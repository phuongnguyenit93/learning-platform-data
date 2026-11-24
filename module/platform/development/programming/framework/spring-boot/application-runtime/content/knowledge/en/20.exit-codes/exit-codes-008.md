# Designing One-Shot Jobs: Success, Input Errors, and Execution Errors

A Spring Boot program does not have to be a continuously running HTTP server. It can be a **one-shot job**: triggered by a shell, CI/CD, cron, Kubernetes Job, or orchestrator, receiving arguments, processing a unit of work, releasing resources, and **terminating the JVM with an exit code that reflects the real outcome**.

Examples include data imports, syncing an order batch, running a migration step, reindexing, exporting reports, or validating configurations. For these tasks, a log line saying "Completed" is insufficient: shells and job controllers typically rely on the **process exit code** to judge success or failure.

This lesson designs three clear outcomes:

| Outcome | Condition | Illustrative exit code |
|---|---|---|
| Success | Valid input; processing completed; required results verified | `0` |
| Input error | Missing/wrong/invalid arguments; work should not start | `2` |
| Execution error | Valid input, yet runtime error, timeout, or commit failure occurred | `10` |

**Codes `2` and `10` are conventions of this example, not mandatory standard codes of Spring Boot.** Each system can establish a different contract, provided it documents the meanings, exact codes, and corresponding retry policies.

The main example uses **Java 17+ and Spring Boot 3.3.x**. Key topics include `ApplicationRunner`, `ApplicationArguments`, `ExitCodeGenerator`, `SpringApplication.exit(...)`, `System.exit(...)`, testing real exit codes, and handling failures outside the normal run flow.

## 1. Distinguishing process exit code from application state

An **exit code** is the integer received by the OS or process supervisor when a process terminates. By Unix convention, `0` usually means success, and non-zero usually means failure. For Unix shells, there are exit-status range limits and signal-based code conventions; for smooth integration, small non-negative codes are typically chosen.

The signals below do not automatically substitute for process exit status:

- `HTTP 200` or `HTTP 500` is the outcome of **one request**, not the entire job.
- `ApplicationContext.isActive()` only indicates whether the context is active.
- `ApplicationReadyEvent` is a Spring Boot startup milestone; it does not prove business data was durably committed.
- Printing `EXIT_CODE=10` to logs **does not make the OS receive code 10** if the JVM ultimately exits normally with 0.
- Catching an exception without recording an outcome can make a job **fail while the process reports 0**.
- `SpringApplication.exit(context)` fetches the exit code and closes the context; distinguish it from `System.exit(code)`, which instructs the JVM to exit with that code.

Expected contract:

~~~text
Start
   |
   v
Parse + validate arguments
   |
   +--- missing/wrong ----> INPUT_ERROR (code 2)
   |
   v
Execute business logic
   |
   +--- error ----------> EXECUTION_ERROR (code 10)
   |
   v
Confirm outcome/commit
   |
   +--- completed -----> SUCCESS (code 0)
   |
   v
Close resources / ApplicationContext
   |
   v
OS receives exit code
~~~

You must **determine the final outcome before passing the code to the OS**. If a worker is still running in the background, never equate "submitted task successfully" with "processed completely."

## 2. Why is ApplicationRunner well suited for one-shot jobs?

Spring Boot invokes `ApplicationRunner` and `CommandLineRunner` beans **after `ApplicationContext` refresh**, yet **before `SpringApplication.run(...)` completes**. This is the ideal point to run business logic needing injected Spring beans such as datasources, HTTP clients, repositories, or transaction services.

Simplified flow:

~~~text
main(String[] args)
    |
    +-- SpringApplication.run(args)
    |        |
    |        +-- Load bean definitions
    |        +-- Create/inject singleton beans
    |        +-- Refresh ApplicationContext
    |        +-- Call ApplicationRunner.run(ApplicationArguments)
    |                    |
    |                    +-- Validate arguments
    |                    +-- Execute job
    |                    +-- Save outcome
    |
    +-- SpringApplication.exit(context)
    |        |
    |        +-- Read ExitCodeGenerator bean
    |        +-- Close context and destroy beans
    |
    +-- System.exit(exitCode)
             |
             +-- Shell / Kubernetes / CI sees status
