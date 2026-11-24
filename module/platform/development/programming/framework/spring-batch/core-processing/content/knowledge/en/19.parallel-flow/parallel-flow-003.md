# Executor for Parallel Flows

In Spring Batch, a job can contain multiple independent flows and execute them concurrently using the **split flow** mechanism. The executor determines which threads those flows run on and how many flows can proceed at the same time. When the branches finish, Spring Batch merges their results to continue the shared flow, such as an aggregation step at the end of the job.

The executor is typically passed to `FlowBuilder.split(TaskExecutor)`. With `ThreadPoolTaskExecutor`, the application can bound the number of workers, manage the queue, name threads, and configure shutdown behavior. If `SyncTaskExecutor` is used, branches execute synchronously on the calling thread, so there is no real concurrency.

The executor for parallel flows controls concurrent execution **across flow branches**. It does not automatically make steps within a single flow run in parallel, nor is it the executor used to launch the job from `JobLauncher`. Understanding this scope helps configure concurrency in the right place and avoid creating too many threads or overloading the database.

## Parallel flows and the role of the executor

A flow can consist of multiple steps running sequentially. When a job needs to perform several independent branches, `split` can be used to run those flows concurrently.

For example, a customer data import job has three branches:

- `customerFlow`: normalize and write customers.
- `accountFlow`: synchronize accounts.
- `referenceFlow`: load reference data.

After all three branches complete, `summaryStep` aggregates the results.

```text
                         parentJob
                             |
                             v
                        split(executor)
                       /      |       \
                      /       |        \
                     v        v         v
              customerFlow accountFlow referenceFlow
                     |        |         |
               customerStep accountStep referenceStep
                     |        |         |
                     +--------+---------+
                             |
                        join / wait
                             |
                             v
                        summaryStep
                             |
                             v
                        job complete
```

The executor receives tasks representing each flow branch. Branches can start on different worker threads. `split` waits for the flows in the group to complete before moving to the next step in the parent flow.

A single branch can still contain multiple sequential steps:

```text
customerFlow:  extractCustomer -> normalizeCustomer -> writeCustomer
accountFlow:   extractAccount  -> reconcileAccount
referenceFlow: loadCurrency    -> loadCountry
```

The split executor controls concurrency among the three flows above. Steps inside `customerFlow` still run in their declared order, unless that flow itself defines another parallel structure.

## Configuring TaskExecutor for a split flow

In production applications, `ThreadPoolTaskExecutor` is usually the appropriate choice because it reuses threads and allows controlling concurrency.

Example of creating a fixed pool for up to three concurrent flows:

```java
@Bean(name = "parallelFlowExecutor")
ThreadPoolTaskExecutor parallelFlowExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(3);
    executor.setMaxPoolSize(3);
    executor.setQueueCapacity(6);
    executor.setThreadNamePrefix("batch-flow-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(60);
    return executor;
}
```

Meaning of the properties:

| Property | Meaning | Considerations |
| --- | --- | --- |
| `corePoolSize` | Base number of workers in the pool | Choose based on the number of flows that need to run regularly |
| `maxPoolSize` | Maximum number of workers | Limits concurrency when load increases |
| `queueCapacity` | Number of tasks that can wait in the queue | Use a bounded queue to avoid accumulating too much pending work |
| `threadNamePrefix` | Thread name prefix | Helps identify flow workers in logs and thread dumps |
| `waitForTasksToCompleteOnShutdown` | Tells the executor to wait for accepted tasks on shutdown | Useful when active flows need controlled completion |
| `awaitTerminationSeconds` | Maximum wait time during shutdown | Choose according to the application's reasonable stop window |

With both `corePoolSize` and `maxPoolSize` equal to 3, the pool has at most three workers executing in parallel. The queue holds tasks that do not have an available worker at submission time. `queueCapacity` does not increase the number of concurrently running flows; it only determines how many tasks can wait.

`ThreadPoolTaskExecutor` is managed by Spring as a bean, so the container coordinates initialization and shutdown lifecycles. If you create an executor manually outside Spring, the application must manage initialization and resource release itself.

## Declaring flow branches

Each branch should be described as a clearly named `Flow`. Example:

