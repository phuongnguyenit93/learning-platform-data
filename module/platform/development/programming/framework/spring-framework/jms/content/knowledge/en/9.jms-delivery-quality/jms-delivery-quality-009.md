# Listener Reply QoS in Spring JMS

## 1. What Is Listener Reply QoS?

In Spring JMS, a `@JmsListener` method can **receive a request, process it, and return a result**. When an appropriate reply destination exists, Spring converts the return value into a JMS message and sends it to the corresponding Queue or Topic. This reply message has its **own Quality of Service (QoS)**, which does not necessarily match the request message.

The three fundamental JMS QoS parameters when **sending a reply** are:

- **Delivery mode:** `PERSISTENT` or `NON_PERSISTENT`.
- **Priority:** priority level from `0` to `9`.
- **Time-to-live (TTL):** response lifetime in milliseconds measured from when **the response is sent**; `0` means no TTL-based expiration.

Spring Framework provides `org.springframework.jms.support.QosSettings` to bundle these three parameters, and `DefaultJmsListenerContainerFactory.setReplyQosSettings(...)` to apply them **to reply messages automatically sent by Spring** from listeners of that container.

```text
Request producer                     Spring JMS listener
        |                                    |
        |  Request: TextMessage              |
        |  destination = demo.requests       |
        +----------------------------------->| @JmsListener
        |                                    | process
        |                                    | return "APPROVED"
        |                                    v
        |                            Spring converts response
        |                            into JMS TextMessage
        |                                    |
        |                                    | applies QosSettings:
        |                                    |   priority=2
        |                                    |   TTL=10,000 ms
        |                                    |   PERSISTENT
        |                                    v
        |                              Response destination
        |                              (JMSReplyTo/@SendTo)
        |<-----------------------------------+
        |
Response consumer (or request-reply client)
```

**Most important point:** configuring `replyQosSettings` controls **messages sent back from the listener**, without changing the QoS of the incoming request being consumed; nor does it set QoS for `JmsTemplate.convertAndSend(...)` in any service.

## 2. Conditions for Spring to Actually Send a Reply

QoS configuration matters only when the listener **actually produces a response**.

### 2.1. Listener Returns a Non-`void` Value

Example:

```java
@JmsListener(destination = "orders.requests")
@SendTo("orders.responses")
public String process(String request) {
    return "ACK:" + request;
}
```

This is a **method inside a Spring bean**, requiring imports `org.springframework.jms.annotation.JmsListener` and `org.springframework.messaging.handler.annotation.SendTo`.

Spring can convert the string `"ACK:..."` into a `TextMessage` via an appropriate `MessageConverter` (with `SimpleMessageConverter` by default). Spring then sends that message to the response destination.

- `@JmsListener(destination=...)`: Queue/Topic to **receive** requests.
- `@SendTo(...)`: default response destination when **sending** replies.
- `return ...`: payload used to build the **reply message**.
- `setReplyQosSettings(...)`: QoS of the **reply send** inside the listener container.

### 2.2. In What Order Is the Response Destination Selected?

With standard automatic reply handling, Spring resolves the destination as follows:

1. **`JmsResponse`** returned by the listener: used when deciding the destination dynamically at runtime.
2. If no custom destination is returned as above, **`JMSReplyTo`** on the request (if present) serves as the response destination.
3. If the request lacks `JMSReplyTo`, Spring uses **`@SendTo`** or the default response destination configured on the listener adapter.
4. If no valid reply destination exists, sending the reply may fail with a destination error.

Therefore `@SendTo("orders.responses")` usually acts as a **fallback** when the request does not provide `JMSReplyTo`. In request-reply using `TemporaryQueue`, clients normally set `JMSReplyTo` on the request to receive their own isolated responses.

**QoS and destination are two separate decisions:** `QosSettings` neither creates Queues nor resolves missing `JMSReplyTo` or `@SendTo`.

### 2.3. Listener Returning No Reply

```java
@JmsListener(destination = "orders.requests")
public void consumeOnly(String request) {
    // Only processes request; creates no automatic response.
}
```

There is no return value to send, so **`replyQosSettings` has no message to apply to**. A `void` listener that **manually calls `JmsTemplate` to send a response** also does not use the container's reply QoS setting for that send; see Section 11.

## 3. Which Fields Does `QosSettings` Contain?

Class `org.springframework.jms.support.QosSettings` has a no-arg constructor and the constructor:

```java
QosSettings settings = new QosSettings(
        DeliveryMode.PERSISTENT,
        2,
        10_000L
);
```

In this snippet, `DeliveryMode` is `jakarta.jms.DeliveryMode`, and `QosSettings` is `org.springframework.jms.support.QosSettings`.

Equivalent setters can be used:

```java
QosSettings settings = new QosSettings();
settings.setDeliveryMode(DeliveryMode.PERSISTENT);
settings.setPriority(2);
settings.setTimeToLive(10_000L);
```

