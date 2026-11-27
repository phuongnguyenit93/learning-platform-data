# Overlap, Retry, and Timeout Policies

In the **Scheduling** chapter of the **SPRING_CLOUD_TASK** module, tasks are typically launched on a fixed cadence: generating a morning report, syncing data hourly, or reconciling at end of day. Spring Cloud Task enables Spring Boot applications to run **finitely** and persist execution metadata into `TaskRepository`. However, **Spring Cloud Task is not itself a distributed scheduling system**. Creating schedules, allowing or forbidding overlaps, deciding process retries, and enforcing deadlines generally belong to the scheduler or deployment platform such as Kubernetes CronJob, Spring Cloud Data Flow (SCDF), or a dedicated orchestrator.

Three concerns are tightly coupled:

- **Overlap:** the previous run has not finished when the next scheduled trigger arrives.
- **Retry:** a run fails; the system decides whether and when to launch another attempt.
- **Timeouts / deadlines:** work does not finish in time; the scheduler may skip an overdue run, terminate a running process, or hand off to reconciliation.

If these concerns are handled in isolation, the system can easily duplicate data: the scheduler launches a second instance while the first task is still running; both Kubernetes **and** the application retry a failed run; or a process is killed right while the database is executing `COMMIT`. This lesson establishes a cohesive policy across **orchestration, process, and business layers**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish launch schedules from the Spring Cloud Task lifecycle and `TaskExecution` metadata.
2. Choose between **allow**, **forbid**, or **replace** overlap policies and understand each option's limits.
3. Classify retryable failures, non-retryable failures, and indeterminate outcomes.
4. Distinguish schedule start deadlines, process runtime deadlines, service call timeouts, and business completion SLAs.
5. Configure an illustrative Kubernetes CronJob using `concurrencyPolicy`, `startingDeadlineSeconds`, `backoffLimit`, and `activeDeadlineSeconds`.
6. Explain why `TaskRepository` and Kubernetes Job status can disagree after a JVM crash.
7. Design business keys, unique constraints, and reconciliation to make re-runs safe.
8. Design observability, alerting, and testing checklists for scheduled or on-demand tasks.

## 2. A Schedule Is Not a Single Execution

Suppose the system must aggregate revenue **every day at 02:00 in the `Asia/Ho_Chi_Minh` timezone**. One schedule produces many executions on different dates. If November 24's run has not finished by 02:00 on November 25, two tasks could be processing concurrently.

Separate these concepts clearly:

| Concept | Example | Responsibility |
| --- | --- | --- |
| **Schedule** | 02:00 daily | When **should** a run be requested? |
| **Scheduled occurrence** | 02:00 tick on Nov 24 | Which **due slot** needs to be processed? |
| **Launch request** | `REQ-20261124-DAILY` | Did the orchestrator accept the request? |
| **Execution / attempt** | `TASK_EXECUTION_ID=503` | How did a concrete process run? |
| **Business key** | `tenant=shop-01;date=2026-11-23;version=v1` | Which **unique** unit of business work is being executed? |
| **Completion** | Report saved and verified complete | Did the outcome satisfy business criteria? |

One scheduled occurrence can produce **multiple attempts** when retries are configured. Each attempt may receive a new `TaskExecution` ID. Yet **the same business key must produce only one business outcome** when uniqueness is required by business rules.

~~~mermaid
flowchart TD
    A["Schedule: daily 02:00"] --> B["Scheduled occurrence: day D"]
    B --> C["Launch request + business key K"]
    C --> D["Attempt 1 / TaskExecution #503"]
    D -->|"Retryable error"| E["Attempt 2 / TaskExecution #504"]
    D -->|"Completed"| F["Business outcome K"]
    E -->|"Completed or already done"| F
    F --> G["Reconcile + conclude for occurrence D"]
~~~

**Important boundary:** Spring Cloud Task records application runs; it does not infer cron policies, handle missed occurrences, or stop two processes from writing the same output. Those protections must be designed outside the repository or in the business layer.

## 3. Overlap Policies: `Allow`, `Forbid`, and `Replace`

When the prior run is still active as the next trigger arrives, the orchestrator needs an explicit policy. Kubernetes CronJob provides three standard `concurrencyPolicy` values:

| Policy | When a New Tick Arrives While the Old Job Is Active | Best Fit | Risks |
| --- | --- | --- | --- |
| **`Allow`** | Permits creating a new Job even while the old Job runs | Work cleanly partitioned by period/shard with sufficient capacity | Duplicate writes, data contention, overload |
| **`Forbid`** | Does not create a new Job from **this same CronJob** while the old Job is active | Shared-resource aggregations avoiding overlap | Triggers can be skipped; not queued by default |
| **`Replace`** | Requests replacing the old Job with a new Job | When only the latest period matters and work stops safely | Can interrupt mid-transaction; termination lag leaves old side effects |

