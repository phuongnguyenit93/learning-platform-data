# Testing Executors in Spring Batch: Verifying Job and Step Execution Mechanisms

In Spring Batch, an **executor** determines which thread runs work, whether tasks execute sequentially or concurrently. When building *test infrastructure*, executor configuration directly affects when a Job launch call returns, how final status is verified, fault reproducibility, and overall test suite stability.

A thorough executor test must answer two separate questions:

1. **Does the executor behave properly?** For example, does a task run on the calling thread or on a worker thread; how many tasks can run concurrently?
2. **Does Spring Batch behave properly with that executor?** Does the Job reach the expected terminal status, does the Step process all items, and is data neither lost nor duplicated during parallel execution?

This lesson progresses from unit-testing `TaskExecutor` directly to integration-testing `JobLauncher`/`JobOperator` and concurrent Steps. All examples include timeouts so a failing test never hangs indefinitely.

## 1. What Is an Executor in the Spring Batch Ecosystem?

`TaskExecutor` is a Spring Framework interface:

```java
public interface TaskExecutor extends Executor {
    void execute(Runnable task);
}
```

Upon receiving a `Runnable`, the executor decides how to run the task. Common implementations:

| Executor | Execution Behavior | When Useful in Tests |
| --- | --- | --- |
| `SyncTaskExecutor` | Runs `Runnable` immediately on the calling thread. | Testing sequential Job/Step logic with easy final-status observation and straightforward stack traces. |
| `SimpleAsyncTaskExecutor` | Runs tasks on another thread, typically creating a new thread per task. | Testing basic asynchronous launching behavior. |
| `ThreadPoolTaskExecutor` | Dispatches tasks to a worker pool with configured pool and queue bounds. | Testing concurrency limits, behavior under load, and executor lifecycle. |
| Custom executor | Intercepts, records, schedules, or executes tasks deterministically for testing. | Verifying task submission and controlling execution order deterministically. |

**Two commonly confused executor configuration points:**

```text
Test / Scheduler / HTTP request
    |
    v
JobLauncher or JobOperator
    |  (A) TaskExecutor launches the Job
    v
Job.execute(...)
    |
    v
Step
    |  (B) TaskExecutor executes chunks/flows in parallel
    v
ItemReader -> ItemProcessor -> ItemWriter
```

- **(A) Job launcher executor:** determines whether `run(...)` or `start(...)` waits for the Job to finish or returns while the Job is still running. It **does not automatically parallelize chunks**.
- **(B) Step or flow executor:** determines whether chunk or flow-branch processing is handed off to worker threads. A Job can be launched synchronously while its chunks still run in parallel.

Beyond these two cases, there are partitioning, split flows, and remote mechanisms. Each has a different coordination model; place assertions at the matching layer.

## 2. Define the Test Contract Before Running

Take an import Job processing 100 transactions:

| Goal | What to Assert | What Not to Assume |
| --- | --- | --- |
| Synchronous executor test | Task finishes before `execute(...)` returns; runs on the calling thread. | Do not assert specific wall-clock speed. |
| Asynchronous executor test | Task is observed on a worker thread; test controls wait and completion gates. | Returning from `execute(...)` does not mean the task finished. |
| Synchronous Job launcher test | Returned `JobExecution` has reached its final status. | `COMPLETED` alone does not prove output data is right. |
| Asynchronous Job launcher test | Job starts, stays running while held at a test gate, then finishes once released. | The initially returned `JobExecution` is not necessarily `COMPLETED`. |
| Parallel Step test | Genuine overlap occurs across workers and final output data is accurate. | Processing or write order of records is not guaranteed. |
| Thread pool configuration test | Tasks obey pool/queue bounds; resources shut down after the test. | Scheduler ordering is not guaranteed across runs. |

Assertions can be grouped into:

- **Status assertions:** `BatchStatus.COMPLETED`, `FAILED`, `STOPPED`; optionally `ExitStatus`.
- **Concurrency assertions:** active task count, thread names, concurrent tasks, start/finish gates.
- **Data assertions:** `readCount`, `writeCount`, `skipCount`, record counts, and output value sets.
- **Lifecycle assertions:** executor resources are released and no tasks remain active when test data is cleaned up.

Never use a timing metric like "must finish under 200 ms" as a substitute for proving concurrency; execution speed varies with CI runners, CPU, and database latency.

## 3. Dependencies and Test Environment Setup

In a Gradle Spring Boot project, typical dependencies are:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

Testing real Jobs requires a properly configured `JobRepository` and `PlatformTransactionManager`, along with the metadata schema matching your Spring Batch version. Use a dedicated test database or schema.

In integration tests using `@SpringBootTest`, disable automatic Job execution on context startup:

```java
@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class MyBatchTest {
    // Test explicitly launches the Job.
}
```

`@SpringBatchTest` provides Spring Batch test utilities; `@SpringBootTest` loads the application. Do not let a Job run automatically before the test finishes preparing fixtures.

### Selecting the API Version

The complete implementations in Sections 4–7 target **Spring Batch 5.x / Spring Boot 3.x**:

- `org.springframework.batch.core.Job`, `JobExecution`, `JobParameters`.
- `JobLauncher` and `TaskExecutorJobLauncher`.
- `JobLauncherTestUtils.launchJob(...)` when using the test launcher utility.

In **Spring Batch 6.x**, APIs are reorganized under packages such as `...core.job`, `...core.job.parameters`, and `...core.step`. `TaskExecutorJobOperator` and `JobOperatorFactoryBean` are the standard APIs for configuring an executor on `JobOperator`. The concepts of testing `TaskExecutor`, latches, status, timeouts, and data isolation remain identical, though imports and launching utilities must match the version. Section 8 covers the Spring Batch 6 variant.

## 4. Unit-Testing `SyncTaskExecutor`: Synchronous Control

`SyncTaskExecutor` is useful when a test focuses on Batch business logic and does not aim to test concurrency.

JUnit Jupiter and AssertJ example:

```java
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.core.task.TaskExecutor;
import org.springframework.core.task.SyncTaskExecutor;

import static org.assertj.core.api.Assertions.assertThat;

class SyncExecutorTest {

    @Test
    void shouldRunOnCallingThreadBeforeExecuteReturns() {
        TaskExecutor executor = new SyncTaskExecutor();
        String callingThread = Thread.currentThread().getName();
        AtomicReference<String> actualThread = new AtomicReference<>();
        AtomicReference<String> outcome = new AtomicReference<>("not-run");

        executor.execute(() -> {
            actualThread.set(Thread.currentThread().getName());
            outcome.set("done");
        });

        assertThat(actualThread.get()).isEqualTo(callingThread);
        assertThat(outcome.get()).isEqualTo("done");
    }
}
```

When `execute(...)` returns, the task has already finished. `SyncTaskExecutor` also has a useful testing trait: uncaught exceptions in `Runnable` propagate directly to the `execute(...)` caller. That makes root-cause tracing easier in sequential tests, though **it does not mean every Step exception will always escape the Job launcher**: Spring Batch normally catches Step exceptions and records `FAILED` in `JobExecution`.

When a test targets read/write behavior or data transformations, synchronous execution eliminates scheduler variability.

## 5. Unit-Testing `ThreadPoolTaskExecutor`: Proving Two Tasks Run Concurrently

To prove an executor actually runs tasks concurrently, use a `CountDownLatch` as a rendezvous gate. Do not rely on `Thread.sleep(100)` and guess that tasks overlapped.

The complete example below launches two workers, holds both inside execution, and only opens the exit gate after observing both active tasks:

```java
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import static org.assertj.core.api.Assertions.assertThat;

class ThreadPoolExecutorTest {

    @Test
    void shouldRunTwoTasksAtTheSameTime() throws Exception {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(0);
        executor.setThreadNamePrefix("batch-test-");
        executor.initialize();

        CountDownLatch bothStarted = new CountDownLatch(2);
        CountDownLatch allowFinish = new CountDownLatch(1);
        CountDownLatch bothFinished = new CountDownLatch(2);
        Set<String> workerNames = ConcurrentHashMap.newKeySet();

        Runnable task = () -> {
            try {
                workerNames.add(Thread.currentThread().getName());
                bothStarted.countDown();

                if (!allowFinish.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Test gate timed out");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Worker interrupted", ex);
            } finally {
                bothFinished.countDown();
            }
        };

        try {
            executor.execute(task);
            executor.execute(task);

            assertThat(bothStarted.await(3, TimeUnit.SECONDS))
                    .as("Both tasks must start before releasing the latch")
                    .isTrue();
            assertThat(workerNames).hasSize(2);
            assertThat(workerNames)
                    .allMatch(name -> name.startsWith("batch-test-"));
        } finally {
            allowFinish.countDown();
            assertThat(bothFinished.await(6, TimeUnit.SECONDS))
                    .as("Workers must exit before the test ends")
                    .isTrue();
            executor.shutdown();
        }
    }
}
```

Explanation:

1. The pool has two core threads; `queueCapacity=0` prevents queuing the second task while a worker slot is free.
2. Each task calls `bothStarted.countDown()` and waits on `allowFinish`.
3. If both call `countDown()` before being released, that proves both were inside `Runnable` simultaneously.
4. `workerNames` is a thread-safe set confirming the two tasks did not run sequentially on one thread.
5. `finally` releases the latch even if an assertion fails, preventing workers from hanging indefinitely.
6. `executor.shutdown()` cleans up pool resources after the test.

Timeouts should have generous headroom for CI. On very slow runners, `3` and `6` seconds may need adjustment, because **happens-before ordering** matters far more than absolute wall-clock duration.

### Testing Capacity Limits and Task Rejection

For a pool with fixed bounds and queue capacity, hold workers with a latch, fill the queue, and assert that an extra submission past capacity is rejected, e.g., with `TaskRejectedException` (depending on Spring and the configured handler). Design task counts, queue capacity, and blocking gates deterministically rather than relying on random timing.

Never replace all `ThreadPoolTaskExecutor` tests with `SyncTaskExecutor` if the goal is catching race conditions or resource-bound errors.

## 6. Spring Batch Integration: Testing a Job with a Synchronous Executor

In Spring Batch 5.x, `TaskExecutorJobLauncher` can use `SyncTaskExecutor` to run the Job on the calling thread. The integration test below assumes the application defines an `importOrdersJob` bean and fixtures allowing the Job to finish successfully.

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.launch.support.TaskExecutorJobLauncher;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.core.task.SyncTaskExecutor;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
@Import(SynchronousJobLauncherIT.ExecutorConfig.class)
class SynchronousJobLauncherIT {

    @Autowired
    @Qualifier("syncTestLauncher")
    private JobLauncher jobLauncher;

    @Autowired
    @Qualifier("importOrdersJob")
    private Job importOrdersJob;

