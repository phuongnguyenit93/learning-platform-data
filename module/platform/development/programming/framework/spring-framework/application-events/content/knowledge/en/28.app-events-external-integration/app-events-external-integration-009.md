# Separating Domain Events and Integration Events in Spring Framework

## 1. The problem: one business change, two kinds of contracts

In Domain-Driven Design (DDD), a **domain event** expresses a fact meaningful to the business model: `OrderPaid`, `InvoiceIssued`, `StockReserved`. Meanwhile, an **integration event** is a message designed for **external applications/services** to consume over a message broker, webhook, API, or another integration system.

Both event types may talk about the same fact, yet carry different responsibilities:

- **Domain event** serves the domain model and internal modules; it reflects domain terminology, invariants, and lifecycle. It can change when the domain is refactored and is not inherently a public API.
- **Integration event** is a **communication contract between independently deployed parties**. It must have an explicit schema, version, metadata, access controls, compatibility rules, serialization, routing, and delivery policies.

If you publish **raw domain event objects** directly to Kafka/RabbitMQ and let outsiders depend on Java class names and every internal field, you unintentionally turn your domain structure into a public contract. Renaming `OrderPaid` to `PaymentCaptured`, splitting an aggregate, or changing an ID type internally can break numerous external consumers.

Conversely, forcing the domain to always emit JSON messages matching a broker schema couples the domain model to infrastructure and makes it hard to evolve due to non-business constraints.

**Central principle:** the domain states “what happened”; the integration boundary decides “what is allowed/sufficient to publish externally, under which contract, and via which durable mechanism”.

```text
                      DOMAIN / APPLICATION
Command: pay order
        |
        v
Order aggregate / domain service
        |
        +-- validates invariant, changes state
        +-- records OrderPaid (domain event)
                    |
                    v
            Application boundary
                    |
                    +-- internal listener: update internal read model
                    |
                    +-- Domain -> Integration mapper
                               |
                               +-- allowlist fields
                               +-- public event type + schema version
                               +-- stable event ID / correlation
                               v
                         PaymentConfirmedV1
                               |
                               v
                     Transactional outbox
                               |
                        database COMMIT
                               |
                               v
                          Relay / broker
                               |
                               v
                       External consumers
```

In this example, the domain event is **never seen by the broker directly**; the integration event is the output of a dedicated mapping layer.

## 2. Comparing domain events and integration events

| Perspective | Domain event | Integration event |
| --- | --- | --- |
| Consumers | Aggregates, application services, internal modules | Systems/teams outside the boundary |
| Purpose | Express a business fact inside a bounded context | Publish changes/contracts for other parties to react to |
| Language | Ubiquitous language of the domain | Language agreed between publisher and consumers |
| Ownership | Owned by the domain/bounded context | Provider owns schema and compatibility policy |
| Stability | Can change during domain model refactoring | Requires versioning and deprecation management |
| Form | Java record/class, domain abstraction, possibly in-memory | JSON/Avro/Protobuf/message envelope per contract |
| Data | Detailed enough for internal reactions, still kept secure | Minimal data permitted to be shared, versioned |
| Transport | Spring Application Events or domain event collections | Broker, queue, webhook, integration API |
| Timing | May be recorded during the transaction | Usually distributed only once durable changes commit |
| Reliability | No built-in durability by default | Requires retries, delivery, outbox, deduplication |
| Consumer autonomy | Coupling within the same product/process may be acceptable | Consumers deploy independently without relying on JVM internals |
| Testing | Domain unit tests and internal module integration | Contract, schema compatibility, and end-to-end integration |

These two types do not have to be two separate classes in every tiny system. However, **the separation of responsibilities must be clear**. Whenever an event crosses a bounded context or goes out to a broker/public integration, creating a separate contract gives much better control over evolution and security.

### Two payload examples

Internal domain event:

```java
record OrderPaid(
        String eventId,
        String orderId,
        long amountCents,
        String currency,
        String internalRiskCode) {}
```

Published integration event:

```java
record PaymentConfirmedV1(
        String eventId,
        String orderId,
        long amountCents,
        String currency,
        int schemaVersion) {}
```

The `internalRiskCode` field is internal technical/business data that does not need to be shared externally. The integration event has a stable schema version and contains only the fields consumers need per contract. These two snippets illustrate record types only; the complete Maven project is in section 7.

**Note:** `orderId`, `eventId`, and `internalRiskCode` can all be sensitive depending on the data domain. Opaque IDs do not automatically make data anonymous. Never send an entire entity/source DTO so “consumers can pick whatever fields they want”.

## 3. When is a domain event created?

A domain event must arise from a **valid domain change**, such as `Order.pay()` after verifying the order is unpaid, the amount is valid, and the payment state has been accepted. On an aggregate root, you can accumulate pending events:

```java
// Aggregate excerpt, not a complete file.
private final List<Object> pendingEvents = new ArrayList<>();

void pay(Payment payment) {
    if (paid) throw new IllegalStateException("Order already paid");

    paid = true;
    pendingEvents.add(
            new OrderPaid(eventId, id, payment.amountCents(),
                    payment.currency(), internalRiskCode));
}

List<Object> pendingEvents() {
    return List.copyOf(pendingEvents);
}
```

A domain can collect multiple events for one command. Calling `registerEvent` or appending to a list **does not mean** the events have been published to Spring or a broker. The application service or repository boundary is responsible for pulling those events and dispatching them once state is valid.

