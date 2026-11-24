# RabbitMQ in Containers and Spring AMQP Testing Tools

> **Module:** Spring Boot – testing  
> **Group:** Messaging  
> **Topic:** RabbitMQ in containers and Spring AMQP testing tools  
> **Goal:** Clearly understand the testing layers for producers, consumers, routing, and real brokers; use Spring AMQP test utilities and RabbitMQ Testcontainers for their proper purposes; set up a Java 17, Spring Boot 3.5, Maven example with deterministic asynchronous tests.

## 1. The big picture

A call to `rabbitTemplate.convertAndSend(exchange, routingKey, payload)` can run without errors in a unit test, yet still fail to prove that the message reached the RabbitMQ broker, routed to the right queue, converted its payload successfully, or triggered business processing in the consumer.

```text
Producer
  |
  v
RabbitTemplate --AMQP--> RabbitMQ container
                         |
                      Exchange
                         |
               Routing key + binding
                         |
                        Queue
                         |
                 @RabbitListener container
                         |
                    Handler logic
                         |
                ACK/NACK + side effect
```

Questions to separate:

1. Did the producer pick the right exchange, routing key, and body?
2. Do the exchange, queue, and binding exist with the right configuration on the broker?
3. Did RabbitMQ accept the publication and route it properly?
4. Did the listener container receive the message, deserialize it properly, and invoke the right handler?
5. Did the handler write the right business state, even though it runs on a different thread than the test?
6. Do ACK/NACK, retries, redelivery, and DLQ operate according to policy?
7. Does CI have a Docker daemon, networking, resources, and proper container cleanup?

**Mockito is good for verifying method calls; RabbitMQ Testcontainers is for verifying broker behavior.** The two tools do not replace each other.

### 1.1. Important AMQP concepts

| Concept | Role | Easy-to-miss pitfalls |
| --- | --- | --- |
| Exchange | Receives publications and selects destinations | Default exchange differs from custom exchanges |
| Queue | Holds deliveries | Durability, auto-delete, queue arguments |
| Binding | Connects an exchange to a queue | Routing key mismatch |
| Routing key | Sent by publisher to an exchange | Not always equal to the queue name |
| RabbitTemplate | Sends/receives via the AMQP client | Call success does not prove routing |
| RabbitAdmin | Declares broker resources | Having beans does not guarantee they were declared |
| @RabbitListener | Consumer method | Runs asynchronously, not on the test thread |
| Publisher confirm | Broker accepts the publication | Differs from consumer ACK |
| Mandatory return | Unroutable publication is returned | Must enable returns/mandatory |
| Consumer ACK/NACK | Acknowledges or rejects a delivery | Related to requeue/retry |
| DLX/DLQ | Destination for dead-lettered messages | Not automatically created just because a listener throws |
| Redelivery | Broker delivers a message again | Handlers need idempotency |

### 1.2. Direct, topic, and fanout exchanges

With a direct exchange, the binding key matches the routing key exactly. For example:

```text
it.events.exchange
  "orders.created" -> it.orders.queue
  "orders.audit"   -> it.audit.queue
```

Topic exchanges use patterns such as `orders.*`, `orders.#`. Fanout exchanges broadcast to all bound queues, ignoring the routing key. A hand-rolled fake `Map` rarely reproduces these semantics accurately.

A publisher confirm ACK does not prove the message routed to a queue. A consumer ACK does not prove a database transaction outside the broker committed. Business success requires its own assertion.

## 2. Testing layers to use

| Level | Tool | Real RabbitMQ broker? | What it proves |
| --- | --- | --- | --- |
| Producer unit | JUnit + Mockito RabbitTemplate | No | Validation, exchange/key/payload arguments |
| Consumer unit | Direct method call | No | Handler business processing |
| Listener wiring | TestRabbitTemplate | No | Listener invoked directly inside the context |
| Listener spy/capture | @RabbitListenerTest, RabbitListenerTestHarness | Depends on send path | Arguments, return values, exceptions |
| Broker available check | @RabbitAvailable | Uses pre-existing broker | Broker reachability/queues per config |
| Routing integration | RabbitMQ Testcontainers + SpringBootTest | Yes | Exchange, queue, bindings, AMQP network |
| Reliability | Broker test + confirms/returns/DLQ | Yes | Routing failures, retries, and redelivery |
| HA/security/perf | Staging cluster | Real topology | TLS/ACL/quorum/failover/load |

