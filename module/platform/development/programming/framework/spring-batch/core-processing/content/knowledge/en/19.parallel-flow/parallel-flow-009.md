# Deadlocks When Flows Share Resources

In Spring Batch, a Job can run multiple flows or Steps in parallel to shorten processing time. When parallel branches access a shared resource such as a database table, data row, file, connection pool, or external service, they can contend for that resource. One severe case is a **deadlock**: each transaction holds a lock that the other transaction needs, leaving neither able to proceed.

Deadlocks commonly appear when Steps update the same group of data in different orders. For example, flow A locks a customer record first and then an account; flow B locks the account first and then the customer. If the two transactions run concurrently, each can hold one lock while waiting for the other's lock. The database typically detects the wait cycle, picks one transaction as the deadlock victim, and rolls it back.

To reduce deadlocks, design each flow's data boundaries, resource access ordering, transaction duration, and concurrency level. Retries can help recover from transient deadlocks, but they do not replace fixing the underlying contention cause.

## 1. What is a deadlock?

A deadlock occurs when two or more transactions hold resources that other transactions are waiting for, forming an unresolvable wait cycle.

Example of two transactions updating two rows in the same table:

```text
Transaction A                    Transaction B
--------------                    --------------
BEGIN                             BEGIN
Lock row 1                        Lock row 2
                                  Request lock row 1
Request lock row 2                (waiting for A)
(waiting for B)                      |
       |                          |
       +-------- wait cycle ------+
```

Transaction A holds a lock on row 1 and waits for row 2. Transaction B holds a lock on row 2 and waits for row 1. Neither can continue. The database detects a cycle in the wait-for graph and typically rolls back one transaction to release its locks.

A deadlock differs from ordinary lock waiting. Lock waiting ends once the lock-holding transaction commits or rolls back. A deadlock has a wait cycle; the database must break the cycle by aborting a transaction or applying specific handling.

## 2. Why can parallel flows cause deadlocks?

When a Job has multiple flows running concurrently, Steps in those flows may use the same database or external resources. Each Step typically has its own transaction per chunk or per Tasklet invocation. Transactions of Steps running on different threads can concurrently hold locks on shared resources.

Example of a Job split into two flows:

```text
                    Job
                     |
                  split()
                 /       \
                v         v
            Flow A      Flow B
                |         |
                v         v
          updateOrder  updateAccount
                |         |
                +----+----+
                     |
             Shared database tables
```

Situations that commonly create contention:

- Two Steps update the same record or the same group of records.
- Two Steps update multiple tables in different orders.
- A Step holds locks while making HTTP calls or waiting on files/network.
- A Writer updates a business table while another flow reads or writes a related table with foreign keys/indexes.
- Partitions have overlapping data ranges.
- One flow updates a business table while another updates shared metadata or status tables.
- Multiple Jobs run concurrently against the same database and the same business keys.

Not every shared resource causes deadlocks. If transactions simply wait on the same lock in one direction, the system slows down without forming a cycle. Deadlocks occur when lock acquisition and wait orders form a cycle.

## 3. Example deadlock caused by different update orders

Suppose two flows update two tables, `customer` and `account`.

Flow A executes:

```sql
BEGIN;
UPDATE customer SET status = 'ACTIVE' WHERE id = 10;
UPDATE account SET balance = balance + 100 WHERE customer_id = 10;
COMMIT;
```

Flow B executes in the reverse order:

```sql
BEGIN;
UPDATE account SET balance = balance + 100 WHERE customer_id = 10;
UPDATE customer SET status = 'ACTIVE' WHERE id = 10;
COMMIT;
```

If the two transactions run concurrently, Flow A may lock the `customer` row first while Flow B locks the `account` row first. Then A waits for account while B waits for customer. That is a wait cycle causing a deadlock.

One way to reduce risk is standardizing resource access order across all flows—for example, always locking/updating `customer` before `account`. This rule must be applied consistently across every code path that can run concurrently, not only the two Steps under immediate observation.

