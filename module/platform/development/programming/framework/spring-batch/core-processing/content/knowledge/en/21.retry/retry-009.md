# Retry with transaction rollback in Spring Batch

In a chunk-oriented Step, Spring Batch processes multiple items within the same transaction. If an operation hits a transient error such as a database deadlock, lock timeout, or remote service interruption, the application may need to retry. However, retrying is only safe when you understand the current transaction's state and whether changes from the previous attempt have rolled back.

**Retry** decides whether to re-attempt an operation after an exception. **Rollback** decides whether the current transaction is undone. These two policies are closely related, yet they are not the same thing. An operation may be marked retryable while the transaction still needs to roll back before the next attempt begins. Conversely, an exception may not trigger rollback and still not be retried.

This lesson covers the chunk transaction lifecycle, how retry coordinates with rollback, the difference between retrying within a transaction and retrying after rollback, configuring rollback rules, how writers and processors are re-invoked, and requirements for idempotency, backoff, restart, and testing.

## 1. Retry and rollback solve two different problems

Retry and rollback frequently appear together when handling transient errors, yet each mechanism has its own responsibility.

| Mechanism | Question it answers | Example |
|---|---|---|
| Retry | Should the operation be attempted again after an exception? | Retry when the database reports a deadlock |
| Rollback | Does the current transaction need to be undone? | Undo the chunk's inserts when the writer fails |
| Skip | May the faulty item be discarded and processing continue? | Discard a malformed CSV line |
| Commit | Should the successful transaction's changes be confirmed? | Persist chunk results to the database |
| Restart | Can the Job continue after a failed or stopped JobExecution? | Resume the Step from a checkpoint |

For example, a writer writes 100 orders and the database raises a deadlock:

1. The writer throws an exception.
2. The current transaction may need to roll back to release locks and discard partial changes.
3. The retry policy decides this exception can be retried.
4. If attempts remain, Spring Batch executes the next attempt per Step mechanics.
5. If writing succeeds, the new transaction commits.
6. If retries are exhausted, the Step proceeds per skip policy or fails.

Retry does not automatically roll back a transaction. Rollback does not automatically decide whether to retry. Both behaviors must be configured and tested.

## 2. Transaction boundary of a chunk-oriented Step

A chunk-oriented Step groups items according to the commit interval. The framework reads data, calls the processor if present, and then calls the writer for the output items. The transaction manager governs the chunk's transaction.

Example:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
~~~

With a commit interval of 100, a chunk holds at most 100 input items. The chunk transaction wraps the work that must finish before the chunk is committed.

~~~mermaid
flowchart TD
    A["Begin chunk transaction"] --> B["Read item"]
    B --> C["Process item"]
    C --> D["Writer writes output"]
    D --> E{"Chunk succeeded?"}
    E -- "Yes" --> F["Commit transaction"]
    E -- "No" --> G["Rollback per policy"]
    G --> H["Retry / skip / fail"]
    F --> I["Next chunk"]
~~~

When the transaction commits, changes participating in the transaction become durable. When it rolls back, those changes are undone. Earlier committed chunks remain intact if the current chunk fails.

### One Job has multiple transactions

If a Job processes 10,000 items with a commit interval of 100, it may have many chunks and many independent transactions. A failure in the 50th chunk does not automatically roll back the 49 previously committed chunks.

This is a key characteristic when investigating failures: rollback is usually scoped to the current transaction, not the entire Job.

## 3. What happens when an error occurs inside a chunk?

Suppose a chunk contains items A, B, C, D. The writer executes write statements and an error occurs at C.

~~~text
Current chunk:
  A -> written successfully inside transaction
  B -> written successfully inside transaction
  C -> constraint or deadlock error
  D -> not completed

Result if transaction rolls back:
  A -> undone
  B -> undone
  C -> not written
  D -> not yet written
~~~

If A and B were written through the same transaction manager and managed resource, rollback undoes both changes even though the earlier statements ran successfully.

Afterward, the retry policy may permit re-executing the operation. The next attempt must start from a valid transaction state. For database errors like deadlocks, rollback is usually required so the database releases locks and terminates the affected transaction.

Never treat a successful update count returned by a SQL statement as proof that data committed. Before commit, changes can still roll back.

## 4. Configuring retry in Spring Batch

A chunk Step can enable fault tolerance and declare retryable exceptions:

~~~java
@Bean
Step processOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("processOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(DeadlockLoserDataAccessException.class)
        .retryLimit(3)
        .build();
}
~~~

Main parts:

- `faultTolerant()` enables retry/skip configuration on the chunk Step.
- `retry(...)` specifies which exception types may be retried.
- `retryLimit(...)` limits attempt counts per the retry policy.
- The transaction manager still governs the chunk's transactions.

Do not take `faultTolerant()` to mean every error is retried. Only exceptions recognized by the policy receive retry behavior.

### Retry limit and call count

Limit semantics can depend on the API/policy and the integrated library version. With a SimpleRetryPolicy-style policy, maxAttempts normally includes the initial call. When using Spring Batch's builder, check your running version's documentation and write tests to confirm exact invocation counts. Do not infer attempt counts solely from parameter names.

Example targeting at most three invocations:

~~~text
Attempt 1: transient error
Attempt 2: transient error
Attempt 3: success
Result: operation succeeded within limit
~~~

If all attempts fail, the final exception passes to the skip policy if allowed; otherwise, the Step fails.

## 5. Why do database retries usually require rollback?

Certain database errors indicate the current transaction is no longer fit to continue:

- Deadlock: the database chooses a transaction as a victim and aborts it.
- Lock timeout: the transaction could not acquire a lock within the allotted time.
- Serialization failure: the database rejects the transaction due to concurrent conflict.
- Connection loss: transaction state may no longer be determinate on the client side.
- Write error causing the transaction to be marked rollback-only.

With these errors, continuing to run statements in the same transaction may fail or the transaction is already marked rollback-only. You must roll back the failed transaction and execute the next attempt in a valid transaction under the Step's retry mechanics.

~~~mermaid
sequenceDiagram
    participant S as Spring Batch
    participant TM as TransactionManager
    participant W as ItemWriter
    participant DB as Database

    S->>TM: Begin transaction
    S->>W: write(chunk)
    W->>DB: Execute statements
    DB-->>W: Deadlock
    W-->>S: Throw exception
    S->>TM: Rollback transaction
    Note over S,TM: Retry policy and backoff
    S->>TM: Begin next transaction
    S->>W: Retry write
    W->>DB: Execute statements
    DB-->>W: Success
    S->>TM: Commit
~~~

The diagram depicts a typical scenario. The exact placement of the retry wrapper, whether the chunk or item is replayed, and when a new transaction starts depend on the error type, the phase where the error occurred, and the Step's fault-tolerant configuration.

What matters is that retries respect actual transaction state. If a transaction is already rollback-only, re-invoking a method inside that same transaction cannot be considered a clean attempt.

## 6. In which phases can retry happen?

In a chunk Step, errors can occur in the reader, processor, or writer. Each phase has different state and replay characteristics.

| Phase | Example error | What to consider |
|---|---|---|
| Reader | Timeout querying source | Can the reader restore cursor, connection, or read position? |
| Processor | Enrichment service temporarily failing | Does the processor have side effects or mutate inputs? |
| Writer | Deadlock during insert/update | Does the transaction roll back all chunk changes? |

### Retry in the processor

The processor typically transforms input to output. If the processor calls an external service and the service is temporarily unavailable, it can throw a retryable exception.

~~~java
@Bean
ItemProcessor<OrderInput, EnrichedOrder> orderProcessor(
        CustomerProfileClient profileClient) {

    return input -> {
        CustomerProfile profile =
            profileClient.fetchProfile(input.customerId());

        return new EnrichedOrder(
            input.orderId(),
            profile,
            input.amount()
        );
    };
}
~~~

If the client throws a retryable exception, the framework can re-invoke the processor per the retry policy. The processor should avoid mutating input objects or producing irreversible side effects, because the same item may be processed again.

### Retry in the writer

The writer can hit deadlocks or transient write errors. When a failure rolls back the transaction, the framework may need to re-execute the write operation or reprocess the chunk under fault-tolerance mechanics.

The writer must tolerate receiving the same item or group of items again. Do not assume each item is sent to the writer strictly once.

### Retry in the reader

The reader can experience connection errors when reading a database or remote source. However, readers carry state such as cursors, offsets, file positions, or message acknowledgments. Ensure retries do not drop items or read from the wrong position.

Do not catch an exception and return `null` to signal EOF. `null` means the source is exhausted; transient errors must be represented as exceptions.

## 7. Retry and rollback classification

Retry policy and rollback policy are two independent decisions.

