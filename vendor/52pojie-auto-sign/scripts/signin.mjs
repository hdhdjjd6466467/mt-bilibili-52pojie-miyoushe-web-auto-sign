import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  ensureDirs,
  extractMessageText,
  getCredentials,
  getCookieString,
  importCookieString,
  isLoggedIn,
  keepBrowserOpenIfNeeded,
  launchBrowser,
  loadStorageStateIfExists,
  humanPause,
  humanizePage,
  paths,
  performLogin,
  saveArtifacts,
  saveStorageState,
  summarizeSignResult,
  typeLikeHuman,
  urls
} from './common.mjs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const wafOcrHelperPath = path.join(__dirname, 'solve-waf-captcha.py');
const wafExpectedLength = 4;
const wafPythonBin = process.env.POJIE_PYTHON_BIN || 'python3';

async function appendLog(result) {
  const logPath = path.join(paths.logsDir, 'signin.log');
  const line = `${new Date().toISOString()} ${JSON.stringify(result)}\n`;
  await fs.appendFile(logPath, line, 'utf8');
}

async function isWafPage(page) {
  return Boolean(await page.locator('#Image1').count());
}

function normalizeCaptchaGuess(value) {
  return String(value || '').replace(/[^0-9A-Za-z]/g, '').trim();
}

function uniqueGuesses(values) {
  return [...new Set(values.filter(Boolean))];
}

async function analyzeWafWithExternalOcr(page) {
  try {
    const imageBuffer = await page.locator('#Image1').first().screenshot();
    const fingerprint = createHash('sha1').update(imageBuffer).digest('hex');
    const result = spawnSync(wafPythonBin, [wafOcrHelperPath], {
      input: imageBuffer,
      encoding: 'utf8',
      maxBuffer: 10 * 1024 * 1024
    });

    if (result.error) {
      return { guess: '', fingerprint, candidates: [], error: result.error.message };
    }

    const stdout = result.stdout?.trim() || '';
    if (result.status !== 0 || !stdout) {
      return {
        guess: '',
        fingerprint,
        candidates: [],
        error: result.stderr?.trim() || `solver exited with code ${result.status ?? 'unknown'}`
      };
    }

    const parsed = JSON.parse(stdout);
    return {
      guess: normalizeCaptchaGuess(parsed.guess),
      fingerprint,
      expectedLength: Number(parsed.expectedLength) || wafExpectedLength,
      importError: parsed.importError || '',
      candidates: (parsed.candidates || []).map((candidate) => ({
        ...candidate,
        text: normalizeCaptchaGuess(candidate.text),
        variants: (candidate.variants || []).map((variant) => ({
          ...variant,
          text: normalizeCaptchaGuess(variant.text)
        })),
        engines: candidate.engines || []
      }))
    };
  } catch (error) {
    return { guess: '', candidates: [], error: error.message };
  }
}

function pickWafGuess(external, internal) {
  const expectedLength = external?.expectedLength || wafExpectedLength;
  const externalGuess = normalizeCaptchaGuess(external?.guess);
  const internalGuess = normalizeCaptchaGuess(internal?.guess);
  const bestExternal = external?.candidates?.[0];
  const externalVariants = uniqueGuesses(
    (bestExternal?.variants || [])
      .map((variant) => normalizeCaptchaGuess(variant.text))
      .filter((variant) => variant.length === expectedLength)
  );
  const externalIsStable =
    normalizeCaptchaGuess(bestExternal?.text) === externalGuess &&
    Number(bestExternal?.score || 0) >= 6 &&
    Number(bestExternal?.count || 0) >= 2;

  if (externalGuess.length === expectedLength && externalIsStable) {
    const guesses = uniqueGuesses([externalGuess, ...externalVariants]);
    if (
      internalGuess.length === expectedLength &&
      internalGuess.toUpperCase() === externalGuess.toUpperCase() &&
      !guesses.includes(internalGuess)
    ) {
      guesses.push(internalGuess);
    }

    return { guess: guesses[0] || externalGuess, guesses, engine: 'external', expectedLength };
  }

  if (internalGuess.length === expectedLength) {
    return { guess: internalGuess, guesses: [internalGuess], engine: 'internal', expectedLength };
  }

  return { guess: '', guesses: [], engine: null, expectedLength };
}

