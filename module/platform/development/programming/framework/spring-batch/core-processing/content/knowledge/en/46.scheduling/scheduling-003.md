# Preventing Overlapping Execution in Spring Batch Scheduling

When a Spring Batch Job is triggered on a schedule, the previous run may still be processing when the next trigger arrives. If two runs read the same data source, update the same tables, generate the same report, or send the same notifications, the system can write duplicates, contend on locks, and become difficult to recover after failures.

**Preventing overlapping execution** is a design to stop unauthorized executions from running concurrently. In Spring Batch, you must define the exact scope you want to guard against overlap: **the same `JobInstance`**, **all runs of the same Job**, or **all processes across an application cluster**. Each scope requires a different control mechanism.

This lesson belongs to the *Scheduling* topic of *Spring Batch Core Processing*. It covers `JobRepository` behavior, `@Scheduled` limitations, single-JVM and multi-instance solutions, distributed lock configuration examples, concurrency testing, and operational scenarios.

## 1. What Is Overlapping Execution?

Suppose `settlementJob` aggregates unsettled transactions. The Job is scheduled every 5 minutes, but a single run can take 8 minutes:

```text
Time            10:00      10:05      10:08      10:10      10:13
                |----------|----------|----------|----------|
Schedule        A          B                     C

Job A           [-----------------------]
Job B                      [-----------------------]
                                ^^^^^^^
                                A and B overlap
```

If both A and B select transactions with `PENDING` status and write results concurrently, you can encounter:

- Duplicate settlement records or sending the same command twice to an external system.
- Overlapping updates leaving an incorrect final state.
- Two Jobs holding database locks and waiting on each other, causing deadlocks or timeouts.
- One Job moving/overwriting a file while another Job is still reading it.
- Confusing counters and run history because multiple `JobExecution`s coexist.

Not all concurrent execution is wrong. Two Jobs processing completely disjoint datasets can validly run in parallel. Before adding a lock, define the **exclusive resource and scope** that need protection.

## 2. Three Scopes of Overlap Prevention

| Scope | Example | Suitable mechanism |
| --- | --- | --- |
| **Same `JobInstance`** | Two calls with the same Job name and same identifying JobParameters. | Spring Batch's `JobRepository` prevents concurrent active `JobExecution`s for the same instance. |
| **Same Job, different `JobInstance`** | `settlementJob` for the 10:00 and 10:05 windows running concurrently. | A lock keyed by Job name/shared resource or an execution queuing mechanism. |
| **Multiple JVMs/containers/pods** | Two Spring Boot instances both run `@Scheduled` and trigger the Job. | Distributed lock, coordinated scheduler, or a central scheduler. |

An important principle:

> **`JobRepository` does not automatically block all concurrent runs of the same Job name.** It controls state and validity per `JobInstance`. Two different sets of identifying parameters form two distinct JobInstances, so they *can* run concurrently.

Example:

```text
Job: settlementJob

JobInstance X
  parameters: {window=2026-11-16T10:00Z}
  execution:  #101 STARTED

JobInstance Y
  parameters: {window=2026-11-16T10:05Z}
  execution:  #102 STARTED

=> Both STARTED concurrently is a possible scenario.
```

If X and Y update a shared business resource, add Job/resource-level exclusivity beyond the JobInstance check.

## 3. How Spring Batch Prevents Duplicate Runs of the Same `JobInstance`

In Spring Batch:

- `Job` is the workflow definition.
- `JobInstance` is identified by **Job name + identifying JobParameters**.
- `JobExecution` is a single execution attempt of a JobInstance; an instance can have multiple executions across restarts.

Suppose two calls are made:

```java
JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16")
        .toJobParameters();

jobLauncher.run(settlementJob, params);
```

If a JobExecution of the same JobInstance is still running, the repository normally rejects the second launch request with `JobExecutionAlreadyRunningException`. If the instance is already completed, attempting to launch again with the same parameters may raise `JobInstanceAlreadyCompleteException`. If the previous instance failed and the Job allows restart, a subsequent call can create a new `JobExecution` to restart it.

