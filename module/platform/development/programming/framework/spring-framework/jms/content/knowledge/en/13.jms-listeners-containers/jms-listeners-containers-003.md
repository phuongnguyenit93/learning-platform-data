# MessageListenerAdapter for Plain Java Objects in Spring JMS

## 1. Goal: Turning a POJO into a JMS Message Listener

In Spring JMS, a listener does not have to be a class that directly implements `jakarta.jms.MessageListener`. Many systems already have a Java class that accepts a string, byte array, or business object, for example:

~~~java
public class OrderHandler {
    public void handleMessage(String orderText) {
        System.out.println("ORDER=" + orderText);
    }
}
~~~

This is a **POJO (Plain Old Java Object)**: it does not implement any JMS interface, needs no `jakarta.jms.*` imports, and knows nothing about brokers, connections, sessions, or acknowledge modes. However, a JMS provider inherently delivers callbacks via `MessageListener.onMessage(Message)`, meaning an intermediary is needed to convert a JMS message into an argument for the POJO's method.

Spring Framework provides **`org.springframework.jms.listener.adapter.MessageListenerAdapter`** as that bridge:

~~~text
Artemis / JMS Broker
         |
         | Jakarta JMS Message
         v
DefaultMessageListenerContainer
         |
         | invokes listener
         v
MessageListenerAdapter
         |
         | MessageConverter:
         | TextMessage -> String
         | BytesMessage -> byte[]
         | MapMessage -> Map
         | ObjectMessage -> Serializable (use with caution)
         |
         | resolves method on delegate and invokes via reflection
         v
POJO OrderHandler
         |
         +-- handleMessage(String body)
         +-- or a method name you configure
~~~

**Scope of the adapter:** it converts data types and dispatches the call to a plain Java object. It does **not** connect to the broker, create consumer threads, guarantee transactions, or persist processing state. Those responsibilities belong to `ConnectionFactory`, the listener container, the provider, and business code.

After this lesson, you will be able to:

1. Explain the roles of the delegate, listener adapter, converter, and container.
2. Configure the default `handleMessage` method or rename it via `setDefaultListenerMethod`.
3. Automatically read bodies as `String`/`byte[]`/`Map` or disable the converter to receive a raw JMS `Message`.
4. Know when the adapter automatically sends a reply from the return value.
5. Build a Java 17/Spring Boot/Artemis application that sends a `TextMessage` and invokes a POJO.
6. Understand method mismatch errors, message conversion, transactions/ACK, and testing.

## 2. How Does MessageListenerAdapter Work?

According to Spring Framework, `MessageListenerAdapter` implements the listener interfaces needed to act as a JMS message listener, including `jakarta.jms.MessageListener` and `org.springframework.jms.listener.SessionAwareMessageListener`. It holds a **delegate** — the actual object containing processing logic.

~~~java
OrderHandler handler = new OrderHandler();
MessageListenerAdapter adapter =
        new MessageListenerAdapter(handler);
~~~

When the container receives a message, it invokes the adapter. The adapter typically performs:

1. Receives `jakarta.jms.Message` from the listener container.
2. Uses a `MessageConverter` (by default `SimpleMessageConverter`) to extract the body into a Java value.
3. Determines the delegate method name; by default **`handleMessage`**.
4. Invokes the matching method via reflection with **one argument** — the extracted Java value.
5. If the method returns a non-null value, the adapter can create and send a **JMS reply** under configured conditions.
6. If the delegate throws an exception, the container applies its error handling/transaction/ACK rules.

For example, suppose an incoming message is a `TextMessage` containing `"ORDER|O-42"`. The default converter extracts a `String`, and the adapter looks for the method:

~~~java
public void handleMessage(String text)
~~~

It does **not** look for an arbitrary method named `onMessage` unless you configure that name.

### 2.1. How JMS-independent is the POJO?

With a `handleMessage(String)` method, the business class uses zero JMS imports. However, the adapter bean, converter, container, and configuration **still depend on Spring JMS**. If you switch brokers/providers, the POJO rarely needs changes; if you migrate entirely to Kafka, you need a corresponding adapter or a dedicated business port.

Do not confuse "the POJO does not implement JMS `MessageListener`" with "the entire application has no JMS dependency". The proper architectural boundary is that the POJO executes business logic while infrastructure handles transport.

## 3. Three Components to Distinguish

| Component | Type/object | Responsibility |
| --- | --- | --- |
| **Delegate** | `OrderHandler` POJO | Method such as `handleMessage(String)` or `onOrder(String)` |
| **Adapter** | `MessageListenerAdapter` | Converts JMS message and invokes delegate via reflection |
| **Container** | `DefaultMessageListenerContainer` / `SimpleMessageListenerContainer` | Manages connection/session/consumer, receives messages, ACK, transactions, and lifecycle |

