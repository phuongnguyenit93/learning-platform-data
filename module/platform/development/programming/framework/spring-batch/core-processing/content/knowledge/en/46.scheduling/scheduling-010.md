# Run Windows and Deadlines in Spring Batch

In batch operations, a 01:00 trigger schedule does not answer what happens if source data arrives late, the scheduler restarts at 02:00, or the job is still running when reporting systems begin serving users. To govern these scenarios, you must define a **run window** (the interval during which starting or executing is allowed) and a **deadline** (the cutoff by which results must be ready).

This lesson belongs to **Spring Batch Core Processing → Scheduling** and covers modeling time, validating run windows before starting, coordinating Spring Batch with schedulers, handling late requests, bounding restarts, monitoring deadlines, and testing time boundaries. Examples use Java 17, Spring Boot 3.x, Spring Batch 5.x, JUnit 5, and the `Asia/Ho_Chi_Minh` timezone.

## 1. Distinguishing Trigger Schedule, Run Window, and Deadline

Suppose `dailyReportJob` produces a report for a business date. Operations agrees on:

| Milestone | Local time | Role |
| --- | --- | --- |
| Planned start | 01:00 | Scheduler issues the first launch request |
| Window open | 01:00 | Allowed to start if data is ready |
| Latest start / start cutoff | 02:30 | After this point, no new run may start |
| Finish deadline | 04:00 | Report must be complete and ready for consumption |
| Downstream consumption | 05:00 | Downstream services begin reading the report |

```text
01:00                02:30                  04:00        05:00
  |--------------------|----------------------|------------|
  ^                    ^                      ^            ^
  window open          start cutoff           deadline     consumers
  |<-- allowed start -->|

  launch 01:15 ────────── finished 02:45            => on time
  launch 02:15 ────────────────── finished 04:10    => missed deadline
  request 02:45                                     => no new start
```

By convention in this lesson, the **launch** window is `[01:00, 02:30)`: inclusive of 01:00, exclusive of 02:30. A run started at 02:15 may continue past 02:30, because **start cutoff is not a forced job-stop timestamp**.

| Concept | Question | Example |
| --- | --- | --- |
| Trigger time | When does the scheduler send a request? | 01:00 |
| Run window | When may start requests be accepted? | `[01:00, 02:30)` |
| Data readiness | Is input complete and stable? | Upstream file marked `READY` |
| Start cutoff | When do we stop attempting new starts? | 02:30 |
| Finish deadline | By when at the latest must output be usable? | 04:00 |
| Execution timeout | How long may a single execution run? | 90 minutes from start |
| SLA/SLO | Target rate of meeting commitments? | E.g., 99% of days ready before 04:00 |

A **relative timeout** is not an **absolute deadline**: a 90-minute timeout starts when the job begins, whereas a 04:00 deadline is fixed to the operational day. If a job launches late, the timeout may still have headroom while results already miss the deadline. When defining a deadline, clarify whether `COMPLETED` status suffices, or whether database commits, output file verification, or downstream publishing must also finish.

## 2. How Does Spring Batch Coordinate with a Scheduler?

Spring Batch manages `Job`, `Step`, transactions, retries, restarts, and metadata in `JobRepository`. It does not replace full time-based scheduling and orchestration. Common choices:

- **Spring `@Scheduled`**: the running app fires cron triggers itself; simple for few schedules and long-lived apps.
- **Quartz**: persistent triggers, misfire policies, and rich schedules when configured properly.
- **Cron / Windows Task Scheduler**: starts a `java -jar` process on schedule.
- **Kubernetes CronJob or orchestrator**: spawns periodic workloads and manages concurrency/retries at the orchestration layer.

The flow should validate policy right **when receiving a launch request**:

```text
Scheduler ──> Launch request(t, scheduledDate)
                      |
                      v
                RunWindowPolicy
                   |          |
            outside window    in window
                   |          |
               skip/alert     v
                          Data readiness
                           |        |
                       NOT READY   READY
                           |        |
                        wait/retry  v
                              JobLauncher
                                  |
                                  v
                               Spring Batch
                                  |
                                  v
                           Deadline monitor
```

A cron expression only describes when a trigger **should have fired**. If the system hits an outage, requests arrive late. Never rely on “cron only runs at 01:00” to assume jobs always start inside the run window.

## 3. Business Date, Timezone, and Windows Crossing Midnight

### 3.1. Defining the Business Timezone

Never let business dates depend on a container's or laptop's default timezone. For example:

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate scheduledDate = LocalDate.of(2026, 11, 16);

