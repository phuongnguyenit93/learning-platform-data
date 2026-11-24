# Priority and Why Prioritization Does Not Replace an Ordering Contract in Spring JMS

## 1. The Problem: Should More Important Messages Be Processed First?

A queue holds two events for the same order:

1. `OrderCreated(order-42, sequence=1)` is sent first, priority 4.
2. `OrderCancelled(order-42, sequence=2)` is sent second, priority 8.

The development team wants the cancellation event processed quickly because the customer is waiting. If the broker delivers `sequence=2` to a consumer before `sequence=1`, the consumer might attempt to cancel an order not yet created in its own store. **That is not necessarily a broker bug:** JMS priority can alter delivery order, whereas the rule *Created must be applied before Cancelled* is a separate business contract.

Three questions must be distinguished:

- **Delivery priority:** does the broker try to deliver urgent messages earlier?
- **Delivery/receive order:** when does the Jakarta Messaging specification impose ordering constraints on messages?
- **Business application order:** does the system guarantee state updates happen in the right sequence, even when messages arrive late, are redelivered, or multiple consumers work concurrently?

`JMSPriority` affects the first question; it **does not replace** defining and enforcing a business ordering contract.

### Learning Objectives

After this lesson, you will be able to identify the valid priority value range, configure priority on `JmsTemplate` so it actually takes effect, explain the exceptions to JMS ordering rules, design consumers with `aggregateId`/`sequence` to detect out-of-order arrivals, and test priority without turning "best effort" behavior into a false assertion.

## 2. What Is JMSPriority?

Jakarta Messaging defines **10 integer priority levels from 0 to 9** for messages:

| Value | Specification Meaning |
| --- | --- |
| `0` | Lowest level |
| `1..3` | Levels in the normal priority group |
| `4` | Default level, still in the normal group |
| `5..8` | Levels in the expedited delivery priority group |
| `9` | Highest level |

According to the API, `0..4` should be viewed as *normal priority* levels, and `5..9` as *expedited priority*. Providers are required to **try** to deliver expedited messages ahead of normal messages, but the specification **does not require providers to maintain a strictly sorted priority queue**. Broker configuration, already-dispatched/prefetched messages, consumer count, and system load all influence observed results.

Key points:

- `JMSPriority` is a **JMS standard header** of type `int`, read via `message.getJMSPriority()`.
- Priority is chosen at **send time**, via `MessageProducer.setPriority(...)` or a `send(...)` overload taking QoS parameters. In Spring, `JmsTemplate` exposes a `priority` property used on send.
- Do not call `message.setJMSPriority(8)` inside a `MessageCreator` as a way to configure priority. The `jakarta.jms.Message` API documentation states that this setter is for the **provider** to populate the header during send.
- Priority is **not** `deliveryMode` (persistent/non-persistent), `timeToLive` (expiration), `deliveryDelay` (delayed availability), or **consumer priority** (consumer dispatch preference on some brokers). Each has a distinct purpose and behavior.

> **Rule:** "priority 8" means send the message with priority level 8; it does not mean "must be processed ahead of all priority 4 messages," nor does it mean "process within 8 seconds."

## 3. Priority, Receive Order, and Processing Order Are Three Different Layers

Consider the following diagram:

```text
Producer                              Broker                  Consumer
--------                              ------                  --------
send A, priority 4  ----------------> queue
send B, priority 8  ----------------> queue
                                       |
                         provider chooses dispatch order
                                       |
                             B? -------+------> process B?
                             A? --------------> process A?

Separate business contract for order-42:
apply sequence=1  ->  apply sequence=2
```

**In what order can A and B arrive?** It depends on conditions and the provider. If the consumer already received A before B arrived, B cannot "turn back time" to arrive before A. If both are waiting on the broker, B may be prioritized and overtake A; however, that is not guaranteed. If multiple consumers receive concurrently, the **business task completion order** can also differ from the order in which individual messages were delivered to consumers.

