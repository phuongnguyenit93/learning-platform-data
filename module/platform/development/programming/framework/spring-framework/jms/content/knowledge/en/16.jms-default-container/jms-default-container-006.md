# receiveTimeout and Idle Responsiveness in DefaultMessageListenerContainer (Spring JMS)

## 1. Scenario: Empty Queue, Listener Must Stay Ready

A Spring Boot service receives events from the `orders.in` queue using `@JmsListener`. During the day the queue has heavy traffic; at night it is nearly empty. Operations engineers want to save resources when there are no messages, respond quickly when new messages arrive, and shut down the application cleanly when deploying a new version.

Spring JMS provides `org.springframework.jms.listener.DefaultMessageListenerContainer` (DMLC) to manage consumers. This container actively calls `MessageConsumer.receive(...)` inside worker tasks. The `receiveTimeout` property controls **the maximum wait time of a single receive attempt when no message is available**, in milliseconds. This value directly relates to when an **empty receive** is detected, stopping or shrinking unnecessary consumers, and the responsiveness of lifecycle operations.

Avoid a false conclusion: **`receiveTimeout=1000` does not mean every new message has to wait a full second before being processed.** If the consumer is already inside a blocking receive call and the provider supports normal delivery, an arriving message can wake it immediately. One second is the wait limit of an *empty receive round*, not a forced timer interval that every message must wait through.

Lesson objectives:

- Understand **DefaultMessageListenerContainer**'s `receiveTimeout` and `0`, negative, and positive values.
- Understand what the thread/consumer does when the queue is idle versus when a message arrives.
- Distinguish message arrival latency, idle detection, scale-down, and shutdown/recovery.
- Properly read `concurrentConsumers`, `maxConcurrentConsumers`, `idleConsumerLimit`, `idleReceivesPerTaskLimit`, `idleTaskExecutionLimit`, and `maxMessagesPerTask`.
- Configure with Spring Boot or `DefaultJmsListenerContainerFactory`, test, and observe using a runnable Java 17+ example in a Spring Boot project.

## 2. DMLC Is Asynchronous at the Application Level Yet Uses Blocking Receive

Handler code looks "automatically invoked":

```java
@JmsListener(destination = "orders.in")
public void handle(String payload) {
    businessService.process(payload);
}
```

This is an **illustrative method snippet inside a Spring bean**, with `businessService` injected. The application does not call `receive` in this method. Nevertheless, underneath, the DMLC infrastructure may use `MessageConsumer.receive(timeout)` on container-managed threads:

```text
                        Spring ApplicationContext
                                  |
                              @JmsListener
                                  |
                      JmsListenerContainerFactory
                                  |
                                  v
                    DefaultMessageListenerContainer
                                  |
                +-----------------+-----------------+
                |                                   |
       consumer task #1                       consumer task #2
       (core or surplus)                      (if scaled up)
                |                                   |
           JMS Session                         JMS Session
                |                                   |
     MessageConsumer.receive(T)         MessageConsumer.receive(T)
                |                                   |
          +-----+------+                      +-----+------+
          |            |                      |            |
        Message       null                  Message       null
          |      after timeout                |      after timeout
          v            |                      v            |
    invoke handler next receive         invoke handler evaluate idle
          |            |                      |            |
       ACK/commit      +----------------------+            v
                                                may scale down surplus
```

Key points:

1. **The container polls on behalf of the application.** `@JmsListener` remains an event-driven model at the business layer; it does not mean busy-waiting in user code.
2. **The thread waiting on receive can block.** Hence `receiveTimeout` governs when the thread returns to the loop to check stop state and update bookkeeping.
3. **A receive returning `null` is normal** when the queue has no messages during the wait interval. It does not mean the broker failed or the handler processed an empty message.
4. **The handler is only invoked when an actual message** is delivered and the adapter converts it into valid arguments; there is no `@JmsListener` invocation on empty timeouts.
5. DMLC has **core consumers** kept in the background and **surplus consumers** added under load when max is configured greater than min.

Do not conflate DMLC with `SimpleMessageListenerContainer`. The Simple container relies on registering a JMS `MessageListener` with the provider, whereas DMLC implements its own receive loop and scaling/recovery mechanisms. The timeout/idle details in this lesson apply to **DefaultMessageListenerContainer**, not all JMS containers.

## 3. Exact Semantics of receiveTimeout

