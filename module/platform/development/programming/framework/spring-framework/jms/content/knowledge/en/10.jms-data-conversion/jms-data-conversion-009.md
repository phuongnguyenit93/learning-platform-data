# Distinguishing Conversion Errors from Business Processing Errors in Spring JMS

## 1. Goal and Real-World Scenario

In a **Spring Framework – JMS** application, a message can be rejected before entering the handler method, or be successfully converted into a Java object and then fail due to a business rule. Both cases may show up in logs as "listener failed", yet **their root cause, who owns the fix, and the retry policy are completely different**.

Consider an order-intake system:
- A message has JSON `{"orderId":"O-101","quantity":2}`, valid schema, and stock available: **processed successfully**.
- A message has `{invalid-json` or an unrecognized type ID: **data conversion error**.
- A message is syntactically and structurally valid, yet `quantity=0`, the item is out of stock, or the order is already cancelled: **business error**, depending on contract and system policy.
- A message is valid, yet the database temporarily lost connectivity: **transient infrastructure error**, occurring during business processing, not a JSON error.

If you configure infinite retries for a malformed JSON message, the consumer gets stuck on a **poison message**. Conversely, if you immediately send all business errors to a DLQ, you may discard transient errors that would have recovered in seconds.

After this lesson, you will know how to:
1. Break down the message flow into stages and identify **whether an exception happened before or after the business handler**.
2. Distinguish JMS `MessageConversionException`, Spring Messaging `MessageConversionException`, validation errors, and business exceptions.
3. Configure `MessageConverter`, `JmsTemplate`, and `@JmsListener` under a shared data contract.
4. Choose appropriate retry, rollback, dead-letter queue (DLQ), alerting, and malformed-data handling policies.
5. Run a **Java 17 + Spring Boot + Artemis** demo with three deterministic outcomes: success, decoding failure, and business rule failure.

This lesson focuses on **data conversion** at the JMS boundary. Production-level outbox, retry queues, schema registries, or distributed transactions are mentioned where relevant without turning them into blanket defaults for every error.

## 2. Processing Map: Where Can Errors Occur?

~~~text
PRODUCER (source application)
  Java object
      |
      |  ① MessageConverter.toMessage(...)
      v
  JMS Message / Headers
      |
      |  ② MessageProducer.send(...) / broker
      v
──────────────────── JMS broker / Queue ─────────────────────
      |
      |  ③ Session / consumer receives JMS Message
      v
  JMS Message
      |
      |  ④ MessageConverter.fromMessage(...)
      v
  Java Payload / Spring Message
      |
      |  ⑤ Adapter: type resolution / @Payload / @Valid / headers
      v
  @JmsListener(OrderCreated command)
      |
      |  ⑥ Business rules, database, external service
      v
  Success / Failure
      |
      |  ⑦ Transaction, ACK, rollback, redelivery/DLQ
      v
  End of message lifecycle
~~~

| Stage | Typical Error | Initial Classification |
|---|---|---|
| ① Producer → JMS | Unserializable object, unsupported mapping, converter cannot build `TextMessage`/`BytesMessage`. | **Outbound conversion error**; the broker may not have received the message yet. |
| ② Sending via JMS | Bad credentials, non-existent Queue, network interruption, broker resource rejection. | **JMS transport/provider error**; do not conflate with converter errors. |
| ③ Receiving from broker | Timeout, dropped connection, ACK/transaction error. | **Receive/transport error**, usually broker or infrastructure related. |
| ④ JMS → Java | Malformed JSON, schema mismatch, missing type ID, unsupported data type. | **Inbound conversion error**; business logic has not run. |
| ⑤ Adapter/validation | Missing required `@Header`, cannot convert method parameter, `@Valid` fails. | **Argument binding/validation error**; may occur before the method yet not always inside the JMS converter. |
| ⑥ Business handler | Invalid quantity, missing order, insufficient inventory, invalid state, DB timeout. | **Business/infrastructure error**; must be further classified as permanent or transient. |
| ⑦ Commit/ACK | Transaction rollback, broker fails to confirm ACK, reply send failure. | **Completion/infrastructure error**, possibly occurring even after business side effects. |

**Never classify solely by the message "listener failed".** Inspect the root cause, stack trace, execution stage, payload type, and message ID. An outer wrapper exception like `ListenerExecutionFailedException` can mask a cause at the converter layer or in business code.

## 3. Two Different "MessageConversionException" Classes

Spring has **two** classes with the same simple name:

~~~java
org.springframework.jms.support.converter.MessageConversionException
org.springframework.messaging.converter.MessageConversionException
~~~

| Class | Component | Typical Context |
|---|---|---|
| `org.springframework.jms.support.converter.MessageConversionException` | Spring **JMS**; extends `org.springframework.jms.JmsException` (unchecked). | `MessageConverter.toMessage` or `fromMessage` fails to convert Java ↔ JMS Message. |
| `org.springframework.messaging.converter.MessageConversionException` | Spring **Messaging**; extends `MessagingException`. | Converter/adapter using Spring `Message<?>` fails during payload conversion for an annotated handler. |

