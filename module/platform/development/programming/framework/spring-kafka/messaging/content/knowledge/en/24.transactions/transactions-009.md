# Transaction Synchronization with DataSource

A business operation may both write data to a database and emit an event to Kafka. For example, when creating an order, the application saves the order into the `orders` table and sends an `OrderCreated` event so billing, inventory, or notification services can continue processing.

If the two operations run independently, a skewed state can occur: the database has committed while the event has not been sent, or the event has appeared in Kafka while the database rolled back. Spring Kafka supports transaction synchronization to coordinate a Kafka transaction with the transaction of another transaction manager, such as `DataSourceTransactionManager`.

Transaction synchronization lets Spring invoke commit or rollback on the second resource according to the lifecycle of the primary transaction. However, the database and Kafka remain two systems with separate transactions; the synchronization mechanism is not a distributed two-phase commit and does not provide absolute atomicity across the two systems. You must understand commit ordering and the remaining failure window to choose the right architecture.

This lesson belongs to the **Transactions** chapter of the **SPRING_KAFKA_MESSAGING** module. The module focuses on building event-driven applications using Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, understanding topics, partitions, offsets, and consumer groups, while learning serialization, retries, dead-letter handling, transactions, exactly-once, concurrency, and testing to operate reliable messaging pipelines.

## 1. The problem of writing to a database and sending to Kafka

Suppose the Order Service handles an order creation request:

1. Write the order to the database.
2. Send an `OrderCreated` event to the `order-events` topic.
3. Other services receive the event to process follow-up work.

Without transaction coordination, the two operations can end up in these states:

| Database | Kafka | Outcome |
| --- | --- | --- |
| Commit | Send succeeds | Desired state. |
| Rollback | Not sent | No order created and no event emitted. |
| Commit | Send fails | Order exists in DB, yet other services do not receive the event. |
| Rollback | Send succeeds | Consumers observe an event for an order that does not exist. |

The problem is that JDBC/JPA transactions and Kafka transactions are managed by two different resource managers. A database transaction does not automatically roll back a Kafka producer, and a Kafka transaction does not automatically roll back a database.

## 2. What is transaction synchronization?

The Spring Framework has a transaction synchronization mechanism to register callbacks tied to the current transaction lifecycle. A second resource can participate in synchronization by registering operations to run when the primary transaction commits or rolls back.

In Spring Kafka, `KafkaTemplate` can synchronize a Kafka transaction with an active transaction of another transaction manager when `ProducerFactory` is configured as transactional. A common pattern is making the database transaction the primary transaction while the Kafka transaction synchronizes with it.

High-level model:

~~~mermaid
flowchart TD
    A[Service method starts] --> B[DataSource transaction opens]
    B --> C[Execute SQL]
    C --> D[KafkaTemplate sends event]
    D --> E[Kafka transaction is synchronized]
    E --> F{Database transaction}
    F -->|Commit| G[Database commit]
    G --> H[Kafka transaction commit]
    F -->|Rollback| I[Database rollback]
    I --> J[Kafka transaction rollback]
~~~

In the common setup, the database transaction commits first, and the Kafka transaction commits afterward. If the database rolls back, the Kafka transaction rolls back via synchronization. If the database has already committed yet the Kafka commit fails, the database cannot automatically roll back; the application must have a recovery strategy for that failure gap.

## 3. Distinguishing transaction manager and transaction synchronization

Two transaction managers manage two different resources:

| Component | Managed resource | Role |
| --- | --- | --- |
| `DataSourceTransactionManager` | JDBC `Connection` | Commits/rolls back SQL operations. |
| `JdbcTransactionManager` | JDBC `Connection` | Variant of `DataSourceTransactionManager` with exception translation support. |
| `JpaTransactionManager` | JPA `EntityManager` | Manages JPA transactions and can coordinate with JDBC on the same `DataSource` depending on configuration. |
| `KafkaTransactionManager` | Kafka `Producer` | Opens, commits, and rolls back Kafka transactions. |
| Transaction synchronization | Spring transaction callbacks | Coordinates a secondary resource with the active transaction's lifecycle. |

The transaction manager defines the primary transaction opened by annotations or programmatic transaction calls. Transaction synchronization registers the secondary resource's behavior to coordinate commit/rollback.

