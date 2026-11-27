# Version deployment, traffic migration, and rollback

> **Chapter:** App Engine  
> **Module:** CLOUD_PROVIDERS_GCP

A Java service on **Google App Engine** is serving customers steadily on version `v1`. The development team is preparing to release `v2` with new features but does not yet know its real-world performance under production traffic. Running `gcloud app deploy` with default settings typically **promotes the new version to receive 100% of traffic immediately**, increasing the risk of a widespread faulty release. Instead, we will deploy **without promoting**, test the new version directly, shift a fraction of traffic, monitor metrics, and then cut over completely—or **roll back** to the old version if problems arise.

This lesson belongs to the **App Engine** chapter of the **CLOUD_PROVIDERS_GCP** module, where learners progress across Google Cloud from projects/IAM, VPC, Compute Engine, GKE, and Cloud Run to storage, databases, deployment, reliability, and cost. The primary example uses **App Engine Standard, Java 21**, while also highlighting key differences when operating **App Engine Flexible**.

**After this lesson, you can:**

1. Distinguish **application, service, version, instance**, and *traffic allocation*.
2. Deploy a version **not yet receiving traffic** using `--version` and `--no-promote`.
3. Test via a **version-specific URL** without altering service traffic.
4. Configure **traffic splitting** by IP, cookie, or random and understand the limitations of each.
5. Distinguish **traffic migration** to a single version from a **multi-stage canary rollout**.
6. Roll back quickly to a prior version without assuming rollback restores databases or secrets.
7. Inspect per-version logs/metrics, handle cold starts, sticky sessions, caching, and manage costs of old versions.

## 1. The App Engine model to remember

An App Engine application consists of one or more **services**; each service has multiple **versions**; each version runs on **instances** managed by the platform according to environment type and scaling configuration.

~~~mermaid
flowchart TB
  APP["App Engine application\nProject: demo-prod"] --> S1["Service: default\norders-api"]
  APP --> S2["Service: worker"]
  S1 --> V1["Version: v20261101a\n95% traffic"]
  S1 --> V2["Version: v20261119a\n5% traffic"]
  V1 --> I1["Instances v1"]
  V2 --> I2["Instances v2"]
  S2 --> VW["Separate worker version"]
~~~

| Concept | Example | Meaning |
| --- | --- | --- |
| **Application** | Project's App Engine app | App-level location and services; creating the application is a separate operation |
| **Service** | `default`, `payments`, `worker` | A serving unit with independent versions and traffic splits |
| **Version** | `v20261119a` | Snapshot of code + runtime + deployment configuration at deploy time |
| **Instance** | Process/VM running a version | Created/destroyed via automatic, basic, or manual scaling |
| **Traffic allocation** | `v1=0.95, v2=0.05` | **Service-level** routing ratio for requests not targeting a specific version |
| **Version-specific URL** | `VERSION-dot-SERVICE-dot-PROJECT.REGION_ID.r.appspot.com` | Accesses a specific version directly for smoke testing |
| **Rollback** | Shift traffic back to `v1` | Reverts **routing/version**; does not reverse external data changes |

A service can have multiple versions existing simultaneously. **Creating a version does not update every instance of the old version in place**: the new version is a separate deployment. This enables fast canaries and rollbacks **as long as the previous good version remains available**.

### 1.1. What changes during deployment

When running `gcloud app deploy`, App Engine uploads source/artifacts, builds if needed, creates or replaces the specified version, and adjusts routing according to the `promote` flag.

- Without `--version`: the CLI typically generates a **unique version ID**.
- With `--version=v20261119a`: assigns that version name to the build.
- Without `--no-promote`: deploy **promotes by default** so the new version receives 100% of traffic.
- With `--no-promote`: creates the new version **while preserving the current traffic split**.

**Critical warning:** If you **deploy over an existing version ID**, App Engine may replace the old version and **shift traffic immediately**, causing you to lose the previous version for rollback. Every release should therefore use an **unused version ID**; never redeploy with the same name to “hotfix” a release.

### 1.2. Where does Standard differ from Flexible?

| Topic | App Engine Standard | App Engine Flexible |
| --- | --- | --- |
| Runtime | Managed runtimes, e.g., Java 21 | More flexible container/VM environment |
| Scaling/cost model | Depends on automatic/basic/manual scaling and instance class | Uses VM resources; old versions can still incur costs when receiving no traffic |
| Deployment | `gcloud app deploy`, `--no-promote` | Same family of deploy/traffic commands |
| Traffic splitting | Supports splitting traffic across versions | Supports splitting traffic across versions |
| **Gradual traffic migration with warmup** | Available when supported and properly configured | **Gradual migration between Flexible versions is not supported** per App Engine docs |
| Cold start/readiness | Consider warmup and instance availability | VM/container startup can take longer; monitor readiness |
| Rollback | Shift traffic back to old version | Shift traffic back to old version; ensure old version has capacity |

**Do not confuse** gradual migration with a manual canary. In Flexible, you can still **manually split traffic** in steps like 5% → 25% → 50% → 100%; that is distinct from Standard's automatic gradual migration mechanism.

## 2. Safe release plan

Assume the `default` service currently runs `v20261101a` at **100%**. The new release is `v20261119a`. Goal:

~~~text
T0: v20261101a=100%   v20261119a=0%
    ↓ Deploy new version with --no-promote
