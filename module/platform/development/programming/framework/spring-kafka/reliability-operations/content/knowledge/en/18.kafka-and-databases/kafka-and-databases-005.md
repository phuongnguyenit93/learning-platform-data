# KafkaTransactionManager with @Transactional

In a Spring Kafka system, business logic often has to update a **database** and then emit a **Kafka event**. For example, an order service saves the `OrderCreated` state to PostgreSQL and publishes a record to the `orders.events` topic. If the database commits while the Kafka publish fails, the system has an order with no event. If Kafka commits first while the database rolls back, downstream consumers see an event referencing an order that does not exist. This is one of the core reliability challenges when coordinating Kafka and a database.

`KafkaTransactionManager` lets Spring manage Kafka producer transactions under the `PlatformTransactionManager` abstraction; `@Transactional` declares transaction boundaries on Spring-managed Java methods. However, using these two components **does not turn Kafka and a database into an atomic distributed transaction**. Kafka and the database remain two resources with separate commits, and failure windows always exist that must be handled through compensation, reconciliation, or avoided via a transactional outbox.

This lesson explains how to configure `KafkaTransactionManager`, choose the transaction manager for `@Transactional`, synchronize Kafka transactions with database transactions, distinguish DB-first from Kafka-first, understand how transactional listener containers work, avoid AOP/rollback pitfalls, and ensure reliability during production incidents.

## 1. Three transaction concepts to distinguish

| Mechanism | Which resource is managed? | Guarantees | Does not automatically guarantee |
|---|---|---|---|
| Database transaction | JDBC/JPA and DB changes | Atomic DB commit/rollback within the DB | Successful Kafka publish |
| Kafka producer transaction | Kafka sends and, when designed properly, consumed offsets | Kafka writes commit/abort together | DB updates, HTTP/email inside the same transaction |
| DB/Kafka synchronization | Commit sequence between two local transactions | Coordinates lifecycles in order | Atomic distributed commit |

Example:

~~~text
                     Spring service
                            |
             +--------------+--------------+
             |                             |
             v                             v
    Database transaction             Kafka transaction
             |                             |
             v                             v
      DB COMMIT/ROLLBACK             Kafka COMMIT/ABORT

          No single shared COMMIT for both.
~~~

Key points:

- `@Transactional("kafkaTransactionManager")` manages the Kafka transaction; it does not automatically roll back the database.
- `@Transactional("transactionManager")`, if that bean is a DB manager, manages the DB; it does not automatically fold every Kafka send into one atomic transaction.
- A service can use both, but **the order of the two commits** determines the failure window rather than eliminating it.

## 2. What is KafkaTransactionManager?

`KafkaTransactionManager<K,V>` is the transaction manager for a Kafka producer. It uses a `ProducerFactory` with transactional support enabled to obtain a producer, start a Kafka transaction, and commit or abort when the transaction scope ends.

In a typical flow:

1. A transaction interceptor or listener container requests a new transaction.
2. `KafkaTransactionManager` obtains a transactional producer from the producer factory.
3. Spring binds the producer to the thread's transaction context.
4. `KafkaTemplate` uses the producer belonging to the active transaction when configured properly.
5. On success, the transaction commits; on errors matching rollback rules, it aborts.
6. The producer is closed or returned to the cache depending on the factory's lifecycle.

`KafkaTransactionManager` **does not manage JDBC Connections**, JPA EntityManagers, or HTTP API state. It is a local transaction manager for Kafka.

### 2.1. What a Kafka transaction covers

A Kafka producer transaction can group multiple records sent to Kafka topics/partitions. With a Kafka transactional listener container, consumed offsets can also be included in the same transaction as output records.

Conversely, simply placing `@Transactional("kafkaTransactionManager")` on a regular Kafka-sending method **does not automatically attach an arbitrary Kafka consumer's offsets** to the transaction. Offset commits in read-process-write must be handled properly by the listener container or Kafka consumer integration.

### 2.2. Technical prerequisites

- The Kafka cluster supports transactions.
- `ProducerFactory` is configured with a transactional ID prefix.
- `KafkaTemplate` participates in transactions through a compatible producer factory.
- Transactional IDs do not collide across concurrent instances.
- Code does not instantiate raw `KafkaProducer` objects outside the Spring factory on transactional paths.

If the producer is non-transactional, annotating the service method does not automatically turn it into a transactional producer.

## 3. Spring Boot configuration

Example configuring a producer capable of starting Kafka transactions:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: orders-instance-a-
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
~~~

`spring.kafka.producer.transaction-id-prefix` lets Spring Boot auto-configure a transactional producer factory and, when appropriate conditions are met, a Kafka transaction manager. The prefix name in the example is only illustrative for a single instance; production must design a **unique prefix per active instance**.

For example:

