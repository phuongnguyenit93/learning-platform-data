# Writer Order and Single Writer Failure

In Spring Batch, CompositeItemWriter allows a chunk to be written to multiple targets by combining multiple ItemWriter delegates. Delegates are invoked sequentially in the configured order. If a delegate throws an exception, the composite stops at that delegate, does not invoke subsequent delegates in the current invocation, and propagates the exception back to the Step.

Call order does not automatically create a shared transaction across all systems. If delegates write to the same database and participate in the chunk transaction, an error can roll back earlier database changes. If a delegate already sent an HTTP request, published a message, or wrote to a non-transactional resource, that side effect may remain even if the chunk rolls back.

When designing a composite writer, determine:

- Which delegate runs first and why.
- Whether each delegate receives the whole chunk or a separate subset of items.
- Which delegate failure will prevent later delegates from running.
- Whether delegates participate in the same transaction.
- On retry or write skip, which delegates will be invoked again.
- Which side effects require idempotency, an outbox, or reconciliation.

## 1. What Is CompositeItemWriter?

CompositeItemWriter is an ItemWriter that coordinates multiple other ItemWriters. When the Step calls write(chunk), the composite calls write(chunk) on each delegate in turn in the configured order.

For example, a Job needs to write orders to a database, write an audit record, and generate an output file:

~~~text
Step
 |
 v
CompositeItemWriter
 |
 +--> DatabaseOrderWriter
 |
 +--> AuditOrderWriter
 |
 +--> OrderFileWriter
~~~

Each delegate has a distinct write responsibility. The composite combines them into a single writer to register on the Step.

CompositeItemWriter does not split a chunk into different item groups per delegate on its own. By default, every delegate receives the same input chunk. If one target needs a different data type or only a filtered subset of items, use an intentional adapter/decorator writer or design a separate pipeline.

## 2. Where Is Delegate Order Determined?

The order is the order in which delegates are passed to CompositeItemWriterBuilder or the list configured on CompositeItemWriter.

~~~java
@Bean
public CompositeItemWriter<Order> orderCompositeWriter(
        ItemWriter<Order> databaseOrderWriter,
        ItemWriter<Order> auditOrderWriter,
        ItemWriter<Order> fileOrderWriter) {

    return new CompositeItemWriterBuilder<Order>()
            .delegates(
                    databaseOrderWriter,
                    auditOrderWriter,
                    fileOrderWriter)
            .build();
}
~~~

When the Step calls the writer, the sequence is:

1. databaseOrderWriter.write(chunk)
2. auditOrderWriter.write(chunk)
3. fileOrderWriter.write(chunk)

The composite invokes delegates sequentially, not in parallel. The second delegate only starts after the first delegate returns normally.

Configured order is part of application behavior. Changing delegate positions can alter which side effect happens before an error is detected. Therefore, changing writer order should be treated as a processing logic change, covered by tests for failure scenarios.

## 3. Every Delegate Receives the Same Chunk

Suppose a chunk has three orders A, B, and C:

~~~text
Chunk = [A, B, C]
          |
          v
DatabaseWriter.write([A, B, C])
          |
          v
AuditWriter.write([A, B, C])
          |
          v
FileWriter.write([A, B, C])
~~~

Each delegate is invoked once per chunk and receives the same list of items in terms of content. Delegates may perform batch inserts, file writes, or calls to external systems.

The composite does not by default send A through all delegates before moving to B. Instead, it calls each delegate with the whole chunk. This matters when analyzing partial failures: the database writer may have processed all of A, B, and C before the audit writer even begins.

Do not let a delegate mutate objects in the chunk in a way that changes the data seen by a later delegate. Treat items passed to writers as prepared, immutable data. If transformations are needed, create new objects in a processor or a dedicated adapter.

## 4. What Happens When One Writer Throws an Exception?

Suppose the order is DatabaseWriter, AuditWriter, and FileWriter. AuditWriter throws an exception:

~~~text
Step calls CompositeItemWriter
          |
          v
DatabaseWriter.write(chunk)
          |
          | returns normally
          v
AuditWriter.write(chunk)
          |
          | throws exception
          v
Composite stops
          |
          +--> FileWriter is not called
          |
          v
Exception propagates to Step
          |
          v
Rollback / Retry / Skip / Fail
~~~