~~~

For batch tasks not serving HTTP requests, set `WebApplicationType.NONE` so no web server keeps the process alive unnecessarily. Use a web environment only when the job genuinely requires an HTTP endpoint and you have explicitly designed when it terminates.

Do not run heavy imports or migrations inside constructors or `@PostConstruct`: those are bean creation callbacks, not a good place to coordinate outcomes, classify error codes, or handle one-shot execution after configuration finishes.

### ApplicationArguments vs raw String[]

`ApplicationRunner.run(ApplicationArguments args)` receives an interface allowing you to read:

| API | Meaning |
|---|---|
| `getSourceArgs()` | All raw arguments |
| `getOptionNames()` | Option names, e.g., `count` |
| `containsOption("flag")` | Whether a flag/option is present |
| `getOptionValues("count")` | List of option values, or `null` if absent |
| `getNonOptionArgs()` | Positional non-option arguments |

For example, `--count=3 --dry-run report.csv`: `count` and `dry-run` are options, `report.csv` is a non-option arg. For options carrying values, use `--count=3`; do not assume `--count 3` parses identically.

`getOptionValues("count")` has three states to distinguish:

~~~text
Missing --count                  -> null
Present --count with no value    -> []
Present --count=3                -> ["3"]
Present --count=3 --count=4      -> ["3", "4"]
~~~

Depending on the contract, a repeated option may be valid or an error. The example below requires **exactly one** `count` value.

## 3. Input error and execution error conventions

Do not lump every exception into one single code:

| Example | Suggested category | Why? |
|---|---|---|
| Missing `--count` | Input error | Cannot run without the parameter |
| `--count=abc` | Input error | Wrong data type |
| `--count=0` when valid range is 1–1000 | Input error | Violates business constraint |
| Passing two `--count` flags | Input error | Ambiguous which value to use |
| Disallowed unknown option | Input error | Violates job interface |
| Database timeout during processing | Execution error | Input may be completely valid |
| I/O error while writing output | Execution error | Task failed at runtime |
| Transaction commit failed | Execution error | Result not durably completed |
| Bug causing `NullPointerException` | Execution/internal failure | Should not blame operators wrongly |

Boundaries may differ by application. For instance, `--input=/missing.csv` detected before processing may be classified as an input error; the same file deleted mid-run is an execution failure. Document the decision rather than automatically grouping every `IOException` together.

**Retry policies differ too:** input errors usually require **fixing input**, whereas execution failures may be transient or permanent. Retrying code 10 is only safe when the business logic supports idempotency, timeouts, backoff, and bounded attempts.

## 4. Runnable Spring Boot example: codes 0, 2, and 10

The following program sums integers from 1 to `count`. The `--fail-execution` flag intentionally makes the task fail after the first item. All operations in this demo occur **in memory**, requiring no database, files, or HTTP services so outcomes are easily verifiable.

### 4.1 Project structure

~~~text
one-shot-job/
├── build.gradle
└── src/
    └── main/
        ├── java/com/example/oneshot/OneShotJobApplication.java
        └── resources/application.properties
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.1.0'

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

springBoot {
    mainClass = 'com.example.oneshot.OneShotJobApplication'
}

tasks.named('bootJar') {
    archiveFileName = 'one-shot-job.jar'
}
~~~

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=one-shot-job
logging.level.root=WARN
~~~

The purpose of `WARN` log level in the example is reducing noise to observe lines printed by the program. Production needs fuller logging for execution errors along with correlation/job IDs.

### 4.2 Complete Java file

Create `src/main/java/com/example/oneshot/OneShotJobApplication.java`:

~~~java
package com.example.oneshot;

