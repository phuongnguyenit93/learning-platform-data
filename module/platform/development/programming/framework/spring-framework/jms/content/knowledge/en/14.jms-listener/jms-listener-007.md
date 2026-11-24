# Using Placeholders and Controlled Configuration Expressions in @JmsListener

## 1. Context: Listeners Need Config Changes Without Code Changes

In a Spring JMS application, a message-receiving method is typically declared with an annotation:

~~~java
@JmsListener(destination = "orders.in")
public void handle(String payload) {
    // Process an order.
}
~~~

The code works, yet local, test, staging, and production environments often have different destinations. Sometimes the broker must filter messages by event type, tenant, or schema; or consumer counts need adjusting per infrastructure. You should not edit a Java class every time a Queue name or concurrency level changes.

`@JmsListener` supports **configuration values resolved at startup**:

- **Property placeholder**: `${app.jms.orders-queue}` fetches a value from the Spring Environment.
- **SpEL (Spring Expression Language)**: `#{@routingPolicy.ordersDestination()}` evaluates an expression against a Spring-managed bean.
- **Listener container factory**: holds transaction, connection, converter, default concurrency, and recovery settings.
- **Bean/config validation**: validates destination names, selector values, consumer counts, and allowed environments before use.

Example configuration via properties:

~~~java
@JmsListener(
        id = "ordersListener",
        destination = "${app.jms.orders-queue}",
        selector = "${app.jms.order-selector}",
        concurrency = "${app.jms.listener-concurrency}")
public void onOrder(String body) {
    // Process matching message.
}
~~~

~~~properties
app.jms.orders-queue=orders.in
app.jms.order-selector=eventType = 'order.created' AND region = 'VN'
app.jms.listener-concurrency=1
~~~

A single Java artifact can be deployed in multiple environments; actual values live in controlled per-environment configuration.

**Important limitation:** annotation values are resolved by Spring when the listener endpoint is discovered/registered and the container is created. They are **not** re-evaluated per incoming message, nor do they automatically update if an external config file is edited while the application is running.

### Lesson Objectives

After this lesson, you will be able to:

1. Know which `@JmsListener` attributes should be externalized.
2. Distinguish `${...}` (property placeholder), `#{...}` (SpEL), and JMS selector expressions.
3. Use required placeholders, defaults, and profiles/environments without accidentally listening to the wrong Queue.
4. Understand SpEL limitations, validate configuration inputs, and prevent selector injection.
5. Build a Java 17 + Spring Boot 3.x + ActiveMQ Artemis example to verify a selector through a real listener.
6. Test, monitor, and deploy safely when changing destinations, selectors, or concurrency.

## 2. Attributes of @JmsListener

According to Spring Framework 6.1 Javadoc, `@JmsListener` has one required String attribute `destination` and optional String attributes:

| Attribute | Meaning | Example |
| --- | --- | --- |
| `destination` | JMS destination name, processed via the container's DestinationResolver | `${app.jms.orders-queue}` |
| `selector` | JMS message selector expression | `${app.jms.order-selector}` |
| `concurrency` | Concurrent consumer limits for the endpoint | `${app.jms.listener-concurrency}` |
| `id` | Unique ID of the listener endpoint/container | `ordersListener` |
| `containerFactory` | Bean name of JmsListenerContainerFactory | `ordersContainerFactory` |
| `subscription` | Subscription name (usually related to Topic/durable subscriptions) | `ordersEventsSubscription` |

`containerFactory` must point to an existing bean. If omitted, Spring typically looks up the default factory named `jmsListenerContainerFactory`, unless another default is configured. `subscription` is not an arbitrary way to name a Queue; it belongs to Topic subscription models.

Example illustrating multiple attributes:

~~~java
@JmsListener(
        id = "ordersListener",
        destination = "${app.jms.orders-queue}",
        selector = "${app.jms.order-selector}",
        concurrency = "${app.jms.listener-concurrency}",
        containerFactory = "ordersContainerFactory")
public void receive(String body) {
    // ...
}
~~~

This snippet requires a bean named `ordersContainerFactory`. Do not use it in the sample project below because the sample leverages the listener factory auto-configured by Spring Boot.

Things that are **not** `@JmsListener` attributes: broker URL, username/password, TLS, pool settings, converter, transaction manager, acknowledge mode, recovery backoff, and resource lifecycle. Those belong to `ConnectionFactory`, container factories, Spring Boot properties, or infrastructure beans.

