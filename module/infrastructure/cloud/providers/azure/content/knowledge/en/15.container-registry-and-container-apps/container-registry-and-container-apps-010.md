# Event-Driven Scaling with KEDA in Container Apps

An invoice-processing system may sit nearly idle at night yet receive thousands of requests within minutes when a retail app closes orders. Maintaining many containers at all times means paying for underutilized resources; running only one container causes the queue to back up during spikes. **Azure Container Apps** supports scaling application instances (**replicas**) up or down based on HTTP traffic or signals from queues, event streams, and other data sources via built-in **KEDA (Kubernetes Event-driven Autoscaling)** autoscaling.

Example: a user uploads a PDF to Blob Storage, the system emits an event via Event Grid, and creates a message in an **Azure Service Bus Queue**. A Container Apps worker reads the queue, validates the file, extracts content, and persists the result. As the queue accumulates messages, the scaler scales replicas up; when work finishes, replicas can scale down to zero if configuration and rule type allow.

This lesson belongs to the **Container Registry and Container Apps** chapter in the Microsoft Azure learning path covering subscriptions, resource groups, Microsoft Entra ID, virtual networking, compute, storage, data, monitoring, security, and cost control. The focus is designing **autoscaling behavior that satisfies SLOs and correctness**, not merely picking a queue threshold.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish Azure Container Apps, KEDA, event sources, scale rules, and replicas.
2. Compare HTTP autoscaling, custom event-driven scaling, and Container Apps Jobs.
3. Design a worker using Azure Service Bus or Azure Queue Storage as its load source.
4. Understand minReplicas, maxReplicas, scale-to-zero, cold starts, and backlog thresholds.
5. Configure scale rules and inspect revisions/replicas via the Azure portal and CLI.
6. Design consumers safe against retries, duplicates, lock timeouts, and scale-in.
7. Use managed identities, RBAC, ACR, secrets, and private networking.
8. Monitor SLAs, backlogs, throughput, costs, and troubleshoot common scaling errors.

## 1. What Problem Does KEDA Solve?

**KEDA** is an event-driven autoscaling mechanism. With Azure Container Apps, the platform exposes KEDA-based scale rules for supported scalers; users **do not deploy a Kubernetes HPA or KEDA operator themselves**.

~~~text
App uploads PDF
         |
         v
Azure Blob Storage
         |
         v
Event Grid / event emitter
         |
         v
Service Bus Queue: invoice-jobs
         |
         +--------------------------+
         |                          |
         v                          v
KEDA scaler inspects backlog     Container Apps Workers
         |                       receive and process messages
         v                          |
Recommends replica count            v
         |                     Save results / ACK
         v
Container Apps scales replicas up/down
~~~

KEDA **does not read and process PDF files on the app's behalf**; it inspects work signals from the queue and adjusts the replica count. Worker code must still connect to the broker, receive messages, validate payloads, write outputs, and acknowledge completion.

### Why Not Scale Solely on CPU?

An idle worker has very low CPU utilization, yet the queue might have just received 10,000 messages. Waiting for CPU to climb delays reaction. Scaling on waiting message counts directly reflects incoming work demand.

Conversely, queue length does not reflect every processing cost: one message could be a small image or a multi-hundred-page PDF; workers may be bottlenecked by databases, OCR, or external APIs. Scale rules must be measured and tuned using real operational telemetry.

## 2. Foundational Concepts

| Concept | Meaning |
|---|---|
| **Container Apps environment** | Shared deployment, infrastructure, and connectivity boundary for multiple apps |
| **Container App** | Resource representing a containerized workload |
| **Revision** | Version of app configuration under Container Apps' revision mechanism |
| **Replica** | A running instance of a revision containing the template's containers |
| **Scale rule** | Declaration of signal source, metadata, and authentication for the scaler |
| **Scaler** | Component observing load, e.g., queue length or HTTP concurrency |
| **minReplicas** | Minimum replica count the platform aims to maintain |
| **maxReplicas** | Upper limit on replicas when scaling out |
| **Scale target** | Target threshold used to estimate required capacity |