async function analyzeWafCaptcha(page) {
  return page.evaluate(() => {
    const image = document.getElementById('Image1');
    if (!image) {
      return null;
    }

    const width = image.naturalWidth || image.width || 80;
    const height = image.naturalHeight || image.height || 34;
    const scale = 6;
    const charset = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz';
    const fonts = ['Arial', 'Verdana', 'Tahoma', 'Trebuchet MS', 'Georgia', 'Times New Roman', 'Courier New'];
    const sourceCanvas = document.createElement('canvas');
    sourceCanvas.width = width;
    sourceCanvas.height = height;
    const sourceContext = sourceCanvas.getContext('2d');
    sourceContext.drawImage(image, 0, 0, width, height);
    const source = sourceContext.getImageData(0, 0, width, height);
    const pixels = source.data;

    function createBinary(size = width * height) {
      return new Uint8Array(size);
    }

    function brightnessAt(offset) {
      return pixels[offset] + pixels[offset + 1] + pixels[offset + 2];
    }

    function normalizeBitmap(binary, sourceWidth, sourceHeight, targetWidth = 24, targetHeight = 32) {
      const output = new Uint8Array(targetWidth * targetHeight);
      const scaleFactor = Math.min(targetWidth / sourceWidth, targetHeight / sourceHeight);
      const scaledWidth = Math.max(1, Math.round(sourceWidth * scaleFactor));
      const scaledHeight = Math.max(1, Math.round(sourceHeight * scaleFactor));
      const offsetX = Math.floor((targetWidth - scaledWidth) / 2);
      const offsetY = Math.floor((targetHeight - scaledHeight) / 2);

      for (let y = 0; y < scaledHeight; y += 1) {
        for (let x = 0; x < scaledWidth; x += 1) {
          const sourceX = Math.min(sourceWidth - 1, Math.floor((x / Math.max(1, scaledWidth)) * sourceWidth));
          const sourceY = Math.min(sourceHeight - 1, Math.floor((y / Math.max(1, scaledHeight)) * sourceHeight));
          if (!binary[sourceY * sourceWidth + sourceX]) {
            continue;
          }

          output[(offsetY + y) * targetWidth + offsetX + x] = 1;
        }
      }

      return output;
    }

    function bitmapFill(binary) {
      let filled = 0;
      for (const pixel of binary) {
        filled += pixel;
      }

      return filled / binary.length;
    }

    function drawScaledBinary(binary, binaryWidth, binaryHeight) {
      const canvas = document.createElement('canvas');
      canvas.width = binaryWidth;
      canvas.height = binaryHeight;
      const context = canvas.getContext('2d');
      const imageData = context.createImageData(binaryWidth, binaryHeight);

      for (let index = 0; index < binary.length; index += 1) {
        const value = binary[index] ? 0 : 255;
        const offset = index * 4;
        imageData.data[offset] = value;
        imageData.data[offset + 1] = value;
        imageData.data[offset + 2] = value;
        imageData.data[offset + 3] = 255;
      }

      context.putImageData(imageData, 0, 0);
      const zoomCanvas = document.createElement('canvas');
      zoomCanvas.width = binaryWidth * scale;
      zoomCanvas.height = binaryHeight * scale;
      const zoomContext = zoomCanvas.getContext('2d');
      zoomContext.imageSmoothingEnabled = false;
      zoomContext.drawImage(canvas, 0, 0, zoomCanvas.width, zoomCanvas.height);
      return zoomCanvas.toDataURL('image/png');
    }

    function buildMasks() {
      const buckets = new Map();

      for (let pixel = 0; pixel < width * height; pixel += 1) {
        const offset = pixel * 4;
        if (pixels[offset + 3] < 10 || brightnessAt(offset) > 715) {
          continue;
        }

        const key = `${Math.floor(pixels[offset] / 32)},${Math.floor(pixels[offset + 1] / 32)},${Math.floor(pixels[offset + 2] / 32)}`;
        const bucket = buckets.get(key) || { count: 0, r: 0, g: 0, b: 0 };
        bucket.count += 1;
        bucket.r += pixels[offset];
        bucket.g += pixels[offset + 1];
        bucket.b += pixels[offset + 2];
        buckets.set(key, bucket);
      }

      return Array.from(buckets.entries())
        .sort((left, right) => right[1].count - left[1].count)
        .slice(0, 5)
        .map(([key, bucket]) => {
          const target = { r: bucket.r / bucket.count, g: bucket.g / bucket.count, b: bucket.b / bucket.count };
          const binary = createBinary();

          for (let pixel = 0; pixel < width * height; pixel += 1) {
            const offset = pixel * 4;
            if (pixels[offset + 3] < 10 || brightnessAt(offset) > 705) {
              continue;
            }

            const distance = Math.sqrt(
              (pixels[offset] - target.r) ** 2 +
              (pixels[offset + 1] - target.g) ** 2 +
              (pixels[offset + 2] - target.b) ** 2
            );

            if (distance < 44) {
              binary[pixel] = 1;
            }
          }

          return { key, binary };
        });
    }

    function despeckle(binary) {
      const next = new Uint8Array(binary);
      for (let y = 1; y < height - 1; y += 1) {
        for (let x = 1; x < width - 1; x += 1) {
          const index = y * width + x;
          if (!binary[index]) {
            continue;
          }

          let neighbors = 0;
          for (let offsetY = -1; offsetY <= 1; offsetY += 1) {
            for (let offsetX = -1; offsetX <= 1; offsetX += 1) {
              if (!offsetX && !offsetY) {
                continue;
              }

              neighbors += binary[(y + offsetY) * width + (x + offsetX)] ? 1 : 0;
            }
          }

          if (neighbors <= 1) {
            next[index] = 0;
          }
        }
      }

      return next;
    }

    function removeWeakComponents(binary) {
      const visited = new Uint8Array(binary.length);
      const next = createBinary();

      for (let start = 0; start < binary.length; start += 1) {
        if (!binary[start] || visited[start]) {
          continue;
        }

        const queue = [start];
        const points = [];
        visited[start] = 1;
        let minX = width;
        let maxX = 0;
        let minY = height;
        let maxY = 0;

        while (queue.length) {
          const current = queue.pop();
          const x = current % width;
          const y = Math.floor(current / width);
          points.push(current);
          minX = Math.min(minX, x);
          maxX = Math.max(maxX, x);
          minY = Math.min(minY, y);
          maxY = Math.max(maxY, y);

          for (let offsetY = -1; offsetY <= 1; offsetY += 1) {
            for (let offsetX = -1; offsetX <= 1; offsetX += 1) {
              if (!offsetX && !offsetY) {
                continue;
              }

              const nextX = x + offsetX;
              const nextY = y + offsetY;
              if (nextX < 0 || nextY < 0 || nextX >= width || nextY >= height) {
                continue;
              }

              const nextIndex = nextY * width + nextX;
              if (!binary[nextIndex] || visited[nextIndex]) {
                continue;
              }

              visited[nextIndex] = 1;
              queue.push(nextIndex);
            }
          }
        }

        const boxWidth = maxX - minX + 1;
        const boxHeight = maxY - minY + 1;
        const keep =
          points.length >= 10 &&
          boxWidth >= 2 &&
          boxHeight >= Math.max(8, Math.floor(height * 0.28)) &&
          !(boxWidth >= Math.floor(width * 0.72) && boxHeight <= 4);

        if (!keep) {
          continue;
        }

        for (const point of points) {
          next[point] = 1;
        }
      }

      return next;
    }

    function projectionSegments(binary) {
      const columns = Array.from({ length: width }, () => 0);
      for (let x = 0; x < width; x += 1) {
        for (let y = 0; y < height; y += 1) {
          columns[x] += binary[y * width + x];
        }
      }

      const groups = [];
      let start = -1;
      for (let x = 0; x < width; x += 1) {
        if (columns[x] > 0 && start === -1) {
          start = x;
        }

        if (!columns[x] && start !== -1) {
          groups.push({ start, end: x - 1 });
          start = -1;
        }
      }

      if (start !== -1) {
        groups.push({ start, end: width - 1 });
      }

      const merged = [];
      for (const group of groups) {
        const previous = merged.at(-1);
        if (previous && group.start - previous.end <= 2) {
          previous.end = group.end;
        } else {
          merged.push({ ...group });
        }
      }

      return merged.filter((group) => group.end - group.start + 1 >= 3);
    }

    function trimSegment(binary, startX, endX) {
      let minX = endX;
      let maxX = startX;
      let minY = height;
      let maxY = 0;
      let area = 0;

      for (let x = startX; x <= endX; x += 1) {
        for (let y = 0; y < height; y += 1) {
          const index = y * width + x;
          if (!binary[index]) {
            continue;
          }

          area += 1;
          minX = Math.min(minX, x);
          maxX = Math.max(maxX, x);
          minY = Math.min(minY, y);
          maxY = Math.max(maxY, y);
        }
      }

      if (!area) {
        return null;
      }

      const segmentWidth = maxX - minX + 1;
      const segmentHeight = maxY - minY + 1;
      const segmentBinary = new Uint8Array(segmentWidth * segmentHeight);

      for (let y = minY; y <= maxY; y += 1) {
        for (let x = minX; x <= maxX; x += 1) {
          if (!binary[y * width + x]) {
            continue;
          }

          segmentBinary[(y - minY) * segmentWidth + (x - minX)] = 1;
        }
      }

      return { width: segmentWidth, height: segmentHeight, binary: segmentBinary };
    }

    const templateCanvas = document.createElement('canvas');
    templateCanvas.width = 64;
    templateCanvas.height = 72;
    const templateContext = templateCanvas.getContext('2d');
    const templates = [];

    for (const character of charset) {
      for (const font of fonts) {
        for (const weight of ['700', '900']) {
          templateContext.fillStyle = '#ffffff';
          templateContext.fillRect(0, 0, templateCanvas.width, templateCanvas.height);
          templateContext.fillStyle = '#000000';
          templateContext.textAlign = 'center';
          templateContext.textBaseline = 'middle';
          templateContext.font = `${weight} 50px ${font}`;
          templateContext.fillText(character, templateCanvas.width / 2, templateCanvas.height / 2 + 2);

          const rendered = templateContext.getImageData(0, 0, templateCanvas.width, templateCanvas.height);
          let minX = templateCanvas.width;
          let maxX = 0;
          let minY = templateCanvas.height;
          let maxY = 0;
          let area = 0;

          for (let y = 0; y < templateCanvas.height; y += 1) {
            for (let x = 0; x < templateCanvas.width; x += 1) {
              const offset = (y * templateCanvas.width + x) * 4;
              const on = rendered.data[offset + 3] > 0 && rendered.data[offset] < 180;
              if (!on) {
                continue;
              }

              area += 1;
              minX = Math.min(minX, x);
              maxX = Math.max(maxX, x);
              minY = Math.min(minY, y);
              maxY = Math.max(maxY, y);
            }
          }

          if (!area) {
            continue;
          }

          const glyphWidth = maxX - minX + 1;
          const glyphHeight = maxY - minY + 1;
          const glyph = new Uint8Array(glyphWidth * glyphHeight);
          for (let y = minY; y <= maxY; y += 1) {
            for (let x = minX; x <= maxX; x += 1) {
              const offset = (y * templateCanvas.width + x) * 4;
              if (rendered.data[offset + 3] > 0 && rendered.data[offset] < 180) {
                glyph[(y - minY) * glyphWidth + (x - minX)] = 1;
              }
            }
          }

          const normalized = normalizeBitmap(glyph, glyphWidth, glyphHeight);
          templates.push({ character, binary: normalized, fill: bitmapFill(normalized), aspect: glyphWidth / Math.max(1, glyphHeight) });
        }
      }
    }

    function compareBitmap(left, right) {
      let difference = 0;
      for (let index = 0; index < left.length; index += 1) {
        difference += left[index] === right[index] ? 0 : 1;
      }

      return difference / left.length;
    }

    function classifySegment(segment) {
      const normalized = normalizeBitmap(segment.binary, segment.width, segment.height);
      const fill = bitmapFill(normalized);
      const aspect = segment.width / Math.max(1, segment.height);
      const candidates = templates.map((template) => ({
        character: template.character,
        score: compareBitmap(normalized, template.binary) + Math.abs(fill - template.fill) * 0.35 + Math.abs(aspect - template.aspect) * 0.18
      }));

      candidates.sort((left, right) => left.score - right.score);
      return candidates.slice(0, 4);
    }

    function analyzeMask(mask) {
      const cleaned = removeWeakComponents(despeckle(mask.binary));
      const segments = projectionSegments(cleaned)
        .map((segment) => trimSegment(cleaned, segment.start, segment.end))
        .filter(Boolean);

      if (segments.length < 4 || segments.length > 5) {
        return { key: mask.key, guess: '', score: 999, segmentCount: segments.length, dataUrl: drawScaledBinary(cleaned, width, height) };
      }

      const picks = segments.map((segment) => classifySegment(segment));
      return {
        key: mask.key,
        guess: picks.map((pick) => pick[0].character).join(''),
        score: picks.reduce((total, pick) => total + pick[0].score, 0) / picks.length,
        segmentCount: segments.length,
        candidates: picks,
        dataUrl: drawScaledBinary(cleaned, width, height)
      };
    }

    const masks = buildMasks();
    const analyses = masks.map(analyzeMask).sort((left, right) => left.score - right.score);
    const zoomCanvas = document.createElement('canvas');
    zoomCanvas.width = width * scale;
    zoomCanvas.height = height * scale;
    const zoomContext = zoomCanvas.getContext('2d');
    zoomContext.imageSmoothingEnabled = false;
    zoomContext.drawImage(sourceCanvas, 0, 0, zoomCanvas.width, zoomCanvas.height);

    return {
      guess: analyses[0]?.guess || '',
      score: analyses[0]?.score ?? 999,
      candidates: analyses.slice(0, 3).map((analysis) => ({ key: analysis.key, guess: analysis.guess, score: analysis.score, segmentCount: analysis.segmentCount })),
      zoomDataUrl: zoomCanvas.toDataURL('image/png'),
      masks: analyses.map((analysis, index) => ({ rank: index + 1, key: analysis.key, guess: analysis.guess, score: analysis.score, segmentCount: analysis.segmentCount, dataUrl: analysis.dataUrl }))
    };
  });
}

