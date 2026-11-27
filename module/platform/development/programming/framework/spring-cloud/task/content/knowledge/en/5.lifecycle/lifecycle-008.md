# Stop Signals, Background Threads, and Completion Limits When the JVM Is Interrupted

## 1. Why "Process Stopped" Does Not Mean "Task Completed"

In **Spring Cloud Task**, each Spring Boot application launch typically represents a job with a finite duration: importing a file, syncing data, exporting reports, reconciling transactions, or running a Spring Batch Job. **TaskRepository** stores metadata such as start/end timestamps, task name, exit code, and details tied to a **`TaskExecution`**. However, when the JVM is interrupted, three distinct states may exist:

- **Process state:** whether the JVM is still running, which exit code it returned, or whether the OS/container forcefully terminated it.
- **Metadata state:** whether `TaskExecution` already has `END_TIME` and completion info or remains unclosed in the database.
- **Business state:** whether the report finished writing completely, transactions committed, messages were acknowledged, and child threads finished all work.

These three states **do not automatically stay strictly synchronized**. A process can be stopped after committing all data yet before writing completion metadata. Conversely, a runner can return normally while background work is still running, causing the application to report completion prematurely if it does not await them.

Consider an example: a report export task has 20 partitions, each taking several seconds. While partition 12 is running, Kubernetes requests stopping the Pod due to a rollout or Job deletion. If the JVM receives a stop signal, can it save already completed results, record task status, report failure to the orchestrator, and exit safely? The answer depends on the **signal type**, **thread handling**, **allowed shutdown grace period**, and **idempotency/checkpoint design**.

The learning objective of this lesson is to understand the exact boundaries of graceful shutdown in Spring Cloud Task so you can design safe termination and recovery for scheduled or on-demand tasks.

## 2. Lifecycle Overview: Launch, Processing, Completion, and Interruption

~~~mermaid
flowchart TD
    A["CLI / Scheduler / Kubernetes Job"] --> B["JVM starts Spring Boot"]
    B --> C["Spring Cloud Task records the run"]
    C --> D["Runner / service executes business logic"]
    D --> E{"Stop requested?"}
    E -- "No" --> F["Await child work, commit results"]
    F --> G["Task completes normally"]
    G --> H["Close context / return exit code"]
    E -- "SIGTERM or context close" --> I["Begin shutdown, bounded time"]
    I --> J["Signal stop, restrict accepting new work"]
    J --> K{"Safely finished before deadline?"}
    K -- "Yes" --> L["Finalize processed work, release resources"]
    L --> H
    K -- "No" --> M["May be killed / terminated mid-way"]
    E -- "SIGKILL / crash / OOMKill" --> M
    M --> N["Metadata or results may be incomplete"]
    H --> O["Orchestrator observes exit code and status"]
    N --> P["Reconcile traces, recover, idempotent retry"]
~~~

The flow above is an operational model and does not guarantee exact ordering among internal callbacks of Spring Cloud Task, Spring Boot, and the JVM across all versions. **Spring Cloud Task cannot execute Java code once the JVM has stopped executing**. Hence, the framework cannot guarantee writing final metadata successfully if the process dies before completing the write operation.

Two levels of "completion" must be clearly defined:

1. **Business completion:** all mandatory work has been processed, data is safely persisted, and errors are aggregated.
2. **Execution completion:** the framework had the opportunity to update `TaskExecution` and the process produced a result observable by the orchestrator.

Good design aligns these two levels **under normal operating conditions**, while tolerating and recovering from inconsistent states during unexpected incidents.

## 3. Types of Stop Signals and JVM Behavior

On Linux/Unix, a Java process can receive signals from a terminal, operating system, or container runtime. Common signals include:

| Event / Signal | Common Source | Does JVM Have a Cleanup Chance? | Key Fact to Know |
|---|---|---|---|
| **SIGTERM** (15) | `kill -TERM PID`, `docker stop`, Kubernetes pod termination | **Usually yes**, via JVM shutdown sequence/hooks if environment and configuration allow | Allows time for controlled shutdown, but not unlimited |
| **SIGINT** (2) | `Ctrl+C` in terminal | **Usually yes** in supported environments | Typically initiates a similar shutdown sequence; does not automatically mean business work finished |
| **SIGKILL** (9) | `kill -KILL PID`, expired grace period, some OOMKill cases | **No** | Cannot catch/block the signal to run Java cleanup or shutdown hooks |
| JVM error / crash / host loss | Native crash, OS halt, power loss | **Cannot be guaranteed** | No commitment that any callbacks will run |
| `System.exit(code)` | Java code explicitly requesting JVM termination | **Runs shutdown hooks**, if JVM is functioning normally | Does not automatically wait for all background business work to finish |
| `Runtime.halt(code)` | Immediate JVM termination invoked by Java code | **Does not** run normal shutdown hooks | Use only when skipping cleanup is genuinely acceptable |
| Natural exit | Runners finish and no non-daemon threads keep JVM alive | Opportunity to close resources if code closes context properly | Do not leave metadata updates to chance upon natural JVM exit |

On Linux, some shells or containers show exit code **143** for SIGTERM (128 + 15), **137** for SIGKILL (128 + 9), and **130** for SIGINT (128 + 2). These are **common runtime conventions**, **not guaranteed codes returned by every Java application**. The final code may be determined by the JVM, shell wrapper, container runtime, or application. On Windows, console events and process termination work differently from Unix; never assume SIGTERM/SIGKILL semantics apply identically across all platforms.

### What is the essential difference between SIGTERM and SIGKILL?

- **SIGTERM** is a stop request: the JVM *can* observe it and run shutdown hooks, Spring *can* close the context, and the application *can* wait and clean up within the allotted window.
- **SIGKILL** is forced termination: the JVM gets no chance to run further Java code; waiting steps, `@PreDestroy`, buffer flushes, or `TaskRepository` updates **do not execute after the kill point**.

Therefore, **graceful shutdown is a bounded best-effort**, not a guarantee that every job finishes regardless of signal.

## 4. JVM Shutdown Hooks and Spring `ApplicationContext`

When the JVM enters a normal shutdown sequence, registered **shutdown hooks** get a chance to run. Spring Boot typically registers a hook to close `ApplicationContext` on JVM shutdown unless disabled or altered by the runtime environment.

Closing the Spring context allows Spring to perform steps such as:

- Publishing `ContextClosedEvent`, notifying interested components that the context is closing.
- Stopping lifecycle components through their respective mechanisms.
- Invoking bean destruction callbacks such as `@PreDestroy`/destroy methods and closing Spring-managed resources.
- Applying shutdown rules for executors, datasources, listeners, and other components if configured.

**Ordering and timing must not be assumed to mean "all running business work will finish."** A callback only gets a chance to run if the JVM is still in a state capable of executing hooks. Callbacks can fail, hit orchestrator timeouts, or lose dependencies they need because other beans are also closing.

Pattern using a Spring hook to detect that the context is closing:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ShutdownState {

    private final AtomicBoolean stopRequested = new AtomicBoolean();

    @EventListener(ContextClosedEvent.class)
    public void onContextClosed(ContextClosedEvent event) {
        stopRequested.set(true);
    }

    public boolean isStopRequested() {
        return stopRequested.get();
    }
}
~~~

`ShutdownState` merely signals a **stop request**. It does not automatically cancel database queries, await workers, replace timeouts, or guarantee execution under SIGKILL. When `ContextClosedEvent` fires on the shutdown thread, other business threads must **proactively check the stop flag** at safe points.

### Should you manually add `Runtime.addShutdownHook`?

Only when a specific requirement cannot be met by Spring's lifecycle infrastructure. If registering custom hooks alongside Spring Boot, **never rely on hook ordering to access beans or datasources**: JVM hook execution order is not guaranteed, and hooks may run concurrently. Never place main business logic, long transactions, or unbounded network calls inside a shutdown hook.