These names are **Kubernetes CronJob policies**, not a built-in Spring Cloud Task enum. In SCDF, Quartz, or custom schedulers, mechanisms and configuration differ.

### 3.1. `Allow`: Parallel Runs Require Clear Partitioning

If each hourly task reads only **its own hourly window** and writes keyed by `(tenant, hour)` with a unique constraint, running two different hours in parallel can be safe.

However, "two different hours" does not automatically mean no shared resources. Check:

- Do they write to the same target file or summary table?
- Do they share staging tables, database locks, or working directories?
- Does the upstream API enforce concurrent request limits?
- Can out-of-order writes (a newer hour committing before an older hour) cause issues?

If the source does not tolerate parallelism, choosing `Allow` just to avoid missing ticks is usually unsafe.

### 3.2. `Forbid`: Prevents Overlaps, but Can Miss Schedules

`Forbid` is useful when a task must not run twice concurrently. For instance, if the 02:00 sync runs until 03:20 on an hourly schedule, the 03:00 tick may be **skipped** rather than queued to run at 03:20.

Therefore, if every period **must be processed**, maintain a table or queue of **due incomplete periods** processed by workers. `Forbid` alone only limits overlaps among Jobs spawned by a single CronJob.

**Protection scope:** `concurrencyPolicy` does not block an operator from launching a manual Job, another CronJob, or an external service from processing the **same business key**. Data-layer protection is still required.

### 3.3. `Replace`: Replaces the Old Run Without Erasing Old Side Effects

`Replace` can make sense when refreshing an entire cache where only the latest version matters and the task publishes results atomically. It is especially dangerous for payments or non-idempotent mutations.

When replacement is requested, the old process receives a termination signal and takes time to close, roll back, or drop connections. **Never assume a magical instant where all side effects of the old Job are erased before the new Job starts.** Unique keys, fencing tokens, or version-checked updates remain the last line of defense.

### 3.4. Choosing a Policy by Business Impact

- **End-of-day aggregation:** usually prefer `Forbid` or a sequential queue, paired with recovery for missed days.
- **Independent partition computations:** `Allow` can work alongside caps on total workers, DB connections, and CPU.
- **Cancellable/replaceable snapshot refreshes:** `Replace` can work if outputs publish only upon completion and the old Job cannot overwrite newer data.
- **Non-deduplicated payments/notifications:** never rely on any concurrency policy in place of idempotency at the target system.

## 4. Schedules, Timezones, and Missed Runs

A **Kubernetes CronJob** expression typically has **5 fields**: minute, hour, day-of-month, month, day-of-week. For example:

~~~text
0 2 * * *     # 02:00 daily
*/15 * * * *  # every 15 minutes
~~~

Meanwhile, Spring `@Scheduled` cron expressions typically have **6 fields**, including **seconds**. Quartz uses yet another convention. **Never copy cron expressions across schedulers without verifying syntax.**

### 4.1. Timezones Must Be Declared Explicitly

Supported Kubernetes CronJob versions provide `spec.timeZone` with an IANA timezone name:

~~~yaml
spec:
  schedule: "0 2 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
~~~

When omitted, execution time may depend on the controller's cluster-configured timezone. Never infer timezone from an operator's workstation or the JVM timezone.

In DST-observing regions, some local clock times may **not exist** or may **occur twice**; define business rules around *scheduled instants* and calendars. `Asia/Ho_Chi_Minh` in this example does not currently observe DST, though specifying the IANA timezone still makes configuration explicit.

### 4.2. Allowed Delay for Missed Schedules

Kubernetes CronJob's `startingDeadlineSeconds` bounds **how late after the scheduled time** the controller may still start a Job. It is **not** a limit on how long **the Job may run**.

Example:

- Job scheduled for 02:00.
- Controller suffers an outage and recovers at 02:18.
- `startingDeadlineSeconds: 600` (10 minutes).

The 02:00 trigger is past the 10-minute window and may not be started. If no period may be lost, persist occurrences in a durable store for catch-up rather than **treating CronJob as a durable exactly-once queue**.

Kubernetes also imposes limits on how the CronJob controller handles accumulated missed schedules; verify the documentation for your cluster version. Garbage collection of old Jobs via retention settings **does not prove a schedule never ran**.

## 5. Retries Differ from Recurring Schedule Launches

A run exiting non-zero or crashing can trigger multiple retry layers:

1. **Inside the app:** JDBC, HTTP client, or micro-operation retries.
2. **Inside Spring Batch:** chunk/item retries according to configured skip/retry policies.
3. **At Kubernetes Job:** spawning replacement Pods or restarting containers based on `restartPolicy` and `backoffLimit`.
4. **At the scheduler/SCDF:** re-launching the entire task.
5. **At the API caller:** resending a launch request after a timeout.

