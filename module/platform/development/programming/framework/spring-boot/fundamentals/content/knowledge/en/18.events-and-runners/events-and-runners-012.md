# Ordered, @Order, and Runner Execution Order

In Spring Boot, `ApplicationRunner` and `CommandLineRunner` are two common ways to execute code after the `ApplicationContext` is initialized. When an application has multiple runners, execution order can matter greatly: one runner prepares data, the next runner reads the prepared data, and the final runner prints a report.

Spring Boot lets you specify runner order using the `Ordered` interface or the `@Order` annotation. The core rule is **a smaller order value runs earlier**. Both `ApplicationRunner` and `CommandLineRunner` participate together in sorting; they are not run as two separate fixed groups.

This lesson belongs to the **Events and Runners** chapter of **Spring Boot Fundamentals**. We will examine when runners are invoked, how `Ordered` and `@Order` work, scenarios where order is not guaranteed, the difference between *runner execution order* and *bean initialization order*, and practice with a multi-runner Spring Boot application.

## 1. What Are Runners and Where Do They Execute During Startup?

`CommandLineRunner` is a Spring Boot functional interface:

```java
package org.springframework.boot;

@FunctionalInterface
public interface CommandLineRunner {

    void run(String... args) throws Exception;
}
```

`ApplicationRunner` is also a functional interface:

```java
package org.springframework.boot;

@FunctionalInterface
public interface ApplicationRunner {

    void run(ApplicationArguments args) throws Exception;
}
```

What they share is that Spring Boot calls `run(...)` on beans implementing these interfaces after the context refreshes. Where they differ is how command-line arguments are received.

| Interface | Parameter of `run(...)` | When to Use |
|---|---|---|
| `CommandLineRunner` | `String... args` | Need to handle raw argument strings |
| `ApplicationRunner` | `ApplicationArguments args` | Need to distinguish option and non-option arguments |
 
Both must be registered as **Spring beans**. A class that merely implements the interface without residing in the container will not be called automatically by Spring Boot.

### 1.1. Relative Position in the Lifecycle

In a typical Spring Boot startup process, the key milestones are:

```text
SpringApplication.run(...)
          │
          ▼
Prepare Environment and ApplicationContext
          │
          ▼
Load bean definitions, create required singletons
          │
          ▼
ApplicationContext refresh completes
          │
          ▼
ApplicationStartedEvent
          │
          ▼
Collect ApplicationRunner and CommandLineRunner beans
          │
          ▼
Sort runners by order
          │
          ▼
Invoke run(...) on each runner
          │
          ▼
ApplicationReadyEvent
          │
          ▼
Application is considered ready
```

`ApplicationStartedEvent` is published after context refresh, **before** runners are invoked. `ApplicationReadyEvent` is published after runners complete successfully.

If a runner throws an unhandled exception, startup can fail and the application never reaches the ready milestone. Therefore, runners are not just a helper to run code: they sit directly on the application's startup path.

### 1.2. What Are Runners Typically Used For?

Some examples:

- Validating required configuration or data before the application is ready.
- Preparing a small amount of initial data.
- Running CLI or batch jobs that need dependency injection.
- Reading command-line arguments and orchestrating a task.
- Printing startup details or a brief diagnostic report.

Do not put an infinitely running loop inside a web application's runner if the application needs to transition to the ready state. A long-running runner delays `ApplicationReadyEvent` and can cause readiness probes to fail.

## 2. Creating a Simple CommandLineRunner

Example:

```java
package com.example.demo.startup;

import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class GreetingRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("GreetingRunner executed");
    }
}
```

When the class is within component scan scope, Spring registers a `greetingRunner` bean. Once context refresh completes, Spring Boot invokes `run(...)`.

For example, if the application has a main class:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Then after the startup logs, you will see:

```text
GreetingRunner executed
```

Runners execute per **ApplicationContext startup**, not again on each HTTP request.

### 2.1. ApplicationRunner Receives Parsed Arguments

Example:

```java
package com.example.demo.startup;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ArgumentRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Has --mode: "
                + args.containsOption("mode"));

        System.out.println("Mode values: "
                + args.getOptionValues("mode"));

        System.out.println("Non-option args: "
                + args.getNonOptionArgs());
    }
}
```

Run:

```bash
java -jar demo.jar --mode=import input.csv
```

Illustrative output:

```text
Has --mode: true
Mode values: [import]
Non-option args: [input.csv]
```

`ApplicationRunner` is helpful when parsing options. `CommandLineRunner` remains suitable when you want raw `String[]` values or use a custom parser.

## 3. With Multiple Runners, Which Order Does Spring Boot Use?

Suppose an application has three runners:

```text
PrepareRunner
ImportRunner
ReportRunner
```

You want:

```text
PrepareRunner
      │
      ▼
ImportRunner
      │
      ▼
ReportRunner
```

