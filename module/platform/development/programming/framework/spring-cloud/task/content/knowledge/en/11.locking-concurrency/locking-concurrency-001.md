# Multiple Executions with the Same Name and the Risk of Overlapping Runs

## 1. The Problem: One Task Name, Multiple Runs

**Spring Cloud Task** helps build Spring Boot applications with a **finite runtime**: receive parameters, perform work, record metadata in **TaskRepository**, and then terminate. A task such as `daily-reconciliation` can be invoked by a nightly schedule, a manual action from an administrator, an API request, or a retry mechanism.

**The task name is not the identifier of a single run.** Each startup can create a different **TaskExecution** with its own `TASK_EXECUTION_ID`, even when `TASK_NAME` and command-line arguments are identical. When two processes of the same task run concurrently, we call that **overlapping execution**.

For example: the reconciliation task for `2026-11-23` takes 12 minutes, but the schedule triggers again after 10 minutes.

| Illustrative Timestamp | Process A | Process B |
| --- | --- | --- |
| 02:00 | Starts reconciliation for `2026-11-23` | Not running yet |
| 02:10 | Still updating data | Scheduler launches again for the same date |
| 02:11 | Updating order `#381` | Also updating order `#381` |
| 02:12 | Finishes | Still running |
| 02:22 | Stopped | Finishes with potentially duplicated or incorrect results |

**Risks:** two processes read the same initial data and then write results concurrently; one run overwrites newer data; the same report file is published twice; two emails are sent; the connection pool is overloaded; or two Batch jobs compete for resources.

This lesson in the **Locking and Concurrency** chapter helps you distinguish **multiple TaskExecutions**, **resource contention**, **locking by task name**, and **idempotency by business key**, enabling you to design scheduled or on-demand tasks safely.

### Learning Objectives

After this lesson, you will be able to:

1. Identify multiple executions that share the same `TASK_NAME` but have different `TASK_EXECUTION_ID` values.
2. Explain why `TaskRepository` records execution history without preventing overlapping runs by default.
3. Configure Spring Cloud Task's **single instance** restriction when genuinely needed.
4. Distinguish framework-level locking from Kubernetes CronJob `concurrencyPolicy` and business-level locking.
5. Choose strategies for concurrency control, retries, TTL, and recovery when a process is killed.
6. Practice launching two overlapping runs, reading logs, and cross-checking the database.

## 2. Do Not Confuse the Three Levels of Identity

In a system, the following three levels often coexist:

| Level | Example | Purpose |
| --- | --- | --- |
| **Task name** | `daily-reconciliation` | Identifies the application type; can be used as a single-instance lock key |
| **Task execution ID** | `1041`, `1042` | Identifies **a single run**; links logs, timestamps, and exit code |
| **Business key** | `tenantA:2026-11-23` | Identifies the **unit of data to process**; foundation for preventing duplicate side effects |

Suppose two runs both have `TASK_NAME=daily-reconciliation` and `--businessDate=2026-11-23`. TaskRepository can create two different execution IDs. This reflects two application startups; it **does not mean** that updating the same date twice is safe.

Conversely, two applications with **different task names** — `reconcile-fast` and `reconcile-manual` — can still process the same business key `tenantA:2026-11-23`. Locking by task name does not prevent two differently named tasks from contending over the same business data.

### Two Separate Questions to Answer

**Question A: Should two processes with the same name be allowed to run concurrently?** If not, you need an **overlap** control mechanism at the scheduler, runtime, or framework level.

**Question B: Should the same business unit of work be executed twice over time?** If not, you need **idempotency**, locks/unique constraints by business key, and reprocessing rules.

**Solving Question A alone does not automatically solve Question B.** Two tasks with the same name running *sequentially* do not overlap, yet they can still produce duplicate data.

## 3. How Does Spring Cloud Task Handle Multiple Runs by Default?

According to the Spring Cloud Task configuration documentation, the property:

`spring.cloud.task.single-instance-enabled`

has a **default value of `false`**. When the single-instance mechanism is not enabled, the framework does not use name-based locking to block another process with the same name. Each process can still record its own `TaskExecution` in TaskRepository if initialization succeeds and the database permits it.

