import {test, expect} from '@playwright/test';

test('web keeps Noto font and imports CSV and XLSX', async ({page}) => {
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.goto('/');
  await expect(page.getByRole('button', {name:'Text', exact:true})).toBeVisible({timeout:120000});
  await page.getByRole('button', {name:'Text', exact:true}).click();
  await expect(page.getByText('Noto Sans CJK TC', {exact:true})).toBeVisible();
  await expect(page.getByRole('button', {name:'Choose font…'})).toHaveCount(0);
  await page.getByRole('tab', {name:'Data', exact:true}).click();
  await page.getByRole('button', {name:'Import XLSX/CSV', exact:true}).click();
  await page.locator('dialog input[type=file]').first().setInputFiles({name:'rows.csv', mimeType:'text/csv', buffer:Buffer.from('SN\nCSV 001\n')});
  await expect(page.getByRole('cell', {name:'CSV 001', exact:true})).toBeVisible();
  await page.getByRole('button', {name:'Import XLSX/CSV', exact:true}).click();
  await page.locator('dialog input[type=file]').first().setInputFiles('tests/fixtures/data.xlsx');
  await expect(page.getByRole('cell', {name:'XLSX 001', exact:true})).toBeVisible();
  await expect(page.getByRole('cell', {name:'CSV 001', exact:true})).toHaveCount(0);
  expect(errors).toEqual([]);
});
