# The Role of ApplicationRunner and CommandLineRunner in Spring Boot

## Learning Objectives

In Spring Boot, there are tasks that should run **after Spring has created the application context and initialized the required beans**, yet **before the application is considered ready to accept traffic**. Examples include validating reference data, checking required startup conditions, warming up a bounded cache, or executing a CLI/batch task based on command-line arguments.

`ApplicationRunner` and `CommandLineRunner` are the two official callbacks designed for this scenario. They are not controllers, not a background loop, and are not automatically invoked by Spring Framework in every type of context initialization; this is a contract discovered and executed at startup by Spring Boot's **SpringApplication**.

After this lesson, you will be able to:

1. Identify precisely where runners sit between `ApplicationStartedEvent` and `ApplicationReadyEvent`.
2. Distinguish between `run(ApplicationArguments args)` and `run(String... args)`, and choose the appropriate interface.
3. Use `ApplicationArguments` to read options, valueless flags, repeated options, and non-option arguments.
4. Register one or more runners using `@Component` or `@Bean`; control execution order using `@Order`/`Ordered`.
5. Write, compile, and run a Java 17+ / Spring Boot 3.3 project with two runners and verifiable log output.
6. Understand the impact of slow runners, runner failures, retries, transactions, readiness, and application lifecycle.
7. Avoid confusing runners with `@PostConstruct`, `ApplicationContextInitializer`, `ApplicationReadyEvent`, scheduled tasks, or request handlers.

**Context:** Spring Boot Application Runtime → Runner. The main APIs and examples use Spring Boot **3.3.13**, Spring Framework 6.1, and Java 17.

## 1. At Which Stage Do Runners Execute?

Abbreviated sequence of a **successful** `SpringApplication.run(...)` call:

~~~text
main(String[] args)
   |
   +-- SpringApplication.run(args)
        |
        +-- Prepare Environment and ApplicationContext
        +-- ApplicationContext.refresh()
        |    +-- Create appropriate bean definitions/bean instances
        |    +-- Initialize non-lazy singletons
        |    +-- Start context infrastructure
        |    +-- ContextRefreshedEvent
        |
        +-- ApplicationStartedEvent
        +-- AvailabilityChangeEvent(LivenessState.CORRECT)
        |
        +-- Discover ApplicationRunner and CommandLineRunner beans
        +-- Sort via Ordered / @Order when present
        +-- Invoke run(...) on each runner
        |
        +-- ApplicationReadyEvent
        +-- AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
        |
        +-- Return ConfigurableApplicationContext
             |
             +-- Application continues running until stopped
~~~

This is a **diagram of major milestones**, not an exhaustive list of every internal callback. In a web application, the embedded server may already have been started during the refresh phase; an open port does not mean startup runners have finished.

Key takeaways:

- **Before runners:** The context has refreshed successfully; singletons requiring eager initialization have generally been created, and injection is working. Spring Boot has published `ApplicationStartedEvent` and signaled liveness `CORRECT`.
- **During runners:** This is still part of the **startup process** orchestrated by `SpringApplication.run`. A synchronous runner that has not finished can prevent the overall startup from reaching ready.
- **After all runners complete successfully:** Only then does Boot publish `ApplicationReadyEvent` and update readiness to `ACCEPTING_TRAFFIC`.
- **When a runner throws an unhandled exception:** Startup can fail. Subsequent runners in the execution order are not necessarily called; `ApplicationReadyEvent` and the accepting readiness state do not occur on the normal success path.

Saying "runners run when startup finishes" must be understood accurately: **context refresh is finished**, but **the entire SpringApplication startup is not finished yet**. Runners themselves count toward the time spent reaching ready.

## 2. Two Interfaces with the Same Purpose, Different Argument Signatures

### ApplicationRunner

API signature in Spring Boot 3.3:

~~~java
@FunctionalInterface
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
~~~

This is an **illustrative signature**, not a re-implementation of `org.springframework.boot.ApplicationRunner` in your source code. `ApplicationArguments` provides both the raw arguments and categorized data:

- `getSourceArgs()`: all source arguments as `String[]`.
- `getOptionNames()`: set of option names.
- `containsOption("name")`: whether this option is present.
- `getOptionValues("name")`: the values for that option; may be `null` when absent.
- `getNonOptionArgs()`: arguments that do not have option form.

This is usually the better choice when you want to write a startup command with options like `--mode=verify`, `--dry-run`, `--region=apac`, or need to separate positional arguments from options.

### CommandLineRunner

API signature:

~~~java
@FunctionalInterface
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
~~~

This is also an **illustrative signature**, not a re-implementation of Spring's interface. `String...` is Java varargs; at runtime the callback receives the string array of arguments forwarded from `main(String[] args)`/`SpringApplication.run(args)`. This runner is convenient for logic that needs the entire raw arguments array, or small projects that do not need a dedicated parsing API.

### Comparison Table

| Criterion | `ApplicationRunner` | `CommandLineRunner` |
| --- | --- | --- |
| Package | `org.springframework.boot` | `org.springframework.boot` |
| Method | `run(ApplicationArguments args)` | `run(String... args)` |
| Arguments type | Wrapper categorizing options/non-options | Raw string array |
| Built-in API for reading `--name=value` | Yes | No; must parse manually if needed |
| Can read raw strings? | Yes, `getSourceArgs()` | Yes, directly in `args` |
| When Boot invokes it | After refresh, before ready | After refresh, before ready |
| Receives dependency injection? | Yes, when the runner is a Spring bean | Yes, when the runner is a Spring bean |
| Can use `@Order`/`Ordered`? | Yes | Yes |
| Can the method throw `Exception`? | Yes | Yes |
| Repeats on every HTTP request? | No | No |
| Runs automatically on a cron schedule? | No | No |

**Neither interface "runs before" the other simply because of its type name.** If you want priority between them, configure the order explicitly. Runners of both types are collected and sorted by Spring Boot in the same startup phase.

## 3. ApplicationArguments: Reading Arguments Correctly

Suppose the application is launched with the following arguments:

~~~bash
--mode=demo --tag=alpha --tag=beta job-42 --dry-run
~~~

These are the **application arguments**, not the syntax of a standalone shell command. In real CLI usage, these arguments follow the JAR name, or are passed by the Gradle/Maven/IDE run mechanism.

Breakdown:

| Expression | Result from `ApplicationArguments` |
| --- | --- |
| `containsOption("mode")` | `true` |
| `getOptionValues("mode")` | `[demo]` |
| `getOptionValues("tag")` | `[alpha, beta]` |
| `getNonOptionArgs()` | `[job-42]` |
| `containsOption("dry-run")` | `true` |
| `getOptionValues("dry-run")` | Empty list `[]` because the flag is present with no value |
| `getOptionValues("missing")` | `null` because the option is absent |
| `getSourceArgs()` | Raw array containing all five passed elements |

**Distinguish the three cases of `getOptionValues`:**

1. Option **does not exist** → `null`.
2. Option exists **without a value**, such as `--dry-run` → empty list `[]`.
3. Option has one or more values `--tag=...` → list of strings preserving the parsed values.

Therefore, do not call `args.getOptionValues("mode").get(0)` before checking `null`/`isEmpty()`. If an option must have exactly one value, validate it explicitly instead of letting an unclear `NullPointerException` or `IndexOutOfBoundsException` occur.

Example of validating a required option:

~~~java
List<String> modes = args.getOptionValues("mode");

if (modes == null || modes.size() != 1
        || modes.get(0).isBlank()) {
    throw new IllegalArgumentException(
            "Expected exactly one --mode=value");
}

String mode = modes.get(0);
~~~

This snippet illustrates **the body of `ApplicationRunner.run`**, requiring `import java.util.List` and the variable `args` of type `ApplicationArguments`. It is not a standalone runnable Java file.

### --name=value vs. --name value Syntax

Spring Boot parses command-line options in `--name=value` form. Given the string:

~~~text
--mode demo
~~~

`--mode` is an option **with no directly attached value**, whereas `demo` is treated as a non-option argument under standard parser behavior. Do not assume the two ways of passing arguments are equivalent.

In addition, `-Dspring.profiles.active=dev` is a **JVM system property** when placed before `-jar`, not a `--...` argument in the `main` array. Similarly, `-Xmx512m` is a JVM option, not part of `CommandLineRunner.run` when placed in the proper position for the JVM.

### Valueless Flags and Booleans

`--dry-run` carries the meaning of a "presence flag" via `containsOption("dry-run")`. Meanwhile, `--dry-run=false` still causes `containsOption("dry-run")` to return `true`; in that case `getOptionValues("dry-run")` is `[false]`. If you want to support both forms, define how they are interpreted:

~~~java
boolean requestedDryRun = args.containsOption("dry-run");
~~~

The line above represents a **presence flag**, not a general-purpose boolean parser. For options where `true`/`false` can be passed, parse the value and validate explicitly.

### Numeric, Enum, or Path Data

`ApplicationArguments` returns **strings**; it does not automatically convert every `--retries=3` into an `int` for your code. You can use `Integer.parseInt(...)`, `Enum.valueOf(...)`, a conversion service, or binding to configuration properties after checking for errors and valid values.

Do not pass arbitrary command-line arguments directly into filenames, queries, or system commands without validation. Be mindful of arguments containing secrets: shell history, process lists, build logs, or startup logs can expose them; for secrets, prefer an appropriate secure configuration channel.

## 4. How SpringApplication Passes and Processes Arguments

With a standard main method:

~~~java
public static void main(String[] args) {
    SpringApplication.run(MyApplication.class, args);
}
~~~

`args` from `main` is forwarded to `SpringApplication.run(...)`. After creating the `ApplicationContext`, Boot registers `ApplicationArguments` so beans can inject it:

~~~java
@Component
class StartupArgumentsInspector {

    StartupArgumentsInspector(ApplicationArguments args) {
        boolean debugEnabled = args.containsOption("debug");
        // Can be used to prepare appropriate configuration.
    }
}
~~~

This is an **illustrative non-standalone snippet**, requiring imports for `Component`/`ApplicationArguments`. Injecting `ApplicationArguments` does not mean it runs `run` automatically; only beans implementing a runner or an appropriate callback mechanism are invoked by Spring Boot in the runners phase.

By default, Spring Boot also adds a **command-line property source** to `Environment`, so an option like `--server.port=9090` can participate in configuration precedence. However, those are **two distinct mechanisms**:

- `ApplicationArguments` categorizes the inputs passed to `run`.
- `Environment` resolves properties from multiple sources according to precedence order.

If programmatic code calls `SpringApplication.setAddCommandLineProperties(false)` before `run`, exposing command-line args as a property source is disabled, which **does not mean** `ApplicationArguments` no longer holds the passed raw arguments. Do not confuse the role of a startup runner with binding configuration via `@ConfigurationProperties`.

## 5. When Are Runner Beans Created and How Many Times Are They Called?

A class can become a runner via component scanning:

~~~java
@Component
public class VerifyStartup implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) throws Exception {
        // Perform startup checks.
    }
}
~~~

Or you can declare it via `@Bean`:

~~~java
@Configuration
class StartupConfiguration {

    @Bean
    CommandLineRunner logArguments() {
        return args -> System.out.println(
                "Arguments: " + Arrays.toString(args));
    }
}
~~~

These two examples are **configuration snippets**, not standalone projects; they require importing `Component`/`ApplicationRunner` or `Configuration`/`Bean`/`CommandLineRunner`, `Arrays`.

Key points:

1. `ApplicationRunner` and `CommandLineRunner` are **functional interfaces**, easy to write as lambdas or classes.
2. A runner must be a **bean managed by SpringApplication** for Boot to discover and invoke it automatically. Simply doing `new VerifyStartup()` in other code without registering it as a bean will not make it run automatically.
3. By default, non-lazy `@Component` classes are typically instantiated during refresh; **the `run` method is not yet called in the constructor**. The callback is invoked in the runners phase after refresh.
4. A normal runner is invoked **once per successful `SpringApplication.run` that reaches the runners phase**. If an application has multiple contexts/runs, there may be multiple invocations across the JVM. If a bean implements **both interfaces**, Boot can invoke both callbacks separately.
5. Spring does not turn a runner into a scheduler: `run` does not repeat every minute, on every request, or whenever the BeanFactory creates another bean.

If you need a command invoked on every request, use a controller/service; if you need a recurring schedule, explore `@Scheduled`; if you need continuous message processing, use a consumer/worker with its own lifecycle.

## 6. Ordering Multiple Runners: @Order and Ordered

When there are two or more runners, execution order matters if a later step depends on the result of an earlier step. Spring Boot supports:

- `org.springframework.core.annotation.Order` on the class.
- `org.springframework.core.Ordered` on the bean.
- `PriorityOrdered` in special cases requiring higher-priority semantics.

Example:

~~~java
@Component
@Order(10)
public class ValidateRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Validate startup");
    }
}
~~~

~~~java
@Component
@Order(20)
public class WarmupRunner implements CommandLineRunner {
    @Override
    public void run(String... args) {
        System.out.println("Warm up cache");
    }
}
~~~

These two snippets illustrate classes that require their corresponding imports. **Smaller order values are generally invoked first**. Here `ValidateRunner` is called before `WarmupRunner` even though they implement different interfaces.

Do not rely on filename order, `@Component` scan order, or bean definition order to infer which runner executes first. If there is a strict dependency that must complete in sequence, configure the order explicitly or consolidate the logic into an orchestration service with clear steps.

### Do Not Use @DependsOn as a Substitute for @Order

`@DependsOn` can affect **bean creation/initialization order**, but it is not a contract for ordering `run(...)` callbacks across runners after refresh. To control **runner execution order**, use `@Order`/`Ordered`.

### Avoid Having One Bean Implement Both Interfaces

Example **not recommended**:

~~~java
class DualRunner implements ApplicationRunner, CommandLineRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("ApplicationRunner callback");
    }

    @Override
    public void run(String... args) {
        System.out.println("CommandLineRunner callback");
    }
}
~~~

The code above illustrates a valid Java class if both interfaces are imported. If this class is a Spring bean, SpringApplication may treat it as both runner types simultaneously and invoke **both methods** during a single startup. That does not mean one method is automatically chosen to run instead of the other. Pick one interface per responsibility to avoid duplicate side effects.

## 7. Runnable Project: Comparing Both Runners and Startup Events

The example has four Java classes, one Gradle settings file, and one Gradle build file. The application **does not open an HTTP server**; at the end of the experiment, `main` closes the context so the program terminates. This makes it easy to observe the lifecycle clearly.

### 7.1. Project Structure

~~~text
runner-lifecycle-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/runner/
    ├── RunnerDemoApplication.java
    ├── OptionsRunner.java
    ├── RawArgumentsRunner.java
    └── StartupEventObserver.java
~~~

**`settings.gradle`:**

~~~groovy
rootProject.name = 'runner-lifecycle-demo'
~~~

**`build.gradle`:**

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
    mainClass = 'com.example.runner.RunnerDemoApplication'
}
~~~

Spring Boot plugin version 3.3.13 together with the BOM specifies the corresponding dependencies. The project requires a Gradle version compatible with Spring Boot 3.3, JDK 17 or newer, and connectivity to Maven Central if dependencies are not yet cached.

### 7.2. Main: SpringApplication.run and Closing the Context

**`src/main/java/com/example/runner/RunnerDemoApplication.java`:**

~~~java
package com.example.runner;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class RunnerDemoApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(
                RunnerDemoApplication.class);

        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN: run returned");
        }

        System.out.println("MAIN: context closed");
    }
}
~~~

`@SpringBootApplication` scans package `com.example.runner` to detect the three beans in the following files. `WebApplicationType.NONE` ensures the demo application does not create a web server. `Banner.Mode.OFF` and `setLogStartupInfo(false)` reduce startup output; they do not remove all system logs.

We use `try-with-resources` to close the context after the test run. **Long-running web applications should not close the context immediately when `run` returns**; this is only a way to terminate the example CLI program.

### 7.3. ApplicationRunner: Structured Arguments

**`src/main/java/com/example/runner/OptionsRunner.java`:**

~~~java
package com.example.runner;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class OptionsRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {

        System.out.println(
                "APP_RUNNER: mode=" + args.getOptionValues("mode"));

        System.out.println(
                "APP_RUNNER: tags=" + args.getOptionValues("tag"));

        System.out.println(
                "APP_RUNNER: nonOptions=" + args.getNonOptionArgs());

        if (args.containsOption("fail-demo")) {
            System.out.println("APP_RUNNER: intentional failure");
            throw new IllegalStateException(
                    "Demo startup validation failed");
        }
    }
}
~~~

This runner shows that `ApplicationArguments` lets you read repeated `--tag=...` options and positional data. `@Order(10)` gives this runner priority before the bean with `@Order(20)`, **not** because it is an ApplicationRunner.

The `--fail-demo` block only runs when that flag is provided; it lets you test the startup failure path without editing code.

### 7.4. CommandLineRunner: Raw Argument Array

**`src/main/java/com/example/runner/RawArgumentsRunner.java`:**

~~~java
package com.example.runner;

import java.util.Arrays;
import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(20)
public class RawArgumentsRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println(
                "CMD_RUNNER: raw=" + Arrays.toString(args));
    }
}
~~~

This runner does not categorize arguments; it simply prints the entire array it receives. In an application that needs to parse a custom format or pass arguments verbatim to another command-line tool, this approach may be appropriate. For standard `--name=value` options, `ApplicationRunner` helps avoid writing your own parser.

### 7.5. Observing ApplicationStartedEvent and ApplicationReadyEvent

**`src/main/java/com/example/runner/StartupEventObserver.java`:**

~~~java
package com.example.runner;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StartupEventObserver {

    @EventListener(ApplicationStartedEvent.class)
    public void onStarted() {
        System.out.println("EVENT: started");
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("EVENT: ready");
    }
}
~~~

These two listeners are registered when the context processes beans. `ApplicationStartedEvent`/`ApplicationReadyEvent` are both published after refresh, so listener beans can receive them. They serve to illustrate the two boundaries of the window in which runners are invoked, **not** as an API to run runners themselves.

### 7.6. Running with Arguments and Verifying Output

In the `runner-lifecycle-demo` directory:

~~~bash
gradle bootRun --args="--mode=demo --tag=alpha --tag=beta job-42"
~~~

If a Gradle Wrapper is present, replace `gradle` with `./gradlew` on Linux/macOS or `.\gradlew.bat` on Windows. The sample project does not generate a wrapper automatically. In an IDE, set **program arguments** to `--mode=demo --tag=alpha --tag=beta job-42`; do not put the entire Gradle command into the arguments field.

Ignoring Gradle/Spring logs and looking at the lines printed by the **demo Java code itself**, the expected order is:

~~~text
EVENT: started
APP_RUNNER: mode=[demo]
APP_RUNNER: tags=[alpha, beta]
APP_RUNNER: nonOptions=[job-42]
CMD_RUNNER: raw=[--mode=demo, --tag=alpha, --tag=beta, job-42]
EVENT: ready
MAIN: run returned
MAIN: context closed
~~~

**Why this exact order?**

1. `EVENT: started`: the context has refreshed, and Boot has not yet called the runners.
2. `APP_RUNNER`: `OptionsRunner` has `@Order(10)`, receives `ApplicationArguments`, and prints the parsed values.
3. `CMD_RUNNER`: `RawArgumentsRunner` has `@Order(20)` and receives the exact raw array.
4. `EVENT: ready`: both runners finished without throwing an exception.
5. `MAIN: run returned`: the `SpringApplication.run(...)` call returned the context.
6. `MAIN: context closed`: the `try-with-resources` block ended, closing the context.

Note that the output above shows **the lines printed by the example code**, excluding framework logs and build messages. With different flags/arguments, the lines printing arguments will change according to the input.

### 7.7. Verifying the Startup Failure Path

Run a new session, intentionally asking the first runner to fail:

~~~bash
gradle bootRun --args="--mode=demo --tag=alpha --tag=beta job-42 --fail-demo"
~~~

The lines printed by the program **before the error is handled by Spring Boot**:

~~~text
EVENT: started
APP_RUNNER: mode=[demo]
APP_RUNNER: tags=[alpha, beta]
APP_RUNNER: nonOptions=[job-42]
APP_RUNNER: intentional failure
~~~

Afterward, Boot/Gradle may print a stack trace, failure analysis, and a non-zero exit status. `RawArgumentsRunner` does not run because the preceding runner threw an exception; `ApplicationReadyEvent` is also not published on the success path, so there is no `EVENT: ready`. `app.run(args)` throws an exception, so `MAIN: run returned` is not printed; the code after `try` also does not print `MAIN: context closed`.

**Distinction:** Spring Boot can still run its error-handling path and clean up the created context. The absence of log lines from `main` does **not** mean the container performs no cleanup.

### 7.8. What Happens If @Order Is Removed?

If `@Order` is removed from both runners, **do not write tests asserting that one runner must always run before the other** solely based on class name or component scanning order. Results might happen to look stable in a small project, but that should not be turned into a business contract.

If runner A must complete before B, define an explicit order. When dependencies are tight or involve complex rollback, consider using **a single orchestrating runner** and services called in explicit, easier-to-test steps.

## 8. Choosing a Runner or Another Lifecycle Callback?

| Need | Usually Suitable Tool | Why |
| --- | --- | --- |
| Establish an invariant of a bean once dependencies are injected | `@PostConstruct` / `InitializingBean` | Tied to **the bean's own** initialization |
| Customize `ApplicationContext` before refresh | `ApplicationContextInitializer` | Context has been created, all beans not yet initialized |
| Run a startup task after refresh that must finish before ready | `ApplicationRunner` / `CommandLineRunner` | Matches Boot's run-on-startup contract |
| Observe that the context has refreshed | `ContextRefreshedEvent` | Represents the Spring context milestone |
| Observe that Boot has started before runners | `ApplicationStartedEvent` | Post-refresh milestone before runners run |
| Observe that Boot has finished calling runners | `ApplicationReadyEvent` | Published after runners and before the readiness accepting event |
| Start/stop a component with a managed lifecycle | `SmartLifecycle` | Participates in starting/stopping runtime components |
| Execute scheduled tasks | `@Scheduled` or scheduler | Repeating callback on its own trigger |
| Serve each HTTP request | Spring MVC/WebFlux controller/service | Request-scoped, not app startup |
| Run periodic batch with checkpoint/restart | Scheduler + Spring Batch (if appropriate) | Has job model, state, retry, and recovery |

**Do not put an infinite loop inside a runner** just to "run right at boot." If `run` never returns, Boot cannot advance to `ApplicationReadyEvent` and readiness accepting. For a consumer/background worker, you can use a runner merely to *initialize or schedule* background execution and then return, paired with appropriate `SmartLifecycle`, shutdown, and health mechanisms. When the platform must ensure the consumer is genuinely ready before receiving traffic, incorporate that condition into the readiness policy.

`@PostConstruct` is not a miniature runner either: it is invoked during bean initialization; unrelated singletons may not have finished being created yet. Runners execute after context refresh, so they generally have a more stable DI environment for application-level work.

## 9. Appropriate and Inappropriate Use Cases

### 9.1. Mandatory Validation Before Ready

For example, an application needs to verify a list of required configurations:

~~~java
@Component
class RequiredConfigurationRunner implements ApplicationRunner {

    private final PaymentSettings settings;

    RequiredConfigurationRunner(PaymentSettings settings) {
        this.settings = settings;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (settings.getMerchantId() == null
                || settings.getMerchantId().isBlank()) {
            throw new IllegalStateException(
                    "Missing payment merchant id");
        }
    }
}
~~~

This is an **illustrative snippet**, requiring the `PaymentSettings` class and imports for `Component`/`ApplicationRunner`/`ApplicationArguments`. If the merchant ID is an indispensable condition for the application to serve traffic, failing fast is reasonable. However, many simple configuration validations can be handled earlier using `@ConfigurationProperties` + Bean Validation; not every configuration requires a runner.

### 9.2. Bounded Warm-Up

A runner can invoke a service that populates a cache to reduce first-request latency:

~~~java
@Component
class CacheWarmupRunner implements CommandLineRunner {

    private final ReferenceCache cache;

    CacheWarmupRunner(ReferenceCache cache) {
        this.cache = cache;
    }

    @Override
    public void run(String... args) {
        cache.warmup();
    }
}
~~~

This is also illustrative code requiring a `ReferenceCache` definition. `warmup()` should have a time bound, resource bound, idempotency, and a clearly decided failure policy: *mandatory* to fail startup or *best effort* logging only a warning.

If warm-up can take several minutes, do not assume blocking readiness for a long time is always good; consider whether only an essential dataset is needed upfront or the rest can be warmed up in the background.

### 9.3. Parameterized CLI and Batch Jobs

For example, the same JAR supports:

~~~bash
java -jar app.jar --task=validate input.csv
java -jar app.jar --task=import input.csv
~~~

`ApplicationRunner` is convenient for parsing `--task=...` and positional input files. After the job finishes, the CLI application can close the context and return an appropriate exit code to the orchestrator.

If the application is a web server, the runner **does not automatically rerun each time** a user calls an import endpoint. To run batch jobs on a schedule or via a separate trigger, an appropriate API/job scheduler is needed.

### 9.4. Do Not Use Runners for One-Time Irrecoverable Operations

By default, runners run again every time **an instance restarts**. In Kubernetes, rolling updates or autoscaling can cause multiple instances to run the runner concurrently. Therefore:

- Do not charge payments, send emails, create orders, or mutate critical data expecting "exactly-once system-wide execution" solely via a runner.
- If data seeding is needed, use upserts/unique constraints/migration tools with idempotency.
- If a task must run on only one instance, design distributed locking, leader election, scheduled jobs, or an appropriate orchestration system.
- Do not use an in-memory flag in a single JVM as proof that a job has not run on another replica.

## 10. Impact on Readiness, Liveness, and Startup Timeouts

In Spring Boot 3.3, **liveness correct** comes after `ApplicationStartedEvent`, **before** runners; **readiness accepting traffic** comes after `ApplicationReadyEvent`, **after** runners succeed.

~~~text
Context refreshed
   |
ApplicationStartedEvent
   |
LivenessState.CORRECT
   |
+--- Runner 1: check configuration
+--- Runner 2: warm up data
+--- Runner 3: verify business preconditions
   |
ApplicationReadyEvent
   |
ReadinessState.ACCEPTING_TRAFFIC
~~~

While runners are still working, the application can be **live but not yet ready**. This is useful when configuring readiness probes for Kubernetes/load balancers.

However, a web server may already have bound its port during refresh before runners finish; if you call the URL directly without going through readiness/load balancing, you might still see a connection or some responses. Therefore, **"port open" does not mean "app ready."**

If a runner takes too long, a startup probe or deployment timeout can trigger a restart. Appropriate measures are measuring duration, trimming mandatory work, configuring timeouts with rationale, improving warm-up, and designing accurate readiness—not simply increasing timeouts indefinitely.

### When a Runner Throws an Error

An unhandled exception in `run(...)` is treated by Boot as a startup failure in the runners phase. The application may publish `ApplicationFailedEvent`, log failure analysis, and close the context along the failure path. `ApplicationReadyEvent` does not occur if startup fails before ready. However, side effects **already completed before throwing** in a DB/API/file are not automatically rolled back just because the context closes.

### When a Runner Spawns a Background Thread

Example:

~~~java
@Override
public void run(ApplicationArguments args) {
    executor.execute(this::warmupInBackground);
}
~~~

This is a non-standalone illustrative snippet, assuming an `executor` and a `warmupInBackground` method. `run` returns immediately after submitting the task; Boot can reach ready **before** warm-up completes. Only use this when the background work is not a condition blocking readiness, or you have another readiness mechanism reflecting actual state.

Do not spawn unmanaged threads on every startup and forget to clean them up on shutdown; use `TaskExecutor`/`SmartLifecycle` or a job/consumer mechanism with proper shutdown hooks.

## 11. Error Handling and Retry Policy

Runners are part of startup, so you must decide **which errors are fatal** and **which errors can be ignored**.

### Fatal Errors

If a mandatory condition is missing (for example, invalid minimal data schema, missing essential key, unable to verify safe configuration), you should usually:

1. Throw an exception with an **actionable** message that does not expose secrets.
2. Let startup fail so orchestration infrastructure reports the failure.
3. Have alerts/logs/metrics for the root cause.
4. Avoid advancing to ready when the application certainly cannot serve traffic properly.

### Retryable Errors

For temporarily unavailable external resources:

1. Set a timeout for each call attempt.
2. Use bounded retries, backoff, and jitter where appropriate.
3. Specify behavior after retries are exhausted: fail-fast or deliberate degradation.
4. Ensure retried operations are **idempotent**, avoiding duplicate data creation.
5. Do not use a `while(true)` loop with no deadline inside `run`.

### Best-Effort Errors

If a task is purely for convenience, such as preloading non-essential search suggestions, you can catch the error, log a warning, and let the application continue. However, do not log `READY` and assume warm-up certainly succeeded. Health/metrics should reflect actual status if it matters for operations.

A common poor design choice is catching `Exception`, calling `printStackTrace()`, and continuing in every case. That blurs the boundary between severe configuration errors and optional minor failures.

## 12. Testing Runners in Isolation from Full SpringApplication

Because both runners are ordinary Java classes, you can test their logic without booting the entire context by invoking `run` directly with controlled inputs.

Example **illustrating manual testing** of `OptionsRunner` with `DefaultApplicationArguments`:

~~~java
ApplicationArguments arguments = new DefaultApplicationArguments(
        "--mode=test",
        "--tag=a",
        "--tag=b",
        "sample.txt");

OptionsRunner runner = new OptionsRunner();
runner.run(arguments);
~~~

This snippet is not a standalone test file; it requires importing `org.springframework.boot.ApplicationArguments` and `org.springframework.boot.DefaultApplicationArguments`, and placing it in the project containing `OptionsRunner`. Expected lines from the runner:

~~~text
APP_RUNNER: mode=[test]
APP_RUNNER: tags=[a, b]
APP_RUNNER: nonOptions=[sample.txt]
~~~

Similarly, test `CommandLineRunner` by calling:

~~~java
new RawArgumentsRunner().run("--mode=test", "sample.txt");
~~~

Corresponding line:

~~~text
CMD_RUNNER: raw=[--mode=test, sample.txt]
~~~

Testing logic directly **does not test** whether Spring Boot invokes runners in lifecycle order. To test integration, run the SpringApplication context or use Spring Boot's testing utilities, verifying the milestones `ApplicationStartedEvent` → runner → `ApplicationReadyEvent` and startup failures as in the demo.

Avoid unit tests that rely purely on the ordering of all framework logs (since that depends on versions, configuration, and environment). You can use spies/recorded state/structured logs to assert which callbacks ran and important before-after relationships.

## 13. Common Pitfalls and Fixes

**1. "Runners execute as soon as the bean is created."** False. Constructors/`@PostConstruct` run during initialization; Boot calls `run` after refresh.

**2. "CommandLineRunner always runs after ApplicationRunner."** False. Both types belong to the same phase and are ordered by `@Order`/`Ordered`, not by interface name.

**3. "ApplicationRunner is just CommandLineRunner with a longer name."** False regarding input data. `ApplicationRunner` receives `ApplicationArguments` with parsed options/non-options; `CommandLineRunner` receives a raw string array. The lifecycle purpose is the same.

**4. "--dry-run=false means containsOption('dry-run') returns false."** False. `containsOption` checks presence; if a boolean value is needed, you must parse and validate it.

**5. "--mode demo is always equivalent to --mode=demo."** Do not rely on that. The standard valued option form is `--mode=demo`; a space can produce a separate non-option.

**6. "Runners rerun automatically on each request."** False. Runners run during `SpringApplication.run`; HTTP requests have their own lifecycle.

**7. "@DependsOn already guarantees run order."** `@DependsOn` concerns bean creation order; startup runner callback order uses `@Order`/`Ordered`.

**8. "A bean implementing both ApplicationRunner and CommandLineRunner only calls one run."** Not guaranteed; both callbacks have different signatures and both can be invoked. Avoid implementing both simultaneously if you want exactly one task.

**9. "A runner throws an error, yet Spring Boot still reports ready."** An unhandled error in a runner normally fails startup; the successful ready path does not continue.

**10. "Catching errors and just calling printStackTrace is safe."** For mandatory tasks, this allows the system to report ready when critical conditions are not met. You must define a failure policy aligned with business requirements.

**11. "Use a runner for cluster-wide once-only work."** Every instance can run the runner during its startup. System-wide single execution requires locking/coordination or an orchestrated job.

**12. "Use a runner to wait for an external system forever."** An infinite blocking loop can prevent readiness from ever being reached and trigger deployment timeouts. Use bounded timeouts/retries or design explicit degraded states.

**13. "Web port open means runners are done."** The port may bind before ready. Traffic-routing infrastructure should rely on proper readiness checks.

**14. "@ApplicationRunner is a method annotation."** There is no Boot annotation by that name for the standard callback: `ApplicationRunner` is an **interface**. To use a lambda, return the interface from a `@Bean`.

**15. "ApplicationArguments always auto-converts to the types the application needs."** It provides parsed strings, without validating all ranges, enums, or schemas. Convert/validate explicitly or use appropriate config binding.

**16. "A runner finishing means async tasks it submitted are complete."** False. If `run` only submits work, readiness can be reached while the background task is still running.

**17. "If startup fails, earlier operations roll back automatically."** Context cleanup does not automatically roll back every side effect outside a transaction. Idempotency, transaction boundaries, and recovery mechanisms are required.

**18. "Having a runner in a manually created context means it runs automatically."** Runner callbacks belong to `SpringApplication`. If you simply call `new AnnotationConfigApplicationContext(...)` or `refresh()` directly, Boot does not automatically run the entire runners phase in the same way.

## 14. Practice Exercises

1. Run the demo with `--mode=demo --tag=alpha --tag=beta job-42`. Record the order of the started event, the two runners, and the ready event.
2. Change `@Order(10)` on `OptionsRunner` to `@Order(30)`. Predict which runner runs first, then verify the output.
3. Remove `@Order` from both classes. Why should you not write tests based on the incidentally observed execution order?
4. Try `--dry-run`, `--dry-run=false`, and omitting `--dry-run`. Compare `containsOption`, `getOptionValues`, and the meaning of each result.
5. Try `--mode demo` instead of `--mode=demo`. Observe how options and non-options differ.
6. Try `--tag=a --tag=b --tag=c`. How many values can `ApplicationArguments` retrieve? How many raw tokens does `CommandLineRunner` see?
7. Add mandatory `--mode=...` validation to `OptionsRunner`. When the value is missing, which exception should be thrown and what should the error message contain?
8. Run `--fail-demo`. Why do `RawArgumentsRunner` and `ApplicationReadyEvent` not appear in the log?
9. Add another runner with `@Order(5)` to validate inputs. If it fails, do the remaining runners continue?
10. Add a `@PostConstruct` bean that logs. Compare when it runs against `ApplicationStartedEvent` and the two runners.
11. Try moving a warm-up from synchronous execution in `run` to submitting onto an executor. When does ready appear relative to when warm-up completes?
12. Suppose 3 replicas are running. If a runner inserts 100 seed records on every startup, what risk arises? Design an idempotent strategy.
13. With a web application, use a readiness probe to observe the window while a runner is executing. Why might you see the TCP port open while readiness is not yet accepting?
14. Write a unit test for `OptionsRunner` using `DefaultApplicationArguments` and assert an error when the required `--mode` is missing.
15. For a one-shot import job that runs once and exits, when should you use `SpringApplication.exit`/`ExitCodeGenerator` instead of treating it as a forever-running web server?
16. An optional notification task fails mid-startup. Should you fail startup or log a warning? State the criteria, timeouts, and operational observability approach.

## Key Takeaways

- `ApplicationRunner` and `CommandLineRunner` are **two Spring Boot callbacks** that run after `ApplicationContext.refresh()` but before `SpringApplication.run(...)` finishes and the application reaches ready.
- `ApplicationRunner` receives `ApplicationArguments` with options, non-options, and source arguments; `CommandLineRunner` receives raw `String... args`.
- Both runner types belong to the same phase; use `@Order`/`Ordered` when order matters.
- Runners are **context beans**; the `run` method is not auto-invoked merely by component scanning, and does not repeat on requests, timers, or messages.
- Synchronous runners block progression toward `ApplicationReadyEvent` until completion; throwing an unhandled exception normally fails startup.
- If a task is mandatory before ready, a runner may be suitable. If a task is long-lived background work, it needs its own lifecycle, timeouts, health, and management mechanisms.
- Spring events, readiness, and an open port are **different signals**. Do not treat liveness correct or a bound TCP port as proof that all runners have finished.
- Every replica/restart can re-execute startup runners: design idempotency and error handling based on real business requirements.

### References

- Spring Boot 3.3.13 — Using the ApplicationRunner or CommandLineRunner: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.command-line-runner
- Spring Boot 3.3.13 — ApplicationRunner Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html
- Spring Boot 3.3.13 — CommandLineRunner Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/CommandLineRunner.html
- Spring Boot 3.3.13 — ApplicationArguments Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html
- Spring Boot 3.3.13 — Application Events and Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Framework — Lifecycle Callbacks: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
