# Returning Exit Codes After Completing Resource Cleanup — Spring Boot 3.3

## 1. Objectives

A Java application used as a command-line tool, batch processor, or container worker must return a **process exit code** so shells, CI/CD, schedulers, Docker, or orchestration systems know how the work ended.

In Spring Boot, a common mistake is calling `System.exit(...)` too early: the process starts terminating before still-running tasks, file-writing threads, connection pools, consumers, or beans finish their cleanup sequence. The opposite mistake is completing cleanup yet **failing to translate the business status into a process exit code**, leaving the calling script believing everything succeeded.

This lesson addresses exactly two requirements:

1. **Return an exit code matching the outcome** (`0` for success, non-zero for failure per the application contract).
2. **Perform controlled resource cleanup before process termination**, and handle cases where cleanup itself fails.

After this lesson you will be able to:

- Understand the differences among `SpringApplication.exit(context)`, `ConfigurableApplicationContext.close()`, and `System.exit(code)`.
- Use `ExitCodeGenerator` to report a job's code, even when the job fails business rules while startup itself succeeded.
- Know **when Spring Boot 3.3.13 computes the exit code** relative to `ContextClosedEvent`, `SmartLifecycle.stop(Runnable)`, and `@PreDestroy`.
- Organize cleanup for Spring-managed resources while ensuring async jobs stop before resources close.
- Write a runnable non-web Java 21 / Spring Boot 3.3.13 Maven app with exit code branches `0` and `17`, JUnit tests, and verification commands on Bash, PowerShell, and CMD.
- Distinguish intentional exit commands from `SIGTERM`, force kills, JVM crashes, and startup failures.

**Main point:** a process exit code becomes visible to the operating system only when the **JVM actually terminates**. `SpringApplication.exit(context)` helps compute the code and close the Spring context; **by itself it does not call `System.exit`**, nor does it guarantee background tasks finished if shutdown callbacks are poorly designed.

## 2. What is an exit code and who reads it?

At the OS level, a process reports a numeric code upon termination. In typical CLIs, we adopt conventions such as:

| Code | Application-defined interpretation | Example |
| --- | --- | --- |
| `0` | Success | Batch finished processing; cleanup succeeded |
| `2` | Invalid input/usage | Missing required option |
| `17` | Business error in demo | Input file contains data violating rules |
| `74` | I/O or cleanup error in demo | Flushing/closing/deleting temp file failed |
| Other non-zero codes | Failure per custom contract | Scheduler decides retry/alert |

**Codes `2`, `17`, and `74` here are example application policies**, not mandatory standards defined by Spring Boot. In production, publish a documented exit-code contract and apply it consistently.

To read the code:

```bash
java -jar target/cleanup-exit-demo-0.0.1-SNAPSHOT.jar
echo $?
```

This is Bash/zsh on Unix-like systems; run `echo $?` **immediately after** the Java command under test because any subsequent command overwrites `$?`.

In PowerShell:

```powershell
java -jar target/cleanup-exit-demo-0.0.1-SNAPSHOT.jar
$LASTEXITCODE
```

In CMD:

```bat
java -jar target/cleanup-exit-demo-0.0.1-SNAPSHOT.jar
echo %ERRORLEVEL%
```

If the Java process terminates via `System.exit(17)` under normal conditions, these shells receive the failure status per platform policy. On Unix, only part of the integer width is reflected in traditional exit statuses; choose small, positive, easily monitored codes. Do not mix codes intentionally returned by the application with numbers assigned by the shell/OS when a process is signal-killed.

### 2.1. Returning from `main` differs from process exit

In Java, `public static void main(String[] args)` has a `void` return type. If `main` returns and **no non-daemon threads keep the JVM alive**, the process usually exits with code `0`, unless a failure/handler changes this condition.

A batch job might encounter a business error without throwing an exception or calling exit properly:

```java
public static void main(String[] args) {
    boolean success = processBatch();
    System.out.println("success=" + success);
}
```

This is a **non-standalone illustrative snippet**: `processBatch()` is undefined. When `main` returns normally, the shell may still see `0` even though `success=false`. For callers to learn the outcome, feed the outcome into the exit-code decision flow.

### 2.2. What does `System.exit(int)` do?

`System.exit(code)` instructs the JVM to begin its shutdown sequence with that code. If JVM shutdown hooks are permitted to run, they can execute. However:

- `System.exit` **does not know on its own** which tasks need draining or which resources need flushing.
- It does not wait indefinitely for an async task if that task is not part of a shutdown protocol.
- It is unsuitable to call directly from `@PreDestroy` or inside a shutdown hook.
- It can terminate the entire JVM, affecting other contexts or components in the process.

Use it at the **outermost boundary** of a CLI application that has deliberately finished its work, never scattered across controllers, repositories, listeners, and runners.

## 3. Three easily confused APIs

| API | Primary effect | Closes Spring context? | Directly terminates JVM with chosen code? |
| --- | --- | --- | --- |
| `context.close()` | Stops lifecycle and destroys Spring beans | **Yes** | **No** |
| `SpringApplication.exit(context)` | Computes code from `ExitCodeGenerator`, closes context if possible | **Yes** | **No** |
| `System.exit(code)` | Starts JVM shutdown and passes exit status | Not a direct context-close call | **Yes** |

