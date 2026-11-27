# Cloud Tasks and HTTP Task Queue Management on Google Cloud

> **Chapter:** Application Orchestration and Integration  
> **Module:** **CLOUD_PROVIDERS_GCP** — Exploring Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners select services, protect resources, automate releases, and monitor reliability alongside cost.

When an ordering API must send receipts, update partner systems, or call a rate-limited webhook, running those operations inline during the user's request increases latency and causes cascading failures. **Cloud Tasks** decouples **registering work** from **calling the HTTP worker**: the producer enqueues a task, and Google Cloud throttles the rate, schedules delivery, calls the endpoint, and retries until a successful response is received.

This lesson focuses on **HTTP target queues** calling **Cloud Run**. Examples use a **Java/Spring Boot** application receiving commands to prepare receipts; the lab demonstrates enqueuing, dispatching, OIDC authentication, retries, and observability. The final sections describe how to add **durable idempotency** before turning the example into a real email or payment pipeline.

**Safety scope:** commands creating queues, IAM bindings, and Cloud Run services can provision billable resources; run them only in an authorized lab project. Never put card details, passwords, access tokens, or PII into task payloads or logs. The example worker only logs simulated events and **does not send real emails**.

## Learning Objectives

After this lesson, learners can:

1. Distinguish **Cloud Tasks, Pub/Sub, Eventarc, and Workflows** based on orchestration needs.
2. Understand queues, tasks, schedule time, HTTP targets, attempts, retries, rate/concurrency limits, and dispatch deadlines.
3. Configure a regional queue and choose dispatch limits matching Cloud Run worker capacity.
4. Authenticate HTTP tasks with **OIDC ID tokens** and separate **Enqueuer, Invoker, and service agent** permissions.
5. Write a Java/Spring Boot handler that parses JSON, validates input, and returns HTTP status codes following the ACK/retry model.
6. Enqueue tasks via **gcloud** or the Java Cloud Tasks SDK, including delayed scheduling.
7. Design **idempotency keys**, handle duplicate dispatches, and handle timeouts between the worker and queue.
8. Monitor backlog, 429/503 errors, retries, logging, costs, and queue lifecycle management.
9. Complete the lab and exercises, and clean up only the resources they own.

## 1. Architecture: The Producer Is Not the Worker

~~~mermaid
sequenceDiagram
    participant U as Client
    participant API as Orders API (producer)
    participant Q as Cloud Tasks queue
    participant W as Cloud Run Java worker
    participant DB as Durable job store (production)
    U->>API: POST /orders
    API->>Q: CreateTask(jobId, payload, target, OIDC)
    Q-->>API: Task resource accepted
    API-->>U: 202 Accepted / order received
    Q->>W: HTTPS POST /tasks/receipt
    W->>DB: Atomic idempotency/business outcome
    DB-->>W: Created or already processed
    W-->>Q: HTTP 2xx acknowledgment
    Note over Q,W: Non-2xx / no response → retry according to policy
~~~

**Cloud Tasks does not execute Java code itself.** It sends HTTP requests to the configured endpoint. Cloud Run, GKE, Compute Engine, or another HTTP service executes the business logic.

| Component | Role | Not Its Responsibility |
|---|---|---|
| **Producer** | Validates requests, creates tasks with target/payload | Does not wait for worker completion if async behavior is desired |
| **Queue** | Persists tasks, schedules, limits dispatch, and retries | Does not understand business logic; shares no transaction with producer DB |
| **Task** | A specific unit of work and HTTP request | Does not guarantee single execution of side effects |
| **HTTP handler/worker** | Validates requests, processes, and returns HTTP status | Should not use instance memory to store long-term state |
| **Durable store** | Business state, idempotency, job outcomes | Not automatically created by Cloud Tasks |
| **Cloud Monitoring/Logging** | Tracks backlog, attempts, errors, latency | Does not replace recovery design after tasks are dropped |

### 1.1. What Does a Task's Lifecycle Look Like?

~~~mermaid
flowchart TD
    NEW["Producer CreateTask"] --> WAIT["Task in queue\nwaiting for scheduleTime & capacity"]
    WAIT --> SEND["HTTP dispatch attempt"]
    SEND --> RESP{"What did worker return?"}
    RESP -->|"HTTP 2xx"| DONE["ACK: Cloud Tasks deletes task"]
    RESP -->|"Non-2xx / timeout / network error"| RETRY{"Within retry/retention limits?"}
    RETRY -->|"Yes"| BACK["Exponential backoff + throttling"]
    BACK --> SEND
    RETRY -->|"No"| DROP["Task dropped from queue\nneeds dedicated audit/recovery"]
~~~

**An HTTP 2xx status code means the task succeeded to Cloud Tasks**, so the task is deleted from the queue. **Non-2xx** responses or missing responses count as failed attempts and may be retried per policy. Notably, HTTP 400/401/403/404 are not "permanently ignored" by default: they can also trigger retries until limits are reached.

If the worker successfully persisted data but the response was lost due to network failure or the dispatch deadline, Cloud Tasks **may invoke it again**. Therefore, **retries and idempotency must be designed together**.

## 2. When to Use Cloud Tasks Instead of Pub/Sub, Eventarc, or Workflows?

| Requirement | Usually Suitable Tool | Reason |
|---|---|---|
| Call **a known HTTP endpoint** after receiving an order | **Cloud Tasks** | Producer controls target, schedule, rate, and retries |
| Send webhooks to a partner limited to 5 requests/s | **Cloud Tasks** | Throttles steady-state dispatch rate and concurrency |
| Wait 10 minutes then call a confirmation endpoint | **Cloud Tasks** | Supports per-task `scheduleTime` |
| Broadcast a business event to **multiple** subscribers | **Pub/Sub** | Fan-out, implicit invocation, and subscriptions |
| Capture a Cloud Storage finalized event and call a service | **Eventarc** | Event routing from supported sources |
| Orchestrate **multi-step conditional** flows, waits, branches, and API calls | **Workflows** | Stateful machine/orchestration with per-step trace |
| High-volume data streaming or consumer-initiated pull | **Pub/Sub** | Subscription flow control, not tied to one target endpoint per task |
| Jobs exceeding the HTTP dispatch deadline | **Cloud Run Jobs / Batch / Workflows** | Runs long tasks and tracks completion separately |

Both Cloud Tasks and Pub/Sub can redeliver messages. **Cloud Tasks provides no ordering guarantee**: task insertion order is preserved on a best-effort basis, while retries, scheduling, and concurrency can cause a later task to finish before an earlier one. If business logic requires per-order ordering, use **sequence/version checks** or an ordered processing architecture.

**DLQ difference:** Pub/Sub provides dead-letter topics/policies on subscriptions; **Cloud Tasks HTTP queues have no equivalent built-in DLQ**. For work needing investigation after retries are exhausted, the application must store durable job state, emit alerts, and implement replay/quarantine handling. Never claim a task will automatically move to a Pub/Sub DLQ just by setting `maxAttempts`.

## 3. Key Concepts and Limits

An HTTP task can be described as follows:

~~~text
Queue:
projects/commerce-lab/locations/asia-southeast1/queues/receipt-http

Task:
projects/commerce-lab/locations/asia-southeast1/queues/receipt-http/tasks/JOB_HASH

HTTP:
POST https://receipt-worker-...run.app/tasks/receipt
Content-Type: application/json
Authorization: Bearer <OIDC token generated by Cloud Tasks>
Body: {"jobId":"demo-001","orderId":"ord-1001"}