A `MessageListenerAdapter` bean **sitting alone** in the Spring context is not enough for the broker to deliver messages. The adapter must be registered with a listener container:

~~~java
DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();
container.setConnectionFactory(connectionFactory);
container.setDestinationName("orders.in");
container.setMessageListener(adapter);
~~~

This is a **configuration snippet**; it requires appropriate `connectionFactory` and `adapter` variables. With a full Spring container bean, Spring manages `afterPropertiesSet`, startup, shutdown, and resource cleanup.

### 3.1. DefaultMessageListenerContainer or SimpleMessageListenerContainer?

- `DefaultMessageListenerContainer`: polling model via JMS receive inside the container, supporting recovery, concurrent consumer scaling, and flexible transaction behavior. Usually the better choice for Spring applications with operational requirements.
- `SimpleMessageListenerContainer`: fewer mechanisms, registers `MessageListener` directly with the JMS provider, suitable for certain simple cases. It has its own transaction/container limitations.
- Both can use the adapter as their message listener; **the adapter does not decide** which container to use.

Merely calling `adapter.onMessage(...)` directly in a unit test does not mean the container is running or the broker is reachable.

## 4. Default Method handleMessage and Renaming It

### 4.1. No extra configuration: default handleMessage

POJO:

~~~java
public class PlainOrderHandler {
    public void handleMessage(String orderText) {
        System.out.println("ORDER=" + orderText);
    }
}
~~~

Adapter:

~~~java
MessageListenerAdapter adapter =
        new MessageListenerAdapter(new PlainOrderHandler());
~~~

By default, Spring searches for a method named **`handleMessage`**. If the `TextMessage` is converted to `String`, the matching signature is `handleMessage(String)`.

### 4.2. Switching to a business-meaningful name

A legacy POJO might already have:

~~~java
public class LegacyOrderProcessor {
    public void processOrder(String payload) {
        System.out.println("PROCESS=" + payload);
    }
}
~~~

Configuration:

~~~java
MessageListenerAdapter adapter =
        new MessageListenerAdapter(new LegacyOrderProcessor());
adapter.setDefaultListenerMethod("processOrder");
~~~

No need to rename the method in legacy code. If you name it `processOrder` but forget to call `setDefaultListenerMethod`, the adapter still looks for `handleMessage` and will fail when a message arrives.

### 4.3. Single-argument methods and overloads

A delegate may declare:

~~~java
public void handleMessage(String text) { /* ... */ }
public void handleMessage(byte[] bytes) { /* ... */ }
public void handleMessage(java.util.Map<?, ?> map) { /* ... */ }
~~~

`SimpleMessageConverter` converts each JMS body type into a Java value; the adapter invokes the method matching the name and parameter type. If there are ambiguous overloads or conversion does not yield the expected type, reflection/method resolution errors may occur.

**Avoid** using multiple ambiguous overloads just to catch every message type. In systems with strict message schemas, standardizing the converter and a single explicit business method is usually easier to maintain.

## 5. What Body Types Does the Default MessageConverter Convert?

`MessageListenerAdapter` uses Spring JMS's **`SimpleMessageConverter`** by default. For typical messages:

| Incoming JMS message | Value passed to POJO |
| --- | --- |
| `TextMessage` | `String` |
| `BytesMessage` | `byte[]` |
| `MapMessage` | `java.util.Map` |
| `ObjectMessage` | Serializable object deserialized per provider |
| `StreamMessage` or other types | Depends on converter support; may fail to convert |

Example:

~~~text
Broker sends TextMessage(body="ORDER|O-42")
    -> SimpleMessageConverter
    -> String "ORDER|O-42"
    -> handler.processOrder(String)
~~~

If the broker sends a UTF-8 JSON `BytesMessage` while the handler only has `processOrder(String)`, the adapter **does not automatically decode `byte[]` into `String`** under default rules. The result may be a method-not-found or conversion/argument error. When JSON/DTOs are required, choose a consistent converter on both producer and consumer.

### 5.1. Do not assume JSON automatically becomes a POJO DTO

Receiving a `TextMessage` with body:

~~~json
{"orderId":"O-42","amountVnd":125000}
~~~

does not automatically make `SimpleMessageConverter` instantiate an `OrderCreated` record. By default it returns a JSON **String**. To use a `handleMessage(OrderCreated event)` method, you need a configured JSON `MessageConverter` with sufficient type information.

Spring provides `MappingJackson2MessageConverter` using Jackson. When designing:

- Agree on `MessageType.TEXT` or `MessageType.BYTES`.
- Provide a type ID property/mapping if the converter must infer the Java type from the message.
- Both sides must use compatible schemas and converters.
- Parsing/schema/DTO errors occur **before** the delegate method is invoked.
- Do not arbitrarily allow external messages to request deserialization of unrestricted classes.

