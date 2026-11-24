# Testing Exit Codes with a Child Process Instead of Stopping the Test Suite JVM

## 1. Learning objectives

A Spring Boot application running as a CLI, batch job, import/export tool, or worker often needs to report its outcome to the shell, CI/CD, or job scheduler via a **process exit code**. Typically `0` means success, while a non-zero code signals failure per the application contract.

Suppose the application's `main()` ends with:

```java
System.exit(code);
```

This is a valid way for a CLI to pass a status code to the OS. However, if a JUnit test **calls `main()` directly inside the same JVM running JUnit**, the `System.exit` call can terminate the Maven Surefire/Failsafe JVM itself before the test reports results, runs subsequent assertions, or finishes the suite.

**Solution:** use `ProcessBuilder` to launch **a child JVM** running the real JAR; JUnit in the parent JVM waits for the child to exit, reads **`Process.exitValue()`**, inspects stdout/stderr, and ensures the child is killed on timeout.

This lesson covers in full:

1. Distinguishing *business outcome*, the value from `ExitCodeGenerator`/`SpringApplication.exit`, and the **OS process exit status**.
2. Understanding why `main()` containing `System.exit()` must not be called directly inside the test runner.
3. Using `ProcessBuilder` with the right `java` executable, argument list, log redirection, and deadline.
4. Configuring Maven **Failsafe** to run integration tests **after** `package` so the executable Spring Boot JAR exists.
5. Writing a Spring Boot 3.3.13 / Java 21 application returning three codes `0`, `2`, `17`, with `ApplicationRunner`, `ExitCodeGenerator`, `ExitCodeEvent`, and `@PreDestroy`.
6. Testing code-selection logic with JUnit unit tests; testing the **real process exit code** with JUnit `ExitProcessIT`.
7. Distinguishing timeouts, force-killed children, JVM shutdown, startup failures, cleanup failures, and async state.
8. Fixing tests that hang due to full stdout/stderr pipes, run the wrong JDK, break on paths with spaces, or return a false `0` code.

**Scope:** examples use Spring Boot 3.3.13, Java 21, JUnit Jupiter, Maven, and a Spring Boot executable JAR. The demo is non-web and requires no database or broker.

## 2. Three outcome layers that must not be conflated

```text
CLI flags / business input
          |
          v
ApplicationRunner processes job
          |
          +-- SUCCESS          -> 0
          +-- INVALID_INPUT    -> 2
          +-- BUSINESS_FAILED  -> 17
          |
          v
ExitCodeGenerator#getExitCode()
          |
          v
SpringApplication.exit(context)
          |
          +-- compute exit code
          +-- close Spring context
          |      +-- stop lifecycle components
          |      +-- @PreDestroy / destroy callbacks
          |
          v
main() calls System.exit(code)
          |
          v
Child JVM terminates, OS records code
          |
          v
Parent JUnit: waitFor -> exitValue -> assert
```

| Layer | Tested with | Terminates the JVM itself? |
| --- | --- | --- |
| **Business outcome** | Pure Java function/enum, unit test | No |
| **Boot-computed code** | `SpringApplication.exit(context)` and `ExitCodeGenerator` | No |
| **Process exit code** | `Process.exitValue()` after child terminates | Result of the terminated child JVM process |

`SpringApplication.exit(context)` **returns an `int`** and closes the context where applicable; it **does not call `System.exit(int)` automatically**. Thus if a CLI app only calls `SpringApplication.exit` and returns normally, the shell may observe code `0` even though the generator returned `17`.

On the other hand, testing `System.exit(code)` inside the JUnit JVM is **unsafe for the test runner**. To be certain the shell/CI receives the right code, run a real child process.

### 2.1. Why not test only ExitCodeGenerator?

For example:

```java
assertEquals(17, outcome.exitCode());
```

This unit test proves the mapping is right, yet does not guarantee `main()` passed that code to `System.exit`. A refactor might leave `main` forgetting to call `System.exit`, or change it to `System.exit(0)` so CI reports a false success while pure tests stay green.

A test like:

```java
int code = SpringApplication.exit(context);
assertEquals(17, code);
```

likewise proves only the code **returned by Spring**, not that the **OS process** received the code. Therefore both test levels are needed.

### 2.2. Why not test every branch with a child process?

Each child JVM must boot the Java runtime, classpath, Spring context, and run cleanup. The cost is far higher than a pure unit test. It is best to unit-test all precedence rules thoroughly, then select a few representative child integration tests for key states: `0`, nonzero, cleanup, and timeout.

## 3. Anti-pattern: calling main() containing System.exit inside JUnit

Here is **code you should not run inside the test JVM**:

```java
@Test
void badTest() {
    ExitChildApplication.main(new String[] {"--business-fail"});

    // The test JVM may have already been terminated by System.exit(17).
    assertEquals(17, expectedCode);
}
```

The application's `main` is designed to call `System.exit`. The test above can terminate the Surefire process before reaching the assertion or before JUnit generates a report. The failure appears as an abnormally terminated fork rather than an informative assertion failure.

Wrong ways to avoid this:

- **Do not** edit production `main` to remove `System.exit` solely so tests pass: the CLI's exit-code behavior will break.
- **Do not** catch all exceptions and return `0`, as that strips failure signals from automation.
- **Do not** rely on `SecurityManager` blocking exit as a primary solution on Java 21: that API is deprecated for removal, and blocking the call does not verify the real OS status.
- **Do not** call `System.exit` inside an `ApplicationRunner`, repository, service, or `@PreDestroy` callback: place the JVM-wide action at the CLI boundary after work completes.
- **Do** extract code-selection logic into a unit-testable class and use `ProcessBuilder` to run the JAR in a child JVM.

## 4. SpringApplication.exit and resource cleanup

In Spring Boot 3.3:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(ExitChildApplication.class, args);

int code = SpringApplication.exit(context);

System.exit(code);
```

This snippet is **illustrative**, requiring imports and the primary source class. `SpringApplication.exit` collects codes from `ExitCodeGenerator` beans and passed generators. It can emit an `ExitCodeEvent` when the code is non-zero, then closes the context. Only the `System.exit` at the end turns the code into the OS process status.

### 4.1. ExitCodeGenerator

This is the Spring Boot contract:

```java
@FunctionalInterface
public interface ExitCodeGenerator {
    int getExitCode();
}
```

This is an **illustrative signature**, not a file to define yourself in the project. A `@Component` bean can implement the interface so Spring reads the code decided by the business job.

When multiple generators exist, Boot evaluates codes in the sorted generator order and picks the **first non-zero code**. Do not assume the largest code or last-running generator automatically wins. If the business domain has multiple error categories, building **a single outcome aggregator** with explicit precedence is easier to maintain.

### 4.2. @PreDestroy and ExitCodeEvent

Success path of a synchronous CLI:

```text
ApplicationRunner.run completes
    |
    v
SpringApplication.exit(context)
    |
    +-- ExitCodeGenerator.getExitCode()
    +-- ExitCodeEvent if code is nonzero
    +-- close ApplicationContext
          +-- ContextClosedEvent
          +-- SmartLifecycle.stop(...)
          +-- @PreDestroy
    |
    v
SpringApplication.exit returns int
    |
    v
System.exit(int)
```

One detail to understand clearly: **generator codes may be evaluated before `@PreDestroy` runs**. If cleanup fails for the first time inside `@PreDestroy`, the already-chosen code does not automatically change to reflect that error. To make the exit result include cleanup failures, perform an explicit cleanup/await step reporting its outcome **before** `SpringApplication.exit` computes the code, or use an exit coordinator governing the final outcome.

In the demo, `@PreDestroy` deletes a temporary file and prints a marker; tests verify the callback runs before `main` announces the context closed. Tests do not intentionally simulate a file-deletion error inside the destroy callback.

### 4.3. When a startup exception occurs

If `ApplicationRunner` throws an exception before `SpringApplication.run` returns the context, code placed **after** `run` may never execute; Boot has its own startup failure handling path, including mapping codes from exceptions/mappers when configured. Thus child tests for controlled business results `2`/`17` do not replace dedicated tests for startup failures.

## 5. Why use ProcessBuilder and the executable JAR?

### 5.1. ProcessBuilder isolates the JVM

```java
ProcessBuilder builder = new ProcessBuilder(
        "java", "-jar", "target/app.jar", "--business-fail");

Process child = builder.start();

boolean finished = child.waitFor(30, TimeUnit.SECONDS);

if (finished) {
    int actualCode = child.exitValue();
}
```

This snippet is **illustrative** only, omitting imports, timeout cleanup, and output handling; see the full test in section 9. `ProcessBuilder.start()` spawns a separate OS process rather than invoking `main` via reflection in the same JVM. When the child calls `System.exit(17)`, JUnit's parent JVM stays alive and receives `exitValue=17` if the child terminates cleanly.

`exitValue()` must only be called after the process has terminated. If the child is still alive, `exitValue()` throws `IllegalThreadStateException`.

### 5.2. Use an argument list, never concatenate shell strings

A command containing paths with spaces is easily misparsed if concatenated manually:

```java
String command = "java -jar C:\\Program Files\\demo.jar --flag";
```

This is a **broken pattern** because argument splitting depends on how a shell is invoked. Replace with:

```java
new ProcessBuilder(
        javaExecutable.toString(),
        "-jar",
        jar.toString(),
        "--business-fail");
```

The second snippet is an **illustrative pattern**, requiring `javaExecutable` and `jar`. `ProcessBuilder` takes each argument individually. Never embed literal quotes into filenames: manual quotes can become literal characters in the argument on some platforms.

### 5.3. Select Java from java.home

If you simply invoke `"java"`, the machine or CI `PATH` may pick a different JDK from the JUnit runtime. Better tests determine:

```java
String osName = System.getProperty("os.name")
        .toLowerCase(Locale.ROOT);

String executable = osName.startsWith("windows")
        ? "java.exe" : "java";

Path java = Path.of(
        System.getProperty("java.home"), "bin", executable);
