# Criteria for Choosing Synchronous Polling vs. Asynchronous Listener in Spring JMS

## 1. Two JMS receiving approaches and the design decision

A Spring application has a queue `orders.in` containing order events. The development team must choose how to fetch messages:

- **Synchronous polling:** the application actively calls `JmsTemplate.receive(...)` or `receiveAndConvert(...)` at a time of its own choosing. The calling thread waits for the broker to return a message or for the timeout to expire.
- **Asynchronous listener:** registers `@JmsListener`; Spring manages a **message listener container** to continuously receive messages and invoke the handler method whenever a matching message arrives. Business flow code does not manually call `receive` in a loop.

Both use Jakarta Messaging (JMS) and can receive from the same queue/topic types when configured properly. The key difference is **who owns the receiving lifecycle, when receiving is allowed, how threads are allocated, load throttling, acknowledgement/transaction management, and failure recovery**.

A mental model:

```text
SYNCHRONOUS POLLING                       ASYNCHRONOUS LISTENER
-------------------                       ---------------------
Scheduler / batch job                     Spring JMS listener container
      |                                              |
      | (time to run)                                | (maintains consumer)
      v                                              v
JmsTemplate.receive(queue)                 receives message via JMS
      |                                              |
      | block <= receiveTimeout                      v
      v                                      @JmsListener handler(...)
message or null                                      |
      |                                              v
      v                                       processing + ack/transaction
business handler
      |
wait for next poll
```

**Important:** "asynchronous listener" describes how **the application is invoked on events**; it does not mean the underlying broker always uses push without polling. Spring's `DefaultMessageListenerContainer` can use `MessageConsumer.receive()` loops on container-managed threads. Therefore, compare **application and operational contracts**, not just a "polling vs. push" label.

### Learning outcomes

After this lesson, you can choose an approach based on latency SLAs, message frequency, allowed execution windows, thread/connection budgets, bursts and backpressure, transactions/redelivery, ordering requirements, observability, and operability. You will also be able to write Java 17+ examples for both approaches and recognize pitfalls when switching from one to the other.

## 2. JmsTemplate.receive: what is synchronous polling really?

In Spring Framework 6.x, `org.springframework.jms.core.JmsTemplate` provides methods such as:

```java
jakarta.jms.Message receive(String destinationName);
Object receiveAndConvert(String destinationName);
```

These abbreviated signatures are for illustration; see the Javadoc for full nullability and overloads.

- `receive(...)` returns a JMS `Message`, such as a `TextMessage`.
- `receiveAndConvert(...)` uses the configured `MessageConverter` and returns a Java object; with the default `SimpleMessageConverter`, a `TextMessage` typically converts to `String`.
- Both can return `null` when **the wait duration expires with no message**.
- Spring manages the JMS connection/session/consumer for template operations and translates appropriate `JMSException`s into unchecked `JmsException`.
- The method completes only when a message is received, the timeout expires, or an error occurs; the calling thread **is occupied** throughout the wait.

### 2.1. receiveTimeout: a critical condition

`JmsTemplate` can be configured with:

```java
template.setReceiveTimeout(1_000L); // up to about 1 second waiting for a message
```

Meaning in Spring `JmsTemplate`:

| Value | Behavior |
| --- | --- |
| `-1`, default `RECEIVE_TIMEOUT_INDEFINITE_WAIT` | Waits **indefinitely** until a message arrives or another event terminates the operation |
| `0`, `RECEIVE_TIMEOUT_NO_WAIT` | Attempts to receive immediately, **does not wait** if no message is available yet |
| Positive number, e.g. `1_000` | Waits up to roughly 1,000 ms for one receive |
| Negative value other than `-1` | Treated by `JmsTemplate` as the no-wait branch; avoid arbitrary confusing negative numbers |

Do not confuse `JmsTemplate`'s timeout convention with the `MessageConsumer.receive(long)` API convention: in the raw JMS API, argument `0` in `receive(0)` means wait indefinitely, whereas Spring `JmsTemplate.setReceiveTimeout(0)` means **no-wait**.

**High-impact mistake:** using default `receive(...)` on an HTTP request thread or a `@Scheduled` job while assuming it returns immediately when the queue is empty. If no message is present, the method can block indefinitely. Set a finite timeout or use no-wait configuration intentionally.

### 2.2. Polling does not have to mean busy-wait

A poor pattern:

```java
while (true) {
    Object message = template.receiveAndConvert("orders.in");
    // If receiveNoWait and no backoff, this can loop very rapidly.
}
```