In Spring Framework 6.2, `AbstractPollingMessageListenerContainer` (DMLC's superclass) declares:

```java
public static final long DEFAULT_RECEIVE_TIMEOUT = 1000L;

// Configuration API:
public void setReceiveTimeout(long receiveTimeout);
```

This is an **illustrative API signature/constant**, not code to redefine. Default `receiveTimeout` is **1,000 ms = 1 second**, per receive call in the processing loop.

| Setting on DMLC | Meaning | When to Use |
| --- | --- | --- |
| `setReceiveTimeout(1000L)` | Waits at most ~1 second for one receive if no message exists | Balanced default, good starting point |
| `setReceiveTimeout(250L)` | Shorter wait round | Need faster status checks/idle detection, accepting more receive iterations |
| `setReceiveTimeout(5000L)` | Longer wait round | Want fewer empty returns and less consumer churn, when transactions/shutdown allow |
| `setReceiveTimeout(0L)` | **Wait indefinitely** when no message exists | Generally **discouraged**, as clean shutdown is hard and incompatible with many transaction manager configs |
| `setReceiveTimeout(-1L)` | **No-wait receive**; does not wait for a message | Special controlled cases; not a default optimization |

Spring Javadoc explicitly states: this value should be **smaller than the transaction timeout** of the transaction manager if a transaction manager is present. `0` (wait indefinitely) is usually unsuitable because the container cannot stop cleanly and reliably while receive keeps waiting for a message. Negative values such as `-1` map to a non-waiting receive.

### 3.1. Why 0 Often Causes Confusion

Three APIs are frequently misread:

| Location | Value `0` | Value `-1` |
| --- | --- | --- |
| `DefaultMessageListenerContainer.setReceiveTimeout` | Wait indefinitely | No-wait |
| `jakarta.jms.MessageConsumer.receive(long timeout)` | Wait indefinitely per JMS API | Do not treat `-1` as a portable direct call; use `receiveNoWait()` |
| `JmsTemplate.setReceiveTimeout` | **No-wait** per template convention | **Wait indefinitely** per template convention |

DMLC and `JmsTemplate` **do not use the same convention** for those two special values. Do not copy `JmsTemplate`'s `setReceiveTimeout(0)` into DMLC expecting a non-waiting poll.

If you do not need zero/negative semantics, use a **finite positive value** with explicit units, such as `250ms`, `1s`, or `3s` in Spring Boot configuration.

### 3.2. receiveTimeout Applies Only to a Single Receive

Suppose timeout `T = 1000ms` and the queue is empty. A worker calls receive; after roughly T without a message it gets `null`. The container updates idle state and can then start the next receive round or decide to reschedule/shrink the task.

If a message arrives at `t = 300ms` while the consumer is waiting, the provider can return the message right away without waiting the rest of `T`. If a message arrives just as the container is changing tasks/connections, there is additional scheduling/recovery overhead. Thus you cannot conclude exact receive latency is `T`, `T/2`, or `0` from the timeout value alone.

Example timeline:

```text
T = 1000 ms

t=0ms      consumer starts receive(T)
t=300ms    broker has message M1
t≈300ms    receive can return M1 immediately if consumer is ready
           -> adapter -> @JmsListener -> handler

t=500ms    worker starts next receive(T)
t=1500ms   no message -> receive returns null
           -> container records empty receive/idle
           -> starts next receive or makes lifecycle decision
```

Approximate timestamps are for explanation only. They are **not an SLA** or benchmark result for Artemis or any provider.

## 4. "Idle Responsiveness" Actually Comprises Multiple Quantities

Saying "the shorter the timeout, the more responsive the listener" is too vague. Separate at least five quantities:

| Quantity | What to Measure | Role of receiveTimeout |
| --- | --- | --- |
| **Message arrival-to-dispatch latency** | Message available on broker → handler begins | Can be much smaller than T if consumer is already waiting; also depends on provider, network, thread/executor |
| **Empty-receive detection time** | How long until container knows a receive got no message | Typically at most around T for an actively waiting receive |
| **Surplus-consumer scale-down delay** | After load ends, how long until **surplus** consumers shrink | Depends on T *and* idle limits, executor type, `maxMessagesPerTask` |
| **Stop/shutdown responsiveness** | When stop is requested, how fast the receive loop yields to lifecycle | Finite T gives periodic status-check windows; actual stop also depends on provider and in-flight handlers |
| **Recovery latency** | Broker goes down then up, how fast a consumer resumes | Depends on recovery/backoff and connectivity; **not** determined by `receiveTimeout` alone |

**Important conclusion:** lowering T from `1000ms` to `100ms` **does not prove p95 business latency drops 10x**. If a consumer stays blocked in receive and is woken immediately by the provider, stronger factors may be thread scheduling, broker dispatch, network, consumer count, processing throughput, or prefetch.

### 4.1. When the Queue Is Completely Empty

A core consumer can still exist and keep looping on receive. "Idle" does **not** mean the container has stopped or released all threads. CPU usage is usually low while threads block properly, yet connection/consumer/session resources remain held.

### 4.2. When Traffic Resumes After a Quiet Period

If a connected core consumer is already waiting, a new message can be processed promptly. If all consumers were manually stopped, the broker is offline, the executor ran out of capacity, or the lone core consumer is busy with another message, processing start time also depends on those factors.

### 4.3. When the Application Is Shutting Down

Some receive calls may be blocked. Finite T lets workers periodically return to the loop to check stop state; however, **do not treat T as a hard upper bound for total shutdown**. Handlers may run long, the database may block, JMS transactions must commit/rollback, and the provider may have its own interrupt/close behavior.

## 5. Core Consumers, Surplus Consumers, and "Idle" in DMLC

DMLC supports:

- `concurrentConsumers`: **baseline** number of consumers maintained while the container runs; default `1`.
- `maxConcurrentConsumers`: maximum consumers the container is allowed to scale up to; default `1`.
- `idleConsumerLimit`: limit on how many consumers may be idle when deciding whether to schedule a new invoker; default `1`.
- `idleReceivesPerTaskLimit`: consecutive receives returning `null` before considering a task idle; with the default/simple executor and surplus consumers, effective default is `10` in Spring 6.2.
- `idleTaskExecutionLimit`: number of times a task is marked idle before stopping a **surplus task** in dynamic scaling; default `1`.
- `maxMessagesPerTask`: maximum **receive attempts** a task processes before yielding scheduling, including `null` returns; `-1` (unlimited) by default for standard executors, or may default to `10` for executors preferring short-lived tasks.

Understand accurately **which elements get scaled down**:

```text
concurrentConsumers = 1
maxConcurrentConsumers = 4

After startup, when queue is idle:
    core: 1 invoker (maintained)
    surplus: 0

When message volume rises and conditions allow:
    core: 1
    surplus: 0..3   <- container can scale up

When load drops:
    core: 1         <- still maintained
    surplus: 3..0   <- evaluated for scale-down per idle limits
```

If `concurrentConsumers = maxConcurrentConsumers = 4`, all four are **core consumers**. Do not expect `idleReceivesPerTaskLimit=10` to shrink them down to 1 because there is no "surplus" in that setup.

### 5.1. idleReceivesPerTaskLimit Differs from maxMessagesPerTask

Suppose a task processed 200 messages and then the queue becomes empty:

- `maxMessagesPerTask=500`: the task has a limit of 500 **receive attempts**, including empty ones. It may take many more attempts before ending under this limit.
- `idleReceivesPerTaskLimit=10`: after 10 consecutive receives returning `null`, the task is marked idle per the corresponding rule and becomes eligible for reclamation if it is a surplus task.
- `idleTaskExecutionLimit=1`: when dynamic scheduling sees the task hit one idle execution at the required threshold, the surplus task can stop.

Do not assume `maxMessagesPerTask=500` always processes exactly 500 successful messages; Javadoc defines it as **receive attempts**, not just arrived messages. Also do not assume `idleTaskExecutionLimit=1` means "stop after exactly 1 second": this limit counts **idle executions**, not wall-clock time.

### 5.2. Approximate Model for Surplus Consumer Shrink Time

With the default/simple executor, let:

- `T` = receive timeout (ms).
- `N` = consecutive null receives before considering a surplus invoker idle.

Without messages, a sequence of N full waits takes **approximately `N × T`** (excluding scheduling/provider/transaction overhead). If N = 10:

| T | N | Approximate consecutive idle receives |
| ---: | ---: | ---: |
| 200 ms | 10 | ~2 seconds |
| 1,000 ms | 10 | ~10 seconds |
| 5,000 ms | 10 | ~50 seconds |

This is an **approximate parameter calculation**, **not an exact deadline for scale-down**. A single intervening message resets the idle streak. `maxMessagesPerTask`, the task executor, activity of other invokers, `idleTaskExecutionLimit`, and scheduling govern when surplus tasks are actually destroyed.

Spring 6.2 describes surplus tasks with the simple executor defaulting to `idleReceivesPerTaskLimit=10` and `T=1000ms`, resulting in scale-down after roughly 10 seconds of empty receives. **Core consumers are not removed merely by setting `idleReceivesPerTaskLimit`** in standard configurations; the Javadoc itself highlights that distinction.

### 5.3. maxMessagesPerTask and TaskExecutor Can Change the Picture

With the default executor, an invoker can be long-lived and reuse its thread continuously. With a `SchedulingTaskExecutor` preferring short-lived tasks, Spring may choose a default `maxMessagesPerTask` of `10` to allow more flexible scheduling/scaling.

This means:

- A task can yield/be re-scheduled by attempt count, **even right after processing messages**.
- Idle limits can affect core consumers via **rescheduling behavior** when combined with `maxMessagesPerTask`; do not apply a simplistic "`N × T` and then core disappears" formula.
- A fixed thread pool that is too small can queue invokers waiting on the executor, introducing latency and unexpected activity metrics.

When switching executors, do not carry over default simple-executor observations unchanged to the new setup. Measure with your exact configuration.

## 6. Parameters Not to Confuse with receiveTimeout

| Parameter | Primary Effect | Same Meaning as T? |
| --- | --- | --- |
| `receiveTimeout` | Wait round for receiving **one message** when none is available | This is T |
| `recoveryInterval` / `BackOff` | Interval/strategy for **attempting recovery** when connection/consumer fails | **No**; DMLC defaults to a 5-second recovery interval |
| `idleReceivesPerTaskLimit` | Consecutive null rounds marking a task idle | No; counts rounds |
| `idleTaskExecutionLimit` | Idle executions before a surplus task stops | No; counts executions |
| `maxMessagesPerTask` | Receive attempts per task | No; counts attempts |
| `idleConsumerLimit` | Idle consumer threshold used when deciding to spawn another invoker | No; counts consumers |
| `concurrentConsumers / maxConcurrentConsumers` | Min/max concurrent consumers | No; concurrency bounds |
| `sessionTransacted` | JMS local transaction during receive/processing | No; affects commit/redelivery |
| `transactionTimeout` | Transaction limit managed by a transaction manager | No; must exceed `receiveTimeout` when a transaction manager is used |
| `JmsTemplate.receiveTimeout` | Timeout of **synchronous receive calls from application code** | Different API, different 0/-1 conventions |
| Producer `timeToLive` | Message lifetime before expiration | No |
| JMS message `deliveryDelay` | Delays when a message becomes eligible for delivery | No |

In particular, **broker loss** is not "an empty queue". If the broker is down, DMLC enters the error and recovery branch. Lowering `receiveTimeout` does not alter the default 5,000 ms `recoveryInterval`; to control connection retries, use the appropriate recovery/backoff API.

## 7. Choosing T by Goal, Not Intuition

### 7.1. When the Queue Rarely Has Messages

For a mostly empty queue:

- Keep `T=1000ms` as a safe starting point.
- Keep minimum core consumers (typically 1); do not try to shrink to 0 just because messages are absent.
- Monitor empty receive counts, connections, threads, and broker metrics.
- If you want surplus consumers to withdraw sooner, consider idle limits and a moderate T, rather than dropping T to a few milliseconds.
- If T is set too small, empty receive loops run more frequently, increasing transaction/receive setup or broker/network overhead depending on the provider.

### 7.2. When Near-Realtime Is Required

If the SLA from message arrival at the broker to handler start is 100–300 ms, setting `T=100ms` **does not satisfy that SLA by itself**. Measure:

- Producer → broker latency and broker dispatch.
- Whether a core consumer thread is available to receive.
- Broker prefetch/buffers, selectors, queue backlog, priority, and network.
- Executor wait time when the container wants to schedule a consumer task.
- Whether prior message processing occupies all consumers.
- CPU, GC, downstream systems, and transaction overhead.

If a core consumer is blocked in `receive(1000)`, an arriving message can wake it immediately; changing T is not a clear p99 optimization.

### 7.3. When Fast Shutdown Is Needed

Keep the timeout **finite**, allocate reasonable shutdown time, and design for in-flight work. `T=5000ms` may make the receive loop return later than `T=500ms` under some conditions, yet total shutdown also depends on provider interrupts, long-running handlers, transactions, thread count, and the lifecycle processor.

Do not set `T=0` to "sleep to save CPU" if the system must stop within a Kubernetes termination window. Spring Javadoc warns that 0 (indefinite wait) often impedes clean shutdown.

### 7.4. When You Want Scale-Down Without Oscillation

Surplus consumers repeatedly scaling up and down under short bursty workloads can cause connection/session/consumer churn and add latency when the next burst arrives. Raising `idleReceivesPerTaskLimit` or a reasonable T keeps surplus consumers alive longer, at the trade-off of holding resources longer while idle.

If consumers need to scale up quickly under load, `idleConsumerLimit` can influence how proactively additional invokers are scheduled. Do not raise it without bounds, as extra consumers can overload the database and break per-aggregate ordering requirements.

## 8. Spring Boot Configuration: Distinguishing Listener Receive Timeout from Template Receive Timeout

Spring Boot 3.4 has properties for the **default JMS listener container factory**:

```yaml
spring:
  jms:
    listener:
      receive-timeout: 1s
      min-concurrency: 1
      max-concurrency: 4
```

`spring.jms.listener.receive-timeout` configures the listener container; `spring.jms.template.receive-timeout` configures `JmsTemplate`. Do not swap their names and meanings.

In Boot 3.4:

- `spring.jms.listener.receive-timeout` defaults to `1s`.
- `0` indicates **wait indefinitely** for the listener; `-1` indicates no-wait.
- `min-concurrency` and `max-concurrency` define the concurrency range when using Boot's auto-configured factory.
- `max-messages-per-task` is a separate property; it does **not** automatically set `idleReceivesPerTaskLimit`.
- `receive-timeout` uses `Duration`, so write `250ms`, `1s`, `5s` for maintainability.

**Note:** if the application defines a **custom `DefaultJmsListenerContainerFactory`** without using Spring Boot's `DefaultJmsListenerContainerFactoryConfigurer`, `spring.jms.listener.*` properties will not automatically apply to that custom factory. Call setters explicitly or let the Boot configurer initialize the factory first before overriding.

## 9. Complete Spring Boot 3.4/Java 17 Example: Observing Consumers When Idle

We build a learning project using ActiveMQ Artemis with two profiles:

- `listener`: enables `@JmsListener` and monitors consumer counts.
- `publish`: sends N test messages via `JmsTemplate`, without creating a listener in this process.

Requires a running Artemis broker with queue `orders.in` and valid credentials, plus permission to create or look up the destination per policy. This is a **complete main-file Spring Boot project**, requiring Gradle/JDK/dependencies and a real broker; it is not a plain Java program runnable solely with `javac`.

### 9.1. Project Structure

```text
jms-idle-demo/
  settings.gradle
  build.gradle
  src/main/resources/application.yml
  src/main/java/demo/idle/IdleDemoApplication.java
  src/main/java/demo/idle/OrdersListener.java
  src/main/java/demo/idle/PublishRunner.java
  src/main/java/demo/idle/ConsumerMonitor.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'jms-idle-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot 3.4.13 is a real release used to keep the example reproducible, though **the 3.4.x branch has reached end of open-source support**. For new production projects, choose a supported Spring Boot branch and verify corresponding API/behavior changes. Java 17+ is the minimum requirement for the example.

### 9.2. application.yml: Configuring from Defaults

File `src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: "${JMS_BROKER_URL:tcp://localhost:61616}"
    user: "${JMS_USER}"
    password: "${JMS_PASSWORD}"
  jms:
    listener:
      receive-timeout: "${JMS_RECEIVE_TIMEOUT:1s}"
      min-concurrency: 1
      max-concurrency: 4

app:
  jms:
    queue: "${JMS_ORDERS_QUEUE:orders.in}"
    demo-count: "${JMS_DEMO_COUNT:12}"
```

Explanation:

1. `mode: native` requires connecting to an external Artemis broker. The broker must be provisioned separately and have queue `orders.in` (or allow auto-create per policy).
2. `JMS_USER`/`JMS_PASSWORD` must be supplied via environment/secrets; do not commit real passwords.
3. You can try `JMS_RECEIVE_TIMEOUT=200ms`, `1s`, and `5s` **one configuration per run** to compare idle consumer counts and scale-down time.
4. `min-concurrency: 1` maintains one core consumer; `max-concurrency: 4` allows up to three surplus consumers when load is sufficient. Not every small burst is guaranteed to spawn four consumers.
5. `demo-count` limits how many messages the publish profile generates per startup.
6. Only the default Boot factory is configured via `spring.jms.listener.*` in this demo; **do not define a custom factory** in the main run.

### 9.3. Application Enabling Annotation Listener and Scheduled Monitor

File `src/main/java/demo/idle/IdleDemoApplication.java`:

```java
package demo.idle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableJms
@EnableScheduling
public class IdleDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(IdleDemoApplication.class, args);
    }
}
```

`@EnableJms` activates listener annotation infrastructure, while `@EnableScheduling` only lets the monitor component observe counts periodically. The monitor **does not** alter JMS receive wait times and does not send messages itself.

### 9.4. Message-Processing Listener

File `src/main/java/demo/idle/OrdersListener.java`:

```java
package demo.idle;