The following table summarizes what the previous status means when requesting the same identifying parameters:

| Previous status | Typical behavior |
| --- | --- |
| `STARTING`, `STARTED`, or still running | Rejects concurrent run for the same JobInstance. |
| `COMPLETED` | Does not relaunch an already-completed instance. |
| `FAILED`, `STOPPED` | Can restart depending on Job/Step configuration and existing metadata. |
| `ABANDONED` or inconsistent metadata | Handle per restartability and operational procedures; do not arbitrarily delete state. |

These checks depend on a properly configured repository, execution-creation transactions, and metadata persistence. Nodes coordinating through `JobRepository` must share one consistent backend; a separate metadata database per node provides no shared protection.

### Why Random Parameters Do Not Prevent Overlap

Many Job launch examples use:

```java
new JobParametersBuilder()
        .addLong("run.id", System.currentTimeMillis())
        .toJobParameters();
```

A new identifying parameter always creates a **new JobInstance**. This is useful when each run should be independent, but it removes the ability to rely on the JobInstance key to recognize two duplicate schedule requests.

In particular, `RunIdIncrementer` is also meant to generate distinct identifying parameters between runs. It is **not a locking mechanism**. If the goal is to prevent Job-wide overlap, a dedicated exclusivity lock is required.

Conversely, using one fixed parameter set forever is not a solution either: once the JobInstance completes, subsequent schedules will be rejected indefinitely with `JobInstanceAlreadyCompleteException`. Design identification around the **unit of work** to process, such as business date or schedule window, and keep overlap prevention separate.

## 4. Does `@Scheduled` Guarantee No Overlap?

Spring Framework lets you trigger tasks with `@Scheduled`:

```java
@Scheduled(cron = "0 */5 * * * *", zone = "UTC")
public void triggerBatch() {
    // Launch Job
}
```

Distinguish between scheduling styles:

| Schedule type | Meaning | Things to watch out for |
| --- | --- | --- |
| `fixedDelay` | Counts pause after the previous method invocation finishes. | Can limit overlap of **that specific schedule call** when the method runs synchronously. |
| `fixedRate` | Task scheduled at a fixed period. | No exclusivity guarantee across multiple schedules, multiple apps, or other callers. |
| `cron` | Fires on a cron expression. | No built-in distributed Job locking mechanism. |

Example:

```java
@Scheduled(fixedDelayString = "PT5M")
public void runAfterPreviousInvocation() {
    jobLauncher.run(job, parameters);
}
```

If the Job launcher is **synchronous**, the call returns only when the Job finishes; `fixedDelay` starts counting afterward. However:

1. If `jobLauncher.run(...)` launches **asynchronously**, the scheduled method can return while the Job is still running. The `fixedDelay` interval only measures from when the trigger method returns, not when the Job finishes.
2. Each pod/application instance has its own scheduler. Two pods can trigger the same schedule.
3. Call paths outside the scheduler (admin APIs, manual run buttons, retry services, another Quartz job) can still launch the same Job.
4. A method with multiple `@Scheduled` declarations, or called from multiple places, can produce independent triggers.

Therefore, choosing `fixedDelay` addresses only a narrow case. To protect resources at the application level, explicitly design synchronization and lock lifecycle.

## 5. Approach 1: Guarding with `AtomicBoolean` in a Single JVM

If the application is guaranteed to run as **one process** and all Job triggers go through the same object, an atomic flag is a simple mechanism to skip new triggers while a run is active.

```java
import java.util.concurrent.atomic.AtomicBoolean;

public final class SingleJvmOverlapGuard {

    private final AtomicBoolean running = new AtomicBoolean(false);

    public boolean runIfIdle(Runnable jobAction) {
        if (!running.compareAndSet(false, true)) {
            return false; // Another run is active; skip trigger.
        }

        try {
            jobAction.run();
            return true;
        } finally {
            // Always release the flag even if jobAction throws an exception.
            running.set(false);
        }
    }
}
```

Usage in a service:

```java
@Component
class LocalBatchSchedule {

    private final SingleJvmOverlapGuard guard =
            new SingleJvmOverlapGuard();

    @Scheduled(fixedRateString = "PT5M")
    void trigger() {
        boolean executed = guard.runIfIdle(() -> {
            // Inside must call a synchronous launcher or wait for actual Job completion.
            runJobSynchronously();
        });

        if (!executed) {
            // Record skipped metric/log: previous execution still active.
        }
    }

    private void runJobSynchronously() {
        // Execute Job, handle status and errors per application requirements.
    }
}
```

**Advantages:** minimal dependencies, clear behavior, and easy to unit test.

**Limitations:**

- The flag exists only in one JVM's memory. Two pods have two separate flags and both can run.
- If code launches the Job and returns immediately via an async executor, `finally` releases the flag too early.
- The flag does not survive process restarts; nor does it provide persistent history for recovery.
- If multiple beans/paths create separate guards, each guard controls only its own scope.

Use this approach for single-instance deployments with strict control over all launch paths. For production with multiple replicas, an inter-node mechanism is required.

## 6. Approach 2: Distributed Lock Across Spring Boot Instances

A common solution is **ShedLock**, a library that adds coordination when multiple instances execute `@Scheduled` methods. ShedLock can store lock state in a shared database via JDBC or another suitable backend.

The idea:

```text
Spring Boot A -- @Scheduled --> acquire("settlementJobSchedule") --┐
                                                                  ├--> Shared lock table
Spring Boot B -- @Scheduled --> acquire("settlementJobSchedule") --┘

A acquires lock    => launches Job, holds lock until Job completes.
B fails to acquire => skips this trigger.
```

This is a **skip when lock cannot be acquired** strategy, not a queue that automatically holds every trigger to run sequentially. If the business requires processing every scheduled window, supplement it with backlog/catch-up storage.

### 6.1. Dependencies

With Spring Boot, you typically need these modules:

```groovy
dependencies {
    implementation 'net.javacrumbs.shedlock:shedlock-spring'
    implementation 'net.javacrumbs.shedlock:shedlock-provider-jdbc-template'
}
```

Manage a **ShedLock version compatible with your project's Spring Framework/Spring Boot** via dependency constraints or explicit version declarations. The two dependencies above are module names and do not imply the Spring Boot BOM manages their versions by default.

### 6.2. Shared Lock Table

Example JDBC table schema on PostgreSQL:

```sql
CREATE TABLE shedlock (
    name       VARCHAR(64)  NOT NULL PRIMARY KEY,
    lock_until TIMESTAMP    NOT NULL,
    locked_at  TIMESTAMP    NOT NULL,
    locked_by  VARCHAR(255) NOT NULL
);
```

All instances must access **the same lock table** with proper transactions/permissions. Do not create a separate `shedlock` table per pod if cluster-wide coordination is intended.

### 6.3. Registering `LockProvider`

Java configuration example:

```java
import net.javacrumbs.shedlock.core.LockProvider;
import net.javacrumbs.shedlock.provider.jdbctemplate.JdbcTemplateLockProvider;
import net.javacrumbs.shedlock.spring.annotation.EnableSchedulerLock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
@EnableSchedulerLock(defaultLockAtMostFor = "PT45M")
public class BatchSchedulingConfig {

    @Bean
    LockProvider lockProvider(JdbcTemplate jdbcTemplate) {
        return new JdbcTemplateLockProvider(
                JdbcTemplateLockProvider.Configuration.builder()
                        .withJdbcTemplate(jdbcTemplate)
                        .usingDbTime()
                        .build()
        );
    }
}
```

`usingDbTime()` uses database time for lock calculations, mitigating clock skew across nodes. The schema above is a PostgreSQL example; if using another database engine, apply the vendor-recommended DDL.

### 6.4. Locking the Scheduled Method

Java example for **Spring Batch 5.x / Spring Boot 3.x**, with a preconfigured **synchronous** launcher:

```java
import java.time.Instant;

import net.javacrumbs.shedlock.spring.annotation.SchedulerLock;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionException;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class SettlementSchedule {

    private static final Logger log =
            LoggerFactory.getLogger(SettlementSchedule.class);

    private final JobLauncher syncJobLauncher;
    private final Job settlementJob;

    public SettlementSchedule(
            @Qualifier("syncJobLauncher") JobLauncher syncJobLauncher,
            @Qualifier("settlementJob") Job settlementJob) {
        this.syncJobLauncher = syncJobLauncher;
        this.settlementJob = settlementJob;
    }

    @Scheduled(cron = "0 */5 * * * *", zone = "UTC")
    @SchedulerLock(
            name = "settlementJobSchedule",
            lockAtMostFor = "PT45M"
    )
    public void executeScheduledWindow() {
        // Same 5-minute window -> same identifying parameter
        // across all nodes with synchronized clocks.
        long fiveMinuteWindow =
                Instant.now().getEpochSecond() / 300L;

        JobParameters parameters = new JobParametersBuilder()
                .addLong("windowIndex", fiveMinuteWindow, true)
                .toJobParameters();

        try {
            JobExecution execution =
                    syncJobLauncher.run(settlementJob, parameters);

            if (execution.getStatus() != BatchStatus.COMPLETED) {
                log.warn("Settlement Job status={}, executionId={}",
                        execution.getStatus(), execution.getId());
            }
        } catch (JobExecutionException ex) {
            // Includes Job launch condition errors;
            // classify further when designing production retry/alerting.
            log.error("Unable to launch settlementJob", ex);
        }
    }
}
```

The two protection layers in the example serve different purposes:

- `@SchedulerLock` blocks **two schedules from running the same Job concurrently across multiple nodes**, even for different windows.
- `windowIndex` gives the same window the **same JobInstance**, preventing duplicate processing if a trigger is retried after completion.

Note that computing `windowIndex` from actual wall-clock time **when the method runs** suits simple schedules. Systems requiring exact catch-up of every missed window should persist window history and pass the *target window* explicitly instead of always taking the current window.

### 6.5. Ensuring a Synchronous Launcher

In Spring Batch 5.x, you can create a launcher with `SyncTaskExecutor`:

```java
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.launch.support.TaskExecutorJobLauncher;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.SyncTaskExecutor;

@Configuration
class SynchronousLauncherConfig {

    @Bean("syncJobLauncher")
    JobLauncher syncJobLauncher(JobRepository jobRepository)
            throws Exception {
        TaskExecutorJobLauncher launcher =
                new TaskExecutorJobLauncher();

        launcher.setJobRepository(jobRepository);
        launcher.setTaskExecutor(new SyncTaskExecutor());
        launcher.afterPropertiesSet();
        return launcher;
    }
}
```

When `run(...)` executes synchronously, the `@SchedulerLock` method holds the lock for the entire Job run and releases it only after the Job returns (unless the maximum lock duration expires).

If the launcher executes **asynchronously**, `run(...)` can return while the Job is still `STARTED`. The `@Scheduled` wrapper also finishes, causing ShedLock to release the lock while the Job is still processing. To avoid this gap, span the lock across the entire actual execution lifecycle: use a synchronous launcher, or design an orchestration service that awaits terminal status and renews the lease appropriately.

In Spring Batch 6.x, launch APIs are reorganized; `JobOperator` and corresponding task executor configuration are the right choice. The principle of **holding the lock until terminal status** remains unchanged.

### 6.6. Understanding `lockAtMostFor` and `lockAtLeastFor`

- `lockAtMostFor` is the **maximum limit** a lock remains valid if a process dies or fails to release it. If a Job runs longer than this limit, the lock can expire **while the Job is still running**; another node may acquire the lock and cause overlap.
- `lockAtLeastFor` (optional) holds the lock for at least a minimum duration, useful for very short tasks or nodes with slight clock skew.
- These two parameters **do not replace** timeout policies, monitoring of long-running jobs, and recovery handling.

