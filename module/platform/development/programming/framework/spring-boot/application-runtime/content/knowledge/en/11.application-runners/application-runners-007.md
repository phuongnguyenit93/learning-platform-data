# Behavior When a Runner Throws an Exception in Spring Boot

## 1. The Question: Does One Failing Runner Fail the Entire Startup?

**Yes.** In Spring Boot 3.3.x's default startup flow, if an `ApplicationRunner` or `CommandLineRunner` **throws an exception out of its `run(...)` method**, Spring Boot treats it as an **application startup failure**, not an ordinary request failure. `SpringApplication.run(...)` does not finish normally: Boot enters the startup failure-handling branch, publishes `ApplicationFailedEvent` when possible, closes the created context, and propagates the exception to the caller. Subsequent runners in the execution order are not invoked.

This behavior is intentional. Runners are commonly used for work that must finish before Boot declares the application ready to serve: checking mandatory configuration, verifying reference data, or completing a critical business initialization step. If that step fails, marking the application "ready" is dangerous.

Even so, **not every error inside a runner has to kill the application**. If that preparation step is optional, has a safe fallback, and operational state remains valid, code can catch the error, record it, and return normally. This must be an **explicit design decision**, not a way of hiding exceptions so logs look clean.

This lesson applies to **Spring Boot 3.3.x / Spring Framework 6.1.x / Java 17+**; on other versions, verify the corresponding APIs and lifecycle order.

## 2. What Is a Runner and At Which Milestone Does It Execute?

Spring Boot supports two interfaces:

```java
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}

public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
```

These are simplified signatures for explanation; there is no need to recreate these two interfaces. They already belong to `org.springframework.boot`, and `ApplicationArguments` is the API for reading parsed command-line options.

- `ApplicationRunner` receives `ApplicationArguments`, convenient when you need `getOptionNames()`, `getOptionValues(...)`, or non-option arguments.
- `CommandLineRunner` receives a `String... args` array corresponding to the raw arguments passed from `main`.
- Both are **Spring beans** collected by `SpringApplication` after `ApplicationContext` has refreshed.
- Spring sorts runners via Spring's ordering mechanism, such as `@Order` or `Ordered`. **There is no fixed rule that every `ApplicationRunner` must run before every `CommandLineRunner`**.
- Each runner's `run` invocation in the default chain is **synchronous**. A call that has not returned or has thrown an exception directly affects the startup flow.

Normal lifecycle diagram:

```text
SpringApplication.run(args)
    |
    +--> Prepare Environment / ApplicationContext
    +--> Load bean definitions and refresh context
    +--> (embedded web server may already have bound its port)
    +--> log "Started ..." if startup logging is enabled
    +--> ApplicationStartedEvent
    +--> AvailabilityChangeEvent(LivenessState.CORRECT)
    |
    +--> runner #1 (by order)
    +--> runner #2
    +--> runner #3
    |
    +--> ApplicationReadyEvent
    +--> AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
    +--> SpringApplication.run(...) return
```

Key distinction: **`ApplicationStartedEvent` is published before runners, whereas `ApplicationReadyEvent` is published after all runners complete normally**. Similarly, **liveness** state differs from **readiness** state. An instance can be alive yet not eligible to receive traffic.

## 3. Handling Flow When a Runner Throws an Exception

Suppose there are three runners ordered `@Order(10)`, `@Order(20)`, and `@Order(30)`. The middle runner throws an exception:

```text
SpringApplication.run(...)
  |
  +--> Context refreshed                     [succeeded]
  +--> ApplicationStartedEvent               [published]
  +--> LivenessState.CORRECT                 [announced]
  |
  +--> Runner A, order=10
  |      completes                           [executed]
  |
  +--> Runner B, order=20
  |      throw IllegalStateException         [failed]
  |            |
  |            +--> stop calling subsequent runners
  |            +--> handleRunFailure branch
  |                   +--> process error details / appropriate exit code
  |                   +--> ApplicationFailedEvent
  |                   +--> close created context, if possible
  |                   +--> exception escapes to caller of run(...)
  |
  +--X Runner C, order=30                    [not called]
  +--X ApplicationReadyEvent                 [not published on success path]
  +--X ReadinessState.ACCEPTING_TRAFFIC      [not announced on ready path]
  +--X run(...) normal return                [does not happen]
```