### 3.1. `ConfigurableApplicationContext.close()`

```java
ConfigurableApplicationContext context = ...;
context.close();
```

This is an **illustrative snippet**, requiring an already started context. In Spring Framework, `close` is a synchronous operation up to the shutdown steps the container actually waits on: publishing `ContextClosedEvent`, calling `LifecycleProcessor.onClose()`, and destroying singleton beans.

However, it does not guarantee **every piece of work a bean ever submitted** has finished if callbacks/workers were poorly designed. Nor does it set a process exit code from business results.

### 3.2. `SpringApplication.exit(context)`

```java
int code = SpringApplication.exit(context);
```

This Spring Boot 3.3.13 API returns an `int`, collecting codes from specified `ExitCodeGenerator` arguments and beans implementing that interface. It attempts to close the `ApplicationContext` if the context supports closing. **After returning**, the context is normally closed per Spring's lifecycle, yet the JVM may remain alive if other non-daemon threads are still running.

You can pass additional generators:

```java
int code = SpringApplication.exit(context, () -> 17);
```

If the application context has `ExitCodeGenerator` beans, all relevant generators are evaluated in order. A directly passed generator does not automatically beat every bean; the rule is the **first non-zero code in generator order**, see section 5.

### 3.3. `System.exit(SpringApplication.exit(context))`

```java
System.exit(SpringApplication.exit(context));
```

Java must **evaluate the argument to `System.exit` first**, so `SpringApplication.exit(context)` is invoked and returns the code before the JVM receives the termination request. This statement is the **official pattern** documented by Spring Boot for command-line applications.

You can also split it into two lines for clearer logging, testing, and policy handling:

```java
int code = SpringApplication.exit(context);
System.exit(code);
```

**Do not reverse** it into `System.exit(code); context.close();`, because `context.close()` after `System.exit` normally never gets a chance to execute.

## 4. A crucial detail in Spring Boot 3.3.13: exit code is computed before close

Inspecting the implementation of `SpringApplication.exit(...)` in Spring Boot 3.3.13 reveals the conceptual sequence:

```text
SpringApplication.exit(context, generators...)
   |
   +-- Find ExitCodeGenerator beans in context
   +-- Combine with caller-supplied generators
   +-- Call getExitCode() in order
   +-- If non-zero, publish ExitCodeEvent
   |
   +-- finally: close ApplicationContext (if closable)
   |      +-- ContextClosedEvent
   |      +-- SmartLifecycle.stop(Runnable) / Lifecycle stop
   |      +-- @PreDestroy / bean destroy
   |
   +-- Handle certain exceptions during exit
   +-- Return int exit code to caller
```

**Critical conclusions:**

- `SpringApplication.exit(...)` **computes the code before `context.close()`**; the code is still **returned** only after the close call finishes or close errors are handled.
- If you only discover a flush error inside `@PreDestroy`, `ExitCodeGenerator.getExitCode()` was already called **earlier** and **cannot automatically "re-read" the new outcome**.
- When a context-close error surfaces as an exception, in Boot 3.3.13's implementation `SpringApplication.exit` logs the error and uses code `1` if no non-zero error code existed yet; if a non-zero code was already computed, that code may be preserved. Do not rely on this exception path as an intentional cleanup-code reporting mechanism.
- Some cleanup errors are logged by the framework without propagating to `SpringApplication.exit` (depending on the callback). In those cases, do not assume code `0` will automatically turn non-zero.
- Therefore, **if the exit code must reflect cleanup status**, execute and verify essential cleanup **before calling `SpringApplication.exit`**, so generators read a stabilized result. Remaining bean destruction afterward still needs proper lifecycle callbacks.
- If cleanup must happen entirely inside `@PreDestroy` and its failure must appear in the exit status, you need explicit orchestration outside the context or a way to clean up and report results **before the close step**, rather than expecting generators to run twice.

This differs from a common misconception: "`SpringApplication.exit` closes the context first and only then queries `ExitCodeGenerator`." **That assumption is incorrect in the 3.3.13 implementation.**

### 4.1. Business errors differ from cleanup errors

A job can have multiple outcomes:

```text
BUSINESS_OK + CLEANUP_OK   -> exit 0
BUSINESS_FAIL + CLEANUP_OK -> exit 17
BUSINESS_OK + CLEANUP_FAIL -> exit 74
BUSINESS_FAIL + CLEANUP_FAIL -> exit code per defined precedence
```

Choose a deliberate policy. For example, this lesson ranks **cleanup failure (74) higher than business failure (17)** so operations knows data or resources may not have been handled safely. In real products, report both business failures and cleanup failures via logs/metrics even when only one process exit status exists.

### 4.2. ExitCodeEvent

When the result from generators is non-zero, Spring Boot can publish `ExitCodeEvent` **before closing the context**. The event exposes `getExitCode()`. Listeners can log or emit metrics for the expected code, yet **must not** rely on this listener to change the code or launch new async work right before shutdown.