### 5.2. Be cautious with ObjectMessage

`ObjectMessage` can involve Java native serialization/deserialization; it is not a language-independent JSON format. For messages from untrusted sources, deserialization carries significant security risks. Prefer JSON `TextMessage` or `BytesMessage` with explicit schemas, type allowlists, and data validation.

## 6. Disabling MessageConverter to Receive a Raw JMS Message

Some delegates need access to `JMSCorrelationID`, `JMSReplyTo`, `JMSType`, properties, or a specific raw body type. In that case, the adapter can disable automatic extraction:

~~~java
import jakarta.jms.TextMessage;

public class RawTextHandler {
    public void receive(TextMessage message) throws Exception {
        String body = message.getText();
        String correlation = message.getJMSCorrelationID();
        System.out.println("BODY=" + body + ", CORR=" + correlation);
    }
}
~~~

Configuration:

~~~java
MessageListenerAdapter adapter =
        new MessageListenerAdapter(new RawTextHandler());
adapter.setDefaultListenerMethod("receive");
adapter.setMessageConverter(null);
~~~

When the converter is `null`, the adapter skips extracting a `String` body and passes the raw JMS `Message` to the matching method. In this example, the delegate **is no longer JMS-independent** because the method accepts `TextMessage`.

Important notes:

1. A raw `Message` may be a `TextMessage`, `BytesMessage`, or another type; use an appropriate parameter type and do not cast without verifying.
2. Reading JMS headers/properties can throw `JMSException`.
3. If the producer changes the body type from `TextMessage` to `BytesMessage`, `receive(TextMessage)` will no longer match validly.
4. Do not set the converter to `null` just to work around JSON parsing errors; that bypasses conversion while JSON handling is still required.
5. If business logic needs both payload and metadata, you can design an application DTO/envelope constructed in an infrastructure adapter instead of forcing the domain method to take raw JMS API types.

## 7. When a Method Returns a Value: The Adapter Can Send a JMS Reply

This is an easily overlooked feature. `MessageListenerAdapter` does not merely convert the request and invoke the delegate. If the method returns a **non-null** value, the adapter can construct a JMS response message and send it to a reply destination.

Example delegate:

~~~java
public class PricingHandler {
    public String handleMessage(String request) {
        return "PRICE_OK:" + request;
    }
}
~~~

If the incoming request has a valid `JMSReplyTo`, an adapter invoked via Spring container's `SessionAwareMessageListener` path can convert the `String` into a `TextMessage` and send it to the reply destination.

~~~text
Requestor
   |
   | TextMessage("PRICE:SKU-42", JMSReplyTo=temp.reply)
   v
Queue pricing.requests
   |
   v
DefaultMessageListenerContainer
   |
   v
MessageListenerAdapter
   |
   v
PricingHandler.handleMessage(String)
   |
   +-- returns "PRICE_OK:PRICE:SKU-42"
   |
   v
Adapter creates TextMessage reply
   |
   v
temp.reply queue
~~~

If the request lacks `JMSReplyTo`, a fallback can be configured:

~~~java
adapter.setDefaultResponseQueueName("pricing.replies");
~~~

**Important limitation:** Spring's Javadoc explicitly notes that automatic response sending is supported when using the **`SessionAwareMessageListener.onMessage(Message, Session)`** entry point (typically via a Spring listener container). If the adapter is invoked only via JMS `MessageListener.onMessage(Message)` without a session path, response creation **is not supported** in the same session-aware flow.

If the delegate returns non-null without a valid reply destination, do not assume that is a harmless "no-op" by default. Verify the behavior/error handling for your adapter and configuration. For event-only consumers, use a **`void` method** so no unintended reply is attempted.

### 7.1. A reply does not equal a business transaction

Sending a response message does not by itself prove that the database transaction and JMS ACK committed together. Check `sessionTransacted`/external transaction managers and the broker's request/reply policy. If the handler sends a reply and the session rolls back, the response can roll back with the transaction when truly sharing the same session; do not assume this when separate resources are used.

### 7.2. Do not assume a String return value is an HTTP response

The POJO's return value through the adapter is a result for **JMS** per reply configuration; it is not an HTTP response or a Java return value synchronously observed by the producer caller. For request/reply, the producer must also use a matching pattern with `JMSReplyTo`, correlation, and receive timeout.

## 8. Complete Lab: POJO Receiving TextMessage via MessageListenerAdapter

Goal: use Spring Boot 3.x, Java 17, and Apache Artemis. The producer sends a `String`, the listener container receives it, the adapter converts the `TextMessage` to `String` and invokes **method `onOrder(String)`** on a POJO. Do not use `@JmsListener` on the POJO.

### 8.1. Start local Artemis

On a machine with Docker, run the demo broker:

~~~bash
docker run --detach --rm --name artemis-adapter-demo -p 127.0.0.1:61616:61616 -p 127.0.0.1:8161:8161 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest
~~~

Wait for the broker to be ready; inspect logs:

~~~bash
docker logs artemis-adapter-demo
~~~

This is a learning configuration. `demo/demo` must not be used in production. If the broker disables Queue auto-creation, pre-create `orders.adapter.demo` and grant send/consume permissions to the service account.

### 8.2. Project structure

~~~text
jms-pojo-adapter/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/demo/jms/
    PojoAdapterApplication.java
    OrderMessageHandler.java
    JmsListenerConfiguration.java
  src/test/java/demo/jms/
    OrderMessageAdapterTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-pojo-adapter'
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

Versions are pinned for consistent project description and do not imply Spring Boot 3.3.0 is the latest release. In real deployments, use a compatible maintenance/security release. Because Spring Boot 3/Framework 6 is used, every JMS type must belong to package **`jakarta.jms`**, not `javax.jms`.

`src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_BROKER_USER:demo}
spring.artemis.password=${JMS_BROKER_PASSWORD:demo}
spring.jms.pub-sub-domain=false
spring.jms.cache.enabled=false
~~~

The configuration uses standard Spring property placeholders: e.g., `$` + `{JMS_BROKER_URL:tcp://localhost:61616}`. Demo defaults are strictly for the lab; production requires secret management. `spring.jms.cache.enabled=false` keeps the factory in the example simple as a raw factory so the container independently manages JMS connections. In production systems, cache/pool configuration must be designed for the workload rather than blindly copying this option.

### 8.3. Business-logic POJO class

`src/main/java/demo/jms/OrderMessageHandler.java`:

~~~java
package demo.jms;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;

@Component
public class OrderMessageHandler {

    private final CountDownLatch received = new CountDownLatch(1);
    private volatile String lastBody;

    // POJO method: no JMS Message or Session.
    public void onOrder(String body) {
        if (body == null || !body.startsWith("ORDER|")) {
            throw new IllegalArgumentException("Invalid order message");
        }

        lastBody = body;
        System.out.println("POJO_RECEIVED=" + body);
        received.countDown();
    }

    public boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return received.await(timeout, unit);
    }

    public String lastBody() {
        return lastBody;
    }
}
~~~

The POJO remains a normal Java class that can be instantiated with `new` in unit tests. `@Component` only lets Spring manage the bean; it is **not a listener annotation**. The `onOrder` method is public, accepts only `String`, and returns `void`, so the adapter needs no reply handling.

`CountDownLatch` is used to observe one message in the demo; it is **not an ACK mechanism** and does not prove the broker transaction committed. In production, replace log printing/latch logic with business logic featuring proper validation, idempotency, and transactions.

### 8.4. MessageListenerAdapter and listener container beans

`src/main/java/demo/jms/JmsListenerConfiguration.java`:

~~~java
package demo.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.jms.listener.adapter.MessageListenerAdapter;

@Configuration
public class JmsListenerConfiguration {

    @Bean
    MessageListenerAdapter orderMessageAdapter(
            OrderMessageHandler handler) {
        MessageListenerAdapter adapter =
                new MessageListenerAdapter(handler);

        // POJO method does not use the default name handleMessage.
        adapter.setDefaultListenerMethod("onOrder");
        return adapter;
    }

    @Bean
    DefaultMessageListenerContainer orderListenerContainer(
            ConnectionFactory connectionFactory,
            MessageListenerAdapter orderMessageAdapter) {

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("orders.adapter.demo");
        container.setMessageListener(orderMessageAdapter);
        container.setConcurrentConsumers(1);

        // So errors from the POJO can roll back the JMS session.
        container.setSessionTransacted(true);
        return container;
    }
}
~~~

This is the **actual wiring**:

1. The `OrderMessageHandler` bean holds the logic.
2. The `MessageListenerAdapter` bean wraps the delegate and knows the `onOrder` method.
3. The `DefaultMessageListenerContainer` bean holds the connection factory, Queue name, adapter, and transaction policy.
4. When Spring builds the context, the container bean is lifecycle-managed and starts receiving messages once ready.
5. With a transacted session, a delegate error before commit can cause the JMS transaction to roll back and the message to be redelivered per broker policy.

**`@EnableJms` is not needed in this example**, because `@JmsListener` endpoints are not used. This is a listener container registered manually as a Spring bean. `@EnableJms` enables annotation-driven listener processing and does not alter the nature of a directly registered adapter.

### 8.5. Main class and demo producer

`src/main/java/demo/jms/PojoAdapterApplication.java`:

~~~java
package demo.jms;