This is Boot 3.3.x's **standard startup failure** sequence; event publication and cleanup depend on context state, error type, and runtime capability. `ApplicationFailedEvent` does not guarantee that every observer callback can always run across all crash types. If the JVM is forcibly killed or an error happens too early, logs or complete cleanup may still be missing.

**Operationally significant consequences:**

1. **Subsequent runners are no longer called**: Spring does not skip a failing runner to continue down the list on its own.
2. **Earlier effects have already occurred**: Runner A may have written to a database/file or sent a message. A failed startup **does not automatically roll back all of those side effects**.
3. **The context is normally closed during failure handling**: eligible singletons' destruction callbacks get a chance to run. However, do not confuse those callbacks with compensating transactions for external data.
4. **No successful ready milestone**: `ApplicationReadyEvent` does not fire on this path; Boot's readiness does not transition to `ACCEPTING_TRAFFIC` as in a completed startup.
5. **A `Started ...` log may already have appeared before the error**: that INFO line marks the post-refresh milestone, not proof that runners succeeded.

### 3.1. Exceptions May Be Wrapped by Spring Boot

A runner's `run(...)` method may declare `throws Exception`. Spring Boot handles exceptions when invoking runners and on some paths may wrap the cause in an `IllegalStateException` with a message such as "Failed to execute ApplicationRunner" or "Failed to execute CommandLineRunner".

Therefore, when debugging, distinguish:

- **Surface exception**: where SpringApplication reports that runner execution failed.
- **Root cause**: the original exception inside the runner, such as `SQLException`, `IllegalArgumentException`, `TimeoutException`, or an application configuration error.
- **Stack trace**: examine the `Caused by:` chain to locate **the first throw site in application code**, not just Spring's wrapper layer.

Do not write logic depending on exact wrapper message strings across versions. If you need to classify error types, use well-managed exception classes or causal chains.

### 3.2. How Do RuntimeException and Checked Exceptions Differ?

Both `ApplicationRunner.run(...) throws Exception` and `CommandLineRunner.run(...) throws Exception` allow checked exceptions to propagate (in Java, an overriding method can declare compatible exceptions). There is no distinction like "Boot ignores checked exceptions and fails on unchecked exceptions":

- **Checked exception** escaping a runner: startup fails.
- **RuntimeException** escaping a runner: startup fails.
- Serious **`Error`**: may enter the failure branch or leave the JVM unable to clean up, depending on the situation; never use `Error` for business control flow.

What matters is **whether an exception escapes the runner invocation**.

## 4. Runnable Example: Runner B Fails, Runner C Is Skipped

This small example uses **Spring Boot 3.3.13, Java 17, and Gradle**. It prints the order of events, runners, destruction callbacks, and the error received by `main`. This simulates a startup failure; it touches no real database, HTTP service, or file, so output produced by the code is directly verifiable.

### 4.1. The build.gradle File

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

File `settings.gradle`:

```groovy
rootProject.name = 'runner-failure-lab'
```

In `src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=ERROR
```

Disabling INFO does not disable events. The lesson uses non-web mode to keep the lifecycle clear. For a web application, the failure message and failure to reach ready carry the same meaning, though the web server may have started earlier.

### 4.2. Complete Single Java File

Create **`src/main/java/com/example/runner/RunnerFailureApplication.java`**:

```java
package com.example.runner;

import jakarta.annotation.PreDestroy;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class RunnerFailureApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(RunnerFailureApplication.class);
        app.addListeners(new FailureObserver());

        System.out.println("00 main: before run");

        // Catching only so the demo has readable output.
        try {
            app.run(args);
            System.out.println("unexpected success");
        } catch (RuntimeException failure) {
            Throwable root = failure;
            while (root.getCause() != null) {
                root = root.getCause();
            }
            System.out.println("06 main caught: " + root.getMessage());
        }
    }

    // Registered at bootstrap to observe errors even before context creation.
    static final class FailureObserver
            implements ApplicationListener<ApplicationFailedEvent> {

        @Override
        public void onApplicationEvent(ApplicationFailedEvent event) {
            System.out.println("04 ApplicationFailedEvent");
        }
    }

    // Listener bean already exists after refresh.
    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("01 ApplicationStartedEvent");
    }

    @Component
    @Order(10)
    public static class ValidateConfiguration implements ApplicationRunner {

        @Override
        public void run(org.springframework.boot.ApplicationArguments args) {
            System.out.println("02 runner A: validated");
        }
    }

    @Component
    @Order(20)
    public static class LoadRequiredData implements ApplicationRunner {

        @Override
        public void run(org.springframework.boot.ApplicationArguments args) {
            System.out.println("03 runner B: failed");
            throw new IllegalStateException("required seed data missing");
        }
    }

    @Component
    @Order(30)
    public static class FinalizeStartup implements ApplicationRunner {

        @Override
        public void run(org.springframework.boot.ApplicationArguments args) {
            System.out.println("THIS MUST NOT PRINT: runner C");
        }
    }

    // Ordinary singleton to observe destruction.
    @Component
    public static class ShutdownObserver {

        @PreDestroy
        public void shutdown() {
            System.out.println("05 singleton @PreDestroy");
        }
    }
}
```