This is an **anti-pattern**, not a standalone runnable program. Continuously polling with no-wait can heat up the CPU, increase call/allocation rates, and put useless load on the broker. A good poller must have a **schedule, timeout, per-run message limit, and sleep/backoff strategy**.

If the schedule is 5 seconds and each run pulls at most one message, then even when the queue backlog is large, the scheduler's throughput can be very low. Conversely, if one poll processes a batch of thousands of messages, you must control time limits, transaction boundaries, and clean shutdown for that batch.

## 3. @JmsListener: asynchronous receiving from the application's perspective

In Spring JMS, a basic example:

```java
@JmsListener(destination = "orders.in")
public void onOrder(String payload) {
    orderHandler.handle(payload);
}
```

This is a **method in a Spring-managed bean**, with `orderHandler` already injected. Spring scans the annotation, creates an endpoint, and uses `JmsListenerContainerFactory` to initialize a listener container. The container handles acquiring connections/sessions/consumers, message dispatching, threading, and most recovery handling.

A listener bean stays ready to receive messages whenever the container is running. When a message arrives, the framework invokes the handler without waiting for an application scheduler's next poll tick.

**Do not confuse two concepts:**

- **Producer asynchronous send:** uses `CompletionListener` to be notified of send completion.
- **Consumer asynchronous listener:** uses `@JmsListener`/listener container to process received messages without business code calling `receive`.

`@JmsListener` does not automatically make the handler non-blocking: if the handler makes slow database or HTTP calls, the listener container thread remains occupied during processing. Concurrency and consumer count determine throughput, while ack/transactions govern behavior on errors.

### 3.1. What does the container do on behalf of the application?

With `DefaultMessageListenerContainer`, Spring can:

- Maintain configured consumer/thread counts, supporting scaling consumers up and down within bounds.
- Receive messages via the JMS provider and invoke the right handler.
- Create/release JMS resources according to container lifecycle; recover from temporary broker connection failures.
- Integrate transactions, acknowledgement modes, and error routing into container mechanics.
- Support starting/stopping or managing endpoints via `JmsListenerEndpointRegistry`.

However, the application must still design **idempotency, Poison Message/DLQ handling, dependency timeouts, data validation, observability, and business ordering guarantees**. A listener container does not automatically guarantee end-to-end exactly-once semantics.

## 4. Decision matrix: which solution should you choose?

| Criterion | Synchronous polling (`JmsTemplate.receive`) | Asynchronous listener (`@JmsListener`) |
| --- | --- | --- |
| **Who triggers it?** | Scheduler, batch job, admin command, or workflow explicitly calling it | Listener container continuously receives while the endpoint is running |
| **Desired latency** | Tolerates delay up to poll interval and wait duration | Fits goals requiring prompt reaction as soon as messages are available |
| **Message volume** | Sparse, periodic, or batchable with bounded intake | Steady or continuous, needing backlog processing and tunable concurrency |
| **Operating hours** | Fits processing restricted to maintenance windows or strict schedules | Fits consumers that must stay ready almost continuously |
| **Backpressure** | Explicit via poll/batch limits and run schedule | Requires configuring concurrency, consumer counts, worker pools, pause/stop |
| **Thread cost** | Thread occupied only while running; however `receive` can block | Threads and JMS consumers exist persistently, even under low load |
| **Transaction/ACK** | Must actively wrap both receive **and** processing in a transaction if rollback is needed | Listener container offers more convenient transaction integration points |
| **Resilience** | Schedule and errors/retries coordinated by code/scheduler | Container provides recovery for connection errors; business errors still need handling |
| **Scaling** | Increase job/worker counts, risking contention and schedule overlap | Tune concurrency, scale replicas; must control ordering and resource limits |
| **Operations** | Monitor empty polls, poll counts, per-batch duration | Monitor container running state, active consumers, retries, backlog, handler failures |
| **Internal complexity** | Less upfront plumbing, but easy to end up writing loops, backoff, shutdown yourself | Spring manages receive infrastructure; must understand lifecycle and consumer concurrency |
| **Broker dependency** | Needs broker when polling; no message means null or blocking | Needs broker while listener is active; on outage container recovers per policy |

**Pragmatic conclusion:** if the requirement is "process promptly when messages arrive, run 24/7, and volume can vary," **prefer a listener container**. If the requirement is "process only when a job is triggered, at most N messages per batch, or only during allowed hours," **controlled polling** is often a better fit.

