# Kubernetes CronJob and Per-Run Parameters

**Spring Cloud Task** is used to build Spring Boot applications with a finite runtime: the process starts, accepts parameters, runs business logic, records `TaskExecution` in `TaskRepository`, and then exits. When you want to run a task daily, hourly, or periodically in Kubernetes, you can use a **CronJob** as the scheduler for **Kubernetes Jobs** that create Pods running the application.

This lesson is part of the **Scheduling** chapter. The central theme is that **the CronJob decides when to request an execution, while per-run parameters decide which data gets processed**. The running example is `daily-invoice-report-task`, which generates an invoice report for the *previous business day* in the `Asia/Ho_Chi_Minh` timezone. We will configure the CronJob, pass and validate parameters, handle retries and backfills, prevent duplicates, and reconcile Kubernetes results with Spring Cloud Task.

> **Principle:** A Kubernetes CronJob does not record `TaskExecution` on its own; Spring Cloud Task does not schedule Kubernetes Jobs. The CronJob creates Jobs/Pods, and the Java process inside each Pod records Task metadata and executes business logic.

## 1. Relationship Between CronJob, Job, Pod, and TaskExecution

~~~mermaid
flowchart TD
  C["CronJob: 02:00 daily"] --> J1["Kubernetes Job period A"]
  C --> J2["Kubernetes Job period B"]
  J1 --> P1["Pod attempt 1"]
  J1 --> P2["Pod retry on failure"]
  J2 --> P3["Pod period B"]
  P1 --> T1["Spring Cloud Task / TaskExecution #1"]
  P2 --> T2["Spring Cloud Task / TaskExecution #2"]
  P3 --> T3["Spring Cloud Task / TaskExecution #3"]
  T1 --> R[("TaskRepository")]
  T2 --> R
  T3 --> R
  T1 --> D[("Business data")]
  T2 --> D
  T3 --> D
~~~

| Component | Primary Responsibility | Do Not Confuse With |
| --- | --- | --- |
| **CronJob** | Evaluates the schedule and creates Kubernetes Jobs from a template | A single business execution |
| **Kubernetes Job** | Tracks completion, Pod retries, and Job deadlines | Spring Batch's `JobExecution` |
| **Pod/Container** | Runs the Java image, receives `args` and `env`, writes logs | A single data period |
| **Spring Cloud Task** | Records `TaskExecution`: name, timestamps, arguments, exit code | A scheduler or deduplication lock |
| **Spring Batch** (if used) | `JobInstance`, `JobExecution`, `StepExecution`, checkpoints | Kubernetes Job |
| **Business logic** | Resolves `businessDate`, tenant, outputs, idempotency | TaskExecution ID |

A single Kubernetes Job may **attempt multiple Pods** if an earlier attempt fails. Each Task process that boots far enough normally receives **its own TaskExecution ID**. Conversely, a Pod that fails during image pull or Spring context startup may **leave behind no TaskExecution**. Therefore, never assume a strict 1:1:1 mapping ("one schedule tick = one Job = one TaskExecution").

### 1.1. Why Not Use `@Scheduled` Inside the Task?

Spring's `@Scheduled` typically runs inside a **long-lived** application waiting for scheduled ticks. A Spring Cloud Task architecture with CronJob creates **a new process, executes exactly one unit of work, and exits**. There is no reason to enable `@Scheduled` inside the app while also launching it via CronJob, as that creates two unnecessary scheduling layers.

## 2. Sample CronJob Manifest

The following manifest illustrates a task running at **02:00 daily in Vietnam**. It assumes namespace `batch-jobs`, ServiceAccount `invoice-task`, Secret `invoice-task-db`, the container image, and the TaskRepository tables are already prepared.

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-invoice-report
  namespace: batch-jobs
