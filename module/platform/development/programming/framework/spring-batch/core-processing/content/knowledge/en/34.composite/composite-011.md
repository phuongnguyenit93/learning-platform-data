# Rolling Back Composite Operations

In Spring Batch, a composite component can perform multiple operations for the same item or chunk. For example, a CompositeItemWriter may write orders to a result table, write an audit record, and update a summary table. If one delegate fails mid-way, the application needs to know which operations roll back and which side effects have already occurred.

The core point is that **a composite does not create a shared transaction on its own**. CompositeItemWriter invokes delegates in order; the chunk Step's transaction is the rollback boundary. Operations roll back together only when they participate in the same managed transaction. Writing files, calling APIs, sending emails, or publishing messages are usually not automatically undone by a database transaction.

## 1. Composite Operations in Spring Batch

A composite operation is an operation composed of multiple smaller components. In Spring Batch, common examples include:

- CompositeItemProcessor: passes an item sequentially through multiple processors.
- CompositeItemWriter: forwards the same chunk to multiple writers.
- Custom ItemWriter or Tasklet: calls multiple services/repositories within one business operation.
- A Step writing to multiple tables or multiple data targets.

Example of a chunk needing three operations:

~~~text
Chunk
  |
  v
CompositeItemWriter
  |
  +--> Writer 1: insert order_result
  |
  +--> Writer 2: insert order_audit
  |
  +--> Writer 3: update batch_summary
~~~

CompositeItemWriter coordinates the call order. It does not decide on its own how to undo each delegate. If Writer 3 throws an exception, Spring Batch receives the exception from the write call and handles the chunk transaction per Step configuration.

## 2. CompositeItemWriter Is Not a Transaction Manager

CompositeItemWriter is an ItemWriter that coordinates other ItemWriters. It does not open a database transaction itself, does not create a distributed transaction, and has no private rollback protocol to invert every call made so far.

In a chunk-oriented Step, the transaction manager is configured on the Step:

~~~java
return new StepBuilder("processOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(compositeWriter)
        .build();
~~~

When the Step executes a chunk, Spring Batch runs chunk processing inside a transaction as configured. If a delegate writer throws an exception and that exception triggers transaction rollback, database changes participating in the transaction are rolled back.

Conceptual flow:

~~~text
BEGIN chunk transaction
       |
       v
CompositeItemWriter.write(chunk)
       |
       +--> Delegate A writes data
       |
       +--> Delegate B writes data
       |
       +--> Delegate C fails
                    |
                    v
              Exception propagates out
                    |
                    v
               ROLLBACK
                    |
                    v
       Uncommitted transactional changes are discarded
~~~

If there is no transaction or a delegate writes to a system outside the transaction, data written before the failure point may remain.

## 3. Example of CompositeItemWriter Writing Multiple Tables

Suppose each Order must be written to a result table and an audit table. Both tables reside in the same database:

~~~sql
create table order_result (
    order_id bigint primary key,
    status varchar(30) not null
);

create table order_audit (
    audit_id bigint generated always as identity primary key,
    order_id bigint not null,
    event_type varchar(40) not null
);
~~~

First writer writes the result:

~~~java
@Bean
public JdbcBatchItemWriter<Order> orderResultWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    insert into order_result(order_id, status)
                    values (:orderId, 'PROCESSED')
                    """)
            .beanMapped()
            .assertUpdates(true)
            .build();
}
~~~

Second writer writes the audit:

~~~java
@Bean
public JdbcBatchItemWriter<Order> orderAuditWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    insert into order_audit(order_id, event_type)
                    values (:orderId, 'ORDER_PROCESSED')
                    """)
            .beanMapped()
            .assertUpdates(true)
            .build();
}
~~~

Combining both writers:

~~~java
@Bean
public CompositeItemWriter<Order> compositeOrderWriter(
        JdbcBatchItemWriter<Order> orderResultWriter,
        JdbcBatchItemWriter<Order> orderAuditWriter) {

    return new CompositeItemWriterBuilder<Order>()
            .delegates(List.of(
                    orderResultWriter,
                    orderAuditWriter))
            .build();
}
~~~

