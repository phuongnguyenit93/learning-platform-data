# Distinguishing Listener Unit Tests from Integration Through a Real Broker

In the **Messaging** group of the **Spring Boot - testing** module, a listener may work very well when invoked directly using JUnit/Mockito yet still fail when running through RabbitMQ, Kafka, or a real message broker. The reason is that **calling a Java method does not mean a message has passed through an exchange/topic, queue/partition, serialization, listener container, acknowledgement, retry, and dead-letter handling**.

This lesson distinguishes between two questions:

1. **Listener unit test:** When receiving a specific payload or domain event, does the listener code decode, validate the data, call the right collaborator, and handle errors as expected? This is a test that **does not start a Spring ApplicationContext or a broker** if the listener is designed with separation of concerns.
2. **Integration test through a real broker:** When the producer publishes a message via Spring APIs, does the broker route it to the expected queue/topic, does the listener container actually consume it, does the converter work, are failing messages rejected/requeued/dead-lettered, and are side effects observable? This is a test using a **real broker**, for example RabbitMQ via Testcontainers.

The main example uses **Java 17+, Spring Boot 3.5.x, Spring AMQP, RabbitMQ, and Testcontainers 1.x, JUnit Jupiter, Mockito**. The code sections contain all files needed to create a sample project; integration tests require Docker and a RabbitMQ image. A standalone Java SE program run with `javac/java` demonstrates the codec before putting it into the listener. Important notes for **Kafka**, Spring Cloud Stream, and other message brokers are presented separately, because their offset/ack/partition mechanics **must not be equated with RabbitMQ**.

## 1. Why do listener unit tests often pass falsely?

Consider the common structure:

```text
Producer / HTTP service
         |
         v
RabbitTemplate.convertAndSend(...)
         |
         v
RabbitMQ exchange + routing key
         |
         v
RabbitMQ queue
         |
         v
Spring AMQP listener container
         |
         v
Message conversion -> @RabbitListener
         |
         v
Business handler -> DB/API/side effects
         |
         v
ACK or reject/nack -> retry/DLQ
```

A unit test only does:

```java
OrderQueueListener listener =
        new OrderQueueListener(mockHandler);
listener.accept("ORD-7|2");
verify(mockHandler).handle(
        new OrderCreated("ORD-7", 2));
```

It can prove the logic of `accept(...)` and dependency interaction, **but it does not verify**:

- Whether the RabbitMQ server is running and whether the application can connect to it.
- Whether the exchange, queue, binding, and routing key are correct.
- Whether the consumer is subscribed to the right queue; whether `@RabbitListener` is discovered by Spring.
- Whether the payload is serialized by `RabbitTemplate` with appropriate headers/content-type.
- How the listener container handles exceptions, acknowledgement, redelivery, or dead-lettering.
- Multiple consumers/threads, message ordering, duplicate delivery, and transaction/offset semantics.
- If a request is published with no matching route, whether the broker drops/returns it.
- Whether the consumer's DB transaction commits/rolls back; whether HTTP, cache, or event side effects are handled safely.

In return, unit tests are **very fast, deterministic, and require no Docker**, making it easy to pinpoint which line a business bug is on. The goal is not to replace unit tests with all integration tests; the goal is to **combine the right test levels to protect different boundaries**.

## 2. Comparison table: direct call vs. real broker

| Criterion | Listener unit test (JUnit/Mockito) | Integration test with a real broker |
| --- | --- | --- |
| Broker startup | No | **Yes** |
| Spring context | Usually no | Usually yes, to verify wiring |
| Listener method | Called directly | Invoked by the listener container |
| Serialization/converter | Tested only if explicitly called | Tests the actual publish → consume path |
| Exchange/queue/routing | No | **Can be verified** |
| Header/content-type | Not by default | Can be verified if specifically asserted |
| ACK/NACK/requeue | No | Can be verified through broker behavior |
| Retry/DLQ | No | Can be verified using failing messages and DLQ |
| Concurrency/timing | Usually synchronous | **Asynchronous**, requires bounded waiting |
| Database commit | No, if only mocking the handler | Only when a real DB is set up and asserted |
| Code failure diagnosis | Very fast | Additional Docker/broker/network causes |
| Speed | Fast | Slower due to startup/transport |
| CI requires Docker | No | Yes, if using Testcontainers |
| Purpose | Method logic and contract | Broker + listener stack integration |

**Rule:** use unit tests for parsing/validation/delegation/error propagation; use integration tests for routing, delivery, converters, failure policies, and actual configuration. If the goal is to verify the DB after the listener processes a message, the integration test also needs a **real DB** or an appropriate persistent side-effect verification; a real broker alone is not enough.

## 3. Choosing RabbitMQ for the example; do not apply mechanically to Kafka

In RabbitMQ/AMQP 0-9-1, the illustrative model is:

```text
Publisher --(exchange + routing key)--> Exchange
                                             |
                                    Binding route
                                             v
                                           Queue
                                             |
                                             v
                                         Consumer
                                             |
                              success: ACK / failure: reject
                                             |
                                     optional Dead Letter Exchange
```

In Apache Kafka, the publisher writes **records to a topic/partition**, and a consumer group reads by offset. There is no exchange + queue + routing-key like RabbitMQ. Kafka uses **offset commit**, rebalancing, partition assignment, and error handling via the Spring Kafka container; you cannot simply swap `@RabbitListener` for `@KafkaListener` and keep the same ACK/DLX tests.

Even under the same "listener unit test vs broker integration" topic, **assertions must follow the protocol**:

| Aspect | RabbitMQ | Kafka |
| --- | --- | --- |
| Message route | Exchange, binding, routing key, queue | Topic, key, partition |
| Consumption | Queue consumers | Consumer group, assigned partitions |
| Progress confirmation | ACK/NACK/requeue | Offset commit/seek/retry strategies |
| Failure | Reject/requeue, dead-letter exchange/queue | Retry topic/DLT or error handler; depends on configuration |
| Ordering | Affected by queue/consumer/prefetch/concurrency | Ordered within one partition, not across the entire topic |
| Integration test | `RabbitMQContainer` | Kafka broker container/embedded broker depending on version |

The full example chooses RabbitMQ because an **exchange → queue → consumer** path and a **dead-letter queue** can be clearly observed; the principles of test levels, async waiting, and idempotency still apply to Kafka, though the configuration and code differ.

## 4. Designing a testable listener

Split into three small layers:

```text
raw wire payload
       |
       v
OrderEventCodec.decode(...)
       |
       v
OrderCreated (domain event)
       |
       v
OrderQueueListener.accept(...)
       |
       v
OrderEventHandler.handle(...)
       |
       v
side effect / persistence
```

As a result:

- `OrderEventCodec` is plain Java; testing it requires no Spring.
- `OrderQueueListener` only coordinates decoding and the handler; unit tests pass a Mockito mock into the constructor.
- `OrderEventHandler` is a port; the production implementation can write to a DB, call a service, or emit a domain event.
- Integration tests send messages through a real RabbitMQ broker, using a real handler and a thread-safe signal to observe that the message has been processed by the consumer.