import org.springframework.context.annotation.Profile;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
@Profile("listener")
public class OrdersListener {

    @JmsListener(id = "ordersListener", destination = "${app.jms.queue}")
    public void onOrder(String body) {
        if (body == null || !body.startsWith("OrderCreated:")) {
            throw new IllegalArgumentException("Unexpected event body");
        }
        System.out.println("HANDLED " + body);
    }
}
```

The payload is converted from `TextMessage` to `String` by the default converter. The handler only validates and prints to console, so it cannot be used as production business logic. With concurrent consumers, the method on a singleton bean can be invoked from multiple threads; do not store unsynchronized mutable state in fields.

### 9.5. Separate Producer Sending a Small Batch

File `src/main/java/demo/idle/PublishRunner.java`:

```java
package demo.idle;

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
    private final String destination;
    private final int count;

    public PublishRunner(
            JmsTemplate template,
            @Value("${app.jms.queue}") String destination,
            @Value("${app.jms.demo-count:12}") int count) {
        this.template = template;
        this.destination = destination;
        this.count = count;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (count < 1 || count > 1000) {
            throw new IllegalArgumentException(
                    "demo-count must be between 1 and 1000");
        }
        for (int i = 1; i <= count; i++) {
            template.convertAndSend(
                    destination, "OrderCreated:ORDER-" + i);
        }
        System.out.println("PUBLISHED " + count);
    }
}
```

The producer runs under the `publish` profile and does not activate the listener bean (because the listener belongs only to the `listener` profile). The producer printing `PUBLISHED 12` proves the template's send loop completed without error; it does **not** prove the listener received them or business work committed.

### 9.6. Monitoring Consumer State

File `src/main/java/demo/idle/ConsumerMonitor.java`:

```java
package demo.idle;

