# Testing JmsTemplate and Listeners with a Real Broker in Spring JMS

## Objectives

A unit test can mock `JmsTemplate` to verify that the application calls `convertAndSend` with the expected arguments. However, that test does not prove that the message was serialized properly, the connection to the broker succeeded, the destination exists, the listener received the message, or transactions/acknowledgements worked as expected.

To verify real messaging flows, run a real JMS broker in an integration test. With Spring Boot, a clean option is Apache ActiveMQ Artemis running in Testcontainers. The test starts the broker via Docker, configures Spring to connect to the container's dynamic port, sends a message using `JmsTemplate`, and verifies that a real `@JmsListener` actually received and processed the message.

The goal of this lesson is to test the path:

`test → JmsTemplate → ConnectionFactory → broker → destination → listener container → @JmsListener`

This is an integration test of the messaging infrastructure. Unit tests remain useful for pure business logic, but cannot replace testing against a broker.

## 1. What to Verify with a Real Broker

A real broker helps catch issues that mocks or embedded brokers may miss:

- Incorrect URL, port, username/password, or connection protocol.
- Queue or topic not created, wrong destination name, or mismatched queue/topic mode.
- Incompatible message converter serialization/deserialization between producer and consumer.
- Lost or malformed JMS headers, properties, correlation ID, delivery mode, priority, or time-to-live.
- Listener container failing to start, misconfigured concurrency, or broken reconnection.
- Messages acknowledged too early, rolled back, redelivered, or routed to a dead-letter queue (DLQ) unexpectedly.
- Broker-specific behavior differing from simulated configurations or other providers.

Not every test needs to run against a broker. Choose the critical flows: basic send/receive, converters, queue/topic routing, transactions, redelivery/DLQ, and related security configurations.

## 2. Dependencies for Spring Boot and Testcontainers

The examples below use Java 17+, Spring Boot with Jakarta JMS, JUnit 5, and Testcontainers 2.x. Spring Boot manages Spring dependency versions. The Testcontainers module and JUnit integration must use the same version.

Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-artemis</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>testcontainers-junit-jupiter</artifactId>
        <version>2.0.5</version>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>testcontainers-activemq</artifactId>
        <version>2.0.5</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

If using Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-artemis")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:testcontainers-junit-jupiter:2.0.5")
    testImplementation("org.testcontainers:testcontainers-activemq:2.0.5")
}
~~~

Testcontainers provides `ArtemisContainer` for ActiveMQ Artemis. This module supports Artemis images and lets you configure username/password, start the container, retrieve the mapped broker URL, and stop the container after tests.

Use a pinned image version instead of `latest`. The example in this lesson uses `apache/activemq-artemis:2.32.0-alpine`, from the same image family illustrated in Testcontainers documentation. When upgrading versions, check the image tag and compatibility with the broker running in production.

## 3. Configuring Spring to Connect to the Broker Container

When tests use an Artemis container, Spring Boot must connect to the external broker. Explicitly set:

- `spring.artemis.mode=native` to use the broker running in the container and avoid starting an embedded broker automatically.
- `spring.artemis.broker-url` obtained from `ArtemisContainer.getBrokerUrl()`.
- Username and password obtained from the container itself.
- Queues/topics configured consistently for both producer and listener.

Spring Boot auto-configures `ConnectionFactory`, `JmsTemplate`, and listener infrastructure when the Artemis starter is present. Artemis properties live under the `spring.artemis.*` prefix; general JMS settings live under `spring.jms.*`.

Example runtime configuration in `application-test.yml` when the broker has a fixed address:

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: testcontainers
    password: testcontainers
  jms:
    pub-sub-domain: false

app:
  jms:
    orders-queue: orders.integration
~~~

In Testcontainers, do not hard-code `localhost:61616`. Testcontainers maps the container port to a free port on the host. Use the URL returned by the container after startup.

## 4. Creating an Observable Listener in Tests

Listeners run on a listener container thread, independent of the test thread. Therefore, you cannot call the listener method directly and conclude that the broker delivered the message successfully.

In this example, the listener records the payload into a `BlockingQueue`. The test waits with a bounded timeout to receive the message; do not use a fixed `Thread.sleep`.

~~~java
import java.time.Duration;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.springframework.jms.annotation.JmsListener;

public class CapturingOrderListener {

    private final BlockingQueue<String> received =
            new LinkedBlockingQueue<>();

