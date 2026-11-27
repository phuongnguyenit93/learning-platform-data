# Revisions, Traffic Splitting, and Rollbacks on Container Apps

A new version of an API may start up cleanly yet fail when serving real users: changing authentication behavior, hitting the wrong database address, introducing an incompatible library, or increasing latency. Shifting 100% of traffic immediately to the new version can impact every customer. **Azure Container Apps** provides **revisions** and **traffic splitting**, enabling teams to run multiple versions of the same container app, route traffic proportionally, and rapidly shift traffic back to a proven version when needed.

This lesson belongs to the **Container Registry and Container Apps** chapter of the **CLOUD_PROVIDERS_AZURE** module. Revision decisions tie directly into the broader Azure architecture: subscriptions and resource groups for governance, Microsoft Entra ID and managed identities for pulling images/secrets, virtual networks and ingress for receiving traffic, Azure Monitor and Application Insights for evaluating outcomes, as well as the cost of running replicas. This is a self-contained guide on **safe version releases, traffic splitting, and rollbacks**, not merely swapping image tags.

After this lesson, you will be able to:

- Explain container apps, environments, revisions, replicas, image tags/digests, activation, and revision labels.
- Distinguish **single revision mode** from **multiple revision mode**.
- Identify which changes create a new revision and which belong to application-scope configuration.
- Design a canary rollout with weights 0% → 5% → 25% → 50% → 100%, with stop criteria.
- Use Azure CLI to inspect revisions, swap images, activate revisions, adjust traffic, and roll back.
- Explain the limitations of rollbacks with respect to database migrations, message schemas, secrets, and external dependencies.
- Analyze health, scaling, routing, logging, identity, security, and costs when operating multiple revisions.

## 1. Core Mindset: Do Not Equate Images, Revisions, and Replicas

| Concept | Explanation | Example |
|---|---|---|
| **Container image** | Artifact containing application/runtime/dependencies stored in a registry; each image manifest has a specific digest | `myregistry.azurecr.io/orders-api:1.2.0` |
| **Container app** | Azure resource defining the application, ingress, configuration, template, and revision list | `ca-orders-api` |
| **Container Apps environment** | Runtime boundary, networking/observability, and shared capabilities for apps inside it | `aca-env-prod` |
| **Revision** | An immutable snapshot of **revision-scope** properties created when modifying supported template fields | `ca-orders-api--v120` |
| **Replica** | A running instance of **a single revision**; count varies per scale rules | Revision v120 has 3 replicas |
| **Active revision** | Revision enabled to run/serve per routing and configuration | v119 and v120 both active |
| **Traffic weight** | Percentage of ingress traffic directed to a target revision | v119 90%, v120 10% |
| **Revision label** | Name routing directly to a specific revision when ingress supports it | `candidate` |

**Image ≠ revision:** the exact same image can be used across multiple revisions if template settings change. **Revision ≠ replica:** one revision can have multiple replicas, and replicas can be created/destroyed by autoscaling. **Active ≠ receiving traffic:** in multiple revision mode, a revision can be active with **0%** weight—meaning it is not selected by the default traffic route, though it may still be reachable via a label URL or other direct path if configured.

### Example of Three Releases

~~~text
Container app: ca-orders-api

Revision ca-orders-api--v118
  Image: orders-api:1.1.8
  Active: false
  Default ingress weight: 0%

Revision ca-orders-api--v119
  Image: orders-api:1.1.9
  Active: true
  Default ingress weight: 90%
  Replicas: 3

Revision ca-orders-api--v120
  Image: orders-api:1.2.0
  Active: true
  Default ingress weight: 10%
  Replicas: 1-3 per scale policy
~~~

Revision names, replica counts, and weights are illustrative. Azure generates revision names per service rules; a suffix can be supplied where supported. Do not treat version names or revision names as proof of the running image without checking the deployment's image reference and digest.

### System Structure

~~~mermaid
flowchart TB
    CLIENT[HTTPS Client] --> INGRESS[Container Apps ingress]
    INGRESS -->|90%| OLD[Revision v119 - stable]
    INGRESS -->|10%| NEW[Revision v120 - canary]
    OLD --> O1[Replica old-1]
    OLD --> O2[Replica old-2]
    OLD --> O3[Replica old-3]
    NEW --> N1[Replica new-1]
    NEW --> N2[Replica new-2]
    OLD --> DB[(Shared database)]
    NEW --> DB
    OLD -. logs/metrics .-> MON[Azure Monitor / Log Analytics]
    NEW -. logs/metrics .-> MON
~~~

Weights apply at the **revision routing layer**, not as a guarantee that out of 100 HTTP requests, exactly 90 hit the old version. Over a finite window, distribution has statistical variance and is affected by connection patterns, supported session/sticky behavior, retries, and direct access paths. Always measure actual request counts by revision over a representative window.

## 2. Single Revision Mode vs. Multiple Revision Mode

Azure Container Apps has a **revision mode** governing how new versions activate and coexist.

| Criterion | Single Revision Mode | Multiple Revision Mode |
|---|---|---|
| Goal | One active version serving traffic at a time per service model | Multiple revisions can remain active |
| Release | Platform transitions from prior revision to new revision per lifecycle rules | Operators manage active revisions and traffic splits |
| 5%/95% Canary | Not the right model | Yes, with HTTP ingress and supported conditions |
| Rollback | Must change template/redeploy older version or use supported workflow | Can shift weight back to old revision **if that revision remains active/available** |
| Running multiple versions simultaneously | Not used to maintain multiple active versions | Can keep stable and candidate running side by side |
| Cost/capacity | Fewer active revisions by design | Can consume replicas across multiple revisions simultaneously |
| Best suited for | Simple apps, linear version releases | Canary, A/B, gradual rollouts, blue-green, or fast weight-based rollbacks |

In **single revision mode**, the platform orchestrates transitions per lifecycle rules; do not equate this with a zero-downtime guarantee for every application. If a new revision fails to start, fails image pull, fails health probes, or mishandles session state, the outcome still depends on configuration and runtime health.

In **multiple revision mode**, you must actively govern **revision activation, traffic targets, scaling, labels, and old revision cleanup policies**. Never assume creating a new image/revision automatically applies your intended canary ratio: **always read back the traffic configuration immediately after creating a revision**, then set weights explicitly.

### Choosing a Mode by Deployment Strategy

~~~mermaid
flowchart TD
    START[Prepare release] --> Q1{Need old and new active simultaneously?}
    Q1 -->|Yes| MULTI[Multiple revision mode]
    Q1 -->|No| SINGLE[Single revision mode may fit]
    MULTI --> Q2{HTTP ingress and need traffic split?}
    Q2 -->|Yes| CANARY[Weight-based canary + telemetry]
    Q2 -->|No| NOHTTP[Design custom rollout for queues/jobs/TCP]
    CANARY --> CHECK[Measure SLOs and decide promote/rollback]
~~~

**Note:** the weighted traffic splitting described in this lesson focuses on Container Apps **HTTP ingress**. Do not infer that arbitrary TCP connections, scheduled jobs, or queue messages share identical HTTP traffic-splitting mechanics. For queue consumers, design replica counts, consumer groups, schemas, and concurrency per messaging models rather than tweaking ingress weights.

## 3. What Creates a New Revision?

A revision is an immutable snapshot of **revision-scope** configuration at creation time. Modifying properties inside the container app's template causes Azure to create a new revision instead of mutating the old revision's contents.

### 3.1. Changes That Typically Create a Revision

- **Container image** or container settings declared inside the template.
- **Environment variables** within the container template (including secret references where supported).
- **CPU/memory resources** of containers.
- **Scale rules**, min/max replicas, and template-scoped scale settings.
- **Init containers, probes, command/args, volume mounts**, or other template properties where supported.
- **Revision suffix** specified when creating a new revision via supported API/CLI.

For example, if you change the image from `orders-api:1.1.9` to `orders-api:1.2.0`, Container Apps creates a new revision. If you simultaneously update `DATABASE_SCHEMA_MODE=v2` in template env vars, that is also a revision-scope change recorded in the new revision.

### 3.2. Container-App-Level Changes

Certain **application-scope** settings can be updated **without creating a new revision**, such as ingress/traffic allocation settings and the app's secrets collection, registry credentials, or revision mode per service capabilities. Distinguish **changing a secret value** from **changing a secret reference in the template**:

- Updating a secret in the app-level collection typically does not create a new revision.
- Running replicas may not automatically pick up the new secret value when you update it. If the secret is injected into an environment variable at startup, a supported revision restart/redeploy is usually needed to consume the new value.
- Modifying an **env var** (even just the referenced secret name) is a template change and can create a new revision.

Never store production passwords directly in YAML or CLI history. Use managed identities, Key Vault, and secret references per appropriate design; plan secret rotation for both stable and canary revisions.