import org.springframework.context.annotation.Profile;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@Profile("listener")
public class ConsumerMonitor {

    private final JmsListenerEndpointRegistry registry;

    public ConsumerMonitor(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    @Scheduled(fixedDelay = 5_000L)
    public void report() {
        MessageListenerContainer listener =
                registry.getListenerContainer("ordersListener");

        if (listener == null) {
            System.out.println("MONITOR endpoint not registered");
            return;
        }
        if (!(listener instanceof DefaultMessageListenerContainer dmlc)) {
            System.out.println("MONITOR different container type");
            return;
        }

        System.out.printf(
                "MONITOR running=%s scheduled=%d active=%d%n",
                dmlc.isRunning(),
                dmlc.getScheduledConsumerCount(),
                dmlc.getActiveConsumerCount());
    }
}
```

These getters are snapshots of the **current container**:

- `getScheduledConsumerCount()`: number of scheduled invoker/consumer tasks per container definition; not the number of threads executing business methods.
- `getActiveConsumerCount()`: number of invokers in active state per DMLC internals; should **not** be interpreted as JMS messages processed in the current second.
- `isRunning()`: container lifecycle state; does not prove the broker connection is healthy or the queue is empty.

When the queue stays empty for a while, `scheduled` typically returns to core count (e.g., 1) without load; `active` may be low. When a burst arrives, surplus count may rise and then fall. **Do not hardcode stdout** because timing, broker provider, and actual message volume change the numbers.

### 9.7. How to Run the Demo

Requirements: JDK 17+, compatible Gradle, a separate Artemis broker, and queue `orders.in`. After creating the project, run with installed Gradle; if using a Gradle wrapper, replace `gradle` with `./gradlew` (Windows: `gradlew.bat`).

First terminal runs **listener**:

```bash
gradle bootRun --args='--spring.profiles.active=listener'
```

Leave the queue empty for a moment and observe `MONITOR` lines spaced ~5 seconds apart. That is the **metrics** polling cadence, not `receiveTimeout`. Then from a second terminal, in the **same project** and pointing to the same broker/queue:

```bash
gradle bootRun --args='--spring.profiles.active=publish'
```

The producer attempts to send N messages and prints, for example:

```text
PUBLISHED 12
```

The listener may print lines such as:

```text
HANDLED OrderCreated:ORDER-1
HANDLED OrderCreated:ORDER-2
```

Those are just **two illustrative lines out of N messages**; Spring Boot/Artemis logs, message ordering, and consumer counts depend on runtime conditions. Do not treat `ORDER-i` order as a business FIFO guarantee when running multiple consumers. If the broker is down or the queue is missing, the program may fail/recover instead of printing the expected lines.

After the queue drains, wait and watch `scheduled` return near min concurrency. With a small 12-message burst and a very fast handler, the container **might not scale up to 4**, which does not mean configuration failed. To investigate real scale-down, create a test workload with controlled slow processing or send more messages, tracking multiple snapshots and broker metrics.

### 9.8. Experimenting with Receive Timeout

Without modifying Java, test configurations by restarting the listener after each change:

```bash
# With Bash/Linux/macOS shell:
JMS_RECEIVE_TIMEOUT=200ms gradle bootRun --args='--spring.profiles.active=listener'

JMS_RECEIVE_TIMEOUT=1s gradle bootRun --args='--spring.profiles.active=listener'

JMS_RECEIVE_TIMEOUT=5s gradle bootRun --args='--spring.profiles.active=listener'
```

Do not run all three listeners simultaneously on one queue when benchmarking each setting, as they become competing consumers. On Windows/PowerShell, set `$env:JMS_RECEIVE_TIMEOUT="200ms"` before running `gradlew.bat`.

Record 4 groups of observations:

1. Latency from message available on broker → handler start (measured with proper clocks/tracing).
2. Timestamps when `scheduled/active` rise and fall as a burst arrives and drains.
3. Resource cost while the queue is empty (CPU, threads, connections).
4. Time for the application to stop receiving and complete shutdown, including in-flight business work.

**Conclude only after measuring:** a shorter T can speed up idle detection or releasing surplus invokers, but does not automatically make message dispatch faster.

## 10. If You Need to Tune idleReceivesPerTaskLimit: Advanced Configuration

`DefaultJmsListenerContainerFactory` directly exposes `setReceiveTimeout(Long)` and `setMaxMessagesPerTask(Integer)`, yet **does not** expose a public `setIdleReceivesPerTaskLimit(...)` setter on the factory itself in Spring 6.2. That setter lives on **`DefaultMessageListenerContainer`**. You can use a container bean directly or subclass the factory to customize the container upon creation.

Example of **a custom replacement factory** for the default factory:

File `IdleAwareFactory.java` (place in package `demo.idle` if extending the project):

```java
package demo.idle;

import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

public class IdleAwareFactory
        extends DefaultJmsListenerContainerFactory {

    @Override
    protected void initializeContainer(
            DefaultMessageListenerContainer container) {
        super.initializeContainer(container);
        container.setIdleReceivesPerTaskLimit(5);
        container.setIdleTaskExecutionLimit(1);
    }
}
```

File `IdleAwareConfiguration.java`:

```java
package demo.idle;

import jakarta.jms.ConnectionFactory;
import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.boot.jms.ConnectionFactoryUnwrapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class IdleAwareConfiguration {

    @Bean("idleAwareJmsFactory")
    public IdleAwareFactory idleAwareJmsFactory(
            DefaultJmsListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        IdleAwareFactory factory = new IdleAwareFactory();
        configurer.configure(
                factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));
        factory.setReceiveTimeout(1000L);
        factory.setConcurrency("1-4");
        return factory;
    }
}
```

To **actually use this factory**, update the annotation in `OrdersListener` to:

```java
@JmsListener(
        id = "ordersListener",
        destination = "${app.jms.queue}",
        containerFactory = "idleAwareJmsFactory")