For example, if a Job takes at most 30 minutes under a reliable SLA, configure `lockAtMostFor` with a reasonable safety margin above 30 minutes. For Jobs with unbounded runtime, do not pretend a fixed TTL is always safe. Use lease renewal, fencing, or more durable coordination.

**A time-bounded lock (lease) does not equate to eternal exclusivity.** In systems exposed to JVM pauses, connection drops, or lease expiration, data-layer idempotency remains essential.

## 7. Approach 3: Coordinated Scheduler or Durable Queue

For more complex needs, you can use:

| Solution | Coordination model | When appropriate |
| --- | --- | --- |
| Quartz with JDBC JobStore and clustering | Schedulers share a JobStore and coordinate triggers across the cluster. | Need rich schedule management, misfires, and trigger durability. |
| Quartz `@DisallowConcurrentExecution` | Blocks concurrent executions of the same `JobDetail` / `JobKey` within the coordinated JobStore. | Want exclusivity scoped to a specific Quartz JobDetail. |
| Central scheduler | Only one orchestrator issues Job launch requests. | Need one clear control point with multiple task workers. |
| Message queue / work table | Persists each window to process and uses consumer claim/lease. | Cannot drop triggers even when a previous Job runs long. |
| Database business lock | Uses unique constraints, claim status, transactions, or DB advisory locks. | Need to guard a specific business resource across multiple launch paths. |

With Quartz, `@DisallowConcurrentExecution` prevents overlap **for the same JobDetail identity**; it does not automatically lock different JobDetails sharing the same Java class. Configuring clustering/shared JDBC JobStore is also crucial; per-node JobStores provide no cluster-wide exclusivity.

If the requirement is **every trigger must be processed once**, a mutex like ShedLock may fall short because runs that fail to acquire the lock are skipped. In that case, storing work in a durable queue/schedule table and having workers claim items transactionally is a better design.

## 8. Checking Running Jobs with `JobExplorer`: Use for Observation, Not as a Lock

`JobExplorer` can query active executions by Job name:

```java
Set<JobExecution> running =
        jobExplorer.findRunningJobExecutions("settlementJob");
```

This information is very useful to:

- Display status on dashboards.
- Log/emit metrics on how many JobExecutions are currently active.
- Diagnose hung Jobs or stale metadata.
- Alert when a Job exceeds its allowed runtime.

However, a naive check-then-launch pattern has a **race condition**:

```text
Node A                           Node B
------                           ------
findRunning(...) -> empty       findRunning(...) -> empty
          |                               |
          +----- both see "idle" ---------+
          |                               |
launch(Job, params A)           launch(Job, params B)
          |                               |
          +---- Can run concurrently -----+
```

Reading status and launching are **not an atomic Job-wide lock**. Even if the query returns empty, another node can start the Job before the current node calls the launcher.

Therefore, `JobExplorer` is an observability tool or a secondary check. If Job-wide exclusivity is required, the deciding mechanism must be an atomic lock/claim with a clearly guarded scope.

## 9. Preventing Overlap Does Not Guarantee Exactly-Once Processing

Three distinct concepts exist:

| Concept | Question | Safeguard |
| --- | --- | --- |
| **Mutual exclusion** | Can more than one execution run concurrently on the same resource? | Distributed lock, guard, or scheduler coordination. |
| **Deduplication** | Is the same unit of work recognized as a duplicate? | Identifying JobParameters, business keys, unique constraints. |
| **Idempotency** | If an operation is called again, does the final data stay correct? | Upsert, unique keys, processing status, outbox/inbox, controlled retry handling. |

Example of sending a payment to an external system:

1. The Job sends the request successfully.
2. The process crashes before Spring Batch metadata is updated to `COMPLETED`.
3. After restart, the Job attempts to send the same request again.
4. The overlap lock may already have been released after the crash; the request still repeats **over time**, even though two Jobs never ran concurrently.

Therefore, for critical workflows, carry an **idempotency key** (such as a payment ID) and persist processing state or rely on an idempotent target-system contract. Schedule locks prevent overlapping runs, but cannot alone provide “exactly-once” guarantees for side effects outside `JobRepository` transactions.

