# Configuring Concurrency with a Single Value or Range in DefaultMessageListenerContainer

**Parent topic:** Default container — Spring Framework / JMS.

**Lesson goal:** Correctly configure the number of concurrent consumers for `DefaultMessageListenerContainer` using a **single-value** or **range** string, via a factory, `@JmsListener`, Spring Boot properties, or Java API; know how to read runtime state, explain dynamic scaling, and choose min/max suited for queues, topics, processing order, transactions, resources, and replica count.

**Version scope:** Java 17+, Spring Framework 6.2.x, Spring Boot 3.5.x, Jakarta Messaging (`jakarta.jms`), and a compatible JMS broker such as Apache ActiveMQ Artemis. Parser behavior of the Default container is verified against official Javadoc; **do not** extrapolate this rule to every messaging framework or Spring Rabbit/AMQP.

> **Most important takeaway:** With **`DefaultMessageListenerContainer`**, `setConcurrency("5")` means **min = 1, max = 5**, not five fixed consumers. `setConcurrency("5-5")` sets **min = 5, max = 5**. `"2-5"` means maintaining two core consumers and scaling up to five. This interpretation also applies when `DefaultJmsListenerContainerFactory` and `@JmsListener(concurrency=...)` pass the configuration down to the Default container.

## 1. What Are Concurrent Consumers Really?

Spring's `DefaultMessageListenerContainer` runs tasks that call `MessageConsumer.receive()` to pull messages from the broker and invoke a handler. Each consumer invoker is typically paired with a JMS `Session` and `MessageConsumer`, scheduled on a worker thread from a `TaskExecutor`. An invoker processes one message, completes processing/transactions accordingly, and then receives the next message.

~~~text
JMS queue: orders.jobs
    │
    ├── Message A ──► Invoker 1 / JMS Session 1 ──► @JmsListener handler
    ├── Message B ──► Invoker 2 / JMS Session 2 ──► @JmsListener handler
    ├── Message C ──► Invoker 3 / JMS Session 3 ──► @JmsListener handler
    └── Message D ──► Waiting for dispatch condition and idle consumer
~~~

Concurrency here is the **number of JMS consumer invokers allowed to run concurrently inside one listener container**, not the number of messages sitting in the queue, HTTP requests, CPU cores, producers, or TCP connections. One `Connection` can hold multiple `Session`s. One invoker processes many messages over time rather than spawning a new thread per message.

With a queue having two consumers, two messages can be processed concurrently. However, both consumers can also wait on `receive(timeout)` at the same time; in that state they are **active** according to the container without executing business logic yet. Therefore, do not use `getActiveConsumerCount()` as the count of busy message handlers at an instant.

## 2. The Two Root Numbers: concurrentConsumers and maxConcurrentConsumers

| Property | Meaning | Default in Default container |
| --- | --- | --- |
| `concurrentConsumers` | The **core/minimum** level the container tries to maintain while running | 1 |
| `maxConcurrentConsumers` | The **maximum** level the container can create when load grows | 1 |

With `min=2, max=5`:

~~~text
Consumer invoker 1  CORE ── maintained
Consumer invoker 2  CORE ── maintained
Consumer invoker 3  EXTRA ─ may be created when many messages arrive
Consumer invoker 4  EXTRA ─ may be created while load remains high
Consumer invoker 5  EXTRA ─ upper limit
                  load drops / idle
                  └─ EXTRAs may stop, CORE is maintained
~~~

Can be configured directly in Java:

~~~java
DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();

container.setConcurrentConsumers(2);
container.setMaxConcurrentConsumers(5);
~~~

This is only a **configuration snippet**; running requires a `ConnectionFactory`, destination, listener, lifecycle, and broker. Both parameters must be positive integers. Enforce the rule `1 ≤ min ≤ max` yourself; do not rely on setter clamping/normalizing behavior if max is accidentally entered lower than min.

A core consumer being "maintained" per lifecycle policy does **not** mean the broker definitely has a connected consumer if the network is down, credentials are invalid, or the executor cannot allocate threads.

## 3. Single-Value vs. Range Syntax: Must-Know Table

`DefaultMessageListenerContainer.setConcurrency(String)` supports:
- `"N"`: **upper limit N**, keeping min at `1`.
- `"MIN-MAX"`: explicitly sets both core min and upper max.

| String configuration | Min/core | Max | Correct interpretation |
| --- | ---: | ---: | --- |
| Not configured | 1 | 1 | One consumer |
| `"1"` | 1 | 1 | One fixed consumer |
| `"4"` | 1 | 4 | **Elastic 1 to 4** |
| `"4-4"` | 4 | 4 | **Fixed 4** |
| `"2-5"` | 2 | 5 | Two core, can scale up to five |
| `"1-8"` | 1 | 8 | Fewer resources when idle, can scale up to eight |
| `"5-10"` | 5 | 10 | Five core, ceiling ten |
| `"8-8"` | 8 | 8 | Fixed eight |

