# Stopping a Running Job in Spring Batch

## 1. Understanding How to Stop a Running Job

In Spring Batch, **stopping a running job** means requesting the system to terminate a `JobExecution` in a controlled manner so processing state can be preserved, the cause can be observed, and — if the job supports restart — execution can resume from saved checkpoint data.

Suppose the `importOrders` job is reading 10 million orders. An operator discovers the source file is wrong and wants to halt further imports. If the JVM is forcibly killed, already-written data may remain while the `JobRepository` status may never be updated. If `JobOperator.stop(executionId)` is invoked instead, Spring Batch records a **stop request**, waits for the job to yield control back to the framework, and terminates the execution at a safe point.

Distinguish three actions:

| Action | Goal | Typical Result |
|---|---|---|
| **Stop** | Request a running execution to stop in a controlled way | `STARTED → STOPPING → STOPPED` on successful stop |
| **Restart** | Relaunch a failed or stopped `JobInstance` | Creates a **new `JobExecution`**, using saved checkpoints and original identifying parameters |
| **Kill process / crash** | Terminate the OS process immediately | Callbacks and checkpoints are not guaranteed to complete; metadata may remain `STARTED` |

**Core point:** `stop` is **not** an immediate thread-kill operation. It is a **cooperative signal**. If a reader is waiting on I/O, a tasklet is running a long loop, or a business service does not return, stopping can take a long time.

### Version Scope

The main Java examples below use **Spring Batch 5.2.x, Spring Boot 3.x, and Java 17+**. In Spring Batch 5.2, the ID-based control API is `JobOperator.stop(long executionId)`; in Spring Batch 6, the API prefers `stop(JobExecution)` and the `long` overload is marked deprecated. Packages and domain classes also changed in some 6.x releases. When using another version, apply the signatures and imports of that version.

## 2. How Do JobInstance, JobExecution, and StepExecution Differ?

To stop the right job, you first need to know which entity the operation targets.

- **`Job`** is the processing definition, e.g., `importOrders`, consisting of steps and flows.
- **`JobInstance`** is a logical run identified by the job name and **identifying `JobParameters`**. For example, `importOrders` with `businessDate=2025-05-12`.
- **`JobExecution`** is a specific run attempt of a `JobInstance`. Restarting creates a new execution.
- **`StepExecution`** is the execution of an individual step within a job execution.

Example:

```text
Job: importOrders
└── JobInstance: businessDate=2025-05-12
    ├── JobExecution id=101, status=STOPPED
    │   └── StepExecution(importStep), status=STOPPED
    └── JobExecution id=117, status=COMPLETED
        └── StepExecution(importStep), status=COMPLETED
```

To stop running execution `101`, pass **`jobExecutionId=101`**. Do not pass `jobInstanceId`, `stepExecutionId`, or the job name to `stop(long)`.

Multiple `JobExecution`s can run concurrently for different `JobInstance`s of the same job name. Therefore, an admin screen should display `jobName`, `jobExecutionId`, `JobParameters`, and `BatchStatus` together before allowing a stop action.

## 3. Statuses During a Stop

Spring Batch uses `BatchStatus` for execution state and `ExitStatus` for outcomes that can participate in flow control. They serve different roles.

A typical path:

```text
STARTING
   |
   v
STARTED
   |  JobOperator.stop(executionId)
   v
STOPPING       <-- request sent; job may still be processing
   |
   |  running component yields control back to Spring Batch
   v
STOPPED        <-- final stopped status; restart can be considered
```

If the job encounters an error while stopping, the final status may be `FAILED` instead of `STOPPED`. If the job finishes naturally concurrently with the stop command, the outcome depends on timing; the admin system must re-check the actual status rather than assuming it from clicking the "Stop" button.

