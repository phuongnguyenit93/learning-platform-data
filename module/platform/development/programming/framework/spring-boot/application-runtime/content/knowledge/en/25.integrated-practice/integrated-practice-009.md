# Building a Command-Line Application with Exit Codes and Testing It via Child Processes

## Learning Objectives

A Spring Boot command-line application (CLI), batch job, or one-shot worker often needs to report **its outcome to the operating system**: completed successfully, partially completed, invalid input data, retry needed, or startup failed. Printing `"FAILED"` to the console is not enough, because shells, CI/CD pipelines, schedulers, and containers typically make decisions based on the **process exit code**.

Spring Boot provides `ExitCodeGenerator` and `SpringApplication.exit(...)`; Java provides `System.exit(int)`. To verify this contract, a test cannot merely call `main` inside the JUnit JVM: `System.exit` can terminate the test runner itself. An **integration test suite using `ProcessBuilder` to spawn a child JVM**, execute the real executable JAR, wait with a deadline, read output, and assert `Process.exitValue()` is far more appropriate.

This lesson belongs to **Spring Boot Application Runtime → Integrated Practice**. The example targets **Java 17+**, **Spring Boot 3.3.13**, **Gradle**, and **JUnit 5**, working on Windows/Linux/macOS with the Java executable and JAR paths passed as separate arguments.

After this lesson, you will be able to:

1. Distinguish returning from `main`, `SpringApplication.exit(context)`, and `System.exit(code)`.
2. Build a Spring Boot CLI with `WebApplicationType.NONE` and an `ApplicationRunner` executing business logic once.
3. Store business outcome state in a bean and supply the code via an `@Bean ExitCodeGenerator`.
4. Create a startup exception implementing `ExitCodeGenerator`, inspect the cause chain, and pass an intentional exit status.
5. Distinguish **context/runner initialization** errors from business logic that ran and returned a **non-zero** outcome.
6. Use `ProcessBuilder` to launch the exact Java executable and built `bootJar`, independent of shell quoting.
7. Merge stdout/stderr into a temporary file to prevent pipe-buffer deadlocks; handle timeouts and kill child processes.
8. Write tests asserting **codes 0, 12, 21, 30, 43, 64**, marker logs, ready/close ordering, and failure cases.
9. Configure Gradle `test dependsOn bootJar` so tests always run against the latest artifact.
10. Understand the differences between the **Java application's** exit code, **Gradle's** exit code, **shell pipeline** exit status, and container status.
11. Design CLI integration into CI/CD, Kubernetes Jobs, or schedulers with appropriate retries, idempotency, and observability.
12. Extend tests for missing arguments, long runs, large stderr output, environment variables, and resource cleanup.

**Intentional scope limit:** The demo uses no HTTP server, database, Kafka, or real network. This keeps outcomes deterministic and focused on **exit codes and child-process testing**. Real I/O operations require adding timeouts, transactions/idempotency, cleanup, and SDK-appropriate resource management.

## 1. Exit Codes Are Part of the CLI Contract

A JVM terminates with an integer returned to the process owner. By common convention:

- **0:** the program completed successfully.
- **Non-zero:** failure or another status requiring orchestrator handling.
- **Specific meaning of non-zero codes:** defined by **the application and operations team**, not a universal table assigned by Spring Boot.

Example of a data-import job:

| Code | Demo Status Name | Meaning | Handling Suggestion |
| ---: | --- | --- | --- |
| `0` | `SUCCESS` | All data valid and job completed | Do not retry |
| `12` | `PARTIAL_RESULT` | Partially processed; some records rejected per policy | Inspect report and decide |
| `21` | `INVALID_INPUT` | Invalid business input | Fix data before re-running |
| `30` | `TEMPORARY_UNAVAILABLE` | Infrastructure temporarily unavailable per business policy | Retry with limits/backoff |
| `43` | `FATAL_STARTUP` | Runner threw a classified startup error | Stop and investigate cause |
| `64` | `USAGE_ERROR` | Unsupported CLI arguments | Fix program invocation |
| `1` | `UNCLASSIFIED_FAILURE` | Other error without a dedicated code | Investigate before retrying |

**Important:** The numbers above are **this learning project's own convention**, not a standard guaranteed by Spring Boot. In production, use concise codes, document their meanings, and align with your batch scheduler.

### Do Not Confuse 0 with "No Exception Thrown"

A runner can finish **executing** while the business result is not fully satisfactory. For instance, a job finishes reading an entire file and counts 5 invalid records. Having the runner **return normally** may be accurate for Spring Boot's lifecycle, yet the CLI still needs to return code `12` to the caller.

Conversely, when a runner throws an exception, `SpringApplication.run(...)` does not finish along the success path. **Startup failure** handling can supply a code via an exception implementing `ExitCodeGenerator`.

These two paths differ and are represented separately in the project:

~~~text
                    SpringApplication.run(args)
                               |
                      ApplicationRunner
                       /             \
          runner return               runner throw
               |                            |
       ApplicationReadyEvent         startup failure path
               |                            |
         context returned            context not returned
               |                            |
       SpringApplication.exit        error/cause classified
               |                            |
       ExitCodeGenerator bean        code from exception or policy
               |                            |
               +------------+---------------+
                            |
                   System.exit(code)
                            |
                   OS/shell receives exit status
~~~

## 2. Three Non-Interchangeable APIs

### `SpringApplication.run(...)`

~~~java
ConfigurableApplicationContext context =
        new SpringApplication(CliApplication.class).run(args);
~~~

This is an **illustrative snippet**, requiring `CliApplication` and appropriate imports. `run(...)` builds the context and executes runners. If startup fails, the method may throw an exception before returning `context`.

### `SpringApplication.exit(context)`

~~~java
int code = SpringApplication.exit(context);
~~~

It computes an exit code based on `ExitCodeGenerator` beans/arguments, publishes an appropriate `ExitCodeEvent`, and **closes the context** if possible. Per Spring Boot 3.3.13 Javadoc, when multiple generators exist, the **first non-zero** code after ordering is used.

**This method returns an `int`. It does not call `System.exit` itself to terminate the JVM and hand status to the OS.**

### `System.exit(code)`

~~~java
System.exit(code);
~~~

This is the JVM call requesting process termination with the desired exit status. It affects **the entire JVM**, so invoke it only at the **outermost entrypoint** of a CLI application once business logic and cleanup have been handled.

Never call `System.exit(...)` inside a running JUnit test JVM, bean constructor, `@PostConstruct`, or out of habit inside a mapper. If the program contains non-daemon background threads, `System.exit` can cut short unfinished work; design draining/cleanup beforehand.

### Comparison Table

| Mechanism | Runs Startup? | Closes Context? | Returns Code to OS? |
| --- | --- | --- | --- |
| `SpringApplication.run` | Yes | No on success path; failure cleanup on error | Not directly |
| `ApplicationRunner.run` | Business step before Ready | Not by default | No |
| `ExitCodeGenerator.getExitCode` | No; only supplies a number | No | No |
| `SpringApplication.exit(context)` | Does not re-run startup | Yes | Only returns int to caller |
| `System.exit(code)` | No | Triggers JVM shutdown; hooks may run | Yes |
| Returning from `main` | Calls no further Boot mechanism | Does not proactively close bean context | JVM typically returns 0 on normal exit |

**Common trap:** Printing `"EXIT=30"` does not make the process exit with code 30. Only the real exit code—`Process.exitValue()`, `$?`, or `$LASTEXITCODE`—proves the orchestrator received the right status.

## 3. Why Choose `WebApplicationType.NONE`?

A one-shot job application does not need Tomcat or HTTP endpoints. Configuring:

~~~java
SpringApplication app = new SpringApplication(CliExitApplication.class);
app.setWebApplicationType(WebApplicationType.NONE);
~~~

tells Spring Boot to use a non-web application context. Yet **it still runs a real Spring lifecycle**:

- Environment and property sources.
- Bean creation, dependency injection.
- `@PostConstruct` and bean destroy callbacks.
- `ApplicationRunner` or `CommandLineRunner`.
- `ApplicationStartedEvent`, `ApplicationReadyEvent`, or `ApplicationFailedEvent` depending on the path.
- `SpringApplication.exit(context)` and context closing.

`NONE` does **not** automatically turn off user-declared schedulers, thread pools, database clients, or message listeners. A CLI can fail to exit if non-daemon threads remain. This project creates no such resources so tests never hang unexpectedly.

### When Is `WebApplicationType.SERVLET` Needed?

If the job must also listen on HTTP, expose Actuator, or serve requests, `NONE` is unsuitable. However, this lab is **CLI practice with process exit statuses**; non-web keeps the test goal focused and avoids port conflicts.

