# Process Exit Codes and Their Meaning to the Shell or Orchestrator

A **process exit code (exit status)** is a number that a **process** sends to the operating system when it terminates. Shells, CI/CD tools, service managers, Docker, and Kubernetes can read this result to decide whether a run **succeeded, failed, needs a retry, or requires an alert**.

With Spring Boot, it is especially important to distinguish between the **business outcome inside the application**, **`SpringApplication.exit(context)`**, **`System.exit(code)`**, and the **code actually observed by the parent process**. An application can log an error and still return `0`; conversely, a process can be stopped by the infrastructure and return a non-zero code even though business code never threw an exception.

This lesson belongs to the **Exit Codes** chapter of the **Spring Boot Application Runtime** module, focusing on the meaning of exit codes to the **shell and orchestrator**, and applies to **Spring Boot 3.3.x, Java 17+, Bash, PowerShell, Docker, and Kubernetes**.

After this lesson, you will be able to:

- Explain why `0` conventionally indicates success and non-zero codes indicate an unsuccessful outcome according to shell conventions.
- Distinguish between "closing the `ApplicationContext`" and "terminating the JVM and passing the exit status."
- Implement `ExitCodeGenerator` to return job status to the shell.
- Observe and test the actual exit status using `$?` (Bash), `$LASTEXITCODE` (PowerShell), and container tools.
- Analyze codes `1`, `7`, `126`, `127`, `130`, `137`, and `143` accurately without guessing the root cause from a single number.
- Design a Kubernetes **Job/CronJob** differently from a **Deployment**, understanding `restartPolicy` and `CrashLoopBackOff`.
- Avoid losing error codes through shell wrappers, pipelines, Gradle/Maven, or catching exceptions and exiting normally.
- Establish consistent retry, logging, and exit code policies for operational systems.

## 1. Exit codes sit at the boundary between processes

Imagine a Spring Boot batch program that receives a file, processes it, and terminates:

~~~text
Shell / CI runner / Container runtime / Kubernetes
                       |
                       | start process
                       v
               Java Virtual Machine
                       |
                       v
               Spring Boot context
                       |
               +-------+--------+
               |                |
               v                v
          Job succeeds      Job fails
               |                |
               v                v
          exit code 0    non-zero exit code
               |                |
               +-------+--------+
                       |
                       v
                 JVM terminates
                       |
                       v
              OS records exit status
                       |
                       v
         Shell/Container runtime observes
                       |
              +--------+--------+
              |                 |
          continue         report error / retry /
          pipeline         fail Job / alert
~~~

The result is passed **across the process boundary**. An `int` stored in a Spring bean, or an `ERROR` log line, **does not automatically become an exit status**. The process must actually terminate and the runner must receive that code.

### Core conventions

| Exit status | Common interpretation | What can be inferred? |
| --- | --- | --- |
| `0` | Success by shell convention | The process self-reported successful completion; does not guarantee all business data is valid if the application misreports |
| Non-zero | Failure by shell convention | Must check the code against the **application contract** and process state |
| `1` | Commonly used for a general error | Does not mean "always necessarily a Java error" |
| `2`, `3`, `7`… | May be application-defined | Must look up the application's code table; do not guess |
| `126` | Commonly used by Bash when a command is found but not executable | May be a shell error, not a Spring Boot business outcome |
| `127` | Commonly used by Bash when a command is not found | Java/JAR/script may not have been invoked at all |
| `128 + N` | Commonly used by Bash when a command is terminated by signal `N` | Does not prove whether the application called `System.exit(128+N)` itself |

In Unix environments, the exit status visible to the shell typically falls within the **0–255** range. On other platforms, the representation and system codes may differ. **Do not build a business contract relying on large or negative codes assuming every OS will pass them through intact.**

## 2. Three layers of state that must be kept separate

For a Spring Boot application, there are at least three layers:

1. **Business outcome:** for example, 500 records processed, 5 malformed records, or file not found. This may be a Java object or a database record.
2. **Result of `SpringApplication.exit(context)`:** Spring Boot closes the context and calculates the code according to the applicable `ExitCodeGenerator` instances.
3. **Java process exit code:** what the JVM sends to the OS upon termination, typically via `System.exit(code)` or another process termination path.

### Calls that are not equivalent

~~~java
context.close();
~~~

Only closes the container according to the Spring contract; **does not automatically send a custom exit status to the shell**.

~~~java
int code = SpringApplication.exit(context);
~~~

Closes the context and **returns an integer** reflecting the result from Spring Boot's exit code mechanism. However, **it does not invoke `System.exit` itself**.

~~~java
System.exit(code);
~~~

Requests the **entire JVM** to terminate with the supplied exit code. This is the step that makes the shell or process supervisor receive the code directly from the process.

The common pattern for a self-terminating CLI/batch application:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

int code = SpringApplication.exit(context);
System.exit(code);
~~~

This is **illustrative code**, requiring a `MyApplication` class and appropriate imports. A full runnable example is in section 7.

**Warning:** do not call `System.exit(...)` from an HTTP controller or a business method just to report "this request failed." It will terminate the **entire JVM**, affecting all other requests and tasks. An HTTP status is the error-reporting mechanism for a single request; a process exit code is the status of the **entire process**.

## 3. What does `SpringApplication.exit(context)` do in Spring Boot 3.3?

According to the Spring Boot **3.3.13** API:

~~~java
int code = SpringApplication.exit(
        applicationContext,
        exitCodeGenerator1,
        exitCodeGenerator2);
~~~

The `exit(ApplicationContext, ExitCodeGenerator...)` method:

- Collects codes from `ExitCodeGenerator` arguments passed directly and from **Spring beans** implementing `ExitCodeGenerator`.
- Following the sorted order of generators, takes the **first non-zero code**; if there is no non-zero code, the success result is typically `0`.
- Supports `Ordered` or `@Order` to control selection priority when multiple sources exist.
- Closes the `ApplicationContext` when possible, so Spring executes the necessary lifecycle callbacks.
- **Returns the code** to the caller without forcing the JVM to exit itself.

