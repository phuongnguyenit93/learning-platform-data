# Triggering Messaging Stubs and Verifying Consumer Code

## Project Goals

**Spring Cloud Contract** helps producers and consumers agree on HTTP or messaging behavior using the **Groovy/YAML DSL**. From a contract, the tooling generates producer-side tests, packages a stub artifact for consumers to load via **Stub Runner**, and integrates checks into CI to detect incompatible API changes.

This hands-on project builds two small services:

- **Order Service (producer):** when an order transitions to paid status, emits an `ORDER_PAID` message to destination `orders.events`.
- **Shipping Service (consumer):** receives the message, creates a shipment for the order, and ensures duplicate deliveries do not create duplicate shipments.

You will complete the entire flow:

~~~text
Order Service
  -> producer message contract
  -> generated producer test
  -> stub artifact

Shipping Service
  -> Stub Runner downloads stub
  -> StubTrigger fires message by label
  -> message binding invokes consumer code
  -> assertions verify shipment is created
~~~

After completing this project, you will be able to:

1. Write a message contract specifying destination, headers, and payload.
2. Use `triggeredBy` so generated producer tests trigger real message-publishing logic.
3. Build and install a stub artifact with classifier `stubs`.
4. Use `@AutoConfigureStubRunner` and `StubTrigger` to emit stub messages in consumer tests.
5. Verify consumer code through business state and repositories—not merely asserting that the stub fired.
6. Test idempotency, message headers, schemas, and destination misconfigurations.
7. Integrate producer verification, stub packaging, and consumer tests into CI.

**Key distinction throughout:** `triggeredBy` in producer tests invokes a trigger method on the producer application; `StubTrigger.trigger(label)` in consumer tests emits a message from the stub to verify the consumer. The two mechanisms serve different roles.

## 1. Business Scenario

An order can transition from `PENDING` to `PAID`. Once payment succeeds, Order Service emits an event:

~~~json
{
  "eventId": "EVT-ORD-1001-PAID",
  "eventType": "ORDER_PAID",
  "orderId": "ORD-1001",
  "amount": 125000,
  "currency": "VND"
}
~~~

Shipping Service receives the event and creates a shipment in state `READY_FOR_PICKUP`.

### Business Flow

~~~mermaid
sequenceDiagram
    participant API as Order Service
    participant DB as Order DB
    participant PUB as Message Publisher
    participant BUS as orders.events
    participant SH as Shipping Consumer
    participant SDB as Shipping DB

    API->>DB: Read order ORD-1001
    API->>DB: Transition state to PAID
    API->>PUB: Publish ORDER_PAID
    PUB->>BUS: Event JSON + headers
    BUS->>SH: Deliver message
    SH->>SDB: Create shipment
    SH-->>BUS: Processing succeeded
~~~

In this lab, the message contract verifies producer output. Stub Runner emits a sample message so consumer tests traverse Shipping Service's **real message binding and handler**.

**Contract tests do not prove production brokers guarantee exactly-once delivery or ordering.** We use a compatible test binder / messaging adapter to verify consumer code, and explicitly identify what requires integration tests with a real broker.

## 2. Architecture and Project Layout

Both services can live in a Maven multi-module project:

~~~text
messaging-contract-lab/
├── pom.xml
├── order-service/
│   ├── pom.xml
│   └── src/
│       ├── main/java/com/example/orders/
│       │   ├── OrderApplication.java
│       │   ├── OrderApplicationService.java
│       │   ├── OrderEventPublisher.java
│       │   └── StreamOrderEventPublisher.java
│       └── test/
│           ├── java/com/example/orders/contract/
│           │   └── OrderMessageContractBase.java
│           └── resources/contracts/orders/
│               └── order-paid.yml
└── shipping-service/
    ├── pom.xml
    └── src/
        ├── main/java/com/example/shipping/
        │   ├── ShippingApplication.java
        │   ├── OrderPaidEvent.java
        │   ├── OrderPaidConsumer.java
        │   ├── ShippingService.java
        │   └── ShipmentRepository.java
        ├── test/java/com/example/shipping/
        │   └── OrderPaidConsumerContractTest.java
        └── test/resources/
            └── application-test.yml
~~~

Package and class names are illustrative choices for the sample project. In a real project, follow existing package, module boundary, and naming conventions.

### Component Roles

| Component | Responsibility |
| --- | --- |
| `order-paid.yml` | Contract for the `ORDER_PAID` message |
| `OrderMessageContractBase` | Prepares fixtures and provides the `triggeredBy` method |
| `OrderApplicationService` | Performs order state transition |
| `StreamOrderEventPublisher` | Sends events via Spring Cloud Stream |
| Contract Verifier | Generates and runs producer message tests |
| Stub JAR | Packages message stubs and labels |
| `StubTrigger` | Fires stub messages on the consumer side |
| `OrderPaidConsumer` | Receives events via binding |
| `ShippingService` | Executes shipment-creation business logic |
| Consumer contract test | Verifies handler and shipment state |

## 3. Preparing the Toolchain and Dependencies

Use a set of Spring Boot, Spring Cloud release train, Spring Cloud Contract, and JDK versions verified against your project compatibility matrix. Do not pick independent versions solely because they are the newest.

