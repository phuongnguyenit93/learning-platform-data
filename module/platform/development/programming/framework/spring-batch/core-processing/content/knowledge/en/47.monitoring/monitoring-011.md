# Alerting on Stalled Jobs in Spring Batch

## 1. Goal: Detecting Stuck Jobs Before Breaching SLAs

A Spring Batch job can stay in `STARTED` status for a very long time without processing any more data. For instance, a job importing 2 million transactions runs normally for 20 minutes, and then `ItemReader` blocks indefinitely on a network connection with no new records committed. Because the job has not thrown an exception, `JobRepository` still shows it as running. If the system only alerts on `BatchStatus.FAILED`, this incident may go unnoticed until the business realizes data is missing.

**Stalled job alerting** aims to detect an execution still considered running that **shows no reliable progress signals for longer than an expected threshold**. This falls under the *Monitoring* topic in the *Spring Batch Core Processing* module.

After this lesson, you will be able to:

- Distinguish **long-running jobs**, **slow jobs**, **stalled jobs**, and **missed scheduled jobs**.
- Read metadata via `JobExplorer` to inspect executions and `StepExecution` counters.
- Design progress signals from counters, checkpoints, heartbeats, and data source state.
- Pick per-job/per-step alert thresholds and reduce false positives.
- Write a stall detector unit-testable with `Clock`/`Instant`.
- Combine Micrometer, Prometheus, Alertmanager, or an equivalent observability stack to send, deduplicate, and resolve alerts.
- Build a safe handling runbook that avoids blind automatic restarts when side-effect state is unknown.

Java examples target **Java 17, Spring Boot 3.x, and Spring Batch 5.2.x**. When using Spring Batch 6.x, check package and API changes for your version.

---

## 2. What Does "Stalled" Mean?

An unchanged `readCount` does not automatically mean the batch is broken. A job might be:

- Starting the JVM, loading configuration, or creating partitions.
- Running a large SQL query inside an `ItemReader`.
- Processing a single item that takes several minutes due to an external API call.
- Waiting on a data source that business rules allow to be temporarily empty.
- Computing inside a `Tasklet` that has no item reader/writer.
- Intentionally waiting until a scheduled time window.
- Performing controlled retry/backoff.

Therefore, a practical definition must account for **the expected progress of each step type** and **maximum acceptable lag**.

| Scenario | Observed signal | Alert as stalled immediately? |
|---|---|---|
| Job running 3 hours, `writeCount` climbing steadily | Normal progress with large total runtime | Not under stall rules; may trigger a separate SLA/duration alert |
| Job `STARTED`, read/write flat for 15 minutes when commits normally happen every minute | High likelihood of stall | Yes, if threshold breached with no valid reason |
| 50,000-item chunk takes 12 minutes, not committed yet | Metadata unchanged even while CPU is working | Needs internal heartbeat/progress or chunk-aware threshold |
| Tasklet sends one processing request then waits 30 minutes for result | No item counters | Use dedicated heartbeat/phase markers and SLA |
| Job `FAILED` | Finished with error | Send failure alert separately; do not classify as stalled |
| Job absent at required run time | No new execution | Send missing-schedule alert, not stalled |
| Job `STARTED` in DB, JVM already dead | Orphaned metadata state | Alert as suspected orphan; check process/lease |
| Job intentionally `STOPPING` | Stopping in progress | Monitor stop timeout; do not use standard stall threshold |

A useful operational definition:

> A step is considered **suspected stalled** when it remains in an active processing state, produces no new business progress or checkpoint for longer than the threshold assigned to that step, and valid exceptions (grace period, waiting for data, maintenance, backoff) have been ruled out.

The word **suspected** matters: counters are observational evidence, not proof of root cause on their own.

### 2.1. Four Distinct Alert Categories

1. **Not started / missing execution:** schedule requires the job to start, yet no `JobExecution` exists for the data period.
2. **Slow / SLA risk:** job is still progressing, yet projected completion misses the deadline.
3. **Stalled progress:** job is running, yet data/phases are not advancing as expected.
4. **Orphan / dead worker:** repository still shows running state, yet the process or worker is no longer alive.

Use distinct alert types or at least distinct `reason` fields. That tells on-call responders whether to inspect the scheduler, performance, dependencies, or infrastructure.

---

## 3. Basic Monitoring Architecture

A stall detection system can be divided into four parts:

```text
Spring Batch worker
  ├── Job / Step executions
  ├── JobRepository (committed metadata)
  ├── Micrometer (durations, call counts, metrics)
  └── optional ProgressHeartbeat (phase, checkpoint, timestamp)
                   │
                   ▼
       Centralized observability data
   JobExplorer + metrics + heartbeat store
                   │
                   ▼
         Stall detection service
  ├── execution status
  ├── last observed progress
  ├── per-job/step thresholds
  ├── grace period / suppression
  └── consecutive checks / deduplication
                   │
                   ▼
           Alerting backend
     Prometheus / Alertmanager / Ops
                   │
                   ▼
         On-call and runbook
  inspect → identify cause → remediate
```

Two deployment topologies exist:

- **Monitor inside the same batch process:** simple and can read in-memory counters; however, if the JVM hangs or dies, the monitor stops too.
- **Monitor from a separate process:** queries `JobRepository`/metrics/heartbeat store over the network; can detect vanished workers. Requires managing read permissions, data lag, and pointing to the right repository.

For critical jobs, a monitor **independent of the batch process** catches process crashes too. Still, monitor the monitor itself: if it fails to query the repository, emit a **monitoring failure/unknown** alert rather than concluding "all jobs completed."

---

## 4. Built-in Signals in Spring Batch

### 4.1. JobExecution and StepExecution

Spring Batch persists metadata through `JobRepository`. At the job level:

- `JobExecution.getId()`, `getStatus()`, `getStartTime()`, `getEndTime()`.
- `JobExecution.getLastUpdated()`: timestamp when execution metadata was last persisted/updated.
- `JobExecution.getStepExecutions()`: step executions attached to this execution.

At the step level:

| Signal | StepExecution getter | Observational meaning |
|---|---|---|
| Read | `getReadCount()` | Items recorded as read |
| Written | `getWriteCount()` | Items recorded as written |
| Filtered | `getFilterCount()` | Items filtered when processor returns `null` |
| Read skips | `getReadSkipCount()` | Items skipped due to read errors |
| Process skips | `getProcessSkipCount()` | Items skipped due to process errors |
| Write skips | `getWriteSkipCount()` | Items skipped due to write errors |
| Commits | `getCommitCount()` | Number of step transaction commits |
| Rollbacks | `getRollbackCount()` | Number of rollbacks |
| Start/end | `getStartTime()`, `getEndTime()` | Step lifecycle timestamps |
| Last updated | `getLastUpdated()` | Timestamp when step metadata was last updated/persisted |
| Status | `getStatus()` | `STARTED`, `FAILED`, `COMPLETED`... |

