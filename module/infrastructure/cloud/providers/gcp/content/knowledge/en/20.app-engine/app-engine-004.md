# Scaling, instance classes, and traffic management

An e-learning API might serve only a few requests per minute at night yet spike sharply when course enrollment opens. If too few instances are provisioned, users face high latency or errors; if too many instances are always kept running, costs increase even with zero traffic. When releasing a new version, another failure mode can occur: the application deploys successfully, yet all users are routed to the new code before testing.

**App Engine** is a Google Cloud managed application platform. This lesson belongs to the **App Engine** chapter of the **CLOUD_PROVIDERS_GCP** module, connecting concepts from projects, IAM, VPC, compute services, and reliability/cost monitoring to three key decisions: **choosing a scaling mode**, **sizing each instance**, and **distributing traffic across versions**. The content covers both the **standard environment** and the **flexible environment**, because their configuration fields are not interchangeable.

**Learning objectives:** after this lesson, you will be able to:

1. Distinguish App Engine application, service, version, and instance.
2. Choose Standard automatic, basic, or manual scaling; and Flexible automatic/manual scaling.
3. Select the right F/B `instance_class` for the scaling type, or CPU/RAM in Flexible.
4. Explain the impact of cold starts, concurrency, min/max instances, and quotas on SLOs and cost.
5. Deploy a version without shifting traffic, split traffic in a controlled way, verify, and roll back.
6. Read operational metrics, diagnose common failures, and practice in a test project.

## 1. App Engine model: application → service → version → instance