**A replica is not a message**: a single replica can process multiple messages concurrently; a single message can be redelivered if a prior attempt failed. Scalers do not pin specific messages to specific replicas.

### Revisions and Scale Rules

Scale configuration belongs to the template tied to a Container App revision. Modifying the template can create a new revision. In multiple-active-revisions mode, different worker versions can pull from the same queue simultaneously. If a new message schema is incompatible with the old version, a rollout can cause failures even when the scaler functions normally.

For simple queue consumers, clearly choose **single active revision** versus multiple revisions, along with a work-draining strategy before switching versions.

## 3. Choosing an Autoscaling Signal Type

| Scale Type | Signal | Best-Fit Applications |
|---|---|---|
| **HTTP scaling** | Concurrent HTTP requests via ingress | Web APIs and services receiving direct requests |
| **TCP scaling** | TCP connections per supported ingress mechanism | Suitable TCP workloads with matching ingress |
| **Custom KEDA scaler** | Queue length, event source, or external metric | Workers consuming Service Bus, Storage Queue, Kafka, Event Hubs |
| **Container Apps event-driven Jobs** | Signal spawning job executions | Batch/run-to-completion tasks with a defined end |

Not every open-source scaler in the KEDA project is automatically supported in every version of Azure Container Apps. Verify the exact **scaler type, metadata, and authentication method** offered by your target environment.

### HTTP Scaling vs. Queue Scaling

~~~text
HTTP:
Browser -> Container Apps Ingress -> Web/API replicas
                 |
                 +-> HTTP concurrency serves as scale signal

Queue:
Producer -> Service Bus Queue
                |
                +-> KEDA reads queue backlog to scale
                |
                +-> Worker replicas connect directly to receive messages
~~~

Queue workers generally **do not need external HTTP ingress**. Enable ingress only if the workload genuinely exposes an API or protected management endpoint; avoid exposing unnecessary internal endpoints publicly.

## 4. minReplicas, maxReplicas, and Scale-to-Zero

A standout benefit of event-driven Container Apps is **scale-to-zero**: when the event source has no remaining work, the platform can scale replicas down to zero if permitted by scaler/rule conditions and configuration.

| Setting | Behavior | Trade-off |
|---|---|---|
| **minReplicas = 0** | Can maintain zero workers when queue is empty | Saves compute resources yet incurs cold starts |
| **minReplicas = 1** | Keeps at least one worker running | Faster response, carries baseline cost |
| **minReplicas = 2** | Keeps two baseline workers running | Better initial headroom, higher baseline cost |
| **maxReplicas = 8** | Replicas will not exceed the configured cap | Queue may still back up if load exceeds eight replicas' capacity |

**maxReplicas does not guarantee replicas are provisioned instantaneously.** The platform still needs sufficient quota/capacity, pullable images, successful container startup, and authenticated scaler access.

### Understanding Backlog Thresholds

Suppose:

~~~text
minReplicas = 0
maxReplicas = 8
Service Bus active messages = 60
Illustrative threshold = 10 messages / replica

Sizing estimate: ceil(60 / 10) = 6 replicas

If backlog grows to 150:
  Estimate is 15, capped at maxReplicas = 8.
~~~

This is merely a **conceptual division**, not a binding formula across all Container Apps/KEDA scenarios. Actual replica counts depend on scaler signals, polling intervals, activation, cooldowns, concurrency, resource limits, and application health.

### Cold Starts

When the queue is empty and replicas sit at 0, a new message must wait for:

1. The scaler to detect incoming work at the source.
2. The platform to allocate resources to run a replica.
3. The image to be ready and the worker process to boot.
4. The worker to establish DNS/networking, identity, and broker connections.
5. The worker to receive the message and begin processing.

Wait times are not fixed. Large images, heavy startup, DNS misconfigurations, missing permissions, or capacity constraints lengthen latency. For tight SLOs, consider **minReplicas greater than 0** and optimize startup.

### Scale-In Requires Managing In-Flight Work

A queue may report zero active messages while workers still hold locks on messages currently in progress. During scale-in, containers can receive termination signals. Workers must handle **SIGTERM**, stop accepting new work, and finish or safely release in-flight tasks; never store critical state solely on a replica's ephemeral filesystem.