A table of distinctions:

| Aspect | What Can Be Relied On? | What Must Not Be Inferred? |
| --- | --- | --- |
| Priority | A priority level from `0` to `9` is send metadata on the message; providers try to expedite higher levels | Higher priority will definitely overtake every lower priority |
| JMS message order | The spec imposes ordering constraints for messages sent by one session to the same destination, **with defined exceptions** | All messages on the broker always follow a global FIFO |
| Queue with multiple consumers | Each queue message is distributed to one eligible consumer | All consumers process strictly in send order; completion order matches receive order |
| Multiple producers/sessions | Ordering must be explicitly designed if cross-stream coordination is needed | JMS guarantees order across messages sent from different sessions |
| Business consistency | Sequence numbers, idempotency, per-aggregate synchronization, and gap/out-of-order handling | Having priority eliminates the need for sequence numbers or concurrency control |

## 4. What Does the Jakarta Messaging Specification Actually Mandate for Ordering?

Section **6.2.9 Message order** of Jakarta Messaging 3.1 mandates *partial ordering*, not global FIFO.

### 4.1. Scope Where Ordering Applies

For messages sent by a single `Session` to **the same destination**, the specification requires receive order to follow send order, **after accounting for exceptions**. Important exceptions include:

1. **Higher priority may overtake** lower-priority messages sent earlier.
2. Messages with a **later delivery time** may be delivered after messages with an earlier availability time.
3. `NON_PERSISTENT` messages may be lost on provider failure.
4. When mixing `PERSISTENT` and `NON_PERSISTENT`, no overall ordering may be inferred across the two delivery modes; the spec maintains ordering constraints within each delivery mode and its applicable conditions.
5. Transactions can group sent messages into an atomic JMS unit; ordering within a transaction for **one destination** is meaningful, without implying ordering across multiple destinations.

Example when all relevant conditions are held constant:

```text
Same Session, same queue Q, same priority and delivery mode,
no delivery delay intervening:
send A -> send B -> send C
  JMS ordering constraint applies on the receiving side.

Same Session, Q:
send A (priority=4) -> send B (priority=8)
  B may overtake A under the priority exception.

Session S1 sends A; Session S2 sends B:
  No cross-session ordering guaranteed by JMS.
```

Note: multiple independent calls to `JmsTemplate.send(...)` **do not automatically share a single continuous `Session`**. The template may acquire sessions via a connection/session factory or a transaction-bound session. Therefore, do not rely on "two consecutive Java lines calling `send`" to assume all conditions of session-level ordering hold.

### 4.2. Factors That Alter Observed Order

- **Concurrent consumers:** multiple listener container threads receive different messages. A slower task can finish after a task that arrived later.
- **Prefetch/client buffering:** messages may already have been dispatched into a consumer's buffer before a high-priority message reaches the broker.
- **Redelivery:** rollbacks, errors, or dropped connections can cause messages to be redelivered; applications need idempotency.
- **Selectors, topic subscriptions, multiple destinations:** each consumer sees only matching messages; global order cannot be inferred from a single consumer's logs.
- **Delayed delivery, expiration, and mixed delivery modes:** messages become eligible at different times or cease to be available.
- **Provider-specific policy:** with the same priority values, different brokers can apply different scheduling and prefetch algorithms.

Even within a single sequential consumer, "received in order" and "persisted data successfully in order" are two different states. If a handler delegates work to an executor and immediately acknowledges, parallel execution can still invert the order.

## 5. Why setPriority Might Not Take Effect in JmsTemplate

`org.springframework.jms.core.JmsTemplate` supports Quality of Service (QoS) properties:

- `setDeliveryMode(int)`: persistent/non-persistent mode.
- `setPriority(int)`: priority level 0..9.
- `setTimeToLive(long)`: time to live in milliseconds; 0 typically means no TTL expiration.
- `setExplicitQosEnabled(boolean)`: determines whether the template uses **its own QoS values** when sending.

