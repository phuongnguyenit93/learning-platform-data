# ApplicationFailedEvent and the Limits of Still-Usable Resources When Spring Boot Fails to Start

## 1. Problem statement: startup failure does not mean a usable container still exists

When `SpringApplication.run(...)` is called, Spring Boot goes through multiple steps: building the `Environment`, creating the `ApplicationContext`, loading bean definitions, refreshing the context, instantiating singletons, starting the web server (if present), running `ApplicationRunner`/`CommandLineRunner`, and only then publishing readiness. An exception at any critical step can cause startup to fail.

Spring Boot provides `org.springframework.boot.context.event.ApplicationFailedEvent` to **signal that a startup attempt has failed**. A failure listener can obtain the exception and partial context about the run. At that moment, however, you must never assume:

- `ApplicationContext` was created.
- `ApplicationContext` refreshed successfully.
- Every `@Bean`/`@Component` was instantiated.
- `getBean(...)` will return a working service.
- `DataSource`, HTTP clients, or message brokers can still be queried.
- Executors can accept new tasks.
- The web server is already accepting traffic or readiness is `ACCEPTING_TRAFFIC`.
- Spring cleanup has not started yet or is guaranteed to complete fully.

**Core rule:** `ApplicationFailedEvent` is appropriate for **recording startup failure diagnostics**, not as a signal that a listener is entitled to execute additional business logic through leftover resources in the context.

This lesson targets **Java 17+, Spring Boot 3.3.x, and Spring Framework 6.1.x**; it distinguishes early listeners from Spring bean listeners, resource readiness levels, safe cleanup, pitfalls of calling `getBean` inside failure callbacks, and a runnable Java 17+ program simulating both a failure **before context exists** and a failure from `ApplicationRunner` **after context refresh**.

## 2. What is ApplicationFailedEvent?

`ApplicationFailedEvent` extends `SpringApplicationEvent`. Per the Spring Boot 3.3 API, it is published by `SpringApplication` when **startup cannot complete**.

Essential APIs:

```java
ApplicationFailedEvent event;

Throwable error = event.getException();

ConfigurableApplicationContext context =
        event.getApplicationContext();

SpringApplication application = event.getSpringApplication();

String[] args = event.getArgs();
```

This is an **API-illustrative snippet only**, not a standalone file; it requires Spring Boot/Spring Context imports. Inside a listener, `event` is passed in by Spring Boot rather than constructed manually.

| API | Data | What to keep in mind |
| --- | --- | --- |
| `getException()` | `Throwable` that caused the failure | May be a wrapper exception; inspect `getCause()` to find near-root causes without discarding wrapper details |
| `getApplicationContext()` | `ConfigurableApplicationContext` or `null` | **Can be null** if failure occurred before context creation; non-null still does not prove beans are usable |
| `getSpringApplication()` | The running `SpringApplication` | Configuration/bootstrap object, not a ready bean container |
| `getArgs()` | Argument array passed to `run(...)` | May contain tokens, passwords, or sensitive values; do not log verbatim |
| `getTimestamp()` | Event timestamp inherited from `ApplicationEvent` | Useful for diagnostics; does not mean a readiness milestone |

### 2.1. Distinguishing "having a context reference" from "a still-valid context"

A `ConfigurableApplicationContext` reference is a **Java object**. It can exist even when:

- It has not been refreshed yet.
- Refresh was aborted mid-way.
- Some singletons were created and then threw an exception.
- Shutdown/cleanup is already underway.
- The context is already closed or never became active.

Therefore:

```java
if (event.getApplicationContext() != null) {
    // NOT enough to guarantee getBean() can be called.
}
```

`context.isActive()` is a context lifecycle signal, yet **it is not a health check for every bean/dependency** and is not sufficient to turn a failure callback into a place for continuing business operations.

### 2.2. ApplicationFailedEvent is not an event for every exception

`ApplicationFailedEvent` concerns **startup failure** during a `SpringApplication.run(...)` call. It does not automatically fire for every scenario:

- An HTTP request after the app is ready returns 500.
- An `@Async` task fails while the app is running normally.
- A message broker temporarily drops connection after startup.
- A `@Scheduled` method throws an exception.
- An intentional shutdown request occurs.
- A business code path returns a validation failure.

Those runtime failures require proper exception handling, task error handlers, logs/metrics, readiness/liveness, or circuit breakers; do not misuse `ApplicationFailedEvent` to monitor every incident across the application's lifetime.

## 3. Startup phases and resource reliability levels

Simplified Spring Boot 3.3 diagram:

```text
main()
  |
SpringApplication.run(args)
  |
  +-- ApplicationStartingEvent
  |      Environment not ready yet
  |
  +-- ApplicationEnvironmentPreparedEvent
  |      Environment ready; ApplicationContext not yet created
  |
  +-- ApplicationContextInitializedEvent
  |      context created/prepared; bean definitions not yet loaded
  |
  +-- ApplicationPreparedEvent
  |      bean definitions loaded; refresh not yet started
  |
  +-- ApplicationContext.refresh()
  |      builds BeanFactory infrastructure, singleton beans
  |      web server/clients/pools may gradually initialize
  |
  +-- ApplicationStartedEvent
  |      refresh complete; runners not yet run
  |
  +-- LivenessState.CORRECT
  |
  +-- ApplicationRunner / CommandLineRunner
  |
  +-- ApplicationReadyEvent
  |
  +-- ReadinessState.ACCEPTING_TRAFFIC
  |
  +-- run() returns context

If an exception occurs during Boot-handled startup phases:
       |
       +--> ApplicationFailedEvent
       +--> error diagnostics + context/resource cleanup (if any)
       +--> run() does not return a healthy context
```

