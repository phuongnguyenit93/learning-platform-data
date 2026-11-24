# Exceptions Providing Exit Codes and ExitCodeExceptionMapper in Spring Boot

## Learning objectives

A Spring Boot CLI, batch job, or worker application may terminate due to a **business failure**, **configuration error**, or **infrastructure error**. The operating system and orchestrators usually see only the **process exit status**, whereas Java logs contain rich exception details. To distinguish among cases, Spring Boot provides mechanisms to obtain exit codes from **exceptions implementing `ExitCodeGenerator`** and from an **`ExitCodeExceptionMapper` bean**.

This lesson belongs to **Spring Boot Application Runtime → Exit Codes**, focusing specifically on these two mechanisms when an application encounters an exception, while explaining their relationship with `SpringApplication.exit(...)`, `System.exit(...)`, and `ExitCodeEvent`.

After this lesson, you will be able to:

1. Explain the role of exit code 0 and non-zero codes for shells, CI/CD, containers, and batch schedulers.
2. Create an exception implementing `org.springframework.boot.ExitCodeGenerator` and define `getExitCode()`.
3. Declare an `org.springframework.boot.ExitCodeExceptionMapper` bean to map **existing exception types** to exit codes.
4. Understand why runner exceptions are often **wrapped** by Boot in another exception, and how to walk `getCause()` instead of inspecting only the outermost exception.
5. Master the selection order on **Spring Boot 3.3.13's startup failure path**: mappers first; if they return 0, search for an exception implementing `ExitCodeGenerator` in the cause chain.
6. Distinguish `ExitCodeGenerator` as a **bean when calling `SpringApplication.exit`** from `ExitCodeGenerator` implemented **on an exception** during startup failure.
7. Write and run a Java 17+ / Spring Boot 3.3.13 project, observing `ExitCodeEvent` and the actual exit code from `java -jar`.
8. Understand limitations when the context is inactive, errors after the application is ready, exceptions on background threads, multiple mappers, signal termination, and exit-code ranges.
9. Design a durable error-code table so job schedulers distinguish retryable vs non-retryable failures.

**Version scope:** Spring Boot **3.3.13**, Spring Framework 6.1.x, Java 17+. Snippets other than the complete project are clearly marked as **illustrative snippets**.

## 1. What is an exit code, and why is logging the exception not enough?

When a Java process terminates, the JVM returns an integer to the environment that launched it. By very common convention:

- **`0`**: the process completed successfully per the application contract.
- **Non-zero**: an error, failure, or special condition occurred that the caller must handle.

However, Java and Spring Boot themselves **do not impose a universal business dictionary** saying 17 is always an input error or 23 is always a validation error. Each application must define its own conventions and document them with the orchestrator.

Example for a batch scheduler:

~~~text
exit 0  -> job succeeded, no retry needed
exit 17 -> invalid input, sender must fix data
exit 23 -> business rule failed, alert operator
exit 29 -> priority mapping policy from mapper
exit 1  -> general error or default runtime/launcher code
~~~

The values `17`, `23`, and `29` in this lesson are **conventions of the sample project**, not built-in codes defined by Spring Boot.

### Exceptions and exit statuses serve two different audiences

| Information | Primary consumer | Example |
| --- | --- | --- |
| Exception class | Java code, error handlers, frameworks | `IllegalArgumentException` |
| Exception message | Operators and logs | "Missing input file" |
| Cause chain | Multi-layer diagnostics | `IllegalStateException → DomainException` |
| Stack trace | Debugging code | Line where the error was thrown |
| Exit code | Shell, systemd, CI, scheduler, container runtime | `17` |
| `ExitCodeEvent` | Listeners inside the Spring application context | Exit code `17` determined |

**An exception does not automatically replace an exit code.** Not every exception carries a number; in many programs, if `main` ends with an unhandled unchecked exception, the OS typically sees a generic failure code with no business distinction.

## 2. Two primary interfaces

Spring Boot defines two distinct contracts in package `org.springframework.boot`.

### ExitCodeGenerator: an object supplying its own code

~~~java
@FunctionalInterface
public interface ExitCodeGenerator {
    int getExitCode();
}
~~~

This is an **illustrative signature**; do not redefine the interface in a real project. Either a bean or an exception can implement `ExitCodeGenerator`.

Exception case:

~~~java
public class DataRejectedException
        extends RuntimeException implements ExitCodeGenerator {

    public DataRejectedException(String message) {
        super(message);
    }

    @Override
    public int getExitCode() {
        return 23;
    }
}
~~~

This is an illustrative class requiring `import org.springframework.boot.ExitCodeGenerator`. When this exception type participates in a startup error path handled by Boot, the framework can call `getExitCode()` to determine the code.

**Advantage:** The business error type owns its own exit code; external modules do not have to maintain a huge mapping table just for this exception.

**Limitation:** You must be able to modify or subclass the exception class to implement the interface. JDK or third-party library exceptions generally cannot be modified.

### ExitCodeExceptionMapper: mapping exceptions to codes

~~~java
@FunctionalInterface
public interface ExitCodeExceptionMapper {
    int getExitCode(Throwable exception);
}
~~~

This is also an **illustrative signature**, not a file to create yourself. The mapper accepts a `Throwable` and returns an `int`:

- Return a **non-zero** code when the mapper applies to this error.
- Return **`0`** when the mapper has no mapping for the error under inspection, allowing other mechanisms to continue deciding.

Example bean:

~~~java
@Bean
ExitCodeExceptionMapper exitCodeExceptionMapper() {
    return exception -> {
        Throwable current = exception;

        while (current != null) {
            if (current instanceof IllegalArgumentException) {
                return 17;
            }
            current = current.getCause();
        }

        return 0;
    };
}
~~~

This is a **configuration snippet**, requiring `@Bean` and interface imports, placed inside a `@Configuration` or `@SpringBootApplication` class. It illustrates walking the cause chain; a complete project should map only **specific business exception types**, avoiding mapping every `IllegalArgumentException` to a data error if it could be a programming bug.

### Comparing the two strategies

