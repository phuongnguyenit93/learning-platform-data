# Do not open a transaction spanning the entire job

In Spring Batch, a Job can consist of multiple Steps and each Step can process a large volume of data. You should not open a single transaction spanning the entire Job and hold that transaction until all Steps finish. Doing so holds connections and locks for too long, increases rollback costs, causes resource contention, and allows an error at the end of the workflow to affect all work already executed earlier.

Spring Batch is designed to manage transactions at a scope suited to the unit of processing. With a chunk-oriented Step, transactions are typically opened and committed per chunk. With a Tasklet Step, transactions are managed per invocation of `Tasklet.execute()`. The Job coordinates the Steps; the fact that a Job has multiple Steps does not mean the entire Job needs to sit inside a single shared transaction.

## 1. Transaction boundaries in Spring Batch

A transaction defines the group of data operations that must commit or roll back together. The longer a transaction stays open, the longer resources are held and the larger the blast radius on rollback.

In Spring Batch, place transaction boundaries around units of work that can commit independently:

```text
Job: importOrdersJob
  |
  +--> validateInputStep
  |       Transaction of Tasklet / per execute invocation
  |
  +--> importOrdersStep
  |       Chunk 1: BEGIN --> READ/PROCESS/WRITE --> COMMIT
  |       Chunk 2: BEGIN --> READ/PROCESS/WRITE --> COMMIT
  |       Chunk 3: BEGIN --> READ/PROCESS/WRITE --> COMMIT
  |
  +--> archiveFileStep
          Transaction of Tasklet / per execute invocation
```

Transactions of Steps or chunks can complete independently. If chunk 3 fails, chunks committed earlier preserve their results. The Job can be restarted based on saved metadata and checkpoints instead of having to roll back every change across the entire Job.

### Chunk transaction

With chunk-oriented processing, Spring Batch groups items according to the commit interval. Each chunk executes inside a transaction managed by the Step's transaction manager. For example, `chunk(500, transactionManager)` creates transactions in batches of up to 500 items.

```text
Chunk 1: BEGIN -> read/process/write 500 items -> COMMIT
Chunk 2: BEGIN -> read/process/write 500 items -> COMMIT
Chunk 3: BEGIN -> read/process/write 500 items -> ROLLBACK
```

When chunk 3 rolls back, changes in chunk 3's transaction are undone. Data from already committed chunks 1 and 2 is not rolled back with it. This is one reason chunk processing fits large-scale data processing.

### Tasklet transaction

With a Tasklet Step, `TaskletStep` uses the transaction manager declared for the Step to manage each call to `execute()`. A Tasklet typically returns `RepeatStatus.FINISHED` after one operation. If it returns `CONTINUABLE`, the Tasklet may be invoked again; each call is managed under TaskletStep's transaction boundary.

A Tasklet running a large stored procedure may still hold a transaction for a long time while the procedure runs. If the operation must be atomic at the level of the entire procedure, that transaction duration may be a business requirement. Still, you should not extend that transaction across all other Steps in the Job.

## 2. Why should you not open a transaction across the entire Job?

A Job may run for minutes, hours, or longer. If a transaction is opened before launching the Job and only ends after the Job completes, database resources can be held for that entire span.

Common risks:

1. **Holding connections too long:** a connection stays occupied for the duration of the Job, reducing connections available to other requests and batches.
2. **Holding locks too long:** a transaction may hold row locks, table locks, or other lock types, forcing concurrent processes to wait or deadlock.
3. **Increased rollback cost:** if an error happens in the final Step, the database may have to undo a massive amount of uncommitted changes.
4. **Increased logs and undo space:** the database must retain information required for rollback and isolation over a long period.
5. **Higher risk of timeout:** the transaction may exceed database, transaction manager, or connection pool timeout limits.
6. **Reduced recoverability:** uncommitted intermediate results are not durable; process termination can wipe out all changes in the long transaction.
7. **Increased contention between Jobs:** one batch holding locks long can block other batches or online transactions.

For example, a Job imports one million records with a commit interval of 500. If a transaction spans the whole Job, 2,000 logical chunks might still sit inside one huge transaction. On an error in the last chunk, the database may have to roll back nearly the entire workload. When transactions are split per chunk, each committed chunk is a durable unit of result.

