# Filtering Null Events and Invalid Data

Spring application events have multiple layers of filtering. Spring checks events at the publish boundary, the listener infrastructure filters by event type and source, and `@EventListener(condition = "...")` can filter by content using SpEL. These mechanisms decide which listeners are invoked; they do not replace validating business data before emitting an event.

Two cases must be clearly distinguished:

- **The event object is null:** Spring `ApplicationContext` rejects publishing immediately.
- **The event object is non-null, but the payload has null fields or invalid data:** Spring can still publish and deliver the event to matching listeners. The application must decide whether to validate, reject, or only filter listeners as needed.

A listener skipped by a `condition` does not mean the event is cancelled. Other listeners can still receive the same event. Therefore, data determining business validity must be checked at the boundary before publishing.

## 1. Distinguishing a Null Event from Nulls Inside a Payload

### Publishing a Null Event Object

In Spring Framework 6.2, `AbstractApplicationContext` checks the event parameter before creating a `PayloadApplicationEvent`. If the event is null, Spring throws `IllegalArgumentException` with the message `Event must not be null`.

~~~java
ApplicationEventPublisher publisher = context;

try {
    publisher.publishEvent((Object) null);
} catch (IllegalArgumentException ex) {
    System.out.println(ex.getMessage());
}
~~~

Casting to `Object` unambiguously selects the `publishEvent(Object)` overload. The rejection happens before the multicaster invokes any listener, so no listener receives a null event.

Do not use `null` as a business signal, such as `publishEvent(null)` to mean an order was cancelled or data was not found. Define explicit events such as `OrderCancelled` or `OrderNotFound`.

### Publishing a Payload Object with Null Fields

Spring Framework 4.2 and later allows publishing any object without requiring it to extend `ApplicationEvent`. Spring wraps the object in `PayloadApplicationEvent` for distribution.

For example, the following payload is non-null even though its internal fields are invalid:

~~~java
public record LegacyOrderPayload(String orderId, Integer amount) {
}

publisher.publishEvent(new LegacyOrderPayload(null, -10));
~~~

The publish call above is valid at the event infrastructure layer: the payload object is non-null. Spring does not automatically know that `orderId` must have a value or that `amount` must be positive. Without validation or filtering, matching listeners can still receive that payload.

`PayloadApplicationEvent` requires both `source` and `payload` to be non-null. When `ApplicationContext` automatically wraps a POJO, `source` is the context and `payload` is the published object. For custom events extending `ApplicationEvent`, the `source` passed to the constructor must also be non-null because `ApplicationEvent` extends `java.util.EventObject`.

### Comparison Table

| Case | Spring behavior | What the application needs to do |
|---|---|---|
| `publishEvent(null)` | Throws `IllegalArgumentException` before dispatch | Never use `null` as an event |
| `new ApplicationEvent(null)` | Constructor rejects null source | Provide a valid source |
| Publish non-null POJO with null fields | Publishes normally | Validate or filter according to business rules |
| Publish payload with negative amount | Does not automatically know negative amount is invalid | Check invariants before publishing |
| Listener SpEL `condition` returns false | Skips that listener method | Do not treat this as a global event rejection |

## 2. Filtering by Event Type

The most basic form of filtering is declaring the event type a listener cares about.

~~~java
public class OrderCreatedListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        // Only handle OrderCreatedEvent.
    }
}
~~~

Spring uses the generic `E` to identify matching listeners. A listener declaring `ApplicationListener<OrderCreatedEvent>` does not receive events of incompatible types. With `@EventListener`, the method parameter type also serves as an event type filter.

Example:

~~~java
@Component
public class OrderListeners {

    @EventListener
    public void onCreated(OrderCreatedEvent event) {
        // Only receives OrderCreatedEvent.
    }

    @EventListener
    public void onCancelled(OrderCancelledEvent event) {
        // Only receives OrderCancelledEvent.
    }
}
~~~

Type-based filtering is effective and clear because each listener only receives the group of events it handles. However, type filtering does not verify the fields inside the event. An `OrderCreatedEvent` with an empty `orderId` still has the exact type `OrderCreatedEvent`.

## 3. Runtime Filtering with @EventListener condition and SpEL

When multiple events share the same type but a listener only cares about certain conditions, use the `condition` attribute of `@EventListener`.

For example, only process orders with a valid ID and positive amount:

~~~java
@Component
public class ValidOrderListener {

