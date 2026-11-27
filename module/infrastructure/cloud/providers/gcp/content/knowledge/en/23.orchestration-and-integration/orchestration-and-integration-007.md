# Cloud Scheduler and Scheduled Task Execution

> **Chapter:** Application Orchestration and Integration  
> **Lesson:** Cloud Scheduler and Scheduled Task Execution  
> **Module:** CLOUD_PROVIDERS_GCP

In the **CLOUD_PROVIDERS_GCP** module, learners explore Google Cloud from project management, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage, and databases, while learning to automate releases and monitor reliability and cost. A recurring operational requirement is **running scheduled jobs**: end-of-day reporting, hourly catalog syncs, expired-data cleanup, or nightly Java batches.

**Cloud Scheduler** is a managed cron service: it **sends a request at the configured schedule**, while the target is responsible for **executing the work**. Targets can be an **HTTP/S endpoint**, a **Pub/Sub topic**, or an **App Engine HTTP application**. To run multi-step Java batches, combine Scheduler with **Cloud Run Jobs, Workflows, or a subscriber**. The service does not provision CPU/RAM to execute Java code itself or replace workflow engines.

Most importantly: Cloud Scheduler has **at-least-once delivery**. When a request times out or the response is lost, the same scheduled interval can be delivered multiple times. Therefore, tasks affecting money, inventory, or data must be **idempotent** — re-running must not produce unintended side effects. Examples and commands in this lesson use hypothetical resources; run them only in an approved sandbox as they can create services, alter IAM, and incur charges.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **Cloud Scheduler** (timing/triggering) from **Cloud Run services**, **Cloud Run Jobs**, **Pub/Sub**, **Cloud Tasks**, and **Workflows** (execution or orchestration).
2. Write **5-field unix-cron** schedules and use IANA timezones, avoiding daylight saving time (DST) bugs.
3. Choose **HTTP**, **Pub/Sub**, or **App Engine** targets matching the architecture.
4. Configure an **OIDC service account** for Scheduler to call a **private Cloud Run service**, and use **OAuth** for Google APIs `*.googleapis.com`.
5. Configure HTTP **attempt deadlines**, retry counts, and backoff; understand limits and effects on subsequent schedules.
6. Use **job name + schedule time** as an idempotency key, enforced via database transactions/unique constraints in Java.
7. Create, inspect, trigger, pause/resume, update, and delete jobs with `gcloud`.
8. Integrate Scheduler with **Pub/Sub**, **Cloud Run Jobs**, or **Workflows** for long or complex tasks.
9. Monitor failures, latency, skipped executions, and costs; write safe runbooks.
10. Complete exercises on schedule design, duplicate handling, and service selection.

## 2. Operating Model: The Trigger Is Not the Worker

~~~mermaid
flowchart LR
    S["Cloud Scheduler<br/>cron + timezone + retry"]
    H["HTTP target<br/>Cloud Run Java service"]
    P["Pub/Sub topic"]
    Q["Java subscriber<br/>GKE/Compute Engine"]
    J["Cloud Run Jobs API<br/>Java batch execution"]
    W["Workflows API<br/>multi-step"]
    DB["Cloud SQL / Cloud Storage"]
    S -->|"OIDC HTTP"| H
    S -->|"Publish"| P
    P --> Q
    S -->|"OAuth HTTP"| J
    S -->|"OAuth HTTP"| W
    H --> DB
    Q --> DB
    J --> DB
    W --> H
~~~

| Component | Role | When to Choose |
|---|---|---|
| **Cloud Scheduler** | Sends events/requests hourly, daily, or on a cron schedule | Recurring jobs with fixed schedules |
| **Cloud Run service** | Receives HTTPS requests, processes within request limits | Fast Java APIs or triggering durable work |
| **Cloud Run Job** | Runs a container to completion; no HTTP listener needed | Java batches, ETL, bulk or long-duration processing |
| **Pub/Sub** | Buffers and distributes messages to consumers | Decouples schedule from processing speed; async load smoothing |
| **Workflows** | Calls services sequentially/in parallel, retries, branches, handles errors | Multi-step/multi-service integration flows |
| **Cloud Tasks** | HTTP task queue with per-task execution times | Work happening **once in the future**, not recurring cron |

**Never assume Scheduler guarantees task completion.** With a Pub/Sub target, Scheduler succeeds upon **publishing to the topic**, without waiting for the Java consumer to commit to a database. With the Cloud Run Jobs API, an HTTP success response usually only means **an execution was requested/initiated**, not that the batch finished running.

## 3. Cron Schedules and Timezones

### 3.1. Five-Field Unix-Cron

~~~text
┌──────── minute        (0–59)
│ ┌────── hour          (0–23)
│ │ ┌──── day of month  (1–31)
│ │ │ ┌── month         (1–12)
│ │ │ │ ┌ day of week   (0–7, SUN=0/7)
│ │ │ │ │
0  18  *  *  *
~~~

Examples:

| Expression | Meaning |
|---|---|
| `*/5 * * * *` | Every 5 minutes |
| `0 * * * *` | Top of every hour |
| `0 18 * * *` | Daily at 18:00 in the configured timezone |
| `30 8 * * 1-5` | Monday–Friday at 08:30 |
| `0 2 1 * *` | 1st of every month at 02:00 |
| `0 6 * * 0` | Sunday at 06:00 |

**Read schedules in the job's timezone**, not your laptop's or cluster's timezone. `0 18 * * *` with `Asia/Ho_Chi_Minh` runs at 18:00 Vietnam time; with `Etc/UTC` it runs at 18:00 UTC. Never infer the schedule from `--location`: **the region storing the Scheduler job does not determine the timezone**.

### 3.2. DST and Schedule Precision