The diagram shows **essential milestones** only and does not guarantee the failure event always fires at the exact same physical moment relative to every custom destroy callback. Regarding usable resources, **the failure phase matters more than the presence of a context variable**.

### 3.1. Failure before context creation

Examples:

- Bootstrap configuration fails before `createApplicationContext()`.
- A critical configuration source cannot be prepared.
- A very early initializer fails.
- The context creation strategy itself throws an exception.

In that case `event.getApplicationContext()` **may be null**. You cannot retrieve `DataSource`, obtain `Environment` through the context, or call `context.getBean(...)`. The listener should rely solely on genuinely available data: the exception, timestamp, non-sensitive app metadata, and a logger or console fallback it owns itself.

### 3.2. Failure during context refresh

Examples: failing to create a bean, missing configuration, invalid dependency cycle, property binding failure, missing JDBC driver, or the embedded web server failing to bind its port.

At this point Boot may hold an `ApplicationContext` reference, yet the context is **not necessarily active/usable**. Some beans were created while others were not; Spring may already be destroying successfully created singletons during cleanup. Do not try "reading a few important beans" from the failure listener to check if they are alive.

### 3.3. Failure in ApplicationRunner/CommandLineRunner

In this phase the context has normally refreshed and may have published `ApplicationStartedEvent` and `LivenessState.CORRECT`. Still, a runner throwing an exception causes startup **to fail** before Boot reaches `ApplicationReadyEvent` and default accepting readiness.

A failure listener can receive a **non-null** context reference. Nevertheless:

- Boot is handling a failed startup and will close the context along the failure path.
- Active resources may already be shutting down.
- Do not start a new job merely because `context.isActive()` returns `true` at one instant.
- Do not treat `LivenessState.CORRECT` having appeared as proof that the application reached ready.

### 3.4. After ready, this is no longer a typical startup failure

If a web service is already up and serving traffic and encounters an error in a request or background task, that error **does not automatically become an ApplicationFailedEvent**. Classify runtime failures separately. For unrecoverable internal failures you can use availability/liveness per Boot's contract; for transient external dependency issues use appropriate retries, readiness, or circuit breakers.

## 4. Why aren't @Component or @EventListener enough to catch very early failures?

A listener defined as a Spring bean:

```java
@Component
public class BeanFailureListener {

    @EventListener
    public void onFailed(ApplicationFailedEvent event) {
        System.err.println(event.getException().getClass().getName());
    }
}
```

This is an **illustrative snippet**; it requires imports for `Component`, `EventListener`, and `ApplicationFailedEvent`.

It only has a chance to run if the listener bean was already instantiated and registered early enough. If the failure occurs **before BeanFactory builds the listener bean**, you **cannot count on** this callback being invoked.

For events that must be captured very early, Spring Boot recommends registering the listener directly with `SpringApplication.addListeners(...)` or `SpringApplicationBuilder.listeners(...)` before `run(...)`, or declaring a listener loaded by Boot via `META-INF/spring.factories`.

### 4.1. A more reliable approach: listeners independent of Spring beans

```java
SpringApplication application = new SpringApplication(MyApp.class);
application.addListeners(new SafeStartupFailureListener());
application.run(args);
```

This snippet lives in `main` and needs appropriate `MyApp` and `SafeStartupFailureListener` classes. The listener is created via a Java constructor **before Boot starts running**, without injecting a `DataSource`, repository, or `ApplicationContext`.

For failure events with a `null` context, this listener can still execute because it does not wait on a Spring bean. The runnable demo in Section 9 uses this exact strategy.

### 4.2. Registration via META-INF/spring.factories

A library wanting its listener auto-loaded for corresponding startups can declare:

```properties
org.springframework.context.ApplicationListener=\
com.example.failure.SafeStartupFailureListener
```

This is a snippet for `src/main/resources/META-INF/spring.factories`. When using this mechanism, the listener class must have a suitable constructor so Spring Boot/`SpringFactoriesLoader` can instantiate it without relying on an already initialized bean context. The class name and package must match the actual class.

In Section 9's demo, we use **`application.addListeners(...)`**, with **no** need for the `spring.factories` entry above. Registering both ways for the same purpose can cause duplicate handling; check registration rather than blaming event propagation.

### 4.3. When can a bean listener be used?

An `@EventListener` on a bean is completely useful for events **after the context has refreshed sufficiently**, but it is **not the sole or reliable mechanism for very early startup failures**.

When listening to events for early telemetry, design it with **minimal** dependencies; avoid autowiring complex services just to record an exception when those very services might be why context creation failed.

## 5. How to design a safe failure listener

A good failure listener should only do things **that do not depend on resources that may already be broken**:

1. Extract the `Throwable` from the event.
2. Record the **error type**, curated metadata, and timestamp.
3. Distinguish `null` vs non-null context if needed.
4. Optionally walk to the root cause without dropping the original stack trace.
5. Use a logger or an active output channel that requires no `BeanFactory`.
6. Finish quickly without blocking startup failure handling.
7. Avoid throwing new exceptions from the listener itself.
8. Let Spring Boot execute its standard cleanup and reporting path.

Conversely, avoid:

- `context.getBean(OrderService.class).sendAlert()`.
- Opening a fresh `DataSource` to probe the DB while the DB is failing.
- Sending HTTP reports through a singleton client that may already be closed.
- Submitting tasks to a `ThreadPoolTaskExecutor` that Boot is destroying.
- Calling `context.refresh()` to "rescue" a failed context.
- Calling `System.exit` inside the listener, cutting off cleanup.
- Logging all of `event.getArgs()` when it might contain secrets.
- Running infinite retry loops or untimed network calls.
- Masking the real exception with a secondary exception thrown by the listener.