async function saveWafArtifacts(page, analysis, prefix, extra = {}) {
  const stamp = new Date().toISOString().replaceAll(':', '-');
  const screenshotPath = path.join(paths.inspectDir, `${prefix}-${stamp}.png`);
  const zoomPath = path.join(paths.inspectDir, `${prefix}-${stamp}-zoom.png`);
  await page.locator('#Image1').first().screenshot({ path: screenshotPath });

  if (analysis?.zoomDataUrl?.startsWith('data:image/png;base64,')) {
    await fs.writeFile(zoomPath, Buffer.from(analysis.zoomDataUrl.slice('data:image/png;base64,'.length), 'base64'));
  }

  const maskPaths = [];
  for (const [index, mask] of (analysis?.masks || []).entries()) {
    if (!mask.dataUrl?.startsWith('data:image/png;base64,')) {
      continue;
    }

    const maskPath = path.join(paths.inspectDir, `${prefix}-${stamp}-mask-${index + 1}.png`);
    await fs.writeFile(maskPath, Buffer.from(mask.dataUrl.slice('data:image/png;base64,'.length), 'base64'));
    maskPaths.push({ ...mask, path: maskPath });
  }

  return { screenshotPath, zoomPath, maskPaths, candidates: analysis?.candidates || [], ...extra };
}