## 5. Example Architecture: Invoice Processing

An invoicing system includes:

- Azure Blob Storage storing PDFs in the **incoming** container.
- Event Grid emitting notifications when files are created.
- An ingest component writing a small message into **Azure Service Bus Queue invoice-jobs**.
- Azure Container Apps workers reading the queue, extracting data, and writing output.
- Azure Container Registry (ACR) storing worker images.
- Azure Monitor and a job ledger recording status and processing duration.

~~~text
Blob Storage/incoming
         |
         v
      Event Grid
         |
         v
    Ingest Function
         |
         v
Service Bus Queue: invoice-jobs
         |
         +----------------------+
         |                      |
         v                      v
    KEDA scaler             Worker replicas
  checks backlog          (1 to N based on load)
         |                      |
         v                      v
   min=0, max=8          Read Blob -> process
                                |
                                v
                       processed/ + job ledger
~~~

The queue decouples user upload rates from OCR/data extraction capacity. During peak periods, the backlog is durably buffered while workers scale with load signals. If a worker fails, messages can be retried or moved to the DLQ per broker/app configuration.

**Event Grid delivery and Service Bus processing are two separate layers.** Event Grid retries delivery to the ingest component; Service Bus enforces locks, delivery counts, and dead-lettering on consumer failures. Monitor both layers.

## 6. Configuring a Service Bus Scale Rule

Suppose we want up to eight workers with a reference threshold of ten active messages per replica:

| Field | Illustrative Value | Notes |
|---|---|---|
| Rule name | invoice-queue-scaler | Easy-to-find name in logs |
| Scale type | azure-servicebus | Custom scaler type |
| Queue name | invoice-jobs | Must exist |
| Namespace | sb-sales-prod | Depends on auth method requirements |
| messageCount | "10" | Scaler backlog target |
| minReplicas | 0 | Enables scale-to-zero |
| maxReplicas | 8 | Consumption cap |
| Authentication | Secret reference or managed identity | Must match supported schema/conditions |

### Illustrative YAML Snippet

~~~yaml
# Illustrative template.scale snippet; not a complete ACA manifest.
template:
  scale:
    minReplicas: 0
    maxReplicas: 8
    rules:
      - name: invoice-queue-scaler
        custom:
          type: azure-servicebus
          metadata:
            queueName: invoice-jobs
            messageCount: "10"
          auth:
            - secretRef: servicebus-connection
              triggerParameter: connection
~~~

In this example, **servicebus-connection** is the name of a secret securely configured inside the Container App, **not a literal connection string**. The secret must be created beforehand with least-privilege permissions for the scaler to inspect the queue. This snippet omits the image, Container Apps environment, resource identity, and secret definitions, so **it cannot be deployed verbatim**.

**Managed identity** is preferred where supported by the scaler type, version, and environment. With managed identity, metadata and auth configuration differ from the `secretRef` example; consult the scaler's service documentation before deploying.

### Scaler Permissions Differ from Worker Permissions

The KEDA scaler needs permission to **read message counts/metrics** from Service Bus. The worker needs permission to **receive, complete, abandon, or dead-letter** messages. If the scaler lacks permissions, the app may fail to wake from 0. If the worker lacks permissions, replicas scale up while the backlog never drains.

Never grant broad namespace admin rights just because reading queue length failed; separate authentication, RBAC, and network paths for each component.

## 7. Using Azure Queue Storage Instead of Service Bus

Another option is **Azure Queue Storage**. The scale rule uses type **azure-queue** with matching metadata:

| Common Metadata | Meaning |
|---|---|
| **queueName** | Azure Storage Queue name |
| **queueLength** | Message count threshold used for scaling |
| **accountName** | Storage Account hosting the queue per supported auth |
| **Authentication** | Connection secret or managed identity per support |

Do not copy Service Bus's **messageCount** metadata key to Azure Queue, as the two scalers have different schemas.

### Which Broker Should You Choose?

