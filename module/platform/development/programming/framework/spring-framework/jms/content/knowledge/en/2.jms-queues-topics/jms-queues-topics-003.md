# Multiple Consumers Receiving from a Single Queue

## Learning Objectives

After this lesson, you will be able to explain why multiple consumers listen on the same JMS Queue yet each message delivery goes to only one consumer; distinguish parallel processing from broadcasting copies to every recipient; configure the number of consumers using Spring JMS; and design safe handling against errors, redelivery, load skew, and out-of-order completion.

## 1. The Competing Consumers Model

In the **point-to-point** model, a producer sends messages to a `Queue` on the broker. Multiple consumers can subscribe to that Queue. For a normal delivery, the broker chooses **one** eligible consumer to receive each message; the remaining consumers do not simultaneously receive a copy of that message. This is the **competing consumers** model.

```text
Producer A ----\
                >---- [orders.queue] ----+---- Consumer 1
Producer B ----/                        +---- Consumer 2
                                        +---- Consumer 3
```

Suppose a producer sends six messages `M1..M6`; a *possible* result is:

| Consumer | Messages received in a hypothetical run |
| --- | --- |
| C1 | M1, M4 |
| C2 | M2, M5 |
| C3 | M3, M6 |

The table only describes **one illustrative distribution**; it does not promise that the broker distributes evenly or in round-robin fashion. If C1 is faster, started earlier, has a larger prefetch buffer (`prefetch`), or C2 is busy, C1 may receive more messages. The Jakarta Messaging specification does not mandate a specific consumer selection algorithm when multiple consumers are on the same Queue.

Key point: "one message is delivered to one consumer" **does not mean** the business logic is guaranteed to execute strictly once in all scenarios. An unacknowledged/uncommitted message can be redelivered after an error; the same business task may go through multiple processing attempts.

### Compared to Topic

| Sending one message | Queue with multiple consumers | Topic with multiple independent subscriptions |
| --- | --- | --- |
| Common purpose | Split work to increase processing capacity | Distribute events to multiple interested groups |
| Who receives? | One eligible consumer per delivery to the Queue | Each eligible subscription can receive a copy |
| Increasing consumer count | Increases the number of workers sharing the Queue's load | Depends on subscription organization; a shared subscription can also share load within that subscription |

Therefore, "all three workers must know about a new order" normally requires different subscriptions on a Topic or a fan-out mechanism; whereas "three workers share the work of processing orders" fits **one Queue with three consumers**.

## 2. How Does a Message Travel Through a Queue?

A typical lifecycle:

1. The producer sends a message with its payload and required properties; the broker accepts and stores/routes it according to durability, transaction, and provider configuration.
2. An eligible consumer receives the message from the Queue. The broker may have pre-pushed multiple messages into this consumer's `in-flight` region.
3. The listener processes the work. Another consumer can simultaneously process a *different message*.
4. When the receiving session acknowledges successfully or the JMS transaction commits, the broker considers the delivery complete.
5. If the consumer loses connection, rolls back, or has not acknowledged successfully, the broker may redeliver the message to **the same consumer or another consumer**, depending on configuration and state.

For example, C1 deducted inventory in the database, but the JVM crashed before the JMS transaction committed. When the message is redelivered to C2, if the code does not guard against duplicate processing, inventory may be deducted again. The "one consumer receives a message" mechanism does not by itself solve atomicity between JMS and the database.

**A consumer is a JMS receiving entity**, tied to a `Session`/`MessageConsumer` or a corresponding listener container. It is not strictly synonymous with "one machine", "one application instance", or "one shared thread". Spring manages consumers and sessions inside the listener container for concurrent processing.

## 3. Ways to Create Multiple Consumers

- **Multiple consumers in one JVM:** one Spring `@JmsListener` using a listener container with `concurrency` greater than 1. The container opens appropriate JMS sessions/consumers; multiple invocations of the same listener can run in parallel.
- **Multiple application instances:** multiple processes/pods configured with the same `destination = "orders.queue"` and connecting to the **same broker/logical Queue**. They share work even without knowing about each other.
- **Combining both:** if there are two replicas, and each replica creates 3–5 consumers for this listener, the total can be around 6–10 consumers when all are active, depending on load conditions and container state.

You do not need to create three separate `@JmsListener` methods just to have three workers. For a single business task, configuring `concurrency` on one listener is usually clearer. Multiple listeners pointing to the same Queue still compete for messages, but you must ensure they understand the same format and processing rules.

In Jakarta Messaging, `Session`, `MessageConsumer`, and `JMSContext` must not be used concurrently across multiple threads arbitrarily. To increase parallelism, create multiple appropriate sessions/consumers or let the Spring listener container do it. Do not share one `Session` across a thread pool and invoke receive concurrently.

