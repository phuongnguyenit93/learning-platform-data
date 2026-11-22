# @Scheduled Tasks and Background Work After Restore

Spring Boot often runs periodic jobs and background tasks in the same process as the web application. For example: syncing data, refreshing caches, sending reports, cleaning up expired data, checking service status, reading message queues, or processing asynchronous tasks. These jobs can be declared with @Scheduled, run via TaskScheduler, TaskExecutor, @Async, or a dedicated worker.

When an application uses CRaC (Coordinated Restore at Checkpoint), the process is saved and then continues running after restore. While checkpointed, Java threads do not process normal work, yet external time still passes. A scheduled run may have come due, a task may have been mid-execution, a message lease may have expired, or a retry attempt may no longer be appropriate.

Therefore, the lifecycle of background work must be designed explicitly: stop accepting new work before checkpoint, wait for or handle in-flight tasks, define a policy for missed runs, reinitialize schedulers/workers after restore, and only allow execution once dependencies are ready. The @Scheduled annotation itself cannot replace that business policy.

## 1. How Does @Scheduled Work?

In Spring, @EnableScheduling enables the mechanism for detecting methods annotated with @Scheduled. Spring registers these methods with a TaskScheduler. For example:

~~~java
@Configuration
@EnableScheduling
public class SchedulingConfiguration {
}
~~~

A bean can declare a periodic job:

~~~java
@Component
public class CacheRefreshJob {

    private final CacheService cacheService;

    public CacheRefreshJob(CacheService cacheService) {
        this.cacheService = cacheService;
    }

    @Scheduled(fixedDelay = 30_000)
    public void refreshCache() {
        cacheService.refresh();
    }
}
~~~

In the example, Spring calls refreshCache() on schedule. If no custom scheduler is configured, Spring selects a scheduler according to the framework's default mechanism; the actual configuration depends on the Spring version and the existing TaskScheduler/TaskExecutor beans. For applications that need control over threads, shutdown, and restore, an explicit scheduler should be declared.

### 1.1. Common Schedule Types

| Property | Meaning | Use case |
|---|---|---|
| fixedDelay | Wait a specified duration after the previous run finishes before running the next one | Polling, cache refresh, tasks requiring a pause after processing |
| fixedRate | Schedule based on the interval between expected start times | Jobs requiring a relatively steady cadence |
| cron | Run according to a calendar-style schedule expression | Reports, hourly/daily aggregations, time-zone-based jobs |

Example:

~~~java
@Component
public class MaintenanceJobs {

    @Scheduled(fixedDelay = 60_000)
    public void pollQueue() {
        // Run again 60 seconds after the previous execution completes.
    }

    @Scheduled(fixedRate = 300_000)
    public void refreshMetrics() {
        // Scheduled 5 minutes apart.
    }

    @Scheduled(
            cron = "0 0 2 * * *",
            zone = "Asia/Ho_Chi_Minh")
    public void dailyMaintenance() {
        // Run at 02:00 Vietnam time.
    }
}
~~~

With cron, the zone attribute is very important. If zone is omitted, the schedule depends on the default timezone of the runtime environment. Two deployments in different timezones may run the same cron expression at different UTC times.

### 1.2. fixedDelay and fixedRate Do Not Mean the Same Thing

With fixedDelay, the interval is measured from when the previous run finishes. If a task takes 20 seconds and the delay is 30 seconds, the next run is scheduled 30 seconds after the previous run completes.

With fixedRate, expected start times are spaced by a fixed interval. If a task takes longer than the period, the next run may start late compared to its scheduled time. fixedRate should not be understood as guaranteeing that the method always runs at exact timestamps, nor should it be assumed that runs will automatically execute in parallel.

If a method has multiple @Scheduled declarations or the application has multiple schedulers/workers, overlapping executions can occur. For tasks that update data, a mechanism to prevent concurrent execution and protect side effects is required.

