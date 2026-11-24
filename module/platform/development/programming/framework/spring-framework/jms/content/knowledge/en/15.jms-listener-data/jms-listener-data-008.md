# DefaultMessageHandlerMethodFactory and Argument Resolution in Spring JMS

> **Parent topic:** Listener Data — Spring Framework JMS.  
> **Mission:** Understand how a `@JmsListener` method receives **payload, headers, Spring Messaging Message, raw JMS Message, and Session**; the role of `DefaultMessageHandlerMethodFactory`, `HandlerMethodArgumentResolver` selection order, type conversion, validation, and custom argument resolver extensions. Includes Java 17+ examples for Spring Boot 3.5 with ActiveMQ Artemis.

**Versions:** Spring Framework 6.2.x, Spring Boot 3.5.x, Jakarta Messaging (`jakarta.jms`), Java 17+. Do not mix legacy Spring 5/JMS `javax.jms` with `jakarta.jms`. All custom configuration examples must be evaluated alongside the actual `JmsListenerContainerFactory` bean and message conversion mechanism of the application.

## 1. Why Can a @JmsListener Method Accept So Many Parameter Types?

A low-level JMS consumer typically receives a single `jakarta.jms.Message` object. In Spring, we can write:

~~~java
@JmsListener(destination = "jobs.in")
public void onJob(String jobId) {
    process(jobId);
}
~~~

or:

~~~java
@JmsListener(destination = "jobs.in")
public void onJob(
        @Payload String jobId,
        @Header("tenantId") String tenantId,
        @Header("retryCount") int retryCount) {
    process(jobId, tenantId, retryCount);
}
~~~

With the same transport message, Spring knows which parameter represents the body and which represents metadata because it has an **argument resolution system**. `DefaultMessageHandlerMethodFactory` constructs an `InvocableHandlerMethod` paired with appropriate `HandlerMethodArgumentResolver`s for method-based endpoints. This is what distinguishes a POJO-style `@JmsListener` from a raw `jakarta.jms.MessageListener` callback.

**Separating three responsibilities:**

1. **Listener container:** opens connection/session/consumer, receives messages, manages concurrency, transactions, recovery, and shutdown.
2. **JMS → Spring Messaging adapter/converter:** wraps the raw JMS message, extracts the body, and maps JMS headers/properties to Spring `Message<?>`.
3. **Handler method factory:** takes the converted Spring message, applies argument resolvers, type conversion/validation, and invokes the Java method matching its signature.

`DefaultMessageHandlerMethodFactory` sits at **step 3**. It is not a JMS provider, not a broker, does not pull messages from a queue, does not create transactions, and does not decide the number of listener threads.

## 2. Message Flow Diagram

~~~text
Producer
   |
   |  JMS TextMessage body="job-101"
   |  property tenantId="shop-a", retryCount=2
   v
JMS Queue: jobs.in
   |
   v
DefaultMessageListenerContainer
   |  receives, manages Session + ACK/transaction
   v
MessagingMessageListenerAdapter
   |  holds raw jakarta.jms.Message, jakarta.jms.Session
   |  converts body + headers into Spring Message<?>
   v
InvocableHandlerMethod
   |  created by DefaultMessageHandlerMethodFactory
   |
   +-- @Payload String jobId           -> "job-101"
   +-- @Header("tenantId") String      -> "shop-a"
   +-- @Header("retryCount") int       -> 2
   +-- @Headers Map<String,Object>     -> multiple headers
   +-- jakarta.jms.Message             -> raw message
   +-- jakarta.jms.Session             -> active Session
   |
   v
Java handler / validation / business service
   |
   v
Return or exception
   |
   v
JMS commit / rollback per listener container
~~~

**Two key observations:**
- Raw JMS `Message` and `Session` can be **passed into the invocation by the listener adapter** as special/provided arguments. Not every parameter is produced by `PayloadMethodArgumentResolver`.
- Successful argument conversion **does not equate to** business success; JMS acknowledgment/transactions must be configured independently.

## 3. Table of Supported Parameter Types

| Parameter signature | Data source | Meaning and notes |
| --- | --- | --- |
| `String payload`, `OrderEvent payload` | Spring message payload | For ordinary unannotated parameters, Spring treats them as payload |
| `@Payload String payload` | Spring message payload | Explicit declaration; can be paired with `@Valid` or `@Validated` |
| `@Header("tenantId") String tenantId` | Spring headers | Reads one header/property; supports type conversion when configured |
| `@Header(value="priority", required=false) Integer priority` | Spring headers | Header may be absent; needs a compatible nullable type |
| `@Headers Map<String,Object> all` | Spring headers | Access multiple headers at once |
| `org.springframework.messaging.Message<OrderEvent> msg` | Spring Messaging abstraction | Payload and header map; differs from raw JMS Message |
| `org.springframework.messaging.MessageHeaders headers` | Spring Messaging headers | Reads mapped header map, avoiding raw provider coupling |
| `org.springframework.jms.support.JmsMessageHeaderAccessor accessor` | Spring accessor for JMS headers | Convenient when standard JMS metadata is needed |
| `jakarta.jms.Message raw`, `TextMessage raw` | Raw transport message | Reads JMS headers/properties/body directly via JMS API |
| `jakarta.jms.Session session` | JMS Session of the listener invocation | Use when JMS-specific APIs are truly needed; never close the session yourself |

These types are documented in Spring Framework 6.2's `@JmsListener` reference. Do not confuse `org.springframework.messaging.Message` with `jakarta.jms.Message`: two different interfaces despite the same short name `Message`.

**Single-payload scope:** an ordinary handler represents **one message** and one payload. Declaring two bare unannotated parameters expecting Spring to split one JSON body into two Java variables **is not** default behavior. For multiple fields, use a DTO or extract fields intentionally after conversion.

## 4. @Payload and Payload Recognition Rules

A method:

~~~java
@JmsListener(destination = "jobs.in")
public void handle(String jobId) {
    // jobId is resolved as payload by Spring.
}
~~~

is equivalent in binding intent to:

~~~java
@JmsListener(destination = "jobs.in")
public void handle(@Payload String jobId) {
    // Explicit declaration so readers understand the parameter's source.
}
~~~

`@Payload` in this context is `org.springframework.messaging.handler.annotation.Payload`, **not** a Jakarta JMS annotation.