Without declared ordering, **never rely on** class name order, bean name order, Java file order, component scanning order, or project source order.

Spring Boot collects beans implementing `ApplicationRunner` and `CommandLineRunner`, sorts them using a comparator that honors order metadata, and invokes the runners in the sorted sequence.

To specify order, there are two main mechanisms:

1. Annotate the runner class with `@Order`.
2. Implement the `Ordered` interface on the runner and return a value from `getOrder()`.

### 3.1. Principle: Lower Values Run First

| Order Value | Relative Execution Order |
|---:|---|
| `-100` | Earlier than `-10` |
| `-10` | Earlier than `0` |
| `0` | Earlier than `10` |
| `10` | Earlier than `100` |
| `100` | Later than the values above |

Negative integers are valid. You do not need to start at 1, nor number consecutively.

For example, `@Order(10)` runs before `@Order(20)`, regardless of which runner was registered first.

## 4. Approach 1: Using the `@Order` Annotation

Import:

```java
import org.springframework.core.annotation.Order;
```

Data-preparation runner example:

```java
package com.example.demo.startup;

import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class PrepareRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("1 - Prepare data");
    }
}
```

Import runner:

```java
package com.example.demo.startup;

import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(20)
public class ImportRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("2 - Import data");
    }
}
```

Report runner:

```java
package com.example.demo.startup;

import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(30)
public class ReportRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("3 - Print report");
    }
}
```

Output:

```text
1 - Prepare data
2 - Import data
3 - Print report
```

The key point is that Spring Boot sorts using the values `10`, `20`, `30`. The strings `1`, `2`, `3` in the logs are merely illustrative output.

### 4.1. `@Order` Is Declarative Metadata

`@Order(10)` is a static directive attached to the class. It is convenient when order rarely changes and is known right at the runner definition.

Example:

```java
@Component
@Order(5)
public class ValidateConfigurationRunner
        implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        // Validate configuration.
    }
}
```

Advantages:

- Easy to read.
- No extra `getOrder()` method needed.
- Fits classes with a clear, fixed place in the startup chain.

Disadvantage: if the order value must be computed or driven by external configuration, the annotation offers no direct dynamic mechanism.

### 4.2. Do Not Mix Up the `@Order` Import

The annotation to use is:

```java
org.springframework.core.annotation.Order
```

Do not confuse it with similarly named annotations from third-party libraries. When code does not run in the expected order, one of the first things to check is the import statement.

## 5. Approach 2: Implementing the `Ordered` Interface

`Ordered` is a Spring Framework interface:

```java
import org.springframework.core.Ordered;
```

The interface defines the method:

```java
int getOrder();
```

A runner can implement both `ApplicationRunner` and `Ordered`:

```java
package com.example.demo.startup;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;

@Component
public class ValidateRunner implements ApplicationRunner, Ordered {

    @Override
    public int getOrder() {
        return 5;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Runs before order 10+ runners");
    }
}
```

With `getOrder() = 5`, this runner executes before a runner annotated with `@Order(10)`.

### 5.1. `Ordered` Fits When Expressing Order in Code

`Ordered` can be helpful when:

- The class already holds ordering logic or implements a matching ordering interface.
- You want to use constants such as `Ordered.HIGHEST_PRECEDENCE`.
- A component needs to supply order dynamically via a method.
- You want to reuse the same ordering contract across multiple Spring mechanisms.

Example:

```java
@Component
public class BootstrapValidationRunner
        implements CommandLineRunner, Ordered {

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }

    @Override
    public void run(String... args) {
        System.out.println("Runs very early in the runner group");
    }
}
```

`Ordered` is not a lifecycle hook. `getOrder()` only supplies a sorting value; Spring Boot still calls `run(...)` during the runner phase after context refresh.

### 5.2. `HIGHEST_PRECEDENCE` and `LOWEST_PRECEDENCE`

The `Ordered` interface defines two constants:

```java
Ordered.HIGHEST_PRECEDENCE
Ordered.LOWEST_PRECEDENCE
```

Corresponding to:

```java
Integer.MIN_VALUE
Integer.MAX_VALUE
```

Meaning:

- `HIGHEST_PRECEDENCE` is one of the earliest possible values recognized by the comparator.
- `LOWEST_PRECEDENCE` is the latest value.
- Any integer between those bounds is permitted.

**Do not confuse "highest" with a large positive integer.** In this ordering system, smaller numbers mean higher priority to run earlier.

For example:

```java
@Override
public int getOrder() {
    return Ordered.HIGHEST_PRECEDENCE;
}
```

will be sorted before:

```java
@Order(0)
```

and also:

```java
@Order(100)
```

unless other runners also share that minimum order value.

### 5.3. What If There Is No `@Order`?

For a runner that neither implements `Ordered` nor carries order metadata, the comparator typically treats it as having `LOWEST_PRECEDENCE`.

That means an unordered runner normally executes after runners with explicit order values lower than the default.

