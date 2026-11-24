# Registering Runners Using @Component or @Bean Methods in Spring Boot

## 1. What Are Runners Used For?

In Spring Boot, a **runner** is a bean that the framework invokes once during the startup sequence of each `SpringApplication.run(...)` call that successfully reaches the runner invocation stage. Runners are well suited for tasks that must execute **after the `ApplicationContext` has been refreshed** and regular Spring dependencies are usable, yet **before the `ApplicationReadyEvent` milestone**.

Practical examples:

- Verifying mandatory data or configuration using a Spring-created service/repository.
- Loading a small amount of initial data or warming up a cache that must complete before the application is considered ready.
- Receiving command-line arguments for a one-off job (`--job=import`, filename, region code).
- Running a bounded-timeout connectivity check and reporting a clear error if the application does not meet startup requirements.

**The two common ways to register a runner** are annotating a class implementing the interface with `@Component`, or declaring a `@Bean` method returning an object implementing the interface. Both place the runner into the **Spring container**; Spring Boot collects runner beans in the context, sorts them if ordered, and calls them during startup.

Key point: Spring Boot does not require the bean name to be `runner`, does not require placing runner code inside the `main` class, and does not automatically scan every Java class implementing the interface. **The object must actually be registered as a bean in the starting context.**

## 2. Where Are Runners Called in the Startup Sequence?

Simplified timeline of Spring Boot 3.3:

```text
SpringApplication.run(args)
         |
Prepare Environment and create ApplicationContext
         |
Load configuration, create beans, refresh context
         |
ApplicationStartedEvent
         |
LivenessState.CORRECT (default sequence)
         |
+--------------------------------------------+
| Spring Boot locates runner beans           |
|  - ApplicationRunner                       |
|  - CommandLineRunner                       |
| Sort by order, then invoke run(...)        |
+--------------------------------------------+
         |
ApplicationReadyEvent
         |
ReadinessState.ACCEPTING_TRAFFIC (default)
         |
SpringApplication.run(...) returns context
         |
Application continues running or exits
```

`ApplicationStartedEvent` arrives **before runners**; `ApplicationReadyEvent` arrives **after runners complete successfully**. Hence a failing runner can prevent the application from reaching Ready. The familiar log line `Started MyApplication in ... seconds` typically reflects the *started* milestone; **it does not prove that runners have finished**.

This is an **application lifecycle** boundary, not a guarantee that the web server has not yet opened its socket. In a Servlet/Reactive application, the web server may already have been initialized before runners run. If a runner performs work critical to data safety, coordinate with readiness probes and deployment traffic-routing policies rather than trusting log order alone.

Runners execute within the `SpringApplication.run(...)` bootstrap call, normally on the startup thread and synchronously. A long-waiting runner task prolongs the time to Ready; it is not a periodic scheduling mechanism.

## 3. Two Interfaces: ApplicationRunner and CommandLineRunner

Spring Boot provides two simple interfaces:

```java
package org.springframework.boot;

// Core signatures, simplified for illustration:
@FunctionalInterface
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}

@FunctionalInterface
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
```

The snippet above is a **signature outline**, not a file to copy into your project: both interfaces already exist in the Spring Boot library, and actual declarations may carry additional API details.

The difference is the **input argument type**:

| Criterion | `ApplicationRunner` | `CommandLineRunner` |
|---|---|---|
| Method | `run(ApplicationArguments args)` | `run(String... args)` |
| Reading named arguments | `getOptionNames()`, `containsOption()`, `getOptionValues()` | Parse strings manually or use a suitable parser |
| Reading unnamed arguments | `getNonOptionArgs()` | Receive raw strings in `args` |
| Accessing raw arguments | `getSourceArgs()` | The `String... args` array itself |
| Best suited for | Apps handling flags/options like `--name=Lan` | Simple logic or needing the verbatim argument list |
| Registration options | `@Component` or `@Bean` | `@Component` or `@Bean` |

Launch example:

```bash
java -jar app.jar --name=Lan --mode=demo file-a.csv
```

In `ApplicationRunner`, you can read:

```java
String name = arguments.getOptionValues("name").get(0);
String mode = arguments.getOptionValues("mode").get(0);
String file = arguments.getNonOptionArgs().get(0);
```

With `CommandLineRunner`, you receive the equivalent string array:

```text
[--name=Lan, --mode=demo, file-a.csv]
```

**Do not blindly call** `getOptionValues("name").get(0)` in production code without checking that the option exists and has a value: `getOptionValues` can return `null` when the option is absent, or a list with no matching element. A safe example is shown in section 6.

Additional note: arguments used to configure Spring Boot such as `--spring.profiles.active=dev` are also present in the launch arguments if the user passed them to `main`. Therefore, do not dump all arguments into production logs when they might contain passwords, tokens, or sensitive data.

## 4. Approach A: Registering a Runner with @Component

This is easy to read when startup work has its own responsibility and should be organized into a class:

```java
package com.example.runner;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class StartupCheckRunner implements ApplicationRunner {

    private final CatalogService catalogService;

    public StartupCheckRunner(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @Override
    public void run(ApplicationArguments arguments) {
        catalogService.checkRequiredData();
    }
}
```

The snippet above **illustrates the implementation pattern**; `CatalogService` and `checkRequiredData()` must exist in the project. Spring creates `StartupCheckRunner` as a bean thanks to `@Component`, locates the `CatalogService` dependency, calls the constructor to inject it, and Spring Boot then recognizes that this bean implements `ApplicationRunner`.

**Key conditions:**

1. The class must lie within **component scan** scope, e.g., the same package or a subpackage of the default `@SpringBootApplication` class.
2. The project must have the appropriate Spring Boot dependency, and startup must go through `SpringApplication.run(...)`.
3. Constructor dependencies must resolve successfully. If the `CatalogService` bean is missing or ambiguous, the context may fail to initialize and the runner will not be called.
4. There is no need to annotate the `run` method with `@Bean` or `@PostConstruct`. The object itself is the runner bean, while `run` is invoked by Boot at the right stage.

### 4.1. CommandLineRunner with @Component Is Equally Valid

```java
package com.example.runner;

import java.util.Arrays;

import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class EchoArgumentsRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Arguments: " + Arrays.toString(args));
    }
}
```

If the project contains both `StartupCheckRunner` and `EchoArgumentsRunner` as two beans, **both** are called by Spring Boot during a normal startup. They are **not** mutually exclusive registration approaches that cancel each other out.

### 4.2. Strengths and Limitations of @Component

- Clear class definition; suitable when logic has multiple branches, requires multiple dependencies, and has its own unit tests.
- Constructor injection keeps dependencies transparent, with final fields fully initialized.
- Supports `@Profile`, `@ConditionalOnProperty` (when conditions/scope fit), `@Order`, or implementing `Ordered`.
- Limitation: the class must be component-scanned and registered exactly once; unsuitable when the class lives outside your source or in a library whose annotations you cannot edit.

Avoid using `@Component` solely to hold a few lines of a lambda if doing so clutters the repository with too many tiny classes. `@Bean` is often cleaner when the task is brief and belongs to a module's configuration.

## 5. Approach B: Registering a Runner with a @Bean Method

You do not need a separate implementation class if you only want a small callback. Place a `@Bean` method inside a `@Configuration` or `@SpringBootApplication` class:

```java
package com.example.runner;

import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class StartupTasksConfiguration {

    @Bean
    CommandLineRunner printStartupMessage() {
        return args -> System.out.println("Startup task executed");
    }
}
```

When the context is created:

1. Spring processes `StartupTasksConfiguration`.
2. Spring calls the matching bean factory method and **registers the returned lambda object** as a bean of type `CommandLineRunner`.
3. Spring Boot finds this bean in the context.
4. Boot calls the bean's `run(String... args)` **after context refresh and before Ready**.

**Spring calls the `@Bean` method to create the bean; Boot calls `run(...)` when the runners phase arrives.** Those two calls are distinct and should not be confused. With the default singleton scope, the factory method runs when Spring creates the bean, whereas the `run` callback is called once during that context's normal startup.

### 5.1. Injecting Services via @Bean Method Parameters

```java
@Configuration
public class StartupTasksConfiguration {

    @Bean
    CommandLineRunner warmup(CacheService cacheService) {
        return args -> cacheService.loadInitialKeys();
    }
}
```

This is **integration illustration** code requiring a real `CacheService`. Spring resolves `CacheService` at bean creation time, and the lambda object holds this reference for use **when the runner is invoked**.

Do not call:

```java
// Do not call manually in main:
warmup(cacheService).run(args);
```

If you call `run(...)` yourself while also registering the runner bean, the task may execute **twice** (once by you, once by Boot). Furthermore, a `@Bean` method in a configuration class is not designed to accept arbitrary arguments from `main` like an ordinary Java function.

### 5.2. @Bean Can Also Return ApplicationRunner

```java
@Bean
ApplicationRunner validateArguments() {
    return arguments -> {
        if (arguments.containsOption("mode")) {
            System.out.println(
                    "Mode: " + arguments.getOptionValues("mode"));
        }
    };
}
```

This is a method added to a `@Configuration` class, not a standalone runnable Java file. Because `ApplicationRunner` is a functional interface, a Java lambda satisfies it.

### 5.3. When to Use @Bean

Choose `@Bean` when:

- You want to place a short startup task right alongside related configuration beans.
- You need to turn a library object **whose class you cannot modify** into a runner bean.
- You need to construct a runner based on factory parameters, feature flags, or other beans.
- You want to control whether the runner bean is created at the `@Bean` method level.

For lengthy logic, do not cram hundreds of lines of business logic into a lambda. Place the business logic in an independently testable service, and let the lambda serve as the startup-milestone caller.

## 6. Complete Example: One @Component ApplicationRunner and One @Bean CommandLineRunner

This example uses Spring Boot **3.3.x**, **Java 17+**, Gradle Groovy DSL, and requires no web server. We intentionally register **both** runners to demonstrate that both registration approaches work together, can be sorted with `Ordered`, and can access Spring services after context refresh.

### 6.1. Project Structure

```text
runner-registration-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/runnerdemo/
    ├── RunnerRegistrationApplication.java
    ├── GreetingService.java
    └── ComponentStartupRunner.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'runner-registration-demo'
```

**`build.gradle`:**

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

The project can be initialized with Spring Initializr selecting Gradle to obtain the **Gradle Wrapper** files out of the box. If you create the three files above manually, install Gradle or generate a compatible wrapper before running `./gradlew`/`gradlew.bat`. Spring Boot 3.3 requires Java 17 or newer; the example uses Java 17.

### 6.2. Shared Service

**`src/main/java/com/example/runnerdemo/GreetingService.java`:**

```java
package com.example.runnerdemo;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String greet(String name) {
        return "Hello " + name;
    }
}
```

`@Service` is a Spring component stereotype. Because the class is in the same package as the main class, `@SpringBootApplication`'s default component scan detects it.

### 6.3. @Component ApplicationRunner: Reading Named Options

**`src/main/java/com/example/runnerdemo/ComponentStartupRunner.java`:**

```java
package com.example.runnerdemo;

import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;

@Component
public class ComponentStartupRunner implements ApplicationRunner, Ordered {

    private final GreetingService greetingService;

    public ComponentStartupRunner(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void run(ApplicationArguments arguments) {
        List<String> values = arguments.getOptionValues("name");

        String name = (values == null || values.isEmpty())
                ? "friend" : values.get(0);

        System.out.println(
                "1. @Component ApplicationRunner: "
                + greetingService.greet(name));

        System.out.println(
                "1. Option names: " + arguments.getOptionNames());

        System.out.println(
                "1. Non-option args: " + arguments.getNonOptionArgs());

        if (arguments.containsOption("demo.fail")) {
            throw new IllegalStateException("Demo runner failure");
        }
    }
}
```

Points to understand:

- `@Component` turns the class into a runner bean.
- The constructor receives a Spring-managed `GreetingService`; no need to instantiate it with `new`.
- `ApplicationArguments` distinguishes `--name=Lan` from a positional argument like `job-a`.
- `getOptionValues("name")` is checked for `null` and empty before accessing an element, falling back to `friend`.
- `Ordered.getOrder() = 10` requests higher priority than the runner with order 20 in the example.
- `--demo.fail` is an intentional failure-testing option, not a special Spring Boot property.

### 6.4. @Bean CommandLineRunner: Receiving Raw Strings

**`src/main/java/com/example/runnerdemo/RunnerRegistrationApplication.java`:**

```java
package com.example.runnerdemo;

import java.util.Arrays;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.core.Ordered;

@SpringBootApplication
public class RunnerRegistrationApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(RunnerRegistrationApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context =
                application.run(args)) {
            // Context closes after runners and ReadyEvent complete.
        }
    }

    @Bean
    CommandLineRunner beanStartupRunner(GreetingService greetingService) {
        return new OrderedBeanStartupRunner(greetingService);
    }

    @EventListener(ApplicationStartedEvent.class)
    public void onStarted() {
        System.out.println("0. ApplicationStartedEvent");
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("3. ApplicationReadyEvent");
    }

    // Implementation dedicated solely to the bean created by the @Bean factory.
    static final class OrderedBeanStartupRunner
            implements CommandLineRunner, Ordered {

        private final GreetingService greetingService;

        OrderedBeanStartupRunner(GreetingService greetingService) {
            this.greetingService = greetingService;
        }

        @Override
        public int getOrder() {
            return 20;
        }

        @Override
        public void run(String... args) {
            System.out.println(
                    "2. @Bean CommandLineRunner: "
                    + greetingService.greet("team"));

            System.out.println(
                    "2. Raw args: " + Arrays.toString(args));
        }
    }
}
```

Why is this approach appropriate?

- `@SpringBootApplication` includes the required configuration/scanning mechanism. The `@Bean` method inside this class is processed as a factory method.
- `beanStartupRunner(GreetingService ...)` receives the service bean via Spring method-parameter injection.
- The returned object implements `CommandLineRunner`, so Spring Boot recognizes it as a runner.
- The implementation also implements `Ordered` and returns 20. It runs **after** the `@Component` runner with order 10 in the same sorted list.
- `@EventListener` in the configuration class observes Started/Ready because listener beans have already been initialized in the context by then.
- `WebApplicationType.NONE` ensures the example does not start an HTTP server and does not depend on a server port.

**Do not call `new OrderedBeanStartupRunner(...).run(...)` in `main`.** Doing so bypasses container dependency resolution and increases the risk of executing the task twice.

### 6.5. Running and Verifying Results

In a project that includes the Gradle Wrapper:

```bash
./gradlew bootRun --args='--name=Lan job-a'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--name=Lan job-a"
```

Spring Boot or Gradle banners/logs may appear interleaved in stdout. **The lines printed by the example source itself** follow this order when arguments are properly passed to the application:

```text
0. ApplicationStartedEvent
1. @Component ApplicationRunner: Hello Lan
1. Option names: [name]
1. Non-option args: [job-a]
2. @Bean CommandLineRunner: Hello team
2. Raw args: [--name=Lan, job-a]
3. ApplicationReadyEvent
```

This is the expected output for **this exact example** with one `name` option and one positional argument; the order of elements inside a multi-element option-names set should not be relied upon as a logging contract. With standard classpath/configuration, runners are sorted by `Ordered` and the Started/Ready events appear on either side of the runners.

You can try running again without passing arguments:

```bash
./gradlew bootRun
```

In that case `ComponentStartupRunner` falls back to `friend`, `Option names` and `Non-option args` are empty sets/lists, and `BeanStartupRunner` receives an empty arguments array.

### 6.6. Running the Intentional Failure Path

```bash
./gradlew bootRun --args='--demo.fail'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--demo.fail"
```

After printing the first runner's lines, `ComponentStartupRunner` throws `IllegalStateException`. In this scenario:

1. The context refreshed and `ApplicationStartedEvent` was published.
2. The order-10 runner started and failed.
3. The order-20 runner **is not called** because Boot does not continue the runner chain after this exception.
4. `ApplicationReadyEvent` **is not published** for the failed startup attempt.
5. Spring Boot handles the startup failure, logs the exception, and may publish `ApplicationFailedEvent`; the Gradle task typically reports failure.

The order is predictable based on `Ordered`, independent of one bean being declared with `@Component` and the other with `@Bean`. The error clearly illustrates the impact of an unsuccessful runner on the entire startup.

## 7. Choosing @Component or @Bean in a Real Project?

| Criterion | `@Component` on runner class | `@Bean` factory method |
|---|---|---|
| Where registered | On the class implementing `ApplicationRunner`/`CommandLineRunner` | Inside `@Configuration` or `@SpringBootApplication` |
| How Spring creates it | Component scan discovers and instantiates the class | Spring processes the factory method to obtain an instance |
| Logic organization | Often convenient for long/standalone tasks | Concise for short callbacks or module configuration |
| Dependency injection | Constructor/field/setter as supported by Spring; prefer constructor | `@Bean` method parameters, or the returned class holds dependencies |
| Unmodifiable library class | Difficult to use `@Component` if annotations cannot be added | Can build an adapter/return an instance from the factory |
| Environment toggling | `@Profile`/`@Conditional...` on the class | `@Profile`/`@Conditional...` on the method |
| Runner ordering | `@Order` or `Ordered` on the object | `Ordered` on returned instance or design class with appropriate `@Order` |
| When multiple runners coexist | All matching beans can be invoked | All matching beans can be invoked |

**There is no default preference that "`@Component` always runs before `@Bean`."** Spring Boot does not prioritize order by declaration style. If multiple runners have ordering dependencies, specify the order with `Ordered`/`@Order` and verify the result. Runners sharing the same priority level should not be used as a pipeline relying on incidental order.

Signs you should extract a `@Component` class: the runner has many dependencies, needs dedicated error handling, has multiple processing steps, or needs dedicated tests. Signs you should use `@Bean`: the callback merely invokes a service and module configuration is clearer when kept together.

In many architectures, the optimal approach is keeping **the real logic in a service**, while the runner (whether using `@Component` or `@Bean`) acts purely as an adapter for the startup milestone.

## 8. Ordering Multiple Runners: @Order, Ordered, and Dependencies

Spring Boot can discover **multiple `ApplicationRunner` and `CommandLineRunner` beans** in the same context. Runners are passed into the sorting mechanism, so both interfaces **can be sorted together by order**—not all ApplicationRunners necessarily run before all CommandLineRunners.

Example with `@Component`:

```java
@Component
@Order(10)
public class FirstRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        System.out.println("First");
    }
}
```

And:

```java
@Component
@Order(20)
public class SecondRunner implements CommandLineRunner {
    @Override
    public void run(String... args) {
        System.out.println("Second");
    }
}
```

These are **two illustrative classes**, requiring the corresponding Spring Boot/Spring Core imports and placement in a component-scanned project. With values 10 and 20, the order-10 runner is prioritized ahead of order 20. **Smaller order values mean higher priority**.

Besides `@Order`, a class can implement `org.springframework.core.Ordered` as shown in section 6:

```java
@Override
public int getOrder() {
    return 10;
}
```

**Note on `@Bean` lambdas:** if you want truly stable and verifiable ordering, section 6's example returns an `Ordered` implementation rather than relying on the incidental order of two bean factory methods. What matters is that the runner bean **received by Boot** carries the appropriate metadata/order for the sorter to use.

Do not use order as a substitute for dependency design. If task B **must** use the result of A, consider an explicit orchestrating service calling `A` then `B` inside **a single runner**, instead of relying on two separate runners and enforcing order solely with a number. This reduces bugs when someone adds a new runner or changes registration conditions.

## 9. Enabling/Disabling Runners by Profile or Property

Runners can easily execute **unintentionally** if the scanned class or `@Bean` method is always active. For data-import, index-refresh, or maintenance tasks, specify clearly when the runner should exist.

### 9.1. @Profile on a Runner Class

```java
@Component
@Profile("seed")
public class SeedDataRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Seed mode");
    }
}
```

This is an illustrative class requiring appropriate imports and project setup. Only when the `seed` profile is active does Spring create this component as a bean. One way to enable the profile at launch:

```bash
./gradlew bootRun --args='--spring.profiles.active=seed'
```

Note: profiles also affect other profile-conditioned beans, not just runners. Do not use a global profile if the actual need is only a small feature flag and you do not want to alter broader environment configuration.

### 9.2. @ConditionalOnProperty on a @Bean Method

```java
@Configuration
public class OptionalStartupConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo",
            name = "startup-check-enabled",
            havingValue = "true")
    CommandLineRunner optionalCheck(HealthCheckService healthCheckService) {
        return args -> healthCheckService.verify();
    }
}
```

This is an **integration illustration** snippet: it requires a real `HealthCheckService` and imports for `@Configuration`, `@Bean`, `@ConditionalOnProperty`, and `CommandLineRunner`. When `demo.startup-check-enabled=true`, Spring creates the runner bean; when false or absent (under default condition settings), this runner is not registered. To enable at runtime:

```bash
./gradlew bootRun --args='--demo.startup-check-enabled=true'
```

**Difference between "not registering the runner" and "runner exists but skips itself":** with `@ConditionalOnProperty`, the BeanDefinition can be skipped conditionally, so the runner is absent from Boot's invocation list. If the runner is always present and checks a flag inside `run`, all of the runner's dependencies may still be instantiated even when the flag is false. Choose the right approach based on initialization cost and condition semantics.

### 9.3. Be Careful with Property Names

Do not confuse `spring.main.web-application-type` (Web type) with application-defined flags like `demo.startup-check-enabled`. Custom flags only take effect if configuration code reads/applies them. Using a dedicated prefix and documenting defaults helps operators avoid triggering tasks unintentionally.

## 10. Runners and Bean Lifecycle: Non-Interchangeable Milestones

Comparing common extension points:

| Mechanism | When It Runs | Injected Services Available? | Purpose |
|---|---|---|---|
| `@PostConstruct` | During initialization of **that specific bean** | The bean's dependencies are generally injected | Prepare the bean's internal state |
| `SmartInitializingSingleton.afterSingletonsInstantiated()` | After non-lazy singletons are created in the corresponding init cycle | Core non-lazy singletons are initialized | Coordinate tasks after singleton creation, not automatically Ready |
| `ApplicationStartedEvent` | After refresh, **before runners** | Context refreshed; regular beans usable | Observe the started milestone |
| `ApplicationRunner` / `CommandLineRunner` | After Started, before Ready | Regular beans usable | Initialization/checks that must finish before Ready |
| `ApplicationReadyEvent` | After runners | Created beans usable | Observe startup-chain completion, signal operational readiness |
| `@Scheduled` | On schedule after scheduling infrastructure is configured | Spring-managed beans available | **Scheduled repeating** tasks, not one-off startup tasks |

A runner class may have `@PostConstruct`. In that case:

1. Spring instantiates the runner.
2. Runs `@PostConstruct` during the bean lifecycle.
3. After context refresh, Boot calls `runner.run(...)`.
4. Once all runners finish, Boot advances to Ready.

Do not have `@PostConstruct` call `run(...)` itself. Doing so can duplicate business work, lack arguments, or run at an inappropriate time.

### Special Case: Lazy Initialization

With lazy beans, not every application bean has already been instantiated before `ApplicationStartedEvent`. However, a runner bean must be created by the container before Boot can call its `run`; its required dependencies will be resolved according to container rules. Thus the runner using a service in the example will work, yet you must not infer that **every lazy bean across the entire application** already exists.

## 11. Runners, Web Server, and Readiness in Deployment

Spring Boot documentation describes runners as tools for tasks that run after the application has started and before the system is ready to serve traffic. Understand how this plays out in practice:

- A Servlet or Reactive web server may be initialized and begin listening on its port **before** runners finish.
- `ApplicationReadyEvent` marks the milestone after runners; afterward, Spring Boot publishes `ReadinessState.ACCEPTING_TRAFFIC` in the default flow.
- A load balancer or Kubernetes can rely on readiness probes to decide when to send traffic; however, that depends on probe configuration, not solely on Spring Boot events.
- Slow runners can push startup duration beyond orchestrator limits. When tasks are long, consider moving them to a separate Job, migration tool, background worker, or a design that does not force the whole application to wait.

Example: loading 50,000 rows from an external service in a runner as every replica boots can cause a load storm on the database. A safer approach is running controlled one-time migration/seeding with idempotency and appropriate permissions, letting replicas boot fast.

**Runners are not a distributed lock.** When there are three replicas, each `SpringApplication.run(...)` instance calls its own runner bean. If the runner mutates shared data, you must account for contention and re-execution across instances.

## 12. Handling Runner Errors Properly

`run(...)` in both interfaces is allowed to throw `Exception`. If a runner throws an unhandled error, Spring Boot treats it as a failure in the startup sequence and may close the context / record a startup failure. Thus failure blocks Ready for that launch.

Consider categorizing errors:

- **Unacceptable errors for serving:** missing required config, incompatible schema, missing critical initial data. You can proactively **fail fast** with a clear exception.
- **Transient errors:** network timeout, another service not ready yet. If retries are needed, include a time bound, backoff, and interruption handling; never retry indefinitely inside a runner.
- **Optional work:** non-essential cache warming. You can log a warning and continue, while being clear about the impact and never swallowing critical data errors.

Fail-fast example in `ApplicationRunner`:

```java
@Override
public void run(ApplicationArguments args) throws Exception {
    if (!requiredDataExists()) {
        throw new IllegalStateException(
                "Required data does not exist");
    }
}
```

This is an **illustrative snippet**, requiring a real `requiredDataExists()` method in the runner class. Do not copy it into a program lacking that method and treat it as complete runnable code.

### Idempotency Across Restarts

Runners are not a migration/versioning system. If writing data at startup, ensure re-running after a restart does not duplicate records or corrupt state. For instance, create seed data using unique-key checks, valid upserts, or a dedicated migration tool depending on purpose.

During a rolling update deployment, multiple old and new version instances may run simultaneously. A runner modifying schema on every instance can cause contention; separate migration responsibilities from routine startup if there is risk.

### Overly Long Tasks

Do not put an infinite loop inside a Web service's `CommandLineRunner` and expect Ready, because the entire startup sequence may never finish. If the application is a one-shot batch processor, using `WebApplicationType.NONE` and a synchronous runner is appropriate; if it is a long-running service, consider proper scheduling/message-consumer/lifecycle infrastructure.

## 13. Common Mistakes When Registering Runners

| Symptom | Common Cause | How to Check or Fix |
|---|---|---|
| Class implements `ApplicationRunner` yet does not run | Missing `@Component`, outside component scan, missing `@Bean`, or disabled by condition | Verify the bean is actually registered in the context |
| Using `@Component` yet application fails to start | Runner needs a nonexistent dependency or multiple beans match the type | Read the root cause of the dependency injection exception |
| `@Bean` method returns `void` so it does not become a runner | Does not return a runner-implementing instance | Define a bean of type `CommandLineRunner`/`ApplicationRunner` and return a valid instance |
| `@Bean` method creates a lambda yet no log appears | `@Configuration` class not imported/scanned or condition unmet | Check the configuration holding the method and active profiles |
| Task runs twice | Both `@Component` and `@Bean` runners exist for the same job, or `run` called manually | Keep only one registration per task, avoid calling callback manually |
| Want A before B yet order is reversed | Order unspecified or identical order | Use `@Order`/`Ordered`, or combine into one orchestrating runner |
| Reading `--name=Lan` directly as a positional argument | Confusing `CommandLineRunner` and `ApplicationRunner` argument parsing | Use `ApplicationArguments.getOptionValues("name")` when options are needed |
| `getOptionValues("name").get(0)` throws an error | Option missing or has no value | Check `null` and empty list before indexing |
| App logs `Started` then never reaches Ready | Runner threw an exception or is still executing | Inspect runner logs, stack traces, wait durations, and timeouts |
| Web server serves HTTP while runner is not finished | Socket opens before the Ready event | Use readiness probes and proper routing |
| Restarts create duplicate data | Runner writes non-idempotent data | Design operations safe for repeated runs and multiple instances |
| Using `@PostConstruct` instead of a runner to call multiple services | Per-bean hook runs before whole-context milestones, hard to coordinate | Use a runner for business logic requiring a refreshed context |
| Trying to use a runner as a scheduler | Runners execute during startup, not every minute/hour | Use `@Scheduled` when periodic execution is actually needed |
| Trying to put `@Bean` on the `run` method | Confusing bean factory with runner callback | Declare a `@Bean` method **returning** the runner, not annotating `run` directly |
| Adding `@Order` to configuration class yet runner order stays wrong | Ordered the wrong object/metadata | Put order on the actual runner bean/instance and verify via logs |

Do not jump to "`@Bean` doesn't work" simply because no runner log appeared if the application actually **failed before the runner invocation stage**. Determine whether context refresh succeeded, whether Started fired, whether the bean exists, and which error occurred first.

## 14. Verification Through Hands-On Exercises

### Exercise A — Confirm Both Registration Methods

Run the section 6 project with `--name=Lan job-a`. Verify:

1. `ApplicationStartedEvent` appears before both runners.
2. `@Component ApplicationRunner` reads option `name` and positional `job-a`.
3. `@Bean CommandLineRunner` receives the raw arguments array.
4. `@Component` order 10 runs before `@Bean` order 20.
5. `ApplicationReadyEvent` appears after both runners.

### Exercise B — Remove @Component, Verify Bean Discovery

Temporarily remove `@Component` from `ComponentStartupRunner` and run again. The class still compiles, yet is not registered as a runner by component scanning; `@Bean CommandLineRunner` still exists and gets invoked. Restore the annotation after observing.

### Exercise C — Remove the @Bean Method

Temporarily remove `@Bean` from `beanStartupRunner(...)` or remove that method while practicing (avoiding leftover unused dependencies). When run, `ComponentStartupRunner` still works; the second bean is no longer invoked automatically by Spring Boot. Restore the configuration after testing.

### Exercise D — Change Order

Change `ComponentStartupRunner`'s `getOrder()` from 10 to 30 while keeping `OrderedBeanStartupRunner` at 20. Observe the runner lines swap order, while Started remains before and Ready remains after. Do not change order at the same time as changing logic so the cause stays clear.

### Exercise E — Startup Failure Blocks Ready

Run `--demo.fail` per section 6. Check that the exception originates from the runner, the order-20 runner is not called, and `ApplicationReadyEvent` does not appear. Explain why failing after `ApplicationStartedEvent` is still a startup failure.

### Exercise F — Place a Runner Under an Optional Profile

Move an experimental runner to the `seed` profile. Run both with and without `--spring.profiles.active=seed`. Observe whether the bean is registered. Before using in a real environment, clearly specify what data the runner will write and its re-run conditions.

### Exercise G — Add Timing Measurement

Add a synchronous task timed with `System.nanoTime()` inside a runner. Compare `ApplicationStartedEvent` and `ApplicationReadyEvent` timestamps to see the runner extend the time to Ready. Do not use the `Started ... in` seconds number as proof that runners finished.

### Self-Assessment Questions

1. Why do two classes both implementing `CommandLineRunner` result in only the bean-registered class running?
2. What is the difference between Spring calling the `@Bean` factory method and Spring Boot calling `runner.run(...)`?
3. Can a `@Component ApplicationRunner` and a `@Bean CommandLineRunner` work together in one context?
4. How do you guarantee order between two runners? Is default order based on `@Component` versus `@Bean`?
5. If you need to read `--name=Lan`, which interface should you pick and how should you check for a missing option?
6. Why is a runner a sensible place for pre-Ready checks, yet not a scheduler?
7. Why do runners with side effects need to be designed idempotently across restarts or multiple replicas?

Being able to answer these questions and prove them with logs in the hands-on project means you understand both **how runners are registered** and **their lifecycle contract**.

## 15. Selection Summary

**Choose `@Component`** if you want a dedicated runner class that is easy to unit test and has explicit constructor injection. **Choose `@Bean`** when you want a concise callback or want to create a runner from existing module configuration. Both approaches **place an instance implementing `ApplicationRunner` or `CommandLineRunner` into the container**, with no inherent priority based on declaration style.

When multiple runners exist, use `Ordered`/`@Order` to state order clearly, or consolidate tightly coupled logic into a single orchestrating runner. When a runner fails, the startup sequence can halt before Ready. Therefore, consider timeouts, argument security, idempotency, and multiple instances starting concurrently.

## Official Documentation for Reference

- Spring Boot 3.3, `SpringApplication`, *Using the ApplicationRunner or CommandLineRunner* section: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3, `ApplicationRunner` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html
- Spring Boot 3.3, `CommandLineRunner` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/CommandLineRunner.html
- Spring Boot 3.3, `ApplicationArguments` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html
- Spring Framework, `@Bean` and `@Configuration`: https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html

**Technical conclusion:** a runner is a **startup bean** invoked by Spring Boot after the context has refreshed and before the application is ready. `@Component` and `@Bean` differ only in **how the runner is placed into the container**; when and under what conditions Boot invokes the runner depends on the interface, configured order, and startup success.