There is no need to start RabbitMQ for every unit test. However, a test whose goal is confirming exchange routing or ACK while mocking the broker uses the wrong level of evidence.

## 3. `spring-rabbit-test` and specialized utilities

### 3.1. `@SpringRabbitTest`

`@SpringRabbitTest` helps provide AMQP infrastructure beans inside a Spring test context, such as a connection factory, `RabbitTemplate`, `RabbitAdmin`, and listener factory. If you already use `@SpringBootTest` and Spring Boot AMQP auto-configuration, these beans are normally already present, so you do not need `@SpringRabbitTest` just to autowire `RabbitTemplate`.

The annotation **does not start a RabbitMQ broker**.

### 3.2. `TestRabbitTemplate` does not send through a broker

`org.springframework.amqp.rabbit.test.TestRabbitTemplate` discovers listener containers in the Spring context and invokes listeners directly by **queue name**, on the test process/thread. It is useful for testing wiring and certain request/reply scenarios.

However, it does not prove broker exchanges/bindings, message persistence, mandatory returns, publisher confirms, or real consumer ACKs. Example **illustrative** bean config, not a standalone project:

```java
@TestConfiguration
class NoBrokerListenerConfig {
    @Bean
    TestRabbitTemplate testRabbitTemplate(
            ConnectionFactory factory) {
        return new TestRabbitTemplate(factory);
    }
}
```

Requires importing `TestConfiguration`, `Bean`, Spring Rabbit `ConnectionFactory`, and `TestRabbitTemplate`. When testing brokerless, configure ordinary listener containers so they do not try to connect to a nonexistent broker.

### 3.3. `@RabbitListenerTest` and `RabbitListenerTestHarness`

`@RabbitListenerTest` is placed on `@Configuration`/`@TestConfiguration` to create a listener test harness. Two modes:

- `spy=true` (default): attaches a Mockito spy to the listener.
- `capture=true`: advice records invocation arguments, results, or exceptions.

For the harness to spy/capture, the listener must have `@RabbitListener(id="...")`. A `final` listener method cannot be spied/advised.

Useful API:

```java
RabbitListenerTestHarness.InvocationData data =
        harness.getNextInvocationDataFor(
                "ordersListener", 10, TimeUnit.SECONDS);

assertThat(data).isNotNull();
assertThat(data.getArguments())
        .containsExactly("order-123");
assertThat(data.getThrowable()).isNull();
```

This snippet requires an autowired `harness` and a publisher/broker or suitable test dispatch. `getNextInvocationDataFor` accepts a timeout, avoiding `Thread.sleep`.

### 3.4. `@RabbitAvailable` and availability policy

`@RabbitAvailable` is processed by `RabbitAvailableCondition` in JUnit 5. It checks a **pre-running broker**:

- `queues`: test queues are declared/purged/deleted per lifecycle.
- `management`: requires the management API.
- `purgeAfterEach` defaults to true.
- When the broker is unavailable, the test may be **skipped**.
- `RABBITMQ_SERVER_REQUIRED=true` per Spring AMQP docs makes the test fail when a broker is required.

When using Testcontainers, `@RabbitAvailable` is usually unnecessary because JUnit `@Container` starts the broker automatically. Do not let the default condition look for `localhost:5672` when the container publishes a random port and mistakenly conclude the broker is down.

### 3.5. `@LongRunning`

A Spring AMQP annotation that helps run long tests only when the corresponding environment flag is set. If a CI job advertises INTEGRATION PASS, verify the tests actually executed rather than being skipped by a test condition.

## 4. RabbitMQ Testcontainers and Spring Boot

