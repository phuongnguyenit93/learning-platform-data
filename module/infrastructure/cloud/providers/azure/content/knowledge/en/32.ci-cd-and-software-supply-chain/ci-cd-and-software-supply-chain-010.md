# Canary, Blue-Green, and Rollback Deployments on Azure

An ordering service running on Microsoft Azure handles thousands of transactions per minute. A newly deployed CI/CD release introduces shipping fee calculation. Automated tests all passed, yet only under real user traffic does this version trigger HTTP 500 errors for a subset of shopping carts. If rolled out to 100% immediately, most customers would be impacted before operations could react.

**Canary deployment**, **blue-green deployment**, and **rollback** are three techniques that reduce release risk by controlling **which version serves traffic**, **what share of traffic shifts to the new version**, **which gates allow traffic increases**, and **how to return to a safe version**. In Azure, multiple mechanisms implement these patterns: Azure App Service deployment slots, Azure Container Apps revisions, Azure Kubernetes Service (AKS) with routing controllers, Azure Front Door, and CI/CD pipelines. However, no single command guarantees rolling back application code, databases, queues, and external side effects together.

This lesson belongs to the **CI/CD and Software Supply Chain** chapter of the **CLOUD_PROVIDERS_AZURE** module: learning how to deploy, monitor, secure, and control costs for Azure architectures across subscriptions, resource groups, Microsoft Entra ID, virtual networking, compute, storage, databases, and containers.

**Practice scope:** use hypothetical resource names and approved lab subscriptions/resource groups; never run traffic-shifting or slot-swap commands in production without authorization and change approval. CLI/YAML examples reflect capabilities supported in corresponding Azure/extension/controller versions; always verify `--help`, SKU, region, workload, and tool release notes before applying. Traffic shifts, revision activations, or database schema changes can cause outages or incur charges.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish **rolling**, **recreate**, **canary**, **blue-green**, **feature flags**, and **A/B testing**.
2. Explain the differences between deployment, release, and traffic cutover.
3. Describe the **build once, deploy the same immutable artifact** workflow using image digests and provenance.
4. Design a canary rollout across **1% → 5% → 20% → 50% → 100%** with hold windows and rollback gates.
5. Understand why traffic percentage does not automatically equal the exact percentage of users or transactions.
6. Design blue-green deployments with parallel green/standby environments, smoke tests, cutover, and rollback windows.
7. Execute conditional canary/swaps on **Azure App Service deployment slots**.
8. Steer traffic across **Azure Container Apps revisions** in multiple revision mode.
9. Distinguish AKS **Deployment rolling updates**, blue-green via Service selectors, and canary via Ingress/Gateway API or service mesh.
10. Explain Azure Front Door origin weights/priorities, health probes, session affinity, and traffic-splitting limits.
11. Configure **progressive delivery gates** based on p95/p99 latency, 5xx rates, conversion, DB errors, queue lag, and business metrics.
12. Distinguish **instant traffic rollback**, artifact redeployment, and **database recovery**.
13. Design **expand–migrate–contract** schema migrations so multiple versions can read and write concurrently.
14. Handle session stickiness, caching, sticky cookies, asynchronous workers, and stateful dependencies.
15. Combine Azure DevOps / GitHub Actions approvals, protected environments, and least-privilege permissions.
16. Govern secrets via Key Vault, managed identities/workload identities, ACR, and the software supply chain.
17. Build incident runbooks, forecast parallel-run costs, and rehearse rollbacks in staging.
18. Distinguish technical pipeline completion from **evidence that a release is genuinely safe**.

## 2. Why a successful deploy does not guarantee a successful release

### 2.1. Deployment and release are distinct milestones

- **Build:** produces a JAR or container image artifact from a specific commit.
- **Deployment:** places the artifact into a runtime, environment, slot, or revision.
- **Release:** exposes that version or feature to real users.
- **Traffic cutover:** shifts routing from the old version to the new one.
- **Rollout:** the phased process of expanding exposure.
- **Rollback:** returns traffic, code, or config to a known-good state; not synonymous with undoing all mutated data.

~~~mermaid
flowchart LR
    C["Git commit"] --> CI["CI: test, scan, build"]
    CI --> A["Immutable artifact + digest"]
    A --> DEP["Deploy revision/slot Green"]
    DEP --> TEST["Warm-up / smoke / security checks"]
    TEST --> G{"Approval + SLO gate"}
    G -->|PASS| TRAF["Progressive traffic"]
    G -->|FAIL| STOP["Keep stable serving"]
    TRAF --> OBS["Observe metrics / traces"]
    OBS --> DEC{"Healthy?"}
    DEC -->|Yes| PROM["Promote to 100%"]
    DEC -->|No| RB["Traffic rollback"]
~~~

In a mature architecture, **an artifact deployed without user traffic is not yet broadly released**. Smoke tests catch early bugs, but cannot replace observing live traffic.

### 2.2. Failures visible only after release

- Bugs triggered only on accounts with a rare combination of feature flags.
- Managed Identity holding staging permissions while missing production permissions.
- HikariCP / connection pool settings exhausting connections under scale.
- Azure SQL or Cosmos DB throttling due to altered query plans.
- JWT claims or tenant data differing from synthetic test fixtures.
- Front Door cache serving stale content or headers.
- Session affinity pinning a group of users to the faulty version.
- New queue consumers failing to parse older message schemas.
- Database migrations breaking backward compatibility.
- HTTP 429 rate limits appearing as real traffic rises.
- Third-party APIs enforcing stricter quotas in production.

**Release criteria must incorporate live operational telemetry**, not solely green build statuses.

### 2.3. Blast radius and detectability

Suppose total traffic is 10,000 requests/minute and the new version fails 2% of requests:

| Traffic to new version | Requests/minute to new version | Expected errors/minute on new version |
|---|---:|---:|
| 1% | 100 | 2 |
| 5% | 500 | 10 |
| 20% | 2,000 | 40 |
| 50% | 5,000 | 100 |
| 100% | 10,000 | 200 |

These figures are illustrative: traffic splits are approximate, samples are not strictly independent, and failures may cluster in a specific user segment. **Minimizing blast radius** matters, yet a canary that is too tiny makes rare error signals hard to detect. Balance sample size, hold duration, and metric gate sensitivity.

## 3. Comparing deployment strategies

### 3.1. Recreate, rolling, blue-green, canary

| Strategy | How it works | Benefits | Risks / limits |
|---|---|---|---|
| **Recreate** | Stops old version, then starts new version | Simple, minimal parallel runtime | Downtime and slow rollback |
| **Rolling update** | Replaces instances in batches within one workload | Uses fewer resources than blue-green | Two versions coexist; imprecise traffic control |
| **Blue-green** | Two complete versioned environments; traffic switches between them | Fast cutover/rollback while old version stays ready | Cost of running 2 environments; complex DB/state handling |
| **Canary** | New version receives a small slice of traffic, growing if healthy | Minimizes blast radius, metric-driven | Needs routing, sample sizing, analysis, and automation |
| **Shadow/mirror** | Copies live requests to new version without using its responses | Compares performance/behavior on real traffic | Unsafe for side effects; requires data sanitization |
| **Feature flag** | Toggles capabilities for targeted cohorts | Decouples code deployment from feature activation | Does not replace binary/schema rollbacks |
| **A/B testing** | Splits cohorts to measure product impact | Compares conversion/experience | Experimentation goals differ from release safety |

Canary and blue-green **can be combined**: deploy a full Green environment, send a fraction of traffic to Green, ramp to 100%, and keep Blue warm for rollback.

### 3.2. Canary vs. A/B testing

- Canary evaluates **technical safety and health** of a release: error rate, latency, saturation, data correctness.
- A/B testing evaluates **product impact**: conversion, retention, revenue, user behavior.
- Canaries can use percentage routing; A/B usually requires stable cohort assignment to avoid cross-group drift.
- Both may use feature flags, but their **decision gates** differ.

Never use a slight conversion uptick to excuse a tenfold jump in 5xx errors. Likewise, never declare a product algorithm inferior just because a 5% canary slice skewed geographically or by device mix.

### 3.3. Selection flow

~~~mermaid
flowchart TD
    Q{"Can two versions run concurrently?"}
    Q -->|No| M["Design backward compatibility / maintenance window"]
    Q -->|Yes| S{"Is weighted traffic splitting available?"}
    S -->|Yes| C["Canary or blue-green + canary"]
    S -->|No| B["Blue-green full cutover / rolling"]
    C --> O["Metric gates + rollback runbook"]
    B --> O
    O --> DB{"State/schema compatible?"}
    DB -->|No| FIX["Expand-contract before release"]
    DB -->|Yes| GO["Approve deployment"]
~~~

Having an Azure Load Balancer does not automatically provide weighted HTTP canaries: evaluate **actual routing-layer capabilities**.

## 4. Prerequisites before progressive delivery

### 4.1. Immutable artifacts and explicit versions

A well-designed pipeline maintains one single artifact:

~~~text
Git commit: 19a24d... (example)
  → build + test + scan
  → container image: acrorders.azurecr.io/orders@sha256:<digest>
  → deploy exact digest to staging/green
  → smoke & approval
  → promote/canary production with the exact same digest
~~~

**Never rebuild from a `latest` tag for production after staging passes**: shifting dependencies or build timestamps can alter the binary. Prefer image digests, SBOMs, provenance, and policy-enforced immutable tags.

### 4.2. Separate configuration and secrets

- Environment-specific config lives in App Configuration, environment settings, or governed config stores.
- Secrets are retrieved via Azure Key Vault, managed identities, AKS workload identity, or supported platform integrations.
- Both Blue and Green need proper permissions, networking, and DNS.
- Never let a test slot accidentally use production payment secrets or write to the production DB when smoke tests create data.
- Distinguish slot/revision-pinned settings from settings traveling with the artifact.
- Diff configurations before swapping so a release does not succeed with missing authorization.

### 4.3. Readiness vs. liveness

- **Liveness:** process is alive and not deadlocked.
- **Readiness:** instance can serve traffic properly (config loaded, warmed up, critical dependencies reachable).
- **Startup probe:** allows heavy apps time to boot before liveness probes fire prematurely.
- **Synthetic smoke test:** actively exercises endpoints on the new version.
- **Business canary test:** tests core transaction paths without causing real production side effects.