## 2. What Happens to Background Work During Checkpoint?

A checkpoint saves the process state. Beans, scheduler objects, scheduled futures, executors, and part of the task state may be captured in the snapshot. However, external systems continue operating while the process is paused.

Example of a sync task:

~~~text
Spring application
     │
     ▼
@Scheduled method
     │
     ▼
Read data from database
     │
     ▼
Call partner API
     │
     ▼
Write result and update cursor
     │
     ▼
Complete
~~~

If a checkpoint occurs in the middle of this flow, several situations can arise:

- An active task is frozen mid-I/O operation or between two business steps.
- Database transactions or HTTP connections may time out while the process is paused.
- A message consumer may lose its lease or have its messages dispatched by the broker to another instance.
- A cron schedule may have one or more scheduled runs that have already passed.
- A retry delay may have already expired before the process is restored.
- The scheduled executor may have tasks waiting in its queue.
- A restored task may resume from an in-memory state that is no longer consistent with external systems.

Do not infer that a task will automatically restart from the beginning or be guaranteed to run once. CRaC restores process state; it does not create a distributed transaction across the JVM, database, message broker, and external APIs.

## 3. Defining a Policy for Missed Runs

Before integrating CRaC, each background job needs a clear policy for the duration the process was paused.

Four common policies:

| Policy | Behavior after restore | Example |
|---|---|---|
| Catch up | Run overdue executions that have not been performed yet | Syncing missed partitions or data ranges |
| Skip missed runs | Ignore passed timestamps and wait for the next scheduled run | Periodic cache refresh, tasks that only need the latest data |
| Coalesce | Merge multiple missed runs into a single execution | Recomputing a dashboard or aggregating current state |
| Resume remaining delay | Continue with the remaining time before the next run | A workflow with a relative wait duration |

For example, a cron job runs every minute. The process is checkpointed for 10 minutes:

- Catch up may generate 10 catch-up runs.
- Skip missed runs only executes at the next future cron timestamp.
- Coalesce runs once to process all new data since the most recent successful run.
- Resume remaining delay is only suitable when the application has a concept of remaining delay to continue.

There is no single right policy for every job. Daily reports, cache refreshes, message consumers, and payment processing jobs have different requirements.

### 3.1. Prefer Persisting Business State

If a task processes data over time ranges, persist the completed cursor or watermark, such as lastProcessedAt or the last committed ID. After restore, the job queries from the committed cursor up to the current time.

Do not rely solely on the number of times a timer has fired. A timer may miss runs during checkpoint, yet the data to be processed still exists in the database or message broker.

### 3.2. Idempotency and Duplicate Processing Prevention

Catch-up or retries can cause the same unit of work to be submitted again. The task needs an idempotency key, unique constraint, transactional outbox/inbox, or an appropriate deduplication mechanism.

For example, if a job sends invoices, it should not just check a boolean in the heap to know whether an invoice was sent. The sent status must be durably recorded in the business-owning system so subsequent runs do not send duplicates.

## 4. Stopping Background Work Before Checkpoint

Before checkpoint, the application should transition into a state where it stops accepting new work. Typical steps include:

1. Transition readiness or job admission to NOT_READY/PAUSED.
2. Stop accepting new messages or stop polling work sources.
3. Prevent new @Scheduled invocations from starting business processing.
4. Wait for active tasks to complete within a bounded timeout.
5. Commit/rollback transactions and return connections to the pool.
6. Close resources that must be recreated after restore.
7. Only complete the callback once the process state is safe for checkpoint.

Merely canceling a ScheduledFuture does not guarantee that a running task has stopped. Nor should you call shutdownNow() and assume all tasks have finished; this method only sends an interrupt to threads, and tasks must cooperate with interruption.

### 4.1. Distinguishing the Scheduler from Running Tasks

The scheduler is responsible for triggering schedules. The task is the actual work. Stopping the scheduler can prevent new runs, but tasks already started by the executor can still continue running.

