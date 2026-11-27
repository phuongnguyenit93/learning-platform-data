# Handling Quota Exceeded, Resource Exhausted, and Capacity Shortages

A Java system running on Google Cloud can fail during traffic spikes even when neither its configuration nor source code has changed. Sometimes a VM creation command returns `QUOTA_EXCEEDED`; other times CPU quota is still available, yet Compute Engine reports `ZONE_RESOURCE_POOL_EXHAUSTED`. A GKE Pod stuck in `Pending`, a Cloud Run request returning 429, or a Java application throwing `OutOfMemoryError` might all be lumped together as "out of resources" — yet **their root causes and remedies are completely different**.

This lesson builds a methodology to classify, investigate, and resolve three problem categories: **quota exceeded** (surpassing granted usage limits), **resource exhausted** (resources needed for an operation have run out or cannot be allocated), and **capacity shortage** (insufficient physical hardware or service-layer capacity). The goal is to restore service safely, avoid panicked changes that lose data or undermine reliability, and design monitoring and capacity planning so incidents do not recur.

This lesson belongs to the **Operations and Troubleshooting** chapter of the **CLOUD_PROVIDERS_GCP** module. The module explores Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners know how to select services, protect resources, automate releases, and monitor reliability and costs. In this lesson, we apply that knowledge to real-world SRE operations and incident response.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **rate quota**, **allocation quota**, **concurrent quota**, **system limits**, **physical capacity**, and **application resource exhaustion**.
- Interpret `429`, `403 QUOTA_EXCEEDED`, gRPC `RESOURCE_EXHAUSTED`, `503`, `ZONE_RESOURCE_POOL_EXHAUSTED`, and `OOMKilled` signals without guessing from the error code alone.
- Identify the exact service, project, region/zone, quota metric, limit, usage, and failing request.
- Use Cloud Quotas, Cloud Monitoring, Cloud Logging, `gcloud`, and `kubectl` for read-only diagnostics.
- Handle common scenarios in Compute Engine, GKE, Cloud Run, Cloud SQL, Pub/Sub, BigQuery, and Cloud Storage.
- Design retries with backoff/jitter, flow control, batching, and idempotency for Java/Spring.
- Prepare evidence-backed quota increase requests, and distinguish quota increases from capacity reservations.
- Build alerts, headroom forecasts, and GO/NO-GO runbooks for traffic spikes, deployments, and DR.
- Evaluate cost, security, and resource fairness impacts during incident mitigation.

## 1. Four Concepts That Must Be Kept Separate

### 1.1 Quota: Granted Administrative Limit

**Quotas** define the amount of resources or number of operations a consumer is allowed to use within a defined scope. Google Cloud has several types:

| Quota Type | Example | Characteristics |
|---|---|---|
| **Allocation quota** | Total vCPUs or accelerators allowed in a region | In-use resources occupy quota until released per service rules |
| **Rate quota** | Number of API requests per minute, day, or other window | Usage capacity replenishes over the service's time window |
| **Concurrent quota** | Number of simultaneous operations or requests | Pressure only drops when requests/operations complete |
| **Per-user quota** | Requests per minute for an identified caller/user | One caller can run out even if total project usage is low |
| **System limit** | Fixed limit of a feature or object | Usually cannot be increased like adjustable quotas |

Quotas are tied to a **scope**: project, region, zone, service, machine family, consumer, or identity, depending on the metric. Requesting quota in region A does not increase quota in region B; quota for API X does not transfer to API Y.

**Key point:** higher quota does not guarantee physical hardware availability, nor does it guarantee the application has enough CPU, RAM, or database connections to process work.

### 1.2 Physical Capacity: Actual Allocation Availability

A zone may lack enough CPU, memory, GPUs, or Local SSDs for a VM or accelerator slice at creation time. When that happens, Compute Engine can return errors such as `ZONE_RESOURCE_POOL_EXHAUSTED`, `REGION_RESOURCE_POOL_EXHAUSTED`, or `POOL_CAPACITY_INSUFFICIENT` depending on the request and API.

**Increasing quota will not immediately add physical hardware to a zone.** Options to evaluate include another zone, another region, an equivalent machine type, splitting the workload, or an appropriate reservation/provisioning model.

### 1.3 Resource Exhaustion Inside the Workload

Even when quotas and zone capacity are sufficient, a process can still exhaust:

- Java heap or native memory, causing `OutOfMemoryError` or container `OOMKilled`.
- HTTP/JDBC thread pools or connection pools.
- Full disks, exhausted inodes, or saturated storage throughput/IOPS.
- CPU throttling, full request queues, or blocked event loops.
- Database `max_connections`, lock contention, or storage limits.
- Unschedulable Pods whose requests exceed node `allocatable` capacity.

These are **workload and runtime** capacity issues and cannot be fixed by clicking "Increase quota" in the Cloud Console.

### 1.4 Service Capacity and Self-Imposed Limits

A managed service like Cloud Run can reject requests when no instance is available due to `max instances`, regional CPU/memory quotas, slow startup times, slow service scaling, or overloaded backends. GKE Cluster Autoscaler can be blocked by node pool max size, Pod scheduling constraints, IP exhaustion, or Compute Engine capacity.

Therefore, investigation must answer **"at which layer is the limit?"** before choosing an action.

## 2. Error Identification Matrix

| Signal | Common Context | First Hypothesis | Avoid Jumping to Conclusion |
|---|---|---|---|
| HTTP `429 Too Many Requests` | API rate limiting, quotas, Cloud Run out of instances | Too many requests or insufficient serving capacity | "Definitely need to increase API quota" |
| HTTP `403 QUOTA_EXCEEDED` | Certain Compute Engine APIs | Allocation quota exceeded | "IAM permission denied" |
| HTTP `403 RATE_LIMIT_EXCEEDED` | Compute Engine rate quota | API call rate too high | "Must increase vCPU count" |
| gRPC `RESOURCE_EXHAUSTED` | Google APIs or application gRPC | Quota, flow control, or resource limit | "Zone hardware is definitely exhausted" |
| `ZONE_RESOURCE_POOL_EXHAUSTED` | VM creation/start | Insufficient physical capacity in zone | "Quota is at 100%" |
| `REGION_RESOURCE_POOL_EXHAUSTED` | Compute Engine request in region | Capacity unavailable across evaluated zones | "Missing IAM/role" |
| `IP_SPACE_EXHAUSTED` | GKE/node provisioning | Insufficient IP address range | "CPU quota is low" |
| Pod `Pending` / `FailedScheduling` | GKE | Cannot fit resources or constraints | "Cluster Autoscaler is broken" |
| `OOMKilled`, exit 137 | Container | Exceeded memory limit or OOM | "Regional memory quota exhausted" |
| HTTP `503` | Cloud Run, load balancer, upstream | Unable to serve request or backend error | "Just retry infinitely" |
| Database `too many connections` | Cloud SQL/PostgreSQL/MySQL | DB connections exhausted | "Need to increase SQL instance quota" |
| BigQuery `resourcesExceeded` | Query execution | Memory/shuffle/CPU resource limits | "Need to increase API requests quota" |