This is not a ranking of "listeners are always right, polling is always wrong." Polling gives exact control over *when* consumption happens; listeners reduce custom infrastructure code and are generally better for continuous event processing.

## 5. Six design questions for choosing an approach

### 5.1. How fast must messages be processed?

With an SLA of a few seconds and irregular arrivals, polling every few dozen seconds introduces unnecessary latency. In scheduled polling, extra latency depends on **message arrival phase relative to the schedule**, prior run duration, and scheduler load. Do not use a simple average formula for SLAs if bursts or long-running jobs occur.

If business rules allow aggregating at the end of an hour or day, batch polling can be easier to control.

### 5.2. Do you need to pause consumption strictly by time window?

For instance, importing data into a legacy system only from 01:00 to 02:00: a scheduler polling during that window expresses the intent naturally. A listener can still be paused by starting/stopping the container on a schedule, yet it requires in-flight message drain rules and shutdown handling; it is not simpler in every case.

### 5.3. How does the system react to a sudden backlog spike?

A listener can scale consumers up to configured limits, yet too many consumers can overload downstream databases/APIs. A poller can deliberately cap messages per run to protect downstream dependencies, though if consumption lags behind sustained arrival rates, backlog will grow.

Measure **arrival rate**, **processing rate**, latency by message age, pending/in-flight counts, and errors/rollbacks. Use **capacity planning** to choose concurrency or batch size, rather than guessing from total queue count alone.

### 5.4. Must processing roll back/redeliver on failure?

If you require "when the business handler fails, the message remains available for retry," inspect receive/ack/transaction boundaries. With `JmsTemplate.receiveAndConvert(...)` used outside a transaction, the message may already be ACKed/committed **before** subsequent code finishes. A listener container using properly configured JMS transactions can roll back when the handler throws an exception.

Do not assume "listener = at-least-once" if the container uses `AUTO_ACKNOWLEDGE` or the callback swallows exceptions; actual configuration decides.

### 5.5. Is strict ordering required per entity?

Even if polling runs on one thread or a listener has `concurrency = 1`, **multiple application instances, multi-session producers, differing priorities, and redeliveries** can still complicate business ordering. Do not treat "one thread" as a global ordering guarantee. When ordering matters, use `aggregateId`, `sequence/version`, idempotency, and version-checked state updates.

### 5.6. Who operates restarts, stops, and retries?

If it is a periodic job managed externally by Kubernetes/CronJob, polling fits cleanly into the job lifecycle. For a continuous message-consuming service, a listener container's built-in lifecycle and recovery significantly cut boilerplate.

Still, maintain operational runbooks for both: broker outages, bad credentials, missing queues, stuck consumers, poison messages, backlog thresholds, deployments/scale-down, and DLQ handling.

## 6. Spring Boot 3.x / Java 17+ example: one business flow, two receiving modes

Below is a sample project using ActiveMQ Artemis and queue `orders.in`, separating modes with **Spring profiles** so the poller and listener do not compete on the same queue during hands-on testing.

- Profile `publish`: sends a test event.
- Profile `poll`: each scheduled tick calls `JmsTemplate.receiveAndConvert`.
- Profile `listener`: uses Spring-managed `@JmsListener`.

The broker must be running, the JMS account must have permissions, and queue `orders.in` must exist. The files are complete Java classes inside a **Gradle-configured Spring Boot project**, and cannot be compiled standalone with `javac` without Spring/JMS dependencies.

### 6.1. Dependencies and connection

In `build.gradle` (Groovy DSL) of a Spring Boot 3.x project with the Boot and dependency-management plugins:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Use Java 17+ and the project's Gradle wrapper. Create `src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: "${JMS_BROKER_URL:tcp://localhost:61616}"
    user: "${JMS_USER}"
    password: "${JMS_PASSWORD}"

app:
  jms:
    queue: "${JMS_QUEUE:orders.in}"
  poll:
    fixed-delay-ms: 5000
    receive-timeout-ms: 1000
```

Never store real passwords in the repository. Configuring a queue name only specifies the name to resolve `Destination`; it **does not guarantee the broker will auto-provision the physical queue**. Both profiles must target the **same broker and same queue type** for valid observation.

### 6.2. Application enabling listener and scheduler

File `src/main/java/demo/receive/ReceiveApplication.java`:

```java
package demo.receive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableJms
@EnableScheduling
public class ReceiveApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReceiveApplication.class, args);
    }
}
```

In Spring Boot, listener infrastructure is usually auto-configured when JMS is present. `@EnableJms` is added explicitly for clarity in the example, while `@EnableScheduling` powers the poller. Enabling scheduling does not make the listener receive on a schedule: the two mechanisms remain independent.

### 6.3. Shared handler

File `src/main/java/demo/receive/OrderHandler.java`:

```java
package demo.receive;