### 3.3. Why Not Just Update the `latest` Tag?

A registry tag can be moved to a new digest without changing the image reference string in the template. Re-pushing the `latest` tag to Azure Container Registry **does not guarantee creating a new revision**, nor does it guarantee all running replicas switch to the new image at the same time.

**Safe operational practice:** build images with immutable version/commit tags, record the **digest**, update the template to the approved image, and verify the revision runs the exact intended artifact. When rolling back, revert to a tested revision/digest rather than relying on the ambiguous meaning of `latest`.

## 4. Lifecycle: Active, Inactive, Replicas, and Labels

A revision has distinct management and runtime states. **Active/inactive**, provisioning/running/failed, and replica count are not interchangeable:

| State / Situation | Meaning | Action |
|---|---|---|
| Revision created | Holds a template config snapshot | Check name, image, resource config |
| Active with 0% weight | Usable for testing; receives no default weighted ingress traffic | Test health via label URL if supported |
| Active, weight > 0% | Target for proportional HTTP ingress | Monitor per-revision request/error metrics |
| Scaled to 0 replicas | Possible scale behavior when idle under supported config | Check minReplicas, warm-up, and cold starts |
| Revision unhealthy/failed | App may be unready | Read logs/probes; do not shift more traffic |
| Inactive | Not serving standard active routing | May need reactivation before rollback |

**Inactive does not mean "deleted."** Still, old revisions may be purged under service retention/limits, or fail to pull images if the registry deleted the digest. Hence, **fast rollback is only feasible while the old revision still exists with an available image, registry rights, and compatible dependencies**.

### Revision Labels

A revision label lets you reach **a specific labeled revision** via a dedicated URL per Container Apps ingress capabilities. This is useful for smoke testing v120 before exposing customers through the primary hostname.

Logical example:

~~~text
Primary hostname:  https://orders.example.com
  → stable 90%, candidate 10%

Label "candidate" (URL provided by Container Apps)
  → routes directly to revision v120 for testing
~~~

A label is **not** a traffic weight. Attaching a label to a revision does not give it 10% of primary hostname traffic, and changing primary hostname weights does not rename labels.

**Security:** a label URL must not be treated as isolation or a secret. If ingress is publicly reachable, label endpoints must enforce authentication, access policies, and appropriate restrictions. Never skip authentication on a canary simply because "it is a test URL."

## 5. Traffic Splitting: Canary, Blue-Green, and A/B

**Traffic splitting** assigns weights to selected revisions on the container app's ingress. For HTTP ingress and multiple revisions under supported configurations, defined route weights must sum to **100%**.

### 5.1. Progressive Canary

| Phase | Stable | Candidate | Goal |
|---|---:|---:|---|
| Prepare | 100% | 0% | Create candidate; verify via label URL and smoke tests |
| Small canary | 95% | 5% | Gather signal from a small user slice; catch critical bugs |
| Expanded canary | 75% | 25% | Compare latency/error rates against stable |
| Broad split | 50% | 50% | Validate load and scaling behavior at larger scale |
| Promote | 0% | 100% | Shift production to the proven candidate |
| Cleanup | 0% or inactive | 100% | Keep rollback target long enough before cleanup |

This is a **controlled plan**, not automatic behavior upon creating a container app. Each weight increase requires an observation window, an approver, and stop criteria.

### 5.2. Blue-Green

With blue-green, keep `blue` (production) and `green` (candidate) running in parallel. Smoke-test `green` on its own endpoint, then shift 100% of traffic from blue to green when checks pass. Rollback shifts weight back to blue if blue remains available and data-compatible.

**Trade-off:** blue-green runs parallel capacity and increases cost. An instant 100% switch can also trigger errors if the workload lacks warm-up capacity; verify minimum replicas and dependency reachability before switching.

### 5.3. A/B Testing

Revision traffic splitting can send portions of traffic to two versions, yet it is **not a complete user-cohort A/B testing engine**. If the same user must consistently land in variant A or B, measure cohort conversion, track consent, or exclude specific user segments, you need identification/feature flag logic in the application or gateway. A 50/50 ingress weight **does not guarantee** the same user always hits the same revision.

### 5.4. When to Use Feature Flags Instead of Revisions

- **Revisions** suit releasing new image/config bundles and shifting workload-level traffic.
- **Feature flags** suit toggling a feature for user segments without swapping images or touching infrastructure.
- Combine both: release v120 with the feature defaulted off, roll out canary traffic, then ramp up the feature percentage once evidence supports it.

Never use feature flags as a substitute for testing cross-revision compatibility or database migrations; both old and new code must tolerate the shared schema/data.

## 6. Safety Criteria Before Increasing Traffic

A release plan must define **who decides, and based on which evidence**, not just the numbers 5/25/50/100.

### Minimum Signals

| Signal Group | Metrics and Questions | Method |
|---|---|---|
| Availability | Does candidate return 2xx for health/readiness? | HTTP probes and per-revision synthetic checks |
| Errors | Are candidate 5xx, timeouts, or exceptions rising? | Logs/metrics segmented by revision |
| Latency | Do candidate p95/p99 exceed stable/SLOs? | Application Insights/distributed tracing |
| Resources | CPU/memory, replicas, restarts, OOMs | Container Apps metrics/logs |
| Dependencies | Are SQL/Storage/Key Vault/partner APIs returning 403/429/5xx? | Dependency tracing and controlled tests |
| Business | Do payments, order creation, and key flows succeed? | Synthetic transactions/canary business metrics |
| Security | No excessive permission drift, secret leaks, or auth failures | Security scans, audits, RBAC checks |

Illustrative **sample thresholds** (not Azure defaults):

- Canary must serve a statistically meaningful minimum number of requests for real traffic; during low traffic, run synthetic tests rather than concluding from 3 passing requests.
- Do not increase traffic if canary 5xx rate breaches SLO or exceeds stable by a defined margin.
- Do not increase traffic if p95 latency degrades noticeably, data corruption appears, or any high-severity business error occurs.
- Increase traffic only after operators verify logs, latency, scaling, and dependencies over the approved observation window.

**Request count is the denominator**, not replica count. A revision with 2 replicas does not receive twice the traffic of a revision with 1 replica. Weights distribute at ingress, while autoscale governs each revision's compute capacity.

## 7. Preparing the Azure Environment for Revision Rollouts

The workflow below demonstrates **Azure CLI in Bash**. These are sample commands for learners to run in an authorized lab subscription; **no real Azure resources were created while authoring this lesson**. Revision/traffic updates modify live applications, so never run them in production without change approval.

### 7.1. Prerequisites

- An Azure subscription and resource group permitted for lab use.
- A Container Apps environment and a **Container App with HTTP ingress** already created and able to pull images from a registry.
- Operator identity holds Azure RBAC permissions to read/modify the container app, create revisions, and update ingress.
- Application already has a working stable revision with a test endpoint to verify versions.
- A candidate image built, scanned, and pushed by CI to ACR or a trusted registry, with tag/digest recorded.
- Container listens on the right target port, responds to health/readiness checks per Container Apps support, and has proper network/secret access.
- Monitoring tracks request count, error rate, p95/p99, and dependency failures by revision.
- Rollback plan and database schema/message contract controls are ready.

Example variable setup:

~~~bash
az login

SUBSCRIPTION_ID="<subscription-id-lab>"
RG="rg-aca-release-lab"
APP="ca-orders-demo"
REGISTRY="<registry-name>.azurecr.io"
REPOSITORY="orders-api"
STABLE_IMAGE="$REGISTRY/$REPOSITORY:1.1.9"
CANDIDATE_IMAGE="$REGISTRY/$REPOSITORY:1.2.0"

az account set --subscription "$SUBSCRIPTION_ID"
az account show --query "{id:id, name:name}" -o table
~~~

Values in `<...>` are placeholders only. Replace them with your real subscription and registry. Do not assume an app named `ca-orders-demo` already exists unless provisioned. In a lab, provision resources via IaC/Portal or your team's standard process; CLI commands exist to create environments and apps, yet you must choose image, ingress, CPU/memory, scaling, and registry auth matching your environment first.

**Important regarding private ACR:** image pull is independent of traffic splitting. The container app needs registry credentials or a **managed identity with pull permissions** matching the ACR permission mode plus network reachability to the registry (including private endpoints/DNS where applicable). When rolling back to an older revision, that revision's image must still be pullable if new replicas spin up.

### 7.2. Inspect Current Resources

~~~bash
az containerapp show \
  --name "$APP" \
  --resource-group "$RG" \
  --query "{name:name, mode:properties.configuration.activeRevisionsMode, ingress:properties.configuration.ingress, latest:properties.latestRevisionName}" \
  --output json