App Engine creates an **application** inside a Google Cloud project in a **location** chosen at initialization (an existing application's location cannot be changed through normal updates). One application can have multiple **services** such as `default`, `api`, and `worker`. Each service has multiple **versions** of code/config; each version runs on one or more **instances**.

~~~mermaid
flowchart TB
  APP["App Engine application<br/>in project"] --> API["Service: api"]
  APP --> WORKER["Service: worker"]
  API --> V1["Version v1<br/>traffic 90%"]
  API --> V2["Version v2<br/>traffic 10%"]
  V1 --> I1["Instances v1<br/>autoscaling"]
  V2 --> I2["Instances v2<br/>autoscaling"]
  WORKER --> W["Current version<br/>separate scaling"]
~~~

**Scaling is configured per version** via `app.yaml`; traffic splitting is configured at the **service** level to distribute requests across versions of that same service. Two versions serving concurrently can both consume resources and incur charges.

| Concept | Key takeaway |
| --- | --- |
| **Application** | A single App Engine app bound to a project/location; not the name of an instance. |
| **Service** | An independently deployed component; `default` is typically the default entrypoint. |
| **Version** | A deployed bundle of code + config; may receive a share of traffic or zero traffic. |
| **Instance** | Execution unit running a version, receiving requests and consuming CPU/RAM per environment. |
| **Traffic split** | Distributes requests **without a specified version** among versions of one service. |
| **Version URL** | Reaches a specific version directly; **bypasses the shared service URL split**. |

A version receiving **0% traffic** does not mean no one can access it: anyone with the version-specific URL can still send requests unless additional protections exist. Never use traffic splitting as an IAM boundary, authentication barrier, or way to hide test environments.

## 2. Choose Standard or Flexible before tuning scaling

| Criterion | Standard environment | Flexible environment |
| --- | --- | --- |
| Infrastructure | App Engine-managed runtime sandbox. | Containers running on platform-managed Compute Engine VMs, flexible in runtimes/dependencies. |
| Scaling | **Automatic, Basic, Manual**. | **Automatic, Manual**; no Basic mode as in Standard. |
| Instance sizing | `instance_class` **F** or **B** series. | `resources`: `cpu`, `memory_gb`, `disk_size_gb`. |
| Scale to 0 capability | **Automatic/Basic** can scale to 0 under suitable conditions. | Active versions must keep at least **one instance**; do not expect Standard-like scale-to-zero in Flexible. |
| Idle cost | Can drop via dynamic instances; `min_instances` and manual create a baseline. | Always incurs compute charges for configured baseline instances. |
| Startup and scale-out | Generally faster, though loading requests/cold starts still occur. | VM/container initialization can take longer; needs headroom capacity. |
| Customizability | Bounded by supported runtimes and sandbox constraints. | Deeper OS/runtime and package customization via container model. |

**Do not copy** Standard's `min_instances` and `max_instances` directly into Flexible: Flexible uses `min_num_instances`, `max_num_instances`, and different CPU parameters. Choose the environment based on runtime and operational requirements first, then optimize instances.

## 3. Standard environment: three scaling modes

### 3.1. Automatic scaling — handling fluctuating traffic

Automatic is the default in Standard. App Engine monitors request rate, latency, CPU, or throughput utilization to scale instances up or down. Low-request workloads can scale to 0, and new requests arriving afterward may trigger a **cold start/loading request**.

Example `app.yaml` for a Standard Python API version:

~~~yaml
runtime: python312
service: api
instance_class: F2
automatic_scaling:
  min_instances: 1
  max_instances: 10
  target_cpu_utilization: 0.65
  max_concurrent_requests: 30
~~~

| Field | Meaning | Trade-offs |
| --- | --- | --- |
| `instance_class: F2` | CPU/RAM capacity of a single instance. | Larger classes handle more load at a higher hourly rate. |
| `min_instances: 1` | Maintains a minimum for a traffic-serving version under product conditions. | Reduces cold starts but incurs baseline cost; requires appropriate warmup handling. |
| `max_instances: 10` | Caps the number of instances the version scales out to. | Controls resources/cost; setting too low can raise latency/503s during peaks. |
| `target_cpu_utilization: 0.65` | CPU target used as a scaling signal. | Not a hard CPU cap or a guarantee CPU stays at 65%. |
| `max_concurrent_requests: 30` | Max concurrent requests scheduled per instance. | Setting too high can slow responses if code does not handle concurrency well. |

**Note on default changes:** for new projects created **after March 2025**, App Engine Standard enforces a default cap of **20 automatic instances** if `max_instances` is unspecified; older applications may have different defaults. Always declare limits intentionally and check quotas/current documentation rather than relying on defaults. For `min_instances`, documentation requires enabling **warmup requests** with proper handling for the mechanism to work as expected.

### 3.2. Basic scaling — start on demand, shut down when idle

Basic creates an instance when a request arrives and shuts it down after `idle_timeout` if inactive. Suitable for intermittently used services or initialization logic needing Basic semantics, though sudden traffic bursts may wait for instance startup.

~~~yaml
runtime: python312
service: report-worker
instance_class: B2
basic_scaling:
  max_instances: 3
  idle_timeout: 10m
~~~

`max_instances` caps active instances for the version; `idle_timeout` is the period without requests before shutting down an instance. It is **not** a per-request duration limit. Basic has different startup and instance-addressability behavior from automatic; use it only when the application specifically needs it.

### 3.3. Manual scaling — fixed instance count

Manual keeps the specified number of instances running even when there is no traffic:

~~~yaml
runtime: python312
service: persistent-worker
instance_class: B2
manual_scaling:
  instances: 2
~~~

The upside is pre-warmed capacity and support for workflows requiring long-lived processes or stable instance addressing. The downside is paying for idle instances and **not scaling out automatically** at peak unless configuration is updated and deployed/operated accordingly.

If a workload is actually event-driven queue processing, do not default to manual scaling to keep an infinite polling loop alive. Compare Cloud Tasks, Pub/Sub, Cloud Run, or other options against requirements, quotas, and cost models.

### 3.4. Quick comparison table

| Standard mode | Instance classes | Scales with load | Scales to 0 when idle | Use when |
| --- | --- | --- | --- | --- |
| **Automatic** | F1, F2, F4, F4_1G | Yes | Possible, if min/idle and conditions permit | HTTP APIs/websites with variable load. |
| **Basic** | B1, B2, B4, B4_1G, B8 | Yes, on request while below max | Yes, after idle timeout | Intermittent load needing backend instance traits. |
| **Manual** | B1, B2, B4, B4_1G, B8 | Does not autoscale | Not via standard idle rules | Fixed capacity or workflows requiring persistent instances. |

Modes have **different request timeout, startup, and background processing limits**; for instance, Standard Automatic typically has a **10-minute** HTTP request limit, whereas Basic/Manual can reach **24 hours** depending on environment/docs. Never assume an HTTP handler should run near the timeout limit: long tasks belong in a queue/background workflow with state tracking and proper retries.

## 4. Instance classes and Flexible resources

### 4.1. Choosing a Standard class with metrics

An instance class determines **relative CPU capacity**, memory limits, and instance-hour cost. Common classes:

| Class | Reference RAM limit | Scaling group |
| --- | ---: | --- |
| F1 | 384 MB | Automatic |
| F2 | 768 MB | Automatic |
| F4 | 1,536 MB | Automatic |
| F4_1G | 3,072 MB | Automatic |
| B1 | 384 MB | Basic, Manual |
| B2 | 768 MB | Basic, Manual |
| B4 | 1,536 MB | Basic, Manual |
| B4_1G | 3,072 MB | Basic, Manual |
| B8 | 3,072 MB | Basic, Manual |

Published CPU figures for F/B are **relative compute capacity**, not a guaranteed fixed physical GHz frequency. The memory limit covers both the application and the runtime; with Java or heavy libraries, runtime overhead can be substantial.

For example, a simple JSON API may run fine on F1 under light load, yet hit CPU or memory limits at peak. Upgrading to F2 can reduce per-request processing time; however, it will not fix a slow database query. **Use p95/p99 latency, CPU/memory utilization, OOM errors, and cost** to pick a class; do not choose F4_1G just because it is “the largest”.

### 4.2. Flexible: allocate CPU/RAM/disk instead of F/B classes

App Engine Flexible runs on VMs/containers, configures resources via `resources`, and supports only **automatic or manual** scaling.

Condensed `app.yaml` example for a Python Flexible application:

~~~yaml
runtime: python
env: flex
service: api-flex
resources:
  cpu: 2
  memory_gb: 2.3
  disk_size_gb: 10
automatic_scaling:
  min_num_instances: 1
  max_num_instances: 5
  cool_down_period_sec: 180
  cpu_utilization:
    target_utilization: 0.6
~~~

This is a **scaling configuration example**, not complete deployable source: Flexible also requires application code/entrypoint compatible with the runtime, service, health checks, and dependencies. CPU/RAM/disk values must stay within product-supported bounds.

| Flexible key | Meaning |
| --- | --- |
| `resources.cpu` | Number of vCPUs requested per instance. |
| `resources.memory_gb` | RAM allocated to the application, excluding some system overhead per docs. |
| `resources.disk_size_gb` | Instance disk capacity; not durable storage. |
| `min_num_instances` / `max_num_instances` | Instance count bounds during automatic scaling. |
| `cool_down_period_sec` | Wait period before using a new instance's load signal for scaling. |
| `cpu_utilization.target_utilization` | Autoscaler CPU utilization target. |
| `target_concurrent_requests` | Flexible option with specific support status; verify limits and version before use. |

Flexible defaults to automatic scaling and typically keeps **at least one active instance**, with current defaults often setting `min_num_instances: 2` if not overridden. Do not apply Standard's `min_instances: 0` to Flexible. For Flexible manual scaling:

~~~yaml
runtime: python
env: flex
service: fixed-api
resources:
  cpu: 2
  memory_gb: 2.3
manual_scaling:
  instances: 2
~~~

Every running Flexible version can incur **VM, disk, and related infrastructure charges** even when its traffic share is 0. Cost and scaling must therefore be evaluated alongside a plan to stop/delete old versions and a defined rollback retention window.

## 5. Sizing for load and controlling cold starts

### 5.1. Estimate concurrency before choosing max instances

A steady-state approximation:

\[
\text{Concurrent requests} \approx \text{RPS}\times\text{Average latency (seconds)}
\]

With 300 requests/second and an average latency of 0.2 seconds per request, concurrency is roughly **60**. If one instance handles **15 concurrent requests effectively**, the minimum ideal estimate is **4 instances**. For production sizing, add headroom for peaks, uneven load distribution, p95/p99, warmup, GC, retries, and dependencies.

**Do not treat `max_concurrent_requests` as measured throughput.** Allowing 30 concurrent requests does not mean the application can process 30 requests within SLO. For example, a service with single-threaded blocking code may bottleneck even while App Engine still has open request slots.

| Observation | Likely cause | Action |
| --- | --- | --- |
| Very high CPU, long request queue | Small instance class or CPU-heavy code | Profile CPU, optimize code, test higher F class or more instances. |
| Low CPU, latency still high | Database, external API, locks, network I/O | Tracing, timeouts, and connection pools; do not blindly add CPU. |
| Scaling instances overloads database | Too many connections or concurrent queries | Cap pool/RPS, cache, tune DB capacity and backpressure. |
| Long idle period, slow first request | Cold start/loading request | Evaluate `min_instances`, warmup, and reduce heavy startup work. |
| Peak hits out-of-instances or 503 | Hit `max_instances`, quota, or capacity | Check quotas, peak profile, RPS, and cost limits. |
| Slow Flexible scale-up | VM/container startup takes time | Provision min instances, optimize container/startup and readiness. |

### 5.2. Warmup requests in Standard Automatic

App Engine can send `GET /_ah/warmup` to prepare an instance before user requests arrive. To enable in Standard:

~~~yaml
runtime: python312
instance_class: F2
inbound_services:
  - warmup
automatic_scaling:
  min_instances: 1
  max_instances: 8
~~~

The application can provide a `/_ah/warmup` handler that performs **short, idempotent initialization without logging secrets**. Warmup is **best effort**: the first request to an unstarted version or a very rapid traffic surge can still hit a loading request. Therefore measure actual cold-start latency instead of assuming warmup guarantees 0 ms.

**Trade-off:** `min_instances > 0` reduces cold-start risk at the expense of higher instance hours. `min_idle_instances` can also keep idle instances warm for fast serving, though billing behavior and applicability to traffic-serving versions should be verified before use. Warmup can consume extra CPU/time if the handler does heavy work.

### 5.3. Autoscaling caps are not attack protection

`max_instances` caps scale, but under abnormal traffic the remaining instances can still be overwhelmed. Combine authentication, Cloud Armor/appropriate load balancing, gateway/app rate limits, timeouts, Cloud Tasks quotas, and connection pool controls. Also monitor costs when old and new versions run side by side.

Never store unique login sessions in a single instance's RAM: the next request may land on another instance or version. Use **shared state** such as an appropriate database/cache, design secure sessions/cookies, and ensure compatible schema migrations while two versions coexist.

## 6. Managing traffic between versions

App Engine allows running multiple versions of **the same service** concurrently, shifting 100% of traffic, or splitting traffic by weight. That is the foundation for **canary**, **A/B testing**, **blue-green**, and **rollback**; a successful deployment only creates a version and does not prove the new version is safe for production.

### 6.1. Deploy and promote are separate operations

- **Deploy:** uploads code and configuration to App Engine, creating or updating a version.
- **Promote / set traffic:** decides which versions receive requests sent to the **shared service URL**.
- **Direct testing:** calls the **version-specific URL** to verify a new version before splitting traffic to it.
- **Rollback:** shifts traffic back to a stable version, then inspects data, logs, and root causes.

~~~mermaid
flowchart LR
  U["Request to service URL"] --> ROUTE["App Engine traffic routing"]
  ROUTE -->|"95%"| V1["Version stable-v1"]
  ROUTE -->|"5%"| V2["Version canary-v2"]
  TEST["Direct test<br/>version URL"] -. "Bypasses service URL split" .-> V2
~~~

**Security note:** a version at 0% is still reachable via its version URL. If it touches real data, apply appropriate app auth/IAM/firewalling; 0% traffic is not a mechanism to “hide” a version.

### 6.2. Three traffic-splitting methods

| Method | How it routes | When suitable | Risks |
| --- | --- | --- | --- |
| **IP** | Hashes sender IP address to assign a bucket to a version. | Simple distribution by client IP source. | NAT/proxies group many users behind one IP; mobile IPs change, causing unstable experiences. |
| **Cookie** | Uses the `GOOGAPPUID` cookie for stable per-user bucketing. | A/B or canary testing needing users pinned relatively consistently to one version. | Clients must store/return cookies; caching and internal request forwarding require care. |
| **Random** | Picks a version per request according to weights. | Independent request distribution where stickiness is unnecessary. | The same user may hit different versions on consecutive requests. |

For example, setting traffic to `stable-v1=0.95` and `canary-v2=0.05` is a **routing target**, not a guarantee that exactly 5% of users or business transactions occur in a short window. With IP splitting, proxies can skew distribution heavily; with cookies, mobile or backend-to-backend clients must actively retain the `GOOGAPPUID` cookie.

**Caching:** when two versions return different content for the same URL, caches/CDNs might store one version's response and serve it to users routed to the other version. Design cache keys, `Vary` headers, and versioned static assets properly; never store sensitive session data in routing cookies.

### 6.3. gcloud: inspect versions and traffic before changing

These are **read-only** commands after selecting the right project:

~~~bash
export PROJECT_ID="YOUR_LAB_PROJECT_ID"
export SERVICE="default"

gcloud config set project "$PROJECT_ID"
gcloud app services list --project="$PROJECT_ID"
gcloud app versions list --service="$SERVICE" --project="$PROJECT_ID"

# View current traffic split configuration and serving versions
gcloud app services describe "$SERVICE" --project="$PROJECT_ID"
~~~

Before production changes, capture a snapshot of current traffic splits and the stable version name. Do not rely on a version name containing `stable` or `canary` to know whether it actually has errors.

### 6.4. Controlled canary with `set-traffic`

Assume the service has two deployed versions: `stable-v1` and `canary-v2`. After system owner approval, split 95/5 by cookie:

~~~bash
# WRITE OPERATION: modifies live traffic weights of the default service
gcloud app services set-traffic "$SERVICE" \
  --project="$PROJECT_ID" \
  --splits=stable-v1=0.95,canary-v2=0.05 \
  --split-by=cookie

# Read back state after the change
gcloud app services describe "$SERVICE" --project="$PROJECT_ID"
~~~

Weights summing to 1 are easiest to read; the CLI accepts relative weights, though normalizing to 100% makes reviews exact. You can ramp through stages **1% → 5% → 25% → 100%** while SLOs hold, keeping each observation window long enough for representative traffic, including peaks.

**Release condition:** the new version must be compatible with the old version across database schemas, caches, APIs, background tasks, and sessions. If v2 ran an incompatible migration, rolling back traffic to v1 may **not** restore the app. Prefer **expand → migrate → contract** migrations and decouple database rollouts from application cutovers.

### 6.5. Fast rollback to a stable version

When 5xx/p99 rates or business errors cross stop thresholds:

~~~bash
# WRITE OPERATION: restores 100% traffic to a verified good version
gcloud app services set-traffic "$SERVICE" \
  --project="$PROJECT_ID" \
  --splits=stable-v1=1

gcloud app services describe "$SERVICE" --project="$PROJECT_ID"
~~~

After rolling back, check **HTTP error rates, latency, logs, and database state**. Do not immediately delete the faulty version while investigative evidence is still needed. If sticky cookie routing was active, verify actual routing behavior after cutover rather than trusting CLI success alone.

### 6.6. Shifting 100% traffic: immediate or gradual migration?

When switching from one version to another, App Engine offers **traffic migration** to reduce cold-start/latency spikes in supported scenarios. Command:

~~~bash
# Only use after approval and verifying support for your scaling type/version
gcloud app services set-traffic "$SERVICE" \
  --project="$PROJECT_ID" \
  --splits=canary-v2=1 \
  --migrate
~~~

`--migrate` asks App Engine to shift traffic gradually so the new version's autoscaler can spin up instances; effectiveness and limitations depend on environment/version type. Do not assume it forces every multi-version split algorithm to migrate gradually. Shifting 100% immediately to a version with no warm instances can trigger a **loading-request latency spike**.

## 7. Safe release workflow

| Phase | Actions | Gate to proceed |
| --- | --- | --- |
| **1. Prepare** | Test code, verify schema/data compatibility, set instance class/scaling and budget. | A known stable version exists to roll back to. |
| **2. Deploy no-promote** | Create the new version without changing shared service traffic. | Deployment finishes; version URL is testable. |
| **3. Smoke test** | Test endpoints, auth, DB, Cloud Storage, task queues; inspect logs. | All essential checks pass. |
| **4. Canary** | Shift 1–5% of requests using the appropriate split method. | Sufficient sample size; p95/p99, error rates, and business KPIs look normal. |
| **5. Expand** | Increase ratio carefully while watching peaks, cold starts, and instance counts. | SLOs, quotas, budgets, and data integrity remain healthy. |
| **6. Full rollout** | Shift 100% and monitor post-release. | No regressions; dependencies remain healthy. |
| **7. Clean up** | Evaluate deleting unused versions/instances after the rollback window. | No routes, jobs, URLs, or dependencies point to old versions. |

**Retained versions are not free by default:** manual/Flexible versions can keep compute running even with zero traffic; Standard Automatic can scale down when idle depending on conditions. Cleanup must consider rollback windows, logs/snapshots, and clients calling version URLs directly.

## 8. Hands-on Lab: two Standard versions and a 10% canary

**Goal:** deploy two versions of **a dedicated lab service**, observe which version answers requests, shift to a 90/10 split, then return to 100/0. The lab does not benchmark peak performance; it verifies **deployment, routing, and rollback** accurately.

**Prerequisites:** the project **already has an App Engine application** and appropriate billing; your account has permissions to deploy App Engine, manage traffic, and view logs; Python runtime is supported by App Engine Standard; `gcloud`, a shell, and required build services are available. **Do not run in a production project.** Creating an App Engine application for the first time locks a **location that cannot be directly changed**, so this lab **does not create the application** or pick a region for you.

### 8.1. Verify the project and that the service does not exist yet

~~~bash
export PROJECT_ID="YOUR_APPROVED_LAB_PROJECT"
export SERVICE="traffic-lab"

gcloud config set project "$PROJECT_ID"
gcloud app describe --project="$PROJECT_ID"
gcloud app services list --project="$PROJECT_ID"
~~~

If the `traffic-lab` service **already exists**, stop and use a dedicated lab project or another approved service name. Never overwrite another team's service. If `gcloud app describe` reports no App Engine application exists, ask an administrator to select a policy-compliant location before continuing.

### 8.2. Create the sample app locally

Create a dedicated directory `traffic-lab/` with three files:

**`app.yaml`**

~~~yaml
runtime: python312
service: traffic-lab
entrypoint: gunicorn -b :$PORT main:app
instance_class: F1
automatic_scaling:
  min_instances: 0
  max_instances: 3
  target_cpu_utilization: 0.65
~~~

**`requirements.txt`**

~~~text
Flask>=3,<4
gunicorn>=22,<24
~~~

**`main.py`**

~~~python
import os
from flask import Flask, jsonify

app = Flask(__name__)

@app.get("/")
def home():
    return jsonify(
        service=os.environ.get("GAE_SERVICE", "unknown"),
        version=os.environ.get("GAE_VERSION", "local"),
        status="ok",
    )
~~~

Both lab versions use **the same source**, while `GAE_VERSION` in the JSON response reveals which version served each request. Using `F1`, `min_instances: 0`, and `max_instances: 3` keeps compute usage small; **it does not guarantee the lab is free**, especially as builds, requests, and logs occur. For real applications, pin tested dependency versions and configure proper security/observability.

### 8.3. Deploy the first version and the canary

Inside the directory containing `app.yaml`:

~~~bash
# Run only when traffic-lab is a new service you own
# Deploy first version; in a new lab service it may receive traffic
gcloud app deploy app.yaml \
  --project="$PROJECT_ID" \
  --version=v1lab \
  --quiet

# Read back: confirm service traffic-lab has v1lab
gcloud app versions list --project="$PROJECT_ID" --service="$SERVICE"

# Second version does NOT automatically shift shared traffic on deploy
gcloud app deploy app.yaml \
  --project="$PROJECT_ID" \
  --version=v2lab \
  --no-promote \
  --quiet

gcloud app versions list --project="$PROJECT_ID" --service="$SERVICE"
~~~

Normally `v1lab` receives traffic for the new lab service; `v2lab` is deployed without being promoted. Inspect the actual `TRAFFIC_ALLOCATED` column/output before proceeding, as default deploy behavior can be affected by CLI/project policies. A version serving 0% can still be tested via its **version-specific URL** if routes/authorization permit.

**You do not need** to change application code between the two deploys to demonstrate version routing; in real releases, however, v2 must be a distinct artifact with clear revision and test evidence.

### 8.4. Split 90/10 by cookie and observe

~~~bash
# Write operation only on the dedicated service created by this lab
gcloud app services set-traffic "$SERVICE" \
  --project="$PROJECT_ID" \
  --splits=v1lab=0.9,v2lab=0.1 \
  --split-by=cookie

gcloud app services describe "$SERVICE" --project="$PROJECT_ID"
~~~

Get the **service** URL from the Console or App Engine describe output, then call it with an HTTP client that preserves cookies:

~~~bash
SERVICE_URL="https://URL_OF_TRAFFIC_LAB_SERVICE"

# Cookie jar retains GOOGAPPUID so the same client stays relatively pinned to a version
curl --silent --show-error \
  --cookie-jar ./lab-cookies.txt \
  --cookie ./lab-cookies.txt \
  "$SERVICE_URL/"

curl --silent --show-error \
  --cookie-jar ./lab-cookies.txt \
  --cookie ./lab-cookies.txt \
  "$SERVICE_URL/"
~~~

The JSON output contains a `version` field equal to `v1lab` or `v2lab`. A single client reusing one cookie **cannot verify an exact 10% total traffic share**; you need multiple independent clients/cookies and enough requests to estimate the ratio. Never run high-load traffic generators against a project hosting other services.

### 8.5. Roll back and clean up lab resources

~~~bash
# Shift all traffic of the lab service back to v1
gcloud app services set-traffic "$SERVICE" \
  --project="$PROJECT_ID" \
  --splits=v1lab=1

gcloud app services describe "$SERVICE" --project="$PROJECT_ID"
gcloud app versions list --service="$SERVICE" --project="$PROJECT_ID"

# Only after confirming traffic-lab was created by this lab and has no remaining users
gcloud app services delete "$SERVICE" \
  --project="$PROJECT_ID" \
  --quiet

# Verify the service is gone
gcloud app services list --project="$PROJECT_ID"
~~~

Deleting a **service** also deletes its attached versions. Therefore **do not** run it if `traffic-lab` has users, workers, or dependent cron/tasks; clean up only after verifying the resource you created. If you used the `default` service for another experiment, do not use this lab service deletion command on `default`.

The local `lab-cookies.txt` file stores lab cookies; clean it up per your test environment policy. The App Engine application/project **is not** deleted; logs, build artifacts, Cloud Storage staging buckets, or related resources may persist after deleting the service and must be managed separately per permissions and policy.

## 9. Operations: measuring performance, reliability, and cost

### 9.1. Dashboards per service **and version**

For fair canary comparisons, segment metrics by **service, version, environment, and time window** instead of looking only at application-wide totals:

| Signal group | What to watch | Example issue |
| --- | --- | --- |
| **HTTP latency p50/p95/p99** | Detect slow requests during cold starts or peaks. | v2 has higher p99 than v1 at similar CPU. |
| **5xx/4xx and success rate** | Separate server errors from client errors; track app errors per version. | v2 5xx spikes during a 5% traffic test. |
| **Instance count, instance hours** | Track running instances and compute consumption. | Both v1 and v2 keep min instances, doubling baseline cost. |
| **CPU/memory and out-of-memory** | Spot undersized classes or runtime memory pressure. | F1 frequently OOMs; a larger class may be warranted. |
| **Pending/loading latency** | Identify queueing and cold starts. | First request after an idle period is very slow. |
| **Dependency metrics** | Cloud SQL connections, Datastore/Firestore, VPC/network/external APIs. | Instance scale-out exhausts DB connection limits. |
| **Business SLIs** | Whether orders/registrations/logins succeed. | HTTP 200 returned, but business logic writes wrong data. |
| **Billing/quotas** | Catch surges in instance-hours, requests, egress, logs, and quotas. | Small canary share still holds many baseline instances. |

Use **Cloud Monitoring**, the App Engine Dashboard/Versions view, **Cloud Logging**, and Error Reporting appropriately. Exact metric names and labels depend on runtime and application instrumentation; never build alerts on metrics that do not exist.

### 9.2. Canary stop criteria

Before ramping percentages, document clear criteria so the on-call engineer **can decide immediately**:

- v2 error rate does not exceed SLO thresholds or diverge significantly from v1 under comparable load.
- p95/p99 stays within agreed bounds; first-request latency is tracked separately.
- No database migration errors, breaking API response changes, or abnormal error budget burn.
- `max_instances`, quotas, memory, and cost stay within approved limits.
- If an incident occurs, rollback commands, an accountable owner, and prior version verification results are ready.

**Statistical trap:** 1% traffic over 5 minutes may yield too few samples to catch rare bugs. Keep observation windows representative; choosing peak/busy hours is a deliberate risk decision, not just glancing at instantaneous 5xx percentages.

### 9.3. Estimating total cost

App Engine charges do not depend solely on HTTP request counts. An architecture-level estimate:

\[
\text{Total cost}\approx
\text{instance hours}
+\text{network egress}
+\text{data services}
+\text{builds/logs/monitoring}
\]

| Scenario | Cost risk |
| --- | --- |
| Keeping high `min_instances` all day | Pays baseline instance hours even with very few users. |
| Picking Standard F4/F4_1G without load data | Higher hourly instance-hour rate than F1. |
| Flexible keeping multiple manual versions | Separate baseline compute per version. |
| Max instances too high under failure or abuse traffic | Massive spike in instance-hours, DB connections, and downstream costs. |
| Max instances too low | Bottlenecks and errors at peak, causing lost revenue/availability. |
| Prolonged canary without cleaning up v1/v2 | Lingering resources, direct version URL requests, and hard-to-track spend. |

In Standard, F/B instance classes convert to **frontend/backend instance-hours** per product billing units. Flexible uses a different pricing structure based on VM resources; check current regional pricing, quotas/free tiers, and supporting services. **A Cloud Billing budget alert is not a hard spending cap.**

## 10. Common troubleshooting

| Symptom | Causes to check | Safe first steps |
| --- | --- | --- |
| Deploy succeeds but users still see old code | New version deployed with `--no-promote` or split still 100% v1 | `gcloud app versions list`, `gcloud app services describe`. |
| “5%” canary receives far more requests | IP splitting with many users behind one corporate proxy/NAT | Switch split method after review; measure across multiple clients. |
| Same user sees two different UIs | Random/IP split, IP changed, or client drops `GOOGAPPUID` | Use cookie splitting if stickiness is needed and verify cookie forwarding. |
| Turning on v2 traffic slows first requests | No warm instances, heavy dependency startup | Inspect cold starts, warmup, `min_instances`, gradual migration. |
| Version serves traffic yet instances do not scale | Hit `max_instances`/quota, CPU signal, pending queue, or dependency | Inspect per-version metrics, quotas, class, and saturation. |
| Flexible does not scale to 0 | Expected behavior of Flexible environment | Budget baseline instances, or evaluate Standard/Cloud Run if scale-to-zero is required. |
| `app.yaml` rejects instance class | F class used with Basic/Manual or B class used with Automatic | Cross-check Standard scaling type and class table. |
| Flexible `min_instances` ignored | Wrongly used Standard key instead of `min_num_instances` | Consult Flexible `app.yaml` reference. |
| Autoscaling causes DB errors | Too many concurrent connections/transactions | Inspect connection pools, DB capacity/quotas, and backpressure. |
| Traffic rolled back yet errors persist | Incompatible data migration, caches, background jobs, or version URLs | Audit schemas, jobs, sessions/caches, and routes; run data recovery runbook. |
| Deleting old version breaks some requests | A client/cron/task hardcoded the version-specific URL | Search references and logs before deleting. |
| Bill still climbs after traffic drops to 0 | Manual/Flexible instances, baseline instances, or active data services | Inspect Versions, Instance Hours, Compute/Network/Billing per service. |

### 10.1. Runbook for 503s during traffic spikes

1. **Identify which service/version receives traffic** and when 503s started.
2. Compare **RPS, CPU, instance count, pending latency, and max instances** per version.
3. Inspect application logs: exceptions, OOMs, database timeouts, config/secret errors.
4. Check dependencies and connection pools—scaling up instances can overload the DB.
5. If errors concentrate in the canary, **reduce its share or roll back** via `set-traffic` after owner confirmation.
6. Verify new requests flow to the stable version and error rates recover; log the incident alongside the traffic change.
7. Fix the root cause before retrying the canary; do not reflexively raise `max_instances` for every failure.

If traffic has returned to v1 yet 503s remain high, check whether **v1 still has enough instances/capacity** or relies on a database degraded by v2. Traffic migration may help instead of an abrupt cutover, guided by metrics and product constraints.

## 11. Scenario exercises

### Scenario A — Variable-load API

A lesson-serving API averages 40 RPS and peaks at **360 RPS**. Average processing time at peak is **150 ms**. Production-like benchmarks show one F2 instance holds SLO up to roughly **12 actual concurrent requests**; beyond that, p99 latency climbs sharply.

**Prompt:** estimate minimum instances from concurrency, explain why extra headroom is required, recommend Automatic vs. Manual, and list metrics to monitor.

**Solution guide:**

\[
360 \times 0.15 = 54\text{ concurrent requests}
\]

Under ideal conditions, `ceil(54/12) = 5` instances. This is only a **lower-bound estimate**, not the final `max_instances` value: p99 spikes, burst traffic, startup times, CPU, dependencies, and quotas may demand more capacity. With fluctuating traffic, **Standard Automatic** fits well, with min/max, class, and concurrency validated via load testing; monitor p99, RPS, instance count, 503s, DB connections, and cost.

### Scenario B — Worker running a few times per day

A reporting service receives requests only a few times a day, with each request taking 30–60 seconds. The team plans to run Standard Manual B8 with two instances 24 hours a day.

**Prompt:** compare against Basic B2, Automatic F2, and a task flow using Cloud Tasks. Identify conditions for choosing each.

**Solution guide:** Basic can cut costs by shutting down idle instances while incurring cold starts; Manual keeps capacity ready at a constant baseline cost; Automatic fits if code/requests meet runtime limits and behavior. For long tasks, evaluate queues, retries/idempotency, and request duration limits rather than choosing B8 just because requests take longer. The choice depends on acceptable latency, job duration, memory, and environment constraints.

### Scenario C — Misconfigured canary skews user experience

A team wants to roll out a new UI to 10% of students. They use `--split-by=ip`, but most requests traverse a corporate reverse proxy and students use mobile networks. Logs show v2 occasionally receiving 35% of traffic, and individual students switching UIs between sessions.

**Prompt:** pick a better splitting method and explain what else must still be controlled.

**Solution guide:** use **cookie splitting** and ensure clients retain `GOOGAPPUID`. Evaluate proxied requests, internal service calls, and cache/`Vary` headers; also verify API/schema/database compatibility between v1 and v2. Cookies provide relative stickiness, not an identity or session security system.

### Scenario D — 5xx surge after canary

App Engine Standard `api` splits 95% to v1 and 5% to v2. After 15 minutes, v2 error rates climb and database connections hit their limit. v2 opens a connection pool of 30 per instance with `max_instances: 20`.

**Prompt:** outline immediate mitigation and long-term fixes.

**Solution guide:** reduce v2 traffic or roll back per runbook, then verify v1 and DB recovery. Next, calculate instance count × pool connections, inspect routing, retry storms, and transaction latency. Fix pooling/concurrency/backpressure and load-test before the next release; never blindly raise `max_instances` or grant privileged DB roles.

## 12. Self-check questions

1. **Is scaling configured per service or per version?** — In `app.yaml` per **version**; a service can hold multiple versions with distinct scaling settings.
2. **Can Standard Automatic use instance class B2?** — No; Automatic uses the **F** series, while Basic/Manual use the **B** series.
3. **Does Flexible have `basic_scaling` or `min_instances: 0` like Standard?** — No; Flexible uses automatic/manual and `min_num_instances`/`max_num_instances`.
4. **Does setting `max_concurrent_requests: 50` guarantee an instance handles 50 requests within SLO?** — No; it is a scheduling threshold—you must benchmark the application.
5. **Does deploying with `--no-promote` switch the service URL to the new release?** — No; a version can be deployed without changing traffic weights.
6. **Is a version with 0% traffic guaranteed unreachable?** — No; its version-specific URL remains reachable unless separately protected.
7. **Why can IP splitting deviate from 10%?** — NAT/proxies aggregate requests, client IPs change, and sample sizes may be small.
8. **Can cookie splitting serve as user authentication?** — No; `GOOGAPPUID` is a traffic-bucketing mechanism, not an authorization identity.
9. **Does warmup eliminate all cold starts?** — No, warmup is best effort.
10. **Does traffic rollback automatically roll back database schemas?** — No; you must design schema compatibility and data runbooks.
11. **Why can even a small canary incur substantial cost?** — v1 and v2 run concurrently and may independently maintain min/manual/Flexible instances.
12. **Is choosing max instances solely by target monthly spend sufficient?** — No; setting it too low can drop requests—balance against peaks/SLOs and load-shedding layers.

## 13. Google Cloud reference documentation

- [App Engine Standard — How instances are managed](https://cloud.google.com/appengine/docs/standard/how-instances-are-managed): three scaling modes, startup, request timeouts, and cold starts.
- [App Engine Standard — Overview and instance classes](https://cloud.google.com/appengine/docs/standard/overview): F/B classes, relative RAM/CPU, and Standard environment.
- [App Engine Standard — app.yaml reference](https://cloud.google.com/appengine/docs/standard/reference/app-yaml): `automatic_scaling`, `basic_scaling`, `manual_scaling`, `instance_class`.
- [App Engine Flexible — app.yaml reference](https://cloud.google.com/appengine/docs/flexible/reference/app-yaml): `resources`, `min_num_instances`, `max_num_instances`, and manual scaling.
- [App Engine Standard — Configuring warmup requests](https://cloud.google.com/appengine/docs/standard/configuring-warmup-requests): best-effort warmup and instance initialization.
- [App Engine Standard — Splitting traffic](https://cloud.google.com/appengine/docs/standard/splitting-traffic): IP/cookie routing, version URLs, and A/B testing.
- [App Engine Standard — Migrating traffic](https://cloud.google.com/appengine/docs/standard/migrating-traffic): shifting 100% traffic and reducing loading latency.
- [gcloud app deploy](https://cloud.google.com/sdk/gcloud/reference/app/deploy): `--version`, `--no-promote`, and deploy options.
- [gcloud app services set-traffic](https://cloud.google.com/sdk/gcloud/reference/app/services/set-traffic): `--splits`, `--split-by`, `--migrate`.
- [gcloud app services delete](https://cloud.google.com/sdk/gcloud/reference/app/services/delete): deleting services/versions in a project.
- [App Engine pricing](https://cloud.google.com/appengine/pricing): Standard, Flexible, instance-hours, and related cost components.
- [App Engine monitoring](https://cloud.google.com/appengine/docs/standard/monitoring): monitoring services, versions, and applications.

**Conclusion:** effective App Engine management means balancing **per-instance capacity**, **how App Engine scales instance counts**, and **how requests reach versions**. Use real load data to pick classes and min/max bounds, deploy new versions without auto-promoting, ramp traffic deliberately, and preserve rollback capability. A configuration is only trustworthy when it satisfies **SLOs, data correctness, access control, and budget** under real measurements.