**Do not confuse `server.port=0` with `NONE`:** Port 0 still starts a web server on a random port when the app is servlet/reactive web. `NONE` starts no embedded HTTP server.

## 4. Project Contract and Scenarios

The application accepts one option:

~~~text
--demo.mode=<mode>
~~~

Valid modes:

| Mode | What Runner Does | Ready Fires? | Code Resolution Path | Exit Code |
| --- | --- | --- | --- | ---: |
| `success` | Records SUCCESS, returns | Yes | `ExitCodeGenerator` bean | 0 |
| `partial` | Records PARTIAL_RESULT, returns | Yes | `ExitCodeGenerator` bean | 12 |
| `invalid` | Records INVALID_INPUT, returns | Yes | `ExitCodeGenerator` bean | 21 |
| `retry` | Records TEMPORARY_UNAVAILABLE, returns | Yes | `ExitCodeGenerator` bean | 30 |
| `fatal` | Throws `FatalJobException` in runner | No | Cause classifier for `ExitCodeGenerator` exception | 43 |
| Other modes | Throws `CliUsageException` | No | Cause classifier for `ExitCodeGenerator` exception | 64 |

If `--demo.mode` is omitted, mode `success` is used. If the option is passed multiple times or without a value, treat it as a usage error; never pick one of the values arbitrarily.

### Note: Ready Does Not Mean the Job Succeeded

For `partial`, `invalid`, and `retry`, the runner **returns normally** because it executed and classified the business outcome; Boot may publish `ApplicationReadyEvent` before returning the context. Nevertheless, the exit-code generator bean still returns **12, 21, or 30**. This is not a contradiction:

- **Ready:** Boot's startup milestone completing along the normal path.
- **Process status:** the job's outcome per the CLI contract.

If a condition is a **startup failure itself**, such as mode `fatal`, the runner throws an exception and the Ready path does not occur.

### Why Have a Separate Exception Branch?

To practice both exit-code sources:

1. **Bean generator:** an `ApplicationContext` exists and the job outcome was stored in a bean. `SpringApplication.exit(context)` reads the bean and closes the context.
2. **Exception generator:** `SpringApplication.run(...)` throws before a successful context exists for the caller to pass to `exit`. Main's handler walks the cause chain and passes the classified error code to `System.exit`.

Spring Boot also has built-in handling for exceptions implementing `ExitCodeGenerator` on the startup failure path. The demo uses **explicit classification in main** so process-status tests remain independent of differences in launchers/uncaught-exception handlers; since no `ExitCodeExceptionMapper` bean is defined, this logic matches the demo's two-exception contract cleanly.

## 5. Architecture Design

~~~text
+----------------------------------------+
| CLI parent (shell / JUnit / scheduler)  |
|                                        |
|  java -jar app.jar --demo.mode=partial |
|                 |                      |
|                 v                      |
|          child Java process            |
|                 |                      |
|      SpringApplication.run             |
|                 |                      |
|          ApplicationRunner             |
|                 |                      |
|         JobOutcome bean (12)           |
|                 |                      |
|      SpringApplication.exit            |
|                 |                      |
|       Context.close + @PreDestroy      |
|                 |                      |
|           System.exit(12)              |
|                 |                      |
+-----------------+----------------------+
                  |
                  v
     parent Process.waitFor(timeout)
                  |
        +---------+----------+
        |                    |
       DONE                 TIMEOUT
        |                    |
 Process.exitValue()    destroy / destroyForcibly
        |                    |
 Compare 12 + log      fail test with diagnostics
~~~

**Advantage of child processes:** `System.exit` terminates only the child JVM. The JUnit/Gradle JVM stays alive to assert results, write reports, run remaining test cases, and clean up.

## 6. Complete Project Structure

~~~text
cli-process-exit-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/com/example/cli/
    │       └── CliExitApplication.java
    └── test/
        └── java/com/example/cli/
            └── CliExitProcessTests.java
~~~

The project requires **JDK 17+** and Gradle compatible with Spring Boot 3.3. If the machine lacks Gradle, generate a compatible Gradle Wrapper or use an installed Gradle. This example does **not** pre-generate wrapper files.

### 6.1. `settings.gradle`

~~~groovy
rootProject.name = 'cli-process-exit-demo'
~~~

### 6.2. `build.gradle`

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
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

springBoot {
    mainClass = 'com.example.cli.CliExitApplication'
}

def executableJar = tasks.named('bootJar')

tasks.named('test', Test) {
    useJUnitPlatform()

    // Do not run tests with a stale/unbuilt JAR.
    dependsOn executableJar

    // Retrieve the exact archiveFile from bootJar instead of hardcoding filename.
    doFirst {
        systemProperty(
            'demo.jar.path',
            executableJar.get().archiveFile.get().asFile.absolutePath
        )
    }
}
~~~

**Why does this `build.gradle` work well?**

- The `org.springframework.boot` plugin provides the `bootJar` task producing an executable JAR with the Boot launcher.
- The `java` toolchain requires Java 17, matching Spring Boot 3.3.
- The BOM dependency avoids repeating versions on individual starters.
- `spring-boot-starter` supplies core Boot without starting a web server.
- `spring-boot-starter-test` provides JUnit Jupiter and test utilities.
- `testRuntimeOnly 'org.junit.platform:junit-platform-launcher'` provides an explicit launcher for the Gradle test runtime.
- `tasks.named('test', Test)` enables JUnit Platform.
- `dependsOn executableJar` ensures `bootJar` is built **before tests run**.
- `doFirst` resolves the JAR path only after the corresponding task is configured/executed, passing it to the test JVM via system property `demo.jar.path`.
- Tests do not need to guess `build/libs/...jar`; if the version changes, the property still points to the exact `bootJar` output.

**Note:** `dependsOn` does not run tests inside the JAR. Tests still run inside the Gradle test JVM; inside the test, `ProcessBuilder` spawns **a separate Java JVM** and executes the JAR produced by `bootJar`.

## 7. Application: Business Outcome and Exit Codes

**Complete file `src/main/java/com/example/cli/CliExitApplication.java`:**

~~~java
package com.example.cli;

import java.util.List;

import jakarta.annotation.PreDestroy;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication(proxyBeanMethods = false)
public class CliExitApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(CliExitApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        int code;

        try {
            ConfigurableApplicationContext context = app.run(args);

            // Read ExitCodeGenerator beans, then close the context.
            code = SpringApplication.exit(context);
        }
        catch (RuntimeException startupFailure) {
            // run() did not return a successful context to main.
            // Walk the cause chain to find exceptions thrown inside runners.
            code = codeFromFailure(startupFailure);

            System.err.println(
                    "MAIN: startup failure code=" + code);
        }

        System.out.println("MAIN: exitCode=" + code);

        // Pass code to the OS. Call only at the CLI entrypoint.
        System.exit(code);
    }

    private static int codeFromFailure(Throwable failure) {
        for (Throwable current = failure;
                current != null;
                current = current.getCause()) {

            if (current instanceof ExitCodeGenerator generator) {
                int code = generator.getExitCode();

                if (code != 0) {
                    return code;
                }
            }
        }

        // Unclassified error type: report generic failure.
        return 1;
    }

    @Bean
    JobOutcome jobOutcome() {
        return new JobOutcome();
    }

    @Bean
    ExitCodeGenerator exitCodeGenerator(JobOutcome outcome) {
        return outcome::getExitCode;
    }

    @Bean
    ApplicationRunner demoRunner(JobOutcome outcome) {
        return args -> {
            List<String> values =
                    args.getOptionValues("demo.mode");

            String mode;

            if (values == null) {
                mode = "success";
            }
            else if (values.size() == 1) {
                mode = values.get(0);
            }
            else {
                System.out.println("JOB: INVALID_ARGUMENT_COUNT");
                throw new CliUsageException(
                        "demo.mode requires exactly one value");
            }

            switch (mode) {
                case "success" -> {
                    outcome.setExitCode(0);
                    System.out.println("JOB: SUCCESS");
                }
                case "partial" -> {
                    outcome.setExitCode(12);
                    System.out.println("JOB: PARTIAL_RESULT");
                }
                case "invalid" -> {
                    outcome.setExitCode(21);
                    System.out.println("JOB: INVALID_INPUT");
                }
                case "retry" -> {
                    outcome.setExitCode(30);
                    System.out.println("JOB: TEMPORARY_UNAVAILABLE");
                }
                case "fatal" -> {
                    System.out.println("JOB: FATAL_STARTUP");
                    throw new FatalJobException(
                            "Mandatory startup step failed");
                }
                default -> {
                    System.out.println("JOB: UNKNOWN_MODE");
                    throw new CliUsageException(
                            "Unsupported demo.mode");
                }
            }
        };
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("EVENT: READY");
    }

    public static final class JobOutcome {

        // If the runner fails to complete yet other code still calls exit,
        // default to generic failure instead of falsely reporting success.
        private volatile int exitCode = 1;

        public void setExitCode(int exitCode) {
            this.exitCode = exitCode;
        }

        public int getExitCode() {
            return exitCode;
        }

        @PreDestroy
        public void onDestroy() {
            System.out.println("LIFECYCLE: closed");
        }
    }

    public static final class FatalJobException
            extends IllegalStateException implements ExitCodeGenerator {

        public FatalJobException(String message) {
            super(message);
        }

        @Override
        public int getExitCode() {
            return 43;
        }
    }

    public static final class CliUsageException
            extends IllegalArgumentException
            implements ExitCodeGenerator {

        public CliUsageException(String message) {
            super(message);
        }

        @Override
        public int getExitCode() {
            return 64;
        }
    }
}
~~~

