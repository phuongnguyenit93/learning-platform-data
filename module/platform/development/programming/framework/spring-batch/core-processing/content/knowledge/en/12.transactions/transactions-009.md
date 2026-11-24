# Deadlocks and transaction retries

In Spring Batch, a Step typically reads, processes, and writes data in chunks. Each chunk is executed inside a transaction managed by the transaction manager. When multiple Jobs, Steps, or applications access the same group of data concurrently, transactions can contend for database locks. A particular contention scenario is a **deadlock**: two or more transactions hold locks that the other needs, forming a wait cycle that cannot resolve on its own.

The database usually detects a deadlock and chooses one transaction as a victim to roll back. The application can retry that transaction after a short wait. In Spring Batch, retries need to be configured with a limit and placed at an appropriate boundary so the next attempt runs in a new transaction. Retry helps handle transient conflicts; it is not a substitute for fixing the SQL statements, update ordering, or locking design that caused the deadlock.

## 1. What is a deadlock?

A deadlock occurs when transactions hold resources that other transactions are waiting for, forming a wait cycle. The database cannot let all transactions proceed, so the database management system detects the cycle and typically chooses one transaction to roll back in order to release its locks.

For example, two transactions update two accounts in opposite order:

```text
Transaction A                 Transaction B
--------------                 --------------
LOCK account 10                LOCK account 20
       |                              |
       v                              v
UPDATE account 10              UPDATE account 20
       |                              |
       v                              v
WAIT account 20                WAIT account 10
       |                              |
       +---------- DEADLOCK ----------+
```

Transaction A holds a lock on account 10 and waits for account 20. Transaction B holds a lock on account 20 and waits for account 10. Each transaction is waiting for a lock held by the other. The database detects the wait cycle and rolls back one transaction, for example Transaction B. Once the lock is released, Transaction A can proceed.

Deadlocks do not only happen when two transactions update the same table. One transaction might lock the orders table and then need the inventory table, while another transaction locks the inventory table and then needs the orders table. A lock cycle across multiple tables still creates a deadlock.

## 2. Distinguishing deadlocks from lock wait timeouts

Deadlocks and lock wait timeouts both relate to a transaction failing to acquire a lock in time, but their nature is different.

| Situation | Meaning | Typical behavior |
|---|---|---|
| Deadlock | Transactions form a lock-wait cycle | The database detects the cycle and rolls back one transaction |
| Lock wait timeout | A transaction waits for a lock longer than the allowed time | The database or transaction configuration terminates the waiting operation/transaction |
| Optimistic locking conflict | Data was already modified by another transaction before the update | The update does not match the expected version or row count; the application must re-read and decide how to handle it |

Not all locking errors should be retried in the same way. A deadlock is usually a conflict likely to clear once the other transaction finishes. A lock timeout can also be transient, though it may indicate that another transaction is holding locks for too long. An optimistic locking conflict may require re-reading the data and recalculating based on the new state.

The application should rely on the exception translated by the database driver and Spring, vendor error codes, and business rules to classify errors. Do not catch every `DataAccessException` and retry, because SQL syntax errors, constraint violations, or invalid data usually will not resolve on retry.

## 3. Why can Spring Batch encounter deadlocks?

Deadlocks often occur when multiple transactions perform overlapping read/write operations. In a batch system, sources of contention can include:

- Multiple Jobs concurrently updating one table or the same group of accounts.
- One Job running in parallel across multiple workers or partitions with overlapping data ranges.
- A Batch Job and an online application updating business data concurrently.
- Transactions updating multiple tables in different orders.
- Queries scanning many rows due to missing appropriate indexes, making the lock scope larger than expected.
- Oversized chunks holding locks longer and increasing transaction duration.
- A transaction performing slow operations or calling external systems while holding locks.

For example, Job A processes orders in ascending `order_id` order while Job B processes inventory and then updates orders in a different order. If both Jobs lock rows in opposite orders, they can create a wait cycle.

Simply increasing the number of threads or partitions does not guarantee a Job runs faster. Higher concurrency can increase throughput when data is independent, but it also increases lock contention when multiple workers access the same data.

## 4. How does the database detect and handle deadlocks?

The database manages locks and tracks wait relationships between transactions. When it detects a deadlock cycle, the database picks one transaction as a victim. The choice may be based on rollback cost, amount of work already done, or rules specific to the database management system.