```java
@Bean
Flow customerFlow(Step extractCustomerStep, Step writeCustomerStep) {
    return new FlowBuilder<SimpleFlow>("customerFlow")
            .start(extractCustomerStep)
            .next(writeCustomerStep)
            .build();
}

@Bean
Flow accountFlow(Step extractAccountStep, Step reconcileAccountStep) {
    return new FlowBuilder<SimpleFlow>("accountFlow")
            .start(extractAccountStep)
            .next(reconcileAccountStep)
            .build();
}

@Bean
Flow referenceFlow(Step loadCurrencyStep, Step loadCountryStep) {
    return new FlowBuilder<SimpleFlow>("referenceFlow")
            .start(loadCurrencyStep)
            .next(loadCountryStep)
            .build();
}
```

Each flow has its own sequence of steps. Steps can share the application's `JobRepository` and transaction manager, but need unique step names within the job scope and resource configurations suitable for concurrent execution.

## Combining flows with split(executor)

After declaring the branches, use `FlowBuilder.split(...)` to specify the executor that runs them:

```java
@Bean
Flow parallelImportFlow(
        @Qualifier("customerFlow") Flow customerFlow,
        @Qualifier("accountFlow") Flow accountFlow,
        @Qualifier("referenceFlow") Flow referenceFlow,
        @Qualifier("parallelFlowExecutor") TaskExecutor executor) {

    return new FlowBuilder<SimpleFlow>("parallelImportFlow")
            .start(customerFlow)
            .split(executor)
            .add(accountFlow, referenceFlow)
            .build();
}
```

In this structure, the first flow is placed in `start(customerFlow)`, and the additional flows are passed via `add(...)`. `split(executor)` orchestrates the branch group using the configured executor.

Then, place the parallel flow into the job and declare the step that runs after the branches finish:

```java
@Bean
Job parallelImportJob(
        JobRepository jobRepository,
        Flow parallelImportFlow,
        Step summaryStep) {

    return new JobBuilder("parallelImportJob", jobRepository)
            .start(parallelImportFlow)
            .next(summaryStep)
            .end()
            .build();
}
```

`summaryStep` starts only after the parallel flow finishes according to the aggregated flow status. It can read results persisted in a suitable shared location, aggregate metrics, or emit the final report.

In applications with multiple `Flow` or `TaskExecutor` beans, use `@Qualifier` to inject the exact branch and executor. Avoid letting Spring pick an unintended default executor meant for another task.

## Synchronous and asynchronous executors

`TaskExecutor` is an abstraction; not every implementation creates concurrency.

| Implementation | Behavior | When appropriate |
| --- | --- | --- |
| `SyncTaskExecutor` | Runs tasks on the calling thread | Testing sequential flows or environments without concurrency needs |
| `SimpleAsyncTaskExecutor` | Creates a new thread per task; supports concurrency limit | Few tasks, light load, or simple examples |
| `ThreadPoolTaskExecutor` | Reuses worker threads and manages a queue | Production workloads needing resource limits and load observability |
| `ConcurrentTaskExecutor` | Adapter for an existing Java executor | Integrating an `Executor` managed elsewhere |

### SyncTaskExecutor

If you pass `SyncTaskExecutor` to split, the flows execute synchronously on the calling thread. This is useful in tests or when keeping the same flow structure without yet running in parallel.

```java
@Bean
TaskExecutor parallelFlowExecutor() {
    return new SyncTaskExecutor();
}
```

The method name remains `parallelFlowExecutor` in the example to match the split configuration, though the actual executor creates no parallel threads. Use a different name in real projects to avoid confusion.

### SimpleAsyncTaskExecutor

`SimpleAsyncTaskExecutor` creates a new thread for each task rather than reusing a pool. You can set `concurrencyLimit` to bound concurrent tasks. It is easy to configure but does not provide worker reuse like a thread pool; for many jobs or flows running continuously, consider thread creation overhead and resource limits.

### ThreadPoolTaskExecutor

`ThreadPoolTaskExecutor` is usually suitable for server applications because both its pool and queue are bounded. It lets the application control how many flows run simultaneously, observe threads, and configure a rejection policy under overload.

## Understanding core size, max size, and queue

A common misconception about `ThreadPoolTaskExecutor` is that the pool necessarily scales threads from core to max as soon as a new task arrives. Following `ThreadPoolExecutor` behavior, new tasks are normally queued once the worker count reaches core size. Only when the queue is full does the pool expand workers toward max size; if both the pool and queue are full, tasks may be rejected.