~~~text
instance A: orders-8f32-
instance B: orders-9b14-
instance C: orders-72a1-
~~~

Spring Kafka may append suffixes for each transactional producer in the pool/cache. If two pods run with the same transactional ID, the broker can fence the older producer. Fencing protects transactions from two producers claiming one identity; never ignore this error.

### 3.1. Custom configuration and auto-configuration

If the application defines custom `ProducerFactory`, `KafkaTemplate`, `KafkaTransactionManager`, or listener factory beans, do not assume Spring Boot applies all properties to your custom beans automatically.

Verify:

- `ProducerFactory` actually has a transactional ID prefix.
- `KafkaTemplate` uses the right `ProducerFactory`.
- `KafkaTransactionManager` uses the same compatible `ProducerFactory`.
- The listener container has a transaction manager if Kafka read-process-write EOS is required.
- Both old and new pods during rolling deployments do not generate colliding transactional IDs.

Inspect effective configuration values and bean wiring, not just `application.yml`.

## 4. Defining KafkaTransactionManager manually

When you need an explicit manager bean:

~~~java
@Configuration
public class KafkaTxConfiguration {

    @Bean
    KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager(
            ProducerFactory<String, OrderEvent> producerFactory) {
        return new KafkaTransactionManager<>(producerFactory);
    }
}
~~~

The example assumes `ProducerFactory` is already configured as transactional. If creating the factory manually, one way to enable the transaction prefix is:

~~~java
Map<String, Object> props = new HashMap<>();
props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class);
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        JsonSerializer.class);
props.put(ProducerConfig.ACKS_CONFIG, "all");

var producerFactory =
        new DefaultKafkaProducerFactory<String, OrderEvent>(props);
producerFactory.setTransactionIdPrefix("orders-instance-a-");
~~~

This snippet illustrates the producer factory API; in a real application, declare beans, configure serializers, and assign per-deployment identities. Never hardcode a shared prefix across multiple pods.

## 5. Which transaction manager does @Transactional pick?

In a project using both a database and Kafka, you may have:

- `JpaTransactionManager` or `DataSourceTransactionManager` for the DB.
- `KafkaTransactionManager` for Kafka.

Writing `@Transactional` without a qualifier makes Spring select a default transaction manager based on configuration, bean naming, or primary rules. When multiple managers exist, the wrong manager may be picked or Spring may fail to resolve a unique manager.

Specify it explicitly:

~~~java
@Transactional("kafkaTransactionManager")
public void publishEvents(...) { ... }

@Transactional("transactionManager")
public void updateDatabase(...) { ... }
~~~

`transactionManager` in the example must match **the actual DB manager bean name**. If your application uses `jpaTransactionManager`, pass that exact name.

### 5.1. Each @Transactional targets one primary manager

The annotation has no parameter meaning "commit both Kafka and the database simultaneously." Even if multiple annotated methods are invoked, each transaction manager governs a single resource. Coordinating them requires understanding how Spring transaction synchronization or nested boundaries work.

## 6. Using KafkaTransactionManager for multiple Kafka sends

A service that only needs multiple Kafka records to succeed or abort together can use a Kafka transaction directly:

~~~java
@Service
public class OrderPublisher {

    private final KafkaTemplate<String, Object> kafkaTemplate;

    public OrderPublisher(KafkaTemplate<String, Object> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("kafkaTransactionManager")
    public void publish(String orderId,
                        OrderCreated created,
                        OrderAudit audit) throws Exception {

        kafkaTemplate.send(
                "orders.events", orderId, created)
                .get(10, TimeUnit.SECONDS);

        kafkaTemplate.send(
                "orders.audit", orderId, audit)
                .get(10, TimeUnit.SECONDS);
    }
}
~~~

In this example, both sends share the same Kafka transaction when `KafkaTemplate` and the manager are wired properly. When the method finishes, the transaction manager commits Kafka; if the method throws an exception matching rollback rules, the transaction aborts. This gives atomicity over **Kafka outputs**, excluding the database.

Calling `get(...)` surfaces send errors inside the service call with a bounded timeout. Not every send must block in real applications, but exceptions and commit failures must be observed and never swallowed.

### 6.1. read_committed on downstream consumers

Consumers that must see only output from committed Kafka transactions must use:

~~~yaml
spring:
  kafka:
    consumer:
      isolation-level: read_committed
~~~

`read_uncommitted` can read records from aborted transactions. Therefore, enabling Kafka transactions on producers while downstream reads uncommitted records fails to deliver "committed outputs only" across the pipeline.

Not every topic necessarily contains only transactional records; `read_committed` does not prove all producers adhere to EOS.

## 7. How is KafkaTemplate.executeInTransaction different?

Another Kafka-only option is:

~~~java
String result = kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders.events", orderId, created);
    operations.send("orders.audit", orderId, audit);
    return "submitted";
});
~~~