T1: Smoke-test new version URL, inspect logs and dependencies
    ↓ Confirmed?
T2: v20261101a=95%    v20261119a=5%
    ↓ Observe errors/p95/DB and canary cohort
T3: v20261101a=75%    v20261119a=25%
    ↓ Observe
T4: v20261101a=0%     v20261119a=100%
    ↓ Continue monitoring
T5: Keep old version for rollback within defined window
~~~

**Note:** Specific observation durations and percentages are illustrative. Under low traffic, a 5% canary may lack enough requests to surface rare bugs; for critical services, design statistically meaningful gates aligned with SLOs and risk.

### 2.1. Pre-rollout prerequisites

- App Engine application/service already exists in the right project and location; the first deployment must create the **default service** before other services.
- Deployer holds appropriate IAM permissions for App Engine/Cloud Build and permission to use the runtime service account if needed.
- Build passed unit/integration/security tests; artifact and source revision are recorded.
- Version ID is **new** and does not collide with any serving version.
- DB schemas and API contracts are **compatible** between v1 and v2 while running concurrently.
- Connectivity to Cloud SQL, Secret Manager, Pub/Sub, or other resources has been verified.
- Dashboards track request count, HTTP 5xx, p95 latency, error logs, and resource usage **per version**.
- Old version still exists, a rollback playbook has an assigned owner, and budget covers running versions in parallel.
- Clear authority to halt the rollout, defined observation windows, and explicit go/no-go criteria are established.

### 2.2. Decision flowchart

~~~mermaid
flowchart TD
  DEP["Deploy v2 --no-promote"] --> SMOKE{"Does v2 smoke test pass?"}
  SMOKE -- "No" --> FIX["Keep v1 at 100%\nFix build, deploy new version"]
  SMOKE -- "Yes" --> CAN["Canary v2 at 5%"]
  CAN --> SLO{"5xx, p95, DB, errors healthy?"}
  SLO -- "No" --> BACK["Rollback: v1=100%"]
  SLO -- "Yes" --> RAMP["25% → 50% → 100%"]
  RAMP --> CHECK{"SLOs still met?"}
  CHECK -- "No" --> BACK
  CHECK -- "Yes" --> HOLD["Monitor, keep v1 during rollback window"]
~~~

## 3. Java Standard example: app.yaml and health/version endpoints

This lesson does not deploy a full application; assume you have a **Spring Boot Java 21** project configured to build an **executable JAR** that runs on App Engine Standard.

Minimal `app.yaml` for the `default` service:

~~~yaml
runtime: java21
service: default

automatic_scaling:
  min_instances: 0
  max_instances: 5

env_variables:
  APP_ENV: lab
~~~

The App Engine Standard Java runtime provides `PORT`, `GAE_SERVICE`, and `GAE_VERSION`. The application must listen on the **port provided by the environment**, never hard-code a fixed port:

~~~yaml
# Example Spring Boot application.yaml config (distinct from App Engine's app.yaml)
server:
  port: ${PORT:8080}
~~~

Create illustrative endpoints for release verification:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import java.util.Map;

@RestController
public class ReleaseInfoController {
    @GetMapping("/healthz")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @GetMapping("/release")
    public Map<String, String> release() {
        return Map.of(
            "service", System.getenv().getOrDefault("GAE_SERVICE", "local"),
            "version", System.getenv().getOrDefault("GAE_VERSION", "local")
        );
    }
}
~~~

**Example limitations:** `/healthz` returns OK if the web request is handled; it does not check databases, dependencies, or business logic. Production apps need dedicated readiness metrics, authentication on sensitive endpoints, and must never expose secrets in responses.

For Spring Boot Java 21, packaging and config file paths vary by Maven/Gradle/plugins. Refer to App Engine Java documentation to configure the right entrypoint/JAR. The examples below **assume `app.yaml` accompanies valid, locally tested source/artifacts**.

## 4. Deploying a new version without receiving traffic

### 4.1. Check context before taking action

~~~bash
# Read-only commands; ensure you are targeting the RIGHT project
gcloud config get-value project
gcloud app describe --project=LAB_PROJECT_ID
gcloud app services list --project=LAB_PROJECT_ID

gcloud app versions list \
  --service=default \
  --project=LAB_PROJECT_ID
~~~

If no App Engine application exists, **do not run `gcloud app create` casually**: the location chosen at initialization cannot be moved easily and creating an application has long-term project consequences.

### 4.2. Safe deploy command

~~~bash
# MODIFIES CLOUD RESOURCES: run only on an approved lab project
gcloud app deploy app.yaml \
  --project=LAB_PROJECT_ID \
  --version=v20261119a \
  --no-promote
~~~

Inspect the version:

~~~bash
gcloud app versions list \
  --service=default \
  --project=LAB_PROJECT_ID

gcloud app versions describe v20261119a \
  --service=default \
  --project=LAB_PROJECT_ID
~~~

**Expected:** Version `v20261119a` appears with **0% traffic**, while `v20261101a` retains **100%**. If this is the very first version of a service, initial routing behaves differently; this lesson assumes **the service already has a prior stable version**.

### 4.3. Testing via the version-specific URL

App Engine URLs after February 2020 typically follow this structure:

~~~text
# Default service:
https://VERSION-dot-default-dot-PROJECT_ID.REGION_ID.r.appspot.com

