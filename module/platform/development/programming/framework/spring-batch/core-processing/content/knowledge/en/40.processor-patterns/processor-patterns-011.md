# Processor side effects and rollback

In Spring Batch, `ItemProcessor` is commonly used to validate, enrich, transform, or filter each item before the writer persists results. A processor may call a database, REST API, message broker, filesystem, or another service. These calls can produce side effects: updating state, sending emails, emitting events, writing audits, or mutating data in external systems.

Problems arise when a chunk rolls back, a step retries, an item is skipped, or a job restarts. A chunk transaction can undo database changes participating in the same transaction, but it cannot automatically undo a sent HTTP request, dispatched email, written file, or already-committed independent transaction. When the processor is invoked again, side effects can repeat; when the processor created a side effect yet the chunk fails to commit, the system can retain inconsistent partial state.

Therefore, processors should prioritize computation and transformations that can be safely repeated. If business rules require writing data, place that operation in a writer or a service participating in the chunk transaction. If out-of-transaction side effects are needed, use an outbox, idempotency keys, staging, or a separate publishing step to control retries and restarts.

## 1. What should a processor do?

`ItemProcessor<I, O>` receives an input item and returns an output item. A processor can:

- Validate data and throw an exception if an item is invalid.
- Compute or normalize data.
- Enrich the item with available data or appropriate lookups.
- Convert an input DTO into an output DTO.
- Return `null` to filter an item per business rules.

Example of a pure processor:

~~~java
public class OrderProcessor
        implements ItemProcessor<OrderInput, OrderOutput> {

    @Override
    public OrderOutput process(OrderInput input) {
        if (input.getAmount() == null || input.getAmount().signum() < 0) {
            throw new InvalidOrderException("amount must be non-negative");
        }

        BigDecimal tax = input.getAmount()
                .multiply(new BigDecimal("0.10"));
        BigDecimal total = input.getAmount().add(tax);

        return new OrderOutput(
                input.getOrderId(),
                input.getCustomerId(),
                total);
    }
}
~~~

This processor computes from the input and creates an output. If Spring Batch invokes it again with the same item after rollback, the result stays identical and creates no extra side effects.

## 2. What is a side effect?

A side effect is an observable change outside the return value of the method. In a processor, side effects can include:

| Action | Side effect |
|---|---|
| `jdbcTemplate.update(...)` | Writing or updating the database |
| Calling a REST API | Creating/updating data in another service |
| Sending a message | Emitting an event or command to a broker |
| Sending email/SMS | Issuing an irreversible notification |
| Writing a file | Modifying artifacts on filesystem/object storage |
| Calling a payment service | Creating a financial transaction |
| Writing an out-of-transaction audit | Creating an independent audit record |
| Incrementing a remote counter | Mutating metrics or external system state |

Not all side effects are wrong. Some business requirements need them. The issue is knowing which transaction a side effect belongs to, whether it can roll back, and what happens when the same item is processed again.

## 3. How does a chunk transaction wrap the processor?

In a chunk-oriented step, Spring Batch manages one transaction per chunk. Conceptually, the transaction spans reading, processing, and writing the items in the chunk, then commits when the chunk completes.

~~~mermaid
flowchart TD
    A[Begin chunk transaction] --> B[Read items]
    B --> C[Process each item]
    C --> D[Write chunk]
    D --> E[Update stream and checkpoint state]
    E --> F{Commit succeeds?}
    F -->|Yes| G[Chunk committed]
    F -->|No| H[Rollback chunk]
    H --> I[Retry, skip or fail according to policy]
~~~

If the processor uses the same transaction-managed database resource as the step, the processor's SQL statements can join the chunk transaction. When the writer or a subsequent step throws an exception before commit, those database changes can roll back with the chunk.

Transactions do not automatically cover every system the processor calls. HTTP services, email servers, filesystems, and independently configured brokers typically sit outside the database transaction. Boundaries must be clearly identified for every side effect.

## 4. Database side effects in the same transaction

A processor may call `JdbcTemplate` to update the database. If `JdbcTemplate` uses the same `DataSource` managed by the step's transaction manager, connections are typically bound to the current transaction and changes commit/roll back with the chunk.

Example:

~~~java
public class OrderEnrichmentProcessor
        implements ItemProcessor<OrderInput, OrderOutput> {

    private final JdbcTemplate jdbcTemplate;

    public OrderEnrichmentProcessor(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public OrderOutput process(OrderInput input) {
        jdbcTemplate.update("""
                update source_order
                   set validation_status = ?
                 where order_id = ?
                """,
                "VALIDATED",
                input.getOrderId());

        return new OrderOutput(input.getOrderId(), input.getAmount());
    }
}
~~~

If the update joins the same chunk transaction, an exception inside the chunk prior to commit rolls back that update. However, writing state inside a processor makes code harder to follow: the processor both transforms items and mutates persistent state. If the goal is persisting business outcomes, moving writes to the writer is usually better.

## 5. Same database server does not guarantee same transaction

Two operations writing to the same database can still run in separate transactions if:

- Using an independent `DataSource` or connection not managed by the transaction manager.
- Using a different transaction manager.
- Manually opening a connection with `autoCommit` enabled.
- Calling a service with `REQUIRES_NEW` propagation.
- Stored procedures or triggers performing autonomous commits.
- Calling another service with its own transaction boundary.

If the processor commits a side effect in a separate transaction and the chunk rolls back, committed data remains. On retry or restart, the processor may rerun the operation and create duplicates.

Verify the actual `DataSource`, transaction manager, and transaction propagation. Never conclude two operations are atomic merely because they point to the same hostname/database.

## 6. Transaction propagation and REQUIRES_NEW

Spring transaction propagation determines whether a side effect joins the chunk transaction:

| Propagation | General behavior when a chunk transaction already exists |
|---|---|
| `REQUIRED` | Joins the current transaction |
| `REQUIRES_NEW` | Suspends the current transaction and creates an independent transaction |
| `SUPPORTS` | Joins if a transaction exists; otherwise runs non-transactionally |
| `NOT_SUPPORTED` | Suspends the current transaction and runs outside a transaction |
| `MANDATORY` | Requires an existing transaction |

Example service using `REQUIRES_NEW`:

~~~java
@Service
public class AuditService {

    private final AuditRepository repository;

    public AuditService(AuditRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAttempt(Long orderId) {
        repository.save(new AuditRecord(orderId, "PROCESSING"));
    }
}
~~~

If the processor calls this service, the audit record can commit even when the outer chunk transaction rolls back. When the processor is invoked again, a second audit record may be created.

`REQUIRES_NEW` can suit independent auditing when intentionally designed for it. However, idempotency or an event key is needed to distinguish attempts from final business outcomes. Never use it merely to "make sure it saves" without considering rollbacks and retries.

Note that `@Transactional` works via proxies in standard Spring configurations. Self-invocation within the same object can bypass the proxy, so actual propagation may differ from expectations if a method directly calls another method on `this`.

## 7. Side effects outside the database transaction

Example processor calling a REST API:

~~~java
public OrderOutput process(OrderInput input) {
    partnerClient.reserveInventory(input.getOrderId());
    return map(input);
}
~~~

If the reservation API succeeds while the writer fails, rolling back the database transaction cannot automatically cancel the reservation. When the chunk retries, the API may be called again.

Common out-of-transaction side effects:

- HTTP requests already processed by another service.
- Messages already accepted by a broker.
- Emails/SMS already sent.
- Files already uploaded.
- Payments or reservations already created.

Even if a transport supports its own transactions, that transaction is not automatically atomic with the chunk's JDBC transaction. Explicit coordination is required if both must succeed or fail together.

## 8. Processor re-invocation after rollback

A fault-tolerant step can retry an operation or roll back and reprocess the chunk. When a processor has side effects, re-invocation is a real risk.

Example:

1. Processor calls an API to create a reservation for order 1001.
2. Processor returns `OrderOutput`.
3. Writer writes to the database, but another item in the chunk fails.
4. Chunk rolls back.
5. Spring Batch retries per policy.
6. Processor may be invoked again for order 1001.
7. API creates a second reservation if the request is not idempotent.

Never assume each item passes through the processor only once. With retries/rollbacks, actual invocation counts depend on fault-tolerant configuration, failure location, and version. Design processors to be safe under repeated calls.

## 9. processorNonTransactional and processor caching

In a fault-tolerant step, Spring Batch offers `processorNonTransactional()` to declare that the processor need not be re-invoked when a chunk rolls back. The framework can cache processor outputs in memory to reuse when reprocessing the chunk.

Configuration example:

~~~java
return new StepBuilder("processOrdersStep", jobRepository)
        .<OrderInput, OrderOutput>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .processorNonTransactional()
        .build();
~~~

This option can reduce processor re-invocations during retries within the same execution, yet it is not a side-effect rollback mechanism:

- Already-emitted side effects do not disappear.
- The cache is not a durable checkpoint and does not replace restart state.
- Process crashes lose the in-memory cache.
- Restarting the `JobInstance` may still rerun the processor for uncommitted items.
- This setting does not make an HTTP request transactional.

Use it only when processor semantics genuinely fit reusing computed results. Never rely on this setting to protect payments, message publishing, or non-idempotent side effects.

## 10. Returning null from a processor and side effects

`ItemProcessor` can return `null` to filter an item. Filtered items are not forwarded to the writer. However, if the processor performs a side effect before returning `null`, that side effect still occurs.

Dangerous example:

~~~java
public OrderOutput process(OrderInput input) {
    notificationClient.send(input.getCustomerId(), "Order received");

    if (input.getAmount().signum() == 0) {
        return null;
    }

    return map(input);
}
~~~

Zero-amount orders are filtered, yet the notification was already sent. If business rules require filtered items to emit no notifications, this logic order is wrong.

Decide filtering first, then perform appropriate work. Better yet, have the processor only return a result or `null`, and let the writer/publisher execute side effects only for accepted items.

## 11. Do not use a processor to send emails or SMS

Sending emails/SMS generally cannot be rolled back. If a processor sends a notification and the chunk rolls back, the recipient still receives the notification even though the business data never committed.

A safer workflow:

1. The processor determines the notification content to send and produces a notification intent.
2. The writer saves business results and the notification intent to the database in the same chunk transaction.
3. After commit, a dedicated publisher reads unsent notification intents.
4. The publisher dispatches via the provider using an idempotency key if supported.
5. The publisher marks it sent or records delivery status.

If sending fails, the notification intent remains available for retry. If the publisher crashes after the provider sent the message but before marking it sent, provider idempotency keys or reconciliation prevent duplicate sends.

## 12. Do not publish messages directly from a processor

Calling `KafkaTemplate.send(...)`, `JmsTemplate.convertAndSend(...)`, or `RabbitTemplate.convertAndSend(...)` inside a processor creates out-of-transaction side effects unless explicit transaction coordination is configured.

Example:

~~~java
public OrderOutput process(OrderInput input) {
    kafkaTemplate.send("order-events", toEvent(input));
    return map(input);
}
~~~

If the writer or a later item causes the chunk to roll back, the sent Kafka record may still exist. On retry, the processor may publish the record again.

When events must correspond to business updates, use a transactional outbox. Write the event to an outbox table in the same database transaction as the business data; a separate publisher dispatches events after commit. This decouples batch transactions from broker transactions while retaining replayability.

## 13. Transactional outbox pattern

An outbox closes the crash window between database commit and message publishing:

~~~mermaid
flowchart TD
    A[ItemProcessor creates result and event intent] --> B[Chunk writer]
    B --> C[Business table]
    B --> D[Outbox table]
    C --> E[Same database transaction]
    D --> E
    E --> F[Commit]
    F --> G[Outbox publisher]
    G --> H[Message broker]
    H --> I[Consumer with deduplication]
~~~

In the chunk writer, write business data and outbox rows in the same transaction:

~~~java
public class OrderAndOutboxWriter
        implements ItemWriter<ProcessedOrder> {

    private final JdbcTemplate jdbcTemplate;

    @Override
    public void write(Chunk<? extends ProcessedOrder> chunk) {
        for (ProcessedOrder order : chunk) {
            jdbcTemplate.update("""
                    insert into processed_order(order_id, amount)
                    values (?, ?)
                    """,
                    order.orderId(),
                    order.amount());

            jdbcTemplate.update("""
                    insert into outbox_event(event_id, event_type, payload, status)
                    values (?, ?, ?, ?)
                    """,
                    order.eventId(),
                    "OrderProcessed",
                    order.eventPayload(),
                    "NEW");
        }
    }
}
~~~

If the chunk rolls back, both the business row and the outbox row roll back. After commit, the publisher can dispatch events independently. The publisher must handle redelivery and send statuses; consumers should deduplicate by `eventId`.

An outbox does not provide exactly-once delivery by itself. It guarantees the event intent is stored atomically with the business update; publishing may be at-least-once and requires consumer idempotency.

## 14. Processor creates intent, writer performs persistence

A clean separation of responsibilities lets the processor produce an output DTO containing data to persist, instead of writing to the database directly:

~~~java
public record ProcessedOrder(
        Long orderId,
        BigDecimal amount,
        String eventId,
        String eventPayload) {
}

public class OrderProcessor
        implements ItemProcessor<OrderInput, ProcessedOrder> {

    @Override
    public ProcessedOrder process(OrderInput input) {
        OrderValidated validated = validateAndNormalize(input);
        OrderEvent event = createEvent(validated);

        return new ProcessedOrder(
                validated.orderId(),
                validated.amount(),
                event.eventId(),
                serialize(event));
    }
}
~~~

The writer persists `ProcessedOrder` and the outbox row inside the transaction. This makes the processor easy to unit test while concentrating transaction boundaries where data is written.

The event ID should be deterministic for the business operation. If the processor generates a random UUID on every call, rollbacks/retries can create new event IDs for the same item. Derive IDs from `source ID + business key + event type/version`, or generate the ID once at the source and pass it through the pipeline.

## 15. Idempotency keys for side effects

If calling an API from a processor or pipeline-invoked service is mandatory, the request needs a stable idempotency key. An API receiving the same key multiple times must return the same result or treat later requests as replays.

Example:

~~~java
String idempotencyKey =
        "reserve-order-" + input.getOrderId();

partnerClient.reserveInventory(
        input.getOrderId(),
        idempotencyKey);
~~~

The key should represent a specific business operation. If the same order can be reserved again under a new version or business attempt, include the operation/version in the key so distinct requests are not accidentally merged.

Never use a random UUID regenerated on each `process` invocation. When the processor runs again, a new key causes the service to treat it as a brand-new operation and duplicate the side effect.

## 16. Idempotency in the database

The database can guard side effects with a unique constraint or a ledger table:

~~~sql
create table processed_operation (
    operation_key varchar(200) primary key,
    business_key varchar(100) not null,
    payload_hash varchar(64) not null,
    processed_at timestamp not null
);
~~~

Before executing the operation, check/insert `operation_key` in the same transaction as the business change. If the key already exists:

- Same payload hash: likely a valid replay.
- Different payload hash: likely a conflict requiring handling.
- Incomplete status: requires recovery per state machine.

Never check via SELECT followed by INSERT when multiple workers run concurrently; race conditions allow both to see the key as absent. A unique constraint is the final safeguard.

## 17. Processor calling a service with REQUIRED transaction

A service called from a processor may use `@Transactional` with default `REQUIRED` propagation. When invoked through a Spring proxy sharing the same transaction manager, it typically joins the active chunk transaction.

~~~java
@Service
public class OrderValidationService {

    private final OrderRepository repository;

    @Transactional
    public void markValidated(Long orderId) {
        repository.updateValidationStatus(orderId, "VALIDATED");
    }
}
~~~

If the service and step share the same transaction manager, changes can roll back when the chunk rolls back. Even so, revisit responsibility boundaries: mutating status in a processor can cause confusion across filters, retries, and skips.

If the status is a final business outcome, the writer is usually a better place to persist it alongside outputs. The service can be invoked from the writer and join the active transaction.

## 18. Side effects before the processor throws an exception

A processor might execute a side effect and then detect invalid data:

~~~java
public OrderOutput process(OrderInput input) {
    auditService.recordAttempt(input.getOrderId());

    if (input.getAmount().signum() < 0) {
        throw new InvalidOrderException("Negative amount");
    }

    return map(input);
}
~~~

If `recordAttempt` uses an independent transaction, the audit row remains even if the item is skipped or the chunk rolls back. If the audit row sits inside the chunk transaction, it rolls back with the chunk.

Define what the audit is meant to record:

- Attempt started: may legitimately exist even when processing fails.
- Validation result: should be recorded after validation determines the outcome.
- Business operation completed: record only after the result commits.

These three concepts are distinct. Use distinct event/status names so operators never mistake an attempt for a completed outcome.

## 19. Retrying exceptions in the processor

If the processor throws a transient exception, the step can be configured to retry:

~~~java
return new StepBuilder("processOrdersStep", jobRepository)
        .<OrderInput, OrderOutput>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TemporaryLookupException.class)
        .retryLimit(3)
        .build();
~~~

Retry only makes sense if the operation can succeed on a subsequent attempt. For example, a timed-out lookup service can be retried; a deterministic validation error should generally not be retried.

If the processor calls a side-effecting API and times out, it is unknown whether the server executed the operation. This is where idempotency keys or status query APIs are required. Blind retries can cause duplicates.

## 20. Skipping exceptions in the processor

A data error can be configured as skippable if records are independent and business rules permit bypassing them:

~~~java
return new StepBuilder("processOrdersStep", jobRepository)
        .<OrderInput, OrderOutput>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .listener(orderSkipListener)
        .build();
~~~

If the processor already invoked a side effect before throwing `InvalidOrderException`, skipping the item does not automatically undo the out-of-transaction side effect. Therefore, validate before side effects and let writers/publishers act only after items are validated.

Skip limits cap total bad items. Once exceeded, the step fails. Record business keys and skip reasons while avoiding logging sensitive full payloads.

## 21. Retry and skip are not the same as rollback

Distinguish three concepts:

- **Rollback:** undoes changes participating in the current transaction.
- **Retry:** re-attempts an operation/chunk per policy.
- **Skip:** excludes a failing item from processing when permitted by policy.

Rollback does not automatically call an API to reverse a side effect. Retry does not ensure prior side effects were erased. Skip does not automatically undo changes the processor already made before throwing an exception.

If a side effect must be compensated, that is a separate business operation, such as releasing a reservation or canceling a request. Compensation can also fail and needs its own retry/idempotency; never treat it like a database rollback.

## 22. Compensation and sagas

In multi-service workflows, an operation may require a compensating action:

~~~text
Reserve inventory
       |
       v
Persist order
       |
       +---- success -> continue
       |
       +---- failure -> release inventory
~~~

This is a saga/compensation pattern. A compensating action does not erase the original side effect from history; it issues a new business event to move the system into an acceptable state.

When using compensation:

- Persist the operation ID of the original action.
- Ensure compensation is idempotent.
- Track `PENDING`/`COMPLETED`/`FAILED` states.
- Retry compensation with bounds and alert when manual intervention is needed.
- Never delete the audit trail of the original operation.

Do not embed a long-running saga inside `ItemProcessor` without a durable state machine. Extract orchestration into services/workflows or separate steps if the process spans multiple states.

## 23. Side effects in ItemProcessListener

Listeners like `beforeProcess`, `afterProcess`, and `onProcessError` are useful for observing the processor. However, listeners also run within the processing lifecycle and may be called during retry/error paths depending on execution flow.

Do not use `afterProcess` to send emails or publish events assuming it only runs after commit. This callback is not a database transaction commit hook.

If a listener writes audits to the same transaction, verify whether it joins the active transaction. If a listener writes to external systems, apply the same idempotency/outbox rules as the processor.

Listeners suit metrics, tracing, logging, and state recording with explicit transaction semantics. They do not replace writers or after-commit publishers.

## 24. Do not use afterWrite as afterCommit

`ItemWriteListener.afterWrite` is invoked after the writer method finishes, which does not mean the chunk transaction has committed. Errors can still occur afterward in the remaining chunk lifecycle or during transaction commit.

Never send "completed" notifications from `afterWrite` if consumers interpret that as committed data. To react after commit, use transaction synchronization or an outbox.

Transaction synchronization `afterCommit` can be useful for lightweight tasks:

~~~java
TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                metricsPublisher.recordCommittedChunk();
            }
        });
