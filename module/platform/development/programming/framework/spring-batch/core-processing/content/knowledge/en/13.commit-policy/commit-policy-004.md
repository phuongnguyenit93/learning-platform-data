# Committing by time

In Spring Batch, a chunk-oriented step usually gathers multiple items into a chunk, then writes the results and commits the transaction. The most common configuration is to set a maximum number of items per chunk, for example `chunk(500, transactionManager)`. However, if the processing time per item varies a lot, a chunk of 500 items might take a few seconds in one run but a few minutes in another.

When you need to limit the processing time of a chunk, Spring Batch lets you use a `CompletionPolicy` in place of a fixed commit interval. `TimeoutTerminationPolicy` is the common policy for ending a chunk when the time has exceeded the configured threshold. When the policy reports that the chunk is complete, the framework passes the existing outputs to the writer, updates state/metadata, and commits the chunk's transaction.

Committing by time helps roughly control the duration of a transaction and reduces the risk of holding locks too long when the processing time per item is uneven. This is a chunk termination threshold, not a schedule that can interrupt an item that is being processed at exactly the right moment. The actual time from the start of a chunk to the commit can be longer than the threshold because the reader, processor, writer, or database may take extra time.

## Commit interval by count and by time

Spring Batch needs a rule to know when the current chunk ends. There are two common approaches:

| How the chunk is determined | Mechanism | When it fits |
| --- | --- | --- |
| By item count | `SimpleCompletionPolicy` or `chunk(int, transactionManager)` | Each item has a relatively stable processing time and you want to control the number of items per transaction |
| By time | `TimeoutTerminationPolicy` through `CompletionPolicy` | The processing time per item varies and you want to roughly limit the chunk duration |

