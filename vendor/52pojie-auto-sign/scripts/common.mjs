import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import dotenv from 'dotenv';
import { firefox } from 'playwright';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = process.env.POJIE_PROJECT_ROOT
  ? path.resolve(process.env.POJIE_PROJECT_ROOT)
  : path.resolve(__dirname, '..');

dotenv.config({ path: path.join(projectRoot, '.env') });

function envToggleEnabled(name, fallback) {
  const raw = process.env[name];
  if (raw === undefined || raw === '') {
    return fallback;
  }

  return !['0', 'false', 'no', 'off'].includes(String(raw).trim().toLowerCase());
}

if (envToggleEnabled('POJIE_USE_RUNTIME_COOKIE', true)) {
  dotenv.config({ path: path.join(projectRoot, '.env.runtime'), override: true });
}

export const paths = {
  projectRoot,
  authDir: path.join(projectRoot, '.auth'),
  logsDir: path.join(projectRoot, 'logs'),
  storageState: path.join(projectRoot, '.auth', 'storage-state.json'),
  inspectDir: path.join(projectRoot, 'logs', 'inspect')
};

export const urls = {
  home: 'https://www.52pojie.cn/',
  login: 'https://www.52pojie.cn/member.php?mod=logging&action=login',
  taskList: 'https://www.52pojie.cn/home.php?mod=task&item=new',
  signApply: 'https://www.52pojie.cn/home.php?mod=task&do=apply&id=2',
  signDraw: 'https://www.52pojie.cn/home.php?mod=task&do=draw&id=2',
  signView: 'https://www.52pojie.cn/home.php?mod=task&do=view&id=2'
};

function envFlag(name, fallback) {
  const raw = process.env[name];
  if (raw === undefined || raw === '') {
    return fallback;
  }

  return ['1', 'true', 'yes', 'on'].includes(String(raw).trim().toLowerCase());
}

function envInt(name, fallback) {
  const raw = process.env[name];
  if (raw === undefined || raw === '') {
    return fallback;
  }

  const value = Number.parseInt(String(raw).trim(), 10);
  return Number.isNaN(value) ? fallback : value;
}

function envString(name, fallback) {
  const raw = process.env[name];
  if (raw === undefined || raw === '') {
    return fallback;
  }

  return String(raw);
}

function randomBetween(min, max) {
  if (max <= min) {
    return min;
  }

  return Math.floor(Math.random() * (max - min + 1)) + min;
}

export function isHumanMode({ headless } = {}) {
  const resolvedHeadless = headless ?? envFlag('POJIE_HEADLESS', false);
  return envFlag('POJIE_HUMAN_MODE', !resolvedHeadless);
}

export async function ensureDirs() {
  await fs.mkdir(paths.authDir, { recursive: true });
  await fs.mkdir(paths.logsDir, { recursive: true });
  await fs.mkdir(paths.inspectDir, { recursive: true });
}

export async function readJsonFromStdin() {
  if (process.stdin.isTTY) {
    return {};
  }

  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }

  const raw = Buffer.concat(chunks).toString('utf8').trim();
  if (!raw) {
    return {};
  }

  return JSON.parse(raw);
}

export async function getCredentials({ allowStdin = false, required = true } = {}) {
  const fromStdin = allowStdin ? await readJsonFromStdin() : {};
  const username = fromStdin.username || process.env.POJIE_USERNAME || '';
  const password = fromStdin.password || process.env.POJIE_PASSWORD || '';

  if ((!username || !password) && required) {
    throw new Error(
      'Missing credentials. Set POJIE_USERNAME and POJIE_PASSWORD, or pass JSON via stdin.'
    );
  }

  if (!username || !password) {
    return null;
  }

  return { username, password };
}

export async function launchBrowser({ headless = undefined, storageState } = {}) {
  const resolvedHeadless = envFlag('POJIE_HEADLESS', headless ?? false);
  const humanMode = isHumanMode({ headless: resolvedHeadless });
  const slowMo = envInt('POJIE_SLOW_MO_MS', humanMode ? 90 : 0);
  const viewport = {
    width: envInt('POJIE_VIEWPORT_WIDTH', 1366),
    height: envInt('POJIE_VIEWPORT_HEIGHT', 768)
  };

  if (!resolvedHeadless && !process.env.DISPLAY) {
    throw new Error('当前为有窗口模式，但没有设置 DISPLAY。请先导出 DISPLAY=:1 再运行。');
  }

  const browser = await firefox.launch({
    headless: resolvedHeadless,
    slowMo
  });
  const context = await browser.newContext({
    locale: 'zh-CN',
    timezoneId: envString('POJIE_TIMEZONE_ID', 'Asia/Shanghai'),
    colorScheme: 'light',
    viewport,
    storageState
  });
  const page = await context.newPage();
  page.setDefaultTimeout(30000);
  page.setDefaultNavigationTimeout(30000);
  return { browser, context, page };
}