In both modules, manage Spring dependencies via a compatible parent or BOM. **The Contract Maven plugin version is declared separately**; the Spring Cloud BOM does not automatically manage plugins inside `build.plugins`.

### Producer Dependencies

The `order-service` POM needs dependencies equivalent to:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter</artifactId>
  </dependency>

  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream</artifactId>
  </dependency>

  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-verifier</artifactId>
    <scope>test</scope>
  </dependency>

  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
  </dependency>

  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

The test binder is appropriate when the application uses Spring Cloud Stream and a compatible version of Contract Verifier / message verifier is configured. If your project uses Spring Integration, direct Kafka/RabbitMQ adapters, or another messaging framework, choose the corresponding integration.

Illustrative Maven plugin:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.springframework.cloud</groupId>
      <artifactId>spring-cloud-contract-maven-plugin</artifactId>
      <version>VERIFIED_CONTRACT_PLUGIN_VERSION</version>
      <extensions>true</extensions>
      <configuration>
        <baseClassForTests>
          com.example.orders.contract.OrderMessageContractBase
        </baseClassForTests>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

`VERIFIED_CONTRACT_PLUGIN_VERSION` is a placeholder; replace it with a version compatible with your Contract libraries and build tool. Do not copy the placeholder literally to build.

### Consumer Dependencies

The `shipping-service` POM needs:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter</artifactId>
  </dependency>

  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream</artifactId>
  </dependency>

  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-stub-runner</artifactId>
    <scope>test</scope>
  </dependency>

  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
  </dependency>

  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

`spring-cloud-starter-contract-stub-runner` provides Stub Runner integration. `spring-cloud-stream-test-binder` lets consumer bindings run in tests without connecting to a shared broker. Confirm that the adapter and message verifier match your Spring Cloud Contract release line.

## 4. Step 1 — Write the Message Contract

Create the file:

`order-service/src/test/resources/contracts/orders/order-paid.yml`

~~~yaml
description: "Paid order emits ORDER_PAID event"
label: order_paid

input:
  triggeredBy: markOrderAsPaid()

outputMessage:
  sentTo: orders.events
  headers:
    contentType: application/json
  body:
    eventId: EVT-ORD-1001-PAID
    eventType: ORDER_PAID
    orderId: ORD-1001
    amount: 125000
    currency: VND
~~~

### Reading the Contract

- `label: order_paid` identifies the message stub that can be triggered on the consumer side.
- `input.triggeredBy` tells the generated producer test to call `markOrderAsPaid()` on the base test.
- `outputMessage.sentTo` specifies the logical destination to which the producer sends the message.
- `headers.contentType` indicates the payload is JSON.
- `body` defines the event payload with ID, event type, order ID, amount, and currency.

### Contracts Do Not Describe Every Broker Detail

`orders.events` is a destination in the messaging interface. The contract does not define Kafka partitions, consumer groups, retention, retries, DLQs, or delivery guarantees. Those requirements must be configured and tested in the appropriate messaging/integration layer.

### Data Types Must Be Explicit

In the body:

- `eventId`, `eventType`, `orderId`, and `currency` are strings.
- `amount` is a JSON number.
- `contentType` is a message header, not a payload field.

Do not quote `125000` as `"125000"` if the consumer schema expects a number.

## 5. Step 2 — Build the Producer Application Service

Define the event:

~~~java
package com.example.orders;

import java.math.BigDecimal;

public record OrderPaidEvent(
    String eventId,
    String eventType,
    String orderId,
    BigDecimal amount,
    String currency
) {}
~~~

Define a publisher interface to decouple business logic from transport:

~~~java
package com.example.orders;

public interface OrderEventPublisher {
    void publish(OrderPaidEvent event);
}
~~~

Application service implementing business logic:

~~~java
package com.example.orders;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final OrderEventPublisher eventPublisher;

    public OrderApplicationService(
            OrderRepository orderRepository,
            OrderEventPublisher eventPublisher) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public void markOrderAsPaid(String orderId) {
        Order order = orderRepository.findById(orderId)
            .orElseThrow(() ->
                new IllegalArgumentException("Order not found")
            );

        order.markPaid();
        orderRepository.save(order);

        OrderPaidEvent event = new OrderPaidEvent(
            "EVT-" + orderId + "-PAID",
            "ORDER_PAID",
            order.getId(),
            order.getAmount(),
            order.getCurrency()
        );

        eventPublisher.publish(event);
    }
}
~~~

`OrderRepository` and `Order` are domain/repository classes for this example. Ensure the fixture seeds order `ORD-1001` with amount `125000` and currency `VND` before triggering.

### Why Separate the Publisher Interface?

- The business service does not depend directly on a specific broker.
- Adapters can be swapped per environment.
- Contract tests still invoke **the real application service**.
- The producer message verifier observes output through the configured messaging integration.

Do not mock `OrderApplicationService` or replace the publisher with a mock that merely returns success if the goal is verifying the producer emits messages per contract.

## 6. Step 3 — Configure the Producer Output Binding

An adapter using Spring Cloud Stream's `StreamBridge` can look like this:

~~~java
package com.example.orders;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;
import org.springframework.util.MimeTypeUtils;

@Component
public class StreamOrderEventPublisher implements OrderEventPublisher {