~~~java
container.setConcurrency("4");   // min = 1, max = 4
container.setConcurrency("4-4"); // min = 4, max = 4
container.setConcurrency("2-4"); // min = 2, max = 4
~~~

Therefore, the statement "`concurrency="4"` creates four workers" is **false** for the Default container. If you want four core consumers right at startup, use `"4-4"`. If you want to start with one and scale up to four, use `"1-4"` or `"4"`.

### Invalid Inputs and Parser Traps

- `"0"` or `"0-5"` is invalid because you cannot have 0 core consumers in this configuration.
- `"auto"`, `"2..5"`, `"two-five"` are not valid `setConcurrency(String)` syntax.
- `"5-2"` reverses the min/max intent; Spring 6.2 may normalize max up to min rather than always throwing. Do not use that intentionally.
- Avoid unusual whitespace such as `"2 - 5"`: the parser is not guaranteed to trim every segment before converting to integers.
- This is a string parsed by the API, not arithmetic subtraction.

**Cross-framework difference:** in Spring Rabbit/AMQP, listener containers have their own APIs and single-integer parsing rules. Do not blindly copy the rule "`N` means min1/maxN" to classes other than Spring JMS `DefaultMessageListenerContainer`.

## 4. Using Java Setters to Express Fixed or Elastic

Fixed count:

~~~java
container.setConcurrentConsumers(3);
container.setMaxConcurrentConsumers(3);
// Equivalent to setConcurrency("3-3").
~~~

Elastic range:

~~~java
container.setConcurrentConsumers(2);
container.setMaxConcurrentConsumers(6);
// Equivalent to setConcurrency("2-6").
~~~

**Why do both APIs exist?** Configuration code might receive separate integer inputs from a config service, while annotations/factories use a short string for convenience. Both produce the min/max pair for the same container. In finished code, prefer a single clear source of configuration rather than setting a string and calling overlapping setters in multiple places.

`maxConcurrentConsumers` is a **configuration limit**, not an instant consumer count right after calling the setter. The container must have load, executor thread allocation, and proper broker dispatch to scale. Conversely, when you want a fixed count, set min=max; when the broker is absent, even a fixed container may be in recovery.

## 5. Configuring on DefaultJmsListenerContainerFactory in Plain Spring Framework

A common pattern is declaring a factory bean:

~~~java
package example.jms;

import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class JmsListenerConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory cf) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setPubSubDomain(false);
        factory.setConcurrency("2-5");
        factory.setReceiveTimeout(1_000L);
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

This Java 17 class compiles in a Spring Framework 6.x project with `spring-jms`, the Jakarta JMS API, and a `ConnectionFactory` bean from a provider. **It has no standalone `main`**, requiring a Spring `ApplicationContext`, broker, and listener bean.

`@EnableJms` activates `@JmsListener` processing; the factory carries the default name `jmsListenerContainerFactory`. When Spring discovers an annotated endpoint using that factory, it creates **one `DefaultMessageListenerContainer` per endpoint** and applies the 2..5 concurrency pair. If four endpoints share the factory, each endpoint gets its own range, **not four endpoints sharing max 5**.

~~~text
Factory concurrency = 2-5
  ├─ Orders container:    min2..max5
  ├─ Billing container:   min2..max5
  ├─ Shipping container:  min2..max5
  └─ Audit container:     min2..max5
Configured maximum = 4 × 5 = 20 invoker tasks / replica
~~~

Containers already created do not necessarily auto-update if the factory bean is mutated at runtime. To change a running level, act on the concrete container/registry with a runbook or update configuration and redeploy.

## 6. @JmsListener Annotation Can Override the Factory

Spring supports per-**listener endpoint** configuration via `@JmsListener(concurrency = "...")`:

~~~java
@Component
class OrderListeners {

    @JmsListener(
            id = "regularOrders",
            destination = "orders.regular",
            concurrency = "1-3")
    public void regular(String body) {
        processRegular(body);
    }

    @JmsListener(
            id = "criticalOrders",
            destination = "orders.critical",
            concurrency = "4-4")
    public void critical(String body) {
        processCritical(body);
    }
}
~~~

This is a snippet inside a Spring bean; import `@Component`, `@JmsListener`, and implement `processRegular`, `processCritical`. If the factory has `"2-5"`, then:
- `regularOrders` uses **min1/max3** per annotation.
- `criticalOrders` uses **min4/max4** per annotation.
- A third listener omitting the concurrency attribute uses the factory's setting.

The `@JmsListener` Javadoc clearly states this attribute **overrides the container factory's concurrency**. It does not override all connection/transaction/converter settings; those still come from the factory or endpoint config.