### 7.1. Why Use the `JobOutcome` Bean?

`JobOutcome` is a **per-context** bean, not a JVM-wide static field. The runner updates `exitCode` based on execution outcome. The `ExitCodeGenerator` bean is a method reference:

~~~java
@Bean
ExitCodeGenerator exitCodeGenerator(JobOutcome outcome) {
    return outcome::getExitCode;
}
~~~

`SpringApplication.exit` retrieves the code while the context can still query beans, then closes it. Using `volatile int` in `JobOutcome` is safe for cross-thread visibility if extended later; in the demo, runner and main run sequentially so no complex concurrency mechanism is needed.

**Do not write `return () -> 0` for all modes**: that hides business outcomes and makes the shell always think the job succeeded.

### 7.2. Using `ApplicationArguments` Instead of Manually Splitting Strings

`ApplicationRunner` receives `ApplicationArguments`. `getOptionValues("demo.mode")`:

- Returns `null` when the option is absent.
- Returns a list of values when present.
- May return an empty list for `--demo.mode` without a value.
- May have multiple elements when the option appears repeatedly.

The demo accepts strictly **one** value if the option is supplied; this prevents `--demo.mode=success --demo.mode=partial` from being interpreted arbitrarily.

If `--demo.mode` lacks a value, the code throws `CliUsageException`. Unsupported modes also throw this type in the default branch.

**Do not ignore extra arguments** if product contracts require strict parsing; the demo only checks the `demo.mode` option, while Boot's parser may retain other options without runner rejection. For a strict CLI, add a validator covering all `getOptionNames()` per your policy.

### 7.3. Why Does `SpringApplication.exit(context)` Follow `run`?

On the normal business path:

~~~text
runner sets JobOutcome.exitCode
   |
ApplicationReadyEvent
   |
SpringApplication.run returns context
   |
SpringApplication.exit(context)
   |
ExitCodeGenerator bean returns code
   |
context.close() → @PreDestroy
   |
main prints code
   |
System.exit(code)
~~~

`@PreDestroy` on `JobOutcome` prints `LIFECYCLE: closed`. It proves a managed bean receives its destroy callback when the context closes. With real database connections/files/executors, logging alone is insufficient; verify resources are released per contract.

### 7.4. Why Does `main` Also Catch `RuntimeException`?

If the runner throws `FatalJobException`, `SpringApplication.run(...)` takes the startup failure branch and throws the exception outward before returning a context. Spring Boot often wraps runner exceptions in an `IllegalStateException` with message "Failed to execute ApplicationRunner", so checking only the outermost exception with `instanceof FatalJobException` could miss it.

`codeFromFailure(...)` walks `getCause()` until it finds an exception implementing `ExitCodeGenerator` and retrieves its code. If no classified code exists, it returns 1. Main then calls `System.exit(code)` so the demo's process status is **explicit and testable**, independent of whether an uncaught exception is mapped to a specific code by a launcher.

**Limitation:** This is a narrow classifier for the teaching project. If an application has `ExitCodeExceptionMapper` beans and wants to use Boot's failure mapping policy on startup failure, do not write a separate classifier that accidentally overrides mappers. Boot already has a mechanism for resolving exception codes on its failure path; in production, pick one consistent classification path and test against your exact Boot version.

### 7.5. Why Not Catch Exceptions and Always Return 0?

An anti-pattern:

~~~java
try {
    runJob();
}
catch (Exception error) {
    System.err.println(error);
}
System.exit(0);
~~~

This is a **broken snippet**, not code to add to the project. It reports success even when the job failed to complete. If catching to classify, return an appropriate non-zero code, preserve cause/logs, and never swallow critical infrastructure errors.

### 7.6. Why Not Call `System.exit` Directly Inside the Runner?

If a runner calls `System.exit(43)` itself the moment it detects an error, Spring may bypass the error reporting/cleanup expected from `SpringApplication.run`. For jobs with open resources or uncommitted transactions, abrupt termination is also dangerous.

Let runners **return a business result** or **throw a domain exception**, leaving status management and closing to the entrypoint/lifecycle. Never put process termination logic in the business layer.

## 8. `ProcessBuilder` Tests: Launching a Real JVM

We want JUnit to verify:

1. Spawn a **child JVM** using the Java executable from the test runtime's `java.home`.
2. Run the exact JAR built by `bootJar`.
3. Pass each option as a **separate argument**, without manually assembling a shell command string.
4. Merge stderr with stdout and write to a **temporary file**.
5. Wait for the process to exit for **at most 60 seconds**.
6. On timeout, send a stop signal; if still alive, force-kill, then fail the test.
7. After the process ends, read `exitValue()` and log file contents.
8. Delete the temporary file in `finally`.
9. Never call `System.exit(...)` inside the JUnit JVM.

**Why write to a temporary file instead of reading output after `waitFor`?** If the child writes heavily to stdout/stderr pipes, the pipe buffer can fill up; the child blocks waiting for the parent to read, while the parent blocks waiting for the child to exit. Using `redirectOutput(file)` and `redirectErrorStream(true)` lets the OS write logs to disk, avoiding pipe deadlock.

## 9. Complete JUnit 5 Code for Child Processes

**File `src/test/java/com/example/cli/CliExitProcessTests.java`:**

~~~java
package com.example.cli;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

class CliExitProcessTests {

    private record ChildResult(int code, String output) {
    }

    @Test
    void successReturnsZeroAndClosesContext() throws Exception {
        ChildResult child = runChild("success");

        assertEquals(0, child.code(), child.output());
        assertTrue(child.output().contains("JOB: SUCCESS"));
        assertTrue(child.output().contains("EVENT: READY"));
        assertTrue(child.output().contains("LIFECYCLE: closed"));
        assertTrue(child.output().contains("MAIN: exitCode=0"));

        // Markers printed by demo code itself, following Boot lifecycle order.
        assertBefore(child.output(), "JOB: SUCCESS", "EVENT: READY");
        assertBefore(
                child.output(), "EVENT: READY", "LIFECYCLE: closed");
        assertBefore(
                child.output(), "LIFECYCLE: closed", "MAIN: exitCode=0");
    }

    @Test
    void partialResultReturnsTwelve() throws Exception {
        ChildResult child = runChild("partial");

        assertEquals(12, child.code(), child.output());
        assertTrue(child.output().contains("JOB: PARTIAL_RESULT"));
        assertTrue(child.output().contains("EVENT: READY"));
        assertTrue(child.output().contains("MAIN: exitCode=12"));
    }

    @Test
    void invalidInputReturnsTwentyOne() throws Exception {
        ChildResult child = runChild("invalid");

        assertEquals(21, child.code(), child.output());
        assertTrue(child.output().contains("JOB: INVALID_INPUT"));
        assertTrue(child.output().contains("EVENT: READY"));
        assertTrue(child.output().contains("MAIN: exitCode=21"));
    }

    @Test
    void retryableResultReturnsThirty() throws Exception {
        ChildResult child = runChild("retry");

        assertEquals(30, child.code(), child.output());
        assertTrue(child.output().contains(
                "JOB: TEMPORARY_UNAVAILABLE"));
        assertTrue(child.output().contains("EVENT: READY"));
        assertTrue(child.output().contains("MAIN: exitCode=30"));
    }

    @Test
    void fatalRunnerFailureReturnsFortyThree() throws Exception {
        ChildResult child = runChild("fatal");

        assertEquals(43, child.code(), child.output());
        assertTrue(child.output().contains("JOB: FATAL_STARTUP"));
        assertFalse(child.output().contains("EVENT: READY"));
        assertTrue(child.output().contains("LIFECYCLE: closed"));
        assertTrue(child.output().contains(
                "MAIN: startup failure code=43"));
        assertTrue(child.output().contains("MAIN: exitCode=43"));
    }