public void onOrder(String body) {
    // Keep the same handler body as in the main example.
}
```

The last snippet **illustrates changing the annotation**; do not create a second `onOrder` method in the same bean. In real deployment, keep one existing method and only add `containerFactory`.

Notes:

- Use Boot's `DefaultJmsListenerContainerFactoryConfigurer` to preserve appropriate listener factory defaults (transactions, unwrapped connection factory, converters...) before customizing.
- `setIdleReceivesPerTaskLimit(5)` marks surplus consumers idle earlier in some scenarios; it **does not cut core consumers**.
- `setIdleTaskExecutionLimit(1)` is a threshold by **idle task executions**, not 1 second.
- With non-default `maxMessagesPerTask` and executors, the effect differs; measure instead of just multiplying numbers.
- Do not configure both the new factory and old factory concurrently on the same queue across different endpoints expecting every message to be duplicated.
- When changing container properties at runtime, verify support for each setter and change-management controls; the easiest approach to control in demos is configuring at container creation and restarting deliberately, not mutating silently under production load.

## 11. Standalone Java 17: *Approximating* the Empty Receive Window

To understand `N × T` without a broker, create `IdleReceiveEstimate.java`:

```java
public class IdleReceiveEstimate {

    static long estimateMillis(long receiveTimeoutMs, int emptyReceives) {
        if (receiveTimeoutMs <= 0 || emptyReceives <= 0) {
            throw new IllegalArgumentException(
                    "Use positive timeout and emptyReceives");
        }
        return Math.multiplyExact(receiveTimeoutMs, emptyReceives);
    }

