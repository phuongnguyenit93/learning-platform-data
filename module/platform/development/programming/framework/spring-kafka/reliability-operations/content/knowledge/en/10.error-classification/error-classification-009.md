# Database deadlock

In a Spring Kafka system, a **database deadlock** is a situation where two or more database transactions hold locks needed by other transactions, forming an unresolvable wait cycle. The database detects the cycle and typically selects one transaction as the deadlock victim, rolling it back to release locks for the remaining transaction.

Deadlocks commonly appear on consumers when multiple messages are processed concurrently and listeners update related rows. Kafka can deliver records in order within each partition, yet other consumers, services, or external requests can still update the same dataset concurrently. Therefore, a deadlock is a database transaction coordination error; it must be diagnosed via database lock graphs and queries, then mitigated by reducing lock contention, shortening transactions, and performing controlled retries.

In Spring Kafka, it is crucial to **let the database transaction roll back completely before retrying message processing**. If you retry inside a transaction already marked rollback-only, subsequent attempts do not run in a clean transaction and can continue failing.

## 1. What is a deadlock?

A transaction typically locks rows, pages, or other resources when reading or writing data. Locks help the database protect consistency when multiple transactions run concurrently.

A deadlock occurs when there is a cycle of lock dependencies. For example:

- Transaction T1 holds a lock on row A and needs a lock on row B.
- Transaction T2 holds a lock on row B and needs a lock on row A.
- T1 must wait for T2 to release B.
- T2 must wait for T1 to release A.

Neither transaction can proceed. The database detects the cycle and picks one transaction to roll back. The remaining transaction can then acquire the lock and proceed.

~~~mermaid
flowchart TD
    A["T1 holds lock on row A"] --> B["T1 waits for lock on row B"]
    C["T2 holds lock on row B"] --> D["T2 waits for lock on row A"]
    B --> C
    D --> A
    E["Database detects cycle"] --> F["Select deadlock victim"]
    F --> G["Roll back victim, release locks"]
    G --> H["Remaining transaction continues"]
~~~

A deadlock is not simply a slow transaction. The core issue is that transactions hold resources and wait on one another in a cycle.

## 2. Database-level deadlock example

Suppose a system has two tables:

- **orders** stores order status.
- **inventory** stores available stock per product.

One order-processing transaction updates the order and then decrements inventory. Another transaction updates inventory and then updates the order.

~~~sql
-- Transaction T1
BEGIN;

UPDATE orders
SET status = 'ALLOCATING'
WHERE order_id = 1001;

UPDATE inventory
SET available = available - 1
WHERE product_id = 77;

COMMIT;
~~~

~~~sql
-- Transaction T2
BEGIN;

UPDATE inventory
SET available = available + 1
WHERE product_id = 77;

UPDATE orders
SET status = 'AVAILABLE'
WHERE order_id = 1001;

COMMIT;
~~~

If T1 locks the row in orders first while T2 locks the row in inventory first, the two transactions can wait on each other's locks. The database will choose one transaction as the victim.

The statement order in this example illustrates one type of lock cycle. Real deadlocks also depend on execution plans, indexes, isolation levels, lock granularity, triggers, foreign keys, and other concurrent transactions. Only a deadlock graph from the database reveals the exact resources and statements involved in the cycle.

## 3. How does a deadlock differ from a lock wait timeout?

These two errors look similar in that a transaction fails to acquire a lock, but their causes and fixes differ.

| Characteristic | Deadlock | Lock wait timeout |
|---|---|---|
| Cause | A lock wait cycle exists among transactions | A transaction waited for a lock longer than the allowed timeout |
| Wait relationship | Forms a dependency cycle | Can be one-way, without a cycle |
| Database response | Usually selects a victim and rolls back automatically | Cancels or errors the waiting transaction depending on DB/config |
| Diagnostic evidence | Deadlock graph, victim, locked resources, SQL statements | Blocking session, lock hold duration, wait events |
| Remediation | Break the cycle via lock ordering, shorter transactions, lower contention | Reduce lock hold duration, find blocking transaction, tune timeout when justified |

Increasing the lock wait timeout does not resolve a deadlock cycle. A cycle will not disappear merely because transactions are allowed to wait longer; the database must detect and break the cycle.

## 4. How do database deadlocks appear in a Spring Kafka flow?

A consumer typically reads records, calls a business service, and updates the database. If multiple records are processed concurrently, database transactions can contend on the same rows or related groups of rows.

