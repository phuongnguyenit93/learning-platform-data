# Transaction-Capable ProducerFactory

In Spring Kafka, a producer can participate in a **Kafka transaction** only when the factory creating the producer is configured to support transactions. Therefore, before using `KafkaTemplate` in a transaction, what matters is not merely "whether `KafkaTemplate` can send a message" but **whether the `ProducerFactory` is transaction capable**, how transaction identity is managed, and where transactions are opened, committed, or aborted.

This topic belongs to the **Kafka Transactions** chapter of the **Spring Kafka Reliability Operations** module. When configured properly, multiple Kafka records can be committed or aborted as a single unit, and in a consume-transform-produce flow, the input record's offset can be committed in the same transaction that writes the output. When misconfigured, a service may still send events normally without a transaction, or fail at runtime because `KafkaTemplate` requires an active transaction.

This article focuses on **DefaultKafkaProducerFactory**, **transactionIdPrefix**, **transactionCapable()**, wiring with **KafkaTemplate** and **KafkaTransactionManager**, as well as atomicity boundaries, producer fencing, caching, lifecycle, and production operations.

## 1. What Is ProducerFactory Responsible For?

In Spring Kafka, **ProducerFactory<K, V>** is the abstraction that creates Kafka producers. Applications typically use **DefaultKafkaProducerFactory<K, V>** and inject that factory into `KafkaTemplate`.

~~~mermaid
flowchart LR
    A["Business service"] --> T["KafkaTemplate"]
    T --> F["ProducerFactory"]
    F --> P["KafkaProducer"]
    P --> B["Kafka brokers"]
~~~

`ProducerFactory` is responsible for creating and managing producers according to configuration:

- Bootstrap servers and security.
- Key/value serializers.
- Producer acknowledgments, retries, and delivery timeouts.
- Transactional ID and transactional producer lifecycle when transactions are enabled.
- Producer caching/reuse, closing producers, and resource cleanup.

`KafkaTemplate` is the application-level API for sending records. It **does not turn a regular producer into a transactional producer by itself**. Transactional capability comes from the factory configuration and having the appropriate transaction context when sending.

### 1.1 Two States to Distinguish

A `ProducerFactory` can be:

1. **Not transaction capable**: creates producers that send non-transactional records. `KafkaTemplate` can still send normally.
2. **Transaction capable**: can create transactional producers and manage `transactional.id`; `KafkaTemplate` can send within a Kafka transaction.

Spring Kafka provides the **ProducerFactory.transactionCapable()** contract to indicate whether a factory supports transactions under its current configuration.

Example startup check:

~~~java
@Component
public class KafkaTransactionConfigurationCheck {

    public KafkaTransactionConfigurationCheck(
            ProducerFactory<String, String> producerFactory) {

        if (!producerFactory.transactionCapable()) {
            throw new IllegalStateException(
                "ProducerFactory must support Kafka transactions"
            );
        }
    }
}
~~~

This is an appropriate guard when business logic requires transactions and must not silently run in non-transactional mode. If a service has multiple `ProducerFactory` beans, check the **exact factory** used by the transactional `KafkaTemplate` or listener container.

### 1.2 Transaction Capable Does Not Mean an Active Transaction Exists

A factory having transaction capability does not mean every thread or every send is inside a transaction. There are three distinct layers:

| Layer | Question |
|---|---|
| ProducerFactory capability | Can it create and manage transactional producers? |
| Transaction boundary | Is there an open transaction for this send? |
| Kafka transaction outcome | Did the transaction commit, abort, or remain uncertain? |

To get atomic record groups, the application needs both capability and a transaction boundary. Furthermore, you must know the commit outcome rather than relying solely on `KafkaTemplate.send()` returning a future.

## 2. How Transactional Producers Differ from Idempotent Producers

A producer with **enable.idempotence=true** helps the broker detect and deduplicate certain duplicate sends caused by producer retries within the same producer session. That helps reliability, but **does not place multiple records into a single transaction**.

A transactional producer adds a mechanism to commit or abort a group of records and can coordinate committing consumer offsets in the Kafka transaction.

| Property | Idempotent producer | Transactional producer |
|---|---|---|
| Reduces duplicates from producer retries | Yes | Yes; idempotence is a prerequisite |
| Commits/aborts a group of records | No | Yes |
| Writes across multiple partitions/topics in one transaction | No | Yes |
| Sends consumer offsets into the same Kafka transaction | No | Yes |
| Requires `transactional.id` | No | Yes |
| Downstream `read_committed` filters out aborted records | No aborted transactions | Yes |
| Makes HTTP/DB side effects atomic with Kafka | No | No |

For example, a service needs to emit two output events:

~~~text
OrderAccepted
    -> orders.audit
    -> orders.notification
~~~

If sent non-transactionally, the first record might be accepted by the broker and then the second send fails. The two topics end up with an inconsistent published state.

If both sends are in **the same Kafka transaction**:

- Commit succeeds: `read_committed` consumers can observe both records once the transaction finishes.
- Abort: `read_committed` consumers do not receive records belonging to the aborted transaction.
- Transaction still in progress: `read_committed` consumers may have to wait at the Last Stable Offset of the affected partitions.

`read_uncommitted` consumers can observe transactional records before commit or records that are later aborted. Thus, the downstream read contract is also critical.

## 3. Conditions for DefaultKafkaProducerFactory to Be Transaction Capable