Both delegates accept the same Order type and write two different pieces of data. The essential condition for rolling back together is that they use a DataSource managed by the Step's transaction manager.

If the second writer fails after the first writer ran, the first writer's insert statements can still roll back because they are uncommitted and participate in the same transaction. The composite does not need to manually delete the first writer's rows.

### Configuring the Transaction Manager

Step example:

~~~java
@Bean
public Step processOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, Order> orderProcessor,
        CompositeItemWriter<Order> compositeOrderWriter) {

    return new StepBuilder("processOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(compositeOrderWriter)
            .build();
}
~~~

In a real application, confirm JobRepository and business data are configured with appropriate transaction strategies. Passing the same DataSource object to two JdbcBatchItemWriters is an important condition, yet you must still ensure the Step uses the transaction manager managing that DataSource.

## 4. What Happens When a Delegate Fails?

Suppose CompositeItemWriter has two delegates:

1. Writer A inserts into order_result.
2. Writer B inserts into order_audit.

If Writer B throws an exception:

~~~text
Writer A: INSERT order_result -> succeeded in transaction
Writer B: INSERT order_audit  -> exception
Chunk transaction             -> ROLLBACK

Result after rollback:
order_result                  -> no longer contains chunk inserts
order_audit                   -> contains no chunk inserts
~~~

This holds true when both statements share the same database transaction and neither commits independently.

If Writer A already called a REST API or sent an email, the database transaction cannot automatically undo that request or email. The real outcome may be:

~~~text
Writer A: REST API already received request
Writer B: database write failed
Chunk transaction: ROLLBACK

Database: changes rolled back
REST API: side effect still persists
~~~

Therefore, when designing a composite, list every resource each delegate writes to and identify which resources are genuinely transactional.

## 5. Delegate Order Affects Side Effects

CompositeItemWriter invokes delegates in the declared order. If a delegate throws an exception, subsequent delegates are normally not invoked in that execution pass.

Example:

~~~text
Delegate A -> succeeded
Delegate B -> failed
Delegate C -> not called yet
~~~

This order matters when delegates have dependencies or side effects. However, changing order does not solve atomicity on its own. If A sends an external message before B fails, putting A after B only reduces certain cases rather than creating a shared transaction.

Design delegates independently when possible. If the second operation depends on the result of the first, consider grouping logic into one business service with an explicit transaction or splitting into Steps with durable intermediate state.

Do not rely on delegate order as a rollback mechanism. Order only determines execution sequence.

## 6. Retries May Re-invoke Already-Executed Delegates

When a chunk rolls back and is retried, Spring Batch may re-invoke the write operation for that chunk. CompositeItemWriter will start the delegate chain over in the new call.

Example:

~~~text
Attempt 1:
  Writer A -> succeeded
  Writer B -> timeout
  Chunk    -> rollback

Retry attempt:
  Writer A -> called again
  Writer B -> called again
~~~

If Writer A wrote to the database inside the rolled-back transaction, the retry can safely execute again under the transaction. If Writer A called an API or published a message, the retry may create a duplicate side effect.

Therefore, any delegate that can be re-invoked needs an appropriate idempotency strategy:

- Use stable business keys.
- Use idempotency keys when calling APIs.
- Use unique constraints to prevent duplicate inserts.
- Use conditional upserts if business rules allow.
- Record operation status to know when side effects already completed.
- Do not generate a new UUID for the same operation on every retry if the UUID serves as the idempotency key.

Idempotency does not replace transactions, yet it prevents repeated operations from producing extra unintended effects.

## 7. CompositeItemProcessor and Side Effects

CompositeItemProcessor chains multiple processors sequentially:

~~~text
Input
  |
  v
ValidationProcessor
  |
  v
EnrichmentProcessor
  |
  v
CalculationProcessor
  |
  v
Output
~~~

Processors should usually focus on validation, mapping, and computation, rather than writing data or triggering irreversible side effects. If one processor sends an email and a later processor throws an exception, rolling back the database chunk cannot retract the email.

Configuration example:

~~~java
@Bean
public CompositeItemProcessor<OrderInput, OrderOutput> orderProcessor(
        ItemProcessor<OrderInput, ValidatedOrder> validationProcessor,
        ItemProcessor<ValidatedOrder, EnrichedOrder> enrichmentProcessor,
        ItemProcessor<EnrichedOrder, OrderOutput> calculationProcessor) {

    return new CompositeItemProcessorBuilder<OrderInput, OrderOutput>()
            .delegates(
                    validationProcessor,
                    enrichmentProcessor,
                    calculationProcessor)
            .build();
}
~~~

CompositeItemProcessor is not a transaction coordinator. If a processor writes to a database, that operation rolls back only when it joins the chunk transaction. If a processor calls external systems, an outbox, idempotency, or compensation is required.

A good design typically keeps processors side-effect-free while placing writes in writers or explicitly transaction-managed services.

## 8. All Database Delegates Must Participate in the Same Transaction

To roll back multiple database writers together, verify:

- Writers share the same transaction-aware DataSource.
- The Step uses the PlatformTransactionManager managing that DataSource.
- Writers use JDBC APIs that participate in Spring transactions, such as JdbcTemplate, NamedParameterJdbcTemplate, or JdbcBatchItemWriter.
- No manual connections are opened via DriverManager and committed separately.
- No independent transactions are started inside delegates unintentionally.
- `commit()` is never called directly on a Spring-managed connection.

Example custom writer using JdbcTemplate:

~~~java
public class CustomAuditWriter implements ItemWriter<Order> {

    private final JdbcTemplate jdbcTemplate;

    public CustomAuditWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            jdbcTemplate.update(
                    """
                    insert into order_audit(order_id, event_type)
                    values (?, ?)
                    """,
                    order.getOrderId(),
                    "ORDER_PROCESSED");
        }
    }
}
~~~

