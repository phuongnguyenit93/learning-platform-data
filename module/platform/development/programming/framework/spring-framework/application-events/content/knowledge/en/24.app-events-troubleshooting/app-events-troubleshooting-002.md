# Event Type or Generic Mismatch When Handling Spring Application Events

## 1. Problem: Published, Yet the Listener Does Not Run

In Spring Framework, many event-listening issues stem from **the type actually emitted by the publisher not matching the type the listener registered to receive**. Some errors are caught by the compiler; others only surface at runtime, causing `publishEvent(...)` to return normally while the callback is never invoked.

For example, a service publishes an `InvoicePaidPayload` record:

```java
publisher.publishEvent(new InvoicePaidPayload("INV-101"));
```

While the listener is written as:

```java
public final class InvoicePaidListener
        implements ApplicationListener<InvoicePaidEvent> {
    @Override
    public void onApplicationEvent(InvoicePaidEvent event) {
        // Only handles InvoicePaidEvent, not InvoicePaidPayload.
    }
}
```

Two classes with similar names and meanings **are not synonymous with the same Java type**. Even though both carry an invoice ID, Spring does not automatically infer they are the same event and convert between them.

A subtler source of bugs is generics:

```java
@EventListener
public void onStringChanged(ValueChangedEvent<String> event) {
    // Intends to receive String-typed changes.
}
```

At runtime, Java applies **type erasure**; if the event does not provide sufficiently clear generic type information, the matching mechanism may fail to distinguish `ValueChangedEvent<String>` from `ValueChangedEvent<Integer>` as the author expects.

This lesson shows how to diagnose whether the problem lies in **event type, generic bound, wrapper, generic resolution capability**, or **other registration/dispatching infrastructure**; then reproduce and fix it using a Spring Framework 6.2 + Java 17 example and tests.

## 2. Quick Diagnostic Diagram

```text
publisher.publishEvent(something)
            |
            v
What type does "something" actually have?
            |
     +------+------------------+
     |                         |
     v                         v
ApplicationEvent           POJO / record
     |                         |
     v                         v
Preserves declared        Spring may wrap it in
event type                PayloadApplicationEvent<T>
     |                         |
     +------------+------------+
                  |
                  v
What type does the listener want to receive?
  - ApplicationListener<E extends ApplicationEvent>
  - @EventListener method param
  - GenericApplicationListener / other conditions
                  |
                  v
Are runtime type/generics compatible?
                  |
           +------+------+
           |             |
          YES           NO
           |             |
           v             v
Check bean,          Fix signature,
condition, timing,   wrapper, or
async/transaction    generic metadata
```

You should record **both sides** before editing code:

1. The Java type of the object at the publish site (including type parameters that may have been erased).
2. The declared type of the listener: generic interface or `@EventListener` method parameter.

Do not change every listener's parameter type to `ApplicationEvent` or `Object` just to "make it listen": this can receive far too many events, hide design bugs, and feed unrelated data into your callback logic.

## 3. ApplicationListener<E>: Mandatory Generic Bound

Spring Framework defines the listener interface as:

```java
public interface ApplicationListener<E extends ApplicationEvent>
        extends EventListener {
    void onApplicationEvent(E event);
}
```

Meaning: `E` **must be a subtype of `org.springframework.context.ApplicationEvent`**.

### 3.1. Correct Approach with an ApplicationEvent Subclass

```java
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;

public final class InvoicePaidEvent extends ApplicationEvent {
    private final String invoiceId;

    public InvoicePaidEvent(Object source, String invoiceId) {
        super(source);
        this.invoiceId = invoiceId;
    }

    public String getInvoiceId() {
        return invoiceId;
    }
}

public final class InvoicePaidListener
        implements ApplicationListener<InvoicePaidEvent> {
    @Override
    public void onApplicationEvent(InvoicePaidEvent event) {
        System.out.println(event.getInvoiceId());
    }
}
```

These are **two illustrative signature classes**, not the complete demo project in section 7. When an `InvoicePaidListener` instance is registered in the Spring context and a matching `InvoicePaidEvent` is published, the listener can be dispatched.

### 3.2. Incorrect Approach with a Plain Java Record

```java
record InvoicePaidPayload(String invoiceId) {
}

// DOES NOT COMPILE:
class WrongListener
        implements ApplicationListener<InvoicePaidPayload> {
    @Override
    public void onApplicationEvent(InvoicePaidPayload event) {
    }
}
```