    private final StreamBridge streamBridge;

    public StreamOrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    @Override
    public void publish(OrderPaidEvent event) {
        Message<OrderPaidEvent> message =
            MessageBuilder.withPayload(event)
                .setHeader(
                    MessageHeaders.CONTENT_TYPE,
                    MimeTypeUtils.APPLICATION_JSON
                )
                .build();

        boolean sent = streamBridge.send(
            "orderPaid-out-0",
            message
        );

        if (!sent) {
            throw new IllegalStateException(
                "Cannot publish ORDER_PAID event"
            );
        }
    }
}
~~~

Binding name `orderPaid-out-0` must match the output binding configuration. This is a Spring Cloud Stream example; exact binding and binder initialization details should match your framework version.

Configuration example:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: orderPaid-out-0
      bindings:
        orderPaid-out-0:
          destination: orders.events
          content-type: application/json
~~~

When using a production binder such as Kafka or RabbitMQ, configure the binder per runtime environment. Producer contract tests must use a suitable **test binder / message verifier** so test events never reach a production broker.

### Cross-Checking Destinations

| Location | Value |
| --- | --- |
| Contract `outputMessage.sentTo` | `orders.events` |
| `StreamBridge` binding name | `orderPaid-out-0` |
| Output binding destination | `orders.events` |
| Message verifier test destination | Destination configured by adapter from contract |
| Consumer input destination | `orders.events` |

Binding names and destinations can differ. **The destination is the channel name both producer and consumer must agree on.**

## 7. Step 4 — Write the Producer Message Base Test

Create:

`order-service/src/test/java/com/example/orders/contract/OrderMessageContractBase.java`

~~~java
package com.example.orders.contract;

import com.example.orders.OrderApplicationService;
import com.example.orders.OrderRepository;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
public abstract class OrderMessageContractBase {

    @Autowired
    private OrderRepository orderRepository;

    @Autowired
    private OrderApplicationService orderApplicationService;

    @BeforeEach
    void prepareOrderFixture() {
        orderRepository.deleteAll();
        orderRepository.save(
            OrderFixture.paidTransitionCandidate(
                "ORD-1001",
                125000,
                "VND"
            )
        );
    }

    public void markOrderAsPaid() {
        orderApplicationService.markOrderAsPaid("ORD-1001");
    }
}
~~~

`OrderFixture` is an illustrative fixture factory. In real projects, use a dedicated test database, schema-compliant fixtures, and safe cleanup. The seeded order must be in a state eligible to transition to `PAID`, such as `PENDING`.

### The `triggeredBy` Method Must Be Accessible

The generated producer test needs to invoke `markOrderAsPaid()`. Therefore:

- The method name must match the contract.
- The method signature must be callable by the generated test.
- Base class configuration must point to the right class.
- The test lifecycle must seed fixtures before the trigger runs.
- The method must trigger **real application behavior**.

If tests fail with `NoSuchMethodError` or `cannot find symbol`, check generated sources and base class mapping before changing the message body.

### Why Not Call the Publisher Directly?

If the base method directly calls `eventPublisher.publish(new OrderPaidEvent(...))`, the test only verifies sending a hardcoded payload. Calling `OrderApplicationService.markOrderAsPaid` exercises the state transition and event construction, catching cases where the producer forgets to publish or populates wrong fields.

## 8. Step 5 — Run Producer Contract Verification

Inside the `order-service` directory, run:

~~~bash
./mvnw clean verify
~~~

When the plugin and lifecycle are configured properly, Contract Verifier will:

1. Discover `order-paid.yml`.
2. Generate the producer message test.
3. Boot the Spring test context.
4. Prepare fixtures via the base test.
5. Invoke `markOrderAsPaid()`.
6. Observe the message emitted by the producer.
7. Assert destination, headers, and body against the contract.
8. Write the test report.

### Things to Confirm

- The contract was discovered properly.
- Generated test sources actually exist.
- The generated test inherits `OrderMessageContractBase`.
- `markOrderAsPaid()` was invoked.
- Output messages were captured by the test messaging integration.
- Destination `orders.events` matches.
- Header content type is JSON.
- Payload has the right fields and types.
- The generated producer test PASSES and was not skipped.

**`BUILD SUCCESS` with 0 generated tests is not successful producer verification.**

### If the Producer Test FAILS

Check in order:

1. Is the fixture in the right initial state?
2. Does `markOrderAsPaid()` execute the application service?
3. Does the business service publish the event?
4. Does the output binding route to the right destination?
5. Is the test binder / message verifier capturing that channel?
6. Does the event serializer produce JSON with expected fields and types?
7. Does the contract describe the agreed behavior accurately?

Never edit a contract just to hide a missing event or wrong producer field.

## 9. Step 6 — Package and Install the Stub Artifact

Once producer verification PASSES, install the artifact into the local Maven repository:

~~~bash
./mvnw clean install
~~~

Under standard packaging, the producer build produces a stub artifact with classifier `stubs`. Example coordinates:

~~~text
groupId:    com.example.orders
artifactId: order-service
version:    2.5.0
classifier: stubs
type:       jar
~~~

The filename typically looks like:

~~~text
order-service-2.5.0-stubs.jar
~~~

Default local Maven repository location is typically:

~~~text
~/.m2/repository/com/example/orders/order-service/2.5.0/
~~~

Actual paths may vary if Maven uses a custom `localRepository` or CI settings. On Windows, the local Maven repository normally resides under the user's home directory in `.m2/repository`.

### Inspecting the Artifact

Verify:

- The stub JAR exists.
- Its classifier is `stubs`.
- The artifact version is `2.5.0` matching the consumer test declaration.
- The JAR contains the required mappings, metadata, and message stubs.
- Contract label `order_paid` was generated properly.
- The artifact was built from the verified contract revision and producer commit.

**Do not merely check that the JAR file exists.** An empty artifact or one built from an old revision does not prove the consumer will receive the right message.

### Distinguishing Version Identifiers

| Value | Meaning |
| --- | --- |
| `2.5.0` in GAV | Order Service version |
| `stubs` | Stub artifact classifier |
| Spring Cloud Contract plugin version | Tooling version generating tests and stubs |
| `order_paid` | Message stub label |
| `orders.events` | Message destination |

## 10. Step 7 — Build the Consumer Event Model

In `shipping-service`, define the DTO:

~~~java
package com.example.shipping;

import java.math.BigDecimal;

public record OrderPaidEvent(
    String eventId,
    String eventType,
    String orderId,
    BigDecimal amount,
    String currency
) {}
~~~

The consumer DTO should reflect the payload the consumer needs to process. You do not need to copy every Java class from the producer; **communication rests on the message schema**, not on sharing internal domain classes.

### Checking Schema Assumptions

The consumer may need:

- `eventId` for deduplication.
- `eventType` for business routing.
- `orderId` to create the shipment.
- `amount` and `currency` if shipping logic checks order value.
- Correlation/tracing headers if required by the system.

If the consumer does not use a field, do not create an artificial business dependency on it just because it exists in a DTO.

## 11. Step 8 — Write Consumer Service and Idempotency

A consumer should process messages with business logic, for example:

~~~java
package com.example.shipping;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ShippingService {

    private final ShipmentRepository shipmentRepository;

    public ShippingService(ShipmentRepository shipmentRepository) {
        this.shipmentRepository = shipmentRepository;
    }

    @Transactional
    public void handleOrderPaid(OrderPaidEvent event) {
        if (!"ORDER_PAID".equals(event.eventType())) {
            throw new IllegalArgumentException("Unexpected event type");
        }

        if (shipmentRepository.existsByEventId(event.eventId())) {
            return;
        }

        Shipment shipment = Shipment.readyForPickup(
            event.eventId(),
            event.orderId(),
            event.amount(),
            event.currency()
        );

        shipmentRepository.save(shipment);
    }
}
~~~

`ShipmentRepository` must support `existsByEventId` and persisting shipments. In production, idempotency should be enforced by an appropriate **unique constraint / transaction strategy** to prevent race conditions when duplicate events arrive concurrently.

### Why Does Idempotency Belong in This Project?

Message delivery can repeat depending on broker, retry, and failure windows. The consumer must not create two shipments simply because the same event is redelivered. Contract tests verify the consumer handles the payload, while idempotency must be demonstrated in **consumer code and assertions**.

## 12. Step 9 — Connect the Consumer via Spring Cloud Stream

Declare a functional consumer:

~~~java
package com.example.shipping;

import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderPaidConsumer {

    @Bean
    Consumer<OrderPaidEvent> orderPaid(ShippingService shippingService) {
        return shippingService::handleOrderPaid;
    }
}
~~~

Configure the binding:

~~~yaml
spring:
  cloud:
    function:
      definition: orderPaid
    stream:
      bindings:
        orderPaid-in-0:
          destination: orders.events
          content-type: application/json
~~~

Spring Cloud Stream maps function definition `orderPaid` to input binding `orderPaid-in-0` by functional binding convention. The destination must match the logical destination in the contract.

### Test Profile

In consumer contract tests, configure a binder so stub messages flow into the binding without a production broker. When using Spring Cloud Stream, test binder and message verifier dependencies must match your chosen Spring Cloud Contract and Stream versions.

Never point to a live production Kafka or RabbitMQ cluster just to run stub tests when your goal is testing handler logic in isolation.

## 13. Step 10 — Write the Consumer Contract Test with Stub Runner

This is the core of the project.

~~~java
package com.example.shipping;

import java.time.Duration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubTrigger;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example.orders:order-service:2.5.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class OrderPaidConsumerContractTest {

    @Autowired
    private StubTrigger stubTrigger;

    @Autowired
    private ShipmentRepository shipmentRepository;

    @BeforeEach
    void cleanTestData() {
        shipmentRepository.deleteAll();
    }

    @Test
    void createsShipmentWhenOrderPaidStubIsTriggered() {
        boolean triggered = stubTrigger.trigger("order_paid");

        assertThat(triggered).isTrue();

        await()
            .atMost(Duration.ofSeconds(5))
            .untilAsserted(() ->
                assertThat(
                    shipmentRepository.findByOrderId("ORD-1001")
                ).isPresent()
            );

        Shipment shipment =
            shipmentRepository.findByOrderId("ORD-1001").orElseThrow();

        assertThat(shipment.getStatus()).isEqualTo("READY_FOR_PICKUP");
        assertThat(shipment.getEventId())
            .isEqualTo("EVT-ORD-1001-PAID");
    }
}
~~~