Never configure layers independently without calculating their combined effect. For example, if an orchestrator attempts **3 launches** and **each Job allows up to 3 Pod attempts**, the application could run up to **9 times** in a worst-case scenario; if each run retries an upstream call 5 times, total request volume multiplies sharply. This illustrates the design budget, not an exact formula for every Kubernetes state.

### 5.1. Error Categories and Actions

| Failure Type | Examples | Handling Strategy |
| --- | --- | --- |
| **Transient** | HTTP 503, brief DNS failure, deadlock/serialization failure | Bounded retries with backoff and jitter using the same business key |
| **Non-retryable as-is** | Malformed date, missing schema, bad DB credentials, data conflict | Fail clearly and fix the root cause first |
| **Indeterminate outcome** | Connection drop around `COMMIT`; timeout after calling a payment API | Reconcile via business key / idempotency key before replaying |
| **Overload** | API returns 429, database exhausts connection pool | Reduce concurrency, honor `Retry-After` if present, back off |
| **Resource error** | OOMKilled, full disk, severe CPU throttling | Adjust resources and investigate root cause; do not loop indefinitely |
| **Deadline exceeded** | Process ran longer than allowed | Verify business state before retrying; handle cancellation |

Whenever you do not know whether a transaction committed, classify the failure as **UNKNOWN**. Never treat every database exception as proof that "nothing was written".

### 5.2. Exponential Backoff and Jitter

An illustrative rule for transient failures:

~~~text
delay(attempt) = min(maxDelay, initialDelay × 2^(attempt-1))
wait = delay(attempt) + randomJitter
~~~

For instance, `initialDelay=5 seconds`, `maxDelay=60 seconds`, and up to **3 attempts**. Thousands of tasks should never retry on the exact same schedule right as an upstream recovers; jitter spreads out the load.

A **total time budget** must also apply: retrying after the business deadline may no longer make sense. All attempts must carry the same **business key** and ideally a correlation ID linking logs.

## 6. Timeouts and Deadlines: Four Distinct Layers

"Task timeout" can refer to several different limits. Collapsing them into one number causes confusion during incident response.

| Layer | Question | Example Configuration / Mechanism |
| --- | --- | --- |
| **Start delay** | How long past due may an occurrence still start? | CronJob `startingDeadlineSeconds` |
| **Job lifetime** | How long may a single Job stay active? | Kubernetes Job `activeDeadlineSeconds` |
| **Business call** | How long do HTTP, SQL, or messaging calls wait? | HTTP client connect/read timeout, JDBC query timeout |
| **Business SLA** | By what time must the report be ready? | Separate deadline in orchestration/monitoring tables |

Plus two additional values:

- **Launch acknowledgment wait:** how long a caller waits for a launch REST API receipt. A timeout here does not prove the server never created the Job.
- **Graceful shutdown window:** how long a Pod has after receiving `SIGTERM` to close resources before forced termination (`terminationGracePeriodSeconds`). This does not guarantee every transaction rolled back cleanly.

### 6.1. `activeDeadlineSeconds` Is Not `startingDeadlineSeconds`

Example:

~~~yaml
spec:
  startingDeadlineSeconds: 600
  jobTemplate:
    spec:
      activeDeadlineSeconds: 1800
~~~

- `600` seconds: late-start window for a **CronJob occurrence**.
- `1800` seconds: maximum active lifetime for **one Job** once started as tracked by the Job controller—including related startup/scheduling delays, not solely runner processing time.

If the Job exceeds `activeDeadlineSeconds`, Kubernetes marks it as `DeadlineExceeded` and terminates its Pods per platform mechanics. `backoffLimit` will not keep retrying a Job past that deadline.

**Never infer database state from a deadline:** the process may have committed partial changes right before termination. After any timeout, reconcile business data just as after a connection failure.

### 6.2. Timeouts Must Align Hierarchically

An example limit budget:

- HTTP request timeout: 30 seconds.
- Up to 3 retries with backoff.
- Total expected business processing under 20 minutes.
- Job active deadline: 30 minutes.
- Report SLA: ready before 03:00 for the 02:00 occurrence.

These are **illustrative parameters** to tune against real data volumes. If worst-case inner HTTP retries exceed 30 minutes, the Job gets killed mid-flight and the inner retry policy becomes futile.

## 7. Kubernetes CronJob Example: Preventing Overlaps with Bounded Retries

Below is an **illustrative** configuration for a daily 02:00 aggregation task. It chooses `Forbid` so two Jobs from the **same CronJob** never process simultaneously.

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-report-task
  namespace: batch
