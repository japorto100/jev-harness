# HERKUNFT / Provenienz

- **Upstream:** https://github.com/PromtEngineer/jev-harness (Default-Branch `main`)
- **Fork (dieses Submodul):** https://github.com/japorto100/jev-harness — angelegt **29.09.2026**
- **Pin in harness_test:** Submodul-Pointer auf den Fork-Commit mit dieser Notiz (Basis `9bd4f670`, main) — keine Vendor-Kopie.
- **Was es ist:** Agent-Harness um ein „System-One"-Modell (TypeSafe Jev): Pi-Agent-Loop + Gemini;
  Jev beantwortet typisierte Fragen (noul/choice/score) an vier Punkten (Router, Context-Picker, Gate,
  Verifier); Arbeit auf echtem Postgres, pro Run ein Neon-Branch; enthält Harness, Benchmark, Dashboard
  und Ergebnisse (Details im README dieses Repos).
- **Warum hier:** JEV-/Pi-Umfeld des Labs; eigenständig versioniert und gepflegt, nicht in den Harness
  kopiert (HARNESS-Regel: Fremdcode nur commit-gepinnt + Herkunft).
- **Transkript:** [`YOUTUBE-TRANSCRIPT.md`](YOUTUBE-TRANSCRIPT.md) — **verbatim** ASR-Transkript des
  Hersteller-Videos (Motivation, vier Entscheidungspunkte, Benchmark/Traps, Ergebnisse, Design-Flaws).
- **Updates:** im Harness `git submodule update --remote JEV_Prompt_engineer`, danach den Pointer committen.
  Eigene Anpassungen **im Fork** committen und pushen — kein Upstream-Push ohne Owner-Entscheid.