Illustrative example:

```java
@Component
class ExitObserver {
    @EventListener
    void onExitCode(ExitCodeEvent event) {
        System.out.println("EXIT event=" + event.getExitCode());
    }
}
```

This snippet requires imports for `@Component`, `@EventListener`, and `ExitCodeEvent`, and must reside inside the Spring context. The full demo in section 7 also includes a matching listener.

## 5. ExitCodeGenerator and code selection

`org.springframework.boot.ExitCodeGenerator` is a functional interface:

```java
@FunctionalInterface
public interface ExitCodeGenerator {
    int getExitCode();
}
```

This is an **illustrative signature**, not an interface to declare yourself. You can supply codes via:

1. A bean implementing `ExitCodeGenerator`.
2. A lambda or object passed directly to `SpringApplication.exit(context, ...)`.
3. An exception implementing `ExitCodeGenerator` when Spring Boot handles an appropriate startup exception.

Example bean:

```java
@Component
class ImportResult implements ExitCodeGenerator {
    private volatile int result;

    public void markBusinessFailure() {
        result = 17;
    }

    @Override
    public int getExitCode() {
        return result;
    }
}
```

**Illustrative code**, requiring imports for `@Component` and `ExitCodeGenerator`. It lets services/runners record status, and Spring Boot reads the code at the end. `volatile` only ensures visibility of a single `int`; multiple threads and multiple error sources need a state machine or atomic policy to avoid races.

### 5.1. Multiple generators

When multiple generators exist, Spring Boot 3.3 picks the **first non-zero code** in the order defined by `Ordered` or `@Order`. There is no default rule like "negative beats positive," "largest code wins," or "last-called generator wins."

When designing systems with multiple failure categories, having **one result aggregator** choose the final code per business precedence is better than letting bean ordering or order tweaks decide subtly.

### 5.2. Reporting errors from startup exceptions

If an `ApplicationRunner` throws an uncaught exception and fails `SpringApplication.run`, **you may not receive a successfully started context to pass to `SpringApplication.exit(context)` from `main`**. Spring Boot has mechanisms to assign exit codes to failure exceptions, including `ExitCodeGenerator` or a matching `ExitCodeExceptionMapper`. Design the startup-failure path separately instead of treating section 7's business-failure-in-result-state demo as a substitute for every exception.

### 5.3. Do not call getExitCode too early

If a job is still running asynchronously, a generator reading state may see `0` before the task fails. You need a completion protocol with timeouts, cancellation, and thread-safe state publication before calling `SpringApplication.exit`.

Do not let generators perform slow I/O, close resources, or launch new work. `getExitCode()` should be fast, stable, and purely read an already-settled outcome.

## 6. Designing the right flow: complete → cleanup → calculate → close → exit

A reliable CLI workflow:

```text
SpringApplication.run(args)
   |
   +-- Spring creates context
   +-- ApplicationRunner executes business job
   |
   +-- Ensure business work reached final state
   |     +-- Stop accepting new jobs
   |     +-- Await async Futures/acks if any
   |
   +-- Intentional cleanup with outcome
   |     +-- Flush files/buffers
   |     +-- Close job-owned resources
   |     +-- Checkpoint and check cleanup errors
   |     +-- Record final outcome in ExitCodeGenerator bean
   |
   +-- SpringApplication.exit(context)
   |     +-- Compute code from generators
   |     +-- Close context
   |           +-- Stop SmartLifecycle beans
   |           +-- @PreDestroy beans still needing cleanup
   |
   +-- Receive returned code
   +-- System.exit(code)
   +-- Shell/scheduler reads code
```

**Dependency relationship:** resources that must stay open for draining must not be closed before consumers stop. Never treat a resource's `@PreDestroy` as a tool that automatically waits for every task that ever used it.

### 6.1. Why not put System.exit inside a runner?

Anti-pattern:

```java
@Component
class DangerousRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        launchBackgroundJobs();
        System.exit(0); // Has not awaited results or cleanup.
    }
}
```

**This is non-standalone illustrative code**. JVM shutdown hooks may run, yet a submitted task does not finish automatically; callers also do not know whether the jobs succeeded. For a one-shot batch, let the runner report outcomes, have `main` or a coordinator await completion and clean up, and only then decide the exit code.

### 6.2. Why not call System.exit inside @PreDestroy?

`@PreDestroy` runs **while the context is being closed**. Calling `System.exit` here can create nested shutdown flows, hold locks, or cut off other destroy callbacks. Use callbacks to release resources; keep JVM termination at the outermost `main`/process supervisor.

### 6.3. Why not simply return from main and expect an error code?

If `main` returns normally without reporting an error, the Java process typically exits with code `0` once no non-daemon threads remain. A service logging `"IMPORT FAILED"` does not automatically turn the OS code non-zero. Especially in CI pipelines, this easily causes **false-green builds**.

## 7. Runnable example — Java 21 and Spring Boot 3.3.13

This non-web demo illustrates:

- `FileBatch` implements `ApplicationRunner` to simulate a job, create a temporary file, and write one line of data.
- `FileBatch` also implements `ExitCodeGenerator`, holding code `0` or `17` per the `--business-fail` option; if flushing/closing/deleting the temp file fails, it reports code `74`.
- `finishAndCleanup()` performs cleanup **before the generator is queried**, recording the final outcome.
- `@PreDestroy` acts as a fallback cleanup if the context closes via another path; on the standard path, it simply confirms cleanup already ran.
- `ExitObserver` observes `ExitCodeEvent` only when the exit code is non-zero.
- `CleanupExitApplication` calls `SpringApplication.exit(context)` and **only then calls `System.exit(code)`**.
- JUnit tests create/close contexts themselves and assert codes without calling `System.exit` and killing the test runner.

The demo intentionally omits an HTTP server because batch CLIs have a clear completion point. No database, message broker, or external account is required.

### 7.1. Project structure

```text
cleanup-exit-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/exit/
    │   ├── CleanupExitApplication.java
    │   ├── FileBatch.java
    │   └── ExitObserver.java
    └── test/java/com/example/exit/
        └── CleanupExitTest.java
```

### 7.2. Maven pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>cleanup-exit-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot 3.3 has a Java 17 minimum and supports Java 21. `spring-boot-starter` suffices to create a non-web context and runners; the test starter includes JUnit Jupiter.

### 7.3. The main class

File `src/main/java/com/example/exit/CleanupExitApplication.java`:

```java
package com.example.exit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class CleanupExitApplication {

    public static void main(String[] args) {
        int code = runAndClose(args);
        System.exit(code);
    }

    public static int runAndClose(String... args) {
        SpringApplication application =
                new SpringApplication(CleanupExitApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context = application.run(args);
        try {
            FileBatch job = context.getBean(FileBatch.class);

            // Cleanup reports outcome before getExitCode is called.
            job.finishAndCleanup();

            // Compute exit code and close the Spring context.
            int code = SpringApplication.exit(context);
            System.out.println("MAIN context closed, code=" + code);
            return code;
        }
        finally {
            if (context.isActive()) {
                context.close();
            }
        }
    }
}
```

**Key points:**

- `SpringApplication.run` invokes `ApplicationRunner` during bootstrap.
- `FileBatch.finishAndCleanup()` synchronously completes flush/close/delete and updates state.
- `SpringApplication.exit` reads `ExitCodeGenerator`, publishes an event when non-zero, and closes the context.
- `System.exit` **appears only in `main`**, not in services, runners, or `@PreDestroy`.
- `runAndClose` **can be called directly from JUnit without terminating the test JVM**.
- `finally` is a safety net closing the context if an exception occurs before or during exit. It does not replace startup exception-handling policies before `application.run` returns a context.

For production code, define both startup-failure and unexpected-runtime-failure paths: if `run()` throws an exception, Boot has mechanisms to close the context and handle exit exceptions itself; never blindly call `SpringApplication.exit(null)` or assume the example method always receives a context.

### 7.4. FileBatch.java — recording business results and cleanup

File `src/main/java/com/example/exit/FileBatch.java`:

```java
package com.example.exit;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import jakarta.annotation.PreDestroy;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.stereotype.Component;

@Component
public class FileBatch implements ApplicationRunner, ExitCodeGenerator {

    private BufferedWriter writer;
    private Path file;
    private int exitCode;
    private boolean cleaned;

    @Override
    public synchronized void run(ApplicationArguments args) throws Exception {
        file = Files.createTempFile("cleanup-exit-", ".txt");
        writer = Files.newBufferedWriter(file, StandardCharsets.UTF_8);
        writer.write("example-batch-entry");
        writer.newLine();

        // Business failure example is still recorded as a result,
        // instead of calling System.exit directly inside the runner.
        exitCode = args.containsOption("business-fail") ? 17 : 0;
        System.out.println("JOB desiredCode=" + exitCode);
    }

    public synchronized void finishAndCleanup() {
        if (cleaned) {
            return;
        }

        IOException failure = null;

        if (writer != null) {
            try {
                writer.flush();
            }
            catch (IOException ex) {
                failure = ex;
            }

            try {
                writer.close();
            }
            catch (IOException ex) {
                if (failure == null) {
                    failure = ex;
                }
                else {
                    failure.addSuppressed(ex);
                }
            }
            writer = null;
        }

        if (file != null) {
            try {
                Files.deleteIfExists(file);
            }
            catch (IOException ex) {
                if (failure == null) {
                    failure = ex;
                }
                else {
                    failure.addSuppressed(ex);
                }
            }
        }

        cleaned = true;

        if (failure == null) {
            System.out.println("CLEANUP completed");
        }
        else {
            // Demo prioritizes cleanup failure over business failure.
            exitCode = 74;
            System.err.println("CLEANUP failed: "
                    + failure.getClass().getSimpleName());
        }
    }

    public synchronized boolean isCleaned() {
        return cleaned;
    }

    @Override
    public synchronized int getExitCode() {
        return exitCode;
    }

    @PreDestroy
    void destroy() {
        // If another context-close path occurs, attempt best-effort cleanup.
        finishAndCleanup();
        System.out.println("BEAN preDestroy");
    }
}
```