The `ExitCodeGenerator` interface is simple:

~~~java
package org.springframework.boot;

@FunctionalInterface
public interface ExitCodeGenerator {
    int getExitCode();
}
~~~

This is a **simplified signature for learning purposes**, not the full source/Javadoc. It can be implemented via a class, lambda, or bean:

~~~java
@Bean
ExitCodeGenerator exitCodeGenerator() {
    return () -> 7;
}
~~~

The snippet above belongs in a Spring configuration class, requiring imports for `@Bean` and `ExitCodeGenerator`; it only illustrates a generator that always returns `7`. In a real application, the code should reflect the **actual work outcome**.

### A common misconception

If you only call:

~~~java
int code = SpringApplication.exit(context);
System.out.println("Calculated code = " + code);
~~~

and let `main` return normally **without calling `System.exit(code)`**, the shell may receive `0` even though `code` is `7`. A Java `int code` variable is not automatically passed to the OS.

Conversely, calling directly:

~~~java
System.exit(7);
~~~

can make the shell receive `7` even without `ExitCodeGenerator`. However, by bypassing `SpringApplication.exit`, you do not use the code calculation mechanism from Spring beans, and closing the context during JVM shutdown depends on the shutdown hook still being active.

## 4. Where can `ExitCodeGenerator` be placed?

### As a bean

~~~java
@Bean
ExitCodeGenerator operationOutcome(OperationResult result) {
    return result::getExitCode;
}
~~~

This is a fragment assuming `OperationResult` is an existing bean with a `getExitCode()` method. Spring Boot reads the generator when `SpringApplication.exit(...)` is called.

### Passed directly to `exit`

~~~java
int code = SpringApplication.exit(
        context, () -> calculationWasValid ? 0 : 7);
~~~

`calculationWasValid` is a boolean variable determined earlier in code, not necessarily a bean. This approach is useful for CLIs whose result is already available directly in `main`.

### When multiple generators exist

Suppose:

~~~text
Generator A (high priority): 0
Generator B (next priority): 7
Generator C (low priority): 4
~~~

By Spring Boot's contract, the **first non-zero code** after sorting is used: in this example, `7`. Do not assume "largest code wins," "last code wins," or "Spring sums all codes."

If outcome sources can conflict, designing **a single component that aggregates business outcomes** and emits one exit code per a clear policy is usually easier to maintain than relying on multiple generators.

## 5. Startup failures: `ExitCodeGenerator` on exceptions and `ExitCodeExceptionMapper`

When startup encounters an exception, Spring Boot has a mechanism to obtain an exit code from an exception implementing `ExitCodeGenerator` or from a matching `ExitCodeExceptionMapper`.

Example of an exception carrying a code:

~~~java
public final class InvalidInputException
        extends RuntimeException implements ExitCodeGenerator {

    public InvalidInputException(String message) {
        super(message);
    }

    @Override
    public int getExitCode() {
        return 4;
    }
}
~~~

This is an illustrative class in a Spring Boot project, requiring an import for `org.springframework.boot.ExitCodeGenerator`. In real code, an exception may be wrapped in another exception by the framework; you must test the entire cause chain on the **exact Spring Boot version**.

`ExitCodeExceptionMapper` is a strategy for mapping a `Throwable` to a code:

~~~java
@Bean
ExitCodeExceptionMapper exitCodeExceptionMapper() {
    return error -> {
        if (error instanceof InvalidInputException) {
            return 4;
        }
        return 0;
    };
}
~~~

This is a fragment inside a Spring configuration class that has `InvalidInputException`, requiring imports for `@Bean` and `ExitCodeExceptionMapper`. For errors occurring **before the mapper bean is created**, this bean may not yet be available; you cannot guarantee every earliest infrastructure failure will be mapped as desired.

**Important distinction:** the batch example in section 7 intentionally **does not throw an exception**, instead storing the business outcome in a bean for `SpringApplication.exit(context)` to read. That way, both success and failure flows are clearly described and reproduced without depending on exception-handling internals inside `SpringApplication.run`.

### `ExitCodeEvent`

Spring Boot also has `ExitCodeEvent`, published when an exit code is determined via `ExitCodeGenerator` in the appropriate processing paths. This event provides `getExitCode()` to observe the determined code; it **does not replace `System.exit` itself**.

Do not treat seeing `ExitCodeEvent` in logs as proof that the OS received the same code: you must check the status of the **actual Java process**.

## 6. Exit code conventions for batch applications

Spring Boot **does not require** applications to assign global meanings to codes such as `2`, `4`, or `7`. Your team should define its own code table and apply it consistently.

An illustrative convention:

| Code | Application-defined meaning | Desired handling |
| --- | --- | --- |
| `0` | Completed all work per success criteria | Do not retry |
| `2` | Malformed input syntax or missing arguments | Report configuration error; usually do not retry identical input |
| `3` | Invalid business data, unprocessable | Send to DLQ/mark failed, do not retry indefinitely |
| `4` | Missing or invalid required configuration or secret | Requires configuration fix |
| `7` | Job failed per business outcome | Decide whether to retry or investigate depending on error nature |
| `10` | External dependency temporarily unavailable | Bounded retry with backoff/jitter |
| `11` | Internal timeout exceeded | Check downstream and timeouts |
| `12` | Resource/quota error | Inspect capacity and limits |

**This is an example code table proposed by this lesson, not a standard defined by Spring Boot or Linux.** In production, document each code along with its owner and retryability.

In particular, **non-zero does not mean "retry forever."** A malformed file remains malformed after 100 runs. The orchestrator needs a retry policy classified by error type, not just an infinite loop.

## 7. Runnable example: Spring Boot CLI returning an exit code to the OS

Create a **Spring Boot 3.3.13 + Java 17 + Gradle** console application. The example has two modes:

- Without `--fail` argument: job succeeds, code `0`.
- With `--fail` argument: job intentionally marks a business failure, code `7`.