### 4.1. What If the Body Type Is Incompatible?

Suppose the producer sends a `TextMessage` containing `"job-101"`; the default JMS converter normally produces a String payload. A method accepting `String` works naturally.

If the method instead declares:

~~~java
@JmsListener(destination = "jobs.in")
public void handle(OrderEvent event) {
    // ...
}
~~~

then Spring must have an **actual conversion path** from the incoming data to `OrderEvent`. Merely changing the signature from `String` to a DTO does not conjure up a JSON parser. With `SimpleMessageConverter`, a JSON TextMessage usually remains a `String`. To get a DTO, you need a matching converter/schema (such as Jackson JSON at the JMS layer) or a Spring Messaging `MessageConverter` with explicit logic.

### 4.2. Payload Parameters Are Not Always Valid by Default

- An empty/nullable body can cause `PayloadMethodArgumentResolver` to fail when the parameter is required.
- `@Payload(required=false)` lets you express optional semantics in the resolver, though behavior also depends on the converter/target type.
- `Optional<T>` is only meaningful when the resolver and conversion stack actually support it; do not assume a missing payload always becomes `Optional.empty()` across all versions.
- A message with a malformed schema may fail **before the handler is called**.
- Do not put `@Payload` on a raw `jakarta.jms.Message` expecting it to represent the transport message; let raw messages be supplied by the adapter via an explicit raw parameter.

### 4.3. Why Does the Payload Resolver Run Last?

`PayloadMethodArgumentResolver` is broad in scope: it can treat many unannotated parameters as the payload. Therefore Spring places it **after** specialized resolvers such as `@Header`, `@Headers`, and Spring `Message<?>`. If it ran earlier, metadata parameters could be mistaken for the body.

## 5. @Header: Extracting a Single Header or JMS Property

A JMS producer can send:

~~~java
jmsTemplate.send("jobs.in", session -> {
    TextMessage text = session.createTextMessage("job-101");
    text.setStringProperty("tenantId", "shop-a");
    text.setIntProperty("retryCount", 2);
    text.setJMSCorrelationID("corr-101");
    return text;
});
~~~

With method:

~~~java
@JmsListener(destination = "jobs.in")
public void onJob(
        @Payload String job,
        @Header("tenantId") String tenantId,
        @Header("retryCount") int retryCount) {
    // job="job-101", tenantId="shop-a", retryCount=2
}
~~~

`@Header` reads data from Spring `MessageHeaders` built by the JMS adapter. Application JMS properties are typically mapped to Spring headers. Spring provides `org.springframework.jms.support.JmsHeaders` defining names for several standard JMS headers; use constants rather than guessing spelling when reading correlation ID/message ID/priority.

### 5.1. Missing Headers and `required`

`@Header` treats headers as required by default. If missing, the listener may fail **before entering the business method**. Example allowing absence:

~~~java
public void handle(
        @Payload String body,
        @Header(value = "region", required = false)
        String region) {
    // region may be null; needs dedicated business policy.
}
~~~

When a default value is needed, you can declare `defaultValue` on the annotation:

~~~java
@Header(name = "region", defaultValue = "GLOBAL")
String region
~~~

This is a **method parameter snippet**, not a standalone Java file. A default header is purely handler argument-binding behavior; it **does not modify** the JMS message property stored by the broker and does not change the consumer's JMS selector.

### 5.2. Header Conversion Using ConversionService

Suppose the producer sets a String property `"2"`:

~~~java
text.setStringProperty("retryCount", "2");
~~~

The header resolver can use Spring `ConversionService` to convert `"2"` to `int` in the method, if the conversion service is configured to allow it. This is **conversion at header binding time**, which **differs** from a JMS selector automatically coercing Strings to numbers.

Distinguish clearly:
- **JMS selector** `retryCount >= 2` will not compare numerically by default if the property is a String.
- **Spring `@Header("retryCount") int`** can convert a String to a number when resolving the method parameter.
- **Schema contracts** should still set numeric JMS properties via numeric setters when they are logically numbers.

Do not use header conversion to mask producer type-contract bugs.

### 5.3. Required, Defaults, and Sensitive Data

When a `tenantId` header is used for authorization, never set an arbitrary default tenant. If a sender submits a spoofed JMS property, `@Header("tenantId")` merely extracts that value; it **does not prove the sender was authorized**. Broker ACLs/TLS, identity, and business authorization must verify the tenant within scope.

## 6. @Headers, MessageHeaders, and JmsMessageHeaderAccessor

Use `@Headers` when you need a map:

~~~java
@JmsListener(destination = "jobs.in")
public void handle(
        @Payload String job,
        @Headers Map<String, Object> headers) {
    Object tenant = headers.get("tenantId");
    // Can read other mapped JMS headers/properties.
}
~~~

Use `MessageHeaders` if you want a clearer abstraction:

~~~java
@JmsListener(destination = "jobs.in")
public void handle(
        @Payload String job,
        MessageHeaders headers) {
    String tenant = headers.get("tenantId", String.class);
}
~~~

These examples are **Java method snippets**, requiring imports for `Map`, `@Headers`, `MessageHeaders`, and Spring JMS annotations.

Use Spring `Message<?>` to group both body and metadata:

~~~java
@JmsListener(destination = "jobs.in")
public void handle(org.springframework.messaging.Message<String> message) {
    String job = message.getPayload();
    Object tenant = message.getHeaders().get("tenantId");
}
~~~

**Note:** the header map reflects mapping through `JmsHeaderMapper` or the corresponding adapter. It does not necessarily contain every JMS/provider property under the same name/type as the raw message. When you need an uncommon raw JMS header, add a `jakarta.jms.Message` parameter and read it directly instead of guessing Spring header names.

### 6.1. JmsMessageHeaderAccessor

Spring provides `org.springframework.jms.support.JmsMessageHeaderAccessor` for typed access to JMS headers. When Spring Messaging-level portability is desired, you can use the accessor instead of manually casting `headers.get("jms_...")`:

~~~java
@JmsListener(destination = "jobs.in")
public void handle(
        @Payload String job,
        JmsMessageHeaderAccessor headers) {
    String correlation = headers.getCorrelationId();
    // Check null values and correlation ID contract.
}
~~~

