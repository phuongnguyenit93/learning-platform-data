# Testing Startup Failures and FailureAnalyzer in Spring Boot

## 1. Goal of this lesson

A Spring Boot application must not only start successfully under normal conditions, it must also **fail properly** when configuration is invalid, dependencies are missing, a bean throws an exception, or a startup task is rejected. Writing tests for these scenarios differs significantly from testing an active controller or service.

A reliable startup-failure testing workflow must answer all of the following simultaneously:

1. **Did it actually fail?** The context or process must refuse to start, rather than logging an error and still being considered ready.
2. **At which stage did the error occur?** Before context creation, during `refresh()`, inside `ApplicationRunner`, or after `ApplicationReadyEvent`?
3. **Is the cause identified accurately?** Tests must locate the exact exception deep inside the cause chain, not merely match a vague message.
4. **Does `FailureAnalyzer` analyze properly?** It recognizes supported errors and produces a `FailureAnalysis` with helpful description and remediation action, without "swallowing" the error.
5. **Is the analyzer registered properly?** A unit test calling the analyzer directly does not prove Boot loads it during a real bootstrap.
6. **What about exit codes and resources?** The process must report failure; singletons that finished construction must be closed per lifecycle contract, while partially opened resources need their own cleanup.
7. **Are the tests isolated and stable?** Never kill the JUnit JVM; avoid depending on free ports, nondeterministic delays, log ordering, ANSI codes, or developer-machine profiles.

Focus: **Spring Boot 3.3.x, Java 17+, JUnit Jupiter 5, AssertJ, `ApplicationContextRunner`, and `FailureAnalyzer`**. The example section uses Gradle and provides complete runnable source code; snippets outside the project are labeled as illustrative.

### Key takeaway to remember immediately

**No single test harness fits every kind of startup failure.**

- **Unit tests:** verify validator/exception/analyzer logic without a Spring context.
- **`ApplicationContextRunner`:** builds a lightweight context, tests bean configuration and `refresh()` errors, is easy to control, and auto-closes.
- **Boot integration tests with `SpringApplication.run(...)`:** test the startup flow with real runners and events.
- **Process-level tests with `java -jar`:** verify `FailureAnalysisReporter` output, real exit codes, and JVM termination behavior.

Choose the smallest layer capable of proving the requirement, then add a few end-to-end tests for wiring that smaller tests do not cover.

## 2. Startup lifecycle and where errors can originate

A Spring Boot application traverses multiple steps. Errors at each step lead to differences in existing beans, emitted events, and cleanup capabilities.

```text
main(args)
  |
  v
SpringApplication prepares Environment
  |          \-- may fail on config data / properties
  v
Create ApplicationContext
  |          \-- may fail in context initializer
  v
Load bean definitions then refresh()
  |          +-- create eager singletons
  |          +-- bind and validate properties
  |          +-- @PostConstruct / init methods
  |          +-- SmartLifecycle auto-start
  |          \-- may fail on dependency / constructor / init
  v
ApplicationStartedEvent
  |
  v
ApplicationRunner / CommandLineRunner
  |          \-- may throw exception
  v
ApplicationReadyEvent
  |
  v
App ready, SpringApplication.run(...) returns context

If startup fails:
  → Spring Boot triggers failure handling
  → Registered FailureAnalyzers get a chance to analyze
  → FailureAnalysisReporter can display description/action
  → Context is closed if created; refresh has its own cleanup
  → Exception is still propagated
  → Process launcher/JVM reports appropriate failure status
```

This diagram condenses the sequence and omits internal hooks. Analyzers/reporters handle **diagnostics**, not replacing context closing mechanisms. Errors in background jobs **after** `SpringApplication.run(...)` returns do not automatically turn into an `ApplicationFailedEvent` for the previous startup.

### Testing tool selection table

| Scenario | Preferred test level | What to verify |
| --- | --- | --- |
| Validator rejects invalid value | Pure unit test | Error type and policy |
| `@Bean` factory throws | `ApplicationContextRunner` | Context fails to refresh, root cause |
| `@ConfigurationProperties` validation fails | `ApplicationContextRunner` or suitable slice test | Binding/validation and cause chain |
| Missing required dependency | Context runner | `NoSuchBeanDefinitionException` in cause chain |
| Previously created bean needs destruction | Context runner with resource recorder | Close callback invoked |
| `ApplicationRunner` throws | `SpringApplication.run` / process test | Runner actually ran; startup failed |
| Custom analyzer handles exception | Analyzer unit test | `FailureAnalysis` description/action/cause |
| Custom analyzer discovered by Boot | Process-level integration | Analyzer report appears in output |
| Reporter prints right guidance | Process-level or reporter unit | Output has safe, stable content |
| Non-zero exit code | Run JAR in separate process | OS process status, not logs |
| Error on occupied HTTP port | Integration with controlled resource, rarely unit | Deterministic failure independent of machine |
| Very early config failure | Process/integration with early listener | Application context may not exist yet |
| Error after service ready | Separate runtime failure test | Do not confuse with boot failure |

## 3. What does FailureAnalyzer actually do?

Spring Boot defines the interface:

```java
package org.springframework.boot.diagnostics;

public interface FailureAnalyzer {
    FailureAnalysis analyze(Throwable failure);
}
```

This is a **condensed signature for study**, not a file you define yourself. In applications, import Spring Boot's built-in interface.

- Input: a `Throwable` that may be a wrapper exception with multiple cause layers.
- Output when recognized: a `FailureAnalysis`.
- Output when unrecognized: **`null`**, giving other analyzers a chance to handle it.
- The analyzer **does not fix configuration**, does not restart the app, and does not turn a failure into success.
- The analyzer also **does not directly decide the exit code**; for specific exit codes, use `ExitCodeGenerator`/dedicated exit mechanisms.

`FailureAnalysis` holds three critical pieces of data:

| Property | Meaning |
| --- | --- |
| `getDescription()` | Explains what failed |
| `getAction()` | Specific instructions on what operators should fix |
| `getCause()` | The exception serving as the basis for analysis |

The constructor takes the form:

```java
new FailureAnalysis(description, action, cause)
```

When Boot cannot produce an analysis from registered analyzers, the dedicated failure-analysis reporter does not necessarily emit a short summary report; Boot still reports the standard startup error.

### 3.1. Separating analyzer and reporter

There are two contracts:

```text
Throwable from startup
       |
       v
FailureAnalyzer.analyze(Throwable)
       |
       +-- null -> another analyzer may try
       |
       +-- FailureAnalysis(description, action, cause)
                         |
                         v
FailureAnalysisReporter.report(FailureAnalysis)
                         |
                         v
Log / console / corresponding reporting mechanism
```

Spring Boot provides `LoggingFailureAnalysisReporter` by default to log a report such as:

```text
***************************
APPLICATION FAILED TO START
***************************

Description:

The demonstration bootstrap mode is invalid.

Action:

Set demo.bootstrap.mode=ok and restart.
```

This is an **illustrative layout**. Do not assert identical whitespace, timestamp prefixes, ANSI colors, or stack traces across every logging backend.

**Do not confuse:** `FailureAnalyzer` returns data; `FailureAnalysisReporter` presents data. Neither alters the fact that the exception still fails startup.

### 3.2. AbstractFailureAnalyzer<T>

Spring Boot provides:

```java
AbstractFailureAnalyzer<T extends Throwable>
```

This base class finds an exception of type `T` in the cause chain, then calls the analysis method:

```java
protected FailureAnalysis analyze(Throwable rootFailure, T cause)
```

Benefits:

- Avoids manually traversing the cause chain in every analyzer.
- Allows testing cases where the exception is wrapped by `BeanCreationException` / `BeanInstantiationException`.
- Keeps each analyzer focused solely on the exceptions it owns.
- Returns `null` if uninterpretable so other analyzers can handle it.

## 4. Registering FailureAnalyzer properly in Spring Boot 3.3

A particularly common mistake is writing:

```java
@Component
class MyFailureAnalyzer implements FailureAnalyzer {
    // ...
}
```

and assuming Boot is guaranteed to discover it for **every error before the context is successfully created**.

For custom bootstrap `FailureAnalyzer`s, Spring Boot's official guide requires **registering via `META-INF/spring.factories`**. Reason: the analyzer may need to run when the application context is incomplete or does not exist at all; component scanning alone cannot satisfy this contract.

File:

```text
src/main/resources/META-INF/spring.factories
```

Example:

```properties
org.springframework.boot.diagnostics.FailureAnalyzer=\
demo.startupcheck.StartupPolicyFailureAnalyzer
```

- The key is the **fully qualified interface name**.
- The value is the **fully qualified class name** of an instantiable analyzer.
- The trailing `\` on the property line continues the value onto the next line.
- The file must be present on the **runtime classpath**, including inside the packaged JAR.
- The analyzer class needs a constructor instantiable by the loader (simplest is a public no-arg constructor) and must not strictly depend on beans that may not exist yet.
- When developing a starter or library, the dependency's `spring.factories` file is loaded alongside the application's files.

**Do not move `FailureAnalyzer` registration to `AutoConfiguration.imports`.** The `AutoConfiguration.imports` file serves auto-configuration registration in modern Boot, whereas failure analyzers use key `org.springframework.boot.diagnostics.FailureAnalyzer` in `spring.factories` per Boot 3.3's official contract.

### 4.1. Do not blindly use bean injection in an analyzer

Spring Boot can support creating analyzers with `BeanFactory` or `Environment` if available, yet an ultra-early error can occur **before the context is ready**.

To keep analyzers reliable:

- Keep analyzers simple and free of side effects.
- Do not query repositories/databases or business beans.
- Do not assume all properties have been bound.
- Never throw a second exception from the analyzer while reading error data.
- Avoid putting raw secret or token values into description/action.

## 5. Complete example project

We build a small application with **two intentional failure paths**:

1. Invalid `demo.bootstrap.mode`: bean `StartupMarker` fails to be created, and the context **fails during refresh**.
2. `demo.runner.fail=true`: context refresh succeeds, yet `ApplicationRunner` throws an exception; Boot **fails during the runner phase**.

Both use a business exception with two distinct reasons. The custom analyzer maps each reason to its own description/action without printing raw input values.

### 5.1. Project structure

```text
startup-check-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          startupcheck/
            StartupCheckApplication.java
            StartupGuardConfiguration.java
            StartupMarker.java
            StartupPolicyException.java
            StartupPolicyFailureAnalyzer.java
      resources/
        application.properties
        META-INF/
          spring.factories
    test/
      java/
        demo/
          startupcheck/
            StartupGuardContextTests.java
            StartupPolicyFailureAnalyzerTests.java
            ContextCleanupTests.java
```

### 5.2. Gradle: Java 17 and Spring Boot 3.3.x

`settings.gradle`:

```groovy
rootProject.name = 'startup-check-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot 3.3.13 is chosen to illustrate the 3.3 branch APIs, not as a recommendation to use an older release in new production systems. The project requires JDK 17+ and compatible Gradle/Gradle wrapper. The `build.gradle` file **does not generate `gradlew` automatically**; if no wrapper exists, run `gradle wrapper` with an installed Gradle.

`src/main/resources/application.properties`:

```properties
spring.application.name=startup-check-demo
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR

demo.bootstrap.mode=ok
demo.runner.fail=false
```

The app runs non-web to test startup without needing an HTTP port; both default properties are valid.

### 5.3. StartupMarker.java

```java
package demo.startupcheck;

public record StartupMarker(String mode) {
}
```

`record` is valid on Java 17+. It represents a bean created **only when configuration is valid**. No DB, file, or network connections are made, keeping tests deterministic.

### 5.4. StartupPolicyException.java

```java
package demo.startupcheck;

public final class StartupPolicyException
        extends RuntimeException {

    public enum Problem {
        INVALID_MODE,
        RUNNER_BLOCKED
    }

    private final Problem problem;

    public StartupPolicyException(Problem problem) {
        super("Startup policy rejected an operation.");
        this.problem = problem;
    }

    public Problem problem() {
        return problem;
    }
}
```

We do not concatenate raw input values into the exception message. `problem` is a code-controlled enum, convenient for both the analyzer and tests.

### 5.5. StartupGuardConfiguration.java

```java
package demo.startupcheck;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class StartupGuardConfiguration {

    @Bean
    StartupMarker startupMarker(
            @Value("${demo.bootstrap.mode:ok}") String mode) {

        if (!"ok".equals(mode)) {
            throw new StartupPolicyException(
                    StartupPolicyException.Problem.INVALID_MODE);
        }

        return new StartupMarker("ok");
    }
}
```

The error is thrown **inside the `@Bean` factory method**. When the container tries to instantiate this eager singleton during `refresh()`, Spring may wrap `StartupPolicyException` in `BeanCreationException` and other exceptions.

Tests **must not demand the outermost exception be literally `StartupPolicyException`**. Inspect the root cause or analyze the cause chain.

### 5.6. StartupCheckApplication.java

```java
package demo.startupcheck;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class StartupCheckApplication {

    public static void main(String[] args) {
        SpringApplication.run(StartupCheckApplication.class, args);
    }

    @Bean
    ApplicationRunner demoRunner(
            StartupMarker marker,
            @Value("${demo.runner.fail:false}") boolean shouldFail) {

        return arguments -> {
            if (shouldFail) {
                throw new StartupPolicyException(
                        StartupPolicyException.Problem.RUNNER_BLOCKED);
            }

            System.out.println("runner.ok=" + marker.mode());
        };
    }
}
```

On the success path, the marker printed by code is:

```text
runner.ok=ok
```

On the `demo.bootstrap.mode=invalid` path, Spring cannot create `StartupMarker`, so the runner never succeeds. On the `demo.runner.fail=true` path, context refresh finishes, the runner is called, and then it intentionally throws an exception.

**Note:** `ApplicationRunner` is invoked by `SpringApplication` after refresh; `ApplicationContextRunner` only creates/refreshes a context and **does not automatically call** runners. We test the two failure paths differently.

### 5.7. StartupPolicyFailureAnalyzer.java

```java
package demo.startupcheck;

import org.springframework.boot.diagnostics.AbstractFailureAnalyzer;
import org.springframework.boot.diagnostics.FailureAnalysis;

public final class StartupPolicyFailureAnalyzer
        extends AbstractFailureAnalyzer<StartupPolicyException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure, StartupPolicyException cause) {

        String description = switch (cause.problem()) {
            case INVALID_MODE ->
                    "The demonstration bootstrap mode is invalid.";
            case RUNNER_BLOCKED ->
                    "The demonstration startup runner was blocked.";
        };

        String action = switch (cause.problem()) {
            case INVALID_MODE ->
                    "Set demo.bootstrap.mode=ok and restart.";
            case RUNNER_BLOCKED ->
                    "Set demo.runner.fail=false and restart.";
        };

        return new FailureAnalysis(description, action, cause);
    }
}
```

`AbstractFailureAnalyzer` finds `StartupPolicyException` in the cause chain, even when Spring wraps it in infrastructure exceptions.

**Why not include the full `cause.getMessage()` in the report?** Because in real applications, exception messages can contain config values, tokens, connection URLs, or sensitive data. Here descriptions and actions derive from a known enum, keeping reports stable and safe.

### 5.8. META-INF/spring.factories

File `src/main/resources/META-INF/spring.factories`:

```properties
org.springframework.boot.diagnostics.FailureAnalyzer=\
demo.startupcheck.StartupPolicyFailureAnalyzer
```

This file is **mandatory for the custom analyzer integration test path**. A direct test of `new StartupPolicyFailureAnalyzer()` passes even when this file is wrong or missing; therefore registration itself must also be tested.

### 5.9. Running the application successfully

With Gradle wrapper:

```bash
./gradlew bootRun
```

Marker printed by application code:

```text
runner.ok=ok
```

Gradle and Spring Boot may print extra output. No failure report appears because both properties are valid.

### 5.10. Refresh failure: invalid mode configuration

```bash
./gradlew bootRun --args='--demo.bootstrap.mode=invalid'
```

Key lines in the report when Boot loads the analyzer and the logging reporter runs:

```text
APPLICATION FAILED TO START

Description:

The demonstration bootstrap mode is invalid.

Action:

Set demo.bootstrap.mode=ok and restart.
```

**This is the key excerpt**, not the full stdout/stderr. Loggers may add headers, timestamps, stack traces, and Gradle task failure summaries. `runner.ok=ok` **must not appear** because bean initialization failed before the runner was invoked.

### 5.11. Runner failure: context refresh succeeded

```bash
./gradlew bootRun --args='--demo.runner.fail=true'
```

Expected report:

```text
APPLICATION FAILED TO START

Description:

The demonstration startup runner was blocked.

Action:

Set demo.runner.fail=false and restart.
```