~~~java
@JmsListener(
        id = "wrongFixedAssumption",
        destination = "demo.jobs",
        concurrency = "4")  // MIN=1, MAX=4, not fixed 4.
public void handle(String body) {
    process(body);
}
~~~

If you need exactly four core consumers, change it to `concurrency="4-4"`. Do not set min too high just to "have lots of threads": with low-traffic queues, idle consumers still occupy resources.

## 7. Spring Boot 3.5: min-concurrency and max-concurrency in YAML

Spring Boot provides two properties for the default JMS listener factory:

~~~yaml
spring:
  jms:
    listener:
      min-concurrency: 2
      max-concurrency: 5
      receive-timeout: 1s
~~~

In Boot 3.5's standard auto-configuration, this config represents **min2/max5**. This expresses it via two separate values rather than passing a single `"2-5"` string.

**Special note:** Boot 3.5 property metadata specifies that when only `min-concurrency` is set **without `max-concurrency`**, min is also used as max. For example:

~~~yaml
spring:
  jms:
    listener:
      min-concurrency: 4
~~~

When Boot's default listener factory is used, this configures **fixed min4/max4**. It **differs** from passing `"4"` to `DefaultMessageListenerContainer.setConcurrency(String)`, which sets min1/max4. Avoid confusing the two API layers.

| Intent | Spring factory or annotation | Spring Boot properties |
| --- | --- | --- |
| Fixed 1 | `"1"` or `"1-1"` | `min-concurrency: 1`, max unset |
| Fixed 3 | `"3-3"` | `min-concurrency: 3`, max unset |
| Elastic 1..3 | `"3"` or `"1-3"` | `min-concurrency: 1` and `max-concurrency: 3` |
| Elastic 2..5 | `"2-5"` | `min-concurrency: 2` and `max-concurrency: 5` |
| Fixed 5 | `"5-5"` | `min-concurrency: 5` and `max-concurrency: 5` |

If Boot's default factory uses 2..5 while an annotation specifies `concurrency="1-8"`, that listener applies **1..8** per the annotation. YAML is not a hard *global max* enforced across the entire app.

**When Boot properties have no effect:** an application declares a custom `DefaultJmsListenerContainerFactory` without calling `DefaultJmsListenerContainerFactoryConfigurer`, bypassing Boot properties. Check which factory each endpoint actually uses.

## 8. Creating a Custom Factory in Boot While Keeping Boot Configuration

If the application needs a dedicated factory for critical queues, you can leverage Boot's configurer:

~~~java
@Configuration(proxyBeanMethods = false)
class CriticalQueueConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory criticalQueueFactory(
            DefaultJmsListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        configurer.configure(
                factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));

        factory.setConcurrency("3-6");
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

Imports: `jakarta.jms.ConnectionFactory`, `org.springframework.context.annotation.Configuration`, `@Bean`, `org.springframework.jms.config.DefaultJmsListenerContainerFactory`, `org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer`, and `org.springframework.boot.jms.ConnectionFactoryUnwrapper`.

This is a snippet in a Spring Boot 3.5 project, not a standalone class. `Configurer` preserves useful Boot defaults (converter, transaction settings, resource handling...) before you override `concurrency`. `ConnectionFactoryUnwrapper.unwrapCaching` retrieves the native factory from caching wrappers in supported cases; this is Spring Boot's recommended pattern for listener containers so the container manages recovery itself.

The listener selects the factory bean by name:

~~~java
@JmsListener(
        id = "criticalInvoices",
        destination = "critical.invoices",
        containerFactory = "criticalQueueFactory")
public void handle(String payload) {
    processInvoice(payload);
}
~~~

If you also add `concurrency="2-2"` on this annotation, the annotation overrides the factory's `"3-6"` for this endpoint, rather than creating both 3–6 and 2–2 consumers. `containerFactory` is the bean name, `id` is the endpoint ID in the registry, and `destination` is the broker queue/topic.

## 9. Java 17 + Spring Boot Example: Observing Fixed and Elastic

This hands-on lab uses two queues:
- `demo.fixed.jobs`: listener `fixedJobs` with `concurrency="3-3"`.
- `demo.elastic.jobs`: listener `elasticJobs` with `concurrency="2-5"`.

The application sends 12 messages to each queue and reads the configuration from `JmsListenerEndpointRegistry`. The goal is **reading actual min/max**, not assuming elastic always hits 5 or fixed always has all connected consumers when the broker is down.

**Run prerequisites:** Java 17+, Spring Boot 3.5.0, compatible Gradle, an Apache ActiveMQ Artemis broker running at `tcp://localhost:61616`, a user with send/consume permissions, and both queues existing or broker auto-create enabled. The lesson uses a real release version as an API anchor, not claiming it is the newest Boot release.

### 9.1. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

repositories { mavenCentral() }

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-concurrency'
~~~