`executeInTransaction` starts a local Kafka transaction for the callback. It is useful when you want transaction scope directly in code without relying on a transaction proxy.

Keep in mind:

- The callback is the template's own Kafka transaction; it does not make a DB transaction atomic with Kafka.
- It does not automatically add a listener's consumed offsets to the Kafka transaction.
- It is not equivalent to a transaction synchronized with an active Spring DB transaction.
- `KafkaTemplate` and its producer factory must support transactions.
- Commit or send failures must still be handled, never swallowed.

Do not call `executeInTransaction` inside a DB method thinking it automatically creates a "two-phase commit."

## 8. Database-first with database @Transactional

In certain Spring Kafka setups, a transactional `KafkaTemplate` can synchronize a Kafka transaction with an active Spring transaction. When the **database transaction is primary**, the application can update the database and call `KafkaTemplate` within the same service method:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderApplicationService(
            OrderRepository orderRepository,
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.orderRepository = orderRepository;
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("transactionManager")
    public void createOrder(CreateOrderCommand command) throws Exception {

        Order order = orderRepository.save(Order.from(command));
        OrderCreated event = new OrderCreated(order.getId());

        kafkaTemplate.send(
                "orders.events", order.getId(), event)
                .get(10, TimeUnit.SECONDS);
    }
}
~~~

This example assumes `transactionManager` is the DB manager and `KafkaTemplate` is configured to synchronize its Kafka transaction with the active Spring transaction. If `KafkaTemplate` is non-transactional, the send will not join a Kafka transaction.

### 8.1. Commit order in database-first

~~~text
BEGIN DB transaction
        |
        v
INSERT/UPDATE orders
        |
        v
KafkaTemplate.send() in synchronized Kafka transaction
        |
        v
Method returns
        |
        v
COMMIT DATABASE
        |
        v
COMMIT KAFKA TRANSACTION
~~~

Normally, the database transaction commits first and the Kafka transaction commits second. If both succeed, both the DB row and the Kafka event exist.

### 8.2. Failure window: DB commits, Kafka commit fails

~~~text
DB COMMIT succeeds
        |
        X crash / broker unavailable / Kafka commit fails
        |
Kafka output has not been confirmed as committed
~~~

Spring cannot roll back an already-committed DB transaction just because the subsequent Kafka transaction commit failed.

In Spring Kafka branches that propagate commit failures from synchronized transactions, an exception may be thrown to the caller; however, the committed DB data remains intact. The application needs **compensation or reconciliation**, or better yet a transactional outbox if events must never be lost.

An HTTP client retrying the entire `createOrder` call can also create a second order without a request ID/idempotency key and uniqueness constraint.

## 9. Kafka-first with two service beans

Some workflows require Kafka to commit before the DB. You can structure an outer DB method that calls a Kafka method annotated with `KafkaTransactionManager` on **a different bean**:

~~~java
@Service
public class KafkaFirstPublisher {

    private final KafkaTemplate<String, OrderCreated> template;

    public KafkaFirstPublisher(
            KafkaTemplate<String, OrderCreated> template) {
        this.template = template;
    }

    @Transactional("kafkaTransactionManager")
    public void publish(OrderCreated event) throws Exception {
        template.send(
                "orders.events", event.orderId(), event)
                .get(10, TimeUnit.SECONDS);
    }
}

@Service
public class OrderService {
    private final OrderRepository repository;
    private final KafkaFirstPublisher publisher;

    public OrderService(
            OrderRepository repository, KafkaFirstPublisher publisher) {
        this.repository = repository;
        this.publisher = publisher;
    }

    @Transactional("transactionManager")
    public void create(CreateOrderCommand command) throws Exception {
        Order order = repository.save(Order.from(command));
        publisher.publish(new OrderCreated(order.getId()));
    }
}
~~~

The Kafka method on the separate bean is invoked through the Spring proxy, allowing a separate Kafka transaction; it commits before the outer DB method finishes.

~~~text
BEGIN DB transaction
       |
       v
INSERT order (uncommitted)
       |
       v
BEGIN Kafka transaction
       |
       v
Kafka send
       |
       v
COMMIT KAFKA
       |
       v
COMMIT DB
~~~

This is Kafka-first via coordinated local transactions. It is not XA.

### 9.1. Failure window: Kafka commits first, DB rolls back later

If the Kafka commit succeeds but the DB commit fails, downstream consumers can observe `OrderCreated` even though the database has no order. This is dangerous if downstream immediately queries the DB upon receiving the event.

You need one of the following:

- Clear, meaningful compensation events.
- Downstream checking business state or version and retrying safely.
- Redesigning with the DB as the source of truth using a transactional outbox.
- Reconciling committed events against database records.