scheduleTime: now or a future timestamp
dispatchDeadline: wait limit for a single HTTP attempt response
~~~

The **commerce-lab** names and worker URL above are illustrative only, not real resources.

| Property | Operational Rule |
|---|---|
| Queue location | **Regional**; explicitly specify project/region on commands |
| Max task size | **1 MiB** including payload and applicable metadata |
| Max schedule time | **30 days** from task creation |
| Max retention | **31 days** from task insertion, including retries |
| HTTP dispatch deadline | Default **10 minutes**; configurable from **15 seconds to 30 minutes** |
| Max HTTP queue rate | **500 task dispatches/second/queue** under current system limits |
| Task name deduplication | Tracks deleted/executed task names for **up to 24 hours** on API-created queues |
| Queue re-creation | A deleted queue name may require **3 days** before reuse |
| HTTP success | Any **2xx** status |
| HTTP failure | Non-2xx or no response before deadline |
| Execution semantics | Aims for single execution, though **duplicate execution can still occur** |

Limits reflect current Cloud Tasks documentation; always check project/region quotas and [Quotas and limits](https://docs.cloud.google.com/tasks/docs/quotas) before deployment.

### 3.1. Do Not Confuse Three Timeouts/Timers

- **scheduleTime:** earliest time a task becomes eligible for dispatch; **not a millisecond-exact execution promise**.
- **dispatchDeadline:** how long Cloud Tasks waits for an HTTP attempt before considering it expired. The worker may still finish side effects after the client stops waiting: idempotency is mandatory.
- **maxRetryDuration/maxAttempts:** task retry limits. Under Cloud Tasks' model, a task is dropped for retry limits only when **both applicable limit conditions are reached**, or upon retention expiry; do not assume hitting `maxAttempts` alone always deletes a task immediately.

**Distinct from Cloud Run timeout:** Cloud Run's request timeout and Cloud Tasks' `dispatchDeadline` are separate settings. If a worker can take 90 seconds, both must permit sufficient time, and downstream calls still need timeouts.

### 3.2. Task Names Do Not Replace Database Uniqueness

When a producer specifies a fixed **task ID**, Cloud Tasks may return **ALREADY_EXISTS** if the same ID is pending or was recently processed/deleted. This reduces duplicates **at the queue entry gate**, not as a permanent idempotency lock.

For task IDs, use hashed or evenly distributed identifiers, avoiding long sequential IDs that increase lookup latency. Keep **jobId** stable per business requirement, while the task ID can be a hash of `jobId` and operation/version.

## 4. Hands-on Scenario: Preparing Order Receipts

We will create two components:

- **Cloud Run worker `receipt-worker-lab`**, private, accepting **POST /tasks/receipt** with a small JSON body.
- **Cloud Tasks queue `receipt-http-lab`**, capped at 2 dispatches/s and at most 3 concurrent attempts.

The producer uses **`gcloud tasks create-http-task`** or the Java Cloud Tasks client. The lab worker **only logs simulated output** to prove task delivery and HTTP acknowledgment; production must replace this with a **durable, deduplicated** business operation before returning 2xx.

| Parameter | Example Value | Meaning |
|---|---|---|
| PROJECT_ID | YOUR_PROJECT_ID | Authorized project |
| LOCATION | asia-southeast1 | Region supporting Cloud Tasks and Cloud Run |
| QUEUE | receipt-http-lab | HTTP queue |
| SERVICE | receipt-worker-lab | Private Cloud Run worker |
| DISPATCH_SA | receipt-dispatcher@PROJECT_ID.iam.gserviceaccount.com | Identity used to mint OIDC tokens calling the worker |
| RUNTIME_SA | receipt-runtime@PROJECT_ID.iam.gserviceaccount.com | Identity used by worker code calling Google APIs |
| POST endpoint | SERVICE_URL/tasks/receipt | Target URL, no public invocation |
| Payload | {"jobId":"demo-001","orderId":"ord-1001"} | Contains no sensitive data |

**Safe sequence:** verify project/context → create service accounts and IAM → deploy private worker → create queue with rate/retry policy → enqueue task → inspect logs/metrics → clean up lab. Never create a queue in a production project just to run this lesson.

## 5. Preflight: APIs, Project, Identities, and Networking

### 5.1. Verify the Project Before Making Any Changes

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
LOCATION="asia-southeast1"
QUEUE="receipt-http-lab"
SERVICE="receipt-worker-lab"

gcloud auth list
gcloud config list
gcloud projects describe "$PROJECT_ID"

# READ-ONLY — list queues/Cloud Run services in the region.
gcloud tasks queues list --location="$LOCATION" --project="$PROJECT_ID"
gcloud run services list --region="$LOCATION" --project="$PROJECT_ID"

# READ-ONLY — check enabled APIs.
gcloud services list --enabled --project="$PROJECT_ID"
~~~

Confirm the region supports **Cloud Tasks** and **Cloud Run**; queues are regional resources, so do not guess nearby regions when submitting tasks. When working across multiple projects, always pass **--project** and **--location/--region** on mutating commands to avoid modifying other resources.

### 5.2. Enable APIs If Approved

~~~bash
# MUTATES PROJECT, may incur charges upon usage.
gcloud services enable \
  cloudtasks.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  --project="$PROJECT_ID"
~~~

Cloud Run source deployment uses **Cloud Build/buildpacks** and stores images in Artifact Registry. The build identity needs **Cloud Run Builder** or matching source build permissions; the deployer may need **roles/run.sourceDeveloper**, **roles/serviceusage.serviceUsageConsumer**, and **roles/iam.serviceAccountUser** on the runtime service account.

### 5.3. Four Independent Identities

| Identity | Least Privilege | Stage |
|---|---|---|
| **Producer identity** | **roles/cloudtasks.enqueuer** on queue; **iam.serviceAccounts.actAs** on DISPATCH_SA when setting OIDC | Task creation |
| **Dispatch identity (DISPATCH_SA)** | **roles/run.invoker** on the exact Cloud Run service | Represents Cloud Tasks outbound requests |
| **Cloud Tasks service agent** | **roles/cloudtasks.serviceAgent** managed by Google Cloud | Token minting and dispatch |
| **Runtime identity (RUNTIME_SA)** | Permissions on databases/Storage/Google APIs actually needed by worker | Business processing |

The service account used to generate OIDC tokens **must belong to the same project as the queue**. The Cloud Tasks service agent mints tokens on behalf of DISPATCH_SA. Never grant **roles/cloudtasks.serviceAgent** to users or runtime accounts. Token minting errors require checking the service agent and IAM policies, not blindly granting Owner.

### 5.4. Create Dedicated Service Accounts for the Lab

~~~bash
# MUTATES IAM — only if absent and approved by owner.
gcloud iam service-accounts create receipt-dispatcher \
  --project="$PROJECT_ID" \
  --display-name="Cloud Tasks HTTP dispatch identity"

gcloud iam service-accounts create receipt-runtime \
  --project="$PROJECT_ID" \
  --display-name="Cloud Run receipt worker identity"

DISPATCH_SA="receipt-dispatcher@$PROJECT_ID.iam.gserviceaccount.com"
RUNTIME_SA="receipt-runtime@$PROJECT_ID.iam.gserviceaccount.com"

gcloud iam service-accounts describe "$DISPATCH_SA" --project="$PROJECT_ID"
gcloud iam service-accounts describe "$RUNTIME_SA" --project="$PROJECT_ID"
~~~

The deployer needs **Service Account User** on the runtime SA; the enqueuing principal needs **Service Account User** on the dispatch SA when attaching OIDC. Grant permissions per service account rather than granting project-wide Editor/Owner for testing.

### 5.5. Networking and Endpoint Protection

For Cloud Run, use the **default `run.app` URL** as the HTTP target. This lesson uses a private Cloud Run service: requests carrying an OIDC token are verified by **Cloud Run IAM** before reaching the Java controller.

- Never enable **--allow-unauthenticated** just to work around a 403 error.
- If the service sets **internal ingress** or restrictive network policies, verify that the Cloud Tasks → Cloud Run path is actually supported.
- IAM does not replace business authorization: the handler must still validate order/job ownership per architecture.
- Avoid a shared account holding permissions across all queues, databases, and Cloud Run services.

## 6. Java/Spring Boot Worker on Cloud Run

The lab worker only **validates JSON and logs the job ID**, then returns **204**. This practices HTTP delivery; it does not send emails or persist business outcomes yet. Section 11 covers idempotency requirements before production use.

Create a separate **`receipt-worker-lab/`** directory in your learning workspace:

~~~text
receipt-worker-lab/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── lab/
        │       └── ReceiptWorkerApplication.java
        └── resources/
            └── application.properties
~~~

### 6.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>
  <groupId>lab.example</groupId>
  <artifactId>receipt-worker</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>21</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

The Spring Boot version is pinned for the lab, not a permanent production recommendation. Check JDK compatibility, updates, and dependency vulnerabilities before production rollout.

### 6.2. ReceiptWorkerApplication.java

~~~java
package lab;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ReceiptWorkerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReceiptWorkerApplication.class, args);
    }

    @RestController
    public static class ReceiptHandler {
        private static final Logger LOG =
                LoggerFactory.getLogger(ReceiptHandler.class);
        private final ObjectMapper json;

        public ReceiptHandler(ObjectMapper json) {
            this.json = json;
        }

        public record ReceiptJob(String jobId, String orderId) {}

        @PostMapping(path = "/tasks/receipt",
                     consumes = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<Void> process(
                @RequestBody byte[] body,
                @RequestHeader(
                    value = "X-CloudTasks-TaskName", required = false)
                    String taskName,
                @RequestHeader(
                    value = "X-CloudTasks-TaskRetryCount", required = false)
                    String retryCount) {

            if (body.length > 4096) {
                LOG.warn("Permanent reject: payload too large");
                return ResponseEntity.noContent().build();
            }

            ReceiptJob job;
            try {
                job = json.readValue(body, ReceiptJob.class);
            } catch (JsonProcessingException ex) {
                LOG.warn("Permanent reject: invalid JSON");
                return ResponseEntity.noContent().build();
            }

            if (job == null ||
                job.jobId() == null ||
                !job.jobId().matches("[A-Za-z0-9_-]{1,64}") ||
                job.orderId() == null ||
                !job.orderId().matches("[A-Za-z0-9_-]{1,64}")) {
                LOG.warn("Permanent reject: invalid task fields");
                return ResponseEntity.noContent().build();
            }

            // DEMO: does not send email or write to database.
            // Production: return 2xx only after the business outcome is persisted.
            LOG.info("receipt job observed jobId={} task={} retries={}",
                     job.jobId(), taskName, retryCount);
            return ResponseEntity.noContent().build();
        }
    }
}
~~~