In Spring Kafka, the standard way is configuring a **transaction ID prefix** on `DefaultKafkaProducerFactory`.

~~~java
DefaultKafkaProducerFactory<String, String> factory =
    new DefaultKafkaProducerFactory<>(producerProperties);

factory.setTransactionIdPrefix("orders-service-instance-a-");
~~~

When a prefix is present, the factory can create transactional producers with a managed **transactional.id** built from the prefix and an appropriate suffix. Adding a suffix allows multiple producers to be created or cached in the same application without all contending on a single transactional ID.

A single prefix is only an example. In a multi-replica system, the prefix must be unique across **concurrently active application instances**.

### 3.1 Do Not Set One Static transactional.id for Every Instance

Dangerous configuration regarding ownership:

~~~properties
transactional.id=orders-service
~~~

If multiple producer instances share this `transactional.id`, Kafka will use producer epoch/fencing to prevent older producers from continuing to write transactions. This can cause pods to continuously fence one another instead of operating stably.

In Spring Kafka, prefer letting `DefaultKafkaProducerFactory` manage `transactional.id` from a **transactionIdPrefix** with a clear per-instance uniqueness rule. Never hard-code one static ID across a whole deployment and treat it as a scale-out configuration.

### 3.2 transactionIdPrefix Is a Per-Instance Identity

An illustrative convention:

~~~text
orders-service-prod-<instance-id>-
~~~

Example of three concurrently running instances:

~~~text
orders-service-prod-instance-01-
orders-service-prod-instance-02-
orders-service-prod-instance-03-
~~~

Each instance can create multiple transactional producers within its own prefix scope.

Goals:

- **Same deployment, multiple concurrent pods:** prefixes do not collide.
- **Restarting a logical instance:** can reuse a stable identity if lifecycle ownership is clear; the old producer will be fenced when the new instance claims the corresponding transactional ID.
- **Rolling deployments:** watch the overlap window when old and new pods run simultaneously; do not share prefixes unless fencing is intentional.
- **Scaling concurrency:** the factory may need multiple transactional producers simultaneously; suffixes/caching distinguish each producer belonging to the same instance.

Do not use a value that changes on every message send as the prefix. A transaction ID is not a request ID or an event ID. It is a long-lived identity for a transactional producer used by Kafka to manage epochs and fencing.

### 3.3 transactionCapable() Is a Check, Not a Command to Open a Transaction

When `factory.transactionCapable()` returns `true`, it only proves the capability to create transactional producers under the factory configuration. That call **does not**:

- Open a Kafka transaction.
- Send an event.
- Commit consumer offsets.
- Commit database data.
- Guarantee that every `KafkaTemplate` in the application uses this factory.

When multiple factories exist, checking factory A says nothing about a `KafkaTemplate` that actually uses factory B.

## 4. Enabling Transactions via Spring Boot

Spring Boot supports configuring the producer transaction ID prefix via a dedicated property:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092

    producer:
      transaction-id-prefix: orders-service-instance-a-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer

      properties:
        acks: all
        enable.idempotence: true
        transaction.timeout.ms: 60000
~~~

In real projects, **transaction-id-prefix** must be supplied uniquely per running instance via a stable/unique configuration source managed by the deployment. The `instance-a` value in the example is for a single instance only.

Key points:

- **spring.kafka.producer.transaction-id-prefix** is the Spring Boot property for creating a transactional producer factory.
- **transaction.timeout.ms** is the producer's transaction timeout, which may be capped by the broker's `transaction.max.timeout.ms` setting.
- **acks=all** is an important choice for producer durability; transactions do not replace topic replication/ISR configuration.
- **enable.idempotence=true** illustrates explicit intent. Kafka transactional producers require idempotence; the client/framework also enforces or requires compatible settings.

Setting `transaction-id-prefix` **does not automatically turn a `@KafkaListener` into a consume-transform-produce transaction** if the listener container is not configured with corresponding transaction support.

### 4.1 Spring Boot Can Create KafkaTransactionManager

In many Spring Boot versions, when producer `transaction-id-prefix` is configured with auto-configuration, Boot can automatically configure a matching **KafkaTransactionManager**.

However, in applications that define custom `ProducerFactory`, `KafkaTemplate`, or listener container factory beans, do not assume all beans wire together automatically. Verify:

- Which `ProducerFactory` is used by `KafkaTransactionManager`.
- Which `ProducerFactory` is used by `KafkaTemplate`.
- Whether the listener container factory uses Kafka transaction management.
- Whether multiple different `PlatformTransactionManager` beans exist in the application.

If configuring everything manually, you can declare `KafkaTransactionManager` as shown in the next section.

### 4.2 Unintended Property Overrides

Spring Boot merges properties from many sources, including profiles, environment variables, Helm/ConfigMaps, command-line arguments, and Java configuration. If production and staging connect to the same Kafka cluster, prevent transactional ID prefix collisions across concurrently live instances.

Example of a hard-to-spot bug:

~~~text
application.yml: transaction-id-prefix = orders-service-prod-a-
Kubernetes env: override prefix      = orders-service-prod-a-
Pod A and pod B share that prefix
=> Producer fencing may occur
~~~

Reading `application.yml` alone is not enough. Inspect the effective runtime configuration and observe actual `transactional.id` values when investigating fencing incidents.

## 5. Creating ProducerFactory in Java

When an application needs a custom producer factory, you can instantiate `DefaultKafkaProducerFactory`, configure serializers, and call `setTransactionIdPrefix()`.

