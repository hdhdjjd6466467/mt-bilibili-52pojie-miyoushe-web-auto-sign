import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import { firefox } from 'playwright';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const vendor52Root = path.resolve(__dirname, '..');
const vendorRoot = path.resolve(vendor52Root, '..');
const projectRoot = path.resolve(vendorRoot, '..');
const ROOT_STATE_DIR =
  process.env.SIGNADMIN_BROWSER_STATE_DIR || path.join(projectRoot, 'state', 'browser-cookie-sync');

const SITES = {
  '52pojie': {
    key: '52pojie',
    label: '52pojie',
    homeUrls: ['https://www.52pojie.cn/'],
    profileDir: process.env.POJIE_PROFILE_DIR || path.join(ROOT_STATE_DIR, '52pojie'),
    runtimePath: process.env.POJIE_RUNTIME_PATH || path.join(vendor52Root, '.env.runtime'),
    staticPath: process.env.POJIE_STATIC_PATH || path.join(vendor52Root, '.env'),
    staticKey: 'POJIE_COOKIE',
    importDomains: ['.52pojie.cn'],
    exportDomains: ['.52pojie.cn'],
    requirements: [['htVC_2132_auth'], ['htVC_2132_saltkey']],
    runtimeFormatter(cookie) {
      return `POJIE_COOKIE="${escapeEnv(cookie)}"\n`;
    }
  },
  mihoyo: {
    key: 'mihoyo',
    label: 'MihoyoBBSTools',
    homeUrls: ['https://www.miyoushe.com/ys/', 'https://user.mihoyo.com/'],
    profileDir: process.env.MIHOYO_PROFILE_DIR || path.join(ROOT_STATE_DIR, 'mihoyo'),
    runtimePath: process.env.MIHOYO_RUNTIME_PATH || path.join(vendorRoot, 'MihoyoBBSTools', 'config', 'runtime.yaml'),
    staticPath: process.env.MIHOYO_STATIC_PATH || path.join(vendorRoot, 'MihoyoBBSTools', 'config', 'config.yaml'),
    importDomains: ['.miyoushe.com', '.mihoyo.com'],
    exportDomains: ['.miyoushe.com', '.mihoyo.com'],
    requirements: [
      ['cookie_token', 'cookie_token_v2'],
      ['ltoken', 'ltoken_v2'],
      ['account_id', 'account_id_v2', 'ltuid', 'ltuid_v2']
    ],
    runtimeFormatter(cookie) {
      return `account:\n  cookie: "${escapeEnv(cookie)}"\n`;
    }
  },
  bilibili: {
    key: 'bilibili',
    label: 'bilibili-auto-sign',
    homeUrls: ['https://www.bilibili.com/'],
    profileDir: process.env.BILIBILI_PROFILE_DIR || path.join(ROOT_STATE_DIR, 'bilibili'),
    runtimePath: process.env.BILIBILI_RUNTIME_PATH || path.join(vendorRoot, 'bilibili-auto-sign', '.env.runtime'),
    staticPath: process.env.BILIBILI_STATIC_PATH || path.join(vendorRoot, 'bilibili-auto-sign', '.env'),
    staticKey: 'BILIBILI_COOKIE',
    importDomains: ['.bilibili.com'],
    exportDomains: ['.bilibili.com'],
    requirements: [['SESSDATA'], ['bili_jct'], ['DedeUserID']],
    runtimeFormatter(cookie) {
      return `BILIBILI_COOKIE="${escapeEnv(cookie)}"\n`;
    }
  }
};

function escapeEnv(value) {
  return String(value).replaceAll('\\', '\\\\').replaceAll('"', '\\"');
}

function normalizeCookieInput(raw) {
  let value = String(raw || '').trim();
  if (value.includes('\n')) {
    value = value.split(/\r?\n/)[0].trim();
  }
  if (value.length >= 2 && value[0] === value[value.length - 1] && ['"', "'"].includes(value[0])) {
    value = value.slice(1, -1);
  }
  return value.trim();
}

function parseCookieString(cookieString) {
  const cookieMap = new Map();
  for (const chunk of String(cookieString || '').split(';')) {
    const part = chunk.trim();
    if (!part) {
      continue;
    }
    const index = part.indexOf('=');
    if (index === -1) {
      continue;
    }
    const key = part.slice(0, index).trim();
    const value = part.slice(index + 1).trim();
    if (!key) {
      continue;
    }
    cookieMap.set(key, value);
  }
  return cookieMap;
}

function cookieMapToString(cookieMap) {
  return [...cookieMap.entries()].map(([key, value]) => `${key}=${value}`).join('; ');
}

function matchesDomain(cookieDomain, exportDomain) {
  const normalizedCookieDomain = String(cookieDomain || '').toLowerCase();
  const normalizedExportDomain = String(exportDomain || '').toLowerCase();
  return (
    normalizedCookieDomain === normalizedExportDomain ||
    normalizedCookieDomain.endsWith(normalizedExportDomain)
  );
}

function missingRequirements(cookieMap, requirements) {
  const missing = [];
  for (const candidates of requirements) {
    if (!candidates.some((name) => cookieMap.has(name))) {
      missing.push(candidates);
    }
  }
  return missing;
}