There is a `@PreDestroy` bean to observe that `SpringApplication.exit(context)` closes the context **before** the process returns the code to the OS.

### 7.1. Directory structure

~~~text
exit-code-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/exitcode/
    └── ExitCodeDemoApplication.java
~~~

### 7.2. `settings.gradle`

~~~groovy
rootProject.name = 'exit-code-demo'
~~~

### 7.3. `build.gradle`

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
    // Manage versions for starters and Jakarta Annotations using the BOM.
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)

    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'jakarta.annotation:jakarta.annotation-api'
}
~~~

**Dependency note:** applying only the `org.springframework.boot` plugin without dependency management/BOM means starters without explicit versions **may fail to resolve**. The example declares the **Gradle native BOM** so it runs standalone. Requires JDK 17+ and a Gradle version compatible with Spring Boot 3.3.

### 7.4. `ExitCodeDemoApplication.java`

~~~java
package com.example.exitcode;

import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PreDestroy;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ExitCodeDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ExitCodeDemoApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        ConfigurableApplicationContext context = application.run(args);

        // Compute the code from the ExitCodeGenerator bean and close the context.
        int code = SpringApplication.exit(context);
        System.out.println("PROCESS exitCode=" + code);

        // Pass this code to the JVM/OS, rather than keeping it only in a Java variable.
        System.exit(code);
    }

    @Bean
    JobResult jobResult() {
        return new JobResult();
    }

    @Bean
    ExitCodeGenerator jobExitCodeGenerator(JobResult result) {
        return result::getExitCode;
    }

    @Bean
    ApplicationRunner runJob(JobResult result) {
        return args -> {
            if (args.containsOption("fail")) {
                result.markFailed(7);
                System.out.println("JOB result=FAILED");
            } else {
                System.out.println("JOB result=SUCCESS");
            }
        };
    }

    @Bean
    CleanupMarker cleanupMarker() {
        return new CleanupMarker();
    }

    static final class JobResult {
        private final AtomicInteger exitCode = new AtomicInteger(0);

        int getExitCode() {
            return exitCode.get();
        }

        void markFailed(int code) {
            exitCode.set(code);
        }
    }

    static final class CleanupMarker {
        @PreDestroy
        void cleanup() {
            System.out.println("CONTEXT cleanup");
        }
    }
}
~~~

Notable points in this pattern:

1. `WebApplicationType.NONE`: the application does not need Tomcat or an HTTP port; suitable for jobs with a clear termination point.
2. `ApplicationRunner` runs **before `SpringApplication.run(args)` returns** on the successful startup path.
3. The runner updates `JobResult`. Because `JobResult` is a context-managed singleton, the `ExitCodeGenerator` bean reads the right code after the runner finishes.
4. `SpringApplication.exit(context)` retrieves the code from the generator and closes the context.
5. `@PreDestroy` on `CleanupMarker` prints the cleanup marker during context closure.
6. `System.exit(code)` forwards the code out of the JVM.
7. `AtomicInteger` here only keeps state representation simple; in this synchronous runner example, complex concurrency is unnecessary. In a real job, you must await all mandatory tasks **before deciding the code**.

**Important:** `--fail` in the demo is an option used to simulate a **business outcome failure**, not an exception. This means Spring Boot can still complete startup and publish `ApplicationReadyEvent` before `main` calls exit. Do not treat the ready event as the final report for a batch job's outcome.

### 7.5. Build

If the project directory has a compatible Gradle Wrapper:

~~~bash
./gradlew clean bootJar
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat clean bootJar
~~~

If no wrapper has been generated yet but compatible Gradle is installed:

~~~bash
gradle clean bootJar
~~~

With `rootProject.name` and `version` as above, the JAR name is typically:

~~~text
build/libs/exit-code-demo-1.0.0.jar
~~~

The actual name may differ if build configuration is customized; verify the generated artifact.

### 7.6. Successful run

In Bash, from the project directory:

~~~bash
java -jar build/libs/exit-code-demo-1.0.0.jar
echo "JAVA_EXIT=$?"
~~~

The lines **printed via `System.out.println` by the demo Java program** on the success path are:

~~~text
JOB result=SUCCESS
CONTEXT cleanup
PROCESS exitCode=0
~~~

Then Bash prints:

~~~text
JAVA_EXIT=0
~~~

This is not necessarily the **entire stdout/stderr**, as Spring Boot or the runner may emit other logs. Compare the demo's markers in order.

### 7.7. Business failure run

Using **a new Java process**:

~~~bash
java -jar build/libs/exit-code-demo-1.0.0.jar --fail
echo "JAVA_EXIT=$?"
~~~

The demo's lines:

~~~text
JOB result=FAILED
CONTEXT cleanup
PROCESS exitCode=7
~~~

Bash then prints:

~~~text
JAVA_EXIT=7
~~~

Key result: **the process actually exits with code `7`**, not just printing the word "FAILED".

On this execution path, `@PreDestroy` was invoked via `SpringApplication.exit(context)` and the context closed before `System.exit(7)`. If the JVM is forcibly killed, there is no guarantee similar callbacks will complete.

### 7.8. Why shouldn't you use only Gradle `bootRun` to measure the code?

Running:

~~~bash
./gradlew bootRun --args="--fail"
~~~

may cause the Gradle `bootRun` task to **fail** because the Java process exited non-zero. However, the exit code of the **Gradle wrapper/Gradle process** seen by the shell **is not a contract guaranteeing preservation of the exact child JVM code `7`**. The build tool may translate the error into its own exit code, along with a stack trace.

To accurately test the process exit code, prefer:

~~~bash
java -jar build/libs/exit-code-demo-1.0.0.jar --fail
~~~

and read the status **immediately after the Java command**. The same applies when running via a Maven plugin, IDE, service wrapper, or an outer script: always ask **which process** is being observed by the shell/CI.

## 8. Bash: reading `$?` and controlling scripts