Instant open = scheduledDate.atTime(1, 0)
        .atZone(zone).toInstant();
Instant cutoff = scheduledDate.atTime(2, 30)
        .atZone(zone).toInstant();
Instant deadline = scheduledDate.atTime(4, 0)
        .atZone(zone).toInstant();
```

`Instant` is a point on the UTC timeline, ideal for comparisons and logs; `ZonedDateTime` expresses local wall-clock meaning in a region. `2026-11-16` at 01:00 in `Asia/Ho_Chi_Minh` equals `2026-11-15T18:00:00Z`.

**Scheduled date does not necessarily equal business date.** For example, the scheduler runs at 01:00 on Nov 16 to process Nov 15 revenue:

```java
LocalDate scheduledDate = LocalDate.now(zone);
LocalDate businessDate = scheduledDate.minusDays(1);
```

Only use `minusDays(1)` when that matches the job's data contract. For backfills, pass the target `businessDate` explicitly rather than reading the current date.

### 3.2. Run Windows Crossing Midnight

Another job is allowed to start from 23:00 on day D to 02:00 on day D+1. Comparing hours with `time >= 23:00 && time < 02:00` is wrong. Instead, construct **two full date-time instants**:

```java
Instant start = businessDate.atTime(23, 0)
        .atZone(zone).toInstant();

Instant end = businessDate.plusDays(1).atTime(2, 0)
        .atZone(zone).toInstant();

boolean allowed = !now.isBefore(start) && now.isBefore(end);
```

Here `now` is an `Instant`. In regions with daylight saving time (DST), a local hour may be skipped or repeated; define explicit handling. `Asia/Ho_Chi_Minh` does not currently observe DST, yet multi-region code should still use `ZoneId` instead of assuming fixed offsets.

## 4. Modeling the Run Window as a Dedicated Policy

Instead of scattering time checks across tasklets, services, and scripts, isolate a **pure time-logic** object. The policy accepts the current instant and window date, returning whether starting is permitted and the corresponding deadline.

`RunWindowPolicy.java`:

```java
package com.example.batch.schedule;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

import org.springframework.stereotype.Component;

@Component
public class RunWindowPolicy {

    public static final ZoneId ZONE =
            ZoneId.of("Asia/Ho_Chi_Minh");

    public record Decision(
            boolean allowed,
            String reason,
            Instant finishDeadline) {}

    public Decision evaluate(
            Instant requestedAt, LocalDate scheduledDate) {

        Instant open = scheduledDate.atTime(1, 0)
                .atZone(ZONE).toInstant();
        Instant cutoff = scheduledDate.atTime(2, 30)
                .atZone(ZONE).toInstant();
        Instant deadline = scheduledDate.atTime(4, 0)
                .atZone(ZONE).toInstant();

        if (requestedAt.isBefore(open)) {
            return new Decision(
                    false, "BEFORE_WINDOW", deadline);
        }
        if (!requestedAt.isBefore(cutoff)) {
            return new Decision(
                    false, "START_CUTOFF_PASSED", deadline);
        }
        return new Decision(true, "IN_WINDOW", deadline);
    }
}
```

Boundaries are explicit: exactly 01:00 is allowed to start, while exactly 02:30 is no longer allowed. `scheduledDate` aligns with the schedule and need not equal the `businessDate` the job reads.

Separating the policy lets launch APIs, internal schedulers, and external orchestrators share one rule. Additional checks like **upstream readiness**, **remaining time budget**, and **backfill authorization** can be added as distinct decision steps.

## 5. Integrating `@Scheduled` and `JobLauncher`

In Spring Framework, `@Scheduled` cron uses six fields: **second, minute, hour, day of month, month, day of week**. To attempt launching every 15 minutes during hours 01 and 02:

```java
@Scheduled(
    cron = "0 0,15,30,45 1-2 * * *",
    zone = "Asia/Ho_Chi_Minh")