Example:

```text
corePoolSize = 2
maxPoolSize  = 4
queueCapacity = 5

Task 1, 2  -> run on 2 core workers
Task 3..7  -> placed into the queue
Next task  -> when queue is full, pool can scale workers up to 3 then 4
Tasks exceeding acceptance capacity -> apply rejection policy
```

If you want to cap concurrency strictly at three flows, setting `corePoolSize=3` and `maxPoolSize=3` is straightforward. A bounded queue decides how many tasks can wait if more than three branches are submitted.

Do not use an unbounded queue arbitrarily. When multiple jobs run concurrently, a large queue can accumulate many waiting flows, increasing completion time and memory consumption. When the queue is full, use a clear rejection policy or back-pressure rather than accepting more work than capacity allows.

## How should the worker count be chosen?

Worker count should not be chosen based solely on CPU count or the number of branches in one job. A flow can consume database connections, memory, CPU, and external services throughout its run.

Limits to consider:

- **Actually independent branches:** no need to create an oversized pool if the job only has two branches.
- **Database connection pool:** each branch may need connections during transactions; a pool that is too small makes branches wait on each other.
- **Database capacity:** many concurrent transactions can increase lock contention, deadlocks, and I/O.
- **CPU and memory:** CPU-heavy processors or ones holding many items can overload the server.
- **External system limits:** APIs, brokers, or reference services may have concurrency quotas.
- **Other jobs on the same application:** an executor may be shared by multiple jobs, so total concurrency can exceed the branches of one job.

For example, if three branches all write to the database and the connection pool only has two connections available for batch work, the third branch may have to wait. Raising the executor to ten workers can increase contention on the database without increasing throughput.

A good starting point is setting max workers according to the expected number of independent branches, then measuring connection wait times, locks, CPU, memory, and external latency. Adjust based on real metrics rather than guessing thread counts.

## Parallel flow vs. JobLauncher executor

Spring Batch uses `TaskExecutor` in several places, and each place controls a different type of concurrency.

| Configuration location | Controls |
| --- | --- |
| `FlowBuilder.split(taskExecutor)` | Running flow branches concurrently inside one job |
| `TaskExecutorJobLauncher` | Running a job execution on a worker thread instead of the calling thread |
| Multi-threaded step or partition handler executor | Controlling concurrency within a single step according to the respective mechanism |

For instance, an application can launch two different `JobInstance`s with `TaskExecutorJobLauncher`, while each job also has a parallel flow using its own executor. Total concurrency can then equal the number of running jobs multiplied by the concurrent branches per job, if resources permit.

Do not use the `JobLauncher` executor expecting it to split flow branches automatically. To run parallel flows, pass the executor directly to `split(...)`.

## Join: the next flow waits for branches

A split flow has a logical convergence point after the branches. Spring Batch waits for the flows in the group to complete before continuing the flow after the split.

This has several implications:

- `summaryStep` should not assume the fastest branch represents the entire result.
- Total split duration is typically governed by the slowest branch, plus orchestration overhead.
- One branch may finish early and release its worker while another branch is still running.
- If a branch fails, the status of the split/parent flow reflects the aggregated result according to Spring Batch rules and configured flow transitions.

Example:

```text
customerFlow   [ 10s ] -------- COMPLETED --+
accountFlow    [       35s       ] COMPLETED +--> join --> summaryStep
referenceFlow  [  15s ] ------- COMPLETED --+
```

In the example, summary starts only after `accountFlow` finishes at 35 seconds. Adding more workers does not help if a branch is slow due to a query, lock, or API latency; that branch itself must be profiled and optimized.

## Conditions for running branches safely in parallel

Parallel flows only pay off when branches can execute independently or already have an explicit synchronization mechanism.

Before putting two steps into different branches, check:

1. Do the two branches read/write the same records or the same file?
2. Is there a data dependency on the other branch's output?
3. Is execution ordering required?
4. Can separate transactions per step still satisfy business requirements?
5. When one branch fails, what data has the other branch already committed?
6. Can the failed branch be re-run without creating duplicates?

If `accountFlow` needs data produced by `customerFlow`, the two flows are not independent and should not run in parallel that way. Place `customerFlow` first, and only split branches that depend on data already ready.

