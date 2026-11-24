# SpringApplication.exit and Returned Exit Code Values in Spring Boot

## 1. What is an exit code and why does an application need it?

When a Java process terminates, the operating system and the program that launched it can receive a **process exit status**. By common convention, **0** indicates success, while a **non-zero value** indicates a condition needing attention or a failure according to the application's contract.

For a Spring Boot program used to run CLI commands, batch imports, scheduled tasks, or per-run workers, exit codes help:

- Shell scripts know whether to proceed to the next step.
- CI/CD jobs mark success or failure.
- Kubernetes Jobs determine whether a container finished successfully.
- Schedulers and batch orchestrators distinguish between error types.
- Monitoring tools and operators know the final outcome of a process.

Spring Boot provides the method:

```java
int code = SpringApplication.exit(context);
```

However, **two things that are often confused are distinct**:

1. `SpringApplication.exit(context)`: lets the application **close the `ApplicationContext` if possible**, computes an **`int` exit code** from supported sources, and **returns the code to the calling Java code**.
2. `System.exit(code)`: instructs the **JVM to terminate with the supplied exit code**, so the parent process/OS can observe that status.

Therefore:

```java
int code = SpringApplication.exit(context);
```

**is not automatically equivalent to**:

```java
System.exit(SpringApplication.exit(context));
```

In the first snippet, Java receives an `int` variable and can continue running subsequent statements. In the second snippet, after Spring handles exit and returns the code, `System.exit` actively instructs the JVM to terminate. This distinction matters when used in tests, libraries, HTTP services, or programs with resources needing cleanup.

This lesson targets **Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+**. We will clarify the API, code sources, generator ordering, shutdown mechanics, error types, a runnable example, how to verify exit status in shells, and anti-patterns to avoid.

## 2. Three concepts that must be kept separate

| Concept | API/Behavior | Meaning |
| --- | --- | --- |
| Closing the bean container | `ConfigurableApplicationContext.close()` | Stops the Spring context, runs lifecycle/destroy callbacks; does not return a business exit code |
| Computing exit code and closing context | `SpringApplication.exit(context, generators...)` | Returns an `int`, collects `ExitCodeGenerator` instances, attempts to close the context |
| Terminating the JVM with an exit code | `System.exit(code)` | Requests the JVM to terminate with a code sent to the operating system |

For example:

```text
SpringApplication.run(...)
      |
      v
ConfigurableApplicationContext is active
      |
      +--> SpringApplication.exit(context)
      |          |
      |          +--> Collect ExitCodeGenerator beans
      |          +--> Combine directly passed generators
      |          +--> Determine first non-zero code in order
      |          +--> Close ApplicationContext if possible
      |          +--> return int code
      |
      +--> Java main can process the code
                 |
                 +--> Print logs, test, return internal status
                 |
                 +--> System.exit(code) if you truly want the JVM to terminate
```

This diagram illustrates API semantics, not an internal method-by-method stack trace. The exact order of error handling, event publishing, and destroy callbacks belongs to the implementation; the key public contract is **returning the code** and **closing the context if possible**.

### 2.1. Closing the context does not necessarily mean terminating the process

In a simple non-web application, after the context closes, there may be no remaining non-daemon threads keeping the JVM alive, so the process terminates naturally when `main` returns. However, that is due to **Java thread liveness rules**, not because `SpringApplication.exit` called `System.exit`.

If your code creates an `ExecutorService` that is not shut down or a library holds a non-daemon thread outside Spring, closing the context does not guarantee the JVM terminates. Conversely, calling `System.exit` abruptly can terminate the JVM while tasks are still not safely handled.

### 2.2. A return code of 0 is not proof that the entire infrastructure is healthy

A code of `0` may simply mean the application **had no `ExitCodeGenerator` reporting an error**. It does not prove:

- Every historical request succeeded.
- No background task failed silently without being recorded.
- All data was committed or sent successfully.
- All cleanup callbacks succeeded.
- A web application was ready before it stopped.

You must design **code calculation rules based on real business outcomes**, and test failure paths. Do not treat exit codes as a replacement for logs, tracing, metrics, or job state.

## 3. Signature and contract of SpringApplication.exit

In Spring Boot 3.3, the API in `org.springframework.boot.SpringApplication` is:

```java
public static int exit(
        ApplicationContext context,
        ExitCodeGenerator... exitCodeGenerators);
```

Calling without extra generators:

```java
int code = SpringApplication.exit(context);
```

Calling with an explicit generator:

```java
int code = SpringApplication.exit(context, () -> 5);
```

`ExitCodeGenerator` resides in package `org.springframework.boot` and is an interface with a single method `getExitCode()`, so it can be written as a lambda.

Points confirmed by the Spring Boot 3.3 Javadoc:

1. The method helps terminate a `SpringApplication` and obtain an **integer code**: `0` for success per exit-code rules, or non-zero when an appropriate outcome occurs.
2. It uses **the `ExitCodeGenerator` instances you pass via varargs** plus **Spring beans implementing `ExitCodeGenerator`** in the context.
3. If multiple generators exist, the **first non-zero code in sorted order** is selected.
4. Order is controlled via `Ordered` or `@Order`.
5. The method attempts not to throw exceptions to the caller; errors encountered during processing may be logged/printed as stack traces. Do not interpret this as "cleanup always succeeds."
6. The context is **closed if possible**.

### 3.1. Do not confuse the context parameter with an OS exit command