| Criterion | Exception implements `ExitCodeGenerator` | `ExitCodeExceptionMapper` bean |
| --- | --- | --- |
| Logic location | Directly on the exception class | Inside a Spring bean |
| API | `int getExitCode()` | `int getExitCode(Throwable)` |
| Must modify exception class? | Yes, or create a subtype | No |
| Suitable for third-party exceptions? | Inconvenient | Suitable |
| Can inspect outermost cause and inner causes? | Boot searches the cause chain on fallback | Mapper receives `Throwable` and decides whether to walk causes |
| Depends on active context when startup fails? | Exception fallback does not require a mapper bean | Mapper beans are only used under appropriate active-context conditions |
| Used when `SpringApplication.exit(context)` succeeds? | Yes if it is an **`ExitCodeGenerator` bean** or passed as an argument | Not the default exception-handling path of `exit(context)` |
| Primary role | Error knows its own code | Application-level policy mapping errors to codes |

**Remember:** `ExitCodeGenerator` is an interface reused in two contexts; it does not mean throwing that exception on any arbitrary thread will make the JVM immediately exit with that code.

## 3. At which stage of startup are exit codes processed?

In Spring Boot, a normal startup goes through:

~~~text
SpringApplication.run(...)
    |
    +-- Environment / bootstrap
    +-- ApplicationContext created and refreshed
    +-- ApplicationStartedEvent
    +-- ApplicationRunner and CommandLineRunner
    +-- ApplicationReadyEvent
    +-- SpringApplication.run returns context
~~~

If a step in `run(...)` fails, Boot takes the **startup failure** branch:

~~~text
Failure Throwable in SpringApplication.run
    |
    +-- handleRunFailure(...)
         |
         +-- Determine exit code from exception
         |      |
         |      +-- context active?
         |      |      |
         |      |      +-- Yes: invoke ExitCodeExceptionMapper beans
         |      |                  |
         |      |                  +-- Non-zero result -> use that code
         |      |                  +-- Result 0 -> try next step
         |      |
         |      +-- Search for ExitCodeGenerator on Throwable
         |             or its causes
         |             |
         |             +-- Found -> call getExitCode()
         |             +-- Not found -> no custom non-zero code
         |
         +-- If non-zero: may publish ExitCodeEvent
         +-- Record code for Boot exception handler if available
         +-- Handle ApplicationFailedEvent / error reporting
         +-- Close context when possible
         +-- Rethrow error out of SpringApplication.run(...)
~~~

This diagram shows the processing order **in the Spring Boot 3.3.13 startup failure branch**, not every internal line of code. Based on the 3.3.13 implementation, Boot tries mappers first, then falls back to exceptions carrying `ExitCodeGenerator` if mappers return 0. <escape>"may"</escape> on `ExitCodeEvent`/handler is critical because failures can occur before an active context exists or in environments lacking the expected JVM exception handler.

### Only an active context can resolve mapper beans

`ExitCodeExceptionMapper` is registered as a Spring bean. When a failure occurs:

- **After refresh, inside runners:** The context is normally active, so mapper beans can be retrieved and used.
- **Before the context finishes building or when inactive:** Do not assume `BeanFactory` can supply mappers. Spring Boot 3.3 checks whether the context is active before looking up mappers.
- **Exceptions implementing `ExitCodeGenerator`:** The fallback mechanism can inspect the exception or cause chain directly, even when no mapper bean is usable.

This is why the runnable example in section 8 throws errors from an `ApplicationRunner`: the context is already refreshed, proving mapper beans work in their intended role.

## 4. Cause chains: why must mappers usually walk getCause()?

In enterprise code, a business exception can pass through multiple layers:

~~~text
IllegalStateException:
  "Failed to execute ApplicationRunner"
     |
     +-- cause: InvalidInputException:
          "input.csv has invalid format"
~~~

When an `ApplicationRunner` or `CommandLineRunner` throws, Spring Boot can wrap the error in an exception noting the failed callback. Therefore, the mapper does not necessarily receive `InvalidInputException` directly at the outermost level.

Anti-pattern:

~~~java
return throwable -> throwable instanceof InvalidInputException
        ? 17
        : 0;
~~~

If `throwable` is an `IllegalStateException` containing `InvalidInputException` in `getCause()`, the expression above returns 0 even though the domain expects code 17.

### Solution: walk the entire cause chain

~~~java
static boolean hasCause(
        Throwable original, Class<? extends Throwable> type) {

    for (Throwable cursor = original;
            cursor != null;
            cursor = cursor.getCause()) {

        if (type.isInstance(cursor)) {
            return true;
        }
    }

    return false;
}
~~~

This snippet is a non-standalone illustrative helper. It checks both the outermost `Throwable` and nested causes underneath. Under normal conditions, the cause chain terminates at `null`.

To guard against custom exceptions with **self-referential causes or cycles** violating normal Java initialization rules, you can track visited nodes in an identity set to avoid infinite loops. There is no need to turn teaching code into a complex exception framework if inputs are under the application's control.

### getCause differs from getSuppressed

A `Throwable` can have:

- `getCause()`: the underlying cause exception.
- `getSuppressed()`: secondary exceptions, such as errors from `close()` when a `try-with-resources` body already failed.

Spring Boot 3.3's exception-code fallback walks the **cause chain**, not all suppressed exceptions automatically. Your custom mappers must also decide whether to inspect suppressed exceptions. Usually, **you should not use a secondary cleanup error** as the primary business code when the root cause is already clear.

### Do not classify by message when clear types exist

Code such as:

~~~java
if (exception.getMessage().contains("timeout")) {
    return 17;
}
~~~

is fragile because the message can be `null`, change across libraries or locales, or contain user data. Prefer **exception types**, domain error codes, structured metadata, or a dedicated contract.

## 5. When both a mapper and an exception provide codes, which wins?

This is easy to answer incorrectly if you only read the two interfaces.

In **Spring Boot 3.3.13's startup failure path**, the implementation chooses:

1. Fetch `ExitCodeExceptionMapper` beans when the context is active and query them for the throwable.
2. If a mapper returns a **non-zero code**, use that code.
3. If the mapper result is 0, search for an exception implementing `ExitCodeGenerator` in the `getCause()` chain and call `getExitCode()`.
4. If no non-zero code is found, the framework has no custom non-zero code from these two mechanisms; the JVM/launcher typically reports a generic failure status on an uncaught exception.

