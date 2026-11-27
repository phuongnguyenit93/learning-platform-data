# Logs, troubleshooting, and cost control in App Engine

After deploying version `v2` of the Java `orders-api` application to App Engine, the operations team receives two alerts: HTTP 5xx error rates spiked, and end-of-day billing is higher than expected. Looking only at total request volume is insufficient because errors may occur solely in one **version**, while costs can stem from **idle instances, old versions, log ingestion, network egress, or Cloud SQL**.

This lesson establishes an **observe → diagnose → fix → verify → cost-optimize** workflow for both the **App Engine standard environment** and the **flexible environment**. It is part of the **App Engine** chapter in the `CLOUD_PROVIDERS_GCP` module: learners apply knowledge of projects/IAM/VPC, Compute Engine, GKE, Cloud Run, storage, and databases to release applications, protect resources, monitor reliability, and manage budgets.

**Example:** Java 21 application, service `orders-api`, versions `v1` and `v2`, project `PROJECT_ID`. Names and numbers are illustrative; commands changing traffic or deleting versions must only be run with authorization and approval. The content stays concise, self-contained, and suitable as a runbook.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish App Engine request logs, application logs, structured logs, and resource labels.
2. Query logs by service/version using Logs Explorer, `gcloud app logs`, and `gcloud logging read`.
3. Correlate a failing request with Java logs, traces, and Monitoring metrics.
4. Diagnose 5xx spikes, p95/p99 latency, startup failures, overload, and dependency errors.
5. Distinguish **pricing, scaling, and free tiers** between App Engine standard and flexible.
6. Bound costs using sizing, scaling configuration, version management, and log controls.
7. Set up Billing budgets while recognizing that **alert-only budgets do not enforce a hard spending cap**.
8. Design SLO-based alerts, rehearse incident response, and verify post-change outcomes.
9. Complete a read-only hands-on lab and scenario exercises with answers.

## 1. App Engine observability architecture

App Engine structures applications as **application → service → version → instances**. Each version has its own runtime/scaling settings and may receive a traffic share or direct calls via its version URL.

~~~mermaid
flowchart TD
    U["HTTP clients"] --> ROUTE["App Engine routing"]
    ROUTE -->|"90%"| V1["orders-api / v1"]
    ROUTE -->|"10%"| V2["orders-api / v2"]
    V1 --> L["Request + application logs"]
    V2 --> L
    V1 --> M["Metrics: requests, latency, instances"]
    V2 --> M
    L --> LOG["Cloud Logging / Error Reporting"]
    M --> MON["Cloud Monitoring / Trace"]
    V1 --> DB["Cloud SQL, Storage, network"]
    V2 --> DB
    DB --> BILL["Cloud Billing"]
    LOG --> BILL
~~~

When analyzing incidents, always record **project, service, version, time window, and Standard/Flexible environment**. Looking only at project totals allows `v1` traffic to mask errors on `v2`.

| Component | Question to answer |
| --- | --- |
| **App Engine versions** | Which versions receive traffic? Are old versions still active? |
| **Cloud Logging** | Which requests failed and what cause did the app log? |
| **Error Reporting** | Which recurring stack traces/error groups appeared post-deploy? |
| **Cloud Monitoring** | How did 5xx, p95 latency, CPU, memory, and instance count change? |
| **Cloud Trace** | Is latency inside the Java app, networking, or downstream calls? |
| **Cloud Billing** | Which SKU rose: instances, network, Cloud SQL, or Logging? |

## 2. How Standard and Flexible differ in operations and cost

| Criterion | Standard environment | Flexible environment |
| --- | --- | --- |
| Compute capacity | Instance classes `F1/F2/F4...`, supported runtimes | App Engine-managed Compute Engine VMs |
| Scaling model | Automatic, basic, manual | Automatic or manual |
| Scale to 0 on low traffic | **Possible**, typically with automatic scaling and `min_instances: 0` | **No**; automatic scaling enforces `min_num_instances >= 1` |
| Default min instances | Depends on scaling/version configuration | Typically **2** with automatic scaling |
| App Engine free tier | **Yes**, per resource type and daily quota | **No App Engine free tier** |
| Billing | Instance class/hours and resources beyond free tier, network, related services | vCPU, memory, persistent disk/network per resource type and usage duration; subject to minimum billing increments |
| Common request log | `request_log` | `nginx.request` |
| Impact of keeping old versions | May incur instance hours depending on scaling/traffic | May continue keeping VMs and incurring charges even at low traffic |