This is an illustrative snippet; import the Spring accessor. Getter names/semantics belong to specific Spring versions, so cross-check Javadoc when upgrading major versions.

## 7. Raw jakarta.jms.Message and Session: Invocation Exceptions to the Rule

`@JmsListener` can receive **raw JMS Message** and **JMS Session**:

~~~java
@JmsListener(destination = "jobs.in")
public void handle(
        @Payload String job,
        jakarta.jms.Message raw,
        jakarta.jms.Session session) throws jakarta.jms.JMSException {

    String jmsMessageId = raw.getJMSMessageID();
    boolean transacted = session.getTransacted();
    // Do not close session yourself: listener container owns its lifecycle.
}
~~~

The JMS listener adapter can pass these raw objects as **additional arguments** to the invoker. That is not the same resolver path as `@Header` or `@Payload`.

**Why need raw message?** You might need:
- `getJMSCorrelationID()`, `getJMSRedelivered()`, or `getJMSReplyTo()` via the JMS API.
- Provider-specific properties or headers not mapped by Spring's mapper.
- Reading a specific `TextMessage`/`BytesMessage` when the contract does not use a Java DTO converter.

**Why need Session?** Certain reply/interop cases need to create JMS messages with the active session; however, most business handlers should not depend on `Session`. Never call `session.close()`, `session.commit()`, `session.rollback()`, or `message.acknowledge()` in general code without designing exact ownership/transaction semantics. With Spring's listener container, it usually handles ACK/commit/rollback.

### 7.1. Raw JMS Message Differs from Spring Message

| Aspect | `jakarta.jms.Message` | `org.springframework.messaging.Message<T>` |
| --- | --- | --- |
| Library | Jakarta Messaging/JMS | Spring Messaging |
| Body | Read via subtype or JMS body API | `getPayload()` already inside generic object |
| Headers | `getJMS...()` / `get...Property()` | `getHeaders()` returns `MessageHeaders` |
| Session | Belongs to JMS container/protocol | Does not carry JMS Session |
| When to use | Need specific transport API | Want handler less coupled to JMS |
| Conversion | Depends on body type & Spring adapter | Spring Messaging method argument resolution |

**Avoid import collisions:** If the same file needs both, write the fully qualified name for at least one type; Java cannot import two `...Message` types with the same simple name and let the compiler disambiguate.

## 8. What Does DefaultMessageHandlerMethodFactory Actually Create?

In Spring Framework 6.2, the class:

~~~text
org.springframework.messaging.handler.annotation.support
    .DefaultMessageHandlerMethodFactory
~~~

implements `MessageHandlerMethodFactory`, `BeanFactoryAware`, and `InitializingBean`. It creates `InvocableHandlerMethod` instances wired with `HandlerMethodArgumentResolver`s.

Common setters:

~~~java
factory.setConversionService(conversionService);
factory.setMessageConverter(springMessagingConverter);
factory.setValidator(validator);
factory.setCustomArgumentResolvers(customResolvers);
~~~

**Important:** `setMessageConverter` on this class accepts **`org.springframework.messaging.converter.MessageConverter`**. It is a **different interface** from `org.springframework.jms.support.converter.MessageConverter` used by `JmsTemplate` and the JMS listener adapter. They cannot be swapped just because both share the name `MessageConverter`.

### 8.1. Resolver Order

The default initialization order of resolvers in Spring Messaging 6.2 is typically:

~~~text
1. HeaderMethodArgumentResolver      -> @Header
2. HeadersMethodArgumentResolver     -> @Headers
3. MessageMethodArgumentResolver     -> Spring Message<?>
4. Custom resolvers (if any)
5. PayloadMethodArgumentResolver     -> @Payload and fallback payload
~~~

**Why do custom resolvers come before payload?** The payload resolver is too broad; if placed before custom resolvers, it would claim almost all custom argument types. Custom resolvers sit after built-in header/message resolvers but before payload; to completely override built-in resolver behavior, construct a custom method factory with an explicit policy rather than merely appending a duplicate resolver.

### 8.2. Roles of ConversionService and MessageConverter

- `ConversionService`: converts parameter/header values between Java types, such as String → int, enums, or domain value objects if a converter is registered.
- **Spring Messaging MessageConverter**: converts the payload inside a Spring `Message<?>` to the target method parameter type via the Messaging converter interface; defaults to `GenericMessageConverter` backed by `ConversionService`.
- **JMS MessageConverter**: converts `TextMessage`, `BytesMessage`, `MapMessage`, JSON JMS messages, etc., into the payload that the adapter puts into Spring Messaging; operates at a different layer.

Do not pass `org.springframework.jms.support.converter.MappingJackson2MessageConverter` into `DefaultMessageHandlerMethodFactory.setMessageConverter(...)`; the signatures are incompatible. If you want a JSON DTO, configure the JMS Jackson converter on `DefaultJmsListenerContainerFactory`/the adapter **or** design a matching Spring Messaging converter, and test end-to-end.

### 8.3. Validator

`setValidator(org.springframework.validation.Validator)` enables validation for `@Payload` arguments annotated with `@Validated` or `@jakarta.validation.Valid`. By default, the method factory does not automatically guarantee execution of all Bean Validation constraints; supply a real validator and the appropriate dependencies.

When the validator reports errors, `PayloadMethodArgumentResolver` may throw `MethodArgumentNotValidException` **before the listener body runs**. This error must be handled by the container's error/transaction policy. Never rely on a `try/catch` inside the business method to catch errors thrown **before method invocation**.

### 8.4. Initializing the Method Factory per Lifecycle

`DefaultMessageHandlerMethodFactory` implements `InitializingBean`; when defined as a `@Bean`, Spring invokes `afterPropertiesSet()` after injecting properties/BeanFactory. If you manually `new` a factory and pass it straight to the registrar outside bean lifecycle management, argument resolvers may **not be initialized yet**. The simplest, safest approach: declare it as a **Spring bean** and inject it into `JmsListenerConfigurer`.

## 9. Proper Configuration via JmsListenerConfigurer

A Spring configurer:

~~~java
@Configuration
@EnableJms
public class JmsMethodConfigurer implements JmsListenerConfigurer {

    private final DefaultMessageHandlerMethodFactory methodFactory;