import java.util.List;
import java.util.Set;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OneShotJobApplication {

    private static final int SUCCESS = 0;
    private static final int INVALID_INPUT = 2;
    private static final int EXECUTION_ERROR = 10;

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(OneShotJobApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);

        // run() invokes runners before returning ApplicationContext.
        ConfigurableApplicationContext context =
                application.run(args);

        // Close context and read code from the ExitCodeGenerator bean.
        int exitCode = SpringApplication.exit(context);
        System.out.println("EXIT_CODE=" + exitCode);

        // Return code to the operating system / process supervisor.
        System.exit(exitCode);
    }

    @Bean
    JobOutcome jobOutcome() {
        return new JobOutcome();
    }

    @Bean
    ApplicationRunner oneShotJob(JobOutcome outcome) {
        return args -> {
            try {
                JobOptions options = parseOptions(args);
                long checksum = execute(options);

                outcome.record(SUCCESS);
                System.out.println(
                        "SUCCESS items=" + options.count()
                                + " checksum=" + checksum);
            } catch (InvalidInputException ex) {
                outcome.record(INVALID_INPUT);
                System.err.println(
                        "INPUT_ERROR: " + ex.getMessage());
            } catch (RuntimeException ex) {
                outcome.record(EXECUTION_ERROR);
                System.err.println(
                        "EXECUTION_ERROR: " + ex.getMessage());
            }
        };
    }

    private static JobOptions parseOptions(
            ApplicationArguments args) {

        Set<String> supported =
                Set.of("count", "fail-execution");

        if (!args.getNonOptionArgs().isEmpty()) {
            throw new InvalidInputException(
                    "positional arguments are not supported");
        }

        for (String name : args.getOptionNames()) {
            if (!supported.contains(name)) {
                throw new InvalidInputException(
                        "unknown option --" + name);
            }
        }

        List<String> values = args.getOptionValues("count");
        if (values == null || values.size() != 1
                || values.get(0).isBlank()) {
            throw new InvalidInputException(
                    "expected exactly one --count=<1..1000>");
        }

        final int count;
        try {
            count = Integer.parseInt(values.get(0));
        } catch (NumberFormatException ex) {
            throw new InvalidInputException(
                    "--count must be an integer");
        }

        if (count < 1 || count > 1000) {
            throw new InvalidInputException(
                    "--count must be in [1,1000]");
        }

        boolean simulateFailure =
                args.containsOption("fail-execution");

        if (simulateFailure
                && !args.getOptionValues(
                        "fail-execution").isEmpty()) {
            throw new InvalidInputException(
                    "--fail-execution does not accept a value");
        }

        return new JobOptions(count, simulateFailure);
    }

    private static long execute(JobOptions options) {
        long checksum = 0;

        for (int item = 1; item <= options.count(); item++) {
            checksum += item;

            if (options.simulateFailure() && item == 1) {
                throw new IllegalStateException(
                        "simulated failure after item 1");
            }
        }

        return checksum;
    }

    private record JobOptions(
            int count, boolean simulateFailure) {
    }

    public static final class JobOutcome
            implements ExitCodeGenerator {

        // Do not default to success if the runner has not reported an outcome.
        private volatile int code = EXECUTION_ERROR;

        void record(int code) {
            this.code = code;
        }

        @Override
        public int getExitCode() {
            return code;
        }
    }

    private static final class InvalidInputException
            extends RuntimeException {

        InvalidInputException(String message) {
            super(message);
        }
    }
}
~~~

### 4.3 Explaining the code mechanics

**Spring Application setup**

`application.setWebApplicationType(WebApplicationType.NONE)` prevents creating an HTTP server for a batch task. `application.run(args)` initializes the container and invokes `ApplicationRunner`.

**Input validation**

`parseOptions(...)` rejects unknown options, positional arguments, missing or repeated counts, blank values, non-numeric values, and out-of-range values. When validation fails, `execute(...)` is never called. This is an important choice to avoid side effects before confirming valid input.

**Execution**

`execute(...)` processes items and calculates the checksum. `--fail-execution` is a flag simulating an execution error **after processing starts**, cleanly separating business execution failures from input failures.

**Outcome**

The `JobOutcome` bean implements `ExitCodeGenerator`. `SpringApplication.exit(context)` inspects generator beans, retrieves the recorded outcome, and closes the context. `volatile` suffices for this synchronous example; switching to async work requires separate completion and visibility control.