    @Test
    void shouldReturnCompletedExecution() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("testRunId", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution = jobLauncher.run(importOrdersJob, parameters);

        // Synchronous launcher: Job has already finished when run(...) returns.
        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);
        assertThat(execution.getEndTime()).isNotNull();
    }

    @TestConfiguration
    static class ExecutorConfig {

        @Bean("syncTestLauncher")
        JobLauncher syncTestLauncher(JobRepository repository)
                throws Exception {
            TaskExecutorJobLauncher launcher =
                    new TaskExecutorJobLauncher();
            launcher.setJobRepository(repository);
            launcher.setTaskExecutor(new SyncTaskExecutor());
            launcher.afterPropertiesSet();
            return launcher;
        }
    }
}
```

Use a random `testRunId` so independent runs do not collide with a `COMPLETED` `JobInstance` in the same `JobRepository`. For restart tests, keep the identifying parameters identical across runs and do not delete metadata in between.

The test above verifies how the launcher integrates the executor with Spring Batch: the final `JobExecution` state is observed **immediately after** the synchronous call. This setup works well for most business tests. Testing an asynchronous launcher requires a different test with a controllable gate.

## 7. Spring Batch Integration: Testing an Asynchronous Job Launcher

When a Job launcher uses an asynchronous executor, the launch call can return before the Job reaches a terminal status:

```text
Test thread               Worker thread                 JobRepository
    |                          |                               |
    |---- run(Job, params) ----|------------------------------>|
    |<--- JobExecution ------- |      saves STARTING           |
    |                          |---- Job.execute() ----------->|
    |                          |      STARTED                  |
    | ...test waits w/ timeout |      processes Step           |
    |                          |      COMPLETED/FAILED         |
    |---- reads back repository ------------------------------>|
```

**Do not assert `BatchStatus.COMPLETED` immediately on the returned object** while the Job is still running. `JobExecution` state changes over time. Use `JobExplorer` to query the persisted record and poll until a terminal state with a timeout.

### Configuring an Asynchronous Launcher for Tests

In Spring Batch 5.x:

```java
@TestConfiguration
static class AsyncLauncherConfig {

    @Bean("asyncTestLauncher")
    JobLauncher asyncTestLauncher(JobRepository repository)
            throws Exception {
        TaskExecutorJobLauncher launcher =
                new TaskExecutorJobLauncher();
        launcher.setJobRepository(repository);
        launcher.setTaskExecutor(
                new SimpleAsyncTaskExecutor("batch-async-test-"));
        launcher.afterPropertiesSet();
        return launcher;
    }
}
```

In real applications, you can swap `SimpleAsyncTaskExecutor` for `ThreadPoolTaskExecutor` when testing actual pool/queue limits. For pool beans, make sure the pool shuts down when the application context closes.

### Checking Final Status via Polling with Timeout

Assuming `asyncTestLauncher` is defined as above and `importOrdersJob` has its required fixtures ready:

```java
import java.time.Duration;
import java.util.UUID;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.explore.JobExplorer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

// Inside a test class with @SpringBatchTest, @SpringBootTest, and
// @Import(AsyncLauncherConfig.class).
//
// @Autowired @Qualifier("asyncTestLauncher") JobLauncher asyncLauncher;
// @Autowired @Qualifier("importOrdersJob") Job importOrdersJob;
// @Autowired JobExplorer jobExplorer;

@Test
void shouldEventuallyCompleteAfterAsyncLaunch() throws Exception {
    var params = new JobParametersBuilder()
            .addString("testRunId", UUID.randomUUID().toString())
            .toJobParameters();

    JobExecution accepted = asyncLauncher.run(importOrdersJob, params);
    Long executionId = accepted.getId();

    await()
            .atMost(Duration.ofSeconds(15))
            .pollInterval(Duration.ofMillis(100))
            .untilAsserted(() -> {
                JobExecution current =
                        jobExplorer.getJobExecution(executionId);
                assertThat(current).isNotNull();
                assertThat(current.getStatus())
                        .isEqualTo(BatchStatus.COMPLETED);
            });
}
```

`Awaitility` is typically brought in transitively with `spring-boot-starter-test`; if your project lacks it, add the test dependency explicitly. This example uses `Spring Batch 5.x`; `JobExecution` and `JobParametersBuilder` moved packages in 6.x.

In this test, Job completion shows that the asynchronous path works without failing, yet **does not by itself prove the initial call returned before the Job finished**. To truly test asynchronous dispatch, place a controlled `CountDownLatch` inside a Tasklet/Processor. Have the worker wait on the latch, verify the launcher call already returned while the latch is still closed, then release the latch and wait for `COMPLETED`. This avoids drawing conclusions from CPU speed.

Conceptual pattern:

```java
CountDownLatch stepStarted = new CountDownLatch(1);
CountDownLatch allowStepToFinish = new CountDownLatch(1);