| Criterion | Azure Queue Storage | Azure Service Bus Queue |
|---|---|---|
| Workload type | Simple queuing | Advanced enterprise messaging |
| Receive control | Visibility timeout | Peek-lock/settlement per service |
| Error handling | Poison handling managed by app/integration | Built-in dead-letter subqueue |
| Sessions | No equivalent to Service Bus sessions | Sessions under supported conditions |
| KEDA scaler | azure-queue | azure-servicebus |
| Cost | Storage service and operations pricing | Tier/operations and feature pricing |

Regardless of broker, **KEDA does not provide exactly-once processing**. Consumers must handle retries and duplicate business side effects themselves.

## 8. Workers Must Receive and Process Messages Themselves

A Container App with a valid scale rule whose image code never reads the queue still accomplishes nothing. The worker must implement receiving, writing output, and acknowledging messages.

~~~text
startup:
    authenticate using managed identity
    connect to Service Bus and Blob Storage
    prepare durable job ledger

loop:
    receive one or more messages
    validate message schema and job identifier

    if job already SUCCEEDED:
        complete duplicate message
        continue

    atomically claim the job
    read exact blob version or validate ETag
    validate file type, size, security checks
    transform and write deterministic output
    record SUCCEEDED durably
    complete message

    if permanent invalid input:
        record rejection
        dead-letter message with safe diagnostic

    if transient failure:
        abandon or retry under bounded policy

on SIGTERM:
    stop receiving new messages
    finish or safely relinquish in-flight work
    close connections and flush telemetry
~~~

This is **pseudocode**, not production-ready implementation code. Use the SDK and authentication mechanisms matching your actual broker.

### Non-Negotiable Principles

1. **At-least-once:** messages can be redelivered after crashes or lock expirations.
2. **Idempotency:** the same jobId must never produce duplicate business results.
3. **Atomic claim:** use unique keys or conditional writes for job state; check-then-write is unsafe across concurrent replicas.
4. **Ack after durable output:** complete the message only after output and ledger updates succeed.
5. **Lock renewal:** long-running jobs must renew locks/visibility timeouts where broker-supported.
6. **Dead-lettering:** unrecoverable data errors should not retry endlessly.
7. **Graceful shutdown:** scale-in must not silently drop in-flight work.
8. **Correlation IDs:** link message, blob, output, and replica across logs.

### Prefetch and Concurrency Affect Scale Results

A worker may prefetch multiple messages or process messages concurrently. Active queue backlog may look low while considerable work remains **in-flight**. If locks expire, messages return to the queue. Hence, **active message count reaching 0 does not prove the pipeline is finished**.

Tune prefetch to match CPU/RAM capacity and processing time; monitor active, locked, dead-lettered counts, and job ledger states together.

## 9. Sizing Based on Throughput and SLA

Suppose one replica processes **6 invoices/minute** and must finish **600 invoices in 20 minutes**.

~~~text
Required rate:      600 / 20 = 30 invoices/minute
Single replica rate: 6 invoices/minute
Theoretical replicas: ceil(30 / 6) = 5
~~~

The result 5 includes no buffer for cold starts, heavy files, database waits, retries, or throttling. Run load tests to choose real min/maxReplicas and message thresholds.

### Metrics to Measure When Sizing

- Time from enqueue to processing start.
- Processing latency p50/p95/p99 per job type.
- Waiting, locked, and DLQ message counts.
- Completed throughput per replica and system-wide.
- CPU, RAM, networking, and backend connection counts.
- Time to scale from 0 to 1 or multiple replicas.
- Retry rates and job failure rates.

**Scaling out can harm the system** when a downstream database allows 20 connections yet 30 replicas open multiple connections simultaneously. Caps on maxReplicas, concurrency, connection pools, and retry rates must align with the entire architecture.

## 10. When to Use Container Apps Jobs?

Container Apps provides **Jobs**, suited to tasks with a start and finish. An event-driven Job can use a scaler to trigger **job executions**, unlike scaling a Container App running a continuous worker loop.

| Characteristic | Container App Worker | Event-Driven Container Apps Job |
|---|---|---|
| Lifecycle | Replicas run a long-lived consumer | Job execution runs then terminates |
| Scale mechanism | Adjusts replica count | Adjusts execution count per configuration |
| Best suited for | Continuous listeners processing many messages | Batch/run-to-completion tasks |
| Message ack | Worker code must acknowledge | Job code must still acknowledge per business logic |
| Config settings | minReplicas/maxReplicas | Executions/parallelism settings suited to Jobs |