## 3. Avoid putting @Transactional around JobLauncher calls

A common design mistake is annotating the Job-launching method with `@Transactional`:

```java
@Service
public class BatchLaunchService {

    private final JobLauncher jobLauncher;
    private final Job importOrdersJob;

    public BatchLaunchService(
            JobLauncher jobLauncher,
            Job importOrdersJob) {
        this.jobLauncher = jobLauncher;
        this.importOrdersJob = importOrdersJob;
    }

    @Transactional
    public void launch(JobParameters parameters) throws Exception {
        jobLauncher.run(importOrdersJob, parameters);
    }
}
```

If JobLauncher runs synchronously on the same thread, the transaction opened on the outer method may still be active when Steps begin. When a Step uses the same transaction manager and default `REQUIRED` propagation, the Step's transaction can join the outer transaction instead of creating independent boundaries per chunk. As a result, chunks that appear committed may not actually commit until the launch method ends.

Exact behavior depends on the JobLauncher type (synchronous or asynchronous), transaction manager, propagation, and repository/Step configuration. Do not rely on the assumption that calling `JobLauncher.run()` always detaches itself from an existing transaction.

### A better way to write it

Ordinarily, a method solely responsible for launching a Job does not need `@Transactional`. Let each Step manage transactions per its configuration:

```java
@Service
public class BatchLaunchService {

    private final JobLauncher jobLauncher;
    private final Job importOrdersJob;

    public BatchLaunchService(
            JobLauncher jobLauncher,
            Job importOrdersJob) {
        this.jobLauncher = jobLauncher;
        this.importOrdersJob = importOrdersJob;
    }

    public JobExecution launch(JobParameters parameters) throws Exception {
        return jobLauncher.run(importOrdersJob, parameters);
    }
}
```

This method does not open a transaction spanning the Job's runtime. Steps use their own transaction manager according to the Step configuration.

## 4. Configuring per-chunk transactions

In Spring Batch 5 and later, pass `PlatformTransactionManager` to `StepBuilder` when declaring a chunk Step:

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
public class ImportOrdersJobConfig {

    @Bean
    public Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<Order> orderReader,
            ItemProcessor<Order, Order> orderProcessor,
            ItemWriter<Order> orderWriter) {

        return new StepBuilder("importOrdersStep", jobRepository)
                .<Order, Order>chunk(500, transactionManager)
                .reader(orderReader)
                .processor(orderProcessor)
                .writer(orderWriter)
                .build();
    }

    @Bean
    public Job importOrdersJob(
            JobRepository jobRepository,
            Step importOrdersStep) {
        return new JobBuilder("importOrdersJob", jobRepository)
                .start(importOrdersStep)
                .build();
    }
}
```

`chunk(500, transactionManager)` specifies the transaction manager and commit interval for the Step. Spring Batch commits after each successful chunk. If a chunk hits an exception requiring rollback, that chunk's transaction is rolled back per policy.

Commit interval should be chosen based on item size, processing duration, database capacity, and restart requirements. Smaller intervals yield shorter transactions and narrower rollback scope, but increase commit count. Larger intervals reduce commits, but hold transactions longer and increase the items needing reprocessing on error.

## 5. Configuring transactions for a Tasklet Step

A Tasklet Step also needs a transaction manager:

```java
@Bean
public Step archiveStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet archiveTasklet) {

    return new StepBuilder("archiveStep", jobRepository)
            .tasklet(archiveTasklet, transactionManager)
            .build();
}
```

Tasklet Step manages the transaction for each Tasklet invocation. If a Tasklet executes a short database statement, the transaction can be brief and easy to control. If the Tasklet runs a long loop reading and updating hundreds of thousands of records in one `execute()` call, that invocation's transaction can still drag on.

When many records must be processed, consider switching to a chunk-oriented Step or splitting work into smaller Steps/tasklets with clear commit boundaries. If a stored procedure must run atomically as a single operation, evaluate the runtime and locks of the procedure itself rather than wrapping the entire Job inside that transaction.

## 6. Transaction propagation in services called from a Step

A processor, writer, or Tasklet may call a business service annotated with `@Transactional`. Understand propagation so you do not accidentally break the Step's transaction boundary.

### REQUIRED

`Propagation.REQUIRED` is the default. If a chunk or Tasklet transaction already exists, the service call usually joins the existing transaction. This is normally suitable when the service performs a short database operation belonging to the chunk's unit of work.

```java
@Service
public class OrderUpdateService {