A shutdown sequence needs to manage both:

~~~text
PAUSE SCHEDULER / JOB ADMISSION
             │
             ▼
Prevent new tasks from entering business logic
             │
             ▼
Wait for active task count = 0
             │
             ▼
Close dependent database/client/resources
             │
             ▼
Checkpoint
~~~

If tasks cannot complete within the deadline, report an error and reject the checkpoint according to policy. Do not let the callback wait indefinitely.

## 5. Using a Gate to Block New Tasks and Drain Running Tasks

An easily controllable approach with @Scheduled is to let the annotated method remain managed by Spring, while placing a gate in front of the business logic. The gate prevents new runs from entering when the application prepares for checkpoint and tracks the number of active tasks.

~~~java
package com.example.jobs;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

public final class BackgroundJobGate {

    private final Object monitor = new Object();

    private boolean accepting = true;
    private int activeTasks;

    public boolean enter() {
        synchronized (monitor) {
            if (!accepting) {
                return false;
            }

            activeTasks++;
            return true;
        }
    }

    public void exit() {
        synchronized (monitor) {
            activeTasks--;

            if (activeTasks == 0) {
                monitor.notifyAll();
            }
        }
    }

    public void pauseAndAwait(Duration timeout)
            throws InterruptedException, java.util.concurrent.TimeoutException {

        long started = System.nanoTime();
        long timeoutNanos = timeout.toNanos();

        synchronized (monitor) {
            accepting = false;

            while (activeTasks > 0) {
                long elapsed = System.nanoTime() - started;
                long remaining = timeoutNanos - elapsed;

                if (remaining <= 0) {
                    // Checkpoint did not proceed; let the application run again.
                    accepting = true;
                    monitor.notifyAll();

                    throw new java.util.concurrent.TimeoutException(
                            "Background tasks did not drain before checkpoint");
                }

                TimeUnit.NANOSECONDS.timedWait(monitor, remaining);
            }
        }
    }

    public void resume() {
        synchronized (monitor) {
            accepting = true;
            monitor.notifyAll();
        }
    }
}
~~~

The gate uses the same monitor for two actions: checking accepting and incrementing activeTasks. Thus, a pause cannot happen between the moment a task is accepted and the moment it is recorded as active.

The task must call exit() inside a finally block so the counter is always decremented even when business logic throws an exception.

### 5.1. Wrapping a @Scheduled Method with a Gate

~~~java
package com.example.jobs;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ReconciliationJob {

    private final BackgroundJobGate gate;
    private final ReconciliationService service;

    public ReconciliationJob(
            BackgroundJobGate gate,
            ReconciliationService service) {
        this.gate = gate;
        this.service = service;
    }

    @Scheduled(fixedDelay = 30_000)
    public void reconcile() {
        if (!gate.enter()) {
            return;
        }

        try {
            service.reconcile();
        } finally {
            gate.exit();
        }
    }
}
~~~

When the gate is paused, Spring may still invoke the method on schedule, but the method exits immediately before executing business logic. This prevents new processing and lets the callback know when previously entered tasks have finished.

The gate does not itself alter the internal schedule of TaskScheduler. Whether a run is skipped, runs due, or catches up after restore still depends on the scheduler and trigger in use. If an exact missed-run policy is required, manage next-run time explicitly as shown in a later section.

## 6. Connecting the Gate to a CRaC Resource

You can create a Resource bean to pause and drain work before checkpoint, then open the gate after restore:

~~~java
package com.example.jobs;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.concurrent.TimeoutException;

@Component
public class BackgroundJobsCracResource implements Resource {

    private final BackgroundJobGate gate;

    public BackgroundJobsCracResource(BackgroundJobGate gate) {
        this.gate = gate;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        try {
            gate.pauseAndAwait(Duration.ofSeconds(20));
        } catch (InterruptedException interrupted) {
            gate.resume();
            Thread.currentThread().interrupt();
            throw interrupted;
        } catch (TimeoutException timeout) {
            gate.resume();
            throw timeout;
        }
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) {
        gate.resume();
    }
}
~~~