Spring Boot 3.5 supports `@ServiceConnection` for a typed `RabbitMQContainer`, providing `RabbitConnectionDetails` matching the mapped AMQP host/port/credentials.

```java
@Testcontainers
@SpringBootTest
class RabbitContainerExample {
    @Container
    @ServiceConnection
    static RabbitMQContainer rabbit =
            new RabbitMQContainer("rabbitmq:4.1.8-management");
}
```

This is an annotation skeleton; the full test project is below. Spring Boot 3.5 parent manages Testcontainers 1.x, so use the Java import:

```java
import org.testcontainers.containers.RabbitMQContainer;
```

With Testcontainers 2.x, the new artifact/package may change to `org.testcontainers:testcontainers-rabbitmq` and `org.testcontainers.rabbitmq.RabbitMQContainer`. Do not mix 2.x imports with Boot 3.5-managed dependencies without upgrading the BOM consistently.

**Do not hard-code localhost:5672.** Docker maps container port 5672 to a dynamic host port. Management HTTP port 15672 is separate, not the AMQP port. Only require the management UI/API when tests actually need it. Pick an image version close to production or pin by digest per policy; do not use `latest` arbitrarily.

### 4.1. `@ServiceConnection` vs. `@DynamicPropertySource`

When not using service connections, you can configure dynamic properties:

```java
@DynamicPropertySource
static void rabbitProps(DynamicPropertyRegistry registry) {
    registry.add("spring.rabbitmq.host", rabbit::getHost);
    registry.add("spring.rabbitmq.port", rabbit::getAmqpPort);
    registry.add("spring.rabbitmq.username", rabbit::getAdminUsername);
    registry.add("spring.rabbitmq.password", rabbit::getAdminPassword);
}
```

This requires a static container and imports from `org.springframework.test.context`. Normally choose one way to supply connection details to avoid overlapping configuration.

### 4.2. Context cache and container lifecycle

A JUnit static `@Container` may stop after the class while the Spring `ApplicationContext` remains cached and gets reused by another test class. Then `RabbitTemplate` can hold a connection factory pointing to a stopped container. With class-scoped containers, use `@DirtiesContext(AFTER_CLASS)` deliberately; for suites that share contexts, consider a Spring-managed container bean living alongside the context.

`@DirtiesContext` manages the Spring context, **not** purging RabbitMQ queues or Docker resources.

## 5. Complete Maven project — Java 17 and Spring Boot 3.5

The demo project has a publisher, consumer, direct exchange, two queues, and an asynchronous observation sink. Tests include 2 publisher unit tests, 1 consumer unit test, 2 broker integration tests, and 1 harness integration test: **6 JUnit `@Test` methods**.

### 5.1. Structure

```text
rabbit-messaging-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/rabbitlab/
    │   ├── RabbitLabApplication.java
    │   ├── RabbitTopology.java
    │   ├── OrderPublisher.java
    │   ├── OrderConsumer.java
    │   └── ProcessedMessages.java
    └── test/java/com/example/rabbitlab/
        ├── OrderPublisherUnitTest.java
        ├── OrderConsumerUnitTest.java
        ├── RabbitBrokerIntegrationTest.java
        └── RabbitHarnessIntegrationTest.java
```

All Java files share the `com.example.rabbitlab` package, with public classes matching their filenames.

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>rabbit-messaging-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-amqp</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.amqp</groupId>
            <artifactId>spring-rabbit-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-testcontainers</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>rabbitmq</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

The Boot BOM manages compatible Spring AMQP/Testcontainers/JUnit versions. `spring-rabbit-test` adds harness helpers; `spring-boot-testcontainers` adds Spring service connections; the `rabbitmq` Testcontainers module runs the broker.

### 5.3. `RabbitLabApplication.java`

```java
// src/main/java/com/example/rabbitlab/RabbitLabApplication.java
package com.example.rabbitlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RabbitLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(RabbitLabApplication.class, args);
    }
}
```

### 5.4. `RabbitTopology.java`

