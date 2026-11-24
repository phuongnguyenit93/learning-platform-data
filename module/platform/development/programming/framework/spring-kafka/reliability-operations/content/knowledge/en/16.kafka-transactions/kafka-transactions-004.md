# KafkaTemplate in Transactions

## 1. Why Does KafkaTemplate Need Transaction Support?

In event-driven systems, a single business operation may emit multiple related Kafka records. If a producer sends each record independently, a failure on a subsequent send can leave downstream seeing part of the change without the rest.

For example, Order Service confirms an order and needs to send two records:

- **OrderConfirmed** to topic `orders.events`.
- **ReserveInventory** to topic `inventory.commands`.

If `KafkaTemplate` uses a **Kafka transaction**, Kafka writes participating in the transaction conclude with a single **commit** or **abort** decision. Consumers configured with **isolation.level=read_committed** read only committed transactional records and do not deliver records from aborted transactions.

~~~text
Order Service
     |
     v
Transactional KafkaTemplate
     |
     +---- send OrderConfirmed -----> orders.events
     |
     +---- send ReserveInventory ---> inventory.commands
     |
     v
 Kafka transaction
     |
     +---- COMMIT -> read_committed consumer reads committed output
     |
     +---- ABORT  -> read_committed consumer skips aborted output
~~~

A Kafka transaction protects **Kafka operations inside the transaction**, and in a consume-transform-produce flow can include committing the consumer group offset. It does **not** automatically create an atomic commit between Kafka and PostgreSQL, MySQL, HTTP APIs, or payment systems.

In Spring Kafka, **KafkaTemplate** is the API for sending records, while **KafkaTransactionManager**, **ProducerFactory**, and the **listener container** determine how transactions are started, synchronized, committed, and aborted.

## 2. Related Components

| Component | Role |
|---|---|
| `KafkaTemplate` | Record-sending API returning `CompletableFuture` and providing `executeInTransaction` |
| `KafkaProducer` | Producer client used inside transactions at the Kafka layer |
| `DefaultKafkaProducerFactory` | Creates/caches transactional producers and assigns `transactional.id` |
| `KafkaTransactionManager` | Integrates Kafka transactions with Spring's `TransactionManager` |
| `@Transactional` | Declares transaction boundaries when Spring AOP selects the right manager |
| `ConcurrentKafkaListenerContainerFactory` | Creates listener containers, configurable with transactions for consumer-driven flows |
| `KafkaConsumer` | Polls records and manages consumer group offsets |
| Transaction coordinator | Broker component managing commit/abort state of Kafka transactions |

A `KafkaTemplate` backed by a transaction-capable `ProducerFactory` can be used in three patterns:

1. **Producer-initiated:** a service explicitly opens a transaction via `@Transactional`, sends multiple records, and commits.
2. **Local KafkaTemplate transaction:** the **executeInTransaction** method starts a local transaction wrapping a callback.
3. **Consumer-initiated:** a listener container starts a transaction, `KafkaTemplate` sends outputs, and the container sends input offsets into the same transaction.

It is especially important to distinguish template-level transactions from listener-container-managed transactions. They do not automatically merge simply because they use the same `KafkaTemplate` bean.

## 3. How Do Transactions Work on the Kafka Broker?

A transactional producer has a **transactional.id** identifier. Kafka assigns a producer ID and epoch to track the producer session and prevent an old producer from continuing once a new producer with the same transactional ID appears.

A typical transaction flow:

~~~text
initTransactions()
       |
       v
beginTransaction()
       |
       +--> send record A to topic 1
       |
       +--> send record B to topic 2
       |
       v
commitTransaction() or abortTransaction()
       |
       v
Transaction coordinator decides state
       |
       v
Broker writes appropriate transaction markers
       |
       v
read_committed consumer reads only committed data
~~~

Transactional records may already exist in the physical log before commit. Therefore, **a broker ack for a send is not equivalent to committing the entire transaction**.

A Kafka transaction can span multiple topics and partitions. However, two different downstream consumers still poll and process on their own schedules. A Kafka commit does not create a distributed transaction across all downstream applications.

### 3.1. Idempotence vs Transactions