export async function humanPause(page, { baseMs = 700, jitterMs = 500 } = {}) {
  if (!isHumanMode()) {
    return;
  }

  const delay = randomBetween(baseMs, baseMs + Math.max(0, jitterMs));
  await page.waitForTimeout(delay);
}

export async function humanizePage(page, { allowScroll = true } = {}) {
  if (!isHumanMode()) {
    return;
  }

  try {
    const viewport = page.viewportSize() || { width: 1366, height: 768 };
    const x = randomBetween(80, Math.max(80, viewport.width - 80));
    const y = randomBetween(80, Math.max(80, viewport.height - 80));
    await page.mouse.move(x, y, { steps: randomBetween(8, 18) });

    if (allowScroll) {
      await page.mouse.wheel(0, randomBetween(90, 220));
      await page.waitForTimeout(randomBetween(120, 260));
      await page.mouse.wheel(0, -randomBetween(40, 140));
    }
  } catch {}

  await humanPause(page, { baseMs: 180, jitterMs: 240 });
}

export async function typeLikeHuman(locator, text, { minDelayMs = 70, maxDelayMs = 140 } = {}) {
  const value = String(text ?? '');
  await locator.click({ delay: randomBetween(30, 120) });
  await locator.fill('');
  await locator.type(value, { delay: randomBetween(minDelayMs, maxDelayMs) });
}

export async function saveArtifacts(page, prefix) {
  const stamp = new Date().toISOString().replaceAll(':', '-');
  const screenshotPath = path.join(paths.inspectDir, `${prefix}-${stamp}.png`);
  const htmlPath = path.join(paths.inspectDir, `${prefix}-${stamp}.html`);
  await page.screenshot({ path: screenshotPath, fullPage: true });
  await fs.writeFile(htmlPath, await page.content(), 'utf8');
  return { screenshotPath, htmlPath };
}

export async function saveStorageState(context) {
  await ensureDirs();
  await context.storageState({ path: paths.storageState });
}

export async function loadStorageStateIfExists() {
  try {
    await fs.access(paths.storageState);
    return paths.storageState;
  } catch {
    return undefined;
  }
}

export function getCookieString() {
  return process.env.POJIE_COOKIE || '';
}

export async function keepBrowserOpenIfNeeded(page) {
  const keepOpenMs = envInt('POJIE_KEEP_OPEN_MS', 0);
  if (keepOpenMs <= 0) {
    return;
  }

  // 给人工观察或手动过验证留时间。
  await page.waitForTimeout(keepOpenMs);
}

export function cookieStringToPlaywrightCookies(cookieString) {
  return cookieString
    .split(';')
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => {
      const index = part.indexOf('=');
      if (index === -1) {
        return null;
      }

      const name = part.slice(0, index).trim();
      const value = part.slice(index + 1).trim();
      if (!name) {
        return null;
      }

      return {
        name,
        value,
        domain: '.52pojie.cn',
        path: '/',
        secure: true,
        httpOnly: false,
        sameSite: 'Lax'
      };
    })
    .filter(Boolean);
}

export async function importCookieString(context, cookieString) {
  const cookies = cookieStringToPlaywrightCookies(cookieString);
  if (!cookies.length) {
    throw new Error('POJIE_COOKIE is empty or invalid.');
  }

  await context.addCookies(cookies);
  await saveStorageState(context);
}

export async function isLoggedIn(page) {
  await page.goto(urls.home, { waitUntil: 'domcontentloaded' });
  await humanPause(page, { baseMs: 1200, jitterMs: 900 });

  const state = await page.evaluate(() => {
    const text = document.body?.innerText || '';
    const logoutLink = document.querySelector('a[href*="action=logout"]');
    const usernameNode =
      document.querySelector('#um .vwmy') ||
      document.querySelector('#um strong.vwmy') ||
      document.querySelector('#um a[href*="home.php?mod=space"]');
    const loginLink = document.querySelector('a[href*="action=login"]');

    return {
      loggedIn: Boolean(logoutLink) || (!loginLink && text.includes('退出')),
      usernameText: usernameNode?.textContent?.trim() || '',
      pageTitle: document.title
    };
  });

  return state;
}