Table order is not the only factor. Databases can acquire locks on indexes, related rows, foreign keys, or internal structures. When investigating a deadlock, examine execution plans and database deadlock reports rather than only comparing statement order in Java.

## 4. Parallel flows in Spring Batch

With Spring Batch 5 and later, independent flows can run in parallel via `split()` and `TaskExecutor`:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.job.flow.Flow;
import org.springframework.batch.core.job.flow.support.SimpleFlow;
import org.springframework.batch.core.job.flow.builder.FlowBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class ParallelJobConfig {

    @Bean
    public TaskExecutor flowTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setThreadNamePrefix("batch-flow-");
        executor.initialize();
        return executor;
    }

    @Bean
    public Flow customerFlow(Step updateCustomerStep) {
        return new FlowBuilder<SimpleFlow>("customerFlow")
                .start(updateCustomerStep)
                .build();
    }

    @Bean
    public Flow accountFlow(Step updateAccountStep) {
        return new FlowBuilder<SimpleFlow>("accountFlow")
                .start(updateAccountStep)
                .build();
    }

    @Bean
    public Job parallelUpdateJob(
            JobRepository jobRepository,
            Flow customerFlow,
            Flow accountFlow,
            TaskExecutor flowTaskExecutor) {

        Flow splitFlow = new FlowBuilder<SimpleFlow>("splitUpdateFlow")
                .start(customerFlow)
                .split(flowTaskExecutor)
                .add(accountFlow)
                .build();

        return new JobBuilder("parallelUpdateJob", jobRepository)
                .start(splitFlow)
                .end()
                .build();
    }
}
```

The example assumes `updateCustomerStep` and `updateAccountStep` are already declared. Both flows can execute concurrently via the executor. Each Step manages transactions per its configuration; transactions on different threads do not automatically combine into one shared transaction.

`TaskExecutor` controls concurrency capability, but it does not resolve data conflicts by itself. If two Steps update the same records in inconsistent order, increasing thread count can make deadlocks happen more frequently.

## 5. Distinguishing deadlocks from connection pool starvation

A Job can slow down or stall due to different kinds of contention. Distinguish them accurately to pick the right fix.

| Symptom | Signs | Common cause |
|---|---|---|
| Database deadlock | Database logs report a deadlock or transaction victim; lock wait cycle exists | Transactions hold and wait for locks in a cycle. |
| Lock wait/lock timeout | Transaction waits too long on a lock and times out | Another transaction holds a lock for a long time, not necessarily forming a cycle. |
| Connection pool starvation | Threads wait to acquire connections; active pool hits limit, pending count rises | Workers/transactions exceed connection supply or connections are held too long. |
| Thread starvation | Tasks are ready but no threads are available to execute | Executor is too small or threads are blocked. |
| Slow query | SQL runs slowly without deadlocks | Missing indexes, poor execution plan, or scanning too much data. |

Increasing the connection pool will not fix a deadlock caused by wrong lock ordering. Conversely, reducing concurrency can lower both lock contention and connection demand, though you should diagnose the root cause before changing settings.

## 6. Solution 1: partition data so flows do not update the same records

The most effective measure is usually reducing overlapping data regions. When possible, each flow or partition should own a distinct set of business keys.

Example splitting by region:

```text
Flow A: region = NORTH
  customer_id in NORTH group

Flow B: region = SOUTH
  customer_id in SOUTH group