**Distinguishing response types:**

- **204 No Content:** Cloud Tasks treats the attempt as successful and deletes the task. In the lab this only means the payload was received/logged, **not that an email was sent**.
- **Permanently invalid input:** the example logs a warning and ACKs to avoid retry loops. Production must **persist a rejected/quarantine state durably before ACKing** if auditing is required.
- **Transient errors:** when replacing the demo with real I/O, throw an exception or return **503** on transient downstream failures so Cloud Tasks retries.
- **`X-CloudTasks-*` headers:** useful for investigation, yet **not independent proof of authentication**; protect requests with Cloud Run IAM/OIDC rather than trusting client-supplied headers.

### 6.3. application.properties

~~~properties
server.port=${PORT:8080}
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=25s
~~~

Cloud Run injects the **`PORT`** environment variable; the setting above uses Spring Boot placeholder syntax to read it with default 8080. Build and test locally:

~~~bash
java -version
mvn -version
mvn -B clean package

# Once built successfully:
PORT=8080 java -jar target/receipt-worker-1.0.0.jar
~~~

In another terminal:

~~~bash
curl -i -X POST "http://127.0.0.1:8080/tasks/receipt" \
  -H "Content-Type: application/json" \
  --data '{"jobId":"demo-001","orderId":"ord-1001"}'
~~~

Expect **204** and logs containing **`jobId=demo-001`**. Local testing does not yet verify Cloud Tasks IAM/OIDC.

## 7. Deploying the Private Cloud Run Worker

Inside **`receipt-worker-lab/`**, once context and permissions are verified:

~~~bash
# MUTATING: Cloud Build builds the image, Cloud Run deploys the service.
gcloud run deploy "$SERVICE" \
  --source . \
  --project="$PROJECT_ID" \
  --region="$LOCATION" \
  --service-account="$RUNTIME_SA" \
  --no-allow-unauthenticated \
  --timeout=60s \
  --max-instances=3 \
  --concurrency=10

# READ-ONLY — root URL and Ready revision.
SERVICE_URL="$(gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" --region="$LOCATION" \
  --format="value(status.url)")"

printf 'Cloud Run service URL: %s\n' "$SERVICE_URL"

gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" --region="$LOCATION" \
  --format="yaml(status.url,status.latestReadyRevisionName,spec.template)"
~~~

Use the **default `run.app` `SERVICE_URL`** as the OIDC audience. When the task URL is **`SERVICE_URL/tasks/receipt`**, the audience remains **`SERVICE_URL`**, without appending the path. Using custom domains, route redirects, or proxy endpoints requires re-verifying token validation and network policies.

Grant Invoker to the dispatch identity, never to `allUsers`:

~~~bash
# MUTATES IAM — only on the lab service.
gcloud run services add-iam-policy-binding "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$LOCATION" \
  --member="serviceAccount:$DISPATCH_SA" \
  --role="roles/run.invoker"

# READ-ONLY.
gcloud run services get-iam-policy "$SERVICE" \
  --project="$PROJECT_ID" --region="$LOCATION"
~~~

A Ready service only proves the container starts on Cloud Run. It **does not yet prove Cloud Tasks can enqueue, mint OIDC tokens, or dispatch**; those steps must be tested separately.

## 8. Creating an HTTP Queue with Rate Limits and Retries

~~~bash
QUEUE="receipt-http-lab"

# MUTATES CLOUD TASKS — lab project, never use a production queue.
gcloud tasks queues create "$QUEUE" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --max-dispatches-per-second=2 \
  --max-concurrent-dispatches=3 \
  --max-attempts=5 \
  --min-backoff=10s \
  --max-backoff=300s \
  --max-doublings=3 \
  --max-retry-duration=3600s \
  --log-sampling-ratio=1.0

# READ-ONLY — queue state/rate/retry.
gcloud tasks queues describe "$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION" \
  --format=yaml
~~~

If the queue already exists, do not recreate it: use **`queues describe`** and **`queues update`** under change review. Values of 2 dispatches/s and 3 concurrent attempts are for easy lab observation, not production settings. **`log-sampling-ratio=1.0`** increases log volume/cost under high attempt counts, so production usually needs tailored sampling.

### 8.1. Rate and Concurrency Are Different

