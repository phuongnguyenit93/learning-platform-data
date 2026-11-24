# receiveTimeout in Spring JMS: Finite Wait, No Wait, and Indefinite Wait

## 1. Learning objectives

In **Spring Framework JMS**, `JmsTemplate.receive(...)` and `JmsTemplate.receiveAndConvert(...)` perform **synchronous message receiving**: the calling thread directly participates in waiting for a message from a JMS destination. If the Queue does not yet have a matching message, the program must decide **how long to wait**.

The **`receiveTimeout`** property of `JmsTemplate` controls three behaviors:

1. **Finite wait:** wait up to a positive duration, such as 2,000 ms; if no message arrives, return `null`.
2. **No wait:** check for an already available message at the moment of receiving; if none is ready, return `null` without waiting for future messages.
3. **Indefinite wait:** the thread can block until a message arrives, the consumer is closed, or an error occurs.

This mechanism is especially important when building synchronous jobs, Queue inspection operations, request/reply APIs, administrative tools, or message-pulling workers. This is the **timeout of the receive operation**, not an HTTP timeout, broker connection timeout, JMS message time-to-live, or `@JmsListener` polling frequency.

```text
             JmsTemplate.receive("orders.in")
                            |
                  Message available now?
                      /          \
                    Yes           No
                    |             |
                 return        receiveTimeout
                 Message         /   |   \
                              > 0   < 0   = 0
                               |     |     |
                            wait up  no     wait
                            to N ms  wait   forever
                               |     |     |
                         message/  message/ message/
                           null     null    err/close
```

**A `null` result does not prove that the destination is permanently empty**; it only indicates that the current receive attempt did not retrieve a message under the configured wait mode and conditions at that moment.

## 2. Standard value table: easy to confuse, essential to remember accurately

In **Spring Framework 6 / Spring JMS**, `JmsTemplate.setReceiveTimeout(long)` is interpreted as follows:

| Value | Mode | Underlying JMS call | Behavior when no message is available |
| --- | --- | --- | --- |
| `receiveTimeout > 0`, e.g. `2_000L` | **Finite wait** | `MessageConsumer.receive(2000)` | May wait up to roughly 2 seconds to receive a message; returns `null` on expiry. |
| `receiveTimeout = 0L` | **Indefinite wait** | `MessageConsumer.receive()` or equivalent semantics | Waits until a message appears, the consumer closes, or an error occurs. |
| `receiveTimeout < 0L`, typically `-1L` | **No wait** | `MessageConsumer.receiveNoWait()` | Returns an immediately available message or `null`, without waiting for future messages. |

Two constants are defined by Spring in `org.springframework.jms.support.destination.JmsDestinationAccessor`:

```java
JmsDestinationAccessor.RECEIVE_TIMEOUT_NO_WAIT
// value -1L

JmsDestinationAccessor.RECEIVE_TIMEOUT_INDEFINITE_WAIT
// value 0L
```

On `JmsTemplate`, `setReceiveTimeout` can be called directly:

```java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.JmsDestinationAccessor;

JmsTemplate template = new JmsTemplate(connectionFactory);

// Wait finitely for 2 seconds.
template.setReceiveTimeout(2_000L);

// To avoid waiting, replace the line above with:
template.setReceiveTimeout(
        JmsDestinationAccessor.RECEIVE_TIMEOUT_NO_WAIT);

// To wait indefinitely, replace with:
template.setReceiveTimeout(
        JmsDestinationAccessor.RECEIVE_TIMEOUT_INDEFINITE_WAIT);
```

These are **mutually exclusive configuration choices**, not three statements to run sequentially on the same bean in production. The `connectionFactory` variable here is an already-configured `jakarta.jms.ConnectionFactory`; this snippet is not a standalone runnable class.

**`JmsTemplate` defaults to indefinite wait, i.e., `0L`.** Therefore, calling `receive("orders.in")` on an empty Queue can block the thread indefinitely if no timeout is configured.

### Warning about 0 in the underlying JMS API

Jakarta Messaging defines `MessageConsumer.receive(long timeout)` such that **`receive(0)` also means indefinite wait**. For immediate polling, call `receiveNoWait()`.

Thus, it is **incorrect** to assume `setReceiveTimeout(0)` means "no wait." In Spring JMS, a **negative** value must be used, preferably the `RECEIVE_TIMEOUT_NO_WAIT` constant.

## 3. How does synchronous receiving work in JmsTemplate?

A call such as:

```java
Message message = jmsTemplate.receive("orders.in");
```

typically proceeds through these steps:

1. `JmsTemplate` uses `ConnectionFactory` to obtain a JMS connection/session according to its configuration and transaction context.
2. Spring resolves `"orders.in"` to an appropriate `Destination` (defaulting to the Queue domain when `pubSubDomain=false`).
3. Spring creates a `MessageConsumer` for the destination (and selector, if any).
4. Spring invokes the receive method corresponding to `receiveTimeout`.
5. If a message is available, it returns `jakarta.jms.Message`. If no message arrives within the limit or during the probe, it typically returns `null`.
6. Spring releases the consumer and manages session/connection/ack/commit according to the template's contract.

`receiveTimeout` primarily governs the **consumer's message-waiting phase**, not a guarantee that the entire Java call (including destination lookup, connection creation, DNS, TLS, broker authentication, and cleanup) will complete strictly within the configured milliseconds.

For example, if you set a 500 ms timeout while the broker takes several seconds to connect or the system is resource-starved, **total execution time can exceed 500 ms**. If the application has a strict HTTP SLA, add connection-layer timeouts and an overall request deadline accordingly.

### Message, null, and exception

```java
jakarta.jms.Message msg = jmsTemplate.receive("orders.in");

if (msg == null) {
    System.out.println("No message in this receive attempt");
} else {
    System.out.println("Received a JMS Message");
}
```

- Message available: returns an object such as `TextMessage`, `BytesMessage`, `MapMessage`, etc.
- Timed out or no message found on probe: returns `null`.
- Unreachable broker, invalid permissions, provider error, or unsupported message format: may throw `org.springframework.jms.JmsException` or a related exception. **Do not** collapse every exception into "Queue is empty."

With `receiveAndConvert(...)`, Spring uses a `MessageConverter` to convert the message into a payload. For example, a `TextMessage` is typically converted to a `String` by the default converter. If no message is received, the return value is also `null`; with custom converters, interpreting `null` also depends on the conversion contract.

## 4. Mode 1: finite wait (`receiveTimeout > 0`)

Finite wait should be considered for most synchronous tasks so that threads do not wait indefinitely for a Queue that currently has no data.

```java
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setReceiveTimeout(1_500L); // 1.5 seconds

Object payload = template.receiveAndConvert("orders.in");

if (payload == null) {
    System.out.println("Wait expired or no message yet");
} else {
    System.out.println("Received: " + payload);
}
```

**This is a snippet inside a method with a valid `connectionFactory`.** If a message appears after 100 ms, the method can return early; if the Queue stays empty during the wait window, it typically returns `null` after roughly 1.5 seconds. Measured elapsed time is only approximate due to broker behavior, OS scheduling, networking, and overhead.

### What happens if a message arrives right at the timeout boundary?

A message arriving right on the time boundary may be received in the current attempt or only become available on the next attempt, depending on scheduling and the JMS provider. Never write business logic assuming "waiting 1,000 ms guarantees every message sent before the 1,000 ms mark has been received."

### How to choose a wait duration?

| Scenario | Suggested choice | Rationale |
| --- | --- | --- |
| HTTP endpoint with only a few seconds of budget | A positive duration smaller than the total request budget | Avoids holding threads too long; still need to budget for connection/conversion time. |
| Periodic result-checking job | 200 ms – a few seconds depending on actual load | Limits tight looping while still allowing clean shutdown. |
| CLI or admin app awaiting a reply | Finite wait and display "no result" upon expiry | Prevents the UI/terminal from hanging forever. |
| Message-pulling batch worker | Positive timeout + stop-signal check | Provides a safe opportunity to exit the loop. |

These numbers are design examples, **not mandatory rules from Spring or the broker**. The choice must be based on processing requirements, latency, and observed measurements.

## 5. Mode 2: no wait (`receiveTimeout < 0`)

This mode corresponds to `MessageConsumer.receiveNoWait()`: it checks for a message **already ready for the consumer at the moment of receiving**, without waiting for new messages to arrive.

```java
import org.springframework.jms.support.destination.JmsDestinationAccessor;

JmsTemplate polling = new JmsTemplate(connectionFactory);
polling.setReceiveTimeout(
        JmsDestinationAccessor.RECEIVE_TIMEOUT_NO_WAIT);

Object payload = polling.receiveAndConvert("orders.in");

System.out.println(
        payload == null ? "No message ready immediately"
                        : "Received: " + payload
);
```

**Be careful with the word "immediate":**

- There is no phase of **waiting for a message to arrive**, but creating connection/consumer, communicating with the provider, resolving the Queue name, and cleanup **still have time cost**.
- `null` does not prove the Queue is strictly empty: there may be competing consumers, dispatch/prefetch may not have delivered the message to the newly created consumer yet, or a selector may not match.
- Repeatedly calling `receiveNoWait` in an unthrottled loop can cause **busy polling**, increasing CPU, network traffic, and broker load.