### 9.2. application.yaml

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
  jms:
    pub-sub-domain: false
    listener:
      min-concurrency: 1
      max-concurrency: 3
      receive-timeout: 1s
~~~

Set the password via environment variable `SPRING_ARTEMIS_PASSWORD` or a secret manager. Do not hard-code credentials in Git. The default YAML 1..3 only applies to endpoints that do not override concurrency; the two Java endpoints below override it to demonstrate fixed and elastic.

### 9.3. Complete Java Application

`src/main/java/example/jmsconcurrency/JmsConcurrencyApplication.java`:

~~~java
package example.jmsconcurrency;

import java.util.List;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class JmsConcurrencyApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsConcurrencyApplication.class, args);
    }

    @Bean
    ApplicationRunner demonstrate(
            JmsTemplate template,
            JmsListenerEndpointRegistry registry) {

        return args -> {
            for (String id : List.of("fixedJobs", "elasticJobs")) {
                MessageListenerContainer container =
                        registry.getListenerContainer(id);

                if (!(container instanceof
                        DefaultMessageListenerContainer dmlc)) {
                    throw new IllegalStateException(
                            "Expected Default container for " + id);
                }

                System.out.printf(
                        "CONFIG %s min=%d max=%d scheduled=%d active=%d%n",
                        id,
                        dmlc.getConcurrentConsumers(),
                        dmlc.getMaxConcurrentConsumers(),
                        dmlc.getScheduledConsumerCount(),
                        dmlc.getActiveConsumerCount());
            }

            for (int i = 1; i <= 12; i++) {
                template.convertAndSend("demo.fixed.jobs", "fixed-" + i);
                template.convertAndSend("demo.elastic.jobs", "elastic-" + i);
            }
            System.out.println("SENT_24_MESSAGES");
        };
    }
}

@Component
class DemoJobsListeners {

    @JmsListener(
            id = "fixedJobs",
            destination = "demo.fixed.jobs",
            concurrency = "3-3")
    public void fixed(String payload) {
        handle("FIXED", payload);
    }

    @JmsListener(
            id = "elasticJobs",
            destination = "demo.elastic.jobs",
            concurrency = "2-5")
    public void elastic(String payload) {
        handle("ELASTIC", payload);
    }

    private void handle(String kind, String payload) {
        try {
            Thread.sleep(250L);
            System.out.printf(
                    "%s thread=%s payload=%s%n",
                    kind, Thread.currentThread().getName(), payload);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Handler interrupted", ex);
        }
    }
}
~~~

### 9.4. Run and Observe

With the Gradle wrapper and test broker running:

~~~bash
./gradlew bootRun
~~~

Some log lines that may appear:

~~~text
CONFIG fixedJobs min=3 max=3 scheduled=3 active=3
CONFIG elasticJobs min=2 max=5 scheduled=2 active=2
ELASTIC thread=... payload=elastic-1
FIXED thread=... payload=fixed-1
SENT_24_MESSAGES
~~~

**This is not guaranteed stdout.** Scheduled/active counts may differ at the exact moment of measurement because container startup/recovery is asynchronous. Consumers may process messages even while `ApplicationRunner` is still sending. Because queues have multiple consumers, handle/commit order is not fixed; `elastic-4` may run before `elastic-3`. With 250ms processing time, the container also does not necessarily scale from 2 to 5 because backlog may drain quickly or broker prefetch may distribute differently.

**The example has no business DB**, only logging; it does not prove exactly-once processing, and a startup runner should not be used to emit production messages. On every restart, the runner sends more test messages.

## 10. Measure Both Min/Max and Running Invokers

`DefaultMessageListenerContainer` provides these getters:

~~~java
int min = dmlc.getConcurrentConsumers();
int max = dmlc.getMaxConcurrentConsumers();
int scheduled = dmlc.getScheduledConsumerCount();
int active = dmlc.getActiveConsumerCount();
~~~

| Getter | What It Provides |
| --- | --- |
| `getConcurrentConsumers()` | **Configured** core min level |
| `getMaxConcurrentConsumers()` | **Configured** max level |
| `getScheduledConsumerCount()` | Number of scheduled consumer invoker tasks |
| `getActiveConsumerCount()` | Number of invokers active per container lifecycle |

**Active is not the number of handlers currently executing business logic**: an active invoker may be waiting on `receive(timeout)`. Scheduled is not necessarily the number of broker-connected consumers when a connection fails or the executor is saturated. Simply seeing `max=10` also does not prove 10 consumers exist right now.

Read via registry by ID:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("elasticJobs");

if (container instanceof DefaultMessageListenerContainer dmlc) {
    System.out.printf(
            "min=%d max=%d scheduled=%d active=%d%n",
            dmlc.getConcurrentConsumers(),
            dmlc.getMaxConcurrentConsumers(),
            dmlc.getScheduledConsumerCount(),
            dmlc.getActiveConsumerCount());
}
~~~