**Process exit**

Only `main()` calls `System.exit(exitCode)`. Never terminate the JVM directly inside the runner, which would skip outcome reading and intentional context closure.

**Exception handling**

Catching `RuntimeException` in the example maps demo execution errors to code 10. In production, log stack traces and controlled diagnostic data rather than just one message; never catch `Throwable` and hide fatal JVM errors.

**Note:** because the runner caught the error and returned normally, Spring Boot may publish `ApplicationReadyEvent` just like a successful startup, even when the business outcome is 2 or 10. This program **serves no traffic and exits immediately afterward**, making that a valid way to express batch outcomes. Do not use this pattern for long-running web services where readiness must reflect failures.

### 4.4 Build and run via JAR

With JDK 17+ and a project containing the Gradle wrapper:

~~~bash
./gradlew bootJar
java -jar build/libs/one-shot-job.jar --count=3
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootJar
java -jar .\build\libs\one-shot-job.jar --count=3
~~~

If there is no Gradle wrapper yet, install or generate a compatible wrapper. Because this is a Spring Boot project, you cannot run `javac OneShotJobApplication.java` standalone without Spring Boot/Spring Framework on the classpath.

**Running the JAR directly matters more than relying solely on `bootRun` when testing exact exit codes**, because Gradle is a process wrapper that may report its own task-failure status without guaranteeing preservation of the 2/10 values returned by your program.

## 5. Verification results for all three cases

### 5.1 Success

~~~bash
java -jar build/libs/one-shot-job.jar --count=3
echo $?
~~~

Lines printed by the program on **stdout**:

~~~text
SUCCESS items=3 checksum=6
EXIT_CODE=0
~~~

The value of `echo $?` on a Unix shell must be **`0`** when run directly and completing normally. The sum `1+2+3=6` is deterministic with no external dependencies.

### 5.2 Input error

~~~bash
java -jar build/libs/one-shot-job.jar --count=abc
echo $?
~~~

Line printed by the program on **stderr**:

~~~text
INPUT_ERROR: --count must be an integer
~~~

Line printed on **stdout**:

~~~text
EXIT_CODE=2
~~~

Actual exit status is **`2`**. `execute(...)` never runs, because the error was caught right during parsing. Other bad inputs in this same category:

| Arguments | Reason |
|---|---|
| Omit `--count` | Missing parameter |
| `--count` | Missing value |
| `--count=0` or `--count=1001` | Outside range 1–1000 |
| `--count=3 --count=4` | Duplicate option |
| `--count=3 input.csv` | Positional arguments unsupported |
| `--count=3 --other=yes` | Unknown option |
| `--count=3 --fail-execution=yes` | Flag does not take a value |

### 5.3 Execution error

~~~bash
java -jar build/libs/one-shot-job.jar --count=3 --fail-execution
echo $?
~~~

Line on **stderr**:

~~~text
EXECUTION_ERROR: simulated failure after item 1
~~~

Line on **stdout**:

~~~text
EXIT_CODE=10
~~~

The shell receives **`10`**. Input `--count=3` is valid, yet the task failed after the first item. This demo writes no external data; in a real job, **partial side effects may already have occurred** before the error. Therefore, retries must rely on transactions, checkpoints, and idempotency.

**Do not rely on stdout/stderr interleaving order** if the console or CI merges both streams: they may be buffered separately. Use process status to verify the outcome.

### 5.4 Windows PowerShell

~~~powershell
java -jar .\build\libs\one-shot-job.jar --count=3
$LASTEXITCODE

java -jar .\build\libs\one-shot-job.jar --count=abc
$LASTEXITCODE

java -jar .\build\libs\one-shot-job.jar --count=3 --fail-execution
$LASTEXITCODE
~~~

The three expected values are `0`, `2`, and `10` respectively. `$LASTEXITCODE` must be read immediately after each native process to avoid reading the status of another command.

## 6. Why are SpringApplication.exit and System.exit both needed?

Snippet from the example:

~~~java
ConfigurableApplicationContext context =
        application.run(args);