az containerapp revision list \
  --name "$APP" \
  --resource-group "$RG" \
  --query "[].{name:name, active:properties.active, created:properties.createdTime, replicas:properties.replicas}" \
  --output table
~~~

Inspect output **before making changes**: which revision is currently targeted by ingress, which are inactive, and what image and variables are configured. Read further:

~~~bash
az containerapp show \
  --name "$APP" \
  --resource-group "$RG" \
  --query "properties.configuration.ingress.traffic" \
  --output json

az containerapp show \
  --name "$APP" \
  --resource-group "$RG" \
  --query "properties.template" \
  --output json
~~~

Seeing `active=true` alone does not prove a revision receives 10% traffic. Always read the actual ingress traffic weight table. When multiple revisions share the same image tag, verify the digest/manifest recorded by the pipeline instead of inferring from names.

## 8. Switching to Multiple Revisions and Creating a Candidate

### 8.1. Set Revision Mode

On a running lab app meeting prerequisites:

~~~bash
az containerapp revision set-mode \
  --name "$APP" \
  --resource-group "$RG" \
  --mode multiple

az containerapp show \
  --name "$APP" \
  --resource-group "$RG" \
  --query "properties.configuration.activeRevisionsMode" \
  --output tsv
~~~

Expect the mode value corresponding to `Multiple`. Check `az containerapp revision set-mode --help` for your Azure CLI/`containerapp` extension version. **Changing modes is an operational change**; review release schedules and traffic first rather than switching in production assuming old revisions automatically restore or receive desired weights.

### 8.2. Record the Stable Revision

From the revision and traffic lists, identify the **exact** revision currently serving production traffic, for example:

~~~bash
# Replace with a real revision verified via revision list.
STABLE_REV="ca-orders-demo--v119"

az containerapp revision show \
  --name "$APP" \
  --resource-group "$RG" \
  --revision "$STABLE_REV" \
  --output json
~~~

Never guess the stable revision by picking the name with the newest timestamp. An app might already have an experimental candidate or a broken recent revision; `latest` does not equal `stable`. Before releasing, save the stable revision name, image/digest, and configuration copy needed for rollback.

### 8.3. Create a Revision with the New Image

**Guard against unintended traffic shifts:** before creating the candidate, confirm production routing is **pinned to the specific stable revision** rather than relying on a `latestRevision` rule that might swing to the newly created revision. In a lab, after verifying the stable revision, set an explicit weight:

~~~bash
az containerapp ingress traffic set \
  --name "$APP" \
  --resource-group "$RG" \
  --revision-weight "$STABLE_REV=100"

az containerapp show \
  --name "$APP" \
  --resource-group "$RG" \
  --query "properties.configuration.ingress.traffic" \
  --output json
~~~

If you cannot guarantee traffic state before and after creating a revision, **do not deploy the candidate directly to production**: test in an equivalent environment or use an IaC/pipeline workflow that manages traffic atomically where supported. Updating the image is a **revision-scope** change:

~~~bash
az containerapp update \
  --name "$APP" \
  --resource-group "$RG" \
  --image "$CANDIDATE_IMAGE" \
  --revision-suffix "v120"
~~~

The revision suffix must be valid and unique per Container Apps rules. Suffix `v120` is illustrative; if already used, pick another suffix. The update command may create a new revision; **immediately verify state and traffic afterward** rather than assuming the candidate defaults to 0% or 10% as intended.

~~~bash
az containerapp revision list \
  --name "$APP" \
  --resource-group "$RG" \
  --output table

az containerapp show \
  --name "$APP" \
  --resource-group "$RG" \
  --query "properties.configuration.ingress.traffic" \
  --output json
~~~

In this document, assume the candidate was created as `ca-orders-demo--v120`. You must use the **exact name returned by Azure** and verify the candidate image:

~~~bash
CANDIDATE_REV="ca-orders-demo--v120"

az containerapp revision show \
  --name "$APP" \
  --resource-group "$RG" \
  --revision "$CANDIDATE_REV" \
  --output json
~~~

If the candidate is unhealthy, fails image pull, or fails readiness, **do not send it traffic**. Fix the root cause and create a new revision when needed; never delete the stable revision before verifying its replacement.

### 8.4. Activate the Candidate If Inactive

If the candidate exists yet is inactive and you want it to participate in the rollout:

~~~bash
az containerapp revision activate \
  --name "$APP" \
  --resource-group "$RG" \
  --revision "$CANDIDATE_REV"
~~~

Activation brings the revision into the active set, yet **is not enough to prove the app is ready**. Observe provisioning/running status, replica startup, liveness/readiness, and dependency reachability before routing customer requests to it.

## 9. Performing Traffic Splitting with Azure CLI

Once **both revisions are active**, set weights explicitly. Examples use `az containerapp ingress traffic set` for HTTP ingress; flag names/behavior may vary across CLI/extension versions, so verify `--help` before automating.

### 9.1. Prepare: 100% Stable, 0% Candidate

~~~bash
az containerapp ingress traffic set \
  --name "$APP" \
  --resource-group "$RG" \
  --revision-weight "$STABLE_REV=100" "$CANDIDATE_REV=0"
~~~

Verify the result:

~~~bash
az containerapp show \
  --name "$APP" \
  --resource-group "$RG" \
  --query "properties.configuration.ingress.traffic" \
  --output json
~~~

Note: when applying configuration over an existing multi-rule state, confirm the resulting rule set **retains no unexpected weights** (such as `latestRevision=true` left over from another workflow). The combined config must be valid and reflect your exact intent. In production, never rely on a single command's exit code; read back traffic rules and verify real requests.

### 9.2. Open 5% Canary

~~~bash
az containerapp ingress traffic set \
  --name "$APP" \
  --resource-group "$RG" \
  --revision-weight "$STABLE_REV=95" "$CANDIDATE_REV=5"
~~~

**Meaning:** ingress distributes traffic between stable and candidate per the specified weights. It **does not** cap the candidate to 5% CPU, 5% replicas, or 5% database connections. Each revision autoscales according to its own template and triggers.

After applying, monitor request metrics **broken down by revision**. Do not let a single app-wide aggregate 5xx rate mask a high error rate on a low-traffic canary.

### 9.3. Expand to 25%, 50%, and Promote

~~~bash
# Proceed only when the prior phase's SLOs pass.
az containerapp ingress traffic set \
  --name "$APP" -g "$RG" \
  --revision-weight "$STABLE_REV=75" "$CANDIDATE_REV=25"

# After an appropriate observation window:
az containerapp ingress traffic set \
  --name "$APP" -g "$RG" \
  --revision-weight "$STABLE_REV=50" "$CANDIDATE_REV=50"

# Once approved:
az containerapp ingress traffic set \
  --name "$APP" -g "$RG" \
  --revision-weight "$STABLE_REV=0" "$CANDIDATE_REV=100"
~~~

The lines above are **not a single automated script to run back-to-back**. There must be testing, observation, and approval between stages. Running all three consecutively with zero delay removes the risk-reduction benefit of staged rollouts.

### 9.4. Using a Label URL to Test the Candidate Before Canary

Where HTTP ingress and revision labels are supported, attach a label:

~~~bash
az containerapp revision label add \
  --name "$APP" \
  --resource-group "$RG" \
  --revision "$CANDIDATE_REV" \
  --label "candidate"
~~~

Then retrieve the label URL from ingress/label metadata returned by the Azure Portal or corresponding CLI, and send `/health` and synthetic requests to that exact label endpoint.

**Never fabricate hostnames from the app name**: actual hostnames, label suffixes, and domain settings depend on the environment. A label provides a **direct test route** without giving the candidate 5% of primary traffic. Requests hitting the label URL must be excluded/distinguished when analyzing real customer cohort traffic ratios.

### 9.5. Quick Status Checks After Each Step

~~~bash
az containerapp revision list \
  -n "$APP" -g "$RG" \
  --query "[].{name:name,active:properties.active,replicas:properties.replicas}" \
  -o table

az containerapp show \
  -n "$APP" -g "$RG" \
  --query "properties.configuration.ingress.traffic" \
  -o json
~~~

Record before/after configurations in change tickets or pipeline logs **without secrets**. If CLI syntax/capabilities differ in your actual tool version, update your runbook from `az containerapp ingress traffic set --help` and validate in a lab first.

## 10. Rollback: Returning Traffic to the Stable Version

**Revision rollback via traffic weight** is a fast way to send **new requests hitting primary ingress** back to the stable revision in multiple mode. This is especially valuable when new code fails while stable remains active with sufficient capacity and data/dependency compatibility.

### 10.1. Emergency Rollback

Suppose canary v120 is receiving 25% and emits high 5xx rates:

~~~bash
# Production-impacting action: execute only per approved runbook.
az containerapp ingress traffic set \
  --name "$APP" \
  --resource-group "$RG" \
  --revision-weight "$STABLE_REV=100" "$CANDIDATE_REV=0"

