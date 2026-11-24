# Validating Payloads with @Valid and Validator in a Spring JMS Listener

## 1. Why Does a Message Reaching the Broker Not Mean the Payload Is Valid?

In Spring JMS, `@JmsListener` receives messages sent by another application, another software version, or an integration system. Even when the broker delivers the message successfully, **the content is not necessarily well-formed or valid for business rules**. Common scenarios include:

- JSON missing `orderId` or containing an empty string.
- `quantity=0`, negative, or exceeding contract limits.
- Shipping address missing `city`, or country code violating rules.
- Producer sending an old schema, wrong data types, or unsupported new fields.
- A message redelivered by the broker after a failure where the handler never validated data.
- Syntactically valid input that violates rules like exceeding quota, nonexistent order, or duplicate command ID.

**Bean Validation** (Jakarta Validation, typically using Hibernate Validator) lets you declare common data constraints directly on **DTOs used at the listener boundary**. Spring Messaging can apply those constraints to a `@Valid`-annotated payload parameter before invoking business logic.

Example:

```java
@JmsListener(destination = "demo.validation.orders")
public void receive(@Payload @Valid OrderCommand command) {
    // Only reaches here if the payload was converted and passed
    // the configured Bean Validation constraints.
    orderService.placeOrder(command);
}
```

This is an **illustrative method snippet**, not a standalone runnable class: it needs a constrained DTO, a `MessageConverter` if the body is JSON, a Bean Validation provider, and a **Validator wired to the listener method adapter**.

### 1.1. Processing Pipeline

```text
JMS Broker
    |
    v
MessageListenerContainer (Consumer/Session)
    |
    v
JMS Message (TextMessage / BytesMessage / ...)
    |
    +--> JMS MessageConverter: body -> Java DTO
    |         |
    |         +--> JSON/type/converter error -> conversion failure
    |
    v
Spring Messaging argument resolver: @Payload
    |
    v
Validator: @Valid / @Validated and constraints on DTO
    |
    +--> violations found -> MethodArgumentNotValidException
    |                        business handler not yet invoked
    |
    v
@JmsListener method
    |
    v
Business validation / authorization / transaction / side effects
    |
    v
Container decides ACK/commit or rollback per configuration
```

**Key takeaway:** `@Valid` **does not automatically decode JSON**, `MessageConverter` **does not automatically validate business rules**, and the JMS broker **does not automatically run Bean Validation on payloads**. All three layers are needed: conversion, structural validation, and business validation.

## 2. Components and Imports to Remember

| Component | Package / role | Note |
| --- | --- | --- |
| `@JmsListener` | `org.springframework.jms.annotation.JmsListener` | Marks the method receiving messages |
| `@Payload` | `org.springframework.messaging.handler.annotation.Payload` | Identifies the parameter receiving the converted body |
| `@Valid` | `jakarta.validation.Valid` | Triggers Bean Validation on the payload object if a Validator is configured |
| `@Validated` | `org.springframework.validation.annotation.Validated` | Spring variant, can select validation groups |
| `@NotNull` | `jakarta.validation.constraints.NotNull` | Value must not be null |
| `@NotBlank` | `jakarta.validation.constraints.NotBlank` | `CharSequence` not null and containing non-whitespace characters |
| `@Size` | `jakarta.validation.constraints.Size` | Length/size of collection, string, array, or map |
| `@Min` / `@Max` | `jakarta.validation.constraints.Min/Max` | Bounds on supported integer values |
| `@Positive` | `jakarta.validation.constraints.Positive` | Positive number, excluding 0 |
| `@Pattern` | `jakarta.validation.constraints.Pattern` | Validates a string against a regex |
| `jakarta.validation.Validator` | Jakarta Validation API | `validate(object)` returns `Set<ConstraintViolation<T>>` |
| `org.springframework.validation.Validator` | Spring validation API | `supports(Class<?>)`, `validate(Object, Errors)` |
| `LocalValidatorFactoryBean` | `org.springframework.validation.beanvalidation.LocalValidatorFactoryBean` | Bridge implementing both Spring Validator and Jakarta Validator |
| `DefaultMessageHandlerMethodFactory` | `org.springframework.messaging.handler.annotation.support` | Configures argument resolution and Validator for listener methods |
| `JmsListenerConfigurer` | `org.springframework.jms.annotation` | Customizes the listener endpoint registrar |
| `JmsListenerEndpointRegistrar` | `org.springframework.jms.config` | Sets the `MessageHandlerMethodFactory` used for endpoints |

**Important for Spring Boot 3+/Spring Framework 6+:** use `jakarta.validation.*` and `jakarta.jms.*` packages; do not mix `javax.validation.*` / `javax.jms.*` from legacy libraries. Constraint annotations are only API; a **Bean Validation provider** (typically Hibernate Validator, via `spring-boot-starter-validation`) is required to execute them.

### 2.1. `@Valid` Differs from `@NotBlank`

- `@Valid` is a **marker requesting validation of an object**, not a constraint definition itself.
- `@NotBlank`, `@NotNull`, `@Min`, `@Size`, and `@Pattern` are **concrete constraints on a field/record component/property**.
- Putting `@Valid` on a DTO with no constraints will not magically infer "business invalidity."
- Putting constraints on a DTO without **registering a Validator on the handler factory** may mean listener-boundary validation does not occur as expected.
- `@Valid` on a nested object field **cascades** validation to the nested DTO when that property is non-null.

## 3. Designing an Input DTO with Clear Constraints

Suppose a queue receives order commands:

```json
{
  "orderId": "order-42",
  "quantity": 2,
  "shipping": {
    "city": "Ha Noi",
    "countryCode": "VN"
  }
}
```

Lesson contract schema:

| Field | Constraint | Meaning |
| --- | --- | --- |
| `orderId` | `@NotBlank`, `@Size(max=64)` | Non-empty; prevents abnormally long keys |
| `quantity` | `@NotNull`, `@Min(1)`, `@Max(500)` | Quantity in range 1–500 |
| `shipping` | `@NotNull`, `@Valid` | Address must be present and nested fields validated |
| `shipping.city` | `@NotBlank`, `@Size(max=100)` | City has a name |
| `shipping.countryCode` | `@NotBlank`, `@Pattern("[A-Z]{2}")` | Two uppercase letters per demo contract |