    public JmsMethodConfigurer(
            DefaultMessageHandlerMethodFactory methodFactory) {
        this.methodFactory = methodFactory;
    }

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {
        registrar.setMessageHandlerMethodFactory(methodFactory);
    }
}
~~~

This is a **configuration class snippet**; it needs a `DefaultMessageHandlerMethodFactory` bean declared elsewhere, along with appropriate Spring imports. `JmsListenerConfigurer` belongs to `org.springframework.jms.annotation`, while `JmsListenerEndpointRegistrar` belongs to `org.springframework.jms.config`.

**Do not confuse the two factories:**
- `registrar.setMessageHandlerMethodFactory(...)` supplies how to **resolve arguments and invoke methods**.
- `registrar.setContainerFactory(...)` supplies the **listener container** to receive messages from the broker.

An endpoint can use a container factory properly configured for transactions/concurrency yet still fail to parse a DTO if the method converter is missing; conversely, a method factory with a good validator does not guarantee JMS retries if the container ACKs before the handler fails.

### 9.1. Does Spring Boot Automatically Enable @JmsListener?

Spring Boot auto-configures listener infrastructure in standard JMS setups. Plain Spring Framework projects can use `@EnableJms`. The lab below declares `@EnableJms` explicitly without creating duplicate infrastructure sets. When working in multi-module applications, check existing factory/annotation support before adding configurations to avoid conflicts.

### 9.2. Selecting an Independent Container Factory

~~~java
@Bean("jmsListenerContainerFactory")
DefaultJmsListenerContainerFactory listenerContainerFactory(
        ConnectionFactory connectionFactory) {

    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("1");
    return factory;
}
~~~

This is a **bean method snippet** importing Jakarta JMS `ConnectionFactory` and Spring's factory. It affects JMS Session, transactions, and concurrency, without replacing `DefaultMessageHandlerMethodFactory`.

## 10. Validation with @Payload and @Validated

Example business rule: a `String` payload is only accepted if it starts with prefix `job-`. With Spring `Validator`:

~~~java
public final class JobIdValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return String.class.equals(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        String value = (String) target;
        if (!value.startsWith("job-")) {
            errors.reject("jobId.invalid", "Job ID must start with job-");
        }
    }
}
~~~

This is a **class snippet**, requiring imports `org.springframework.validation.Validator` and `Errors`, and does not need Jackson/Bean Validation just to validate a string.

Wire into the method factory:

~~~java
@Bean
DefaultMessageHandlerMethodFactory handlerMethodFactory() {
    var factory = new DefaultMessageHandlerMethodFactory();
    factory.setValidator(new JobIdValidator());
    return factory;
}
~~~

Listener using it:

~~~java
@JmsListener(destination = "jobs.in")
public void handle(@Payload @Validated String jobId) {
    // Reaches here only when argument resolution + validator succeed.
}
~~~

`@Validated` is `org.springframework.validation.annotation.Validated`; it marks the argument requiring validation in `PayloadMethodArgumentResolver`. For DTOs with Jakarta Bean Validation constraints (`@NotBlank`, `@Min`, etc.), you need `jakarta.validation.Valid`, a Bean Validation provider (e.g., Hibernate Validator via `spring-boot-starter-validation`), and an appropriate Spring `Validator`.

### Difference from Method-Level Validation

`@Validated` placed on a **payload parameter** triggers validation in the argument resolver; some patterns also use AOP method validation on a class/service. These two paths **differ** in when exceptions are thrown and how they are configured. Do not document it as if every `@NotBlank` on a method parameter runs automatically just because the service class carries `@Validated`.

### Case to Remember: Errors Happen Before the Handler

If `jobId="bad"`, the validator may throw `MethodArgumentNotValidException` before code inside `handle(...)` runs. With a transacted listener container, the error may roll back the JMS Session; with non-transacted/AUTO_ACK, redelivery is not guaranteed the same way. Have a DLQ/max redelivery policy and alerts to avoid poison messages.

## 11. Custom HandlerMethodArgumentResolver

When a handler method needs a domain object built from headers, such as `TenantContext`, you can add a custom resolver.

**Domain type file (Java 17+ snippet):**

~~~java
public record TenantContext(String tenantId) {}
~~~

**Spring Messaging resolver snippet:**

~~~java
public final class TenantContextArgumentResolver
        implements HandlerMethodArgumentResolver {

    @Override
    public boolean supportsParameter(MethodParameter parameter) {
        return TenantContext.class.equals(parameter.getParameterType());
    }

    @Override
    public Object resolveArgument(
            MethodParameter parameter,
            org.springframework.messaging.Message<?> message) {

        Object value = message.getHeaders().get("tenantId");
        if (!(value instanceof String tenant) || tenant.isBlank()) {
            throw new IllegalArgumentException("Missing tenantId");
        }
        return new TenantContext(tenant);
    }
}
~~~

These snippets require imports `org.springframework.core.MethodParameter`, `org.springframework.messaging.handler.invocation.HandlerMethodArgumentResolver` and must be placed in properly named files/classes. **Do not pick the wrong one** — `org.springframework.web.method.support.HandlerMethodArgumentResolver` from Spring MVC: the messaging handler resolver is a **different package and different signature**.

Registering it:

~~~java
@Bean
DefaultMessageHandlerMethodFactory handlerMethodFactory() {
    var factory = new DefaultMessageHandlerMethodFactory();
    factory.setCustomArgumentResolvers(
            List.of(new TenantContextArgumentResolver()));
    return factory;
}
~~~

Requires `import java.util.List`. A method-based listener can then accept:

~~~java
@JmsListener(destination = "jobs.in")
public void handle(@Payload String jobId, TenantContext context) {
    // Reads context.tenantId() created by the custom resolver.
}
~~~

**What to test:** the resolver only matches its exact target type, does not hijack `@Header` or Spring `Message<?>` parameters, and throws an appropriate exception when the header is missing. Because custom resolvers run **before payload fallback**, do not annotate `TenantContext` with `@Payload` expecting it to always be converted from the body; decide explicitly where each parameter comes from.

### When Is a Custom Resolver Unnecessary?

If you only need a single header, `@Header("tenantId")` is enough. A custom resolver is worthwhile when multiple handlers share a **context object with dedicated validation/normalization rules**, and you want to centralize context construction. A resolver is not a standalone security boundary: tenant info from a JMS property must still be verified against identity/broker ACLs and business authorization.