# Read back active allocation.
az containerapp show \
  --name "$APP" \
  --resource-group "$RG" \
  --query "properties.configuration.ingress.traffic" \
  --output json
~~~

Then **verify reality**:

1. Stable revision remains active, healthy, and has enough replicas for 100% load.
2. HTTP 5xx, timeouts, and p95/p99 latency drop within expected thresholds.
3. Critical transactions such as order creation, reads, and payments work.
4. No jobs/queue consumers on the candidate continue writing faulty data.
5. No app-level dependency/configuration change is also breaking stable.

**Rolling back ingress traffic is not "canceling all running requests."** Existing connections, in-flight requests, and sticky sessions may continue having impact during transition. Never assume changing weights instantaneously halts every side effect of the new version.

### 10.2. If the Stable Revision Is Inactive

Before routing 100% back to stable, verify the revision still exists and its image can be pulled. When needed and supported:

~~~bash
az containerapp revision activate \
  --name "$APP" \
  --resource-group "$RG" \
  --revision "$STABLE_REV"
~~~

Wait for the revision to become healthy before shifting traffic back, or follow a safe cutover procedure suited to incident severity. If the old revision was purged from the system, you must **redeploy the old image/digest as a new revision**; you cannot activate a revision that no longer exists.

### 10.3. Should You Deactivate the Faulty Revision Immediately?

After setting its weight to 0%, you may consider:

~~~bash
az containerapp revision deactivate \
  --name "$APP" \
  --resource-group "$RG" \
  --revision "$CANDIDATE_REV"
~~~

**Do not rush to deactivate** if you need the candidate to collect logs, reproduce bugs, or inspect rollback conditions; conversely, do not leave a faulty revision active indefinitely if reachable via labels or running background work. Weigh investigation workflows, direct access exposure, billing, and security risks before deciding.

Deactivation does not necessarily delete images in the registry or historical records. If compliance requires evidence, preserve manifests, logs, deployment events, and change tickets in an approved archive.

### 10.4. Rolling Back via Old Image as a Fallback

If the old stable revision cannot be reused (deleted or incompatible changes), use your pipeline to deploy a **new revision** from the verified image digest:

~~~bash
# Example using a pipeline-managed immutable tag.
ROLLBACK_IMAGE="$REGISTRY/$REPOSITORY:1.1.9"

az containerapp update \
  --name "$APP" \
  --resource-group "$RG" \
  --image "$ROLLBACK_IMAGE"
~~~

This is a **roll forward with an old artifact**, not a "full application snapshot restore." App-scope config, secrets, networking, and databases may have changed since the prior release. Verify compatibility and ingress policies after creating the new revision.

### 10.5. Rollback Decision Flow

~~~mermaid
flowchart TD
    ALERT[Canary errors exceed threshold] --> STOP[Halt traffic ramp / pause pipeline]
    STOP --> Q1{Stable still active and healthy?}
    Q1 -->|Yes| ROUTE[Route 100% traffic to stable]
    Q1 -->|No| Q2{Stable revision exists?}
    Q2 -->|Yes| ACT[Activate + verify health]
    Q2 -->|No| REP[Redeploy verified stable artifact]
    ACT --> ROUTE
    REP --> ROUTE
    ROUTE --> CHECK[Assess API, DB, queue, and SLOs]
    CHECK --> INCIDENT[Log incident, root cause, preventive actions]
~~~

This diagram shows business logic: if stable lacks capacity or data schemas broke compatibility, merely shifting traffic can worsen the outage. In that case, invoke DR/restore plans or fix shared dependencies before taking load.

## 11. Code Rollback Does Not Mean Data Rollback

The riskiest aspect of canary deployments is two versions **sharing a common data system** simultaneously. If the new version alters data in a way the old version cannot parse, routing ingress back to the old version will not stop errors.

### 11.1. Incompatible Migration Example

Order app version v119 uses schema:

~~~sql
-- Illustrative old structure
CREATE TABLE Orders (
    Id BIGINT PRIMARY KEY,
    CustomerId BIGINT NOT NULL,
    TotalAmount DECIMAL(18,2) NOT NULL
);
~~~

Version v120 wants to replace `TotalAmount` with `TotalAmountMinorUnits`. If a migration drops the old column when v120 boots, v119—still serving 90% of traffic—queries a missing column and fails. Rolling traffic back to v119 **does not restore the dropped column**.

**Expand–migrate–contract strategy:**

1. **Expand:** add new columns/structures without breaking the old contract.
2. **Deploy compatible v120:** new code reads/writes one or both formats during transition.
3. **Backfill:** migrate old data to the new format using a checkpointed, resumable job.
4. **Observe:** ensure both v119 and v120 handle traffic properly while split.
5. **Promote:** shift 100% traffic to v120 and observe long enough.
6. **Contract:** drop the old structure only in a separate change after the rollback window closes and a restore plan is approved.

Never run destructive schema migrations inside the **startup command** of every replica: multiple replicas/revisions can boot and run migrations concurrently. Separate migrations into an orchestrated, single-execution task with locking/checkpoints and dedicated credentials where needed.

### 11.2. Other Dependencies Requiring Compatibility

| Component | Risk When Running Multiple Revisions | Design Approach |
|---|---|---|
| Azure SQL / PostgreSQL / Cosmos DB | New schema, index, or enum breaks old code | Backward-compatible migrations; test both v119/v120 |
| Azure Service Bus / Event Hubs | Message payload changes; old consumer fails to parse | Versioned schemas, tolerant readers, schema registry where suitable |
| Azure Blob Storage | Object names/metadata change or files overwritten | Versioned formats; do not break old keys/metadata immediately |
| Cache/Redis | Key namespace or serialization changes | Versioned keys, TTLs, and cache invalidation strategy |
| Key Vault | Secret value changes while revisions read at different times | Overlapping secret rotation, restarts, and verification |
| External API | New client version triggers rate limits or changes idempotency | API contract tests, concurrency caps, retries with backoff |
| Feature flags | One revision expects a flag different from the other | Define scope/cohorts, audit, and independent flag rollback |

Data rollback may require backup/restore independent of app rollback. A full database restore can also lose valid transactions committed after the snapshot timestamp; coordinate RPO/RTO and approvals. Never trigger a reflex restore on a 5xx spike if the root cause is simply a bad deployment solvable by traffic rollback.

### 11.3. Request Side Effects and Idempotency

Even at 5% of HTTP requests, v120 can send emails, process payments, or publish messages. If a client request fails after a side effect occurred, a retry hitting v119 might re-process it. Enforce:

- **Idempotency keys** for operations like payments and order creation.
- Transaction states in the database or event log distinguishing processed vs. unprocessed work.
- Outbox or reliable event publishing patterns to avoid "DB committed yet event never sent."
- Message/schema contracts understood by both revisions during coexistence.
- Cron/background job coordination: two concurrent revisions may **process the same job** if the app lacks coordination.

Traffic splitting adjusts **ingress request routing**; it does not replace idempotency or exactly-once business processing.

## 12. Scaling and Health During Canary

A newly created revision may start with low replica counts or scale to zero per rules. Sending 50% traffic right away to a revision lacking warm capacity or facing cold starts can spike latency even if the code is bug-free.

### 12.1. Each Revision Has Its Own Scale Template

Properties such as `minReplicas`, `maxReplicas`, and scale rules are revision-scoped in Container Apps. Editing a scale template can create a **new revision**; therefore, choose candidate scale settings **before** ramping traffic and verify the new revision name.

Example:

| Revision | Ingress Weight | minReplicas | maxReplicas | Meaning |
|---|---:|---:|---:|---|
| Stable v119 | 95% | 2 | 8 | Enough capacity for most traffic |
| Candidate v120 | 5% | 1 | 4 | Keep at least one replica to avoid cold starts during testing |

Numbers above are illustrative, not default quotas. In environments with scale-to-zero, `minReplicas=0` reduces idle costs yet increases initial request latency; evaluate against SLAs and observed traffic.

### 12.2. Startup, Readiness, and Liveness

**Startup probes** handle initialization time, **liveness** decides whether to restart stuck instances, and **readiness** checks whether an instance is fit to receive traffic. Configurations, probe types, and support depend on Container Apps protocols, ingress, and runtime.

Example app endpoints:

~~~text
/health/live  → 200 if the process can still handle work
/health/ready → 200 if HTTP server and essential dependencies are ready
/health/deep  → richer diagnostics for protected monitoring
~~~

Probes must be lightweight, use reasonable timeouts, require no user tokens if the platform does not send them, and never leak secrets. Avoid making readiness require every peripheral service—a shared hiccup could pull every revision out of rotation, widening an outage.

### 12.3. Distinguishing Startup Failures from Canary Failures

