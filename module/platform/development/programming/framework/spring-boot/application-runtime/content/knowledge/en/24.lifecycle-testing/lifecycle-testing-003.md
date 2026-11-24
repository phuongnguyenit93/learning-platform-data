# Testing Initializers or Listeners Without Running the Entire Spring Boot Application

## 1. Goal: verifying lifecycle behavior with the smallest scope

A Spring Boot application often contains code that hooks into the startup and shutdown lifecycle, such as:

- `ApplicationContextInitializer` setting default properties, profiles, or registering infrastructure before `refresh()`.
- `ApplicationListener<ApplicationReadyEvent>` logging, updating internal state, or notifying when Boot emits the ready event.
- `ApplicationListener<ContextRefreshedEvent>` reacting when a Spring context is refreshed.
- `@EventListener` declaring a method to receive events via Spring's event infrastructure.
- Listeners registered very early via `SpringApplication.addListeners(...)` to receive `SpringApplicationEvent` instances emitted before the bean container is ready.

A common reflex is to write `@SpringBootTest` for all scenarios. That often creates many beans, reads application configuration, triggers auto-configuration, and sometimes connects to databases or networks — making tests slow and introducing failure causes unrelated to the initializer/listener under test.

**Not every lifecycle test needs to call `SpringApplication.run()`.** Separate them into:

1. **Pure unit test:** instantiate the initializer/listener as a Java object and call its method directly.
2. **Minimal context test:** use `GenericApplicationContext` or `AnnotationConfigApplicationContext` to test `refresh`, the event multicaster, dependency injection, and cleanup.
3. **ApplicationContextRunner:** create a small context with controlled configuration, invoke initializers, override properties, check startup failures, and auto-close the context.
4. **Full integration test:** only when you must prove Spring Boot itself emits events in order, runs runners, auto-configuration, a web server, readiness, or real startup failures.

This lesson uses **Java 17+, Spring Boot 3.3.x, and Spring Framework 6.1.x**. It includes a complete Gradle example, a program that builds only a small context, and JUnit 5 tests using AssertJ. The main examples **do not call `SpringApplication.run()` or `@SpringBootTest`**.

## 2. Distinguishing the test target from event-publishing infrastructure

The target under test may be:

```java
public final class ModeInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        // Customize Environment before refresh.
    }
}
```

or:

```java
public final class ReadySummaryListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        // React when the corresponding event occurs.
    }
}
```

The two snippets above are **skeletons**; they do not run standalone because they lack method bodies and imports. Complete classes appear in section 9.

Tests must answer precisely **what you want to prove**:

| Question | Appropriate test level |
| --- | --- |
| Does the initializer add a default property? | Call `initialize(context)` on an unrefreshed context |
| Does the initializer avoid overriding configured properties? | Unit test with `MapPropertySource` and precedence order |
| Does the initializer reject invalid configuration? | Exception unit test or `ApplicationContextRunner` |
| Does the listener turn the event into the expected message? | Call `onApplicationEvent(event)` directly |
| Does the Spring event bus route the event to a registered listener? | `GenericApplicationContext`, `publishEvent` |
| Is a method with `@EventListener` discovered? | Refreshed `AnnotationConfigApplicationContext` |
| Does Boot automatically emit `ApplicationReadyEvent` after runners? | Integration test with `SpringApplication` |
| Does a listener registered before the context receive very early events? | Test `SpringApplication`'s registration path, not just calling the method |
| Do web readiness/health endpoints work properly? | Appropriate slice or web integration test |

**Avoid overclaiming:** unit testing a listener receiving an event **does not prove** Boot will actually register and emit that event in production. Conversely, a full integration test is usually unnecessary when you only want to prove a property string is added properly.

## 3. Spring Boot's lifecycle and timing of initializers/listeners

Spring Boot 3.3 emits key milestones in this general sequence:

```text
SpringApplication.run(...)
        |
ApplicationStartingEvent
        |
ApplicationEnvironmentPreparedEvent
        |
Create ConfigurableApplicationContext
        |
ApplicationContextInitializer.initialize(context)
        |
ApplicationContextInitializedEvent
        |
Load bean definitions
        |
ApplicationPreparedEvent
        |
ApplicationContext.refresh()
        |
ContextRefreshedEvent
        |
ApplicationStartedEvent
        |
LivenessState.CORRECT
        |
ApplicationRunner / CommandLineRunner
        |
ApplicationReadyEvent
        |
ReadinessState.ACCEPTING_TRAFFIC
        |
SpringApplication.run(...) returns context

If startup fails:
        |
ApplicationFailedEvent via failure path
```

These milestones do not mean all of them are emitted automatically by `GenericApplicationContext.refresh()`.

### 3.1. ApplicationContextInitializer runs before refresh

`ApplicationContextInitializer<C extends ConfigurableApplicationContext>` has the method:

```java
void initialize(C applicationContext);
```

Initializers are used to configure the context **before `refresh()`**, such as adding a `PropertySource`, enabling profiles, or registering definitions when the context type supports it.

At that point, **you should not expect all singletons to be created** or call `context.getBean(MyService.class)` as if the app were ready. A good unit test can verify behavior **without refreshing the context**, even without any bean definitions.

### 3.2. @EventListener and ApplicationListener differ in registration

- An object implementing `ApplicationListener<E>` can receive events if you call `onApplicationEvent` directly, or if you register it with `context.addApplicationListener(listener)` before `publishEvent`.
- A method annotated with `@EventListener` needs Spring's event-listener method processor to detect it after the bean is placed in a suitable context and annotation configuration is processed. Instantiating an object with `new` and calling `context.publishEvent(...)` **does not automatically register that method**.
- Early Boot events can be emitted **before the context is created**, so a `@Component` or `@EventListener` bean does not exist yet to receive them. Register early via `SpringApplication.addListeners(...)`/`SpringApplicationBuilder.listeners(...)` or `spring.factories` when wiring from the very beginning must be guaranteed.

### 3.3. Simulating an event does not make Boot truly ready

You can construct `ApplicationReadyEvent` directly using Spring Boot 3.3's constructor:

```java
new ApplicationReadyEvent(
        new SpringApplication(DemoClass.class),
        new String[0],
        context,
        Duration.ofMillis(10));
```