    @EventListener(
        condition = "#a0.orderId != null and " +
                    "!#a0.orderId.isBlank() and " +
                    "#a0.amount != null and #a0.amount > 0")
    public void process(LegacyOrderPayload event) {
        // Only runs when the SpEL expression returns true.
    }
}
~~~

Spring evaluates `condition` in a dedicated evaluation context. Useful references:

| Expression | Meaning |
|---|---|
| `#root.event` or `event` | Actual `ApplicationEvent` |
| `#root.args` or `args` | Method argument array |
| `#root.args[0]` or `args[0]` | First parameter |
| `#a0` | First parameter by index |
| `#p0` | Another alias for the first parameter |
| `#paramName` | Parameter by name if bytecode retains name metadata |

Use `#a0` or `#p0` when you want to avoid depending on whether compilation retains parameter names. If using a name like `#event`, ensure parameter names are present in bytecode, e.g., by configuring the compiler with the `-parameters` option.

`condition` is considered true when the expression returns boolean `true` or one of the strings `true`, `on`, `yes`, `1`. An empty `condition` means the listener is always processed if the event type matches.

### Condition Is Not Validation

Suppose a publisher emits a payload with a null `orderId`. A listener with a `condition` checking `orderId` will be skipped. Yet the event was still published; another listener without a `condition` can still receive that payload.

Therefore:

- Use `condition` when a listener only cares about a valid subset or a specific business branch.
- Use pre-publish validation when invalid data must be rejected at the business level.
- Do not use `condition` to hide data errors that every consumer should know about.
- If skipping a payload intentionally, record an appropriate metric or log when tracking is needed.

### Using Safe Navigation When Properties May Be Null

SpEL supports the safe navigation operator `?.` to access a property or method without causing a `NullPointerException` on that specific access.

Example:

~~~java
@EventListener(
    condition = "#a0?.customer?.email != null and " +
                "#a0.customer.email.contains('@')")
public void sendEmail(OrderPayload event) {
    // Only runs when customer and email are present, and email contains '@'.
}
~~~

Conditional expressions should be short and easy to read. For complex business rules, put the logic into a validator or policy bean, then invoke that component at the appropriate boundary. Avoid writing a long SpEL string that is difficult to test.

## 4. Distinguishing Event Type, Source, and Content Filtering

Spring can filter listeners at multiple layers:

1. **Event type:** the listener declares `ApplicationListener<E>` or an `@EventListener` method parameter.
2. **Generic event type:** Spring inspects generic metadata when the event type is sufficiently concrete.
3. **Source type:** `SmartApplicationListener` or `GenericApplicationListener` can check the class of the event source.
4. **Runtime condition:** `@EventListener(condition = "...")` inspects event content using SpEL.
5. **Business validation:** a service or domain model verifies whether data satisfies invariants before publishing.

`GenericApplicationListener` provides `supportsEventType(ResolvableType)` and inherits `supportsSourceType(Class<?>)` from `SmartApplicationListener`. This mechanism is useful when writing infrastructure listeners that need to select events by generic type or by source. This is dispatch-layer filtering, not business data validation.

For example, a listener might only care about events emitted from a specific kind of source. However, the source type only tells you what class the event-emitting object belongs to; it does not prove the payload is valid or that the caller is authorized to perform the operation.

### Generic Events and Type Erasure

Java erases generic types at runtime. Spring can still analyze generic metadata when the event hierarchy preserves concrete type arguments.

~~~java
public class EntityCreatedEvent<T> {

    private final T entity;

    public EntityCreatedEvent(T entity) {
        this.entity = entity;
    }

    public T getEntity() {
        return entity;
    }
}

public class PersonCreatedEvent
        extends EntityCreatedEvent<Person> {

    public PersonCreatedEvent(Person person) {
        super(person);
    }
}
~~~

A listener can declare the concrete type:

~~~java
@EventListener
public void onPersonCreated(
        EntityCreatedEvent<Person> event) {
    // Handle event for Person.
}
~~~

If the generic type cannot be inferred from the hierarchy, you can implement `ResolvableTypeProvider` to provide an explicit `ResolvableType`. Do not rely on runtime casts or raw types to substitute for generic metadata.

## 5. Validating Data Before Publishing

An event usually describes a business occurrence that has already happened. Therefore, the publisher should ensure required data is valid before creating and emitting the event.

Practical rules:

- Check that input objects are non-null.
- Check that required strings are non-null, non-empty, and not whitespace-only.
- Check that amounts, quantities, versions, and timestamps fall within valid ranges.
- Check that collections are non-null, elements are non-null, and there are no duplicates if business rules forbid duplicates.
- Check IDs and relationships between fields, e.g., `orderId` must belong to the right `customerId`.
- Make events immutable so data cannot be altered after publishing.

Validation can be done in the service:

~~~java
public void submit(OrderCommand command) {
    if (command == null) {
        throw new IllegalArgumentException("command is required");
    }

    if (command.orderId() == null || command.orderId().isBlank()) {
        throw new IllegalArgumentException("orderId is required");
    }

    if (command.amount() == null || command.amount() <= 0) {
        throw new IllegalArgumentException("amount must be positive");
    }

    publisher.publishEvent(
            new OrderSubmitted(command.orderId(), command.amount()));
}
~~~

The event can protect its own invariants in its constructor to prevent invalid objects from being constructed via another code path:

~~~java
public record OrderSubmitted(String orderId, int amount) {

    public OrderSubmitted {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }

        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
    }
}
~~~

Validation in the service returns errors right at the use-case boundary. Validation in the constructor keeps the event valid wherever it is created. Both layers of protection can coexist when invariants are critical.

### Using Jakarta Bean Validation

If the project uses Jakarta Bean Validation, you can declare constraints:

~~~java
public record OrderCommand(
        @NotBlank String orderId,
        @NotNull @Positive Integer amount) {
}
~~~

Annotations such as `@NotBlank` and `@Positive` are just metadata for a validation provider. They do not execute automatically simply because an object is published via `ApplicationEventPublisher`.

You must call `Validator.validate(...)`, configure appropriate method validation, or use a boundary where Spring has validation enabled. Without a validation provider and an execution mechanism, constraints will not reject payloads on their own.

Example calling `Validator` directly:

~~~java
Set<ConstraintViolation<OrderCommand>> violations =
        validator.validate(command);

if (!violations.isEmpty()) {
    throw new ConstraintViolationException(violations);
}
~~~

Only after validation succeeds should you create and publish the event. Do not offload the responsibility of verifying required data to a downstream listener.

## 6. Invalid Data in Batch Events

When an event carries multiple items, define a policy for the whole batch:

- **All-or-nothing:** if one item is invalid, reject the entire batch before publishing.
- **Partial acceptance:** accept valid items, and return the list of rejected items along with their reasons.
- **Quarantine:** store faulty items in a quarantine area for reprocessing, if the architecture provides one.

Do not silently filter out null or invalid items with `stream.filter(Objects::nonNull)` and treat the batch as succeeded. Callers need to know which items were excluded and why.

Example handling partial acceptance:

~~~java
List<OrderCommand> accepted = new ArrayList<>();
List<RejectedOrder> rejected = new ArrayList<>();

for (OrderCommand command : commands) {
    String reason = validateReason(command);

    if (reason == null) {
        accepted.add(command);
    } else {
        rejected.add(new RejectedOrder(command, reason));
    }
}
~~~

Only publish events for accepted data. You can emit a `BatchImportCompleted` event containing the accepted/rejected counts and batch ID; avoid stuffing all sensitive invalid data into events or logs.

## 7. Validation Errors and Listener Errors Are Two Different Categories

Validation occurs before publishing and decides whether a command is allowed to become an event. Listener filtering occurs after publishing and decides which consumers care about the event.

| Situation | Handling location | Outcome |
|---|---|---|
| Null command | Application service | Rejects the use case |
| Blank `orderId` | Validator/domain constructor | Event is not created |
| `publishEvent(null)` | `ApplicationContext` | Throws `IllegalArgumentException` |
| Payload has null fields | Boundary or listener policy | Must be validated or intentionally filtered |
| Incompatible event type | Multicaster | Listener is not invoked |
| SpEL `condition` false | Event listener adapter | Listener method is skipped |
| Listener throws exception | Multicaster/async executor | Handled according to exception policy |
| Valid event, consumer uninterested | Listener condition/type | Consumer skips the event |

If invalid data prevents the business process from continuing, fail fast before publishing. If a listener simply does not care about a variant of the event, use a type filter or `condition`. If a secondary listener fails, handle the error according to the listener policy; do not turn infrastructure failures into command validation errors.

## 8. Null-Safe Event Design

A well-designed event should have an explicit data contract:

~~~java
public record OrderSubmitted(
        UUID eventId,
        String orderId,
        int amount,
        Instant occurredAt) {

    public OrderSubmitted {
        Objects.requireNonNull(eventId, "eventId is required");
        Objects.requireNonNull(occurredAt, "occurredAt is required");

        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }

        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
    }
}
~~~