```

This snippet is in the complete test. With Java 21, the JDK runtime normally has its executable at `bin/java` or `bin/java.exe`; tests can check the file exists and fail clearly if the environment mismatches.

### 5.4. Why use the JAR instead of -cp?

A subprocess could run:

```bash
java -cp "runtime-classpath" com.example.exitdemo.ExitChildApplication
```

With Maven Surefire/Failsafe, however, the test runner's `java.class.path` may contain only a bootstrapping JAR or a classpath mismatching the application runtime. Manually assembling all dependencies is error-prone and depends on Windows/Unix classpath separators.

The Spring Boot executable JAR after `package` already bundles the loader and required dependencies. Therefore:

```bash
java -jar target/exit-child-demo-0.0.1-SNAPSHOT.jar
```

matches how the CLI app runs in practice and reduces coupling to test runner internals.

## 6. Which phases do Maven Surefire and Failsafe run in?

```text
compile
   |
test             <-- Surefire runs *Test
   |
package          <-- Spring Boot Maven plugin builds executable JAR
   |
integration-test <-- Failsafe runs *IT
   |
verify           <-- Failsafe verifies integration test results
```

We must **wait for the JAR to be built in `package`** before `ExitProcessIT` uses it. Hence this test must run in `integration-test`, not in Surefire `test` before the JAR exists.

Standard command:

```bash
mvn clean verify
```

`mvn test` only runs pure unit tests in the `test` phase and does not verify the OS exit code of the newly packaged JAR. Do not invoke `mvn integration-test` alone and skip `verify` if you want Failsafe to report full outcomes after integration teardown.

### 6.1. Test naming

- `JobOutcomeTest.java`: unit tests executed by Surefire.
- `ExitProcessIT.java`: integration tests executed by Failsafe.

Maven Failsafe supports JUnit Jupiter when dependencies and plugin versions match. The project below pins Failsafe `3.2.5`.

### 6.2. Never run the integration test before packaging

If `ExitProcessIT` checks the path:

```text
target/exit-child-demo-0.0.1-SNAPSHOT.jar
```

while the developer only ran `mvn test`, the file may not exist yet or may be a stale artifact from an earlier build. **Never** use a stale JAR to claim current source passes. `mvn clean verify` builds from scratch and runs tests against the newly built JAR.

## 7. Complete Spring Boot 3.3.13 / Java 21 demo

The project comprises a non-web CLI and two test suites. The CLI handles three simple outcome flags, creates/deletes a temporary file, and returns the code to the OS. No HTTP ports or external servers are opened.

### 7.1. Project structure

```text
exit-child-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/exitdemo/
    │   ├── ExitChildApplication.java
    │   ├── JobOutcome.java
    │   ├── ExitJob.java
    │   └── ExitCodeObserver.java
    └── test/java/com/example/exitdemo/
        ├── JobOutcomeTest.java
        └── ExitProcessIT.java
```

### 7.2. pom.xml

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
    <artifactId>exit-child-demo</artifactId>
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

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.2.5</version>
                <executions>
                    <execution>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

The Spring Boot parent manages dependencies and configures plugins appropriately so `spring-boot-maven-plugin` repackages the executable JAR. Failsafe runs ITs after packaging.

`spring-boot-starter` suffices for `ApplicationRunner`, events, and the non-web context. `spring-boot-starter-test` brings JUnit Jupiter. Java 21 is compatible with Boot 3.3.13.

### 7.3. JobOutcome.java

File `src/main/java/com/example/exitdemo/JobOutcome.java`:

```java
package com.example.exitdemo;

public enum JobOutcome {

    SUCCESS(0),
    INVALID_INPUT(2),
    BUSINESS_FAILED(17);

    private final int exitCode;

    JobOutcome(int exitCode) {
        this.exitCode = exitCode;
    }

    public int exitCode() {
        return exitCode;
    }

    public static JobOutcome fromFlags(
            boolean invalidInput, boolean businessFailed) {

        if (invalidInput) {
            return INVALID_INPUT;
        }
        if (businessFailed) {
            return BUSINESS_FAILED;
        }
        return SUCCESS;
    }
}
```

Here, business → code mapping is pure Java, easy to test and independent of JVM shutdown. If both `--invalid-input` and `--business-fail` are present, the demo **prioritizes `INVALID_INPUT` (2)**. This is a business choice in the example, not a Spring default.

### 7.4. ExitJob.java

File `src/main/java/com/example/exitdemo/ExitJob.java`:

```java
package com.example.exitdemo;

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
public class ExitJob implements ApplicationRunner, ExitCodeGenerator {

    private volatile JobOutcome outcome = JobOutcome.SUCCESS;
    private Path temporaryFile;

    @Override
    public void run(ApplicationArguments args) throws Exception {
        temporaryFile = Files.createTempFile("exit-child-demo-", ".tmp");

        Files.writeString(
                temporaryFile, "demo job completed\n",
                StandardCharsets.UTF_8);

        outcome = JobOutcome.fromFlags(
                args.containsOption("invalid-input"),
                args.containsOption("business-fail"));

        System.out.println("JOB result=" + outcome.name()
                + " code=" + outcome.exitCode());
    }

    @Override
    public int getExitCode() {
        return outcome.exitCode();
    }