The parameter is `ApplicationContext`, not a PID, shell command, initial exit code, or `SpringApplication` instance. Code should only call it after a context has actually been created successfully (unless you are handling an API failure per a dedicated contract).

```java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApp.class, args);

int code = SpringApplication.exit(context);
```

This is a snippet inside `main` of a project containing class `MyApp`. After calling `exit`, **do not continue using beans from this context to process new work**.

### 3.2. Do not call exit twice to "re-fetch the code"

Once `SpringApplication.exit(context)` closes the context, the bean lifecycle has entered shutdown state. Subsequent calls are not a reliable protocol for recomputing results; do not write business flows relying on calling `exit` multiple times.

**Good design:** only one owner decides when to terminate and calls `SpringApplication.exit` once; store the returned code variable and use it.

## 4. ExitCodeGenerator: the primary source for determining outcomes

Interface:

```java
package org.springframework.boot;

@FunctionalInterface
public interface ExitCodeGenerator {
    int getExitCode();
}
```

This is an API signature description (not a file to redefine yourself, as the interface is already in Spring Boot). A bean implementing the interface can decide the code based on a job result or controlled business state.

### 4.1. Registering a generator as a @Bean

```java
@Bean
ExitCodeGenerator jobExitCode(JobResult result) {
    return () -> result.isSuccessful() ? 0 : 12;
}
```

This is a **snippet in a configuration class**, assuming `JobResult` is a business bean with `isSuccessful()`. Spring discovers `ExitCodeGenerator` beans when `SpringApplication.exit` computes the code.

Goal: **the task outcome determines the exit status**, rather than hardcoding `System.exit(1)` in many places.

### 4.2. Passing a generator directly

```java
int exitCode = SpringApplication.exit(context, () -> 17);
```

This approach is convenient when `main` already knows the result of the command just executed. Directly passed generators participate alongside existing generator beans; if existing beans already return a non-zero code, do not assume `17` is guaranteed to win. You need to understand **generator ordering** and the "first non-zero" rule.

### 4.3. Only one generator returning 0 vs multiple generators

If the system has only one generator and it returns `0`, the result is `0`. If an earlier generator returns `0` and a later generator returns `9`, the system continues evaluating and selects `9` according to the applied order.

**`0` means "no error from this source"**, not a signal that forces evaluation of the remaining generators to stop.

## 5. When multiple ExitCodeGenerators exist: order matters

Suppose three generators yield:

| Generator | Priority order | `getExitCode()` |
| --- | ---: | ---: |
| Configuration check | 10 | 0 |
| Data validation | 20 | 14 |
| External system check | 30 | 7 |

Under Spring Boot 3.3's **first non-zero** rule, the selected code is **14**, not `7`, not `14 + 7 = 21`, and not automatically the numerically largest code.

### 5.1. Type-safe example with Ordered

```java
package com.example.exit;

import org.springframework.boot.ExitCodeGenerator;
import org.springframework.core.Ordered;

public final class OrderedExitCode
        implements ExitCodeGenerator, Ordered {

    private final int code;
    private final int order;

    public OrderedExitCode(int code, int order) {
        this.code = code;
        this.order = order;
    }

    @Override
    public int getExitCode() {
        return code;
    }

    @Override
    public int getOrder() {
        return order;
    }
}
```

This is a **complete Java file** in a Spring Boot 3.3 project: `src/main/java/com/example/exit/OrderedExitCode.java`. A configuration class can create:

```java
@Bean
ExitCodeGenerator configResult() {
    return new OrderedExitCode(0, 10);
}

@Bean
ExitCodeGenerator dataResult() {
    return new OrderedExitCode(14, 20);
}

@Bean
ExitCodeGenerator dependencyResult() {
    return new OrderedExitCode(7, 30);
}
```

These are **illustrative methods** inside a `@Configuration`/`@SpringBootApplication` class importing `@Bean` and `ExitCodeGenerator`. If all three are registered in the specified order, the prioritized result is **14**.

**Do not copy these three extra beans into the demo project in section 8** if you want to keep the exact output shown in the practice section; they are two independent examples.

### 5.2. Ordered and @Order

Spring Boot supports `Ordered` or `@Order` to determine generator order. In Spring, a **smaller** order value typically means **higher** priority. Implementing `Ordered` on the object is clearer when code needs to decide priority at runtime.

If two generators have the same priority, **do not rely on unguaranteed registration order** to decide an important code. Assign distinct orders or centralize error rules into one aggregating generator.

### 5.3. Exit codes are a contract, not random integers

A batch system might use:

```text
0  = Completed successfully
2  = Invalid arguments or configuration
4  = Business validation failed
8  = External dependency unavailable
16 = Internal error that requires investigation
```

This is an **illustrative convention table chosen by the application**, not mandatory standard codes from Spring Boot. Which values are used, whether to retry, and scheduler consequences must be documented in operational runbooks.

Avoid directly using HTTP statuses such as 404 or 503 as process exit codes. HTTP statuses and process statuses belong to different protocols; in some shells/OSes, large values may be represented or truncated differently than expected.

## 6. Why must you call System.exit to pass the code to the OS?

Consider two programs:

**Case A — only compute the code and close the Spring context:**

```java
int code = SpringApplication.exit(context);
System.out.println("Computed code = " + code);
```

Java code can continue executing after `println`. If `main` finishes normally and no other mechanism forces an exit code on the JVM, the OS may receive **0** even though `code` holds `7`.

**Case B — pass the code to the JVM:**

```java
int code = SpringApplication.exit(context);
System.exit(code);
```

The `System.exit` call tells the JVM to stop with that code. This is the pattern in Spring Boot documentation for command-line programs whose process **must report an outcome** to a runner or scheduler.

### 6.1. Where should System.exit be placed?

Usually only the **`main` entrypoint** or an orchestration layer at the application boundary should decide to terminate the **entire JVM**. Do not arbitrarily call `System.exit` in:

- A controller handling an HTTP request.
- A reusable repository or business service.
- A listener that may be invoked multiple times.
- `@PostConstruct` or a bean constructor.
- Unit tests sharing a JVM with other tests.
- Library code used across multiple applications.

If only a single request fails, return an appropriate HTTP error/failure response; **do not stop the entire JVM**.

### 6.2. System.exit is not automatic graceful orchestration

`System.exit` triggers JVM shutdown and shutdown hooks, but **does not replace designing traffic draining, stopping producers, awaiting tasks, committing transactions, and cleaning up resources**.

Calling `SpringApplication.exit(context)` before `System.exit(code)` is a sensible way to give Spring a chance to run lifecycle callbacks. However, if a running task is stuck or the OS kills the container due to timeout, cleanup steps can still be cut short.

## 7. How do SpringApplication.exit and ApplicationContext.close differ?

`ConfigurableApplicationContext.close()` closes the context without computing a business code from `ExitCodeGenerator` instances.

```java
context.close();
// No int value returned from close().
```

`SpringApplication.exit(context)` additionally evaluates generators and returns the code:

```java
int code = SpringApplication.exit(context);
// After exit, the context is normally closed.
```

Therefore, if a batch application needs an exit code, do not just call `context.close()` and assume Spring will automatically pass the job status to the OS.

### 7.1. No need to double-close with try-with-resources

`ConfigurableApplicationContext` is `AutoCloseable`; you can write:

```java
try (ConfigurableApplicationContext context =
             SpringApplication.run(MyApp.class, args)) {
    // Work with context.
}
// Auto-closes, but does not invoke ExitCodeGenerator.
```

This is a snippet in a program that has `MyApp`. If you need a code from `SpringApplication.exit(context)`, a single owner in `main` can explicitly call it **once**. Do not combine try-with-resources closing with arbitrary calls to `exit` across multiple paths and assume callbacks will execute exactly once as intended.

### 7.2. What about web applications?

`SpringApplication.exit(context)` can close a web `ApplicationContext` and stop the embedded web server according to lifecycle rules. However, it is not a safe default HTTP admin endpoint. A web service serving multiple clients needs:

- Readiness/traffic draining.
- Stopping acceptance of new work.
- Stopping the server and handling in-flight requests.
- Stopping schedulers, message consumers, and background workers.
- Ensuring dependencies close after consumers.
- Coordinating Spring Boot and Kubernetes shutdown deadlines.

The `int` code from `SpringApplication.exit` should not be used as an HTTP response status.

## 8. Complete Spring Boot 3.3 example: compute exit code without forcing JVM exit

The goal is to **run and observe** without abruptly forcing the process to stop on the first trial. The demo includes:

- A **non-web** Spring Boot app (`WebApplicationType.NONE`).
- An `ExitCodeGenerator` bean reading its value from property `demo.exit-code`.
- An `ApplicationRunner` simulating work.
- A resource bean with `close()` to prove the context is destroyed.
- After `SpringApplication.exit(context)`, the program prints the code and the context's active state.
- An optional `--demo.os-exit=true` flag to actually call `System.exit(code)` and pass the code to the OS.

### 8.1. Directory structure

```text
exit-code-lesson/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/com/example/exit/
    ExitCodeLessonApplication.java
```

### 8.2. settings.gradle

```groovy
rootProject.name = 'exit-code-lesson'
```

### 8.3. build.gradle (Groovy DSL)

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

This is a basic build script usable with Java 17+ and Spring Boot 3.3.13. The `./gradlew` commands assume the project has a **Gradle Wrapper**; you can generate the project via Spring Initializr or generate the wrapper with Gradle if needed.

### 8.4. application.properties

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off

# Business code to observe; defaults to success.
demo.exit-code=0

# Do not force System.exit while learning.
demo.os-exit=false
```

The example uses Java `main` to check the `--demo.os-exit=true` option. Properties in the file and command-line arguments are processed by Spring Boot through standard configuration sources; CLI values generally take higher precedence than file properties.

### 8.5. ExitCodeLessonApplication.java — complete code

```java
package com.example.exit;

import java.util.Arrays;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class ExitCodeLessonApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ExitCodeLessonApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context = application.run(args);

        // Spring closes the context and returns the exit code without calling System.exit.
        int exitCode = SpringApplication.exit(context);

        System.out.println("RETURNED_EXIT_CODE=" + exitCode);
        System.out.println("CONTEXT_ACTIVE=" + context.isActive());

        // Opt-in only at the entrypoint if you truly want the OS to receive the code.
        if (Arrays.asList(args).contains("--demo.os-exit=true")) {
            System.exit(exitCode);
        }
    }

    @Bean
    ExitCodeGenerator configuredExitCode(Environment environment) {
        return () -> environment.getProperty(
                "demo.exit-code", Integer.class, 0);
    }

    @Bean
    DemoResource demoResource() {
        return new DemoResource();
    }

    @Bean
    ApplicationRunner sampleJob(DemoResource resource) {
        return args -> System.out.println("RUNNER_DONE");
    }

    public static final class DemoResource
            implements AutoCloseable {

        @Override
        public void close() {
            System.out.println("RESOURCE_CLOSED");
        }
    }
}
```

**This is a complete Java file**, requiring no external classes, server, or database. `DemoResource` is a nested class of the application, created as a Spring bean via `@Bean`. Spring recognizes `AutoCloseable.close()` to invoke when the bean is destroyed; if you want a more explicit contract, you can use `@Bean(destroyMethod="close")` on the resource factory method.

Key points:

1. `application.run(args)` creates the context and runs the runner normally.
2. `sampleJob` depends on `DemoResource`, so the resource is created before the runner executes.
3. `configuredExitCode` is an `ExitCodeGenerator` bean. When `SpringApplication.exit` is called, the generator reads the `demo.exit-code` property.
4. `SpringApplication.exit(context)` determines `int exitCode`, closes the context, and triggers `DemoResource.close()`.
5. After `exit` returns, `main` prints `RETURNED_EXIT_CODE` and `CONTEXT_ACTIVE`.
6. Only when the CLI contains the exact string `--demo.os-exit=true` does `main` call `System.exit(exitCode)`.
7. Without calling `System.exit`, this non-web program normally finishes when `main` returns and no non-daemon threads remain, so the process status does not necessarily equal `RETURNED_EXIT_CODE` if the code is non-zero.

### 8.6. Default run

In the directory containing the Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows CMD:

```bat
gradlew.bat bootRun
```

Output of **the lines printed by the demo itself** in order on the success path:

```text
RUNNER_DONE
RESOURCE_CLOSED
RETURNED_EXIT_CODE=0
CONTEXT_ACTIVE=false
```

Banners and standard logs were reduced via properties, but Gradle/Spring may still print other output. There is no promise that **all stdout** consists solely of those four lines.

### 8.7. Try a non-zero code WITHOUT passing it to the OS yet

Run:

```bash
./gradlew bootRun --args="--demo.exit-code=7"
```

Demo output:

```text
RUNNER_DONE
RESOURCE_CLOSED
RETURNED_EXIT_CODE=7
CONTEXT_ACTIVE=false
```

Because `main` did not call `System.exit(7)`, the run can still finish **successfully at the JVM/Gradle level** even though it printed `RETURNED_EXIT_CODE=7`. This is the most important distinction in this lesson.

**Do not use this case to test that CI/CD or a scheduler receives code 7.** It only proves that **SpringApplication.exit returns 7**.

### 8.8. Actually passing the code to the OS

In the same project, build the executable JAR:

```bash
./gradlew bootJar
```

Then run (filename matches `group`/`version` in the example):

```bash
java -jar build/libs/exit-code-lesson-0.0.1-SNAPSHOT.jar \
  --demo.exit-code=7 --demo.os-exit=true
```

The lines printed by the demo code remain:

```text
RUNNER_DONE
RESOURCE_CLOSED
RETURNED_EXIT_CODE=7
CONTEXT_ACTIVE=false
```

But this time the JVM had `System.exit(7)` invoked. On common shells, the corresponding process status is reported to the parent program.

In Bash/zsh, run **immediately after the java command**:

```bash
echo $?
```

Expected output:

```text
7
```

Windows PowerShell:

```powershell
$LASTEXITCODE
```

Windows CMD:

```bat
echo %ERRORLEVEL%
```

The inspection command must be executed **immediately after the process being measured**, because running another command can overwrite the exit status remembered by the shell.

If `--demo.exit-code=0 --demo.os-exit=true` is passed, the code sent to the OS will be 0 and is normally treated as success.

### 8.9. Why not use Gradle bootRun to prove every OS code?

`bootRun` is a Gradle task that spawns a Java process and may turn a non-zero process exit into a **Gradle task failure**. When that happens, the exit status of the `gradlew` command itself is not guaranteed to remain equal to the number you passed to `System.exit` in Java. To verify the application's actual exit code, run **`java -jar` directly** (or a wrapper contracted to preserve exit status).

This is not a bug in `SpringApplication.exit`; it is the difference between the **application child process** and the **build-tool parent process**.

## 9. ExitCodeEvent: observing the determined code

Spring Boot includes `org.springframework.boot.ExitCodeEvent`. The Javadoc describes it as an application event published when an exit code is determined from an `ExitCodeGenerator`.

Primary API:

```java
int code = event.getExitCode();
```

A listener can be used for logging/telemetry:

```java
@Component
public class ExitCodeAudit {

    @EventListener
    public void onExitCode(ExitCodeEvent event) {
        System.out.println("EXIT_EVENT_CODE=" + event.getExitCode());
    }
}
```

This is an **illustrative class** placed in a Spring-scanned package, requiring imports for `@Component`, `@EventListener`, and `ExitCodeEvent`. Do not add this class to the demo if you want to keep the four-line stdout from section 8.

Do not use an event handler to **alter** the code by calling `System.exit` or throwing an exception: an event is a notification; the place deciding process termination must retain clear ownership. Nor should you base correctness on expecting a specific event to appear in every case returning 0 or every startup failure path; follow each phase's contract.

### 9.1. ExitCodeEvent differs from ContextClosedEvent

- `ExitCodeEvent` is about **the determined code** in Boot's exit-code mechanism.
- Spring Framework's `ContextClosedEvent` states that **the context is closing**.
- A context can be closed via `context.close()` or a shutdown hook **without** the application computing an exit code from `ExitCodeGenerator`.
- When `SpringApplication.exit` is called, an exit-code-related event may be published and then the context closed; listeners for each event must handle the right type.
- `ApplicationFailedEvent` belongs to the **startup failure path**, not merely because an application intentionally exited non-zero after a job.

Do not conflate a "process ending" event with every kind of shutdown event.

## 10. Exceptions can also provide ExitCodeGenerator

Spring Boot 3.3 documentation allows an exception to implement `ExitCodeGenerator` to supply an exit code when a specific error is handled in Spring Boot's failure path.

Example:

```java
package com.example.exit;

import org.springframework.boot.ExitCodeGenerator;

public final class InvalidImportException
        extends RuntimeException
        implements ExitCodeGenerator {

    public InvalidImportException(String message) {
        super(message);
    }

    @Override
    public int getExitCode() {
        return 12;
    }
}
```

This is a **complete Java file** meant to represent an error type; it does not trigger a startup failure by itself. If a runner or bean throws this exception type during startup, Spring Boot can use `getExitCode()` in its error-handling mechanism.

**Important:** if `SpringApplication.run(...)` throws an exception, the next call:

```java
System.exit(SpringApplication.exit(
        SpringApplication.run(MyApp.class, args)));
```

**cannot execute along the normal success branch**, because `run` did not return a context. Spring Boot has dedicated failure/exit-code handling for this situation; do not think your code in `main` actively called `SpringApplication.exit` with a valid context.

How the OS/launcher ultimately represents the failure code also depends on the startup failure path and how the process was launched. For a production job, test the **actual process exit code** in the script/container in use.

### 10.1. Do not use exceptions for normal business outcomes

If a job processes 10,000 records and detects three records that failed validation while still finishing, you can use a business outcome stored in `JobResult` and a generator bean instead of throwing an exception for the whole run.

Exceptions should express **abnormal failure paths**; exit-code beans are suited for intentionally mapping a job's final state.

## 11. ExitCodeExceptionMapper: mapping errors to meaningful codes

Spring Boot also provides `org.springframework.boot.ExitCodeExceptionMapper`, used to map a `Throwable` to a code:

```java
int getExitCode(Throwable exception);
```

A sample mapper bean:

```java
@Bean
ExitCodeExceptionMapper invalidImportMapper() {
    return error -> {
        Throwable current = error;

        while (current != null) {
            if (current instanceof InvalidImportException) {
                return 12;
            }
            current = current.getCause();
        }

        return 0;
    };
}
```

This is a **snippet in a configuration class**, requiring imports for `ExitCodeExceptionMapper` and the `InvalidImportException` class defined in section 10. It illustrates walking the cause chain because the root exception may be wrapped by another exception.

When Spring Boot handles errors in phases where mapper beans have been created and are accessible, the mapper can contribute the appropriate code. **Do not rely on a mapper bean working for very early errors**, before the context has initialized enough for that bean to exist. For errors such as unreadable configuration, classpath load failures, or the JVM failing to run `main`, Spring bean mechanisms may not yet be ready.

### 11.1. What does 0 from a mapper mean?

In the mapper contract, `0` can be used to indicate this mapper **does not assign a special code** to the given exception. When multiple mappers/generators exist, determine priority and verify the result on the Spring Boot version you use; do not assume a mapper returning 0 will always clear an error status already determined by another mapper.

### 11.2. Avoid mixing error logic across multiple layers

Do not simultaneously have an exception implement `ExitCodeGenerator`, another mapper returning a conflicting code for that same exception, plus a failing job generator bean, unless you have clearly defined the precedence contract.

For exercises, choosing one of the two error mechanisms is enough:

- Have the exception implement `ExitCodeGenerator` if the exception type itself **carries exit-code semantics**.
- Use `ExitCodeExceptionMapper` if you want to decouple error classification from the exception class.

For job outcomes after running cleanly until intentional exit, use an `ExitCodeGenerator` bean or a directly passed generator.

## 12. Exit codes in batch/CLI differ from HTTP and availability

A Spring Boot application can run in three main styles:

| Application style | Primary signal to orchestrator |
| --- | --- |
| One-off CLI | **Process exit code** |
| Kubernetes Job/CronJob | Container/process exit status and Job status |
| Long-running HTTP service | Readiness, liveness, request responses, logs, metrics |
| Long-running consumer | Liveness/readiness, consumer state, and restart/checkpoint mechanisms |

**Do not** call `SpringApplication.exit` at the end of every HTTP request. Closing the context affects all users and background tasks sharing it.

### 12.1. A successful job should usually terminate on its own

For CLI/batch, the termination milestone is typically:

```text
Start JVM
   |
SpringApplication.run()
   |
ApplicationRunner / CommandLineRunner
   |
Job result completed and recorded
   |
SpringApplication.exit(context)
   |
System.exit(code) if exact OS reporting is needed
   |
Scheduler/CI/CD reads process exit status
```

If code must run long-term, **do not** actively close the context right after startup just to return a code 0.

### 12.2. For Kubernetes

A pod running a **Job** is tracked by the platform via its exit status and pod phase. Non-zero codes usually cause the Job to retry/fail according to `backoffLimit` and restart policy, though exact behavior depends on manifest and infrastructure.

For a **Deployment** or long-running server, do not use the application exit code as a traffic-control mechanism replacing readiness. If an instance cannot recover internally, you can use `LivenessState` and appropriate liveness probes; when you need to temporarily stop receiving traffic, use readiness. These mechanisms are not synonymous with the code returned from `SpringApplication.exit`.

## 13. Exit codes and OS status: limits to know

Java's `System.exit(int)` accepts an `int`, but operating systems and shells have their own status representation rules.

- **0** normally means success.
- **Non-zero** is normally treated as failure or a state requiring handling.
- On common Unix shells, the observable status portion usually lies in the **low 8 bits** for normal exit statuses; codes above 255 or negative may not be preserved as the original Java integer.
- On Windows, command processors have different representations and status variables than Unix.
- Build tools, Docker wrappers, scripts, or schedulers may accept or transform codes per their own contracts.

**Recommendation:** use a **small, positive, stable** set of codes, e.g., 0, 2, 4, 8, 16. Document their meanings, maintain pipeline compatibility, and avoid random numbers or HTTP-like statuses.

### 13.1. Bash set -e can abort a script before echoing status

Example:

```bash
set +e
java -jar build/libs/exit-code-lesson-0.0.1-SNAPSHOT.jar \
  --demo.exit-code=7 --demo.os-exit=true
code=$?
echo "Java exit status: $code"

if [ "$code" -ne 0 ]; then
    echo "Job failed"
    exit "$code"