`registry` is the injected `JmsListenerEndpointRegistry` Spring bean. It looks up the container created for the matching endpoint `id`; **not** by queue name. Use `instanceof` instead of casting blindly, because another factory could create a `SimpleMessageListenerContainer`.

## 11. Scale Up/Down Is Not Simply Queue Depth Exceeding a Threshold

The Default container does not by default follow a formula like "queue depth > 100 then add 1 consumer". It observes receive activity, busy/idle invokers, allowed surplus scheduling, and executor resources. Min consumers are retained; surplus consumers can be created when load grows and stopped when there is no work left.

~~~text
min=2, max=5

t0: queue empty             [core A, core B]
t1: backlog arrives         [core A busy, core B busy]
t2: more messages remain    [core A, core B, extra C] (possible)
t3: load continues          [core A, B, C, extra D, extra E] (possible)
t4: queue becomes empty     [surplus C/D/E idle]
t5: past idle threshold     [core A, core B]
~~~

**This order and timing are illustrative only.** Reaching max depends on `TaskExecutor`, message processing time, broker credit/prefetch, selectors, timeouts, and idle limits. "Queue depth increases ⇒ active immediately equals max" does not necessarily hold.

If one consumer prefetches too many messages onto the client, new consumers may sit idle even when the broker queue shows fewer messages. If the database is slow, opening more consumers can worsen DB connection pool contention instead of increasing throughput.

## 12. Receive Timeout and Idle Limits Alter Scaling Cadence

| Setting | Role |
| --- | --- |
| `setReceiveTimeout(long)` | Duration a consumer invoker waits for a message, typically 1000ms in Default container |
| `setIdleConsumerLimit(int)` | Number of idle consumers allowed when deciding to schedule more (default 1) |
| `setIdleTaskExecutionLimit(int)` | Limit on idle task executions before a surplus consumer is reclaimed (default 1) |
| `setIdleReceivesPerTaskLimit(int)` | Consecutive null receives required to mark a task idle |
| `setMaxMessagesPerTask(int)` | Max receive **attempts** in a task, which may include null receives |
| `setTaskExecutor(Executor)` | Where invoker tasks are scheduled, affecting pool capacity and task lifetime |

**Distinguish two counts:** `maxMessagesPerTask` is not just successfully processed messages; it can count timed-out receive attempts. `idleTaskExecutionLimit` counts idle task executions, unlike `idleReceivesPerTaskLimit` which counts consecutive null receives.

In Spring Framework 6.2, with the default/non-pooling executor, the effective default `idleReceivesPerTaskLimit` is 10 for surplus consumers. If each `receive` waits at most one second, a surplus consumer may be reclaimed after roughly 10 empty polls, or about 10 seconds in an ideal scenario. **This is not a fixed timing SLA**, and core consumers are still retained per min.

With a `SchedulingTaskExecutor` preferring short-lived tasks, `maxMessagesPerTask` may default to 10; tasks are split/rescheduled differently from the default executor. Only adjust idle limits when load tests show slow ramp-up or overly frequent scale-up/down—not because "since a range was set, every property must be tuned".

## 13. TaskExecutor: Setting Max Does Not Guarantee Enough Threads

A `DefaultMessageListenerContainer` runs invoker tasks through a Spring `TaskExecutor`. With the default executor, this is typically `SimpleAsyncTaskExecutor`. When using a custom bounded executor, invokers can hold threads long-term because each task loops on `receive`.

~~~text
Custom executor has 3 threads:
Thread #1: core invoker A → receive → handler → receive ...
Thread #2: core invoker B → receive → handler → receive ...
Thread #3: extra invoker C → receive → handler → receive ...
Tasks D and E: must wait for an executor slot even though container max=5
~~~

**Lack of scaling is not necessarily a JMS setting issue:** if the executor pool is small or shared across many endpoints, scheduled invokers may not get threads. Measure executor active count/queue length, broker consumer count, handler duration, and idle count before concluding `setConcurrency` is broken.

Also avoid sharing a single bounded pool sized smaller than total core consumers across all endpoints. Core invokers can hold threads indefinitely and starve the remaining endpoints.

### Virtual Threads

Spring Framework 6.2+ supports virtual threads on Java 21+ with the default executor under appropriate conditions, though **this Java 17 illustration** does not enable them. Virtual threads reduce JVM waiting overhead rather than turning broker JMS sessions, prefetch memory, database connections, or API rate limits infinite.

## 14. Fixed vs. Elastic: When to Choose Which?

| Criterion | Fixed `"4-4"` | Elastic `"1-4"` / `"4"` |
| --- | --- | --- |
| Core consumers | 4 | 1 |
| Max consumers | 4 | 4 |
| Footprint when queue is empty | Usually larger | Usually smaller |
| Immediate burst responsiveness | Core already warm | Must schedule extra invokers |
| Invoker count changes with load | Not due to min/max | Can scale up/down |
| Resource budget predictability | Easier | Requires observing dynamic scaling |
| Suitable for | Steady baseline load, latency-sensitive | Bursty load, wanting low idle resources |
| Ordering loss risk when >1 | Yes | Yes when scaling to 2+ |