This is a **snippet** where `context` is a real `ConfigurableApplicationContext` and `DemoClass` is a project-specific Java class. It serves to test listeners; it **does not run runners, does not start a web server, does not emit Boot-managed availability states, and does not prove real readiness**.

This is the most important boundary between **testing a handler** and **testing lifecycle orchestration**.

## 4. Unit testing an initializer with GenericApplicationContext

`GenericApplicationContext` belongs to Spring Framework and can be instantiated with `new`. Before calling `refresh()`, you already have a context object and can manipulate `Environment`.

Example initializer setting a default configuration:

```java
@Override
public void initialize(ConfigurableApplicationContext context) {
    context.getEnvironment().getPropertySources().addLast(
            new MapPropertySource(
                    "demo-defaults",
                    Map.of("demo.mode", "safe")));
}
```

This is an illustrative method inside an initializer class. `addLast` places the property source at lowest precedence; a property declared earlier in higher-precedence sources (e.g., test configuration) can still win.

### 4.1. Testing without refresh

```java
try (GenericApplicationContext context =
             new GenericApplicationContext()) {

    new ModeInitializer().initialize(context);

    assertThat(context.getEnvironment()
            .getProperty("demo.mode")).isEqualTo("safe");
    assertThat(context.isActive()).isFalse();
}
```

This is a snippet inside a JUnit test with appropriate imports. The key is that **`initialize` is called directly and the context has not refreshed**, so the full application is not booted.

To test **precedence**, create a `MapPropertySource` with a pre-supplied value:

```java
context.getEnvironment().getPropertySources().addFirst(
        new MapPropertySource(
                "test-override",
                Map.of("demo.mode", "fast")));

new ModeInitializer().initialize(context);

// Expected: fast, not overridden by default safe.
```

Here `addFirst` puts the test source at highest precedence. If the initializer mistakenly uses `addFirst` and writes the same property name, it can accidentally violate the "defaults only" rule.

### 4.2. Testing configuration errors

If an initializer has a contract rejecting values other than `safe` or `fast`, unit tests should assert:

- The exact **exception type**.
- A helpful error message that does not leak secrets.
- The context **has not refreshed**.
- No side effects such as opening databases/sockets or creating executors.

Do not force tests to start a web server just to verify an `IllegalArgumentException` thrown by an initializer.

### 4.3. Initializers and bean registration

Some initializers call `context.getBeanFactory()` or register bean definitions when the context supports it. You can test with `GenericApplicationContext` or `AnnotationConfigApplicationContext`, but **do not assume every context subtype can be refreshed multiple times**. `GenericApplicationContext` normally refreshes only once; if a test needs a fresh run, create a new instance and close the old one.

## 5. ApplicationContextRunner for controlled configuration

Spring Boot provides `org.springframework.boot.test.context.runner.ApplicationContextRunner` in `spring-boot-test`.

It helps:

- Create a **small context**, non-web by default.
- Register initializers via `withInitializer(...)`.
- Supply properties via `withPropertyValues(...)`.
- Register only needed beans/configurations instead of scanning the whole project.
- Execute the `run(context -> ...)` callback after refresh.
- **Auto-close** the context after the callback.
- Inspect startup failures if an initializer/configuration throws an exception.

Example:

```java
new ApplicationContextRunner()
        .withInitializer(new ModeInitializer())
        .withPropertyValues("demo.mode=fast")
        .run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context.getEnvironment()
                    .getProperty("demo.mode")).isEqualTo("fast");
        });
```

This is a JUnit/AssertJ snippet; complete code is in section 9.

### 5.1. run is not SpringApplication.run

`ApplicationContextRunner.run(...)` creates and **refreshes** a context, but does not perform the full orchestration of `SpringApplication.run(...)`: it does not automatically run all Boot auto-configurations, runners, a web server, or publish `ApplicationReadyEvent`. It only loads the configurations and beans you registered with the runner.

This is an **advantage for isolated testing**, but conclusion limits must be stated accurately.

### 5.2. prepare instead of run when you don't want refresh yet

Spring Boot 3.3 also provides `ApplicationContextRunner.prepare(...)`. Unlike `run(...)`, `prepare(...)` **does not refresh** the prepared context. It is suitable when you only want to inspect state before refresh, provided the test target does not need the full BeanFactory lifecycle.

Like `run`, the runner manages closing the context when the callback ends. Do not retain the callback's context reference and continue calling `getBean` afterward.

### 5.3. Testing a failing initializer

An initializer can throw an exception due to invalid configuration. When using the runner, tests can check:

```java
new ApplicationContextRunner()
        .withPropertyValues("demo.mode=broken")
        .withInitializer(new ModeInitializer())
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                    .hasMessageContaining(
                            "demo.mode must be safe or fast");
        });
```

This is an **illustrative snippet**, relying on the runner's error-handling, AssertJ, and the example `ModeInitializer`. If you only need to test the exception-throwing contract, calling `initialize` directly is often simpler and clearer. Never infer from a context runner failure that Spring Boot's `ApplicationFailedEvent` was emitted: the runner does not run `SpringApplication`.

### 5.4. When a web context is needed without starting a server

Spring Boot also offers `WebApplicationContextRunner` or `ReactiveWebApplicationContextRunner` for auto-configuration depending on web context types. They remain **lightweight context test utilities**, not equivalent to starting a full embedded web server.

For pure `Environment` initializers, use `GenericApplicationContext` or `ApplicationContextRunner` first; do not choose a web runner merely because the real application is a REST service.

## 6. Unit testing an ApplicationListener without a Spring container

A listener that simply translates an event into an action can receive dependencies via its constructor:

```java
public final class ReadySummaryListener
        implements ApplicationListener<ApplicationReadyEvent> {

    private final Consumer<String> sink;

    public ReadySummaryListener(Consumer<String> sink) {
        this.sink = sink;
    }

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        String mode = event.getApplicationContext()
                .getEnvironment()
                .getProperty("demo.mode", "unset");
        sink.accept("READY_MODE=" + mode);
    }
}
```

This class illustrates the complete logic but requires imports and a package; full code is in section 9. `Consumer<String>` lets tests pass `List::add` without sending HTTP requests, opening databases, or initializing LoggingSystem.

Unit test:

```java
List<String> reports = new ArrayList<>();
ReadySummaryListener listener =
        new ReadySummaryListener(reports::add);

listener.onApplicationEvent(syntheticReadyEvent(context));

assertThat(reports).containsExactly("READY_MODE=safe");
```