```java
// src/main/java/com/example/rabbitlab/RabbitTopology.java
package com.example.rabbitlab;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RabbitTopology {

    public static final String EXCHANGE = "it.events.exchange";
    public static final String ORDERS_QUEUE = "it.orders.queue";
    public static final String AUDIT_QUEUE = "it.audit.queue";
    public static final String ORDER_KEY = "orders.created";
    public static final String AUDIT_KEY = "orders.audit";

    @Bean
    DirectExchange eventsExchange() {
        return new DirectExchange(EXCHANGE, false, false);
    }

    @Bean
    Queue ordersQueue() {
        return new Queue(ORDERS_QUEUE, false);
    }

    @Bean
    Queue auditQueue() {
        return new Queue(AUDIT_QUEUE, false);
    }

    @Bean
    Binding orderBinding(
            @Qualifier("ordersQueue") Queue q,
            DirectExchange exchange) {
        return BindingBuilder.bind(q).to(exchange)
                .with(ORDER_KEY);
    }

    @Bean
    Binding auditBinding(
            @Qualifier("auditQueue") Queue q,
            DirectExchange exchange) {
        return BindingBuilder.bind(q).to(exchange)
                .with(AUDIT_KEY);
    }
}
```

Both queues use `durable=false` solely for an **ephemeral test broker**, not as a production durability policy. `@Qualifier` distinguishes the two `Queue` beans. When auto-declaration is enabled, Spring `RabbitAdmin` creates the queues/exchange/bindings on the broker once the connection is ready. If declaration is disabled or a queue name already exists with different arguments, `NOT_FOUND`/`PRECONDITION_FAILED` can occur.

### 5.5. `ProcessedMessages.java`

```java
// src/main/java/com/example/rabbitlab/ProcessedMessages.java
package com.example.rabbitlab;

import java.time.Duration;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;

@Component
public class ProcessedMessages {

    private final BlockingQueue<String> values =
            new LinkedBlockingQueue<>();

    public void add(String value) {
        values.add(value);
    }

    public String await(Duration timeout)
            throws InterruptedException {
        return values.poll(
                timeout.toMillis(), TimeUnit.MILLISECONDS);
    }

    public void clear() {
        values.clear();
    }
}
```

`BlockingQueue` lets the test thread wait for observations produced by the listener thread without fixed sleeps. This is in-JVM state; real applications should assert business side effects in a test-only DB or downstream service.

### 5.6. `OrderPublisher.java`

```java
// src/main/java/com/example/rabbitlab/OrderPublisher.java
package com.example.rabbitlab;

import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {

    private final RabbitTemplate template;

    public OrderPublisher(RabbitTemplate template) {
        this.template = template;
    }

    public void publish(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "orderId must not be blank");
        }

        template.convertAndSend(
                RabbitTopology.EXCHANGE,
                RabbitTopology.ORDER_KEY,
                orderId);
    }
}
```

Using `String` keeps the focus on routing. For real JSON events, producer/consumer must use an appropriate converter and should have schema version/compatibility tests.

### 5.7. `OrderConsumer.java`

```java
// src/main/java/com/example/rabbitlab/OrderConsumer.java
package com.example.rabbitlab;

import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumer {

    private final ProcessedMessages processed;

    public OrderConsumer(ProcessedMessages processed) {
        this.processed = processed;
    }

    @RabbitListener(
            id = "ordersListener",
            queues = RabbitTopology.ORDERS_QUEUE)
    public void receive(String orderId) {
        processed.add(orderId);
    }
}
```

The listener method is public, non-final, and has a stable ID `ordersListener` so the harness can capture it. The default `SimpleMessageConverter` supports String bodies. In `AUTO` mode, the container ACKs per lifecycle after the handler returns; observing `ProcessedMessages` does not directly prove the AMQP ACK frame was sent.

## 6. Unit tests without Docker

### 6.1. `OrderPublisherUnitTest.java`

