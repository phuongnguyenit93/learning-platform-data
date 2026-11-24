# Listener Bean Not Scanned in Spring Application Events

A familiar situation when using **Spring Framework Application Events**: a service calls `ApplicationEventPublisher.publishEvent(...)` without errors, yet the method annotated with `@EventListener` prints no logs and performs no work. A very common cause is that **the class containing the listener is not registered as a Spring bean** because it lies outside the component scan scope, lacks a stereotype annotation, is excluded by a filter, or is disabled by a configuration condition.

Key point: **`@EventListener` only marks an event-handling method on an already Spring-managed bean; the annotation itself does not register the class as a bean.** If the class does not belong to the `ApplicationContext` publishing the event, Spring has no listener method to invoke.

This lesson guides you through distinguishing a **not-scanned / missing-bean** error from other causes with the same "event not received" symptom: wrong payload type, `@EventListener` condition, unrefreshed context, too-early event, missing transaction, async listener execution, or context hierarchy issues.

## 1. Mechanism: From a Class on the Classpath to an Actual Event Listener

An `@EventListener` method can only be used once the required steps have taken place:

```text
Class OrderPlacedListener exists in JAR / classpath
            |
            v
Does @ComponentScan scan the right package and does the class pass filters?
            |
            +-- NO  --> no bean definition
            |             -> @EventListener is not registered
            |
            +-- YES --> bean definition is registered
                           |
                           v
                    Bean is created/initialized per lifecycle
                           |
                           v
                    EventListenerMethodProcessor
                    detects @EventListener
                    and creates listener adapter
                           |
                           v
                    ApplicationEventMulticaster
                    has listener matching the event
                           |
                           v
                    Publisher emits event with matching type/context
                           |
                           v
                    Listener method is invoked
```

`@ComponentScan` searches for **candidate components** on the classpath according to base packages and filters. Classes annotated with `@Component`, `@Service`, `@Repository`, `@Controller`, or properly meta-annotated custom stereotypes can be discovered, provided they lie within the scan scope. Besides component scanning, beans can also be registered **explicitly** via `@Bean`, `@Import`, or bean definition registration APIs.

`EventListenerMethodProcessor` processes `@EventListener` on Spring-managed beans during bean/context processing. With a properly initialized `ApplicationContext`, you normally **do not need** to register this processor manually. However, if you instantiate an object via `new` without declaring it as a bean, the processor will not inspect that object.

### A Very Typical Incorrect Example

```java
package com.acme.listeners;

import org.springframework.context.event.EventListener;

public class OrderPlacedListener {

    @EventListener
    public void handle(OrderPlaced event) {
        System.out.println("Received " + event.orderId());
    }
}
```

This is **illustrative code**, assuming `OrderPlaced` is imported or declared appropriately. The class has no `@Component` and is not declared via `@Bean`/`@Import`, so Spring has no reason to register it as a bean automatically.

Adding `@Component` is a necessary step **if using component scanning**, but **not sufficient** if the `com.acme.listeners` package lies outside the base packages being scanned.

## 2. Check Package Placement: Most Common Cause in Spring Boot

When an application uses `@SpringBootApplication`, that annotation includes component scanning. Under standard configuration, the scan scope starts from **the package containing the startup class** and descends into **subpackages**.

### 2.1. Wrong Layout: Listener in a Sibling Package

```text
src/main/java/
└── com/acme/
    ├── app/
    │   ├── StoreApplication.java
    │   └── service/
    │       └── OrderService.java
    └── listeners/
        └── OrderPlacedListener.java
```

Example `StoreApplication`:

```java
package com.acme.app;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StoreApplication {
    // main(...) calls SpringApplication.run(...).
}
```

By default, scanning starts at `com.acme.app`, which includes `com.acme.app.service`. It **does not automatically include `com.acme.listeners`** because it is a **sibling** package, not a subpackage. An `OrderPlacedListener` with `@Component` is still skipped in this layout.

### 2.2. Fix 1: Place the Startup Class in a Common Root Package