**Design choices in the example:**

- `FailureObserver` is registered via `app.addListeners(...)` **before** `run(...)`. An `ApplicationFailedEvent` listener placed purely inside a bean might not catch errors occurring before beans exist in the context; bootstrap registration lets you observe a wider range of startup failures.
- `onStarted(...)` is an `@EventListener` method on the application bean; it works after refresh.
- Three nested `static` classes have `@Component` and `@Order(10/20/30)`. Spring scans package `com.example.runner` and discovers the `ApplicationRunner` beans after refresh.
- Runner B intentionally throws `IllegalStateException` to test the failure path, with no external dependencies.
- `ShutdownObserver` is a singleton; `@PreDestroy` helps observe the context closing as Boot handles startup failure. It does not replace cleanup for file/database/remote side effects.
- `main` **catches and does not rethrow the exception solely for this experiment**. As a result, the JVM may exit with code 0 even though startup failed. **Do not copy this `catch` pattern verbatim into a production service**.

### 4.3. Running the Application

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

macOS/Linux:

```bash
./gradlew bootRun
```

Lines printed on stdout by **the Java code itself**, in order with the configuration above:

```text
00 main: before run
01 ApplicationStartedEvent
02 runner A: validated
03 runner B: failed
04 ApplicationFailedEvent
05 singleton @PreDestroy
06 main caught: required seed data missing
```

Spring Boot may still print a stack trace or error log to stderr (because a real error occurred), and Gradle may print task/build info. Those extra lines are outside the compared stdout list.

In particular, the following line **will not appear**:

```text
THIS MUST NOT PRINT: runner C
```

nor will any `ApplicationReadyEvent` line appear, because runner B caused startup to fail.

### 4.4. Why Does the @PreDestroy Line Appear?

During normal failure handling, Boot closes the refreshed context. When the context closes, eligible singletons receive destruction callbacks, such as `ShutdownObserver`'s `@PreDestroy` method. Consequently, the cleanup log appears after the failure event and before the exception is returned to `main` in the example.

This only illustrates **cleanup of Spring-owned singletons**. If runner A wrote a file, committed a transaction, or created a remote resource not tied to bean lifecycle, closing the context **does not automatically undo all of those**. For `prototype` beans, Spring also does not manage per-instance destruction callbacks just because the context closes.

### 4.5. Try Modifying to Verify

1. **Remove the `throw` line in Runner B:** All three runners will be called, Boot publishes `ApplicationReadyEvent`, and `SpringApplication.run(...)` returns normally. In the demo code, the line `"unexpected success"` will appear then; it is merely a label for the failure experiment.
2. **Change Runner B's `@Order(20)` to `@Order(40)`:** Runner C with order 30 will run before B and perform its own side effects before B fails. Remember to adjust log labels if needed.
3. **Make Runner A throw an exception before B:** Neither Runner B nor Runner C is called.
4. **Catch the error inside Runner B and return:** If all runners return normally, Boot can still publish `ApplicationReadyEvent`. Precisely this difference determines whether to fail-fast or gracefully degrade.
5. **Remove the `catch` in `main`:** The exception propagates to the launcher, causing the run task to fail with a non-zero exit code; this is usually the right signal when the application cannot operate safely.

## 5. When Should You Throw an Exception to Fail-Fast?

A runner should fail-fast if it verifies a **mandatory condition** for the application to serve properly:

- Required secret/configuration is missing or invalid.
- Mandatory reference data cannot be loaded and there is no reliable substitute.
- Required system migration or schema invariants are invalid (even though migrations should generally be handled by dedicated tools).
- Resources required by every request cannot be initialized.
- Critical access permissions or security contracts are not met.
- Continuing to accept traffic would return wrong results, lose data, or violate contracts.