| Property | Method | Valid Range or Meaning |
| --- | --- | --- |
| Delivery mode | `setDeliveryMode(int)` | `DeliveryMode.PERSISTENT` or `DeliveryMode.NON_PERSISTENT`. |
| Priority | `setPriority(int)` | `0..9`; 9 highest, 0 lowest. JMS default is typically 4. |
| Time-to-live | `setTimeToLive(long)` | Non-negative milliseconds; `10_000L` is 10 seconds, `0` is no TTL expiration. |

The **default values inside `new QosSettings()`** are JMS message defaults: `PERSISTENT`, priority `4`, TTL `0`. Those are standard defaults on the settings object, **not a guarantee that the broker always uses those exact values** when QoS is unconfigured; a JMS provider may have its own administrative defaults.

Summary:

```text
new QosSettings()
  deliveryMode = PERSISTENT
  priority     = 4
  timeToLive   = 0 ms

new QosSettings(PERSISTENT, 2, 10_000)
  deliveryMode = PERSISTENT
  priority     = 2
  timeToLive   = 10,000 ms
```

**`NON_PERSISTENT` does not mean "guaranteed message loss"; `PERSISTENT` likewise does not equal exactly-once.** Delivery mode is only one part of the JMS contract; crash recovery, acknowledgements, retries, transactions, broker policies, and consumer idempotency still matter.

### Priority Is Only a Hint to the Broker

Priority `2` is **lower** than the default `4` (not "high priority"). Providers may use priority for delivery scheduling, yet never strictly promise priority 9 messages always precede every priority 4 message. With multiple consumers, transacted sessions, prefetch, retries, and concurrency, actual log order can differ from send order.

### TTL Starts Counting When the Reply Is Sent

`timeToLive=10_000L` does not start when the listener receives the request or when the user sends the request. It is the duration applied to the **reply message at send time**. For example, if a listener processes a request for 5 seconds and then sends a reply with a 10-second TTL: in principle the response expires roughly 10 seconds after **sending the reply**, not 5 seconds after the request arrived.

With a standard provider, you can inspect the `JMSExpiration` header on the reply; `0` usually indicates no expiration, while a positive timestamp is the expected expiration time (epoch milliseconds). Headers may be subject to broker/provider policies. TTL is not a client-side response wait timeout.

## 4. Proper Configuration: `setReplyQosSettings` on the Listener Container Factory

Spring Framework 6 provides `DefaultJmsListenerContainerFactory` to create listener containers for `@JmsListener`.

Minimal example **in a Spring app that already has a `ConnectionFactory` bean**:

```java
package demo.jms;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.support.QosSettings;

@Configuration
public class ReplyQosConfiguration {

    @Bean("replyQosFactory")
    public DefaultJmsListenerContainerFactory replyQosFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);

        var qos = new QosSettings();
        qos.setDeliveryMode(DeliveryMode.PERSISTENT);
        qos.setPriority(2);
        qos.setTimeToLive(10_000L);

        factory.setReplyQosSettings(qos);
        return factory;
    }
}
```

And a listener referencing the **exact factory name**:

```java
@Component
public class OrderResponder {

    @JmsListener(
            destination = "orders.requests",
            containerFactory = "replyQosFactory"
    )
    @SendTo("orders.responses")
    public String respond(String request) {
        return "ACK:" + request;
    }
}
```

`OrderResponder` requires imports for `org.springframework.stereotype.Component`, `org.springframework.jms.annotation.JmsListener`, and `org.springframework.messaging.handler.annotation.SendTo`, placed in an app with the configuration above.

**Effect:** responses **automatically created and sent by Spring** through a listener container built by `replyQosFactory` will carry the declared QoS. The setting does not automatically apply to `@JmsListener` endpoints on other factories.

If you want a default factory for `@JmsListener` methods that omit `containerFactory`, name the bean `jmsListenerContainerFactory` (or configure the default factory via `JmsListenerConfigurer`). With Spring Boot, use the configurer to preserve defaults; see Section 5.

### Do Not Confuse the APIs

The `QosSettings` class here belongs to Spring JMS. There is **no** `jakarta.jms.QosSettings` (no such API exists). `setReplyQosSettings` belongs to the **listener container factory / listener container**, not an attribute on `@SendTo` or `@JmsListener`. Spring does not provide `priority` or `timeToLive` attributes directly on `@SendTo` for JMS.

## 5. With Spring Boot: Preserve Auto-Configuration

In Spring Boot 3, if you define a custom `DefaultJmsListenerContainerFactory`, use `DefaultJmsListenerContainerFactoryConfigurer` to apply Boot defaults (converter, concurrency, transaction settings, etc., if present) before overriding reply QoS.