    @Test
    void unsupportedModeReturnsUsageError() throws Exception {
        ChildResult child = runChild("unknown-value");

        assertEquals(64, child.code(), child.output());
        assertTrue(child.output().contains("JOB: UNKNOWN_MODE"));
        assertFalse(child.output().contains("EVENT: READY"));
        assertTrue(child.output().contains("MAIN: exitCode=64"));
    }

    private static ChildResult runChild(String mode) throws Exception {
        String pathProperty = Objects.requireNonNull(
                System.getProperty("demo.jar.path"),
                "Missing demo.jar.path: run tests using Gradle test task");

        Path jar = Path.of(pathProperty).toAbsolutePath();
        assertTrue(Files.isRegularFile(jar), "Missing JAR: " + jar);

        String executable = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT)
                .contains("win") ? "java.exe" : "java";

        Path java = Path.of(
                System.getProperty("java.home"),
                "bin",
                executable);

        assertTrue(
                Files.isRegularFile(java),
                "Missing Java executable: " + java);

        Path logFile = Files.createTempFile(
                "cli-process-test-", ".log");

        Process process = null;

        try {
            ProcessBuilder builder = new ProcessBuilder(
                    java.toString(),
                    "-Dfile.encoding=UTF-8",
                    "-jar",
                    jar.toString(),
                    "--demo.mode=" + mode);

            // Prevent stdout/stderr pipes from filling while parent awaits exit.
            builder.redirectErrorStream(true);
            builder.redirectOutput(logFile.toFile());

            process = builder.start();

            boolean finished =
                    process.waitFor(60, TimeUnit.SECONDS);

            if (!finished) {
                // Timeout must fail the test rather than hanging CI.
                process.destroy();

                if (!process.waitFor(3, TimeUnit.SECONDS)) {
                    process.destroyForcibly();
                    process.waitFor(5, TimeUnit.SECONDS);
                }

                fail("Child JVM exceeded timeout. Output:\n"
                        + Files.readString(
                                logFile, StandardCharsets.UTF_8));
            }

            int code = process.exitValue();
            String output = Files.readString(
                    logFile, StandardCharsets.UTF_8);

            return new ChildResult(code, output);
        }
        finally {
            if (process != null && process.isAlive()) {
                process.destroyForcibly();
                process.waitFor(5, TimeUnit.SECONDS);
            }

            Files.deleteIfExists(logFile);
        }
    }

    private static void assertBefore(
            String output, String earlier, String later) {

        int first = output.indexOf(earlier);
        int second = output.indexOf(later);

        assertTrue(first >= 0, "Missing marker: " + earlier);
        assertTrue(second >= 0, "Missing marker: " + later);
        assertTrue(first < second, "Wrong order:\n" + output);
    }
}
~~~

### 9.1. What Does Each Assertion Prove?

**`successReturnsZeroAndClosesContext`**

- Child JVM returns exactly 0.
- Runner executed business logic successfully.
- `ApplicationReadyEvent` fired.
- Bean received `@PreDestroy` while `SpringApplication.exit(context)` closed the context.
- Main printed the exit code only after the resource-closing event ran.
- **Does not** substitute a logged status for `Process.exitValue()`; the test checks both.

**`partialResultReturnsTwelve` and `invalidInputReturnsTwentyOne`**

- Runner **returned normally**; Boot reached ready per lifecycle.
- Generator bean returned a non-zero code based on the business result.
- External orchestrators can distinguish "ran yet business result incomplete" from "process crash".

**`retryableResultReturnsThirty`**

- The demo only classifies "temporary unavailable"; it **does not retry itself**. The test confirms schedulers can receive code 30 to decide on backed-off retries.
- Do not automatically retry jobs with side effects without an idempotency/recovery policy.

**`fatalRunnerFailureReturnsFortyThree`**

- Runner threw an exception carrying code 43.
- Boot did not publish ready on the success path.
- Main caught the exception thrown by `run` and walked the cause chain to obtain 43.
- The child actually exited with 43, not just a string in logs.
- Context had already refreshed before the runner; Spring Boot 3.3 handles failure by attempting to close the context, so `@PreDestroy` on initialized beans can run. This test specifically checks runner failure **after refresh**, not every ultra-early bootstrap failure.

**`unsupportedModeReturnsUsageError`**

- Unrecognized modes are explicitly classified as `USAGE_ERROR` 64.
- Never silently runs `success` when user input is invalid.

### 9.2. Why Use `record ChildResult`?

Java 17 supports `record`:

~~~java
private record ChildResult(int code, String output) {
}
~~~

It groups a process exit code and output together without a manual class with constructors/getters. Tests read `child.code()` and `child.output()`; both belong to **the same run**, avoiding accidentally pairing process A's log with process B's exit code.

### 9.3. Why Use `java.home`?

The Java path in the test:

~~~java
Path java = Path.of(
        System.getProperty("java.home"),
        "bin",
        executable);
~~~

invokes the exact JDK/JRE executable running the test JVM. On Windows it is `java.exe`; on Unix-like systems it is `java`. It avoids assuming `java` is on `PATH` or that the shell is configured identically to CI.

Paths containing spaces are passed as **a single argument in `ProcessBuilder`**, without wrapping quotes around the path as you would when building a shell command string.

### 9.4. Why Pass Each Argument Separately?

Correct:

~~~java
new ProcessBuilder(
        java.toString(),
        "-jar",
        jar.toString(),
        "--demo.mode=partial");
~~~

Common mistake:

~~~java
new ProcessBuilder(
        "java -jar " + jar + " --demo.mode=partial");
~~~

`ProcessBuilder` does not invoke Bash/PowerShell by default to parse a command string. Passing one combined string makes the OS look for an executable named after the entire string, causing an `IOException`.

**Do not wrap the JAR path in literal quotes** inside a `ProcessBuilder` argument: the framework already passes structured arguments individually; adding `"` into the path value can turn quotes into unwanted literal filename characters.

### 9.5. Why `redirectErrorStream(true)`?

The child process can write:

- `System.out.println(...)` to stdout.
- `System.err.println(...)` or Spring Boot failure logs to stderr.

If you read only stdout and ignore stderr, the stderr buffer can fill and block the child. By using:

~~~java
builder.redirectErrorStream(true);
builder.redirectOutput(logFile.toFile());
~~~

all logs go to one file. The test does not need two reader threads draining two pipes concurrently, and no error output is lost.

**Trade-off:** You no longer know which line came from stdout vs. stderr; merging can make cross-stream log ordering non-deterministic. Therefore tests assert **markers/ordering within lines produced by the same application code**, rather than matching entire framework stack traces verbatim.

### 9.6. Why Must There Be a Timeout?

Parameterless `Process.waitFor()` can wait **forever** when:

- A runner gets stuck in `while(true)`.
- A non-daemon thread keeps the JVM from exiting.
- A network call has no timeout.
- A shutdown hook waits on an unfinished task.
- The process accidentally starts an HTTP server and stays alive.

`process.waitFor(60, TimeUnit.SECONDS)` returns a boolean; if false, the child has not exited by the deadline. The test must send `destroy()`, fall back to `destroyForcibly()`, and **report FAIL** so CI does not hang.

`destroyForcibly()` **does not guarantee the process vanishes immediately on that line**; the test also waits briefly afterward. The 60-second timeout here is an **illustrative budget** for a lightweight Spring Boot CLI and can be tuned for CI hardware and cold-start times.

### 9.7. Why Is the Log File Deleted in `finally`?

Even if assertions or process startup throw an exception, the test must delete the temporary file. Using `Files.createTempFile(...)` gives each test its own path, reducing collisions when tests run in parallel.

In production CI, it is sometimes helpful to retain failed test logs as artifacts. You can copy the log to a report directory before deletion, subject to retention policies, sensitive-data scrubbing, and disk limits. Since the demo uses short output, `Files.readString(...)` is appropriate.

## 10. Running the Test Suite

From the `cli-process-exit-demo` directory:

~~~bash
gradle test
~~~

If a Gradle Wrapper was generated:

~~~bash
./gradlew test
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Because `test dependsOn bootJar`, Gradle automatically builds the executable JAR before JUnit spawns child processes.

**Six expected tests:**

~~~text
successReturnsZeroAndClosesContext                 PASS
partialResultReturnsTwelve                         PASS
invalidInputReturnsTwentyOne                       PASS
retryableResultReturnsThirty                       PASS
fatalRunnerFailureReturnsFortyThree                PASS
unsupportedModeReturnsUsageError                   PASS
~~~