**An error code is not a complete diagnosis.** Inspect the error message, service/API method, `reason`, `domain`, `quota_metric`, `quota_limit`, project, location, request ID, and timestamp. Different products expose different detail fields.

### Illustrative Log Example (Not a Standard Response Across All APIs)

~~~json
{
  "severity": "ERROR",
  "service": "orders-worker",
  "operation": "create-compute-instance",
  "project_id": "demo-project",
  "location": "asia-southeast1-b",
  "api_error": "QUOTA_EXCEEDED",
  "resource_type": "compute.googleapis.com",
  "request_id": "example-request-id",
  "retryable": false,
  "message": "Requested operation exceeds a quota in the specified scope"
}
~~~

Preserve the original error code from the provider. Fields such as `service`, `operation`, and `retryable` in this example are a **custom application log schema**, not guaranteed to be returned by every Google API.

## 3. First 10 Minutes of an Incident: Mitigate Impact Before Requesting Quota

A capacity incident can escalate rapidly when clients retry simultaneously. The first goal is **containing impact**, not immediately filing a quota increase.

### Handling Flow

~~~mermaid
flowchart TD
  A[Alert / error / Pod Pending] --> B[Classify customer impact and scope]
  B --> C{Which layer is failing?}
  C -->|Rate or concurrent quota| D[Rate limit, backoff, queue, reduce fan-out]
  C -->|Allocation quota| E[Check usage, safely release unused resources]
  C -->|Zone capacity| F[Change zone/machine type or use reservation]
  C -->|Workload exhausted| G[Tune memory/pool/requests, shed traffic]
  C -->|Unclear| H[Hold changes, gather logs/metrics]
  D --> I[Verify SLOs and backlog]
  E --> I
  F --> I
  G --> I
  H --> I
  I --> J{Stabilized?}
  J -->|No| K[Escalate to support / incident commander]
  J -->|Yes| L[RCA, quota/capacity plan, alerts]
~~~

### Initial Triage Checklist

1. **Assess impact:** are requests failing, transactions aborting, queues backing up, deployments blocked, or is only a test job failing?
2. **Determine scope:** project, billing account, service, region/zone, tenant/user, resource, API method.
3. **Record timestamps and traces:** log entries, request ID, operation ID, error details, and recent deployments/changes.
4. **Measure usage/limit:** check the exact quota metric and limit for the right dimension, not just a project-wide aggregate.
5. **Inspect health:** CPU/memory, latency, queue age, DB connections, GKE events, node capacity.
6. **Apply safe mitigations:** reduce batch concurrency, pause non-critical jobs, enable backpressure, or shift routing via approved procedures.
7. **Escalate to the right team:** Platform/Quota owner for quotas; SRE/Network for capacity; DBA for database; app team for Java memory.
8. **Only raise quotas or alter architecture** after confirming the bottleneck and evaluating FinOps/security impacts.

**Never stop/delete a running production VM to "free a slot" when a zone has a capacity shortage**: Compute Engine may be unable to recreate or restart the instance without a matching reservation.

## 4. Inspecting Quotas in the Right Place and Dimension

In the Google Cloud Console:

1. Select the exact project/folder/organization.
2. Open **IAM & Admin > Quotas & System Limits**.
3. Filter by Service, quota metric, location, and limit name.
4. Inspect Value, Current usage, Current usage percentage, Unit, and Scope.
5. Open the **usage chart** and correlate it with the error timestamps.
6. Check for pending quota adjustments or overrides lower than the default.
7. Check service documentation to see whether it is adjustable or a fixed system limit.

**Caution:** for per-minute rate quotas, the Current usage column may reflect an average over an observation window; brief spikes can trigger 429s even if the displayed number is below 100%. For per-day quotas, daily resets may follow Pacific Time. Always read the metric and period definitions.

### Investigation Table to Complete

| Field | Example | Why Needed |
|---|---|---|
| Incident ID | INC-2026-XX | Tracking |
| Product/API | Compute Engine API | Locate the right quota table |
| Project | `project-prod` | Quota consumer |
| Location | `asia-southeast1` / zone | Allocation scope |
| Quota metric | CPU family or API request rate | Suspected limit |
| Limit | Value read from Console | Avoid guessing defaults |
| Usage | Value for same scope/time window | Calculate headroom |
| Error reason | `QUOTA_EXCEEDED` | Classification |
| Business impact | 20% of deployments failing | Severity assessment |
| Owner | `platform-oncall` | Action owner |
| Evidence | Console chart, logs, request ID | Audit/RCA |

### Distinguishing "Remaining Quota" from "Allocatable Capacity"

Suppose a region's machine-family quota has 40 vCPUs remaining, yet a 32-vCPU request fails because the zone lacks enough matching hardware at that moment. That is a **capacity shortage**, not a reason to automatically request a quota bump from 40 to 80 vCPUs.

Conversely, when a zone has hardware capacity but the project has exhausted its 40-vCPU quota, switching to another zone **in the same region** will still hit the same regional quota. Always check the scope.

## 5. Initial Read-Only Inspection Commands

The following examples are **read-only**. Replace `PROJECT_ID`, `REGION`, `ZONE`, `CLUSTER`, and resource names before running. Always confirm your active project/context to avoid inspecting the wrong environment.

### Project and Compute Engine Quotas

~~~bash
gcloud config get-value project
gcloud projects describe PROJECT_ID

gcloud compute regions describe REGION \
  --project=PROJECT_ID \
  --format="yaml(quotas)"

gcloud compute project-info describe \
  --project=PROJECT_ID \
  --format="yaml(quotas)"
~~~

This inspects **Compute Engine quotas exposed on those resources**, not the quota table for every Google Cloud product. For other quotas, use the Cloud Quotas Console/API and service-specific documentation.

### VMs, Reservations, and Zones

~~~bash
gcloud compute instances list --project=PROJECT_ID

gcloud compute reservations list --project=PROJECT_ID

gcloud compute zones describe ZONE --project=PROJECT_ID
~~~