```text
com/acme/
├── StoreApplication.java       <-- @SpringBootApplication in com.acme
├── app/service/OrderService.java
└── listeners/OrderPlacedListener.java
```

When `StoreApplication` resides in `com.acme`, default component scanning covers all subpackages. This is usually the simplest and most maintainable layout for a single-context Spring Boot application.

**Do not place the startup class in the default package** (without a `package` declaration). Doing so can force Spring to scan too broadly, causing performance issues and unwanted bean registrations.

### 2.3. Fix 2: Explicitly Specify Packages to Scan

If the project structure does not allow moving the startup class:

```java
package com.acme.app;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(scanBasePackages = {
        "com.acme.app",
        "com.acme.listeners"
})
public class StoreApplication {
}
```

This is an **illustrative configuration snippet**, not standalone. You can prefer the **type-safe** variant:

```java
@SpringBootApplication(scanBasePackageClasses = {
        StoreApplication.class,
        OrderPlacedListener.class
})
public class StoreApplication {
}
```

When using this variant, import `OrderPlacedListener`. Spring uses **the package of each class** as a scan root. This avoids typos in package name strings during refactoring.

**Scope limitation:** `scanBasePackages`/`scanBasePackageClasses` control **component scanning**; they do not automatically replace all scanning rules for JPA entities or Spring Data repositories. If the application has JPA/repositories in other packages, separately check `@EntityScan` or `@EnableJpaRepositories` when needed. Do not fix a listener issue by indiscriminately widening scanning across all dependencies.

### 2.4. Fix 3: Register the Listener Bean Explicitly

When you only need a single listener outside the scan scope, you can declare it explicitly:

```java
@Configuration
@Import(OrderPlacedListener.class)
class EventListenerConfiguration {
}
```

Or:

```java
@Configuration
class EventListenerConfiguration {

    @Bean
    OrderPlacedListener orderPlacedListener() {
        return new OrderPlacedListener();
    }
}
```

These are **two separate illustrative options**; each requires appropriate imports, and `EventListenerConfiguration` must itself be a configuration class loaded by Spring. Do not apply both if they accidentally create **two listener beans** handling the same event. A listener does not need `@Component` if it is already declared via `@Bean`.

## 3. Runnable Java 17+ Practice: Missing Listener Scan, Then Fixing Component Scan

Pure **Spring Framework 6.2.9** example, requiring no Spring Boot or database. Two `ApplicationContext` instances are created sequentially with different configurations:

1. `ServiceOnlyConfig` scans only `example.service`, so `OrderService` is a bean while `OrderPlacedListener` is not. The service still publishes the event; the listener prints nothing.
2. `ServiceAndListenerConfig` scans both `example.service` and `example.listener`, so the listener is a Spring bean; the same event type is handled normally.

This setup proves the difference comes from **component scanning**, not the event API or transaction configuration.

### 3.1. Directory Structure

```text
listener-scan-demo/
├── pom.xml
└── src/main/java/example/
    ├── ScanDiagnosisDemo.java
    ├── config/
    │   ├── ServiceOnlyConfig.java
    │   └── ServiceAndListenerConfig.java
    ├── events/
    │   └── OrderPlaced.java
    ├── service/
    │   └── OrderService.java
    └── listener/
        └── OrderPlacedListener.java
```

Save each file at the path matching its `package` statement. Do not put multiple `public` classes into one Java file.

### 3.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>listener-scan-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.ScanDiagnosisDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 3.3. src/main/java/example/events/OrderPlaced.java

```java
package example.events;

public record OrderPlaced(String orderId) {
}
```

A Java record is a normal event payload; extending `ApplicationEvent` is not required. When using `publishEvent(Object)`, Spring can wrap this payload in `PayloadApplicationEvent` and select `@EventListener` methods matching the payload type.

### 3.4. src/main/java/example/service/OrderService.java