Reversing the commit order only shifts which side bears the risk; it does not eliminate the gap.

## 10. Why can't a single @Transactional cover both resources?

A service like the following is not enough to guarantee an atomic DB + Kafka commit:

~~~java
@Transactional
public void process(OrderCommand command) {
    repository.save(...);
    kafkaTemplate.send(...);
}
~~~

The annotation does not clarify which manager is used. If the manager is the DB manager, Kafka may synchronize as database-first under suitable conditions, yet the two commits remain separate. If the manager is the Kafka manager, the database is not automatically included in the Kafka transaction.

Some projects have used chained transaction managers to coordinate resources, including an older deprecated Spring Kafka API. Chained local transactions are still not equivalent to an atomic distributed transaction: the resource that commits first can succeed while the resource that commits second fails.

Start with the business question: "Which resource is the source of truth, if one commit fails who recovers, and how do we know whether a record was published?"

## 11. What does a transactional listener container change?

When a listener container is configured with a Kafka transaction manager, the container starts a Kafka transaction before invoking `@KafkaListener`. When the listener succeeds, the container sends consumed offsets into the same Kafka transaction as the outputs and commits.

~~~text
KafkaConsumer.poll()
         |
         v
Container BEGIN Kafka transaction
         |
         v
@KafkaListener reads OrderCreated
         |
         v
KafkaTemplate sends OrderProcessed
         |
         v
Container sends input offset to transaction
         |
         v
COMMIT Kafka output + input offsets
~~~

This is the basis of **Kafka-to-Kafka exactly-once semantics** for read-process-write. Outputs and consumed offsets commit or abort together inside the Kafka transaction. However, it does not guarantee the Java listener runs only once: crashes or rollbacks can cause redelivery.

### 11.1. Attaching the Kafka transaction manager to the factory

Example for Spring Kafka versions with `setKafkaAwareTransactionManager`:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
transactionalOrdersFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        KafkaAwareTransactionManager<?, ?> kafkaTransactionManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(kafkaTransactionManager);
    return factory;
}
~~~

Exact APIs may vary by Spring Kafka version. Older projects may use different setter names. Most importantly, **the listener must actually use the factory wired with the Kafka transaction manager**, and the output `KafkaTemplate` must use a compatible producer factory.

### 11.2. read_committed for downstream

Downstream consumers must use `read_committed` so they do not see records from aborted Kafka transactions:

~~~yaml
spring:
  kafka:
    consumer:
      isolation-level: read_committed
~~~

Do not switch to `read_uncommitted` just to see outputs earlier while transactions are awaiting commit. Doing so can expose aborted outputs to downstream processing.

## 12. Listener updating a database and writing to Kafka

Consider a listener with a container-managed Kafka transaction that internally calls a database service annotated with `@Transactional("transactionManager")`:

~~~java
@Component
public class OrderListener {
    private final OrderDbService dbService;
    private final KafkaTemplate<String, OrderProcessed> kafkaTemplate;

    public OrderListener(
            OrderDbService dbService,
            KafkaTemplate<String, OrderProcessed> kafkaTemplate) {
        this.dbService = dbService;
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
            topics = "orders.input",
            groupId = "orders-group",
            containerFactory = "transactionalOrdersFactory")
    public void onMessage(OrderCreated event) throws Exception {
        dbService.applyIdempotently(event);
        kafkaTemplate.send(
                "orders.processed",
                event.orderId(),
                new OrderProcessed(event.orderId()))
                .get(10, TimeUnit.SECONDS);
    }
}

@Service
public class OrderDbService {
    private final OrderRepository repository;

    public OrderDbService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional("transactionManager")
    public void applyIdempotently(OrderCreated event) {
        repository.applyIfNotProcessed(event.eventId());
    }
}
~~~

`applyIfNotProcessed` is an illustrative business method; production must enforce protection via database constraints and proper transactions.

Timeline:

~~~text
Container BEGIN Kafka transaction
       |
       v
Listener calls DB service
       |
       v
BEGIN DB transaction
       |
       v
DB update
       |
       v
COMMIT DB
       |
       v
KafkaTemplate.send()
       |
       v
Container COMMIT Kafka output + consumed offset
~~~

If the DB commits and then the Kafka transaction aborts due to a crash, the input is redelivered while the previous DB side effect already exists. **Idempotent DB updates** are mandatory to prevent duplicate writes even when Kafka outputs and offsets are handled transactionally.

### 12.1. Never manually ack/commit consumer offsets outside the transaction

The transactional listener container coordinates attaching offsets to the Kafka transaction. Never call `KafkaConsumer.commitSync()` manually or use a separate producer to "push offsets forward" to work around errors, as doing so can break atomicity with Kafka outputs.

### 12.2. Exceptions and after-rollback handling