### 5.1. Why avoid getBean even when a context exists?

When startup fails, the container can be in one of several states:

```text
Context not created    -> no getBean
Context not refreshed  -> BeanFactory not ready
Context refresh failed -> part of bean graph invalid
Context closing        -> singletons may be destroyed
Context closed         -> using beans is outside lifecycle
```

`context.isActive()` does not make beans safe either: state can change immediately after the check (**time-of-check/time-of-use race**). And even while active, a specific bean may not have been created yet or may be the exact component that threw the exception.

### 5.2. Logging must tolerate "logging system not fully initialized"

In very early failures, complex logging configuration may not be ready yet. A minimal listener can use `System.err.println(...)` as a **fallback** if aligned with operational needs. In production, use early-initialized logging infrastructure **that needs no context**, configured to be non-blocking and independent of failing backends.

Never guarantee stdout/stderr always reaches disk: containers or log collectors can fail or get hard-killed. Important failure recording requires external monitoring and cause analysis through logs, stack traces, and failure analyzers.

## 6. Exceptions and root cause: extracting information safely

A bean error may be wrapped across multiple layers:

```text
IllegalStateException: Failed to execute ApplicationRunner
    |
    +-- IllegalStateException: BUSINESS_STARTUP_PRECHECK_FAILED

BeanCreationException: Error creating bean
    |
    +-- BeanInstantiationException
             |
             +-- IllegalArgumentException: invalid required setting
```

`event.getException()` gives you the exception reported by Spring Boot. You can walk `getCause()` to find the near-root error:

```java
static Throwable rootCause(Throwable throwable) {
    Throwable current = throwable;
    int hops = 0;
    while (current.getCause() != null
            && current.getCause() != current
            && hops++ < 20) {
        current = current.getCause();
    }
    return current;
}
```

This is a standalone Java method you can place inside the listener class. Bounding the hop count guards against buggy code or unusual cause chains. **Do not replace the entire exception with the root cause** during analysis; wrappers carry valuable bean names, initialization phases, and stack traces.

In production, avoid printing raw exception messages if they can contain property values, JDBC URLs with credentials, sensitive file paths, or user-supplied arguments. The demo prints only fixed messages authored by the sample code itself.

## 7. Let Spring Boot report startup failures via standard mechanisms

Spring Boot provides `FailureAnalyzer` and `FailureAnalysisReporter` to give readable messages for common startup failures, such as a port already in use or configuration errors. When you need to understand why a bean was not created, enable `--debug` or logging for `ConditionEvaluationReportLoggingListener` to inspect auto-configuration conditions.

**FailureAnalyzer** and **ApplicationFailedEvent listeners** serve different purposes:

| Mechanism | Primary purpose | Should business beans be called here? |
| --- | --- | --- |
| `ApplicationFailedEvent` | Signals an error during `SpringApplication` startup | Not by default, especially when context is null/unrefreshed |
| `FailureAnalyzer` | Turns a known failure into a clear description/action | Analyze the exception; do not restart business logic |
| `ConditionEvaluationReport` | Explains auto-configuration conditions | For diagnosis, not mutating beans in place |
| `ApplicationRunner` | Runs mandatory steps after refresh, before ready | Can use beans during normal startup, but enters failure path if it throws |
| `@PreDestroy`/`DisposableBean` | Cleans up created resources per lifecycle | Only within the owner/callback actually invoked |
| `SmartLifecycle.stop(...)` | Coordinates stopping active components | Design timeouts/cancellation and callbacks per contract |

A failure listener **should not compete** with Boot to manually close the same resources or throw secondary errors that obscure the root cause.

### 7.1. Do not turn a listener into a "repair" mechanism

If a property is missing, fix the configuration and restart via deployment/CI. If the DB is unreachable, handle it via external dependency and startup policies. If `BeanFactory` already failed refresh, calling `refresh()` again on the same object from a failure listener is a dangerous intervention with no guarantee of working.

Better: log the cause, let Boot roll back/close, and let the orchestrator decide retries/restarts per policy.

## 8. Which resources remain usable when ApplicationFailedEvent fires?

The answer always **depends on the failure phase and ownership**; never claim "everything is dead" or "because context exists, everything is alive".

| Resource | Very early failure | Failure during refresh | Runner failure after refresh | Safe handling |
| --- | --- | --- | --- | --- |
| `ApplicationContext` | May be `null` | May be non-null yet not active | Usually has context; preparing to close | Null-check; avoid `getBean` in failure callback |
| `Environment` | May not be fully prepared | May exist | Usually exists | Do not assume every property resolved; do not log secrets |
| Standard JDK/console logger | Usually safe to try | Safe to try | Safe to try | Log minimally, without `BeanFactory` |
| Spring-managed `DataSource` | May not exist | May be partially created/destroying | May exist but about to destroy | Do not keep querying in listener |
| HTTP client Spring bean | May not exist | May be uncreated or destroyed | May still hold sockets yet about to close | Do not send reports with this client in listener |
| `TaskExecutor` executor | May not exist | May be uninitialized | May be rejecting new tasks | Do not submit new work |
| Embedded web server | Not created | May be partially initialized | May already be started | Do not rely on HTTP endpoints to report startup failure |
| ApplicationRunner/CommandLineRunner | Not run | Not run | May be throwing | Do not invoke runner a second time in listener |
| Resource opened outside BeanFactory | May exist | May exist | May exist | Creating code must ensure exception-safe cleanup |