**Test design note:** the handler storing events in memory is only to provide an observable signal when testing the broker. It **does not prove a database commit**; if the production handler writes to Postgres, a separate test with PostgreSQL and corresponding transactions is needed.

### Minimal payload contract

To focus on the broker, the example's wire format is:

```text
ORD-7|2
```

This means orderId `ORD-7` and quantity 2, separated by the `|` character. This is a **demo contract**, not a production message serialization standard. When running a real system, you should generally use JSON/Avro/Protobuf/CloudEvents along with schema versioning, content-type, backward compatibility, and separate converter tests.

With a simple format, important aspects can still be tested: parse errors, out-of-range quantity, exception propagation, message delivery through a queue, and DLQ routing. Payload validation is one layer; broker/message headers/converters are other layers.

## 5. Java 17 / Spring Boot 3.5 project structure

Files to create:

```text
src/
├── main/java/example/messaging/
│   ├── MessagingApplication.java
│   ├── OrderCreated.java
│   ├── OrderEventCodec.java
│   ├── OrderEventHandler.java
│   ├── InMemoryOrderHandler.java
│   ├── OrderQueueListener.java
│   ├── RabbitTopology.java
│   └── OrderCodecDemo.java
└── test/java/example/messaging/
    ├── OrderQueueListenerUnitTest.java
    ├── OrderEventCodecTest.java
    └── RabbitBrokerIntegrationTest.java
```

All Java classes share the `example.messaging` package. Placing the application in this root package lets Spring Boot component scanning find the listener, handler, and topology.

### 5.1. Gradle dependencies

In a project generated with Spring Initializr (which already has the Spring Boot Gradle plugin, repositories, BOM, and Java 17+ toolchain), the relevant section in `build.gradle` is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:rabbitmq'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **dependency configuration snippet** for Spring Boot **3.5.x / Testcontainers 1.21.x**, not a complete standalone build file. `spring-boot-starter-test` provides JUnit Jupiter/Mockito; `spring-boot-testcontainers` supports `@ServiceConnection`. The artifact `org.testcontainers:rabbitmq` and import `org.testcontainers.containers.RabbitMQContainer` are the **Testcontainers 1.x** usage. With Testcontainers 2.x, the module may change to `org.testcontainers:testcontainers-rabbitmq` and different packages; you must check the right BOM and not mix two major versions.

**Environment requirements:** Docker or a container runtime recognized by Testcontainers; permission to pull/run the `rabbitmq:4.1-management-alpine` image; sufficient CPU/RAM and network for the broker to start. Unit tests do not require Docker, while integration tests do. Do not connect to a production broker or use production credentials in tests.

### 5.2. MessagingApplication.java

Create `src/main/java/example/messaging/MessagingApplication.java`:

```java
package example.messaging;

import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@EnableRabbit
public class MessagingApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                MessagingApplication.class, args);
    }
}
```

`@EnableRabbit` registers the infrastructure for `@RabbitListener` methods. Spring Boot auto-configures `ConnectionFactory`, `RabbitTemplate`, and the listener container factory from the starter/properties when appropriate. It is used explicitly in the example so learners clearly see that a listener annotation is not just an ordinary Java method.

**No need to start an HTTP server**: the example focuses on messaging, and the integration test uses `webEnvironment=NONE`.

## 6. Domain event and plain Java codec

### 6.1. OrderCreated.java

Create `src/main/java/example/messaging/OrderCreated.java`:

```java
package example.messaging;

public record OrderCreated(
        String orderId,
        int quantity) {
}
```

This immutable record is the domain message after parsing. Unit tests can compare records using Java's auto-generated `equals`. Do not confuse it with a RabbitMQ envelope: this record does not carry a delivery tag, exchange, routing key, message headers, or acknowledgement metadata.

### 6.2. OrderEventCodec.java

Create `src/main/java/example/messaging/OrderEventCodec.java`:

```java
package example.messaging;

import java.util.Objects;

public final class OrderEventCodec {
    private OrderEventCodec() {
    }

    public static OrderCreated decode(String payload) {
        if (payload == null || payload.length() > 100) {
            throw new IllegalArgumentException(
                    "invalid event format");
        }

        String[] fields = payload.split("\\|", -1);

        if (fields.length != 2
                || !fields[0].matches(
                        "ORD-[A-Za-z0-9-]{1,64}")) {
            throw new IllegalArgumentException(
                    "invalid event format");
        }

        final int quantity;
        try {
            quantity = Integer.parseInt(fields[1]);
        } catch (NumberFormatException error) {
            throw new IllegalArgumentException(
                    "invalid quantity", error);
        }

        if (quantity < 1 || quantity > 100) {
            throw new IllegalArgumentException(
                    "invalid quantity");
        }

        return new OrderCreated(fields[0], quantity);
    }

    public static String encode(OrderCreated event) {
        Objects.requireNonNull(event, "event");

        String payload =
                event.orderId() + "|" + event.quantity();

        // Use the same rule so we do not create a message
        // that our consumer would reject.
        decode(payload);
        return payload;
    }
}
```

The code makes explicit decisions:

- Exactly two fields separated by `|`.
- `orderId` follows the `ORD-...` allowlist, without pipes, whitespace, or excessive length.
- Quantity is an integer in **[1,100]**.
- Exceptions do not include the raw payload, helping avoid accidentally logging sensitive data when handling failing messages.
- `encode` uses the same rule so the demo producer does not emit invalid payloads.

**In production:** if an event has many fields, versions, decimal types, Unicode, and optional fields, use a managed schema/JSON serializer rather than growing an ad-hoc custom pipe-delimited protocol. Test charset, content-type, backward compatibility, and the difference between missing, null, and blank.

### 6.3. How are codec unit tests useful?

Codec tests enforce the **payload contract**, without needing RabbitMQ:

- Valid input returns the corresponding `OrderCreated`.
- Quantity 0/101 is rejected.
- Non-numeric quantity is rejected.
- Malformed payload is rejected.

A `listener.accept("ORD-7|2")` test does not by itself prove that actual AMQP bytes convert properly into a String. Therefore, unit codec tests and integration wire tests **complement each other**.

## 7. Business port and observable implementation

### 7.1. OrderEventHandler.java

Create `src/main/java/example/messaging/OrderEventHandler.java`:

```java
package example.messaging;

public interface OrderEventHandler {
    void handle(OrderCreated event);
}
```

### 7.2. InMemoryOrderHandler.java

Create `src/main/java/example/messaging/InMemoryOrderHandler.java`:

```java
package example.messaging;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.stereotype.Service;

@Service
public class InMemoryOrderHandler
        implements OrderEventHandler {

    private final ConcurrentMap<String,
            CompletableFuture<OrderCreated>> received =
            new ConcurrentHashMap<>();

    private final ConcurrentMap<String, Integer> processed =
            new ConcurrentHashMap<>();

    @Override
    public void handle(OrderCreated event) {
        processed.merge(event.orderId(), 1, Integer::sum);

        received.computeIfAbsent(
                event.orderId(),
                ignored -> new CompletableFuture<>())
                .complete(event);
    }

    public CompletableFuture<OrderCreated> watch(
            String orderId) {
        return received.computeIfAbsent(
                orderId,
                ignored -> new CompletableFuture<>());
    }

    public int processedTimes(String orderId) {
        return processed.getOrDefault(orderId, 0);
    }
}
```

This is a **real handler**, though its side effect is only in an in-process concurrent map. The integration test uses `watch(id).get(timeout)` to wait for the signal when the listener processes the event, avoiding `Thread.sleep(...)`. `processedTimes(id)` provides the processing count within one JVM.

**Very important limitation:** the `CompletableFuture` is completed inside the handler **before the listener method returns**, so the test observes that the event reached the handler, **not directly proving that the AMQP ACK was confirmed by the broker**. To accurately test ack/prefetch/reconnect or database commits, use appropriate assertions/lifecycles at the broker/consumer/DB layer rather than over-interpreting the watch result.

Similarly, processing an ID exactly once in a test does not prove that delivery semantics are exactly-once. RabbitMQ commonly uses **at-least-once**, where duplicate delivery can happen after a crash/redelivery. Production handlers should have idempotency keys or deduplication tested separately.

## 8. Listener: only parsing and delegation

Create `src/main/java/example/messaging/OrderQueueListener.java`:

```java
package example.messaging;

import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderQueueListener {
    private final OrderEventHandler handler;

    public OrderQueueListener(OrderEventHandler handler) {
        this.handler = handler;
    }

    @RabbitListener(queues = RabbitTopology.ORDER_QUEUE)
    public void accept(String rawPayload) {
        OrderCreated event =
                OrderEventCodec.decode(rawPayload);

        handler.handle(event);
    }
}
```

**The listener's responsibility truly consists of just two steps**: deserialize/validate `rawPayload` and then call `handler.handle`. Therefore, we can unit-test constructor injection directly without needing a Spring context.

When running with Spring AMQP:

- The `@RabbitListener` annotation is discovered by the listener endpoint infrastructure, which creates a consumer on the queue.
- The message converter turns the AMQP message body into a String according to the corresponding content-type/encoding. In the example, `RabbitTemplate.convertAndSend(..., String)` and the default `SimpleMessageConverter` handle String messages.
- If `decode` or `handler.handle` throws an exception, the exception propagates to the listener adapter/container. At that point, the **retry/requeue/DLQ configuration** (not JUnit) decides the fate of the delivery.
- Do not catch every `Exception` and merely log and return normally: with AUTO ack, returning successfully can cause the message to be ACKed even though it was not processed, leading to event loss.

**A useful rule:** use unit tests to assert that the listener does not swallow errors. Use broker integration tests to assert that real errors are handled according to broker policy.

## 9. RabbitMQ topology: exchange, queue, binding, and DLQ

Create `src/main/java/example/messaging/RabbitTopology.java`:

```java
package example.messaging;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RabbitTopology {
    public static final String ORDER_EXCHANGE =
            "lesson.orders.exchange";
    public static final String ORDER_QUEUE =
            "lesson.orders.queue";
    public static final String ORDER_ROUTING =
            "lesson.orders.created";

    public static final String DEAD_EXCHANGE =
            "lesson.orders.dlx";
    public static final String DEAD_QUEUE =
            "lesson.orders.dead";
    public static final String DEAD_ROUTING =
            "lesson.orders.failed";

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange(
                ORDER_EXCHANGE, true, false);
    }

    @Bean
    DirectExchange deadExchange() {
        return new DirectExchange(
                DEAD_EXCHANGE, true, false);
    }

    @Bean
    Queue ordersQueue() {
        return QueueBuilder.durable(ORDER_QUEUE)
                .deadLetterExchange(DEAD_EXCHANGE)
                .deadLetterRoutingKey(DEAD_ROUTING)
                .build();
    }

    @Bean
    Queue deadQueue() {
        return QueueBuilder.durable(DEAD_QUEUE).build();
    }

    @Bean
    Binding orderBinding(
            @Qualifier("ordersQueue") Queue queue,
            @Qualifier("ordersExchange") DirectExchange exchange) {
        return BindingBuilder.bind(queue)
                .to(exchange)
                .with(ORDER_ROUTING);
    }

    @Bean
    Binding deadBinding(
            @Qualifier("deadQueue") Queue queue,
            @Qualifier("deadExchange") DirectExchange exchange) {
        return BindingBuilder.bind(queue)
                .to(exchange)
                .with(DEAD_ROUTING);
    }
}
```

**Topology explanation:**

1. The producer publishes to `lesson.orders.exchange` with routing key `lesson.orders.created`.
2. The direct exchange has a binding to `lesson.orders.queue` with that exact key.
3. `@RabbitListener(queues=ORDER_QUEUE)` consumes from this queue.
4. If the listener fails and the delivery is **rejected without requeue**, RabbitMQ uses the dead-letter exchange declared on the queue to route the message to `lesson.orders.dead`.
5. The dead-letter queue **has no automatic processing listener** in the example; the test can read from it using `RabbitTemplate` to inspect it.

**Why use `@Qualifier`?** The configuration has **two Queue beans** and **two DirectExchange beans**. You cannot inject by type alone and guarantee the right queue/exchange is picked; `@Qualifier("ordersQueue")` and `@Qualifier("deadQueue")` force the bindings to point to the intended beans.

Spring AMQP has `RabbitAdmin` to declare queue/exchange/binding beans on the broker when the connection is created. With Spring Boot starter AMQP and appropriate default dynamic declaration, the topology is created on the RabbitMQ container during the integration test. If you disable dynamic declaration or change the administration policy, you must declare the topology via external infrastructure and align the test with that contract.

**Production note:** defining topology via beans is one pattern, not mandatory. Some organizations manage exchanges/queues via Terraform/Helm/an operator. In that case, integration tests must use a topology matching the target environment, especially durability, queue type, arguments, DLX, and permissions.

## 10. Listener unit test: no Spring, no RabbitMQ

Create `src/test/java/example/messaging/OrderQueueListenerUnitTest.java`:

```java
package example.messaging;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

class OrderQueueListenerUnitTest {

    @Test
    void delegatesValidEventToHandler() {
        OrderEventHandler handler =
                mock(OrderEventHandler.class);
        OrderQueueListener listener =
                new OrderQueueListener(handler);

        listener.accept("ORD-7|2");

        verify(handler).handle(
                new OrderCreated("ORD-7", 2));
    }

    @Test
    void rejectsZeroQuantityWithoutCallingHandler() {
        OrderEventHandler handler =
                mock(OrderEventHandler.class);
        OrderQueueListener listener =
                new OrderQueueListener(handler);

        assertThrows(
                IllegalArgumentException.class,
                () -> listener.accept("ORD-7|0"));

        verifyNoInteractions(handler);
    }

    @Test
    void rejectsMalformedWireMessageWithoutDelegation() {
        OrderEventHandler handler =
                mock(OrderEventHandler.class);
        OrderQueueListener listener =
                new OrderQueueListener(handler);

        assertThrows(
                IllegalArgumentException.class,
                () -> listener.accept("invalid-payload"));

        verifyNoInteractions(handler);
    }

    @Test
    void doesNotSwallowBusinessHandlerFailure() {
        OrderEventHandler handler =
                mock(OrderEventHandler.class);
        OrderQueueListener listener =
                new OrderQueueListener(handler);

        doThrow(new IllegalStateException(
                "storage unavailable"))
                .when(handler)
                .handle(new OrderCreated("ORD-9", 1));

        assertThrows(
                IllegalStateException.class,
                () -> listener.accept("ORD-9|1"));

        verify(handler).handle(
                new OrderCreated("ORD-9", 1));
    }
}
```

**Four tests run without Docker**, without starting a Spring context, and without opening any TCP port:

- `delegatesValidEventToHandler`: the parser builds the right domain record and calls the right collaborator.
- `rejectsZeroQuantityWithoutCallingHandler`: validation rejects invalid messages, and the business handler is not called.
- `rejectsMalformedWireMessageWithoutDelegation`: malformed payloads are not "guessed/fixed" and processed.
- `doesNotSwallowBusinessHandlerFailure`: the exception propagates out of the listener method so the listener container can apply its policy.

**Conclusion boundary:** the last test **does not prove** RabbitMQ reject/requeue/DLQ. It only proves the Java method throws an exception. A Mockito mock itself does not connect to a broker.

**Do not put `@SpringBootTest` here**: it makes unit tests slow, dependent on Docker/config, and increases the risk of startup failures unrelated to business logic. If you want to verify annotation scanning/AOP listener registry, that is a Spring-layer integration test.

## 11. Codec unit test to keep the contract clear

Create `src/test/java/example/messaging/OrderEventCodecTest.java`:

```java
package example.messaging;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OrderEventCodecTest {

    @Test
    void encodeAndDecodeRoundTrip() {
        OrderCreated original =
                new OrderCreated("ORD-123", 100);

        String payload = OrderEventCodec.encode(original);

        assertEquals("ORD-123|100", payload);
        assertEquals(
                original, OrderEventCodec.decode(payload));
    }

    @Test
    void quantityAboveMaxIsRejected() {
        assertThrows(
                IllegalArgumentException.class,
                () -> OrderEventCodec.decode("ORD-7|101"));
    }

    @Test
    void nonNumericQuantityIsRejected() {
        assertThrows(
                IllegalArgumentException.class,
                () -> OrderEventCodec.decode("ORD-7|oops"));
    }
}
```

**Three tests** confirm encoder/decoder consistency, the upper boundary, and type mismatch. This is a good place to add min/max cases, missing/blank, malformed Unicode, and version/schema checks as the message format evolves. Still, a codec test does not protect **AMQP content-type/headers, listener binding, or DLQ**, so an integration test is needed.

## 12. Integration test: real RabbitMQ with Testcontainers

Create `src/test/java/example/messaging/RabbitBrokerIntegrationTest.java`:

```java
package example.messaging;

import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.NONE,
        properties = {
                "spring.rabbitmq.dynamic=true",
                "spring.rabbitmq.listener.simple.default-requeue-rejected=false",
                "spring.rabbitmq.listener.simple.concurrency=1",
                "spring.rabbitmq.listener.simple.max-concurrency=1"
        })
class RabbitBrokerIntegrationTest {

    @Container
    @ServiceConnection
    static RabbitMQContainer rabbit =
            new RabbitMQContainer(
                    DockerImageName.parse(
                            "rabbitmq:4.1-management-alpine"));

    @Autowired
    private RabbitTemplate template;

    @Autowired
    private InMemoryOrderHandler handler;

    private static String newOrderId() {
        return "ORD-" + UUID.randomUUID();
    }

    @Test
    void messageTravelsThroughRealBrokerToListener()
            throws Exception {
        assertTrue(rabbit.isRunning());

        String id = newOrderId();
        OrderCreated event = new OrderCreated(id, 2);
        CompletableFuture<OrderCreated> arrived =
                handler.watch(id);

        template.convertAndSend(
                RabbitTopology.ORDER_EXCHANGE,
                RabbitTopology.ORDER_ROUTING,
                OrderEventCodec.encode(event));

        OrderCreated actual =
                arrived.get(10, TimeUnit.SECONDS);

        assertEquals(event, actual);
        assertEquals(1, handler.processedTimes(id));
    }

    @Test
    void independentKeysDoNotDependOnDeliveryOrder()
            throws Exception {
        String firstId = newOrderId();
        String secondId = newOrderId();

        CompletableFuture<OrderCreated> first =
                handler.watch(firstId);
        CompletableFuture<OrderCreated> second =
                handler.watch(secondId);

        template.convertAndSend(
                RabbitTopology.ORDER_EXCHANGE,
                RabbitTopology.ORDER_ROUTING,
                OrderEventCodec.encode(
                        new OrderCreated(firstId, 1)));

        template.convertAndSend(
                RabbitTopology.ORDER_EXCHANGE,
                RabbitTopology.ORDER_ROUTING,
                OrderEventCodec.encode(
                        new OrderCreated(secondId, 100)));

        assertEquals(
                new OrderCreated(firstId, 1),
                first.get(10, TimeUnit.SECONDS));
        assertEquals(
                new OrderCreated(secondId, 100),
                second.get(10, TimeUnit.SECONDS));

        assertEquals(1, handler.processedTimes(firstId));
        assertEquals(1, handler.processedTimes(secondId));
    }

    @Test
    void invalidMessageIsRejectedToDeadLetterQueue()
            throws Exception {
        String id = newOrderId();
        String invalid = id + "|0";

        // Producer intentionally skips encode(): we need to send
        // an invalid payload to verify the broker failure path.
        template.convertAndSend(
                RabbitTopology.ORDER_EXCHANGE,
                RabbitTopology.ORDER_ROUTING,
                invalid);

        // Consumer fails; requeue=false; queue has DLX.
        Message dead = template.receive(
                RabbitTopology.DEAD_QUEUE,
                10_000L);

        assertNotNull(dead);
        assertEquals(
                invalid,
                new String(
                        dead.getBody(),
                        StandardCharsets.UTF_8));
        assertTrue(
                dead.getMessageProperties()
                        .getHeaders()
                        .containsKey("x-death"));

        assertEquals(0, handler.processedTimes(id));
    }
}
```

These **three test methods** actually connect to a RabbitMQ Docker container:

1. **Valid delivery:** publishes via `RabbitTemplate` to the right exchange and routing key, RabbitMQ routes to the queue; the Spring listener container dispatches to `@RabbitListener`; the handler receives the domain event. The test awaits the Future by event ID with an explicit timeout.
2. **Two independent keys:** does not depend on which event arrives first. The test awaits each Future by ID, avoiding asserting an order that is not guaranteed across all broker/concurrency configurations.
3. **Invalid message → DLQ:** sends raw quantity 0; `OrderEventCodec.decode` throws `IllegalArgumentException`; the listener container is configured with `default-requeue-rejected=false`, so the message is rejected without requeue, and the RabbitMQ DLX routes it to `lesson.orders.dead`. The test reads the actual message from the DLQ and checks the body + `x-death` header.

**Professional observation:** `template.receive(DEAD_QUEUE, 10_000L)` **removes the message from the DLQ** so the test can inspect it. It does not merely "peek" at the queue. This is intentional behavior to clean up the test message. Do not apply this consume operation directly in production observability if you only want to measure queue depth.

### Why use CompletableFuture instead of Thread.sleep?

Message consumption is **asynchronous**. A unit test calling a Java method returns immediately; an integration test publishes to a broker and then may have to wait for:

- Connection/broker handshake.
- Exchange routing and queue delivery.
- Listener container poll/dispatch.
- Message conversion and business handler.
- ACK/reject/DLX according to the error policy.

Using `Thread.sleep(500)` and then asserting a map is often flaky: it passes on a fast dev machine and fails on slow CI. `CompletableFuture.get(10, TimeUnit.SECONDS)` **waits for the handler's real signal**, with a bounded timeout. For the failure path, `RabbitTemplate.receive(queue, timeout)` waits for the message to appear in the DLQ per broker state.

**Warning:** `CompletableFuture.get` timing out does not automatically cancel the consumer task. If the integration test is using a shared broker and the consumer processes the message after timeout, it may leave messages behind for another test. Use dedicated containers/test queues or cleanup/reconciliation per policy to ensure isolation.

### What has this broker test proved and not proved?

**Proved when passing:** Testcontainers RabbitMQ starts; Boot connects; topology is declared; the producer sends a String payload; exchange/routing/queue work; Spring `@RabbitListener` receives; the handler is invoked; invalid messages are rejected and observable in the DLQ per test config.

**Not yet proved:** producer confirms/publisher returns, durable persistence across broker restarts, exactly-once, end-to-end DB transactions, idempotency under real redelivery, production TLS/networking, quorum queue clusters, consumer crash/reconnect, all headers/schema versions, or multi-consumer throughput.

**Nor does it prove that the broker ACK completed on the success path** just because `handler.watch(...).get(...)` completed: the signal may complete **before the container sends the ACK**. If you need to test durable ACK, add a scenario checking queue delivery/unacked metrics or redelivery/restart semantics with appropriate synchronization.

## 13. Why is @ServiceConnection important?

In Spring Boot 3.5, `@ServiceConnection` on `RabbitMQContainer` provides **`RabbitConnectionDetails`** to Spring AMQP auto-configuration. As a result, the test does not have to manually write `spring.rabbitmq.host/port/username/password` from a random mapped port.

Separate roles of the annotations:

| Mechanism | Effect |
| --- | --- |
| `@Testcontainers` | Registers the Testcontainers JUnit Jupiter extension |
| Static `@Container` | Starts/stops RabbitMQ per **test class** |
| `@ServiceConnection` | Boot creates RabbitMQ connection details from the container |
| `@SpringBootTest(webEnvironment=NONE)` | Loads the Spring context and listener/handler/topology |
| `@EnableRabbit` | Enables annotation-driven Rabbit listener infrastructure |
| `@RabbitListener` | Registers a listener endpoint for the queue |
| `RabbitTemplate` | Publishes/receives messages over AMQP |
| `spring.rabbitmq.listener.simple.default-requeue-rejected=false` | On listener failure, rejects instead of requeuing by default |
| DLX/binding in `RabbitTopology` | Broker routes rejected messages to the DLQ |

If using a Spring Boot/Testcontainers version that does not support `@ServiceConnection`, you can use `@DynamicPropertySource` to register host/port/credentials dynamically. Choose one approach consistently; do not hardcode `localhost:5672` because Testcontainers uses a mapped port.

**Special note:** in Testcontainers 2.x, artifacts/group packages change. This example intentionally targets Boot 3.5/Testcontainers 1.x. For a new project on Boot 4/Testcontainers 2.x, adjust dependencies/imports to match the BOM version rather than mixing the two lines.

## 14. @RabbitListenerException: requeue, retry, and DLQ

In Spring AMQP, separate three concerns:

1. **Exception from the listener:** Java code could not process the message.
2. **Listener container policy:** whether there is a retry advice, and how to nack/reject/requeue after errors.
3. **Broker routing:** whether a message rejected without requeue has a dead-letter exchange/queue.

**Throwing an exception does not automatically send a message to the DLQ.** With common listener containers when retry is disabled, the default requeue-rejected setting is often **true**: failing messages may be redelivered repeatedly. If retry is enabled, the retry/recoverer policy also affects the outcome. In this lesson, the test explicitly sets:

```properties
spring.rabbitmq.listener.simple.default-requeue-rejected=false
spring.rabbitmq.listener.simple.concurrency=1
spring.rabbitmq.listener.simple.max-concurrency=1
```

and the topology has `x-dead-letter-exchange`/`x-dead-letter-routing-key`. Because of both parts, a quantity-0 message goes to the DLQ.

### Ack does not mean the handler has durable side effects

With acknowledge mode AUTO:

- Listener returns normally → the listener container may ACK the message.
- Listener throws an exception → the container handles it per retry/requeue/reject policy.
- A business handler might write to the DB and then throw an exception **after a separate commit**; redelivery can cause duplicate side effects.
- A RabbitMQ ACK and a SQL COMMIT are ordinarily **not a distributed atomic transaction**.

This is why an **idempotent** consumer needs a business key or a processed-message table, and critical production workflows may require a transactional outbox/inbox, deduplication, dead-letter monitoring, and compensating actions.

### What should a retry test verify?

If an application requires three retry attempts and then DLQ:

- Configure a clear retry policy with attempts/backoff/recoverer.
- Use a handler test double that can count attempts in a thread-safe way, not an unsynchronized counter.
- Verify successful retry before max and exhaustion → DLQ.
- Avoid overly short timeouts, `Thread.sleep`, or assuming the scheduler is always fast.
- Ensure the test does not create an infinite redelivery loop if default requeue remains true.
- Verify the exact count **according to the framework version's maxAttempts semantics**; do not guess off-by-one.
- If retry targets transient database errors, the test must use proper recoverable/unrecoverable errors; do not retry validation poison messages infinitely.

The runnable suite focuses on **reject once → DLQ** to keep the scenario deterministic. Do not claim retry/backoff is tested when the configuration and tests do not include them.

## 15. Publisher tests differ from consumer tests

Listener unit tests focus on the consumer method; broker integration tests should distinguish:

- **Producer-side:** event is serialized properly, exchange/routing key is chosen properly, required headers are present, publisher confirms/returns if the contract requires them.
- **Broker topology:** exchange/queue/binding exist, durability, DLX, permissions, and routing behavior.
- **Consumer-side:** method is dispatched, payload converts properly, validation, exceptions, ack/requeue/retry/DLQ, side effects.
- **End-to-end workflow:** HTTP command/DB transaction emits a message, consumer processes it, and the read model/DB ends up correct.

A producer unit test can mock `RabbitTemplate`:

```java
verify(template).convertAndSend(
        RabbitTopology.ORDER_EXCHANGE,
        RabbitTopology.ORDER_ROUTING,
        "ORD-7|2");
```

This is an illustrative snippet inside a test where `template` is a Mockito mock and production code calls it; it checks the **arguments passed to the publisher**, but does not prove RabbitMQ received or routed the message.

In RabbitMQ, a message published to an exchange that cannot be routed may not throw an exception under all configurations. If unroutable detection is required, you need publisher returns, the mandatory flag, and confirms per the Spring AMQP/RabbitMQ contract, plus an integration test. Do not assume that `RabbitTemplate.convertAndSend(...)` returning normally means the message was processed by a consumer.

## 16. Avoid accidentally opening a Spring context in "unit tests"

The goal of a listener unit test is to test the smallest piece of Java behavior. With the example's design:

```java
OrderEventHandler handler = mock(
        OrderEventHandler.class);
OrderQueueListener listener =
        new OrderQueueListener(handler);

listener.accept("ORD-7|2");
```

No `@SpringBootTest`, `@MockBean`, `@MockitoBean`, or `@Testcontainers` is needed. If you add a full Spring context, the test can fail because RabbitMQ is missing, even though the goal is only parsing/delegation.

**When is a Spring context needed without a broker yet?**

- To verify listener bean injection/configuration, conversion logic in the Spring messaging adapter, `@RabbitListener` registration, or argument resolution.
- When there is a custom `MessageConverter` and you want to verify the right bean is selected.
- When there are AOP advice/validation proxies that need to work through Spring.

You can use Spring-focused tests or custom mock connection infrastructure to test parts in isolation, but **do not call them broker integration tests** if no RabbitMQ server is running.

**With Spring Kafka:** `@EmbeddedKafka` uses a test broker running during the test, not a direct listener unit test; the Spring Cloud Stream test binder checks function/binding behavior in-process but **does not replace a real Kafka/RabbitMQ broker** when the contract involves protocol/delivery. State the boundary clearly.

## 17. Testing JSON schemas and headers when production does not use demo text

The `ORD-7|2` payload example is mainly for learning the broker. In a real project, events may be JSON:

```json
{
  "eventId": "evt-7",
  "schemaVersion": 2,
  "type": "order.created",
  "orderId": "ORD-7",
  "quantity": 2,
  "occurredAt": "2026-11-08T00:00:00Z"
}
```

When moving to JSON, also test:

1. The producer creates the exact JSON schema (required/optional fields, enums, decimal/time formats).
2. The message converter/serializer sends the right content-type/charset, correlation ID, event type/schema version.
3. The consumer reads payloads of the new version and handles old versions per the backward-compatibility policy.
4. Invalid types, malformed JSON, missing/null fields, and Unicode have clear handling (reject/DLQ or fallback).
5. Do not log full payloads if they contain PII, tokens, or financial data; mask and restrict log access.
6. Do not put raw exception messages in DLQ reasons or public responses that could leak secrets.
7. Test that duplicate `eventId` **does not** cause duplicate business processing under an at-least-once contract.

If using `Jackson2JsonMessageConverter`/`JacksonJsonMessageConverter`, names and supported APIs change across Spring AMQP/Spring Boot major versions. Check the dependency BOM and the converters actually configured; do not unit-test an `ObjectMapper` alone and conclude AMQP headers are right.

**A typical class of bugs:** the message body is valid JSON, yet the content-type is wrong, the consumer's converter rejects it, or Java type mapping fails. A unit test calling `listener.accept("...")` cannot catch this; integration through a broker must verify real delivery.

## 18. What to test when the consumer has a database?

When a real handler persists data:

```text
RabbitMQ delivery
    |
    v
@RabbitListener -> service transaction
    |
    +-- INSERT/UPDATE database
    |
    +-- ACK RabbitMQ (per container policy)
```

Here you should verify:

- **Valid:** the message is consumed, the database row appears, and values are accurate.
- **Validation violation:** the database is unchanged, and the message is rejected/DLQ'd or ignored per contract.
- **Database transient failure:** appropriate retry/backoff and attempt counts.
- **Duplicate delivery:** no duplicate records or double charges are created.
- **Crash window:** the DB may commit while ACK has not been sent; the broker redelivers after restart. The handler must be idempotent.
- **Outbox:** when a DB transaction produces an event to send to the broker, ensure no event is lost if the DB commits but publishing fails.
- **Inbox/deduplication:** the consumer can store the processed `eventId` in the same transaction as the side effect.
- **Poison message:** do not retry infinitely causing backlog/starvation; have a DLQ and controlled investigation.

**Do not put `@Transactional` on a JUnit test and assume the consumer thread is rolled back.** With RabbitMQ, `@RabbitListener` usually runs on a listener container thread, **not the test thread**. Data committed by the consumer can survive the JUnit test's rollback. Tests must use a dedicated DB/container and proper transaction/lifecycle cleanup.

**In the runnable suite:** `InMemoryOrderHandler` only updates a `ConcurrentHashMap` for test synchronization. It tests broker-to-listener, **not persistence/DB transactions**. To practice persistence further, replace the port with a handler writing to Postgres and add Testcontainers PostgreSQL/SQL assertions; do not claim the lesson already does that when no such test exists.

## 19. Async assertions: waiting properly and avoiding flakiness

A flawed messaging test typically looks like:

```java
template.convertAndSend(...);
Thread.sleep(200);
assertEquals(1, results.size());
```

This is an anti-pattern (not complete code): sleeping based on a guessed duration. On slow CI, the consumer may not have started/connected yet; on a fast machine, sleep wastes time.

Replace it with:

- A `CompletableFuture` completed when the handler actually processes the event.
- `BlockingQueue.poll(timeout, unit)` if you only need to pull each receipt (watch out for order independence).
- Awaitility with a synchronized predicate if the project already uses that dependency.
- Kafka-specific consumer polling/record assertions per the appropriate test library.
- For DLQs, use a timed broker receive such as `RabbitTemplate.receive(queue, timeout)`.

**The signal must reflect the actual claim being concluded.** If the handler completes the Future before a DB commit, a passing Future does not prove the DB committed. If you want to verify that the consumer completed the full transaction, observe the DB from a separate connection/transaction or emit a "committed" event after transaction completion.

**Timeout is a failure, not proof of absence:** a Future not completing within 10 seconds could be due to the broker not being ready, wrong routing, listener not registered, converter failure, or insufficient resources. Tests should have logs/diagnostics to classify the cause, rather than endlessly raising timeouts.

## 20. Independent test data and order-independent testing