    public static void main(String[] args) {
        int count = 10;
        long[] timeouts = {200, 1_000, 5_000};

        for (long timeout : timeouts) {
            long estimated = estimateMillis(timeout, count);
            System.out.printf(
                    "T=%dms N=%d approximate=%dms%n",
                    timeout, count, estimated);
        }
    }
}
```

Run with Java 17+:

```bash
javac IdleReceiveEstimate.java
java IdleReceiveEstimate
```

**Exact stdout**:

```text
T=200ms N=10 approximate=2000ms
T=1000ms N=10 approximate=10000ms
T=5000ms N=10 approximate=50000ms
```

This is a **standalone arithmetic calculation** of N consecutive timeouts, not a simulation of a real JMS container. It excludes thread scheduling, intervening messages, `maxMessagesPerTask`, rollbacks, scaling policies, or broker responses. Do not use its output as a scale-down or shutdown SLA.

## 12. Transactions, ACK, and Errors: An Empty Receive Is Not a Failed Processing

DMLC can run listeners with a local JMS transaction or an external transaction manager. If a listener receives a real message and then throws an exception, the outcome depends on ACK/transaction configuration and broker policy.

However, **a receive returning `null`** is a different matter:

- No business handler is invoked simply because of an empty receive.
- The container still manages the session and may need to complete the transaction scope of that receive attempt if transactions are configured.
- Do not record an empty receive as a business error or redelivery.
- With a transaction manager, `receiveTimeout` should be **shorter than the transaction timeout** so the wait loop does not exceed the transaction window.
- Expired messages, selector mismatches, or messages not yet dispatched by the broker can also yield empty receives from the consumer's perspective; that does not prove the whole broker has no data.

### 12.1. receiveTimeout Is Not a Business Processing Timeout

If `receiveTimeout=1000ms` yet a handler runs for 30 seconds, Spring **does not** automatically terminate the handler after 1 second. Timeout applies only when calling `receive` to wait for a message.

Design **database/HTTP timeouts**, circuit breakers, or cancellation policies for the handler separately. Business processing time also affects when the consumer returns to the receive loop, thereby affecting the next message's latency if no idle consumer is available.

### 12.2. receiveTimeout Is Not Message Expiration

Producers can set `timeToLive` or delivery delay, and the broker can hold messages based on selectors/priority. Those mechanisms decide whether a message is eligible for delivery. Consumer receive timeout **does not alter TTL** or delete messages from the queue while waiting for expiration.

### 12.3. receiveTimeout Is Not the Recovery Interval

DMLC has `setRecoveryInterval(long)` or `setBackOff(BackOff)`. The default 5,000ms recovery interval in Spring 6.2 is the retry interval when **the broker/consumer encounters an error**. It is not the wait time of a single receive on an empty queue.

```text
Empty queue:
  receive(timeout) -> null -> idle bookkeeping -> next receive