This example assumes:

- The consumer uses Spring Cloud Stream functional bindings and a compatible message verifier / test binder.
- The repository is an isolated test repository or test database.
- Stub artifact `order-service:2.5.0:stubs` is installed in the local Maven repository.
- Label `order_paid` matches the label in the producer contract.
- Consumer handlers process messages asynchronously, so Awaitility is used with a bounded timeout.

Package names, APIs, and messaging settings may require adjustments for your release train. Verify against generated tests and the actual integration adapter.

### Reading the Test Step by Step

1. `@SpringBootTest` starts Shipping Service.
2. `@AutoConfigureStubRunner` downloads Order Service's stub artifact.
3. `StubTrigger` is injected.
4. `trigger("order_paid")` instructs Stub Runner to emit the message with that label.
5. The message routes to destination `orders.events`.
6. Spring Cloud Stream binding `orderPaid-in-0` passes the message to function `orderPaid`.
7. The function invokes `ShippingService.handleOrderPaid`.
8. The repository persists the shipment.
9. Assertions verify the persisted status and event ID.

**`assertThat(triggered).isTrue()` only confirms the stub fired per the StubTrigger API. It does not replace business assertions against the repository.**

## 14. Producer `triggeredBy` vs. Consumer `StubTrigger`

These two mechanisms are often confused:

| Mechanism | Side where it runs | Purpose |
| --- | --- | --- |
| `input.triggeredBy: markOrderAsPaid()` | Producer generated test | Calls application service so producer emits a real message verified by verifier |
| `StubTrigger.trigger("order_paid")` | Consumer test | Emits sample message from stub artifact for consumer processing |

~~~mermaid
flowchart TD
    A["Producer contract input.triggeredBy"] --> B["OrderMessageContractBase"]
    B --> C["OrderApplicationService"]
    C --> D["Real publisher + test message verifier"]
    D --> E["Producer output verified"]
    F["Consumer StubTrigger.trigger(label)"] --> G["Message stub in artifact"]
    G --> H["Destination orders.events"]
    H --> I["Shipping consumer code"]
    I --> J["Shipment repository assertions"]
~~~

If a producer generated test only called `StubTrigger`, it would not prove the producer emits events. If a consumer test called `ShippingService.handleOrderPaid` directly, it would not prove the message stub can trigger the binding and deliver the payload to the consumer.

**The project needs both lines of evidence** to verify the producer contract and consumer integration.

## 15. Step 11 — Testing Idempotency by Triggering Repeatedly

You can add a test:

~~~java
@Test
void duplicateOrderPaidMessageDoesNotCreateDuplicateShipment() {
    assertThat(stubTrigger.trigger("order_paid")).isTrue();
    assertThat(stubTrigger.trigger("order_paid")).isTrue();

    await()
        .atMost(Duration.ofSeconds(5))
        .untilAsserted(() ->
            assertThat(
                shipmentRepository.findAllByOrderId("ORD-1001")
            ).hasSize(1)
        );
}
~~~

This test assumes the same stub label can be triggered multiple times and the consumer handles repeated event IDs. If your message verifier/binder or test setup does not support triggering repeatedly this way, use an appropriate integration test that delivers the same payload twice.

### What Must Be Proven

- Identical `eventId` does not create a second shipment.
- Existing records retain valid state.
- The handler does not corrupt data on retries.
- Unique constraints / transaction handling protect concurrent executions.

A unit test calling the handler twice directly is a useful supplement, yet **the StubTrigger test** is still needed to cover the messaging path.

## 16. Step 12 — Testing Consumer Behavior, Not Just DTO Mapping

A weak consumer test:

~~~java
assertThat(stubTrigger.trigger("order_paid")).isTrue();
~~~

That test only verifies the label can be triggered. It does not prove:

- The consumer function received the message.
- JSON deserialized into `OrderPaidEvent`.
- The handler executed.
- The shipment persisted accurately.
- The event ID was handled idempotently.
- The consumer did not drop or misinterpret the event type.

A thorough consumer test verifies **observable outcomes** of consumer code—such as repository state, outgoing commands, status transitions, or downstream domain events.

### Assertions by Business Outcome

| Assertion | Value |
| --- | --- |
| Trigger returns `true` | Stub label fired |
| Shipment exists | Consumer handler created the record |
| Shipment order ID matches | Payload field read accurately |
| Event ID matches | Message metadata/payload processed properly |
| Status matches | Consumer business logic executed properly |
| Duplicate creates no second record | Idempotency behavior protected |

If handlers execute asynchronously, use Awaitility or adapter-appropriate synchronization; avoid fixed `Thread.sleep` calls.

## 17. Step 13 — Configuring the Test Application

An illustrative `application-test.yml`:

~~~yaml
spring:
  cloud:
    function:
      definition: orderPaid
    stream:
      bindings:
        orderPaid-in-0:
          destination: orders.events
          content-type: application/json
~~~

The test binder dependency is already declared in the consumer module. Automatic binder and message verifier selection can depend on versions, test configuration, and other binder dependencies on the classpath.

### Profile Checklist

