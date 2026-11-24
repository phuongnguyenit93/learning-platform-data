# Flow Split and Join

In Spring Batch, a Job does not have to run all Steps in a single sequential chain. When groups of work are independent, a Job can split execution into multiple branches to run concurrently, then wait for all branches to finish before continuing with shared work. This mechanism is called **split and join**.

`split` divides a flow into multiple sub-flows that can run in parallel via a `TaskExecutor`. The **join** point is the boundary where the orchestrating flow waits for the branches to finish before moving to the next Step. This organization reduces overall duration when branches can run independently, but requires managing resources, shared data, transactions, and how failures in a branch are handled.

## 1. What are split and join?

Suppose a Job generates an end-of-day report. After validating the business date, the Job needs to perform two independent groups of work:

- Updating balances and aggregating transactions.
- Refreshing customer data and computing segment metrics.

These two groups can run concurrently. Once both finish, the Job aggregates the results and exports the report.

```text
                    prepareStep
                         |
                         v
                       SPLIT
                      /     \
                     /       \
                    v         v
              accountFlow  customerFlow
                    |         |
                    v         v
              calculate   refreshCustomer
                    |         |
                    v         v
              aggregate   calculateSegment
                    |         |
                    +----+----+
                         |
                         v
                        JOIN
                         |
                         v
                  generateReportStep
                         |
                         v
                        END
```

Here:

- **Split:** starts executing the sub-flows in parallel.
- **Flow branch:** a branch consisting of one or more sequential Steps.
- **Join:** waits for the flow branches to finish in order to determine the result of the split section.
- **Post-join Step:** starts only after the split section has completed and the control flow allows continuation.

Join is a synchronization point in control flow. It does not automatically merge data, unify branch transactions, or resolve conflicts when multiple branches write to the same table.

## 2. When should you use split and join?

Split is suitable when a Job has independent groups of work that can run concurrently without depending on each other's immediate results.

Examples:

- Generating multiple separate reports for independent data domains.
- Refreshing a customer cache while another branch aggregates transactions.
- Reading and processing data from independent sources.
- Preparing data for multiple target systems, then running a Step to aggregate results.
- Running independent validations before making a final decision.

Do not use split if branch B needs data produced by branch A in the same run. When data dependencies exist, place the dependent branch after the join or organize the Steps sequentially.

A Job can combine all three patterns: sequential Steps before the split, multiple flows running in parallel, and then a sequential Step after the join.

## 3. Declaring a split flow in Spring Batch 5

Spring Batch provides the `split(TaskExecutor)` API on the Job/Flow builder. Flows added via `add(...)` are executed through the executor.

For example, a Job with a preparation Step, two independent flows, and an aggregation Step after the join:

```java
@Bean
Job endOfDayJob(
        JobRepository jobRepository,
        Step prepareStep,
        Flow accountFlow,
        Flow customerFlow,
        Step generateReportStep,
        TaskExecutor batchFlowExecutor) {

    return new JobBuilder("endOfDayJob", jobRepository)
            .start(prepareStep)
            .split(batchFlowExecutor)
            .add(accountFlow, customerFlow)
            .next(generateReportStep)
            .end()
            .build();
}
```

In this flow, `prepareStep` runs first. Afterward, `accountFlow` and `customerFlow` are launched via `batchFlowExecutor`. When the split section finishes, the Job transitions to `generateReportStep` according to the declared flow.

Each branch can contain a single Step or a sequence of Steps:

```java
@Bean
Flow accountFlow(
        Step calculateAccountBalanceStep,
        Step summarizeAccountStep) {

    return new FlowBuilder<SimpleFlow>("accountFlow")
            .start(calculateAccountBalanceStep)
            .next(summarizeAccountStep)
            .build();
}

@Bean
Flow customerFlow(
        Step refreshCustomerStep,
        Step calculateSegmentStep) {

    return new FlowBuilder<SimpleFlow>("customerFlow")
            .start(refreshCustomerStep)
            .next(calculateSegmentStep)
            .build();
}
```

Within each branch, Steps still run sequentially according to `.start()` and `.next()`. Only the independent branches run in parallel with each other.

## 4. TaskExecutor determines how parallel execution runs

`split()` requires a `TaskExecutor` to execute the flow branches. The executor determines how tasks are dispatched to threads and limits the amount of concurrent work.

In simple examples, `SimpleAsyncTaskExecutor` may be used. However, in production applications, a bounded thread pool should be considered to control resource usage.

```java
@Bean
ThreadPoolTaskExecutor batchFlowExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(8);
    executor.setThreadNamePrefix("batch-flow-");
    return executor;
}
```

With the configuration above, the executor has at most four active concurrent threads and a queue capacity of eight tasks. If the Job only has two branches, at most two branches run during that split. If there are more flows than threads, the remaining flows must wait according to the executor's policy.