Do not copy a Job's **maxExecutions** setting onto a Container App's **maxReplicas**. Choose the model based on application lifecycle and error-handling needs.

## 11. Deploying via the Azure Portal

The steps below suit labs with proper permissions and budgets. **Container Apps environments, ACR, Service Bus, Storage, and logs can all incur charges.**

### Step 1: Prepare the Worker Image

Write the program to consume the queue, handle errors, and log safely. Containerize it, test locally with test inputs, and publish the image to **Azure Container Registry**.

- Use specific version tags or digests rather than relying on an uncontrolled latest tag.
- Never embed secrets in the Dockerfile/image.
- Run processes with least privilege and handle shutdown signals.
- Ensure no critical state is stored solely on the container filesystem.

### Step 2: Prepare Service Bus

Create a namespace and the **invoice-jobs** queue in an authorized environment. Producers send small messages containing jobId, blob reference, and ETag/version; never place entire PDFs into the queue.

Test sending, receiving, completing, and dead-lettering in an environment free of customer data.

### Step 3: Create the Container Apps Environment and App

Create the environment in an appropriate region, selecting networking, workload profiles, logging, and administrative rights. Create the Container App from the ACR image, configuring CPU/RAM, managed identity, environment variables, and data connections.

Queue-consuming workers typically do not need external ingress. If an admin dashboard is needed, protect it appropriately rather than exposing the worker directly.

### Step 4: Configure Scale Rules

In the **Scale** section, set minReplicas=0, maxReplicas=8 for the lab. Add a custom rule of type **azure-servicebus** targeting queue **invoice-jobs** with appropriate messageCount metadata. Configure the secret reference or identity supported by the scaler.

Check active revisions after saving. If the app uses multiple active revisions, ensure older versions do not consume messages with incompatible schemas.

### Step 5: Load Testing

Send a few test messages. Watch replicas scale up from 0, the consumer receive/complete messages, outputs appear, and the backlog drain. Once idle, observe scale-in without expecting it to be instantaneous.

Next, send 50–100 messages to measure throughput, processing time, resource consumption, and scaling behavior. Avoid pushing load past downstream limits.

### Step 6: Fault Testing

In the lab, simulate:

- A valid message.
- A malformed schema message to verify DLQ routing.
- Two messages with the same jobId to verify idempotency.
- A transient error to verify retries and backoff.
- Stopping/redeploying a worker mid-processing to verify lock recovery.

Document findings and clean up only lab resources confirmed no longer in use.

## 12. Read-Only Checks via Azure CLI

The commands below are **read-only** and do not create or modify configurations. Subscription/resource group/app names are illustrative.

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

az containerapp show \
  --resource-group "rg-container-lab" \
  --name "invoice-worker" \
  --query "{name:name,state:properties.provisioningState,environment:properties.environmentId}" \
  --output json
~~~

### View Scale Rules

~~~bash
az containerapp show \
  --resource-group "rg-container-lab" \
  --name "invoice-worker" \
  --query "properties.template.scale" \
  --output json
~~~

Inspect min/maxReplicas, rule types, metadata, and identity/secret references. Avoid printing secret values to logs.

### View Revisions and Replicas

~~~bash
az containerapp revision list \
  --resource-group "rg-container-lab" \
  --name "invoice-worker" \
  --output table

az containerapp replica list \
  --resource-group "rg-container-lab" \
  --name "invoice-worker" \
  --revision "<ACTIVE_REVISION_NAME>" \
  --output table
~~~

An empty replica list can be normal when minReplicas=0 and the source has no work. When backlog actually grows, inspect system logs and scale rules rather than immediately assuming the app is broken.

### Read Worker Logs

~~~bash
az containerapp logs show \
  --resource-group "rg-container-lab" \
  --name "invoice-worker" \
  --type console \
  --tail 100
~~~

### Inspect Service Bus Queue Status