```

Or splitting by non-overlapping ID ranges:

```text
Worker 1: id 1       - 100000
Worker 2: id 100001  - 200000
Worker 3: id 200001  - 300000
```

When splitting data, ensure Writers also update only their assigned scope. A Reader filtering by ID range while a Writer updates a shared summary table can still create lock contention.

If multiple flows must update the same entity, designate a single Step responsible for updating that entity, or funnel changes into a sequential stream. You can run independent computation in parallel and merge results in one final Step.

## 7. Solution 2: standardize resource access order

If multiple transactions must lock multiple tables or rows, standardize the access order. For instance, every processing path:

1. Locks or updates the `customer` record.
2. Locks or updates the `account` record.
3. Updates the `order` record.

When processing multiple IDs, sort the IDs in the same order before locking/updating. This reduces the chance of transaction A holding a lock on resource X while waiting for Y while transaction B holds Y and waits for X.

Illustrative SQL example:

```sql
BEGIN;
SELECT id FROM customer WHERE id = ? FOR UPDATE;
SELECT id FROM account WHERE customer_id = ? ORDER BY id FOR UPDATE;
-- Update data in the agreed order
COMMIT;
```

Lock syntax and semantics depend on the database. Verify `FOR UPDATE` clauses, isolation levels, and lock order on the actual database engine. Not every `SELECT` locks rows; also avoid adding pessimistic locks without a clear business need.

## 8. Solution 3: shorten transactions

The longer a transaction runs, the longer locks may be held, increasing the chance of colliding with other transactions. In Spring Batch, chunk processing commits per group of items instead of holding one transaction for the entire Job.

Ways to shorten transaction duration:

- Choose a moderate commit interval so transactions do not span excessive work.
- Do not make HTTP calls, send emails, or wait on message brokers while holding database locks.
- Compute non-database transformations before opening a write transaction if architecture allows.
- Add appropriate indexes so update statements locate target rows faster.
- Avoid queries or updates scanning excessive rows inside the same transaction.
- Do not open an outer transaction wrapping the entire Job or a long flow.
- Use Tasklets for short operations; move large item-processing loops into chunk Steps.

For example, instead of calling an API per item inside a Writer transaction, write an event to a transactional outbox within the business transaction and dispatch externally after commit. This avoids holding locks during network waits while still persisting the send request durably.

## 9. Solution 4: bound concurrency appropriately

More threads do not always make a Job faster. If a database can only handle a certain number of concurrent transactions efficiently, adding workers can increase lock waits, deadlocks, context switching, and connection usage.

Parameters you can tune:

- `corePoolSize` and `maxPoolSize` of `TaskExecutor`.
- `gridSize` when using partitioning.
- Number of partitions dispatched concurrently.
- Number of Jobs the scheduler allows to run simultaneously.
- Connection pool size and timeouts, within database resource limits.

Example of a clearly bounded executor:

```java
@Bean
public TaskExecutor batchTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(8);
    executor.setThreadNamePrefix("batch-worker-");
    executor.initialize();
    return executor;
}
```

Four threads is only an example. Benchmark based on database capacity, connection counts, transaction times, and online application load. Do not set pool sizes to an arbitrary large number.

The connection pool needs enough capacity for genuinely concurrent transactions alongside other application needs. However, making the pool too large can push more concurrent transactions onto the database than optimal. Observe active connections, pending connections, acquisition time, and transaction duration before tuning.

## 10. Solution 5: choose appropriate isolation and locking strategies

Isolation levels affect how transactions view data and what locks or concurrency control mechanisms the database uses. Higher isolation does not automatically eliminate deadlocks; in some databases, it can increase locks or create additional contention.

Common options:

- `READ_COMMITTED`: often the default in many databases; avoids dirty reads while still able to encounter deadlocks on updates.
- `REPEATABLE_READ`: preserves stronger read consistency depending on the database; can increase lock duration or range.
- `SERIALIZABLE`: highest standard isolation level; reduces anomalies but lowers concurrency and can trigger serialization failures.
- Optimistic locking: uses a version column to detect concurrent updates; suitable when conflicts are rare and business retries are possible.
- Pessimistic locking: locks before updating; suitable when preventing concurrent edits is required, though it can increase lock waits.

Example of optimistic locking with JPA:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class Account {

    @Id
    private Long id;

    private String status;

    @Version
    private long version;
}
```

When two transactions update the same entity concurrently, the version field detects that one transaction wrote based on stale state. Optimistic locking typically fails with an optimistic lock exception instead of holding long lock waits, though the application still needs to handle conflicts, reload, and retry per business rules.