Java 17 record:

```java
package com.example.jms;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record OrderCommand(
        @NotBlank @Size(max = 64) String orderId,
        @NotNull @Min(1) @Max(500) Integer quantity,
        @NotNull @Valid ShippingAddress shipping
) {
    public record ShippingAddress(
            @NotBlank @Size(max = 100) String city,
            @NotBlank @Pattern(regexp = "[A-Z]{2}") String countryCode
    ) {}
}
```

### 3.1. Why Use `Integer` Instead of `int` for `quantity`?

When JSON omits a field, the converter may assign the primitive default value; with `int`, `0` is easily confused between "0 was supplied" and "the field was absent." `Integer` exposes null so `@NotNull` reports a violation. Use `@Min(1)` to reject 0 and negatives, and `@Max(500)` to cap oversized quantities.

**Note:** *an absent field* and *a field with explicit null* may both become `null` when Jackson maps into a record. If the contract must strictly distinguish those two cases, use JSON Schema validation/`JsonNode` or a custom deserializer at the protocol layer; `@NotNull` alone does not distinguish them.

### 3.2. Why Do You Need `@NotNull @Valid ShippingAddress shipping`?

`@Valid` on a nested field **does not** mean the field is required. Bean Validation **does not cascade into null**. Therefore:

```java
@Valid ShippingAddress shipping
```

when `shipping == null` normally produces no nested validation error. To require an address, use:

```java
@NotNull @Valid ShippingAddress shipping
```

When `shipping` is present, `@Valid` instructs validation to check `city` and `countryCode`. If you forget nested `@Valid`, many providers will not validate constraints inside the nested object when validating the root DTO.

### 3.3. `@NotNull`, `@NotEmpty`, and `@NotBlank` Are Not Equivalent

| Value | `@NotNull` | `@NotEmpty` on String | `@NotBlank` on String |
| --- | --- | --- | --- |
| `null` | Invalid | Invalid | Invalid |
| `""` | Valid | Invalid | Invalid |
| `"   "` | Valid | Valid | Invalid |
| `"order-42"` | Valid | Valid | Valid |

`@NotBlank` fits order IDs/required strings. `@NotNull` fits numbers or objects. `@NotEmpty` is for collections/maps/arrays/strings that must be non-empty without treating whitespace as blank. Depending on version/provider, applying constraints to an **incompatible Java type** can throw `UnexpectedTypeException` rather than producing a normal violation.

## 4. Where Does @Payload @Valid Run in Spring JMS?

Method:

```java
@JmsListener(destination = "orders.commands")
public void receive(@Payload @Valid OrderCommand command) {
    // business logic
}
```

Spring JMS creates a listener endpoint and container, then uses a listener method adapter. During **argument resolution**, `PayloadMethodArgumentResolver` receives the converted Java payload, checks for `@Valid`/`@Validated`, and invokes the configured Validator.

If violations exist, Spring Messaging typically throws:

```text
org.springframework.messaging.handler.annotation.support
    .MethodArgumentNotValidException
```

The error may be wrapped by the listener adapter/container in an outer exception; when classifying errors, inspect the **root cause** and framework version rather than only matching the outermost exception class.

### 4.1. Do Not Confuse with Spring MVC Validation

In MVC, many applications are used to controllers like:

```java
@PostMapping("/orders")
public void create(@Valid @RequestBody OrderCommand command) { ... }
```

That mechanism handles **HTTP requests**. `@JmsListener` does not go through MVC argument resolvers, does not use `@RequestBody`, and does not automatically return HTTP 400. JMS validation requires listener method adapter infrastructure and its own error handling.

Specifically, having a global Spring MVC/Boot Validator for web **is not proof** that the listener adapter is using that Validator. Spring Framework lets you explicitly configure `DefaultMessageHandlerMethodFactory#setValidator(...)`, shown in the next section.

### 4.2. Errors Occur at Different Layers

| Layer | Example error | Business handler invoked? |
| --- | --- | --- |
| JMS transport/broker | Queue missing, insufficient permissions, lost connection | No |
| JMS/JSON conversion | Malformed JSON, invalid `_type`, unconvertible field type | No |
| Argument resolution | Unable to resolve payload/missing required content | No |
| Bean Validation | `orderId=""`, `quantity=0`, `shipping.city=""` | No, once Validator is configured |
| Business rule | `orderId` already processed, locked customer, quantity exceeds current stock | May be invoked, then rejected by business code |
| Database/integration | DB timeout, downstream unavailable | Handler entered, fails later |

**Do not equate successful JSON parsing with successful Bean Validation; and do not equate successful Bean Validation with a valid business decision.**

## 5. Wiring a Validator into the JMS Listener Method Adapter

Transparent configuration per the Spring Framework reference:

1. Have a Bean Validation provider on the classpath.
2. Have an `org.springframework.validation.Validator` bean (e.g., `LocalValidatorFactoryBean`).
3. Create `DefaultMessageHandlerMethodFactory` and call `setValidator(validator)`.
4. Configure `JmsListenerConfigurer` to supply that factory via `JmsListenerEndpointRegistrar`.

Example **illustrative configuration snippet**:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.JmsListenerConfigurer;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.messaging.handler.annotation.support
        .DefaultMessageHandlerMethodFactory;
import org.springframework.validation.Validator;

@Configuration
public class JmsValidationConfig implements JmsListenerConfigurer {
    private final Validator validator;

    public JmsValidationConfig(Validator validator) {
        this.validator = validator;
    }

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {
        DefaultMessageHandlerMethodFactory methodFactory =
                new DefaultMessageHandlerMethodFactory();
        methodFactory.setValidator(validator);
        registrar.setMessageHandlerMethodFactory(methodFactory);
    }
}
```

**Important lifecycle note:** the snippet above only illustrates the idea; `DefaultMessageHandlerMethodFactory` actually implements `InitializingBean`, so you should **register it as a Spring bean so the framework calls `afterPropertiesSet()`**, or initialize its lifecycle properly before use. The complete project in section 8 uses a dedicated `DefaultMessageHandlerMethodFactory` bean to avoid accidentally skipping argument resolver setup.

### 5.1. Two Validator Interfaces

**Jakarta Validation `jakarta.validation.Validator`:**

```java
Set<ConstraintViolation<OrderCommand>> violations =
        jakartaValidator.validate(order);
