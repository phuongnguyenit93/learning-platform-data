# Registering Early Listeners with SpringApplication.addListeners

## 1. The Problem: A Listener Created After an Event Cannot Receive That Event

In Spring Boot, application events (`ApplicationEvent`) help observe bootstrap phases and react when a key milestone occurs. However, not every event is published **after Spring has created the `ApplicationContext` and application beans**.

For example, `ApplicationStartingEvent` is published very early in `SpringApplication.run(...)`, even before `Environment` preparation. If you only write a bean to receive the event:

```java
@Component
public class TooLateListener {

    @EventListener(ApplicationStartingEvent.class)
    public void onStarting() {
        System.out.println("Starting");
    }
}
```

then this method **will not receive `ApplicationStartingEvent` for the current startup run**, because the bean and `@EventListener` processing have not been created/registered yet when that event occurs.

To observe very early events, register an `ApplicationListener` **directly on the `SpringApplication` instance before calling `run(args)`**:

```java
SpringApplication application = new SpringApplication(MyApplication.class);

application.addListeners(
        (ApplicationListener<ApplicationStartingEvent>) event ->
                System.out.println("Application starting bootstrap"));

application.run(args);
```

This is an **illustrative integration snippet**: `MyApplication` is the project's configuration/startup class, and you must import `SpringApplication`, `ApplicationListener`, and `ApplicationStartingEvent` appropriately. A complete runnable example is in Section 6.

**Important rule:** choose a listener suited to **when the event is published** and **what resources actually exist** at that moment. `addListeners(...)` solves early registration; it **does not make `ApplicationContext` or business services appear any earlier**.

## 2. What Does addListeners(...) Actually Do?

API in `org.springframework.boot.SpringApplication`:

```java
public void addListeners(ApplicationListener<?>... listeners);
```

This method accepts **one or more** implementations of `org.springframework.context.ApplicationListener<?>` (varargs) and adds them to the listeners `SpringApplication` uses during startup, while also registering them with the `ApplicationContext` once the context is created.

Three things to distinguish:

1. **Registers listeners**, does not publish events. Events are published only when `SpringApplication.run(...)` reaches the corresponding phase.
2. **Adds listeners**, does not replace the whole list. The `setListeners(Collection<? extends ApplicationListener<?>>)` method sets/resets the listener collection; avoid accidentally replacing the list and losing other listeners.
3. **Registers with `SpringApplication`**, which does not mean the listener object is **created by Spring as a bean with dependency injection**. A listener you instantiate with `new` can receive early events, but you cannot expect `@Autowired` on it to inject services that do not exist yet.

Example adding multiple listeners for different event types:

```java
SpringApplication app = new SpringApplication(MyApplication.class);

ApplicationListener<ApplicationStartingEvent> starting =
        event -> System.out.println("starting");

ApplicationListener<ApplicationReadyEvent> ready =
        event -> System.out.println("ready");

app.addListeners(starting, ready);
app.run(args);
```

This is **illustrative code to place in `main`**; it requires imports and a real source class. Because the varargs parameter is `ApplicationListener<?>...`, differently typed listeners can be passed in the same call.

**Required timing:** call `addListeners` **before `run`** if you need the earliest bootstrap events. If called after `run` has returned, the early events of that startup run have already occurred; adding a listener to `SpringApplication` then **does not replay** event history.

## 3. Spring Boot Events and Available Resources at Each Milestone

Spring Boot 3.3 publishes key events in the following order during `SpringApplication.run(...)`:

| Order | Event | Resources/state | What the listener should do |
|---|---|---|---|
| 1 | `ApplicationStartingEvent` | Just started; `Environment` and `ApplicationContext` not prepared yet | Record a very early marker, read arguments, set up appropriate bootstrap observation |
| 2 | `ApplicationEnvironmentPreparedEvent` | `ConfigurableEnvironment` available, context not created yet | Observe/influence the environment with awareness of listener order and property sources |
| 3 | `ApplicationContextInitializedEvent` | Context created and initializers have run; application bean definitions not loaded yet | Observe initial context state |
| 4 | `ApplicationPreparedEvent` | Primary bean definitions loaded, context not `refresh`ed yet | Diagnose before refresh; do not rely on initialized business singletons |
| 5 | `ApplicationStartedEvent` | Context refreshed, runners not called yet | Observe the started milestone and normally initialized beans |
| 6 | `AvailabilityChangeEvent` with `LivenessState.CORRECT` | Notifies that the application is considered live | Observe liveness when needed |
| 7 | `ApplicationRunner` / `CommandLineRunner` | Runners execute; these are **not** ApplicationEvents | Perform initialization work that must complete before ready |
| 8 | `ApplicationReadyEvent` | Runners have been called and completed successfully | Observe completion of the startup sequence |
| 9 | `AvailabilityChangeEvent` with `ReadinessState.ACCEPTING_TRAFFIC` | Notifies default ready state | Observe readiness |

`ApplicationFailedEvent` is published **when startup encounters an exception**; it is not a mandatory success milestone at the end of the sequence. If the failure occurs very early, this event's `ApplicationContext` **can be `null`**.

Beyond the table, there are also Spring Framework's `ContextRefreshedEvent` and, for applicable web applications, `WebServerInitializedEvent`. These occur during context refresh and should not be confused with `ApplicationReadyEvent`.

Two milestones learners often confuse:

- **`ApplicationStartedEvent`:** the context has refreshed, but `ApplicationRunner` and `CommandLineRunner` have not run yet.
- **`ApplicationReadyEvent`:** published after the runners; this is a later milestone. In the default flow, the readiness change to `ACCEPTING_TRAFFIC` is published right after the Ready event.

Registering an early listener with `addListeners(...)` allows an appropriate listener to observe **both early and late events**. It does not turn those events into callbacks with identical resource availability.

### The Earliest Milestone Has No ApplicationContext

`ApplicationStartingEvent` holds bootstrap details such as `SpringApplication` and `String[] args`, but **does not** provide a refreshed application context. Do not call `event.getApplicationContext()` on an event that does not have that method, and do not instantiate business services yourself just to run business logic here.

At `ApplicationEnvironmentPreparedEvent`, you already have:

```java
ConfigurableEnvironment env = event.getEnvironment();
```

However, when a listener receives this event, how complete each property source is still depends on the order of listeners and environment processors. In particular, do not assume every external configuration has already been loaded in final order for an arbitrary listener based solely on the event's name. If you need to **add early configuration sources to influence bean creation**, `EnvironmentPostProcessor` usually expresses that responsibility more clearly.

## 4. Standard and Safe Ways to Register Typed Listeners

### Approach A — Lambda for a Single Event Type

When only one event is needed, a lambda is concise and explicitly typed:

```java
SpringApplication app = new SpringApplication(MyApplication.class);

ApplicationListener<ApplicationStartingEvent> listener = event -> {
    System.out.println("Argument count: " + event.getArgs().length);
};

app.addListeners(listener);
app.run(args);
```

`getArgs()` belongs to `SpringApplicationEvent` and returns the arguments used for the run. This **does not** mean an `ApplicationArguments` bean exists yet; at Starting, there are no context-managed beans.

You can also pass a cast listener directly into `addListeners`:

```java
app.addListeners(
        (ApplicationListener<ApplicationStartingEvent>) event -> {
            System.out.println("Starting: " + event.getArgs().length);
        });
```

Keep the exact generic `ApplicationListener<ApplicationStartingEvent>`. If you use a lambda without a clear target type, Java may not infer the event type as expected.

### Approach B — A Separate Listener Class

Suitable when error handling, multiple steps, and unit tests are needed:

```java
package com.example.listener;

import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public final class StartingTraceListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("Bootstrap args: " + event.getArgs().length);
    }
}
```