import org.springframework.stereotype.Service;

@Service
public class OrderHandler {

    public void handle(String payload) {
        if (payload == null || !payload.startsWith("OrderCreated:")) {
            throw new IllegalArgumentException("Unsupported order event");
        }
        System.out.println("Handling event: " + payload);
    }
}
```

The demo handler only prints to stdout, with no database. Production requires an idempotent operation and clear transaction boundaries; printing "Handling" does not prove business state was committed.

### 6.4. JmsTemplate configuration dedicated to polling

File `src/main/java/demo/receive/PollingJmsConfiguration.java`:

```java
package demo.receive;

import jakarta.jms.ConnectionFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.jms.core.JmsTemplate;

@Configuration(proxyBeanMethods = false)
@Profile("poll")
public class PollingJmsConfiguration {

    @Bean("pollingJmsTemplate")
    public JmsTemplate pollingJmsTemplate(
            ConnectionFactory connectionFactory,
            @Value("${app.poll.receive-timeout-ms}") long timeoutMs) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setReceiveTimeout(timeoutMs);
        return template;
    }
}
```

Benefits of a dedicated template:

- Configures `receiveTimeout` for the poller without altering another `JmsTemplate` used for sending.
- Reuses the same `ConnectionFactory` prepared by Spring Boot.
- Pins a **finite** 1-second timeout in the example, preventing the job from blocking indefinitely.

**Note:** this configuration only illustrates basic polling. It does **not** open a transaction wrapping both receiving and processing. Therefore it is unsuitable for business flows needing reliable retries after handler failures.

### 6.5. Poller receiving at most one message per tick

File `src/main/java/demo/receive/OrderPoller.java`:

```java
package demo.receive;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@Profile("poll")
public class OrderPoller {
    private final JmsTemplate template;
    private final OrderHandler handler;
    private final String queue;

    public OrderPoller(
            @Qualifier("pollingJmsTemplate") JmsTemplate template,
            OrderHandler handler,
            @Value("${app.jms.queue}") String queue) {
        this.template = template;
        this.handler = handler;
        this.queue = queue;
    }

    @Scheduled(fixedDelayString = "${app.poll.fixed-delay-ms}")
    public void pollOnce() {
        Object value = template.receiveAndConvert(queue);
        if (value == null) {
            // Queue empty or receiveTimeout expired; not an exception.
            return;
        }
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException("Expected TextMessage");
        }
        handler.handle(text);
    }
}
```

Execution behavior:

- With `fixedDelay`, the next run begins 5 seconds **after** the previous execution finishes, rather than strictly every 5 clock seconds.
- Each run receives at most **one** JMS message.
- If the queue is empty, `receiveAndConvert` can wait up to 1 second and return `null`.
- If another profile's listener were active simultaneously, the two consumers would compete for messages on the same queue — **they would not duplicate each message like fan-out**.

To process batches, add explicit bounds on **message count, duration, memory, and error policy**; never write an unbounded `while(true)` loop inside a `@Scheduled` method.

### 6.6. Listener without manual receive calls

File `src/main/java/demo/receive/OrderListener.java`:

```java
package demo.receive;

import org.springframework.context.annotation.Profile;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
@Profile("listener")
public class OrderListener {
    private final OrderHandler handler;

    public OrderListener(OrderHandler handler) {
        this.handler = handler;
    }

    @JmsListener(destination = "${app.jms.queue}", concurrency = "1")
    public void onMessage(String body) {
        handler.handle(body);
    }
}
```

Spring registers the endpoint via `JmsListenerContainerFactory`. With the JMS starter and Spring Boot auto-configuration, a listener container is created automatically if no custom factory is defined; Boot 3.4 configures the listener factory as transactional by default (using JTA if applicable, otherwise local session transactions). **Do not assume this default applies to every Spring Boot version or custom factory**: inspect your application's actual configuration.

`concurrency = "1"` only limits that endpoint's container to **one concurrent consumer per that endpoint's configuration**. Scaling the application to multiple replicas still yields multiple consumers overall. It does not turn the queue into a global business ordering guarantee, nor does it yield high throughput when the handler is slow.

### 6.7. Separate test producer to put a message onto the queue

File `src/main/java/demo/receive/PublishRunner.java`:

```java
package demo.receive;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
@Profile("publish")
public class PublishRunner implements ApplicationRunner {
    private final JmsTemplate template;
    private final String queue;