~~~

After-commit callbacks avoid running on transaction rollback, though the process can still crash after commit before the callback finishes. For side effects requiring durability such as publishing business events, an outbox is far more reliable than in-memory callbacks.

## 25. File side effects from a processor

If a processor writes files directly:

~~~java
public OrderOutput process(OrderInput input) throws IOException {
    Files.writeString(
            auditPath,
            input.getOrderId() + System.lineSeparator(),
            StandardOpenOption.CREATE,
            StandardOpenOption.APPEND);
    return map(input);
}
~~~

Regular file writes do not participate in JDBC transactions. When a chunk rolls back, appended lines remain. When the processor reruns, lines can be appended again.

Some standard Spring Batch writers implement specific buffering/transaction-aware behavior. Do not generalize that behavior to `Files.write`, custom file writers, or arbitrary filesystems. If output files need rollback/restart safety, use appropriate writers, staging files, record keys, or a repeatable artifact-generation step.

## 26. Updating caches or in-memory state

A processor may update caches, counters, or mutable singletons:

~~~java
cache.put(input.getOrderId(), "PROCESSED");
~~~

Database rollbacks do not revert caches. If a chunk fails, the cache may claim an item was processed even though the business transaction rolled back. Retries may read stale state and skip the item.

If a cache is purely an optimization, ensure it can be invalidated/rebuilt from the source of truth and never let the cache dictate correctness. Never use in-memory flags as durable checkpoints. In parallel steps, caches also require thread safety and isolation across `JobInstance` runs.