## 4. Spring JMS Example: Multiple Consumers on One Queue

The example below uses **Java 17+**, **Spring Boot 4.0.6**, and an **externally running Apache ActiveMQ Artemis broker**. This is a standalone test application; the broker must allow using Queue `orders.queue` (pre-created or auto-creation enabled). Credentials must match the actual broker.

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.6</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>queue-consumers</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
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

**`src/main/resources/application.properties`**

```properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
# If the broker requires authentication, provide the actual credentials:
# spring.artemis.user=...
# spring.artemis.password=...
```

**`src/main/java/example/jms/QueueConsumersApplication.java`**

```java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class QueueConsumersApplication {

    public static void main(String[] args) {
        SpringApplication.run(QueueConsumersApplication.class, args);
    }

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);       // Queue, not Topic
        factory.setConcurrency("3-5");        // 3 baseline consumers, max 5
        factory.setSessionTransacted(true);   // JMS commit/rollback
        return factory;
    }

    // For demo only: each startup sends 12 new messages.
    @Bean
    ApplicationRunner sendDemo(JmsTemplate jmsTemplate) {
        return args -> {
            for (int i = 1; i <= 12; i++) {
                jmsTemplate.convertAndSend("orders.queue", "order-" + i);
            }
        };
    }

    @Component
    public static class OrderListener {
        @JmsListener(destination = "orders.queue")
        public void onOrder(String orderId) {
            System.out.printf(
                    "consumer=%s | message=%s%n",
                    Thread.currentThread().getName(),
                    orderId
            );
        }
    }
}
```

Run when the broker is ready:

```bash
mvn spring-boot:run
```

The test run may print lines of the form `consumer=<thread-name> | message=order-1` through `order-12`. **There is no fixed stdout**: which thread processes which message, the order of lines, and whether all five consumers are actually used all depend on scheduling and the broker. Each string `order-1` through `order-12` is sent once by the application during a single demo startup; do not infer from the log that the system guarantees exactly-once business processing upon failures.

**Explanation of key lines:**

- `@EnableJms` enables Spring's `@JmsListener` endpoint infrastructure.
- `jmsListenerContainerFactory` is the default factory name used by endpoints that do not specify `containerFactory`. It creates listener containers of the `DefaultMessageListenerContainer` family.
- `setConcurrency("3-5")` requests a concurrency range of 3 to 5 for **this endpoint**; each consumer operates with an appropriate session. You can replace it with `setConcurrency("1")` to observe near-sequential processing.
- `setPubSubDomain(false)` explicitly indicates the destination is interpreted as a Queue. This is also typically the default, but writing it makes the intent clear.
- `setSessionTransacted(true)` requests a **local JMS** transaction: if the listener succeeds, it commits the receive; if a runtime error escapes the listener, the container rolls back the receive. This does not automatically put database operations into the same transaction.
- `JmsTemplate.convertAndSend` uses the default message converter suitable for `String`, and the receiving side maps it to the `String orderId` parameter.
- Spring can use a single `OrderListener` instance across multiple parallel invocations. Therefore, the listener should not hold shared mutable state without synchronization.

If you want to see multiple processes competing for work, split `sendDemo` into a one-shot publisher, then run two or three listener-only instances against the same broker and Queue. **Do not keep the demo seed bean in all replicas**: each restarting replica will generate another 12 messages, easily mistaken for duplicate message processing.

## 5. Concurrency Increases Throughput but Does Not Guarantee Even Distribution

Suppose a message requires 50 ms of work on average and faces no other resource bottlenecks. One consumer has a theoretical throughput of about `1 / 0.05 = 20 messages/second`. Six consumers could reach nearly `120 messages/second` under ideal conditions; in reality there is connection overhead, I/O, broker, database, lock contention, and processing-time variance.

If the incoming message rate (`λ`) exceeds the total sustainable processing rate, Queue depth grows steadily. Choose concurrency based on arrival rate, processing time, CPU usage, database limits, and `in-flight` message count; infinitely increasing consumer count will not make an overloaded database faster.

**Why don't three consumers each receive exactly 1/3 of the messages?**

1. **Prefetch/buffering:** the broker may dispatch multiple messages to one consumer before another consumer is ready. A newly arrived consumer may see little work even though the Queue previously had a backlog.
2. **Speed of each consumer:** a consumer with faster processing, better network, or less I/O waiting often gets opportunities to receive more.
3. **Connection timing:** a consumer that started earlier may already have received many messages.
4. **Selectors, priority, and broker policies:** a message may only match a subset of consumers; priority, grouping, and dispatch policies alter distribution.
5. **Resource limits:** session pool, connection pool, threads, transactions, broker quotas, or downstream service limits make effective concurrency lower than configured.