**Principle:** if a resource is not inside the Spring context or has not been handed over to the container, **Spring cannot promise to clean it up** when context startup fails.

## 9. Runnable Java 17+ example: fail before context and fail in ApplicationRunner

This example uses **Spring Boot 3.3.x + Java 17+**, non-web, needing no database, broker, or HTTP server. It demonstrates three paths:

1. Normal run: runner completes, context closes intentionally.
2. Runner throws after context refresh: `ApplicationFailedEvent` fires, context may be non-null, and Boot enters failure cleanup.
3. `createApplicationContext()` throws before a context exists: event receives a `null` context.

The listener is constructed via a Java constructor before `run`, **without `@Component`**. It only uses the exception and a boolean null-check, never calling `getBean`.

### 9.1. Directory structure

```text
failure-event-lesson/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/com/example/failure/
    FailureEventLessonApplication.java
```

### 9.2. settings.gradle

```groovy
rootProject.name = 'failure-event-lesson'
```

### 9.3. build.gradle (Groovy DSL)

```groovy
plugins {
    id 'java'
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

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

The `./gradlew` commands below assume the project has a Gradle Wrapper; generate the project with Spring Initializr or use a compatible Gradle installation to create the Wrapper if absent.

### 9.4. application.properties

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off

# Default mode: startup succeeds.
demo.fail-runner=false
```

There is no need to put `demo.fail-before-context` in this file because the sample reads that mode in `main` from command-line arguments before Spring creates the context.

### 9.5. FailureEventLessonApplication.java — complete file

```java
package com.example.failure;

import java.util.Arrays;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class FailureEventLessonApplication {

    public static void main(String[] args) {
        boolean failBeforeContext = Arrays.asList(args)
                .contains("--demo.fail-before-context=true");

        SpringApplication application;

        if (failBeforeContext) {
            // Demo: intentionally fail before context is created.
            application = new SpringApplication(
                    FailureEventLessonApplication.class) {
                @Override
                protected ConfigurableApplicationContext
                        createApplicationContext() {
                    throw new IllegalStateException(
                            "SIMULATED_BEFORE_CONTEXT");
                }
            };
        } else {
            application = new SpringApplication(
                    FailureEventLessonApplication.class);
        }

        application.setWebApplicationType(WebApplicationType.NONE);

        // Register before run; does not depend on BeanFactory.
        application.addListeners(new SafeFailureListener());

        ConfigurableApplicationContext context = application.run(args);
        System.out.println("STARTUP_SUCCESS");

        // Runs only along the successful startup path.
        context.close();
    }

    @Bean(destroyMethod = "close")
    CloseMarker closeMarker() {
        return new CloseMarker();
    }

    @Bean
    ApplicationRunner demoRunner(CloseMarker marker,
                                 Environment environment) {
        return args -> {
            if (environment.getProperty(
                    "demo.fail-runner", Boolean.class, false)) {
                throw new IllegalStateException(
                        "SIMULATED_RUNNER_FAILURE");
            }

            System.out.println("RUNNER_OK");
        };
    }

    static final class CloseMarker implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("RESOURCE_CLOSED");
        }
    }

    static final class SafeFailureListener
            implements ApplicationListener<ApplicationFailedEvent> {

        @Override
        public void onApplicationEvent(ApplicationFailedEvent event) {
            Throwable root = rootCause(event.getException());

            System.out.println("FAILED_EVENT_RECEIVED");
            System.out.println("CONTEXT_PRESENT="
                    + (event.getApplicationContext() != null));
            System.out.println("ROOT_TYPE="
                    + root.getClass().getSimpleName());
            System.out.println("ROOT_MESSAGE=" + root.getMessage());

            // Do not call context.getBean(), do not send HTTP,
            // do not use DataSource, and do not call System.exit().
        }

        private static Throwable rootCause(Throwable error) {
            Throwable current = error;
            int hops = 0;

            while (current.getCause() != null
                    && current.getCause() != current
                    && hops++ < 20) {
                current = current.getCause();
            }

            return current;
        }
    }
}
```

This is a **standalone Java file in a Spring Boot 3.3 project**. The public class name matches the filename, and all inner classes live in the same file. There are no placeholder classes or undefined helpers.

**Why the code makes sense:**

- `SafeFailureListener` is a Java object registered early; it injects no Spring beans.
- `event.getApplicationContext() != null` is only logged, never used as permission to call `getBean`.
- `rootCause(...)` caps traversal depth and prints only **fixed messages set by the demo**. In production, redact messages from real failures.
- `CloseMarker` is a bean with a destroy callback; once the context actually created the bean, closing the context invokes `close()` per lifecycle.
- `demoRunner(...)` takes `CloseMarker` as a dependency, so the resource is created along the normal/runner initialization path.
- Both simulated failures happen in **different phases**, proving failure events do not always have the same level of resource availability.
- `SpringApplication.run(args)` throws an exception in failure modes; `STARTUP_SUCCESS` and `context.close()` in `main` **do not run** when `run` fails to return.

### 9.6. Running the success case

```bash
./gradlew bootRun
```

Windows CMD: `gradlew.bat bootRun`. PowerShell: `.\gradlew.bat bootRun`.

On the successful run, the lines **explicitly printed by the demo code**, ignoring framework/Gradle logs, are:

```text
RUNNER_OK
STARTUP_SUCCESS
RESOURCE_CLOSED
```

There is no `FAILED_EVENT_RECEIVED` because no startup failure occurred.

### 9.7. Failure from ApplicationRunner