| Setting | Meaning | Trade-off |
|---|---|---|
| **maxDispatchesPerSecond=2** | Target steady-state dispatch rate | Protects request/s-limited APIs |
| **maxConcurrentDispatches=3** | At most 3 in-flight attempts awaiting completion | Protects slow workers/DBs |
| **maxAttempts=5** | Maximum attempts, including initial attempt | Cuts futile retries |
| **minBackoff=10s** | Initial/minimum retry wait interval | Gives downstream time to recover |
| **maxBackoff=300s** | Upper bound on exponential delay | Prevents overly sparse retries |
| **maxRetryDuration=3600s** | Retry window measured from first attempt | Prevents unbounded retries |
| **logSamplingRatio=1** | Logs many operations/attempts | Easy debugging, higher cost |

Cloud Tasks uses a **token bucket**; active queues can **burst** briefly above the steady-state rate. Newly created, resumed, or long-idle queues may **ramp up gradually** rather than hitting max rate instantaneously.

When workers return **429/503** or high 5xx rates, Cloud Tasks may throttle dispatches further below config and inspect **`Retry-After`**. Raising rates while the backend is overloaded usually worsens backlogs.

### 8.2. Granting Queue Enqueuer IAM

Replace **`PRODUCER_EMAIL`** with an approved practitioner or the Orders API's actual service account. Never grant project-wide roles when only enqueuing to this queue is needed.

~~~bash
PRODUCER_EMAIL="REPLACE_WITH_AUTHORIZED_USER_EMAIL"

# MUTATES IAM on the exact lab queue.
gcloud tasks queues add-iam-policy-binding "$QUEUE" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --member="user:$PRODUCER_EMAIL" \
  --role="roles/cloudtasks.enqueuer"

# READ-ONLY — verify queue IAM.
gcloud tasks queues get-iam-policy "$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION"
~~~

A principal creating tasks with OIDC also needs **`iam.serviceAccounts.actAs`** on `DISPATCH_SA`. Administrators can grant **`roles/iam.serviceAccountUser`** on that specific SA:

~~~bash
# MUTATES IAM — only when approved.
gcloud iam service-accounts add-iam-policy-binding "$DISPATCH_SA" \
  --project="$PROJECT_ID" \
  --member="user:$PRODUCER_EMAIL" \
  --role="roles/iam.serviceAccountUser"
~~~

In production, **the producer is usually a service account** attached to a Cloud Run/GKE app rather than an interactive user. Replace the `user` principal with `serviceAccount` in queue IAM and the `actAs` binding. Avoid shared long-lived JSON keys when Workload Identity Federation or Google Cloud runtime identities are available.

## 9. Enqueuing and Testing HTTP Tasks with gcloud

### 9.1. Creating an Immediate Task

This example uses HTTP POST, a JSON body without real data, and an OIDC token minted for `DISPATCH_SA`:

~~~bash
TASK_ID="receipt-demo-001"

# MUTATING: creates task; Cloud Tasks will invoke the Cloud Run worker.
gcloud tasks create-http-task "$TASK_ID" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --queue="$QUEUE" \
  --url="$SERVICE_URL/tasks/receipt" \
  --method=POST \
  --header="Content-Type:application/json" \
  --body-content='{"jobId":"demo-001","orderId":"ord-1001"}' \
  --oidc-service-account-email="$DISPATCH_SA" \
  --oidc-token-audience="$SERVICE_URL"
~~~

Upon creation, the API returns the task's resource name. Attempting to recreate **the same `TASK_ID`** may return **ALREADY_EXISTS** while the task is pending or within the deduplication window. To test a fresh task with a new payload, supply a **new task ID and new `jobId`**; never modify queued production tasks.

### 9.2. Reading Logs and Status

~~~bash
# READ-ONLY — list pending tasks.
gcloud tasks list \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --queue="$QUEUE"

# READ-ONLY — worker logs.
gcloud run services logs read "$SERVICE" \
  --project="$PROJECT_ID" --region="$LOCATION" \
  --limit=50

# READ-ONLY — attempt logs when logging is enabled.
gcloud logging read \
  'resource.type="cloud_tasks_queue" AND resource.labels.queue_id="receipt-http-lab"' \
  --project="$PROJECT_ID" --limit=30
~~~

**A task disappearing from the queue list is not proof of a successful business outcome.** It may have been ACKed **2xx**, purged due to retry/retention expiry, or removed administratively. Cross-check worker logs, task attempt logs, durable job status, and metrics. In the lab, the **`receipt job observed`** log proves the worker received the payload, not that an email was sent.

When log sampling is enabled, Cloud Tasks status codes may appear as **canonical gRPC statuses** (e.g., HTTP 429 → `RESOURCE_EXHAUSTED`, 503 → `UNAVAILABLE`) rather than raw HTTP numbers. Interpret metrics and log schemas against current documentation.

### 9.3. Scheduling a Task 5 Minutes Later

On **Google Cloud Shell or Linux with GNU `date`**:

~~~bash
SCHEDULE_TIME="$(date -u -d '+5 minutes' '+%Y-%m-%dT%H:%M:%SZ')"

# MUTATING: future schedule, up to 30 days ahead.
gcloud tasks create-http-task "receipt-demo-later-001" \
  --project="$PROJECT_ID" --location="$LOCATION" --queue="$QUEUE" \
  --url="$SERVICE_URL/tasks/receipt" \
  --method=POST \
  --header="Content-Type:application/json" \
  --body-content='{"jobId":"demo-later-001","orderId":"ord-1002"}' \
  --oidc-service-account-email="$DISPATCH_SA" \
  --oidc-token-audience="$SERVICE_URL" \
  --schedule-time="$SCHEDULE_TIME"
~~~

On Windows PowerShell/macOS, generate an RFC3339 UTC timestamp with the corresponding tool and pass it to **`--schedule-time`**. The task becomes eligible for dispatch at or after the scheduled time; Cloud Tasks does not guarantee exact execution timing when a queue is paused, overloaded, or ramping up.

### 9.4. Inspecting and Adjusting a Queue

~~~bash
# READ-ONLY.
gcloud tasks queues describe "$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION"

# MUTATING — lower rate to protect the worker; requires review.
gcloud tasks queues update "$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION" \
  --max-dispatches-per-second=1 \
  --max-concurrent-dispatches=2
~~~

**Pause** halts dispatches while still allowing enqueues; **resume** restarts queue delivery without guaranteeing FIFO. Use only on lab queues you own:

~~~bash
# MUTATING, lab only:
gcloud tasks queues pause "$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION"

# After maintenance finishes:
gcloud tasks queues resume "$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION"
~~~

If paused for multiple days, backlogs can accumulate and tasks can hit retention limits. When resuming, raise rates gradually instead of flooding a weak backend. **Purge** irreversibly deletes every task in a queue; never use it casually on shared queues.

## 10. Java Producer Creating HTTP Tasks via the Cloud Tasks SDK

In a Java Orders API, the producer can call **`CloudTasksClient`** to enqueue tasks without shelling out to `gcloud`. The SDK uses **Application Default Credentials** from the runtime identity; never embed JSON keys. The example below can live in a **separate Java project**, or add the dependency to an existing Spring Boot `pom.xml`.

### 10.1. Maven Dependency

Add the Google Cloud Libraries BOM to **`dependencyManagement`**, and **`google-cloud-tasks`** to **`dependencies`**. If your project already imports the BOM, only add the dependency without duplicating the BOM:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.google.cloud</groupId>
      <artifactId>libraries-bom</artifactId>
      <version>26.90.0</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-tasks</artifactId>
  </dependency>