This snippet assumes `context` is already created/refreshed; the `syntheticReadyEvent` helper is defined in the complete test. In this test, you **invoke the listener directly**, so it only asserts that the handler processes data properly.

### 6.1. Avoid complex mocks when a plain Java object suffices

If a listener only reads a property from the context, you can spin up a tiny real context. If you need to verify interactions with a dependency, inject a fake `Consumer`, a fake interface, or a Mockito mock. Avoid mocking the entire SpringApplication lifecycle when the goal is just comparing a string.

### 6.2. Do not call System.exit in listener tests

An application listener should not arbitrarily call `System.exit(...)`. Inside the JUnit JVM, doing so can terminate the entire test process. When you genuinely need to test an entrypoint returning a process exit status, run the application in a **subprocess** and observe the exit code; that is no longer a pure listener unit test.

## 7. Testing the Spring event dispatcher with a small context

To verify a listener receives events **via the Spring event bus**, stop calling the method directly. Replace with:

```java
try (GenericApplicationContext context =
             new GenericApplicationContext()) {

    new ModeInitializer().initialize(context);

    List<String> reports = new ArrayList<>();
    context.addApplicationListener(
            new ReadySummaryListener(reports::add));

    context.refresh();
    assertThat(reports).isEmpty();

    context.publishEvent(syntheticReadyEvent(context));
    assertThat(reports).containsExactly("READY_MODE=safe");
}
```

This is a snippet inside a JUnit class whose helper is in section 9.

**What this proves:**

- The listener was registered directly with `GenericApplicationContext`.
- Spring's event dispatcher routes the `ApplicationReadyEvent` type properly.
- The handler transforms the event into the expected outcome.
- No `SpringApplication.run` needed.

**What this does not prove:** whether Spring Boot actually emits `ApplicationReadyEvent` after completing runners. The event in the test was **manually constructed and published**.

### 7.1. ContextRefreshedEvent is genuinely emitted by refresh()

A case with a **real event emitted by the small context**:

```java
AtomicInteger seen = new AtomicInteger();

try (GenericApplicationContext context =
             new GenericApplicationContext()) {

    context.addApplicationListener(
            (ApplicationListener<ContextRefreshedEvent>)
                    event -> seen.incrementAndGet());

    context.refresh();
    assertThat(seen.get()).isEqualTo(1);
}
```

`context.refresh()` emits `ContextRefreshedEvent` when refresh finishes. It is a **Spring Framework context event**, distinct from `ApplicationStartedEvent` or `ApplicationReadyEvent` emitted by Spring Boot.

### 7.2. Synchronous event dispatch vs. async listeners

Under standard configuration, the Spring event multicaster uses **synchronous** dispatch. Therefore, in the example above, immediately after `publishEvent(...)` returns, `reports` already contains the message.

If the application configures an asynchronous `ApplicationEventMulticaster` or the listener uses `@Async`, asserting immediately after publish can race. In that case, test synchronously via a fake executor or use bounded waiting with `Awaitility`/`CountDownLatch` rather than an arbitrary `Thread.sleep(2000)`.

### 7.3. Generic types and event filtering

`ApplicationListener<ApplicationReadyEvent>` is not a listener for every `ApplicationEvent`. The Spring event bus uses the matching generic event type for dispatch. Writing a raw `ApplicationListener` or misconfiguring generics can cause unintended event reception or missed events.

In the test, the listener's constructor and generic type are declared explicitly to reduce the risk of handling the wrong type.

## 8. Testing @EventListener with AnnotationConfigApplicationContext

`@EventListener` on a method requires annotation method processing. A test that only creates:

```java
AnnotatedObserver observer = new AnnotatedObserver();
// Not yet registered in Spring context.
```

**cannot** prove Spring discovers the annotated method.

Instead, use `AnnotationConfigApplicationContext`:

```java
try (AnnotationConfigApplicationContext context =
             new AnnotationConfigApplicationContext()) {

    context.registerBean(AnnotatedObserver.class);
    context.refresh();

    context.publishEvent(syntheticReadyEvent(context));

    assertThat(context.getBean(AnnotatedObserver.class)
            .getCount()).isEqualTo(1);
}
```

This is a snippet; the `AnnotatedObserver` class and `syntheticReadyEvent` helper appear in the full test in section 9.

Key differences:

- `AnnotationConfigApplicationContext` registers annotation configuration processors.
- `registerBean(...)` adds the bean under test without scanning the whole package.
- `refresh()` activates the event listener method processor.
- `publishEvent(...)` makes the event bus invoke the `@EventListener` method.
- Still never runs `SpringApplication.run(...)`.

### 8.1. Do not confuse @EventListener with ultra-early registered listeners

A normal `@EventListener(ApplicationStartingEvent.class)` bean is not instantiated before the context exists. To catch ultra-early startup events, use `SpringApplication.addListeners(...)` or `META-INF/spring.factories` per the Spring Boot contract. Unit testing the event-handling method remains useful, yet **does not prove registration timing**.

## 9. Runnable Java 17+ project: initializers and listeners without SpringApplication.run

The project uses **Spring Boot 3.3.13**, Spring Framework 6.1, and JUnit Jupiter. It includes:

- `ModeInitializer`: validates `demo.mode` and supplies default `safe` via a low-precedence property source.
- `ReadySummaryListener`: receives `ApplicationReadyEvent` and records a message via `Consumer`.
- `LifecycleProbe`: Java program building a `GenericApplicationContext`, calling refresh, and publishing a **synthetic event**; does not run the Boot application lifecycle.
- `LifecycleComponentsTest`: tests for direct initializer, precedence, invalid config, `ApplicationContextRunner`, direct listener, event dispatch, `ContextRefreshedEvent`, and `@EventListener` annotation processing.

### 9.1. Project structure

```text
lifecycle-unit-tests/
  settings.gradle
  build.gradle
  src/main/java/com/example/lifecycle/
    ModeInitializer.java
    ReadySummaryListener.java
    LifecycleProbe.java
  src/test/java/com/example/lifecycle/
    LifecycleComponentsTest.java
```

### 9.2. settings.gradle

```groovy
rootProject.name = 'lifecycle-unit-tests'
```

### 9.3. build.gradle (Groovy DSL)