spec:
  schedule: "0 2 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 1800
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  suspend: false
  jobTemplate:
    spec:
      backoffLimit: 2
      activeDeadlineSeconds: 3600
      template:
        spec:
          serviceAccountName: invoice-task
          restartPolicy: Never
          containers:
            - name: task
              image: registry.example.com/batch/daily-invoice-report-task:1.0.0
              imagePullPolicy: IfNotPresent
              args:
                - "--business-zone=Asia/Ho_Chi_Minh"
              env:
                - name: TASK_DB_URL
                  valueFrom:
                    secretKeyRef:
                      name: invoice-task-db
                      key: jdbc-url
                - name: TASK_DB_USER
                  valueFrom:
                    secretKeyRef:
                      name: invoice-task-db
                      key: username
                - name: TASK_DB_PASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: invoice-task-db
                      key: password
              resources:
                requests:
                  cpu: "250m"
                  memory: "512Mi"
                limits:
                  memory: "1Gi"
~~~

This is an **example**, not a live deployed resource. The image needs an `ENTRYPOINT` that launches Spring Boot and forwards `args` to `main(String[] args)`. If the image lacks a suitable entrypoint, declare `command` and `args` accordingly. In Kubernetes, `args` overrides the image's `CMD` arguments, not necessarily the full entrypoint command.

### 2.1. Meaning of Key Fields

| Field | Purpose | Risks to Watch |
| --- | --- | --- |
| `schedule: "0 2 * * *"` | **5-field** cron: minute, hour, day-of-month, month, day-of-week | Not the 6-field cron used by some Java libraries |
| `timeZone` | Timezone Kubernetes uses to interpret the schedule | Use an IANA name; do not embed `TZ` or `CRON_TZ` in `schedule` |
| `concurrencyPolicy: Forbid` | Prevents overlapping Jobs of the **same CronJob** | Can skip a period if the previous Job runs too long |
| `startingDeadlineSeconds: 1800` | Maximum late-start window of 30 minutes | Not a runtime limit for the Job |
| `backoffLimit: 2` | Maximum Pod retries managed by the Job controller | Retries can create new TaskExecutions |
| `activeDeadlineSeconds: 3600` | Maximum active duration of the Job | May be killed before Task writes end metadata |
| `restartPolicy: Never` | Failed Pod will not restart containers inside the same Pod | Job controller can still spawn a replacement Pod |
| `successfulJobsHistoryLimit` / `failedJobsHistoryLimit` | Number of finished Jobs retained in Kubernetes | **Does not** purge TaskRepository records |
| `args` | Startup arguments passed to the application | Static in the template—**identical across all runs** |
| `env` | Container/process configuration | Not automatically saved in `TaskExecution.arguments` |

`timeZone` graduated to stable in **Kubernetes v1.27**. On older clusters, verify API support for your version. Trigger timestamps are evaluated on the control plane, independent of the timezone on a laptop running `kubectl`.

### 2.2. Corresponding Spring Boot Configuration

Inside the image, the application can use:

~~~yaml
spring:
  application:
    name: daily-invoice-report-task
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
  cloud:
    task:
      initialize-enabled: false
~~~

Setting `initialize-enabled=false` assumes the TaskRepository tables were already created via migrations matching your DBMS and Spring Cloud Task version. Appropriate JDBC drivers, database permissions, and infrastructure config are required. If the app defines multiple DataSources, explicitly designate which DataSource backs TaskRepository.

## 3. Understanding What "Per-Run Parameters" Means

Three categories of values typically appear in a Task:

| Category | Examples | Scope |
| --- | --- | --- |
| **Deployment configuration** | DB URL, username, password, image, memory | One deployment/environment |
| **Job parameters** | `--business-date`, `--tenant-id`, `--source-id`, `--report-version` | One logical data period |
| **Technical attempt IDs** | Kubernetes Job UID, Pod UID, TaskExecution ID | One concrete Job/Pod/process |

Example of two reporting dates:

~~~text
Logical run A: tenantId=acme, businessDate=2026-11-23
Logical run B: tenantId=acme, businessDate=2026-11-24
~~~

If logical run A retries across three Pods, **the business date must remain 2026-11-23** on all three. TaskExecution IDs may differ, yet the business key must stay constant.

Command-line arguments are persisted by Spring Cloud Task in `TaskExecution.arguments` via `TaskRepository`, typically in `TASK_EXECUTION_PARAMS`. Values supplied only via environment variables or **computed after startup** do not automatically appear in saved arguments. For auditability, record the resolved business date in structured logs or a business table, and never pass secrets in arguments.

## 4. The Biggest Trap: CronJob Does Not Auto-Advance `businessDate`