```

Returns a set of violations so code can proactively decide how to handle them. Suitable for manual validation outside the listener argument resolver when filtered error lists are needed.

**Spring `org.springframework.validation.Validator`:**

```java
@Override
public boolean supports(Class<?> candidate) { ... }

@Override
public void validate(Object target, Errors errors) { ... }
```

This is the API required by `DefaultMessageHandlerMethodFactory#setValidator(...)`. `LocalValidatorFactoryBean` implements both interfaces, bridging Jakarta constraints with Spring's error API (`Errors`, `BindingResult`).

**Do not mistakenly inject** `jakarta.validation.Validator` and pass it directly to a method expecting `org.springframework.validation.Validator`: they are not the same interface. Inject `LocalValidatorFactoryBean` or an appropriate Spring Validator bean.

### 5.2. Creating a Custom Spring Validator for Specialized Rules

A custom Validator can check rules not available in Jakarta constraints:

```java
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

final class OrderPolicyValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return OrderCommand.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        OrderCommand command = (OrderCommand) target;
        if (command.quantity() != null && command.quantity() > 100) {
            errors.rejectValue(
                    "quantity", "order.quantity.tooLargeForChannel",
                    "Quantity exceeds channel limit");
        }
    }
}
```

This is an illustrative class snippet with `OrderCommand` in the same package. If you replace the handler's validator with **only** the custom class above, `@NotBlank`, `@Min`, and nested `@Valid` constraints **will not run automatically** through it. To combine Jakarta constraints and custom logic, use a properly delegating/composite validator, or place business rules in a service after Bean Validation.

For dynamic rules depending on databases, inventory, customer limits, or permissions, placing them in a **business service** is usually cleaner because boundary validation should stay deterministic without issuing batches of network/DB queries.

## 6. @Validated and Validation Groups

`@Valid` does not select groups; it normally validates the `Default` group. If one DTO is shared across two contexts with different constraints, Spring supports `@Validated(Group.class)` with custom validation groups.

Example (illustrative snippet):

```java
interface CreateOrder {}
interface UpdateOrder {}

record OrderPatch(
        @NotNull(groups = UpdateOrder.class) String orderId,
        @NotNull(groups = CreateOrder.class) Integer quantity
) {}
```

A listener method can request a group:

```java
@JmsListener(destination = "orders.create")
public void create(@Payload @Validated(CreateOrder.class)
                   OrderPatch patch) {
    // ...
}
```

Condition: the Validator used in `DefaultMessageHandlerMethodFactory` understands validation hints/groups (e.g., `LocalValidatorFactoryBean`). When groups are specified, constraints belonging only to `Default` will **not execute automatically** unless you include `Default` or configure a group sequence; design groups carefully.

**Reusing one DTO for every command type is rarely a good solution.** If `CreateOrder` and `UpdateOrder` have noticeably different schemas, two separate DTO contracts are usually simpler than overlapping validation groups.

## 7. Nested Validation, Collections, and Limits

For nested objects, `@Valid` triggers cascading validation:

```java
record BatchCommand(
        @NotNull String batchId,
        @NotEmpty java.util.List<@Valid OrderCommand> orders
) {}
```

This is an illustrative snippet requiring Bean Validation annotation imports. `@NotEmpty` checks that the list is non-empty; `@Valid` on the type argument requests validating each `OrderCommand` in the list via Bean Validation container element support.

However, the validator does not limit raw JSON payload size or nesting depth before deserialization. If a message contains ten million elements, deserialization can exhaust memory **before** `@Size(max=...)` ever runs. For untrusted data, ensure:

- Message size limits at the broker/producer and deserializer layer.
- `@Size(max=...)` on parsed collections, without treating it as the sole line of defense.
- Bounds on string length, item count, numeric ranges, and nesting depth.
- Avoiding arbitrary class deserialization from a sender-controlled `_type`; use stable type IDs and allowlisted type mappings/trusted packages.
- Monitoring decode latency, memory usage, and errors by event type/schema version.

### 7.1. Collections Can Contain Nulls

`List<@Valid OrderCommand>` does not forbid null elements by itself. To disallow null elements, you can write:

```java
List<@NotNull @Valid OrderCommand> orders
```

with a Bean Validation provider supporting container element constraints. For nested DTOs, `@Valid` does not replace `@NotNull`, just like `shipping` earlier.

## 8. Runnable Project: Spring Boot 3.5.7 + Java 17+ + Artemis + Bean Validation

This demo shows:

- Producer uses `JmsTemplate.convertAndSend` to send `OrderCommand` as JSON in a `TextMessage`.
- Spring's `MappingJackson2MessageConverter` converts JSON into `OrderCommand` on the consumer.
- `JmsListenerConfigurer` registers a **real Spring `Validator`** with `DefaultMessageHandlerMethodFactory`.
- `@JmsListener` invokes `receive(@Payload @Valid OrderCommand command)`.
- The handler records a valid payload in a tracker; the runner waits up to 10 seconds and prints a deterministic line.
- A separate broker-free test demonstrates an invalid payload being blocked **before the Java handler method is invoked**.

### 8.1. Environment Requirements

- JDK 17+ and Maven 3.9+.
- Docker to run Apache ActiveMQ Artemis at localhost port `61616`.
- Ability to download Maven dependencies and the Docker image.
- No other application consuming queue `demo.validation.orders` on the same lab broker.

The credentials below are for **local practice only**; never use them in production.

### 8.2. Starting Artemis

```bash
docker run --rm -d --name jms-validation-broker \
  -p 127.0.0.1:61616:61616 \
  -e ARTEMIS_USER=artemis \
  -e ARTEMIS_PASSWORD=artemis \
  apache/artemis:latest-alpine

docker logs jms-validation-broker
```

Wait for the broker to be ready. The demo broker normally enables queue auto-creation per image defaults; in environments without auto-create, provision the queue/address and grant permissions. Running on the host connects to `tcp://localhost:61616`; if the app runs in another container, use the appropriate hostname/network.

### 8.3. Project Structure

```text
jms-payload-validation/
├── pom.xml
└── src/
    ├── main/
    │   ├── resources/application.properties
    │   └── java/com/example/jms/
    │       ├── ValidationApplication.java
    │       ├── OrderCommand.java
    │       ├── ValidatedOrderListener.java
    │       ├── ReceiptTracker.java
    │       └── JmsListenerValidationConfigurer.java
    └── test/
        └── java/com/example/jms/
            └── ValidationResolutionTest.java
```

### 8.4. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>jms-payload-validation</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-json</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Each starter has a dedicated role:

- Artemis starter: JMS API, Spring JMS, Artemis client/connection.
- JSON starter: Jackson and `ObjectMapper`.
- Validation starter: Jakarta Validation API and Hibernate Validator implementing constraints.
- Test starter: JUnit 5, Spring Test, and common test libraries.

Do not lump all logic into `@Valid`: the converter only decodes; Validator enforces constraints; the service decides business semantics.

### 8.5. `src/main/resources/application.properties`

```properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
```

This is a lab configuration without TLS and using demo passwords. For real deployments, use environment variables or a secret manager, TLS, and destination-level ACLs; never commit production credentials to source control.

### 8.6. `OrderCommand.java` — DTO with Declared Constraints

```java
package com.example.jms;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record OrderCommand(
        @NotBlank @Size(max = 64) String orderId,
        @NotNull @Min(1) @Max(500) Integer quantity,
        @NotNull @Valid ShippingAddress shipping
) {
    public record ShippingAddress(
            @NotBlank @Size(max = 100) String city,
            @NotBlank @Pattern(regexp = "[A-Z]{2}") String countryCode
    ) {}
}
```

This is a **transport DTO**, not a JPA entity. Nested `@Valid` is crucial: it requires validating both `city` and `countryCode`.

### 8.7. `ValidationApplication.java` — Jackson JMS Converter Config and Runner

```java
package com.example.jms;

import java.util.Map;
import java.util.concurrent.TimeUnit;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageConverter;
import org.springframework.jms.support.converter.MessageType;
import org.springframework.messaging.handler.annotation.support
        .DefaultMessageHandlerMethodFactory;
import org.springframework.validation.Validator;

@SpringBootApplication
@EnableJms
public class ValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationApplication.class, args);
    }

    @Bean
    MessageConverter jsonJmsMessageConverter(ObjectMapper objectMapper) {
        MappingJackson2MessageConverter converter =
                new MappingJackson2MessageConverter();
        converter.setObjectMapper(objectMapper);
        converter.setTargetType(MessageType.TEXT);
        converter.setTypeIdPropertyName("_type");
        converter.setTypeIdMappings(Map.of(
                "order.command.v1", OrderCommand.class));
        return converter;
    }

    @Bean
    DefaultMessageHandlerMethodFactory jmsHandlerMethodFactory(
            Validator validator) {
        DefaultMessageHandlerMethodFactory factory =
                new DefaultMessageHandlerMethodFactory();
        factory.setValidator(validator);
        return factory;
    }

    @Bean
    CommandLineRunner runDemo(JmsTemplate template,
                              ReceiptTracker tracker) {
        return args -> {
            OrderCommand command = new OrderCommand(
                    "order-42",
                    2,
                    new OrderCommand.ShippingAddress("Ha Noi", "VN")
            );

            template.convertAndSend("demo.validation.orders", command);

            if (!tracker.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timeout waiting for a validated order");
            }

            System.out.println("Accepted payload: " + tracker.result());
        };
    }
}
```

**Explanation:**

1. `MappingJackson2MessageConverter` converts `OrderCommand` to a JSON `TextMessage` and vice versa.
2. `_type` is a **JMS property** holding the stable alias `order.command.v1`; the mapping resolves the alias to `OrderCommand.class`. Without type ID mappings, the converter may emit the raw Java class name, coupling the wire format to internal classes.
3. Spring Boot wires the `MessageConverter` bean into `JmsTemplate` and the default JMS listener container factory in standard auto-configuration.
4. The `DefaultMessageHandlerMethodFactory` bean is initialized by Spring (`InitializingBean`) and then passed to the registrar by `JmsListenerConfigurer` below. `setValidator(validator)` enables validation in the payload argument resolver.
5. The runner sends only a **valid** message so the demo does not enter a poison-message redelivery loop. It waits up to 10 seconds on the tracker and prints the output.
6. There are no DB calls; this is an example of data validation at the listener boundary, not production order processing.

### 8.8. `JmsListenerValidationConfigurer.java` — Wiring the Handler Method Factory

```java
package com.example.jms;

import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.JmsListenerConfigurer;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.messaging.handler.annotation.support
        .DefaultMessageHandlerMethodFactory;

@Configuration
public class JmsListenerValidationConfigurer
        implements JmsListenerConfigurer {

    private final DefaultMessageHandlerMethodFactory methodFactory;

    public JmsListenerValidationConfigurer(
            DefaultMessageHandlerMethodFactory methodFactory) {
        this.methodFactory = methodFactory;
    }

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {
        registrar.setMessageHandlerMethodFactory(methodFactory);
    }
}
```

Note: this is the **factory for resolving `@JmsListener` method parameters**, which is **distinct from** `DefaultJmsListenerContainerFactory` that manages connections/sessions/ack/retries. If you only configure `MessageConverter` without supplying `Validator` to the method factory when validation is needed, `@Valid` may not reject invalid data as expected.

### 8.9. `ValidatedOrderListener.java` — Validating Before Processing

```java
package com.example.jms;

import jakarta.validation.Valid;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

@Component
public class ValidatedOrderListener {

    private final ReceiptTracker tracker;

    public ValidatedOrderListener(ReceiptTracker tracker) {
        this.tracker = tracker;
    }

    @JmsListener(
            id = "validated-orders",
            destination = "demo.validation.orders"
    )
    public void accept(@Payload @Valid OrderCommand command) {
        // Runs only if the argument was converted and Bean Validation passed.
        tracker.accepted(command.orderId(), command.quantity());
    }
}
```

If a payload has `quantity=0`, Bean Validation produces a `quantity` violation and the argument resolver throws before invoking `accept` (when the factory/validator is properly configured). If the JSON is malformed, a conversion error occurs **earlier** and is not counted as a `@Min` violation.

### 8.10. `ReceiptTracker.java` — Thread-Safe Demo Result Holder

```java
package com.example.jms;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.stereotype.Component;

@Component
public final class ReceiptTracker {

    private final AtomicReference<String> result =
            new AtomicReference<>();
    private final CountDownLatch latch = new CountDownLatch(1);

    public void accepted(String orderId, int quantity) {
        result.set(orderId + " x " + quantity);
        latch.countDown();
    }

    public boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return latch.await(timeout, unit);
    }

    public String result() {
        return result.get();
    }
}
```

Uses `AtomicReference` and `CountDownLatch` so the listener thread safely publishes the result to the runner thread. The demo uses one message. In real systems, never use a single latch for all requests or replace a DB/outbox with an in-memory tracker.

### 8.11. Running and Expected Stdout

From the project directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

Once Artemis is ready, the queue is created, and the listener receives the valid message within 10 seconds, the program prints the business line:

```text
Accepted payload: order-42 x 2
```

Other Spring/Artemis startup logs appear on stdout. Because the runner waits on `CountDownLatch`, the line above only appears after the listener marks the message valid. It does not depend on listener thread scheduling order.

Stop the broker after practicing:

```bash
docker stop jms-validation-broker
```

**Demo limitations:** sends only a valid payload; no JDBC, DLQ/retry policy, TLS, secret manager, production metrics, or idempotent database handler. The next section provides a unit test for invalid payloads without sending poison messages into the broker.

## 9. Unit Test: Proving Both Constraints and @Valid in the Argument Resolver

A broker-free test can verify **two layers**:

1. Jakarta Validator detects all constraint violations, including nested `shipping`.
2. `DefaultMessageHandlerMethodFactory` using that Validator makes `@Payload @Valid` **block method invocation** for invalid payloads.

This is stronger than simply calling `validator.validate(dto)` and mistakenly assuming Spring wired the Validator into the listener.

### 9.1. `src/test/java/com/example/jms/ValidationResolutionTest.java`

```java
package com.example.jms;

import java.lang.reflect.Method;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.handler.annotation.support
        .DefaultMessageHandlerMethodFactory;
import org.springframework.messaging.handler.annotation.support
        .MethodArgumentNotValidException;
import org.springframework.messaging.handler.invocation.InvocableHandlerMethod;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ValidationResolutionTest {

    @Test
    void invalidNestedPayloadIsRejectedBeforeHandlerRuns()
            throws Exception {
        LocalValidatorFactoryBean validator =
                new LocalValidatorFactoryBean();
        validator.afterPropertiesSet();

        try {
            OrderCommand invalid = new OrderCommand(
                    "",
                    0,
                    new OrderCommand.ShippingAddress("", "vn")
            );

            Set<String> invalidPaths = validator.validate(invalid)
                    .stream()
                    .map(v -> v.getPropertyPath().toString())
                    .collect(Collectors.toSet());

            assertEquals(Set.of(
                    "orderId",
                    "quantity",
                    "shipping.city",
                    "shipping.countryCode"
            ), invalidPaths);

            DefaultMessageHandlerMethodFactory factory =
                    new DefaultMessageHandlerMethodFactory();
            factory.setValidator(validator);
            factory.afterPropertiesSet();

            ReceiptTracker tracker = new ReceiptTracker();
            ValidatedOrderListener handler =
                    new ValidatedOrderListener(tracker);

            Method method = ValidatedOrderListener.class
                    .getMethod("accept", OrderCommand.class);
            InvocableHandlerMethod invocable =
                    factory.createInvocableHandlerMethod(handler, method);

            var message = MessageBuilder.withPayload(invalid).build();

            assertThrows(
                    MethodArgumentNotValidException.class,
                    () -> invocable.invoke(message)
            );
            assertNull(tracker.result());
        } finally {
            validator.destroy();
        }
    }
}
```

Run command:

```bash
mvn test
```

Expected outcome: the test **passes** when Hibernate Validator/JUnit/Spring dependencies are present and the code compiles. The violated fields consist of exactly four paths:

```text
orderId
quantity
shipping.city
shipping.countryCode
```

`Set` is **unordered**, so the test compares two sets rather than asserting error message order. `tracker.result()==null` confirms the handler was not invoked through the test's argument resolver path.

**Verification boundary:** the test does not start a JMS listener container or connect to Artemis. It proves the method resolver config and DTO constraints; broker integration tests must be added to verify JMS conversion, transaction/ack/rollback, and DLQ behavior matching production.

### 9.2. Extended Exercises

Learners can add tests for:

- `OrderCommand("order-42", 2, ShippingAddress("Ha Noi", "VN"))` → empty violations.
- `OrderCommand(null, 2, ...)` → `orderId` error.
- `OrderCommand("order-42", null, ...)` → `quantity` `@NotNull` error.
- `OrderCommand("order-42", 2, null)` → `shipping` `@NotNull` error.
- `OrderCommand("order-42", 501, ...)` → `quantity` `@Max` error.
- `countryCode="vn"` → `shipping.countryCode` pattern error.
- JSON `quantity:"two"` → **deserialization/conversion** error before Bean Validation.
- `_type` not in allowed type mappings → conversion/type resolution error.

Do not depend on **error ordering** or fixed English messages since providers/locales can change.

## 10. Manual Validation with Validator When Not Using @Payload @Valid

Not every consumer uses annotation-driven argument resolution. For example, a raw `jakarta.jms.TextMessage` handler that parses JSON manually, or logic receiving from another event system, may need to call Jakarta Validator directly:

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import java.util.Set;

// Snippet inside a service with an injected Validator:
Set<ConstraintViolation<OrderCommand>> violations =
        jakartaValidator.validate(command);

if (!violations.isEmpty()) {
    // Log with sensitive data stripped; decide reject/quarantine.
    throw new IllegalArgumentException(
            "Invalid command fields: " + violations.size()
    );
}
```

With manual validation, **your code** must decide how to report errors, map paths, and handle retry/DLQ; the framework will not infer operational rules automatically.

### 10.1. Avoid Redundant Duplicate Manual Validation

If `@Payload @Valid` is already properly configured, avoid calling `validator.validate(command)` again on the first line of the listener just to obtain the same errors. Only invoke it manually when:

- Different groups are needed based on `eventType`/`version`.
- Another intermediate object needs validation after mapping.
- Cross-field rules not expressed as constraints need checking.
- Processing raw data/paths outside `@JmsListener`.

For business validation requiring DB queries, separate it into a clear service for easier transactions/retries and unit testing.

## 11. What Does a Validation Failure Make the Broker Do?

**This is the most commonly misunderstood part.** A validation failure throws an exception in the listener method adapter, but whether the broker **ACKs, rolls back, redelivers, or moves to DLQ** depends on the container, session/transaction, provider, and broker policy; `@Valid` **does not mean messages are automatically sent to DLQ**.

### 11.1. When the Listener Uses a Transacted JMS Session

With `DefaultMessageListenerContainer` or a factory configured with `sessionTransacted=true`, if an exception reaches the container, that delivery is normally rolled back; the broker may **redeliver the message** per its redelivery policy.

```text
Receive invalid payload
      |
      v
Conversion / @Valid fails
      |
      v
Container sees exception
      |
      +--> rollback transacted Session
      |
      +--> broker redelivery policy
               |
               +--> bounded retry -> still failing -> DLQ/quarantine
               +--> unbounded retry -> poison message loop
```

**`@Valid` does not make a message vanish safely.** A message with `quantity=0` does not fix itself simply by being redelivered 10 ms later. Rolling back forever without a max-delivery-attempts/DLQ policy can create a loop, clog the queue, or burn CPU/logs.

Separate **permanent** errors (malformed JSON, unsupported schema, unrecoverable constraint violations) from **transient** errors (temporary broker/DB/network outages). Design bounded retries, dead-letter addresses/queues, alerts, and controlled replay tools.

### 11.2. AUTO_ACKNOWLEDGE Is Not a Guarantee of "Errors Always Retry"

With JMS `AUTO_ACKNOWLEDGE`, acknowledgment depends on the container type/receive path and when the provider acknowledges. Do not rely on the assumption that every parse/validation exception returns the message to the queue. Spring Framework recommends transacted sessions when reliability is required. In Spring Boot, the default factory may enable `sessionTransacted` via auto-config; if you replace it with a custom factory, verify the **actual** configuration.

Example configuring a factory for a reliable listener:

```java
// Optional snippet, not part of the demo project in section 8.
@Bean("validatedTransactedFactory")
DefaultJmsListenerContainerFactory validatedFactory(
        ConnectionFactory connectionFactory,
        DefaultJmsListenerContainerFactoryConfigurer configurer) {
    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();
    configurer.configure(
            factory, ConnectionFactoryUnwrapper.unwrapCaching(
                    connectionFactory));
    factory.setSessionTransacted(true);
    return factory;
}
```

The snippet above requires imports from `jakarta.jms.ConnectionFactory`, Spring JMS, and Spring Boot's JMS configurer/unwrapper, plus an appropriate bean context. If named `validatedTransactedFactory`, set `containerFactory="validatedTransactedFactory"` on the corresponding `@JmsListener`.

### 11.3. Handling Invalid Payloads in Production

Common options:

- **Controlled rejection:** throw a classified error so the broker moves the message to DLQ after bounded delivery attempts.
- **Dedicated quarantine:** move the message to an error destination with error code/schema version metadata and ACK the original message **in a consistent transaction**.
- **Audit errors without logging PII:** record eventId/JMSMessageID/constraint path without exposing the full body or stack traces containing secrets.
- **Replay after fixing:** only replay messages after fixing the upstream payload/schema, matching versions, and ensuring idempotency.
- **Rate-based alerts:** a spike in `MethodArgumentNotValidException` may indicate an incompatible producer deployment.

Do not expect the `@JmsListener` method to **catch and swallow the exception** when validation actually happens **before the method is invoked**. To intercept such errors, configure a container `ErrorHandler`, error channel/interceptor, or appropriate broker DLQ mechanisms depending on the stack. Never expect a `try/catch` *inside the method* to catch argument resolver exceptions thrown before the method runs.

## 12. @Valid Alone Is Not Enough for Schema and Business Rules

### 12.1. Contract/Schema Verification

`@Valid` on a DTO validates many field rules, yet does not necessarily distinguish:

- Misspelled field names if Jackson ignores unknown properties.
- JSON containing extra contract-violating properties while still parsing into the object.
- Producer with `schemaVersion=2` sending to a v1 consumer whose converter silently drops new fields.
- Wrong Content-Type, missing `_type`, or spoofed type-ids.
- Missing `JMSCorrelationID`, `eventId`, or `schemaVersion` headers/properties outside the DTO.
- JSON nesting/body size limits prior to deserialization.

Add schema validation, allowed type mappings, contract version checks, broker ACLs, message size caps, and header checks. DTOs should contain only necessary public fields; never deserialize JPA entities or arbitrary classes from `_type`.

### 12.2. Business Validation Requiring Transactions/Idempotency

Suppose `quantity=2` and `orderId="order-42"` pass Bean Validation, yet the order was already processed or inventory only has 1 unit left. That is business validation: it belongs in a service with access to data stores, transaction boundaries, and idempotency policies.

```text
DTO constraints pass
       |
       v
BusinessService:
  verify idempotency/businessCommandId
  verify current inventory/state
  update database transaction
  publish result/outbox if required