- Cloud Scheduler defaults to **UTC** when no timezone is specified.
- Timezones support **IANA tz database** names such as `Asia/Ho_Chi_Minh`, `America/Los_Angeles`, and `Etc/UTC`.
- In regions observing **daylight saving time**, local times can **not exist** or **occur twice**, making wall-clock schedules uneven.
- If you need a steady cadence or financial processing, **prefer UTC**; if business rules depend on local time, store the timezone explicitly and test DST transitions.

Cloud Scheduler also supports human-readable **groc** expressions such as `every 5 minutes` or `first sunday of month 04:00`. However, **`X-CloudScheduler-ScheduleTime` is not guaranteed to be sent for groc**, so if you plan to use that header for deduplication, **choose unix-cron**.

### 3.3. Recurring Schedules Are Not One-Time Runs

| Requirement | Appropriate Solution |
|---|---|
| Aggregate reports every night at 18:00 | Scheduler cron |
| Emit a cache refresh signal every 15 minutes | Scheduler → Pub/Sub |
| Run once tomorrow at 14:30 | Cloud Tasks with `scheduleTime` or a suitable one-shot solution |
| Users create millions of individual appointment times | Cloud Tasks/queue; never create one cron job per event |
| Run 4 sequential APIs after market close | Scheduler → Workflows |
| 2-hour Java batch | Scheduler → Cloud Run Job/Workflows; **never** hold an HTTP request for 2 hours |

**Operational note:** when the Cloud Scheduler API is disabled and re-enabled, missed intervals during the disabled period may fire **immediately upon re-enabling** instead of waiting for future schedules. Never disable the API as a "pause job" mechanism, and do not assume no catch-up occurs.

## 4. Choosing a Target: HTTP, Pub/Sub, or App Engine?

| Target | What Scheduler Sends | When to Use | Risks to Handle |
|---|---|---|---|
| **HTTP/S** | HTTP method, headers, body, optional OIDC/OAuth token | Cloud Run Java services, Workflows/Cloud Run Jobs APIs | Auth, timeouts, status codes, and idempotency |
| **Pub/Sub** | Message to a topic | Async processing with multiple subscribers | Scheduler success **does not** prove consumer completion; needs Pub/Sub retry/DLQ |
| **App Engine HTTP** | HTTP to an App Engine app in the same project | Systems already running on App Engine | Region, routing, scaling, and target permission constraints |

**HTTP targets** are this lesson's primary example. For Cloud Run services, the endpoint must have an **HTTPS address reachable by Scheduler**; it can still remain **private via IAM**. Do not equate "reachable URL" with "allowing unauthenticated callers". For internal-only ingress setups, verify Cloud Run/Cloud Scheduler documentation and project/perimeter placement rather than assuming all HTTPS URLs are reachable.

**App Engine targets** require an App Engine app in the project and the job in that app's location. If you do not use App Engine, **you do not need to create an App Engine application** just to use Cloud Scheduler.

## 5. Authentication and IAM for HTTP Targets

### 5.1. Three Separate Identities

~~~mermaid
flowchart LR
    Deployer["Developer/CI<br/>creates Scheduler job"]
    JobSA["scheduler-caller SA<br/>OIDC or OAuth"]
    Agent["Cloud Scheduler service agent<br/>Google-managed"]
    Scheduler["Cloud Scheduler job"]
    Run["Cloud Run Java<br/>private target"]
    Runtime["Cloud Run runtime SA"]
    DB["Cloud SQL / APIs"]
    Deployer -->|"create job + actAs"| Scheduler
    Agent -. "Mints token on behalf of JobSA" .-> Scheduler
    Scheduler -->|"authenticated request as JobSA"| Run
    JobSA -. "run.invoker on target" .-> Run
    Run -->|"ADC / runtime SA"| DB
    Runtime -. "DB/API permissions" .-> DB
~~~

| Principal | Permission / Role | Reason |
|---|---|---|
| **Scheduler job creator/admin** | `roles/cloudscheduler.admin` or custom role; `iam.serviceAccounts.actAs` on the job's SA | Allowed to create/edit jobs and attach caller identity |
| **Job caller service account** | `roles/run.invoker` on the target Cloud Run service | Scheduler calls private Cloud Run using this identity |
| **Cloud Scheduler service agent** | `roles/cloudscheduler.serviceAgent` on the project, Google-managed | Mints auth tokens and dispatches requests |
| **Cloud Run runtime SA** | Cloud SQL, Storage, Pub/Sub permissions **per business need** | Java code uses ADC when calling APIs |
| **Job operator** | `roles/cloudscheduler.jobRunner` if only triggering existing jobs | Avoids granting full Scheduler admin rights |

**Important:** never use `service-PROJECT_NUMBER@gcp-sa-cloudscheduler.iam.gserviceaccount.com` as the **job caller SA**; that is Google's service agent. For authenticated HTTP targets, the job caller SA must belong to the **same project as the Scheduler job**. Never grant `roles/cloudscheduler.serviceAgent` to a user-managed SA.

Cloud Scheduler IAM for jobs is primarily **project-scoped**; by default you cannot grant permissions on a single Scheduler job alone. To isolate job admins across teams, consider **separating projects**, while scoping target invoke permissions to each **target service**.

### 5.2. OIDC or OAuth?

| Destination | Suitable Token | Example |
|---|---|---|
| **Private Cloud Run service/function** | **OIDC ID token**, matching service audience | `https://...run.app` |
| **Google API endpoint** `*.googleapis.com` | **OAuth 2.0 access token** | `https://run.googleapis.com/v2/...:run` |
| **Workflows Executions REST API** | **OAuth access token** | `https://workflowexecutions.googleapis.com/v1/...` |
| **Third-party API** | Depends on provider auth; if using OIDC, receiver must verify token | External HTTPS endpoint |

For a Cloud Run HTTP endpoint at `https://HOST/internal/close-day`, **the OIDC audience should be the base service URL `https://HOST`** as accepted by Cloud Run, excluding query parameters. If `--oidc-token-audience` is omitted, Scheduler uses **the full target URI** as audience, which can trigger 401/403 if the service validates a different audience.