</dependencies>
~~~

The BOM version reflects an example Google Cloud Java library release at the time of writing, not a permanently mandated version. Production projects should coordinate the BOM with existing dependency management and test binary compatibility. **Do not blindly paste a second `<dependencies>` block if `pom.xml` already has one**; merge properly within Maven's structure.

### 10.2. ReceiptEnqueuer.java

~~~java
package lab;

import com.google.cloud.tasks.v2.CloudTasksClient;
import com.google.cloud.tasks.v2.HttpMethod;
import com.google.cloud.tasks.v2.HttpRequest;
import com.google.cloud.tasks.v2.OidcToken;
import com.google.cloud.tasks.v2.QueueName;
import com.google.cloud.tasks.v2.Task;
import com.google.cloud.tasks.v2.TaskName;
import com.google.protobuf.ByteString;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Map;

public final class ReceiptEnqueuer {
    public static void main(String[] args) throws Exception {
        String project = required("PROJECT_ID");
        String location = required("LOCATION");
        String queueId = required("QUEUE");
        String serviceUrl = required("SERVICE_URL");
        String dispatchSa = required("DISPATCH_SA");

        // In production, obtain job ID from the database/business request.
        String jobId = args.length > 0 ? args[0] : "demo-002";
        String orderId = args.length > 1 ? args[1] : "ord-1002";
        if (!jobId.matches("[A-Za-z0-9_-]{1,64}") ||
            !orderId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid job or order ID");
        }

        // Task ID evenly distributed via SHA-256; jobId is the durable business key.
        byte[] hash = MessageDigest.getInstance("SHA-256")
                .digest(("receipt:" + jobId)
                .getBytes(StandardCharsets.UTF_8));
        String taskId = "receipt-" + HexFormat.of().formatHex(hash);
        String taskName = TaskName.of(
                project, location, queueId, taskId).toString();

        byte[] body = new ObjectMapper()
                .writeValueAsBytes(Map.of(
                    "jobId", jobId,
                    "orderId", orderId
                ));

        String cleanServiceUrl = serviceUrl.replaceAll("/+$", "");
        HttpRequest http = HttpRequest.newBuilder()
                .setUrl(cleanServiceUrl + "/tasks/receipt")
                .setHttpMethod(HttpMethod.POST)
                .putHeaders("Content-Type", "application/json")
                .setBody(ByteString.copyFrom(body))
                .setOidcToken(OidcToken.newBuilder()
                        .setServiceAccountEmail(dispatchSa)
                        .setAudience(cleanServiceUrl)
                        .build())
                .build();

        Task task = Task.newBuilder()
                .setName(taskName)
                .setHttpRequest(http)
                .build();

        try (CloudTasksClient client = CloudTasksClient.create()) {
            String parent = QueueName.of(
                    project, location, queueId).toString();
            Task created = client.createTask(parent, task);
            System.out.println("Task accepted: " + created.getName());
        }
    }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing env: " + key);
        }
        return value;
    }
}
~~~

Preparation steps:

- Environment variables **`PROJECT_ID`, `LOCATION`, `QUEUE`, `SERVICE_URL`, `DISPATCH_SA`** set accurately for the lab resources.
- Producer principal granted **`roles/cloudtasks.enqueuer`** on the queue and **`iam.serviceAccounts.actAs`** on `DISPATCH_SA`.
- Use attached service account ADC on Cloud Run/GKE; local dev machines can use **`gcloud auth application-default login`** per organizational policy.
- Build the project with Maven and run the class via your IDE or Maven exec plugin. **Never grant Cloud Tasks Administrator** to a producer that only creates tasks.

### 10.3. Task Names and Job Names Must Stay Separate

With **`jobId=demo-002`**, deterministic task IDs formatted as **`receipt-[sha256]`** mean re-enqueuing the same job within the dedup window can return **ALREADY_EXISTS**. This prevents short-term duplicate insertion at queue ingress, yet **does not guarantee the database or email will not be reprocessed after 24 hours**. Business logic still requires a durable idempotency key.

**Architectural note:** if the Orders API writes an order to the database and then enqueues a task, a failure can happen between those two steps: the order commits while the task is never created. When work must never be lost, use a **transactional outbox** or reconciliation mechanism to create tasks from pending state records, rather than assuming two separate services share a transaction.

## 11. Idempotency, Permanent Errors, and the ACK Model

### 11.1. Why Is a Durable Key Required?

Suppose the worker commits to the database at second 40, yet the 204 response fails to reach Cloud Tasks before `dispatchDeadline`. The queue will retry, and a new worker instance could repeat the action.

~~~mermaid
sequenceDiagram
    participant Q as Cloud Tasks
    participant W as Worker A
    participant DB as Durable store
    participant W2 as Worker B
    Q->>W: POST jobId=demo-001
    W->>DB: Commit result for demo-001
    DB-->>W: COMMIT OK
    Note over Q,W: HTTP response lost/deadline exceeded
    Q->>W2: Retry same jobId
    W2->>DB: Atomic create with unique jobId
    DB-->>W2: Already exists
    W2-->>Q: 204 ACK duplicate safely
~~~

For simple results persisted in a database, the right pattern is **atomic create-if-absent**:

~~~text
BEGIN durable transaction
  IF result(jobId) already exists and is COMPLETED:
    COMMIT -> ACK 2xx
  ELSE:
    validate ownership/payload/business constraints
    INSERT result(jobId, outcome) with UNIQUE(jobId)
    COMMIT -> ACK 2xx
END

If database encounters a transient error: do not ACK, return 503 to retry.
If input is permanently invalid: write REJECTED to durable store, then ACK.
~~~

For example, in Firestore, **`document ID = jobId`** with **`DocumentReference.create(data)`** is a create-only atomic operation. In Cloud SQL, use a unique constraint and transaction; a plain Redis cache TTL is rarely sufficient for full business lifetimes. Understand isolation levels, race conditions, and all side effects before choosing an implementation.

### 11.2. What If the Action Is Sending an Email or Charging Payment?

Creating a `COMPLETED` record **before** sending the email can lose emails if the process crashes after commit; sending the email **before** creating the record can send twice on retry. You cannot solve this simply by reordering a single write statement.

Safer approach:

1. Write an **outbox/job record** in the same transaction as the initial business event.
2. Have the worker claim the job via **lease/atomic state transition**.
3. Call downstream with a provider-supported **idempotency key**; store the provider message/transaction ID.
4. Persist the durable completion state and ACK.
5. Implement reconciliation for cases where the provider received the request while the worker lost the outcome.
6. If the provider lacks idempotency support, document the **at-least-once** boundary and design downstream duplicate detection.

**Never promise exactly-once external side effects** solely on the basis of Cloud Tasks, task naming, or a retry flag.

### 11.3. HTTP Cases and Correct Actions

| Scenario | Worker Response | Cloud Tasks Effect | Business Condition |
|---|---|---|---|
| Commit succeeded | **200/204** | ACKs and deletes task | Real outcome persisted |
| Job already processed | **204** | ACKs | Idempotency record exists |
| Permanently invalid input | **2xx** after recording rejected/quarantine | Stops futile payload retries | Audit/notification recorded |
| Transient DB/network error | **503** | Backoff/retry | Never fake an ACK |
| Downstream rate limited | **429** + `Retry-After` if appropriate | Throttling/backoff | Protects upstream |
| Missing/wrong OIDC | **401/403** from Cloud Run | Retries may repeat | Fix IAM/audience |
| Request too slow | Timeout/`DEADLINE_EXCEEDED` | May retry | Bound processing, idempotency |
| Worker crashes after side effect | No response | May retry | Atomic unique key/outbox |