Run:

```bash
./gradlew bootRun --args="--demo.fail-runner=true"
```

Additional Spring Boot/Gradle logging can be verbose. Markers explicitly printed by the demo on the normal failure path include:

```text
FAILED_EVENT_RECEIVED
CONTEXT_PRESENT=true
ROOT_TYPE=IllegalStateException
ROOT_MESSAGE=SIMULATED_RUNNER_FAILURE
RESOURCE_CLOSED
```

**Explanation:** Runners execute after refresh, so Boot already had a context when the runner failed. The failure listener receives the error info, and Spring Boot cleans up created context/beans. The `RESOURCE_CLOSED` line reflects the bean's destroy callback. Do not claim all resources are usable solely from `CONTEXT_PRESENT=true`.

In real tooling, startup failure logs and Gradle logs can interleave with markers, and shutdown behavior depends on additional code. When running in an IDE or test, assert only the **relevant markers and contracts**, rather than requiring exact ordering of every framework log line.

### 9.8. Failure before ApplicationContext is created

Run:

```bash
./gradlew bootRun --args="--demo.fail-before-context=true"
```

Because `SpringApplication.createApplicationContext()` is overridden to throw **before creating the context**, a listener registered before `run` still records:

```text
FAILED_EVENT_RECEIVED
CONTEXT_PRESENT=false
ROOT_TYPE=IllegalStateException
ROOT_MESSAGE=SIMULATED_BEFORE_CONTEXT
```

There is no `RESOURCE_CLOSED` for `CloseMarker` because the bean was never created. Nor is there `STARTUP_SUCCESS`.

**Key takeaway:** code like `event.getApplicationContext().getBean(...)` would immediately throw `NullPointerException` in this mode, potentially hiding the original root cause of startup failure.

### 9.9. Gradle's exit code is not the business exit code

When `bootRun` launches the child application and the app fails, Gradle normally marks the task as failed. The process exit code of `gradlew` does not necessarily match a custom exit code you designed in your app. Do not assign business meaning to an arbitrary exit code observed while studying events. If a batch job needs an explicit exit-status contract, design `ExitCodeGenerator`/exception mapping and test `java -jar` directly.

## 10. Writing listeners that use only reliable data at failure time

A minimal production implementation usually only needs:

```java
public final class StartupFailureAudit
        implements ApplicationListener<ApplicationFailedEvent> {

    @Override
    public void onApplicationEvent(ApplicationFailedEvent event) {
        Throwable failure = event.getException();

        String type = failure.getClass().getName();
        boolean contextExists =
                event.getApplicationContext() != null;

        System.err.println("Startup failed: " + type
                + ", contextExists=" + contextExists);
    }
}
```

This is a **class snippet** requiring `ApplicationListener` and `ApplicationFailedEvent` imports. To use it as a pre-run listener, register it via `SpringApplication.addListeners(new StartupFailureAudit())` or another appropriate early registration mechanism.

Do not do:

```java
@Component
class WrongAudit {

    @Autowired
    DataSource dataSource;

    @EventListener
    void failed(ApplicationFailedEvent event) {
        // Do not require the DB in a startup failure callback.
        try (Connection c = dataSource.getConnection()) {
            // ...
        }
    }
}
```

This is an **illustrative anti-pattern** with incomplete imports/methods. It both depends on a bean that may not exist yet and attempts to access a DB that might itself be the cause of startup failure. Even if the resource happened to exist in one particular run, that is not a contract you can rely on across all failure paths.

### 10.1. Metadata safe to log

You can log in a controlled manner:

- Exception class name.
- Abbreviated cause chain.
- Application name/version from constants or non-sensitive system properties.
- Launcher-generated startup attempt/correlation ID.
- Whether a context reference is present.
- Event timestamp.
- A normalized stage/cause category.

Avoid logging the raw `event.getArgs()` array since it may contain `--password=...`, API keys, or secret URIs. Never call `Environment.toString()` to dump all property sources.

## 11. How do FailureAnalyzer and ConditionEvaluationReport differ from listeners?

Spring Boot includes many `FailureAnalyzer`s for common errors. For instance, when a port is occupied, Boot may print:

```text
APPLICATION FAILED TO START

Description:
Web server could not start because the configured port was in use.

Action:
Choose another port or stop the conflicting process.
```

This is an **illustrative content sample**, not mandatory verbatim output for every Boot 3.3 app. Wording varies by failure analyzer and version.

`FailureAnalyzer` is responsible for producing an **actionable error report**, whereas `ApplicationFailedEvent` is a **lifecycle signal** carrying the exception. They do not compete and are not a reason to open new resources.

For auto-configuration issues, enable:

```bash
java -jar build/libs/failure-event-lesson-0.0.1-SNAPSHOT.jar --debug
```

This command assumes the JAR is already built. In real failures, `--debug` adds auto-configuration condition details to logs; it does **not** turn a broken `BeanFactory` into a recoverable context.

## 12. Cleanup if resources were not yet handed over to Spring

An easily overlooked bug lives inside factory methods:

```java
@Bean
CloseableClient partnerClient() {
    CloseableClient client = openClient();
    validateFurtherConfiguration(); // May throw.
    return client;
}
```

This snippet illustrates the problem; `CloseableClient`, `openClient`, and `validateFurtherConfiguration` are application-defined types/helpers. If an exception is thrown **after `openClient()` returns a resource but before the `@Bean` method returns**, Spring has no handed-over bean instance on which to invoke `destroy()`. An `ApplicationFailedEvent` listener should not try to track down this local resource to close it either.