```java
// src/test/java/com/example/rabbitlab/OrderPublisherUnitTest.java
package com.example.rabbitlab;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

class OrderPublisherUnitTest {

    @Test
    void sendsToExpectedExchangeAndKey() {
        RabbitTemplate template = mock(RabbitTemplate.class);
        OrderPublisher publisher = new OrderPublisher(template);

        publisher.publish("order-123");

        verify(template).convertAndSend(
                RabbitTopology.EXCHANGE,
                RabbitTopology.ORDER_KEY,
                "order-123");
    }

    @Test
    void rejectsBlankPayloadWithoutSending() {
        RabbitTemplate template = mock(RabbitTemplate.class);
        OrderPublisher publisher = new OrderPublisher(template);

        assertThatThrownBy(() -> publisher.publish(" "))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("orderId must not be blank");

        verifyNoInteractions(template);
    }
}
```

Two tests prove Java validation/interaction, not that the broker has the queue/binding.

### 6.2. `OrderConsumerUnitTest.java`

```java
// src/test/java/com/example/rabbitlab/OrderConsumerUnitTest.java
package com.example.rabbitlab;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class OrderConsumerUnitTest {

    @Test
    void directlyHandlesPayload() throws Exception {
        ProcessedMessages sink = new ProcessedMessages();
        OrderConsumer listener = new OrderConsumer(sink);

        listener.receive("order-321");

        assertThat(sink.await(Duration.ofMillis(100)))
                .isEqualTo("order-321");
    }
}
```

This test invokes the handler directly, without a Spring listener container or AMQP network.

## 7. RabbitMQ Testcontainers integration test

### 7.1. `RabbitBrokerIntegrationTest.java`

```java
// src/test/java/com/example/rabbitlab/RabbitBrokerIntegrationTest.java
package com.example.rabbitlab;

import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.test.annotation.DirtiesContext;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class RabbitBrokerIntegrationTest {

    @Container
    @ServiceConnection
    static RabbitMQContainer rabbit =
            new RabbitMQContainer("rabbitmq:4.1.8-management");

    @Autowired
    OrderPublisher publisher;

    @Autowired
    RabbitTemplate template;

    @Autowired
    ProcessedMessages processed;

    @BeforeEach
    void clearState() {
        processed.clear();
    }

    @Test
    void messageTravelsThroughBrokerToListener()
            throws Exception {
        String value = "order-" + UUID.randomUUID();

        publisher.publish(value);

        assertThat(processed.await(Duration.ofSeconds(10)))
                .isEqualTo(value);
    }

    @Test
    void auditKeyRoutesToAuditQueue() {
        String value = "audit-" + UUID.randomUUID();

        template.convertAndSend(
                RabbitTopology.EXCHANGE,
                RabbitTopology.AUDIT_KEY,
                value);

        Object received = template.receiveAndConvert(
                RabbitTopology.AUDIT_QUEUE, 5_000);

        assertThat(received).isEqualTo(value);
    }
}
```

The first test flows through publisher → real broker → direct exchange/binding/queue → listener container → observed side effect. The second test goes through the audit binding and then uses `RabbitTemplate` to receive directly from the audit queue, which has no listener. Do not use a short-lived queue depth assertion when an active listener could consume before the test measures it.

### 7.2. An optional topology test

If you need to verify that a queue was declared on the broker, add a test receiving `RabbitTemplate` and calling passive declaration (illustrative, not counted among the 6 methods):

```java
Integer count = template.execute(channel ->
        channel.queueDeclarePassive(
                RabbitTopology.ORDERS_QUEUE)
                .getMessageCount());

assertThat(count).isNotNull();
assertThat(count).isGreaterThanOrEqualTo(0);
```

AMQP passive declaration fails when the queue does not exist. It checks a real broker resource, not merely a Java bean.

## 8. `RabbitListenerTestHarness` with a real broker

### 8.1. `RabbitHarnessIntegrationTest.java`