In Bash, `$?` holds the exit status of the **most recently completed command/pipeline**. For example:

~~~bash
java -jar build/libs/exit-code-demo-1.0.0.jar --fail
status=$?
printf 'java exit=%s\n' "$status"
~~~

**You must save `$?` immediately.** If you run another command before reading it, you may be reading the code of `echo`, `printf`, or `grep` instead of Java's code.

### Branching inside `if`

~~~bash
if java -jar build/libs/exit-code-demo-1.0.0.jar --fail; then
    echo "JOB SUCCEEDED"
else
    status=$?
    echo "JOB FAILED with exit=$status"
fi
~~~

The `else` branch reads `$?` right after Java fails. If `set -e` is enabled, a standalone non-zero command can terminate the script **before** reaching the line that saves the status. Placing the command in an `if` condition is a clear way to handle non-zero intentionally.

### Propagating errors from an outer wrapper script

If the script decides it must report the same code:

~~~bash
#!/usr/bin/env bash
if java -jar build/libs/exit-code-demo-1.0.0.jar --fail; then
    exit 0
else
    status=$?
    exit "$status"
fi
~~~

This script can be invoked by CI. If Java returns `7`, the script returns `7`; if Java succeeds, the script returns `0`.

### Pipelines with `tee` can mask Java's code

For example:

~~~bash
java -jar build/libs/exit-code-demo-1.0.0.jar --fail | tee app.log
echo "$?"
~~~

Under default Bash rules, the status of the pipeline above is typically the status of the **last command `tee`**. If `tee` succeeds, the script may print `0` **even though Java returned `7`**.

In Bash, enable:

~~~bash
set -o pipefail
java -jar build/libs/exit-code-demo-1.0.0.jar --fail 2>&1 | tee app.log
status=$?
printf 'pipeline status=%s\n' "$status"
~~~

If Java is the only failing component and `tee` succeeds, the pipeline will return Java's non-zero code. **`pipefail` is a Bash feature**, not available by default in every `/bin/sh`. If you need to analyze the status **of each stage** when multiple commands can fail, use Bash's `PIPESTATUS` mechanism or an explicitly designed wrapper script.

### `&&` and `||`

~~~bash
java -jar build/libs/exit-code-demo-1.0.0.jar &&
    echo "Next stage can run"
~~~

With exit code `0`, the next command runs. With non-zero, the branch after `&&` is skipped.

~~~bash
java -jar build/libs/exit-code-demo-1.0.0.jar --fail ||
    echo "Job failed; investigate"
~~~

The `||` handles the error, but if the script ends with a successful `echo`, the **final exit status of the script can become `0`**. If you want CI to detect the failure, you must `exit` with the appropriate code after logging.

## 9. PowerShell and Windows: reading the right status type

In **PowerShell**, after invoking a native program like `java.exe`, the exit code is stored in `$LASTEXITCODE`:

~~~powershell
java -jar .\build\libs\exit-code-demo-1.0.0.jar --fail
$code = $LASTEXITCODE
Write-Output "JAVA_EXIT=$code"
~~~

Expected output if the demo runs properly:

~~~text
JAVA_EXIT=7
~~~

**Do not confuse PowerShell's `$?` with Bash's `$?`**. In PowerShell, `$?` typically indicates **success/failure of the PowerShell operation as a Boolean** per shell version semantics, not an exact copy of code `7`. When you need the numeric process exit status, use **`$LASTEXITCODE`**.

To test:

~~~powershell
java -jar .\build\libs\exit-code-demo-1.0.0.jar --fail
$code = $LASTEXITCODE
if ($code -ne 7) {
    throw "Expected exit 7 but got $code"
}
Write-Output "PASS exit code 7"
~~~

In **Windows Command Prompt (cmd.exe)**, the status is typically read via `ERRORLEVEL`:

~~~bat
java -jar build\libs\exit-code-demo-1.0.0.jar --fail
echo JAVA_EXIT=%ERRORLEVEL%
~~~

The snippet above is an interactive cmd example; in batch files with command blocks/variable expansion quirks, check the expansion timing of `%ERRORLEVEL%`.

**Warning:** Windows and Linux differ in code ranges and how the OS represents signals. The `128+signal` table is a Bash/Unix convention and **does not translate verbatim into a meaning table for all Windows codes**.

## 10. Docker: container exit codes can differ from JVM codes if a wrapper handles them wrongly

In containers, the platform observes the **main container process**. If the JVM is run directly using exec-form:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY build/libs/exit-code-demo-1.0.0.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

and the image is built from the sample artifact, runtime arguments are passed to Java:

~~~bash
docker run --rm exit-code-demo:local --fail
echo "CONTAINER_EXIT=$?"
~~~

If the image is named `exit-code-demo:local` (built locally), the Docker CLI normally returns the container process status on the happy path of the `docker run` command itself; when Java exits `7`, you expect to see the corresponding non-zero code. However, distinguish **Docker CLI/daemon/image startup errors** from errors where the JVM actually ran. In monitoring environments, prefer reading the **container termination state** rather than relying solely on a wrapper's output.

### Shell wrappers must preserve status

If the image runs a script:

~~~sh
#!/bin/sh
exec java -jar /app/app.jar "$@"
~~~

`exec` replaces the shell with the Java process, helping signals and exit codes reach the main process cleanly. `"$@"` forwards all caller arguments intact.

A wrapper that easily loses the code:

~~~sh
#!/bin/sh
java -jar /app/app.jar "$@"
echo "Java finished"
~~~

The last command of the script is `echo`. If Java returns `7` but `echo` succeeds, the script can exit with `0`. This misleads the container/CI into thinking the job succeeded.

If you need to log after Java:

~~~sh
#!/bin/sh
java -jar /app/app.jar "$@"
status=$?
echo "Java finished with $status"
exit "$status"
~~~

This is an intentional wrapper path; also account for signal forwarding to the child process when the shell acts as PID 1. For production containers, **exec-form ENTRYPOINT or a script using `exec`** usually simplifies signal management.