    @JmsListener(
            id = "orders-test-listener",
            destination = "${app.jms.orders-queue}")
    public void onMessage(String body) {
        received.add(body);
    }

    public String awaitMessage(Duration timeout)
            throws InterruptedException {
        return received.poll(
                timeout.toMillis(),
                TimeUnit.MILLISECONDS);
    }
}
~~~

This is a test-oriented listener. In a real application, a listener typically calls an application service and retains minimal observable state. Do not use non-thread-safe collections to share data between the listener thread and the test thread.

## 5. Complete Integration Test with ArtemisContainer

The following test starts a real broker, injects the dynamic address into the Spring context, sends a string via `JmsTemplate`, and waits for the listener to receive the exact content.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.activemq.ArtemisContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest(properties = {
        "spring.artemis.mode=native",
        "app.jms.orders-queue=orders.integration",
        "spring.jms.pub-sub-domain=false"
})
@Import(JmsBrokerIntegrationTest.ListenerConfig.class)
class JmsBrokerIntegrationTest {

    private static final String QUEUE = "orders.integration";

    @Container
    static final ArtemisContainer broker =
            new ArtemisContainer("apache/activemq-artemis:2.32.0-alpine")
                    .withUser("testcontainers")
                    .withPassword("testcontainers");

    @DynamicPropertySource
    static void brokerProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.artemis.mode", () -> "native");
        registry.add("spring.artemis.broker-url", broker::getBrokerUrl);
        registry.add("spring.artemis.user", broker::getUser);
        registry.add("spring.artemis.password", broker::getPassword);
    }

    @Autowired
    JmsTemplate jmsTemplate;

    @Autowired
    CapturingOrderListener listener;

    @Test
    void sendsMessageThroughBrokerAndReceivesIt() throws Exception {
        String payload = "order-" + UUID.randomUUID();

        jmsTemplate.convertAndSend(QUEUE, payload);

        assertEquals(
                payload,
                listener.awaitMessage(Duration.ofSeconds(10)));
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class ListenerConfig {

        @Bean
        CapturingOrderListener capturingOrderListener() {
            return new CapturingOrderListener();
        }
    }
}
~~~

Key details:

1. `@Container` declares the Artemis container managed by Testcontainers. Because it is a static field, the container has a test-class lifecycle and is shared across methods in the class.
2. `@Testcontainers` registers the JUnit 5 extension to start the container before tests and stop it afterward.
3. `@DynamicPropertySource` registers properties after Testcontainers provides the dynamic endpoint. The Spring context thus receives the exact broker URL, user, and password.
4. `spring.artemis.mode=native` forces the application to use the broker in the container.
5. `JmsTemplate.convertAndSend` sends the payload through the real JMS provider.
6. `@JmsListener` is managed by the listener container and receives messages asynchronously.
7. `BlockingQueue.poll` waits up to 10 seconds. If the listener does not receive the message, the test fails with a received value of null instead of hanging forever.

The example uses a string to focus on testing connectivity and delivery. For DTOs, configure a `MessageConverter` and write additional tests proving that objects are converted accurately in both directions.

In Spring Boot, listener infrastructure is auto-configured when JMS is on the classpath; you usually do not need to add `@EnableJms` manually. If using plain Spring Framework, declare `@EnableJms`, `ConnectionFactory`, `JmsTemplate`, and an appropriate `JmsListenerContainerFactory`.

## 6. Testing MessageConverter and Typed Payloads

A test sending a String only verifies the transport path for a simple type. If the application sends POJOs, JSON, or messages with custom headers, you must test the real converter.

Scenarios to test:

- Producer creates the proper JMS message type, such as `TextMessage` or `BytesMessage`.
- Consumer decodes into the right DTO type and preserves fields.
- Null fields, Unicode, dates/times, decimals, and collections are serialized per contract.
- Type mapping allows only registered types. Never trust an arbitrary class name from a message property to dynamically load classes.
- Required content type and message properties are preserved.
- Invalid messages produce observable conversion errors handled according to policy.

You can use a shared `MessageConverter` bean so Spring Boot attaches it to both `JmsTemplate` and the auto-configured listener factory. If you create a custom listener factory, configure the corresponding converter on that factory; otherwise, producer and consumer may use two different conversion rules.

Example of sending a message with a correlation ID:

~~~java
String correlationId = UUID.randomUUID().toString();