When a prerequisite fails, trying to keep running with a "fake ready" application usually causes distributed bugs that are harder to trace than a clear startup failure.

You can throw an exception stating **cause and impact**:

```java
@Override
public void run(ApplicationArguments args) {
    if (requiredCatalog.isEmpty()) {
        throw new IllegalStateException(
                "Cannot start: mandatory product catalog is empty");
    }
}
```

This is an **illustrative snippet**, not standalone runnable: it needs a runner class, an import for `ApplicationArguments`, and a `requiredCatalog` variable of an appropriate type. In production, avoid putting secrets, passwords, or customer payloads into messages/stack traces.

**Important:** "fail-fast" is only the right choice when the condition is genuinely mandatory. Do not turn an optional monitoring endpoint into a single point of failure causing every instance to restart endlessly.

## 6. When Should You Catch the Exception and Continue?

You can handle an error inside a runner and return normally if all of the following hold:

1. **The failing task is optional**, or has a tested fallback.
2. **Business invariants still hold**; bad data will not cause incorrect results or loss of safety.
3. **Degraded state is made visible** via appropriate logs/metrics/health rather than hiding the error.
4. **A recovery path exists**: controlled background retry, periodic refresh, or operational action.
5. **There are no dangerous half-finished side effects**; if any occurred, proper rollback/compensation is in place.

Pseudo-code example inside a runner:

```java
@Override
public void run(ApplicationArguments args) {
    try {
        optionalSearchIndex.warmUp();
    } catch (SearchIndexUnavailableException ex) {
        log.warn("Optional index warm-up failed; using database fallback", ex);
        fallbackMode.enable();
    }
}
```

This is an **illustrative snippet**, requiring classes/imports for `optionalSearchIndex`, `fallbackMode`, `log`, and the actual exception. If the fallback truly meets serving requirements, the runner can complete and Boot reaches Ready.

**Never do this for mandatory data**. The statement:

```java
try {
    loadMandatoryData();
} catch (Exception ignored) {
    // Forbidden pattern when the application cannot operate validly.
}
```

is an anti-pattern. It erases the root cause and lets Boot proceed to the ready milestone.

### 6.1. Boot Ready Does Not Replace Business Health Checks

If a runner catches an error and returns, Spring Boot only sees that **the runner finished**. It can then publish `ApplicationReadyEvent` and `ReadinessState.ACCEPTING_TRAFFIC`. That does not automatically guarantee a downstream service, search index, or external database is healthy.

When readiness truly depends on a condition that can change over time, consider using:

- Actuator readiness group/`HealthIndicator` (when building a web app with the Actuator dependency).
- Custom application state measured by a probe matching operational contracts.
- `ApplicationAvailability` if you need to actively publish the application's readiness state; design clearly when traffic can resume.
- Circuit breaker/fallback mechanisms if the dependency is optional.

Separate **"Boot completed startup"** from **"eligible to receive traffic under the system contract"**. Do not rely solely on an open port or a `Started ...` log to decide.

## 7. Retries Inside Runners: Use Appropriately and With Bounds

Transient network errors may be worth retrying, yet unbounded retries in a runner can leave an instance stuck unready for a very long time. A minimal strategy should have:

- **A limit on attempts** and total wait duration.
- Distinction between **transient** retryable errors and **permanent** errors like bad credentials or incompatible schemas.
- Timeouts on every I/O operation; `Thread.sleep` does not fix a network request that can hang forever.
- Bounded backoff, considering jitter when multiple instances start together to prevent a "thundering herd".
- If interrupted, preserve the interrupt signal or let `InterruptedException` propagate properly.
- After retries are exhausted: **throw an exception** for mandatory conditions; **observable fallback** for optional work.

Java 17 logic example for an essential component, designed with dependency injection:

```java
@Override
public void run(ApplicationArguments args) throws Exception {
    int maxAttempts = 3;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            requiredRemoteClient.checkReady(); // must have its own I/O timeout
            return;
        } catch (TransientRemoteException ex) {
            if (attempt == maxAttempts) {
                throw new IllegalStateException(
                        "Required remote service unavailable after retries", ex);
            }
            Thread.sleep(200L * attempt);
        }
    }
}
```