int exitCode = SpringApplication.exit(context);
System.exit(exitCode);
~~~

This is code inside `main` with `application` and appropriate imports. The last two statements perform two distinct jobs:

| API | Function |
|---|---|
| `SpringApplication.exit(context)` | Queries `ExitCodeGenerator`, computes exit code, closes context if possible, returns an integer |
| `System.exit(exitCode)` | Requests the JVM to terminate with that code so the OS/launcher observes it |

If you only call `SpringApplication.exit(context)` and print the code, the process may not return that exact code to the OS. Conversely, if `System.exit(0)` is called before the job finishes or before the outcome is updated, the orchestrator may receive a **false success**.

### What about multiple ExitCodeGenerators?

Spring Boot supports `ExitCodeGenerator` beans as well as generators passed directly to `SpringApplication.exit(context, ...)`. When multiple generators exist, Boot picks the **first non-zero code** in applied order; `Ordered` or `@Order` can control that order.

For simple batches, keep **one unified outcome source**. If multiple layers jointly decide the exit code, establish transparent priority rules—for example, execution failures outranking warnings—rather than letting one bean accidentally overwrite another's outcome.

`JobOutcome` in the example starts at `EXECUTION_ERROR=10` to avoid self-reporting success if the runner has not recorded a result yet. However, if Spring Boot fails too early before the runner/context finishes, startup exception handling must still be addressed separately.

## 7. An alternative: letting exceptions escape and mapping errors

The main example uses `Outcome` to handle all three scenarios deterministically. Yet Spring Boot also allows:

- Exceptions implementing `ExitCodeGenerator`.
- `ExitCodeExceptionMapper` beans mapping exceptions to exit codes during startup failure handling.

A **separate illustrative class**, not integrated into the program in section 4:

~~~java
import org.springframework.boot.ExitCodeGenerator;

public final class InvalidArgumentsFailure
        extends RuntimeException
        implements ExitCodeGenerator {

    public InvalidArgumentsFailure(String message) {
        super(message);
    }

    @Override
    public int getExitCode() {
        return 2;
    }
}
~~~

If this exception is thrown at a phase that Spring Boot handles as startup failure, the framework can read the code from `getExitCode()`. In addition, an `ExitCodeExceptionMapper` bean can inspect the exception type/cause chain and return an appropriate code.

Example **illustrative factory method** placed in a configuration class with required imports:

~~~java
@Bean
ExitCodeExceptionMapper exitCodeExceptionMapper() {
    return exception -> {
        // Example contract: unclassified errors map to code 10.
        return 10;
    };
}
~~~

**Caution:** if an error happens very early before the context creates mapper beans, mappers may not exist. Never treat a mapper bean as a universal handler for all JVM failures.

### Two models differ in lifecycle behavior

| Design | When runner fails | How Spring Boot sees it | How exit code is obtained |
|---|---|---|---|
| **Record Outcome** as in example | Catch error, record 2/10, return normally | Runner completes; startup proceeds | `SpringApplication.exit(context)` after `run` |
| **Throw exception** | Exception escapes runner | `SpringApplication.run` may fail; `ApplicationFailedEvent` | Boot startup-failure handling and available generators/mappers |

If `SpringApplication.run(...)` throws an exception before returning a context, **never write logic assuming a context was returned from `run` to call `SpringApplication.exit(context)` on the next line**.

For one-shot jobs with no web traffic, the Record Outcome model is usually easier to test deterministically for process exit. For long-running services, the throw-on-failure model may fit better because readiness and startup events must reflect failure.

## 8. Bootstrap failures differ from job input errors

A one-shot job can fail **before `ApplicationRunner` is ever called**:

- A bean cannot be created due to missing dependencies or bad configuration.
- Unreadable config, secrets, or connection pool initialization failure.
- Classpath errors or unsupported Java runtime.
- Spring context refresh fails.

In these cases, `JobOutcome` may not yet exist or be updated; do not assume every bootstrap error automatically yields code 10 from the example. Design a dedicated startup-failure policy and test with a **real JVM launch**.

