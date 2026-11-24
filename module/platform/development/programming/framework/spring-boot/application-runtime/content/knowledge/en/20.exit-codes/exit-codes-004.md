# Implementing ExitCodeGenerator for Spring Boot Command-Line Applications

## 1. Why does a CLI application need an exit code?

A command-line program is commonly launched by a user, shell script, CI/CD, cron, Docker, or a Kubernetes Job. When the Java process terminates, the caller needs to know the **final outcome** to decide whether to run the next step, alert, retry, or mark a batch run failed.

Common conventions:

- **Exit code = 0**: the program completed with the success semantics declared by the tool.
- **Non-zero exit code**: the program did not achieve a successful outcome; specific numbers can classify errors or business conditions.
- The meanings of **2, 4, 7, 64...** must be agreed upon between the application and infrastructure; Spring Boot does not impose a fixed error-code table for all domains.

Spring Boot supports the **`org.springframework.boot.ExitCodeGenerator`** interface so beans can return an exit code when the application prepares to exit via **`SpringApplication.exit(...)`**. Boot 3.3 documentation uses the pattern:

```java
System.exit(
    SpringApplication.exit(
        SpringApplication.run(MyApplication.class, args)
    )
);
```

This is an **illustrative pattern**, requiring `MyApplication` and appropriate imports. Each of the three calls has its own role:

1. `SpringApplication.run(...)`: starts the context and invokes `ApplicationRunner`/`CommandLineRunner`; returns the context when startup succeeds.
2. `SpringApplication.exit(context)`: resolves the exit code from relevant `ExitCodeGenerator` instances, **closes the context**, and returns an `int`.
3. `System.exit(code)`: instructs the **JVM to exit** with that code so the OS/launcher receives the process status.

**Most importantly:** Simply implementing `ExitCodeGenerator` without invoking an appropriate `SpringApplication.exit(...)` path **does not mean Java automatically sends that code to the shell**. And `SpringApplication.exit(context)` returning an `int` **does not mean** `System.exit` was called. You must separate Spring-level outcome, JVM process exit, and how the environment receives the exit status.

This lesson uses **Spring Boot 3.3.13, Spring Framework 6.1.x, Java 17+**. The example is designed for a **one-shot non-web CLI**, not for using `System.exit` to stop a web service actively serving requests.

## 2. Three distinct types of "completion"

| Layer | Example | Meaning and limitations |
| --- | --- | --- |
| **Business work finished** | Job imported data or detected invalid input | The application determines status itself; can be 0 or non-zero without throwing an exception |
| **Spring context closed** | `SpringApplication.exit(context)` | Spring computes the exit code and closes the context, triggering lifecycle/destruction callbacks when feasible |
| **JVM/process exited** | `System.exit(code)` | The OS receives the Java process exit status; Java does not run statements after a normal `System.exit` |
| **Shell/CI observes result** | Bash `$?`, PowerShell `$LASTEXITCODE`, Kubernetes Job | Reads the actual received process code, which may be interpreted by a launcher or wrapper |
| **Resources released** | `@PreDestroy`/`DisposableBean.destroy()` | Merely lifecycle cleanup; does not prove all external side effects were rolled back |

Some misconceptions:

- `return;` from `main` ends the method; **it does not invoke `ExitCodeGenerator`**.
- `System.out.println("status=7")` only prints a message; **it does not change the process exit code**.
- `SpringApplication.exit(context)` closes the context and **returns an `int`**, but if the caller ignores the return value, the shell will not necessarily receive that number.
- `System.exit(7)` passes the status to the JVM, but if called prematurely inside a runner, you can break Spring's controlled cleanup sequence.

### 2.1. Why does a non-web CLI fit this pattern?

In a CLI application, work typically has a finite endpoint: reading files, validating, batch processing, detecting business errors, writing results, and exiting. Once all mandatory work completes, `main` can close the context and return the code.

For a web server or long-running scheduler, `SpringApplication.run(...)` is designed so the context stays active and the process receives shutdown signals from the environment. Calling `System.exit(SpringApplication.exit(...))` immediately after `run(...)` in a web app can **shut down the server almost instantly**. Use the CLI pattern only when exiting after startup is **intentional**.

## 3. What is the ExitCodeGenerator API really?

In Spring Boot 3.3, `ExitCodeGenerator` is a functional interface:

```java
package org.springframework.boot;

@FunctionalInterface
public interface ExitCodeGenerator {
    int getExitCode();
}
```

The snippet above only **illustrates the API signature**; real projects import Spring Boot's interface rather than redefining it.

`getExitCode()` is a query asking **which exit code should be used**. It takes no parameters and returns an integer. A simple implementation:

```java
final class JobExitStatus implements ExitCodeGenerator {
    private int code;

    void setCode(int code) {
        this.code = code;
    }

    @Override
    public int getExitCode() {
        return code;
    }
}
```

This is an **illustrative class snippet**, requiring importing `ExitCodeGenerator` and registering an instance as a Spring bean if you want `SpringApplication.exit(context)` to collect it. Since `code` initializes to `0` by default, the caller must update it to non-zero when detecting a corresponding outcome.

### 3.1. Is ExitCodeGenerator a bean or just a Java object?

A bean implementing `ExitCodeGenerator` is discovered by `SpringApplication.exit(context)` among the context's beans. For example:

```java
@Bean
ExitCodeGenerator exitCodeGenerator() {
    return () -> 42;
}
```

This is a **method snippet inside a `@Configuration`/`@SpringBootApplication` class**, not standalone. With this bean, if the context starts up successfully and the caller runs `SpringApplication.exit(context)`, the generator can provide code `42`.