- Tests do not connect to a production broker.
- Destination is `orders.events`.
- Consumer function definition is `orderPaid`.
- Input binding is `orderPaid-in-0`.
- Message content type is JSON.
- No other active profile overrides the binding destination.
- No shared consumer group/topic causes unintended side effects.

If multiple binders are present, bind a specific binder per binding or test profile so Stub Runner messages reach the intended adapter.

## 18. Step 14 — Running the Full Lab in Order

Assume both modules exist under the `messaging-contract-lab` root.

### Run the Producer

Inside `order-service`:

~~~bash
./mvnw clean verify
./mvnw clean install
~~~

The first command generates and executes producer contract tests. The second runs the lifecycle installing the artifact into the local repository; depending on plugin configuration, tests will also run again.

Afterward, inspect the stub artifact `order-service-2.5.0-stubs.jar` in your local Maven repository.

### Run the Consumer

Inside `shipping-service`:

~~~bash
./mvnw clean test
~~~

Stub Runner in `StubsMode.LOCAL` resolves the installed artifact. The consumer test triggers `order_paid` and verifies the shipment is created.

### If Using a Remote Artifact Repository

When publishing to a shared Maven repository:

- Publish the artifact to the internal repository via a privileged release pipeline.
- Switch consumer Stub Runner to `StubsMode.REMOTE`.
- Configure `repositoryRoot` and credentials via a secret store.
- Never embed usernames or passwords in source code or test reports.
- Record GAV, repository, and checksum of the resolved artifact.

Do not use `REMOTE` before publishing the artifact; do not use `LOCAL` in CI unless the local Maven repository was explicitly populated beforehand.

## 19. Expected Outcomes

<badge color="success">Target Outcome</badge>

| Step | Result |
| --- | --- |
| Producer contract discovery | Found `order-paid.yml` |
| Generated producer test | Generated and executed |
| Producer trigger | `markOrderAsPaid()` invoked |
| Producer message verification | Destination/header/body PASS |
| Stub packaging | `order-service:2.5.0:stubs` produced |
| Consumer Stub Runner | Exact artifact resolved |
| Stub trigger | `trigger("order_paid")` returned `true` |
| Consumer message handler | Received and processed event |
| Business assertion | Shipment `ORD-1001` created |
| Idempotency test | Repeated triggers create no duplicate shipment |

These are **target outcomes for the exercise**, not a claim that the sample project was built in this workspace.

## 20. Troubleshooting the Project

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Producer generated test cannot find `markOrderAsPaid()` | Wrong base class mapping or method visibility/name | Inspect generated test and plugin config |
| Producer test PASSES with no message | Publisher not called or verifier missed output | Inspect application service, binder, and message verifier |
| Producer test cannot find destination | `sentTo` differs from output binding destination | Compare contract and `StreamBridge`/binding config |
| Stub JAR missing | Packaging goal not executed or producer build not installed | Check Maven plugin logs and attached artifacts |
| Consumer fails to resolve stub | Wrong GAV/version/classifier or not installed/published | Check local/remote repository |
| `StubTrigger` returns `false` | Label missing or stub lacks message label | Compare contract `label` with artifact contents |
| Trigger succeeds but consumer misses message | Destination/binder/binding mismatch | Inspect message verifier, binding, and test binder |
| Consumer receives message but JSON conversion fails | Content-type header / serializer / DTO mismatch | Inspect message headers and payload types |
| Shipment never appears | Handler not invoked or business validation failed | Check consumer logs and repository state |
| Consumer test times out | Async processing, binder, or handler error | Check logs, timeout, and binding lifecycle |
| Two shipments created | Missing idempotency / unique constraint | Check event ID and transaction strategy |
| Passes locally, FAILS in CI | Different dependency versions, artifact cache, or binder config | Record resolved versions and stub checksum |

### Distinguishing Trigger Failure from Handler Failure

- If `stubTrigger.trigger(label)` returns `false`, check the **stub artifact and label** first.
- If the trigger returns `true` but no shipment appears, check **destination, binding, deserialization, and consumer handler**.
- If a shipment is created with wrong data, check **payload schema and business mapping**.

Never modify consumer code to mask a stale stub artifact or mismatched label.

## 21. Inspecting Stub Artifact Contents

When a consumer cannot find a label or message, confirm the producer packaged the right artifact.

Check:

1. Do `groupId`, `artifactId`, `version`, and `classifier` match?
2. Does the contract revision match what the producer verified?
3. Does the stub JAR contain the message mappings/resources?
4. Is label `order_paid` present in stub metadata?
5. Is destination `orders.events` correct?
6. Is the consumer resolving the exact artifact rather than a stale cache?

A release record should log:

~~~yaml
producer:
  service: order-service
  version: "2.5.0"
  sourceCommit: "ACTUAL_PRODUCER_COMMIT"
contract:
  path: "contracts/orders/order-paid.yml"
  revision: "ACTUAL_CONTRACT_REVISION"
stub:
  coordinate: "com.example.orders:order-service:2.5.0:stubs"
  sha256: "CI_COMPUTED_CHECKSUM"
consumer:
  service: shipping-service
  version: "1.4.0"
  resolvedStub: "com.example.orders:order-service:2.5.0:stubs"
~~~

Commit and checksum values are placeholders. CI must extract them from real sources and artifact files.