The composite does not catch errors and keep calling remaining delegates. When one delegate throws an exception, the delegate loop terminates and the exception exits write().

Consequently:

- Delegates before the error were already invoked.
- The failing delegate was invoked but did not finish normally.
- Delegates after the error were not invoked in that composite invocation.
- The Step receives the exception and handles it per transaction/fault-tolerance settings.

Do not assume that one delegate throwing an error makes the composite automatically roll back earlier delegates. Rollback depends on the resources and transactions used by those delegates.

## 5. Outcome Table by Failing Writer Position

Suppose there are three delegates in order A, B, C:

| Failing Delegate | A | B | C |
|---|---|---|---|
| A throws error | May have partially written | Not called | Not called |
| B throws error | Returned normally | May have partially written | Not called |
| C throws error | Returned normally | Returned normally | May have partially written |
| No error | Completed | Completed | Completed |

This table only describes delegate invocations. It does not conclude whether data remains after the transaction ends.

If A, B, and C share a database transaction and the transaction rolls back, database changes within the transaction can be undone. If A is an HTTP API or a file writer not participating in the transaction, A's changes may persist.

## 6. The Chunk Transaction Wraps the Composite Writer

In a chunk-oriented Step, Spring Batch manages the chunk transaction. The writer is invoked during chunk processing before the transaction commits.

~~~text
Begin chunk transaction
       |
       v
Read / process items
       |
       v
CompositeItemWriter.write(chunk)
       |
       +--> Delegate A
       +--> Delegate B
       +--> Delegate C
       |
       v
Update stream state
       |
       v
Commit transaction
~~~

If an exception arises and is classified by the transaction policy as requiring rollback, the chunk transaction is rolled back. Default Spring transactions usually roll back on RuntimeException and Error; checked exceptions must be evaluated against the rollback rules of the active transaction attribute.

Therefore, seeing an exception exit the writer is not enough to conclude rollback always happens. Check the exception type, transaction attribute, and Step rollback classification.

If a writer catches an exception and returns normally, the Step may proceed to commit as though writing succeeded. Do not swallow write errors unless there is an explicit handling policy and output state has been updated consistently.

## 7. When All Delegates Write in the Same Database Transaction

If multiple delegates write to the same database and participate in the Step's transaction, a failure in a later delegate can roll back changes made by an earlier delegate.

For example:

- DatabaseOrderWriter uses JdbcTemplate with the Step's DataSource.
- AuditOrderWriter uses the same DataSource and transaction manager.
- Neither commits independently on its own.
- AuditOrderWriter throws a RuntimeException.

Expected outcome:

~~~text
Transaction T begins
   |
   +--> INSERT orders
   |
   +--> INSERT order_audit
   |        |
   |        +--> error
   |
   v
ROLLBACK T
   |
   +--> orders no longer contains chunk changes
   +--> order_audit no longer contains chunk changes
~~~

The key condition is that both operations genuinely participate in the same transaction. Sharing a database server is not enough if each delegate acquires its own connection and commits separately.

Spring JDBC components normally participate in the current transaction when configured with the properly managed DataSource. Verify the DataSource, transaction manager, and transaction propagation of services invoked by the writer.

## 8. When a Delegate Uses a Separate Transaction

A delegate may use REQUIRES_NEW propagation or open its own connection and commit independently. In that case, the delegate's transaction may finish before the outer chunk transaction ends.

~~~text
Chunk transaction T1 begins
        |
        v
Delegate A calls REQUIRES_NEW service
        |
        v
Transaction T2 commits successfully
        |
        v
Delegate B throws exception
        |
        v
T1 rolls back
        |
        v
A's changes in T2 remain
~~~

This situation breaks the assumption that one writer failing rolls back all earlier writes.

Do not use REQUIRES_NEW on a delegate merely to separate services. Decide explicitly whether that data must commit independently or roll back with the chunk. If all-or-nothing within the same database is required, delegates should join the Step's transaction instead of committing on their own.

## 9. When Delegates Write to Multiple Resource Types

A composite can combine diverse targets:

- Database.
- File.
- HTTP API.
- Message broker.
- Object storage.
- Search index.
- External audit system.

A local database transaction manager does not automatically roll back external systems. For example, once an API receives a request or a broker accepts a message, a database rollback cannot retract that request or message.

~~~text
CompositeItemWriter
      |
      +--> Database: participates in transaction T
      |
      +--> HTTP API: external system
      |
      +--> Message broker: separate transaction