In the demo, `FileBatch` creates a temp file, writes data, flushes/closes the writer, and deletes the file once finished. The goal is illustrating resource lifecycles, not writing a real business report meant to survive process exit.

**Do not delete real business data** after processing: deleting the temp file in the demo applies only to a resource created by the job as temporary scratch output. For durable outputs, use flush/fsync/atomic renames per durability requirements.

`finishAndCleanup()` is `synchronized` to avoid two callers closing the writer simultaneously in the demo, and `cleaned` prevents double cleanup. In production, also address concurrency with tasks that might still be writing to the writer: a `synchronized` method on the owner alone **is not enough** if background threads do not share an admission/drain protocol.

**Error note:** the method attempts flush, close, and file deletion on a best-effort basis, capturing the first error and attaching subsequent errors as suppressed. It sets `74` so the caller does not report success. In production, log the full cause with stack trace, safe file path, retry policy, and ensure recoverable data is never hidden. Setting `cleaned=true` here means **one cleanup pass ran and recorded its result**, not that all resources were guaranteed freed when an error occurred.

### 7.5. ExitObserver.java

File `src/main/java/com/example/exit/ExitObserver.java`:

```java
package com.example.exit;

import org.springframework.boot.ExitCodeEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ExitObserver {

    @EventListener
    public void onExit(ExitCodeEvent event) {
        System.out.println("EXIT event=" + event.getExitCode());
    }
}
```

`ExitCodeEvent` is published when `SpringApplication.exit` resolves a non-zero code. It fires **before the context-close step**. This listener only logs; never submit new jobs or alter business status at the last moment.

### 7.6. Build and run

Install Java 21 and Maven. Inside `cleanup-exit-demo`:

```bash
java -version
mvn -version
mvn test
mvn package
java -jar target/cleanup-exit-demo-0.0.1-SNAPSHOT.jar
echo $?
```

In Bash/zsh, the lines **intentionally printed by the demo code** in order on the success branch are:

```text
JOB desiredCode=0
CLEANUP completed
BEAN preDestroy
MAIN context closed, code=0
```

After the process exits, `echo $?` prints:

```text
0
```

Spring Boot also prints banners/other startup logs; the blocks above are not the entire stdout. Since `code=0`, `ExitCodeEvent` is not published by this exit call, so there is no `EXIT event` line on the success branch.

### 7.7. Run the business-failure branch

```bash
java -jar target/cleanup-exit-demo-0.0.1-SNAPSHOT.jar --business-fail
echo $?
```

The lines printed by the code will be:

```text
JOB desiredCode=17
CLEANUP completed
EXIT event=17
BEAN preDestroy
MAIN context closed, code=17
```

Immediately after the Java command, `echo $?` prints:

```text
17
```

`EXIT event=17` occurs before `BEAN preDestroy`, accurately illustrating: **generators determine the exit code before context cleanup/destroy**. Intentional cleanup ran earlier so the code can reflect any failure from that step.

### 7.8. Why not force a cleanup failure using file permissions in the demo?

Trying to trigger real I/O errors via file permissions or filling the filesystem makes tests OS/container-dependent and causes side effects. In production code, introduce a mockable abstraction for file operations or an explicit `CleanupOutcome` and unit-test failure branches with injected fakes rather than mutating real filesystems to simulate errors.

Do not change the demo to `throw new IOException` directly inside `@PreDestroy` expecting `ExitCodeGenerator` to see the error: the generator phase has already passed and many destroy exceptions are only logged.

## 8. JUnit: verifying returned codes without stopping the test JVM

File `src/test/java/com/example/exit/CleanupExitTest.java`:

```java
package com.example.exit;

import org.junit.jupiter.api.Test;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CleanupExitTest {

    @Test
    void successCodeIsReturnedAfterCleanupAndContextClose() {
        verifyExit(0);
    }

    @Test
    void businessFailurePreservesItsCodeAfterCleanup() {
        verifyExit(17, "--business-fail");
    }

    private void verifyExit(int expectedCode, String... args) {
        SpringApplication app =
                new SpringApplication(CleanupExitApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context = app.run(args);
        try {
            FileBatch job = context.getBean(FileBatch.class);
            job.finishAndCleanup();

            assertTrue(job.isCleaned());
            assertEquals(expectedCode, job.getExitCode());

            int returnedCode = SpringApplication.exit(context);

            assertEquals(expectedCode, returnedCode);
            assertFalse(context.isActive());
        }
        finally {
            if (context.isActive()) {
                context.close();
            }
        }
    }
}
```

Run:

```bash
mvn test
```

This class is expected to run **2 passing tests** without calling `System.exit()` inside JUnit. `SpringApplication` creates an isolated context for each test, executes `ApplicationRunner`, and `SpringApplication.exit` computes the code and closes the context.

The assertions verify:

1. The job ran and intentional cleanup was invoked.
2. `ExitCodeGenerator` preserved the right business code after cleanup.
3. `SpringApplication.exit` returned the right code.
4. The context was closed.

This test **does not prove subprocess OS exit codes** because it does not spawn another JVM. To test OS exit end-to-end, run `java -jar` as a subprocess or via a CLI script/CI job and read its exit status. Never call `CleanupExitApplication.main(...)` directly inside a test because `System.exit` can terminate the entire JUnit process.

### 8.1. Checking the code on Windows

PowerShell:

```powershell
java -jar target/cleanup-exit-demo-0.0.1-SNAPSHOT.jar --business-fail
$LASTEXITCODE
```

CMD:

```bat
java -jar target/cleanup-exit-demo-0.0.1-SNAPSHOT.jar --business-fail
echo %ERRORLEVEL%
```

Expected code is `17` with the option present. Without it, `0`.

### 8.2. Testing multiple generators

An additional test can supply two `ExitCodeGenerator` lambdas:

```java
int code = SpringApplication.exit(context, () -> 0, () -> 23);
```

**This is an illustrative snippet**; do not place it after `SpringApplication.exit(context)` in the main test because the context is already closed. With multiple generators, verify Spring Boot ordering/sorting rather than assuming "last generator wins." If you need a strict precedence contract, use one aggregator returning a single code.

## 9. When cleanup is asynchronous

In real applications, cleanup may involve:

- Awaiting in-flight HTTP requests.
- Stopping Kafka/RabbitMQ consumers and acknowledging processed messages.
- Awaiting `CompletableFuture`, executor tasks, or scheduled jobs.
- Flushing file streams, committing/rolling back transactions, or checkpointing.
- Canceling subscriptions and closing network clients.
- Finally closing datasources, broker connections, thread pools, and shared resources.

A proper sequence:

```text
ACCEPTING
   |
   | request shutdown
   v
STOPPING: stop accepting new jobs
   |
   | await accepted tasks with timeout / retry policy
   v
DRAINED
   |
   | flush/commit/ACK (dependencies still alive)
   v
CLEANED
   |
   | SpringApplication.exit(context)
   v
CONTEXT CLOSED
   |
   | System.exit(code)
   v
JVM EXITED
```

### 9.1. SmartLifecycle.stop(Runnable)

**Architectural pattern** example:

```java
@Override
public void stop(Runnable callback) {
    stopAccepting();

    CompletionStage<Void> drained = drainWithTimeout();
    drained.whenComplete((unused, failure) -> {
        if (failure != null) {
            recordFailure(failure);
            handleRetryOrCancel();
        }
        markStopped();
        callback.run();
    });
}
```

This snippet **does not compile standalone**; methods, imports, and synchronization must be defined. It shows that `stop(Runnable)` must not invoke `callback` right when drain is submitted. If the callback runs prematurely, the lifecycle processor may close resource providers in the next phase while tasks are still using them.

**Important:** the `stop` invoked by Spring when `SpringApplication.exit` closes the context happens **after generators already returned the code**, so cleanup errors first detected here will not automatically change the exit code. If the code must reflect errors, use an **explicit pre-exit drain phase** or another exit orchestrator that receives completion/error before settling the code.

### 9.2. Avoid deadlocks when awaiting pools

A buggy example:

```text
Executor: single worker only
   |
   +-- Worker runs shutdown coordinator
           |
           +-- Submit cleanup task to same executor
           +-- future.get() waits for cleanup
                  |
                  +-- Cleanup is never scheduled
```

When using `Future.get(timeout)` or latch timeouts, check whether the executor running the coordinator still has capacity to finish the task it is waiting on. You may need a dedicated coordinator thread, callback-based completion, or synchronous stopping outside the pool.

### 9.3. A timeout does not mean cleanup succeeded

`Future.get(5, TimeUnit.SECONDS)` timing out **does not automatically cancel** the background task. `Future.cancel(true)` only requests an interrupt if the task is cooperative; I/O may continue and DB transactions may still be pending.

Therefore, when a deadline expires:

1. Record the incomplete job state.
2. Request appropriate cancellation and await confirmation if possible.
3. Emit specific error codes/metrics.
4. Ensure data sources can retry or roll back.
5. Never declare "cleanup completed" while a task still holds resource access.

When complete cleanup cannot be achieved, returning a non-zero exit code and ensuring durable recovery state matters far more than logging a false success.

### 9.4. Transactions and resource ownership

An `@Async` task running on another thread does not inherit the caller's thread-local transaction. Never close the `DataSource` as soon as a business method returns if background transactions are still using the connection pool.

The resource owner (container, connection manager) is responsible for closing the pool; consumers only close **borrowed connections** upon finishing. If critical tasks must never be lost on process death, use transactional outboxes/durable queues and idempotent processing rather than relying on Java shutdown hooks.

## 10. Exit codes when closing the context fails

A decision table:

| State | Suggested code | Notes |
| --- | --- | --- |
| Business succeeded, explicit cleanup succeeded | `0` | Goes through Spring context close before `System.exit` |
| Business failed, explicit cleanup succeeded | `17` | Business result settled before generator |
| Explicit cleanup failed | `74` | Ranked above business failure per demo policy |
| Exception in `context.close()` after generator reported `0` | May be `1` per Boot 3.3 exit helper | Depends on exception propagating to the helper |
| Exception in `context.close()` when code is already non-zero | Helper may keep initial non-zero code | Should not replace explicit cleanup-result logic |
| Async task killed without reporting completion | No guarantee of desired app code | Requires recovery/deadlines/process supervision |