Example:

~~~text
Exception implementing ExitCodeGenerator: 23
ExitCodeExceptionMapper for same error: 29
----------------------------------------
Code determined by Spring Boot when context is active: 29
~~~

**Do not confuse this precedence with `SpringApplication.exit(context)`**, where Boot collects generator beans/arguments rather than running the startup-failure throwable mapping branch.

### Multiple mappers

An application can have more than one `ExitCodeExceptionMapper` bean. When that happens:

- Avoid having two mappers claim to match the same error type while returning different codes.
- If precedence matters, define and verify ordering (`Ordered`/`@Order` where applicable).
- Put specialized mappings before general ones, or consolidate rules into one centralized mapper.
- Have each mapper return **0 for errors outside its scope**.
- Do not write a catch-all mapper "matching every Throwable and returning 1" early and expect later specialized mappers to classify errors.

Spring Boot's rule with multiple exit-code generators is to **pick the first non-zero code in the determined order**, not min/max or summing codes.

### What does returning 0 mean?

For `ExitCodeExceptionMapper`, returning 0 means **no non-zero mapping from that mapper**. It does not "swallow" an exception and does not make `SpringApplication.run` succeed. If all mappers return 0 while a cause implements `ExitCodeGenerator`, the fallback can still return a non-zero code.

If a mapper has the logic:

~~~java
return exception -> 0;
~~~

then that mapper supplies no distinguishing error code; it does not ensure the OS receives 0 when startup throws an exception.

## 6. ExitCodeGenerator on a bean vs on an exception

Spring Boot lets you declare a bean:

~~~java
@Bean
ExitCodeGenerator exitCodeGenerator() {
    return () -> 42;
}
~~~

And invoke:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

int code = SpringApplication.exit(context);
System.exit(code);
~~~

These are **two illustrative snippets**, requiring imports for `ExitCodeGenerator`, `Bean`, `SpringApplication`, `ConfigurableApplicationContext`, and class `MyApplication`. Do not paste them verbatim into the runnable project in section 8.

This path applies when the **context is already running** and the application wants to exit intentionally—for example, a batch task completed but its outcome must report a non-zero status.

### Three distinct roles

| API | Input | When to use |
| --- | --- | --- |
| `Exception implements ExitCodeGenerator` | The exception itself on startup failure | The exception knows its own code |
| `@Bean ExitCodeExceptionMapper` | The `Throwable` causing startup failure | Mapping exception types to codes |
| `SpringApplication.exit(context, generators...)` | `ApplicationContext` + optional `ExitCodeGenerator` | Computing code and closing context after app runs |

`SpringApplication.exit(...)` **returns an `int`**; it closes the context if possible, but **does not itself force the OS to receive that code**. To return the exit status for the process, `main` must pass it to `System.exit(code)` or an equivalent process-control mechanism.

Conversely, when an unhandled exception escapes `main`, the uncaught-exception / Boot exception handler path can influence the exit code without an explicit `System.exit(...)` line written by you. Run from a separate JVM and verify the actual code rather than guessing from API calls.

### Why not call SpringApplication.exit(null)?

`SpringApplication.exit(context)` requires a valid `ApplicationContext`; it does not accept `null` to handle bootstrap errors. If `SpringApplication.run(...)` throws before returning a context, you **do not have a successful context to pass to `exit`**. For startup failures, the framework has its own `handleRunFailure(...)` path.

## 7. Exit code conventions for a CLI/batch application

Example for a data-ingestion system:

| Code | Proposed meaning | Auto-retry? |
| --- | --- | --- |
| `0` | Processed successfully | No |
| `17` | Invalid input file or request schema | Usually no; fix input |
| `23` | A mandatory business rule was violated | Depends on business logic |
| `29` | Policy mapping overrode exception code | Per override policy |
| `1` | Unclassified error or unhandled exception | May need investigation before retry |

This is an **illustrative convention table** for the project below. In production, many failures such as timeouts, rate limits, and unavailable dependencies merit retries, though you should not default every non-zero code to infinite retries.

### Choosing portable codes

On many Unix-like systems, shells expose only the **low 8 bits** of a normal exit status: large codes can be altered when observed via `$?`. To minimize surprises across platforms/runners, the examples use small positive codes like 17, 23, and 29.

**Do not rely on negative codes or codes above 255** if multi-environment compatibility is needed. On Windows, exit-code handling differs; document and test on your organization's target platforms.

### Avoid colliding with reserved codes

Some shells use `126` for "command cannot execute," `127` for "command not found," and `128 + signal` for processes terminated by a signal. For jobs launched through shells/scripts, use application-defined codes in a small range and avoid those special values where possible.

## 8. Runnable project: two strategies and precedence order

**Java 17+ / Spring Boot 3.3.13 / Gradle** project needing no database or web server. Errors are intentionally thrown from an `ApplicationRunner` after context refresh, ensuring `ExitCodeExceptionMapper` is already a bean in an active context.

The modes:

- `success`: runner finishes, `main` closes the context, process exits normally.
- `exception`: throws `RuleViolationException implements ExitCodeGenerator`, returning code **23**.
- `mapped`: throws plain `InvalidInputException`; mapper returns code **17**.
- `both`: throws `OverrideRuleException implements ExitCodeGenerator` with code 23, yet the mapper maps it to **29**; the mapper code takes precedence when the context is active.
- `unknown`: throws an exception unrecognized by the mapper and not implementing `ExitCodeGenerator`; startup fails without a custom exit code from either mechanism in the example.

### 8.1. Project structure

~~~text
exit-exception-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/exitcode/
    └── ExitCodeDemoApplication.java
~~~

**File `settings.gradle`:**

~~~groovy
rootProject.name = 'exit-exception-demo'
~~~

**File `build.gradle`:**

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
    mainClass = 'com.example.exitcode.ExitCodeDemoApplication'
}
~~~

The demo requires a Gradle version compatible with Spring Boot 3.3 and JDK 17 or newer. If dependencies are not cached, access to Maven Central is required. The project does not generate a Gradle Wrapper; you can use an installed `gradle` or generate a wrapper yourself.