## 22. Extending the Lab: Event Versioning and Consumer Validation

Extend the contract with a field:

~~~yaml
body:
  eventId: EVT-ORD-1001-PAID
  eventType: ORDER_PAID
  schemaVersion: 1
  orderId: ORD-1001
  amount: 125000
  currency: VND
~~~

The consumer DTO adds `schemaVersion` and checks:

- Is the version in the set supported by the consumer?
- Is the event type `ORDER_PAID`?
- Is the amount valid and currency supported?
- How does a missing field differ from an explicit null?
- Do older consumers ignore new fields or fail under strict deserialization?

**Adding fields to an event is not automatically backward-compatible.** Older consumers with strict parsers may reject unknown properties. Test supported consumer versions against the new stub.

## 23. Extending the Lab: Negative Cases and Invalid Events

You can write unit tests for `ShippingService`:

~~~java
@Test
void rejectsUnexpectedEventType() {
    OrderPaidEvent event = new OrderPaidEvent(
        "EVT-1001",
        "ORDER_CANCELLED",
        "ORD-1001",
        new BigDecimal("125000"),
        "VND"
    );

    assertThatThrownBy(() ->
        shippingService.handleOrderPaid(event)
    ).isInstanceOf(IllegalArgumentException.class);
}
~~~

This test verifies business validation directly. To verify end-to-end messaging, define a matching contract/stub scenario for that event or add a message adapter integration test.

Do not take a valid message stub and mutate the event inside consumer assertions; create separate fixtures and scenarios so tests stay clear and reproducible.

## 24. Extending the Lab: Correlation and Tracing Headers

When a system requires correlation IDs, the contract can add:

~~~yaml
outputMessage:
  sentTo: orders.events
  headers:
    contentType: application/json
    correlationId: CORR-ORD-1001
  body:
    eventId: EVT-ORD-1001-PAID
    eventType: ORDER_PAID
    orderId: ORD-1001
    amount: 125000
    currency: VND
~~~

Consumers can use headers for tracing/logging, while distinguishing:

- **Message headers** propagated by the adapter.
- **Payload fields** carried inside the body.
- **Trace context** potentially created/propagated by instrumentation frameworks.

Do not assume a contract header automatically populates MDC or trace spans. If that is an acceptance criterion, write the appropriate consumer or observability tests.

## 25. CI Integration for Both Producer and Consumer

~~~mermaid
flowchart TD
    A["Commit contract + producer code"] --> B["Producer CI"]
    B --> C["Generated message contract tests"]
    C --> D{"Producer output PASS?"}
    D -->|No| X["BLOCK"]
    D -->|Yes| E["Package stub artifact"]
    E --> F["GAV + checksum + provenance"]
    F --> G["Publish/Install stub"]
    G --> H["Consumer CI resolves exact stub"]
    H --> I["StubTrigger fires message"]
    I --> J["Consumer handler + business assertions"]
    J --> K{"Required consumer tests PASS?"}
    K -->|No| X
    K -->|Yes| L["Release evidence"]
~~~

### Producer CI Gate

- Contract file is discovered.
- Generated producer tests are produced and executed.
- `triggeredBy` invokes the real application service.
- Message destination, headers, and body match.
- No mandatory tests are skipped.
- Stub artifact is built from the exact contract revision.
- Artifact checksum and provenance are recorded.

### Consumer CI Gate

- Stub Runner resolves the exact GAV/classifier/version.
- Message label is found.
- `StubTrigger` emits the message through the test adapter.
- Consumer binding receives the message.
- Handler establishes the expected business state.
- Negative and idempotency tests PASS.
- Logs do not leak secrets or sensitive data.

### Never Treat Both Gates as One

Producer CI PASSING does not prove consumer code was tested. Consumer tests PASSING against an old stub do not prove a new producer is compatible. Both require **the exact same contract revision and stub artifact identity**.

## 26. Project Acceptance Criteria

| ID | Criterion | Evidence |
| --- | --- | --- |
| AC-01 | Message contract has clear label and destination | `order-paid.yml` |
| AC-02 | Producer test triggers real service via `triggeredBy` | Generated source / test report |
| AC-03 | Producer sends message to expected destination | Message verifier report |
| AC-04 | Headers and body match contract | Producer contract assertions |
| AC-05 | Stub artifact carries `stubs` classifier | GAV and JAR |
| AC-06 | Consumer downloads exact artifact | Stub Runner resolved ID/version |
| AC-07 | `StubTrigger` fires label `order_paid` | Trigger result |
| AC-08 | Consumer function receives JSON payload | Handler execution / evidence |
| AC-09 | Shipment created with expected order/status | Repository assertions |
| AC-10 | Duplicate event creates no duplicate shipment | Idempotency test |
| AC-11 | Producer and consumer reports link to exact revisions | CI metadata |
| AC-12 | No production broker or credentials used in contract tests | Test environment configuration |

**AC-07 does not replace AC-08/AC-09.** A successful trigger does not mean the consumer processed the message properly.

## 27. Extended Exercises

### Exercise A — Mismatched Message Label

Contract defines `label: order_paid`, but the test calls `stubTrigger.trigger("paid_order")`.

**Task:** predict the outcome and explain how to inspect the artifact.