For Spring Cloud Task applications, prefer defining clear **completion points in the runner**, executing work in services, and using lifecycle callbacks solely to assist with **stopping new work acceptance, issuing cancellation signals, and releasing resources**.

## 5. Daemon Threads, Non-Daemon Threads, and the "Runner Done but Task Not Done" Risk

In Java, threads can be **daemon** or **non-daemon**. This difference affects how the JVM terminates naturally:

- **Non-daemon thread:** while alive, it can keep the JVM process alive even after `main` and runners have returned.
- **Daemon thread:** does not keep the JVM alive on its own; when the JVM exits, work on daemon threads can be abandoned mid-flight.

The following example illustrates a design mistake:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;

@Bean
ApplicationRunner startInBackground(ReportService reportService) {
    return args -> {
        Thread worker = new Thread(
            reportService::generateReport,
            "report-worker"
        );
        worker.start();

        // Runner finishes right away; no guarantee generateReport() finished.
    };
}
~~~

Here:

1. The runner has returned, yet `generateReport()` may still be running.
2. If `worker` is non-daemon, the JVM may stay alive if the context is not closed; the `TaskExecution` lifecycle may already be finalized before child work completes, depending on configuration and callbacks.
3. If `worker` is daemon, work may vanish as soon as no non-daemon threads remain.
4. If the context closes, the datasource or executor may shut down while the worker still needs them.
5. On SIGTERM, having a non-daemon thread **does not force shutdown to wait indefinitely for that thread**. Once shutdown hooks complete, the JVM can terminate even if business work remains unfinished.

Do not solve this by turning every thread into non-daemon or inserting `Thread.sleep(...)` after submitting work. You need an **explicit completion tracking mechanism**.

### Background Work Sources Easily Overlooked

| Mechanism | Why It Can Finish Prematurely | How to Control It |
|---|---|---|
| `new Thread(...).start()` | Thread reference is not stored/awaited | Manage lifecycle, `join` with timeout, and inspect results |
| `@Async` | Method is handed off to an executor | Return `CompletableFuture`/`Future`, await it, and handle exceptions |
| `TaskExecutor.execute(...)` | Submitting a `Runnable` does not mean completion | Use futures, latches, or appropriate coordination interfaces |
| `CompletableFuture.runAsync(...)` | May use the common pool or a separate executor | Specify a managed executor and await the future |
| `@Scheduled` | Can keep scheduling work while the app is alive | Stop accepting new work; do not use continuous schedulers to keep finite tasks alive |
| Spring Batch asynchronous job | Runner may receive launch result before job finishes | Inspect `JobExecution` and await terminal status when synchronous completion is needed |

In a finite-running task, clearly define **which work must finish before the runner returns**. Spring Cloud Task metadata describes the application lifecycle; it does not automatically track individual futures or know how many jobs a service submitted to a thread pool.

## 6. Designing Runners That Return Only After Mandatory Work Finishes

The example below uses a Spring-managed `ThreadPoolTaskExecutor` and `CompletableFuture` to export report partitions in parallel. The runner waits for all partitions to finish before returning.

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class ExportTaskConfiguration {

    @Bean("exportExecutor")
    ThreadPoolTaskExecutor exportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("export-");

        // Supports context closing; does not replace awaiting futures.
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }

    @Bean
    ApplicationRunner exportRunner(
            ExportService exportService,
            @Qualifier("exportExecutor") TaskExecutor executor) {
        return args -> {
            List<Integer> partitions = List.of(1, 2, 3, 4, 5, 6, 7, 8);

            List<CompletableFuture<Void>> futures = partitions.stream()
                .map(part -> CompletableFuture.runAsync(
                    () -> exportService.exportPartition(part), executor))
                .toList();

            CompletableFuture<Void> all = CompletableFuture.allOf(
                futures.toArray(new CompletableFuture<?>[0])
            );

            // Completes only when all finish; errors propagate to the runner.
            all.join();
        };
    }
}
~~~

`ExportService` is a business service supplied by your project. `exportPartition(part)` must have a transaction and idempotency strategy, such as each partition writing a result uniquely identified by `date` and `partitionId`.