If the queue is small and requires ordering, `"1-1"` may be appropriate. If the queue always has a backlog and downstream has ample capacity, fixed `"4-4"` may improve startup latency. If the queue sits idle for hours and then sees brief bursts, `"1-4"` saves idle cost, though ramp-up should be tested.

**Do not assume fixed means no retries.** Container/recovery/broker can redeliver even with a single consumer; idempotency is still required for critical operations.

## 15. Increasing Concurrency Can Break Processing Order

~~~text
Broker dispatch: M1, M2, M3
Consumer A receives M1 → processes 2s ─────────► DB COMMIT
Consumer B receives M2 → processes 100ms ─► DB COMMIT
Consumer C receives M3 → processes 300ms ─► DB COMMIT

Business commit order can be M2, M3, M1.
~~~

With multiple consumers on a queue, processing order and completion order can differ from enqueue order, even if the broker dispatches in order. If a workflow requires strict state ordering for the same `orderId`, consider:
- One consumer if strict total ordering is required and reduced throughput is acceptable.
- Message grouping via `JMSXGroupID` if supported by the broker and tested across failovers.
- Partitioning by aggregate key, event versioning, optimistic locking, or a state machine.
- Idempotent handling to cope with redeliveries/duplicate publishes.

**A `"1-5"` range may temporarily process in order while at one consumer, then break ordering when scaling to five.** Do not treat the min=1 state as an ordering promise across all load levels.

## 16. Topics Differ from Queues When Increasing Consumer Count

Spring Default container Javadoc warns: when the destination is a **topic** with standard JMS subscriptions, increasing consumers can create multiple independent subscriptions all receiving **a copy of the same event**, rather than sharing load like competing queue consumers.

~~~text
Topic: audit.events
   │
   ├─ Consumer/subscription A receives Event X
   ├─ Consumer/subscription B receives Event X
   └─ Consumer/subscription C receives Event X
       → potentially three callbacks for the same Event X
~~~

For a regular non-shared topic, typically keep `concurrency="1-1"` unless there is a shared/durable subscription design supported by the JMS provider and verified. `pubSubDomain=true` only marks the destination as a topic; it **does not automatically configure shared subscriptions or durable identity** across consumers.

On a queue, multiple consumers compete to receive messages, and the broker dispatches one message to one consumer per delivery. On a topic, multiple subscriptions receive events under pub/sub semantics. Blindly increasing concurrency on a topic can be mistaken for duplicate business processing.

## 17. Sessions, Connections, and Downstream Capacity

When increasing `maxConcurrentConsumers`, a container may need additional JMS `Session`s, `MessageConsumer`s, and tasks. However, a single JMS `Connection` can hold multiple sessions; **do not** conclude max 5 equals five physical TCP connections.

Resources to consider:
- Broker max consumers/addresses, memory, and prefetch/credit.
- Container cache level: `CACHE_NONE`, `CACHE_CONNECTION`, `CACHE_SESSION`, `CACHE_CONSUMER`, `CACHE_AUTO`.
- `TaskExecutor` threads and queue.
- DB pool size, SQL locks, transactions, external API rate limits.
- Payload size, serialization/deserialization, and handler duration.
- Number of endpoints, replicas, and failover/recovery after outages.

With native/local JMS, the Default container can cache sessions/consumers. With an external transaction manager/JTA, default auto caching may drop so resources enlist properly. Do not change cache level arbitrarily just to reach max consumers faster.

In Spring Boot, listener containers should generally use the native `ConnectionFactory` unwrapped from template caching wrappers, allowing the container to manage recovery. Do not use `CachingConnectionFactory` directly in every listener without understanding lifecycle and scaling limits.

## 18. Transactions and Acknowledgment Are Not Determined by Concurrency

Increasing min/max does not inherently make consumers more reliable:

- With `AUTO_ACKNOWLEDGE` on `DefaultMessageListenerContainer`, acknowledgment may happen **before** the listener handler runs; processing errors may not trigger redelivery.
- With `sessionTransacted=true`, each receive/handler is wrapped in a local JMS transaction; an eligible handler exception triggers rollback/redelivery per broker policy.
- A local JMS transaction **does not automatically include a SQL database** or an HTTP payment API.
- Multiple invokers can process different messages concurrently; each JMS Session follows single-threaded context rules.

~~~java
@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {

    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setConcurrency("2-5");
    factory.setSessionTransacted(true);
    return factory;
}
~~~