```java
package example.service;

import example.events.OrderPlaced;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ApplicationEventPublisher publisher;

    public OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void place(String orderId) {
        System.out.println("service: publish " + orderId);
        publisher.publishEvent(new OrderPlaced(orderId));
    }
}
```

The service is a Spring bean because it has `@Service` and is scanned by both configurations. `ApplicationEventPublisher` is a Spring-provided dependency. `place(...)` prints a line before publishing to show that calling the publisher **does not necessarily fail when there are no listeners**.

### 3.5. src/main/java/example/listener/OrderPlacedListener.java

```java
package example.listener;

import example.events.OrderPlaced;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderPlacedListener {

    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        System.out.println("listener: received " + event.orderId());
    }
}
```

The class has `@Component` and the method has `@EventListener`. This is a valid listener configuration **if `example.listener` is scanned**; implementing `ApplicationListener<?>` is unnecessary.

### 3.6. src/main/java/example/config/ServiceOnlyConfig.java

```java
package example.config;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@ComponentScan(basePackages = "example.service")
public class ServiceOnlyConfig {
}
```

Scans only `example.service`, so `OrderService` is in the context. `example.listener.OrderPlacedListener` lies outside the scan scope, even though it is completely present on the classpath.

### 3.7. src/main/java/example/config/ServiceAndListenerConfig.java

```java
package example.config;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@ComponentScan(basePackages = {
        "example.service",
        "example.listener"
})
public class ServiceAndListenerConfig {
}
```

The only difference from `ServiceOnlyConfig` is the **base packages of `@ComponentScan`**.

### 3.8. src/main/java/example/ScanDiagnosisDemo.java

```java
package example;

import example.config.ServiceAndListenerConfig;
import example.config.ServiceOnlyConfig;
import example.listener.OrderPlacedListener;
import example.service.OrderService;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class ScanDiagnosisDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             ServiceOnlyConfig.class)) {

            int listenerBeans =
                    context.getBeanNamesForType(
                            OrderPlacedListener.class).length;

            System.out.println(
                    "case=missing listenerBeans=" + listenerBeans);
            context.getBean(OrderService.class).place("PO-42");
        }

        try (var context =
                     new AnnotationConfigApplicationContext(
                             ServiceAndListenerConfig.class)) {

            int listenerBeans =
                    context.getBeanNamesForType(
                            OrderPlacedListener.class).length;

            System.out.println(
                    "case=fixed listenerBeans=" + listenerBeans);
            context.getBean(OrderService.class).place("PO-43");
        }
    }
}
```

Run from the project directory using JDK 17+ and Maven (dependencies may be downloaded on the first run):

```bash
mvn -q compile exec:java
```

**Lines printed by the program**, in order (ignoring other Maven/Spring logs):

```text
case=missing listenerBeans=0
service: publish PO-42
case=fixed listenerBeans=1
service: publish PO-43
listener: received PO-43
```

**Step-by-step breakdown:**

1. The first context is created with `ServiceOnlyConfig`; Spring scans `example.service`, registers `OrderService`, and does not scan `example.listener`. Result: `listenerBeans=0`.
2. `OrderService.place("PO-42")` still calls `publishEvent` normally. There is no `OrderPlacedListener` bean in the context to register an `@EventListener` handler method, so there is no `listener: received PO-42` line.
3. The first context is closed; the second context is created **fresh and independent** to avoid leftover bean state.
4. The second context scans both packages; Spring has an `OrderPlacedListener` bean, and `EventListenerMethodProcessor` processes the listener method during context refresh. Result: `listenerBeans=1`.
5. `OrderService.place("PO-43")` publishes the same `OrderPlaced` payload type and the listener prints `listener: received PO-43`.

The example intentionally creates no async executor, condition, or transaction; thus it isolates **the scanning cause**. If a real application uses a custom multicaster or transaction-bound listener, add the corresponding checks from the sections below.

## 4. Diagnostic Procedure: From "No Log Printed" to the Specific Cause

Do not change `@ComponentScan` immediately when no log appears. First determine **whether the listener is a Spring bean**. This is the most useful branching point.