fi
```

This is a snippet for Bash/sh; it assumes the demo JAR has been built. If the script previously enabled `set -e`, a command returning non-zero can cause the shell to exit before you save `$?`; therefore, handle status deliberately.

Do not write:

```bash
java -jar app.jar
echo "Job completed"
```

and assume the job succeeded, if the code actually returned a non-zero status that the script ignored. Shell pipelines must define explicit success/failure conditions.

## 14. How do shutdown hooks and @PreDestroy relate?

Spring Boot normally registers a JVM shutdown hook to close the `ApplicationContext` when the process terminates along an appropriate path. Therefore, for many web applications, sending an orderly stop signal can trigger bean destruction callbacks even when code never calls `SpringApplication.exit` itself.

However:

- Shutdown hooks **do not automatically compute and send business codes** per the `ExitCodeGenerator` contract unless the exit-code mechanism is invoked/handled on an appropriate path.
- A JVM killed by **SIGKILL**, power loss, a severe crash, or forced container termination is not guaranteed to run shutdown hooks completely.
- A `@PreDestroy` method running on context close does not mean all async tasks have finished.
- Infrastructure shutdown timeouts can cut cleanup short.

### 14.1. Resource cleanup example in the demo

In section 8, `DemoResource.close()` prints `RESOURCE_CLOSED`. That line appears **before `SpringApplication.exit` returns the code** on the success path. It proves Spring invoked the standard resource destroy callback when closing the context.

Nevertheless, if real cleanup throws an exception or holds a lock, do not conclude from a code of 0 alone that all resources were reclaimed. To be sure, test startup/shutdown under load and failure paths.

### 14.2. Shutdown ordering is a separate concern

When a batch job has running HTTP clients, DataSources, or executors:

1. Stop submitting new tasks.
2. Await in-flight tasks within a deadline.
3. Handle transactions/checkpoints/cancellations.
4. Close responses and borrowed JDBC connections.
5. Close shared clients, connection pools, and executors per bean lifecycle.
6. Return the appropriate exit code and terminate the process.

`SpringApplication.exit` helps close the context, but **does not automatically turn an uncooperative task into a checkpointed task**, create a durable queue, or make infrastructure wait forever.

## 15. Multiple ExitCodeGenerator beans

Some projects have generators from:

- A job processor.
- A validation module.
- An external dependency checker.
- External plugins or starters.
- Spring Batch (e.g., `JobExecutionExitCodeGenerator` when integrated appropriately).

When multiple generators exist, Spring Boot does not sum codes, does not pick the largest code, and does not prefer the "newest bean." It uses the **first non-zero code in order**.

### 15.1. Managing order as a business contract

Suppose you want priority:

1. Invalid configuration.
2. Invalid input data.
3. External system error.
4. Job completed normally.

Assign meaningful `Ordered`/`@Order` values rather than depending on bean names or insertion order. If the business requires a complex aggregation rule, an **aggregating ExitCodeGenerator** can be clearer than multiple competing generators.

### 15.2. Generators should be lightweight and side-effect-free

`getExitCode()` should return an outcome already established by the job, e.g., from an immutable `JobResult`. It should not:

- Re-run the job.
- Write data a second time.
- Call remote APIs with long timeouts.
- Open additional thread pools.
- Close the `ApplicationContext` inside the generator.
- Call `System.exit(...)` inside `getExitCode()`.
- Throw arbitrary exceptions to "beat" another generator.

This is the status-determination and shutdown phase, not the place to start new business work.

## 16. Testing without killing the test runner JVM

A dangerous testing mistake:

```java
@Test
void testExit() {
    System.exit(7); // Do not do this: terminates the entire test runner JVM.
}
```

This is an **anti-pattern**; to test codes, do not call `System.exit` inside the same test process.

Recommended testing approaches:

1. Unit test `ExitCodeGenerator.getExitCode()` with different job results.
2. Unit test `Ordered`/priority policies when multiple generators exist.
3. Integration test by creating **an isolated context**, calling `SpringApplication.exit(context)`, and asserting the returned code and closed context.
4. Process-level test running `java -jar` via `ProcessBuilder` or shell **in a child process**, verifying the real exit code.
5. When testing exception paths, verify whether the exception source/mapper is visible to Boot in that phase.

### 16.1. Conceptual integration test example

```java
@SpringBootTest(
    classes = ExitCodeLessonApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class ExitCodeLessonTest {

    @Autowired
    ConfigurableApplicationContext context;

    @Test
    void exitReturnsExpectedCode() {
        int code = SpringApplication.exit(context);
        assertEquals(0, code);
        assertFalse(context.isActive());
    }
}
```

**This is an illustrative snippet, not a test recommended to run as-is on a shared cached context.** It also requires imports for `@SpringBootTest`, `@Autowired`, JUnit assertions, and `SpringApplication`. Calling `exit(context)` closes a context that the TestContext cache might reuse, affecting subsequent tests.

**Better** is to create an isolated context in the test and close it under your own ownership. If you intentionally test lifecycle with `@SpringBootTest`, mark scope/`@DirtiesContext` appropriately and understand its cache impact.

### 16.2. Process-level test with Java ProcessBuilder

```java
ProcessBuilder builder = new ProcessBuilder(
        "java",
        "-jar",
        "build/libs/exit-code-lesson-0.0.1-SNAPSHOT.jar",
        "--demo.exit-code=7",
        "--demo.os-exit=true"
);
builder.inheritIO();

Process process = builder.start();
int status = process.waitFor();

System.out.println("OBSERVED_STATUS=" + status);
```

This is a **snippet inside a method declaring `throws IOException, InterruptedException`** with the JAR already built. It avoids calling `System.exit` in the test process; only the child process exits. When used on build servers, set a timeout and clean up stuck processes rather than calling unbounded `waitFor()` on untrusted work.

On environments fully supporting code 7, the parent process output includes:

```text
OBSERVED_STATUS=7
```

That is how to verify **real process status**, unlike merely asserting the `int` returned by `SpringApplication.exit` inside a running JVM.

## 17. What if startup fails before a context exists?

Do not assume:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(App.class, args);
int code = SpringApplication.exit(context);
```

always reaches the second line. If `run` throws due to invalid properties, circular dependencies, runner errors, bean init failures, or an unbindable web server port, `context` may never be assigned.

On the startup failure path, Spring Boot provides:

- `ApplicationFailedEvent`.
- `FailureAnalyzer` for user-friendly diagnostics.
- `ExitCodeGenerator` on exceptions.
- `ExitCodeExceptionMapper` for mapped errors when mappers are available.

Do not write `catch (Exception ex) { return 0; }` causing the scheduler to see a false success. Nor should you call `SpringApplication.exit(null)` just to force a code; use explicit failure handling and test in a real launcher.

### 17.1. ApplicationFailedEvent is not ExitCodeEvent

`ApplicationFailedEvent` indicates startup failure; `ExitCodeEvent` describes a determined exit code. Both can appear on a particular failure path, but they do not replace each other. Event listeners registered as Spring beans may **not yet be ready** if startup fails very early.

If you need to catch very early failure events, listeners must be registered through `SpringApplication` mechanisms before `run`. Do not assume `@EventListener` in a component will always catch errors occurring before that component is created.

## 18. Common anti-patterns

| Mistake | Consequence | Better alternative |
| --- | --- | --- |
| Calling only SpringApplication.exit and assuming OS receives code | The int stays in Java; process may exit 0 | System.exit(code) in main when reporting to OS |
| Calling System.exit in a controller | Stops the entire service for one request | Return an appropriate HTTP error |
| Calling context.close() and assuming exit code was computed | Does not evaluate ExitCodeGenerator | Use SpringApplication.exit when a code is needed |
| Calling SpringApplication.exit multiple times | Lifecycle already closed; no repeatable contract | One owner, one exit call |
| Using exit codes to represent HTTP 404/503 | Mixes protocols; large numbers may alter in shells | Small, separately documented codes |
| Assuming the largest non-zero always wins | Boot picks first non-zero by order | Ordered/@Order with a clear policy |
| Leaving multiple generators unordered | Result may depend on unintended ordering | Clear priority or aggregator |
| Generator calling network APIs during shutdown | May hang exit or open new resources | Record outcome before computing code |
| Generator calling System.exit internally | Cuts off Spring cleanup | Only main terminates the JVM |
| Returning 0 when a job failed | CI/Kubernetes treats it as success | ExitCodeGenerator from job result |
| Runner throws exception yet expecting code after run to execute | SpringApplication.run already threw | Test failure path separately |
| Using ExitCodeExceptionMapper for errors before context creates beans | Mapper may not exist yet | Appropriate early handling |
| Using System.exit in JUnit in the same JVM | Terminates the test runner | Test int directly or via subprocess |
| Closing cached SpringBootTest context | Other tests break due to shared cache | Isolated context / appropriate DirtiesContext |
| Using Gradle exit status to infer exact original Java code | Gradle may turn child error into task failure | Run JAR directly to verify |
| Using negative/outside 0–255 codes without shell testing | Platforms may represent them differently | Small stable code convention |
| Assuming shutdown hooks always run despite SIGKILL | Cleanup skipped on hard kill | Checkpointing/idempotence, grace period |
| Treating exitCode=0 as proof all resources were cleanly freed | Does not prove comprehensive cleanup | Test close/failure paths and monitoring |

## 19. Checklist for a Spring Boot CLI/batch application

1. Determine whether the program **exits after one run** or is a long-lived service.
2. Clearly define exit code 0 and failure codes.
3. Choose where to store the completed **business outcome**.
4. Use an `ExitCodeGenerator` bean if status belongs to job outcomes inside the context.
5. Pass a generator directly to `SpringApplication.exit` if `main` already knows the code.
6. With multiple generators, assign unambiguous `Ordered`/`@Order` values.
7. Keep `getExitCode()` short, safe, and free of heavy I/O.
8. Call `SpringApplication.exit(context)` exactly once after obtaining a valid context.
9. Call `System.exit(code)` only at the entrypoint when the process must report the OS code.
10. Do not call exit/`System.exit` in controllers or reusable services.
11. For startup failures, distinguish exception generators/mappers from intentional exits.
12. Do not assume mapper beans always exist if startup fails before refresh.
13. Ensure resources have destroy callbacks and background jobs have deadlines.
14. Measure/checkpoint incomplete work before process termination.
15. Run integration tests on returned codes **without `System.exit`** in the test JVM.
16. Run process-level tests with a real JAR to verify shell/container status.
17. Check Bash `$?` / PowerShell `$LASTEXITCODE` / CMD `%ERRORLEVEL%` properly.
18. Do not mix `SpringApplication.exit` codes with liveness/readiness/HTTP statuses.
19. For Kubernetes Jobs, verify `backoffLimit`, retries, and idempotence.
20. If code 0 occurs in production, require evidence that the job result was committed.
21. Log the exit code, job ID, and error category without exposing secrets.
22. Document the exit-code contract for CI/CD, operators, and runbooks.

## 20. Self-check questions

**1. Does SpringApplication.exit(context) call System.exit itself?**

No. It returns an `int` and closes the context if possible; the Java caller decides whether to invoke `System.exit(int)`.

**2. If an ExitCodeGenerator bean returns 7 but main does not call System.exit(7), will the OS definitely receive 7?**

No. Only a Java `int` variable exists; if `main` finishes normally, the process may return 0.

**3. Where can SpringApplication.exit obtain codes from?**

From `ExitCodeGenerator` beans in the context and generators passed into the varargs of the `exit` call.

**4. If multiple generators return 0, 14, 7, which code is chosen?**

`14` if the exact order is 0, then 14, then 7. Spring Boot uses **first non-zero**, rather than summing or picking the largest value.

**5. How do you control ordering?**

Implement `Ordered` or use `@Order` per the Spring contract.

**6. How do ConfigurableApplicationContext.close() and SpringApplication.exit() differ?**

`close()` closes the context; `SpringApplication.exit` also computes and returns a code from generators.

**7. Should System.exit be called inside a REST controller?**

No. It terminates the entire JVM and affects all other requests and tasks.

**8. When is an exception implementing ExitCodeGenerator used?**

In Spring Boot's appropriate error-handling paths, especially startup failures; it is not an active generator bean call after a successful job.

**9. Can ExitCodeExceptionMapper handle errors before Spring BeanFactory creates the mapper?**

There is no guarantee. Very early errors can occur before the mapper bean exists.

**10. Are ExitCodeEvent and ContextClosedEvent the same?**

No. One relates to a determined exit code; the other relates to closing the context.

**11. What is the best way to test System.exit(7) without harming the test runner?**

Run the application in a **subprocess**, wait for and read the process exit status; test the int from `SpringApplication.exit` directly in an isolated context.

**12. Does Gradle bootRun reporting a task failure tell you which exact integer SpringApplication.exit returned?**

You cannot reliably infer the exact integer without reading build-tool logs/contracts. Run `java -jar` directly and inspect the OS status.

## 21. Quick summary

```text
Spring Boot application completed its work
                 |
      business outcome recorded
                 |
      ExitCodeGenerator(s)
                 |
SpringApplication.exit(context)
                 |
    +--> compute first non-zero
    +--> close ApplicationContext
    +--> return int exitCode
                 |
       Java main receives code
                 |
        +--------+--------+
        |                 |
  Only print/check    System.exit(code)
  int in Java               |
        |              OS / parent process
  OS not guaranteed    receives process status
  to get this code
```

**Core rule:** `SpringApplication.exit` **computes and returns** the exit code while requesting the Spring context to close; `System.exit` is the call that forwards the code to JVM termination. With multiple `ExitCodeGenerator` beans, Spring Boot picks the **first non-zero code in order**. Use exit codes as a **documented contract** for CLI/batch/schedulers, do not confuse them with HTTP status or web service availability, and test in a real environment to confirm the process returns the expected code.

## Official documentation

- [Spring Boot 3.3.13 — SpringApplication.exit API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Boot 3.3.13 — SpringApplication: Application Exit](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3.13 — ExitCodeGenerator API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeGenerator.html)
- [Spring Boot 3.3.13 — ExitCodeEvent API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeEvent.html)
- [Spring Boot 3.3.13 — ExitCodeExceptionMapper API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeExceptionMapper.html)
- [Spring Framework — ApplicationContext lifecycle and destroy callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Java 17 — Runtime.exit and System.exit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html)
- [Gradle — Spring Boot 3.3: Running your application](https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html)