~~~java
@Configuration
public class KafkaProducerConfiguration {

    @Bean
    ProducerFactory<String, String> orderProducerFactory() {

        Map<String, Object> props = new HashMap<>();

        props.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "kafka-1:9092,kafka-2:9092,kafka-3:9092"
        );
        props.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class
        );
        props.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class
        );
        props.put(
            ProducerConfig.ACKS_CONFIG,
            "all"
        );
        props.put(
            ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG,
            true
        );

        DefaultKafkaProducerFactory<String, String> factory =
            new DefaultKafkaProducerFactory<>(props);

        // Illustrative for a single application instance only.
        // Production must assign a unique prefix per instance.
        factory.setTransactionIdPrefix(
            "orders-service-instance-a-"
        );

        return factory;
    }

    @Bean
    KafkaTemplate<String, String> orderKafkaTemplate(
            ProducerFactory<String, String> orderProducerFactory) {

        return new KafkaTemplate<>(orderProducerFactory);
    }

    @Bean
    KafkaTransactionManager<String, String> kafkaTransactionManager(
            ProducerFactory<String, String> orderProducerFactory) {

        return new KafkaTransactionManager<>(orderProducerFactory);
    }
}
~~~

The factory, `KafkaTemplate`, and `KafkaTransactionManager` all receive **the exact same `ProducerFactory` instance**. This reduces the risk of the template sending via a regular producer while the transaction manager coordinates a different transactional producer.

In a real application, bootstrap servers, credentials, serializers, prefixes, and timeouts should come from deployment properties. The example above uses fixed values intentionally to clarify the dependency graph, not as a multi-replica production deployment pattern.

### 5.1 Verifying the Factory Is Transaction Capable

You can add a startup check:

~~~java
@Bean
ApplicationRunner validateTransactionalFactory(
        ProducerFactory<String, String> orderProducerFactory) {

    return args -> {
        if (!orderProducerFactory.transactionCapable()) {
            throw new IllegalStateException(
                "orderProducerFactory is not transaction capable"
            );
        }
    };
}
~~~

A configuration error caught at startup is much easier to fix than having the service run for hours before hitting a business branch that needs a transaction.

### 5.2 Multiple ProducerFactories in the Same Application

A service might send both non-transactional telemetry and transactional business events.

~~~text
Business KafkaTemplate
  -> transactional ProducerFactory
  -> KafkaTransactionManager

Telemetry KafkaTemplate
  -> non-transactional ProducerFactory
  -> independent sends
~~~

Do not apply `@Transactional` and assume it manages every `KafkaTemplate`. A transaction manager coordinates only producers from its matching factory. Other templates may behave differently.

If you need to send messages outside a transaction using a `KafkaTemplate` backed by a transactional factory, Spring Kafka provides configuration options such as **allowNonTransactional** in supported versions. This must be a deliberate choice, because it allows some sends to bypass transactions. Do not enable it just to "silence an error" without checking atomicity requirements.

## 6. Kafka Transaction Lifecycle

A Kafka transactional producer follows a logical lifecycle:

~~~mermaid
flowchart TD
    A["ProducerFactory creates/obtains producer"] --> B["initTransactions if needed"]
    B --> C["beginTransaction"]
    C --> D["send record A"]
    D --> E["send record B"]
    E --> F{"Processing succeeded?"}
    F -->|Yes| G["commitTransaction"]
    F -->|No| H["abortTransaction"]
    G --> I["Records visible to read_committed"]
    H --> J["Records filtered out from read_committed"]
~~~

A Kafka transaction can include records across multiple topics and partitions. When commit completes, transactional records become eligible for `read_committed` consumers. When aborted, that transaction's records are not returned to `read_committed` consumers.

**`transactionCapable=true` does not replace begin/commit/abort.** Those operations are normally orchestrated by `KafkaTemplate` or `KafkaTransactionManager` with Spring's transaction infrastructure, sparing the application from managing the producer manually.

### 6.1 A Transaction Must Have an End

A transaction left open too long can:

- Hold back the Last Stable Offset (LSO) on participating partitions.
- Prevent `read_committed` consumers from reading past the open transaction.
- Increase end-to-end latency.
- Hit the transaction timeout and get aborted.
- Hold producer resources longer than expected.

Do not wrap a multi-minute workflow or unbounded HTTP waits inside a Kafka transaction if it can be broken into shorter steps.

### 6.2 A Kafka Transaction Is Not an HTTP Request Transaction

A Kafka send enters a transaction when the right transactional producer is used. However, calling a REST API or writing to a database in the same Java method is not automatically managed by the Kafka broker.

~~~text
begin Kafka transaction
  -> send Kafka record
  -> call external HTTP API
  -> commit Kafka transaction
~~~

If the HTTP API succeeds and the Kafka commit later fails, the HTTP side effect has already occurred. Kafka cannot automatically roll back responses from external systems.

Therefore, producer transactions primarily solve atomicity within **Kafka**, not distributed transactions spanning every service dependency.

## 7. Using KafkaTemplate.executeInTransaction

When you need to send multiple records in a Kafka transaction within a specific block of code, you can use `KafkaTemplate.executeInTransaction()`.

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publishTwoEvents(String orderId) {
        kafkaTemplate.executeInTransaction(operations -> {

            operations.send(
                "orders.audit",
                orderId,
                "ORDER_ACCEPTED"
            );

            operations.send(
                "orders.notifications",
                orderId,
                "NOTIFY_CUSTOMER"
            );

            return null;
        });
    }
}
~~~