This is an **expected JUnit result list**, not a guarantee Gradle prints this exact format verbatim on the console: test reporting UI depends on Gradle version and `testLogging` settings.

### Conditions That Must Hold

- `:bootJar` runs before `:test` per task dependencies.
- JUnit sees `demo.jar.path` and the file exists.
- The Java executable exists under `java.home/bin`.
- Each child process exits on its own within 60 seconds in normal scenarios.
- Exit codes match expected values.
- Stdout/stderr markers are written to the temp file and read back completely.
- After each test, the temp file is deleted and no process remains running.

**No web server or TCP port is needed.** The application's `WebApplicationType.NONE` lives inside the JAR executed by the child JVM.

## 11. Running the JAR Manually and Reading Exit Codes

Build the JAR first:

~~~bash
gradle bootJar
~~~

With `rootProject.name` and `version` in the example, the default output file is:

~~~text
build/libs/cli-process-exit-demo-1.0.0.jar
~~~

If you change project name/version, take the actual path from `build/libs` or `bootJar.archiveFile`; do not blindly keep the sample path.

### 11.1. Bash/Zsh — `success`

~~~bash
java -jar build/libs/cli-process-exit-demo-1.0.0.jar \
  --demo.mode=success
echo $?
~~~

**Lines printed by the demo code**, excluding Spring Boot framework logs:

~~~text
JOB: SUCCESS
EVENT: READY
LIFECYCLE: closed
MAIN: exitCode=0
~~~

Expected shell exit status: **`0`**.

### 11.2. Bash/Zsh — `partial`

~~~bash
java -jar build/libs/cli-process-exit-demo-1.0.0.jar \
  --demo.mode=partial
echo $?
~~~

Lines printed by the demo:

~~~text
JOB: PARTIAL_RESULT
EVENT: READY
LIFECYCLE: closed
MAIN: exitCode=12
~~~

Expected shell exit status: **`12`**.

### 11.3. Bash/Zsh — `invalid`

~~~bash
java -jar build/libs/cli-process-exit-demo-1.0.0.jar \
  --demo.mode=invalid
echo $?
~~~

Lines printed by the demo:

~~~text
JOB: INVALID_INPUT
EVENT: READY
LIFECYCLE: closed
MAIN: exitCode=21
~~~

Expected shell exit status: **`21`**.

### 11.4. Bash/Zsh — `retryable`

~~~bash
java -jar build/libs/cli-process-exit-demo-1.0.0.jar \
  --demo.mode=retry
echo $?
~~~

Lines printed by the demo:

~~~text
JOB: TEMPORARY_UNAVAILABLE
EVENT: READY
LIFECYCLE: closed
MAIN: exitCode=30
~~~

Expected shell exit status: **`30`**.

### 11.5. Bash/Zsh — `fatal startup`

~~~bash
java -jar build/libs/cli-process-exit-demo-1.0.0.jar \
  --demo.mode=fatal
echo $?
~~~

**Markers printed by the demo**, excluding Spring's stack trace/error report:

~~~text
JOB: FATAL_STARTUP
LIFECYCLE: closed
MAIN: startup failure code=43
MAIN: exitCode=43
~~~

Expected shell exit status: **`43`**. The line `MAIN: startup failure code=43` prints to stderr, so **interleaving order** with Boot logs/output may vary across launchers; tests check marker presence rather than asserting the entire log character-for-character.

**No `EVENT: READY`** because the runner threw an exception.

### 11.6. Bash/Zsh — `unknown mode`

~~~bash
java -jar build/libs/cli-process-exit-demo-1.0.0.jar \
  --demo.mode=no-such-mode
echo $?
~~~

Markers from demo:

~~~text
JOB: UNKNOWN_MODE
LIFECYCLE: closed
MAIN: startup failure code=64
MAIN: exitCode=64
~~~

Expected shell exit status: **`64`**.

### 11.7. Omitting the Option

~~~bash
java -jar build/libs/cli-process-exit-demo-1.0.0.jar
echo $?
~~~

The runner picks default `success`. Expected exit code is 0.

### 11.8. Windows PowerShell

~~~powershell
java -jar .\build\libs\cli-process-exit-demo-1.0.0.jar --demo.mode=partial
$LASTEXITCODE
~~~

`$LASTEXITCODE` reflects the exit code of the Java executable just run. In Bash/Zsh, read `$?` **immediately after the Java command**.

**Watch out:** Running another command before reading `$?` overwrites it with that command's exit status. If piping through `tee`, understand your shell's `pipefail`/`PIPESTATUS`; otherwise you may read `tee`'s status instead of Java's.

## 12. Why Not Use `gradle bootRun` as the Source of Exit Codes?

`gradle bootRun` is a Gradle task running the Java application. When the child Java process exits non-zero, Gradle typically reports a task/build failure with the **Gradle process's** exit code. That code **does not necessarily equal** business codes `12`, `21`, or `43`.

Example:

~~~bash
gradle bootRun --args="--demo.mode=partial"
echo $?
~~~

Gradle may return a generic build failure code instead of 12. Therefore:

- Use `gradle bootRun` to try functionality and read application logs.
- Use `java -jar ...` to measure the **application JVM's** exit code.
- Use `ProcessBuilder` in tests to measure `Process.exitValue()` of the exact JAR.
- Never treat a log line `"MAIN: exitCode=12"` as final proof that the OS received 12.

A test that checks only `stdout` and omits `exitValue()` will miss a bug where the code forgot `System.exit(code)`.

## 13. Exception Implementing `ExitCodeGenerator` vs. Bean Generator

The project demonstrates both:

### Bean Generator When `run` Succeeds

~~~java
@Bean
ExitCodeGenerator exitCodeGenerator(JobOutcome outcome) {
    return outcome::getExitCode;
}
~~~

`SpringApplication.exit(context)` collects `ExitCodeGenerator` beans, picks the non-zero code per contract, and closes the context. For `success`, the result is 0.

### Exception Generator When Startup Fails

~~~java
public static final class FatalJobException
        extends IllegalStateException implements ExitCodeGenerator {

    public FatalJobException(String message) {
        super(message);
    }

    @Override
    public int getExitCode() {
        return 43;
    }
}
~~~

On the startup failure path, Spring Boot 3.3 can search the cause chain for exceptions implementing `ExitCodeGenerator` to derive the exit code. The demo's `main` still includes an explicit classifier so tests consistently pass the exact code to `System.exit` after `run` throws.

### `ExitCodeExceptionMapper` Is a Third Option

When you do not control the exception class, Spring Boot also offers `ExitCodeExceptionMapper`:

~~~java
@Bean
ExitCodeExceptionMapper exitCodeExceptionMapper() {
    return error -> {
        for (Throwable t = error; t != null; t = t.getCause()) {
            if (t instanceof IllegalArgumentException) {
                return 64;
            }
        }
        return 0;
    };
}
~~~

**This is an extension snippet, not part of the runnable project.** It requires importing `org.springframework.boot.ExitCodeExceptionMapper` and placing it in a configuration class. Mappers operate on the **startup failure path when the ApplicationContext is active**. In Spring Boot 3.3.13, a non-zero mapped code takes precedence over falling back to exceptions implementing `ExitCodeGenerator`.

**Do not paste the snippet into the project while keeping the old `main` classifier and expect both policies to stay in sync automatically**: the demo's `codeFromFailure` does not read mapper beans from a failed-startup context. When upgrading for production, choose one unified policy and write process-level tests for the real behavior.

### Do Not Use Mappers for Arbitrary HTTP Requests

`ExitCodeExceptionMapper` in SpringApplication startup failure does not automatically apply to Spring MVC, Kafka listener, or `@Async` exceptions after the app is ready. Those belong to runtime error-handling mechanisms. One-shot CLI jobs are where process exit codes fit best.

## 14. Child-Process Testing Is Black-Box Testing

A process-level integration test observes **inputs and outputs**:

~~~text
Input: executable JAR + CLI arguments + environment
Output: process exit code + stdout/stderr + side effects (if any)
~~~

This mirrors how a real scheduler interacts with the CLI. Such tests catch bugs invisible to unit tests:

- Forgetting to call `System.exit(code)`.
- Computing the right code without closing the context.
- `main` failing to forward arguments to `SpringApplication.run(args)`.
- Boot JAR missing the right Main-Class/Start-Class.
- Missing packaged dependency causing JAR execution failure.
- Application inadvertently starting a server so the JVM never exits.
- A thread pool failing to stop, timing out the process test.
- Wrapped exception where main's classifier fails to walk causes.
- Broken shell quoting on paths containing spaces.
- Build tool returning a different code from the app JVM.

**Limitation:** The demo has no real database/broker, so it does not prove transactional correctness, idempotency, multi-process coordination, or network-failure recovery. Test those dependencies separately.

## 15. Unit Tests Remain Essential at the Business Layer

You should not spin up a new JVM for every tiny case. With 10,000 validation cases, booting the JAR each time would be painfully slow.

A typical production pyramid:

~~~text
JobService
   |
   +-- unit tests: input, output, validation, branch coverage
   |
   +-- Spring integration tests: wiring, runners, lifecycle
   |
   +-- process tests: representative exit codes, packaging, shutdown
   |
   +-- system tests: real DB/broker/file storage when needed
~~~

In this lab, the six child-process tests focus on **the external contract**. Business result calculation is intentionally simple so no mock database is needed.

### Why Not Call `main()` Directly in JUnit?

A test such as:

~~~java
@Test
void badTest() {
    CliExitApplication.main(
            new String[] { "--demo.mode=partial" });
}
~~~

is an **anti-pattern** for this project: `main` calls `System.exit(12)`, which can terminate the JUnit/Gradle test worker JVM itself. Wrapping `main` in `assertThrows` does not turn `System.exit` into a normal exception either.

**Solution:** Keep process termination at the application entrypoint and invoke that entrypoint **from a child JVM**. Inside the test JVM, interact only with `Process`.

## 16. Common Pitfalls with `ProcessBuilder`

### Mistake 1 — Combining the Entire Command into One String

Wrong:

~~~java
new ProcessBuilder(
        "java -jar app.jar --demo.mode=partial");
~~~

`ProcessBuilder` is not a shell command parser. Separate the executable and each argument.

### Mistake 2 — Hardcoding `java` from `PATH`

If CI has multiple JDKs, `java` on `PATH` may differ from the JDK Gradle uses. Resolving from `java.home/bin` keeps the test environment consistent.

### Mistake 3 — Reading Only Stdout Without Draining Stderr

The child can block if the stderr pipe fills up. Use `redirectErrorStream` + `redirectOutput` to a file, or spawn two reader tasks genuinely draining both streams concurrently.

### Mistake 4 — Reading All Output Before `waitFor` with Blocking Reads

`readAllBytes()` on a pipe can block waiting for EOF indefinitely if the child never exits; read only after process exit with a deadline, or read asynchronously. In this project, file redirection keeps waiting straightforward.

### Mistake 5 — Calling `waitFor()` Without a Timeout

A regression creating a non-terminating thread can hang CI forever. Use `waitFor(timeout, unit)`, destroy on timeout, and fail explicitly.

### Mistake 6 — Timing Out Without Killing the Process

The test finishes while the child JVM lingers in the background consuming CPU/files/ports. In `finally`, check `isAlive()` and force-kill when needed.

### Mistake 7 — Killing the Child and Treating the Test as Passed

A timeout must **FAIL the test**, even if destroy succeeds. Killing is cleanup, not proof the job completed.

### Mistake 8 — Calling `Process.exitValue()` Before the Process Ends

`exitValue()` throws `IllegalThreadStateException` if the child is still running. Call it only after `waitFor(...)` returns `true` or you know the process has exited.

### Mistake 9 — Setting the Wrong Charset

If output contains Vietnamese or Unicode characters, ensure the child JVM, file, and reader use compatible encodings. The project prints ASCII markers for cross-OS stability while also passing `-Dfile.encoding=UTF-8` in the child command.

### Mistake 10 — Reading the Log After Deleting the File

Read output **before** `Files.deleteIfExists(...)`. `finally` in the helper only deletes after `ChildResult` already holds the String output or when the test errors out.

### Mistake 11 — Neglecting Environment Variables

`ProcessBuilder` normally inherits the parent's environment. A CI environment property/secret could alter child behavior. In real apps, define explicit test profiles and environment overrides; never wipe the entire environment accidentally (losing PATH, HOME, TMP).

### Mistake 12 — Checking Right Stdout While Missing Wrong Exit Code

An app printing "SUCCESS" and calling `System.exit(21)` is still a failure under the process contract. Tests must assert **both**.

### Mistake 13 — Checking Right Exit Code Without Knowing the Cause

`exitCode=21` is insufficient diagnostics if the app crashed before running the job and accidentally used code 21. Add markers and logging/error categories to distinguish them.

### Mistake 14 — Asserting Exact Line-by-Line Boot Logs

Spring Boot/Gradle loggers vary by version, log level, and stdout/stderr merging. Assert only contract markers from the demo and lifecycle-guaranteed before–after relationships.

### Mistake 15 — Testing a Stale JAR

If the JAR is not rebuilt after code edits, tests may pass against an outdated artifact. `test dependsOn bootJar` and reading `archiveFile` prevent this basic mistake.

## 17. Exit Codes on Unix, Windows, and Shell Pipelines

### Unix-Like Shells

In standard POSIX environments, shell-visible exit statuses sit in the 0–255 range; very large or negative values can wrap to the low 8 bits, making statuses unpredictable.

That is why the sample uses **small positive** codes like 12, 21, 30, 43, and 64. Never use `Integer.MAX_VALUE` as a portable error code.

Some shells reserve common statuses:

- `126`: command cannot be executed.
- `127`: command not found.
- `128 + signal`: termination by signal in many shells.

Avoid assigning those special values as business codes if schedulers need to tell them apart.

### PowerShell

Use `$LASTEXITCODE` after a Java executable. Do not assume PowerShell's `$?` is an integer like in Bash; `$?` in PowerShell is a boolean success/failure status of the last command.

### Pipelines with `tee`

If running:

~~~bash
java -jar app.jar --demo.mode=partial | tee output.log
echo $?
~~~

in a shell without `pipefail`, `$?` is usually **`tee`'s** status, not Java's. To capture Java's code, use Bash `PIPESTATUS` or enable `set -o pipefail` depending on the shell, understanding its impact on other commands in the script.

**`ProcessBuilder` in this project uses no shell pipeline**, so `Process.exitValue()` reads the Java child process's status directly.

## 18. Integrating with CI/CD and Job Schedulers

Suppose a pipeline runs the CLI:

~~~text
Checkout source
   |
Build executable Boot JAR
   |
Run CLI job
   |
Capture process exit code
   |
   +-- 0: success
   +-- 12: partial; inspect report
   +-- 21/64: input/usage error; no blind retry
   +-- 30: temporary; bounded retry
   +-- 43/1: startup or unknown failure; investigate
~~~

A pipeline can use exit codes to:

- Halt a stage when configuration is invalid.
- Mark an ingestion job successful.
- Separate data errors from infrastructure errors.
- Retry with backoff when dependencies are temporarily unavailable.
- Raise alerts with correlation IDs and links to logs/artifacts.
- Prevent downstream steps from running when upstream outcomes violate the contract.

### Do Not Retry Infinitely Just Because the Code Is Non-Zero

Code `21` for bad data will not fix itself across retries. Code `30` can be retried, yet requires:

- Maximum attempt count and deadline.
- Backoff/jitter.
- Timeouts on every network operation.
- Idempotency keys or checkpoints if the job produces side effects.
- Telemetry for retry counts and final outcomes.

A scheduler must never blindly retry **every non-zero code** with the same strategy.

### Illustrative Bash Branching Script

~~~bash
#!/usr/bin/env bash

java -jar build/libs/cli-process-exit-demo-1.0.0.jar \
  --demo.mode=partial

code=$?

case "$code" in
  0)
    echo "Job completed"
    ;;
  12)
    echo "Partial result: inspect report"
    ;;
  21|64)
    echo "Fix input or CLI invocation"
    ;;
  30)
    echo "Retryable: schedule bounded retry"
    ;;
  *)
    echo "Unexpected failure: $code"
    ;;
esac

exit "$code"
~~~

**This is an illustrative Bash script**, not Gradle/JUnit source. If the shell runs with `set -e`, a non-zero Java command can abort the script **before reaching `case`**; temporarily guard errexit or use an `if java ...; then ... else ... fi` structure. To preserve the failure code for a parent scheduler, return `exit "$code"` at the end of the script.

## 19. Kubernetes Jobs and Containers

In a CLI container, the entrypoint should propagate exit signals accurately:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY build/libs/cli-process-exit-demo-1.0.0.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
CMD ["--demo.mode=success"]
~~~

This is an **illustrative Dockerfile** runnable once the JAR is built and the base image is available, not a prerequisite to run tests. Using exec-form `ENTRYPOINT` ensures Java receives signals and reports exit status directly, avoiding a shell wrapper accidentally returning 0 when Java returns non-zero.

A Kubernetes `Job` can:

- Mark the Pod/container failed when the process returns non-zero.
- Restart/recreate pods depending on `restartPolicy` and `backoffLimit`.
- Consider the Job successful only when its completions policy is met.

