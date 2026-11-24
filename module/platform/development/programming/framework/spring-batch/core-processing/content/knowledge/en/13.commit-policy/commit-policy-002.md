# CompletionPolicy

In Spring Batch, `CompletionPolicy` is the mechanism that determines when an iteration cycle or a chunk is considered complete. With a chunk-oriented Step, the policy decides when Spring Batch stops collecting items for the current chunk and moves on to the write phase and the transaction commit.

When you configure `.chunk(500, transactionManager)`, the application is using a completion rule based on a fixed number of items. `CompletionPolicy` lets you describe more flexible rules, such as ending a chunk when enough items have been processed, when a period of time has elapsed, or when a custom condition is satisfied.

The important point is that `CompletionPolicy` controls the boundary of one iteration/chunk. It does not decide whether the Job has succeeded or whether the Step has `BatchStatus.COMPLETED`. The execution results of the Job and Step are still managed by the status, the exit status, and other Spring Batch mechanisms.

## 1. Where does CompletionPolicy sit in chunk processing?

Chunk-oriented processing gathers multiple items into a group. Spring Batch reads items, passes them through the processor if there is one, hands the appropriate results to the writer, and then commits the chunk's transaction. `CompletionPolicy` determines when the current group is eligible to end.

```text
Job
 |
 v
Chunk-oriented Step
 |
 v
CompletionPolicy starts the cycle
 |
 +--> ItemReader reads an item
 |       |
 |       v
 |    ItemProcessor processes the item
 |       |
 |       v
 |    Add the result to the chunk
 |       |
 |       v
 |    CompletionPolicy checks the condition
 |       |
 |       +-- Not complete --> Read the next item
 |       |
 |       +-- Complete ------> ItemWriter writes the chunk
 |                              |
 |                              v
 |                         Commit transaction
 |
 +--> Start the next chunk
```

If the policy reports that the chunk is not complete, the Step continues collecting items. When the policy reports completion, the chunk is passed to the writer and the transaction is committed through the Step's mechanism. If the reader reports that the data has run out before the condition is reached, Spring Batch must still finish the remaining data and complete the Step.

## 2. Why do we need CompletionPolicy?

Not every data source or workload suits a fixed commit interval. For example:

- A system may want to commit after every 500 items to achieve stable throughput.
- A data source with an uneven rate may need to limit the time spent collecting items in one chunk.
- An application may want to end a chunk when the item count or the processing time reaches a threshold.
- A specific business or technical rule may require a chunk to end under its own condition.

`CompletionPolicy` separates the rule "when does the chunk end" from the reader, processor, and writer. The reader focuses on reading data, the processor focuses on processing each item, the writer focuses on writing results, and the policy decides the chunk boundary.

For many simple Jobs, a fixed chunk size is enough. Use a custom policy only when there is a specific requirement that a fixed commit interval cannot express well.

## 3. Fixed commit interval and SimpleCompletionPolicy