Do not confuse synchronization with a single distributed transaction manager. Spring coordinates lifecycles, yet does not provide XA atomic commit between Kafka and a database merely because both are invoked inside one method.

## 4. Configuring a transactional Kafka producer

For `KafkaTemplate` to use Kafka transactions, `ProducerFactory` needs a transaction ID prefix. Spring Kafka uses the prefix to create transactional producers with distinct IDs per producer instance.

With Spring Boot, you can configure:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: order-service-instance-unique-tx-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
~~~

`transaction-id-prefix` enables transactional producer creation via `ProducerFactory`. The prefix must be unique across concurrently running application instances in the same cluster to prevent transactional ID collisions/fencing.

In Kubernetes environments, you can embed pod identity or a unique instance identity into the prefix. Do not hardcode the same static prefix across all replicas. `ProducerFactory` generates suffixes for producers managed within the factory; the application must ensure the base prefix does not collide across instances.

If creating `ProducerFactory` manually in Java, set the prefix:

~~~java
@Bean
public ProducerFactory<String, OrderCreated> orderProducerFactory(
        KafkaProperties kafkaProperties) {

    Map<String, Object> properties =
        kafkaProperties.buildProducerProperties();

    DefaultKafkaProducerFactory<String, OrderCreated> factory =
        new DefaultKafkaProducerFactory<>(properties);

    factory.setTransactionIdPrefix("order-service-instance-a-tx-");
    return factory;
}
~~~

The Java example only illustrates configuration. In a real application, the prefix value must be injected from deployment configuration and must differ across instances.

## 5. Configuring the `DataSource` transaction manager

If the application uses JDBC, `DataSourceTransactionManager` manages transactions on the JDBC `Connection`:

~~~java
@Bean
public PlatformTransactionManager dbTransactionManager(
        DataSource dataSource) {

    return new DataSourceTransactionManager(dataSource);
}
~~~

If the application uses JPA, `JpaTransactionManager` is typically used for the `EntityManager`:

~~~java
@Bean
public PlatformTransactionManager dbTransactionManager(
        EntityManagerFactory entityManagerFactory) {

    return new JpaTransactionManager(entityManagerFactory);
}
~~~

Do not declare two transaction managers managing the same transaction boundary without understanding how they interact. Choose the transaction manager matching the service's persistence technology and name beans clearly when the application context contains multiple managers.

When using Spring Boot, auto-configuration may already create a transaction manager for `DataSource` or JPA. Check existing beans before declaring a new one; avoid creating two competing managers for the same persistence context.

## 6. Sending events inside a `DataSource` transaction

When the database transaction is the primary transaction, the service method is annotated with `@Transactional` pointing to the right transaction manager bean. `KafkaTemplate` uses a transactional `ProducerFactory` to synchronize the send with the active transaction.

JDBC example:

~~~java
@Service
@RequiredArgsConstructor
public class OrderApplicationService {

    private final JdbcTemplate jdbcTemplate;
    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    @Transactional(transactionManager = "dbTransactionManager")
    public void createOrder(Order order) {
        jdbcTemplate.update(
            "insert into orders(id, status) values (?, ?)",
            order.id(),
            "CREATED"
        );

        OrderCreated event = new OrderCreated(
            order.id(),
            order.customerId(),
            order.total()
        );

        kafkaTemplate.send(
            "order-events",
            order.id(),
            event
        );
    }
}
~~~

Key points:

- The method executes inside the database transaction managed by `dbTransactionManager`.
- SQL statements and database changes belong to that transaction.
- `KafkaTemplate` uses a transactional producer and synchronizes a Kafka transaction with the active transaction.
- If the database transaction rolls back, the Kafka transaction rolls back via synchronization.
- When the database commits successfully, the Kafka transaction commits according to the default synchronization order.

Do not omit the transaction ID prefix and expect an ordinary Kafka send to roll back with the database. `ProducerFactory` must support transactions and `KafkaTemplate` must participate properly in transaction synchronization.

## 7. What happens when the method succeeds?

Suppose both SQL and Kafka send succeed:

~~~text
1. Spring opens the database transaction.
2. Service writes the order to the database.
3. KafkaTemplate sends OrderCreated in the synchronized Kafka transaction.
4. Method finishes normally.
5. Database transaction commits.
6. Kafka transaction commits.
7. Consumers using read_committed can read the committed event.
~~~