## Thread safety of steps and components

Flow branches run on multiple threads. Therefore, objects shared across branches must be safe under concurrent access.

### Singleton services

Spring services are typically singletons. If a service holds mutable state in a field, multiple branches can mutate that state concurrently and cause race conditions. Shared services should be stateless or use appropriate thread-safe/synchronized structures.

### Readers and writers

Readers or writers with state such as cursors, file positions, buffers, or counters should not be shared concurrently across branches unless the implementation is designed to be thread-safe. Each branch should have its own reader/writer with appropriate resources and stream names.

For example, two branches writing files should use two separate output paths. If writing to the same file, explicit synchronization and a clear record format are needed; it is usually easier to manage if each branch writes its own file and a step merges them after the join.

### StepScope

`@StepScope` creates beans scoped to `StepExecution`, which is useful for stateful readers/writers or when late binding from job/step parameters is needed. When branches create separate `StepExecution`s, step-scoped components can hold isolated state for each execution.

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> customerReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {
    // Create a dedicated reader for the current StepExecution.
    return buildReader(inputFile);
}
```

Ensure scopes are configured properly and avoid storing execution-specific state in singleton fields outside step-scoped components.

## Transactions and data during parallel execution

Each branch step has its own execution and transaction boundary. A split flow does not create a single transaction enclosing all branches.

For example, `customerFlow` commits successfully while `accountFlow` fails. Committed customer data remains; Spring Batch does not automatically roll back completed transactions in another branch just because one branch failed.

```text
customerFlow:  transaction -> COMMIT ------------------+
                                                     |
accountFlow:   transaction -> ROLLBACK                +--> split failure
                                                     |