- Retry policy classifies whether an exception may be retried.
- Rollback policy classifies whether an exception rolls back the transaction.
- Skip policy decides whether an item may be discarded.

An exception can be marked retryable without triggering rollback under configuration. Conversely, an exception can trigger rollback without being retried.

Example decision table:

| Exception | Retry? | Rollback? | Reason |
|---|---|---|---|
| Deadlock | Usually yes | Usually yes | Transaction was aborted by the database or cannot continue |
| Lock timeout | Possibly | Usually yes | Transaction must be released before a fresh attempt |
| ValidationException | No | Depends on phase and policy | Data does not change when retried |
| File parse error | Usually no | May not need chunk rollback per policy | Faulty line can be skipped individually |
| HTTP 503 from API | Possibly | Database rollback if chunk must retry and side effects need consistency | Service may recover |
| Broken SQL configuration | No | Usually yes if transaction erred | Configuration must be fixed |

This table is a guideline. Actual exceptions and the transaction manager decide final behavior. Check cause chains, rollback rules, and enlisted resources.

## 8. Rollback rules and checked exceptions

Spring transactions have rollback rules by exception type. Under common defaults, unchecked exceptions and Errors usually trigger rollback; checked exceptions do not necessarily trigger rollback automatically unless a rollback rule is configured.

Example:

~~~java
@Transactional(rollbackFor = IOException.class)
public void writeFileMetadata() throws IOException {
    // Operation that must roll back when IOException occurs.
}
~~~

For a chunk Step, the Step's transaction attributes and Spring Batch's rollback classifier also affect behavior. Never assume every exception behaves identically.

If a checked exception is marked retryable while the transaction does not roll back, the next attempt might continue inside a transaction that still contains changes from the previous attempt. That is safe only if the transaction and operations remain in a valid state. For database errors that break the transaction, rollback is required.

### Configuring transaction attributes for a Step

You can configure propagation, isolation, timeout, and rollback rules via TransactionAttribute:

~~~java
@Bean
TransactionAttribute chunkTransactionAttribute() {
    RuleBasedTransactionAttribute attribute =
        new RuleBasedTransactionAttribute();

    attribute.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRED
    );
    attribute.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED
    );
    attribute.setTimeout(60);
    attribute.setRollbackRules(List.of(
        new RollbackRuleAttribute(Exception.class)
    ));

    return attribute;
}
~~~

Attach to the Step:

~~~java
return new StepBuilder("importStep", jobRepository)
    .<InputRecord, OutputRecord>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .transactionAttribute(chunkTransactionAttribute)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .build();
~~~

The example above demonstrates configuring rollback for all Exceptions. In real applications, choose rollback rules carefully. Do not add an overly broad rule if a checked exception is intended as a skippable error that does not compromise transaction consistency.

## 9. noRollback does not mean safe retry

A fault-tolerant Step can declare exceptions that do not trigger rollback via `noRollback(...)`:

~~~java
return new StepBuilder("importStep", jobRepository)
    .<InputRecord, OutputRecord>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TemporaryBusinessServiceException.class)
    .retryLimit(3)
    .noRollback(TemporaryBusinessServiceException.class)
    .build();
~~~

This configuration is suitable only if the exception does not corrupt the transaction and previously executed operations remain valid. It is not a general way to handle every retryable error.

For deadlocks, serialization failures, or transactions already marked rollback-only, keeping the transaction makes no sense. The database may reject subsequent statements or commit may throw UnexpectedRollbackException.

### When to consider noRollback?

You can consider it when an exception merely signals a condition that does not break the transaction and the application wants to continue within the same transaction boundary. However, verify:

- The resource remains healthy.
- The transaction has not been marked rollback-only.
- No partial changes need undoing.
- Items can be skipped or processed onward consistently.
- Tests prove the final data is accurate.

Never use noRollback to dodge deadlocks or retain partial writes.

## 10. The writer must participate in the Step-managed transaction

Database writers should use APIs that participate in the current transaction, such as JdbcTemplate, NamedParameterJdbcTemplate, Spring Data repositories, or JDBC connections obtained through Spring's management mechanisms.

JdbcBatchItemWriter example:

~~~java
@Bean
JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
        .dataSource(dataSource)
        .sql("""
            INSERT INTO processed_order(order_id, amount)
            VALUES (:orderId, :amount)
            """)
        .beanMapped()
        .build();
}
~~~