**Meaning of this code:**

- The pool bounds threads and queue capacity, avoiding uncontrolled thread creation.
- `CompletableFuture.allOf(...).join()` completes normally only after **every future succeeds**; if any future fails, `join()` throws an exception (typically wrapped in `CompletionException`).
- `setWaitForTasksToCompleteOnShutdown(true)` and `setAwaitTerminationSeconds(30)` support executor shutdown. They **do not guarantee** the orchestrator gives the JVM a full 30 seconds, do not roll back transactions, and do not replace `join()`.
- A shutdown wait timeout differs from a business timeout. A unit of work stuck on I/O for too long still requires its own deadline, timeout, and cancellation policy.

For a task that needs controlled cancellation while running, add cancellation handling inside the service: accept a stop request, **stop accepting new partitions**, allow the active partition to finish to a safe commit point, save a checkpoint, and then stop. This is hard to achieve if thousands of tasks have already been dumped into a queue and you only try to handle them during shutdown.

## 7. Cooperative Stopping: Interruption, Stop Flags, and Safe Commit Points

**Thread interruption** is a cooperative stop-request mechanism in Java. It does not forcibly terminate arbitrary computations and does not guarantee canceling active I/O or transactions.

A unit of work can receive a stop signal from:

- An application stop flag (such as `ShutdownState.isStopRequested()` after `ContextClosedEvent`).
- The thread's interrupted status when an executor or cancellation logic calls `interrupt()`/`Future.cancel(true)`.
- Timeouts or business quotas enforced by the orchestrator.

Service pattern processing data partition by partition while avoiding stopping mid-transaction:

~~~java
import java.util.List;
import java.util.concurrent.CancellationException;

import org.springframework.stereotype.Service;

@Service
public class PartitionCoordinator {

    private final ShutdownState shutdownState;
    private final PartitionService partitionService;

    public PartitionCoordinator(
            ShutdownState shutdownState,
            PartitionService partitionService) {
        this.shutdownState = shutdownState;
        this.partitionService = partitionService;
    }

    public void process(List<String> partitionIds) {
        for (String id : partitionIds) {
            // Check before starting a new unit of work.
            if (shutdownState.isStopRequested()
                    || Thread.currentThread().isInterrupted()) {
                throw new CancellationException(
                    "Task requested to stop before partition " + id);
            }

            // Each partition is an independent commit/idempotency unit.
            partitionService.processAndCommit(id);
        }
    }
}
~~~

In this example, `PartitionService.processAndCommit(id)` lives in another bean so transactions apply properly via Spring proxies when using `@Transactional`. Each successful commit must carry enough identity to be recognized on retry. The stop flag is checked **before starting a new partition** to avoid arbitrarily aborting mid-transaction. For very long partitions, add safe internal checkpoints and apply timeouts on network/DB calls.

**Two limits to keep in mind:**

1. `interrupt()` only sets the interrupt flag and wakes up certain interrupt-aware blocking operations. A loop that ignores interruption or an I/O driver without cancellation support may keep running.
2. If the context is closing concurrently, essential beans such as datasources may also be shutting down. Hence, stop flags and `@PreDestroy` **are not enough to guarantee** a transaction commits in time. For bounded waiting, coordinate resource teardown order with workers and test real shutdown behavior.

### When `InterruptedException` is caught

If a method cannot propagate `InterruptedException` directly and must catch it for cleanup, **restore the interrupt flag** so upper layers recognize the stop request:

~~~java
try {
    workerDone.await();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException(
        "Interrupted while waiting for worker", ex);
}
~~~

Never silently swallow `InterruptedException` and continue as if nothing happened. Conversely, do not treat throwing `CancellationException` during JVM shutdown as proof that `TaskRepository` definitely recorded a failure code; at that moment callbacks or database connections might no longer be functional.

## 8. Limits of Graceful Shutdown and Timeout Policies