**Exception-safe approach:** validate before opening resources; if multiple steps must happen after opening, keep local ownership in `try/catch`:

```java
@Bean(destroyMethod = "close")
CloseableClient partnerClient() {
    validateSettings();

    CloseableClient client = openClient();
    try {
        configureClient(client);
        return client; // Hand over ownership to container.
    } catch (RuntimeException ex) {
        try {
            client.close();
        } catch (Exception cleanupError) {
            ex.addSuppressed(cleanupError);
        }
        throw ex;
    }
}
```

This is a **snippet** with project-defined helpers `validateSettings`, `openClient`, `configureClient` and type `CloseableClient`; handle checked exceptions per your actual APIs. Meaning: before the bean is returned to Spring, **the factory owns the resource** and must clean up on failure. Once the factory returns cleanly, the container manages the lifecycle via destroy callbacks.

### 12.1. Do not "fix" startup failures by closing resources inside event listeners

When context refresh fails, Spring has mechanisms to destroy singletons that were already created. Calling `context.getBeansOfType(DataSource.class)` inside `ApplicationFailedEvent` to manually close every `DataSource` is both error-prone and liable to double-close resources or trigger unintended side effects.

For resources outside the container, their own owner must clean up; for Spring-managed resources, respect their lifecycle. A listener should at most report missing cleanup when reliable evidence exists, never act as a second owner.

## 13. Common resource types and risks during failure handling

### 13.1. DataSource/HikariCP

HikariCP may be:

- Not yet initialized if startup failed early.
- Opening its initial connections when `BeanFactory` failed.
- Pool created, while Boot is closing the context.
- Already destroyed during refresh failure cleanup.

Even when `event.getApplicationContext() != null`, do not call `context.getBean(DataSource.class).getConnection()` as a "startup failure audit". If the root cause is an unreachable DB, that call triggers extra connection attempts/timeouts and obscures the original stack trace.

### 13.2. HTTP clients, Redis, Kafka

Network-dependent clients may have created threads/sockets or not been created at all. Sending an error webhook via an HTTP client bean that is itself broken can fail. If you must send incident telemetry on startup failure, use a mechanism **outside the Spring context** or an external supervisor/log collector with tight timeouts; never force a failure listener to make long synchronous network calls.

### 13.3. ThreadPoolTaskExecutor and schedulers

Executors/schedulers own worker threads, queues, and shutdown lifecycles. When startup fails, they may not be initialized yet or may be shutting down. Do not submit "send failure email" tasks to a pool that may no longer accept tasks.

If code manually creates `Executors.newFixedThreadPool(...)` outside the container without shutting it down, the JVM can stay alive after failure. That is an ownership bug in the pool-creating code, not a shortcoming of `ApplicationFailedEvent`.

### 13.4. Logging/metrics/tracing

Some logging and observation systems initialize very early, yet exporters/appenders can depend on configuration or I/O. Use them best-effort; avoid making telemetry delivery a blocking prerequisite before the process is allowed to exit. For reliable auditing across crashes and hard kills, rely on a supervisor/container runtime and independent monitoring infrastructure.

## 14. Web applications: a context may exist even when the web server is unusable

An application can fail when:

- Binding a port because the address is already in use.
- Creating the Servlet web server while another bean init fails.
- Initializing the security filter chain fails.
- Context refresh aborts mid-way.
- A runner throws an exception after the web server already opened.

Thus, a context object existing **does not mean HTTP endpoints work**. A failure listener **must not** call `http://localhost:8080/health`, especially when the web server may never have opened or is already shutting down.

### 14.1. Liveness/readiness on startup failure

In Spring Boot 3.3, liveness is published as `CORRECT` after `ApplicationStartedEvent`, and readiness as `ACCEPTING_TRAFFIC` after `ApplicationReadyEvent` and runners.

If a runner fails:

```text
ApplicationStartedEvent
LivenessState.CORRECT
ApplicationRunner throws
ApplicationFailedEvent
ApplicationReadyEvent: not reached along success path
ReadinessState.ACCEPTING_TRAFFIC: not published along success path
```

There is no contradiction here. Liveness became `CORRECT` because the context refreshed, yet **the overall startup still failed** before ready. Infrastructure monitoring process/container health can restart per policy. Do not try to force readiness false inside a failure listener using an `ApplicationAvailability` bean that may no longer be usable.

### 14.2. What if a failure happens after ready?

An exception in an HTTP controller after ready does not automatically generate `ApplicationFailedEvent`. For unrecoverable runtime failures, Boot provides `AvailabilityChangeEvent<LivenessState>`/health probes; for recoverable failures, use error handling, retries, circuit breakers, and readiness as appropriate.

**Do not pick a mechanism just because its name contains "Failed".** The right event must match the **lifecycle phase**.

## 15. Listener limitations with multiple ApplicationContexts

Spring Framework supports parent/child context hierarchies. An event published in a child context can propagate up to ancestor listeners. When multiple `SpringApplication` instances form a hierarchy, a listener on the parent can see multiple events of the same type.

With `ApplicationFailedEvent`, inspect:

- `event.getSpringApplication()` to distinguish which run emitted it.
- `event.getApplicationContext()` can be null, so do not rely on context identity comparison when the event has no context.
- If one failure listener is registered across multiple `SpringApplication` instances, avoid duplicate reports caused by registration/topology.
- Do not let a parent listener close parent resources just because a child startup failed.

When you need a single report across multiple startup attempts, attach a **correlation/attempt ID** from the launcher or use metrics with deduplication policies; never infer that every event with the same name came from the same failure.

## 16. Do not "hide" runner exceptions to avoid ApplicationFailedEvent