async function refreshWafCaptcha(page) {
  const refresh = page.locator('.captcha-refresh a, .refreshIcon').first();
  if (await refresh.count()) {
    await humanPause(page, { baseMs: 180, jitterMs: 220 });
    await refresh.click();
    await humanPause(page, { baseMs: 450, jitterMs: 450 });
    await humanizePage(page, { allowScroll: false });
    return;
  }

  await page.reload({ waitUntil: 'domcontentloaded' });
  await humanPause(page, { baseMs: 800, jitterMs: 700 });
  await humanizePage(page, { allowScroll: false });
}

async function readWafFingerprint(page) {
  try {
    const imageBuffer = await page.locator('#Image1').first().screenshot();
    return createHash('sha1').update(imageBuffer).digest('hex');
  } catch {
    return '';
  }
}

async function submitWafGuess(page, guess) {
  const captchaInput = page.locator('input[name="captcha"]').first();
  await humanPause(page, { baseMs: 180, jitterMs: 220 });
  await typeLikeHuman(captchaInput, guess, { minDelayMs: 60, maxDelayMs: 130 });
  await humanPause(page, { baseMs: 160, jitterMs: 180 });
  await Promise.all([
    page.waitForLoadState('domcontentloaded').catch(() => {}),
    page.locator('input[type="submit"], .code-btn').first().click()
  ]);
  await humanPause(page, { baseMs: 1100, jitterMs: 700 });
}

