# Data Normalization Pipeline with Supplier, Function, and Consumer

In event-driven systems, incoming data often originates from multiple sources and lacks consistency in formatting, data types, or business conventions. One service might receive customer names with extra whitespace, lowercase country codes, monetary amounts as strings, and inconsistent currency codes. If every consumer performs normalization in its own way, different services can easily produce divergent results.

Spring Cloud Stream provides a functional programming model to split the processing pipeline into three roles:

- **Supplier** produces or retrieves events from a source.
- **Function** transforms and normalizes events.
- **Consumer** receives the results to record them or execute downstream business logic.

This hands-on exercise builds an order pipeline over a message broker. The Supplier publishes raw data to the `orders.raw` topic; the Function validates and normalizes it, then publishes to `orders.normalized`; the Consumer receives the normalized data. Each function has its own binding, allowing each stage to be observed, scaled, and tested independently.

## 1. Objectives and Architecture

After completing this exercise, you will be able to create all three types of function beans, declare independent functions, map bindings to destinations, configure the Kafka binder, normalize data, test, and observe the message flow.

~~~mermaid
flowchart LR
    A["Supplier<br/>orderSource"] -->|"orders.raw"| B["Kafka topic<br/>orders.raw"]
    B --> C["Function<br/>normalizeOrder"]
    C -->|"orders.normalized"| D["Kafka topic<br/>orders.normalized"]
    D --> E["Consumer<br/>consumeOrder"]
    E --> F["Log / Database / downstream"]
~~~

The two topics represent two data boundaries. This lesson runs all three functions in a single application for ease of practice; in production, each role can be split into a separate service without changing the message contract.

## 2. Data Design

Sample input:

~~~json
{
  "eventId": "evt-order-001",
  "orderId": "order-101",
  "customerName": "  Nguyen   Van An ",
  "email": " AN@example.com ",
  "country": "vn",
  "amount": "125000.00",
  "currency": "vnd"
}
~~~

The Function needs to trim and collapse whitespace in the customer name, convert the email to lowercase, convert the country code to two uppercase letters, parse the amount, and normalize the currency code to three uppercase letters.

Expected output:

~~~json
{
  "eventId": "evt-order-001",
  "orderId": "order-101",
  "customerName": "Nguyen Van An",
  "email": "an@example.com",
  "countryCode": "VN",
  "amount": 125000.00,
  "currency": "VND"
}
~~~

Preserve `eventId` and `orderId` to correlate messages across stages. Use `BigDecimal` for monetary amounts instead of `double` because binary floating-point numbers can inaccurately represent decimal values. Define scale and rounding rules per currency according to real-world business requirements.

## 3. Project and Dependencies

Create a Spring Boot application with Spring Cloud Stream and the Kafka binder. Manage versions using the Spring Boot parent and a compatible Spring Cloud BOM; select the release train according to the official compatibility matrix.

Example Maven dependencies:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>SPRING_CLOUD_COMPATIBLE_RELEASE</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-stream-kafka</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-stream-test-binder</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Replace `SPRING_CLOUD_COMPATIBLE_RELEASE` with a release train compatible with the Spring Boot version in use. If the parent project already imports the BOM, do not import another version of the BOM in a child module.

Minimal project structure:

~~~text
src/main/java/com/example/orders/
  OrderNormalizationApplication.java
  OrderFunctions.java
  RawOrder.java
  NormalizedOrder.java
src/main/resources/application.yml
src/test/java/com/example/orders/OrderNormalizationTest.java
~~~

## 4. Declaring DTOs

`RawOrder.java`:

~~~java
package com.example.orders;

public record RawOrder(
        String eventId,
        String orderId,
        String customerName,
        String email,
        String country,
        String amount,
        String currency) {
}
~~~

`NormalizedOrder.java`:

~~~java
package com.example.orders;

import java.math.BigDecimal;

public record NormalizedOrder(
        String eventId,
        String orderId,
        String customerName,
        String email,
        String countryCode,
        BigDecimal amount,
        String currency) {
}
~~~

Records are well-suited for immutable DTOs. Modern Spring Boot/Jackson versions support Java records when dependencies and versions are compatible. If you use a different native serializer or schema, you must configure the corresponding schema instead of assuming the JSON converter handles every format.