Suppose you write:

~~~yaml
args:
  - "--business-date=2026-11-23"
~~~

Kubernetes will pass the **exact literal 2026-11-23 to every Job** created from this template until the manifest is edited. It **does not increment the date**. Neither of the following strings is interpolated automatically either:

~~~yaml
# Wrong if expecting Kubernetes to compute the date automatically:
args:
  - "--business-date=${YESTERDAY}"
  - "--business-date={{ yesterday }}"
~~~

CronJob has no built-in `YESTERDAY` variable, does not invoke a shell to evaluate `{{ yesterday }}`, and placing strings in `args` does not turn them into date expressions. The `$(NAME)` syntax only references an already-defined env var in supported contexts; it never computes "yesterday".

There are two main strategies:

1. **Application resolves the date itself** from an agreed `ZoneId` and the runtime clock. Simple, but sensitive to delayed starts or retries crossing midnight.
2. **An orchestrator fixes `businessDate` before creating the Job** and passes an immutable value. Better suited for backfills, long retries, or auditing a specific data period.

## 5. Approach A: Application Computes the Date at Runtime

With a daily 02:00 schedule in `Asia/Ho_Chi_Minh`, the common rule is **process yesterday's local date**. For the 2026-11-24 02:00 tick, the target date is 2026-11-23.

This Spring Boot example accepts `--business-date` when provided; otherwise it computes yesterday in the selected timezone. Injecting `Clock` makes testing straightforward and avoids relying on the container's default timezone.

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class DailyInvoiceReportTaskApplication {

    public static void main(String[] args) {
        SpringApplication.run(DailyInvoiceReportTaskApplication.class, args);
    }

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    ApplicationRunner runReport(ReportService service, Clock clock) {
        return args -> {
            ZoneId zone = ZoneId.of(
                    option(args, "business-zone", "Asia/Ho_Chi_Minh"));
            String explicit = option(args, "business-date", null);
            LocalDate date = explicit == null
                    ? LocalDate.now(clock.withZone(zone)).minusDays(1)
                    : LocalDate.parse(explicit);

            service.generateFor(date); // Synchronous until completion.
        };
    }

    private static String option(
            ApplicationArguments args, String key, String fallback) {
        if (!args.containsOption(key)) {
            return fallback;
        }
        List<String> values = args.getOptionValues(key);
        if (values == null || values.size() != 1
                || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Expected exactly one --" + key + "=value");
        }
        return values.get(0);
    }
}

interface ReportService {
    void generateFor(LocalDate businessDate);
}
~~~

This code is an **illustrative skeleton**; it still needs a `ReportService` bean, migrations, date validation, transactions, and idempotency. The runner must block until work completes. If it only submits a `Future` and returns, the Task/Pod can exit while processing is still incomplete.

### 5.1. Limitations of Computing from the Pod's Clock

~~~text
Scheduled Cron time:  2026-11-24 02:00
Period to process:    2026-11-23

Delayed catch-up Job: 2026-11-26 08:00
"Yesterday" then:     2026-11-25  ← wrong target period
~~~

When a Pod starts late due to control plane delays, resource exhaustion, or retries crossing midnight, `LocalDate.now(...).minusDays(1)` can shift between retry attempts of **the same Job**. That is especially dangerous if the first attempt already committed partial data.

Hence, Approach A is only suitable if latency is tightly controlled and that risk is acceptable or mitigated. For critical data, **pin the exact date** before any attempt begins.

## 6. Approach B: Pin the Date Before Passing It into the Job

A stronger design uses a **launcher/orchestrator** to determine the business period from the scheduled timestamp and then create a Kubernetes Job with fixed arguments:

~~~text
scheduledAt  = 2026-11-24T02:00:00+07:00
businessDate = 2026-11-23

args:
  --business-date=2026-11-23
  --business-zone=Asia/Ho_Chi_Minh
~~~

When that Job retries, the replacement Pod receives the **exact same Pod template and args** from the Job. It no longer has to infer "yesterday" from the retry Pod's clock.

~~~mermaid
flowchart LR
  S["Schedule tick 24/11 02:00 +07"] --> C["Compute businessDate = 23/11"]
  C --> J["Create Kubernetes Job with fixed args"]
  J --> P1["Pod attempt #1"]
  J --> P2["Pod retry #2"]
  P1 --> B[("Same businessKey")]
  P2 --> B
