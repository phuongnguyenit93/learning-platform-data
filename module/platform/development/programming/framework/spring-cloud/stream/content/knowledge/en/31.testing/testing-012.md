# Testing Restarts, Network Failures, and Incident Recovery

A Spring Cloud Stream application must continue processing properly when the process restarts, the broker temporarily stops, the network connection drops, or an external dependency becomes unresponsive. Testing these scenarios confirms that the application reconnects, resumes from the right position, handles redelivered messages, and avoids unintended duplicate side effects.

With the Supplier, Function, and Consumer model, both sending and receiving paths must be tested. For Kafka, RabbitMQ, or Pulsar, each binder has its own mechanisms for storing read positions, acknowledgements, retries, and redelivery. Therefore, a test running functions solely in the JVM cannot prove the resilience of a system running against a real broker.

## 1. Objectives of Recovery Testing

A recovery test should answer concrete questions:

- Can the application start when the broker is temporarily unavailable?
- Does the producer resume sending after connectivity is restored?
- Does the consumer reconnect and continue receiving messages?
- Are messages that were in-flight when the process stopped redelivered?
- Are read positions or acknowledgements persisted properly?
- Can a message be reprocessed, and are side effects duplicated?
- Do business errors go through retries and then to the DLQ as configured?
- After the broker or application comes back up, is the backlog fully drained?
- Does the consumer group, queue, or subscription retain its identity across restarts?

Do not merely check that logs contain "connected" or health status turns UP. Verify business outcomes in durable storage and inspect broker state.

## 2. Three Complementary Testing Layers

| Layer | Component Under Test | Can Verify | Cannot Prove on Its Own |
|---|---|---|---|
| Unit test | Business logic, idempotency, mapping, application retry policy | Function output for given inputs | Broker connectivity, offsets, acknowledgements, reconnection |
| Test Binder | Function/Consumer, bindings, and in-JVM message routing | Basic wiring and fast processing results | Network errors, broker restarts, partition rebalancing, persistence |
| Integration/resilience test | Application with real broker and test infrastructure | Reconnection, redelivery, offsets, DLQ, incident recovery | Every production scenario if test topology is overly simplified |

Spring Cloud Stream provides the Spring Integration Test Binder to test applications without a broker. This binder runs in the JVM using internal channels. It is useful for verifying function logic and binding names, but it does not emulate sockets, broker elections, consumer groups, or message persistence.

A balanced test suite uses the Test Binder for fast logic checks, then uses broker containers or integration environments for operational scenarios.

## 3. Testing Logic with the Test Binder Before Injecting Infrastructure Faults

Spring Cloud Stream test dependency:

~~~kotlin
testImplementation("org.springframework.cloud:spring-cloud-stream-test-binder")
~~~

Example Function receiving an order event and normalizing status:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderEvent(String orderId, String status) {}

@Configuration
class OrderFunctions {

    @Bean
    Function<OrderEvent, OrderEvent> normalizeOrder() {
        return event -> new OrderEvent(
                event.orderId(),
                event.status().trim().toUpperCase());
    }
}
~~~

The Test Binder can verify bindings and Function output:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.cloud.stream.binder.test.EnableTestBinder;
import org.springframework.context.annotation.Import;
import org.springframework.messaging.support.GenericMessage;

@SpringBootTest(classes = OrderFunctionTest.TestApplication.class)
class OrderFunctionTest {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void normalizesOrderStatus() {
        input.send(new GenericMessage<>(
                "{\"orderId\":\"O-100\",\"status\":\" paid \"}".getBytes()),
                "normalizeOrder-in-0");

        var result = output.receive(2_000, "normalizeOrder-out-0");

        assertThat(result).isNotNull();
        assertThat(new String(result.getPayload()))
                .contains("\"status\":\"PAID\"");
    }

    @SpringBootApplication
    @EnableTestBinder
    @Import(OrderFunctions.class)
    static class TestApplication {}
}
~~~

Adapt this example to how your application configures component scanning, serializers, and test configuration. The goal of this test is to verify the function works with bindings; it is not a restart test.

## 4. Setting Up a Real Broker Environment for Integration Tests

Testcontainers provides modules for Kafka, RabbitMQ, and Apache Pulsar. Each test can start a disposable broker, provide its dynamic address to Spring Boot, and clean up the container afterward.

