# Writing an ApplicationListener with a Specific Event Type

## Learning Objectives

In Spring Boot, `ApplicationListener<E>` is an extension point for receiving notifications when **a specific event** is published. Instead of catching every event and writing a chain of `if/else instanceof` checks, we can directly declare the exact type we want to observe:

~~~java
public final class OrderPlacedListener
        implements ApplicationListener<OrderPlacedEvent> {

    @Override
    public void onApplicationEvent(OrderPlacedEvent event) {
        System.out.println("New order: " + event.getOrderId());
    }
}
~~~

The snippet above **only illustrates the signature**; this lesson will provide a complete Spring Boot program, including the event class, how to register listeners, and how to publish events.

After this lesson, you will be able to:

1. Explain the generic type `E extends ApplicationEvent` and the `onApplicationEvent(E event)` method.
2. Write a listener that receives specifically `ApplicationReadyEvent`, `ApplicationEnvironmentPreparedEvent`, or a business event extending `ApplicationEvent`.
3. Choose a registration approach: `@Component`, `@Bean`, `SpringApplication.addListeners(...)`, or `META-INF/spring.factories`.
4. Understand why **a bean-based listener does not receive very early startup events**.
5. Publish events with `ApplicationEventPublisher` and recognize the synchronous default, exception handling, listener ordering, and transaction constraints.
6. Run and verify the Java 17+ / Spring Boot 3.3.13 example with explained output.

**Context:** Spring Boot Application Runtime → Listener. This lesson focuses on **writing a listener with a specific generic type**; advanced mechanisms such as asynchronous multicasters and transactional events are introduced at the level needed to use the API correctly.

## 1. What Is ApplicationListener?

Spring Framework provides the functional interface:

~~~java
package org.springframework.context;

// Abbreviated declaration to illustrate the API; do not create this file in the project.
@FunctionalInterface
public interface ApplicationListener<E extends ApplicationEvent>
        extends EventListener {

    void onApplicationEvent(E event);
}
~~~

In practice, always **import Spring's API** rather than redefining the interface yourself. Meaning:

- `ApplicationListener` is the contract of a component that **listens** for events.
- `E` represents the **event type** the listener is interested in. The bound `E extends ApplicationEvent` ensures this type is a subclass of `org.springframework.context.ApplicationEvent`.
- `onApplicationEvent(E event)` is invoked when a compatible event is published within a scope where the listener is registered.
- Spring uses generic type metadata when available to **filter by type**, without requiring each listener to perform `instanceof` checks for every unrelated event.
- The callback receives the event object, which **does not mean every listener always runs on another thread** or always has a transaction.

Example:

~~~java
public final class ReadyListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        System.out.println("Application is ready");
    }
}
~~~

The snippet above is not standalone: it requires importing `ApplicationListener`, `ApplicationReadyEvent`, and a listener registration mechanism. A properly registered `ReadyListener` will receive `ApplicationReadyEvent`, but it will not receive `ApplicationStartingEvent`, `ContextRefreshedEvent`, or unrelated business events.

### Comparing Three Generic Forms

| Listener declaration | Expected reception scope | When to use |
| --- | --- | --- |
| `ApplicationListener<ApplicationReadyEvent>` | Ready event (and compatible subtypes if any) | Doing work when Boot startup is nearly complete |
| `ApplicationListener<OrderPlacedEvent>` | Business event `OrderPlacedEvent` | Decoupling the publisher from business reaction logic |
| `ApplicationListener<ApplicationEvent>` | Many types of Spring `ApplicationEvent` | Diagnostics/middleware when you truly need to dispatch across many events |

**Prefer a narrow type** when you already know the event you need: the code is easier to read, the IDE checks types better, and it prevents the listener from executing on unrelated events.

If a listener needs multiple event types with different handling, you can create **multiple listeners with specific types** instead of lumping everything into one broad listener. When you need dynamic classification via `ResolvableType` or complex conditional support, you can explore `GenericApplicationListener`/`SmartApplicationListener`, though most business code does not need them.

## 2. Where Do Events Come From?

Spring has two common groups of examples.

### 2.1. Application Lifecycle Events Published by Spring Boot

Events in the `org.springframework.boot.context.event` package include:

- `ApplicationStartingEvent`: very early, before `Environment` and `ApplicationContext` are created.
- `ApplicationEnvironmentPreparedEvent`: the environment is prepared, and the application context has not yet been created.
- `ApplicationContextInitializedEvent`: the context is created, initializers have run, and bean definitions have not yet been loaded.
- `ApplicationPreparedEvent`: bean definitions are loaded, before `refresh`.
- `ApplicationStartedEvent`: after context refresh, **before** `ApplicationRunner`/`CommandLineRunner`.
- `ApplicationReadyEvent`: after the runners, when the startup sequence has nearly reached the ready milestone.
- `ApplicationFailedEvent`: the failure branch when `SpringApplication` fails to start.

In addition, there are `ContextRefreshedEvent` from Spring Framework and `AvailabilityChangeEvent` from Spring Boot. They can also be observed through the appropriate event infrastructure, but they have different types and different meanings.

Example:

~~~java
public final class ReadyListener
        implements ApplicationListener<ApplicationReadyEvent> {
    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        // Handle only when this event is actually published and the listener is registered.
    }
}
~~~

A **successful HTTP request** does not automatically publish `ApplicationReadyEvent`. This event is tied to the application startup process, not a "per-request" callback.

### 2.2. Business Events Published by the Application

For example, when business logic confirms an order, the code can publish `OrderPlacedEvent`. The publisher does not have to call each listener directly; the Spring event infrastructure distributes the event to registered listeners matching the type.

~~~text
OrderService
    |
    +-- ApplicationEventPublisher.publishEvent(OrderPlacedEvent)
              |
              +-- OrderPlacedListener
              +-- AuditOrderListener (if registered)
              +-- Other listener types: do not need to be invoked
~~~

This helps separate responsibilities, but an in-process event **does not automatically become a durable message**. If requirements demand no data loss across instances/processes or across crashes, you need to design transactions, an outbox, a queue/broker, or a suitable retry workflow.

## 3. Two Conditions to Receive an Event: Correct Type and Timely Registration

Even a listener written with the right generic type will not receive an event if it **is not registered with the publisher's context** or **is registered too late**.

| Registration option | Suitable for | Does it catch ApplicationStartingEvent? |
| --- | --- | --- |
| `@Component` on a class implementing `ApplicationListener<E>` | Business listeners or events after the bean factory is ready | **No**, because the bean does not exist yet at Starting |
| `@Bean` returning `ApplicationListener<E>` | Managing listeners through Spring configuration | **No** for events before the bean is created |
| `SpringApplication.addListeners(listener)` **before `run()`** | Very early Boot events; configured directly in `main` | **Yes**, if the generic type matches |
| `SpringApplicationBuilder.listeners(listener)` | Projects using the builder to start up | **Yes**, if registered before run |
| `META-INF/spring.factories` with key `ApplicationListener` | Libraries or apps wanting automatic early listener registration | **Yes**, when metadata is loaded properly by Boot |
| `@EventListener` on a bean method | Events once the container already manages the bean | **No** for events published before bean initialization |

**A very common issue:** Writing:

~~~java
@Component
public class EarlyListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    @Override
    public void onApplicationEvent(ApplicationEnvironmentPreparedEvent event) {
        System.out.println("Environment prepared");
    }
}
~~~

The code above is **valid Java**, but relying solely on `@Component` scanning to register the listener is **too late** for `ApplicationEnvironmentPreparedEvent`. At that point, the application context has not even been created to scan beans. This cannot be solved by adding `@Order(-100)`: ordering among listeners cannot change when a bean is created.

**The right approach:** Instantiate the listener early with `new`, then call `addListeners(...)` before `run(...)`, or declare the class in `spring.factories`.

## 4. Complete Example: Three ApplicationListeners with Specific Types

We will build a non-web CLI application to keep logs clear:

- `EnvironmentPreparedListener`: added to `SpringApplication` before `run`; listens only for `ApplicationEnvironmentPreparedEvent`.
- `OrderPlacedListener`: a Spring bean; listens only for the custom `OrderPlacedEvent`.
- `ReadyListener`: a Spring bean; listens only for `ApplicationReadyEvent`.
- `ApplicationRunner`: publishes the custom event to verify callback ordering.

**Requirements:** JDK 17+ and Gradle compatible with Spring Boot 3.3.13. This lesson uses Spring Boot **3.3.13** for API consistency, without needing an embedded web server or database.

### 4.1. Directory Structure