# Named service:
https://VERSION-dot-SERVICE-dot-PROJECT_ID.REGION_ID.r.appspot.com

# REGION_ID is an App Engine-assigned code; do not substitute a region name like asia-southeast1.
~~~

You can use gcloud to get the version URL without manually building hostnames:

~~~bash
gcloud app versions browse v20261119a \
  --service=default \
  --project=LAB_PROJECT_ID \
  --no-launch-browser
~~~

From an authorized client, verify `/healthz`, `/release`, read-only database/mock endpoints, logs, startup, and dependencies:

~~~bash
# Replace with the real URL and call only non-sensitive endpoints
curl -i "https://VERSION-dot-default-dot-PROJECT_ID.REGION_ID.r.appspot.com/healthz"
curl -i "https://VERSION-dot-default-dot-PROJECT_ID.REGION_ID.r.appspot.com/release"
~~~

**Security warning:** Version-specific URLs **bypass traffic splits**; even a 0% version can be called directly if ingress/auth allow it. It is **not a private test sandbox**. Use IAM/IAP/ingress or appropriate protections, never embed secrets, and never expose public debug endpoints just for smoke testing.

### 4.4. Why never deploy over an old version name?

Suppose production runs `v20261101a`, and CI deploys new code under **the same ID**. Google Cloud warns that reusing a version ID can **replace the old version**, shift traffic immediately, and make it impossible to revert to the previous binary. CI policies should:

- Assign a **unique ID** per build/run, e.g. `v20261119a`, `v20261119b`.
- Record **source commit + build ID + version ID + deployment timestamp + approval**.
- Fail the pipeline if the target version ID already exists.
- Roll back by **routing to a retained version**, never by rebuilding and overwriting an old name.

## 5. Traffic splitting: splitting ratios, not splitting instances

Traffic splitting sets **weights across versions within one service**. Example:

~~~bash
# Affects service request routing; run in lab only
gcloud app services set-traffic default \
  --splits=v20261101a=0.95,v20261119a=0.05 \
  --split-by=cookie \
  --project=LAB_PROJECT_ID
~~~

Syntax is `--splits=VERSION=WEIGHT,...`; weights are normalized proportionally, e.g., `v1=1,v2=1` equals 50/50. The command replaces **the entire traffic split of the service** for the listed versions rather than adding 5% to existing settings.

### 5.1. Choosing a traffic-splitting algorithm

| CLI value | How version is chosen | Best for | Limitations |
| --- | --- | --- | --- |
| `ip` | Hashes source IP address | Simple, cookie-less splitting | NAT/proxies share IPs across many users; distribution may skew |
| `cookie` | `GOOGAPPUID` cookie hashes into 1,000 buckets | Sticky user experience, A/B tests | Clients must retain cookies; caching and internal cookies need care |
| `random` | Randomly samples per request by weight | Stateless requests, approaches ratio at high volume | Same user may see multiple versions; not sticky |

Per traffic-splitting docs, **IP split** can be inaccurate for small canary percentages or callers behind a shared NAT. **Cookie split** uses the `GOOGAPPUID` cookie to stabilize routing; mobile apps or HTTP clients must store/forward the cookie for stickiness. **Random** is available in `gcloud app services set-traffic`; weigh risks for multi-request sessions/workflows.

~~~mermaid
flowchart LR
  USER["1000 requests / users"] --> SPLIT{"Traffic split\nv1=95%, v2=5%"}
  SPLIT -->|"By IP / cookie / random"| A["v1: approx. 950"]
  SPLIT -->|"By IP / cookie / random"| B["v2: approx. 50"]
  B --> METRIC["Compare 5xx, p95, saturation\nagainst v1 and baseline"]
~~~

**Actual ratios do not always match configured ratios** in short windows; cookies/IPs group users, and request counts or caching can skew samples.

### 5.2. Only requests not targeting a version undergo traffic splitting

- **Service** URLs (without a version) are routed according to traffic allocation.
- **Version-specific** URLs go straight to that version, ignoring service split ratios.
- Callers targeting a version directly (tasks/cron/internal clients, depending on setup) may continue hitting the old version after migration.
- Routing via `dispatch.yaml`, custom domains, or external load balancers follows separate rules; always inspect **the real request path**.

Therefore, **0% traffic does not mean a version receives zero requests**. Before deleting an old version, check version URLs, cron/tasks, and internal dependencies.

### 5.3. Cookie splitting and cache/session handling

If v1 returns HTML referencing unversioned CSS/JS filenames, browsers/CDNs might cache v1 assets and serve them to v2, breaking the UI. Mitigations:

1. Use **hashed filenames** for static assets to keep both versions compatible.
2. Never store critical sessions solely in instance RAM; use shared session storage when needed.
3. Handle the `GOOGAPPUID` cookie properly; clients must preserve cookies across requests.
4. For HTTP caches, evaluate `Vary: Cookie` and its cache-hit impact; do not enable it blindly for every response.
5. Verify critical routes and multi-step workflows on both v1 and v2.

## 6. Multi-stage canary rollout

After smoke testing, ramp percentages step by step **with approvals/guardrails**:

~~~bash
# Step 1: 5% canary for the new version
gcloud app services set-traffic default \
  --splits=v20261101a=0.95,v20261119a=0.05 \
  --split-by=cookie \
  --project=LAB_PROJECT_ID