## 27. Processor calling external systems to enrich data

Not every HTTP call from a processor creates side effects. A pure `GET` lookup may only read data. Still, it can:

- Return different results on retry.
- Consume quota or create audit/access logs on the external service.
- Time out after the server sent a response that the client never received.
- Make the processor non-deterministic if data changes between calls.

If enrichment must stay consistent across restarts, consider:

- Storing a snapshot/version of lookup data.
- Caching results by key and version.
- Writing enriched results into a staging table.
- Using immutable reference data.
- Explicitly documenting that lookups may be called multiple times.

`GET` usually causes no business mutations, yet still carries cost and semantics that must be controlled. Calling `POST` to "look up" data when the service creates a record or reservation is a side effect.

## 28. Processors and determinism

A processor is deterministic when the same input and same reference context produce the same output. This property helps retries, restarts, testing, and reconciliation.

Sources of non-determinism in processors:

- Using `Instant.now()` or `LocalDate.now()` directly.
- Generating a fresh random UUID on every `process` call.
- Calling services returning mutable data.
- Relying on singleton state that changes with item order.
- Reading unversioned/un-snapshotted data.
- Relying on the JVM's default timezone or locale.

If business time is needed, pass business timestamps via job parameters or input events. If stable IDs are needed, use source event IDs/business keys or a deterministic derivation rule. If random values are required, generate them once and persist them durably before retries.