This is an **illustrative snippet inside a runner**, not a standalone Java file. `requiredRemoteClient` must be injected, `TransientRemoteException` must be a real exception type, and `checkReady` must have a request timeout. `Thread.sleep` here shows simple backoff; production can use a retry library with metrics, jitter, and explicit deadlines.

If `Thread.sleep` is interrupted, `run` declaring `throws Exception` allows `InterruptedException` to propagate, failing startup. Do not catch `InterruptedException` and ignore it; if you must catch it, call `Thread.currentThread().interrupt()` before deciding the next step.

### 7.1. Why Not Retry Every Exception?

Some errors must not be retried blindly:

- `IllegalArgumentException` from misconfiguration.
- `AuthenticationException` from revoked credentials or wrong keys.
- Failed mandatory data validation.
- Incompatible schema migration.
- Programming bug `NullPointerException`.

Retrying these errors only prolongs startup and hides the real cause behind a timeout. Separate domain-specific errors from transient errors and write error-type-specific policies.

### 7.2. @Async in a Runner Is Not a Way to Bypass Failure

If `run` simply opens a `CompletableFuture`, submits a task to an executor, or starts a background thread and returns immediately, Spring Boot **does not automatically await that work**:

```java
@Override
public void run(ApplicationArguments args) {
    executor.submit(() -> loadRequiredCatalog());
    // Runner returns immediately even though catalog may not be loaded yet.
}
```

This is an **anti-pattern** with hypothetical `executor` and `loadRequiredCatalog`. Errors inside the async task may stay inside the `Future` or go to another handler rather than becoming an exception thrown by the runner. Boot may publish ready while the task is still running.

If loading data is a mandatory precondition before readiness, **await the result with a timeout and propagate failure**, or design an explicit independent readiness gate. `@Async` or an executor does not automatically establish a "done before ready" relationship.

## 8. Side Effects of Earlier Runners Do Not Roll Back Automatically

Suppose startup executes:

1. Runner A writes a marker row to the database and commits.
2. Runner B calls an external API; the API returns an error and B throws.
3. Boot closes the context; runner C is never called.

**The data committed by A can still remain**. Spring only manages context lifecycle; it does not open a global transaction spanning all runners.

Safe design directions:

- **Idempotency:** Runners initialize data by stable keys, using upsert/existence checks instead of inserting duplicates on every restart.
- **Transaction boundaries:** Steps that must be atomic within the same database should use a well-scoped transaction instead of expecting the entire startup to roll back automatically.
- **Compensation:** If an external system was called and a later step fails, provide compensation or reconciliation if required by business rules.
- **Versioned checkpoints:** Allow restarts to resume missing pieces in a controlled way.
- **Avoid risky migrations inside runners across all replicas:** When deploying multiple instances, all may run concurrently. Use dedicated migration tools or orchestrated jobs.
- **Time bounds:** Every I/O call needs a deadline, not just the retry loop.
- **Root-cause observability:** Log phase, attempt, non-sensitive resource IDs, and error type—never secrets.

Test failing and restarting repeatedly to verify whether runners corrupt or skew data. This is especially crucial in rolling deployments and autoscaling.

## 9. Context Closing, Destruction Callbacks, and External Resources

When startup fails due to a runner, Boot attempts to handle the error and close the refreshed context. That can trigger:

- `@PreDestroy` on container-managed singletons.
- `DisposableBean.destroy()` or `@Bean(destroyMethod=...)` as defined.
- Stopping container-managed lifecycle/scheduler components properly.
- Shutting down the web server and context-integrated resources.

However, there are limits:

- **Prototype beans:** the container generally does not invoke per-instance destruction callbacks for prototypes when the context closes.
- **Resources created directly with `new`:** if held only in a runner's local variable and not owned/cleaned by a bean, Spring has no way to know to call `close`.
- **Committed transactions or remote side effects:** closing the context does not undo them.
- **Forced termination / SIGKILL:** the JVM cannot guarantee running Java callbacks.
- **Callbacks failing during destruction:** cleanup may remain incomplete, so design resources with timeouts, recoverability, and idempotent closing where needed.

If a runner opens a temporary resource, close it right within the runner's scope:

```java
@Override
public void run(ApplicationArguments args) throws Exception {
    try (InputStream input = Files.newInputStream(configFile)) {
        validate(input); // IOException propagates automatically if unhandled.
    }
}
```