```java
package demo.jms;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.support.QosSettings;

@Configuration(proxyBeanMethods = false)
public class ReplyQosConfiguration {

    @Bean("replyQosFactory")
    public DefaultJmsListenerContainerFactory replyQosFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer) {

        var factory = new DefaultJmsListenerContainerFactory();
        configurer.configure(factory, connectionFactory);

        var reply = new QosSettings();
        reply.setDeliveryMode(DeliveryMode.PERSISTENT);
        reply.setPriority(2);
        reply.setTimeToLive(10_000L);
        factory.setReplyQosSettings(reply);

        return factory;
    }
}
```

Here `replyQosFactory` is an **additional, explicitly scoped factory**; Boot can still create the default `jmsListenerContainerFactory` for other listeners. `@JmsListener(containerFactory = "replyQosFactory")` selects this configuration.

**Order matters:** call `configurer.configure(...)` first and `setReplyQosSettings(...)` second so custom reply QoS values are not overwritten by general configuration.

### Why Not Just Set `spring.jms.template.priority`?

The following properties control **`JmsTemplate` when sending outbound messages**:

```yaml
spring:
  jms:
    template:
      priority: 8
      time-to-live: 5s
      qos-enabled: true
```

They **do not automatically set QoS on auto-generated replies from listeners**. To give listener replies priority 2 and a 10-second TTL, configure **`setReplyQosSettings` on the corresponding factory**.

Conversely, configuring reply QoS on a listener does **not** alter the QoS of requests sent by services via `JmsTemplate`. The two send paths use two separate configuration layers. Never set priority 8 system-wide just hoping one listener's replies get higher priority.

## 6. Full Demo: Java 17 + Spring Boot + ActiveMQ Artemis

Demo goals:

1. Producer sends `"PING-001"` to Queue `demo.reply.requests`.
2. `@JmsListener` receives the request and **returns** `"ACK:PING-001"`.
3. Spring automatically sends the reply to `demo.reply.responses` via `@SendTo`.
4. The reply is sent with **priority 2, 10-second TTL, PERSISTENT** via `replyQosFactory`.
5. A separate listener reads the reply and prints `JMSPriority`, `JMSDeliveryMode`, and `JMSExpiration`.

Environment: **Java 17+, Spring Boot 3.3.13, Gradle 8.5+**, with an **Apache ActiveMQ Artemis** broker running at `localhost:61616`. The example uses `jakarta.jms` APIs without mixing old `javax.jms`.

### 6.1. Starting a Test Broker

On a machine with Docker running:

```bash
docker run --detach --rm --name artemis-reply-qos -p 61616:61616 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest-alpine
```

Wait for the broker to be ready before running the app. Queues `demo.reply.requests` and `demo.reply.responses` must exist or the broker must allow auto-creation. If auto-create is off or permissions are restricted, an administrator must provision both queues and grant permissions beforehand. Demo credentials are for local use only.

Stop the broker when done:

```bash
docker stop artemis-reply-qos
```

### 6.2. Project Structure

```text
reply-qos-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/jms/
    │   ├── ReplyQosApplication.java
    │   ├── ReplyQosConfiguration.java
    │   └── ReplyHandlers.java
    └── resources/
        └── application.yml
```

File `settings.gradle`:

```groovy
rootProject.name = 'reply-qos-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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

`pub-sub-domain: false` resolves the demo's destination names as **Queues**, not Topics. Both Queues must match broker configuration.

### 6.3. Main Application and Request Producer

File `src/main/java/demo/jms/ReplyQosApplication.java`:

```java
package demo.jms;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
@EnableJms
public class ReplyQosApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReplyQosApplication.class, args);
    }

    @Bean
    ApplicationRunner sendOneRequest(JmsTemplate jmsTemplate) {
        return args -> {
            jmsTemplate.convertAndSend(
                    "demo.reply.requests",
                    "PING-001"
            );
            System.out.println("Request submitted");
        };
    }
}
```

Here the request is sent via Boot's auto-configured `JmsTemplate` with standard defaults. No `JMSReplyTo` is set; the listener uses `@SendTo` to pick the reply queue. **The request message's priority has no direct bearing on reply priority=2**.

### 6.4. Listener Container Factory with Reply QoS

File `src/main/java/demo/jms/ReplyQosConfiguration.java`:

```java
package demo.jms;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;

import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.support.QosSettings;

@Configuration(proxyBeanMethods = false)
public class ReplyQosConfiguration {

    @Bean("replyQosFactory")
    public DefaultJmsListenerContainerFactory replyQosFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer) {

        var factory = new DefaultJmsListenerContainerFactory();
        configurer.configure(factory, connectionFactory);

        var replyQos = new QosSettings();
        replyQos.setDeliveryMode(DeliveryMode.PERSISTENT);
        replyQos.setPriority(2);
        replyQos.setTimeToLive(10_000L);

        factory.setReplyQosSettings(replyQos);
        return factory;
    }
}
```

`replyQosFactory` is selected **only** for listeners specifying `containerFactory="replyQosFactory"`. Defining a named factory bean does not switch every listener in the app to use it.

### 6.5. Handling Requests and Inspecting Replies

File `src/main/java/demo/jms/ReplyHandlers.java`:

```java
package demo.jms;