Spring Data Commons offers `@DomainEvents`, `@AfterDomainEventPublication`, and `AbstractAggregateRoot` to help publish events when using appropriate repository operations. However, those mechanisms **do not automatically turn events into durable broker messages**, and the “after domain event publication” callback does not mean the transaction committed or all listeners finished processing.

Some domain events are useful only within one bounded context, such as “pricing rule recomputed”. Do not publish every event merely because it exists. External consumers should see a **deliberately curated** set.

## 4. Integration events are external contracts, not entity copies

When a message crosses the application boundary, you must decide:

1. **Event meaning:** does “OrderPaid” mean internal payment confirmation, funds captured successfully, or merely charge request sent? An ambiguously named event causes subtle integration bugs.
2. **Boundary:** what fact do external consumers need to know? If they only need invoice creation, you can publish `PaymentConfirmedV1` instead of overly detailed order domain data.
3. **Payload:** only fields explicitly permitted; include a snapshot to preserve historical accuracy when needed.
4. **Event identity:** an immutable ID for the business fact, not regenerated on each retry.
5. **Schema/version:** data types, required/optional fields, enums, null semantics, timestamp format, currency, and defaults.
6. **Envelope:** event ID, type, version, `occurredAt`, producer, correlation/causation IDs where applicable.
7. **Delivery policy:** at-least-once, ack, retry, DLQ, ordering, retention, replay.
8. **Security:** producer/consumer authentication, topic/queue permissions, encryption, data classification.
9. **Lifecycle:** which consumers use it, deprecation schedule, migration, and parallel v1/v2 support.

Example of an **illustrative** JSON integration message:

```json
{
  "eventId": "evt-100",
  "type": "payment.confirmed.v1",
  "schemaVersion": 1,
  "occurredAt": "2026-11-11T00:00:00Z",
  "aggregateId": "O-100",
  "payload": {
    "orderId": "O-100",
    "amountMinor": 1500,
    "currency": "USD"
  }
}
```

This is an **illustrative design contract**, not a format automatically generated by Spring. The `amountMinor` field uses the smallest currency unit under a consistent currency model. For currencies with different numbers of decimal places, define the representation explicitly instead of assuming “cents” for every currency.

You can use ISO-8601 UTC for `occurredAt` and an ID truly independent of email addresses/PII. If a message is replayed, keep `eventId` and `occurredAt` unchanged; you can add `publishedAt` when each forwarding attempt needs separate tracking, but never overwrite the business fact timestamp with retry time.

## 5. The mapping layer (mapper / anti-corruption layer)

An integration adapter receives a domain event, applies an **allowlist mapping**, builds an integration DTO, and writes to an outbox or calls a messaging gateway.

```java
// Illustrative excerpt, DTOs already defined.
PaymentConfirmedV1 toIntegrationEvent(OrderPaid domain) {
    return new PaymentConfirmedV1(
            domain.eventId(),
            domain.orderId(),
            domain.amountCents(),
            domain.currency(),
            1);
}
```

Mapping should perform the following:

- **Strip internal data:** `internalRiskCode`, DB entity relations, JPA lazy-loaded graphs, internal notes, and secrets.
- **Stabilize field names:** externally use `amountMinor` or standard schema names, never forcing consumers onto entity property names.
- **Normalize types:** `Instant` → RFC 3339/ISO-8601, money → minor units + currency, IDs → stable strings.
- **Decouple event types:** internal domain names can change; public `payment.confirmed.v1` stays intact while semantics stay unchanged.
- **Preserve correlation:** event ID, aggregate ID, aggregate version/correlation ID where the contract requires them.
- **Audit authorization:** do not rely on “it serialized to JSON” to conclude it is safe.
- **Never turn a technical error into a business fact:** the bridge must never emit `PaymentConfirmed` if the domain has not confirmed payment.

Mappers should not perform network I/O or depend on data mutating outside the transaction when a point-in-time snapshot is required. If additional data for the integration contract must be looked up, do so at a boundary with clear consistency and authorization; avoid consumers receiving a snapshot mixed from multiple versions.

## 6. Event translation timing and transaction issues

### 6.1. Sending directly before commit: published-but-rolled-back risk

```text
BEGIN TRANSACTION
  update orders paid=true
  publishEvent(OrderPaid)
    -> listener calls KafkaTemplate.send(...) / HTTP POST
  ROLLBACK
```

Once a side effect leaves the process, a database rollback cannot recall the message or HTTP request. External consumers see “paid” while the order in the database was never committed.

### 6.2. Sending after commit: right timing, still has an event-loss gap

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` ensures the listener runs only after a successful commit. However:

- After commit and before the listener executes, the process can crash.
- A failed post-commit callback does **not** roll back an already-committed transaction.
- Default Spring Application Events are not a durable queue.
- With imperative transactions, callbacks attach to the thread-bound transaction; events outside a transaction do not trigger `@TransactionalEventListener` by default unless fallback is enabled.
- If a post-commit listener wants to write to the DB, it needs a new transaction design; old resources may still be bound without a subsequent commit cycle.

**Conclusion:** after-commit is a timing policy, not a durability guarantee.

### 6.3. Transactional outbox: writing publication intent in the same transaction

A common mechanism to tie DB changes and integration events together:

```text
BEGIN TRANSACTION
   update/insert orders
   insert into integration_outbox(
       event_id, type, payload, version, status, created_at)