| `BatchStatus` | Operational Meaning | Should a New Stop Request Be Sent? |
|---|---|---|
| `STARTING` / `STARTED` | Execution is starting or actively processing | Can attempt stop |
| `STOPPING` | Stop signal recorded, not finished yet | Do not spam stop calls indefinitely; monitor progress |
| `STOPPED` | Stopped and persisted in metadata | Can consider restart if configuration permits |
| `COMPLETED` | Execution finished | Cannot stop this execution |
| `FAILED` | Execution ended in error | Evaluate the error and restartability |
| `ABANDONED` | Execution marked abandoned; framework will not restart an abandoned execution | Not used for gracefully stopping a running job |

A `STOPPING` status does not prove the processing thread is still alive. If the JVM crashes mid-flight, the metadata row can get stuck. To conclude a process is still alive, combine `JobRepository` status with execution instance telemetry, logs, heartbeats, or infrastructure info.

## 4. Sending a Stop Request with `JobOperator`

`JobOperator` is Spring Batch's interface for observing and controlling jobs, including viewing executions, `stop`, `restart`, and related operations. Under standard Spring Batch configuration, the `JobOperator` bean is provided by Batch infrastructure; if the application builds batch infrastructure manually, you must declare all components required by `SimpleJobOperator`.

### 4.1. Stopping by Execution ID

```java
import org.springframework.batch.core.launch.JobExecutionNotRunningException;
import org.springframework.batch.core.launch.NoSuchJobExecutionException;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.stereotype.Service;

@Service
public class BatchStopService {

    private final JobOperator jobOperator;

    public BatchStopService(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public boolean requestStop(long executionId)
            throws NoSuchJobExecutionException,
                   JobExecutionNotRunningException {

        // true = stop signal sent, not guaranteed that execution is already STOPPED.
        return jobOperator.stop(executionId);
    }
}
```

Example call:

```java
boolean accepted = batchStopService.requestStop(101L);

if (accepted) {
    System.out.println("Stop request sent for execution 101");
}
```

Per the `JobOperator` contract:

- Returning `true` means the **stop signal was sent**, **not** that the job has already stopped.
- `NoSuchJobExecutionException` means no execution exists with the supplied ID.
- `JobExecutionNotRunningException` means the execution is no longer in a stoppable state.
- If the method returns `false`, the system should not report success; check the cause and metadata state.

Do not manually call `jobExecution.setStatus(BatchStatus.STOPPED)` in an API to pretend the job stopped. Mutating metadata alone does not force a reader, writer, or tasklet to halt work.

### 4.2. Finding Running Executions by Job Name

When you do not know the ID yet, you can list them:

```java
import java.util.Set;
import org.springframework.batch.core.launch.JobOperator;

public class RunningJobFinder {

    private final JobOperator jobOperator;

    public RunningJobFinder(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public Set<Long> findRunningImportExecutions() throws Exception {
        return jobOperator.getRunningExecutions("importOrders");
    }
}
```

If the result set contains multiple IDs, **do not arbitrarily pick `iterator().next()`**. Use `JobExplorer` to read each `JobExecution`, inspect `JobParameters`, and choose the exact execution to stop.

Example before issuing the command:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;

JobExecution execution = jobExplorer.getJobExecution(executionId);

if (execution == null) {
    throw new IllegalArgumentException("Execution does not exist: " + executionId);
}

System.out.println("executionId=" + execution.getId());
System.out.println("jobName=" + execution.getJobInstance().getJobName());
System.out.println("parameters=" + execution.getJobParameters());
System.out.println("status=" + execution.getStatus());
```

`JobExplorer` provides a read-only metadata view; `JobRepository` manages execution and checkpoint persistence. Many applications use both: `JobOperator` to send control commands, `JobExplorer` to observe state.

## 5. Polling Until a Terminal Stopped Status

After calling `stop`, the next step is reading back status from an observable metadata source:

```java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;

public class BatchStatusReader {

    private final JobExplorer jobExplorer;