`zones describe` does not promise to report real-time physical hardware availability. If the API reports resource exhaustion, use the reason details and capacity error guidance to select an alternative.

### Sample Logs Explorer Query

~~~text
severity>=ERROR
(
  "QUOTA_EXCEEDED" OR
  "RATE_LIMIT_EXCEEDED" OR
  "RESOURCE_EXHAUSTED" OR
  "ZONE_RESOURCE_POOL_EXHAUSTED"
)
~~~

This is a string-search screening query. In real logs, filter by resource labels, project, time range, and service-specific structured fields so you do not miss errors with different messages.

### Evidence Discipline

A quota screenshot taken at 14:00 does not prove quota was not hit at 13:15. Every observation must record timestamp, scope, log timestamp, and the failing request.

## 6. Monitoring Quotas with Cloud Monitoring

Cloud Monitoring supports multiple quota metrics across two main families:

- **Consumer quotas:** metrics under the `consumer_quota` monitored resource, such as `serviceruntime.googleapis.com/quota/exceeded`; use the `quota_metric` label to distinguish limits.
- **Resource-specific quotas:** certain services emit `usage`, `limit`, and `exceeded` metrics directly on their own monitored resources.

Example filter in Metrics Explorer or equivalent Monitoring Query Language:

~~~text
metric.type="serviceruntime.googleapis.com/quota/exceeded"
resource.type="consumer_quota"
~~~

Only deploy alerts after confirming the service actually emits the corresponding metric. Quota metrics are not emitted with the same schema, latency, or dimensions across all products.

### Minimum Quota Dashboard

| Widget | Purpose |
|---|---|
| Usage / limit (%) by quota and region | Headroom |
| Quota exceeded events | Detect limit hits |
| Request rate, p95/p99 latency | User impact |
| Retry rate / 429 / 503 | Detect retry storms |
| Queue age and backlog | Measure accumulating pressure |
| CPU, memory, disk, connections | Separate quota from workload saturation |
| GKE Pending Pods / scale-up errors | Scheduler/autoscaler bottlenecks |
| Deploy/traffic change markers | Correlate error spikes with changes |

### Alerting Thresholds

A 70–80% headroom usage threshold or a multi-day exhaustion forecast can serve as an **initial internal threshold**, not a Google Cloud guarantee. Services with sub-second bursts need burn-rate/short-window alerts; slow-moving allocation quotas can use longer windows.

Avoid paging on-call for a "90% quota" that poses no service risk. Separate **planning alerts** from **incident alerts**.

## 7. Compute Engine: Distinguishing Quotas from Zone Capacity Exhaustion

### Case A: `QUOTA_EXCEEDED`

Symptoms: creating a VM or scaling a Managed Instance Group (MIG) fails; error specifies the quota metric.

Investigation:

1. Identify the machine family, region/zone, vCPU/GPU/Local SSD/external IP, or resource limit involved.
2. Check usage/limit in Cloud Quotas and Compute Engine.
3. Cross-check existing VMs/MIGs, reservations, and recently created instances.
4. Check for unused resources still consuming quota.
5. Decide whether to reduce demand, safely release unused resources, or request a quota adjustment.

Never delete disks, snapshots, or other VMs to "free quota" without knowing which quota was hit and what depends on those resources.

### Case B: `ZONE_RESOURCE_POOL_EXHAUSTED`

Symptoms: quota remains available, but the zone lacks sufficient hardware for the requested configuration.

Options:

- Switch to an alternative machine type that meets workload needs.
- Select another zone in the region, if permitted by data residency and HA design.
- Try another region within data policy constraints.
- Split the workload across smaller instances if the architecture supports it.
- Use compatible provisioning models like Spot/flex-start for interruptible jobs.
- Set up **reservations** for critical resources where possible.

**Do not stop/start a running production VM just to test**; once stopped, its hardware capacity is no longer guaranteed on restart without an appropriate reservation.

### General Capacity Does Not Mean Every VM Type Is Available

A zone may have plenty of E2 capacity yet lack A-series GPUs, or have vCPUs available yet lack a specific memory/local SSD configuration. Check machine type, accelerator, disk interface, topology, and placement constraints altogether.

## 8. Reservations, Spot, and Capacity Planning

**Reservations** in Compute Engine help assure capacity for matching resources when required conditions are satisfied. They do not bypass quotas, region/zone rules, billing, or IAM. Reservation configuration must match all required VM attributes.

| Option | When to Use | Risks / Trade-offs |
|---|---|---|
| On-demand | Standard workloads | Susceptible to capacity shortages |
| Matching reservation | Workloads that must create/start on schedule | Incurs cost/commitments depending on type |
| Spot | Interruptible batch/checkpointable, test, stateless jobs | Can be preempted |
| Flex-start (where supported) | Workloads that can wait for allocation | No fixed start time like reservations |
| Change machine type/zone | Equivalent options exist | Must validate memory, CPU arch, latency, compliance |
| Pre-provisioning/warm pool | Critical traffic and deployments | Idle resource cost |

### GPU/TPU

GPUs/TPUs can have **dedicated quotas per accelerator family and location**, alongside physical capacity and topology requirements. Multi-host TPU slices can fail even when total chip quota suffices due to interconnect topology or capacity mismatches.

Never attempt to fix GPU/TPU capacity shortages by raising a generic CPU quota. Review accelerator-specific quotas, capacity, reservations, and provisioning guides.

## 9. GKE: At Least Five Different Causes for a Pending Pod

A `Pending` Pod does not automatically mean missing vCPU quota.

| Symptom / Event | Blocked Layer | Appropriate Remedy |
|---|---|---|
| `Insufficient cpu` / `Insufficient memory` | Scheduler cannot find matching allocatable resources | Adjust requests/limits, node size, autoscaling |
| `scale.up.error.quota.exceeded` | Compute Engine quota during node creation | Check corresponding quota |
| `scale.up.error.out.of.resources` | Insufficient physical capacity in zone | Choose another zone/machine type |
| `scale.up.error.ip.space.exhausted` | Insufficient subnet/Pod IPs | Expand IP range per GKE procedures |
| `no.scale.up.mig.failing.predicate` | Node selectors/affinity/taints/tolerations | Align scheduling constraints with requirements |
| Node pool reached max size | Autoscaler cannot add more nodes | Review autoscaling limits and quotas |
| Unbound PVC | Storage/PV binding | Check CSI, storage class, zone/volume |
| Pod requests exceed a single node's capacity | No node can fit even when scaling out | Split workload or choose larger nodes |

### Read-Only Triage on GKE