This is a Spring configuration snippet requiring compatible imports and a `ConnectionFactory` bean. If the handler commits the DB and the process dies before JMS commit, the broker can redeliver. At higher concurrency, races on the same business key become more visible. Use a stable `eventId`, unique constraints/inbox in the same DB transaction, and idempotency for external side effects.

Do not spawn a raw `new Thread` inside a listener and return immediately before business work completes if you expect the JMS transaction to protect it. Returning from the listener can cause JMS commit before the background thread's business effect completes.

## 19. Multi-Replica: One Container's Max Is Not a Global Max

For example, four replicas, each with three endpoints, each endpoint min2/max6:

~~~text
Configured core invoker tasks:     4 × 3 × 2 = 24
Configured maximum:                4 × 3 × 6 = 72
~~~

These are **theoretical invoker counts**, not measurements of actual broker connections or throughput. If every worker calls the DB, each replica needs an appropriate resource budget. Raising max across all replicas simultaneously can trigger a thundering herd when the broker recovers or queue backlog spikes.

If an external API allows at most ten concurrent calls system-wide, `concurrency="1-10"` **per replica** does not create a global cap of ten. You need an appropriate limiter/distributed coordination or throttling at the target system.

### Estimating Throughput with Explicit Assumptions

If each handler averages 200ms and five consumers are genuinely busy continuously, ideal throughput is roughly:

\[
\frac{5\text{ consumers}}{0.2\text{ s/message}} = 25\text{ messages/s}
\]

The **25 msg/s figure is only a model**, omitting SQL locks, broker latency, serialization, retries, tail latency, prefetch, or CPU contention. For production sizing, measure p95/p99 processing duration, oldest message age, error rate, and DB pool saturation; do not treat one division as a benchmark.

## 20. Runtime Tuning: Change on the Right Container with Monitoring

`DefaultMessageListenerContainer`'s `setConcurrentConsumers`/`setMaxConcurrentConsumers` setters can be updated at runtime in Spring 6.2, provided you obtain the **actual container instance**:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("elasticJobs");

if (container instanceof DefaultMessageListenerContainer dmlc) {
    dmlc.setConcurrentConsumers(2);
    dmlc.setMaxConcurrentConsumers(6);
}
~~~

`registry` is the `JmsListenerEndpointRegistry` Spring bean, not a broker API. Do not mutate `DefaultJmsListenerContainerFactory` assuming all already-created containers update immediately.

Before a runtime change:
1. Verify the exact endpoint ID, queue/topic, and runtime implementation.
2. Confirm permissions/admin approval, audit logging, and a rollback mechanism.
3. Keep min/max within the resource budget of the JVM/broker/DB and total replicas.
4. Observe actual scheduled/active counts, handler latency, and queue age for several cycles.
5. Understand changes are not necessarily instantaneous; scale-down requires idle events.
6. Persist changes to durable configuration when appropriate; runtime setters can be lost on restart.

Do not expose a public HTTP endpoint letting anyone set `maxConcurrentConsumers` to thousands.

## 21. Symptom-Based Troubleshooting

| Symptom | Possible Cause | Inspection Action |
| --- | --- | --- |
| Set `"5"` yet startup shows only 1 consumer | `"5"` means min1/max5 | Check `getConcurrentConsumers()` and `getMaxConcurrentConsumers()` |
| Wanted fixed 5 yet count drops when idle | Used `"5"` instead of `"5-5"` | Fix format for fixed count |
| `"2-6"` yet active stays at 2 | Low load, broker not dispatching, executor short on threads | Broker consumer count, scheduled/active, executor queue |
| Backlog grows yet scale never reaches max | Prefetch/credit, fast/slow handler, resource saturation | Queue age, in-flight, and consumer metrics |
| YAML min4 without max yet behaves as fixed4 | Boot min-only uses min as max | Check Boot properties and factory runtime |
| Annotation wants max8 yet YAML has max5 | Annotation overrides factory for that endpoint | Inspect `@JmsListener(concurrency)` and actual container |
| Seeing 20 consumers despite max5 | Multiple endpoints/replicas on the same queue | Count per container and across cluster |
| Business completion out of order | Consumers process concurrently | Choose grouping/ordering invariant |
| Topic receives duplicate events | Multiple subscriptions instead of competing consumers | Check topic topology/shared subscription |
| Handler fails yet broker does not redeliver | `AUTO_ACK`/transaction config | Test rollback, DLQ, `sessionTransacted` |
| DB pool exhausted after raising max | Concurrency exceeds downstream capacity | Measure DB connections, locks, handler latency |
| Max8 yet throughput does not rise | CPU/DB/broker bottleneck | Profile before raising further |
| Many scheduled, few active | Executor saturation or invokers not ready | Thread dump, executor metrics, broker connection |
| Slow shutdown when max is large | Blocked invokers/handler I/O/transactions | Receive timeout, shutdown grace, logs |