### 8.2. Complete Java code

**File `src/main/java/com/example/exitcode/ExitCodeDemoApplication.java`:**

~~~java
package com.example.exitcode;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.ExitCodeEvent;
import org.springframework.boot.ExitCodeExceptionMapper;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class ExitCodeDemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ExitCodeDemoApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN: application ready");
        }

        System.out.println("MAIN: normal exit");
    }

    @Bean
    ApplicationRunner demoRunner(
            @Value("${demo.mode:success}") String mode) {

        return args -> {
            switch (mode) {
                case "success" -> {
                    System.out.println("RUNNER: success");
                }
                case "exception" -> {
                    System.out.println("RUNNER: exception");
                    throw new RuleViolationException(
                            "Business rule did not pass");
                }
                case "mapped" -> {
                    System.out.println("RUNNER: mapped");
                    throw new InvalidInputException(
                            "Input format is invalid");
                }
                case "both" -> {
                    System.out.println("RUNNER: both");
                    throw new OverrideRuleException(
                            "Mapping should win");
                }
                default -> {
                    System.out.println("RUNNER: unknown");
                    throw new IllegalStateException(
                            "Unknown demo.mode: " + mode);
                }
            }
        };
    }

    @Bean
    ExitCodeExceptionMapper exceptionMapper() {
        return exception -> {
            // Runner errors may have an outer IllegalStateException.
            for (Throwable current = exception;
                    current != null;
                    current = current.getCause()) {

                if (current instanceof InvalidInputException) {
                    return 17;
                }

                if (current instanceof OverrideRuleException) {
                    return 29;
                }
            }

            // No mapping: let Boot try ExitCodeGenerator in causes.
            return 0;
        };
    }

    @EventListener
    public void onExitCode(ExitCodeEvent event) {
        System.out.println(
                "EVENT: exit code=" + event.getExitCode());
    }

    public static final class RuleViolationException
            extends RuntimeException implements ExitCodeGenerator {

        public RuleViolationException(String message) {
            super(message);
        }

        @Override
        public int getExitCode() {
            return 23;
        }
    }

    public static final class InvalidInputException
            extends RuntimeException {

        public InvalidInputException(String message) {
            super(message);
        }
    }

    public static final class OverrideRuleException
            extends RuntimeException implements ExitCodeGenerator {

        public OverrideRuleException(String message) {
            super(message);
        }

        @Override
        public int getExitCode() {
            return 23;
        }
    }
}
~~~

### 8.3. Logic explained per mode

**`success`**

- `ApplicationRunner` runs and prints `RUNNER: success`.
- No exception is thrown; `SpringApplication` reaches ready and returns the context.
- `main` prints `MAIN: application ready`, closes the context via `try-with-resources`, and prints `MAIN: normal exit`.
- `SpringApplication.exit(context)` is not called because the example defines no `ExitCodeGenerator` bean for the success path.
- The process normally terminates with code 0 when no non-daemon threads keep the JVM alive.

**`exception`**

- The runner throws `RuleViolationException` with `getExitCode() == 23`.
- The mapper does not recognize this type and returns 0.
- Boot inspects the exception/cause chain, finds `ExitCodeGenerator`, and retrieves 23.
- Since the context is active, an `ExitCodeEvent` with 23 is published.
- `SpringApplication.run` does not return normally; neither `MAIN: application ready` nor `MAIN: normal exit` is printed.

**`mapped`**

- The runner throws `InvalidInputException`. The exception does not implement `ExitCodeGenerator`.
- The mapper walks the cause chain and returns 17.
- Boot uses 17 because the context is active. The exception did not need modification to add an interface.
- This case also confirms the mapper does not compare only the outermost throwable.

**`both`**

- The runner throws `OverrideRuleException` with `getExitCode() == 23`.
- The mapper also recognizes that exception and returns 29.
- With an active context, Boot takes the non-zero mapper result first, using **29** instead of 23.
- This is the precedence inside the **SpringApplication startup-failure path**, not the selection order of `ExitCodeGenerator` beans when calling `SpringApplication.exit`.

**`unknown`**

- The runner throws `IllegalStateException`, which the mapper does not recognize.
- The mapper returns 0, and the exception has no `ExitCodeGenerator` in its cause chain.
- No custom non-zero `ExitCodeEvent` is determined from either mechanism.
- The JVM normally reports failure due to the unhandled exception, though the exact process code may depend on the launcher/handler. Never promise Spring Boot "actively assigns code 1" merely because the mapper returned 0.

### 8.4. Build the JAR

From the `exit-exception-demo` directory:

~~~bash
gradle bootJar
~~~

The generated JAR with default naming configuration is typically:

~~~text
build/libs/exit-exception-demo-0.0.1-SNAPSHOT.jar
~~~

If using Gradle Wrapper, replace `gradle` with `./gradlew` on Linux/macOS or `.\gradlew.bat` on Windows. If you change `rootProject.name` or `version`, the JAR name can change; check your project's `bootJar` output.

### 8.5. Run success mode and check status

In Bash/Zsh:

~~~bash
java -jar build/libs/exit-exception-demo-0.0.1-SNAPSHOT.jar \
  --demo.mode=success
echo $?
~~~

In PowerShell:

~~~powershell
java -jar .\build\libs\exit-exception-demo-0.0.1-SNAPSHOT.jar --demo.mode=success
$LASTEXITCODE
~~~

**Lines printed by the Java code itself:**

~~~text
RUNNER: success
MAIN: application ready
MAIN: normal exit
~~~

Normal process exit code: **`0`**.

### 8.6. Run exception self-providing code 23

In Bash/Zsh:

~~~bash
java -jar build/libs/exit-exception-demo-0.0.1-SNAPSHOT.jar \
  --demo.mode=exception
echo $?
~~~

**Lines printed by the demo code** (excluding Boot stack traces/logs):

~~~text
RUNNER: exception
EVENT: exit code=23
~~~

JVM exit code under the standard Spring Boot launcher: **`23`**. Aside from demo lines, Boot may print startup errors and stack traces; the process terminates intentionally as a failure.

### 8.7. Run mapper code 17

~~~bash
java -jar build/libs/exit-exception-demo-0.0.1-SNAPSHOT.jar \
  --demo.mode=mapped
echo $?
~~~

Lines printed by the demo code:

~~~text
RUNNER: mapped
EVENT: exit code=17
~~~

Expected JVM exit code: **`17`**.

### 8.8. When both mechanisms provide codes

~~~bash
java -jar build/libs/exit-exception-demo-0.0.1-SNAPSHOT.jar \
  --demo.mode=both
echo $?
~~~

Lines printed by the demo code:

~~~text
RUNNER: both
EVENT: exit code=29
~~~

Expected JVM exit code: **`29`**. If you see 23, check whether the mapper bean exists in an active context and whether the cause-chain check matches.

### 8.9. Check unknown mode

~~~bash
java -jar build/libs/exit-exception-demo-0.0.1-SNAPSHOT.jar \
  --demo.mode=unknown
echo $?
~~~

Line guaranteed to be printed by the demo code **before the error**:

~~~text
RUNNER: unknown
~~~

Boot/Java reports failure. No non-zero mapping came from either configured mechanism; check the exit status in the shell rather than asserting a number not defined by the application.

### 8.10. Why not use gradle bootRun's exit code for measurement?

`gradle bootRun` is a **Gradle task** that launches the application JVM. If the child process exits non-zero, Gradle can report a build failure and Gradle itself returns the **build tool's** error code, not necessarily preserving the application's business code.

To test the exit code of the **application JVM itself**:

1. Build with `gradle bootJar`.
2. Invoke `java -jar ...` directly.
3. Read `$?` or `$LASTEXITCODE` **immediately after the java command**.
4. Do not run another command before reading the exit status, as the shell overwrites the previous command's status.

Do not use seeing `EVENT: exit code=17` in logs as sole proof that the OS received 17; verify the actual process status when the requirement is exit-code orchestration.

## 9. Actual Spring Boot 3.3.13 flow when a runner throws

According to `SpringApplication` in Spring Boot 3.3.13:

1. `callRunners(...)` invokes `ApplicationRunner`/`CommandLineRunner`, potentially wrapping exceptions in an `IllegalStateException` noting the failed callback.
2. `SpringApplication.run`'s `catch(Throwable ex)` branch calls run-failure handling.
3. `getExitCodeFromException(...)` tries `getExitCodeFromMappedException(context, ex)`.
4. In the mapper branch, if the context does not exist or `!context.isActive()`, it skips fetching mappers and returns 0.
5. If the context is active, it retrieves `ExitCodeExceptionMapper` beans, queries them with the supplied exception, and selects a non-zero code via the generators mechanism.
6. If no mapped non-zero code is produced, `getExitCodeFromExitCodeGeneratorException(ex)` walks `getCause()` until it finds an object implementing `ExitCodeGenerator`.
7. If the exit code is non-zero, Boot publishes `ExitCodeEvent` when a context is available and registers the code with the main thread's `SpringBootExceptionHandler` under appropriate handler conditions.
8. Boot performs failure reporting, closes the context when possible, and still rethrows the exception out of `run`.

### Why is the cause with a code still found even when the runner wraps it?

If `RuleViolationException` is wrapped:

~~~text
IllegalStateException("Failed to execute ApplicationRunner")
   |
   +-- caused by RuleViolationException
           |
           +-- getExitCode() -> 23
~~~

the fallback walks `getCause()` and finds `RuleViolationException`. Thus, an exception implementing `ExitCodeGenerator` can still work even when the runner wraps it in an outer exception.

### Where is ExitCodeEvent published?

`ExitCodeEvent` is an `ApplicationEvent` with a `getExitCode()` method. On a non-zero startup-failure path, Boot can publish the event in the context **before** failure reporting and corresponding context closure. The `@EventListener` in the runnable project only observes; it does not participate in selecting the code.

**Do not turn an event listener into a place that calls `System.exit(...)`**. Exiting the JVM inside a listener can cut off cleanup, tests, and logging. Use generators/mappers for code policy, and listeners for observation.

## 10. When mapper beans cannot participate

Some errors happen too early:

- Environment/property parsing fails before context creation.
- `ApplicationContextInitializer` fails while the context is not yet active.
- Classpath/configuration errors occur before `BeanFactory` can supply mappers.
- Bean factory refresh fails and the context is not in an active state.
- An exception occurs in code before `SpringApplication.run` is called.

In those situations, **do not guarantee `ExitCodeExceptionMapper` beans will be invoked**. The mapper path in Spring Boot 3.3 checks for an active context.

If the exception implements `ExitCodeGenerator` itself and passes through `SpringApplication.run`'s error handling, the fallback can supply a code even when mappers are unusable.

**Not equivalent:** a mapper not being called **does not mean** every startup exception turns into code 0. The JVM/launcher still fails on the uncaught exception, and Boot may have resolved a code via an exception generator.

### Solutions for very early failures

If you need deterministic codes for errors before the context is active, consider:

- Creating domain exceptions carrying `ExitCodeGenerator` yourself when you control the code.
- Moving certain bean-dependent checks into an `ApplicationRunner` if the logic genuinely fits checking after refresh and before ready.
- For errors outside `SpringApplication`, handling them explicitly in `main` while preserving exception/cause details for logs and cleanup.
- Never blindly catching `Throwable` and calling `System.exit(0)`, causing failures to report success.
- Never initializing heavy resources just to run a mapper while bootstrap itself is broken.

## 11. Do exceptions after the app is ready exit the JVM via mappers?

**Not automatically.**

After `SpringApplication.run(...)` returns a context, a runtime error can occur in:

- A Spring MVC/WebFlux HTTP controller.
- A Kafka/RabbitMQ/JMS message listener.
- A `@Scheduled` method.
- An `@Async` task or `ExecutorService` worker.
- A batch processing request triggered after startup.

These exceptions flow through **the error handling of their respective technologies**. They **do not automatically re-enter** `SpringApplication`'s `handleRunFailure(...)`. Thus, an `ExitCodeExceptionMapper` bean **is not a global exception handler for every request/thread**.

Example:

~~~java
@GetMapping("/data")
String loadData() {
    throw new InvalidInputException("Bad request payload");
}
~~~

This is a **non-standalone controller snippet** requiring Spring Web, imports, and a controller class. On an HTTP request, the app normally returns an HTTP error status via MVC/WebFlux exception handling; it does **not** terminate the process with 17 by default.

If a job in a background thread throws, the main thread and JVM may stay alive; Boot does not automatically extract `ExitCodeGenerator` from that exception and call `System.exit`. To make a job dictate the entire process exit status, forward outcomes/errors back to an **orchestrator** or the main thread and exit intentionally after cleanup.

## 12. Process status, HTTP status, and batch status are three distinct layers

| Concept | Example values | Used for |
| --- | --- | --- |
| HTTP response status | `400`, `422`, `500` | A single HTTP request |
| Spring Batch `ExitStatus` | `COMPLETED`, `FAILED`, or custom string | Job status inside Batch |
| Process exit code | `0`, `17`, `23` | Outcome of the entire JVM/process |

They may relate, yet **are not the same API**.

A web application can return HTTP 422 for an invalid request and keep serving other requests; a mapper must never kill the entire JVM because one request failed.

A Spring Batch job can finish with its own status, and a `JobExecutionExitCodeGenerator` can help translate job status into a process code under appropriate configuration. Do not confuse Spring Batch's string-based `ExitStatus.getExitCode()` with Spring Boot's `int`-returning `ExitCodeGenerator.getExitCode()`.

### Long-running applications differ from one-shot CLIs

If the application is an HTTP server, a non-zero startup exception typically prevents the instance from coming up; runtime request errors are request concerns and must not trigger JVM exits via a catch-all mapper.

For a CLI/batch app, `main` can wait for the whole job to finish, compute the outcome, and exit intentionally. That is why exit codes are a natural part of the batch contract.

## 13. Mapper priority and maintainability

### Do not write overly broad mappers

A mapper returning non-zero for every exception:

~~~java
@Bean
ExitCodeExceptionMapper alwaysOne() {
    return error -> 1;
}
~~~

can shadow specialized codes from exceptions implementing `ExitCodeGenerator`, since mapped codes take precedence in the startup-failure path.

If you need a generic fallback, define the strategy explicitly rather than carelessly placing it ahead of specialized mappers. In practice, a centralized mapper with clear logic:

~~~java
@Bean
ExitCodeExceptionMapper domainCodes() {
    return error -> {
        for (Throwable t = error; t != null; t = t.getCause()) {
            if (t instanceof InvalidInputException) {
                return 17;
            }
            if (t instanceof TemporaryDependencyException) {
                return 24;
            }
        }
        return 0;
    };
}
~~~

This is an illustrative snippet: `InvalidInputException` and `TemporaryDependencyException` require real classes and imports. Codes 17 and 24 are contract examples.

### Do not overuse @Order

When multiple mappers exist, ordering can affect which code is used if multiple beans return non-zero. You can use `Ordered`/`@Order` per the generator-sorting contract, but you must **test it in practice** on your Boot version and bean declarations.

Do not guess order from class names, component-scanning order, or the top-to-bottom order of `@Bean` methods in a file. If mapping rules are complex or conflict, a single mapper with explicit conditional order is usually easier to reason about.

### Avoid errors inside getExitCode itself

`getExitCode()` should be lightweight, deterministic, and side-effect-free. Do not:

- Make HTTP/DB calls to decide the code.
- Read destroyed beans or rely on a failing context.
- Throw a new exception that obscures the original failure.
- Print secrets from exceptions in logs.
- Call `System.exit` from inside a generator or mapper.

This sits on the **error-handling path**; the simpler it is, the less likely it causes secondary failures.

## 14. Exit codes and cleanup

Exit codes do not replace closing resources.

On startup failure:

1. Boot attempts to determine the code.
2. Reports the error and publishes related events where appropriate.
3. Closes the application context if it was created and can be closed.
4. Fully initialized singletons may receive `@PreDestroy`/`DisposableBean.destroy()` per lifecycle.
5. The exception still escapes `SpringApplication.run` on the failure path.

On a planned exit after a successful run:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

int code = SpringApplication.exit(context);
System.exit(code);
~~~

`SpringApplication.exit` computes the code and closes the context per API. `System.exit` reports the process exit status to the OS. The snippet above is non-standalone and is no substitute for handling errors **before `run` returns**.

### Do not halt the JVM abruptly before cleaning up

If a mapper/handler directly calls `Runtime.getRuntime().halt(...)` or the application calls `System.exit(...)` at an inappropriate time, callbacks/log flushes can be cut short or background tasks abandoned. For critical jobs, stop accepting work, drain in-flight tasks, close resources, and only then exit.

**No pure Java mechanism guarantees all cleanup runs on `SIGKILL`, JVM crash, or host death.** Design recovery/idempotency/checkpoints for those cases.

## 15. Testing exit codes with a child JVM

When testing exception mapping, test at **two levels**.

### Unit level

Call `getExitCode()` on the exception:

~~~java
RuleViolationException e =
        new RuleViolationException("rule failed");

assertEquals(23, e.getExitCode());
~~~

This is a JUnit snippet assuming appropriate imports/class definitions. You can test the mapper directly with a cause chain:

~~~java
Throwable wrapped = new IllegalStateException(
        "Failed to execute ApplicationRunner",
        new InvalidInputException("invalid"));

ExitCodeExceptionMapper mapper = exception -> {
    for (Throwable t = exception; t != null; t = t.getCause()) {
        if (t instanceof InvalidInputException) {
            return 17;
        }
    }
    return 0;
};

assertEquals(17, mapper.getExitCode(wrapped));
~~~

This is a unit-test snippet, not standalone runnable source: it uses JUnit `assertEquals` and the defined exception classes.

### Integration level with a real process

Use `ProcessBuilder` or a test script to launch the JAR in **a child JVM**, pass the mode, capture stdout/stderr, and call `process.waitFor()` to read the status.

Reasons not to call `System.exit` in the same test JVM:

- It can terminate the JVM hosting the JUnit/Gradle test runner.
- Shutdown hooks and process exit codes cannot be tested like normal Java method calls.
- Launchers can transform codes or wrap errors differently.
- A `SpringApplication` context inside a test JVM does not necessarily have the same uncaught-exception handler and thread naming as when launched from a JAR.

### Reasonable integration matrix

| Mode | Custom ExitCodeEvent | Expected JVM code when run directly via Boot launcher |
| --- | --- | --- |
| `success` | No non-zero error event | `0` |
| `exception` | `23` | `23` |
| `mapped` | `17` | `17` |
| `both` | `29` | `29` |
| `unknown` | No custom non-zero event | Inspect actual failure code; typically `1` |

When building automated tests, do not compare only exit codes: also verify the thrown exception type, cause, logs, context cleanup, and that the mapper method was actually invoked.

## 16. Edge cases

### 16.1. Mapper is not invoked when the context is inactive

If `BeanFactory` has not finished refreshing, mapper beans cannot be fetched. Never fix this by "force creating" beans in a broken context state. For very early errors you control, an exception carrying `ExitCodeGenerator` or explicit handling in `main` may be more appropriate.

### 16.2. Deeply nested exceptions

In multi-layer services, you may encounter:

~~~text
IllegalStateException from runner
   └-- CompletionException
          └-- BusinessValidationException
~~~

Mappers should walk the cause chain when the contract requires it. Do not check only `exception.getCause() instanceof ...` when multiple wrapper layers may exist.

### 16.3. Beans implementing ExitCodeGenerator used with SpringApplication.exit

A singleton implementing `ExitCodeGenerator` can return 42 when `SpringApplication.exit(context)` is called, yet **is not automatically invoked merely because an HTTP request threw an exception**. Those are two distinct mechanisms and contexts.

### 16.4. Returning non-zero when a job throws no exception

A batch job can finish executing yet have an outcome like "5 records rejected." If you do not want to throw an exception and trigger startup failure, store the outcome in an `ExitCodeGenerator` bean, call `SpringApplication.exit(context)` after the job, and then `System.exit(code)`. In that flow, exception mapping does not participate.

### 16.5. Exceptions from a background worker

If a runner only submits a task and returns immediately, the application may become ready before the worker fails. To ensure the exit code reflects job errors, the runner/orchestrator must **await completion** or have an error-reporting channel back to `main`; do not expect startup mappers to catch errors on other threads automatically.

### 16.6. Multiple SpringApplication contexts

With parent/child contexts or multiple `SpringApplication.run` calls in one JVM, identify which context owns the mapper bean, which context handles the exception, and which lifecycle closes. Never treat a mapper bean as a global JVM singleton.

### 16.7. Container receives SIGTERM or SIGKILL

Signal termination is distinct from startup exceptions. Do not expect mappers to turn `SIGTERM` into a "business exit code." Process/runtime/shell/orchestrator exit statuses follow their own signal rules, and `SIGKILL` bypasses Java shutdown hooks.

### 16.8. A library throws an Error

`SpringApplication` catches `Throwable` on the startup path; however, if the JVM is in a severe state like `OutOfMemoryError`, mapper beans, event listeners, and cleanup cannot be guaranteed to run. Avoid designing error codes that depend on instantiating new beans when memory is exhausted.

## 17. Anti-patterns and how to fix them

**1. "Every exception automatically becomes code 1."** That is not a Spring Boot business-code policy. Uncaught exceptions usually yield a generic process failure; for deterministic codes, implement a generator/mapper and test the real launcher.

**2. "`ExitCodeGenerator` is only for beans."** False. Exceptions can also implement the interface to provide codes.

**3. "`ExitCodeExceptionMapper` is an annotation."** False. It is a **functional interface**; implement it or return a lambda bean.

**4. "Mappers run before the context exists."** Cannot be assumed; Boot 3.3 checks for an active context to use mapper beans.

**5. "Checking `exception instanceof DomainException` alone is enough."** Not when runners/frameworks wrap exceptions. Walk the cause chain per contract.

**6. "Mapper returning 0 means startup succeeded."** False. 0 only means no mapped non-zero code; the exception can still fail startup.

**7. "If the exception already has code 23, a mapper cannot override it."** False on Boot 3.3's startup-failure path when the context is active: mapped non-zero codes are tried before the fallback.

**8. "Mappers always win even when returning 0."** False. When mappers return 0, Boot continues searching for exceptions carrying `ExitCodeGenerator`.

**9. "`System.exit` is unnecessary because `SpringApplication.exit` closed the context."** Confuses return value with OS process status. `exit(context)` returns an `int`; delivering it to the JVM process requires an appropriate exit mechanism.

**10. "Just call `SpringApplication.exit(null)` in a catch block when `run` fails."** Invalid; there is no successful context to pass, and `SpringApplication` has its own error path.

**11. "The exit code of `gradle bootRun` always equals the app's exact code."** Not guaranteed. Gradle is a build-tool process; invoke the JAR directly when verifying the app JVM's exit status.

**12. "`ExitCodeEvent` always fires whenever an error happens."** False. Non-zero events depend on a code being determined and a context/event publisher being available.

**13. "`ExitCodeExceptionMapper` handles HTTP 400/500 too."** Not by default. HTTP error handlers operate at the request layer.

**14. "An exception in `@Async` automatically terminates the JVM with the `ExitCodeGenerator` code."** False. Orchestration/propagation is needed for a process-level result.

**15. "If multiple mappers return non-zero, Boot sums them or picks the largest."** False. Selection picks non-zero by order, not aggregation.

**16. "You can unconditionally log full exception data."** Exceptions may contain file paths, tokens, SQL, or personal data; apply redaction and logging policies.

**17. "Negative or >255 exit codes are always portable."** False; Unix-like shells have representations that can lose information.

**18. "Business-rule codes work like HTTP status codes."** False. A single HTTP request failure does not exit the entire JVM by default.

**19. "Once a mapper is in place, cleanup is unnecessary."** False. Exit-code mapping does not release database pools, files, threads, or external resources.

**20. "An `ExitCodeGenerator` bean automatically exits the JVM whenever created."** False. The bean only supplies a code when `SpringApplication.exit` or an appropriate flow queries it.

## 18. Process for designing error codes in real applications