Broker disconnected:
  receive or connection encounters error
       -> DMLC failure/recovery path
       -> wait per recoveryInterval / BackOff policy
       -> attempt to recreate/recover resources and resume receiving
```

If the broker is down for 15 seconds, lowering `receiveTimeout` from 1 second to 100ms does not guarantee the application reconnects in 100ms; observe the actual recovery policy, broker, and network.

## 13. Shutdown and Responsiveness: Do Not Treat Timeout as an Absolute Guarantee

During shutdown, DMLC needs to stop scheduling consumer tasks, handle in-flight work (per policy), and release connections/sessions. Threads blocked in receive may be released upon receiving a message, timing out, stop/close, or provider error. Therefore:

- `T=0` (infinite wait) is a risky choice; Spring Javadoc warns that the container struggles to shut down cleanly when receive never returns.
- `T>0` is a safer configuration so tasks have opportunities to return to the loop.
- Even with `T=200ms`, a listener running 20 seconds of business logic can still make shutdown take a long time.
- The broker/provider may block during session, transaction, or connection close; receive timeout does not bound all those steps.
- Stopping one container only affects consumers belonging to that container, not other JVMs on the same queue.

Example Spring Boot configuration so the lifecycle processor waits an appropriate interval per shutdown phase:

```yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
```

This property **does not** set receive timeout; it controls the wait budget for the Spring lifecycle processor's **shutdown phase**. If handlers run longer than the budget, define an explicit policy for stopping and redelivery rather than assuming shutdown always succeeds cleanly.

## 14. Operational Observability and Benchmark Design

### 14.1. Metrics to Measure

| Suggested Metric | Meaning | Why It Is Needed |
| --- | --- | --- |
| `listener_running` | Container lifecycle state | Know whether the listener is enabled |
| `scheduled_consumers` | DMLC `getScheduledConsumerCount()` | Observe task count changes |
| `active_consumers` | DMLC `getActiveConsumerCount()` | Observe activity per container definition |
| `queue_depth` | Pending messages on broker | Know backlog |
| `oldest_message_age` | Age of oldest message | Know if the queue is stalled |
| `message_delivery_latency` | Time from broker message available → handler start | Measure receive responsiveness |
| `handler_latency` | Business processing duration | Measure bottlenecks outside receive |
| `redelivery_total` | Re-delivery attempts after errors | Measure transaction/retry impact |
| `recoveries_total` | Connection recovery attempts | Distinguish broker failure from queue idle |
| `shutdown_duration` | Time to stop/drain resources | Verify timeout effectiveness |

Metric names are **application suggestions**, not all built into Boot Actuator out of the box. You can use Micrometer/Observation alongside broker metrics and tracing. Snapshots of `scheduled/active` from the demo are supporting data, not a replacement for broker consumer counts and in-flight queue metrics.

### 14.2. How to Measure Latency Correctly

Record a timestamp near when the **broker confirms message availability** and a timestamp when the **handler begins**, or use tracing/benchmarks in an environment with synchronized clocks. If producer and consumer are on separate machines, clock skew can produce negative or badly skewed latencies; synchronize clocks and understand measurement points.

Do not measure "how long until the monitor sees active consumers increase" and call that message latency: a monitor running every 5 seconds has **sampling lag** completely unrelated to `receiveTimeout`. Do not infer p99 from a handful of sends into an empty queue.

### 14.3. Practical Benchmark Scenarios

1. **Long empty queue:** keep the listener profile running; measure CPU/threads/connections and scheduled consumer count across different T values.
2. **Single message after silence:** send a message while a core consumer is waiting; measure arrival-to-handler latency. Verify it can often be smaller than T.
3. **Burst large enough to trigger scale-up:** send many messages with controlled slow handlers; see how high scheduled count climbs.
4. **Post-burst drain:** observe surplus shrinking back to core count; compare T and idle limits.
5. **Broker down/up:** verify recovery interval/backoff without confusing it with empty-receive timeout.
6. **Graceful shutdown while queue is empty:** measure stop time with short/long T.
7. **Shutdown while handler is running:** verify in-flight/transaction/redelivery, not just the stop flag.
8. **Change executor/`maxMessagesPerTask`:** verify whether the old scale-down model still holds.
9. **Multiple replicas:** inspect total consumers and throughput; a container with min=1 does not mean the cluster has only one consumer.

Run multiple trials, separate warm-up from measurement, and hold broker, payload, queue type, concurrency, and resource budget constant. If you change T, max concurrency, and handler latency all at once, it is very hard to attribute differences to `receiveTimeout`.

## 15. Common Misconceptions

| Misconception | Why It Is Wrong | Correct Understanding |
| --- | --- | --- |
| `receiveTimeout=1000` makes every message wait at least 1 second | Blocking receive can return as soon as a message arrives | T is the maximum wait time of a receive without messages |
| Lowering T 10x makes business SLA 10x faster | Business latency has many sources | Measure broker dispatch, threads, backlog, and handler |
| `T=0` means "do not wait" like `JmsTemplate` | DMLC and template use different conventions | In DMLC, 0 is indefinite, -1 is no-wait |
| `T=-1` always saves resources | No-wait can cause many receive iterations | Use only with good reason and benchmarks |
| Empty queue means listener container is not running | Core consumer usually keeps running in the background | Check registry, scheduled consumers, and broker |
| `idleReceivesPerTaskLimit=10` shrinks all consumers to 0 | Core consumers are retained | Only surplus consumers are scaled down by default |
| `idleTaskExecutionLimit=1` means stop after 1 second | It counts idle executions | Evaluate together with T, `maxMessagesPerTask`, and executor |
| `maxMessagesPerTask=10` means "10 messages processed" | It caps receive attempts, including null | Read the Javadoc carefully |
| `recoveryInterval=5s` means poll an empty queue every 5 seconds | Recovery is the broker error branch | Do not confuse recovery with receive timeout |
| `spring.jms.template.receive-timeout` controls `@JmsListener` | Template config differs from listener factory | Use `spring.jms.listener.receive-timeout` |
| Small T guarantees shutdown within T | Handlers/provider/transactions may wait longer | Test stop/drain and configure shutdown phase |
| `scheduledConsumerCount` equals running business methods | That getter measures invoker scheduling | Combine broker metrics and handler timers |
| More consumers is always better | Can overload DB and break processing order | Tune concurrency and transactions/idempotency |
| Tuning T fixes converter/poison-message errors | Errors happen after receive | Design redelivery/DLQ and converters/validation |

## 16. Production Checklist

When tuning DMLC, follow this order:

1. **Confirm implementation:** does the app use `DefaultMessageListenerContainer` or another container? Where is property T set?
2. **Confirm effective config:** Boot default factory, custom factory, or XML/container bean? Is a configurer used?
3. **Keep T positive and finite:** start with `1s` unless measurements justify changing it.
4. **Verify transactions:** with an external transaction manager, T must be smaller than the transaction timeout.
5. **Check min/max concurrency:** if max = min, do not expect surplus scale-down; if max > min, inspect idle limits.
6. **Read executor properly:** standard/simple or scheduling short-lived? Is `maxMessagesPerTask` overridden?
7. **Measure idle and burst separately:** empty-receive detection/scale-down differs from arrival-to-handler latency.
8. **Distinguish connection failures:** recovery interval/backoff is not receive timeout.
9. **Test graceful stop:** both empty queue and active handler; do not infer shutdown time from T alone.
10. **Set resource bounds:** consumer threads, sessions, connections, downstream DB, and delivery ordering.
11. **Operate with observability:** queue age, active/scheduled consumers, redelivery, DLQ, CPU, and p95/p99 metrics.
12. **Ensure idempotency:** JMS transactions/ack and business database commits are not automatically exactly-once.

**Remember:** DefaultMessageListenerContainer's `receiveTimeout` **governs how long one receive waits when no message is available**, defaulting to **1 second** in Spring Framework 6.2. It gives the receive loop points to check idle state and lifecycle; it is **not a timer delaying every message**. Idle responsiveness depends simultaneously on core/surplus consumers, idle thresholds, the executor, broker readiness, transactions, and downstream capacity. Proper tuning must rely on **benchmarks covering empty → loaded → drained scenarios**, not a lone T number.

### References

- Spring Framework 6.2 — `AbstractPollingMessageListenerContainer`: 1,000 ms default, 0/-1 semantics, and transaction timeout: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/AbstractPollingMessageListenerContainer.html
- Spring Framework 6.2 — `DefaultMessageListenerContainer`: min/max concurrent consumers, idle limits, `maxMessagesPerTask`, recovery, and scheduled/active counts: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
- Spring Framework 6.2 — `DefaultJmsListenerContainerFactory`: `setReceiveTimeout` and container configuration for `@JmsListener`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html
- Spring Framework 6.2 — Annotation-driven listener endpoints: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Boot 3.4 — Common Application Properties, `spring.jms.listener.receive-timeout` and `spring.jms.template.receive-timeout`: https://docs.spring.io/spring-boot/3.4/appendix/application-properties/index.html
- Spring Boot 3.4 — JMS + Artemis, factory configurer, and connection factory unwrapping: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
- Spring Boot 3.4.13 — release announcement and end of OSS support for 3.4.x: https://spring.io/blog/2025/12/18/spring-boot-3-4-13-available-now
