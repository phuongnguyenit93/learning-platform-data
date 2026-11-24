# Coordinating Multiple Runners with `Ordered` and `@Order`

In Spring Boot, `ApplicationRunner` and `CommandLineRunner` are extension points for running tasks **after the `ApplicationContext` has refreshed** and **before `SpringApplication.run(...)` finishes**. An application may have multiple runners: checking configuration, loading initial data, warming caches, and verifying system state. If they must execute in a specific order, Spring Boot supports **`org.springframework.core.Ordered`** or **`org.springframework.core.annotation.Order`**.

The goal of this lesson is to understand **order values**, how Spring Boot merges both runner types into **a single shared order**, how to declare order via annotation and interface, what happens when runners tie or fail, along with a runnable **Java 17 + Spring Boot 3.3.x** example to observe the results.

## 1. Where Do Runners Sit in the Startup Lifecycle?

~~~text
SpringApplication.run(args)
   |
   +-- Prepare Environment
   +-- Create and refresh ApplicationContext
   +-- Finish non-lazy singletons requiring eager initialization
   |
   +-- ApplicationStartedEvent
   |        Runners not yet called
   |
   +-- Collect ApplicationRunner / CommandLineRunner beans
   +-- Resolve order and sort
   +-- Execute each runner in sorted order
   |
   +-- ApplicationReadyEvent
   +-- ReadinessState.ACCEPTING_TRAFFIC
   |
   v
SpringApplication.run returns ConfigurableApplicationContext
~~~

In Spring Boot 3.3, `ApplicationStartedEvent` is published **before** runners. `ApplicationReadyEvent` is published **after** all runners execute successfully. The `Started ... in ... seconds` log line typically appears at the started milestone; seeing that log should not be taken to mean all runners have completed.

Runners **are Spring beans**. The container can instantiate a runner and execute `@PostConstruct` callbacks during refresh, whereas **the runner's `run(...)` method** is called afterward by Spring Boot. These are two independent orderings: **bean creation order** and **runner execution order**.

## 2. Two Runner Interfaces

### `ApplicationRunner`

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;

public final class OptionsRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        System.out.println("mode=" + args.getOptionValues("mode"));
    }
}
~~~

`ApplicationRunner.run(ApplicationArguments)` receives a parsed command-line object. Useful methods: `getSourceArgs()`, `getOptionNames()`, `containsOption(...)`, `getOptionValues(...)`, and `getNonOptionArgs()`. With the argument `--mode=demo`, `getOptionValues("mode")` returns a list containing `demo`.

The example class **is only invoked by Spring Boot once registered as a bean**, e.g., via `@Component` or `@Bean`; merely creating a Java file does not make it a runner automatically.

### `CommandLineRunner`

~~~java
import java.util.Arrays;
import org.springframework.boot.CommandLineRunner;

public final class RawRunner implements CommandLineRunner {
    @Override
    public void run(String... args) {
        System.out.println("args=" + Arrays.toString(args));
    }
}
~~~

`CommandLineRunner.run(String...)` receives the raw argument array. With `--mode=demo`, `Arrays.toString(args)` produces `[--mode=demo]`.

| Need | Convenient Interface |
| --- | --- |
| Parse options by name/value | `ApplicationRunner` |
| Read exact original argument strings | `CommandLineRunner` |
| Run a one-time task after refresh | Both |
| Apply `Ordered` or `@Order` | Both |

**There is no rule that "all `ApplicationRunner`s run before all `CommandLineRunner`s."** They are sorted together.

## 3. Rule: **Smaller** Order Runs **First**

| Runner Bean | Order | Expected Position |
| --- | ---: | ---: |
| Configuration check | 10 | 1 |
| Data load | 20 | 2 |
| Cache preparation | 30 | 3 |
| Finalize setup | 40 | 4 |
| Unspecified order | `Ordered.LOWEST_PRECEDENCE` | Last in the example group |

`@Order(1)` runs before `@Order(10)`; `@Order(10)` runs before `@Order(100)`. Negative values are still valid, though projects typically pick clear values for maintainability.

Two constants:

- `Ordered.HIGHEST_PRECEDENCE` = `Integer.MIN_VALUE`, highest priority.
- `Ordered.LOWEST_PRECEDENCE` = `Integer.MAX_VALUE`, lowest priority.

A runner without an explicit order is generally treated by the comparator as `LOWEST_PRECEDENCE`. **If two runners share the same order**, do not rely on their relative order as a business requirement; assign distinct values or coordinate via a single runner.

## 4. Approach 1: Declaring `@Order`

Import:

~~~java
import org.springframework.core.annotation.Order;
~~~

Placed on a class:

~~~java
@Order(10)
public final class ValidateRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        System.out.println("validate");
    }
}
~~~

This snippet requires importing `ApplicationRunner` and `ApplicationArguments` and registering the class as a bean to be invoked. The annotation assigns priority level **10** to the runner class.

Placed on a `@Bean` factory method:

~~~java
@Bean
@Order(20)
CommandLineRunner loadReferenceData() {
    return args -> System.out.println("load data");
}
~~~

This is a **method inside a configuration class** with imports for `Bean`, `Order`, and `CommandLineRunner`. In Spring Boot **3.3.13**, the runner-sorting logic can read `@Order` from **the bean factory method**; hence placing the annotation here is also valid.

**Do not** annotate only the configuration class with `@Order` and assume every runner created by `@Bean` methods inside that class receives the same priority. Place the annotation directly on the **runner class** or **runner factory method**.

`@Order` fits well when priority is fixed and easy to read. It **does not dictate the order in which Spring creates all singleton beans**; bean creation order is governed by dependency relationships and other container rules.

## 5. Approach 2: Implementing `Ordered`

Import:

~~~java
import org.springframework.core.Ordered;
~~~

With `Ordered`, the object provides its order via `getOrder()`:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.Ordered;

public final class CacheRunner implements ApplicationRunner, Ordered {
    private final int priority;

    public CacheRunner(int priority) {
        this.priority = priority;
    }

    @Override
    public int getOrder() {
        return priority;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("cache priority=" + priority);
    }
}
~~~

Bean registration:

~~~java
@Bean
ApplicationRunner cacheRunner() {
    return new CacheRunner(30);
}
~~~

The factory method above must live inside a configuration class with `Bean` imported. The runner returns order 30. With two instances `new CacheRunner(10)` and `new CacheRunner(20)` registered under two different bean names, they can be sorted by **each instance's own value**.

| Criterion | `@Order` | `Ordered` |
| --- | --- | --- |
| Source of order | Annotation on class/factory method | Instance's `getOrder()` |
| Usually fixed value | Yes | Possible, though can also come from constructor |
| Requires dedicated method | No | Yes |
| Best suited for | Simple runners with minimal customization | Reusable runner classes with varying priority levels |

Avoid declaring two conflicting order levels via `@Order` and `Ordered` on the same bean. Readers cannot easily tell which source is authoritative, and the code becomes harder to maintain.

`getOrder()` should be stable, fast, and side-effect-free. Spring Boot determines the order when invoking runners; it does not rerun all runners if an order field changes later.

## 6. Actual Coordination Mechanism in Spring Boot 3.3

Spring Boot 3.3.13's `SpringApplication.callRunners(...)` source code shows these steps:

1. Retrieve beans belonging to the common `Runner` interface from `ApplicationContext`; these beans may be `ApplicationRunner` or `CommandLineRunner`.
2. Pair instances with bean names to look up ordering metadata from the bean/factory method when needed.
3. Sort all runner beans using a comparator supporting `Ordered` and `@Order`.
4. For each sorted object, invoke the callback of the interface it implements.
5. When no exception occurs, proceed to the ready milestone.

Example:

~~~text
ApplicationRunner A: order 30
CommandLineRunner B: order 10
ApplicationRunner C: order 20

Invocation order: B -> C -> A
~~~

Because sorting operates on **one unified collection**, a `CommandLineRunner` with order 10 can run before an `ApplicationRunner` with order 20.

### Bean Implementing Both Interfaces

One object can implement both `ApplicationRunner` and `CommandLineRunner`:

~~~java
public final class DualRunner
        implements ApplicationRunner, CommandLineRunner, Ordered {

    @Override
    public int getOrder() {
        return 50;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("application callback");
    }

    @Override
    public void run(String... args) {
        System.out.println("command-line callback");
    }
}
~~~

This snippet requires corresponding imports and bean registration. In Spring Boot 3.3.13, when this object's turn arrives, `SpringApplication` can invoke **both methods**; what they print is:

~~~text
application callback
command-line callback
~~~

Do not implement both interfaces only to execute the same task twice. If two tasks are independent, two separate runner beans with explicit order levels are usually easier to manage.

## 7. Hands-On Java 17 / Spring Boot 3.3 Example: Five Runners

The application below runs without a web server to avoid Tomcat logs. It demonstrates:

- `@Order` on an **`ApplicationRunner` class**;
- `@Order` on a **`@Bean` method creating a `CommandLineRunner`**;
- `Ordered` on an **`ApplicationRunner` instance**;
- A runner with a larger order value;
- An unordered runner.

### Creating the Project

Structure:

~~~text
ordered-runners/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/ordered/OrderedRunnersApplication.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'ordered-runners'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    // Native BOM to resolve versions for Spring Boot dependencies.
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

**Gradle note:** the Spring Boot plugin combined with the Gradle native BOM above provides version management for starters without specifying versions. If using an existing project that already has another dependency-management mechanism, use the project's convention instead of declaring duplicates.

File `src/main/java/com/example/ordered/OrderedRunnersApplication.java`:

~~~java
package com.example.ordered;

import java.util.Arrays;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
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
import org.springframework.core.annotation.Order;

@SpringBootApplication
public class OrderedRunnersApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(OrderedRunnersApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN active=" + context.isActive());
        }
    }

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("EVENT started");
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("EVENT ready");
    }

    @Bean
    ApplicationRunner validate() {
        return new ValidateRunner();
    }

    @Order(10)
    static final class ValidateRunner implements ApplicationRunner {
        @Override
        public void run(ApplicationArguments args) {
            System.out.println(
                "RUN 10 mode=" + args.getOptionValues("mode"));
        }
    }

    @Bean
    @Order(20)
    CommandLineRunner prepareData() {
        return args -> System.out.println(
            "RUN 20 args=" + Arrays.toString(args));
    }

    @Bean
    ApplicationRunner prepareCache() {
        return new CacheRunner(30);
    }

    static final class CacheRunner implements ApplicationRunner, Ordered {
        private final int order;

        CacheRunner(int order) {
            this.order = order;
        }

        @Override
        public int getOrder() {
            return order;
        }

        @Override
        public void run(ApplicationArguments args) {
            System.out.println("RUN " + order + " cache");
        }
    }

    @Bean
    @Order(40)
    CommandLineRunner finalSetup() {
        return args -> System.out.println("RUN 40 setup");
    }

    @Bean
    CommandLineRunner unrankedRunner() {
        return args -> System.out.println("RUN default");
    }
}
~~~

This is a complete program **within a Spring Boot project with declared dependencies**, not compiled with standalone `javac OrderedRunnersApplication.java`. The two nested classes are created via `@Bean` and do not need `@Component`. Do not accidentally declare another runner bean duplicating their roles.

The `@EventListener` methods on the configuration class are registered by Spring during context initialization to receive the started/ready events occurring after refresh.

### Running and Output

If the project has a compatible Gradle Wrapper:

~~~bash
./gradlew bootRun --args="--mode=demo"
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--mode=demo"
~~~

If there is no wrapper yet but a compatible Gradle installation is available:

~~~bash
gradle bootRun --args="--mode=demo"
~~~

The output **produced by `System.out.println` in the example code** appears in this order on a successful run:

~~~text
EVENT started
RUN 10 mode=[demo]
RUN 20 args=[--mode=demo]
RUN 30 cache
RUN 40 setup
RUN default
EVENT ready
MAIN active=true
~~~

Other Gradle/Spring logs may interleave; these are solely the lines intentionally printed by the demo.

Reading the output:

1. `EVENT started` is first because `ApplicationStartedEvent` occurs before runners.
2. `RUN 10` takes precedence due to `@Order(10)` on the `ValidateRunner` class.
3. `RUN 20` is a `CommandLineRunner` with `@Order(20)` on the `@Bean` method, still running before the `ApplicationRunner` at order 30.
4. `RUN 30` is an `ApplicationRunner` implementing `Ordered`.
5. `RUN 40` runs after 30; the unordered runner comes last.
6. `EVENT ready` proves all runners completed on the success path.
7. `MAIN active=true` proves `SpringApplication.run(...)` returned the context.

### Experiment: Changing Order

Change `@Order(40)` on `finalSetup()` to `@Order(5)` and also change the printed string from `RUN 40 setup` to `RUN 5 setup`. That runner will now be invoked **before** `ValidateRunner` (order 10), even though it appears lower in the source file.

### Experiment: Equal Orders

Change two runners to both have `@Order(20)`. Do not treat the actual print order of two tied runners as a design guarantee. For tightly dependent steps, assign distinct numbers or consolidate into an explicit orchestrating runner.

## 8. Why Equal Orders Are Insufficient for Business Dependencies

An order value expresses only **relative priority**. If A and B both have order 10, they share the same level. Bean collection order and other implementation details may influence tie-breaking, which is not a guaranteed contract for business logic.

Consequence: if runner B needs data produced by runner A, leaving both at order 10 creates an error-prone hidden dependency. Fix it as follows:

~~~text
A: @Order(10) -> prepare data
B: @Order(20) -> confirm data is ready
~~~

Or combine them into one runner:

~~~text
StartupWorkflowRunner.run(...)
   +-- validateConfiguration()
   +-- loadReferenceData()
   +-- warmUpCache()
~~~

The second approach fits when these steps **truly form one tightly coupled workflow** needing unified error, transaction, or retry management.

In Spring Boot 3.3.13, the runner-collection mechanism uses an identity-based map of instances prior to sorting. This further reinforces **not relying on accidental ordering among tied beans**.

## 9. `@Order` Guarantees **Invocation** Order, Not Async Task Completion

Spring Boot invokes `run(...)` methods in order. However, if runner A merely launches background work and returns, runner B can start while A's work has not finished.

Illustrative example:

~~~java
@Override
public void run(ApplicationArguments args) {
    executor.submit(this::loadData);
    // Runner returns while the task may still be running.
}
~~~

This snippet is **not standalone**, assuming the class has `executor` and `loadData`. If runner B needs data from A, there must be a completion synchronization mechanism, or runner A must await the required condition before returning. Simply placing `@Order(10)` on A and `@Order(20)` on B **is not enough** to ensure A's background work is done.

Similarly, a runner with an infinite loop prevents `SpringApplication.run` from advancing to the ready milestone. For long-lived consumers or workers, consider managing them via `SmartLifecycle` and a proper readiness system.

## 10. What If a Runner Throws an Exception

Suppose three runners have orders 10, 20, and 30. Runner 20 throws an exception:

~~~java
@Bean
@Order(20)
CommandLineRunner failingStep() {
    return args -> {
        throw new IllegalStateException("Required data unavailable");
    };
}
~~~

This is an **illustrative snippet inside a configuration class**, requiring imports for `Bean`, `Order`, `CommandLineRunner`. Do not add it to the default demo unless intentionally testing the failure path.

Sequence of events:

~~~text
Runner 10: completes
Runner 20: throws IllegalStateException
Runner 30: does not run on the success path
ApplicationReadyEvent: not published on the success path
SpringApplication.run: does not return as a successful startup
~~~

Spring Boot will handle the startup error; when diagnosing, read the **root cause** and the failing runner name in the stack trace. Runner 20 failing does not mean runner 10's side effects are automatically rolled back: transactions, idempotency, and compensating steps must be designed explicitly if needed.

## 11. Runner Order and Readiness

Runners are often used to prepare the application before signaling readiness to receive traffic:

~~~text
Context refreshed
   |
   +-- ApplicationStartedEvent
   +-- @Order(10): check configuration
   +-- @Order(20): load mandatory data
   +-- @Order(30): warm up cache
   |
   +-- ApplicationReadyEvent
   +-- ReadinessState.ACCEPTING_TRAFFIC
~~~

However, readiness does not mean **every external dependency is always healthy**; operations require proper health/readiness checks. If a runner returns while a background task is still running, Spring Boot can advance to ready before the task finishes. If the web server already opened its port during refresh, you also must not assume all runners have completed.

## 12. Distinguishing Similarly Named Mechanisms

| Mechanism | Controls | Does Not Automatically Control |
| --- | --- | --- |
| `@Order` / `Ordered` on runners | Invocation order of runner `run(...)` | Constructors or `@PostConstruct` of all beans |
| Constructor injection / `@DependsOn` | Bean creation relationships | Execution order of multiple independent runners |
| `SmartLifecycle.getPhase()` | Start/stop order of Lifecycle beans | Runner invocation order |
| `@Order` on listeners | Listener invocation order at event dispatch points supporting sorting | Runners |
| `ApplicationStartedEvent` | Milestone after refresh, before runners | Milestone after runners |
| `ApplicationReadyEvent` | Milestone after runners succeed | Guarantee that all external systems are always ready |

Putting `@Order(10)` on a runner does not mean Spring will instantiate that class before every `@Order(20)` singleton. Initialization order follows the dependency graph and container rules.

## 13. Common Errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| Runner class does not run | Not registered as a bean | Use `@Component` or `@Bean` |
| Runner is at bottom of file yet runs first | Has a higher-priority order | Check `@Order`/`getOrder()` values |
| `CommandLineRunner` runs before `ApplicationRunner` | Both interfaces are sorted together | Do not rely on interface type |
| Tied-order runners execute in unexpected order | No guaranteed tie-breaker | Use distinct order values |
| Unordered runner runs last | `LOWEST_PRECEDENCE` | Specify an explicit order if needed |
| `@Order` does not make constructor run first | Runner order differs from bean init order | Review dependency relationships |
| Runner A submits async, B lacks data | A only started the task | Await completion or synchronize explicitly |
| `ApplicationReadyEvent` never arrives | Runner hangs or fails | Check stack trace, timeouts, thread dumps |
| Duplicate data created after restart | Runner is not idempotent | Check state and use appropriate transactions |
| Same bean implements both runner interfaces | Callbacks may run twice | Split responsibilities or use one interface |
| `build.gradle` fails to resolve starters | Missing BOM/dependency management | Import Spring Boot BOM or compatible plugin |

## 14. Self-Check

1. `CommandLineRunner` order 10 and `ApplicationRunner` order 20—which runs first? **Order 10 runner**.
2. Which has higher priority: `@Order(0)` or `@Order(100)`? **0**.
3. What level does an unordered runner usually receive? **`LOWEST_PRECEDENCE`**.
4. Where does `Ordered` obtain priority? **Instance's `getOrder()`**.
5. Does `@Order` cause `@PostConstruct` to execute in the corresponding order? **No**.
6. Do two runners with the same order guarantee an execution sequence? **Do not rely on tied ordering**.
7. Runner 10 only submits a background task; does runner 20 wait for that task to finish? **Not automatically**.
8. Runner order 20 throws an unhandled exception; is runner 30 invoked on the success path? **No**.
9. Does `ApplicationStartedEvent` occur before or after runners? **Before**.
10. Does `ApplicationReadyEvent` occur before or after runners? **After runners succeed**.
11. In Spring Boot 3.3, does `@Order` on a `@Bean` factory method creating a runner take effect? **Yes**.
12. Can a single bean implementing both interfaces receive two callbacks? **Yes**.
13. Why should `getOrder()` not perform network I/O? **Because sorting must be fast, stable, and side-effect-free**.
14. How should three tightly coupled startup steps be structured? **Use distinct order values and ensure completion, or use an explicit orchestrator runner**.

**Remember:** `Ordered` and `@Order` control **the order in which Spring Boot invokes `run(...)` methods**, not bean creation order. `ApplicationRunner` and `CommandLineRunner` are sorted **together**, smaller numbers running first; tied runners should not be relied upon for business dependencies; asynchronous work does not automatically finish merely because of `@Order`.

### References

- Spring Boot 3.3 — Using the ApplicationRunner or CommandLineRunner: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — ApplicationRunner API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html
- Spring Boot 3.3.13 — CommandLineRunner API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/CommandLineRunner.html
- Spring Boot 3.3.13 — SpringApplication.callRunners source: https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/SpringApplication.java
- Spring Framework 6.1 — Ordered: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/Ordered.html
- Spring Framework 6.1 — Order: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/annotation/Order.html
- Spring Boot 3.3 Gradle plugin — dependency management: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