This is an **illustrative snippet**, not a standalone file: `configFile` is a `Path` provided from configuration, `validate(InputStream)` is an application method, and imports for `InputStream`, `Files`, `ApplicationArguments` are required. `try-with-resources` closes the stream even if validation throws.

Do not close a connection pool or HTTP client owned by another singleton simply because a runner borrowed it. The rule is **whoever owns a resource decides its lifetime**.

## 10. ApplicationFailedEvent: Observe Errors, Not a Repair Tool

Spring Boot publishes `ApplicationFailedEvent` when startup encounters an error and is being handled. The event holds the exception and may hold the context (if already created). Distinguish:

- `ApplicationStartedEvent`: context refreshed, before runners.
- `ApplicationReadyEvent`: after runners succeed.
- `ApplicationFailedEvent`: startup entered the failure path.

**An application can publish both `ApplicationStartedEvent` and then `ApplicationFailedEvent` during the same launch** if failure occurs in a runner. There is no contradiction: "started" is the pre-runner milestone, while "ready" is post-runner.

To observe very early failures, register a listener at bootstrap rather than relying solely on `@Component`:

```java
SpringApplication app = new SpringApplication(MyApp.class);
app.addListeners(new MyFailureListener());
app.run(args);
```

This is an illustrative snippet; `MyFailureListener` must implement `ApplicationListener<ApplicationFailedEvent>` and have a real implementation. Section 4's runnable example uses this exact approach.

You can listen for `ApplicationFailedEvent` from a bean in cases where the context is already active (such as runner failures), yet **never assume a bean listener exists for every early-stage error**. Moreover, a failure-handling listener can itself throw; prefer **fast recording, minimal side effects, and no unbounded blocking**.

The application needs appropriate logging/observability:

- Log root cause, runner name, phase, and non-sensitive correlation ID.
- If alerts/metrics are needed, emit them via a mechanism that will not introduce new failures during shutdown.
- Do not rely on a failure listener to "flip ready back on" after a runner has thrown.
- Never call a full `SpringApplication.run(...)` again inside a failure listener to rescue startup; that creates a new context and risks resource, side-effect, port, and thread issues.

## 11. Exit Codes: Do Not Mask Startup Failures

### 11.1. Exceptions Escaping main

With a standard entry point:

```java
public static void main(String[] args) {
    SpringApplication.run(MyApplication.class, args);
}
```

if a runner fails and Boot does not complete startup, the exception propagates to the launcher. An application launched via `java -jar` will normally not terminate as successful, and orchestration/build tools receive a failure status. That is a useful signal for deployment.

By contrast, section 4's example **caught the exception in `main` without rethrowing** so stdout stayed clear:

```java
try {
    app.run(args);
} catch (RuntimeException ex) {
    System.err.println("Startup failed: " + ex.getMessage());
    // Simply returning from main here can let the process exit 0.
}
```

This is an **anti-pattern in production**. If the caller silently swallows the exception, the orchestrator may see the process exit "successfully" even though startup never reached ready.

The typical production choice is **to let Boot throw the error outward**. If adding logging in `main`, rethrow after writing a concise message:

```java
try {
    SpringApplication.run(MyApplication.class, args);
} catch (RuntimeException ex) {
    System.err.println("Startup failed: " + ex.getClass().getSimpleName());
    throw ex;
}
```

This is an illustrative snippet requiring class `MyApplication` and importing `SpringApplication`.

### 11.2. ExitCodeGenerator and Custom Exit Codes

Spring Boot also provides `ExitCodeGenerator`, `ExitCodeExceptionMapper`, and related mechanisms to assign custom meanings to exit codes. This is an adjacent topic to failure handling, yet **do not assume simply implementing an interface guarantees every launcher receives a specific exit code**. Final behavior depends on how the application is launched, how Spring Boot processes exit codes, and how the process terminates.

If infrastructure requires standardized exit codes, test with the exact `java -jar`, container entrypoint, or build tool in use. Avoid calling `System.exit(0)` after a runner fails.

## 12. The Web Server May Already Have Opened Its Port While the Service Is Not Ready

In a Servlet/Reactive web application, the embedded web server is typically initialized during context refresh, **before** runners. Thus this situation can arise:

```text
HTTP port listening
   |
   +--> ApplicationStartedEvent
   |
   +--> runner loads mandatory data, throws error after 5 seconds
   |
   +--> ApplicationFailedEvent
   +--> context/web server shutdown
   |
   X    ApplicationReadyEvent
```

Do not use a TCP "port open" check or a `Started ...` log as the sole criterion for routing requests. In systems with a load balancer/Kubernetes, combine readiness probes against the proper endpoint/port/security with operational contracts.

Spring Boot Actuator provides liveness/readiness health groups when configured appropriately. While startup has not finished runners, Boot's readiness state has not transitioned to `ACCEPTING_TRAFFIC` along the normal ready path.

Several notes:

- Actuator must be added as a dependency and endpoints must be properly configured/exposed.
- Readiness probes only block traffic if **the orchestrator actually uses them**.
- If an instance binds its port before readiness succeeds, the application can still receive direct requests if a client bypasses the load balancer/probe.
- If a dependency is a dynamic operational requirement, custom health/readiness indicators may need to reflect post-startup state rather than relying solely on a one-shot runner.
- Liveness and readiness are two different signals: do not trigger a restart every time an external dependency blips briefly.

## 13. Common Misconceptions

| Claim or Symptom | Where Is It Wrong? | Check / Remedy |
| --- | --- | --- |
| "Seeing `Started ...` means all runners are done" | Log marks post-refresh, pre-runner milestone | Track `ApplicationReadyEvent` or readiness |
| "Runner B throws yet Boot still calls runner C" | Runner calls are a synchronous chain; errors abort startup | Check runner order and root exception |
| "`CommandLineRunner` always runs after `ApplicationRunner`" | Both runner types are sorted together | Set explicit `@Order`/`Ordered` |
| "`ApplicationStartedEvent` cannot occur alongside `ApplicationFailedEvent`" | A runner can fail **after** started | Review event sequence |
| "`ApplicationFailedEvent` is guaranteed to reach every bean listener" | Beans may not be initialized in early failures | Register listeners at bootstrap |
| "Closing the context rolls back runner A's database commit" | Context destruction is not a global transaction rollback | Use idempotency/transactions/compensation |
| "Catching `Exception` and returning so the app doesn't crash is always good" | Can create a false ready state with bad data | Distinguish mandatory vs. optional and degraded states |
| "With `@Async`, a task error makes the runner throw" | Runner can return before the task; exceptions do not propagate back automatically | Await with deadline or use a readiness gate |
| "Retrying forever will eventually succeed" | Permanent errors exist and deployments can hang | Bound attempts/deadlines, classify errors |
| "Context always calls `@PreDestroy` after every crash" | Process may be killed; context may not exist or cleanup may fail | Design for crash recovery |
| "`@Order` just needs numbers and every runner will run" | An earlier failing runner blocks later runners | Test ordering and failure paths |
| "Catching exceptions in `main` and returning still guarantees a non-zero exit" | Swallowing the exception can exit 0 | Rethrow or design explicit exit handling |
| "When a runner throws, all side effects vanish" | Prior side effects may already have committed | Design idempotency and reconciliation |
| "No `ApplicationReadyEvent` means the process died instantly" | Failure reporting/cleanup phase may be running | Observe startup state, process, and shutdown |

## 14. Debugging Checklist When Startup Stops at a Runner

1. **Identify the exact phase:** do logs/traces show `ApplicationStartedEvent`? If yes without ready, inspect runners and ready listeners.
2. **Identify the failing runner:** read the "Failed to execute ...Runner" stack trace, locating your application `run(...)` class/method and root `Caused by`.
3. **Check ordering:** `@Order`, `Ordered`, and beans across both interfaces; never assume class names determine order.
4. **Inspect side effects prior to failure:** were files/databases/messages written? Will restarting duplicate or corrupt state?
5. **Classify the error:** permanent validation/config, transient network, permissions, schema, timeout, or code bug.
6. **Verify retry logic:** are timeouts, attempt limits, backoff, and final error propagation present?
7. **Check for swallowed errors:** are there empty `catch (Exception)` blocks, unconditional `onErrorResume`/fallbacks, or unawaited `Future`s?
8. **Check failure events and cleanup:** did `ApplicationFailedEvent` reach an early-registered listener? Did singleton resources shut down properly?
9. **Check deployment readiness:** can load balancers/Kubernetes see an open port before ready? Is a proper readiness probe configured?
10. **Check process exit code:** test with the real launcher (`java -jar`, container, Gradle), paying attention to `catch` blocks in `main`.
11. **Check multi-instance deployments:** do runners execute concurrently across replicas and cause races or duplicate migrations?
12. **Add tests for the failure path:** verify subsequent runners are not called, ready does not fire, side effects are safe to retry, and logs contain actionable causes.