## 5. Creating the Supplier, Function, and Consumer

Create `OrderFunctions.java`:

~~~java
package com.example.orders;

import java.math.BigDecimal;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderFunctions {

    private static final Logger log =
            LoggerFactory.getLogger(OrderFunctions.class);

    @Bean
    Supplier<RawOrder> orderSource() {
        List<RawOrder> sampleOrders = List.of(
                new RawOrder("evt-order-001", "order-101",
                        "  Nguyen   Van An ", " AN@example.com ",
                        "vn", "125000.00", "vnd"),
                new RawOrder("evt-order-002", "order-102",
                        "Tran Thi Binh", "binh@example.com",
                        "sg", "89.90", "sgd"),
                new RawOrder("evt-order-003", "order-103",
                        "  Le   Minh Cuong", "CUONG@example.com",
                        "us", "42.50", "usd"));

        Iterator<RawOrder> iterator = sampleOrders.iterator();
        return () -> iterator.hasNext() ? iterator.next() : null;
    }

    @Bean
    Function<RawOrder, NormalizedOrder> normalizeOrder() {
        return raw -> {
            String eventId = required(raw.eventId(), "eventId");
            String orderId = required(raw.orderId(), "orderId");
            String customerName = required(
                    raw.customerName(), "customerName")
                    .replaceAll("\\s+", " ");
            String email = required(raw.email(), "email")
                    .toLowerCase(Locale.ROOT);
            String countryCode = required(raw.country(), "country")
                    .toUpperCase(Locale.ROOT);
            String currency = required(raw.currency(), "currency")
                    .toUpperCase(Locale.ROOT);

            if (!email.matches("^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$")) {
                throw new IllegalArgumentException("Invalid email");
            }
            if (!countryCode.matches("[A-Z]{2}")) {
                throw new IllegalArgumentException("Invalid country code");
            }
            if (!currency.matches("[A-Z]{3}")) {
                throw new IllegalArgumentException("Invalid currency code");
            }

            BigDecimal amount;
            try {
                amount = new BigDecimal(required(raw.amount(), "amount"));
            }
            catch (NumberFormatException ex) {
                throw new IllegalArgumentException("Invalid amount", ex);
            }
            if (amount.signum() < 0) {
                throw new IllegalArgumentException(
                        "Amount must not be negative");
            }

            return new NormalizedOrder(
                    eventId, orderId, customerName, email,
                    countryCode, amount, currency);
        };
    }

    @Bean
    Consumer<NormalizedOrder> consumeOrder() {
        return order -> log.info(
                "Order normalized eventId={}, orderId={}, country={}, currency={}",
                order.eventId(), order.orderId(),
                order.countryCode(), order.currency());
    }

    private static String required(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " is required");
        }
        return value.strip();
    }
}
~~~

### Data-Producing Supplier

`orderSource()` returns `Supplier<RawOrder>`. Spring Cloud Stream uses a poller to invoke the supplier periodically. This example reads three records sequentially and returns `null` when exhausted; invocations returning `null` do not emit a message.

This Supplier is only a sample source. In production, it may read from an API, an outbox table, a file, or another system. If the source is stateful, design a checkpoint or acknowledgment mechanism so data is not marked as consumed before publication is guaranteed according to the contract.

**Scaling note:** each instance in this example creates its own list and iterator, so two instances will emit two copies of the same three events. Production requires a work-partitioning/lease mechanism, a shared cursor, or an outbox pattern so multiple instances do not emit unintended duplicates.

### Data-Normalizing Function

`normalizeOrder()` takes a `RawOrder` and returns a `NormalizedOrder`. The Function checks required IDs, normalizes the name and email, validates the format of country and currency codes, and parses the amount. It does not call the database or broker directly, making the logic easy to unit test and reuse.

The email regex is only a basic syntax check and does not replace real address verification. Real applications should use standardized country/currency catalogs and corresponding business rules.

### Result-Receiving Consumer

`consumeOrder()` logs only the necessary fields and avoids logging email/PII. In production, you can replace the log sink with a repository, an API call, or a business service. Persist `eventId` with a unique constraint or an inbox table to prevent duplicate processing when a message is redelivered.

## 6. Initializing the Application