~~~text
Spring Environment
  |
  +-- destination property ----+
  +-- selector property -------+----> @JmsListener endpoint
  +-- concurrency property ----+          |
  |                                       v
  +-- Artemis connection configuration  ListenerContainerFactory
                                          |
                                          v
                                    Listener container
                                          |
                                          v
                                    JMS provider/broker
                                          |
                                          v
                                      handler method
~~~

## 3. Placeholders: Fetching Strings from the Spring Environment

Spring resolves placeholders with `${property.name}` syntax. You can declare a fallback `${property.name:defaultValue}`.

~~~java
// Property configuration is required:
@JmsListener(destination = "${app.jms.orders-queue}")
public void handle(String body) { }
~~~

~~~java
// With fallback for local demo:
@JmsListener(destination = "${app.jms.orders-queue:orders.demo}")
public void handleDemo(String body) { }
~~~

These are **two separate options**; do not put both in the same production application unless you want two consumers.

### 3.1. When Should Default Values Be Used?

Fallbacks suit tutorials or non-critical settings. However, for a production destination, an unnoticed fallback can lead to a dangerous error: the application forgets to set a property and silently listens to `orders.demo` or routes data to the wrong environment.

**Recommendation:** Queue/Topic names, tenant routing parameters, credentials, and critical broker choices should require explicit validated configuration. Do not add defaults just so an app starts without essential config.

### 3.2. @Value Differs from Placeholders in Annotations

Java does not allow an annotation to directly reference an instance field that is not a constant expression:

~~~java
// INVALID if ordersQueue is a runtime variable:
@JmsListener(destination = ordersQueue)
public void handle(String payload) { }
~~~

However, a String literal containing a placeholder is valid in Java source:

~~~java
@JmsListener(destination = "${app.jms.orders-queue}")
public void handle(String payload) { }
~~~

Reason: the Java compiler sees only a String literal, while Spring resolves its contents at runtime. `@Value("${...}")` can inject a value into a field or constructor, but it does not turn a runtime field into a compile-time constant for annotations.

### 3.3. Property Sources and Precedence

In Spring Boot, the Spring Environment combines sources such as:

- `application.properties` or `application.yml`.
- Profile-specific files, e.g., `application-dev.properties`.
- Environment variables supplied by the container/orchestrator.
- Command-line arguments at startup.
- Other config sources registered by the app and deployment.

Sources have specific precedence rules per Boot version; do not assume a file always beats every environment variable. In production, observe the **effective resolved values** of non-sensitive keys at startup rather than trusting a file opened manually.

Example:

~~~properties
# application-dev.properties
app.jms.orders-queue=orders.dev.in
app.jms.order-selector=eventType = 'order.created' AND region = 'VN'
app.jms.listener-concurrency=1
~~~

~~~properties
# application-prod.properties
app.jms.orders-queue=orders.prod.in
app.jms.order-selector=eventType = 'order.created' AND region = 'VN'
app.jms.listener-concurrency=2-6
~~~

The two blocks are **two separate files**, merely illustrating a profile-based configuration strategy. Do not paste both blocks with duplicate keys into the same file expecting Spring to guess which value to use.

## 4. SpEL: Expressions Evaluated by Spring at Endpoint Registration

SpEL uses `#{...}` syntax. With `@JmsListener`, a common example is retrieving Queue names and selectors from a bean **controlled by application code**:

~~~java
@JmsListener(
        destination = "#{@ordersRouting.destination()}",
        selector = "#{@ordersRouting.selector()}")
public void handle(String body) {
    // ...
}
~~~

Corresponding bean:

~~~java
import org.springframework.stereotype.Component;

@Component("ordersRouting")
public class OrdersRouting {
    public String destination() {
        return "orders.in";
    }

    public String selector() {
        return "eventType = 'order.created' AND region = 'VN'";
    }
}
~~~

Spring resolves both expressions to obtain Strings before registering the container. The broker only sees the **resolved** destination name and selector.

Distinction:

| Form | Who evaluates | When |
| --- | --- | --- |
| `${app.jms.orders-queue}` | Spring Environment | When resolving listener configuration |
| `#{@ordersRouting.destination()}` | Spring SpEL/BeanFactory | When processing annotations |
| `region = 'VN' AND eventType = 'order.created'` | JMS provider | When the consumer selects messages by metadata |
| `$.region` | JSONPath parser, if used by app | Not a JMS selector mechanism |
| `order.region().equals("VN")` | Java business code | After the message is converted to an object |