Here, both sends participate in the same transaction managed by the template. If the callback throws an exception or the transaction fails to commit, the transaction follows `KafkaTemplate`'s abort/failure semantics.

Notes:

- `executeInTransaction()` requires a transactional `ProducerFactory`.
- Code inside the callback must have bounded execution time.
- `KafkaTemplate.send()` returns asynchronously; if you need per-send confirmation, handle futures/callbacks properly without swallowing errors.
- Transaction commit depends on the broker response. Do not log "published successfully" merely because `send()` was called before knowing the transaction outcome.
- If `executeInTransaction()` is called while another transaction is already open outside it, do not assume the callback automatically joins the outer transaction; Spring Kafka has specific semantics for template-initiated transactions. Determine your intended transaction boundary.

### 7.1 When to Use executeInTransaction?

Suitable when:

- One method needs to publish multiple Kafka records as a unit.
- You do not need a Spring-managed transaction across the entire service method.
- You want the transaction boundary directly visible in code.
- You do not need to coordinate consumer offsets from a listener container.

If you need to combine multiple methods into one transaction using declarative transactions, `KafkaTransactionManager` may be a better fit.

## 8. Using KafkaTransactionManager and @Transactional

`KafkaTransactionManager` integrates Kafka transactions into Spring's transaction model.

Example:

~~~java
@Service
public class PaymentEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public PaymentEventPublisher(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional(transactionManager = "kafkaTransactionManager")
    public void publishPaymentResult(
            String paymentId,
            String result) {

        kafkaTemplate.send(
            "payments.status",
            paymentId,
            result
        );

        kafkaTemplate.send(
            "payments.audit",
            paymentId,
            "AUDIT:" + result
        );
    }
}
~~~

When the method is called through the Spring transaction proxy and the right transaction manager is selected:

1. `KafkaTransactionManager` starts the Kafka transaction.
2. `KafkaTemplate` uses the producer bound to that transaction context.
3. Sends inside the method share the transaction.
4. Method completes normally: the transaction manager commits.
5. Method throws an exception matching rollback policy: the transaction manager rolls back/aborts.

### 8.1 Do Not Pick the Wrong TransactionManager

If the application has `DataSourceTransactionManager`, `JpaTransactionManager`, and `KafkaTransactionManager`, `@Transactional` without specifying a manager may pick an unintended default manager.

Example:

~~~java
@Transactional
public void publish() {
    kafkaTemplate.send("orders", "k", "v");
}
~~~

This snippet **does not prove a Kafka transaction exists**. You must know which manager is selected, whether `KafkaTemplate` synchronizes properly, and whether the factory is transaction capable.

A clearer approach is specifying the name:

~~~java
@Transactional(transactionManager = "kafkaTransactionManager")
~~~

If the goal is a database transaction combined with publishing a Kafka message, consider an outbox or a transaction coordination approach with documented failure windows rather than assuming two transaction managers produce an atomic distributed commit.

### 8.2 Self-Invocation Bypasses the Transaction Proxy

A method annotated with `@Transactional` called from another method **in the same bean** may bypass the Spring proxy. In that case, the transaction annotation may not apply as expected.

~~~java
@Service
public class ExampleService {

    public void outer() {
        inner(); // Self-invocation; watch Spring proxy semantics.
    }

    @Transactional(transactionManager = "kafkaTransactionManager")
    public void inner() {
        // Send Kafka records...
    }
}
~~~

With Spring's default proxy-based transaction management, this call does not start a Kafka transaction from `@Transactional` on `inner()`. Design boundaries across beans/proxies properly or use `executeInTransaction()` where appropriate.

### 8.3 Do Not Swallow Exceptions If Rollback Is Desired

If a transactional method catches an exception, logs it, and returns normally, the transaction manager may treat the method as successful and commit the sent Kafka records.

~~~java
try {
    kafkaTemplate.send("orders", key, value);
} catch (Exception ex) {
    log.error("send failed", ex);
    // Does not automatically roll back if the method still returns normally.
}
~~~

If a failure must abort the transaction, let the exception propagate or mark the transaction rollback-only via the appropriate Spring transaction API. Also account for asynchronous send failures occurring after `send()` has returned.

## 9. Transaction-Capable ProducerFactory in Consume-Transform-Produce

A key use case is a service that:

1. Reads a record from an input topic.
2. Transforms the data.
3. Writes records to an output topic.
4. Commits the input offset.

If step 3 succeeds but step 4 fails, the input may be read again and produce duplicate output. If step 4 commits first and step 3 fails, the input may be skipped without output.

Kafka transactions allow placing **output records and input consumer offsets** in the same Kafka transaction, forming the basis of Kafka-scoped exactly-once processing.

~~~mermaid
flowchart LR
    I["Input topic"] --> C["Spring Kafka listener container"]
    C --> L["Business transform"]
    L --> T["Transactional KafkaTemplate"]
    T --> O["Output topic"]
    C --> K["Kafka transaction: output + consumed offsets"]
    K --> G["Commit or abort atomically in Kafka"]
~~~

To achieve the desired behavior, you need:

- A transaction-capable `ProducerFactory`.
- `KafkaTransactionManager` or container transaction configuration matching your Spring Kafka version.
- `KafkaTemplate` using the right transactional factory.
- A listener container that is genuinely transaction-enabled.
- Consumer group offsets sent into the transaction via the container mechanism.
- Downstream consumers needing only committed output configured with `isolation.level=read_committed`.
- Broker/client/transaction settings supporting the required semantics.