Example by count:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(500, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .build();
```

With this configuration, a chunk usually ends after 500 input items have been processed or when the data source ends. If each item takes 10 ms, the reader/processor processing time can be approximately 5 seconds; if each item takes 500 ms, the same chunk size can last about 250 seconds, not counting the writer and commit.

Committing by time determines the chunk based on the time that has elapsed since the chunk started. This is useful when the time per item is unstable, but the number of items in each chunk will change with the load and the complexity of the data.

## CompletionPolicy and TimeoutTerminationPolicy

`CompletionPolicy` is Spring Batch's abstraction for determining when an iteration or a chunk should end. Instead of only counting items, a policy can rely on time or another condition.

`TimeoutTerminationPolicy` implements the time-based termination rule. Its constructor takes the timeout in milliseconds. For example, `30_000` corresponds to about 30 seconds.

With Spring Batch 5, you can pass the policy directly to `StepBuilder.chunk(...)`:

```java
@Bean
Step importOrdersByTimeStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    CompletionPolicy completionPolicy =
            new TimeoutTerminationPolicy(30_000);

    return new StepBuilder("importOrdersByTimeStep", jobRepository)
            .<OrderInput, Order>chunk(completionPolicy, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

In the example:

- `TimeoutTerminationPolicy(30_000)` sets a time threshold of about 30 seconds for a chunk.
- `chunk(completionPolicy, transactionManager)` tells the step to use this policy to determine when the chunk ends.
- The reader and processor keep processing items in the chunk until the policy completes or the reader reports that the data has run out.
- The writer writes the collected outputs; Spring Batch updates metadata and commits the transaction according to the chunk lifecycle.

Imports commonly used in Spring Batch 5:

```java
import org.springframework.batch.repeat.CompletionPolicy;
import org.springframework.batch.repeat.policy.TimeoutTerminationPolicy;
```

The builder API and packages need to be checked against your project's framework version. In older versions, creating a step may go through `StepBuilderFactory`; the idea is still to provide a `CompletionPolicy` for the chunk instead of only passing an item count.

## How does a chunk end by time?

A chunk transaction begins, and then Spring Batch reads and processes each item. The policy tracks the time of the iteration. When the timeout condition has been reached at a check point of the repeat operation, the chunk is considered complete and the framework moves on to the write phase.

```text
Start chunk and transaction
          |
          v
      Read item 1
          |
          v
      Process item 1
          |
          v
      Check policy
          |
          v
      Read / process next item
          |
          v
    Timeout reached yet?
        /          \
      Not yet       Yes
       |             |
       +--- loop     v
                ItemWriter
                    |
                    v
           Update state/metadata
                    |
                    v
                 COMMIT
```

The policy does not interrupt a `read()` or `process()` call that is already running. If a processor starts just before the 30-second threshold but takes another 20 seconds to complete, the chunk can only end after that operation returns and the framework checks the policy at the next point. The writer and the commit also need their own time.

Therefore, the timeout policy creates an approximate operational threshold for the chunk duration; it does not guarantee that every transaction is committed in exactly 30 seconds.

## Example with uneven processing time

Suppose a job processes customer records. Some records only need string normalization and take a few milliseconds; some records need a call to a lookup service and take a few hundred milliseconds.

If you use `chunk(500, transactionManager)`, the chunk always gathers a nearly fixed number of items. The transaction time can fluctuate widely:

| Situation | Average time per item | 500 items (estimated processing portion) |
| --- | ---: | ---: |
| Simple data | 5 ms | 2.5 seconds |
| Typical data | 40 ms | 20 seconds |
| Data needing lookup | 250 ms | 125 seconds |

If the goal is to keep a transaction at around 20–30 seconds under normal load, you can use `TimeoutTerminationPolicy(30_000)`. When items are processed quickly, a chunk can contain many items. When items are processed slowly, a chunk can contain fewer items.

The number of items in each chunk is therefore not fixed. This affects the number of writer calls, the number of commits, and throughput. You need to measure on near-real data to choose an appropriate timeout.

## Chunk timeout differs from transaction timeout

These are two different configurations and should not be confused.

**Chunk timeout** via `TimeoutTerminationPolicy` determines when the framework should stop gathering items into the chunk and move on to the writer/commit. It controls the chunk size by time.

**Transaction timeout** is the time limit of a transaction managed by the transaction manager. If the transaction exceeds this limit, database operations may fail or the transaction may be marked rollback-only, depending on the transaction manager and resource.

| Criterion | TimeoutTerminationPolicy | Transaction timeout |
| --- | --- | --- |
| Purpose | End the chunk by time | Limit how long a transaction is allowed to exist |
| Effect | Decides when to stop reading/processing items for the current chunk | Can make the transaction fail if the limit is exceeded |
| When it takes effect | Checked during repeat/chunk processing | Applied by the transaction manager/database |
| Does it interrupt a running processor? | No | Not necessarily; depends on the operation and resource |
| Configuration unit | Milliseconds in `TimeoutTerminationPolicy` | Usually seconds or the transaction manager's own configuration |

For example, the chunk timeout is set to 30 seconds but the transaction timeout is set to 20 seconds. If the reader/processor is still working after 20 seconds, the transaction manager may make the transaction fail before the chunk policy has a chance to end normally. Conversely, a transaction timeout of 5 minutes with a chunk timeout of 30 seconds usually lets the chunk end earlier, as long as the writer and commit complete within the transaction limit.

When setting the two thresholds, leave time for the writer, the metadata update, and the commit. Do not set the transaction timeout exactly equal to the chunk timeout if the writer may take a significant amount of extra time.

## Choosing a timeout for the chunk

There is no single optimal timeout value for every job. The right value depends on the item processing time, the writer time, the database load, lock contention, the connection pool, and restart requirements.

Factors to consider:

- **Reader/processor time:** if each item has high latency or an uneven distribution, a time-based chunk can avoid gathering too many items into one transaction.
- **Writer time:** the writer may take significant time to write a large batch; this must be counted in the transaction duration.
- **Lock tolerance:** a long chunk holds locks longer and can make other transactions wait.
- **Commit cost:** a timeout that is too short creates many chunks and many commits, increasing the load on the database and the metadata repository.
- **Restart capability:** smaller chunks usually reduce the amount of work to redo when a transaction rolls back, but increase the number of checkpoints.
- **Throughput:** a large chunk can increase batch write efficiency; a small chunk can reduce lock duration but increase overhead.

One way to start is to measure the processing and write time of some representative chunks, then choose a timeout lower than the threshold at which the database can hold transactions stably. Keep observing the p95/p99 chunk duration instead of only looking at the average time.

## Combining time and item count limits

Some jobs need both limits:

- Don't let a chunk run too long when items are processed slowly.
- Don't let a chunk contain too many items when items are processed very quickly.

In this case, you can combine `CompletionPolicy` instances or implement a custom policy based on both time and count. Spring Batch has policy composition in the repeat package; the specific way to combine them needs to be checked against the API of the version you are using and the completion rules of the composite policy.

In terms of design, the desired condition is usually to end the chunk when **either threshold** is reached first: the maximum item count or the maximum time. For example, a maximum limit of 1,000 items or about 30 seconds, whichever comes first.

Do not assume that passing both `chunk(1000, transactionManager)` and a `TimeoutTerminationPolicy` in two different places will combine automatically. The Step needs one clearly configured `CompletionPolicy` to represent the combined logic.

## Custom CompletionPolicy

If the commit rule is more complex than a plain timeout, you can implement a custom `CompletionPolicy`. For example, a policy can end a chunk when the maximum time is reached, the maximum item count is reached, or another business condition is met.

A custom policy needs to manage each chunk's state through `RepeatContext`, determine the start of an iteration, update state after each processing step, and answer whether the policy has completed. Do not store a chunk's counter or timestamp in a field shared among multiple executions if the policy object may be shared; state should be tied to the execution's repeat context.

Before writing your own policy, consider using a built-in policy. A custom policy needs to be tested with cases of fast items, slow items, the reader running out of data, exceptions, retry, and restart. In particular, you need to define clearly whether the termination condition is OR or AND when combining multiple thresholds.

## Impact on transactions and restart

When a chunk ends by time, Spring Batch still uses the transaction semantics of chunk-oriented processing. The writer and checkpoint updates are coordinated within the chunk's transaction according to the step configuration.

If the chunk commits successfully, business data and checkpoint metadata participating in the same transactional resource can be saved together. If the chunk rolls back, the changes participating in the transaction are rolled back and the chunk's items may be read/processed again on restart.

A timeout policy does not make data get committed automatically while a processor is running. If an item takes 90 seconds and the chunk timeout is 30 seconds, that item still needs to complete or throw an error before the framework can end the chunk according to the policy. If an item takes too long, handle the timeout at the reader/processor operation itself, the HTTP client, or the database query, instead of only reducing the chunk timeout.

On restart, the reader/writer's `ExecutionContext` is still the mechanism for saving state. Whether a chunk ends by time or by item count does not change the principle of identifying parameters: restarting the same logical job needs to reuse the same identifying parameters.

## Impact on performance

Committing by time can improve the predictability of transaction duration, but it does not always increase throughput.

### Timeout too short

If you set a very small timeout, each chunk contains only a few items. The consequences may include:

- More writer calls and more batch SQL executions.
- More transaction begin/commit/rollback operations.
- More metadata and execution context updates.
- More read/write overhead and contention on the `JobRepository`.
- Reduced efficiency of batch inserts or batch messages.

### Timeout too long

If the timeout is too large, a chunk can hold a transaction for a long time:

- Database locks exist for a long time and increase the wait time of other transactions.
- An error at the end of a chunk can force many items to be reprocessed.
- The connection pool is occupied for longer.
- The writer receives a large amount of output, increasing memory and write time.
- A system shutdown or timeout may occur while the transaction is still open.

### Measurement

You should monitor at least:

- Average chunk duration and high percentiles such as p95/p99.
- The number of items read, processed, filtered, skipped, and written per chunk.
- Reader, processor, and writer time.
- The number of commits, rollbacks, and retries.
- Lock wait, deadlocks, connection pool usage, and database latency.
- Throughput in items/second and the completion time of the whole job.

Choose the timeout based on measured data and business requirements. A single fixed number cannot be optimal for every type of data and every load level.

## A timeout policy is not a scheduler or a job timeout

Committing by time is often confused with other timeout mechanisms:

| Mechanism | What does it control? |
| --- | --- |
| `TimeoutTerminationPolicy` | The time spent gathering items for one chunk |
| Transaction timeout | The maximum duration of a transaction |
| HTTP/client timeout | The wait time for a request to an external system |
| Application-managed job execution timeout | The overall run time of the job according to application policy |
| Scheduler interval/cron | The time at which the job starts |

For example, a scheduler that runs the job every hour does not mean a chunk commits every hour. Conversely, a chunk timeout of 30 seconds does not mean the job stops by itself after 30 seconds; the job can run many consecutive chunks for several hours.

If the processor calls HTTP, configure the connect/read/request timeouts for the HTTP client. If a database query could hang, configure an appropriate query timeout. `TimeoutTerminationPolicy` only decides that the chunk should end at the next check point; it does not replace the timeout on each I/O operation.

## When the reader or processor is blocked for a long time

An important limitation: a time-based completion policy cannot safely interrupt a running Java call. If `ItemReader.read()` is waiting on an API for 2 minutes, or `ItemProcessor.process()` is waiting on a lock, the policy cannot cut in by itself to commit the chunk at the 30th second.

To control operations that may be blocked, configure the timeout at the right layer:

- JDBC query timeout or the database statement timeout.
- HTTP connect timeout, response/read timeout, and overall request timeout.
- The timeout when receiving messages from a broker.
- The timeout for a lock or semaphore in the application.
- Cancellation and interrupt handling if the API in use supports it safely.

Do not use `Thread.interrupt()` carelessly to cut off an item that is updating data. Interrupting mid-operation can leave side effects outside the transaction or an unclear state.

## Common mistakes when using commit by time

### Thinking the commit happens exactly every 30 seconds

The policy is checked in the repeat/chunk loop. A running item is not interrupted at the threshold; the writer and the commit also need time. Treat the timeout as an approximate termination threshold, not an exact commit schedule.

### Confusing chunk timeout with transaction timeout

A policy that ends a chunk does not mean the transaction manager allows the transaction to last indefinitely. Configure the two thresholds in coordination and leave time for the writer/commit.

### Choosing a timeout that is too short

Many small chunks increase overhead and reduce the benefit of batch writes. Measure the processing time and commit cost before lowering the timeout.

### Choosing a timeout that is too long

A long transaction can hold locks and connections for a long time and widen the rollback scope. Choose the threshold based on the database's capability and restart requirements.

### Expecting the policy to interrupt a running processor

The policy does not preempt a reader/processor call. Configure timeouts for I/O or split long processing operations into smaller ones.

### Believing the timeout policy limits the total job time

The timeout only controls one chunk. The job can still run many consecutive chunks until the reader runs out of data or the flow ends.

### Using the current time as an identifying parameter to avoid duplicate runs

A new identifying timestamp can create a new `JobInstance` and lose the restart link to the old instance. Use stable business parameters; the commit policy does not determine job identity.

## Testing a time-based commit policy

You should test the policy's behavior with simulated time or processors with controlled latency in the test environment. Avoid writing tests that depend too tightly on real wall-clock time, because the machines running the tests have different loads.

Cases to check:

- Many fast items are gathered into the same chunk until the timeout is reached.
- A slow item makes the chunk exceed the threshold before the policy can end it.
- The reader runs out of data before the timeout; the final chunk is still completed correctly.
- The writer fails after the policy ends; the transaction rolls back as configured.
- The earlier chunk commits successfully and the later chunk fails; restart begins from the committed checkpoint.
- The transaction timeout is smaller than the required time; the step handles the error as configured.
- A policy combining time and item count ends when the first desired condition is reached.

To verify the policy, you should record the chunk start time, the time the writer is called, and the time the transaction completes. Compare these figures to understand how much time goes to the reader/processor, the writer, and the commit.

## When should you use commit by time?

Commit by time fits when item processing time varies strongly and you want to roughly limit the duration of a transaction. Some situations:

- The processor calls a lookup service whose latency is unstable.
- Items differ significantly in size or complexity.
- The writer needs to avoid receiving too large a batch when the load increases.
- The database has operational requirements on how long transactions or locks may be held.
- You want to balance the number of commits against the rollback scope in uneven workloads.

Commit by count usually fits when item processing time is stable, the writer is optimized for a batch size, and you want to limit the exact number of items per chunk. If both time and item count have important limits, configure one clearly combined `CompletionPolicy`.

Do not choose a time-based policy just because its name sounds more flexible. Identify the problem you need to solve: transactions that are too long, chunk output that is too large, uneven item latency, or commit cost that is too high. Then measure and choose the corresponding policy.

## Key takeaways

Spring Batch supports commit by time through `CompletionPolicy`, most commonly `TimeoutTerminationPolicy`. The policy ends the gathering of items for a chunk when the time has exceeded the threshold, after which the framework calls the writer, updates state/metadata, and commits the transaction. This threshold is checked at points in the repeat loop, so it does not interrupt a running reader or processor and does not guarantee a commit at exactly every millisecond. Chunk timeout differs from transaction timeout, job timeout, and scheduler interval. Leave time for the writer/commit, configure timeouts on each I/O operation, measure chunk duration, and choose a threshold that fits locks, the connection pool, throughput, and restart requirements.