Both signal a **conversion** failure, yet their packages and classes differ. When writing `catch`, import the right class; when diagnosing logs showing only `MessageConversionException`, read the **fully-qualified class name**.

Other exceptions that may be involved:

- `jakarta.jms.MessageFormatException`: provider API error when reading incompatible JMS content/types.
- `jakarta.jms.JMSException`: checked JMS exception; Spring may translate it into a `JmsException` subclass when using `JmsTemplate`.
- `org.springframework.jms.listener.adapter.ListenerExecutionFailedException`: exception tied to listener/adapter execution that may wrap another error; **inspect `getCause()`**.
- `org.springframework.messaging.handler.annotation.support.MethodArgumentNotValidException` or argument/validation errors: indicates input failed method constraints; the business handler has not necessarily executed.
- `IllegalArgumentException`/custom application exceptions: **insufficient on their own to infer the source**. A custom converter can throw `IllegalArgumentException`, and a business service can also parse JSON incorrectly.

Do not assume all conversion errors share the same exception class. With custom converters, runtime wrappers, and adapters, exact exceptions depend on APIs, Spring versions, and implementations. For uniform handling, design an application taxonomy at the boundary.

## 4. Conversion Errors: Accurate Identification and Stopping Points

### 4.1. Outbound Conversion: Before the Message Is Sent

With `JmsTemplate.convertAndSend(destination, object)`:

~~~java
// Code snippet inside a service with injected JmsTemplate.
jmsTemplate.convertAndSend("sales.orders", orderCreated);
~~~

Spring calls `MessageConverter.toMessage(orderCreated, session)`. If the converter does not support `orderCreated`'s class, Jackson fails to serialize, or the JMS Message cannot be created, the error occurs **in the producer path**. Do not assume "the broker received it, check the DLQ" because no message may have been published.

Distinguish:
- Converter fails **before** `send`: fix producer data/schema/converter and resend under the business event ID.
- `send` was called but outcome is **uncertain** due to timeout: the broker may have received it even if the client missed the ACK. On retry, use idempotency/deduplication; never assert total send failure from a timeout alone.
- Serializer succeeds but payload has wrong semantics: that is not a technical conversion error; run contract/schema validation before publishing.

### 4.2. Inbound Conversion: The Message Is Already on the Queue

On the consumer, `MessageConverter.fromMessage(jmsMessage)` turns `TextMessage`/`BytesMessage` into a Java object or simple type. Common cases:
- Body contains JSON missing a brace or bytes with a mismatched encoding.
- Producer sent an `ObjectMessage` while consumer expects a JSON `TextMessage`.
- Type ID header is missing, wrong, or points to an unpermitted type.
- Java class structure changed so Jackson cannot construct the object.
- Consumer uses a JSON converter while producer still uses `SimpleMessageConverter` under another contract.

Syntactically broken JSON will rarely "heal" by retrying the exact same byte payload. Before calling the handler, the adapter can throw a conversion exception while business logic **has not run**. Never try to fix this by putting `catch (Exception)` at the top of the `@JmsListener` method and ignoring it: the method may not have been invoked yet, so an in-method `catch` **cannot catch** errors thrown by the converter/adapter outside it.

### 4.3. Schema Contracts Matter More Than JSON Syntax Alone

A payload like:

~~~json
{"orderId":"O-202","quantity":0}
~~~

is valid JSON. If the Java class has `String orderId` and `int quantity`, Jackson can construct the object cleanly. Yet `quantity=0` may violate the rule "quantity must be positive" and get rejected by the **business handler**.

Conversely, a payload:

~~~json
{"orderId":"O-202","quantity":"two"}
~~~

can trigger a **conversion failure** if the Java type is `int` and the parser cannot convert `"two"` to a number (exact coercion behavior depends on Jackson configuration). To be certain, define and test coercion/unknown-field policies rather than guessing from JSON that "looks reasonable".

**Valid-looking JSON is not enough to be a valid business event.** At least three contract layers are required:
1. **Syntax/transport:** bytes/`TextMessage` decode cleanly.
2. **Structure/schema:** required fields, types, versions, type IDs, input constraints.
3. **Domain invariants:** order state, inventory, business permissions, transaction limits.

Establish clear boundaries: schema/message-contract errors can be caught at the converter or validation layer; domain errors should only be decided once trustworthy data is available.

## 5. Is a Validation Error a Conversion Error?

**Not necessarily.** A `@JmsListener` with parameter `@Valid @Payload OrderCreated order` can:
- Successfully decode JSON into an object in the converter.
- Then run bean validation checking `@NotBlank`, `@Positive`, or other constraints.
- If a constraint fails, adapter/argument validation raises an error **before the business method runs**.

