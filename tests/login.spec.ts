import { test, expect } from '@playwright/test';

// This app requires auth for everything past the login screen, and the
// backend (Supabase/Anthropic/OpenAI) isn't available in CI — so this
// only verifies the one screen that renders without a live API: the
// signed-out login gate (see client/src/App.jsx, client/src/components/Login.jsx).

test('shows the Williams sign-in gate when signed out', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('EphRead')).toBeVisible();
  await expect(page.getByRole('button', { name: /Sign in with Google/i })).toBeVisible();
  await expect(page.getByText(/@williams\.edu/i).first()).toBeVisible();
});