referenceFlow: transaction -> COMMIT ----------------+
```

If a job needs to undo changes across all branches when one branch fails, design a compensation mechanism or a separate staging/publish workflow. You cannot rely on split flow for a distributed atomic transaction across steps.

When branches write to the same database, the database still manages each branch's transactions and locks separately. Avoid updating the same rows in inconsistent orders, use clear business keys, and test for deadlocks. If branches partition non-overlapping data ranges, safe parallel execution is generally much easier.

## Failure states and flow transitions

Each branch can complete, stop, or fail according to its own logic. The split flow aggregates branch results so the parent flow can decide the next step. Clearly design what happens when a branch fails.

Common options:

- Let a branch failure fail the job and require a restart after fixing the root cause.
- Use transitions or a dedicated flow to run a recovery step when the split status matches.
- Allow a branch to end with a custom exit code if the business clearly defines that state as acceptable.
- Record each branch's result so the aggregation step can report which branches succeeded or failed.

Do not catch exceptions inside a tasklet and return `FINISHED` just to let the split continue. Doing so can turn a failed branch into a false success. If an error is retryable or skippable, configure fault tolerance on the corresponding branch step.

For flows with custom exit codes, check both `BatchStatus` and `ExitStatus`. Flow transitions typically depend on exit codes; tests must confirm the actual patterns match as expected.

## Restarting a parallel flow

Each branch contains its own `StepExecution`s with metadata stored in `JobRepository`. When a job fails, restarts rely on each step's status and the job's restart rules.

Several scenarios:

- Branch A completes, branch B fails: on restart, Spring Batch can skip already-completed steps and resume the restartable step according to metadata.
- A branch has multiple steps and a middle step fails: previously completed steps may not re-run if restart semantics allow.
- A branch writes data to an external system and fails before the checkpoint is saved: output may be resent; the writer must be idempotent.
- A branch depends on a file created by another branch: the file must exist and have a stable version on restart.

Keep identifying job parameters stable when restarting the same `JobInstance`. Do not add a new identifying timestamp just to bypass duplicate-run errors, as that creates a new logical instance and may cause all branches to re-run from the beginning.

If branches share resources outside the database, persist appropriate checkpoints/references and design cleanup to run only after all branches needing that resource have finished.

## Rejection, queues, and back-pressure

Executors have bounded workers and queues. When an application runs multiple jobs in parallel, several split flows may submit branches to the same pool concurrently. If both the pool and queue are full, the executor can reject tasks according to its rejection policy.

Consider:

- Using a bounded queue to limit waiting flows.
- Choosing a rejection policy with clear behavior; never silently drop tasks.
- Catching and logging submission/rejection errors at the appropriate orchestration level.
- Limiting concurrent jobs to prevent multiple splits from exhausting all workers.
- Monitoring active count, pool size, queue size, and rejected task count.

Do not choose `CallerRunsPolicy` mechanically. This policy can force the submitting thread to run the task directly, altering latency and orchestration flow; in some cases it provides back-pressure, but you must understand its impact on threads calling `JobStep` or the flow engine.

## Nested parallel flows and thread starvation risk

A flow branch can contain another split structure, but using the same small pool for multiple layers of parallelism can cause thread starvation.

For example, all workers of the outer split are running parent branches and waiting for child tasks submitted to that very same pool. If no free workers remain and parent tasks cannot finish to release workers, child tasks may wait indefinitely or until timeout.

To reduce this risk:

- Avoid nesting multiple split levels unless necessary.
- Use separate executors per layer when independent concurrency is needed.
- Ensure the pool has enough workers for the designed nested structure.
- Avoid synchronously waiting on a future submitted to the same pool when all workers are occupied.
- Load-test with branch and concurrent job counts close to production.

Do not grow the pool unboundedly to evade starvation; that can turn the problem into CPU, database, or memory overload. Flow and executor design must consider the entire concurrency model.

## Thread context: logging, security, and tracing

When a flow moves to a worker thread, data bound to the calling thread such as `ThreadLocal`, MDC logging context, or security context is not automatically copied in every configuration.

If correlation IDs or tracing info must be preserved, configure a `TaskDecorator` on `ThreadPoolTaskExecutor` to copy required context at submission time and restore/clear context after the task finishes.

Do not rely on HTTP request context or calling-thread security context if a job can outlive the request. Pass the requester identifier or necessary business context via `JobParameters` or a protected store. Do not put credentials or tokens directly into parameters.

## Shutdown while branches are running

When the application receives a shutdown signal, the executor needs a policy for running or queued branches.

`setWaitForTasksToCompleteOnShutdown(true)` tells the executor to wait for accepted tasks to finish during shutdown. `setAwaitTerminationSeconds(...)` bounds that wait time. This does not guarantee every branch always finishes: the process could be killed, the timeout could expire, or external systems could be unresponsive.

Long-running jobs must be restartable. On abrupt shutdown, uncommitted transactions roll back when resources are released; committed branches retain their data. Readers/writers need checkpoints and external side effects need idempotency.

Do not close database connection pools or external system clients before flow workers have finished their necessary work. Shutdown ordering of executors, datasources, and clients should align with the application lifecycle.

## Testing parallel flows

Testing parallel flows needs to verify both business outcomes and that branches can genuinely run concurrently. Simply asserting the job `COMPLETED` does not prove the executor is configured properly; a `SyncTaskExecutor` can still make a job finish sequentially.

### Testing each branch's outcome

Use integration tests running the job with small datasets. After the job finishes, verify:

- Each branch has corresponding `StepExecution`s.
- Each step's status and `ExitStatus` are correct.
- Each branch's business data is written properly.
- `summaryStep` only runs after required branches finish.
- No duplicates or lost updates occur from concurrent execution.

You can use `JobLauncherTestUtils` to run the job and `JobExplorer` to inspect metadata. If the application context has multiple jobs, specify the test job with `setJob(...)` or inject the appropriate `@Qualifier`.

### Controlled concurrency testing

To confirm two branches run concurrently, use a shared `CountDownLatch` in tests. Each branch counts down the latch on start and waits for the other branch to reach the same point. If the executor genuinely allows at least two workers, both pass the barrier; if running sequentially, the first branch times out.

Example helper for tests:

```java
public class ParallelStartBarrier {

    private final CountDownLatch ready = new CountDownLatch(2);