**enable.idempotence=true** helps a producer avoid duplicates caused by its own retries within supported limits. It does not create commit/abort boundaries across multiple output records.

**Kafka transactions** use an idempotent producer and extend guarantees across a group of Kafka writes, while also able to coordinate input offsets with outputs in consume-transform-produce.

| Mechanism | Purpose |
|---|---|
| Idempotent producer | Limits producer retries from creating duplicate records |
| Transactional producer | Atomically commits/aborts a group of Kafka operations |
| `read_committed` consumer | Does not deliver transactional records from aborted transactions |
| Idempotent business consumer | Prevents duplicate DB/HTTP side effects when records are redelivered |
| Transactional outbox | Durably coordinates DB writes and the intent to publish to Kafka |

## 4. Preparing Broker, ProducerFactory, and Permissions

Before using transactions, ensure:

- Kafka brokers and the transaction coordinator are healthy.
- The transaction state log has replication/min ISR suitable for the environment.
- `ProducerFactory` is configured with a **transaction ID prefix**.
- Producers have proper key/value serializers, **acks=all**, and appropriate reliability settings.
- The principal has WRITE permission on target topics, corresponding permissions on the transactional ID, and additional cluster permissions where required by version/authorizer.
- Downstream consumers use **read_committed** if aborted outputs must stay hidden.
- Transaction boundaries in code are deliberately chosen.

A single-broker development environment may need transaction state log replication tuned to the actual broker count. Never lower internal transaction topic durability in production as a shortcut to fix initialization errors.

## 5. Configuring a Transactional KafkaTemplate in Spring Boot

Example `application.yml`:

~~~yaml
spring:
  application:
    name: order-service
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      transaction-id-prefix: "order-service-pod-a-tx-"
      acks: all
      properties:
        "[enable.idempotence]": true
        "[delivery.timeout.ms]": 120000
~~~

**transaction-id-prefix** causes `ProducerFactory` to create transactional producers. In Spring Boot, under suitable auto-configuration conditions, a **KafkaTransactionManager** is also configured.

In the example above, the pod name is hard-coded for illustration. Multi-replica production applications must derive a **unique instance identity per pod/process** from configuration or environment variables rather than sharing the literal string `order-service-pod-a-tx-`.

Do not assign the same transactional ID to concurrently running producers. Kafka will fence the old producer when a new producer initializes with the same transactional ID.

### 5.1. Transactional Producers May Require an Active Transaction

If `KafkaTemplate` uses a transaction-capable `ProducerFactory` and non-transactional sends are disallowed, calling `send` outside a transaction can throw an error like "No transaction is in process".

This differs from a regular `KafkaTemplate`. Proper usage is:

- Open a Kafka transaction via **@Transactional** with `KafkaTransactionManager`.
- Use **KafkaTemplate.executeInTransaction** for a local transaction.
- Send from a listener that already has a container-initiated Kafka transaction.
- Only when business logic permits non-transactional sends should you consider `KafkaTemplate`'s **setAllowNonTransactional(true)** API.

Do not enable `allowNonTransactional` merely to mask a configuration error, as some outputs could then be sent outside transactions while others are sent transactionally.

## 6. Approach 1: @Transactional with KafkaTransactionManager

When a business method needs to send multiple records in one transaction, you can use Spring's transaction abstraction:

~~~java
@Service
public class OrderPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("kafkaTransactionManager")
    public void publish(
            String orderId,
            OrderConfirmed confirmed,
            InventoryReservationRequested reserve) {

        var first = kafkaTemplate.send(
            "orders.events",
            orderId,
            confirmed
        );

        var second = kafkaTemplate.send(
            "inventory.commands",
            orderId,
            reserve
        );

        CompletableFuture.allOf(first, second).join();
    }
}
~~~

With the right `KafkaTransactionManager`, the general flow is:

1. Spring's transaction interceptor opens a Kafka transaction before entering the method.
2. `KafkaTemplate` uses the transactional producer bound to the current transaction.
3. The `send` calls emit records into the transaction.
4. When the method finishes normally, the manager requests a commit.
5. When the method throws an exception triggering Spring rollback rules, the manager aborts.

**CompletableFuture.allOf(...).join()** surfaces asynchronous send failures inside the transaction boundary rather than merely logging them after the method ends.