Graceful shutdown operates within a **time budget** imposed by the runtime environment. In Kubernetes, when a Pod is terminated, the system usually gives containers a chance to receive SIGTERM and stop before forcing termination with SIGKILL when the grace period expires. `terminationGracePeriodSeconds` is part of that process. Hooks such as `preStop` also consume part of the budget; never assume the entire grace period is available for business processing.

Minimal Job example:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: daily-revenue-export
spec:
  backoffLimit: 2
  template:
    spec:
      restartPolicy: Never
      terminationGracePeriodSeconds: 45
      containers:
        - name: revenue-export
          image: example/revenue-task:1.0
          args:
            - "--date=2026-11-23"
~~~

This example assumes the image declares an entrypoint executing the Java application; the image name is purely illustrative. In practice, add database access configuration, secrets, resources, duplicate-run protection, and proper observability.

**There is no guaranteed formula:** "45s grace + 30s executor await = guaranteed 30s." The signal must reach the Java process properly, hooks must run, components must close in order, and the JVM remains subject to external deadlines. When using a shell wrapper, use `exec java -jar ...` or proper signal forwarding so the JVM receives the stop request; otherwise, Java may only observe its parent process dying.

Timeouts to examine individually:

| Timeout / Limit | Role | If Exceeded / Unmet |
|---|---|---|
| Pod/container grace period | Total time the environment grants to stop | May receive SIGKILL |
| Per-partition processing timeout | Bounds a single business unit | Needs cancellation, rollback, retry, or failure marking |
| I/O / DB timeout | Prevents workers from hanging indefinitely | Long I/O can exceed the grace period |
| Executor await termination | Waits on thread pool after shutdown command | Timing out does **not** prove all tasks completed |
| Overall task deadline | Execution limit enforced by orchestrator | Can be killed even while runners are processing |
| Retry / backoff | How reruns occur after failure | Can duplicate business actions if not idempotent |

A finite run should have explicit deadlines and points that **accept stopping between two commit units**, rather than trying to "finish everything at all costs" before the kill deadline.

## 9. What Happens to `TaskRepository` When the JVM Is Interrupted?

Spring Cloud Task's **`TaskRepository`** stores `TaskExecution` metadata in the database when properly configured, typically including `TASK_EXECUTION_ID`, `TASK_NAME`, `START_TIME`, `END_TIME`, `EXIT_CODE`, and exit messages. Whether metadata is actually present depends on whether the repository initialized and database connectivity succeeded.

Consider three cases:

| Incident Timing | Observable Metadata | Accurate Conclusion |
|---|---|---|
| After task initialization, before business completion | `START_TIME` present, no `END_TIME` or final outcome | Task **may** still be running, hung, or dead; reconcile with process and orchestrator |
| After committing data, before updating run completion | Business data may be complete, `TaskExecution` unclosed | Do not rerun blindly; inspect idempotency/outputs |
| Before repository wrote the start record | Corresponding `TaskExecution` record may not exist | Cannot infer "never launched" from metadata table alone |

Spring Cloud Task **cannot write metadata after SIGKILL**; an unclosed state does not automatically turn into "FAILED" via the framework. Moreover, a row missing `END_TIME` does not by itself prove the job died, as it could still be running legitimately.

Illustrative query to find runs missing an end timestamp (parameter syntax depends on driver):

~~~sql
SELECT TASK_EXECUTION_ID, TASK_NAME, START_TIME, END_TIME, EXIT_CODE
FROM TASK_EXECUTION
WHERE END_TIME IS NULL
  AND START_TIME < :cutoff_time
ORDER BY START_TIME;
~~~

When handling this list, cross-check Pod/Job/process status, logs, heartbeats, or external evidence. Only after confirming the run has stopped should the system resolve abnormal rows according to agreed operational procedures. Never run ad-hoc scripts that blindly overwrite `EXIT_CODE` or `END_TIME`: doing so risks overwriting a still-live run or erasing investigation trails.

**`TaskExecution` does not equal business results.** To know whether 12/20 partitions committed, the application needs its own progress table, checkpoints, transaction logs, or persisted outputs.