## 12. Complete Lab: Java 17, Spring Boot 3.5, and Embedded Artemis

The lab focuses on **method factory + argument resolution + validation**, without needing a Jackson JSON converter. A `TextMessage` containing `job-101` is sent alongside tenant/attempt metadata. The listener declares all forms:
- `@Payload @Validated String`;
- `@Header("tenantId") String`;
- `@Header("retryCount") int`;
- `@Headers Map<String,Object>`;
- raw `jakarta.jms.Message`;
- `jakarta.jms.Session`.

A `CountDownLatch` makes `ApplicationRunner` wait for the callback, printing one deterministic result line regardless of thread scheduling.

### 12.1. Initializing the Maven Project

Create a project on https://start.spring.io/:
- Maven, Java 17+, Spring Boot 3.5.x.
- Group `com.example`, artifact `jms-arguments-lab`.
- Package `com.example.jmsargumentslab`.
- Dependency **Spring for Apache ActiveMQ Artemis** (`spring-boot-starter-artemis`).

Add to `pom.xml` with the Spring Boot parent/BOM:

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-server</artifactId>
</dependency>
~~~

This is an **additional dependency**, not the full `pom.xml`. Use the Artemis version managed by the Boot BOM. Because the lab uses a custom Spring `Validator`, adding the Jakarta Bean Validation starter is **not required**; to switch to `@Valid` Bean Validation DTOs, add `spring-boot-starter-validation`.

### 12.2. Configuring the Local Broker

Create `src/main/resources/application.properties`:

~~~properties
spring.application.name=jms-arguments-lab
spring.main.web-application-type=none
spring.artemis.mode=embedded
spring.artemis.embedded.queues=handler.method.demo
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

This embedded broker is solely for demonstrating argument resolution; `persistent=false` means the lab **does not verify durability across restarts**. Production environments require a broker with persistence, auth/TLS, quotas, and proper DLQs.

### 12.3. File 1 — Application Entry Point, JMS Factory, and Producer

Save `src/main/java/com/example/jmsargumentslab/JmsArgumentsLabApplication.java`:

~~~java
package com.example.jmsargumentslab;

import java.util.concurrent.TimeUnit;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.messaging.handler.annotation.support.DefaultMessageHandlerMethodFactory;

@SpringBootApplication
@EnableJms
public class JmsArgumentsLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsArgumentsLabApplication.class, args);
    }

    @Bean("jmsListenerContainerFactory")
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory factory) {

        var containerFactory = new DefaultJmsListenerContainerFactory();
        containerFactory.setConnectionFactory(factory);
        containerFactory.setSessionTransacted(true);
        containerFactory.setConcurrency("1");
        return containerFactory;
    }

    @Bean
    DefaultMessageHandlerMethodFactory jmsHandlerMethodFactory(
            JobIdValidator validator) {

        var methodFactory = new DefaultMessageHandlerMethodFactory();
        methodFactory.setValidator(validator);
        return methodFactory;
    }

    @Bean
    ApplicationRunner publish(
            JmsTemplate template,
            ListenerResult result) {

        return args -> {
            template.send("handler.method.demo", session -> {
                TextMessage text =
                        session.createTextMessage("job-101");
                text.setStringProperty("tenantId", "shop-a");
                text.setIntProperty("retryCount", 2);
                text.setJMSCorrelationID("corr-101");
                return text;
            });

            if (!result.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Listener did not handle the message in time");
            }

            System.out.println("RESULT=" + result.value());
        };
    }
}
~~~

**Why is `jmsHandlerMethodFactory` a bean?** Spring automatically invokes lifecycle initialization (`afterPropertiesSet`) on `DefaultMessageHandlerMethodFactory` before the configurer attaches it to the registrar. Meanwhile, `JmsListenerContainerFactory` is a separate bean for receiving messages with `sessionTransacted=true`. Those are **two factories with different functions**.

### 12.4. File 2 — JmsListenerConfigurer Wiring the Method Factory

Save `src/main/java/com/example/jmsargumentslab/ArgumentConfigurer.java`:

~~~java
package com.example.jmsargumentslab;

import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.JmsListenerConfigurer;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.messaging.handler.annotation.support.DefaultMessageHandlerMethodFactory;

@Configuration(proxyBeanMethods = false)
public class ArgumentConfigurer implements JmsListenerConfigurer {

    private final DefaultMessageHandlerMethodFactory methodFactory;

    public ArgumentConfigurer(
            DefaultMessageHandlerMethodFactory methodFactory) {
        this.methodFactory = methodFactory;
    }

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {
        registrar.setMessageHandlerMethodFactory(methodFactory);
    }
}
~~~

`ArgumentConfigurer` **does not** replace the JMS container factory declared in the application. It only changes how Spring creates invokers and binds arguments for `@JmsListener` method-based endpoints.

### 12.5. File 3 — Validator for String Payload

Save `src/main/java/com/example/jmsargumentslab/JobIdValidator.java`:

~~~java
package com.example.jmsargumentslab;

import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component
public class JobIdValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return String.class.equals(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        String jobId = (String) target;
        if (!jobId.startsWith("job-")) {
            errors.reject(
                    "jobId.invalid",
                    "Job ID must start with job-");
        }
    }
}
~~~

`JobIdValidator` illustrates a pure Spring Validator without needing Hibernate Validator/a Bean Validation provider. Real projects typically validate DTOs with Jakarta Bean Validation constraints and explicit schema contracts/versioning.

### 12.6. File 4 — Listener with All Argument Types

Save `src/main/java/com/example/jmsargumentslab/JobListener.java`:

~~~java
package com.example.jmsargumentslab;

import java.util.Map;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.Session;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;
import org.springframework.validation.annotation.Validated;

@Component
public class JobListener {

    private final ListenerResult result;

    public JobListener(ListenerResult result) {
        this.result = result;
    }

    @JmsListener(
            id = "methodArgsListener",
            destination = "handler.method.demo")
    public void onJob(
            @Payload @Validated String jobId,
            @Header("tenantId") String tenantId,
            @Header("retryCount") int retryCount,
            @Headers Map<String, Object> headers,
            Message raw,
            Session session) throws JMSException {

        if (!tenantId.equals(headers.get("tenantId"))) {
            throw new IllegalStateException(
                    "Header mapping mismatch");
        }

        String correlation = raw.getJMSCorrelationID();
        boolean transacted = session.getTransacted();

        result.record(
                jobId + "|" + tenantId + "|" + retryCount
                + "|" + correlation + "|" + transacted);
    }
}
~~~