Key fields:

- `eventId` for tracing, deduplication, or idempotent handling.
- `orderId` to link with the aggregate.
- `amount` with a valid value range.
- `occurredAt` to express when the business event occurred.

Do not use `null` to represent multiple distinct states. If a field is truly optional, clearly document what its absence means. If there are multiple states, use an enum or an explicit data type.

With mutable payloads, listeners might observe data modified after publishing, especially when events are dispatched asynchronously. Prefer records, immutable collections, and defensive copies so every listener sees the same valid snapshot.

## 9. Complete Example with Java 17 and Spring Framework 6.2

The example below illustrates four scenarios:

1. `publishEvent(null)` is rejected by Spring right at the publish boundary.
2. A non-null legacy payload with invalid fields is still published; the observer listener receives the event, while the listener with a SpEL `condition` skips that payload.
3. An invalid command is rejected by `OrderService` before creating an event.
4. A valid command creates an immutable `OrderSubmitted` event and the listener receives it.

### Directory Structure

~~~text
event-validation-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── EventValidationDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>event-validation-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### EventValidationDemo.java

~~~java
package demo;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class EventValidationDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            ApplicationEventPublisher publisher = context;
            OrderService service = context.getBean(OrderService.class);

            try {
                publisher.publishEvent((Object) null);
            } catch (IllegalArgumentException ex) {
                System.out.println("NULL_EVENT_REJECTED: " + ex.getMessage());
            }

            publisher.publishEvent(
                    new LegacyOrderPayload(null, -10));

            publisher.publishEvent(
                    new LegacyOrderPayload("ORD-79", 120));

            try {
                service.submit(new OrderCommand(" ", 50));
            } catch (IllegalArgumentException ex) {
                System.out.println("COMMAND_REJECTED: " + ex.getMessage());
            }

            service.submit(new OrderCommand("ORD-80", 250));
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        public OrderService orderService(
                ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }

        @Bean
        public EventListeners eventListeners() {
            return new EventListeners();
        }
    }

    public record OrderCommand(String orderId, Integer amount) {
    }

    public record OrderSubmitted(String orderId, int amount) {

        public OrderSubmitted {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException("orderId is required");
            }

            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
        }
    }

    public static class LegacyOrderPayload {

        private final String orderId;
        private final Integer amount;

        public LegacyOrderPayload(String orderId, Integer amount) {
            this.orderId = orderId;
            this.amount = amount;
        }

        public String getOrderId() {
            return orderId;
        }

        public Integer getAmount() {
            return amount;
        }
    }

    public static class OrderService {

        private final ApplicationEventPublisher publisher;

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void submit(OrderCommand command) {
            if (command == null) {
                throw new IllegalArgumentException("command is required");
            }

            if (command.orderId() == null ||
                    command.orderId().isBlank()) {
                throw new IllegalArgumentException("orderId is required");
            }

            if (command.amount() == null || command.amount() <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }

            publisher.publishEvent(
                    new OrderSubmitted(command.orderId(), command.amount()));
        }
    }

    public static class EventListeners {

        @EventListener
        @Order(1)
        public void observeLegacy(LegacyOrderPayload event) {
            System.out.println(
                    "LEGACY_EVENT_RECEIVED: " + event.getOrderId());
        }

        @EventListener(
                condition = "#a0.orderId != null and " +
                            "!#a0.orderId.isBlank() and " +
                            "#a0.amount != null and #a0.amount > 0")
        @Order(2)
        public void processValidLegacy(LegacyOrderPayload event) {
            System.out.println(
                    "LEGACY_FILTER_ACCEPTED: " + event.getOrderId());
        }

        @EventListener
        public void onOrderSubmitted(OrderSubmitted event) {
            System.out.println(
                    "VALID_ORDER_RECEIVED: " + event.orderId());
        }
    }
}
~~~

### Compiling and Running

Run in the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.EventValidationDemo
~~~

Stdout output:

~~~text
NULL_EVENT_REJECTED: Event must not be null
LEGACY_EVENT_RECEIVED: null
LEGACY_EVENT_RECEIVED: ORD-79
LEGACY_FILTER_ACCEPTED: ORD-79
COMMAND_REJECTED: orderId is required
VALID_ORDER_RECEIVED: ORD-80
~~~

Explanation:

1. `ApplicationContext` rejects the null event before dispatch and throws `IllegalArgumentException`.
2. The first `LegacyOrderPayload` is a non-null object, so Spring wraps it in `PayloadApplicationEvent`. The observer listener receives the payload and prints `orderId` null.
3. The `condition` of `processValidLegacy` returns `false` because `orderId` is null and `amount` is negative, so that method is not invoked. The event was still published.
4. The valid payload `ORD-79` is accepted by both the observer listener and the conditional listener.
5. `OrderService` rejects the command with a whitespace-only `orderId`. No `OrderSubmitted` event is created for that command.
6. Command `ORD-80` passes validation, creates a valid `OrderSubmitted` event, and the listener receives it.

The example intentionally keeps an unvalidated `LegacyOrderPayload` class to illustrate how legacy data or data from external sources can enter the event bus. In new code, create immutable events and check invariants before publishing.

## 10. Testing and Observability

Test the publish boundary, validation, and listener filters separately:

- Publishing a null event must throw `IllegalArgumentException`.
- An event's constructor must reject a null source or null required fields per the event contract.
- Invalid commands must be rejected and not publish events.
- Non-null payloads with null fields must only trigger listeners without conditions or listeners designed to handle such data.
- A `false` condition must skip the exact listener method, while other listeners still receive the event.
- A `true` condition must trigger the corresponding listener method.
- Test generic event types so listeners do not receive unintended payloads.
- Test batch partial acceptance so rejected items are not lost track of.

When observability of skipped data is needed, record metrics such as `invalid_payload_total`, `filtered_event_total`, and `rejected_command_total`. Logs should include an event ID or correlation ID, event type, rejection reason, and relevant business keys. Avoid logging full payloads if they contain personal or confidential data.

With async listeners, exceptions do not necessarily propagate back to the publisher. Configure error handling and monitor failed tasks separately. A `false` condition is not an exception and normally does not need error-level logging; only record it if that filtering matters for operations.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Publishing a null event | Spring throws `IllegalArgumentException` | Check the event before publishing |
| Assuming Spring auto-validates payload fields | Listeners may receive invalid data | Validate commands/domain objects at the boundary |
| Using a SpEL condition as global validation | Only one method is skipped; other listeners still run | Validate before publishing if the event is invalid |
| Condition accesses null fields unsafely | SpEL may fail during evaluation | Use null checks or safe navigation |
| Using parameter names without retaining parameter metadata | SpEL cannot find the variable | Use `#a0`/`#p0` or compile with `-parameters` |
| Filtering only by event class | Invalid payloads can still be received | Combine validation and `condition` when needed |
| Using raw generic listeners | Loses explicit type filtering capability | Declare concrete generics |
| Using null to represent a business state | Consumers do not know what null means | Create dedicated events or enums |
| Silently dropping invalid items in a batch | Data loss and hard to audit | Return rejected items with reasons |
| Catching errors in a listener and ignoring them | Faulty data may vanish from observability | Record status, metrics, and retry policy |

## 12. Design Checklist

- Never call `publishEvent` with a null event object.
- Ensure `ApplicationEvent` sources and `PayloadApplicationEvent` payloads are non-null.
- Define which fields are required and which are truly optional.
- Validate commands and business data before publishing.
- Keep events immutable and containing a valid data snapshot.
- Use generic event types to filter event groups at the dispatch layer.
- Use `@EventListener(condition)` only to decide which listener is interested.
- Use `#a0` or `#p0` when stable parameter references are needed in SpEL.
- Use safe navigation and null checks for optional properties.
- Never treat a `false` condition as an event being rejected or cancelled.
- Have a clear policy for batches: all-or-nothing, partial acceptance, or quarantine.
- Track rejected commands and filtered events when business auditing requires it.
- Test null events, null fields, invalid values, true/false conditions, and listener exceptions.

Event filtering ensures each listener only receives the data it cares about. Validation guarantees that emitted events satisfy their business contract. Placing these two responsibilities in their proper places avoids null pointers, invalid data reaching consumers, and conditions accidentally masking publisher bugs.

## 13. Official Documentation

- [Spring Framework 6.2 — Additional Capabilities of the ApplicationContext](https://docs.spring.io/spring/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework 6.2 — PayloadApplicationEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/PayloadApplicationEvent.html)
- [Spring Framework 6.2 — GenericApplicationListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/GenericApplicationListener.html)
- [Spring Framework 6.2 — Null-safety](https://docs.spring.io/spring/reference/6.2/core/null-safety.html)