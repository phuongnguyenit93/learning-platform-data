# Conversion or Validation Errors Before Business Code Runs in Spring JMS

> **Module:** Spring Framework – JMS  
> **Group:** Listener Data  
> **Focus:** Why a message has reached the `@JmsListener` container yet the business method **was never invoked**, how to pinpoint which layer failed, and how to design safe rollbacks, retries, and DLQs.

## Learning Objectives

After this lesson, you will be able to:

1. Trace the processing chain from `jakarta.jms.Message` → wire payload conversion → Spring `Message<?>` → argument resolution → Bean Validation → invoking the `@JmsListener` method.
2. Distinguish **conversion errors**, **header/method-argument errors**, and **validation errors** occurring **before** the first line of the business method executes.
3. Recognize that `spring-jms`'s `MessageConversionException` differs from Spring Messaging conversion errors, and that `MethodArgumentNotValidException` may be wrapped in `ListenerExecutionFailedException`.
4. Configure converters and `@Payload @Valid` using `DefaultJmsListenerContainerFactory`, `JmsListenerConfigurer`, `DefaultMessageHandlerMethodFactory`, and an actually working `Validator`.
5. Explain why a `try/catch` **inside the listener method body** cannot catch errors thrown before the method is invoked.
6. Understand the exact effects of `sessionTransacted=true`, `AUTO_ACKNOWLEDGE`, redelivery, broker DLQs, and `ErrorHandler`, without claiming every exception automatically goes to a DLQ.
7. Separate permanent data errors (poison messages) from transient infrastructure errors to apply bounded retries, quarantine, and controlled fix/replay mechanisms.
8. Test two representative scenarios: syntactically invalid JSON and a JSON-valid DTO violating `@NotBlank`/`@Positive`, while proving the business method never ran.
9. Observe errors directly at the adapter/container layer, along with correlation ID, message type/schema, root-cause error, and delivery count without logging sensitive payloads.

## 1. Nature of the Problem: Message Exists Yet Handler Never Runs

A common operational failure in Spring JMS:

> The broker shows the message was delivered (or increments delivery count), the listener container is running, yet no log appears from the first line of `@JmsListener`. On the broker side, the message may repeat, increment redelivery count, or land in the DLQ.

It is not necessarily due to networking or business code "swallowing exceptions." A **listener method with typed parameters** must be prepared by Spring before invocation. If preparing arguments fails, the method **is never called even once**.

```text
JMS Broker
   |
   | 1. Deliver jakarta.jms.Message
   v
DefaultMessageListenerContainer / Session
   |
   | 2. MessagingMessageListenerAdapter
   |    -> JMS MessageConverter (body + metadata)
   v
Spring Message<?> (payload + headers)
   |
   | 3. Resolve method arguments
   |    -> @Payload / @Header / MessageConverter / target type
   v
Typed Java arguments
   |
   | 4. @Valid / @Validated if Validator present
   |    -> Bean Validation constraints
   v
@JmsListener method body
   |
   | 5. Business validation, database, outbound calls...
   v
Ack / commit or rollback per container policy
```

**Three pre-method failure points:**

- **Step 2:** Unable to convert a JMS TextMessage/BytesMessage/MapMessage to a Java payload, malformed JSON, missing type-id, unmapped type-id, or mismatched body type.
- **Step 3:** Unable to turn the decoded payload into the parameter type `OrderCreated`, missing required header, wrong `@Header int` type, or no suitable converter.
- **Step 4:** The Java DTO was constructed, yet it violates `@Valid` constraints such as empty `orderId` or non-positive `quantity`.

**Step 5** is where your own application code inside the method begins. You must identify the failing path before choosing a fix. An exception from conversion/validation can be thrown back to the container by the adapter **without the method body ever executing**.

## 2. "Before Business" Does Not Mean "Before JMS Receive"

There are three distinct events:

1. The broker delivers the message to the JMS consumer/session.
2. The Spring adapter converts, resolves arguments, and validates to prepare calling the handler.
3. The application method is invoked and executes side effects.

If failure happens at (2), the broker/provider and container **may already have counted that as a delivery attempt**. Consequently:

- The message may have transitioned from ready to in-flight inside the broker.
- The transaction may roll back, leading to redelivery of that message.
- `JMSRedelivered` or `JMSXDeliveryCount` may change on redelivery, depending on support and policies.
- No "handler started" log is emitted, yet the message could still be consumed/acked if the container uses an acknowledgment mode unsuitable for retries.
- Do not infer from `handlerCallCount=0` that the broker never sent the message.

**"Before" here strictly means before the business method body runs**, not before the message left the broker.

### 2.1. Two Ways to Write a Listener for Two Control Levels

Listener receiving a raw JMS Message:

```java
@JmsListener(destination = "orders.in")
public void raw(jakarta.jms.Message message) {
    // Application checks JMS type and reads body manually.
}
```

Listener receiving a typed DTO:

```java
@JmsListener(destination = "orders.in")
public void typed(@Payload @Valid OrderCreated order) {
    // Spring must prepare OrderCreated and validate before entering here.
}
```

These are **two separate illustrative signatures**. If both are registered on the same Queue, they become competing consumers; both will not see every message. A raw listener reduces automatic pre-handler conversion, shifting decoding/validation responsibility into **business code or a dedicated adapter**. Neither handler style is "universally safe."

### 2.2. @Valid Can Prevent the Method from Being Invoked

When a `@Payload` argument passes through `PayloadMethodArgumentResolver` with a configured `Validator`, the resolver checks constraints before calling the method. Violations can throw `org.springframework.messaging.handler.annotation.support.MethodArgumentNotValidException`. At the JMS adapter layer, the exception may be wrapped in `ListenerExecutionFailedException`, so container logs often show an outer **wrapper** and an inner **root cause**.

Never look solely at the top-level exception line and blame the business handler. Trace the `cause` chain and conversion/argument-resolver stack frames.

## 3. Classifying Error Types by Stage

| Stage | Example error | Did method body run? | What to check |
| --- | --- | --- | --- |
| JMS consumer receive | Broker connection lost, destination/permission error | No | Network, credentials, broker, container recovery |
| JMS wire conversion | TextMessage contains malformed JSON | **No** | JMS converter, payload, schema, encoding |
| JMS wire conversion | Missing/unknown `_type` for Jackson JMS converter | **No** | Type-id property, allowlist mapping, version |
| JMS wire conversion | BytesMessage received by converter expecting TextMessage | **No** | JMS message subtype, converter target type |
| Spring argument resolution | Payload is String yet handler demands DTO with no converter | **No** | Spring Messaging converter, target type |
| Header binding | `@Header("attempt") int n` with missing/mistyped header | **No** | JMS/Spring header mapping, required flag |
| Bean Validation | DTO has `quantity=0` violating `@Positive` | **No** | `@Valid`, Bean Validation provider, validator |
| Method invoked, app guard rejects | `if (order.invalid()) throw ...` | **Already started** | Business rules, application exception |
| Method invoked, DB timeout | Transaction/resource failure | **Already started** | DB metrics, transactions, retries |
| Return-value/reply conversion | Method returns DTO yet converter fails to serialize reply | **Method already ran** | Return converter, `@SendTo`/`JMSReplyTo` |

**Separate inbound and outbound clearly.** This lesson focuses on **pre-invocation inbound** errors. Response conversion errors only happen **after** the method body, so they must not be diagnosed under the same "business code never ran" symptom.