The chosen transaction typically receives a deadlock error and is rolled back. The remaining transactions can proceed once locks are released. Applications should not assume the rolled-back transaction is always the newest or the one with the least data; victim selection policy depends on the database.

Databases provide tools to inspect deadlock information, such as deadlock graphs, transactions holding/waiting for locks, involved SQL statements, and locked objects. When incidents recur, collect this data to find the root cause rather than merely increasing the retry limit.

## 5. What does transaction retry mean?

When a transaction is rolled back by the database due to a deadlock, operations inside that transaction cannot simply continue as if nothing happened. The transaction has usually been marked rollback-only or the database has aborted the transaction state. Attempting to re-run just the SQL statement within the same failed transaction usually will not solve the problem.

A true retry means re-executing the unit of work in a new transaction:

```text
Attempt 1
  Begin transaction
  Read / process / write
  Database reports deadlock
  Roll back transaction
          |
          v
      Wait backoff
          |
          v
Attempt 2
  Begin new transaction
  Re-execute unit of work
  Commit if successful
```

In Spring Batch, with a chunk-oriented Step, the transaction typically wraps one chunk. If the writer operation hits a deadlock, the chunk can roll back. The Step's fault tolerance and retry mechanism can retry according to the configured policy. Details of which items are re-read or reprocessed depend on exception type, reader buffering, retry policy, and Step configuration; the design must assume that logic within the chunk can be executed again.

Retries should be bounded. If the database is overloaded or deadlocks occur continuously due to locking design, infinite retries only add load and prolong Job runtime.

## 6. Configuring deadlock retries in Spring Batch

For a chunk-oriented Step, you can use `faultTolerant()` and specify the exception to retry. The following example illustrates Spring Batch 5:

```java
@Bean
Step updateAccountsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<AccountChange> reader,
        ItemProcessor<AccountChange, AccountChange> processor,
        ItemWriter<AccountChange> writer) {

    return new StepBuilder("updateAccountsStep", jobRepository)
            .<AccountChange, AccountChange>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .retry(PessimisticLockingFailureException.class)
            .retryLimit(3)
            .build();
}
```

`PessimisticLockingFailureException` is Spring's exception family for pessimistic locking failures. Depending on the database, driver, and `SQLExceptionTranslator`, a specific deadlock error may be mapped to another subclass, such as `DeadlockLoserDataAccessException` in some versions or `CannotAcquireLockException`. In production, check the actual exception thrown and configure the narrowest possible type for the error you want to retry. Retrying a broad exception group can cause inappropriate locking errors to be retried as well.

`retryLimit(3)` sets the retry limit per the API of the version in use. Confirm how the Spring Batch version in the project counts attempts and document the operational limit clearly. If the error persists after the allowed attempts, the Step fails so operators can investigate.

Do not configure `.skip(PessimisticLockingFailureException.class)` as a standard way to handle deadlocks. A deadlock does not mean the input item is invalid; skipping the item can lose business updates. Normally you should retry the transaction/chunk, then let the Job fail if it cannot complete.

## 7. Adding backoff between retries

If retried immediately, the new transaction may hit the exact same lock contention before the other transaction finishes. Backoff introduces a wait interval before the next attempt, helping reduce the chance of multiple workers colliding again simultaneously.

You can configure `ExponentialBackOffPolicy`:

```java
@Bean
ExponentialBackOffPolicy deadlockBackOffPolicy() {
    ExponentialBackOffPolicy policy = new ExponentialBackOffPolicy();
    policy.setInitialInterval(200L);
    policy.setMultiplier(2.0);
    policy.setMaxInterval(2_000L);
    return policy;
}
```

Attach the policy to the Step:

```java
return new StepBuilder("updateAccountsStep", jobRepository)
        .<AccountChange, AccountChange>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(PessimisticLockingFailureException.class)
        .retryLimit(3)
        .backOffPolicy(deadlockBackOffPolicy)
        .build();
```

With exponential backoff, the wait time increases progressively across attempts up to a maximum cap. You can add jitter if supported by the library or policy in use, so multiple workers do not wake up and resubmit transactions at the exact same instant.

Backoff needs to fit the batch window. Waiting too long may prevent the Job from finishing in time; waiting too briefly may cause deadlocks to repeat. Measure in practice and avoid stacking backoff multipliers across multiple retry layers.