~~~bash
kubectl config current-context
kubectl get pods -A --field-selector=status.phase=Pending
kubectl describe pod POD_NAME -n NAMESPACE
kubectl get events -A --sort-by=.metadata.creationTimestamp
kubectl get nodes -o wide
kubectl describe nodes
kubectl get hpa -A
~~~

When Cluster Autoscaler does not add nodes:

- Check errors in GKE Console > Workloads / Notifications.
- Inspect `scaleUp` and `noScaleUp` events in Cloud Logging.
- Check node pool min/max, Compute Engine quotas, and machine type.
- Check GKE IP space and free addresses for nodes/Pods.
- Check node affinity, taints/tolerations, resource requests, and PVC topology.

### Example Pod Capacity Calculation

An 8-vCPU node **does not necessarily offer 8 allocatable vCPUs** for Pods because of kubelet, system components, and node reservations. If a Pod requests 8 CPUs on an 8-vCPU node, it may never schedule. Rely on `kubectl describe node` (Capacity, Allocatable, Allocated resources), not just the machine type name.

### Backoff After Quota Errors

GKE Cluster Autoscaler can enter **backoff** after repeated scale-up errors like quota exhaustion. After increasing quota, Pods may not immediately transition to Running; inspect events/backoff, scheduling, and whether the quota update has taken effect.

**Never arbitrarily lower `requests`** to force a Pod onto a node if the workload truly needs that memory; lowering `requests` does not reduce actual RAM usage and can cause OOMs or noisy-neighbor issues.

## 10. Cloud Run: 429 Is Not Always an API Quota

Cloud Run can return:

- **429 "no available instance"** when requests arrive with no instance ready to handle them, due to hitting max instances, slow startup, or rapid traffic spikes.
- **503** during scaling events, backend/container crashes, or exhausted serving capacity.
- Application-level 429s returned by the Java service itself or an API gateway rate limiter.
- Errors from downstream Google APIs even while the Cloud Run request still has compute resources.

### Limits to Distinguish

1. **Service-level max instances**: caps total serving capacity per configuration.
2. **Revision-level max instances**: per-revision cap under revision configuration.
3. **Regional CPU/memory/GPU quotas**: resources allocated to Cloud Run workloads in the region.
4. **Concurrency per instance**: requests handled simultaneously by a single instance.
5. **Request timeout and startup time**: how long instances/threads remain occupied.
6. **Downstream capacity**: Cloud SQL connections, Pub/Sub throughput, external APIs.

In Cloud Run, max instances can be temporarily exceeded under certain scaling or rollout conditions. Therefore, DB connection calculations need a **safety margin**—never treat `max instances × pool size` as an absolute hard cap.

### Inspecting Configuration and Logs

~~~bash
gcloud run services describe SERVICE \
  --region=REGION \
  --project=PROJECT_ID \
  --format=yaml

gcloud run revisions list \
  --service=SERVICE \
  --region=REGION \
  --project=PROJECT_ID
~~~

In Console/Monitoring, check instance count, request concurrency, request latency, startup latency, CPU, memory, and 429/503 counts by revision. Read **request log messages** to separate platform "no available instance" errors from application-generated 429s.

### Mitigations

| Issue | Remediation |
|---|---|
| Max instances too low for peak | Review raising service-level max, quotas, and cost |
| Slow startup | Reduce startup work, image size, init I/O; use min instances if SLO requires |
| Poorly tuned concurrency | Benchmark and tune request concurrency, CPU, and DB pool |
| Application out of memory | Profile heap/native memory, tune memory limits and code |
| DB overloaded during scale-out | Bound connection pooling, queuing, and concurrency before scaling |
| Insufficient regional quota | Request quota adjustment for the exact metric and region |
| Large traffic bursts | Rate-limit upstream, queue work, and fail gracefully |

Never assume raising max instances is always better: if each instance opens 20 DB connections, scaling instances can turn a Cloud Run bottleneck into a database outage.

## 11. Cloud SQL: Connection Exhaustion, Storage, and Performance

At the database layer, "resource exhausted" errors are rarely administrative Cloud SQL API quotas.

### `too many connections`

Possible causes:

- Too many Cloud Run/GKE replicas simultaneously opening JDBC pools.
- Connection leaks or unclosed connections.
- Slow queries holding connections open too long.
- Batch or admin clients opening continuous connections.
- Database `max_connections` and memory undersized for the workload.

Connection budget formula:

~~~text
Estimated DB connections
  ≈ number_of_active_app_instances × max_pool_size_per_instance
    + workers + admin + background connections
~~~

For example, 120 instances × 15 connections = 1,800 connections, **excluding** workers and admin sessions. This is an illustrative calculation; actual counts must be measured, and Cloud Run can temporarily exceed max instances under some conditions.

### Read-Only PostgreSQL Checks

~~~sql
SHOW max_connections;

SELECT count(*) AS total_connections
FROM pg_stat_activity;

SELECT state, count(*) AS connections
FROM pg_stat_activity
GROUP BY state
ORDER BY connections DESC;
~~~

Do not indiscriminately run `pg_terminate_backend` to "free slots." Doing so can abort active transactions, trigger retry storms, or lose job progress.

### Storage/IOPS Saturation

When a database approaches storage limits or high I/O:

- Check disk usage, growth rate, automatic storage increases, and instance limits.
- Inspect slow queries, locks, replication lag, and transaction logs.
- Review backup/PITR/HA behavior for your engine and edition.
- Evaluate scaling instance size/IOPS/connection caps per DBA runbooks.
- Review indexes, vacuum/maintenance, or workload batching to reduce pressure.

**Increasing Cloud SQL instance-count quota will not fix a single instance running out of connections.** Target the right limit layer.

## 12. Pub/Sub, BigQuery, Cloud Storage, and API Rate Quotas

### Pub/Sub

Pub/Sub can return `RESOURCE_EXHAUSTED` when exceeding throughput, request rate, or other quotas depending on method and region.

Remediation steps:

- Check publish/subscribe throughput and quotas in the exact region.
- Reduce producer concurrency with flow control.
- Optimize batching and message sizes.
- Design appropriate subscriber parallelism.
- Monitor oldest unacked message age, retry/dead-letter policies, and backpressure.
- Do not add more publishers if throughput quota is already saturated.

Message processing can back up; evaluate business RPO and backlog drain time before requesting quota increases.

### BigQuery

Distinguish between:

- API jobs/query request quotas.
- Concurrent job limits per project/location.
- Query `resourcesExceeded` due to memory, shuffle, or execution engine limits.
- Slot capacity/reservations allocated for query compute.
- Storage quotas and streaming ingestion limits.

For queries hitting memory/shuffle limits:

1. Inspect query job execution details and execution plan.
2. Check large joins, `ORDER BY`, aggregations, and data skew.
3. Apply partitioning/pruning, predicate pushdown, and proper schema design.
4. Check slots/concurrency and reservation capacity.
5. Split queries into stages or batches where appropriate.

Do not assume every `resourcesExceeded` error requires increasing BigQuery API quota.

### Cloud Storage

HTTP `429` or `503` during bursts or operation contention may require:

- Retries with exponential backoff and jitter.
- Gradual traffic ramp-up under very high request rates.
- Avoiding multiple workers hammering the same object for writes or metadata updates.
- Batching or adjusting object naming/layout where appropriate.
- Checking bucket location, API method, operation costs, and service limits.

Object operations must support **idempotency/preconditions** when retried; never blindly overwrite production data.

### Other APIs

Secret Manager, Cloud Logging, Cloud Monitoring, and IAM APIs also enforce rate/usage quotas. A tight polling loop or misbehaving autoscaler can multiply requests dramatically, so measure **actual API calls per business transaction**, not just frontend RPS.

## 13. Java Runtime: Heap Exhaustion and Thread/Connection Pools

When a Java application fails in a container, inspect the JVM and container before looking at Google Cloud quotas.

### Java Memory Is More Than Just Heap

~~~text
Container memory
  = Java heap
    + metaspace + code cache
    + thread stacks + direct/off-heap buffers
    + native libraries + JVM overhead
    + sidecar or other processes in the container
~~~

If a container has a 1 GiB limit, setting `-Xmx1024m` leaves no headroom for native memory, causing an `OOMKill` even before the Java heap throws `OutOfMemoryError`.

### Signals to Watch

| Signal | Possible Explanation | What to Check |
|---|---|---|
| `java.lang.OutOfMemoryError: Java heap space` | Heap cannot accommodate allocations | Heap usage, GC behavior, policy-compliant heap dumps |
| `OOMKilled` / exit 137 | Cgroup/container memory exceeded | GKE Pod events, Cloud Run logs, memory metrics |
| `GC overhead limit exceeded` | JVM spends most of its time in GC freeing very little | GC logs, allocation profile |
| Continuously rising thread count | Thread leak or blocking calls | Thread dumps, executor metrics |
| HikariCP connection timeout | Undersized pool, slow DB, or connection leak | Active/idle/pending counts, DB sessions |
| HTTP 429 from downstream | Quota/rate limiting or backend capacity | HTTP headers, request IDs, `Retry-After` |
| `RESOURCE_EXHAUSTED` from gRPC | Possible quota or flow control | gRPC status details, service metrics |

### Java Mitigations

- Profile allocations and live heap set before simply increasing memory.
- Tune `-XX:MaxRAMPercentage` or `-Xmx` against the container memory budget.
- Bound worker threads, queue lengths, and concurrent blocking calls.
- Set HTTP/JDBC/gRPC timeouts; never let requests hold resources indefinitely.
- Ensure connections close via `try-with-resources` or framework lifecycle hooks.
- Use pagination/streaming for large datasets.
- Add circuit breakers, bulkheads, and backpressure.
- Run peak/burst load tests and fault injection before scaling replicas.

## 14. Proper Retries: Difference Between Transient Errors and Hard Limits

**Retries do not create extra quota or capacity.** They only help when failures are transient and waiting gives a chance of success.

| Error | Retry? | Conditions |
|---|---|---|
| API 429 rate limit | Usually yes | Honor `Retry-After`, exponential backoff + jitter |
| gRPC `RESOURCE_EXHAUSTED` | Service-dependent | Check semantics and quota details |
| Transient 503 | Possible | Timeouts, retry budget, idempotency |
| Allocation quota exhausted | Avoid tight retries | Quota must be freed or adjusted |
| Zone capacity shortage | Bounded retry only; usually needs another option | Switch zone/machine/reservation |
| IAM 403 permission denied | No | Fix identity/permissions |
| Validation 400 | No | Fix request payload |
| DB max connections | Limited | Apply backpressure; recover pool/DB first |

### Exponential Backoff with Full Jitter

Illustrative formula:

~~~text
baseDelay = 200 milliseconds
maxDelay  = 10 seconds
attempt   = 0, 1, 2, ...
ceiling   = min(maxDelay, baseDelay × 2^attempt)
sleep     = random_uniform(0, ceiling)
~~~

Beyond capping attempt counts, enforce an **overall deadline** so user threads are not held indefinitely. If the provider returns `Retry-After`, prioritize honoring that guidance.

### Java 17 Example with Idempotent HTTP GET

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public class BoundedRetryExample {
    private static final int MAX_ATTEMPTS = 4;

    public static String getWithRetry(String endpoint)
            throws Exception {
        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

        HttpRequest request = HttpRequest.newBuilder(URI.create(endpoint))
            .timeout(Duration.ofSeconds(5))
            .GET()
            .build();

        for (int attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
            HttpResponse<String> response =
                client.send(request, HttpResponse.BodyHandlers.ofString());

            int status = response.statusCode();

            if (status >= 200 && status < 300) {
                return response.body();
            }

            if (status != 429 && status != 503) {
                throw new IllegalStateException(
                    "Non-retryable HTTP status " + status);
            }

            if (attempt == MAX_ATTEMPTS - 1) {
                throw new IllegalStateException(
                    "Retry budget exhausted, status " + status);
            }

            long maxBackoffMs = Math.min(10000L, 200L << attempt);
            long jitterMs = ThreadLocalRandom.current()
                .nextLong(maxBackoffMs + 1);

            // Demo: read and honor Retry-After, along with overall deadline,
            // before using in production.
            Thread.sleep(jitterMs);
        }

        throw new IllegalStateException("Unreachable");
    }
}
~~~

This snippet is an **educational sample for GET** and does not handle `Retry-After`, I/O exceptions, circuit breakers, cancellation, or an overall request deadline. In production, prefer documented bounded retry configurations from Google Cloud client libraries or frameworks. Never copy this verbatim for POST requests with side effects without an idempotency key or duplicate-write protection.

### Retry Storms and Amplification

If one API request calls three dependencies and each retries three times, downstream traffic can multiply dramatically while the system is already stressed. Enforce a retry budget at **one primary layer**, configure timeouts and bulkheads, and avoid stacking uncoordinated nested retry policies.

## 15. Flow Control, Queuing, and Graceful Degradation

When quotas or rate limits trigger, throttling demand often restores stability faster than requesting a quota increase.

### Pressure-Relief Mechanisms