**Do not** write:

~~~java
// WRONG IDEA: There is no incoming "payload" at annotation resolution time.
@JmsListener(
        destination = "orders.in",
        selector = "#{payload.region == 'VN'}")
public void handle(String payload) { }
~~~

If you want to filter by region **per message**, the producer must set a `region` JMS property and the listener uses JMS selector `region = 'VN'`. Annotation SpEL cannot inspect individual message payloads before the broker delivers messages.

### 4.1. When Is SpEL Truly Needed?

SpEL is useful when the application has a **trusted config policy bean**, for example:

- Choosing a destination from a predefined list and checking naming conventions.
- Computing a selector from a fixed per-deployment tenant allowlist.
- Synchronizing Queue names between listeners and infrastructure beans.
- Supplying a configuration value from a service validated/normalized at startup.

For simple values already in the environment, `${...}` is usually simpler, easier to audit, and easier to test.

### 4.2. Never Let External Users Define SpEL

SpEL can access beans and methods depending on the evaluation context. Never take a String from an HTTP request or untrusted data source and evaluate it as a SpEL expression in the application context.

**Good:** expressions live in reviewed source code; beans perform bounded selections and return validated Strings.

**Bad:** accepting an entire expression as a client-supplied parameter and letting it access the BeanFactory or arbitrary classes/methods.

SpEL is not a sandbox for untrusted input. For truly dynamic parameters, use a validated data structure, an allowlist, or an explicit configuration object instead of expression execution.

## 5. JMS Selectors: Different Expressions from SpEL

After resolving `selector`, the container passes a String to the JMS provider. This String must follow the **JMS message selector grammar** (a subset of SQL-92).

Example:

~~~properties
app.jms.order-selector=eventType = 'order.created' AND region = 'VN'
~~~

Selectors pick messages based on **JMS headers and properties**, not by querying a JSON body. The producer must set the right JMS properties:

~~~java
jmsTemplate.convertAndSend("orders.in", "ORDER|O-42", message -> {
    message.setStringProperty("eventType", "order.created");
    message.setStringProperty("region", "VN");
    return message;
});
~~~

The expression:

~~~sql
eventType = 'order.created' AND region = 'VN'
~~~

is a valid JMS selector. However:

~~~sql
WHERE body.region = 'VN'
JSON_VALUE(body, '$.region') = 'VN'
~~~

are not standard JMS selectors. The broker does not automatically deserialize JSON bodies to search for `region`.

### 5.1. Limits and Property Types

- `setIntProperty("amount", 150)` creates a numeric property; `amount >= 100` is a numeric comparison.
- `setStringProperty("amount", "150")` creates a String; selectors do not coerce it to a number in the same expression.
- Missing properties turn many comparisons into `UNKNOWN`; only `TRUE` results match.
- `status <> 'CANCELLED'` does not match messages missing `status`; to include messages lacking the property, use `status IS NULL OR status <> 'CANCELLED'`.
- String literals use single quotes; escape a single quote with **two single quotes**.

**Never** treat a syntactically valid selector as proof of tenant authorization. JMS selectors only filter delivery, whereas broker ACLs and destination isolation govern what data a consumer is allowed to access.

### 5.2. Be Careful with Selectors Built from Dynamic Input

Wrong:

~~~java
String selector = "tenant = '" + tenantFromHttpRequest + "'";
~~~

If a client supplies single quotes, operators, or special characters, the expression can alter logic or become invalid. Beyond syntax issues, a client could select an unauthorized tenant.

A minimal builder needs an allowlist:

~~~java
import java.util.Set;

public final class TenantSelectorPolicy {
    private static final Set<String> ALLOWED = Set.of("vn", "sg");

    public static String forTenant(String tenant) {
        if (!ALLOWED.contains(tenant)) {
            throw new IllegalArgumentException("Tenant not allowed");
        }
        return "eventType = 'order.created' AND tenant = '" + tenant + "'";
    }
}
~~~

This is an illustrative Java class independent of the sample project below. Because it only permits `vn` or `sg`, it cannot accept arbitrary selector strings. When free-form String literals are required, validate and escape single quotes per JMS grammar, though **quote escaping does not replace authorization**.

