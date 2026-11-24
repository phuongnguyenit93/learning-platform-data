# Testing a Real Run Using SpringApplication with WebApplicationType.NONE

## Learning objectives

When testing a Spring Boot application's lifecycle, many bugs only surface when executing the **real startup path**: processing `Environment`, creating and refreshing `ApplicationContext`, instantiating singleton beans, invoking lifecycle callbacks, running `ApplicationRunner`/`CommandLineRunner`, emitting `ApplicationReadyEvent` or `ApplicationFailedEvent`, and then closing the context and releasing resources. A unit test that only invokes a constructor or a service method cannot prove this entire flow.

However, **testing a real lifecycle does not require opening an HTTP server**. `SpringApplication.setWebApplicationType(WebApplicationType.NONE)` forces Spring Boot to use a **non-web** environment under the default context configuration, even when Spring MVC/Tomcat is present on the classpath. This is a useful way to run application-runtime integration tests without occupying a port.

This lesson belongs to **Spring Boot Application Runtime → Lifecycle Testing**. The examples use **Java 17+**, **Spring Boot 3.3.13**, **Spring Framework 6.1.x**, **JUnit 5**, **Gradle**.

After this lesson, you will be able to:

1. Explain the difference between a **real `SpringApplication.run`** and tests that merely instantiate beans or mock services.
2. Understand precisely that `WebApplicationType.NONE` disables web application context and embedded web server creation, **not the Spring Boot lifecycle**.
3. Start a fresh `SpringApplication` in each test, configure `NONE`, pass separate arguments and properties, and close the context with `try-with-resources`.
4. Verify the order `ApplicationStartedEvent → ApplicationRunner → ApplicationReadyEvent` on the successful startup path.
5. Verify errors from `ApplicationRunner`: `SpringApplication.run` throws, `ApplicationFailedEvent` occurs, and **no** success-path ready event fires.
6. Observe `ContextClosedEvent` and verify cleanup after closing the context.
7. Register listeners **before calling `run`** to receive ultra-early events or failure events, instead of relying solely on `@EventListener` beans.
8. Compare `@SpringBootTest(webEnvironment = NONE)`, `@SpringBootTest(webEnvironment = MOCK)`, and `ApplicationContextRunner`.
9. Avoid leaking test contexts, thread pools, schedulers, and network ports; keep tests independent of execution order.
10. Write tests asserting **genuine lifecycle invariants**, rather than relying on `Thread.sleep`, arbitrary logs, or accidental behavior.

## 1. What does "real run" mean?

`SpringApplication` is Spring Boot's central entry point. With:

~~~java
ConfigurableApplicationContext context =
        new SpringApplication(MyApp.class).run(args);
~~~

Spring Boot still performs the real steps of application startup:

- Creating `SpringApplicationRunListeners` and emitting Boot startup events.
- Preparing `Environment` from properties, command-line arguments, profiles, and appropriate sources.
- Creating `ApplicationContext` and registering configuration/bean definitions.
- Refreshing the context: bean instantiation, dependency injection, `BeanPostProcessors`, `@PostConstruct`, and relevant lifecycle stages.
- Having auto-start `SmartLifecycle` beans participate in refresh.
- Emitting `ApplicationStartedEvent` after refresh.
- Running `ApplicationRunner` and `CommandLineRunner`.
- Emitting `ApplicationReadyEvent` once runners complete successfully.
- Returning the context to the caller, or transitioning to startup-failure handling if an error occurs.

**Difference from unit tests:** these components are not merely "faked" with mocks. The BeanFactory, configuration class processing, auto-configuration conditions, event publication, and runner callbacks all execute inside a real `ApplicationContext`.

**Difference from end-to-end HTTP tests:** this test **does not** verify socket listeners, embedded Tomcat startup, HTTP filters, servlet routing, requests/responses, or network traffic because the web environment is intentionally disabled.

### Common testing levels

| Technique | Real SpringApplication startup? | HTTP server? | Focus |
| --- | --- | --- | --- |
| Plain JUnit + mock dependencies | No | No | Class/method logic |
| Manually created `AnnotationConfigApplicationContext` | Has Spring bean lifecycle, but incomplete `SpringApplication` path | No | Spring Framework bean lifecycle |
| `ApplicationContextRunner` | Focused test context; not the full Boot application run path | No by default | Auto-configuration, conditions, bean definitions |
| `@SpringBootTest(webEnvironment = NONE)` | Yes; test framework uses `SpringApplication` | No | Full non-web application context |
| **Create `SpringApplication` and call `run` directly** | **Yes; caller explicitly controls the entire run and close** | No when set to `NONE` | Boot events, runners, startup failure, shutdown |
| `@SpringBootTest(webEnvironment = MOCK)` | Yes | No embedded server, yet provides a mock web environment when web is on classpath | Spring MVC/WebFlux test context |
| `@SpringBootTest(webEnvironment = RANDOM_PORT)` | Yes | Yes, binds a random port | Real HTTP integration |

Test selection depends on the goal. When testing the **main lifecycle** and effects of `SpringApplication`, calling `run(...)` directly is often clearer than a test annotation implicitly managed by the framework.

## 2. What does WebApplicationType.NONE do and not do?

Spring Boot provides enum `org.springframework.boot.WebApplicationType` with primary modes:

- `SERVLET`: creates a servlet-web application context and can start an embedded web server.
- `REACTIVE`: creates a reactive-web application context.
- `NONE`: creates a non-web `ApplicationContext`.

When unconfigured, Spring Boot deduces the web type from the classpath. If Spring MVC is present, Boot typically deduces `SERVLET`. In lifecycle tests, we can override it explicitly:

~~~java
SpringApplication app = new SpringApplication(MyApp.class);
app.setWebApplicationType(WebApplicationType.NONE);

try (ConfigurableApplicationContext context = app.run(args)) {
    // Test real context, without an HTTP server.
}
~~~