- **Client-side rate limiter:** caps calls/second and concurrency.
- **Token bucket:** permits controlled bursts while maintaining an average rate.
- **Semaphore/bulkhead:** caps concurrent calls to a dependency.
- **Bounded queue:** finite capacity prevents OOM and makes overload explicit.
- **Circuit breaker:** temporarily blocks calls to a persistently failing dependency.
- **Batching:** reduces per-request overhead where supported by the API.
- **Caching:** avoids repeatedly fetching unchanging data.
- **Async processing:** offloads non-realtime work to Pub/Sub/Cloud Tasks.
- **Priority shedding:** preserves critical transactions while deferring auxiliary jobs.

### What to Avoid

- Unbounded queues that grow memory usage and latency endlessly.
- Retries without jitter causing synchronized client stampedes.
- Disabling all rate limits and collapsing downstream services.
- Scaling replicas endlessly when the database or API quota is the bottleneck.
- Marking work successful upon enqueue when business rules require eventual completion guarantees.

If shedding load by dropping requests, return clear error responses, emit telemetry, and notify callers. For financial or state-mutating transactions, enforce idempotency, deduplication, and reconciliation.

## 16. Evidence-Based Quota Increase Process

Once you prove an **adjustable quota** has been reached, follow this process:

1. Confirm the exact quota metric, project, region/zone, and unit.
2. Measure current usage, peak usage, growth, retry amplification, and required headroom.
3. Propose a justified value and document the business impact.
4. Confirm it is not a system limit or physical capacity shortage.
5. Evaluate the cost impact when higher quota allows compute/service expansion.
6. Submit a quota adjustment request in **IAM & Admin > Quotas & System Limits**.
7. Track request status; if manual review is needed, engage Google Cloud support/account team.
8. Update runbooks/rollout plans only after the quota is **approved and active**.
9. Re-test against real demand; never treat an approval email alone as full verification.

### IAM for Quotas

Per Cloud Quotas documentation, `roles/servicemanagement.quotaViewer` supports viewing quotas and `roles/servicemanagement.quotaAdmin` supports requesting adjustments. Exact permissions depend on project/folder/organization scope and API.

### Information to Include in the Request

~~~yaml
request_type: quota_adjustment
project_id: "PROJECT_ID"
product: "Compute Engine"
quota_metric: "EXACT_METRIC_FROM_CONSOLE"
location: "REGION"
current_limit: "READ_FROM_CONSOLE"
peak_usage: "READ_FROM_MONITORING"
requested_limit: "CALCULATED_AND_APPROVED_VALUE"
business_reason: "Planned production launch and tested peak load"
expected_start: "YYYY-MM-DD"
alternatives_considered:
  - "Tune requests and autoscaling"
  - "Other zone/machine family"
risk_owner: "platform-team"
cost_approval: "finops-owner"
status: "proposed"
~~~

This is a ticket tracking template, **not a standard Cloud Quotas API request body**. Never attach screenshots or tickets containing secrets or personal data.

### Requesting Quota Does Not Guarantee Instant Change

Requests may be approved immediately, require review, or be denied. Some system limits cannot be raised. Avoid scheduling a go-live on an unconfirmed promise that quota will be granted by a specific deadline.

## 17. Demand-Based Capacity Planning and Failure Scenarios

### API Quota Example

Assume a workload has:

- Peak 250 frontend requests/second.
- Average of 4 Google API calls per request.
- Approved burst/maintenance/retry multiplier of 1.2.

Projected call rate:

~~~text
250 requests/second × 4 calls/request = 1,000 calls/second
1,000 × 60 = 60,000 calls/minute
60,000 × 1.2 = 72,000 calls/minute
~~~

The 72,000/min figure is a **workload estimate**, not available quota. Check service, project, per-user, and regional quotas, and measure sub-minute bursts if the product enforces shorter rate windows. If batch jobs or other workers share the API, sum all consumers within the same scope.

### CPU Quota and Zone Reserve Example

Suppose a GKE node pool needs 12 nodes at 8 vCPUs each, plus 4 nodes of headroom:

~~~text
Planned nodes      = 12 + 4 = 16 nodes
Regional vCPUs     = 16 × 8 = 128 vCPUs
Additional overhead = other VM/MIG/node pools and reservations
~~~

128 vCPUs does not account for other quotas or guarantee VM allocation in a given zone. To survive a zone failure, verify whether **the remaining zones** have sufficient capacity and regional quota for failover—not just steady-state totals.

### Multiple Dimensions Simultaneously

In practice, a workload is constrained by its **smallest dimension**:

~~~text
Effective capacity = min(
  compute allocation quota,
  physical available capacity,
  configured autoscaling ceiling,
  available Pod IPs,
  per-instance CPU/RAM capacity,
  downstream connection/API throughput
)
~~~

This is a conceptual model: each term uses different units, so you cannot apply `min` directly to raw numbers. Convert each dimension into **requests/second or effective throughput** before comparing.

### Avoiding Aimless Overprovisioning

Headroom for HA/DR is necessary, but excessively high quotas can allow autoscaling to overshoot expectations and drive up costs. Combine:

- SLOs/error budgets.
- Load tests and peak forecasts.
- Justified quota requests.
- Balanced rate limits and max instances.
- Budget alerts and billing anomaly detection.
- Reservations for critical capacity.
- Clear ownership and periodic reviews.

## 18. Symptom-Based Playbooks

### Playbook A: Google API Returns 429

1. Identify the API/method, caller, and quota scope.
2. Read `Retry-After`, error details, and `quota/exceeded` metrics.
3. Compare request rate spikes against quota and downstream health.
4. Temporarily reduce non-critical fan-out/batch jobs.
5. Enable backoff + jitter, cap concurrency, and enforce retry budgets.
6. If long-term capacity is needed, request the exact quota increase.
7. Monitor 429 rate, backlog, p95 latency, and business success.

### Playbook B: Compute Engine Cannot Create a VM

1. Read the exact reason: `QUOTA_EXCEEDED` or `ZONE_RESOURCE_POOL_EXHAUSTED`.
2. For quota, check project/region/family and usage/limit.
3. For capacity, evaluate an alternative zone or machine type.
4. Do not stop running VMs to test availability.
5. Evaluate reservations and provisioning models for critical workloads.
6. Re-run once under an approved change and record the result.

### Playbook C: GKE Pods Pending During Traffic Spikes