async function solveWafAutomatically(page, { maxAttempts = 6 } = {}) {
  const history = [];

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    if (!(await isWafPage(page))) {
      return { encountered: history.length > 0, solved: true, attempts: history.length, history };
    }

    const external = await analyzeWafWithExternalOcr(page);
    const internal = await analyzeWafCaptcha(page);
    const pick = pickWafGuess(external, internal);
    const attemptRecord = {
      attempt,
      guess: pick.guess,
      guesses: pick.guesses || [],
      engine: pick.engine,
      expectedLength: pick.expectedLength,
      externalFingerprint: external.fingerprint || null,
      externalError: external.error || null,
      externalCandidates: external.candidates || [],
      internalScore: internal?.score ?? null,
      internalCandidates: internal?.candidates || [],
      guessesTried: []
    };
    history.push(attemptRecord);

    if (!pick.guesses?.length) {
      await refreshWafCaptcha(page);
      continue;
    }

    for (const guess of pick.guesses.slice(0, 3)) {
      attemptRecord.guess = guess;
      attemptRecord.guessesTried.push(guess);
      await submitWafGuess(page, guess);

      if (!(await isWafPage(page))) {
        return { encountered: true, solved: true, attempts: history.length, history };
      }

      const nextFingerprint = await readWafFingerprint(page);
      if (nextFingerprint && nextFingerprint !== external.fingerprint) {
        attemptRecord.captchaChanged = true;
        break;
      }
    }

    await refreshWafCaptcha(page);
  }

  return { encountered: history.length > 0, solved: !(await isWafPage(page)), attempts: history.length, history };
}