App Engine Flexible uses VMs billed per second with a **one-minute minimum**, not “only when HTTP requests arrive”. Most Java apps can pick Standard when features/runtimes fit, though decisions must rest on technical limits, workload patterns, and **actual regional pricing**, not free tiers alone.

## 3. Request logs and application logs

Cloud Logging receives two primary groups of entries:

- **Request logs:** automatically generated by App Engine for HTTP requests, typically including timestamp, HTTP method/path/status, latency, and resource metadata.
- **Application logs:** written by Java/frameworks to describe execution, warnings, exceptions, or business events.

Example:

~~~text
Request: GET /api/orders/123 → HTTP 500, latency 1.8s
App:     order_query_failed errorCode=DB_TIMEOUT requestId=req-123
Trace:   request → Java handler → Cloud SQL connection timeout
~~~

Request logs show **symptoms**. Application logs explain **context**. Traces pinpoint the slow step; Monitoring confirms service-wide impact.

### 3.1. Log fields to include

| Field | Purpose |
| --- | --- |
| `timestamp`, `severity` | Classify and query by time |
| `message/event`, `errorCode` | Identify stable error categories |
| `service`, `version` | Tie errors to a specific release |
| `requestId` and Cloud Trace ID | Correlate multiple log lines for one request |
| `latencyMs`, `dependency` | Analyze latency contributors |
| `resource.type=gae_app` | Filter App Engine resources |

Never log **Authorization headers, access tokens, passwords, session cookies, payment data/PII**, or full request bodies just for “quick debugging”.

## 4. Reading logs: CLI and Logs Explorer

### 4.1. Read-only preflight

~~~bash
gcloud auth list
gcloud config get-value project

gcloud app describe --project=PROJECT_ID
gcloud app services list --project=PROJECT_ID
gcloud app versions list \
  --service=orders-api --project=PROJECT_ID
~~~

With appropriate viewer roles, these commands **do not alter production state**. Confirm running versions and traffic allocations before investigating.

### 4.2. Fetching recent logs

~~~bash
# 50 entries from service orders-api:
gcloud app logs read \
  --service=orders-api --limit=50 \
  --project=PROJECT_ID

# View warning severity and above, version v2:
gcloud app logs read \
  --service=orders-api --version=v2 \
  --level=warning --limit=100 \
  --project=PROJECT_ID

# Stream in real time (Ctrl+C to stop):
gcloud app logs tail \
  --service=orders-api --version=v2 \
  --level=error --project=PROJECT_ID
~~~

The `--level` flag accepts `critical/error/warning/info/debug/any`; requires `logging.logEntries.list` or an appropriate IAM role. For specific log streams:

~~~bash
# App Engine Standard request logs:
gcloud app logs read \
  --service=orders-api --logs=request_log \
  --limit=30 --project=PROJECT_ID

# App Engine Flexible request logs:
gcloud app logs read \
  --service=orders-api --logs=nginx.request \
  --limit=30 --project=PROJECT_ID
~~~

### 4.3. Logs Explorer query by version

In the Console, open **Logging → Logs Explorer**, select the right project, and resource **GAE Application**. Start with:

~~~text
resource.type="gae_app"
resource.labels.module_id="orders-api"
resource.labels.version_id="v2"
severity>=ERROR
~~~

The resource label `module_id` holds the **service name** under monitored resource `gae_app`. `version_id` is the version name, not a Git release tag.

To search HTTP errors:

~~~text
resource.type="gae_app"
resource.labels.module_id="orders-api"
resource.labels.version_id="v2"
httpRequest.status>=500
~~~

If no results appear, remove filters one by one (version, severity, status); check the time range, log name/request log, and read permissions. For `textPayload` app logs, fields like `jsonPayload.errorCode` will not exist.

### 4.4. Querying via gcloud logging

~~~bash
gcloud logging read \
  'resource.type="gae_app" AND resource.labels.module_id="orders-api" AND severity>=ERROR' \
  --project=PROJECT_ID --limit=50 \
  --freshness=1h --format=json
~~~

You can add `resource.labels.version_id="v2"` and `httpRequest.status>=500` to narrow results, but **do not assume every application log carries an HTTP status field**.