**Key point:** counters in the repository reflect work **that crossed an update/commit boundary**. While a chunk is running, in-flight items may not yet be persisted. Thus unchanged counters alone do not prove the thread stopped working.

For example, with `chunk(1000)` and a single API read taking 18 minutes, `readCount` can stay flat for 18 minutes while the reader legitimately waits within its timeout. If the SLO allows only 5 minutes without **committed output**, that alert may still be useful; if the goal is "process truly hung," additional signals are needed.

### 4.2. Is `lastUpdated` a Heartbeat?

**No.** `StepExecution.getLastUpdated()` and `JobExecution.getLastUpdated()` record when the metadata object was updated/persisted, not a guaranteed periodic heartbeat every N seconds.

Consequences:

- A CPU-heavy step inside a long chunk can be actively working while `lastUpdated` stays unchanged.
- A `STARTED` execution may have died abruptly before persisting `FAILED`.
- Metadata updates can occur without useful output advancing (e.g., rollbacks/retries).
- Timestamp APIs may return timezone-less `LocalDateTime`; never assume UTC and compute lag without verifying your system's read/write convention.

Use `lastUpdated` as a **supporting signal**, combined with counters, heartbeats, and worker health. Never treat `now() - lastUpdated > 5m` as sole proof of deadlock.

### 4.3. Reading Running Executions via JobExplorer

Spring Batch 5.2 API:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;

Set<JobExecution> running =
        jobExplorer.findRunningJobExecutions("dailyImportJob");