    public void awaitBothBranches() throws InterruptedException {
        ready.countDown();
        if (!ready.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                    "Both branches did not reach the barrier in time");
        }
    }
}
```

Two test tasklets call `awaitBothBranches()` right at startup. Use a finite timeout so the test does not hang if the executor is configured sequentially or has only one worker. The barrier is only for verifying concurrency in tests; do not put this wait mechanism into production tasklets.

Do not rely on `Thread.sleep` and comparing total runtime to conclude concurrency. Test machine runtime fluctuates with load, so explicit barriers or synchronization give more reliable results.

### Testing a single-branch failure

Make one branch throw a controlled exception while the other completes. Confirm the split/parent status matches the configured flow, committed transactions of the succeeding branch remain intact, and restarts do not create duplicate data.

### Testing executor overload

With a small pool and queue, submit many branches or run multiple parent jobs concurrently to confirm rejection/back-pressure is handled cleanly. Do not let tests depend on non-deterministic timing; use bounded test executors and barriers/latches to control ordering.

## Observing and operating the executor

In production, monitor:

- Pool size, active worker count, and waiting threads.
- Queue size and rejected task count.
- Per-branch duration and wait time at the join.
- Concurrent job/flow count.
- Database connection pool usage, lock waits, and deadlocks.
- CPU, memory, and latency of APIs/brokers used by branches.
- Status of each `StepExecution` and `JobExecution`.

Thread names with a prefix like `batch-flow-` help identify workers in logs and thread dumps. Include job execution ID, step execution ID, and branch name in structured logging to trace parallel branches.

If one branch is consistently slower, measure the reader, processor, and writer timings of that branch. Increasing workers will not necessarily fix a slow query or a rate-limited API.

## Common mistakes

### Using SyncTaskExecutor while expecting parallel branches

`SyncTaskExecutor` runs on the calling thread. Use `ThreadPoolTaskExecutor` or an appropriate asynchronous executor when concurrency is needed.

### Passing the executor to the wrong place

The `JobLauncher` executor controls job execution; the executor in `split(...)` controls flow branches. Configure the right place for parallel execution.

### Mistaking queueCapacity for worker count

The queue only holds waiting tasks. Concurrent executing workers are bounded by the pool size.

### Increasing threads and overloading the database

Many branches opening transactions or connections concurrently can increase lock contention and deadlocks. Bound the pool according to database and connection pool capacity.

### Sharing non-thread-safe readers/writers

Branches may access mutable state or write to the same file concurrently. Use separate components, `@StepScope`, separate resources, or proper synchronization.

### Running data-dependent branches in parallel

If branch B needs branch A's result, split may run B before A finishes. Separate dependent parts into sequential flows or place the step after the join.

### Assuming one branch failure rolls back all branches

Steps have separate transactions; committed branches do not automatically roll back when another branch fails. Use staging, idempotency, or compensation if global recovery is needed.

### Small pool causing starvation in nested splits

Parent tasks occupy all workers while waiting on child tasks in the same pool. Avoid nested splits or design separate executors with enough workers.

### Not handling shutdown and rejection

Tasks may be rejected or interrupted when the application shuts down. Configure queues, rejection policies, graceful shutdown, and proper restarts.

## Principles for designing a parallel flow executor

When bringing split flows into production, determine:

1. Which branches are genuinely independent and can run concurrently?
2. How many database connections, CPU, memory, and external quotas does each branch need?
3. How do `corePoolSize`, `maxPoolSize`, and `queueCapacity` bound concurrency and queuing?
4. Do multiple jobs share the executor?
5. Are shared readers, writers, and services thread-safe?
6. Do branches overwrite each other's data or resources?
7. When one branch fails, how is data committed by other branches handled?
8. Can restarts resume each branch without creating duplicates?
9. How are rejection, thread context, and shutdown handled?
10. Have tests verified concurrent branch execution, join, failure, and restart?

For most applications, a `ThreadPoolTaskExecutor` with bounded size, bounded queue, and clear thread naming is a good starting point. Measure real load to tune worker counts. Keep branches independent, use thread-safe components, and design transactions/restarts per step rather than assuming the entire split is a single commit unit.

## Key takeaways

The executor for parallel flows is passed to `FlowBuilder.split(TaskExecutor)` to orchestrate multiple flow branches concurrently. `ThreadPoolTaskExecutor` is generally suited for production because it bounds workers and queues; `SyncTaskExecutor` runs sequentially only. Worker count governs concurrency, while the queue only holds waiting tasks. Split waits for branches to finish before continuing the shared flow, and each branch step has its own transaction. One failing branch does not automatically roll back already-committed branches. Size the pool to match database/CPU/external service capacity, ensure thread-safe readers/writers/services, handle rejection and shutdown, keep identifying parameters stable for restarts, and test concurrency with barriers/latches rather than relying on runtime measurements.