## 11. Kubernetes: how are exit codes used?

Kubernetes manages containers according to the **Pod lifecycle** and `restartPolicy`. Two contexts have distinctly different semantics:

### A. Deployment — long-running service processes

A Deployment typically uses Pods with `restartPolicy: Always`. When a container terminates, the kubelet attempts to restart the container according to policy, **even when the exit code is `0`**.

~~~text
Deployment / web application
   |
   +-- Process 0: exits cleanly
   |       -> restarted due to restartPolicy Always
   |
   +-- Process 7: exits with business failure
   |       -> restarted due to restartPolicy Always
   |
   +-- Process killed / liveness failure
           -> kubelet may restart
~~~

Key takeaway: **code `0` does not mean a Deployment will not restart**. A web service whose `main` exits after a few seconds while deployed as a Deployment may restart continuously, not because business code returned an error.

If restarts happen consecutively, Kubernetes may show **`CrashLoopBackOff`** with increasing backoff delays. This **is not an exit code** and does not identify the root cause by itself.

### B. Job/CronJob — processes with a finite lifecycle

A Job aims to complete a unit of work. Normally:

- Exit code `0` from the main container is treated as a signal of successful completion of that container run.
- A non-zero exit code usually indicates an unsuccessful run.
- Kubernetes may retry according to `restartPolicy` and the Job's policy until success or failure criteria are met.
- A CronJob creates Jobs on a schedule; the Job's status reflects the success/failure of the scheduled work, not merely whether a Pod ever reached Running.

### Job example

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: exit-code-demo-job
spec:
  backoffLimit: 2
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: batch
          image: registry.example.com/demo/exit-code-demo:1.0.0
          args: ["--fail"]
~~~

This is a **sample manifest** using a placeholder image for illustration; a real image must be built/pushed with an `ENTRYPOINT` running the example JAR. With `--fail`, Java returns `7`. Because `restartPolicy: Never`, the failed Pod's container is not restarted inside that same Pod by policy; the **Job controller may create a retry Pod** per `backoffLimit` and Job logic. After exhausting retry budget per policy, the Job is marked Failed.

If `--fail` is omitted and no other error occurs, Java returns `0`; the Job can reach Succeeded once the Job's completion conditions are satisfied.

**Do not equate `backoffLimit: 2` with "guaranteed to create exactly two Pods and then stop"** in every scenario. Retry/backoff calculations, parallelism, and infrastructure failures affect the actual number of launches; consult the Job documentation for your cluster version.

### `restartPolicy` at the Pod level

| Policy | Exit `0` | Non-zero exit |
| --- | --- | --- |
| `Always` | Restart | Restart |
| `OnFailure` | Do not restart because container finished successfully | Restart the failing container |
| `Never` | Do not restart this container | Do not restart this container |

These rules represent the basic Pod container model per Kubernetes documentation; sidecar specifics, init containers, and restart policies in newer cluster versions may require separate handling.

The **Job controller** also implements higher-level Pod creation/failure counting logic. Therefore, saying "`restartPolicy: Never` means the Job will not retry" is **false**: it only states that the kubelet does not restart **the container inside that Pod**; the controller can still create new Pods.

## 12. Codes `130`, `137`, `143`: do not hard-bind a single cause

In Bash/Unix environments, when a process **is terminated by signal number `N`**, Bash typically reports status **`128 + N`**.

| Commonly observed code | Calculation in Bash | Possible interpretation |
| --- | --- | --- |
| `130` | `128 + 2` | `SIGINT`, often from Ctrl+C |
| `137` | `128 + 9` | `SIGKILL`, could be OOM kill or forced kill |
| `143` | `128 + 15` | `SIGTERM`, could be from a normal stop request |
| `1` | Not a signal code by this formula | Could be a general error from app/JVM/launcher |
| `7` | Not a signal code by this formula | Could be defined by the application itself |

**Do not conclude every `137` = OOM.** An administrator might use `kill -9`, or the orchestrator might send `SIGKILL` after exceeding the grace period. To distinguish, inspect `reason: OOMKilled`, Pod events, memory metrics, kernel/container logs, and shutdown timestamps.

**Do not conclude every `143` = application bug.** A process may receive `SIGTERM` due to a rolling deployment or normal scale-down. The JVM might also handle the signal, run hooks, and return a different code itself. Actual status depends on the runtime and how the process terminated.

And **you cannot determine with certainty from the number alone that a signal was received**: an application can intentionally call `System.exit(143)`. You must corroborate with `signal`, `reason`, logs, and controller activity.

### Shutdown hooks do not guarantee exit code 0

In Spring Boot, the `ApplicationContext` is normally closed during graceful JVM shutdown via a shutdown hook. However, `@PreDestroy` running completely only proves that part of cleanup executed; **the exit code still depends on how the JVM was told to exit and the actual outcome of the process**.

If a container receives `SIGTERM` followed by `SIGKILL` due to timeout, the final result may be `137` regardless of whether some callbacks had started. You must coordinate Spring's timeout, Kubernetes grace period, and actual drain time.

## 13. Reading the real code from Kubernetes

Suppose a Pod is named `my-batch-pod` in namespace `jobs`:

~~~bash
kubectl get pod my-batch-pod -n jobs -o wide
kubectl describe pod my-batch-pod -n jobs
kubectl logs my-batch-pod -n jobs --container=batch
~~~

For a terminated container, you can read the code directly in the `terminated` state:

~~~bash
kubectl get pod my-batch-pod -n jobs \
  -o jsonpath='{.status.containerStatuses[0].state.terminated.exitCode}'
~~~

If the container has restarted and is currently running, the previous run's code may be found at:

~~~bash
kubectl get pod my-batch-pod -n jobs \
  -o jsonpath='{.status.containerStatuses[0].lastState.terminated.exitCode}'
~~~