In Spring Boot 3.3's default setup, `NONE` creates an `AnnotationConfigApplicationContext` instead of an `AnnotationConfigServletWebServerApplicationContext`. Thus there is no need to pass `server.port=0` just to avoid port conflicts: **no embedded web server is created to bind a port**.

### NONE does not mean "no Spring"

`NONE` **does not** mean:

- Creating plain Java objects and skipping the BeanFactory.
- Skipping `@Configuration`, `@Bean`, auto-configuration, or dependency injection.
- Skipping `@PostConstruct`, `SmartLifecycle`, or bean destroy callbacks.
- Skipping `ApplicationRunner`, `CommandLineRunner`, or `ApplicationReadyEvent`.
- Skipping `ApplicationFailedEvent` on startup failure.
- Automatically mocking databases, filesystems, message brokers, or cloud services.
- Automatically disabling `@Scheduled`, `@Async`, background consumers, or application-created custom threads.
- Removing all web-related classes from the classpath.

It only changes the **application/context type and web runtime behavior**. External dependencies like DB/Redis/Kafka can still be auto-configured or connected if configuration and conditions allow.

### Stronger test: intentionally keeping the web starter

To prove `NONE` is an **explicit** decision rather than merely a consequence of missing servlet classes, the example project keeps `spring-boot-starter-web` on the classpath yet still forces `WebApplicationType.NONE`.

If you remove the `setWebApplicationType(NONE)` call, `SpringApplication` may auto-detect `SERVLET` and start Tomcat. Therefore, **keep this call inside the same factory method used by both `main` and tests**.

## 3. What is guaranteed in the Boot 3.3 lifecycle?

According to Spring Boot 3.3, the core event sequence can be summarized as:

~~~text
ApplicationStartingEvent
          |
ApplicationEnvironmentPreparedEvent
          |
ApplicationContextInitializedEvent
          |
ApplicationPreparedEvent
          |
     context refresh
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
SpringApplication.run returns context
~~~

These events apply to **`SpringApplication`**, even when `WebApplicationType` is `NONE`. Without a web server, **no `WebServerInitializedEvent` from a real embedded server** occurs during that non-web startup.

### Several critical distinctions

- `ApplicationStartedEvent` fires **after refresh** and **before runners**.
- `ApplicationReadyEvent` fires **after runners** complete successfully.
- `ApplicationFailedEvent` belongs to the **startup failure branch**.
- `ContextClosedEvent` is a Spring Framework event when a context is closed; it does not equate to Boot ready/failed.
- `ApplicationReadyEvent` does not guarantee every **lazy bean** has been instantiated, every network dependency stays healthy later, or every async task has finished.
- If a runner throws, `SpringApplication.run` does not return the context as on the success path; the framework runs the failure path and cleanup where possible.

In tests, assert **milestones guaranteed by contract**, rather than trying to assert every internal log line printed by Spring Boot.

### Do not turn all bean log lines into a "contract"

Two independent beans sharing the same lifecycle phase may have an implementation-dependent init/start order. A realistic lifecycle test should not force them into A–Z order without a matching dependency or phase. The example asserts the order:

~~~text
started → runner → ready → context close
~~~

This ordering comes from **Boot milestones and test-controlled actions**, not a claim that every bean in the context has a single fixed init order.

## 4. When to use new SpringApplication instead of static run?

Both calls create an application:

~~~java
SpringApplication.run(MyApp.class, args);
~~~

and:

~~~java
SpringApplication app = new SpringApplication(MyApp.class);
app.setWebApplicationType(WebApplicationType.NONE);
app.run(args);
~~~

The second form allows configuring **before running**:

- `setWebApplicationType(WebApplicationType.NONE)`.
- `setBannerMode(Banner.Mode.OFF)` to reduce unrelated output.
- `setLogStartupInfo(false)` to reduce informational startup logs.
- `setAdditionalProfiles(...)` when testing specific profiles.
- `setDefaultProperties(...)` for single-run default properties.
- `addListeners(...)` to capture events from the earliest stages.
- `addInitializers(...)` to modify the context **before refresh** when tests require it.

**Important:** Passing command-line args into `run(args)` is a convenient way to separate scenarios, such as `--demo.fail`. There is no need to mutate global `System.setProperty(...)` for each test.

You can also use `SpringApplicationBuilder(...).web(WebApplicationType.NONE)`, but this project uses the `SpringApplication` API directly to stay aligned with the lesson topic.

## 5. Designing a test suite that is both "real" and deterministic

The test suite verifies four core invariants:

1. **Web context:** the created context is `AnnotationConfigApplicationContext`, even with `spring-boot-starter-web` present.
2. **Successful lifecycle:** the code-recorded sequence is `started → runner → ready`; when the caller closes the context, `closed` is appended.
3. **Startup failure:** the runner is called yet throws an exception; the application emits `ApplicationFailedEvent` and does not emit `ApplicationReadyEvent` on the success path.
4. **Early registration:** a listener attached via `app.addListeners(...)` before `run(...)` sees `ApplicationStartingEvent` even though Spring beans do not exist yet at that time.

### Avoid turning test data into global state

Do not use a single `static List<String> events` shared across the entire test suite. It can retain data across contexts and cause JUnit to fail when running the whole suite even if a single test passes in isolation.

Instead, each `SpringApplication.run(...)` creates a fresh `StartupTrace` bean; each test holds its own reference. For events occurring before context initialization or during run failure, the test passes a separate list into `app.addListeners(...)`.

### Use try-with-resources to close the context

~~~java
try (ConfigurableApplicationContext context = app.run()) {
    // Assertions while context is active.
}
// context.close() has already been called.
~~~

`ConfigurableApplicationContext` implements `Closeable`, so it works in `try-with-resources`. Closing the context is crucial in tests because an unclosed context can retain thread pools, scheduled tasks, connection pools, shutdown callbacks, or test resources.

**Do not close the context and then call `context.getBean(...)` for further checks.** To inspect traces after close, obtain a reference to a dedicated tracking object **before closing**, then read that object's snapshot afterward.