A controlled polling loop:

```java
while (running.get()) {
    Object payload = polling.receiveAndConvert("orders.in");

    if (payload != null) {
        process(payload);
    } else {
        Thread.sleep(250L);
    }
}
```

This is an **illustrative snippet requiring an `AtomicBoolean running` variable and a `process` method already defined**; it must run inside an application-managed worker and handle `InterruptedException` according to the shutdown policy. Do not copy it verbatim into a Java class and expect it to compile without declaring those components.

In continuous message-processing systems, rather than writing your own loop, **`@JmsListener`** and a listener container are usually more appropriate because Spring manages concurrency, recovery, and consumer lifecycle.

## 6. Mode 3: indefinite wait (`receiveTimeout = 0`)

With no additional timeout configuration:

```java
JmsTemplate blocking = new JmsTemplate(connectionFactory);
// Default value is equivalent to:
// blocking.setReceiveTimeout(0L);

Object payload = blocking.receiveAndConvert("orders.in");
System.out.println("Received: " + payload);
```

If the Queue has no messages, the thread can block **forever**. When a message arrives, the consumer is closed, or the JMS provider reports an error, the call can return or throw an exception. **"Indefinite" does not mean the program is immune to network errors, connection closures, or transaction timeouts.**

### When can indefinite wait be acceptable?

- A dedicated thread with a clearly designed **lifecycle/cancellation** strategy and a proper way to close the consumer/connection to exit.
- A local demo tool where **a message is guaranteed to be available** before calling `receive()`.
- A system with dedicated startup/shutdown management that has been tested under broker interruptions.

### When should it be avoided?

- Inside HTTP request threads: an empty Queue can exhaust the thread pool and degrade the API.
- Inside `@Scheduled` jobs or `ApplicationRunner` without an exit path: startup/shutdown can get stuck.
- Inside transactions or flows with strict deadlines: indefinite waiting makes SLAs very hard to meet.
- When polling with multiple workers without supervision or cancellation policies.

**Note on interruption:** do not assume `Thread.interrupt()` will always break a blocked `MessageConsumer.receive()` across all JMS providers. You must design shutdown according to the consumer/connection contract and test directly against your provider.

## 7. Using `receive`, `receiveAndConvert`, and selectors

`receiveTimeout` is a property of a **`JmsTemplate` instance**, not specified per overload. The same timeout configuration applies when invoking the corresponding receive methods.

| Method | Result | How destination is chosen |
| --- | --- | --- |
| `receive()` | `jakarta.jms.Message` or `null` | Uses the template's default destination. |
| `receive("orders.in")` | `Message` or `null` | Selects destination by name. |
| `receive(destination)` | `Message` or `null` | Uses a `jakarta.jms.Destination` object. |
| `receiveAndConvert("orders.in")` | Object payload or `null` | Automatically converts the message using the converter. |
| `receiveSelected("orders.in", selector)` | `Message` or `null` | Receives only messages whose JMS headers/properties match the selector. |
| `receiveSelectedAndConvert("orders.in", selector)` | Object payload or `null` | Selector + converter. |

Example:

```java
template.setDefaultDestinationName("orders.in");
template.setReceiveTimeout(700L);

Message message = template.receive(); // uses orders.in

Object payload = template.receiveAndConvert("orders.audit");
// uses orders.audit, yet still waits up to 700 ms for the receive operation
```

If you call `receive()` without configuring a default destination, Spring does not know where to receive from and typically throws `IllegalStateException`; it does **not** return `null` merely because the destination is missing.

### Selectors do not search inside the body

```java
template.setReceiveTimeout(1_000L);

Message invoice = template.receiveSelected(
        "orders.in",
        "eventType = 'INVOICE'"
);
```

Here the selector evaluates matching **JMS headers/properties**, such as the `eventType` property; it does not parse a JSON body to look for an `eventType` key. If the Queue has messages but **none match the selector**, the call can still expire and return `null`.

Another consumer may also receive from the same Queue first, so `null` does not mean messages were lost or never existed on the broker.

## 8. Configuration with plain Spring Framework

Example bean declarations in a Spring Framework 6 application that already has a `jakarta.jms.ConnectionFactory`:

```java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.JmsDestinationAccessor;

@Configuration
public class ReceiveTimeoutConfig {

    @Bean("boundedJmsTemplate")
    public JmsTemplate boundedJmsTemplate(ConnectionFactory factory) {
        var template = new JmsTemplate(factory);
        template.setDefaultDestinationName("orders.in");
        template.setReceiveTimeout(1_000L);
        return template;
    }

    @Bean("pollingJmsTemplate")
    public JmsTemplate pollingJmsTemplate(ConnectionFactory factory) {
        var template = new JmsTemplate(factory);
        template.setReceiveTimeout(
                JmsDestinationAccessor.RECEIVE_TIMEOUT_NO_WAIT);
        return template;
    }

    @Bean("blockingJmsTemplate")
    public JmsTemplate blockingJmsTemplate(ConnectionFactory factory) {
        var template = new JmsTemplate(factory);
        template.setReceiveTimeout(
                JmsDestinationAccessor.RECEIVE_TIMEOUT_INDEFINITE_WAIT);
        return template;
    }
}
```

This is a compilable Java class when Spring JMS / Jakarta Messaging and a valid `ConnectionFactory` bean are present. **No** `ConnectionFactory` bean is defined in this class: the application must declare one or let Boot create it from the provider.

In a service with multiple beans of type `JmsTemplate`, select the bean using `@Qualifier`:

```java
public OrderPullService(
        @Qualifier("boundedJmsTemplate") JmsTemplate template) {
    this.template = template;
}
```

The constructor above sits inside an `OrderPullService` class with a `JmsTemplate template` field, and requires importing `org.springframework.beans.factory.annotation.Qualifier` and `org.springframework.jms.core.JmsTemplate`.

**Do not repeatedly mutate `setReceiveTimeout` on a singleton `JmsTemplate` shared across multiple threads.** A template instance is designed to be shared after configuration is complete; changing the timeout at runtime can cause request A to accidentally use a timeout set by request B. When multiple wait policies exist, use separate qualifier-injected templates or create dedicated templates per task.

## 9. Spring Boot: configuring `spring.jms.template.receive-timeout`

Spring Boot supports binding the timeout for the auto-configured `JmsTemplate`:

```yaml
# src/main/resources/application.yml
spring:
  jms:
    pub-sub-domain: false
    template:
      default-destination: orders.in
      receive-timeout: 2s
```

Here `2s` is **2 seconds**; Spring Boot converts it to a millisecond-level timeout when configuring the template. Human-readable durations like `500ms` or `2s` can be used. Writing a bare integer without a suffix can be ambiguous; specify the unit explicitly.

The three modes can be expressed via the property:

```yaml
# PICK one value for spring.jms.template.receive-timeout:
receive-timeout: 1500ms   # finite
receive-timeout: -1ms     # no wait
receive-timeout: 0ms      # indefinite wait
```

These are **three alternative lines**, not three repeated YAML keys in a single valid configuration.

**Note:** when you manually construct `new JmsTemplate(connectionFactory)` and declare a custom bean, do not assume Spring Boot properties are automatically applied to every instance. Use appropriate auto-configuration or call `setReceiveTimeout` yourself.

### `spring.jms.listener.receive-timeout` is not the same setting

Spring Boot also has another property:

```yaml
spring:
  jms:
    listener:
      receive-timeout: 1s
```

This property relates to the **receive cycle inside the Boot-configured JMS listener container**, **not the timeout for `JmsTemplate.receive(...)`**. A listener container generally needs opportunities to return from receive to check shutdown/recovery signals; setting listener receive to indefinite does not imply it behaves the same or as safely as a standalone template.

In summary:

| Property | Scope |
| --- | --- |
| `spring.jms.template.receive-timeout` | Synchronous receive operations via the auto-configured `JmsTemplate`; can also affect reply waiting in `sendAndReceive` on that template. |
| `spring.jms.listener.receive-timeout` | Internal receive operation of the listener container; affects stop/recovery checks. |
| `spring.jms.template.default-destination` | Default destination name when template methods omit the destination. |
| `spring.jms.template.time-to-live` | Time-to-live of **sent** messages, not receive wait duration. |

Do not confuse a JMS listener timeout with an HTTP timeout or an overall job timeout.

## 10. Java 17/Spring Boot/Artemis demo: observing all three modes

The example below is a **Java 17 + Spring Boot 3.3.x + ActiveMQ Artemis** application without embedding a JMS server in the application classpath. It uses dedicated test Queues:

- `demo.timeout.empty`: assumed **empty** during the first two checks.
- `demo.timeout.ready`: the producer pre-sends a message before the consumer receives in "indefinite wait" mode so the **demo does not hang unintentionally**.

### 10.1. Running Artemis with Docker

If Docker is available:

```bash
docker run --detach --rm --name artemis-timeout-demo -p 61616:61616 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:2.57.0-alpine
```