**Do not rely on exceptions in `@PreDestroy` to determine code 74:** generators normally run beforehand; some destroy errors may be logged and swallowed by the framework per bean destruction contracts.

### 10.1. Error mapping in Spring Boot

An exception implementing `ExitCodeGenerator` or a matching mapper can make Spring Boot report an error code when startup/run fails. This is a separate path from `SpringApplication.exit(context)` on a successfully started context.

If `ApplicationRunner` throws an exception and `SpringApplication.run` returns no context, do not put cleanup/exit logic in code **that only runs after `run()`** expecting it to always be called. In practice:

- Bind cleanup to resource owners and Spring failure shutdown callbacks.
- Have retry/exception-mapping policies for startup failures.
- Never call `System.exit(0)` in a catch block to hide errors.
- Write errors to `stderr` and structured logs when monitoring requires it.

### 10.2. ExitCodeEvent does not announce cleanup completion

`ExitCodeEvent` can fire on a non-zero generator code **before close**. Therefore, its listeners do not signal "all resources cleaned" or "JVM about to be physically terminated" in the sense that all hooks finished.

To log a **cleanup completed** milestone, log after the coordinator's own completion signal or after `SpringApplication.exit` returns; note that unrelated JVM shutdown hooks triggered by `System.exit` may still run afterward.

## 11. Differences between CLI batches and server applications

### 11.1. CLI batch

Batches have a natural completion point. You can structure them as:

```text
run job -> await result -> explicit cleanup -> SpringApplication.exit -> System.exit
```

When an accurate OS code is needed so cron/CI knows whether the job succeeded, `System.exit` in `main` is a sensible choice.

### 11.2. Long-running web services

Servers normally **do not** call `System.exit` after `SpringApplication.run`, because they must serve requests. Upon receiving `SIGTERM` or container orchestration termination, Spring Boot's shutdown hook usually closes the context. The code reported by the OS/container in a signal-termination scenario is not automatically generated by an `ExitCodeGenerator` bean; distinguish **process signal status** from **explicitly calling `SpringApplication.exit`**.

Spring Boot 3.3 supports graceful web shutdown via:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

This is an example for **web servers**, not opening an HTTP endpoint in section 7's CLI project. Graceful HTTP shutdown does not automatically wait for async jobs detached from request lifecycles; workers need separate stop/drain handling.

### 11.3. Shutdown in Docker and Kubernetes

Orchestration platforms normally send a stop signal, wait a grace period, and force-kill if the deadline expires. To give the process a chance to return a reliable code:

- Ensure the JVM actually receives signals (proper PID/entrypoint, not swallowed by a wrapper).
- Provide enough grace period for traffic draining, worker draining, and bean cleanup.
- Avoid `SIGKILL`/OOM/power loss; if they occur, shutdown hooks are not guaranteed.
- Design durable work and retryability after restarts.
- In health/rollouts, do not treat `exit 0` as proof all out-of-process data was durably synced unless the workflow guarantees it.

**Never force a server app to call `System.exit` inside a controller just to return an HTTP error code.** HTTP status codes and process exit codes are two separate mechanisms.

## 12. Common mistakes

| Mistake | Why it is wrong | Fix |
| --- | --- | --- |
| Calling `System.exit(0)` directly inside `ApplicationRunner` | Background tasks/cleanup may still be unfinished | Await results, clean up, `SpringApplication.exit`, then `System.exit` |
| `System.exit` followed by `context.close()` | Statements afterward usually never run | Reverse order; close context first |
| Calling only `SpringApplication.exit(context)` assuming OS gets the code | Helper only returns `int`; does not exit the JVM | At outermost `main`, call `System.exit(code)` if truly needed |
| Calling only `context.close()` assuming business error code is sent | Close carries no business exit code | Use `ExitCodeGenerator` / explicit result |
| Believing a `@PreDestroy` error changes the generator exit code automatically | Generators run before destroy | Run outcome-reporting cleanup before calling `exit` |
| Computing code while async jobs are still running | Generator reads non-final state | Await completion/timeout and settle outcome first |
| `getExitCode()` doing long network I/O | Complicates exit and risks timeouts | Generators should only read settled final state |
| Multiple `ExitCodeGenerator` beans without rules | Selection order for first non-zero is unclear | Use `Ordered` or a single aggregator |
| Calling `System.exit` inside `@PreDestroy` | Reentrant shutdown, locks/cleanup corruption | Terminate only at outermost boundary |
| Catching cleanup errors and reporting `0` | CI gets a false green | Return non-zero code and log error |
| Seeing `0` and assuming the job is durable | Async writes/DB may not have committed | Flush/fsync/transaction/ack per contract |
| Awaiting futures infinitely during shutdown | Process may be killed before finishing | Timeouts, cancellation, checkpoints/retries |
| Tests calling `main` with `System.exit` | Terminates the JUnit JVM | Test `runAndClose` method; use subprocess for end-to-end |
| Not checking `$?` immediately after Java | Shell status overwritten by later commands | Read status immediately |
| Confusing HTTP status `500` with process exit code | Two different error-reporting layers | HTTP code for requests, exit code for entire process |
| Expecting `SIGKILL` to run cleanup | JVM gets no chance | Durable state, retry/recovery |