1. Inspect `kubectl describe pod`, Events, and resource requests.
2. Inspect node allocatable resources, affinity/taints, and PVCs.
3. Inspect Cluster Autoscaler `scaleUp`/`noScaleUp` events.
4. Classify as quota, zone capacity, IP exhaustion, node pool max, or scheduling constraint.
5. Adjust the right layer; avoid lowering memory requests below actual workload needs.
6. Monitor Pod Ready status, p95, CPU/memory, node health, cost, and scale-down.

### Playbook D: Cloud Run 429/503 During Bursts

1. Determine whether errors originate from the Cloud Run platform or the app/downstream.
2. Check revision, instance count, concurrency, startup time, and 429/503 logs.
3. Check service/revision max instances and regional CPU/memory quotas.
4. Check Cloud SQL connection pools and external API quotas.
5. Adjust max/concurrency or min instances **after benchmarking**.
6. Deploy a canary and monitor p95, DB load, and billing.
7. If capacity cannot scale further, return graceful 429s or queue requests per business rules.

### Playbook E: Cloud SQL `too many connections`

1. Inspect pool metrics and DB connection counts.
2. Cross-check application replica counts, workers, and recent rollouts.
3. Safely reduce/cap concurrency or pool sizes.
4. Hunt for connection leaks and slow transactions.
5. Evaluate database instance sizing and connection management.
6. Verify whether timed-out/retried transactions caused duplicate writes.
7. Run load tests after making changes.

## 19. Hands-On Practice: Simulating Errors and Verifying Handling

This lab **never intentionally overloads** production systems or live Google Cloud APIs. Use sandboxes, existing logs/events, or synthetic records to practice classification.

### Exercise 1: Classify Five Error Records

~~~json
[
  {
    "service": "Compute Engine",
    "reason": "QUOTA_EXCEEDED",
    "location": "region-a",
    "quota_usage_percent": 100
  },
  {
    "service": "Compute Engine",
    "reason": "ZONE_RESOURCE_POOL_EXHAUSTED",
    "location": "zone-b",
    "quota_usage_percent": 60
  },
  {
    "service": "GKE",
    "reason": "scale.up.error.ip.space.exhausted",
    "location": "cluster-c"
  },
  {
    "service": "Cloud Run",
    "http_status": 429,
    "message": "The request was aborted because there was no available instance"
  },
  {
    "service": "Java",
    "reason": "java.lang.OutOfMemoryError: Java heap space"
  }
]
~~~

For each record, document: the failure layer, what additional evidence to collect, three actions to try, and one action **never to take**. These records are synthetic practice examples and do not reflect metrics or logs from any real project.

### Exercise 2: Build a Dashboard

1. Pick one service and one quota metric.
2. Create charts for usage, limit, and quota-exceeded events if the service emits those metrics.
3. Add service request rate/latency, 429/503 counts, and downstream saturation.
4. Configure a planning alert before quota exhaustion and an incident alert for user impact.
5. Test the notification channel within authorized boundaries.
6. Attach a runbook and owner to every alert.

### Exercise 3: Plan for Doubled Traffic

Assume Orders API peak traffic doubles and Cloud SQL is a shared dependency. Calculate:

- Requests/second and resulting downstream API calls.
- Instance count and DB pool connections.
- Regional vCPU/memory quotas and GKE Pod IP headroom (if running on GKE).
- Required node count if one zone fails.
- Cost impact if min instances or reservations must increase.
- p95/429/503 thresholds that trigger a rollout halt.

### Lab PASS Criteria

- Correctly distinguishes quotas, physical capacity, and application exhaustion.
- Does not propose a quota increase for a zone capacity error.
- Uses metric/log evidence with scope and timestamps.
- Includes bounded retries/backpressure.
- Defines owner, escalation, rollback, and cost estimates.
- Performs no destructive or overloading actions on real resources.

## 20. Sample Incident Report and GO/NO-GO Decision

~~~yaml
incident_id: "INC-EXAMPLE-2026-001"
service: "orders-api"
environment: "production"
project_id: "PROJECT_ID"
location: "REGION_OR_ZONE"
start_time_utc: "YYYY-MM-DDTHH:MM:SSZ"
impact:
  affected_transactions: "TO_BE_MEASURED"
  error_rate: "TO_BE_MEASURED"
evidence:
  error_reason: "QUOTA_EXCEEDED"
  quota_metric: "EXACT_METRIC_FROM_CONSOLE"
  quota_limit: "MEASURED_VALUE"
  quota_usage: "MEASURED_VALUE"
  request_id: "REDACTED"
classification: "quota_allocation"
mitigation:
  action: "PAUSE_NON_CRITICAL_JOB_AND_REVIEW_QUOTA"
  owner: "platform-oncall"
permanent_actions:
  - "Capacity forecast and approved quota adjustment"
  - "Quota headroom alert and load test"
validation:
  customer_errors_recovered: false
  backlog_draining: false
  quota_headroom_confirmed: false
decision: "NO-GO_UNTIL_VALIDATION"
approvers:
  - "incident-commander"
  - "service-owner"
~~~

This is an **incident ticket/log template**, not a GCP configuration. Switch to GO only after recovery criteria are verified and approved by the system and change owners.

### Mandatory Rollout-Stop Conditions

- Insufficient quota/capacity for deployment or failover.
- Rising 429/503 rates with an unidentified bottleneck.
- Persistent unexplained GKE Pending Pods.
- Cloud SQL connections approaching limits while latency climbs.
- Missing rollback path or risk of data loss from retries/duplicate writes.
- No alert recipient or authorized incident responder available.

## 21. Common Troubleshooting Mistakes

| Wrong Action | Why Dangerous | Better Approach |
|---|---|---|
| Raising CPU quota to fix `ZONE_RESOURCE_POOL_EXHAUSTED` | Does not add physical hardware to the zone | Switch zone/machine type, use reservation |
| Blindly retrying every `RESOURCE_EXHAUSTED` | Retry storms, cost spikes, held connections | Read error details, use bounded backoff |
| Stopping and starting a VM during a zone capacity shortage | VM may fail to start again | Keep VM running; evaluate reservations |
| Raising Cloud Run max instances without sizing DB connections | Overloads downstream database | Tune pools, rate limits, and concurrency |
| Setting GKE memory requests too low | OOMs, evictions, noisy neighbors | Measure working set and pick appropriate nodes |
| Deleting unowned resources to free quota | Risks data loss or breaking DR | Asset inventory and approval before deletion |
| Assuming 70% quota usage is always safe | Brief bursts can trip rate quotas | Chart appropriate windows and `quota-exceeded` metrics |
| Assuming Pod Pending always means vCPU quota | Could be IPs, PVCs, or taints | Read scheduler/autoscaler events |
| Raising DB `max_connections` without checking RAM | Increases memory pressure and contention | Connection pool budgeting and benchmarked scaling |
| Ignoring `Retry-After` and retrying immediately | Amplifies load during throttling | Backoff + jitter + deadline |
| Switching regions without checking residency/DR | Policy violations, higher latency/egress | Security approval and load testing |
| Looking only at metrics without user impact | Wasted pages or missed outages | Tie quotas to SLOs and business KPIs |