    public BatchStatusReader(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public BatchStatus getStatus(long executionId) {
        JobExecution execution = jobExplorer.getJobExecution(executionId);

        if (execution == null) {
            throw new IllegalArgumentException(
                    "JobExecution not found " + executionId);
        }

        return execution.getStatus();
    }
}
```

An admin application typically exposes:

```text
POST /batch/executions/101/stop
202 Accepted
{
  "executionId": 101,
  "message": "Stop requested"
}

GET /batch/executions/101
200 OK
{
  "executionId": 101,
  "batchStatus": "STOPPING"
}

GET /batch/executions/101
200 OK
{
  "executionId": 101,
  "batchStatus": "STOPPED"
}
```

This is a **custom REST contract example**, not a built-in Spring Batch endpoint. HTTP `202 Accepted` fits better than `200 Stopped` because stopping completes asynchronously after the API returns.

When a client monitors progress, poll with a reasonable interval and timeout. Allow `STOPPING` to be shown for a period, then report "stop request still in progress" or "needs operational inspection" if the timeout expires. **Never automatically assign `STOPPED` just because polling timed out.**

### 5.1. A Small Service for an Admin Portal

```java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.stereotype.Service;

@Service
public class BatchExecutionControl {

    private final JobOperator operator;
    private final JobExplorer explorer;

    public BatchExecutionControl(JobOperator operator, JobExplorer explorer) {
        this.operator = operator;
        this.explorer = explorer;
    }

    public boolean stop(long executionId) throws Exception {
        return operator.stop(executionId);
    }

    public BatchStatus status(long executionId) {
        JobExecution execution = explorer.getJobExecution(executionId);

        if (execution == null) {
            throw new IllegalArgumentException(
                    "Unknown JobExecution: " + executionId);
        }

        return execution.getStatus();
    }
}
```

The outer API/controller should map exceptions to appropriate responses: `404` for a missing ID, `409` for an execution already finished or not stoppable, `202` when the signal is accepted. Permission to stop jobs must be restricted to authorized operators and audited (who requested it, when, which execution, and why).

## 6. Why Can Stopping Be Slow?

Spring Batch controls the execution flow **when the framework gets a chance to regain control**. Exact behavior depends on the step type.

### 6.1. Chunk-Oriented Steps

Simple flow:

```text
Read item → process → write chunk → commit/checkpoint
                         ↑
                Stop signal arrives during processing
                         ↓
               Framework checks signal
                         ↓
               Stops at an appropriate boundary
```

While a chunk is executing, the framework typically waits for current work to reach an appropriate checkpoint. Do not mistake `stop` for rolling back all earlier changes: **already-committed** chunks can remain. The in-flight chunk may commit or roll back depending on timing, exceptions, transaction configuration, and the components invoked. Inspect `commitCount`, `rollbackCount`, and actual data instead of assuming one universal outcome.

If `chunkSize` is 10,000 and each item is slow, stop latency can be large. Tune chunk size to balance throughput, transaction overhead, and stop responsiveness; no single number fits every job.

**Step configuration example — Spring Batch 5.x:**

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, ProcessedOrder> orderProcessor,
        ItemWriter<ProcessedOrder> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, ProcessedOrder>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

`Order` and `ProcessedOrder` are illustrative domain types. `chunk(100, ...)` is only a starting point for configuration; adjust it based on load profile and operational goals. If the writer calls an external API with a 30-minute timeout, a small chunk size still will not make stop fast while that API call is blocking.

### 6.2. Long-Running `Tasklet`s

A `Tasklet` containing an infinite loop or holding control for too long forces the stop signal to wait:

```java
@Override
public RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext) {

    while (true) {
        // A long-running task that never yields control back
        // to the framework makes stopping hard to take effect.
        pollRemoteService();
    }
}
```

This is an **anti-pattern to avoid**, not production code. Split work into bounded units and return `RepeatStatus.CONTINUABLE` so the framework can repeat the tasklet, manage transactions, and check status.

```java
import org.springframework.batch.core.StepContribution;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;

