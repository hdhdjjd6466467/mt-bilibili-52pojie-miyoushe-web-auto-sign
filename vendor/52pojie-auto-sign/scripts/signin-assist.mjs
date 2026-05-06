import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import readline from 'node:readline/promises';

import {
  ensureDirs,
  extractMessageText,
  getCookieString,
  importCookieString,
  isLoggedIn,
  launchBrowser,
  loadStorageStateIfExists,
  paths,
  saveArtifacts,
  saveStorageState,
  summarizeSignResult,
  urls
} from './common.mjs';

async function appendLog(result) {
  const logPath = path.join(paths.logsDir, 'signin.log');
  const line = `${new Date().toISOString()} ${JSON.stringify(result)}\n`;
  await fs.appendFile(logPath, line, 'utf8');
}

async function isWafPage(page) {
  return Boolean(await page.locator('#Image1').count());
}

async function saveCaptcha(page, attempt) {
  const captchaPath = path.join(paths.inspectDir, `waf-captcha-attempt-${attempt}.png`);
  const zoomPath = path.join(paths.inspectDir, `waf-captcha-attempt-${attempt}-zoom.png`);
  await page.locator('#Image1').screenshot({ path: captchaPath });
  const rendered = await page.evaluate(() => {
    const image = document.getElementById('Image1');
    if (!image) {
      return {
        zoomDataUrl: '',
        masks: []
      };
    }

    const sourceCanvas = document.createElement('canvas');
    sourceCanvas.width = image.naturalWidth;
    sourceCanvas.height = image.naturalHeight;
    const sourceContext = sourceCanvas.getContext('2d');
    sourceContext.drawImage(image, 0, 0);

    const scale = 6;
    const canvas = document.createElement('canvas');
    canvas.width = image.naturalWidth * scale;
    canvas.height = image.naturalHeight * scale;

    const context = canvas.getContext('2d');
    context.imageSmoothingEnabled = false;
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    const imageData = sourceContext.getImageData(0, 0, sourceCanvas.width, sourceCanvas.height);
    const buckets = new Map();

    for (let index = 0; index < imageData.data.length; index += 4) {
      const r = imageData.data[index];
      const g = imageData.data[index + 1];
      const b = imageData.data[index + 2];
      const alpha = imageData.data[index + 3];
      if (alpha < 10) {
        continue;
      }

      if (r + g + b > 700) {
        continue;
      }

      const key = `${Math.floor(r / 32)},${Math.floor(g / 32)},${Math.floor(b / 32)}`;
      const bucket = buckets.get(key) || { count: 0, r: 0, g: 0, b: 0 };
      bucket.count += 1;
      bucket.r += r;
      bucket.g += g;
      bucket.b += b;
      buckets.set(key, bucket);
    }

    const topBuckets = Array.from(buckets.entries())
      .sort((left, right) => right[1].count - left[1].count)
      .slice(0, 4)
      .map(([key, bucket]) => ({
        key,
        r: bucket.r / bucket.count,
        g: bucket.g / bucket.count,
        b: bucket.b / bucket.count
      }));

    const masks = topBuckets.map((bucket) => {
      const maskCanvas = document.createElement('canvas');
      maskCanvas.width = sourceCanvas.width;
      maskCanvas.height = sourceCanvas.height;
      const maskContext = maskCanvas.getContext('2d');
      const maskData = maskContext.createImageData(sourceCanvas.width, sourceCanvas.height);

      for (let index = 0; index < imageData.data.length; index += 4) {
        const r = imageData.data[index];
        const g = imageData.data[index + 1];
        const b = imageData.data[index + 2];
        const alpha = imageData.data[index + 3];
        const distance = Math.sqrt(
          (r - bucket.r) ** 2 + (g - bucket.g) ** 2 + (b - bucket.b) ** 2
        );
        const on = alpha >= 10 && distance < 40;
        maskData.data[index] = on ? 0 : 255;
        maskData.data[index + 1] = on ? 0 : 255;
        maskData.data[index + 2] = on ? 0 : 255;
        maskData.data[index + 3] = 255;
      }

      maskContext.putImageData(maskData, 0, 0);

      const scaledCanvas = document.createElement('canvas');
      scaledCanvas.width = sourceCanvas.width * scale;
      scaledCanvas.height = sourceCanvas.height * scale;
      const scaledContext = scaledCanvas.getContext('2d');
      scaledContext.imageSmoothingEnabled = false;
      scaledContext.drawImage(maskCanvas, 0, 0, scaledCanvas.width, scaledCanvas.height);

      return {
        key: bucket.key,
        dataUrl: scaledCanvas.toDataURL('image/png')
      };
    });

    return {
      zoomDataUrl: canvas.toDataURL('image/png'),
      masks
    };
  });

  if (rendered.zoomDataUrl.startsWith('data:image/png;base64,')) {
    const base64 = rendered.zoomDataUrl.slice('data:image/png;base64,'.length);
    await fs.writeFile(zoomPath, Buffer.from(base64, 'base64'));
  }

  const maskPaths = [];
  for (const [index, mask] of rendered.masks.entries()) {
    if (!mask.dataUrl.startsWith('data:image/png;base64,')) {
      continue;
    }

    const maskPath = path.join(paths.inspectDir, `waf-captcha-attempt-${attempt}-mask-${index + 1}.png`);
    const base64 = mask.dataUrl.slice('data:image/png;base64,'.length);
    await fs.writeFile(maskPath, Buffer.from(base64, 'base64'));
    maskPaths.push({
      key: mask.key,
      path: maskPath
    });
  }

  return { captchaPath, zoomPath, maskPaths };
}