Points to observe:
- `@Payload @Validated` triggers `JobIdValidator` via `DefaultMessageHandlerMethodFactory`.
- `@Header` resolves the `tenantId` string and `retryCount` int.
- `@Headers` holds the map of Spring headers mapped from JMS properties.
- `Message raw` here is **`jakarta.jms.Message`**; importing `org.springframework.messaging.Message` gives different behavior and API.
- `Session` is supplied by the container; `session.getTransacted()` returns `true` per `setSessionTransacted(true)` in the lab.
- The method declares `throws JMSException` because raw JMS getters throw checked exceptions; Spring method invocation can propagate exceptions for container management.

**Never call `session.commit()`/`session.close()` inside the listener**. Let the container decide the transaction outcome after the method finishes.

### 12.7. File 5 — Synchronizing Output to Avoid Racing with the Listener Thread

Save `src/main/java/com/example/jmsargumentslab/ListenerResult.java`:

~~~java
package com.example.jmsargumentslab;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.stereotype.Component;

@Component
public class ListenerResult {

    private final CountDownLatch latch = new CountDownLatch(1);
    private volatile String value;

    public void record(String newValue) {
        this.value = newValue;
        latch.countDown();
    }

    public boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return latch.await(timeout, unit);
    }

    public String value() {
        return this.value;
    }
}
~~~

Use `CountDownLatch` only to prove the callback ran. In production, **never use** a fixed latch to coordinate a long-running JMS pipeline; use metrics, transactions, and proper status stores.

### 12.8. Running and Stdout

Linux/macOS:

~~~bash
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

With embedded Artemis running, an initially empty queue, no competing consumers, all Spring beans loaded, and the callback completing within 10 seconds, the line printed by the application is:

~~~text
RESULT=job-101|shop-a|2|corr-101|true
~~~

Other Boot/Artemis logs may appear before/after. After the runner prints the result line, the process may keep running because JMS listener containers use daemon/worker threads; stop with Ctrl+C and observe graceful shutdown.

**What the RESULT line proves:** the payload was resolved, headers/JMS objects were supplied, the validator accepted `job-101`, and the Session is transacted. **It does not prove** exactly-once business effects or that the JMS commit already occurred at the exact moment `ListenerResult.record` was called; the container commit happens in lifecycle steps after the callback.

### 12.9. Controlled Validation Error Experiment

Change `"job-101"` to `"invalid-101"`. The validator reports an error before the method body runs. Because the factory uses JMS transactions, the message may be rolled back and redelivered by the broker per policy. **Do not test this on a production broker or an unbounded-retry queue**: a poison message can loop endlessly and the runner will time out. For integration tests, configure max deliveries and a DLQ, then inspect delivery/rollback counts.

### 12.10. Missing Header Error Experiment

Remove `setStringProperty("tenantId","shop-a")` when creating the message. `@Header("tenantId")` is required by default; resolution may fail **before method invocation**, never reaching the `if` statement in the handler. This is an important boundary between argument binding errors and business logic errors. This scenario also requires a dedicated test broker with a retry budget/DLQ.

## 13. JSON DTO: Do Not Confuse the Two Converter Systems with the Same Name

When the payload is JSON from a `TextMessage` and you want:

~~~java
@JmsListener(destination = "orders.json")
public void onOrder(@Valid @Payload OrderEvent event) {
    // DTO has been converted and validated.
}
~~~

the following conditions are required:
1. The producer emits a **JSON body matching the schema**, not just a Java `toString()`.
2. The container/adapter uses an appropriate JSON converter, such as **`org.springframework.jms.support.converter.MappingJackson2MessageConverter`** in Spring Framework 6.x, with target text/bytes and type ID mapping (or an explicit typed parsing strategy).
3. `DefaultMessageHandlerMethodFactory` has a Spring `Validator` capable of validating the DTO, typically via `LocalValidatorFactoryBean` and `spring-boot-starter-validation`.
4. `@Valid` is `jakarta.validation.Valid`; `OrderEvent` constraints define required fields/ranges.
5. JMS transactions/ACK, DLQ, and idempotency satisfy the business contract.

**Two non-interchangeable interfaces:**

~~~text
org.springframework.jms.support.converter.MessageConverter
   - toMessage(Object, jakarta.jms.Session)
   - fromMessage(jakarta.jms.Message)

org.springframework.messaging.converter.MessageConverter
   - toMessage(Object, MessageHeaders)
   - fromMessage(org.springframework.messaging.Message<?>, Class<?>)
~~~

Depending on version, the Spring Messaging interface has overloads supporting conversion hints. The illustrative lines show key signatures, **not full interface definitions to copy and compile**.

### JSON Security Notes

If the converter reads type IDs from JMS properties:
- Use fixed aliases and an explicit allowlist; never allow arbitrary Java FQCNs from untrusted sources.
- Keep Spring Framework updated with current security patches; do not treat a type-ID map as the sole deserialization defense.
- Avoid broad Jackson polymorphic default typing, configure parser limits, and validate schemas.
- Do not send Java `ObjectMessage` across untrusted service boundaries just to receive typed DTOs.

## 14. Tuning ConversionService for Headers/Domain Types

To accept `@Header("region") RegionCode region` instead of a String, you can register a converter on `ConversionService`:

~~~java
// Snippet: app-defined enum RegionCode { APAC, EU, US }.
var conversion = new DefaultFormattingConversionService();
conversion.addConverter(
        String.class,
        RegionCode.class,
        RegionCode::valueOf);

var methodFactory = new DefaultMessageHandlerMethodFactory();
methodFactory.setConversionService(conversion);
~~~

This is a **configuration snippet**, requiring imports for `DefaultFormattingConversionService`, the DTO/enum, and registering the factory as a Spring bean so lifecycle initializes the resolvers. In the lab, a dedicated method factory bean already exists; do not copy this snippet to create **a second factory** while omitting the validator configuration.