An anti-pattern:

```java
@Bean
ApplicationRunner initializeEverything() {
    return args -> {
        try {
            loadMandatoryData();
        } catch (Exception ex) {
            System.err.println("Ignored");
        }
    };
}
```

This snippet intentionally omits `loadMandatoryData` to illustrate the concept. If that data is **mandatory** for safe operation, swallowing the exception lets Boot proceed to ready even though the app is unready.

The right choice depends on the nature of the data:

- **Mandatory:** let the runner fail fast or throw a descriptive exception, driving startup into the failure path.
- **Optional/recoverable:** fall back, record metrics, and continue in a bounded degraded functional state per policy.
- **Long yet mandatory:** synchronous runner with an appropriate timeout or properly coordinated readiness gating.
- **Needs retries across process restarts:** store state in a job store/durable queue, rather than an endless background loop in an unready context.

`ApplicationFailedEvent` records the **outcome of the failure path**; it does not replace business code deciding whether an error is a startup failure or runtime failure.

## 17. Testing failure listeners without breaking the test suite

### 17.1. Unit tests passing only the event

A unit test can construct an `ApplicationFailedEvent` using its constructor taking `SpringApplication`, arguments, a possibly-null context, and a sample `Throwable`, then invoke the listener. Test that:

- No `NullPointerException` occurs when context is null.
- The exception is identified accurately.
- The listener does not call `getBean` or network APIs.
- No secrets from args are printed.
- A failure in formatting/logging does not mask the original exception.

For production code, separate error data normalization from log output for easier testing.

### 17.2. Integration testing pre-context failure

Use the `createApplicationContext()` exception simulation from Section 9. Verify the listener was **registered before `run`** and prints `CONTEXT_PRESENT=false`, while destroy callbacks for beans in the uncreated context do not execute.

A `@SpringBootTest` with a shared `TestContext` cache is unsuitable for arbitrarily corrupting a shared context. Create an isolated `SpringApplication` or launch a **subprocess** so failures do not pollute other tests.

### 17.3. Integration testing runner failure

Run the program with `--demo.fail-runner=true` in a child process and verify:

- `ApplicationFailedEvent` fires.
- A context reference may exist.
- The root cause reflects the runner error.
- `STARTUP_SUCCESS` is absent.
- Created beans are cleaned up per lifecycle.
- No unmanaged non-daemon threads or connection pools created by the app remain alive.

Note: if you use `@SpringBootTest` with context caching, calling `SpringApplication.exit` intentionally on a cached context can break subsequent tests. Use a dedicated context or process.

### 17.4. Process-level tests

Use `ProcessBuilder`/shell to run `java -jar` and check the actual exit status, logs, and deadline. For failure paths without a custom `ExitCodeGenerator`, do not hardcode one exact exit number across every JVM/launcher; it will normally be non-zero, while the final code depends on the failure path and environment.

If a test uses `Process.waitFor()`, set a timeout and kill the child process if stuck. A manually created executor that was never shut down can keep the child JVM alive even after Boot cleans up the context.

## 18. Common mistakes and fixes

| Mistake/misconception | Consequence | Fix |
| --- | --- | --- |
| Always calling `event.getApplicationContext().getBean(...)` | NPE before context or invalid `BeanFactory` | Null-check; do not rely on beans inside failure handlers |
| Context non-null => all beans safe | May actually be unrefreshed or destroying | Use only event metadata and an independent logger |
| Defining failure listener solely with `@Component` | Misses errors before the bean is created | `SpringApplication.addListeners` or `spring.factories` |
| Listener injects `DataSource` to send audit | DB/pool itself may be why startup failed | Use logs/fallback outside the container |
| Calling remote webhook synchronously in failure event | Stalls startup failure handling, secondary errors | Use timeouts and out-of-process monitoring |
| Listener calls `System.exit` | Aborts cleanup/diagnostics | Let the entrypoint/Boot failure path decide exit |
| Relying on `isActive()` to keep running business logic | Races and context no longer guaranteed healthy | Do not start new work on a failed context |
| Logging raw `getArgs()` | Leaks secrets/tokens/passwords | Redact and log only essential metadata |
| Failure event = every runtime exception | Misses request and background failures | Use proper runtime error handling |
| Context failed yet trying `refresh()` again | Unclear state, repeated side effects | Fix cause and start a fresh instance |
| `@Bean` factory opens client then throws | Resource never handed over to Spring to destroy | Validate first, catch/finally close |
| Closing every bean inside failed listener | Double-close or `BeanFactory` errors | Let lifecycle owners handle cleanup |
| Runner catches/ignores mandatory error | App may report ready when unsafe | Fail fast on critical errors |
| Treating liveness CORRECT as ready | Runners can fail after context refresh | Distinguish Liveness from Readiness |
| Startup failure before logging init has no telemetry | Lost incident logs | Stderr fallback, supervisor, external log collector |
| Listener creates `ExecutorService` to report error | Thread leak after app already failed | Minimal synchronous write or external monitor |
| Test kills JVM with `System.exit` | Terminates entire test suite | Spawn an isolated subprocess |
| Using Spring `ApplicationFailedEvent` as health probe | Event fires only on startup failure | Liveness/readiness and health indicators |
| Child failure triggers parent cleanup | Confuses ownership/context | Filter source; let parent owner keep its resources |
| Assuming `@PreDestroy` always runs | SIGKILL/crash/timeout cannot guarantee it | Checkpointing, idempotency, shutdown infrastructure |
| Reading only root exception, dropping wrappers | Loses bean name and failure phase | Keep full cause chain in safe error diagnostics |