When the writer uses the Step's DataSource and transaction manager, JDBC statements can participate in the chunk transaction.

Do not open a separate connection and commit manually inside the writer:

~~~java
public void write(Chunk<? extends Order> chunk) throws Exception {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        // Perform inserts...

        connection.commit();
    }
}
~~~

If the writer commits independently, the Step's transaction cannot roll back those changes. On retry, already-committed data may be written twice or trigger constraint violations.

### Using the same transaction manager

Verify:

- Which transaction manager the Step receives.
- Which DataSource or EntityManagerFactory the transaction manager manages.
- Which resource the writer uses.
- Whether invoked DAOs/services participate in the current transaction.
- Whether any independent connections or unusual propagation settings exist.

If the writer uses a different DataSource, the Step's rollback will not automatically roll back data in that datasource.

## 11. Retry and transaction propagation

Propagation determines whether a called method joins the current transaction or creates another transaction.

### PROPAGATION_REQUIRED

This is the common choice for business write services:

~~~java
@Transactional(propagation = Propagation.REQUIRED)
public void saveOrder(Order order) {
    orderRepository.save(order);
}
~~~

If a chunk transaction is active, the method joins that transaction. When the chunk rolls back, the service's changes also roll back.

### PROPAGATION_REQUIRES_NEW

REQUIRES_NEW creates an independent transaction:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordAttempt(Order order) {
    attemptRepository.save(toAttempt(order));
}
~~~

This audit transaction can commit even when the outer chunk rolls back. That can be useful for recording attempt logs, yet avoid using it for primary business data that must roll back with the chunk.

During retries, an audit event might be written multiple times for the same item. Use an attempt ID or deduplication key to distinguish attempts.

### Transaction marked rollback-only

A service joining a transaction may mark the transaction rollback-only after an exception. Even if an outer layer catches the exception, the transaction still cannot commit. Upon transaction completion, the application may receive UnexpectedRollbackException.

Do not catch an exception and assume the transaction returned to a normal state. If a transaction is rollback-only, the next attempt must run under a valid transaction boundary.

## 12. Retrying the writer can re-invoke write operations

When a writer throws an exception, the framework may retry per policy. With write skips or fault-tolerant processing, the framework may also isolate the offending item by re-invoking the writer with smaller item groups.

Conceptual example:

~~~text
First call:
  write([A, B, C, D]) -> fails at C

Rollback:
  chunk transaction is undone

Error isolation process:
  write([A]) -> success
  write([B]) -> success
  write([C]) -> error
  write([D]) -> success

After skipping C:
  write valid items in appropriate transactions
~~~

This illustrates the isolation process, not a guarantee that every retry invokes the writer in this exact sequence. The framework may use different strategies depending on configuration and exception types.

### Why design an idempotent writer?

If the writer writes to a system that cannot roll back, re-invocations can create duplicate side effects. Even when the database rolls back, an external API may already have processed the request.

Protective measures:

- Unique constraints by business key.
- Upserts when aligned with business rules.
- Stable idempotency keys for APIs.
- Outbox for publishing messages.
- Writing per-batch temporary files and publishing after commit.
- Persisting processing status for reconciliation when responses are ambiguous.

Idempotency must be designed on the target system side when the client cannot know for sure whether an earlier request was processed.

## 13. Retry and side effects outside the transaction

A database rollback cannot automatically undo emails, HTTP requests, sent messages, or files already read by another system.

Example:

1. Writer inserts order into the database.
2. Writer calls notification API.
3. API processes the request, yet the client times out.
4. Database transaction rolls back.
5. Retry invokes the writer again.
6. API receives the request a second time.

If the API lacks idempotency support, the recipient may get two notifications or the system may create two transactions.

### Outbox pattern

One way to coordinate a database and a message broker is writing events to an outbox table in the same transaction as business data:

~~~mermaid
flowchart TD
    A["Chunk writer"] --> B["Database transaction"]
    B --> C["Write order"]
    B --> D["Write outbox event"]
    C --> E["Commit"]
    D --> E
    E --> F["Outbox publisher"]
    F --> G["Message broker"]
~~~

When the chunk commits, both order and outbox event exist together. A separate publisher sends events and can retry. Consumers still need deduplication because the publisher can resend if it misses an acknowledgment.

### Do not emit success notifications before commit

The Processor or ItemProcessListener only knows the processor returned a result. That does not prove the writer committed. Publish notifications after commit or use an outbox.