This differs from both JSON syntax errors and inventory failures inside the service. From a **message processing** standpoint, input validation is usually treated as a **permanent contract/input error**, though in exception class terms it need not be a JMS `MessageConversionException`.

Example distinguishing three states:

| Input | JSON → Java Conversion | Input Validation | Business Logic |
|---|---|---|---|
| `{broken-json` | **Fails** | Does not run | Does not run |
| `{"orderId":"","quantity":0}` | May succeed | **Fails** if `@NotBlank`/`@Positive` applied | Has not run |
| `{"orderId":"O-7","quantity":2}`, but order already closed | Succeeds | Succeeds | **Rejected by domain state** |

When using `@Valid` on listener methods, ensure a bean validator and `DefaultMessageHandlerMethodFactory`/adapter are properly configured; never assume Spring JMS automatically enforces every validation annotation just because a class carries `@NotBlank`.

## 6. Business Errors: Further Separating Permanent and Transient

Once the converter/adapter constructs the payload, business code runs. Two business errors both throw exceptions yet should not share the same policy:

| Category | Example | Recommended Handling |
|---|---|---|
| **Permanent business rejection** | `quantity <= 0`, order state already `CANCELLED`, reference to an invalid object per contract. | Record rejection outcome with reason code; ACK/commit **only when intentionally handled** with audit. Optionally move to parking queue/DLQ if contract requires investigation. |
| **Potentially self-resolving business conflict** | Waiting for a dependent event arriving out of order, locked resource, stale data version. | Bounded retry + backoff or wait for dependent event; never loop infinitely. |
| **Transient infrastructure error** | DB timeout, HTTP 503, secondary broker disconnect. | Rollback/bounded retry, circuit breaker, alerting, and DLQ after exhausting attempts. |
| **Programming bug** | `NullPointerException`, internal mapping bug, wrong domain assumption. | Fix code rather than treating every bug as an input error; temporarily park messages to recover after deploy. |
| **Already-processed idempotent operation** | Redelivery of an `eventId` previously completed. | Can ACK as success after verifying stored outcome without repeating side effects. |

Example domain exception:

~~~java
public final class InvalidOrderQuantityException
        extends RuntimeException {
    public InvalidOrderQuantityException(String id) {
        super("quantity must be positive for " + id);
    }
}
~~~

This is an **application-defined exception type**, not a Spring JMS API. Meaningful exception names make retry/ACK/DLQ decisions much clearer than a generic `IllegalStateException`.

Do not equate "failure inside handler" with "business rejection". A `DataAccessResourceFailureException` from the DB is an infrastructure error occurring while the handler is running; that scenario usually merits retrying, unlike `InvalidOrderQuantityException`.

## 7. Designing MessageConverter to Match the Contract

In Spring Framework 6, interfaces live in `jakarta.jms` (not `javax.jms`). Primary JMS converter:

~~~java
org.springframework.jms.support.converter.MessageConverter
~~~

Two directions:

~~~java
Message toMessage(Object object, jakarta.jms.Session session)
Object fromMessage(jakarta.jms.Message message)
~~~

Both can throw `jakarta.jms.JMSException` or `org.springframework.jms.support.converter.MessageConversionException`, depending on the failure. `JmsTemplate` invokes the configured converter on `convertAndSend`/`receiveAndConvert`. For annotated listeners, the converter must also be wired into the listener adapter/container factory; never assume both sides share the same config if you declare multiple factories manually.

### SimpleMessageConverter

`SimpleMessageConverter` is the default choice in many Spring JMS setups, handling common forms like `String` ↔ `TextMessage`, `byte[]` ↔ `BytesMessage`, `Map` ↔ `MapMessage`, and certain `Serializable` objects. It **does not automatically guess that a JSON String should deserialize into your domain record**.

If a producer sends a `TextMessage` containing `{"orderId":"O-1"}`, a listener taking a `String` parameter receives the raw JSON String and must parse it manually; JSON parsing **inside the method** throws an exception inside the handler even though the root cause is input data. Therefore, classify by **root cause and the stage that actually parsed**, not merely stack-trace location.

### MappingJackson2MessageConverter

Use Spring Framework 6's Jackson 2 converter to convert POJO/record ↔ JSON `TextMessage`:

~~~java
import java.util.Map;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageType;

MappingJackson2MessageConverter converter =
        new MappingJackson2MessageConverter();
converter.setTargetType(MessageType.TEXT);
converter.setTypeIdPropertyName("_type");
converter.setTypeIdMappings(
        Map.of("order.created.v1", OrderCreated.class));
converter.setTrustedPackages("example.jms"); // Spring Framework 6.2.19+
~~~

This is a **configuration snippet**, assuming `OrderCreated` exists. `setTypeIdPropertyName("_type")` is critical: on receive, the converter needs to know the target Java type. `setTypeIdMappings` lets you use a **stable ID** like `order.created.v1` rather than forcing producers to send internal Java class names. `setTargetType(TEXT)` makes inspecting JSON bodies convenient in broker tools.