```groovy
plugins {
    id 'java'
    id 'application'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'com.example.lifecycle.LifecycleProbe'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-test` pulls in JUnit Jupiter, AssertJ, and compatible test dependencies; `ApplicationContextRunner` lives in `spring-boot-test` in test scope. The `application` plugin allows `./gradlew run` to execute `LifecycleProbe.main()` **without running `SpringApplication.run`**.

Only `./gradlew test` and `./gradlew run` are used for this lesson; no REST server, DataSource, or message broker is required.

### 9.4. ModeInitializer.java

```java
package com.example.lifecycle;

import java.util.Map;
import java.util.Set;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.MapPropertySource;

public final class ModeInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        String mode = context.getEnvironment()
                .getProperty("demo.mode");

        if (mode != null
                && !Set.of("safe", "fast").contains(mode)) {
            throw new IllegalArgumentException(
                    "demo.mode must be safe or fast");
        }

        // Add default with low precedence only.
        context.getEnvironment().getPropertySources().addLast(
                new MapPropertySource(
                        "lesson-mode-defaults",
                        Map.of("demo.mode", "safe")));
    }
}
```

This is a **complete file**, requiring no refreshed BeanFactory. It does not access a database, create executors, or call `getBean`.

If `demo.mode=fast` is already present in a higher-precedence source, default `safe` does not override it; if `broken` is supplied, the initializer throws an exception immediately. These are two key contracts to verify with unit tests.

### 9.5. ReadySummaryListener.java

```java
package com.example.lifecycle;

import java.util.Objects;
import java.util.function.Consumer;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;

public final class ReadySummaryListener
        implements ApplicationListener<ApplicationReadyEvent> {

    private final Consumer<String> sink;

    public ReadySummaryListener(Consumer<String> sink) {
        this.sink = Objects.requireNonNull(sink);
    }

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        String mode = event.getApplicationContext()
                .getEnvironment()
                .getProperty("demo.mode", "unset");

        sink.accept("READY_MODE=" + mode);
    }
}
```

This is a **complete file**. It is not a `@Component`; in tests, we explicitly register the listener or call it directly. In a real application, if you want Boot to deliver the event when ready, register the listener via the proper path and timing.

`Consumer<String>` allows tests to replace the log/event destination with `ArrayList::add`, avoiding side effects outside the JVM.

### 9.6. LifecycleProbe.java

```java
package com.example.lifecycle;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.support.GenericApplicationContext;

public final class LifecycleProbe {

    public static void main(String[] args) {
        List<String> reports = new ArrayList<>();
        AtomicInteger refreshEvents = new AtomicInteger();

        try (GenericApplicationContext context =
                     new GenericApplicationContext()) {

            new ModeInitializer().initialize(context);

            context.addApplicationListener(
                    (ApplicationListener<ContextRefreshedEvent>)
                            event -> refreshEvents.incrementAndGet());

            context.addApplicationListener(
                    new ReadySummaryListener(reports::add));

            // This is Spring Framework refresh, not Boot run.
            context.refresh();

            // This event is created by test code; Boot does not emit it automatically.
            ApplicationReadyEvent syntheticReady =
                    new ApplicationReadyEvent(
                            new SpringApplication(LifecycleProbe.class),
                            new String[0],
                            context,
                            Duration.ofMillis(42));

            context.publishEvent(syntheticReady);

            System.out.println("MODE="
                    + context.getEnvironment()
                            .getProperty("demo.mode"));
            System.out.println("REFRESH_EVENTS="
                    + refreshEvents.get());
            System.out.println("READY_REPORTS=" + reports);
        }
    }
}
```

This is a **complete Java file**. The program merely creates a `GenericApplicationContext`, adds listeners, calls `refresh`, and publishes a test event. `new SpringApplication(LifecycleProbe.class)` only creates an object as the event **source**; it **does not** call `SpringApplication.run`.

With a `GenericApplicationContext` containing no business beans, `refresh()` creates minimal infrastructure and emits exactly one `ContextRefreshedEvent` on the normal execution path.

### 9.7. Command to run the illustrative program

From the project directory with Gradle Wrapper:

```bash
./gradlew run
```

Windows CMD:

```bat
gradlew.bat run
```

Windows PowerShell:

```powershell
.\gradlew.bat run
```

The lines **printed by `LifecycleProbe` itself** on the success path, in order:

```text
MODE=safe
REFRESH_EVENTS=1
READY_REPORTS=[READY_MODE=safe]
```

Gradle may print additional progress and build messages, but the three lines printed by our code do not depend on machine timing. The `READY_REPORTS` line appears because the test **manually publishes** `ApplicationReadyEvent`, not because Boot actually reached accepting readiness.

### 9.8. LifecycleComponentsTest.java