For a batch/CLI to have a stable contract:

1. **List states to distinguish:** success, invalid input, non-retryable business error, temporary dependency failure, unclassified failure.
2. **Choose clean, non-conflicting codes:** prefer small positive numbers with clear documentation.
3. **Identify ownership:** which domain exceptions implement `ExitCodeGenerator` themselves? Which library exceptions need a mapper?
4. **Define priority:** avoid mappers matching the same error with different codes; prioritize specialized mappings.
5. **Handle wrappers:** walk the cause chain with a bound, without relying on exact exception messages.
6. **Separate startup failures from runtime failures:** choose the right entrypoint to consume codes.
7. **Clean up before exiting:** ensure resources close and job results are durable before process termination.
8. **Test on a real JVM:** do not rely solely on Gradle status or unit tests calling methods directly.
9. **Monitor metrics/logs:** exit codes, error categories, and correlation IDs; never include secrets.
10. **Document for the scheduler:** which codes retry, which need human intervention, deadlines, and escalation.

A code map can look like:

~~~text
0  -> SUCCESS
17 -> INVALID_INPUT        (do not retry until corrected)
23 -> BUSINESS_RULE_FAILED (notify operator)
24 -> DEPENDENCY_TEMPORARY (bounded retry/backoff)
29 -> POLICY_OVERRIDE      (inspect reason)
1  -> UNKNOWN_FAILURE      (investigate)
~~~

This is an **illustrative operational contract**, not constants provided by Spring Boot.

## 19. Practice exercises

1. State the difference among exit codes `0`, `17`, and `23` in the sample project's contract.
2. Write an exception `InvalidBusinessStateException implements ExitCodeGenerator` returning `31`. Which error branch uses it?
3. Write an `ExitCodeExceptionMapper` mapping `NumberFormatException` to `17`, only when the error appears in the cause chain.
4. Why can a mapper receiving `IllegalStateException("Failed to execute ApplicationRunner", cause)` fail to match if it checks only the outermost `Throwable`?
5. Run `exception` mode. Why does the mapper return 0 yet Boot still resolves 23?
6. Run `mapped` mode. Why did `InvalidInputException` not need editing to implement an interface?
7. Run `both` mode. Explain why the code is 29 instead of 23 in an active context.
8. Remove the `exceptionMapper` bean from the project and re-run `both` mode. With the exception having `getExitCode() == 23`, what fallback code is expected?
9. Remove the mapper and run `mapped` mode. Why is business code 17 no longer provided?
10. Trigger an error inside a bean constructor before context refresh completes. Is the mapper guaranteed to participate?
11. Use an exception with three nested `getCause()` levels. How should the mapper be written to find the subtype at the innermost level?
12. Write two mappers that both return non-zero for one exception. How would you choose an ordering policy or consolidate mappings?
13. Why can a catch-all mapper always returning 1 mask specialized codes?
14. Compare `SpringApplication.exit(context)` and `System.exit(code)`. Which method computes the code and closes the context, and which tells the JVM to stop?
15. Add `@Bean ExitCodeGenerator` returning 42. After the context starts successfully, call `SpringApplication.exit(context)` and observe 42; how does this differ from a startup-failure mapper?
16. Run `mapped` mode with `gradle bootRun` and `java -jar`. Why do they not necessarily yield the same shell exit status?
17. In Bash, run `java -jar` and then insert `echo hi` before `echo $?`. Which command does the read value belong to?
18. In PowerShell, why must you read `$LASTEXITCODE` to inspect a Java process?
19. Have a runner only submit a `CompletableFuture` and return immediately; the background task then throws `InvalidInputException`. Does the startup mapper automatically exit the JVM with 17?
20. A web controller throws `InvalidInputException` on a request. How do the HTTP response and process exit status differ?
21. Write unit tests for a mapper using nested causes and for an exception generator, then write an integration test spawning a JVM to measure the process exit code.
22. Use `ExitCodeEvent` to record an exit-code metric; why should the event listener not call `System.exit` itself?
23. If an exception matches no mapper and implements no generator, should you assert Spring Boot actively returns 0? Why not?
24. For a Linux container receiving `SIGKILL`, does the observed exit code still come from the mapper? Why not?
25. Design a stable exit-code table for an ingestion job: invalid input, temporarily unavailable DB, partial success, and completed; describe the retry policy for each code.

## Key takeaways

- **`ExitCodeGenerator` on an exception:** the exception returns a number itself via `getExitCode()`.
- **`ExitCodeExceptionMapper` bean:** maps a `Throwable` to a code; useful when errors come from library classes or require a unified policy.
- In **Spring Boot 3.3.13's startup-failure flow**, mappers are tried **first**; if they return 0, fallback searches the cause chain for exceptions implementing `ExitCodeGenerator`.
- Mappers require an **active `ApplicationContext`**; very early failures cannot rely on mapper beans.
- `ApplicationRunner`/`CommandLineRunner` can wrap exceptions; walk `getCause()` instead of checking only the outermost layer.
- `0` from a mapper does not mean no exception occurred, nor does it guarantee the process returns 0.
- `SpringApplication.exit(context)` computes the code from **generator beans/arguments** and closes the context; it **does not call `System.exit` itself**.
- `ExitCodeEvent` is for observing determined codes, not a global handler for all exceptions in the application.
- Errors occurring after the application is ready in HTTP requests or background threads do not automatically trigger startup mappers.
- Verify exit codes using **`java -jar` and shell exit status**, not merely logs or `gradle bootRun`.
- Exit codes do not replace cleanup, retry policies, transactions/idempotency, and observability.

### References

- Spring Boot 3.3.13 — SpringApplication / Application Exit: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — `SpringApplication` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3.13 — `ExitCodeGenerator` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeGenerator.html
- Spring Boot 3.3.13 — `ExitCodeExceptionMapper` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeExceptionMapper.html
- Spring Boot 3.3.13 — `ExitCodeEvent` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeEvent.html
- Spring Boot 3.3.13 — `SpringApplication.java` source, failure handling and exit-code selection: https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/SpringApplication.java
- Java SE 17 — `Throwable` and cause chain: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html
- Java SE 17 — `System.exit`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#exit(int)