**Security:** with brokers or producers that are not fully trusted, never allow arbitrary type IDs to trigger deserialization of unpermitted classes. Spring Framework **6.2.19+** adds `setTrustedPackages(...)` and patches Jackson JMS converter deserialization issues (CVE-2026-41855); use a patched version, allowlist IDs/types/packages, and restrict publish permissions. Type ID mapping should be an explicit contract, not a gateway for arbitrary class selection.

## 8. Runnable Demo: Three Different Cases on the Same Queue

Demo goals:
- Use **Spring Boot 3.5.16** (BOM managing **Spring Framework 6.2.19**), Java 17, and embedded Artemis.
- Use `MappingJackson2MessageConverter` to produce a `TextMessage` containing JSON and the `_type` JMS property.
- Send three messages sequentially, and after each send **receive the raw JMS Message**, invoke the converter explicitly, and run business rules.
- Print three deterministic outcomes so learners **see at which layer each error occurs**.

**Intentional limitation note:** the example uses `JmsTemplate.receive(...)` and invokes the converter **after receiving** to observe both error paths directly, so it cannot demonstrate production `@JmsListener` rollback/redelivery behavior. Under `AUTO_ACKNOWLEDGE`, a message already returned by `receive()` that subsequently fails conversion may already be ACKed. Later sections show how to configure listener transactions for real systems.

### 8.1. Structure

~~~text
jms-error-boundary/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── resources/application.yml
    └── java/example/jms/ErrorBoundaryApplication.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-error-boundary'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
    implementation 'org.springframework.boot:spring-boot-starter-json'

    // Embedded server is for lab use only; not needed with a remote broker.
    runtimeOnly 'org.apache.activemq:artemis-jakarta-server'
}
~~~

If a production project uses another Spring Boot version, use the matching dependency BOM and supported branch; do not mix arbitrary Spring Framework/Jackson/Artemis versions. Spring Boot 3.5.16 is chosen for reproducible demo execution, **not as a default security baseline for all future projects**.

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: embedded
    embedded:
      queues: demo.orders
      persistent: false
~~~

### 8.2. Java 17: Complete Single File

`src/main/java/example/jms/ErrorBoundaryApplication.java`:

~~~java
package example.jms;

import java.util.Map;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageConversionException;
import org.springframework.jms.support.converter.MessageConverter;
import org.springframework.jms.support.converter.MessageType;

@SpringBootApplication
public class ErrorBoundaryApplication {
    private static final String QUEUE = "demo.orders";
    private static final String TYPE_ID = "order.created.v1";

    // Java 17 record; Jackson recognizes orderId/quantity components.
    public record OrderCreated(String orderId, int quantity) {}

    static final class InvalidQuantity extends RuntimeException {
        InvalidQuantity() {
            super("quantity must be positive");
        }
    }

    public static void main(String[] args) {
        SpringApplication.run(ErrorBoundaryApplication.class, args);
    }

    @Bean
    MessageConverter jmsMessageConverter() {
        MappingJackson2MessageConverter converter =
                new MappingJackson2MessageConverter();
        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("_type");
        converter.setTypeIdMappings(Map.of(TYPE_ID, OrderCreated.class));
        converter.setTrustedPackages("example.jms");
        return converter;
    }

    @Bean
    JmsTemplate jmsTemplate(
            ConnectionFactory connectionFactory,
            MessageConverter jmsMessageConverter) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setMessageConverter(jmsMessageConverter);
        template.setReceiveTimeout(3_000L);
        return template;
    }

    @Bean
    ApplicationRunner runCases(
            JmsTemplate template, MessageConverter converter) {
        return args -> {
            // 1. Valid JSON created by converter + valid business rule.
            template.convertAndSend(QUEUE,
                    new OrderCreated("O-100", 2),
                    message -> {
                        message.setJMSCorrelationID("case-1");
                        return message;
                    });
            classifyOnce(template, converter);

            // 2. Send malformed JSON TextMessage via MessageCreator.
            // send(...) does not invoke converter.toMessage(...) for this body.
            template.send(QUEUE, session -> {
                TextMessage raw =
                        session.createTextMessage("{invalid-json");
                raw.setStringProperty("_type", TYPE_ID);
                raw.setJMSCorrelationID("case-2");
                return raw;
            });
            classifyOnce(template, converter);

            // 3. Valid JSON (quantity=0), yet violates business rule.
            template.convertAndSend(QUEUE,
                    new OrderCreated("O-102", 0),
                    message -> {
                        message.setJMSCorrelationID("case-3");
                        return message;
                    });
            classifyOnce(template, converter);
        };
    }

    private static void classifyOnce(
            JmsTemplate template, MessageConverter converter)
            throws JMSException {
        Message raw = template.receive(QUEUE);
        if (raw == null) {
            throw new IllegalStateException("receive timed out");
        }

        String correlationId = raw.getJMSCorrelationID();

        try {
            Object payload = converter.fromMessage(raw);
            if (!(payload instanceof OrderCreated order)) {
                throw new IllegalStateException(
                        "unexpected payload type");
            }

            applyBusinessRule(order);
            System.out.println(
                    "ACCEPTED|" + correlationId + "|" + order.orderId());

        } catch (MessageConversionException ex) {
            System.out.println("CONVERSION_ERROR|" + correlationId);

        } catch (InvalidQuantity ex) {
            System.out.println(
                    "BUSINESS_ERROR|" + correlationId
                    + "|" + ex.getMessage());
        }
    }

    private static void applyBusinessRule(OrderCreated event) {
        if (event.quantity() <= 0) {
            throw new InvalidQuantity();
        }
    }
}
~~~