~~~

A static CronJob YAML **does not dynamically render** `businessDate` per tick. If you want to keep CronJob as the trigger, the CronJob can run a short-lived *launcher container*; the launcher reads the scheduled timestamp, computes `businessDate`, and calls the Kubernetes API to create the worker Job. This requires designing RBAC, launcher deduplication, and Job status tracking. Alternatively, a workflow engine or external scheduler can create Jobs with explicit dates.

### 6.1. Scheduled Timestamp Annotation Since Kubernetes v1.32

Starting in **Kubernetes v1.32**, the CronJob controller attaches an annotation to Jobs created from a CronJob:

~~~text
batch.kubernetes.io/cronjob-scheduled-timestamp
~~~

Its value is the expected scheduled time in RFC3339 format, such as `2026-11-24T02:00:00+07:00`. Because this is the **scheduled time**, it remains accurate even if the Job was created late. It can be converted like this:

~~~java
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;

OffsetDateTime scheduledAt =
        OffsetDateTime.parse("2026-11-24T02:00:00+07:00");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

LocalDate businessDate =
        scheduledAt.atZoneSameInstant(zone).toLocalDate().minusDays(1);
~~~

**Note:** the annotation lives in the **Kubernetes Job's metadata**; it does not automatically appear as an environment variable inside the Pod. To expose it to the application, add an explicit delivery mechanism—such as a launcher querying the Job API, a controller/injector, or a minimal-RBAC side/init step. Never assume a container has a `SCHEDULED_AT` variable unless you configured one.

For manual backfills, you still must provide an explicit `scheduledAt` or `businessDate`. A manually created Job's timestamps do not automatically carry an annotation matching the historical business period you intend to process.

## 7. Timezones and Data Boundaries

~~~yaml
spec:
  schedule: "0 2 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
~~~

CronJob interprets 02:00 using the specified IANA timezone. Simultaneously, business code must determine the **data date** using the corresponding timezone; never trust the JVM's default timezone to match the Kubernetes CronJob's timezone.

For data stored with UTC timestamps, use a **half-open** interval `[start, end)`:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate date = LocalDate.parse("2026-11-23");

Instant start = date.atStartOfDay(zone).toInstant();
Instant end = date.plusDays(1).atStartOfDay(zone).toInstant();
// WHERE occurred_at >= start AND occurred_at < end
~~~

`Instant` is imported from `java.time.Instant`. In DST-observing timezones, a local calendar day can last **23 or 25 hours**; never replace `end` with `start.plus(Duration.ofHours(24))`. During DST transitions, a scheduled Cron wall-clock time may not exist or may occur twice, requiring explicit period-determination and missed-schedule policies.

### 7.1. `startingDeadlineSeconds` Is Not the Task Timeout

`startingDeadlineSeconds` is the maximum allowed **start delay** after the scheduled time. If exceeded, a scheduled run can be skipped; it **does not cap Job execution time**. Job runtime limits are controlled by `activeDeadlineSeconds`.

Kubernetes docs note that setting `startingDeadlineSeconds` below **10 seconds** may prevent a CronJob from being scheduled because the controller checks schedules periodically. Furthermore, multiple missed ticks do not mean the controller will catch up **all** of them automatically; you still need period tracking and a separate backfill process.

## 8. Overlapping Runs: `Allow`, `Forbid`, `Replace`

| `concurrencyPolicy` | When a New Tick Arrives While an Old Job Is Active | What to Prepare |
| --- | --- | --- |
| **Allow** (default) | Permits overlapping Jobs from consecutive ticks | Business locks/idempotency when touching the same data |
| **Forbid** | Skips launching a new run of the **same CronJob** while the old Job runs | Monitoring for skipped periods; backfill |
| **Replace** | Terminates the active Job and replaces it with the new Job | Recovery for abruptly stopped Jobs; guard against partial writes |

`Forbid` applies **only to Jobs created by the same CronJob**. A second CronJob, a manual Job, or an API-launched Task can still process the same data simultaneously. Cross-source concurrency limits require locking outside the CronJob.