public class OnePageTasklet implements Tasklet {

    private final PageImporter importer;

    public OnePageTasklet(PageImporter importer) {
        this.importer = importer;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception {

        boolean hasMorePages = importer.importNextPage();

        // Finish one bounded unit of work.
        // If continuing, the framework regains control.
        return hasMorePages
                ? RepeatStatus.CONTINUABLE
                : RepeatStatus.FINISHED;
    }
}
```

Here `PageImporter` is a hypothetical business interface: each `importNextPage()` call processes at most one page and returns whether more pages remain. For proper **restart**, the cursor/page index must also be persisted (for example via `ExecutionContext` on checkpoint boundaries), not only stored in a singleton bean field.

### 6.3. I/O, Locks, and Timeouts

Common causes of slow stops:

- Reader waiting on network, file system, or database locks without a timeout.
- Writer making a long HTTP request or doing excessive internal retries.
- Tasklet running a tight loop without yielding control.
- Long-running chunk transaction; database waiting on locks.
- Job running in another worker/process and the worker cannot update `JobRepository` in time.

A stop-friendly design should have finite I/O timeouts, reasonable unit-of-work sizes, restartable checkpoints, and enough logging to pinpoint which step is blocking shutdown. Never use `Thread.stop()` (deprecated/unsafe) or forcibly overwrite metadata status as a "fix" for these issues.

## 7. Requesting a Stop Proactively from Inside a Step

In addition to external control APIs, Spring Batch provides `StepExecution.setTerminateOnly()`. It signals that **the currently executing step wants to terminate**, letting the framework handle it at an appropriate point. This is a termination request originating **from within the execution thread itself**, unlike `JobOperator.stop(executionId)` from an admin console/API.

For example, a listener detects that business errors exceeded a threshold and wants to ask the step to stop:

```java
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class BusinessStopListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        // Prepare any required state.
    }

    public void requestStopIfNeeded(
            StepExecution stepExecution,
            boolean stopRequired) {

        if (stopRequired) {
            stepExecution.setTerminateOnly();
        }
    }
}
```

This snippet illustrates the `setTerminateOnly()` primitive; the application itself must invoke `requestStopIfNeeded(...)` wherever the business condition is checked. Do not assume Spring Batch calls this arbitrary method as a callback.

In a `Tasklet` that needs to stop on a business condition, you can obtain `StepExecution` from `StepContribution`:

```java
@Override
public RepeatStatus execute(
        StepContribution contribution,
        ChunkContext context) {

    if (maintenanceWindowReached()) {
        contribution.getStepExecution().setTerminateOnly();
        return RepeatStatus.FINISHED;
    }

    processOneUnit();
    return RepeatStatus.CONTINUABLE;
}
```

`maintenanceWindowReached()` and `processOneUnit()` are hypothetical application methods. Setting the `terminateOnly` flag does not kill the thread instantaneously; the framework still processes transitions and metadata. This mechanism cannot replace a remote stop endpoint: an in-memory `StepExecution` object does not automatically refresh from a `JobExecution` row modified by another process.

**Contrast with throwing an exception:** An unhandled business exception typically causes the step to become `FAILED`. If the intent is "pause now and restart later", using the appropriate stop mechanism expresses the operational intent better than artificially failing.

## 8. Stop, stopAndRestart, end, fail, and abandon

These mechanisms are easily confused because all of them can end a job early, yet their semantics differ.

| Mechanism | When to Use | Final `BatchStatus` | Resumability |
|---|---|---|---|
| `JobOperator.stop(executionId)` | Operator requests a running execution to stop | Usually `STOPPED` if stop succeeds | Can restart if the job allows |
| `StepExecution.setTerminateOnly()` | Logic inside a step requests stopping | Usually `STOPPED` via framework | Depends on checkpoints and config |
| `stopAndRestart(nextStep)` | Intentional flow stop at a step boundary | `STOPPED` | Restarts at the predefined step |
| `.end()` | Flow ends and is considered complete | `COMPLETED` | Same completed `JobInstance` normally cannot restart |
| `.fail()` | Flow intentionally marks failure | `FAILED` | Can restart if conditions permit |
| `JobOperator.abandon(...)` | Mark execution as no longer to be resumed | `ABANDONED` | Cannot restart an abandoned execution |

### 8.1. Intentional Stop at a Step Boundary

Sometimes a job should stop after a data validation step so an operator can review and approve running the next step. That is **predefined flow control**, without waiting for someone to click Stop mid-step.

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;

@Bean
Job stagedImportJob(
        JobRepository jobRepository,
        Step validateStep,
        Step applyStep) {

    return new JobBuilder("stagedImportJob", jobRepository)
            .start(validateStep)
            .on("COMPLETED")
            .stopAndRestart(applyStep)
            .end()
            .build();
}
```