```java
package com.example.lifecycle;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.context.support.GenericApplicationContext;
import org.springframework.core.env.MapPropertySource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class LifecycleComponentsTest {

    @Test
    void initializerWorksBeforeRefresh() {
        try (GenericApplicationContext context =
                     new GenericApplicationContext()) {

            new ModeInitializer().initialize(context);

            assertThat(context.getEnvironment()
                    .getProperty("demo.mode")).isEqualTo("safe");
            assertThat(context.isActive()).isFalse();
        }
    }

    @Test
    void initializerDoesNotOverrideConfiguredValue() {
        try (GenericApplicationContext context =
                     new GenericApplicationContext()) {

            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource(
                            "test-override",
                            Map.of("demo.mode", "fast")));

            new ModeInitializer().initialize(context);

            assertThat(context.getEnvironment()
                    .getProperty("demo.mode")).isEqualTo("fast");
        }
    }

    @Test
    void initializerRejectsUnknownMode() {
        try (GenericApplicationContext context =
                     new GenericApplicationContext()) {

            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource(
                            "test-bad-mode",
                            Map.of("demo.mode", "broken")));

            assertThatThrownBy(
                    () -> new ModeInitializer().initialize(context))
                    .isInstanceOf(IllegalArgumentException.class)
                    .hasMessage("demo.mode must be safe or fast");

            assertThat(context.isActive()).isFalse();
        }
    }

    @Test
    void runnerExecutesInitializerWithSelectedProperties() {
        new ApplicationContextRunner()
                .withPropertyValues("demo.mode=fast")
                .withInitializer(new ModeInitializer())
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getEnvironment()
                            .getProperty("demo.mode")).isEqualTo("fast");
                });
    }

    @Test
    void readyListenerCanBeTestedDirectly() {
        List<String> observed = new ArrayList<>();

        try (GenericApplicationContext context =
                     new GenericApplicationContext()) {

            new ModeInitializer().initialize(context);
            context.refresh();

            ReadySummaryListener listener =
                    new ReadySummaryListener(observed::add);

            listener.onApplicationEvent(readyEvent(context));

            assertThat(observed)
                    .containsExactly("READY_MODE=safe");
        }
    }

    @Test
    void contextDispatcherRoutesSyntheticReadyEvent() {
        List<String> observed = new ArrayList<>();

        try (GenericApplicationContext context =
                     new GenericApplicationContext()) {

            new ModeInitializer().initialize(context);
            context.addApplicationListener(
                    new ReadySummaryListener(observed::add));

            context.refresh();
            assertThat(observed).isEmpty();

            context.publishEvent(readyEvent(context));
            assertThat(observed)
                    .containsExactly("READY_MODE=safe");
        }
    }

    @Test
    void refreshPublishesContextRefreshedEvent() {
        AtomicInteger count = new AtomicInteger();

        try (GenericApplicationContext context =
                     new GenericApplicationContext()) {

            context.addApplicationListener(
                    (ApplicationListener<ContextRefreshedEvent>)
                            event -> count.incrementAndGet());

            context.refresh();
            assertThat(count.get()).isEqualTo(1);

            // Manually publish an event of the same type to verify dispatch.
            context.publishEvent(new ContextRefreshedEvent(context));
            assertThat(count.get()).isEqualTo(2);
        }
    }

    @Test
    void annotationListenerWorksInMinimalAnnotationContext() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.registerBean(AnnotatedReadyObserver.class);
            context.refresh();

            context.publishEvent(readyEvent(context));

            assertThat(context.getBean(AnnotatedReadyObserver.class)
                    .getCount()).isEqualTo(1);
        }
    }

    private static ApplicationReadyEvent readyEvent(
            GenericApplicationContext context) {

        return new ApplicationReadyEvent(
                new SpringApplication(LifecycleProbe.class),
                new String[0],
                context,
                Duration.ofMillis(42));
    }

    public static final class AnnotatedReadyObserver {

        private final AtomicInteger count = new AtomicInteger();

        @EventListener
        public void onReady(ApplicationReadyEvent event) {
            count.incrementAndGet();
        }

        public int getCount() {
            return count.get();
        }
    }
}
```

**This is a complete test file**, containing eight test methods. The tests do not call `SpringApplication.run`, do not use `@SpringBootTest`, and do not open HTTP ports.

What each test proves:

| Test | Scope |
| --- | --- |
| `initializerWorksBeforeRefresh` | Sets default property before refresh |
| `initializerDoesNotOverrideConfiguredValue` | Property source precedence is preserved |
| `initializerRejectsUnknownMode` | Initializer validation and exception path |
| `runnerExecutesInitializerWithSelectedProperties` | `ApplicationContextRunner.withInitializer` uses proper properties |
| `readyListenerCanBeTestedDirectly` | Handler logic on receiving the event |
| `contextDispatcherRoutesSyntheticReadyEvent` | Event multicaster routes the event properly to the listener |
| `refreshPublishesContextRefreshedEvent` | Context refresh genuinely emits the Spring Framework event |
| `annotationListenerWorksInMinimalAnnotationContext` | `@EventListener` is registered by annotation processors |

### 9.9. Running JUnit tests

```bash
./gradlew test
```

Windows CMD: `gradlew.bat test`; PowerShell: `.\gradlew.bat test`.

When tests pass, Gradle reports `BUILD SUCCESSFUL` (exact output details and timing depend on Gradle). The standard HTML report is typically located at:

```text
build/reports/tests/test/index.html
```

This lesson expects **8 passing tests** in a compatible environment. Do not predict exact seconds or full Gradle/Spring logs, as they depend on the machine and cache.

### 9.10. Why doesn't the demo project have @SpringBootApplication?

We are only testing small lifecycle components; there is no need to create a full application class, component scanning, auto-configuration, or an embedded server. `LifecycleProbe` is a plain Java entrypoint that may instantiate `SpringApplication` to construct **a synthetic event**, without calling `run(...)`.

If you later move the listener/initializer into a real application, you must still verify how they are registered on `SpringApplication` and their behavior during full startup. This small test **does not replace** an integration test covering the deployment path.

## 10. Testing the order of multiple initializers

Spring Boot applies initializers in order, supporting `Ordered` and `@Order`. One initializer may write a default property while another reads it. If logic depends on order, test at the **right layer**:

- **Unit test**: call `first.initialize(context)` and `second.initialize(context)` in explicit order; only proves logic when invoked in that order.
- **Sorted list test**: use Spring's `AnnotationAwareOrderComparator`/`Ordered` to verify the expected order of a collection.
- **SpringApplication integration test**: needed when confirming Boot applies initializers registered via code, properties, or `spring.factories` in actual runtime order.

Illustrative pseudo-test example:

```java
List<String> calls = new ArrayList<>();

ApplicationContextInitializer<ConfigurableApplicationContext> first =
        context -> calls.add("first");

ApplicationContextInitializer<ConfigurableApplicationContext> second =
        context -> calls.add("second");

try (GenericApplicationContext context =
             new GenericApplicationContext()) {
    first.initialize(context);
    second.initialize(context);
}

assertThat(calls).containsExactly("first", "second");
```

This is a **snippet**, requiring imports and assertions; it only proves the order **invoked manually by test code**, not that `SpringApplication` sorted them by `Ordered`.

**Note:** lower order values normally have higher precedence. If two initializers share the same order, do not rely on accidental registration order for critical logic.

## 11. Testing @ContextConfiguration(initializers=...) when Spring TestContext is needed

Spring Framework TestContext lets you register initializers for a framework-managed test context:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(
        classes = SmallTestConfiguration.class,
        initializers = ModeInitializer.class)
class WithInitializerTest {

    @Autowired
    Environment environment;