**Key point:** calling `template.setPriority(8)` alone is **not enough**. You must enable `template.setExplicitQosEnabled(true)` if you want `JmsTemplate` to pass the configured QoS values into the send call. When this flag is off, sends use the default QoS of the `MessageProducer`/provider, which may have been administratively configured outside the application.

Simple example:

```java
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setPriority(8);
template.setExplicitQosEnabled(true);
```

This is a **Java snippet inside a configuration method** with a `connectionFactory` variable of type `jakarta.jms.ConnectionFactory`. You do not need to manually create a `MessageProducer` just to set one priority level for all messages sent by a template.

Important warning: enabling explicit QoS causes **deliveryMode, priority, and timeToLive** to all come from the `JmsTemplate` configuration, not just priority. If the broker has its own default delivery mode/TTL policies, determine and declare all three desired values; do not accidentally alter message durability or lifetime just to raise priority.

## 6. Spring Boot 3.x Example: Normal and Urgent Using Two JmsTemplates

This example uses Java 17+, Spring Boot 3.x/Spring Framework 6.x, and ActiveMQ Artemis. It assumes the broker is running, queue `orders.events` exists, and the user has send permission; this is a **Spring Boot application**, not a standalone Java SE program built with just `javac`.

Goal: send `OrderCreated` with priority 4 and `OrderCancelled` with priority 8 to **the same queue**. A successful send **does not promise** the consumer will receive the cancellation event before the creation event.

### 6.1. Dependencies and External Configuration

In a Spring Boot Gradle Groovy DSL project that already has the Boot plugin and dependency management, add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
```

File `src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: "${JMS_BROKER_URL:tcp://localhost:61616}"
    user: "${JMS_USER}"
    password: "${JMS_PASSWORD}"

app:
  jms:
    destination: "${ORDERS_EVENTS_QUEUE:orders.events}"
```

Broker credentials and destination must be provisioned in the target environment. Spring does not automatically guarantee a physical queue exists simply because you typed a queue name in YAML.

### 6.2. Creating Two Templates with Explicit QoS

File `src/main/java/demo/priority/JmsPriorityConfiguration.java`:

```java
package demo.priority;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class JmsPriorityConfiguration {

    @Bean("normalJmsTemplate")
    public JmsTemplate normalJmsTemplate(ConnectionFactory connectionFactory) {
        return createTemplate(connectionFactory, 4);
    }

    @Bean("urgentJmsTemplate")
    public JmsTemplate urgentJmsTemplate(ConnectionFactory connectionFactory) {
        return createTemplate(connectionFactory, 8);
    }

    private static JmsTemplate createTemplate(
            ConnectionFactory connectionFactory, int priority) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        template.setPriority(priority);
        template.setTimeToLive(0L);
        return template;
    }
}
```

Because both templates are pre-configured singletons, services can reuse them safely under `JmsTemplate`'s contract. Do not mutate `setPriority` on a shared singleton across threads to handle individual requests: that is **mutating shared state**. Two clearly named templates avoid confusion in the example.

`DeliveryMode.PERSISTENT` and TTL 0 are illustrative choices that **must be checked against infrastructure policy** before adoption. They do not by themselves turn processing into exactly-once.

### 6.3. Service Sending Messages with Explicit Sequence

File `src/main/java/demo/priority/OrderEventPublisher.java`:

```java
package demo.priority;