    public PublishRunner(
            JmsTemplate template,
            @Value("${app.jms.queue}") String queue) {
        this.template = template;
        this.queue = queue;
    }

    @Override
    public void run(ApplicationArguments args) {
        template.convertAndSend(queue, "OrderCreated:order-42");
        System.out.println("Sent: OrderCreated:order-42");
    }
}
```

Because the `publish` profile does not activate `PollingJmsConfiguration`, Spring Boot can auto-configure a default `JmsTemplate` for the producer. This runner sends only **one message per startup** and does not verify consumer receipt/ACK.

### 6.8. Testing the three profiles without running two consumers at once

Start the broker in a test environment and pass credentials via environment variables. To test polling:

1. Send a message using the `publish` profile.
2. Stop the producer process after sending completes.
3. Start the process with the `poll` profile and watch logs.

```bash
# Terminal 1: send event (can stop process after sending)
./gradlew bootRun --args='--spring.profiles.active=publish'

# Terminal 2, once only broker and pending message remain:
./gradlew bootRun --args='--spring.profiles.active=poll'
```

With demo data and the broker receiving the message properly, the poller can print:

```text
Handling event: OrderCreated:order-42
```

To test the listener, **do not run the poll profile at the same time**. Start the app with only the `listener` profile, then send a message from another process using the `publish` profile:

```bash
# Terminal 1: listener only
./gradlew bootRun --args='--spring.profiles.active=listener'

# Terminal 2: send one event to the same broker
./gradlew bootRun --args='--spring.profiles.active=publish'
```

The listener can likewise print:

```text
Handling event: OrderCreated:order-42
```

This is only the **log line emitted by `OrderHandler`**; real stdout includes many Spring/Artemis logs, and ordering across two processes is not fixed. If two messages exist, two lines may appear. If the broker lacks the queue/permissions or is unreachable, the example will fail instead of printing output.

**Do not infer redelivery policy from the `OrderPoller` demo.** With synchronous receiving outside a transaction, the message may already be received/acked before the handler throws, so design transactions before using it for critical workloads.

## 7. Transactions and ACK: a bigger reliability factor than "poll vs. listener"

This is the most critical point when turning a prototype into a real application.

### 7.1. Polling receives then processes later: an easily missed gap

This code looks very natural:

```java
Object payload = jmsTemplate.receiveAndConvert("orders.in");
if (payload != null) {
    businessService.updateDatabase(payload);
}
```

Yet if `receiveAndConvert` uses a JMS session not wrapped in a shared transaction with processing, **the message acknowledgement point can occur inside the receive operation itself**. When `updateDatabase` fails afterward, the broker may treat the message as consumed and not redeliver as expected.

Replacing `receiveAndConvert` with `receive` **does not automatically close** this gap. Separating receive and processing from the transaction boundary is the root cause, not the method name.

### 7.2. More reliable polling within a JMS transaction

To roll back a message when the handler fails, use `JmsTransactionManager` sharing the same `ConnectionFactory` as `JmsTemplate`; a Spring-managed transaction must wrap **both receiving and processing**.

An **illustrative supplementary example** for an application with a JMS transaction manager bean named `jmsTransactionManager`:

```java
@Transactional("jmsTransactionManager")
public void pollAndHandle() {
    Object body = pollingJmsTemplate.receiveAndConvert("orders.in");
    if (body instanceof String text) {
        businessHandler.handle(text);
    }
}
```

This is an **illustrative method**, not a standalone Java file. The annotation requires importing `org.springframework.transaction.annotation.Transactional`. The transaction manager bean can be declared via:

```java
@Bean("jmsTransactionManager")
JmsTransactionManager jmsTransactionManager(
        ConnectionFactory connectionFactory) {
    return new JmsTransactionManager(connectionFactory);
}
```

Requires importing `jakarta.jms.ConnectionFactory`, `org.springframework.jms.connection.JmsTransactionManager`, and `org.springframework.context.annotation.Bean`, placed in a `@Configuration` class. `pollAndHandle` must be invoked **through the Spring transaction proxy**, not via self-invocation `this.pollAndHandle()`. To keep a `@Scheduled` schedule, ensure the scheduler invokes the managed proxy method properly.

`JmsTransactionManager` manages only **JMS** transactions; it does not make database transactions atomic with the broker. If the DB commits while the JMS commit fails, the message may be redelivered. Consumers still need idempotency, or an outbox/inbox/XA pattern as required.

### 7.3. Listener: transactions live inside the listener container

Spring's `DefaultMessageListenerContainer` is designed to run listeners inside a JMS transaction when configured with `sessionTransacted = true` or an appropriate transaction manager. When the handler throws an exception **allowing the error to propagate to the container**, the JMS transaction can roll back and the provider redelivers the message.

Conversely, per Spring Javadoc, `DefaultMessageListenerContainer` with `AUTO_ACKNOWLEDGE` may ACK **before** the handler runs; if the handler fails, you cannot assume by default that the message will be redelivered. Therefore, never write:

```java
@JmsListener(destination = "orders.in")
public void onMessage(String body) {
    try {
        businessHandler.handle(body);
    } catch (Exception ex) {
        // ANTI-PATTERN: swallows error, container may treat it as success.
    }
}
```

This is an **anti-pattern**. Decide explicitly which failures should retry and which should move to a DLQ, and let exceptions/transaction policies express that outcome. `AUTO_ACKNOWLEDGE`, `CLIENT_ACKNOWLEDGE`, and local transactions are not equivalent, nor do all listener containers behave identically.

### 7.4. Do not conflate JMS ACK with business commit

Whether polling or using a listener, if business logic writes to a separate database, **a JMS transaction does not automatically wrap the database transaction**. The DB may commit while JMS has not yet ACKed/committed, causing the event to be redelivered. Designing idempotent consumers using `eventId`/business keys is foundational.

For stronger guarantees, consider inbox/deduplication, transactional outbox, or an XA-capable transaction coordinator (at the cost of latency and operational complexity). Never pick a listener merely because it sounds "more reliable"; verify actual configuration and failure modes.

## 8. Ordering, scaling, and two consumers competing on the same queue

In the example, both poller and listener target `orders.in`. If **both profiles or two services** consume concurrently:

```text
                         queue "orders.in"
                                |
                    +-----------+-----------+
                    |                       |
             Poller consumer           Listener consumer
               receives M1?              receives M2?