    @Transactional
    public void updateOrder(Order order) {
        // Short database operation, joining the chunk's transaction if present.
    }
}
```

### REQUIRES_NEW

`Propagation.REQUIRES_NEW` suspends the current transaction and opens an independent transaction. Data committed in the new transaction may persist even if the outer chunk rolls back.

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAuditRecord(AuditRecord record) {
    // Commits independently from the calling chunk's transaction.
}
```

Only use `REQUIRES_NEW` when that independence is genuinely required, such as saving an audit record that must survive even if business processing fails. Using it for every record in a writer without clear reason can produce partially committed data and complicate restarts.

### NOT_SUPPORTED

`Propagation.NOT_SUPPORTED` suspends the current transaction while the method runs. This can be useful for operations that should not run inside a transaction, but it also means changes made by that operation are not protected by the chunk's transaction. Avoid applying it indiscriminately to processors or writers.

Do not use propagation as a quick fix for the whole Job. Clearly identify which operations must be atomic with the chunk, which can commit independently, and the impact on retry/restartability.

## 7. JobRepository does not require a Job-wide transaction

`JobRepository` stores metadata for JobInstance, JobExecution, StepExecution, and ExecutionContext. Metadata operations must be transactionally managed so execution state is not half-written or left inconsistent.

That does not mean the entire Job must sit in one transaction. Job and Step metadata are updated at appropriate points in the execution lifecycle; chunk business data is managed by the Step's transaction manager.

Distinguish between:

| Component | Purpose |
|---|---|
| JobRepository transaction | Consistently stores execution metadata and batch state. |
| Chunk transaction | Commits or rolls back business changes within a single chunk. |
| Tasklet transaction | Manages database operations within one Tasklet invocation. |
| External business transaction | Manages pre/post-launch updates per the application's own requirements. |

In typical configurations, the repository and business data may share a database while still having distinct transaction boundaries. Do not open one giant transaction manually just to wrap both metadata and all business data.

## 8. Synchronous and asynchronous launching

`JobLauncher` can be configured to run Jobs synchronously or asynchronously. This affects when the Job-calling method returns, not a reason to keep a long transaction open.

- **Synchronous launcher:** the launch method waits for the Job to finish executing. If the calling method is annotated with `@Transactional`, the outer transaction may stay open for the entire wait and may affect Step transactions if they share the same transaction manager.
- **Asynchronous launcher:** the launch method can return as soon as the Job is submitted to an executor. The caller's outer transaction usually ends after submitting the request; it does not automatically span work running on another thread.

Do not rely on an asynchronous launcher to substitute for proper transaction design. Ensure input data and request state have committed before workers begin reading them.

### Case: launching after a business transaction commits

Suppose an API creates a file import request in the database and then wants to launch a Job. If you launch the Job before the transaction creating the request commits, an asynchronous worker may start reading data before the record is visible.

One solution is to emit the launch signal after the transaction commits, or write an event into a transactional outbox within the same transaction as the request. A separate worker reads the outbox after commit and launches the Job. This decouples the short request transaction from batch processing transactions.

```text
API request
    |
    v
Short transaction
  - save BatchRequest
  - save OutboxEvent
    |
    v
COMMIT
    |
    v
Outbox dispatcher
    |
    v
JobLauncher
    |
    v
Job / Step transactions
```

The outbox dispatcher needs deduplication against duplicate dispatch, and the Job still needs stable identifying JobParameters. This is a durable way to coordinate application transactions with Job launching.

## 9. Database transactions and external side effects

A database transaction does not automatically roll back filesystems, emails, HTTP requests, or message brokers unless those resources participate in the same transaction mechanism.

For example, a chunk updates orders in the database and then calls HTTP to send details to another system. If HTTP succeeds but the database rolls back, the external system may still have received the data. On retry, the request may be sent again.

Common techniques:

1. **Idempotency key:** attach a unique request ID so the receiving system does not process duplicates.
2. **Transactional outbox:** write the event to be emitted in the same transaction as business data, then send after commit.
3. **Compensation:** perform compensating actions when an external system cannot be rolled back.
4. **Step separation:** save database results first, then use a separate Step to send messages with a clear retry policy.

Do not hold a database transaction open while waiting on a slow HTTP request if the operation does not require atomicity with the database. Network wait time keeps connections and locks held longer, and a database rollback cannot recall a request already processed externally.

## 10. Designing restarts when transactions are split by Step or chunk

When a Job fails, Spring Batch stores metadata so the same JobInstance can be restarted if configuration permits. Short transaction boundaries turn committed parts into clear recovery milestones.

For example:

```text
importOrdersJob
  |
  +--> Chunk 1: COMMITTED
  +--> Chunk 2: COMMITTED
  +--> Chunk 3: FAILED / ROLLED BACK
  +--> Chunk 4: not yet run

Restart with the same identifying JobParameters
  |
  +--> New JobExecution
         +--> restore from committed checkpoint
         +--> reprocess the needed portion
```

For safe restarts:

- Use the same identifying JobParameters to identify the correct JobInstance.
- Use a stateful reader if continuing from a checkpoint is needed.
- Design the writer and business operations to tolerate retries or re-runs.
- Control non-transactional side effects using idempotency or an outbox.
- Avoid committing each item independently if doing so breaks the chunk's desired consistency.

If a Step completed in a previous run, Spring Batch normally skips that Step on restart unless configured with `allowStartIfComplete(true)`. Enable this option only when you genuinely want the Step to re-run and the Step's logic is safe to execute multiple times.

## 11. How to spot transactions running too long

When investigating performance or lock contention, observe both the application and the database:

| Symptom | What to check |
|---|---|
| Connection pool exhausted while Job runs | How long connections are held, whether an outer transaction wraps the launcher. |
| Locks persist until the end of the Job | Which transaction holds the lock, which Step/chunk has not committed. |
| Rollback takes a long time | Transaction size and number of uncommitted changes. |
| Deadlocks spike when batches run concurrently | Update ordering, lock scope, and transaction duration. |
| Transaction timeout | Timeouts of the database, transaction manager, and connection pool. |
| Chunks processed yet committed data not visible | Whether an outer transaction wraps the Job or Step. |

You can log start/end timestamps of Steps and chunks, and monitor database transaction duration, connection pool active count, lock waits, and deadlocks. Do not just raise timeouts to hide an oversized transaction scope.

## 12. Common design mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Putting `@Transactional` on a method calling `JobLauncher.run()` | An outer transaction can wrap a synchronous Job and make Steps join one transaction. | Keep the launch method non-transactional; configure transactions at the Step. |
| Using one Tasklet to process millions of items in a single call | The Tasklet transaction can run long and be hard to restart. | Switch to chunks or split into small units with checkpoints. |
| Using `REQUIRES_NEW` for every item | Data can partially commit even if the chunk rolls back. | Use only when an independent transaction is intentionally needed. |
| Calling HTTP inside a chunk transaction and waiting long | Holds connections/locks during the wait; HTTP does not roll back with the database. | Use an outbox, idempotency, or a separate messaging Step. |
| Thinking JobRepository needs a Job-wide transaction | Metadata transaction scope is confused with business transactions. | Let repository and Step manage metadata/transactions via Spring Batch mechanisms. |
| Using a long transaction to guarantee all-or-nothing for the whole Job | Massive rollbacks and cannot cover files/APIs without distributed transactions. | Split transactions by business unit and design restart/compensation. |

## Conclusion

Do not open a single transaction spanning an entire Job. A Job's role is coordination, whereas transactions should be managed at the scope of a Step, a chunk, or a single Tasklet execution. Avoid placing `@Transactional` around `JobLauncher` calls because with a synchronous launcher, an outer transaction can cause Step transactions to join one long transaction. Splitting transactions by processing unit limits locks, connections, and rollback cost while providing clear checkpoints for restarts. For side effects outside the database, use idempotency, an outbox, or compensation instead of expecting a database rollback to undo every system.