Suggested classification:

~~~text
Bootstrap failure
    -> technical/startup failure handling

Valid Spring context + invalid job arguments
    -> input error (2)

Valid context + valid arguments + failed job
    -> execution error (10)

Valid context + job completed
    -> success (0)
~~~

If you want to standardize startup failures as code 20 as well, design handling for cases before the context even has mapper beans; never catch all exceptions in `main` and unconditionally call `System.exit(0)`.

## 9. True success must mean completion, not merely "submitted"

A dangerous bug:

~~~java
@Async
public void importAsync() {
    // Work taking several minutes.
}

@Bean
ApplicationRunner runner(ImportService service) {
    return args -> service.importAsync();
}
~~~

These are **two illustrative snippets**, requiring `ImportService`, `@EnableAsync`, and proper bean declarations; not standalone runnable code.

When the async proxy is active, the runner can return **immediately upon submission**, before the import actually processes or commits. If `main` calls exit 0, the OS receives success while the background task is still incomplete.

The proper approach is awaiting completion with an explicit timeout:

~~~java
CompletableFuture<ImportResult> future =
        importService.importAsync();

ImportResult result =
        future.get(timeoutSeconds, TimeUnit.SECONDS);
~~~

This is an illustrative snippet inside a service where the types and variables are already declared. Production also needs handling for `InterruptedException`, `ExecutionException`, `TimeoutException`, cancellation, and rollback/compensation.

**Success must rest on the business contract**, for example:

1. Input is valid.
2. Required items were processed.
3. Transactions/outputs committed or published successfully.
4. Necessary acks/checkpoints were durably persisted.
5. No mandatory tasks remain unawaited.
6. Only then record code `0`.

A method returning without throwing an exception does not prove those steps completed if it swallowed errors, returned an incomplete future, or only enqueued an in-memory message.

## 10. Retries: avoid turning execution errors into duplicate data

Suppose a job processes 1,000 records yet fails after record 600. Code 10 states that the **job failed**; it does not tell you whether records 1–599 were persisted.

Situations to distinguish:

| Failure point | Side effects possible? | What should retry do? |
|---|---|---|
| Argument parsing | Not yet, if validated before execution | Fix input; usually do not retry identical request |
| Mid-processing | Yes | Inspect checkpoints, transactions, idempotency |
| After commit but before OS gets code 0 | May already have succeeded in business terms | Reconcile durable state; avoid duplicate runs |
| JVM killed by `SIGKILL` or `OOMKilled` | Insufficient info from 0/2/10 alone | Recover using persisted job state |

For jobs with side effects, establish:

- Stable **job IDs** to identify runs and retries.
- **Idempotency keys** for operations at risk of repetition.
- **Checkpoints/offsets** durably saved after completed steps.
- Proper **transaction boundaries** and ack/commit semantics.
- **Bounded retries with backoff**, distinguishing transient vs permanent errors.
- **Metrics/logs** recording processed counts and failure stages.

An in-JVM `ConcurrentHashMap` cannot replace durable state when containers can restart. If a transaction committed yet the JVM died before reporting success, the retry must be able to detect that the result already exists.

## 11. Using exit codes in shells and CI

POSIX shell:

~~~bash
java -jar build/libs/one-shot-job.jar --count=3
status=$?

if [ "$status" -eq 0 ]; then
    echo "batch succeeded"
elif [ "$status" -eq 2 ]; then
    echo "invalid arguments: change input"
else
    echo "execution/startup failure: investigate"
fi
~~~

Save `$?` **immediately after the Java command**; any subsequent command overwrites it.

In shell scripts using `set -e`, a command returning non-zero can abort the script before you inspect the code. Use `if command; then ... else ... fi` or deliberate error control instead of adding `|| true` to mask every failure.

Example:

~~~bash
if java -jar build/libs/one-shot-job.jar --count=abc; then
    echo "success"
else
    code=$?
    echo "job failed with code=$code"
fi
~~~

In PowerShell:

~~~powershell
java -jar .\build\libs\one-shot-job.jar --count=abc
$code = $LASTEXITCODE