**Hint:** labels must match; inspect which labels exist in the stub artifact and use the exact name.

### Exercise B — Mismatched Destination

Contract sends to `orders.events`, while the consumer binding listens on `order.events`.

**Task:** why can the trigger succeed while no shipment is created?

**Hint:** the stub fires, but the message routes to a destination other than the consumer's binding; compare `sentTo` with the binding destination.

### Exercise C — Producer Trigger Sends Only a Hardcoded Payload

The base test calls the publisher directly with sample JSON, bypassing the application service.

**Task:** what does the producer test still prove, and what does it miss?

**Hint:** it only proves the publisher path; it fails to test the state-transition logic and the decision to emit the event.

### Exercise D — Consumer Calls Service Directly

A consumer integration test calls `shippingService.handleOrderPaid(event)` instead of `StubTrigger`.

**Task:** does this test prove Stub Runner message delivery?

**Hint:** no; that is a service/unit test. Keep it as supplemental coverage and add a `StubTrigger` integration test.

### Exercise E — Number vs. String in Message Body

Contract specifies `amount` as a number, but the consumer DTO defines `String`.

**Task:** where should you investigate?

**Hint:** raw message payload, serializer/content type, DTO types, and coercion rules; never loosen contracts arbitrarily.

### Exercise F — Duplicate Events

Triggering the same label twice creates two shipments.

**Task:** propose how to enforce idempotency.

**Hint:** event ID, unique constraint, transaction/atomic insert, and duplicate-delivery tests.

### Exercise G — Consumer Receives Nothing Due to Test Binder

`StubTrigger` returns `true`, yet the binding never initializes.

**Task:** what should you inspect?

**Hint:** binder dependencies, function definition, binding name, destination, and message verifier adapter.

### Exercise H — Stale Stub

Consumer tests PASS against Order Service 2.4.0 while the producer prepares to release 2.5.0.

**Task:** what must change before declaring compatibility?

**Hint:** producer verifies 2.5.0 and packages/publishes the exact stub; consumer resolves 2.5.0 and re-runs.

### Exercise I — Production Broker Misconfigured in Tests

A test profile accidentally reads Kafka bootstrap servers from a shared environment.

**Task:** how do you mitigate this risk?

**Hint:** use the test binder or an isolated test broker, test-only credentials, egress restrictions, and fail-fast config validation.

### Exercise J — Adding `schemaVersion`

Producer adds `schemaVersion: 2`, while an older consumer uses a strict JSON deserializer.

**Task:** can an additive change be breaking? Which versions must be tested?

**Hint:** it can be breaking; run supported consumer versions against the new stub and establish a migration strategy.

## 28. Lab Completion Checklist

### Contract and Producer

- [ ] `order-paid.yml` defines `label: order_paid`.
- [ ] `outputMessage.sentTo` is `orders.events`.
- [ ] Header content type is JSON.
- [ ] Body fields and types are unambiguous.
- [ ] `triggeredBy` calls the right base test method.
- [ ] Base test seeds fixtures in an isolated environment.
- [ ] Real producer application service performs the state transition and publishes the event.
- [ ] Generated producer message test is generated and PASSES.
- [ ] Producer test verifies destination, headers, and payload.
- [ ] No mandatory generated tests are skipped.

### Stub Artifact

- [ ] Stub JAR is packaged.
- [ ] Classifier is `stubs`.
- [ ] GAV/version matches the producer release.
- [ ] Artifact contains the right message stub and label.
- [ ] Contract revision, producer commit, and checksum are recorded.
- [ ] Consumer tests use the exact artifact, not a stale cache or older version.

### Consumer

- [ ] `StubTrigger` is injected from Stub Runner.
- [ ] `trigger("order_paid")` returns `true`.
- [ ] Consumer binding listens on `orders.events`.
- [ ] JSON deserializes into the right DTO.
- [ ] Business handler executes.
- [ ] Shipment is created with the expected order ID, event ID, and status.
- [ ] Duplicate events are handled idempotently.
- [ ] Consumer tests verify business outcomes, not just the trigger result.
- [ ] Service methods are not called directly in place of the messaging path in integration tests.

### CI and Safety

- [ ] Boot/Cloud/Contract plugin versions are a verified compatible set.
- [ ] Test binder/broker is properly configured with no production destinations.
- [ ] Async assertions use bounded timeouts.
- [ ] Test data and cleanup are properly scoped.
- [ ] No secrets or PII are logged.
- [ ] Producer and consumer reports are traceable.
- [ ] Release gate distinguishes producer verification from consumer verification.
- [ ] Limitations of the test binder relative to a real broker are documented.

## Conclusion

The **Triggering Messaging Stubs and Verifying Consumer Code** project is complete when both sides hold independent evidence linked by a single message contract. On the producer side, generated tests use `triggeredBy` to execute the application service and verify that real messages reach the right destination with valid headers and body. On the consumer side, Stub Runner downloads the stub artifact, `StubTrigger` fires the message by label, the message traverses the binding into consumer code, and assertions verify **the shipment is genuinely created and duplicate deliveries are handled safely**.

**Remember:** *Producer `triggeredBy` verifies the producer emits the message; consumer `StubTrigger` fires the stub message; business assertions prove the consumer handles it properly. Do not stop merely because the stub triggered successfully.*