Conversely, writing `new JobExitStatus()` somewhere **without registering it as a bean** does not make Spring collect that object automatically. You can pass generators directly when calling `SpringApplication.exit(context, generator1, ...)`, but that is a **different API path** where you must supply the instance explicitly.

### 3.2. Do you have to throw an exception to return a non-zero exit code?

**No.** A batch run can execute normally from a technical standpoint yet return an "unsuccessful" business outcome: for example, skipped records or invalid input. A runner can store the exit code in an `ExitCodeGenerator` bean and **return normally**; `SpringApplication.exit(context)` reads the state and returns the non-zero code.

Conversely, if `ApplicationRunner.run(...)` throws an exception, `SpringApplication.run(...)` does not return a context along the success path. That is the **startup failure path**, distinct from the "normal run + exit status" model of the main example. Exception mapping is explained separately in a later section.

## 4. Standard lifecycle when a CLI app has an ExitCodeGenerator

```text
OS/shell invokes java -jar batch.jar --mode=partial
    |
    +--> main(String[] args)
    +--> SpringApplication.run(...)
    |       +--> refresh ApplicationContext
    |       +--> ApplicationStartedEvent
    |       +--> run ApplicationRunner / CommandLineRunner
    |       |       +--> execute business logic
    |       |       +--> update status bean
    |       +--> ApplicationReadyEvent
    |       +--> return context
    |
    +--> SpringApplication.exit(context)
    |       +--> collect ExitCodeGenerator beans
    |       +--> pick first non-zero code by ordering
    |       +--> close context (ContextClosedEvent, Lifecycle stop, bean destroy)
    |       +--> return int exitCode
    |
    +--> System.exit(exitCode)
    |       +--> JVM/process shutdown
    |
    +--> shell/CI/Kubernetes reads exit status
```

**Note:** In Spring Boot 3.3, `ApplicationReadyEvent` can be published before `main` calls `SpringApplication.exit`, even when the business code will be 4 or 7. This **is not a contradiction**: Boot "ready" only states that the startup path completed per contract, not that the business job declared "exit 0." For a one-shot CLI, `ApplicationReadyEvent` should not be used as proof that the batch satisfied business requirements.

If a runner uses background threads, `ApplicationReadyEvent` does not automatically wait for all submitted futures either. For the exit code to be meaningful, mandatory work must be awaited/evaluated completely before `getExitCode()` is called, or a sufficiently verified status model must exist.

### 4.1. "Exit" in the method name does not mean System.exit

`SpringApplication.exit(context)` returns an `int`. It **closes the context** but **does not call `System.exit(int)` itself**. Thus, the explicit pattern is:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

int code = SpringApplication.exit(context);
System.exit(code);
```

This is an illustrative snippet requiring imports and an application class. We intentionally separate the last two lines so you can log or test **the chosen code** before the JVM actually exits.

## 5. Runnable example: CLI with four outcomes 0, 2, 4, 7

We create a Java 17 / Spring Boot 3.3.13 application that opens no HTTP port. An `ApplicationRunner` reads `--mode=...` and determines the outcome; a singleton bean **implementing `ExitCodeGenerator`** stores that outcome. Once the runner finishes, `main` calls `SpringApplication.exit(context)` to read the code and clean up, then calls `System.exit(code)` so the shell receives the status.

The modes:

| Argument | Exit code | Sample meaning |
| --- | ---: | --- |
| No `--mode` or `--mode=ok` | **0** | Batch succeeded |
| `--mode=partial` | **4** | Partial results needing follow-up per contract |
| `--mode=fail` | **7** | Controlled business task failure |
| `--mode=wrong` or `--mode` without a value | **2** | Invalid input argument |

These are **codes chosen by this lesson** for observation. Spring Boot **does not automatically define** 2 as invalid argument or 7 as business failure for every project.

### 5.1. build.gradle

Create a Gradle Groovy project with a compatible Gradle Wrapper, Java 17. File **`build.gradle`**:

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

File **`settings.gradle`**:

```groovy
rootProject.name = 'cli-exit-code-lab'
```

File **`src/main/resources/application.properties`**:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=ERROR
```

Do not add `spring-boot-starter-web`: this is a **one-shot CLI**. We intentionally invoke exit when processing finishes, needing no HTTP server or long-lived scheduler.

### 5.2. Complete Java file

Create the exact file **`src/main/java/com/example/exitcode/CliExitCodeApplication.java`**:

```java
package com.example.exitcode;

import java.util.List;

import jakarta.annotation.PreDestroy;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CliExitCodeApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(CliExitCodeApplication.class, args);

        // Compute the exit code and CLOSE the context, without exiting the JVM yet.
        int code = SpringApplication.exit(context);

        System.out.println("EXIT requested=" + code);

        // Pass the exit code to the operating system / shell.
        System.exit(code);
    }

    @Bean
    JobOutcome jobOutcome() {
        return new JobOutcome();
    }

    @Bean
    ApplicationRunner processBatch(JobOutcome outcome) {
        return args -> {
            List<String> values = args.getOptionValues("mode");

            // No option -> default to ok.
            // 0 or more than 1 value -> invalid.
            String mode = values == null
                    ? "ok"
                    : (values.size() == 1 ? values.get(0) : "invalid");

            int code = switch (mode) {
                case "ok" -> 0;
                case "partial" -> 4;
                case "fail" -> 7;
                default -> 2;
            };

            // Status is recorded BEFORE the runner returns.
            outcome.setCode(code);
            System.out.println("RUN mode=" + mode + " code=" + code);
        };
    }

    @Bean
    CloseProbe closeProbe() {
        return new CloseProbe();
    }

    // This is a Spring bean implementing ExitCodeGenerator.
    static final class JobOutcome implements ExitCodeGenerator {
        private int code = 0;

        void setCode(int code) {
            this.code = code;
        }

        @Override
        public int getExitCode() {
            return code;
        }
    }

    static final class CloseProbe {
        @PreDestroy
        public void onClose() {
            System.out.println("CLEANUP @PreDestroy");
        }
    }
}
```

**This program uses Java 17 switch expressions and requires no libraries outside the Spring Boot starter.** Every required class is in a single file, with package name matching the directory path.

### 5.3. Why does this code work properly?

1. `@SpringBootApplication` initializes the context. `processBatch(...)` registers an `ApplicationRunner` bean.
2. `JobOutcome` is created by `@Bean`, lives inside the Spring container, and **implements `ExitCodeGenerator`**, so `SpringApplication.exit(context)` collects it.
3. `ApplicationArguments.getOptionValues("mode")` retrieves the list of values for the CLI option. Absent option gives `null`; an option with one valid value selects the mode; empty, invalid, or multiple values map to code 2.
4. The runner computes the code from the **sample business outcome**, updates the bean, and returns normally. It does not call `System.exit` and throws no exceptions.
5. `SpringApplication.run(...)` only returns the context after normal startup and after runners complete. When `main` calls `SpringApplication.exit(context)`, the exit generator bean returns the stored code.
6. `SpringApplication.exit(context)` closes the context. `CloseProbe` is a singleton with `@PreDestroy`, so it gets to print `CLEANUP` **before `main` prints the exit code**.
7. Only `System.exit(code)` sends that code to the operating system. No Java statement after `System.exit` is expected to run in a normal execution.
8. Because there is only **one** `ExitCodeGenerator` bean and no extra generators passed to `exit`, there is no code-selection ordering conflict.

**Concurrency state note:** In this example, the runner and `main` run sequentially on the main thread, so a plain `code` field suffices. If multiple threads update the outcome, choose proper synchronization/atomics and a clear finalization rule. Never allow a still-pending async job to update the exit code **after** `SpringApplication.exit` has already read it.

### 5.4. Build the executable JAR

Windows PowerShell:

```powershell
.\gradlew.bat bootJar
```

macOS/Linux:

```bash
./gradlew bootJar
```

Standard output per project configuration is the file:

```text
build/libs/cli-exit-code-lab-0.0.1-SNAPSHOT.jar
```

The file is produced when the Gradle build succeeds and the wrapper/toolchain resolves dependencies. Use `java -version` to confirm at least Java 17.

### 5.5. Running in Bash and reading the exit code

```bash
java -jar build/libs/cli-exit-code-lab-0.0.1-SNAPSHOT.jar --mode=ok
echo $?
```

Lines **printed by the Java program**:

```text
RUN mode=ok code=0
CLEANUP @PreDestroy
EXIT requested=0
```

The following `echo $?` prints:

```text
0
```

With partial mode:

```bash
java -jar build/libs/cli-exit-code-lab-0.0.1-SNAPSHOT.jar --mode=partial
echo $?
```

Lines from Java:

```text
RUN mode=partial code=4
CLEANUP @PreDestroy
EXIT requested=4
```

`echo $?` prints `4`.

With business failure mode:

```bash
java -jar build/libs/cli-exit-code-lab-0.0.1-SNAPSHOT.jar --mode=fail
echo $?
```

Lines from Java:

```text
RUN mode=fail code=7
CLEANUP @PreDestroy
EXIT requested=7
```

`echo $?` prints `7`.

With an invalid option:

```bash
java -jar build/libs/cli-exit-code-lab-0.0.1-SNAPSHOT.jar --mode=wrong
echo $?
```

The program prints:

```text
RUN mode=wrong code=2
CLEANUP @PreDestroy
EXIT requested=2
```

`echo $?` prints `2`. When run without `--mode`, the program defaults to `mode=ok` and exits 0.

**Note:** `echo $?` in Bash must run **immediately after the Java command** if you want Java's exit status. An intervening command overwrites the status variable of the most recent command.

### 5.6. Running and reading the exit code in PowerShell

```powershell
java -jar build/libs/cli-exit-code-lab-0.0.1-SNAPSHOT.jar --mode=fail
$LASTEXITCODE
```

PowerShell displays `7` for the exit code of the `java` process just run. You can use:

```powershell
if ($LASTEXITCODE -ne 0) {
    Write-Host "Batch failed with code $LASTEXITCODE"
}
```

In Windows PowerShell, **`$LASTEXITCODE`** is the direct signal for the exit status of the most recent native executable. `$?` carries PowerShell pipeline command-result semantics and how it reflects native exit codes depends on version/configuration, so it does not replace `$LASTEXITCODE` by default in this check.

### 5.7. Why test with java -jar instead of only bootRun?

`gradlew bootRun` runs Java via **a Gradle task**. When the application calls `System.exit(7)`, Gradle can mark the task failed, and the Gradle process itself returns its own code. Consequently, **`gradlew`'s exit status is not always exactly `7`**. To verify the **actual code returned by the Java CLI to the OS**, build the JAR and run `java -jar` directly, as shown above.

The same holds for automated tests: verify the exit status of the **application process**, not merely text like "EXIT requested=7" in stdout.


## 6. Separating runner and generator duties for maintainable code

A good pattern has three areas of responsibility:

```text
Runner (business processing)
    |
    +--> determine clear outcome
    |
    v
JobOutcome (stores final result)
    |
    +--> implements ExitCodeGenerator.getExitCode()
    |
    v
SpringApplication.exit(context)
    |
    +--> read code and close resources
    |
    v
System.exit(code) -> shell/CI
```

**A runner should not call `System.exit(7)` itself** upon detecting a bad record. Doing so can skip subsequent runners, bypass unified exit-code resolution, or interrupt shutdown unexpectedly. It is especially dangerous if tasks submitted side effects and exited without awaiting acknowledgments/cleanup.

If a program has multiple steps, a `JobOutcome` should define a status aggregation policy:

- `0` only when **all mandatory steps satisfy success criteria**.
- A code for invalid input when no part of the job should run.
- A code for partial results when policy allows produced output but requires operator review.
- A code for unrecoverable failure.
- Ensure all mandatory Futures or transactions have finished before declaring the outcome.
- Never pick a success status simply because a worker **was submitted** to an executor.

A thread-safe state holder might use `AtomicInteger`, yet **atomicity of an `int` does not solve races in choosing the final status**. For instance, two workers writing 4 and then 0 can let 0 overwrite a failure. You need explicit priority/aggregation and finalization rules.

### 6.1. Can you use only a @Bean lambda?

Yes. If the code only needs a fixed exit code, the shortest bean method is:

```java
@Bean
ExitCodeGenerator exitCodeGenerator() {
    return () -> 42;
}
```

However, in real jobs the exit code usually depends on post-runner outcomes; therefore, a stateful `JobOutcome implements ExitCodeGenerator` bean, updated at the right time, expresses intent better than a constant 42.

### 6.2. Can you pass a generator directly to SpringApplication.exit?

Yes:

```java
int exitCode = SpringApplication.exit(
        context,
        () -> 8
);
System.exit(exitCode);
```

This is an **illustrative snippet**, requiring `context` to be an open `ApplicationContext` and appropriate imports. The API accepts multiple `ExitCodeGenerator...` arguments from the caller, **in addition to** generator beans found in the context.

If multiple generators exist, **do not assume the lambda just passed in always "wins"**: Spring picks the first non-zero code after ordering. Prefer having a single owner responsible for the final state unless aggregating multiple sources is genuinely necessary.

## 7. When multiple ExitCodeGenerators exist, which code is chosen?

According to Spring Boot 3.3.13:

> **The first non-zero exit code in the ordered list of generators is used.**

Spring supports ordering via `org.springframework.core.Ordered` or `org.springframework.core.annotation.Order`. **Lower order numbers have higher priority** under Spring's standard ordering convention.

Conceptual example:

```java
@Order(10)
final class ValidationExitCode implements ExitCodeGenerator {
    @Override
    public int getExitCode() {
        return 2;
    }
}

@Order(20)
final class ReportingExitCode implements ExitCodeGenerator {
    @Override
    public int getExitCode() {
        return 7;
    }
}
```

This is an **illustrative class snippet**, not a standalone file; it requires importing annotations/interfaces and registering **the objects as Spring beans** or passing the instances directly to `SpringApplication.exit`. When both are in the evaluated generator set with this order, the first non-zero code is **2**; Spring does not add them to 9, nor does it pick the numerically largest code by default.

If `ValidationExitCode.getExitCode()` returns `0` while Reporting returns `7`, the selected code is **7**. `0` is treated as that source **providing no non-zero error code** in the selection.

### 7.1. Ordered#getOrder() and @Order

A class can implement both `ExitCodeGenerator` and `Ordered`:

```java
final class ValidationExitCode
        implements ExitCodeGenerator, Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public int getExitCode() {
        return 2;
    }
}
```

This snippet also requires Spring interface imports. When order must be computed at runtime or injected via constructor, `Ordered#getOrder()` is more flexible; for fixed order, `@Order` on the class is easy to read.

Do not put both `@Order(10)` and `getOrder()=50` on the same instance expecting Spring to add or average them; pick one clear ordering source.

### 7.2. What if two generators have the same order?

Never treat tie-breaking order between two equal-order generators as a business contract. Bean registration order, classpath scanning, or Spring version changes can produce surprising results when both return non-zero codes.

For determinism:

1. Use distinct `@Order`/`Ordered` values and document precedence;
2. Or better, **one aggregating generator** evaluating business conditions to return a single code.

### 7.3. ExitCodeGenerator order is not runner @Order

A runner's `@Order(5)` and an ExitCodeGenerator's `@Order(5)` belong to **two separate lists**. Runner order affects **task execution sequence at startup**; generator order affects **exit code selection sequence during `SpringApplication.exit`**. Never use the same number to assume one runner controls a particular generator's code.

## 8. When a runner throws an exception: a different handling path

The main example intentionally **does not throw an exception**, because its purpose is to show `ExitCodeGenerator` beans being queried when `SpringApplication.exit(context)` is called after startup.

If an `ApplicationRunner` throws an exception outward:

```text
SpringApplication.run(...)
    |
    +--> context refresh succeeds
    +--> ApplicationStartedEvent
    +--> runner throws
    |
    +--> startup failure handling
    +--> ApplicationFailedEvent (when feasible)
    +--> cleanup/close context (when feasible)
    +--> exception escapes SpringApplication.run(...)
    |
    X   main receives no context from run(...)
    X   does not follow the normal SpringApplication.exit(context) block
```

Therefore, **do not** merely register an `ExitCodeGenerator` bean assuming it will always be invoked normally **after `run` has thrown**. When `run` fails, error-code resolution lies inside **startup failure handling**. To classify exceptions, Spring Boot also supports dedicated mechanisms.