The number of threads should not be chosen based solely on CPU count. If branches mostly wait on databases or HTTP, a different configuration may be needed compared to CPU-bound work. Connection pools, external service quotas, database limits, and the load of other concurrently running Jobs must be considered.

## 5. When does join happen?

Join is the synchronization point after all flow branches in the split have finished. The Step after the join is only executed when the split section returns its result to the parent flow.

Example:

```text
Branch A: A1 -> A2 ----------- done
                  \          /
                   \        /
                    JOIN
                   /        \
                  /          \
Branch B: B1 -> B2 ----------- done
                    |
                    v
              aggregateStep
```

If Branch A finishes faster than Branch B, the Job still waits for Branch B. `aggregateStep` does not run immediately when A finishes; it only runs after all branches of the split have finished and the flow result allows continuation.

Therefore, the duration of the split section is usually dominated by the slowest branch, plus orchestration overhead. If branch durations vary widely, a very slow branch can reduce the benefit of parallel execution.

## 6. Split/join is not partitioning

Both mechanisms enable parallel execution, but they solve different problems.

| Criterion | Split and join | Partitioning |
|---|---|---|
| Unit of division | Flow branches, each of which can contain multiple different Steps | A single Step divided into multiple partitions |
| Goal | Run independent groups of work concurrently | Split data of the same processing logic into parts |
| Main components | `Flow`, `split(TaskExecutor)`, `add(...)` | `Partitioner`, manager Step, worker Step, `PartitionHandler` |
| Input data | Each branch can use appropriate sources and JobParameters/context | Each partition typically receives a data range via StepExecutionContext |
| Execution | Steps in flow branches have their own StepExecutions | Each partition creates its own worker StepExecution |
| Example | Computing balances in parallel with refreshing customer profiles | Splitting a customer table into ID ranges for multiple workers to import |

If you need to run three different processes concurrently, split flow is usually easier to express. If you need to run the same worker Step across multiple data ranges, partitioning is usually a better fit.

## 7. Each branch has its own StepExecution and transaction

Flow branches share the parent Job's JobExecution, but each Step execution has its own `StepExecution`. Transactions are managed per Step and per chunk, depending on the Step's configuration.

Example:

```text
JobExecution
    |
    +---- prepareStep StepExecution
    |
    +---- accountFlow
    |        +---- calculateBalanceStep StepExecution
    |        +---- summarizeAccountStep StepExecution
    |
    +---- customerFlow
    |        +---- refreshCustomerStep StepExecution
    |        +---- calculateSegmentStep StepExecution
    |
    +---- generateReportStep StepExecution
```

Steps in the two branches can commit independently. If `calculateBalanceStep` commits while `calculateSegmentStep` fails, the committed data of the account branch is not automatically rolled back. Join does not create a single transaction spanning all branches.

If business requirements dictate undoing the data of a succeeded branch when another branch fails, you must design compensation operations, intermediate states, or a saga. Do not rely on split/join to provide atomicity across multiple transactions.

## 8. Passing data into and out of branches

Parallel branches often need to share a batch code, business date, or snapshot ID. Values provided by the caller when launching the Job can be passed via `JobParameters` and read in each Step using `@StepScope`.

Example of reading a JobParameter:

```java
@Bean
@StepScope
Tasklet accountTasklet(
        @Value("#{jobParameters['businessDate']}") LocalDate businessDate,
        AccountService accountService) {

    return (contribution, chunkContext) -> {
        accountService.calculateFor(businessDate);
        return RepeatStatus.FINISHED;
    };
}
```

If branches produce data that the post-join Step needs to aggregate, write the results to a durable data store keyed by a shared identifier, such as `batchId`. After the join, the aggregation Step reads the results of all branches using that key.

```text
                 JobParameters: batchId
                         |
                +--------+--------+
                |                 |
                v                 v
          accountFlow        customerFlow
                |                 |
                v                 v
         account_summary   customer_summary
                |                 |
                +--------+--------+
                         |
                         v
                    JOIN POINT
                         |
                         v
                 generateReportStep
                   read by batchId
```

Do not let multiple branches write to the same key in `JobExecutionContext` without coordination. JobExecutionContext belongs to the shared JobExecution, so concurrent updates from multiple threads can cause overwrites or unpredictable state. If results must be shared, prefer separate result tables per branch or separate keys, and read them after the join.

## 9. What happens when a branch fails?

If a Step in a flow branch fails and the flow has no error-handling transition, that branch typically ends with a failure status. The split flow aggregates the results of the branches; the Job typically fails and the post-join Step does not run.

Example:

```text
accountFlow:   A1 -> A2 -> COMPLETED
                              \
                               JOIN -> FAILED
                              /
customerFlow:  C1 -> C2 -> FAILED

generateReportStep: does not run in the normal success flow
```

Other branches may have already completed and committed data before the failure is recorded. Do not assume Spring Batch automatically cancels all running branches and rolls back all committed changes when one branch fails. How active branches terminate also depends on the executor, failure timing, and orchestration mechanism; design each branch to terminate safely.

If you want to handle errors inside a branch, you can declare transitions in that flow—for example, transitioning from the failed Step to a Step that records the error or performs compensation. The final result of the flow branch affects the status returned by the split.

### Using ExitStatus to route within each branch

```java
@Bean
Flow accountFlow(
        Step calculateBalanceStep,
        Step recordAccountFailureStep,
        Step summarizeAccountStep) {

    return new FlowBuilder<SimpleFlow>("accountFlow")
            .start(calculateBalanceStep)
                .on("FAILED").to(recordAccountFailureStep)
            .from(calculateBalanceStep)
                .on("COMPLETED").to(summarizeAccountStep)
            .end();
}
```

This example illustrates flow transitions based on ExitStatus. Declare the necessary transitions and decide whether the final flow should be considered a success or failure according to business rules. Do not turn a critical error into `COMPLETED` just to let the Job continue without a status or report that accurately reflects the outcome.

## 10. Restarting a Job with a split flow

Spring Batch persists the JobExecution and StepExecutions of each branch in `JobRepository`. When a Job fails and is restarted with the same identifying JobParameters, the framework uses the persisted metadata to determine which Steps need to re-execute.

Typically:

- Steps that already `COMPLETED` are skipped on restart, unless configured with `allowStartIfComplete(true)`.
- Failed Steps can be re-run if the Job and Step allow restart.
- Chunk-oriented Steps with a reader supporting `ItemStream` can restore checkpoints from StepExecutionContext.
- Completed Steps belonging to other branches may not need to run again.

Example:

```text
First run:
  accountFlow:   A1 COMPLETED, A2 COMPLETED
  customerFlow: C1 COMPLETED, C2 FAILED
  Job: FAILED

Restart same JobInstance:
  accountFlow:   COMPLETED Steps are usually skipped
  customerFlow: C1 is skipped, C2 is re-run
  After branches complete: join -> generateReportStep
```

Exact behavior also depends on flow transitions, StepExecution states, and how the split is configured. Test restarts in scenarios where one branch fails after another branch has committed, rather than only testing scenarios where all branches succeed.

If a completed Step must run again after a restart, `allowStartIfComplete(true)` can be used, but only when the operation is idempotent or protected against duplicate side effects. For example, sending emails, making payments, or generating files needs a stable business key to identify the same action.

## 11. Branch independence and idempotency

For split to be beneficial and safe, each branch should have clear inputs, outputs, and data ownership.

Design principles:

1. Each branch depends only on data ready before the split or data owned by that branch.
2. Branches do not overwrite the same record or the same context key without explicit synchronization.
3. Side effects outside the transaction need stable idempotency keys.
4. Branch results must be durably persisted so the post-join Step can read and reconcile them.
5. If one branch fails, already-completed branches should not need to run again just to reproduce the exact same result.

For example, `accountFlow` writes `account_summary` keyed by `batchId`, while `customerFlow` writes `customer_summary` keyed by the same `batchId`. After the join, `generateReportStep` reads both tables. This separation lets each branch own its own output table and reduces write contention.

If both branches update the same summary table, locking or proper write-range partitioning is needed. Otherwise, running in parallel can cause lock contention, deadlocks, or overwritten results.

## 12. Resource limits and performance

Split reduces duration by running branches concurrently, but it does not eliminate total work. Load on the database, CPU, memory, connection pool, and external services can increase.

When choosing the thread count, consider:

- The number of flow branches that can run concurrently.
- The duration and CPU usage of each branch.
- The number of database connections each Step can hold.
- Quotas and concurrency limits of external APIs.
- Load from other Jobs running in the same application.
- Heap size and the number of objects allocated when multiple Steps run simultaneously.

For example, if each branch has a chunk writer holding one database connection and there are four concurrent branches, the connection pool must have enough capacity to serve them alongside other requests. Increasing threads when the pool only has two connections can cause branches to wait on each other without improving throughput.

Do not use an unbounded executor for Jobs with many flows or Jobs that may be launched concurrently multiple times. A bounded thread pool and suitable queue help control load, though the rejection policy and shutdown behavior must match how the Job is orchestrated.

## 13. Bean thread safety in parallel flows

Steps across branches may run on different threads. Spring singleton beans are shared across threads, so processors, listeners, services, or helpers should not hold per-execution mutable state in shared fields.

Unsafe example:

```java
@Component
public class UnsafeAccountProcessor
        implements ItemProcessor<AccountInput, AccountResult> {

    private AccountInput currentItem;

    @Override
    public AccountResult process(AccountInput item) {
        currentItem = item;
        return calculate(currentItem);
    }
}
```

If multiple Steps or multiple threads share the processor, `currentItem` can be overwritten. Use local variables and keep only immutable dependencies in fields:

```java
@Component
public class AccountProcessor
        implements ItemProcessor<AccountInput, AccountResult> {

    private final AccountCalculationService calculationService;

    public AccountProcessor(AccountCalculationService calculationService) {
        this.calculationService = calculationService;
    }

    @Override
    public AccountResult process(AccountInput item) {
        return calculationService.calculate(item);
    }
}
```

Readers or writers with per-Step state should be declared with an appropriate scope, usually `@StepScope`, so each StepExecution gets its own instance or state as designed. Also verify that concurrently invoked services, caches, and HTTP clients are thread-safe.

## 14. Monitoring split and join

When a Job has multiple branches, checking only the overall Job status is rarely enough to locate bottlenecks. Monitor each StepExecution within each flow branch.

Useful metrics and metadata:

- JobExecution ID and identifying JobParameters.
- Flow branch name and Step name.
- StepExecution ID, BatchStatus, and ExitStatus.
- Start time, end time, and execution duration.
- Read/write/filter/skip counts of chunk Steps.
- Exceptions and retry counts.
- Active thread count and executor queue wait time.
- Elapsed time from when the split starts until the last branch completes.

Attach a correlation ID or `batchId` to logs across all branches to link records together. When investigating a slow Job, compare the duration of each branch; the longest branch typically determines when the join completes.

## 15. Testing split and join

A Job using split needs testing for both business outcomes and orchestration behavior:

- Independent branches execute and the post-join Step only starts after all branches finish.
- Each branch's input data is read accurately.
- One failing branch gives the Job the appropriate status and prevents the post-join Step from running if the flow does not handle errors.
- Error-handling transitions within a branch work according to the declared ExitStatus.
- Restarting after one branch fails does not unexpectedly re-execute already-completed Steps.
- Shared beans do not suffer race conditions under concurrent execution.
- The connection pool and executor support the configured concurrency level.

In tests, a small executor and mock services with latches/barriers can be used to verify that the join point truly waits for the branches. Do not test parallelism solely by measuring elapsed time, as results depend on the test machine and scheduler.

## 16. Common mistakes

**Confusing split/join with partitioning:** split runs multiple different flows; partitioning divides one Step into multiple data slices for worker Steps.

**Assuming join merges transactions:** each Step/chunk has its own transaction. Join only synchronizes the flow and does not roll back committed data in other branches.

**Assuming the post-join Step runs as soon as one branch completes:** join waits for all branches in the split to finish.

**Splitting branches that have data dependencies:** if one branch needs output from another, running in parallel can mean the data is not ready. Place dependencies after the join or sequence them.

**Using an unbounded executor:** can create too many threads and exhaust the connection pool or overload dependent services.

**Multiple branches writing to the same data:** easily causes race conditions, lock contention, or deadlocks. Define clear data ownership per branch.

**Concurrently updating the shared JobExecutionContext from multiple threads:** risks overwrites or unpredictable state. Use separate keys or durable per-branch data stores.

**Assuming one failed branch rolls back other branches:** transactions are independent; committed data from a successful branch remains.

**Not testing restarts:** the states of completed Steps and external side effects can cause unexpected outcomes when the Job runs again.

## 17. Split and join design process

When building a Job with parallel flows, follow these steps:

1. Identify which tasks are genuinely independent and can run concurrently.
2. Place shared preparation steps before the split.
3. Group dependent Steps into separate flow branches.
4. Define durable inputs and outputs for each branch.
5. Configure a bounded `TaskExecutor` aligned with system resources.
6. Place the aggregation Step or next step after the join point.
7. Define the status handling when a branch fails and declare appropriate transitions.
8. Design transactions, idempotency, and compensation mechanisms for committed data.
9. Test concurrency, failures, and restarts in a representative environment.
10. Monitor each branch's duration to spot slow branches and tune resources.

## Conclusion

`split` allows a Job to execute multiple flow branches concurrently via a `TaskExecutor`; `join` is the point that waits for branches to finish before the Job moves to the next Step. Each branch has its own StepExecutions and transactions, so join neither creates a shared transaction nor automatically merges data. Only parallelize independent work, use a bounded executor, pass data through JobParameters or durable stores, avoid concurrent updates to shared context, and design idempotency for side effects. When a branch fails, understand the status of each Step and test restarts to ensure completed branches are not re-executed unexpectedly.