When `validateStep` succeeds, the job transitions to `STOPPED`. The next restart begins from `applyStep` per the configured flow. Do not confuse this with `JobOperator.stop`: an operational stop targets a **running execution**, whereas `stopAndRestart` defines the **job flow** path.

### 8.2. Do Not Use Abandon Instead of Stop

`ABANDONED` expresses the intent **not to restart** that execution. It is not a graceful stop call for an active process. In particular, if a JVM crashes abruptly and metadata remains `STARTED`, verify the process is truly gone and inspect checkpoint data before changing status. Moving to `FAILED` or `ABANDONED` is an operational decision based on data recoverability, not something to automate merely on a short timeout.

## 9. Restarting After `STOPPED`

Once the status has genuinely become `STOPPED`, you can restart it using `JobOperator.restart(executionId)` in Spring Batch 5.2.

```java
import org.springframework.batch.core.launch.JobOperator;

public class BatchRestartService {

    private final JobOperator jobOperator;

    public BatchRestartService(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public long restart(long stoppedExecutionId) throws Exception {
        // Returns the ID of the NEW JobExecution.
        return jobOperator.restart(stoppedExecutionId);
    }
}
```

Example:

```text
Before stop:
  JobInstance=27, JobExecution=101, status=STARTED

After stop:
  JobInstance=27, JobExecution=101, status=STOPPED

After restart:
  JobInstance=27, JobExecution=101, status=STOPPED
  JobInstance=27, JobExecution=117, status=STARTED
```

**Restart is not "resuming the old thread".** The framework launches a new execution for the same `JobInstance`, using persisted metadata and `ExecutionContext` to determine what work remains.

Key requirements:

1. `Job` must be configured as restartable, and the previous execution must be in a valid restartable state.
2. Stateful `ItemReader`/`ItemWriter` components must save checkpoints properly (e.g., `ItemStream` and `ExecutionContext`).
3. Transactions and external side effects must prevent duplicate writes. If 100 orders already committed, restarting must not blindly re-import those 100 orders.
4. Identifying `JobParameters` of the same job instance must remain unchanged. Changing `businessDate` or adding an identifying `run.id` can accidentally create a new `JobInstance`, meaning a fresh run rather than a restart.
5. When a job is configured with `preventRestart()` or business logic cannot safely restart, the system must clearly display that manual intervention is needed.

For file readers, storing the number of lines read in `ExecutionContext` only works if the source file is immutable or verified via identity/checksum. If the source file changes between stop and restart, resuming at "line 5001" may no longer align with the original records.

## 10. Stopping in Distributed Systems

An application might host the admin API on instance A while the job executes on worker B. Distinguish carefully:

```text
Operator / Admin UI
       |
       v
API (instance A)
       |
       | JobOperator.stop(jobExecutionId)
       v
JobRepository (shared database)
       |
       | persist stop status/request
       v
Worker (instance B)
       |
       | yields control to Spring Batch at checkpoint
       v
JobRepository: STOPPED
```