    @Test
    void defaultModeIsVisible() {
        assertThat(environment.getProperty("demo.mode"))
                .isEqualTo("safe");
    }
}
```

This is a **snippet**, requiring imports from JUnit, Spring Test, AssertJ, and a `SmallTestConfiguration` class. It is not a standalone runnable file because the configuration class is not defined in the illustrative snippet.

This model fits when you need Spring TestContext to manage:

- Injection via `@Autowired`.
- Minimal configuration classes.
- Test context lifecycle and test execution listeners.
- Certain post-processors absent in pure unit tests.

However, it **does not run `SpringApplication.run`**, and test context caching may reuse the context. Do not manually call `close()` on a cached Spring TestContext inside a test unintentionally; use a dedicated context or `@DirtiesContext` where appropriate.

### 11.1. When to choose ApplicationContextRunner over @ContextConfiguration?

`ApplicationContextRunner` is usually more concise when testing many combinations:

```text
demo.mode=missing  -> initializer picks default safe
demo.mode=fast     -> keeps fast
demo.mode=broken   -> validation failure
```

It creates/closes each context per callback. `@ContextConfiguration` is convenient when you need `SpringExtension`, injection, and reuse of the same configuration across multiple test methods.

This is a trade-off between **cost and verification scope**, not an "always best" tool choice.

## 12. Early SpringApplication events: limits when mocking

Several events occur **before the ApplicationContext exists**:

- `ApplicationStartingEvent` is emitted very early.
- `ApplicationEnvironmentPreparedEvent` occurs after the Environment is ready but before the context is created.
- `ApplicationContextInitializedEvent` occurs after initializers run but before bean definitions are loaded.
- `ApplicationPreparedEvent` occurs after definitions are loaded and before refresh.

A listener receiving `ApplicationEnvironmentPreparedEvent` may want to modify a property source on `ConfigurableEnvironment`. You can **unit test the handler** by creating a `StandardEnvironment` and constructing the event with **Spring Boot 3.3's exact constructor**, including `ConfigurableBootstrapContext` if required.

**Do not copy a constructor from Boot 2.x or another version** and expect 3.3 code to compile. Boot 3.3 JavaDoc defines the constructor:

```java
ApplicationEnvironmentPreparedEvent(
        ConfigurableBootstrapContext bootstrapContext,
        SpringApplication application,
        String[] args,
        ConfigurableEnvironment environment)
```

This is an API signature description, not a standalone file call. In tests you can fake/mock the bootstrap context matching the interface when the handler genuinely needs it; if the handler only processes the Environment, extract pure logic from the event adapter for easy unit testing.

### 12.1. Separating business logic from event adapters

A testable design:

```text
ApplicationEnvironmentPreparedEvent
          |
EarlyEnvironmentListener.onApplicationEvent(event)
          |
EnvironmentPolicy.apply(environment)
          |