spec:
  schedule: "0 2 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 600
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 5
  jobTemplate:
    spec:
      backoffLimit: 1
      activeDeadlineSeconds: 1800
      parallelism: 1
      completions: 1
      template:
        spec:
          restartPolicy: Never
          terminationGracePeriodSeconds: 30
          containers:
            - name: daily-report
              image: registry.example.internal/batch/daily-report:1.0.0
              imagePullPolicy: IfNotPresent
              command: ["java"]
              args: ["-jar", "/app/daily-report.jar", "--mode=process-due"]
              env:
                - name: TASK_DB_URL
                  valueFrom:
                    secretKeyRef:
                      name: daily-report-db
                      key: jdbc-url
                - name: TASK_DB_USERNAME
                  valueFrom:
                    secretKeyRef:
                      name: daily-report-db
                      key: username
                - name: TASK_DB_PASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: daily-report-db
                      key: password
              resources:
                requests:
                  cpu: "250m"
                  memory: "256Mi"
                limits:
                  cpu: "1"
                  memory: "512Mi"
~~~

**Example prerequisites:** namespace `batch`, registry/image, Secret `daily-report-db`, and the application JAR must be prepared beforehand; `--mode=process-due` is a **custom CLI contract defined by this example app**, not a built-in Spring Cloud Task flag. Without implementing that mode in the app, CronJob cannot discover due periods on its own.

### 7.1. Meaning of Each Field

| Field | Practical Effect |
| --- | --- |
| `schedule: "0 2 * * *"` | Requests execution at 02:00 every day |
| `timeZone` | Uses the specified IANA timezone (supported in compatible modern Kubernetes releases) |
| `concurrencyPolicy: Forbid` | Prevents overlapping active Jobs owned by this CronJob |
| `startingDeadlineSeconds: 600` | Stops attempting to start occurrences overdue by more than 10 minutes |
| `backoffLimit: 1` | Caps Job retries on Pod failure; typically permits at most one retry after the initial attempt in simple setups |
| `activeDeadlineSeconds: 1800` | Prevents a Job from running longer than ~30 minutes under Job deadline rules |
| `parallelism: 1`, `completions: 1` | Requires a single completion without parallel Pods |
| `restartPolicy: Never` | Failed container will not restart in-place inside the same Pod; Job controller may spawn another Pod per retry policy |
| `terminationGracePeriodSeconds: 30` | Grace window for the Pod to shut down cleanly before forced termination |
| `successfulJobsHistoryLimit / failedJobsHistoryLimit` | Caps old Jobs retained by CronJob, not `TaskRepository` retention |

In production, verify admission policies, Secret read permissions, resource quotas, image pull access, and database connectivity. Never hardcode passwords in `args`, as command-line arguments can appear in container history or Task metadata.

### 7.2. Why Not Hardcode `businessDate` in the CronJob?

A configuration like:

~~~yaml
args: ["-jar", "/app/daily-report.jar", "--businessDate=2026-11-24"]
~~~

will process **the exact same date 2026-11-24 on every run**, even though the CronJob repeats daily. Replacing it with today's date from the JVM clock is not always safe either: an occurrence delayed past midnight can select the **wrong period**.

A more stable approach is **deriving the business key from the scheduled occurrence** inside an orchestrator and persisting it durably, or having `--mode=process-due` claim a **due incomplete** period from a business table/queue. Every attempt for the same period must use the same `businessDate`, `tenantId`, and `version`. If you rely on Kubernetes Job scheduled timestamps, verify annotation/metadata support in your **actual Kubernetes version** and how that value reaches the application; never assume CronJob injects the scheduled date into JVM args automatically.

### 7.3. Spring Cloud Task Metadata Schema

Inside the application, configure JDBC metadata via environment variables:

~~~yaml
spring:
  application:
    name: daily-report-task
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
  cloud:
    task:
      name: daily-report-task
      initialize-enabled: false
~~~

Use a durable database with version-matched Task tables created via migrations. `initialize-enabled: false` **does not disable `TaskRepository`**; it assumes the schema already exists rather than letting every instance auto-create tables at startup.

## 8. Designing a Due-Periods Table So No Schedule Is Lost

If `Forbid` skips an occurrence or the scheduler goes down, the pipeline should not silently assume "that day no longer needs to run". For workloads requiring every period to finish, maintain a **business work-request table**:

~~~sql
CREATE TABLE scheduled_work (
    tenant_id       VARCHAR(64) NOT NULL,
    business_date   DATE NOT NULL,
    report_version  VARCHAR(24) NOT NULL,
    status          VARCHAR(32) NOT NULL,
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    scheduled_at    TIMESTAMPTZ NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, business_date, report_version)
);
~~~