If the tenant needs to vary per incoming message, do not mutate annotation SpEL at runtime; design routing, fixed per-consumer selectors, or a dedicated subscription/endpoint registration mechanism with a clear lifecycle.

## 6. Concurrency, containerFactory, and Topic Choices

The `concurrency` attribute is a String configuring consumer limits according to the underlying container's capabilities. Example:

~~~java
@JmsListener(
        destination = "${app.jms.orders-queue}",
        concurrency = "${app.jms.listener-concurrency}")
public void handle(String payload) { }
~~~

~~~properties
app.jms.listener-concurrency=2-6
~~~

With `DefaultMessageListenerContainer`, this represents a minimum/maximum consumer range. Other containers may not fully support dynamic scaling. Do not read `2-6` as Spring always spinning up six threads or guaranteeing message ordering. Multiple consumers on a Queue process in parallel and can change observed completion order.

When configuring concurrency on `DefaultJmsListenerContainerFactory`:

~~~java
// Snippet inside a @Configuration class:
@Bean
DefaultJmsListenerContainerFactory ordersContainerFactory(
        ConnectionFactory connectionFactory) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("1-4");
    return factory;
}
~~~

Requires importing `jakarta.jms.ConnectionFactory`, `org.springframework.context.annotation.Bean`, and `org.springframework.jms.config.DefaultJmsListenerContainerFactory`. Only annotations with `containerFactory = "ordersContainerFactory"` choose this bean. `concurrency` on the annotation can override the factory value for an individual endpoint.

Consider before raising concurrency:

- Does the broker have sufficient connection/session/consumer capacity?
- Can the DB connection pool and external API rate limits handle the load?
- Does the singleton handler hold shared mutable state that could cause race conditions?
- Does business logic require ordering by a key?
- How are transaction rollback, redelivery, and idempotency designed?

`subscription` relates to Topics, not a Queue naming shortcut. For durable Topic subscriptions, client IDs and selectors must be managed carefully; changing selectors or subscription names can affect retained messages. Never use placeholders that randomly change subscription IDs on every deploy.

## 7. Startup-Time Resolution and Runtime Changes

In Spring's `JmsListenerAnnotationBeanPostProcessor` source, annotation attributes such as `destination`, `selector`, `subscription`, `concurrency`, `containerFactory`, and `id` are resolved during endpoint registration.

~~~text
Startup:
  Spring Environment / bean factory ready
    -> find @JmsListener
    -> resolve placeholders and SpEL
    -> register endpoint with concrete destination/selector/concurrency
    -> create listener container
    -> connect to JMS provider and start consumer

When a message arrives:
  Broker applies configured JMS selector
    -> invoke method if message matches

When config file is edited while app is running:
  Does not automatically update selector/Queue of existing consumer
~~~

To change destination/selector/concurrency, normally deploy the new config and perform a controlled restart/rolling update. For dynamic endpoint registration, use official lifecycle APIs synchronized with the broker; merely editing `application.properties` does not recreate consumers.

### 7.1. Using id to Manage Listeners

With an annotation:

~~~java
@JmsListener(
        id = "ordersListener",
        destination = "${app.jms.orders-queue}")
public void handle(String payload) { }
~~~

You can look up the container via `JmsListenerEndpointRegistry`:

~~~java
// Snippet inside a bean with injected registry:
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");
if (container != null) {
    container.stop();
}
~~~

Requires importing `org.springframework.jms.config.JmsListenerEndpointRegistry` and `org.springframework.jms.listener.MessageListenerContainer`. `stop()` manages lifecycle; it does **not** force annotations to re-resolve new values. Starting after stopping reuses the already configured endpoint/container unless you perform valid reconfiguration.

### 7.2. autoStartup Is Not an Annotation Attribute

Spring Boot provides:

~~~properties
spring.jms.listener.auto-startup=true
~~~

to control the default for containers managed by auto-configuration. Spring Framework 6.1's `@JmsListener` has no String attribute named `autoStartup`. If you need to keep a listener stopped on deployment, configure `autoStartup` on the factory or control the registry appropriately; do not add `autoStartup` to the annotation expecting Java to compile.

## 8. Runnable Project: Spring Boot 3.3 + Artemis + @JmsListener with Placeholders

The example sends **two messages** to a lab Queue:

- `ORDER|O-42` with `eventType=order.created` and `region=VN`: received by the listener.
- `ORDER|O-43` with `eventType=order.created` and `region=US`: does not match the listener, remains receivable by another consumer.
- A `CommandLineRunner` verifies the handler ran, then retrieves the `US` message using `JmsTemplate.receiveSelectedAndConvert`.

### 8.1. Starting the Lab Broker

Requires Docker:

~~~bash
docker run --detach --rm --name artemis-listener-config -p 127.0.0.1:61616:61616 -p 127.0.0.1:8161:8161 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest
~~~

Wait for the broker to become ready via `docker logs artemis-listener-config`. Credentials `demo/demo` are only for local use. If the broker does not auto-create Queues, pre-create the Queue and grant permissions. Use a dedicated Queue or clear old messages in the lab environment to ensure clean results.

### 8.2. Project Structure

~~~text
jms-listener-config/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/demo/jms/
    ListenerConfigApplication.java
    FilteredOrderListener.java
    DemoPublisher.java
  src/test/java/demo/jms/
    FilteredOrderListenerTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-listener-config'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Versions are pinned to illustrate a consistent API set, not necessarily the latest maintenance release. Use JDK 17+ and a Gradle 8.x version compatible with the plugin. Spring Boot 3 uses `jakarta.jms`, not legacy `javax.jms`.

### 8.3. application.properties