**Why do the outcomes differ?**
- `case-1`: `convertAndSend` uses Jackson to produce valid JSON and type ID. `fromMessage` instantiates `OrderCreated`; `applyBusinessRule` accepts `quantity=2`.
- `case-2`: raw `TextMessage` is sent directly with `_type=order.created.v1` and body `{invalid-json`. Jackson reads the valid type ID, then fails to parse JSON and throws JMS `MessageConversionException`. **`applyBusinessRule` does not run.**
- `case-3`: JSON body and type ID are valid; conversion into the record succeeds. `applyBusinessRule` checks `quantity=0` and throws `InvalidQuantity`. **This is a business error, not a conversion error.**

### 8.3. Running

From the project directory, use JDK 17+ and a compatible Gradle. If Gradle Wrapper is present:

~~~bash
./gradlew bootRun
~~~

If without a Wrapper, use an installed Gradle:

~~~bash
gradle bootRun
~~~

On Windows PowerShell, with Wrapper:

~~~powershell
.\gradlew.bat bootRun
~~~

After Spring Boot and Artemis logs, the demo code prints exactly three lines (in the order of send/receive calls in the Runner):

~~~text
ACCEPTED|case-1|O-100
CONVERSION_ERROR|case-2
BUSINESS_ERROR|case-3|quantity must be positive
~~~

Startup logs, thread names, and timestamps from Spring/Artemis depend on the environment and are not part of the fixed output. The demo intentionally **does not** reuse failed messages and defines no competing `@JmsListener`, so the run only observes the decode step and business rule without evaluating redelivery/retries. `persistent: false` is for lab use only and does not prove durability.

### 8.4. Key Points When Moving from Demo to Production

In the demo, `JmsTemplate.receive` fetches the raw message and then manually calls `converter.fromMessage`. With `receiveAndConvert`, the template performs conversion inside the method. Neither replaces a listener container with transaction/ACK policies and a DLQ.

Never copy the demo's `catch (MessageConversionException)`-and-print-log pattern as a production consumer policy. In a real system, if a message is ACKed without recording/quarantining it, you can lose failure evidence and cannot replay it after fixing the producer.

## 9. `@JmsListener`: The Converter Can Fail Before the Method Is Called

Example listener receiving a record:

~~~java
package example.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {
    private final OrderService service;

    public OrderListener(OrderService service) {
        this.service = service;
    }

    @JmsListener(destination = "orders.incoming")
    public void onOrder(OrderCreated event) {
        service.handle(event);
    }
}
~~~

This is an **illustrative snippet**: `OrderCreated` and `OrderService` are application-provided types, and an appropriate listener factory/converter is required. For malformed JSON or unresolvable type IDs, the converter/adapter may throw **before `onOrder(...)`** is entered; logging at the start of the method will never capture that case.

Conversely, if `onOrder(...)` runs and `service.handle(event)` throws `OrderRejectedException`, the failure is on the business path. A handler method returning a result whose **reply conversion** fails can also produce a conversion error **after** business logic has executed — in that case side effects may already have occurred, requiring special attention to transactions/idempotency.

### Illustrative Listener Container Configuration

~~~java
@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory,
        MessageConverter jmsMessageConverter) {

    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setMessageConverter(jmsMessageConverter);

    // Method invocation and message receipt share a local JMS transaction.
    factory.setSessionTransacted(true);
    factory.setConcurrency("1-3");
    return factory;
}
~~~

This bean snippet requires importing `jakarta.jms.ConnectionFactory`, `org.springframework.context.annotation.Bean`, `org.springframework.jms.config.DefaultJmsListenerContainerFactory`, and `org.springframework.jms.support.converter.MessageConverter` inside a `@Configuration` class with `@EnableJms` when using plain Spring Framework. With Boot, check auto-configuration and factory selection before redeclaring. Name the bean `jmsListenerContainerFactory` if `@JmsListener` does not specify a factory.

**Important:** `setSessionTransacted(true)` lets message receipt roll back if listener processing fails within a local JMS transaction (when using a compatible container). However, retry count, redelivery delay, DLQ, and when retries stop are **broker/container policies** that must be verified. Nothing in the snippet above automatically enforces "max three tries then DLQ".