The two `jsonpath` expressions above assume the first container in `containerStatuses` is the one under investigation; in multi-container Pods, **do not assume index 0 is always the container you want**. Read `name` or filter by name when implementing monitoring scripts.

Also inspect `reason`, `message`, `startedAt`, `finishedAt`, and restart count. For example:

~~~text
state.terminated.exitCode = 137
state.terminated.reason   = OOMKilled
~~~

This is an **illustrative pair of values**, not status retrieved from an active cluster. If you actually observe `OOMKilled` alongside code `137`, investigating memory limits and memory usage is far better grounded than inferring from `137` alone.

For a Job, inspect:

~~~bash
kubectl get job exit-code-demo-job -n jobs
kubectl describe job exit-code-demo-job -n jobs
~~~

The overall Job status (`Succeeded`/`Failed`) and a single container's exit code are **two different levels**. A Job may have gone through multiple Pods or retries before reaching its final outcome.

## 14. Exit codes and readiness/liveness are not the same

| Signal | When does it occur? | Who consumes it? |
| --- | --- | --- |
| HTTP status `200` / `500` | When an HTTP request completes | HTTP client, gateway |
| `ReadinessState` / readiness probe | While the process is still running | Traffic routing system |
| `LivenessState` / liveness probe | While the process is still running | Kubelet/health recovery |
| `ApplicationReadyEvent` | After Spring Boot runners | Code inside the JVM knowing startup milestone |
| Process exit code | When the process terminates | Shell, CI, OS, container runtime, Job controller |
| Job status | After container/Pod runs per policy | Kubernetes Job/CronJob, workflow controller |

An HTTP endpoint returning `500` **does not mean the JVM must exit `1`**. A failing readiness probe **does not automatically become an exit code**; if a liveness failure causes the kubelet to restart the container, the process may terminate afterward via its own mechanism.

Conversely, the CLI program example in section 7 can publish `ApplicationReadyEvent`, yet the runner logged `JOB result=FAILED`. Afterward, `SpringApplication.exit(context)` resolves code `7` and the JVM returns non-zero. **Successful startup is not proof that a batch job succeeded.**

For long-running web applications, process exit codes should not be used to communicate individual request outcomes. For batch applications with finite lifecycles, exit codes are very well suited as the **final contract** between the job and the scheduler.

## 15. How should CI/CD and workflow engines handle codes?

A pipeline typically wants to stop when a job fails:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

java -jar build/libs/exit-code-demo-1.0.0.jar
echo "Next stage: publish results"
~~~

If Java returns `0`, the next stage runs; if Java returns non-zero, `set -e` in a standard simple-command situation causes the script to fail. However, `set -e` has many exceptions involving `if`, `while`, `&&`/`||`, and subshells; when handling retries, explicitly capture the status rather than relying on every implicit shell nuance.

If a job fails and may be retried:

~~~bash
#!/usr/bin/env bash
attempt=1
while [ "$attempt" -le 3 ]; do
    if java -jar build/libs/exit-code-demo-1.0.0.jar --fail; then
        echo "Succeeded"
        exit 0
    else
        status=$?
        echo "Attempt $attempt failed with $status"
    fi
    attempt=$((attempt + 1))
done
exit "$status"
~~~

This illustrative script **intentionally always passes `--fail`**, so the job fails all three times; it demonstrates how to propagate the code, **not how to retry a recoverable failure**. Production needs error classification and backoff/jitter, not endless retries of a deterministic input error.

### Classifying retries by code

| Error group | Example code | Should auto-retry? |
| --- | --- | --- |
| Success | `0` | No |
| Permanent bad input | `2` or `3` | Usually no |
| Bad secret/config | `4` | No until configuration is fixed |
| Transient network error | `10` | Bounded, if work is idempotent |
| Transient timeout | `11` | Evaluate cause and attempt count |
| `SIGTERM` due to scale-down | Possibly `143` or another code | Do not assume it is a business failure needing rerun |
| `SIGKILL`/OOM | Possibly `137` | Investigate memory/grace before retrying |

This is an **example policy**, not a universal contract. Kubernetes `restartPolicy: OnFailure` uses simple non-zero→restart logic; if you need to distinguish permanent vs recoverable errors by code, use an appropriate Job/controller policy or put decision logic in the workflow per cluster-supported features.

## 16. Exit codes and exceptions: do not silently turn failure into `0`

An easy mistake to make:

~~~java
try {
    processFile();
} catch (Exception ex) {
    log.error("Job failed", ex);
}
// main returns normally; the shell may receive 0!
~~~

This is a fragment within a program that already has `processFile`/`log`, not standalone source. An `ERROR` log is not automatically interpreted by the OS as an exit status.

There are three appropriate approaches depending on the scenario:

1. **Let the exception propagate to startup-failure handling**, while configuring the exit code when needed; verify the status from a real process.
2. **Catch the error, record the outcome state**, let `ExitCodeGenerator` return a non-zero code as in the demo, and call `System.exit(code)`.
3. **Catch the error and choose the status directly**, after controlled cleanup, if the CLI application does not need Spring's exit-code mechanism.

Do not both swallow the exception and `return` normally if the scheduler/CI needs to detect failures. Nor should you call `System.exit` from a low-level repository or service layer; deciding when to terminate is the responsibility of the **process lifecycle orchestration layer**.

### Concurrent errors after startup

If `main` has returned and a background thread throws an exception, the JVM **does not necessarily exit non-zero automatically**: other threads may keep running. When writing batches with executors/async tasks, you need to:

- Await `Future`/`CompletableFuture`/job completion with timeouts.
- Capture asynchronous errors and fold them into the final outcome.
- Do not let `main` finish or call `SpringApplication.exit` before mandatory tasks complete.
- Design cancellation and shutdown when one task fails.

A stack trace printed by a worker thread is not automatically the exit code of the entire process.

## 17. Preserving exit codes across Dockerfile and entrypoint

### Good: run Java as the main process

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY build/libs/exit-code-demo-1.0.0.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Runtime arguments like `--fail` are passed to Java `main`. Stop signals reach the Java process more cleanly.