### 8.1. Exceptions implementing ExitCodeGenerator themselves

Spring Boot allows the exception itself to implement `ExitCodeGenerator`. Example:

```java
final class InvalidInputException
        extends RuntimeException implements ExitCodeGenerator {

    InvalidInputException(String message) {
        super(message);
    }

    @Override
    public int getExitCode() {
        return 2;
    }
}
```

This is an **illustrative class snippet**, requiring an `ExitCodeGenerator` import. Per Spring Boot documentation, when such an exception is encountered during startup failure handling, Boot can read the code from `getExitCode()` and use it for the application's exit code information.

**Do not over-infer:** the code above **does not generate a `System.exit(2)` call in `main` itself**. How the launcher/Boot handles the final error code when an exception is thrown also depends on the startup failure path and how the process was launched. To confirm the exact number the shell receives, run **a real process** and read its exit status, rather than merely checking `getExitCode() == 2`.

### 8.2. ExitCodeExceptionMapper

Spring Boot also provides `org.springframework.boot.ExitCodeExceptionMapper` with the method:

```java
int getExitCode(Throwable exception);
```

This is a simplified signature of the interface API. Its goal is to map an exception to an error code, rather than requiring every domain exception to implement `ExitCodeGenerator` itself.

Example configuration snippet:

```java
@Bean
ExitCodeExceptionMapper exitCodeExceptionMapper() {
    return throwable -> {
        Throwable cause = throwable;
        while (cause.getCause() != null) {
            cause = cause.getCause();
        }
        if (cause instanceof IllegalArgumentException) {
            return 2;
        }
        return 0;
    };
}
```

This is an **illustrative** method, not a standalone file; it requires importing `ExitCodeExceptionMapper` and `@Bean`. Returning `0` means this mapper assigns no non-zero error code for that case. In production, mapping should target **specific business exceptions**, rather than turning every `RuntimeException` into the same code and losing classification.

### 8.3. What is ExitCodeEvent?

Spring Boot has the **`org.springframework.boot.ExitCodeEvent`** event, published when the framework determines an exit code from `ExitCodeGenerator` in the corresponding handling paths. The event provides `getExitCode()`. It **is not** `ContextClosedEvent` and does not replace `System.exit(...)`.

Listeners should only be used for quick observation/logging/metrics if needed; do not rely on this event to stop all workers or guarantee transactions roll back. For very early failures, listener beans may not exist yet; do not assume every listener receives every startup failure.

### 8.4. Do not catch an exception and return a fake 0

Anti-pattern snippet:

```java
try {
    loadRequiredData();
} catch (Exception ignored) {
    // Ignore the error and let the runner return successfully.
}
```

This is illustrative non-standalone code, and wrong when dealing with required data. If the runner swallows the error, `SpringApplication.run` can return normally; `JobOutcome` keeps its default 0; then `SpringApplication.exit` returns 0 and CI marks the job successful **contrary to reality**.

Two reasonable choices:

- Handle the business error cleanly, **set a non-zero outcome**, and return if the job has finished evaluating;
- Or **throw the exception** so Boot enters startup failure handling when continuing safely is impossible.

Never both swallow an exception and return code 0 just to keep a pipeline green.


## 9. Exit codes and graceful shutdown

An important design question is **when to close the context**.

With the sample CLI:

```text
Runner finished and finalized outcome
    |
    +--> SpringApplication.exit(context)
    |      +--> compute ExitCodeGenerator code
    |      +--> ContextClosedEvent
    |      +--> LifecycleProcessor stops Lifecycle/SmartLifecycle
    |      +--> @PreDestroy / DisposableBean / destroy-method
    |      +--> close context
    |
    +--> System.exit(code)
```

`SpringApplication.exit` closes the context before `main` calls `System.exit`. This creates an opportunity to stop schedulers, executors, connection pools, and singleton resources according to Spring's lifecycle.

**However:** cleanup callbacks can fail or time out; `SpringApplication.exit` does not automatically roll back committed database transactions, sent messages, or created files. If the job has important side effects, use transactions, idempotency, commits/acks, and reconciliation per contract.

### 9.1. Why shouldn't you call System.exit directly inside ApplicationRunner?

```java
@Bean
ApplicationRunner unsafeRunner() {
    return args -> {
        performWork();
        System.exit(7); // Anti-pattern: bypasses controlled exit/cleanup in main.
    };
}
```

This is an **anti-pattern snippet**, requiring `performWork()` to be defined. When `System.exit` is called inside a runner, Spring cannot run the rest of the startup sequence and `main` does not receive the context along the completion path to call `SpringApplication.exit`. Shutdown hooks may assist cleanup, yet still cannot replace a clear lifecycle strategy and centralized exit-code computation.

### 9.2. Avoid double close or calling exit when the context is not ready

- If `SpringApplication.run` throws an exception, **no context is returned** for you to use along the success path.
- If the caller already called `SpringApplication.exit(context)`, the context is already closed; there is no need to also call `context.close()` for the same normal lifecycle.
- If code uses `try-with-resources` to close the context before querying generators, it becomes awkward to call `SpringApplication.exit` on time because generator beans may already be destroyed.
- If an `ExitCodeGenerator` bean accesses an already-shut-down resource, it might fail to retrieve the right code. Compute/finalize the outcome **before closing**, keeping `getExitCode()` simple and safe.
- Do not spawn new threads inside `@PreDestroy` expecting `SpringApplication.exit` to wait for them automatically.

### 9.3. CLIs and web services have different goals

**CLI:** The goal is to execute finite work, close the context, and exit with a clear code.

**Web service:** The goal is to keep serving traffic after startup. Stopping happens primarily via `SIGTERM`/context shutdown; never place `System.exit(SpringApplication.exit(...))` immediately after `run(...)` like a CLI, as it shuts down the app right after opening.

**Scheduled service:** If jobs repeat long-term, do not let a single scheduler tick decide to exit the entire JVM. Design explicit contracts for when the service stops and how the orchestrator handles status.

## 10. How shells, CI/CD, containers, and Kubernetes read codes

### 10.1. Bash on Linux/macOS

`$?` holds the exit status of the most recent command in the shell:

```bash
java -jar batch.jar --mode=fail
code=$?
echo "Java exit status: $code"
if [ "$code" -ne 0 ]; then
    echo "Batch failed"
    exit "$code"
fi
```

This is an **illustrative script**; `batch.jar` must be a real file. If you want a shell wrapper to return the exact code, you must **explicitly propagate it**. If the wrapper always ends with `echo "done"` and returns 0, CI may treat the pipeline as successful even though Java returned 7.

Note on pipelines:

```bash
java -jar batch.jar | tee batch.log
```

In Bash, a pipeline's exit status is normally the status of its last command (`tee`), so Java returning 7 can still be masked. Use `set -o pipefail` when appropriate, or inspect `PIPESTATUS` right after the pipeline. Do not treat a `"Batch failed"` log line as sufficient; the pipeline must return the right status.

### 10.2. PowerShell

`$LASTEXITCODE` normally reports the exit code of the most recent native process:

```powershell
java -jar batch.jar --mode=fail
$code = $LASTEXITCODE
Write-Host "Java exit status: $code"
if ($code -ne 0) {
    exit $code
}
```

Note that `exit $code` terminates the PowerShell script/session depending on where it runs; suitable when the script is a CI entrypoint. If you are only testing in an interactive shell and do not want to close the shell, just print the code instead of calling `exit`.

### 10.3. Docker

When using **exec-form entrypoint**:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY build/libs/cli-exit-code-lab-0.0.1-SNAPSHOT.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

This is an **illustrative Dockerfile**, requiring an available image/tag and a built JAR file. When the container's Java process returns 0/2/4/7, the container runtime observes the exact code.

If using a shell wrapper, ensure the wrapper **propagates** Java's code. A wrapper without `exec` or without `exit "$code"` can make the container observe a different code. Avoid logging/shell cleanup afterward accidentally returning 0.

### 10.4. Kubernetes Job

A Kubernetes Job evaluates Pod/container results based on process status and Job policies. Under standard semantics, exit code 0 counts as successful completion, while non-zero can count as failure and trigger retries/backoff depending on `backoffLimit`, `restartPolicy`, and configuration.

**Do not assume "exit 4 is a warning so Kubernetes will mark the Job Succeeded"**. To most orchestrators, **every non-zero code is a failure** unless custom classification rules are configured. If `partial=4` is an acceptable outcome in a workflow, configure matching orchestration/next-step policies or consider a contract returning 0 while emitting warnings on another channel.

### 10.5. Code portability

On Unix-like OSes and shells, exit status is typically presented within the `0–255` range; large or negative numbers can be transformed/truncated across call layers. Windows represents process exit statuses differently. For portability across shells, containers, and CI, choose **small, non-negative codes**, such as 0, 2, 4, and 7 in this lab.

Do not cram all failure details into the exit code: you also need **logs/structured events, job ID, failed record count, and actionable root causes**. The exit code is a brief signal for the caller to act on, not the entire report.

## 11. Testing and verifying exit codes

### 11.1. Unit testing exit-code generation logic

Most business logic should be tested **independently of `System.exit`**. You can extract a status-mapping function:

```java
static int toExitCode(String mode) {
    return switch (mode) {
        case "ok" -> 0;
        case "partial" -> 4;
        case "fail" -> 7;
        default -> 2;
    };
}
```

This is an **illustrative method**, not part of the main program unless added to the class. Unit tests can call `toExitCode("fail")` and assert `7` without booting an entire Spring container.

### 11.2. Integration testing: querying the generator before System.exit

You can start a test context or CLI runner from a harness, fetch the `ExitCodeGenerator` bean and assert `getExitCode()`, or call `SpringApplication.exit(context)` and assert the `int` return value. **Never call `System.exit(...)` in the same JUnit JVM**, as it can terminate the test runner.

Conceptual example:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(CliExitCodeApplication.class, "--mode=partial");

int code = SpringApplication.exit(context);

assertEquals(4, code);
```

This is a **test snippet**, not a standalone runnable file; it requires imports and a testing framework, plus appropriate profile/logging management. When the main class calls `System.exit` inside `main`, tests invoke `SpringApplication.run` directly as shown rather than calling `main`.

### 11.3. End-to-end testing: running a separate process

To verify the **actual code received by the OS**, use `ProcessBuilder` or a shell to launch `java -jar` as **a child process**, wait for it to finish with a timeout, and assert its exit status.

Standalone Java 17 example verifying the built JAR (run separately in the project directory):

```java
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

public class ExitCodeProcessCheck {
    public static void main(String[] args) throws Exception {
        String javaBinary = Path.of(
                System.getProperty("java.home"), "bin", "java").toString();

        Process process = new ProcessBuilder(
                javaBinary,
                "-jar",
                "build/libs/cli-exit-code-lab-0.0.1-SNAPSHOT.jar",
                "--mode=fail")
                .inheritIO()
                .start();

        boolean finished = process.waitFor(20, TimeUnit.SECONDS);
        if (!finished) {
            process.destroyForcibly();
            throw new IllegalStateException("CLI process timeout");
        }

        int code = process.exitValue();
        if (code != 7) {
            throw new AssertionError("Expected 7, got " + code);
        }

        System.out.println("CHECK PASS: exit=7");
    }
}
```

The file above can be saved as **`ExitCodeProcessCheck.java`** at the project root, then run:

```bash
javac ExitCodeProcessCheck.java
java ExitCodeProcessCheck
```

Requires JDK 17+ and the demo JAR already built. `inheritIO()` lets you observe child stdout; `waitFor(20, TimeUnit.SECONDS)` prevents hanging indefinitely. On Windows, `Path.of(java.home,"bin","java")` is also resolved by normal JVM executable lookup; in environments with stricter requirements, you can specify `java.exe` or an explicit Java launcher path.

When the child process runs the demo properly, you will see the Java CLI lines:

```text
RUN mode=fail code=7
CLEANUP @PreDestroy
EXIT requested=7
CHECK PASS: exit=7
```

The last line is printed by the checker process. This approach isolates `System.exit(7)` from the test-running JVM, avoiding accidentally killing JUnit/IDE.

### 11.4. Do not assert only stdout

A program can print "EXIT requested=7" and then have a wrapper mask the error or get killed before returning the corresponding process status. In acceptance tests, observe the **real process `exitValue`**. Conversely, seeing shell status 7 without root-cause logs still leaves operations without data to act on; check both.

## 12. Common mistakes

| Symptom / claim | Why is it wrong? | How to handle it |
| --- | --- | --- |
| "Once `ExitCodeGenerator` is implemented, the shell gets the code automatically" | Generators are only queried by the framework on the matching path | Call `SpringApplication.exit(context)` and `System.exit(code)` for CLIs |
| "`SpringApplication.exit` is equivalent to `System.exit` itself" | The method returns `int` and closes the context | Caller passes the code to process exit |
| "Just printing `status=7` means the batch failed" | Logs do not change exit status | Assert the real exit code |
| "`System.exit(7)` in a runner is always better" | Skips intentional orchestration/cleanup | Finalize outcome, exit in `main` |
| "`ApplicationReadyEvent` proves exit code 0" | Ready fires after runners, before `main` computes status; business outcome is independent | Track job status |
| "If a runner throws, `main` still gets a context to call exit" | `SpringApplication.run` can throw before returning | Handle startup failure/exception mapping separately |
| "With multiple generators, Spring picks the largest code" | Boot picks the first non-zero code in order | Set `@Order`/`Ordered` or one aggregator |
| "A generator returning 0 always wins" | 0 means no non-zero error code in the selection | Understand first non-zero |
| "Two equal-order generators deterministically run by class name" | Tie order is not a reliable contract | Use distinct orders or consolidate |
| "Runner `@Order` also controls `ExitCodeGenerator`" | Two separate extension points | Separate runner order from generator ordering |
| "Async submission done means the job qualifies for exit 0" | Futures may still be running or failing | Await and verify business ACK |
| "`SpringApplication.exit` does not close beans" | The API closes the context if possible | Design `@PreDestroy`/`Lifecycle` properly |
| "Having `@PreDestroy` rolls back the DB" | Cleanup does not replace transactions/compensation | Design consistency |
| "`gradlew bootRun` returning 7 means Java returned 7" | Gradle wrapper may alter codes | Verify directly with `java -jar` |
| "PowerShell `$?` always equals Java's process code" | `$?` depends on command semantics/version | Read `$LASTEXITCODE` |
| "Bash pipeline through `tee` preserves Java's exit status" | Default pipeline can take the last command's status | Use `pipefail` or capture status |
| "Code 4 is a warning so Kubernetes treats the Job as Succeeded" | Many orchestrators treat all non-zero as failure | Choose a clear contract and policy |
| "You can call `System.exit` in regular unit tests" | It can terminate the test runner JVM | Test logic separately, process tests separately |
| "Negative or huge exit codes are preserved across every OS" | Exit statuses have platform limits/representations | Choose a small, non-negative range |

## 13. Production CLI design checklist

1. **Define the exit-code contract**: what does 0 mean, what do 2/4/7 represent, when to retry or alert?
2. **Separate business status from exceptions**: invalid input can be a classified outcome or an exception, but be consistent.
3. **Choose an owner**: one aggregating `ExitCodeGenerator` bean if there are multiple steps; use multiple generators only with clear reason.
4. **Initialize state safely**: a default 0 must not hide that mandatory work never ran. Consider a `PENDING` state mapped to 0 only after verified completion.
5. **Return from runners at the right time**: await required Futures/transactions/acks; do not equate queue submission with done.
6. **Do not call `System.exit` prematurely**: return the outcome and let `main` exit along a path with cleanup.
7. **Close the context**: call `SpringApplication.exit(context)` on the success path; know that it triggers destruction callbacks.
8. **Handle startup failures**: do not assume `run` always returns a context; use verified exception mapping and launcher behavior.
9. **Avoid throwing in `getExitCode` where possible**: generators should read an already-finalized result—simple, deterministic, and requiring no I/O from about-to-be-destroyed beans.
10. **Verify real shell status**: use `$?`/`$LASTEXITCODE` or `Process.exitValue()`, not just logs.
11. **Watch CI/container wrappers**: pass the exact exit status through the entrypoint without script overrides.
12. **Ensure zero data loss on restart**: batches need idempotency/checkpoints, especially when partial work committed before a non-zero status.
13. **Log safely**: job ID, mode, processed/failed counts, specific cause; never log tokens/passwords/customer payloads just for debugging.
14. **Test real failure paths**: invalid input, business partial, executor rejected, timeout, DB unavailable, `SIGTERM`, and OOM/crash where environment allows.
15. **Avoid the wrong model**: web services must not use the CLI exit-right-after-`run` pattern.

## 14. Self-check questions

**Q1.** An `ExitCodeGenerator` bean returns 7. If `main` only calls `SpringApplication.run(...)` and returns, is the shell guaranteed to receive exit code 7?

**A:** No. You need code computation via `SpringApplication.exit(context)` and forwarding via `System.exit(code)` or a suitable process termination mechanism.

**Q2.** What does `SpringApplication.exit(context)` do?

**A:** Collects generators, selects the exit code per contract, closes the context if possible, and returns an `int`. It does not call `System.exit` for the caller.

**Q3.** Three generators at orders 10, 20, and 30 return 0, 4, and 7 respectively. Which code is chosen?

**A:** **4**, because it is the first non-zero code in ordering.

**Q4.** Do you have to throw an exception just so a CLI returns code 4 after partial processing?

**A:** No. The runner can finalize outcome 4 and return; the generator bean returns 4 at exit.

**Q5.** A runner throws an exception before `SpringApplication.run` returns. Does `main` receive a context to call `SpringApplication.exit(context)` along the success path?

**A:** No. That is the startup failure path, requiring exception mapping and separate launcher testing.

**Q6.** If `System.exit(7)` is called right inside a runner, what issues can arise?

**A:** It bypasses centralized outcome finalization and context closure, and cuts off other runners; use orchestration logic in `main` instead.

**Q7.** Why did `@PreDestroy` run in the example before the `EXIT` line?

**A:** `SpringApplication.exit` closes the context before returning the code to `main`; singleton destruction callbacks run during normal close.

**Q8.** Running `java -jar ... --mode=fail` followed immediately by `echo $?` in Bash produces what result?

**A:** **7** for this demo, because `main` calls `System.exit(7)`.

**Q9.** A CLI job has an unfinished `@Async` future yet the generator returns 0. Is that okay?

**A:** Only if the work is optional and permitted by contract. If mandatory, status 0 is premature; await the result or use a different job model.

**Q10.** Is a CLI `ExitCodeGenerator` suitable for stopping a web server right after startup?

**A:** Not via the demo pattern. A long-lived web server should stay up until receiving a shutdown signal, rather than exiting right after `run`.

**Q11.** Why does code 4 require care in a Kubernetes Job?

**A:** Many orchestrators treat any non-zero as failure and may retry; code 4 only means "partial" if the platform/workflow is configured to understand it.

**Q12.** Should unit tests call `CliExitCodeApplication.main` directly?

**A:** Not if `main` calls `System.exit`, as it can terminate the testing JVM. Use logic unit tests or a child process.

**Q13.** A shell wrapper runs Java which exits 7, yet the wrapper's last line returns 0. What does CI see?

**A:** CI may see 0. The wrapper must propagate the code properly—for example, saving `$?` and calling `exit "$code"`.

**Q14.** If multiple generators share the same order and all return non-zero, should you rely on bean names to pick one?

**A:** No. Use distinct orders or one aggregating generator for a deterministic contract.

## 15. Takeaways and references

- **`ExitCodeGenerator`** is a single-method contract `int getExitCode()`. Implementing beans can supply a code when `SpringApplication.exit(context)` runs.
- **`SpringApplication.run`** starts up and invokes runners; **`SpringApplication.exit`** computes the code and closes the context; **`System.exit`** delivers the code to the OS.
- **Code `0`** represents success per CLI contract; **non-zero** represents a non-success outcome. Specific numeric codes must be documented by the project.
- **Multiple generators:** Spring Boot selects the **first non-zero code** by `Ordered`/`@Order`, not the numerically largest code.
- **Exception-based exit codes** are a separate path; exceptions can implement `ExitCodeGenerator` or be mapped via `ExitCodeExceptionMapper` during startup failure handling.
- **Do not call `System.exit` inside runners** when `main` can cleanly collect outcomes and perform cleanup.
- **Test the real process** with `java -jar` and process exit status; watch out for wrappers, pipelines, and build-tool launchers.
- **Do not equate submitted jobs with completed jobs**, context closed with JVM exited, or exit codes with durable rollbacks.

Official sources for Spring Boot 3.3.13:

1. [Spring Boot 3.3 — SpringApplication: Application Exit](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html), `System.exit(SpringApplication.exit(...))` example, exceptions, and multiple generators.
2. [Spring Boot 3.3.13 API — SpringApplication.exit](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html), collecting beans, picking first non-zero, and closing context.
3. [Spring Boot 3.3.13 API — ExitCodeGenerator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeGenerator.html), `getExitCode()` signature.
4. [Spring Boot 3.3.13 API — ExitCodeExceptionMapper](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeExceptionMapper.html), mapping Throwable to exit code.
5. [Spring Boot 3.3.13 API — ExitCodeEvent](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeEvent.html), event published when an exit code is determined.
6. [Spring Boot 3.3 — ApplicationRunner and CommandLineRunner](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html), execution steps before `run` returns.
7. [Spring Framework 6.1 — Bean Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html), singleton cleanup principles when the context closes.

**Conclusion:** `ExitCodeGenerator` lets a command-line application **express its outcome as a code**. To ensure the operating system receives the right code, finalize the outcome deterministically, use `SpringApplication.exit(context)` to read the code and close the Spring context, and let `System.exit(code)` forward that status to the external process. That is the difference between "a bean knows an error code" and "the CLI accurately reports success or failure to the calling system."