~~~

If the third delegate fails, the database may roll back, yet the API or broker may still retain its side effect. This is a cross-resource consistency issue, not a bug specific to CompositeItemWriter.

Writer order only determines which side effect is attempted first. It does not create a distributed atomic commit.

## 10. How to Choose Writer Order

There is no single right order for every application. Consider the dependencies and reversibility of each delegate.

Guidelines:

- Place checks or operations prone to early failure before irreversible side effects, provided they do not depend on written data.
- Group database writes requiring atomicity into the same transaction.
- Avoid sending messages or calling non-idempotent APIs before business data is confirmed.
- Use an outbox to decouple database commit from external publishing.
- Ensure later delegates can re-run safely after rollback/retry.
- Document dependencies between delegates in configuration and tests.

Example order:

~~~text
Validate / prepare
       |
       v
Database business write
       |
       v
Database outbox write
       |
       v
Commit chunk
       |
       v
Outbox publisher sends event
~~~

This model is usually easier to recover than calling APIs directly inside the same CompositeItemWriter. Events are only published after the business transaction commits, and the outbox worker can retry independently.

If an audit record must commit alongside the business record, write the audit in the same database transaction. If the audit target is an external system, use an outbox or an idempotent delivery mechanism.

## 11. Order Does Not Replace Dependency Management

Suppose FileWriter needs an ID generated by DatabaseWriter. If DatabaseWriter runs first but generates the ID inside an uncommitted transaction, FileWriter may still use the ID returned via the object or repository depending on implementation. However, if FileWriter queries the database over a separate connection, it may not see uncommitted data yet.

Do not rely on delegate order to guarantee a later writer sees uncommitted changes made by an earlier writer on a different resource. Verify transaction isolation, connections, and data passed directly through items.

If delegate B needs a result produced by A, clearer approaches are:

- Have a processor prepare the needed value before the writer.
- Have A update the object under an explicit contract if design permits.
- Use a shared service to generate data before the composite.
- Split into a subsequent Step if B must read committed data.

Avoid letting writers depend implicitly on side effects of preceding writers without tests covering transaction visibility.

## 12. Retry Calls the Composite from the Beginning

When a writer fails and the Step is configured to retry, Spring Batch may retry the chunk. The retry call goes through CompositeItemWriter again, starting from the first delegate.

First attempt example:

~~~text
A.write(chunk) -> succeeded
B.write(chunk) -> succeeded
C.write(chunk) -> transient error
~~~

Retry attempt:

~~~text
A.write(chunk) -> called again
B.write(chunk) -> called again
C.write(chunk) -> called again
~~~

The composite does not maintain a cursor saying it already reached delegate C so that a retry would only rerun C. Therefore, A and B can be invoked again even though they returned normally on the prior attempt.

If A or B performs non-transactional side effects, retries can create duplicates. This is why every delegate must be evaluated for idempotency and transaction participation.

## 13. Retry Policy for Delegate Failures

Retries can be configured for transient exceptions:

~~~java
@Bean
public Step exportOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemWriter<Order> compositeWriter) {

    return new StepBuilder("exportOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(compositeWriter)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .build();
}
~~~

In the example, the Step retries transient errors up to the configured retry limit. Check the actual exception thrown or wrapped by delegates.

Retry fits deadlocks, brief connection drops, or service errors known to be transient. Do not endlessly retry validation errors, bad SQL, schema mismatches, or configuration errors.

On retry, the chunk transaction is typically rolled back per rollback policy before the next attempt runs. If a delegate wrote outside the transaction, retry does not automatically retract the earlier side effect.

## 14. Write Skip and the Composite Writer

Write skip can cause Spring Batch to re-invoke the writer with smaller subsets of items to isolate the offending item. Because the composite writer is the Step's writer, its delegates can be re-invoked while isolating the failing item.

Initial chunk example:

~~~text
[A, B, C, D]
~~~

If the write error originates from B, the framework may retry with subsets or single items depending on fault-tolerance and writer mechanics. Every time the composite is invoked, it runs delegates in the configured order again.

This means:

- Delegate A may receive the original chunk multiple times.
- Delegate B may receive subsets during error isolation.
- Delegate C is only called if earlier delegates in that invocation return normally.
- A side effect may repeat even if the item is ultimately skipped.

Not every writer supports isolating faulty items safely. If a delegate sends a batch request to an API that only returns a generic error, the framework may not know which item caused the failure. Test write skip with the real composite and only configure skip for classifiable errors.

## 15. Idempotency of Each Delegate

Idempotency means repeating the same operation produces no extra unintended effects.

Example database upsert by business key:

~~~sql
INSERT INTO order_export(order_id, status)
VALUES (:orderId, :status)
ON CONFLICT (order_id)
DO UPDATE SET status = EXCLUDED.status
~~~

This statement illustrates an upsert by unique key; exact syntax depends on the database.

For HTTP APIs, use a stable idempotency key per business operation, such as order ID plus event type. For message brokers, use an event ID with consumer deduplication. For files, use a dedicated output path per JobExecution or write to staging in a recoverable way.

Idempotency must be designed for every delegate. Making only the first writer idempotent is not enough if the second or third writer still creates duplicate side effects.

## 16. Transactional Outbox When the Composite Includes an API or Broker

If a Job needs to persist database data and notify another system, a transactional outbox keeps the first two consistent within one transaction.

~~~text
Composite writer in chunk
       |
       +--> OrderRepository writes order
       |
       +--> OutboxRepository writes event
       |
       v
Chunk transaction COMMIT
       |
       v
Outbox publisher reads event
       |
       v
HTTP API / Message broker
       |
       v
Mark event as sent
~~~

If the chunk rolls back, the order and outbox event roll back together. If the chunk commits and the application stops, the event stays in the outbox for the publisher to process later.

The outbox publisher can still resend an event if an acknowledgment is lost or a crash occurs between sending and updating status. Thus, the target system still needs idempotency by event ID or deduplication.

With this pattern, CompositeItemWriter may only need to write database resources inside the Step's transaction. Calling external systems is handled in a separate worker with independent retries and monitoring.

## 17. File Writers in a Composite

FlatFileItemWriter is commonly used with CompositeItemWriter. Spring Batch's standard writer supports transaction-aware buffering and ItemStream state when properly configured. This helps coordinate file writes with Step transactions and supports restart.

However, do not generalize that behavior to every custom file writer.

A custom writer using Files.writeString(), FileOutputStream, or direct appending can leave written data behind when a chunk rolls back. If the composite retries, the file may contain duplicates.

When using a file delegate:

- Prefer FlatFileItemWriter or a writer with clear transaction/restart semantics.
- Use a stable writer name and saveState when restart is required.
- Keep output resources stable across restarts.
- Do not let consumers read files while they are still being written.
- Consider staging and publishing after Job completion.
- Check behavior when a later delegate fails.

If the file is a final output requiring publication, a final Step can rename the staging file after all data-writing Steps succeed.

## 18. ItemStream Lifecycle of Delegates

Some writers implement ItemStream to open resources, save state, and close resources. CompositeItemWriter also supports lifecycle callbacks to manage stream delegates per configuration.

With default configuration, CompositeItemWriter can forward open, update, and close to delegates implementing ItemStream. The builder has an ignoreItemStream option in supported versions; enabling it means the composite does not forward lifecycle callbacks to delegates automatically.

Ensure every ItemStream delegate is registered and its lifecycle is invoked exactly once as designed. If a delegate misses open(), a file writer may not have opened its resource; if it misses update(), checkpoints may not be saved; if it misses close(), resources can leak.

Example composite configuration with delegates:

~~~java
@Bean
public CompositeItemWriter<Order> orderCompositeWriter(
        FlatFileItemWriter<Order> fileWriter,
        JdbcBatchItemWriter<Order> databaseWriter) {

    return new CompositeItemWriterBuilder<Order>()
            .delegates(databaseWriter, fileWriter)
            .build();
}
~~~

With stateful delegates, check your API version and how the composite registers ItemStreams. If wrappers are nested or delegates are instantiated inside custom components, you may need to register streams explicitly on the Step via stream(...). Avoid registering the same stream twice if the composite already manages it.

## 19. Do Not Let a Writer Mask Errors

A delegate should not catch an exception and return normally if the write operation failed.

Unsafe example:

~~~java
public void write(Chunk<? extends Order> chunk) {
    try {
        externalClient.send(chunk.getItems());
    } catch (Exception exception) {
        log.error("External write failed", exception);
        // Returns normally.
    }
}
~~~

The composite will treat this delegate as complete and continue calling later delegates. The Step may commit the chunk even though the external write failed.

A better approach is propagating the exception:

~~~java
public void write(Chunk<? extends Order> chunk) throws Exception {
    externalClient.send(chunk.getItems());
}
~~~

If translating exceptions, preserve the cause and use a meaningful exception type so retry/skip classifiers can categorize it.

If business rules allow tolerating failure on one target, persist the error status durably and establish a separate retry/repair process. Do not turn failures into log-only handling and report the chunk as successful.

## 20. noRollback Does Not Fix Partial Side Effects

Exceptions can be configured not to roll back a transaction using noRollback or an equivalent rollback classifier. However, this does not turn multiple delegates into an atomic transaction.

If DatabaseWriter already wrote data and FileWriter throws an exception classified as no-rollback, the transaction can commit the database portion even though the file was not completely written. This is usually an undesirable state.

Only use noRollback when business logic truly wants to keep transaction changes despite that exception and writers can continue consistently. For a single delegate write failure, the default should normally roll back the chunk or use a separate recovery workflow.

Do not use noRollback solely to avoid re-invoking an earlier delegate. That can hide incomplete data and advance checkpoints even when a target never received the data.

## 21. Example of Failure in the Second Delegate

Suppose a composite has three writers:

~~~java
@Bean
public CompositeItemWriter<Order> compositeWriter(
        ItemWriter<Order> databaseWriter,
        ItemWriter<Order> auditWriter,
        ItemWriter<Order> notificationWriter) {

    return new CompositeItemWriterBuilder<Order>()
            .delegates(
                    databaseWriter,
                    auditWriter,
                    notificationWriter)
            .build();
}
~~~

AuditWriter throws an exception after databaseWriter returns:

~~~text
Chunk transaction T begins
       |
       v
databaseWriter.write(chunk)
       |
       | insert order in T
       v
auditWriter.write(chunk)
       |
       | error
       v
notificationWriter is not called
       |
       v
Exception exits composite
       |
       v
T rolls back if exception is classified for rollback
       |
       v
Order insert in T is rolled back
~~~

If databaseWriter committed in its own separate transaction, order data may remain. If auditWriter wrote partially to an external system before throwing, that side effect may also remain.

To test this properly, use real database transactions or test doubles with clear semantics rather than only mocking the composite and asserting an exception was thrown.

## 22. Example Tracking Delegate Call Order

Test doubles can be used to verify order:

~~~java
@Test
void invokesDelegatesInConfiguredOrder() throws Exception {
    List<String> calls = new ArrayList<>();

    ItemWriter<Order> first = chunk -> calls.add("first");
    ItemWriter<Order> second = chunk -> calls.add("second");
    ItemWriter<Order> third = chunk -> calls.add("third");

    CompositeItemWriter<Order> composite =
            new CompositeItemWriterBuilder<Order>()
                    .delegates(first, second, third)
                    .build();

    composite.write(new Chunk<>(List.of(new Order())));

    assertEquals(
            List.of("first", "second", "third"),
            calls);
}
~~~

This test verifies the composite calls delegates in the configured order. It does not test transactions or rollbacks.

Add a test for when the second delegate throws an exception:

~~~java
@Test
void stopsCallingDelegatesAfterFailure() {
    List<String> calls = new ArrayList<>();

    ItemWriter<Order> first = chunk -> calls.add("first");

    ItemWriter<Order> failing = chunk -> {
        calls.add("failing");
        throw new IllegalStateException("write failed");
    };

    ItemWriter<Order> third = chunk -> calls.add("third");

    CompositeItemWriter<Order> composite =
            new CompositeItemWriterBuilder<Order>()
                    .delegates(first, failing, third)
                    .build();

    assertThrows(
            IllegalStateException.class,
            () -> composite.write(
                    new Chunk<>(List.of(new Order()))));

    assertEquals(List.of("first", "failing"), calls);
}
~~~

In real tests, use your project's valid item model. The key assertion is that the third delegate is not invoked after the second delegate throws an exception.

## 23. Testing Rollback Across Multiple Database Delegates

An integration test should verify that writers sharing a transaction truly roll back together.

Scenario:

1. DatabaseWriter inserts order.
2. AuditWriter inserts audit record and then throws RuntimeException.
3. NotificationWriter is not called.
4. Step rolls back the chunk transaction.
5. Query the database in an independent transaction.
6. Confirm neither the order nor the audit record from the chunk remains.

Test conditions:

- Writers use the same managed DataSource.
- The same transaction manager is passed to the Step.
- No REQUIRES_NEW or manual commits exist.
- The exception escapes and is handled by the rollback policy.
- Do not wrap the test in an outer transaction that distorts observation.

If a test only uses mock repositories, it does not prove the transaction manager rolled back the database.

## 24. Testing External Side Effects

For APIs or brokers, demonstrate that non-transactional side effects can persist after rollback.

Example:

~~~text
Delegate A: API call succeeded
Delegate B: database write then throws error
Chunk transaction: rollback
API: request was still received
~~~

Tests can use a mock server or broker test container:

- Verify the API received the request before the later delegate failed.
- Verify the database rolled back.
- Run a retry or restart.
- Verify the idempotency key prevents the request from creating duplicate effects.

If using an outbox, separately test that transaction rollback produces no outbox event and transaction commit produces one logical event. Then test publisher retries and consumer deduplication.

## 25. Testing ItemStream Delegates

If delegates hold state, test the lifecycle:

- open() is called when the Step starts.
- update() is called at checkpoints.
- close() is called when the Step ends.
- State is persisted in ExecutionContext.
- Restart restores the proper position or output state.
- One delegate throwing an error does not leave other resources uncleaned.

With nested composites, verify streams are registered properly. If ignoreItemStream is enabled, there must be a separate mechanism registering delegate streams; otherwise readers/writers may fail to restore state.

Do not merely check that a file was written. Restart a test Step and verify data is neither duplicated nor lost.

## 26. Monitoring Errors per Delegate

A Step's ItemWriteListener observes write calls on the writer registered on the Step. When a Step uses CompositeItemWriter, the Step-level listener typically sees the composite invocation without automatically identifying the exact internal delegate that failed.

Each delegate can be wrapped to record dedicated logs or metrics:

~~~java
public class ObservedOrderWriter implements ItemWriter<Order> {

    private final String writerName;
    private final ItemWriter<Order> delegate;

    public ObservedOrderWriter(
            String writerName,
            ItemWriter<Order> delegate) {
        this.writerName = writerName;
        this.delegate = delegate;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) throws Exception {
        try {
            delegate.write(chunk);
        } catch (Exception exception) {
            log.error(
                    "Delegate {} failed for {} items",
                    writerName,
                    chunk.size(),
                    exception);
            throw exception;
        }
    }
}
~~~

The wrapper must rethrow the exception so Spring Batch still applies rollback/retry/skip. Do not log full payloads if data is sensitive.

Metrics should record:

- Delegate name.
- Invocation count.
- Number of items in the chunk.
- Execution duration.
- Error count by exception type.
- JobExecution and StepExecution IDs.
- Appropriate business key or correlation ID.

These metrics distinguish errors in the database writer, audit writer, or file writer rather than merely reporting CompositeItemWriter failed.

## 27. Nested Composite Writers

A delegate may itself be another CompositeItemWriter. In that case, the effective execution order is a depth-first traversal across layers.

~~~text
OuterComposite
    |
    +--> DatabaseWriter
    |
    +--> InnerComposite
            |
            +--> AuditWriter
            |
            +--> FileWriter
    |
    +--> MetricsWriter
~~~

If AuditWriter fails, FileWriter in the inner composite and MetricsWriter in the outer composite are not invoked in that call. DatabaseWriter was already invoked earlier.

Nesting can help group targets by responsibility, though it makes order and failure paths harder to trace. Keep the structure simple, give delegates clear names, and test failures at every layer.

Do not create multiple composite layers just to group beans without clear business or lifecycle boundaries.

## 28. Delegates Must Accept Compatible Data Types

CompositeItemWriter<T> sends the same Chunk of T to delegates. If one target needs Order and another needs AuditEvent, an adapter writer can convert each Order into an AuditEvent.

~~~java
public class OrderAuditWriter implements ItemWriter<Order> {

    private final ItemWriter<AuditEvent> auditWriter;

    public OrderAuditWriter(ItemWriter<AuditEvent> auditWriter) {
        this.auditWriter = auditWriter;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) throws Exception {
        List<AuditEvent> events = chunk.getItems().stream()
                .map(order -> new AuditEvent(
                        order.id(),
                        "ORDER_EXPORTED"))
                .toList();

        auditWriter.write(new Chunk<>(events));
    }
}
~~~

The adapter makes type conversion explicit and keeps the composite working with Order. Ensure the adapter neither drops items nor alters order unintentionally.

If targets require data assembled from completely different sources, separate Steps or an event-driven pipeline may be clearer than a composite packed with complex adapters.

## 29. Later Writers May Not Run and Data Needs Reconciliation

When a delegate fails, later delegates are not called during that composite invocation. If the error is not retried or the Step fails, the system must know which targets received data and which did not.

Do not rely solely on logs to reconstruct state across multi-resource systems. Maintain a business key, event ID, or export batch ID for reconciliation.

A status table can track:

| Target | Status |
|---|---|
| Database | COMMITTED / ROLLED_BACK |
| Audit store | PENDING / SENT / FAILED |
| File output | STAGING / PUBLISHED / FAILED |
| External API | PENDING / ACKNOWLEDGED / UNKNOWN |

Particularly with timeouts, an UNKNOWN status can occur: the client does not know whether the external system received the request. In that case, query by idempotency key or reconcile by business key before resending.

## 30. Common Mistakes

### Thinking the Composite Runs Delegates in Parallel

The composite calls them sequentially in configured order. A later delegate only runs when the preceding delegate returns normally.

### Thinking One Writer Failing Automatically Rolls Back All Earlier Writers

Rollback only applies to resources participating in a rollback-capable transaction. APIs, message brokers, or independent transactions may retain side effects.

### Thinking Retry Only Reruns the Failing Delegate

Retry re-invokes the composite for the chunk, so earlier delegates can be called again. Design idempotency for every delegate.

### Thinking Later Delegates Still Run After an Exception

An exception stops the call chain. If you want to proceed despite an error, you need an explicit error-recording policy and a clear decision on whether the chunk should commit.

### Catching Exceptions and Only Logging

The composite treats the delegate as complete and may continue. Exceptions must be propagated outward if the write actually failed.

### Using REQUIRES_NEW While Still Expecting Rollback with the Chunk

An independent committed transaction is not rolled back by the chunk transaction. Define propagation explicitly.

### Changing Delegate Order Without Testing

Side effects and failure paths change. Write tests verifying order and failures at each position.

### Using Non-Idempotent Writers Under Retry/Skip

Delegates can be re-invoked with the same chunk or subsets. Use unique keys, idempotency keys, outboxes, or staging.

### Ignoring ItemStream Lifecycle

Delegates fail to open, update state, or close resources properly. Ensure streams are managed by the composite or registered separately.

### Using noRollback to Keep Partially Written Data

Partial outputs can commit while another delegate fails. Only use it when post-commit states have been proven valid.

### Failing to Verify the Actual Transaction Manager

Two writers targeting the same database via different connections or transactions may not roll back together. Verify DataSource, propagation, and transaction manager.

## 31. Workflow for Designing a Composite Writer

Before combining multiple writers into a Step, determine:

1. Which resource does each delegate write to?
2. What business dependencies govern invocation order?
3. Does each delegate take the same chunk or need a subset/separate transformation?
4. Which delegates can throw exceptions and of what types?
5. Do exceptions propagate out of the composite?
6. Do database delegates participate in the same Step transaction?
7. Does any delegate use REQUIRES_NEW or self-commit?
8. Can non-transactional resources retain side effects after rollback?
9. Which delegates will retry re-invoke?
10. How might write skip call the writer with chunk subsets?
11. Is each delegate idempotent?
12. Are an outbox, idempotency keys, or reconciliation needed?
13. Where is the delegates' ItemStream lifecycle managed?
14. Do metrics/logs pinpoint exactly which delegate failed?
15. Do integration tests verify rollback, retry, skip, and external side effects?

CompositeItemWriter executes delegates sequentially in configured order and stops immediately when a delegate throws an exception. The Step then applies transaction and fault-tolerance policies to the overall writer call. Changes within the same transaction can roll back together, whereas side effects in independent resources may persist and earlier delegates can be re-invoked on retry or write skip. Design order based on dependencies, keep database writes requiring atomicity in the same transaction, use idempotency/outbox for external systems, and test failures at every delegate position so the Job can recover without creating duplicates or inconsistent state.