Register in `main`:

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners(new StartingTraceListener());
app.run(args);
```

`StartingTraceListener` can be instantiated with a normal Java constructor without `@Component`. It runs very early, so it **should not depend on Spring services or a database already being created**.

### Approach C — Multiple Event Types with ApplicationListener<ApplicationEvent>

A listener can implement `ApplicationListener<ApplicationEvent>` and dispatch using `instanceof`. This is very useful when printing **a single timeline** from Starting to Ready within one run. Because it accepts many Spring `ApplicationEvent` subtypes, it may be called for unrelated events as well; handle only the required types and ignore the rest.

Note: `ApplicationListener<ApplicationEvent>` differs from `ApplicationListener<ApplicationStartingEvent>`. The first has a broad scope; the second fits only one event. Do not use a broad generic unnecessarily when the goal is a single narrow callback.

## 5. Why Listeners Declared with @Bean/@Component/@EventListener Are Usually Too Late

Example:

```java
@Component
public class StartingListenerBean {

    @EventListener(ApplicationStartingEvent.class)
    public void tooLate() {
        System.out.println("Does not appear during normal startup");
    }
}
```

Spring only discovers beans and registers `@EventListener` methods during context creation/refresh. By that time `ApplicationStartingEvent` has already been published. Spring **does not store a history of all startup events to replay automatically** for newly appearing listeners.

The same applies to an `ApplicationListener<ApplicationEnvironmentPreparedEvent>` bean:

```java
@Bean
ApplicationListener<ApplicationEnvironmentPreparedEvent> environmentListener() {
    return event ->
            System.out.println("Environment observed");
}
```

This `ApplicationListener` bean will be created **after** the current bootstrap's EnvironmentPrepared event, so it is not an early enough registration approach for that event.

**However, do not conclude that bean listeners are useless.** For `ApplicationReadyEvent` or events after context refresh, bean listeners or `@EventListener` methods are very suitable and also benefit from dependency injection.

Quick selection table:

| Need | Preferred registration approach | Why? |
|---|---|---|
| Observe `ApplicationStartingEvent` | `SpringApplication.addListeners(...)` before `run` | Beans do not exist yet |
| Observe `ApplicationEnvironmentPreparedEvent` | `addListeners(...)`, builder, or `spring.factories` | Context not created yet |
| Observe very early context initialization milestones | `addListeners(...)` | Registered before refresh |
| Use services in `ApplicationReadyEvent` | `@EventListener` bean / listener bean | Context and services are already created |
| Catch startup errors, including before context creation | Early-registered listener for `ApplicationFailedEvent` | Does not assume beans exist |
| Run business work that must finish before ready | `ApplicationRunner` or `CommandLineRunner` | Can use services and reflects the ready milestone |
| Modify property sources before bootstrap | `EnvironmentPostProcessor` | Dedicated to Environment handling |

A manually registered listener can still receive Ready. However, if the goal requires accessing a Spring repository/service at Ready, using a listener bean is usually easier to manage thanks to standard constructor injection.

## 6. Complete Java 17+ / Spring Boot 3.3 Example: Tracking Events Before and After Context

The hands-on exercise below actually uses `SpringApplication.addListeners(...)` **before `run`**, observes event ordering, compares against a bean `@EventListener` method, and tests a failed startup branch. No HTTP server, database, or dependency beyond the Spring Boot starter is needed.

### 6.1. Project Structure

```text
early-listener-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/earlylistener/
    ├── EarlyListenerApplication.java
    └── BootTimelineListener.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'early-listener-demo'
```

**`build.gradle`** (Gradle Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

This example targets Spring Boot **3.3.x** and Java 17+. If you already have a Spring Boot project, keep the dependency/plugin versions managed by your project. Running `./gradlew`/`gradlew.bat` requires an existing Gradle Wrapper (e.g., from a project generated by Spring Initializr); Wrapper files do not appear automatically just by writing `build.gradle`.

### 6.2. Early-Registered Listener Receiving Multiple Event Types

**`src/main/java/com/example/earlylistener/BootTimelineListener.java`:**

```java
package com.example.earlylistener;

import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;