Spring Boot may return 400 for unparseable JSON before the handler executes. Cloud Tasks treats 400 as non-2xx; production needs **durable rejected-state persistence** in an error handler or pre-processor to avoid prolonged retries. Do not blame the queue when permanent vs. transient classification belongs in the application.

### 11.4. No Built-In Dead-Letter Queue

Cloud Tasks **does not automatically route failed tasks to a Pub/Sub DLQ** after `maxAttempts`. Therefore, for critical jobs:

- Create a **job record before/after enqueuing** with `PENDING/PROCESSING/COMPLETED/FAILED` states.
- Tag logs/metrics with `jobId`; monitor queue backlog and errors.
- Define a **retry horizon** shorter than retention so alerts can fire.
- When retries expire, run a reconciler to find uncompleted jobs, record `FAILED` with error details, and decide whether to **re-enqueue with a new task ID** per policy.
- Never infinitely re-enqueue permanently invalid payloads; use manual review/quarantine or data remediation plans.

For multi-subscriber pipelines or native per-subscription DLQs, consider Pub/Sub. For multi-step stateful flows with conditional branches, consider Workflows combined with Cloud Tasks where appropriate.

## 12. Observability, Backlog, and Troubleshooting

### 12.1. Key Operational Signals

| Signal | Source | When to Alert? |
|---|---|---|
| **Queue depth / pending tasks** | Cloud Tasks metrics/console | Backlog grows continuously |
| **Oldest task age / schedule delay** | Cloud Tasks + job timestamps | Delay breaches SLA |
| **Task attempts by response code** | Cloud Monitoring/Cloud Tasks logs | 429, 503, 401/403, or timeouts spike |
| **Dispatch rate/concurrency** | Queue settings + metrics | Worker overloaded or throughput collapsed |
| **Cloud Run 5xx, p95 latency, instance count** | Cloud Run Monitoring/Logging | Processing SLO missed |
| **Business job status** | Database/application telemetry | Jobs remain uncompleted despite empty queue |
| **Job duplicate/rejected counts** | Structured application logs | Duplicates or permanent errors climb |
| **Cloud Billing per SKU** | Cloud Billing | Retry storms and anomalous cost spikes |

In Cloud Monitoring, the **`cloudtasks.googleapis.com/queue/task_attempt_count`** metric supports breaking down attempts by **`response_code`**; status names may follow **canonical gRPC codes**. For instance, HTTP 429 typically maps to `RESOURCE_EXHAUSTED`, and HTTP 503 maps to `UNAVAILABLE`.

Cloud Tasks logging is not necessarily enabled in full by default: log sampling defaults to 0. Production projects should set an appropriate sampling ratio balancing troubleshooting visibility against log cost.

### 12.2. Read-Only Diagnostic Commands

~~~bash
gcloud tasks queues describe "$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION" \
  --format=yaml

gcloud tasks list \
  --project="$PROJECT_ID" --location="$LOCATION" \
  --queue="$QUEUE"

gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" --region="$LOCATION" \
  --format="yaml(status.url,status.latestReadyRevisionName,status.traffic)"

gcloud run services logs read "$SERVICE" \
  --project="$PROJECT_ID" --region="$LOCATION" --limit=100

gcloud logging read \
  'resource.type="cloud_tasks_queue" AND resource.labels.queue_id="receipt-http-lab" AND jsonPayload.attemptResponseLog.status!="OK"' \
  --project="$PROJECT_ID" --limit=50
~~~

Never copy raw task payloads, ID tokens, API keys, or order details into reports or tickets. Each task should carry a **`jobId`**, correlation ID, queue ID, task ID, attempt count, and outcome state while minimizing PII.

### 12.3. Troubleshooting Table

| Symptom | Common Cause | Check / Remediation |
|---|---|---|
| **CreateTask 403** | Producer lacks Enqueuer or `actAs` on `DISPATCH_SA` | Queue IAM, service account IAM |
| **Dispatch 401/403** | Wrong OIDC audience, missing Invoker, service agent unable to mint token | Cloud Run IAM, audience, Cloud Tasks service agent |
| **Task created but does not run** | Future `scheduleTime`, queue `PAUSED`, ramp-up, or task ineligible | Describe queue/task, check `scheduleTime` |
| **HTTP 404** | Wrong `/tasks/receipt` path, deployed to wrong service/region | URL, Cloud Run revision, handler mapping |
| **Repeated HTTP 400** | Bad payload/syntax, worker returns non-2xx | Validate, persist rejected state, ACK if permanent |
| **Rising HTTP 429/503** | Backend/DB overload, quota, or downstream limit | Lower dispatch/concurrency, scale capacity properly |
| **DEADLINE_EXCEEDED** | Handler slower than `dispatchDeadline`/Cloud Run timeout | Measure p95 task duration, reduce work per request |
| **Queue has backlog despite low CPU** | Slow downstream, per-request latency, cold ramp-up, scheduler constraints | Task attempts, Cloud Run concurrency, networking |
| **Duplicate business side effects** | Timeout retry or new task for same job | Persistent idempotency, external API idempotency keys |
| **Task gone yet order unfinished** | Worker ACKed too early or retries/retention exhausted | Job state + logs, reconciler |
| **Errors after resuming queue** | Accumulated backlog causing bottlenecks | Ramp rate slowly, watch 429/503 |
| **Deleting and recreating queue with old name fails** | Queue re-creation waiting period | Choose a new name or avoid delete/recreate |
| **Cloud Run not Ready** | Java build/startup, `PORT`, memory, IAM | Build logs, revision conditions, container logs |

### 12.4. Layered 403 Investigation Flow

~~~mermaid
flowchart TD
    ERR["403 creating/dispatching task"] --> WHEN{"Which stage failed?"}
    WHEN -- "CreateTask" --> ENQ["Check Enqueuer + iam.serviceAccounts.actAs"]
    WHEN -- "Dispatch" --> OIDC["Check DISPATCH_SA + OIDC audience"]
    OIDC --> INV["Cloud Run Invoker on exact service"]
    INV --> AGENT["Cloud Tasks service agent properly configured"]
    AGENT --> NET["Check ingress/routing if IAM is correct"]
    ENQ --> RECHECK["Retry with lab principal/queue"]
    NET --> RECHECK
~~~

Never fix this by granting **`roles/owner`** to all service accounts. When a queue calls **Google APIs on `*.googleapis.com`**, use an **OAuth access token** if required by the API; for **Cloud Run services**, prefer **OIDC ID tokens** with the proper audience.

## 13. Capacity, Reliability, and Cost Design

### 13.1. Calculating Throughput with Headroom

Suppose a partner tolerates at most **20 requests/second** and each request averages **0.5 seconds**. Minimum steady-state concurrency per Little's Law is:

\[
L \approx \lambda \times W
= 20\ \mathrm{requests/s} \times 0.5\ \mathrm{s}
= 10\ \mathrm{in\ flight}
\]

However, do not immediately set the queue right at 20/10 without accounting for spikes and SLOs. A test configuration might start at **15 dispatches/s, 8 concurrent attempts**, then tune after load testing based on p95/timeouts, partner rate limits, Cloud Run instance counts, and DB connections.

**Do not confuse concurrency layers:** queue `maxConcurrentDispatches` caps the entire queue; Cloud Run **`--concurrency`** caps concurrent requests **per instance**; `max-instances` caps worker horizontal scale but is not a blanket cost cap. Cloud SQL connection pools, partners, or NAT may impose additional bottlenecks.