## 4. JMS Wire Conversion Layer: Data from Broker Not Yet a DTO

Objects from the provider are `jakarta.jms.Message` and subtypes such as `TextMessage`, `BytesMessage`, and `MapMessage`.

Spring's JMS converter lives in package:

```text
org.springframework.jms.support.converter.MessageConverter
```

Two key methods:

```java
jakarta.jms.Message toMessage(Object object, jakarta.jms.Session session)
        throws jakarta.jms.JMSException;

Object fromMessage(jakarta.jms.Message message)
        throws jakarta.jms.JMSException;
```

These are **abbreviated signatures for learning concepts**: the real API also declares conversion exceptions. On inbound, `fromMessage` must decode the JMS message into a Java payload. It can fail **before** the annotated handler is invoked.

### 4.1. SimpleMessageConverter Does Not Automatically Parse JSON into a Record

The default JMS converter is usually:

```text
org.springframework.jms.support.converter.SimpleMessageConverter
```

It converts simple forms: `TextMessage` → `String`, `BytesMessage` → `byte[]`, `MapMessage` → map, and `ObjectMessage` per supported policies. If the broker holds:

```json
{"orderId":"ORD-42","quantity":2}
```

as a **JMS TextMessage**, `SimpleMessageConverter` typically returns a **JSON String**, not `OrderCreated`.

If the handler declares:

```java
public void onOrder(OrderCreated order)
```

another conversion step is needed to turn the String into a DTO, or a JSON converter must be placed at the **JMS wire layer**. Never assume merely putting a DTO type in the signature causes every framework to automatically invoke Jackson.

### 4.2. JMS MappingJackson2MessageConverter Needs Two-Way Type-IDs

With **Spring Framework 6.2.x/Jackson 2**, Spring provides:

```text
org.springframework.jms.support.converter.MappingJackson2MessageConverter
```

It supports JSON → Java DTO on inbound; typically requiring:

```java
converter.setTargetType(MessageType.TEXT);
converter.setTypeIdPropertyName("_type");
converter.setTypeIdMappings(Map.of(
        "order-created-v1", OrderCreated.class));
```

`setTypeIdPropertyName("_type")` plays a crucial role **when receiving**: the converter needs the type-id to select the Java class. If a producer sends a TextMessage with JSON yet **forgets `_type`**, or the id is not in the mappings, conversion fails right at the adapter.

Using **allowlisted logical type IDs** reduces coupling to Java package/class names. Never let untrusted senders dictate arbitrary Java classes via raw class names.

### 4.3. JSON Parse Errors and Validation Errors Are Completely Different

Example 1 — Syntactically malformed JSON:

```text
{ "orderId": "ORD-42", "quantity":
```

Jackson cannot construct an object. This is a **conversion error**; Bean Validation has no DTO to inspect yet.

Example 2 — Valid JSON violating constraints:

```json
{"orderId":"","quantity":0}
```

Jackson can instantiate `OrderCreated("", 0)`; then `@Valid` catches `@NotBlank` and `@Positive`. This is a **validation error**, not a JSON syntax error.

Example 3 — Valid JSON with wrong field type:

```json
{"orderId":"ORD-42","quantity":"abc"}
```

Jackson fails converting String to a number; depending on coercion settings, the failure occurs during conversion. Avoid assuming every type-mismatch error is a `MethodArgumentNotValidException`.

### 4.4. Encoding and Message Subtypes Are Also Part of the Contract

If the producer switches to `BytesMessage` while the receiver tries to read `TextMessage`, the converter may not support it. If bytes are not valid UTF-8 matching the schema, or are compressed without the receiver decompressing them, conversion also fails.

A wire contract must specify:

- Queue/topic and message subtype.
- Content type/schema format.
- Encoding, compression, size limits.
- Type ID, schema version, and backward compatibility.
- Required properties and null/missing rules.
- Classes permitted for deserialization.

A newer consumer version cannot automatically read every older message if the wire contract breaks compatibility. Producer/consumer compatibility tests are needed before rollout.

## 5. Spring Messaging Layer: Resolving Arguments Before the Handler

Annotated endpoints in Spring use the Spring Messaging abstraction to invoke Java methods:

```text
org.springframework.messaging.Message<?>
org.springframework.messaging.handler.annotation.Payload
org.springframework.messaging.handler.annotation.Header
org.springframework.messaging.handler.annotation.support
        .DefaultMessageHandlerMethodFactory
```

**Easily confused package differences:**

| Component | Primary package | Role |
| --- | --- | --- |
| JMS `MessageConverter` | `org.springframework.jms.support.converter` | Java payload ↔ `jakarta.jms.Message` |
| Messaging `MessageConverter` | `org.springframework.messaging.converter` | Spring `Message<?>` ↔ target Java type |
| `MessagingMessageConverter` | `org.springframework.jms.support.converter` | Bridge JMS ↔ Spring Message/headers |
| `DefaultMessageHandlerMethodFactory` | `org.springframework.messaging.handler.annotation.support` | Creates invoker/resolvers, converter, validator for methods |
| `@Payload` | `org.springframework.messaging.handler.annotation` | Marks the payload argument |
| `@Header` | `org.springframework.messaging.handler.annotation` | Extracts a header argument |
| `@Valid` | `jakarta.validation` | Requests Bean Validation on the argument |

Here there are **two interfaces sharing the simple name `MessageConverter`** with different signatures. Changing the converter on the producer's `JmsTemplate` does not automatically configure the listener's converter, and changing the converter in `DefaultMessageHandlerMethodFactory` does not make an invalid JMS TextMessage valid.

### 5.1. Issues with @Header

Example:

```java
@JmsListener(destination = "orders.created")
public void handle(
        @Payload String orderId,
        @Header("tenantId") String tenantId,
        @Header("attempt") int attempt) {
    // Only enters the method when Spring resolves all arguments.
}
```

If `tenantId` is missing (and the header is treated as required), or `attempt` is `"oops"` while the handler expects `int`, Spring can fail right in the argument resolver. Thus, even a **valid payload** does not guarantee the method body will run.

For optional headers:

```java
@Header(name = "tenantId", required = false) String tenantId
```

When a header is missing, handle null/defaults explicitly. Never use primitive `int` for an optional header without a default if absence must be supported; use `Integer` or a tested default value convention.

**Note:** JMS headers and Spring `MessageHeaders` are not completely identical. `JmsHeaderMapper` controls mapping. A custom JMS property with an unsupported name/type may not appear under the key the handler expects.

### 5.2. @Payload and targetClass

A handler:

```java
public void handle(@Payload OrderCreated order)
```

needs an `OrderCreated` object at method invocation. If the JMS layer returns a `String`, the Spring Messaging argument resolver may try its converter with **targetClass = OrderCreated.class**. Without a String JSON → DTO converter, conversion fails.

If the JMS layer already returns `OrderCreated`, the argument resolver can normally pass it straight through without parsing JSON twice. Choose one clear strategy:

1. **JMS converter decodes JSON → DTO**, then `@Valid`.
2. **JMS converter decodes TextMessage → String**, then Spring Messaging JSON converter decodes String → DTO, then `@Valid`.

Do not mix both into redundant double-decoding; what matters is that producer and consumer follow the same wire/schema contract.

## 6. Bean Validation Layer: Object Built Yet Invalid

Bean Validation is a **separate** step after obtaining a correctly typed object, if configured and triggered via `@Valid` or `@Validated`.

### 6.1. Java 17 DTO with Constraints

**File `OrderCreated.java`:**

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

public record OrderCreated(
        @NotBlank String orderId,
        @Positive int quantity) {
}
```

`@NotBlank` rejects null, empty strings, and whitespace-only strings. `@Positive` requires a number **greater than 0**. With `quantity=0`, JSON deserialization can still succeed; validation then rejects it.

**Do not confuse three layers of "valid":**

- Valid JSON syntax.
- Valid types/schema to construct the Java object.
- Object satisfies business-facing Bean Validation constraints.

An object can pass layers 1–2 yet fail layer 3.

### 6.2. @Valid on @JmsListener

**File `ValidatedOrderListener.java`:**

```java
import jakarta.validation.Valid;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@Component
public class ValidatedOrderListener {

    private final OrderApplicationService applicationService;

    public ValidatedOrderListener(
            OrderApplicationService applicationService) {
        this.applicationService = applicationService;
    }

    @JmsListener(
            id = "orders.created.validated.v1",
            destination = "orders.created",
            containerFactory = "validatedOrderListenerFactory")
    public void receive(@Payload @Valid OrderCreated order) {
        // This line ONLY runs if conversion + validation succeeded.
        applicationService.process(order);
    }
}
```

`OrderApplicationService` is an application-provided business service that must have a real bean/implementation. The example is a class integrated **within a Spring project**, not standalone runnable under the JDK alone.

When constraints fail before invocation, `applicationService.process` **is not called** for that delivery. This is the benefit of method-boundary validation: avoiding side effects for invalid messages, **when the Validator is configured properly**.

### 6.3. @Valid Alone Is Not Enough Without a Provider and Validator

`@NotBlank`/`@Positive` annotations are provided by the **Jakarta Bean Validation API**; executing them also requires a **provider** (e.g., Hibernate Validator) and a `Validator` used by Spring's handler method infrastructure.

In Spring Boot, the validation starter can supply appropriate configuration. In plain Spring Framework, configure `LocalValidatorFactoryBean` and pass the validator to `DefaultMessageHandlerMethodFactory`. Never assume merely adding the `jakarta.validation-api` dependency enables runtime validation.

### 6.4. What Does MethodArgumentNotValidException Mean?

`PayloadMethodArgumentResolver` checks `@Valid`/`@Validated`; on binding/constraint errors, it can throw:

```text
org.springframework.messaging.handler.annotation.support
    .MethodArgumentNotValidException
```

This is **not** Spring MVC's `org.springframework.web.bind.MethodArgumentNotValidException`; same simple name, different package. The annotated JMS path may wrap the exception in `org.springframework.jms.listener.adapter.ListenerExecutionFailedException` or another wrapper. Always inspect the cause chain when logging.

Never write an exception handler catching only the **MVC exception class** expecting it to always work for JMS.

### 6.5. @Valid Does Not Check All Business Logic

`@Valid` fits input-boundary invariants:

- Non-empty `orderId`.
- Positive `quantity`.
- Basic email/identifier format.
- Nested beans if cascaded properly with `@Valid`.
- Field length bounds and payload structure.

Business rules requiring external data (whether the order was already paid, inventory levels, pricing policies, etc.) are normally checked **inside the service**, after the method runs. Do not stuff nondeterministic database/network calls into synchronous validators where they can make the conversion boundary hard to observe and misclassify retries.

## 7. Complete Spring JMS Configuration: Converter and Validator in the Right Places

Examples use **Spring Framework 6.2.x, Java 17+, Jakarta Messaging 3.x, Jackson 2, and a Jakarta Bean Validation implementation**. A real broker/`ConnectionFactory` is assumed, with queue `orders.created` provisioned or auto-created per provider policy. If using Spring 7/Jackson 3, verify the corresponding classes/converters in your actual version rather than copying packages and constructors blindly.

### 7.1. Validator Bean

**File `OrderValidationConfig.java`:**

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class OrderValidationConfig {

    @Bean("orderBeanValidator")
    public LocalValidatorFactoryBean orderBeanValidator() {
        return new LocalValidatorFactoryBean();
    }
}
```

`LocalValidatorFactoryBean` bridges the Bean Validation provider with Spring's `Validator`. A runtime provider (such as Hibernate Validator) is required. With Spring Boot auto-configuration, avoid creating two competing validator beans if the application already has a default validator; choose one consistent setup.

### 7.2. JMS Converter, Listener Factory, Handler Factory

**File `OrderJmsConfig.java`:**

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListenerConfigurer;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageType;
import org.springframework.messaging.handler.annotation.support
        .DefaultMessageHandlerMethodFactory;
import org.springframework.validation.Validator;

import java.util.Map;

@Configuration
@EnableJms
public class OrderJmsConfig implements JmsListenerConfigurer {

    private final Validator validator;

    public OrderJmsConfig(
            @Qualifier("orderBeanValidator") Validator validator) {
        this.validator = validator;
    }

    @Bean("orderJmsJsonConverter")
    public MappingJackson2MessageConverter orderJmsJsonConverter() {
        var converter = new MappingJackson2MessageConverter();
        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("_type");
        converter.setTypeIdMappings(
                Map.of("order-created-v1", OrderCreated.class));
        return converter;
    }

    @Bean("validatedOrderListenerFactory")
    public DefaultJmsListenerContainerFactory listenerFactory(
            ConnectionFactory connectionFactory,
            @Qualifier("orderJmsJsonConverter")
            MappingJackson2MessageConverter converter) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(converter);
        factory.setSessionTransacted(true);
        factory.setPubSubDomain(false);
        factory.setConcurrency("1-3");

        // Observe errors outside the handler; does not automatically alter broker DLQ.
        factory.setErrorHandler(error -> {
            System.err.println(
                    "JMS listener pipeline failed: "
                    + error.getClass().getName());
        });
        return factory;
    }

    @Bean("orderJmsTemplate")
    public JmsTemplate orderJmsTemplate(
            ConnectionFactory connectionFactory,
            @Qualifier("orderJmsJsonConverter")
            MappingJackson2MessageConverter converter) {

        var template = new JmsTemplate(connectionFactory);
        template.setMessageConverter(converter);
        template.setPubSubDomain(false);
        return template;
    }

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {

        var methodFactory = new DefaultMessageHandlerMethodFactory();
        methodFactory.setValidator(validator);
        registrar.setMessageHandlerMethodFactory(methodFactory);
    }
}
```

**Two intentionally separate configuration points:**

1. `factory.setMessageConverter(converter)` uses the **JMS-specific converter** to read JSON TextMessages and resolve `OrderCreated` from the `_type` property.
2. `methodFactory.setValidator(validator)` uses Spring Messaging method-argument validation **after** the DTO exists to enforce `@Valid`.

`setErrorHandler` registers a container-level callback that can record errors even when the method never ran. The callback here only prints the top-level exception class; production requires the cause chain, tracking IDs, and metrics, with sensitive-data masking policies. This callback **does not automatically fix poison messages, does not automatically republish to DLQ, and is not a place to arbitrarily override transaction commits**.

**Why `setSessionTransacted(true)`?** So that pre-invocation failures (as well as in-method errors) can trigger rollback/redelivery under JMS transaction semantics, instead of risking unreliable ACKs under `AUTO_ACKNOWLEDGE`. However, exact retry/DLQ behavior is determined by the container, broker, and policy configuration; you cannot guarantee exact retry counts via this annotation alone.

### 7.3. Business Service and Handler

**File `OrderApplicationService.java`:**

```java
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {

    public void process(OrderCreated event) {
        // Minimal example: in a real system, this would be DB/outbox/idempotency.
        System.out.println("BUSINESS INVOKED: " + event.orderId());
    }
}
```

Use `ValidatedOrderListener` from section 6.2 with the configurations above. Only when the input is converted and validated is the service invoked. With malformed/invalid input, `"BUSINESS INVOKED"` must never appear for that message.

The Spring code above only makes sense when placed in **the same application** with component scanning, Spring container, JMS provider, broker queue, Jackson, Bean Validation provider, and matching dependencies. You cannot simply drop these files into a folder and run `javac *.java` with just the JDK.

### 7.4. Required Dependencies

In a Maven/Gradle project, you need equivalents of:

- `org.springframework:spring-jms`.
- `org.springframework:spring-messaging` per Spring dependency management.
- Jakarta JMS API and JMS provider/broker implementation.
- Jackson matching the Spring version (Spring 6.x examples use Jackson 2).
- `jakarta.validation:jakarta.validation-api`.
- Runtime Bean Validation provider (e.g., Hibernate Validator).
- Spring Context and transaction infrastructure if needed by the application.
- Test stack with JUnit 5 and an appropriate test broker/provider.

If using Spring Boot, starters/versions manage dependencies via the BOM; never mix Spring 6 classes arbitrarily with Spring 7/Jackson 3 assuming identical APIs.

## 8. Creating Three Test Messages: Valid, Invalid JSON, Invalid Constraints

Suppose the `orderJmsTemplate` bean using the JSON converter above is available. The producer sends one **valid** DTO, one **malformed** TextMessage, and one DTO **violating constraints**.

**File `OrderTestPublisher.java`:**

```java
import jakarta.jms.TextMessage;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderTestPublisher {

    private final JmsTemplate template;

    public OrderTestPublisher(
            @Qualifier("orderJmsTemplate") JmsTemplate template) {
        this.template = template;
    }

    public void sendValid() {
        template.convertAndSend(
                "orders.created",
                new OrderCreated("ORD-42", 2));
    }

    public void sendMalformedJson() {
        template.send("orders.created", session -> {
            TextMessage message = session.createTextMessage(
                    "{\"orderId\":\"ORD-43\",\"quantity\":");
            message.setStringProperty("_type", "order-created-v1");
            message.setStringProperty("testCase", "malformed");
            return message;
        });
    }

    public void sendInvalidConstraint() {
        template.convertAndSend(
                "orders.created",
                new OrderCreated("", 0));
    }
}
```

Here:

- `sendValid()`: Jackson serialization → `TextMessage`; `_type` property is set by converter per mapping → valid inbound DTO → validation passes → method is called.
- `sendMalformedJson()`: uses `send(..., MessageCreator)` to **bypass the sender's converter**, crafting broken JSON while keeping `_type`, forcing the receiver to try parsing and fail.
- `sendInvalidConstraint()`: JSON can be produced/parsed normally into `OrderCreated("",0)`; the failure occurs only at **method argument validation**.

**Never invoke these three test methods against production.** With `sessionTransacted=true`, the two invalid messages may trigger repeated redeliveries and increase retry/DLQ counts per broker config. Tests must isolate queues, bound retries, and verify cleanup.

### 8.1. Expected Outcomes Without Fabricating Runtime Stdout

If the queue, converter, and validator are all configured accurately:

| Send call | JMS conversion | Bean Validation | Business body |
| --- | --- | --- | --- |
| `sendValid` | PASS | PASS | **Invoked** |
| `sendMalformedJson` | FAIL | No DTO to validate | **Not invoked** |
| `sendInvalidConstraint` | PASS | FAIL | **Not invoked** |

Exact logs, redelivery counts, and ordering cannot be asserted from code alone. Provider, concurrency, transactions, listener timing, and broker retry/DLQ policies govern runtime behavior.

### 8.2. What If Business Logic Is Still Called with quantity=0?

Check these possibilities:

1. Wrong `@Valid` import (e.g., Jakarta 3 mixed with legacy `javax.validation`).
2. Missing runtime Bean Validation provider.
3. `DefaultMessageHandlerMethodFactory` lacks a validator or the factory bean is not used by the registrar.
4. Listener annotation does not point to `validatedOrderListenerFactory` as assumed.
5. The handler is actually receiving from another route/binding, or an extra unvalidated listener exists.
6. Constraints were placed on a different object than the one actually deserialized.
7. The test is measuring output from a different message or another consumer on the same queue.

Never conclude `@Valid` is unsupported in JMS just because of a misconfiguration.

## 9. Pre-Method Errors: Cannot Be Caught by try/catch Inside the Method

Anti-pattern:

```java
@JmsListener(
        destination = "orders.created",
        containerFactory = "validatedOrderListenerFactory")