| Symptom | Common Cause | Decision |
|---|---|---|
| Image pull failed | Wrong tag/digest, missing registry rights, DNS/private endpoint | Send zero traffic; fix registry auth/network |
| Replica pending or crash-looping | OOM, wrong entrypoint/port, missing env/secret | Inspect system/console logs; fix image/template |
| Candidate healthy yet 5xx rises | Business logic bug, dependency auth, schema | Roll back traffic; investigate app/dependencies |
| High p95 during first few minutes | Cold start, cache warm-up, or scaling lag | Hold at 0/5% until warmed up and data collected |
| 429/503 when ramping from 5% to 50% | Scale limits or external API overloaded | Dial back traffic; check throughput, quotas, retries |
| Stable also fails after v120 runs | Shared migration/schema/secret/config | Investigate shared dependency; traffic rollback may not suffice |

For a canary to be meaningful, test traffic must run against a **production-equivalent configuration** for networking, identity, and data. A canary with the right image yet mismatched test environment settings yields misleading results.

### 12.4. Scaling Does Not Guarantee Exact Request Ratios

Traffic weights distribute at revision routing; KEDA/HTTP scalers determine each revision's replicas from configured metrics and rules. Observed distributions are affected by:

- Scale-to-zero and cold starts.
- Min/max replicas and scaling reaction time.
- Keep-alive, session affinity, and client distribution if enabled/supported.
- Request duration, retries, and long-lived connections.
- Requests hitting label URLs bypassing primary hostname weights.
- Background tasks consuming CPU/memory independently of HTTP traffic.

Therefore, never look at `trafficWeight=5` and assume the candidate cannot overload the database. A single candidate request might issue hundreds of times more queries or open more DB connections than stable.

## 13. Monitoring Per Revision Rather Than Only App-Wide Totals

To make promote/rollback decisions, compare **stable** against **candidate** over the same time window and equivalent request types.

### 13.1. Tag Telemetry with Revision Identity

Every request log should record:

- UTC timestamp, request/correlation ID, route, and response status.
- Processing duration, dependency calls, and timeout/retry counts.
- **Revision name or deployment version** obtained from platform-provided metadata/env or pipeline injection where supported.
- Trace ID linking ingress → API → database/messaging.
- Relevant schema versions and feature flags when troubleshooting.

Never log access tokens, authorization headers, connection strings, or sensitive personal data just for debugging. Attach container app/revision resource IDs to resource logs or custom dimensions using supported telemetry mechanisms.

### 13.2. Azure Monitor and Log Analytics

Common data sources:

| Source | Reflects | Limitations |
|---|---|---|
| Container Apps system logs | Startup, replicas, provisioning, platform events | Does not replace business telemetry |
| Container console logs | App stdout/stderr by revision/replica | Needs structuring and secret scrubbing |
| Azure Monitor metrics | CPU, memory, replicas, requests/network per supported metrics and dimensions | Not every metric exposes a revision dimension in all deployments |
| Application Insights/OpenTelemetry | Requests, exceptions, dependencies, distributed traces | Requires proper instrumentation and sampling |
| Azure Activity Log | Control-plane edits to app config, ingress, RBAC | Does not show individual HTTP requests |
| Azure Container Registry diagnostics | Image pushes/pulls and registry health per enabled logging | Does not explain app errors once image pull succeeds |

Never assume having a Log Analytics workspace means app logs already land in the expected table. Identify telemetry destinations, enable appropriate settings, and verify with test requests before release. When writing KQL, pick **table and field names from your actual workspace** rather than copying schemas between custom App Insights and container console logs assuming they match.

### 13.3. KQL Analysis Example with Custom Request Telemetry

Suppose the app emits request telemetry to Application Insights with a `revision` property in custom dimensions. The table/field names below are an **illustrative analytical pattern** for environments using the `AppRequests` table:

~~~kusto
AppRequests
| where TimeGenerated > ago(30m)
| extend rev = tostring(Properties["revision"])
| where rev in ("ca-orders-demo--v119", "ca-orders-demo--v120")
| summarize
    requests = count(),
    failed = countif(Success == false),
    p95Ms = percentile(DurationMs, 95)
  by rev, bin(TimeGenerated, 5m)
| extend errorRate = iff(requests == 0, 0.0,
                         todouble(failed) / todouble(requests))
| order by TimeGenerated asc, rev asc
~~~

**Conditions:** the `AppRequests` table and columns `Properties`, `DurationMs`, and `Success` must actually exist for your SDK/exporter; some workspaces use different schemas such as `requests`/`customDimensions`. Before turning a query into an alert, inspect your schema and confirm `revision` is populated accurately. In this sample, `errorRate` measures requests with `Success=false`, which may differ from 5xx if telemetry logic differs.

### 13.4. Recommended Alerts

1. Candidate 5xx/error rate exceeds an absolute threshold or exceeds stable beyond an accepted margin.
2. Candidate p95/p99 latency spikes on key routes.
3. Replica restarts/OOMs or revision provisioning failures.
4. Rising 403/5xx errors toward Key Vault, database, Storage, or partner APIs.
5. Candidate request volume deviates sharply from expected weights after a reasonable window.
6. App-level secret/traffic changes or registry permission changes outside approved pipelines.
7. A revision has traffic >0 yet zero healthy replicas.

Every alert should have an **owner**, runbook, observation window, noise filtering, and hold/cutover criteria. Never merely post notifications to a chat channel while advancing weights automatically on a timer.

## 14. Azure CLI for Inspecting Logs, Status, and Live Versions

For a configured app:

~~~bash
# List revisions and activation state
az containerapp revision list \
  -n "$APP" -g "$RG" -o table

# Inspect stable/candidate details
az containerapp revision show \
  -n "$APP" -g "$RG" \
  --revision "$CANDIDATE_REV" \
  -o json

# Stream console logs if supported by CLI/runtime in current environment.
az containerapp logs show \
  -n "$APP" -g "$RG" \
  --revision "$CANDIDATE_REV" \
  --type console \
  --tail 100

# System logs help inspect provisioning/startup errors.
az containerapp logs show \
  -n "$APP" -g "$RG" \
  --type system \
  --tail 100
~~~

Note that log commands return entries within current endpoint/retention limits. For production incidents, use a durable log collection system (Log Analytics, Application Insights, or another integrated tool) rather than relying solely on `--tail 100`.

### Recording Revisions and Images on Release

A deployment record might contain:

~~~yaml
application: ca-orders-demo
environment: production
stableRevision: ca-orders-demo--v119
candidateRevision: ca-orders-demo--v120
stableImage: myregistry.azurecr.io/orders-api:1.1.9
candidateImage: myregistry.azurecr.io/orders-api:1.2.0
candidateDigest: sha256:<digest-from-registry>
trafficBefore: "100/0"
trafficAfter: "95/5"
decision: "hold pending observation"
changeTicket: "CHG-EXAMPLE"
~~~

This is a **data template**, not an extra file to create. Store it in your organization's change/CI/CD system. `candidateDigest` must be the **actual** digest retrieved from registry/build metadata; never use placeholders as deployment sources.

## 15. Security, Identity, and Permissions with Multiple Revisions

Inside one container app, multiple revisions can run concurrently, yet this **does not automatically create an independent security boundary** between stable and canary. They may share app-level settings, managed identities, secret collections, networking, and backend services.

### 15.1. Common Risks

- Candidate holds untested code yet receives the **exact same production database permissions** as stable.
- Build pipeline holds overly broad repository push/delete rights; an image tag could be overwritten.
- App-level secrets get rotated and affect both stable and candidate revisions on restart.
- Public label endpoint leaks and allows directly invoking unverified code.
- Public ingress created without required authentication, WAF, or rate limiting.
- Broad Contributor permissions on the resource group allow bypassing release traffic controls.
- Candidate logs print authorization headers or sensitive payloads.

### 15.2. Control Principles

1. Use **managed identities** and appropriate Azure RBAC/ACR repository permissions for image pulls.
2. Enforce least-privilege **data-plane** permissions for SQL, Storage, and Key Vault; private networking does not replace auth.
3. Enforce immutable tags/digests and image scanning in pipelines, recording provenance when required.
4. Restrict who can run `az containerapp update` and `az containerapp ingress traffic set` in production.
5. Separate image build/push permissions from production traffic-shifting permissions.
6. Protect both the primary hostname and label URLs with authentication and ingress policies.
7. Audit secret refs, environment variables, and manage safe rotation while two revisions remain active simultaneously.
8. Require change approvals/auditing for promote/rollback actions.

**A revision is not a separate subscription or VNet.** If you must test untrusted code or high-risk changes against production data, use an independent **test container app, environment, or subscription** rather than relying on 0% weight as complete isolation.

### 15.3. Ingress and Egress Network Paths