Log just enough: runner name, phase, error type, attempt count, duration, context/instance ID. Never dump secrets, credentials, tokens, personal data, or the entire environment.

## 15. Self-Assessment

**Question 1.** Runner A `@Order(10)` succeeds, Runner B `@Order(20)` throws, Runner C `@Order(30)` has not been called. Can startup be considered successful?

**Answer:** No. Boot enters startup failure handling; runner C does not proceed, and `ApplicationReadyEvent` is not published on the successful startup path.

**Question 2.** Why can you still see the log "Started ExampleApplication" before a runner error?

**Answer:** Because the started log and `ApplicationStartedEvent` occur after refresh yet **before** invoking runners.

**Question 3.** Will Spring Boot automatically roll back a transaction committed in an earlier runner?

**Answer:** No. Each transaction/side effect has its own boundary. Explicit idempotency, transaction boundaries, or compensation must be designed.

**Question 4.** If a runner catches an error from a mandatory operation and returns, what can happen?

**Answer:** Boot can proceed to invoke later runners and report ready even though the prerequisite was not met. This is dangerous if the service lacks a proper fallback.

**Question 5.** Can `ApplicationFailedEvent` occur after `ApplicationStartedEvent`?

**Answer:** Yes. A runner can fail after the started milestone; the failure event reflects that startup ultimately did not complete.

**Question 6.** A runner submits a background task and returns. If the background task throws, is `SpringApplication.run` guaranteed to throw as well?

**Answer:** No. The exception lives on another thread or future and does not automatically fail the synchronous runner call. If the task is a mandatory precondition, you must await it and propagate errors properly.

**Question 7.** What should be done for transient errors when a runner needs to connect to a mandatory downstream service?

**Answer:** Use I/O timeouts and bounded retries with sensible backoff/jitter; once exhausted, propagate the startup error rather than retrying forever.

**Question 8.** Why can a singleton's `@PreDestroy` run after a runner failure yet not be enough to guarantee data consistency?

**Answer:** The context is closed during failure handling, allowing callbacks to run. However, callbacks do not automatically reverse committed transactions, remote side effects, or crashes caused by SIGKILL.

**Question 9.** If readiness needs to differ from simply having runners return, what tools should you use?

**Answer:** Readiness health checks/Actuator, `ApplicationAvailability`, and appropriate orchestration probes based on genuine serving readiness.

**Question 10.** Why should you not swallow exceptions in `main` in production?

**Answer:** Launchers may receive a false zero exit code even though the application is non-functional; let exceptions propagate or use a tested exit-code strategy.

## 16. Summary and References

**Key Points to Remember:**

- **Runner throws outward → Spring Boot 3.3.x handles it as a startup failure.** Subsequent runners are not called, `ApplicationReadyEvent` does not occur, and `SpringApplication.run(...)` does not return normally.
- **Started does not mean ready:** `ApplicationStartedEvent` and the started log may already have appeared before a runner fails.
- **Failure reporting and cleanup have limits:** `ApplicationFailedEvent` may be published; singleton destruction callbacks may be called when the context closes. Do not mistake this for rolling back all side effects.
- **Fail-fast for mandatory conditions, observable fallback for optional conditions.** Avoid swallowing errors and reporting ready falsely.
- **Bounded retries, I/O timeouts, idempotency, and proper exit codes** are essential operational safeguards.
- **Do not offload mandatory work to the background and return** if startup/readiness must still depend on that work's outcome.

Official references:

- [Spring Boot 3.3 — SpringApplication: Application Events and Listeners / CommandLineRunner and ApplicationRunner](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html).
- [Spring Boot 3.3 — SpringApplication Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html).
- [Spring Boot 3.3 — ApplicationFailedEvent Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationFailedEvent.html).
- [Spring Boot 3.3 — ApplicationRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html).
- [Spring Boot 3.3 — Actuator Health/Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

A helpful exception message does not only state **which runner failed**, but also **which mandatory condition was not met, what prior effects may already have occurred, and whether startup should proceed**. Designing these boundaries clearly makes applications safer to boot and deploy.