~~~bash
az servicebus queue show \
  --resource-group "rg-container-lab" \
  --namespace-name "sb-sales-lab" \
  --name "invoice-jobs" \
  --output json
~~~

Compare active message counts, dead-letter counts, API-supported runtime properties, and replica counts **at the same point in time**. Azure CLI/extension versions may require updating per documentation before running Container Apps commands.

## 13. Security: Scaler and Worker Are Two Access Paths

### Managed Identity and RBAC

Prefer **managed identities** for the Container App and dependent services where supported:

| Target | Permissions to Evaluate |
|---|---|
| Azure Container Registry | Image pull permission, e.g., AcrPull per supported mechanism |
| Service Bus scaler | Queue state/metrics read permission per scaler support |
| Service Bus worker | Receive/settle message permissions on the target queue |
| Blob Storage | Data-plane role to read inputs and write outputs at proper scope |
| Job ledger/DB | Permission to create/update business records |

Distinguish the **scaler** role from the **worker** role. When the scale rule lacks permissions, replicas may not scale up; when the worker lacks permissions, replicas scale up yet work never finishes.

### Secrets

If a connection string must be used, store it in a **Container App secret** or a Key Vault reference where supported. The scale rule references only the secret name. Apply rotation/revocation policies and never place connection strings in images, repository YAML, or logs.

### Private Networking

For Service Bus or Storage restricted via Private Endpoints, verify **connectivity and DNS for both the scaler and the worker** within your supported environment type. Confirming the worker reaches the queue privately does not automatically prove the scaler can read queue metrics.

Never open public network access to all sources merely to bypass a 403 or timeout before isolating the root cause.

## 14. Multiple Scale Rules and Multiple Active Revisions

One app can declare multiple supported scale rules, yet do not assume recommended replica counts **simply add together**. The platform reconciles scaling requests across signals; check official behavior and run load tests.

Two active revisions can consume from the same queue concurrently. Example:

~~~text
revision v1: understands old message schema
revision v2: requires new currency field
shared queue: invoice-jobs

If v1 and v2 both receive messages:
  -> v1 may receive incompatible new messages
  -> messages retry or land in DLQ
~~~

Mitigations:

1. Design backward-compatible message schemas during transitions.
2. Control active revision mode.
3. Consider separate queues per version or job type when needed.
4. Drain/stop receiving and enforce graceful shutdown.
5. Maintain idempotency across post-deployment retries.

## 15. Monitoring Performance and SLAs

Never evaluate autoscaling solely by "how many replicas are running." Business SLOs are **jobs completed on time, accurate outputs, and reasonable cost**.

| Signal | What to Observe |
|---|---|
| Active messages | Waiting workload |
| Oldest message age | Age of oldest waiting task vs. SLA |
| Locked/in-flight messages | Work received but not yet completed |
| Dead-letter messages | Failed jobs needing investigation or replay |
| Replicas by revision | Whether scaling occurs and which version is running |
| Worker throughput | Completed jobs/minute |
| Latency p50/p95/p99 | Processing time and tail latency |
| End-to-end latency | From enqueue to ready output |
| Retry/duplicate rate | Stability and correctness |
| CPU, RAM, and connection usage | Per-replica limits |
| 401/403, timeouts | Authentication vs. networking faults |
| Cost per successful job | End-to-end pipeline efficiency |

Example correlated log entry:

~~~json
{
  "jobId": "invoice-2026-001",
  "queue": "invoice-jobs",
  "revision": "invoice-worker--rev42",
  "replica": "replica-id",
  "attempt": 2,
  "state": "SUCCEEDED",
  "durationMs": 2250
}
~~~

Never log SAS tokens, account keys, or full payloads containing customer or invoice data. Use Azure Monitor, Log Analytics, Application Insights/telemetry, and broker metrics per supported configuration.

### Recommended Alerts

- Oldest message age breaches SLA.
- Backlog grows even while replicas sit at maxReplicas.
- Replicas remain at 0 for an extended period while active messages sit in the queue.
- Worker crash loops or continuous auth errors.
- Unusual spikes in dead-letter messages.
- Compute or monitoring spend exceeds budget.