**Do not misunderstand:** Kubernetes does not inherently know `21` means bad data or `30` means transient unless you define policy via an appropriate controller/operator/script. A default Kubernetes Job mainly observes success vs. failure, rather than executing the app's full business retry matrix.

With side effects, if a Job re-runs after node failure/SIGKILL, idempotency and durable progress are required; calling `SpringApplication.exit` on the normal path cannot guarantee callbacks run if the host dies.

## 20. Extending the Application: Real Business Execution

The demo uses a switch just to assign codes. A real ingestion app typically separates:

~~~text
CliExitApplication
   |
   +-- ApplicationRunner
          |
          +-- JobService.execute(input)
                   |
                   +-- JobResult(status, accepted, rejected, ...)
          |
          +-- map JobResult -> exit code
          |
          +-- JobOutcome bean
   |
   +-- SpringApplication.exit(context)
   |
   +-- System.exit(code)
~~~

Java 17 domain object example:

~~~java
public record ImportResult(
        int acceptedCount,
        int rejectedCount,
        boolean dependencyUnavailable) {

    public int exitCode() {
        if (dependencyUnavailable) {
            return 30;
        }
        if (rejectedCount > 0) {
            return 12;
        }
        return 0;
    }
}
~~~

This is a **standalone illustrative Java record class** that can live in `ImportResult.java`, though it is not directly referenced in section 7's complete project without creating that file.

If an exception occurs in `JobService`:

- Exceptions **preventing startup from continuing** can propagate out of the runner; Boot will take the failure path.
- A **business outcome** handled completely can be mapped to an exit code in `JobOutcome` without throwing.
- Do not lump "partial result accepted" and "startup failed" into one case if schedulers need to distinguish them.

### Idempotency When the Scheduler Retries

Suppose a job wrote 8,000 rows to the DB and the process was killed before updating progress. A retry could write duplicates. You therefore need:

- Stable job ID / correlation ID.
- Unique constraints or idempotency keys.
- Transactions/outbox/checkpoints per business operation.
- Retry budgets and appropriate dead-letter/reporting.
- Never rely solely on local in-memory flags.

A process exit code only **reports the result**; it does not create exactly-once execution on its own.

## 21. Extending `ProcessBuilder` Tests with Input and Environment

The base project passes one CLI option. When a job needs a file path or environment variable, keep passing them through the argument list:

~~~java
ProcessBuilder builder = new ProcessBuilder(
        java.toString(),
        "-jar",
        jar.toString(),
        "--demo.mode=success",
        "--job.input=" + inputFile.toAbsolutePath());
~~~

This is an **illustrative snippet**, assuming `java`, `jar`, and `Path inputFile` already exist. Do not manually quote paths containing spaces.

Per-child environment override:

~~~java
builder.environment().put(
        "APP_TEST_MODE", "true");
~~~

Only override keys the test needs, avoiding clearing the entire environment. If CI uses secrets, never print the whole environment or dump it into test logs.

### Testing Missing or Unreadable Files

A process-level test can create a temp file in the parent, pass its absolute path to the child, have the child parse it, and return code 21 on invalid input. The parent must clean up the temp file and test report afterward. This increases realism over a switch statement, while increasing I/O cost and requiring file-lock care on Windows.

### Testing Stderr Independently

If you must distinguish stderr from stdout, **do not** use `redirectErrorStream(true)`. Instead redirect to **two separate files** or run two concurrent reader tasks. Never read two streams sequentially expecting EOF when the child might fill the other stream first.

### Testing Large Output

A job might write gigabytes of logs. In such tests, do not load the entire log file into a String after exit. Cap log sizes, stream-parse needed lines, save artifacts on failure, and prune old logs. The demo produces short output so `Files.readString(...)` fits well.

## 22. Distinguishing Startup Failure, Normal Exit, and Hard Kill

| Scenario | Successful Context? | `SpringApplication.exit` Called? | How Code Is Determined |
| --- | --- | --- | --- |
| Runner returns SUCCESS | Yes | Yes | Generator bean returns 0 |
| Runner returns PARTIAL | Yes | Yes | Generator bean returns 12 |
| Runner returns INVALID_INPUT | Yes | Yes | Generator bean returns 21 |
| Runner returns TEMPORARY_UNAVAILABLE | Yes | Yes | Generator bean returns 30 |
| Runner throws FatalJobException | No successful context returned to main | No in main | Catch classifies cause, explicit `System.exit(43)` |
| Unsupported args | No successful context returned | No in main | Catch classifies usage error, explicit `System.exit(64)` |
| Process receives SIGKILL | No guarantee Java callbacks run | Not guaranteed | OS/orchestrator determines status from signal |
| JVM/host crash | No | Not guaranteed | External supervisor receives failure/signal per environment |

**Key takeaway:** `SpringApplication.exit(context)` is the right mechanism once **a working context exists**. Never pass `null` to it after `run` throws.

### `ContextClosedEvent` Is Not a Business Outcome

A context can close and every Spring-managed bean destroy callback can run, yet the job still had a PARTIAL result. Never treat `ContextClosedEvent` or "shutdown complete" as a SUCCESS signal to a scheduler. Combine **job result**, **resource cleanup**, and **process exit status**.

### Closing Context Before `System.exit`

Calling `SpringApplication.exit(context)` before `System.exit(code)` gives beans a chance to run destruction callbacks and flush appropriately. If the app has background tasks, stop intake and drain within a deadline before closing required resources; do not assume a short destroy callback suffices for long-running jobs.

## 23. Common Mistakes When Designing CLIs

**1. "Printing `exitCode=12` means the OS received 12."** False. You must call `System.exit(12)` or an equivalent mechanism.

**2. "`SpringApplication.exit` automatically stops the JVM."** No. It returns an `int` and closes the context, unlike `System.exit`.

**3. "`ExitCodeGenerator` codes are only for thrown exceptions."** No. Beans can supply business result codes during `exit(context)`.

**4. "If the runner finishes normally, exit is always 0."** No. A generator bean can return 12/21/30.

**5. "`ApplicationReadyEvent` means the business job succeeded."** No. Ready is a lifecycle milestone after normal runner return; it does not read `JobOutcome`.

**6. "When a runner throws, main still has a context to call `SpringApplication.exit`."** No. `run` never returned a context successfully.

**7. "Checking only the outermost exception is enough."** No. Runner failures can be wrapped by Spring Boot; walk the cause chain.

**8. "Using `ExitCodeExceptionMapper` alongside a manual classifier keeps both in sync automatically."** No. Pick one consistent policy and test it.

**9. "`System.exit` inside a runner makes code shorter."** It can bypass error reporting/cleanup; place it at the entrypoint.

**10. "JUnit calls `main` directly and checks the code."** That risks terminating the test JVM itself.

**11. "`ProcessBuilder` parses strings like PowerShell/Bash."** No. Use a separate argument list.

**12. "Always add quotes around paths passed to `ProcessBuilder`."** That can turn quotes into literal filename characters; do not add quotes yourself.

**13. "`Process.waitFor()` without a deadline is safe because the demo is tiny."** A regression can leave a hanging thread; always use a timeout.

**14. "`destroyForcibly()` means the test PASSED."** No. Force kill only cleans up a hung process; the test must FAIL.

**15. "No need to read stderr."** Can cause deadlocks if the child writes heavily to the error pipe.

**16. "`Files.readAllBytes` on a pipe before `waitFor` is always safe."** Not if the child never closes output; drain asynchronously or redirect to a file.

**17. "`gradle bootRun`'s exit code matches `java -jar`."** Not guaranteed; Gradle can wrap errors into a build failure code.

**18. "Asserting only `exitValue` is enough."** A code could match by coincidence; also assert markers/logs and side effects when relevant.

**19. "Hardcoding `build/libs/name.jar` is always fine."** Breaks when the project version changes; read `bootJar.archiveFile`.

**20. "Testing an old JAR is still a meaningful integration test."** No; enforce a build dependency before tests run.

**21. "`WebApplicationType.NONE` guarantees no background threads remain."** No; user-created threads, schedulers, and consumers can still run.

**22. "Negative exit codes or codes above 255 always pass intact across all shells."** No portability guarantee; use small positive numbers and test on the target OS.

**23. "Code 30 means the scheduler should retry forever."** No. Retries need budgets and idempotency.

**24. "Partial results can be treated as 0 because the app didn't crash."** No if the scheduler contract requires distinguishing partial runs.

**25. "Kubernetes understands each business exit code automatically."** Not automatically; you need appropriate policies/controllers/scripts.

**26. "`@PreDestroy` runs even on SIGKILL."** No. Hard kills bypass Java cleanup hooks.