```

For a **queue**, each message is typically delivered to **one eligible consumer**, not copied automatically to every consumer. Having two receive paths on the same queue creates **competing consumption**, making demo results nondeterministic. For **topics**, subscription semantics differ, so evaluate `pubSubDomain`, durable/shared subscriptions, selectors, and connection/client IDs.

Factors to examine when increasing concurrency:

- `@JmsListener(concurrency = "1")` limits concurrent consumers for that endpoint, not total replicas across machines.
- Multiple consumers can finish processing out of order; even a single consumer can encounter redelivery, delayed delivery, and multi-session producers.
- JMS priority, selectors, and transactions also influence observed order.
- When business ordering per order is required, use `aggregateId`, `sequence/version`, broker-supported message groups, and version-checked state updates.
- Do not run multiple pollers on the same queue assuming each poller reads a "dedicated partition" unless the broker has configured partitioning/distribution.

**Switching from polling to a listener does not automatically create exactly-once, strict FIFO, or fan-out.** Those guarantees require explicit contracts and configuration.

## 9. Performance and backpressure

### 9.1. When polling is advantageous

- Messages arrive sparsely and only need processing at specific times.
- Downstream systems cap request rates, so you want to process at most a small batch per turn.
- Batch workflows need explicit start/end boundaries for summary reporting.
- Jobs must turn on/off strictly by schedule alongside dependent resources.
- Receiving a message is one step in a synchronous orchestration flow **with a finite timeout**.

Polling does not always save resources: a job running no-wait receives very frequently can cost more than a listener container with optimized connection/consumer pooling.

### 9.2. When a listener is advantageous

- Processing is needed almost immediately upon message arrival.
- Message flow is continuous and backlogs can spike abruptly.
- You want the framework to manage basic container lifecycle/recovery/throttling.
- You need scaling via consumer counts with proper lag and error observability.
- Event-driven processing is a long-lived background responsibility of the service.

Still, a listener does not automatically prevent overload. For example, raising `concurrency` from 1 to 20 when the database can sustain only a few concurrent transactions can degrade overall system stability.

### 9.3. Different tuning knobs

| Poller | Listener |
| --- | --- |
| `fixedDelay` or cron schedule | Concurrent consumer count |
| `receiveTimeout` | Container `receiveTimeout` and recovery/backoff |
| Max messages per run | Max concurrency, pool/executor limits |
| Batch duration, next-run backoff | Start/stop endpoint, consumer throttling |
| Job deadline and shutdown | Container graceful shutdown/drain |
| Number of jobs/replicas | Number of listener instances/replicas |

Do not treat a listener container's `receiveTimeout` as an "application schedule interval" like `@Scheduled`: the container has its own receive loop, thread lifecycle, and scaling strategy.

A cautionary example: with `@Scheduled(fixedDelayString="5000")` and a poller taking at most one message, each run finishes processing and then waits another 5 seconds. When backlog grows, this is often an intentional throttle; if unintentional, consider increasing batch size, using a bounded worker pool, or switching to a listener.

## 10. Observability, testing, and migration workflow

### 10.1. Metrics to watch

| Suggested metric | Polling | Listener |
| --- | --- | --- |
| `queue_depth` / `oldest_message_age` | Yes | Yes |
| `poll_attempt_total` | Primary | Not needed at application level |
| `poll_empty_total` | Important for measuring empty-poll cost | Not needed with same definition |
| `poll_duration` | Receive wait + processing | No |
| `listener_active_consumers` | No | Important |
| `message_process_success_total` | Yes | Yes |
| `message_process_failure_total` | Yes | Yes |
| `redelivery_total` / DLQ depth | Yes | Yes |
| `processing_latency` (arrival → business commit) | Yes | Yes |

These are **suggested metric names**, not built-in Spring properties. Use Micrometer/Actuator and corresponding broker metrics, tagging `destination`, `consumerType`, and `eventId`/correlation where needed for tracing; avoid logging sensitive payloads.

### 10.2. Testing polling

For `OrderPoller`, unit tests can mock `JmsTemplate`:

```java
package demo.receive;