**Note:** this is a **custom application schema designed by your team**, not a standard Spring Cloud Task table.

A planning service can insert rows when occurrences fall due, while workers process `PENDING` or `RETRYABLE` rows:

1. Determine the business key for the occurrence and insert idempotently (`INSERT ... ON CONFLICT DO NOTHING` in PostgreSQL).
2. The worker selects an incomplete row and **claims it atomically** via a transaction/row lock or bounded lease—never merely `SELECT` and assume ownership.
3. Execute the task and write business results under the same business key.
4. Mark `COMPLETED` only after the actual output is persisted and verified.
5. After a crash, check the lease, already-committed results, and resumability before retrying.

### Protecting Concurrent Processing

Claiming can use `SELECT ... FOR UPDATE SKIP LOCKED` inside a short transaction when multiple workers pull work from the same database, combined with updating status/lease columns. However, **never hold a row-locking transaction open for minutes while doing the actual work**. Use bounded leases, generation tokens (*fencing tokens*), and target-side constraints so an expired worker cannot overwrite a newer worker's results.

If reports are generated per partition, the unique key can sit at `(businessDate, partitionId, version)`; locking solely by date would needlessly serialize independent partitions.

## 9. Safe Retries on Connection Drops or Mid-Commit Kills

A dangerous failure occurs when the database commits the report, yet the connection drops before the JVM receives acknowledgment. The scheduler sees a failed attempt and retries.

Never assume:

~~~text
Exit code != 0  =>  business work definitely rolled back
~~~

Instead:

~~~mermaid
flowchart TD
    A["Job failed, timed out, or killed"] --> B["Read business key from schedule / request table"]
    B --> C{"Can primary business data source be queried?"}
    C -->|"No"| D["UNKNOWN: alert and back off for reconciliation"]
    C -->|"Yes"| E["Check committed result by key"]
    E --> F{"Result exists and is valid?"}
    F -->|"Yes"| G["Confirm completed; do not duplicate"]
    F -->|"No; key exists with different data"| H["CONFLICT: investigate"]
    F -->|"Not found"| I["Retry idempotent operation with same key"]
    I --> J["Re-verify result / update status"]
    J --> G
~~~

To prevent races between checking and writing when two processes run concurrently, enforce a `UNIQUE`/`PRIMARY KEY` or atomic write in **the business database**, not just a `SELECT` before `INSERT`.

PostgreSQL example recording **one** result row per period:

~~~sql
CREATE TABLE daily_report (
    tenant_id      VARCHAR(64) NOT NULL,
    business_date  DATE NOT NULL,
    report_version VARCHAR(24) NOT NULL,
    content_hash   CHAR(64) NOT NULL,
    report_body    TEXT NOT NULL,
    PRIMARY KEY (tenant_id, business_date, report_version)
);
~~~

~~~sql
INSERT INTO daily_report (
    tenant_id, business_date, report_version, content_hash, report_body
)
VALUES ('shop-01', DATE '2026-11-23', 'v1', :content_hash, :report_body)
ON CONFLICT (tenant_id, business_date, report_version)
DO NOTHING;
~~~

The `:content_hash` and `:report_body` placeholders here represent SQL layers supporting named parameters, **not direct raw `JdbcTemplate` syntax**. With `JdbcTemplate`, use `?` placeholders and positional parameter binding.

If the row already exists, verify the hash and business rules: **same key with different content** indicates a conflict or requires a new version—never return a false success. If the task sends emails/HTTP requests or writes to object storage, add an idempotency key or target-system reconciliation; a JDBC transaction alone cannot roll back external side effects.

## 10. Spring Cloud Task Apps Must Propagate Failures Properly

An `ApplicationRunner` typically parses arguments and delegates to a business service. On unhandled failures, never catch the exception just to log it and exit normally.

Illustrative Java structure:

~~~java
package com.example.task;

import java.time.LocalDate;
import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DailyReportApplication {

    public static void main(String[] args) {
        SpringApplication.run(DailyReportApplication.class, args);
    }

    @Bean
    ApplicationRunner dailyReportRunner(ReportService service) {
        return args -> {
            LocalDate date = requiredDate(args, "businessDate");
            String tenant = requiredValue(args, "tenant");

            service.generateIdempotently(tenant, date, "v1");
            System.out.println("Report completed: " + tenant + "/" + date);
        };
    }

    private static LocalDate requiredDate(
            ApplicationArguments args, String name) {
        return LocalDate.parse(requiredValue(args, name));
    }

    private static String requiredValue(
            ApplicationArguments args, String name) {
        List<String> values = args.getOptionValues(name);
        if (values == null || values.size() != 1
                || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Missing or invalid: --" + name + "=...");
        }
        return values.get(0).trim();
    }
}
~~~