import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSException;
import jakarta.jms.TextMessage;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Component;

@Component
public class ReplyHandlers {

    @JmsListener(
            destination = "demo.reply.requests",
            containerFactory = "replyQosFactory"
    )
    @SendTo("demo.reply.responses")
    public String respond(String request) {
        return "ACK:" + request;
    }

    @JmsListener(destination = "demo.reply.responses")
    public void inspectResponse(TextMessage message)
            throws JMSException {

        String body = message.getText();
        int priority = message.getJMSPriority();
        boolean persistent =
                message.getJMSDeliveryMode() == DeliveryMode.PERSISTENT;
        boolean expiring = message.getJMSExpiration() > 0L;

        System.out.printf(
                "Reply body=%s, priority=%d, persistent=%s, expires=%s%n",
                body, priority, persistent, expiring
        );
    }
}
```

**Analysis:**

- `respond` returns a `String`; Spring's listener adapter converts it into a JMS response message.
- `@SendTo` supplies the response Queue name because the demo request **has no `JMSReplyTo`**.
- `replyQosFactory` sets QoS when Spring sends the response.
- `inspectResponse` receives a raw `TextMessage` to read metadata, **sends no reply** since it returns `void`, and uses Boot's default factory.
- `JMSPriority`, `JMSDeliveryMode`, and `JMSExpiration` are **reply headers** assigned/processed by the provider; inspecting them proves actual QoS effect rather than just printing in-memory configuration.

### 6.6. Running and Output

From the project directory, run:

```bash
gradle bootRun
```

With the Gradle Wrapper, use `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows.

On a clean broker with Queues provisioned/auto-creatable, listeners ready, and an unexpired reply, the app can print:

```text
Request submitted
Reply body=ACK:PING-001, priority=2, persistent=true, expires=true
```

**The order of these two lines is not guaranteed**: listeners run asynchronously, so `Reply body...` may appear before `Request submitted`. Other Spring console logs also appear. If the provider enforces custom policies or QoS is not sent as expected, investigate header values rather than assuming the output above is fixed.

Because TTL is only 10 seconds, ensure the listener consumes promptly; if the broker holds the reply past expiration, it may never be delivered to `inspectResponse`. Increase TTL if startup/load timing affects tests.

### 6.7. If the Demo Fails to Run

Check in order:

1. Artemis is ready at `tcp://localhost:61616` with valid user/password.
2. Both Queues exist or auto-creation is enabled; the application has send/consume permissions.
3. `spring-boot-starter-artemis` resolved cleanly with no mixing of `javax.jms` and `jakarta.jms` clients.
4. `replyQosFactory` matches the exact bean name and `respond` specifies `containerFactory="replyQosFactory"`.
5. `respond` actually returns a `String`, the converter builds a `TextMessage`, and `@SendTo` targets the right response Queue.
6. Test against a clean broker to avoid leftover messages from previous runs, expired messages, redeliveries, or other consumers.

This example contains **complete source code and configuration to compile/run in a suitable environment**; it does not claim to have been executed directly against a live broker during documentation authoring.

## 7. How Do `JMSReplyTo` and `@SendTo` Interact with QoS?

### 7.1. Requests Carrying `JMSReplyTo`

A producer can place the reply destination directly on the request:

```java
jmsTemplate.send("demo.reply.requests", session -> {
    TextMessage request = session.createTextMessage("PING-002");
    request.setJMSReplyTo(session.createQueue("client.private.replies"));
    return request;
});
```

This is a snippet **inside a method with an injected `JmsTemplate`**, requiring `jakarta.jms.TextMessage`. For this request, `respond` may send its response to **`client.private.replies`** instead of `@SendTo("demo.reply.responses")`, because the request's `JMSReplyTo` takes precedence under default reply resolution.

**Reply QoS still remains reply QoS**: `replyQosFactory` can send the response to the chosen reply Queue with priority 2, 10s TTL, `PERSISTENT`. Changing destination does not alter `QosSettings`.

Note: the client must have a consumer listening on `client.private.replies`. Otherwise you might see the request processed with no log on `demo.reply.responses` and mistakenly think the reply vanished.

### 7.2. Using `JmsResponse` When Destination Depends on Result

When picking the destination inside the handler method:

```java
@JmsListener(
        destination = "orders.requests",
        containerFactory = "replyQosFactory"
)
public JmsResponse<String> process(String request) {
    String destination =
            request.startsWith("VIP:")
                    ? "orders.vip.replies"
                    : "orders.standard.replies";

    return JmsResponse.forQueue("ACK:" + request, destination);
}
```