### Step 1: Verify You Are Inspecting the Right ApplicationContext

An application may have parent/child contexts, test contexts, separate web contexts, or multiple started `SpringApplication` instances. A listener being a bean in **context A** does not prove an event published in **context B** will reach that listener.

In a Spring context hierarchy, events from a **child can propagate up to the parent**; events in the parent **are not automatically sent down to all children**. Do not assume two contexts form one global event bus.

Know which publisher was injected into the service and which beans belong to the corresponding context. In tests, ensure the producer and listener belong to **the same context or a valid event-propagation direction**.

### Step 2: Confirm Whether the Listener Bean Is Present

In a Spring-managed diagnostic component, you can check:

```java
String[] beans = applicationContext.getBeanNamesForType(
        OrderPlacedListener.class);
System.out.println("listener bean count=" + beans.length);
```

This is **illustrative code**; `applicationContext` and `OrderPlacedListener` are application objects/types. `getBeanNamesForType(...)` checks beans by type in the context, not classes on the filesystem.

Distinguish:

- **`0` beans:** the listener was not registered, was excluded by a condition, or lives in another context. Investigate `@ComponentScan`, `@Component`, `@Bean`, `@Profile`, `@Conditional...`.
- **`1` bean:** the bean exists. This does not yet guarantee the `@EventListener` method was registered, but **missing class scan** is no longer the primary conclusion.
- **Multiple beans:** the same listener may have been accidentally registered via both `@Component` and `@Bean`; risk of duplicate event handling. Inspect bean names/configuration.

Do not use `Class.forName("...OrderPlacedListener")` to prove a listener bean exists: a class being on the classpath **is different from** a bean being registered in `ApplicationContext`.

### Step 3: Identify the Scan Base Package

Check the package of the class with `@SpringBootApplication` or `@ComponentScan`, for example:

```java
@SpringBootApplication
public class StoreApplication {
}
```

If `StoreApplication` is in `com.acme.app`, compare the listener's package path:

```text
com.acme.app.listener.OrderPlacedListener      -> inside scan scope
com.acme.listeners.OrderPlacedListener         -> outside scan scope
```

In multi-module Maven/Gradle projects, also ensure the module containing the listener **has been added to the runtime classpath**. If the module JAR is missing from dependencies, changing base packages will not make Spring find the class.

### Step 4: Inspect Annotations and Filters

A scanned class must be a valid candidate. Example:

```java
@Component
public class OrderPlacedListener {
    @EventListener
    public void on(OrderPlaced event) {
        // ...
    }
}
```

This snippet is **not enough** on its own to guarantee the listener runs: you still need the right scan scope, active bean, matching event type, and valid lifecycle.

Look for:

- Missing `@Component`/`@Service` or missing `@Bean`/`@Import`?
- `@ComponentScan(useDefaultFilters = false)` missing required `includeFilters`?
- `excludeFilters` excluding by type/annotation/package?
- Custom stereotype not properly meta-annotated with `@Component`?
- `@Profile("prod")` while running with the `test` or `dev` profile?
- `@ConditionalOnProperty`, `@ConditionalOnBean`, feature flags, or other conditions filtering out the bean? These conditions typically live in Spring Boot.
- `@Lazy` on the bean containing `@EventListener`? Per Spring documentation, marking a listener bean lazy can prevent the listener method **from being registered** as expected, because the container respects lazy beans and does not instantiate them for listener registration.
- Bean initialization errors causing the whole context to fail before any events can be published?

If the class is present and the bean is registered yet the method still receives no events, do not stop at "scan error". Check the event processor/lifecycle/multicaster in the next steps.

### Step 5: Prove the Event Is Published and Has the Right Type

Add logging or a test at the publish site:

```java
System.out.println("publish OrderPlaced id=" + orderId);
applicationEventPublisher.publishEvent(new OrderPlaced(orderId));
```