This example assumes a Spring Kafka version where `KafkaTemplate.send` returns `CompletableFuture`. Older versions may have different future types and callback APIs; use the API of your actual dependency.

### 6.1. Selecting the Right Transaction Manager

When an application has both a database transaction manager and `KafkaTransactionManager`, **@Transactional** without a qualifier may choose a non-Kafka manager.

Example:

~~~java
@Transactional("kafkaTransactionManager")
public void publishKafkaEvents() {
    // Kafka transaction
}
~~~

If the manager bean has another name, the annotation must reference the actual bean name. Never assume `@Transactional` uses Kafka merely because the code inside calls `KafkaTemplate`.

### 6.2. Spring Proxies and Self-Invocation

Spring `@Transactional` typically relies on AOP proxies. If a method in the same class calls **this.publishKafkaEvents()** directly, the call may bypass the proxy and not open a transaction.

The template may then behave as if outside a transaction and throw an error. Place the boundary on a method called through a Spring bean proxy or use programmatic transactions when needed.

## 7. Approach 2: KafkaTemplate.executeInTransaction

`KafkaTemplate` provides **executeInTransaction** to wrap a callback in a local Kafka transaction.

~~~java
public void publishPair(
        String orderId,
        OrderConfirmed confirmed,
        InventoryReservationRequested reserve) {

    kafkaTemplate.executeInTransaction(operations -> {
        operations.send(
            "orders.events",
            orderId,
            confirmed
        ).join();

        operations.send(
            "inventory.commands",
            orderId,
            reserve
        ).join();

        return null;
    });
}
~~~

Visualization:

~~~text
executeInTransaction(callback)
           |
           v
     begin transaction
           |
           v
     execute callback
           |
      +----+----+
      |         |
   success   exception
      |         |
      v         v
    commit     abort
      |         |
      v         v
    return   propagate error
~~~

This approach fits a small Kafka-publishing method wanting an explicit transaction boundary without relying on AOP annotations on an outer service.

### 7.1. Note on Existing Transactions

**executeInTransaction creates its own local Kafka transaction and does not join an outer open transaction.**

For example, if a listener container has already opened a Kafka transaction to coordinate outputs and consumer offsets, yet code inside the listener calls `executeInTransaction`, the callback's output may commit in a separate transaction rather than the input offset's transaction. That breaks the atomic consume-transform-produce assumption.

Therefore, inside a transactional listener, normally **call `kafkaTemplate.send` directly** so the template uses the producer bound to the active container transaction.

### 7.2. Comparing the Two Approaches

| Requirement | `@Transactional` with `KafkaTransactionManager` | `executeInTransaction` |
|---|---|---|
| Transaction boundary on a service method | Suitable | Usable without annotations |
| Requires AOP/proxy | Yes in the standard model | No |
| Callback creates a local transaction | No | Yes |
| Coordinates multiple methods in a Spring transaction | Yes if sharing the same manager | Callback is its own boundary |
| Existing listener Kafka transaction | Works per container design | Do not use to replace container transaction |
| Guarantees atomic DB+Kafka | No | No |

## 8. Send Future Is Not Transaction Commit

`KafkaTemplate.send` typically returns **CompletableFuture<SendResult<K,V>>**. The future reports the result of a single send, not the commit outcome of the entire transaction.

~~~java
var future = kafkaTemplate.send(
    "orders.events",
    orderId,
    event
);

future.whenComplete((result, failure) -> {
    if (failure != null) {
        log.error("Kafka send failed orderId={}", orderId, failure);
    }
    else {
        log.info(
            "Broker acknowledged topic={} partition={} offset={}",
            result.getRecordMetadata().topic(),
            result.getRecordMetadata().partition(),
            result.getRecordMetadata().offset()
        );
    }
});
~~~

If the callback reports a successful send, the record may have been acknowledged by the broker while the transaction has not yet committed. If the transaction aborts afterward, `read_committed` consumers will not receive that record.

Conversely, if the callback reports an error and the code only logs it while letting the method return normally, the application fails to feed the error into rollback rules. Producer commit may subsequently fail, but you should not rely on the system to infer business policy automatically.

### 8.1. Awaiting Futures Inside the Transaction When Needed