The error occurs **after refresh**, yet still inside `SpringApplication.run(...)`. It still counts as a startup failure, and `ApplicationReadyEvent` does not mark a successful startup.

**The two tests are not equivalent:** use the context runner to test refresh errors; to test real runner failures, run `SpringApplication.run` or the corresponding Boot process.

## 6. Unit testing FailureAnalyzer: testing logic without a context

File `src/test/java/demo/startupcheck/StartupPolicyFailureAnalyzerTests.java`:

```java
package demo.startupcheck;

import org.junit.jupiter.api.Test;
import org.springframework.boot.diagnostics.FailureAnalysis;

import static org.assertj.core.api.Assertions.assertThat;

class StartupPolicyFailureAnalyzerTests {

    private final StartupPolicyFailureAnalyzer analyzer =
            new StartupPolicyFailureAnalyzer();

    @Test
    void analyzesInvalidModeNestedInsideAnotherException() {
        Throwable failure = new IllegalStateException(
                "Framework wrapper",
                new StartupPolicyException(
                        StartupPolicyException.Problem.INVALID_MODE));

        FailureAnalysis analysis = analyzer.analyze(failure);

        assertThat(analysis).isNotNull();
        assertThat(analysis.getDescription())
                .isEqualTo(
                        "The demonstration bootstrap mode is invalid.");
        assertThat(analysis.getAction())
                .isEqualTo(
                        "Set demo.bootstrap.mode=ok and restart.");
        assertThat(analysis.getCause())
                .isInstanceOf(StartupPolicyException.class);
    }

    @Test
    void analyzesRunnerFailureWithDifferentAction() {
        Throwable failure = new StartupPolicyException(
                StartupPolicyException.Problem.RUNNER_BLOCKED);

        FailureAnalysis analysis = analyzer.analyze(failure);

        assertThat(analysis).isNotNull();
        assertThat(analysis.getDescription())
                .isEqualTo(
                        "The demonstration startup runner was blocked.");
        assertThat(analysis.getAction())
                .isEqualTo(
                        "Set demo.runner.fail=false and restart.");
    }

    @Test
    void returnsNullForUnrelatedException() {
        FailureAnalysis analysis =
                analyzer.analyze(new IllegalArgumentException("other"));

        assertThat(analysis).isNull();
    }
}
```

Three independent tests demonstrate:

1. The analyzer handles **an exception nested deep in the cause chain**.
2. One exception type can produce different actions per **business error category**.
3. The analyzer returns `null` for unrecognized errors so other analyzers can try.

**Critical limitation:** these three tests **do not prove** `spring.factories` exists, Boot loaded the analyzer, the default reporter printed output, or the process exited non-zero. They only verify **the logic of a single analyzer object**.

### 6.1. Why check both description and action?

A quality analyzer must report:

- **Description:** which policy violation occurred, not merely repeating `IllegalStateException`.
- **Action:** what operators can change — property, dependency, port, or concrete remediation step.
- **Cause:** preserving the exception as evidence.

A test that only asserts `analysis != null` can miss an analyzer returning a wrong, unsafe, or overly generic action.

### 6.2. Testing the null path is a public contract

For `FailureAnalyzer`, `null` **does not mean a broken test**. It means this analyzer does not support the current exception. Returning a bogus `FailureAnalysis` for **every** error can steal the opportunity from a more specialized analyzer.

Therefore, negative-path tests are mandatory for shared analyzers.

## 7. ApplicationContextRunner: testing refresh failures in a controlled way

`org.springframework.boot.test.context.runner.ApplicationContextRunner` supports running a lightweight application context with defined bean configurations. It is well-suited to test:

- Bean presence or absence.
- Property binding.
- `@ConditionalOnProperty` conditions.
- Constructor or `@Bean` factory errors.
- Exceptions in `@PostConstruct`.
- Singleton cleanup when refresh fails.

**Not equivalent to running the full `SpringApplication` startup.** It builds a test context, does not emit the full Boot `ApplicationStartedEvent`/`ApplicationReadyEvent` suite, and **does not auto-invoke `ApplicationRunner`**.

### 7.1. Testing context success and failure

File `src/test/java/demo/startupcheck/StartupGuardContextTests.java`:

```java
package demo.startupcheck;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class StartupGuardContextTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            StartupGuardConfiguration.class);

    @Test
    void startsWithValidMode() {
        runner.withPropertyValues("demo.bootstrap.mode=ok")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(StartupMarker.class);
                    assertThat(context.getBean(StartupMarker.class).mode())
                            .isEqualTo("ok");
                });
    }

    @Test
    void failsDuringRefreshWithInvalidMode() {
        runner.withPropertyValues(
                "demo.bootstrap.mode=invalid")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(
                                    StartupPolicyException.class);
                });
    }
}
```

This is a complete JUnit 5/AssertJ test in the configured Gradle environment.

- `withUserConfiguration` registers only `StartupGuardConfiguration`.
- `withPropertyValues` injects properties into the test context.
- `run(context -> ...)` supplies an **`AssertableApplicationContext`** to the callback.
- When refresh fails, the callback **is still invoked** with the failed state for assertions.
- Once the callback finishes, the runner cleans up the context properly.
- `getStartupFailure()` reveals the exception raised during context initialization.
- `hasRootCauseInstanceOf` checks the deepest cause, decoupling the test from the exact number of Spring wrapper exceptions.

**Never call `context.getBean(...)` in the failure branch** to probe beans casually: the context did not refresh cleanly and doing so can throw another error, masking the main assertion.

### 7.2. Why assert the root cause instead of a full message?

A `@Bean` factory throwing:

```text
StartupPolicyException
```

can be wrapped by the framework as:

```text
BeanCreationException
    |
    +-- BeanInstantiationException
              |
              +-- StartupPolicyException
```

Wrapper order/types can vary by version or bean creation point. Asserting verbatim on a huge message like:

```text
Error creating bean with name ... defined in class path ...
```

makes tests brittle against changes unrelated to behavior.

**Better:** assert the exception type in the cause chain and check a few business-meaningful details, without locking the test to a full stack trace.

### 7.3. The runner is a per-run immutable API

`ApplicationContextRunner` methods like `withPropertyValues`/`withUserConfiguration` return a newly configured runner in builder style. There is no need to mutate shared fields across tests when switching from success to failure. This reduces cross-test interference under varying test execution orders.

### 7.4. Why can't context runner test FailureAnalyzer wiring?

`ApplicationContextRunner` runs a test `ApplicationContext`, **not the default `SpringApplication.run(...)` path with `SpringBootExceptionReporter`s loaded at startup**. Thus a context failure test can pass even when `META-INF/spring.factories` contains a misspelled analyzer name.

Treat it as **testing context behavior**, not testing full startup diagnostics. Test the analyzer separately, then run the JAR to confirm final wiring/reporting.

## 8. Testing cleanup when context refresh fails

A startup error can occur **after several singletons have already been created successfully**. Tests should prove that container-owned resources are cleaned up, without claiming destructors run for objects that never finished construction.

File `src/test/java/demo/startupcheck/ContextCleanupTests.java`:

```java
package demo.startupcheck;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ContextCleanupTests {

    @Test
    void closesCompletedSingletonWhenLaterBeanCreationFails() {
        CleanupConfiguration.CLOSE_COUNT.set(0);

        new ApplicationContextRunner()
                .withUserConfiguration(CleanupConfiguration.class)
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(
                                    StartupPolicyException.class);
                });

        assertThat(CleanupConfiguration.CLOSE_COUNT.get())
                .isEqualTo(1);
    }

    @Configuration(proxyBeanMethods = false)
    static class CleanupConfiguration {

        static final AtomicInteger CLOSE_COUNT =
                new AtomicInteger();

        @Bean(destroyMethod = "close")
        TrackedResource trackedResource() {
            return new TrackedResource(CLOSE_COUNT);
        }

        @Bean
        String failingBean(TrackedResource alreadyCreated) {
            throw new StartupPolicyException(
                    StartupPolicyException.Problem.INVALID_MODE);
        }
    }

    static final class TrackedResource implements AutoCloseable {

        private final AtomicInteger closeCount;

        TrackedResource(AtomicInteger closeCount) {
            this.closeCount = closeCount;
        }

        @Override
        public void close() {
            closeCount.incrementAndGet();
        }
    }
}
```

**Why this test matters:**

- `failingBean(TrackedResource alreadyCreated)` forces Spring to create `TrackedResource` **before** invoking the failing factory method.
- `TrackedResource` was returned to the bean factory cleanly and registered custom destructor `close`.
- When refresh fails on the subsequent bean, Spring destroys already-created singletons.
- `CLOSE_COUNT` lets the test verify the cleanup mechanism without opening real sockets/files.
- Does not depend on delays or process termination.