import jakarta.jms.TextMessage;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final JmsTemplate normalTemplate;
    private final JmsTemplate urgentTemplate;
    private final String destination;

    public OrderEventPublisher(
            @Qualifier("normalJmsTemplate") JmsTemplate normalTemplate,
            @Qualifier("urgentJmsTemplate") JmsTemplate urgentTemplate,
            @Value("${app.jms.destination}") String destination) {
        this.normalTemplate = normalTemplate;
        this.urgentTemplate = urgentTemplate;
        this.destination = destination;
    }

    public void publishCreated(String orderId) {
        send(normalTemplate, "OrderCreated", orderId, 1L);
    }

    public void publishCancelled(String orderId) {
        send(urgentTemplate, "OrderCancelled", orderId, 2L);
    }

    private void send(
            JmsTemplate template, String eventType,
            String orderId, long sequence) {
        template.send(destination, session -> {
            TextMessage message =
                    session.createTextMessage(eventType + ":" + orderId);
            message.setStringProperty("eventType", eventType);
            message.setStringProperty("aggregateId", orderId);
            message.setLongProperty("sequence", sequence);
            return message;
        });
    }
}
```

`aggregateId` and `sequence` are **application properties** used to check business ordering. `JMSPriority` is a **standard header** populated by the provider from the send QoS. Do not call `message.setJMSPriority(...)` inside the callback; the code relies on each template's priority level.

This example uses fixed sequence numbers 1 and 2 to observe two messages. In a real application, the sequence must come from a controlled state source (database/aggregate/outbox) and increment consistently per `aggregateId`, rather than being hardcoded by event type name.

### 6.4. Main Class and Demo Runner

File `src/main/java/demo/priority/DemoApplication.java`:

```java
package demo.priority;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

File `src/main/java/demo/priority/PriorityDemoRunner.java`:

```java
package demo.priority;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("priority-demo")
public class PriorityDemoRunner implements ApplicationRunner {
    private final OrderEventPublisher publisher;

    public PriorityDemoRunner(OrderEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public void run(ApplicationArguments args) {
        publisher.publishCreated("order-42");
        System.out.println("Sent OrderCreated (priority 4)");
        publisher.publishCancelled("order-42");
        System.out.println("Sent OrderCancelled (priority 8)");
    }
}
```

Set `JMS_USER`, `JMS_PASSWORD`, and the broker/queue first. In a Gradle Spring Boot project with the `bootRun` task, run:

```bash
./gradlew bootRun --args='--spring.profiles.active=priority-demo'
```

If both `JmsTemplate.send(...)` calls complete normally, **two application lines** appear in order:

```text
Sent OrderCreated (priority 4)
Sent OrderCancelled (priority 8)
```

This is not the entirety of Spring Boot stdout and **not the order processed by consumers**. The broker may receive/deliver the first message before the second is sent, or delay dispatch according to its policy. Do not use these two log lines as proof that priority inverted the order.

Only enable the `priority-demo` profile in test environments; every startup re-sends the same two messages with `aggregateId`/`sequence`, which must be isolated from production data.

## 7. Reading JMSPriority on the Receiving Side

A message received via a listener can have its standard header inspected directly. The following example is a **method snippet** inside a Spring JMS listener bean with `@EnableJms` enabled and a configured listener container:

```java
@JmsListener(destination = "${app.jms.destination}")
public void inspect(jakarta.jms.Message message)
        throws jakarta.jms.JMSException {
    String aggregateId = message.getStringProperty("aggregateId");
    long sequence = message.getLongProperty("sequence");
    int priority = message.getJMSPriority();
    System.out.printf(
            "aggregate=%s sequence=%d JMSPriority=%d%n",
            aggregateId, sequence, priority);
}
```

To compile this snippet in a listener class, import `org.springframework.jms.annotation.JmsListener`; the application must enable `@EnableJms` in a configuration class. If observed values match the template configuration:

```text
aggregate=order-42 sequence=1 JMSPriority=4
aggregate=order-42 sequence=2 JMSPriority=8
```

These two lines are **examples of lines that may appear**, not a claim that they appear in that order. Actual log ordering also depends on the broker and multiple consumers. In particular, merely seeing header priority 8 **does not prove the broker prioritized dispatching that message**.

Note: if the listener throws an error/rolls back and receives the message again, logs can appear multiple times. Do not treat raw logs as a table of committed business state order.

## 8. Priority Does Not Guarantee Business FIFO: Three Scenarios

### Scenario A: Newer Message Has Higher Priority