## 29. Should a processor call a repository?

There is no rigid rule forbidding a processor from calling a repository. A read-only lookup for enrichment can be reasonable. However, mutating persistent state from a processor must be weighed carefully:

- Writing primary results usually belongs in the writer.
- Writing outbox rows usually belongs in the same writer transaction as business data.
- Auditing attempts may need a separate service with clear semantics.
- Reference data lookups can sit in the processor if they have no side effects.
- Updating source state may require a writer or a dedicated claim step.

If a processor calls a repository to write, tests must prove transaction participation and rollback/retry behavior. Never rely on method names like `save()` or `@Transactional` annotations alone to conclude changes will roll back with the chunk.

## 30. Processor calling a service that retries independently

A service may have its own retries, such as retrying HTTP timeouts inside a method. Combined with step retries, actual call counts can multiply:

- Step retries up to 3 times.
- Service retries up to 4 times per invocation.
- One item can trigger far more requests than anticipated.

Calculate total retry budgets, timeouts, and backoff across layers. Avoid unbounded nested retries. Service-level retries can handle transport errors; step-level retries can handle transaction/chunk errors. Clarify which layer owns each exception category.

## 31. Batch writer is the proper place for persistence

A pure processor returns a result:

~~~java
public class OrderProcessor
        implements ItemProcessor<OrderInput, ProcessedOrder> {

    @Override
    public ProcessedOrder process(OrderInput input) {
        return validateAndBuild(input);
    }
}
~~~

The writer persists output:

~~~java
@Bean
public JdbcBatchItemWriter<ProcessedOrder> processedOrderWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<ProcessedOrder>()
            .dataSource(dataSource)
            .sql("""
                    insert into processed_order(order_id, amount)
                    values (:orderId, :amount)
                    """)
            .beanMapped()
            .assertUpdates(true)
            .build();
}
~~~

The writer is invoked inside the chunk transaction. If inserts fail, the transaction can roll back the whole chunk along with checkpoints. Concentrating persistence in the writer clarifies transaction boundaries and simplifies integration testing.

## 32. When side effects must occur before the writer

Some business flows genuinely require reserving resources before writing to the database. In that case, model the reservation as a stateful operation:

1. Generate a stable operation key.
2. Call the reserve API with an idempotency key.
3. Store the reservation ID and status in the output/staging data.
4. Persist business results along with the operation reference.
5. If the chunk fails to commit, retries query or reuse the existing reservation.
6. If business processing fails permanently, emit compensation to release the reservation.

Never call an API and discard its response. Without storing the reservation ID, retries struggle to determine whether the earlier operation succeeded.

## 33. Side effects in a processor when items are skipped

Suppose a processor:

1. Calls an API to create a shipment.
2. Validates the address.
3. Throws `InvalidAddressException`.

If that exception is configured as skippable, the item is bypassed yet the shipment may still exist. That is a dangerous business state.

A better order:

1. Validate all internal data first.
2. Construct a valid output/command.
3. Record an intent or reservation with an idempotency key.
4. Perform external side effects only in a controlled step.
5. If failures happen after the side effect, persist state for retry/compensation.

Predictable data errors should be caught before triggering irreversible side effects.

## 34. Chunk rollback is not whole-job rollback

A chunk transaction covers only one chunk. Earlier committed chunks persist even if a later chunk fails:

~~~text
Chunk 1 -> COMMIT
Chunk 2 -> COMMIT
Chunk 3 -> PROCESSOR ERROR -> ROLLBACK
Job -> FAILED
~~~

Restarting the same `JobInstance` resumes from the checkpoint of the last committed chunk. If the processor caused out-of-transaction side effects in chunk 3, those side effects may remain despite chunk 3 rolling back.

If business requirements demand all-or-nothing across the entire job, you cannot rely on per-chunk rollbacks. Write into separate staging/versioned tables and publish once the entire job finishes, or use workflow compensation when side effects cannot be staged.

## 35. Side effects and remote chunking

In remote chunking, the manager sends chunks over a broker for workers to process. Workers may receive the same chunk again upon message redelivery or manager retries.

If a processor runs on a worker and creates side effects:

- Workers can process the same chunk multiple times.
- Message acks and database commits may not be atomic.
- A worker dying after a side effect but before acking can have work redelivered.
- The manager may miss a response even though the worker committed.

Use stable chunk IDs/event IDs, worker idempotency ledgers, and proper transactions. Never treat broker acknowledgments as a guarantee that worker side effects happened once.

## 36. Side effects and remote partitioning

In remote partitioning, each worker processes one partition. Side effects can execute concurrently:

- Two partitions must not process the same business key if partitioning overlaps.
- Writers/processors must use per-business-operation idempotency keys.
- External services must tolerate concurrency and retries.
- Partition restarts must receive the identical input range/configuration.
- Audits must carry partition/job correlation for traceability.

If processors update a shared counter or global state, multiple workers can race. Use atomic database operations or design an aggregation step after partitions complete.

## 37. Side effects in asynchronous processors

Some Spring Batch setups run processors asynchronously. Side effects may then execute on another thread or in another transaction context. Never assume the chunk transaction automatically propagates to worker threads.

Points to check:

- Is the transaction context propagated across threads?
- Does a service called on an async thread open its own transaction?
- How are processor future results awaited before commit?
- How do exceptions from futures propagate back to the step?
- Can a side effect complete after the chunk has already rolled back?
- Is the delegate thread-safe?

Do not use async processing for critical side effects without defining transaction and cancellation semantics. Once an async task has called an external API, canceling the future does not mean the server canceled the request.