# Step 2: raise to 25% ONLY if metrics stay healthy
gcloud app services set-traffic default \
  --splits=v20261101a=0.75,v20261119a=0.25 \
  --split-by=cookie \
  --project=LAB_PROJECT_ID

# Step 3: raise to 50% ONLY after review
gcloud app services set-traffic default \
  --splits=v20261101a=0.50,v20261119a=0.50 \
  --split-by=cookie \
  --project=LAB_PROJECT_ID
~~~

**Do not run all three commands back-to-back without observation windows**: these are **three separate release decisions**. At each stage, confirm sufficient canary request volume, no session/account errors, and that the database handles the shift.

### 6.1. Per-stage go/no-go checklist

| Metric group | Comparison rule | When to stop/roll back |
| --- | --- | --- |
| HTTP 5xx | Compare v2 against v1 in the same window/request type | v2 exceeds error budget or approved threshold |
| P95/P99 latency | Compare by route/traffic volume against baseline | Tail latency rises significantly beyond SLO |
| Instance startup | Loading requests, cold starts, scaling behavior | Timeouts/latency increase because v2 lacks capacity |
| DB/cache | SQL errors, connection count, query latency | v2 causes saturation or schema errors |
| Business KPIs | Checkout success, payments, orders | Failed transactions, double processing |
| Security/compatibility | Auth 401/403, secrets, payloads | Access leaks/denials or contract errors |
| Cost | Instance hours, logs, external dependencies | Cost spikes beyond budget or uncontrolled |

**Do not watch only the homepage HTTP status.** A canary can return 200 on `/healthz` yet fail on data writes, schema migrations, async workers, or background tasks.

### 6.2. Verify routing after every step

~~~bash
gcloud app services describe default \
  --project=LAB_PROJECT_ID

gcloud app versions list \
  --service=default \
  --project=LAB_PROJECT_ID

gcloud app logs read \
  --service=default \
  --version=v20261119a \
  --limit=100 \
  --project=LAB_PROJECT_ID
~~~

In the Console, open **App Engine → Versions** to inspect each version's traffic % and **Traffic splitting** links. Do not rely solely on pipeline output: configured routing must match actual traffic seen in metrics.

## 7. Traffic migration: shifting 100% to one version

**Traffic migration** moves request routing for **a service** entirely to **one target version**. It differs from the multi-step canary above: the end state of migration is **100% on the target version**.

### 7.1. Immediate cutover

~~~bash
# CHANGES 100% of routing immediately; may cause a cold-start spike
gcloud app services set-traffic default \
  --splits=v20261119a=1 \
  --project=LAB_PROJECT_ID
~~~

The old version `v20261101a` receives **0% traffic from the regular service URL**, but is not deleted. If the new version lacks ready instances, initial requests may wait for startup.

### 7.2. Gradual migration with warmup in Standard

~~~bash
# App Engine Standard: requests rate/capacity-controlled migration
gcloud app services set-traffic default \
  --splits=v20261119a=1 \
  --migrate \
  --project=LAB_PROJECT_ID
~~~

Per App Engine Standard docs, when warmup requests are supported and enabled, the platform can **gradually shift traffic** to the target version so the autoscaler can create and warm up new instances. For **Java Standard**, warmup is enabled by default; other runtimes may need `inbound_services: [warmup]` depending on runtime generation. Warmup is **best effort** and does not guarantee zero loading requests; always observe real performance.

**Special limitation:** **Gradual traffic migration is not supported between versions running on App Engine Flexible** per current documentation. If using Flexible or switching across environments, plan **manual stepped traffic splits** or immediate migration—do not treat `--migrate` as a guaranteed gradual rollout.

### 7.3. Three easily confused concepts

| Task | Example | Intent |
| --- | --- | --- |
| **Deploy** | `gcloud app deploy --no-promote` | Ship new code/config as a version without changing routing |
| **Split traffic** | `--splits=v1=.9,v2=.1` | Serve percentages of requests across multiple versions concurrently |
| **Migrate traffic** | `--splits=v2=1 --migrate` | Move target to v2, optionally gradually in Standard so autoscaling catches up |

**Do not treat `--migrate` as a canary test with quality gates.** If you need automatic halting at 5% when errors spike, build a separate canary pipeline with metrics checks and gates.

### 7.4. Warmup and limits to understand

- When the new version has no instances yet, an abrupt switch to 100% easily causes response latency spikes.
- App Engine Standard may send `GET /_ah/warmup` to load the app/caches when needed; it is not guaranteed to precede every user request.
- Warmup consumes instance hours and should stay lightweight; never run DB migrations, write orders, or perform non-idempotent actions inside warmup.
- In Flexible, VM/capacity provisioning for both old and new versions must align with Flexible scaling behavior.
- With `--migrate`, monitor migration progress; **never promise an exact completion time**.
- After reaching 100%, retain the prior version long enough for rollback unless policy dictates otherwise.

## 8. Rollback: returning traffic to a known-good version

Rollback is **shifting routing** back to a previously verified version. For example, if canary v2 causes payment failures, revert to v1:

~~~bash
# Production-impacting if run on the wrong project: verify service first
gcloud app services set-traffic default \
  --splits=v20261101a=1 \
  --project=LAB_PROJECT_ID
~~~

**This command does not redeploy code** and does not delete v2. It updates the service's traffic allocation so regular requests route to v1.