File `src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_BROKER_USER:demo}
spring.artemis.password=${JMS_BROKER_PASSWORD:demo}
spring.jms.pub-sub-domain=false
spring.jms.template.receive-timeout=2s

app.jms.orders-queue=${JMS_DEMO_QUEUE:orders.listener.config.demo}
app.jms.order-selector=eventType = 'order.created' AND region = 'VN'
app.jms.listener-concurrency=1
~~~

Real Spring placeholders start with a dollar sign and curly braces; the lines above use that exact syntax when saved. `spring.jms.template.receive-timeout=2s` only bounds **JmsTemplate synchronous receives**, not `@JmsListener` callback timeouts. In production, remove the `demo` fallbacks for username/password and use secret injection.

### 8.4. Main Class

File `src/main/java/demo/jms/ListenerConfigApplication.java`:

~~~java
package demo.jms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class ListenerConfigApplication {
    public static void main(String[] args) {
        SpringApplication.run(ListenerConfigApplication.class, args);
    }
}
~~~

`@EnableJms` enables `@JmsListener` method processing. When the Artemis starter and connection configuration are complete, Spring Boot can auto-configure `ConnectionFactory`, `JmsTemplate`, and the default listener factory.

### 8.5. Listener with Selector Read from Properties

File `src/main/java/demo/jms/FilteredOrderListener.java`:

~~~java
package demo.jms;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class FilteredOrderListener {

    private final CountDownLatch received = new CountDownLatch(1);
    private final AtomicReference<String> lastBody =
            new AtomicReference<>();

    @JmsListener(
            id = "ordersListener",
            destination = "${app.jms.orders-queue}",
            selector = "${app.jms.order-selector}",
            concurrency = "${app.jms.listener-concurrency}")
    public void onOrder(String body) {
        lastBody.set(body);
        System.out.println("MATCHED=" + body);
        received.countDown();
    }

    public boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return received.await(timeout, unit);
    }

    public String lastBody() {
        return lastBody.get();
    }
}
~~~

Once resolved, the annotation has values:

~~~text
id          = ordersListener
destination = orders.listener.config.demo
selector    = eventType = 'order.created' AND region = 'VN'
concurrency = 1
~~~

`CountDownLatch` only lets the demo program know the handler was invoked. It does not prove broker ACK, DB commit, or guarantee exactly-once. In production, handlers are usually stateless and need idempotency if a message can be redelivered.

### 8.6. Producer and Checking Non-Matching Messages

File `src/main/java/demo/jms/DemoPublisher.java`:

~~~java
package demo.jms;

import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
public class DemoPublisher implements CommandLineRunner {

    private final JmsTemplate template;
    private final FilteredOrderListener listener;
    private final String queue;

    public DemoPublisher(
            JmsTemplate template,
            FilteredOrderListener listener,
            @Value("${app.jms.orders-queue}") String queue) {
        this.template = template;
        this.listener = listener;
        this.queue = queue;
    }

    @Override
    public void run(String... args) throws Exception {
        template.convertAndSend(queue, "ORDER|O-42", message -> {
            message.setStringProperty("eventType", "order.created");
            message.setStringProperty("region", "VN");
            return message;
        });

        template.convertAndSend(queue, "ORDER|O-43", message -> {
            message.setStringProperty("eventType", "order.created");
            message.setStringProperty("region", "US");
            return message;
        });

        boolean invoked = listener.await(10, TimeUnit.SECONDS);
        System.out.println("HANDLER_INVOKED=" + invoked);

        Object remaining = template.receiveSelectedAndConvert(
                queue, "region = 'US'");
        System.out.println("OTHER_MESSAGE=" + remaining);
    }
}
~~~

The producer sends a Java String, and Spring's default converter turns it into a JMS TextMessage. `eventType` and `region` are separate **JMS properties**, not JSON body fields. The `ordersListener` only matches region `VN`, while `receiveSelectedAndConvert` uses a separate selector to retrieve the `US` message.

With a clean lab Queue, this example is reproducible. If the broker has leftover messages or other competing consumers on the same Queue, results may differ. Set the `JMS_DEMO_QUEUE` environment variable to a fresh test Queue name per run to minimize interference. Never use a production Queue for practice exercises.

### 8.7. Running and Expected Stdout

~~~bash
gradle test
gradle bootRun
~~~

When the broker, credentials, ACLs, and Queue are valid, the three lines printed by the code itself are:

~~~text
MATCHED=ORDER|O-42
HANDLER_INVOKED=true
OTHER_MESSAGE=ORDER|O-43
~~~

Spring/Artemis/Gradle startup logs may interleave. `HANDLER_INVOKED=true` is printed after the listener calls `CountDownLatch.countDown()`; it does not prove the final JMS commit. If lab prerequisites are not met, you may see a timeout or exception instead of the three lines above.

Clean up:

~~~bash
docker stop artemis-listener-config
~~~

## 9. Unit Tests, Context Tests, and Integration Tests

### 9.1. Unit Testing the Business Method

File `src/test/java/demo/jms/FilteredOrderListenerTest.java`:

~~~java
package demo.jms;

import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FilteredOrderListenerTest {

    @Test
    void storesHandledMessage() throws InterruptedException {
        FilteredOrderListener listener =
                new FilteredOrderListener();

        listener.onOrder("ORDER|O-42");

        assertTrue(listener.await(100, TimeUnit.MILLISECONDS));
        assertEquals("ORDER|O-42", listener.lastBody());
    }
}
~~~

`gradle test` runs pure Java tests without needing a broker. The test verifies the handler, yet **does not** prove annotation placeholders resolved or that Artemis evaluates the selector properly. That is the responsibility of integration tests.

### 9.2. Checking the Registry After Context Startup

From a Spring test/infrastructure with `JmsListenerEndpointRegistry` injected:

~~~java
// Snippet inside a test importing JUnit assertNotNull:
var container =
        registry.getListenerContainer("ordersListener");
assertNotNull(container);
~~~

A container existing does not prove it connected to the broker successfully. Combine with state/`isRunning`, broker consumer counts, and real matching/non-matching message tests.

### 9.3. Testing Against a Real Broker

An integration test suite should verify:

1. Missing required destination property causes deployment configuration failure.
2. Placeholders are overridden by profiles or env vars matching the deployment.
3. The listener receives only messages with `eventType=order.created` and `region=VN`.
4. Messages with `region=US` do not enter the listener but remain eligible for another Queue consumer.
5. Messages lacking `region` do not match because comparisons yield UNKNOWN.
6. Producers setting the wrong property type are not coerced as hoped.
7. Syntactically invalid selectors are caught by the broker/provider; observe appropriate logs/errors.
8. Out-of-bounds concurrency values are blocked in CI/config review.
9. Changing properties at runtime is not mistaken for updating a live container.
10. Transaction rollback/redelivery and duplicates are handled per business policy.

Mockito does not run a JMS selector engine. To verify selectors, use a real Artemis instance or a broker spun up via Testcontainers; avoid testing against production.

## 10. Controlling Configuration: Naming, Allowlists, and Security

Property placeholders merely return Strings. They do not validate Queue names, selectors, or consumer counts.

### 10.1. Validating Destinations via a Policy Bean

One approach when naming conventions are fixed:

~~~java
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component("safeOrdersRoute")
public class SafeOrdersRoute {

    private static final Pattern VALID =
            Pattern.compile("[A-Za-z0-9._-]{1,80}");

    private final String destination;

    public SafeOrdersRoute(
            @Value("${app.jms.orders-queue}") String destination) {
        if (!VALID.matcher(destination).matches()) {
            throw new IllegalArgumentException(
                    "Invalid destination configuration");
        }
        this.destination = destination;
    }

    public String destination() {
        return destination;
    }
}
~~~

You can then use **an alternative option** in the listener:

~~~java
@JmsListener(destination = "#{@safeOrdersRoute.destination()}")
public void onMessage(String payload) { }
~~~

This snippet is a separate alternative; do **not** add it simultaneously to the lab project unless you intend to create a second listener. Regex only checks format and cannot tell whether the Queue is permitted by ACLs. Production must still verify destination ownership and broker permissions.

### 10.2. Disallow Arbitrary containerFactory Selection

If using:

~~~java
@JmsListener(
        destination = "${app.jms.orders-queue}",
        containerFactory = "ordersContainerFactory")
public void onOrder(String payload) { }
~~~

then the `ordersContainerFactory` bean must exist and have proper transaction/ACK/recovery policies. Never accept an arbitrary bean name from external users to choose the listener container type or silently swap transaction policies.

### 10.3. Secret Management

Usernames, passwords, and TLS keys do not belong in annotations:

~~~properties
spring.artemis.user=${JMS_BROKER_USER}
spring.artemis.password=${JMS_BROKER_PASSWORD}
~~~

In production, property sources must be managed securely. Never print passwords when logging "resolved configuration"; never pass secrets via JMS headers/properties or embedded SpEL.

### 10.4. Do Not Treat Selectors as ACLs

A selector like `tenant = 'vn'` only filters delivery for a consumer. If the service account holds broad permissions on the broker, changing a selector could expose another tenant's data. Enforce per-destination consume permissions, isolate tenants where required, and audit configurations before deployment.

## 11. Failure Modes to Distinguish

| Symptom | Failure Boundary | Resolution |
| --- | --- | --- |
| Cannot resolve `${app.jms.orders-queue}` | Spring Environment/config | Declare property properly, remove unsafe fallbacks |
| SpEL bean/method does not exist | BeanFactory/SpEL | Fix expression/bean, test context |
| Wrong `containerFactory` name | Spring bean registration | Use an existing bean or the default factory |
| Resolved selector fails to parse | JMS provider | Test grammar against broker, check quotes |
| Valid selector yet no messages received | JMS message metadata | Check property names/types, null/UNKNOWN |
| Config file edited yet Queue unchanged | Container lifecycle | Controlled restart/recreation of endpoint |
| High concurrency spikes DB pressure | Resources/throughput | Set bounds, load test, tune pools |
| Listener receives another tenant's data | Authorization/routing | Audit ACLs and selector policies |
| Handler throws exception | Business/transaction | Retry/DLQ/idempotency per policy |
| Queue has backlog yet listener does not process | Overly narrow selector or consumer not running | Check broker metrics, consumer count, DLQ |
| Unit tests pass yet integration fails | Mocks did not test broker | Run broker tests, inspect root cause |

A selector error may surface when the container creates a consumer and retries connections, rather than always crashing the entire JVM immediately. Therefore, beyond startup validation, use readiness/metrics and alerts confirming the listener actually operates.

## 12. Transactions and Idempotency Are Not Determined by Placeholders

`@JmsListener` receives messages through a container. The container factory/session transaction governs ACK/commit, not placeholders.

If the handler writes to the DB and fails before JMS ACK, the message may be redelivered. If concurrency is raised, the handler may run across multiple threads. Therefore:

- Use stable business event IDs to deduplicate.
- Define clear transaction boundaries across JMS and the database.
- Do not assume JPA `@Transactional` automatically creates an XA transaction with Artemis.
- Implement bounded retries, DLQs, alarms, and poison-message handling.
- Do not change selectors in production without checking old backlogs and new consumers.

For example, configuring a factory with transacted sessions provides only a JMS local transaction; coordinating with a DB requires dedicated design. Annotation placeholders do not take over this responsibility.

## 13. Operations and Safe Configuration Changes

To change `app.jms.orders-queue` or `app.jms.order-selector` in production:

1. Review configuration changes in source control or a controlled config management system.
2. Verify the target Queue exists, the account has permissions, and property schemas are compatible.
3. Verify the selector matches intended event types and excludes unwanted messages.
4. Check concurrency against DB connection pools and handler thread safety.
5. Run integration tests covering matches, non-matches, invalid properties, and redelivery.
6. Deploy a canary or single instance first; monitor backlog/consumer counts.
7. Prepare a rollback plan in case the new selector causes messages to pile up on the Queue.
8. Never promise that a runtime config update automatically rewires running consumers.
9. For durable Topics, verify subscription identity and transition policies.
10. Log effective non-secret configuration (destination name, selector fingerprint/config version) appropriately without exposing sensitive data.

**Key point:** if you switch a listener to a new Queue while producers still publish to the old Queue, the application may report "healthy" while processing no events. Health checks should include consumer registration and observed message delivery, not merely JVM startup.

## 14. Extended Exercises

### Exercise 1: Staging Environment

Create `application-staging.properties` using Queue `orders.staging.in`, a selector for `region='SG'`, and concurrency `1`. Without modifying Java source, verify on a test broker that VN messages do not enter the staging listener.

### Exercise 2: Selector with Missing Properties

Send a TextMessage without `region` but with `eventType=order.created`. Verify it does not match `region = 'VN'`. Explain three-valued logic and write an explicit selector including `region IS NULL` if the real application also wants messages lacking region.

### Exercise 3: SpEL Policy Bean

Write a `RoutingPolicy` containing a Queue name allowlist. Use `@JmsListener(destination = "#{@routingPolicy.ordersQueue()}")`, and test the Spring context both when the destination format is valid and when config violates policy.

### Exercise 4: Changing Concurrency

Run `app.jms.listener-concurrency=1` and then `2-4` on a test Queue with many messages. Observe consumer count/throughput and ensure the handler does not store message state in unsynchronized shared fields.

### Exercise 5: Config Drift

Intentionally deploy the producer to Queue `orders.v2` while the consumer still listens on `orders.v1`. Write a checklist verifying effective configuration, queue depth, ACLs, and rollout steps to catch drift before production.

## 15. Self-Check Questions

**1.** How do `${...}` and `#{...}` differ?