async function visitWithWaf(page, context, label, url) {
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await humanPause(page, { baseMs: 1700, jitterMs: 1200 });
  await humanizePage(page);

  let waf = null;
  if (await isWafPage(page)) {
    waf = await solveWafAutomatically(page, { maxAttempts: 6 });
    if (waf.solved) {
      await saveStorageState(context);
    } else {
      const external = await analyzeWafWithExternalOcr(page);
      const analysis = await analyzeWafCaptcha(page);
      waf.artifacts = await saveWafArtifacts(page, analysis, `signin-${label}-waf-failed`, {
        externalGuess: external.guess,
        externalError: external.error || null,
        externalCandidates: external.candidates || []
      });
    }
  }

  await humanPause(page, { baseMs: 900, jitterMs: 700 });
  return { waf, info: await extractMessageText(page) };
}

function normalizeStatus(visited) {
  const status = summarizeSignResult(visited);
  if (status !== 'unknown') {
    return status;
  }

  const taskListText = visited.find((item) => item.label === 'task-list')?.info?.bodySnippet || '';
  const viewText = visited.find((item) => item.label === 'view')?.info?.bodySnippet || '';
  if (/暂无新任务/.test(taskListText) || (/完成于\s*20\d{2}-\d{1,2}-\d{1,2}/.test(viewText) && /可以再次申请/.test(viewText))) {
    return 'already_done';
  }

  return status;
}