```java
// src/test/java/com/example/rabbitlab/RabbitHarnessIntegrationTest.java
package com.example.rabbitlab;

import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.test.RabbitListenerTest;
import org.springframework.amqp.rabbit.test.RabbitListenerTestHarness;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Import;
import org.springframework.test.annotation.DirtiesContext;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest
@Import(RabbitHarnessIntegrationTest.HarnessConfig.class)
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class RabbitHarnessIntegrationTest {

    @Container
    @ServiceConnection
    static RabbitMQContainer rabbit =
            new RabbitMQContainer("rabbitmq:4.1.8-management");

    @Autowired
    OrderPublisher publisher;

    @Autowired
    RabbitListenerTestHarness harness;

    @Test
    void capturesListenerInvocation() throws Exception {
        String value = "harness-" + UUID.randomUUID();

        publisher.publish(value);

        RabbitListenerTestHarness.InvocationData call =
                harness.getNextInvocationDataFor(
                        "ordersListener", 10, TimeUnit.SECONDS);

        assertThat(call).isNotNull();
        assertThat(call.getArguments())
                .containsExactly(value);
        assertThat(call.getThrowable()).isNull();
    }

    @TestConfiguration(proxyBeanMethods = false)
    @RabbitListenerTest(spy = false, capture = true)
    static class HarnessConfig {
    }
}
```

`@Import(HarnessConfig.class)` brings the test annotation into the Spring context. `spy=false,capture=true` enables invocation capture advice. The ID must match the `ordersListener` listener. A bounded 10s wait avoids fixed sleeps. The harness captures arguments/exceptions, but does not by itself verify the ACK frame or external transaction commits.

### 8.2. Spy/latch as another option

You can use `@RabbitListenerTest(spy=true,capture=false)`, retrieve `harness.getSpy("ordersListener")`, and then Mockito verify with Awaitility or a harness latch answer. The listener method must not be final. This is an extension option, not part of the counted sample project.

## 9. Running Maven and expected results

```bash
java -version
mvn -version

# 3 unit tests without Docker:
mvn -B -ntp -Dtest=OrderPublisherUnitTest,OrderConsumerUnitTest test

# 3 integration tests requiring a RabbitMQ container:
docker info
mvn -B -ntp -Dtest=RabbitBrokerIntegrationTest,RabbitHarnessIntegrationTest test

# All tests:
mvn -B -ntp test
```

Per the source, the project has **6 JUnit test methods**: 3 unit, 2 broker integration, 1 harness integration. This is the expected structure, **not actual execution logs**. Maven needs to download dependencies if the cache is empty; Testcontainers needs a Docker runtime/image registry and may pull the RabbitMQ image on the first run.

## 10. Reliability: confirms, returns, ACK, retry, DLQ

### 10.1. Publisher confirms and returns

Spring Boot can configure:

```properties
spring.rabbitmq.publisher-confirm-type=correlated
spring.rabbitmq.publisher-returns=true
spring.rabbitmq.template.mandatory=true
```

These three properties **do not by themselves make a test**. Real testing must send a message with a valid routing key and wait for the correlated confirm, then send a key with no binding and wait for the return callback. Check the routing key, exchange, return code/body/correlation id; do not merely assert `convertAndSend` does not throw.

Broker confirm ACK and consumer ACK are different. A confirm tells you the broker accepted the publication, not that queue routing succeeded or the handler completed.

### 10.2. ACK modes

`AUTO` usually has the container ACK after a successful listener method, `MANUAL` requires the application to invoke `basicAck`/`basicNack`/`basicReject`, and `NONE` normally means automatic acknowledgement at the broker; do not interpret NONE as "never ACK".

When the handler throws, retry/requeue depends on listener container/error handler policies. A poison message can be redelivered endlessly if retries are not bounded.

### 10.3. DLQ requires topology too

Example property:

```properties
spring.rabbitmq.listener.simple.default-requeue-rejected=false
```

It **does not automatically create a dead-letter exchange/queue**. To test DLQ:

1. Declare the source queue with a DLX/routing policy, and create the DLQ and matching binding.
2. Send a failing payload with a distinct correlation id.
3. Enable finite retries and verify the message eventually enters the DLQ.
4. Read the DLQ with a bounded timeout, asserting body/headers/reason per contract.
5. Verify no wrong or duplicate business effects occurred.
6. Clean up only the broker/queues belonging to the test run.