JdbcTemplate acquires connections through Spring's transaction integration. If custom code must access a JDBC connection directly, use DataSourceUtils or an appropriate transaction-aware API instead of opening an unmanaged connection.

### Two DataSources Pointing to the Same Database Are Not One Transaction

If writer A uses dataSourceA and writer B uses dataSourceB, even if both DataSources point to the same server/schema, they can use two separate connections and two separate transactions. A local transaction manager managing one DataSource does not automatically coordinate the other DataSource's transaction.

If atomicity across multiple database resources is strictly mandatory, a distributed/XA transaction manager can be considered when databases, drivers, and infrastructure support it. Evaluate operational cost and complexity carefully. Many systems choose an outbox or compensating workflows for eventual consistency rather than XA.

## 9. Propagation Can Break Expected Rollbacks

A delegate may invoke a service annotated with @Transactional. Pay attention to transaction propagation:

| Propagation | General Behavior | Effect on Chunk |
| --- | --- | --- |
| REQUIRED | Joins current transaction or starts a new one if none exists | Usually right for letting a service join the chunk transaction |
| REQUIRES_NEW | Suspends current transaction and creates an independent transaction | Inner transaction can commit even if the outer chunk rolls back |
| SUPPORTS | Joins transaction if present, otherwise runs non-transactionally | Requires understanding the caller context |
| NOT_SUPPORTED | Suspends current transaction | Operations do not roll back with the chunk |

Example:

~~~java
@Transactional
public void writeBusinessData(Order order) {
    repository.save(order);
}
~~~

Default REQUIRED normally joins the active transaction if the service is invoked through a Spring proxy and uses the matching transaction manager.

Conversely:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAudit(Order order) {
    auditRepository.save(new AuditRecord(order.getOrderId()));
}
~~~

The audit transaction can commit on its own. If a later delegate fails, chunk rollback does not undo the committed audit record.

Do not use REQUIRES_NEW merely to "make sure audit is always written" without defining business semantics. If the audit must persist even when the chunk fails, record it clearly as an attempt/failure event and model states accordingly.

## 10. noRollback and Exception Policies

In a chunk Step, exceptions from writers usually trigger transaction rollback. However, a fault-tolerant Step can configure retry, skip, or noRollback for specific exceptions.

Configuration example:

~~~java
return new StepBuilder("processOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(compositeWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .build();
~~~

Skip policies and rollback policies are related but not synonymous. If an exception is configured not to roll back, changes already made within the transaction may still commit depending on the flow and how the exception is handled. Do not mark a delegate exception as noRollback if the delegate may have written partial data that must be undone.

For skippable data errors, clarify which delegates already ran and whether the chunk can safely continue. For infrastructure failures such as connection errors, deadlocks, or timeouts, configure retry/fail per policy rather than skipping them like bad records.

## 11. ItemStream Lifecycle of Delegates

Some writers also implement ItemStream to manage resources or checkpoints, such as FlatFileItemWriter. The composite writer needs to manage the lifecycle of stream delegates:

- open(ExecutionContext) when the Step opens the writer.
- update(ExecutionContext) at checkpoints.
- close() when the Step finishes.

CompositeItemWriter has mechanisms to forward lifecycle callbacks to ItemStream delegates per your Spring Batch version's configuration. If writing a custom composite or wrapping delegates in decorators, ensure ItemStream delegates are registered and callbacks are forwarded properly.

Custom wrapper example:

~~~java
public class AuditingWriter<T>
        implements ItemStreamWriter<T> {

    private final ItemStreamWriter<T> delegate;

    public AuditingWriter(ItemStreamWriter<T> delegate) {
        this.delegate = delegate;
    }

    @Override
    public void open(ExecutionContext context) throws ItemStreamException {
        delegate.open(context);
    }

    @Override
    public void write(Chunk<? extends T> chunk) throws Exception {
        delegate.write(chunk);
    }

    @Override
    public void update(ExecutionContext context) throws ItemStreamException {
        delegate.update(context);
    }

    @Override
    public void close() throws ItemStreamException {
        delegate.close();
    }
}
~~~

If a wrapper only implements ItemWriter without forwarding ItemStream, the delegate may fail to open, update checkpoints, or close properly. This breaks restarts or leaks resources even though standalone write() calls appear to work.

Lifecycle is not rollback. Calling close() does not mean already-executed side effects are undone.

## 12. Writing Database and File in the Same Composite

A composite can combine JdbcBatchItemWriter and FlatFileItemWriter. This is an easy place for misunderstandings:

~~~text
CompositeItemWriter
      |
      +--> JdbcBatchItemWriter
      |
      +--> FlatFileItemWriter
~~~

Databases have clear transactions. FlatFileItemWriter has transactional buffering to coordinate chunk writes, yet the filesystem does not automatically become an XA resource shared with the database. Process crashes, I/O errors, or failures between flush/commit steps can still leave the two targets out of sync.

For critical output files, use staging:

1. Write the file to a temporary name tied to JobInstance or JobExecution.
2. Write database data inside the chunk transaction.
3. Finish the Job and inspect BatchStatus, ExitStatus, and business validation.
4. Check record counts, size, and checksum of the staging file.
5. Publish the file via rename/move or an appropriate storage mechanism.
6. Record publish status and notify consumers.

Consumers only read files in PUBLISHED state. If the Job fails, the staging file can be kept for investigation or deleted under a retention policy.

If database state and publish state must remain consistent, store a publication/outbox record in the same database transaction, then have a separate publisher perform the move and mark completion idempotently.

## 13. Writing Database and Sending Messages

Example of a composite writing an order to the database and then sending a message:

~~~text
CompositeItemWriter
      |
      +--> Database writer: INSERT order
      |
      +--> Message writer: publish OrderCreated
~~~

If the database insert succeeds and the broker publish fails, the chunk can roll back the database. However, if the broker already accepted the message and then the database transaction fails, the message is not automatically retracted.

This is the dual-write problem. Write ordering cannot guarantee atomicity between a database and a message broker.

### Using a Transactional Outbox

Within the same database transaction, write both business data and the event to an outbox:

~~~sql
insert into orders(order_id, status)
values (:orderId, 'CREATED');

insert into outbox_event(event_id, aggregate_id, event_type, payload, status)
values (:eventId, :orderId, 'ORDER_CREATED', :payload, 'PENDING');
~~~

After the transaction commits, a separate publisher reads PENDING outbox events and sends them to the broker:

~~~text
Chunk transaction
    |
    +--> INSERT orders
    |
    +--> INSERT outbox_event
    |
    +--> COMMIT
             |
             v
      Outbox publisher
             |
             v
          Message broker
~~~

If the chunk rolls back, both the order and the outbox event roll back. If the publisher sends the message yet the process stops before marking SENT, the event may be sent again. Consumers still need idempotency keyed by event_id.

An outbox does not automatically provide end-to-end exactly-once delivery, yet it prevents losing events between database commit and publish.

## 14. Calling REST APIs or Sending Emails in a Composite

REST APIs, emails, and many external services do not join the Step's database transaction. When called directly inside a writer:

- The API may already have processed the request even if the chunk rolls back.
- Sent emails cannot be recalled by a rollback.
- Retries may resend the request or email.
- A timeout does not prove the receiver did not process the request.

Options:

- Send requests with a stable idempotency key.
- Write commands to an outbox and process them in a separate publisher.
- Use APIs that support transactions or deduplication if available.
- Persist operation status for reconciliation.
- Use compensation when business rules permit undoing via a new action.

Do not put non-idempotent API calls in a processor merely because the processor runs before the writer. If the processor is re-invoked after rollback/retry, side effects can still repeat.

## 15. Compensation When Rollback Is Impossible

Rollback only discards uncommitted changes in transaction-capable resources. For side effects that already occurred outside transactions, compensation may be needed.

Example:

~~~text
Operation A: reserve inventory
Operation B: create shipment
Operation C: payment request fails

Compensation:
  release inventory
  cancel shipment if supported by the system
~~~

Compensation is a new business action, not a physical rollback. It can fail, may need retries, and requires its own tracking state.

When using compensation:

- Record the original operation and each step's outcome.
- Define a compensating action for every side effect.
- Make compensations idempotent.
- Track PENDING/COMPLETED/FAILED status for each action.
- Have a manual intervention procedure when compensation fails.
- Do not delete the original operation history.

The Saga pattern is commonly used when a process spans multiple independent services without a shared distributed transaction.

## 16. Custom Composite Service with @Transactional

If one business operation consists of multiple repository calls on the same database, they can be grouped into a service:

~~~java
@Service
public class OrderCompletionService {

    private final OrderRepository orderRepository;
    private final AuditRepository auditRepository;

    public OrderCompletionService(
            OrderRepository orderRepository,
            AuditRepository auditRepository) {
        this.orderRepository = orderRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public void complete(Order order) {
        orderRepository.markProcessed(order.getOrderId());
        auditRepository.insertProcessedEvent(order.getOrderId());
    }
}
~~~

Writer calling the service:

~~~java
public class OrderCompletionWriter implements ItemWriter<Order> {

    private final OrderCompletionService service;

    public OrderCompletionWriter(OrderCompletionService service) {
        this.service = service;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            service.complete(order);
        }
    }
}
~~~

With default REQUIRED propagation and the same transaction manager, the service normally joins the active chunk transaction. If any item in the chunk causes the service to throw an exception, the chunk transaction can roll back all database operations for that chunk.

Notes:

- The service must be invoked via a Spring proxy for the transaction interceptor to apply.
- Self-invocation within the same bean may bypass the proxy.
- Repositories must share the same transaction manager/resource if they must roll back together.
- Do not use REQUIRES_NEW if the service's operations must roll back with the chunk.
- Exceptions must propagate to the writer if the Step must roll back.

Do not catch exceptions inside the service just to log and continue if failure leaves data inconsistent.

## 17. Rollback Across Multiple Databases

If a composite writes to two independent databases:

~~~text
Composite writer
   |
   +--> DataSource A / transaction A
   |
   +--> DataSource B / transaction B
~~~

A local transaction manager typically manages only one resource. If transaction A commits first and then B fails, rolling back transaction B cannot undo already-committed A.

Options:

1. **JTA/XA:** coordinate commit/rollback across multiple resources if all resources and infrastructure support it. Accept higher configuration and operational complexity.
2. **Outbox/inbox:** persist status and sync requests in one database transaction, then sync to the other database with an idempotent consumer.
3. **Saga/compensation:** execute independent steps and run compensating actions if a later step fails.
4. **Reconciliation:** record per-target status and run reconciliation to resolve discrepancies.

Do not invoke two transaction managers back-to-back and treat them as one atomic transaction. Explicitly define the state when a process stops between the two commits.

## 18. Readers, Checkpoints, and Chunk Rollbacks

When the composite writer fails, the chunk transaction can roll back. Reader state is persisted through ItemStream/ExecutionContext at chunk boundaries per Spring Batch's mechanism. Subsequent retries or restarts resume from the most recent valid checkpoint.

Example:

~~~text
Chunk 1:
  delegate A + delegate B succeeded
  COMMIT
  checkpoint saved

Chunk 2:
  delegate A succeeded
  delegate B failed
  ROLLBACK

Restart:
  resume from checkpoint after chunk 1
  reprocess chunk 2 data
~~~

If delegate A has non-transactional side effects, reprocessing chunk 2 can repeat those side effects. Checkpoints only manage Step progress; they do not automatically undo or deduplicate external systems.

For safe restarts:

- Readers and writers must save state properly if restart is required.
- Reader/writer names and identifying JobParameters must be stable.
- Input datasets must stay unchanged or be version-pinned.
- Writers need appropriate unique keys or idempotency.
- Non-transactional side effects must be recorded and reconciled.

## 19. Skip and Retry with Composite Writers

If a delegate throws an exception, the Step can retry the chunk or skip per fault-tolerance policy. Understand which delegate threw the exception and the state of delegates that ran earlier.

Retry example:

~~~java
return new StepBuilder("processOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(compositeWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
~~~

If delegate A writes to the database inside the chunk transaction and delegate B hits a transient error, rolling back and retrying can be safe for A. If A calls an API, idempotency keys or an outbox must be used.

Skipping writer exceptions requires care. If one delegate already executed an irreversible side effect and the exception is skipped, the chunk may proceed while targets diverge. Only skip when the state of all operations is well understood and business rules are explicit.

Do not retry endlessly or retry every exception. Permanent data errors do not become valid after repeated attempts; configuration errors should fail fast.

## 20. Testing Composite Rollbacks

Separate two levels of testing:

**Unit tests:** verify the composite calls delegates in order and passes the right chunk; verify exceptions propagate when a delegate fails.

**Integration tests:** run the Step with a real transaction manager and database to verify earlier delegates' changes roll back.

Illustrative unit test:

~~~java
@Test
void callsDelegatesInOrderAndPropagatesFailure() throws Exception {
    @SuppressWarnings("unchecked")
    ItemWriter<Order> first = mock(ItemWriter.class);
    @SuppressWarnings("unchecked")
    ItemWriter<Order> second = mock(ItemWriter.class);

    doThrow(new IllegalStateException("second writer failed"))
            .when(second)
            .write(any());

    CompositeItemWriter<Order> composite =
            new CompositeItemWriterBuilder<Order>()
                    .delegates(List.of(first, second))
                    .build();

    Chunk<Order> chunk = new Chunk<>(List.of(new Order(1001L)));

    assertThrows(
            IllegalStateException.class,
            () -> composite.write(chunk));

    InOrder order = inOrder(first, second);
    order.verify(first).write(chunk);
    order.verify(second).write(chunk);
}
~~~

This test only proves invocation order and exception propagation. Mocks have no database transaction and therefore do not prove rollback.

### Integration Test Verifying Database Rollback

An integration test should:

1. Set up a test database and both result/audit tables.
2. Configure two JDBC delegates using the same DataSource.
3. Configure the Step with the transaction manager managing that DataSource.
4. Make the second delegate throw an exception after the first delegate writes.
5. Run the Step and verify execution fails.
6. Query both tables to verify inserts from the uncommitted chunk do not exist.

Example assertions after the Step completes:

~~~java
assertEquals(BatchStatus.FAILED, execution.getStatus());

Integer resultCount = jdbcTemplate.queryForObject(
        "select count(*) from order_result where order_id = ?",
        Integer.class,
        1001L);

Integer auditCount = jdbcTemplate.queryForObject(
        "select count(*) from order_audit where order_id = ?",
        Integer.class,
        1001L);

assertEquals(0, resultCount);
assertEquals(0, auditCount);
~~~

Ensure the exception happens before commit and both writers genuinely join the same transaction. If using a dummy failing writer, place it after the database writer in the composite. Use the same database engine as production when behavior depends on the engine.

### Testing Non-Rollback Side Effects

If the first delegate calls a fake external API and the second delegate fails, tests should verify the fake API still recorded the request. This demonstrates why idempotency or an outbox is needed rather than expecting database rollback to erase side effects.

## 21. Common Mistakes

### Thinking CompositeItemWriter Rolls Back Delegates Automatically

The composite only coordinates calls. The Step's transaction manages rollback for participating transactional resources.

### Two Writers Using Two Independent Transaction Managers

One writer can commit while the other rolls back. Use the same transaction manager when sharing a database, or design XA/outbox/compensation.

### Writing to Database Then Calling an API Directly

The API does not roll back with the database. Use idempotency keys or an outbox.

### Retries Sending Duplicate Messages/Emails

Earlier delegates may be re-invoked after rollback. Design idempotent operations and use stable keys.

### Using REQUIRES_NEW in a Delegate While Expecting Chunk Rollback

An independent transaction can commit separately. Use REQUIRED if joining the chunk transaction with the same transaction manager is desired.

### Catching Exceptions and Continuing

The Step will not know the operation failed and may commit inconsistent data. Propagate exceptions or handle them under an intentional policy.

### Ignoring ItemStream Lifecycle

Delegates may fail to save checkpoints or close resources. Forward open/update/close and register streams properly.

### Treating File/Footer Presence as Proof of Commit

Filesystems are not inherently atomic with databases. Use staging and a publish step after verifying outcomes.

### Using Skip for Infrastructure Errors

Connection failures, timeouts, or deadlocks usually need retry/fail, not skipping records.

### Testing Only Exception Propagation

Unit tests do not verify transaction rollback. Add integration tests with a real database and transaction manager.

## 22. Workflow for Designing Rollback in Composite Operations

Before combining multiple delegates, map out a resource table:

| Delegate | Target Resource | Transaction Manager | Rolls Back with Chunk? |
| --- | --- | --- | --- |
| Database writer A | Business database | Step's transaction manager | Yes, if in the same transaction |
| Database writer B | Same database/DataSource | Same transaction manager | Yes, if in the same transaction |
| Writer C | Different database | Separate transaction manager | Not automatically |
| File writer | Filesystem | Writer/file-specific mechanism | Not atomic with database |
| Message publisher | Broker | Broker transaction if separately configured | Not automatically with DB |
| REST/email delegate | External service | Outside DB transaction | No |

Then determine:

1. Which delegates have side effects and what does call order imply?
2. Does an exception in each delegate roll back the chunk?
3. Do database writers use the same DataSource and transaction manager?
4. Does any service use REQUIRES_NEW or a different transaction manager?
5. Will retries re-invoke delegates that already ran?
6. Do non-transactional side effects carry idempotency keys?
7. Are an outbox, staging files, compensation, or reconciliation needed?
8. Is ItemStream delegate lifecycle managed?
9. Can checkpoints restore the same input and output paths?
10. Do unit tests and integration tests verify the exact rollback boundaries?

A reliable composite operation needs clear transaction boundaries, idempotent delegates wherever re-invocation is possible, and dedicated handling for non-transactional resources.

## Conclusion

Rollback of composite operations in Spring Batch comes from the chunk Step's transaction, not from CompositeItemWriter automatically undoing individual delegates. When writers share one DataSource and transaction manager, uncommitted database changes can roll back together if a delegate fails. If a composite writes files, sends messages, calls APIs, or writes to multiple independent databases, side effects can persist after rollback and repeat on retry. Classify resources, use a shared transaction for database operations that can join it, design idempotency for re-invoked delegates, and use an outbox, staging/publishing, or compensation for external side effects. Verify delegate order with unit tests and prove real rollback via integration tests against the proper transaction manager and database.