When a transactional listener throws an exception, the Kafka transaction can abort. After-rollback handlers such as `DefaultAfterRollbackProcessor` decide seeking, retries, or record recovery per policy. Do not mechanically apply `DefaultErrorHandler` guidance for non-transactional containers without checking transaction-specific flow.

## 13. Transaction synchronization does not equal end-to-end EOS

| Design | Protected outcome |
|---|---|
| Kafka-only `@Transactional("kafkaTransactionManager")` | Kafka sends in the transaction commit/abort together |
| Kafka transactional listener + KafkaTemplate | Kafka outputs and consumed offsets commit/abort atomically in Kafka |
| DB `@Transactional` + Kafka synchronized producer | Two local commits in sequence; partial commit window still exists |
| Kafka-first nested local transactions | Kafka commits before DB; partial commit window still exists |
| DB transaction + outbox row | Business DB state and publish intent reside in the same DB transaction |
| Kafka consumer + DB inbox | Database processes idempotently when Kafka redelivers |

Never use the term "exactly-once" without stating **the exact scope**. Kafka EOS does not roll back HTTP calls, emails, database updates, or file writes.

## 14. Transactional outbox when the database is the source of truth

If the requirement is "once an order is saved, the Kafka event must eventually exist," directly synchronizing Kafka with the DB still carries the risk of DB commit succeeding while Kafka commit fails. **Transactional outbox** is an important approach to consider.

~~~text
Create order request
        |
        v
BEGIN DB transaction
        |
        +-- INSERT order
        |
        +-- INSERT outbox_event
        |
        v
COMMIT DB (atomic)
        |
        v
Outbox publisher / CDC
        |
        v
Kafka topic
~~~

Example:

~~~sql
CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    aggregate_id VARCHAR(120) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ
);
~~~

This illustrative schema fits PostgreSQL; production needs retention policies, partitioning, indexing, payload schemas, and cleanup.

Within one DB transaction, the service saves the entity and outbox row together. An independent publisher/CDC emits the event to Kafka and retries as needed. If the publisher crashes after a successful Kafka send and before marking the row published, the event can be republished. Thus outbox still requires **stable event IDs and idempotent consumers**, while eliminating the window where "DB committed with no publish intent left."

### 14.1. Why not just retry the DB-first method?

Once the DB has committed and Kafka commit fails, retrying the entire method can create extra entities or side effects. Outbox cleanly separates "create order" from "publish order event" and provides reconcilable state without re-running all business logic.

## 15. Inbox and idempotency for consumers updating a database

Kafka can redeliver a record due to:

- Consumer crashing before offset commit.
- Kafka transaction abort.
- Rebalance.
- DLT/replay.
- Recovery publisher resending a record.

If a listener updates a database, prevent duplicate side effects:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(120) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Within **the same DB transaction**:

1. Insert the event ID into the processed-events table protected by a unique constraint.
2. If the event ID already exists, recognize the data was already processed.
3. If new, execute the business DB update.
4. Commit the database transaction.
5. Let the listener complete and the container commit the offset per configuration.

The processed marker and business update must commit together so the marker never says "done" while business state remained unchanged.

Do not use Kafka's transactional ID as a business idempotency key: a transactional ID identifies a producer, not an event.

## 16. AOP proxies: @Transactional does not apply to every call

In standard proxy configurations, Spring `@Transactional` only takes effect when the call goes through the Spring proxy.

### 16.1. Self-invocation

~~~java
@Service
public class WrongOrderService {

    @Transactional("transactionManager")
    public void create() {
        publish();
    }

    @Transactional("kafkaTransactionManager")
    public void publish() {
        // A direct call within the same object may bypass the proxy.
    }
}
~~~

Having an annotation on `publish` does not prove a Kafka transaction starts. The straightforward fix is moving it to a separate service bean and calling it via Spring dependency injection, as shown in the Kafka-first example.

### 16.2. Other cases

- Objects created with `new` instead of Spring-managed beans.
- Methods not intercepted by proxies under the current configuration.
- Annotation selecting the wrong transaction manager.
- Exceptions caught and swallowed.
- Work handed off to a thread pool after the method returns.
- Transaction wrapping only task scheduling rather than task execution.

Write integration tests observing real committed/aborted outputs, not merely asserting that an annotated method was called.

## 17. Rollback rules and checked exceptions

Under standard Spring `@Transactional` rules, `RuntimeException` and `Error` trigger rollback by default; checked exceptions do not automatically roll back unless configured.

Example:

~~~java
@Transactional(
        transactionManager = "kafkaTransactionManager",
        rollbackFor = Exception.class)
public void publishOrder(OrderCreated event) throws Exception {
    kafkaTemplate.send("orders.events", event.orderId(), event)
            .get(10, TimeUnit.SECONDS);
}
~~~