## 16. Troubleshooting Common Errors

| Symptom | Possible Causes | Checks |
|---|---|---|
| Queue has messages yet replicas stay at 0 | Wrong rule type/metadata/auth or networking | Inspect scale config, identity, system logs, and queue source |
| Replicas scale up yet backlog does not drop | Worker fails to receive, missing permissions, or processing errors | Inspect worker logs, Service Bus roles, and retries |
| Only one replica runs despite large backlog | Threshold too high, low max/quota, or wrong metric | Inspect rule, quotas, queue metrics, and revision |
| Container crash loop | Startup error, image issue, env var error, or OOM | Inspect replica status and console logs |
| Job processed twice | Message retry/lock expired and missing idempotency | Check jobId, ledger, and lock renewal |
| DLQ grows steadily | Bad payload, schema mismatch, or exhausted attempts | Read dead-letter reasons and fix message contract |
| Cannot connect to Service Bus | DNS, egress, private endpoint, secret, or RBAC | Separate timeouts from 401/403 |
| Slow scale-to-zero wake-up | Cold start, heavy image, or scaler polling | Measure latency and consider minReplicas=1 |
| More replicas reduce throughput | Downstream database/API throttling | Measure concurrency, 429/5xx, and connection pools |
| Two worker groups after deployment | Multiple active revisions consuming the same queue | Inspect revision list and rollout strategy |
| Queue empty yet fails to scale in | Non-zero minReplicas, cooldown, or another active rule | Inspect all scale rules and conditions |
| Active count 0 yet job unfinished | Messages locked/in-flight | Check job ledger and settlement status |

### Six-Step Diagnostic Flow

1. **Source:** right queue/namespace, and what are active/locked/dead-letter counts?
2. **Rule:** right type/metadata, min/max, secretRef/identity, and active revision?
3. **Scaler:** any auth, DNS, egress, or metric errors in platform logs?
4. **Replica:** did image pull succeed, process start, any OOM/restarts?
5. **Consumer:** proper receive/complete/abandon logic, lock timeouts, or duplicates?
6. **Downstream:** are Blob, database, or OCR throttling or failing and dragging throughput down?

If every replica fails with 403, raising maxReplicas only multiplies errors and increases costs. Fix the right layer before tuning scale settings.

## 17. Cost and Scale Optimization

Scale-to-zero reduces worker compute time when idle, **yet does not make the entire architecture free**. Account for:

- Azure Container Apps billing by **workload profile, CPU/RAM, and usage** under your active plan.
- Always-on resources when minReplicas > 0 and environment charges where applicable.
- Service Bus/Storage Queue: tier, throughput, and operations.
- ACR: image storage, tier, networking.
- Blob Storage, databases, OCR/APIs, and private networking.
- Azure Monitor/Log Analytics, retention, and log queries.

Measure **cost per successful job**, not merely replica count. Eight replicas finishing quickly are not necessarily cheaper than four replicas if downstream bottlenecks trigger mass retries and excessive logging.

Set budgets/tags on subscriptions/resource groups, and track Azure Cost Management alongside current regional/plan pricing.

## 18. Real-World Scenario: Product Image Thumbnail Generation

A company operates an e-commerce site. Users upload images to Blob Storage, Event Grid triggers an ingest service writing messages to a Service Bus Queue, and Container Apps workers generate thumbnails.

Assumptions:

- One replica processes an average of **12 images/minute** when unthrottled.
- Nearly zero uploads overnight.
- Promotional burst sends **2,400 images in 20 minutes**.
- SLA: complete processing within **30 minutes** of enqueue time.
- Downstream result API enforces a **100 requests/minute** limit.
- Some images have corrupt formats and get re-uploaded under the same filename.

### Design Requirements

1. Choose Container App worker or event-driven Job; explain.
2. Design Blob → Event Grid → queue → worker and permissions per component.
3. Propose minReplicas, maxReplicas, and backlog threshold to start load testing.
4. Calculate theoretical replicas needed to process 2,400 images in 30 minutes.
5. Explain the impact of the 100 requests/minute downstream API limit.
6. Design job IDs, ETag/versioning, idempotency, and retries.
7. Choose handling for permanent errors, DLQ, replay, and graceful shutdown.
8. Outline how to verify scale-to-zero, cold starts, metrics, SLA, and cost.