### 8.1. Note on static recorders in tests

`CLOSE_COUNT` is a static field to illustrate observation. In large suites with parallel execution, static mutable state can cause contention. For production-grade tests, consider:

- An independent recorder instance supplied via test configuration.
- Not running tests sharing the same static recorder in parallel.
- Resetting state at test start and measuring precisely after context close.
- Using a unique resource owner instead of a single recorder shared across all contexts.

The example picks `AtomicInteger` solely to keep the runnable file simple and independent of a DB.

### 8.2. What is NOT guaranteed to be cleaned up?

Dangerous case:

```java
@Bean(destroyMethod = "close")
SocketClient socketClient() throws Exception {
    SocketClient client = new SocketClient();
    client.connect(); // What if it fails before return?
    return client;
}
```

This is an **illustrative snippet**, requiring a `SocketClient` class with `connect/close`. If `connect()` allocated resources and then threw an exception, the bean was never handed over to Spring. **Never rely on `destroyMethod` of an unreturned bean** to clean up local resources.

In real factories, catch failures at the allocation point and close resources before rethrowing; use `try-with-resources` or `try/catch` with appropriate suppressed exceptions.

### 8.3. Prototype and lazy beans

- Prototype beans do not have Spring-managed destruction like singletons.
- Lazy beans never instantiated have no destructor instance to invoke.
- `ApplicationContextRunner` tests a context with the exact beans you registered; if it differs from production config, do not extrapolate cleanup results to every real resource.
- `@PostConstruct` throwing before a bean completes initialization may mean that instance's destructor was never registered.
- With `SmartLifecycle`, stopping by phase when refresh fails very early is not equivalent to a complete normal shutdown.

## 9. Testing ApplicationRunner failures: requires real SpringApplication

Look at bean `demoRunner` in the section 5 application. It is **created during refresh**, yet `run(ApplicationArguments)` is called by Boot only in the post-refresh steps.

### 9.1. Why can an ApplicationContextRunner test pass even when the runner will throw?

Suppose the context runner registers an `ApplicationRunner`:

```java
@Bean
ApplicationRunner alwaysFailingRunner() {
    return arguments -> {
        throw new IllegalStateException("runner failed");
    };
}
```

This is a snippet inside `@Configuration`, requiring `Bean` and `ApplicationRunner` imports.

`ApplicationContextRunner` can refresh the context **successfully**, because it does not auto-invoke this bean's `run(...)` callback. The test:

```java
assertThat(context).hasNotFailed();
```

says nothing about whether calling the runner during `SpringApplication.run(...)` throws an error.

### 9.2. Integration testing path

To validate runner errors:

- Launch the app via `SpringApplication.run(StartupCheckApplication.class, args)` in an appropriate test harness, or
- Run `java -jar ... --demo.runner.fail=true` as a separate process.

When Boot startup actually invokes `demoRunner`, it throws `StartupPolicyException(RUNNER_BLOCKED)`. The custom `FailureAnalyzer` must return the exact action `demo.runner.fail=false`.

**Recommendation:** a process test is the simplest, most reliable way to verify the failure analysis report, `spring.factories` registration, and exit code outside the test JVM simultaneously.

### 9.3. ApplicationStartedEvent vs. ApplicationReadyEvent

In Boot 3.3's cycle:

```text
context refresh
       |
       v
ApplicationStartedEvent
       |
       v
ApplicationRunner / CommandLineRunner
       |
       +-- error → failure path
       |
       v
ApplicationReadyEvent (only if runners complete)
```

Thus when a runner throws, an `ApplicationStartedEvent` listener may have already executed, while `ApplicationReadyEvent` is not emitted on the successful startup path.

To test readiness, verify the proper event/state rather than relying on a `"Started ..."` log from the pre-runner milestone.

## 10. Process-level test: verifying FailureAnalyzer registration and exit codes

This is what unit tests and `ApplicationContextRunner` **cannot substitute for**: running Boot as a standalone Java process.

### 10.1. Build the JAR

```bash
./gradlew clean test bootJar
```

With `settings.gradle` and `version=1.0.0` in the example, the expected JAR is:

```text
build/libs/startup-check-demo-1.0.0.jar
```

If you change the project name or archive settings, check the actual JAR name instead of guessing.

### 10.2. Refresh failure: running the JAR directly

On Linux/macOS or a POSIX shell, run:

```bash
set +e
java -jar build/libs/startup-check-demo-1.0.0.jar \
  --demo.bootstrap.mode=invalid \
  > startup-refresh-fail.log 2>&1
status=$?
set -e

printf 'exit=%s\n' "$status"
test "$status" -ne 0
grep -F 'The demonstration bootstrap mode is invalid.' \
  startup-refresh-fail.log
grep -F 'Set demo.bootstrap.mode=ok and restart.' \
  startup-refresh-fail.log
```

This runs in a POSIX shell; `set +e` prevents the intentionally failing command from aborting the script if `errexit` is enabled externally, and `status=$?` must be captured **immediately after the Java process**. `grep` checks two meaningful strings rather than diffing the entire log file.

Expectations:

- Java process exits non-zero.
- Log contains the custom analyzer's description and action.
- No `runner.ok=ok` marker appears.
- No need to assert exact stack trace text, ANSI codes, or timestamps.

**Never claim the exit code must be a specific number** merely because a `FailureAnalyzer` is registered. Analyzers aid diagnostics; exit status depends on exception/failure handling and the launcher. If an app needs fixed codes like 2/23/64, design them explicitly with `ExitCodeGenerator`/policy and process tests.

### 10.3. Runner failure: running the JAR separately

```bash
set +e
java -jar build/libs/startup-check-demo-1.0.0.jar \
  --demo.runner.fail=true \
  > startup-runner-fail.log 2>&1
status=$?
set -e

printf 'exit=%s\n' "$status"
test "$status" -ne 0
grep -F 'The demonstration startup runner was blocked.' \
  startup-runner-fail.log
grep -F 'Set demo.runner.fail=false and restart.' \
  startup-runner-fail.log
```

This exercises **two genuinely distinct integration layers**: one failure during refresh, and one post-refresh failure inside the runner. Both prove the analyzer is loaded and the reporter is called on the corresponding startup failure path.

### 10.4. Success path

```bash
java -jar build/libs/startup-check-demo-1.0.0.jar \
  --demo.bootstrap.mode=ok \
  --demo.runner.fail=false

printf 'exit=%s\n' "$?"
```

Primary marker:

```text
runner.ok=ok
```

A simple non-web CLI without background tasks keeping the JVM alive that finishes cleanly normally exits with status 0. If the process hangs, check background executors/daemon policies before blaming the analyzer.

### 10.5. PowerShell on Windows

```powershell
java -jar build/libs/startup-check-demo-1.0.0.jar --demo.runner.fail=true
$exitCode = $LASTEXITCODE
Write-Output ("exit=" + $exitCode)
```

In PowerShell, use `$LASTEXITCODE` to read `java`'s exit status. Do not treat `$?` as always holding the raw native process exit code.

### 10.6. Why not just use ./gradlew bootRun?

Gradle may report the exit code of the **task/wrapper**, not necessarily the actual Java process exit code. Furthermore, Gradle/IDEs may inject logs or forward exceptions under their own rules.

To prove which status the Java/JVM process reports, **run the JAR directly** or spawn a child process and inspect its exit value. This test layer also avoids JUnit tests calling `System.exit` and killing the entire runner.

## 11. Can process tests be automated with ProcessBuilder?

Yes. In an isolated integration test, `ProcessBuilder` lets you launch a child Java process with fixed arguments and await termination with a timeout.

Illustrative Java 17 sample:

```java
import java.io.File;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

public class ChildProcessProbe {

    public static void main(String[] args) throws Exception {
        String javaBinary = Path.of(
                System.getProperty("java.home"),
                "bin",
                isWindows() ? "java.exe" : "java"
        ).toString();

        Process process = new ProcessBuilder(
                javaBinary,
                "-jar",
                "build/libs/startup-check-demo-1.0.0.jar",
                "--demo.bootstrap.mode=invalid")
                .redirectErrorStream(true)
                .redirectOutput(new File("probe-output.log"))
                .start();

        try {
            if (!process.waitFor(20, TimeUnit.SECONDS)) {
                process.destroyForcibly();
                process.waitFor();
                throw new IllegalStateException(
                        "Child process exceeded timeout.");
            }

            int exit = process.exitValue();
            System.out.println("childFailed=" + (exit != 0));
        } finally {
            if (process.isAlive()) {
                process.destroyForcibly();
            }
        }
    }

    private static boolean isWindows() {
        return System.getProperty("os.name")
                .toLowerCase()
                .contains("win");
    }
}
```

