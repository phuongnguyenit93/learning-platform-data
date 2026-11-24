# Testing Runners with ApplicationArguments and Fake Dependencies in Spring Boot

`ApplicationRunner` and `CommandLineRunner` often contain logic that runs **once during the Spring Boot application startup sequence**: reading command-line arguments, validating inputs, kicking off a batch job, syncing data, or performing preparation steps before the application becomes ready. Because runners are invoked automatically by the framework, test authors commonly run into two problems: having to boot the entire Spring context just to test a parsing branch, or accidentally letting the runner touch a real database/API **before the test has a chance to set up mocks**.

A reliable approach is to **separate argument interpretation, business execution, and Spring Boot's automatic runner invocation mechanism**, then test each layer:

1. **Fast unit test:** construct `new DefaultApplicationArguments(...)` directly, inject a **fake dependency** into the runner, call `runner.run(args)` directly, and verify inputs, invocation count, parameters, and errors. **No ApplicationContext needed.**
2. **Unit test with Mockito:** mock the dependency interface, use `verify(...)` to check interactions, with no real I/O.
3. **Lifecycle integration test:** use `@SpringBootTest(args = {...})` to let **`SpringApplication` start and automatically invoke the runner**, while replacing the dependency with a fake **configured before the context is created**.
4. **Process-level test when needed:** launch a child JVM or JAR to verify stdout, startup failures, exit codes, and external side effects.

This lesson uses **Java 17+, Spring Boot 3.3.x, JUnit Jupiter 5, AssertJ, and Mockito**. In the example, the runner accepts `--count=N` and a `--dry-run` flag; underlying processing is hidden behind the `JobGateway` interface so tests never call a real API or database.

> **Principle:** a runner unit test verifies *what the runner asks its dependency to do*; an integration test verifies *whether Spring Boot actually invokes the runner at the right time with the right arguments and beans*. The two types of testing complement each other; neither replaces the other.

## 1. Where do runners execute in the application lifecycle?

A generalized sequence in Spring Boot 3.3:

~~~text
SpringApplication.run(args)
         |
         +-- Create Environment and ApplicationContext
         +-- Load bean definitions, dependency injection
         +-- Refresh ApplicationContext
         +-- ApplicationStartedEvent
         |
         +-- Call ApplicationRunner / CommandLineRunner
         |       |
         |       +-- Validate ApplicationArguments
         |       +-- Call service/gateway to do work
         |       +-- If unhandled error: startup may fail
         |
         +-- ApplicationReadyEvent when startup completes normally
         +-- SpringApplication.run(args) returns context
~~~

`ApplicationRunner.run(ApplicationArguments args)` is a callback invoked by Spring Boot **near the end of startup and before `SpringApplication.run(...)` completes**. Multiple runners can be ordered with `@Order` or `Ordered`, but you should not assume ordering based on class name or package scan order.

**Two important points when testing:**

- Creating the `BatchRunner` Spring bean **does not mean the `run(...)` method has been called**. Those are two distinct events.
- When `@SpringBootTest` initializes the ApplicationContext via Spring Boot, the runner callback **has typically already executed before `@Test` and `@BeforeEach` begin**. Therefore, configuring a mock inside a test method can be **too late** for the startup run.

If a runner throws an exception during startup, `SpringApplication.run(...)` can fail before returning the context. Unit tests should verify that the error is **propagated**, while failure integration tests require dedicated test design rather than tricks that swallow exceptions and report a false startup success.

## 2. What states does ApplicationArguments have?

Spring Boot provides the `ApplicationArguments` interface and the `DefaultApplicationArguments` implementation. In production, Spring Boot builds the arguments object from the command line. In unit tests, you can instantiate it directly:

~~~java
ApplicationArguments args =
        new DefaultApplicationArguments(
                "--count=3", "--dry-run");
~~~

This snippet requires importing `org.springframework.boot.ApplicationArguments` and `org.springframework.boot.DefaultApplicationArguments`; no Spring context is needed.

Useful methods:

| API | Meaning |
|---|---|
| `getSourceArgs()` | Array of original command-line tokens |
| `getOptionNames()` | Set of option names without the `--` prefix |
| `containsOption("dry-run")` | Whether the flag/option is present |
| `getOptionValues("count")` | List of values associated with the option |
| `getNonOptionArgs()` | Positional arguments |

In particular, `getOptionValues(name)` **does not return the same thing** in all cases:

| Input token | `getOptionValues("count")` |
|---|---|
| No `--count` | `null` |
| `--count` with no value | Empty list `[]` |
| `--count=3` | `["3"]` |
| `--count=3 --count=4` | `["3","4"]` |
| `--count=` | Has a single empty string value, must validate manually |

Therefore, code like the following **can fail** when the option is missing:

~~~java
String count = args.getOptionValues("count").get(0);
~~~

It can throw `NullPointerException` or `IndexOutOfBoundsException`, resulting in confusing messages for operators. The proper solution is to verify **a required option exists, has exactly one value, is non-empty, and falls within the valid range** before dispatching work to the dependency.

For the `--dry-run` flag, `containsOption("dry-run")` indicates presence. If the design specifies the flag **must not take a value**, also check `getOptionValues("dry-run")` to reject forms like `--dry-run=true`.

## 3. Designing runner classes for testability

**Do not put JDBC/HTTP logic directly inside the runner.** Extract an interface representing the business action:

~~~text
CLI tokens
    |
    v
DefaultApplicationArguments / ApplicationArguments
    |
    v
BatchRunner implements ApplicationRunner
    |       - check options
    |       - parse numbers
    |       - select dry-run
    v
JobGateway (interface)
    |
    +-- ConsoleJobGateway (demo app)
    +-- FakeJobGateway (unit test)
    +-- RecordingGateway (integration test)
    +-- Mockito mock (other unit test)
~~~

Benefits:

- The runner is a plain Java object: `new BatchRunner(fake)`.
- The dependency is injected via constructor; no need to mutate private fields with reflection.
- Test validation without opening network connections.
- Test dependency failure paths by having the fake throw an exception intentionally.
- Verify invocation count, order, and arguments using a recording fake/mock.
- Integration tests can use a fake that already exists when SpringApplication invokes the runner at startup.

**Fake vs. mock:** a fake is a test-written implementation that actually holds state or has simple behavior; a mock is generated by a framework like Mockito to stub returns/exceptions and verify interactions. Both are **test doubles**, and neither automatically makes a test an integration test.

## 4. Runnable Spring Boot + JUnit project

The following example includes complete production and test code, requiring no database or HTTP server.

Structure:

~~~text
runner-test-lab/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/runnerlab/
    │   │   ├── RunnerTestingApplication.java
    │   │   ├── JobGateway.java
    │   │   ├── ConsoleJobGateway.java
    │   │   └── BatchRunner.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/runnerlab/
            ├── BatchRunnerTest.java
            └── RunnerStartupIntegrationTest.java
~~~

### 4.1 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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

springBoot {
    mainClass = 'com.example.runnerlab.RunnerTestingApplication'
}
~~~

`spring-boot-starter-test` provides JUnit Jupiter, AssertJ, Mockito, and Spring Test under Boot-compatible dependency management. There is no need to manually pull incompatible JUnit/Mockito versions just to test this runner.

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=runner-test-lab
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=WARN
~~~

Without a web starter, the demo batch application does not need an HTTP server. Setting web application type to `none` makes the intent explicit. In production, consider more detailed logging; here startup messages are suppressed so business output is easy to see.

### 4.2 RunnerTestingApplication.java

~~~java
package com.example.runnerlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class RunnerTestingApplication {

    public static void main(String[] args) {
        // run() invokes ApplicationRunner before returning the context.
        try (ConfigurableApplicationContext ignored =
                     SpringApplication.run(
                             RunnerTestingApplication.class, args)) {
            // One-shot demo: after runner finishes, close the context.
        }
    }
}
~~~

Because `main` **does not call `System.exit(...)`**, JUnit tests do not risk terminating the JVM via a direct call at the application layer. However, **do not call `main` in unit tests**: testing the `BatchRunner` class directly is faster, more stable, and more deterministic.

In `@SpringBootTest` by default, the Spring Boot TestContextLoader creates the context via `SpringApplication` and **does not necessarily invoke the main method itself** (the `useMainMethod` attribute defaults to `NEVER` in Spring Boot 3.3). Therefore, the `try-with-resources` block in `main` does not cause the integration test to close the context before the test method begins.

### 4.3 JobGateway.java

~~~java
package com.example.runnerlab;

public interface JobGateway {

    void execute(int count, boolean dryRun);
}
~~~

Interface representing the business operation. In a real system it might delegate to a repository or external API. For this lesson, it has **no binding** to a database/HTTP, making it easy to fake and test.

### 4.4 ConsoleJobGateway.java

~~~java
package com.example.runnerlab;

import org.springframework.stereotype.Component;

@Component
public class ConsoleJobGateway implements JobGateway {

    @Override
    public void execute(int count, boolean dryRun) {
        if (dryRun) {
            System.out.printf("DRY_RUN count=%d%n", count);
            return;
        }

        System.out.printf("EXECUTED count=%d%n", count);
    }
}
~~~

This is merely a demo implementation printing to the console; it does not actually create data. In production, `dryRun` must be implemented under a contract of **causing no unintended side effects**, or handled in a separate verifiable layer.

### 4.5 BatchRunner.java

~~~java
package com.example.runnerlab;

import java.util.List;
import java.util.Set;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class BatchRunner implements ApplicationRunner {

    private final JobGateway gateway;

    public BatchRunner(JobGateway gateway) {
        this.gateway = gateway;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (!args.getNonOptionArgs().isEmpty()) {
            throw new IllegalArgumentException(
                    "Positional arguments are not supported");
        }

        Set<String> allowed = Set.of("count", "dry-run");
        for (String name : args.getOptionNames()) {
            if (!allowed.contains(name)) {
                throw new IllegalArgumentException(
                        "Unknown option: --" + name);
            }
        }

        List<String> counts = args.getOptionValues("count");
        if (counts == null || counts.size() != 1
                || counts.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Exactly one --count=<1..1000> is required");
        }

        final int count;
        try {
            count = Integer.parseInt(counts.get(0));
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "--count must be an integer", ex);
        }

        if (count < 1 || count > 1000) {
            throw new IllegalArgumentException(
                    "--count must be between 1 and 1000");
        }

        List<String> dryRunValues =
                args.getOptionValues("dry-run");
        if (dryRunValues != null && !dryRunValues.isEmpty()) {
            throw new IllegalArgumentException(
                    "--dry-run is a flag without a value");
        }

        boolean dryRun = args.containsOption("dry-run");

        // Only call dependency after ALL validations have passed.
        gateway.execute(count, dryRun);
    }
}
~~~

**Testability properties:**

- Does not use `System.exit(...)`, threads, sleep, or network APIs inside the runner.
- If input is invalid, an exception escapes and **`gateway.execute(...)` is never called**.
- Valid input causes the gateway to be called **exactly once**.
- If the gateway fails, the runner **does not swallow the error**; the error continues propagating for Spring Boot to handle startup failure.
- Constructor injection allows swapping the dependency with a fake/mock per test without changing application-wide configuration.

Note `@Component` so Spring discovers and registers the runner in production. When a unit test only uses `new BatchRunner(fake)`, that annotation **does not trigger** automatic lifecycle execution — this is intentional.

## 5. Unit testing with DefaultApplicationArguments and a fake dependency

Create file `src/test/java/com/example/runnerlab/BatchRunnerTest.java`:

~~~java
package com.example.runnerlab;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.DefaultApplicationArguments;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;

class BatchRunnerTest {

    private final FakeJobGateway fake = new FakeJobGateway();
    private final BatchRunner runner = new BatchRunner(fake);

    @Test
    void validCountInvokesDependencyExactlyOnce() {
        runner.run(new DefaultApplicationArguments("--count=3"));

        assertThat(fake.calls)
                .containsExactly(new Invocation(3, false));
    }

    @Test
    void dryRunFlagIsPassedToDependency() {
        runner.run(new DefaultApplicationArguments(
                "--count=5", "--dry-run"));

        assertThat(fake.calls)
                .containsExactly(new Invocation(5, true));
    }

    @Test
    void invalidArgumentsNeverInvokeDependency() {
        String[][] invalid = {
                {},
                {"--count"},
                {"--count="},
                {"--count=abc"},
                {"--count=0"},
                {"--count=1001"},
                {"--count=2", "--count=3"},
                {"--count=2", "extra"},
                {"--count=2", "--other=yes"},
                {"--count=2", "--dry-run=true"}
        };

        for (String[] tokens : invalid) {
            assertThatThrownBy(() ->
                    runner.run(new DefaultApplicationArguments(tokens)))
                    .isInstanceOf(IllegalArgumentException.class);
        }

        assertThat(fake.calls).isEmpty();
    }

    @Test
    void downstreamFailureIsNotSwallowed() {
        fake.failure = new IllegalStateException(
                "storage unavailable");

        assertThatThrownBy(() ->
                runner.run(new DefaultApplicationArguments("--count=2")))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("storage unavailable");

        assertThat(fake.calls)
                .containsExactly(new Invocation(2, false));
    }

    @Test
    void mockitoCanVerifyTheSameInteraction() {
        JobGateway mocked = mock(JobGateway.class);
        BatchRunner underTest = new BatchRunner(mocked);

        underTest.run(new DefaultApplicationArguments(
                "--count=7", "--dry-run"));

        verify(mocked).execute(7, true);
        verifyNoMoreInteractions(mocked);
    }

    private record Invocation(int count, boolean dryRun) {
    }

    private static final class FakeJobGateway
            implements JobGateway {

        private final List<Invocation> calls = new ArrayList<>();
        private RuntimeException failure;

        @Override
        public void execute(int count, boolean dryRun) {
            calls.add(new Invocation(count, dryRun));
            if (failure != null) {
                throw failure;
            }
        }
    }
}
~~~

### 5.1 Why is this test truly a unit test?

- No `@SpringBootTest`, `@Autowired`, or `ApplicationContext`.
- Each JUnit test instance under the default lifecycle creates a fresh `FakeJobGateway`.
- All arguments are constructed in memory via `DefaultApplicationArguments`.
- No database, HTTP requests, random timing, or automatic startup.
- Results are verified via **fake state** or **Mockito mock interactions**.

Each test reflects a single responsibility:

| Test | Guarantee |
|---|---|
| `validCountInvokesDependencyExactlyOnce` | Valid input, count parsed properly, no unintended dry-run |
| `dryRunFlagIsPassedToDependency` | Flag received and passed properly |
| `invalidArgumentsNeverInvokeDependency` | Validation before side effects; various invalid inputs |
| `downstreamFailureIsNotSwallowed` | Dependency error propagates; gateway called once |
| `mockitoCanVerifyTheSameInteraction` | Mockito can substitute for a manual fake |

A notable detail of `invalidArgumentsNeverInvokeDependency`: it **does not just check the exception**. It also verifies that the gateway **was never touched**. For an import or migration job, this is a critical boundary to prevent performing partial business work before knowing input is invalid.

### 5.2 When to use fake state vs. Mockito interactions?

**Fakes** are suitable when you need to observe multiple calls, retain data, simulate state, or verify outcomes across multiple steps. For instance, `FakeJobGateway.calls` allows asserting exact order and arguments.

**Mockito mocks** are suitable when you simply want to be sure a method was called with the right parameters/count. They can be extended with:

~~~java
verify(mocked).execute(7, true);
verifyNoMoreInteractions(mocked);
~~~

These two lines belong in the context of the previous test, not a standalone program.

For dependencies with return values or failures, Mockito supports `when(...).thenReturn(...)`, `thenThrow(...)`, and `doThrow(...)`. For the `void execute(...)` interface method in the example, use `doThrow(...)` to simulate an exception; do not call `when(mock.execute(...))` because the method returns `void`.

Do not overuse `verifyNoMoreInteractions(...)` in every production test: non-contract implementation changes can make tests brittle. Use it when **making no extra unintended dependency calls** is itself a business requirement to guard.

## 6. Integration test: letting SpringApplication actually auto-invoke the runner

Unit tests prove `BatchRunner.run(...)` works when you **call it yourself**. However, unit tests do not prove:

- Does Spring recognize `BatchRunner` as a bean?
- Is the runner automatically invoked when context refresh completes?
- Does `@SpringBootTest(args=...)` actually pass arguments to the runner?
- Does dependency injection select the right test double?
- Is the production gateway invoked during context startup?

To test this, create an integration test with `@SpringBootTest` and a fake registered via `@TestConfiguration` **before the runner executes**.

File `src/test/java/com/example/runnerlab/RunnerStartupIntegrationTest.java`:

~~~java
package com.example.runnerlab;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = {
                RunnerTestingApplication.class,
                RunnerStartupIntegrationTest.FakeBeans.class
        },
        args = {"--count=4", "--dry-run"},
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class RunnerStartupIntegrationTest {

    @Autowired
    private RecordingGateway recordingGateway;

    @Test
    void runnerWasCalledDuringSpringApplicationStartup() {
        // When @Test starts, ApplicationRunner has already run.
        assertThat(recordingGateway.snapshot())
                .containsExactly(new Invocation(4, true));
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class FakeBeans {

        @Bean
        @Primary
        RecordingGateway recordingGateway() {
            return new RecordingGateway();
        }
    }

    private record Invocation(int count, boolean dryRun) {
    }

    static final class RecordingGateway implements JobGateway {

        private final List<Invocation> calls =
                new CopyOnWriteArrayList<>();

        @Override
        public void execute(int count, boolean dryRun) {
            calls.add(new Invocation(count, dryRun));
        }

        List<Invocation> snapshot() {
            return List.copyOf(calls);
        }
    }
}
~~~

**Why is this approach reliable?**

1. `@SpringBootTest(classes=..., args=..., webEnvironment=NONE)` uses Spring Boot to create the ApplicationContext.
2. Boot 3.3 runs `ApplicationRunner` during startup, **before the `@Test` method is invoked**.
3. `FakeBeans` is test configuration included from the start; it creates `RecordingGateway` implementing `JobGateway`.
4. `@Primary` ensures this test double is selected when injecting `JobGateway` into `BatchRunner`, instead of the production component-scanned `ConsoleJobGateway`.
5. The fake is created **before the runner executes**, recording `Invocation(4,true)`.
6. The test simply reads the fake's snapshot after startup. **Do not call `runner.run(...)` manually again**, because then the test no longer proves "called once automatically by Spring".
7. The context is managed and closed by Spring Test according to the test lifecycle/cache; no `System.exit` call is needed.

The two test classes operate at two levels: the unit class builds no context, while the integration class builds a context. Running tests on a project with no real database avoids external connections.

### Do not replace the fake with an overly late @MockBean configuration

An anti-pattern:

~~~java
@SpringBootTest(args = "--count=4")
class BrokenTimingTest {

    @MockBean
    JobGateway gateway;

    @BeforeEach
    void setUp() {
        // Too late if the runner already used the gateway at startup.
        doThrow(new IllegalStateException("failed"))
                .when(gateway).execute(4, false);
    }
}
~~~

This is an **illustrative anti-pattern snippet**, omitting imports, not part of the project's runnable code. In Spring Boot 3.3, `@MockBean` can place a mock in the context, but configuring stubbing **in `@BeforeEach` or `@Test`** happens **after Boot has already invoked the runner at startup**. Therefore, the mock may have returned default values when called, and calling `doThrow(...)` afterward does not change startup history.

Spring Boot documentation also warns against expecting `@MockBean` configuration inside a test method to affect beans already used during context refresh. For startup runners, the timing is slightly later than refresh itself, yet still before test methods.

If you want a Mockito mock **pre-configured before startup**, create it in a `@TestConfiguration @Bean` and stub it right inside the factory method, then inject it via `@Primary` like the recording fake pattern. However, for this lesson, a hand-written fake is simpler and easier to observe.

## 7. Running tests and distinguishing test reports from runtime stdout

In the project directory with Gradle wrapper and JDK 17+:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Expected JUnit tests:

~~~text
BatchRunnerTest: 5 tests PASSED
RunnerStartupIntegrationTest: 1 test PASSED
Total: 6 tests PASSED
~~~

This is a **summary of expected test counts and statuses**, not a literal string Gradle is guaranteed to print verbatim. Gradle may only print `BUILD SUCCESSFUL` or show test details in XML/HTML reports depending on configuration.

To run separately:

~~~bash
./gradlew test --tests 'com.example.runnerlab.BatchRunnerTest'
./gradlew test --tests 'com.example.runnerlab.RunnerStartupIntegrationTest'
~~~

The expected result is that both test classes complete successfully. These tests **make no database or external API calls**.

To run the real application:

~~~bash
./gradlew bootJar
java -jar build/libs/runner-test-lab-1.0.0.jar --count=3
~~~

Gradle JAR names typically carry a version suffix as above unless packaging is customized. Check the actual JAR filename in `build/libs` if you change `version` or `archiveFileName`.

**Lines printed by `ConsoleJobGateway`** under normal running conditions:

~~~text
EXECUTED count=3
~~~

With:

~~~bash
java -jar build/libs/runner-test-lab-1.0.0.jar \
    --count=3 --dry-run
~~~

Expected business line:

~~~text
DRY_RUN count=3
~~~

Spring Boot/Gradle may print separate logs; the two lines above are **output from the demo gateway**, not a guarantee that all stdout/stderr contains only that line.

### What happens on invalid input at runtime?

For example:

~~~bash
java -jar build/libs/runner-test-lab-1.0.0.jar --count=abc
~~~

`BatchRunner` throws `IllegalArgumentException` during the startup sequence. Spring Boot handles the startup failure and the application does not finish running normally. No `EXECUTED...` line appears because the gateway was never called.

Do not assert that this example's exit code is always a specific number across every launcher/OS: the code **has not yet defined** a custom exit-code contract. If you want to distinguish exit statuses 0/2/10, add an `ExitCodeGenerator`/`ExitCodeExceptionMapper` mechanism and test it **via a child process**, not just by looking at JUnit assertions.

## 8. Comparing the three testing techniques

| Technique | Has Spring context? | Who calls the runner? | When to use? |
|---|---|---|---|
| Unit test with `DefaultApplicationArguments` + fake | **No** | Test calls `runner.run(args)` | Parsing, validation, call counts, dependency errors |
| Unit test with Mockito mock | **No** | Test calls `runner.run(args)` | Interactions, argument capture, exceptions |
| `@SpringBootTest(args=...)` + fake in `@TestConfiguration` | **Yes** | **Spring Boot startup auto-invokes** | Wiring, lifecycle, arguments passed properly |
| `ApplicationContextRunner` | Lightweight context, not full SpringApplication startup | Test usually calls runner manually if needed | Auto-configuration/bean registration, **does not replace full runner lifecycle tests** |
| Child process/JAR integration | Separate JVM/process | Actual Spring Boot | Startup failure, console output, exit code, shutdown |

There is no reason to boot the entire Spring container just to verify `--count=abc` throws an error. Yet you should also not unit-test alone and conclude `@Component`, `@Order`, injection, and real lifecycle execution are guaranteed to work.

### A bad test: calling the runner manually inside @SpringBootTest

~~~java
@Autowired
BatchRunner runner;

@Test
void callsRunner() {
    runner.run(new DefaultApplicationArguments("--count=4"));
}
~~~

This is an **illustrative snippet** inside a test class that already has imports. Because the context already auto-ran `BatchRunner` earlier, this test calls it a **second time**. It does not prove the runner is auto-invoked once on startup; worse, if the runner has real side effects, the test can cause duplicates.

Therefore, use unit tests that call directly or integration tests that observe state **already present after startup** — do not unintentionally mix the two models.

## 9. Edge cases to test for ApplicationArguments

### 9.1 Missing required option

~~~java
new DefaultApplicationArguments()
~~~

`getOptionValues("count") == null`. The runner should throw an error with a specific message, not `NullPointerException`.

### 9.2 Option name present but missing value

~~~java
new DefaultApplicationArguments("--count")
~~~

Here `count` is present without a value. Structurally this differs from a missing option, though it can throw the same business exception.

### 9.3 Multiple values for one option

~~~java
new DefaultApplicationArguments("--count=2", "--count=3")
~~~

If the contract allows only one value, reject it instead of silently picking the first or last element.

### 9.4 Unknown options and positional arguments

~~~java
new DefaultApplicationArguments("--count=3", "--other=yes")
new DefaultApplicationArguments("--count=3", "data.csv")
~~~

If unsupported, both must be rejected before calling the gateway.

### 9.5 Boolean flags that accept no values

~~~java
new DefaultApplicationArguments("--count=3", "--dry-run")
new DefaultApplicationArguments("--count=3", "--dry-run=true")
~~~

Under the example's contract, the first line is valid and the second is invalid. `containsOption("dry-run")` **alone is insufficient** to reject assigning a value.

### 9.6 Numeric bounds

Test negative numbers, zero, values above the maximum, unparseable numbers, or integer overflow:

~~~text
--count=-1
--count=0
--count=1001
--count=99999999999999999999
--count=3.5
~~~

The code uses `Integer.parseInt` and bounds 1–1000, so all of these cases must fail before reaching the gateway.

### 9.7 Dependency exceptions

Input is valid, but the fake throws `IllegalStateException("storage unavailable")`. The test must verify the **error is propagated**, the gateway is called the exact number of times, and there is no silent retry or false success report.

### 9.8 Dry-run and real side effects

The runner unit test confirms `dryRun=true` is passed down to the dependency. However, if a requirement guarantees "dry-run does not write to the database", you must also test the **gateway implementation** or actual business layer, typically with a fake repository or a separate transaction integration test. **A correctly passed boolean alone does not prove zero side effects.**

## 10. Runners and transactions: avoiding database calls during tests

A runner may call a service using `@Transactional`:

~~~java
@Component
class ImportRunner implements ApplicationRunner {

    private final ImportService importService;

    ImportRunner(ImportService importService) {
        this.importService = importService;
    }

    @Override
    public void run(ApplicationArguments args) {
        importService.importOnce();
    }
}
~~~

This is an **illustrative snippet**, omitting `ImportService` and parsing policy; it is not a complete project. If `@SpringBootTest` runs with the real import service bean, work may execute **before the test method**, opening the datasource and mutating a real or in-memory database.

Do not rely on `@Transactional` on the test method to roll back side effects that already happened **during context startup** before the test transaction began. Even within a test transaction, background threads or external connections do not automatically join that same transaction.

Recommended approach:

- **Unit test:** inject a fake repository/service and call the runner directly, with no DB.
- **Lifecycle integration test:** supply a `@Primary` fake gateway **before startup**, as in section 6.
- **Real database integration test:** use an isolated, controlled test database/container, reset state, and assert transactions.
- **External API:** use an HTTP stub server or mock client bean, blocking any requests to production domains.
- **Jobs with side effects:** use a job ID/idempotency key, verifying no duplicates occur on repeated context refreshes.

If you want a runner enabled conditionally only in production, you can use `@Profile`/`@ConditionalOnProperty` or a managed trigger, but **do not add conditions solely to hide it in tests and skip lifecycle verification**. A separate integration test must still verify that when the condition is enabled, the runner actually executes.

## 11. MockBean and TestConfiguration: timing boundaries

In Spring Boot 3.3, `@MockBean` is a valid tool for replacing beans in the context. It is very useful for services **called only after test setup completes**, such as controllers invoked by MockMvc inside a test method.

For startup runners, ask a different question: **what behavior must the mock have right when SpringApplication builds the context?**

- If the runner only calls a void method and you need to verify the call, a preconfigured recording fake is usually clearer.
- If the mock must return data for the startup runner to succeed, stubbing must be configured **before the runner runs**.
- `@BeforeEach` or `@Test` is not an early enough phase for startup callbacks.
- If using Mockito with `@TestConfiguration @Bean`, create and configure the mock inside the bean factory method rather than waiting for the test method.
- With Spring Boot Test auto-resetting mocks, interactions occurring during context startup may be reset before a test assertion depending on the test listener lifecycle. Do not rely on unverified behavior.
- When multiple tests share a cached context, the startup runner **does not re-run before each test method**, because the context may be reused. To get one invocation per test, use direct unit tests or construct isolated contexts intentionally.

Illustrative example configuring a Mockito mock **before startup**:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class StartupMockConfig {

    @Bean
    @Primary
    JobGateway preconfiguredGateway() {
        JobGateway mock = Mockito.mock(JobGateway.class);
        // Stubbing for startup can be configured here.
        return mock;
    }
}
~~~

This snippet is an **illustrative configuration**, requiring imports for `TestConfiguration`, `Bean`, `Primary`, and `Mockito`; it must be registered into the test context (via explicit classes/imports), not run as a standalone class. For the main project, the fake in section 6 requires even less configuration and is easier to assert against.

**Do not mix versions:** newer Spring Boot docs introduce new mocking annotations and different deprecations. This lesson targets **Spring Boot 3.3.x**, where `@MockBean` is still the corresponding API; when upgrading the framework, check the documentation for the exact version you are running.

## 12. Context caching, test isolation, and verifying "runs exactly once"

Spring Test has an **ApplicationContext cache**: multiple tests using the same configuration can reuse one context. This speeds up tests, but causes confusion if you expect `ApplicationRunner` to re-run automatically before every test.

For example, in the section 6 integration test, `runnerWasCalledDuringSpringApplicationStartup()` checks that the fake recorded **one invocation** from when the context was created. Adding another `@Test` method to that class does not mean `ApplicationRunner` will auto-run again.

To verify **once per startup** accurately, there are three reasonable ways:

1. **Unit test:** create a new runner and call `run(...)` once; check the fake has one invocation.
2. **Integration test:** create a new context, read the recording fake after startup; one invocation is the expected result for a configuration with one runner bean.
3. **Process test:** launch a fresh JVM/JAR, check for a single job execution via logs/durable status, then let the process exit.

Do not assume every JUnit method = one startup. If you must reset the context, consider `@DirtiesContext`, though it slows tests, increases I/O, and can trigger runners with repeated side effects. In most cases, separate unit/integration tests as shown rather than forcing reloads indiscriminately.

Also check:

- Was the runner registered twice (both `@Component` and `@Bean`)? Then it may be called twice.
- Are there multiple runners with the same side effect? Need an idempotency policy or single-run coordination.
- Does the runner spawn an async task and return immediately? Then recording one invocation does not prove the job finished processing.
- Are there multiple `ApplicationContext` instances in one JVM? A new context can execute its own runner.
- Are there multiple replicas in Kubernetes? Each JVM runs its own runner; "once per startup" **does not mean once cluster-wide**.

## 13. Testing order across multiple runners

Spring Boot supports `@Order`/`Ordered` to determine execution order when multiple `ApplicationRunner` or `CommandLineRunner` beans exist.

**Illustrative** configuration example, not in the main project:

~~~java
@Component
@Order(10)
class PrepareRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        // Prepare prerequisites.
    }
}

@Component
@Order(20)
class ImportRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        // Import after PrepareRunner.
    }
}
~~~

These are two illustrative classes requiring imports for `Component`, `Order`, `ApplicationRunner`, and `ApplicationArguments`. They can be verified using a **shared recording fake**: each runner records a marker into a `List<String>`, then assert the order `["prepare","import"]` in an integration test.

**Do not test ordering by measuring timestamps between log lines**: async logging, thread scheduling, or multiple loggers make observations unreliable. Check intentional state/sequence, or use an integration test with beans sharing the same recorder.

If runners must guarantee **business-critical ordering**, consider a single runner explicitly orchestrating the steps. Scattering complex workflows across multiple runners makes rollback, error handling, and retries harder to manage.

## 14. When a runner works asynchronously

A runner statement like the following can be dangerous:

~~~java
@Override
public void run(ApplicationArguments args) {
    backgroundService.executeAsync();
}
~~~

This is an illustrative method inside a class with a `backgroundService` dependency and async configured. If `executeAsync()` merely submits a task and returns, `ApplicationRunner` finishes **before the work is done**. Spring Boot may announce Ready even while the task is still processing.

A unit test with a fake only confirms that a **request was sent** to the dependency; it does not prove the async work completed. To test completion:

- Have the service return `CompletableFuture<Result>` or an equivalent completion contract.
- Wait via `get(timeout, ...)`/`join()` when semantics allow, managing timeouts and cancellation.
- Have the fake control future completion as success/failure.
- Verify async errors are not swallowed and whether the runner decides to fail startup.
- In integration tests, never use `Thread.sleep(...)` to "wait long enough"; use a latch/future with a timeout.
- If the job must definitely complete before Ready, the runner **must wait** or readiness infrastructure must be designed to reflect progress accurately.

Illustrative API example:

~~~java
CompletableFuture<Result> future =
        service.executeAsync(options);

Result result = future.get(5, TimeUnit.SECONDS);
~~~

This snippet requires existing types/variables/imports and an exception handling policy. Do not treat it as a standalone Java file. Fire-and-forget processing may be appropriate if designed that way, but clearly distinguish "runner enqueued the job" from "batch succeeded".

## 15. Why ApplicationContextRunner is not equivalent to @SpringBootTest

The name **`ApplicationContextRunner`** is easily confused with **`ApplicationRunner`**; they are **not the same thing**.

- `org.springframework.boot.test.context.runner.ApplicationContextRunner` is a **test utility** that builds a context per configuration and lets you assert conditions, properties, and beans.
- `org.springframework.boot.ApplicationRunner` is a **startup callback interface** invoked by `SpringApplication` during the startup sequence.

A typical `ApplicationContextRunner` **only refreshes the context via a test utility**; it does not fully reproduce every step of `SpringApplication.run(...)`, especially invoking runners and publishing startup/ready events. To test a runner method in such a test, the test must **invoke it explicitly** with `DefaultApplicationArguments`, or use `@SpringBootTest` when testing Boot's lifecycle itself.

Do not write:

~~~java
new ApplicationContextRunner()
    .withUserConfiguration(SomeConfiguration.class)
    .run(context -> {
        // Inferring "runner bean exists"
        // means "runner was called by SpringApplication"
        // is a wrong conclusion.
    });
~~~

This is an **illustrative anti-pattern**, requiring `SomeConfiguration` and imports. The error lies in the **conclusion about lifecycle**, not creating the context.

## 16. Observing runner errors without making tests flaky

There are three failure levels:

| Error location | Unit test should check | Integration/process test should check |
|---|---|---|
| Input parsing | Exception message/type; gateway is not called | Startup fails if input is invalid in the real application |
| Dependency execution | Fake throws error; runner does not swallow/retry outside contract | Spring Boot startup failure/cleanup works properly |
| Infrastructure bootstrap | Usually outside runner unit scope | Controlled bean wiring/config/datasource failures |

For production logic needing exit codes that distinguish input vs. execution errors, you can use distinct exception types, `ExitCodeGenerator`, or `ExitCodeExceptionMapper`. However, **decouple the exit code contract from parser unit tests** so you don't have to launch a child JVM for every input variant.

**Never assert** that an `IllegalArgumentException` will always become exit code 2 in Spring Boot solely from the exception name. Configure an explicit policy if you want specific codes.

**Never run failing integration tests against a real database** just to "test failure", because the runner executes before test setup and could unintentionally alter data. For real errors, simulate them in a fake or use an isolated test infrastructure.

## 17. Common testing mistakes

**Mistake 1 — Using a Spring context for every simple parsing case.**

Makes tests slow, introduces many dependencies, and obscures exact failure causes. Use `new DefaultApplicationArguments(...)` and a fake in unit tests.

**Mistake 2 — Asserting only the exception on invalid input.**

Insufficient: the gateway might have run before the exception was thrown. Also assert the fake recorded no invocations.

**Mistake 3 — Using `@MockBean`, stubbing in `@BeforeEach`, and expecting the runner to use that stub at startup.**

Too late. The runner already executed while SpringApplication initialized the context. Use a fake/mock configured in `@TestConfiguration @Bean` before startup.

**Mistake 4 — Manually calling `runner.run(...)` in an integration test and concluding Boot auto-invoked it once.**

The call inside the test may be the second invocation. Observe the recorder right after startup instead of calling it again.

**Mistake 5 — Failing to distinguish `getOptionValues` returning null vs. an empty list.**

Can cause NPE/IndexOutOfBounds, or accept empty options contrary to contract.

**Mistake 6 — Letting the runner use a real repository/HTTP client in @SpringBootTest.**

Can mutate data before the test method begins. Fakes must be injected before startup.

**Mistake 7 — Treating a fake invocation as proof that an async task finished.**

For fire-and-forget, the fake only proves submission, not that data was committed.

**Mistake 8 — Confusing `ApplicationContextRunner` with `ApplicationRunner`.**

One is a context test utility, the other is a Boot startup callback. Never assume context runner invokes lifecycle runners.

**Mistake 9 — Assuming every @Test method is an independent startup.**

Spring Test context caching can reuse contexts; startup runners normally run only when a context is freshly created.

**Mistake 10 — Using `System.exit(...)` inside a runner tested in the same JVM.**

Can terminate the entire Gradle/JUnit process. Separate the outcome and use process-level tests when exit statuses are required.

**Mistake 11 — Asserting only on the log "runner started".**

Logs can be buffered or interleaved from multiple sources. Assert invocations, state, exceptions, and process status directly when needed.

**Mistake 12 — Using `Thread.sleep(1000)` to check job completion.**

Flaky under heavy CI load; use a completion contract, latch/future, and timeout.

**Mistake 13 — Enabling `@Order` without testing real dependencies and side effects.**

Ordering does not replace workflows/idempotency; if later steps depend on earlier ones, test state and business contracts, not just runner names.

**Mistake 14 — Ignoring duplicate/unknown input options.**

Picking the first element or swallowing unknown options can trigger the wrong batch run. Require an allowlist and validation.

## 18. Extended exercises

1. In `BatchRunnerTest`, add cases for `--count=1` and `--count=1000`; verify the gateway receives the exact boundary values.
2. Try `--count=-1`, `--count=3.5`, and `--count=999999999999999999`, verifying the gateway is never called.
3. Modify the contract to support a positional input file, then explicitly test the difference from named options.
4. Add a `--mode=import|validate` parameter, reject other modes, and verify all validations run before calling the gateway.
5. Create a Mockito mock for `JobGateway`, configure `doThrow(...)`, and assert the exception propagates through `BatchRunner.run(...)`.
6. Remove `@Primary` from `RecordingGateway` in the integration test: explain why two `JobGateway` candidates can cause an injection error or unexpected selection.
7. Add another runner with `@Order(20)` and a shared recorder; verify runner order matches policy.
8. Try booting a `@SpringBootTest` with invalid input and observe context-load failure; use a **separate** test class so it does not break the main suite.
9. Change `JobGateway` to an API returning `CompletableFuture`, fake success/failure completion, and test timeouts without sleep.
10. Use a child process test for the JAR to verify startup logs and real exit codes on invalid input, instead of calling `main` containing `System.exit` inside JUnit.
11. Configure two integration test classes with different arguments; explore why they produce different context cache keys and may invoke the runner again.
12. Swap production `ConsoleJobGateway` for a real external adapter in staging; ensure the unit/integration suite remains completely isolated from real endpoints.

## 19. Checklist before reviewing a runner and test suite

- The runner properly implements `ApplicationRunner`, accepts `ApplicationArguments`, and uses constructor injection.
- Parse/validate every option before calling business logic; distinguish missing, empty, duplicate, wrong type, out-of-range, and unknown options.
- Dependencies have suitable interfaces/abstractions; tests can inject fakes/mocks **without a Spring context**.
- Unit tests verify both outcomes **and zero side effects** on invalid input.
- Dependency errors propagate or map per contract, rather than being logged and swallowed.
- `DefaultApplicationArguments` uses proper CLI syntax without confusing options and positional args.
- `@SpringBootTest(args=...)` is used to verify the runner is auto-invoked by Boot during startup.
- Fakes are supplied via `@TestConfiguration @Bean @Primary` **before the runner executes**.
- Never stub mocks inside test methods expecting to alter calls that already happened at startup.
- Never call `run(...)` manually in tests verifying auto-invocation.
- Startup tests do not open DB/network connections or execute real non-rollbackable jobs.
- Account for context caching, runner ordering, multiple contexts, and multiple replicas.
- Async jobs have explicit completion/timeout tests without arbitrary sleeps.
- When exit codes are needed, test in a separate subprocess without killing the test JVM via `System.exit`.
- Include an integration test proving wiring + lifecycle; keep most other cases as fast, independent unit tests.

### Official documentation

- Spring Boot 3.3 — `ApplicationRunner` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html
- Spring Boot 3.3 — `ApplicationArguments` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html
- Spring Boot 3.3 — `DefaultApplicationArguments` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/DefaultApplicationArguments.html
- Spring Boot 3.3 — Testing Spring Boot Applications (arguments, `@SpringBootTest`, `@MockBean`): https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — `SpringBootTest` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/SpringBootTest.html
- Spring Boot 3.3 — SpringApplication and runners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — `ApplicationContextRunner` test utility: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- JUnit 5 — Writing Tests: https://junit.org/junit5/docs/current/user-guide/

**Conclusion:** testing `ApplicationRunner` does not require opening a Spring context for every case. Use `DefaultApplicationArguments` with **fake/mock dependencies** to verify parsing, validation, invocation counts, and failures quickly and deterministically. Then use **a `@SpringBootTest(args=...)` integration test with a fake registered before startup** to prove Spring Boot actually auto-invokes the runner and injects the right dependency. Clearly distinguish "test manually calls `run(...)`" from "framework invokes runner at startup", avoid real side effects, late mock configuration, and tests broken by context caching.