## 5. Writing clear, structured Java logs

In Spring Boot, use SLF4J/Logback or Java Util Logging. Minimal example:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import java.util.Map;

@RestController
class HealthController {
    private static final Logger LOG =
            LoggerFactory.getLogger(HealthController.class);

    @GetMapping("/healthz")
    ResponseEntity<Map<String, String>> health() {
        LOG.info("event=healthcheck status=ok");
        return ResponseEntity.ok(Map.of("status", "ok"));
    }
}
~~~

Assumes a Spring Boot Web project with standard logging dependencies. This demo endpoint does not check Cloud SQL; **200 on /healthz does not prove the whole system is healthy**.

### 5.1. Structured JSON logs

When querying `jsonPayload.errorCode`, the app can serialize a JSON object **on a single line** to `stdout` or use an appropriate Cloud Logging client:

~~~json
{
  "severity": "ERROR",
  "message": "order_query_failed",
  "event": "dependency_timeout",
  "errorCode": "DB_TIMEOUT",
  "requestId": "req-123",
  "dependency": "cloudsql",
  "latencyMs": 1800,
  "logging.googleapis.com/trace":
    "projects/PROJECT_ID/traces/0123456789abcdef0123456789abcdef"
}
~~~

This is an **illustrative log record**; when writing to stdout, serialize as **one valid JSON line**, not pretty-printed across multiple lines. Cloud Logging recognizes special fields such as `severity` and `logging.googleapis.com/trace` for filtering and correlation. Project ID and trace ID must come from the real runtime/request—never fabricate values in production.

In App Engine, `X-Cloud-Trace-Context` links requests to traces. Extract only the properly formatted trace ID rather than logging raw headers containing unneeded data. Log messages should use **stable error codes and request IDs**, never secrets.

### 5.2. Why do logs sometimes lack severity or correlation?

Plain text from `stdout/stderr` can land in `textPayload` without queryable `errorCode` fields, and severity levels may differ from expectations. Request logs and app logs group together only when **trace metadata correlates properly**; some first-request/startup moments may not correlate completely.

**Limit to remember:** App Engine Cloud Logging docs warn that app log entries exceeding roughly **16 KiB** may not display properly in Logs Explorer. Avoid dumping huge exception payloads or response bodies; log correlation IDs and essential stack traces instead.

## 6. Diagnosing HTTP 5xx spikes after deployment

Follow an ordered runbook:

~~~mermaid
flowchart TD
    A["Alert: 5xx spike"] --> B["Lock project, service, time window"]
    B --> C["Compare versions v1/v2"]
    C --> D["Request logs: path, status, latency"]
    D --> E["App logs: exception/errorCode/trace"]
    E --> F{"App bug or dependency?"}
    F -->|"v2 application"| G["Controlled traffic rollback"]
    F -->|"DB/network/IAM"| H["Investigate Cloud SQL/VPC/quotas/identity"]
    G --> I["Verify 5xx and business metrics"]
    H --> I
~~~

**Step 1 – Isolate:** compare `v1` and `v2` 5xx rates and pick 10–20 representative requests. Note deployment time, traffic split, version-specific URLs, and correlation IDs.

**Step 2 – Identify root cause:** inspect stack traces, `errorCode`, request paths, and latency. Check Cloud SQL connection pools, database locks, Cloud Storage permissions, Secret Manager, and networking. HTTP 500 may stem from application code; 503 may relate to insufficient serving/startup capacity or downstreams.

**Step 3 – Verify:** if errors are isolated to `v2`, shift traffic back to `v1` following change/rollback procedures. If both versions fail, code rollback alone may not help—inspect shared dependencies.

**Step 4 – Post-mitigation:** confirm request count, 5xx, p95 latency, order success rate, and Cloud SQL connections stabilize. Do not draw conclusions from a single minute of data.

### 6.1. Is Error Reporting alone enough?

**Error Reporting** groups exceptions/stack traces cleanly for tracking recurring failures, yet **not every 500 request creates an error group**. If an app returns 500 without logging a recognizable exception format, Error Reporting may miss it. Combine with request logs and Monitoring.

## 7. Analyzing latency: p50, p95, p99, and Cloud Trace