### `ErrorHandler` Is Not an "ACK Message" Button

You can configure an `ErrorHandler` on the listener container for logging/metrics on escaping exceptions; however, do not infer that adding an `ErrorHandler` alone automatically classifies poison messages, ACKs, rolls back, or routes to a DLQ. Transaction scope, where exceptions are caught/rethrown, and broker policies determine the outcome. Integration tests with the specific JMS provider are required.

## 10. Common Exception-Handling Mistakes

### Mistake 1: Catching Too Broadly and Swallowing Errors

~~~java
@JmsListener(destination = "orders.incoming")
public void onOrder(OrderCreated event) {
    try {
        service.handle(event);
    } catch (Exception ex) {
        log.error("failed to process order", ex);
        // Not rethrowing: the container may treat the invocation as successful.
    }
}
~~~

In the snippet above, `service` and `log` are application components; this is only an illustration. With a transacted session, if a handler **swallows an exception** and returns normally, the container may commit/ACK the message, preventing a transient error from being retried. At the same time, that `catch` block cannot handle errors occurring in the converter **before the method runs**.

**Fix:** explicitly decide which exceptions represent final business outcomes (with audit/outcome recording) and which must continue failing so the container rolls back. Never treat every exception as success, nor infinitely retry permanent input errors.

### Mistake 2: Catching Every Conversion Error and Manually Publishing to a New DLQ

Without a transaction/outbox setup, "catch, publish to a new queue, then ACK the old queue" can lose data in between the two steps. Furthermore, broker policies already provide DLQ/redelivery; manual forwarding can create duplicates or loops.

**Fix:** use broker-appropriate dead-letter/parking mechanisms, or ensure forwarding shares an appropriate transaction with event ID, attempt count, reason code, and controlled replay.

### Mistake 3: Catching `JsonProcessingException` in Business Code and Labeling It a Business Error

~~~java
public void onOrder(String json) throws Exception {
    OrderCreated event = objectMapper.readValue(
            json, OrderCreated.class);
    service.handle(event);
}
~~~

This example parses JSON **inside the handler** because it chose a `String` parameter. The root cause of a `readValue` failure is **data conversion/input**, even though the stack trace originates inside the method. You can refactor to use an explicit JMS `MessageConverter`, or separate a `parse` function before `handleDomain`. This snippet assumes `objectMapper`, `OrderCreated`, and `service` exist in the app.

### Mistake 4: Calling `@Valid` Failures "Jackson Errors"

JSON may deserialize into an object normally and only fail validation afterward. Distinguish the error type and failure stage; use codes like `SCHEMA_INVALID` or `ARGUMENT_VALIDATION_FAILED` where appropriate instead of always logging `JSON_PARSE_ERROR`.

### Mistake 5: Treating `IOException`, `JMSException`, or Timeouts as Business Rejections

Connectivity/broker/DB timeout errors may be transient and benefit from retries. Never assign root cause solely from a calling context named "OrderService" without checking the exception chain, transaction state, and telemetry.

## 11. Retry / Rollback / DLQ Policy by Error Type

No single default policy fits all systems, yet the table below is a pragmatic starting point:

| Outcome Type | Retry? | Suggested ACK / Rollback / Parking |
|---|---|---|
| Malformed JSON syntax, unresolvable missing type ID | **Never infinitely retry the same message**. | Park/DLQ with code `CONVERSION_ERROR` and diagnostic metadata; enforce access control and avoid logging sensitive payloads. |
| Schema incompatibility after deployment | Potentially **recoverable via code/schema migration**. | Park/dead-letter with management and replay once converter is fixed; retain message ID/business ID. |
| Permanent input validation failure | Usually do not retry identical data. | Record rejection/audit; ACK or park per contract. |
| Final business rule rejection | Do not retry if immutable; optionally emit rejection event. | Record outcome once; ACK after completing the rejection behavior. |
| Business dependency not yet ready | Conditional retry if self-healing is expected. | Backoff/jitter, max attempts, DLQ once threshold exceeded. |
| DB/HTTP/broker timeout | Usually bounded retry. | Rollback within appropriate transaction; idempotency before side effects. |
| Post-deployment code bug | Continuous retries rarely help until a fix ships. | Alert, cap attempts, park messages, replay after deploy. |

### Why Not Let Every Exception Roll Back Forever?

For a permanently corrupted message, if the container rolls back and the broker redelivers endlessly, the consumer can spike CPU, spam logs, and starve valid messages. For an immutable business error, continuous retries will never succeed either.

A practical poison-message policy needs:
- **Max delivery attempts** and redelivery delay/backoff.
- Dedicated DLQ/parking with proper access controls and controlled replay operations.
- Recorded reason taxonomy and schema/converter versions.
- Metrics for conversion failure rates and stuck message counts per Queue/producer.
- Never "ACK and drop" unless the contract explicitly defines that as a final outcome with required auditing.

### Notes on ACK/Transactions

- For listeners using a local JMS transaction, an exception escaping the invocation usually rolls back the transaction, allowing the broker to apply its redelivery policy.
- For `AUTO_ACKNOWLEDGE` without a transaction, the message may already be ACKed **before or during** the callback depending on container/receive mode; never assume throwing an exception always triggers redelivery.
- With `JmsTemplate.receive` followed by manual processing, ACK may have already occurred before the converter, as shown in the demo.
- A database transaction and a JMS transaction are not automatically one transaction; committing DB then rolling back JMS can cause duplicate side effects. Use idempotency, outbox/inbox, or XA/JTA when genuinely required and supported by infrastructure.

**Nothing here promises end-to-end exactly-once.** Business-level once-only processing typically relies on unique keys, transactional persistence, and deduplication.

## 12. Observability: Log the Exact Cause Without Leaking Data

A system with dozens of Queues should standardize log/metric fields for every error:

| Field | Purpose |
|---|---|
| `JMSMessageID` / event ID | Correlate broker, producer, and consumer; never assume `JMSMessageID` is a business idempotency key. |
| `JMSCorrelationID` | Link request/reply pairs, trace transactions, or workflows. |
| Destination / subscriber / consumer group | Identify the responsible Queue/Topic and component. |
| Schema name/version and type ID | Identify which data contract failed. |
| `errorStage` | `PRODUCER_CONVERSION`, `CONSUMER_CONVERSION`, `ARGUMENT_VALIDATION`, `BUSINESS_RULE`, `INFRASTRUCTURE`, or `ACK_COMMIT`. |
| `errorCode` / exception cause | Stable code for alerting and routing, e.g. `INVALID_JSON`, `UNKNOWN_TYPE_ID`, `ORDER_REJECTED`, `DB_TIMEOUT`. |
| Delivery count | Read `JMSXDeliveryCount` if supplied by the provider and present; verify semantics per broker. |
| Outcome and retry policy | `REJECTED`, `RETRYING`, `PARKED`, `COMPLETED`; backoff/max attempts. |

Never log full JSON containing personal data, tokens, payment details, or sensitive stack traces to unauthorized systems. For debugging converters, store **controlled/redacted/encrypted payloads** in short-lived quarantine storage with retention and audit controls. Never log unbounded raw bodies from untrusted producers.

### Distinguishing via Stack Trace

Example of two cause chains (structural illustration, not verbatim vendor output):

~~~text
ListenerExecutionFailedException
  caused by MessageConversionException (Spring JMS)
    caused by JsonParseException
→ CONSUMER_CONVERSION: handler has not run
~~~

~~~text
ListenerExecutionFailedException
  caused by InvalidOrderQuantityException
→ BUSINESS_RULE: handler was invoked
~~~

Walk `getCause()` across multiple levels alongside a marker of "whether the handler was entered"; never assign taxonomy by substring-matching an error message. Watch out for other exceptions wrapping `MessageConversionException`, or JSON parsing done manually inside the business handler.

## 13. Testing Both Producer and Consumer

A minimal test suite should include:

| Test | Input / Trigger | Expected Outcome |
|---|---|---|
| **Valid happy path** | Valid JSON accepted by domain. | Converts cleanly, service runs once per test, ACK/commit. |
| **Outbound conversion** | Producer serializes unsupported object. | Not treated as business rejection; verify broker publish happens/skips per error boundary. |
| **Malformed JSON** | Syntactically broken `TextMessage` with valid type ID. | Reports conversion stage; business handler does not run. |
| **Missing type ID** | Valid JSON without `_type`. | Converter reports target type cannot be resolved (with converter configured as in example). |
| **Wrong type / schema** | Unsupported type ID or wrong field types. | Classified as contract/schema error; never auto-invokes domain. |
| **Input validation** | Valid JSON violating `@Valid`. | Object constructed, yet method does not run; separate reason. |
| **Business permanent** | `quantity=0` or disallowed order status. | Service ran; rejected per contract, no infinite retries. |
| **Business transient** | Recoverable DB timeout. | Bounded rollback/redelivery; side effects not duplicated. |
| **Listener transaction** | `sessionTransacted=true` and throw from handler. | Verify real broker rollback, redelivery, and DLQ. |
| **Reply conversion** | Handler finishes yet response object fails to serialize. | Marked as post-business error; protect idempotency/reply semantics. |
| **Recovery/migration** | Deploy new converter accepting older schema. | Controlled replay; failed messages not lost before fix. |

**Key point:** do not unit test Java methods alone. Run integration tests with **the actual JMS provider/driver, acknowledgement mode, and listener factory** used in production. A "conversion failed" log in a lab does not tell you whether a message will be redelivered in production.

### Unit Tests Without a Broker

You can test `MessageConverter` directly with mocked/stubbed messages (or an isolated embedded provider), and extract domain logic into a pure Java service to test quantity/state transitions without JMS. However, when verifying ACK, transactions, DLQ, or retries, converter unit tests alone are **insufficient**.

## 14. Design Checklist Before Merging Code

- [ ] Clearly separated outbound conversion, broker transport, inbound conversion, validation, business logic, and commit/ACK boundaries.
- [ ] Selected a payload contract (`TextMessage` JSON, `BytesMessage`, or other) with explicit schema/version/type ID.
- [ ] `JmsTemplate` and listener factory use compatible converters; verified against real payloads from other producers.
- [ ] No arbitrary class deserialization from untrusted type IDs; Spring upgraded to patched release with type/package allowlists.
- [ ] Business handlers do not arbitrarily re-parse JSON without classifying data-input causes.
- [ ] Meaningful business exceptions distinguish permanent rejections from transient errors.
- [ ] Retry/backoff/max-attempt rules, DLQ/parking, and replay strategies defined.
- [ ] Consumer transaction/ACK semantics tested; no unintentional exception swallowing.
- [ ] Business operations are idempotent across redeliveries after timeouts/rollbacks.
- [ ] Observability includes `errorStage`, message ID, schema version, delivery attempts; no secrets logged.
- [ ] Tested malformed payloads, missing type IDs, validation failures, business rejections, and DB/network failures.
- [ ] Never treat `STATUS=sent`/HTTP 202 or a success logger as proof that the business handler completed.

## 15. Self-Check Questions

**Question 1.** Consumer receives a `TextMessage` with body `{bad-json`, and Jackson's converter throws `MessageConversionException` before `@JmsListener` is called. Which category is this?

**Answer:** Inbound conversion error. The domain method has not run; infinite retries on the same byte payload are futile. Investigate producer/schema, park/DLQ, and replay after fixing.

**Question 2.** JSON `{"orderId":"O-30","quantity":0}` deserializes into `OrderCreated`, and then `OrderService` throws `InvalidOrderQuantityException`. Is this a converter error?

**Answer:** No. The converter finished; a business rule rejected the data. If minimum positive quantity is part of the contract, the constraint can move to pre-handler validation while explicitly recording the detection layer.

**Question 3.** A `@JmsListener(String rawJson)` handler calls Jackson directly and hits `JsonParseException`. Should it be logged as `BUSINESS_RULE_ERROR` just because it occurred inside the handler?

**Answer:** No. The true cause is data conversion/input. Classify by the parsing step, and consider refactoring to use a `MessageConverter` before the domain service.

**Question 4.** Can a service catch `org.springframework.messaging.converter.MessageConversionException` and `org.springframework.jms.support.converter.MessageConversionException` as the same class?

**Answer:** No. The two types have different packages and hierarchies; classify accurately using fully qualified names or the cause chain, and avoid ambiguous imports.

**Question 5.** Why does `sessionTransacted=true` not automatically guarantee a bad message goes to the DLQ after exactly three attempts?

**Answer:** It governs listener transactions/rollbacks. Redelivery counts, delays, and DLQ routing depend on broker/provider configuration and additional policies.

**Question 6.** A DB timeout occurs after the converter succeeds and before business processing completes. Should it be treated as a "permanent business rejection"?

**Answer:** No. It is a transient infrastructure error occurring along the business processing path; consider bounded retries, backoff, idempotency, and alerting.

**Question 7.** A conversion exception was caught when calling `JmsTemplate.receive()` under `AUTO_ACKNOWLEDGE` and logged. Will the message automatically return to the Queue?

**Answer:** You cannot assume so. `receive()` may have already ACKed before the converter step; test actual semantics, use appropriate listener transactions, and apply a quarantine policy rather than expecting a catch block to roll back.

## 16. Official Documentation

- [Spring Framework 6.2 — Using JMS and MessageConverter](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html).
- [Spring Framework 6.2 — Receiving a Message, listener transactions and ACK](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html).
- [Spring Framework 6.2 — Annotation-driven JMS listener endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html).
- [Spring Framework 6.2.19 — JMS MessageConverter interface](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/converter/MessageConverter.html).
- [Spring Framework 6.2.19 — JMS MessageConversionException](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/converter/MessageConversionException.html).
- [Spring Framework 6.2.19 — MappingJackson2MessageConverter](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html).
- [Spring Framework 6.2.19 — Spring Messaging MessageConversionException](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/messaging/converter/MessageConversionException.html).
- [Spring Boot — Messaging with JMS: Artemis, JSON converter, and listener](https://spring.io/guides/gs/messaging-jms/).
- [Spring Boot 3.5.16 — Managed dependency coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html).
- [Spring Security Advisory CVE-2026-41855 — Jackson JMS deserialization](https://spring.io/security/cve-2026-41855/).
- [Jakarta Messaging 3.1 specification — JMS Message and semantics](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html).