Consumer isolation level configuration:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        isolation.level: read_committed
~~~

`read_committed` ensures consumers read only records belonging to committed Kafka transactions and skip records from aborted transactions. It does not make consumers inspect the database; it applies strictly to Kafka transaction visibility rules.

If a consumer uses `read_uncommitted`, it may observe records from uncommitted transactions or transactions that are later aborted, depending on read position and transaction state. For events that must honor Kafka transaction visibility, configure `read_committed` on the corresponding consumers.

## 8. What happens when the database rolls back?

Suppose SQL succeeds, yet a subsequent business step throws an exception:

~~~java
@Transactional(transactionManager = "dbTransactionManager")
public void createOrder(Order order) {
    jdbcTemplate.update(
        "insert into orders(id, status) values (?, ?)",
        order.id(),
        "CREATED"
    );

    kafkaTemplate.send(
        "order-events",
        order.id(),
        toEvent(order)
    );

    throw new IllegalStateException("Business operation failed");
}
~~~

Spring rolls back the database transaction. The synchronized Kafka transaction is also rolled back. Consumers using `read_committed` do not see the event from the aborted Kafka transaction.

This is the main benefit of synchronization: preventing an event from being committed in Kafka when the primary database transaction rolls back, provided the Kafka send joined transaction synchronization properly.

If `KafkaTemplate` sends outside a transaction, uses a non-transactional `ProducerFactory`, or offloads the send to another thread without the transaction context, the outcome may differ. Ensure the send runs on the right thread and within the transaction boundary.

## 9. Commit order and the remaining failure window

In the common configuration where the database is the primary transaction, Spring commits the database first and then commits the Kafka transaction.

This creates a failure window:

~~~text
Database commits successfully
        |
        v
Application/cluster fails or Kafka commit fails
        |
        v
Database has the order, yet the event was not successfully published
~~~

Once the database has committed, Spring cannot roll back already-durable changes merely because the subsequent Kafka commit failed. Therefore, transaction synchronization does not guarantee absolute atomic commit across both systems.

If you reverse the order so Kafka commits before the database, the failure window flips: the Kafka event may be committed while the database commit fails. Changing the order does not eliminate the problem; it only shifts the kind of inconsistency that can occur.

Do not pick a commit order based merely on a sense of safety. Identify which system is the source of truth, the acceptable level of inconsistency, and how to recover.

## 10. Why isn't transaction synchronization XA?

XA/two-phase commit requires resource managers to participate in a distributed commit protocol with a coordinator and prepare/commit or rollback capabilities per the protocol.

Spring transaction synchronization primarily relies on transaction lifecycle callbacks. It can ask the second resource to commit or roll back after the primary transaction, yet there is no shared atomic prepare step spanning both a JDBC database and Kafka.

| Capability | Transaction synchronization | XA/2PC |
| --- | --- | --- |
| One primary transaction manager | Yes | Has coordinator |
| Commit/rollback callbacks for second resource | Yes | Follows prepare/commit protocol |
| Atomic commit across all resources | Not guaranteed | Achievable within XA-supporting resources |
| Potential failure window between two commits | Yes | Handled by protocol, with its own cost and operational risk |
| Fit for typical Kafka + JDBC | Commonly used for coordination | No shared XA by default for Kafka producer and JDBC |

Do not call synchronization a distributed transaction. The accurate phrasing is two local transactions coordinated via Spring's commit/rollback ordering.

## 11. Role of `KafkaTransactionManager`

`KafkaTransactionManager` manages Kafka producer transactions and can serve as the transaction manager for a method requiring only Kafka transactions:

~~~java
@Bean
public KafkaTransactionManager<String, OrderCreated>
        kafkaTransactionManager(
            ProducerFactory<String, OrderCreated> producerFactory) {

    return new KafkaTransactionManager<>(producerFactory);
}
~~~

A method using the Kafka transaction manager:

~~~java
@Transactional(transactionManager = "kafkaTransactionManager")
public void publishOrderEvent(OrderCreated event) {
    kafkaTemplate.send(
        "order-events",
        event.orderId(),
        event
    );
}
~~~