```text
t0: order-42 / sequence=1 / priority=4  -> enters queue
t1: order-42 / sequence=2 / priority=8  -> enters queue
t2: consumer receives sequence=2        -> may happen
t3: consumer receives sequence=1
```

If applying state updates in exact business order is mandatory, the consumer must recognize that `sequence=2` is not ready when `sequence=1` has not yet been applied. Priority is only a message scheduling hint.

### Scenario B: Same Priority, Multiple Sessions

```text
Producer A / Session A ---- send "order-42#1" ---\
                                               \ 
                                                > queue Q
                                               /
Producer B / Session B ---- send "order-42#2" ---/
```

Jakarta Messaging provides no global ordering across two sessions. Each producer seeing a "send succeeded" log is also insufficient to decide which event is entitled to be applied first in business terms. Sequences must be generated at a reliable ordered source; if two producers increment counters independently, the sequence is wrong from the start.

### Scenario C: Delivered in Order, Finished Out of Order

```text
Consumer 1 receives #1 -> API call takes 3 seconds -> commits late
Consumer 2 receives #2 -> API call takes 0.1 seconds -> commits first
```

Even when the broker dispatches `#1` before `#2`, parallel processing can commit out of order. The solution lies in **concurrency control, idempotency, and transaction boundaries** in business logic, not in `JMSPriority`.

## 9. Designing an Explicit Ordering Contract When Business Requires It

### 9.1. Specify Aggregate and Sequence

A typical event contract can include:

| Field | Meaning |
| --- | --- |
| `eventId` | Unique ID of an event, used for deduplication |
| `aggregateId` | ID of the entity requiring local ordering, e.g., `order-42` |
| `sequence` | Monotonically increasing version per aggregate, e.g., 1, 2, 3 |
| `eventType` | Event type and how it is applied |
| `schemaVersion` | Schema version for compatibility |
| `JMSPriority` | Send QoS hint, **not the source of ordering truth** |

For events affecting the same aggregate, **processing rules** might be:

- `sequence == lastApplied + 1`: eligible to apply in order.
- `sequence <= lastApplied`: possible duplicate/replay; check `eventId` and skip repeated side effects where appropriate.
- `sequence > lastApplied + 1`: gap detected; do not blindly commit ahead of order—apply a wait, retry/backoff, or controlled pending storage policy.

If sequences are non-contiguous for domain-specific reasons (such as using a different database version), adapt the condition to the real contract instead of mechanically applying `last + 1`.

### 9.2. Standalone Java 17 Example: Detecting Out-of-Order Events

The following example simulates **business sequence** only. It does not call JMS or create queues; thus it compiles and runs standalone to demonstrate ordering handling before broker integration.

File `SequenceGateDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;

public class SequenceGateDemo {
    private final Map<String, Long> lastApplied = new HashMap<>();

    void onEvent(String aggregateId, long sequence) {
        long last = lastApplied.getOrDefault(aggregateId, 0L);

        if (sequence <= last) {
            System.out.println("DUPLICATE " + aggregateId + "#" + sequence);
            return;
        }
        if (sequence > last + 1) {
            System.out.println("GAP " + aggregateId + "#" + sequence
                    + " (waiting for " + (last + 1) + ")");
            return;
        }

        lastApplied.put(aggregateId, sequence);
        System.out.println("APPLY " + aggregateId + "#" + sequence);
    }

    public static void main(String[] args) {
        SequenceGateDemo gate = new SequenceGateDemo();

        gate.onEvent("order-42", 2);
        gate.onEvent("order-42", 1);
        gate.onEvent("order-42", 2);
        gate.onEvent("order-42", 2);
    }
}
```

Compile/run:

```bash
javac SequenceGateDemo.java
java SequenceGateDemo
```

Exact stdout:

```text
GAP order-42#2 (waiting for 1)
APPLY order-42#1
APPLY order-42#2
DUPLICATE order-42#2
```

