/**
 * Harness policy. Jev supplies numbers; these plain functions make the decisions.
 * Nothing here calls a model, so every rule is unit-testable (see tests/policy.test.ts).
 */

export type Verdict = "allow" | "checkpoint" | "ask" | "block";

export const GATE = {
	/** Off-branch probability at or above this blocks outright. */
	blockOffBranchAt: 0.5,
	/** Destroy probability at or above this goes to a human (and gets a checkpoint if approved). */
	askDestroyAt: 0.3,
	/** Modify + destroy at or above this, or a low-confidence answer, takes a checkpoint first. */
	checkpointAt: 0.35,
	minConfidence: 0.6,
};

/** The gate. `p` holds Jev's probabilities for read / additive / modify / destroy. */
export function decideGate(p: Record<string, number>, confidence: number, offBranch: number): Verdict {
	const destroy = p.destroy ?? 0;
	const modify = p.modify ?? 0;
	if (offBranch >= GATE.blockOffBranchAt) return "block"; // never touch production or another branch
	if (destroy >= GATE.askDestroyAt) return "ask"; // irreversible: a human decides
	if (modify + destroy >= GATE.checkpointAt || confidence < GATE.minConfidence) return "checkpoint"; // reversible with a branch
	return "allow";
}

export const ROUTER = { powerfulAtComplexity: 0.7, minConfidence: 0.7 };

/** The router. High complexity or an unsure pick escalates; otherwise use Jev's pick. */
export function decideTier(pick: string | undefined, confidence: number, complexity: number): { tier: "fast" | "powerful"; why: string } {
	if (complexity >= ROUTER.powerfulAtComplexity) return { tier: "powerful", why: "complexity high" };
	if (confidence < ROUTER.minConfidence) return { tier: "powerful", why: "low confidence" };
	return { tier: pick === "fast" ? "fast" : "powerful", why: "jev pick" };
}

export const VERIFIER = { maxAttempts: 2, minGrounded: 0.5, minQuality: 0.34, minConfidence: 0.5 };

/**
 * The verifier. Retry once when claims look ungrounded or the work looks unfinished, unless Jev is unsure of its own grade.
 * If the gate held an action for a human who never approved it, stopping was the right outcome: never push the agent past the gate.
 */
export function decideRetry(attempt: number, quality: number, grounded: number, qualityConfidence: number, awaitingHuman = false): boolean {
	if (awaitingHuman) return false;
	if (attempt >= VERIFIER.maxAttempts) return false;
	if (qualityConfidence < VERIFIER.minConfidence) return false;
	return grounded < VERIFIER.minGrounded || quality < VERIFIER.minQuality;
}

/**
 * Hard rules: anything code can check for certain is checked in code, before any model is asked.
 * Blocks the Neon control plane, the neon CLI, and any mention of a protected id (production branch, endpoint).
 */
export function hardRule(text: string, protectedIds: string[]): string | undefined {
	if (/console\.neon\.tech|\bneonctl\b|(^|[\s;&|(])neon\s+[a-z]/i.test(text)) return "neon control plane or CLI";
	const hit = protectedIds.find((x) => x && text.includes(x));
	if (hit) return `protected id ${hit}`;
	return undefined;
}