## 14. Backoff between retry attempts

If retries happen immediately, multiple workers can flood a failing database or service. Backoff gives the target system time to recover.

Exponential backoff example:

~~~java
@Bean
BackOffPolicy retryBackOffPolicy() {
    ExponentialBackOffPolicy policy =
        new ExponentialBackOffPolicy();

    policy.setInitialInterval(500L);
    policy.setMultiplier(2.0);
    policy.setMaxInterval(5000L);

    return policy;
}
~~~

Attach to Step:

~~~java
return new StepBuilder("processOrdersStep", jobRepository)
    .<OrderInput, Order>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .backOffPolicy(retryBackOffPolicy)
    .build();
~~~

The wait interval grows progressively and stays within the configured maximum. Exact backoff policy APIs must match your Spring Retry version.

### Jitter when multiple workers exist

If many partitions retry after a fixed interval, they can call back simultaneously. Randomized or exponential random backoff spreads out retry timestamps.

When calling external APIs, honor Retry-After if supplied by the service. Do not hammer retries when the system is asking you to slow down.

### Calculating total retry time

Total time to process an item can include:

- Timeout of each request.
- Backoff wait time.
- Transaction rollback time.
- Time to acquire a new connection.
- Execution time of the next attempt.

Set timeouts and retry limits compatible with the Job's deadline. Overly long retries can cause workers to hold resources while a service cannot recover.

## 15. Combining retry, skip, and rollback

All three policies can work together:

- Retry transient errors within limits.
- If retries are exhausted, skip if the item is permitted to be discarded.
- If neither retryable nor skippable, the Step fails.
- Roll back per rollback policy to protect transactions.

Example:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
    .<OrderInput, Order>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .skip(InvalidOrderException.class)
    .skipLimit(20)
    .build();
~~~

In this configuration, transient data access errors are retried. InvalidOrderException is skipped if business rules permit. Other errors outside retry or skip policies can fail the Step.

If the same exception is both retryable and skippable, test post-exhaustion behavior. Do not assume all policies share identical ordering or attempt counts across versions.

### Exhausted retries do not mean automatic skip

When retries run out, the framework still evaluates the skip policy. If the exception is not skippable or the skip limit is exceeded, the Step fails.

Retry limit and skip limit are two distinct limits:

| Limit | What does it count? |
|---|---|
| Retry limit | Attempts to re-run an operation under the retry policy |
| Skip limit | Total items permitted to be discarded in the Step |

## 16. Retry in the reader and buffering

When a chunk rolls back, the framework may need to replay already-read items. For typical readers, Spring Batch buffers chunk items so it does not have to re-read the source immediately.

This matters for file readers or cursor readers, because the source position may already have advanced.

With transactional queues, messages can be returned to the queue when the transaction rolls back. In that case, the Step may need:

~~~java
return new StepBuilder("queueStep", jobRepository)
    .<Message, ProcessedMessage>chunk(50, transactionManager)
    .reader(messageReader)
    .processor(messageProcessor)
    .writer(messageWriter)
    .readerIsTransactionalQueue()
    .faultTolerant()
    .retry(TransientMessageException.class)
    .retryLimit(3)
    .build();
~~~

This setting tells Spring Batch the reader consumes from a transactional queue so the framework handles buffering accordingly.

Coordinate acknowledgments with transactions. If the reader acknowledges a message before chunk commit, the database may roll back while the message is already gone from the queue. Retrying cannot recover an item permanently removed by the source.

## 17. Stateful and stateless retry

Retries can maintain attempt-count state in different ways.

**Stateless retry** typically holds the retry context within the current invocation scope. If the operation is called again in another execution, state may reinitialize depending on policy.

**Stateful retry** uses a key to recognize the same logical processing unit across rollbacks and re-invocations. This mechanism helps when an exception rolls back the transaction and the framework must reintroduce the item into processing in a new transaction.

In batch processing, Spring Retry and Spring Batch coordinate retry context with items/chunks and rollbacks. Implementation details vary by version, retry policy, and configuration. Do not assume retry counters automatically survive across all transactions or JobExecutions.

### Choosing stateful or stateless by operation traits

Consider:

- Is the item identified by a stable key?
- Does the transaction roll back between attempts?
- Is the item replayed by the reader?
- Across which re-invocations must the retry context survive?
- Could two items share equals/hashCode while being distinct business records?