## 38. Do not arbitrarily use listeners to compensate rollbacks

You might think of calling an undo API inside `afterChunkError` when a chunk rolls back. That can work as compensation, yet it is not a database rollback:

- Compensation callbacks can fail.
- Callbacks may re-run during recovery.
- Processes can crash before the callback executes.
- Not every side effect has an undo operation.
- Compensation may require business authorization or dedicated state.

When compensation is required, persist a durable operation record and execute it via a retry-capable step/worker, rather than relying solely on in-memory callbacks.

## 39. Logging and auditing side effects

When a processor calls external systems, logs should aid investigation:

- Job/Step execution reference.
- Business key.
- Operation/idempotency key.
- Correlation ID.
- External request ID if available.
- Side effect category.
- Request/response status.
- Attempt count.

Never log access tokens, credentials, full payment details, or sensitive full payloads. Logging "request sent" does not mean the external operation succeeded; distinguish `SENT`, `ACKNOWLEDGED`, `COMMITTED`, and `CONFIRMED` per semantics.

## 40. Testing pure processors

Processor unit tests should verify transformations and validation without database/broker dependencies:

~~~java
class OrderProcessorTest {

    private final OrderProcessor processor = new OrderProcessor();

    @Test
    void calculatesTotalWithoutExternalSideEffect() throws Exception {
        OrderInput input = new OrderInput(
                1001L,
                "C001",
                new BigDecimal("100.00"));

        OrderOutput output = processor.process(input);

        assertEquals(1001L, output.getOrderId());
        assertEquals(new BigDecimal("110.00"), output.getTotal());
    }

    @Test
    void rejectsNegativeAmount() {
        OrderInput input = new OrderInput(
                1002L,
                "C002",
                new BigDecimal("-1.00"));

        assertThrows(
                InvalidOrderException.class,
                () -> processor.process(input));
    }
}
~~~

For processors with read-only dependencies, mock dependencies and verify lookups follow the contract. If the goal is pure transformation, avoid mocking persistence or external clients.

## 41. Testing database side-effect rollbacks

Integration tests must prove database updates in a processor join the chunk transaction:

1. Use a real test database or appropriate container.
2. Have the processor update a table via `JdbcTemplate` sharing the `DataSource`.
3. Have the writer or a test double intentionally throw an exception after the processor runs.
4. Let the step roll back.
5. Query the database and verify the processor's changes are absent.
6. Rerun under passing conditions and confirm changes commit.

Do not just verify `JdbcTemplate.update()` was called. Mock interactions do not prove transaction rollback.

## 42. Testing REQUIRES_NEW

Create a test service using `REQUIRES_NEW`, call it from the processor, then force chunk rollback. Verify:

- Business updates participating in the chunk transaction roll back.
- Audit rows from the `REQUIRES_NEW` transaction persist.
- Retries do not create duplicate audits beyond policy.

This test gives the team clarity on transaction boundaries. Use database integration tests rather than mocked services to verify actual propagation through Spring proxies.

## 43. Testing external side effects and retries

Use a fake HTTP server or stub broker to record requests:

1. Processor sends a request with an idempotency key.
2. Fake server records the operation as succeeded, yet the client gets a timeout.
3. Step retries the same item.
4. Fake server receives the same key again.
5. Verify only one business operation was created.
6. Verify the processor/step finishes per policy.

If the external service lacks idempotency support, tests should expose the duplicate risk and validate reconciliation/compensation mechanisms. Never simulate a server that always fails before processing requests, as that skips the most critical crash window.

## 44. Testing processorNonTransactional

If `processorNonTransactional()` is configured, write integration tests confirming processor outputs are reused in rollback/retry paths as expected for your project's Spring Batch version.

Tests should:

- Count processor invocations for the same item.
- Intentionally fail the writer and retry.
- Compare behavior with `processorNonTransactional` enabled vs. disabled.
- Verify the cache is not treated as durable across process restarts.
- Check final outputs and actual side effects.

Do not write tests merely to prove fewer calls occurred; the goal is proving business correctness when the processor is not re-invoked on certain rollback paths.

## 45. Testing filters and side effects

Provide an input filtered by the processor and verify:

- The processor returns `null`.
- The writer does not receive that item.
- No unintended notifications, reservations, or external mutations occur.
- Read/filter/write counts reflect expected semantics.

If a processor has a permitted side effect before filtering, document the reason and test it explicitly. Generally, filter decisions must precede side effects.

## 46. Testing the outbox

Outbox integration tests should verify:

- Business rows and outbox rows commit together.
- If the writer throws an exception, both roll back together.
- After commit succeeds, the publisher can read the outbox row.
- Publisher retries do not lose events.
- Resending the same event ID does not duplicate business effects at the consumer.
- Publisher crashing after sending but before marking sent is handled safely.

Do not stop at checking rows in the outbox table. Test the crash window between sending and status update, as that is where duplicates commonly occur.