Spring Cloud Task offers `spring.cloud.task.single-instance-enabled` when configured with a suitable lock backend; it locks by **Task name**, not by `(tenant, businessDate)`. To allow different tenants to run concurrently while blocking duplicate `(tenant, date)` work, use a **unique constraint or distributed business-key lock**.

**CronJob does not guarantee exactly-once execution.** As noted in Kubernetes docs, under certain circumstances two Jobs may be created for one tick, or none at all; applications must therefore be **idempotent**.

## 9. Retries, Exit Codes, and TaskExecution

With:

~~~yaml
jobTemplate:
  spec:
    backoffLimit: 2
    template:
      spec:
        restartPolicy: Never
~~~

When a container exits with an error, the Job controller can spawn a new Pod to retry. `restartPolicy: Never` prevents restarting the container in-place inside the same Pod; the Job controller manages retries according to `backoffLimit` and other rules. With `restartPolicy: OnFailure`, the container can restart inside the existing Pod.

Illustrative example:

~~~text
Kubernetes Job for reporting period 2026-11-23
  Pod attempt #1 → TaskExecution 4101, exitCode=1
  Pod attempt #2 → TaskExecution 4102, exitCode=1
  Pod attempt #3 → TaskExecution 4103, exitCode=0
~~~

This is **not a guarantee of exactly three Pods or TaskExecutions** when `backoffLimit=2`: retry accounting depends on multiple conditions, and a Pod can fail before Spring Cloud Task ever writes a TaskExecution.

### 9.1. Propagating Errors Out of the Application

Never catch an exception just to log it:

~~~java
try {
    service.generateFor(businessDate);
} catch (Exception ex) {
    log.error("Could not generate report", ex);
    // Wrong if the runner then returns normally.
}
~~~

If the runner returns normally, the process can exit with code `0`, causing Kubernetes to mark the Job `Complete` despite a broken report. Either let the exception propagate or explicitly map the failure to a non-zero exit code.

When running **Spring Batch** inside a Task, verify whether a failed `JobExecution` actually forces the Task/process to exit non-zero. You can enable `spring.cloud.task.batch.fail-on-job-failure=true` on supporting integration versions, or check `JobExecution` status explicitly in your launcher.

### 9.2. Killed Pods

If a Pod is killed by OOM, node failure, or `activeDeadlineSeconds`, Spring Cloud Task's shutdown listener may never execute. A row with a null `TASK_EXECUTION.END_TIME` does not prove the process is still alive. Always cross-check against Kubernetes Job/Pod status and system logs.

## 10. Business Keys and Idempotency Across Attempts

A report may be triggered by a CronJob, manual run, retry, or backfill. All of them must share one logical key:

~~~text
businessKey = (tenantId, businessDate, reportVersion)
~~~

Example PostgreSQL table:

~~~sql
CREATE TABLE report_run (
    tenant_id       varchar(100) NOT NULL,
    business_date   date NOT NULL,
    report_version  integer NOT NULL,
    status          varchar(30) NOT NULL,
    artifact_uri    text,
    updated_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, business_date, report_version)
);
~~~

Creating a claim for the business key:

~~~sql
INSERT INTO report_run
    (tenant_id, business_date, report_version, status)
VALUES
    (:tenant_id, :business_date, :report_version, 'RUNNING')
ON CONFLICT (tenant_id, business_date, report_version)
DO NOTHING;
~~~

`ON CONFLICT DO NOTHING` is only **the first step**. When the row already exists, the application must inspect `status`: skip if completed, reject/wait if running, or follow a safe takeover rule if failed. When using leases or timeouts, include an owner token/fencing check so an old stalled process cannot overwrite results after losing ownership.

For side effects outside the database—such as sending emails, publishing events, or writing files to object storage—use an **idempotency key**, immutable artifact names, an outbox pattern, or equivalent safeguards. A unique constraint on the report table alone does not prevent an email from being sent twice.

| ID | Example | What Is It Used For? |
| --- | --- | --- |
| Kubernetes Job UID | API-assigned UID | Technical Job tracking |
| Pod UID | UID of a single Pod | Investigating container attempts |
| TaskExecution ID | `4103` | Spring Cloud Task history |
| Spring Batch JobInstance | Job name + identifying JobParameters | Batch restart/checkpointing |
| Business key | `acme, 2026-11-23, v1` | Protecting logical data output |