If stateful retry is needed for items, the identifying key must distinguish logical items accurately. Avoid using mutable objects as keys if fields affecting hashCode mutate during processing.

## 18. Retry and restart operate at different scopes

Retry happens while a Step is running. Restart happens after a JobExecution ends in failure or stops and needs a new JobExecution for the same JobInstance.

| Mechanism | Scope | When used |
|---|---|---|
| Retry | An operation or item in a running Step | Transient error recoverable quickly |
| Rollback | Current transaction | Undo partial changes before trying again |
| Skip | Faulty item in a running Step | Item permitted to be discarded |
| Restart | New JobExecution | Job failed or stopped after retries were insufficient |
| New JobInstance | A fresh logical run | Different batch ID or identifying parameters |

Example:

~~~text
Chunk 1: committed successfully
Chunk 2: writer deadlock -> rollback -> retry succeeded
Chunk 3: committed successfully
Job: COMPLETED
~~~

No restart is needed because retry recovered within the same JobExecution.

If chunk 2 exhausts retries and the Step fails:

~~~text
Chunk 1: committed successfully
Chunk 2: rollback -> retry exhausted -> Step FAILED
Restart same JobInstance after fixing issue
Chunk 2 reprocessed from checkpoint
~~~

Restart requires a recoverable reader and a writer safe under replay.

## 19. Monitoring retry and rollback

StepExecution provides counters such as:

| Attribute | Meaning |
|---|---|
| readCount | Items returned by reader |
| writeCount | Items written by writer |
| filterCount | Items filtered by processor |
| readSkipCount | Read errors skipped |
| processSkipCount | Process errors skipped |
| writeSkipCount | Write errors skipped |
| commitCount | Number of commits |
| rollbackCount | Number of rollbacks |

There is no single StepExecution counter representing all retry attempts. If you need retry counts, instrument retry listeners or metrics at the appropriate retry/client layer.

Monitor:

- Retry attempts by exception type.
- Successful retry count.
- Items exhausting retries.
- Rollbacks by Step and partition.
- Backoff wait times.
- Total processing time per item across attempts.
- Items ultimately skipped.
- Error rates by database or target service.

### Successful retries can still be a warning sign

A Job can finish COMPLETED even though thousands of operations had to retry. That can signal an overloaded database, lock contention, or an unstable external service.

Set alert thresholds on retry rates and rollback counts. Do not inspect only the final Job status.

## 20. Testing retry with rollback

Tests must verify both attempt counts and post-transaction data state.

### Testing simulated writer deadlock followed by success

Create a test writer or mock repository that throws a retryable exception on the first call and succeeds on the next.

Expectations:

1. First write fails.
2. Transaction rolls back per policy.
3. Retry policy permits retrying.
4. Next attempt writes successfully.
5. Chunk commits.
6. No duplicate data or partial changes remain.

Illustrative simulation logic:

~~~java
AtomicInteger attempts = new AtomicInteger();

ItemWriter<Order> writer = chunk -> {
    if (attempts.incrementAndGet() == 1) {
        throw new DeadlockLoserDataAccessException(
            "Simulated deadlock"
        );
    }

    orderRepository.saveAll(chunk.getItems());
};
~~~

This snippet illustrates the first write failing and the next succeeding. Integration tests should use a real transaction manager and test database to verify actual rollbacks.

### Testing retry exhaustion

Have the writer always throw a retryable exception. Confirm:

- Invocation count matches policy limits.
- Failed transaction rolls back.
- Step ends FAILED if exception is not skipped.
- Previously committed chunks remain.
- No partial data exists from the failed chunk.

### Testing noRollback

Configure a noRollback exception in a scenario where continuing safely is valid. Confirm the transaction stays valid and final data is accurate. Do not rely on tests that only mock the transaction manager to conclude the database did not roll back.

### Testing rollback-only transactions

Create a service joining the transaction that marks it rollback-only. Catch the exception in an outer caller and try committing. Confirm the application sees UnexpectedRollbackException and does not treat a subsequent call inside the same transaction as a clean retry.

### Testing side effects outside the transaction

Simulate an API accepting the request while the client times out. On retry, confirm the same idempotency key is sent and the target system creates only one logical operation.

### Testing restart after retry exhaustion

Let the Step fail after exhausting retries, then restart the same JobInstance. Confirm the reader restores checkpoints, committed chunks are not rewritten, and the writer safely handles the uncommitted portion.