### 8.1. Incident rollback runbook

1. **Identify** the project, service, new/stable versions, and current traffic shares.
2. **Decide** to roll back based on error budget, HTTP 5xx, p95, business data, or security alerts.
3. **Shift routing** to the good version using the command above or Console → App Engine → Versions → Migrate traffic.
4. **Verify the traffic split**; check per-version requests and errors rather than stopping at “command exited 0”.
5. **Check active sessions**, direct version-URL calls, cron/queues/background jobs, and caches.
6. **Reconcile** database migrations, secrets, feature flags, and Pub/Sub/Task queues: these systems **do not roll back with code**.
7. **Preserve incident evidence** and fix the fault in the release pipeline; do not delete v2 before root-cause analysis.

### 8.2. Shifting traffic is fast, not a zero-downtime guarantee

- If v1 scaled down to 0, returning traffic can trigger **loading latency**; pre-warm capacity when possible.
- If rollback happens during peak traffic, the old version might temporarily lack connection pools, CPU, or quotas.
- In-flight requests on v2 do not automatically move to v1 when routing changes.
- Callers hitting the v2 URL directly **bypass the traffic split** and can keep using v2.
- If v2 modified the database schema in an **incompatible** way, v1 may crash as soon as it receives traffic.

**Safe rollback ≠ command succeeded.** Verify that business metrics recover and data remains consistent.

### 8.3. Rolling back after deleting the old version?

If `v20261101a` has been deleted, **you cannot route traffic back to it**; you must redeploy the saved artifact/source under a new version ID and re-verify it. Therefore enforce a **retention** policy for approved releases instead of deleting old versions the moment traffic hits 0%.

### 8.4. Schema migration scenario: expand–migrate–contract

Suppose v2 renames column `customer_name` to `buyer_name`. If the migration immediately drops the old column, v1 will break upon rollback. Safe approach:

1. **Expand:** add `buyer_name` while keeping `customer_name`; v1 keeps running.
2. **Migrate:** v2 reads/writes compatibly, backfill data, and observe.
3. **Rollout:** canary v2, then move to 100% once data is consistent.
4. **Contract:** drop the old column **only after** the rollback window closes and no clients use it.

The same applies to message formats and APIs: **preserve backward compatibility while multiple versions run concurrently**.

## 9. Per-version observability and decision thresholds

### 9.1. Read-only gcloud commands

~~~bash
# Query current traffic routing
gcloud app services describe default \
  --project=LAB_PROJECT_ID

# List versions and traffic allocation
gcloud app versions list \
  --service=default \
  --project=LAB_PROJECT_ID

# Inspect metadata/config of one version
gcloud app versions describe v20261119a \
  --service=default \
  --project=LAB_PROJECT_ID

# Read v2 logs, bounded output
gcloud app logs read \
  --service=default \
  --version=v20261119a \
  --limit=100 \
  --project=LAB_PROJECT_ID

# Stream logs continuously (stop when finished)
gcloud app logs tail \
  --service=default \
  --version=v20261119a \
  --project=LAB_PROJECT_ID
~~~

**Never print secrets or tokens into logs.** On App Engine Standard, request logs and application logs can be filtered by service/version; on Flexible, request log sources may differ (for example `nginx.request`).

### 9.2. Required dashboards

| Metric | Comparison | Purpose |
| --- | --- | --- |
| Request count | v1 vs. v2 over time | Confirm canary receives expected traffic volume |
| 4xx/5xx rate | By version and endpoint | Spot release errors; separate client from server failures |
| p50/p95/p99 latency | By version, route, and request type | Catch regressions hidden by averages |
| Instance count / startup latency | v1 and v2 | Measure cold starts, warmup, and autoscaling |
| Memory/CPU and error logs | By version | Detect OOMs, crashes, resource exhaustion |
| DB connections/queries | App-wide and per version if instrumented | Prevent two versions combined from exceeding DB capacity |
| Business KPIs | Checkout success, invoice creation, job failures | Confirm users still complete workflows |
| Cost | Instance hours, Cloud Build, logs/network | Watch budget while running versions concurrently |

In Cloud Monitoring and Logs Explorer, filter by labels such as **service, version**, and project; check exact metric names/resource types for your runtime/environment. **Never compare v2's 5xx rate directly against v1 if v2 only serves requests from a different cohort without normalizing traffic distribution.**

### 9.3. Sample decision matrix

| Illustrative condition | Decision |
| --- | --- |
| Smoke test `/release` shows wrong version or DB connection fails | Halt, do not shift traffic |
| 5% canary shows 5xx clearly above baseline | Roll back to v1 |
| Unclear anomaly with too few requests to conclude | Hold ratio, gather more evidence |
| v2 meets SLOs, business metrics steady, dependencies unsaturated | Increase share per approval |
| Errors appear at 100% during peak hours | Revert to v1 immediately, monitor capacity and data |

Real quantitative thresholds must be grounded in **SLOs/error budgets**, traffic volume, statistics, and business context; never apply one rigid percentage across all services.

## 10. Special considerations when running multiple versions

### 10.1. Sessions and sticky routing

Cookie splitting helps a user generally return to the same version if the client retains `GOOGAPPUID`; it **does not replace** an application session store.