// Test fixture tasklet:
// stepStarted.countDown();
// if (!allowStepToFinish.await(10, TimeUnit.SECONDS)) {
//     throw new IllegalStateException("Gate timed out");
// }
// return RepeatStatus.FINISHED;

// Test method:
JobExecution accepted = asyncLauncher.run(gatedJob, params);

try {
    assertThat(stepStarted.await(3, TimeUnit.SECONDS)).isTrue();

    // Since the tasklet is still blocked, the job cannot have finished yet.
    JobExecution current =
            jobExplorer.getJobExecution(accepted.getId());
    assertThat(current.getStatus())
            .isIn(BatchStatus.STARTING, BatchStatus.STARTED);
} finally {
    allowStepToFinish.countDown();
}

// After releasing the latch, poll JobExplorer until COMPLETED.
// Wait until the Job fully finishes before cleaning JobRepository.
```

Note: fixture latches must belong to a single test or be reset cleanly; never share a depleted zero-count latch across runs. In `@AfterEach`, never delete metadata while an asynchronous Job may still be updating `StepExecution`/`JobExecution`.

## 8. Spring Batch 6.x Variant

Spring Batch 6 reorganizes Job APIs and uses `JobOperator` as the primary operational interface for many actions, including launching Jobs. Configuring an asynchronous executor per the documentation uses `JobOperatorFactoryBean`:

```java
import org.springframework.batch.core.launch.support.JobOperatorFactoryBean;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.SimpleAsyncTaskExecutor;