Example:

~~~mermaid
flowchart TD
    A["Kafka topic<br/>orders.events"] --> B["Consumer group"]
    B --> C["Consumer 1"]
    B --> D["Consumer 2"]
    C --> E["Listener processes event A"]
    D --> F["Listener processes event B"]
    E --> G["Database transaction T1"]
    F --> H["Database transaction T2"]
    G --> I["Same dataset / locks"]
    H --> I
    I --> J["Deadlock detector"]
    J --> K["Roll back one transaction"]
    K --> L["Listener/container receives error"]
    L --> M["Retry after rollback or recovery"]
~~~

Deadlocks can arise when:

- Multiple messages update the same order, account, inventory item, or aggregate.
- Listeners update multiple tables in inconsistent orders.
- A consumer group has high concurrency and processes many records simultaneously.
- Multiple services or HTTP requests update the database concurrently alongside consumers.
- Triggers, foreign key cascades, or indexes cause transactions to hold extra locks not directly visible in application code.
- Transactions hold locks while calling APIs or performing other slow work.

Kafka does not create deadlocks in the database. Kafka only delivers records to consumers; deadlocks occur when database transactions contend over shared resources.

## 5. Why do concurrency and partitions affect deadlocks?

Higher concurrency lets more listener invocations execute simultaneously. This often increases throughput, but also increases active database transactions and lock contention risk.

A topic with multiple partitions can distribute records across multiple consumers. If records from different partitions update the same inventory or account row, they can still deadlock even though each partition preserves its own ordering.

Partition keys can help maintain ordering for the same aggregate within one consumer group:

- Events with the same key usually land in the same partition.
- One partition within a consumer group is assigned to only one consumer at a time.
- Events on a partition are read in offset order.

This can reduce concurrent processing for the same aggregate within one group. However, it does not protect the database from other writers, other consumer groups, or HTTP requests updating the same rows. If two services modify the same account, partitioning by account ID on one topic does not automatically serialize all database transactions.

Do not scale concurrency based solely on partition count. Measure lock waits, deadlock rates, transaction durations, connection pools, and database capacity.

## 6. Symptoms and exceptions in Spring

Database drivers typically return vendor-specific errors. Spring JDBC, Spring Data, or Hibernate can translate those errors into Spring's exception hierarchy.

Common examples:

| Database | Common indicators |
|---|---|
| MySQL / InnoDB | Error 1213, SQLSTATE 40001: deadlock found when trying to get lock |
| PostgreSQL | SQLSTATE 40P01: deadlock detected |
| SQL Server | Error 1205: transaction was deadlocked on lock resources |
| Oracle | ORA-00060: deadlock detected while waiting for resource |

Actual details depend on driver, database version, and data access layer. Spring can wrap the underlying error into types such as **PessimisticLockingFailureException**, **CannotAcquireLockException**, or another specialized exception. Some older codebases may encounter **DeadlockLoserDataAccessException**.

Do not check only the outermost exception name. Record the cause chain, SQLState, vendor error code, and transaction details from database logs. Not every **PessimisticLockingFailureException** is a deadlock; it can also represent other locking errors.

### Distinguishing deadlocks from other database errors

- **ConstraintViolationException** or unique constraint errors are usually data violations, not lock cycles suitable for arbitrary retries.
- **CannotAcquireLockException** may reflect a deadlock or another lock acquisition failure depending on driver and exception translation.
- **DataIntegrityViolationException** usually requires data or business handling.
- **TransientDataAccessException** represents a broad category of transient errors; do not assume all of them are deadlocks.
- **Connection failure** or database unavailable is a connectivity/infrastructure incident requiring its own retry policy.

Classify based on the root exception and database error codes rather than solely on a generic class name.

## 7. Transaction boundaries in Spring applications

A listener should normally delegate database work to a service with its own transaction. When the service throws a deadlock error, the transaction interceptor rolls back the transaction before the exception returns to the listener container.

Example:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    private final OrderProcessingService processingService;

    public OrderEventListener(OrderProcessingService processingService) {
        this.processingService = processingService;
    }

    @KafkaListener(
        topics = "orders.events",
        groupId = "order-processor"
    )
    public void onOrderEvent(OrderEvent event) {
        processingService.process(event);
    }
}
~~~