**27. "Every test process should share the same log file."** No. Parallel tests risk overwriting each other; use separate temp files.

**28. "Bash `$?` is always Java's code even after `tee` or `echo`."** Not necessarily. Capture status right after the direct process, or handle pipelines properly.

**29. "No need for timeouts in CI tests."** False. One hung process can lock the entire pipeline.

**30. "Result code 0 in a bean means all resources flushed."** No. Set SUCCESS only after real commits/acks and guaranteed cleanup.

## 24. Code Review Checklist

Before deploying a CLI to a scheduler, verify:

1. **Entrypoint:** Does `SpringApplication.run(args)` forward args and set `WebApplicationType.NONE` when web is unneeded?
2. **Business logic:** Does the runner execute once and map results into a clear domain structure?
3. **Exit contract:** Does the code table have stable names, meanings, and retry policies?
4. **Bean generator:** Does `ExitCodeGenerator` read the actual final outcome rather than wrongly returning 0 by default?
5. **Startup exceptions:** Are runner errors classified without losing the cause chain?
6. **Exit ordering:** Do cleanup and context closing occur before `System.exit` on the normal path?
7. **Non-web:** Are no servers or stray threads accidentally keeping the JVM alive?
8. **Build:** Does `bootJar` produce an executable JAR with the right `mainClass` and version?
9. **Tests:** Does `ProcessBuilder` execute **the current build's JAR**, not an arbitrary classpath?
10. **OS portability:** Are Java executable and JAR path passed as separate arguments?
11. **Output:** Are stdout/stderr consumed or redirected so logs cannot deadlock?
12. **Timeout:** Does the child have a deadline and forced cleanup on expiry?
13. **Assertions:** Are both exit status and markers/side effects verified?
14. **Isolation:** Does each test have its own temp output without shared mutable static state?
15. **CI:** Are non-zero codes preserved rather than masked as 0 by shell/Gradle wrappers?
16. **Operations:** Are retries scoped to appropriate codes with idempotency, deadlines, and alerts?
17. **Secrets:** Are credentials and sensitive environment variables excluded from logs?
18. **Failure recovery:** On SIGKILL/host crash, are checkpoints/reconciliation in place?
19. **Deployment:** Does the Docker/Kubernetes entrypoint preserve the JVM exit code?
20. **Versioning:** Are process tests re-run whenever Spring Boot, JDK, or Gradle is upgraded?

## 25. Practice Exercises

1. Describe the distinct roles of `SpringApplication.run`, `SpringApplication.exit`, and `System.exit`.
2. Why does a non-web CLI still benefit from `ApplicationContext` and `ApplicationRunner`?
3. Run `gradle test` and identify which task builds the JAR before JUnit runs.
4. Run `--demo.mode=success`. Why does `EVENT: READY` appear before `LIFECYCLE: closed`?
5. Run `--demo.mode=partial`. Why does Ready fire yet the process exits with 12?
6. Try `--demo.mode=invalid`. What makes the code 21 instead of the JVM defaulting to 1?
7. Run `--demo.mode=retry`. Which retry policy should a scheduler apply? Why not retry infinitely?
8. Run `--demo.mode=fatal`. Why is `EVENT: READY` absent?
9. `FatalJobException` can be wrapped. Which code in `main` recovers code 43?
10. Remove `System.exit(code)` at the end of `main`. Which tests catch the contract violation? How does the process status change?
11. Change the `ExitCodeGenerator` bean to always return 0. Which tests fail?
12. Put `System.exit(12)` directly inside the runner. Which cleanup markers/lifecycle steps can be lost?
13. Call `CliExitApplication.main(...)` directly inside JUnit. Why is this an anti-pattern?
14. Modify a test to check only the log `MAIN: exitCode=12` without asserting `exitValue`. Which bug could slip through?
15. Intentionally remove `dependsOn bootJar`, then run tests after editing Java source. What risk occurs?
16. Change the version in Gradle from 1.0.0 to 1.0.1. Why do tests still find the right JAR?
17. Move the JAR path into a directory containing spaces. Why does `ProcessBuilder`'s argument list handle it better than a shell string?
18. Remove `redirectErrorStream(true)` and let the child write large stderr output. What forms of deadlock can happen?
19. Replace `redirectOutput(file)` with `getInputStream().readAllBytes()` before child exit. If the child hangs, what goes wrong?
20. Add a `hang` mode strictly in a sandbox. Does the test suite time out and kill the child properly?
21. In a test, call `process.exitValue()` immediately after `start()`. What exception can occur?
22. Pass `--demo.mode` without a value. How does `ApplicationArguments` handle it?
23. Pass `--demo.mode=success` twice. Why does the demo return a usage error instead of picking one value?
24. Run `java -jar` in Bash followed immediately by `echo $?`. Why shouldn't you run `echo hello` in between?
25. Pipe the application output through `tee`. How do you preserve Java's exit code?
26. Run in PowerShell. Why is `$LASTEXITCODE` better than `$?` for getting an integer exit code?
27. Add a bean with `@PreDestroy` recording a closed resource. How should you assert it without trusting logs alone?
28. Design a `JobResult` record and a method mapping status → code per business rules.
29. A job commits to the DB successfully but crashes before sending an ack. Why can't a process test guarantee exactly-once?
30. Add an `unexpected` mode throwing an exception that does not implement `ExitCodeGenerator`. What fallback code does `main` return?
31. Write a test using `ProcessBuilder.environment()` to pass a custom config value to the child without changing the test JVM's system properties.
32. Add a test verifying process exit code 64 on unsupported arguments while ensuring logs do not leak secret input values.
33. Compare a passing `@SpringBootTest` against a child-process test: which one verifies real OS exit status?
34. If you must verify 1,000 validation variants, how many should be unit tests vs. process-level tests? Explain the trade-off.
35. Integrate the JAR into a Kubernetes Job: what does the default controller understand on exit 12, and what external logic is needed for custom handling?
36. If CI has both JDK 17 and 21, why does using `java.home` for child tests reduce risk?
37. A child process writes gigabytes of logs. How would you modify the helper to avoid loading everything into RAM with `Files.readString`?
38. When a process receives SIGKILL, is Java `@PreDestroy` guaranteed? What recovery strategy is needed?
39. Design an exit code table for a file-import job: success, partial, bad input, transient dependency failure, permission denied, unknown.
40. Propose a pre-release checklist for a CLI whose exit codes serve as an API contract for orchestrators.

## Key Takeaways

- **Business outcomes and Spring Boot lifecycle are two distinct layers.** Runners can return normally and Boot can publish Ready, yet the CLI can still return non-zero via an `ExitCodeGenerator` bean.
- `SpringApplication.exit(context)` **retrieves the code from generators and closes the context**, whereas `System.exit(code)` delivers the code to the process owner.
- When `SpringApplication.run` throws, `main` receives no working context; classify the exception/cause chain and return a clear startup failure code.
- Never call `System.exit` directly inside JUnit or a bean lifecycle callback; **use a child JVM**.
- `ProcessBuilder` takes **an executable + separate arguments**, never a shell command string.
- When testing child processes, **drain/redirect stdout+stderr**, enforce `waitFor(timeout)`, kill timed-out processes, and clean up log files in `finally`.
- `Process.exitValue()` after child exit is the proof verifying **OS-level exit status**; never replace it with a log line.
- `test dependsOn bootJar` and a property pointing to `bootJar.archiveFile` ensure tests verify **the current JAR**.
- Do not use `gradle bootRun` as the sole source of truth for business exit codes; Gradle has its own build exit codes.
- Use small, stable codes and document retry policies; avoid non-portable values across shells/OSes.
- For jobs with side effects, exit codes do not replace timeouts, transactions, idempotency, checkpoints, or recovery.

### References

- Spring Boot 3.3 — Application Exit and ExitCodeGenerator: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — SpringApplication Javadoc (exit, run, WebApplicationType): https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3 — ExitCodeGenerator Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeGenerator.html
- Spring Boot 3.3 — ExitCodeExceptionMapper Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeExceptionMapper.html
- Spring Boot 3.3 — ApplicationRunner and ApplicationArguments: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html
- Spring Boot 3.3.13 — SpringApplication failure/exit-code source: https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/SpringApplication.java
- Java SE 17 — Process: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Process.html
- Java SE 17 — ProcessBuilder: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.html
- Java SE 17 — System.exit: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#exit(int)
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/
- Gradle — Testing in Java & JVM Projects: https://docs.gradle.org/current/userguide/java_testing.html
- Gradle — Task Dependencies: https://docs.gradle.org/current/userguide/part2_gradle_tasks.html
- Kubernetes — Jobs: https://kubernetes.io/docs/concepts/workloads/controllers/job/