Example Gradle dependencies when the project manages Testcontainers versions via a BOM:

~~~kotlin
testImplementation("org.testcontainers:testcontainers")
testImplementation("org.testcontainers:testcontainers-kafka")
testImplementation("org.testcontainers:testcontainers-rabbitmq")
testImplementation("org.testcontainers:testcontainers-pulsar")
testImplementation("org.testcontainers:testcontainers-toxiproxy")
~~~

Only add modules for brokers that the test suite actually uses. There is no need to start all three brokers for every test.

For Kafka, Spring Kafka provides Embedded Kafka and test utilities. An embedded broker works well for many lightweight integration tests, while restart, network interruption, or multi-broker tests need an environment with explicit broker lifecycle control. Testcontainers runs brokers in containers and pairs with Toxiproxy to inject network faults.

If the application uses the Kafka binder and wants to use an embedded broker, ensure the test binder does not replace the Kafka binder in that test. Spring Kafka notes that Spring Cloud Stream's test support dependency can auto-select the Test Binder; tests using a real broker must exclude the corresponding Test Binder configuration.

Example integration test skeleton using a Kafka container:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.kafka.KafkaContainer;

@Testcontainers
@SpringBootTest(properties = {
        "spring.autoconfigure.exclude="
                + "org.springframework.cloud.stream.test.binder.TestSupportBinderAutoConfiguration"
})
class KafkaBinderRecoveryIT {

    @Container
    static final KafkaContainer kafka =
            new KafkaContainer("apache/kafka-native:3.8.0");

    @DynamicPropertySource
    static void brokerProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.cloud.stream.kafka.binder.brokers",
                kafka::getBootstrapServers);
    }

    @Test
    void brokerIsAvailableForTheApplication() {
        // Send and receive messages through real bindings; other tests
        // orchestrate restarts or network faults.
    }
}
~~~

This is a test skeleton; Kafka image version, Testcontainers API, and binder properties must match your project's dependencies. This test uses the real Kafka binder, not the Test Binder in the same context.

## 5. Setting Stable Consumer Groups or Subscriptions

Resuming after restarts depends on consumer identity:

| Broker | Identity to Keep Stable | What to Verify |
|---|---|---|
| Kafka | Consumer group | Committed offsets continue to be used after a new instance joins |
| RabbitMQ | Queue and group bindings | Durable queue persists and unacked messages are redelivered |
| Pulsar | Subscription name | Subscription cursor and subscription type persist across reconnects |

With Kafka, declare the group explicitly:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
~~~

When the application restarts with the same group, the consumer resumes from the committed offset per configuration. Properties like start-offset `earliest` usually only determine the initial position for a new group without existing offsets; it does not mean reading from the beginning on every restart. Do not change the group ID across deployments if the goal is to resume saved progress.

With RabbitMQ, the queue used for a consumer group must have an appropriate lifecycle. Temporary or auto-delete queues can vanish when consumers disconnect, altering how messages are retained. With Pulsar, subscription names must remain stable so the cursor continues rather than creating an unrelated new subscription.

## 6. Testing Application Restarts

Application restart scenarios should test both completed messages and in-flight messages:

1. Start producer and consumer with a fixed group/subscription.
2. Send a batch of messages with unique IDs, e.g., EVT-001 through EVT-020.
3. Wait for part of the messages to be processed and confirm results are durably stored.
4. Stop the consumer deliberately; for crash scenarios, terminate the process abruptly rather than closing the context gracefully.
5. While the consumer is stopped, keep sending additional messages.
6. Start the consumer with the same configuration and same group/subscription.
7. Wait for the backlog to be processed.
8. Verify all expected messages produced outcomes and no unintended duplicate side effects occurred.

Graceful shutdown and crashes are two distinct scenarios. On graceful shutdown, the listener container can stop accepting new messages, finish in-flight work, and commit offsets/acks per configuration. When the process is killed, in-flight messages may remain unacknowledged and be redelivered.

Include at least two separate tests:

- **Graceful restart:** verify the application stops in a controlled manner and resumes from the saved position.
- **Abrupt termination:** verify unacknowledged messages are redelivered and the application handles duplicates safely.

## 7. Testing Broker Restarts and Reconnection

