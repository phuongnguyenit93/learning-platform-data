# Choosing a policy based on latency, throughput, and reliability

In Spring Batch, the commit policy decides when a group of items is finished and the chunk's transaction is committed. With a chunk-oriented Step, the choice usually starts with the commit interval: how many items each chunk processes before writing and committing. This value directly affects the response time of each data batch, throughput, lock hold time, transaction cost, and the amount of work that may have to be redone on error.

There is no single optimal commit interval for every Job. Jobs that need data to appear quickly for downstream systems usually favor small chunks; Jobs processing large volumes within a batch window may favor larger chunks to reduce overhead. Jobs requiring high restartability and reliability must balance both factors, while designing readers/writers with checkpoints and safe re-execution capability.

## 1. Commit policy in chunk processing

In chunk-oriented processing, Spring Batch reads and processes items until the chunk reaches its termination condition, then calls the Writer and commits the transaction. With a fixed commit interval, the number of items in a chunk is determined by configuring `chunk(size, transactionManager)`.

```text
Chunk 1: BEGIN -> read/process 500 items -> write -> COMMIT
Chunk 2: BEGIN -> read/process 500 items -> write -> COMMIT
Chunk 3: BEGIN -> read/process 500 items -> write -> COMMIT
```

For example, `chunk(500, transactionManager)` usually means a chunk holds up to 500 items read and processed before writing. The last chunk can have fewer if the data source has run out. If the chunk's transaction fails, changes belonging to that transaction may roll back; previously committed chunks remain preserved.

A commit policy is not a Job schedule. It does not decide when the Job starts, nor does it decide whether the Job runs synchronously or asynchronously. The policy defines the boundaries between commit units inside a Step.

## 2. Three factors to balance

### Latency

Latency in batch processing can be viewed at multiple levels:

- Time from when the Job starts until the first result is committed.
- Time a chunk stays in processing state before data is committed.
- Delay from when source data appears until results can be read by another system.

Small chunks usually help data get committed in smaller batches and earlier. This is useful when downstream needs to see partial results or when the Job must share the database with online transactions. Large chunks can increase the wait time before a chunk's data is committed.

### Throughput

Throughput is the amount of work completed per unit of time, such as records/second. Large chunks can increase throughput by reducing the number of commits, round trips, and transaction management overhead. However, chunks that are too large can also reduce throughput because transactions hold locks long, increase memory, put pressure on the database, and make other Jobs wait.

Therefore, throughput does not necessarily scale linearly with the commit interval. You need to measure on real workloads and real database systems.

### Reliability

Reliability reflects the ability to keep data consistent, detect errors, recover, and continue processing without losing or duplicating data.

- Small chunks limit the amount of uncommitted data and usually reduce the rollback scope.
- Large chunks can cause an error to force retrying more items and hold transactions longer.
- Frequent commits create denser checkpoints, but are only helpful when the reader saves state and the writer is designed to be safe on restart.
- With retry, items in a chunk may be processed again; processors and writers need to tolerate retries.

## 3. Small chunks and large chunks: trade-offs

| Criterion | Small chunk | Large chunk |
|---|---|---|
| Commit timing | Commits more frequently | Waits for more items before committing |
| Transaction duration | Usually shorter | Usually longer |
| Commit overhead | More commits, higher overhead | Fewer commits, lower overhead |
| Memory | Usually holds fewer items | Holds more items in the chunk |
| Locks and contention | Usually reduces lock hold time | Can hold locks longer |
| Rollback scope | Fewer items in a chunk | More items may have to be reprocessed |
| Checkpoints | More commit points | Fewer commit points |
| Throughput | Can be low if overhead accounts for a large share | Can be higher up to an appropriate threshold |
| Partial data latency | Usually lower | Usually higher |

You should not conclude that small chunks are always more reliable or that large chunks are always faster. A writer writing each item with multiple SQL statements may benefit from batch inserts and larger chunks. A Job updating tables used by online transactions may need small chunks to reduce lock contention.

