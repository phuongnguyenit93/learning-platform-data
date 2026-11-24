# Legacy Transaction Manager Deprecation in Spring Kafka

## 1. Why Does an API Change Matter for Data Reliability?

An application consumes events from Kafka, updates a database, and then publishes a result event to another topic. In an older version, the project might have used `ChainedKafkaTransactionManager` to "combine" Kafka and JDBC transactions, attaching that transaction manager directly to the listener container. When upgrading Spring Kafka, the IDE flags `@Deprecated`, or `ContainerProperties.setTransactionManager(...)` is marked for removal.

The tempting mistake is swapping one class for another to clear the warning without checking **commit order and recoverability**. That can leave the service working on the happy path, yet when the broker, database, or network fails right at commit time, data between the two systems can diverge.

This article, **Legacy Transaction Manager Deprecation**, belongs to *Spring Kafka Reliability Operations → Upgrades and Compatibility*. The goal is not to memorize every Spring transaction API, but to understand why legacy transaction managers were deprecated, what replacements are recommended, and how to migrate **without losing or duplicating business side effects**.

You will learn how to:

- Identify exactly which APIs are deprecated, the relevant versions, and which APIs **remain supported**.
- Understand `ChainedKafkaTransactionManager` based on `ChainedTransactionManager` and why chaining is not XA/two-phase commit.
- Replace it with `KafkaTransactionManager` on the Kafka container and `@Transactional` with a DB transaction manager at the service layer.
- Distinguish **consumer-initiated** from **producer-initiated** transactions.
- Analyze DB-first/Kafka-first commit orders, partial-commit windows, and how idempotency handles redelivery.
- Properly configure `transactionIdPrefix`, producer factories, consumer isolation, listener containers, and multiple transaction manager beans.
- Adjust error handlers, rollback processors, DLT/retry, and testing strategies when the container uses transactions.
- Build a deployment, observability, and migration rollback checklist.

Examples are based on **Java 17, Spring Boot 3.4.x, Spring Kafka 3.3.x, and Spring Framework 6.x**. In Spring Boot 4/Spring Kafka 4, auto-configuration package structures change; consult the Javadoc for your exact version set. Examples are illustrative designs and do not claim to have been built/executed in any specific project environment.

---

## 2. What Exactly Was Deprecated?

The phrase "legacy transaction manager" in Spring Kafka causes confusion because there are **two related deprecation groups**, which are not identical.

| Component | Status in Spring Kafka 3.3.x | Replacement |
|---|---|---|
| `org.springframework.kafka.transaction.ChainedKafkaTransactionManager<K,V>` | Deprecated since Spring Kafka **2.7** | Use `KafkaTransactionManager` on the container; start the DB transaction via `@Transactional` on listener/service |
| `org.springframework.data.transaction.ChainedTransactionManager` | Deprecated since Spring Data Commons **2.5** | Transaction synchronization or separate coordination; for high reliability, consider outbox/idempotency |
| `ContainerProperties.setTransactionManager(PlatformTransactionManager)` | Deprecated since Spring Kafka **3.2**, marked for removal | `ContainerProperties.setKafkaAwareTransactionManager(KafkaAwareTransactionManager<?, ?>)` |
| `ContainerProperties.getTransactionManager()` | Deprecated since Spring Kafka **3.2**, marked for removal | `getKafkaAwareTransactionManager()` |
| `KafkaAwareTransactionManager<K,V>` | Supported interface in 3.3 | Used when the container needs a transaction manager aware of `ProducerFactory` |
| `KafkaTransactionManager<K,V>` | Supported, **not the deprecated class here** | Still used for transactional Kafka producers/containers |

**Timeline:** `ChainedKafkaTransactionManager` existed since Spring Kafka 2.1.3; starting in 2.7, documentation advised against using it in new designs. In 3.2, Spring Kafka also narrowed the type accepted by `ContainerProperties`, replacing the general `PlatformTransactionManager` setter with one taking `KafkaAwareTransactionManager`. As a result, projects upgrading from 2.x to 3.3 can encounter both warning groups at once.

"Deprecated" **does not automatically mean "the class has been deleted."** For example, Spring Kafka 3.3 and 4.0 Javadocs still list `ChainedKafkaTransactionManager` with the deprecated annotation. Yet continuing to rely on APIs marked for removal increases future upgrade costs and retains known partial-commit risks.

### 2.1. How to Spot It in Legacy Code

Sign 1:

```java
import org.springframework.kafka.transaction
        .ChainedKafkaTransactionManager;

@Bean
ChainedKafkaTransactionManager<String, String> chained(
        PlatformTransactionManager jdbcTx,
        KafkaTransactionManager<String, String> kafkaTx) {

    return new ChainedKafkaTransactionManager<>(
            jdbcTx, kafkaTx);
}
```

Sign 2:

```java
factory.getContainerProperties()
        .setTransactionManager(chained);
```

Sign 3: the project does not define a chained manager itself, yet still calls `setTransactionManager(kafkaTransactionManager)`. That case is primarily a **container property API migration**, not removing chaining.

Sign 4: multiple `PlatformTransactionManager` beans exist and `@Transactional` code does not specify a bean. Even without deprecation warnings, transactions may start under the wrong manager or fail startup due to ambiguity.

### 2.2. Why Deprecation Is Not Just About "Cleaner Code"

A chained transaction manager cannot turn two independent resources into **one distributed atomic transaction**. If one resource commits while the other fails at commit time, the system ends up with one side succeeded and the other failed. The old class may throw an exception, yet it cannot undo a commit already completed elsewhere.

A proper migration must therefore **make Kafka transaction boundaries, DB transaction boundaries, and commit order explicit**, and then design replay/idempotency/reconciliation rather than trusting the name "Chained" to guarantee safety.

---

## 3. How Did the Legacy Transaction Manager Actually Work?

### 3.1. In What Order Does ChainedTransactionManager Start and End?

`ChainedKafkaTransactionManager` extends Spring Data's `ChainedTransactionManager`. The parent manager takes a sequence of `PlatformTransactionManager`s. In principle:

- **Starts transactions** in the order passed in.
- **Commits and rolls back** in reverse order.
- If a resource fails to commit, the manager can roll back resources not yet committed.
- However, any resource that already committed successfully **cannot be rolled back** by the transaction manager alone.

For example:

```java
new ChainedKafkaTransactionManager<>(
        dbTransactionManager,
        kafkaTransactionManager);
```

In this chain, **Kafka commits before the DB** due to reverse order. If Kafka commits successfully and then the DB commit fails, Kafka consumers can read the output event while the DB data was never persisted.

Reversing the constructor order:

```java
new ChainedKafkaTransactionManager<>(
        kafkaTransactionManager,
        dbTransactionManager);
```

makes **the DB commit before Kafka** under the chaining mechanism. If the DB commits yet the Kafka commit fails, the DB contains a change with no corresponding event.

**Do not pick an order by intuition.** Commit order is a business and failure-recovery decision. Both orders have partial-commit windows.

### 3.2. HeuristicCompletionException

The `ChainedTransactionManager` Javadoc warns about **partially committed** states and can throw `HeuristicCompletionException` when committing one delegate fails after another delegate already committed. This is not an automatic compensation mechanism.

Simulation:

```text
Begin DB transaction
Begin Kafka transaction
       │
       ▼
Process event
       │
       ▼
Commit Kafka ────────── SUCCESS
       │
       ▼
Commit DB ───────────── FAILURE
       │
       ▼
Partial commit:
  downstream sees Kafka event
  database has not saved matching data
```

The system may have to run reconciliation, emit a compensating event, mark a pending state, or reprocess by business key. Chaining has no XA-style commit coordinator guaranteeing both sides commit or roll back together under every failure.

### 3.3. KafkaTransactionManager Is Not an XA Manager Either

`KafkaTransactionManager` manages transactions on a **Kafka ProducerFactory**. It can commit Kafka messages and offsets within a Kafka transaction when the container is configured accordingly. It **does not** enlist a JDBC database into the same XA transaction.

Spring Kafka transactions work cleanly for the flow:

```text
Consume Kafka → transform → produce Kafka
                  │
                  ▼
      Kafka output + consumed offsets
           inside Kafka transaction
```

Yet when JDBC/HTTP/email side effects exist:

```text
Consume Kafka → update PostgreSQL → produce Kafka
                        │
               a different transaction
```

You must design for divergence between the two resources.

---

## 4. Three Distinct Transaction Scenarios to Choose From Correctly

Do not apply a single migration template to every piece of code using Kafka.

### 4.1. Kafka → Kafka (No Database)

A listener reads an input topic, transforms the message, and publishes to an output topic. The container starts a Kafka transaction, and `KafkaTemplate` sharing the same producer factory participates. The input offset is sent into the Kafka transaction upon container completion.

Within Kafka read-process-write scope, exactly-once semantics can be achieved given proper configuration and `read_committed`, without needing a DB transaction manager.

**Design:** a single `KafkaTransactionManager` suffices; `ChainedKafkaTransactionManager` is unnecessary.

### 4.2. Kafka → DB or Kafka → DB + Kafka

The listener reads Kafka, updates a database, and optionally publishes to an output topic. The migration pattern recommended by Spring Kafka:

1. The container starts the **Kafka transaction** via `KafkaTransactionManager`.
2. The service/listener method is guarded with `@Transactional("dbTransactionManager")` to open a separate **DB transaction**.
3. The DB transaction completes when the service method returns.
4. The container then commits the Kafka transaction (including Kafka outputs and the input offset).

In the normal flow, the order is **DB-first, Kafka-second**. If the Kafka commit fails after the DB commit, the input record can be redelivered. Hence the DB write must be **idempotent**.

### 4.3. DB → Kafka (Producer-Initiated, No Kafka Consumer Container)

A REST endpoint or scheduled job updates the database and publishes an event. Typically `@Transactional("dbTransactionManager")` is the primary transaction; when using a properly configured transactional `KafkaTemplate`, sending can synchronize a Kafka transaction with the DB transaction.

In this flow, the DB commits first and Kafka commits second. If the Kafka commit fails, the DB may already have committed. For reliable publication requirements, a **transactional outbox** is usually safer than synchronization alone.

### 4.4. Selection Matrix

| Flow | Common Approach | What Must Be Protected |
|---|---|---|
| Kafka → Kafka | Kafka container transaction | Producer factory, offsets, isolation, fencing |
| Kafka → DB | Kafka container transaction + DB `@Transactional` | DB redelivery/idempotency |
| Kafka → DB → Kafka | Kafka container transaction + DB `@Transactional` + `KafkaTemplate` | DB/Kafka partial commits |
| DB → Kafka | DB transaction + Kafka synchronization | DB commits before Kafka; publish reconciliation |
| DB → Kafka requiring zero lost events | Transactional outbox + dispatcher | At-least-once outbox delivery and consumer idempotency |
| Kafka → HTTP/payment | Kafka transactions do not cover HTTP side effects | Idempotency keys, unknown outcomes, reconciliation |

---

## 5. Legacy Pattern: What to Replace and What Not to Copy

Example from an older Spring Kafka project:

```java
// LEGACY, DO NOT USE FOR NEW CODE.

@Bean("chainedTransactionManager")
ChainedKafkaTransactionManager<String, String> chainedTx(
        @Qualifier("dbTransactionManager")
                PlatformTransactionManager dbTx,
        KafkaTransactionManager<String, String> kafkaTx) {

    return new ChainedKafkaTransactionManager<>(
            dbTx, kafkaTx);
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, String>
legacyFactory(
        ConsumerFactory<String, String> consumers,
        ChainedKafkaTransactionManager<String, String> chainedTx) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory
                    <String, String>();

    factory.setConsumerFactory(consumers);
    factory.getContainerProperties()
            .setTransactionManager(chainedTx);

    return factory;
}
```

**Issue 1:** `ChainedKafkaTransactionManager` was deprecated in 2.7. **Issue 2:** `setTransactionManager(PlatformTransactionManager)` was deprecated in 3.2. **Issue 3:** even when it succeeds, there is no DB + Kafka atomicity.

The solution is **not** swapping `ChainedKafkaTransactionManager` for `KafkaTransactionManager` on the same line and calling the migration done. You must also decide where the DB transaction opens, which manager each service uses, the new commit order, and redelivery handling logic.

---

## 6. Preparing Kafka Transactions in Spring Boot 3.x

### 6.1. Enabling the Transactional Producer

In Spring Boot, the standard way to enable Kafka transactions is declaring:

```yaml
spring:
  kafka:
    bootstrap-servers: "${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}"
    producer:
      transaction-id-prefix: "orders-${POD_NAME:local}-tx-"
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
    consumer:
      group-id: "orders-worker"
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      properties:
        isolation.level: read_committed
    listener:
      type: single
      concurrency: 3
```

In a single-machine dev environment, the `local` fallback is illustrative only. **Production must use a unique prefix per instance/pod**, e.g., sourced from pod name/instance identity, and never allow two live processes to share a prefix.

When `spring.kafka.producer.transaction-id-prefix` is present and the app uses standard Kafka auto-configuration, Spring Boot can auto-configure a transactional producer factory, a `KafkaTransactionManager`, and wire the manager into the default listener container. If the application creates its own factory or defines multiple transaction manager beans, verify explicit wiring instead of assuming Boot picks every bean correctly.

### 6.2. Each Replica Needs Its Own Transaction ID

Kafka transactions identify producers via `transactional.id`. With Spring Kafka 3.x, the producer factory typically constructs IDs from prefix + suffix. If two replicas use the same ID, Kafka can **fence** the older producer, causing `ProducerFencedException`/transaction failures.

```text
Pod A:
  prefix = orders-pod-a-tx-
  transactional.id = orders-pod-a-tx-0 / 1 / ...

Pod B:
  prefix = orders-pod-b-tx-
  transactional.id = orders-pod-b-tx-0 / 1 / ...
```

Do not hard-code one identical prefix across all pods of the same Deployment. When a pod restarts with the same identity, understand old producer lifecycles, transaction timeouts, and fencing; do not treat unique prefixes as a silver bullet while ignoring resource management.

### 6.3. ProducerFactory and KafkaTemplate Must Match

If declaring manually:

```java
@Bean("kafkaTransactionManager")
KafkaTransactionManager<String, String> kafkaTransactionManager(
        ProducerFactory<String, String> producerFactory) {

    if (!producerFactory.transactionCapable()) {
        throw new IllegalStateException(
                "ProducerFactory must support transactions");
    }

    return new KafkaTransactionManager<>(producerFactory);
}
```

This snippet **applies only when you manage the bean explicitly**; do not declare a duplicate `KafkaTransactionManager` alongside Boot's auto-created bean. Choose one approach: Boot auto-config or explicit custom configuration.

The `KafkaTemplate` used within the same transaction must share **the same `ProducerFactory`** as the manager. If the template sends through a different producer factory or cluster, it will not automatically participate in the open Kafka transaction.

### 6.4. EOSMode.V2 and Isolation

Starting in Spring Kafka 3.0, `EOSMode.V2` is the supported EOS mode. Do not try preserving an old EOS mode switch just to avoid changes during migration.

Consumers reading output from transactional producers should consider:

```yaml
spring:
  kafka:
    consumer:
      properties:
        isolation.level: read_committed
```

`read_committed` helps consumers avoid reading records from aborted Kafka transactions. It **does not** establish consistency for JDBC databases or remote HTTP calls.

### 6.5. Transaction ID Cache and Concurrency

Spring Kafka 3.2 includes `TransactionIdSuffixStrategy` and `DefaultTransactionIdSuffixStrategy` to manage transactional ID suffixes. When the producer factory uses a bounded suffix cache:

- Cache size must be **at least equal to the concurrency** of transactional listener containers sharing that factory.
- If nested Kafka transactions exist or multiple listeners share the factory, reserve additional capacity.
- Monitor `NoProducerAvailableException` when no suffix/producer is available.
- Check producer connection counts, memory, and broker transaction state.
- Evaluate `maxAge` of cached producers to avoid reusing a producer that sat idle too long and got fenced by broker transactional ID expiration.

Do not grow the cache infinitely to mask resource starvation; sizing depends on actual concurrent transactions.

---

## 7. Migrating Consumer-Initiated Transactions: Recommended Approach

### 7.1. Explicitly Define Two Managers

An application using both JDBC and Kafka can define two transaction managers:

```text
dbTransactionManager
    └── JdbcTransactionManager(DataSource)
         manages JDBC connections/transactions only

kafkaTransactionManager
    └── KafkaTransactionManager(ProducerFactory)
         manages Kafka producer transactions only

@KafkaListener container
    └── outer Kafka transaction

OrderProcessingService.process()
    └── @Transactional("dbTransactionManager")
         inner DB transaction
```

Example JDBC manager bean for Spring Framework 6:

```java
package com.example.kafka.tx;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.support.JdbcTransactionManager;

@Configuration(proxyBeanMethods = false)
public class DatabaseTxConfiguration {

    @Bean("dbTransactionManager")
    JdbcTransactionManager dbTransactionManager(
            DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
```

`JdbcTransactionManager` is an appropriate implementation for JDBC; `DataSourceTransactionManager` or `JpaTransactionManager` can also be used depending on the persistence stack. If using JPA, choose the manager matching `EntityManagerFactory` rather than assuming a JDBC manager manages the full JPA persistence context.

**Spring Boot auto-config note:** when defining custom transaction managers, default bean creation conditions can change; inspect bean names/types in the application context. Examples here assume the app has one Kafka manager bean and one matching DB manager bean.

### 7.2. New Listener Factory with the Right Setter

In Spring Boot 3.4.x, `ConcurrentKafkaListenerContainerFactoryConfigurer` lives in `org.springframework.boot.autoconfigure.kafka`.

```java
package com.example.kafka.tx;

import org.springframework.boot.autoconfigure.kafka
        .ConcurrentKafkaListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import org.springframework.kafka.config
        .ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.transaction
        .KafkaTransactionManager;

@Configuration(proxyBeanMethods = false)
public class KafkaListenerTxConfiguration {

    @Bean("ordersTxListenerContainerFactory")
    ConcurrentKafkaListenerContainerFactory<Object, Object>
    ordersTxListenerContainerFactory(
            ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
            ConsumerFactory<Object, Object> consumerFactory,
            KafkaTransactionManager<?, ?> kafkaTransactionManager) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory
                        <Object, Object>();

        // Apply baseline from spring.kafka.* bound by Boot.
        configurer.configure(factory, consumerFactory);

        // API supported since Spring Kafka 3.2:
        factory.getContainerProperties()
                .setKafkaAwareTransactionManager(
                        kafkaTransactionManager);

        factory.setConcurrency(3);
        factory.setBatchListener(false);

        return factory;
    }
}
```

Core migration change:

```java
// Old, deprecated since 3.2:
containerProperties.setTransactionManager(oldManager);

// New:
containerProperties.setKafkaAwareTransactionManager(
        kafkaTransactionManager);
```

**Do not** pass a `JdbcTransactionManager` or a `ChainedKafkaTransactionManager` to the new setter. The `KafkaAwareTransactionManager` interface is specifically for a Kafka manager aware of `ProducerFactory`.

If using Boot's default factory and only standard features are needed, you may **not need a custom factory**: configure the producer transaction ID prefix and verify Boot wired the manager onto the container. A dedicated factory makes sense when custom naming/behavior is required or to avoid ambiguity across multiple listeners.

### 7.3. Listener Starts the Kafka Transaction, Service Opens the DB Transaction

```java
package com.example.kafka.tx;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrdersEventListener {

    private final OrdersApplicationService service;

    public OrdersEventListener(
            OrdersApplicationService service) {
        this.service = service;
    }

    @KafkaListener(
            id = "orders-tx-v1",
            topics = "orders.events",
            groupId = "orders-worker",
            containerFactory =
                    "ordersTxListenerContainerFactory")
    public void onOrder(String payload) {

        service.applyEvent(payload);

        // Do not swallow exceptions:
        // if the service fails, the container must roll back.
    }
}
```

Service:

```java
package com.example.kafka.tx;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrdersApplicationService {

    private final OrdersRepository orders;
    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrdersApplicationService(
            OrdersRepository orders,
            KafkaTemplate<String, String> kafkaTemplate) {

        this.orders = orders;
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("dbTransactionManager")
    public void applyEvent(String payload) {
        OrderEvent event = OrderEvent.parse(payload);

        // Repository must enforce idempotency by eventId.
        boolean firstProcessing =
                orders.claimEventId(event.eventId());

        if (!firstProcessing) {
            return; // Kafka redelivery of an already-processed event.
        }

        orders.updateStatus(
                event.orderId(), event.status());

        kafkaTemplate.send(
                "orders.processed",
                event.orderId(),
                event.toProcessedJson());
    }
}
```

Types `OrdersRepository` and `OrderEvent` are domain components to define in your project; section 10 (section 11.3) shows a database deduplication example. The logic illustrates **Kafka → DB + Kafka**. It runs with a transactional `KafkaTemplate` sharing the same producer factory on which the container opened the transaction.

### 7.4. Commit Order in This Flow

```text
Kafka listener container
  ├── START Kafka transaction
  │       ├── receive input record
  │       └── call OrdersApplicationService
  │               ├── START DB transaction
  │               ├── INSERT dedup key
  │               ├── UPDATE business table
  │               ├── KafkaTemplate.send(...) in Kafka tx
  │               └── COMMIT DB transaction
  │
  ├── listener returns successfully
  ├── send consumed offsets to Kafka transaction
  └── COMMIT Kafka transaction
```

When everything succeeds:

- The database holds the business effect.
- Topic `orders.processed` receives the committed output event.
- The consumed offset of `orders.events` is committed in the corresponding Kafka transaction.

When the DB commit fails, the exception must propagate to the listener; the Kafka transaction rolls back and the input is not marked processed.

When **the DB commit succeeds yet the Kafka commit fails**, the input can be redelivered. Use an idempotent DB transaction, otherwise the business update runs a second time. **The new pattern does not turn DB + Kafka commits into 2PC**; it makes the boundary explicit so recovery can be designed.

### 7.5. Why Place `@Transactional` on a Separate Service Bean?

Spring Framework normally applies `@Transactional` through an AOP proxy. If a `this.applyEvent(...)` method calls itself inside the same class, self-invocation can bypass the proxy and fail to open the expected DB transaction.

To keep things clear and testable:

- The listener only receives/dispatches messages.
- A Spring-managed service bean carries `@Transactional("dbTransactionManager")`.
- The listener calls it through the service's bean proxy.
- Do not annotate private methods expecting proxies to apply.
- Do not catch exceptions in the listener and return normally when the DB failed.

---

## 8. When Is Only Changing the `setTransactionManager` API Enough?

If legacy code **already used a plain `KafkaTransactionManager`**, for instance:

```java
factory.getContainerProperties()
        .setTransactionManager(kafkaTransactionManager);
```

then migration is mainly:

```java
factory.getContainerProperties()
        .setKafkaAwareTransactionManager(kafkaTransactionManager);
```

In this case business transaction boundaries do not necessarily change; still verify the transaction-enabled producer factory, offset commits, error handling, and listener behavior before deploying. Do not lump this together with replacing `ChainedKafkaTransactionManager`—the two changes carry different risk levels.

If legacy code passed a **non-Kafka** `PlatformTransactionManager` to the container, the new setter will not accept that type. Instead of casting, move the DB transaction to an appropriate service/interceptor layer such as `@Transactional`, and supply a Kafka transaction manager to the container only when Kafka transactional consumption is needed.

---

## 9. Producer-Initiated Flow: DB-First Synchronization

In flows without a Kafka listener container (REST/service/scheduler), Spring Kafka supports synchronizing a `KafkaTemplate` transaction with an active Spring transaction.

Example:

```java
@Service
public class BillingService {

    private final JdbcTemplate jdbc;
    private final KafkaTemplate<String, String> kafka;

    public BillingService(
            JdbcTemplate jdbc,
            KafkaTemplate<String, String> kafka) {
        this.jdbc = jdbc;
        this.kafka = kafka;
    }

    @Transactional("dbTransactionManager")
    public void createInvoice(
            String invoiceId, String payload) {

        jdbc.update(
                "INSERT INTO invoices (invoice_id) VALUES (?)",
                invoiceId);

        kafka.send("invoices.created", invoiceId, payload);
    }
}
```

With a suitable transactional producer factory and a **producer-initiated DB transaction**, `KafkaTemplate` can synchronize the Kafka transaction to the DB transaction: **DB commits first, Kafka commits second**. This differs from a listener container that already opened an outer Kafka transaction.

### 9.1. DB-First Failure Window

```text
DB transaction BEGIN
     │
     ├─ insert invoice
     ├─ KafkaTemplate.send
     │
DB COMMIT ──────────── SUCCESS
     │
Kafka COMMIT ───────── FAILURE
     │
     ▼
DB has invoice;
Kafka lacks/has unknown event.
```

In Spring Kafka versions highlighted by the docs (2.5.17, 2.6.12, 2.7.9, 2.8.0 and later), a commit failure in the synchronized transaction after the primary commit is thrown to the caller rather than silently ignored. **An exception does not mean the DB rolled back.** The caller must have a way to determine and reconcile state.

### 9.2. Do Not Blindly Retry the Whole Method

If the caller sees an exception from a failed Kafka commit and retries `createInvoice(...)`, the DB `INSERT` may trigger a duplicate key error or create a second invoice if a new ID is generated. Use stable business IDs and idempotency.

A worker cannot infer from a Kafka exception that no message was sent, no DB row exists, or no transaction committed. Reconcile against durable state.

### 9.3. `@Transactional` Does Not Auto-Select the Right DB Manager

When both `dbTransactionManager` and `kafkaTransactionManager` exist:

```java
@Transactional("dbTransactionManager")
```

is clearer than:

```java
@Transactional
```

An unqualified annotation can depend on bean names/defaults/primary markers in the context, causing ambiguity or picking an unintended manager. Never assume that with multiple managers Spring "picks automatically based on the JDBC method called inside."

---

## 10. Kafka-First via Nested `@Transactional`: Understanding the Consequences

Sometimes business logic wants **Kafka to commit first** and the DB to commit afterward. Spring Kafka documents using nested transactional methods across two explicit beans/proxies.

### 10.1. Nested Services Example

Kafka writer bean:

```java
@Service
public class KafkaInvoicePublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public KafkaInvoicePublisher(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("kafkaTransactionManager")
    public void publish(String invoiceId, String body) {
        kafkaTemplate.send(
                "invoices.created", invoiceId, body);
    }
}
```

DB orchestrator bean:

```java
@Service
public class InvoiceOrchestrator {

    private final JdbcTemplate jdbc;
    private final KafkaInvoicePublisher publisher;

    public InvoiceOrchestrator(
            JdbcTemplate jdbc,
            KafkaInvoicePublisher publisher) {
        this.jdbc = jdbc;
        this.publisher = publisher;
    }

    @Transactional("dbTransactionManager")
    public void execute(String invoiceId, String payload) {

        jdbc.update(
                "INSERT INTO invoices (invoice_id) VALUES (?)",
                invoiceId);

        // Proxy on another bean opens/commits Kafka transaction.
        publisher.publish(invoiceId, payload);

        // After the Kafka method returns, outer DB TX commits.
    }
}
```

**Order:** open outer DB transaction → open inner Kafka transaction → inner Kafka commits → outer DB commits.

### 10.2. Kafka-First Failure Window

```text
DB transaction BEGIN
     │
Kafka transaction BEGIN
     │
Kafka COMMIT ──────────── SUCCESS
     │
DB COMMIT ─────────────── FAILURE
     │
     ▼
Consumer already sees invoice event;
database lacks matching invoice.
```

Do not use this option if downstream consumers must read the DB immediately upon receiving the Kafka event without tolerating an "event arrives before data" state. For eventually consistent systems, state protocols and reconciliation are still required.

### 10.3. Note That Nesting Is Not XA

Nested `@Transactional` across two different managers merely creates **two local transactions** whose completion order is governed by method scope. An inner transaction commit is not reversed by rolling back the outer transaction.

Hence "Kafka-first" is not universally safer than DB-first; it simply shifts the direction of potential inconsistency.

---

## 11. A More Accurate Failure Model: Partial-Commit Matrix

You must analyze both success cases and failures that cannot roll back together.

| Flow | Failure Occurs When | Possible Remaining State | Action |
|---|---|---|---|
| Consumer-initiated, DB-first | DB update fails before commit | Kafka transaction rolls back; input can redeliver | Fix DB, bounded retry |
| Consumer-initiated, DB-first | DB commits OK, Kafka commit fails | DB effect exists, Kafka output/offset may be uncommitted | DB dedup, redelivery, and reconciliation |
| Producer-initiated, DB-first | DB commits OK, Kafka commit fails | DB row exists, Kafka event missing/unknown | Outbox or publish reconciliation |
| Producer-initiated, Kafka-first | Kafka commits OK, DB commit fails | Event visible, DB row missing | Consumer handles pending state, compensation |
| Kafka-only read-process-write | Kafka transaction aborts | Kafka output and offset in transaction do not commit | Consumer redelivery |
| DB transaction business error | Exception caught/swallowed | App may return success even though DB failed | Never swallow errors; ensure rollback |
| HTTP side effect alongside Kafka | HTTP timeout after server commit | Remote outcome unknown | Idempotency keys, status lookup |
| DLT publish failure | Recoverer could not store failed record | Record not safely recovered | Do not mark handled; alert/retry |

### 11.1. Why Is DB Idempotency Mandatory?

Suppose a consumer processes event `evt-123`:

1. DB commit records the order status.
2. Kafka transaction commit fails; offset is not committed.
3. When the consumer restarts, Kafka redelivers `evt-123`.
4. If the code adds balance a second time, the business effect is duplicated.
5. If the DB records a unique marker `evt-123` in the same transaction as the update, the second pass sees it was already processed and skips creating a new side effect.

Idempotency must be designed around **event/business identity**, not merely the absence of thrown exceptions.

### 11.2. Where Does the Idempotency Key Come From?

Options:

- `eventId` stably generated by the producer for a business event.
- `businessTransactionId` or `paymentId` if it corresponds 1-to-1 with a side effect.
- `(topic, partition, offset)` to identify redelivery of a specific Kafka record.
- `aggregateId + version` if old event versions must not overwrite newer state.

Key `orderId` is usually **insufficient** when one order emits multiple legitimate events (`CREATED`, `PAID`, `SHIPPED`). Conversely, offset cannot deduplicate two records at different offsets carrying the same business event due to duplicate producer publishing.

### 11.3. Example Idempotent DB Transaction via Unique Key

PostgreSQL schema:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id      VARCHAR(120) NOT NULL,
    topic_name    VARCHAR(255) NOT NULL,
    partition_no  INTEGER NOT NULL,
    kafka_offset  BIGINT NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE order_state (
    order_id      VARCHAR(120) PRIMARY KEY,
    status        VARCHAR(40) NOT NULL
);
```

Repository service:

```java
@Service
public class OrdersRepository {

    private final JdbcTemplate jdbc;

    public OrdersRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public boolean claimEventId(
            String eventId,
            String topic,
            int partition,
            long offset) {

        int count = jdbc.update("""
            INSERT INTO processed_events (
                consumer_name, event_id,
                topic_name, partition_no, kafka_offset
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (consumer_name, event_id) DO NOTHING
            """,
            "orders-worker", eventId, topic, partition, offset);

        return count == 1;
    }

    public void updateStatus(
            String orderId, String status) {
        jdbc.update("""
            INSERT INTO order_state (order_id, status)
            VALUES (?, ?)
            ON CONFLICT (order_id)
            DO UPDATE SET status = EXCLUDED.status
            """,
            orderId, status);
    }
}
```

In this example, `claimEventId` and `updateStatus` must run inside the **same DB transaction** managed by `@Transactional("dbTransactionManager")`. If the "processed" marker commits first and the business update rolls back, a subsequent redelivery could be wrongly skipped.

If events carry business versions/ordering, `ON CONFLICT DO UPDATE` must check version. Do not let an older event overwrite newer state simply because its `eventId` had not appeared in the dedup table yet.

---

## 12. Outbox: When Is Transaction Synchronization Not Enough?

For **DB → Kafka** flows where the event must reliably be emitted after writing business rows, a transactional outbox is usually worth considering.

### 12.1. Pattern

```text
HTTP request / Scheduled job
        │
        ▼
@Transaction DB
  ├── INSERT/UPDATE business rows
  └── INSERT outbox event
        │
        ▼
    DB COMMIT
        │
        ▼
Outbox dispatcher (polling/CDC)
        │
        ├── Kafka send success
        │        └── mark SENT / ack by CDC
        └── Kafka send failure
                 └── retry later
```

Business rows and the outbox event are written **in the same DB transaction**, eliminating the risk of "DB committed yet the event is lost without a record to send."

### 12.2. Outbox Does Not Mean Kafka Messages Are Sent Once

A dispatcher can:

1. Successfully publish the event to Kafka.
2. Crash before marking the outbox row `SENT`.
3. Restart and publish the event again.

Thus an outbox typically guarantees **at-least-once delivery** to Kafka; consumers must use `eventId` and idempotency to handle duplicates. Do not treat an outbox as an absolute exactly-once promise across all external systems.

### 12.3. When Is Synchronization Still Reasonable?

- Event side effects are not critical enough to require strict atomicity with the DB.
- Periodic database state scans can reconcile discrepancies.
- Downstream consumers are idempotent and accept eventual consistency.
- Outbox/CDC complexity outweighs the benefit at current scale.

The decision must be agreed upon by the business owner and operations team. Migrating merely to remove deprecation warnings does not automatically force building an outbox, yet you **must explicitly define which partial-commit window is acceptable**.

---

## 13. Transactional Container: Offsets, Rollback, and Error Handler

### 13.1. How Does a Kafka Transaction Include Offsets?

When a listener container has a `KafkaTransactionManager`, a successful processing cycle can include:

- The consumed record.
- Records sent by `KafkaTemplate` within the transaction.
- Offsets sent by the container into the Kafka transaction.
- Commit of the Kafka producer transaction.

If the transaction aborts, Kafka outputs and offsets inside that transaction do not become committed results. The consumer can re-read the record after restart/rebalance/seek per policy.

This differs from non-transactional containers using `AckMode.RECORD/BATCH` to commit offsets outside a producer transaction.

### 13.2. AckMode Is Not a 2PC Switch

In a transactional container, sending offsets to the transaction is managed by the container under record/batch listener modes. Do not use `MANUAL_IMMEDIATE` or manually call `Acknowledgment.acknowledge()` as a way to make Kafka + DB commits atomic.

If changing `AckMode` during migration, test actual runtime behavior; offset semantics with Kafka container transactions have specific rules unlike simple non-transactional listeners.

### 13.3. Error Handling with a Container Transaction

With non-transactional listeners, `DefaultErrorHandler` typically handles retries/recovery. With a **transactional container**, when the listener throws an exception, the Kafka transaction rolls back and `AfterRollbackProcessor` handles seek/replay/recovery per configuration.

Model:

```text
@KafkaListener throws
         │
         ▼
Kafka transaction ROLLBACK
         │
         ▼
AfterRollbackProcessor
         │
         ├── seek/reprocess with backoff
         ├── recover poison record per policy
         └── decide next step
```

Do not copy a non-transactional container's error handler verbatim and assume equivalence. Per Spring Kafka documentation, configuring a `CommonErrorHandler` that **swallows exceptions** inside a transactional container can cause the framework to treat processing as successful and commit instead of rolling back as intended. Handlers for transactional flows must preserve error propagation and the recovery contract.

### 13.4. DefaultAfterRollbackProcessor

Spring Kafka provides `DefaultAfterRollbackProcessor`, which can retry and recover per configuration. For records failing repeatedly, `DeadLetterPublishingRecoverer` can be used as the recoverer. When publishing to a DLT **and** committing the recovered offset inside a Kafka transaction, configure the version/producer factory, `kafkaTemplate`, and options such as `commitRecovered` and `kafkaOperations` per documentation.

Never ship DLT code assumed to "succeed" without verifying:

- The DLT topic has sufficient partitions/ACLs.
- The serializer handles raw payloads on deserialization failures.
- The DLT producer transaction participates in the right transaction.
- Recovered offsets are committed properly.
- If DLT publishing fails, the source record is not marked completed.
- A replay/quarantine workflow exists outside the listener.

### 13.5. Non-Blocking Retries and Container Transactions

Spring Kafka documentation notes that **non-blocking retries via retry topics do not combine with container transactions** in the usual way. When an error path routes records to a retry topic, transaction/offset behavior can diverge from transactional container expectations.

If a transactional listener needs retries:

- Prefer bounded blocking retries/after-rollback recovery where appropriate.
- For prolonged outages, pause/stop consumers and coordinate reprocessing.
- If non-blocking retry topics are required, redesign boundaries and evaluate ordering/transaction semantics explicitly.
- Do not just slap `@RetryableTopic` onto an existing method assuming transactions remain intact.

### 13.6. `KafkaTemplate.executeInTransaction` Does Not "Join" the Active Transaction as Often Assumed

`KafkaTemplate.executeInTransaction(...)` opens a **separate local Kafka transaction**. Documentation states that even when a `KafkaTransactionManager` or synchronized transaction is active, it uses a nested separate transaction rather than automatically joining the outer one.

Therefore:

```java
kafkaTemplate.executeInTransaction(ops -> {
    ops.send("topic", "value");
    return null;
});
```

should not be added inside a service already covered by a Kafka container transaction intending to "make the transaction safer." An inner transaction completing before the outer boundary creates another inconsistency window; use it only when an independent transaction is genuinely intended.

---

## 14. Step-by-Step Migration in a Real Codebase

### 14.1. Step 1 — Inventory

Find all occurrences of:

```text
ChainedKafkaTransactionManager
ChainedTransactionManager
setTransactionManager(
getTransactionManager(
KafkaTransactionManager
KafkaAwareTransactionManager
@Transactional
KafkaTemplate.executeInTransaction
transaction-id-prefix
setTransactionIdPrefix
AfterRollbackProcessor
DefaultErrorHandler
@RetryableTopic
```

Not every `setTransactionManager` in a codebase is a Spring Kafka API; some JDBC/JPA components have legitimate setters too. Identify the target class before replacing.

Document:

- Each listener ID, topics, group ID, and concurrency.
- Which factory bean each listener uses.
- Which `ProducerFactory`/`KafkaTemplate` participates in transactions.
- Which DB transaction manager is selected.
- The chain's current commit order.
- How retry/DLT works.
- Which business side effects can replay.
- Whether idempotency/outbox/reconciliation exists.

### 14.2. Step 2 — Draw Resource Boundaries

Before migration example:

```text
@KafkaListener
    │
    ▼
ChainedKafkaTransactionManager(DB, Kafka)
    ├── Kafka producer transaction
    └── DB transaction
          │
          ▼
Commit in reverse constructor order
```

After migration:

```text
@KafkaListener container
    │
    ▼
KafkaTransactionManager (outer)
    │
    ▼
@Transaction("dbTransactionManager") (inner)
    │
    ▼
DB commit
    │
    ▼
Kafka commit + consumed offsets
```

Compare both diagrams **for commit order**. If the legacy chain listed DB then Kafka, the old commit order was Kafka-first; the new DB-first design can **change failure recovery behavior**. Decide whether that fits business requirements rather than treating migration as a class rename.

### 14.3. Step 3 — Standardize Bean Names

Name beans explicitly:

```text
dbTransactionManager
kafkaTransactionManager
ordersTxListenerContainerFactory
ordersApplicationService
ordersEventListener
```

With `@Transactional`, always specify the manager when multiple resources exist:

```java
@Transactional(transactionManager = "dbTransactionManager")
```

If a Kafka-only service transaction is needed:

```java
@Transactional(transactionManager = "kafkaTransactionManager")
```

Do not casually add `@Primary` to hide ambiguity when two method groups must participate in different transactions.

### 14.4. Step 4 — Replace the Container Property

Change:

```java
props.setTransactionManager(chainedKafkaTransactionManager);
```

to:

```java
props.setKafkaAwareTransactionManager(
        kafkaTransactionManager);
```

and move the DB transaction into a service protected by a Spring transaction proxy. Delete the chained manager bean if unused, along with obsolete imports/references.

### 14.5. Step 5 — Keep Producer/Config Consistent

Check:

- `ProducerFactory.transactionCapable()`.
- `KafkaTemplate` uses the same `ProducerFactory` as the Kafka TM.
- `transactionIdPrefix` is uniquely assigned per pod/instance.
- Consumer isolation level matches transactional outputs.
- Consumer `enable.auto.commit=false` when using container-managed offsets.
- DLT/after-rollback policy is designed for a transactional container.
- Transaction cache has enough capacity as concurrency scales.

### 14.6. Step 6 — Add Idempotency If Missing

Before deploying, ensure **at a minimum** a safeguard against duplicate DB side effects when Kafka commit fails after DB commit. Prefer a unique business key + dedup table in the same DB transaction. For HTTP/email, add separate idempotency keys/outbox and reconciliation.

### 14.7. Step 7 — Fault-Injection Testing

Do not test only the listener happy path. Must test:

- DB commit failure.
- Kafka commit failure after DB commit.
- Pod crash before Kafka commit.
- Redelivery of the same event ID.
- Fenced producer.
- DLT/recovery failure.
- Transaction ID prefix collision across replicas.
- Retries after broker outage.
- Wrong transaction manager bean.
- Self-invocation bypassing DB transaction.

### 14.8. Step 8 — Canary and Rollback Plan

Deploy first to staging/canary with isolated test groups/topics; measure error rates, retries, rebalances, and business duplicates. If rolling out gradually within the same group, confirm running versions share compatible schemas and idempotency contracts.

If binary rollback is needed, do not just revert code: check published messages, committed offsets, and DB side effects already applied. Re-running old code with a chained manager may produce different recovery behavior from the new release; rollback must include a data procedure.

---

## 15. Version-by-Version API Checklist

| Task | Spring Kafka 2.6 and Earlier | 2.7–3.1 | 3.2–3.3 | Notes |
|---|---|---|---|---|
| Chaining DB + Kafka | Some projects use `ChainedKafkaTransactionManager` | Deprecated since 2.7 | Still deprecated | Do not use for new code |
| Container transaction setter | `setTransactionManager(...)` | Legacy API present | Deprecated since 3.2 | Use narrowed-type setter |
| Kafka TM | `KafkaTransactionManager` | Supported | Supported | Primary manager for Kafka transactions |
| Narrow transaction manager | `KafkaAwareTransactionManager` | Available | Available | Used in the new container API |
| Kafka EOS mode | Legacy modes per version | Transitioning per release | EOS V2 only since 3.0 | Do not hard-code old modes |
| Producer transaction-id prefix | Required for transactional producer | Supported | Supported | Unique per instance |
| Transaction ID suffix cache | Prior producer cache | Present | Suffix strategy API since 3.2 | Size per concurrency |

**This table only guides migration** and does not replace release notes for your specific version. A Spring Boot 3.4/Spring Kafka 3.3 system should use the 3.2+ API group; Spring Boot 4 projects need updated auto-configuration namespaces and may involve other changes beyond transaction managers.

### 15.1. Do Not Confuse Package Changes with Transaction Deprecation

Spring Boot 3.x example:

```java
org.springframework.boot.autoconfigure.kafka
    .ConcurrentKafkaListenerContainerFactoryConfigurer
```

Spring Boot 4.x moves the configurer to a different namespace. That is a **framework API/package migration**, not a reason to revert to `ChainedKafkaTransactionManager`. Always evaluate the full version matrix across Boot, Spring Kafka, Spring Framework, Spring Data, and Kafka clients.

---

## 16. Order Consistency: Producer-Only vs. Consumer-Initiated

This is an easy point to misread in documentation.

### 16.1. Producer-Only Transaction Synchronization

```text
@Transactional("dbTransactionManager")
  update DB
  KafkaTemplate.send(...)
RETURN
  COMMIT DB
  COMMIT synchronized Kafka transaction
```

Can be called **DB-first**.

### 16.2. Consumer-Initiated Kafka Transaction

```text
Container starts Kafka transaction
  @Transactional("dbTransactionManager")
     update DB
     KafkaTemplate.send(...)
  COMMIT DB
  RETURN from listener
Container commits Kafka transaction (+ offset)
```

Also **DB-first** under the recommended pattern.

### 16.3. Nested Kafka-First in Producer-Only Flows

```text
@Transactional("dbTransactionManager") outer
  update DB
  @Transactional("kafkaTransactionManager") inner
     KafkaTemplate.send(...)
  COMMIT Kafka
COMMIT DB
```

This is **Kafka-first**. It does not automatically apply when a Kafka listener container has already opened an outer Kafka transaction; the scope order differs.

### 16.4. Why Distinguish Them?

Because an exception in the final commit step means different things:

| Order | First Step Succeeded | Second Step Failed | Consequence |
|---|---|---|---|
| DB-first | DB commit | Kafka commit | DB row exists while Kafka event/offset may not be committed |
| Kafka-first | Kafka commit | DB commit | Kafka event exists while DB row is missing |
| Kafka-only | Kafka transaction aborts | No DB transaction | Kafka output/offset in transaction do not commit |

No approach using **two independent local resources** yields perfect atomic commit under every network/power failure. Systems need **business recovery**, not just exception handling.

---

## 17. Testing Migration with Embedded Kafka and Database

### 17.1. Test Dependencies

Gradle example for Spring Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.testcontainers:postgresql'
    testImplementation 'org.testcontainers:kafka'
}
```

In production, Gradle/Spring Boot/Testcontainers versions must be managed via compatible BOMs. This example lists common dependencies, not an already-executed build.

### 17.2. Integration Test Skeleton

Tests need a real/EmbeddedKafka broker and a transactional test DB:

```java
@SpringBootTest
@EmbeddedKafka(
        partitions = 3,
        topics = {
                "orders.events",
                "orders.processed"
        },
        bootstrapServersProperty =
                "spring.kafka.bootstrap-servers")
class KafkaTxMigrationIT {

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void transactionalContainerIsRegistered() {
        var container =
                registry.getListenerContainer("orders-tx-v1");
        assertNotNull(container);
    }

    // Subsequent tests send real events, await via
    // Awaitility/latch, then assert DB + Kafka.
}
```

Reference imports:

```java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.test.context.EmbeddedKafka;
```

This skeleton only confirms the Spring context registered the container. It **does not by itself prove** transaction boundaries. Real broker + DB, fault, and redelivery tests are needed.

### 17.3. Testing DB Success Followed by Kafka Commit Failure

This is the most critical failure case of the consumer-initiated DB-first pattern:

1. Send event `evt-123` to `orders.events`.
2. Let the JDBC service write and commit successfully.
3. Trigger a controlled Kafka transaction commit failure (e.g., broker interruption/fault injection appropriate for the environment).
4. Verify the DB holds the business row while the consumed offset may remain uncommitted.
5. Restore the broker and let the record be redelivered.
6. Confirm the dedup table prevents duplicating the business side effect.
7. Confirm the final Kafka output matches the recovery contract.

Hitting this exact window probabilistically using only `Thread.sleep` can be unreliable. Use fault-injection hooks or Testcontainers/network proxies, asserting against committed offsets, records, and DB state. Do not treat Mockito unit tests of the service as sufficient.

### 17.4. Testing Kafka Producer Fencing

Run two instances deliberately sharing the same `transactionIdPrefix` in a test environment:

- Observe `ProducerFencedException`/transaction failures.
- Confirm the fenced instance stops publishing successfully.
- Switch to unique per-instance prefixes and verify stability.
- Test rolling restarts and graceful shutdowns.

Never run a fencing test against production producer IDs.

### 17.5. Testing Rollback from DB Errors

1. Send an input record.
2. Trigger a DB constraint/connection error in the service.
3. Ensure the exception propagates to the container.
4. Kafka transaction rolls back with no committed Kafka output for the failed attempt.
5. Restore the DB.
6. Record is reprocessed successfully or routed through after-rollback recovery per policy.
7. Zero duplicate DB effects.

### 17.6. Testing Transaction Manager Bean Selection

Define both beans:

```text
dbTransactionManager
kafkaTransactionManager
```

Then test that a `@Transactional("dbTransactionManager")` method actually rolls back a JDBC insert when throwing an exception. This catches missing Spring proxy application, wrong bean qualification, or a data source wired to a different transaction manager.

### 17.7. Testing DLT with a Transactional Container

- Fixed poison message.
- `AfterRollbackProcessor` attempts the exact configured retries.
- Recovery publishes to the DLT per transaction policy.
- Recovered offset commits or source record redelivers per chosen contract.
- If the DLT producer fails, the source record is not silently lost.
- DLT replay has idempotency and does not create an infinite loop.

### 17.8. Testing Kafka-Only EOS

- Input event produces one output record.
- Inject an exception before commit so the transaction aborts.
- A `read_committed` consumer does not see the output from the aborted transaction.
- Successful retry yields one valid output matching the EOS contract.
- Measure record offsets and transaction state, not just application logs.

---

## 18. Alerts and Metrics After Upgrading

### 18.1. Signals to Track

| Metric | Purpose |
|---|---|
| Kafka transaction commit successes/failures | Detect uncommitted publishes/offsets |
| Producer fenced errors | Detect duplicate `transactional.id` or stale producers |
| Transaction abort/rollback count | Detect business or dependency errors |
| Consumer lag/rebalances | Monitor redelivery and catch-up capacity |
| DB deadlocks/rollback/commit latency | Evaluate DB transactional behavior |
| Kafka producer send latency/retries | Detect broker/network problems |
| `NoProducerAvailableException` | Transaction ID suffix cache/producer capacity |
| DLT/recovery success/failure | Ensure poison messages are not lost |
| Business dedup hits | Count redeliveries and producer duplicates by `eventId` |
| Outbox pending age/count | Detect committed DB rows whose events are unpublished |
| Partial-commit incidents | Reconcile missing/mismatched events vs. DB |
| Processing latency p95/p99 | Alert on overly long transactions |

Not all metrics exist out of the box with these names; some require custom Micrometer counters or DB/outbox queries. When configuring monitoring, use low-cardinality labels like service, cluster, transaction outcome, and error category; never attach per-record `eventId` as a metric tag.

### 18.2. Structured Logs

Example:

```json
{
  "event": "KAFKA_TX_COMMIT_FAILED",
  "listenerId": "orders-tx-v1",
  "groupId": "orders-worker",
  "topic": "orders.events",
  "partition": 1,
  "offset": 10998,
  "transactionalIdPrefix": "orders-pod-a-tx-",
  "dbOperation": "ORDER_STATUS_UPDATE",
  "dbOutcome": "COMMITTED",
  "kafkaOutcome": "UNKNOWN_OR_FAILED",
  "reconciliationRequired": true
}
```

This is a **sample log schema**, not a literal framework event. Crucially: if the application does not know whether the DB commit finished, do not log `dbOutcome=COMMITTED` by guesswork. On network failures during commit, the outcome can be unknown and must be verified at the source system.

Never log credentials, producer configs containing SASL passwords, raw PII payloads, or tokens. Transactional IDs and business keys may also be sensitive metadata depending on the system; mask as needed.

### 18.3. High-Priority Alerts

- Producer fencing increases after a rolling deployment.
- Consumer lag grows continuously alongside transaction aborts.
- Kafka commit failure rate increases.
- DB dedup hits spike after pod restarts.
- DLT producer/recoverer fails.
- Outbox pending exceeds SLA.
- Zero records processed successfully despite active source input.
- Transaction ID suffix cache exhausted when concurrency scales.

Never treat zero consumer lag as proof that DB and Kafka are consistent: listeners may be swallowing exceptions or recovery policy may be diverting records straight to the DLT.

---

## 19. Incident Runbook During Migration

### 19.1. Bean Startup Error or Ambiguous Transaction Manager

1. Verify beans named `dbTransactionManager` and `kafkaTransactionManager` exist.
2. Check for duplicate Boot auto-created and custom Kafka managers serving the same purpose.
3. Check that `@Transactional` annotations select the right transaction manager.
4. Verify `KafkaTemplate` and `KafkaTransactionManager` share the same `ProducerFactory`.
5. Confirm `transactionIdPrefix` is configured and `ProducerFactory` is transaction-capable.
6. Do not patch over ambiguity by slapping `@Primary` on a bean without understanding which calls need DB vs. Kafka transactions.

### 19.2. `ProducerFencedException` After Deployment

1. Compare `transactional.id` prefixes across all live pods.
2. Confirm every pod/instance has a unique prefix.
3. Check whether old and new deployments overlap while sharing prefixes.
4. Inspect producer cache sizing, `maxAge`, and broker transaction ID expiration.
5. Never reuse a fenced producer as if its transaction remained valid.
6. Watch offsets/DB dedup after recovery, since redeliveries can occur.

### 19.3. Kafka Commit Failed While Database Committed

1. Extract topic/partition/offset/`eventId` and transaction outcome from logs.
2. Query the DB by `eventId`; verify the dedup marker and business row committed in the same transaction.
3. Inspect Kafka committed offsets/output events rather than guessing from exception messages.
4. When the record redelivers, verify the DB update is idempotent.
5. If Kafka output is missing, run reconciliation/outbox/reprocessing per runbook.
6. Never edit DB/Kafka offsets manually without verifying processed data.

### 19.4. Messages Failing in an Endless Loop

1. Distinguish deserialization, business validation, DB outage, and Kafka commit errors.
2. Check whether the listener uses a transactional container.
3. Inspect `AfterRollbackProcessor`, recovery attempts, and the DLT.
4. Avoid attaching a non-transactional error-swallowing handler inside a transactional container.
5. For persistent poison messages, quarantine/DLT after bounded business attempts.
6. For prolonged infrastructure outages, consider pausing/stopping listeners to avoid a retry storm.

### 19.5. Spike in Duplicate DB Operations After Upgrade

1. Check whether commit order shifted from Kafka-first to DB-first.
2. Inspect pod restarts/rebalances/transaction aborts.
3. Verify dedup uniqueness and that the marker is written inside the same business transaction.
4. Look for self-invocation bypassing DB `@Transactional`.
5. Confirm producer events carry stable `eventId`s instead of generating fresh IDs per retry.
6. For duplicates that cannot be automatically removed, run business reconciliation/compensation.

### 19.6. DLT Not Receiving Records

1. Check whether the transactional path uses `AfterRollbackProcessor` or `DefaultErrorHandler`.
2. Verify DLT producer, serializer, ACLs, topic partition count, and key handling.
3. Check whether DLT publishing is transactional and actually committed.
4. If the recoverer fails, ensure the source record remains redeliverable.
5. If a record's offset was committed with no DLT event, investigate data loss immediately.

---

## 20. Common Mistakes

| Mistake | Consequence | Right Approach |
|---|---|---|
| Thinking `KafkaTransactionManager` is deprecated | Discards the supported mechanism | Distinguish exact classes/APIs |
| Seeing `ChainedKafkaTransactionManager` deprecated and swapping 1-for-1 | Loses DB transaction boundary | Move DB `@Transactional` into service |
| Treating chaining like XA transactions | False confidence in DB/Kafka atomicity | Partial-commit design/idempotency |
| Ignoring old commit order | Migration behaves differently on failure | Diagram before/after order |
| Passing DB manager to `setKafkaAwareTransactionManager` | Wrong type/semantics | Use only a `KafkaAware` manager |
| Keeping `setTransactionManager` deprecated since 3.2 | For-removal technical debt | Use the new setter |
| Omitting `transaction-id-prefix` | Kafka producer is not properly transactional | Configure producer factory explicitly |
| All pods share the same prefix | Producer fencing | Unique prefix per instance |
| Two `KafkaTemplate`s use different producer factories | Not in the same Kafka transaction | Unify factory |
| `@Transactional` without qualifier when multiple managers exist | Ambiguity or wrong transaction opened | Specify bean name explicitly |
| Self-invocation via `this.method()` | May bypass AOP proxy | Separate service bean/proxy |
| Catching exceptions and returning success | Container commits despite business failure | Propagate appropriate exceptions |
| Believing DB commit also commits Kafka offsets | Kafka offsets reside in another resource | Kafka transactions + redelivery policy |
| Believing DB rollback cancels an already-committed Kafka TX | Cannot roll back a committed resource | Reconcile/compensate |
| Treating `read_committed` as DB consistency | Affects only reading transactional Kafka records | Dedicated DB transaction/idempotency |
| Using `KafkaTemplate.executeInTransaction` to join outer TX | Opens an independent inner TX | Understand method scope |
| Using retry topics like a non-TX listener | Ordering/transaction behavior changes | Check transactional container support |
| Using error-swallowing `DefaultErrorHandler` in TX container | Risks skipping rollback | `AfterRollbackProcessor`/propagate |
| Changing Kafka group ID to "fix offsets" | Can replay/drop batches of events | Manage offsets intentionally |
| Raising concurrency without sizing producer cache | Producer exhaustion | Capacity planning |
| Testing only the happy path | Misses partial commits/redeliveries | Fault-injection integration tests |
| Rolling back code without checking data | Can duplicate/lose business effects | Reconcile before/after deploy |

---

## 21. Hands-On Exercises

### Exercise 1 — Identify Deprecations

Read the Javadocs of `ChainedKafkaTransactionManager`, `ChainedTransactionManager`, and `ContainerProperties.setTransactionManager`. Record the version each was deprecated and its replacement. Explain why `KafkaTransactionManager` is not among those to remove.

### Exercise 2 — Legacy Commit Order

Given chain `(dbTx, kafkaTx)`, determine begin/commit order. Suppose Kafka commits and DB fails to commit; sketch the remaining state and reconciliation plan. Then reverse the chain order and repeat.

### Exercise 3 — API Migration

Migrate a custom listener container factory from `setTransactionManager(chainedTx)` to `setKafkaAwareTransactionManager(kafkaTx)`, moving the DB transaction into a dedicated service annotated with `@Transactional("dbTransactionManager")`. Confirm the listener method still throws when the service fails.

### Exercise 4 — Kafka-Only Transaction

Create an app reading `orders.input` and publishing to `orders.output` using a transactional container. Verify output records from an aborted transaction never appear to a `read_committed` consumer and the input is redelivered.

### Exercise 5 — DB-First Failure

Create a DB unique marker keyed by `eventId`. Simulate a successful DB commit followed by a failed Kafka commit; redeliver the event multiple times and prove the business side effect happens only once.

### Exercise 6 — Producer-Only DB + Kafka

Create a `@Transactional("dbTransactionManager")` method writing an invoice and publishing to Kafka. Describe DB state when the Kafka commit fails and implement outbox/reconciliation to handle it.

### Exercise 7 — Kafka-First Nested Transaction

Split two Spring beans with an inner Kafka transaction and outer DB transaction. Simulate a DB commit failure after Kafka commits; explain why the event becomes visible while the DB still lacks the invoice.

### Exercise 8 — Self-Invocation

Inside one service, invoke a `@Transactional` method via `this.method()` and run a JDBC rollback test. Split across two Spring beans/proxies and compare behaviors.

### Exercise 9 — Per-Pod Transaction ID

Run two instances sharing the same `transactionIdPrefix` in a test environment and observe producer fencing. Then assign unique prefixes and verify stable transactional publishing.

### Exercise 10 — AfterRollbackProcessor and DLT

Configure a transactional listener with a poison message. Verify retries/recovery and successful DLT publishing, then simulate DLT failure. Prove source offsets are never silently committed when failed records are not stored per policy.

### Exercise 11 — Sizing Producer Cache

A topic has six partitions, three consumer threads, and nested producer transactions. Propose a cache size/suffix strategy based on real concurrency, test exhaustion, and alert on `NoProducerAvailableException`.

### Exercise 12 — Migration ADR

Write an Architecture Decision Record covering: current transactions, rationale for dropping the chained manager, before/after commit order, business idempotency, outbox choice, partial-commit tests, deployment/rollback plan, and owners responsible for reconciliation.

---

## 22. References

- [Spring Kafka — Transactions (reference 3.3)](https://docs.spring.io/spring-kafka/reference/3.3/kafka/transactions.html): `KafkaTransactionManager`, transaction synchronization, consumer-initiated transactions, and chaining deprecation.
- [Spring Kafka — ChainedKafkaTransactionManager Javadoc 3.3](https://docs.spring.io/spring-kafka/docs/3.3.x/api/org/springframework/kafka/transaction/ChainedKafkaTransactionManager.html): deprecated class and inheritance hierarchy.
- [Spring Data — ChainedTransactionManager Javadoc](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/transaction/ChainedTransactionManager.html): begin/commit order, partial commits, and `HeuristicCompletionException`.
- [Spring Kafka — ContainerProperties Javadoc 3.3](https://docs.spring.io/spring-kafka/docs/3.3.1/api/org/springframework/kafka/listener/ContainerProperties.html): old setter deprecated since 3.2 and new `setKafkaAwareTransactionManager` setter.
- [Spring Kafka — KafkaTransactionManager Javadoc 3.3](https://docs.spring.io/spring-kafka/docs/3.3.x/api/org/springframework/kafka/transaction/KafkaTransactionManager.html): transaction manager for `ProducerFactory`.
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/3.3/kafka/exactly-once.html): Kafka EOS scope and container offset semantics.
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/3.3/kafka/annotation-error-handling.html): `AfterRollbackProcessor` and error recovery.
- [Spring Kafka — Tips, Tricks and Examples](https://docs.spring.io/spring-kafka/reference/3.3/tips.html): examples of transactions with other transaction managers.
- [Spring Kafka — Change History](https://docs.spring.io/spring-kafka/reference/appendix/change-history.html): milestones such as chaining/container property deprecations.
- [Spring Boot 3.4 — Kafka Support](https://docs.spring.io/spring-boot/3.4/reference/messaging/kafka.html): `spring.kafka.*`, transactional producers, and auto-configuration.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): `@Transactional`, proxies/self-invocation, and transaction managers.
- [Apache Kafka — Transactions](https://kafka.apache.org/documentation/): transactional producers, `transactional.id`, consumer isolation, and offset semantics.

## 23. Summary

Legacy transaction manager deprecation in Spring Kafka is not merely a class-name warning. **`ChainedKafkaTransactionManager` (deprecated since 2.7)** and **`ContainerProperties.setTransactionManager(...)` (deprecated since 3.2)** mark two related yet distinct shifts: dropping partial-commit-prone resource chaining and adopting a clearer Kafka-aware container transaction manager interface.

For consumer-initiated flows, the replacement guided by Spring Kafka documentation is **`KafkaTransactionManager` on the listener container + `@Transactional` with a DB transaction manager at the service layer**, not a chain pretending to give atomicity between Kafka and the database. For producer-only flows, transaction synchronization or nested methods can choose commit order, yet **both DB-first and Kafka-first have consistency windows that must be handled**.

A successful migration must therefore prove three things: **APIs no longer rely on old deprecations**, **commits/rollbacks/retries behave properly on broker and database**, and **business side effects are neither duplicated nor lost under partial failures**. The core mechanisms are unique transaction IDs, idempotency/dedup, outbox where needed, after-rollback recovery, observability, and fault-injection tests—not merely code compiling without warnings.