If a container app uses internal ingress inside a privately networked Container Apps environment, verify DNS, VNet, routing, and client access to ingress. With public ingress, enforce TLS, identity/authorization, and WAF/rate limiting per architecture. Both stable and candidate call external APIs through the same egress policy; ramping traffic can change connection counts, SNAT pressure, and partner allowlist requirements.

Never assume HTTP traffic splitting automatically splits **outbound** database connections or query volume strictly 95/5. A single request on the candidate may hit the database multiple times more than stable.

## 16. Illustrative Lab: Identifying Revisions via HTTP Responses

To visualize traffic splitting directly, run a demo API returning its version number and request path. This sample **contains no production data** and is used solely to demonstrate routing, not to benchmark real system performance.

### 16.1. Minimal Node.js Application

Create `server.js` in a demo directory you own:

~~~javascript
const http = require("node:http");

const port = Number(process.env.PORT || 8080);
const version = process.env.RELEASE_VERSION || "v1";

const server = http.createServer((req, res) => {
  if (req.url === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "ready", version }));
    return;
  }

  if (req.url === "/") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({
      version,
      time: new Date().toISOString(),
      path: req.url
    }));
    return;
  }

  res.writeHead(404);
  res.end("not found");
});

server.listen(port, "0.0.0.0", () => {
  console.log("Demo running:", version, "port:", port);
});
~~~

Create `Dockerfile`:

~~~dockerfile
# Illustrative base image; pick a supported version/digest and scan for real use.
FROM node:22-alpine
ENV NODE_ENV=production
ENV PORT=8080
WORKDIR /app
COPY --chown=node:node server.js /app/server.js
USER node
EXPOSE 8080
CMD ["node", "server.js"]
~~~

Note that `EXPOSE 8080` is merely image metadata; the app must listen on `0.0.0.0:8080` and the Container App must set `targetPort=8080` for ingress to route requests to the right port.

Test on a machine with Docker:

~~~bash
docker build -t aca-revision-demo:1.0.0 .
docker run --rm -p 8080:8080 \
  -e RELEASE_VERSION=v1 \
  aca-revision-demo:1.0.0

# In another terminal
curl -i http://localhost:8080/
curl -i http://localhost:8080/health
~~~

Expect responses containing `"version":"v1"` and health 200. Next, you can build/push the image to ACR in an authorized environment, for example:

~~~bash
# ACR and push permissions prepared beforehand; no admin key used.
ACR_NAME="<lab-acr-name>"
IMAGE_REPO="aca-revision-demo"
IMAGE_TAG="1.0.0"

az acr build \
  --registry "$ACR_NAME" \
  --image "$IMAGE_REPO:$IMAGE_TAG" \
  .
~~~

This only builds/pushes one demo image. If an existing Container App uses that image, **updating the `RELEASE_VERSION` env var in the template** also creates a new revision to simulate another release even with the same image. However, that only exercises revision/split mechanics and **is not a substitute for a real v2 image build workflow**. In production, new code must be built, scanned, and deployed under its own tag/digest.

### 16.2. How to Verify 95/5 Traffic Is Actually Splitting

After configuring 95/5 and confirming both revisions are running and healthy:

1. Call the primary URL repeatedly from an authorized test source.
2. Record response version, HTTP status, and timestamp.
3. Count responses from v119 vs. v120.
4. Compare observed ratios against traffic config and per-revision logs.
5. Hit the candidate label URL to verify direct access while weight is 0% (if supported by ingress/labels).

Bash test snippet for demonstration purposes (**not a production load test**):

~~~bash
FQDN="<container-app-fqdn>"

for i in $(seq 1 100); do
  curl --silent --show-error --max-time 10 "https://$FQDN/"
  printf '\\n'
done
~~~

Observed counts may not hit exactly 95/5 across 100 requests. If every request hits one version, check traffic config, exact ingress hostname, caching/proxies, sticky sessions or supported routing rules, sample size, and actual logs. Never immediately blame Azure traffic splitting from a tiny sample or a client reusing a single connection/session.

### 16.3. Evidence to Save in the Lab

| Component | Evidence |
|---|---|
| Image | Registry/repository, tag/digest, and build timestamp |
| Stable revision | Name, image, active status, health, and weight |
| Candidate revision | Name, image/env version, active status, health, and weight |
| Test | Target URL, response codes, request counts per revision |
| Rollback | 100/0 config after rollback, new requests hitting stable |
| Logs | Request/console/system logs free of secrets |

Never send real personal data in lab requests. Demo data must be safely deletable per policy without triggering side effects on production payments, emails, or databases.

## 17. Automating Canary Releases in CI/CD

Running weight commands manually teaches the mechanics, yet production needs an **auditable, stoppable delivery path**.

### 17.1. Reference Pipeline

~~~mermaid
flowchart LR
    PR[Pull request] --> TEST[Unit/integration/security tests]
    TEST --> IMAGE[Build + scan + push image digest]
    IMAGE --> CREATE[Create candidate revision]
    CREATE --> SMOKE[Label URL smoke test]
    SMOKE --> W5[5% traffic]
    W5 --> GATE1{SLO pass?}
    GATE1 -->|Yes| W25[25% traffic]
    GATE1 -->|No| ROLLBACK[100% stable]
    W25 --> GATE2{SLO pass?}
    GATE2 -->|Yes| W100[Promote 100% candidate]
    GATE2 -->|No| ROLLBACK
    W100 --> MONITOR[Observe + keep stable backup]
~~~

`SLO pass?` gates must be enforced by real automated checks or human approvers per workflow. The Mermaid diagram above **is not a runnable pipeline** and does not perform rollbacks itself.

### 17.2. Build and Deploy Principles

- CI builds images once, applies immutable tags, and records digests plus SBOM/provenance if required by policy.
- CI/pipeline identities use **federated workload identity** or protected credentials instead of hardcoded long-lived service principal secrets.
- Separate image push rights (ACR) from Container App/production traffic update rights.
- Enforce concurrency locks or deployment gates to prevent **two pipelines from mutating traffic simultaneously** and overwriting each other.
- Read current revisions before setting explicit weights; read back API state afterward.
- Before raising weights, verify the candidate is **active**, healthy, free of image pull errors, and data-compatible.
- Record approver/automation identity, timestamp, traffic before/after, metrics, and rollback results in the change record.
- If metrics lack data or monitoring disconnects, **never treat silence as a pass**.

### 17.3. When Using IaC/Bicep/Terraform

Azure Resource Manager/Bicep/Terraform define Container App templates and ingress configurations. Yet an important operational caveat applies: **two control sources writing traffic weights** will collide.

For example, if a canary pipeline sets 95/5 via CLI and a subsequent IaC deployment applies `traffic latestRevision 100%`, IaC will overwrite the canary state. Therefore:

1. Define the single source of truth for the **app template** and for **traffic allocation**.
2. If IaC manages ingress traffic too, canary transitions must update IaC state/config or use coordinated pipelines.
3. Never apply manual tweaks and leave long-term drift unexplained.
4. After updating secrets/ingress/scaling/revisions, read back active revisions and weights.
5. Never let an IaC cleanup prune revisions needed for rollback without approval.

### 17.4. Avoid Auto-Promoting When Monitoring Has Insufficient Data

A 5% canary step might receive only a handful of requests per minute. If a pipeline waits 30 seconds, sees zero errors, and promotes, it can push a broken build because the **denominator is zero**. Require:

- Minimum observation time.
- Minimum successful request count or synthetic transaction count.
- Thresholds for error rate, timeouts, latency, and dependency failures.
- Comparison against stable baseline over the same time-of-day window to reduce noise.
- Hold criteria when telemetry is missing, broken, or the canary receives less traffic than expected.

Automated rollbacks also need anti-flapping policies: if a metric spikes slightly then dips, pipelines should not oscillate 0/100 ↔ 100/0 repeatedly without cooldowns or approval gates.

## 18. Costs and Capacity of Multiple Revisions

Canary traffic reduces **change risk**, yet does not always cost the same as a single-revision release. Under Container Apps billing, compute costs depend on plan/environment, vCPU/memory, replica count, active state, requests, and service components per current pricing rules.

### 18.1. Why Can Two Active Revisions Cost More Than One?

| Component | What Increases? |
|---|---|
| Stable + candidate replicas | More allocated or consumed CPU/memory, especially when `minReplicas` > 0 |
| Container images | Registry retains more images/digests for rollbacks |
| Logs/traces | Extra per-version logging can raise ingestion and retention |
| Double request processing | Synthetic tests, retries, and warm-up add traffic |
| Dependency connections | Two versions maintain separate connection pools and caches |
| Networking | Private endpoints, NAT/firewalls, and egress per architecture |
| People/process | Canary observation, verification, and multi-step operations |