## 6. Runnable project: Java 17 / Spring Boot 3.3.13 / JUnit 5

The project has two main Java files: the application and tests calling real `SpringApplication.run(...)`. The build includes the web starter **to prove `NONE` overrides auto-detection**, without opening an HTTP server.

### 6.1. Directory structure

~~~text
real-spring-run-test/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/realrun/
    │   └── RealRunApplication.java
    └── test/java/com/example/realrun/
        └── RealRunApplicationTests.java
~~~

**File `settings.gradle`:**

~~~groovy
rootProject.name = 'real-spring-run-test'
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
    // Intentionally include Spring MVC/Tomcat on classpath.
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}

springBoot {
    mainClass = 'com.example.realrun.RealRunApplication'
}
~~~

**Requirements:** Java 17+ and Gradle compatible with Spring Boot 3.3.x; Maven Central may require network access to fetch dependencies on the first build. The project does not include a Gradle Wrapper; if one is present, use the wrapper instead of `gradle`.

### 6.2. Real application, trace bean, and runner

**File `src/main/java/com/example/realrun/RealRunApplication.java`:**

~~~java
package com.example.realrun;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class RealRunApplication {

    public static void main(String[] args) {
        SpringApplication app = newNonWebApplication();

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println(
                    "MAIN: active=" + context.isActive());
        }

        System.out.println("MAIN: context closed");
    }

    public static SpringApplication newNonWebApplication() {
        SpringApplication app =
                new SpringApplication(RealRunApplication.class);

        // Override even when spring-boot-starter-web is present.
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        return app;
    }

    @Bean
    StartupTrace startupTrace() {
        return new StartupTrace();
    }

    @Bean
    ApplicationRunner demoRunner(StartupTrace trace) {
        return arguments -> {
            trace.record("runner");

            if (arguments.containsOption("demo.fail")) {
                throw new IllegalStateException(
                        "intentional runner failure");
            }
        };
    }

    public static final class StartupTrace {

        private final List<String> events =
                new CopyOnWriteArrayList<>();

        public void record(String event) {
            events.add(event);
            System.out.println("TRACE: " + event);
        }

        public List<String> snapshot() {
            return List.copyOf(events);
        }

        @EventListener
        public void onStarted(ApplicationStartedEvent event) {
            record("started");
        }

        @EventListener
        public void onReady(ApplicationReadyEvent event) {
            record("ready");
        }

        @EventListener
        public void onClosed(ContextClosedEvent event) {
            record("closed");
        }
    }
}
~~~

**Rationale for each decision:**

- `newNonWebApplication()` is shared between `main` and tests. If `main` changes `WebApplicationType` configuration, tests exercise the same **initialization path** rather than a different configuration.
- `setWebApplicationType(NONE)` is called before `run`, so Boot does not create a servlet web server despite the web starter being present.
- `@Bean StartupTrace` is a fresh bean per context. `CopyOnWriteArrayList` keeps snapshots thread-safe if another callback reads the trace.
- Three `@EventListener` methods observe events from the **initialized context**: Started, Ready, and ContextClosed.
- `ApplicationRunner` is invoked by Boot at its proper lifecycle position. It prints `runner` after Started and before Ready.
- The `--demo.fail` command-line flag is detected via `ApplicationArguments.containsOption("demo.fail")`. When present, the runner intentionally throws an exception.
- Using a single runner and a single trace bean ensures the example does not depend on arbitrary ordering among multiple runners or multiple lifecycle peers.
- `main` prints `active=true` **after `run` returns**. It opens no port and runs no HTTP server; immediately afterward, the context is intentionally closed because this is a CLI demo.

In a long-running web application, you **should not** close the context immediately when `run` returns as in the demo, since the goal is serving traffic; closing immediately here lets us observe shutdown in CLI tests.

### 6.3. JUnit tests calling real SpringApplication.run

**File `src/test/java/com/example/realrun/RealRunApplicationTests.java`:**

~~~java
package com.example.realrun;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.junit.jupiter.api.Test;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RealRunApplicationTests {

    @Test
    void realRunIsNonWebAndClosesInLifecycleOrder() {
        SpringApplication app =
                RealRunApplication.newNonWebApplication();

        RealRunApplication.StartupTrace trace;

        try (ConfigurableApplicationContext context = app.run()) {
            assertInstanceOf(
                    AnnotationConfigApplicationContext.class, context);
            assertTrue(context.isActive());

            trace = context.getBean(
                    RealRunApplication.StartupTrace.class);

            assertEquals(
                    List.of("started", "runner", "ready"),
                    trace.snapshot());
        }

        assertEquals(
                List.of("started", "runner", "ready", "closed"),
                trace.snapshot());
    }

    @Test
    void runnerFailureEmitsFailedEventWithoutReadyEvent() {
        SpringApplication app =
                RealRunApplication.newNonWebApplication();

        List<String> signals = new CopyOnWriteArrayList<>();

        app.addListeners(
                (ApplicationListener<ApplicationStartedEvent>)
                        event -> signals.add("started"),
                (ApplicationListener<ApplicationReadyEvent>)
                        event -> signals.add("ready"),
                (ApplicationListener<ApplicationFailedEvent>)
                        event -> signals.add("failed"));

        RuntimeException thrown = assertThrows(
                RuntimeException.class,
                () -> app.run("--demo.fail"));

        assertTrue(
                hasMessageInCauseChain(
                        thrown, "intentional runner failure"));

        assertTrue(signals.contains("started"));
        assertTrue(signals.contains("failed"));
        assertFalse(signals.contains("ready"));
    }

    @Test
    void listenerRegisteredBeforeRunReceivesStartingEvent() {
        SpringApplication app =
                RealRunApplication.newNonWebApplication();

        List<String> signals = new CopyOnWriteArrayList<>();

        app.addListeners(
                (ApplicationListener<ApplicationStartingEvent>)
                        event -> signals.add("starting"));

        try (ConfigurableApplicationContext context = app.run()) {
            assertTrue(context.isActive());
        }

        assertEquals(List.of("starting"), signals);
    }

    private static boolean hasMessageInCauseChain(
            Throwable original, String fragment) {

        for (Throwable cursor = original;
                cursor != null;
                cursor = cursor.getCause()) {

            String message = cursor.getMessage();

            if (message != null && message.contains(fragment)) {
                return true;
            }
        }

        return false;
    }
}
~~~