This diagram illustrates **control via shared metadata**, not a guarantee that every remote partitioning or scheduling setup automatically propagates stop to every worker. With remote chunking, partitioning, message consumers, or tasks dispatched to external systems, identify which component manages workers, how far stop propagates, and what data has already committed.

Minimum operational prerequisites:

- API and worker point to the same `JobRepository`/database in the same environment; execution IDs generally have no global meaning across environments.
- The job has proper checkpoints and transactions.
- I/O operations have timeouts; workers cannot block indefinitely.
- Configuration data and job definitions remain compatible enough to restart.
- Stop/restart/abandon commands are protected by authorization and auditing.
- Dead JVM/worker detection exists so operators do not wait on `STOPPING` forever.

If a job runs in a container/Kubernetes, deleting a Pod or sending `SIGKILL` does not mean Spring Batch received a `JobOperator.stop` command. Infrastructure graceful shutdown gives the app time to close and update status, yet can still fail if the grace period expires. In Spring Batch 6, the framework adds `JobExecutionShutdownHook` to support handling shutdown signals appropriately; in 5.x, rely on your version's mechanisms and deployment setup.

## 11. Testing Job Stop Functionality

Testing stop should separate **issuing the stop request** from **verifying the actual stop outcome**.

### 11.1. Unit Testing the Control Layer

Verify that the service passes the exact execution ID to `JobOperator` and preserves the return value or exception.

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.launch.JobOperator;

class BatchStopServiceTest {

    @Test
    void shouldForwardStopRequestForSpecifiedExecution() throws Exception {
        JobOperator operator = org.mockito.Mockito.mock(JobOperator.class);
        BatchStopService service = new BatchStopService(operator);

        when(operator.stop(101L)).thenReturn(true);

        assertTrue(service.requestStop(101L));
        verify(operator).stop(101L);
    }

    @Test
    void shouldNotClaimSuccessWhenSignalWasNotSent() throws Exception {
        JobOperator operator = org.mockito.Mockito.mock(JobOperator.class);
        BatchStopService service = new BatchStopService(operator);

        when(operator.stop(102L)).thenReturn(false);

        assertFalse(service.requestStop(102L));
        verify(operator).stop(102L);
    }
}
```

This is a unit test of the **API call**. It does not prove Spring Batch updates `BatchStatus` to `STOPPING` or that a worker actually halts.

### 11.2. Integration Testing with Event Synchronization Instead of Fixed Sleeps

To verify the real lifecycle, run a job on another thread, use a `Tasklet` with a `CountDownLatch` to pause at a deterministic point, send `stop`, and release the latch. This gives the test explicit ordering control:

```text
Test thread                    Job thread
-----------                    ----------
start job  ------------------>  tasklet starts
await(entered) <-------------  entered.countDown()
JobOperator.stop(id)            tasklet is waiting
release.countDown() --------->  tasklet yields control
wait for job to finish        -> framework finishes STOPPED
assert STOPPED
```

A complete illustrative test with Spring Boot 3.x / Spring Batch 5.x:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepContribution;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBootTest(
        classes = StopJobIntegrationTest.TestApplication.class,
        properties = {
                "spring.batch.job.enabled=false",
                "spring.batch.jdbc.initialize-schema=always"
        }
)
class StopJobIntegrationTest {

    @Autowired JobLauncher launcher;
    @Autowired JobOperator operator;
    @Autowired Job job;
    @Autowired GateTasklet tasklet;

    @Test
    void stopShouldFinishAsStoppedAfterTaskletReturnsControl()
            throws Exception {

        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<JobExecution> future = executor.submit(() ->
                    launcher.run(
                            job,
                            new JobParametersBuilder()
                                    .addLong("run.id", 1L)
                                    .toJobParameters()
                    )
            );

            assertTrue(tasklet.entered.await(5, TimeUnit.SECONDS));

            Set<Long> running = operator.getRunningExecutions("stoppableJob");
            assertEquals(1, running.size());

            long executionId = running.iterator().next();
            assertTrue(operator.stop(executionId));

            // Tasklet yields control back to framework, which handles stop.
            tasklet.release.countDown();

            JobExecution execution = future.get(10, TimeUnit.SECONDS);
            assertEquals(executionId, execution.getId().longValue());
            assertEquals(BatchStatus.STOPPED, execution.getStatus());
        } finally {
            // Ensure tasklet is released if an earlier assertion fails.
            tasklet.release.countDown();
            executor.shutdownNow();
        }
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {

        @Bean GateTasklet gateTasklet() {
            return new GateTasklet();
        }

        @Bean
        Step stoppableStep(
                JobRepository jobRepository,
                PlatformTransactionManager transactionManager,
                GateTasklet tasklet) {

            return new StepBuilder("stoppableStep", jobRepository)
                    .tasklet(tasklet, transactionManager)
                    .build();
        }

        @Bean
        Job job(JobRepository jobRepository, Step stoppableStep) {
            return new JobBuilder("stoppableJob", jobRepository)
                    .start(stoppableStep)
                    .build();
        }
    }

    static class GateTasklet implements Tasklet {
        final CountDownLatch entered = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);

        @Override
        public RepeatStatus execute(
                StepContribution contribution,
                ChunkContext context) throws Exception {

            entered.countDown();

            if (!release.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Test gate timed out");
            }

            // Force another iteration so framework handles the stop signal.
            return RepeatStatus.CONTINUABLE;
        }
    }
}
```

