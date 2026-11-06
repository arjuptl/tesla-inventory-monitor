# Public inventory UI monitor

A deterministic Python + Playwright monitor for Tesla Model Y **new inventory**, using ordinary visible public UI controls. GitHub Actions runs are manual one-shots. No LLM at runtime. Email is disabled; this package has no notification stack.

**Not cloud-verified against Tesla.** No Tesla network access was used to develop or test this package. Public UI selectors and eligibility wording are conservative assumptions, so UI changes or unsupported layouts return `UI_UNVERIFIED` or `TIMEOUT`. Datacenter IPs may receive a 403/challenge. The monitor stops and latches; it does not bypass challenges or retry a blocked run.

## Configuration and one-shot

Use Python 3.12. Install `requirements.txt`, then run `playwright install --with-deps chromium` on Linux. The Playwright [browser context documentation](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context) describes the isolated profile API used here.

Copy `config.example.json` to a private location **outside this repository**, replace the fictional placeholders locally, and set the repository secret:

```sh
gh secret set WATCH_CONFIG_JSON < /secure/location/private.json
```

The exact configuration shape is shown in `config.example.json`: both `watches` and `email` are required, every watch field is required, unknown fields are rejected, IDs must be unique, and email must remain disabled. ZIP values must be five ASCII digits. `00000` and `99999` are fictional test placeholders. The only supported trims are `MY_PR_RWD` and `MY_PR_AWD`, with matching drivetrain preferences; payment is `Cash`, condition is `new`, and search radius is `All Deliverable`.

Select **Actions → Inventory one-shot → Run workflow**. There is no cron. Do not add scheduling until a successful one-shot smoke has been manually reviewed.

For a local run with the environment secret already set:

```sh
python -m inventory_monitor.runner
```

Configuration is read only from `WATCH_CONFIG_JSON`; no config-file CLI or fallback private files are loaded. Each watch gets a fresh temporary Chromium profile, deleted when closed. Watches run serially. The browser navigates to the base inventory URL, enters the ZIP in the visible location dialog, selects and verifies New/Cash/trim controls, then waits for stable cards or an explicit empty message. Block detection takes priority over an empty message. Only visible full 17-character VIN tokens are captured; order IDs never become VINs. Demo cards are excluded.

Candidate details require an explicit positive registration eligibility statement naming the configured ZIP. Negative or uncertain eligibility yields no match. Detail checks are capped at 20 candidates per watch and ten seconds of eligibility waiting per detail; `CANDIDATE_LIMIT` signals incomplete coverage. This package does not claim exhaustive inventory coverage or validate VIN check digits. Prices and mileage are display strings, not financial calculations.

## Privacy and failure behavior

Never commit real configuration. Workflow logs are public: the runner emits only generic watch labels, status enums, counts, a boolean, and a fixed note. It suppresses browser/library stdout and stderr, never prints raw exceptions, and includes a tested redaction helper for any future diagnostic logging. Do not enable verbose/debug/trace logging or echo the environment secret in workflows.

Detailed matches and dedupe hashes are written only under `RUN_PRIVATE_DIR` (default `/tmp/inventory-monitor-private`), with owner-only permissions. The runner rejects output inside the repository. Never upload this directory as an artifact, commit it, or expose it through logs. No screenshots, HARs, email files, or browser storage are retained. Profiles live under the OS temporary directory and are disposable. No artifacts are uploaded by the workflow.

Statuses are `LOADED_EMPTY`, `LOADED_WITH_CARDS`, `BLOCKED`, `BLOCKED_LATCHED`, `TIMEOUT`, `UI_UNVERIFIED`, `CANDIDATE_LIMIT`, and `ERROR`. A non-success status produces a nonzero CLI exit. Card count includes visible demo/nonmatching cards; match count includes only eligible non-demo cards of the requested trim. `LOADED_WITH_CARDS` with zero matches does not assert zero stock or verified negative eligibility.

A challenge writes `blocked.json` into the private directory and stops remaining watches. Subsequent runs using that directory do not visit the site until an operator deliberately runs `python -m inventory_monitor.runner --resume-blocked`. GitHub-hosted runners are ephemeral: that local latch cannot survive a new hosted job, so another manually dispatched job is an explicit fresh attempt. There is no automatic retry loop. Durable cross-run state for scheduled jobs is out of scope. Dedupe events are `existing_match` for newly seen stable VINs or detail links; they are private and do not change match counts.

## Offline tests and sanitization

Create a virtual environment outside the repository, install `requirements-dev.txt`, and run `PYTHONDONTWRITEBYTECODE=1 python -m pytest` from this directory. Tests use fictional HTML and mocks only; they never contact Tesla. Run `python scripts/sanitize.py` before publication. Its denylist is supplied as encoded fingerprints so this repository does not embed prohibited private identifiers. It scans all bytes and paths, rejects symlinks, generated caches, unexpected files, contact email addresses, and non-placeholder ZIP literals. It is a defense against known leaks, not proof that arbitrary free text contains no personal information. This repository was authored from scratch without reading private configuration.

`MANIFEST.md` records file sizes and local verification results. No repository initialization or publication is performed by this package.