export async function performLogin(page, credentials) {
  await page.goto(urls.home, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle').catch(() => {});
  await humanPause(page, { baseMs: 900, jitterMs: 700 });

  const quickLoginVisible = await page.locator('#lsform').count();
  const quickResult = {
    attempted: false,
    responseText: ''
  };

  if (quickLoginVisible) {
    quickResult.attempted = true;
    await typeLikeHuman(page.locator('#ls_username'), credentials.username);
    await humanPause(page, { baseMs: 180, jitterMs: 220 });
    await typeLikeHuman(page.locator('#ls_password'), credentials.password);
    await humanPause(page, { baseMs: 220, jitterMs: 280 });
    await page.locator('#lsform button[type="submit"]').click();
    await page.waitForTimeout(6000);
    quickResult.responseText = await page.locator('#return_ls').innerText().catch(() => '');

    const quickState = await isLoggedIn(page);
    if (quickState.loggedIn) {
      return {
        ...quickState,
        captchaInfo: { hasHCaptcha: false, hasSeccode: false },
        bodyText: quickResult.responseText,
        url: page.url()
      };
    }
  }

  await page.goto(urls.login, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle').catch(() => {});
  await humanPause(page, { baseMs: 1000, jitterMs: 800 });

  const captchaInfo = await page.evaluate(() => ({
    hasHCaptcha: Boolean(
      document.querySelector('iframe[src*="hcaptcha"], iframe[src*="challenges.cloudflare.com"]')
    ),
    hasSeccode: Boolean(
      document.querySelector('input[name="seccodeverify"], input[id*="seccodeverify"]')
    )
  }));

  await typeLikeHuman(page.locator('input[name="username"]').first(), credentials.username);
  await humanPause(page, { baseMs: 180, jitterMs: 220 });
  await typeLikeHuman(page.locator('input[name="password"]').first(), credentials.password);
  await humanPause(page, { baseMs: 220, jitterMs: 280 });

  const questionSelect = page.locator('select[name="questionid"]').first();
  if (await questionSelect.count()) {
    await questionSelect.selectOption('0');
  }

  const submit = page
    .locator('form[name="login"] button[name="loginsubmit"], form[name="login"] input[name="loginsubmit"]')
    .first();

  const loginResponsePromise = page
    .waitForResponse((response) => response.url().includes('member.php?mod=logging&action=login'), {
      timeout: 10000
    })
    .then(async (response) => {
      const buffer = await response.body().catch(() => null);
      let text = '';

      if (buffer) {
        try {
          text = new TextDecoder('gbk').decode(buffer);
        } catch {
          text = buffer.toString('utf8');
        }
      }

      return {
        status: response.status(),
        url: response.url(),
        text
      };
    })
    .catch(() => null);

  await submit.click();
  await page.waitForTimeout(6000);

  const loginState = await isLoggedIn(page);
  const bodyText = await page.locator('body').innerText().catch(() => '');
  const loginResponse = await loginResponsePromise;

  return {
    ...loginState,
    captchaInfo,
    quickResult,
    bodyText: (loginResponse?.text || bodyText).slice(0, 4000),
    url: page.url()
  };
}

export async function findRelevantLinks(page) {
  return page.evaluate(() => {
    return Array.from(document.querySelectorAll('a[href]'))
      .map((anchor) => {
        const href = anchor.getAttribute('href') || '';
        const text = (anchor.textContent || '').trim();
        return { href, text };
      })
      .filter(({ href, text }) => {
        return (
          href.includes('task') ||
          href.includes('plugin.php') ||
          text.includes('签到') ||
          text.includes('任务') ||
          text.includes('奖励')
        );
      })
      .slice(0, 100);
  });
}

export async function extractMessageText(page) {
  return page.evaluate(() => {
    const message =
      document.querySelector('#messagetext') ||
      document.querySelector('.alert_info') ||
      document.querySelector('.alert_error') ||
      document.querySelector('.showmessage');

    return {
      title: document.title,
      url: location.href,
      bodySnippet: (document.body?.innerText || '').slice(0, 2000),
      messageText: message?.textContent?.replace(/\s+/g, ' ').trim() || ''
    };
  });
}

export function summarizeSignResult(results) {
  const combined = results
    .map((item) => `${item.label}: ${item.info.messageText || item.info.bodySnippet}`)
    .join('\n');

  const normalized = combined.replace(/\s+/g, ' ');

  if (/waf_text_verify|请完成安全验证|验证码访问/i.test(normalized)) {
    return 'waf_verification_required';
  }

  if (/已成功领取每日登录奖励|奖励领取成功|任务已成功完成/i.test(normalized)) {
    return 'success';
  }

  if (/您今天已经申请过此任务|您已经领取过该奖励|下期再来|已申请过此任务/i.test(normalized)) {
    return 'already_done';
  }

  if (/需要先登录|请先登录/i.test(normalized)) {
    return 'login_required';
  }

  return 'unknown';
}