However, when multiple runners omit order or share the lowest value, **no business ordering is guaranteed among them**.

## 6. Use `@Order` or `Ordered`?

Both mechanisms provide an integer for Spring Boot to sort runners.

| Criterion | `@Order` | `Ordered` |
|---|---|---|
| Syntax | Annotation on the class | Implement interface and `getOrder()` |
| Value | Integer declared in annotation | Integer returned from method |
| Best suited for | Static order, easily visible on class | Order expressed via code/interface |
| Requires extra method? | No | Yes |
| Recognized by Spring's comparator? | Yes | Yes |
| Applies uniformly to both runner types? | Yes | Yes |

A clean annotation example:

```java
@Component
@Order(10)
public class StartRunner implements CommandLineRunner {
    @Override
    public void run(String... args) {
        // ...
    }
}
```

And an equivalent interface example:

```java
@Component
public class StartRunner implements CommandLineRunner, Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void run(String... args) {
        // ...
    }
}
```

In ordinary applications, `@Order` is usually concise and easy to spot. If the class already follows an `Ordered` contract or needs constants/logic for ordering, use the interface.

### 6.1. If a Class Has Both `@Order` and `Ordered`

Example:

```java
@Component
@Order(100)
public class MixedRunner implements CommandLineRunner, Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void run(String... args) {
        System.out.println("MixedRunner");
    }
}
```

Spring's annotation-aware comparator gives precedence to the value returned by an `Ordered` instance when the class implements that interface. Thus, `getOrder() = 10` determines this runner's position above, rather than `@Order(100)`.

Even knowing this rule, **never declare two conflicting values on the same class**. Readers will easily misunderstand it. Pick one mechanism, or ensure both agree if a library forces both.

## 7. ApplicationRunner and CommandLineRunner Are Sorted Together

A very important point: Spring Boot **does not run all ApplicationRunners first and then CommandLineRunners**, or vice versa, just because of interface type.

Runners are gathered and sorted by ordering metadata regardless of which interface they implement.

Example:

```java
@Component
@Order(10)
public class FirstRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("A - CommandLineRunner");
    }
}
```

```java
@Component
@Order(20)
public class SecondRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("B - ApplicationRunner");
    }
}
```

```java
@Component
@Order(30)
public class ThirdRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("C - CommandLineRunner");
    }
}
```

Output:

```text
A - CommandLineRunner
B - ApplicationRunner
C - CommandLineRunner
```

The reason is orders `10`, `20`, `30`; not the runner interface type.

### 7.1. Change Order, Change Execution Sequence

If you set `@Order(5)` on `SecondRunner`, output becomes:

```text
B - ApplicationRunner
A - CommandLineRunner
C - CommandLineRunner
```

This directly shows that an `ApplicationRunner` can execute before a `CommandLineRunner` if its order value is smaller.

### 7.2. One Bean Implementing Both Interfaces

In Java, a class can implement both `ApplicationRunner` and `CommandLineRunner`:

```java
@Component
@Order(10)
public class DualRunner
        implements ApplicationRunner, CommandLineRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("ApplicationRunner callback");
    }

    @Override
    public void run(String... args) {
        System.out.println("CommandLineRunner callback");
    }
}
```

In Spring Boot's runner invocation mechanism, such a bean can be picked up via both interfaces and both `run(...)` methods invoked during that runner pass.

Therefore, if the goal is a single task, **choose one of the two interfaces**. Avoid implementing both at once merely to receive both argument forms, as calling shared logic from both callbacks runs the work twice.

## 8. Equal Order Values: What Is Guaranteed?

Suppose two runners both declare:

```java
@Order(10)
```

or neither declares an order.

In this case, they have **equal priority**. Never rely on classpath scanning order, bean name order, or source file declaration order to enforce a business dependency between them.

Example:

```java
@Component
@Order(10)
public class InitializeA implements CommandLineRunner {
    @Override
    public void run(String... args) {
        System.out.println("A");
    }
}
```

```java
@Component
@Order(10)
public class InitializeB implements CommandLineRunner {
    @Override
    public void run(String... args) {
        System.out.println("B");
    }
}
```

If A must complete before B, give them distinct order values:

```java
@Order(10) // InitializeA
```

```java
@Order(20) // InitializeB
```

Do not write code that only works when runners sharing the same order happen by chance to run in a certain sequence.

### 8.1. Why Do Equal-Ordered Runners Sometimes Always Produce the Same Output?

A given Spring Boot version with the same classpath and bean registration setup may yield repeatable results across runs. That only reflects stable candidate collection/sorting in that environment, **not a business ordering contract** between two runners of equal order.

Upgrading Boot, changing component scanning, adding dependencies, or changing the build tool can alter candidate collection order.

### 8.2. When Is Strict Order Needed?

If steps must follow one another strictly, consider placing them inside **one coordinating runner**:

```java
@Component
public class ImportWorkflowRunner implements ApplicationRunner {

    private final PreparationService preparationService;
    private final ImportService importService;
    private final ReportService reportService;

    public ImportWorkflowRunner(
            PreparationService preparationService,
            ImportService importService,
            ReportService reportService
    ) {
        this.preparationService = preparationService;
        this.importService = importService;
        this.reportService = reportService;
    }

    @Override
    public void run(ApplicationArguments args) {
        preparationService.prepare();
        importService.importData();
        reportService.generate();
    }
}
```

This creates explicit ordering via method calls, making error handling and testing straightforward. `@Order` fits sorting **multiple independent startup tasks**, whereas a multi-step orchestration with strong dependencies usually belongs under a single coordinating entry point.

## 9. `@Order` Does Not Control Bean Creation Order

A common misconception is treating `@Order` on a runner as an instruction telling Spring to **instantiate that runner object before** other beans.

Those are two separate things.

Spring creates and injects required beans during context refresh. Only afterward does Boot sort the runner list and invoke `run(...)` methods.

```text
BEAN CREATION PHASE
  Constructor, dependency injection,
  @PostConstruct, initialization
               │
               ▼
      Context refresh completes
               │
               ▼
RUNNER EXECUTION PHASE
  Sort by @Order / Ordered
               │
               ▼
   Invoke run(...) sequentially
```

A `@Order(100)` runner can easily be instantiated by Spring before an `@Order(1)` runner if the dependency graph or refresh flow leads to that. What gets sorted is the **invocation of `run`**, not all bean creation steps.

### 9.1. Example Where Constructor and `run` Have Different Orders

```java
@Component
@Order(20)
public class LaterRunner implements CommandLineRunner {

    public LaterRunner() {
        System.out.println("Constructor LaterRunner");
    }

    @Override
    public void run(String... args) {
        System.out.println("Run LaterRunner");
    }
}
```

```java
@Component
@Order(10)
public class EarlierRunner implements CommandLineRunner {

    public EarlierRunner() {
        System.out.println("Constructor EarlierRunner");
    }

    @Override
    public void run(String... args) {
        System.out.println("Run EarlierRunner");
    }
}
```

At startup, the order of the two constructor lines depends on bean creation mechanics. However, the two `Run ...` lines are ordered as expected when no errors occur:

```text
Run EarlierRunner
Run LaterRunner
```

Do not inspect constructor logs to conclude that `@Order` is broken.

## 10. How Does `@DependsOn` Differ from `@Order`?

Spring's `@DependsOn` specifies that a bean must be initialized after one or more other beans.

Example:

```java
@Component
public class SetupRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Setup run");
    }
}
```

```java
@Component
@DependsOn("setupRunner")
public class ImportRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Import run");
    }
}
```

`@DependsOn("setupRunner")` guarantees the `setupRunner` bean is **initialized** before the `importRunner` bean per the declared dependency relationship. However, it **does not guarantee** that `setupRunner.run(...)` is invoked before `importRunner.run(...)`.

If you need runner execution order, use `@Order` or `Ordered`; if you need **bean initialization order**, use dependency injection or `@DependsOn` as appropriate.

### 10.1. Comparison Table

| Mechanism | What Does It Control? | When to Use? |
|---|---|---|
| `@Order` | Relative order when runners are invoked | Multiple runners in the startup phase |
| `Ordered#getOrder()` | Relative order when runners are invoked | Similar to `@Order`, value supplied by instance |
| `@DependsOn` | Before/after bean initialization relationship | One bean requires another bean initialized first |
| Constructor injection | Dependency needed to construct a valid object | Bean A needs instance B |
| `@PostConstruct` | Initialization callback of each individual bean | Preparing a bean after injection |
| `ApplicationReadyEvent` | Event after runners finish running | Actions waiting for the ready milestone |

Choose the tool matching the exact lifecycle milestone you need to control.

## 11. Runner `@Order` vs. Collection Injection `@Order`

`@Order` is used by Spring in multiple contexts. It can sort elements injected into a collection:

```java
@Component
@Order(10)
public class FirstValidator implements OrderValidator {
    // ...
}
```

```java
@Component
@Order(20)
public class SecondValidator implements OrderValidator {
    // ...
}
```

```java
@Service
public class ValidationService {

    private final List<OrderValidator> validators;

    public ValidationService(List<OrderValidator> validators) {
        this.validators = validators;
    }
}
```

Spring can populate `validators` in the order specified by the order metadata.

That shares the same idea of **sorting objects in a collection**, though the context differs from Spring Boot runner invocation. Do not assume `@Order` governs everything in Spring, such as singleton creation order, request handling order, or transaction commit order.

### 11.1. `@Order` Is Not `@Primary`

`@Primary` solves a different problem: when injecting **a single bean** and multiple candidates of the same type exist, Spring prefers the bean marked primary.

`@Order` is primarily used when **sorting a collection of candidates** or processing steps that support ordering.

Examples:

- Need to choose **one** `PaymentGateway` among multiple beans: consider `@Primary` or `@Qualifier`.
- Need to sort **multiple** `ApplicationRunner` beans: use `@Order` or `Ordered`.

Do not put `@Primary` on a runner expecting it to execute before other runners. Similarly, `@Order(1)` does not mean that bean is selected over others when injecting a single-valued interface.

## 12. Ordered, PriorityOrdered, and `@Priority`

In Spring's infrastructure, several related ordering concepts exist:

- `Ordered`: interface providing `getOrder()`.
- `PriorityOrdered`: specialized interface used by some Spring internals to distinguish a high-priority group in phases like bean post-processing.
- `@Priority`: Jakarta standard annotation recognized by comparators in certain contexts.
- `@Order`: Spring annotation for ordering metadata.

For sorting `ApplicationRunner` and `CommandLineRunner`, the two clear choices documented directly by Spring Boot are **`Ordered` and `@Order`**.

### 12.1. No Need for `PriorityOrdered` on Ordinary Runners

`PriorityOrdered` carries special meaning in certain internal Spring mechanisms, and should not be applied just to make a runner go first. For runners, use:

```java
@Order(Ordered.HIGHEST_PRECEDENCE)
```

or:

```java
@Override
public int getOrder() {
    return Ordered.HIGHEST_PRECEDENCE;
}
```

That expresses execution order directly.

### 12.2. `@Priority` Is Not `@Primary`

Even though the names look alike:

- Jakarta's `@Priority` relates to priority/order in mechanisms that support it.
- Spring's `@Primary` relates to selecting one bean when dependency injection finds multiple candidates.

Do not use `@Priority` as the default substitute for `@Order` in a startup runners guide when simple ordering numbers are all you need.

## 13. Complete Example: Three Runners with Both Ordering Mechanisms

Let's build a Spring Boot application with three steps:

1. Validate configuration before running.
2. Import data.
3. Print a report.

The first runner uses `Ordered`, while the other two use `@Order`; some are `ApplicationRunner` and another is `CommandLineRunner`.

### 13.1. Project Structure

```text
src/main/java/com/example/runnerdemo/
├── RunnerDemoApplication.java
└── startup/
    ├── ValidateConfigurationRunner.java
    ├── ImportDataRunner.java
    └── ReportRunner.java
```

Minimal dependency with Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Assumes the project has configured the Spring Boot Gradle plugin and a Java version compatible with the Boot release in use.

### 13.2. Main Application

```java
package com.example.runnerdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RunnerDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RunnerDemoApplication.class, args);
    }
}
```

### 13.3. First Runner: `Ordered` + `ApplicationRunner`

```java
package com.example.runnerdemo.startup;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;

@Component
public class ValidateConfigurationRunner
        implements ApplicationRunner, Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("01 - Validate configuration");

        if (args.containsOption("dry-run")) {
            System.out.println("Dry-run mode enabled");
        }
    }
}
```

### 13.4. Second Runner: `@Order` + `CommandLineRunner`

```java
package com.example.runnerdemo.startup;

import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(20)
public class ImportDataRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("02 - Import data");
    }
}
```

### 13.5. Third Runner: `@Order` + `ApplicationRunner`

```java
package com.example.runnerdemo.startup;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(30)
public class ReportRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("03 - Print report");
    }
}
```

### 13.6. Run and Observe

Run the program:

```bash
java -jar runner-demo.jar --dry-run
```

Illustrative runner log output:

```text
01 - Validate configuration
Dry-run mode enabled
02 - Import data
03 - Print report
```

Note: Spring Boot's own startup logs may appear before, after, or interleaved in various places. What is guaranteed here is **the invocation order of runners based on metadata**: `10`, `20`, `30`.

This mechanism does not depend on the first runner being `ApplicationRunner` and the second being `CommandLineRunner`.

### 13.7. Change Order to Verify

If you change `ReportRunner` to:

```java
@Order(5)
```

then the report runner will be called before validation and import:

```text
03 - Print report
01 - Validate configuration
Dry-run mode enabled
02 - Import data
```

This example deliberately creates an illogical business order so you can see that `@Order` only controls **technical execution order**. Spring does not know that reporting must follow importing unless you express that requirement yourself.

## 14. Using Runners as a Workflow: When Should You and Shouldn't You?

There are two ways to organize startup tasks.

### 14.1. Multiple Runners with Explicit Order

```text
@Order(10) ValidateRunner
           │
           ▼
@Order(20) PrepareRunner
           │
           ▼
@Order(30) ReportRunner
```

Suitable when steps are relatively independent, cleanly separated into distinct startup concerns, and ordering needs are simple.

However, when inserting a new runner in between, maintainers must know the numbering convention across the system.

### 14.2. One Orchestration Runner