jmsTemplate.send(QUEUE, session -> {
    var message = session.createTextMessage("order-created");
    message.setJMSCorrelationID(correlationId);
    message.setStringProperty("eventType", "OrderCreated");
    return message;
});
~~~

If correlation ID or properties are part of the contract, the test listener should receive `jakarta.jms.Message` or `TextMessage` and assert both body and headers/properties. Do not check only the payload and ignore metadata.

## 7. Queues, Topics, and Destinations

JMS distinguishes queues and topics:

- **Queue:** a message is typically delivered to one consumer in a competing group. Used for work queues and command processing.
- **Topic:** messages are delivered to active subscribers. You must verify subscriptions, durable subscriptions, and when the subscriber starts listening.

Spring Boot configures `JmsTemplate` and the listener container in queue mode (`pubSubDomain=false`) by default. If testing a topic, configure both producer and listener container for topic mode. Mismatched settings across the two sides cause the test to send to one destination type while the consumer listens to another.

Destinations must be created by the broker or allowed to auto-create per configuration. In production, queues/topics, DLQs, and policies should be managed by broker configuration or deployment infrastructure. Tests can use dedicated destinations such as `orders.integration`; do not share production queues or another test's queue.

For durable topics, verify subscription name, client ID, persistent delivery, and that the subscriber can receive messages sent while offline. Regular subscriber tests only prove that an active subscriber receives messages.

## 8. Transactions, Acknowledgements, and Redelivery

A successful listener typically acknowledges a message after processing. If processing fails, session transactions and broker policies determine whether the message is rolled back, redelivered, or moved to a DLQ.

Spring Boot configures the default listener factory transactionally. If a JTA transaction manager is present, it is attached to the listener container; otherwise, `sessionTransacted` is enabled. You can coordinate local storage transactions with message handling via `@Transactional` on the listener or a service called by the listener. However, do not assume a local transaction automatically produces an atomic commit across independent systems; choose XA/JTA or outbox/inbox when cross-resource consistency is required.

Integration tests should be written for these scenarios:

1. **Successful processing:** listener updates state, message is acknowledged, and does not reappear.
2. **Throwing an exception:** transaction rolls back per configuration, and the broker performs redelivery per policy.
3. **Exhausting retry attempts:** message is moved to the dead-letter queue per policy.
4. **Failure after side effects:** test idempotency so redelivery does not create duplicate records or transactions.
5. **Temporary broker disconnect:** producer/consumer recover per reconnect policy without losing broker-confirmed messages.

Do not test redelivery simply by counting how many times the listener method was called unless the test clearly configures transactions and broker redelivery policy. Invocation counts can differ from how many times the broker actually redelivered the message. Inspect delivery count, queue state, and DLQ using the appropriate broker API/management tools.

In particular, producer-side cancellation or timeout tests do not prove that the broker has not processed the message. When send outcomes are ambiguous, use message IDs, business keys, or idempotency keys to determine state and prevent duplicate side effects.

## 9. Verifying Listener Containers and Asynchronous Handling

`@JmsListener` is not invoked directly by `JmsTemplate`; Spring creates a listener container to receive messages on separate threads. Integration tests need to confirm the container is running and wait for results using a bounded-timeout mechanism.

You can retrieve the container via `JmsListenerEndpointRegistry` if you need to check its state:

~~~java
@Autowired
JmsListenerEndpointRegistry registry;

@Test
void listenerContainerIsRunning() {
    var container =
            registry.getListenerContainer("orders-test-listener");

    assertNotNull(container);
    assertTrue(container.isRunning());
}
~~~

The ID must match the `id` attribute on `@JmsListener`. Checking `isRunning()` only confirms the container is active; send/receive tests are still required to prove messages flow through the broker.

Do not use `JmsTemplate.receive()` as the primary mechanism for asynchronous consumers. `receive` is a synchronous operation that blocks the calling thread. For applications consuming messages continuously, a listener container such as `DefaultMessageListenerContainer` is more suitable.

When configuring concurrency, test the actual number of consumers, message ordering within the scope guaranteed by the broker, and whether concurrent processing introduces race conditions. Do not assume global ordering when multiple competing consumers or multiple producers exist.

## 10. Avoiding Flaky Integration Tests