**Never commit service account JSON keys or access tokens into a scheduler job body or headers.** Scheduler mints short-lived tokens automatically on behalf of the job caller SA. Once a request enters Cloud Run, the Java runtime uses a **separate runtime SA**, not inheriting the caller SA's permissions automatically.

### 5.3. Distinguishing Three Control Layers

- **IAM Invoker:** is the job caller authorized to invoke the Cloud Run service?
- **Ingress / network:** can the request reach Cloud Run ingress under the chosen policy?
- **Business authorization:** does Java permit this action for the given schedule and data scope?

An `X-CloudScheduler-*` header **is not proof of authentication**, because any authorized caller could send identical headers. Protect endpoints with OIDC/IAM before trusting headers to build idempotency keys.

## 6. Practice A — Scheduler Calling a Private Java Cloud Run Service

**Goal:** at 18:00 daily in Vietnam time, Scheduler sends an HTTP POST to `/internal/close-day` on a Java Spring Boot service. The Java sample only logs the schedule interval and returns HTTP 204; durable processing is covered in Section 7.

### 6.1. Preparation

| Property | Illustrative Value |
|---|---|
| Project | `PROJECT_ID` |
| Scheduler location | `asia-southeast1` |
| Cloud Run service | `daily-close-api` in `asia-southeast1` |
| Cloud Run HTTPS URL | `https://SERVICE_HOST` (retrieved from real `gcloud`) |
| Job ID | `daily-close-schedule` |
| Job caller SA | `scheduler-caller@PROJECT_ID.iam.gserviceaccount.com` |
| Cron | `0 18 * * *` |
| Timezone | `Asia/Ho_Chi_Minh` |

Requirements: project with billing, `cloudscheduler.googleapis.com` and Cloud Run APIs enabled; Java service already deployed privately and ready; permissions to create SAs/jobs/IAM approved. If the service does not exist yet, deploy the Java Spring Boot endpoint following your team's workflow **before** creating the job.

Read-only inspection commands:

~~~bash
gcloud auth list
gcloud config get-value project

gcloud run services describe daily-close-api \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --format="value(status.url)"

gcloud scheduler jobs list \
  --project=PROJECT_ID \
  --location=asia-southeast1
~~~

### 6.2. Minimal Java Spring Boot Handler

A Java 17 project with Spring Boot Web starter can include this controller:

~~~java
package com.example.scheduler;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public final class DailyCloseController {
    private static final Logger log =
        LoggerFactory.getLogger(DailyCloseController.class);

    @PostMapping("/internal/close-day")
    public ResponseEntity<Void> closeDay(
        @RequestHeader(value = "X-CloudScheduler-JobName",
                       required = false) String jobName,
        @RequestHeader(value = "X-CloudScheduler-ScheduleTime",
                       required = false) String scheduleTime
    ) {
        // Demo only: logs metadata without executing business logic.
        log.info("Scheduled call: job={} time={}", jobName, scheduleTime);
        return ResponseEntity.noContent().build();
    }
}
~~~

The controller must sit in a package scanned by `@SpringBootApplication`; the Spring Boot app must listen on the port provided by Cloud Run via `PORT` per runtime config. In this lab, the handler writes no data so test runs cause no side effects. **Returning 204 in the demo only confirms the request reached the handler**, not that accounting books were closed.

### 6.3. Create a User-Managed Caller SA and Grant Invoker

**The following commands modify real resources**:

~~~bash
gcloud iam service-accounts create scheduler-caller \
  --project=PROJECT_ID \
  --display-name="Scheduler to private Cloud Run caller"

gcloud run services add-iam-policy-binding daily-close-api \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --member="serviceAccount:scheduler-caller@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
~~~

The job creator must hold `iam.serviceAccounts.actAs` on this SA. If missing, ask an admin to grant **`roles/iam.serviceAccountUser` to the deployer on that exact SA**. Never grant project-wide `Owner` to fix small permission errors. Check service IAM:

~~~bash
gcloud run services get-iam-policy daily-close-api \
  --project=PROJECT_ID \
  --region=asia-southeast1
~~~

### 6.4. Create an HTTP Job with OIDC and Bounded Retries

Replace `SERVICE_HOST` with the real Cloud Run service hostname (excluding `https://`). All requests in the example carry only non-sensitive demo metadata.

~~~bash
gcloud scheduler jobs create http daily-close-schedule \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --schedule="0 18 * * *" \
  --time-zone="Asia/Ho_Chi_Minh" \
  --uri="https://SERVICE_HOST/internal/close-day" \
  --http-method=POST \
  --headers="Content-Type=application/json" \
  --message-body='{"reason":"scheduled-day-close"}' \
  --oidc-service-account-email="scheduler-caller@PROJECT_ID.iam.gserviceaccount.com" \
  --oidc-token-audience="https://SERVICE_HOST" \
  --attempt-deadline=120s \
  --max-retry-attempts=3 \
  --min-backoff=10s \
  --max-backoff=60s
~~~

Explanation:

- `--schedule` and `--time-zone` govern the cadence, not the Cloud Run region.
- `--oidc-service-account-email` is the **job caller**, holding Invoker on that exact service.
- `--oidc-token-audience` must match the audience validated by Cloud Run; omit query parameters.
- `--attempt-deadline=120s` caps how long Scheduler waits for **one HTTP attempt**.
- `--max-retry-attempts=3` allows policy retries upon attempt failure; it **does not** guarantee each schedule executes only once.
- `--message-body` applies only to POST/PUT; the API does not treat the body as a secret or trusted command.

### 6.5. Describe Configuration, Trigger a Test Run, and Check Logs

~~~bash
gcloud scheduler jobs describe daily-close-schedule \
  --project=PROJECT_ID \
  --location=asia-southeast1