This is standalone Java 17, requiring the built JAR at the specified path and a writable output file. It can be compiled with:

```bash
javac ChildProcessProbe.java
java ChildProcessProbe
```

If the JAR exists and startup fails as designed, the probe's stdout prints:

```text
childFailed=true
```

File `probe-output.log` holds output from the child Java process, not the probe's stdout. Before running tests, verify the JAR and working directory under CI; avoid relying on a relative path that a JUnit runner might change.

### 11.1. Production-grade improvements for ProcessBuilder tests

- Use a separate temporary directory/log file per test.
- Never overwrite the same `probe-output.log` when tests run in parallel.
- Set a timeout generous enough for slow CI yet never infinite.
- Ensure the child process tree is cleaned up; `destroyForcibly()` does not automatically kill every grandchild process.
- Avoid deadlocks from full stdout/stderr pipes: redirect to a file or read streams concurrently.
- Use the Java binary from the target runtime; Gradle toolchains and the JUnit JVM may differ.
- Execute only an artifact already built prior to the integration test.
- Verify exit codes and report contents using stable markers.
- Never pass real sensitive data in test args or logs.

## 12. Avoiding @SpringBootTest when the context is expected to fail immediately

An error-prone approach:

```java
@SpringBootTest(properties = "demo.bootstrap.mode=invalid")
class BrokenStartupTest {

    @Test
    void testFailure() {
        // This method may NEVER be executed.
    }
}
```

This is a **counter-example**.

`@SpringBootTest` asks the Spring TestContext Framework to load the application context **before running the test method**. If the context fails, JUnit reports a test setup failure instead of giving the test method a chance to assert the cause.

In Boot 3.3, avoid using `@SpringBootTest` as the default way to "expect the application context to fail to build" if you need to inspect and assert the exception from a failed context.

**Choose `ApplicationContextRunner`** when testing bean refresh failures. Choose **process-level tests** or a harness calling `SpringApplication.run` in a controlled scope when testing full bootstrapping.

### 12.1. What is @SpringBootTest suited for?

It is suited for confirming **the application starts successfully** with expected configuration, auto-configuration, and runnable beans; it is also useful for web integration tests. When the test's goal is **intentional startup failure**, the context runner returns the failure object as inspectable data rather than turning a setup failure into a framework error.

## 13. How FailureAnalyzer unit tests differ from reporter tests

Three distinct layers:

| Layer | How to test | What it proves |
| --- | --- | --- |
| Analyzer logic | `new Analyzer().analyze(exception)` | Mapping exception → analysis |
| Reporter formatting | `LoggingFailureAnalysisReporter.report(analysis)` or custom reporter | Analysis → output/log |
| Boot wiring/integration | `java -jar app.jar` and capture logs | Registration + exception trigger + analyzer + reporter |

With only an analyzer unit test, `spring.factories` could have a package typo and **production would never show the report**.

With only log capture, analyzer logic could be wrong while the test passes because a random stack trace happened to contain a string similar to the description. Therefore end-to-end tests should check for the **distinct action provided by the analyzer**, and logic tests should assert the exact `FailureAnalysis.getAction()`.

### 13.1. Testing a custom FailureAnalysisReporter

`FailureAnalysisReporter` has one method:

```java
void report(FailureAnalysis analysis);
```

A production reporter might write structured logs or ship data to monitoring. Reporter unit tests should:

1. Construct a fake `FailureAnalysis`, without real startup.
2. Invoke `report`.
3. Verify the payload is sanitized.
4. Make no real network calls in unit tests.
5. Require no refreshed context.
6. If multiple reporters are used, verify actual registration via an integration test.

**Registration note:** The Reporter SPI also has its own registration; do not confuse `FailureAnalyzer` with `FailureAnalysisReporter` merely because both live in package `org.springframework.boot.diagnostics`.

### 13.2. Common mistake: asserting the whole banner/ANSI block

Avoid:

```java
assertThat(output).isEqualTo("...full 200-line startup log...");
```

Instead assert meaningful markers:

```java
assertThat(output)
        .contains("APPLICATION FAILED TO START")
        .contains("The demonstration bootstrap mode is invalid.")
        .contains("Set demo.bootstrap.mode=ok and restart.");
```

This is a **snippet** using a captured string variable `output`. It does not compile standalone without defining `output`, yet illustrates writing assertions resilient to formatting changes.

## 14. Testing when an analyzer does not recognize an error

An analyzer may intentionally return null:

```java
FailureAnalysis result =
        analyzer.analyze(new IllegalStateException("not mine"));
```

Returning `null` is valid behavior. When running real Boot, another analyzer can still recognize the error; if no analyzer handles it, Boot still has its fallback mechanism to report the startup exception.

Do not create a catch-all fallback analyzer "handling every `Throwable`" with an overly generic message unless you have an explicit policy. If a fallback runs ahead of a specialized analyzer, it can hide a more helpful report.

### 14.1. Testing priority when multiple analyzers exist

Spring Boot loads multiple analyzers from the classpath. When multiple candidates match, order may be affected by `Ordered`/`@Order` and factory ordering. If an exception can be handled by several analyzers:

- Define which analyzer **must** handle it.
- Write unit tests for competing exception types.
- Declare explicit ordering where APIs and loading mechanisms support it.
- Verify integration output under a configuration with all analyzers present.
- Avoid relying on accidental JAR ordering on the classpath.

**Do not design systems relying on accidental ordering** inside `spring.factories` as a contract across separate libraries.

## 15. Boot errors with built-in FailureAnalyzers: how to structure tests

Spring Boot ships analyzers for many common errors, such as:

- Occupied web server port.
- Missing bean or multiple matching candidates.
- Binding/validation errors on configuration properties.
- Certain auto-configuration and classpath incompatibilities.
- Disallowed bean definition overriding.

Do not write custom analyzers for errors Boot already reports properly. Still, understand the **testing layer**.

### 15.1. Missing bean

A bean depends on an interface with no implementation:

```java
@Configuration(proxyBeanMethods = false)
class MissingDependencyConfig {

    @Bean
    ServiceA serviceA(MissingClient client) {
        return new ServiceA(client);
    }
}
```

This snippet requires types `ServiceA` and `MissingClient` to be defined, along with `Configuration` and `Bean` imports.

A context runner test can assert the missing-bean failure/cause. To test Boot's default analyzer output, run full Boot/process with real config; **the context runner does not automatically turn errors into `APPLICATION FAILED TO START` startup reports**.

### 15.2. Port already in use

This is an easy scenario for writing **flaky** tests:

```text
server.port=8080
expect startup failure because 8080 is busy
```

On a developer machine, port 8080 may be free; on CI, another service may hold it. Never write tests depending on uncontrolled external state.

If testing port conflicts is mandatory:

- Proactively bind a port with a test-owned resource using OS-appropriate mechanisms.
- Ensure the server tries binding that exact held port/socket.
- Enforce timeouts and clean up the port resource in `finally`.
- Never use a common fixed port if tests run in parallel.
- Do not assert only the embedded server message without verifying the failure cause.
- Consider testing the bind-error analyzer independently if the goal is solely report formatting.

For most applications, a deterministic custom analyzer test like the demo is far more valuable than an uncontrolled port-grabbing test.

### 15.3. Binding validation failure

With `@ConfigurationProperties` and Jakarta Bean Validation:

- Register the properties bean (`@ConfigurationPropertiesScan` / `@EnableConfigurationProperties`).
- Include a validation provider when needed, typically via `spring-boot-starter-validation`.
- Supply invalid properties via `ApplicationContextRunner.withPropertyValues`.
- Inspect the root cause or appropriate cause chain; sometimes the error is a wrapped `BindValidationException`.
- Do not expect `@NotBlank` to fail automatically without a proper provider/binding.
- When testing Boot's specific report, add a process/integration test.

## 16. Testing ApplicationFailedEvent

Spring Boot emits `ApplicationFailedEvent` when the `SpringApplication` startup path fails. The event can carry:

- The startup exception.
- The application context, **which may be null if the failure occurred too early**.

A Spring bean listener is not guaranteed to exist when an error happens before context creation; to observe early-stage errors, register the listener directly before `run`.

