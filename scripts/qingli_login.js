/**
 * 青梨AI 扫码登录脚本
 * 用法: node qingli_login.js
 * 
 * 弹出浏览器窗口，微信扫码登录后自动保存登录态到 qingli_auth.json
 */
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const AUTH_FILE = path.join(process.cwd(), 'qingli_auth.json');
const QINGLI_URL = 'https://qingli.newacademic.net/';

async function getPageSnapshot(page) {
  return await page.evaluate(() => ({
    url: location.href,
    hasLoginForm: !!document.querySelector('input[placeholder*="账号"], input[placeholder*="密码"], input[type="password"]'),
    hasQRCode: !!document.querySelector('canvas, .qrcode, img[src*="qr"]') || document.body.innerText.includes('扫码登录'),
    hasSearchInput: !!document.querySelector('input[placeholder*="DOI"], input[placeholder*="搜索"], input[placeholder*="查询"]'),
    inputCount: document.querySelectorAll('input').length,
    buttonTexts: Array.from(document.querySelectorAll('button')).map(b => b.innerText.trim()).filter(t => t),
    navItems: Array.from(document.querySelectorAll('nav a, .nav-item, .menu-item')).map(n => n.innerText.trim()).filter(t => t),
  }));
}

(async () => {
  console.log('启动浏览器...');
  const browser = await chromium.launch({
    headless: false,
    args: ['--start-maximized']
  });

  const context = await browser.newContext({
    viewport: { width: 1400, height: 900 }
  });
  const page = await context.newPage();

  console.log('打开青梨AI...');
  await page.goto(QINGLI_URL, { waitUntil: 'networkidle', timeout: 30000 });

  const initial = await getPageSnapshot(page);
  console.log('');
  console.log('=== 扫码登录 ===');
  console.log('  请在弹出的浏览器窗口中，用微信扫码登录');
  console.log('  登录成功后脚本会自动检测并保存');
  console.log('  最长等待 5 分钟');
  console.log('');

  // Poll every 3 seconds for up to 5 minutes
  const startTime = Date.now();
  const maxWait = 5 * 60 * 1000;
  let loggedIn = false;

  while (Date.now() - startTime < maxWait) {
    await page.waitForTimeout(3000);
    const current = await getPageSnapshot(page);

    // Login form disappeared AND search input appeared → logged in
    if (!current.hasLoginForm && current.hasSearchInput) {
      console.log('检测到搜索输入框，登录成功！');
      loggedIn = true;
      break;
    }

    // QR code disappeared AND nav items appeared → logged in
    if (!current.hasQRCode && current.navItems.length > 0) {
      console.log('检测到导航菜单，登录成功！');
      loggedIn = true;
      break;
    }

    // URL contains /home or /search → logged in
    if (current.url.includes('/home') || current.url.includes('/search')) {
      console.log('页面跳转到主页，登录成功！');
      loggedIn = true;
      break;
    }
  }

  if (loggedIn) {
    await page.waitForTimeout(3000);
    await context.storageState({ path: AUTH_FILE });
    console.log(`\n登录态已保存: ${AUTH_FILE}`);
  } else {
    console.log('\n等待超时，未检测到登录成功');
  }

  await browser.close();
  console.log(loggedIn ? '完成！' : '未登录，请重试。');
  process.exit(loggedIn ? 0 : 1);
})();