## 4. Choosing commit interval by workload characteristics

Some common situations:

| Job characteristics | Initial choice direction | Reason |
|---|---|---|
| Data needs to appear quickly for downstream | Small or medium chunk | Commits results in short batches, reducing observation latency. |
| Large volume import, writer supports batch insert | Medium or large chunk | Reduces round trips and commits. |
| Database shared with online applications | Small or medium chunk | Reduces lock hold time and impact on requests. |
| Heavy item processing, uneven time per item | Medium chunk or time-limited policy | Avoids transactions dragging on just because of an overly large group of items. |
| Requires fast restart after errors | Small or medium chunk, reader with checkpoint | Limits rework scope after rollback. |
| Items have side effects outside the database | Chunk by business batch, with idempotency/outbox | Controls duplicate sends or writes on retry. |

Specific values must be benchmarked. You can start with a moderate value, such as 100 or 500 items, then compare against smaller and larger levels. This is just a starting point for experimentation, not a universal rule for every database or item type.

## 5. Configuring a fixed commit interval

With Spring Batch 5 and later, configure the commit interval directly in `StepBuilder`:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class ImportJobConfig {

    @Bean
    public Step importStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<InputRecord> reader,
            ItemProcessor<InputRecord, OutputRecord> processor,
            ItemWriter<OutputRecord> writer) {

        return new StepBuilder("importStep", jobRepository)
                .<InputRecord, OutputRecord>chunk(500, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .build();
    }
}
```

Here, 500 is the commit interval. Each successful chunk will be committed separately. To test another policy, you can replace 500 with 100 or 1,000 and measure throughput, chunk duration, lock wait, and rollback rate on the same data set.

## 6. Using CompletionPolicy when counting items alone is not enough

A fixed commit interval is based on item count. In some Jobs, the processing time per item varies significantly. For example, one item may process in a few milliseconds, while another needs multiple calculation steps or additional data access. In that case, 500 items can create very short chunks in one part of the data while creating long-running transactions in another.

Spring Batch supports `CompletionPolicy` to determine when a chunk ends. `SimpleCompletionPolicy` is an item-count policy:

```java
import org.springframework.batch.repeat.CompletionPolicy;
import org.springframework.batch.repeat.policy.SimpleCompletionPolicy;

CompletionPolicy completionPolicy = new SimpleCompletionPolicy(500);