### 9.1 Listeners Need Not Commit Offsets Manually When the Container Manages the Transaction

Example listener logic:

~~~java
@KafkaListener(
    topics = "orders.in",
    groupId = "orders-transformer",
    containerFactory = "transactionalListenerFactory"
)
public void transform(OrderCreated event) {

    String output = transformService.convert(event);

    kafkaTemplate.send(
        "orders.out",
        event.orderId(),
        output
    );
}
~~~

The code above shows only the business logic. **The decisive condition** is that `transactionalListenerFactory` must be properly configured to open a Kafka transaction for the listener and let the container manage offsets within the transaction. Merely calling a transactional `KafkaTemplate` inside a listener does not guarantee EOS if the container factory lacks proper transaction management.

In some Spring Kafka/Spring Boot versions, the framework can auto-associate `KafkaTransactionManager` with the matching container factory. With custom factories, check the transaction configuration API on `ContainerProperties` and bean wiring for your exact version.

### 9.2 When the Listener Throws an Exception

If a listener running inside a Kafka transaction throws an exception:

- The container rolls back/aborts the Kafka transaction according to policy.
- Output records sent in the transaction are not visible to downstream `read_committed` consumers.
- The input offset included in that transaction is not committed.
- The input may be redelivered for retry after rollback.
- Recovery policies for transactional listeners usually involve `AfterRollbackProcessor` mechanisms; do not blindly assume the same `DefaultErrorHandler` behavior as non-transactional listeners.

Side effects outside Kafka still do not roll back automatically with the Kafka transaction.

### 9.3 Exactly-Once Has a Clear Scope

Kafka EOS protects the **consume Kafka → produce Kafka → commit consumer offset within a Kafka transaction** pipeline when configured properly.

It does not automatically guarantee:

- Database inserts happen only once.
- HTTP APIs are called only once.
- Emails are sent only once.
- Another consumer using `read_uncommitted` never sees aborted records.
- Business events are never duplicated by upstream producers.

To protect side effects outside Kafka, use idempotency keys, inbox/outbox patterns, unique constraints, or compensating workflows depending on the use case.

## 10. Kafka Producer Transaction ID and Fencing

Kafka uses **transactional.id** to identify a logical producer, track its epoch, and block an older producer when a newer producer claims the same identity. This mechanism is called **producer fencing**.

An example:

~~~text
Instance A opens transaction with transactional.id = orders-prod-slot-1-0
A hangs or loses connectivity

Instance B starts with the same transactional.id
B initializes transaction and gets a new epoch

A tries to continue sending/committing
=> A is fenced; cannot continue the old transaction
~~~

Fencing stops zombie producers from continuing to write as if they still owned a valid identity.

### 10.1 Errors from Duplicate Prefixes

If two active pods use the same `transactionIdPrefix`, their factories may generate the same `transactional.id` suffix. Kafka will fence the contending producers, causing send/commit failures.

Symptoms:

- `ProducerFencedException` or related transaction errors.
- Transaction commits failing.
- Continuous retries/restarts after a rolling deployment.
- Starting one instance causes another instance to start failing.
- `read_committed` consumers waiting for a transaction to finish or time out.

The priority fix is correcting the instance identity assignment strategy and rollout lifecycle, not catching `ProducerFencedException` and retrying forever on a producer that lost ownership.

### 10.2 How to Design the Prefix

There are three requirements:

1. **Uniqueness across concurrently active instances.**
2. **Stability at the logical-instance level when fencing an old producer after restart is desired.**
3. **Not forcing every event to create a new transactional ID.**

In Kubernetes, you can choose an identity from a StatefulSet slot or a deployment-managed instance identity. With Deployments whose pods lack persistent identities, ensure a unique prefix per running pod and understand that changing identities across restarts can leave old transactional IDs waiting for expiration/cleanup rather than immediate reuse.

Do not use `group.id` as the `transactional.id` prefix across all replicas; a consumer `group.id` is intentionally shared across replicas, whereas transactional prefixes require uniqueness.

### 10.3 Producer Fencing Is a Lifecycle Error

When a producer is fenced, it cannot continue transactions as before. You should:

- Log the transactional identity, producer instance, and exception.
- Stop using the old producer per framework policy.
- Check for pods with duplicate prefixes or rolled-back old pods that have not exited.
- Let the factory/container initialize a valid producer according to lifecycle.
- Never retry indefinitely with the same fenced producer.
- Inspect input offset state, output visibility, and replayability.

## 11. Producer Cache, Concurrency, and transactional.id Suffixes

`DefaultKafkaProducerFactory` manages a producer cache to reuse transactional producers. A transaction does not need to spin up a brand-new `KafkaProducer` from scratch and close it immediately after commit.

When `KafkaTemplate` or the transaction manager finishes a transaction, the factory can return the producer to the cache instead of immediately closing the physical connection. This reduces transaction initialization overhead and network churn.

### 11.1 Why Does Caching Matter?

Initializing a transactional producer can require interacting with the transaction coordinator, including `initTransactions()`. If every transaction had to initialize a fresh producer, latency and broker load would increase.

Proper producer reuse helps:

- Reduce create/close overhead.
- Stabilize connections and metadata.
- Lower `initTransactions` cost.
- Support higher throughput for many short transactions.