An HTTP 200 on **/** does not prove JDBC connections, Key Vault permissions, or Service Bus senders work. Readiness should also avoid hard-failing on an optional analytics service if doing so would strip serving capacity from the entire cluster.

### 4.4. Rollback path must exist before promotion path

Before shifting even 1% of traffic, confirm:

1. Which stable version/image digest can run again?
2. Are the stable slot/revision/pods retained and healthy?
3. Do commands or IaC exist to route back to stable?
4. Can feature flags and configs be reverted?
5. Does the database schema still allow stable code to run?
6. Can stable workers read event payloads emitted by the new version?
7. Is there a runbook for writes already committed by the new version?
8. Are rollback approvals and permissions fast enough to meet RTO?
9. Is an owner assigned to make the call and verify post-rollback recovery?

**An unrehearsed rollback is an assumption, not a proven capability.**

## 5. Designing traffic splitting properly

### 5.1. Distinguish request %, user %, and business %

Routing 10% of HTTP requests to a canary does not guarantee:
- 10% of unique users see the new version.
- 10% of orders flow through the canary.
- 10% of background messages are handled by the new worker.
- 10% of requests per region, device, or tenant.
- 10% of CPU or cost.
- 10% of high-risk paths such as payments.

One user may issue 100 requests while another sends one. Sticky cookies/session affinity can skew realized proportions away from configured weights. Client retries and CDN caches also alter actual origin traffic.

### 5.2. Traffic weights vs. cohort routing

| Method | When to use | Considerations |
|---|---|---|
| Random weighted request | Stateless systems with independent requests | One user may bounce between versions across requests |
| Sticky session | Session state or consistent UX required | Session persistence, uneven traffic distribution |
| Stable user hash | Deterministic cohort canary | PII handling and hash/routing config governance |
| Header/cookie routing | QA/staff testing a new version | Never trust client-supplied headers for security-sensitive routing |
| Geographic ring | Region/site-by-site canary | Differing traffic profiles, latency, and compliance |
| Tenant allowlist | Agreed enterprise pilot | Single high-volume tenant may skew load |
| Feature flag cohort | Toggling behavior per user/tenant | Does not isolate process crashes when the binary serves all traffic |

### 5.3. Enforce hold windows

Hold each traffic stage long enough to:
- Collect adequate request volume and signals.
- Account for telemetry ingestion delay.
- Observe startup spikes and cache warm-up.
- Measure p95/p99 latency.
- Encounter key cron/background jobs.
- Check queue backlogs and eventual consistency.
- Observe cost and downstream load.

Holding 10% for 30 seconds just because a dashboard looks green misses failures triggered by a 15-minute batch job. Conversely, holding too long may conflict with urgent security hotfixes; apply risk-based approvals and clear rollback plans.

## 6. Signals deciding promote vs. rollback

### 6.1. Metric gates go beyond HTTP 200

A healthy canary requires multiple signal groups:

| Group | Example signals | Compare against |
|---|---|---|
| Availability | 5xx, request failures, crashloops | Stable version and SLO |
| Latency | p50/p95/p99 by route | Same-window/region baseline |
| Saturation | CPU, memory, GC, thread pools, HikariCP | Stable and capacity limits |
| Dependencies | SQL timeouts, Cosmos RU throttling, Key Vault 403/429 | Prior release and quotas |
| Messaging | Service Bus active messages, DLQ, processing lag | Consumer baseline |
| Business | Orders completed, payment failures, duplicate invoices | Business thresholds |
| Security | Auth failure spikes, access denied, unusual egress | Security policy |
| Telemetry quality | Trace/metric coverage, log ingestion health | Monitoring pipeline |
| Cost | Azure API calls, egress, replicas, DB load | Expected budget |

Define critical gates (fail → immediate rollback) and warning gates (hold/investigate) instead of a single composite score that hides severe failures.

### 6.2. Illustrative canary policy

~~~text
Canary stages: 1% → 5% → 20% → 50% → 100%
Hold windows: 10m → 15m → 20m → 30m

During each hold:
  min requests to canary: >= 500
  canary HTTP 5xx <= 1.0%
  canary 5xx <= stable 5xx + 0.5 percentage point
  canary p95 <= 1.25 × stable p95
  payment failure rate <= approved business threshold
  no critical data-integrity incident
  no new high-severity security failure
  sufficient telemetry freshness/coverage

On critical gate failure:
  stop promotion
  route traffic back to stable
  disable dangerous feature flags if needed
  preserve evidence
  verify recovery
~~~

**This is an example, not a Microsoft Azure default or universal threshold.** Calibrate real thresholds to SLOs, business risk, meaningful baselines, sample sizes, and metric accuracy. At low traffic, requiring 500 requests can extend hold windows longer than planned.

### 6.3. Denominators and noisy signals

`5xx rate = 5xx / total requests` must be calculated per **exact version's traffic**, never mixing stable and canary traffic. Filter or classify:
- Health probe URLs.
- Synthetic test traffic.
- User-cancelled requests.
- Expected 4xx validation errors.
- App or gateway retries.
- Overlapping time windows.
- Traffic from tenants/geographies with distinct baselines.

At 1% canary receiving 100 requests, a single error equals 1%. Do not roll back over an expected 404; however, **one data-corruption or double-charge error** can trigger a critical gate regardless of sample size.

### 6.4. Observing with Azure Monitor

Telemetry sources can include:
- Application Insights `AppRequests`/`AppDependencies`/`AppExceptions`.
- Azure Monitor metrics and alert rules.
- Log Analytics KQL / Workbooks.
- App Service metrics and slot-specific telemetry where configured.
- Azure Container Apps revision metrics/logs.
- AKS kube-state metrics / Container Insights / managed Prometheus where configured.
- Azure SQL / Cosmos DB / Storage / Service Bus metrics.
- OpenTelemetry traces carrying `service.version`/role attributes.

**KQL exhibits ingestion delay and sampling**: never rely solely on sampled traces for total error rates without understanding weights. Metric gates need fresh, version-separable sources. If telemetry is missing (no data), the safe policy is **HOLD**, never auto-promote.


## 7. Azure App Service: deployment slots and blue-green

### 7.1. What is a deployment slot?

**Deployment slots** let a single Azure App Service host multiple runtime environments—such as production, staging, or test—on supported tiers. A slot provides:
- Its own endpoint for smoke testing.
- Its own application code/container version.
- App settings/connection strings with **slot-specific/sticky** rules.
- A **slot swap** mechanism to promote a verified version to production.
- Ability to route a percentage of traffic to a non-production slot where supported.

**Prerequisites:** deployment slots depend on the App Service plan and SKU; typically **Standard, Premium, or Isolated** tiers support slots—do not assume Free/Shared/Basic provide them. Check app type (Windows/Linux/container), region, plan, and exact Azure CLI behavior.

### 7.2. Blue-green diagram with slots

~~~mermaid
flowchart LR
    U["Users"] --> PROD["Production hostname"]
    PROD --> B["Production slot: Blue v1"]
    STAGE["Staging slot URL"] --> G["Staging slot: Green v2"]
    Q["QA + smoke tests"] --> STAGE
    G -. "swap after approval" .-> PROD
~~~

**Before swap:** production runs Blue v1; staging holds Green v2. **After a successful swap:** production serves Green v2; staging typically retains the prior production version to enable a reverse swap depending on swap/config behavior. Both slots may share App Service plan capacity; **slots are not necessarily isolated compute environments**.

### 7.3. Read-only preflight checks

~~~bash
RG="rg-orders-lab"
APP="app-orders-lab"

az account show --query "{subscription:id,tenant:tenantId}" -o json

az webapp show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "{name:name,state:state,host:defaultHostName,plan:serverFarmId}" \
  -o json

az webapp deployment slot list \
  --resource-group "$RG" \
  --name "$APP" \
  -o table
~~~

These commands only read metadata. If no staging slot exists, never create one arbitrarily in production because slots carry config, capacity, and cost implications.

### 7.4. Creating a staging slot in an authorized lab

~~~bash
az webapp deployment slot create \
  --resource-group "$RG" \
  --name "$APP" \
  --slot staging
~~~

This mutates an Azure resource and requires proper IAM. Some options clone configuration from a source slot; **never copy all production secrets/connection strings to staging uncontrollably**.

Once created, deploy Green to staging via CI/CD from an **approved, built-and-tested artifact**. Never redeploy from a floating source branch when production uses a different artifact.

### 7.5. Slot-specific settings and secrets

Certain app settings and connection strings can be marked **deployment slot settings** (sticky), staying attached to the slot name during swaps. This is critical:

- Application Insights connection strings for staging and production must target the right resource and telemetry attribution.
- Staging database connection strings should usually point to a sandbox DB.
- Managed identities, networking, hostnames/certificates, and other settings have specific swap semantics.
- Feature flags must be checked before promotion.
- Never assume all App Settings swap with the code, or that all settings stay put.

**Smoke tests must target test resources or avoid side effects.** If staging points to the production database and runs migrations at startup, Green can corrupt production data before receiving 1% traffic.

### 7.6. Warm-up and health checks

Before cutover, ensure:
1. The Green process has booted.
2. JIT, connection pools/caches, and dependency clients are warmed up.
3. Startup configuration and identities are verified.
4. GET readiness endpoints or bounded smoke tests run cleanly.
5. Memory, GC, CPU, and HTTP dependencies look healthy.
6. Staging logs/telemetry show no hidden errors.
7. The stable slot remains healthy.

App Service supports **swap warm-up** settings such as `WEBSITE_SWAP_WARMUP_PING_PATH` and `WEBSITE_SWAP_WARMUP_PING_STATUSES` depending on runtime/version. **App Service Health Check** and **slot swap warm-up** are distinct features; configuring a health endpoint alone does not automatically configure desired swap-wait behavior.

### 7.7. Swapping staging → production

Once approved and preflight checks pass:

~~~bash
az webapp deployment slot swap \
  --resource-group "$RG" \
  --name "$APP" \
  --slot staging \
  --target-slot production
~~~

This command **impacts production traffic**; never run it in a lab if that URL serves real customers. A swap is not a "manual DNS switch"; App Service runs platform swap mechanics including config application and warm-up steps.

**Swap with preview** supports inspecting configuration before finalizing in some App Service environments, with limitations across OS/app types; do not assume it is always available on Linux/container workloads.

### 7.8. Rolling back via reverse swap

If Green fails after cutover:
1. Halt promotion and disable suspect feature flags.
2. Confirm staging still holds Blue v1 and can start cleanly.
3. Verify DB/schema, secrets, and queues remain backward-compatible.
4. If satisfied, execute a **reverse swap**:

~~~bash
az webapp deployment slot swap \
  --resource-group "$RG" \
  --name "$APP" \
  --slot staging \
  --target-slot production
~~~

Running the same command a second time after a swap brings the previous version back into production. **Swap rollback is not guaranteed if** staging was overwritten, config drifted, a migration broke schema compatibility, the slot was deleted, or the prior version can no longer boot.

If unsure of slot state, inspect **sanitized deployment version/hash, host, and response headers** before swapping; never swap blindly out of habit.

## 8. Canary on App Service via traffic routing

### 8.1. Routing distribution across deployment slots

When a staging slot supports traffic routing, App Service can send a percentage of requests to staging. Model:

~~~mermaid
flowchart LR
    U["Client requests"] --> ROUTER["App Service routing"]
    ROUTER -->|"90% target"| BLUE["Production slot v1"]
    ROUTER -->|"10% target"| GREEN["Staging slot v2"]
    BLUE --> OBS["Metrics by version"]
    GREEN --> OBS
~~~

Traffic splits are **not exact request counts**. App Service uses a **routing cookie** (e.g., `x-ms-routing-name`) to keep clients pinned to a slot where appropriate. Testing with `curl`, browsers, and load generators must account for cookies and session stickiness to measure distribution accurately.

### 8.2. Setting canary percentages

In an App Service lab on a supported SKU with Green deployed:

~~~bash
RG="rg-orders-lab"
APP="app-orders-lab"

# Shift a portion of production-hostname traffic to staging.
az webapp traffic-routing set \
  --resource-group "$RG" \
  --name "$APP" \
  --distribution staging=10

# Inspect actual routing configuration on the app.
az webapp traffic-routing show \
  --resource-group "$RG" \
  --name "$APP"
~~~

Use these commands only after approval because they alter live user traffic. Verify **staging slot readiness, auth/config, and endpoints** beforehand. If commands or syntax differ by Azure CLI version, inspect `az webapp traffic-routing --help` in an authorized admin context rather than assuming availability across all plans.

### 8.3. Traffic ramp schedule

~~~text
T0: Staging Green deployed, warmed up, smoke PASS
T1: App Service routing staging=1%
    → wait for sufficient requests + observe
T2: staging=5%
    → measure error rate and p95 per version
T3: staging=20%
    → inspect DB/queue/business metrics
T4: staging=50%
    → capacity, frontend/session behavior
T5: promote/swap or move Green to production per plan
~~~

Routing 100% of traffic to staging still leaves deployment slot state and configuration distinct from performing a **swap**. Define the **final target state** clearly—traffic routing vs. slot swap cutover—and never set staging to 100% assuming code moved into the production slot.

### 8.4. Clearing traffic routing rolls back the canary phase

When staging Green fails while production Blue remains healthy:

~~~bash
az webapp traffic-routing clear \
  --resource-group "$RG" \
  --name "$APP"
~~~

This resets routing to default (production slot) under current configuration. **It does not roll back code that was already swapped.** If the production slot already holds Green from an earlier swap, clearing routing only removes the split without restoring Blue; inspect slot state and execute a separate rollback strategy.

### 8.5. Session stickiness and measurement effects

- Browsers carry cookies pinning them to one slot across requests.
- Load tests reusing one cookie jar may hit only one version.
- Initial requests may not reflect target percentages in tiny samples.
- Long-lived connections/WebSockets behave differently from stateless requests.
- Authentication redirects and hostnames can affect sessions.
- Canary metrics must be segmented by version/slot, not just domain.

Never inject **production secrets** into headers to force routing. When QA needs to test a staging URL/slot, use protected test routes and test accounts.

### 8.6. Slot isolation limits

Staging and production slots can share App Service plan CPU and memory. A memory leak in Green v2 can **slow down Blue v1** even when Green receives only 5% of traffic. Canaries must therefore monitor **stable health** in parallel; a "5% canary" does not guarantee a 5% blast radius in every situation.

## 9. Azure Container Apps: revisions and traffic splitting

### 9.1. What is a revision?

An **Azure Container Apps revision** is an immutable snapshot of **revision-scope** settings: image, command, env vars, scaling template, and related configuration. Updating those properties creates a new revision; application-scope changes like secrets or ingress have different semantics.

Container Apps offers two **revision modes**:
- **Single:** maintains one active revision serving traffic at a time; supports platform rollouts, but does not let you actively split percentages across two revisions like multiple mode.
- **Multiple:** keeps multiple revisions active concurrently, allowing **traffic weights** on ingress for canary and blue-green workflows.

A revision existing does not mean it is active or has healthy replicas. Inspect status, ingress, and scaling.

### 9.2. Diagram

~~~mermaid
flowchart LR
    C["Internet / private ingress"] --> ING["Container Apps ingress"]
    ING -->|"95%"| R1["orders--stable revision"]
    ING -->|"5%"| R2["orders--canary revision"]
    R1 --> DB["Shared database / services"]
    R2 --> DB
    R1 --> MET["Revision metrics / logs"]
    R2 --> MET
~~~

Ingress traffic splitting applies to HTTP ingress where supported; **it does not automatically split 5% of Azure Service Bus messages** across queue-consuming workers. Queue-driven background workers have separate scale rules and competing consumers, requiring independent migration and compatibility design.

### 9.3. Inspecting app state and revisions

~~~bash
RG="rg-orders-lab"
APP="ca-orders-lab"

az containerapp show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "{name:name,activeMode:properties.configuration.activeRevisionsMode}" \
  -o json

az containerapp revision list \
  --resource-group "$RG" \
  --name "$APP" \
  --output table

az containerapp show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "properties.configuration.ingress.traffic" \
  -o json
~~~

Do not guess revision names from tags; real names carry generated rollout/revision suffixes returned by the API.

### 9.4. Enabling multiple revisions mode in a lab

~~~bash
az containerapp revision set-mode \
  --resource-group "$RG" \
  --name "$APP" \
  --mode multiple
~~~

This changes how the app manages revisions; run only with approval. In live systems, switching modes or active revisions can alter traffic and scaling behavior. Verify your Azure Container Apps CLI extension/version.

### 9.5. Setting 95/5 weights

Assuming two revisions are **active**, healthy, and verified by exact name:

~~~bash
STABLE="ca-orders-lab--stable123"  # Replace with actual revision
CANARY="ca-orders-lab--new456"     # Replace with actual revision

az containerapp ingress traffic set \
  --resource-group "$RG" \
  --name "$APP" \
  --revision-weight "$STABLE=95" "$CANARY=5"
~~~

Configured traffic weights must sum to 100 per ingress rules. **Never deploy a revision and shift traffic immediately** without verifying readiness, startup, and secrets. If a revision scales to zero, account for cold starts and readiness when the canary receives its first requests.

### 9.6. Rolling back traffic to stable

When a gate fails:

~~~bash
az containerapp ingress traffic set \
  --resource-group "$RG" \
  --name "$APP" \
  --revision-weight "$STABLE=100" "$CANARY=0"
~~~

Then verify ingress weights and stable health. **Do not deactivate or delete the canary immediately** while active connections finish draining or logs, side effects, and forensic evidence still need collection. Deactivation/deletion should follow separate approval and retention policies.

### 9.7. Blue-green using revisions and labels

One approach:
- Deploy the Green revision in parallel receiving zero production traffic.
- Test via a revision-specific URL or label URL where supported.
- Flip traffic from stable 100% → Green 100% on passing checks.
- Keep Blue active for the rollback window.
- On failure, route traffic 100% back to Blue.

Container Apps provides **revision labels** offering stable URLs per revision depending on ingress configuration. Labels aid testing and cutovers, yet **a label URL does not equal a traffic weight**. Always verify the actual routing configuration.

### 9.8. Revision scope, secrets, and configuration drift

- Updating the image or env template creates a new revision.
- Updating application-scope secrets does not automatically create a revision or reload secrets in running processes.
- Managed identities, networking, and registry auth must work for all active revisions.
- Rolling back a revision does not revert external secret values.
- An older revision may fail to start if its image was purged from ACR or a key rotated.
- Test custom domains, TLS, certificates, and cookies on the real ingress.
- Workers without HTTP ingress do not use HTTP traffic weights.

**Keeping an old revision around helps only while its artifact, identity, network, and data schema remain viable.**


## 10. AKS: rolling updates do not equal weighted canaries

### 10.1. Deployment rolling updates

Kubernetes Deployments support **RollingUpdate** with **maxSurge** and **maxUnavailable**. Example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
  namespace: commerce
spec:
  replicas: 4
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: orders
  template:
    metadata:
      labels:
        app: orders
        version: v2
    spec:
      containers:
        - name: orders
          image: acrorders.azurecr.io/orders@sha256:<approved-digest-v2>
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            periodSeconds: 5
            failureThreshold: 3
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              memory: 1Gi
~~~

This is **illustrative YAML—replace digest, namespace, resource settings, and image pull/trust configs**. Create the namespace, identity/ACR authorization, networking, and readiness endpoint in your lab before applying; never copy straight into production.

Key semantics:
- `maxSurge: 1` permits at most one extra Pod above desired replicas, requiring cluster capacity.
- `maxUnavailable: 0` keeps desired Pods available during normal rollouts, relying on readiness and termination probes.
- Rollouts can still stall due to node quotas, pending Pods, misconfigured readiness, or external dependencies.
- A Service targeting all ready Pods serves old and new versions simultaneously during the rollout.

**RollingUpdate does not guarantee 10% request traffic to v2.** Pod counts do not govern exact request proportions because of connection reuse, session affinity, and uneven per-Pod load.

### 10.2. Checking rollout status and history

~~~bash
NS="commerce"
DEP="orders"

kubectl rollout status \
  deployment/"$DEP" \
  -n "$NS" \
  --timeout=5m

kubectl get deployments,pods \
  -n "$NS" \
  -l app=orders \
  -o wide

kubectl rollout history \
  deployment/"$DEP" \
  -n "$NS"
~~~

These commands inspect status only. **A passing `kubectl rollout status` does not prove business metrics pass**: readiness probes can stay green while 5% of orders miscalculate shipping fees.

### 10.3. Using `rollout undo` when appropriate

When a rolling update fails and the prior revision remains in history:

~~~bash
kubectl rollout undo deployment/orders -n commerce
kubectl rollout status deployment/orders -n commerce --timeout=5m
~~~

**Limitations:**
- Restores only the Deployment Pod template/revision retained by Kubernetes; does not revert schemas, secrets, or external writes.
- May fail if the old image was purged from Azure Container Registry.
- If GitOps (Flux/Argo CD) or a pipeline still reconciles desired state v2, a manual undo will be overwritten.
- Update the **source of truth** (GitOps manifests / release config) and reconcile cleanly to avoid flip-flopping production.

### 10.4. Pod readiness and graceful termination

To avoid dropping traffic during rollbacks:
- `readinessProbe` must remove a Pod from endpoints before it stops serving.
- `preStop` hooks and `terminationGracePeriodSeconds` let in-flight requests finish cleanly.
- Apps, Nginx, and sidecars must handle graceful shutdown.
- Avoid readiness probes that perform unauthorized writes to databases.
- Configure `PodDisruptionBudget` to fit cluster capacity and maintenance.
- HPA, Cluster Autoscaler, and node pools need capacity for surge and overlapping versions.
- Watch for 502/503 responses caused by connection draining during traffic cuts.

For queue-consuming workers, readiness/termination alone is insufficient: stop pulling new messages and finish or release message locks/offsets cleanly to prevent duplicates or lost work.

## 11. AKS blue-green with two Deployments and one Service

### 11.1. Separating versions with labels

Maintain two independent Deployments:
- `orders-blue`: Pods labeled **app=orders, track=blue**.
- `orders-green`: Pods labeled **app=orders, track=green**.
- One Kubernetes Service **orders** selecting either group via the `track` selector.

~~~mermaid
flowchart LR
    R["Ingress / Gateway"] --> S["Service orders"]
    S -->|"selector track=blue"| B["Deployment orders-blue"]
    S -. "switch selector" .-> G["Deployment orders-green"]
~~~

Green can be smoke-tested via a separate Service (`orders-green-preview`) or protected internal route without receiving production traffic prior to cutover.

### 11.2. Service selecting Blue

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: orders
  namespace: commerce
spec:
  selector:
    app: orders
    track: blue
  ports:
    - name: http
      port: 80
      targetPort: 8080
  type: ClusterIP
~~~

Both Deployments need matching Pod labels and readiness probes; **do not alter a Deployment's immutable `spec.selector` after creation**. In a blue-green setup, maintain the two Deployments rather than recreating selectors constantly.

### 11.3. Switching traffic Blue → Green

Only in an approved environment:

~~~bash
kubectl patch service orders \
  -n commerce \
  --type merge \
  -p '{"spec":{"selector":{"app":"orders","track":"green"}}}'
~~~

Then inspect Endpoints/EndpointSlices, readiness, 5xx rates, session draining, and telemetry:

~~~bash
kubectl get service orders -n commerce -o yaml
kubectl get endpointslice -n commerce \
  -l kubernetes.io/service-name=orders
~~~

**Patching a Service selector is not an atomic zero-connection-loss switch across every layer.** `kube-proxy`, ingress controllers, and active connections exhibit propagation delays. Under GitOps, commit the selector change to desired state manifests or the controller will revert it to Blue.

### 11.4. Immediate rollback at the routing layer

When Green fails while Blue remains ready:

~~~bash
kubectl patch service orders \
  -n commerce \
  --type merge \
  -p '{"spec":{"selector":{"app":"orders","track":"blue"}}}'
~~~

This is strictly a traffic rollback. If Green ran an incompatible migration, Blue may fail once traffic returns. If Green published schema v2 messages, Blue workers may fail to parse them. Prove **backward compatibility** before cutover.

### 11.5. AKS blue-green costs

Running 4 Blue Pods + 4 Green Pods concurrently may require extra nodes or squeeze quotas for other workloads. Azure Standard Load Balancer and Application Gateway also carry their own costs and limits; 5% canary traffic **does not mean paying only 5% for Green**, because warmed Pods and dependencies stay running.

## 12. AKS canary via Gateway API or service mesh

### 12.1. Why standard Kubernetes Services fall short

A standard Kubernetes Service selects Endpoints by label; it **has no built-in field to send 90% of requests to version A and 10% to version B**. Controlling HTTP/L7 weights requires a **routing controller** supporting:

- Gateway API `HTTPRoute` `backendRefs` weights.
- A service mesh like Istio with `VirtualService`/`DestinationRule`.
- Ingress controllers with native canary annotations.
- Azure Front Door in front of two origins at the edge when architecturally appropriate.

Required APIs/CRDs must be installed and supported by your controller; **creating an AKS cluster does not automatically enable weighted `HTTPRoute` or Istio**.

### 12.2. Illustrative Gateway API `HTTPRoute`

Given two Services:
- `orders-stable` → stable version Pods.
- `orders-canary` → canary version Pods.

The controller must have a configured Gateway named **orders-gateway** supporting weighted `backendRefs`:

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: orders-route
  namespace: commerce
spec:
  parentRefs:
    - name: orders-gateway
  hostnames:
    - "orders.example.test"
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /
      backendRefs:
        - name: orders-stable
          port: 80
          weight: 95
        - name: orders-canary
          port: 80
          weight: 5
~~~

**This template requires integration with an actual `GatewayClass`/controller.** An `HTTPRoute` not yet `Accepted`/`Programmed` has no effect; check status conditions, Gateway readiness, DNS, TLS, backend namespaces, and `NetworkPolicy`. Controllers or Azure managed offerings may implement subsets of the Gateway API—confirm weighted `backendRef` support before relying on it.

### 12.3. Illustrative Istio service mesh

When AKS has a service mesh/ingress configured per its support matrix, use **DestinationRule subsets** and **VirtualService traffic weights**:

~~~yaml
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: orders-subsets
  namespace: commerce
spec:
  host: orders.commerce.svc.cluster.local
  subsets:
    - name: stable
      labels:
        track: stable
    - name: canary
      labels:
        track: canary
---
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: orders-routing
  namespace: commerce
spec:
  hosts:
    - orders.commerce.svc.cluster.local
  http:
    - route:
        - destination:
            host: orders.commerce.svc.cluster.local
            subset: stable
          weight: 90
        - destination:
            host: orders.commerce.svc.cluster.local
            subset: canary
          weight: 10
~~~

This illustrates **internal mesh routing on the service host**; external ingress requires additional Gateway/host configuration. For subsets to work, the Service must select Pods from both tracks with matching labels, and traffic must traverse the configured mesh data plane. Workloads outside the mesh or clients bypassing sidecars will not obey `VirtualService` weights as expected.

### 12.4. Other mechanisms

- Ingress controllers have **vendor-specific** canary annotations/properties; never copy YAML from controller A to controller B expecting identical behavior.
- Azure Application Gateway for Containers and other Gateway API implementations vary by version and features; confirm weighted `backendRef` support before production design.
- Basic Azure Load Balancer operates at L4 and **does not provide release-aware HTTP canary weights**.
- Native Kubernetes rollouts replace Pods in batches without automated SLO analysis.

### 12.5. Rolling back to stable in mesh / Gateway API

When a canary fails:
1. Update routing configuration to **100/0** stable/canary.
2. Ensure the stable deployment has sufficient capacity.
3. Confirm the controller reports the route programmed and upstream traffic shifts back.
4. Monitor in-flight requests, WebSockets, and session persistence.
5. Retain canary Pods briefly if needed for forensics, then scale down under control.
6. Commit the rolled-back GitOps manifest so reconciliation does not revert to 90/10.

**Rolling back routing does not automatically roll back the container image in the canary Deployment.** Treat them as distinct steps with explicit state tracking.

## 13. Azure Front Door: canary/blue-green at the edge

### 13.1. When is Front Door appropriate?

**Azure Front Door Standard/Premium** provides edge routing across backend origins, health probes, TLS/WAF, and edge protections. An architecture can front two independent origins:

~~~mermaid
flowchart LR
    U["Users across regions"] --> FD["Azure Front Door"]
    FD -->|"High weight"| B["Blue origin / old app"]
    FD -->|"Low weight"| G["Green origin / new app"]
    B --> M["Metrics/logs"]
    G --> M
~~~

Examples include two distinct App Services, two Container Apps endpoints, or two ingress gateways; **Front Door cannot split traffic between two code versions if only one origin address exists**.

### 13.2. Weights, priorities, and health

- **Priority:** selects preferred and failover origins per routing semantics.
- **Weight:** distributes relative traffic across healthy, eligible origins of equal priority under weighted routing.
- **Health probe:** failing origins drop out of the eligible pool, altering realized weights.
- **Latency-based selection:** routing sensitivity settings can influence origin choice.
- **Session affinity:** pins a user to one origin for a duration.
- **Caching:** edge nodes may serve cached responses without forwarding requests to origins.

Setting weights Blue=900, Green=100 expresses an **approximate 90/10 target ratio when routing conditions permit**, not a guarantee of 10% of unique users.

### 13.3. Never use priority instead of weight for a canary

Giving Blue higher priority than Green sends nearly all traffic to Blue while Blue is healthy, reaching Green only on failover. That is **failover, not a 10% canary**. Configure weights and priorities per your origin group's routing rules and verify distribution in access logs.

### 13.4. Caching, state, and security

- For sensitive dynamic APIs, enforce `Cache-Control: no-store` or strict caching rules to prevent cross-user data leaks.
- Keep WAF policies and rule sets consistent between stable and canary traffic.
- Validate origin hostnames, TLS certificates, origin host headers, and allowlists.
- Feature flags or route rules may affect only specific regions or paths.
- Data residency rules may restrict routing traffic across regions.
- Inspect Azure Front Door access logs to verify origin splits rather than relying solely on client metrics.

### 13.5. Azure Traffic Manager is not a request-level canary

Azure Traffic Manager steers DNS responses using methods such as weighted routing. DNS TTLs, resolver caching, and client behavior make request-level HTTP accuracy impossible. It fits regional routing policies, **not a direct substitute for Front Door / L7 Gateways** when a precise 1% canary is needed.

### 13.6. Multi-region releases

With Southeast Asia and West Europe regions:
1. Canary one region with a representative business mix.
2. Hold other regions on the stable baseline.
3. Evaluate data residency, latency, and cross-region dependencies.
4. Expand to the next ring once checks pass.
5. Watch failover vs. weighted routing—never mistake failover traffic for a healthy canary.
6. Maintain per-region rollback and a global kill switch if needed.

A canary passing in one region **does not guarantee safety in every region**, since networking, database topology, availability zones, and traffic mixes vary.


## 14. Database migrations: why rolling back the app is not enough

### 14.1. Risks of shared state

Blue and Green commonly share access to:
- Azure SQL Database / PostgreSQL / MySQL.
- Azure Cosmos DB.
- Azure Storage.
- Azure Cache for Redis.
- Azure Service Bus / Event Hubs.
- Key Vault / App Configuration.
- External SaaS APIs.

If Green automatically **drops a column**, alters column semantics, or writes a format Blue cannot parse, routing 100% back to Blue triggers new failures—even if Green served only 1% of requests.

### 14.2. Expand–migrate–contract pattern

~~~mermaid
flowchart LR
    A["Stable v1 reads schema A"] --> E["EXPAND: add compatible fields"]
    E --> B["v1 + v2 compatible"]
    B --> M["MIGRATE/BACKFILL data gradually"]
    M --> C["All consumers on v2"]
    C --> D["CONTRACT: remove legacy only after window"]
~~~

**Expand:** add new columns, tables, indexes, or API fields compatibly so v1 keeps running. Never drop or rename fields still required by v1.

**Migrate:** gradually backfill existing rows or dual-read/dual-write while monitoring errors.

**Contract:** remove legacy structures/behaviors only when:
- All applications and workers have migrated.
- Rollback to v1 is no longer expected.
- Retention, offline clients, and replay windows have closed.
- Migration/backfill is verified with a tested backup/recovery plan.
- Governance and change approvals are complete.

### 14.3. Illustrative Azure SQL example

Suppose v1 writes `Orders.Status`, and v2 adds `ShippingStatus`.

**Expand (intentional, lab/T-SQL):**

~~~sql
-- Illustrative only: review locks, table size, transactions,
-- indexes, backups, and deployment order before production.
ALTER TABLE dbo.Orders
ADD ShippingStatus nvarchar(32) NULL;
~~~

Version v1 keeps working because the new column is nullable. Version v2 reads `ShippingStatus` and falls back cleanly when legacy rows are NULL. **Never write v2 code assuming every row immediately has a non-null value.**

**Migrate/backfill:** run controlled batches to avoid long locks on large tables; track progress and audit data correctness.

**Contract:** only after the rollback window closes should you consider dropping legacy fields, adding `NOT NULL` constraints, or removing dual-write code. Test every step in staging against realistic data sizes.

### 14.4. A schema change that cannot be quickly reversed

Bad example:

~~~sql
-- DO NOT run during canary / rollback window
-- if v1 still depends on this field:
ALTER TABLE dbo.Orders
DROP COLUMN Status;
~~~

Once executed, Blue v1 fails immediately. Restoring schema structure does not recover dropped data, and point-in-time backup restores risk losing newer writes. After a destructive migration, only a **forward fix**, RPO/RTO backup restore, or complex data recovery remains—not a simple traffic rollback.

### 14.5. Feature flags reduce risk but do not replace schema design

Distinguish:
- **Flag OFF:** app still runs v2 code while skipping the new logic branch.
- **Traffic rollback:** routes back to v1.
- **Schema rollback:** alters database structure/data (potentially destructive).
- **Data correction:** repairs records written incorrectly by v2.

If v2 already wrote new data, disabling a feature flag does not erase it. Flagged paths must remain compatible when OFF and be tested in both ON and OFF states.

### 14.6. Rollback windows and retention

Depending on SLOs, teams might retain v1 for 24–72 hours after releasing v2, though there is no universal fixed window. Retention should cover:
- Delayed jobs, scheduled jobs, and batch ETL.
- Cache TTLs and session lifetimes.
- In-flight requests and queue backlogs.
- Mobile/edge clients still calling v1 APIs.
- Replication lag and backup cycles.
- Daily reports and downstream consumers.
- Recoverability of older secrets and image digests.

Contracting the schema after 30 minutes when background message retries can span a full day is usually far too early.

## 15. Async workloads: queue workers and event contracts

### 15.1. HTTP canaries do not automatically split queue consumers

In Azure Service Bus, if v1 and v2 workers listen on **the same queue**, they compete for messages based on broker dispatch, concurrency/prefetch, and availability. Setting HTTP ingress to 10% **does not mean v2 processes only 10% of messages**.

~~~mermaid
flowchart LR
    SB["Azure Service Bus queue"] --> W1["Worker v1"]
    SB --> W2["Worker v2"]
    W1 --> DB["Shared DB"]
    W2 --> DB
~~~

All active workers must parse every message format present on the queue, or else messages must be partitioned/routed via versioned subscriptions. Otherwise, rolling back the HTTP API still leaves v2 workers causing side effects.

### 15.2. Safe worker transition plan

Options:
- Deploy v2 workers only against a **staging queue/subscription** using synthetic data.
- Use feature flags to gate v2 job-handling branches where frameworks permit.
- Segment workloads using topic subscriptions, filters, or controlled routing topologies.
- Canary by **consumer replica counts** only when dispatch behavior is proven—never equate replica counts with exact traffic percentages.
- Keep both v1 and v2 workers **backward-compatible** with shared event schemas.
- For strict isolation, use dedicated queues and a migration plan.

### 15.3. Message schema versioning

~~~json
{
  "schemaVersion": "1.1",
  "messageId": "invoice-order-123",
  "eventType": "InvoiceRequested",
  "orderId": "demo-123",
  "occurredAtUtc": "2026-11-20T10:00:00Z",
  "payload": {
    "currency": "VND",
    "totalMinorUnits": 125000
  }
}
~~~

Example uses synthetic IDs. Contracts should specify:
- Required vs. optional fields.
- Default values.
- Units and timestamp formats.
- Version migration strategy.
- Whether unknown fields are ignored or rejected.
- DLQ and replay policies.
- Stable idempotency keys.

**Never break v1 workers** by having a v2 producer abruptly rename `eventType` or switch currency units without versioning.

### 15.4. Graceful consumer draining

When rolling back worker v2:
1. Stop accepting **new messages**.
2. Let in-flight jobs complete within an appropriate timeout.
3. Renew or release locks/checkpoints properly per service/client SDK.
4. Never complete/delete a message before its business transaction commits.
5. Re-enable v1 workers or adjust routing per plan.
6. Monitor queue age, DLQ counts, duplicates, and failed side effects.
7. Keep stable handlers compatible with any v2-emitted payloads.
8. Reconcile partially completed jobs.

Azure Service Bus delivery supports retries and redelivery; **tracing does not guarantee exactly-once processing**. Enforce stable message IDs, unique constraints, outbox/saga patterns, or deduplication per business rules.

### 15.5. Long-running jobs and canaries

A 45-minute batch job should not be killed mid-execution just because an HTTP canary failed. Consider:
- Draining before process termination.
- Durable checkpoints.
- Resume/retry semantics.
- Version-compatible persisted state.
- Job-level feature flags.
- Dedicated ownership for rolling back background processing.

**A rollback runbook that only says "shift HTTP traffic 100% back to v1" is incomplete for systems with asynchronous processing.**

## 16. Types of rollback and levels of recovery

### 16.1. Rollback is a family of operations

| Target | Possible action | What is NOT guaranteed |
|---|---|---|
| HTTP traffic | Shift 100% back to stable slot/revision/origin | Reverting DB changes or code config |
| Application binary | Redeploy digest v1 | Erasing external side effects |
| Feature flag | Turn off risky capability | Fixing crashes unrelated to the flag |
| Configuration | Revert app settings / IaC | Making already-rotated secret values valid again |
| Database schema | Forward-compatible migration or planned restore | Zero data loss on point-in-time restore |
| Business data | Compensation / reconciliation | Instant reversal of every transaction |
| Queues / workers | Drain, reroute, restart stable consumers | Exactly-once message handling |
| Network / IAM | Revert firewall / RBAC with approval | Instant token cache or DNS invalidation |
| CDN / cache | Purge or use content-hashed assets | Immediate cache eviction on every client |

### 16.2. Traffic rollback vs. disaster recovery

**Traffic rollback** usually takes seconds or minutes if stable capacity is ready. **Disaster recovery** addresses regional, data, or service loss with dedicated RPO/RTO targets. Never present App Service slot swaps or ACA revision weights as a complete DR solution.

### 16.3. Realistic recovery time

~~~text
Detection time
  + alerting/decision delay
  + authorization/approval
  + traffic rollback execution
  + propagation/draining
  + stable warm-up/capacity
  + verification/reconciliation
  = incident mitigation time
~~~

If stable scaled to zero and pulling its image takes two minutes, a traffic-rollback command finishing in one second **does not mean users recover in one second**.

### 16.4. When to roll back vs. roll forward?

**Roll back** when:
- The prior version remains compatible with data and dependencies.
- Switching traffic/code is faster and lower-risk than hotfixing.
- The regression is clearly tied to the new release.
- No rollback-breaking migration ran.

**Roll forward / fix forward** when:
- A destructive schema migration ran or v2 data is incompatible with v1.
- A mandatory security patch forbids restoring vulnerable v1.
- A bug can be fixed cleanly via safe config or a feature flag.
- Rolling back causes greater impact than a forward fix with approved evidence.
- An external provider changed APIs such that v1 can no longer connect.

Never act on a knee-jerk "always roll back" reflex; weigh incident severity, RTO/RPO, data integrity, and security context.

### 16.5. Minimal rollback runbook

~~~text
Incident identified:
  Release ID / commit / image digest:
  Runtime (App Service / ACA / AKS / Front Door):
  Affected region / tenant / cohort:
  Stable version and availability:
  DB schema compatibility verified:
  Message compatibility verified:
  Current traffic weights:
  Source of truth / GitOps change:
  Approved action:
  Rollback action:
  Verification metrics and time:
  Outstanding in-flight work:
  Data correction / follow-up owner:
  Evidence links / timeline:
~~~

Never record secrets, raw customer payment data, or tokens in incident tickets. Reference Azure resource IDs, trace IDs, and logs under proper access controls.

## 17. Feature flags and kill switches

### 17.1. Why separate code rollout from feature rollout?

A single v2 image may bundle multiple changes:
- A new fee calculation algorithm.
- A new caching mechanism.
- A new email template.

Enabling everything immediately at deployment time means one buggy feature forces rolling back the entire binary. **Feature flags** let you deploy code first, enable behaviors per cohort, and disable them rapidly if needed.

Azure App Configuration Feature Management and compatible flag platforms allow:
- Enabling for QA groups.
- Enabling for 5% of users.
- Enabling for a single tenant/site.
- Using a kill switch to disable a faulty code path.
- Measuring feature impact.

### 17.2. Feature flags do not equal 5% request routing

Assigning a flag to 5% of **users** switches logic inside v2; all requests still execute inside the v2 process. A startup bug or memory leak in v2 affects 100% even when the flag is OFF.

Conversely, App Service routing 5% of requests to Green does not guarantee 5% of users see the feature consistently. Measure both axes separately:

~~~text
Deployment cohort:
  Which binary handles request?

Feature cohort:
  Which behavior executes in that binary?
~~~

### 17.3. Flag evaluation and session consistency

- Use deterministic assignment by approved user/tenant key.
- Never log raw PII in feature flag telemetry.
- Microservices participating in one business transaction must observe consistent flag state.
- Define TTL, refresh, and rollback semantics for flag caches.
- Provide safe fallback defaults if App Configuration is unreachable.
- Audit who toggled each flag and when.
- Clean up stale flags after releases stabilize to limit technical debt.

### 17.4. Security kill switches

A kill switch is effective only if:
- It does not depend on a failing control plane to toggle.
- Emergency change permissions and procedures are tightly governed.
- The OFF path has actually been tested.
- Toggling mid-workflow cannot leave inconsistent writes.
- Observability confirms the switch took effect.
- Admin controls are never exposed to clients.

Do not confuse a "disable payment" flag with revoking a leaked payment token; security incidents still require revocation, rotation, and investigation.

## 18. Software supply chain of a release

### 18.1. Build once, release many

A sound supply-chain pipeline:

~~~mermaid
flowchart LR
    S["Protected Git branch + reviewed PR"] --> C["CI unit/integration tests"]
    C --> SCAN["SAST / SCA / secrets scan"]
    SCAN --> BUILD["Reproducible container build"]
    BUILD --> SBOM["SBOM / provenance / image signing"]
    SBOM --> ACR["Azure Container Registry by digest"]
    ACR --> STAGE["Staging deploy + tests"]
    STAGE --> APPROVE["Approval / policy gate"]
    APPROVE --> CANARY["Canary traffic"]
    CANARY --> PROM["Promote same digest"]
~~~

### 18.2. Image digests matter more than mutable tags

~~~text
Unsafe for identifying a release:
  acrorders.azurecr.io/orders:latest

Explicit identifier:
  acrorders.azurecr.io/orders@sha256:<approved-digest>
~~~

A tag can be repointed depending on registry policy, whereas a digest identifies exact manifest bytes. Pinning digests enables exact rollbacks and provenance checks. Still, a digest alone does not prove safety: combine **trusted build origin, signature verification, vulnerability scanning, and SBOMs** as required.

### 18.3. Azure Container Registry (ACR)

Ensure:
- Registry network reachability from runners and compute nodes.
- Appropriate managed identities or workload identities for pull/push.
- Tightly scoped role assignments per permission model.
- Retention policies protecting digests throughout the rollback window.
- Cleanup policies that never purge active stable images prematurely.
- Image scanning and remediation workflows.
- No hardcoded registry secrets/credentials in pipelines.
- Geo-replication, networking, and egress aligned with region capacity.

**Rollback is impossible if the prior artifact was purged from the registry or the runtime cannot pull it.**

### 18.4. Provenance and attestations

Records may include:
- Commit SHA, build run ID, build-time toolchain.
- SBOM (Software Bill of Materials).
- SCA and secret scan results.
- Artifact/image digest.
- Organizational signatures and attestations.
- Deployment target, environment, and revision/slot.
- Approval record and release decision.
- Canary metrics and correlation IDs.

Never embed token or secret values in attestations. Evidence showing a "signed v2 image" audits artifact origin, yet **does not prove v2 handles the database schema**—compatibility tests are still mandatory.

### 18.5. Pipeline identities

Across GitHub Actions, Azure DevOps, or other runners:
- Prefer **OpenID Connect workload identity federation** with Entra ID where supported.
- Constrain token issuance by repo, branch, environment, and subject.
- Grant least-privilege Azure RBAC strictly to the target resource group, app, or registry.
- Never assign subscription Owner or long-lived service principal secrets just to deploy.
- Enforce protected environments, reviewers, and branch protection.
- Never print Azure login credentials, Key Vault secrets, or SAS tokens in logs.
- Separate CI build/push identities from CD deploy/traffic/promote identities.

A pipeline authorized to update an app image rarely needs rights to reconfigure Key Vault firewalls, drop databases, or assign subscription-wide RBAC.


## 19. CI/CD pipelines: stages, approvals, gates, and promotion

### 19.1. Standard progressive delivery pipeline

~~~mermaid
flowchart TD
    A["Pull request reviewed"] --> B["CI: tests, SCA, SAST, SBOM"]
    B --> C["Build & push immutable digest to ACR"]
    C --> D["Deploy Green to staging"]
    D --> E["Readiness + integration/smoke tests"]
    E --> F{"Security/owner approval"}
    F -->|Fail| STOP["Stop release / preserve stable"]
    F -->|Pass| G["Canary 1%"]
    G --> H{"Metrics gate 1"}
    H -->|Fail| R["Rollback traffic + incident evidence"]
    H -->|Pass| I["Canary 5% → 20% → 50%"]
    I --> J{"Metrics + business gates"}
    J -->|Fail| R
    J -->|Pass| K["Promote 100% / swap"]
    K --> L["Observe + retain stable rollback window"]
    L --> M["Close release / eventual contract"]
~~~

A release is **not complete** the moment a deployment API call returns 200. Pipelines must await readiness, gather live signals, and record gate decisions.

### 19.2. Explicit release states

You can model release states as:

~~~text
CREATED
BUILT_AND_SIGNED
DEPLOYED_GREEN
SMOKE_PASSED
APPROVED
CANARY_1
CANARY_5
CANARY_20
CANARY_50
PROMOTED_100
VERIFIED
COMPLETED

Failure states:
HOLD
ROLLBACK_REQUESTED
ROLLBACK_IN_PROGRESS
ROLLED_BACK
NEEDS_DATA_REPAIR
FAILED
~~~

This is a **reference state machine** for pipelines/release management, not a built-in Azure API enum. Every transition needs an owner, timestamp, inputs, and evidence. If a pipeline restarts between Canary 20% and 50%, **read live traffic weights first** rather than assuming the workflow starts from 0%.

### 19.3. Azure DevOps environments and approvals

In Azure Pipelines:
- **Deployment jobs** bind to an **Environment** to track deployment history and enforce configured approvals/checks.
- **Approvals and checks** are administered on Environments, resources, and service connections—not via a single YAML line.
- Branch control, required templates, business hours, Azure Monitor alert checks, and REST checks can be applied per platform support.
- CI builds and tests; CD consumes published artifacts/fixed digests.
- Production service connections hold least-privilege permissions.

Abbreviated YAML example for **one routing step in an approved lab**:

~~~yaml
trigger: none

variables:
  resourceGroup: rg-orders-lab
  appName: app-orders-lab

stages:
  - stage: Canary10
    displayName: Canary 10 percent in approved lab
    jobs:
      - deployment: RouteCanary
        environment: orders-lab-approval
        strategy:
          runOnce:
            deploy:
              steps:
                - task: AzureCLI@2
                  inputs:
                    azureSubscription: sc-orders-lab-federated
                    scriptType: bash
                    scriptLocation: inlineScript
                    inlineScript: |
                      az webapp traffic-routing set \
                        --resource-group "$(resourceGroup)" \
                        --name "$(appName)" \
                        --distribution staging=10
~~~

**This YAML illustrates a single deployment job, not a full production pipeline.** It omits build/test, read-before-write checks, traffic verification, KQL gates, and rollback logic. Approvals occur only if Environment **orders-lab-approval** actually has Approvals and checks configured. Never copy dummy service connection names into production pipelines.

### 19.4. GitHub Actions protected environments

A GitHub Actions workflow can:
1. Build and sign artifacts in a job holding no production credentials.
2. Publish digest + SBOM.
3. Deploy to staging using a scoped OIDC identity.
4. Run smoke and integration tests.
5. Target a job with `environment: production` enforcing configured protection rules.
6. Authenticate to Azure via OIDC with minimal `id-token: write` and `contents: read`.
7. Start the first canary stage.
8. Query metric gates and require additional approvals before large increments.
9. Promote or roll back.
10. Record audit trails: run ID, commit, digest, and outcome.

**`environment: production` alone does not enforce approvals** unless required reviewers and branch restrictions are configured on the repository/environment. Never store long-lived client secrets in GitHub Actions secrets when workload identity federation is supported.

### 19.5. Separation of duties

- Developers review code and tests.
- Platform teams manage release tooling and routing.
- Security teams/automation verify image signing, SBOMs, and vulnerability policies.
- Product/business owners approve financially impactful changes.
- SRE/on-call operators monitor canaries and hold rollback authority per incident policy.
- Database owners approve destructive migrations or restores.

Never force one individual to hold subscription Owner just to run a canary. Equally, never design an approval chain slower than your committed RTO for critical rollbacks; **emergency rollback permissions** must be pre-authorized and audited.

### 19.6. Pipeline idempotency

An unintended rerun could:
- Deploy a different revision due to a mutable image tag.
- Swap slots twice, silently reverting back to the old version.
- Jump traffic from 10% to 50% without passing a gate.
- Apply a migration twice.
- Purge a stable image before the rollback window closes.

Each stage should therefore:
1. Read current live state.
2. Verify expected source and target releases.
3. Check target readiness and configuration.
4. Apply an idempotent desired change or fail-safe HOLD.
5. Read back actual state.
6. Record audit evidence.
7. Advance only when gates pass.

**Slot swap is stateful; running swap twice is not idempotent.**

## 20. Automated metric gates and KQL

### 20.1. Tag telemetry with release/version

Comparing v1 and v2 requires:
- Consistent `AppRoleName` per service.
- Deployment version/digest attributes or `CustomDimensions`/`Properties`.
- Slot/revision-specific tagging or separate App Insights resources.
- Matching time windows and region/tenant segmentation.
- Adequate sample counts.
- Explicit handling for missing telemetry.

If both v1 and v2 emit identical `AppRoleName` values with no version attribute, aggregate KQL cannot drive safe canary decisions.

### 20.2. Example KQL using app-emitted version attributes

Assuming instrumentation attaches `deployment.release` to `AppRequests`:

~~~kusto
let windowStart = ago(15m);
AppRequests
| where TimeGenerated >= windowStart
| where AppRoleName == "orders-api"
| extend Release = tostring(Properties["deployment.release"])
| where Release in ("v1", "v2")
| extend Is5xx = toint(ResultCode) between (500 .. 599)
| summarize
    Requests = sum(ItemCount),
    Errors5xx = sumif(ItemCount, Is5xx),
    P95Ms = percentile(DurationMs, 95)
  by Release, bin(TimeGenerated, 5m)
| extend ErrorRate5xx =
    iff(Requests > 0, todouble(Errors5xx) / Requests, real(null))
| order by TimeGenerated asc, Release asc
~~~

**This query is illustrative**: the `deployment.release` property must be emitted accurately per schema; `AppRequests` uses the dynamic `Properties` column in workspace-based Application Insights depending on configuration. `ItemCount` can reflect sampling weights. Percentiles over sampled rows are not automatically weighted; for high-confidence automated SLO gates, use statistically sound metrics/sources and test against real data.

### 20.3. Comparing errors across releases without a version property

If stable and canary telemetry live in separate App Insights resources/workspaces and cross-resource queries are permitted, compute metrics per resource and join afterward. On Azure Container Apps, combine revision-specific metrics and logs.

Never assume "v2 receives 10% of traffic, so attribute 10% of total errors to v2"—errors rarely distribute uniformly.

### 20.4. Sampling considerations

- Application Insights sampling may omit individual requests.
- Some queries use `sum(ItemCount)` to estimate volume across sampling weights.
- Sampled p95 carries higher variance on small canaries.
- Unequal sampling rates between stable and canary skew raw count comparisons.
- Ingress/app metrics often provide cleaner SLI denominators across 100% of traffic.
- Traces excel at diagnosing individual errors, not always as full SLO denominators.

### 20.5. Gate decision algorithm

~~~text
Input:
  canaryRelease
  stableRelease
  window = last 15 minutes
  minRequests = 500

if telemetry unavailable or stale:
    HOLD; notify owner
elif canaryRequests < minRequests:
    HOLD; extend observation
elif criticalDataIntegrityIncident or securityCritical:
    ROLLBACK immediately
elif canary5xxRate > absoluteThreshold:
    ROLLBACK
elif canary5xxRate > stable5xxRate + allowedDelta:
    ROLLBACK
elif canaryP95 > stableP95 * allowedRatio:
    HOLD or ROLLBACK per severity
elif queueDLQSpike or businessConversionCrash:
    HOLD + investigate / ROLLBACK
else:
    PASS; eligible for next stage
~~~

This is **policy pseudocode**, not a built-in Azure DevOps task. Production implementations must verify query permissions, cardinality, time windows, saturation, and false-positive handling.

### 20.6. Avoiding race conditions during auto-rollback

An auto-rollback controller may collide with an operator promoting manually. Prevent this with:
- A **single release owner/controller** or lease/lock.
- Compare-and-set checks against expected current release/traffic weights.
- Idempotent rollback desired states.
- Centralized audit and incident state.
- Pause/resume mechanisms requiring approval.
- Platform atomicity where supported, or readback verification otherwise.
- Blocking CI promotion jobs from re-pushing v2 right after an auto-rollback.

**An auto-rollback system paired with a pipeline that keeps redeploying the broken version creates an outage loop.**

## 21. Stage-by-stage operational workflow

### 21.1. Pre-deployment

- Verify artifact digest, signature, SBOM, and security scan results.
- Verify release manifest covers version/config/schema compatibility matrix.
- Check production baseline metrics and active incidents.
- Verify stable runtime health, rollback capacity, and retained image.
- Confirm expand DB migrations are applied/approved.
- Check queues, secret expirations, managed identities, and networking.
- Confirm smoke tests will not create real payments or orders.
- Confirm approvers and on-call support availability.
- Confirm canary routing controller health and telemetry version tagging.

### 21.2. Deployment and warm-up

1. Deploy Green/canary digest to staging slot, revision, or Deployment.
2. Wait for startup, readiness, and health checks.
3. Warm caches and connection pools.
4. Probe protected internal, label, or slot URLs.
5. Verify auth, DB reads, and sandbox storage/queue integrations.
6. Confirm logs show no secrets, policy denials, or TLS errors.
7. Mark `DEPLOYED_GREEN` and record artifact ID and UTC timestamp.

### 21.3. Progressive canary rings

Example:
- Ring 1: 1% or internal allowlist.
- Ring 2: 5% with adequate sample size.
- Ring 3: 20% watching load and queue metrics.
- Ring 4: 50% approaching production scale.
- Ring 5: 100% under close observation.

Between rings:
- Record realized routing weights.
- Wait out the full hold window.
- Check HTTP errors, latency, and business invariants.
- Compare against stable baselines per region/tenant.
- Verify telemetry freshness.
- Approve progression or trigger automated rollback per policy.
- Record which person or system made each decision.

### 21.4. After reaching 100%

- Do not delete Blue/stable prematurely.
- Continue watching batch jobs, cron tasks, and queues.
- Retain v1 images and compatible configs across the rollback window.
- Monitor exceptions, CPU, DB, and queues by release.
- Verify migration backfill/dual-write behavior.
- Contract schemas only once owners confirm no rollback is needed.
- Update release audits, cost tracking, and post-release notes.

**Reaching 100% traffic does not end rollback readiness obligations.**

## 22. What level of automation fits best?

### 22.1. Manual blue-green

Fits:
- Infrequent, high-risk releases.
- Workloads lacking version-segmented telemetry.
- Releases needing explicit DBA or business sign-off.
- Teams needing strict cutover timing control.

Requirements: detailed runbooks, scripted operator commands to prevent typos, readback checks, and blast-radius controls.

### 22.2. Semi-automated canary

- Pipeline automatically deploys and shifts 1–5%.
- Automated alerts/gates evaluate metrics.
- Human approval gates 20% or 100%.
- Auto-rollback triggers on critical conditions.
- Manual review checks data and business anomalies.

Fits teams that already have observability in place but lack historical data to calibrate fully automated thresholds.

### 22.3. Fully automated progressive delivery

Suitable with Azure Pipelines, GitHub Actions, dedicated controllers/operators, or GitOps automation when you have:
- High-quality version-aware telemetry.
- Concurrency and locking.
- Fail-safe HOLD on missing data.
- Verified rollbacks and business compatibility.
- Anomaly detection and human override controls.
- Audit evidence and approval compliance.
- Bounded cost and scope.
- Regular staging fault-injection and rollback drills.

Do not assume Azure Pipelines performs SLO-based canaries automatically just by naming a stage "Canary"; metric evaluation and traffic shifting require real scripts, tasks, or controllers.

### 22.4. Progressive delivery and GitOps on AKS

In the GitOps (Flux/Argo CD) model:
- Git holds desired image digests and Deployment/Service/HTTPRoute/VirtualService manifests.
- Pipelines update release manifests via reviewed PRs.
- In-cluster controllers reconcile desired state.
- Rollbacks must update the **Git source of truth**.
- Avoid ad-hoc `kubectl patch` fixes that GitOps will overwrite.
- GitOps-compatible progressive delivery controllers can perform metric analysis, provided versions, ownership, and support are verified.

**"`kubectl rollout undo` passed" while GitOps still points to v2 is an incomplete rollback.**


## 23. Lab: canary and rollback on Azure Container Apps

### 23.1. Lab objectives

Using an **existing lab Container App** with HTTP ingress, a stable revision, and a new revision, learners will:

1. Inspect current state and permissions.
2. Verify both revisions are active and healthy.
3. Shift 5% of traffic to Green.
4. Run safe smoke/load tests.
5. Compare metrics by version.
6. Simulate a failing metric gate using test data.
7. Route 100% of traffic back to Stable.
8. Verify live state and record audit logs.
9. Preserve evidence and avoid deleting Stable before the rollback window closes.

### 23.2. Prerequisites

- Dedicated **lab subscription/resource group** and budget.
- Container Apps environment + an HTTP ingress app.
- Two revisions deployed from explicit digests.
- App never calls production payment, email, or database systems.
- Matching Azure CLI `containerapp` extension and operator permissions.
- Revision metrics/logs or a version response header available in the lab.
- Rollback command tested prior to the drill.

### 23.3. Read-only state discovery

~~~bash
RG="rg-orders-lab"
APP="ca-orders-lab"

az account show --query "{subscription:id,name:name}" -o json

az containerapp show -g "$RG" -n "$APP" \
  --query "{mode:properties.configuration.activeRevisionsMode,traffic:properties.configuration.ingress.traffic}" \
  -o json

az containerapp revision list -g "$RG" -n "$APP" -o table
~~~

Record **exact revision names**, active/healthy status, and current traffic weights before testing. Never assume a newly deployed revision automatically receives 5% of traffic.

### 23.4. Setting 95/5 after approval

~~~bash
STABLE="<exact-stable-revision>"
GREEN="<exact-green-revision>"

# Run only in lab after preflight checks and approval.
az containerapp revision set-mode -g "$RG" -n "$APP" \
  --mode multiple

az containerapp ingress traffic set -g "$RG" -n "$APP" \
  --revision-weight "$STABLE=95" "$GREEN=5"

# Read back actual traffic split:
az containerapp show -g "$RG" -n "$APP" \
  --query "properties.configuration.ingress.traffic" -o json
~~~

If Green is not active and healthy, **do not shift traffic**. During testing, avoid sending just 10 requests from one browser cookie; tiny samples and sticky sessions produce misleading distributions.

### 23.5. Smoke tests

Define lab endpoints:

~~~text
GET /ready
  → HTTP 200 when readiness passes

GET /version
  → JSON {"release":"v1"|"v2","healthy":true}

POST /orders/dry-run
  → never writes production DB, never calls real payment/queue
  → returns 200 or 202 per lab contract
~~~

These routes are **defined by the test application**, not built-in Container Apps endpoints. If your app lacks them, use equivalent safe API tests with zero side effects.

### 23.6. Intentionally failing a canary gate in the lab

In **staging**, enable a test feature flag causing Green to return 503 for allowlisted synthetic requests. Never enable fault injection on public production endpoints.

Next:
- Measure Green's 5xx rate by revision/version.
- Confirm Stable remains unaffected.
- Observe metrics, logs, and ingestion delay.
- Mark **HOLD/ROLLBACK_REQUESTED** with evidence.
- Execute rollback per runbook.

### 23.7. Rolling back to stable

~~~bash
az containerapp ingress traffic set -g "$RG" -n "$APP" \
  --revision-weight "$STABLE=100" "$GREEN=0"

az containerapp show -g "$RG" -n "$APP" \
  --query "properties.configuration.ingress.traffic" -o json
~~~

Verify:
- Live telemetry confirms traffic returned to Stable.
- Stable has sufficient replicas and capacity.
- In-flight requests drain cleanly.
- HTTP errors return to baseline.
- Queues and workers remain healthy.
- Forensic logs and metrics remain preserved.

Never treat exit code 0 as proof of recovery; **verify live user-facing health**.

### 23.8. Controlled cleanup

- Turn off the synthetic fault flag.
- Retain Green logs and evidence for postmortem.
- Deactivate/clean up revisions under approval and retention policies.
- Never delete a shared Container App or resource group.
- Log replica counts, traffic, and storage/logging costs from the drill.
- If you hold read-only permissions, stop after step 23.3 without mutating traffic.

## 24. Lab: blue-green on App Service and swap rollback

### 24.1. Prerequisites

- App Service plan supporting deployment slots.
- Production Blue slot and staging Green slot with clear artifact IDs.
- Slot-specific settings, managed identities, and networking verified.
- Smoke tests do not corrupt databases or queues.
- Green warmed up via slot URL or compatible preview mechanism.
- Approval, monitoring, and recovery plan in place.

### 24.2. Recording pre-swap evidence

~~~text
App Service resource ID:
Production slot release digest:
Staging slot release digest:
Production configuration fingerprint (redacted):
Staging slot-specific settings verified:
Database schema / compatibility:
Warm-up and readiness status:
Azure Monitor alert state:
App Service plan capacity:
Release approval ID:
~~~

Never record actual passwords or access tokens. If any critical field is missing, **HOLD**.

### 24.3. Controlled swap execution

~~~bash
RG="rg-orders-lab"
APP="app-orders-lab"

az webapp deployment slot list \
  --resource-group "$RG" \
  --name "$APP" \
  -o table

# Run only after smoke tests, compatibility checks, and approval:
az webapp deployment slot swap \
  --resource-group "$RG" \
  --name "$APP" \
  --slot staging \
  --target-slot production
~~~

If using **swap with preview**, follow exact feature support and commands for your app type; never execute a regular swap while a preview swap is pending.

### 24.4. Post-swap verification

- Production hostname returns the expected release ID via a sanitized endpoint.
- App Insights p95/5xx show no regression.
- Slot/sticky settings and Key Vault identities remain intact.
- DB migrations are backward-compatible.
- No Service Bus or Blob config errors appear.
- Staging still holds a rollback-capable stable version.
- Traffic routing state (if previously used) is clearly understood.

On failure, inspect both slots first, then swap back per Section 7.8 or redeploy stable per plan. Never swap twice blindly without checking state between swaps.

### 24.5. Key lessons

- Warm-up reduces cold starts, but does not replace SLO gates.
- Destructive DB migrations break rollbacks.
- `GET /` smoke tests miss Storage/Key Vault permission bugs.
- Sticky cookies skew traffic tests.
- Retain artifacts and stable slots long enough.
- Post-swap readback is just as important as the swap command itself.
- Operators need pre-authorized rollback rights matching committed RTO.


## 25. Pre-production testing and fault injection

### 25.1. Testing matrix

| Scenario | How to test in staging/lab | Pass condition |
|---|---|---|
| Green starts slowly | Inject realistic startup delay | Readiness prevents premature traffic |
| Green fails liveness | Controlled process crash | Router/controller removes unhealthy target |
| Green returns 503 | Inject fault on test cohort | Metric gate triggers rollback |
| Green p95 doubles Stable | Inject artificial latency | Hold/rollback fires per threshold |
| Low 1% canary traffic | Limit test volume | No-data/insufficient samples → HOLD |
| Azure Monitor unavailable | Disconnect lab exporter | No auto-promote without telemetry |
| Traffic cutover | 95/5 → 50/50 → 100/0 | Realized distribution measured |
| Traffic rollback | 10% → 0% | Stable handles returning traffic |
| Blue not ready | Constrain stable capacity | Block promote when rollback path is unready |
| Database expand migration | Add nullable column | Both v1 and v2 read/write cleanly |
| Destructive DB change | Flag incompatible migration | Pipeline blocks release before cutover |
| Secret rotation | Rotate test token in Key Vault | Both revisions use valid credentials |
| HTTP session affinity | Browser with cookies | Session flows stay intact |
| Service Bus worker v2 | Send v1/v2 test schemas | Workers process cleanly; zero DLQ spike |
| Worker graceful stop | Terminate mid-job | Zero lost messages or duplicate side effects |
| Front Door cache | Check `Cache-Control`/headers | No data leaks, no masking canary |
| GitOps reconcile | Manual patch followed by reconcile | Desired rollback state converges |
| Old ACR image missing | Simulate missing digest in lab | Rollback preflight catches gap |
| Pipeline rerun | Replay same release state | No accidental double-swap or un-gated promote |
| Region failover | Take lab origin/region offline | Failover is not mistaken for canary pass |

### 25.2. Segment test traffic realistically

If production serves:
- 60% mobile users.
- 30% desktop/tablet.
- 10% API integrations.
- 2% high-volume enterprise tenants (potentially overlapping above groups).

Canaries should validate **cohort representation** or use dedicated test rings for high-risk flows. Random 1% traffic might miss legacy enterprise protocols or end-of-month transactions.

Never dilute SLO denominators with 100%-passing synthetic requests to mask real failures; tag and separate synthetic traffic from user-facing traffic.

### 25.3. Data integrity tests

A release can return HTTP 200 while:
- Writing duplicate orders.
- Miscalculating taxes or currency units.
- Sending duplicate invoices.
- Silently dropping queue messages.
- Writing incompatible Blob schemas.
- Breaking tenant isolation.

Canaries need business assertions:
- Unique idempotency keys.
- Referential integrity.
- Zero duplicate payment captures.
- Orders accepted vs. persisted reconciled per window.
- Service Bus sent, processed, and DLQ counts verified.
- Schema versions valid for both stable and green.
- Zero cross-tenant PII leakage.

**Low HTTP error rates are necessary, never sufficient for data-critical releases.**

### 25.4. Network and managed identity tests

- Does Green have DNS/Private Endpoint reachability to Azure SQL, Storage, and Key Vault?
- Does the Container Apps revision hold ACR pull permissions?
- Are AKS workload identity annotations and ServiceAccounts right?
- Does the App Service slot hold valid identities and slot-specific settings?
- Are Front Door origin TLS, host headers, and WAF compatible?
- Do CI runners deploy with least privilege without subscription Owner?
- Does token refresh succeed after expiration?
- When reverting to Blue, are rotated credentials still accepted?

Never fix a canary 403 by opening public networking or granting Administrator roles indiscriminately.

### 25.5. Acceptance criteria for a rollback drill

~~~text
Canary release intentionally fails in isolated lab.
Alert/gate detects issue within target window.
Pipeline/orchestrator stops promotion.
Traffic returns to healthy stable release.
Readback confirms routing state.
User-facing error rate returns to baseline.
In-flight jobs and DB records are reconciled.
No unauthorized manual changes remain.
Evidence and UTC timeline are preserved.
Operator can explain what was and was not rolled back.
~~~

If a drill runs a single `traffic set` command without verifying user-facing recovery, the rollback exercise is incomplete.

## 26. Security, governance, and blast radius

### 26.1. Least-privilege permissions

| Principal | Needed permissions | Should NOT hold by default |
|---|---|---|
| CI build identity | Pull source, push images to ACR | Production slot swap |
| CD deploy identity | Deploy revision/slot in target scope | Subscription Owner |
| Traffic controller | Update routing/weights on target app | Key Vault Administrator |
| Runtime managed identity | Read needed secrets and data resources | Modify resource group IAM |
| On-call rollback operator | Route traffic to stable per runbook | Delete databases or registries |
| DB migration identity | Run approved schema operations | Unnecessary global DB admin |
| Auditor/observer | View logs, metrics, deployment history | Secret values or prod mutations |

Inspect exact Azure RBAC role definitions, actions, and scopes per resource; never assume one generic role name covers traffic routing across every service.

### 26.2. Isolate preview/staging from production impact

- Staging slots and preview URLs may be Internet-reachable if left unprotected.
- Test routes must not bypass WAF or authentication.
- Test accounts and synthetic payments must follow strict policies.
- Never use production payment tokens for synthetic transactions.
- Restrict preview/green access via test IP allowlists, VNet, or authentication.
- Monitor access to staging hostnames and label URLs.
- Never print Azure credentials or connection strings in pipeline logs.

### 26.3. Supply-chain compromise risks

A canary receiving 1% of traffic can still read **the entire database or Key Vault** if its runtime identity is over-privileged. **1% canary traffic does not mean a 1% security blast radius.**

Enforce:
- Image signature and provenance verification.
- Least-privilege runtime identities.
- NetworkPolicies and private endpoints.
- Egress controls.
- Secret scanning, SAST/SCA, and vulnerability policies.
- Protected runners and service connections.
- Audits of anyone able to override gates or approvals.
- Stable image retention and rollback integrity checks.

### 26.4. IaC and configuration drift

Whenever operators patch traffic weights or Service selectors directly:
- Reconcile and update the Terraform/Bicep/ARM/GitOps source of truth.
- Enable drift detection where feasible.
- Separate emergency rollbacks from routine config edits.
- Prevent auto-deploy from immediately re-pushing the broken version.
- Record live state after all automation runs.
- Keep release histories clear.

Bicep/Terraform can manage apps and ingress, yet **may be ill-suited as the step-by-step controller for 1% canary increments** if plan/apply produces side effects; maintain one consistent routing owner.

### 26.5. Compliance and audit

Release evidence should include:
- Artifact digest, commit, SBOM/signature references.
- Impacted subscription, resource group, and region.
- Environment, tenant, and deployment rings.
- Approval IDs and UTC timestamps.
- Migration/schema versions and backup evidence.
- Before/after traffic weights.
- Redacted metric/KQL evidence.
- Rollback verification and owners.
- Business verification and incident actions.
- Cleanup and schema-contract authorization.

Never include JWTs, PII, SAS tokens, or payment details in reports merely to document a rollback.


## 27. Capacity planning, costs, and limits of blue-green

### 27.1. Blue-green can double compute demand

Suppose Blue on AKS runs 6 Pods, each requesting 0.5 vCPU and 1 GiB memory. Running Green identically before cutover:

~~~text
Blue capacity reservations:
  6 pods × 0.5 vCPU = 3 vCPU
  6 pods × 1 GiB = 6 GiB memory

Green capacity reservations:
  6 pods × 0.5 vCPU = 3 vCPU
  6 pods × 1 GiB = 6 GiB memory

During overlapping window:
  6 vCPU and 12 GiB requested
  before system pods, overhead, failover capacity
~~~

These are **Pod requests/reservations**, not the AKS bill; actual cost depends on VM/node SKUs, autoscalers, utilization, region, networking, storage, and billing terms. Confirm cluster headroom or autoscaling before starting a canary.

### 27.2. A 1% canary does not cost 1%

A warmed Green deployment with 4 replicas handling 1% traffic still consumes:
- CPU/memory for app processes.
- Sidecar/agent overhead.
- Connection pools and database connections.
- Logs, metrics, and traces.
- Image storage and registry egress.
- Cache memory.
- Load balancer / gateway / Front Door charges.

In Container Apps, costs depend on resource profiles, consumption vs. dedicated plans, active replicas, requests, and scale rules; calculate against your actual billing model. On App Service slots sharing one plan, a new slot can cause **resource contention** even without an extra plan charge.

### 27.3. Cost components

~~~text
Progressive delivery total cost =
    Stable compute
  + Green/canary compute during overlap
  + Extra gateway/routing/Front Door costs
  + Database and cache load from both versions
  + Registry image storage and artifact retention
  + Azure Monitor/Log Analytics ingestion/retention
  + CI/CD runner/build minutes and artifact scans
  + Migration/backfill jobs
  + Synthetic/load tests
  + Incident/approval operations
~~~

Do not optimize by deleting Blue immediately after promotion if rollback risk is high. Choosing how long to keep Stable balances **recovery readiness** against cost.

### 27.4. Optimization levers

- Warm Green minimally to meet readiness/SLOs rather than over-provisioning before traffic arrives.
- Measure real CPU/memory/connection pools and use autoscalers where supported.
- Limit concurrent overlapping release candidates.
- Align image retention with rollback windows instead of retaining every build forever.
- Tune tracing, sampling, and log retention.
- Avoid unnecessary cross-region origins when business does not need them.
- Batch migrations/backfills to avoid forcing excessive DB scaling.
- Schedule releases around traffic mixes and on-call coverage.
- Automate deactivation/cleanup once hold windows close with approval.

### 27.5. Cost metrics to monitor

| Metric | Meaning |
|---|---|
| Extra compute-hours per release | Cost of parallel overlap |
| Mean rollback time | Return on standby capacity |
| Failed-release incidents | Release quality |
| Percentage of canaries auto-rolled back | Gate and code quality |
| App Insights GB ingested per release | Observability budget |
| Deployment frequency vs. rollback frequency | Balance of velocity and reliability |
| Retained registry/artifact storage | Supply-chain and recovery footprint |
| DB/network spend during migrations | Data-plane change cost |
| Customer-visible failed requests | Real business impact cost |
| Time spent in HOLD | Telemetry/sample sufficiency |

Total cost of ownership extends beyond a few minutes of extra Pod runtime; a botched rollback causing data loss costs orders of magnitude more than keeping Green on standby.

## 28. Troubleshooting and runbooks

### 28.1. Symptom table

| Symptom | Common cause | Action |
|---|---|---|
| Staging slot missing | App Service plan unsupported or slot uncreated | Check SKU and slot list |
| Slot swap fails | Warm-up, config, or permissions | Check swap diagnostics and sticky settings |
| 10% traffic routing shows no Green hits | Cookie affinity, low volume, route unapplied | Check slot metrics, cookies, and raw requests |
| Swap rollback fails to restore Blue | Blue overwritten or config drifted | Inspect slot digests and backups |
| ACA revision gets zero traffic | Single mode, inactive, or unhealthy revision | Inspect `activeRevisionsMode`/status and probes |
| ACA weights mismatch expectations | Wrong revision names or ingress config | Read back live traffic config |
| AKS rollout hangs | Readiness, image pull, quota, or pending Pods | `kubectl describe`/events, check ACR |
| `kubectl undo` gets overwritten | GitOps still targets v2 | Revert Git source of truth |
| AKS canary does not split 90/10 | Missing route controller or mesh support | Check Gateway API/Istio status and mesh participation |
| 502s right after Service selector rollback | Connection draining or unsynced endpoints | Check readiness, EndpointSlices, and ingress |
| Front Door Green receives zero traffic | Priority, health probe, route, or caching | Inspect origins and access logs |
| 5% traffic breaks 50% of users | Session affinity or tenant skew | Analyze cohort and user distribution |
| Stable slows down when Green fails | Shared compute, database, or registry | Scale/isolate resources and check quotas |
| Database fails after rollback | Destructive migration | Execute DB recovery or forward fix |
| Worker v1 fails on v2 messages | Incompatible event schema | Enforce versioned contracts and DLQ runbooks |
| Traffic = 0 yet v2 requests continue | In-flight requests, sticky sessions, background jobs | Drain and observe before deleting |
| Alerts stay silent | Telemetry ingestion delay or sampling | Fail-safe HOLD; check exporter health |
| Auto-rollback loops / redeploys broken v2 | Two controllers or GitOps conflict | Enforce release locks and desired state |
| New release loses Key Vault access | Changed identity, slot, revision, or IAM | Check data-plane roles and networking |
| ACR pull fails on rollback | Digest purged or registry denied | Retain artifacts and fix identity |
| Log costs spike sharply | Duplicate telemetry or higher volume | Adjust sampling, tags, and cost breakdown |
| HTTPS health probe green while checkout fails | Probe too shallow | Add business canary tests and critical metrics |
| Front Door cache hides v2 from users | Stale cached responses | Fix cache policy and content hashing |
| Pipeline shows success while users see errors | Checked only command exit code | Add post-deploy metrics and business gates |

### 28.2. Runbook A: canary 5xx spike

1. Record release ID, UTC timestamp, platform, canary weights, and impacted cohort.
2. Calculate 5xx rates **per version** (never aggregate totals).
3. Check request volume and telemetry ingestion delay.
4. Classify severity: data-integrity or security issues override sample-wait timers.
5. **HOLD** all further promotion steps.
6. When rollback criteria trigger, route 100% of traffic back to Stable.
7. Read back traffic weights, Service selectors, or Front Door origins.
8. Verify Stable readiness, capacity, and error-rate recovery.
9. Audit in-flight/background jobs and any corrupted writes from Green.
10. Preserve traces, logs, and evidence; build an incident timeline—never redeploy the broken build.

### 28.3. Runbook B: blocked rollback due to database

1. Halt further promotion and any pending migrations.
2. Identify migration version and affected tables/rows.
3. Check whether v1 remains compatible with the current schema.
4. If compatible, roll back traffic per plan and verify.
5. If incompatible, **never force v1 into production** knowing it will fail.
6. Coordinate with DBAs on a forward fix, restore, or compensation.
7. Verify backups, RPO/RTO, replication, and recent writes.
8. Obtain approvals for schema/data fixes.
9. Test read/write compatibility for both stable and target versions safely.
10. After recovery, strengthen expand–contract gates and migration pipelines.

### 28.4. Runbook C: GitOps reverts a manual rollback

1. Identify Flux, Argo CD, or the reconciling controller.
2. Pause promotion automation to stop pushing the broken release.
3. Record live state alongside Git desired state.
4. Commit a revert of the image digest, HTTPRoute, or Service selector back to Stable.
5. Review and merge under emergency policy.
6. Monitor reconciliation and controller status.
7. Verify live traffic and Pods—never stop at the Git commit.
8. Confirm release locks/automation stopped retrying v2.
9. Resume CI/CD once root cause is resolved.
10. Record audit trail and lessons learned.

### 28.5. Runbook D: App Service swap fails after 100%

1. Confirm whether production runs Green or Blue via release ID.
2. Confirm staging still holds a rollback-eligible Blue artifact.
3. Check slot settings, identities, and DB compatibility.
4. If verified, swap back under approval/incident policy.
5. Read back slot versions and the production hostname.
6. Verify routing cookies and traffic splits are not pointing to staging.
7. Compare p95, error rates, and Key Vault/DB errors.
8. Check queues and in-flight work.
9. If staging was overwritten, redeploy the approved stable digest instead of swapping blindly.
10. Document root cause and strengthen pre-swap state checks.

### 28.6. Runbook E: missing telemetry

1. Block promotion; **no data ≠ healthy**.
2. Check version tagging and Cloud Role Name.
3. Check App Insights connection string and Log Analytics permissions.
4. Check sampling, ingestion delay, and query time windows.
5. Check exporter egress, DNS, TLS, and proxies.
6. Check 429/5xx throttling and dropped telemetry.
7. Cross-check independent ingress/gateway/platform metrics where available.
8. If evidence remains missing, HOLD the release and fix monitoring.
9. Never disable all logging security controls just to view raw payloads.
10. Rehearse the metric gate in staging after remediation.

### 28.7. Runbook F: rollback succeeded but side effects remain

1. Identify the exact UTC window during which Green served traffic.
2. List affected operation IDs and records via authorized queries.
3. Reconcile orders accepted vs. persisted vs. charged.
4. Inspect Service Bus deliveries, DLQs, and worker retries.
5. Never bulk-delete records just because "they came from v2."
6. Execute business-approved idempotent reconciliation or compensation.
7. Verify zero duplicate payments or invoices.
8. Report incidents per organizational policy and legal requirements.
9. Maintain audit trails with PII redaction.
10. Close the incident only once data correctness is confirmed.

## 29. Case study: shipping-fee outage on orders

### 29.1. Architecture

An enterprise runs:
- Spring Boot Orders API on Azure Container Apps.
- Pricing API on AKS.
- Azure SQL Database storing orders.
- Azure Service Bus feeding an Invoice Worker.
- Azure Blob Storage storing invoices.
- Azure Key Vault managing partner API tokens.
- Azure Container Registry storing image digests.
- Azure Monitor Application Insights and Log Analytics.
- Azure DevOps with Environment approvals.

~~~mermaid
flowchart TD
    U["Users"] --> ING["Container Apps ingress"]
    ING -->|"95%"| BLUE["Orders stable v1"]
    ING -->|"5%"| GREEN["Orders canary v2"]
    BLUE --> P["Pricing API AKS"]
    GREEN --> P
    BLUE --> SQL["Azure SQL"]
    GREEN --> SQL
    BLUE --> SB["Service Bus"]
    GREEN --> SB
    SB --> W["Invoice Worker"]
    W --> B["Blob Storage"]
    BLUE -. "Telemetry" .-> M["Application Insights"]
    GREEN -. "Telemetry" .-> M
~~~

### 29.2. Pre-canary state

- CI built image v2 and SBOM; digest verified.
- DB migration used **expand** only, adding nullable `ShippingRuleVersion`.
- Worker v1 reads both v1 and v2 messages.
- Green passed smoke tests with synthetic orders.
- Stable v1 retains 6 ready replicas.
- Telemetry carries `v1`/`v2` release tags.
- Rollback permissions and metric gates are active in the pipeline.
- Cost and hold window approved.

### 29.3. Traffic and signals

Suppose total traffic averages **6,000 requests/minute** with an approximate 95/5 split:

~~~text
Canary v2:
  ~300 requests/min × 15 min = 4,500 requests
  5xx rate = 2.0% → 90 errors

Stable v1:
  ~5,700 requests/min × 15 min = 85,500 requests
  5xx rate = 0.2% → 171 errors

Relative rate:
  Canary 2.0% vs Stable 0.2% = 10× error rate
~~~

Although Stable shows more **absolute** failed requests, the canary is drastically worse by **error rate**. This simplified calculation assumes production also checks confidence intervals, per-route/cohort slices, time windows, and sampling. The root bug: v2 fails to parse one postal code format, throwing exceptions during shipping calculation.

### 29.4. Decision

- Canary exceeded 500 requests.
- Canary 5xx breached the 1% absolute threshold.
- Canary exceeded Stable by more than +0.5 percentage points.
- Business error logs confirm checkout failures.
- No rollback-breaking migration occurred.
- Stable capacity is healthy.

Decision: **ROLL BACK traffic immediately** to v1, then investigate root cause. Never ramp to 20% just to "gather more data."

### 29.5. Execution

In the release controller:
1. Halt the promotion pipeline.
2. Set traffic weights to Stable 100% / Canary 0%.
3. Read back ingress configuration.
4. Confirm App Insights and ingress metrics return to baseline.
5. Check Green-created orders for duplicate or partial writes.
6. Inspect Service Bus DLQ and invoice worker behavior.
7. Retain Green image + logs and open an incident with trace IDs.
8. Fix validation logic in a new commit.
9. Build artifact v3, run CI/tests, and start a **fresh** approved canary.
10. Contract the DB schema only after rollback is no longer needed.

### 29.6. What if v2 had dropped a DB column?

Completely different outcome: if Green's migration dropped `Status` which v1 needs, **never shift 100% traffic back to v1 before restoring schema compatibility**. Work with DBAs on recovery or a forward fix accounting for newly written rows. This is why migration/rollback preflight checks must precede the very first canary percent.

### 29.7. Success criteria

- Incident caught before 100% of traffic reached v2.
- Blast radius limited.
- Zero data corrupted by blind rollback.
- App, workers, DB, and queues reconciled.
- Stable SLO restored within committed RTO.
- Pipeline prevented from auto-repromoting v2.
- Metrics and evidence sufficient to fix root cause.
- Complete SBOM, digest, and audit trail recorded for v3.


## 30. Production checklist: canary, blue-green, and rollback

### 30.1. Artifacts and supply chain

- [ ] Git commit/branch passed code review and branch protection.
- [ ] CI unit, integration, and security tests pass.
- [ ] Secret scanning, SAST, SCA, and vulnerability checks pass policy.
- [ ] SBOM, provenance, and signatures attached where required.
- [ ] Image digests / JAR versions are immutable, independent of `latest`.
- [ ] Artifact tested in staging is the exact artifact promoted to production.
- [ ] ACR retains the Stable image throughout the rollback window.
- [ ] CI/CD identities use federation / managed identities where supported.
- [ ] Service connections and runner permissions are narrowly scoped.
- [ ] No credentials or PII appear in logs or pipeline artifacts.

### 30.2. Platform readiness

- [ ] SKU / App Service plan supports required slots and routing.
- [ ] Slot-specific settings and connection strings are verified.
- [ ] App Service warm-up and health checks are tested.
- [ ] Container Apps runs in multiple revision mode when weight splitting is needed.
- [ ] Both Stable and Green revisions are active and healthy.
- [ ] AKS Pods define proper readiness, startup, and liveness probes.
- [ ] AKS provides surge capacity and `PodDisruptionBudget` per workload.
- [ ] Gateway API / Istio / controller weighted routing support is verified.
- [ ] Front Door origins, TLS, WAF, and health probes are working.
- [ ] DNS weighted routing is not used for request-level precision unvetted.
- [ ] Preview/staging URLs are protected without bypassing auth/WAF.
- [ ] Graceful termination and draining have been tested.

### 30.3. Data and backward compatibility

- [ ] Schema expanded before deploying v2.
- [ ] Both v1 and v2 read/write the schema cleanly during the rollback window.
- [ ] Migrations/backfills are batched and data-verified.
- [ ] No fields needed by v1 were dropped, renamed, or made `NOT NULL`.
- [ ] Message schemas define versioning, defaults, and unknown-field rules.
- [ ] Service Bus v1/v2 consumers share a compatibility strategy.
- [ ] Worker draining, locks, offsets, and deduplication are tested.
- [ ] Stable secrets/identities remain valid after rotations.
- [ ] Sessions, caches, long-lived connections, and CDNs are checked.
- [ ] Compensation/reconciliation plans cover v2 write side effects.
- [ ] DB restore / forward-fix plans exist if traffic rollback is insufficient.

### 30.4. Canary metric gates

- [ ] Stable baselines exist by route, region, and cohort.
- [ ] Release/version tags attach to logs, metrics, and traces.
- [ ] 5xx, p95/p99, CPU/memory, DB errors, and queue lag are tracked.
- [ ] Business correctness metrics (orders, payments, invoices) are tracked.
- [ ] Sample sizes and hold windows are adequate.
- [ ] Health probes and synthetic traffic do not distort SLOs.
- [ ] Application Insights sampling and ingestion delays are understood.
- [ ] Missing/stale telemetry triggers HOLD, never promote.
- [ ] Critical security/data incidents trigger immediate rollback/mitigation.
- [ ] Gate thresholds and decision owners are approved.
- [ ] Actual traffic weights are read back at every ring.
- [ ] Canaries do not degrade shared Stable capacity significantly.

### 30.5. Rollback and automation

- [ ] Stable revision, slot, or deployment is ready and healthy.
- [ ] Stable artifact/digest remains pullable/downloadable.
- [ ] Traffic rollback commands have been rehearsed.
- [ ] Pipelines halt promotion post-rollback instead of looping v2 deploys.
- [ ] GitOps source of truth supports synchronized reverts.
- [ ] Rollback requires no ad-hoc admin privilege escalation during incidents.
- [ ] Post-rollback state readback is mandatory.
- [ ] User-facing metrics are verified back to baseline.
- [ ] In-flight sessions/jobs and queue workers have drain plans.
- [ ] Incident owner and communication plan are defined.
- [ ] Separate approvals govern DB restores or forward fixes.
- [ ] Pre/post-rollback evidence is archived without secrets.

### 30.6. Cost, governance, and closeout

- [ ] Compute overlap, registry retention, and monitoring costs are budgeted.
- [ ] Budgets/alerts are configured by subscription, resource group, and tags.
- [ ] Managed identities, Key Vault, and network access are verified.
- [ ] Azure RBAC scopes and approval audits are in place.
- [ ] Monitoring ingestion, retention, and PII redaction policies exist.
- [ ] Concurrent canaries and resource quotas are capped.
- [ ] Stable versions are retained across the full rollback window.
- [ ] Schema contracts wait until the rollback window closes.
- [ ] Post-release reports and lessons learned are documented.
- [ ] Releases close on verified business/technical health, not just CLI exit codes.

## 31. Self-check questions

1. **How does deployment differ from release?** Deployment places an artifact into runtime; release exposes that version or feature to users.
2. **What is a canary deployment?** Routing a small share of traffic or cohort to the new version and expanding gradually through gates.
3. **What is blue-green deployment?** Two parallel versioned environments with serving cut over between them.
4. **What is a rolling update?** Replacing instances in batches, typically without precise weighted HTTP routing.
5. **What risk does `recreate` carry?** Potential downtime and slow rollback.
6. **Do feature flags replace container rollbacks?** No; they only govern behavior behind the flag.
7. **How does A/B testing differ from canary?** A/B measures product impact; canary prioritizes release safety.
8. **Why do immutable artifacts matter?** They ensure the exact artifact tested is what gets promoted and rolled back.
9. **How does an image digest differ from the `latest` tag?** A digest uniquely identifies exact image bytes; tags can move.
10. **What does an SBOM help with?** Inventorying components/libraries in an artifact to assess supply-chain risk.
11. **What do provenance and attestations provide?** Evidence of build origin, process, and artifact metadata under policy.
12. **Why avoid rebuilding in production?** Rebuilding can produce a different binary than what was tested.
13. **How does readiness differ from liveness?** Readiness governs whether a Pod receives traffic; liveness triggers restarts when stuck.
14. **Is a `GET /` smoke test enough?** No; verify dependencies and core business flows too.
15. **Does a 10% request canary guarantee 10% of users?** No—sticky sessions, caching, and request patterns vary.
16. **How do sticky cookies affect traffic?** A single client can remain pinned to one slot or revision.
17. **What are hold windows for?** Collecting enough samples/telemetry and catching delayed side effects.
18. **If metrics are missing, promote or HOLD?** HOLD under fail-safe policy.
19. **What are App Service deployment slots used for?** Deploying and testing a version prior to swapping or routing traffic.
20. **Do all App Service plans support slots?** No; support depends on tier/SKU.
21. **What does a staging/production swap do?** Swaps code and non-sticky configuration between slots via platform mechanics.
22. **Does a slot swap roll back the database?** No.
23. **What do sticky slot settings mean?** Settings pinned to the slot name that do not swap alongside application code.
24. **When is App Service traffic routing used?** To send a percentage of HTTP traffic to a staging slot.
25. **Does `traffic-routing clear` roll back swapped code?** No; it only resets routing percentages.
26. **Do App Service slots always have independent compute?** No; slots can share the same App Service plan.
27. **What is a Container Apps revision?** An immutable snapshot of revision-scope template and config.
28. **Which mode is required to split traffic across revisions?** Multiple active revisions mode.
29. **Can an inactive revision receive weighted traffic automatically?** No; check activation, health, and ingress.
30. **Do ACA HTTP traffic weights split queue consumer messages?** No.
31. **Is an ACA label URL the same as a traffic weight?** No; test/label endpoints differ from ingress weights.
32. **Does AKS `Deployment RollingUpdate` deliver an exact 10% request canary?** No.
33. **What does `maxUnavailable: 0` mean?** Aims to keep all desired Pods available during rollout/readiness, requiring extra capacity.
34. **What does `kubectl rollout undo` revert?** Deployment Pod template/history—not external DBs, data, or out-of-scope configs.
35. **Can GitOps undo a manual rollback?** Yes, if desired state in Git still specifies v2.
36. **How does AKS blue-green via Service selector work?** The Service selects Pods carrying either `track: blue` or `track: green`.
37. **Do Kubernetes Services have native HTTP traffic weights?** No standard weighted HTTP field exists.
38. **What does Gateway API `HTTPRoute` support?** Weighted routing across `backendRefs` when supported by the controller.
39. **What does Istio use to shift traffic?** `VirtualService` and `DestinationRule` subsets per mesh setup.
40. **How does Front Door origin priority differ from weight?** Priority sets preference/failover; weight splits among eligible origins at equal priority.
41. **Why aren't Front Door weights mathematically exact?** Health probes, affinity, caching, routing logic, and traffic volume.
42. **Does Traffic Manager weighted DNS give request-level precision?** No, due to DNS caching and TTLs.
43. **What is schema expand–migrate–contract?** Compatible expansion, gradual data migration, and contraction only once safe.
44. **What breaks when dropping schema elements prematurely?** Version v1 can no longer run on rollback.
45. **Is database migration rollback just restoring a backup?** No; restores lose newer writes and often require DBAs or forward fixes.
46. **Why is message schema versioning critical?** So v1 and v2 workers process and replay queued messages safely.
47. **What is needed when stopping worker v2?** Drain in-flight messages, locks/checkpoints, and prevent duplicates.
48. **How does idempotency help during retries?** Prevents duplicate side effects when requests or messages replay.
49. **What is traffic rollback?** Routing traffic back to stable; it does not revert configs or data automatically.
50. **What does a feature-flag kill switch require?** Tested OFF path, access controls, auditing, and data consistency.
51. **What must a metric gate compare?** Canary vs. Stable across matching windows/cohorts, thresholds, and sample counts.
52. **Should sampled traces serve as the sole SLO error denominator?** No, not without accounting for sampling weights.
53. **Should a data-corruption bug wait for 500 requests before rolling back?** No; critical gates trigger immediately.
54. **Why must pipelines read back traffic after mutations?** To confirm actual live state instead of trusting exit codes alone.
55. **Why isn't slot swap idempotent when run twice?** The second swap reverses the first swap.
56. **Does Azure DevOps `environment: production` create approvals automatically?** No; configure Approvals and checks on the environment.
57. **Does a GitHub Actions environment enforce reviewers automatically?** No, unless protection rules are enabled.
58. **What risk does OIDC federation reduce?** Storing long-lived service principal secrets.
59. **Does a 1% canary limit DB access to 1% of data?** No; its runtime identity can access whatever RBAC/DB grants allow.
60. **Why retain Stable after promoting to 100%?** For rapid rollback if delayed bugs surface.
61. **Should v1 images be deleted from ACR immediately?** Not before the recovery/rollback window closes.
62. **If a release has low 5xx rates yet double-charges payments, what should happen?** Trigger critical rollback/mitigation and data reconciliation.
63. **How can auto-rollback enter a loop?** A promotion or GitOps controller re-pushes the broken version.
64. **When is rolling forward better than rolling back?** When data, schemas, or security patches render v1 unsafe.
65. **Can a 5% Green canary cause memory contention for Blue?** Yes, when sharing plans, databases, or nodes.
66. **Why doesn't Green cost 5% of Stable?** Green still maintains running replicas, telemetry, and dependencies.
67. **What must a rollback runbook contain?** Release ID, stable status, data compatibility, actions, readback, and evidence.
68. **When a Front Door origin health probe fails, what happens to realized weights?** They shift as the unhealthy origin leaves the eligible set.
69. **What is needed to view canaries in Application Insights?** Version/role metadata and version-segmented queries.
70. **When is a release truly complete?** When gates, user-facing SLOs, business integrity, and audit evidence are all confirmed.

## 32. References

These official sources serve as primary lookup points. APIs, SKU support, CLI limits, and controller versions evolve; verify docs against your active environment before applying in production.

### Azure App Service

- [Set up staging environments in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots) — slots, swaps, sticky settings, warm-up, and traffic routing.
- [Azure App Service overview](https://learn.microsoft.com/en-us/azure/app-service/overview) — hosting, plans/SKUs, and capabilities.
- [App Service health check](https://learn.microsoft.com/en-us/azure/app-service/monitor-instances-health-check) — instance health monitoring.
- [Azure CLI webapp traffic-routing](https://learn.microsoft.com/en-us/cli/azure/webapp/traffic-routing) — show/set/clear commands and distributions.
- [Azure CLI webapp deployment slot](https://learn.microsoft.com/en-us/cli/azure/webapp/deployment/slot) — swap/create/list.

### Azure Container Apps

- [Azure Container Apps revisions](https://learn.microsoft.com/en-us/azure/container-apps/revisions) — revision scopes/modes and lifecycles.
- [Traffic splitting in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/traffic-splitting) — weights, canaries, and labels.
- [Azure Container Apps health probes](https://learn.microsoft.com/en-us/azure/container-apps/health-probes) — startup/liveness/readiness behavior.
- [Azure Container Apps CLI](https://learn.microsoft.com/en-us/cli/azure/containerapp) — revisions and ingress commands.

### AKS, Gateway API, and Istio

- [Kubernetes Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/) — RollingUpdate, ReplicaSets, rollout history.
- [Kubernetes Services](https://kubernetes.io/docs/concepts/services-networking/service/) — selectors, Endpoints, traffic basics.
- [Gateway API traffic splitting](https://gateway-api.sigs.k8s.io/guides/traffic-splitting/) — HTTPRoute weighted backendRefs.
- [Istio traffic shifting](https://istio.io/latest/docs/tasks/traffic-management/traffic-shifting/) — VirtualService/DestinationRule.
- [AKS Istio service mesh add-on](https://learn.microsoft.com/en-us/azure/aks/istio-about) — capabilities, limitations, and operations.
- [AKS applications](https://learn.microsoft.com/en-us/azure/aks/concepts-clusters-workloads) — workloads, capacity, and operational design.
- [GitOps with Flux v2 on AKS](https://learn.microsoft.com/en-us/azure/azure-arc/kubernetes/conceptual-gitops-flux2) — desired state and reconciliation.

### Azure Front Door and traffic steering

- [Azure Front Door routing methods](https://learn.microsoft.com/en-us/azure/frontdoor/routing-methods) — priority, weight, and latency.
- [Azure Front Door origins and origin groups](https://learn.microsoft.com/en-us/azure/frontdoor/origin) — origin weights, probes, and health.
- [Azure Traffic Manager routing methods](https://learn.microsoft.com/en-us/azure/traffic-manager/traffic-manager-routing-methods) — weighted DNS, TTLs, and limitations.

### CI/CD, observability, security, and cost

- [Azure DevOps deployment jobs](https://learn.microsoft.com/en-us/azure/devops/pipelines/process/deployment-jobs) — environment-bound deployments.
- [Azure DevOps approvals and checks](https://learn.microsoft.com/en-us/azure/devops/pipelines/process/approvals) — environments, approvals, and resource checks.
- [GitHub Actions with Azure OpenID Connect](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect) — identity federation.
- [Azure Container Registry best practices](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-best-practices) — registries, artifact lifecycles, and reliability.
- [Azure Monitor Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview) — error, latency, and dependency diagnostics.
- [AppRequests table reference](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/apprequests) — request telemetry/KQL schema.
- [Azure SQL Database](https://learn.microsoft.com/en-us/azure/azure-sql/database/) — schema/data operations and resilience.
- [Azure Service Bus](https://learn.microsoft.com/en-us/azure/service-bus-messaging/) — queue delivery, retries, and DLQ semantics.
- [Azure Well-Architected safe deployment practices](https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/safe-deployments) — progressive rollouts, ring deployments, and rollbacks.
- [Azure Cost Management](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/) — costs, budgets, and allocation.
- [Azure Chaos Studio](https://learn.microsoft.com/en-us/azure/chaos-studio/chaos-studio-overview) — policy-governed fault injection.

**Conclusion:** canary, blue-green, and rollback on Azure are far more than running **slot swap**, **setting revision weights**, or **`kubectl rollout undo`**. Safe releases begin with **immutable artifacts, identities/ACR, and approvals**, continue through **parallel deploys, readiness, controlled traffic, and evidence-backed metric gates**, and finish with **verified business correctness and recoverability**. App Service deployment slots, Azure Container Apps revisions, AKS Gateway API/service mesh, and Azure Front Door offer distinct routing mechanisms; select based on runtime/SKU, session state, traffic, and cost. Most importantly, **traffic rollback does not undo schemas, data, messages, secrets, or side effects**. Design expand–migrate–contract, message versioning, stable artifact retention, drift controls, incident runbooks, and rollback drills **before** shifting traffic to a new version.