Never use TaskExecution ID for deduplication: every technical retry may receive a new ID while sharing **the same business key**.

## 11. Manual Runs and Backfills

Kubernetes command to spawn a Job from a CronJob:

~~~bash
kubectl create job \
  --from=cronjob/daily-invoice-report \
  manual-invoice-report \
  -n batch-jobs
~~~

This command **copies the Job template**, including its current `args`. It **does not** infer a new date from the Job name, nor does it know which historical period a manual Job is meant to cover.

When backfilling a specific date, create a **dedicated Job manifest** or have your launcher spawn a Job with a pinned `--business-date`:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: manual-invoice-report-20261123
  namespace: batch-jobs
spec:
  backoffLimit: 1
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: task
          image: registry.example.com/batch/daily-invoice-report-task:1.0.0
          args:
            - "--business-date=2026-11-23"
            - "--business-zone=Asia/Ho_Chi_Minh"
          envFrom:
            - secretRef:
                name: invoice-task-runtime
~~~

This example assumes Secret `invoice-task-runtime` contains the proper `TASK_DB_*` variables, plus valid image, pull permissions, and deployment settings. Never put passwords in `args` or commit plaintext Secrets. Manually triggered Jobs should follow an **approval/reconciliation process** to avoid re-issuing an already completed date.

## 12. Observing Three Data Sources

### 12.1. Observing Kubernetes

~~~bash
kubectl get cronjobs -n batch-jobs
kubectl describe cronjob daily-invoice-report -n batch-jobs
kubectl get jobs -n batch-jobs
kubectl describe job ACTUAL_JOB_NAME -n batch-jobs
kubectl get pods -n batch-jobs \
  -l batch.kubernetes.io/job-name=ACTUAL_JOB_NAME
kubectl logs -n batch-jobs job/ACTUAL_JOB_NAME
kubectl get events -n batch-jobs --sort-by=.lastTimestamp
~~~

Replace `ACTUAL_JOB_NAME` with the actual Kubernetes Job name. If retries created multiple Pods, inspect logs for **every Pod**, not just a single `kubectl logs job/...` command. Once Jobs/Pods are garbage-collected, use your centralized logging platform.

### 12.2. Observing TaskRepository

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE,
       EXIT_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'daily-invoice-report-task'
ORDER BY START_TIME DESC;
~~~

TaskExecution stores application-level status, not Kubernetes controller state. To correlate the two layers, attach non-sensitive correlation IDs such as **Job name/UID or Pod name** in logs or business metadata. Pod name is not automatically injected as `POD_NAME`; you can expose it via the **Downward API**:

~~~yaml
env:
  - name: POD_NAME
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
~~~

This is a container snippet to merge into the Pod spec, not a standalone CronJob manifest. Pod name is **not a business key**, because retries create new Pods.

### 12.3. Troubleshooting Symptoms

| Symptom | Where to Check |
| --- | --- |
| CronJob does not create Jobs | `suspend`, `schedule`/`timeZone`, deadlines, controller events |
| Job exists but no Pod runs | Scheduler, quotas, image pull, RBAC/admission |
| Pod runs but no TaskExecution appears | App crashed before Task lifecycle started, wrong datasource/schema |
| Job `Complete` but data is missing | Runner swallowed exception, missing output reconciliation |
| `END_TIME` is null | Process still running or died abruptly |
| Same date processed twice | Retries, duplicate CronJobs, manual Job, missing business lock |
| Wrong date after retry | App computed "yesterday" from Pod clock instead of pinned date |
| `Forbid` causes skipped periods | Previous Job ran too long; new tick skipped |
| Schedule fires at wrong hour | `timeZone`, DST, inconsistent internal app timezone |
| Batch Job `FAILED` while Pod `Complete` | Batch failure not propagated to process exit code |

`successfulJobsHistoryLimit` and `failedJobsHistoryLimit` only control how many **finished Kubernetes Jobs** are retained. If `ttlSecondsAfterFinished` is set, Kubernetes can also clean up Jobs/Pods by TTL. Neither setting **replaces retention policies** in TaskRepository or Spring Batch JobRepository.