This is a method in a Spring bean requiring `org.springframework.jms.listener.adapter.JmsResponse` and `JmsListener`. `JmsResponse` enables dynamic reply destinations while QoS remains on the listener's factory. With this approach, no fixed `@SendTo` is needed.

**Do not confuse** `JmsResponse<T>` with `QosSettings`: `JmsResponse` specifies **where to send**, whereas `QosSettings` specifies **with which QoS to send**.

### 7.3. Correlation ID

In Spring's default listener adapter reply mechanism, when building a reply, Spring typically sets the reply's `JMSCorrelationID` to the request's `JMSCorrelationID` if present; otherwise it may fall back to the request's `JMSMessageID`. The goal is helping clients match responses to requests.

`replyQosSettings` **does not set correlation IDs** and does not replace a request-reply correlation policy. For stable tracing across retries or multiple systems, include a business event/request ID rather than relying solely on JMS message IDs.

## 8. Queue/Topic for Replies Is a Separate Setting

The same name `"orders.responses"` can be treated by the provider as a **Queue** or a **Topic** depending on resolution settings.

- `pubSubDomain`: destination domain that the listener **consumes from**.
- `replyPubSubDomain`: domain used to **resolve response names** for the listener when using a dynamic resolver; when unset, it typically follows `pubSubDomain`.
- `replyQosSettings`: delivery mode, priority, and TTL of **the outgoing response message**.

These three settings are not interchangeable.

Example of a listener **consuming from a Queue while replying to a Topic** given proper naming/policies:

```java
var factory = new DefaultJmsListenerContainerFactory();
factory.setConnectionFactory(connectionFactory);
factory.setPubSubDomain(false);      // consume from Queue
factory.setReplyPubSubDomain(true);  // resolve reply name as Topic
factory.setReplyQosSettings(
        new QosSettings(DeliveryMode.PERSISTENT, 2, 10_000L)
);
```

This is a snippet **inside a configuration method with a `ConnectionFactory` bean**, requiring `DefaultJmsListenerContainerFactory`, `QosSettings`, and `DeliveryMode`. The listener's return value must have an eligible destination, and recipients must subscribe to that Topic. When `JMSReplyTo` is already a `Destination` object, that object's type determines the actual destination; `replyPubSubDomain` primarily affects name-based resolution.

Never toggle `setReplyPubSubDomain(true)` just hoping to raise priority; they are completely unrelated.

## 9. Reply QoS Differs from JmsTemplate Request QoS

Comparison table:

| Criterion | Request Sent via `JmsTemplate` | Reply Sent Automatically by `@JmsListener` |
| --- | --- | --- |
| Configuration point | `JmsTemplate` or `spring.jms.template.*` | `DefaultJmsListenerContainerFactory.setReplyQosSettings` |
| Container QoS | Does not inherit from listener factory | Yes, if listener uses configured factory |
| Priority | `template.setPriority(...)` plus explicit QoS | `QosSettings.setPriority(...)` |
| TTL | `template.setTimeToLive(...)` plus explicit QoS | `QosSettings.setTimeToLive(...)` |
| Delivery mode | `template.setDeliveryMode(...)` plus explicit QoS | `QosSettings.setDeliveryMode(...)` |
| Destination | Destination passed to `JmsTemplate` | `JmsResponse`, `JMSReplyTo`, `@SendTo` |
| When nothing is sent | Send not invoked | `void` listener method / no response |

Example configuring priority 8 and 5s TTL via Boot for requests, while replying with priority 2 and 10s TTL via the listener factory:

```yaml
spring:
  jms:
    template:
      priority: 8
      time-to-live: 5s
      qos-enabled: true
```

When a producer uses Boot's `JmsTemplate` to send a request, the request can carry the QoS above. When a listener configured with `replyQosFactory` returns a result, the reply is sent with the factory's **priority 2 / 10s TTL** settings—it does not "inherit" priority 8 / 5s TTL from the request.

**Do not confuse request TTL with reply timeout:** a request expiring before the listener receives it produces no reply. A reply sent with a 10-second TTL can still expire before the waiting client receives it, even after request processing finished.

## 10. Practical Impact of the Three QoS Parameters

### 10.1. Delivery Mode

`DeliveryMode.PERSISTENT` instructs the provider to ensure persistent delivery semantics per the JMS contract under supporting conditions. It suits critical replies that must not be lost across broker restarts, at the cost of extra I/O and potential transaction interaction.

`DeliveryMode.NON_PERSISTENT` can reduce overhead for ephemeral replies that are useless once a client cancels waiting or can retry; whether losing messages during broker failures is acceptable depends on the system.

Neither delivery mode alone guarantees **exactly once** or a combined database-and-JMS business transaction.

### 10.2. Priority