- For multi-step APIs, use compatible schemas/session formats across v1/v2.
- Never store critical state solely in an instance's RAM because autoscaling and migration can replace instances.
- For mobile/CLI clients, preserve cookies across requests if stickiness is desired.
- Using IP splitting with calls from Google Cloud or many users behind NAT can skew canary ratios significantly.
- Do not rely on stickiness to guarantee all steps of a transaction always run inside the exact same process.

### 10.2. Caching and assets

During a split rollout, v1 HTML could reference v2 CSS/JS if assets share identical names. Use versioned filenames or content hashes. With CDNs/Cloud Load Balancing, check cache keys, headers, and request paths; never assume App Engine splitting acts as a canary for requests served by an upstream cache/layer.

### 10.3. Background tasks and cron

Service URL traffic splits **do not guarantee** that background tasks/cron or direct-version requests follow the same ratios. Task queues, scheduled jobs, and app-to-app calls may use separate routing paths. During rollout:

- Audit cron/task routes and target services/versions.
- Ensure idempotent processing; two versions must not cause double processing.
- Do not run incompatible database migrations/cleanups across v1 and v2.
- On rollback, verify producers and consumers still understand event schemas.

### 10.4. App Engine version URLs and access control

Version-specific URLs are convenient for smoke-testing 0%-traffic versions, but if the application lacks ingress/authorization restrictions, outsiders can still hit that URL directly. Similarly, when placing an external Application Load Balancer/Cloud Armor in front for protection, configure **App Engine ingress controls** so `appspot.com` paths cannot bypass the load balancer depending on architecture.

**Never expose canary URLs in customer interfaces or treat 0% traffic as a security control.**

## 11. Version lifecycle management and cost

### 11.1. Never delete a version receiving traffic

~~~bash
# List versions first before considering cleanup
gcloud app versions list \
  --service=default \
  --project=LAB_PROJECT_ID
~~~

Per the CLI, `gcloud app versions delete` **refuses to delete a version currently receiving traffic**. Only after routing traffic away, completing the rollback window, confirming zero direct-version callers, and obtaining approval should you consider:

~~~bash
# DESTRUCTIVE TO VERSION: run only in lab/on versions past retention
gcloud app versions delete v20261119a \
  --service=default \
  --project=LAB_PROJECT_ID
~~~

**Do not delete v2 immediately after rollback** if logs/evidence are still needed for investigation. Do not delete v1 solely because v2 reached 100%—retaining the prior release is essential for rollback.

### 11.2. “Stop version” has limitations

Per the current CLI reference, `gcloud app versions stop VERSION` applies only when a service uses **manual scaling**. Do not treat stop as a universal way to shut down **automatic scaling** versions:

~~~bash
# Applies only when manual scaling conditions are met; impactful
gcloud app versions stop VERSION_ID \
  --service=SERVICE_NAME \
  --project=LAB_PROJECT_ID
~~~

With automatic scaling, manage traffic allocation and deletion per lifecycle/approvals; check Standard/Flexible behaviors and the Console separately when needed. **0% traffic does not guarantee zero cost**, especially in Flexible or with `min_instances`/manual scaling.

### 11.3. Estimating parallel version costs

Cost components that can increase:

- Concurrent **instance hours/VM resources** for both v1 and v2, especially warm instances and Flexible VMs.
- Cloud Build, Artifact Registry/source staging, and storage artifacts.
- Log/trace/monitoring ingestion for both versions.
- Cloud SQL connections, caches, outbound network egress, and Pub/Sub/Task queue operations.
- Capacity held specifically for rollback readiness.

Configure **Cloud Billing Budgets** and alert thresholds; after the rollback window, decide retention/deletion per policy and audit requirements. Never delete solely because “traffic is 0%” if direct callers remain.

## 12. Operating via Console and CI/CD

### 12.1. Google Cloud Console

1. Go to **App Engine → Versions**, select the project and target service.
2. Inspect the existing version, traffic percentages, and error rates.
3. Deploy the new version via pipeline or CLI with `--no-promote`.
4. After smoke-testing the version URL, choose **Split traffic** to split 5%/95%.
5. Select the split method (IP or cookie) and monitor per version.
6. Ramp ratios as quality gates pass; finally **Migrate traffic** to one version.
7. On failure, select the previous stable version and **Migrate traffic** back.
8. After the rollback window, clean up unneeded versions per approval.

Button labels may evolve; never click **Migrate traffic** without confirming the right project, service, and version.

### 12.2. Reference release pipeline

~~~text
Source commit + pull request review
  → Build/test Java artifact
  → Security/dependency scans
  → Generate unique release version ID
  → Deploy --no-promote
  → Smoke-test version-specific URL
  → Split traffic 5%
  → Metrics gate + approval
  → Split traffic 25% → 50%
  → 100% and post-release monitoring
  → Retain previous good version
  → If SLO violated: set-traffic old=1
~~~

**Pipelines must not equate “deploy success = release success”.** Each stage should record a release log: project, service, version IDs, artifact/source commit, change approver, traffic ratios, dashboard links, timestamps, and rollback reason if triggered.

### 12.3. Least-privilege permissions

- **Deployer identity:** permissions needed to deploy App Engine versions and act as the runtime service account; exact roles depend on App Engine/Cloud Build and org policies.
- **Release operator:** permission to manage **traffic splitting/migration** on the service without necessarily modifying code.
- **Runtime identity:** scoped access to Cloud SQL, Secret Manager, or Google APIs on exact resources; never use an Editor service account.
- **Observer:** read metrics/logs without deploy/delete permissions.
- **Admin:** manages application/configuration, quotas, IAM, and audited emergency changes.