In the example, if tasks do not drain within 20 seconds, the callback reports an error so the checkpoint fails according to policy. The gate is reopened because the process continues running after a failed checkpoint. If the thread is interrupted, the interrupt status is preserved.

This is a minimal pattern. A real application needs to coordinate readiness, schedulers, worker pools, and the resources used by jobs. Do not just pause the gate and ignore the state of the database or HTTP clients.

### 6.1. Registering in Dependency Order

Suppose a job requires the database, and the HTTP server continues accepting requests while the application runs:

~~~text
Resource registration:
1. DatabasePoolResource
2. BackgroundJobsCracResource
3. HttpServerResource

beforeCheckpoint (reverse order):
1. HttpServerResource stops accepting requests
2. BackgroundJobsCracResource pauses/drains jobs
3. DatabasePoolResource closes pool

afterRestore (forward order):
1. DatabasePoolResource recovers pool
2. BackgroundJobsCracResource opens gate
3. HttpServerResource accepts requests
~~~

The order above is an example for a specific context and dependency graph. If a job depends on additional resources, arrange resource callbacks so dependencies are ready before the gate is opened. Do not register a resource twice such that two callbacks manage the same scheduler or connection pool.

## 7. Explicitly Configuring TaskScheduler in Spring Boot

For applications with many scheduled jobs, configure the scheduler explicitly to control threads and observe activity:

~~~java
package com.example.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration
@EnableScheduling
public class SchedulerConfiguration {

    @Bean
    public TaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();

        scheduler.setPoolSize(4);
        scheduler.setThreadNamePrefix("scheduled-job-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(20);

        return scheduler;
    }
}
~~~

Pool size should be based on the number of jobs, execution duration, and I/O intensity. A pool that is too small can delay jobs; a pool that is too large can create excessive threads and increase load on databases or external services.

The shutdown properties help Spring wait for tasks during a normal application context shutdown. They do not by themselves form a complete CRaC policy. Checkpoint callbacks must be explicitly integrated to stop admission, drain work, and decide how to continue after restore.

If the Spring Framework version in use provides a pause/resume mechanism for the scheduler, you can leverage that API to control the schedule. Confirm the actual version and test behavior during pause, resume, shutdown, and restore. Do not assume all TaskScheduler implementations support the same lifecycle API.

## 8. Handling Missed Schedules with Deadlines and Next-Run Times

For jobs with explicit schedule requirements, store the next run time as an Instant rather than relying solely on a delay sitting in the scheduler queue.

For example, a job needs to run every 5 minutes and skip past timestamps. After each completion, the application computes nextRunAt as the next future timestamp. Before checkpoint, stop the scheduler and preserve nextRunAt. After restore, recompute the delay:

~~~java
Instant now = clock.instant();

Duration delay =
        Duration.between(now, nextRunAt);

if (delay.isNegative()) {
    delay = Duration.ZERO;
}

taskScheduler.schedule(job, nextRunAt);
~~~

TaskScheduler can accept an Instant timestamp for scheduling. Choose a specific policy when nextRunAt is already in the past:

- Run once immediately.
- Skip and compute the next timestamp.
- Coalesce data from the missed timestamps.
- Catch up with a bounded number of runs.

Do not simply call schedule with a past timestamp and assume the scheduler will follow the desired business policy.

### 8.1. fixedDelay After Restore

If the policy is fixedDelay, the next run time should be calculated from when the most recent run completed or from restore time depending on the goal.

For example:

- If checkpoint duration is not counted toward the wait time, set nextRunAt = restoreTime + delay after restore.
- If checkpoint duration is counted toward the wait time, save the absolute deadline before checkpoint and compute the remaining time after restore.
- If the job is already overdue, run once immediately or skip according to policy.