Do not change isolation levels based on guesswork. Examine deadlock reports and database documentation to determine which locks are acquired by your queries, indexes, and current isolation level.

## 11. Solution 6: controlled deadlock retries

Deadlocks are sometimes transient errors caused by two transactions momentarily crossing paths. The database typically rolls back a victim transaction; the application can retry that transaction after a brief delay.

In Spring Batch, you can configure retries for the appropriate locking exception hierarchy:

```java
import org.springframework.dao.PessimisticLockingFailureException;

return new StepBuilder("updateStep", jobRepository)
        .<InputRecord, OutputRecord>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(PessimisticLockingFailureException.class)
        .retryLimit(3)
        .build();
```

Adjust this example to match the exceptions actually thrown by your database driver and Spring exception translator. Some errors may surface as another subclass of `TransientDataAccessException` or `PessimisticLockingFailureException`. Check the exception chain in logs before configuring.

Retries should have limits and backoff so transactions do not immediately collide again at the same instant. If deadlocks happen continuously because two flows always lock resources in opposite order, retries only increase retry counts; fix the access order or partition the data.

Writers and external operations must be idempotent before enabling retries. If a transaction rolls back after an API call already succeeded, a retry may send the request again. Use idempotency keys or an outbox for such side effects.

## 12. Caution when flows share JobRepository

Steps and flows in a Job update execution metadata via `JobRepository`. During parallel runs, multiple StepExecutions may write metadata nearly simultaneously. Spring Batch supports this, provided the repository and schema are configured properly, the transaction manager is suitable, and the database can handle the load.

Key points to remember:

- Never update `BATCH_*` tables directly to bypass locks or alter statuses while a Job is running.
- Use the metadata schema matching your Spring Batch version.
- Never share a custom mutable `ExecutionContext` across threads.
- Each Step/partition needs its own framework-managed metadata scope.
- If JobRepository and business tables share a DataSource, include metadata load when sizing the connection pool and concurrency.
- Never open an outer transaction wrapping the entire Job; metadata transactions and business transactions need clear boundaries.

If deadlocks occur on `BATCH_*` tables, inspect the deadlock report to see which SQL statements and transactions hold locks. Do not assume every batch deadlock involves business tables.

## 13. Shared files, caches, and external services

Deadlocks are usually discussed in the context of databases, yet parallel flows can contend on other resources as well:

### Shared files

Two flows writing to one file can interleave data, overwrite contents, or fail on file locks. Address this by using separate filenames per partition/StepExecution, writing separate temporary files and merging in a final Step, or using file locking with timeouts and proper release.

### Caches or mutable singletons

A singleton bean holding a `HashMap`, `ArrayList`, or shared state fields can suffer race conditions when multiple flows mutate it. This is not necessarily a database deadlock, yet it can hang Jobs, corrupt data, or throw concurrent exceptions. Use thread-safe structures, immutable data, or appropriate durable state.

### External services

Two flows can call the same API and hit concurrency limits or business locks in the target system. Apply rate limits, idempotency keys, timeouts, and retries with backoff. Do not hold a database transaction open while waiting on an external service unnecessarily.

Java `synchronized` only coordinates threads within the same JVM. If a Job runs across multiple processes or machines, in-memory locks cannot protect resources shared across processes. When distributed coordination is required, use database constraints/locks, a distributed lock service, or data partitioning; also define leases, timeouts, and behavior when a worker dies.

## 14. How to diagnose deadlocks

When a Job deadlocks, identify the exact transactions, SQL statements, and resources rather than merely increasing timeouts.

Investigation steps:

1. **Pinpoint timing:** record JobExecution, StepExecution, flow, thread name, and deadlock timestamp.
2. **Collect the database deadlock report:** inspect the victim transaction, held locks, awaited locks, tables/indexes, and related SQL statements.
3. **Correlate parallel Steps:** determine which Steps were running concurrently and whether they update the same keys.
4. **Compare access order:** verify whether transactions lock tables/rows in different orders.
5. **Inspect transaction durations:** look for slow queries, network calls, or long loops inside transactions.
6. **Check pools and executors:** check active/pending connections, running/waiting threads, and concurrency limits.
7. **Reproduce deterministically:** run the same data at low concurrency and scale up gradually to isolate thresholds and patterns.
8. **Apply fixes:** reduce overlapping data ranges, unify lock order, shorten transactions, or cap workers; then re-verify.

Metrics to observe:

| Metric | What to look for |
|---|---|
| Deadlock count and deadlock victim | Frequency, SQL statements, and transaction chosen for rollback. |
| Lock wait duration | Which Step holds locks long or waits heavily. |
| Transaction duration | Whether transactions run longer than expected. |
| Query duration/plan | Whether queries scan tables or lack indexes. |
| Connection pool active/pending | Whether workers wait for connections. |
| Executor active/queue | Whether thread starvation or excessive queuing exists. |
| StepExecution start/end/status | Which flow is slow, failed, or retried. |
| Rollback/retry count | Whether deadlocks recover or loop repeatedly. |

Thread dumps help identify Java threads waiting on connections, JVM locks, or external service responses. However, database deadlocks must be confirmed with database-side diagnostics because JVM thread dumps do not show the database wait-for graph.

## 15. Example of redesigning two conflicting flows

Suppose two flows previously updated `customer` and `account` in opposite orders. You can fix this in one of several ways:

**Option A: consolidate updates into one sequential Step.** If both operations modify the same business aggregate, handle them in one Writer/Step with a consistent order to prevent two transactions from competing simultaneously.

**Option B: split into non-overlapping data.** Flow A processes even customer IDs, Flow B processes odd IDs, if business logic permits and related updates do not cross group boundaries.

**Option C: parallelize computation, serialize writes.** Both flows write independent results to staging tables; one final Step merges into main tables by business key and unified lock order.

**Option D: cap concurrent flows.** If the database has tight transaction concurrency limits, shrink the thread pool and schedule Jobs in smaller batches.

Choose the option based on business independence. Do not split data solely to dodge deadlocks if doing so leaves an aggregate half-updated or breaks consistency invariants.

## 16. Common mistakes

| Mistake | Consequence | Solution |
|---|---|---|
| Adding threads to cure a slow Job | More transactions contend, deadlocks may increase. | Benchmark concurrency and inspect lock waits. |
| Two flows updating tables in opposite orders | Creates wait cycles between transactions. | Standardize resource access order. |
| Holding transactions during HTTP calls or file waits | Locks and connections are held too long. | Move side effects post-commit via outbox or a separate Step. |
| Only increasing transaction timeouts | Deadlocks do not vanish; wait times simply grow longer. | Read deadlock reports and fix lock contention. |
| Unbounded retries | Creates retry storms and overloads the database. | Bound retries with backoff and idempotency. |
| Using `synchronized` to lock database work across hosts | Monitors apply only within one JVM. | Use database/distributed coordination or data partitioning. |
| Checking only that Readers do not overlap | Writers can still update shared tables/keys. | Analyze the entire write path and related resources. |
| Confusing pool starvation with deadlocks | Tunes the wrong component. | Combine DB deadlock reports, pool metrics, and thread dumps. |
| Unbalanced partitions | One worker drags on while others wait to finish the flow. | Choose more balanced partition keys and ranges. |

## Conclusion

Deadlocks in parallel flows typically occur when concurrently executing Steps hold and wait for locks on shared resources in inconsistent orders. Reduce overlapping data regions, standardize access orders, shorten transactions, and bound concurrency to match database capacity. Bounded retries can recover from transient deadlocks, provided Writers and side effects are idempotent to prevent duplicate data. When diagnosing issues, correlate database deadlock reports with JobExecution, StepExecution, threads, connection pools, and transaction durations to locate the exact root cause before tuning configurations.