for (JobExecution job : running) {
    System.out.println("Job execution: " + job.getId());
    System.out.println("Status: " + job.getStatus());

    for (StepExecution step : job.getStepExecutions()) {
        System.out.printf(
                "%s read=%d write=%d filter=%d commit=%d rollback=%d%n",
                step.getStepName(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getFilterCount(),
                step.getCommitCount(),
                step.getRollbackCount());
    }
}
```

`findRunningJobExecutions` returns executions **recorded as running in the repository**. The returned set has no guaranteed order; to fetch full step details or `ExecutionContext`, call:

```java
StepExecution detailed = jobExplorer.getStepExecution(
        jobExecutionId, stepExecutionId);
```

Note that nested step data from running-execution lookups may not be fully hydrated depending on the implementation. Counters and status are usually enough for an overview, while explicit lookups ensure full execution context.

**Never use `JobExplorer` to write heartbeats or update statuses.** It is a metadata read API. Never modify `BatchStatus` directly in the database to "fix" a stuck job.

### 4.4. Checking Whether a Run Already FAILED

`BatchStatus.isRunning()` returns true for `STARTING`, `STARTED`, and `STOPPING`. However, a detector tracking item progress should normally watch only **StepExecutions in `STARTED`**. A job stuck in `STARTING` with no step yet needs a separate "startup timeout" detector; `STOPPING` needs a separate "stop timeout."

To avoid conflating states:

```java
if (jobExecution.getStatus() == BatchStatus.FAILED) {
    // Alert job failure.
} else if (jobExecution.getStatus() == BatchStatus.STARTED) {
    // Check progress, startup timeout, heartbeat.
} else if (jobExecution.getStatus() == BatchStatus.STOPPING) {
    // Check stop timeout.
}
```

---

## 5. Built-in Metrics, Micrometer, and Complementary Signals

Spring Batch 5.2 includes Micrometer-based metrics under the `spring.batch` prefix. Common meters include:

| Meter | Type | Question it helps answer |
|---|---|---|
| `spring.batch.job` | Timer | How long do jobs take to finish? |
| `spring.batch.job.active` | Long task timer | How many jobs are currently active in the instrumented process? |
| `spring.batch.step` | Timer | Step execution duration by status |
| `spring.batch.step.active` | Long task timer | Which steps are active and for how long? |
| `spring.batch.item.read` | Timer | Item read time, error/latency level |
| `spring.batch.item.process` | Timer | Item processing time |
| `spring.batch.chunk.write` | Timer | Chunk write time |
| `spring.batch.job.launch.count` | Counter | Job launch invocation count |

The meter names above are Micrometer-layer names; Prometheus converts dots to underscores and appends suffixes based on meter type and registry version. When writing PromQL, inspect **actual series names at the metrics endpoint** instead of guessing from Java names.

Spring Boot Actuator and the Prometheus registry can expose metrics:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Example endpoint config (expose only on protected internal networks):

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
```

In Spring Batch 5.2, built-in metrics write to Micrometer's global registry; export and registry alignment depend on your Micrometer/Spring Boot setup. In Spring Batch 6.x, observability is configured around `ObservationRegistry`, so consult the exact version documentation before upgrading.

**Limitation:** `spring.batch.job.active` shows active duration inside the emitting process. It **does not guarantee** items are progressing. If the process is killed, its active metric vanishes too; pair it with worker liveness checks and expected-run schedule monitoring.

### 5.1. Which "Progress" Signals Are Good Enough?

Depending on step type:

| Step type | Useful signal | Misleading signal |
|---|---|---|
| CSV read/write chunk | Post-commit `readCount`, `writeCount`; new checkpoints | Looking only at `STARTED` |
| Valid heavy-filtering processing | `readCount` paired with `filterCount` | Watching only `writeCount` and flagging stall when all items are filtered |
| Step with many retried errors | Succeeded item count, retry count, rollback count | Treating endless rollbacks as business progress |
| Long-computing Tasklet | Phase, completed units, annotated heartbeat | Prolonged `readCount=0` |
| Queue/stream reader | Committed offset, lag, heartbeat, source status | Treating zero messages as failure when an empty source is valid |
| Large file writer | Committed bytes/chunks, output finalization phase | Treating unchanged file size during buffering as a stall |
| Partitioned step | Per-partition progress plus total progress | Watching only the manager step while one worker is stuck |

### 5.2. Heartbeat Differs from Meaningful Progress

A simple heartbeat can fire every 30 seconds even if a thread is only looping "still alive." That proves **the worker is alive**, not that it is making progress.

Separate two concepts:

- **Liveness heartbeat:** at which `Instant` did the worker/step last check in?
- **Progress watermark:** at which `Instant` did processing reach a new checkpoint or business milestone, such as successfully processed records, ACKed offsets, or completed phases?

A worker with a fresh heartbeat yet unchanged progress for 20 minutes may be blocked waiting, deadlocked in one component, or trapped in a retry loop. Combining both signals guides severity and remediation.

---

## 6. Defining Alert Thresholds by Step and SLA

A generic rule like "no counter increase after 5 minutes" causes excessive false positives. Instead, understand normal processing cadence.

Suppose:

- `dailyImportJob/importCsvStep` normally commits every 20–40 seconds; an occasional commit takes 3 minutes.
- `dailyImportJob/exportRemoteStep` calls an external API with a 4-minute per-request timeout and retry/backoff.
- `monthlyClosingJob/calculateTaxStep` has a computation phase with no item counters taking up to 25 minutes.

Initial example thresholds:

| Job / Step | Primary progress observation | Idle time before review | Notes |
|---|---|---|---|
| `importCsvStep` | Post-commit item counters | 10 minutes | Well above normal chunk time |
| `exportRemoteStep` | ACKed records + phase | 15 minutes | Accounts for valid timeouts and backoff |
| `calculateTaxStep` | Heartbeat/phase marker | 35 minutes | Does not use read/write counters |
| Entire job | End-to-end deadline | 2 hours | Separate SLA alert; can fire even while progressing |

These values are **illustrative only**, not universal constants. In production, derive thresholds from latency percentiles (p95/p99), chunk size, minimum throughput, source latency, and SLA commitments.

### 6.1. Key Time Intervals

- **Startup grace:** time allowed for the job to create steps, open readers, and connect to data sources.
- **Polling interval:** interval between metadata reads, e.g., 30 seconds.
- **Stall threshold:** maximum allowed time without progress, e.g., 10 minutes.
- **Confirmation:** require the condition to persist across two or three polls or use Alertmanager `for: 2m`.
- **Recovery condition:** detect counters/phases advancing again or the job reaching a terminal state.
- **Cooldown/dedup:** avoid re-sending the same alert every 30 seconds for the same suspected-stuck execution.

Example:

```text
09:00:00 step STARTED
09:00:30 detector sees step for the first time, read=1_000
09:01:30 read=2_000  → reset idle timer
09:05:30 read=2_000  → below 10-minute threshold
09:11:30 read=2_000  → 10 minutes elapsed, candidate STALLED
09:13:30 still flat  → send critical alert after confirmation
09:14:00 read=3_000  → mark recovered
```

### 6.2. Formula

For step `s`:

```text
progressSignature(s) =
    (readCount, writeCount, filterCount,
     readSkipCount, processSkipCount, writeSkipCount)

lastProgressObservedAt(s) =
    timestamp when the monitor last observed the signature change

idleDuration(s) =
    now - lastProgressObservedAt(s)

suspectedStall(s) =
    status(s) == STARTED
    AND idleDuration(s) >= threshold(s)
    AND NOT approvedWaiting(s)
    AND NOT inGracePeriod(s)
```

Here, "signature change" signals **work crossed a metadata update boundary**. For steps that advance phases without incrementing item counters, add dedicated phase/heartbeat tracking.

Never treat `rollbackCount` as successful progress: endlessly rising rollbacks can indicate an inescapable error loop. Likewise, `commitCount` climbing on empty chunks does not prove business progress. Track those counters separately as diagnostic signals.

### 6.3. Data-Driven Thresholds

A more adaptive approach measures throughput:

```text
throughput = ΔwriteCount / Δtime

estimatedRemainingSeconds =
    max(0, expectedItems - writeCount) / max(throughput, epsilon)
```

This formula is meaningful only with a reliable `expectedItems` and steady processing rates. With streaming inputs or heavy filtering, estimates skew easily. Avoid throughput-based stall rules unless a valid expected workload exists.

---

## 7. Java Example: Stalled StepExecution Detector

This example separates **data collection** from **detection rules** into two layers. The detector uses plain Java, is easy to test, and avoids wall-clock dependencies. The watchdog uses Spring Batch `JobExplorer` to read persisted metadata.

### 7.1. Pure Java Detector

Create `ProgressStallDetector.java` in package `com.example.batch.monitoring`:

```java
package com.example.batch.monitoring;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class ProgressStallDetector {

    // Distinct ID per StepExecution; restarts create different execution IDs.
    private record Key(long jobExecutionId, long stepExecutionId) {}

    // Count only item progress signals, excluding rollbacks.
    private record Signature(
            long read, long write, long filtered,
            long readSkip, long processSkip, long writeSkip) {}

    public record Snapshot(
            long jobExecutionId,
            long stepExecutionId,
            String jobName,
            String stepName,
            long readCount,
            long writeCount,
            long filterCount,
            long readSkipCount,
            long processSkipCount,
            long writeSkipCount) {

        private Key key() {
            return new Key(jobExecutionId, stepExecutionId);
        }

        private Signature signature() {
            return new Signature(
                    readCount, writeCount, filterCount,
                    readSkipCount, processSkipCount, writeSkipCount);
        }
    }

    public record StallAlert(
            long jobExecutionId,
            long stepExecutionId,
            String jobName,
            String stepName,
            Instant lastProgressObservedAt,
            Duration idle) {}

    private static final class State {
        private Signature lastSignature;
        private Instant lastProgressObservedAt;
        private boolean alertEmitted;

        private State(Signature signature, Instant observedAt) {
            this.lastSignature = signature;
            this.lastProgressObservedAt = observedAt;
        }
    }

    private final Duration idleThreshold;
    private final Map<Key, State> states = new HashMap<>();

    public ProgressStallDetector(Duration idleThreshold) {
        Objects.requireNonNull(idleThreshold, "idleThreshold");
        if (idleThreshold.isNegative() || idleThreshold.isZero()) {
            throw new IllegalArgumentException(
                    "idleThreshold must be positive");
        }
        this.idleThreshold = idleThreshold;
    }

    /**
     * Pass all STARTED StepExecutions from a successful poll.
     * Timestamp is injected from a Clock in the caller for testability.
     */
    public synchronized List<StallAlert> inspect(
            Collection<Snapshot> running, Instant now) {

        Objects.requireNonNull(running, "running");
        Objects.requireNonNull(now, "now");

        Set<Key> seen = new HashSet<>();
        List<StallAlert> alerts = new ArrayList<>();

        for (Snapshot current : running) {
            Key key = current.key();

            // Ignore duplicate entries within the same collection pass.
            if (!seen.add(key)) {
                continue;
            }

            Signature signature = current.signature();
            State state = states.get(key);

            if (state == null) {
                // Not seen previously: start tracking from this poll.
                states.put(key, new State(signature, now));
                continue;
            }

            if (!signature.equals(state.lastSignature)) {
                // New progress observed: clear any held alert state.
                state.lastSignature = signature;
                state.lastProgressObservedAt = now;
                state.alertEmitted = false;
                continue;
            }

            Duration idle = Duration.between(
                    state.lastProgressObservedAt, now);

            // Clock moved backward: do not emit a false alert.
            if (idle.isNegative()) {
                state.lastProgressObservedAt = now;
                continue;
            }

            if (!state.alertEmitted
                    && idle.compareTo(idleThreshold) >= 0) {
                alerts.add(new StallAlert(
                        current.jobExecutionId(),
                        current.stepExecutionId(),
                        current.jobName(),
                        current.stepName(),
                        state.lastProgressObservedAt,
                        idle));
                state.alertEmitted = true;
            }
        }

        // Stop tracking steps that already COMPLETED/FAILED/STOPPED.
        // Call inspect only when the metadata scan SUCCEEDED completely.
        states.keySet().retainAll(seen);

        return List.copyOf(alerts);
    }
}
```

**Characteristics of this detector:**

- Uses `(jobExecutionId, stepExecutionId)` as the key to distinguish restarts from fresh runs.
- On first observation, never guesses how long the job had already been idle; tracking starts when the monitor first sees it.
- When counters change, resets `lastProgressObservedAt` and re-arms alerting if it later stalls again.
- Emits **a single signal** per idle episode instead of spamming alerts on every poll.
- Once a step leaves the running set, its tracking state is removed. In production, the alerting system should also emit recovery/close transitions.
- If querying the repository fails, **never call `inspect(emptyList, now)`**. That would wipe all tracking history while jobs are still running.

This is an explanatory implementation storing state in RAM with a single threshold for all steps. A multi-replica production monitor or one that must preserve alert state across restarts should store state centrally or rely on persisted heartbeats/metrics.

### 7.2. Watchdog Reading JobExplorer and Calling the Detector

Create `JobProgressWatchdog.java`:

```java
package com.example.batch.monitoring;

import java.time.Clock;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import com.example.batch.monitoring.ProgressStallDetector.Snapshot;

@Configuration(proxyBeanMethods = false)
@EnableScheduling
class MonitoringConfiguration {

    @Bean
    Clock monitoringClock() {
        return Clock.systemUTC();
    }

    @Bean
    ProgressStallDetector progressStallDetector() {
        return new ProgressStallDetector(Duration.ofMinutes(10));
    }
}

@Component
public class JobProgressWatchdog {

    private static final Logger log =
            LoggerFactory.getLogger(JobProgressWatchdog.class);

    private final JobExplorer explorer;
    private final ProgressStallDetector detector;
    private final Clock clock;

    // Example: production should load this list from controlled configuration.
    private final List<String> monitoredJobs =
            List.of("dailyImportJob", "settlementJob");

    public JobProgressWatchdog(
            JobExplorer explorer,
            ProgressStallDetector detector,
            Clock monitoringClock) {
        this.explorer = explorer;
        this.detector = detector;
        this.clock = monitoringClock;
    }

    @Scheduled(
        fixedDelayString = "${app.batch.monitor.poll-ms:30000}"
    )
    public void poll() {
        List<Snapshot> snapshots = new ArrayList<>();

        try {
            for (String jobName : monitoredJobs) {
                for (JobExecution job :
                        explorer.findRunningJobExecutions(jobName)) {

                    Long jobId = job.getId();
                    if (jobId == null) {
                        continue;
                    }

                    for (StepExecution step : job.getStepExecutions()) {
                        Long stepId = step.getId();

                        // Startup/stop timeouts are tracked by a separate detector.
                        if (stepId == null
                                || step.getStatus()
                                    != BatchStatus.STARTED) {
                            continue;
                        }

                        snapshots.add(new Snapshot(
                                jobId,
                                stepId,
                                jobName,
                                step.getStepName(),
                                step.getReadCount(),
                                step.getWriteCount(),
                                step.getFilterCount(),
                                step.getReadSkipCount(),
                                step.getProcessSkipCount(),
                                step.getWriteSkipCount()));
                    }
                }
            }
        } catch (RuntimeException metadataFailure) {
            log.error("Cannot inspect Spring Batch metadata",
                    metadataFailure);
            // Emit a dedicated monitor/repository-unavailable alert.
            // Do not clear detector state due to a failed poll.
            return;
        }

        for (var alert : detector.inspect(
                snapshots, clock.instant())) {
            log.warn(
                    "Suspected stalled step: job={}, step={}, "
                    + "jobExecutionId={}, stepExecutionId={}, "
                    + "lastProgressObservedAt={}, idleSeconds={}",
                    alert.jobName(),
                    alert.stepName(),
                    alert.jobExecutionId(),
                    alert.stepExecutionId(),
                    alert.lastProgressObservedAt(),
                    alert.idle().toSeconds());
        }
    }
}
```

**Limitations to recognize in this example:**

1. `@Scheduled` runs the watchdog every 30 seconds, yet in a multi-node deployment **multiple watchdogs could scan and alert redundantly**. Production needs leader election/locking or deduplication at the alert backend.
2. `monitoredJobs` is hardcoded to keep the example short; move it to configuration in deployment.
3. While a step is `STARTING` or a job is running with no `STARTED` step, this watchdog **does not fire**. Pair it with startup, stopping, and orphan detectors.
4. Tasklets that do not update item counters will alert after 10 minutes even while working. Enable counter-based detectors only for steps with item-level progress.
5. The alert in this code is only a **warning log**. Paging/email/ticket systems should consume events from a sink with deduplication and routing rather than relying on a single log line.
6. The detector uses the monitor host's UTC `Instant` at the time **counter changes are observed**. It avoids directly comparing repository `LocalDateTime lastUpdated` against UTC because timezone conventions may differ.
7. A freshly started monitor begins measuring only once it sees the execution. To catch jobs already hung before the monitor restarted, persist durable heartbeat/checkpoint timestamps.

In larger infrastructure, split `JobExplorer reader → ProgressObservation service → Alert publisher` into separate beans; the combined example simply shows the full data path cleanly.

---

## 8. Unit Testing the Stall Detector with Fake Time

Create `ProgressStallDetectorTest.java` using JUnit Jupiter. Tests supply explicit `Instant` values without `Thread.sleep` or waiting on a real job.

```java
package com.example.batch.monitoring;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;

import com.example.batch.monitoring.ProgressStallDetector.Snapshot;

class ProgressStallDetectorTest {

    private static Snapshot sample(long read, long write) {
        return new Snapshot(
                701L, 801L,
                "dailyImportJob", "importCsvStep",
                read, write, 0L, 0L, 0L, 0L);
    }

    @Test
    void alertsOnceAfterThresholdThenRecoversOnProgress() {
        var detector =
                new ProgressStallDetector(Duration.ofMinutes(10));

        Instant t0 = Instant.parse("2026-11-16T00:00:00Z");

        assertTrue(detector.inspect(
                List.of(sample(100, 100)), t0).isEmpty());

        assertTrue(detector.inspect(
                List.of(sample(100, 100)),
                t0.plus(Duration.ofMinutes(9))).isEmpty());

        var alerts = detector.inspect(
                List.of(sample(100, 100)),
                t0.plus(Duration.ofMinutes(10)));

        assertEquals(1, alerts.size());
        assertEquals(701L, alerts.get(0).jobExecutionId());
        assertEquals(Duration.ofMinutes(10), alerts.get(0).idle());

        // Same stall episode: do not spam alerts.
        assertTrue(detector.inspect(
                List.of(sample(100, 100)),
                t0.plus(Duration.ofMinutes(11))).isEmpty());

        // Counter changed: reset observation window.
        assertTrue(detector.inspect(
                List.of(sample(150, 140)),
                t0.plus(Duration.ofMinutes(12))).isEmpty());

        assertEquals(1, detector.inspect(
                List.of(sample(150, 140)),
                t0.plus(Duration.ofMinutes(22))).size());
    }

    @Test
    void completedStepIsRemovedFromTracking() {
        var detector =
                new ProgressStallDetector(Duration.ofMinutes(5));

        Instant t0 = Instant.parse("2026-11-16T00:00:00Z");

        detector.inspect(List.of(sample(0, 0)), t0);
        detector.inspect(List.of(), t0.plusSeconds(60));

        // Treated as a fresh observation, not carrying over old stall time.
        assertTrue(detector.inspect(
                List.of(sample(0, 0)),
                t0.plus(Duration.ofMinutes(30))).isEmpty());
    }

    @Test
    void firstObservationDoesNotClaimHistoricalStall() {
        var detector =
                new ProgressStallDetector(Duration.ofMinutes(10));

        Instant firstSeen =
                Instant.parse("2026-11-16T12:00:00Z");

        // No evidence of counters prior to this scan.
        assertTrue(detector.inspect(
                List.of(sample(0, 0)), firstSeen).isEmpty());
    }
}
```

This test suite verifies the detector's state machine. It **does not prove** that `JobExplorer` returns expected data or that the scheduled watcher runs on schedule; those require integration and deployment tests.

### 8.1. Additional Scenarios to Cover on Rollout

| Scenario | What to verify |
|---|---|
| Counters increment every 3 minutes, threshold 10 minutes | No alert |
| Counters unchanged for full 10 minutes | Alerts once |
| Counters increment after alert | Emits recovery and allows future alerting |
| Job transitions to `COMPLETED` or `FAILED` | Closes stall alert; emits terminal-status alert if needed |
| Restart of same JobInstance | New StepExecution ID starts a fresh tracking window |
| Repository query fails for one poll | Does not clear baselines; emits monitor failure signal |
| Watchdog restarts | Does not guess old progress time; uses persisted checkpoint/heartbeat if available |
| Multiple steps running concurrently | Each step has independent state, threshold, and alerts |
| Tasklet without item counters | Uses phase/heartbeat, avoiding false positives |
| Host clock jumps backward | Never emits negative idle duration |
| Continuous retry loop | Never treats climbing rollbacks as meaningful progress |
| Two watchdogs emit the same alert | Deduplicated by alert key and durable state |

---

## 9. Heartbeats and Progress Events for Long-Running Work

Not every batch step updates item counters regularly. A `Tasklet` compressing a 30 GB file inside one `execute()` call may be making steady progress while `readCount=0` and `writeCount=0` from start to finish.

In that case, actively emit progress events:

```text
jobExecutionId = 701
stepExecutionId = 801
phase           = "compressing"
lastHeartbeatAt = 2026-11-16T02:05:00Z
lastProgressAt  = 2026-11-16T02:04:40Z
processedBytes  = 4_294_967_296
totalBytes      = 32_212_254_720
workerId        = "batch-worker-3"
```

Distinguish:

- `lastHeartbeatAt`: worker recently sent an alive signal.
- `lastProgressAt`: useful bytes/records/phases advanced.
- `processedBytes`: quantitative progress amount.
- `phase`: current stage of work for selecting thresholds.
- `workerId`: links to logs, pod/container, JVM, or thread dumps.

### 9.1. Heartbeat Reporting Interface

An illustrative abstraction:

```java
public interface BatchProgressReporter {

    void heartbeat(long jobExecutionId,
                   long stepExecutionId,
                   String phase,
                   Instant observedAt);

    void progress(long jobExecutionId,
                  long stepExecutionId,
                  String phase,
                  long completedUnits,
                  Instant observedAt);
}
```

Implementations can write to a dedicated monitoring table, Redis, or an event/metrics system. Never write directly to framework `BATCH_*` tables to record heartbeats: updating metadata outside `JobRepository` can break checkpoint/version assumptions and corrupt restarts.

### 9.2. Recording Heartbeats Without Overloading the System

If processing 100,000 items/second, never hit the network or database per item just for heartbeats. Report every 15–30 seconds, every 10,000 items, on each committed chunk, or on phase transitions.

A useful pattern:

```text
Tasklet/Processor
     │
     ├─ every N seconds → heartbeat(workerAlive)
     │
     └─ after successful checkpoint → progress(committedUnits)
                                    │
                                    ▼
                           Durable progress store
                                    │
                                    ▼
                    Independent monitor/alert engine
```

If progress is emitted **before** the batch transaction commits, an event might claim 1,000 items processed even though the transaction actually rolled back. When business accuracy matters, tie progress updates to successful checkpoints/commits or clearly label pre-commit numbers as `attemptedUnits`.

### 9.3. When Heartbeats Continue While Progress Stalls

This scenario is no longer a "vanished worker" failure. Check:

- Is the data source legitimately empty or blocked?
- Is the thread waiting on a network timeout or database lock?
- Are `retry/backoff` attempts and durations bounded?
- Can the current step report progress via another phase marker?
- Is there a queue backlog?
- Is there a deadlock/livelock or a loop producing no output?

Low `heartbeat_age_seconds` paired with high `progress_age_seconds` calls for a different alert message than **losing both heartbeat and progress**.

---

## 10. Exporting Signals to Prometheus and Writing Alert Rules

One model has the monitor expose step/job-level metrics:

```text
batch_step_running{job="dailyImportJob",step="importCsvStep",env="prod"} 1
batch_step_progress_age_seconds{job="dailyImportJob",step="importCsvStep",env="prod"} 683
batch_step_heartbeat_age_seconds{job="dailyImportJob",step="importCsvStep",env="prod"} 35
batch_monitor_last_success_timestamp_seconds{env="prod"} 1794790000
```

These metric names are **application-defined custom metrics**, not Spring Batch built-ins. When multiple executions share the same job/step, decide whether to aggregate via min/max/quantiles or expose per-execution series with strict cardinality control; generally avoid putting record IDs, file paths, or user IDs in labels.

### 10.1. Example Alert Rules

Prometheus example (assuming the collector exports the custom metrics with the labels above):

```yaml
groups:
  - name: spring-batch-progress
    rules:
      - alert: SpringBatchStepNoProgress
        expr: |
          (batch_step_progress_age_seconds{env="prod"} > 600)
          and on (job, step, env)
          (batch_step_running{env="prod"} == 1)
        for: 2m
        labels:
          severity: warning
          service: spring-batch
        annotations:
          summary: "Spring Batch step is not making progress"
          description: >
            Job {{ $labels.job }}, step {{ $labels.step }}
            has made no progress for over 10 minutes.

      - alert: SpringBatchMonitorNotReporting
        expr: |
          absent(batch_monitor_last_success_timestamp_seconds{env="prod"})
          or
          (time() - batch_monitor_last_success_timestamp_seconds{env="prod"} > 120)
        for: 2m
        labels:
          severity: critical
          service: spring-batch
        annotations:
          summary: "Batch monitor signal not received"
```

This configuration is **illustrative**: the exporter must actually emit these series, and aggregation must be verified when multiple pods or job executions emit metrics concurrently.

Operational notes:

- `for: 2m` requires the expression to remain true for two minutes before firing.
- Handle **missing metrics** explicitly when a process or exporter dies; Prometheus does not treat an absent metric as `0` or "all steps healthy."
- If `batch_step_running=1` is exported only while running and disappears on completion, alerts must have proper recovery semantics.
- If the collector loses DB connectivity, progress metrics may freeze just like a stalled job. Watch `monitor_last_success` or `monitor_scrape_success` to avoid false conclusions.
- Overly granular labels explode time-series counts; keep labels stable like job name, step name, environment, and cluster. Put execution IDs inside alert context or event stores for locating specific runs.

### 10.2. Choosing Where to Store State

| Mechanism | Pros | Limitations |
|---|---|---|
| In-memory HashMap in watchdog | Simple to write, fast unit tests | State lost on restart; unsuitable for multiple replicas |
| Prometheus time series | Easy rates, lags, `for`, dashboards | Missing series or scrape failures need special rules; doesn't always keep execution IDs |
| Database progress/heartbeat table | Preserves history and exact execution lookup | Read/write cost; needs TTL/cleanup and schema |
| Redis/KV with TTL | Fast heartbeat reads/writes, useful TTL | Requires durability and alert-state design |
| Central event stream | Great for monitoring many jobs and systems | Needs consumers, late-event handling, and dedup |

No tool replaces defining **progress semantics** for each step. A polished dashboard showing only CPU/RAM cannot tell whether a job finished a business checkpoint.

---

## 11. Designing Noise-Resistant, Actionable Alerts

A useful alert must tell the on-call engineer **which job, where progress stopped, how long it has been affected, and whether immediate action is needed**.

Event payload should include:

```json
{
  "type": "SPRING_BATCH_STEP_STALLED",
  "severity": "warning",
  "environment": "prod",
  "jobName": "dailyImportJob",
  "jobInstanceId": 5301,
  "jobExecutionId": 7012,
  "stepName": "importCsvStep",
  "stepExecutionId": 8022,
  "status": "STARTED",
  "lastProgressObservedAt": "2026-11-16T02:15:00Z",
  "observedAt": "2026-11-16T02:28:00Z",
  "idleSeconds": 780,
  "thresholdSeconds": 600,
  "readCount": 150000,
  "writeCount": 149998,
  "filterCount": 2,
  "runbook": "https://internal.example/runbooks/batch-stalled"
}
```

This payload is illustrative. When providing a runbook link, point to your organization's real internal address in deployment. Never put tokens, sensitive item contents, or credentials into alerts.

A **dedup key** typically comprises:

```text
environment + jobExecutionId + stepExecutionId + alertType
```

For example, if an execution stays stuck for 30 minutes, alert once and escalate severity after a second threshold rather than sending 60 emails from 30-second polls.

### 11.1. Prioritization

| Scenario | Priority handling |
|---|---|
| Step stalled 10 minutes with 6 hours left in SLA | Warning; investigate during business hours |
| Step stalled 20 minutes with deadline 10 minutes away | Critical or page on-call |
| Multiple jobs stalled on the same shared database | Group by shared dependency incident; avoid alert storms |
| Job returns to healthy progress | Emit recovery; close incident or update timeline |
| Approved maintenance window | Time-boxed silence while still recording observability data |
| Monitor fails to read metadata | Separate monitor/data-source failure alert |

Severity must reflect **business impact**, not elapsed time alone. A slow job far from its deadline may be a warning; the same job near settlement cutoff or affecting customers may be critical.

### 11.2. Cooldown and Escalation

An operational state machine:

```text
HEALTHY
   │ no progress past threshold
   ▼
SUSPECTED
   │ condition persists
   ▼
FIRING
   │ more time elapses or SLA approaches
   ▼
ESCALATED
   │ progress resumes / execution terminates
   ▼
RESOLVED
```

If a job transitions to `FAILED` while a stall alert is firing, close the stall alert and open/link a failure alert. Avoid leaving both alerts firing after the incident has changed state.

### 11.3. Missing Schedule Is Not a Stall

If a job must run before 02:30 daily yet no `JobExecution` exists for that `businessDate`, querying running executions returns empty and the stall detector above stays silent. That failure is **job failed to launch**.

Run an independent check driven by expected schedules, business timezones, `JobInstance`/`JobExecution` records, and deadline cutoffs. This is vital when a scheduler inside the same JVM died before trigger time.

---

## 12. Runbook: Handling a Stalled Step Alert

A stalled alert should trigger an ordered diagnostic procedure, not an immediate automatic restart.

### Step 1 — Confirm the Incident

Capture:

- `jobName`, `jobExecutionId`, `stepExecutionId`, and `businessDate`.
- Current status in `JobExplorer` plus `lastUpdated`/`startTime`.
- Counters across two or more observations to confirm whether anything moved.
- Step stall threshold and related SLA/deadline.
- Deployment coordinates: pod/host/worker/thread.

Verify the monitor is reading the right database, schema, cluster, and environment. A lagging read replica can make metadata look stale while the job is actually progressing on primary.

### Step 2 — Inspect Execution Signals

If the execution is still `STARTED`:

- Is the worker/pod/JVM still alive?
- Do CPU, memory, GC pauses, or thread dumps show a deadlock or busy loop?
- Does the database show locks, connection pool saturation, deadlocks, or slow queries?
- Are external networks/APIs hitting timeouts, retry storms, rate limits, or outages?
- Does the source queue still have data? Is the consumer under backpressure or legitimately idle?
- Are output files flushed/published at the right phase?
- For partitioned steps, is one individual worker stuck while the aggregate still climbs?

### Step 3 — Classify the Root Cause

| Cause category | Signs | Investigation actions |
|---|---|---|
| Blocked reader | No new items; thread waiting on I/O | Check network timeouts, DB cursors, source servers |
| Processor loop or deadlock | Abnormally high CPU or blocked threads | Thread dumps, flame graphs, code paths, locks |
| Stuck writer | Chunk read done; write/commit stalled | DB locks, full storage, remote APIs, transaction timeouts |
| Inescapable retry loop | Rollbacks/retries climbing, output flat | Inspect backoff, retry limits, exception types |
| Dead worker | Metadata still `STARTED`, no live process | Compare infrastructure state with repository |
| Long-chunk false positive | Thread actively working; counters uncommitted | Improve visibility via heartbeats/phases or adjust threshold |
| Validly waiting on empty source | Input currently empty; polling per policy | Switch to lag/deadline alerting instead of stall |

### Step 4 — Decide Remediation

- If a downstream dependency is failing, prioritize fixing the dependency and let the job recover if designed with safe retries.
- If the job is alive yet stuck unproductively, request a stop **through standard control APIs** (such as `JobOperator`) and monitor shutdown; stopping is normally cooperative, not an instant kill.
- If the worker died, inspect metadata, transactions, and checkpoints before restarting.
- When restarting, use the exact `JobInstance`/`JobParameters` of the target period and reconcile output to avoid duplicate side effects.
- If the job is non-restartable or partially published output, follow a dedicated recovery/reprocessing procedure.

**Never update `BATCH_JOB_EXECUTION.STATUS` or `BATCH_STEP_EXECUTION.STATUS` via SQL just to clear an alert.** Doing so breaks repository and restart consistency. Manual metadata intervention must happen only under a specialized operational procedure with full awareness of consequences.

### Step 5 — Close Incident and Prevent Recurrence

Once the job recovers or terminates:

- Verify input/output counts, checkpoints, and business results.
- Close the stall alert, documenting root cause and recovery timestamp.
- Check whether the next scheduled period was delayed or missed.
- If thresholds caused false positives, tune thresholds using workload analysis instead of disabling monitoring.
- Add timeouts, retry limits, circuit breakers, phase-appropriate heartbeats, or supporting dashboards as needed.

---

## 13. Tricky Edge Cases in Spring Batch

### 13.1. Steps with Very Long Chunks

In chunk-oriented processing, `StepExecution` may only update when a chunk/transaction finishes. A 20-minute chunk can be valid for certain workloads, yet a 5-minute counter-based stall timeout will fire wrongly.

How to handle:

- Shrink chunk size if compatible with throughput and transaction costs.
- Enforce bounded timeouts on external sources.
- Emit progress events during long phases, distinguishing attempted from committed units.
- Set thresholds larger than normal worst-case chunk times.
- For strict-SLA steps, track the duration of **the active item/chunk**, not just total counters.

### 13.2. Filter-Only Steps

A processor may return `null` for many records to discard them by rule. In that case `writeCount` stays flat while `readCount` and `filterCount` rise. A detector watching only output count will raise false positives.

Include all relevant counters with proper semantics; monitor filter ratio separately if unusually high filtering indicates an issue.

### 13.3. Multithreaded / Partitioned Steps

A manager step may appear to progress because several partitions advance while one partition hangs permanently. Watching only aggregated totals lets healthy partitions mask the stuck one.

Monitor at the **partition/worker StepExecution** level. Track identity keys and thresholds individually, then summarize for the job. When a stuck partition blocks job completion, the incident should name the partition ID and worker host.

### 13.4. Long-Running Tasklets

A `Tasklet` does not necessarily have `readCount`/`writeCount`. Never assume a tasklet is stalled just because item counters are 0. Use phase markers, total units, heartbeats, or external-call timeouts. If work runs inside an uninterruptible blocking call, enforce dependency timeouts/cancellation or inspect threads/processes.

### 13.5. Retry Storms

A step rolling back continuously may still touch metadata. Treating `lastUpdated` as progress misses the outage. Conversely, watching useful counters catches "no output produced," though you also need retry counts, representative exceptions, and backoff metrics to diagnose why.

### 13.6. Execution Still `STARTED` After JVM Death

A killed JVM or power-lost host cannot persist a terminal status. `JobExplorer.findRunningJobExecutions` reads metadata and will still return that execution.

To confirm an "orphan":

1. Check whether the worker/container is still running.
2. Cross-check heartbeat timestamps and deployment events.
3. Inspect `lastUpdated` and the last commit.
4. Separate orphan alerts from live-process stall alerts.
5. Recover via supported restart procedures, never ad-hoc metadata edits.

### 13.7. Jobs Calling External Systems Outside the DB Transaction

A writer calling REST APIs, publishing messages, or writing object storage can create side effects before chunk metadata commits. On restart, some operations may repeat.

Therefore, before auto-restarting on a stall, verify idempotency mechanisms in the target system, transaction boundaries, outboxes, or deduplication keys. Monitoring **cannot guarantee exactly-once** based on `JobRepository` status alone.

---

## 14. Designing Integration Tests and Chaos Scenarios

Unit-testing the detector is necessary but not sufficient. A real system must prove signals are read properly from `JobRepository` and routed to the alert backend.

### 14.1. Testing Real Metadata

Using `spring-batch-test`, write an integration test launching a checkpointed step, then inspect `JobExecution`/`StepExecution` via `JobExplorer`. Use a 5–10 item fixture with a processor having controlled delays/faults.

Assertions should check:

- Step status is `STARTED` while executing.
- Counters from `JobExplorer` advance after successful commits.
- No alert fires before the threshold.
- When progress freezes via a test hook, the detector fires after the threshold.
- Once the job finishes, alerts resolve and the execution leaves the running set.
- When repository queries fail, monitor failure is signaled instead of a false stall.

Do not sleep for 10 minutes in tests: inject a `Clock` or pass `Instant` values to test the state machine; integration tests only need to verify metadata-to-snapshot conversion.

### 14.2. Testing Worker Death

In an isolated test environment:

1. Launch a test job configured to pause at a known checkpoint.
2. Abruptly kill the worker/container per the test scenario.
3. Inspect `JobExplorer` and the heartbeat store.
4. Verify the monitor detects the mismatch between metadata and worker liveness.
5. Run recovery and verify outputs have neither duplicates nor losses.

Never use production databases or jobs with real external side effects for such experiments.

### 14.3. Testing Network / DB Outages

Simulate a window where the monitor cannot read the repository:

- Do not wipe baselines of currently tracked executions.
- Log the observation error clearly and trigger a monitoring-unavailable alert.
- When connectivity returns, reconcile state.
- Never conclude jobs `COMPLETED` just because the running list came back empty due to a failed query.

### 14.4. Testing Empty Data Sources

If a valid queue is empty for an hour while the job polls as expected:

- Heartbeats keep advancing.
- Lag/backlog may be 0.
- Do not emit a stalled alert for "zero items" when waiting on empty input is expected behavior.
- If the business expects a file before a cutoff, emit a **missing input/SLA alert** instead of a stall.

### 14.5. Testing Restarts and Duplicate Alerts

After restarting a job:

- `JobExecutionId` and `StepExecutionId` can change.
- Progress is tracked on the new execution without inheriting stale stall state.
- Old alerts resolve/close properly.
- If the restart fails, a separate failure alert points to the new execution and links to the prior incident.

---

## 15. Production Deployment: Reliability of the Alert System Itself

A stalled-job detector is itself a critical operational component. These safeguards prevent both false positives and missed outages.

| Issue | Risk | Mitigation |
|---|---|---|
| Monitor runs in the same batch process | JVM death kills the monitor too | Independent monitor, health/missing-heartbeat checks |
| Multiple monitor replicas | Duplicate alerts | Leader election, locking, or backend deduplication |
| Repository queried against a lagging replica | Stale counters | Monitor replication lag, tune thresholds, or query primary when needed |
| Metadata store overloaded | Monitoring slows down batch jobs | Limit poll frequency, run targeted queries, skip loading full execution contexts |
| Clock skew across nodes | Incorrect idle duration | Sync NTP, compute elapsed on monitor using clear UTC timestamps |
| Polls delayed by GC/network | False positives | Grace/confirmation windows and monitor self-health checks |
| High-cardinality time series | High memory and observability cost | Use stable job/step/env tags; put IDs in event context |
| Process crash wipes in-memory state | Lost baselines or alerts | Persistent progress store or metric history |
| Variable commit durations | False positives | Per-step thresholds and proper checkpoint/heartbeat signals |
| Missing runbook | Unactionable alerts | Attach `jobExecutionId`, dashboard, log links, remediation steps |
| Unsafe auto-restarts | Duplicate data, side effects | Triage, approvals, or verified idempotency/restart policies |

### 15.1. Security and Sensitive Data

Include only information needed for triage in alerts:

- Job name, step name, execution IDs, environment, timestamps, counters.
- Severity, threshold, status, and internal dashboard links.
- Normalized error codes or hashed keys when needed.

Never broadcast full `JobParameters`, `ExecutionContext`, input payloads, stack traces containing secrets, or sensitive paths to wide notification channels. Restrict metadata read access to operations teams.

### 15.2. Metrics for Evaluating the Alerting System

- **Time to detect:** time from actual progress stop until the alert fires.
- **False positive rate:** share of alerts where the job was still operating within policy.
- **Coverage:** share of critical jobs/steps with progress signals and thresholds.
- **Time to acknowledge / resolve:** on-call response and remediation time.
- **Missing monitoring duration:** time without data due to monitor failures.
- **Alert noise:** repeated alerts for the same incident.

Never optimize solely for "alert as early as possible": overly tight thresholds erode trust in alerts, while overly loose thresholds miss SLAs.

---

## 16. Hands-on Exercises

### Exercise 1 — Identifying Signals

Given a `StepExecution` with `readCount=1000`, `writeCount=0`, `filterCount=1000`, explain why monitoring only `writeCount` triggers false stall alerts. List which counters should be watched.

### Exercise 2 — Chunk-Aware Thresholds

An import job uses `chunk(500)`, with the slowest normal chunk taking 4 minutes and polling every 30 seconds. Propose a threshold and confirmation period, then explain how to adjust them if chunks occasionally take 12 minutes.

### Exercise 3 — Implementing the Detector

Extend `ProgressStallDetector` from this article to support per-`(jobName, stepName)` thresholds, startup grace periods, and recovery events. Write tests for thresholds, resumed progress, and restarted executions.

### Exercise 4 — Itemless Tasklets

Create a `Tasklet` that compresses a file and reports `processedBytes` every 15 seconds. Design two alerts:

- Worker heartbeat missing for over 2 minutes.
- Heartbeat present yet `processedBytes` unchanged for 10 minutes.

### Exercise 5 — Observing with Micrometer

Enable Spring Boot Actuator and the Prometheus registry in a test environment. Inspect the actual series of `spring.batch.step.active` and add a custom `batch_step_progress_age_seconds` metric. Write an alert rule using `for` to reduce false positives.

### Exercise 6 — Killed Worker

Launch a test job, kill the worker mid-run, and query `JobExplorer.findRunningJobExecutions(jobName)`. Explain why `STARTED` in the repository does not prove the process is alive and list safe recovery steps.

### Exercise 7 — Missing Schedule

A reconciliation job must have an execution for yesterday's `businessDate` before 03:00 Vietnam time. Design a detector that alerts if **no matching execution exists** even when no job is `STARTED`. Compare this alert type with stalled alerts.

### Exercise 8 — Runbook and Deduplication

Design an alert payload containing job/step IDs, last progress timestamp, and counters. Define a dedup key, escalation near SLA, recovery when progress resumes, and behavior when the job transitions to `FAILED`.

---

## 17. References

- [Spring Batch 5.2 — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/5.2/monitoring-and-metrics.html): default Micrometer metrics and meanings.
- [Spring Batch 5.2 — Domain Language](https://docs.spring.io/spring-batch/reference/5.2/domain.html): `JobExecution`, `StepExecution`, and counters.
- [Spring Batch 5.2 — JobExplorer Javadoc](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/explore/JobExplorer.html): reading running executions and historical metadata.
- [Spring Batch 5.2 — StepExecution Javadoc](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/StepExecution.html): read/write/skip/commit/rollback, status, and `lastUpdated`.
- [Spring Batch — Observability (newer releases)](https://docs.spring.io/spring-batch/reference/spring-batch-observability/micrometer.html): `ObservationRegistry` and configuration changes in Spring Batch 6.x.
- [Spring Boot — Production-ready Monitoring](https://docs.spring.io/spring-boot/reference/actuator/index.html): Actuator, metrics endpoints, application observability.
- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/): expressions, `for`, labels, and annotations.
- [Prometheus — Alertmanager](https://prometheus.io/docs/prometheus/latest/alertmanager/): grouping, deduplication, routing, and silences.

A "stalled job" alert is trustworthy only when built on **step-specific progress semantics**. `JobExplorer` and repository counters are useful starting points, yet jobs with long chunks, tasklets, retries, empty inputs, or crashed workers also need heartbeats, source signals, and infrastructure status. Combining that evidence with calibrated thresholds, deduplication, missed-schedule alerts, and runbooks enables early incident detection while protecting data integrity during recovery.