@Bean
JobOperatorFactoryBean asyncJobOperator(JobRepository repository) {
    JobOperatorFactoryBean factory = new JobOperatorFactoryBean();
    factory.setJobRepository(repository);
    factory.setTaskExecutor(
            new SimpleAsyncTaskExecutor("batch-operator-test-"));
    return factory;
}
```

This snippet illustrates *executor* wiring; a real application context still needs the remaining batch infrastructure such as `JobRegistry` and `JobRepository`. `JobOperatorTestUtils` in `spring-batch-test` can start the configured test Job via `startJob(parameters)`.

When testing Job logic synchronously, configure `SyncTaskExecutor` instead of `SimpleAsyncTaskExecutor` on the test-scoped `JobOperator` bean. When testing asynchronous behavior, apply the same latch and `JobExplorer` polling pattern from Section 7.

Never mix Spring Batch 5 and 6 imports for `Job`/`Step`/`JobParameters` in the same project; choose the right APIs based on your actual dependencies.

## 9. Testing Executors in a Concurrent Step

In a multi-threaded Step, the executor is configured directly on the Step builder. In Spring Batch 5.x:

```java
@Bean
Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter,
        TaskExecutor batchStepExecutor) {

    return new StepBuilder("importStep", jobRepository)
            .<Order, Order>chunk(10, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .taskExecutor(batchStepExecutor)
            .build();
}
```

`Order`, the reader/processor/writer beans, and `batchStepExecutor` are application-provided components. In Spring Batch 6.x, chunk/transaction manager builder signatures may differ; consult your version's API.

### Properties to Verify

- **No lost or duplicate records:** total output IDs must equal valid inputs with no duplicates.
- **Order independence:** instead of asserting `[1, 2, 3, 4]` in exact order, use `containsExactlyInAnyOrder(...)` or compare ID sets.
- **Genuine concurrency:** track active workers with `AtomicInteger`/latches; verify at least two workers overlapped if concurrency is a requirement.
- **Resource bounds:** size pools, datasources, and transaction managers appropriately; with databases, connection pool size can throttle parallelism.
- **Thread safety:** `ItemReader`, `ItemProcessor`, `ItemWriter`, and shared beans must be safe under concurrent access; strictly avoid unsynchronized mutable fields.

You can instrument entry/exit concurrency in a Processor like this:

```java
AtomicInteger inFlight = new AtomicInteger();
AtomicInteger peakConcurrency = new AtomicInteger();

ItemProcessor<Integer, Integer> processor = item -> {
    int active = inFlight.incrementAndGet();
    peakConcurrency.accumulateAndGet(active, Math::max);

    try {
        // Process the item; optionally use a test latch to force overlap.
        return item * 2;
    } finally {
        inFlight.decrementAndGet();
    }
};
```

After the Job completes, if the test fixture was designed to hold two workers concurrently:

```java
assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(peakConcurrency.get()).isGreaterThanOrEqualTo(2);
assertThat(output).containsExactlyInAnyOrder(2, 4, 6, 8);
```

If the processor executes extremely fast, `peakConcurrency` can stay at 1 even though the executor supports concurrency. Therefore, to make `>= 2` deterministic, create a **controlled rendezvous point** (such as a two-worker `CountDownLatch` or barrier) in the test fixture, launch the Job from another thread so the test thread can release the latch, and put timeouts on every wait.

### Reader Thread Safety

Many `ItemReader`s hold internal state (cursors, line positions, record counts), so using them directly in a multi-threaded Step can corrupt reads or break restartability. Use an inherently thread-safe reader, partition the data source (*partitioning*), or wrap with a decorator like `SynchronizedItemReader`/`SynchronizedItemStreamReader` where appropriate. Synchronizing `read()` alone does not automatically solve all state, transaction, and restart concerns; verify the concrete behavior thoroughly.

### Transaction Notes

Spring binds transactions to threads. In a multi-threaded Step, never assume the calling thread's transaction context propagates to workers. Verify commits, rollbacks, retries/skips, and idempotency against real infrastructure, especially when `ItemProcessor`/`ItemWriter` perform database operations.

## 10. Testing Executors for Split Flows and Partitioning

Executors also appear at the Job flow level or partition handler level:

| Processing Model | Executor Coordinates | Suggested Tests |
| --- | --- | --- |
| Split flows | Flow branches can run concurrently. | Verify both branches start and the Job finishes only after all branches complete. |
| Local partitioning | Runs worker `StepExecution`s per partition. | Verify each partition processes its exact range with no gaps/duplicates and status aggregates accurately. |
| Multi-threaded chunk Step | Multiple chunks/units processed on worker threads. | Verify thread safety, Step status, total counts, and idempotency. |

Do not assume that merely configuring a `TaskExecutor` guarantees every branch runs in parallel. Actual concurrency depends on task counts, pool limits, queues, Step settings, database resources, and deployment configuration. To prove concurrency in a test, supply enough work and synchronization so two workers genuinely overlap.

## 11. Organizing Tests to Avoid Flakiness and Thread Leaks

### 11.1. Use Synchronous Execution for Most Business Tests

Tests verifying parsing, transformations, skips, retries, listeners, or statuses can usually run with `SyncTaskExecutor`. Reserve asynchronous pools and controlled synchronization gates for tests specifically targeting concurrency behavior.

### 11.2. Never Use Fixed Sleeps to Guess Completion

Fragile pattern:

```java
jobLauncher.run(job, params);
Thread.sleep(300);
assertThat(jobExplorer.getJobExecution(id).getStatus())
        .isEqualTo(BatchStatus.COMPLETED);
```

Job execution time varies by environment. A fixed delay both slows down tests and fails to guarantee the Job finished. Use `CountDownLatch`, `Future.get(timeout, unit)`, `CompletableFuture`, or bounded polling depending on the layer under test.

### 11.3. Always Release Threads and Blocking Gates

When a test fails, `finally` must still release latches and interrupt or shut down any executor owned by the test. For a test-created `ThreadPoolTaskExecutor`, call `shutdown()`. For Spring-managed executor beans, ensure the application context lifecycle closes cleanly with no background tasks still touching test resources.

### 11.4. Isolate `JobRepository` and Business Data

Asynchronous Step/Job results may still be flushing to metadata tables. Do not clean metadata right after `run(...)` just because the call returned. Wait for terminal status first, and only then call `JobRepositoryTestUtils.removeJobExecutions()` on a dedicated test repository. Likewise, never delete input/output files or business tables while workers may still be using them.

### 11.5. Do Not Share Mutable State Across Parallel Tests

`CountDownLatch`, `AtomicInteger`, queues, output lists, file paths, and `JobParameters` names should be scoped per test. If Spring's test context caches shared beans holding mutable state, design explicit resets or isolation. Test thread pools should also use distinct thread-name prefixes to simplify debugging.

### 11.6. Avoid Asserting Exact Completion Order

Submitting two tasks in order A, B does not mean they finish in order A, B. Only assert ordering if it is an explicit contract of the executor/infrastructure and configured to enforce it. For concurrent processing, output sets and happens-before gates are far more reliable checks.

### 11.7. Distinguish Submission Failures from Execution Failures

Two distinct failure modes exist:

- **Task submission failure:** for example, the pool is shut down or the queue is full and configured to reject. Errors may surface immediately on `execute(...)`/`run(...)`.
- **Job/Step execution failure:** the executor accepts the task, business processing throws an exception, and Spring Batch records `BatchStatus.FAILED` and the exception on `JobExecution`.

A test verifying task rejection should not automatically expect a `JobExecution` marked `FAILED` if the Job never started. A test verifying processing failures should inspect the actual run's `JobExecution`/`StepExecution`.

## 12. Practice Scenario

An application has an `importProductsJob` that reads 20 products, transforms them, and writes to a database. The goal is testing the executor infrastructure under two configurations.

**Scenario A — Synchronous:**

1. Set up a test Job/Step, a 20-product dataset, and an isolated repository.
2. Use `SyncTaskExecutor` for the Job launcher and Step when the test does not need concurrency.
3. Launch the Job with fresh identifying parameters.
4. Assert `BatchStatus.COMPLETED`, accurate `readCount` and `writeCount`, and 20 rows in the target table.
5. Clean metadata and business data after the Job completes.

**Scenario B — Two Concurrent Workers:**

1. Configure `ThreadPoolTaskExecutor` with two workers and a custom thread-name prefix.
2. Use a thread-safe `ItemReader` or partitioned data; build a test Processor with a latch so two tasks reach the rendezvous point together.
3. Launch the Job on a separate thread so the test thread is not blocked while the Processor waits on the latch.
4. Await the two-worker latch with a timeout; confirm two workers actually ran concurrently.
5. Release the latch and wait for Job completion via `Future` or `JobExplorer` with a timeout.
6. Assert `COMPLETED`, 20 unique output IDs with no missing records, using order-independent comparison.
7. Shut down the executor and confirm no active tasks remain before deleting metadata and fixtures.

Once complete, try replacing the two-worker pool with `SyncTaskExecutor` and observe how the overlap assertion behaves. This exercise cleanly separates **executor concurrency capability** from **Spring Batch data correctness and state management**.

## References

- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskExecutor`, executor implementations, and thread pool configuration.
- [Spring Batch 5.2 – Configuring a JobLauncher](https://docs.spring.io/spring-batch/reference/5.2/job/configuring-launcher.html): synchronous/asynchronous executors with `TaskExecutorJobLauncher`.
- [Spring Batch – Configuring a JobOperator](https://docs.spring.io/spring-batch/reference/job/configuring-operator.html): configuring `JobOperator` and executors in Spring Batch 6.x.
- [Spring Batch – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded Steps, split flows, and partitioning.
- [Spring Batch – Unit Testing](https://docs.spring.io/spring-batch/reference/testing.html): Job/Step testing utilities and the Spring Batch test context.
- [Spring Batch 6 – TaskExecutorJobOperator API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/launch/support/TaskExecutorJobOperator.html).