~~~mermaid
sequenceDiagram
    participant S as Scheduler / API
    participant A as Task A (name=invoice-export)
    participant B as Task B (name=invoice-export)
    participant DB as TaskRepository

    S->>A: Run --businessDate=2026-11-23
    A->>DB: Record executionId=21
    A->>A: Export data
    S->>B: Run --businessDate=2026-11-23
    B->>DB: Record executionId=22
    B->>B: May export the same data
    A->>DB: Update result #21
    B->>DB: Update result #22
    Note over A,B: Two separate IDs do not mean no business contention
~~~

**TaskRepository is a history store, not a default business synchronization mechanism.** Queries such as "find a running TaskExecution" should not be used as a homegrown distributed lock: between the read and the write, another process can still start. This is a **check-then-act race condition** bug.

~~~text
Process A: SELECT -> sees no one running yet
Process B: SELECT -> sees no one running yet
Process A: starts processing
Process B: starts processing
~~~

To prevent overlap across multiple processes, "checking and acquiring the right to run" must rely on a reliable **synchronized/atomic** mechanism.

## 4. Spring Cloud Task Single-Instance Lock

Spring Cloud Task provides a feature to **restrict to a single instance per task name**. When runs are properly configured, share the same lock store, and a task with the same name already holds the lock, a competing launch is rejected instead of processing business logic concurrently.

### 4.1. Enabling the Configuration