The snippet above is an **intentionally invalid anti-pattern**, not included in the runnable project. The compiler reports an error like `Type parameter ... is not within its bound; should extend ApplicationEvent` because `InvoicePaidPayload` does not extend `ApplicationEvent`.

Do not try to drop generics to bypass the compiler. Fix it according to your actual goal:

- If you want the `ApplicationListener<InvoicePaidEvent>` interface, define the event extending `ApplicationEvent`.
- If you want to keep a plain Java record/POJO, use an `@EventListener` method accepting that record directly.
- If you need an interface listener for a POJO, you can use `ApplicationListener<PayloadApplicationEvent<InvoicePaidPayload>>` to receive the corresponding wrapper; note the difference between wrapper and payload.

This is a **compile-time error**. It is not an event that was published and "swallowed" by Spring.

## 4. ApplicationEvent and POJO/Record Payloads Are Not the Same

Since Spring Framework 4.2, the publisher accepts event objects without requiring them to extend `ApplicationEvent`.

### 4.1. Publishing a Traditional ApplicationEvent

```java
publisher.publishEvent(
        new InvoicePaidEvent(this, "INV-101"));
```

Here Spring processes the event as class `InvoicePaidEvent`. An `ApplicationListener<InvoicePaidEvent>` bean or an `@EventListener` method taking that class are appropriate declarations.

### 4.2. Publishing a Plain Java Payload

```java
public record InvoicePaidPayload(String invoiceId) {
}

publisher.publishEvent(new InvoicePaidPayload("INV-102"));
```

For a POJO/record that is not an `ApplicationEvent`, Spring uses `PayloadApplicationEvent` to wrap the content for the event infrastructure. You can receive the payload directly via a method:

```java
@EventListener
public void onInvoicePaid(InvoicePaidPayload event) {
    System.out.println(event.invoiceId());
}
```

Spring has a payload matching mechanism, so an `@EventListener` method accepting a record is valid. You do not need to convert the record into an `ApplicationEvent` subclass just to use the annotation.

If you want to work with the wrapper:

```java
import org.springframework.context.ApplicationListener;
import org.springframework.context.PayloadApplicationEvent;

public class InvoicePayloadListener
        implements ApplicationListener<
                PayloadApplicationEvent<InvoicePaidPayload>> {

    @Override
    public void onApplicationEvent(
            PayloadApplicationEvent<InvoicePaidPayload> event) {
        InvoicePaidPayload payload = event.getPayload();
        System.out.println(payload.invoiceId());
    }
}
```

This is an **illustrative class**, requiring the `InvoicePaidPayload` record to be defined and the class registered as a bean/listener instance. With this approach, the callback receives `PayloadApplicationEvent<InvoicePaidPayload>`, **not** `InvoicePaidPayload` itself.

### 4.3. Confusing the Source Object and the Payload Content

```java
var event = new PayloadApplicationEvent<>(
        "publisher-source", new InvoicePaidPayload("INV-102"));
```

In the wrapper:
- `event.getSource()` returns the source object passed when creating the wrapper.
- `event.getPayload()` returns the `InvoicePaidPayload` record.
- These two values can be completely different objects.

When `publishEvent(Object)` receives a POJO, Spring wraps it with the appropriate source. Do not write listeners assuming `getSource()` is always the payload, or cast the source to a business class without verifying the contract.

**Key debugging signal:** log the class of the object passed to `publishEvent(...)`, and when inspecting a wrapper, also log `getPayload().getClass()`. Avoid logging only variable names or event names in messages.

## 5. Differences Between @EventListener and ApplicationListener

| Registration approach | Typical signature | Required event |
| --- | --- | --- |
| Implement interface | `ApplicationListener<InvoicePaidEvent>` | `InvoicePaidEvent extends ApplicationEvent` |
| Method annotation | `@EventListener void on(InvoicePaidEvent e)` | `InvoicePaidEvent` |
| Method annotation | `@EventListener void on(InvoicePaidPayload p)` | Payload record/POJO |
| Interface receiving wrapper | `ApplicationListener<PayloadApplicationEvent<InvoicePaidPayload>>` | Spring wrapper for the corresponding payload |
| Advanced generic listener | `GenericApplicationListener` | Filter by `ResolvableType` and source type as configured |

**One type is not automatically equivalent to another.** `InvoicePaidEvent` and `InvoicePaidPayload` might share the same `invoiceId` field, yet Spring still treats them as distinct.

If a method is annotated:

```java
@EventListener
public void on(InvoicePaidEvent event) {
    // ...
}
```

... and the publisher emits `InvoicePaidPayload`, this callback does not match; change the method parameter to `InvoicePaidPayload` or update the producer to emit `InvoicePaidEvent` according to the agreed business contract.

If using:

```java
@EventListener({InvoicePaidEvent.class, ContextRefreshedEvent.class})
public void onEither() {
    // Multiple event types declared on the annotation, method has no parameter.
}
```

This is an **illustrative snippet**, requiring imports for the referenced types. When a method needs to listen to multiple event types via the annotation attribute, use a **parameterless** method, since two unrelated classes cannot fit into a single strongly typed parameter. If you want to branch by event and use their data, separating into two typed methods is usually much clearer.

## 6. Generic Type Erasure: Silent Failures at Runtime

### 6.1. The Problem

Suppose you want an event whose payload type varies:

```java
class ValueChangedEvent<T> extends ApplicationEvent {
    private final T value;

    ValueChangedEvent(Object source, T value) {
        super(source);
        this.value = value;
    }

    T getValue() {
        return value;
    }
}
```

Goal:

```java
@EventListener
public void onText(ValueChangedEvent<String> event) {
    // String values only.
}

@EventListener
public void onNumber(ValueChangedEvent<Integer> event) {
    // Integer values only.
}
```

The two methods have different generics **in source code**. However, the JVM does not retain the concrete type argument in an instance like `new ValueChangedEvent<>("source", "ready")` in a way that can be reliably inferred from the runtime class alone. The runtime class of the instance is the same `ValueChangedEvent`.

According to Spring documentation, generic filtering works when the framework **can resolve** the event's generic parameter—for instance from a concrete subclass or from `ResolvableTypeProvider`. If the runtime type does not expose that information, filtering may not work as intended; do not assume Spring infers `T` merely from the diamond operator `<>` at the `new` site.

### 6.2. Option A: Subclass Fixing the Generic

```java
class StringValueChangedEvent extends ValueChangedEvent<String> {
    StringValueChangedEvent(Object source, String value) {
        super(source, value);
    }
}
```

This is an **illustrative class**; it assumes `ValueChangedEvent<T>` is defined with a constructor and visibility permitting subclassing. The subclass hierarchy fixes `T = String`, allowing Spring to read the generic info from the type declaration. This approach makes sense when the number of event variants is small and each has distinct meaning.

### 6.3. Option B: ResolvableTypeProvider

If you create many events with the same generic class, implement `org.springframework.core.ResolvableTypeProvider` to supply type information to Spring:

```java
@Override
public ResolvableType getResolvableType() {
    return ResolvableType.forClassWithGenerics(
            ValueChangedEvent.class,
            ResolvableType.forInstance(value));
}
```

This snippet is an **illustrative method** inside `ValueChangedEvent<T>`; the class must implement `ResolvableTypeProvider` and import `ResolvableType`. When `value` is a `String`, the reported type is `ValueChangedEvent<String>`; when it is an `Integer`, the reported type is `ValueChangedEvent<Integer>`.

**Limitations to understand:**
- `ResolvableType.forInstance(value)` inspects the runtime type of the value. For a `List<String>` instantiated as `ArrayList`, the type argument `String` still cannot be resolved from the instance alone due to erasure.
- When `value` is a proxy or subtype object, its runtime type may differ from the expected generic contract. If exactness is required, store a `ResolvableType`/type token explicitly provided via the constructor.
- When `value` is `null`, type inference from the instance is impossible; disallow null or pass explicit generic metadata.
- Do not force every generic event to implement the provider; if the generic only serves domain type safety and Spring does not need to filter by `T`, a regular event class may suffice.

### 6.4. Distinguishing Java Generics from Runtime Event Types

Even though syntax like:

```java
new ValueChangedEvent<String>("source", "ready")
```

has explicit generics at compile time, Spring does not receive that raw source-code line during runtime dispatch. Generic metadata must have a **readable path**: class hierarchy, `ResolvableTypeProvider`, or an equivalent metadata mechanism.

Therefore, when a `ValueChangedEvent<String>` listener does not run, check how the event exposes `ResolvableType` before removing `@EventListener` or changing the event parameter to `Object`.

## 7. Runnable Project: Testing 4 Distinct Event Paths

The project uses **Java 17+, Spring Framework 6.2.13, and Maven**. No Spring Boot/web/DB is needed; this is a simple Spring `ApplicationContext` example. It demonstrates:

1. `ApplicationListener<InvoicePaidEvent>` receiving an event extending `ApplicationEvent`.
2. `@EventListener` receiving a plain Java record when the record is published directly.
3. Two `@EventListener` methods distinguishing `ValueChangedEvent<String>` and `ValueChangedEvent<Integer>` via `ResolvableTypeProvider`.
4. Tests confirming handlers do not cross-fire and an unrelated record triggers no business listener.

### 7.1. Directory Structure

```text
event-type-diagnostics/
├── pom.xml
└── src/
    ├── main/java/example/events/EventTypeDiagnostics.java
    └── test/java/example/events/EventTypeDiagnosticsTest.java
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>event-type-diagnostics</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.13</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. EventTypeDiagnostics.java

```java
package example.events;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.PayloadApplicationEvent;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.ResolvableType;
import org.springframework.core.ResolvableTypeProvider;

public class EventTypeDiagnostics {

    // Traditional type: a genuine ApplicationEvent.
    public static final class InvoicePaidEvent extends ApplicationEvent {
        private final String invoiceId;

        public InvoicePaidEvent(Object source, String invoiceId) {
            super(source);
            this.invoiceId = Objects.requireNonNull(invoiceId);
        }

        public String getInvoiceId() {
            return invoiceId;
        }
    }

    // Payload type: record does NOT extend ApplicationEvent.
    public record InvoicePaidPayload(String invoiceId) {
    }

    public record UnrelatedPayload(String value) {
    }

    // Generic event: supplies runtime ResolvableType to Spring.
    public static final class ValueChangedEvent<T> extends ApplicationEvent
            implements ResolvableTypeProvider {

        private final T value;

        public ValueChangedEvent(Object source, T value) {
            super(source);
            this.value = Objects.requireNonNull(value);
        }

        public T getValue() {
            return value;
        }

        @Override
        public ResolvableType getResolvableType() {
            return ResolvableType.forClassWithGenerics(
                    ValueChangedEvent.class,
                    ResolvableType.forInstance(value));
        }
    }

    public static final class EventLog {
        private final List<String> messages = new ArrayList<>();

        public void add(String value) {
            messages.add(value);
            System.out.println(value);
        }

        public List<String> snapshot() {
            return List.copyOf(messages);
        }
    }

    public static final class ClassicListener
            implements ApplicationListener<InvoicePaidEvent> {

        private final EventLog log;

        public ClassicListener(EventLog log) {
            this.log = log;
        }

        @Override
        public void onApplicationEvent(InvoicePaidEvent event) {
            log.add("CLASSIC invoice=" + event.getInvoiceId());
        }
    }

    public static final class PayloadHandler {
        private final EventLog log;

        public PayloadHandler(EventLog log) {
            this.log = log;
        }

        @EventListener
        public void onPaid(InvoicePaidPayload event) {
            log.add("PAYLOAD invoice=" + event.invoiceId());
        }
    }

    public static final class GenericHandlers {
        private final EventLog log;

        public GenericHandlers(EventLog log) {
            this.log = log;
        }

        @EventListener
        public void onText(ValueChangedEvent<String> event) {
            log.add("GENERIC string=" + event.getValue());
        }

        @EventListener
        public void onNumber(ValueChangedEvent<Integer> event) {
            log.add("GENERIC integer=" + event.getValue());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ExampleConfig {

        @Bean
        EventLog eventLog() {
            return new EventLog();
        }

        @Bean
        ClassicListener classicListener(EventLog log) {
            return new ClassicListener(log);
        }

        @Bean
        PayloadHandler payloadHandler(EventLog log) {
            return new PayloadHandler(log);
        }

        @Bean
        GenericHandlers genericHandlers(EventLog log) {
            return new GenericHandlers(log);
        }
    }

    public static void publishSamples(
            AnnotationConfigApplicationContext context) {
        context.publishEvent(new InvoicePaidEvent("app", "INV-1"));
        context.publishEvent(new InvoicePaidPayload("INV-2"));
        context.publishEvent(new ValueChangedEvent<>("app", "ready"));
        context.publishEvent(new ValueChangedEvent<>("app", 7));
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             ExampleConfig.class)) {
            publishSamples(context);
        }
    }
}
```

This program has two type-independent listener groups:

- `ClassicListener` is registered via `ApplicationListener<InvoicePaidEvent>`, so when the `InvoicePaidPayload` record is published, it is not selected.
- `PayloadHandler` is registered via `@EventListener`, receiving the actual payload class even though Spring wraps the record internally in `PayloadApplicationEvent`.
- `GenericHandlers` has two `@EventListener` methods with different type arguments. `ValueChangedEvent.getResolvableType()` returns the type corresponding to `String` or `Integer`; Spring uses this metadata when selecting the method.

One design detail: `EventLog` simply writes to an `ArrayList` without synchronization. The demo uses **synchronous dispatch on the same thread**, so it suits illustration. If using async/a multicaster executor, replace it with a thread-safe sink and test with explicit synchronization.

### 7.4. Running main and stdout

In the directory containing `pom.xml`, using Maven 3.9+ and JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.events.EventTypeDiagnostics
```

Lines printed by **the program itself** (excluding environment-dependent logs):

```text
CLASSIC invoice=INV-1
PAYLOAD invoice=INV-2
GENERIC string=ready
GENERIC integer=7
```

Reason for this ordering: the application publishes each event sequentially; the example `AnnotationConfigApplicationContext` configuration uses the default synchronous event multicaster, without an executor or `@Async`. Each event matches only its intended callback, so there are no extra log lines.

If a generic callback receives the wrong type, verify that `getResolvableType()` is correct and the listener declares the corresponding generic; do not "fix" it by casting inside `onNumber(...)`.

## 8. Integration Test Reproducing the Publish and Filter Paths

File `src/test/java/example/events/EventTypeDiagnosticsTest.java`:

```java
package example.events;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class EventTypeDiagnosticsTest {

    @Test
    void eachEventMatchesOnlyItsExpectedHandler() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             EventTypeDiagnostics.ExampleConfig.class)) {

            EventTypeDiagnostics.publishSamples(context);

            var log = context.getBean(
                    EventTypeDiagnostics.EventLog.class);

            assertEquals(
                    List.of(
                            "CLASSIC invoice=INV-1",
                            "PAYLOAD invoice=INV-2",
                            "GENERIC string=ready",
                            "GENERIC integer=7"),
                    log.snapshot());
        }
    }

    @Test
    void unrelatedPayloadDoesNotTriggerAnyBusinessHandler() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             EventTypeDiagnostics.ExampleConfig.class)) {

            context.publishEvent(
                    new EventTypeDiagnostics.UnrelatedPayload("OTHER"));

            var log = context.getBean(
                    EventTypeDiagnostics.EventLog.class);

            assertTrue(log.snapshot().isEmpty());
        }
    }

    @Test
    void directCallTestsCallbackButNotSpringDispatch() {
        var log = new EventTypeDiagnostics.EventLog();
        var listener = new EventTypeDiagnostics.ClassicListener(log);

        listener.onApplicationEvent(
                new EventTypeDiagnostics.InvoicePaidEvent(
                        this, "INV-DIRECT"));

        assertEquals(
                List.of("CLASSIC invoice=INV-DIRECT"),
                log.snapshot());
    }
}
```

Run:

```bash
mvn test
```

Or run only this class:

```bash
mvn -Dtest=EventTypeDiagnosticsTest test
```

The project defines **3 JUnit test methods**. When all assertions pass, Maven Surefire reports tests passing; timing and exact log output depend on the environment and should not be treated as fixed stdout.

**Meaning of the three tests:**

1. `eachEventMatchesOnlyItsExpectedHandler` verifies **actual Spring dispatch**, including class matching, payload wrapping, and generics via `ResolvableTypeProvider`.
2. `unrelatedPayloadDoesNotTriggerAnyBusinessHandler` verifies that an unrelated event does not accidentally leak into typed listeners.
3. `directCallTestsCallbackButNotSpringDispatch` proves that calling `onApplicationEvent` manually tests callback logic, **not Spring's registration/matching**.

If a direct unit test passes while a publish integration test fails, the issue likely lies in bean registration, event type, or dispatch configuration; that is why the first kind of test is especially valuable for diagnostics.

## 9. When Generics Truly Cannot Be Resolved

For events using custom generics, you must clarify which type was actually preserved at runtime.

### 9.1. Inspecting the Event's Own ResolvableType

In debug code you can inspect:

```java
ValueChangedEvent<String> event =
        new ValueChangedEvent<>("source", "ready");

System.out.println(event.getResolvableType());
```

This is an **illustrative snippet**, assuming you are in the project from section 7 with appropriate imports/nested classes. `getResolvableType()` returns a `ResolvableType` representing `ValueChangedEvent<java.lang.String>`. The string representation of `ResolvableType` may vary across versions; do not write assertions depending on exact `toString()` output if your goal is only to verify the generic.

A better assertion in tests:

```java
assertEquals(
        String.class,
        event.getResolvableType().getGeneric(0).resolve());
```

For the integer event, the corresponding generic is `Integer.class`. This is the actual fact showing whether Spring has enough information to separate typed listener methods.

### 9.2. Use ResolvableTypeProvider Only When Needed

If an application only needs separate events for `InvoicePaid` and `InvoiceCancelled`, two concrete classes are usually easier to read than a `GenericBusinessEvent<T>` with multiple nested generic levels. Do not overuse generics just to reduce class count at the cost of hard diagnostics and ambiguous business contracts.

If the generic contains a collection or interface, store a real type token (e.g., a `ResolvableType` built from `ParameterizedTypeReference`/explicit metadata) if deeper filtering is required. `value.getClass()` is not enough to recover every erased type argument.

### 9.3. Receiving Generics via an Explicit Subclass

Spring can resolve generics from a hierarchy such as:

```java
final class InvoiceStringChanged
        extends ValueChangedEvent<String> {
    InvoiceStringChanged(Object source, String value) {
        super(source, value);
    }
}
```

This is an **illustration of the subclass solution**; do not drop it directly into the demo because the demo's `ValueChangedEvent` is declared `final`. To use this solution, you must define a **non-final** generic base event and permit valid subclassing. Change the design in one direction or the other; do not copy this snippet into the demo expecting it to compile as-is.

The goal is to preserve the concrete type argument in the class hierarchy — not to create subclasses merely to "satisfy" syntax.

## 10. Generic Loss Due to Intermediate Interfaces or Raw Types

### 10.1. Losing Generic Information in Abstractions

Consider a hierarchy like:

```java
interface ListenerPort<T> {
    void handle(T event);
}

abstract class BaseListener<T> {
    public abstract void handle(T event);
}
```

These are **illustrative Java types**, not directly recognized by Spring as `ApplicationListener`. When writing an adapter bridging `T` and `ApplicationEvent`, ensure the actual event type is declared/resolved on the final bean. If the interface/base class is too generic, runtime metadata may lack the information Spring needs.

When refactoring from `ApplicationListener<InvoicePaidEvent>` to a generic class like `abstract class BaseEventListener<T extends ApplicationEvent> implements ApplicationListener<T>`, check whether subclasses fix `T`. A raw generic bean does not guarantee Spring knows which exact event it receives.

### 10.2. Raw ApplicationListener and Dangerous Casts

```java
// Anti-pattern: using a raw type and casting arbitrarily.
ApplicationListener listener = event -> {
    InvoicePaidEvent paid = (InvoicePaidEvent) event;
    System.out.println(paid.getInvoiceId());
};
```

This is an **illustrative snippet with unchecked/raw warnings**, not a safe listener to register. If the listener receives another event, the cast can throw `ClassCastException` at runtime. Raw types forfeit type safety and can obscure the framework's event filtering.

Fix with:

```java
ApplicationListener<InvoicePaidEvent> listener =
        event -> System.out.println(event.getInvoiceId());
```

When registering via a lambda instance, Spring's inference of the generic type from the lambda's runtime representation can be less clear than from a concrete class. For code requiring strict type filtering and easy diagnostics, prefer classes with explicit generic declarations or register via `ApplicationListener.forPayload(...)` as appropriate.

### 10.3. Wildcards and Overly Broad Types

```java
@EventListener
public void onAny(ApplicationEvent event) {
    // Receives many ApplicationEvent types, including lifecycle events.
}
```

This method is broader than `@EventListener void on(InvoicePaidEvent e)`: it can receive system events the handler was not designed to process. For Spring-wrapped POJO payloads, it sees the wrapper rather than the record. If subsequent code downcasts unchecked, runtime risk is high.

Scope listeners to the **narrowest event type** needed; do not use `Object`/`ApplicationEvent` as a blanket workaround for mismatch errors.

## 11. Not Every "Lost Event" Listener Is Caused by Types

A solid diagnostic procedure must rule out causes with identical symptoms:

| Symptom | Possible cause | How to verify |
| --- | --- | --- |
| `publishEvent` succeeds, listener does not run | Different event type; generic mismatch | Print publisher class, listener signature, `ResolvableType` |
| Listener uses the right class yet still does not run | Bean not registered/scanned | Inspect context configuration and integration test |
| `@EventListener` is only on an object created with `new` | Object is not a Spring bean | Register the bean, do not instantiate manually outside context |
| Listener waiting for `AFTER_COMMIT` does not run | No active transaction or rolled back | Check transaction phase, `fallbackExecution` |
| `@Async` listener logs appear late | Dispatched to executor/queue | Log thread, executor, and task result |
| Listener with `condition` does not run | SpEL expression false or evaluation error | Check condition and inputs |
| Event published very early during bootstrap | Listener bean not yet created/registered | Register early with `SpringApplication.addListeners(...)` when appropriate |
| Same simple class name in different package/classloader | Different runtime classes | Print qualified class name and classloader when needed |
| Multiple listeners appear to fire repeatedly | Possible duplicate bean/instance registration | Inspect bean graph / registration points |
| `ClassCastException` inside listener | Raw generic or wrong cast on wrapper/source | Eliminate raw types, use type-safe signatures |

Specifically:

- **`@TransactionalEventListener`** does not run outside an active transaction when `fallbackExecution=false`, even if the event type matches. Do not change generics to fix a transaction bug.
- **`@Async`** can run after the publisher returns; tests must wait with a timeout rather than relying on lucky `Thread.sleep(...)`.
- **Early bootstrap events** such as `ApplicationEnvironmentPreparedEvent` occur before context beans are initialized; an `@Component @EventListener` in that context will generally miss them. Register the listener on `SpringApplication` before `run(...)`.
- **Parent/child context listeners** can receive events propagated up the hierarchy; distinguish source/context to avoid unintended duplicate handling. A matching type does not guarantee every delivery represents the same business event.

## 12. Step-by-Step Debugging Workflow in a Real Environment

### Step 1: Start from the Publish Call Itself

At the publish site, verify:

```java
Object event = buildEvent();
log.info("Publishing event runtimeType={}",
        event.getClass().getName());
publisher.publishEvent(event);
```

This is an **illustrative snippet**, assuming `buildEvent()`, logger, and publisher are defined. Do not log the entire event if it contains PII, passwords, or tokens. The runtime type is the essential piece of data; the variable name `event` reveals nothing.

### Step 2: Check the Listener Signature

Open the actual registered class and confirm:

- The interface is `ApplicationListener<ConcreteEvent>`, not another type.
- Class `ConcreteEvent` actually extends `ApplicationEvent`.
- If using `@EventListener` for a POJO, the parameter is the **payload class** rather than accidentally an unintended wrapper.
- If using the wrapper, verify the corresponding `PayloadApplicationEvent<T>` generic.
- For generic events, confirm `T` is resolved via subclass or provider.
- No raw types or broad casts are masking the error.

### Step 3: Cross-Check with a Small Integration Test

A test with `AnnotationConfigApplicationContext` and the real listener bean is usually the fastest path. Publish **the exact same object type** production emits and assert the callback is invoked the expected number of times. If a direct `listener.onApplicationEvent(...)` test passes while a publish test fails, suspect wiring or type routing.

### Step 4: Inspect Event Metadata and ResolvableType

For events implementing `ResolvableTypeProvider`, check `getResolvableType().getGeneric(0).resolve()`. If the type fails to resolve, supply explicit metadata or switch to concrete classes.

If the event is a POJO, distinguish the runtime payload class from the internal `PayloadApplicationEvent`. Do not assume `event.getSource()` is the business object.

### Step 5: Verify Bean and Filters

Verify the bean belongs to the context that actually publishes the event. For `@EventListener(condition = "...")`, confirm the condition holds for that payload. If `@Order` is present, remember it affects execution order, not whether an incompatible event type matches.

### Step 6: Verify Async/Transaction

Log the thread name and transaction status at the start of the callback if needed. For `@Async`, confirm the executor received the task; for `@TransactionalEventListener`, check phase, commit, and rollback. Do not assume `publishEvent(...)` returning means an asynchronous listener has finished.

### Step 7: Lock In with Regression Tests

Once fixed, add tests verifying:
- Events of the right type are received.
- Similar-looking events of a different type **are not received**.
- `String` and `Integer` generics do not cross-handle.
- Payload records reach the expected `@EventListener` method.
- When parent/child contexts, async, or transactions are involved, test those mechanisms separately.