Never grant broad Project Owner/Editor just because `gcloud app deploy` threw Permission denied. Read the error to identify whether App Engine, Cloud Build, Artifact Registry, Staging Storage, or Service Account User permissions are missing, and grant at the proper scope.

## 13. Troubleshooting table

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| New deploy puts 100% of customers on v2 immediately | Forgot `--no-promote` | Roll back traffic to v1; fix pipeline |
| New version not visible | Deployment failed or targeted wrong project/service | Check deploy logs, `gcloud app versions list` |
| Cannot roll back to v1 | v1 was deleted or overwritten with the same version ID | Restore artifact, deploy with new version ID; audit CI |
| 5% canary gets nearly 0% or too many requests | IP NAT, low traffic, or skewed cookie cohort | Review split method, sample size, request metrics |
| Users bounce between v1 and v2 unexpectedly | Random split, changing IPs, or client drops cookies | Use cookie split and shared state |
| `/healthz` on version URL returns OK yet production fails | Tests omitted DB/auth/business paths | Add integration tests and business metrics |
| Switching to 100% causes p95 spike | v2 lacks warm capacity; cold start/warmup | Use Standard `--migrate` when eligible; pre-warm instances |
| Flexible does not migrate gradually as expected | Feature not supported as in Standard | Step traffic splits manually or migrate immediately |
| v1 crashes after rollback | Database/schema/secrets changed incompatibly | Use expand–migrate–contract; restore dependencies separately |
| App Engine logs still show v2 after rollback | Direct version URL/cron/tasks or in-flight requests | Check target paths, callers, and request logs |
| Cookies/cache break assets | Unversioned CSS/JS filenames or changed session format | Content hashing, compatibility, cache policies |
| 0% traffic yet still incurring charges | Flexible VMs, min instances/manual scaling, background tasks | Inspect scaling/instance hours and clean up safely |
| Cannot delete version | Version still has traffic allocation | Change traffic split first; check direct callers/retention |
| `versions stop` fails | Service does not use manual scaling | Use proper lifecycle management instead of forcing stop |
| CI permission denied | Missing App Engine/Cloud Build/SA IAM roles | Grant least-privilege IAM per error logs |

**Investigation sequence:** right project/service → version ID → traffic split → version URL → application logs → backend dependencies → SLO/cost. Avoid changing multiple variables at once and losing track of root causes.

## 14. Guided hands-on lab

**Prerequisites:** Run only in a lab project with an App Engine Standard Java 21 `default` service currently serving `v20261101a`. You have a new artifact for `v20261119a`, permissions to deploy/split traffic, and log/monitoring dashboards. If no sandbox is available, complete **the state-table simulation** instead of running live commands.

### Part A — Establish baseline

1. Use `gcloud app services list` and `versions list` to confirm the service/version receiving 100%.
2. Record old version, source commit, and HTTP 5xx/p95 baseline.
3. Verify database/API backward compatibility and budget for running two versions.

### Part B — Deploy and test in isolation

1. Run `gcloud app deploy app.yaml --version=v20261119a --no-promote` in the lab project.
2. Check output version ID and `versions list`: v2 is at 0%.
3. Use `gcloud app versions browse ... --no-launch-browser` to obtain the version URL.
4. Test `/release` returns v2, `/healthz`, and one read-only function.
5. Inspect error logs/latency and confirm no secrets are logged.

### Part C — Canary 5% then 25%

1. Choose `--split-by=cookie` for sticky users; explain why `ip` fails behind NAT.
2. Apply 95/5; record start time, actual request count, and metrics.
3. If healthy, update to 75/25; if not, roll back.
4. Do not run both split commands back-to-back without observation.

### Part D — Migration and rollback drill

1. On **App Engine Standard**, after review, shift 100% to v2 (consider `--migrate`).
2. Verify routing, per-version request volume, and resource usage.
3. Assume v2 shows a sudden spike in HTTP 5xx; **roll back traffic to v1=1**.
4. Verify the production-like service endpoint now returns `GAE_VERSION=v1` for service-routed requests, while the v2 version-specific URL remains reachable if allowed.
5. Explain how to prevent rollback from breaking the DB after schema changes.

### Part E — Report

| Evidence | Values to record |
| --- | --- |
| Project/service | ID and correct environment |
| Old/new versions | Unique IDs, source commit |
| Deploy no-promote | v2=0% after deploy |
| Smoke test | Results via version URL |
| 5% Canary | Timestamp, sample size, 5xx/p95 |
| 25% Canary | Timestamp, sample size, metrics |
| 100% migration | Immediate/gradual type, outcome |
| Rollback | v1=100%, errors return to baseline |
| DB compatibility | Changes requiring/not requiring rollback |
| Cost | Instance hours, dependencies/extra metrics |
| Cleanup decision | How long to retain old version and why |

**Never intentionally break production to prove rollback.** Simulate faults in lab code or toggle a feature flag in an isolated environment.

## 15. Review exercises and answers