return new StepBuilder("importStep", jobRepository)
        .<InputRecord, OutputRecord>chunk(completionPolicy, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
```

For workloads with uneven processing time, you can use a time-based policy or a composite policy to end chunks at an appropriate limit. For example, `TimeoutTerminationPolicy` can limit the iteration time of a chunk:

```java
import org.springframework.batch.repeat.CompletionPolicy;
import org.springframework.batch.repeat.policy.TimeoutTerminationPolicy;

CompletionPolicy completionPolicy = new TimeoutTerminationPolicy(5_000);

return new StepBuilder("importStep", jobRepository)
        .<InputRecord, OutputRecord>chunk(completionPolicy, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
```

The value `5_000` is 5 seconds. When using a time-based policy, understand that it decides when to end the loop; it does not necessarily forcibly interrupt a hung `read()`, `process()`, or `write()` call. If items process very quickly, limiting only time can gather many items into one chunk; you can combine count and time conditions to bound both dimensions.

A time-based policy also does not replace transaction timeout. A policy that ends a chunk after a duration and a transaction timeout are two different mechanisms: one decides when the chunk stops accepting more items, the other sets a time limit for the transaction. Design and test both if the Job has strict timing requirements.

## 7. Transaction timeout and isolation level

The commit interval determines the number of items in a chunk; transaction attributes determine transaction properties such as timeout and isolation level.

Example configuring timeout and isolation for a chunk Step:

```java
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.interceptor.DefaultTransactionAttribute;

DefaultTransactionAttribute transactionAttribute =
        new DefaultTransactionAttribute();
transactionAttribute.setTimeout(60);
transactionAttribute.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED);

return new StepBuilder("importStep", jobRepository)
        .<InputRecord, OutputRecord>chunk(500, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .transactionAttribute(transactionAttribute)
        .build();
```

The example sets a 60-second timeout and `READ_COMMITTED` isolation; values need to be adjusted according to the database, transaction manager, and actual SLA. You can declare the variable as `DefaultTransactionAttribute` from the start to avoid casting:

```java
DefaultTransactionAttribute transactionAttribute =
        new DefaultTransactionAttribute();
transactionAttribute.setTimeout(60);
transactionAttribute.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED);
```

A few notes:

- Timeout is not a target completion time for the chunk. It is a transaction limit; how timeout is enforced depends on the transaction manager and resources.
- Transaction timeout does not guarantee cancelling a running HTTP call or CPU processing segment.
- Higher isolation levels can increase isolation but also increase locks or database cost. Only use stricter levels when business rules require them.
- Do not increase timeout to mask chunks that are too large or a transaction waiting too long on an external service.

## 8. Combining commit policy with retry and skip

Commit policy affects how recovery works when an item encounters an error. With a fault-tolerant Step, Spring Batch can roll back the chunk and then retry the operation or skip the item according to configuration.

```java
return new StepBuilder("importStep", jobRepository)
        .<InputRecord, OutputRecord>chunk(300, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidRecordException.class)
        .skipLimit(20)
        .build();
```

In the example, transient data access errors can be retried up to the configured limit; invalid business records can be skipped within the allowed limit. If retries are exhausted or an unhandled error occurs, the Step may fail.

When choosing chunk size, account for how many times items might be retried and the cost of redoing a chunk. Overly large chunks can cause a transient error to trigger a lot of repeated work. Overly small chunks increase overhead on retries and commits. Processors should minimize side effects, while writers need to be idempotent or have duplicate-prevention mechanisms where appropriate.

Filtering and skipping also must be distinguished: a processor returning `null` increments `filterCount`; an exception configured for skip increments the corresponding skip counter. Do not raise the skip limit just so the Job always completes if bad data needs investigation.

## 9. Reliability and restartability

Every successful commit is a durable data milestone. If the Job fails in the next chunk, already committed chunks remain. On restarting the same JobInstance, Spring Batch can use `ExecutionContext` to restore reader state and continue from the appropriate checkpoint.

```text
JobExecution #1: FAILED
  Chunk 1: COMMITTED
  Chunk 2: COMMITTED
  Chunk 3: ROLLED BACK
  Chunk 4: not run yet

Restart with same identifying JobParameters
  |
  v
JobExecution #2
  Restore from saved checkpoint
  Continue remaining work
```

For the commit policy to support genuine reliability:

1. The reader must support saving state if you want to continue from a checkpoint.
2. The writer must tolerate items being reprocessed on retry or restart.
3. Identifying JobParameters must stably represent the unit of work.
4. Side effects outside the transaction must have idempotency keys, an outbox, or compensation mechanisms.
5. Do not place a transaction spanning the entire Job such that chunks appear committed while not actually committed independently.

Smaller chunks can limit the number of items needing rework, but if the reader does not save state or the writer is unsafe on re-execution, frequent commits do not by themselves guarantee accurate restart.

## 10. Example of choosing policy for three Job types

### Large file import job in a nightly window

The main goal is throughput. The file has millions of lines, the writer batch-writes to the database, and there are few competing online transactions. You can start testing with chunk 500 or 1,000, then measure write time, commit latency, memory, and locks. If larger chunks continue improving throughput without significantly increasing errors or rollback time, you can keep a larger value.

### Near-real-time data sync job

The goal is low latency. Downstream needs to see results soon after items are processed. Chunk 10, 25, or 50 can be a starting test point, depending on commit cost and data volume. Prioritize time from read to commit and avoid transactions holding locks long.

### Job updating tables shared with an online system

The goal is reliability and minimizing impact on online transactions. Medium or small chunks help reduce lock hold time and limit rollback scope. Monitor lock wait, deadlocks, transaction duration, and connection pool. If the online system is impacted, you can reduce chunk size, limit concurrency, or run the batch outside peak hours.

| Job type | Priority | Initial configuration direction for benchmarking |
|---|---|---|
| Large import, low contention | Throughput | Chunk 500–1,000, batch-enabled writer |
| Sync needing early results | Latency | Chunk 10–50 |
| Updating shared database | Reliability and isolation | Chunk 50–200, monitor locks and rollbacks |

The ranges above are only starting examples. Item size, database type, indexes, SQL statements, network, processor, and concurrency can make actual results vary significantly.

## 11. Measuring to fine-tune commit policy

Do not choose chunk size based only on intuition or a single run. Use the same input data, the same environment configuration, and compare several values.

Useful metrics:

| Metric | Meaning | Used to decide |
|---|---|---|
| Throughput (items/second) | Items completed in one second | Do larger chunks actually improve performance? |
| Chunk duration p50/p95 | Typical chunk processing time and slow tail | Are chunks too long or highly variable? |
| Commit latency | Transaction commit time | Is the database experiencing overhead or slow writes? |
| Rollback/retry count | Number of rollbacks and retries | Do large chunks increase recovery cost? |
| Lock wait/deadlock | Database contention level | Does the batch affect other transactions? |
| Connection pool usage | Active and waiting connections | Are transactions holding connections too long? |
| Heap/GC | Memory and garbage collection cost | Are chunks holding too many items in memory? |
| End-to-end lag | Delay from source to committed result | Are latency requirements met? |

A practical benchmarking process:

1. Choose a representative data set, including both normal items and items with long processing times.
2. Run with a small chunk, for example 100, recording throughput, latency, locks, and memory.
3. Run with medium and large chunks, for example 500 and 1,000, under the same conditions.
4. Run once with controlled errors to observe rollback and restart time.
5. Compare results against the Job's SLA and impact on the shared database.
6. Choose a configuration meeting latency and reliability requirements, and only then optimize throughput within those limits.

## 12. Common mistakes when choosing commit policy

| Mistake | Consequence | How to handle |
|---|---|---|
| Choosing the largest possible chunk size | Long transactions, high memory, locks, and large rollback scope. | Benchmark by workload; increase gradually until gains become negligible. |
| Choosing overly small chunks | High commit overhead and low throughput. | Measure commit latency and try increasing interval if database has spare capacity. |
| Measuring only total Job time | Misses slow chunks, lock wait, or rising rollbacks. | Collect chunk duration, commit latency, and database metrics. |
| Confusing transaction timeout with chunk completion policy | Timeout does not necessarily end the chunk as desired. | Distinguish chunk termination condition from transaction limit. |
| Retrying when the writer is not idempotent | Data may be written twice after rollback/retry. | Use business keys, controlled upserts, or duplicate-prevention mechanisms. |
| Raising skip limit to avoid FAILED | Bad data may be ignored without investigation. | Specify which exceptions are skippable and record faulty records. |
| Keeping a transaction open while calling HTTP | Connections and locks are held during network wait; external requests do not roll back with DB. | Use an outbox or separate sending tasks into a dedicated Step. |

## Conclusion

Choosing a commit policy is a problem of balancing latency, throughput, and reliability. Small chunks usually commit early, keep transactions short, and limit rollback scope; large chunks reduce commit overhead but can hold locks long, consume memory, and increase rework volume. Start with a reasonable commit interval, measure throughput, chunk duration, commit latency, lock wait, memory, and restart behavior on real data. Combining the commit interval with appropriate transaction timeouts, retry/skip, and checkpoints will help the Step meet SLAs while keeping data consistent.