### 16.1. Early listener

```java
SpringApplication application =
        new SpringApplication(StartupCheckApplication.class);

application.addListeners(
        (ApplicationListener<ApplicationFailedEvent>) event -> {
            System.out.println("failed="
                    + event.getException().getClass().getSimpleName());
        });

application.run(args);
```

This snippet **lives inside a method receiving `args`**, requiring imports for `SpringApplication`, `ApplicationListener`, `ApplicationFailedEvent`, and the demo's application class. It illustrates listener registration, not a requirement to modify `main` of the running project.

It does not set exit codes or clean up resources automatically. In unit/integration tests, avoid having listeners call repositories or `event.getApplicationContext().getBean(...)` without accounting for a context that may not exist or has failed.

### 16.2. Testing events vs. testing analysis

- **Event test:** was the exception delivered to the listener at the right time?
- **Analyzer test:** was the exception converted into helpful description/action?
- **Cleanup test:** were already-owned resources closed?
- **Process test:** did the process report failure and a valid exit status?

A passing event test does not prove the analyzer is registered or the reporter printed output.

### 16.3. Events may fire before context cleanup completes

`ApplicationFailedEvent` does not mean all `@PreDestroy` callbacks have run. Inside failure handling, events, logging, and context closing have distinct milestones. If a test must verify resources were closed, record directly in the resource owner or inspect state from the process/test harness after `run` fails, rather than inferring from the failure event.

## 17. Proving FailureAnalyzer must never mask errors

Suppose the analyzer recognizes a mode error:

```java
FailureAnalysis analysis =
        analyzer.analyze(new StartupPolicyException(
                StartupPolicyException.Problem.INVALID_MODE));
```

Even when `analysis` is non-null, the application **still fails** as the exception continues propagating during startup.

That is a sound contract:

```text
FailureAnalyzer: "I help explain the error and how to fix it."
FailureReporter: "I present the analysis."
SpringApplication: "A bootstrap error is still an error; must handle failure."
Process launcher: "I report exit status to the OS."
```

Never build an analyzer that calls `System.exit`, repairs beans, retries HTTP requests, or resets a database inside `analyze`. An analyzer is a **diagnostic step** that must operate safely even when the system is in a broken state.

## 18. Exit codes: relationship with FailureAnalyzer

Some people assume a custom `FailureAnalyzer` can turn a minor error into exit 0 or assign code 42. That is false.

Spring Boot provides `ExitCodeGenerator` and `ExitCodeExceptionMapper` for exit-code policies. You can use:

```java
public final class InvalidStartupException
        extends RuntimeException implements ExitCodeGenerator {

    @Override
    public int getExitCode() {
        return 42;
    }
}
```

This is a Java class snippet requiring importing `org.springframework.boot.ExitCodeGenerator`. It is not in the demo project and is not a required part of `StartupPolicyFailureAnalyzer`.

When startup fails, Boot has a path to determine exit codes from exceptions or mappers if configured; to know precisely what the **process** returns, test with `java -jar`.

### 18.1. Never use System.exit in JUnit tests

Calling `System.exit(42)` directly inside the test process can kill the JUnit/Gradle worker itself. That does not properly verify cleanup or registration.

Alternatives:

- Unit test `getExitCode()` on an exception.
- Boot integration test without calling `System.exit` inside the JUnit process.
- Process-level test with `ProcessBuilder` or `java -jar` to observe the exit value.

### 18.2. When is SpringApplication.exit(context) used?

`SpringApplication.exit(context)` applies when `SpringApplication.run(...)` **has already returned a context successfully**, and the application wants to compute an exit code/close the context intentionally.

If `run` throws an exception during refresh/runners, the returned context variable **does not exist** at the caller; you cannot simply call `SpringApplication.exit(context)` after a failed call. Never create a new context just to call exit, as it may allocate extra resources and trigger new errors.

## 19. Capturing logs safely

Spring Boot Test provides `OutputCaptureExtension` to capture stdout/stderr in appropriate tests.

Illustrative **snippet** in a JUnit test:

```java
@ExtendWith(OutputCaptureExtension.class)
class OutputCaptureExample {

    @Test
    void capturesText(CapturedOutput output) {
        System.out.println("marker");
        assertThat(output.getOut()).contains("marker");
    }
}
```

This requires importing `ExtendWith`, `OutputCaptureExtension`, `CapturedOutput`, `Test`, `assertThat`, placed in a test source file. It only proves output capture, **not the full `SpringApplication` failure path**.

### 19.1. Risks when asserting on logging

- Log formats vary across logging backends/profiles/versions.
- Stack traces have varying classes and line numbers.
- ANSI sequences may be toggled depending on the terminal.
- Some async loggers write after the assertion executes.
- Changing `logging.level` can alter reporter logs.
- During parallel test runs, stdout/stderr are virtually global resources.

To test the final `FailureAnalysisReporter`, a process test redirecting to a dedicated file is usually clearer and avoids polluting the test JVM's logging.

### 19.2. Preventing fake secrets from leaking into reports

Test with a dummy value, such as `DUMMY_SECRET_987`, never a real credential. If an exception message contains raw config values, the analyzer might accidentally echo them.

In the demo's custom analyzer, description/action **never insert the actual mode value** into the report. You can add a test assertion:

```java
assertThat(analysis.getDescription())
        .doesNotContain("DUMMY_SECRET_987");
assertThat(analysis.getAction())
        .doesNotContain("DUMMY_SECRET_987");
```

This is an additional snippet inside a test method with an appropriate `analysis`. Output tests can catch leaks in the analyzer, yet you must still check stack traces, exception messages, launcher logs, and CI logs.

## 20. Debugging when your FailureAnalyzer does not appear

When the application fails yet shows only a generic stack trace:

1. **Verify the actual exception**: is the error of a type your analyzer handles? Is it in the cause chain?
2. **Unit test the analyzer**: call `analyze(failure)` to see if it returns `FailureAnalysis` or `null`.
3. **Check the registration file location**: must be `src/main/resources/META-INF/spring.factories`, not a similar filename.
4. **Check the key**: must be exactly `org.springframework.boot.diagnostics.FailureAnalyzer`.
5. **Check the class name**: exact package-qualified class name, instantiable.
6. **Inspect the JAR artifact**: was `META-INF/spring.factories` packaged into the build output?
7. **Check the test launcher**: are you running `java -jar`, `bootRun`, IDE, or a context runner? Different paths have different coverage.
8. **Check reporter/logging**: the analysis may be created while output doesn't appear as expected.
9. **Check other analyzers**: did another analyzer match the error first and claim the report path?
10. **Check version**: ensure APIs/registration match the Spring Boot version you run, without applying newer-version guides unverified.
11. **Check safe error-input handling**: the analyzer must not throw a second exception while processing.
12. **Compare process tests before/after fixes** rather than merely adding debug logs inside the analyzer.

### 20.1. Checking spring.factories inside the JAR

With a JDK providing `jar`:

```bash
jar tf build/libs/startup-check-demo-1.0.0.jar \
  | grep 'spring.factories'
```

Because this is a **Spring Boot executable JAR**, application resources normally live inside `BOOT-INF/classes/META-INF/spring.factories`. `jar tf` only lists archive entries; it does not prove the analyzer instantiates cleanly or prints a report.

Only combining artifact inspection with the `--demo.bootstrap.mode=invalid` process test proves complete wiring.

### 20.2. Meaningful diagnostic sequence

```text
Analyzer unit test PASS?
        |
        +-- NO -> fix analyzer logic / cause recognition
        |
        +-- YES
             |
             v
File spring.factories present in runtime artifact?
        |
        +-- NO -> fix packaging/registration
        |
        +-- YES
             |
             v
java -jar failure scenario produces report/action?
        |
        +-- NO -> check analyzer order, logging, failure stage
        |
        +-- YES -> FailureAnalyzer/Reporter wiring confirmed
```

This is a pragmatic debugging flow: narrowing down the cause step by step instead of modifying multiple configuration layers at once.

## 21. Testing multiple failures sharing an exception class but different causes

An `IllegalStateException` can represent countless scenarios. Writing an analyzer that catches every `IllegalStateException` and advises "add a database URL" would be wrong when the actual cause is a job runner.

In the demo, `StartupPolicyException` carries a `Problem` enum. That is a way to preserve **structured business context** without embedding raw secrets in messages.

Another analyzer might inspect:

- Exception types in the cause chain.
- Domain-managed error codes.
- Non-sensitive property names.
- Available and reliable metadata.
- Environment conditions when guaranteed to be prepared.

Avoid checking messages solely via `contains("password")`: changing log language/formatting breaks the analyzer, and parsing raw messages can lead to leaks.

## 22. Caveats with @ConfigurationProperties validation

An application using:

```java
@ConfigurationProperties(prefix = "demo.client")
@Validated
public record ClientProperties(
        @NotBlank String endpoint) {
}
```

is a **snippet**, requiring imports for `ConfigurationProperties`, `Validated`, `jakarta.validation.constraints.NotBlank`, and registering the properties bean/provider properly. It is simply a separate example from the complete project.

When configuration lacks `endpoint`:

- The context can fail during binding/validation.
- The outermost exception is usually not `ConstraintViolationException` itself.
- Boot provides built-in analyzers for several bind/validation cases.
- Context runner tests must add the configuration and validation provider.
- Tests should assert the root/cause and appropriate property path rather than pinning a 200-line full error message.

**Important:** missing `spring-boot-starter-validation` in the project can prevent validation from running as expected. Tests must match production configuration for required validation behavior.

### 22.1. @Value is not validation annotation

The main demo uses `@Value("${demo.bootstrap.mode:ok}")` and manual validation inside `@Bean` to avoid adding `starter-validation`.

If a project uses `@ConfigurationProperties` and real Bean Validation, test that exact binding/validation mechanism rather than extrapolating from the `@Value` demo.

## 23. Limitations of test harnesses

| Tool | Strength | Cannot prove on its own |
| --- | --- | --- |
| JUnit unit test | Fast, tests analyzer/validator logic | Spring Boot registration, context cleanup |
| `ApplicationContextRunner` | Builds small context, asserts refresh failure | Runner invocation, full `SpringApplication` report/exit |
| `@SpringBootTest` | Full context success, integration | Awkward for asserting startup failures because test setup fails |
| `SpringApplication.run` in test JVM | Tests real callbacks/events/runners | Process exit status without spawning a child process |
| `OutputCaptureExtension` | Asserts stdout/stderr in the same JVM | Does not guarantee async logger behavior or exit codes |
| `ProcessBuilder` | Exit status, Java process logs, wiring | Slower tests; must manage timeouts/working directory |
| Manual `java -jar` | Reproduces production-like startup | Does not re-run in CI unless scripted |

An effective test suite typically consists of **many fast unit/context tests** and **a few targeted integration/process tests**, without launching a Spring Boot process hundreds of times just to test each `if` branch.

## 24. Common testing mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `@SpringBootTest` fails before entering `@Test` | Context errored during test setup | Use context runner for expected failures |
| Context runner PASSES even though runner will throw | Context runner does not call `ApplicationRunner` | Use `SpringApplication.run`/process tests |
| Unit analyzer passes yet runtime prints no description | Missing/wrong `META-INF/spring.factories` | Check artifact + process tests |
| Analyzer always returns one generic report | Doesn't classify exceptions accurately | Return `null` when unsupported; test negative paths |
| Test asserts exact volatile `BeanCreationException` message | Wrapper and source locations vary | Assert root cause/cause chain |
| `OutputCapture` misses the report | Logger config/async/capture timing differs | Process test redirecting output; stable markers |
| Test kills the entire JVM | Calling `System.exit` from unit tests | Run app as a child process |
| Exit code from Gradle is 1 despite app policy 42 | Wrapper returns its own status | Run `java -jar` directly |
| Port-in-use test passes sometimes and fails others | Port depends on external machine state | Control socket resource or use deterministic errors |
| Resource closed zero times | Bean failed before Spring finished creating it; no destructor | Clean up partial initialization explicitly |
| Cleanup test occasionally sees count=2 | Static recorder/context cache or parallel tests | Isolate state; avoid shared contexts |
| Startup failure test breaks other tests | Sharing JVM with global properties/listeners/threads | Use process isolation and cleanup |
| Analyzer suggests wrong action across multiple reasons | Fails to inspect domain error codes | Use enums/error types and unit test every branch |
| Debug flags leak secrets | Condition/config report too verbose | Use dummy data; enforce log sanitization |
| Test uses `@Lazy` so broken bean isn't created | Lazy init defers validation | Force creating target bean or disable lazy in harness |
| Bean excluded by `@Conditional*` | Test omits required property/profile | Add `withPropertyValues` or user config |
| Test mocks hide missing dependency errors | Mock registered instead of missing bean | Test with production-equivalent candidates/conditions |
| Reporter registered twice | Duplicate metadata or registration | Inspect classpath and reporter config |
| CI hangs on failure test | Child process blocks or stdout pipe fills | Redirect streams, enforce timeout, destroy child process |

## 25. Stage-by-stage testing strategy for startup failures

### 25.1. Failures before ApplicationContext

For example, the Config Data loader fails to read required config. The context may not exist yet; a regular `@Component` observer is unlikely to be registered.

Test layers:

- Process test with explicit configuration, independent of real environment variables.
- Early listener registered via `SpringApplication.addListeners` if measuring `ApplicationFailedEvent`.
- Analyzer decoupled from the container when recognizing ultra-early errors.
- Do not use context runner to infer all Config Data bootstrap behavior.

### 25.2. Failures during refresh

For example, a bean constructor throws an exception or validation fails.

Test layers:

- `ApplicationContextRunner` for minimal configuration.
- Assert the exact root cause.
- Verify already-created dependencies are cleaned up.
- Unit test the analyzer for the relevant exception.
- One process test if final reporter output must be confirmed.

### 25.3. Failures inside runners

For example, `ApplicationRunner` throws because startup data checks fail.

Test layers:

- Unit test runner logic with fake `ApplicationArguments` if possible.
- `SpringApplication.run` integration to confirm the runner actually executes.
- Process test to observe the failure report and non-zero status.
- Verify `ApplicationReadyEvent` is not emitted on the success path.

### 25.4. Failures inside @PostConstruct

If `@PostConstruct` creates a resource and then throws, context failure does not guarantee the failing bean's own destructor was registered. Test cleanup directly inside the method/constructor.

### 25.5. Failures after ready

Request/job failures after the process is ready are runtime failures, not handled by startup `FailureAnalyzer`s. Test exception handling, retries/transactions, readiness/liveness, and shutdown policies separately; do not mix them with startup testing.

## 26. Writing acceptance criteria for a startup failure

Instead of "when config is wrong, the app fails", define testable criteria:

**Example requirement:** when `demo.bootstrap.mode` is not `ok`:

1. Context fails to refresh.
2. Root cause is `StartupPolicyException` with problem `INVALID_MODE`.
3. Business runner does not execute.
4. Analyzer produces a description explaining the invalid mode.
5. Action instructs `demo.bootstrap.mode=ok`.
6. Reporter prints the analysis when running the JAR with Boot.
7. Process returns a non-zero exit status.
8. Untrusted mode value is never printed in the report.
9. Fully created resource beans are cleaned up per lifecycle.
10. Tests do not depend on network ports, DBs, or clocks.

Once acceptance criteria exist, test layers split cleanly:

- 1, 2 → context runner.
- 4, 5, 8 → unit analyzer.
- 3, 6, 7 → process-level.
- 9 → context cleanup test.
- 10 → cross-cutting test design rule.

Do not force a single test to verify every criterion.

## 27. QA checklist before merging startup diagnostics changes

- [ ] Exception represents the domain failure clearly and contains no secrets.
- [ ] Unit tests cover every error category recognized by the analyzer.
- [ ] Test verifies unrelated exceptions return `null`.
- [ ] Description/action are specific, helpful, and stable.
- [ ] Analyzer creates no side effects and requires no beans that may not exist.
- [ ] Custom analyzer is declared in `META-INF/spring.factories`.
- [ ] Analyzer class is instantiable at runtime.
- [ ] Registration file is present in the output JAR.
- [ ] Context failures are tested with `ApplicationContextRunner`.
- [ ] Root cause is asserted rather than full exception stack traces.
- [ ] Runner failures are tested with a real `SpringApplication`.
- [ ] Do not use `@SpringBootTest` expecting context load failure before entering the test method.
- [ ] Cleanup is tested for singletons that completed initialization.
- [ ] Cleanup of partially opened resources in constructors/factories is tested if applicable.
- [ ] Never call `System.exit` inside the JUnit process.
- [ ] Process-level tests cover reports and exit statuses.
- [ ] Child processes have timeouts, stream redirection, and cleanup.
- [ ] No reliance on an external fixed port.
- [ ] Logging assertions rely on markers rather than timestamps/ANSI.
- [ ] Success path is tested so analyzers/policies don't break valid startups.
- [ ] Post-`ApplicationRunner` behavior and readiness milestones are verified.
- [ ] Consider whether lazy initialization causes tests to skip broken beans.
- [ ] Do not confuse `FailureAnalyzer` with `ExitCodeGenerator` or `FailureAnalysisReporter`.
- [ ] Troubleshooting docs never instruct passing secrets via CLI.
- [ ] Tests leave no leftover files, processes, or mock resources behind after completion.