A broker restart differs from an application restart. In this test, keep the application running, stop the broker or make it unreachable, then start the broker again.

Basic steps:

1. Start the broker and the application.
2. Verify producer and consumer are connected.
3. Send a baseline message to verify the normal path.
4. Stop the broker or temporarily sever the network between application and broker.
5. During the outage, attempt sends and observe errors per producer semantics.
6. Restore the broker or network connectivity.
7. Wait for clients to reconnect and the consumer group/queue/subscription to become active again.
8. Send a new test message.
9. Verify the message is received, processed, and stored.
10. Reconcile messages sent during the broker outage to determine which were retried and which must be resent by the application.

Do not assume the producer buffers every message in memory indefinitely while the broker is down. Outcomes depend on timeouts, retries, buffers, binders, and send APIs. Applications must handle send failures and decide whether to persist to an outbox or retry at the business layer.

For multi-broker Kafka, a single broker in Testcontainers does not fully simulate leader election, replica ISR, or quorum loss. If recovery requirements involve replication, run a multi-broker test cluster and stop the broker holding a partition leader to verify clients switch to the new leader.

## 8. Simulating Network Faults with Toxiproxy

Testcontainers Toxiproxy places a TCP proxy between the application and the broker. Tests can inject latency, limit bandwidth, or sever connections to test reconnection and timeouts.

A test topology can look like:

~~~text
Spring Cloud Stream application
             |
             v
         Toxiproxy
             |
             v
       Kafka / RabbitMQ / Pulsar
~~~

Testcontainers lets you create a proxy to a broker on the same Docker network. For example, the proxy control API can create a proxy named kafka listening on a test port and forwarding to the internal broker address. Then configure the application to connect through the proxy address instead of connecting directly to the broker.

Useful fault types:

| Network Fault | Purpose |
|---|---|
| Cut both TCP directions | Simulate sudden connection loss |
| Cut upstream only | Test producer/client inability to send data |
| Cut downstream only | Test client inability to receive responses or acknowledgements |
| Add latency and jitter | Test timeouts and backoff |
| Limit bandwidth | Test backlogs, throughput, and recovery time |
| Slow socket close | Test handling of hung or delayed connection closures |

Conceptual Toxiproxy control example:

~~~java
// Proxy has been created and is forwarding to the broker.
proxy.toxics().bandwidth(
        "cut-upstream",
        ToxicDirection.UPSTREAM,
        0);

proxy.toxics().bandwidth(
        "cut-downstream",
        ToxicDirection.DOWNSTREAM,
        0);

// After verifying the application detects the fault, remove both toxics.
proxy.toxics().get("cut-upstream").remove();
proxy.toxics().get("cut-downstream").remove();
~~~

This snippet illustrates the Toxiproxy API; create the container, network, proxy, and broker address beforehand. When cutting connectivity, tests must wait until the application observes the failure; after removing toxics, verify clients reconnect and process new messages.

Toxiproxy tests TCP faults. It does not simulate all DNS failures, TLS certificate issues, broker authentication failures, broker logic bugs, or application-level network partitions. Test those separately if included in your threat model.

## 9. Distinguishing Business Errors from Connection Errors

Business errors occur once a message reaches the application yet the Function/Consumer cannot process it—such as malformed schema or violated business rules. Connection errors occur when clients cannot communicate with the broker or fail to receive responses on time.

| Error Type | Example | Behavior to Verify |
|---|---|---|
| Transient business error | Database timeout, temporary auxiliary API outage | Retry with backoff and attempt limit |
| Unrecoverable business error | Malformed payload, missing required field | Route to DLQ or error flow; avoid infinite retries |
| Broker error | Broker restart, leader switchover | Client reconnects; producer/consumer resumes per config |
| Network error | TCP reset, timeout, lost route | Bounded timeouts, reconnect, and recovery |
| Authentication error | Expired or wrong credentials | Fail loudly; do not retry infinitely like transient errors |
| Schema error | Incompatible producer and consumer | Do not loop endlessly on an undecodable payload |

A network failure can happen after the broker received a message yet before the producer receives its acknowledgement. In that case, the producer is unsure whether the broker persisted the message. Application-level retries can create duplicates. This is why stable event IDs and idempotent consumers are essential.