import org.junit.jupiter.api.Test;
import org.springframework.jms.core.JmsTemplate;

import static org.mockito.Mockito.*;

class OrderPollerTest {
    @Test
    void noMessageMeansNoBusinessCall() {
        JmsTemplate template = mock(JmsTemplate.class);
        OrderHandler handler = mock(OrderHandler.class);
        when(template.receiveAndConvert("orders.in")).thenReturn(null);

        OrderPoller poller =
                new OrderPoller(template, handler, "orders.in");
        poller.pollOnce();

        verify(template).receiveAndConvert("orders.in");
        verifyNoInteractions(handler);
    }

    @Test
    void receivedTextGoesToHandler() {
        JmsTemplate template = mock(JmsTemplate.class);
        OrderHandler handler = mock(OrderHandler.class);
        when(template.receiveAndConvert("orders.in"))
                .thenReturn("OrderCreated:order-42");

        new OrderPoller(template, handler, "orders.in").pollOnce();

        verify(handler).handle("OrderCreated:order-42");
    }
}
```

Save at `src/test/java/demo/receive/OrderPollerTest.java`, run:

```bash
./gradlew test --tests demo.receive.OrderPollerTest
```

If the tests pass, Gradle reports success (log format varies by version). Mock tests **do not prove** the broker ACKed, redelivered, or handled transactions; they only test control flow and `null` handling.

### 10.3. Testing listeners

For a listener, unit tests can call `new OrderListener(mockHandler).onMessage("OrderCreated:order-42")` and verify the handler. Integration tests are what verify the real container, broker/destination, receiving, ack/rollback, concurrency, recovery, and transaction settings.

Minimum scenarios to run for **both approaches**:

1. Empty queue: polling must time out/return null; listener must not invoke the business handler.
2. One valid message: processed properly and records exactly one **business intent** (with idempotency).
3. Business handler throws exception: verify whether the message rolls back/redelivers per **designed policy**.
4. Broker interruption then recovery: how the poll schedule / container recovers, and whether duplicates occur.
5. Large backlog and slow dependency: processing throughput, queue age, concurrency, and backpressure.
6. Two application instances: competing consumption, business ordering, and graceful shutdown.

### 10.4. Migrating from poller to listener without losing messages

A safe migration procedure:

1. Confirm the **exact same destination**, selector, queue/topic semantics, converter, schema, and permissions.
2. Document the poller's current ack/transaction policy; design the new listener with equivalent or better failure/retry/DLQ behavior.
3. Share a common idempotent business handler to avoid behavioral drift.
4. Deploy the listener **without yet enabling it on production traffic**; verify on a test queue or cleanly isolated consumer.
5. Stop the poller gracefully, wait for in-flight jobs/transactions to finish, then enable the listener. Do not run both consumer types concurrently when a clean cutover is required.
6. Monitor backlog, queue age, redeliveries, DLQ, and throughput; maintain a rollback plan and criteria to prevent duplicates or lost events.

Architectural rollback works similarly: stop the listener gracefully, verify in-flight work completes, and then re-enable the polling scheduler. Stopping a listener does not mean every in-flight message has committed; verify drain time and transaction completion.

## 11. Common misconceptions

| Mistake | Why is it dangerous? | Proper fix |
| --- | --- | --- |
| Using default `JmsTemplate.receive` in an HTTP handler | Can block the thread indefinitely | Finite timeout or decouple receiving from request threads |
| Confusing Spring `receiveTimeout=0` with `MessageConsumer.receive(0)` | Two different conventions | In `JmsTemplate`, 0 is no-wait; -1 is indefinite |
| No-wait polling inside `while(true)` without backoff | Busy polling wastes CPU and broker load | Scheduler, backoff, batch limits |
| Thinking `@Scheduled` makes `receive` non-synchronous | Scheduler only runs the method on another thread | The scheduler thread still blocks inside `receive` |
| Thinking `@JmsListener` uses no threads or is always push | Container uses threads and may run receive loops | Account for threads/connections and container lifecycle |
| Polling receives then updates DB outside a transaction | Message may ACK before business failure | Wrap receive + handling in a transaction or use idempotency/inbox |
| Listener swallows exceptions | Container may treat processing as successful | Let exceptions propagate per retry/DLQ policy |
| Choosing a listener for "exactly once" | No default business exactly-once guarantee | Enforce transactions, idempotency, and dedup |
| Running poller and listener on the same queue to "compare" | They compete for messages and confuse logs | Run separate profiles and isolated test queues |
| Raising listener concurrency expecting order to remain | Parallel processing can reorder commits | Versioning/sequencing, grouping, per-aggregate partitioning |
| Using one polling job for a huge backlog taking one message per tick | Throughput is far too low | Increase capacity within limits or switch to a listener |
| Increasing listener concurrency unboundedly | Overloads DB/APIs and causes redelivery storms | Cap concurrency/backpressure and configure DLQ |
| Assuming an empty queue is a `receiveAndConvert` error | Timeout returns `null` | Handle null normally; track empty-poll metrics |
| Treating queue receipt as completed business work | JMS ACK and DB commit are distinct | Track separate business status/confirmation |

## 12. Decision checklist

Walk through these questions in order:

1. **Must consumption run only on a schedule / batch / maintenance window?** If yes, pick scheduled polling or a listener with strictly orchestrated lifecycle; polling is usually simpler.
2. **Must messages be processed nearly continuously as they arrive?** If yes, prefer `@JmsListener`.
3. **Are there strict SLAs and significant backlogs?** Measure throughput, handler latency, and resource budgets; a concurrent listener is usually more convenient, but cap load.
4. **Must handler failures trigger redelivery?** Design transactions/acks before choosing; never use a non-transacted demo poller for critical work.
5. **Is per-aggregate ordering required?** Standardize `aggregateId`/`sequence` contracts and idempotency; evaluate concurrency, replica counts, and message groups/provider features.
6. **Do you need pausing or controlled shutdown?** Define drain rules, retries, metrics, and operational ownership explicitly.

**Remember:** `JmsTemplate.receive` is **synchronous receiving that blocks the calling thread** and fits clearly scheduled or bounded pull tasks. `@JmsListener` is an **application-level asynchronous processing model**, managed by Spring's listener container, suited for continuous event consumption. Reliability and quality in both depend on transactions, acknowledgement, idempotency, backpressure, and operations — **not merely the API name**.

### References

- Spring Framework 6.2 — Receiving a Message (synchronous receive and message-driven POJOs): https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html
- Spring Framework 6.2 — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework 6.2 — JmsTemplate Javadoc (receive, receiveAndConvert, receiveTimeout): https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Framework 6.2 — DefaultMessageListenerContainer and acknowledge/transaction: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
- Spring Boot 3.4 — JMS with Artemis, JmsTemplate and listener auto-configuration: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
- Spring guide — Messaging with JMS: https://spring.io/guides/gs/messaging-jms/