## 21. Common design mistakes

### Retrying inside a rollback-only transaction

A transaction marked rollback-only cannot become a clean transaction simply by calling a method again. Let the framework roll back and run the next attempt under a valid transaction boundary.

### Retrying without rolling back database errors

Deadlocks or serialization failures usually require ending the current transaction. Do not keep a broken transaction alive and keep writing.

### Rolling back while the writer commits its own connection

An independently committed connection is outside the chunk transaction. Step rollback cannot undo those changes.

### Retrying all Exceptions

Data errors, broken SQL, and permission errors do not vanish on retry. Retry only recoverable exceptions.

### Using noRollback for severe transaction failures

noRollback does not repair a broken or rollback-only transaction. Misconfiguration can leave partial changes committed.

### Duplicate side effects during retry

Emails, messages, or API requests may have succeeded despite client timeouts. Use idempotency keys, outboxes, or deduplication.

### Catching exceptions and returning dummy results

If a writer or processor swallows exceptions, the retry policy never knows the operation failed. Throw exceptions with clear semantics.

### Skipping real rollback testing

A mock writer does not prove the database rolled back changes. Run integration tests with a suitable transaction manager and database.

### Raising retry limits to mask infrastructure faults

Frequent retries can prolong the Job and increase load. If a service cannot recover, fail the Step and investigate root causes.

### Confusing retry with restart

Retry is an attempt within the current execution; restart is a new JobExecution. Monitor and design the two mechanisms separately.

## 22. Process for designing retry with transaction rollback

When adding retry to a Step, follow this sequence:

1. **Identify failure points:** reader, processor, writer, or external service.
2. **Classify exceptions:** transient, data error, or configuration error.
3. **Choose retry policy:** allow retrying only recoverable exceptions.
4. **Define rollback rules:** decide which transactions must roll back when exceptions occur.
5. **Verify transaction manager:** ensure writers and DAOs use the right managed resources.
6. **Set retry limit:** account for request timeouts and total Job runtime.
7. **Configure backoff:** use fixed, exponential, or jitter based on system load.
8. **Verify replay:** determine which items/chunks may be re-invoked and how the reader recovers.
9. **Design idempotency:** protect writers and external side effects.
10. **Combine skip/fail:** decide the outcome when retries are exhausted.
11. **Monitor:** track retry attempts, rollback counts, exhausted retries, and processing time.
12. **Test:** confirm real rollbacks, retry success, retry exhaustion, skips, and restarts.

A decision matrix aligns the team on policies:

| Error type | Retry | Rollback | Outcome when retries exhausted |
|---|---|---|---|
| Database deadlock | Yes, bounded | Yes | Fail or restart |
| Lock timeout | Yes, bounded | Usually yes | Fail or skip if permitted item error |
| HTTP 503 | Yes, backoff | Per chunk transaction and side effects | Fail or route to recovery flow |
| Validation error | No | Per phase and rollback rules | Skip or fail |
| Misconfigured SQL | No | Usually yes if transaction erred | Fail |
| Invalid API request | No | Cannot roll back external effects if already applied | Reject or fail |

## 23. Key points to remember

- Retry decides whether to re-attempt an operation; rollback decides whether to undo the current transaction.
- The two policies are independent and must be designed together.
- A chunk transaction wraps work for a group of items; previously committed chunks do not roll back when a later chunk fails.
- Database errors like deadlocks typically require rolling back the transaction before retrying.
- Retry policies should accept only recoverable exceptions.
- Rollback rules and retry policies are not the same configuration.
- noRollback does not restore a rollback-only transaction to healthy state and does not enable retry.
- Writers must use resources participating in the Step's transaction manager, never committing separate connections manually.
- Processors and writers can be re-invoked; side effects must be idempotent or decoupled from the main flow.
- Backoff and jitter relieve load when multiple workers retry simultaneously.
- Skip applies only if business rules allow discarding the item after retries run out.
- Retry is not restart; restart uses a new JobExecution and relies on checkpoints.
- Track retry attempts separately from rollbackCount and skip counts.
- Test with real transactions to verify rollback, replay, retry success, and retry exhaustion.

When retry coordinates properly with rollback, Spring Batch can recover from transient errors while preserving data consistency. The key conditions are that the transaction must be in a valid state before a new attempt, the writer must enlist with the right transaction manager, and any repeatable side effects must be protected against duplication.