`Future.get()` can throw checked exceptions such as `ExecutionException` or `InterruptedException`. If those exceptions are expected to trigger rollback, configure appropriate rules or translate them into domain exceptions with clear semantics. When handling interruption, preserve the interrupt flag if the catching layer intercepts it.

Do not set `rollbackFor=Exception.class` just "to be safe" if some checked exceptions represent business success or should not roll back; policy must match business semantics.

### 17.1. Catching an error and returning normally

~~~java
@Transactional("kafkaTransactionManager")
public void wrong(OrderCreated event) {
    try {
        kafkaTemplate.send("orders.events", event);
    }
    catch (Exception ex) {
        log.warn("Send failed", ex);
        // Wrong if you expect the transaction to roll back.
    }
}
~~~

If the transaction interceptor sees the method return normally, it may commit. Propagate the exception or mark rollback via the Spring API when policy demands it; never log an error and assume the transaction aborted.

## 18. @Async, CompletableFuture, and transaction boundaries

Transaction context is normally bound to a thread. Dangerous example:

~~~java
@Transactional("kafkaTransactionManager")
public void publishAsync(OrderCreated event) {
    executor.submit(() -> kafkaTemplate.send("orders.events", event));
    // Method finishes before the task completes.
}
~~~

A worker on another thread does not automatically join the caller's Kafka transaction. The transaction may commit when the method returns while the worker has not yet sent the output, or sends after the producer transaction has already ended.

If async execution is needed:

- Define a separate transaction inside the worker or workflow.
- Guarantee the task is durably persisted before the caller returns success.
- Never commit Kafka input offsets before outputs or recovery records are durably stored.
- Use an outbox when decoupling work from the request thread without losing events.

Do not assume using `CompletableFuture` inside a transactional method keeps the transaction open until the future finishes.

## 19. Transaction timeouts, producer cache, and fencing

Kafka producer transactions have timeouts and depend on the broker transaction coordinator. Transactions prolonged by HTTP requests, database locks, oversized batches, or broker lag can be aborted.

Factors to manage:

- Transaction timeout matched to listener processing time.
- Producer send timeouts and client retry/backoff.
- Transactional ID uniqueness.
- Producer cache lifecycle.
- Consumer group rebalances and graceful shutdown.
- Topic `min.insync.replicas`/`acks` when high durability is required.

### 19.1. ProducerFencedException

Two producers using the same transactional ID can cause the broker to fence the older producer:

~~~text
Pod A: transactional.id=orders-tx-1
Pod B: transactional.id=orders-tx-1
             |
             v
      Old producer fenced
             |
             v
     Transaction commit fails
~~~

Do not attempt to keep committing with a fenced producer; resolve the ID collision and recover the producer/container via Spring Kafka's supported lifecycle.

### 19.2. Producer factory maxAge

For lightly used producer caches, some Spring Kafka versions support `DefaultKafkaProducerFactory.maxAge` to refresh transactional producers before transactional ID state becomes stale relative to broker settings. Choose values based on broker expiration, workload, and Spring Kafka version; do not copy blindly from another system.

## 20. Error handling in transactional listeners and DLT

When a transactional listener throws an exception, the Kafka transaction aborts. Spring Kafka provides after-rollback mechanisms like `DefaultAfterRollbackProcessor` to decide seeking, retrying, recovering, or routing to a DLT.

If a record cannot be processed and must go to a DLT, ensure **DLT publishing and source offset confirmation** follow a safe recovery policy. Some configurations use a transactional `KafkaTemplate` and commit recovered offsets within the corresponding Kafka transaction. APIs like `commitRecovered` have version and transaction-manager prerequisites; check documentation for your exact dependency version.

Principles:

1. Never commit input offsets before outputs or DLT recovery are durably persisted.
2. Never ignore failures when the producer sends to the DLT.
3. The DLT producer needs serializers able to handle raw bytes on deserialization errors.
4. Recovery/DLT consumers must be idempotent when records are redelivered.
5. Test DLT broker-unavailable and ACL-denied cases to observe commit behavior.

### 20.1. Non-blocking retry topics are not a drop-in replacement

Spring Kafka has compatibility limitations between `@RetryableTopic` non-blocking retries and transactional listener containers; in many versions, combining them directly is not supported. Do not add retry topics and assume Kafka read-process-write EOS automatically spans the entire topology.

When long delayed retries are needed, design a separate recovery path and idempotency, or select a model with clear transaction boundaries per supported version.

## 21. Failure windows to remember