import java.util.concurrent.TimeUnit;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class PojoAdapterApplication {

    public static void main(String[] args) {
        SpringApplication.run(PojoAdapterApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JmsTemplate jmsTemplate,
                           OrderMessageHandler handler) {
        return args -> {
            jmsTemplate.convertAndSend(
                    "orders.adapter.demo", "ORDER|O-42");

            // Prove the handler is actually invoked in the lab.
            boolean invoked = handler.await(10, TimeUnit.SECONDS);
            System.out.println("HANDLER_INVOKED=" + invoked);
        };
    }
}
~~~

The producer's `convertAndSend` accepts a `String`; with the common `SimpleMessageConverter`, the `String` becomes a JMS `TextMessage`. The container receives the `TextMessage` and the adapter converts it to a Java `String` for `OrderMessageHandler.onOrder`.

On a broker with no other consumers and valid configuration, expected stdout from **the demo code itself** is:

~~~text
POJO_RECEIVED=ORDER|O-42
HANDLER_INVOKED=true
~~~

Spring/Artemis and Gradle logs may interleave. `HANDLER_INVOKED=true` only indicates that the POJO method reached `CountDownLatch.countDown()`; it does not prove the business DB committed or the JMS ACK was confirmed by the broker. If the broker is not ready, credentials/ACLs are wrong, or another consumer on the same Queue takes the message, the demo may not produce those exact two lines.

### 8.6. Running

With JDK 17+, a compatible Gradle version, and a running broker:

~~~bash
gradle test
gradle bootRun
~~~

In repositories with the Gradle wrapper, you can run `./gradlew test` and `./gradlew bootRun` on Bash or `.\gradlew.bat` on Windows.

Stop the demo broker:

~~~bash
docker stop artemis-adapter-demo
~~~

## 9. Unit Testing the Adapter Directly Without a Broker

A unit test can use Mockito to create a mock `TextMessage`, pass it to `MessageListenerAdapter.onMessage(Message, Session)`, and verify the POJO is invoked properly. This verifies default converter + reflection dispatch without starting Artemis.

`src/test/java/demo/jms/OrderMessageAdapterTest.java`:

~~~java
package demo.jms;

import jakarta.jms.TextMessage;
import org.junit.jupiter.api.Test;
import org.springframework.jms.listener.adapter.MessageListenerAdapter;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class OrderMessageAdapterTest {

    @Test
    void convertsTextMessageAndInvokesPojo() throws Exception {
        OrderMessageHandler handler = new OrderMessageHandler();

        MessageListenerAdapter adapter =
                new MessageListenerAdapter(handler);
        adapter.setDefaultListenerMethod("onOrder");

        TextMessage message = mock(TextMessage.class);
        when(message.getText()).thenReturn("ORDER|O-42");

        // Null Session is only suitable for testing a void delegate:
        // no automatic response needs to be sent.
        adapter.onMessage(message, null);

        assertEquals("ORDER|O-42", handler.lastBody());
    }
}
~~~

This test proves that a `TextMessage` with a `String` body is converted by the adapter and calls `onOrder` properly; it does not prove a broker connection was created, the Queue exists, ACLs work, or the session commits. Those require an **integration test** against a real broker.

### 9.1. Testing the POJO directly without the framework

Because the POJO takes no JMS types, you can also test:

~~~java
OrderMessageHandler handler = new OrderMessageHandler();
handler.onOrder("ORDER|O-42");
assertEquals("ORDER|O-42", handler.lastBody());
~~~

This is a snippet inside a test method and requires importing `assertEquals`. It isolates validation/business logic from the adapter. You should have **both POJO tests** and **adapter tests**, while avoiding relying on mock-only tests to claim messages were actually delivered.

## 10. When to Use MessageListenerAdapter vs @JmsListener?

Modern Spring commonly uses `@JmsListener`:

~~~java
@Component
public class AnnotatedOrderListener {

    @JmsListener(destination = "orders.in")
    public void onOrder(String payload) {
        System.out.println(payload);
    }
}
~~~

This is a **separate option**; do not add it to the same Queue as the demo unless you want competing consumers. Import `org.springframework.stereotype.Component` and `org.springframework.jms.annotation.JmsListener` in an actual class.

Comparison:

| Aspect | MessageListenerAdapter | @JmsListener |
| --- | --- | --- |
| How it is declared | Adapter bean + container or listener endpoint | Annotation on method |
| POJO independent of Spring JMS? | Possible, if delegate uses no JMS types and no JMS annotations | Method contains Spring JMS annotation |
| Default method | `handleMessage`, changed via `setDefaultListenerMethod` | Annotated method |
| Conversion | Adapter's `MessageConverter` | Listener infrastructure conversion/argument resolution |
| Reply | Return value via SessionAware entry point and reply destination | Dedicated annotation/handler reply mechanism |
| Legacy POJO | Well suited when you do not want to modify the class | Requires modifying the class or writing an annotated wrapper method |
| Configuration boilerplate | More | Less in Spring Boot applications |
| Container control | Manual bean declaration and setup | Can configure listener factory and annotation |
| Fit for new projects | When reusing an existing POJO/custom contract | Usually the more convenient option |

**When to use the adapter:** reusing legacy classes without annotations, keeping services decoupled from transport, wiring listeners via configuration, or flexibly choosing delegates/methods.

**When to use `@JmsListener`:** building new Spring applications, readable endpoints, convenient argument binding/validation/annotations, and letting Boot manage most wiring.

Neither option is "always faster" just because the adapter uses reflection: overall performance is usually dominated by the broker, network, deserialization, DB, and business logic. Benchmark if it is an actual requirement.

## 11. MappingJackson2MessageConverter and Receiving DTOs Instead of String

In the runnable example, the adapter receives a `String` from a `TextMessage` by default. If the message body is JSON and the delegate wants to receive a record:

~~~java
public record OrderCreated(
        String eventId,
        String orderId,
        long amountVnd) {
}
~~~

You must configure a JSON converter matching the message format and type metadata, rather than assuming changing the method signature alone is enough:

~~~java
public void onOrder(OrderCreated event) {
    // Process the event deserialized by the converter.
}
~~~

Reference configuration snippet (do not add directly to the String demo project in section 8):

~~~java
import java.util.Map;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageType;

MappingJackson2MessageConverter converter =
        new MappingJackson2MessageConverter();

converter.setTargetType(MessageType.TEXT);
converter.setTypeIdPropertyName("_type");
converter.setTypeIdMappings(
        Map.of("order-created.v1", OrderCreated.class));

adapter.setMessageConverter(converter);
~~~

This is a **snippet inside a configuration method that already has an `adapter` variable**; import `OrderCreated` if it is in another package. The producer must also use a compatible converter and attach the `_type` property per contract. A default JSON converter does not automatically allow every DTO type to deserialize safely without proper type IDs and schema mappings.

Spring Javadoc notes that the Jackson converter produces `BytesMessage` by default unless switched to `MessageType.TEXT`. Producer and consumer must agree on `TextMessage`/`BytesMessage`, encoding, schema version, and allowed object types.

**Architectural choice:** you can let the adapter receive only a JSON `String` and invoke a separate parser service, or configure the converter so the method receives a DTO. The first is explicit and easy to observe; the second is more concise but depends on converter configuration. Choose based on contracts and tests, not line count.

## 12. Common Pitfalls When Configuring MessageListenerAdapter

| Symptom | Cause | Fix |
| --- | --- | --- |
| Broker has messages but POJO never runs | Adapter not registered with listener container or wrong destination | Check `setMessageListener`, `setDestinationName`, container startup |
| `NoSuchMethodException` / reflection error | Delegate lacks default `handleMessage` | Set `setDefaultListenerMethod("onOrder")` or rename method |
| Method has right name but cannot be invoked | Parameter type does not match converted body | Inspect JMS message type and converter |
| Handler receives `byte[]` instead of `String` | Producer sent `BytesMessage` and default converter returns bytes | Align body contract or use JSON converter |
| Handler wants raw `TextMessage` but receives `String` | Conversion not disabled | `adapter.setMessageConverter(null)`, update signature |
| Handler fails to receive DTO | Missing JSON converter/type ID/schema mapping | Configure converter symmetrically and test |
| Handler returns `String` but reply never arrives | Missing `JMSReplyTo`/default response destination or non-session-aware entry point | Verify request/reply contract and container |
| Message is reprocessed | Exception, rollback, redelivery | Design idempotency, retry/DLQ, and transactions |
| Method invoked but data is wrong | Conversion/schema or property/body mismatch | Log metadata safely, test byte/JSON encoding |
| Multiple instances compete to receive | Queue competing consumers | Adjust concurrency/partitioning/Queue design |
| Container fails to recover on restart | Excessive connection factory caching or wrong provider recovery config | Check factory lifecycle and DMLC recovery policy |
| Runtime `javax.jms`/`jakarta.jms` mismatch | Legacy client/provider incompatible with Spring Boot 3 | Use compatible Jakarta JMS libraries |

### 12.1. Wrong method names must be caught before production

The adapter locates methods via reflection. The Java compiler cannot verify that the string `"onOrder"` still exists after a refactor when only string configuration is used. For new code, write unit tests that invoke the adapter and cover conversion branches, rather than only checking that the Spring context contains the adapter bean.

### 12.2. Errors happen at processing time, not bean registration

An adapter bean may initialize cleanly and only fail when the first message arrives with no matching method or a conversion error. Therefore health checks that only verify connectivity are insufficient; integration tests must **actually send and receive** at least one properly typed message.

### 12.3. Do not swallow exceptions from the delegate

If the POJO fails yet the adapter/container never sees the exception, the message may be ACKed as processed. Do not catch and merely log:

~~~java
// Anti-pattern to avoid if the business logic needs retry:
try {
    processBusiness(payload);
} catch (Exception failure) {
    logger.error("Failed", failure);
    // Not rethrowing => the container may treat it as success!
}
~~~

Propagate the exception or transition to a failed outcome according to the chosen transaction policy, with appropriate DLQ/idempotency. If in-handler retries are needed, bound attempts/backoff and avoid holding transaction resources for long durations.

## 13. Transactions, ACK, Redelivery, and Replies

### 13.1. The container determines the ACK point

`MessageListenerAdapter` does not itself decide whether a message is ACKed before or after the POJO runs. `DefaultMessageListenerContainer` and `Session` define that behavior.

- With default `AUTO_ACKNOWLEDGE` on `DefaultMessageListenerContainer`, Spring docs warn that ACK may occur **before the listener executes**, so handler errors do not guarantee redelivery.
- With `sessionTransacted=true`, the container uses a local JMS transaction; normal method completion can lead to commit, while exceptions can cause rollback and redelivery per provider policy.
- If using an external transaction manager/XA, configure transaction boundaries, resource enlistment, and recovery properly.

**Do not treat `CountDownLatch.countDown()` in the example as an ACK.** It only proves the Java handler reached a point in code, not that the transaction committed with the broker.

### 13.2. Same-session response when supported

An adapter returning a non-null value with `JMSReplyTo`/default response destination can send a reply using the container-supplied session. With a transacted session, receiving the request and sending the reply can belong to the same local JMS transaction. However, the business database is a separate resource; do not assume JMS+DB atomicity solely from `@Transactional` or `setSessionTransacted(true)`.

### 13.3. Redelivery and idempotency

When the listener throws an exception and the session rolls back, the broker may redeliver the message. A business event can also appear multiple times due to producer retries, broker redelivery, or a crash after DB commit but before JMS ACK. Consumers need a business event ID, durable processing state, and deduplication of repeated side effects.

A good event contract should include:

~~~text
eventId = stable identifier across retries
eventType = order.created.v1
schemaVersion = 1
payload = business data
~~~

Do not use `JMSMessageID` as the unique key across all republishes of the same event: a newly published JMS message can have a different message ID. If using a DLQ, define policies for malformed payloads and unrecoverable exceptions to prevent infinite retries from clogging the Queue.

## 14. Caching, Concurrency, and Lifecycle

### 14.1. How does the container use connections/sessions?

`DefaultMessageListenerContainer` manages connections/sessions/consumers itself and applies an appropriate caching strategy. Spring Boot may wrap the native factory in `CachingConnectionFactory` for `JmsTemplate`; however, DMLC should consider using the native factory to avoid unclear resource ownership and recovery behavior. In the sample, Boot JMS caching was disabled to keep the path simple.

In production:

- A factory used for publishers can be appropriately cached/pooled.
- The listener container should have authority to manage connection lifecycle and recovery.
- Do not increase `concurrentConsumers` without measuring broker resources, business thread safety, and ordering.
- With Queues, multiple consumers share messages; with Topics, subscription semantics differ.
- Use resource metrics instead of inferring broker connection counts from the number of listener beans.

### 14.2. Thread safety of the delegate

POJOs are typically Spring singletons; multiple container threads may invoke the same delegate **concurrently** when concurrency is increased. Do not store current message state in mutable fields without proper synchronization.

Unsafe example:

~~~java
private String currentOrder;

public void onOrder(String body) {
    currentOrder = body;
    // Another thread may overwrite currentOrder before it is used.
}
~~~

Replace with local variables or a stateless design:

~~~java
public void onOrder(String body) {
    String currentOrder = body;
    processBusiness(currentOrder);
}
~~~

This is an illustrative snippet in a class that already has `processBusiness`. The demo application's `lastBody` and latch are solely for observing **a single message**; do not copy that state pattern for production multithreading.

## 15. Integrating a Legacy POJO Without Modifying Old Code

Suppose an internal library has:

~~~java
public final class LegacyInvoiceService {
    public void acceptInvoice(String invoiceJson) {
        // Parse JSON, validate, persist business data.
    }
}
~~~

Do not add `@JmsListener` to this class. In the broker integration module:

~~~java
@Bean
MessageListenerAdapter invoiceAdapter(
        LegacyInvoiceService service) {
    MessageListenerAdapter adapter =
            new MessageListenerAdapter(service);
    adapter.setDefaultListenerMethod("acceptInvoice");
    return adapter;
}
~~~

Then declare the listener container with `setMessageListener(invoiceAdapter)` as in the sample project. If the legacy POJO is not a Spring bean, you can expose a `@Bean LegacyInvoiceService` or obtain the instance from an existing factory.

Advantages:

- Adds no JMS/Spring dependencies to the business library.
- Does not change legacy method signatures.
- Tests the POJO independently and tests adapter dispatch separately.
- Broker infrastructure can change while the business method still receives a JSON `String`.

Limitation: the adapter invokes via reflection using a string method name, so signature changes must be verified by tests. If the POJO needs extensive metadata, use an envelope/application DTO or custom adapter rather than forcing transport framework types into the domain.

## 16. Recommended Test Suite

| Test level | What to verify | Needs broker? |
| --- | --- | --- |
| POJO unit test | Validation, business transformations, business errors | No |
| Adapter unit test | Converter + dispatch to correct method/type | No |
| Spring context test | Adapter/container beans/wiring not missing | Possibly not, if container auto-start is disabled |
| Artemis integration test | Queue receives, adapter calls POJO, transaction/ACK/retry work | Yes |
| End-to-end test | Database commit, idempotency, DLQ, reply to requestor | Yes, along with related DB/services |

Scenarios to test:

1. Normal `TextMessage` invokes `onOrder(String)`.
2. `BytesMessage` hitting a `String` handler produces a clear contract error.
3. Changing `setDefaultListenerMethod` to a nonexistent name causes a detectable error.
4. Handler throws an exception on invalid payload and rollback/redelivery follows policy.
5. `JMSReplyTo` present with a `String`-returning delegate: response is created via the session-aware path.
6. No `JMSReplyTo` and no default reply configured: behavior matches adapter/container expectations.
7. Two competing consumers on one Queue: each message goes to one consumer per JMS Queue semantics.
8. Multiple concurrent messages: delegate has no mutable shared state causing races.
9. Broker restart between receive/ACK: verify retry/redelivery and idempotency.
10. No credentials or sensitive payloads are logged by the adapter/handler.

## 17. Self-Check Questions

**1.** Why does an `OrderHandler.handleMessage(String)` not need to implement `MessageListener`?

Because `MessageListenerAdapter` sits between the container and the POJO, takes the JMS message, converts the body into a Java `String`, and invokes the method.

**2.** What is the default method name Spring looks for on a delegate?

`handleMessage`. If the business method is named `processOrder`, use `setDefaultListenerMethod("processOrder")`.

**3.** Does a standalone `MessageListenerAdapter` bean connect to a Queue by itself?

No. A listener container must be registered with a `ConnectionFactory`, destination, and the adapter.

**4.** What type does the default converter usually turn a `TextMessage` into?

`String`. `BytesMessage` is usually converted to `byte[]`, and `MapMessage` to `Map`.

**5.** How do you make the delegate receive a raw `TextMessage` instead of a `String`?

Call `adapter.setMessageConverter(null)` and declare the method to accept `TextMessage` (or `Message`) as appropriate.

**6.** Does a handler `String handleMessage(String)` returning a non-null result always send a JMS reply?

No. It requires the `SessionAwareMessageListener` path via a container and a valid reply destination (`JMSReplyTo` or default response destination).

**7.** Should `@JmsListener` be used on the same Queue alongside the adapter demo?

If you want deterministic demo results, no: the two consumers can compete and messages may be taken by the other listener.

**8.** If the POJO method throws an exception, is the message guaranteed to be redelivered?

Not under every acknowledge mode; container transaction/ACK configuration is required. `sessionTransacted=true` is the option that enables rollback/redelivery per broker policy.

**9.** What does a unit test calling `adapter.onMessage(mockTextMessage, null)` prove?

It proves the converter/dispatch path into the POJO inside the JVM; it does not prove broker delivery or successful ACK.

**10.** When is `MessageListenerAdapter` more useful than `@JmsListener`?

When you have an existing legacy POJO, want to keep annotations/JMS dependencies out of that class, or want configuration-driven delegate wiring.

## 18. Official Documentation

- Spring Framework 6.1 — `MessageListenerAdapter` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/jms/listener/adapter/MessageListenerAdapter.html
- Spring Framework — MessageListenerAdapter / receiving JMS: https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
- Spring Framework — Using Spring JMS, listener containers: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Framework 6.1 — `DefaultMessageListenerContainer` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
- Spring Framework 6.1 — `SimpleMessageConverter` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/jms/support/converter/SimpleMessageConverter.html
- Spring Framework — `@JmsListener` reference: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Boot — JMS and ActiveMQ Artemis: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
- Jakarta Messaging 3.1 Specification: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html

**Remember:** `MessageListenerAdapter` turns **a POJO method into a JMS listener endpoint** via a converter and reflection. The container is what manages connections, lifecycle, and transactions. Use the adapter when reusing existing Java objects, configure method/converter settings properly, and test both dispatch and real broker behavior.