COMMIT
               |
               v
Outbox relay (reads committed rows)
               |
               v
Broker publish with eventId + routing
               |
               v
Mark delivered after broker acknowledgement
```

The outbox row and order state commit or roll back **atomically in the same database transaction**. The relay reads the row again after a restart on crash. However, if the broker accepts the message and the relay crashes before marking `DELIVERED`, the relay can resend. Thus **at-least-once + idempotent consumers** is a safer assumption than “exactly once” for external side effects.

Safe architectural choices:

- Domain code creates domain events or records pending events.
- Application/integration boundary maps to an integration event.
- **Write the outbox in the same transaction** as state; do not wait for after-commit to insert into the outbox when atomicity is needed.
- Relay publishes messages *after commit*, with retries/backoff, stable keys, and monitoring.
- Consumers deduplicate `eventId` and apply side effects idempotently.

When using a Spring `@EventListener` to write to the outbox, keep the bridge listener **synchronous and participating in the publisher’s transaction**; do not attach `@Async` or `@TransactionalEventListener(AFTER_COMMIT)` to the outbox insert that must be atomic. The runnable example below demonstrates this approach.

## 7. Java 17 Maven example: domain event → integration event → outbox

The project uses **Spring Framework 6.2.8**, Spring JDBC, H2 2.3.232, and Java 17. It runs with Maven, without needing Spring Boot or a real broker.

Scenario:

1. `CheckoutService` validates a positive amount, inserts an order, and publishes the **domain event `OrderPaid`** inside a transaction.
2. `DomainToIntegrationBridge` is a synchronous `@EventListener` that maps `OrderPaid` to `PaymentConfirmedV1` and writes the outbox **in the same transaction**. The internal `internalRiskCode` field is omitted from the outbox.
3. Commit succeeds: order and outbox coexist.
4. `OutboxRelay` runs **after commit** as called by `main`, reads the outbox, uses a fake broker to print the message, and marks it delivered.
5. Running the relay a second time does not resend an event already marked delivered.
6. A negative-amount command is rejected before starting a transaction, emitting no domain event.
7. A simulated bridge failure rolls back both the order and the outbox, illustrating atomicity.

> This is an example of module boundaries and transactions, **not** a production Kafka publisher. The simulated relay lacks locking, leases, retries, and real broker acks. Do not use this demo to claim exactly-once delivery.

### 7.1. Structure

```text
separate-domain-integration-events/
├── pom.xml
└── src/main/java/demo/SeparateEventsDemo.java
```

### 7.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>separate-domain-integration-events</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.SeparateEventsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. src/main/java/demo/SeparateEventsDemo.java

```java
package demo;