A large prefetch can improve throughput when work is very fast; conversely, it can cause load imbalance or leave many messages waiting on a slow consumer. Tune prefetch/consumer window per **specific broker**, without treating a single parameter as universal across all JMS providers. When measuring performance, inspect both pending Queue depth and messages dispatched but not yet acknowledged.

## 6. Ordering: Queue FIFO Does Not Mean Out-of-Order Completion Is Prevented

A Queue has a notion of message order, but when multiple consumers process in parallel, **business completion order is not guaranteed**.

Example:

```text
M1 (update order A) -> C1 processes in 800 ms
M2 (cancel order A) -> C2 processes in  50 ms
Result: M2 may complete before M1
```

Rollback/redelivery, priority, and selectors can further complicate the observed delivery order. Therefore, do not rely on log line order or database commit order when using multiple consumers.

If messages with the same `orderId` must be processed sequentially, consider:

- Reducing concurrency to 1 for a Queue that truly requires global sequential processing (trading off throughput).
- Partitioning work by business key (for example, per order or customer) so related messages are routed to a sequential processing stream.
- Using **message groups** if supported by the broker: for instance, ActiveMQ Artemis supports the JMS property `JMSXGroupID` to pin messages in the same group to one consumer. You must understand throughput limits, rebalancing, and consumer disconnect handling.
- Designing business state with version/sequence numbers and rejecting stale operations, if the problem requires correctness despite out-of-order processing.

`JMSXGroupID` is an example of a specific broker feature/implementation; do not assume every provider has identical grouping and recovery policies.

## 7. Errors, Rollback, Redelivery, and Duplicate Handling

Configuring `sessionTransacted(true)` in the example is an appropriate choice for Queue processing flows needing JMS reception reliability:

| Scenario | Typical Meaning |
| --- | --- |
| Listener returns normally | Container commits the JMS transaction; message is acknowledged at the broker |
| Listener throws an exception and it is not swallowed | Container rolls back JMS; broker may redeliver per policy |
| Listener catches the exception, just logs it, and returns normally | Container may treat it as success and commit; the business error is hidden |
| JVM crashes after database side effect commits but before JMS commit | Message may be redelivered; side effect risks duplication |
| Message fails repeatedly | Requires retry limit policy, wait/backoff delay, and dead-letter queue managed by the broker |

**Do not equate a local JMS transaction with a database transaction.** When a listener updates a database, they are usually **two separate resources and two separate transactions**. `@Transactional` for the database does not automatically create an atomic commit with JMS; even when the DB transaction completes before JMS acknowledgment, there is still a window where failure can occur. Distributed/XA transactions should only be chosen when requirements, platform, and operational cost truly justify them.

A common defense is an **idempotent consumer**:

1. The producer attaches a stable `eventId` to each business event. Do not generate a new ID each time the broker redelivers the same message.
2. In the database, create a unique constraint on `processed_event(event_id)`.
3. Within the **same DB transaction**, check/record `eventId` and perform the business change. If the ID has already been processed, skip the side effect and return normally.
4. Only let the listener return normally when the DB transaction completes; for transient errors, let the error propagate to trigger JMS rollback and controlled retry.
5. For side effects to external services (email, payments...), apply an idempotency key/appropriate mechanism at the target service, because an internal unique constraint does not by itself guarantee an external call will not be repeated.

Design-oriented SQL example (not a runnable script as schema/SQL dialect depends on the system):

```sql
-- processed_event.event_id has a UNIQUE constraint.
-- Both recording event_id and updating business state must be in the same DB transaction.
BEGIN;
INSERT INTO processed_event(event_id) VALUES (:event_id);
-- Apply business changes only if INSERT succeeds.
UPDATE orders SET processed = TRUE WHERE order_id = :order_id;
COMMIT;
```

If a duplicate key is encountered, the duplicate-handling branch must exit safely (and handle DB transaction state appropriately for the driver/dialect), **without re-running UPDATE**. You can use `INSERT ... ON CONFLICT DO NOTHING` in PostgreSQL and only update when the insert actually adds a row. This is an active fault-tolerance mechanism that does not depend on whether the message is redelivered to the same consumer or a different one.

For endlessly failing errors (poison messages), configure the broker for finite redeliveries and routing to a **DLQ (dead-letter queue)**. "How many retries", "how long to delay", and "where the DLQ is" belong to broker policy; do not assume all brokers behave alike. Monitor the DLQ and maintain a process to fix data and replay in a controlled manner.