PropertySource / profile changes
```

Unit testing `EnvironmentPolicy` with `StandardEnvironment` is very fast. Test the listener adapter separately with synthetic events. Finally, you only need one small integration test to ensure listener registration via `SpringApplication.addListeners`/`spring.factories` actually fires at the right time.

**Do not** force every test to run full startup just because a listener handles a Boot event.

### 12.2. Testing real registration of an early listener is a separate test

Merely calling:

```java
listener.onApplicationEvent(event);
```

**cannot prove** `META-INF/spring.factories` has the right path, the class has a public no-arg constructor, or `SpringApplication.addListeners(...)` was called before `run`.

When you need to prove wiring, you can have a constrained test launching `SpringApplication` with `WebApplicationType.NONE` and minimal beans. That is a **separate integration test**, not a reason to turn every unit test into `@SpringBootTest`.

## 13. Listeners in parent/child ApplicationContexts

Spring Framework has event propagation from **child contexts up to ancestor contexts**. A listener registered on the parent can observe events from the child, so:

- A child's `ContextRefreshedEvent` can reach the parent's listener.
- If a listener should only handle events from its own context, compare `event.getApplicationContext()` against the context the listener is attached to.
- Directly unit testing the event handler does not prove propagation behavior.
- A small context hierarchy test can be constructed to verify it; no web server startup is needed.

For `ApplicationReadyEvent`, the source is `SpringApplication`, yet the event also has `getApplicationContext()`. Do not assume all ready events in a hierarchy belong to the same context.

**Do not let a listener close the parent's DataSource/executor just because a child context emits a shutdown event.** Ownership and context identity must be checked.

## 14. Testing errors and side effects in a controlled way

### 14.1. Exceptions from initializers

If an initializer throws an exception before refresh, a direct unit test should assert the exact exception. `ApplicationContextRunner` can reveal mini-context startup failure. However, **never claim** Spring Boot's `ApplicationFailedEvent` was emitted if you did not call `SpringApplication.run`.

### 14.2. Exceptions from listeners

With the standard synchronous event multicaster, a listener's exception can propagate back to the publisher unless you configure a different error handler or executor. A direct unit test can assert the exception. A mini-context test can assert how the publisher receives the error.

However, if the listener is annotated with `@Async` or `ApplicationEventMulticaster` uses an async executor, errors may follow a different contract; do not put `assertThrows` around `publishEvent` expecting to catch an exception thrown on another thread.

### 14.3. Avoiding network and threads in small tests

If a listener only sends notifications, replace the client with a fake in-memory sink. If an initializer only validates properties, do not create a real database. If a handler creates an executor, the test must shut down the executor so it does not keep the JUnit process alive. The goal here is **isolation**, not reproducing full production infrastructure.

### 14.4. Cleaning up contexts

`GenericApplicationContext` and `AnnotationConfigApplicationContext` are `AutoCloseable` via Spring's context contract; examples use try-with-resources. `ApplicationContextRunner` auto-closes after the callback.

Do not create hundreds of contexts and leave them open: even a small context has a lifecycle and may hold beans needing destruction. Avoid static/shared mutable contexts across tests if initializer logic mutates the Environment or listener state.

## 15. Things unit tests cannot prove

| Test performed | What is **not** proved |
| --- | --- |
| Calling `initialize(context)` directly | Boot registered the initializer and called it at the right phase |
| Calling `listener.onApplicationEvent(event)` | Spring event multicaster knows about this listener |
| `context.publishEvent(syntheticReady)` succeeds | Boot ran runners or readiness is accepting |
| `context.refresh()` emits ContextRefreshedEvent | Boot emitted ApplicationStartedEvent/ReadyEvent |
| `ApplicationContextRunner.run` succeeds | Full Boot auto-configuration and web server will succeed |
| `@EventListener` receives event in a small context | The bean will be scanned from production packages |
| Putting `@Order` on test classes | Production registration/ordering works |
| Fake callback reports success | Real remote notification or auth/timeout is correct |
| Test without a database passes | Production datasource is created and connects for real |
| Testing handler throws no exception | Listener runs cleanly in every concurrency/deployment scenario |

Distinguish this boundary in test names, comments, or test docs. Some teams name unit tests `onReadyFormatsReport` and integration tests `bootPublishesReadyAfterRunners`; the two tests verify two different contracts.

## 16. When is a real integration test needed?

Escalate to `@SpringBootTest` or a real minimal `SpringApplication` run when the question involves:

- Is the listener properly registered via `META-INF/spring.factories` or `addListeners`?
- What is the actual order in which Boot applies initializers?
- Do ConfigData, profiles, property binding, and auto-configuration interact properly?
- Do `ApplicationStartedEvent`, `ApplicationReadyEvent`, and `AvailabilityChangeEvent` occur in the right sequence after runners?
- Does a runner failure lead to `ApplicationFailedEvent` and proper context cleanup?
- Are beans created before/not before refresh, or do Spring lifecycle callbacks stop in order?
- Does the event listener depend on the embedded web server/security/health endpoints?
- Do native image, AOT, or `@EventListener` reflection hints alter behavior?

**Pick a small number of meaningful integration tests**, rather than using full application tests for every simple property branch. If a listener requires verifying readiness probes over HTTP, that is clearly no longer a synthetic-event unit test.

### 16.1. @SpringBootTest does not necessarily open a TCP server

`@SpringBootTest` defaults to `webEnvironment = MOCK` for web apps, so it can spin up a mock web environment without opening a real socket. Still, it can load many configurations/beans and take time. Do not equate "no server needed" with "no need to run the full application" without checking the actual bean graph loaded.

### 16.2. ApplicationContextRunner has its own limitations

Per Spring Boot 3.3 documentation, `ApplicationContextRunner` is well-suited for testing auto-configuration in a standard JVM, but **cannot be used when running tests as a native image**. If a project has a native-test pipeline, an appropriate test solution is required; never assume code passing with the runner on the JVM proves native AOT configuration is right.

## 17. Learning scenarios: purposefully moving from unit to integration

### A. Initializer sets a default property source

**First:** unit test with an unrefreshed `GenericApplicationContext`, checking defaults and precedence.

**Next if needed:** `ApplicationContextRunner.withInitializer` with property combinations.

**Only if registration risk exists:** test `SpringApplication.addInitializers` or real registration config.

### B. Listener receives ApplicationReadyEvent and logs

**First:** create a synthetic `ApplicationReadyEvent` and call the listener directly; inject a fake `Consumer`.

**Then:** publish the event in a `GenericApplicationContext` with the listener registered, verifying dispatch.

**Finally if needed:** test real Boot events after runners, without using synthetic events to claim readiness.

### C. @EventListener method discovered by component scan

**First:** test the method's logic as a standalone Java method if no Spring behavior is needed.

**Then:** use `AnnotationConfigApplicationContext` and `registerBean(...)` to verify annotation processing.

**Finally:** test real package scanning if scan configuration bugs have occurred.

### D. Early environment listener must run before context creation

**First:** extract `Environment` handling logic and unit test with `StandardEnvironment`.

**Then:** unit test the event adapter using the exact constructor for the Boot version.

**Finally:** one integration test verifying the listener is registered via `addListeners`/`spring.factories` before `run`.

### E. Listener with @Async

**First:** test logic synchronously via direct calls and mock dependencies.

**Then:** mini-context test with `@EnableAsync` and a test executor if proxying must be verified.

**Finally:** integration test with bounded wait and error handling if real concurrency is involved.

### F. Initializer registers infrastructure beans

**First:** check the bean definition was registered before refresh.

**Then:** refresh a minimal `GenericApplicationContext` to check the singleton is created properly.

**Finally:** an integration test if the bean is created via complex Boot auto-configuration/conditions.

## 18. Common mistakes and fixes

| Mistake | Why it is wrong | Replacement |
| --- | --- | --- |
| Using `@SpringBootTest` for every `if` branch | Slow tests, many unrelated dependencies | Direct unit test first |
| Calling `context.getBean(...)` in an initializer before refresh | BeanFactory is not yet in a ready application phase | Only configure context/definitions |
| Calling initializer after refresh and concluding it matches production | Wrong phase for initializer contract | Call before `refresh` |
| Using synthetic ApplicationReadyEvent to prove Boot is ready | Event was manually created by the test | Integration test Boot milestones if needed |
| Instantiating `@EventListener` object with `new` without registering | Spring does not scan arbitrary objects | AnnotationConfigApplicationContext + registerBean |
| Putting `@Component` to catch ApplicationStartingEvent | Bean does not exist when early event fires | Early registration via SpringApplication |
| Failing to close test contexts | Resource leaks across tests | try-with-resources or runner callback |
| Calling `GenericApplicationContext.refresh` twice | Generic contexts are not meant for repeated refreshes | Create a new context |
| Asserting immediately after async event publish | Race/flaky under async dispatch | Fake synchronous executor or bounded await |
| Implicitly relying on untested event order | With multiple listeners, order can matter | Ordered/@Order and test at the right layer |
| Having listener read DB in a unit test | External dependency slows tests | Fake dependency/Consumer |
| Thinking ApplicationContextRunner is full SpringApplication | Does not run full Boot lifecycle | Separate integration test |
| Passing property via addFirst to act as default | Can override user overrides | addLast or explicit precedence |
| Testing listener directly and thinking it's registered on event bus | No framework dispatch in the test | publishEvent in a mini-context |
| Closing cached `@SpringBootTest` context inside a test | Breaks other tests | Never close cached contexts arbitrarily |
| Calling System.exit in a unit test | Terminates JUnit runner | Subprocess/process-level test |
| Using Thread.sleep to wait for @Async | Flaky / lacks timeout policy | CountDownLatch/Awaitility with deadline |
| Confusing ContextRefreshedEvent and ApplicationReadyEvent | One is from Framework refresh, one from Boot | Test the right event publisher |
| Mocking Boot 2.x APIs in a 3.3 project | Constructors/generics changed | Check exact 3.3 JavaDoc |
| Treating a small context test as proof the web server works | No real web server | Slice/web integration test when needed |

## 19. Checklist for choosing the right test

1. State the exact event/initializer contract to test.
2. If only pure logic is involved, call the method directly.
3. Use an unrefreshed `GenericApplicationContext` for initializer properties.
4. Place defaults in a property source with proper precedence.
5. Test invalid config with a specific exception.
6. When testing many property combinations, use `ApplicationContextRunner`.
7. When event dispatch is needed, use `addApplicationListener` and `publishEvent`.
8. When `@EventListener` method processing is needed, use `AnnotationConfigApplicationContext`.
9. Distinguish synthetic events from Boot-emitted events.
10. Do not use `SpringApplication.run` if you don't need to prove Boot lifecycle.
11. If real early listener registration is needed, test the `addListeners`/`spring.factories` path.
12. Do not depend on real network/DB/threads when fakes are possible.
13. Use clear JUnit/AssertJ assertions for content, count, and exceptions.
14. Determine sync vs. async event delivery before asserting.
15. Document environment property precedence and profile expectations clearly.
16. Do not refresh a `GenericApplicationContext` repeatedly.
17. Close small contexts; do not retain beans past the runner callback.
18. Do not close shared cached `@SpringBootTest` contexts arbitrarily.
19. Test initializer failure paths separately.
20. Use integration tests only for wiring/lifecycle that must be verified.
21. When testing early events, use the exact Boot 3.3 constructor.
22. With parent/child contexts, check event source/context identity.
23. Do not conclude readiness from a self-published event alone.
24. For native/AOT, do not infer that `ApplicationContextRunner` has verified native runtime behavior.

## 20. Self-check questions

**1. Can `initialize(context)` be called when the context has not refreshed?**

Yes. That is the exact stage meant for `ApplicationContextInitializer`; direct unit tests are the natural choice.

**2. Why use `GenericApplicationContext` instead of `@SpringBootTest`?**

To avoid building the entire bean graph/auto-configuration when only testing a property source or simple callback.

**3. Does `ApplicationContextRunner.run()` run `SpringApplication.run()`?**

No. It creates and refreshes a context for testing without executing the full Spring Boot lifecycle.

**4. What does a test calling `listener.onApplicationEvent(event)` prove?**

It proves the listener logic when receiving the event. It does not yet prove the listener is registered and receives events via the event bus.

**5. How do you test the Spring event dispatcher?**

Register the listener via `context.addApplicationListener(...)`, refresh the context, and then call `context.publishEvent(...)`.

**6. Does calling `publishEvent(new ApplicationReadyEvent(...))` make the app ready?**

No. It only publishes a test-created event object; it does not run runners or replace Boot's lifecycle/availability.

**7. Does `@EventListener` work if you instantiate the object with `new` and don't register it?**

Not automatically. You need a context supporting annotation event listener processing, or invoke the method directly.

**8. Which component emits `ContextRefreshedEvent`?**

Spring Framework emits it when `ApplicationContext.refresh()` completes. It differs from Spring Boot's `ApplicationReadyEvent`.

**9. Will an early `@Component` listener always catch `ApplicationStartingEvent`?**

No. The event can be emitted before Spring beans are created; it must be registered early enough.

**10. Can you test an initializer throwing without starting a web server?**

Yes, using `assertThatThrownBy(() -> initializer.initialize(context))` or a context runner.

**11. When should `@ContextConfiguration(initializers=...)` be used?**

When you want Spring TestContext, dependency injection, and small context configuration with initializers, without needing a full Boot application.

**12. Do unit tests completely replace integration tests?**

No. Unit tests prove logic; wiring, Boot event order, scanning, and real readiness require appropriately scoped integration tests.

## 21. Decision diagram and conclusion

```text
What do you need to test?
      |
      +-- Initializer modifies Environment/PropertySources?
      |       |
      |       +--> GenericApplicationContext + initialize()
      |       +--> ApplicationContextRunner.withInitializer()
      |
      +-- Listener processes event data accurately?
      |       |
      |       +--> new Listener(...), call onApplicationEvent()
      |
      +-- Event dispatcher delivers event to listener?
      |       |
      |       +--> context.addApplicationListener()
      |       +--> context.refresh() + publishEvent()
      |
      +-- @EventListener annotation is discovered?
      |       |
      |       +--> AnnotationConfigApplicationContext
      |       +--> registerBean + refresh + publishEvent
      |
      +-- Boot auto-emits events in order/runners/readiness?
              |
              +--> SpringApplication integration test