    @PreDestroy
    void cleanup() throws IOException {
        boolean deleted = temporaryFile != null
                && Files.deleteIfExists(temporaryFile);

        System.out.println("CLEANUP tempFileDeleted=" + deleted);
    }
}
```

`ExitJob` creates a **temporary file** to perform real resource cleanup rather than merely printing "cleaned up". `@PreDestroy` deletes it during bean destruction. Without exceptions, output confirms `tempFileDeleted=true`.

**Limitation:** the demo's temp file is not durable production data. For real business files, do not delete final outputs; use flush/fsync, atomic renames, retries, and proper error persistence. If cleanup in `@PreDestroy` fails, do not assume the generator code changes automatically; see section 13.

`JobOutcome` is stored in a field so Spring Boot calls `getExitCode()` after `ApplicationRunner`. The demo processes synchronously rather than submitting a background task and returning before the outcome is finalized.

### 7.5. ExitCodeObserver.java

File `src/main/java/com/example/exitdemo/ExitCodeObserver.java`:

```java
package com.example.exitdemo;

import org.springframework.boot.ExitCodeEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ExitCodeObserver {

    @EventListener
    public void observe(ExitCodeEvent event) {
        System.out.println("EXIT event=" + event.getExitCode());
    }
}
```

`ExitCodeEvent` can be emitted when `SpringApplication.exit` computes a non-zero code, before closing the context. The listener only records a marker for testing. It does not decide the code itself and never calls `System.exit`.

### 7.6. ExitChildApplication.java

File `src/main/java/com/example/exitdemo/ExitChildApplication.java`:

```java
package com.example.exitdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class ExitChildApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ExitChildApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context = application.run(args);

        int code = SpringApplication.exit(context);

        System.out.println("MAIN contextClosed="
                + !context.isActive() + " code=" + code);

        System.exit(code);
    }
}
```

`WebApplicationType.NONE` lets it run as a CLI without opening a port. On successful startup, the runner has already executed before `application.run()` returns the context. `SpringApplication.exit(context)` reads the code and closes the context. Only afterward does `System.exit(code)` terminate the JVM.

**Never call this `main()` inside a JUnit unit test**. It intentionally calls `System.exit` because that is the real CLI contract.

## 8. Unit tests for business mapping

File `src/test/java/com/example/exitdemo/JobOutcomeTest.java`:

```java
package com.example.exitdemo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class JobOutcomeTest {

    @Test
    void successReturnsZero() {
        assertEquals(0, JobOutcome.fromFlags(false, false).exitCode());
    }

    @Test
    void businessFailureReturnsSeventeen() {
        assertEquals(17, JobOutcome.fromFlags(false, true).exitCode());
    }

    @Test
    void invalidInputHasPriority() {
        assertEquals(2, JobOutcome.fromFlags(true, true).exitCode());
    }
}
```

Tests run inside the JUnit JVM because they only invoke pure Java functions and never terminate the process. The command:

```bash
mvn test
```

runs these **three tests** via Surefire. Do not claim OS exit status has been tested when running only `mvn test`.

## 9. Controlled process integration test

File `src/test/java/com/example/exitdemo/ExitProcessIT.java`:

```java
package com.example.exitdemo;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

class ExitProcessIT {

    @TempDir
    Path temporaryDirectory;

    private record RunResult(int exitCode, String output) {
    }

    @Test
    void successReturnsZeroAfterCleanup() throws Exception {
        RunResult result = runChild();

        assertEquals(0, result.exitCode(), result.output());

        assertInOrder(result.output(),
                "JOB result=SUCCESS code=0",
                "CLEANUP tempFileDeleted=true",
                "MAIN contextClosed=true code=0");
    }

    @Test
    void businessFailureReturnsSeventeen() throws Exception {
        RunResult result = runChild("--business-fail");

        assertEquals(17, result.exitCode(), result.output());

        assertInOrder(result.output(),
                "JOB result=BUSINESS_FAILED code=17",
                "EXIT event=17",
                "CLEANUP tempFileDeleted=true",
                "MAIN contextClosed=true code=17");
    }

    @Test
    void invalidInputReturnsTwo() throws Exception {
        RunResult result = runChild(
                "--business-fail", "--invalid-input");

        assertEquals(2, result.exitCode(), result.output());

        assertInOrder(result.output(),
                "JOB result=INVALID_INPUT code=2",
                "EXIT event=2",
                "CLEANUP tempFileDeleted=true",
                "MAIN contextClosed=true code=2");
    }

    private RunResult runChild(String... options) throws Exception {
        Path projectDir = Path.of(
                System.getProperty("user.dir")).toAbsolutePath();

        Path jar = projectDir.resolve("target")
                .resolve("exit-child-demo-0.0.1-SNAPSHOT.jar");

        assertTrue(Files.isRegularFile(jar),
                "Executable JAR not found; run mvn clean verify: " + jar);

        String os = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT);

        String binary = os.startsWith("windows")
                ? "java.exe" : "java";

        Path javaExecutable = Path.of(
                System.getProperty("java.home"), "bin", binary);

        assertTrue(Files.isRegularFile(javaExecutable),
                "Java executable not found: " + javaExecutable);

        List<String> command = new ArrayList<>();
        command.add(javaExecutable.toString());
        command.add("-Dfile.encoding=UTF-8");
        command.add("-jar");
        command.add(jar.toString());
        command.add("--spring.main.banner-mode=off");
        command.add("--logging.level.root=ERROR");
        Collections.addAll(command, options);

        Path outputFile = Files.createTempFile(
                temporaryDirectory, "child-", ".log");

        ProcessBuilder builder = new ProcessBuilder(command);
        builder.directory(projectDir.toFile());
        builder.redirectErrorStream(true);
        builder.redirectOutput(outputFile.toFile());

        Process process = builder.start();

        try {
            if (!process.waitFor(30, TimeUnit.SECONDS)) {
                process.destroy();

                if (!process.waitFor(2, TimeUnit.SECONDS)) {
                    process.destroyForcibly();
                    process.waitFor(5, TimeUnit.SECONDS);
                }

                String partialOutput = Files.readString(
                        outputFile, StandardCharsets.UTF_8);

                fail("Child JVM exceeded 30-second timeout:\n"
                        + partialOutput);
            }

            String output = Files.readString(
                    outputFile, StandardCharsets.UTF_8);

            return new RunResult(process.exitValue(), output);
        }
        finally {
            if (process.isAlive()) {
                process.destroyForcibly();
                process.waitFor(5, TimeUnit.SECONDS);
            }
        }
    }

    private static void assertInOrder(
            String output, String... markers) {

        int previousIndex = -1;

        for (String marker : markers) {
            int currentIndex = output.indexOf(marker);

            assertTrue(currentIndex >= 0,
                    "Missing marker " + marker + "\n" + output);

            assertTrue(currentIndex > previousIndex,
                    "Marker out of order " + marker + "\n" + output);

            previousIndex = currentIndex;
        }
    }
}
```

### 9.1. Key sound practices in the ProcessBuilder test

**Runs the real JAR.** The test looks up `target/exit-child-demo-0.0.1-SNAPSHOT.jar` after the packaging step. It does not rely on `.class` files or Surefire's test classpath.

**Uses the right JDK.** The Java executable is taken from `java.home/bin`. On Windows it has the `.exe` suffix; on Linux/macOS it uses `java`. On CI machines with multiple JDKs, this avoids picking the wrong `"java"` from `PATH`.

**Passes arguments properly.** Each argument is an element of `List<String>`. Paths like `C:\Program Files\Java\...` do not need manual shell quoting.

**Avoids pipe deadlocks.** `redirectErrorStream(true)` merges stderr into stdout; `redirectOutput(outputFile)` writes child output directly to a file. The parent **does not** have to drain streams before `waitFor`. Once the child terminates, the test reads the file to assert.

**Enforces a timeout.** `waitFor(30, SECONDS)` bounds total time from child launch, covering Spring bootstrap, runner, and shutdown. If the deadline expires, the child is asked to stop and then force-killed if needed, failing the test with the partial log attached.

**Leaves no orphan child.** `finally` checks `process.isAlive()` and calls `destroyForcibly()` if needed. This guards against JUnit leaving orphan processes behind when code changes or tests fail.

**Meaningful assertions.** Tests check both the OS status (`exitCode`) and the `JOB`, `EXIT`, `CLEANUP`, `MAIN` markers. Never assert only `BUSINESS_FAILED` in the log while forgetting to check the process code.

### 9.2. Why redirect output before waitFor?

A classic mistake:

```java
Process p = builder.start();
p.waitFor();

String output = new String(
        p.getInputStream().readAllBytes(),
        StandardCharsets.UTF_8);
```

This is an **anti-pattern** when the child can print substantial logs: OS pipes have finite buffers, so the child can block once the pipe fills. Meanwhile the parent waits for the process to exit, causing a **deadlock**. If stdout and stderr use two separate pipes, draining only one pipe is still insufficient.

Two solutions:

- Redirect both stdout and stderr into one file as in the demo (simple and fits test logs).
- Use separate readers running **concurrently** to consume stdout/stderr, with thread management and timeouts.

Never wait indefinitely before starting to read output when using default `PIPE`. In tests producing large logs, also cap disk usage or retain only needed excerpts.

### 9.3. A timeout does not mean the app returned non-zero

If the child times out and the test calls `destroyForcibly()`, the OS exit status returned at that point **is not** proof the application called `System.exit` with a matching code. Timeouts must be reported as **distinct test failures**, never folded into assertions on business codes `2` or `17`.

Across Windows, Linux, and macOS, `destroy()`/`destroyForcibly()` semantics can differ; do not treat `destroy()` on every platform as identical to a specific POSIX `SIGTERM`.

### 9.4. Why not use Thread.sleep to wait for the child JVM?

Code such as:

```java
Process p = builder.start();
Thread.sleep(2000);
assertEquals(17, p.exitValue());
```

is **unreliable**: CI machines may take 4 seconds to boot Spring, or the app may finish much sooner. After two seconds if the child is still running, `exitValue()` throws `IllegalThreadStateException`; otherwise the sleep time is wasted.

`waitFor(timeout, TimeUnit.SECONDS)` synchronizes on **real completion** with a deadline, making it far superior to an arbitrary sleep. Likewise, never busy-spin calling `isAlive()` without a timeout and backoff.

### 9.5. Why is @TempDir useful?

`@TempDir Path temporaryDirectory` is a JUnit Jupiter feature creating an isolated temporary directory per test, avoiding log-file collisions across tests. Logs are cleaned up by the extension lifecycle. The child JVM creates its own temp file in `ExitJob`, and `@PreDestroy` deletes it when the context closes cleanly.

In real projects, if children share a DB, filesystem paths, or ports, isolate those resources too; a child process isolates **JVM memory**, not the entire OS, network, and storage automatically.

## 10. Full verification with Maven

### 10.1. First, unit tests only

```bash
java -version
mvn -version
mvn clean test
```

For the demo project, Surefire is expected to run the **3 unit tests** in `JobOutcomeTest`; `ExitProcessIT` has not run yet. `BUILD SUCCESS` on this command does not yet verify the app's OS exit code.

### 10.2. Next, integration tests with the executable JAR

```bash
mvn clean verify
```

Flow:

```text
mvn clean verify
     |
     +-- compile
     +-- test: JobOutcomeTest (3 assertions)
     +-- package: executable JAR
     +-- integration-test: ExitProcessIT (3 child JVMs)
     +-- verify: Failsafe aggregates results