### 13.2. Estimating Backlog Drain Time

If a queue holds **6,000 tasks**, the producer stops adding new ones, and the worker sustains **10 successful tasks/s**, the theoretical minimum drain time is:

\[
T = 6000/10 = 600\ \mathrm{s} = 10\ \mathrm{minutes}
\]

In practice, retries, rate ramp-up, bursts, request latency, and downstream rejections occur; measure **successful tasks/s** rather than treating `maxDispatchesPerSecond` as a guaranteed completion rate.

### 13.3. Cost Categories and Resource Risks

| Cost Category | When Incurred | How to Control |
|---|---|---|
| **Cloud Tasks** | Operations/task requests per pricing/quotas | Avoid overly granular tasks and retry storms |
| **Cloud Run** | Requests/compute/instances per configuration | Right-size CPU/RAM/concurrency, min/max instances |
| **Cloud Build + Artifact Registry** | Source builds, image storage | Manage build frequency and artifact retention |
| **Cloud Logging/Monitoring** | Log ingestion, metrics/retention | Appropriate sampling, avoid logging PII |
| **Databases/third-party APIs** | State writes, email/webhook/quotas | Sensible batching, idempotency, rate control |
| **Network egress** | Calling cross-region or Internet endpoints | Co-locate regions/topology, monitor egress SKUs |

Tasks retrying repeatedly can make **HTTP attempts vastly outnumber successful jobs**. When evaluating efficiency, measure **cost per successfully completed job**, not just cost per enqueue.

### 13.4. Controlled Queue Change Runbook

1. Capture baseline: queue depth, oldest job age, dispatch rate, 429/503s, Cloud Run p95, and DB metrics.
2. Pick **one** change: `maxDispatchesPerSecond`, `maxConcurrentDispatches`, or worker capacity.
3. Review target throughput, quotas, IAM, and partner risks.
4. Test in lab/staging, monitoring backlog and request failures.
5. Roll out gradually in production if approved; avoid rapid pause/resume cycles that disrupt ramp-up.
6. If 429/503s climb, lower the rate or resolve downstream bottlenecks; never raise rates blindly.
7. Track configuration in IaC/GitOps or change records; avoid mixing **`queue.yaml`** and **Cloud Tasks API** management on the same queue.
8. Verify improvement via successful throughput, latency, and Cloud Billing after the reporting lag.

## 14. Case Study: Order Confirmation Webhook

**Hypothetical scenario:** a Java Orders API receives 300 orders/minute during peak hours. The shipping partner only accepts **2 webhook requests/second** and occasionally returns HTTP 429. Business requirements: never send the same order status twice, retry on partner errors, and expose job status for customer support lookup.

### 14.1. Design

~~~mermaid
flowchart LR
    USER["Order API"] --> DB["Orders DB + outbox"]
    DB --> P["Outbox publisher\nCloud Tasks Enqueuer"]
    P --> Q["HTTP queue\n2 dispatch/s, 3 concurrent"]
    Q --> W["Cloud Run webhook worker"]
    W --> EXT["Carrier HTTPS API"]
    W --> STATE["Delivery job state\nidempotency + audit"]
    MON["Monitoring + alert"] -. "Backlog, 429, 503" .-> Q
~~~

**Decisions:**

- The Orders transaction writes an **outbox record**; the dispatcher creates a task with a durable **`jobId`**.
- The private Cloud Run target uses the OIDC dispatch identity; the runtime account holds only the permissions needed for outbox/secrets/downstream.
- The worker uses `jobId` to prevent duplicate sends and passes an **external idempotency key** if supported by the carrier API.
- 429/503 responses are retried with backoff while honoring `Retry-After`; permanent failures persist state, route to manual review, and ACK per policy.
- Dashboards track uncompleted jobs by age, not only queue depth.

### 14.2. Incident

The partner returns 429 continuously, and the queue climbs from 100 to 5,000 tasks. The dev team thinks "raising the rate to 10/s will clear the backlog faster."

**Analysis:** this produces the exact opposite effect. The carrier is already asking to shed load; Cloud Tasks may also engage congestion backoff. Identify the root cause of 429s (quotas, tokens, per-customer limits), keep the rate <= actual capacity, separate queues for partners with different capacities, and adjust SLOs/wait times before accepting more work.

### 14.3. Acceptance Criteria

- Producer persists task/job state without losing work on mid-step crashes.
- No double charges or duplicate sends when retrying a `jobId`.
- HTTP 429/503 errors are handled with backoff and alerting.
- Oldest job age stays within agreed thresholds.
- Cloud Run is private with proper OIDC identity/audience.
- A plan exists to pause/replay work aligned with owners, retention, and support processes.
- Cloud Tasks + Cloud Run + network costs are measured per successful job.

## 15. Exercises and Guided Answers

### 15.1. Exercise A — Distinguishing Cloud Tasks and Pub/Sub

Choose the tool for each requirement:

| Requirement | Guided Answer |
|---|---|
| Call a specific webhook after 5 minutes at 3 req/s | **Cloud Tasks** |
| Broadcast `payment.created` event to 5 microservices | **Pub/Sub** |
| Trigger when a GCS object is finalized | **Eventarc** |
| Orchestrate KYC verification → await callback → update profile | **Workflows** |
| Run a 4-hour video batch | **Cloud Run Jobs/Batch** |
| Ensure an API is not called with excessive concurrency | **Cloud Tasks `maxConcurrentDispatches`** |

Explain why requirements involving a **specific target endpoint**, scheduling, and rate control suit Cloud Tasks better than Pub/Sub, whereas fan-out, ordering keys, and built-in per-subscription DLQs are strengths of Pub/Sub's subscription model.

### 15.2. Exercise B — Reading Queue Configuration

~~~yaml
rateLimits:
  maxDispatchesPerSecond: 5
  maxConcurrentDispatches: 10
retryConfig:
  maxAttempts: 7
  minBackoff: 5s
  maxBackoff: 120s
  maxDoublings: 3
  maxRetryDuration: 1800s
~~~

**Questions:**

1. Can 10 HTTP attempts be awaiting responses at the same time?
2. Is it guaranteed to execute exactly 5 requests in **every** 1-second window?
3. A task returns 503 on the first attempt—what does Cloud Tasks do?
4. If `maxAttempts` is reached before `maxRetryDuration`, is the task necessarily deleted immediately?
5. Does the queue guarantee strict FIFO insertion-order processing?

**Answers:** (1) Yes, if tasks and capacity are available. (2) No, token buckets allow bursts and ramp-up. (3) Backoff/retry per policy, potentially with congestion throttling. (4) No, evaluate both limits and retention logic. (5) No, best-effort ordering only.

### 15.3. Exercise C — Idempotency

Suppose the same **`jobId=receipt-123`** is dispatched by Cloud Tasks three times because two prior attempts timed out:

- The worker sends the email three times before writing `COMPLETED` to the database. Is this safe?
- If the producer only relies on a hashed task name, what happens if the job is recreated after 25 hours?
- If the business action is purely **create-one-document** keyed by `jobId` in Firestore, which operation should be used?
- If the downstream email provider lacks idempotency keys, what must be added?

**Answers:** sending three emails is unsafe; task name deduplication provides no guarantee past its retention window; use **atomic create-if-absent** for the outcome document; emails need an outbox/reconciliation, auditing, and duplicate-detection mechanisms rather than claiming exactly-once.

### 15.4. Exercise D — Capacity Calculation

A queue is configured at **10 dispatches/s** and **`maxConcurrentDispatches=4`**. The worker takes an average of **1 second/attempt** to respond. What is the approximate maximum successful throughput assuming zero errors, independent requests, and no other bottlenecks?

\[
\min(10,\ 4 / 1\ \mathrm{s}) = 4\ \mathrm{tasks/s}
\]

**Follow-up:** if processing time increases to **2 seconds**, throughput drops to roughly **2 tasks/s**. Raising `maxDispatchesPerSecond` will not overcome `maxConcurrentDispatches` or worker latency limits.

### 15.5. Exercise E — Controlled Testing

In an authorized lab project:

1. Deploy the private worker and verify `allUsers` does not hold Invoker.
2. Enqueue a valid task; observe the 204 response and `jobId` log.
3. Enqueue another task scheduled 5 minutes ahead; inspect `scheduleTime`.
4. Attempt to recreate the same task ID and record **`ALREADY_EXISTS`** if returned.
5. In an isolated lab test, try creating a task with `DISPATCH_SA` lacking Invoker; observe the 401/403 dispatch failure, then restore proper permissions.
6. Test a mock endpoint returning 503 in a controlled environment; observe retries/backoff and Cloud Tasks logs.
7. Pause and resume the queue; record effects on queued tasks and ramp-up behavior.
8. Record metrics and incurred charges, and clean up resources you own.

Only alter IAM or inject 503 errors **in a lab**; never intentionally break production queues or webhooks.

### 15.6. Acceptance Report Template

~~~text
PROJECT_ID / LOCATION / OWNER:
QUEUE_NAME / STATE / RATE_LIMIT / CONCURRENCY:
RETRY_CONFIG / DISPATCH_DEADLINE:
CLOUD_RUN_SERVICE / URL / REVISION:
PRODUCER_PRINCIPAL / DISPATCH_SA / RUNTIME_SA:
ENQUEUER / ACT_AS / INVOKER / SERVICE_AGENT:
TASK_ID / JOB_ID / SCHEDULE_TIME:
HTTP_STATUS / WORKER_LOG / RETRY_COUNT:
BUSINESS_OUTCOME_PERSISTED?:
DUPLICATE_REPLAY_RESULT:
QUEUE_BACKLOG / OLDEST_TASK_AGE:
429 / 503 / DEADLINE_EXCEEDED:
COST_AND_LOG_SAMPLING:
CLEANUP_RESULT / OPEN_ISSUES:
~~~

Mark **PASS** only after real verification. When the lab only logs simulated work, **`BUSINESS_OUTCOME_PERSISTED`** must be marked **NO/NOT APPLICABLE**—never mark a real receipt as COMPLETED.

## 16. Safe Lab Resource Cleanup

### 16.1. Inventory Before Deleting

~~~bash
# READ-ONLY — verify project and queue.
gcloud config list project

gcloud tasks queues describe "$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION"

gcloud tasks list \
  --project="$PROJECT_ID" --location="$LOCATION" --queue="$QUEUE"

gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" --region="$LOCATION"
~~~

**Never delete a queue containing unprocessed business jobs.** Successfully ACKed tasks normally leave the queue; for auditable jobs, outcomes must reside in a durable store per Section 11.

### 16.2. Pause Dispatching Before Considering Deletion

~~~bash
# MUTATING — only when the lab queue is fully owned by you.
gcloud tasks queues pause "$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION"

# READ-ONLY — inspect state and pending tasks.
gcloud tasks queues describe "$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION"
~~~

After confirming no work remains or jobs are saved/reconciled, an administrator may delete **the exact lab queue**:

~~~bash
# DELETE RESOURCE — irreversible, only after owner approval.
gcloud tasks queues delete "$QUEUE" \
  --project="$PROJECT_ID" --location="$LOCATION"
~~~

**Consequences:** all remaining tasks in the queue are lost; recreating a queue with the same name may be blocked for **3 days**. If the goal is merely temporary suspension, use **pause**; to tune rates, use **update**. **Purge** is likewise irreversible and is not a default cleanup step.

### 16.3. Deleting the Cloud Run Worker and Revoking IAM

~~~bash
# DELETE RESOURCE — only if the service was genuinely created for the lab.
gcloud run services delete "$SERVICE" \
  --project="$PROJECT_ID" --region="$LOCATION"
~~~

Finally, review IAM bindings added on the queue/service and the two service accounts **`receipt-dispatcher`**, **`receipt-runtime`**; revoke/delete them only when no workloads rely on them. **Never delete the Cloud Tasks service agent**, Cloud Build service account, or shared Artifact Registry repository. Deleting a Cloud Run service does not automatically clean up Cloud Build logs, Artifact Registry images, or external resources; verify Cloud Billing after reporting delay.

## 17. Official Documentation and Checklist

- [Cloud Tasks overview](https://docs.cloud.google.com/tasks/docs/dual-overview)
- [Choose Cloud Tasks or Pub/Sub](https://docs.cloud.google.com/tasks/docs/comp-pub-sub)
- [Quickstart: Add a task to an HTTP queue](https://docs.cloud.google.com/tasks/docs/add-task-queue)
- [Create Cloud Tasks queues](https://docs.cloud.google.com/tasks/docs/creating-queues)
- [Create HTTP target tasks programmatically](https://docs.cloud.google.com/tasks/docs/creating-http-target-tasks)
- [Use Cloud Tasks with authenticated HTTP targets](https://docs.cloud.google.com/tasks/docs/authentication)
- [Configure queue rate limits and retries](https://docs.cloud.google.com/tasks/docs/configuring-queues)
- [Set retry parameters for a task](https://docs.cloud.google.com/tasks/docs/configure-retry-task)
- [Manage queues and tasks](https://docs.cloud.google.com/tasks/docs/manage-queues-and-tasks)
- [Cloud Tasks quotas and limits](https://docs.cloud.google.com/tasks/docs/quotas)
- [Common pitfalls](https://docs.cloud.google.com/tasks/docs/common-pitfalls)
- [Manage Cloud Tasks scaling risks](https://docs.cloud.google.com/tasks/docs/manage-cloud-task-scaling)
- [Cloud Tasks IAM roles](https://docs.cloud.google.com/iam/docs/roles-permissions/cloudtasks)
- [Java Cloud Tasks client library](https://docs.cloud.google.com/java/docs/reference/google-cloud-tasks/latest/overview)
- [gcloud tasks create-http-task reference](https://docs.cloud.google.com/sdk/gcloud/reference/tasks/create-http-task)
- [Cloud Run deploy from source](https://docs.cloud.google.com/run/docs/deploying-source-code)
- [Cloud Tasks pricing](https://cloud.google.com/tasks/pricing)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)

**Application checklist:** right project/region → separate Producer/Dispatch/Runtime identities → private Cloud Run with valid OIDC audience → appropriate queue rate/concurrency/retry → tasks carry stable `jobId` → handler ACKs only after durable outcome → idempotency/outbox/reconciliation in place → monitor 429/503/backlog/oldest age → appropriate Billing and logging → pause/resume/delete governed by ownership.

**Connection to the `CLOUD_PROVIDERS_GCP` track:** Cloud Tasks adds **throttled and delayed HTTP work dispatch** between applications running on **Cloud Run, GKE, or Compute Engine**. Combine **IAM/OIDC, Cloud Logging/Monitoring, Cloud Billing, Firestore/Cloud SQL, Pub/Sub, and Workflows** intentionally: **Cloud Tasks manages dispatch**, while the application remains responsible for **correct business logic, durable data, and post-retry recovery**.