Service managing the database transaction:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderProcessingService {

    private final OrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;

    public OrderProcessingService(
            OrderRepository orderRepository,
            InventoryRepository inventoryRepository) {
        this.orderRepository = orderRepository;
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public void process(OrderEvent event) {
        var order = orderRepository.findForUpdate(event.orderId())
                .orElseThrow();

        var inventory = inventoryRepository.findForUpdate(event.productId())
                .orElseThrow();

        inventory.reserve(event.quantity());
        order.markAllocated();
    }
}
~~~

In this example, repositories can use database-appropriate locking queries, such as pessimistic write locks. When the database detects a deadlock and throws an error, the service transaction rolls back. The listener receives the exception after the service call finishes, and the container can apply a retry policy.

### Why must the exception escape the transaction?

If the service catches the deadlock exception and continues returning normally, Spring may not receive the signal to roll back as expected. The transaction may also already have been rolled back by the database or marked rollback-only by Spring. Subsequent statements can fail, or the final commit can throw **UnexpectedRollbackException**.

When a deadlock occurs, let the exception cross the transaction boundary so the transaction terminates. Only then should you start a new attempt in a fresh transaction.

### Self-invocation and transaction proxies

Spring transactions are typically applied through proxies. If a method within the same object directly calls another **@Transactional** method, the internal call can bypass the proxy and the annotation may not start a new transaction as expected.

Extracting transactional business logic into a separate Spring service bean injected into the listener keeps transaction boundaries clear. When retrying outside the transaction, place the retry at the layer calling the transactional service through its proxy, or let the listener container retry after the previous transactional call has ended.

## 8. Retrying deadlocks properly

Deadlocks are typically temporary errors: the database rolled back one transaction so the other could proceed. Retrying can succeed once the competing transaction finishes. However, if data access patterns always form a lock cycle, continuous retries only repeat the same incident.

An appropriate retry must:

1. Let the failed transaction roll back completely.
2. Wait briefly before retrying.
3. Run each attempt in a fresh transaction.
4. Limit the number of retries.
5. Classify deadlocks as retryable; do not retry permanent data errors.
6. Once retries are exhausted, move to recovery/DLT or a recoverable workflow.
7. Ensure side effects are idempotent so redelivery does not duplicate impacts.

### Retrying at the listener container

When a listener method throws an exception outward, **DefaultErrorHandler** can retry the record per the configured BackOff. With a listener calling a database-transactional service, each container re-invocation calls the service again and opens a fresh transaction, provided the previous transaction rolled back before the exception escaped.

Illustrative configuration example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.PessimisticLockingFailureException;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.ExponentialBackOff;

@Configuration
public class KafkaErrorHandlerConfiguration {

    @Bean
    DefaultErrorHandler databaseRetryErrorHandler() {
        ExponentialBackOff backOff = new ExponentialBackOff(250L, 2.0);
        backOff.setMaxInterval(4_000L);
        backOff.setMaxElapsedTime(15_000L);

        DefaultErrorHandler handler = new DefaultErrorHandler(backOff);

        handler.addRetryableExceptions(
                PessimisticLockingFailureException.class
        );

        return handler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            DefaultErrorHandler databaseRetryErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(databaseRetryErrorHandler);

        return factory;
    }
}
~~~

This example illustrates Spring Kafka versions featuring **CommonErrorHandler** and **DefaultErrorHandler**. BackOff APIs and exception translation may differ depending on version. In production applications, register only the exception types that genuinely represent deadlocks or temporary locking failures for your database. If the driver throws vendor-specific exceptions not translated by Spring, classify the cause chain or translate errors in the data access layer.

Do not apply a generic retry configuration to all exceptions. Validation errors, invalid data, or business violations usually do not clear after a few attempts.

### Retrying inside a transactional service

Do not write a retry loop inside a method that has already opened a transaction:

~~~java
@Transactional
public void process(OrderEvent event) {
    for (int attempt = 0; attempt < 3; attempt++) {
        try {
            updateDatabase(event);
            return;
        } catch (PessimisticLockingFailureException ex) {
            // Unsafe to continue using a failed transaction.
        }
    }
}
~~~

After a deadlock, the current transaction may already be rolled back or marked rollback-only. Continuing to use it does not create an independent attempt.

If retrying at the service layer, structure it as a non-transactional method calling a transactional method through a proxy so each attempt starts a fresh transaction. Conceptual example:

~~~java
@Service
public class RetryingOrderProcessor {

    private final TransactionalOrderWriter writer;

    public RetryingOrderProcessor(TransactionalOrderWriter writer) {
        this.writer = writer;
    }

    public void processWithRetry(OrderEvent event) {
        // Retry outside the transaction.
        // Each call to writer.process() goes through the transaction proxy.
        writer.process(event);
    }
}

@Service
public class TransactionalOrderWriter {

    @Transactional
    public void process(OrderEvent event) {
        // Database operations within a short transaction.
    }
}
~~~

The snippet above only shows the boundary. To retry multiple times at the outer layer, add a retry mechanism with BackOff and an exception classifier, or rely on the listener container. Never build an unbounded retry loop.

## 9. When the listener uses Kafka transactions

If the listener container uses **KafkaTransactionManager**, the exception-handling path differs from a listener using only database transactions.

In a transactional listener container:

- The container starts a Kafka transaction for processing.
- The listener executes business logic and may send output records.
- If the listener throws an exception, the Kafka transaction rolls back.
- **AfterRollbackProcessor** handles seeking/redelivery and attempt counts after rollback.
- Once retries hit the limit, recovery can run per processor configuration.

If the listener also updates a database, clearly understand how database transactions and Kafka transactions coordinate. A Kafka transaction does not automatically roll back a database transaction, and a database deadlock must be handled by the database transaction manager.

Do not assume **DefaultErrorHandler** is the sole retry mechanism for transactional listener containers. With container transactions, configure and test **DefaultAfterRollbackProcessor** or an AfterRollbackProcessor matching your Spring Kafka version.

If the listener uses only database transactions via **@Transactional** and does not use Kafka transactions for the container, the listener container's error handler is usually the right place to retry exceptions after the database transaction rolls back.

## 10. Ensuring idempotency when Kafka redelivers records

Suppose a listener updates the database successfully, but the process stops before the Kafka offset is committed. When the consumer restarts, the record can be redelivered. Without idempotency, business logic may execute twice.

A common pattern is storing the event ID in an inbox table within the same transaction as the business update:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Idempotent event-processing service:

~~~java
@Transactional
public void process(OrderEvent event) {
    boolean inserted = processedEventRepository.insertIfAbsent(
            event.eventId(),
            Instant.now()
    );

    if (!inserted) {
        return;
    }

    orderRepository.apply(event);
}
~~~

This illustrative snippet requires **insertIfAbsent** to be implemented via a database-appropriate atomic operation, such as an insert with conflict handling or a unique constraint. Do not read-then-insert without a constraint because two consumers could concurrently see the event as absent.

The inbox marker and business changes must belong to the same database transaction. If the transaction rolls back due to a deadlock, the marker also rolls back; the retry can reprocess it. If the transaction commits while the Kafka offset has not committed, redelivery hits the unique event ID and avoids repeating side effects.

If business logic updates multiple tables, the marker must commit together with every change it protects. If the listener emits output events, use an outbox to persist output events in the same database transaction.

## 11. Common causes and how to reduce deadlocks

### Inconsistent lock acquisition order

This is the most recognizable cause. One flow updates table A then B, while another updates B then A. Standardize resource access order across all code paths.

For example, every flow updating orders and inventory acquires locks in the order:

1. orders row.
2. inventory row.
3. shipment row.

If an order contains multiple products, sort product IDs before locking so transactions acquire locks in the same order. Consistent ordering lowers the chance of wait cycles.

### Overly long transactions

The longer a transaction holds locks, the greater the chance another transaction collides on the same resources. Avoid:

- Calling REST APIs while a database transaction is open.
- Sending emails or calling external services inside a transaction.
- Waiting for messages or other threads while holding locks.
- Processing large files or running heavy calculations before committing.
- Executing unnecessary queries inside the transaction.

Prepare data outside the transaction when safe, then open a short transaction solely to read/write what is necessary. For external side effects, use an outbox or appropriate workflow.

### Missing indexes or overly broad locking queries

An UPDATE or SELECT FOR UPDATE without a proper index can scan and lock far more rows than intended. Query plans and indexes affect both the number of locked resources and lock hold times.

Inspect execution plans, WHERE clauses, indexes, foreign keys, and triggers. Avoid overly broad update conditions when business logic needs only one row. For locking queries, confirm the database uses the expected index.

### Oversized batches

A batch listener might update hundreds or thousands of records in one transaction. Long transactions holding many locks make deadlocks more likely.

Consider splitting into smaller chunks with a separate transaction per chunk. However, when chunking, define business semantics clearly: if an earlier chunk committed and a later chunk fails, records may be retried. Consumers must be idempotent or have business checkpoints to resume safely.

### Isolation levels and locking strategies

Higher isolation levels can increase lock counts or lock duration depending on the database. Pessimistic locking may be necessary under heavy contention, yet increases lock-wait likelihood. Optimistic locking with a version column can fit when conflicts are rare.

Do not lower isolation levels solely to reduce deadlocks without assessing dirty/inconsistent read risks. Choose strategies based on business invariants and database engine behavior.

### Reducing contention with partition keys and concurrency

If events for the same aggregate can be routed to the same partition, a consumer group processes those events sequentially. This can reduce contention on the same aggregate. Consider keys like **accountId**, **orderId**, or **inventoryId** depending on business boundaries.

Lowering listener concurrency can reduce simultaneously contending transactions, at the cost of throughput. Experiment using metrics for deadlocks, transaction duration, consumer lag, and database CPU/IO.

## 12. Diagnosing deadlocks using database data

Application logs usually tell you only that a transaction failed. A database deadlock graph or diagnostic report reveals the transactions, lock resources, and statements forming the cycle.

Information to collect:

- Timestamp and database instance.
- Transaction IDs or session IDs of involved parties.
- Running SQL statements and earlier statements that acquired locks.
- Locked tables, indexes, rows/pages, or resources.
- Lock mode of each transaction.
- Which transaction was chosen as the victim.
- Relevant isolation levels and execution plans.
- Event ID, topic, partition, offset, and consumer instance to correlate with the message.

### MySQL / InnoDB

InnoDB provides the latest deadlock details via **SHOW ENGINE INNODB STATUS**. In environments needing frequent investigation, consider logging deadlocks to the error log per DBA policy. Deadlock reports show transactions, held locks, awaited locks, and involved statements.

Do not enable excessive logging without considering disk capacity and operational policy. Capture reports near incident time because "latest detected deadlock" can be overwritten by a subsequent deadlock.

### PostgreSQL

PostgreSQL writes deadlock notices to server logs when a cycle is detected. Logging settings like **log_lock_waits** and **deadlock_timeout** help observe lock waits, though a logged lock wait does not mean every wait is a deadlock.

Combine server logs with **pg_stat_activity**, **pg_locks**, and query details to find blocking sessions and lock relationships. When a transaction is aborted by deadlock, SQLSTATE is typically **40P01**.

### SQL Server

SQL Server can capture deadlock graphs via Extended Events, commonly through the **xml_deadlock_report** event. The graph shows the victim, process list, and resource list. Use the graph to identify tables/indexes and lock order.

### Oracle

Oracle records deadlocks via **ORA-00060** messages and corresponding trace files. Traces help pinpoint involved statements and resources. DBAs should correlate execution plans, sessions, and transactions at failure time.

Tool names and log locations depend on version, DBA privileges, and system configuration. Applications should not attempt to query sensitive administrative views if their principals lack permission.

## 13. Logging and metrics on the Spring Kafka side

To link a database deadlock with the message that triggered it, application logs need consumer and business context.

Useful fields:

| Field | Purpose |
|---|---|
| service and environment | Identify workload |
| consumer group | Identify the group processing the record |
| topic, partition, offset | Locate the record in Kafka |
| event ID / correlation ID | Link to business logic and inbox/outbox |
| database transaction/session ID | Link to DB deadlock report if available |
| exception class, SQLState, vendor code | Classify the database error |
| retry attempt and backoff | Track recovery progress |
| processing duration | Detect slow transactions or listeners |
| instance / client ID | Identify the consumer creating the transaction |

Do not log passwords, tokens, connection strings with secrets, or full payloads containing sensitive data. Use event IDs and permitted fields to look up original data.

### Metrics to track

- Deadlock count by database and service.
- Number of transactions rolled back due to deadlocks.
- Lock wait duration and lock timeout counts.
- Listener failure rate by exception class.
- Retry attempts and recovery/DLT rates.
- Consumer lag by topic, partition, and group.
- Transaction duration and connection pool utilization.
- Throughput before and after concurrency adjustments.

Even a single deadlock that succeeds on retry must be tracked. If deadlock rates rise, retries only mask symptoms and can increase database load.

## 14. Retry, backoff, and DLT

Deadlocks are retryable because the database rolled back the victim and released locks. However, retries need bounds and pauses. If all consumers retry immediately, they can collide again on the same rows and create another wave of deadlocks.

A typical policy:

- Retry a small number of times.
- Use exponential backoff with a maximum cap.
- Add jitter when multiple consumers may retry simultaneously.
- Do not retry unrecoverable data errors.
- Once retries are exhausted, route the record to a DLT or observable, replayable recovery store.
- Alert when deadlocks cross thresholds or events stall too long.

A DLT is part of the recovery workflow, not a place to hide failures. When a record moves to a DLT, retain exception, event ID, original topic, partition, offset, and timestamp for investigation. Replays must preserve idempotency and respect ordering if required by the business.

If using a transactional listener container, recovery and offset commits must be configured through an appropriate AfterRollbackProcessor. If using only database transactions with a standard listener container, DefaultErrorHandler can be used after the database transaction rolls back.

## 15. Deadlocks in batch listeners

Batch listeners receive multiple records per invocation. If processing the whole batch in one transaction, the number of updated rows and held locks can be large. One deadlocking record can roll back the entire batch transaction.

Options:

- Reduce batch size to reduce the number of records and locks in one transaction.
- Split batches into chunks and commit per chunk if business semantics allow.
- Sort keys in a stable order before updating.
- Use per-partition sub-batches if per-partition processing/transaction boundaries fit.
- Rely on idempotency to tolerate partial work committed before a later failure.

Do not assume splitting batches by partition eliminates deadlocks. If two partitions still update the same account or inventory row, transactions can still contend. You must fix lock ordering or the database data model.

## 16. Production handling runbook

When consumers encounter database deadlocks:

1. Identify service, consumer group, topic, partition, offset, and event ID.
2. Collect root exception, SQLState, vendor code, and cause chain.
3. Record database instance, transaction/session ID, and timestamp.
4. Retrieve the deadlock graph or report from the database.
5. Identify the victim, surviving transaction, locked resources, and involved statements.
6. Check whether code paths updating the same tables/rows acquire locks in different orders.
7. Measure transaction duration, query plans, indexes, batch size, and consumer concurrency.
8. Confirm the database transaction rolled back before retrying.
9. Inspect error handler or AfterRollbackProcessor and actual retry counts.
10. Verify whether the event was partially processed; check inbox/idempotency.
11. Adjust lock ordering, transaction boundaries, queries/indexes, or concurrency based on evidence.
12. Re-test under production-like concurrent load.
13. Monitor deadlock rate, listener retries, DLT, consumer lag, and database load after deployment.

If retries succeed while deadlocks keep recurring, do not close the incident solely because the consumer kept moving. Document the root cause and plan to eliminate the lock cycle.

## 17. Testing deadlocks and recoverability

Deadlock testing should use the same database engine as production because locking behavior differs across databases. H2 or mock repositories cannot replace testing lock semantics of MySQL, PostgreSQL, SQL Server, or Oracle.

A controlled test scenario:

1. Prepare two rows A and B.
2. Open transaction T1 and lock A.
3. Open transaction T2 and lock B.
4. Have T1 request B.
5. Have T2 request A.
6. Confirm the database detects the deadlock and one transaction rolls back.
7. Confirm the service receives the exception after the transaction terminates.
8. Let the listener container retry the record per BackOff.
9. Confirm the retry runs in a new transaction.
10. Confirm side effects apply only once thanks to idempotency.
11. Confirm offsets commit only after listener/recovery finishes per configuration.

In automated tests, use barriers or latches to coordinate lock order rather than arbitrary sleeps. Keep finite timeouts so tests do not hang if no deadlock occurs. Clean up test data in separate transactions or fixtures.

### Scenarios to cover

| Scenario | Expected outcome |
|---|---|
| Deadlock occurs once | Victim rolls back; retry in a new transaction can succeed |
| Deadlock repeats beyond limit | Record goes to recovery/DLT per policy |
| Unique constraint error | Not retried like a deadlock if unrecoverable |
| Listener stops after DB commit before Kafka offset commit | Record may redeliver, but idempotency prevents duplicate side effects |
| Multiple consumers retry simultaneously | Backoff reduces collisions; deadlock rate is monitored |
| Batch contains one failing record | Transaction/chunk rolls back to the designed scope |
| DB unavailable | Apply connectivity policy; do not misclassify as deadlock |

## 18. Common mishandling patterns

**Retrying directly inside the failed transaction.** The transaction may already be rolled back or rollback-only. End the transaction and start a fresh attempt.

**Infinite retries.** Repeated deadlocks can increase database load, consumer lag, and rolled-back transactions. Bound attempt counts and add recovery.

**Simply increasing timeouts.** Timeouts do not break lock cycles. Use deadlock graphs to find the root cause.

**Reducing concurrency without measuring.** It can reduce contention while hurting throughput. Use before-and-after metrics to evaluate.

**Updating tables in different orders across services.** Standardize lock acquisition order across all code paths.

**Holding transactions open while calling external APIs.** Lock hold time and deadlock likelihood rise. Move network calls outside transactions or use outbox/workflows.

**Using oversized batches.** Transactions hold more locks longer. Split into chunks if business semantics permit.

**Catching exceptions and returning normally from listeners.** Containers can consider the message processed and advance offsets despite failed database transactions. Let errors cross the right boundary for retry/recovery.

**Routing every database exception to DLT.** Temporary errors can recover via retries. Classify exceptions and recover only after an appropriate retry policy.

**Assuming Kafka partitions eliminate deadlocks.** Partition ordering applies only within one topic-partition and one consumer group. Other writers can still contend on the same database rows.

## 19. Operational checklist

**Database diagnostics**

- [ ] Captured root exception, SQLState, and vendor error code.
- [ ] Collected deadlock graph or database report.
- [ ] Identified victim, surviving transaction, and locked resources.
- [ ] Inspected execution plans, indexes, triggers, and relevant foreign keys.
- [ ] Compared lock acquisition order across code paths.

**Spring transactions and retries**

- [ ] Database transaction ends/rolls back before the next retry.
- [ ] Each attempt uses a fresh transaction.
- [ ] Deadlock exceptions are intentionally classified as retryable.
- [ ] Backoff and retry counts are bounded.
- [ ] Unrecoverable data errors are not retried infinitely.
- [ ] Transactional listeners use an appropriate AfterRollbackProcessor if Kafka transactions are used.

**Kafka and business logic**

- [ ] Listeners do not swallow exceptions after DB rollback.
- [ ] Consumers have idempotency/inbox to tolerate redelivery.
- [ ] Batches/chunks have clear transaction boundaries.
- [ ] DLT/recovery retains enough metadata for investigation and replay.
- [ ] Offsets advance only per configured processing/recovery semantics.

**Observability and prevention**

- [ ] Logs include topic, partition, offset, event ID, and consumer instance.
- [ ] Timestamps/sessions can be correlated with database deadlock reports.
- [ ] Monitoring covers deadlock rate, rollbacks, retries, DLT, lag, and transaction duration.
- [ ] Lock order is standardized and transactions are kept short.
- [ ] Deadlocks tested against the actual database engine.

## 20. Handling principles

A database deadlock is a conflict between transactions holding and waiting on locks in a cycle. Kafka consumers can amplify concurrent transactions, yet the root cause lies in how the database accesses and locks resources.

In Spring Kafka, let the database transaction roll back completely, then retry the message in a new transaction with BackOff and clear limits. Use deadlock graphs to identify statements and resources forming the cycle; standardize lock order, shorten transactions, inspect indexes, and tune concurrency or batch size using metrics. Combine idempotency with offset commits so redelivered records never cause duplicate side effects.

## 21. Example implementing service-layer retry outside transactions

In some systems, teams prefer retrying at the service layer instead of container-level retries. In that case, retry advice must wrap a separate transactional method invoked through a Spring proxy. Each call to the transactional method starts a fresh transaction.

Example using Spring Retry if the application already includes its dependency and configuration:

~~~java
import org.springframework.dao.PessimisticLockingFailureException;
import org.springframework.retry.annotation.Backoff;
import org.springframework.retry.annotation.Retryable;
import org.springframework.stereotype.Service;

@Service
public class RetryingOrderApplicationService {

    private final TransactionalOrderWriter writer;

    public RetryingOrderApplicationService(TransactionalOrderWriter writer) {
        this.writer = writer;
    }

    @Retryable(
        retryFor = PessimisticLockingFailureException.class,
        maxAttempts = 4,
        backoff = @Backoff(delay = 250, multiplier = 2.0, maxDelay = 4_000)
    )
    public void process(OrderEvent event) {
        writer.write(event);
    }
}

@Service
public class TransactionalOrderWriter {

    @Transactional
    public void write(OrderEvent event) {
        // Lock rows in a consistent order and apply the database changes.
    }
}
~~~

Method **process** does not open a transaction. It calls **write** on another bean, allowing the writer's transaction proxy to create and finish a transaction per attempt. If an attempt fails due to a deadlock, the exception exits the writer after rollback; the retry interceptor re-invokes the method and opens a new transaction.

If both methods live in the same bean and the retry method calls the transactional method directly, self-invocation can bypass the proxy. Separating beans as shown makes boundaries explicit. When using Spring Retry, enable retry annotation support and verify advisor/interceptor ordering for your application version.

Do not enable multiple retry layers simultaneously without calculating total attempts. If the service retries four times and the container also retries four times, one record can generate up to sixteen database calls, excluding driver or downstream retries. Pick one primary owner for the retry policy, or establish a clear overall budget.

## 22. Choosing between container retry and service retry

| Criterion | Container error handler | Service retry |
|---|---|---|
| Scope | Entire listener invocation | A business operation or service call |
| Transaction boundary | Exception must escape transactional listener for container handling | Retry wraps a transactional method invoked via proxy |
| Use when | You want record-level retries and offset/recovery control in the Kafka listener | You want to reuse retry logic across non-Kafka callers |
| Recovery | Integrates with DLT/recoverer and offset handling | Service must propagate the final error to caller/container |
| Risk | Misconfiguration can retry unsuitable errors | Retrying inside a transaction or stacking multiple retry layers |

If retrying in the service, once attempts are exhausted let the exception escape to the listener so the container can apply final recovery. If the service swallows the error and returns normally, the container may commit the offset as a successful execution.

## 23. Defining a retry budget

A record can traverse multiple layers: Kafka client, listener container, service retry, and database driver. Each layer may have its own timeout or retry. Total processing time must stay within consumer poll and operational limits.

When designing, calculate:

- Maximum attempts at each layer.
- Initial backoff and multiplier.
- Maximum backoff.
- Maximum duration of a single database transaction.
- Maximum duration a listener invocation can run.
- **max.poll.interval.ms** and impact if batch processing runs long.
- How long an event may remain in backlog before alerting.
- DLT/replay policy once retries are exhausted.

Exponential backoff lowers the odds of consumers colliding repeatedly, though it does not guarantee deadlocks will disappear. If a deadlock stems from fixed lock ordering, retries may keep hitting the same cycle.

Some systems need jitter so consumers do not retry at the exact same instant. If a BackOff instance is shared, check randomization configuration capabilities for your Spring version and how handlers are instantiated. Never sleep inside a listener while a transaction remains open.

## 24. Handling data and side effects when partially completed

Deadlocks roll back the victim database transaction. If all related changes live inside that same transaction, the database restores them atomically. However, side effects outside the database may already have happened before the deadlock was detected.

For example, a listener calls a payment API, then updates the database and hits a deadlock. Database rollback cannot undo an already-succeeded API call. When the record is retried, the API may be called again.

To avoid this issue:

- Do not trigger external side effects before knowing the database transaction will commit unless idempotent.
- Use idempotency keys when calling external APIs.
- Use an outbox to emit events after the database transaction commits.
- Persist workflow state when a business process spans steps that cannot roll back together.
- Design compensating actions when atomic cross-system transactions are impossible.

Idempotency guarantees must cover the entire business operation that may be re-executed, not merely the final SQL statement.

## 25. When should the data model change?

If deadlocks happen frequently despite standardized lock order and short transactions, the data model or workload partitioning may be creating excessive contention.

Consider:

- Splitting a hot row into buckets or business shards if invariants permit.
- Using atomic updates instead of multi-step read-then-write where possible.
- Using optimistic locking/version columns when conflicts are low and resolvable.
- Routing sequential updates by aggregate key into a dedicated consumer group.
- Using appropriate queue/partition keys to serialize streams for the same aggregate.
- Designing smaller batches or chunked processing.
- Reducing the number of services that share write ownership over the same dataset.

Do not alter a schema solely to eliminate a single isolated deadlock. Use deadlock reports and metrics to prove a hotspot, then evaluate trade-offs in throughput, consistency, and scalability.