An active revision at **0%** weight keeping `minReplicas=1` still consumes resources; conversely, scale-to-zero lowers idle compute yet introduces cold starts. Optimize around SLOs and your active pricing model rather than optimizing solely on "revision count."

### 18.2. Capacity Estimation Example

Suppose stable needs 6 replicas to serve 1,200 requests/second at measured throughput. Candidate v120 consumes 30% more CPU per request. Shifting 50% traffic to candidate with a low `maxReplicas` or insufficient capacity headroom can cause candidate to slow down or return 429/503 while stable stays healthy.

Measure:

- Requests per second and per-request complexity.
- CPU/memory per replica, startup latency, and scaling speed.
- Max concurrent requests/scale rules per supported configuration.
- DB pools, caches, and external API limits while both revisions run simultaneously.
- Headroom when rolling 100% of traffic back to stable.

**Rolling 100% back to stable requires stable to still have sufficient capacity.** If you scaled stable down to one replica to save costs right as canary hit 50%, a full rollback can trigger a capacity spike. Balance the cost of parallel capacity against recovery time.

### 18.3. Budgets and Stable Retention Windows

After promotion, keep a **retention window** for the stable revision/digest long enough to catch delayed regressions. Still, leaving every historical revision active forever inflates complexity and cost. Design:

1. Retain stable through a rollback window aligned with risk.
2. Deactivate afterward once the candidate proves stable and data remains compatible.
3. Clean up images/revisions per retention policies while keeping audit/DR artifacts required by policy.
4. Monitor Azure Cost Management, registry storage, Log Analytics, and networking.
5. Tag resources appropriately with `owner`, `application`, `environment`, and `costCenter`.

**Budget alerts are notifications, not hard spending caps.** Never adjust scale min/max or purge registry images solely from unverified estimates without checking SLO and rollback needs.

## 19. Troubleshooting Revisions, Traffic, and Rollbacks

Never alter image, ingress, secrets, networking, and scaling simultaneously when troubleshooting; doing so destroys root-cause isolation. Trace along **artifact → revision → replica → ingress → dependency → telemetry**.

### 19.1. Common Scenarios Table

| Symptom | Possible Cause | Investigation Steps |
|---|---|---|
| `az containerapp update` succeeds yet no new revision appears | Template did not actually change; identical image/tag ref; misread API response | Check `revision list`, `properties.template`, and image/digest |
| Candidate revision fails to run | Image pull denied/not found, wrong CPU architecture, crash, missing secret, or port | System logs, revision show, console logs, registry auth/network |
| Cannot assign 5/95 split across revisions | App in single mode, unsupported ingress/protocol, inactive revision, or invalid weights | Check `activeRevisionsMode`, HTTP ingress, revision status, and traffic |
| Revision active yet receives zero requests | 0% weight, wrong hostname/route, scaled to zero, tiny traffic | Inspect `ingress.traffic`, per-revision metrics, and labels |
| Label added yet URL unreachable | Label misapplied, internal ingress, network/DNS/access policy, unhealthy revision | Check revision labels, actual FQDN, DNS, and auth |
| Candidate returns 503 after ramping to 5% | Cold start, readiness, insufficient replicas, CPU/memory, or dependency overload | Check health/probes, replica count, scale rules, and logs |
| Observed ratio diverges far from 95/5 | Small sample, sessions/caching/retries, test traffic hitting label, misclassified telemetry | Increase sample, verify URLs and per-revision ingress logs |
| 5xx spikes on both stable and candidate | Shared database/schema/secret/network or downstream API failure | Cross-revision dependency traces and recent changes |
| Rolled back weight 100% to stable yet errors persist | Stable unhealthy, incompatible migration, or app-scope config changed | Verify stable health, DB schema, secrets/ingress |
| Cannot reactivate old stable revision | Revision purged, old image deleted, or missing pull permissions | Revision list, ACR digest, roles/networking |
| Rollback does not stop all side effects | In-flight requests/consumers still running, queued messages, committed transactions | In-flight work, idempotency, message dedup, stop/scale |
| Secret update has no effect | App-scope secret changed while running replicas/env hold startup values | Check secret refs, safe restart/redeploy on both stable and candidate |
| Revision count and bill increase | Leaving multiple active revisions/min replicas or long image retention | Clean up per policy after rollback window and check Cost Management |

### 19.2. Reusable Investigation Procedure

**Step 1 — Confirm scope.** Right subscription, resource group, container app, environment, revision, and time window?

~~~bash
az account show --query "{id:id,name:name}" -o table
az containerapp show -n "$APP" -g "$RG" \
  --query "{mode:properties.configuration.activeRevisionsMode,latest:properties.latestRevisionName,traffic:properties.configuration.ingress.traffic}" \
  -o json
~~~

**Step 2 — Inspect revisions.** Does the candidate exist, is it active and healthy? Right image? Check scale rules, probes, and secret references via `revision show` or Portal, redacting sensitive data before sharing.

**Step 3 — Inspect traffic targets.** Do weights sum properly with accurate rules? Is an unexpected `latestRevision` entry pointing elsewhere? Does the test label URL point to the exact candidate revision?

**Step 4 — Inspect startup logs.** Separate registry pull errors, environment variable issues, readiness failures, and runtime crashes. A revision with 0 healthy replicas should not receive more traffic.

**Step 5 — Inspect dependency paths.** Once the image runs and HTTP/health succeed yet API calls fail, check database schemas, message formats, managed identity, RBAC, private DNS, networking, and downstream rate limits.

**Step 6 — Inspect real SLOs/traffic.** Analyze request counts, error rates, p95 latency, and business metrics for stable vs. candidate over the same timeframe.

**Step 7 — Mitigate risk.** Pause promotion and return 100% ingress to the verified stable revision if appropriate; preserve evidence and perform root cause analysis. If the fault lies in a shared dependency, repair/restore the dependency per its own runbook.

### 19.3. Why Avoid "Deleting Candidate First and Asking Questions Later"?

Deactivating/deleting a revision too early destroys the environment needed to reproduce the bug, breaks rollbacks still referencing the candidate, and alters background worker behavior. Better sequence:

- First reduce candidate weight to 0% and verify stable.
- Check whether candidate has label endpoints, background jobs, or other internal traffic.
- Collect logs, revision template, image digest, deployment events, and test results.
- Only after security/operational sign-off, deactivate or purge per retention policy.

If the candidate carries a severe vulnerability and remains reachable via a label URL, prioritize blocking/disabling that access path immediately per runbook rather than only shifting primary hostname weights.

## 20. Real-World Scenario: Payment API Rollout on Azure

A company runs an ordering system inside a Container Apps environment in a production subscription. The `ca-orders-api` API uses a private ACR, managed identity for Key Vault, an Azure SQL database, and Azure Service Bus for order-processing events. The team prepares v120 with new payment logic. Requirements: **prevent payment bugs from affecting all customers**, enable fast rollback, and prevent duplicate transactions.

### 20.1. Release Design

| Component | Stable v119 | Candidate v120 |
|---|---|---|
| Image | `orders-api:1.1.9`, digest recorded | `orders-api:1.2.0`, scanned build |
| Revision | `ca-orders-api--v119` | `ca-orders-api--v120` |
| Mode | Multiple revisions | Multiple revisions |
| Initial ingress | 100% | 0% |
| During canary | 95% | 5% |
| Replicas | min 2, max 8 per measured load | min 1, max 4 per measured load |
| Data | Azure SQL schema compatible with both | Same database; old column not dropped |
| Identity | Least-privilege data-plane rights | Least privilege, no excess scope |
| Observability | Per-revision requests/errors/latency | Same + business success rate |

**Assumption:** the system handles 10,000 requests/minute at peak. A 5% canary receives roughly **500 requests/minute in long-run expectation** if routing and request mix align; this is not a per-minute guarantee and does not measure successful transactions. To evaluate payments, measure **eligible payment attempts** and success rates specifically, not just total HTTP requests.

### 20.2. Before Opening 5%

1. Build/scan image v120; verify digest and signatures/attestations if required by policy.
2. Review SQL migrations under expand–migrate–contract; v119 still reads data cleanly.
3. Deploy v120; verify ACR pull, image startup, health, identity, DNS, and private SQL connectivity.
4. Attach label `candidate` and test a **sandbox** transaction with an idempotency key.
5. Confirm v119 is healthy with enough capacity for 100% rollback.
6. Lock traffic changes to a single release pipeline.
7. Prepare the 100/0 rollback command and authorized executor.

### 20.3. Open Canary and Evaluate

Set 95/5 traffic and monitor:

- Per-revision HTTP error rates, especially `POST /payments`.
- Valid transaction rate, payment gateway timeouts, and retried transactions.
- Per-route p95/p99 latency.
- SQL deadlocks/connections and Service Bus dead-letter/retries.
- Container restarts/CPU/memory, health responses, and logs with correlation IDs.

If v120 returns numerous 500s on `POST /payments` while `GET /health` still returns 200, **health-only monitoring will miss the business degradation**. Business telemetry or synthetic payment tests are required to decide.

### 20.4. When Canary Fails

Suppose after five minutes v120's payment error rate hits 7% while v119 stays under 0.5%, breaching the approved stop threshold:

1. Hold the pipeline; do not ramp to 25%.
2. Set `v119=100%` and `v120=0%` on ingress.
3. Verify stable handles new requests; compare error rates and SQL health after the shift.
4. Inspect payment requests v120 sent to partners: reconcile **idempotency keys**, callbacks, and transaction states to prevent duplicates.
5. If v120 runs background consumers, handle stopping/pausing them separately per messaging procedures.
6. Preserve image digest, traces, logs, and change record; do not purge evidence.
7. Investigate root cause, add regression tests, and release a **fixed new revision**.

If v120 already executed a migration breaking the old schema, step 2 **does not guarantee service restoration**. A corresponding schema fix or data recovery plan is needed, avoiding blind database restores without accounting for valid transactions committed in the meantime.

## 21. Self-Assessment Lab Exercise

**Prompt:** A shipping API currently has stable revision `shipment-api--v5` (image tag `5.0.0`) and candidate `shipment-api--v6` (image tag `6.0.0`), both active. The app uses HTTP ingress and a shared Azure SQL database. Operations wants to test 10% traffic on the new version, ramp gradually to 100%, retain single-action rollback, and lose zero shipments.

Complete the following items:

1. Diagram the Container App, HTTP ingress, stable/candidate revisions, replicas, Azure SQL, and monitoring system.
2. Explain the differences among container image, revision, active revision, replica, and revision label.
3. Confirm **Multiple revision mode** is active; describe how to check via Azure CLI.
4. List which changes create a new revision: image, environment variable, scale rule, ingress traffic, secret value, CPU/memory.
5. Write the command setting traffic **90% v5 / 10% v6**, then read back `properties.configuration.ingress.traffic`.
6. Describe how to test v6 individually at 0% weight without exposing general traffic, using a label URL where supported.
7. Propose at least six metrics/logs to analyze separately by revision before increasing traffic.
8. Suppose a minute sees only 20 requests; explain why an observed 85/15 split does not prove routing is broken.
9. Design a 10% → 25% → 50% → 100% progression with **observation durations** and automatic stop criteria per step.
10. Write the 100% rollback command to v5 and post-rollback checks.
11. If v6 altered the Azure SQL schema in a way v5 cannot read, what happens on rollback? Propose a safe migration.
12. Describe how to handle duplicate Service Bus messages when both v5 and v6 process the same event type.
13. Compare cost/latency trade-offs of keeping `minReplicas=1` for the candidate versus scale-to-zero.
14. State the risk if an app-level secret rotates mid-rollout while the stable revision is not restarted.
15. Create a checklist of Azure RBAC, ACR pull, data access, and auditing permissions needed for the pipeline to adjust traffic.
16. Design a plan to clean up revisions/images after the rollback window without deleting artifacts needed for DR.

### Expected Command Skeleton

~~~bash
RG="rg-shipping-lab"
APP="shipment-api"
OLD="shipment-api--v5"
NEW="shipment-api--v6"

az containerapp revision set-mode -n "$APP" -g "$RG" --mode multiple
az containerapp revision list -n "$APP" -g "$RG" -o table

# After confirming both revisions are active and healthy:
az containerapp ingress traffic set \
  -n "$APP" -g "$RG" \
  --revision-weight "$OLD=90" "$NEW=10"

# Verify traffic configuration:
az containerapp show -n "$APP" -g "$RG" \
  --query "properties.configuration.ingress.traffic" -o json

# Rollback (while OLD remains active/healthy):
az containerapp ingress traffic set \
  -n "$APP" -g "$RG" \
  --revision-weight "$OLD=100" "$NEW=0"
~~~

All names above are **samples**, not commands to copy-paste against real production. Verify actual revision names in Azure first. Setting 100% back to the old revision is an **ingress rollback**; it does not revert SQL schemas, message processing, secrets, or app-scope configuration changes.

### Completion Criteria

The exercise is complete when learners can explain: which version actually receives traffic, what conditions are needed before promoting, how to measure per-revision 5xx/latency, when weight rollback suffices to recover, when data recovery plans are required, and why stable must not be deactivated/deleted before the rollback window closes.

## 22. Pre – During – Post Canary Checklist

### Before Release

- [ ] Identified the exact subscription/resource group/Container App and accountable owner.
- [ ] Image built, scanned, tagged with an immutable version, and digest recorded.
- [ ] Managed identity/registry permissions, private DNS/network, and secret refs verified.
- [ ] Database migrations/message schemas are compatible with both stable and candidate during coexistence.
- [ ] App runs in Multiple revision mode with HTTP ingress supporting traffic splitting.
- [ ] Stable revision is active/healthy with capacity for 100% traffic on rollback.
- [ ] Candidate image runs cleanly; health/readiness and label smoke tests pass.
- [ ] Per-revision telemetry is active with sufficient data/confidence for decisions.
- [ ] Authorized operator/pipeline for rollback and change ticket/approval are ready.

### During Rollout

- [ ] Weights set explicitly and `ingress.traffic` read back.
- [ ] Cross-checked revision names and tags/digests before every weight increase.
- [ ] Monitored request count, error rate, p95/p99, restarts, CPU/memory, and dependency metrics.
- [ ] Verified real business transactions or matching synthetic tests.
- [ ] Halted traffic increases if the candidate shows issues or telemetry drops data.
- [ ] Held canary steps long enough; never ran a continuous 5/25/50/100 script without pauses.
- [ ] Maintained immediate path back to stable if incident thresholds trigger.

### After Promotion or Rollback

- [ ] Read back traffic configuration; confirmed which version actually receives new requests.
- [ ] Verified health, SLOs, and all critical dependencies.
- [ ] Checked side effects/background consumers and duplicate business operations.
- [ ] Logged the change, decision maker, root cause, and outcome.
- [ ] Retained stable revision and image digest through the rollback window.
- [ ] Deactivated/cleaned up revisions only after verifying no label/internal paths remain in use.
- [ ] Reviewed costs for replicas, Log Analytics, image retention, and networking.

## 23. Controlled Lab Cleanup

In a lab, **clean up only revisions and resources you genuinely created**. Never delete Container Apps environments, ACRs, or resource groups shared with other teams' applications.

Before cleaning up, inspect:

~~~bash
az account show --query "{id:id,name:name}" -o table

az containerapp revision list \
  --name "$APP" \
  --resource-group "$RG" \
  --output table

az containerapp show \
  --name "$APP" \
  --resource-group "$RG" \
  --query "properties.configuration.ingress.traffic" \
  --output json

az resource list \
  --resource-group "$RG" \
  --output table
~~~

If you need to stop an active demo revision once its weight is back at 0%:

~~~bash
# Use only on TEST revisions after confirming zero remaining traffic.
# az containerapp revision deactivate \
#   --name "$APP" --resource-group "$RG" \
#   --revision "$CANDIDATE_REV"
~~~

Never delete older images in ACR while still needed for rollback, replay/auditing, or disaster recovery. Deleting a Container App, environment, or resource group requires scoped verification and separate approval; **never run automated bulk-delete commands just to "tidy up revisions."**

## 24. Key Takeaways

- A **Revision** is an immutable snapshot of template properties managed by Container Apps; a **replica** is a running instance of a revision. An image tag is not a revision and may not uniquely represent a digest.
- **Single revision mode** suits simple release flows; **Multiple revision mode** allows multiple active revisions and weighted control of **HTTP ingress traffic**.
- **Traffic splitting** requires explicit weights, healthy revisions, and per-revision monitoring. Traffic ratio does not directly dictate replica counts or database query volume.
- A **Revision label** is a direct route to a specific revision where ingress supports it—not a weight replacement and not a security boundary.
- **Fast rollback** typically shifts 100% of ingress back to the stable revision while it remains active/available with sufficient capacity and data compatibility.
- **Code rollback does not roll back databases/schemas, secrets, queue messages, or side effects.** Design backward compatibility, idempotency, and backup/DR before releasing.
- **Observability and security** are mandatory: image digests/registry auth, startup/health checks, per-revision SLOs, Azure RBAC, private networking, and change auditing.
- **Cost** depends on multiple active replicas, scale rules, logs, registries, and networking; keep stable long enough for rollback without leaving old revisions running endlessly without purpose.

The goal of a canary is not "sending exactly 5% of traffic to the new version," but **gathering enough evidence to safely increase traffic or return traffic to the stable version before impact spreads**. A release is complete only when service quality, rollback readiness, and shared data integrity are all verified.