### Good when a wrapper is needed: `exec`

~~~sh
#!/bin/sh
echo "Starting batch JVM"
exec java -jar /app/app.jar "$@"
~~~

Because `exec` replaces the shell with Java, Java's code determines the main process status.

### Error-prone: discarding Java's code

~~~sh
#!/bin/sh
java -jar /app/app.jar "$@"
echo "Finished"
~~~

The wrapper ends with `echo`; without explicitly calling `exit "$status"`, a failure result can turn into `0`.

### Error-prone: backgrounding Java and letting the wrapper exit

~~~sh
#!/bin/sh
java -jar /app/app.jar "$@" &
echo "Started Java in background"
~~~

If the shell as PID 1 exits, the container lifecycle can terminate while the child Java process is still unfinished, without a valid outcome code. If you truly need to manage multiple processes, use an appropriate init/supervisor and handle `wait`, signals, and exit statuses deliberately.

## 18. Common operational failures and how to diagnose them

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Console prints `FAILED` but CI is green | Only logged, did not return non-zero | `System.exit`/`SpringApplication.exit`, shell status, wrapper script |
| `SpringApplication.exit` returns `7` but shell receives `0` | Code not passed to the JVM | Was `System.exit(code)` called? |
| Running `bootRun` returns `1` instead of `7` | That is the Gradle task/process code | Verify directly with `java -jar` |
| Using `tee` and pipeline receives `0` | `pipefail` not enabled or reading final stage status | `set -o pipefail`, save status immediately |
| PowerShell prints `True` instead of `7` | Using `$?` as if in Bash | Use `$LASTEXITCODE` |
| Cmd processes status wrongly | `ERRORLEVEL` overwritten by another command | Read/copy immediately after `java` |
| Docker exits `0` despite Java returning `7` | Shell entrypoint logs and exits `0` | Use exec form or `exit "$status"` |
| Pod restarts after exit `0` | Pod belongs to a Deployment with `restartPolicy: Always` | Check workload type and Pod spec |
| Job fails with code `7` and retries | `backoffLimit`/restart policy | Check Job controller, Pod history |
| `CrashLoopBackOff` treated as an exit code | Confusing status/backoff with exit status | Inspect `lastState.terminated.exitCode` |
| Seeing `137` and immediately concluding OOM | `SIGKILL` has multiple causes | `reason=OOMKilled`, kernel/memory metrics, grace timeout |
| Seeing `143` and filing an app bug | Pod may have received a normal `SIGTERM` | Scale-down/rollout reason, signal, shutdown logs |
| Web app returns HTTP `500` while process exits `0` | HTTP and process are two independent layers | Inspect HTTP metrics, liveness/restarts separately |
| An async worker throws an exception, JVM stays alive | Error not folded into process outcome | Await futures, exception handler, supervisor |
| Exit code differs between Windows and Linux | Different OS/shell/process wrapper | Standardize environment and code ranges |
| `@PreDestroy` does not run | `SIGKILL`, hook disabled, object outside container | Distinguish forced kill from Spring lifecycle bug |
| Job succeeds but data is not committed | Reported success before transaction/durable write | Return `0` only after verified completion criteria |

## 19. What should be monitored in production?

A minimal dashboard or runbook should correlate:

- **Integer exit code** and **exit reason** from container/runtime, not just the Pod phase name.
- **Workload kind:** Deployment, StatefulSet, Job, CronJob; each has different semantics.
- **Container name** and restart count, since a Pod may have multiple containers.
- **Start/finish timestamps**, image version, commit, and command line with sensitive data redacted.
- **Root-cause error logs** from the application, along with correlation/job ID.
- **`OOMKilled`, memory/CPU, termination grace**, signals, and liveness/readiness events.
- **Retry/backoff count**, final Job outcome, and volume of work processed.
- **Separate business outcomes**: count of succeeded/failed records, checksums, transaction commits, or checkpoints.
- **Cleanup duration**, stop/destroy callbacks, and number of still-running tasks.

Do not retain secrets, passwords, tokens, or command lines containing credentials in diagnostic logs. Exit codes are short and safe signals to aggregate, but require context to infer root causes.

## 20. Investigation workflow when a Job is Failed

1. **Identify the workload:** is this a Job/CronJob or a Deployment? What are the Job's `restartPolicy` and `backoffLimit`?
2. **Select the right Pod/container:** inspect current state and previous state if restarts occurred.
3. **Read `exitCode` + `reason` + timestamps:** code `7` could be a business failure, `137` could be KILL/OOM, `143` could be TERM.
4. **Read logs for the right run:** for a restarting Pod, consider `kubectl logs --previous` if the container still exists and has a prior run.
5. **Cross-reference the application's code convention:** what does `7` mean in the current code/version?
6. **Check wrappers:** is Java really the main PID, does the script forward status, is a pipeline/Gradle masking the code?
7. **Find the root cause:** input, config, dependency, transaction, memory, timeout, signal, pod eviction.
8. **Decide conditional retry:** input errors should not retry indefinitely; transient errors need backoff/jitter and idempotency.
9. **Fix and verify:** rerun on safe test input, checking both OS code and business outcome.
10. **Add regression tests:** prevent failure codes from accidentally turning into `0` later.

### Exit codes are not the whole story

Sometimes a job processes 99% successfully and returns `0`, while business criteria require **100%** completion. Conversely, a job may return non-zero even though part of the data already committed, requiring care to avoid duplicate reruns. Therefore, you must define **success criteria** and idempotency/checkpoint policies based on real data; the exit code is only a concise summary for the orchestrator to act upon.

## 21. Repeatable verification exercises

### Exercise A — Verify exit `0`

~~~bash
java -jar build/libs/exit-code-demo-1.0.0.jar
status=$?
test "$status" -eq 0
echo "PASS: zero exit"
~~~

### Exercise B — Verify exit `7`