Placeholders read values from the Spring Environment; SpEL evaluates Spring expressions, often retrieving Strings from a controlled bean. Both resolve endpoint configuration rather than running per message.

**2.** Can a Java instance field be passed directly into an annotation attribute?

No. Java annotations require constant expressions; String literals containing placeholders or SpEL are how Spring resolves them at runtime.

**3.** Does `selector = "${app.jms.order-selector}"` let the broker inspect a JSON body?

No. After resolution, the String is still a JMS selector applied to JMS headers/properties, not JSONPath.

**4.** When editing `application.properties` while the app is running, does the annotation pick up new values automatically?

Not by default. The listener endpoint/container is already configured; a restart or controlled re-registration/reconfiguration is needed.

**5.** Why should you never take a raw SpEL expression from an HTTP request?

Because SpEL can invoke beans/methods depending on the evaluation context; untrusted input can alter logic and introduce security vulnerabilities.

**6.** Does `concurrency = "2-6"` mean there are always six threads?

No. It is a container-level bound; actual concurrency depends on the implementation and workload.

**7.** What is `id = "ordersListener"` used for?

Identifying the endpoint/container for `JmsListenerEndpointRegistry` and lifecycle management.

**8.** Why is a selector insufficient for tenant isolation?

It only filters which messages are delivered; ACLs and destination isolation are the real security boundary.

**9.** What risk does a fallback value in a placeholder carry?

Production might silently listen to a demo/wrong Queue if a deployment omits a property, instead of failing fast.

**10.** Does unit-testing the listener method directly verify that Artemis executes the selector?

No. Integration tests with a broker are needed to verify property types and selector matching.

## 16. Official References

- Spring Framework 6.1 — Javadoc `@JmsListener`: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jms/annotation/JmsListener.html
- Spring Framework — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Framework — Using Spring JMS: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Framework — Value annotations and placeholders: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html
- Spring Framework — Spring Expression Language: https://docs.spring.io/spring-framework/reference/core/expressions.html
- Spring Boot 3.3 — JMS support: https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html
- Spring Boot 3.3 — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Jakarta Messaging 3.1 — Message selection: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html

**Summary:** Use `${...}` for simple, managed configuration values; use `#{...}` only when computing values from a trusted bean. Annotations are resolved at listener registration, while JMS selectors are evaluated by the broker per message. Ensure quality through validation, ACLs, concurrency bounds, integration tests, and clear deployment policies.