public final class BootTimelineListener
        implements ApplicationListener<ApplicationEvent> {

    @Override
    public void onApplicationEvent(ApplicationEvent event) {
        if (event instanceof ApplicationStartingEvent) {
            System.out.println("00. ApplicationStartingEvent");
        } else if (event instanceof ApplicationEnvironmentPreparedEvent e) {
            System.out.println("01. Environment available = "
                    + (e.getEnvironment() != null));
        } else if (event instanceof ApplicationContextInitializedEvent e) {
            System.out.println("02. Context initialized = "
                    + (e.getApplicationContext() != null));
        } else if (event instanceof ApplicationPreparedEvent) {
            System.out.println("03. ApplicationPreparedEvent");
        } else if (event instanceof ApplicationStartedEvent) {
            System.out.println("04. ApplicationStartedEvent");
        } else if (event instanceof ApplicationReadyEvent) {
            System.out.println("06. ApplicationReadyEvent (early listener)");
        } else if (event instanceof ApplicationFailedEvent e) {
            System.out.println("FAIL. ApplicationFailedEvent: "
                    + e.getException().getClass().getSimpleName());
            System.out.println("FAIL. Context exists = "
                    + (e.getApplicationContext() != null));
        }
    }
}
```

The `instanceof` branches with pattern variable `e` are valid Java 17 syntax. The listener only prints messages; it **does not call `getBean` and needs no DI** during bootstrap. If it encounters another `ApplicationEvent`, the method prints nothing. Specifically, the Failed branch reads the exception from `getException()` and checks the context for `null` before using it: if an error happens very early, the context may not have been created yet.

### 6.3. SpringApplication Registering the Listener Before Run

**`src/main/java/com/example/earlylistener/EarlyListenerApplication.java`:**

```java
package com.example.earlylistener;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class EarlyListenerApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(EarlyListenerApplication.class);

        // Select a non-web app so the exercise does not open an HTTP port.
        application.setWebApplicationType(WebApplicationType.NONE);

        // Key point: must register BEFORE application.run(args).
        application.addListeners(new BootTimelineListener());

        try (ConfigurableApplicationContext context =
                application.run(args)) {
            // At this point the runner and ApplicationReadyEvent have been handled.
        }
    }

    @Bean
    ApplicationRunner startupTask() {
        return arguments -> {
            System.out.println("05. ApplicationRunner");

            if (arguments.containsOption("demo.fail")) {
                throw new IllegalStateException("demo startup failure");
            }
        };
    }

    // This method is on a bean, so it only catches late-stage events.
    @EventListener(ApplicationReadyEvent.class)
    public void readyFromBean() {
        System.out.println("06. ApplicationReadyEvent (@EventListener bean)");
    }
}
```

The `@EventListener(ApplicationReadyEvent.class)` method belongs to the application configuration bean and is discovered by Spring when the context initializes. Both the early-registered listener and the bean method **can** receive Ready, though the relative order between **two callbacks for the same event type** is not pinned down by default in this lesson.

Reason for `try-with-resources`: in a non-web demo, it closes the context right after `run` to clean up resources. In a real web server, do not close the context right after startup if the goal is to keep serving HTTP traffic.

### 6.4. Running the Example

Linux/macOS inside the directory with a Wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

The lines **printed by the example code itself** will appear in the following milestone sequence (Spring Boot/Gradle may print banners and logs in between):

```text
00. ApplicationStartingEvent
01. Environment available = true
02. Context initialized = true
03. ApplicationPreparedEvent
04. ApplicationStartedEvent
05. ApplicationRunner
06. ApplicationReadyEvent (early listener)
06. ApplicationReadyEvent (@EventListener bean)
```

**Exception regarding the order of the last two lines:** because both listeners handle the **same `ApplicationReadyEvent`**, the two lines starting with `06.` may appear in reverse order. What is deterministic here is the sequence **Starting → EnvironmentPrepared → ContextInitialized → Prepared → Started → Runner → Ready**; not the priority order between two callbacks for the same event.

Why does the output prove `addListeners` registered early enough?

- Lines **00** and **01** are printed when the context does not exist yet, so a bean listener created during refresh could not have produced those two lines.
- Line **02** proves `ConfigurableApplicationContext` exists, though full bean definitions have not been loaded yet.
- Line **04** runs before the runner; line **05** is the runner; lines **06** appear only after the runner finishes.
- Both Ready lines show that the listener attached to `SpringApplication` **continues working in late phases**, alongside the bean-based listener.

### 6.5. Testing a Failed Startup

Because the example includes an `ApplicationRunner` with a failure branch, you can run:

```bash
./gradlew bootRun --args='--demo.fail'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--demo.fail"
```

In this scenario:

- Starting, EnvironmentPrepared, ContextInitialized, Prepared, and Started have already occurred before the runner executes.
- The runner prints `05. ApplicationRunner` and then throws `IllegalStateException`.
- Spring Boot publishes `ApplicationFailedEvent`; the early-attached listener can record the error and whether the context exists.
- **There is no `ApplicationReadyEvent` for that failed run**, because the runner did not complete successfully.
- The Gradle `bootRun` task normally reports build/task failure because the application JVM exits unsuccessfully. Read the root stack trace to see the actual cause.

A log excerpt from the listener in the failure branch may look like:

```text
04. ApplicationStartedEvent
05. ApplicationRunner
FAIL. ApplicationFailedEvent: IllegalStateException
FAIL. Context exists = true
```

The log above illustrates the key points in an **intentional runner failure case**; other lines, log timing, and how Spring reports exceptions depend on the environment. If the failure occurs earlier than context creation, `FAIL. Context exists` can be `false`.

**Do not rely on a Failed listener to guarantee access to repositories, data sources, or services from the context.** Bootstrap error handling must cope even when beans have not been initialized.

## 7. Distinguishing addListeners from Other Listener Registration Approaches

### 7.1. SpringApplicationBuilder.listeners(...)

When using the builder, you can perform equivalent early registration:

```java
new SpringApplicationBuilder(EarlyListenerApplication.class)
        .web(WebApplicationType.NONE)
        .listeners(new BootTimelineListener())
        .run(args);