## 8. Where to place retries so a new transaction is created

Where you place the retry matters greatly. If code catches a deadlock error inside a transaction and immediately repeats the SQL statement within that same transaction, the database may already have marked the transaction rollback-only or aborted it. The next attempt no longer has a valid transaction to execute in.

With Spring Batch, configure retry in the Step's fault tolerance mechanism so the framework manages the rollback and performs the retry at the transaction boundary. Each attempt needs a suitable new transaction opened by the transaction manager.

If building custom retry around a service using `TransactionTemplate`, the general structure should place the transaction inside the retry loop so each iteration creates a new transaction:

```text
Retry controller
    |
    +--> Attempt 1 -> Transaction 1 -> deadlock -> rollback
    |
    +--> backoff
    |
    +--> Attempt 2 -> Transaction 2 -> success -> commit
```

Do not place a retry loop inside a single `@Transactional` method if that causes all attempts to share a broken transaction. Also pay attention to Spring proxies: calling another `@Transactional` method in the same object via self-invocation may bypass the proxy and fail to create a new transaction as expected.

Avoid stacking `@Retryable`, HTTP client retries, and Spring Batch retries without calculating the total number of attempts. Multiple retry layers can multiply the number of requests or update attempts tremendously.

## 9. Reducing deadlocks through database and transaction design

Retries handle transient situations, but reducing the causes of deadlocks generally delivers longer-lasting results.

### Lock rows in a consistent order

If multiple transactions must update the same set of rows, standardize the access order. For example, all Jobs update accounts in ascending `account_id` order. This reduces the likelihood of transaction A locking row 10 and waiting for 20 while transaction B locks 20 and waits for 10.

For operations updating multiple tables, standardize both table order and row order across business flows.

### Keep transactions short

Hold a transaction only for as long as needed to read/write the related data. Avoid calling HTTP APIs, sending emails, waiting on users, or performing heavy computation while a transaction is holding locks. If reference data from external systems is needed, consider fetching it beforehand or using a snapshot.

### Create appropriate indexes

Queries lacking indexes may scan many rows, increasing the number of locked rows or lock duration depending on the database and isolation level. Indexes on filter columns, joins, and update keys can help queries locate target rows faster. However, indexes also add write overhead; inspect execution plans and actual database locking behavior.

### Reduce update scope

Update only the necessary rows and columns. Avoid holding locks over a broad dataset when it can be split into non-overlapping ranges. `WHERE` conditions should be selective enough and have appropriate indexes.

### Reduce chunk size where appropriate

Smaller chunks can make transactions shorter and reduce lock hold times. In return, commit count increases and throughput may drop. Test multiple chunk sizes on representative data rather than shrinking them arbitrarily.

### Control concurrency level

Reducing the number of concurrent workers or partitions can lower lock contention. If partitions have independent data ranges, partition by non-overlapping keys. Avoid having multiple workers update the same group of accounts or the same summary record concurrently.

## 10. Isolation levels can affect deadlocks

The isolation level governs how much one transaction sees changes from other transactions and how the database locks or versions data. Higher isolation levels may increase waiting or lock scope in some databases; lower levels may improve concurrency while permitting different read phenomena.

Do not lower the isolation level just to eliminate deadlocks without verifying data consistency requirements. For example, a Job calculating balances or performing reconciliation may need to guarantee a consistent dataset. Changing isolation can cause results to violate business rules.

Check:

- The actual isolation level of the transaction manager and the database.
- Whether queries use `SELECT ... FOR UPDATE` or any special lock types.
- How the database uses row locks, page locks, range locks, or MVCC mechanisms.
- Whether indexes and execution plans alter the lock scope.
- Whether optimistic locking with a version column can be used for low-contention updates.

Optimistic locking detects conflicts when the version has changed, typically via an updated row count of 0 or a corresponding exception. It is not the same as a deadlock; the application typically must re-read the data and recalculate changes based on the new version.

## 11. Idempotency and side effects on retry

Retries can cause part of the logic to be executed again. If all operations reside within the same database transaction and the transaction rolls back completely, changes in that transaction are undone. However, side effects outside the transaction may still persist.

For example, a processor calls a partner API to create a transaction, then the writer updates the database and hits a deadlock. The database rolls back, yet the partner transaction has already been created. If the chunk is retried, the API may be called again and create a duplicate transaction.