TESTING SYNTHETIC EVENT != FULL BOOT LIFECYCLE
DIRECT INITIALIZER TEST != VERIFYING PRODUCTION REGISTRATION
```

**Core principle:** test initializers or listeners at the **smallest layer sufficient to prove behavior**. Use plain Java objects and `GenericApplicationContext` for unit/component tests, `ApplicationContextRunner` for configuration combinations, `AnnotationConfigApplicationContext` for `@EventListener`, and full `SpringApplication` only when verifying wiring or real event lifecycles. Results are faster, test failures are sharper, and the boundary between **tested logic** and **production behavior needing confirmation** stays clear.

## Official documentation

- [Spring Framework 6.1 — ApplicationContextInitializer API](https://docs.spring.io/spring-framework/docs/6.1.10/javadoc-api/org/springframework/context/ApplicationContextInitializer.html)
- [Spring Framework 6.1 — GenericApplicationContext API](https://docs.spring.io/spring-framework/docs/6.1.10/javadoc-api/org/springframework/context/support/GenericApplicationContext.html)
- [Spring Framework — Application Events and event listener model](https://docs.spring.io/spring-framework/reference/6.1/core/beans/context-introduction.html)
- [Spring Framework — TestContext: Context Configuration with Context Initializers](https://docs.spring.io/spring-framework/reference/6.1/testing/testcontext-framework/ctx-management/initializers.html)
- [Spring Framework — TestContext: Recording Application Events](https://docs.spring.io/spring-framework/reference/6.1/testing/testcontext-framework/application-events.html)
- [Spring Boot 3.3 — SpringApplication events and listener registration](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.3 — ApplicationReadyEvent constructor API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html)
- [Spring Boot 3.3 — ApplicationEnvironmentPreparedEvent constructor API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationEnvironmentPreparedEvent.html)
