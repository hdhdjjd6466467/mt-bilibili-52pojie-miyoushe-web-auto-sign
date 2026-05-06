import process from 'node:process';

import {
  ensureDirs,
  getCookieString,
  importCookieString,
  isLoggedIn,
  keepBrowserOpenIfNeeded,
  launchBrowser,
  saveArtifacts
} from './common.mjs';

async function main() {
  await ensureDirs();

  const cookieString = getCookieString();
  if (!cookieString) {
    throw new Error('Missing POJIE_COOKIE. Paste your browser cookie into the environment first.');
  }

  const { browser, context, page } = await launchBrowser();
  try {
    await importCookieString(context, cookieString);
    const loginState = await isLoggedIn(page);
    const artifacts = await saveArtifacts(page, 'cookie-import');

    console.log(
      JSON.stringify(
        {
          ok: loginState.loggedIn,
          usernameText: loginState.usernameText,
          pageTitle: loginState.pageTitle,
          artifacts
        },
        null,
        2
      )
    );
    await keepBrowserOpenIfNeeded(page);
  } finally {
    await browser.close();
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