`ReportService` is a business service **implemented by your project**, not a Spring Cloud Task class. It must handle idempotency/transactions and ambiguous commits as discussed in Sections 8–9; the snippet only illustrates runner structure and argument validation.

Furthermore, the CronJob sample in Section 7 uses `--mode=process-due`; to combine both examples, either **implement due-period claiming** or update the launcher to supply stable `--tenant` and `--businessDate` args. You cannot pair a Java runner requiring both parameters with a CronJob that never passes them.

### What Does Spring Cloud Task Record Automatically?

When infrastructure is properly configured and the repository is reachable, each application launch can create a `TaskExecution`. Useful fields include:

- `TASK_EXECUTION_ID` — ID of the attempt.
- `TASK_NAME` — task application name.
- `START_TIME` and `END_TIME`.
- `EXIT_CODE`, `EXIT_MESSAGE`, and `ERROR_MESSAGE`.

Still, `EXIT_CODE=0` cannot substitute for verifying business results. Conversely, `END_TIME IS NULL` does not prove a process is still running. If `ApplicationContext` fails early, no row may exist in `TaskRepository` at all.

Example lookup query:

~~~sql
SELECT TASK_EXECUTION_ID, TASK_NAME, START_TIME,
       END_TIME, EXIT_CODE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'daily-report-task'
ORDER BY START_TIME DESC;
~~~

To determine why a Job was killed due to timeout, **cross-check Kubernetes Job/Pod status and logs**, because the repository cannot always update metadata upon forced runtime termination.

## 11. Observing and Alerting Around Schedules

You should integrate at least three data sources:

~~~mermaid
flowchart LR
    A["CronJob / scheduler"] --> B["Job / Pod runtime status"]
    A --> C["Business key + scheduled occurrence"]
    B --> D["Operational reconciliation"]
    E["TaskRepository / TaskExecution"] --> D
    C --> D
    D --> F["Business DB: result accurate/complete?"]
    F --> G["SUCCEEDED / FAILED / MISSED / UNKNOWN"]
~~~

| Data | Source | Why Needed |
| --- | --- | --- |
| `scheduledAt` | Scheduler or occurrence table | Know which periods fell due, even if no Job was created |
| `acceptedAt` / Job UID | Runtime API | Confirm the Job was accepted |
| `startedAt`, `finishedAt` | Pod, Job, scheduler | Measure real startup and execution durations |
| `taskExecutionId` | `TaskRepository` | Inspect Task error details when recorded |
| `businessKey` and `attempt` | Orchestration table | Group multiple retries under one request |
| `lastHeartbeat` / lease | Work table if needed | Distinguish live workers from stale records |
| `deadline` / SLA | Business rules | Determine when to fire alerts |
| `resultFingerprint` / output URI | Business database | Verify actual outputs |

### Useful Alerts

- An occurrence passed `scheduledAt + tolerance` with neither a Job nor an output: **MISSED_SCHEDULE**.
- A Job runs past expected duration even before hitting its hard deadline: **SLOW_TASK**.
- Pod terminated via OOMKilled, `DeadlineExceeded`, or repeated failures: **EXECUTION_FAILED**.
- Job finished yet `TaskExecution.END_TIME` remains null past a reconciliation grace window: **METADATA_INCOMPLETE**.
- Multiple attempts processing the same business key concurrently: **OVERLAP_DETECTED**.
- Business outcome missing past SLA despite an attempt having `EXIT_CODE=0`: **BUSINESS_INCOMPLETE**.

These alert names are **conventions an operations team can define**, not built-in Spring Cloud Task statuses.

## 12. Timeline Walkthrough Example

Assume a daily 02:00 schedule using `Forbid`, `startingDeadlineSeconds=600`, and `activeDeadlineSeconds=1800`.

| Time | Event | Conclusion |
| --- | --- | --- |
| 02:00 | CronJob falls due; controller creates Job J1 | Schedule accepted; **no** business outcome yet |
| 02:02 | Pod boots JVM; `TaskExecution` recorded | Proof that the task started executing |
| 02:15 | Report committed | Business result verifiable by key |
| 02:17 | `TaskRepository` updated; process exits | Metadata complete enough to report success if output checks pass |
| Next day 02:00 | Controller falls due again | A **distinct** occurrence with a distinct business key |
| Failure case: 02:18 | JVM killed right after commit but before `END_TIME` update | Do not retry blindly; reconcile by key first |

Another example: on an **every-10-minutes** schedule, if the 02:00 run takes until 02:35, `Forbid` may skip the 02:10, 02:20, and 02:30 ticks. That is why a **backlog ledger** is needed whenever every 10-minute slice must be processed.