if ($code -eq 2) {
    Write-Host "Input error - fix arguments"
}
~~~

Do not rely on the word "SUCCESS" in logs. Pipelines must check the **child process status**, not the exit code of a wrapper or a trailing `echo` command.

## 12. Kubernetes Jobs: Succeeded and Failed Pods

A one-shot Spring Boot batch can run as a Kubernetes Job:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: one-shot-demo
spec:
  backoffLimit: 2
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: app
          image: example.invalid/one-shot-job:demo
          args: ["--count=3"]
~~~

This is an **illustrative** manifest; `example.invalid/...` is a placeholder requiring a real image before deployment.

Under standard Job/Pod mechanics:

- Container exits with code 0: the run counts as successful completion.
- Container exits non-zero: the Job may record a failure and retry per `backoffLimit`, `restartPolicy`, and other policies.
- `restartPolicy: Never` does not mean **the Job won't retry**; the controller can create a new Pod.
- `--count=abc` is an input error; retrying the identical bad input will keep failing until the job spec is fixed.
- Platform terminations like `OOMKilled`/`SIGKILL` do not necessarily produce application codes 0/2/10.

To orchestrate based on specific codes, Kubernetes offers features like `podFailurePolicy` in supporting environments/versions. Still, **the exit code is only a signal**: the orchestrator must be configured not to retry invalid-input codes, or to retry only errors deemed transient.

A CronJob can create Jobs at multiple times, so it does not by itself guarantee cluster-wide exactly-once business execution. Idempotency, job keys, and concurrency policies remain necessary.

## 13. Testing exit codes accurately

There are at least two levels:

### A. Logic unit tests

Verify the input parser and processing logic:

- `--count=3` is valid.
- Missing `--count`, value-less `--count`, `--count=abc`, `--count=0`, and `--count=1001` all fail.
- Repeated counts and unknown options are rejected.
- `--fail-execution` is a flag rejecting values.
- `execute(...)` computes `checksum=6` for count 3.
- `--fail-execution` produces an execution error, not an input error.
- Validation finishes before any side effects occur.

### B. Process-level integration tests

Run **real `java -jar` commands**:

1. `--count=3` → exit 0.
2. `--count=abc` → exit 2.
3. `--count=3 --fail-execution` → exit 10.
4. Set a timeout on the child process to prevent hanging tests.
5. Correlate stdout/stderr with actual process status.
6. Verify the context closes resources after the run finishes.
7. Run under the same Java version, launcher, and OS as production when possible.

Example using Java 17 `ProcessBuilder` (an illustrative snippet inside a test class with imports):

~~~java
Process child = new ProcessBuilder(
        "java", "-jar",
        "build/libs/one-shot-job.jar", "--count=3")
        .inheritIO()
        .start();

boolean finished = child.waitFor(30, TimeUnit.SECONDS);
if (!finished) {
    child.destroyForcibly();
    throw new IllegalStateException("job timed out");
}
if (child.exitValue() != 0) {
    throw new AssertionError(
            "Unexpected exit code: " + child.exitValue());
}
~~~

This snippet requires `import java.util.concurrent.TimeUnit;` and a built JAR. **Never invoke `main()` containing `System.exit(...)` directly inside the same JVM running JUnit tests**, as it can terminate the test runner process itself. For unit testing, separate parsing/execution/exit-code calculation; for testing OS status, use a subprocess.

## 14. Cleanup and forced termination errors

`SpringApplication.exit(context)` closes the Spring context on the intentional exit path, giving beans with destroy callbacks a chance to release resources. However, some incidents bypass this path:

- `SpringApplication.run(...)` throws an error before returning a context.
- The process receives `SIGKILL` or the container exceeds its termination grace period.
- The JVM crashes or the host loses power.
- An I/O thread hangs or cleanup is cut short.
- Remote side effects already happened, yet the app never received the response.

Therefore, `@PreDestroy` and `finally` are essential yet **cannot be the sole guarantee of exactly-once execution**. Real tasks need durable state, retry/idempotency, and resume/reconciliation capabilities.