## 10. Verifying Offsets and Acknowledgements at the Right Time

Recovery testing must verify when a message is acknowledged:

- Kafka: offsets commit only per acknowledgement mode, transaction, or container config. If side effects complete yet the process stops before committing offsets, the message may be redelivered.
- RabbitMQ: unacked messages may be requeued/redelivered when a consumer or connection drops. Verify durable queues, acknowledgement mode, and reject/requeue/DLQ config.
- Pulsar: acknowledgement mode can be BATCH, RECORD, or MANUAL in Spring for Apache Pulsar. Redelivery depends on ack timeouts, nacks, and subscription types.

Do not verify solely by counting how many times a Function was called. Cross-check message IDs, created business records, offset/ack state, and DLQ state.

For Kafka, read group offsets using admin tools or the Admin API in integration tests. For RabbitMQ, inspect queue depth, unacked counts, and dead-letter queues. For Pulsar, inspect subscription backlogs and redelivery/DLQs.

## 11. Testing the Duplicate Window When an Application Crashes

A critical failure window occurs when side effects finish yet the acknowledgement has not been persisted:

~~~text
Consumer receives EVT-100
        |
        v
Writes business result to database
        |
        v
Process terminates before ack/commit
        |
        v
Broker redelivers EVT-100
        |
        v
Consumer re-executes the same business logic
~~~

If the consumer is not idempotent, the database may record twice, a payment may be charged twice, or an email may be sent repeatedly.

A common safeguard is recording the event ID in a deduplication table within the same transaction as the business update:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Example implementation for PostgreSQL:

~~~java
record OrderCreated(String eventId, String orderId) {}

// Method resides in a service with jdbcTemplate and orderRepository injected.
@Transactional
public void handle(OrderCreated event) {
    int inserted = jdbcTemplate.update("""
            INSERT INTO processed_events(event_id, processed_at)
            VALUES (?, CURRENT_TIMESTAMP)
            ON CONFLICT (event_id) DO NOTHING
            """, event.eventId());

    if (inserted == 0) {
        return;
    }

    orderRepository.apply(event);
}
~~~

If the event ID already exists, the handler skips the already-completed side effect. Because the dedup insert and business update share the same database transaction, a crash between the two operations rolls back both; redelivery can safely reprocess it.

This example assumes a database supporting PostgreSQL syntax and operations sharing the same transaction manager. If side effects happen in an external system, use an idempotency key or outbox/inbox workflow; a database transaction does not automatically cover HTTP APIs or payment systems.

## 12. Testing Retries and DLQs After an Incident

After a broker or dependency recovers, a message with a business error may still need retries or DLQ routing. Tests must distinguish recoverable transient errors from unprocessable poison messages.

Example Kafka consumer configuration with group, retry, and DLQ:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
          consumer:
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 5000
            back-off-multiplier: 2
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.events.order-processor.dlq
~~~

With the Kafka binder, DLQ requires an explicit consumer group. Once retries are exhausted while the handler still fails, the record is sent to the configured DLQ. Broker/network errors and exceptions thrown by a Function do not necessarily go through the same retry mechanism; test client reconnection behavior separately from binder message-handler retries.

With the RabbitMQ binder, use autoBindDlq, maxAttempts, republishToDlq, or dead-letter exchanges/queues as needed. Avoid infinite requeue configuration for poison messages as it can cause continuous redelivery loops.

With Pulsar, acknowledgement timeouts or negative acknowledgements can trigger redelivery. Pulsar's native dead-letter topic has restrictions by subscription type; Spring for Apache Pulsar documentation describes native DLQ for Shared subscriptions. Check the exact semantics of your deployed binder/client before assuming all subscription types behave identically.

A good DLQ test verifies:

1. The failing message is delivered the expected number of attempts.
2. The message moves to the exact DLQ after retries are exhausted.
3. Source metadata and error details are preserved well enough for investigation.
4. The primary consumer continues processing subsequent messages if policy permits.
5. Redriving from the DLQ does not create duplicate side effects.

## 13. Testing RabbitMQ Reconnection and Redelivery

The Spring AMQP listener container can restart consumers when connections drop. If the broker is unavailable when the container starts, the container can keep trying to connect per recovery backoff.

RabbitMQ scenario:

- Send messages to a durable queue before stopping the consumer.
- Stop RabbitMQ or sever the TCP proxy.
- Verify producer/consumer observe connection errors per config.
- Restart the broker or remove the network fault.
- Verify the listener container recreates the consumer.
- Verify unacked messages are redelivered.
- Inspect the redelivered header or delivery metadata to distinguish redeliveries.
- Verify the queue and DLQ still exist after broker restart.

If the queue is auto-delete or exclusive, behavior after connection loss differs from durable queues. Tests must use the exact queue type deployed in production.

## 14. Testing Pulsar Acknowledgements and Redelivery

With Spring for Apache Pulsar, the ack mode directly affects how messages are acknowledged:

The semantics below apply to Spring for Apache Pulsar. If the application uses a dedicated Pulsar binder for Spring Cloud Stream, check how that binder maps acknowledgements and redelivery to the Pulsar client in your exact deployed version.

| Ack Mode | Behavior to Verify |
|---|---|
| BATCH | Messages in the batch are acked when batch processing succeeds; errors may nack failed messages |
| RECORD | Ack or nack per individual record in single-record mode |
| MANUAL | Application calls acknowledge or nack directly; every exception branch must be tested |

A consumer crash before ack can cause message redelivery. An ack timeout greater than 0 can also trigger redelivery of unacked messages. When using negative acknowledgements, delay/backoff controls redelivery timing.

For batch listeners, specifically test how a single failing record within a batch is handled. Do not assume RECORD ack mode works for every batch listener; APIs and limits depend on the Spring Pulsar version.

## 15. Testing Backlogs and Recovery Speed

After an extended outage, a consumer may face a large backlog. Verifying that one new message arrives is not enough.

Create a backlog of known size, e.g., 5,000 events with unique IDs:

1. Pause the consumer or cut connectivity.
2. Send the backlog to the broker.
3. Restore the consumer.
4. Measure the time from reconnect until the first message is received.
5. Measure consumption throughput and time until backlog reaches 0.
6. Monitor consumer lag, queue depth, or subscription backlog.
7. Verify the count of unique business events processed equals the expected count.

Set recovery thresholds based on actual SLOs. Do not set test timeouts so tight that tests flake on slow CI machines, yet never use infinite timeouts that mask a consumer failing to reconnect.

## 16. Recommended Scenario Matrix

| Scenario | How to Inject Fault | Outcome to Verify |
|---|---|---|
| Consumer graceful restart | Controlled context/process stop | Consumer rejoins same group/subscription and resumes progress |
| Consumer crash mid-processing | Kill process after side effect, before ack/commit | Message is redelivered; idempotency blocks duplicate side effects |
| Broker restart | Stop then start broker | Client reconnects; queues/topics/subscriptions and durable data stay intact |
| TCP connection reset | Cut proxy in both directions | Client detects error and reconnects |
| Network blackhole | Hold connection open without passing data | Bounded timeout triggers; recovers afterward |
| High latency | Inject delay/jitter | Timeouts/backoff do not trigger retry storms |
| Temporary dependency outage | Make auxiliary API/database return errors | Bounded retries; succeeds once dependency returns |
| Poison message | Send invalid payload | Bounded retries then DLQ/error path |
| Consumer scale up/down | Vary instance count | Rebalancing/assignment drops no messages |
| Large backlog | Produce many messages while consumer is stopped | Backlog drains within SLO |
| DLQ redrive | Replay a fixed message | Event processes properly without repeating side effects |

Not every scenario must run on every pull request. Run unit/Test Binder tests frequently, broker integration tests in CI, and long-running chaos tests or multi-broker cluster tests on a schedule or before major releases.

## 17. Using Awaitility to Wait on Conditions Instead of Fixed Sleeps

In integration tests, reconnection timing depends on the broker, container runtime, and CI. Instead of sleeping for a fixed time and assuming recovery completed, wait for an observable condition with a timeout:

~~~java
import static org.awaitility.Awaitility.await;
import static java.util.concurrent.TimeUnit.SECONDS;

await()
        .atMost(30, SECONDS)
        .pollInterval(200, java.util.concurrent.TimeUnit.MILLISECONDS)
        .untilAsserted(() -> {
            assertThat(orderRepository.countByEventId("EVT-200"))
                    .isEqualTo(1);
        });