### Solution Hint

~~~text
Requirement:    2,400 images / 30 minutes = 80 images/minute
Single replica: 12 images/minute
Theoretical replicas: ceil(80/12) = 7
~~~

Seven replicas is only a **theoretical estimate**, without buffer for cold starts, complex files, retries, or burst skew. If each image requires multiple requests to an API capped at 100 requests/minute, adding more replicas alone cannot resolve the bottleneck. Bound concurrency, batch/reduce requests, or raise downstream capacity.

## 19. Production Checklist

| Category | Verification Item |
|---|---|
| Broker | Queue exists with clear producer and message schema |
| Scaler | KEDA type/metadata/auth match the Container Apps version |
| Range | min/maxReplicas align with SLA, quotas, and downstream |
| Zero | Tested scaling from 0, measured cold start, verified permissions |
| Worker | Receive/process/complete/DLQ follow contract |
| Idempotency | jobId, unique ledger, no duplicate outputs |
| Locks | Renewal, timeouts, safe SIGTERM handling |
| Image | Clear ACR version/digest, reliable startup |
| IAM | Managed identity/RBAC for ACR, scaler, queue, Blob |
| Network | Accurate DNS/egress/private endpoints for both scaler and worker |
| Revision | Controlled mode and schema migrations |
| Metrics | Backlog, age, throughput, replicas, retries, latency, and DLQ |
| Alerts | Runbooks for backlog, 403, crash loops, throttling |
| Cost | Budgets for compute, broker, registry, storage, and logs |
| Recovery | Tested retry/replay, state reconciliation, and rollback |

## 20. Self-Check Questions

1. Does KEDA directly process Service Bus messages on behalf of the worker?
2. Why is queue length usually more useful than CPU for non-HTTP consumers?
3. How does a Container App replica differ from a Container Apps Job execution?
4. What are the benefits and risks of minReplicas=0?
5. Does maxReplicas=8 guarantee eight replicas will always be created?
6. How does Service Bus's messageCount metadata differ from Azure Queue Storage's queueLength?
7. A queue has 80 messages and a target of 10 messages/replica: estimate the replica count, and explain why reality may differ.
8. Why must one message never be assumed to equal one replica?
9. Why can a worker still fail to receive messages even when the scaler has permission to read the queue?
10. When a lock expires and a message is redelivered, how do you prevent duplicate outputs?
11. Does a queue active count of 0 prove all jobs have completed?
12. How does a DLQ help with data errors and replay workflows?
13. Why can multiple active revisions cause schema errors?
14. When using a Private Endpoint, why must scaler and worker be verified separately?
15. If replicas hit max while the backlog keeps growing, which limits should you measure?
16. Which metrics directly reflect job processing SLAs?
17. Why can scale-to-zero increase latency even while saving compute?
18. How do you optimize costs without triggering downstream throttling or mass retries?

## References

- Microsoft Learn — *Set scaling rules in Azure Container Apps*: https://learn.microsoft.com/azure/container-apps/scale-app
- Microsoft Learn — *Azure Container Apps overview*: https://learn.microsoft.com/azure/container-apps/overview
- Microsoft Learn — *Azure Container Apps revisions*: https://learn.microsoft.com/azure/container-apps/revisions
- Microsoft Learn — *Azure Container Apps jobs*: https://learn.microsoft.com/azure/container-apps/jobs
- Microsoft Learn — *Managed identities in Azure Container Apps*: https://learn.microsoft.com/azure/container-apps/managed-identity
- Microsoft Learn — *Azure Container Apps networking*: https://learn.microsoft.com/azure/container-apps/networking
- Microsoft Learn — *Azure Service Bus messaging overview*: https://learn.microsoft.com/azure/service-bus-messaging/service-bus-messaging-overview
- Microsoft Learn — *Azure Container Registry overview*: https://learn.microsoft.com/azure/container-registry/container-registry-intro
- KEDA documentation — *Scalers*: https://keda.sh/docs/latest/scalers/
