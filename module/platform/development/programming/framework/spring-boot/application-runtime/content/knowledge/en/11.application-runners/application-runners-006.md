# Shared Ordering When Both ApplicationRunner and CommandLineRunner Are Present in Spring Boot

## 1. Core Answer

In Spring Boot, `ApplicationRunner` and `CommandLineRunner` are both startup callbacks invoked **after the `ApplicationContext` has refreshed successfully, yet before `SpringApplication.run(...)` finishes**.

When **the same application has beans of both interfaces**, Spring Boot **does not apply a mandatory rule of "run all `ApplicationRunner`s first, then run `CommandLineRunner`s."** Instead, both groups of runners participate in **one shared ordering**, controllable via:

- `org.springframework.core.annotation.Order`: the `@Order(n)` annotation on the runner class.
- `org.springframework.core.Ordered`: the interface allowing a bean to supply an order value via `getOrder()`.

**Smaller order values run first**; larger values run later, regardless of whether the bean implements `ApplicationRunner` or `CommandLineRunner`.

Example with four beans:

| Bean | Interface | Order Value | Invocation Position |
| --- | --- | ---: | ---: |
| `prepareRunner` | `CommandLineRunner` | 10 | 1 |
| `loadRunner` | `ApplicationRunner` | 20 | 2 |
| `verifyRunner` | `CommandLineRunner` | 30 | 3 |
| `reportRunner` | `ApplicationRunner` | 40 | 4 |

The order will be:

```text
CommandLineRunner (10)
        ↓
ApplicationRunner (20)
        ↓
CommandLineRunner (30)
        ↓
ApplicationRunner (40)
        ↓
ApplicationReadyEvent
```

**There are not two separate queues by runner type**. The order in the example results from the order values—not interface names, bean names, filenames, or method declaration positions.

> Scope: This lesson describes Spring Boot 3.3.x / Spring Framework 6.x with Java 17 or newer and the normal `SpringApplication` startup flow. The APIs and ordering principles are documented in Spring Boot's reference; when upgrading major versions, re-verify the Javadocs and test behavior.

## 2. How Are the Two Interfaces Similar and Different?

Both interfaces have a single `run` method, differing in parameter type:

```java
// Spring Boot API, simplified for comparison:
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}

public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
```

These are **illustrative signatures**, not two files your application should redefine. Import the built-in interfaces from `org.springframework.boot`.

| Aspect | `CommandLineRunner` | `ApplicationRunner` |
| --- | --- | --- |
| Callback method | `run(String... args)` | `run(ApplicationArguments args)` |
| Input data | Raw string array of arguments from `main` | Spring Boot's parsed arguments object |
| Reading option `--mode=demo` | Parse strings manually or use another API | `containsOption("mode")`, `getOptionValues("mode")` |
| Reading positional arguments | Inspect `args` manually | `getNonOptionArgs()` |
| Registration | Spring bean, typically `@Component` or `@Bean` | Spring bean, typically `@Component` or `@Bean` |
| Invocation timing | Runners phase after refresh | Same runners phase after refresh |
| Order control | `@Order` or `Ordered` | Same `@Order` or `Ordered` mechanism |

**Neither interface is inherently "higher priority" so as to run first.** Choose `ApplicationRunner` when you need categorized argument access; choose `CommandLineRunner` when you want the raw argument array, write a small command, or already have an API accepting `String[]`.

Example receiving arguments:

```bash
java -jar app.jar --mode=demo report.csv
```

At runtime:

- With `CommandLineRunner`, `args` essentially contains `"--mode=demo"` and `"report.csv"`.
- With `ApplicationRunner`, `args.containsOption("mode")` is `true`, `args.getOptionValues("mode")` contains `"demo"`, and `args.getNonOptionArgs()` contains `"report.csv"`.
- `ApplicationArguments.getSourceArgs()` still lets you retrieve the original raw argument array.

This example is an illustrative command requiring the corresponding JAR file. Do not confuse `ApplicationArguments` with `Environment`: exposing a command-line option in property sources is a separate Spring Boot configuration mechanism.

## 3. When Does SpringApplication Process Runners?

Abbreviated startup flow:

```text
SpringApplication.run(...)
    |
    +-- Prepare Environment
    +-- Create ApplicationContext
    +-- Register bean definitions and refresh context
    |      +-- instantiate matching non-lazy singletons
    |      +-- execute bean initialization callbacks
    |
    +-- ApplicationStartedEvent
    |      (context refreshed, runners not yet executed)
    |
    +-- Collect both runner groups:
    |      ApplicationRunner beans
    |      CommandLineRunner beans
    |
    +-- Sort together by order
    |
    +-- Sequentially invoke run(...) on runners
    |
    +-- ApplicationReadyEvent
    |      (only when the runners phase succeeds)
    |
    +-- SpringApplication.run(...) returns context
```

All normal runners execute during this phase when `SpringApplication.run` actually launches the application. They **do not run automatically when the bean is created**, do not run from another bean's `@PostConstruct` method, and do not wait until the first HTTP request.

This explains several behaviors:

1. A runner bean's `@PostConstruct` can run **before** both `run(...)` types, because bean creation occurs during refresh.
2. `ApplicationStartedEvent` is published before the runner invocation phase.
3. `ApplicationReadyEvent` is published after runners, and is not published on a failed startup path.
4. A runner blocking for too long extends startup time and delays reaching the ready state.
5. When a runner throws an exception that fails `SpringApplication.run`, subsequent runners cannot be assumed to still run.

Spring Boot recommends runners for work needed **after the context is built yet before the application is reported ready**, such as validating a startup precondition, loading small datasets, or establishing required state.

## 4. Why Are Both Types Sorted Together Rather Than Run by Group?

Conceptually, runner execution in Spring Boot 3.3 can be described as:

```text
1. Retrieve ApplicationRunner beans from context
2. Retrieve CommandLineRunner beans from context
3. Put them into a shared candidate list
4. Sort candidates with an Ordered / @Order-aware comparator
5. Avoid iterating the same runner instance twice in the loop
6. Iterate in sorted order and invoke the matching callback
```

The Java snippet below is **pseudo-code illustrating the mechanism**, not verbatim Spring Boot source code and not meant to compile standalone:

```java
List<Object> runners = new ArrayList<>();

runners.addAll(findApplicationRunners());
runners.addAll(findCommandLineRunners());

AnnotationAwareOrderComparator.sort(runners);

for (Object runner : deduplicateInOrder(runners)) {
    if (runner instanceof ApplicationRunner applicationRunner) {
        applicationRunner.run(applicationArguments);
    }
    if (runner instanceof CommandLineRunner commandLineRunner) {
        commandLineRunner.run(rawArguments);
    }
}
```

The functions `findApplicationRunners`, `findCommandLineRunners`, and `deduplicateInOrder` in the pseudo-code merely represent the idea. Reading actual Spring Boot 3.3 source code shows `SpringApplication#callRunners` and the use of `AnnotationAwareOrderComparator`.

**Key point to remember:** both groups are entered together into order comparison. Spring Boot does not run a full `ApplicationRunner` pass first and only then start a `CommandLineRunner` pass as an operational contract.

If you have not set an order, you might **observe** a repeating sequence across runs due to bean iteration order in a specific Boot version. Do not turn that observation into a business dependency. Only explicitly declared order relationships, with distinct values, should determine execution sequence.

## 5. Rules of @Order and Ordered

### 5.1. Lower Values Run First

Example:

```java
@Order(-10)
@Component
class FirstStartupTask implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("first");
    }
}

@Order(20)
@Component
class SecondStartupTask implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("second");
    }
}
```

This snippet belongs to a Spring Boot project importing `@Component`, `@Order`, both runner interfaces, and `ApplicationArguments`; each class can live in its own file or in the same Java file if there is no duplicate public class.

When both beans are properly registered, the output is:

```text
first
second
```

**`-10` precedes `20`**, because smaller values take precedence. Order values can be negative, zero, or positive.

### 5.2. Ordered Is the Interface Option

A bean can supply its order via:

```java
@Component
class ExplicitlyOrderedRunner implements ApplicationRunner, Ordered {

    @Override
    public int getOrder() {
        return 5;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("order 5");
    }
}
```

This snippet requires importing `org.springframework.core.Ordered`, `Component`, `ApplicationRunner`, and `ApplicationArguments`. If added to an existing demo, you must recalculate expected output because the new bean is called by Spring Boot at order 5.

`Ordered` is helpful when a class determines its order programmatically. Do not let `getOrder()` depend on state mutating erratically during sorting; order values should remain stable throughout a launch.

### 5.3. Default Values and Constants

Spring defines key milestones in `Ordered`:

- `Ordered.HIGHEST_PRECEDENCE`: highest priority in the integer order model; typically equals `Integer.MIN_VALUE`.
- `Ordered.LOWEST_PRECEDENCE`: lowest priority; typically equals `Integer.MAX_VALUE`.

A bean without `@Order` or `Ordered` is generally treated as specifying no explicit priority, defaulting to low precedence. **If multiple beans share the same priority, do not rely on relative ordering between them**.

### 5.4. Both @Order and Ordered Present?

Under Spring Framework's `AnnotationAwareOrderComparator`-based comparison, if an instance implements `Ordered`, the result of `getOrder()` is typically used as that instance's order rather than looking solely at the class annotation. Avoid this situation when unnecessary, as readers may confuse the two priority sources.

Recommendation: each runner should have **one clear ordering mechanism**, and each truly order-dependent step should have its own distinct priority value.

## 6. Complete Example: Both Runner Types Interleaved in One Order

This is a **Java 17+ / Spring Boot 3.3.x** example runnable in a compatible Gradle project. The goal is to prove: **a CommandLineRunner can run before an ApplicationRunner, followed by another ApplicationRunner running before another CommandLineRunner**, strictly according to `@Order`.

### 6.1. Project Structure

```text
runner-order-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          runners/
            RunnerOrderApplication.java
      resources/
        application.properties
```

To minimize file count in the example, all runner classes are defined **package-private and top-level** in the same Java file as one public application class.

### 6.2. The build.gradle File

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
}
```

`settings.gradle`:

```groovy
rootProject.name = 'runner-order-demo'
```

The Spring Boot 3.3 configuration here uses a specific release to illustrate the API; in production projects, pick a version actively supported and maintained by your organization. The project needs a Gradle wrapper compatible with Spring Boot and an appropriate Java toolchain; the build snippet does not generate the wrapper automatically.

### 6.3. The application.properties File

```properties
spring.application.name=runner-order-demo
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR
```

We use `NONE` because the demo does not need an HTTP server. Runner callbacks still execute in a non-web context. The logging setting suppresses routine logs; the output below shows only lines printed by application code.

### 6.4. Runnable Java Source

File `src/main/java/demo/runners/RunnerOrderApplication.java`:

```java
package demo.runners;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class RunnerOrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(RunnerOrderApplication.class, args);
    }
}

@Component
@Order(10)
class PrepareCommandLineRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println(
                "10 | CommandLineRunner | prepare | rawArgs=" + args.length);
    }
}

@Component
@Order(20)
class LoadApplicationRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "20 | ApplicationRunner | load | dryRun="
                + args.containsOption("dry-run"));
    }
}

@Component
@Order(30)
class VerifyApplicationRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("30 | ApplicationRunner | verify");
    }
}

@Component
@Order(40)
class ReportCommandLineRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("40 | CommandLineRunner | report");
    }
}
```

The package-private classes here are valid: Java allows one top-level public class per file and other non-public top-level classes. `@Component` lets them be scanned in package `demo.runners`, which is under the `@SpringBootApplication` package.

### 6.5. Running and Viewing Results

When the project has a Gradle wrapper:

```bash
./gradlew bootRun
```

Lines printed by the demo code with **no extra application arguments**:

```text
10 | CommandLineRunner | prepare | rawArgs=0
20 | ApplicationRunner | load | dryRun=false
30 | ApplicationRunner | verify
40 | CommandLineRunner | report
```

This is **deterministic order based on order values**. Other Spring Boot/Gradle logs may appear, excluded from the four illustrative lines.

If run as:

```bash
./gradlew bootRun --args='--dry-run'
```

in a shell handling quotes as above, the raw argument count and option value change:

```text
10 | CommandLineRunner | prepare | rawArgs=1
20 | ApplicationRunner | load | dryRun=true
30 | ApplicationRunner | verify
40 | CommandLineRunner | report
```

With PowerShell on Windows, you can use double quotes for the corresponding Gradle parameter per shell syntax. Do not rely on Unix single-quote syntax across all shells.

### 6.6. Proof of Shared Ordering

Suppose there were two separate queues, one per interface; then the two types would not interleave strictly as `10, 20, 30, 40`. Yet the actual demo result is:

- `CommandLineRunner` order 10 runs **before** `ApplicationRunner` order 20.
- `ApplicationRunner` order 30 runs **before** `CommandLineRunner` order 40.
- There is no separate phase per interface name; order is compared across **both types together**.

Therefore, the claim "`ApplicationRunner` always runs before `CommandLineRunner`" or vice versa **is not a rule that holds when explicit priorities are present**.

## 7. What If @Order Is Replaced with Ordered?

Both mechanisms supply a value for order comparison. You can replace `PrepareCommandLineRunner` in the demo with a similar class:

```java
@Component
class PrepareOrderedRunner implements CommandLineRunner, Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void run(String... args) {
        System.out.println(
                "10 | CommandLineRunner | prepare | rawArgs=" + args.length);
    }
}
```

This snippet requires importing `org.springframework.core.Ordered`, `Component`, and `CommandLineRunner`. It is an **alternative variant**, not a bean to add alongside the demo if you want to keep the exact four-line output.

After removing the old `PrepareCommandLineRunner` bean and replacing it with this one, the order remains 10, 20, 30, 40. Conversely, if you keep both with the same order 10, the relative order between them is no longer a reliable contract.

**When should you use Ordered?**

- You need to determine order via instance logic, e.g., an infrastructure class using a value configured in its constructor.
- You want to avoid annotation dependencies in shared classes.
- You are extending Spring infrastructure that already uses the `Ordered` interface.

For fixed startup steps, `@Order(10)` is usually shorter and clearer than `implements Ordered` just to return a constant.

## 8. If @Order Is Omitted, Which Runs First?

This is where most misunderstandings occur. Distinguish carefully:

**A. Observed behavior in a specific Spring Boot release**

A given Spring Boot release may collect `ApplicationRunner`s first, then `CommandLineRunner`s, or follow a certain bean iteration order while building the list. If objects all have the same default order, runs on your machine may repeatedly exhibit the same sequence.

**B. What the application is allowed to treat as a contract**

Spring Boot documentation instructs using `Ordered` or `@Order` when multiple runners **must run in a specific order**. There is no promise that default order among equal-priority beans will stay stable when:

- Upgrading Spring Boot or Spring Framework versions.
- Adding/removing starters, auto-configurations, or runner beans from another library.
- Changing bean registration methods (`@Component`, `@Bean`, conditional configuration).
- Renaming classes/beans, changing the classpath, or changing context construction.
- Moving to multi-application-context structures or custom bootstrapping.

Thus the technically accurate answer is:

> **Without explicit priority declarations, never depend on an ordering between runners that share the same order.**

If step B's output depends on data produced by step A, you must have an explicit dependency or orchestration mechanism. Avoid relying on "locally Spring invokes A before B."

### If Two Runners Share @Order(10)

```java
@Component
@Order(10)
class FirstTask implements ApplicationRunner { ... }

@Component
@Order(10)
class SecondTask implements CommandLineRunner { ... }
```

This snippet is **abbreviated pseudo-code** (the ellipsis is not valid Java source). Both share priority 10, so `@Order` **establishes no ordering relationship** between them. If A must precede B, use distinct values such as `@Order(10)` and `@Order(20)`, or consolidate dependent steps into an orchestrator.

### @Order Does Not Sort Bean Initialization Order

`@Order(10)` on a runner **controls where `run(...)` is invoked**, not whether that runner's constructor, `@PostConstruct`, or `InitializingBean.afterPropertiesSet()` executes before a bean with `@Order(20)`. Those are two distinct container phases:

```text
Refresh ApplicationContext:
    create / inject / initialize singletons per container rules
    |
    v
ApplicationStartedEvent
    |
    v
Runners phase:
    sort and invoke run(...) by order
```

To manage **bean initialization** relationships, use constructor injection, `@DependsOn` when appropriate, or other container mechanisms. To orchestrate **ordered startup logic**, use order and/or an explicit orchestrator. Do not expect one annotation to govern every kind of ordering.

## 9. Do Beans Registered via @Bean Sort Together with @Component?

**Yes.** `SpringApplication` cares about **beans in the context implementing a runner interface**; how they were registered does not create a separate execution phase.

Example:

```java
@Configuration
class RunnerConfiguration {

    @Bean
    CommandLineRunner simpleCommandRunner() {
        return args -> System.out.println("command bean ran");
    }

    @Bean
    ApplicationRunner simpleApplicationRunner() {
        return args -> System.out.println("application bean ran");
    }
}
```

This snippet requires importing `Configuration`, `Bean`, `CommandLineRunner`, and `ApplicationRunner`. Both beans are valid runners. **Neither has an explicit order yet**, as these are plain lambdas.

A version pitfall: **do not assume `@Order` placed on a `@Bean` method is always enough to control runner lambdas across every Spring Boot version**. The example above focuses on showing both are collected, not on proving priority. In Spring Boot 3.3, for predictable ordering, prefer:

- A runner class with `@Order` on the **class** and registered via `@Component`.
- A class implementing `Ordered` with an explicit `getOrder()`.
- A `@Bean` returning an instance of a runner class whose order configuration is recognized by the comparator.

If a project wishes to rely on annotations on `@Bean` factory methods, verify against your actual Spring Boot version and comparator. Do not deduce from `@Order` on factory methods working in some other injection/sorting mechanism that it automatically behaves identically for runner callbacks.

### Using @Bean with an @Order-Annotated Implementation

```java
@Order(15)
class AuditRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("audit order 15");
    }
}

@Configuration
class AuditConfiguration {

    @Bean
    AuditRunner auditRunner() {
        return new AuditRunner();
    }
}
```

This is a source example that can reside in a valid package, requiring imports for `Order`, `Configuration`, `Bean`, and `CommandLineRunner`. The `AuditRunner` bean is registered via `@Bean`, yet the instance's class carries an explicit order annotation, so it can participate in shared ordering.

If added to section 6's demo, `AuditRunner` will be invoked between order 10 and order 20. So **do not** add this snippet verbatim if you want to preserve the four-line sample output.

## 10. Case Where One Bean Implements Both Interfaces

A single class can implement both `ApplicationRunner` and `CommandLineRunner`:

```java
package demo.runners;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(25)
class DualRunner implements ApplicationRunner, CommandLineRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("25 | dual | ApplicationRunner");
    }

    @Override
    public void run(String... args) {
        System.out.println("25 | dual | CommandLineRunner");
    }
}
```

This snippet is a valid Java class that can be placed in `DualRunner.java` in the same package as the demo. Note that Java permits overloading `run` because one overload takes `ApplicationArguments` and the other takes `String[]`.

In Spring Boot 3.3's `callRunners` flow, **the exact same instance** can appear in both discovered bean groups. The runner traversal avoids processing the same instance twice, yet when handling an instance that implements both interfaces, Boot checks **both**:

1. If `ApplicationRunner`, invoke `run(ApplicationArguments)`.
2. If `CommandLineRunner`, invoke `run(String...)`.

Hence this bean holds **one position at order 25** in the runner object list, yet has **two distinct `run` callbacks** invoked when that position is reached. With section 6's demo, the output after adding `DualRunner` is:

```text
10 | CommandLineRunner | prepare | rawArgs=0
20 | ApplicationRunner | load | dryRun=false
25 | dual | ApplicationRunner
25 | dual | CommandLineRunner
30 | ApplicationRunner | verify
40 | CommandLineRunner | report
```

This is an advanced case and not necessarily good design. The two interfaces typically differ only in how arguments are supplied; implementing both easily causes **duplicate execution of startup logic** if both overloads call the same service, open connections, or send requests to external systems.

**Recommendation:** for a single startup step, usually choose **one** interface. If you need both raw and parsed arguments, `ApplicationRunner` already provides `ApplicationArguments.getSourceArgs()` for raw args. Use `DualRunner` mainly when you clearly understand why two independent callbacks are needed.

## 11. When a Runner Throws an Exception: How Is Shared Order Affected?

Runners are invoked in sorted order during startup. If a runner throws an exception that Spring Boot treats as a startup failure, **the invocation chain does not continue normally to subsequent runners**.

Suppose:

| Order | Runner | Behavior |
| ---: | --- | --- |
| 10 | `CommandLineRunner` | Completes |
| 20 | `ApplicationRunner` | Throws `IllegalStateException` |
| 30 | `CommandLineRunner` | Does not run |
| 40 | `ApplicationRunner` | Does not run |

Illustrative example for a method in a class implementing `ApplicationRunner`:

```java
@Override
public void run(ApplicationArguments args) {
    System.out.println("runner order 20 started");
    throw new IllegalStateException("required data unavailable");
}
```

This is a **method snippet placed inside a runner class**, not a standalone Java program. On the normal flow, after order-20 runner's print line, `SpringApplication.run` fails. `ApplicationReadyEvent` will not be published for that failed launch.

`SpringApplication` handles the failure, publishes `ApplicationFailedEvent` per Boot's mechanism, and performs context cleanup as appropriate. Exceptions may be wrapped by runner infrastructure, so when diagnosing, read the **root cause** rather than only the outermost exception type.

**Do not rely on "the last runner will clean up resources for all previous runners."** If an earlier runner fails, later runners are no longer guaranteed to run. Resources must be managed by bean lifecycle, `@PreDestroy`, `DisposableBean`, `AutoCloseable`, or appropriate `try/finally` blocks; critical cleanup must not be placed solely in the last runner.

If a non-essential initialization task fails yet the application is still allowed to run, design an explicit failure policy, handle exceptions selectively, and record state. Never catch all `Exception`s by default and treat startup as successful, as doing so can let the application run without necessary data ready.

## 12. When to Use @Order vs. an Orchestrator?

`@Order` is a great tool when there are a few **independent or linearly dependent operations**, such as:

```text
10 - verify configuration details
20 - initialize a small cache
30 - verify the cache
40 - log startup result
```

When steps are tightly coupled or involve rollback, transactions, or branching, placing them all inside a single **startup orchestrator** is usually easier to control.

### Orchestrator Example Using ApplicationRunner

```java
@Component
class StartupOrchestrator implements ApplicationRunner {

    private final StartupVerifier verifier;
    private final CacheWarmup warmup;

    StartupOrchestrator(StartupVerifier verifier, CacheWarmup warmup) {
        this.verifier = verifier;
        this.warmup = warmup;
    }

    @Override
    public void run(ApplicationArguments args) {
        verifier.verifyConfiguration();
        warmup.populate();
        verifier.verifyCache();
    }
}
```

This is an **illustrative design snippet**: you must supply the two services `StartupVerifier` and `CacheWarmup` with the invoked methods, plus imports for `Component` and `ApplicationRunner` / `ApplicationArguments`. It does not compile standalone without those two services.

Advantages:

- The sequence among `verifyConfiguration`, `populate`, and `verifyCache` is expressed directly in one method.
- Transaction boundaries, timeouts, retries, and error handling can be added as needed.
- Easy to unit test a single `run(...)` call.
- Independent of priorities across multiple runners contributed by other starters or modules.

**Warning:** an orchestrator does not automatically resolve asynchronous tasks it launches without awaiting results. If `populate()` only starts a thread and returns immediately, subsequent steps can still run before that thread finishes. Appropriate await/synchronization mechanisms or clear startup responsibilities are required.

### Design Principles

- Few runners, simple relationships → `@Order` suffices.
- Multiple critical steps needing rollback/error policies → consider an orchestrator.
- Logic needed before beans are created → runners are **too late**; use an appropriate pre-refresh extension point.
- Work that must run periodically after startup → use a proper scheduler/job system, not runners as repeating timers.
- Runtime monitoring needed after ready → use health/availability checks, not runners as continuous health signals.

## 13. Do Not Confuse Runner Order with Other Annotations/Lifecycle Hooks

| Mechanism | Primary Control | Guarantees `run` Order Across Both Runner Types? |
| --- | --- | --- |
| `@Order` on runner class | Runner invocation order when recognized by sorter | **Yes**, when priority values are explicitly distinct |
| `Ordered#getOrder()` | Dynamic order of a runner instance | **Yes**, per returned value |
| `@DependsOn` | Bean creation and destruction relationships | **Not directly**; not a runner-ordering API |
| Constructor injection | Bean created with required dependencies | **Not directly**; guarantees dependencies, not run order |
| `@PostConstruct` | Initialization callback of each bean | Runs in bean lifecycle, **before** runners phase |
| `InitializingBean.afterPropertiesSet()` | Bean initialization callback | Does not order runners |
| `ApplicationStartedEvent` | Event after refresh, before runners | Not "runner order" |
| `ApplicationReadyEvent` | Event after runners | Does not determine order among runners |
| `SmartLifecycle` | Start/stop lifecycle beans by phase | Phase mechanism distinct from runner order |
| `@Priority` / other comparators | Depends on applying mechanism | Do not assume identical behavior to `@Order` without verifying |
| Declaration order in `@Configuration` | Appearance order in source file | **Not** a runner ordering contract |
| Alphabetical bean name order | Identifier name | **Not** a runner ordering contract |

Some applications follow this flow:

```text
Create beans A / B (constructor, @PostConstruct)
        |
        v
ContextRefreshedEvent
        |
        v
ApplicationStartedEvent
        |
        v
Runner order 10
        |
        v
Runner order 20
        |
        v
ApplicationReadyEvent
```

Do not replace those arrows with "`@Order` sorts the entire lifecycle from constructor to ready." That annotation has a specific role when Spring Boot compares runners.

## 14. Common Scenarios in Real Applications

### 14.1. Seeding Data Before Validating Data

Requirement:

```text
SeedDataRunner (CommandLineRunner)
          ↓
ValidateDataRunner (ApplicationRunner)
```

You can configure:

```java
@Order(10)
class SeedDataRunner implements CommandLineRunner { ... }

@Order(20)
class ValidateDataRunner implements ApplicationRunner { ... }
```

This is **abbreviated pseudo-code**; `...` merely stands in for method bodies to write, not valid Java source. In this case, distinct `@Order` values create an explicit execution relationship. However, for migrations or critical data requiring atomicity/rollback, use dedicated tools or an orchestrator with proper error handling.

### 14.2. Two Separate Modules Both Register Runners

Module A has an `ApplicationRunner` with order 100, and module B has a `CommandLineRunner` with order 50. Even if module A's dependency is declared earlier in the build file, runner B still executes first because `50 < 100` in the shared order.

Do not rely on starter import order or JAR position on the classpath to order startup logic; establish a cross-module order contract or a coordinator.

### 14.3. Running a Runner Only in the Dev Environment

You can combine bean conditions:

```java
@Component
@Profile("dev")
@Order(10)
class DevDataRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Development-only startup task");
    }
}
```

This snippet requires importing `Profile`, `Component`, `Order`, and `CommandLineRunner`. If the `dev` profile is not active, the bean is not registered and therefore will not be invoked. In that case, remaining runners keep their own order. `@Order` does not cause a bean excluded by `@Profile` to be created.

### 14.4. A Runner Launches an Async Task

If a runner calls:

```java
backgroundExecutor.execute(() -> doWork());
```

that is a pseudo-code snippet with two undefined variables/methods. `run(...)` can return **before `doWork()` finishes**, so Spring Boot moves on to the next runner and then to ready. `@Order` only orders **`run` invocations**; it does not by default wait for every asynchronous task they spawn.

If a later step truly depends on an earlier step's result, return a `Future`/`CompletableFuture` and await appropriately, use an orchestrator, or design readiness/availability so traffic is refused until preconditions are met. Avoid unbounded blocking during bootstrap.

## 15. How to Test Shared Ordering

### Simple Console Testing

Use section 6's demo, run without arguments, and verify the exact order:

```text
10 | CommandLineRunner | prepare | rawArgs=0
20 | ApplicationRunner | load | dryRun=false
30 | ApplicationRunner | verify
40 | CommandLineRunner | report
```

Then change order:

- Change `PrepareCommandLineRunner` from 10 to 35.
- Keep the remaining three values 20, 30, 40.

Predict and verify output:

```text
20 | ApplicationRunner | load | dryRun=false
30 | ApplicationRunner | verify
10 | CommandLineRunner | prepare | rawArgs=0
40 | CommandLineRunner | report
```

Notice in the third line of the modified example that **the string `"10 | ..."` is hardcoded text printed by the method from source**, even though `@Order(35)` was changed. That is an easy-to-misread trick: log labels do not automatically update with annotations. In real testing, update the text to `35 | ...` to reflect the new priority. Once text is updated too, expected lines are 20, 30, 35, 40.

To avoid confusion, a better practice is printing order from a shared constant or using a test recorder instead of treating labels as the source of truth.

### Testing with a Recorder Instead of Console Output

You can create a singleton bean holding a list of step names recorded by runners. After `SpringApplication.run(...)` returns successfully, inspect the list:

```java
List<String> steps = List.of(
        "command-prepare",
        "application-load",
        "application-verify",
        "command-report");

System.out.println(steps);
```

The snippet above illustrates only **the expected values**, not an executable test: a real test needs a recorder written to by the runners and assertions against this list. When running multiple Spring contexts in the same JVM or using async executors, avoid shared static recorders and ensure proper isolation.

An important note about test frameworks: `ApplicationContextRunner` is a tool for testing auto-configuration/contexts, **not equivalent** to a full `SpringApplication.run(...)` call with the runner execution flow. If the goal is to test startup runner ordering, actually launch `SpringApplication` or use an appropriate integration test rather than assuming creating a context runs runners automatically.

### Testing Priority Values via Reflection? Unnecessary

To prove shared ordering, observing runtime behavior is clearest. Checking `@Order` presence via reflection only proves the annotation is present, not that the bean is created, present in the context, or selected as a runner by Spring Boot.

## 16. Common Errors and Diagnosis

| Symptom | Causes Worth Checking | Fix |
| --- | --- | --- |
| `CommandLineRunner` runs first even though developer thought ApplicationRunner always has priority | Neither group has a fixed priority rule; smaller order sorts first | Assign explicit `@Order`/`Ordered`, check output |
| Two runners both with `@Order(1)` run unpredictably | Same priority, establishes no ordering relationship | Change to distinct values or merge logic |
| Renaming beans does not change order to match names | Bean name is not the ordering mechanism | Use `@Order` or `Ordered` |
| Placed `@Order` somewhere yet callback order did not change | Annotation placed on wrong target, runtime type, proxy, factory-method metadata, or different version behavior | Place on implementation class or use `Ordered`; check Boot version |
| `@Order` on runner A yet bean B initializes first | `run` order differs from constructor/`@PostConstruct` order | Declare dependency/init lifecycle separately |
| Runner does not execute | Class is not a bean, profile/condition unmet, or app failed before runners phase | Check component scanning, bean registry, startup exceptions |
| Runner executes twice | Bean may implement both interfaces or callback was invoked manually outside Boot | Check implemented interfaces, call sites, instance/context counts |
| Subsequent runner does not run | Earlier runner threw an exception or `run` is blocking | Read stack trace, inspect threads and timeouts |
| `ApplicationReadyEvent` never arrives | Runner failed or startup never completed | Check errors in earlier runners and `ApplicationFailedEvent` |
| Test run differs from production | Different test slice/context loader or not executing full `SpringApplication` | Use integration test with proper scope and config |
| Runners ordered yet async data not ready | `run` returned before background work completed | Synchronize results or use an appropriate readiness mechanism |
| Adding a starter module changes order | Added auto-configured runner with different order or unspecified tie | Inspect actual runner beans and plan priorities |
| Web endpoint receives requests before runners finish | Server can bind during refresh, before ready phase | Do not rely on runners for absolute HTTP-layer isolation; use proper readiness/gating |

You can follow these diagnostic steps:

1. Verify **the right class implements the runner interface** and the bean is genuinely in the context.
2. List the runners present in the application: user-declared beans and beans from starters/auto-configuration.
3. Record the `@Order` or `Ordered.getOrder()` value **of each instance**.
4. Distinguish **`run(...)` invocation order** from bean creation order and events.
5. Spot runners with equal order or no order; this is a frequent cause of hidden order dependencies.
6. Read the first exception if the chain stopped midway; later runners may not run because an earlier runner failed.
7. If the project uses multiple contexts or invokes runners manually, confirm this is indeed the `SpringApplication` flow you intend to observe.
8. If data is still wrong despite correct order, check whether work genuinely **completed synchronously before `run` returned**.

## 17. Exercises and Self-Check Questions

### Exercise 1: Predict Mixed-Type Ordering

Suppose:

```text
App-A: ApplicationRunner, @Order(15)
Cmd-B: CommandLineRunner, @Order(5)
App-C: ApplicationRunner, @Order(25)
Cmd-D: CommandLineRunner, @Order(20)
```

Correct order:

```text
Cmd-B → App-A → Cmd-D → App-C
```

Why? Because `5 < 15 < 20 < 25`, with no priority step based on interface name.

### Exercise 2: Equal Values

Two runners both have `@Order(10)`, one of each type. Can you guarantee which runs first? You should not. If one runner must read results written by the other, assign distinct orders and consider clearer dependency coordination.

### Exercise 3: @Order Does Not Change Initialization Order

Add `@PostConstruct` to two runners with different orders, then log constructors and `run` callbacks. Distinguish:

- When beans are created/initialized.
- When `SpringApplication` invokes `run`.
- Which order `@Order` affects.

Do not write tests requiring constructor order to match runner order.

### Exercise 4: Comparing Arguments

Run the demo with `--dry-run`. Why does `CommandLineRunner` receive `String[]` while `ApplicationRunner` receives `ApplicationArguments`? Why is calling `args.containsOption("dry-run")` only valid on `ApplicationArguments`?

### Exercise 5: Startup Failure

In an order-20 runner, throw `IllegalStateException` after printing a log line. Predict whether order-30/40 runners and `ApplicationReadyEvent` will occur. Inspect the root exception and confirm startup fails rather than silently swallowing the error.

### Exercise 6: One Bean, Two Interfaces

Add section 10's order-25 `DualRunner`. Explain why two log lines appear at the same runner object position, and why the `ApplicationRunner` callback is called before the `CommandLineRunner` overload on that same instance in Boot 3.3's implementation.

### Exercise 7: Redesigning Multi-Step Startup

Suppose an application has seven startup steps, three with data dependencies and two needing retries when calling external services. Identify which parts should use single ordered runners and which should be consolidated into an orchestrator or handled via separate readiness. The goal is to avoid using integer order values as an uncontrolled workflow engine.

## 18. Summary to Remember

- **`ApplicationRunner` and `CommandLineRunner` are sorted together during startup**, not forced to run all of one group before the other.
- Spring Boot uses Spring's order comparator; **smaller numbers run first**, regardless of runner type.
- `@Order` on the runner class or `Ordered.getOrder()` defines ordering. Runners with equal priority or missing priority **must not have implicit ordering dependencies**.
- `@Order` controls **`run` invocation order**, not constructors, `@PostConstruct`, `@DependsOn`, or the entire lifecycle.
- Both runner types are invoked **after `ApplicationStartedEvent` and before `ApplicationReadyEvent`** on a successful startup.
- If an earlier runner throws an error, subsequent runners are not guaranteed to execute; `ApplicationReadyEvent` does not appear on a failed startup.
- A bean implementing both interfaces can receive **two calls across its two overloads** at the same runner position in Spring Boot 3.3; usually choose one interface to avoid duplicate logic.
- If startup has many tightly coupled steps, an explicit orchestrator and sensible error handling are generally safer than relying on a chain of `@Order` integers.

### Official References

- [Spring Boot 3.3 — Using the ApplicationRunner or CommandLineRunner](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): runner invocation timing and `@Order`/`Ordered`.
- [Spring Boot 3.3 — ApplicationRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html): `run(ApplicationArguments)`, ordering, and purpose.
- [Spring Boot 3.3 — CommandLineRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/CommandLineRunner.html): `run(String...)`, ordering, and purpose.
- [Spring Framework — Ordered API](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/core/Ordered.html): `getOrder()` values and precedence constants.
- [Spring Framework — Order Annotation API](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/core/annotation/Order.html): how to declare order for Spring components.