## 8. Choosing Parallelism and Protecting Resources

A practical strategy:

1. Start with small concurrency, such as `2-4`, against a single-consumer baseline; measure messages/second, processing duration, and Queue depth.
2. Increase incrementally when the Queue grows continuously and CPU/I/O/database still have headroom; check connection/session health, latency, lock contention, and redeliveries.
3. Cap DB/HTTP connection pools so concurrent tasks do not trigger connection storms or cascading timeouts.
4. Monitor `queue depth`, `in-flight/unacknowledged`, `active consumers`, `oldest message age`, `retry/redelivery`, `DLQ`, throughput, and processing p95/p99; do not watch CPU alone.
5. Configure shutdown policies so in-progress tasks have an opportunity to finish; test killing a replica to observe how uncommitted messages are redelivered.
6. For messages with ordering dependencies, choose a design that preserves ordering by business key before raising concurrency.

If a workload primarily calls an external API rate-limited to 30 requests/second, increasing from 5 to 50 consumers may only cause the API to return 429 and increase retries. Appropriate backpressure, rate limiting, or quotas are needed, not just adding listeners.

## 9. Testing Correct Behavior

A meaningful exercise must verify **business outcomes**, not just log line counts:

| Test | Setup | What to observe |
| --- | --- | --- |
| Normal load sharing | Send 100 messages with distinct `eventId`; run 3 consumers | Each ID completes once at the business layer; distribution may be uneven |
| Adding consumers | Increase concurrency or add a replica while Queue has a backlog | How throughput/queue age changes; do not assume the new consumer immediately takes half |
| Consumer killed | Force-stop a consumer while processing a message before JMS commit | Message may be redelivered; eventId still does not create duplicate side effects |
| Transient error | Intentionally throw a controlled error in the listener, then allow the next attempt to succeed | Rollback/redelivery follows policy without swallowing exceptions |
| Poison message | Create a message that always fails and configure finite redelivery | Message reaches DLQ; main Queue is not blocked indefinitely |
| Ordering dependency | Send two operations with the same business key and different processing durations | Detect out-of-order completion; apply grouping/partitioning if needed |

To test "no simultaneous duplicate delivery to two consumers", distinguish **message delivery** from **effect**: the broker can redeliver after failure or timeout, so an application log showing the same `eventId` twice does not prove two consumers received the same delivery simultaneously. Inspect message IDs, delivery count (if provided by the broker), transaction outcomes, and business IDs.

## 10. Common Confusions

- **"With three consumers, one message is received by all three."** False for Queue competing consumers; each delivery selects one recipient, not a broadcast.
- **"Distribution is definitely 1–2–3 round-robin."** Not guaranteed by the JMS standard; prefetch and dispatch policies can skew load.
- **"Queues guarantee code runs strictly once."** No; retry/redelivery can repeat side effects if not idempotent.
- **"Just increasing concurrency makes it faster."** False when the bottleneck is the broker, database, external API, or locks.
- **"Parallel processing still guarantees order A is updated before being canceled."** No; use per-key ordering or sequencing when dependencies exist.
- **"Catching an exception and logging it triggers a retry."** If the listener returns normally within a JMS transaction, the message may be committed instead of retried.
- **"Create multiple threads sharing the same JMS Session."** Violates threading rules; use multiple sessions or listener containers.
- **"A JMS transaction automatically covers the database."** No; you need idempotency design, transaction discipline, or intentional XA.

## Summary to Remember

A Queue can have multiple consumers to **split work**: on each delivery, one message goes to one eligible consumer while other messages are processed in parallel. Spring JMS uses `@JmsListener` and `DefaultJmsListenerContainerFactory#setConcurrency` to configure consumer count; it can scale across multiple JVMs/replicas. When increasing concurrency, you must simultaneously address **out-of-order completion**, **skewed distribution from broker/prefetch**, **redelivery**, and **duplicate side effects**. For business applications, transacted JMS sessions + business-ID idempotency + retry/DLQ + Queue monitoring form a reliable foundation.

## References

- Jakarta Messaging 3.1 — Queue semantics, multiple consumers, session threading: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Spring Framework — Annotation-driven listener endpoints: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Framework — Message listener containers and transactions: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Boot — JMS / ActiveMQ Artemis: https://docs.spring.io/spring-boot/4.0/reference/messaging/jms.html
- Apache ActiveMQ Artemis — Messaging concepts: https://artemis.apache.org/components/artemis/documentation/latest/messaging-concepts.html
- Apache ActiveMQ Artemis — Message grouping: https://artemis.apache.org/components/artemis/documentation/latest/message-grouping.html