| Metric | Meaning | Alert when |
| --- | --- | --- |
| `p50` | Half of requests are faster than threshold | Many users experience slowness |
| `p95` | 95% of requests are faster than threshold | Significant cohort of slow requests |
| `p99` | 99% of requests are faster than threshold | Tail latency/SLO impacted |
| Instance count | Running instance count | Unusual scale-out or insufficient capacity |
| CPU/memory | Resources pushed near limits? | JVM GC pauses, memory exhaustion, or CPU saturation |
| Downstream duration | Cloud SQL/Storage/external API slow? | Latency rises while app CPU stays normal |

**Analyze per version**, not only service aggregates. If `p50` looks normal while `p99` is very high, a subset of requests may be hitting cold starts, GC pauses, or connection pool waits.

**Cloud Trace** pinpoints request timing and downstream spans **when appropriate instrumentation/sampling is enabled**; do not assume every request automatically emits full Java spans. For Spring Boot, use approved OpenTelemetry/Cloud Trace exporters and ensure no PII is exported in span attributes.

### 7.1. Diagnosing Java cold starts

App Engine Standard automatic scaling can scale to 0, forcing the first request after idle periods to initialize an instance and JVM. Inspect:

- Instance creation and Spring Boot initialization time.
- Class loading, dependency injection, and Cloud SQL connection setup at startup.
- Whether `instance_class` has sufficient memory/CPU; avoid upgrading classes without data.
- `min_instances`/warmup requests if SLAs require steady latency, while accounting for **always-on instance charges**.

App Engine Flexible maintains min instances rather than scaling to 0 like Standard automatic, yet restarts/redeploys/health events still introduce startup latency.

## 8. Logs must not inflate risk or bills

**More logging** does not equal better diagnostics. Logging a line per object/item in a batch can generate millions of records, inflating ingestion costs and burying critical errors.

| Practice | Benefit | Caution |
| --- | --- | --- |
| Prefer structured logs | Filter by `errorCode`, `version`, `requestId` | Avoid high-cardinality fields in log-based metrics |
| Trim repetitive DEBUG/INFO | Cuts volume and noise | Retain enough logs for incident tracing |
| Sample successful request logs | Reduces volume at high traffic | Never sample out critical errors |
| Cloud Logging exclusion filters | Cuts ingestion into selected buckets | Can lose investigative trails or violate retention policies |
| Log sinks to Cloud Storage/BigQuery | Long-term archive or separate analytics | Incurs separate storage/query/egress costs |
| Appropriate retention | Optimizes storage and compliance | Never delete required audit logs |

**Never drop audit/security logs or request errors solely to save money** without Security/SRE review. Keep secrets out of logs at the source; exclusion filters are not a fix for leaked data.

## 9. Cost drivers in App Engine

| Cost source | Standard | Flexible | Notes |
| --- | --- | --- | --- |
| Instances | Instance class/hours, conditional free quotas | VM vCPU/memory/disk resources, no App Engine free tier | Multiple versions can accrue billable load concurrently |
| Network egress | Per network pricing/quotas | Per network pricing | Do not confuse ingress with egress |
| Cloud SQL | Billed separately from App Engine | Billed separately from App Engine | Pools, connections, and DB instance |
| Cloud Storage | Storage/operations/egress | Same | Bucket files used by app are not automatically free |
| Cloud Logging | Ingestion/storage per pricing | Same | Debug spam and sinks can drive charges |
| Trace/Monitoring | Per feature/volume | Per feature/volume | Review observability pricing |
| Extra services/versions | May incur instance costs | May keep minimum VMs alive | 0% traffic version does not mean zero cost |