```

This is an **alternative bootstrap option** and should not be run simultaneously with the `main` from Section 6. It requires importing `org.springframework.boot.builder.SpringApplicationBuilder`, `WebApplicationType`, and the listener class. The builder is convenient when you need a fluent configuration chain or parent/child context hierarchies.

### 7.2. META-INF/spring.factories for Automatic Registration

If you develop a library that needs to observe bootstrap events of **every application** using it, you cannot require every application to call `addListeners(...)` in `main`. Spring Boot 3.3 supports listener registration via `spring.factories`.

Place **`src/main/resources/META-INF/spring.factories`**:

```properties
org.springframework.context.ApplicationListener=com.example.earlylistener.BootTimelineListener
```

Because `BootTimelineListener` in the example has a default no-arg constructor, Spring Boot can instantiate it when loading listeners from factories. When testing this approach, **remove `application.addListeners(new BootTimelineListener())`** so you do not register the same logic through two paths and clutter the output.

A real library must ensure the listener class and the `META-INF/spring.factories` resource are packaged in the JAR. This is a **Spring Boot classpath extension mechanism**, not a claim that `@ComponentScan` can discover every early listener. In Spring Boot 3.3, the key for `ApplicationListener` remains `org.springframework.context.ApplicationListener`.

### 7.3. @Component, @Bean, and @EventListener

Spring bean-based mechanisms remain the natural choice **when events arrive after context initialization**:

```java
@Component
public class ReadyNotification {

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("Application ready");
    }
}
```

This is a **separate illustrative class** requiring imports for `Component`, `EventListener`, and `ApplicationReadyEvent`, placed in a scanned package. It differs from bootstrap listeners in that Spring can use DI inside the bean.

If you only want to handle `ApplicationReadyEvent` using a Spring-injected service, a bean listener is usually simpler than instantiating a listener in `main` and trying to fetch services before the right lifecycle point.

### 7.4. addListeners and addInitializers Are Not the Same Type of Hook

`SpringApplication.addInitializers(...)` accepts `ApplicationContextInitializer<?>`, used to customize the context **after the context is created but before refresh**. `addListeners(...)` accepts `ApplicationListener<?>`, used to **listen for events** across multiple milestones.

Comparison:

```java
SpringApplication app = new SpringApplication(MyApplication.class);

app.addInitializers(context ->
        System.out.println("Initializer: context already exists"));