## 47. Testing skips and compensation

If a processor executes a side effect and then throws a skippable exception, tests must prove side effects are not left dangling unintentionally. If business flows require compensation, verify:

- The original operation has a durable ID.
- Compensation is created on skip/failure.
- Compensation is retryable.
- Final state is stored clearly.
- Error ledgers indicate the item was skipped and how the side effect was handled.

If compensation is impossible, policy may require failing the job instead of skipping items. Skipping is only safe when dropping the item leaves no half-finished system state.

## 48. Common pitfalls

| Situation | Cause | How to handle |
|---|---|---|
| API called twice after rollback | Processor had external side effect and was re-invoked | Idempotency keys or outbox |
| Audit row persists after chunk rollback | Audit service used `REQUIRES_NEW` | Clarify whether audit tracks attempts or committed results; deduplicate |
| DB update in processor does not roll back | Used independent connection/transaction manager | Use step's transaction resource or move writes to writer |
| Email sent despite `FAILED` job | Email sent before commit | Store notification intent in outbox and publish after commit |
| Message published while business row rolled back | Broker not in database transaction | Transactional outbox/inbox |
| Item filtered yet side effect occurred | Side effect ran before returning `null` | Decide filter first, move side effects to writer |
| Item skipped yet reservation remains | Processor created reservation before validation failed | Validate first or use stateful compensation |
| Nested retries generate too many requests | Service retries and step retries stack | Partition retry budgets and timeouts |
| `processorNonTransactional` mistaken for rollback | Output cache only avoids some re-invocations | Still use idempotency and durable state |
| `afterWrite` sends notifications too early | `afterWrite` is not `afterCommit` | Outbox or commit-aware mechanisms |
| Cache claims item processed despite DB rollback | Mutable out-of-transaction in-memory state | Rebuild/invalidate cache from source of truth |
| Async processor runs outside transaction | Transaction context does not auto-propagate across threads | Design explicit transactions and idempotency |
| Compensation fails to run after crash | Undo invoked only in an in-memory callback | Persist durable compensation intents |
| Tests pass yet production duplicates occur | Mocked APIs or repositories only | Integration tests failing after side effects |

## 49. Design workflow for processors with side effects

1. **List side effects:** database, HTTP, broker, file, notification, cache, and audit.
2. **Identify transaction ownership:** does the side effect join the chunk transaction?
3. **Keep processors simple:** favor validation, mapping, calculation, and output DTOs.
4. **Move persistence to writers:** write business results and outbox rows in the same transaction when appropriate.
5. **Classify external calls:** read-only lookup or mutating operation?
6. **Design idempotency:** use operation/event keys stable across retries and restarts.
7. **Define retry/skip rules:** distinguish transient errors from business validation errors.
8. **Review filtering:** avoid side effects for ultimately excluded items unless required by business rules.
9. **Evaluate propagation:** avoid `REQUIRES_NEW`/separate connections if rollback with the chunk is needed.
10. **Use outbox or staging:** for messages, emails, files, and external publications needing reliability.
11. **Design compensation:** when side effects cannot roll back and compensating actions exist.
12. **Test real transactions:** verify database rollback, retry, skip, duplicates, and restarts.
13. **Monitor operations:** log business key, correlation ID, idempotency key, and status.

## 50. Principles to remember

- `ItemProcessor` should focus on validating, transforming, enriching, and filtering; avoid unnecessary side effects.
- Chunk transactions can cover processors, yet only undo changes participating in the same transaction resource.
- JDBC updates in a processor roll back with the chunk only when using the properly managed `DataSource`/transaction manager.
- `REQUIRES_NEW`, manually opened connections, and independent services/databases can commit outside the chunk.
- HTTP, email, brokers, and filesystems do not automatically roll back with database transactions.
- Processors may be re-invoked in retry/rollback paths; never assume each item is processed only once.
- `processorNonTransactional()` can cache outputs to avoid some re-invocations within the same execution; it does not undo side effects and is not a durable checkpoint.
- Returning `null` is filtering; side effects executed prior to returning `null` can still persist.
- Validate before side effects and let writers perform persistence whenever possible.
- Use stable idempotency keys for external operations and business keys/unique constraints for databases.
- Use transactional outboxes to store event intents alongside business data; consumers should implement inbox/deduplication.
- `afterWrite` does not mean the transaction committed; in-memory after-commit callbacks still have a crash window.
- Compensation is a separate business operation, not automatic rollback.
- Test with real transactions/databases and fake external services simulating timeouts after side effects occurred.
- Verify retry, skip, filter, rollback, restart, and duplicates in both outputs and external systems.

Processor side effects and rollbacks must be designed around actual transaction boundaries. When processors primarily produce repeatable results, writers own persistence, outboxes manage publication, and external operations use idempotency/compensation, Spring Batch can retry or restart without leaving duplicate side effects or half-completed business states.