async function solveWafInteractively(page) {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
  });

  try {
    for (let attempt = 1; attempt <= 12; attempt += 1) {
      if (!(await isWafPage(page))) {
        return {
          solved: true,
          attempts: attempt - 1
        };
      }

      const captcha = await saveCaptcha(page, attempt);
      console.log(
        JSON.stringify(
          {
            status: 'waf_verification_required',
            attempt,
            captchaPath: captcha.captchaPath,
            zoomPath: captcha.zoomPath,
            maskPaths: captcha.maskPaths,
            pageTitle: await page.title(),
            pageUrl: page.url()
          },
          null,
          2
        )
      );

      const answer = (await rl.question(`Enter captcha for attempt ${attempt}: `)).trim();
      if (!answer) {
        continue;
      }

      await page.locator('input[name="captcha"]').fill(answer);
      await Promise.all([
        page.waitForLoadState('domcontentloaded').catch(() => {}),
        page.locator('input[type="submit"], .code-btn').click()
      ]);
      await page.waitForTimeout(1500);
    }

    return {
      solved: !(await isWafPage(page)),
      attempts: 12
    };
  } finally {
    rl.close();
  }
}

async function main() {
  await ensureDirs();

  const cookieString = getCookieString();
  const storageState = await loadStorageStateIfExists();
  const { browser, context, page } = await launchBrowser({ storageState });

  try {
    if (cookieString) {
      await importCookieString(context, cookieString);
    }

    const loginState = await isLoggedIn(page);
    if (!loginState.loggedIn) {
      const failure = {
        ok: false,
        status: 'login_required',
        message:
          'No active session found. Set POJIE_COOKIE to import a logged-in browser session first.'
      };
      await appendLog(failure);
      console.log(JSON.stringify(failure, null, 2));
      return;
    }

    await page.goto(urls.taskList, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2500);

    const wafResult = await solveWafInteractively(page);
    if (!wafResult.solved) {
      const artifacts = await saveArtifacts(page, 'signin-assist-waf-failed');
      const failure = {
        ok: false,
        status: 'waf_verification_required',
        usernameText: loginState.usernameText,
        wafAttempts: wafResult.attempts,
        artifacts
      };
      await appendLog(failure);
      console.log(JSON.stringify(failure, null, 2));
      return;
    }

    const visited = [];
    for (const [label, url] of [
      ['task-list', urls.taskList],
      ['apply', urls.signApply],
      ['draw', urls.signDraw],
      ['view', urls.signView]
    ]) {
      await page.goto(url, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(2500);
      visited.push({ label, url, info: await extractMessageText(page) });
    }

    await saveStorageState(context);

    const status = summarizeSignResult(visited);
    const artifacts = await saveArtifacts(page, 'signin-assist-final');
    const result = {
      ok: status === 'success' || status === 'already_done',
      status,
      usernameText: loginState.usernameText,
      wafAttempts: wafResult.attempts,
      visited,
      artifacts
    };

    await appendLog(result);
    console.log(JSON.stringify(result, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch(async (error) => {
  const result = {
    ok: false,
    status: 'error',
    error: error.message
  };
  try {
    await ensureDirs();
    await appendLog(result);
  } catch {}
  console.error(JSON.stringify(result, null, 2));
  process.exitCode = 1;
});