```

The illustrative test classes expect **3 unit tests + 3 integration tests**, 6 tests total, all passing in an environment with JDK 21, Maven, and dependencies. Never hardcode execution durations or full Maven output in assertions.

If the JAR is missing, check `artifactId`, `version`, actual JAR name, the Spring Boot Maven plugin, the current Maven module, and which lifecycle phase ran.

### 10.3. Maven reports

Typical reports:

```text
target/surefire-reports/
    TEST-com.example.exitdemo.JobOutcomeTest.xml

target/failsafe-reports/
    TEST-com.example.exitdemo.ExitProcessIT.xml
    failsafe-summary.xml
```

Reports separate unit test failures from child exit-code integration test failures. When CI fails, save child log files from `@TempDir`/test artifacts per policy or print an excerpt in the assertion failure; avoid accidentally logging secrets.

### 10.4. Never run Failsafe before package

Merely running `mvn test` and then manually running ITs can pick up a stale JAR from a previous build. That is a dangerous bug: tests appear "green" without measuring the current source code. `mvn clean verify` guarantees a clean build before running ITs against the freshly created JAR.

## 11. Running the JAR manually to cross-check

In Bash/zsh, immediately after `mvn package` or `mvn verify`:

### 11.1. Success

```bash
java -jar target/exit-child-demo-0.0.1-SNAPSHOT.jar
echo $?
```

Lines **explicitly printed by the demo code** in order:

```text
JOB result=SUCCESS code=0
CLEANUP tempFileDeleted=true
MAIN contextClosed=true code=0
```

Shell prints:

```text
0
```

`EXIT event=...` is not emitted on the zero-code path. Spring Boot may print banners, logs, and timestamps, so the block above is not all of stdout.

### 11.2. Business failure

```bash
java -jar target/exit-child-demo-0.0.1-SNAPSHOT.jar --business-fail
echo $?
```

Demo lines in order:

```text
JOB result=BUSINESS_FAILED code=17
EXIT event=17
CLEANUP tempFileDeleted=true
MAIN contextClosed=true code=17
```

Right after the Java command, Bash/zsh prints:

```text
17
```

### 11.3. Invalid input

```bash
java -jar target/exit-child-demo-0.0.1-SNAPSHOT.jar --invalid-input
echo $?
```

Lines:

```text
JOB result=INVALID_INPUT code=2
EXIT event=2
CLEANUP tempFileDeleted=true
MAIN contextClosed=true code=2
```

And the shell prints:

```text
2
```

If both flags are passed, `JobOutcome.fromFlags` prioritizes invalid input, so the code stays `2`.

### 11.4. PowerShell and CMD

PowerShell:

```powershell
java -jar target/exit-child-demo-0.0.1-SNAPSHOT.jar --business-fail
$LASTEXITCODE
```

CMD:

```bat
java -jar target/exit-child-demo-0.0.1-SNAPSHOT.jar --business-fail
echo %ERRORLEVEL%
```

In both cases, the expected code is `17`. Do not use Bash's `$?` in PowerShell: `$?` has boolean success/failure semantics for the last command, whereas `$LASTEXITCODE` is the proper variable for inspecting a native process exit code.

**Read the code immediately after the Java command**; running another native command overwrites the shell status variable.

## 12. When should you test the context directly?

Not every test goal needs a child process. A Spring context test can be written as:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(ExitChildApplication.class);

int code = SpringApplication.exit(context);
assertEquals(0, code);
```

This is a **non-standalone illustrative pattern**. It shows bean wiring, exit generators, and close logic work inside a JVM. Because it **does not call `main`**, this test will not terminate the JUnit process.

Still, it **does not prove** the CLI `main` actually passes the code into `System.exit(code)`. In this lesson, verifying the OS exit code is the core requirement, so the child test is indispensable.

| Test style | Separate JVM? | Verifies OS exit status? | When to use |
| --- | --- | --- | --- |
| Code mapping unit test | No | No | All precedence rules and input validation |
| Spring context integration test | No | No | Bean lifecycle, `ExitCodeGenerator`, DI |
| `ProcessBuilder` + packaged JAR | **Yes** | **Yes** | `main`, `System.exit`, shell codes, cleanup, and deployment artifact |

## 13. Non-happy-path scenarios

### 13.1. `ApplicationRunner` throws an exception

If a runner throws an exception before `SpringApplication.run` returns the context, `main` in the demo may never reach the `SpringApplication.exit` line. Spring Boot handles startup failures via its own mechanism, including exception handling, context shutdown, and exit-code mappers when configured. The demo's controlled business failure test (`--business-fail`) **does not throw an exception**, allowing us to observe the generator-chosen code.

To test startup exception exit codes, add a separate child test with an explicitly specified error mapping and OS code assertion. Never collapse every exception into `System.exit(0)`.

### 13.2. Cleanup error after the generator is read

`@PreDestroy` runs when Spring destroys beans. If `getExitCode()` ran before `@PreDestroy`, the code has already been computed. A file-deletion failure inside the destroy callback may be logged yet is **not guaranteed** to change the OS exit code from `0` to a failure value.

If a requirement demands **the exit code reflect cleanup outcomes**, organize explicit cleanup before calling `SpringApplication.exit`:

```java
CleanupOutcome cleanup = job.cleanupAndAwait();

int plannedCode = decideCode(job.outcome(), cleanup);

int returnedCode = SpringApplication.exit(
        context, () -> plannedCode);

System.exit(returnedCode);
```

This is **architectural pseudocode**, requiring definitions for `CleanupOutcome`, `decideCode`, `job`, and `context`; it is not a standalone compilable class. Note that if other `ExitCodeGenerator` beans exist, code selection order must be clearly defined. Use a single result aggregator when strict precedence is required.

### 13.3. Incomplete async tasks

If a runner merely calls `executor.submit(...)` and returns, Boot may compute the exit code before the task finishes. When the context closes, resource providers may be destroyed while the task still uses them.

To stay safe:

1. Stop accepting new tasks.
2. Await in-flight work with a finite deadline.
3. Persist results, checkpoints/acks, or retry states.
4. Finalize the exit code only after success/failure is known.
5. Let Spring stop `SmartLifecycle` per phase/dependencies.
6. After the context closes cleanly, call `System.exit(code)`.

Never invoke `SmartLifecycle.stop(Runnable callback)` and call the callback immediately after merely submitting a drain task. The callback must signal stop has **genuinely completed** or reached timeout/failure per policy; firing too early can close providers while consumers remain active.

### 13.4. SIGTERM, SIGKILL, and test-triggered kills

`System.exit(17)` is an application-initiated exit. If a child JVM is hit with `SIGKILL` or `destroyForcibly`, the OS may return a termination-specific status, **not** the business logic code. On Unix shells, convention often encodes signal termination as `128 + signal`, though this is not universal across every launcher/OS.

Do not lump timeout/force-kill cases into an assertion expecting business failure `exitCode == 17`. For forced termination, tests must verify a different **failure mode and recovery**, without assuming `@PreDestroy` ran.

### 13.5. Child processes spawning grandchild processes

`process.destroyForcibly()` typically acts on one process handle and does not automatically manage all descendants spawned by the app. If a test uses shell launchers, wrappers, or child subprocesses, clean up the process tree via `ProcessHandle.descendants()` under an explicit policy.

The demo runs `java -jar` **directly** and spawns no additional processes, so this extra logic is unneeded.

### 13.6. External resources remain shared outside the JVM

A child JVM isolates classloaders, threads, and memory, yet does not isolate:

- Host filesystem.
- Shared test database, broker, or Redis.
- TCP ports.
- Environment variables and secrets.
- CI CPU/RAM/disk quotas.

For larger projects, use `@TempDir`, dynamic ports, Testcontainers, or fake dependencies as appropriate. Avoid testing by deleting production files or accidentally connecting to real systems.

## 14. Common mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Surefire fork terminates abnormally | Test called `main` containing `System.exit` | Use a child JVM; unit-test logic separately |
| `mvn test` passes yet `ExitProcessIT` didn't run | Failsafe runs only after `package` | `mvn clean verify` |
| JAR missing in `target/` | Not packaged or wrong artifact path | Check POM/phase/working dir |
| `no main manifest attribute` | Missing proper Spring Boot repackaging | Check Spring Boot Maven plugin |
| `ClassNotFoundException` when using `-cp` | Incomplete test launcher classpath | Use the executable JAR |
| Child runs wrong JDK version | `"java"` picked from `PATH` | Use `java.home/bin/java[.exe]` |
| Paths with spaces fail | Concatenating arguments into one shell string | Use `ProcessBuilder(List<String>)` |
| `waitFor()` hangs when child logs heavily | Stdout/stderr pipes full | Redirect to file or read streams concurrently |
| Test reads `exitValue()` while child is alive | `waitFor` did not complete yet | Wait with a deadline |
| Child times out yet test hangs | Missing cleanup fallback | `destroy`, `destroyForcibly`, `finally` |
| `Thread.sleep` then assert is flaky | Sleep does not prove process finished | `waitFor(timeout, TimeUnit.SECONDS)` |
| Child JVM lacks permission for temp files | CI environment / read-only filesystem | Supply proper temp dir and investigate permissions |
| Missing cleanup marker | Context didn't close, stdout lost logs, startup failed | Check logs, process path, exit helper |
| Business failure yields OS code `0` | `main` forgot `System.exit(code)` | Child IT verifying real code |
| Test asserts entire Boot log | Banner/version/timing varies | Assert stable markers and ordering |
| JUnit test dies after passing one case | Test called `main` inside parent JVM | Never call directly; use subprocess |
| Parallel tests collide on ports | Children share a fixed port | Non-web demo or dynamic ports |
| Cleanup failure doesn't alter OS code | Exit generator read before destroy | Explicit cleanup before computing code |
| App receives `SIGKILL` yet test expects `@PreDestroy` | Force kill skips shutdown hooks | Separate force-kill recovery tests |