### 8.2. fixedRate After Restore

fixedRate is based on a time cadence. If the process is paused for a long time, many timestamps may have passed. The application must decide whether to catch up, skip, or coalesce.

For jobs that do not need to catch up every missed timestamp individually, the next future timestamp can be calculated based on the period and schedule start time. Do not repeat every missed run if each execution merely refreshes the same current state.

### 8.3. Cron and Timezones

Cron is a calendar-based schedule. Store the cron expression, ZoneId, and missed-run policy. After restore, use the current time along with the zone to compute the next run.

For example, a 02:00 schedule in Asia/Ho_Chi_Minh must be computed using that timezone. Do not add 24 hours to the previous Instant as a universal substitute for daily schedules; calendar schedules can be affected by timezones and daylight saving time in other regions.

## 9. When to Use @Scheduled vs. When a Custom Scheduler Is Needed

@Scheduled is suitable for simple jobs with a steady schedule and an easily defined post-restore policy. For example: refreshing a cache, running health checks, or executing cleanup that can be safely repeated.

Use a custom scheduler or stateful job orchestration when:

- Exact nextRunAt tracking is needed.
- Missed runs must be caught up or coalesced.
- Jobs require durable retry/backoff state.
- There are multiple steps with checkpoints between business steps.
- Concurrency must be controlled per tenant/partition.
- Duplicate runs across multiple instances must be prevented.
- The work is long-running or has critical side effects.

A custom scheduler can persist schedule state in a database and use TaskScheduler only to wake up workers. The database is the source of truth for what work needs to run; the JVM timer is merely the wake-up mechanism.

## 10. Other Types of Background Work in Spring Boot

CRaC does not affect only @Scheduled. The following workloads also need corresponding lifecycle management.

### 10.1. @Async and TaskExecutor

@Async submits methods to an executor. Before checkpoint, stop accepting new tasks and wait for running tasks to complete. If tasks remain in the queue, decide whether to retain, cancel, or persist them into a durable queue.

Do not assume tasks in an in-memory queue are durably processed. If work must survive process restarts, persist the job to a database or message broker before the executor executes it.

### 10.2. Message Listeners and Consumers

A consumer may hold connections, sessions, or leases from the broker. Before checkpoint:

- Stop accepting new messages.
- Wait for in-flight messages to finish processing within the deadline.
- Ack messages after side effects have committed.
- Nack/requeue unfinished messages according to the broker's semantics.
- Close or pause the consumer according to the library.

After restore, reconnect to the broker, recover subscriptions, and process remaining messages. Do not rely on an old consumer object or a flag in the heap to prove a message has not been processed on another instance.

### 10.3. Executor Loops and Self-Managed Worker Threads

A loop thread typically needs a stop flag, interruption, or wake-up mechanism. Before checkpoint, stop accepting work, bring the loop to a safe point, and wait for the thread to terminate. After restore, create new worker threads based on the saved state.

Do not keep a Thread object on the heap and assume that thread automatically resumes in the proper state merely because the object still exists. Thread lifecycle must be managed according to the capabilities of the JDK/CRaC runtime and the library's resource API.

### 10.4. Retry and Backoff

A 5-minute retry delay may have already expired during checkpoint. Store retryAt as an Instant or persist retry state durably. After restore, recompute the remaining time and enforce retry limits.

Do not reset the retry counter to 0 simply because the process restored. Doing so could cause the system to retry a failing request indefinitely or place heavy load on a struggling dependency.

## 11. Multiple Instances and Distributed Scheduling

If the application runs multiple replicas, each replica may restore the same @Scheduled job. This can cause the job to run multiple times after restore.

For example, 5 instances all have a cleanup schedule at 02:00. When all 5 instances restore at the same time, each instance may trigger cleanup.

Common mitigations:

- Distributed locks or scheduler clustering.
- Leader election.
- Partition work by tenant or shard.
- Unique constraints and idempotency keys.
- Database job table with time-bounded claim/lease.
- Jitter to reduce simultaneous request bursts.

Distributed locks must be revalidated after restore. An old lease may have expired while the process was paused, and another instance may have become the owner. Use fencing tokens or versions so the data system rejects operations from stale owners.

Do not use synchronized or AtomicBoolean inside a single JVM to guarantee a singleton job across the cluster. Those mechanisms only coordinate threads within the same process.

## 12. Transactions and Background Job Safe Points

A background job should have clear transaction boundaries. If a task has multiple steps, persist progress after each committed step so it can resume after restore without repeating side effects.

Example:

~~~text
Job starts
   │
   ▼
Read data batch
   │
   ▼
Process batch
   │
   ▼
Commit result + update cursor
   │
   ▼
Next batch
~~~

If a checkpoint occurs between two batches, the job can resume from the committed cursor. If a checkpoint occurs between the write operation and the cursor update, both operations need to be in the same transaction or have an idempotency mechanism to avoid missing or duplicating data.

Do not try to hold a JDBC transaction open across a checkpoint. The database server may time out or close the session while the process is paused. Before checkpoint, drain tasks and finish transactions; after restore, create new connections and resume from durable state.

## 13. Readiness and Work Activation Order After Restore

Do not enable all schedulers, consumers, and the HTTP server at the same time if they depend on one another.

A common order:

~~~text
Restore process
      │
      ▼
Load runtime configuration/secrets
      │
      ▼
Restore database and external clients
      │
      ▼
Validate dependencies
      │
      ▼
Resume background workers
      │
      ▼
Start accepting HTTP traffic
      │
      ▼
Application READY
~~~

Depending on the system, background workers may need to run before or after the HTTP listener. For example, if a worker generates data that incoming requests must read, the worker may need to complete its bootstrap step before readiness transitions to READY. If the worker can run independently, it can be enabled once dependencies are ready.

What matters is that readiness accurately reflects serving capability. Do not mark READY merely because the Spring context has been restored. Check the database, broker, secret provider, and required resources.

## 14. Checking and Observing Jobs After Restore

Each background job should log the following information:

- Job name and configuration version.
- Expected next run time.
- Actual start/end time.
- Processing duration.
- Number of active and queued tasks.
- Committed cursor or watermark.
- Retry count and most recent error.
- Missed-run policy applied after restore.

Avoid logging secrets, tokens, or sensitive business data.

Additional metrics can be added:

| Metric | Meaning |
|---|---|
| job_active_tasks | Number of currently running tasks |
| job_last_success_timestamp | Timestamp of the most recent success |
| job_next_run_timestamp | Next expected run timestamp |
| job_duration_seconds | Duration of each run |
| job_skipped_runs_total | Number of skipped timestamps |
| job_catchup_runs_total | Number of catch-up runs |
| job_restore_failures_total | Number of worker restore failures |
| job_checkpoint_drain_seconds | Drain duration before checkpoint |

After restore, compare nextRunAt with the current time to confirm the missed-run policy has been applied. If there are multiple instances, include the instance ID and fencing token in logs to distinguish owners.

## 15. Testing Checkpoint/Restore Scenarios

A test that only verifies the application restores and endpoints return HTTP 200 is not enough. Background job behavior must also be tested.

| Scenario | What to verify |
|---|---|
| Checkpoint when no task is active | Gate pauses, restore opens the gate, and schedule resumes according to policy |
| Checkpoint while a task is running | Callback waits for task drain or fails on timeout |
| Task does not finish within deadline | Checkpoint is rejected in a controlled manner; application continues running |
| Multiple cron timestamps missed | Catch up/skip/coalesce follows policy |
| fixedDelay waiting | Remaining delay is computed according to policy |
| Database unavailable after restore | Job does not run while dependency is not READY |
| Message lease expired | Consumer reacquires/revalidates lease |
| Two replicas restore simultaneously | Job does not create duplicate side effects outside policy |
| Task fails after restore | Retry/backoff and durable state operate properly |
| Restore callback fails | Readiness does not falsely transition to READY |