async function main() {
  await ensureDirs();

  const credentials = await getCredentials({ required: false });
  const cookieString = getCookieString();
  const storageState = await loadStorageStateIfExists();
  const { browser, context, page } = await launchBrowser({ storageState });

  try {
    if (cookieString) {
      await importCookieString(context, cookieString);
    }

    let loginState = await isLoggedIn(page);
    if (!loginState.loggedIn) {
      if (!credentials) {
        const failure = { ok: false, status: 'login_required', message: 'No active session found. Set POJIE_COOKIE to import a logged-in browser session, or provide POJIE_USERNAME/POJIE_PASSWORD.' };
        await appendLog(failure);
        console.log(JSON.stringify(failure, null, 2));
        process.exitCode = 1;
        return;
      }

      loginState = await performLogin(page, credentials);
      if (!loginState.loggedIn) {
        const failure = {
          ok: false,
          status: 'login_failed',
          url: loginState.url,
          pageTitle: loginState.pageTitle,
          captchaInfo: loginState.captchaInfo,
          quickResult: loginState.quickResult,
          usernameText: loginState.usernameText,
          message: loginState.bodyText.slice(0, 600),
          hint: '52pojie currently requires a verification code during scripted login. Import POJIE_COOKIE from a browser session instead.'
        };
        await appendLog(failure);
        console.log(JSON.stringify(failure, null, 2));
        process.exitCode = 1;
        return;
      }

      await saveStorageState(context);
    }

    const visited = [];
    for (const [label, url] of [
      ['task-list', urls.taskList],
      ['apply', urls.signApply],
      ['draw', urls.signDraw],
      ['view', urls.signView]
    ]) {
      const visit = await visitWithWaf(page, context, label, url);
      visited.push({ label, url, info: visit.info, waf: visit.waf });

      if (visit.waf && !visit.waf.solved) {
        const failure = { ok: false, status: 'waf_verification_required', usernameText: loginState.usernameText, at: label, url, waf: visit.waf };
        await appendLog(failure);
        console.log(JSON.stringify(failure, null, 2));
        process.exitCode = 1;
        return;
      }
    }

    const status = normalizeStatus(visited);
    const artifacts = await saveArtifacts(page, 'signin-final');
    const result = { ok: status === 'success' || status === 'already_done', status, usernameText: loginState.usernameText, visited, artifacts };

    await appendLog(result);
    console.log(JSON.stringify(result, null, 2));
    if (!result.ok) {
      process.exitCode = 1;
    }
    await keepBrowserOpenIfNeeded(page);
  } finally {
    await browser.close();
  }
}

main().catch(async (error) => {
  const result = { ok: false, status: 'error', error: error.message };
  try {
    await ensureDirs();
    await appendLog(result);
  } catch {}
  console.error(JSON.stringify(result, null, 2));
  process.exitCode = 1;
});