In `RabbitBrokerIntegrationTest`, every valid event uses an ID formatted as `"ORD-" + UUID.randomUUID()`. This helps:

- The Future waits for the exact event, not picking up signals from another test.
- The `processedTimes(id)` counter is checked against a fresh ID.
- Test B does not rely on test A running first to set up data.
- Production/user business records are never touched.

The DLQ test is an exception: it reads from **a shared queue within the test class**. With exactly three tests in the example, only one intentionally sends an invalid payload; the container is owned exclusively by the class, so the expected dead message is unambiguous. In a larger suite with multiple producers, use per-suite queue names, correlation IDs, or inspect/requeue out-of-scope messages; **do not purge the entire DLQ** just to make a test pass.

**Do not:**

- Publish to production queues during CI runs.
- Use a shared RabbitMQ across tests with destructive purges outside locks/isolation.
- Assume the listener receives messages in publish order when multiple consumers, priorities, retries, or requeues are involved.
- Assert `processedTimes(id) == 1` as an exactly-once guarantee under all failures.
- Rely on `@DirtiesContext` to purge the broker: rebuilding the context does not clear queued messages.
- Use a static container while assuming the context cache always has a compatible lifecycle.

### Spring TestContext cache and static @Container

If a Spring test class has `static @Container RabbitMQContainer`, the JUnit extension stops it when the class finishes, but Spring may cache the context/DataSource/connection factory for reuse by another class with the same cache key. When a context reuses connection details of a stopped container, the test suite can fail intermittently.

To share a context across multiple classes, consider:

- Making the container a **Spring test bean** with `@TestConfiguration @Bean @ServiceConnection` so its lifecycle lives with the context.
- A suite-wide shared container owner with explicit startup/stop.
- Intentionally isolating contexts/configurations when classes use different brokers.
- Selective `@DirtiesContext` if the context truly must be closed, though it does not replace broker data cleanup.

Which model fits depends on Spring TestContext caching, runtime resource ownership, and the number of classes. For a **single integration class** example, static `@Container` is the simplest approach.

## 21. Testing retries, at-least-once, and idempotency

In real messaging systems, a single success delivery test is only the starting point. Key cases:

### 21.1. Duplicate event

Publish the same `eventId` twice and verify the DB records only one business effect. Define an idempotency key and a SQL unique constraint or deduplication store.

**Do not equate this with the example's two different order IDs test.** That test only checks independent events, not deduplication.

### 21.2. Consumer handler failure before commit

Inject a controlled failure (e.g., repository throws a transient exception on the first attempt), verify broker retry/requeue per config, attempt count, and eventual success. With Rabbit listener containers, enable retry/track attempts per version; avoid using an infinite requeue loop to simulate "retry".

### 21.3. Consumer handler failure after commit

This is the **crash window**: a DB write has committed, yet the ACK has not reached the broker. Redelivery of the same event must not double-apply the side effect. This is why idempotency matters more than wishing for exactly-once.

### 21.4. Poison message

Payload has an unsupported schema version or unparseable data. Per policy, the message can move to the DLQ once, with safe error metadata, without infinite requeues. The DLQ test in section 12 is a minimal version of this case.

### 21.5. Publisher failure

When a DB transaction commits an order but publishing the message fails, there is a risk of losing the event. Testing transactional outbox/inbox and publisher confirms/retries is a different boundary from listener tests; do not use a listener unit test to claim the system has atomicity.

## 22. When to use @RabbitListenerTest or a test binder?

Spring AMQP provides listener-related test infrastructure, including `@RabbitListenerTest`/listener test harness in certain versions/configurations, useful for spying/testing method invocations and dispatch. However, distinguish:

- **Method-level unit test:** call `new OrderQueueListener(mockHandler).accept(...)`, no broker.
- **Spring listener configuration test:** verify listener beans/registry, conversions/harness depending on config; may not need a real broker if only testing a slice.
- **Broker integration test:** requires a real RabbitMQ server (e.g., Testcontainers) and publishing/consuming over AMQP.
- **End-to-end system test:** real producer, real broker, real consumer, real database/API side effects; requires managing multiple dependencies.

A **Spring Cloud Stream test binder** verifies binding/function wiring in-process but does not fully replicate a broker. It is great for fast feedback, yet it does not prove Kafka partition assignment or RabbitMQ DLX works. With Kafka, `@EmbeddedKafka` runs a test broker rather than being a pure listener unit test; Kafka Testcontainers provides a containerized broker environment and still requires testing topics/consumer-groups/offsets as a contract.

**Naming tests after their true boundary** prevents readers from over-interpreting a green test.

## 23. Standalone Java 17 demo: encoder/decoder without Docker

Create `src/main/java/example/messaging/OrderCodecDemo.java`:

```java
package example.messaging;

public class OrderCodecDemo {
    public static void main(String[] args) {
        OrderCreated event =
                new OrderCreated("ORD-7", 2);

        String encoded = OrderEventCodec.encode(event);
        OrderCreated decoded =
                OrderEventCodec.decode(encoded);

        System.out.println(encoded);
        System.out.println(decoded);

        try {
            OrderEventCodec.decode("ORD-7|0");
        } catch (IllegalArgumentException error) {
            System.out.println(
                    "reject=" + error.getMessage());
        }
    }
}
```

Compile from the project root with **JDK 17+** (no Spring/RabbitMQ/Gradle required):

```bash
javac -encoding UTF-8 -d out src/main/java/example/messaging/OrderCreated.java src/main/java/example/messaging/OrderEventCodec.java src/main/java/example/messaging/OrderCodecDemo.java
java -cp out example.messaging.OrderCodecDemo
```

**Exact** stdout:

```text
ORD-7|2
OrderCreated[orderId=ORD-7, quantity=2]
reject=invalid quantity
```

This demo can genuinely run on Java SE and helps you distinguish **codec logic** from the **broker communication path**. If the demo passes, do not conclude that exchanges/queues/listeners were created, because the program **neither calls RabbitTemplate nor starts RabbitMQ**.

## 24. How to run the JUnit test suite

Unit tests (no Docker required):

```bash
./gradlew test --tests example.messaging.OrderQueueListenerUnitTest
./gradlew test --tests example.messaging.OrderEventCodecTest
```

Broker integration test (requires Docker running the RabbitMQ image):

```bash
./gradlew test --tests example.messaging.RabbitBrokerIntegrationTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.messaging.OrderQueueListenerUnitTest"
.\gradlew.bat test --tests "example.messaging.OrderEventCodecTest"
.\gradlew.bat test --tests "example.messaging.RabbitBrokerIntegrationTest"
```

**Expected results if the project, Docker image, and dependencies match the stated versions:**

| Test class | Method count | Broker |
| --- | ---: | --- |
| `OrderQueueListenerUnitTest` | 4 | No |
| `OrderEventCodecTest` | 3 | No |
| `RabbitBrokerIntegrationTest` | 3 | **Real RabbitMQ via Testcontainers** |
| **Total** | **10** | Covers both levels |