```

This expression fires at 01:00, 01:15, ..., 02:45. The policy in section 4 rejects requests at 02:30 and 02:45. Repeated triggers help when source data arrives late or when jobs need restarts, provided duplicate processing is prevented.

When using `@Scheduled` to drive launches, disable Spring Boot's startup auto-runner:

```properties
spring.batch.job.enabled=false
```

Otherwise, Boot may run the job immediately at application context startup while the scheduler also invokes it on schedule.

### 5.1. Using `Clock` for Time Testability

```java
package com.example.batch.schedule;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ClockConfig {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

Take `Instant` from the clock and interpret it in `RunWindowPolicy.ZONE` to determine the schedule date; in tests, supply `Clock.fixed(...)`.

### 5.2. Scheduler Actually Calling Spring Batch

Assume the application context has a `Job` bean named `dailyReportJob`:

```java
package com.example.batch.schedule;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.repository.JobExecutionAlreadyRunningException;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRestartException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ScheduledDailyReport {

    private static final Logger log =
            LoggerFactory.getLogger(ScheduledDailyReport.class);

    private final JobLauncher launcher;
    private final Job dailyReportJob;
    private final RunWindowPolicy policy;
    private final Clock clock;

    public ScheduledDailyReport(
            JobLauncher launcher,
            @Qualifier("dailyReportJob") Job dailyReportJob,
            RunWindowPolicy policy,
            Clock clock) {
        this.launcher = launcher;
        this.dailyReportJob = dailyReportJob;
        this.policy = policy;
        this.clock = clock;
    }

    @Scheduled(
        cron = "0 0,15,30,45 1-2 * * *",
        zone = "Asia/Ho_Chi_Minh")
    public void launchWithinWindow() {
        Instant now = clock.instant();
        LocalDate scheduledDate =
                LocalDate.ofInstant(now, RunWindowPolicy.ZONE);

        RunWindowPolicy.Decision decision =
                policy.evaluate(now, scheduledDate);
        if (!decision.allowed()) {
            log.info("Skip launch: date={}, reason={}",
                    scheduledDate, decision.reason());
            return;
        }

        // If the job processes the previous day, replace with
        // scheduledDate.minusDays(1) per business contract.
        LocalDate businessDate = scheduledDate;

        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", businessDate.toString(), true)
                .addString("region", "VN", true)
                .toJobParameters();

        try {
            JobExecution execution =
                    launcher.run(dailyReportJob, parameters);

            log.info("Job execution: id={}, date={}, status={}",
                    execution.getId(), businessDate,
                    execution.getStatus());

            if (execution.getStatus() == BatchStatus.FAILED) {
                log.error("Batch execution failed: id={}",
                        execution.getId());
            }
        } catch (JobInstanceAlreadyCompleteException e) {
            log.info("Already completed: {}", businessDate);
        } catch (JobExecutionAlreadyRunningException e) {
            log.info("Already running: {}", businessDate);
        } catch (JobRestartException
                | JobParametersInvalidException e) {
            log.error("Could not start batch: {}", businessDate, e);
        }
    }
}
```

Enable scheduling:

```java
@SpringBootApplication
@EnableScheduling
public class ReportBatchApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReportBatchApplication.class, args);
    }
}
```

Imports are `org.springframework.boot.autoconfigure.SpringBootApplication`, `org.springframework.boot.SpringApplication`, and `org.springframework.scheduling.annotation.EnableScheduling`.

This example intentionally keeps the two **identifying parameters** `businessDate` and `region` stable for the same date/region. Adding a random `run.id` on every trigger would create a new `JobInstance` each time and duplicate processing. With a persistent `JobRepository`:

- A `COMPLETED` instance normally does not rerun; the launcher throws `JobInstanceAlreadyCompleteException`.
- An already-running execution of the same instance is rejected with `JobExecutionAlreadyRunningException`.
- A `FAILED` instance can be **restarted** with the same identifying parameters if the job allows it.

Never restart automatically without limits: enforce error classification, maximum restart counts, intervals between attempts, and remaining time budget.

**Example limitations:** `JobLauncher` may be configured synchronously or asynchronously. With an async launcher, `run(...)` returns while the job is still `STARTING`/`STARTED`; final status must be tracked separately. A long-running scheduled method can also occupy a scheduler thread. Size pools or dispatch architecture for actual runtime.

`launchWithinWindow()` only blocks **starts outside the window**. It does not monitor whether the job finishes before 04:00; deadlines require a separate mechanism.

## 6. Checking Remaining Time Budget Before Launch

Beyond the start cutoff, operations can enforce a *latest safe start*: the latest start time with enough remaining budget to finish before the deadline.

Example with a 04:00 deadline:

| Component | Budget |
| --- | ---: |
| Expected runtime per design limit | 75 minutes |
| Retry/recovery buffer | 15 minutes |
| Publish and downstream margin | 10 minutes |
| **Total** | **100 minutes** |

Under these assumptions, starting after 02:20 leaves fewer than 100 minutes until 04:00. Even if the administrative start cutoff is 02:30, a budget-enforcing policy picks the earlier bound.

```text
remaining_budget = finish_deadline - now
required_budget = expected_runtime + retry_budget + safety_margin

Allow start when:
  in run window
  AND upstream READY
  AND remaining_budget >= required_budget
```

Java example:

```java
Duration requiredBudget = Duration.ofMinutes(100);
Instant lastSafeStart = finishDeadline.minus(requiredBudget);
boolean enoughTime = !now.isAfter(lastSafeStart);
```

Here `finishDeadline` and `now` are `Instant`s. Add this logic to `RunWindowPolicy` to return `INSUFFICIENT_TIME_BEFORE_DEADLINE` when budget is short. Base runtime estimates on real operational data with headroom for volume spikes and retries.

Still, having sufficient budget **does not guarantee** on-time completion: databases can stall, I/O can slow, or source data can contain errors. Actual deadline monitoring remains necessary.

## 7. Deadline Monitoring and Handling Overruns

Setting a 04:00 milestone only matters when you define **completion criteria** and **actions when incomplete**.

### 7.1. Soft Deadline vs. Hard Deadline

| Policy | Example | Action |
| --- | --- | --- |
| Soft deadline | 03:30 without output | Alert, assess ETA, let the job keep running |
| Hard deadline | 04:00 without accepted output | Record SLA breach, block publish, or request controlled stop |
| Data cutoff | No new source data accepted after 04:00 | Close snapshot, handle remaining items per rules |

**A deadline does not automatically mean killing the JVM.** Force-killing processes can leave output files or external transactions half-done. When data integrity is vital, you may flag outputs as late and let the job finish, serve fallback data, or send a graceful stop request per business contract.

A deadline monitor typically needs to:

1. Identify the exact `JobInstance` by job name and identifying parameters for the business date.
2. Read the latest `JobExecution` and step statuses from `JobExplorer` or monitoring feeds.
3. Verify whether **outputs are committed/published**, rather than looking solely at `BatchStatus.COMPLETED`.
4. At the deadline, emit metrics/alerts with `scheduledDate`, `businessDate`, `executionId`, `deadlineAt`, overrun duration, and status.
5. If policy demands stopping, send a stop request and monitor until execution truly terminates.

Spring Batch provides `JobOperator` to manage executions. Example:

```java
// executionId obtained from JobRepository / JobExplorer
// after identifying the exact execution to stop.
boolean stopRequested = jobOperator.stop(executionId);
```

This call is a **stop request**, not a promise of instant step termination. A long-blocking tasklet or I/O-bound chunk may respond only when reaching an interruption/chunk boundary. `stop(...)` can also return `false` or throw exceptions depending on execution status.

When the business requires hard deadlines, design:

- Timeouts on connections, HTTP calls, SQL queries, and I/O.
- Controllably sized chunks and transactions supporting stop/restart.
- Staging outputs; **publish only complete artifacts** to downstream.
- Idempotency, checkpoints, and post-failure resumption plans.
- Fallback rules when on-time completion is impossible.

### 7.2. Observing Metadata and Metrics

Useful log or metric fields:

```text
jobName=dailyReportJob
businessDate=2026-11-16
scheduledAt=2026-11-16T01:00:00+07:00
actualStartedAt=2026-11-16T01:15:12+07:00
finishedAt=2026-11-16T03:47:02+07:00
deadlineAt=2026-11-16T04:00:00+07:00
batchStatus=COMPLETED
outputPublished=true
deadlineMet=true
```

Example metadata query (default Spring Batch schema):

```sql
SELECT
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'dailyReportJob'
ORDER BY je.JOB_EXECUTION_ID DESC;
```

In production, filter further by identifying parameters or use `JobExplorer`, since one job has many instances across dates. Useful metrics include `scheduled_to_start_delay`, `duration`, `deadline_breaches`, `data_freshness`, and `remaining_budget_at_launch`.

## 8. Run Windows with External Schedulers

### 8.1. Cron Launching an Executable JAR

With OS cron or orchestrators that launch standalone processes, the app can use Spring Boot's auto-run mechanism:

```bash
#!/usr/bin/env bash
set -euo pipefail

BUSINESS_DATE="$1"
exec java -jar /opt/batch/report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  "businessDate=$BUSINESS_DATE" \
  region=VN
```

Here `spring.batch.job.enabled=true` (or left enabled), because Boot runs the job at JVM startup. Cron only specifies **when to invoke**; checking data readiness, run window, and deadlines still falls to the script, app, or orchestrator.

For the scheduler to detect failures, the process exit code must reflect batch outcomes. A `FAILED` `JobExecution` does not guarantee a non-zero exit code in every JVM setup; use an `ExitCodeGenerator`, custom launcher, or repository status check.

### 8.2. Kubernetes CronJob

Illustrative YAML template:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-report
spec:
  schedule: "0 1 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 5400
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: report
              image: example/report-batch:1.0
              args:
                - "--spring.batch.job.name=dailyReportJob"
                - "businessDate=2026-11-16"
                - "region=VN"
```

This is an **illustrative template**; replace the image and compute `businessDate` dynamically before production use. Specifically:

- Kubernetes cron normally uses **five fields**, unlike Spring `@Scheduled`'s six fields.
- `timeZone` requires a Kubernetes version supporting that field.
- `concurrencyPolicy: Forbid` prevents overlapping Jobs from the same CronJob, not jobs launched externally.
- `startingDeadlineSeconds: 5400` bounds startup delay for a **scheduled occurrence**, not promising completion before 04:00.
- `activeDeadlineSeconds` on `jobTemplate.spec` is a timeout **measured from when the Kubernetes Job becomes active**, not directly representing the business day's absolute deadline.
- `backoffLimit` and pod restarts can re-invoke the JAR with the same `JobParameters`. Coordinate with Spring Batch restartability and idempotency.

To monitor the 04:00 milestone, you still need a policy or monitor aware of the business date and output state.

## 9. Late Arrivals, Restarts, and Backfills

### 9.1. Late Request Still Inside the Window

Scheduled trigger was 01:00, arriving at 01:40. If data is `READY` and sufficient budget remains before the deadline, policy may allow starting. Record both planned and actual timestamps to separate **scheduler delay** from **job runtime**.

### 9.2. Request Arriving After Start Cutoff

The scheduler recovers at 03:00 when cutoff is 02:30. Do not automatically push this request onto the normal run path. Mark it `MISSED_WINDOW`, alert, and let orchestration decide whether to backfill or trigger fallback plans.

### 9.3. Job Running Past Cutoff

A job starting at 02:15 and still running at 02:40 **does not automatically violate the start window**. Only crossing the completion deadline (or hitting an explicit timeout/condition) triggers a violation.

### 9.4. Restarting a Failed Instance

Suppose the job starts at 01:00 and becomes `FAILED` at 01:20. If restarts are permitted, relaunch at 01:30 with **the same identifying `JobParameters`** so Spring Batch uses metadata and checkpoints:

```text
JobInstance(date=2026-11-16, region=VN)
├── JobExecution #1: FAILED
└── JobExecution #2: COMPLETED   (restart same instance)
```

Passing a new identifying `run.id` creates a different instance and reprocesses data from the start. Keep **restart** distinct from **running a new instance**. Retries inside an execution are also distinct from restarts.

### 9.5. Out-of-Schedule Backfills

Suppose on Nov 16 you discover Nov 10 data must be reprocessed. This is an **intentional backfill**, not a late scheduled trigger. Provide a dedicated operational path with explicit `businessDate`, proper authorization, audit reason logging, and guards against overwriting published outputs.

Never alter system clocks or delete `BATCH_*` metadata just to “squeeze into” a run window or rerun a completed job.

## 10. Testing Time Boundaries with JUnit 5

Never make tests wait until 01:00 wall-clock time. Because `RunWindowPolicy` accepts `Instant`, pass deterministic timestamps directly. When testing schedulers, inject `Clock.fixed`.

Example `RunWindowPolicyTest.java`:

```java
package com.example.batch.schedule;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;

class RunWindowPolicyTest {

    private final RunWindowPolicy policy = new RunWindowPolicy();
    private final LocalDate date = LocalDate.of(2026, 11, 16);

    @Test
    void rejectsBeforeWindow() {
        var d = policy.evaluate(
                Instant.parse("2026-11-15T17:59:59Z"), date);
        assertThat(d.allowed()).isFalse();
        assertThat(d.reason()).isEqualTo("BEFORE_WINDOW");
    }

    @Test
    void permitsExactlyAtOpening() {
        var d = policy.evaluate(
                Instant.parse("2026-11-15T18:00:00Z"), date);
        assertThat(d.allowed()).isTrue();
    }

    @Test
    void rejectsAtStartCutoff() {
        var d = policy.evaluate(
                Instant.parse("2026-11-15T19:30:00Z"), date);
        assertThat(d.allowed()).isFalse();
        assertThat(d.reason()).isEqualTo("START_CUTOFF_PASSED");
    }

    @Test
    void computesDeadline() {
        var d = policy.evaluate(
                Instant.parse("2026-11-15T19:00:00Z"), date);
        assertThat(d.finishDeadline()).isEqualTo(
                Instant.parse("2026-11-15T21:00:00Z"));
    }
}
```

These `Instant` values correspond to `Asia/Ho_Chi_Minh` times: 00:59:59, 01:00, 02:30, and 04:00 on 2026-11-16.

Stub the clock when testing `ScheduledDailyReport`:

```java
Clock testClock = Clock.fixed(
        Instant.parse("2026-11-15T18:15:00Z"),
        ZoneOffset.UTC
);
```

Mock `JobLauncher` to verify `run(...)` is invoked only when policy permits. In integration tests with `JobRepository`, also inspect `JobInstance`/`JobExecution` to prove duplicate triggers never spawn unwanted runs.

| Scenario | Time / state | Expected outcome |
| --- | --- | --- |
| Before window | 00:59:59 | Reject start |
| Exactly at opening | 01:00:00 | Allow if upstream ready |
| Mid-window | 01:45 | Allow start if budget suffices |
| Just before cutoff | 02:29:59 | Not blocked by cutoff, but evaluate deadline budget |
| Exactly at cutoff | 02:30:00 | Reject new start |
| Completed before deadline | 03:59:59 | On time if output accepted |
| Completed after deadline | 04:00:01 | Record deadline breach |
| Same instance already `COMPLETED` | Subsequent trigger | Do not rerun as a new instance |
| `FAILED` instance | Inside window | Restart if policy allows |
| Scheduler recovers late | 03:15 | Record missed window, do not auto-start |

In DST regions, add transition-day test cases because cron instants and window durations differ from normal days.

## 11. Common Design Mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Job runs twice on the same day | Each trigger generates a random `run.id` | Use stable identifying parameters |
| Job starts immediately on service boot | Boot startup runner and `@Scheduled` both enabled | Set `spring.batch.job.enabled=false` when using `@Scheduled` |
| Job starts past cutoff | Trusting cron alone without checking actual time | Evaluate policy at launch time |
| Job finishes late despite timeout remaining | Using relative timeout instead of absolute deadline | Monitor deadline against operational day |
| Fails to restart from checkpoint | Changing identifying parameters or losing metadata | Keep instance identity and persistent repository |
| Report has wrong date | Confusing scheduled date with business date | Define business date explicitly |
| Job killed with partial outputs | Force-killing process at deadline | Use graceful stop and atomic output publishing |
| Two layers retry endlessly | Orchestrator retry and Spring Batch restart lack shared budget | Bound total attempts, time, and retry conditions |
| Multiple replicas all fire cron | Each replica has its own `@Scheduled` | Single orchestrator or shared lock/coordination |
| `COMPLETED` yet downstream cannot use output | Checking `BatchStatus` only | Tie “done” to commit/publish verification |

## 12. Practice Exercise

Design a schedule for `dailyReportJob` with run window `[01:00, 02:30)`, finish deadline 04:00, and timezone `Asia/Ho_Chi_Minh`:

1. Write `RunWindowPolicy` and test all four boundary instants 00:59:59, 01:00:00, 02:29:59, and 02:30:00 with JUnit 5.
2. Add a data-readiness gate: start only if upstream file or table is `READY`.
3. Configure a scheduler polling every 15 minutes. Pass `businessDate` as a stable identifying parameter so duplicate triggers never launch independent runs.
4. Simulate the job ending `FAILED` at 01:20 and restarting at 01:30. Identify which parameters must remain identical to restart the same `JobInstance`.
5. Add a 100-minute runtime budget. Explain why at 02:21 starting must be rejected even before the 02:30 cutoff.
6. Design a 04:00 monitor: if the job is still `STARTED` or output is unpublished, record an SLA breach and trigger your chosen remediation.
7. Try deploying via Kubernetes CronJob; contrast `startingDeadlineSeconds`, `activeDeadlineSeconds`, and the 04:00 business milestone.
8. Add an administrative backfill flow during business hours for a past date, with explicit business date and duplicate-write protection.

In Spring Batch scheduling, **the run window answers when starting is permitted**, while **the deadline defines when results must be ready**. Combining both rules with `JobParameters`, `JobRepository`, restarts, timezones, and output monitoring keeps systems reliable when schedulers lag, source data shifts, or runs fail.