~~~java
var a = kafkaTemplate.send("orders.events", orderId, confirmed);
var b = kafkaTemplate.send("inventory.commands", orderId, reserve);

CompletableFuture.allOf(a, b).join();
~~~

With this approach, a send failure causes **join()** to throw `CompletionException` directly inside the transactional method. Configure delivery timeout, request timeout, and bounded blocking times appropriately to avoid holding the transaction open too long.

Do not use an asynchronous callback running after the `@Transactional` method finishes as the place to decide whether to roll back an already committed or aborted transaction.

## 9. Commit, Abort, and Failure Scenarios

| Scenario | Meaning |
|---|---|
| All sends acked, transaction committed | Kafka records in the transaction are committed |
| One send fails, transaction aborts | Transaction outputs are not delivered to `read_committed` consumers |
| JVM dies before commit | Uncommitted transaction is handled by broker timeout/recovery |
| Transaction coordinator unavailable | Commit may fail or outcome may be uncertain |
| Producer fenced | Old producer cannot continue valid transactions |
| Transaction timeout | Coordinator can abort an overdue transaction |
| `read_uncommitted` consumer | Can read aborted transactional records |

Distinguish between:

1. **send invoked**: the application called `KafkaTemplate.send`.
2. **send acknowledged**: the broker returned a record write acknowledgment.
3. **transaction committed**: the coordinator confirmed commit for the transaction.

A "send succeeded" log cannot substitute for proof of transaction commit. When commit outcome is uncertain due to timeout or crash, rely on idempotency and reconciliation rather than assuming all sends succeeded.

## 10. Transactional ID and Producer Fencing

**transactional.id** identifies a logical producer. The broker uses producer ID/epoch to fence an old producer if a new producer initializes with the same transactional ID.

~~~text
Producer A: transactional.id = orders-tx-0
          |
          v
Producer B initializes with the same transactional.id
          |
          v
Broker increments epoch, producer A is fenced
          |
          v
Producer A cannot continue a valid transaction
~~~

Fencing protects correctness but can become an operational incident if replicas lack distinct transactional IDs.

### 10.1. How Should Prefixes Be Chosen?

- Include application and environment namespaces.
- Distinguish concurrently running instances/processes.
- Do not generate random IDs per event.
- Do not use event IDs or request IDs as transactional IDs.
- Keep compatible with ACL prefixes and avoid overly broad permissions.
- Monitor for ID collisions when scaling pods or restarting.

Per-instance example:

~~~text
order-service-prod-pod-a-tx-0
order-service-prod-pod-a-tx-1
order-service-prod-pod-b-tx-0
order-service-prod-pod-b-tx-1
~~~

If a producer receives **ProducerFencedException**, do not simply retry with the same fenced producer. Let the framework handle initializing a new producer lifecycle and investigate the ID collision or restart/rollout state.

## 11. Sending to Multiple Topics/Partitions in One Transaction

A Kafka transaction can span multiple topics/partitions:

~~~java
@Transactional("kafkaTransactionManager")
public void publishWorkflow(
        String orderId,
        OrderConfirmed confirmed,
        InventoryReserved reserved,
        OrderAudit audit) {

    var first = kafkaTemplate.send(
        "orders.events", orderId, confirmed
    );

    var second = kafkaTemplate.send(
        "inventory.events", orderId, reserved
    );

    var third = kafkaTemplate.send(
        "orders.audit", orderId, audit
    );

    CompletableFuture.allOf(first, second, third).join();
}
~~~

This snippet assumes the `KafkaTemplate` value type and serializer support all three event classes. With Avro/Protobuf/JSON Schema, ensure serializers, schema subjects, and type mappings match.

**An atomic Kafka commit does not mean all downstream consumers process simultaneously.** One consumer reading `orders.events` and another reading `inventory.events` may finish at different times. If business coordination is required, use correlation IDs and an appropriate state machine or orchestration.

## 12. Consume-Transform-Produce with KafkaTemplate

An important use case is reading an input record, transforming it, publishing Kafka output, and committing input offsets in the same transaction.

~~~text
orders.in
    |
    v
Transactional listener container
    |
    +-- begin Kafka transaction
    |
    v
@KafkaListener
    |
    +-- transform input
    +-- kafkaTemplate.send("orders.validated", output)
    |
    v
Container sends consumed offsets to transaction
    |
 +--+---+
 |      |
commit  abort
 |      |
 v      v
output  output aborted
+offset input offset is not committed
committed
~~~

Listener example:

~~~java
@KafkaListener(
    topics = "orders.in",
    groupId = "orders-transformer",
    containerFactory = "transactionalListenerContainerFactory"
)
public void transform(OrderCreated input) {
    ValidatedOrder output = validator.validate(input);

    kafkaTemplate.send(
        "orders.validated",
        input.orderId(),
        output
    );
}
~~~

The example assumes **transactionalListenerContainerFactory** is configured with a Kafka-aware transaction manager or the equivalent API for your Spring Kafka version. `KafkaTemplate` must use a producer that joins the container-opened transaction.

**Merely annotating a listener with `@Transactional` does not replace configuring the container to send input offsets into the Kafka transaction.** The container is the component coordinating offset commits after the listener finishes.

### 12.1. Why Must Offsets and Outputs Share the Transaction?

If outputs commit successfully while the input offset has not committed, the consumer may re-read the input after a crash and emit duplicate outputs. When the container sends outputs and offsets in the same Kafka transaction, their commit or abort is coordinated under Kafka semantics.

This forms the basis for **Kafka-only** exactly-once consume-transform-produce when downstream reads with `read_committed`. It does not automatically guarantee exactly-once with systems outside Kafka.

### 12.2. Avoid executeInTransaction Inside a Transactional Listener

A common design mistake is calling **executeInTransaction** inside a listener callback for which the container has already opened a Kafka transaction. The transaction opened by that method is an independent transaction. Outputs may commit while the input offset in the container transaction has not committed.

In flows requiring atomic input-offset + Kafka-output, call **KafkaTemplate.send** normally to join the active transaction.

## 13. Consumer read_committed

Downstream consumers should configure:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        "[isolation.level]": read_committed
~~~

With **read_uncommitted**, a consumer can observe aborted transactional records and execute side effects on data that should have stayed hidden.

An operational note: `read_committed` consumers can be bounded by the **Last Stable Offset (LSO)** when open transactions exist. A producer holding a transaction open for a long time can block `read_committed` consumers from reading subsequent records even though the log end offset advances.

When unexpected lag appears, inspect open transactions and transaction duration, not just listener processing speed.

## 14. Kafka Transactions Do Not Include Databases

Example:

~~~java
@Transactional
public void createOrder(CreateOrder command) {
    orderRepository.save(new Order(...));
    kafkaTemplate.send("orders.created", ...);
}
~~~

If **@Transactional** here uses `JpaTransactionManager`, the code does not automatically get a Kafka transaction. If it uses `KafkaTransactionManager`, the DB is not automatically committed atomically with Kafka either.

These are two separate resources; a Kafka transaction is not a distributed XA transaction between a Kafka broker and a database.

### 14.1. Failure Window Between Two Commits

Even when Spring coordinates transaction synchronization for a database and Kafka, this scenario still exists:

~~~text
DB commit succeeds
        |
        v
Kafka transaction commit fails
        |
        v
DB has Order but Kafka has no committed event
~~~

Reversing the commit order creates a symmetric failure window. Spring transaction synchronization coordinates operation ordering, but cannot eliminate every failure scenario between two systems.

### 14.2. Transactional Outbox

If business requirements dictate that no event can be lost after a DB transaction commits, a common design is transactional outbox:

~~~text
Create order request
      |
      v
Single DB transaction
      |
      +-- INSERT order
      +-- INSERT outbox_event
      |
      v
    COMMIT
      |
      v
Outbox publisher
      |
      v
KafkaTemplate sends event
      |
      v
Kafka topic
~~~

The outbox publisher may re-send events after a crash, so consumers still require idempotency. In return, order state and publish intent are persisted atomically within the same DB transaction.

When multiple steps span different systems, consider adding inbox, saga, or compensation patterns. Do not expect `KafkaTemplate.executeInTransaction` to replace these patterns.

## 15. KafkaTemplate.executeInTransaction and DB Side Effects

Example where atomic DB+Kafka must not be assumed:

~~~java
kafkaTemplate.executeInTransaction(operations -> {
    orderRepository.save(order);
    operations.send("orders.created", orderId, event);
    return null;
});
~~~

The callback above creates a Kafka transaction only for Kafka operations. The DB save does not automatically join the same atomic transaction. If the DB commits and Kafka aborts, the application can still lose the event.

Solutions depend on consistency goals:

- Outbox when the DB is the primary source of truth.
- Inbox/idempotent consumer for replays.
- Saga or compensation across multiple services.
- Periodic reconciliation for workflows requiring eventual convergence.
- Kafka-only transactions if both data and offsets live in Kafka.

## 16. Transaction Errors and Handling

| Error group | Symptom | Handling |
|---|---|---|
| Send timeout | Future fails or delivery timeout | Check broker/network and retry at a safe boundary |
| Serialization error | Failed to produce bytes | Fix serializer/schema |
| Authorization error | Missing topic WRITE / TransactionalId permissions | Fix ACL/principal |
| `ProducerFencedException` | Old producer fenced | Recreate valid producer, check duplicate IDs |
| Transaction timeout | Transaction held open too long | Shorten transaction, tune timeouts per policy |
| Coordinator unavailable | Cannot begin/commit transaction | Check broker/transaction coordinator |
| Uncertain commit outcome | Timeout or process crash during commit | Idempotency and reconciliation |
| DLT recovery failure | DLT publish or recovery failed | Do not commit erroneously; check serializer/ACL |

Not every failure can be fixed by retrying a single `KafkaTemplate.send` inside the same transaction. Once a transaction has errored or aborted, you may need to **start a new transaction and retry the entire business unit**, rather than resending just one record.

~~~text
Transaction #1:
    send A -> ack
    send B -> error
    ABORT

Transaction #2:
    determine safe business state
    send A + send B
    COMMIT
~~~

When retrying a transaction at the application level, ensure callers or consumers do not produce duplicate business side effects.

## 17. Transaction Timeout, Caching, and Producer maxAge

Long-open transactions increase timeout risk, hold resources, and stall `read_committed` consumers at the LSO. Common causes:

- Listener processing a very large batch in one transaction.
- `@Transactional` method calling an HTTP API without timeouts.
- DB locks or slow downstream dependencies.
- Long retries/backoff occurring while a transaction remains open.
- Long GC pauses or thread blocking.

Keep transactions short, enforce explicit timeouts, and minimize unrelated work inside transaction boundaries.

### 17.1. Producer Cache and Transactional ID Suffixes

`DefaultKafkaProducerFactory` can cache transactional producers. Producers are created with distinct transactional IDs based on prefix and suffix:

~~~text
order-pod-a-tx-0
order-pod-a-tx-1
order-pod-a-tx-2
~~~

When concurrency is high, ensure `ProducerFactory` can supply enough producers and the broker transaction coordinator can handle the corresponding load.

### 17.2. Reusing Producers After Idle Periods

Kafka brokers expire inactive transactional IDs. A cached producer unused for too long may encounter errors when reused, depending on version and broker configuration.

Spring Kafka provides the **maxAge** option on `DefaultKafkaProducerFactory` in supported versions to refresh producers before the expiration threshold. Check the broker's **transactional.id.expiration.ms**, client version, and actual `maxAge` configuration API.

## 18. ACLs and Authentication for Transactional Producers

A transactional producer may require:

- WRITE on each output topic.
- Appropriate permissions on the **TransactionalId** used.
- Idempotent write / cluster-level permissions where required by configuration/version.
- If participating in consume-transform-produce, consumer READ on input topics and corresponding group permissions.

When transactional IDs have suffixes generated by `ProducerFactory`, overly narrow literal ACLs may not match. You can use prefix ACLs scoped specifically to the service and environment.

Do not make the application principal a superuser just to bypass authorization errors. Identify the principal, resource, and operation from broker logs, then grant least privilege.

## 19. Transactional Listeners and Error Handlers

Error handling in a transactional container has different semantics from non-transactional listeners.

With non-transactional containers, **DefaultErrorHandler** is commonly used to seek/retry/recover. With transactional containers, an exception can abort the transaction and post-rollback handling typically goes through **AfterRollbackProcessor**.

When designing consume-transform-produce, clarify:

1. Who starts the Kafka transaction: container or service?
2. Does `KafkaTemplate` join the right transaction?
3. Are input offsets sent into the transaction?
4. If the listener fails, which transaction aborts?
5. When sending to a DLT, are DLT output and input offset commit safely coordinated?
6. Are there DB/HTTP side effects needing idempotency or compensation?

Never manually call commit/abort on a container-managed `KafkaProducer`. Spring Kafka must retain control over producer lifecycle, offsets, and transaction outcomes.

### 19.1. DLT in Transactional Flows

A poison record must be handled so it does not block a partition indefinitely. If publishing to the DLT fails yet the input offset still commits, the record may be skipped without isolation.

Verify the DLT recoverer / `AfterRollbackProcessor` and commit policy for your running Spring Kafka version, rather than assuming non-transactional record listener settings apply verbatim.

## 20. Monitoring KafkaTemplate in Transactions

| Metric / signal | What to observe |
|---|---|
| Transaction commit/abort count | How Kafka transactions are concluding |
| Transaction duration | Whether any transactions stay open abnormally long |
| Producer send failures | Which topic or partition fails writes |
| Transaction commit latency | Whether the Kafka coordinator responds slowly |
| Producer fencing errors | Whether transactional ID collisions occur |
| Transactional ID distribution | Whether replicas use distinct namespaces |
| Producer cache usage | Whether producers are created/closed too frequently |
| `read_committed` consumer lag | Whether outputs are blocked by open transactions |
| Last Stable Offset | Whether open transactions stall read progress |
| DLT recovery success/failure | Whether poison records are safely isolated |
| Downstream duplicate detection | Whether replays cause duplicate side effects |

Exact metric names depend on the Kafka client, Spring Kafka, Micrometer, and exporters. Some transaction outcome details must be instrumented at the service or container layer.

Logs may record:

~~~text
service=order-service
action=publishOrderEvents
topic=orders.events
transactionOutcome=committed
transactionDurationMs=38
correlationId=ord-801
~~~

Never log tokens, passwords, JAAS configs, private keys, or sensitive payloads. Avoid using event IDs or order IDs as high-cardinality metric labels.

## 21. Diagnosing Common Errors

| Symptom | Possible cause | Check |
|---|---|---|
| "No transaction is in process" | Send outside transaction | Verify `@Transactional` manager, `executeInTransaction`, AOP proxy |
| `ProducerFencedException` after scaling | Replicas share transactional ID | Check per-pod `transaction-id-prefix` |
| `TransactionalIdAuthorizationException` | Missing ACL on actual ID | Check broker principal/resource |
| Send future succeeds yet consumer sees nothing | Transaction uncommitted, aborted, or consumer not polling | Check outcome and `isolation.level` |
| DB committed yet Kafka lacks event | No atomic DB+Kafka commit | Evaluate outbox |
| Consumer lag rises despite broker records | Open transaction holds LSO | Check `read_committed` and transaction duration |
| Errors after long idle | Cached transactional producer and ID expiration | Check `maxAge` and broker config |
| DLT write fails | Serializer, topic, ACL, broker | Verify recovery outcome |
| Timeout during commit | Coordinator/network/transaction duration | Check coordinator and timeouts |

### 21.1. Do Not Equate Send Success with Commit Success

A producer future can complete successfully before the Kafka transaction commits. If the transaction subsequently aborts, downstream `read_committed` consumers still will not receive the record.

Log the transaction outcome at the appropriate boundary and retain correlation IDs to reconcile when commit outcome is uncertain.

### 21.2. Fencing After Rollout

If two pods share a fixed prefix and generate colliding transactional IDs, they can continuously fence each other. When errors appear only after increasing replicas, check ID namespacing before raising retry counts.

## 22. Integration Tests for Kafka Transactions

Test scenarios using Embedded Kafka or Testcontainers with a transaction-capable broker.

### 22.1. Testing Commit

1. Configure a transactional `ProducerFactory` and `KafkaTemplate`.
2. Open a transaction via `@Transactional` or `executeInTransaction`.
3. Send records A and B to appropriate topics/partitions.
4. Commit the transaction.
5. Read back with a `read_committed` consumer.
6. Verify both committed outputs appear.

### 22.2. Testing Abort

1. Start a transaction.
2. Send record A.
3. Throw a `RuntimeException` inside the callback.
4. Verify the transaction aborts.
5. Verify a `read_committed` consumer does not return record A.
6. Run a new transaction to confirm the producer lifecycle continues per policy.

Illustrative example:

~~~java
assertThrows(
    IllegalStateException.class,
    () -> kafkaTemplate.executeInTransaction(ops -> {
        ops.send("orders.events", "o-1", event).join();
        throw new IllegalStateException("force abort");
    })
);
~~~

This is an illustrative test snippet; supply appropriate test data, `KafkaTemplate`, and imports.

### 22.3. Testing Restarts, Fencing, and External Consistency

- Restart the producer before commit and inspect `read_committed` output.
- Intentionally create two producers with the same transactional ID in a test environment to observe fencing.
- Inject coordinator/commit failures and verify the app does not treat an uncertain outcome as guaranteed success.
- If a DB is involved, simulate a crash between DB commit and Kafka commit.
- Verify that an outbox publisher re-sending an event remains safe due to idempotency.

## 23. Operational Runbook

1. Identify the actual `KafkaTemplate` and `ProducerFactory` in use.
2. Check the effective `transaction-id-prefix` for each instance.
3. Verify `KafkaTransactionManager` is selected properly in `@Transactional`.
4. Identify the boundary: annotation, `executeInTransaction`, or listener container.
5. Verify the producer participates in the active transaction.
6. For consume-transform-produce, verify input offsets travel with Kafka outputs.
7. Check that downstream uses `read_committed` if aborted records must be excluded.
8. Verify ACLs on topics and `TransactionalId`.
9. Monitor transaction duration, commits/aborts, and producer fencing.
10. On errors, distinguish send timeout, commit timeout, authorization, and fenced producers.
11. Retry at a safe transaction scope; avoid creating duplicate side effects.
12. Protect DB/HTTP side effects with outbox, inbox, or compensation.
13. Test restarts, aborts, fencing, DLT recovery, and idle producers.
14. Document reconciliation procedures when commit outcomes are uncertain.

## 24. Misconceptions to Avoid

**`KafkaTemplate.send` succeeding means the transaction committed.** False: send acknowledgments can arrive before transaction commit.

**`executeInTransaction` always reuses the listener transaction.** False: this method opens its own local transaction.

**`@Transactional` automatically merges DB and Kafka into one XA transaction.** False: they use different transaction managers and resources.

**Kafka idempotence is equivalent to transactions.** False: idempotence handles retry duplicates; transactions manage commit/abort for a group of Kafka operations.

**`read_uncommitted` reads only committed records.** False: it can return aborted transactional records.

**All pods can share one transactional ID.** False: concurrent use of the same ID causes fencing.

**Retry `ProducerFencedException` infinitely.** False: an old fenced producer cannot continue operating normally.

**Keeping transactions open very long is safer.** False: long transactions risk timeouts and stall `read_committed` consumers.

**Kafka transactions guarantee two downstream apps process simultaneously.** False: Kafka atomic commit does not control downstream poll schedules or side effects.

## 25. Key Takeaways

**`KafkaTemplate` in transactions** lets Spring Kafka send multiple records to Kafka as a single commit/abort unit. Producer-initiated transactions typically use **@Transactional** with `KafkaTransactionManager` or **KafkaTemplate.executeInTransaction**. In consumer-initiated transactions, the listener container opens the transaction and `KafkaTemplate` sends outputs so input offsets and Kafka outputs are managed together under Kafka semantics.

To operate safely, configure a transactional `ProducerFactory`, unique `transaction-id-prefix` per instance, ACLs, timeouts, and downstream `read_committed`. Send acknowledgments do not mean transaction commit; monitor commits/aborts, fencing, and transaction durations.

Kafka transactions do not atomically commit on behalf of databases or HTTP services. For cross-system workflows, combine outbox/inbox, idempotency, and proper recovery to guarantee correctness even when processes crash or commit outcomes are uncertain.