The `run.id=1` data here is only suitable when the test uses an isolated JobRepository created fresh per case. In a shared test suite, use unique identifying `JobParameters` or clean test metadata properly so you do not hit an already `COMPLETED` job instance error. If the environment uses an asynchronous `JobLauncher`, adjust how you await the result; the example above explicitly uses an external `ExecutorService` to launch the job.

This test demonstrates verifying cooperative stopping at a tasklet boundary. It does not prove stop can interrupt un-timed-out I/O, does not verify writer rollbacks, and does not replace integration tests with production readers/writers.

### 11.3. Additional Scenarios to Test

| Scenario | What to Verify |
|---|---|
| Stop while `STARTED` | Request is accepted; observed final status is `STOPPED` once the execution processes stop |
| Stop while `STOPPING` | API returns appropriate status; avoid infinite retries |
| Stop non-existent ID | Does not return false success; clear error mapping |
| Stop `COMPLETED` execution | Does not alter the completed job |
| Stop mid-chunk | Committed data/checkpoints are consistent; no lost or duplicated records on restart |
| Stop when writer fails | Final status may be `FAILED`; accurately reports root cause |
| Restart after `STOPPED` | Creates a new `JobExecution` under the same `JobInstance`, without unintentionally reprocessing committed items |
| Worker killed mid-run | Detect stale metadata and run recovery procedure; do not assume automatic `STOPPED` |
| Two operators send stop concurrently | No confusing/duplicate control errors; audit every request |

When tests run asynchronously, use latches, futures, or bounded status polling with **timeouts**. Avoid `Thread.sleep(5000)` to guess when a job has started or stopped; fixed sleeps are both slow and unreliable.

## 12. Recommended Operational Workflow

A safe workflow when a job is discovered importing incorrect data:

1. **Identify the execution.** Read running jobs, choose the exact `jobExecutionId`, and verify `JobParameters` so you do not stop the wrong business date.
2. **Send the stop request.** Audit the reason and operator; call `JobOperator.stop(executionId)`.
3. **Monitor status.** Re-read from `JobExplorer` until `STOPPED`, `FAILED`, or `COMPLETED`; if `STOPPING` persists too long, check tasklets, I/O, locks, and worker health.
4. **Inspect data.** Cross-check read/write counts, `commitCount`, `rollbackCount`, emitted side effects, and `ExecutionContext` checkpoints.
5. **Confirm recovery plan.** Prepare the right source data, fix the root cause, and assess idempotency before restarting.
6. **Restart or close out.** Call `restart` only when state and preconditions are valid; if safe continuation is impossible, follow a separate recovery workflow rather than manually mutating metadata.