public void receive(@Payload @Valid OrderCreated event) {
    try {
        applicationService.process(event);
    } catch (Exception ex) {
        // Cannot catch pre-invocation deserialize/validate errors!
    }
}
```

If `@Valid` fails, Java execution **has not even entered the `{` brace of the method**, so `catch` never runs. Likewise, required `@Header` errors or argument conversion failures before invocation cannot be caught by this method.

**The right observation path** is container/adapter error-handling, converter logging/observability, listener container metrics, and broker redelivery metrics. When you need to classify and quarantine poison messages, rely on system/broker policies and code at a layer that can access the **raw JMS message** prior to conversion.

### 9.1. Errors Are Often Wrapped: Find the Root Cause

A log might have the conceptual structure:

```text
ListenerExecutionFailedException
  caused by MethodArgumentNotValidException
    field error: quantity must be greater than 0
```

Or:

```text
MessageConversionException
  caused by JsonProcessingException
    malformed JSON at ...
```

These are **illustrative log patterns**, not fixed stack traces across all Spring versions. Wrappers vary by adapter, converter, provider, and underlying error. Never write alerts matching only an uncontracted message string.

### 9.2. Do Not Catch and Treat Unprocessed Messages as Successful

If a raw listener catches every exception and returns normally:

```java
try {
    decodeAndProcess(raw);
} catch (Exception ex) {
    logError(ex);
    // If returning normally: the container may commit/ACK.
}
```

With a transacted session, if the exception is **swallowed** and the method returns normally, the container may **commit** that delivery. The faulty message can vanish from the queue without ever being saved to quarantine.

Only confirm success upon reaching a defined **terminal outcome** (business commit or durable, managed quarantine). Otherwise, let errors propagate so retry/rollback policies work, or route into transactional/recoverable error handling.

## 10. Ack, Transactions, Retries, and DLQ: Consequences of Pre-Handler Failures

Conversion/validation can fail **before the business method**, yet the JMS reaction still depends on the listener container and acknowledgment/transaction mode.

### 10.1. With DefaultMessageListenerContainer and sessionTransacted=true

Typically:

```text
Broker delivers M
   |
   v
Spring container receives M inside JMS transaction
   |
   v
conversion or @Valid fails
   |
   v
Exception propagates out of listener adapter
   |
   v
JMS transaction rolls back
   |
   v
Broker may redeliver M according to redelivery policy
   |
   +-- after retry limit, possibly DLQ/quarantine (provider-specific)
```

Rollback **does not fix broken JSON or constraints**. If the input is immutable and the failure is deterministic, each retry fails at the exact same spot. A corrupt message can become a **poison message** wasting time, polluting metrics, and blocking the backlog.

Some brokers support retry delays, max delivery attempts, and dead-letter addresses; **the JMS API does not standardize a DLQ name or default retry count across all providers**. Configure directly per target broker.

### 10.2. With AUTO_ACKNOWLEDGE

Per Spring JMS documentation for `DefaultMessageListenerContainer`, `AUTO_ACKNOWLEDGE` **does not provide reliability guarantees equivalent to transacted receives**; the container may acknowledge before listener execution and exceptions do not lead to redelivery as hoped.

Therefore, do not write:

> "Any conversion error in @JmsListener will be retried by the broker and automatically moved to DLQ."

That is false without checking the configuration. A pre-method failure can still result in **the message being considered handled** depending on ack mode and container semantics.

### 10.3. CLIENT_ACKNOWLEDGE and Other Session Modes

`CLIENT_ACKNOWLEDGE` has its own semantics; the Spring container may acknowledge on success and recover on failure, depending on container/provider and configuration. It does not solve DB transactions automatically, and acknowledgment timing differs.

For workloads requiring reliability, the Spring reference recommends considering **local JMS transacted sessions** instead of default auto-ack. When DB writes accompany JMS, design idempotency/outbox/transaction isolation; a local JMS transaction does not make the DB part of the same atomic commit.

### 10.4. ErrorHandler Is Not a Broker Retry Controller

`DefaultJmsListenerContainerFactory.setErrorHandler(...)` (via the listener container) can receive uncaught processing exceptions for logging/metrics, even when the method body never started. However:

- Do not treat returning normally from `ErrorHandler` as equivalent to ACK/commit.
- Do not assume the callback can alter broker redelivery policies.
- Do not arbitrarily throw errors from the error handler that blind container observability.
- Do not use it to execute non-idempotent DB side effects on every retry.
- Change ack behavior via **real transaction/ack configuration** and test against the provider.

Error-handling callbacks should observe and classify, whereas **quarantine/ack** needs an explicit bounded strategy (broker DLQ policy, raw listener gateway, or a consumer adapter designed to handle terminal outcomes).

### 10.5. Distinguishing Permanent vs. Transient Errors

| Error type | Does retrying help? | Handling approach |
| --- | --- | --- |
| Malformed JSON | Almost never fixes the old message | Quarantine/DLQ, fix producer/schema |
| Missing required type-id | Will not magically appear on retry | Fix producer/mapping; controlled replay |
| Unknown schema version | Might work after deploying newer consumer, though uncertain | Route to compatible consumer/quarantine, versioning |
| DTO violates `@NotBlank` | Unchanged on retry | Terminal invalid, reject/quarantine per policy |
| Missing required header | Will not appear on its own | Fix contract, quarantine |
| JSON converter bug | May need a deployed fix; infinite retries remain risky | Fix/rollout, planned pause/redrive |
| Transient broker disconnect | Retry/reconnect usually helps | Bounded retries, backoff, metrics |
| DB timeout after method starts | Retries may help, though side effects might already exist | Idempotency, transactions, controlled retries |
| Bean Validation depending on flaky remote service | Should not live inside validator by default | Move remote checks into business flow |

**Principle:** deterministic format/schema errors are generally unsuited for infinite retries. Yet **never silently ACK and drop a message** just because you spotted an error; use intentional quarantine, auditing, or business rejection paths.

## 11. DLQ Limitations and Quarantine Strategies

### 11.1. DLQ Is Not a Default Feature of @Valid

Spring does not create a Queue named `orders.created.DLQ` simply because a method has `@Valid`. Nor does the JMS specification standardize `DLQ`/`ActiveMQ.DLQ` names across every broker. One broker may support dead-letter addresses/queues after a redelivery limit, while another follows a different policy.

If the requirement is "never lose invalid messages":

1. Configure destinations with clear retention and redelivery policies.
2. Set suitable max attempts and backoff.
3. Define dead-letter/quarantine destinations per provider.
4. When a message enters quarantine, store metadata: original destination, message ID, correlation ID, type/schema version, rejection stage, timestamp, and reason code.
5. Retain the raw payload if needed for investigation, **encrypting/restricting access and TTL** for sensitive data.
6. Establish a workflow for triage, fixing producer/schema, compatibility checks, and **idempotent manual redrive**.
7. Test that a malformed message actually lands in the expected destination after configured retries.

### 11.2. If Broker DLQ Is Not Permitted

An application can build an **ingress validation gateway** using a raw JMS listener to decode and validate:

```text
incoming queue
   |
   v
Raw listener / validation gateway
   |
   +-- valid -> business queue/event flow
   |
   +-- invalid -> quarantine queue + reason
```

However, you must solve **atomicity** between receiving the original and publishing the quarantine/valid message. Within the same JMS provider/session, a local JMS transaction can work where appropriate; if pushing results to a database or another broker, outbox/XA or compensating design is needed. Never return normally and lose the message if writing to quarantine fails.

In this gateway style, conversion happens **inside code designed to inspect raw messages**, rather than `@Payload @Valid` on the same method where failures are uncatchable. Changing architecture carries tradeoffs: boilerplate, duplicate handling, throughput, and security.

### 11.3. Idempotency During Redrive

Never use `JMSMessageID` as the sole business idempotency key in all situations: when republishing/redriving, the provider may assign a new message ID. Keep an independent `eventId`/`orderId` in the body/JMS property to guard side effects. Redrives must record why they were triggered, how many times, and the outcome.

## 12. Observing the Right Places When the Handler Is Not Called

### 12.1. Metrics to Separate

| Metric | Meaning | Pitfall to avoid |
| --- | --- | --- |
| `jms_receive_attempts` | Broker delivered or container attempted receive | Does not mean the method was invoked |
| `jms_conversion_failures` | Body/serialization/type-id errors | Not a business DB error |
| `jms_argument_failures` | `@Payload`/`@Header` binding errors | Not always JSON syntax |
| `jms_validation_failures` | DTO violated constraints before invocation | Not equivalent to database validation |
| `jms_handler_invocations` | Number of times method body was entered | May exceed unique business IDs on redelivery |
| `jms_handler_success` | Business method completed | Does not guarantee DB/JMS committed together |
| `jms_redeliveries` | Retries from broker/session | Does not distinguish permanent vs. transient |
| `jms_dlq_messages` | Messages moved to dead-letter destination | Broker-specific policy |
| `queue_oldest_age` | Age of oldest unprocessed message | Can rise from poison/retries or lack of capacity |

The metric names in this table are **design suggestions**, not a promise that Spring/JMS emits all of them out of the box. Spring 6.1+ provides observation support depending on configuration, so inspect your actual version and observation registry.

### 12.2. Log the Root Cause, Not the Full Body

A useful diagnostic record:

```text
endpointId=orders.created.validated.v1
destination=orders.created
messageId=ID:...                 (provider value)
correlationId=req-42
eventId=evt-42
typeId=order-created-v1
schemaVersion=1
stage=VALIDATION
cause=MethodArgumentNotValidException
fields=[quantity]
attempt=3
outcome=ROLLED_BACK
```

This is an **illustrative structure**, not a fixed auto-generated log. When the business ID field cannot be decoded from malformed JSON, use headers/JMS properties readable by the broker rather than guessing `eventId`.

Avoid logging raw tokens, PII, or payment/card data. If extracting payloads is necessary for debugging, use a secured quarantine channel with retention/auditing.

### 12.3. Locating the Exact Error Stack

Checklist when seeing `ListenerExecutionFailedException`:

1. Check the **root cause**: JMS `MessageConversionException`, JSON parse error, `MethodArgumentNotValidException`, header binding, or application error?
2. Check whether the stack is in `MessagingMessageListenerAdapter.toMessagingMessage`, `PayloadMethodArgumentResolver`, or the service method.
3. Identify the sent message type and `_type` property.
4. Check whether the `DefaultJmsListenerContainerFactory` bean referenced by `containerFactory` has the right converter.
5. Check whether `JmsListenerConfigurer` registered a method factory with a `Validator`.
6. Check transaction/ack mode and broker retry/DLQ policies.
7. Check broker redelivery count and message age before deciding to replay.
8. Distinguish **repeated errors on the same raw message** from many different messages sharing a schema bug.

### 12.4. Why a Body Log in @JmsListener Is an Insufficient Signal

`System.out.println("start")` inside the body will not run on pre-invocation failures. Analyzing those failures requires **pre-body observation points**, such as container `ErrorHandler`, adapter instrumentation, broker metrics, and tracing. Logs inside the method only confirm all earlier stages passed.

## 13. Standalone Java 17 Demo: Proving Failures at Two Gates Before Business Logic

The following is a pure-JDK Java 17 program. It **simulates** the three steps decode → validate → business method and separates the two failure types. No Spring/JMS libraries or broker are needed. Use it to observe why errors cannot be caught inside a method that has not been invoked.

Create file **`PreHandlerFailureDemo.java`**:

```java
import java.util.List;

public final class PreHandlerFailureDemo {

    record Order(String id, int quantity) {}

    static final class DecodeFailure extends RuntimeException {
        DecodeFailure(String message) {
            super(message);
        }
    }

    private static int businessCalls = 0;

    static Order decode(String raw) {
        String[] fields = raw.split(",", -1);

        if (fields.length != 2) {
            throw new DecodeFailure("expected two fields");
        }

        try {
            return new Order(fields[0], Integer.parseInt(fields[1]));
        } catch (NumberFormatException ex) {
            throw new DecodeFailure("quantity is not an integer");
        }
    }

    static void validate(Order order) {
        if (order.id().isBlank() || order.quantity() <= 0) {
            throw new IllegalArgumentException("invalid order fields");
        }
    }

    static void business(Order order) {
        businessCalls++;
        System.out.println("BUSINESS: " + order.id());
    }

    static void deliver(String raw) {
        try {
            Order order = decode(raw);
            validate(order);
            business(order);
        } catch (DecodeFailure ex) {
            System.out.println("CONVERSION: " + ex.getMessage());
        } catch (IllegalArgumentException ex) {
            System.out.println("VALIDATION: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        for (String wire : List.of(
                "ORD-1,2",
                "not-a-record",
                "ORD-2,0",
                "ORD-3,1")) {
            deliver(wire);
        }

        System.out.println("Business calls: " + businessCalls);
    }
}
```

Compile and run:

```bash
javac PreHandlerFailureDemo.java
java PreHandlerFailureDemo
```

**Exact stdout:**

```text
BUSINESS: ORD-1
CONVERSION: expected two fields
VALIDATION: invalid order fields
BUSINESS: ORD-3
Business calls: 2
```

Explanation:

- `ORD-1,2` has two fields and a valid quantity → decode/validate pass → business runs.
- `not-a-record` lacks a comma → `DecodeFailure` before an `Order` exists.
- `ORD-2,0` decodes into `Order` yet quantity is non-positive → validation fails, business does not run.
- `ORD-3,1` is valid → business runs.
- Four simulated "deliveries" occurred, yet only **two** business invocations.

**Limitations:** The demo does not implement `@JmsListener`, use Jackson/Jakarta Validation, or involve JMS sessions, transactions, redelivery, DLQs, or Spring exception wrappers. It illustrates the order of the **logical pipeline**; real runtime behavior must be tested on a JMS provider.

## 14. Real Broker Testing: Verifying "Method Never Ran"

### 14.1. Testing Conversion Failure

1. Provision test queue `orders.created` and configure the consumer's JMS Jackson converter with `_type` mapping.
2. Send a raw `TextMessage` containing malformed JSON while still setting `_type=order-created-v1`.
3. Wait for the delivery attempt to be recorded by the broker.
4. Assert the business service mock had zero calls for that event.
5. Verify the log/root cause belongs to conversion/JSON, not Bean Validation.
6. Observe rollback and redelivery if the listener session is transacted.
7. Cap attempts and verify the message moves to quarantine/DLQ when configured on the broker.

**Never share a single FIFO queue unisolated across test suites**, because one poison message can hang integration tests or cause tests to steal messages from each other.

### 14.2. Testing Bean Validation Failure

1. Send DTO `new OrderCreated("",0)` via the Spring JSON converter.
2. Ensure the message serializes into a valid JSON TextMessage with `_type`.
3. Consumer parses it into the DTO successfully.
4. Argument resolver invokes Validator and catches `@NotBlank`/`@Positive`.
5. Assert the service method had zero calls.
6. Verify root cause `MethodArgumentNotValidException` or its appropriate wrapper.
7. Verify rollback/retry/DLQ per policy.

If the test fails to reject and invokes the service instead, check the validation provider and `JmsListenerConfigurer` setup before touching business code.

### 14.3. Testing Missing Header vs. Wrong Header Type

Use a test listener:

```java
@JmsListener(destination = "header.test")
public void handle(
        @Payload String body,
        @Header("tenantId") String tenantId,
        @Header("attempt") int attempt) {
    // Code runs after both headers are bound.
}
```

Send a message missing `tenantId` and a message with `attempt="n/a"`; verify the exceptions belong to **argument resolution** rather than the JSON converter. Separate messages and destinations so test results do not bleed together.

### 14.4. Testing with sessionTransacted=false

In an isolated test environment:

1. Send a malformed message to the queue.
2. Use `DefaultMessageListenerContainer` with `AUTO_ACKNOWLEDGE`.
3. Verify redelivery may not occur as expected per Spring semantics.
4. Compare against a `sessionTransacted=true` listener.
5. Record actual behavior on your active provider version instead of generalizing from a single broker.

**Never run this test against real business data**, because the wrong ack mode can lose messages.

### 14.5. Testing Bounded Poison-Message Policy

1. Configure test broker max delivery attempts and dead-letter target.
2. Send a permanently invalid message.
3. Verify the same event ID is attempted up to the configured limit.
4. Verify the message eventually lands in the DLQ and the main queue does not loop forever.
5. Verify conversion/validation failure metrics classify accurately instead of counting as business exceptions.
6. When redriving after fixing producer/schema, ensure idempotency.

### 14.6. Testing Compatibility When Deploying Two Versions

1. Producer V1 emits schema version 1.
2. Consumer V2 runs a converter with version-1 type-id mapping.
3. Prove V2 still parses/validates old data properly.
4. Send a V2 payload containing a new field; verify consumer V1 intentionally rejects/quarantines or handles it backward-compatibly.
5. Test missing/unknown type-ids without permitting arbitrary Java class loading.
6. Never substitute "worked locally" for integration tests with identical provider settings.

## 15. Production Runbook: Missing First Log of @JmsListener

When alerted "queue backlog or DLQ growing, yet handler method shows no logs":

### Step 1 — Pinpoint the Exact Endpoint

- `@JmsListener.id`, `destination`, `containerFactory`, and selector.
- Queue vs. Topic; subscription identity if durable.
- Broker namespace/vhost, ACLs, consumer count, and connection status.
- Are other listener containers competing on the same queue?

If the selector does not match, the message may **never have reached the adapter**. That is a **pre-receive** cause, distinct from conversion errors. Do not confuse it with the scope of this lesson.

### Step 2 — Verify Delivery Attempts

- JMS provider metrics: delivered/in-flight/redelivered counts.
- Spring container adapter errors.
- Where possible, trace message ID/correlation ID.
- Check `JMSRedelivered`/`JMSXDeliveryCount` per provider support.

If the broker has no matching consumer, you cannot conclude conversion failed merely from missing business logs.

### Step 3 — Extract the Root Cause, Not Just the Exception Wrapper

Group into:

- Transport/connection `JMSException`.
- `org.springframework.jms.support.converter.MessageConversionException` or JSON cause: wire conversion.
- `org.springframework.messaging.converter.MessageConversionException`: Spring Messaging conversion.
- `MethodArgumentNotValidException`: Bean Validation/method arguments.
- Missing `@Header`/wrong type: argument resolution.
- Stack trace inside `OrderApplicationService.process`: business method already started.

### Step 4 — Inspect a Sample Message Contract

Using non-destructive broker management/browsing when possible, gather:

- JMS Message subclass and body format.
- `_type`/`schemaVersion`/`contentType`.
- Header/property names and types.
- Violating values (if authorized and sensitive fields masked).
- Event ID and validity of the business key.

Avoid attaching an un-selected consumer to a production queue just to "peek," as it may ACK another worker's messages.

### Step 5 — Inspect Transactions/Retries/DLQ

- Is the container running `sessionTransacted=true` or auto-ack?
- Does the broker have bounded retries or redelivery delays?
- Are messages looping endlessly without any body-level fix possible?
- Is the DLQ actually provisioned with proper permissions?
- Is a converter failing on older messages during a rolling deploy?

### Step 6 — Fix at the Right Layer

- Malformed JSON: fix producer/serialization, quarantine/replay by version.
- Wrong type-id: fix mappings/metadata and compatibility.
- Method-arg type mismatch: configure Spring Messaging converter or update method contract.
- Missing header: clarify required/optional rules and align producers.
- Validation failure: fix data/constraints if valid per business rules; never disable `@Valid` just to silence logs.
- Transient broker error: backoff/recovery and re-observe.
- Non-working DLQ: configure the provider; do not wait for Spring to create a DLQ on its own.
- Poisons clogging queue: pause/move messages carefully with auditing; never purge blindly.

### Step 7 — Verify After Fixing

- Converter/validator errors drop.
- Business invocations rise for valid messages.
- Main queue backlog shrinks and DLQ stops surging.
- Unique business IDs are not processed twice.
- Replayed events are tagged with source version/reason.
- No PII leaks in error logs/quarantine.

## 16. Common Misconceptions

**Misconception 1 — "Broker delivered logs mean the handler method ran."**  
False. Delivery reaches the container before conversion/validation; the body may never have been invoked.

**Misconception 2 — "Adding try/catch inside @JmsListener catches all deserialization errors."**  
False. Errors can occur before invocation, so the catch block inside the body never runs.

**Misconception 3 — "A Java DTO with @NotBlank is automatically validated."**  
False. You need `@Valid`/`@Validated` on the argument, a validator/runtime provider, and properly configured method infrastructure.

**Misconception 4 — "Syntactically broken JSON is a Bean Validation error."**  
False. Parsing/deserialization fails before Bean Validation has a DTO to inspect.

**Misconception 5 — "Once the DTO is created, the handler is guaranteed to run."**  
False. Method-argument validation can block it, or a required header may be missing.

**Misconception 6 — "Spring JMS and Spring Messaging MessageConverter are the same interface."**  
False. They differ in package, signatures, and purpose. Place converters at the right layer.

**Misconception 7 — "Setting a JSON converter on the sender is enough for the listener to receive DTOs."**  
False. The consumer listener factory must also have a compatible converter/argument conversion setup.

**Misconception 8 — "@Valid with old javax.validation.Valid imports is always compatible."**  
False. Spring Framework 6+/Jakarta uses `jakarta.validation`; avoid mixing incompatible versions.

**Misconception 9 — "A missing @Header is always passed as null."**  
False. `@Header` has required semantics by default; the argument resolver can fail before the method.

**Misconception 10 — "Converter errors automatically go to DLQ."**  
False. DLQ is a broker/consumer retry policy; Spring `@Valid` does not create it.

**Misconception 11 — "AUTO_ACKNOWLEDGE guarantees redelivery when a handler fails."**  
False per Spring `DefaultMessageListenerContainer`; configure transacted/reliable modes and test.

**Misconception 12 — "Just keep retrying malformed JSON until it stops failing."**  
False. Immutable data fails deterministically; apply bounded retries/quarantine instead of a poison loop.

**Misconception 13 — "Just logging in ErrorHandler quarantines the message."**  
False. ErrorHandler logging does not publish to a DLQ or guarantee a terminal outcome.

**Misconception 14 — "Catching exceptions and returning normally is always safe."**  
False. The container may commit/ACK a message that was never processed or safely quarantined.

**Misconception 15 — "Exceptions from the receiver method are always business errors."**  
False. Wrappers can come from pre-invocation argument binding/validation; check the root cause and stack.

**Misconception 16 — "Changing JMSMessageID deduplicates redrives."**  
False. Redrives often assign new message IDs; use stable business/event IDs.

**Misconception 17 — "Validation errors only happen in HTTP controllers."**  
False. Spring Messaging's `PayloadMethodArgumentResolver` supports `@Valid` on annotated message listeners, including JMS.

**Misconception 18 — "Valid JSON body alone makes messaging secure."**  
False. Enforce type-id allowlists, schema constraints, ACLs, and size limits; avoid untrusted Java deserialization.

## 17. Code Review and Operations Checklist

- [ ] Is the handler receiving raw `jakarta.jms.Message`, `String`, Spring `Message<?>`, or a typed DTO?
- [ ] Are all **pre-method-invocation** steps identified?
- [ ] Does the JMS wire converter use the right package and is it wired to the **listener factory**, not only the producer?
- [ ] Are JMS TextMessage/BytesMessage subtypes, encoding, schema, and content types aligned?
- [ ] If the JSON converter needs a type-id, does the producer set the property and does the receiver enforce allowlisted mappings?
- [ ] If using `@Payload OrderCreated`, does the handler have a converter for that target type?
- [ ] If using `@Valid`, are a Jakarta Bean Validation implementation and Spring `Validator` genuinely active?
- [ ] Is Spring Messaging `MethodArgumentNotValidException` distinguished from MVC's?
- [ ] Are required `@Header` fields actually sent/mapped with the right types by producers?
- [ ] Are there logs/counters at the container boundary for pre-handler failures?
- [ ] Does `ErrorHandler` log the cause chain without losing message ID/type/schema details?
- [ ] Is there a policy preventing raw sensitive payloads from entering logs/quarantine?
- [ ] Does the listener container use an acknowledgment/transaction mode matching reliability needs?
- [ ] On rollback, does the broker enforce redelivery limits and a real DLQ/quarantine?
- [ ] Are permanent errors routed to audited terminal handling instead of infinite retries?
- [ ] Does catch/return avoid accidentally ACKing unprocessed messages?
- [ ] Is idempotency keyed by business ID for retries/redrives?
- [ ] Are there tests proving malformed JSON **does not invoke the business service**?
- [ ] Are there tests proving DTOs violating `@Positive`/`@NotBlank` **do not invoke the business service**?
- [ ] Are missing/invalid `@Header` tests verifying the exact failure stage?
- [ ] Has real broker/container behavior been tested for ack, redelivery, DLQ, and graceful shutdown?
- [ ] Was producer/consumer compatibility tested for rolling deployments?
- [ ] Are backlog, oldest age, redelivery rate, validation failures, and DLQ monitored?
- [ ] Are Spring/Jackson/Validation versions compatible with the example code?

## 18. Self-Check Knowledge Quiz

**Question 1.** The broker delivered a message, yet `@JmsListener` does not print its first log line. Why might that happen?

**Answer:** Conversion/argument resolution/Bean Validation may have failed **before invocation**. Also check selector/consumer metrics to confirm the message actually reached the container.

**Question 2.** A JMS TextMessage contains malformed JSON. Will `@Valid` catch it first or the Jackson converter?

**Answer:** Jackson/JMS wire conversion fails first; there is no DTO yet for `@Valid` to check.

**Question 3.** DTO `OrderCreated("",0)` deserialized successfully. Why didn't the method run?

**Answer:** `@Payload @Valid` detected `@NotBlank`/`@Positive` violations and threw a validation exception in the argument resolver before invocation.

**Question 4.** Can a `try/catch` inside the `@JmsListener` body catch `MethodArgumentNotValidException` for its own argument?

**Answer:** No. The exception occurs while preparing arguments, before entering the Java method body.

**Question 5.** Setting `MappingJackson2MessageConverter` on the sender `JmsTemplate` without configuring the listener: is the receiver guaranteed to get a DTO?

**Answer:** No. A compatible listener converter/argument conversion is also required, depending on the container factory actually used.

**Question 6.** How does `spring-jms MessageConverter` differ from `spring-messaging MessageConverter`?

**Answer:** The JMS converter works with `jakarta.jms.Message` and `Session`; the Messaging converter works with Spring `Message<?>` and target types. The two interfaces are not directly interchangeable.

**Question 7.** Which exception do `@Valid` violations typically raise in Spring Messaging's argument resolver?

**Answer:** `org.springframework.messaging.handler.annotation.support.MethodArgumentNotValidException`; at the adapter level you may see a wrapper like `ListenerExecutionFailedException`.

**Question 8.** When can `@Header("tenantId") String tenantId` prevent the method from being called?

**Answer:** When the required header is missing or cannot be resolved/converted; argument binding fails before invocation.

**Question 9.** Why doesn't "method never ran" mean the broker never counted a delivery attempt?

**Answer:** Spring receives the JMS Message before conversion; the broker has already delivered it to the consumer/session.

**Question 10.** How does `sessionTransacted=true` help when conversion fails?

**Answer:** It can roll back the delivery so the broker redelivers per policy. It does not fix the payload or define a DLQ automatically.

**Question 11.** Should malformed JSON errors be retried infinitely?

**Answer:** No. They are permanent data errors; apply bounded retries and quarantine/DLQ per policy, fix the producer/schema, then redrive safely.

**Question 12.** Does Spring `ErrorHandler` automatically create a DLQ queue?

**Answer:** No. It aids container error observation; DLQs require explicit broker/application policies.

**Question 13.** Does `AUTO_ACKNOWLEDGE` guarantee a message is retried after an exception in `DefaultMessageListenerContainer`?

**Answer:** No. Per the Spring reference, auto-ack does not guarantee reliable redelivery; prefer transacted sessions when reliability is needed.

**Question 14.** Why can a raw listener catching exceptions and returning normally be dangerous?

**Answer:** The container may ACK/commit the message despite failed decoding/business processing, causing data loss unless durably quarantined.

**Question 15.** Why is `_type` needed with the JMS Jackson converter?

**Answer:** To identify the Java class when deserializing incoming JSON per configuration; logical type-id mappings help govern compatibility and safety.

**Question 16.** When redriving messages from a DLQ, is using `JMSMessageID` as the sole idempotency key sufficient?

**Answer:** No. The provider may assign a new ID; use a stable business/event ID to deduplicate.

**Question 17.** A message has `quantity="abc"` in JSON. Is that always a validation error?

**Answer:** No. Converting String→number may fail before building the DTO, so it is typically a conversion error depending on converter/coercion settings.

**Question 18.** To know whether the business method ran, what should you measure?

**Answer:** Instrument method invocation/business side effects separately, alongside container conversion/validation failures and broker delivery/retry metrics.

**Question 19.** With `jakarta.validation-api` on the classpath but no runtime implementation, will `@Valid` definitely run?

**Answer:** No. A Bean Validation provider and a Spring Validator configured/wired into the method factory are required.

**Question 20.** When encountering `ListenerExecutionFailedException`, what is the first diagnostic step?

**Answer:** Inspect the cause chain and stack frames to distinguish wire conversion, argument binding, pre-invocation validation, or an actual exception inside the method.

## Conclusion

In Spring JMS, entry into a `@JmsListener` **does not begin at the first line of code inside the method**. The framework must already receive `jakarta.jms.Message`, convert data, build a Spring Message, resolve parameters, and possibly run Bean Validation **before calling the Java method**. Any failure in these steps can result in a broker-delivered message whose business method **never executed**.

To handle this properly, you must:

- **Classify errors by stage**, inspecting the root cause instead of only the wrapper.
- Place the **JMS converter** and **Spring method validator** in their respective configuration spots.
- Use `@Payload @Valid` with an actually active runtime Validator.
- Capture pre-handler errors at the container/adapter, not only with in-body `try/catch`.
- Configure transactions/ack, bounded retries, broker DLQ/quarantine, and audited redrive.
- Never equate message delivered, handler invoked, business committed, and JMS acknowledged.

### Official References

1. [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html) — `@JmsListener`, annotated method arguments, `@Payload @Valid`, `DefaultMessageHandlerMethodFactory`, and `Validator`.
2. [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html) — message listener containers, transactions, acknowledgment, and failure propagation.
3. [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html) — `DefaultMessageListenerContainer`/`SimpleMessageListenerContainer`, `AUTO_ACKNOWLEDGE`, and transacted sessions.
4. [Spring Framework — PayloadMethodArgumentResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/support/PayloadMethodArgumentResolver.html) — targetClass conversion, `@Valid`/`@Validated`, and `MethodArgumentNotValidException`.
5. [Spring Framework — DefaultMessageHandlerMethodFactory](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/support/DefaultMessageHandlerMethodFactory.html) — configuring method argument converters and validators.
6. [Spring Framework — JMS MappingJackson2MessageConverter (6.2)](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html) — `MessageType.TEXT`, `setTypeIdPropertyName`, and type-id mappings.
7. [Spring Framework — MessagingMessageListenerAdapter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/adapter/MessagingMessageListenerAdapter.html) — JMS-to-Spring Message adapter and handler invocation.
8. [Spring Framework — AbstractMessageListenerContainer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html) — `setErrorHandler`, converter, acknowledgment, and error handling.
9. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — provider delivery/ack/transactions, message headers, and redelivery.
10. [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/3.0/) — `@Valid` and constraint semantics.