However, the cache must be managed alongside concurrency, transaction lifetimes, and broker expiration.

### 11.2 Producer Count Can Exceed One

If an application has four listener threads concurrently processing Kafka transactions, multiple transactional producers may be needed at the same time. The factory uses `transactional.id` prefixes/suffixes so those producers do not contend with one another.

Some sample log lines:

~~~text
orders-service-instance-a-0
orders-service-instance-a-1
orders-service-instance-a-2
orders-service-instance-a-3
~~~

These are merely illustrative ID formats, not a guaranteed suffix format across every framework version.

Note that the number of transactional producers created/cached depends on configuration and actual transaction usage, not always matching `concurrency` 1-to-1. Different Spring Kafka versions have different suffix allocation and caching strategies.

### 11.3 ProducerPerThread Is Not Group Assignment

Some `ProducerFactory` configurations select producers per thread. Do not confuse thread-bound producers with consumer group partition assignment:

- Kafka consumer threads can scale with listener concurrency.
- Kafka transactional producers have their own identities.
- A transaction manager manages producers via the transaction context.
- A `KafkaTemplate` can be called from multiple threads, but transaction participation does not automatically propagate across threads.

If an application uses an asynchronous executor or thread handoff, verify whether the transaction context is preserved on the thread performing the send. Never assume `@Transactional` on thread A automatically applies to sends executed on thread B.

## 12. Producer Expiration and maxAge

Kafka brokers have settings such as **transactional.id.expiration.ms** to expire inactive transactional IDs. If a transactional producer sits idle in the cache for too long, its ID may expire on the broker.

A scenario that can occur:

1. The factory creates a transactional producer and completes a transaction.
2. The producer is placed in the cache.
3. No traffic arrives for a long period.
4. The broker expires the transactional ID due to inactivity.
5. When the factory reuses the old producer, epoch/producer fencing errors may occur.

In supporting Spring Kafka versions, `DefaultKafkaProducerFactory` provides **maxAge** to evict producers from the cache before the broker expires the transactional ID.

Guidelines:

- Choose `maxAge` smaller than the broker's `transactional.id.expiration.ms` with a safety margin.
- Monitor cached producer counts and producer age.
- Do not set `maxAge` so small that `initTransactions` runs unnecessarily often.
- Verify behavior against your Spring Kafka version and traffic pattern.

If a service runs in bursts with long idle gaps followed by sudden traffic spikes, producer cache expiration deserves extra attention.

## 13. Transaction Timeout and Limits

A transactional producer must finish its transaction within the time allowed by the broker.

Common settings:

| Configuration | Role |
|---|---|
| `transaction.timeout.ms` | Maximum time the producer requests for a transaction |
| `transaction.max.timeout.ms` | Broker-side transaction timeout ceiling |
| `delivery.timeout.ms` | Producer message delivery time limit, not synonymous with transaction timeout |
| `request.timeout.ms` | Network request timeout, not the whole transaction |
| `acks` | Producer acknowledgment level; durability also depends on replication/ISR |
| `enable.idempotence` | Enables duplicate prevention for producer retries |
| `retries` | Retries producer requests within delivery timeout limits |
| `transactional.id` | Identity of a transactional producer |
| `transactionIdPrefix` (Spring) | Prefix used by the factory to allocate transactional IDs |

Do not treat `transaction.timeout.ms` as consumer backoff. It is the transaction timeout managed by the Kafka coordinator.

### 13.1 Transaction Open Too Long

If a listener opens a Kafka transaction and waits 2 minutes on an HTTP API while `transaction.timeout.ms` is only 60 seconds, the coordinator can abort the transaction. When the method attempts to commit, the application receives an exception.

Increasing the timeout is not the default solution. You may need to:

- Move non-Kafka work outside the Kafka transaction.
- Reduce processing time per input record/batch.
- Enforce clear downstream timeouts.
- Reduce load and add capacity if needed.
- Choose a transaction timeout fitting p99 processing time within broker limits.

Prolonged transactions also force downstream `read_committed` consumers to wait at the LSO on partitions holding records from the open transaction.

### 13.2 Producer Send ACKed While Transaction Not Yet Committed

A producer can receive an ACK for a sent record even though the transaction later aborts. There is no contradiction:

- A send ACK means the broker accepted/wrote the record per producer ACK policy.
- Transaction commit decides whether that group of records is considered committed.
- `read_committed` consumers only see committed transactional records.

Therefore, do not emit business notifications claiming "event published" just because a send callback succeeded while the transaction is still open.

## 14. Transaction Commit, Abort, and Uncertain Outcomes

Not all producer errors are alike. If a send fails, the framework may need to abort the transaction. If a commit fails due to a network interruption, the application sometimes cannot tell for sure from the client-side exception alone whether the broker completed the commit.

Do not assume:

~~~text
commitTransaction() throws timeout
=> transaction is definitely aborted
~~~

Outcomes may need verification according to Kafka client/transaction coordinator semantics and business records. When retrying an entire business operation, account for the possibility that the output committed on the previous attempt while the response was lost.

Principles:

- Do not retry infinitely on fatal/fenced producers.
- Let the transaction manager and `KafkaProducer` handle abort per the API contract.
- Design event IDs and downstream side effects to tolerate duplicates at uncertain boundaries.
- Monitor commit/abort rates and transaction coordinator errors.
- Use a `read_committed` consumer to observe effective output rather than inferring from send ACKs alone.

## 15. Kafka and Database Transactions: Atomicity Limits