## 13. Suspending, Rescheduling, and Backfilling

To prevent creating Jobs on upcoming ticks:

~~~yaml
spec:
  suspend: true
~~~

`suspend: true` **does not stop** Jobs that have already started. When unsuspending, missed ticks can affect how the controller catches up depending on `startingDeadlineSeconds` and missed-schedule rules. Never assume every skipped day will automatically backfill; maintain a reconciliation table of **processed business dates**.

Updating `jobTemplate` (image, args, env) applies only to **Jobs created after the update**. Already-running Jobs/Pods are not retroactively changed. Use immutable image tags and manage schedule/parameter updates through controlled changes.

When changing a schedule from 02:00 to 01:00, do not silently alter the reporting-date rule. The schedule defines **when to run**; `businessDate` defines **which data belongs to the run**.

## 14. Practice Exercises

Suppose a system has two tasks: `orders-import-task` importing orders at 01:30 and `daily-invoice-report-task` generating reports at 02:00 in `Asia/Ho_Chi_Minh`.

1. Write two CronJobs specifying `concurrencyPolicy`, deadlines, retries, and resource limits. Explain why `Forbid` on the report CronJob does not block the orders-import Job.
2. Inject DB credentials via a Secret rather than command-line arguments.
3. Use a fixed `Clock` to test the "previous day" formula for the 2026-11-24 trigger; then simulate a delayed Job starting on 2026-11-26.
4. Design a launcher passing `--business-date=2026-11-23` to a Job; simulate a retry past midnight and verify every Pod receives the same date.
5. Explain the `batch.kubernetes.io/cronjob-scheduled-timestamp` annotation and how to pass its value to the app **without assuming it is automatically in Pod env**.
6. Have a Pod return a non-zero exit code, inspect `kubectl get jobs/pods`, and reconcile with TaskExecution. Also test an abrupt process kill.
7. Use the unique key `(tenantId, businessDate, reportVersion)` to guard against duplicate publishing during manual re-runs.
8. Suspend the schedule, let two ticks pass, re-enable it, and identify the missing dates to backfill using dedicated Job manifests.

**Completion criteria:** accurately explain **CronJob → Kubernetes Job → Pod → TaskExecution**, recognize that CronJob `args` are static, distinguish *scheduled time* from *actual start time*, and preserve `businessDate` across retries and backfills.

## 15. Conclusion

- CronJob **schedules**, Kubernetes Job **manages Pods/retries**, Spring Cloud Task **tracks execution**, and business code **manages outputs and business keys**.
- `schedule` is a 5-field cron expression; `timeZone` governs schedule evaluation. JVM timezone does not override CronJob `timeZone`.
- `args` in `jobTemplate` **do not compute per-run values automatically**. Never hardcode a date expecting Kubernetes to advance it.
- Computing `LocalDate.now().minusDays(1)` inside a Pod is simple yet **fragile across retries or multi-day backfills**; the reliable solution is passing a pinned `businessDate`.
- Kubernetes v1.32+ attaches a scheduled-timestamp annotation to Jobs, though applications still need an explicit mechanism to read or pass it.
- `Forbid`, `Allow`, and `Replace` only govern overlap **for a single CronJob**; they do not guarantee exactly-once execution.
- `startingDeadlineSeconds` bounds **start delay**, `activeDeadlineSeconds` bounds **Job runtime**, and `backoffLimit` governs **retries**.
- One Job can correspond to multiple Pods/TaskExecutions. **TaskExecution ID is not a business key**; idempotency is mandatory.
- When investigating issues, inspect **Kubernetes Job/Pod, TaskRepository, and business result tables** together; manage retention, secrets, and backfill workflows separately.

### References

- [Kubernetes — CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
- [Kubernetes — Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/)
- [Kubernetes API — CronJobSpec](https://kubernetes.io/docs/reference/kubernetes-api/batch/cron-job-v1/)
- [Kubernetes — Well-Known Labels and Annotations](https://kubernetes.io/docs/reference/labels-annotations-taints/)
- [Spring Cloud Task — Features and TaskRepository](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task — Spring Batch Integration](https://docs.spring.io/spring-cloud-task/reference/batch.html)