Priority is a scheduling hint among queued messages on the same broker/destination and **never guarantees strict ordering**. In request-reply, higher reply priority can help when a reply Queue builds a backlog, though prefetch and multiple consumers must always be tested.

`QosSettings.setPriority(2)` is an example from Spring documentation demonstrating effective configuration, **not a recommended default for every system**. Priority 9 is not an "execute immediately" switch and can starve lower-priority work in some setups.

### 10.3. Time-to-Live

Suppose a server sends a response at 10:00:00.000 with a 10,000 ms TTL:

```text
10:00:00.000 reply is sent
10:00:01.000 client receives -> valid
10:00:08.000 client receives -> valid
10:00:10.000 reply reaches expiration timestamp
10:00:12.000 client tries to receive -> reply may already be expired
```

These timestamps are illustrative; actual expiration handling depends on the JMS provider and broker clock/policies. `JMSExpiration` is an **absolute timestamp**, not "remaining ms." When TTL = 0, the expiration header is typically 0.

Choose TTL based on **how long the response remains useful**, backlogs, SLAs, and retry mechanics, not simply the listener's execution duration.

## 11. What If a Listener Sends Its Reply Manually Using JmsTemplate/MessageProducer?

Distinguish two reply paths:

**Path A — Spring sends automatically:**

```java
@JmsListener(
        destination = "demo.requests",
        containerFactory = "replyQosFactory"
)
@SendTo("demo.responses")
public String handle(String input) {
    return "ACK:" + input;
}
```

The `return` value is converted into a JMS message and sent by Spring. **`replyQosSettings` is applied** on this path.

**Path B — application sends manually:**

```java
@JmsListener(
        destination = "demo.requests",
        containerFactory = "replyQosFactory"
)
public void handle(String input) {
    myJmsTemplate.convertAndSend("demo.responses", "ACK:" + input);
}
```

In snippet B, `myJmsTemplate` is an injected bean and the method returns nothing. This send **follows `myJmsTemplate`'s QoS configuration** and does not pick up `replyQosSettings` from the listener's factory. You must configure `myJmsTemplate.setExplicitQosEnabled(true)`, `setPriority`, `setTimeToLive`, etc., or call `MessageProducer.send(..., mode, priority, ttl)` appropriately.

Similarly, if a listener implements `SessionAwareMessageListener` and creates a `MessageProducer` to call `send`, that code owns QoS and lifecycle; the listener adapter will not apply `replyQosSettings`.

**Avoid accidentally sending two replies:** if a method both manually calls `JmsTemplate.convertAndSend` and **returns a non-`void` value** handled by Spring, two separate responses can be emitted. Pick one reply model unless emitting two events is intentional.

## 12. Scoping Configuration Across Multiple Listeners

Multiple listeners can have differing reply QoS requirements:

- Business order-status listener: needs short-TTL replies because clients wait only a few seconds.
- Audit receipt listener: may need persistent delivery with a longer TTL.
- Consume-and-save-to-DB listener: produces no reply, so `replyQosSettings` has no direct effect.

Instead of forcing one config onto all listeners, define **multiple clearly named factories**:

```java
@Bean("fastReplyFactory")
DefaultJmsListenerContainerFactory fastReplyFactory(
        ConnectionFactory cf,
        DefaultJmsListenerContainerFactoryConfigurer configurer) {
    var f = new DefaultJmsListenerContainerFactory();
    configurer.configure(f, cf);
    f.setReplyQosSettings(
            new QosSettings(DeliveryMode.NON_PERSISTENT, 6, 3_000L));
    return f;
}

@Bean("durableReplyFactory")
DefaultJmsListenerContainerFactory durableReplyFactory(
        ConnectionFactory cf,
        DefaultJmsListenerContainerFactoryConfigurer configurer) {
    var f = new DefaultJmsListenerContainerFactory();
    configurer.configure(f, cf);
    f.setReplyQosSettings(
            new QosSettings(DeliveryMode.PERSISTENT, 4, 60_000L));
    return f;
}
```

These are **two illustrative bean methods inside a `@Configuration`**, needing the same imports as Section 5. Then use:

```java
@JmsListener(
        destination = "billing.fast.requests",
        containerFactory = "fastReplyFactory")
@SendTo("billing.fast.replies")
public String fastResponse(String payload) {
    return "ACK:" + payload;
}
```

If `containerFactory` is omitted, Spring uses the default factory (typically named `jmsListenerContainerFactory`) rather than guessing which bean has the "right" QoS. If multiple `ConnectionFactory` beans exist, use `@Qualifier` to avoid pointing at the wrong provider.

Never mutate `new QosSettings()` priority at runtime per request on a shared listener container: this configuration is meant to be set before the container starts. If individual replies need dynamic per-business QoS, consider sending explicitly via a dedicated publisher or configuring separate listeners/factories.