### 14.1. Diagnostic checklist

1. Does the test actually spawn a child process, or just call `main` in the same JVM?
2. Does `mvn verify` execute `ExitProcessIT` and produce a failsafe report?
3. Is the JAR at the right path, version, and module?
4. Does the process command split arguments separately without bogus quotes?
5. Is the Java executable from JDK 21?
6. Is the child colliding on ports/resources outside the JVM?
7. Could full stdout/stderr pipes cause a deadlock?
8. Does `waitFor` have a deadline and timeout failure?
9. Does the test clean up the child in `finally`?
10. Are both the real exit code and business markers asserted?
11. Does `@PreDestroy` execute before the context-closed message?
12. When logs show non-zero, does `System.exit` actually deliver that code to the OS?
13. If cleanup fails, is there an explicit result before `SpringApplication.exit`?
14. Are any secrets written to test logs?
15. Is recovery tested when the process is killed abruptly?

## 15. Exercises and self-check questions

1. Why can a JUnit test calling `ExitChildApplication.main` terminate the Surefire JVM?
2. Distinguish business outcome, Spring exit-code calculation, and OS exit status.
3. When is `System.exit(17)` valid?
4. Why does `SpringApplication.exit(context)` not replace `System.exit(code)` for a CLI needing OS exit codes?
5. Why should `System.exit` live in the outermost `main` rather than in a runner or `@PreDestroy`?
6. In the demo, why does `@PreDestroy` execute before `MAIN contextClosed`?
7. If cleanup fails after `getExitCode()`, is the code guaranteed to change?
8. Why should `JobOutcome.fromFlags` mapping be unit-tested separately?
9. Why must `ExitProcessIT` run after `package`?
10. Distinguish Maven Surefire from Failsafe.
11. Does `mvn clean test` execute `ExitProcessIT`?
12. Does `mvn clean verify` build the JAR before testing OS exit codes?
13. Why does `ProcessBuilder` with an argument list avoid failures on paths containing spaces?
14. What is the advantage of selecting the Java executable from `System.getProperty("java.home")`?
15. In tests, why must `exitValue()` be read after `waitFor`?
16. Why avoid `Thread.sleep(2000)` to wait for a child process?
17. When can an unbounded `waitFor()` hang indefinitely?
18. Why shouldn't you read stdout only after `waitFor()` while keeping default pipes?
19. What is the trade-off of `redirectErrorStream(true)`?
20. What does `@TempDir` solve when multiple tests run?
21. If a child exceeds 30s, what must the test do to avoid leaving orphan processes?
22. Does `destroyForcibly()` guarantee instantaneous process termination?
23. Why does an exit code from a forced kill not mean the app called `System.exit(code)` itself?
24. If a child spawns grandchild processes, how do you verify process tree cleanup?
25. Write a new test for a `--permission-error` option returning code `13`.
26. Why avoid asserting Spring Boot timestamps/banners?
27. If `ApplicationRunner` throws an exception before `run` returns the context, what differs?
28. How do you test file operation cleanup failures without harming the host filesystem?
29. How should CI archive failsafe reports and child logs when a test fails?
30. Propose a testing workflow combining pure unit tests, Spring context tests, and packaged-JAR child integration tests.

**Success criteria:** the Java 21/Spring Boot 3.3 CLI app returns codes `0`, `2`, `17`; `mvn clean verify` runs three unit tests and three process integration tests; the JUnit JVM is never killed by the child's `System.exit`; tests never deadlock on output pipes, enforce timeouts, clean up processes, and assert on real OS exit codes.

## 16. References

- Spring Boot 3.3.13 — `SpringApplication.exit`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3 — Application Exit, `ExitCodeGenerator`: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Maven Plugin Packaging: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Maven Failsafe — `integration-test`/`verify`: https://maven.apache.org/surefire/maven-failsafe-plugin/index.html
- Maven Failsafe — Usage: https://maven.apache.org/surefire/maven-failsafe-plugin/usage.html
- Java 21 — `ProcessBuilder`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessBuilder.html
- Java 21 — `Process.waitFor(timeout)`, `exitValue()`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Process.html
- Java 21 — `ProcessHandle`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.html
- JUnit Jupiter — `@TempDir`: https://junit.org/junit5/docs/current/user-guide/#writing-tests-built-in-extensions-TempDirectory