```java
@Component
public class StartupWorkflow implements ApplicationRunner {

    private final DataValidator validator;
    private final DataImporter importer;
    private final ReportGenerator reporter;

    public StartupWorkflow(
            DataValidator validator,
            DataImporter importer,
            ReportGenerator reporter
    ) {
        this.validator = validator;
        this.importer = importer;
        this.reporter = reporter;
    }

    @Override
    public void run(ApplicationArguments args) {
        validator.validate();
        importer.importData();
        reporter.generate();
    }
}
```

Suitable when each step depends on the outcome of the prior step. Order lives directly inside `run`, making workflow-level transaction/exception handling and testing easy.

If a workflow needs retries, timeouts, checkpoints, or complex scheduling, consider a batch/job orchestration framework rather than simple runners.

## 15. How Errors in a Runner Affect the ApplicationReadyEvent Milestone

Suppose the runner with order 10 throws an exception:

```java
@Component
@Order(10)
public class ValidateRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        throw new IllegalStateException("Invalid configuration");
    }
}
```

When the exception goes unhandled, `SpringApplication.run(...)` can fail. Remaining runners may not run, and the application does not publish `ApplicationReadyEvent` along the successful startup path.

This can be the right behavior for mandatory validation: if configuration is invalid, the application should not receive traffic.

### 15.1. Avoid Swallowing Errors Just to Run Remaining Runners

Example:

```java
@Override
public void run(ApplicationArguments args) {
    try {
        validateConfiguration();
    } catch (Exception ex) {
        System.err.println("Validation failed: " + ex.getMessage());
    }
}
```

If validation fails yet the exception is swallowed, subsequent runners may continue executing in an invalid state.

Define an explicit error policy:

- Mandatory step: let the error fail startup or handle intentionally.
- Optional step: log and continue only when genuinely safe.
- Retryable step: design bounded retries/timeouts without blocking startup forever.

`@Order` only controls order; it does not provide transactions, retries, or error recovery.

### 15.2. Long-Running Runners Delay Readiness

```java
@Override
public void run(ApplicationArguments args) throws Exception {
    Thread.sleep(60000);
}
```

This example blocks the runner during startup. Because `ApplicationReadyEvent` fires after runners, readiness is delayed.

In HTTP-serving applications, evaluate how necessary the task is before readiness. If work can run after startup without compromising safe request handling, move it to an appropriate mechanism like an event, scheduler, or background worker instead of letting a runner block the startup path.

For CLI/batch apps, the runner may be the primary job itself, so waiting for completion is desired.

## 16. Running Runners in Multi-Instance Applications

Runners do not run "once for the entire system." They are called whenever **each ApplicationContext** starts through Spring Boot's process.

If you deploy three replicas of the same application:

```text
Replica A: start -> runners execute
Replica B: start -> runners execute
Replica C: start -> runners execute
```

A runner that creates an admin account, seeds data, or runs migrations can execute three times. `@Order` does not synchronize across replicas.

If an operation must execute once globally across the system, design additionally:

- Task idempotency.
- Database constraints or locks.
- Separate job/migration orchestration.
- Leader election or distributed locking where appropriate.

Do not use `@Order` numbers to solve cross-process concurrency problems.

### 16.1. Context Restarts or Integration Tests

Tests starting multiple independent contexts can cause runners to execute multiple times. If a runner writes data or calls external services, tests may produce unexpected side effects.

Use `@Profile`, `@ConditionalOnProperty`, or test configuration to control which runners are registered. This differs from `@Order`: conditions decide **whether a runner exists**, while order decides **whether it runs earlier or later** among existing runners.

## 17. `@Order` vs. ApplicationStartedEvent and ApplicationReadyEvent

Some developers try to use `@Order` to "run before a startup event." Yet runners and application events reside at different milestones.

Example:

```java
@Component
public class StartupEventLogger {

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("STARTED event");
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("READY event");
    }
}
```

And a runner:

```java
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class EarlyRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("RUNNER");
    }
}
```

Typical sequence:

```text
STARTED event
RUNNER
READY event
```

Even with the earliest runner order, it is still invoked **after `ApplicationStartedEvent`**. `@Order` does not alter `SpringApplication`'s lifecycle phases.

If you have multiple listeners for the same event, event listener ordering is a related yet separate mechanism. Do not treat a runner's order number and an event listener's order number as belonging to one global list.

### 17.1. When to Use Runners vs. Events?

| Goal | Appropriate Mechanism |
|---|---|
| Run task after context refresh, before app is ready | `ApplicationRunner` / `CommandLineRunner` |
| Observe the context-refreshed milestone | `ApplicationStartedEvent` listener |
| React once application reports ready | `ApplicationReadyEvent` listener |
| Initialize a single bean's internal state | `@PostConstruct` or init method |
| Initialize one bean after another bean | Dependency injection or `@DependsOn` |
| Run periodic scheduled jobs | `@Scheduled` or scheduler/job framework |

Choose the mechanism by **when it must run**, and only then apply ordering within that mechanism.

## 18. Ways to Define Runners with `@Bean`

Not every runner has to be a separate `@Component` class. You can also register them with `@Bean`:

```java
@Configuration(proxyBeanMethods = false)
public class StartupRunnerConfiguration {

    @Bean
    public CommandLineRunner loggingRunner() {
        return args -> System.out.println("Runner from @Bean");
    }
}
```

This is a bean implementing `CommandLineRunner` and will be invoked by Spring Boot at startup.

When explicit ordering across multiple runners is needed, a clear approach is declaring the runner via a class with `@Order` or implementing `Ordered`:

```java
public final class LoggingRunner
        implements CommandLineRunner, Ordered {

    @Override
    public int getOrder() {
        return 50;
    }

    @Override
    public void run(String... args) {
        System.out.println("Runner order 50");
    }
}
```

```java
@Configuration(proxyBeanMethods = false)
public class StartupRunnerConfiguration {

    @Bean
    public CommandLineRunner loggingRunner() {
        return new LoggingRunner();
    }
}
```

Spring Boot sorts runner objects by `getOrder()` regardless of whether they came from component scanning or `@Bean` methods.

### 18.1. Why Be Careful with Order Placed on Factory Methods?

Runner order is determined when Spring Boot retrieves **bean instances** and sorts them. If the returned bean is a lambda or an object without `Ordered`, order metadata placed elsewhere might not apply as expected across every version or proxy setup.

When order is an important requirement, express the intent directly on the **runner class** or `Ordered#getOrder()` on the returned instance. With `@Bean` configurations, this avoids misunderstandings.

## 19. Order Numbering Strategy in Real Projects

You do not have to use 1, 2, 3. Leaving gaps lets you insert future runners without renumbering everything:

| Runner Group | Example Order Range |
|---|---:|
| Validate mandatory configuration | 10–19 |
| Prepare resources | 20–29 |
| Seed or import data | 30–39 |
| Startup report/notification | 40–49 |

Example:

```java
@Order(10) // ValidateConfigurationRunner
```

```java
@Order(20) // PrepareCacheRunner
```

```java
@Order(30) // SeedDemoDataRunner
```

```java
@Order(40) // StartupSummaryRunner
```

This is purely an illustrative internal convention. Spring imposes no such ranges.

### 19.1. Should You Declare Constants?

If several runners in the same module share a convention, you can create constants:

```java
public final class StartupOrder {

    public static final int VALIDATION = 10;
    public static final int PREPARATION = 20;
    public static final int IMPORT = 30;
    public static final int REPORT = 40;

    private StartupOrder() {
    }
}
```

Usage:

```java
@Component
@Order(StartupOrder.VALIDATION)
public class ValidationRunner implements CommandLineRunner {
    // ...
}
```

Annotation arguments must be compile-time constants. `public static final int` fields initialized with literals satisfy that rule.

If the project is very small, writing `@Order(10)` directly can be clear enough. Constants help when many classes share one ordering scheme.

### 19.2. What If You Want Order Configured by Property?

The `@Order` annotation value is a compile-time constant in source code. If you truly need an order value determined dynamically in code, implement `Ordered` and return the appropriate value.

However, letting startup order vary dynamically through configuration can make diagnostics difficult. Keep the order of mandatory initialization steps simple and predictable.

## 20. Common Mistakes and Misconceptions

| Symptom | Cause or Misconception to Revisit | Remediation |
|---|---|---|
| Runner never executes | Class was not registered as a bean | Check `@Component`, `@Bean`, and component scanning |
| Two runners run in unexpected order | Missing order or identical order values | Declare distinct values |
| `@Order(100)` runs after `@Order(1)` | Lower numbers have higher precedence | That is the intended rule |
| Runner instantiated first yet `run` runs later | Bean initialization differs from runner execution | Observe the right phase |
| `@DependsOn` did not make `run` execute first | `@DependsOn` primarily controls bean initialization | Use `@Order`/`Ordered` to sort runners |
| Mix of ApplicationRunner and CommandLineRunner | Both types are sorted together | Do not infer order from interface type |
| Runner has earliest order yet STARTED event still runs first | Order does not alter lifecycle phases | Pick event or runner for the needed milestone |
| Application not ready | Runner threw exception or runs too long | Inspect runner errors and duration |
| Runner runs multiple times across replicas | Runners execute per context/process | Design idempotency or orchestration |
| `@Primary` did not make runner run first | `@Primary` applies to single-bean selection | Use `@Order` or `Ordered` |
| Runner implementing both interfaces runs two callbacks | Both `run` overloads can be called | Implement one interface for a single task |
| `HIGHEST_PRECEDENCE` is a huge negative number | Comparator prioritizes smaller numbers first | Do not interpret "highest" as largest integer |

### 20.1. Reading Logs Correctly

When observing order, print separate logs in the constructor and in `run`:

```java
public ExampleRunner() {
    System.out.println("constructor");
}

@Override
public void run(String... args) {
    System.out.println("runner");
}
```

When comparing ordering, rely only on `run` logs to verify runner order. Constructor logs reflect the bean creation phase.

### 20.2. Do Not Guess from Package Order

Classes may happen to scan in an apparently stable order. Yet if ordering is a business requirement, declare it explicitly. Do not name classes `AFirstRunner` and `BSecondRunner` trying to force Spring to run alphabetically.

## 21. Workflow for Diagnosing Runner Order

When an application has multiple runners and order differs from expectations, follow this sequence:

1. **Confirm each runner is a bean.** Check `@Component`, `@Bean`, profiles, and conditional registration.
2. **List effective order values.** Read the annotation for `@Order`; inspect `getOrder()` for `Ordered`.
3. **Check if a runner uses both mechanisms.** `Ordered` can override the annotation value.
4. **Ensure dependent steps have distinct values.** Avoid equal order values for dependent steps.
5. **Separate constructor logs from `run` logs.** Bean creation order does not reflect runner order.
6. **Check for both ApplicationRunner and CommandLineRunner.** They are sorted together.
7. **Look for exceptions or blocking tasks.** An earlier runner failing or hanging can stop later runners from running.
8. **Check context/process counts.** Multiple replicas or test contexts produce independent runner log sequences.
9. **Review design.** If steps depend tightly on each other, consider one orchestrating runner.

Minimal log example:

```text
[RUNNER order=10] validate
[RUNNER order=20] prepare
[RUNNER order=30] import
[RUNNER order=40] report
```

Including the order value in logs is very helpful when multiple modules or plugins contribute runners.

## 22. Practice Exercises

### Exercise 1 — Two CommandLineRunners

Create two `CommandLineRunner` beans annotated with `@Order(10)` and `@Order(20)`. Run the application, then swap the two values and observe the log order change.

### Exercise 2 — Combining Both Runner Types

Create an `ApplicationRunner` with `@Order(5)` and a `CommandLineRunner` with `@Order(10)`. Predict the order, then run to confirm runners are sorted together.

### Exercise 3 — `Ordered` Interface

Replace `@Order` on a runner with `implements Ordered` returning `getOrder() = -10`. Observe that runner executing before runners with larger order values.

### Exercise 4 — Equal Order Values

Create two runners both with `@Order(10)`. Observe the outcome, then explain why you should not rely on that order to build workflows. Change them to `10` and `20` if a real dependency exists.

### Exercise 5 — Bean Initialization Differs from Runner Execution

Log inside the constructor, `@PostConstruct`, and `run` of two runners. Observe how initialization lines may not follow `@Order` while `run` calls are sorted.

### Exercise 6 — `@DependsOn`

Give runner B `@DependsOn("runnerA")`, yet make B's `@Order` smaller than A's. Observe and explain the difference between **bean creation** order and **`run` execution** order.

### Exercise 7 — Startup Error

Make the runner with the smallest order throw `IllegalStateException`. Observe subsequent runners and `ApplicationReadyEvent` emission. Then handle the failure intentionally to restore startup.

### Exercise 8 — Using ApplicationArguments

Create an `ApplicationRunner` reading `--mode=import`. Add an earlier data-preparation runner using `@Order`. Explain when to use `ApplicationArguments` instead of `String... args`.

### Exercise 9 — One Orchestration Runner

Combine three steps—validate, import, report—into one `ApplicationRunner`. Compare readability, error handling, and testability against three separate runners with `@Order`.

### Exercise 10 — Multiple Instances

Simulate starting two ApplicationContexts. Observe runners running twice and discuss how to ensure a data-seeding task does not create duplicate records.

## 23. Official References

- [Spring Boot Reference — SpringApplication: CommandLineRunner and ApplicationRunner](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.command-line-runner): runner lifecycle and ordering guidance with `Ordered` or `@Order`.
- [Spring Boot API — ApplicationRunner](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/ApplicationRunner.html): `run(ApplicationArguments)` method.
- [Spring Boot API — CommandLineRunner](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/CommandLineRunner.html): `run(String... args)` method.
- [Spring Framework API — Ordered](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/Ordered.html): `getOrder()` and precedence constants.
- [Spring Framework API — Order](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/annotation/Order.html): annotation declaring order.
- [Spring Boot Reference — Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-events-and-listeners): position of `ApplicationStartedEvent` and `ApplicationReadyEvent` in startup.

**`Ordered` and `@Order` determine the invocation order of runners in Spring Boot.** Smaller order values run earlier; `ApplicationRunner` and `CommandLineRunner` share the same sorted list. This sorting happens after context refresh, so runner order cannot be used to control bean constructors or `@PostConstruct`. When tasks have tight dependencies, express execution order and error handling explicitly, such as through a single coordinating runner rather than relying solely on order numbers.