## 10. Process Loss Scenario and Recovery Strategy

Consider a daily revenue export job consisting of partitions 1 through 20. Each partition has a unique identifying key combining `business_date` and `partition_id`.

~~~mermaid
sequenceDiagram
    participant O as Orchestrator
    participant T as Spring Cloud Task
    participant D as Business DB
    participant R as TaskRepository
    O->>T: Launch date=2026-11-23
    T->>R: Record run
    loop Each partition
        T->>D: Process + commit by business key
    end
    O-->>T: SIGTERM
    T->>T: If time remains: accept no new work
    T->>D: Commit active unit if safe
    alt Enough time to stop
        T->>R: May record final status
        T-->>O: Process exits
    else Timeout / SIGKILL
        T--xO: Process cut off
        Note over D,R: Data and metadata may diverge
    end
    O->>D: Check committed partitions
    O->>T: Retry with same business_date
    T->>D: Skip or verify already-completed units
~~~

For safe reruns:

1. **Define an idempotency key** aligned with business requirements, such as `businessDate + partitionId`. Use unique constraints/upserts or a dedicated processing status table.
2. **Commit in sensible units:** each complete partition is saved as an independent transaction; avoid holding one long transaction just to bundle the entire report.
3. **Avoid inconsistently separating "writing output" and "marking done":** whenever possible, update outputs and checkpoints in the same transaction or use an outbox/reconciliation pattern.
4. **Retries inspect actual data:** an older `TaskExecution` may remain unclosed even though partition outputs were saved. Decide whether to skip, update, or compensate based on business state.
5. **Prevent concurrent duplicates:** if an older task is still processing when a new one launches, enforce appropriate locking/coordination and clear work ownership.
6. **Alerting and monitoring:** track launch counts, Pod/Job states, exit codes, runtime durations, and `TaskExecution` records missing `END_TIME` beyond a reasonable threshold.

Do not label this mechanism "exactly once" merely because `TaskRepository` or unique keys are used. When interacting with external services, sending emails, writing object storage, or publishing messages, add receiver-side idempotency and reconciliation; an internal database transaction does not cover external side effects.

## 11. Spring Cloud Task and Spring Batch When Interrupted Mid-Run

Spring Cloud Task and Spring Batch manage **two levels of state**:

| Component | What It Tracks | When the Process Is Killed |
|---|---|---|
| Spring Cloud Task / `TaskRepository` | **Application run** lifecycle (`TaskExecution`) | May lack end timestamp or final exit code |
| Spring Batch / `JobRepository` | `JobExecution`, `StepExecution`, checkpoints, batch status | May remain in running or unknown state, requiring investigation/recovery |
| Business DB | Written outputs and business keys | Only durably committed data remains valid; external side effects require reconciliation |

When using chunk-oriented processing, Spring Batch can store checkpoints and support **restarts** per job/step design. That does not mean restarts always happen automatically, nor that every step is safe to restart. Readers, processors, writers, and side effects must be designed accordingly.

With cooperative shutdown, you can consider signaling a job to stop at a clean processing boundary so checkpoints are persisted, though under SIGKILL no final Spring Batch callback is guaranteed to run. Just like Spring Cloud Task, inspect both repositories and business data before restarting.

For the requirement "finite processing application with `TaskExecution` that also needs fine-grained per-chunk checkpoints," combining Spring Cloud Task and Spring Batch is usually an appropriate architecture. If you only have a simple looping runner and want recovery after kills, you must build your own business checkpointing or adopt a suitable batch processing framework.

## 12. Dangerous Operational Misconceptions

### "Receiving SIGTERM guarantees `TaskExecution` is marked failed"

**Not guaranteed.** SIGTERM can trigger shutdown, yet hooks may be cut short by a deadline, the repository connection may be gone, or metadata recording may already have occurred before the service truly finished. Always inspect records, logs, and process state.

### "`@PreDestroy` will always execute"

**False.** Callbacks only get a chance to run during controlled context shutdown. SIGKILL, crashes, or host loss bypass callbacks completely. Never place the sole responsibility for persisting business outcomes inside `@PreDestroy`.