## 19. Safe listener and cleanup design checklist

1. Recognize that failure events apply only to **startup**.
2. Register listeners early enough if capturing pre-context failures.
3. Avoid listener dependencies on Spring beans the container might fail to build.
4. Handle `event.getApplicationContext() == null`.
5. Remember a non-null context still does not guarantee `BeanFactory`/beans are usable.
6. Extract `event.getException()`, keeping both wrappers and root cause for diagnosis.
7. Never print secrets, raw args, or the full Environment.
8. Avoid network/database/broker calls inside failure listeners.
9. Never call `System.exit` or `SpringApplication.exit` from a failure listener.
10. Keep handlers fast, bounded, and low-side-effect.
11. Let Boot's `FailureAnalyzer` print standard failure reports.
12. Resources opened before a `@Bean` returns must be cleaned up by the factory if it throws.
13. Spring-managed resources require destroy callbacks aligned with ownership.
14. For producers/executors, design stop/await/cancel and deadlines.
15. Where rollback is incomplete due to SIGKILL, ensure idempotency/checkpointing.
16. Separate Environment, context creation, refresh, and runner failures.
17. Do not equate Liveness `CORRECT` with Readiness `ACCEPTING_TRAFFIC`.
18. Never swallow critical runner exceptions just to make startup succeed.
19. Test early failures and runner failures in isolated processes/contexts.
20. Test that the listener does not NPE when context is null.
21. Verify bean cleanup for resources that were actually created.
22. Never use cached test contexts to simulate destructive failures.
23. Monitor threads/pools after failure; avoid unmanaged executors.
24. Document clearly who owns operational alerts and instance restarts.

## 20. Self-check questions

**1. Is ApplicationFailedEvent published when an HTTP request returns 500 after startup?**

Not by default. It reports `SpringApplication` failures during startup, not a global event for every runtime exception.

**2. Is getApplicationContext() always non-null?**

No. If startup fails before the context is created, it can be `null`.

**3. Does a non-null context allow calling getBean(DataSource.class) to log an error?**

No. The context may be unrefreshed, failed during refresh, closing, or the resource itself may be the cause of failure.

**4. Is an @EventListener in a @Component guaranteed to receive errors when Environment loading fails?**

No. The bean may not exist yet. Register the listener with `SpringApplication.addListeners` before `run` if early handling is needed.

**5. When ApplicationRunner throws an exception, could the context already have refreshed?**

Yes. Runners execute after refresh but before ready; Boot may already have published liveness `CORRECT`, yet startup still fails.

**6. Should you restart a broken bean by calling context.refresh inside a listener?**

No. Recovery from a failed context startup is not guaranteed; fix the cause and restart cleanly via the owner.

**7. Can @PreDestroy clean up resources on every failure path?**

No. If the bean was never created or the resource was never handed over to the container, there is no instance for the callback. `SIGKILL` cannot guarantee callbacks either.

**8. What does FailureAnalyzer do?**

Generates description/action for startup failures to aid diagnosis; it does not replace resource owners or service restarts.

**9. If a factory method creates an HTTP client and throws before returning, will Spring close the client automatically?**

Do not expect it. The bean instance was not handed over to the container; factory code must clean up opened resources.

**10. Why not send a webhook using a Spring-managed HTTP client inside a listener?**

The client may not exist, be unhealthy, be closing, or depend on the failing service itself. Listeners should minimize side effects.

**11. If you want to measure the real exit code of a startup failure, how should you test it?**

Run the app as a **child process** and inspect exit status/logs in the actual launcher, without calling `System.exit` from the test JVM.

**12. If startup succeeds and a @Scheduled job fails 10 minutes later, does ApplicationFailedEvent fire?**

Not under the startup contract. Use task error handling, metrics/tracing, and severity-appropriate availability handling.

## 21. Summary

```text
SpringApplication.run(...)
        |
        +-- Fail before create context
        |       |
        |       +--> ApplicationFailedEvent
        |       +--> getApplicationContext() == null
        |       +--> No Spring beans available to use
        |
        +-- Fail during context.refresh()
        |       |
        |       +--> ApplicationFailedEvent
        |       +--> context may exist, unstable
        |       +--> container-managed resources cleaned up
        |
        +-- Fail in ApplicationRunner
                |
                +--> Context may have refreshed
                +--> ApplicationFailedEvent
                +--> Successful readiness not reached
                +--> Boot handles cleanup/failure reporting

Safe listener:
  Receives exception + curated metadata
  DO NOT call getBean / query DB / submit tasks
  DO NOT open extra resources or hijack shutdown
```

**Most important rule:** `ApplicationFailedEvent` indicates **startup failed**, while how usable Spring resources remain depends on **the failure phase** and **ownership/lifecycle**. When the event fires, prefer recording the failure with a listener registered early enough and independent of `BeanFactory`. Avoid trying to recover or reuse a failed `ApplicationContext`. Let Spring Boot and resource owners handle cleanup, and let infrastructure restart the application according to policy.

## Official documentation

- [Spring Boot 3.3 — SpringApplication: Application Events and Listeners](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — SpringApplication: Startup Failure and FailureAnalyzer](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — ApplicationFailedEvent API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationFailedEvent.html)
- [Spring Boot 3.3 — SpringApplicationRunListener.failed API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplicationRunListener.html)
- [Spring Boot 3.3 — SpringApplication.createApplicationContext API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Boot 3.3 — ApplicationAvailability lifecycle](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Framework 6.1 — Bean creation, destruction and lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework 6.1 — ApplicationContext events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