Choose converters intentionally:
- What type does the header value have in JMS?
- Is conversion case-sensitive?
- What exception is thrown for invalid values?
- If the header is optional, how is null handled?
- Does this code need telemetry/auditing when mapping fails?

A `ConversionService` does not automatically parse JSON DTOs without an appropriate `MessageConverter`; it primarily manages conversions between Java value types.

## 15. Custom Resolver or @Header? Selection Criteria

| Requirement | Solution | Notes |
| --- | --- | --- |
| One String/number property | `@Header` | Usually sufficient; readable |
| All Spring headers | `@Headers` or `MessageHeaders` | Preserves abstraction |
| Unmapped JMS-specific header | raw `jakarta.jms.Message` | Accepts transport coupling |
| Simple-type payload | `@Payload` + default converter | TextMessage → String |
| JSON DTO payload | JSON converter + validator | Verify schema/type security |
| Domain context built from multiple headers | Custom `HandlerMethodArgumentResolver` | Runs before payload fallback |
| Receiving `Session` to send JMS replies | raw `jakarta.jms.Session` | Never control transactions arbitrarily |
| Preventing handler execution when DTO invalid | `setValidator` + `@Valid`/`@Validated` | Must supply a real validator |
| Tuning threads/recovery/transactions | `DefaultJmsListenerContainerFactory` | Separate from method factory |

**Do not build a custom resolver just to rename `tenantId`:** this can normally be handled via `@Header` or a domain service. A new resolver increases complexity around resolution order and error handling.

## 16. Common Errors and Diagnostics

| Symptom | Possible cause | Diagnostic steps |
| --- | --- | --- |
| `@Header` cannot find `tenantId` | Producer omitted JMS property, different mapper, wrong casing | Read raw JMS properties and Spring headers on a test broker |
| `@Header int` fails type conversion | Property is an invalid String or `ConversionService` lacks converter | Check producer setter and actual value |
| `@Headers Map` misses a field | JMS header mapper only copies a subset or field is in the body | Do not guess; inspect raw message and mapper config |
| Method receives String instead of DTO | `SimpleMessageConverter` does not parse JSON | Attach a JMS JSON converter/schema |
| `@Valid` has no effect | Missing Spring Validator on factory or Bean Validation provider | Configure `setValidator`, add validation starter if using constraints |
| Custom resolver does not run | Wrong interface package or `supportsParameter` returns false | Use messaging resolver, test resolution order |
| Spring resolves payload instead of `TenantContext` | Resolver not registered on the factory used by annotated methods | Check registrar/method factory bean |
| Method factory fails after manual `new` | `afterPropertiesSet` never ran to initialize argument resolvers | Declare the method factory as a Spring bean |
| Sees `Message` without `getPayload()` | Imported `jakarta.jms.Message` instead of Spring Messaging `Message<?>` | Use fully qualified class names when both are needed |
| `Session` missing/mismanaged | Handler invoked outside JMS listener adapter or closed manually | Inject only via `@JmsListener` with valid infrastructure |
| Converter error not caught by handler's `catch` | Error occurs before invocation | Check container error handler, transactions, and DLQ |
| Delivery count mismatch | Rollback, broker redelivery, concurrency, or ack mode | Enable message ID/correlation ID/retry metrics, idempotency |
| `@Header(required=false) int` fails when missing | Primitive `int` cannot represent null | Use `Integer` or nullable `String` |
| Duplicate method invocation | Two listener endpoints on same queue or redelivery | Check registry IDs, subscriptions, and idempotency |
| No listener runs at all | Misconfigured `@EnableJms`/Boot autoconfig/factory/connection | Check Spring context, broker URL, destination name |
| Custom factory loses Boot defaults | Created `new DefaultJmsListenerContainerFactory` without configurer | Use `DefaultJmsListenerContainerFactoryConfigurer` to retain Boot settings |
| ACK occurs before business success | Non-transacted container/session or swallowed exception | Review ACK policy; handle failures via transactions, DLQ |
| Repeated validation errors cause backlog | Poison message lacking redelivery limits | Bounded retries, quarantine/DLQ, alerts |

### About Logging/Debugging

Log **destination, endpoint ID, JMSMessageID, correlation ID, error category, and redelivery count** when supported by the provider, without logging entire payloads containing PII/secrets just for diagnostics. Payload validation errors can happen before the method body; monitor container-level error handlers rather than relying solely on in-handler logs.

## 17. Transactions, Retries, DLQ, and Work Boundaries

In the lab, `sessionTransacted=true` separates the phases:

~~~text
Broker delivers message
  -> JMS listener container receives in Session
  -> message converter / argument resolvers
  -> payload validator
  -> business handler
  -> handler returns normally => local JMS commit
  -> handler/conversion error => local JMS rollback (broker policy)
~~~

If a message repeatedly fails validation, it may be redelivered up to the broker's limit and moved to DLQ; broker policies must be configured. If a handler catches an exception, logs it, and **returns normally**, the container may commit as successful. That can cause silent work loss.

**No automatic business exactly-once:**
- Handler writes to DB, process crashes before JMS commit → broker may redeliver and the DB operation repeats.
- Use an idempotency key per event/business ID, or an inbox/dedup table with a unique constraint.
- If a producer must publish messages alongside a DB transaction, consider a transactional outbox.
- A local JMS transaction does not automatically include a DB transaction; if XA/JTA is genuinely used, it must be carefully designed, tested, and accounted for in cost.

`DefaultMessageHandlerMethodFactory` only ensures arguments are bound and validated properly; it **does not solve** delivery guarantees, persistence, DLQ, ordering, or network partitions.

## 18. Testing: Unit, Integration, Negative Cases

### 18.1. Method-Level Unit Tests

For custom resolvers/validators:
- `JobIdValidator.supports(String.class)` must be true; `supports(Integer.class)` must be false.
- `validate("job-101")` produces no errors; `validate("bad")` produces an error code.
- `TenantContextArgumentResolver.supportsParameter(...)` matches `TenantContext` and rejects other types.
- `resolveArgument` reads `tenantId` from `MessageHeaders` properly and fails when absent.
- Custom `ConversionService` mappings for enums, numbers, and malformed values must have explicit tests.

### 18.2. Real Broker Integration Tests

| Scenario | Expected behavior |
| --- | --- |
| TextMessage `job-101` with `tenantId` and `retryCount` | Handler receives String, int, Map, and raw JMS Message/Session |
| JMS correlation ID sent | Raw JMS getter reads it back accurately |
| Payload starts with `job-` | Validator passes, method runs |
| Payload `bad-1` | Validator fails before invocation; broker handles per transaction |
| `tenantId` header missing | `@Header` fails before invocation |
| Numeric header set as String `"2"` | Converts if `ConversionService` allows; JMS selector still needs proper type contract |
| Target method expects DTO yet JMS converter is Simple | Conversion fails or type mismatches; does not silently build DTO |
| Registered custom `TenantContext` resolver | Context is built before payload fallback |
| Registry has exact endpoint ID | No accidental duplicate consumers created |
| Listener throws exception after business write | Transaction/rollback and idempotency verified |
| Invalid JSON or unknown type ID | Conversion/error handler/DLQ operates |
| Broker reconnect/rolling deployment | Container recovery and backlog compatibility |
| App receives SIGTERM while handler runs | Container stops cleanly, handling in-flight messages per policy |

**Do not judge retries solely by business method logs.** Conversion/validation failures can occur before the method runs, so inspect JMS delivery counts, broker DLQ, transactions, and Spring listener exception logs.

### 18.3. Why Unit Tests Alone Are Insufficient

Mocking `Message<?>` can prove a custom resolver works. However, it does not verify JMS Session injection, the header mapper, broker selectors, ACK/commit, redelivery, or thread lifecycles. Use local/containerized staging Artemis for integration tests; never test poison messages on production queues.

## 19. Practical Listener Design Checklist

- Does the method clearly separate payload, headers, raw JMS message, and Session?
- Are package imports for the two `Message` types accurate?
- Does the JMS producer set properties with the contracted names and Java types?
- Does `@Header` handle optional/missing values properly, avoiding primitives when nullable?
- Do Spring `MessageHeaders`/`JmsHeaderMapper` preserve the required metadata?
- Is `DefaultMessageHandlerMethodFactory` registered via `JmsListenerConfigurer`/`JmsListenerEndpointRegistrar`?
- Is the method factory a Spring bean that undergoes initialization?
- Is the Validator configured and `@Payload @Valid`/`@Validated` used accurately?
- Are Spring Messaging `MessageConverter` and Spring JMS `MessageConverter` kept distinct?
- Do custom resolvers use the messaging package and run before payload fallback?
- Does the JMS container factory have the right `ConnectionFactory`, `pubSubDomain`, concurrency, transactions, and converter?
- When customizing Spring Boot auto-configuration, are relevant defaults preserved?
- Do JSON DTOs have schema/version/type-ID allowlists, parser limits, and validation?
- Do exceptions thrown from listeners roll back per broker policy? Are poison messages bounded via retry budgets/DLQ?
- Is idempotency implemented when the broker redelivers after a crash?
- Are registry IDs, error handlers, JMS message IDs, DLQs, and shutdown monitored?
- Are integration tests covering missing headers, conversion failures, validation failures, and happy paths?
- Do handlers avoid calling `Session.close()`/`commit()` arbitrarily?
- Are headers from unverified producers never trusted as the sole authorization source?

## 20. Reinforcement Exercises

1. Diagram the three layers: listener container, JMS-to-Spring converter, and handler method factory.
2. A method `onJob(String job, @Header("tenantId") String tenant)` receives a JMS `TextMessage` and `tenantId` property. Which resolver handles each parameter?
3. Change `@Header("retryCount") int` to `Integer` with a missing property; what changes when `required=false` is set?
4. Why does the method factory's `setMessageConverter(...)` reject `org.springframework.jms.support.converter.MappingJackson2MessageConverter`?
5. Explain why `PayloadMethodArgumentResolver` must come after custom resolvers.
6. A listener wants to receive raw `jakarta.jms.Message` and `org.springframework.messaging.Message<String>` together. How do you avoid import collisions?
7. If `@Validated @Payload String` is rejected by the validator, does code inside the method execute? How does the container handle the message transactionally?
8. Add a custom `TenantContext` resolver and prove it extracts the ID from headers rather than a JSON body.
9. Use `@Headers Map` to inspect message metadata and compare with `raw.getJMSCorrelationID()`; can they differ due to the mapper?
10. Explain why `@Header("tenantId")` does not automatically authenticate or authorize the tenant.
11. An application defines a `DefaultMessageHandlerMethodFactory` bean without wiring it to the registrar; do `@JmsListener` methods use that bean automatically?
12. Change the lab's queue name to one absent on the broker with auto-create disabled; distinguish connection/destination errors from argument resolution errors.
13. Test a malformed `job=bad-1` message in staging, verifying rollback, redelivery count, and DLQ without causing infinite retries.
14. Configure a typed v2 DTO converter/validator while the backlog holds v1 JSON; propose a migration using schema versions, aliases, and tests.
15. In the lab, refactor the method to take Spring `Message<String>` instead of `@Payload String`/`@Headers Map`; what information remains accessible and what still requires raw access?
16. Why doesn't a `RESULT=...` line printed from the callback prove a JMS commit or database exactly-once execution?

## Official References

- Spring Framework 6.2 — **Annotation-driven JMS Listener Endpoints**, supported arguments and validator configuration: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework 6.2 — **DefaultMessageHandlerMethodFactory** Javadoc, ConversionService, MessageConverter, Validator, custom resolvers: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/messaging/handler/annotation/support/DefaultMessageHandlerMethodFactory.html
- Spring Framework 6.2 — **PayloadMethodArgumentResolver** Javadoc, validation and fallback payload: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/messaging/handler/annotation/support/PayloadMethodArgumentResolver.html
- Spring Framework 6.2 — **JmsListenerConfigurer** Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/annotation/JmsListenerConfigurer.html
- Spring Framework 6.2 — **MessagingMessageListenerAdapter** Javadoc, raw JMS Message/Session as additional arguments: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/listener/adapter/MessagingMessageListenerAdapter.html
- Spring Framework 6.2 — **JmsListener** API, supported method signatures: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/annotation/JmsListener.html
- Spring Boot 3.5 — **Messaging with JMS**, Artemis autoconfiguration: https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html
- Spring Boot 3.5 — **System Requirements**, Java 17: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Jakarta Messaging 3.1 — **JMS Message and Session APIs**: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