| Failure point | DB | Kafka | Risk |
|---|---|---|---|
| Before both commits | Rolled back | Aborted | Can be retried if idempotent |
| DB-first: DB commits, Kafka commit fails | Committed | Aborted/unknown | DB has state, event may be missing |
| Kafka-first: Kafka commits, DB commit fails | Aborted/unknown | Committed | Downstream sees event while DB state is missing |
| Transactional listener: DB commits, Kafka aborts | Committed | Output/offset uncommitted | Input redelivery; DB side effects may repeat |
| Kafka-only transaction aborts | Not applicable | Aborted | `read_committed` does not see aborted outputs |
| DLT send fails while source commits improperly | Depends | Recovery not persisted | Risk of record loss |

A Kafka commit failure can yield an unknown result at the caller layer; do not blindly resend an event with a new ID. Use a stable event ID, outbox publish state, or reconciliation to determine actual state.

## 22. Integration testing: do not just mock KafkaTemplate

To prove transaction behavior, you need a real Kafka broker or transaction-capable test broker alongside an appropriate test DB. Simply mocking `KafkaTemplate` does not prove atomic commit/abort.

### 22.1. Kafka-only commit

1. A `@Transactional("kafkaTransactionManager")` service sends two records.
2. Call succeeds.
3. Use a `read_committed` consumer to verify both records are visible.
4. Reconcile records and transaction outcome.

### 22.2. Kafka-only rollback

1. Inside the transactional method, send a record and then throw an exception.
2. Verify the transaction aborts.
3. Use a `read_committed` consumer to verify the aborted record is invisible.

### 22.3. DB-first partial commit

1. DB transaction updates a row and sends to Kafka via synchronization.
2. Simulate a Kafka commit failure after the DB commit.
3. Verify the DB row still exists.
4. Verify the application detects the condition and has reconciliation/outbox.
5. Verify HTTP caller retries do not create duplicate entities.

### 22.4. Kafka-first partial commit

1. Kafka transaction method commits.
2. Simulate DB rollback at the outer commit step.
3. Verify downstream `read_committed` sees the event.
4. Verify compensation or state validation.

### 22.5. Transactional listener + DB idempotency

1. Consumer receives input and the DB service updates.
2. Simulate a crash after the DB commit but before the Kafka transaction commit.
3. Input is redelivered.
4. DB inbox detects the event ID was already processed.
5. Kafka output + input offset commit as designed.

### 22.6. AOP, exceptions, async

1. Compare calling an annotated method through a proxy vs. self-invocation.
2. Test checked-exception rollback rules.
3. Test producer fencing.
4. Test that worker threads do not inherit transaction context.
5. Test DLT publish failure to confirm input is not lost.

Assert actual DB state, outputs visible to `read_committed`, and real consumer group offsets—not just a log line saying "transaction started."

## 23. Observability for Kafka and database systems

Metrics and logs should reflect both resources:

| Metric | Target |
|---|---|
| Kafka txn begin/commit/abort | Transaction success/failure rate |
| Kafka commit latency | Slow broker or network |
| Producer fencing errors | Transactional ID collision/lifecycle |
| Kafka send failure count | Record send errors |
| DB commit/rollback rate | Health of DB transactions |
| DB committed, Kafka failed cases | Inconsistency detection |
| Outbox backlog and oldest age | Unpublished events |
| Consumer lag and record age | Processing delay |
| Inbox duplicates | Redeliveries/replays |
| DLT publish/recovery failure | Health of recovery path |

Not all metrics exist with identical names in Spring Kafka. Several require Micrometer, Kafka client metrics, database monitoring, and application instrumentation.

### 23.1. Structured logging

Logs should include service, instance ID, request/event ID, topic, partition, offset, transaction stage, manager type, and exception class. Do not log secrets, PII, or full sensitive payloads. Avoid using event ID or offset as metric tags due to high cardinality; use traces/logs to locate specific events.

### 23.2. Alerts

- Sustained rise in Kafka transaction aborts.
- `ProducerFencedException` appearing after scale-out.
- DB commits succeeding while Kafka commits fail.
- Outbox backlog exceeding SLA.
- Kafka consumer lag rising due to slow transaction/DB processing.
- DLT/recovery publish failures.

Alert thresholds should tie to business SLOs rather than using one global threshold across all topics.

## 24. Runbook: DB has data, Kafka is missing the event

1. Identify entity ID, event ID, and DB commit timestamp.
2. Check whether the service uses DB-first synchronization or outbox.
3. Inspect Kafka transaction commit errors and broker status.
4. Confirm `KafkaTemplate` is actually transactional.
5. If an outbox exists, inspect the outbox row and publisher state.
6. If direct synchronization, execute appropriate reconciliation/compensation.
7. Never generate a new event ID before verifying whether the old event committed.
8. Verify downstream state after recovery.

## 25. Runbook: Kafka has the event, DB lacks the row