Never increment attempt numbers arbitrarily or alter `businessDate` before a task completes; doing so breaks correlation and deduplication across runs.

## 13. Spring Cloud Data Flow and `@Scheduled`

Kubernetes CronJob is one scheduling option, not the only one.

### 13.1. Spring Cloud Data Flow

SCDF supports registering, launching, and scheduling Tasks on supported platforms. With SCDF, scheduling, resource, concurrency, and retry properties depend on the **target scheduler/deployer and SCDF version**; do not copy Kubernetes YAML fields assuming they are generic Spring Cloud Task properties.

The core principles remain unchanged:

- A schedule or trigger creates a **launch request**.
- Distinguish `launch accepted` from **task completed**.
- Persist correlation across scheduled occurrence, execution ID, platform Job, and business key.
- Observe outcomes across SCDF/runtime, `TaskRepository`, and the business store.
- Never auto-relaunch after a launch API timeout without checking whether the prior request was already accepted.

### 13.2. `@Scheduled` in Spring

`@Scheduled` fits a **long-lived service application** triggering periodic work. Placing `@Scheduled` inside a Spring Cloud Task **meant to run once and exit** is usually the wrong architecture: keeping the JVM alive waiting for the next tick breaks the finite-process model.

If a coordinator service uses `@Scheduled`, it can invoke a launcher to **spawn a separate Spring Cloud Task process**. Keep in mind:

- `@Scheduled` does not provide distributed locking across multiple replicas by default.
- Separate the timer from workers, and add leader election/locking when running multiple replicas.
- Do not rely on Spring's cron to avoid missed schedules across downtime without durable occurrence persistence.
- Cron syntax and `zone` specification differ from Kubernetes CronJob.

## 14. Coordinating with Spring Batch

A Spring Cloud Task application can execute a Spring Batch Job. Two repositories track two distinct layers:

- `TaskRepository`: metadata for **one application launch**.
- `JobRepository`: `JobExecution`, `StepExecution`, checkpoints, and restarts for the **Batch Job/Step**.

When the scheduler retries the entire process:

1. Identify the business key and semantically meaningful `JobParameters`.
2. Decide whether to **restart the same `JobInstance`** or create a new job instance. That depends on Spring Batch's **identifying parameters**, not merely the task name.
3. Inspect reader/writer checkpoints and transactions; already-committed steps may not need re-execution.
4. For writers targeting APIs, emails, or object storage, implement dedicated idempotency or compensation.
5. Verify whether a failed Batch job propagates to the Task exit code per your version's policy. For example, where supported: `spring.cloud.task.batch.fail-on-job-failure=true`.

Never treat `BatchStatus.COMPLETED` automatically as "the report was delivered to the partner". If notification happens outside the Job and fails, the overall task may still be incomplete.

## 15. Common Configuration Mistakes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Two Jobs for the same period run concurrently | `Allow`, duplicate CronJobs, or manual trigger | Choose the right policy; add business/database locks |
| Chose `Forbid` yet an hour of data is missing | Occurrence skipped while previous Job was active | Maintain a backlog/ledger and catch-up mechanism |
| `Replace` results in new report being overwritten | Old Task stopped slowly without fencing/versioning | Use atomic publish, fencing tokens, unique constraints |
| Job terminated after 30 minutes | `activeDeadlineSeconds` reached | Inspect logs, runtime, and business state; optimize or tune deadline |
| No Job created during controller slowdown | `startingDeadlineSeconds` exceeded or broken schedule | Monitor missed occurrences, fix scheduler, backfill |
| More attempts than expected | Stacked retries across client, Batch, Job, and scheduler | Calculate total retry budget; remove redundant retries |
| Re-run writes duplicate reports | Missing business key / unique constraint | Design idempotency and reconciliation |
| `END_TIME IS NULL` while Job is Failed | JVM killed or JDBC update failed | Reconcile Job/Pod, logs, DB, and output state |
| Same cron fires at wrong hour | Timezone or cron syntax mismatch | Declare timezone explicitly and test in target environment |
| Scheduled Task JVM never exits | Web server or non-daemon threads stay alive, or long-lived design | Use non-web app; ensure runner completes and resources close |

## 16. Production Scheduling Checklist