Example operational log fields to include:

```text
event=batch.stop.requested
jobName=importOrders
jobExecutionId=101
businessDate=2025-05-12
requestedBy=ops-user
reason=source-file-invalid
requestAccepted=true

event=batch.stop.observed
jobExecutionId=101
batchStatus=STOPPED
readCount=50000
writeCount=49750
commitCount=498
```

Numeric values are illustrative data. Logs must be populated from the actual execution while avoiding tokens, passwords, or sensitive personal data.

### When Stop "Has No Effect"

If code keeps running despite calling `stop`, check actual causes in order: is the execution ID and `JobRepository` right, what did the stop call return, did `BatchStatus` transition to `STOPPING`, which step is the worker in, does current work have a timeout, and is checkpoint persistence blocked on locks. A frequent mistake is calling stop from an admin app pointing to a test database while the worker runs against production.

If the process is dead, you cannot expect a vanished thread to return and flip `STOPPING` to `STOPPED`. Metadata status must be reconciled with actual system state and handled via a controlled recovery procedure.

## 13. Practice Exercise

Build an `archiveOrders` job with two steps: `findExpiredOrders` and `writeArchive`. The second step writes up to 100 records per chunk. Requirements:

1. Create an API accepting `jobExecutionId` and calling `JobOperator.stop(...)`. The API returns `202 Accepted` on receipt along with a status-check URL.
2. Build a view or query displaying job name, `JobParameters`, `BatchStatus`, and update timestamp from `JobExplorer`.
3. Use `CountDownLatch` in an integration test to send stop while a chunk/tasklet is active; assert final `STOPPED` status and verify committed records.
4. Call `restart` using the `STOPPED` execution ID and verify the framework creates a new `JobExecution` for the same `JobInstance`.
5. Simulate a reader calling a slow API: set a reasonable timeout and verify stop latency does not depend on unbounded blocking.
6. Write a flow using `stopAndRestart(nextStep)` after a validation step, then explain why this flow-driven stop differs from an operator clicking Stop mid-chunk.

**Review question:** If `JobOperator.stop(101)` returns `true` and `JobExplorer` still reports `STOPPING` after 30 seconds, can you conclude the batch has stopped? **No.** That status only proves the stop signal was recorded; keep monitoring or resolve the bottleneck, and never manually mark it `STOPPED` to hide active work.

## 14. References

- [Spring Batch 5.2 — Advanced Metadata Usage: Stopping a Job](https://docs.spring.io/spring-batch/reference/5.2/job/advanced-meta-data.html): stopping via `JobOperator`, graceful shutdown characteristics, and handling abandoned executions.
- [Spring Batch 5.2 — JobOperator API](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/launch/JobOperator.html): `stop(long)`, `getRunningExecutions`, `restart` contracts and exceptions.
- [Spring Batch 5.2 — StepExecution API](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/StepExecution.html): `setTerminateOnly()` and `isTerminateOnly()`.
- [Spring Batch 5.2 — Controlling Step Flow](https://docs.spring.io/spring-batch/reference/5.2/step/controlling-flow.html): `stopAndRestart`, `end`, and `fail`.
- [Spring Batch — Domain Language](https://docs.spring.io/spring-batch/reference/domain.html): `JobInstance`, `JobExecution`, `StepExecution`, `BatchStatus`, and `ExecutionContext`.
- [Spring Batch 6 — JobOperator API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/launch/JobOperator.html): `stop(JobExecution)` API and deprecation status of the ID overload.