**Standard has a free tier; Flexible does not.** Quotas/free tiers vary by region, resource, and pricing plan; never use an F1/CPU-hour rate from another region as a guaranteed forecast. Always check [App Engine pricing](https://cloud.google.com/appengine/pricing) and actual Cloud Billing SKUs.

### 9.1. Hypothetical cost estimation

Suppose **a Flexible service** keeps two instances running for 30 days, even with zero requests:

~~~text
Baseline instance-hours = 2 instances × 24 hours × 30 days
                        = 1,440 instance-hours
~~~

In Flexible, the real bill comprises VM **vCPU, memory, disk, and networking**; never multiply 1,440 blindly by a single generic “instance unit price”. Keeping **two independent versions**, each with a minimum of 2 instances, can yield baseline capacity equivalent to **4 instances**, excluding canaries/rollouts and supporting services.

This example illustrates **the impact of min instances**, not a Google Cloud price quote.

## 10. Standard: automatic scaling balanced for cost/SLO

Example `app.yaml` for a Java 21 app on **Standard**:

~~~yaml
runtime: java21
service: orders-api
instance_class: F2

automatic_scaling:
  min_instances: 0
  max_instances: 5
  target_cpu_utilization: 0.65
  max_concurrent_requests: 20
~~~

Explanation:

- `min_instances: 0`: allows dropping baseline instances when idle; **cold starts may increase**.
- `max_instances: 5`: limits scale-out and associated costs, though traffic exceeding capacity raises latency or errors.
- `target_cpu_utilization`: balances CPU load and instance count; not a hard CPU cap.
- `max_concurrent_requests`: maximum requests scheduled per instance in automatic scaling; load-test against Java thread pools and DB connections.
- `F2`: larger resources than `F1`, not automatically cheaper; compare p95/error rates, not just instance counts.

**Common pitfall:** `max_instances: 0` **does not mean running 0 instances**; in current Standard configuration, 0 can disable the configured max limit, while omitting the field uses the default. Since **March 2025**, App Engine applies a default limit of **20 max instances** to **new Standard applications** without automatically changing older apps. **Declare a sensible max explicitly** and check quotas/Direct VPC egress if used.

### 10.1. Min instances carry monetary impact

Raising `min_instances` reduces cold starts but keeps instances running, **potentially incurring charges even with zero requests**. Per Standard documentation, for min instances to work properly with traffic, evaluate enabling **warmup requests**; versions receiving no traffic follow different min_instances rules. Never raise min instances to fix slow requests before verifying whether the cause is cold starts or the database.

## 11. Flexible: watch baseline VMs and min instances

Example **scaling snippet** in Flexible `app.yaml` (not a complete runtime file):

~~~yaml
automatic_scaling:
  min_num_instances: 2
  max_num_instances: 4
  cool_down_period_sec: 180
  cpu_utilization:
    target_utilization: 0.6
~~~

For Flexible:

- `min_num_instances` has a minimum of **1**, commonly defaulting to **2** to reduce latency; this is a baseline cost even at low traffic.
- `max_num_instances` caps scaling, but should not be below SLA needs.
- `cool_down_period_sec` avoids using CPU metrics during instance startup; setting it too high slows autoscaler reactions.
- Size vCPU/memory/disk for JVM performance, Cloud SQL connection pools, and region.

Do not put Standard's `min_instances/max_instances` keys into Flexible; Flexible uses `min_num_instances/max_num_instances`. Deploying Java Flexible also requires compatible **runtime, env: flex, runtime_config/resources** for a supported version. Because this lesson focuses on logs and cost, do not use this fragment as a full deployment manifest.

## 12. Version management: traffic and cost do not always move together

An app has stable `v1` and canary `v2`. If `v2` fails, route traffic back to `v1`:

~~~bash
# LIVE traffic-changing command: run only after change approval.
gcloud app services set-traffic orders-api \
  --splits=v1=1 \
  --project=PROJECT_ID
~~~

This is **App Engine traffic**, distinct from Cloud Run's `gcloud run services update-traffic`. App Engine supports `--split-by=ip|cookie|random` (usually defaulting to `ip`), so split ratios do not guarantee exact per-request or per-user proportions.

**Key cautions:**

- Version-specific URLs can be called directly, bypassing traffic splits; audit actual access and traffic.
- Setting a version to 0% traffic **does not guarantee zero cost**; in Flexible or manual scaling, instances/VMs may keep running.
- Per current CLI reference, `gcloud app versions stop` **works only for versions with manual scaling**; do not teach it as a universal kill switch for all versions.
- Delete unneeded versions only after checking **traffic, dependencies, rollback needs, and related data**. Never delete a serving version or the sole version required by the app.

Inspect before cleanup:

~~~bash
gcloud app versions list \
  --service=orders-api \
  --project=PROJECT_ID

gcloud app versions describe v2 \
  --service=orders-api \
  --project=PROJECT_ID
~~~

If you need to delete an unused **lab version**:

~~~bash
# WARNING: deletes the actual version; no simple undo.
gcloud app versions delete v2 \
  --service=orders-api \
  --project=PROJECT_ID
~~~

**Never delete a production version solely because traffic = 0%**: it may be needed for rollback, direct URLs, background services, or inter-service calls. Check Billing Reports to verify whether charges come from that version or from Cloud SQL/network/logging.

## 13. Billing Reports, budgets, and anomaly alerts

### 13.1. Pinpointing expensive SKUs

In the Console:

1. Open **Billing → Reports**, select the billing account and date range before/after the incident.
2. Filter by **Project**, then group by **Service/SKU** to see whether increases stem from App Engine, Cloud SQL, Network, or Logging.
3. Compare a normal day against the `v2` deploy day; record total cost, trend, and delta.
4. Cross-reference with **instance count, request rate, egress bytes, and log volume** in Cloud Monitoring.

Do not blame the entire bill jump on App Engine if Cloud SQL autoscaled/grew storage or logs multiplied.

### 13.2. Budget alerts are not hard caps

Create a **Cloud Billing alert budget** on the authorized project/services with thresholds such as 50%, 80%, 100%, and forecasted spend. **Alert-only budgets only notify**—they do not stop App Engine from running and incurring charges, and billing data has reporting lag.

At the time of writing, Cloud Billing **spend cap budgets** maintain a specific list of eligible services and **do not list App Engine** among supported services. Never promise learners they have a “hard App Engine cap” simply by creating a budget.

### 13.3. When anomalous costs exceed thresholds

- Alert FinOps and on-call; verify numbers and cost sources.
- Cap `max_instances` or downsize resources **only if load tests/SLOs permit**.
- Fix log spam, retry storms, and request loops.
- Evaluate old versions/baseline VMs while preserving necessary rollback targets.
- **Disabling the App Engine application** is an emergency measure that can cause **all requests to fail**; run only under approved procedures. App Engine data/config may persist, while other Google Cloud products **continue billing**.

Never automatically disable billing/the entire project upon receiving a budget Pub/Sub event without evaluating blast radius and billing reporting lag.

## 14. Safe lab: simulated investigation without touching production

**Hypothetical context:** `orders-api` sends 90% of requests to `v1` and 10% to `v2`; `v2` reports rising HTTP 5xx and a higher bill.

### Step 1 – Confirm versions and logs

~~~bash
gcloud app versions list \
  --service=orders-api --project=PROJECT_ID

gcloud app logs read \
  --service=orders-api --version=v2 \
  --level=error --limit=50 \
  --project=PROJECT_ID
~~~

### Step 2 – Filter failing requests

Paste into Logs Explorer, adjusting version as needed:

~~~text
resource.type="gae_app"
resource.labels.module_id="orders-api"
resource.labels.version_id="v2"
httpRequest.status>=500
~~~

Record **5 request IDs/trace IDs**, status, path, and latency; never copy PII.

### Step 3 – Cross-check metrics

In **Monitoring/App Engine dashboard**, compare p95 latency, HTTP 5xx, request count, and instance counts of **v1/v2** over the same interval. Inspect Cloud SQL connections, CPU, memory, and startup errors if any.

### Step 4 – Inspect Billing

Use Billing Reports filtered by project, service, and SKU to determine whether increases come from **instance hours, networking, Logging, or Cloud SQL**. When documenting costs during an investigation, record **numbers, time windows, and hypotheses** rather than jumping to conclusions from a single chart.

### Step 5 – Write a change proposal

Example:

~~~text
Issue: v2 5xx spike after 09:00 UTC deploy
Evidence: request logs + app errorCode + p95 + Cloud SQL pool
Cost source: Flex instance baseline or log volume increase
Proposed mitigation: reduce v2 traffic / fix connection pool / log sampling
Risk: preserve rollback capability and business continuity
Verify: 5xx, p95, order success, instance count, daily cost trend
Owner: SRE + backend + FinOps
~~~

**By default this lab is read-only.** Do not run `gcloud app deploy`, `set-traffic`, `versions delete`, or edit `app.yaml` on production to complete the exercise. If you have a dedicated lab environment, make changes under supervision using the prepared rollback runbook.

## 15. Common errors and signals table

| Symptom | Likely cause | Inspection path |
| --- | --- | --- |
| 5xx only on `v2` | New code/config, secrets, incompatible schema | Per-version logs, deployment diff, rollback plan |
| 5xx on both `v1` and `v2` | Cloud SQL, network, IAM, shared dependency | Traces, downstream metrics, quotas |
| `429` or timeouts when capping instances | `max_instances` too low, request backlog | Instance count, queue/latency, sizing |
| High p99 with normal p50 | Cold starts, JVM GC, slow tail requests | Traces, JVM metrics, startup logs |
| Logs Explorer shows no requests | Wrong project/time/resource/version/log type | `gae_app`, `request_log` vs. `nginx.request` |
| App logs appear but not grouped under requests | Missing trace correlation | `X-Cloud-Trace-Context`, trace field |
| Cannot find error group | Unrecognized exception log format, HTTP status only | Request logs + Error Reporting + stack traces |
| Cost rises as traffic drops | Min/manual/Flex instances or old versions | Scaling config, version list, SKUs |
| Cloud Logging cost rises | DEBUG logs, retries/loops, stdout spam | Log volume by source, controlled exclusions |
| App Engine Standard starts slowly | Scale-to-zero instances, JVM startup | Startup logs, warmup/min instances, SLOs |
| App Engine Flexible does not scale to 0 | Min instances ≥ 1 | Flex pricing model, `min_num_instances` |
| v2 still gets requests after rollback | Direct version URL, propagation, sessions | Traffic split, URLs, timestamps |

## 16. End-to-end scenario: cutting both errors and costs

The Commerce team deploys Java `orders-api v2` on Flexible. After two days, 5xx rises from **0.2% to 2.1%** and the bill grows. Investigation reveals v2 enlarged its Cloud SQL connection pool, while the rollout kept both v1 and v2 running with **min 2 instances per version**. Logging every database attempt also drove up log ingestion.

**Evidence-based plan:**

1. Read v2 request logs and traces: confirm 5xx concentrates on Cloud SQL connection timeouts.
2. Check instance counts, Cloud SQL connection counts, and log volume over time.
3. Since errors are isolated to v2, shift traffic back to v1 per runbook after checking schema/data compatibility.
4. Fix pool settings, add bounded retries, trim duplicate DEBUG logs, and test in staging.
5. On re-releasing v2, roll out incrementally; track 5xx, p95, business success rate, and pool saturation.
6. After the rollback window, manage old versions so idle baseline VMs are not kept running unnecessarily.
7. Review Billing Reports after updates without expecting instant bill drops due to reporting lag.

**Separate the two goals:** reducing instances/logs must never sacrifice order data integrity or breach SLOs. Cost decisions are valid only when metrics prove the system remains reliable.

## 17. Self-check exercises

**Q1.** Request log returns HTTP 500, app log says `DB_TIMEOUT`. Where should you investigate next?

*Answer:* Traces and Cloud SQL connections/pool/latency; status 500 is only the symptom.

**Q2.** Why filter by `resource.labels.version_id` when v2 is only at a 5% rollout?

*Answer:* Service-wide totals can hide v2 errors because v1 handles most requests.

**Q3.** What is App Engine's `resource.type`, and which label holds the service name?

*Answer:* `gae_app`; the service name is in `resource.labels.module_id`.

**Q4.** Do Standard and Flexible share the same App Engine free tier?

*Answer:* No. Standard has quota-based free tiers; Flexible has no App Engine free tier.

**Q5.** Does `min_instances: 0` in Standard guarantee zero cold starts?

*Answer:* No. Scaling to 0 can require JVM initialization when new requests arrive.

**Q6.** How can raising Flexible `min_num_instances` from 2 to 4 affect baseline cost?

*Answer:* It can roughly double the minimum VM footprint, depending on configuration, resources, and runtime duration.

**Q7.** Why not set `max_instances: 1` on every production app to save money?

*Answer:* Too low a cap can increase latency, drop requests, or violate SLOs.

**Q8.** Does Standard `max_instances: 0` shut down the service?

*Answer:* No; it is not a switch to shut down all instances.

**Q9.** Is a Flexible version receiving 0% traffic guaranteed to be free?

*Answer:* No. Min/manual instances and related resources can still incur charges.

**Q10.** Does creating a 100% Billing budget alert block App Engine from consuming more resources?

*Answer:* No. Alert-only budgets do not automatically cap spending; appropriate operational controls and responses are needed.

**Q11.** Why should you not delete all `request_log` entries to reduce Logging costs?

*Answer:* You lose debugging, SLO, and audit evidence; choose responsible sampling or exclusions instead.

**Q12.** Is `gcloud app versions stop` a universal way to stop every auto-scaling version?

*Answer:* No. CLI stop currently applies to manual scaling; check version type/config and valid alternatives.

**Q13.** What does rising p99 with flat p50 suggest?

*Answer:* A small subset of requests is slow due to cold starts, GC pauses, pool waits, or external dependencies.

**Q14.** After rolling back v2, why must you still monitor Cloud SQL and business errors?

*Answer:* Migrations, data, and external state do not roll back with App Engine traffic; faults may persist in dependencies.

## 18. Production checklist

- [ ] Identify project, App Engine service, version, and Standard/Flexible before debugging.
- [ ] Request logs and app logs include severity, errorCode, and trace/request correlation.
- [ ] Logs exclude PII, tokens, and secrets; logging volume has an owner.
- [ ] Dashboards track 5xx, p95/p99, traffic, instance count, CPU/memory, and dependency metrics.
- [ ] Alerts cover SLOs and canary versions, not only aggregate service totals.
- [ ] Error Reporting/Trace have proper instrumentation and permissions.
- [ ] Standard `instance_class`, `min_instances`, `max_instances`, and concurrency are load-tested.
- [ ] Flexible `min_num_instances` and baseline CPU/memory/VM sizing are explicitly accounted for.
- [ ] Inventory of versions, direct URLs, traffic splits, and rollback plans exists.
- [ ] App Engine charges are separated from Cloud SQL, Storage, Network, and Logging.
- [ ] Billing Reports, alert-only budgets, alert owners, and response workflows are in place.
- [ ] Budgets are not treated as hard App Engine caps, nor `max_instances` edits as risk-free optimizations.
- [ ] Log exclusions/sinks/retention are approved by Security/SRE.
- [ ] All traffic, scaling, app-disabling, or version-deletion changes are approved.
- [ ] 5xx incident drills, rollback verification, and post-change cost checks have been executed.

## 19. Conclusion

**Effective App Engine observability combines request logs, app logs, version labels, metrics, and traces; effective cost control starts by reading Billing SKUs before tweaking scaling.** Standard and Flexible differ in pricing models; 0% traffic does not mean zero cost, and Billing alerts are not automatic emergency brakes. A reliable workflow is **measure – isolate – fix – verify – monitor costs**, rather than deleting logs or cutting instances blindly.

## Official references

- [App Engine overview](https://cloud.google.com/appengine/docs/an-overview-of-app-engine)
- [App Engine Standard: Write and view logs](https://cloud.google.com/appengine/docs/standard/writing-application-logs)
- [App Engine Flexible: Write and view logs](https://cloud.google.com/appengine/docs/flexible/writing-application-logs)
- [Troubleshoot App Engine Standard](https://cloud.google.com/appengine/docs/standard/troubleshooting)
- [App Engine Standard: How instances are managed](https://cloud.google.com/appengine/docs/standard/how-instances-are-managed)
- [App Engine Standard: app.yaml reference](https://cloud.google.com/appengine/docs/standard/reference/app-yaml)
- [App Engine Flexible: app.yaml reference](https://cloud.google.com/appengine/docs/flexible/reference/app-yaml)
- [Manage App Engine costs](https://cloud.google.com/appengine/docs/standard/managing-costs)
- [App Engine pricing](https://cloud.google.com/appengine/pricing)
- [Cloud Logging monitored resource types](https://cloud.google.com/logging/docs/api/v2/resource-list)
- [gcloud app logs read](https://cloud.google.com/sdk/gcloud/reference/app/logs/read)
- [gcloud app logs tail](https://cloud.google.com/sdk/gcloud/reference/app/logs/tail)
- [gcloud app services set-traffic](https://cloud.google.com/sdk/gcloud/reference/app/services/set-traffic)
- [gcloud app versions stop](https://cloud.google.com/sdk/gcloud/reference/app/versions/stop)
- [Cloud Billing budgets and alerts](https://cloud.google.com/billing/docs/how-to/budgets)
- [Cloud Billing spend cap eligible services](https://cloud.google.com/billing/docs/how-to/budgets-spend-caps)