```

`@Min(1)` cannot be turned into an actual inventory check. If it fails due to business state that will not change on retry, reject it; if it fails transiently due to a DB outage, apply bounded retries. `@Valid` alone does not guarantee exactly-once processing.

### 12.3. Cross-Field Constraints

Some rules depend on **multiple fields** (e.g., `deliveryDate >= orderDate`, or `currency` matching `amount`). You can build a custom Jakarta Bean Validation annotation/`ConstraintValidator` for class-level constraints. When validation groups and metadata become complex, emit stable error codes and test each branch.

Do not abuse validators as a workflow engine: custom constraints with side effects (DB writes/HTTP calls) easily cause unexpected retries since Bean Validation may be invoked multiple times from different places.

## 13. Thread Safety, Performance, and Security

### 13.1. Validator and Listener Concurrency

`@JmsListener` often runs inside a concurrent container. A singleton listener can be invoked concurrently. Bean Validation providers design `Validator` to be reusable and thread-safe after initialization, whereas **business handler mutable state** must be managed explicitly.

- Do not store "current message" state in a listener field.
- Do not use an unsynchronized `int` counter on a singleton.
- Do not create a new `ValidatorFactory` for **every message**: initializing provider/metadata is expensive, so manage it via Spring's lifecycle.
- Do not cache `ConstraintViolation` instances holding validated objects across messages.
- Review custom `ConstraintValidator` implementations if they use mutable state/shared resources.

### 13.2. Error Messages May Contain Sensitive Data

When validation fails, `ConstraintViolation#getInvalidValue()` may contain sensitive payload values. Do not print full violations, raw JSON, customer addresses, or credentials into default logs. Log instead:

```text
event=payload_rejected
destination=demo.validation.orders
errorCode=ORDER_VALIDATION_FAILED
fields=orderId,quantity
schemaVersion=1
```

If correlation between producer and consumer is needed, use appropriate event/correlation IDs while avoiding personal data IDs in metric labels (cardinality). Broker ACLs and TLS are separate layers; validation does not replace authentication/authorization.

### 13.3. Resource Limits

Validating a small DTO is usually cheap, but can become expensive if:

- The payload contains a huge list of hundreds of thousands of items.
- A custom validator queries a DB/external service per field.
- A regex constraint triggers catastrophic backtracking on long input strings.
- The message decoder builds a massive object graph before validation.

Design limits, batching, deadlines, backpressure, concurrency, and monitoring before scaling up listeners. For untrusted inputs, enforce limits at the broker/deserializer before invoking Bean Validation.

## 14. Comparison Table: @Valid, Validator, and Business Validation

| Mechanism | Trigger | Best suited for | Limitations |
| --- | --- | --- | --- |
| `@Valid` on `@Payload` | Argument resolver + configured Validator | Constraints on DTO and nested objects | Does not decode JSON, does not check DB state |
| `@Validated(Group.class)` | Spring validation hints/groups | Context-dependent rules | Can accidentally skip the `Default` group |
| Jakarta `Validator#validate` | Manually called by code | DTOs at any layer | Code must handle violations/errors manually |
| Spring `Validator#validate(target, errors)` | Called by code or handler factory | Custom validation via `Errors` | Does not run Jakarta constraints unless custom validator delegates |
| JSON Schema/contract validator | Protocol boundary/decoder | Required/unknown fields, types, schema versions | Does not replace business invariants |
| Business service validation | Transaction and domain layer | Inventory, permissions, current state, idempotency | Has side effects/IO; needs retry/transaction strategy |
| JMS broker ACL/transport policy | Broker/configuration | Auth, destination rights, delivery settings | Unaware of business DTOs |

Draw a clear boundary: **decode** → **contract/Bean Validation** → **business validation** → **commit/ack**.

## 15. Common Mistakes and Resolutions

| Error | Symptom | Resolution |
| --- | --- | --- |
| Using `javax.validation.Valid` with Boot 3 | Jakarta incompatibility/compile error | Use `jakarta.validation.Valid` |
| Missing validation provider | Constraints inactive, provider initialization error | Add `spring-boot-starter-validation` |
| Have `@Valid` but no Validator set on handler factory | Invalid DTO still reaches handler or is not validated as expected | Use `JmsListenerConfigurer` + `DefaultMessageHandlerMethodFactory#setValidator` |
| `DefaultMessageHandlerMethodFactory` not initialized per lifecycle | Argument resolvers not set up | Declare as a bean/ensure `afterPropertiesSet()` |
| Only `@Valid` with no constraints | Invalid data goes undetected | Add proper `@NotBlank`, `@Min`, etc. |
| Missing `@Valid` on nested field | `shipping.city=""` goes unchecked | Use `@NotNull @Valid` on nested objects |
| Only `@Valid` without `@NotNull` | Null nested object triggers no error | Add `@NotNull` |
| Using `@NotNull` on required String | Empty/whitespace strings still pass | Use `@NotBlank` |
| Using `int` on required field | Missing field becomes 0 | Use `Integer` + `@NotNull` and schema |
| JSON DTO lacks a matching `MessageConverter` | Conversion error before validation | Configure JSON converter/target type/type ID |
| Jackson type ID is Java FQCN | Producer refactoring breaks compatibility | Use stable aliases + allowlisted mapping |
| Validator enabled only in MVC | JMS listener has separate configuration | Check the JMS method factory |
| Using `@Validated(Group)` and forgetting `Default` | Some constraints do not run | Specify groups/group sequences explicitly |
| Catching validation errors inside `@JmsListener` method | Method was never called; cannot catch | Configure container error handling/DLQ |
| Auto-retrying invalid messages forever | Poison-message loop, log spam | Bounded retries, DLQ/quarantine |
| Treating `@Valid` as broker ACL/security | Spoofed input still reaches queue | TLS/auth/ACLs and schema validation |
| Logging full `getInvalidValue()` | Leaks PII/secrets | Log sanitized field paths and error codes |
| Using `@Valid` instead of inventory checks | DTO passes yet business state is invalid | Validate in the domain service |
| Creating a `ValidatorFactory` per message | High CPU/memory overhead | Use a Spring-managed bean |
| Mixing JS/JSON type coercion | Numbers/strings violate strict schema | Schema validation + controlled converter |