## 28. Practice exercises with answers

### Exercise 1: varying actions by error

Modify `StartupPolicyFailureAnalyzer` so `RUNNER_BLOCKED` suggests a different action, such as checking a specific feature flag. Write a unit test asserting the exact action string and ensuring `INVALID_MODE` is unaffected.

**Key answer:** write two separate assertions per `Problem`; do not classify by parsing exception messages.

### Exercise 2: deleting spring.factories

Delete the registration file (in a copy of the demo project) and run:

```bash
./gradlew test bootJar
java -jar build/libs/startup-check-demo-1.0.0.jar \
  --demo.bootstrap.mode=invalid
```

Why do analyzer unit tests still pass while the custom `Description/Action` report disappears?

**Answer:** unit tests instantiate the analyzer directly, whereas Boot can only auto-load custom analyzers when runtime registration is valid. Startup still fails, yet reporting falls back to generic failure output.

### Exercise 3: runner failure with context runner

Create an `ApplicationRunner` bean that always throws, pass it into `ApplicationContextRunner`, and assert `context.hasNotFailed()`. Explain the result.

**Answer:** context runner does not auto-invoke `ApplicationRunner.run(...)`; runners are invoked only by `SpringApplication` during startup.

### Exercise 4: checking cleanup

In `ContextCleanupTests`, change `@Bean(destroyMethod = "close")` to `@Bean(destroyMethod = "")` and observe behavior when the resource implements `AutoCloseable`. Why can the cleanup test outcome change?

**Answer:** disabling destroy method inference/registration prevents Spring from calling that method automatically as before. This is an experiment only; never use it as a production pattern.

### Exercise 5: adding a wrapper layer

Wrap `StartupPolicyException` in two exception layers before calling the analyzer:

```java
Throwable failure = new IllegalStateException(
        "outer",
        new RuntimeException(
                "inner",
                new StartupPolicyException(
                        StartupPolicyException.Problem.INVALID_MODE)));
```

Does `AbstractFailureAnalyzer` still recognize the problem?

**Answer:** yes, because it searches the cause chain by type; unit tests should confirm analysis is non-null and the action matches.

### Exercise 6: non-flaky port conflict test

Write a test where the web server fails on an occupied port **without hardcoding 8080**. Design test-owned socket holding with timeouts/cleanup and verify the port is actually occupied before bootstrap.

**Key answer:** port resource ownership must reside in the test; never assume CI machines have another process occupying a port.

### Exercise 7: testing exit codes

Add an exception implementing `ExitCodeGenerator` returning 29, then run the JAR as a child process. Why is asserting `getExitCode()==29` in a unit test insufficient?

**Answer:** unit tests only verify the method; process status also depends on failure handlers/launchers and operations in `main`.

### Exercise 8: testing when cleanup itself fails

In a separate test, make a resource's `close()` throw an exception while another bean fails startup. Verify whether the root cause remains the bootstrap failure and how cleanup failures are recorded. Do not force tests to assert a fixed stack trace log when the framework may wrap exceptions in multiple ways.

### Exercise 9: testing with lazy initialization enabled

Enable `spring.main.lazy-initialization=true` in the demo process. Why might `StartupMarker` remain uncreated during refresh in a configuration where no bean needs it? What happens if the runner directly depends on the marker?

**Answer:** lazy initialization can defer beans; however, runners are required by Boot and runner injection can trigger marker creation before startup completes. You must test the real runtime stage rather than mechanically applying context runner expectations.

### Exercise 10: auditing secrets in failure reports

Pass a dummy value like `DUMMY_SECRET_987` as an invalid mode, run the JAR, and verify analysis description/action **do not echo the input**. If stack traces/framework logs still contain the value, inspect the exception message origin and logging formatters rather than just tweaking an analyzer assertion.

## 29. Misconceptions to eliminate

**Misconception 1:** "`FailureAnalyzer` makes the application start successfully if it handles the error."

False. It builds an analysis and suggested action; it never swallows exceptions.

**Misconception 2:** "`@Component` is enough for a custom analyzer to always handle early errors."

False per Spring Boot 3.3 registration guidance: `META-INF/spring.factories` is required to load analyzers into bootstrap reporting.

**Misconception 3:** "Testing the analyzer directly also tests the console report."

False. Analyzer unit tests do not verify runtime registration or the reporter.

**Misconception 4:** "`ApplicationContextRunner` can test every error of `SpringApplication.run`."

False. Context runner does not call runners and does not reproduce the full Boot application lifecycle.

**Misconception 5:** "If a `@SpringBootTest` fails before entering the test method, we have a good expected-failure test."

Not really. Test setup failure is not an intentional assertion on cause and action.

**Misconception 6:** "Merely grepping `APPLICATION FAILED TO START` completes integration testing."

Insufficient. Verify specific description/action, exit status, and error origin.

**Misconception 7:** "On startup error, every resource is guaranteed to receive `@PreDestroy`."

False. Beans that never finished construction or non-Spring resources may not be managed.

**Misconception 8:** "A fixed port number will always be occupied on the test machine."

False. Tests become flaky if they depend on OS state outside the test's control.

**Misconception 9:** "`ExitCodeGenerator` lives inside `FailureAnalyzer`."

False. Those are two separate mechanisms: diagnostics and exit-code reporting.

**Misconception 10:** "Printing a full stack trace is enough; no action is needed."

False for operational experience: a report with concrete guidance usually speeds up config fixes, provided sensitive data is not exposed.

## 30. Summary

A strong startup-failure testing strategy in Spring Boot 3.3 includes:

1. **Use `ApplicationContextRunner`** to test errors occurring during context creation/refresh. Assert context failure and root cause, and check cleanup of created singletons.
2. **Use unit tests for `FailureAnalyzer`**: errors are recognized, `FailureAnalysis.getDescription()` / `getAction()` are accurate, `getCause()` is reasonable, and unrelated errors return `null`.
3. **Register analyzers via `META-INF/spring.factories`**, rather than relying solely on component scanning.
4. **Run the real JAR** to confirm Boot loads the analyzer, the reporter prints the action, and the process returns non-zero on startup failure.
5. **Test runner failures with a real `SpringApplication`**: context runner does not call `ApplicationRunner`.
6. **Keep tests stable**: avoid fixed ports, logging layouts, startup log ordering, or raw exception messages.
7. **Protect the test JVM**: never call `System.exit` directly in JUnit; use child processes to observe exit statuses.
8. **Separate cleanup from reporting**: `FailureAnalyzer` does not close resources; resources not yet owned by Spring must be cleaned up at the allocation site.
9. **Also test the success path**, ensuring analyzers/test policies do not reject valid configurations.
10. **Test against secret leaks** in descriptions, actions, exceptions, startup reports, and logging pipelines.

### Official references

- [Spring Boot 3.3.13 — SpringApplication / Startup Failure](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): failure reporting, events, and startup lifecycle.
- [Spring Boot 3.3 — Create Your Own FailureAnalyzer](https://docs.spring.io/spring-boot/3.3/how-to/application.html): `AbstractFailureAnalyzer` and `META-INF/spring.factories`.
- [Spring Boot 3.3.13 — FailureAnalyzer API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalyzer.html): `analyze(Throwable)` returning `FailureAnalysis` or `null`.
- [Spring Boot 3.3.13 — FailureAnalysis API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalysis.html): description, action, and cause.
- [Spring Boot 3.3.13 — AbstractFailureAnalyzer API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/AbstractFailureAnalyzer.html): recognizing nested exceptions.
- [Spring Boot 3.3.13 — FailureAnalysisReporter API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalysisReporter.html): reporting contract.
- [Spring Boot 3.3.13 — ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): building test contexts and failed context assertions.
- [Spring Boot 3.3 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/index.html): test slices, Spring Boot Test, and JUnit.
- [Spring Framework 6.1 — Bean Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): bean creation, initialization, destruction.
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/): JUnit Jupiter test lifecycle and assertions.