# This command IMMEDIATELY triggers a real request.
gcloud scheduler jobs run daily-close-schedule \
  --project=PROJECT_ID \
  --location=asia-southeast1

gcloud run services logs read daily-close-api \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --limit=50
~~~

Inspect Cloud Scheduler job status/logs, Cloud Run request logs, and a `Scheduled call` log line. When testing against handlers with business effects, always use a **sandbox and dedup**; `jobs run` is not a dry run.

**Important note on manual runs:** `X-CloudScheduler-ScheduleTime` may match the upcoming scheduled interval or **be absent**. If you use this header as a dedup key, a manual run could mark the upcoming scheduled interval as already processed. Never use `jobs run` to test real day-close logic without a dedicated test mode.

## 7. At-Least-Once Delivery and Deduplication in Java

### 7.1. Why Can One Scheduled Interval Be Called Twice?

~~~mermaid
sequenceDiagram
    participant S as Cloud Scheduler
    participant R as Cloud Run Java
    participant DB as Cloud SQL
    S->>R: POST run=2026-11-19T11:00Z
    R->>DB: COMMIT day close
    Note over S,R: 204 response lost on network
    S->>R: Retry same scheduled time
    R->>DB: Check unique run key → already processed
    R-->>S: 204, do not execute again
~~~

Cloud Scheduler guarantees **at-least-once delivery**: lost HTTP responses or timeouts can resend the same scheduled run even though the backend already committed. Setting retry count to 0 **is not enough** to guarantee zero transport-level duplicates.

### 7.2. Headers Supporting Deduplication

Cloud Scheduler sends on HTTP/App Engine targets using unix-cron:

- `X-CloudScheduler-JobName`: job identifier.
- `X-CloudScheduler-ScheduleTime`: scheduled run timestamp in RFC 3339; **stays constant across retries of the same scheduled run**.

Construct a composite key `project + region + jobName + scheduleTime`, since `jobName` alone can collide across projects/regions. **Never trust headers as authentication**; require OIDC/IAM on Cloud Run. Groc schedules do not guarantee `ScheduleTime`, and manual `jobs run` invocations need a separate test path.

### 7.3. Transaction / Unique Constraint Pattern for Cloud SQL

PostgreSQL example:

~~~sql
CREATE TABLE scheduler_runs (
    job_name TEXT NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (job_name, scheduled_at)
);