app.addListeners(
        (ApplicationListener<ApplicationStartingEvent>) event ->
                System.out.println("Listener: context does not exist yet"));

app.run(args);
```

This is integration code, not a standalone project; it requires appropriate imports and a source class. The difference lies in the *input object* and *lifecycle*: initializers operate on the context, whereas a Starting listener cannot use the context.

If you need to modify property sources very early, consider `EnvironmentPostProcessor`; if you need to register bean definitions, consider a context initializer or an appropriate registry post-processor. Listeners are not a universal tool for every form of customization.

## 8. Do Bootstrap Listeners Receive Dependency Injection?

A situation that easily causes misunderstanding:

```java
public class WrongEarlyListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Autowired
    private PaymentService paymentService;

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        paymentService.pay();  // Likely null or invalid!
    }
}
```

This snippet only illustrates **misuse**, not runnable example code: `PaymentService`, `@Autowired`, and imports are omitted. The issue is not merely the `@Autowired` annotation; even if you instantiate it yourself later, **at Starting time no PaymentService bean has been initialized by the container**. A listener you create via `new WrongEarlyListener()` does not become a Spring-managed bean either.

A better design is **separation of responsibilities**:

- **Early listener:** record startup metadata, arguments, or process foundational information independent of beans.
- **EnvironmentPostProcessor / initializer:** configure the environment/context with dedicated APIs at the right milestone.
- **ApplicationRunner or @EventListener(ApplicationReadyEvent.class) bean:** use dependency-injected services to execute business logic at late milestones.

If you need to pass non-Spring data from `main` into an early listener, use constructor injection **in plain Java**:

```java
public final class BootstrapTagListener
        implements ApplicationListener<ApplicationStartingEvent> {

    private final String tag;

    public BootstrapTagListener(String tag) {
        this.tag = tag;
    }

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("Bootstrap tag: " + tag);
    }
}
```

Then:

```java
app.addListeners(new BootstrapTagListener("batch-worker"));
```

These two snippets are illustrative code requiring Spring imports; `tag` is supplied by `main` when instantiating the listener, **not a Spring bean injected from the context**.

## 9. Which Thread Calls Listeners? Should They Perform Heavy Work?

Spring Boot generally publishes startup events to listeners via Spring Framework's event mechanism; in the default configuration, callbacks usually run **synchronously on the event-publishing thread** (typically the startup thread). This directly impacts performance and safety.

If a Starting callback executes:

```java
Thread.sleep(10_000);
```

subsequent bootstrap work can be delayed by about 10 seconds. This snippet **only illustrates the impact of a blocking operation**, not a recommendation to run `sleep` in a listener; in real Java code you would have to handle `InterruptedException`.

Things you should not do in an early listener:

- Make synchronous HTTP/database calls without timeouts, slowing or hanging the system before logging is fully initialized.
- Use `@Autowired` to fetch services before the context exists.
- Rely on `Environment` or beans at the `ApplicationStartingEvent` milestone.
- Turn a listener into a background worker by spawning unmanaged threads and ignoring shutdown/error handling.
- Throw exceptions as normal control flow without understanding their impact on startup.

When work **must complete before the application is ready**, `ApplicationRunner`/`CommandLineRunner` usually provides clearer boundaries and safer service usage. When work must execute **after ready**, choose an appropriate hook and async/scheduling mechanism for the requirement. Either way, manage timeouts and idempotency/repeatability.

### How Does Using System.out Very Early Differ from Using a Logger?

`ApplicationStartingEvent` occurs before application logging is fully configured. `System.out.println` in this exercise lets learners see milestones simply. In real applications, if very early bootstrap logging is needed, use Spring Boot's supported logging mechanism or deferred logging strategy rather than assuming every logger already follows its final configuration at Starting.

Also never log secrets, tokens, passwords, or full CLI arguments. `event.getArgs()` can contain sensitive values in some deployments; the example here prints only the **argument count**.

## 10. Listener Ordering, Duplication, and Multi-Context Applications

### 10.1. Ordering Between Events vs. Ordering Between Listeners

Spring Boot guarantees the order of **lifecycle event milestones** along the standard startup path. However, if there are **multiple listeners for the same event type**, their callback order can depend on `Ordered` priority, `@Order`, registration mechanism, and the event-publishing infrastructure.

A custom listener can implement `Ordered`:

```java
public final class FirstStartingListener
        implements ApplicationListener<ApplicationStartingEvent>, Ordered {

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("Early observer");
    }
}
```

This is an illustrative class requiring imports for `ApplicationListener`, `Ordered`, and `ApplicationStartingEvent`. `HIGHEST_PRECEDENCE` sets a very high priority relative to other listeners in the same sorting mechanism, but **does not** make `ApplicationReadyEvent` occur before `ApplicationStartedEvent`. Nor should you pick the highest precedence arbitrarily and accidentally run before required Spring Boot infrastructure.

### 10.2. Avoid Registering the Same Logic Through Multiple Mechanisms

Suppose you both call:

```java
app.addListeners(new BootTimelineListener());
```

and declare the same class in `META-INF/spring.factories`. That risks creating **two separate listener instances** and receiving duplicate logs or execution. Do not rely on the listener collection automatically merging two different instances by class.

If an action has side effects, running twice can cause bugs. Pick one appropriate registration path or design callbacks to be idempotent when necessary.

### 10.3. Parent/Child ApplicationContexts

In a `SpringApplicationBuilder.parent(...).child(...)` hierarchy or multi-context system, an event can be **published or propagated** from child to ancestor. A listener may receive **multiple events of the same type**, even with certain milestones emitted from multiple contexts.

Do not use a listener to infer "the application lifetime has exactly one ApplicationReadyEvent" across all architectures. If a listener handles a specific context, it can compare `event.getApplicationContext()` against the expected context **on event types that actually provide that method**. At `ApplicationStartingEvent`, no context exists yet, so that comparison does not apply.

This also relates to hot restarts in development environments: each restart is a new lifecycle, not necessarily the system replaying the same event to old listeners in every case.

## 11. Common Mistakes and Diagnostics

| Symptom | Possible cause | Fix / verification |
|---|---|---|
| `@EventListener(ApplicationStartingEvent.class)` listener prints nothing | Bean was created after Starting was published | Register with `SpringApplication.addListeners(...)` before `run` or use `spring.factories` |
| `ApplicationListener<ApplicationEnvironmentPreparedEvent>` declared via `@Bean` does not work | Bean does not exist yet when event arrives | Switch to early bootstrap registration |
| Listener exists but does not receive the first event | `addListeners(...)` called too late, or wrong event generic | Move registration before `run`; check listener type |
| Listener fails with missing bean or `NullPointerException` | Trying to use service/context too early, or using `new` while expecting `@Autowired` | Keep early callbacks bean-independent; move business logic to runner/ready |
| Calling `getApplicationContext()` during Starting | Event type does not provide context | Use each event's actual API; avoid invalid casts |
| Handling Failed when `getApplicationContext()` is null | Failure occurred before context creation | Write a null-safe branch; use the exception to diagnose |
| Event log appears twice | Registered in both main and factories, or multiple contexts | Check all registration paths, classloaders/contexts, and propagation |
| Log order between two listeners varies across runs | Multiple callbacks on same event with varying registration/priority | Use `Ordered` when truly needed and verify within the same context |
| Slow listener slows down startup | Synchronous callback performing I/O or `sleep` | Minimize bootstrap work; use an appropriate runner/service |
| Listener throws exception and app fails to start | Unhandled exception in bootstrap path | Read stack trace; fail fast only with clear reason |
| Ready not received after Started | Runner threw an exception or has not finished | Check `ApplicationRunner`/`CommandLineRunner` and startup errors |
| Event listener appears not to run | Spring Boot logging not configured yet or log level filtered | Place reliable verification markers; inspect logging config and timing |
| Using `setListeners(...)` and losing other listeners | Replaced instead of adding to the listener set | Use `addListeners(...)` or manage the configured set carefully |

Short troubleshooting checklist:

1. **Identify the event type**: Starting, EnvironmentPrepared, Initialized, Prepared, Started, Ready, or Failed.
2. **Identify when the listener was registered**: before `run` or after beans were created?
3. **Identify what data the callback accesses**: args, Environment, context, beans, or ready system.
4. **Identify registration scope**: once in main, factories, builder, bean, or multiple contexts.
5. **Check exceptions and logs**: an early callback error can fail bootstrap; do not treat missing Ready logs as proof that the listener itself was wrong.
6. **Check API versions and imports**: use modern Spring Boot's `ApplicationStartingEvent`, not startup event examples from very old Spring Boot versions.

## 12. Step-by-Step Practice

Use the `early-listener-demo` project from Section 6, keeping the original code intact before each experiment.

**Exercise 1 — confirm early registration.** Run the original version. Verify that milestones `00, 01, 02, 03` appear before `04` and `05`. Explain why those initial milestones cannot be observed by an `@EventListener` bean created in the context.

**Exercise 2 — move the listener to a bean.** Remove `application.addListeners(new BootTimelineListener())` and try declaring `@Bean BootTimelineListener` in the `@SpringBootApplication` class. Observe that the early milestones are no longer printed by this listener, yet it can still receive late events after the bean is created. Do not confuse this with `BeanPostProcessor` "dropping" events.

**Exercise 3 — catch only one event.** Write an `ApplicationListener<ApplicationStartingEvent>` lambda and register it with `addListeners(...)`. Compare the number of callbacks invoked with the broad `ApplicationListener<ApplicationEvent>` implementation in the main lesson.

**Exercise 4 — move the callback to the factories path.** Create `META-INF/spring.factories` per Section 7. Remove the `main` registration line and run again, verifying that early events are still logged. Explain the advantage for library code.

**Exercise 5 — test startup failure.** Run `bootRun --args='--demo.fail'`. Verify `ApplicationFailedEvent` occurs and `ApplicationReadyEvent` does not. Explain why a Failed listener must handle a potentially null context for errors occurring earlier than the runner.

**Exercise 6 — test long-running work in the runner.** Add a controlled wait inside the runner; observe that Ready arrives after the runner finishes. Handle interruption if using `Thread.sleep`. Do not move a long wait into Starting just to see the first log line early.

**Exercise 7 — test duplicate registration.** Try registering a listener via both factories and `main` in a test build; observe that the callback can run multiple times. Restore a single registration path before going to production.

### Self-Check Questions

1. Why does `@EventListener(ApplicationStartingEvent.class)` on a bean miss Starting for the current run?
2. **Before which milestone** must `addListeners(...)` be called?
3. Does `ApplicationStartingEvent` allow using `Environment` or `@Autowired` services yet?
4. What is the difference between `addListeners(...)` and `addInitializers(...)`?
5. Why is `ApplicationStartedEvent` not synonymous with `ApplicationReadyEvent`?
6. If a runner throws an exception, which event can an early listener receive and why does it not receive Ready?
7. When should you choose `META-INF/spring.factories` instead of modifying each application's `main`?
8. Why should a bootstrap listener avoid performing long-running network I/O by default?

Once you can answer and demonstrate these with the hands-on project, you know how to **register listeners early enough**, **use data appropriate to each stage**, and **avoid confusing application listeners with beans that do not yet exist**.

## Official References

- Spring Boot 3.3, `SpringApplication` Javadoc (`addListeners`, `getListeners`, `setListeners`): https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3, SpringApplication Events and Listeners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3, `ApplicationStartingEvent`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationStartingEvent.html
- Spring Boot 3.3, `ApplicationEnvironmentPreparedEvent`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationEnvironmentPreparedEvent.html
- Spring Boot 3.3, `ApplicationFailedEvent`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationFailedEvent.html

**Conclusion:** `SpringApplication.addListeners(...)` lets you attach an `ApplicationListener` **before the context is created**, enabling the listener to observe the earliest events that `@Bean` or `@EventListener` cannot catch in the normal lifecycle. In return, early callbacks may rely only on data actually available at that stage; they are not a place to access Spring beans, run arbitrary business logic, or slow down bootstrap uncontrolled.