This is an **academic model running in a single JVM and single thread**. For production:

- Do not store `lastApplied` only in a `HashMap`; an application restart wipes state.
- Update `lastApplied` together with business effects using controlled transactions/CAS/optimistic locking.
- Synchronize processing per `aggregateId` so two consumers cannot both pass the `last + 1` check simultaneously.
- Gapped messages need pending storage or a safe retry mechanism, monitoring, and dead-lettering after limits; do not endlessly reject so the broker hot-redelivers continuously.
- Duplicate rules need `eventId` and proper idempotency definitions, since `sequence <= last` does not cover every replay/schema case.
- If events can be permanently lost, "wait for missing sequence" needs a timeout/reconciliation policy, not infinite waiting.

This contract allows business logic to preserve order **even when the broker occasionally delivers higher-priority messages first**.

### 9.3. Message Groups and Their Limits

Some brokers support message grouping via `JMSXGroupID` or an equivalent mechanism to pin messages in the same group to one consumer. Example setting the application property:

```java
message.setStringProperty("JMSXGroupID", orderId);
```

This is a **snippet inside a `MessageCreator`** that has variables `message` and `orderId`, requiring verification of provider support. Message grouping can help prevent multiple consumers from processing the same group concurrently, but **it does not automatically restore events reordered by priority**, does not replace sequence/idempotency, and requires verifying behavior during consumer failover/rebalance.

If the business requires strict ordering between Created and Cancelled on the same order, a safer approach may be a single stream per aggregate, avoiding different priorities across order-dependent events, using proper grouping, and checking sequence at the consumer. Redeliveries and failures still must be handled.

## 10. Testing Priority Properly

A test suite should distinguish three levels:

| Level | What to Verify | What Not to Assert |
| --- | --- | --- |
| Configuration unit test | Normal template has priority 4, urgent has priority 8, explicit QoS is enabled, deliveryMode/TTL match | Which message arrives at the consumer first |
| Broker integration test | Sent messages carry expected `JMSPriority`, credentials/destination are right, both messages are delivered under test conditions | Every broker at all times puts higher priority first |
| Business logic test | Consumer never commits `#2` before `#1` and handles duplicates/gaps properly | Raising priority alone achieves ordering |

### 10.1. Configuration Unit Test Without a Broker

With `spring-boot-starter-test` and JUnit Jupiter, file `src/test/java/demo/priority/JmsPriorityConfigurationTest.java`:

```java
package demo.priority;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import org.junit.jupiter.api.Test;
import org.springframework.jms.core.JmsTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;

class JmsPriorityConfigurationTest {
    private final JmsPriorityConfiguration config =
            new JmsPriorityConfiguration();

    @Test
    void templatesUseExpectedQos() {
        ConnectionFactory connectionFactory = mock(ConnectionFactory.class);

        JmsTemplate normal = config.normalJmsTemplate(connectionFactory);
        JmsTemplate urgent = config.urgentJmsTemplate(connectionFactory);

        assertTrue(normal.isExplicitQosEnabled());
        assertTrue(urgent.isExplicitQosEnabled());
        assertEquals(4, normal.getPriority());
        assertEquals(8, urgent.getPriority());
        assertEquals(DeliveryMode.PERSISTENT, normal.getDeliveryMode());
        assertEquals(DeliveryMode.PERSISTENT, urgent.getDeliveryMode());
        assertEquals(0L, normal.getTimeToLive());
        assertEquals(0L, urgent.getTimeToLive());
    }
}
```

With test dependencies:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Run:

```bash
./gradlew test --tests demo.priority.JmsPriorityConfigurationTest
```

When tests pass, Gradle may report `BUILD SUCCESSFUL`, though detailed log output depends on version and task configuration. This test verifies bean configuration only and **does not send real messages**.

### 10.2. Broker Integration Test

To test real behavior:

1. Create a dedicated test queue, configure the broker's priority policy, and verify it is active.
2. Stop consumers before sending messages if the goal is to observe the broker selecting from a backlog containing both low and high priorities; record consumer prefetch and broker version.
3. Send messages with varying `eventId`/`sequence`/priority, read `getJMSPriority()` on the consumer, and record receive/commit timestamps.
4. Repeat across single consumer, multiple consumers, multiple sessions/producers, broker restarts, and redeliveries if the environment permits.
5. Check both SLA/latency of the urgent group and whether normal messages suffer **starvation** under continuous high-priority traffic.

A single run producing `priority 8` before `priority 4` proves only **one observation** under those conditions. Do not write an integration test mandating a fixed `8 -> 4` order for every broker; that is not the specification contract. For the business contract `sequence=1 -> 2`, test in-order commitment independently of receive order.

## 11. Common Mistakes

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Calling `setPriority(9)` without enabling `explicitQosEnabled` | The template may keep using the provider's default QoS | Enable `setExplicitQosEnabled(true)` and verify deliveryMode/TTL too |
| `message.setJMSPriority(9)` inside `MessageCreator` | This header setter is meant for the provider during send | Configure QoS on `JmsTemplate`/`MessageProducer` |
| Assuming priority 9 is guaranteed to arrive before priority 4 | Jakarta Messaging only requires best-effort prioritization, not strict ordering | Separate latency goals from ordering contracts |
| Using `priority` instead of `sequence` | Priority expresses importance, not event version | Use `aggregateId`, `sequence`, and `eventId` |
| Sending across multiple templates/sessions and assuming FIFO | JMS ordering guarantee is not global across sessions | Design per-aggregate ordering at the source and consumer |
| Increasing listener concurrency for speed without state checks | Parallel processing can commit out of order | Enforce concurrency control, grouping, and version checks |
| Seeing two messages logged in producer order and assuming consumer matches | Send completion is not consumption/business commit | Track receive logs/metrics and business transactions |
| Confusing `JMSPriority` with consumer priority | One applies to messages, the other to broker-specific consumer dispatch policy | Name mechanisms accurately and check provider docs |
| Enabling explicit QoS just for priority and accidentally changing TTL/delivery mode | The flag applies to all three QoS parameters | Declare all QoS values or purposefully use producer-level APIs |
| Believing grouping eliminates redelivery/out-of-order | Grouping mainly assists same-group routing, with provider limits | Still enforce idempotency, sequence checks, and recovery policies |

## 12. Self-Check Questions

1. What is the default JMS priority? What do levels `0..4` and `5..9` signify?
2. Why might `template.setPriority(8)` fail to send messages at priority 8?
3. If a producer sends `#1` priority 4 and then `#2` priority 8 to the same queue, does the spec force the consumer to receive `#1` before `#2`? Which exception applies?
4. Why are two consecutive `JmsTemplate.send` calls insufficient to claim they used the same JMS `Session`?
5. What problem does `JMSXGroupID` solve, and why is `sequence` still needed?
6. If `#2` arrives before `#1`, what should the consumer do to avoid committing invalid state? What concurrency/transaction conditions does holding that state require?

**Takeaway:** Priority is a **send-time QoS hint** that helps the broker favor urgent messages. JMS ordering applies only within defined scopes and has exceptions. Business order requires its own contract built on versioning/sequence numbers, idempotency, and contention control.

## References

- Jakarta Messaging 3.1, `6.2.9 Message order` and `3.4 Message header fields`: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging 3.1 API, `Message.getJMSPriority()` and `setJMSPriority(int)`: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message
- Jakarta Messaging API, `MessageProducer.setPriority(int)`: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer
- Spring Framework 6.2, Using `JmsTemplate` and explicit QoS: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework 6.2, `JmsTemplate` API: https://docs.spring.io/spring-framework/docs/6.2.x-SNAPSHOT/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- ActiveMQ Artemis, Message Priority: https://artemis.apache.org/components/artemis/documentation/latest/examples.html