CREATE TABLE daily_close_results (
    business_date DATE PRIMARY KEY,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Within a **single transaction**, Java executes:

~~~sql
BEGIN;

-- Marker ensuring one scheduled interval is processed only once.
INSERT INTO scheduler_runs (job_name, scheduled_at)
VALUES ('daily-close-schedule', '2026-11-19T11:00:00Z')
ON CONFLICT DO NOTHING;

-- The app must inspect the affected rows of the INSERT:
-- = 0 → already completed by a prior transaction: COMMIT and return 204.
-- = 1 → execute the business logic below in the same transaction.
INSERT INTO daily_close_results (business_date)
VALUES (DATE '2026-11-19')
ON CONFLICT (business_date)
DO UPDATE SET completed_at = now();

COMMIT;
~~~

**Warning:** the SQL snippet above illustrates the **execution flow pattern**, not a self-branching script. **Java must skip the UPDATE if the marker INSERT added zero rows**, and must roll back both the marker and business work if processing fails. If the task calls external payment/email/API endpoints outside the database transaction, you need an **end-to-end idempotency key, outbox, or workflow**; a unique marker in Cloud SQL cannot roll back a completed external HTTP call.

### 7.4. Designing Keys and Locks by Business Scope

| Requirement | Key / Guardrail |
|---|---|
| Never close the same schedule run twice | `jobName + scheduledTime` |
| Never close the same business day twice | Unique `businessDate` independent of schedule |
| Multiple projects/regions calling one service | Include `project + region` in key |
| Only one worker processes long-running jobs | Durable claim/lease with TTL and fencing token |
| Publish to Pub/Sub and update DB | Transactional outbox; never assume cross-service atomicity |
| Manual replay/backfill | Distinct, explicitly approved run ID |

**Never use Java `synchronized` or an in-memory set as a distributed lock:** Cloud Run scales across multiple instances and restarts. For multi-step flows, use datastore transactions/conditional writes with `IN_PROGRESS`/`COMPLETED` states, lease expiration, and dead-worker recovery.

## 8. Retries, Attempt Deadlines, and Overlapping Schedules

### 8.1. When Does Scheduler Consider an Attempt Successful?

| Target | Success from Scheduler's Perspective |
|---|---|
| **HTTP** | Target returns HTTP **2xx** before `attemptDeadline` |
| **Pub/Sub** | Message publish to topic is accepted |
| **App Engine** | Target HTTP responds with success status within timeout |

**HTTP 202 Accepted** is still a 2xx status. If a Java API returns 202 while holding the task only in RAM, Scheduler treats it as succeeded even if the task vanishes on instance crash. For async work, return 2xx only after **persisting to a durable queue/store**, or invoke the Cloud Run Jobs/Workflows API with proper execution tracking.

### 8.2. Retry Parameters

| Property | Purpose | Default / Limit to Remember |
|---|---|---|
| `attemptDeadline` (HTTP) | Wait timeout for one HTTP attempt | **3 minutes default**, configurable **15 seconds–30 minutes** |
| `retryCount` / `--max-retry-attempts` | Retry attempt limit | **0 default**, max **5** in retry config |
| `maxRetryDuration` | Retry window from initial attempt | **0 default**; understand interaction with `retryCount` |
| `minBackoffDuration` | Initial retry wait interval | **5 seconds default** |
| `maxBackoffDuration` | Maximum retry backoff ceiling | **1 hour default** |
| `maxDoublings` | Exponential doubling steps before linear backoff | **5 default** |

**Default `retryCount=0` and `maxRetryDuration=0`** means zero policy retries on failure; the next scheduled interval still triggers normally. When combining `retryCount` and `maxRetryDuration`, behavior is not simple addition; consult the `RetryConfig` documentation and test actual configurations.

### 8.3. An Overlong Run Affects the Next Schedule

Cloud Scheduler generally avoids keeping **two outstanding runs of the same job concurrently**. If a previous attempt is still awaiting response, the next interval may be **delayed or skipped**, especially during prolonged retries. Meanwhile, a request that timed out on Scheduler's side may still be **running in the backend**, and rare duplicate requests can still occur.

For example, a job runs every 5 minutes, and the HTTP backend takes 12 minutes:

- With a 3-minute attempt deadline, Scheduler may time out and retry while Java is still running.
- If retries overlap the next scheduled time, the next run may not fire as expected.
- Without idempotency/leasing in the Java API, multiple instances can write business data concurrently.

**Solution:** trigger **durable asynchronous work** and return quickly, or run a Cloud Run Job with execution tracking; add distributed claims/locks and bound processing by SLO. Never turn Scheduler into a multi-hour worker via a single HTTP request.

## 9. Practice B — Scheduler Publishing a Pub/Sub Message

Choose Pub/Sub when you want to **decouple trigger timing from the processing speed** of Java workers on GKE/VMs/Cloud Run.

~~~mermaid
flowchart LR
    Sch["Scheduler every 15 minutes"]
    Topic["Pub/Sub topic<br/>refresh-cache"]
    Sub["Subscription<br/>refresh-cache-sub"]
    Java["Java worker"]
    DB["Cloud SQL / cache"]
    Sch -->|"Publish succeeded"| Topic
    Topic --> Sub
    Sub -->|"At-least-once delivery"| Java
    Java --> DB
~~~

Create lab resources when authorized:

~~~bash
gcloud pubsub topics create refresh-cache-tick \
  --project=PROJECT_ID

gcloud pubsub subscriptions create refresh-cache-sub \
  --project=PROJECT_ID \
  --topic=refresh-cache-tick

gcloud scheduler jobs create pubsub refresh-cache-schedule \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --schedule="*/15 * * * *" \
  --time-zone="Etc/UTC" \
  --topic=refresh-cache-tick \
  --message-body='{"task":"refresh-cache"}'
~~~

**Distinguish two acknowledgment layers:**

1. Scheduler publishes a message to Pub/Sub → job attempt **succeeds**.
2. Java subscriber receives and processes the message → **separate acknowledgment** with Pub/Sub retries/DLQ.

If the subscriber crashes, Scheduler can still report success while the Pub/Sub backlog grows. Therefore you need **both sets of metrics** (Scheduler and Pub/Sub) plus idempotency keyed by schedule interval or business event. Scheduler's **service agent** handles topic publishing permissions per service design; never grant Admin to workers just to make Scheduler work.

## 10. Practice C — Scheduling a Cloud Run Job or Workflows

### 10.1. Cloud Run Jobs for Java Batches

Java batches processing millions of records rarely fit inside an HTTP request wait. Deploy the container as a **Cloud Run Job** with its own timeout and retries. Cloud Scheduler sends an HTTP POST to the Cloud Run Admin API:

~~~text
https://run.googleapis.com/v2/projects/PROJECT_ID/locations/asia-southeast1/jobs/nightly-batch:run
~~~

Example (assuming Cloud Run Job `nightly-batch` already exists):

~~~bash
gcloud scheduler jobs create http nightly-batch-trigger \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --schedule="0 1 * * *" \
  --time-zone="Etc/UTC" \
  --uri="https://run.googleapis.com/v2/projects/PROJECT_ID/locations/asia-southeast1/jobs/nightly-batch:run" \
  --http-method=POST \
  --oauth-service-account-email="scheduler-caller@PROJECT_ID.iam.gserviceaccount.com"
~~~

**Unlike Section 6:** the target is **`run.googleapis.com`**, so use an **OAuth access token**, not an OIDC ID token. The job caller SA needs permission to run the Cloud Run Job, e.g. `roles/run.invoker` on that exact job per Cloud Run docs. The batch container's runtime SA separately holds data access permissions.

Scheduler receiving an HTTP 2xx only means an **execution was requested**; inspect **Cloud Run Job execution status/logs** to see whether the batch succeeded or failed. If Scheduler retries after a network error despite the execution already starting, **multiple executions** may launch. Prevent duplicates using proxy/idempotency tokens or downstream business guards.

### 10.2. Workflows for Multi-Step Integration

Example chain: aggregate orders → update Cloud SQL → publish Pub/Sub → write audit. With Workflows:

~~~mermaid
flowchart TD
    S["Cloud Scheduler"] -->|"OAuth POST executions"| W["Workflows execution"]
    W --> A["Call Java Orders API"]
    A --> D["Verify data"]
    D --> P["Publish event"]
    P --> L["Write audit + finish"]
    W -. "Retry + error handling" .-> A
~~~

Scheduler can call the **Workflows Executions API** at `https://workflowexecutions.googleapis.com/v1/projects/.../executions` using OAuth and a service account holding `roles/workflows.invoker` at the proper scope. Workflows manages step ordering, conditions, and retries; Scheduler acts solely as the **trigger**.

An HTTP success response from the Executions API **does not prove Workflows steps finished**. Track execution state and pass idempotency tokens across side-effecting steps.

### 10.3. Architecture Selection Guide

| Job Characteristics | Approach |
|---|---|
| 2-second Java handler, single HTTP call | Scheduler → private Cloud Run service |
| Need queued workers with a DLQ | Scheduler → Pub/Sub → subscriber |
| 45-minute Java CLI with exit code | Scheduler → Cloud Run Job |
| 5 APIs with retries/error branches/compensation | Scheduler → Workflows |
| Schedule one invoice at a unique date/time | Cloud Tasks or dedicated business scheduling |

## 11. Operations: Pause, Resume, Update, Delete

### 11.1. Administrative Command Set

~~~bash
# Read-only status checks:
gcloud scheduler jobs list \
  --project=PROJECT_ID \
  --location=asia-southeast1

gcloud scheduler jobs describe daily-close-schedule \
  --project=PROJECT_ID \
  --location=asia-southeast1

# The following commands MODIFY job state:
gcloud scheduler jobs pause daily-close-schedule \
  --project=PROJECT_ID \
  --location=asia-southeast1

gcloud scheduler jobs resume daily-close-schedule \
  --project=PROJECT_ID \
  --location=asia-southeast1

gcloud scheduler jobs update http daily-close-schedule \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --schedule="30 18 * * *" \
  --time-zone="Asia/Ho_Chi_Minh"
~~~

**Pause** stops future triggers at the job level, **without cancelling HTTP requests or Cloud Run executions already in progress**. **Resume** requires inspecting backlog/business conditions; never assume missed intervals will all behave identically. Schedule updates must be tested because they can shift close-of-day cutoffs and timezone semantics.

### 11.2. Deleting Lab Resources

After verifying the job and service account are not used by other consumers:

~~~bash
gcloud scheduler jobs delete daily-close-schedule \
  --project=PROJECT_ID \
  --location=asia-southeast1

gcloud scheduler jobs delete refresh-cache-schedule \
  --project=PROJECT_ID \
  --location=asia-southeast1

gcloud scheduler jobs delete nightly-batch-trigger \
  --project=PROJECT_ID \
  --location=asia-southeast1
~~~

These are **cleanup examples for the jobs created in this lab**; do not run them blindly if resources are absent or shared. Deleting a Scheduler job **does not delete** Cloud Run Job executions, Pub/Sub messages, or Cloud SQL rows created by targets.

## 12. Observability and Troubleshooting

### 12.1. What Can You Observe?

| Component | Signals | What to Distinguish |
|---|---|---|
| **Cloud Scheduler** | Job status, last attempt, attempt logs, scheduled time, retries | Request sent/succeeded at the trigger layer |
| **Cloud Run service** | HTTP 2xx/4xx/5xx, latency, container logs, instances | Whether the handler actually processed and committed |
| **Cloud Run Job** | Executions, task failures, exit codes, duration | Whether the batch completed or was merely started |
| **Pub/Sub** | Backlog age, delivery failures, DLQ | Whether the subscriber actually consumed messages |
| **Workflows** | Execution state, step failures, retries | Which step the integration flow reached |
| **Cloud SQL** | Unique key violations, transactions, locks | Whether data stayed accurate across retries |
| **Billing** | Scheduler jobs, Cloud Run, Pub/Sub, Workflows, logs/egress | Whether retries/cadence drove up costs |

Cloud Scheduler logs emit `AttemptStarted` and `AttemptFinished` entries. When a job misses its next interval, look for unfinished or timed-out attempts before creating a duplicate job. Viewing actual logs/metrics requires appropriate Logging Viewer/Monitoring Viewer roles.

### 12.2. Quick Diagnostic Table

| Symptom | Common Cause | Resolution Path |
|---|---|---|
| HTTP 401/403 calling private Cloud Run | Job caller SA lacks `roles/run.invoker` or wrong OIDC audience | Check job SA, target IAM, audience |
| 403 even though job caller holds Invoker | Cloud Scheduler service agent lost `roles/cloudscheduler.serviceAgent` | Check Google-managed principal and role; do not assign user SA by mistake |
| 401 calling `run.googleapis.com` or Workflows API | Used OIDC instead of OAuth, or missing API role | Switch target auth to OAuth, check job/workflow permissions |
| HTTP 404 | Wrong URL/path/region or target changed | Describe Cloud Run service/Job and Scheduler URI |
| HTTP 429/503 | Target overloaded, DB connection pool exhausted | Lower cadence/retries, scale, apply backpressure |
| `DEADLINE_EXCEEDED` | Backend slower than attempt deadline | Tune timeouts realistically; move to async Job/Workflows |
| Scheduler succeeds yet DB not updated | HTTP returned 2xx before durable commit, or Pub/Sub consumer failed | Check downstream logs/backlog and transactions |
| Same interval runs twice | Retry/transport duplicate or manual run | Durable idempotency on `jobName`/`scheduleTime` |
| Job does not run at expected time | Wrong cron/timezone/DST, paused, or API disabled | Describe job, verify timezone, state, logs |
| Next interval not triggered | Previous attempt still pending or retry overlapped schedule | Inspect `AttemptStarted`/`AttemptFinished` and retry policy |
| Manual test caused next day to skip | Used next interval's `scheduleTime` as dedup key | Design distinct run IDs for manual/backfill runs |
| High cost | Too many jobs/high frequency, downstream compute/logging | Check Billing and cost per successful business run |

### 12.3. Troubleshooting Procedure

1. Identify **project, region, job ID, schedule/timezone**, and target.
2. Run `gcloud scheduler jobs describe`: check paused/enabled state, URI, SA, retries, and attempt deadline.
3. Inspect `AttemptStarted`/`AttemptFinished` and HTTP status; separate trigger failures from downstream failures.
4. On 401/403: verify **OIDC vs. OAuth**, audience, job caller SA, target IAM, and Scheduler service agent.
5. On timeout: inspect Cloud Run request timeout, Java logs/GC, Cloud SQL latency, and processing scope.
6. On trigger success with business failure: inspect **Cloud Run Job execution, Workflows execution, or Pub/Sub consumer**.
7. On duplicates: enforce durable keys; never replay before checking whether side effects already applied.
8. Fix in sandbox, test failure/retry/manual paths, then monitor SLOs and costs.

**Never fix a 403 by opening Cloud Run publicly or granting Owner**, and never recover an interval with uncertain data completeness via non-idempotent manual replays.

## 13. SLOs, Cost, and Limits

### 13.1. SLOs Should Not Rely Only on Scheduler Job Success

Example requirement: **yesterday's sales report is ready before 07:00**. The right SLO is:

~~~text
Business completion SLO =
  timestamp when data is processed + report is ready
  <= 07:00 in business timezone
~~~

A Scheduler HTTP job returning 202 at 06:00 meets the trigger SLO yet **does not prove** the report finished. You need end-to-end metrics from Java/Workflows/Job executions and output artifacts.

### 13.2. Cost Sources

- Cloud Scheduler job count/cadence under current pricing.
- Cloud Run compute/requests when targets are invoked, and Cloud Run Jobs executions.
- Pub/Sub messages, Workflows steps, and Cloud Tasks if combined.
- Cloud SQL queries/storage, networking, Cloud Logging, and Monitoring.
- Retry traffic, duplicate handling, and operational effort during failures.

Use **Billing Reports**, **Budgets and alerts**, and current pricing pages; avoid guessing USD unit prices without knowing region, SKU, and execution patterns.

### 13.3. Quotas and Limits

Cloud Scheduler enforces quotas per **project/region** on job count, API reads/writes, and **request payload size**. If running crons every minute across thousands of jobs, first consider consolidating triggers, distributing across projects, or using queue-based processing. For HTTP targets, the **maximum attempt deadline is 30 minutes**, making it unsuitable as a long-running batch worker.

Service limit documentation is subject to change: consult **Cloud Scheduler quotas and limits** before baking numbers into capacity plans or SLAs.

## 14. Case Study: Daily Order Reconciliation

### 14.1. Context

A retail company runs a **Java Orders API** on Cloud Run with Cloud SQL PostgreSQL. At the end of each day in `Asia/Ho_Chi_Minh`, the system must:

1. Finalize the order list.
2. Compute total revenue.
3. Publish a `DAILY_CLOSED` event to Billing and Analytics.
4. Have the complete report ready before 07:00 the next day.

The batch can take **45 minutes**, and Cloud SQL is occasionally slow. There is a strict requirement **never to close or submit settlement twice**.

### 14.2. Proposed Architecture

~~~mermaid
flowchart LR
    Sch["Scheduler 18:00 Asia/Ho_Chi_Minh"]
    WF["Workflows<br/>execution + retries"]
    Batch["Cloud Run Job<br/>Java close-day"]
    DB["Cloud SQL<br/>transaction + idempotency"]
    Pub["Pub/Sub DAILY_CLOSED"]
    Mon["Monitoring & alert"]
    Sch -->|"OAuth start"| WF
    WF --> Batch
    Batch --> DB
    WF --> Pub
    WF -. "execution status" .-> Mon
    Batch -. "result metrics" .-> Mon
~~~

**Why not Scheduler → Java HTTP waiting 45 minutes?** Cloud Scheduler's HTTP attempt deadline caps at 30 minutes. Holding an HTTP request past that limit causes Scheduler to time out and retry while Java is still running, producing duplicate side effects. A **Cloud Run Job** fits long batches; **Workflows** orchestrates steps and checks status. Scheduler only needs to fire a timely trigger.

**Correctness design:**

- `businessDate` key to close each business day once; `scheduleTime` to identify the scheduled interval.
- Durable stateful claim/transaction with fencing if needed—never an in-memory lock.
- Outbox for the `DAILY_CLOSED` event so DB commit + publish failure never drifts.
- Idempotent Workflows/Job retries; timeouts and alerts aligned to SLO.
- If Scheduler calls the Workflows API directly and retries after a lost response, **multiple executions** may be created; Workflows/Java must deduplicate themselves.

### 14.3. Evidence of Completion

| Question | Evidence |
|---|---|
| Did the trigger fire on schedule and timezone? | Scheduler logs, scheduled time |
| Did Workflows/Job complete? | Execution status and logs |
| Did the DB record exactly one day-close? | Unique `businessDate` / transaction audit |
| Was `DAILY_CLOSED` published once in business terms? | Outbox/event ID and subscriber dedup |
| Was the report ready before SLO? | Business completion timestamp |
| Do retries cause duplicates? | Test crash after DB commit before HTTP success |
| Is the cost reasonable? | Billing/cost per interval and retry count |

## 15. Hands-on Exercises and Self-Assessment

### Exercise 1 — Cron and Timezone

Write cron expressions for: (a) 08:30 Monday–Friday Vietnam time; (b) 00:00 on the first day of each month UTC; (c) every 15 minutes.

**Hint:** `30 8 * * 1-5` + `Asia/Ho_Chi_Minh`; `0 0 1 * *` + `Etc/UTC`; `*/15 * * * *`.

### Exercise 2 — DST

A system sets `0 2 * * *` in a timezone observing DST. On clock-change days, the job occasionally does not run as expected. Why? Propose ways to mitigate the risk.

**Hint:** schedules follow wall clock; use UTC or define explicit business rules when local hours repeat or skip.

### Exercise 3 — Caller Identity

Scheduler calls private Cloud Run and gets 403. The deployer holds `roles/cloudscheduler.admin`, yet the job caller SA holds no role on the target.

**Question:** which role must be granted to **which principal, on which resource**? Should `allUsers` be opened?

**Hint:** grant `roles/run.invoker` to the job caller SA on the Cloud Run service; never open publicly.

### Exercise 4 — OIDC or OAuth?

Scheduler calls (a) `https://SERVICE_HOST/internal/close-day` and (b) `https://run.googleapis.com/v2/.../jobs/nightly-batch:run`. Which token does each target require?

**Hint:** OIDC for the Cloud Run service, OAuth for the Google API.

### Exercise 5 — Lost HTTP Response

Java updates the DB and returns 204, yet the response is lost. Scheduler retries the same interval and may update the DB twice. Design the table/key and transaction to prevent this.

**Hint:** `jobName + scheduleTime` or `businessDate`, unique constraint, and atomic commit.

### Exercise 6 — Manual Run

An operator runs `gcloud scheduler jobs run` before the 18:00 schedule; the target uses `scheduleTime` as its dedup key. What problem can occur for the real 18:00 run?

**Hint:** a manual run may carry the next interval's `scheduleTime` or omit the header; design a separate run ID for test/backfill runs.

### Exercise 7 — 45-Minute Job

A Java billing batch takes 45 minutes and runs directly via Scheduler HTTP. What limits/risks arise? Choose an alternative architecture.

**Hint:** 30-minute max HTTP attempt deadline, retries, and duplicate side effects; use Cloud Run Jobs and/or Workflows.

### Exercise 8 — Pub/Sub Target "Success"

Scheduler publishes a message successfully, yet the Java consumer on GKE hits OOM and the Pub/Sub backlog grows. The Scheduler dashboard still shows success. Is this contradictory?

**Hint:** no; Scheduler only confirms the publish, so Pub/Sub subscriptions and consumers must be monitored separately.

### Exercise 9 — Retries and Schedule Intervals

A job runs every 5 minutes, and the target responds after 12 minutes or times out and retries for a long time. Is the next interval guaranteed to fire on the exact minute? Why is a durable claim needed?

**Hint:** the next interval may be delayed or skipped; the old backend request may still be processing after timeout.

### Exercise 10 — End-of-Day SLO Design

Design an architecture for Java to finalize orders and publish events before 07:00 the next morning. Cover **Scheduler cron/timezone, Workflows/Cloud Run Job, IAM, idempotency, monitoring, retries, and recovery**.

**Hint:** measure business completion and side effects, not just Scheduler's HTTP success.

## 16. Production Readiness Checklist

- [ ] Selected **Cloud Scheduler** for recurring scheduled tasks; not confused with one-off Cloud Tasks.
- [ ] 5-field cron verified, with explicit **IANA timezone** and DST accounted for.
- [ ] Target (HTTP/PubSub/App Engine) matches requirements and location/network constraints.
- [ ] Separated **deployer, job caller SA, Scheduler service agent, and runtime SA**.
- [ ] Private HTTP Cloud Run uses **OIDC + Invoker**; Google APIs use **OAuth**.
- [ ] OIDC audience matches the service URL without query strings.
- [ ] No hardcoded service account keys/tokens; no broad Editor/Owner grants.
- [ ] Verified Scheduler service agent retains `roles/cloudscheduler.serviceAgent`.
- [ ] Java handler returns 2xx **after durable result persistence** or durable enqueue.
- [ ] Durable idempotency handles retries and manual/backfill runs; headers are never treated as credentials.
- [ ] Attempt deadline, `retryCount`, and min/max backoff fit SLOs; no HTTP calls over 30 minutes.
- [ ] Long tasks run via **Cloud Run Jobs/Workflows** with **execution status** tracking.
- [ ] Pub/Sub targets have separate subscription/consumer metrics, DLQs, and retries.
- [ ] Tested timeouts, lost responses, 403, 429/503, duplicates, and post-commit crashes.
- [ ] Alerts configured for failed Scheduler attempts, Cloud Run/Job/Workflow errors, and business SLOs.
- [ ] IaC/config review, owner, log retention, IAM audit, and rollback are in place.
- [ ] Budgeted Scheduler, compute, Pub/Sub/Workflows, database, logging, egress, and retry costs.
- [ ] Sandbox cleanup only after verifying ownership; never delete shared jobs/queues.

## 17. Official Google Cloud Documentation

Flags, limits, pricing, and integration details may change. Cross-check before deploying:

- [Cloud Scheduler — Overview](https://docs.cloud.google.com/scheduler/docs/overview)
- [Cloud Scheduler — Create and manage cron jobs](https://docs.cloud.google.com/scheduler/docs/creating)
- [Cloud Scheduler — Cron job schedules and time zones](https://docs.cloud.google.com/scheduler/docs/configuring/cron-job-schedules)
- [Cloud Scheduler — HTTP target authentication](https://docs.cloud.google.com/scheduler/docs/http-target-auth)
- [Cloud Scheduler — Deduplicate job requests](https://docs.cloud.google.com/scheduler/docs/configuring/deduplicate-job-requests)
- [Cloud Scheduler — Configure retry jobs](https://docs.cloud.google.com/scheduler/docs/configuring/retry-jobs)
- [Cloud Scheduler — Troubleshoot jobs](https://docs.cloud.google.com/scheduler/docs/troubleshooting)
- [Cloud Scheduler — IAM access control](https://docs.cloud.google.com/scheduler/docs/access-control)
- [Cloud Scheduler — Quotas and limits](https://docs.cloud.google.com/scheduler/quotas)
- [Cloud Scheduler — gcloud HTTP job reference](https://docs.cloud.google.com/sdk/gcloud/reference/scheduler/jobs/create/http)
- [Cloud Run — Running services on a schedule](https://docs.cloud.google.com/run/docs/triggering/using-scheduler)
- [Cloud Run — Execute jobs on a schedule](https://docs.cloud.google.com/run/docs/execute/jobs-on-schedule)
- [Workflows — Schedule workflow execution](https://docs.cloud.google.com/workflows/docs/schedule-workflow)
- [Cloud Tasks — Overview](https://docs.cloud.google.com/tasks/docs/overview)
- [Cloud Scheduler pricing](https://cloud.google.com/scheduler/pricing)

**Key takeaway:** **Cloud Scheduler triggers tasks on a schedule; it does not run Java code for you.** Choose **HTTP, Pub/Sub, Cloud Run Job, or Workflows** based on runtime duration and orchestration needs. Define cron/timezone explicitly, use **OIDC or OAuth matching the target**, and always protect business logic with **durable idempotency** because Scheduler can redeliver the same interval. Measure success only when **the actual work completes, meets SLOs, and creates no duplicate side effects** — not merely when Cloud Scheduler reports "Success".