function cookiesToCookieMap(cookies, exportDomains) {
  const cookieMap = new Map();
  for (const cookie of cookies) {
    if (!exportDomains.some((domain) => matchesDomain(cookie.domain, domain))) {
      continue;
    }
    cookieMap.set(cookie.name, cookie.value);
  }
  return cookieMap;
}

function cookieStringToPlaywrightCookies(cookieString, domains) {
  const cookieMap = parseCookieString(cookieString);
  const cookies = [];
  for (const [name, value] of cookieMap.entries()) {
    for (const domain of domains) {
      cookies.push({
        name,
        value,
        domain,
        path: '/',
        secure: true,
        httpOnly: false,
        sameSite: 'Lax'
      });
    }
  }
  return cookies;
}

async function ensureDirForFile(filePath) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
}

async function readEnvValue(filePath, key) {
  try {
    const text = await fs.readFile(filePath, 'utf8');
    for (const rawLine of text.split(/\r?\n/)) {
      if (!rawLine.startsWith(`${key}=`)) {
        continue;
      }
      return normalizeCookieInput(rawLine.slice(key.length + 1));
    }
  } catch {}
  return '';
}

async function readMihoyoCookie(filePath) {
  try {
    const text = await fs.readFile(filePath, 'utf8');
    let inAccount = false;
    for (const rawLine of text.split(/\r?\n/)) {
      const line = rawLine.replace(/\r$/, '');
      const trimmed = line.trim();
      if (trimmed === 'account:') {
        inAccount = true;
        continue;
      }
      if (inAccount && line && !line.startsWith(' ')) {
        inAccount = false;
      }
      if (inAccount && line.startsWith('  cookie:')) {
        return normalizeCookieInput(line.split(':', 2)[1] || '');
      }
    }
  } catch {}
  return '';
}

async function readStaticCookie(site) {
  if (site.staticKey) {
    return readEnvValue(site.staticPath, site.staticKey);
  }
  if (site.key === 'mihoyo') {
    return readMihoyoCookie(site.staticPath);
  }
  return '';
}

async function writeRuntimeCookie(site, cookieString) {
  await ensureDirForFile(site.runtimePath);
  await fs.writeFile(site.runtimePath, site.runtimeFormatter(cookieString), 'utf8');
}

async function readStdinText() {
  if (process.stdin.isTTY) {
    return '';
  }

  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString('utf8');
}

async function openAndRefresh(site, { mode, seedCookie }) {
  await fs.mkdir(site.profileDir, { recursive: true });

  const context = await firefox.launchPersistentContext(site.profileDir, {
    headless: mode !== 'open',
    viewport: { width: 1280, height: 860 },
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
    colorScheme: 'light'
  });

  let importedCookie = false;

  try {
    let currentCookieMap = cookiesToCookieMap(await context.cookies(), site.exportDomains);
    const beforeMissing = missingRequirements(currentCookieMap, site.requirements);
    const fallbackCookie = normalizeCookieInput(seedCookie || (await readStaticCookie(site)));

    if (beforeMissing.length && fallbackCookie) {
      const cookies = cookieStringToPlaywrightCookies(fallbackCookie, site.importDomains);
      if (cookies.length) {
        await context.addCookies(cookies);
        importedCookie = true;
      }
    }

    const page = context.pages()[0] || (await context.newPage());
    for (const url of site.homeUrls) {
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(() => {});
      await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {});
      await page.waitForTimeout(2500);
    }

    if (mode === 'open') {
      console.log(
        JSON.stringify(
          {
            ok: true,
            mode,
            target: site.key,
            message: '浏览器已打开，请在这个专用会话里手动登录。登录完成后直接关闭浏览器窗口即可自动保存。'
          },
          null,
          2
        )
      );
      await new Promise((resolve) => context.browser().once('disconnected', resolve));
      return null;
    }

    currentCookieMap = cookiesToCookieMap(await context.cookies(), site.exportDomains);
    const missing = missingRequirements(currentCookieMap, site.requirements);
    const cookieString = cookieMapToString(currentCookieMap);

    if (!cookieString || missing.length) {
      throw new Error(
        `missing required cookies: ${missing.map((group) => `[${group.join('|')}]`).join(', ')}`
      );
    }

    await writeRuntimeCookie(site, cookieString);
    return {
      ok: true,
      mode,
      target: site.key,
      importedCookie,
      runtimePath: site.runtimePath,
      profileDir: site.profileDir,
      cookieCount: currentCookieMap.size,
      cookieNames: [...currentCookieMap.keys()].slice(0, 30)
    };
  } finally {
    await context.close().catch(() => {});
  }
}

async function main() {
  const mode = process.argv[2] || '';
  const target = process.argv[3] || '';
  const site = SITES[target];

  if (!site || !['sync', 'seed', 'open'].includes(mode)) {
    console.error('Usage: node browser-cookie-sync.mjs <sync|seed|open> <52pojie|mihoyo|bilibili>');
    process.exitCode = 1;
    return;
  }

  const seedCookie = mode === 'seed' ? normalizeCookieInput(await readStdinText()) : '';
  const result = await openAndRefresh(site, { mode, seedCookie });
  if (result) {
    console.log(JSON.stringify(result, null, 2));
  }
}

main().catch((error) => {
  console.error(
    JSON.stringify(
      {
        ok: false,
        error: error.message
      },
      null,
      2
    )
  );
  process.exitCode = 1;
});