Example `application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  cloud:
    task:
      name: daily-reconciliation
      single-instance-enabled: true
~~~

Or pass it at startup:

~~~bash
java -jar reconciliation-task.jar --spring.cloud.task.single-instance-enabled=true
~~~

**Important conditions:**

- Every process to be controlled must have the **same task name** configured via `spring.cloud.task.name` or a `TaskNameResolver` mechanism, and **all must enable** `single-instance-enabled=true`.
- They must use the **same JDBC lock store** accessible to Spring Cloud Task/Spring Integration; two applications pointing to different databases cannot use database locks to coordinate with each other.
- The lock schema, DataSource, transactions, and appropriate database permissions must be in place. Enabling a single YAML line is **not enough** if the classpath or SQL tables are missing.
- The lock operates by **task name**; it does not automatically distinguish `businessDate`, `tenantId`, or other per-run arguments.

The Spring Cloud Task documentation requires adding Spring Integration dependencies for this feature:

~~~xml
<!-- Excerpt of pom.xml, version managed by a compatible BOM -->
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-core</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jdbc</artifactId>
</dependency>
~~~

These dependencies **supplement** the Spring Cloud Task dependency and the JDBC driver you are using. Choose a BOM/version compatible with your project's Spring Boot version; do not blindly copy a hardcoded library version without verification.

### 4.2. Two Competing Runs

~~~mermaid
sequenceDiagram
    participant A as Process A
    participant DB as JDBC Lock Store
    participant B as Process B
    participant W as Business Processing

    A->>DB: Request lock name=daily-reconciliation
    DB-->>A: Lock acquired successfully
    A->>W: Execute
    B->>DB: Request same lock by task name
    DB-->>B: Lock is currently held
    B--xB: TaskExecutionException / startup failure
    A->>W: Complete
    A->>DB: Release lock on normal termination
~~~

According to the Spring Cloud Task documentation, if a task with the same name is already running with this feature enabled, another invocation **fails** with a message like:

~~~text
Task with name "daily-reconciliation" is already running.
~~~

The documentation also notes process exit code **`1`** for the rejected run in standard contention cases. This is a **contention failure signal**, not an instruction to automatically queue and retry later.

A point requiring caution: a rejected process **has not necessarily created a complete `TaskExecution` record**. Depending on which startup step failed, you may only see the error in logs and the process exit status. Therefore, you must observe **both the launch infrastructure and TaskRepository**, rather than relying on the number of database rows to count every rejected launch request.

### 4.3. The TASK_LOCK Table

The Spring Cloud Task schema includes the **`TASK_LOCK`** table to support the single-instance feature (when using the default prefix). Its structure typically includes these columns:

| Column | General Purpose |
| --- | --- |
| `LOCK_KEY` | Identifier of the lock record |
| `REGION` | Lock group/scope |
| `CLIENT_ID` | Identifier of the client owning the lock |
| `CREATED_DATE` | Timestamp when the lock record was created |

This is a **table supporting the framework's locking mechanism**, distinct from `TASK_EXECUTION` (execution history). Do not assume `CLIENT_ID` is `TASK_EXECUTION_ID` or that `REGION` is always the task name without checking the corresponding schema and implementation.

Example **read-only** query for inspection in a lab environment:

~~~sql
SELECT LOCK_KEY, REGION, CLIENT_ID, CREATED_DATE
FROM TASK_LOCK
ORDER BY CREATED_DATE DESC;
~~~

Do not run `DELETE FROM TASK_LOCK` or manually modify lock entries simply because a process appears stopped. The lock might still be valid for another process, or a TTL/recovery mechanism might be handling it; deleting it arbitrarily can open the door for two processes to run concurrently.

## 5. TTL, Lock Check Interval, and Failure Scenarios

A distributed lock is not merely about being **held** or **released**. When a process dies abruptly, loses network connectivity, or hangs, expiration and recovery policies are required.

The Spring Cloud Task configuration properties listed in the Spring Cloud reference include:

| Property | Meaning | Documented Default Value |
| --- | --- | --- |
| `spring.cloud.task.single-instance-enabled` | Enables single-instance locking by name | `false` |
| `spring.cloud.task.single-instance-lock-check-interval` | Interval between lock checks | `500` ms |
| `spring.cloud.task.single-instance-lock-ttl` | Maximum duration an execution may hold the lock | `Integer.MAX_VALUE` ms |

Default values and detailed behavior can vary across versions; consult the configuration properties for the version you deploy. **Do not assume `lock-check-interval` turns rejection into a queue**: according to the single-instance guide, a competing launch with the same name will fail. The interval relates to how the locking mechanism checks state; verify its exact effect when tuning instead of guessing a retry schedule.

### 5.1. A TTL That Is Too Short Can Reintroduce Overlap Risk

Suppose a task takes 40 minutes to run, but the lock TTL is only 10 minutes. Once lock ownership expires under the implementation's rules, another process **can acquire the lock** while the old process is still executing business logic. Therefore, setting a short TTL is not a safe shortcut for "fast self-recovery."

**Rule of thumb:** estimate normal runtime, slow-processing duration, infrastructure timeouts, and external wait times; configure the TTL according to a realistic lock-control strategy. Even with a long TTL, **idempotency** is still required because network failures or synchronization limits can create uncertain situations.

### 5.2. A TTL That Is Too Long Can Cause Prolonged Rejections for Subsequent Runs

If a task dies while holding the lock and the mechanism does not release it promptly, the next run may fail to acquire the lock for a long period. This requires an operational procedure:

1. Confirm that the process/pod holding the lock **has actually stopped**.
2. Inspect logs, task status, lock creation timestamp, and timeouts.
3. Review the expiration/release mechanism of the framework version.
4. Perform lock recovery according to an approved procedure with appropriate database access.
5. Verify business state before retrying to avoid duplicate processing.

**Do not recommend blind lock deletion:** metadata about lock ownership and whether the task actually wrote real data can diverge.

## 6. Controlling Overlapping Runs from the Scheduler: Kubernetes CronJob

When a task is packaged as a container and launched periodically by a **Kubernetes CronJob**, the scheduler provides the `spec.concurrencyPolicy` option:

| Value | Behavior for Jobs created by the **same CronJob** |
| --- | --- |
| `Allow` | Default; allows multiple overlapping Jobs |
| `Forbid` | If the previous Job has not finished, skips the new scheduled run instead of creating a concurrent Job |
| `Replace` | Replaces the currently running Job with a new Job; risks interrupting unfinished work |

Configuration example:

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-reconciliation
spec:
  schedule: "0 2 * * *"
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: reconciliation
              image: example.registry/reconciliation-task:1.0
              args:
                - "--businessDate=2026-11-23"
~~~

This is **illustrative YAML** for a lab; in practice, `businessDate` must be generated for the target date rather than hardcoded forever, and appropriate image, resource limits, secrets, and job policies must be configured.

**Critical limitation:** `concurrencyPolicy: Forbid` only applies to Jobs **created by that same CronJob**. A manually launched Job, another CronJob, or an external system outside Kubernetes can still start the application with the same name. If there are multiple trigger paths, you need a shared locking mechanism or appropriate business data constraints.

Kubernetes can also cause relaunches, schedule delays, or a Job running more than once under certain conditions; therefore, do not rely on `Forbid` to guarantee exactly-once processing.

## 7. Locking Options and Protection Levels

Not every problem requires a global lock by task name. The choice depends on the **contended resource** and the **unit of work**.

| Solution | Control Scope | Suitable For | Limitations |
| --- | --- | --- | --- |
| Spring Cloud Task `single-instance-enabled` | One **task name** on a shared lock store | Allowing only one run of the same application at a time | Does not distinguish business keys; does not prevent duplicate side effects across sequential runs |
| Kubernetes CronJob `Forbid` | Jobs belonging to the **same CronJob** | Periodic schedules within the same CronJob | Does not block manual runs or other CronJobs |
| Distributed lock by business key | `tenant + date + job type` | Allowing different tenants/dates to run in parallel while blocking the same business unit | Requires proper TTL/lease, fencing, and recovery implementation |
| Unique constraint / idempotency in business database | A unique result or operation | Preventing duplicate writes even when a request is resent | Does not limit CPU or process count on its own |
| Queue with consumer limits | Number of tasks accepted/processed | Controlling throughput and ordering | Requires handling redelivery, ack, and idempotency |
| Workflow orchestration | Multi-step, dependent workflows | Centralized scheduling, retries, and concurrency limits | Does not replace business-logic correctness |

### 7.1. When Is Name-Based Locking Too Broad?

For example, `monthly-export` can run independently for multiple `tenantId` values. If single-instance locking by name is enabled, tenant B's process could be rejected just because tenant A is running, even though they share no data. You might consider locking by `tenantId + reportingPeriod` if your architecture supports it.

### 7.2. When Is Name-Based Locking Too Narrow?

For example, `refund-batch` and `refund-manual` both update the same refund transaction. Two different task names do not contend for the **same lock name**, yet they contend over the **same transaction**. Service/database-level business constraints are needed to prevent double refunds.

### 7.3. "No Overlapping Runs" Does Not Mean "Exactly Once"

Even with single-instance enabled, Run 1 may finish at 02:10 and Run 2 may start at 02:11 with the same parameters. Because they do not overlap, the lock does not reject Run 2. If the business logic generates a file or sends an email again, duplicate side effects still occur.

A safe approach is to attach a **business key**, such as `reportDate + tenantId`. In the business database, design a unique constraint for the result and processing states (for example, `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`) with appropriate transactions. If the same request arrives again after success, return the existing result or skip the already completed side effect.

## 8. Querying TaskRepository to Detect Overlapping Runs

`TaskRepository` stores each execution, while `TaskExplorer` helps read metadata. When backed by a SQL database, the two commonly used tables are `TASK_EXECUTION` and `TASK_EXECUTION_PARAMS`.

### 8.1. Listing Runs with the Same Name

~~~sql
SELECT
    TASK_EXECUTION_ID,
    TASK_NAME,
    START_TIME,
    END_TIME,
    EXIT_CODE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'daily-reconciliation'
ORDER BY START_TIME DESC, TASK_EXECUTION_ID DESC;
~~~

Illustrative example:

| ID | Task Name | Start | End | Exit Code |
| --- | --- | --- | --- | --- |
| 1041 | daily-reconciliation | 02:00 | 02:12 | 0 |
| 1042 | daily-reconciliation | 02:10 | 02:22 | 0 |
| 1043 | daily-reconciliation | 03:00 | 03:05 | 0 |

The two intervals `[02:00, 02:12)` and `[02:10, 02:22)` overlap by 2 minutes. Thus **1041 and 1042 overlapped**. Both having exit code `0` does not prove the business outcome is correct.

### 8.2. Querying for Pairs with Overlapping Time Intervals

For records that have **already ended**, you can self-join the table to find pairs with overlapping durations:

~~~sql
SELECT
    a.TASK_EXECUTION_ID AS execution_a,
    b.TASK_EXECUTION_ID AS execution_b,
    a.START_TIME AS a_start,
    a.END_TIME AS a_end,
    b.START_TIME AS b_start,
    b.END_TIME AS b_end
FROM TASK_EXECUTION a
JOIN TASK_EXECUTION b
  ON a.TASK_NAME = b.TASK_NAME
 AND a.TASK_EXECUTION_ID < b.TASK_EXECUTION_ID
 AND a.START_TIME < b.END_TIME
 AND b.START_TIME < a.END_TIME
WHERE a.TASK_NAME = 'daily-reconciliation'
  AND a.END_TIME IS NOT NULL
  AND b.END_TIME IS NOT NULL
ORDER BY a.START_TIME, b.START_TIME;
~~~

The interval overlap rule here uses **[start, end)**: two runs touching at the exact moment one finishes **are not considered overlapping**. This query only illustrates post-hoc inspection; timestamps stored in the repository may have low resolution or differ from display time zones, so interpret results cautiously.

**Note:** records with `END_TIME IS NULL` are excluded from the query because they could represent a task currently running or a process that died before updating metadata. Do not replace `NULL` with `CURRENT_TIMESTAMP` and conclude with certainty that two processes overlapped; always check actual logs/infrastructure.

### 8.3. Finding Records Without an End Time Recorded

~~~sql
SELECT TASK_EXECUTION_ID, TASK_NAME, START_TIME
FROM TASK_EXECUTION
WHERE TASK_NAME = 'daily-reconciliation'
  AND END_TIME IS NULL
ORDER BY START_TIME;
~~~

This result is a list of records **to verify**, not a list of processes guaranteed to still be alive. If the JVM was killed, metadata may remain unfinished even though no valid lock remains.

## 9. Spring Boot Example to Test Overlapping Runs

Assume the application has been created using a Spring Boot version compatible with Spring Cloud Task and has a shared DataSource/schema. The following runner simply **waits for a bounded period** so you have time to launch two processes from two terminals without modifying real data.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class OverlapDemoApplication {

    private static final Logger log =
            LoggerFactory.getLogger(OverlapDemoApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(OverlapDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner runTask() {
        return args -> {
            log.info("WORK_BEGIN businessDate={}",
                    args.getOptionValues("businessDate"));

            // Simulate finite processing so there is time to start a second run.
            try {
                Thread.sleep(30_000);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw ex;
            }

            log.info("WORK_DONE");
        };
    }
}
~~~

Lab configuration round 1 — **allow overlap**:

~~~yaml
spring:
  main:
    web-application-type: none
  cloud:
    task:
      name: overlap-demo
      single-instance-enabled: false
~~~

In two terminals connected to the same environment/database, run the same command nearly simultaneously:

~~~bash
java -jar overlap-demo.jar --businessDate=2026-11-23
~~~

**Expected outcome:** if both processes initialize successfully, you will see two `overlap-demo` runs with different IDs and overlapping time windows. This demonstrates the default behavior and should not be used as-is for real business processing.

Lab configuration round 2 — **enable single-instance restriction**:

~~~yaml
spring:
  main:
    web-application-type: none
  cloud:
    task:
      name: overlap-demo
      single-instance-enabled: true
~~~

Ensure you have added `spring-integration-core` and `spring-integration-jdbc`, created the lock schema, and are using the **same database**. Run Process A, then run Process B while A is still in `sleep`.

**Expected outcome:** Process A acquires the lock, and B is rejected due to having the same name; inspect the error message and exit code. After A finishes normally, a new Process C can be launched. This is an **overlap** restriction; it does not stop C from reprocessing the same `businessDate`.

**Testing tip:** do not send `kill -9` in a production environment to simulate a stale lock. To investigate failures, use an isolated environment where you know how to recover data, and observe proper timeout/shutdown scenarios first.

## 10. Spring Batch and Concurrent Runs

When a Spring Cloud Task application launches **Spring Batch**:

- `TaskRepository` tracks the **task process** lifecycle.
- `JobRepository` tracks **JobInstance, JobExecution, StepExecution**, job parameters, and processing status.
- `TaskExecution` is distinct from `JobExecution`. A task can link to a Batch job according to integration configuration.

Spring Batch has rules for identifying a JobInstance by job name and **identifying job parameters**. A running JobInstance can cause an equivalent launch request to be rejected under Batch policies. However, that is **not the same mechanism** as Spring Cloud Task's single-instance lock by **task name**.

For example: two tasks with the same name might run for two different dates; single-instance blocks by name even though Batch treats them as two independent JobInstances. Conversely, two task applications with different names might trigger the same JobInstance in Batch; in that case, Batch's concurrency control comes into play.

If using an asynchronous JobLauncher, the runner may return before the job finishes; you must design the application so that **the task only terminates when mandatory Batch work completes**, or manage job state independently. Otherwise, a task-lifecycle lock could be released too early while Batch is still running.

## 11. Troubleshooting and Operational Decisions

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| Two tasks with the same name still run concurrently | `single-instance-enabled` not enabled everywhere, different effective task names, different lock databases, or missing classpath/schema | Check runtime config, task name, DataSource, dependencies, and lock logs |
| Second launch fails | Single-instance rejected it because the lock is held | Check Process A, Process B logs, and exit code; decide whether to skip or retry via scheduler |
| Subsequent run is rejected even though old process died | Lock not released yet, TTL too long, or recovery incomplete | Confirm the process is genuinely dead, inspect lock and recovery procedure |
| Re-run starts after TTL while old work is still active | TTL shorter than runtime / lack of proper lease control | Review TTL config, timeouts, resources, process state; protect data with fencing/idempotency if needed |
| Multiple `TASK_EXECUTION` rows share the same name | Multiple requests initialized successfully at different times | Cross-check timelines; different IDs are normal—check whether they actually overlapped |
| CronJob uses `Forbid` yet two tasks still run | Two Jobs not from the same CronJob, manual run, or another trigger path | Check Job creator source, retry policy, and shared lock |
| `END_TIME` metadata is empty | Process still running or died before recording completion | Cross-check pod/PID, logs, and business data; do not conclude from SQL alone |
| No overlap occurred, yet results are duplicated | Same business key re-executed sequentially | Add idempotency, unique constraints, and reconciliation procedures |

### Procedure When Rejected Due to Lock Contention

1. **Find the task holding the lock:** inspect logs, infrastructure, and metadata by `taskName` / timestamp.
2. **Assess the cause:** is this a valid overlapping schedule trigger, a manual admin run, an automatic retry, or a stuck old process?
3. **Choose an action:** skip until the next run, enqueue, schedule a retry with backoff, or halt new orchestration; never retry immediately in an infinite loop.
4. **Check business state:** did the previous run write data yet? If already completed, handle the duplicate request by business key.
5. **Recover the lock if needed:** only after verifying the owner and lease/TTL procedure; avoid uncontrolled direct SQL edits.
6. **Record the event:** log the rejection reason, task name, execution ID if available, job/pod ID, non-sensitive business key, and handling decision.

## 12. Safe Design Checklist

Before deploying to production:

- [ ] Identified the **unit that must not overlap**: entire task, per tenant, per date, or per record.
- [ ] Identified all sources that can trigger the task: scheduler, API, manual run, retry, orchestrator.
- [ ] Defined a **clear contention policy**: reject, skip, queue, replace, or controlled parallel execution.
- [ ] If using single-instance, all processes to control share the same task name, lock-enabled config, and **same JDBC store**.
- [ ] Prepared the `TASK_LOCK` schema and compatible Spring Integration dependencies, managing tables via migrations.
- [ ] Tested TTL, task timeouts, graceful shutdown time, and stale-lock recovery.
- [ ] Implemented a **business key** and idempotency/unique constraints in the result storage system.
- [ ] Configured a retry policy with backoff and stop conditions to avoid launch storms.
- [ ] Logs include task name, execution ID when available, trigger source, and non-sensitive business parameters.
- [ ] Monitoring covers TaskRepository, pod/process state, and actual business outcomes together.
- [ ] If using Spring Batch, reconciled task locking with JobInstance/JobExecution identification.
- [ ] Prepared test scenarios for two concurrent runs, sequential runs with identical parameters, killed processes, and timeouts.

## 13. Key Takeaways

**Having multiple `TaskExecution` records with the same `taskName` is normal; danger arises when they operate simultaneously on resources not designed for concurrent access.** Spring Cloud Task records execution history, while `single-instance-enabled` rejects competing runs with the **same name** when enabled and configured with a shared lock store. Kubernetes CronJob `Forbid` only prevents overlaps **within the same CronJob**.

To operate safely, always answer both questions: **should overlapping runs be allowed?** and **does re-running the same work cause duplicate side effects?** Name-based locking only addresses the first question; business keys, idempotency, and data constraints address the second. Combining TaskRepository metadata, infrastructure monitoring, and retry policies keeps finite Spring Cloud Task applications stable whether scheduled or triggered on demand.

### References

- [Spring Cloud Task Reference — Restricting Spring Cloud Task Instances](https://docs.spring.io/spring-cloud-task/reference/features.html#restricting-spring-cloud-task-instances)
- [Spring Cloud Task Reference Guide — Task Lock Schema](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/)
- [Spring Cloud configuration properties — Task single-instance](https://docs.spring.io/spring-cloud/docs/current/reference/html/configprops.html)
- [Kubernetes — CronJob concurrency policy](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/#concurrency-policy)