Avoid changing min/max, `receiveTimeout`, prefetch, DB pool, and executor all at once; it becomes very hard to isolate what improved or degraded behavior.

## 22. Practice Exercises and Checklist

**Exercise 1 — Decode strings:** in a Default container test, set `"1"`, `"3"`, `"3-3"`, `"2-5"`. Print both min/max getters and compare against the table in section 3.

**Exercise 2 — Prove fixed:** set `"4-4"` on a test queue and observe core invokers while the queue is empty. Stop the broker to see that configured min does not guarantee broker-connected consumers at all times.

**Exercise 3 — Elastic burst:** set `"1-5"`, send enough backlog with handlers taking 300ms; measure scheduled/active over time without assuming max 5 always appears.

**Exercise 4 — Boot min-only:** use `min-concurrency: 3` without max and compare with `factory.setConcurrency("3")`. State the difference in min/max.

**Exercise 5 — Annotation override:** factory `"2-5"`, endpoint A uses default, endpoint B has `concurrency="1-8"`; read actual config of both via the registry.

**Exercise 6 — TaskExecutor:** use a bounded pool smaller than total core consumers in a test; explain why some invokers are scheduled yet not running.

**Exercise 7 — Queue ordering:** send sequenced messages and compare one consumer vs. four consumers. Measure business completion order, not just send order.

**Exercise 8 — Topic:** test a non-shared topic with three consumers, observe duplicates, and explain how it differs from competing queue consumers.

**Exercise 9 — Transacted listener:** make the handler throw an exception, observe redelivery/DLQ per policy; show that concurrency and transactions are separate concerns.

**Exercise 10 — Replicas:** run two replicas with max 4 on the same queue; inventory total broker consumers and identify why there is no global cap of 4.

**Exercise 11 — DB bottleneck:** raise max while the DB pool is small, measure waiting threads/SQL locks; find the throughput saturation point.

**Exercise 12 — Idle shrink:** create a burst then drain load, measure when extra invokers shrink back to core. Relate to `receiveTimeout`, `idleReceivesPerTaskLimit`, and `maxMessagesPerTask`.

**Exercise 13 — Graceful shutdown:** stop the app mid-processing, measure in-flight work, rollback/commit, and idempotency after restart.

**Exercise 14 — Capacity planning:** three replicas, five endpoints, each max 6 gives a configured ceiling of **90 invoker tasks**. Do not infer 90 TCP connections.

**Self-assessment checklist:**
- [ ] I remember **`"N" = min1/maxN`** and **`"N-N" = fixed N`** in the Default container.
- [ ] I distinguish configured min/max from runtime scheduled/active.
- [ ] I know how to configure Java factory, annotation, and Boot YAML, as well as precedence order.
- [ ] I do not confuse Boot min-only with the `setConcurrency("N")` string.
- [ ] I understand how queue ordering and topic subscriptions are affected when concurrency > 1.
- [ ] I accurately calculate max consumers across multiple endpoints and replicas.
- [ ] I do not equate consumers, sessions, threads, and physical connections.
- [ ] I monitor `TaskExecutor`, broker credit/prefetch, receive timeout, and idle limits.
- [ ] I do not treat concurrency as a replacement for transactions/ACK/idempotency.
- [ ] I run verified benchmarks rather than always setting max as high as possible.

**Final check question:** "Is `concurrency="5"` the same as `concurrency="5-5"`?" — **No.** In Spring JMS `DefaultMessageListenerContainer`, the former is a **maximum limit** with min 1; the latter is **five fixed consumers**. Choose explicitly based on response-time and resource requirements.

## Official References

1. [Spring Framework 6.2 — DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html): `setConcurrency(String)`, min/max, scaling, idle limits, thread executor, ordering/topic.
2. [Spring Framework 6.2 — @JmsListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListener.html): `concurrency` format `"N"` or `"MIN-MAX"`, overriding the factory per endpoint.
3. [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): `setConcurrency("3-10")` example with the Default factory.
4. [Spring Framework 6.2 — DefaultJmsListenerContainerFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html): container creation and concurrency configuration.
5. [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.jms.listener.min-concurrency`, `max-concurrency`, receive timeout.
6. [Spring Boot 3.5 — JMS Reference](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): JMS auto-configuration, Artemis, and listener transactions.
7. [Spring Boot 3.5 — Messaging How-to](https://docs.spring.io/spring-boot/3.5/how-to/messaging.html): `DefaultJmsListenerContainerFactoryConfigurer` and native `ConnectionFactory`.
8. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): `Session`, `MessageConsumer`, queue/topic, ACK, transactions, and delivery.

**Conclusion:** choose min/max based on **clear intent**, using `"N-N"` when fixed and `"MIN-MAX"` when elastic. Verify configuration using getters on the actual container, then verify effectiveness using queue age, handler latency, executor, and DB pool—not just by looking at max values.