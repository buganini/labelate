import {defineConfig} from '@playwright/test';
export default defineConfig({
  testDir: './tests/browser',
  timeout: 180000,
  expect: {timeout: 20000},
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:8868',
    viewport: {width: 1440, height: 1000},
    headless: true,
    actionTimeout: 20000,
    launchOptions: {executablePath: process.env.CHROME_PATH || undefined},
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure'
  },
  webServer: {
    command: 'python3 -m http.server 8868 --bind 127.0.0.1 --directory dist/pyodide',
    url: 'http://127.0.0.1:8868',
    reuseExistingServer: !process.env.CI
  }
});