Wait for the broker to become ready and inspect `docker logs artemis-timeout-demo`. Queue names `demo.timeout.empty` and `demo.timeout.ready` must be **provisioned** or the broker must allow auto-creation. These are local test credentials/environment settings; production must secure the broker with proper authentication and TLS.

### 10.2. Project structure

```text
receive-timeout-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── resources/application.yml
    └── java/example/jms/ReceiveTimeoutApplication.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'receive-timeout-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

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
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

File `src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
    password: demo
  jms:
    pub-sub-domain: false
```

This is a **native** connection to an external broker. Spring Boot creates an appropriate `ConnectionFactory` for Artemis. The example creates three separate templates to clearly demonstrate the three timeout modes rather than mutating a single singleton while other requests are running.

### 10.3. Complete Java file

Create `src/main/java/example/jms/ReceiveTimeoutApplication.java`:

```java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.JmsDestinationAccessor;

@SpringBootApplication
public class ReceiveTimeoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReceiveTimeoutApplication.class, args);
    }

    @Bean
    ApplicationRunner demonstrate(ConnectionFactory connectionFactory) {
        return args -> {
            String emptyQueue = "demo.timeout.empty";
            String readyQueue = "demo.timeout.ready";

            // 1) Finite wait: 250 ms.
            JmsTemplate finite = new JmsTemplate(connectionFactory);
            finite.setReceiveTimeout(250L);
            Object a = finite.receiveAndConvert(emptyQueue);
            System.out.println("FINITE: " + describe(a));

            // 2) No wait: -1 ms.
            JmsTemplate noWait = new JmsTemplate(connectionFactory);
            noWait.setReceiveTimeout(
                    JmsDestinationAccessor.RECEIVE_TIMEOUT_NO_WAIT);
            Object b = noWait.receiveAndConvert(emptyQueue);
            System.out.println("NO_WAIT: " + describe(b));

            // 3) Indefinite wait: 0 ms.
            // Pre-send so the demo does not block forever on an empty Queue.
            JmsTemplate sender = new JmsTemplate(connectionFactory);
            sender.convertAndSend(readyQueue, "READY");

            JmsTemplate indefinite = new JmsTemplate(connectionFactory);
            indefinite.setReceiveTimeout(
                    JmsDestinationAccessor.RECEIVE_TIMEOUT_INDEFINITE_WAIT);
            Object c = indefinite.receiveAndConvert(readyQueue);
            System.out.println("INDEFINITE: " + describe(c));
        };
    }

    private static String describe(Object result) {
        return result == null ? "NONE" : result.toString();
    }
}
```

Key points to notice:

1. All three templates share the same **`ConnectionFactory`**, yet each template has its own wait policy.
2. Both `finite` and `noWait` read from the same Queue **assumed to be empty**, so the illustrative output does not depend on late message arrival.
3. `indefinite` is genuinely a `0L` template, but the **producer already sent `"READY"` beforehand**, so with a healthy broker the message is ready and no long wait occurs.
4. `receiveAndConvert` turns `TextMessage("READY")` into a `String` when an appropriate default converter is active.
5. There is no competing `@JmsListener` in the demo: all three receives run **synchronously on the `ApplicationRunner` thread**.

### 10.4. Running and output

With JDK 17 and Gradle 8.x compatible with Spring Boot 3.3.x:

```bash
gradle bootRun
```

If a Gradle Wrapper is present, use `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows.

With a clean broker, both Queues validly created, `"READY"` successfully sent/received, and no competing consumers, the lines printed by the application are:

```text
FINITE: NONE
NO_WAIT: NONE
INDEFINITE: READY
```

This is the **expected output under the conditions stated above**, not captured log output from an actual run in this article. In addition to these lines, Spring Boot startup logs will also appear. If `demo.timeout.empty` still holds messages from a previous run, the first two lines may no longer be `NONE`. If the broker fails or destinations are not provisioned, the application may throw an exception instead of printing all three lines.

When finished, stop the broker:

```bash
docker stop artemis-timeout-demo
```

### 10.5. Testing finite wait when a message arrives late

To observe `receive(2_000)` returning **earlier than 2 seconds** when a message arrives, an independent producer thread can send after roughly 500 ms. This is a **standalone experiment** snippet (do not paste directly into the sample without handling thread lifecycle):

```java
try (var executor = java.util.concurrent.Executors
        .newSingleThreadExecutor()) {
    executor.submit(() -> {
        Thread.sleep(500L);
        sender.convertAndSend("demo.timeout.delayed", "ARRIVED");
        return null;
    });

    finite.setReceiveTimeout(2_000L);
    Object result = finite.receiveAndConvert("demo.timeout.delayed");
    System.out.println("DELAYED: " + result);
}
```