Do not assign fixed stdout for Gradle/JUnit because logs, Docker startup, and test runners can vary. **The code is provided for learners to run; this lesson does not claim to have executed the Docker tests in the reader's environment.** Exact stdout applies only to `OrderCodecDemo` running on Java SE.

### Quick failure triage

- Unit codec fails → format parsing rule or expected record.
- Unit listener fails → delegation, error propagation, Mockito setup.
- Docker fails to start → Docker daemon/image/resources; cannot conclude the Rabbit listener is wrong yet.
- Spring context fails → Boot dependencies/autoconfiguration/connection details/topology.
- Message does not reach handler → exchange/routing/binding, listener container, converter, consumer startup.
- Failing message keeps requeuing → `defaultRequeueRejected`/retry policy misconfigured.
- Invalid payload missing from DLQ → check DLX/queue binding, requeue policy, listener exception, and broker logs.
- Test waiting on Future times out → check async delivery end-to-end; do not blindly increase sleep.
- Passes in isolation but fails in suite → context caching, shared queues, test data contamination, or consumer concurrency.

## 25. Common anti-patterns

**1. Calling the listener method directly and claiming "broker integration passed".** No network/queue/consumer container was exercised.

**2. Mocking RabbitTemplate and claiming the message was delivered.** Verifying the invocation only checks the producer call, not broker routing.

**3. Mocking the business handler in every test and forgetting to test real side effects.** Mockito does not prove DB commit/rollback or persistence mapping.

**4. Catching every exception in the listener and returning.** AUTO ack may report success even though the event was not processed, losing the message.

**5. Assuming exceptions go to the DLQ by default.** It still depends on requeue, retry/recoverer, and DLX topology. Without explicit configuration, a redelivery loop may occur.

**6. Asserting the handler was called once and claiming exactly-once.** At-least-once delivery and crash windows can still produce duplicates.

**7. Using Thread.sleep to wait for the consumer.** Flaky under CI load; use a Future/BlockingQueue/broker receive with a timeout.

**8. Creating another consumer to "peek" at the main queue.** It can steal messages from the test's production listener, causing inconsistent assertions; observe side effects/signals properly instead.

**9. Not checking the routing key and exchange.** Publishing may go to the wrong exchange and the queue never receives it; unit tests cannot catch this.

**10. Reading the DLQ while forgetting the message is removed.** A test could accidentally consume forensic data; only do this in a dedicated test queue.

**11. Sharing a fixed persistent queue across parallel integration tests.** Failing data mixes together, and tests read the wrong DLQ messages.

**12. Using `@Transactional` on the test and believing the consumer thread rolls back with it.** The consumer runs on a separate thread/transaction.

**13. Using `@DirtiesContext` to purge RabbitMQ queues.** It replaces the Spring context, not broker committed state.

**14. Not waiting for async tasks to finish before container teardown.** Messages can arrive after cleanup or the container stops mid-processing.

**15. Assuming a Testcontainers broker equals a production cluster.** Clustering, TLS, auth, quorum queues, network latency, and broker config can differ.

**16. Sending malformed JSON while only testing that the listener parses a raw String.** JSON converter/headers/schema handling remain untested.

**17. Not testing error paths.** Valid messages succeeding do not prove retry/DLQ works; poison messages can back up the queue.

**18. Not versioning the event contract.** Consumers can break when producers add/remove fields or change enums.

**19. Setting timeouts too low and blaming the code.** Container startup, queue declaration, and async dispatch need a reasonable budget; classify the failure.

**20. Using production credentials/brokers in CI.** Integration tests must have isolated environments and safe data.

## 26. QA Checklist for Messaging listener tests

**Unit test boundary:**

- Does the listener have constructor injection for direct testing?
- Are valid payloads, invalid boundaries, and malformed payloads tested?
- Is the collaborator verified to be called with the right argument?
- Is `verifyNoInteractions` used when parsing fails?
- Are business handler errors propagated instead of swallowed?
- Do unit tests run without a Spring context or Docker?

**Broker integration boundary:**

- Is there a real broker (RabbitMQContainer/Kafka) rather than only mocks/test binders?
- Is the listener annotation discovered by Spring and is the queue/topic right?
- Are exchange, queue, binding/routing key or topic/group/partition verified?
- Does the producer send via a real client/template, not a mock?
- Does delivery waiting use a timed signal instead of `Thread.sleep`?
- Are invalid messages tested against the right retry/requeue/DLQ policy?
- Does the DLQ test check exact message body/headers and isolate the queue?
- Is handler signaling distinguished from broker ACK/DB commit?
- Is test data/eventId isolated and independent of execution order?

**Reliability/production:**

- Does the consumer have an idempotency/deduplication policy for at-least-once delivery?
- Are duplicates, transient errors, poison messages, and crash windows tested if part of the contract?
- Do database side effects have separate commit/rollback tests if a DB is used?
- Are schema/content-type/headers/versioning and Unicode covered by corresponding tests?
- Are publisher confirms/returns used if delivery guarantees are required?
- Are metrics, tracing, and safe error logging free of PII/tokens?
- Is container lifecycle compatible with Spring context caching and parallel CI?
- Does CI have Docker/network/image access, and does missing Docker fail/skip per policy?
- Can unit tests run separately, broker integration separately, and the full suite together to catch state leakage?

**Conclusion:** **listener unit tests** protect parsing/validation/delegation logic and exception propagation on Java methods; **integration tests through a real broker** protect publishing, routing, the listener container, delivery, and error policies. The two levels do not replace each other. With Spring Boot, combine JUnit/Mockito (fast, independent) with RabbitMQ Testcontainers (realistic, asynchronous); verify DLQ, idempotency, schema, and database commits at their proper boundaries. Most importantly: **a green test must be interpreted accurately for what it actually ran**.

## 27. References

- [Spring Boot 3.5 — AMQP Messaging](https://docs.spring.io/spring-boot/3.5/reference/messaging/amqp.html): `@RabbitListener`, `RabbitTemplate`, listener factory, and error/requeue configuration.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection` with `RabbitMQContainer`/connection details.
- [Spring AMQP — Exception Handling](https://docs.spring.io/spring-amqp/reference/amqp/exception-handling.html): listener exceptions, requeue, reject, dead-letter behavior.
- [Spring AMQP — Listener Container Attributes](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): `defaultRequeueRejected` and listener container options.
- [Spring AMQP — RabbitListener API](https://docs.spring.io/spring-amqp/api/org/springframework/amqp/rabbit/annotation/RabbitListener.html): annotation setup, queue declarations, and consumer configuration.
- [Testcontainers Java — JUnit 5](https://java.testcontainers.org/test_framework_integration/junit_5/): static `@Container` and extension lifecycle.
- [Testcontainers Java — RabbitMQ Module](https://java.testcontainers.org/modules/rabbitmq/): broker test dependencies and `RabbitMQContainer`; note current docs may use Testcontainers 2.x artifacts while this lesson targets 1.x.
- [Spring Kafka — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html): broker integration/embedded Kafka and Kafka-specific test utilities.