## 13. Common Errors and Confusing Scenarios

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| No reply sent | `void` method or no response destination. | Check return type, `JMSReplyTo`, `@SendTo`, Queue/Topic. |
| Reply arrives with default priority | Listener runs on a different factory; missing `setReplyQosSettings`. | Inspect `containerFactory` and the resolved bean. |
| Set `spring.jms.template.priority=8` yet replies stay priority 4 | That property applies to `JmsTemplate`, not listener auto-replies. | Configure `replyQosSettings` on the listener factory. |
| Reply has priority 2 while request had priority 8 | Both messages have independent QoS. | Inspect request and reply headers separately. |
| Reply vanishes after a few seconds | TTL too short or client arrived past `JMSExpiration`. | Check `JMSExpiration`, queue backlog, clocks, and TTL policy. |
| Reply lands in a destination other than `@SendTo` | Request set `JMSReplyTo`; or listener returned `JmsResponse`. | Inspect request headers and destination selection logic. |
| Reply sent yet not visible on Queue | Wrong Queue/Topic domain or broker auto-create/ACL issue. | Check `replyPubSubDomain`, resolver, and destination mapping. |
| `replyQosFactory` config has no effect | `@JmsListener` omitted `containerFactory="replyQosFactory"`. | Verify exact bean name and startup logs. |
| Reply is not persistent as expected | Provider/broker policy or manual send via another template. | Inspect `JMSDeliveryMode` on the reply, broker, and send path. |
| Flaky test passes intermittently | Concurrency, prefetch, retries, stale broker backlog, or expired reply. | Use clean Queues, single consumer, adequate TTL, and assert headers. |
| Reply sent twice | Code both sent manually via template and returned a value for Spring auto-reply. | Pick a single reply path. |
| Listener throws after side effects | Request ACK/transaction/retry and reply send are inconsistent. | Design transactions, idempotency, and integration tests. |

### What Does `setReplyQosSettings(null)` Mean?

In Spring, when `replyQosSettings` is `null`, the reply mechanism uses **JMS producer/provider defaults**, which may be configured on the broker/application server. Never read that as "forced priority=0" or "forced TTL=0" in every runtime.

If you want fixed reply QoS, pass a non-null `QosSettings`; if you want administered defaults, leave it null and document expectations with integration tests.

## 14. Relationship to Transactions, ACK, Redelivery, and Client Timeouts

### 14.1. QoS Does Not Guarantee Request-Reply Exactly-Once

`DeliveryMode.PERSISTENT` and a 10-second TTL do not guarantee a client receives **exactly one reply**. A listener can process a request, send a response, and then fail during transaction/ACK; the broker redelivers the request and the app may emit another reply. A producer can also retry on network error without knowing whether the prior send reached the broker.

Robust designs typically include request IDs/correlation IDs, processing-side idempotency, client timeouts, retry/backoff policies, and (where needed) an appropriate transaction manager. When combining JMS with a database, verify actual atomicity or use a transactional outbox/inbox; never infer from QoS that DB and broker commit together.

### 14.2. Reply TTL vs. Client Wait Time

| Concept | Where Set | When Does It Start? |
| --- | --- | --- |
| Request TTL | Producer sending request | When the request is sent. |
| Reply TTL | `replyQosSettings.setTimeToLive(...)` | When the listener sends the reply. |
| Client receive timeout | `JmsTemplate.receiveTimeout` or request-reply API | How long the client thread waits for a response. |
| Server processing timeout | Business logic / orchestrator | Request processing duration, not a JMS QoS property. |

For example, if a client waits only 2 seconds while the listener takes 4 seconds to process: even if the reply has a 10-second TTL upon send, the client may **already have timed out before the reply is sent**. The response still being alive on the broker does not mean the client will process it.

Conversely, if a client waits 30 seconds while reply TTL is 5 seconds and broker backlog causes the reply to expire, the client still receives nothing.

### 14.3. Transactions on the Listener Container

When a listener container uses transacted sessions, request ACKing and reply sending can be governed by that transaction depending on the adapter and broker/JTA setup. However, QoS settings **do not enable transactions** and do not automatically fold external side effects (databases, HTTP) into one transaction. Verify `sessionTransacted`, `transactionManager`, and rollback/redelivery behavior in your deployment environment.

## 15. Meaningful Testing

Never assert only `getReplyQosSettings().getPriority() == 2` and consider the system verified; that only checks the bean property, **not that the auto-reply path actually applied it**.

### 15.1. Configuration Unit Tests

Verify `replyQosFactory` is created and the listener specifies `containerFactory="replyQosFactory"`. If testing annotation mapping directly, confirm the handler has a return value and valid destination. Such unit tests catch bean-name typos but do not replace broker tests.

### 15.2. Integration Tests with a Real Broker

