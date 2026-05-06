import {
  ensureDirs,
  findRelevantLinks,
  getCredentials,
  isLoggedIn,
  keepBrowserOpenIfNeeded,
  launchBrowser,
  loadStorageStateIfExists,
  paths,
  performLogin,
  saveArtifacts,
  saveStorageState,
  urls
} from './common.mjs';

async function main() {
  await ensureDirs();

  const credentials = await getCredentials({ allowStdin: true });
  const storageState = await loadStorageStateIfExists();
  const { browser, context, page } = await launchBrowser({ storageState });

  try {
    let loginState = await isLoggedIn(page);

    if (!loginState.loggedIn) {
      loginState = await performLogin(page, credentials);
      await saveArtifacts(page, 'post-login');

      if (!loginState.loggedIn) {
        console.log(
          JSON.stringify(
            {
              ok: false,
              step: 'login',
              url: loginState.url,
              pageTitle: loginState.pageTitle,
              captchaInfo: loginState.captchaInfo,
              quickResult: loginState.quickResult,
              usernameText: loginState.usernameText,
              storageStatePath: paths.storageState,
              bodyText: loginState.bodyText
            },
            null,
            2
          )
        );
        return;
      }

      await saveStorageState(context);
    }

    await page.goto(urls.taskList, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(3000);

    const links = await findRelevantLinks(page);
    const artifacts = await saveArtifacts(page, 'task-list');

    console.log(
      JSON.stringify(
        {
          ok: true,
          step: 'inspect',
          pageTitle: await page.title(),
          url: page.url(),
          usernameText: loginState.usernameText,
          storageStatePath: paths.storageState,
          artifacts,
          links
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
        error: error.message,
        stack: error.stack
      },
      null,
      2
    )
  );
  process.exitCode = 1;
});