This is **illustrative code**. A log line before `publishEvent` verifies code reaches the publisher call, **not that the listener finished running**. With the default synchronous `SimpleApplicationEventMulticaster`, matching listeners receive the event on the publisher thread; with `@Async` or a multicaster executor, the publisher may return before the listener even starts.

Check listener and payload types:

```java
@EventListener
public void handle(OrderPlaced event) {
    // Receives the exact OrderPlaced.
}
```

If the publisher sends `PaymentPlaced`, this listener has no reason to be called. For POJOs, Spring may wrap them in `PayloadApplicationEvent`; an `@EventListener` declaring the POJO type remains valid. However, a listener declaring a different wrapper type will not automatically match arbitrary payloads.

Also check `@EventListener(condition = "...")`: when the SpEL expression evaluates to false, the listener is **intentionally skipped**, not a scanning error. For generic events, sufficient type metadata must exist for Spring to distinguish them at runtime if the contract requires it.

### Step 6: Distinguish Standard Events from Transactional Events

A method:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderPlaced(OrderPlaced event) {
    // ...
}
```

is a **transaction-bound listener**, not equivalent to an immediate `@EventListener`. By default `fallbackExecution = false`: if there is no suitable transaction, the listener **does not run**, even when the bean was scanned properly and the publisher emitted the event.

Common phases:

| Phase | When the callback runs |
| --- | --- |
| `BEFORE_COMMIT` | Before the source transaction commits |
| `AFTER_COMMIT` | After a successful commit |
| `AFTER_ROLLBACK` | After rollback |
| `AFTER_COMPLETION` | After the transaction completes regardless of outcome |

For instance, in a `@Transactional` test that Spring automatically rolls back after the method, an `AFTER_COMMIT` listener **does not run** if the transaction never commits. Do not change scanning or enable `fallbackExecution = true` just to mask a broken transaction design.

With reactive transactions, the transaction context resides in **Reactor Context**, unlike the `ThreadLocal` of imperative transactions. When publishing transactional events in a reactive pipeline, follow the `TransactionalEventPublisher`/`TransactionContext` APIs; context propagation for logging does not automatically replace transaction propagation.

### Step 7: Check Timing, Async, and Exceptions

A regular listener bean is only created/registered at the appropriate stage of the context lifecycle. **Early Spring Boot startup events**, such as `ApplicationStartingEvent` or `ApplicationEnvironmentPreparedEvent`, fire before application beans are ready. Use `SpringApplication.addListeners(...)` or register an early listener via `META-INF/spring.factories` as supported by Spring Boot if you need to receive those early events.

With `@Async`:

- The listener may execute after the publisher log is printed and the request has completed.
- Exceptions on the worker do not automatically propagate back to the publisher thread. For `void` async methods, you may need an `AsyncUncaughtExceptionHandler` or proper logging/monitoring.
- ThreadLocal/MDC/trace context does not propagate automatically across all executors.
- Tests need a deterministic synchronization point; do not conclude "not scanned" merely because no log appeared after an arbitrary delay.

With a synchronous multicaster, if **the first listener throws an exception**, subsequent listeners may not be called. This can produce the symptom "listener B did not run", even though bean B actually exists. Check stack traces, `ErrorHandler`, and listener ordering when relevant.

## 5. How to Fix Scanning Properly in Multi-Module Projects

An application may be split into:

```text
store-app/                   <-- Spring Boot main
store-domain/                <-- OrderPlaced
store-notifications/         <-- OrderPlacedListener
store-data/                  <-- repositories
```

There are **two independent conditions**:

1. The `store-notifications` module must be present in the **runtime dependencies/classpath** of `store-app`.
2. The Java package containing `OrderPlacedListener` must be included in scanning, or the listener must be **registered explicitly**.

Illustrative Maven dependency (**groupId and artifactId are hypothetical for the project**):

```xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>store-notifications</artifactId>
    <version>1.0.0</version>