`OrderNormalizationApplication.java`:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderNormalizationApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                OrderNormalizationApplication.class, args);
    }
}
~~~

There is no need to write a manual Kafka adapter. The binder creates the bindings from the function beans and configuration.

## 7. Function Definition and Bindings

Create `application.yml`:

~~~yaml
spring:
  application:
    name: order-normalization
  cloud:
    function:
      definition: orderSource;normalizeOrder;consumeOrder
    stream:
      poller:
        fixed-delay: 2000
      bindings:
        orderSource-out-0:
          destination: orders.raw
          content-type: application/json
        normalizeOrder-in-0:
          destination: orders.raw
          group: order-normalizers
          content-type: application/json
        normalizeOrder-out-0:
          destination: orders.normalized
          content-type: application/json
        consumeOrder-in-0:
          destination: orders.normalized
          group: order-sinks
          content-type: application/json
      kafka:
        binder:
          brokers: localhost:9092
        bindings:
          orderSource-out-0:
            producer:
              message-key-expression: payload.orderId
          normalizeOrder-out-0:
            producer:
              message-key-expression: payload.orderId
~~~

### Why Use Semicolons?

`spring.cloud.function.definition` uses semicolons to activate multiple independent functions within the same application context:

~~~text
orderSource;normalizeOrder;consumeOrder
~~~

This is not function composition. The three beans are bound independently:

| Function bean | Type | Binding |
|---|---|---|
| `orderSource` | `Supplier<RawOrder>` | `orderSource-out-0` |
| `normalizeOrder` | `Function<RawOrder, NormalizedOrder>` | `normalizeOrder-in-0`, `normalizeOrder-out-0` |
| `consumeOrder` | `Consumer<NormalizedOrder>` | `consumeOrder-in-0` |

The pipe symbol (`|`) represents function composition, where the output of the preceding function is connected directly to the input of the next function. This exercise uses separate destinations so messages can be observed through the broker and each stage can scale independently.

### Binding Semantics

| Binding | Direction | Destination | Group | Role |
|---|---|---|---|---|
| `orderSource-out-0` | Output | `orders.raw` | — | Supplier emits raw data |
| `normalizeOrder-in-0` | Input | `orders.raw` | `order-normalizers` | Function reads raw data |
| `normalizeOrder-out-0` | Output | `orders.normalized` | — | Function emits normalized data |
| `consumeOrder-in-0` | Input | `orders.normalized` | `order-sinks` | Consumer receives results |

Both input bindings declare explicit groups. In Kafka, a group defines an independent consumer group and offset tracking. You should not rely on anonymous/ephemeral groups for services that need to persist consumption progress.

`content-type: application/json` indicates that payloads are exchanged as JSON. When using native encoding/decoding or custom schemas, you must configure the corresponding serializer/deserializer; the JSON converter may not participate in the native path.

### Partition Key

Both output bindings use `payload.orderId` as the Kafka record key. Events belonging to the same order can go to the same partition to preserve per-order ordering, while different orders can be distributed across partitions. If business logic requires ordering by account or tenant, choose the key matching the aggregate that truly requires serialization.

## 8. Preparing the Kafka Broker

Run Kafka locally or use an authorized development cluster. Example topic creation:

~~~bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create --if-not-exists \
  --topic orders.raw \
  --partitions 3 \
  --replication-factor 1

kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create --if-not-exists \
  --topic orders.normalized \
  --partitions 3 \
  --replication-factor 1
~~~

A replication factor of 1 is suitable for a single local broker, not for production durability. In production, topics, partitions, replication, retention, and ACLs should be provisioned through infrastructure workflows. The Kafka binder can auto-provision topics if the broker allows it; this exercise creates topics explicitly to verify destinations and permissions.

## 9. Running and Observing Each Stage

Start the application after Kafka is ready. The Supplier polls every two seconds and emits three records:

~~~text
orderSource -> orders.raw
normalizeOrder <- orders.raw
normalizeOrder -> orders.normalized
consumeOrder <- orders.normalized
~~~

Read the raw topic using a separate diagnostic group:

~~~bash
kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic orders.raw \
  --group diag-orders-raw \
  --from-beginning \
  --property print.key=true \
  --property print.partition=true \
  --property print.offset=true
~~~

Read the normalized topic:

~~~bash
kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic orders.normalized \
  --group diag-orders-normalized \
  --from-beginning \
  --property print.key=true \
  --property print.partition=true \
  --property print.offset=true
~~~

Diagnostic consumers use groups distinct from `order-normalizers` and `order-sinks`, so they do not steal partition assignments from the application. Verify that the key is the order ID and the payload contains the normalized fields.

Expected consumer logs:

~~~text
Order normalized eventId=evt-order-001, orderId=order-101, country=VN, currency=VND
Order normalized eventId=evt-order-002, orderId=order-102, country=SG, currency=SGD
Order normalized eventId=evt-order-003, orderId=order-103, country=US, currency=USD
~~~

A specific partition ID is not required because mapping depends on the partition count and partitioner. What must be confirmed is that the same order ID is used as the key and records are read from the expected topic.

## 10. Observing Bindings and Consumer Groups

Add Actuator configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,bindings
~~~

Endpoints you can inspect:

~~~http
GET /actuator/health
GET /actuator/bindings
GET /actuator/bindings/normalizeOrder-in-0
GET /actuator/bindings/consumeOrder-in-0
~~~

The bindings endpoint shows whether a binding is running. It also exposes lifecycle operations; do not send `START`/`STOP` requests in production just for experimentation because doing so can trigger rebalances or alter consumption state.

Inspect consumer groups:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group order-normalizers

kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group order-sinks
~~~

Compare partition assignments, current offset, log end offset, and lag. If the raw topic grows while the normalizer group has no members, check the function definition, input binding, and broker connection. If the normalized topic has data while the sink is not processing, check the final consumer binding.

## 11. Testing Invalid Data

Try sending a record with an invalid amount:

~~~json
{
  "eventId": "evt-order-invalid",
  "orderId": "order-invalid",
  "customerName": "Test User",
  "email": "test@example.com",
  "country": "vn",
  "amount": "not-a-number",
  "currency": "vnd"
}
~~~

The Function throws `IllegalArgumentException` when parsing the amount. This is a data error and should not be silently converted to 0 or dropped without recording it.

| Error type | Recommended action |
|---|---|
| Transient error calling downstream | Bounded retry with backoff |
| Temporary broker disconnection | Binder-level recovery |
| Malformed payload schema or missing required fields | DLT/DLQ or quarantine |
| Non-retryable business error | Record rejection with event ID and reason |
| Consumer finishes processing but ACK fails | Allow redelivery and protect side effects with idempotency |

Spring Cloud Stream provides common error handling, and individual binders offer specific retry/DLQ configurations. Property names, DLT partition requirements, and header forwarding depend on the binder and version. Do not enable infinite retries for permanent data errors because poison messages can consume resources and increase lag.

## 12. Unit Testing the Function

`normalizeOrder()` is a pure Java function, so it can be tested without a broker.

`OrderNormalizationTest.java`:

~~~java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.function.Function;
import org.junit.jupiter.api.Test;

class OrderNormalizationTest {

    private final Function<RawOrder, NormalizedOrder> normalizer =
            new OrderFunctions().normalizeOrder();

    @Test
    void normalizesOrderFields() {
        RawOrder raw = new RawOrder(
                "evt-101", "order-101",
                "  Nguyen   Van An ", " AN@example.com ",
                "vn", "125000.00", "vnd");

        NormalizedOrder result = normalizer.apply(raw);

        assertThat(result.eventId()).isEqualTo("evt-101");
        assertThat(result.orderId()).isEqualTo("order-101");
        assertThat(result.customerName()).isEqualTo("Nguyen Van An");
        assertThat(result.email()).isEqualTo("an@example.com");
        assertThat(result.countryCode()).isEqualTo("VN");
        assertThat(result.amount()).isEqualByComparingTo("125000.00");
        assertThat(result.currency()).isEqualTo("VND");
    }

    @Test
    void rejectsInvalidAmount() {
        RawOrder raw = new RawOrder(
                "evt-102", "order-102", "Test User",
                "test@example.com", "vn", "invalid", "vnd");

        assertThatThrownBy(() -> normalizer.apply(raw))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("Invalid amount");
    }

    @Test
    void rejectsMissingOrderId() {
        RawOrder raw = new RawOrder(
                "evt-103", " ", "Test User",
                "test@example.com", "vn", "10.00", "vnd");

        assertThatThrownBy(() -> normalizer.apply(raw))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("orderId is required");
    }
}
~~~

Unit tests verify normalization and validation logic. They do not test JSON serialization, binding names, Kafka keys, broker acknowledgment, or consumer groups.

## 13. Test Binder and Real-Broker Testing

The Spring Cloud Stream Test Binder allows testing functions and bindings in the JVM without starting Kafka. A test context can enable `@EnableTestBinder`, send messages to `InputDestination`, and receive messages from `OutputDestination`.

Test flow for `normalizeOrder`:

1. Activate only the `normalizeOrder` function in the test context.
2. Send a `RawOrder` to the `normalizeOrder-in-0` binding.
3. Receive the output from `normalizeOrder-out-0`.
4. Assert the payload, content type, and required headers.
5. Send an invalid record to verify error handling.

The Test Binder verifies wiring and conversion at the Spring Cloud Stream level. It does not verify native Kafka keys/partitions, RabbitMQ exchange routing, publisher confirms, or Pulsar subscriptions.

An integration test using Testcontainers should start a real Kafka instance, configure the broker URL via `@DynamicPropertySource`, send an event with a unique ID, and await the consumer outcome with a bounded timeout. Verify the expected topic, key, normalized payload, consumer group, and final side effect. Avoid using a fixed `Thread.sleep` as proof that a message has been processed.

## 14. Idempotency and Side Effects

In the sample exercise, the Consumer only logs messages. When writing to a database, brokers typically provide at-least-once delivery: the same message can be redelivered if the consumer crashes after committing to the DB but before ACK/offset commit.

Illustrative handling pattern:

~~~java
@Transactional
public void handle(NormalizedOrder order) {
    if (processedEventRepository.existsByEventId(order.eventId())) {
        return;
    }
    orderRepository.save(toEntity(order));
    processedEventRepository.save(new ProcessedEvent(order.eventId()));
}
~~~

`processed_event.event_id` requires a unique constraint so two concurrent executions cannot both succeed in writing. The duplicate check and side-effect write must reside within the same transaction or an equivalent atomic mechanism; handle unique-constraint race conditions according to the actual database in use.

Do not claim that Kafka, RabbitMQ, or Pulsar automatically guarantee exactly-once semantics for arbitrary side effects outside the broker. For the DB → broker flow, the transactional outbox pattern records business data and the intent to publish an event within the same database transaction; a separate publisher sends outbox records to the broker.

## 15. Scaling to Multiple Instances

~~~mermaid
flowchart TB
    S["Source service<br/>Supplier"] --> R["Kafka: orders.raw"]
    R --> F["Normalizer group<br/>Function"]
    F --> N["Kafka: orders.normalized"]
    N --> C["Sink group<br/>Consumer"]
~~~

- A Supplier only scales safely if the source partitions work across instances or uses a shared outbox, lease, or checkpoint.
- A Function consumer group can have multiple instances; Kafka distributes partitions among members of the same group.
- Parallel consumer processing is bounded by the number of assigned partitions.
- The final Consumer scales independently from the normalizer if the normalized topic has enough partitions.
- Each group maintains its own offsets; different groups can independently read the same topic.

If a topic has three partitions and a group runs six consumer instances, at least three instances will have no partitions to process at any given time. Adding consumers beyond the partition count does not automatically increase throughput.

## 16. Switching to RabbitMQ or Pulsar

The function model and binding names can stay the same when swapping binders, but broker semantics differ:

| Component | Kafka | RabbitMQ | Pulsar |
|---|---|---|---|
| Destination | Topic | Exchange/queue mapped by binder | Topic |
| Group | Consumer group and offsets | Queue/group topology | Subscription |
| Distribution | Topic partitions | Routing key, queue, and consumer | Partitioned topic, subscription type |
| Ordering | Within a single partition | Depends on queue, consumer, prefetch, and requeue | Depends on key, partition, and subscription type |
| Delivery observability | Record metadata, offset, lag | Publisher confirms/returns, ready/unacked | Message ID, backlog, redelivery |

With RabbitMQ, inspect the exchange, queue, and binding key; a publisher confirm ACK alone does not prove a message was routed into a queue. With Pulsar, inspect tenant/namespace/topic, subscription name, subscription type, and cursor. Whenever you change binders, you must run integration tests against the corresponding real broker.

## 17. Troubleshooting

| Symptom | Possible cause | How to check |
|---|---|---|
| Supplier does not emit data | Definition missing supplier or poller not active | Check function definition, poller, and startup logs |
| Raw topic has no records | Wrong output binding, broker connection, or producer error | Check orderSource-out-0, destination, and producer errors |
| Raw topic has records but Function does not run | Input binding stopped, wrong group, or no assignment | Check normalizeOrder-in-0, group, and lag |
| Function reports conversion error | Content type/JSON/schema mismatch | Check application/json, DTO, and serializer |
| Normalized topic has no records | Function throws exception or wrong output binding | Check validation errors, retry/DLT, and normalizeOrder-out-0 |
| Final Consumer does not log | Wrong group/binding or message has not reached normalized topic | Read the topic and check consumeOrder-in-0 |
| Messages processed repeatedly | Redelivery or multiple Supplier instances emitting same sample | Use event ID and an idempotent sink |
| Consumer lag increases | Slow processing, too few partitions, or downstream bottleneck | Measure per-partition lag, latency, and resources |
| Test Binder passes but Kafka has no records | Test only runs in the JVM | Run real-broker integration tests |

When diagnosing issues, trace the event ID from the raw topic to the normalized topic and Consumer logs. Do not conclude the broker received a message solely because `StreamBridge.send()` returned `true`; local handoff and broker acknowledgment are distinct milestones.

## 18. Extension Exercises and Acceptance Criteria

Exercises:

1. Add `sourceSystem` to `RawOrder` and `NormalizedOrder`.
2. Normalize phone numbers by country code without logging the phone numbers.
3. Create a dedicated validator and write tests for email, country code, currency code, and amount.
4. Send a record with an invalid schema; observe retry and DLT/DLQ behavior.
5. Replace the Consumer log with a repository enforcing a unique constraint on `eventId`.
6. Run two normalizer instances and observe consumer group assignment.
7. Increase the partition count in a test environment, then measure lag and key distribution.
8. Write an integration test verifying that the same `orderId` uses the same Kafka record key.
9. Replace the Kafka binder with the RabbitMQ or Pulsar binder and document the topology differences.
10. Split the Supplier, Function, and Consumer into three applications while preserving the message contract.

Acceptance checklist:

- [ ] Application starts up and discovers all three function beans.
- [ ] Function definition lists three independent functions separated by semicolons.
- [ ] Supplier emits `RawOrder` into `orders.raw`.
- [ ] Function validates and produces `NormalizedOrder`.
- [ ] Function emits results into `orders.normalized`.
- [ ] Consumer receives results and logs event ID/order ID.
- [ ] Content type is consistent across bindings.
- [ ] Kafka record key is set to `orderId`.
- [ ] Consumer groups for both input bindings are declared explicitly.
- [ ] Unit tests verify normalization and validation errors.
- [ ] Test Binder results are not mistaken for real-broker proof.
- [ ] Integration tests verify the end-to-end path through the broker.
- [ ] Retry/DLT/DLQ is bounded and observable.
- [ ] Sink implements idempotency if side effects must not repeat.
- [ ] Supplier does not emit unintended duplicates when scaled.

## Conclusion

The data normalization pipeline demonstrates how to structure a Spring Cloud Stream application around independent functions. The Supplier produces input data, the Function focuses on pure validation and transformation, and the Consumer receives results to execute side effects. Bindings connect functions to destinations and consumer groups, while the binder handles communication with Kafka or another broker. By keeping responsibilities separated, maintaining stable payload/key contracts, testing through a real broker, and designing consumer idempotency, the pipeline can scale into multiple services while remaining easy to observe and operate.

## References

- [Spring Cloud Stream — Programming Model](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/programming-model.html)
- [Spring Cloud Stream — Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/overview.html)
- [Spring Cloud Stream — Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Spring Cloud Stream — Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html)
- [Spring Cloud Stream — RabbitMQ Binder](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