## 22. Operational Checklist Before Traffic Increases or Go-Live

- [ ] Service has documented owner, project, region/zone, and workload dependency map.
- [ ] Key allocation/rate/concurrent quotas and system limits are inventoried.
- [ ] Usage and limits have dashboards with appropriate observation windows.
- [ ] Quota-exceeded and headroom alerts exist for high-risk resources.
- [ ] API clients implement bounded retries, exponential backoff, jitter, timeouts, and idempotency.
- [ ] Rate limiters, bounded queues, or graceful degradation plans are in place.
- [ ] Cloud Run max instances, concurrency, and regional CPU/memory quotas are tested.
- [ ] GKE node requests/allocatable, Pod IP space, and autoscaler/max nodes are verified.
- [ ] Compute Engine/GPU/TPU have plans for zone capacity shortages.
- [ ] Reservations/provisioning models are evaluated for critical workloads.
- [ ] Cloud SQL pool budgets, storage, and saturation are monitored.
- [ ] BigQuery/Pub/Sub/Storage API quotas for high-load jobs are reviewed.
- [ ] Peak/burst/soak load tests and failover capacity tests are completed.
- [ ] Quota change procedures, cost approvals, and lead times are documented.
- [ ] On-call, escalation, runbooks, and rollback policies are active.
- [ ] Limits/budgets are not raised indefinitely just to mask application bugs.
- [ ] Post-recovery, error rates, backlogs, p95 latency, and data integrity are verified.

## Review Questions

1. How do allocation quotas and rate quotas differ? Why must location/scope always be checked?
2. Why cannot `ZONE_RESOURCE_POOL_EXHAUSTED` be fixed by increasing CPU quota?
3. What causes can leave a GKE Pod `Pending` besides insufficient CPU quota?
4. When Cloud Run returns 429 "no available instance," which settings should be inspected?
5. Regional CPU quota still has headroom, yet a VM fails to create: what are three hypotheses and how do you test them?
6. Why can a Java container get `OOMKilled` even when `-Xmx` is lower than the container memory limit?
7. When should `RESOURCE_EXHAUSTED` be retried and when should it not?
8. Why are full jitter and a total retry deadline necessary?
9. Why must you budget database connections before scaling Cloud Run instances?
10. What does the `serviceruntime.googleapis.com/quota/exceeded` metric mean, and do all products emit the exact same metric?
11. How do reservations help capacity, and can they replace quotas?
12. How do you prove a capacity incident has truly been resolved rather than merely subsiding temporarily?

## Conclusion

**Quota exceeded**, **resource exhausted**, and **capacity shortage** are easily confused symptom groups that must be handled at different layers. Quotas are administrative limits by scope and resource type; capacity is physical hardware or real serving capability; resource exhaustion can happen inside the JVM, a Pod, a database, or an application queue.

A sound runbook starts from the **error code and error details**, identifies the exact project/region/service/metric, compares usage against limits, checks workload health, and **applies safe impact mitigations**. For rate errors, use backoff/jitter, flow control, and quota planning. For Compute Engine capacity shortages, choose the right zone, machine type, or reservation. For GKE and Cloud Run, inspect the scheduler, autoscaling, IP space, instance ceilings, memory, and downstream dependencies. For Java and Cloud SQL, controlling heap, thread pools, and database connections often matters more than increasing quotas.

To prevent repeat incidents, combine Cloud Monitoring quota metrics, load testing, SLOs, capacity forecasting, approved quota workflows, HA/DR plans, and FinOps. The goal is not "never seeing a 429," but building **a system that detects, mitigates, and recovers when limits are reached without corrupting data or blowing the budget**.

## References

- [Cloud Quotas: Overview](https://cloud.google.com/docs/quotas/overview)
- [Cloud Quotas: Troubleshoot quota errors](https://cloud.google.com/docs/quotas/troubleshoot)
- [Cloud Quotas: View and manage quotas](https://cloud.google.com/docs/quotas/view-manage)
- [Cloud Quotas: Request quota adjustments](https://cloud.google.com/docs/quotas/quotas-adjust)
- [Cloud Monitoring: Chart and monitor quota metrics](https://cloud.google.com/monitoring/alerts/using-quota-metrics)
- [Compute Engine: Troubleshoot resource availability errors](https://cloud.google.com/compute/docs/troubleshooting/troubleshooting-resource-availability)
- [Compute Engine: Troubleshoot quota errors](https://cloud.google.com/compute/docs/troubleshooting/troubleshooting-quota-errors)
- [Compute Engine: Resource reservations](https://cloud.google.com/compute/docs/instances/reservations-overview)
- [Compute Engine: Regions and zones](https://cloud.google.com/compute/docs/regions-zones)
- [GKE: Troubleshoot Cluster Autoscaler scale-up](https://cloud.google.com/kubernetes-engine/docs/troubleshooting/cluster-autoscaler-scale-up)
- [GKE: Troubleshoot deployed workloads](https://cloud.google.com/kubernetes-engine/docs/troubleshooting/deployed-workloads)
- [GKE: Node allocatable resources](https://cloud.google.com/kubernetes-engine/docs/concepts/plan-node-sizes)
- [Cloud Run: Troubleshoot service issues](https://cloud.google.com/run/docs/troubleshooting)
- [Cloud Run: Maximum instances limits](https://cloud.google.com/run/docs/configuring/max-instances-limits)
- [Cloud Run: Configure maximum instances](https://cloud.google.com/run/docs/configuring/max-instances)
- [Cloud Run: Instance autoscaling](https://cloud.google.com/run/docs/about-instance-autoscaling)
- [Cloud SQL PostgreSQL: Database connections](https://cloud.google.com/sql/docs/postgres/manage-connections)
- [Pub/Sub: Quotas and limits](https://cloud.google.com/pubsub/quotas)
- [BigQuery: Quotas and limits](https://cloud.google.com/bigquery/quotas)
- [BigQuery: Optimize query computation](https://cloud.google.com/bigquery/docs/best-practices-performance-compute)
- [Cloud Storage: Request rate and access distribution guidelines](https://cloud.google.com/storage/docs/request-rate)
- [Google SRE Workbook](https://sre.google/workbook/table-of-contents/)