When you declare the chunk with an integer:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(500, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .build();
```

Spring Batch uses a completion rule based on a fixed number of items. This is a common choice because it is easy to understand and easy to predict: each chunk collects at most 500 items before the writer writes and the transaction commits. The last chunk may have fewer than 500 items if the data source has run out.

You can express the counting rule explicitly with `SimpleCompletionPolicy`:

```java
CompletionPolicy completionPolicy = new SimpleCompletionPolicy(500);

return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(completionPolicy, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .build();
```

`SimpleCompletionPolicy` ends the chunk after the configured number of iterations/items. In the example, the policy uses a threshold of 500. In meaning, this is equivalent to choosing a fixed commit interval of 500.

Use a fixed commit interval when:

- Item sizes are relatively uniform.
- The read and write cost per item is relatively stable.
- The system needs predictable throughput.
- The transaction requirement can be expressed as the number of items in each chunk.

## 4. Configuring CompletionPolicy directly on a Step

In Spring Batch 5, `StepBuilder` supports accepting a `CompletionPolicy` together with a transaction manager. You can declare the policy as a bean for reuse or for centralized configuration control:

```java
@Bean
CompletionPolicy orderChunkPolicy() {
    return new SimpleCompletionPolicy(300);
}

@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        CompletionPolicy orderChunkPolicy,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(orderChunkPolicy, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

The policy is supplied to the Step when the configuration is built. In the example, each chunk ends at a threshold of 300 iterations/items. If you use a shared policy bean across multiple Steps, you must ensure the policy does not hold shared mutable state across executions. A policy is usually created or managed in an appropriate scope so that each chunk has its own context.

## 5. CompletionPolicy works through RepeatContext

`CompletionPolicy` belongs to Spring Batch's repeat mechanism. It works with `RepeatContext`, which is the context that stores the state of one iteration. The main contract has these operations:

- `start(parent)`: initializes the context for a new iteration cycle.
- `update(context)`: updates the state after one execution.
- `isComplete(context)`: checks the completion condition based on the context.
- `isComplete(context, result)`: checks completion taking the result of the iteration into account.

Spring Batch calls these methods during the repeat orchestration lifecycle. A policy can store counters or timestamps in the context to decide when to stop.

`RepeatContext` is not `ExecutionContext`. The two objects have different purposes:

| Object | Role |
|---|---|
| `RepeatContext` | Holds the state of a loop in progress so that the CompletionPolicy can decide when to end. |
| `ExecutionContext` | Stores the durable execution state of a Job or Step, commonly used for checkpoints and restart. |

You should not use `RepeatContext` as a long-term checkpoint store. When you need to resume work after a process stops, use `ExecutionContext` and the appropriate `ItemStream` mechanisms.

## 6. TimeoutTerminationPolicy: ending based on time

Some workloads need to limit the time spent collecting items in a chunk. `TimeoutTerminationPolicy` is a built-in policy that ends the loop when the configured amount of time has elapsed.

For example, to end a chunk after about 30 seconds:

```java
@Bean
CompletionPolicy timeBasedChunkPolicy() {
    return new TimeoutTerminationPolicy(30_000L);
}

@Bean
Step processEventsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        CompletionPolicy timeBasedChunkPolicy,
        ItemReader<EventInput> eventReader,
        ItemProcessor<EventInput, Event> eventProcessor,
        ItemWriter<Event> eventWriter) {

    return new StepBuilder("processEventsStep", jobRepository)
            .<EventInput, Event>chunk(timeBasedChunkPolicy, transactionManager)
            .reader(eventReader)
            .processor(eventProcessor)
            .writer(eventWriter)
            .build();
}
```

The time parameter of `TimeoutTerminationPolicy` is measured in milliseconds. The policy ends the cycle when the time threshold has been reached. This is a time-based condition for ending a chunk, not a hard timeout for cancelling a reader, processor, or writer call that is already running.

For example, if one processor call takes 45 seconds, the policy cannot interrupt it midway just because the 30-second threshold has passed. The completion condition is checked at the appropriate repeat orchestration points; an operation that is already running needs its own timeout if it risks hanging.

A time-based policy can be useful when item rates fluctuate and the application wants to limit chunk collection time. However, it does not guarantee that every chunk has the same number of items. When items are processed quickly, a chunk may contain many items; when items are processed slowly, a chunk may contain few items.

## 7. Combining count and time limits

In some systems, limiting only the item count or only the time is not enough. For example, the application wants a chunk to not exceed 500 items and also not to collect data for longer than 30 seconds.

You can implement a custom `CompletionPolicy` or a composite policy to express multiple conditions. When designing it, you need to clearly define the combination semantics:

- End when any condition is met (for example, 500 items are reached **or** 30 seconds are exceeded).
- End only when all conditions are met (usually less suitable for maximum limits).
- Add conditions based on payload size or the state of the data source.

For maximum limits, the combination usually ends when the first condition is reached. You need to use the right composite policy or implement the corresponding semantics yourself; do not assume that every composite policy uses OR by default.

An illustrative example of the requirement:

```text
Chunk starts
   |
   +--> Count items
   |
   +--> Track time
   |
   +--> Reached 500 items? ------ Yes ----+
   |                                |
   +--> Over 30 seconds? ------- Yes ----+--> End chunk
   |                                |
   +--> Neither reached ---------------+--> Continue reading
```

Not every application needs to combine multiple conditions. A fixed commit interval is usually simpler, easier to test, and easier to predict. Add complexity only when metrics or operational requirements prove it necessary.

## 8. Writing a custom CompletionPolicy

When the built-in policies do not meet the requirements, you can implement the `CompletionPolicy` interface. For example, an application may want to end a chunk when enough items have been collected or when a custom threshold stored in the `RepeatContext` is reached.

A custom policy needs to:

1. Initialize state for each iteration in `start`.
2. Update state in `update`.
3. Check the completion condition in `isComplete`.
4. Handle the case where the repeat result signals termination or the source has no more items.
5. Not depend on global mutable state that may be shared among multiple StepExecutions.

Contract skeleton:

```java
public interface CompletionPolicy {
    RepeatContext start(RepeatContext parent);

    void update(RepeatContext context);

    boolean isComplete(RepeatContext context);

    boolean isComplete(RepeatContext context, RepeatStatus result);
}
```

This is a Spring Batch interface; when implementing it, you need to use the correct package and API for the dependency version in your project. A policy should have small, deterministic logic that is easy to test. You should not perform database queries, call APIs, or cause side effects in `isComplete`, because the method may be called multiple times during orchestration.

If the condition depends on data of the current item, consider where to place the logic. `CompletionPolicy` controls the loop boundary; it does not replace `ItemProcessor` and does not receive the item directly as a parameter. You can update the necessary information through the context under an appropriate design, but you should not turn the policy into the place that holds all the record-processing business logic.

## 9. CompletionPolicy and data at the end of the source

A chunk does not necessarily always reach exactly the target size or time. If the reader returns `null` because the data has run out, Spring Batch ends reading and processes the final chunk with the remaining items.

For example, the chunk size is 100 but the source has only 35 items left; the writer can still receive a final chunk of 35 items. There is no need to wait until there are 100 items before ending the Step.

Similarly, with a time-based policy, the source may run out before the timeout. In that case the Step ends on the reader's end-of-data signal. `CompletionPolicy` determines the loop completion condition, while the reader determines when there are no more items to read.

This is especially important when processing finite data sources such as a CSV file or a database query. With a continuous or polling source, you need to define additional stop conditions for the reader/Step; a time policy does not by itself turn an infinite source into a business-meaningful Job without a clear termination rule.

## 10. CompletionPolicy and filter, skip, retry

`CompletionPolicy` decides when a chunk ends; filter, skip, and retry decide how each item or exception is handled. These are different mechanisms, but they all affect the actual size and duration of a chunk.

- **Filter:** the processor returns `null`; the item is not sent to the writer. Filtering does not mean the policy has completed.
- **Skip:** an exception is allowed to be skipped; the item is dropped under the fault-tolerance policy and recorded in the skip counters.
- **Retry:** the framework retries an operation that hit a transient error; the chunk's completion time may increase.
- **CompletionPolicy:** checks the chunk's end condition according to the configured rule.

For example, with `SimpleCompletionPolicy(100)`, some items may be filtered or skipped but the chunk is still controlled by the counting policy. The number of items the writer actually receives may be lower than the number the reader has read.

If a retry runs long, a time-based policy may reach its time threshold while the Step is processing. However, the policy does not cancel a retry operation that is running; retry has its own timeout/backoff and needs to be configured appropriately.

## 11. CompletionPolicy and transaction commit

When the policy reports that the chunk is complete, Spring Batch moves the chunk to the write phase and commits the transaction according to the Step's structure. Therefore, the policy indirectly affects:

- The number of items gathered in one transaction.
- The commit frequency.
- The time transactions and database locks are held.
- The amount of data that may have to be rolled back when a chunk fails.
- Throughput and the cost of communicating with the database.

A large chunk can reduce the number of commits and make better use of batch writes, but it can also increase memory, transaction time, and the amount of work to redo on failure. A small chunk commits more frequently but may increase overhead.

With a time-based policy, the chunk size changes with the processing speed. You need to measure transaction time and the actual number of items per chunk to know whether the policy meets the operational goals.

## 12. CompletionPolicy is not BatchStatus or ExitStatus

Some concepts have similar names but serve different purposes:

| Concept | Question answered |
|---|---|
| `CompletionPolicy` | When does a loop or the current chunk end? |
| `RepeatStatus` | Does the Tasklet or repeat callback need to keep being called? |
| `BatchStatus` | Is the JobExecution or StepExecution running, completed, failed, or stopped? |
| `ExitStatus` | Which result code is used to describe the outcome and control the flow? |
| `ExecutionContext` | What state needs to be saved to share or recover on restart? |

For example, a chunk ending and committing does not mean the Step has completed. The Step may continue to process more chunks. Only when the reader runs out of data can the Step end. After that, BatchStatus and ExitStatus reflect the Step's final result.

## 13. Which policy for which workload?

| Workload | Policy that usually fits | Reason |
|---|---|---|
| CSV import with rows of relatively uniform size | `SimpleCompletionPolicy` or `chunk(int)` | A fixed commit interval is predictable. |
| Database batch insert in groups of 500 items | `SimpleCompletionPolicy(500)` | Makes use of batch writes and controls the transaction. |
| Items arrive slowly, and you want to limit chunk collection time | `TimeoutTerminationPolicy` | The chunk ends at a time threshold. |
| You want to limit both item count and time | Composite policy or custom policy | Ends when the appropriate limiting condition is reached. |
| The termination rule depends on application-specific criteria | Custom `CompletionPolicy` | Expresses the specific termination logic. |
| Small Job, little data, and stable speed | `chunk(int)` | No need to add complexity. |

Before using a timeout or a custom policy, identify the specific goal. If the goal is to time out a database query or an HTTP request, you need to configure the timeout at the reader/service/driver; CompletionPolicy only controls the chunk boundary.

## 14. Measuring and tuning CompletionPolicy

You should not choose a policy threshold by gut feeling. Observe real running data:

- The number of items per chunk.
- The time from the start to the end of a chunk.
- Writer and commit time.
- Overall throughput.
- Heap usage and garbage collection pressure.
- The number of rollbacks, retries, and skips.
- Lock hold time and database load.

With a count-based fixed policy, you can start from a moderate chunk size and then measure throughput and transaction time. With a time-based policy, check the distribution of items per chunk and confirm that the commit time falls within the desired target.

If the writer is the bottleneck, increasing the chunk size may help batch writes but may also lengthen the transaction. If the processor is slow, a timeout policy cannot cut off an item that is being processed. Optimize the slow component itself, use a dedicated timeout for I/O, and tune the policy based on the metrics.

## 15. Testing CompletionPolicy

A policy should be tested independently to confirm that the termination condition behaves as expected.

With `SimpleCompletionPolicy`, check these cases:

- When the chunk does not yet have enough items, the policy is not complete.
- When the configured item count is reached, the policy reports completion.
- A new context starts a new counter.

With `TimeoutTerminationPolicy`, check that:

- The policy is not complete before the timeout.
- The policy is complete after the time threshold has elapsed.
- A long-running operation is not mistaken for having been cancelled midway.

With a custom policy, you need to check that:

- The context is initialized separately for each iteration.
- `update` changes the right state that needs to be tracked.
- The termination conditions have clear semantics.
- EOF and a terminating repeat result are handled correctly.
- Multiple concurrent StepExecutions do not unintentionally share mutable state.

A Step-level integration test can additionally check the number of times the writer is called, the number of items per chunk, commit/rollback, and the behavior when the source runs out of data.

## 16. Common mistakes

### Confusing CompletionPolicy with the Job termination condition

The policy only decides that the current loop/chunk ends. The Job may still have many chunks or subsequent Steps.

### Thinking a timeout policy will interrupt a running item

A timeout policy checks the completion condition at orchestration points. It does not interrupt a reader, processor, or writer call that is blocked. Configure a dedicated timeout for I/O.

### Using a time-based policy to replace a database timeout

If a SQL query hangs, a policy cannot replace a query timeout or socket timeout. You need to set the timeout at the driver, the JDBC statement, or the corresponding service.

### Assuming a chunk always contains exactly the configured number of items

The last chunk can be smaller because the reader runs out of data. Filters and skips also make the number of items the writer receives lower than the number read.

### Writing a custom policy that keeps state in a shared field

If a policy bean is shared among executions, mutable state can get mixed up between Jobs. Use `RepeatContext` to hold state per loop and control the policy's scope.

### Combining multiple conditions without specifying AND/OR

A combined policy can end when one condition is met or only when all conditions are met. Define the semantics clearly and test them, especially for maximum limits such as item count and time.

### Choosing a large chunk size without measuring transactions

A large chunk can increase lock hold time, memory, and rollback workload. Tune it based on throughput, transaction time, and database load.

## 17. Process for choosing and configuring a CompletionPolicy

When designing a chunk Step, you can follow this sequence:

1. Determine the commit unit that the business and the database can accept.
2. If a fixed item count is enough, use `.chunk(n, transactionManager)`.
3. If you want to express the counting policy explicitly, use `SimpleCompletionPolicy`.
4. If you need to end based on chunk collection time, consider `TimeoutTerminationPolicy`.
5. If you need multiple conditions, determine the OR/AND semantics and then choose a composite policy or implement a custom policy.
6. Keep the policy logic small, deterministic, and free of side effects.
7. Configure dedicated timeouts for the reader, processor, writer, or I/O if you need to limit operation time.
8. Measure the number of items per chunk, transaction time, throughput, and rollbacks to tune the threshold.
9. Test EOF, filter, skip, retry, and concurrent execution.

## Conclusion

`CompletionPolicy` determines when a loop or a chunk in Spring Batch is considered complete. `SimpleCompletionPolicy` suits a fixed commit interval based on item count; `TimeoutTerminationPolicy` ends a chunk based on a period of time; a custom or composite policy can express more complex conditions. The policy affects the chunk size, the commit frequency, the transaction time, and the amount of work that may have to be rolled back. Distinguish it from I/O timeouts, `RepeatStatus`, `BatchStatus`, and `ExitStatus`, and choose thresholds based on actual operational metrics.