- Use finite timeouts and polling assertions; avoid `Thread.sleep(1000)` or arbitrary fixed waits.
- Use unique payloads or correlation IDs to identify messages belonging to the current test.
- Do not share destinations across parallel tests if they could consume each other's messages.
- Clear test listener state between methods or use per-test queues.
- Ensure the broker is ready before the Spring context connects.
- Use a static container for tests in the same class to avoid repeatedly restarting the broker.
- If Spring TestContext caches a context across multiple test classes, ensure the container is not stopped while that context is still being reused. You can use a suite-wide singleton container or manage context/container lifecycles consistently.
- When verifying exact message counts, use an isolated destination and assert both count and content.
- Do not leave leftover messages that cause a later test to pick up results from an earlier test.
- Pin broker image and Testcontainers dependency versions for reproducible CI results.

Integration tests require Docker or a compatible container runtime on dev machines and CI. If Docker is unavailable, tests should clearly report that the environment requirements are not met; never silently replace the real broker with a mock and still report that integration tests passed.

## 11. Running Tests and Diagnosing Failures

With Maven:

~~~bash
./mvnw test
~~~

With Gradle:

~~~bash
./gradlew test
~~~

When tests fail, categorize by layer:

| Symptom | What to Check |
| --- | --- |
| Container fails to start | Docker daemon, image pull, architecture, and container logs |
| Connection refused | Broker URL, mapped port, container readiness timing, and transport |
| Authentication failed | Username/password configured in the container and Spring properties |
| Listener does not receive messages | Queue/topic mode, destination name, listener container state, and auto-startup |
| Wrong payload type | MessageConverter, JMS message type, and type mapping |
| Message delivered multiple times | Session transactions, exception path, acknowledgement, and redelivery policy |
| Message lands in DLQ | Broker address/queue policy, retry count, exceptions, and DLQ routing |
| Test passes alone but fails in parallel | Shared destination, leftover messages, container/context lifecycle, and race conditions |

When debugging, read the broker container logs alongside the Spring listener container logs. You can enable appropriate logging for JMS/provider packages in the test profile; avoid logging sensitive payloads or leaving overly verbose logs enabled long-term in CI.

## 12. Recommended Test Scope

| Test Type | Purpose | Real Broker? |
| --- | --- | --- |
| Service unit test | Verify business rules without JMS dependency | No |
| Publisher/listener adapter unit test | Verify mapping and branching using mocks where appropriate | No |
| JMS integration test | Verify ConnectionFactory, JmsTemplate, converter, listener, and destination | Yes |
| Broker policy test | Verify redelivery, DLQ, expiry, persistence, and acknowledgement | Yes |
| End-to-end test | Verify producer, broker, listener, and downstream services working together | Usually in the appropriate pipeline |

You do not need to start a broker for every unit test. Place integration tests in a separate group if starting Docker slows down the suite; however, still run them regularly in CI to catch integration bugs before deployment.

## 13. Completion Checklist

- [ ] Tests use a real broker container and a pinned image version.
- [ ] Testcontainers manages the broker lifecycle and provides dynamic endpoints.
- [ ] Spring Boot is configured with `mode=native`, container URL, username, and password.
- [ ] `JmsTemplate` sends messages through the broker, not a mock.
- [ ] `@JmsListener` receives messages through a real listener container.
- [ ] Tests verify payload content with explicit timeouts.
- [ ] MessageConverter, headers, and properties are tested if part of the contract.
- [ ] Queue/topic mode and destinations are configured consistently.
- [ ] Transactions, acknowledgement, redelivery, and DLQ are tested when the application relies on them.
- [ ] Tests isolate destinations and do not leak messages across methods.
- [ ] Container lifecycle is compatible with Spring context caching.
- [ ] CI has Docker/container runtime and runs the integration test suite.

## References

- [Spring Boot — JMS](https://docs.spring.io/spring-boot/reference/messaging/jms.html): auto-configuration of ConnectionFactory, JmsTemplate, @JmsListener, Artemis, and listener transactions.
- [Spring Framework — JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html): JmsTemplate, listener containers, message conversion, and transaction support.
- [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/): example of JmsTemplate sending messages and @JmsListener receiving messages.
- [Testcontainers for Java — ActiveMQ and Artemis](https://java.testcontainers.org/modules/activemq/): ArtemisContainer, credentials, and module dependency.
- [Testcontainers for Java — JUnit 5](https://java.testcontainers.org/test_framework_integration/junit_5/): @Testcontainers, @Container, and container lifecycle.
- [Apache ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html): official image, messaging ports, and broker startup environment variables.