**Notable point:** This test invokes **real `SpringApplication.run(...)`**, with no `@MockBean` for the runner and without merely instantiating `AnnotationConfigApplicationContext` manually. The test starts the Boot lifecycle and verifies official milestones.

### 6.4. Why is each test isolated independently?

The first test uses its own `SpringApplication` and `StartupTrace`, closes the context in `try-with-resources`, and retains the `trace` reference to verify the close event.

The second test creates a **new** `SpringApplication`, registers application listeners **before** `run`, and intentionally passes `--demo.fail`. Because `run` throws, there is no successful context to put into `try-with-resources`; Spring Boot handles its own failure path. The test simply observes the exception and application events externally.

The third test also creates a new app and records only `ApplicationStartingEvent`, an event fired **before beans exist**. Do not use an `@EventListener` bean to catch it.

**No static mutable trace** and no dependence on JUnit execution order. This allows running individual tests, the full class, or parallel runs under suitable configuration without mixing data across contexts.

## 7. Running tests and running main

### 7.1. Running JUnit 5

From the `real-spring-run-test` directory:

~~~bash
gradle test
~~~

If Gradle Wrapper is present:

~~~bash
./gradlew test
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

The sample project **does not include a wrapper**; use `gradle test` when only an installed Gradle is available.

All expected tests **PASS**:

~~~text
RealRunApplicationTests
  realRunIsNonWebAndClosesInLifecycleOrder()       PASS
  runnerFailureEmitsFailedEventWithoutReadyEvent() PASS
  listenerRegisteredBeforeRunReceivesStartingEvent() PASS
~~~

This is an **expected test result list**, not a claim that Gradle prints this exact format to the console: different Gradle/JUnit versions may render summaries and stdout differently. The intentional runner failure case may print stack trace logs from Boot, yet **the test still PASSES** because `assertThrows` is used.

**QA distinction:** `assertThrows` catches the exception inside the test JVM, so this **is not** an exit code test of a separate Java process. To verify the OS exit code, spawn a child JVM or run the executable JAR from a shell.

### 7.2. Running main on the success path

~~~bash
gradle bootRun
~~~

Lines printed by **project code** in order, ignoring Spring Boot/Gradle logs:

~~~text
TRACE: started
TRACE: runner
TRACE: ready
MAIN: active=true
TRACE: closed
MAIN: context closed
~~~

Explanation:

1. Context refreshed → `ApplicationStartedEvent` → trace records `started`.
2. `ApplicationRunner` runs → records `runner`.
3. Runner finishes → `ApplicationReadyEvent` → records `ready`.
4. `SpringApplication.run` returns → `main` prints `active=true`.
5. Exits `try-with-resources` → context closes → `ContextClosedEvent` records `closed`.
6. `main` continues → `MAIN: context closed`.

No "Tomcat started on port ..." line appears from the demo application despite `spring-boot-starter-web` being in dependencies, because Boot is forced to `NONE`.

### 7.3. Running main with runner failure

~~~bash
gradle bootRun --args="--demo.fail"
~~~

Lines printed by the **application's trace** on the typical failure path:

~~~text
TRACE: started
TRACE: runner
TRACE: closed
~~~

There is no `TRACE: ready`, `MAIN: active=true`, or `MAIN: context closed` because `app.run(...)` throws before returning the context to `main`. Spring Boot may print additional exceptions, error reports, or stack traces; Gradle may mark `bootRun` as failed because the Java process exited with an error.

**Note:** `ContextClosedEvent` is observed in the runner failure case **after the context has refreshed and can be closed**. If a failure happens very early before the context exists, do not expect these exact three lines or a close event.

### 7.4. No need for server.port=0

Setting `server.port=0` in a **SERVLET** app tells the server to pick a random port; it **still opens a socket**. In `NONE`, there is no embedded web server, so setting a random port has no network-testing meaning.

If the goal is **real HTTP integration**, use `@SpringBootTest(webEnvironment = RANDOM_PORT)` or directly create a servlet app with an appropriate port instead of `NONE`.

## 8. Assertions to include and avoid

### Strong assertions

~~~java
assertInstanceOf(
        AnnotationConfigApplicationContext.class, context);

assertTrue(context.isActive());

assertEquals(
        List.of("started", "runner", "ready"),
        trace.snapshot());
~~~

These assertions are in the complete project. They verify the **real context** and **Boot event/runner ordering** without assuming speed or milliseconds between events.

### Assertion when the context closes

~~~java
assertEquals(
        List.of("started", "runner", "ready", "closed"),
        trace.snapshot());
~~~

The `closed` entry appears only when the context has actually closed. You can add a bean with `@PreDestroy` and a counter to test destruction callbacks if needed by your scenario.

### Failure path assertions

~~~java
assertTrue(signals.contains("started"));
assertTrue(signals.contains("failed"));
assertFalse(signals.contains("ready"));
~~~

This is a more stable check than hardcoding entire error logs or stack traces printed by Boot. The test intentionally makes the runner throw without assuming English/Vietnamese error reports or stack trace formatting.

### Error-prone assertions

Avoid:

- Asserting exact lines of Spring Boot startup logs; log levels and versions change.
- Asserting fixed durations like "context must start within 200 ms" across all CI machines.
- Asserting that all `SmartLifecycle` beans in the same phase start in name or source order.
- Relying on `Thread.sleep(1000)` and assuming an event fired; use listeners/latches/actual state.
- Asserting HTTP port 8080 returns a response, since `NONE` mode has no HTTP server.
- Fetching a bean after the context has closed if the bean requires an active BeanFactory.
- Concluding `ready` means all external dependencies remain healthy forever.