## 13. Common Mistakes and Fixes

**Mistake 1 — `ApplicationListener<SomeRecord>` fails to compile.** The interface requires `SomeRecord extends ApplicationEvent`. Fix by using an event subclass, an `@EventListener` accepting the record, or a wrapper listener.

**Mistake 2 — Publisher emits a POJO, listener expects an ApplicationEvent subclass.** The two types do not match. Align the producer/consumer contract rather than just making class names look similar.

**Mistake 3 — Treating `PayloadApplicationEvent.getSource()` as the payload.** Use `getPayload()`; `source` is the originating source object.

**Mistake 4 — Expecting `GenericEvent<String>` to distinguish itself just from `<String>`.** Java erases type arguments at runtime. Use a generic-fixing subclass or `ResolvableTypeProvider`.

**Mistake 5 — Using raw `ApplicationListener`.** Forfeits compile-time type safety and invites bad casts. Declare concrete generics or use the appropriate listener API.

**Mistake 6 — Placing `@EventListener` on an object outside the Spring container.** The annotation does not automatically discover objects created via `new`. Register the bean or listener instance through the context.

**Mistake 7 — Changing the parameter to `Object` when the listener does not run.** Destroys the event contract and lets the callback receive unrelated types. Fix the actual type and metadata.

**Mistake 8 — Changing generics without testing the provider.** If the event already implements `ResolvableTypeProvider` incorrectly, Spring can still misclassify it. Unit test `getResolvableType()` and integration test dispatch.

**Mistake 9 — Testing by invoking the listener directly and concluding Spring dispatch works.** A direct test only calls a Java method. Test through `context.publishEvent(...)`.

**Mistake 10 — Ignoring bean lifecycle, transactions, and async.** Some bugs look like type mismatches when the callback was actually registered too late, is waiting for commit, or is running on a worker.

**Mistake 11 — Logging short class names.** Two packages or classloaders can hold classes with the same simple name. When needed, log the fully qualified name and classloader/correlation ID.

**Mistake 12 — Casting payloads based on field contents.** Two records with identical fields are still two distinct Java types. Use an explicit adapter/mapping if event conversion is needed.

## 14. Checklist When Fixing Event Type or Generic Issues

1. Have you identified the **runtime class** of the object passed into `publishEvent(...)`?
2. Does that object **extend ApplicationEvent** or is it a POJO/record?
3. Does the listener declare **`ApplicationListener<E>`**, `@EventListener`, or a wrapper listener?
4. For `ApplicationListener<E>`, does `E extends ApplicationEvent` hold?
5. When receiving a payload, did you distinguish `PayloadApplicationEvent.getPayload()` from `getSource()`?
6. For `GenericEvent<T>`, does Spring have **sufficient ResolvableType** to determine `T`?
7. Is any raw class/interface or unchecked cast hiding type information?
8. Is the listener registered in the **right ApplicationContext** and at the right time?
9. Is a `condition`, async, transaction phase, or another filter preventing the callback from running?
10. Does the integration test publish the exact object type production emits and assert the invocation count?
11. Does the test cover similar but invalid events to prevent accidental matching?
12. After the fix, does the code preserve a clear business contract instead of widening to `Object`?

**Remember:** Spring does not route events based on variable names, matching fields, or business descriptions. It relies on **resolvable event types**, proper generic metadata, and registered listener mechanisms. Start from the runtime class at the publisher, compare against the listener signature, check erasure/`ResolvableTypeProvider`, and confirm with an integration test; only then investigate other causes like bean lifecycle, async, or transactions.

## References

- [Spring Framework 6.2 — ApplicationContext Events and Generic Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html): event types, `@EventListener`, generic events, and `ResolvableTypeProvider`.
- [Spring Framework API — ApplicationListener](https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/context/ApplicationListener.html): `ApplicationListener<E extends ApplicationEvent>` and listener matching.
- [Spring Framework API — PayloadApplicationEvent](https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/context/PayloadApplicationEvent.html): wrapper for POJO payloads.
- [Spring Framework API — ResolvableTypeProvider](https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/core/ResolvableTypeProvider.html): providing runtime generic type metadata.
- [Spring Framework API — GenericApplicationListener](https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/context/event/GenericApplicationListener.html): advanced event/source type filtering.
- [JUnit 5 User Guide](https://docs.junit.org/5.11.4/user-guide/): integration testing and assertions.