## 10. Policy When a Trigger Arrives While a Job Is Running

When a new scheduled trigger encounters an active Job, a clear business behavior must be agreed upon:

### 10.1. Skip the New Trigger

- Simple; suitable if the next Job always scans all remaining backlog data.
- Emit metrics/logs recording the skip.
- If each schedule represents a distinct data window, skipping may drop a window unless catch-up exists.

### 10.2. Queue and Run Later

- Store each window in a task table with a unique key.
- Workers claim a task and process it to completion.
- While a Job is busy, new tasks wait in the queue.
- Handle worker crashes, lease expiration, retries, and dead-lettering.

### 10.3. Coalesce: Merge Multiple Triggers into One Run

- For example, a catalog sync Job reads all unprocessed changes without needing a separate run per minute.
- Only store a “new work pending” flag or the latest target timestamp.
- After the current Job finishes, schedule one new run if more changes remain.

### 10.4. Allow Bounded Parallel Execution

- If data has independent partitions/keys, each partition can have its own lock.
- For example, `settlementJob:merchant=123` and `settlementJob:merchant=456` run concurrently, while two jobs for merchant 123 do not.
- Locks must align with the **actual conflicting resource**, avoiding system-wide locks that create unnecessary bottlenecks.

Lock key design often matters more than library choice: too coarse a lock kills throughput; too narrow a lock fails to prevent real conflicts.

## 11. Handling Jobs Stuck in `STARTED` After a Crash

If a process terminates abruptly mid-run:

- `JobExecution` in the repository may still show `STARTED` even though the worker no longer exists.
- Requests for the same JobInstance may be rejected because the repository believes the prior execution is still running.
- A TTL-based distributed lock may expire so another node can acquire it, but **JobInstance metadata and business data state must be handled separately**.

Do not automatically delete `BATCH_JOB_EXECUTION` rows to “unstick” and rerun. Doing so loses restart information, checkpoints, and audit trails.

A recovery procedure should include:

1. Verify the old execution's process/worker is genuinely no longer active.
2. Inspect persisted JobExecution, StepExecution, and ExecutionContext.
3. Assess whether steps are restartable and side effects are idempotent.
4. Following operational runbooks, update status or perform restart via the system's proper API/mechanism.
5. Record the execution ID, incident cause, and resolution outcome for auditing.

If two nodes do not see the same `JobRepository`, “currently running” conclusions are unreliable. Metadata datasource and lock provider configurations must be understood and verified across the entire cluster.

## 12. Deterministically Testing Overlap Prevention

A test that merely launches a Job twice sequentially does not reliably test overlap: the first run may finish before the second begins. To prove exclusivity, you must **hold the first run active** and then trigger the second.

### 12.1. Unit Testing a Single-JVM Guard