To reduce risk:

- Use a stable idempotency key derived from the item's business identifier.
- Ensure the target system checks the key and returns the prior call's result instead of creating a new side effect.
- Write events to be emitted into a transactional outbox and dispatch them via an idempotent consumer.
- Separate reading reference data from operations that produce side effects.
- Have a reconciliation step when the outcome of an external call is uncertain due to a timeout.

Do not assume a request timeout means the target service has not performed the operation. The server may have committed while the response was lost in transit. Retrying a write request without idempotency can cause duplicates even without a deadlock.

## 12. Monitoring and investigating deadlocks

When a Job hits a locking error, collect sufficient information to determine the cause:

- JobExecution ID, StepExecution ID, and Job/Step names.
- The chunk or business key being processed when the error occurred.
- Full exception, SQLState, vendor error code, and root cause.
- SQL statements and the order of update operations in the transaction.
- Transaction start/end timestamps and lock wait times.
- Deadlock graph or corresponding logs from the database.
- Retry count, backoff, and the outcome of each attempt.

Do not log sensitive data or full payloads unnecessarily. You can log record identifiers and correlation IDs for tracing.

Useful metrics:

| Metric | What to observe |
|---|---|
| Deadlock count | Number of deadlocks by database, Job, and time period |
| Retry count | Number of times transactions/chunks had to be retried |
| Retry exhausted | Number of times a Step failed after exhausting retries |
| Transaction duration | Transaction duration and p95/p99 distribution |
| Lock wait time | Time spent waiting on locks |
| Chunk duration | Processing duration per chunk |
| Job throughput | Number of items completed per second/minute |

If retries surge while the Job still finishes, the system may be masking a lock contention problem. If deadlocks cluster around the same table or group of business keys, investigate the SQL statements and how data is partitioned.

## 13. Procedure when a Step encounters a deadlock

A practical operational procedure can include:

1. Identify the failing StepExecution and chunk from logs and Spring Batch metadata.
2. Inspect the exception, SQLState, and vendor error code to confirm whether it is a deadlock or a lock timeout.
3. Check the database deadlock graph/logs to find the transactions, SQL statements, and locks forming the cycle.
4. Identify the Jobs, workers, or online applications updating the same data concurrently.
5. Inspect table/row access order, indexes, transaction duration, and chunk size.
6. Fix the root cause, such as standardizing lock order or separating data ranges.
7. Configure bounded retries and backoff for identified transient errors.
8. Verify the writer and external services are safe when a chunk is re-executed.
9. Re-run in a representative environment, monitoring deadlock count, retry count, and throughput.

Do not just raise the retry limit to make alerts disappear. If deadlocks occur frequently, retries can prolong the Job, increase database load, and hide an unsuitable data access design.

## 14. Common mistakes when retrying transactions

**Retrying every exception:** data errors, bad SQL, or constraint violations do not fix themselves when retried. Only retry exceptions identified as transient.

**Retrying SQL inside a rollback-only transaction:** the old transaction is no longer valid. Each attempt must run in a new transaction.

**Infinite retries:** prolongs the Job and increases load when the database is having an incident. Set clear limits, backoff, and failure policies.

**Skipping deadlocks like data errors:** can drop valid updates. Deadlocks should normally retry the transaction/chunk rather than skip the item.

**Holding a transaction while calling external services:** network wait times keep locks held longer, increasing deadlock probability. Move external calls outside the transaction scope when business rules permit.

**Failing to ensure idempotency:** a retry can repeat side effects that already happened outside the database transaction.

**Not checking the actual exception:** each database and driver may map deadlocks to different error codes or exceptions. Check the translator and system logs.

**Only shrinking chunk size without finding the root cause:** smaller chunks may reduce lock hold time, but do not eliminate lock cycles caused by reversed update ordering.

## Conclusion

Deadlocks happen when transactions hold locks and wait on each other in a cycle. The database typically rolls back one transaction to release locks; Spring Batch can retry transient locking errors using the fault-tolerance mechanism of a chunk-oriented Step. Retries need limits, backoff, and must re-run in a new transaction. To reduce deadlocks long term, standardize row and table update ordering, keep transactions short, optimize indexes, narrow lock scope, and control concurrency. At the same time, design writes and external side effects to be idempotent so retries or restarts do not create duplicate data.