~~~text
typed-listener-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/listeners/
    ├── TypedListenerApplication.java
    ├── EnvironmentPreparedListener.java
    ├── OrderPlacedEvent.java
    ├── OrderPlacedListener.java
    └── ReadyListener.java
~~~

**File `settings.gradle`:**

~~~groovy
rootProject.name = 'typed-listener-demo'
~~~

**File `build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.listeners.TypedListenerApplication'
}
~~~

The Spring Boot plugin has an explicit version; `platform(...)` manages starter versions via the Spring Boot 3.3.13 BOM. No web starter is needed because the example only demonstrates lifecycle and events within the context.

### 4.2. Environment Event Listener: Starting Very Early

**File `EnvironmentPreparedListener.java`:**

~~~java
package com.example.listeners;

import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;

public final class EnvironmentPreparedListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    @Override
    public void onApplicationEvent(ApplicationEnvironmentPreparedEvent event) {
        System.out.println("EARLY: environment prepared");
    }
}
~~~

Do not place `@Component` on this class: we will instantiate and add it **before** `SpringApplication.run`. This is the reliable way for a listener that needs to receive events before Spring creates the application context.

Inside the callback, `event.getEnvironment()` already exists. However, do not call `event.getApplicationContext()` because this event type does not provide a context. Do not inject application repositories/services in the listener constructor because beans are not ready yet.

### 4.3. Defining a Custom ApplicationEvent

**File `OrderPlacedEvent.java`:**

~~~java
package com.example.listeners;

import java.util.Objects;
import org.springframework.context.ApplicationEvent;

public final class OrderPlacedEvent extends ApplicationEvent {

    private final String orderId;

    public OrderPlacedEvent(Object source, String orderId) {
        super(source);
        this.orderId = Objects.requireNonNull(orderId, "orderId");
    }

    public String getOrderId() {
        return orderId;
    }
}
~~~

Analysis:

- `OrderPlacedEvent` **extends** `ApplicationEvent` so it can be used as type `E` for `ApplicationListener<OrderPlacedEvent>`.
- The constructor `super(source)` declares the source object of the event; the source value must not be `null`. In this example, the application instance is used as the source.
- `orderId` is the business data passed to the listener. Making it `final` without a setter keeps the event payload stable during delivery; if it holds mutable objects, immutability must be managed separately.
- This event **is not automatically published** merely because the class exists. A component must call `publishEvent(...)`.

Avoid placing an entire JPA entity with open lazy relations inside an event and passing it to another thread without analyzing transactions and the persistence context. In this example, `String orderId` is concise and easy to understand.

### 4.4. Spring-Managed Business Listener

**File `OrderPlacedListener.java`:**

~~~java
package com.example.listeners;

import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;

@Component
public final class OrderPlacedListener
        implements ApplicationListener<OrderPlacedEvent> {

    @Override
    public void onApplicationEvent(OrderPlacedEvent event) {
        System.out.println("ORDER_LISTENER: " + event.getOrderId());
    }
}
~~~

`@Component` lets Spring component scanning discover the class. During context refresh, Spring manages and registers it with the event multicaster. The generic type `OrderPlacedEvent` is the event filtering contract: this listener **does not** receive `ApplicationReadyEvent` or `ApplicationEnvironmentPreparedEvent`.

If the callback requires dependencies such as `AuditRepository`, constructor injection can be used on the listener bean. Note that this listener **does not exist early** like `EnvironmentPreparedListener`, so do not use it to modify Config Data loading before the context is created.

### 4.5. Listener Observing the Ready Milestone

**File `ReadyListener.java`:**

~~~java
package com.example.listeners;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;

@Component
public final class ReadyListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        System.out.println("READY_LISTENER: application ready");
    }
}
~~~

Here `@Component` is appropriate: `ApplicationReadyEvent` is published **after** the context is refreshed and startup runners have completed. The listener bean has already been created and registered at an earlier stage.

`ApplicationReadyEvent` is not `AvailabilityChangeEvent<ReadinessState>`. Boot publishes the ready event and then publishes the readiness accepting-traffic state; they are two distinct event objects, and two separate listener types can be used if the application truly needs both.

### 4.6. Main Class, Publisher, and ApplicationRunner

**File `TypedListenerApplication.java`:**

~~~java
package com.example.listeners;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class TypedListenerApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(TypedListenerApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        // Add before run: the listener receives the EnvironmentPrepared event.
        application.addListeners(new EnvironmentPreparedListener());

        try (ConfigurableApplicationContext context = application.run(args)) {
            System.out.println("MAIN: run returned");
        }

        System.out.println("MAIN: context closed");
    }

    @Bean
    ApplicationRunner publishOrder(ApplicationEventPublisher publisher) {
        return args -> {
            System.out.println("RUNNER: before publish");

            publisher.publishEvent(
                    new OrderPlacedEvent(this, "ORD-001"));

            System.out.println("RUNNER: after publish");
        };
    }
}
~~~

Explanation of each responsibility:

1. `SpringApplication` creates a non-web context thanks to `WebApplicationType.NONE`. `Banner.Mode.OFF` and `setLogStartupInfo(false)` reduce the startup lines printed by Boot, though they do not disable all logging.
2. `application.addListeners(new EnvironmentPreparedListener())` happens before `run`; the listener can observe the early event of the matching type.
3. `@SpringBootApplication` and component scanning discover `OrderPlacedListener` and `ReadyListener` in the `com.example.listeners` package.
4. Spring injects `ApplicationEventPublisher` into the `@Bean` factory method so the Runner can publish an `OrderPlacedEvent`. `ApplicationEventPublisher` is not an HTTP message broker; it is the API for the in-context event mechanism.
5. `ApplicationRunner` runs **after** `ApplicationStartedEvent` and **before** `ApplicationReadyEvent`.
6. By default, the Spring event multicaster is synchronous: `OrderPlacedListener` runs when `publishEvent(...)` is called, and control then returns to the runner. If an asynchronous multicaster is configured, completion order may differ.
7. `try-with-resources` closes the `ConfigurableApplicationContext` after the experiment. Use this pattern only for short-lived CLI applications; long-running server applications should not close the context immediately when `run` returns.

### 4.7. Running and Inspecting stdout

In the `typed-listener-demo` directory, with Gradle installed:

~~~bash
gradle bootRun
~~~

If the project already has the Gradle Wrapper, you can run `./gradlew bootRun` on Linux/macOS or `.\gradlew.bat bootRun` on Windows. The sample project does not generate a wrapper automatically; an external Gradle installation is required, or you can add a wrapper separately.

**The lines printed by the example Java code itself**, ignoring framework/Gradle logs and assuming no other listeners with side effects are added, appear in this order:

~~~text
EARLY: environment prepared
RUNNER: before publish
ORDER_LISTENER: ORD-001
RUNNER: after publish
READY_LISTENER: application ready
MAIN: run returned
MAIN: context closed
~~~

Output reading table:

| Log line | Where is it printed? | Why does it appear then? |
| --- | --- | --- |
| `EARLY: environment prepared` | `EnvironmentPreparedListener` | The Environment has been prepared, before the context is created. |
| `RUNNER: before publish` | `ApplicationRunner` | The context has refreshed; the runner begins its task. |
| `ORDER_LISTENER: ORD-001` | `OrderPlacedListener` | The publisher emits `OrderPlacedEvent`; the listener is selected by type. |
| `RUNNER: after publish` | `ApplicationRunner` | With the synchronous default, the listener callback has returned. |
| `READY_LISTENER: application ready` | `ReadyListener` | Boot publishes `ApplicationReadyEvent` after the runners. |
| `MAIN: run returned` | `main` | The `application.run(args)` call completes. |
| `MAIN: context closed` | `main` | `try-with-resources` closes the context after use. |

**Key check:** There is no `ORDER_LISTENER` when Boot publishes `ApplicationReadyEvent`; there is no `READY_LISTENER` when the runner publishes `OrderPlacedEvent`. Generic types help Spring route events to interested listeners.

## 5. Using @Bean Instead of @Component

You do not always need a listener class annotated with `@Component`. If you own a configuration class, you can define a bean:

~~~java
@Configuration
class ListenerConfiguration {

    @Bean
    ApplicationListener<OrderPlacedEvent> extraOrderListener() {
        return event ->
                System.out.println("EXTRA_ORDER: " + event.getOrderId());
    }
}
~~~

This is an **additional illustrative snippet**, not a required file for the project in Section 4. It requires importing `@Configuration`, `@Bean`, and `ApplicationListener`. Once the bean is created and registered, it listens for `OrderPlacedEvent`. The generic return type on the `@Bean` method allows Spring to inspect type information; obscuring it behind a raw bean/type without enough metadata can make event type resolution less clear.

If you add this bean to the sample project, **an additional listener** will receive the event, so the sample stdout in Section 4.7 will change. Avoid having two listeners with non-idempotent side effects unintentionally.

An important distinction: a `@Bean ApplicationListener<ApplicationEnvironmentPreparedEvent>` is still too late for the first environment-prepared event. Both `@Bean` and `@Component` depend on the application context. Being able to write a lambda does not make the listener appear earlier than the container lifecycle.

## 6. Registering an Early Listener via spring.factories

When building a starter/library that needs to auto-register a listener before context creation, you can use:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Content:

~~~properties
org.springframework.context.ApplicationListener=com.example.listeners.EnvironmentPreparedListener
~~~

With this approach, Boot loads `EnvironmentPreparedListener` via the factories mechanism. The sample class has a no-argument constructor, so it fits. **To test the `spring.factories` path on its own**, remove the line:

~~~java
application.addListeners(new EnvironmentPreparedListener());
~~~

in `main`. Keeping both registration paths active at the same time can easily produce **two listener instances** and duplicate logs/side effects; you should not rely on Boot automatically deduplicating every form of duplicate registration.

Do not confuse the key above with:

~~~properties
org.springframework.boot.BootstrapRegistryInitializer=...
~~~

That is a different extension point that receives `BootstrapRegistry` during a very early phase. Also do not place `ApplicationListener` in `AutoConfiguration.imports` — that file is the mechanism for auto-configuration.

### What If You Only Observe ApplicationStartingEvent?

A listener such as:

~~~java
public final class StartingListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("Starting now");
    }
}
~~~

is illustrative; it requires importing `ApplicationStartingEvent` and `ApplicationListener`, then registering via `addListeners` **before run** or `spring.factories`. At this point **neither `Environment` nor `ApplicationContext` exists yet**, so do not inject beans or call APIs that require a live context. This illustrates that **both the generic type and the registration timing** must be right.

## 7. ApplicationListener vs. @EventListener

Both event-receiving styles use the same Spring mechanism but differ in syntax:

**Interface style:**

~~~java
@Component
class InventoryListener implements ApplicationListener<OrderPlacedEvent> {
    @Override
    public void onApplicationEvent(OrderPlacedEvent event) {
        // Handle the specific event type.
    }
}
~~~

**Annotation style:**

~~~java
@Component
class InventoryObserver {

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        // The event type is inferred from the method parameter.
    }
}
~~~

These two snippets are illustrative only; do not add them to the Section 4 example if you want to preserve its exact stdout. They require the corresponding imports, and both become **listener beans once managed by the context**.

| Criterion | `ApplicationListener<E>` | `@EventListener` |
| --- | --- | --- |
| Type declaration | Generic `E` on the interface | Method parameter or annotation attribute |
| Callback | `onApplicationEvent(E event)` | Application-defined method |
| Early registration before context | Yes, via instance + `addListeners`/`spring.factories` | Not with a regular bean method |
| Multiple event types | Typically multiple classes/interfaces or a broad type with filtering | Supports conditions and multiple methods |
| Spring API dependency on the class | Yes | Spring annotation on the method |
| Ease of testing | Can call `onApplicationEvent` directly | Can call the handler method or test through the context |

Choose `ApplicationListener<E>` when you want an **explicit listener contract**, a class with a single clear responsibility, or early registration before the context exists. Choose `@EventListener` when you already have a bean and want a concise method, or need annotation conditions (such as `condition`) without creating a separate class.

Do not use `@EventListener` as a workaround for an `ApplicationEnvironmentPreparedEvent` that already occurred before beans existed.

## 8. Custom Events: Type Safety and Scope

### Event Classes Must Extend ApplicationEvent

The generic bound on `ApplicationListener<E>` requires `E extends ApplicationEvent`. For example:

~~~java
record OrderPlaced(String orderId) {}
~~~

this is a Java record that **does not** extend `ApplicationEvent`, so you **cannot** directly declare:

~~~java
// INVALID with respect to the type bound E:
ApplicationListener<OrderPlaced> listener = event -> {};
~~~

The second snippet intentionally demonstrates a **compile error**; do not place it into runnable source code. If you want to publish a record as a payload object, Spring Framework supports `ApplicationEventPublisher.publishEvent(Object)` and can wrap it in `PayloadApplicationEvent<T>`. In that case you can use:

~~~java
ApplicationListener<PayloadApplicationEvent<OrderPlaced>>
        listener = event ->
                System.out.println(event.getPayload().orderId());
~~~

This snippet is an **API illustration**; it requires importing `ApplicationListener`, `PayloadApplicationEvent`, and defining the `OrderPlaced` record. You can also use `@EventListener` with the record payload as a parameter. In our main hands-on example, we deliberately declare `OrderPlacedEvent extends ApplicationEvent` so the type parameter is explicit and does not depend on a wrapper.

### The Publisher Is Not Coupled to a Specific Listener

~~~java
publisher.publishEvent(new OrderPlacedEvent(this, "ORD-001"));
~~~

The publisher does not need to call `orderPlacedListener.onApplicationEvent(event)`. Routing relies on the event infrastructure and registered listeners. This makes it possible to add audit/notification listeners without directly modifying the publisher.

However, **events are not RPC**. Do not rely on a listener's return value to pass results back to the business flow that published the event; `onApplicationEvent` returns `void`. If the publishing side needs a guaranteed synchronous result, calling a service interface directly may be more appropriate.

## 9. Synchronicity, Listener Ordering, and Exceptions

### Synchronous Default

With the default configuration of `SimpleApplicationEventMulticaster`, most listeners execute **synchronously** on the thread that publishes the event. In our example, because the runner calls `publisher.publishEvent(...)`, the `ORDER_LISTENER` line appears before `RUNNER: after publish`.

This has several consequences:

1. A slow listener delays the return of the `publishEvent` call.
2. A listener throwing an unchecked exception can propagate the exception back up to the publisher.
3. If the publisher is inside an `ApplicationRunner`, an unhandled exception can cause **Spring Boot startup to fail** and prevent reaching `ApplicationReadyEvent`.
4. If the publisher is handling an HTTP request, a failing synchronous listener can affect that request/response, depending on exception handling policies.

**Do not treat event listeners as asynchronous "fire-and-forget"** unless you have explicitly configured a suitable executor/multicaster.

### Adjusting Order

If two listeners handle the same event and ordering genuinely matters, you can use `@Order` or implement `Ordered` when supported by the listener registration/sorting mechanism:

~~~java
@Component
@Order(10)
class FirstOrderListener implements ApplicationListener<OrderPlacedEvent> {
    @Override
    public void onApplicationEvent(OrderPlacedEvent event) {
        // Prioritize processing according to listener order.
    }
}
~~~

This is a **partial illustration** requiring imports for `Component`, `Order`, and `ApplicationListener`. Smaller order values generally have higher priority. Do not use listener ordering as a substitute for mandatory business dependencies; if B must run only after A successfully commits data, design proper transaction/coordination boundaries.

When event delivery is switched to asynchronous execution, **invocation or scheduling order does not guarantee completion order**. A listener with a lower order value can still finish after another listener.

### Failing Listeners Can Break the Startup Path

Example **intentionally causing an error**:

~~~java
@Override
public void onApplicationEvent(OrderPlacedEvent event) {
    throw new IllegalStateException("Order listener failed");
}
~~~

This is only an illustrative callback body, not a change to add to the runnable code. If it is invoked synchronously from a runner without exception handling, `SpringApplication.run(...)` can fail before ready. Therefore, a listener needs a clear error policy: should failures fail the business operation, or should errors be retried/recorded separately?

Do not "swallow" every exception just to keep the application running, especially when the listener performs critical side effects such as mandatory audit logging or balance updates.

## 10. Transactions and Reliability

An event published from inside a transaction **does not automatically wait for commit**. With a regular synchronous listener, the callback can run before the transaction commits. If the listener sends an email or calls an external system and the DB transaction later rolls back, the system may already have sent a notification for a transaction that was never confirmed.

Mental model:

~~~text
@Transactional orderService.placeOrder(...)
    |
    +-- save Order (not yet committed)
    +-- publishEvent(OrderPlacedEvent)
    |      └-- listener sends email immediately (if synchronous)
    |
    +-- transaction rollback
           └-- Sent email is not automatically recalled
~~~

When a callback needs to be bound to a transaction, Spring provides `@TransactionalEventListener` (commonly used with `AFTER_COMMIT`) within an appropriate transaction management context. This **does not** mean the event is durably persisted and automatically redelivered after a crash. With an outbox, the application writes an event record in the same transaction, and a worker/broker processes and retries it. Each solution provides a different level of guarantee.

The same applies to multi-replica applications: `ApplicationEventPublisher` only publishes within **a single application context/process**, and does not automatically forward events to other pods. For inter-process communication, you need a message broker, HTTP/gRPC, or other suitable infrastructure.

## 11. Advanced Notes When Using Generic Events

### Broad Listeners vs. Narrow Listeners

~~~java
ApplicationListener<ApplicationEvent> broad = event -> {
    // Listen to multiple subtypes.
};
~~~

With a broad listener, code usually has to distinguish each event via `instanceof`. If the requirement is only to handle `OrderPlacedEvent`, a narrow listener is clearer and less likely to be triggered unintentionally.

### Generic Listeners and Spring's ResolvableType

When a class directly declares `implements ApplicationListener<OrderPlacedEvent>`, generic type information is usually clear enough for Spring to determine which event type to deliver. However, scenarios using **raw types**, custom proxies, multiple layers of generic base classes, or lambdas lacking type metadata can be more complex.

Example to avoid:

~~~java
@SuppressWarnings("rawtypes")
ApplicationListener listener = event -> {
    // No concrete type parameter remains in the declaration.
};
~~~

The snippet above is an **illustration of bad code**. Raw types lose Java's type-safety guarantees, invite warnings, and make routing harder to reason about. In real code, declare `ApplicationListener<MyEvent>` or a concrete class with a clear type.

### Parent/Child Contexts Can Propagate Duplicate Events

Spring event publication in an `ApplicationContext` can propagate events from a **child context up to a parent context**. If there are multiple contexts or multiple `SpringApplication` runs, a listener in the parent may see multiple events of the same type published from different contexts. Therefore:

- Do not assume every event appears only once across the entire JVM.
- For events carrying a context (`ContextRefreshedEvent`, some Spring Boot events), check the source context when needed.
- If you only want to handle events from the current context, compare the event's context with the context injected into the listener bean.
- Do not use `@Order` to fix duplicate listener registration or event bubbling.

### Cleanup Is Not Tied to the Request Lifecycle

A listener bean is destroyed together with the application context according to bean lifecycle rules, **not** created and destroyed per event. If a listener holds mutable state, ensure concurrency safety, avoid storing per-request data in singleton fields, and clean up resources in the proper lifecycle hooks.

## 12. Common Mistakes and Fixes

**Mistake 1 — Using only `@Component` for an early listener.** Early events are published before bean scanning; switch to `SpringApplication.addListeners(...)` before `run` or `spring.factories`.

**Mistake 2 — Writing `ApplicationListener<ApplicationEvent>` and assuming every event has a context.** Some very early Boot events do not have a context yet. Choose a specific type or check the event/source appropriately.

**Mistake 3 — Confusing `@EventListener` with `ApplicationListener`.** `@EventListener` is an annotation on a bean method; `ApplicationListener<E>` is an interface with the `onApplicationEvent` callback. You can choose either, but do not assume an annotation makes a bean get created before the context.

**Mistake 4 — Never calling `publishEvent`.** Defining `OrderPlacedEvent` and a listener does not publish the event automatically; a publisher must call `ApplicationEventPublisher.publishEvent(...)` in the business flow.

**Mistake 5 — Using a generic type that does not extend `ApplicationEvent`.** `ApplicationListener<OrderPlaced>` will not compile if `OrderPlaced` is a plain record. Use an event class extending `ApplicationEvent`, or `PayloadApplicationEvent<T>`/`@EventListener` for payload objects.

**Mistake 6 — Believing events are always async.** By default listeners are typically synchronous, which can slow down or fail the publisher. If asynchronous execution is needed, design the executor, backpressure, error handling, and task ordering.

**Mistake 7 — Assuming `@Order` guarantees transaction commit.** Listener order does not replace transaction boundaries. Check `@TransactionalEventListener` or an outbox if after-commit/durable delivery is required.

**Mistake 8 — Publishing an event and thinking every replica receives it.** Spring application events are local to the process/context, not a distributed message bus.

**Mistake 9 — Running an infinite task in an `ApplicationReadyEvent` listener.** The callback runs at the startup/ready milestone; long-blocking work can affect readiness. Use a background service/executor with an appropriate lifecycle.

**Mistake 10 — Accessing beans during `ApplicationStartingEvent`/`EnvironmentPreparedEvent`.** At that moment the context has not been created yet; do not autowire application services into an early listener and expect them to be ready.

**Mistake 11 — Registering the same listener via both `addListeners` and `spring.factories`.** This can create multiple instances and duplicate side effects; choose one approach or design idempotency yourself.

**Mistake 12 — Swallowing exceptions so "events do not affect the publisher."** If a side effect is critical, failing to handle errors explicitly can corrupt business state. Distinguish mandatory tasks from best-effort tasks, and attach appropriate retry/monitoring.

## 13. Exercises

1. Run the Section 4 example. Why does `EARLY` appear before `RUNNER`, while `READY_LISTENER` appears after the runner?
2. Change `OrderPlacedListener` to `ApplicationListener<ApplicationReadyEvent>` while keeping the logic that reads `getOrderId()`. What error will the compiler report? How do generic types protect your code?
3. Remove `application.addListeners(new EnvironmentPreparedListener())`. Does the `EARLY` log still appear? Why do the bean listeners still work?
4. Register `EnvironmentPreparedListener` via `spring.factories` while removing `addListeners`. Confirm it still receives the early event.
5. Add another `AuditOrderListener implements ApplicationListener<OrderPlacedEvent>`. When one event is published, how many business listeners receive it? When changing the type to `ApplicationReadyEvent`, what changes?
6. Inside the `OrderPlacedListener` callback, print the thread name using `Thread.currentThread().getName()` and compare it with the runner. With the synchronous default, what do you expect? Should you hard-code thread names in tests?
7. Temporarily throw an exception in `OrderPlacedListener`. Observe `RUNNER: after publish` and `READY_LISTENER`. What does this show about how an event listener can affect startup?
8. Replace `OrderPlacedEvent` with a plain record and try `ApplicationListener<OrderPlaced>`. Why does the generic constraint prevent compilation? Explore `PayloadApplicationEvent<OrderPlaced>`.
9. A listener needs to send an email **only after** the DB commit succeeds. Why is an immediately running `ApplicationListener<OrderPlacedEvent>` not always suitable? Explain the roles of after-commit and outbox.
10. A system has parent and child application contexts. Why can a parent listener see events published in the child, and how would you identify the source?
11. Add an `@EventListener` method on another bean to listen for `OrderPlacedEvent`. Compare its syntax and registration timing with the interface listener.
12. When an application receives thousands of events per second, what should you measure before configuring an asynchronous multicaster (callback duration, queue, retry, memory, ordering, tracing)?
13. Why is `ApplicationReadyEvent` not equivalent to a successful HTTP request event? Choose the appropriate listener for these two different needs.

## Key Takeaways

- `ApplicationListener<E extends ApplicationEvent>` lets you **receive a specific event type** via `onApplicationEvent(E event)`.
- **Having the right type is not enough**: the listener must be registered **before** the event occurs and within the scope where the event is published.
- For events after refresh/runners, `@Component`/`@Bean` beans or `@EventListener` methods are generally suitable.
- For very early startup events, use `SpringApplication.addListeners(...)` before `run` or `META-INF/spring.factories`.
- Business events are published via `ApplicationEventPublisher.publishEvent(...)`; Spring routes them by event type.
- By default, listeners are usually **synchronous**, and exceptions can affect the publisher; Spring internal events are not a durable message queue.
- When you need transaction-after-commit semantics, async delivery, multi-replica distribution, or retries, choose a dedicated design mechanism rather than just changing the generic type.

### References

- Spring Framework 6.1 — `ApplicationListener<E>` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/ApplicationListener.html
- Spring Framework 6.1 — `ApplicationEventPublisher` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework — Standard and Custom Events: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events
- Spring Framework — Annotation-based Event Listeners: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events-annotation
- Spring Framework — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Boot 3.3 — SpringApplication Events and Listeners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — `ApplicationEnvironmentPreparedEvent` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationEnvironmentPreparedEvent.html
- Spring Boot 3.3 — `ApplicationReadyEvent` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html