### 15.1. How to Debug When @Valid Does Not Run

1. Verify the message **actually reaches** the scanned bean's listener method.
2. Verify Spring Boot/Spring Framework versions use the Jakarta namespace.
3. Check the validation provider dependency and `org.springframework.validation.Validator` bean.
4. Verify `JmsListenerConfigurer` is scanned by Spring and `setMessageHandlerMethodFactory(...)` executes.
5. Verify the factory has `setValidator(validator)` and was initialized properly.
6. Verify the signature uses `@Payload @Valid OrderCommand`, not just raw `TextMessage`.
7. Verify the DTO has constraints and nested `@Valid`.
8. Send a valid payload first; then test invalid payloads **in a unit/integration environment with a DLQ policy** to avoid poisoning a production broker.
9. Inspect the exception's root cause: `MessageConversionException` differs from `MethodArgumentNotValidException`.
10. Check listener container transactions, broker redelivery attempts, and DLQ.

### 15.2. When Deserialization Fails Without a Violation

Example JSON:

```json
{"orderId":"order-42","quantity":"not-a-number","shipping":{"city":"Ha Noi","countryCode":"VN"}}
```

If Jackson cannot convert `"not-a-number"` into `Integer`, it throws an error **before** Bean Validation. Handle this via contract/schema converter error handling; do not expect `@Min` to report an error. If you want to reject numeric strings instead of allowing coercion, configure Jackson coercion/schema policies explicitly, as behavior varies across versions and configurations.

## 16. Production Deployment Checklist

- [ ] Proper Spring/Jakarta `Validator` bean and Bean Validation provider present.
- [ ] `@JmsListener` receives `@Payload @Valid` with the right DTO type.
- [ ] `DefaultMessageHandlerMethodFactory` is registered with `setValidator(...)`.
- [ ] `MessageConverter` properly decodes the JMS body, type ID, and JSON schema version.
- [ ] DTO has required/length/range/format constraints, nested `@Valid`, and `@NotNull`.
- [ ] Nullable/absent/empty/default fields are defined in the contract.
- [ ] If using `@Validated`, group composition is accurate and tested.
- [ ] Conversion failures are separated from validation failures and business errors.
- [ ] Arbitrary Java classes are never deserialized from producer-controlled type IDs.
- [ ] Raw entities/JPA proxies are never sent as public payloads.
- [ ] Max message size/nesting/collection limits and security checks are enforced.
- [ ] Container transaction/ack/recovery config is tested against a real broker.
- [ ] Permanently invalid messages go to DLQ/quarantine with bounded redelivery and alerts.
- [ ] Business side effects are idempotent; validation is not confused with exactly-once.
- [ ] Unit tests cover constraints + resolver; integration tests with Artemis cover converter/ACK/DLQ.
- [ ] Logs contain only filtered error codes/paths without exposing bodies/PII/secrets.
- [ ] Validation latency, error rates, queue backlog, DLQ, and throughput are monitored.

## 17. Review Questions

**1. Does `@Valid` automatically parse JSON into a Java DTO?**  
No. JMS `MessageConverter` performs conversion; `@Valid` triggers validation on the converted DTO.

**2. Why must `spring-boot-starter-validation` be installed?**  
To provide a Jakarta Validation provider that executes constraints rather than having only the annotation API.

**3. Why might `@Valid` in `@JmsListener` not run even when MVC validation works?**  
Because JMS uses its own handler method factory and argument resolvers. A Validator must be properly wired through `DefaultMessageHandlerMethodFactory`.

**4. If `shipping` is missing yet declared as `@Valid ShippingAddress shipping`, is there an error?**  
Not automatically. `@Valid` does not cascade into null; use `@NotNull @Valid`.

**5. How do `@NotBlank` and `@NotNull` differ?**  
`@NotNull` only rejects null; `@NotBlank` also rejects empty or whitespace-only strings.

**6. What kind of error is JSON `quantity="abc"`?**  
Typically a conversion/deserialization error before validation, not a `@Min` violation.

**7. What exception typically occurs when constraints on `@Payload` fail?**  
`MethodArgumentNotValidException` in Spring Messaging, which may be wrapped in listener invocation exceptions.

**8. Are Spring Validator and Jakarta Validator the same interface?**  
No. `LocalValidatorFactoryBean` can bridge between the two APIs.

**9. When is `@Validated` useful?**  
When validation groups like Create/Update are needed. Select groups carefully; arbitrary use can accidentally skip the `Default` group.

**10. If a message failing a constraint is retried many times, will it become valid on its own?**  
No. Permanent validation failures normally require DLQ/quarantine instead of infinite retries.

**11. Does `@Valid` guarantee exactly-once processing or zero message loss?**  
No. Those are responsibilities of transactions, acknowledgment, broker redelivery, idempotency, and operational policies.

**12. Do validator unit tests replace Artemis integration tests?**  
No. Unit tests verify constraints/argument resolvers; broker tests are needed to verify real JSON conversion, delivery, transactions, and DLQs.

## 18. Official References

1. [Spring Framework 6.2 — Annotation-driven JMS Listener Endpoints: @Valid and DefaultMessageHandlerMethodFactory](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html)
2. [Spring Framework 6.2 — DefaultMessageHandlerMethodFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/messaging/handler/annotation/support/DefaultMessageHandlerMethodFactory.html)
3. [Spring Framework 6.2 — PayloadMethodArgumentResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/messaging/handler/annotation/support/PayloadMethodArgumentResolver.html)
4. [Spring Framework 6.2 — MethodArgumentNotValidException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/messaging/handler/annotation/support/MethodArgumentNotValidException.html)
5. [Spring Framework — LocalValidatorFactoryBean Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
6. [Spring Boot 3.5 — JMS and Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html)
7. [Spring Boot 3.5 — Validation](https://docs.spring.io/spring-boot/3.5/reference/io/validation.html)
8. [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/)
9. [Jakarta Bean Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/)
10. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
11. [Apache ActiveMQ Artemis — Docker](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)