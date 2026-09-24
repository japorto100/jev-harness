// Screenshot the Jev Harness Lab dashboard at 1600x1000 @2x.
//   node capture.mjs live      loop: every 20 s, capture every run that is still running (until the queue is done)
//   node capture.mjs final     capture every finished run (Run tab, full page + "hide reads"), plus the Results, Gate lab and Neon tabs
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const BASE = process.env.JEV_LAB_URL ?? "http://localhost:8918";
const OUT = join(dirname(dirname(fileURLToPath(import.meta.url))), "results", "screens");
const mode = process.argv[2] ?? "final";
const stamp = () => new Date().toISOString().slice(11, 19).replace(/:/g, "");

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 2 });
const runs = async () => (await (await fetch(BASE + "/api/runs")).json());

async function shot(run, file, { full = false, writesOnly = false, tab = "run" } = {}) {
	await page.goto(`${BASE}/?run=${encodeURIComponent(run ?? "")}&tab=${tab}`, { waitUntil: "networkidle" });
	await page.waitForTimeout(900);
	if (writesOnly) { await page.check("#wonly"); await page.waitForTimeout(400); }
	await page.screenshot({ path: file, fullPage: full });
}

if (mode === "live") {
	mkdirSync(`${OUT}/live`, { recursive: true });
	let idle = 0;
	for (;;) {
		const rs = await runs();
		for (const r of rs.filter((x) => x.status === "running")) {
			await shot(r.id, `${OUT}/live/${r.name}-${stamp()}.png`);
		}
		idle = rs.some((x) => x.status === "running") ? 0 : idle + 1;
		if (idle >= 30) break; // nothing running for ~10 minutes: the queue is done
		await new Promise((res) => setTimeout(res, 20000));
	}
} else {
	mkdirSync(`${OUT}/final`, { recursive: true });
	mkdirSync(`${OUT}/tabs`, { recursive: true });
	for (const r of (await runs()).filter((x) => x.status !== "running")) {
		await shot(r.id, `${OUT}/final/${r.name}.png`);
		await shot(r.id, `${OUT}/final/${r.name}-writes-full.png`, { full: true, writesOnly: true });
	}
	for (const tab of ["results", "gatelab", "neon"]) await shot(null, `${OUT}/tabs/${tab}.png`, { full: true, tab });
}
await browser.close();