- [ ] Define the **business key** per period and clarify when independent periods may run in parallel.
- [ ] Choose the overlap policy (`Allow`/`Forbid`/`Replace` or equivalent) based on business impact, not mere convenience.
- [ ] Have a recovery plan for **missed occurrences** whenever losing a period is unacceptable.
- [ ] Declare cron syntax and timezone for the actual scheduler; test DST if applicable.
- [ ] Separate `startingDeadline`, Job active deadline, API timeouts, and business SLAs.
- [ ] Set a cross-layer retry budget; classify retryable errors, config errors, and `UNKNOWN` outcomes.
- [ ] Enforce unique/idempotency keys at the target business store, even when `Forbid` is set.
- [ ] Configure shutdown/timeout handling, resource requests/limits, and diagnostic logs.
- [ ] Use a durable JDBC `TaskRepository` when execution history must persist.
- [ ] Reconcile scheduler/runtime state, `TaskExecution`, Batch `JobExecution` (if any), and business outputs.
- [ ] Alert on missed schedules, unexpected overlaps, timeouts, exhausted retries, or missing metadata.
- [ ] Test network drops around `COMMIT`, Pod kills after commit, and multiple launches with the same key.
- [ ] Ensure secrets and sensitive data never appear in args, logs, or metadata.

## 17. Exercises and Self-Check Questions

**Question 1.** A CronJob runs every 15 minutes, while each execution takes 25 minutes. Compare the consequences of `Allow`, `Forbid`, and `Replace`. Choose a solution when **no period may be lost**.

**Question 2.** Why does `startingDeadlineSeconds: 600` not mean the process is allowed to run for up to 600 seconds?

**Question 3.** A Kubernetes CronJob uses `concurrencyPolicy: Forbid`. Someone still launches a manual Job with the same inputs. What can happen, and what protection layer is needed?

**Question 4.** A Job times out right after an SQL `COMMIT`. Can you conclude the data rolled back? Why or why not?

**Question 5.** If Job retries are already configured in Kubernetes, why should a REST caller not automatically resend launch requests indefinitely?

**Question 6.** When `END_TIME IS NULL` yet the Pod was `OOMKilled`, what evidence would you gather before deciding to retry?

**Exercise A — Choosing policies.** Given three workloads—cache sync needing only the latest snapshot, invoice generation forbidding duplicates, and independent partition processing—select an overlap policy and explain database or target-system protections.

**Exercise B — CronJob YAML.** Update the Section 7 example to an every-30-minutes schedule with appropriate deadlines and retry budget. Explain how many occurrences could be skipped when each run takes 45 minutes.

**Exercise C — Backlog.** Design a `scheduled_work` table and claim flow ensuring every due period gets processed even when `Forbid` skips cron ticks. Include lease timeouts and unique keys.

**Exercise D — Fault injection.** In a test environment, simulate a Job terminated after writing business results but before updating `TaskRepository`. Re-run with the same business key and verify business data is not duplicated.

**Exercise E — Budget.** Build a spreadsheet/table calculating total upstream calls across retries in the HTTP client, Spring Batch, Kubernetes Job, and scheduler. Recommend which layer(s) should retain retries and SLA bounds.

## 18. Key Takeaways

- **Schedules live in the scheduler/deployer; Spring Cloud Task tracks a single finite execution.**
- **`Allow`** permits overlapping Jobs, **`Forbid`** prevents overlaps for one CronJob but can skip occurrences, and **`Replace`** attempts to replace the old Job without undoing prior side effects.
- `startingDeadlineSeconds` bounds **start delay**; `activeDeadlineSeconds` bounds **Job duration**; API/DB timeouts and business SLAs are separate scopes.
- Retries require an **overall budget**, backoff/jitter, and failure classification. Timeouts or disconnects around `COMMIT` leave outcomes **indeterminate (`UNKNOWN`)**.
- `TaskExecution` helps trace timestamps and exit codes, yet **is insufficient to prove** all periods ran or no duplicates occurred.
- When missing a schedule is unacceptable, store occurrences in a **durable backlog/ledger** and reuse a fixed business key across attempts.
- When integrating with Spring Batch, reconcile `JobExecution`/`StepExecution` and business outputs as well, not just process exit codes.

## References

- [Kubernetes — CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/): `schedule`, `timeZone`, `concurrencyPolicy`, `startingDeadlineSeconds`, and missed schedules.
- [Kubernetes — Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/): `backoffLimit`, `activeDeadlineSeconds`, `parallelism`, and handling Pod failures.
- [Kubernetes — Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): Pod termination, termination signals, and grace periods.
- [Spring Cloud Task — Features](https://docs.spring.io/spring-cloud-task/reference/features.html): `TaskExecution`, `TaskRepository`, lifecycle, and error handling.
- [Spring Cloud Data Flow — Task Scheduling](https://docs.spring.io/spring-cloud-dataflow/reference/feature-guides/batch/scheduling.html): scheduling tasks on supported platforms.
- [Spring Batch — Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): chunk/step retries and transaction coordination.

**Version note:** Kubernetes fields and scheduler APIs must be verified against your actual cluster and deployer; the Java and SQL configurations in this lesson are illustrative and do not replace integration testing against your project's versions of Spring Boot, Spring Cloud Task, Spring Batch, JDBC driver, and database.