1. **What is the risk of omitting `--no-promote` during deploy?** The new version usually receives 100% of traffic immediately.
2. **Can a v2 deployed at 0% still be accessed?** Yes, via its version-specific URL if ingress/auth permit.
3. **Does a service with two versions mean each runs exactly 50% of instances?** No; splits control request ratios, while capacity/instances are governed by scaling.
4. **Is `v1=2,v2=2` different from `v1=.5,v2=.5`?** No; weights are normalized.
5. **Why can a 5% IP split receive more than 5% of traffic?** NAT, concentrated callers, and source IP distribution.
6. **What does cookie splitting require from mobile clients?** Retaining and forwarding the `GOOGAPPUID` cookie across requests.
7. **Does random splitting keep the same user on one version?** No.
8. **Does a version URL participate in traffic splitting?** No; it targets the version directly.
9. **How does `--migrate` differ from a canary?** It targets 100% on one version with optional gradual ramp in Standard when supported; canaries require staged decisions and metric gates.
10. **Does Flexible support gradual migration like Standard?** No, per current docs; use manual stepped splits.
11. **When v2 fails, what is the core rollback command?** `gcloud app services set-traffic default --splits=v1=1`.
12. **Does routing rollback undo DB migrations?** No.
13. **Why avoid reusing an old version ID?** Risk of overwriting the existing version and losing the rollback target.
14. **Can you delete a version currently receiving traffic?** No; remove its traffic allocation first.
15. **Does 0% traffic guarantee zero cost?** No; scaling config, environment, and version-targeted requests still matter.
16. **Does `gcloud app versions stop` work for all autoscaling versions?** No; CLI stop is limited to manual scaling.
17. **Is HTTP 200 on healthz enough to promote?** No; business logic, DB, 5xx, p95, and security checks are required.
18. **What is different when v1 and v2 run concurrently?** Routing can split across separate code/configs, yet both still share the DB and external dependencies.

## 16. Production checklist and references

- [ ] Correct project/app/service/location; new version ID and artifact/source traceability.
- [ ] Deployed with **--no-promote**, version URL tested; never treat 0% as private.
- [ ] Selected cookie/IP/random split matching client types, sessions, NAT/caching.
- [ ] Canary has sufficient request volume and SLO-based quality gates.
- [ ] Warmup/capacity plan ready; Standard vs. Flexible migration behavior understood.
- [ ] Stable version retained through rollback window; never overwrite or delete prematurely.
- [ ] DB/schemas/message formats remain compatible while v1/v2 run together.
- [ ] Monitoring broken down by service/version and business endpoints, not just HTTP 200.
- [ ] Direct-version URLs, cron/tasks, and ingress/security controls audited.
- [ ] Least-privilege IAM, release approvals, and secret-free logs enforced.
- [ ] Budget accounts for parallel versions, Cloud Build, and data dependencies.
- [ ] Rollback runbook, post-rollback verification, and retention/cleanup policy ready.

**Official Google Cloud documentation:**

- [App Engine overview](https://docs.cloud.google.com/appengine/docs/an-overview-of-app-engine) — application, services, versions.
- [Deploy/test App Engine Standard](https://docs.cloud.google.com/appengine/docs/standard/testing-and-deploying-your-app) — `--no-promote`, version URLs.
- [Deploy/test App Engine Flexible](https://docs.cloud.google.com/appengine/docs/flexible/testing-and-deploying-your-app) — Flexible deployment.
- [Traffic splitting — Standard](https://docs.cloud.google.com/appengine/docs/standard/splitting-traffic) — IP/cookie split, limitations.
- [Traffic splitting — Flexible](https://docs.cloud.google.com/appengine/docs/flexible/splitting-traffic) — canary for Flexible.
- [Traffic migration — Standard](https://docs.cloud.google.com/appengine/docs/standard/migrating-traffic) — warmup, immediate/gradual, limits.
- [Traffic migration — Flexible](https://docs.cloud.google.com/appengine/docs/flexible/migrating-traffic) — Flexible routing.
- [App Engine request routing](https://docs.cloud.google.com/appengine/docs/standard/how-requests-are-routed) — service/version URLs and dispatch.
- [Warmup requests](https://docs.cloud.google.com/appengine/docs/standard/configuring-warmup-requests) — optimizing cold starts.
- [Java Standard runtime](https://docs.cloud.google.com/appengine/docs/standard/java-gen2/runtime) — Java 21, `PORT`, `GAE_VERSION`.
- [gcloud app deploy](https://docs.cloud.google.com/sdk/gcloud/reference/app/deploy) — `--version`, `--no-promote`.
- [gcloud app services set-traffic](https://docs.cloud.google.com/sdk/gcloud/reference/app/services/set-traffic) — `--splits`, `--split-by`, `--migrate`.
- [gcloud app versions delete](https://docs.cloud.google.com/sdk/gcloud/reference/app/versions/delete) — deletion constraints.
- [gcloud app versions stop](https://docs.cloud.google.com/sdk/gcloud/reference/app/versions/stop) — manual scaling only.
- [App Engine pricing](https://cloud.google.com/appengine/pricing) — instance hours and charges.

**Key takeaway:** Low-risk releases on App Engine start by **deploying a new version without shifting traffic**, followed by smoke testing, percentage-based canaries with quality gates, and migration to the target version. When incidents occur, **shift traffic back to the retained good version** and verify both application and data health. Application code rollback never replaces backups, compatible migrations, or SLO monitoring.