Do not let a poison event test create an infinite requeue loop.

### 10.4. Idempotency

A consumer can update the database and then crash before ACK; RabbitMQ redelivers and the handler runs again. A Spring DB transaction and a RabbitMQ ACK are not by default an atomic distributed transaction. Sensitive workflows need event IDs, inbox/outbox, or deduplication, and redelivery tests against a test-only DB.

Do not claim exactly-once just because one message was processed once on a clean broker.

## 11. Deterministic async tests and CI

### 11.1. Bounded wait instead of fixed sleep

```java
publisher.publish("order-1");
assertThat(processed.await(Duration.ofSeconds(10)))
        .isEqualTo("order-1");
```

This example assumes a test context with `processed` and `throws Exception`. A bounded poll returns early when the message arrives and fails on timeout. A fixed `Thread.sleep(5000)` is flaky and wastes time. For database side effects, use Awaitility and assert database state with a bounded timeout.

### 11.2. Test isolation

- Each test group should have its own container/vhost/queue namespace.
- Use event IDs/UUIDs to avoid fixture collisions.
- Never purge queues on a shared dev/production broker.
- `ProcessedMessages.clear()` works for sequential test methods; if parallel execution is enabled, isolate state by event ID.
- The listener thread does not automatically share the JUnit test thread's transaction.
- Context cache and container lifecycle must align; `@DirtiesContext` in the sample avoids reusing a context pointing at a stopped broker.
- Do not enable Testcontainers reusable containers on mandatory CI if a clean broker per job is desired.

### 11.3. Illustrative GitHub Actions

```yaml
name: RabbitMQ testing
on: [push, pull_request]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Check Docker
        run: |
          docker version
          docker info --format 'Engine={{.ServerVersion}}'
      - name: Run tests
        run: mvn -B -ntp test
      - name: Upload reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: surefire
          path: target/surefire-reports/
          if-no-files-found: ignore
```

The job needs a Docker-compatible daemon, permission to create containers and pull images, and enough CPU/RAM/disk for the RabbitMQ Erlang VM and JVM. `@ServiceConnection` obtains the mapped host/AMQP port rather than hard-coding `localhost:5672`. On a Docker executor, the Maven container and Docker host have different networking; configure `DOCKER_HOST`/host overrides to match the topology.

Do not mount a shared host's rootful `docker.sock` into untrusted PR jobs. Do not unconditionally disable Ryuk or run global Docker prune on a daemon shared with other workloads. Mandatory CI integration jobs must not use `mvn test || true` or silently skip tests when the runtime is unavailable.

## 12. Common troubleshooting

| Symptom | Likely cause | Action |
| --- | --- | --- |
| Docker environment not found | Missing daemon/socket | Check Docker API and permissions |
| RabbitMQ image fails to pull | Registry/network/tag | Pin image/auth/proxy |
| Connection refused localhost:5672 | Different mapped port | `@ServiceConnection`, Docker networking |
| `NOT_FOUND - no queue` | `RabbitAdmin` has not declared it | Queue beans, dynamic declaration |
| `PRECONDITION_FAILED inequivalent arg` | Different queue flags | Fresh test broker, consistent topology |
| `MessageConversionException` | Wrong content type/converter | Test serialization end-to-end |
| Listener timeout | Wrong binding/key/consumer | RabbitMQ/Spring listener logs |
| Harness does not capture | Missing config/id or final method | Import `@RabbitListenerTest`, stable id |
| Publisher call succeeds yet event lost | Unroutable key | Confirms/mandatory returns |
| Handler throws repeatedly | Retry/requeue loop | Bounded retry and DLQ |
| Queue empty yet business work unfinished | Delivered/unacked | Assert business outcome |
| Suite fails starting from second class | Context reused stopped container | Context-managed lifecycle or `DirtiesContext` |
| CI OOM/exit 137 | Runner overloaded | CPU/RAM/disk/parallelism |

## 13. Exercises and self-check questions

**Exercise 1.** Run the publisher unit test first, then broker integration; explain why mocks do not prove real bindings.