**Important note:** `ExecutorService` only implements `AutoCloseable` in **Java 19+**, so the `try-with-resources` block above is not for Java 17. If practicing on Java 17, use the valid version below:

```java
java.util.concurrent.ExecutorService executor =
        java.util.concurrent.Executors.newSingleThreadExecutor();

try {
    executor.submit(() -> {
        Thread.sleep(500L);
        sender.convertAndSend("demo.timeout.delayed", "ARRIVED");
        return null;
    });

    finite.setReceiveTimeout(2_000L);
    Object result = finite.receiveAndConvert("demo.timeout.delayed");
    System.out.println("DELAYED: " + result);
} finally {
    executor.shutdown();
}
```

This valid Java 17 snippet is used **inside a method where `sender` and `finite` exist**, and requires the `demo.timeout.delayed` Queue to exist or be auto-creatable. Under normal conditions, you can observe `DELAYED: ARRIVED`, though there is no strict guarantee on the 500 ms timing due to thread scheduling and broker startup. If the producer task fails while the consumer has a 2-second timeout, the caller exits with `null` instead of waiting forever. In production code, inspect the producer's `Future` so send failures are not silently missed.

## 11. Waiting for a message vs. waiting for a reply: do not mix deadlines

A request-reply application often uses `JmsTemplate.sendAndReceive(...)` to send a request and then wait for a reply on an appropriate response destination. In Spring JMS, `JmsTemplate`'s `sendAndReceive` mechanism also uses **`receiveTimeout`** when waiting for the response.

Example:

```java
JmsTemplate rpc = new JmsTemplate(connectionFactory);
rpc.setReceiveTimeout(3_000L);

Message reply = rpc.sendAndReceive(
        "orders.requests",
        session -> session.createTextMessage("STATUS:42")
);
```

This is a snippet inside a method with `connectionFactory`; it requires importing `jakarta.jms.Message`. Depending on the version/overload, Spring may use a temporary reply Queue, set `JMSReplyTo` on the request, and wait for the response. If no matching reply arrives within the timeout, the result may be `null`.

**Do not confuse different time limits:**

| Setting | What does it control? |
| --- | --- |
| `receiveTimeout` | Wait time for a message/reply in the corresponding receive operation on the template. |
| `timeToLive` / JMSExpiration | Lifetime of a message after being **sent**; past expiry it may be expired by the broker. |
| `deliveryDelay` | Duration the broker is asked to delay delivery of a sent message. |
| HTTP client timeout | How long an HTTP client is willing to wait for the server. |
| Business SLA/deadline | Time budget for the entire business workflow. |

A request that expires before a consumer processes it will not automatically produce a reply. A client waiting 3 seconds and timing out may miss a late reply even though the reply message still exists on the broker. Hence, request-reply requires proper **correlation IDs, retry/idempotency, and cleanup**, not just setting `receiveTimeout`.

In real systems, avoid using the default `receiveTimeout=0` for an HTTP request waiting on a remote service, because the request can hang and hold resources.

## 12. How does synchronous receiving differ from asynchronous listeners?

### `JmsTemplate.receive`: the caller actively waits

```java
Object msg = template.receiveAndConvert("orders.in");
// Continues only after receiving a message, timing out, or throwing an error.
```

The **calling thread** is held until the receive operation completes. If the Queue rarely has messages, each poll creates a temporary consumer and can incur overhead. This approach makes sense for tools, bounded jobs, or specialized request-reply integrations.

### `@JmsListener`: the container manages consumers automatically

```java
@JmsListener(destination = "orders.in")
public void onMessage(String text) {
    System.out.println("Received: " + text);
}
```

This is a method inside a Spring bean, requiring `@EnableJms` or appropriate auto-registration. The listener container maintains consumers and dispatches as messages arrive; you do not need to write a `receive()` loop in business code.

**Competing Queue warning:** if both a `@JmsListener` and `JmsTemplate.receive` read from the same Queue, they are competing consumers. A message may be delivered to the listener before `receive` can grab it, so the synchronous call can return `null` even though the producer just sent a message. You cannot conclude from that result that JMS is broken.

### When to choose which?

- Continuous receiving, high concurrency, recovery/monitoring: typically choose a listener container.
- One-off checks or waiting for a result with a deadline: synchronous receive with a **positive timeout**.
- Instant Queue inspection to support operations: **no-wait**, while avoiding busy loops.
- Intentional indefinite wait: only in contexts with controlled shutdown and exception handling.