1. Spin up a test broker and provision request/reply Queues with a single reply consumer.
2. Send a request without `JMSReplyTo`; verify the response appears on `@SendTo`.
3. Read the raw JMS response and assert `getJMSPriority()==2`, `getJMSDeliveryMode()==DeliveryMode.PERSISTENT`, and `getJMSExpiration()>0` when TTL is positive.
4. Send a request with a custom `JMSReplyTo`; verify that destination takes precedence while reply QoS still matches config.
5. Test a short TTL with controlled delay and verify expiration per broker policy. Never rely on arbitrary `Thread.sleep` calls to claim real-time guarantees.
6. Test `void` listeners and manual `JmsTemplate` replies to confirm `replyQosSettings` is not mistakenly expected on non-auto-reply paths.
7. Test redelivery when a listener throws/rolls back, and test correlation IDs under concurrent requests.

If tests are sensitive to broker clocks, queue backlogs, or concurrency, collect headers, logs, message IDs, and business request IDs; avoid blaming Spring for flaky tests before pinpointing the failure.

### 15.3. Operational Monitoring

Track sent response counts, queue depths, expired replies, request processing latency, client reply receive latency, retries, DLQs, and consumer errors. Never log full reply payloads if they contain PII/tokens. Trace standardized correlation IDs and mask sensitive data.

## 16. Practice Exercises

**Exercise 1.** A listener has `@SendTo("q.response")` and returns a `String`, while the request sets `JMSReplyTo=q.client`. Where is the response sent under default behavior?

**Answer:** `q.client` via `JMSReplyTo`, not `q.response`. If the listener returns a `JmsResponse` specifying a destination, evaluate that choice first.

**Exercise 2.** `QosSettings` has priority=2 and TTL=10,000 ms. Is this the QoS of the request or the reply when set via `factory.setReplyQosSettings(qos)`?

**Answer:** The QoS of **the reply automatically sent by Spring** from listener containers created by that factory; it does not affect the request.

**Exercise 3.** Why can you not rely on `jmsTemplate.setPriority(9)` to conclude a `@JmsListener`'s auto-reply has priority 9?

**Answer:** `JmsTemplate` and listener auto-reply are two distinct send paths. The listener needs `replyQosSettings` on the right factory unless application code manually uses that template to send the reply.

**Exercise 4.** A request takes 8 seconds to process, and the response is sent with TTL=10 seconds. Does the response expire 2 seconds later because the request took 8 seconds?

**Answer:** No. Reply TTL starts when **the reply is sent**, so in principle it still has ~10 seconds from send time, regardless of the 8-second request processing time.

**Exercise 5.** If a listener returns `void` and manually sends a message via `myJmsTemplate.convertAndSend(...)`, does `setReplyQosSettings` override `myJmsTemplate`?

**Answer:** No. Manual sends follow `myJmsTemplate` or the direct `MessageProducer`'s configuration.

**Exercise 6.** When needing to reply to a Topic while the listener consumes requests from a Queue, which setting controls the domain and which controls priority?

**Answer:** `setReplyPubSubDomain(true)` controls **the domain for resolving reply names**, and `QosSettings.setPriority(...)` controls **reply send priority**. The two settings are independent.

**Exercise 7.** Does `DeliveryMode.PERSISTENT` plus a long TTL guarantee the system receives and processes each reply exactly once?

**Answer:** No. You must also account for ACK/transactions, client timeouts, redeliveries, duplicates, and idempotency.

## 17. Official References

- [Spring Framework – Annotation-driven Listener Endpoints, Response Management section](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)
- [Spring Framework 6.2 – DefaultJmsListenerContainerFactory](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html)
- [Spring Framework 6.2 – AbstractJmsListenerContainerFactory.setReplyQosSettings](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/AbstractJmsListenerContainerFactory.html)
- [Spring Framework 6.2 – QosSettings](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/QosSettings.html)
- [Spring Framework 6.2 – AbstractMessageListenerContainer](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
- [Spring Framework 6.2 – AbstractAdaptableMessageListener](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/listener/adapter/AbstractAdaptableMessageListener.html)
- [Spring Boot – Messaging with JMS (listener factory configuration guide)](https://spring.io/guides/gs/messaging-jms/)
- [Spring Boot – Common Application Properties](https://docs.spring.io/spring-boot/3.3/reference/application-properties.html)
- [Jakarta Messaging 3.1 – MessageProducer and JMS message headers](https://jakarta.ee/specifications/messaging/3.1/)

**Takeaway:** When a `@JmsListener` returns a value and has a valid reply destination, **Spring can automatically build and send a reply**. To control **that reply's delivery mode, priority, and TTL**, configure `QosSettings` via **`DefaultJmsListenerContainerFactory.setReplyQosSettings(...)`** on the exact factory used by the listener. Never confuse reply QoS with `JmsTemplate` request QoS, destination selection via `JMSReplyTo/@SendTo`, or system-wide transaction/idempotency requirements.