JUnit Jupiter example with `SingleJvmOverlapGuard` from section 5:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class SingleJvmOverlapGuardTest {

    @Test
    void shouldSkipSecondRunWhileFirstIsActive() throws Exception {
        SingleJvmOverlapGuard guard = new SingleJvmOverlapGuard();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<Boolean> first = pool.submit(() ->
                    guard.runIfIdle(() -> {
                        entered.countDown();
                        try {
                            if (!release.await(5, TimeUnit.SECONDS)) {
                                throw new IllegalStateException(
                                        "Timed out waiting for test");
                            }
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                            throw new IllegalStateException(ex);
                        }
                    })
            );

            assertThat(entered.await(3, TimeUnit.SECONDS))
                    .as("First run must enter the guarded region")
                    .isTrue();

            boolean second = guard.runIfIdle(() -> {
                throw new AssertionError(
                        "Second run must not execute while busy");
            });

            assertThat(second).isFalse();

            release.countDown();
            assertThat(first.get(5, TimeUnit.SECONDS)).isTrue();

            boolean third = guard.runIfIdle(() -> {});
            assertThat(third)
                    .as("After the first run finishes, lock must be released")
                    .isTrue();
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
```

This test verifies all three states:

1. The first run is holding the guard.
2. The second run is skipped and the work is not executed.
3. Once the first run finishes, a new run is allowed.

`CountDownLatch` controls the concurrency boundary; timeouts prevent hanging tests. This tests the **single-JVM** mechanism and is not sufficient to conclude a distributed lock works correctly.

### 12.2. Integration Testing `JobRepository` and Same `JobInstance`

Scenario:

1. Create a test Job whose Tasklet pauses on a `CountDownLatch` after starting.
2. Launch the Job on one thread or via an async launcher with fixed identifying parameters.
3. Wait until the Tasklet signals it has entered processing.
4. From another thread, call the launcher with the **same Job and same identifying parameters**.
5. Assert the repository rejects the second launch, e.g., `JobExecutionAlreadyRunningException`.
6. Release the latch, wait for the first Job to complete, and assert final status.
7. Clean up metadata and test data after all workers stop.

Watch out: if the second call uses different parameters, the test no longer checks rejection of the **same JobInstance**. That is a different scenario requiring a global guard/lock to prevent overlap.

### 12.3. Integration Testing a Distributed Lock

Test using **two application contexts or two processes** sharing the same lock database:

```text
Context A                      Shared DB                 Context B
---------                      ---------                 ---------
@Scheduled / manual call  ----> lock: acquired
                                                          |
                                                   lock: rejected
    |
 Job waiting on latch
    |
  release latch
    |
 Job COMPLETED  -------------> lock released
                                                          |
                                                   re-trigger -> acquired
```

Verify:

- While A holds the lock, B **does not execute the Job body**.
- After A finishes and releases the lock, a new valid trigger can run.
- Both nodes use the same lock key and point to the same backend.
- Simulating a Job longer than `lockAtMostFor` exposes the risk of lease expiration while the Job is still running.
- If the lock releases as soon as an async launcher returns, the test should catch the risk of B overlapping.

Note that `@SchedulerLock` can rely on Spring proxies; calling `this.executeScheduledWindow()` directly within the same bean may bypass interception depending on configuration. In tests, invoke through the Spring-managed bean/proxy or trigger the real scheduler to exercise the production execution path.

### 12.4. Asserting Data State

Counting how many times a Job was submitted is not enough. For order-writing workflows, verify:

```java
assertThat(orderRepository.count()).isEqualTo(expectedCount);
assertThat(orderRepository.countDistinctBusinessKeys())
        .isEqualTo(expectedCount);
```

`countDistinctBusinessKeys()` is an illustrative project-defined repository method. Tests should query actual persisted state to confirm zero duplicate business records and zero duplicate side effects.

## 13. Operational Observability: Logs, Metrics, and Alerts

To detect overlaps or stuck Jobs, record:

| Field/metric | Meaning |
| --- | --- |
| `jobName` and `jobExecutionId` | Precisely identifies the active execution. |
| `jobInstanceId` or identifying parameters | Distinguishes duplicate runs of one instance from two separate tasks. |
| `scheduledWindow` | Correlates trigger schedule and business data window. |
| `trigger_result` = started/skipped/failed | Shows which triggers ran, were skipped, or errored. |
| `lock_key` and acquire result | Identifies locked resource and skip reason. |
| `job_duration` | Guides alert thresholds and lease limits. |
| `BatchStatus`, `ExitStatus`, failure exceptions | Separates failed Jobs from rejected triggers. |
| `concurrent_execution_count` | Alerts when exceeding allowed concurrency. |

A **skipped trigger** differs from a **failed Job**. When lock acquisition fails, there is not necessarily a new `JobExecution` in `JobRepository` to inspect. The scheduler needs separate logs/metrics for skip events.

Useful operational alerts: a Job running longer than usual, repeatedly skipping consecutive windows, metadata stuck `STARTED` too long, or growing backlog volume. These signals reveal schedule configurations mismatched with actual processing times.

## 14. Common Mistakes

### Using Random `run.id` and Expecting Spring Batch to Block Duplicates

Each random parameter usually creates a new JobInstance. `JobRepository` does not prevent two different instances from running concurrently. To lock an entire Job, use a distributed lock or single orchestrator.

### Reading `JobExplorer.findRunningJobExecutions(...)` Before Launching

Two nodes can both see the repository idle. Check-then-launch is not an atomic mutex. Use a lock/claim mechanism where concurrency is guarded.

### Using Only `synchronized` or `AtomicBoolean` with Multiple Pods

These mechanisms lock only within a single JVM. They do not share state with other pods. For cluster exclusivity, use a shared backend.

### Using ShedLock with an Async Launcher

`@SchedulerLock` normally holds the lock while the **annotated method** executes. If the launcher returns before the Job finishes, the lock releases early. Keep the lock until terminal state or switch to a synchronous launcher in the scheduler.

### Setting `lockAtMostFor` Too Short

When the TTL expires while the Job is still processing, another node can acquire the lock. Base it on reliable maximum runtime, define policies for overrun Jobs, and monitor timeouts.

### Forgetting to Handle Skipped Windows

If each 5-minute window owns distinct data and a trigger is skipped because the lock is busy, nothing guarantees that window is automatically caught up. Build backlog/catch-up handling if the domain cannot drop time intervals.

### Locking the Entire Job When Data Is Independent

One global lock can severely degrade throughput. When data partitions are truly independent, lock per partition/business key to allow safe concurrency.

### Hastily Deleting Metadata or Editing Status to “Unlock”

`JobRepository` metadata serves restart and auditing. Interventions must follow recovery procedures, verify the old Job stopped, and account for business idempotency.

### Assuming No Overlap Means Zero Duplicate Side Effects

Crashing after a successful side effect can still cause a retry to resend it. Unique business keys, idempotency, and proper transaction/outbox design are a separate protection layer from scheduler locks.

## 15. Practice Exercise

You have `dailyReportJob` generating revenue reports, normally taking 2 minutes but occasionally stretching to 12 minutes. The system runs 3 Spring Boot pods; each pod has `@Scheduled(cron = "0 */5 * * * *")`.

**Requirement:** at any point in time, only one `dailyReportJob` may write reports to the shared output resource, without losing data from unprocessed time windows.

Implement in steps:

1. Identify work by `businessDate`/`windowStart` and keep identifying JobParameters consistent across pods.
2. Configure a shared `JobRepository` so Spring Batch properly identifies JobInstances.
3. Create a distributed lock by Job name or report resource name; configure a shared lock backend and choose a lease matching execution time.
4. Ensure the lock scope spans the **entire** Job execution, even when the Job takes 12 minutes.
5. Persist unprocessed windows in a backlog table or design the report to coalesce work, depending on the business contract.
6. Use a latch to simulate a long-running Job; trigger the schedule on two nodes and prove only one node enters the guarded section.
7. Once Job A finishes, trigger the next turn; verify the backlog is processed with no duplicate files/records.
8. Simulate a mid-run process crash; verify lease policy, metadata recovery, restart, and output idempotency.

Self-check questions: if you keep all configuration identical but swap the synchronous launcher for an asynchronous one, what happens to when the lock is released? If each pod uses a different ShedLock database, what happens? If a window is skipped, by what mechanism does the system catch it up?

## References

- [Spring Batch – Configuring and Running a Job](https://docs.spring.io/spring-batch/reference/job/running.html): launching Jobs, JobParameters, JobInstance, and JobExecution.
- [Spring Batch – Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): repository role in persisting and controlling metadata.
- [Spring Batch – Job Restart](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html): metadata management and restart conditions.
- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Scheduled`, fixed delay/rate, and executors.
- [ShedLock – Documentation](https://github.com/lukas-krecan/ShedLock): distributed locking mechanism, JDBC provider, `lockAtMostFor`, and `lockAtLeastFor`.
- [Quartz – `DisallowConcurrentExecution`](https://www.quartz-scheduler.org/api/2.3.0/org/quartz/DisallowConcurrentExecution.html): concurrency restriction per Quartz JobDetail.