## 13. Timeout is not a transaction, ACK, or redelivery policy

`receiveTimeout` determines **how long to wait for a message**; it does **not** determine:

- Whether the session uses `AUTO_ACKNOWLEDGE`, `CLIENT_ACKNOWLEDGE`, or transactions.
- When a local/JTA transaction commits or rolls back.
- Whether a received message can be redelivered if the consumer crashes.
- Whether a message is filtered by a selector or expires due to TTL.
- How many competing consumers exist on the Queue or the retry count.

Example:

```java
template.setReceiveTimeout(500L);
Message message = template.receive("orders.in");

if (message != null) {
    // Business processing requires idempotency and an appropriate transaction.
    handleBusinessEvent(message);
}
```

This snippet requires a `handleBusinessEvent` method to be declared. Once `template.receive` returns a message, ACK/transaction responsibility still depends on session/template/provider configuration. **Do not** assume setting a short timeout makes messages "safer" or automatically prevents duplication.

Inside an active transaction, the transaction deadline and transaction-aware session management can also affect waiting/committing. To guarantee an end-to-end business deadline, inspect the transaction manager as well as time spent opening connections, sending/receiving, converting, and writing to the DB.

### Null is not a rollback

If `receive` returns `null`, it means the current operation received no matching JMS message; typically there is no body to process or ACK. This should not be treated as an error that forces a transaction rollback; the application can treat it as "no work," retry later, or finish the job normally.

## 14. Common errors and how to diagnose them

| Symptom | Possible cause | Proper fix |
| --- | --- | --- |
| Called `setReceiveTimeout(0)` and the app hangs | `0` is **indefinite wait**, not no-wait. | Use `RECEIVE_TIMEOUT_NO_WAIT` (`-1L`) or a positive timeout. |
| Called `setReceiveTimeout(-1)` and got `null` despite Queue having messages | Immediate probe; message not yet dispatched or taken by another consumer. | If waiting is desired, use a positive timeout; check broker and competing consumers. |
| Set `2_000L` but call took over 2 seconds | Timeout applies mainly to the `receive` phase, excluding connect/setup/cleanup. | Measure each phase; configure connect timeout and caller-level deadlines. |
| `receive()` does not know where to receive from | Missing default destination on the template. | Call `receive("queue")` or `setDefaultDestinationName("queue")`. |
| Queue has messages but `receiveSelected` always returns `null` | Selector does not match JMS properties/headers. | Check selector and properties; do not query JSON body fields. |
| `receiveAndConvert` returns `null` | No message in this attempt or custom converter returned null. | Test raw `receive`; inspect converter and broker. |
| Set `spring.jms.listener.receive-timeout` yet `JmsTemplate` still blocks | That property is for the listener container, not the template. | Set `spring.jms.template.receive-timeout` or call the setter on the template. |
| Set `spring.jms.template.receive-timeout` yet custom bean is unchanged | Manually constructed `new JmsTemplate` without applying properties. | Configure the custom bean directly or use Boot auto-config. |
| `receive` returns an unexpected message type | Multiple message types/producers on the Queue, mismatched converter or selector. | Inspect raw headers/type; use the right converter/schema. |
| Slow API or thread exhaustion | Indefinite wait or overly long timeout inside every HTTP request. | Reduce timeout; use async listener/service or event-driven design. |
| High CPU/broker load despite no messages | Tight no-wait polling loop without backoff. | Use finite wait, delay/backoff, or a listener. |
| Message "disappeared" from your receive attempt | Another consumer on the Queue received it. | Check concurrency, routing, consumer groups/provider policies. |
| Encountered `JmsException` | Broker disconnected, invalid permissions, session error. | Log the root cause and check the provider; do not swallow errors as "no message." |
| Worker refuses to stop | Blocking indefinite receive and provider does not exit on interrupt alone. | Switch to a positive timeout; design shutdown to close resources per contract. |

A practical debugging workflow:

1. Record the template bean in use and its **`getReceiveTimeout()`**.
2. Verify destination name, Queue/Topic domain, `DestinationResolver`, and selector.
3. Check broker logs: connections, permissions, Queue depth, dispatched messages, consumer count.
4. Confirm whether competing consumers exist; test on a clean Queue with a single consumer.
5. Measure **end-to-end call duration** and separate connection/resolve time from message wait time.
6. Check ACK, transactions, redelivery, and converter if a message was received but the app did not see the expected payload.

## 15. Recommended tests

### Unit tests

For pure timeout configuration code, do not assume a mocked `JmsTemplate` executes real `receive` semantics. You can verify bean configuration:

```java
assertEquals(1_000L, boundedTemplate.getReceiveTimeout());
assertEquals(-1L, pollingTemplate.getReceiveTimeout());
assertEquals(0L, blockingTemplate.getReceiveTimeout());
```

This is an **illustrative JUnit assertion** snippet in a test with three matching template beans; it requires importing `org.junit.jupiter.api.Assertions.assertEquals`.

Testing setters/constants prevents mixing up `0` and `-1`, but **does not replace** real message-receiving tests.

### Integration tests with a broker

1. Create a clean Queue with no other consumers.
2. With a `-1` template, call `receive` on the empty Queue and assert it returns `null` (without asserting exact millisecond timing).
3. With a `300L` template, call receive on the empty Queue and assert it returns `null` after a bounded wait, allowing environmental tolerance.
4. Send a `TextMessage`, then use a `0L` template to receive; send **first** so the test does not hang.
5. Send a message after a small delay from a separate producer and verify the finite-timeout template can receive before expiry.
6. Test a non-matching selector on a Queue containing messages; verify waiting/not waiting depends on **matching messages**, not total Queue depth.
7. Test when the broker loses connection; verify exceptions are distinguished from `null`.
8. If the product uses HTTP or transactions, measure end-to-end deadlines and add cancellation/shutdown tests instead of testing only the happy path.

Avoid `assertEquals(300, elapsedMillis)` because scheduling, broker dispatch, network, and resource creation introduce variance. Use a reasonable range instead, along with metric/log observation when needed.

## 16. Self-check exercises

**Q1.** With `receiveTimeout=0`, `receive("orders.in")` returns `null` immediately when the Queue is empty — true or false?

**Answer:** **False**. A value of `0` means **indefinite wait**; the thread can block until a message arrives, the consumer closes, or an error occurs.

**Q2.** To check for an already available message without waiting for new messages to arrive, which value should be used?

**Answer:** A **negative** value, typically `JmsDestinationAccessor.RECEIVE_TIMEOUT_NO_WAIT` (`-1L`).

**Q3.** Does `1_500L` guarantee that the entire `receiveAndConvert` call always finishes within at most 1.5 seconds?

**Answer:** No. It is a timeout **for waiting on the message**, not an overall deadline covering connection setup, consumer creation, converter execution, and cleanup.

**Q4.** If a Queue has two consumers and a message is delivered to consumer A, does consumer B receiving `null` after timeout mean the broker lost the message?

**Answer:** No. On a Queue, consumers compete; once a message is delivered to A, B may not receive it.

**Q5.** Does `spring.jms.listener.receive-timeout` configure `JmsTemplate.receive`?

**Answer:** No. That setting is for the listener container; the template uses `spring.jms.template.receive-timeout` or `setReceiveTimeout` directly.

**Q6.** In the standard JMS API, `MessageConsumer.receive(0)` means no wait, right?

**Answer:** **No**. According to Jakarta Messaging, `receive(0)` means **indefinite wait**; immediate polling is `receiveNoWait()`.

**Q7.** `receiveSelected("orders.in", "type = 'X'")` times out and returns `null`, while the Queue holds a `type='Y'` message. Is that expected?

**Answer:** Yes. A consumer with a selector receives only matching messages; `Y` messages are not eligible inputs for that receive attempt.

**Q8.** When should indefinite wait be used?

**Answer:** Only in environments with clear control over resources, lifecycle, and shutdown; avoid it in HTTP threads or workers lacking a cancellation mechanism.

## 17. Official documentation

- [Spring Framework – Receiving a Message (Synchronous Receipt)](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework 6.2 – JmsTemplate: setReceiveTimeout and receive](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Spring Framework 6.2 – JmsDestinationAccessor: RECEIVE_TIMEOUT_NO_WAIT / INDEFINITE_WAIT](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/destination/JmsDestinationAccessor.html)
- [Spring Framework – JmsTemplate Constants and JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/constant-values.html)
- [Spring Boot 3 – Configuring JMS](https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html)
- [Spring Boot – Common Application Properties: spring.jms.template.receive-timeout](https://docs.spring.io/spring-boot/3.4/appendix/application-properties/)
- [Jakarta Messaging 3.1 – MessageConsumer.receive / receiveNoWait](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageconsumer)
- [Apache ActiveMQ Artemis – Running Broker with Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)

**Most important takeaway:** In **Spring JMS `JmsTemplate`**, **positive = finite wait**, **`-1` (negative) = no wait**, and **`0` = indefinite wait**. Choose the timeout according to business goals and thread lifecycle, distinguish `null` from `JmsException`, and never confuse the template's timeout with the listener's timeout or message TTL.