**Exercise 2.** Intentionally send a nonexistent key; design a mandatory returned message test and compare it with publisher confirms.

**Exercise 3.** Change the String event to a JSON DTO with `eventId`/`schemaVersion`; verify producer/consumer converters through real RabbitMQ.

**Exercise 4.** Create a dead-letter exchange/queue and a poison event; verify there is no infinite requeue.

**Exercise 5.** Create a consumer idempotency test with a test-only database and simulate redelivery.

**Question 1.** Does Mockito verifying `RabbitTemplate` prove RabbitMQ received the message? **No.**

**Question 2.** Does `TestRabbitTemplate` use real exchange routing? **No**, it invokes listeners directly.

**Question 3.** Does `@RabbitAvailable` automatically start a Docker container? **No**, it checks an existing broker.

**Question 4.** What does the harness need to capture a listener? **A listener id and a non-final method**.

**Question 5.** Is a publisher confirm ACK equivalent to a consumer ACK? **No.**

**Question 6.** Does queue depth equal to 0 guarantee a DB commit? **No.**

**Question 7.** Why use bounded waits? **To handle async timing instead of fixed sleeps.**

**Question 8.** If Docker is missing and CI skips broker tests, is that an integration PASS? **No.**

## 14. QA Checklist

- [ ] Identified the right unit/consumer/listener-wiring/harness/broker test level.
- [ ] Included `spring-rabbit-test` when using test utilities.
- [ ] Did not mistake `TestRabbitTemplate` for real RabbitMQ.
- [ ] Appropriate broker container image/version, no hard-coded host port.
- [ ] Exchange/queue/bindings declared with exact names/flags.
- [ ] `@ServiceConnection` supplies Rabbit connection details.
- [ ] Listener has an ID and is non-final when using the harness.
- [ ] Asynchronous waits are bounded, no fixed sleeps.
- [ ] Asserts handler outcome, not just queue depth.
- [ ] Distinguishes publisher confirms, mandatory returns, and consumer ACKs.
- [ ] Retry/DLQ policy is bounded, avoiding poison loops.
- [ ] Handler is idempotent if redelivery can happen.
- [ ] Test isolation/cleanup never touches production brokers.
- [ ] Spring TestContext cache aligns with Testcontainers lifecycle.
- [ ] CI has proper Docker/API permissions/resources, never silently skipping mandatory tests.

## 15. Official References

- [Spring AMQP Testing Support](https://docs.spring.io/spring-amqp/reference/testing.html): `SpringRabbitTest`, `TestRabbitTemplate`, `RabbitListenerTest`, `RabbitAvailable`.
- [RabbitListenerTestHarness 3.2 API](https://docs.spring.io/spring-amqp/docs/3.2.x/api/org/springframework/amqp/rabbit/test/RabbitListenerTestHarness.html): spy/capture/latch.
- [InvocationData 3.2 API](https://docs.spring.io/spring-amqp/docs/3.2.x/api/org/springframework/amqp/rabbit/test/RabbitListenerTestHarness.InvocationData.html): invocation arguments, result, throwable.
- [Spring Boot 3.5 Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `RabbitMQContainer`/`RabbitConnectionDetails`.
- [Testcontainers RabbitMQ Module](https://java.testcontainers.org/modules/rabbitmq/): Java dependencies and container API.
- [Testcontainers JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): Container lifecycle.
- [RabbitMQ Publisher Confirms and Consumer Acknowledgements](https://www.rabbitmq.com/docs/confirms): types of acknowledgments.
- [RabbitMQ Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): DLX/DLQ behavior.
- [RabbitMQ Official Docker Image](https://hub.docker.com/_/rabbitmq): versions and management image.

**Conclusion:** Accurate RabbitMQ testing must separate publisher calls, broker routing, listener invocation, ACK/recovery, and business effects. Mockito keeps unit tests fast; Spring AMQP helpers support listener wiring/capture; RabbitMQ Testcontainers verifies a real broker. Avoid concluding delivery is guaranteed from a non-throwing `convertAndSend` or a green mock test.