## 9. Why is @SpringBootTest(NONE) similar yet different from calling run directly?

In Spring Boot Test:

~~~java
@SpringBootTest(
        classes = RealRunApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ContextOnlyTest {
    // @Autowired ApplicationContext, @Test methods...
}
~~~

This is an **illustrative snippet**, not added to the runnable project since it lacks full test bodies/imports. `@SpringBootTest(webEnvironment = NONE)` also creates a context via `SpringApplication` and provides neither a mock nor a real web environment.

### Differences in context ownership

| Criterion | Self-created SpringApplication + run | @SpringBootTest(webEnvironment = NONE) |
| --- | --- | --- |
| Who calls `run`? | Test directly | Spring TestContext framework |
| Who closes the context? | Test directly, usually via `try-with-resources` | Spring TestContext/cache lifecycle |
| Context caching across test methods | No, if each test creates a new app | Can cache compatible configurations |
| Customizing app before `run` | Directly via setters/listeners/initializers | Via annotations, properties, context customizers, or `useMainMethod` |
| Observing events before context creation | Easy via `app.addListeners` | Requires listener mechanisms compatible with TestContext |
| Testing `SpringApplication.run` failure | Easy with `assertThrows` | Context load failure managed by framework; needs different strategy |
| Testing shutdown right inside a method | Easy because `close()` is controlled directly | Does not close context after each test method by default |
| Real web server | No when NONE | No when NONE |

**Note on `main` method:** `@SpringBootTest` should not be assumed to always invoke code inside the application's `public static void main`. If `NONE` configuration sits only in `main` via a setter, `@SpringBootTest` tests may need `spring.main.web-application-type=none` or appropriate `useMainMethod` settings. This matters especially if you must ensure tests run customizations placed in the production entrypoint.

### NONE and MOCK differ even though neither opens a port

- `MOCK` (`@SpringBootTest` default) can create a **mock web application context** if the classpath supports it.
- `NONE` has no web environment, not even a mock one.
- `RANDOM_PORT` creates a web application context with a real embedded server binding a random port.
- Do not infer from "no real port" that all modes are identical.

### When to choose @SpringBootTest

If the goal is testing injection, service composition, and configuration with caching for a fast suite, `@SpringBootTest(webEnvironment = NONE)` is usually sufficient and simple. If you want to test **a specific `SpringApplication` failure path** or event/close ordering in **an isolated run**, this lesson's direct invocation pattern gives better control.

## 10. What scope does ApplicationContextRunner fit?

Spring Boot Test provides `ApplicationContextRunner` to test auto-configuration/conditions/bean definitions in a lightweight environment.

Illustrative snippet:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(MyConfiguration.class)
        .withPropertyValues("feature.enabled=true")
        .run(context -> {
            assertThat(context).hasSingleBean(MyService.class);
        });
~~~

This is an **AssertJ/Spring Boot Test snippet**, requiring config and service definitions and imports. It is useful when asking:

- Is a bean created when a property is enabled?
- Does an auto-configuration back off when a user bean is present?
- Do `@ConditionalOnClass`/`@ConditionalOnProperty` evaluate properly?
- Does a bean definition fail during binding?

However, **do not confuse** `ApplicationContextRunner` with a full `SpringApplication.run` carrying the complete Boot startup-runner and application-event path. When the requirement is **"testing a real run with `SpringApplication`"**, use the direct run path as in section 6.

## 11. Capturing ultra-early events: addListeners before run

A bean such as:

~~~java
@Component
class EarlyListener {

    @EventListener
    public void starting(ApplicationStartingEvent event) {
        System.out.println("starting");
    }
}
~~~

is an **unsuitable pattern for catching ultra-early events**; imports are omitted. `ApplicationStartingEvent` fires before the context and beans are created. The `EarlyListener` bean cannot yet be instantiated by Spring to handle that event.

Better:

~~~java
SpringApplication app = new SpringApplication(MyApp.class);

app.addListeners(
        (ApplicationListener<ApplicationStartingEvent>)
                event -> earlyEvents.add("starting"));

app.setWebApplicationType(WebApplicationType.NONE);
app.run(args);
~~~

This is an **illustrative snippet**, requiring `MyApp`, `earlyEvents`, and imports. The listener is registered with Boot **before** startup begins, so it can receive `ApplicationStartingEvent`.

### ApplicationFailedEvent also requires phase awareness

If a failure occurs before context refresh completes, an `@EventListener` bean may not exist yet. For tests intentionally making `ApplicationContextInitializer` throw, a listener registered early via `addListeners(...)` is the right way to observe the failure.

Events are published synchronously by default, yet if an application configures an async multicaster or multiple contexts in a hierarchy, assumptions about threads/ordering must be revisited. For simple tests and default settings in this project, the stated event trace order holds.

## 12. Testing a real ApplicationRunner instead of calling run directly

If a test only executes:

~~~java
new MyRunner().run(arguments);
~~~

it only proves the runner's own logic. It does not verify:

- The `ApplicationRunner` bean is properly registered by Spring.
- Dependency injection into the runner succeeds.
- The context refreshes before the runner runs.
- Boot invokes the runner at startup.
- `ApplicationReadyEvent` fires only after the runner.
- Runner exceptions enter Boot's startup-failure flow.
- The context is cleaned up after an error.

That is why the example uses `@Bean ApplicationRunner` and lets `SpringApplication.run` invoke it for real.

### When should direct unit tests still exist?

If a runner implements complex algorithms, extract logic into a service and unit-test many cases with fake collaborators. Then use **a few integration tests** like this to verify wiring and lifecycle contracts. Do not turn every small business logic test into an unnecessary full-context startup.

## 13. Testing ContextClosedEvent and real cleanup

In the example, the trace receives `ContextClosedEvent`. This signals that the Spring context is closing; it **does not automatically prove every resource was released successfully**.

To test a real resource, you can add a bean:

~~~java
@Bean
CloseableResource resource() {
    return new CloseableResource();
}
~~~

And:

~~~java
final class CloseableResource implements AutoCloseable {
    private final AtomicBoolean closed = new AtomicBoolean();

    @Override
    public void close() {
        closed.set(true);
    }

    boolean isClosed() {
        return closed.get();
    }
}
~~~

These are **two illustrative snippets**, requiring the class, imports, and an appropriate destroy method. When used as a bean, declare `@Bean(destroyMethod = "close")` so Spring calls `close` on destruction. Grab a reference before `context.close()`, then assert `isClosed() == true`.

**Order note:** `ContextClosedEvent` fires as the context starts closing; it does not mean every `@PreDestroy`/destroy method has finished at the exact instant the listener runs. To assert destroy callback execution, **read state after `context.close()` returns**, not solely inside the listener.

### Cleanup on startup failure

When a runner fails **after refresh**, Boot closes the context while handling startup failure, so fully initialized beans can receive destroy callbacks. However, if an error occurs in a constructor/factory/`@PostConstruct` **before bean initialization succeeds**, partially opened resources must still be cleaned up manually; do not expect Spring to clean up local resources it does not know about.

### Never use System.exit() in JUnit

`System.exit(code)` can terminate the entire JVM running the test suite. To test real exit codes, launch a child JVM with `ProcessBuilder`; to test `SpringApplication`'s failure path, use `assertThrows(...)`.

## 14. Ensuring tests do not affect one another

### Each test creates a fresh app and context

~~~java
SpringApplication app =
        RealRunApplication.newNonWebApplication();

try (ConfigurableApplicationContext context = app.run()) {
    // Assertions specific to this test.
}
~~~

This is a simple way to avoid cross-test cache dependencies. Trade-off: booting a full context can take time; large test suites should balance this with `@SpringBootTest` caching or test slices.

### Avoid global System properties

If Test A calls:

~~~java
System.setProperty("demo.fail", "true");
~~~

and forgets to restore it, Test B can be affected. Prefer **single-run** command-line arguments or `setDefaultProperties` on the test's own `SpringApplication`.

### Watch out for actors surviving outside the context

- Threads created manually via `new Thread` may not be stopped by Spring.
- Bean-managed executors need proper stop/destroy hooks.
- `@Scheduled` schedulers can generate unintended work.
- Kafka/RabbitMQ listeners can open connections if the real app has dependencies and config.
- Flyway/Liquibase or initializers can connect to the DB automatically.
- Static caches, non-Spring singletons, and global registries can leak state across runs.

`NONE` **does not automatically mock or disable** these behaviors. Supply appropriate fake/test beans or profiles, without replacing the very lifecycle target you intend to test.

### Avoid unnecessary repeated full-context runs

If you have hundreds of logic-only tests, use plain JUnit or `ApplicationContextRunner` for most of them and reserve a few `SpringApplication.run` tests for key lifecycle contracts. This is the trade-off between realism and CI speed.

## 15. Testing properties, args, and profiles in NONE

### Command-line options

In the runner:

~~~java
if (arguments.containsOption("demo.fail")) {
    throw new IllegalStateException("intentional runner failure");
}
~~~

The `--demo.fail` argument is parsed by `ApplicationArguments`. Tests do not need to write resource files or mutate global state.

### Setting default properties on the test app

~~~java
SpringApplication app =
        RealRunApplication.newNonWebApplication();

app.setDefaultProperties(
        Map.of("demo.feature.enabled", "true"));
~~~

This is a snippet requiring `java.util.Map`. Default properties have lower precedence than several other property sources; if a test requires guaranteed overrides, choose command-line options or appropriate test property mechanisms.

### Profiles

~~~java
SpringApplication app =
        RealRunApplication.newNonWebApplication();

app.setAdditionalProfiles("test");
~~~

This is a snippet using the `SpringApplication` API. Profiles affect bean conditions and configuration without mutating JVM-wide state. Still, recognize that a real app may have `@Profile`/conditional beans requiring mocked resources.

### Environment and readiness

A property assertion only shows that `Environment` received data; it does not prove an external dependency is healthy. If a real startup gate is needed, create a runner or lifecycle component checking the condition and assert ready/failure events per contract.

## 16. Test scenarios that must be separated

### Scenario A — Bean init failure test

A bean with `@PostConstruct` throws an exception before refresh finishes. In that case, **do not** assert that `ApplicationStartedEvent` occurred; Boot can emit `ApplicationFailedEvent` very early. Register listeners via `app.addListeners(...)` before `run`.

### Scenario B — Runner failure after refresh

This is the project's `--demo.fail` mode. `ApplicationStartedEvent` has occurred, `ApplicationReadyEvent` has not, and `run` will throw. Tests can assert these signals.

### Scenario C — A `SmartLifecycle.start()` bean fails

If auto-start during refresh throws an exception, the context may not have finished `refresh`. Therefore, the event path differs from runner failure. The bean must roll back resources opened inside `start()` rather than relying solely on subsequent shutdown callbacks.

### Scenario D — Runtime failure after ready

Once `SpringApplication.run` has returned the context, an HTTP handler or message consumer throwing at runtime **does not automatically** go through the startup-failure path. To test such errors, test error handlers, retry/DLQ, availability, or service logic per the corresponding technology.

### Scenario E — CLI exits immediately after startup

A non-web CLI may run its runner and have `main` close the context and exit. Do not interpret "exiting immediately" as a startup failure if exit code is 0 and required tasks completed.

## 17. When SmartLifecycle needs testing in the same project

`SmartLifecycle` lets a bean auto-start during refresh and stop when the context closes.

An illustrative class:

~~~java
final class ProbeLifecycle implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        running = true;
    }

    @Override
    public void stop() {
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
~~~

This is an **illustrative class snippet**, requiring importing `org.springframework.context.SmartLifecycle`. In Spring Framework 6.1, `SmartLifecycle` has default implementations for the remaining methods, yet production components should implement `stop(Runnable callback)` per contract when shutdown involves asynchronous work.

If you add a lifecycle bean to the project, you can verify `start` occurs before Boot's `ApplicationStartedEvent` and `stop` occurs before context close completes. However, **do not** assert absolute ordering between two independent beans sharing the same phase; phases/dependencies define the constraints.

**A limitation:** a component setting `running=true` right upon submitting an async connection is not necessarily business-ready. Testing lifecycle "start was called" differs from testing "remote dependency is truly ready".

## 18. Troubleshooting: signs a test is off-target

### Tomcat starts even though the test expects NONE

Check:

1. Did the test actually call `newNonWebApplication()`?
2. Was **another** `SpringApplication.run(MyApp.class)` created without the setter?
3. Did the test use `@SpringBootTest` with default web configuration instead of `NONE`?
4. Is a custom application context factory/bootstrap altering semantics?
5. Is Spring MVC on the classpath so Boot auto-detected `SERVLET` when `setWebApplicationType` was omitted?

### Test hangs after assertions complete

A non-daemon thread, timer, executor, or unclosed context may still be alive. Check:

- Did `try-with-resources` reach `close`?
- Did any bean spawn its own thread?
- Is any `@Scheduled` task or consumer still active?
- Did `SmartLifecycle.stop(Runnable)` invoke its callback upon completion?
- Is a task ignoring interrupts?
- Was a second context created and left unclosed?

`NONE` does not guarantee the JVM will exit if you spawn unmanaged non-daemon threads.

### Context fails on database even though the test doesn't use a database

If dependencies/configuration trigger DB auto-configuration, the context may require a DataSource, credentials, or migrations. `NONE` only removes the web runtime; it does not exclude DB conditions. Tests should:

- Use a specific test profile/config.
- Provide a fake in-memory database if the goal is lifecycle.
- Use intentional auto-configuration exclusions when DB is out of scope.
- Avoid randomly disabling parts of init that turn the test into a context wholly unlike the real application.

### Test sees Started but never sees Ready

Check startup runners, exceptions inside a runner, or a runner blocked indefinitely. `ApplicationStartedEvent` fires **before** runners. If a runner throws, no successful ready event occurs.

### Failure test lacks ContextClosedEvent

If the error occurs very early and the context was never created/refreshed, the close event may not fire as it does in runner failure. Do not assert events not guaranteed by contract for every failure point.

### Test passes alone yet fails when running the full suite

Often caused by static mutable state, system properties, context cache, shared ports, parallel tests, file fixtures, or resource leaks. This test pattern keeps traces per context, opens no web port, and requires no test execution order.

### Test does not see ApplicationStartingEvent in a bean

That is expected behavior: the event occurs before bean creation. Use `app.addListeners(...)` or an early registration mechanism.

### Test uses @SpringBootTest and misses main customizations

Spring TestContext does not necessarily invoke the application's `main` method as written. Use `@SpringBootTest(useMainMethod = ...)` when needed/supported by your version, configure `spring.main.web-application-type=none`, or construct `SpringApplication` and call `run` directly as in this lesson.

## 19. Testing after context.close returns

A quality lifecycle test not only sees the `closed` event, it also verifies resources were released.

Example checking a resource bean:

~~~java
CloseableProbe resource;

try (ConfigurableApplicationContext context = app.run()) {
    resource = context.getBean(CloseableProbe.class);
    assertFalse(resource.isClosed());
}

assertTrue(resource.isClosed());
~~~

This is an **illustrative test snippet**, requiring a `CloseableProbe` bean with a destroy method and assertion imports. It distinguishes:

- **Event emitted:** the context began closing.
- **Destroy callback ran:** the bean cleaned itself up.
- **External resource truly released:** requires corresponding logic or API observation, not just a boolean.

To prove no pending tasks or live threads remain, use `CountDownLatch`, `Future`/`awaitTermination` with timeouts; never use `Thread.sleep` and infer from elapsed time.

## 20. Common mistakes

**1. "`WebApplicationType.NONE` skips the entire Boot lifecycle."** False; it only disables the web runtime while still running context/beans/events/runners.

**2. "Having `spring-boot-starter-web` forces Tomcat to start."** False when `SpringApplication` is explicitly set to `NONE`.

**3. "Not opening a port means no real `SpringApplication` is created."** False; `SpringApplication` can run a full non-web lifecycle.

**4. "`@SpringBootTest` always creates a real web server by default."** False; default `MOCK` does not open an embedded server, though it can create a mock web environment.

**5. "`@SpringBootTest` NONE and MOCK are identical."** False; `NONE` creates no web environment, whereas `MOCK` can create a mock web context.

**6. "Merely calling `runner.run()` tests the `SpringApplication` lifecycle."** No; it skips BeanFactory, Boot event ordering, failure handling, and context closing.

**7. "`ApplicationStartedEvent` proves runners have finished."** False; runners execute **after** Started.

**8. "`ApplicationReadyEvent` fires even when a runner throws."** Not on Boot's successful startup path.

**9. "`ApplicationFailedEvent` happens only if the HTTP server fails to bind a port."** False; many other startup exceptions cause failures.

**10. "An `@EventListener` bean receives `ApplicationStartingEvent`."** Unreliable, because the event fires before beans are created.

**11. "No need to close contexts in JUnit."** False; contexts can hold threads/pools/files/listeners.

**12. "`ContextClosedEvent` means `@PreDestroy` has already finished at the moment of the event."** False; lifecycle destruction continues after the event.

**13. "`NONE` automatically mocks databases, Kafka, and cloud SDKs."** No; other dependencies can still initialize for real.

**14. "`setWebApplicationType(NONE)` means all web beans are automatically deleted."** No; only auto-configurations conditioned on web types adjust to non-web; user beans follow their own configurations.

**15. "`server.port=0` equals `NONE`."** No; port 0 opens an embedded server on a random port when running as a web app.

**16. "A second run sharing the first run's trace is normal."** Not if tests expect independent contexts; avoid static state and global registries.

**17. "Only testing expected stack trace text suffices."** Brittle; assert events, exception types/causes, and state.

**18. "`assertThrows` in a test means the OS received a nonzero exit code."** No; JUnit catches the exception inside the test JVM without producing a separate process exit code.

**19. "`@SpringBootTest` always calls the `main` method."** Not by default; check `useMainMethod`/entrypoint policy.

**20. "Ready means every lazy bean is valid."** No; lazy beans can fail on first use.

**21. "`@Scheduled` tasks auto-disable in `NONE`."** No; schedulers can run if enabled and registered as beans.

**22. "Seeing `ContextClosedEvent` proves executors terminated."** No; verify task shutdown/callbacks.

**23. "The log order of two beans in the same phase is an API contract."** No; assert only guaranteed phases/dependencies.

**24. "`Thread.sleep` in JUnit stabilizes lifecycle tests."** No; use listeners/latches/timeout-aware assertions.

**25. "Real run tests are always better than unit tests at every level."** No; full-context tests are heavier, so combine multiple testing levels.

## 21. Practice exercises

1. Why does `WebApplicationType.NONE` still allow `ApplicationRunner` to run?
2. With `spring-boot-starter-web` on the classpath, why does the sample project still create a non-web `AnnotationConfigApplicationContext`?
3. Distinguish `NONE` from `server.port=0`.
4. Explain the order `started → runner → ready` in the trace.
5. Why is `ContextClosedEvent` only tested after exiting `try-with-resources`?
6. Run `gradle test`. Which contracts do the three tests verify, and do they depend on JUnit order?
7. Run `gradle bootRun`. Why does `main` print `active=true` after the `ready` trace?
8. Run `gradle bootRun --args="--demo.fail"`. Why do neither `ready` nor `main` success messages appear?
9. Register an `ApplicationFailedEvent` listener before `run`. Why can this observe failures even when listener beans have not yet initialized?
10. Add an `ApplicationContextInitializer` that intentionally throws. Compare the events with runner failure.
11. Why might an `@EventListener(ApplicationStartingEvent.class)` listener never be invoked?
12. Create a bean with `@PostConstruct` recording a trace and verify it appears before `ApplicationStartedEvent`.
13. Create a `SmartLifecycle`, assert start before Started, and stop before context close returns.
14. If two beans share the same phase, should you assert their order by name? When order is needed, which mechanism should you use?
15. Add a `CloseableProbe` bean with `destroyMethod="close"`; assert its state before/after `context.close`.
16. Change `NONE` to `SERVLET` and set `server.port=0` in a sandbox. How do the context type and port-binding behavior differ?
17. Use `@SpringBootTest(webEnvironment = NONE)` instead of direct `run`. Who owns the context and when does it close?
18. Why does `@SpringBootTest(MOCK)` not replace a non-web test when the goal is having no web environment?
19. Use `ApplicationContextRunner` to test `@ConditionalOnProperty`; why not use it as proof of the full Boot event order?
20. Run `SpringApplication.run` twice in one test, close each context, and assert distinct trace instances.
21. Test a bean needing a database when no DB is present. Does `NONE` automatically resolve that dependency error?
22. When a test has external threads, how should you assert to avoid leaking tasks after close?
23. Why shouldn't `System.exit` be called from a runner during JUnit tests?
24. To measure the process exit code of a startup failure, design a test using `ProcessBuilder` to spawn a child JVM.
25. Write an integration test independent of logs, verifying event order via trace and failure events via listeners.
26. If lazy initialization is enabled, can a broken bean still remain uncreated before ready?
27. An app only needs service logic tested. When are pure unit tests more useful than full `SpringApplication.run`?
28. Why is a test class with a static mutable events list prone to failing when the test suite runs in parallel?
29. Add a property via `app.setDefaultProperties(...)` in a single test and verify it does not alter other tests.
30. Outline a checklist to prove "real, non-web run with complete startup and cleanup" for a Spring Boot CLI application.

## Key takeaways

- `SpringApplication.setWebApplicationType(WebApplicationType.NONE)` **disables the web application runtime**, not the Spring Boot context, beans, lifecycle events, or runners.
- **Real run tests** call `SpringApplication.run(...)`, receive a real `ConfigurableApplicationContext`, assert while active, and **close the context** intentionally.
- In Spring Boot 3.3: **Started → runners → Ready** on successful startup; a runner throwing leads to startup failure and no Ready on the success path.
- To observe events **before the context exists**, register via `app.addListeners(...)` before `run`.
- `@SpringBootTest(webEnvironment = NONE)` is also a non-web Boot test, yet the context is managed by Spring TestContext and may be cached, unlike creating/closing a context per method.
- `NONE` does not automatically mock DB, Kafka, schedulers, external APIs, thread pools, or security/validation.
- `ContextClosedEvent` is a context-closing milestone, **not proof that every external resource has stopped**; test destroy callbacks and termination when needed.
- Never use `System.exit` in JUnit or `Thread.sleep` to guess event order.
- Combine full-run integration tests with unit tests, context-runner tests, and HTTP integration tests at the proper scopes.

### References

- Spring Boot 3.3 — SpringApplication, Web Environment, Application Events and Runners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Testing Spring Boot Applications, WebEnvironment NONE/MOCK/RANDOM_PORT: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — SpringApplication Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3 — WebApplicationType Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/WebApplicationType.html
- Spring Boot 3.3 — ApplicationArguments Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html
- Spring Boot 3.3 — SpringBootTest Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/SpringBootTest.html
- Spring Framework 6.1 — ConfigurableApplicationContext: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html
- Spring Framework 6.1 — AnnotationConfigApplicationContext: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/AnnotationConfigApplicationContext.html
- Spring Framework 6.1 — ContextClosedEvent: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/event/ContextClosedEvent.html
- JUnit 5 — User Guide: https://junit.org/junit5/docs/current/user-guide/