import java.util.List;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public class SeparateEventsDemo {

    // Internal event: contains internalRiskCode, must not be serialized to broker.
    public record OrderPaid(
            String eventId,
            String orderId,
            long amountCents,
            String currency,
            String internalRiskCode) {}

    // External contract: only fields permitted to be published.
    public record PaymentConfirmedV1(
            String eventId,
            String orderId,
            long amountCents,
            String currency,
            int schemaVersion) {}

    public static final class CheckoutService {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate transactions;
        private final ApplicationEventPublisher publisher;

        public CheckoutService(
                JdbcTemplate jdbc,
                TransactionTemplate transactions,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.transactions = transactions;
            this.publisher = publisher;
        }

        public void pay(
                String eventId,
                String orderId,
                long amountCents,
                String currency,
                String internalRiskCode) {

            if (amountCents <= 0) {
                throw new IllegalArgumentException(
                        "amount must be positive");
            }

            transactions.executeWithoutResult(status -> {
                jdbc.update(
                        "insert into orders " +
                        "(order_id, amount_cents, currency, internal_risk_code)" +
                        " values (?, ?, ?, ?)",
                        orderId, amountCents, currency, internalRiskCode);

                System.out.println("domain: paid " + orderId);

                // Internal event, published while the transaction is active.
                publisher.publishEvent(new OrderPaid(
                        eventId, orderId, amountCents,
                        currency, internalRiskCode));
            });

            System.out.println("service: committed " + orderId);
        }
    }

    public static final class DomainToIntegrationBridge {
        private final JdbcTemplate jdbc;

        public DomainToIntegrationBridge(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @EventListener
        public void onPaid(OrderPaid domain) {

            // Simulate adapter failure to observe atomic rollback.
            if ("evt-fail".equals(domain.eventId())) {
                throw new IllegalStateException("outbox unavailable");
            }

            PaymentConfirmedV1 external = new PaymentConfirmedV1(
                    domain.eventId(),
                    domain.orderId(),
                    domain.amountCents(),
                    domain.currency(),
                    1);

            // Write outbox synchronously inside CheckoutService's transaction.
            // Do not store internalRiskCode in the external contract.
            jdbc.update(
                    "insert into integration_outbox " +
                    "(event_id, event_type, order_id, amount_cents," +
                    " currency, schema_version, delivered)" +
                    " values (?, ?, ?, ?, ?, ?, false)",
                    external.eventId(),
                    "payment.confirmed.v1",
                    external.orderId(),
                    external.amountCents(),
                    external.currency(),
                    external.schemaVersion());

            System.out.println("bridge: staged " + external.eventId());
        }
    }

    public static final class FakeBroker {
        public void send(PaymentConfirmedV1 event) {
            System.out.println(
                    "broker: payment.confirmed.v1 event="
                            + event.eventId()
                            + " amount=" + event.amountCents()
                            + " " + event.currency());
        }
    }

    public static final class OutboxRelay {
        private final JdbcTemplate jdbc;
        private final FakeBroker broker;

        public OutboxRelay(JdbcTemplate jdbc, FakeBroker broker) {
            this.jdbc = jdbc;
            this.broker = broker;
        }

        public void flushOnce() {
            List<PaymentConfirmedV1> pending = jdbc.query(
                    "select event_id, order_id, amount_cents," +
                    " currency, schema_version" +
                    " from integration_outbox" +
                    " where delivered = false order by event_id",
                    (rs, index) -> new PaymentConfirmedV1(
                            rs.getString("event_id"),
                            rs.getString("order_id"),
                            rs.getLong("amount_cents"),
                            rs.getString("currency"),
                            rs.getInt("schema_version")));

            System.out.println("relay: pending=" + pending.size());

            for (PaymentConfirmedV1 event : pending) {
                // In real systems, wait for a genuine broker acknowledgement.
                broker.send(event);
                jdbc.update(
                        "update integration_outbox set delivered = true" +
                        " where event_id = ? and delivered = false",
                        event.eventId());
                System.out.println("relay: delivered " + event.eventId());
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:event_separation;DB_CLOSE_DELAY=-1",
                    "sa", "");
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        TransactionTemplate transactionTemplate(
                PlatformTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean
        CheckoutService checkoutService(
                JdbcTemplate jdbc,
                TransactionTemplate transactions,
                ApplicationEventPublisher publisher) {
            return new CheckoutService(jdbc, transactions, publisher);
        }

        @Bean
        DomainToIntegrationBridge bridge(JdbcTemplate jdbc) {
            return new DomainToIntegrationBridge(jdbc);
        }

        @Bean
        FakeBroker fakeBroker() {
            return new FakeBroker();
        }

        @Bean
        OutboxRelay outboxRelay(
                JdbcTemplate jdbc, FakeBroker broker) {
            return new OutboxRelay(jdbc, broker);
        }
    }

    private static int count(JdbcTemplate jdbc, String table) {
        // table is an internal constant passed by main, NOT user input.
        Integer value = jdbc.queryForObject(
                "select count(*) from " + table, Integer.class);
        return value == null ? 0 : value;
    }

    private static int pending(JdbcTemplate jdbc) {
        Integer value = jdbc.queryForObject(
                "select count(*) from integration_outbox" +
                " where delivered = false",
                Integer.class);
        return value == null ? 0 : value;
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute(
                    "create table orders (" +
                    "order_id varchar(64) primary key," +
                    "amount_cents bigint not null," +
                    "currency varchar(3) not null," +
                    "internal_risk_code varchar(64) not null)");
            jdbc.execute(
                    "create table integration_outbox (" +
                    "event_id varchar(64) primary key," +
                    "event_type varchar(64) not null," +
                    "order_id varchar(64) not null," +
                    "amount_cents bigint not null," +
                    "currency varchar(3) not null," +
                    "schema_version int not null," +
                    "delivered boolean not null)");

            CheckoutService service =
                    context.getBean(CheckoutService.class);
            OutboxRelay relay =
                    context.getBean(OutboxRelay.class);

            System.out.println("=== SUCCESS ===");
            service.pay(
                    "evt-100", "O-100", 1500, "USD", "INTERNAL-RISK-A");
            System.out.println(
                    "db: orders=" + count(jdbc, "orders") +
                    " pending=" + pending(jdbc));

            System.out.println("=== RELAY ===");
            relay.flushOnce();
            System.out.println("db: pending=" + pending(jdbc));

            System.out.println("=== REPEATED RELAY ===");
            relay.flushOnce();

            System.out.println("=== INVALID COMMAND ===");
            try {
                service.pay(
                        "evt-invalid", "O-invalid", -1, "USD", "RISK-X");
            } catch (IllegalArgumentException ex) {
                System.out.println("main: invalid amount rejected");
            }

            System.out.println("=== BRIDGE FAILURE ===");
            try {
                service.pay(
                        "evt-fail", "O-fail", 500, "USD", "RISK-Y");
            } catch (IllegalStateException ex) {
                System.out.println("main: transaction rolled back");
            }
            System.out.println(
                    "db: orders=" + count(jdbc, "orders") +
                    " pending=" + pending(jdbc));
        }
    }
}
```

### 7.4. How to run

Requires JDK 17+ and Maven. From the directory containing `pom.xml`:

```bash
mvn -q clean compile exec:java
```

Output produced by the `System.out.println` statements in the program (excluding Maven logs):

```text
=== SUCCESS ===
domain: paid O-100
bridge: staged evt-100
service: committed O-100
db: orders=1 pending=1
=== RELAY ===
relay: pending=1
broker: payment.confirmed.v1 event=evt-100 amount=1500 USD
relay: delivered evt-100
db: pending=0
=== REPEATED RELAY ===
relay: pending=0
=== INVALID COMMAND ===
main: invalid amount rejected
=== BRIDGE FAILURE ===
domain: paid O-fail
main: transaction rolled back
db: orders=1 pending=0
```

### 7.5. Consistency analysis

**In the SUCCESS branch:**

- `CheckoutService` INSERTs into `orders` within a transaction, creates `OrderPaid` including `internalRiskCode`, and calls `publishEvent`.
- Spring calls `DomainToIntegrationBridge.onPaid(...)` **synchronously on the publisher thread**. The bridge’s `JdbcTemplate` uses the same `DataSourceTransactionManager`/transaction connection, so the outbox row is inserted in the same transaction.
- The bridge maps separately to `PaymentConfirmedV1`, omitting `internalRiskCode` from the integration outbox table. The (simulated) broker never sees the internal field either.
- Only after `TransactionTemplate` finishes committing does `main` call the relay. The outbox row with `delivered=false` is already durable in the running H2 DB.
- The fake broker prints the message and the relay marks it delivered. The second relay run sees no `pending` rows.

**In the INVALID COMMAND branch:** the negative-amount command is rejected before any transaction begins, so there is no INSERT, no event published, and no outbox row created.

**In the BRIDGE FAILURE branch:** the order INSERT ran but had not committed; the simulated bridge threw an unchecked exception inside `publishEvent`. `TransactionTemplate` rolled back the order INSERT as well. Because no event was committed, no new outbox row exists. The final order count stays 1.

**Limitations**: the fake broker returns no real acknowledgment, the relay does not claim rows via leases/locks, there are no retries/backoff, no separate transaction when marking delivered, and no multi-instance coordination. Printing `broker: ...` does not prove durable delivery. Production must use a proper broker client, handle acks/errors, and implement idempotent consumers.

**Data risk:** the internal risk code stays in the database/domain event and out of the integration contract. Even so, internal domain events can still be logged/snapshotted if code misbehaves; internal does not mean exempt from data classification.

## 8. Why not map inside the domain aggregate?

Anti-pattern:

```java
// Illustrative anti-pattern: domain knows Kafka, JSON, and public version.
void pay(Payment p) {
    this.paid = true;
    kafkaTemplate.send(
            "payment.confirmed.v1",
            serializeToJson(new PaymentConfirmedV1(...)));
}
```

Now the domain depends on Kafka, a serializer, a routing target, and an external schema. Switching from Kafka to AMQP or from JSON to Avro forces edits to business code. Changing a public schema can accidentally perturb domain invariants.

Better design:

```text
Domain / Aggregate
    └── records OrderPaid

Application / Integration Boundary
    ├── translates OrderPaid -> PaymentConfirmedV1
    ├── decides which events qualify for externalization
    └── persists outbox / publishes via messaging port

Infrastructure adapter
    ├── serializes contract
    ├── resolves topic/routing key
    ├── sends + ack/retry
    └── metrics/logging/DLQ
```

In a Ports and Adapters architecture, the domain/application layer can define an `IntegrationEventPort` or `OutboxWriter` interface as needed, implemented by infrastructure. Domain events do not have to know Spring at all. `ApplicationEventPublisher` can be invoked in the application service or an adapter, while aggregates gather pure-Java pending domain events.

## 9. Choosing which events to externalize

**Not every domain event should have an integration event.**

A bounded context might emit:

- `OrderItemRepriced`: internal line-item pricing update, no need to expose publicly.
- `OrderReadyForPayment`: internal state, still subject to change.
- `OrderPaid`: accounting consumers need to know once payment is confirmed.
- `FraudRuleTriggered`: contains sensitive internal info; do not publish to a shared topic.
- `OrderCancellationApproved`: external fulfillment service needs to know to stop shipping.

An integration event is sometimes a projection of **multiple** domain facts or an aggregated business milestone, such as `OrderFinanciallySettledV1` emitted only after all settlement conditions finish. Never force a 1:1 mapping everywhere. Conversely, one domain event can lead to multiple distinct integration contracts for consumers with different purposes and permissions—for instance, a minimal public stream and a restricted internal stream.

Place externalization decisions at the boundary and review them like public APIs. Do not serialize the entire domain-event hierarchy and let every consumer pick whatever it wants, as that widens coupling and sensitive data exposure.

### Event vs. command

`OrderPaid` is a **fact**: payment has been confirmed. `SendReceipt` is a **command**: a request telling a service to send a receipt. Never name a command `ReceiptSent` before sending succeeds, and never name a fact `PayOrder` to confuse consumers. A workflow can receive `PaymentConfirmedV1` and issue a command to send a receipt, while events should describe only what actually happened.

### Event vs. CDC

Change Data Capture (CDC) from a database can emit row changes, such as a `paid` column flipping `false→true`. However, **a row change is not inherently a domain event**: it often lacks business cause, public semantics, multi-table transaction boundaries, and filtering of what should or shouldn’t be published. CDC can be used to **relay outbox rows**—in which case the outbox schema is the integration contract and CDC is the transport mechanism—instead of exposing raw table changes directly as an API.

## 10. Versioning integration events and schema evolution

The domain model can evolve quickly, while integration contracts must avoid breaking older consumers.

For example, `PaymentConfirmedV1` has:

```json
{
  "eventId": "evt-100",
  "type": "payment.confirmed.v1",
  "schemaVersion": 1,
  "payload": {
    "orderId": "O-100",
    "amountMinor": 1500,
    "currency": "USD"
  }
}
```

When you need to add `paymentMethodCategory` for a new consumer, you can add an **optional field with a clear default** if both the schema registry and consumers support it. When you need to **change the meaning** of `amountMinor` or replace one fact with another, you generally must create `payment.confirmed.v2` with a migration plan.

| Change | Usually safe? | Condition |
| --- | --- | --- |
| Add optional field with default | Usually yes | Consumers ignore unknown fields; format/registry allows it |
| Remove a required field | Usually breaking | Older consumers depend on it |
| Change `amountMinor` from number to string | Breaking for many serializers | Requires compatible version/adapter |
| Change `OrderPaid` meaning from “charged” to “settled” | Semantically breaking | Requires new event type/version |
| Add enum value | Can be breaking | Consumers that do not handle unknown enums |
| Rename routing topic | Can be breaking | Consumers/broker ACLs/subscriptions must migrate |
| Add PII to payload | Requires security/privacy review | Not merely a technical schema change |
| Change `eventId` on each retry | Breaks idempotency contract | Keep ID stable for the same business fact |

There is no rule saying “just bumping `schemaVersion` makes it safe”. Beyond syntax compatibility lies **semantic compatibility**: the same field with altered meaning is a breaking change. When using Avro/Protobuf/JSON Schema, define backward/forward/full compatibility strategies, schema registry versions, contracts, and tests.

An upgrade plan might include:

1. Define contract v2 and rationale.
2. Ensure consumers accept v2 or deploy dual consumption.
3. Switch publisher to v2, or dual-publish with stable event identity and explicit consumer deduplication.
4. Monitor lag/usage and announce the v1 sunset date.
5. Retire v1 once consumers have migrated and retention/replay policies allow.

**Avoid blind dual publishing:** two messages (v1 and v2) can represent the same fact. A consumer reading both topics must recognize them as **one** business occurrence when computing side effects.

## 11. Envelopes, routing, and ordering

An integration envelope typically includes metadata:

| Field | Purpose |
| --- | --- |
| `eventId` | Idempotency/dedup, kept stable across retries |
| `type` | Public event type, e.g., `payment.confirmed.v1` |
| `schemaVersion` | Reading payload per contract |
| `occurredAt` | When the business fact occurred |
| `publishedAt` | When actually sent over transport (may differ on retry) |
| `aggregateId` | Supports routing/ordering; may still be sensitive |
| `aggregateVersion` | Establishes change order within an aggregate where needed |
| `correlationId` | Links command/request and processing steps |
| `causationId` | Event/command that caused the current event |
| `source` | Producer service/bounded context |
| `tenantId` | Used only when needed and permitted; enforces authorization |

For Kafka, the key can be the aggregate ID so changes for the same aggregate land on the same partition and preserve **per-partition order** under specific producer/broker settings. That does not guarantee global order, and consumer retries/DLQs can let a later event overtake an earlier one. If ordering is a business invariant, design relay, partitioning, aggregate versions, and consumer reordering/idempotency together.

The order **created in the domain** can also differ from the order **confirmed by the broker** when relays run concurrently. Do not assume an outbox table with `ORDER BY created_at` preserves order across multiple instances if workers claim rows competitively; you need a per-aggregate claim/serialization strategy when required.

## 12. Failure modes and remediation

| Failure | Consequence | Strategy |
| --- | --- | --- |
| Domain operation rejected | No business fact to publish | Emit no success event |
| Database state insert fails | Transaction rolls back | No committed outbox row created |
| Mapper/outbox insert fails in transaction | State + outbox roll back together | Log safely, retry command if valid |
| Commit succeeds, process dies before relay runs | Outbox row remains | Relay resumes after restart |
| Broker receives event but relay hasn’t marked delivered | May publish duplicates | Stable event ID + idempotent consumer |
| Consumer cannot understand v2 | Parse/semantic errors | Contract tests, dual support, DLQ |
| Consumer relies on internal domain enum | Coupled to refactors | Create external enum/public mapping |
| Integration message contains secrets | Leaked across broker/DLQ/logs | Allowlist fields, ACLs, retention, encryption |
| Concurrent relays claim the same row | Duplicates or reordering | Locks/leases, unique IDs, idempotency, partitioning |
| `AFTER_COMMIT` handler writes outbox after commit | Loses outbox atomicity | Write outbox in the source transaction |
| Consumer re-receives event after phantom rollback | Wrong side effects | Relay only committed outbox rows |
| Domain events kept only in an in-RAM list on crash | Events can be lost | Flush into outbox within Unit of Work |
| Schema v1 deleted prematurely | Replays/older consumers fail | Deprecation/retention/compatibility plan |

### Producer idempotency

Outbox rows typically use `event_id` as a primary/unique key so two rows cannot represent the same business fact. However, the event ID generated by the service must be **stable across retries of the same command** if the contract must avoid duplicates. Calling `UUID.randomUUID()` every time a command is retried can cause the same business operation to be recorded twice under two different event IDs.

Control duplicates at the **source** using idempotency keys, database uniqueness, or aggregate state. The outbox unique constraint is only one layer of protection and does not solve duplicate business operations on its own.

### Consumer idempotency

Illustrative consumer pattern:

```text
BEGIN CONSUMER TRANSACTION
  INSERT INTO processed_events(event_id) ... UNIQUE
  IF inserted:
      apply side effects in same transaction
  ELSE:
      skip duplicate
COMMIT
ACK broker
```

This is a design diagram, not copy-paste SQL. For side effects like email/external APIs, the consumer’s DB transaction does not guarantee atomicity with external systems; use downstream idempotency keys, a dedicated outbox, or reconciliation. The goal is usually **effectively once** for the specific business operation, never claiming “exactly once” across all systems.

## 13. What do Spring Framework, Spring Data, and Spring Modulith provide?

### Spring Framework

`ApplicationEventPublisher.publishEvent(Object)` is a mechanism to notify listeners in the context. `@EventListener` is supported for POJO/record payloads. With the default multicaster, standard listeners run synchronously; however, the publication API is a **handoff** and does not guarantee durable delivery or async completion.

`@TransactionalEventListener` lets you pick `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, or `AFTER_COMPLETION`, defaulting to after-commit. It is useful for running internal reactions in the right phase, but by itself does not turn an event into a public integration contract or an outbox.

### Spring Data

`@DomainEvents` and `AbstractAggregateRoot` help register/publish domain events from repository-managed aggregates. `@AfterDomainEventPublication` cleans up the pending event buffer after publication. Never equate this with “the message reached Kafka” or “the transaction committed”.

### Spring Modulith

Spring Modulith provides **module boundary** checks, application module listeners, an event publication registry, and event externalization. Per the official documentation, event externalization allows you to:

- Select events to externalize (e.g., via `@Externalized` or a configuration selector).
- Map the original event to an external payload.
- Specify broker routing targets and headers.
- Integrate with Kafka/AMQP/JMS/Spring Messaging with the appropriate dependencies.
- Record/recover event publications via the registry and configured mechanisms.

**Do not equate all event externalization with a traditional transactional outbox.** Different modes/tools have different characteristics. Spring Modulith 2.1 documentation describes outbox options through integrations such as Namastack/JobRunr alongside listener-based externalization. Choose the exact version and mechanism matching your durability, concurrency, and ordering needs; never copy config from another version without verifying.

A conceptual configuration snippet, **not a standalone program**:

```java
// API paths in Spring Modulith depend on the chosen version.
// This is a mapping illustration only; full bean configuration is required.
EventExternalizationConfiguration.externalizing()
    .select(EventExternalizationConfiguration.annotatedAsExternalized())
    .mapping(OrderPaid.class, event -> toExternal(event))
    .build();
```

When using an externalization framework, still review mappings so sensitive domain events are never serialized verbatim. Explicitly define “which event”, “which payload”, “which route”, and reliability/retention settings.

## 14. Testing the domain and integration boundary

### 14.1. Domain unit tests

Verify domain behavior and pending events **without needing a Spring broker**:

- Valid payment commands produce `OrderPaid` facts with accurate data.
- Commands violating invariants emit no success events.
- No Kafka/JSON schema dependencies exist in domain code.
- Event IDs, `occurredAt`, and aggregate versions follow rules.
- Repeated calls do not emit duplicate events once the aggregate is already paid.

### 14.2. Mapper unit tests

Verify the **schema allowlist**:

```java
// Test excerpt using record definitions from the example and JUnit.
OrderPaid domain = new OrderPaid(
        "evt-100", "O-100", 1500, "USD", "PRIVATE-RISK");
PaymentConfirmedV1 external = toIntegrationEvent(domain);

assertEquals("evt-100", external.eventId());
assertEquals("O-100", external.orderId());
assertEquals(1, external.schemaVersion());
```

This is an illustrative snippet; `toIntegrationEvent` and `assertEquals` must be defined/imported in the test fixture. Beyond checking field values, serialize using **the real serializer** and assert that the JSON/Avro/Protobuf output does not contain `internalRiskCode` or disallowed data.

### 14.3. Integration transaction/outbox tests

Run against a real DB transaction:

1. Valid command → exactly one order row and one integration outbox row.
2. Outbox row has event type `payment.confirmed.v1`, `schemaVersion=1`, and **no** internal risk field.
3. Invalid-amount command → no new order/outbox row.
4. Bridge throws exception → both changes roll back.
5. After commit, relay sees the row; before commit, another connection does not see the uncommitted row under proper isolation.
6. Relay sends successfully and marks delivered; re-running relay does not resend once the marker committed.
7. Simulate relay crash after broker ack but before marker update → resend can happen; consumer idempotency avoids duplicate side effects.
8. Simulate multiple relays/ordering/retries to verify locking/lease strategies.

### 14.4. Consumer contract tests

An integration contract must be tested **without depending on internal Java classes**:

- Consumers read messages built from the official schema.
- Required/optional fields and unknown enum handling behave properly.
- Older versions remain supported during the deprecation window.
- Consumers do not depend on JSON field ordering, Java enum string representations, or package names.
- Replays preserve event ID, timestamp, and payload semantics.
- Contracts contain no disallowed PII/secrets; logs, DLQs, broker payloads, and traces also leak nothing.

### 14.5. Failure/chaos tests

Inject failures: DB disconnects, mapper errors, broker timeouts, process crashes between commit and relay, lost broker acks, duplicate deliveries, DLQ replays, schema incompatibilities, slow consumers, and queue backlogs. Verify responses and **durable state**, rather than just checking a “event published” log line.

## 15. Common design mistakes

**Mistake 1 — Exposing domain-event classes directly as integration DTOs.** Couples consumers to internal fields and class changes.

**Mistake 2 — Letting aggregates import `KafkaTemplate`/`RestClient`.** Couples business logic to transport/serializers.

**Mistake 3 — Sending every domain event to the broker.** Increases coupling, traffic, retention, and unnecessary data exposure.

**Mistake 4 — Copying raw JPA entities as payloads.** Exposes lazy relations, sensitive fields, mutable state, and fragile serialization.

**Mistake 5 — Publishing messages to the broker before the transaction commits.** Consumers can observe business facts that never committed.

**Mistake 6 — Writing to the outbox in an `AFTER_COMMIT` callback and claiming it is atomic.** State already committed; the outbox insert is outside the source transaction.

**Mistake 7 — Using an async `@EventListener` for a bridge meant to write the outbox in the same transaction.** Thread-bound transaction context does not transfer automatically; atomicity is lost.

**Mistake 8 — Only bumping `schemaVersion` without testing compatibility.** Semantic breaks can still cause consumers to misbehave.

**Mistake 9 — Minting a new event ID on every retry.** Consumers cannot deduplicate a single business fact.

**Mistake 10 — Treating `publishEvent` returning as broker delivery.** It is an in-process handoff, not a broker acknowledgment.

**Mistake 11 — Ignoring duplicates/reordering when relays run concurrently.** Real at-least-once delivery requires consumer idempotency and ordering strategies.

**Mistake 12 — Not managing deprecation.** External consumers may still need schema v1, including replays of historical data.

**Mistake 13 — Putting `internalRiskCode`, tokens, or passwords into integration payloads.** An event can live in brokers/DLQs/backups longer than the source database.

**Mistake 14 — Having consumers look up the current entity and treat it as a historical snapshot.** State may change after the event was emitted; select snapshot fields intentionally.

**Mistake 15 — Counting broker messages as the number of domain facts.** Relay retries can send the same `eventId` multiple times.

**Mistake 16 — Naming a command as a fact that already happened.** `SendReceipt` and `ReceiptSent` have different semantics; name them accurately.

**Mistake 17 — Encoding integration versions solely in Java package names as the contract.** Non-Java consumers still need clear schemas, docs, and compatibility rules.

## 16. Implementation checklist

- [ ] Identify bounded contexts and consumers outside the boundary.
- [ ] Define domain facts and name them in business terminology.
- [ ] Keep aggregates free of broker/client/serializer dependencies.
- [ ] Externalize only events needed by approved consumers.
- [ ] Create separate, immutable integration event contracts with minimal data.
- [ ] Define stable event IDs, types, schema/versions, and clear timestamp semantics.
- [ ] Use allowlist mapping; never send unnecessary entities/credentials/PII.
- [ ] Specify amount/currency/time/ID/enum/nullable formats.
- [ ] Write state and outbox in the same transaction where atomicity is required.
- [ ] Relay only committed messages, with broker ack/retry/backoff.
- [ ] Multi-instance relays have claiming/leases and appropriate ordering mechanisms.
- [ ] Consumers are idempotent by stable event ID and have DLQ/replay policies.
- [ ] Contract tests and a v1→v2 migration/deprecation plan exist.
- [ ] Producer/consumer ACLs, data retention, encryption, and log redaction are in place.
- [ ] Measure events created, outbox pending, relay delivered/failed, and consumer lag.
- [ ] Evaluate Spring Modulith externalization/publication registry per exact version and needs.
- [ ] Test rollbacks, process crashes, duplicates, replays, schema compatibility, and sensitive data handling.

## 17. Self-check questions

1. **What is the main difference between a domain event and an integration event?** — A domain event describes a fact in the internal model; an integration event is a stable contract for external consumption.
2. **Must there be a 1:1 mapping between the two event types?** — No; mapping can filter, aggregate, or produce separate contracts as needed.
3. **Why not send raw entities or domain events directly to Kafka?** — It exposes internal structure, creates tight coupling, and risks leaking sensitive data.
4. **What is the mapper’s job?** — Translate domain semantics into public schemas, normalize/allowlist fields, and attach required metadata.
5. **Why not publish to the broker before DB commit?** — You risk emitting a fact outside the application when the source transaction later rolls back.
6. **Is `AFTER_COMMIT` equivalent to an outbox?** — No; after-commit controls timing, not durability.
7. **Where should the outbox be inserted to be atomic with state?** — In the same DB transaction as the aggregate mutation.
8. **What happens if the broker receives an event but the relay crashes before marking delivered?** — The event may be sent again; consumers must be idempotent.
9. **Is `schemaVersion` alone enough to guarantee older consumers will not break?** — No; you must test both syntactic and semantic compatibility.
10. **When adding `internalRiskCode` to the domain, must the integration event change too?** — No, unless external consumers genuinely need and are permitted to have it; the mapper governs the contract.
11. **Can one integration event represent multiple domain facts?** — Yes, when the contract publishes an aggregated business milestone.
12. **Does Spring `ApplicationEventPublisher` guarantee the broker received the message?** — No; it is an in-context notification mechanism.
13. **Do Spring Data domain events automatically guarantee Kafka delivery?** — No; dedicated integration/publication infrastructure is needed.
14. **What must a consumer reading both v1 and v2 avoid during dual publishing?** — Applying side effects twice for the same business fact.
15. **Why must `eventId` stay unchanged across retries?** — So deduplication/replay can recognize the exact same business occurrence.

## References

- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.2.8 — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Data Commons — Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/commons/reference/repositories/core-domain-events.html)
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Modulith — Event Externalization Configuration](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/EventExternalizationConfiguration.html)
- [Apache Kafka — Core Concepts](https://kafka.apache.org/documentation/)
