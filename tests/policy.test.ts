// Run: node --experimental-strip-types --test tests/
import { test } from "node:test";
import assert from "node:assert/strict";
import { decideGate, decideRetry, decideTier, hardRule } from "../extension/policy.ts";

const p = (read: number, additive: number, modify: number, destroy: number) => ({ read, additive, modify, destroy });

test("gate: reads and additive changes run", () => {
	assert.equal(decideGate(p(1, 0, 0, 0), 1, 0.02), "allow");
	assert.equal(decideGate(p(0, 1, 0, 0), 1, 0.03), "allow"); // CREATE INDEX
});

test("gate: targeted modify gets a checkpoint first", () => {
	assert.equal(decideGate(p(0, 0, 1, 0), 1, 0.03), "checkpoint");
});

test("gate: an unsure answer gets a checkpoint", () => {
	assert.equal(decideGate(p(0.7, 0, 0.19, 0.11), 0.59, 0.02), "checkpoint");
});

test("gate: destroy goes to a human", () => {
	assert.equal(decideGate(p(0, 0, 0, 1), 1, 0.03), "ask"); // DROP COLUMN
	assert.equal(decideGate(p(0.6, 0, 0.1, 0.3), 0.6, 0.0), "ask");
});

test("gate: anything aimed at another branch is blocked, even a read", () => {
	assert.equal(decideGate(p(1, 0, 0, 0), 1, 0.9), "block");
});

test("router: complexity and confidence escalate", () => {
	assert.deepEqual(decideTier("fast", 1.0, 0.25), { tier: "fast", why: "jev pick" });
	assert.equal(decideTier("fast", 1.0, 0.72).tier, "powerful");
	assert.deepEqual(decideTier("powerful", 0.44, 0.2), { tier: "powerful", why: "low confidence" });
});

test("verifier: at most one retry, and no retry on an unsure grade", () => {
	assert.equal(decideRetry(1, 0.9, 0.2, 0.9), true);
	assert.equal(decideRetry(2, 0.9, 0.2, 0.9), false);
	assert.equal(decideRetry(1, 0.2, 0.9, 0.3), false);
	assert.equal(decideRetry(1, 0.99, 0.87, 0.96), false);
});

test("verifier: never pushes the agent past a gate that is waiting for a human", () => {
	assert.equal(decideRetry(1, 0.01, 0.83, 0.98, true), false);
	assert.equal(decideRetry(1, 0.01, 0.83, 0.98, false), true);
});

test("hard rules: control plane, CLI, and protected ids", () => {
	const ids = ["br-prod-123", "ep-prod-456"];
	assert.ok(hardRule("curl -s https://console.neon.tech/api/v2/projects", ids));
	assert.ok(hardRule("neon branches list", ids));
	assert.ok(hardRule("cd /tmp && neon roles reset-password", ids));
	assert.ok(hardRule('psql "postgresql://u:p@ep-prod-456.aws.neon.tech/db"', ids));
	assert.equal(hardRule('psql "$BRANCH_URL" -c "select 1"', ids), undefined);
	assert.equal(hardRule("SELECT * FROM neon_stats", ids), undefined);
});