</dependency>
```

Adding the dependency alone is not always enough: if the JAR is loaded but the class lies outside the base scan, there is still no bean. Conversely, widening `scanBasePackages` alone does not help if the artifact is not on the classpath.

**A clean approach for intentional extension modules** is importing a `@Configuration` from the module into the application via `@Import`, for example:

```java
@Configuration
@Import(NotificationModuleConfiguration.class)
class StoreIntegrationConfiguration {
}
```

This snippet requires a real `NotificationModuleConfiguration` and imports for `@Configuration`/`@Import`; the imported configuration can declare the required listener `@Bean`. This is much clearer than scanning all packages of third-party libraries indiscriminately.

If there are multiple `ApplicationContext` instances across microservices, each service must register listeners in **its own context**. Spring in-process events **do not transmit events to another JVM**; cross-service messaging requires a broker/HTTP/outbox and dedicated contracts.

## 6. Diagnosing When the Bean Exists Yet the Listener Method Is Not Called

Scan failures are only one category of cause. A classification table:

| Evidence | Cause to check first |
| --- | --- |
| `getBeanNamesForType(OrderPlacedListener.class).length == 0` | Wrong component scan package, missing stereotype, conditional/profile, module missing from runtime dependency, wrong context |
| Bean exists but method never runs in flow | `@EventListener` annotation, method signature, lifecycle, lazy bean, custom configuration |
| Standard `@EventListener` runs, `@TransactionalEventListener` does not | Source transaction, phase, and `fallbackExecution` |
| Listener receives event A but not event B | Event type/generics, SpEL condition, publisher emitting B via another context |
| Listener logs arrive very late | `@Async`, executor queue, or custom multicaster |
| Publisher fails before expected listener runs | Another listener threw an exception, `ErrorHandler`, invocation order |
| Fails only when running JUnit | Different test slice/context packages, test transaction rollback, mock replacing real bean |
| Some listeners appear to fire twice | Duplicate bean registration, context hierarchy, code publishing the event multiple times |

Do not temporarily change all listeners to regular `@EventListener` or turn on `fallbackExecution = true` just to "make it run". Those changes can break invariants: a callback meant to run **only after commit** would now run before commit or outside any transaction.

### Using Spring Boot Actuator to Inspect Beans and Conditions

In Spring Boot applications with Actuator, endpoints like `/actuator/beans` and `/actuator/conditions` help inspect registered beans and configuration condition outcomes. **Endpoints may not be exposed by default**; configure management exposure according to security policy.

For development environments, you can use appropriate logging to observe component scanning:

```properties
logging.level.org.springframework.context.annotation=TRACE
```

This is **diagnostic configuration** that can produce heavy logging. Enable it only as narrowly as needed and turn it off afterward. Do not expose sensitive actuator endpoints publicly just to debug one listener.

The primary data to compare are **bean names/types in the actual running context**, not the number of classes found by your IDE in the project.

## 7. Writing Tests to Prevent Scan Regressions

### 7.1. Smoke Test for Bean Registration

In a Spring Boot integration test:

```java
@SpringBootTest
class EventListenerRegistrationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void listenerIsRegistered() {
        assertEquals(1,
                context.getBeanNamesForType(
                        OrderPlacedListener.class).length);
    }
}
```

This is **illustrative skeleton code**, requiring imports, JUnit 5/Spring Boot Test dependencies, and a concrete project. It confirms a bean of that **type** is present in the test's Spring context, without by itself proving events reach the method.

Note: `@SpringBootTest` and a test slice such as `@WebMvcTest` have **different bean-loading scopes**. A listener absent from a test slice context is not necessarily missing in production. Choose a test context that accurately represents the wiring under test.

### 7.2. Testing Both Publication and Listener Side Effects

A stronger smoke test should:

1. Start the context with the real configuration.
2. Assert the listener bean exists.
3. Call the service producing the event with the right payload.
4. Assert the listener produces the expected side effect, such as updating a fake sink/test counter.
5. If the listener is async or transaction-bound, wait for the appropriate completion point and verify the corresponding transaction outcome.

`@RecordApplicationEvents` from `spring-test` is very useful for checking **whether the event was published**:

```java
@SpringBootTest
@RecordApplicationEvents
class OrderEventTest {