Business workflows often need to both write to a database and emit events. `KafkaTransactionManager` does not automatically create an atomic distributed transaction with a database.

Example:

~~~text
Begin DB transaction
    update orders table
Commit DB transaction

Begin Kafka transaction
    send OrderUpdated
Commit Kafka transaction
~~~

If the DB commit succeeds but the Kafka commit fails, the database changed while the event may remain unpublished. Reversing the order produces the inverse failure window.

Spring supports certain transaction synchronization mechanisms between Kafka and databases, but without a shared distributed atomic commit, you must still understand commit ordering and mid-flight failure handling. Injecting a transaction manager into a method does not mean two systems achieve cross-boundary exactly-once.

### 15.1 Transactional Outbox

A common solution:

1. Within a single DB transaction, write the business table and an outbox row.
2. Commit the DB transaction.
3. A publisher or CDC process reads the outbox.
4. The publisher sends the event to Kafka with retries.
5. Mark/track publishing progress according to design and idempotency.

Outbox does not automatically eliminate all duplicate Kafka events. Consumers still need idempotent processing. However, it eliminates the failure window where "the DB committed without durably recording the intent to publish the event".

### 15.2 Choosing Transaction Scope

If the entire requirement is writing two Kafka topics atomically together, a transaction-capable `ProducerFactory` may be the right mechanism.

If you need to coordinate a SQL database, Kafka, HTTP APIs, and email as a long business workflow, design proper orchestration, outbox/inbox, or sagas rather than holding a Kafka transaction open across the whole workflow.

## 16. Monitoring Transaction-Capable ProducerFactory in Production

A system with transactional producers needs monitoring for both **configuration** and **transaction outcomes**.

| Group | Signals to monitor |
|---|---|
| Factory | `transactionCapable`, `transactionIdPrefix`, count of factories/templates |
| Producer | Producer creation, cache reuse, producer close, age |
| Transaction | Begin/commit/abort rate, commit latency, timeouts |
| Failure | Fenced producers, coordinator errors, authentication/ACL errors |
| Send | Record send success/failure, request latency, retry rate |
| Broker | Transaction coordinator health, ISR, replica lag |
| Consumer | `read_committed` lag, LSO/HW, records received |
| Business | Event IDs, duplicate detection, downstream consistency |

### 16.1 Useful Startup Logs

You can log sanitized values such as:

~~~text
service=orders-transformer
environment=prod
producerFactory=orderProducerFactory
transactionCapable=true
transactionIdPrefix=orders-prod-instance-17-
transactionManager=kafkaTransactionManager
~~~

Avoid logging credentials or sensitive Kafka configuration. Do not dump raw security settings.

In systems with multiple factories, log each factory separately along with the templates/containers using it. Having **one** capable factory in the application does not prove the intended listener uses that factory.

### 16.2 Errors That Warrant Alerts

- Sudden spikes in `ProducerFencedException` or epoch errors.
- Higher-than-normal Kafka transaction abort rates.
- Rising transaction commit latency.
- Transaction timeouts occurring.
- Continuous producer cache misses or excessive producer creation.
- Rising `read_committed` consumer lag while HW advances and LSO stalls.
- Producer sends succeeding while downstream observes no committed output.
- Duplicate side effects after restarts/retries.

Do not monitor send success rates alone; records can be sent while the transaction later aborts.

## 17. Misconfiguration Scenarios

| Scenario | Symptoms | Remediation |
|---|---|---|
| Factory lacks `transactionIdPrefix` | `transactionCapable=false`; transactional sends fail | Configure prefix and verify factory |
| Two pods share the same prefix | Repeated fencing at startup/commit | Assign unique prefixes per concurrent instance |
| `KafkaTemplate` uses wrong factory | Does not join intended transaction | Check dependency injection and bean qualifiers |
| `@Transactional` picks DB manager | Kafka transaction does not behave as expected | Specify the right `transactionManager` |
| Self-invocation calls `@Transactional` | No transaction through proxy | Redesign boundary or use `executeInTransaction` |
| Kafka send outside transaction on transactional template | May throw error if non-transactional sends disallowed | Call inside a transaction or explicitly configure non-tx sends |
| Listener container not transaction-enabled | Outputs/offsets not atomic | Configure container transaction and verify |
| Prefix shared via group ID | Pods in the same group may collide on transactional IDs | Separate logical consumer group ID from per-instance transactional prefix |
| Producer cache idle too long | Fencing/epoch error on reuse | Consider `maxAge` below broker expiration |
| Transaction waits too long on downstream | Timeouts, aborts, `read_committed` stalls | Shorten transaction lifetime |
| DLT/retry side effects outside Kafka | Duplicates after replay | Idempotency and recovery policy |
| `read_uncommitted` downstream | May see aborted records | Set `isolation.level=read_committed` where committed semantics are needed |

## 18. Investigation Procedure When Transactions Do Not Work

When an application reports "transactions are enabled yet partial events were still sent" or `KafkaTemplate` throws errors:

1. Identify the actual **ProducerFactory instance** used by `KafkaTemplate`.
2. Check **transactionCapable()** at runtime.
3. Check **transactionIdPrefix** and generated `transactional.id` values to ensure no collision across pods.
4. Identify the transaction boundary: `executeInTransaction`, `@Transactional` with `KafkaTransactionManager`, or container transaction.
5. If using `@Transactional`, verify the method is invoked via the Spring proxy and uses the right manager.
6. If using `@KafkaListener`, verify the container factory, transaction manager, and offset-in-transaction configuration.
7. Inspect `KafkaProducer` exceptions, especially fencing, timeout, coordinator, or serialization issues.
8. Compare producer send ACKs against transaction commit outcomes; never equate the two.
9. Check downstream `isolation.level` and LSO if records "have not appeared yet".
10. Check broker `transaction.max.timeout.ms`, topic replication/ISR, and ACLs.
11. If database/HTTP side effects exist, determine which committed and which may be duplicated.
12. After fixing, test commit/abort, restarts, and fault injection in staging before expanding rollout.

Do not reset consumer group offsets merely because output has not appeared yet. The cause may be an uncommitted transaction, an abort, or a downstream `read_committed` consumer waiting on LSO.

## 19. Integration Tests for Transaction-Capable ProducerFactory

Unit tests mocking `KafkaTemplate` cannot prove that a Kafka broker supports transactional commits, aborts, and consumer isolation. Use an integrated Kafka broker, such as Testcontainers or a staging environment.

### 19.1 Verifying Capability

- Boot the application context with the transactional prefix configured.
- Retrieve the real `ProducerFactory` from the context.
- Assert `transactionCapable()` returns `true`.
- Verify `KafkaTemplate` and `KafkaTransactionManager` use the right factory.
- Verify the prefix injected by the deployment.

### 19.2 Successful Commit

- Start a transaction via `executeInTransaction` or `KafkaTransactionManager`.
- Send two records to test topics/partitions.
- Commit the transaction.
- Read with a `read_committed` consumer.
- Verify both records appear.
- Record transaction latency and output offsets.

### 19.3 Abort

- Start a transaction.
- Send two records.
- Throw an exception before commit.
- Verify the transaction aborts/rolls back.
- Verify with a `read_committed` consumer that neither record appears.
- If testing with a `read_uncommitted` consumer, understand it may observe records from the aborted transaction.

### 19.4 Fencing

- Initialize a transactional producer with a specific `transactional.id` in the test environment.
- Initialize a second producer using the same identity.
- Verify the older producer is fenced per Kafka semantics.
- Verify the service does not retry the old producer infinitely.
- Ensure tests never use production transactional IDs.

### 19.5 Consume-Transform-Produce

- Create an input topic and an output topic.
- Configure the listener container with Kafka transactions.
- Send an input record.
- Let the listener write output and the container commit the input offset in the same transaction.
- Verify downstream `read_committed` reads the output after commit.
- Repeat with the listener throwing an exception; verify output is rolled back and input is not committed under the transactional flow.
- Verify recovery/retry can complete afterward without creating duplicate side effects outside Kafka.

### 19.6 Crashes and Producer Reuse

- Open a transaction and stop the instance before commit in the test environment.
- Start a valid instance with the proper prefix.
- Verify producer fencing/abort cleanup per lifecycle.
- Leave the factory idle for a shortened test expiration window if possible.
- Verify producer reuse/expiration policies do not trigger abnormal errors.
- Verify committed records are consumed normally after recovery.

## 20. Pre-Deployment Checklist

**Factory configuration**

- [ ] Expected `ProducerFactory` returns `transactionCapable()=true`.
- [ ] `DefaultKafkaProducerFactory` is configured with `transactionIdPrefix`.
- [ ] Prefix is unique across running application instances.
- [ ] `KafkaTemplate` and `KafkaTransactionManager` use the right factory.
- [ ] Serializers, `acks`, security, and transaction timeouts are appropriate.
- [ ] Producer cache and `maxAge` are reviewed against traffic/expiration.

**Transaction boundary**

- [ ] Sends requiring atomicity execute within the same actual transaction.
- [ ] Commit/abort paths are clear; rollback exceptions are not swallowed.
- [ ] `@Transactional` uses the right manager and proxy boundary.
- [ ] Sends do not accidentally execute outside transactions.
- [ ] Transactions are not held open excessively by external I/O.

**Consume-transform-produce**

- [ ] Listener container genuinely uses Kafka transaction management.
- [ ] Output records and input offsets share the transaction when EOS is required.
- [ ] Downstream uses `read_committed` when committed-transaction visibility is needed.
- [ ] Retry/rollback/`AfterRollbackProcessor` behavior is understood for the version.
- [ ] Side effects outside Kafka have idempotency or outbox/inbox protection.

**Operations**

- [ ] Metrics exist for transaction begin/commit/abort and fencing.
- [ ] Producer cache, age, transaction timeouts, and coordinator health are monitored.
- [ ] Runbooks exist for duplicate prefixes, zombie producers, and commit failures.
- [ ] Commit, abort, restarts, and `read_committed` consumers have been tested in staging.
- [ ] Cross-database/HTTP atomicity is not claimed without a dedicated mechanism.

A **transaction-capable `ProducerFactory`** is the foundational requirement for Spring Kafka to create producers that can join Kafka transactions. With `DefaultKafkaProducerFactory`, configuring a transaction ID prefix enables the factory to manage transactional producers so `KafkaTemplate`/`KafkaTransactionManager` can coordinate begin, commit, or abort. However, capability is only the first step: transactional IDs must be assigned properly per instance, transaction boundaries must actually be active, listener offsets must be coordinated when EOS is required, and downstream must read with `read_committed` to filter out aborted records. Production reliability comes from consistency across factory, template, transaction manager, broker, and recovery procedures — not merely from enabling a single property.