1. Determine whether the Kafka output belongs to a committed transaction.
2. Check whether Kafka-first commit order is in use.
3. Inspect database rollbacks, constraint violations, or commit timeouts.
4. Determine whether the event could have been published by another producer.
5. Check whether downstream uses `read_committed`.
6. Execute compensation or design DB state validation.
7. Consider an outbox if the DB is the source of truth.

## 26. Runbook: @Transactional does not roll back Kafka as expected

1. Check the transaction manager name in the annotation.
2. Verify the method is invoked through a Spring proxy.
3. Check whether an exception was caught and swallowed.
4. Check checked exceptions and `rollbackFor`.
5. Confirm `KafkaTemplate` uses a transactional `ProducerFactory`.
6. Check whether code uses a separate `executeInTransaction`.
7. Check whether an async worker crosses the transaction boundary.
8. Use a `read_committed` consumer to confirm whether output aborted.

## 27. Runbook: ProducerFencedException after deployment

1. Check transactional ID prefixes/suffixes across all pods.
2. Check whether rolling update or blue/green overlap occurred.
3. Verify unique instance ID assignment.
4. Inspect producer cache/lifecycle and transaction timeouts.
5. Never reuse a fenced producer to keep committing.
6. Recover the container/producer via proper lifecycle.
7. Monitor abort rate, lag, and outputs after fixing.

## 28. Common mistakes

**Confusing KafkaTransactionManager with a DB transaction manager.** The two managers govern two separate resources.

**Believing two nested @Transactional annotations create XA.** The first commit can succeed while the second fails.

**Omitting explicit manager selection.** The annotation may bind to an unintended manager.

**Self-invocation bypassing the proxy.** The annotation may not start a transaction.

**Swallowing Kafka send exceptions.** Returning normally can lead to commit even when intended outputs were not written.

**Using executeInTransaction inside a DB method and assuming atomicity.** A local Kafka callback transaction is not a distributed commit.

**DB-first without outbox or reconciliation.** Events can be lost after a DB commit.

**Kafka-first without compensation.** Downstream may receive events even when the DB rolls back.

**Forgetting database idempotency.** Kafka redelivery can apply DB updates multiple times.

**Sending async after the method returns.** Workers do not automatically join the transaction.

**Downstream using read_uncommitted.** Aborted Kafka records can appear.

**Not testing second-commit failures.** That is the most critical failure window.

## 29. Implementation checklist

### Kafka configuration

- [ ] ProducerFactory has a transactional ID prefix.
- [ ] Transactional IDs are unique across instances.
- [ ] KafkaTemplate and KafkaTransactionManager use compatible ProducerFactories.
- [ ] Listener container has a Kafka transaction manager if read-process-write EOS is needed.
- [ ] Downstream uses `read_committed` when transactional visibility is required.

### Spring transaction boundaries

- [ ] `@Transactional` selects the right manager bean.
- [ ] DB-first, Kafka-first, or Kafka-only model is explicitly chosen.
- [ ] Commit order and failure windows are documented.
- [ ] No self-invocation/async breaks transaction context.
- [ ] Rollback rules for checked exceptions match business semantics.

### Reliability and recovery

- [ ] DB-first has outbox/reconciliation if events must not be lost.
- [ ] Kafka-first has compensation when DB commit fails.
- [ ] Consumers updating the DB have inbox/idempotency.
- [ ] DLT/recovery publish errors are not swallowed.
- [ ] Retry/backoff limits and transaction timeouts are bounded.

### Validation and observability

- [ ] Test Kafka-only commit and rollback.
- [ ] Test DB-first/Kafka-first partial commits.
- [ ] Test listener redelivery after DB commit.
- [ ] Test fencing, rebalance, transaction timeout, and DLT failure.
- [ ] Metrics/alerts for Kafka aborts, DB rollbacks, outbox lag, consumer lag.
- [ ] Runbook exists for reconciling data between DB and Kafka.

## Conclusion

`KafkaTransactionManager` integrates Kafka producer transactions into Spring's transaction abstraction; `@Transactional("kafkaTransactionManager")` creates a Kafka send boundary that can commit or abort as a group. When the listener container also uses a Kafka transaction manager and compatible `KafkaTemplate`, Kafka outputs and consumed offsets can commit atomically within **Kafka read-process-write**. However, Kafka transactions do not automatically include database or HTTP side effects.

When coordinating a database with Kafka, **DB-first synchronization** and **Kafka-first nested transactions** only determine the commit order of two local transactions. Both leave a window where one resource has committed and the other fails; neither is distributed XA. If the DB is the source of truth and Kafka events must not be lost, transactional outbox is an essential choice. If a Kafka consumer updates a database, inbox/idempotency provides safety under redelivery. Finally, specify managers explicitly, understand Spring AOP proxies, manage transactional IDs carefully, and run fault-injection tests right at the second commit step before deploying to production.