~~~

Wait conditions should assert meaningful business outcomes or broker state, not merely a log line. When a test times out, print consumer group/offset details, queue depth, DLQ depth, and container status to aid investigation.

## 18. Mistakes That Make Recovery Tests Unreliable

- Using the Test Binder and concluding the application can reconnect to Kafka or RabbitMQ.
- Using a random consumer group on every startup so tests inadvertently re-read the entire topic.
- Sharing topics/queues across tests so stale messages corrupt results.
- Only counting handler invocations without checking side effects and duplicates.
- Using a single Kafka broker to conclude cluster replication/leader election works properly.
- Cutting the network without waiting for the client to detect the fault before restoring it.
- Using fixed `Thread.sleep` instead of condition waits.
- Infinite retries causing tests to hang or poison messages to stall consumers.
- Skipping DLQ or backlog verification after tests finish.
- Failing to isolate data and clean queues/topics/subscriptions so subsequent tests receive stale messages.
- Testing only graceful shutdown while skipping abrupt crashes during message processing.

## 19. Post-Recovery Observability

To know whether an application has truly recovered, monitor:

- Producer and consumer connection states.
- Reconnect counts and time from error to reconnection.
- Consumer lag, queue depth, or subscription backlog.
- Offset commit or acknowledgement rates.
- Redelivery and retry counts.
- Messages entering DLQs.
- Duplicate event ID rate skipped by idempotency.
- Post-incident backlog drain rate.
- Authentication, TLS, serialization, and provisioning errors.

Logs should include event ID, destination/topic, group/subscription, attempt number, and correlation ID. Never log sensitive payloads. Metrics should distinguish broker errors from business errors so operators do not mistake a network outage for a poison-message wave.

## 20. Pre-Release Checklist

- Test Binder verified Supplier/Function/Consumer logic and bindings.
- Integration tests use real brokers for critical send/receive paths.
- Consumer groups, queues, or subscriptions have stable identities.
- Both graceful restart and abrupt termination tests exist.
- Broker restart or severed-connection tests exist.
- Latency/timeout and reconnection tests exist.
- Verified offsets/acks are saved only per intended semantics.
- Critical side effects have idempotency or inbox/deduplication.
- Retries are bounded and poison messages route to DLQ/error flows.
- Redrive is tested and avoids repeating side effects.
- Backlogs drain within SLO timelines.
- Tests isolate topics/queues/subscriptions and clean up state after execution.
- Logs, metrics, and alerts for reconnection, lag, redelivery, and DLQs are in place.

Testing restarts, network failures, and incident recovery must verify both reconnection capability and business outcomes after messages are redelivered. The Test Binder verifies in-JVM logic; broker containers and Toxiproxy verify brokers, offsets/acks, reconnection, and network faults. Because Kafka, RabbitMQ, and Pulsar binders have different semantics, test the right groups, queues, or subscriptions, verify retries/DLQs, and design idempotent consumers for crash windows occurring after side effects yet before acknowledgements.

## References

- [Spring Cloud Stream — Testing with the Spring Integration Test Binder](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Spring Kafka — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring Kafka — Listener Container and Offset Commits](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring AMQP — Recovering from Errors and Broker Failures](https://docs.spring.io/spring-amqp/reference/4.0/amqp/resilience-recovering-from-errors-and-broker-failures.html)
- [Spring Cloud Stream — Kafka Retry and DLQ](https://docs.spring.io/spring-cloud-stream/reference/5.0/kafka/kafka-binder/retry-dlq.html)
- [Spring Cloud Stream — RabbitMQ Binder DLQ and Retry](https://docs.spring.io/spring-cloud-stream-binder-rabbit/docs/current/reference/html/overview.html)
- [Spring for Apache Pulsar — Message Acknowledgment and Redelivery](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-consumption.html)
- [Testcontainers — Toxiproxy Module](https://java.testcontainers.org/modules/toxiproxy/)
- [Testcontainers — Kafka Module](https://java.testcontainers.org/modules/kafka/)
- [Testcontainers — RabbitMQ Module](https://java.testcontainers.org/modules/rabbitmq/)
- [Testcontainers — Apache Pulsar Module](https://java.testcontainers.org/modules/pulsar/)