Combine unit tests for the gate and schedule with integration tests on the exact CRaC-enabled JDK, Spring Framework/Spring Boot version, scheduler implementation, and CRIU environment intended for deployment.

### 15.1. Testing the Gate

Three scenarios can be tested:

1. When accepting=true, enter() returns true and activeTasks increments.
2. When a task is active, pauseAndAwait() waits until exit() is called.
3. After pause completes, enter() returns false until resume() is called.

Add a timeout test to ensure the gate reopens itself when checkpoint cannot proceed. For long-running tasks, test interruption and deadlines to avoid hanging the callback.

### 15.2. Testing the Missed-Run Policy

Use a controllable Clock to simulate:

- Before checkpoint, nextRunAt is 2 minutes away.
- Restore after 10 minutes.
- The skip policy chooses the future cron timestamp.
- The catch-up policy creates one or a bounded number of catch-up jobs.
- The coalesce policy creates only a single aggregated run.

There is no need to wait 10 real minutes to test deadline logic. Use Clock.fixed or a mock Clock for schedule calculation; then run an actual integration test to confirm the scheduler behaves properly with the runtime.

## 16. Common Pitfalls

| Mistake | Consequence | How to handle |
|---|---|---|
| Assuming @Scheduled automatically recalculates all runs after restore | Job may run catch-up or late unexpectedly | Define a missed-run policy and test the actual scheduler |
| Only canceling ScheduledFuture | Running tasks may still continue | Drain active tasks and wait for completion |
| Calling shutdownNow and proceeding directly to checkpoint | Tasks may not have stopped; transactions may be unsafe | Wait for termination with a timeout |
| Not blocking new tasks during drain | Active count may rise again | Use an admission gate |
| Opening scheduler before database | Job accesses dependencies that are not ready | Order callbacks by dependencies |
| Running cron on every replica | Side effects executed multiple times | Distributed lock, leader election, or idempotency |
| Keeping retry delay via nanoTime across restore | Remaining time does not match policy | Store deadline/Instant and recalculate |
| Not persisting business cursor | Catch-up may miss or duplicate processing | Persist cursor/watermark durably |
| Task holding transaction across checkpoint | Connection/session may already be lost after restore | Drain and commit/rollback before checkpoint |
| Opening readiness before workers are ready | Requests see inconsistent state | Only mark READY after required dependencies work |

## 17. Process for Designing @Scheduled and Background Work for CRaC

For each job, determine:

1. Does the job use fixedDelay, fixedRate, cron, or is it triggered by a queue?
2. Can it run concurrently across multiple threads or multiple replicas?
3. At what safe points can a running job stop?
4. How long does it need to drain before checkpoint?
5. If the checkpoint spans a long period, will missed runs be caught up, skipped, or coalesced?
6. Which progress state must be persisted durably?
7. Which database, broker, secret, or client does the job require?
8. Which resources must be ready before resuming?
9. How are idempotency and duplicate processing prevention ensured?
10. Which readiness checks and metrics prove the worker is operational after restore?

A Spring Boot application using CRaC should manage background work as part of the process lifecycle. Stop admission before checkpoint, drain running work, handle transactions and leases according to policy, and recalculate schedules after restore. For simple jobs, @Scheduled combined with a gate may suffice; for jobs with catch-up, retry, or strict scheduling requirements, use an explicitly managed scheduler and business state.

What must be guaranteed after restore is that each job runs according to its defined policy, uses valid dependencies, and does not produce duplicate side effects. Restoring the Spring context or continuing to invoke @Scheduled methods is only part of the process; background worker readiness must be verified separately before the application resumes serving.