In this case, the transaction boundary is managed by `KafkaTransactionManager`. It fits when publishing multiple Kafka records in one transaction, or when a listener container needs Kafka transactions for consume-process-produce.

If the method also writes to a database, clearly define which transaction manager is primary and how the other is synchronized. Placing two annotations or injecting two managers alone does not create an atomic transaction.

## 12. Choosing the transaction manager for a method

When the application context has multiple `PlatformTransactionManager` beans, explicitly specify the manager in `@Transactional`:

~~~java
@Transactional(transactionManager = "dbTransactionManager")
public void updateDatabaseAndPublishEvent() {
    // Database transaction is the primary transaction.
}
~~~

Or:

~~~java
@Transactional(transactionManager = "kafkaTransactionManager")
public void publishSeveralKafkaRecords() {
    // Kafka transaction is the primary transaction.
}
~~~

Do not let a method rely on a default transaction manager if the application has both database and Kafka managers and bean names or primary selection are unclear.

If using meta-annotations or transaction manager qualifiers, establish a consistent convention across services. Code reviews should immediately identify the transaction boundary at method entry.

## 13. Beware of thread-bound transaction context

Standard Spring transactions are bound to the current thread. Transaction synchronization likewise relies on the resources and synchronization context of that thread.

Cases that can break coordination:

- Sending to Kafka on a thread created by an executor.
- Using `@Async` for the publish step.
- Calling `KafkaTemplate` from a callback running on another thread.
- Dispatching work to a scheduler or reactive pipeline without matching transaction configuration.
- Calling an internal method via self-invocation such that the `@Transactional` proxy is bypassed.

Example where transaction synchronization should not be expected:

~~~java
@Transactional(transactionManager = "dbTransactionManager")
public void createOrder(Order order) {
    jdbcTemplate.update(/* SQL */);

    executor.execute(() ->
        kafkaTemplate.send("order-events", order.id(), toEvent(order))
    );
}
~~~

The send runs on another thread, outside the method's transaction context. A database rollback will not automatically roll back that send.

If asynchronous processing is required, use an outbox or a durable handoff mechanism between the database transaction and the publisher. Do not rely on propagating `ThreadLocal` transaction context by manually copying state.

## 14. Propagation and nested transactions

Transaction propagation such as `REQUIRED`, `REQUIRES_NEW`, or `NESTED` affects database transaction boundaries. When a Kafka transaction is synchronized, examine which transaction it attaches to and when synchronization callbacks execute.

For instance, `REQUIRES_NEW` creates an independent database transaction. If the Kafka send happens inside that method, publishing may synchronize with the new transaction rather than the outer one, depending on how proxies and managers are invoked.

Do not use `REQUIRES_NEW` as a workaround for commit failures between DB and Kafka. It can make consistency boundaries even harder to reason about. Write tests for nested transaction boundaries if the business logic genuinely needs them.

Also watch out for self-invocation: calling another `@Transactional` method on the same instance normally bypasses the default Spring proxy, so propagation declared on that method may not take effect.

## 15. Sending multiple events within the same database transaction

A single database transaction can emit multiple Kafka events. When Kafka transactions synchronize properly, records sent in the same Kafka transaction commit or abort as a Kafka group.

Example:

~~~java
@Transactional(transactionManager = "dbTransactionManager")
public void completeOrder(Order order) {
    updateOrderStatus(order.id(), "COMPLETED");

    kafkaTemplate.send(
        "order-events",
        order.id(),
        new OrderCompleted(order.id())
    );

    kafkaTemplate.send(
        "billing-commands",
        order.id(),
        new CreateInvoice(order.id(), order.total())
    );

    kafkaTemplate.send(
        "inventory-commands",
        order.id(),
        new ReleaseReservation(order.id())
    );
}
~~~

If the database rolls back, the synchronized Kafka transaction also rolls back. If the database commits and the Kafka commit fails, the database is already done while the events may not be published. Monitor commit outcomes and maintain reconciliation or an outbox.

Kafka transactions guarantee that records in the Kafka transaction commit/abort as a group for consumers with `read_committed` isolation. They do not turn three downstream services processing concurrently into a distributed transaction.

## 16. Transaction synchronization with JPA

With JPA, you can use `JpaTransactionManager` as the primary transaction and send Kafka events in the same method:

~~~java
@Service
@RequiredArgsConstructor
public class JpaOrderService {

    private final OrderRepository orderRepository;
    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    @Transactional(transactionManager = "jpaTransactionManager")
    public void create(Order order) {
        orderRepository.save(order);

        kafkaTemplate.send(
            "order-events",
            order.getId(),
            new OrderCreated(order.getId(), order.getCustomerId())
        );
    }
}
~~~

JPA may defer SQL until flush/commit. If you need to detect constraint violations before publishing or ensure SQL runs before a business step, you can flush inside the transaction; however, flushing does not mean the database has committed.

Transaction synchronization still depends on a transactional producer configuration and an active manager. Test against a real or suitable embedded database to verify rollback and commit behavior rather than mocking repositories alone.

## 17. Transaction synchronization vs. transactional outbox

If the business requirement is never losing events once the database has committed, a transactional outbox is usually a better fit.

Within a single database transaction:

1. Write the order to the `orders` table.
2. Write an outbox row containing the event into the `outbox` table.
3. Commit both together.

A separate publisher reads the outbox and sends events to Kafka. On success, the publisher marks the row published, or uses CDC to transform database log entries into Kafka events.

~~~mermaid
flowchart TD
    A[Order service] --> B[Database transaction]
    B --> C[Update orders]
    B --> D[Insert outbox event]
    C --> E[DB commit]
    D --> E
    E --> F[Outbox relay or CDC]
    F --> G[Kafka topic]
    G --> H[Consumer services]
~~~

Outbox ensures the business change and the intent to emit an event are stored atomically in the same database transaction. The publisher can retry when Kafka is temporarily unavailable without losing events already committed in the outbox.

Outbox generally provides at-least-once semantics: the relay can send an event and crash before marking it published, causing the event to be re-sent. Consumers still require idempotency by event ID.

| Criterion | Transaction synchronization | Transactional outbox |
| --- | --- | --- |
| DB write and Kafka send | Same method, two local transactions coordinated | DB write and outbox row in one DB transaction |
| DB commit / Kafka commit gap | Present | Publisher retries from outbox |
| Complexity | Lower initially | Requires relay/CDC and outbox management |
| Resilience when Kafka is unavailable | Depends on commit/reconciliation | Events stay durable in the outbox |
| Duplicates | Possible on failure/retry | Possible when relay retries |
| Use case | Simple coordination where remedial action is acceptable | High reliability required for event emission after DB commit |

Outbox does not eliminate all errors or duplicates; it makes the intent to publish durable and retryable independently of Kafka transactions.

## 18. Inbox/idempotency on the consumer side

When a consumer receives an event, updating the database and committing the Kafka offset can also hit a failure window: the database commits successfully while the offset has not committed, so the event is read again.

The inbox pattern can help:

- Each event has a unique `eventId`.
- The consumer inserts `eventId` into a `processed_events` table within the same transaction as the business update.
- If `eventId` already exists, skip side effects and acknowledge the record per policy.
- If the transaction rolls back, both business changes and the processed marker roll back together.

Inbox handles duplicates from Kafka safely. It complements outbox on the producer side and idempotent handlers on the consumer side.

## 19. `ChainedKafkaTransactionManager` and the modern approach

`ChainedKafkaTransactionManager` was once used to chain multiple transaction managers, such as database and Kafka. This API has been deprecated in Spring Kafka since version 2.7; do not select it for new designs.

For modern applications, prefer Spring Kafka-supported transaction synchronization, explicitly choose the primary transaction manager, and understand commit order. If strong consistency between the database and Kafka is required, evaluate transactional outbox instead of trying to build a distributed transaction by chaining two managers.

When maintaining legacy applications using a chained manager, read the exact version's documentation and plan a migration. Do not alter manager ordering or transaction semantics in production without matching failure/recovery tests.

## 20. Testing transaction synchronization

Tests must verify both database state and Kafka visibility. Using Testcontainers for Kafka and the database helps validate real interactions between the two resource managers.

Scenarios:

1. Method succeeds: database row is committed and event appears to a `read_committed` consumer.
2. Exception thrown before commit: database rolls back and event does not appear to a `read_committed` consumer.
3. Kafka broker temporarily unavailable: observe commit error and verify DB/Kafka state per actual commit order.
4. Non-transactional producer factory: verify Kafka does not roll back with DB.
5. Sending event from another thread: verify transaction synchronization does not automatically propagate to that thread.
6. Multiple events in one transaction: verify Kafka records in the same transaction commit/abort as a group.
7. Multiple application instances: verify transaction ID prefixes do not collide and instances do not fence one another.
8. Outbox relay retry: verify the event is eventually published and consumers handle duplicates safely.

Success checks can use a test listener or dedicated consumer with `isolation.level=read_committed`. Use Awaitility or latches with timeouts to wait for records; avoid fixed sleeps.

For the failure window after database commit yet before Kafka commit, deterministically inducing a commit failure may require broker fault injection or a dedicated test harness. Do not write a test that merely simulates an exception inside the service and conclude you have tested commit failure between the two resources.

## 21. Observing transactions in production

Monitor:

- Database transaction duration and rollback count.
- Kafka transaction commit/abort count.
- Errors during producer transaction begin/commit/abort.
- Producer fencing and transactional IDs.
- Event send duration and send failure counts.
- Discrepancies between database state and downstream events if reconciliation exists.
- Outbox backlog and age of outbox rows if using outbox.
- Consumer lag and duplicate processing rate.

Logs should include correlation ID/`eventId` to link database operations with Kafka records. Do not log sensitive payload data. When a commit error occurs, distinguish database commit failures from Kafka commit failures because the durable state can differ.

With outbox, alert when an outbox row stays pending too long or the relay cannot publish. This is a key signal that an event has not left the database even though the business transaction committed.

## 22. Common misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| `@Transactional` on DB automatically rolls back any Kafka send. | Only when Kafka producer transactions are configured and sends join synchronization properly. |
| Transaction synchronization is XA/2PC. | It is callback coordination tied to the primary transaction lifecycle, not an atomic distributed commit. |
| When the database rolls back, already-sent events are always deleted. | Only true when the send ran in a synchronized Kafka transaction; non-transactional sends may already exist. |
| Injecting two transaction managers creates a single transaction. | They still manage two resources; you must define the primary transaction manager and synchronization. |
| DB and Kafka always commit at the exact same instant. | Commits happen sequentially; by default DB commits before Kafka in DB-primary mode. |
| Reversing commit order eliminates inconsistency. | It merely shifts the failure window from one direction to the other. |
| Kafka `read_committed` checks the database. | It filters only uncommitted/aborted Kafka transactions. |
| Sending to Kafka from `@Async` still joins the DB transaction. | Standard transaction context is thread-bound and does not automatically propagate to other threads. |
| `ChainedKafkaTransactionManager` is the modern choice. | That API is deprecated; prefer synchronization or outbox depending on requirements. |
| Transactional outbox guarantees zero duplicates. | The relay can resend; consumers still need idempotency. |

## 23. Design checklist

Before using transaction synchronization with `DataSource`, confirm:

1. The primary transaction manager is the appropriate `DataSource`/JPA manager.
2. `ProducerFactory` has a transaction ID prefix.
3. The prefix is unique across concurrently running instances.
4. `KafkaTemplate` uses that exact transactional `ProducerFactory`.
5. Kafka sends execute on the same thread and within the transaction boundary.
6. `@Transactional` explicitly specifies the manager when the application has multiple managers.
7. The DB-then-Kafka commit order in your configuration is understood.
8. Handling exists if Kafka commit fails after DB commit.
9. Consumers use `read_committed` when only committed Kafka transactions should be read.
10. Synchronization is not assumed to be XA or atomic commit.
11. Events are not dispatched to other threads if expecting the same transaction.
12. Transactional outbox has been evaluated for flows requiring guaranteed event emission.
13. Consumers have idempotency/inbox to handle redeliveries.
14. Integration tests cover commit, rollback, Kafka unavailable, and multiple instances.

Transaction synchronization with `DataSource` helps coordinate Kafka transactions alongside database transactions within a Spring flow. It can roll back Kafka when the database transaction rolls back and commit Kafka after the database commits by default. However, the two resources still commit separately and a failure window remains between commits. Choose synchronization when this level of coordination fits, and use transactional outbox when the intent to emit events must be durably persisted alongside database changes.