~~~bash
java -jar build/libs/exit-code-demo-1.0.0.jar --fail
status=$?
test "$status" -eq 7
echo "PASS: business failure exit 7"
~~~

The two snippets above are suitable when running in an interactive shell **without `set -e` enabled**. If a script uses `set -e`, place the Java command inside `if` and inspect the status intentionally so non-zero does not abort the script before the verification step.

### Exercise C — Prove logs are not exit status

Temporarily **remove the `System.exit(code)` line** in the demo source, rebuild, and run the `--fail` branch. The code may print `PROCESS exitCode=7`, yet when `main` returns normally and the JVM has no remaining non-daemon threads, the shell may receive `0`. Restore `System.exit(code)` after experimenting.

Do not use this incorrect variant in CI or production.

### Exercise D — Prove `tee` masks failures

~~~bash
java -jar build/libs/exit-code-demo-1.0.0.jar --fail | tee failed.log
echo "pipeline=$?"
~~~

In default Bash, you may see `pipeline=0`. Run again on **a new Java process**:

~~~bash
set -o pipefail
java -jar build/libs/exit-code-demo-1.0.0.jar --fail | tee failed.log
echo "pipeline=$?"
~~~

If `tee` succeeds and Java returns `7`, the pipeline under `pipefail` will return `7`. If other commands also fail, inspect per-stage statuses; do not assume pipeline status always equals Java's status.

### Exercise E — Inspect a Job

Deploy the sample Job manifest using a **real test image**, then:

~~~bash
kubectl get jobs
kubectl get pods
kubectl describe job exit-code-demo-job
~~~

Compare the container status and the Job status. Do not use a production cluster or real input just to simulate `--fail`; do not create a failing Job with unbounded retries.

## 22. Self-check questions

1. **Is an exit code the status of an HTTP request or of a process?** Of a process.
2. **By Bash convention, what does `0` usually mean?** The command/process succeeded.
3. **Does `SpringApplication.exit(context)` call `System.exit` itself?** No.
4. **How do you pass the code from `ExitCodeGenerator` to the shell?** `System.exit(SpringApplication.exit(context))` or equivalent steps.
5. **If a runner logs `ERROR` and `main` finishes normally, will the shell definitely receive non-zero?** No.
6. **When multiple `ExitCodeGenerator` instances yield different results, what rule does Spring Boot use?** The first non-zero code in the sorted order of generators.
7. **How do you control generator ordering?** `Ordered` or `@Order`.
8. **In Bash, what reads the status?** `$?`, immediately after the command to check.
9. **In PowerShell, what reads Java's numeric status?** `$LASTEXITCODE`.
10. **In cmd.exe, what do you read?** `ERRORLEVEL`.
11. **Why can the pipeline `java ... | tee` easily make CI report a false green?** The default pipeline status usually comes from the last command `tee`.
12. **How do you preserve non-zero through a Bash pipeline?** Use `set -o pipefail` and handle the status intentionally.
13. **Does `Gradle bootRun` guarantee the shell receives the exact child JVM code `7`?** No; the shell receives the Gradle process code.
14. **Does `restartPolicy: Always` restart after exit `0`?** Yes.
15. **Does `restartPolicy: Never` on a Job mean the Job controller will not retry?** No; it can create new Pods per Job policy.
16. **Is `137` definitely an OOM?** No; check `reason` and metrics.
17. **Is `143` definitely an application bug?** No; it could be `SIGTERM` during normal shutdown.
18. **Is `CrashLoopBackOff` a numeric exit code?** No; it is a status/backoff caused by repeated restarts.
19. **Does `ApplicationReadyEvent` guarantee a batch job completed its business work successfully?** No.
20. **Does HTTP `500` mean the JVM returns exit `1`?** No.
21. **Does an exception in a background thread automatically make the JVM exit non-zero?** Not necessarily.
22. **When should a job return `0`?** After business completion criteria have been verified, not merely because the context started successfully.
23. **Why shouldn't `System.exit` be inside an HTTP handler?** Because it stops the entire JVM, not just that request.
24. **When retrying a failed job, should every non-zero code be retried infinitely?** No; classify permanent vs transient errors, bound retries, and ensure idempotency.

**Conclusion:** Process exit codes are the **contract between the application and external systems**. In Spring Boot, `ExitCodeGenerator` and `SpringApplication.exit(context)` determine the code from the work outcome and close the context; `System.exit(code)` forwards the code to the JVM/OS. Shells read `$?` or `$LASTEXITCODE`; Docker and Kubernetes read the process/container termination state and apply restarts/retries by workload kind. To operate reliably, **preserve codes through wrappers, do not guess root causes from 137/143, distinguish Jobs from Deployments, and test actual process exit codes rather than checking logs alone**.

### References

- Spring Boot 3.3.13 — **SpringApplication: Application Exit** (`ExitCodeGenerator`, `System.exit`, generator ordering): https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — **`SpringApplication.exit` API**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3.13 — **`ExitCodeGenerator` API**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeGenerator.html
- Spring Boot 3.3.13 — **`ExitCodeExceptionMapper` API**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeExceptionMapper.html
- Spring Boot 3.3.13 — **`ExitCodeEvent` API**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeEvent.html
- GNU Bash Reference Manual — **Exit Status** (0/non-zero, 128+signal, 126/127): https://www.gnu.org/software/bash/manual/html_node/Exit-Status.html
- GNU Bash Reference Manual — **Pipelines** (last pipeline status and `pipefail`): https://www.gnu.org/software/bash/manual/html_node/Pipelines.html
- Kubernetes — **Pod Lifecycle**, container restart policy, `CrashLoopBackOff`: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/
- Kubernetes — **Jobs** (retry, `backoffLimit`, Pod failure): https://kubernetes.io/docs/concepts/workloads/controllers/job/
- Kubernetes — **CronJob**: https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/
- Docker — **Dockerfile ENTRYPOINT** (exec form vs shell form): https://docs.docker.com/reference/dockerfile/#entrypoint