## 13. Pre-production checklist

1. Are code `0` and non-zero codes defined in the contract with schedulers/CI?
2. Has business work genuinely completed (or settled as FAILED) before computing the code?
3. Are any tasks submitted yet unstarted or still sitting in an executor queue?
4. Is there explicit cleanup for resources whose outcome generators need to know?
5. Are cleanup failures distinguished from business failures and both logged?
6. Is `ExitCodeGenerator.getExitCode()` deterministic, thread-safe, and fast?
7. Is there one result aggregator or explicit ordering when multiple generators exist?
8. Is `SpringApplication.exit(context)` called on a valid started context?
9. Are `context.close()`/Spring-managed destroy and `SmartLifecycle` stop configured with proper phases?
10. Does `stop(Runnable)` invoke its callback after genuine draining, not prematurely?
11. Are deadlines and shutdown-phase timeouts aligned with the platform?
12. Are `System.exit` calls kept out of runners, workers, and destroy hooks?
13. Does the shell/CI actually inspect the process exit status?
14. Do unit/integration tests isolate the code-returning method from `main` so the test JVM isn't killed?
15. Is there a startup-failure plan when `run()` returns no context?
16. Are `SIGTERM`/`SIGKILL` scenarios and interrupted-job recovery covered?
17. Are flush/commit/ack guarantees in place for data needing durability?
18. Do metrics/logs distinguish `cleanup requested`, `cleanup completed`, and `context closed`?
19. Are resources prevented from closing while consumers still use them?
20. When context close errors occur, are codes/exceptions recorded for investigation?

## 14. Practice exercises

1. State the differences among `context.close()`, `SpringApplication.exit(context)`, and `System.exit(code)`.
2. Why does `System.exit(SpringApplication.exit(context))` close the context before the process exits?
3. If Java `main` returns normally after printing `"FAILED"`, what default OS code might be observed?
4. Why shouldn't an `ExitCodeGenerator` wait on network calls inside `getExitCode()`?
5. In Boot 3.3.13's implementation, are generators queried **before or after** `@PreDestroy`?
6. Why shouldn't cleanup codes be computed solely inside `@PreDestroy` if generators were already read beforehand?
7. Run the demo without options; verify `CLEANUP completed` appears before `BEAN preDestroy`.
8. Run `--business-fail`; verify process exit `17` using Bash `$?` or PowerShell `$LASTEXITCODE`.
9. Explain why `EXIT event=17` occurs before `BEAN preDestroy`.
10. If cleanup fails, why does the lesson prioritize code `74` over `17`?
11. Write an `ExitCodeGenerator` bean for three states: `SUCCESS`, `INPUT_ERROR`, and `IO_ERROR`.
12. If two `ExitCodeGenerator` beans both report errors, which code does Spring Boot select?
13. In JUnit, why must you not call `CleanupExitApplication.main` directly?
14. Write a subprocess test launching the JAR, waiting for the process, and asserting the exit code.
15. Add a fake `FileOperations` abstraction to test `close()` failures without altering OS permissions.
16. If `ApplicationRunner` throws an exception during `SpringApplication.run`, why might code after `run` never execute?
17. Explain the role of `ExitCodeExceptionMapper` on the startup-failure path.
18. When is `@PreDestroy` used as a fallback, and why shouldn't the primary code depend on that fallback?
19. Design shutdown/draining for a worker with hundreds of tasks running on a thread pool.
20. Why does a future timeout not mean the worker stopped?
21. If a container receives `SIGKILL`, which hooks are not guaranteed to execute?
22. For an HTTP service, why shouldn't `System.exit` be called right after server startup?
23. Compare HTTP status 503, process exit code 17, and readiness refusal.
24. When no work may be lost after a crash, propose outboxes/durable queues/idempotency.
25. Design a runbook covering: stop accepting, wait, flush, checkpoint, exit code, close context, exit JVM.

**Pass criteria:** runnable Java 21/Boot 3.3 code, clear distinction between business and cleanup outcomes, understanding that `SpringApplication.exit` resolves the code before closing the context yet returns it after closing, avoiding premature `System.exit`, and clear awareness of JVM/crash/platform shutdown limits.

## 15. Official documentation

- Spring Boot 3.3.13 — `SpringApplication.exit(...)`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3.13 — Application Exit and ExitCodeGenerator: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — `ExitCodeGenerator`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeGenerator.html
- Spring Boot 3.3.13 — `ExitCodeEvent`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeEvent.html
- Spring Boot 3.3.13 — `SpringApplication.exit` source: https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/SpringApplication.java
- Spring Framework 6.1 — `ConfigurableApplicationContext`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html
- Spring Framework 6.1 — `SmartLifecycle`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Boot 3.3 — Graceful shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Java 21 — `System.exit` and JVM runtime shutdown: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html