    @Autowired
    OrderService service;

    @Test
    void publishesOrderPlaced(ApplicationEvents events) {
        service.place("PO-42");

        assertEquals(1L,
                events.stream(OrderPlaced.class).count());
    }
}
```

This is **illustrative integration code**, not standalone. The annotation and API belong to `org.springframework.test.context.event`. This assertion shows the matching event was **recorded by the test framework**, but does **not** confirm the business listener was scanned. Therefore, verify bean registration and side effects separately.

### 7.3. Plain Spring Framework Test from Section 3's Example

No Spring Boot is needed to test bean registration:

```java
try (var context = new AnnotationConfigApplicationContext(
        ServiceAndListenerConfig.class)) {

    assertEquals(1,
            context.getBeanNamesForType(
                    OrderPlacedListener.class).length);
}
```

This is **illustrative JUnit skeleton code**; besides the example's imports, it requires JUnit's `assertEquals`. It is well suited for guarding scan configurations in a library using Spring Framework directly.

### 7.4. Verifying Post-Commit Behavior

If a listener uses `@TransactionalEventListener(AFTER_COMMIT)`, a `@Transactional` test with default rollback **is not suitable for confirming the AFTER_COMMIT callback ran** solely via assertions inside the test body. You can use `TestTransaction.flagForCommit()`/`TestTransaction.end()` if a test-managed transaction is appropriate, or call the transactional service inside a test not wrapped in an outer transaction so the service genuinely commits.

Completing `repository.saveAndFlush(...)` does not mean the transaction has committed. Query post-commit state from another connection/transaction when needed.

## 8. Bad Fixes That Easily Cause New Problems

**Mistake 1 — Adding `@EventListener` to a method without registering the class as a bean.**  
Spring will not detect the method. Fix by adding a stereotype inside the proper scan scope or registering the bean explicitly.

**Mistake 2 — Adding `@Component` while the class sits outside the base package.**  
The annotation does not automatically expand `@ComponentScan`. Check the main class package or declare scan packages intentionally.

**Mistake 3 — Configuring `@ComponentScan("com")` or the default package just to "scan everything".**  
Can activate too many beans, cause name/condition conflicts, and slow down startup. Scan only the application's root package or known modules.

**Mistake 4 — Forgetting the module runtime dependency.**  
The IDE finds sources across a multi-module project, yet the built artifact lacks the listener class on the runtime classpath.

**Mistake 5 — Registering the listener twice.**  
`@Component` is scanned, while a `@Bean` method also returns another instance or `@Import` creates a duplicate definition; a single event can trigger two listeners.

**Mistake 6 — Confusing conditionals/profiles with a scan failure.**  
The class is inside the scan scope, but `@Profile` or `@Conditional...` excludes the bean. Read the condition evaluation report and active profiles before changing packages.

**Mistake 7 — Confusing lazy initialization with event method registration.**  
A `@Lazy` listener bean may not be instantiated to register `@EventListener` as expected. Do not mark listeners handling critical events as lazy without understanding the lifecycle.

**Mistake 8 — Ignoring events that fire before context refresh.**  
Normal listeners are beans and therefore absent during early Spring Boot startup events. Register an early `ApplicationListener` before `run()` for that group of events.

**Mistake 9 — Enabling `fallbackExecution=true` to "patch" a non-running transactional listener.**  
Changes semantics: callbacks may now run outside a transaction even though the requirement was post-commit only.

**Mistake 10 — Confusing an unpublished event with an unscanned listener.**  
A log line saying "service started" does not prove the `publishEvent` branch executed; inspect the call path and use an appropriate recorder/test.

**Mistake 11 — Waiting a couple seconds and concluding an async listener does not exist.**  
The task may be queued or failing on the executor. Inspect completion, executor metrics, error handlers, and correlation IDs.

**Mistake 12 — Changing one component scan and inadvertently affecting repositories/entities in another module.**  
Component scanning and JPA/Spring Data scanning mechanisms are not completely identical. Always run integration tests covering related beans.

## 9. Incident Handling Workflow

When a bug is reported as "event published but handler did not run", proceed in least-invasive order:

1. **Confirm the publish call:** was `ApplicationEventPublisher.publishEvent(...)` actually called? What is the payload type?
2. **Identify the contexts:** which contexts do producer and listener belong to; is there a hierarchy?
3. **Verify bean registration:** check `getBeanNamesForType(...)` or Actuator beans in the failing environment.
4. **If the bean is missing:** check root package, `@Component`/`@Bean`/`@Import`, module classpath, filters, profile/condition, and lazy beans.
5. **If the bean exists:** check `@EventListener` method, signature, type, condition, lifecycle, and runtime exceptions.
6. **If `@TransactionalEventListener`:** confirm transaction context and phase; do not assume publication implies commit.
7. **If async:** inspect executor, queue, completion, and exception handler; add trace/event IDs to link publisher and listener.
8. **Pick the smallest fix:** move the main package, declare targeted scan packages, or import configuration instead of opening project-wide scanning.
9. **Add a regression test:** assert bean presence **and** observe event handling, plus transaction outcome if applicable.
10. **Verify in real runtime:** after deployment, verify the actual context and bean graph, not just IDE results or mocked unit tests.

If business data must be processed durably, remember that **Spring `ApplicationEventPublisher` is not a message broker**. Fixing component scanning enables listeners to receive events **in-process**, but does not add persistence, retries, an outbox, or cross-service delivery.

## 10. Self-Check Questions

**1. A method has `@EventListener` but the class lacks `@Component`; does Spring automatically register the class?**  
No. `@EventListener` is not a class stereotype. If not using component scanning, register the class via `@Bean` or `@Import`.

**2. The class has `@Component` yet still receives no events; what should you check first?**  
The context's base scan packages, active profiles/conditions, and whether the bean actually exists in `ApplicationContext`. Do not guess from source files alone.

**3. `StoreApplication` is in `com.acme.app`, and the listener is in `com.acme.listeners`. Does Spring Boot scan the listener by default?**  
No. It is a sibling package, not beneath `com.acme.app`. Move the main class to a common root package, expand scanning intentionally, or register the bean explicitly.

**4. `applicationContext.getBeanNamesForType(...)` returns 1 yet the listener does not run; can you still conclude a missing scan?**  
You should not. The bean already exists. Check event type, condition, lifecycle, transaction phase, async, or another listener throwing an exception.

**5. `@TransactionalEventListener(AFTER_COMMIT)` does not run when published outside a transaction. Is it definitely an unscanned listener?**  
No. Because `fallbackExecution` defaults to false, the callback is skipped when no suitable transaction exists.

**6. Can Spring Boot's `ApplicationStartingEvent` be reliably received by a normal `@Component` bean?**  
No. That event fires very early before application beans are created; you must register an early listener using the appropriate Boot mechanism.

**7. Why shouldn't a test asserting only that `@RecordApplicationEvents` captured an event be used to conclude the listener was scanned?**  
The recorder verifies **publication**; the business listener can be completely absent while the event is still published and recorded.

**8. If the listener lives in a dependency JAR yet is still not scanned, what else must be checked?**  
The bean must fall within the proper base scan and satisfy stereotypes/filters/conditions. Having the JAR on the classpath is necessary but not sufficient.

## 11. Official Documentation

- [Spring Framework 6.2 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html)
- [Spring Framework 6.2 — Annotation-based Event Listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2.9 Javadoc — EventListener](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework 6.2.9 Javadoc — EventListenerMethodProcessor](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/EventListenerMethodProcessor.html)
- [Spring Boot 3.3 — Structuring Your Code / Locating the Main Application Class](https://docs.spring.io/spring-boot/3.3/reference/using/structuring-your-code.html)
- [Spring Boot — Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-events-and-listeners)
- [Spring Framework — Testing Application Events](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html)