Never put `System.exit(0)` in a global exception handler to "exit cleanly" when a job fails. That sends a false success to the OS, leaving CI/Job controllers unable to detect the failure.

## 15. Common mistakes

**Mistake 1 — "The runner was invoked, so the job definitely succeeded."** False. A runner can throw, catch an error, or merely submit unfinished async work.

**Mistake 2 — "Logging the error code is enough."** False. A non-zero process exit status is required.

**Mistake 3 — "`SpringApplication.exit(context)` terminates the JVM itself."** No. It returns the code and closes the context; `System.exit(code)` instructs the JVM to exit with that status.

**Mistake 4 — "Catching an Exception makes Spring Boot automatically mark failure."** Not if the runner returns normally. You must record the outcome or throw an exception per contract.

**Mistake 5 — "Input errors and execution errors can share code 2."** Makes operations hard because one requires fixing input while the other may warrant retrying.

**Mistake 6 — "Every non-zero error should be retried immediately."** Invalid inputs rarely heal themselves; execution errors require assessing transient vs permanent causes and idempotency.

**Mistake 7 — "An unfinished `CompletableFuture` can still report success."** No. You must await and verify the outcome within a timeout.

**Mistake 8 — "Having an `ExitCodeGenerator` bean gives every early startup failure a custom code."** Not guaranteed. Exceptions can occur before the bean is even created.

**Mistake 9 — "Using Gradle `bootRun` reliably verifies exact Java codes 2/10."** Not guaranteed, as Gradle is a process wrapper; run the JAR directly.

**Mistake 10 — "Code 0 means the job will never run again."** No. Cron/schedulers/retries/manual runs can re-trigger it; durable job IDs and idempotency remain necessary.

**Mistake 11 — "No exception means all data committed."** Not if code swallowed errors or side effects were asynchronous.

**Mistake 12 — "`System.exit(0)` is the best cleanup method."** No. It can exit before confirming outcomes, closing resources, or completing workers.

## 16. Checklist for designing one-shot jobs

1. Document success, input error, and execution error definitions and codes 0/2/10.
2. Use `WebApplicationType.NONE` when HTTP is unnecessary.
3. Parse and validate `ApplicationArguments` **before side effects**.
4. Classify input errors per contract without mislabeling bugs as input errors.
5. Use `ApplicationRunner` to execute one clearly orchestrated unit of work.
6. Never report success while background tasks remain unfinished or transactions uncommitted.
7. Maintain one place to store outcomes and one point deciding exit status.
8. Call `SpringApplication.exit(context)` to read the code and close the context, then `System.exit(code)` when OS status is required.
9. Handle bootstrap failures prior to runners separately.
10. Unit-test logic and subprocess-test actual exit codes.
11. Avoid infinite retries on input errors; design bounded retry/backoff for appropriate execution errors.
12. Ensure idempotency, durable job state, and checkpoints when handling critical data.
13. Log job ID, outcome, processed count, failure stage, and duration without exposing secrets.
14. Account for forced process kills where cleanup cannot finish.
15. Verify Kubernetes Job/CI policies interpret your exit codes properly.

### References

- Spring Boot 3.3 — SpringApplication / ApplicationRunner / Application Exit: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — SpringApplication Javadoc, `exit(...)`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3 — `ApplicationArguments`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html
- Spring Boot 3.3 — `ExitCodeGenerator`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeGenerator.html
- Spring Boot 3.3 — `ExitCodeExceptionMapper`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeExceptionMapper.html
- Java 17 — `ProcessBuilder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.html
- Kubernetes — Job: https://kubernetes.io/docs/concepts/workloads/controllers/job/

**Key takeaway:** a one-shot Spring Boot job must **accurately classify business outcomes, close the `ApplicationContext`, and pass the right exit code to the operating system**. In the example: **0 = success**, **2 = input error**, **10 = execution error**. `ApplicationRunner` runs the job; `ExitCodeGenerator` carries the outcome; `SpringApplication.exit` closes the context and returns the code; `System.exit` delivers the code to the shell/orchestrator. Report success only when all required work has genuinely completed.