### "Non-daemon threads guarantee no work is lost"

**False.** Non-daemon threads can keep the JVM alive during natural exit, yet they neither prevent SIGKILL nor force the JVM to wait indefinitely during a shutdown sequence. Those threads may also reference resources that have already closed.

### "Executor `awaitTermination` finishing means business logic succeeded"

**False.** When the timeout expires, workers may still be running; when all threads stop, some tasks may have been rejected, canceled, or thrown exceptions. Check future results, outputs, and success criteria before returning code 0.

### "`TaskRepository` shows COMPLETED so external side effects definitely succeeded"

**Insufficient evidence.** Metadata shows how the framework observed the run. It does not independently confirm that message receivers, third-party services, or object storage completely processed the work. Business-layer verification/reconciliation is required.

### "Configured 60-second graceful shutdown means exactly 60 seconds left for processing"

**Not guaranteed.** Actual time received depends on the runtime, hooks, `preStop`, signal forwarding, and orchestrator limits. Shutdown should be viewed as an opportunity to **stop safely at a clean boundary**, not free time to execute arbitrary additional workloads.

## 13. Implementation Checklist for Safely Stoppable Spring Cloud Tasks

| Verification Question | Action If Not Met |
|---|---|
| Does each runner return only after all mandatory work finishes? | Await `Future`/`CompletableFuture`, aggregate errors, avoid fire-and-forget |
| Can work stop at clear commit boundaries? | Split into partitions/chunks, check stop flag before each new unit |
| Are timeouts set on I/O, database, and work units? | Configure controlled timeouts, avoid threads hanging past grace period |
| Are signals forwarded to the JVM/container properly? | Check `exec`-style entrypoint and SIGTERM handling in real environments |
| Is there a shutdown time budget? | Configure grace period, worker timeouts, deadlines, and test overrun scenarios |
| Is there a persistent result store and checkpoint outside `TaskRepository`? | Store business state with idempotency keys and proper transactions |
| Can you distinguish dead processes from unclosed metadata? | Cross-check Pod/Job/process, logs, heartbeats, and `TaskExecution` |
| Could retries duplicate writes or sends? | Add unique keys, upserts, idempotency, outbox, or reconciliation |
| Can business errors be distinguished from infrastructure errors? | Return sensible exit codes, log context, never swallow exceptions |
| Have SIGTERM, SIGKILL, and timeouts been rehearsed? | Run operational drills in staging; verify business outputs and repository state after restart |

A rehearsal drill worth running:

1. Launch a task with 20 partitions, ensuring each partition writes progress upon commit.
2. Mid-processing, send **SIGTERM** and observe when the runner stops, executor waits, context closes, and what code the process returns.
3. Repeat with **SIGKILL** to observe the difference: do not expect shutdown callbacks or finalized metadata.
4. Reconcile `TaskExecution` against business data; verify which partitions committed.
5. Rerun with the same arguments; verify final results are accurate without duplicates.
6. Test a job hanging past its deadline; ensure alerting triggers and a recovery procedure exists.

Test at startup, mid-transaction, and after processing finishes before exit, because **when the incident hits** determines what trace remains.

## 14. Conclusion

In **Spring Cloud Task**, reliable completion evidence starts with **completed business logic and persisted outputs**, followed by `TaskExecution` and process exit codes. `SIGTERM` usually provides an opportunity to close the Spring context, propagate stop requests, and save status; `SIGKILL` or crashes can cut off all of those steps. Background threads, `@Async`, and executors are safe only when the application genuinely awaits completion, enforces timeouts, and stops cleanly at commit boundaries.

To operate finite-running applications reliably on a schedule or on demand, combine **time-bounded graceful shutdown**, **`TaskRepository` for lifecycle visibility**, **durable business state persistence**, and **idempotent retries**. When the JVM is interrupted mid-run, the practical goal is to **identify completed work, recover the remainder, and avoid producing wrong or duplicate results**, rather than expecting every callback to always finish in time.
