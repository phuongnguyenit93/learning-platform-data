# SpringApplication.exit, ExitCodeGenerator, and Process Exit Codes

A Spring Boot application needs to know how to start up and also how to terminate. When a web service shuts down, it must close resources and let infrastructure manage the process. When a command-line application or batch job finishes, the caller also needs to know whether the job succeeded or failed. That information is commonly passed via a **process exit code**.

Spring Boot provides `SpringApplication.exit(...)` to calculate the exit code and close `ApplicationContext`, along with the `ExitCodeGenerator` interface so the application decides what the code means. When status must be reported to the operating system, the caller can pass the returned integer to `System.exit(...)`.

These three mechanisms have distinct responsibilities:

- **`SpringApplication.exit(context)`:** collects the result code from generators and closes the context if possible.
- **`ExitCodeGenerator.getExitCode()`:** supplies an integer representing the application's outcome.
- **`System.exit(code)`:** requests the JVM to terminate and passes the status code to the operating system.

If you only call `SpringApplication.exit(...)`, the JVM is not instructed to exit by that call alone. If you call `System.exit(0)` regardless of whether the job succeeded or failed, schedulers cannot easily detect failures. If you put `SpringApplication.exit(SpringApplication.run(...))` right inside a web server's main method, the application may shut down immediately after startup.

This lesson explains everything from exit status fundamentals to designing batch exit codes, choosing among multiple generators, handling exceptions, shutting down beans safely, and testing.

## 1. What Is a Process Exit Code?

The operating system provides a status code after a process exits. A shell script, scheduler, CI job, or process supervisor can inspect that code to decide the next step.

The common convention is:

| Code | Meaning |
|---|---|
| `0` | Completed successfully |
| Non-`0` | An error or a special state requiring handling |
| `1` | May be used by applications for general errors |
| `2` | May be used by applications for input errors |
| `10` | May be used by applications for transient auxiliary failures |

The codes `1`, `2`, and `10` in the table are **illustrative conventions only**. Spring Boot does not assume `2` always means argument error or `10` means database error. Each system should establish stable, consistent meanings shared between the application and its callers.

Example of an import command on Linux:

~~~bash
java -jar import-job.jar --input=orders.csv
status=$?

if [ "$status" -eq 0 ]; then
  echo "Import completed"
else
  echo "Import failed: exit code $status"
  exit "$status"
fi
~~~

The `$?` variable stores the exit status of the command that just ran. Read it immediately after the `java` command; running another command overwrites `$?`.

In Windows PowerShell:

~~~powershell
java -jar import-job.jar --input=orders.csv
$code = $LASTEXITCODE

if ($code -ne 0) {
    Write-Error "Import failed with exit code $code"
    exit $code
}
~~~

`$LASTEXITCODE` holds the exit code from native programs such as `java`.

### How Does It Differ from HTTP Status and Logs?

| Mechanism | Recipient | Example |
|---|---|---|
| HTTP status | Client calling a request | `200`, `400`, `500` |
| Logs | Operators and observability systems | Cannot connect to database |
| Exit code | Shell, scheduler, OS, process supervisor | `0`, `1`, `10` |

A REST API returning HTTP 500 for one request **does not mean** the entire JVM must stop with exit code 500. Likewise, a job without an HTTP server still needs to return an exit status to its scheduler.

## 2. Application Lifecycle at Shutdown

Once `SpringApplication.run(...)` starts successfully, Spring holds an `ApplicationContext` containing bean definitions and managed beans. During normal context closure, Spring publishes close events, stops lifecycle components, and destroys singleton beans.

General flow:

~~~text
An action requests termination
                  |
                  v
   SpringApplication.exit(context)
                  |
                  +--> Evaluate ExitCodeGenerators
                  |
                  +--> Close ApplicationContext
                  |        |
                  |        +--> ContextClosedEvent
                  |        +--> Stop lifecycle components
                  |        +--> Destroy singleton beans
                  |        +--> @PreDestroy / destroy callbacks
                  |
                  v
             Return int code
                  |
                  v
          System.exit(code)
                  |
                  v
          OS receives exit status
~~~

This is a responsibility diagram, not a guarantee of the exact internal callback sequence. Detailed lifecycle ordering depends on context, dependencies, and components such as `SmartLifecycle`.

A key point: **the Spring container and the JVM process are two different entities**. A single JVM can host multiple threads or even multiple `ApplicationContext`s.

### JVM Shutdown Hook

Spring Boot normally registers a shutdown hook so the Spring context can close when the JVM terminates along a normal path. This gives callbacks such as `@PreDestroy` and `DisposableBean.destroy()` a chance to run.

However, if the process is forcefully killed, the JVM crashes, or power fails, shutdown hooks may not run. Never persist critical data solely inside shutdown callbacks.

## 3. How Does SpringApplication.exit(...) Work?

The method supports this signature:

~~~java
static int exit(
        ApplicationContext context,
        ExitCodeGenerator... exitCodeGenerators
);
~~~

It can evaluate both generators passed directly and beans implementing `ExitCodeGenerator` in the context. When multiple generators exist, Spring Boot determines the code according to their order. Next, the context is closed if possible and the method returns an `int`.

Example:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(BatchApplication.class, args);

int exitCode = SpringApplication.exit(context);
System.exit(exitCode);
~~~

Here:

1. `SpringApplication.run` creates the context and performs startup.
2. Synchronous runners, if any, complete before `run` returns.
3. `SpringApplication.exit` computes the code and closes the context.
4. `System.exit` instructs the JVM to terminate with that code.

This pattern fits **one-shot CLI/batch apps** especially well.

### If You Only Call SpringApplication.exit

~~~java
int code = SpringApplication.exit(context);
log.info("Exit code = {}", code);
~~~

The context may close, yet this call alone does not tell the JVM to terminate. The JVM may exit on its own if no non-daemon threads remain; or it may stay alive due to lingering threads or components outside the context.

### Why Not Call It Right After run in a Web Application?

Consider:

~~~java
public static void main(String[] args) {
    int code = SpringApplication.exit(
            SpringApplication.run(WebApplication.class, args)
    );
    System.exit(code);
}
~~~

In a Spring Boot web service, `SpringApplication.run` typically returns once the server starts, rather than blocking forever until all HTTP requests finish. Thus, this `main` method closes the context almost immediately. For long-running web servers, `main` should normally be:

~~~java
public static void main(String[] args) {
    SpringApplication.run(WebApplication.class, args);
}
~~~

When stopping is needed, let the deployment platform or an appropriate lifecycle orchestration mechanism request shutdown.

## 4. ExitCodeGenerator: Contract for Choosing an Exit Code

The interface resides in package `org.springframework.boot.ExitCodeGenerator` and has one method:

~~~java
public interface ExitCodeGenerator {
    int getExitCode();
}
~~~

An implementation can return `0` for success and non-`0` for error states. Example:

~~~java
@Configuration
public class ExitConfiguration {

    @Bean
    public ExitCodeGenerator exitCodeGenerator() {
        return () -> 42;
    }
}
~~~

`42` is just an illustrative number. If this bean exists in the context and the application calls `SpringApplication.exit(context)`, it can supply that exit code.

### Why Use an Interface?

Instead of letting arbitrary services call `System.exit(1)` immediately on error, the application can separate:

- Business processing to determine job outcome.
- Mapping the outcome to an exit code.
- Closing the context and terminating the process.

`ExitCodeGenerator` handles the second part. As a result, logic can be tested without terminating the test JVM, and business components do not need to know about process management.

### Generators Should Read Already-Completed Outcomes

`getExitCode()` should be lightweight, predictable, and mostly side-effect-free. If it calls remote APIs, queries a database, or executes another large transaction during shutdown, stopping the application can stall or fail.

Determine the outcome while doing the work and let the generator simply read that result.

## 5. Complete Example: CLI Import Job Returning an Exit Code

Suppose a job reads a CSV file and imports data. Operations wants to distinguish:

- `0`: import succeeded.
- `2`: missing argument or invalid input.
- `10`: import failed due to a retryable error.
- `20`: error that cannot be handled automatically.

First, define constants:

~~~java
public final class JobExitCodes {
    public static final int SUCCESS = 0;
    public static final int INVALID_INPUT = 2;
    public static final int TEMPORARY_FAILURE = 10;
    public static final int PERMANENT_FAILURE = 20;

    private JobExitCodes() {
    }
}
~~~

### 5.1. Bean Holding Job Outcome

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.boot.ExitCodeGenerator;

public final class ImportJobOutcome
        implements ExitCodeGenerator {

    private final AtomicInteger exitCode =
            new AtomicInteger(JobExitCodes.SUCCESS);

    public void success() {
        exitCode.set(JobExitCodes.SUCCESS);
    }

    public void invalidInput() {
        exitCode.set(JobExitCodes.INVALID_INPUT);
    }

    public void temporaryFailure() {
        exitCode.set(JobExitCodes.TEMPORARY_FAILURE);
    }

    public void permanentFailure() {
        exitCode.set(JobExitCodes.PERMANENT_FAILURE);
    }

    @Override
    public int getExitCode() {
        return exitCode.get();
    }
}
~~~

`AtomicInteger` makes reading/writing the value safer when multiple threads are involved. It does not by itself solve precedence rules across errors: if multiple tasks run in parallel, establish an appropriate outcome aggregation strategy.

Register the bean:

~~~java
@Configuration
public class ImportJobConfiguration {

    @Bean
    public ImportJobOutcome importJobOutcome() {
        return new ImportJobOutcome();
    }
}
~~~

Because `ImportJobOutcome implements ExitCodeGenerator`, Spring Boot can discover this bean when computing the exit code.

### 5.2. ApplicationRunner Performing the Work

~~~java
@Component
public class ImportJobRunner implements ApplicationRunner {

    private final ImportService importService;
    private final ImportJobOutcome outcome;

    public ImportJobRunner(
            ImportService importService,
            ImportJobOutcome outcome
    ) {
        this.importService = importService;
        this.outcome = outcome;
    }

    @Override
    public void run(ApplicationArguments args) {
        List<String> inputs = args.getOptionValues("input");

        if (inputs == null || inputs.isEmpty()) {
            outcome.invalidInput();
            return;
        }

        try {
            importService.importFile(inputs.get(0));
            outcome.success();
        } catch (TemporaryImportException ex) {
            outcome.temporaryFailure();
        } catch (PermanentImportException ex) {
            outcome.permanentFailure();
        }
    }
}
~~~

`ImportService` and the two exception types in the example are hypothetical application classes. In real code, log the cause, check for empty option values, configure retries, and manage import transactions.

Here the runner **catches known errors and translates them into outcomes**. It completes normally from Spring's lifecycle standpoint, allowing `SpringApplication.run` to return the context. `main` then closes the context and returns the exit code.

### 5.3. Main Method Terminating the Process

~~~java
@SpringBootApplication
public class ImportJobApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(
                        ImportJobApplication.class,
                        args
                );

        int code = SpringApplication.exit(context);
        System.exit(code);
    }
}
~~~

Execution flow:

~~~text
java -jar import-job.jar --input=orders.csv
                  |
                  v
       SpringApplication.run
                  |
                  v
       ImportJobRunner.run
                  |
          Process file import
                  |
       +----------+----------+
       |                     |
    Success               Failure
       |                     |
   outcome=0          outcome=2/10/20
       |                     |
       +----------+----------+
                  |
                  v
    SpringApplication.exit(context)
                  |
                  v
          System.exit(code)
                  |
                  v
         Shell receives exit status
~~~

This pattern suits a one-shot job whose runner works synchronously and leaves no background tasks running after completion.

## 6. Passing ExitCodeGenerator Directly

Generators do not have to be beans. `SpringApplication.exit` accepts generators via varargs:

~~~java
int code = SpringApplication.exit(
        context,
        () -> 12
);
~~~

For example, the caller already holds a result:

~~~java
int requestedCode = completed ? 0 : 10;

int code = SpringApplication.exit(
        context,
        () -> requestedCode
);

System.exit(code);
~~~

Multiple generators can be passed:

~~~java
int code = SpringApplication.exit(
        context,
        () -> 0,
        () -> 12
);
~~~

Directly passed generators are evaluated alongside generator beans in the context. When multiple generators return non-`0` codes, the outcome is not simply "the last generator always wins".

### When to Use a Bean vs. Passing Directly?

| Scenario | Choice |
|---|---|
| Multiple services update a job's outcome | State bean implementing `ExitCodeGenerator` |
| Caller already determined the code and only needs to close context | Pass generator directly |
| Multiple modules propose exit codes | Ordered generators or a single outcome aggregator |
| Exception causes startup to fail | Exception generator or exception mapper |

For operational clarity, a batch application should normally have **one final place responsible** for the exit code.

## 7. Multiple ExitCodeGenerators: First Non-Zero Code Wins

Spring Boot can collect multiple `ExitCodeGenerator`s. If they are ordered A, B, C and return:

~~~text
A -> 0
B -> 12
C -> 20
~~~

the result is `12`, because Spring Boot picks the **first non-zero code** in generator order. An earlier `0` does not prevent later generators from supplying an error code.

To control order, implement `Ordered` or use `@Order`.

~~~java
@Component
public class ValidationExitCode
        implements ExitCodeGenerator, Ordered {

    @Override
    public int getExitCode() {
        return hasValidationFailure() ? 2 : 0;
    }

    @Override
    public int getOrder() {
        return 10;
    }

    private boolean hasValidationFailure() {
        return false; // Read actual application outcome.
    }
}
~~~

Another generator:

~~~java
@Component
public class InfrastructureExitCode
        implements ExitCodeGenerator, Ordered {

    @Override
    public int getExitCode() {
        return hasInfrastructureFailure() ? 10 : 0;
    }

    @Override
    public int getOrder() {
        return 20;
    }

    private boolean hasInfrastructureFailure() {
        return false;
    }
}
~~~

Lower order values usually have higher evaluation priority. In this example, the validation generator is evaluated before the infrastructure generator.

You can use annotations:

~~~java
@Component
@Order(10)
public class ValidationExitCode
        implements ExitCodeGenerator {

    @Override
    public int getExitCode() {
        return 2;
    }
}
~~~

If you need to decide which error type takes precedence, specify order explicitly or use a single aggregator. Never let a business-meaningful exit status depend on accidental bean registration order.

### Distinguishing Generator Order from Runner Order

`@Order` on `ApplicationRunner` orders runners per Spring Boot's runner contract. Evaluation order of `ExitCodeGenerator`s is a separate concern. A runner executing earlier does not mean its associated bean's exit code takes precedence earlier.

## 8. Do Not Use ExitCodeGenerator for Shutdown Side Effects

Example to avoid:

~~~java
@Override
public int getExitCode() {
    remoteClient.sendFinalBusinessTransaction();
    archiveService.archiveAllData();
    return 0;
}
~~~

A better principle is completing business logic first, recording the result, and letting the generator solely return the code.

~~~java
public final class BatchResult implements ExitCodeGenerator {
    private volatile int code = 0;

    public void failWith(int newCode) {
        this.code = newCode;
    }

    @Override
    public int getExitCode() {
        return code;
    }
}
~~~

If cleanup must occur, put it in an appropriate lifecycle callback such as `@PreDestroy` or an explicitly coordinated stop service. If durable state must be saved, persist it inside the business transaction; do not rely on shutdown callbacks always running.

Never call `System.exit` from inside `getExitCode` itself:

~~~java
@Override
public int getExitCode() {
    System.exit(1); // Do not do this.
    return 1;
}
~~~

That exceeds the generator's responsibility and can cut short context closing.

## 9. Exceptions Can Also Implement ExitCodeGenerator

Not every run completes startup normally. A severe failure inside a runner or during startup can cause `SpringApplication.run(...)` to throw an exception before returning a context.

Spring Boot supports exceptions implementing `ExitCodeGenerator`:

~~~java
public class InvalidImportArgumentsException
        extends RuntimeException
        implements ExitCodeGenerator {

    public InvalidImportArgumentsException(String message) {
        super(message);
    }

    @Override
    public int getExitCode() {
        return 2;
    }
}
~~~

A runner can throw this exception:

~~~java
@Component
public class ImportArgumentsRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        if (!args.containsOption("input")) {
            throw new InvalidImportArgumentsException(
                    "Missing --input argument"
            );
        }

        // Process work.
    }
}
~~~

If the exception causes startup to fail and passes through Spring Boot's failure handling, the framework can determine the exit code from `getExitCode()`.

### Distinguishing Normal Outcomes from Exceptions

If a job finishes with a valid business status—such as "no data to process"—it does not necessarily need to throw an exception. You can store that status in an `ExitCodeGenerator` bean.

Exceptions fit situations where startup or the job genuinely cannot continue and should be treated as a failure.

### Exceptions Occurring After Startup

An exception implementing `ExitCodeGenerator` thrown inside an HTTP request after the server is running does not automatically terminate the JVM. HTTP request handlers can catch the error and return an HTTP response. Startup failure exit code handling does not replace runtime error handling in a service.

## 10. ExitCodeExceptionMapper for Unmodifiable Exceptions

When an exception belongs to an external library or its class cannot be modified to implement the interface, use `ExitCodeExceptionMapper`.

Contract:

~~~java
public interface ExitCodeExceptionMapper {
    int getExitCode(Throwable exception);
}
~~~

The mapper returns the appropriate code, or `0` if it does not want to map that exception to a special exit code.

Example:

~~~java
@Configuration
public class ExceptionExitConfiguration {

    @Bean
    public ExitCodeExceptionMapper exitCodeExceptionMapper() {
        return exception -> {
            if (exception instanceof InvalidConfigurationException) {
                return 2;
            }
            if (exception instanceof ExternalSystemUnavailableException) {
                return 10;
            }
            return 0;
        };
    }
}
~~~

The two exceptions in the example are hypothetical types. A mapper should recognize the exact errors operations needs to distinguish.

### Exceptions Can Be Wrapped Multiple Layers Deep

An original exception may appear inside a `BeanCreationException` or another framework wrapper exception. If needed, inspect the cause chain:

~~~java
@Bean
public ExitCodeExceptionMapper exitCodeExceptionMapper() {
    return exception -> {
        Throwable cause = exception;

        while (cause != null) {
            if (cause instanceof InvalidImportArgumentsException) {
                return 2;
            }

            if (cause instanceof ExternalSystemUnavailableException) {
                return 10;
            }

            cause = cause.getCause();
        }

        return 0;
    };
}
~~~

Do not map every `RuntimeException` to a special code, because that hides unrelated errors.

### ExitCodeExceptionMapper Is Not @ControllerAdvice

`@ControllerAdvice` and `@ExceptionHandler` serve HTTP responses. `ExitCodeExceptionMapper` serves application exit codes during startup failure handling. The two tools do not replace each other.

## 11. If SpringApplication.run Fails Before Returning Context

The familiar snippet:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(BatchApplication.class, args);

int code = SpringApplication.exit(context);
System.exit(code);
~~~

only runs the last two lines if `SpringApplication.run` returns a context successfully. If an exception is thrown during bean creation or a runner, Java execution can exit `main` before `SpringApplication.exit(context)` is ever called.

Therefore, distinguish clearly:

~~~text
          SpringApplication.run
                   |
          +--------+--------+
          |                 |
       Success         Startup error
          |                 |
   Return context      Failure handling
          |                 |
          v                 v
 SpringApplication.exit   Exception generator
          |              or mapper if appropriate
          v                 |
    System.exit(code)     Exit with error status
~~~

Spring Boot has its own failure handling when startup fails. When designing error codes, use an exception generator/mapper if you want specific codes in that situation, and test actual process exit statuses using a child process.

### Avoid Overwriting Errors with Success

This snippet sends a misleading signal:

~~~java
try {
    SpringApplication.run(BatchApplication.class, args);
} catch (Exception ex) {
    System.exit(0);
}
~~~

Returning `0` when startup failed causes schedulers or CI pipelines to mark the job successful. If catching exceptions in `main`, preserve the failure meaning and do not suppress diagnostic information.

## 12. ExitCodeEvent and Shutdown Events

Spring Boot provides `ExitCodeEvent` in package `org.springframework.boot`. It represents an event emitted once the exit code has been determined by the corresponding generator mechanism.

Observation example:

~~~java
@Component
public class ExitCodeObserver {

    @EventListener
    public void onExitCode(ExitCodeEvent event) {
        int exitCode = event.getExitCode();
        // Record logs or metrics.
    }
}
~~~

Distinguish it from other events:

| Event | Meaning |
|---|---|
| `ExitCodeEvent` | Exit code determined by generator mechanism |
| `ContextClosedEvent` | `ApplicationContext` is closing |
| `ApplicationFailedEvent` | Application startup failed |
| `ApplicationReadyEvent` | Application completed appropriate startup steps |

`ExitCodeEvent` is not the single reliable place for cleanup. Not every shutdown type is guaranteed to emit this event, especially when the process is forcefully killed.

## 13. SpringApplication.exit, context.close, and System.exit

| Call | Closes Spring context | Returns exit code | Actively asks JVM to terminate |
|---|---|---|---|
| `context.close()` | Yes | No | No |
| `SpringApplication.exit(context)` | Yes, if possible | Yes, `int` | No |
| `System.exit(code)` | Via shutdown hooks if they run | Passes code to OS | Yes |
| `Runtime.getRuntime().halt(code)` | Bypasses normal shutdown hooks | Passes code to OS | Yes, forcefully |

`Runtime.halt` fits only exceptional cases where normal shutdown cannot complete. It can lose unflushed data or skip cleanup.

### Why Are Both exit and System.exit Needed?

A job can call:

~~~java
int code = SpringApplication.exit(context);
~~~

After that call, Spring Boot has computed the result code, yet the shell may not receive that code if the JVM exits naturally along another path. When you want to return the exact code to the OS:

~~~java
System.exit(code);
~~~

### Why Not Use Only System.exit?

Spring Boot normally registers a shutdown hook, so `System.exit` can trigger context closure. However, in a job where code already holds the context and needs a generator-computed result, calling `SpringApplication.exit` first clearly separates cleanup from exit-code calculation. It also makes testing exit-code calculation possible without forcing the JVM to exit.

## 14. Spring Bean Cleanup When the Context Closes

When `SpringApplication.exit(context)` closes the context, Spring can invoke registered destruction callbacks.

### @PreDestroy

~~~java
@Component
public class TemporaryFileManager {

    @PreDestroy
    public void cleanup() {
        // Close/delete temporary resources owned by the bean.
    }
}
~~~

In Spring Boot 3 and Spring Framework 6, the annotation normally comes from `jakarta.annotation.PreDestroy`. Older generations may use `javax.annotation.PreDestroy`.

### DisposableBean

~~~java
@Component
public class ManagedSocket implements DisposableBean {

    @Override
    public void destroy() throws Exception {
        // Close socket owned by the bean.
    }
}
~~~

### @Bean destroyMethod

~~~java
@Configuration
public class RemoteClientConfiguration {

    @Bean(destroyMethod = "close")
    public ExternalClient externalClient() {
        return new ExternalClient();
    }
}
~~~

### SmartLifecycle

A background component may need to stop accepting tasks and wait for running tasks to complete. `SmartLifecycle` provides start/stop hooks and phases to coordinate ordering. It is preferable to a standalone destroy callback when dependencies exist across multiple workers.

Bean cleanup must be safe, properly bounded by timeouts, and close only resources actually owned by the bean.

### Prototypes Are Not Fully Auto-Destroyed Like Singletons

Spring creates and configures prototypes and then hands the instance to the caller. The container usually does not track every prototype's full usage lifecycle to invoke destruction callbacks as it does for singletons. If a prototype holds resources, the caller needs its own closing mechanism.

## 15. ApplicationRunner and CommandLineRunner

`ApplicationRunner` and `CommandLineRunner` are common ways to run work after the context refreshes. In batch applications, `main` can call `SpringApplication.exit` once synchronous runners finish.

~~~text
SpringApplication.run
        |
        +--> Create ApplicationContext
        +--> Create beans
        +--> Invoke runners
        |
        v
Runner completes
        |
        v
SpringApplication.run returns context
        |
        v
SpringApplication.exit(context)
        |
        v
System.exit(code)
~~~

### Runners Return void Yet Need Error Codes

A runner does not return an `int`. It can update a `JobOutcome` that an `ExitCodeGenerator` reads afterward. If an exception must fail startup, the runner can throw an exception with a corresponding code.

### Async Tasks Might Not Be Done Yet

This is an important trap:

~~~java
@Override
public void run(ApplicationArguments args) {
    executor.submit(() -> importService.importData());
}
~~~

The runner returns right after submitting, while the task is still running. If `main` immediately calls `SpringApplication.exit(context)`, the context may close before the import finishes and the exit code will not reflect the true result.

Wait for completion or use explicit coordination:

~~~java
@Override
public void run(ApplicationArguments args) throws Exception {
    Future<?> future = executor.submit(
            () -> importService.importData()
    );

    future.get();
}
~~~

The example illustrates waiting; real code must handle timeouts, interruption, cancellation, and error mapping. Do not wait forever on an unresponsive resource.

## 16. Graceful Shutdown for Web Services

A web service usually does not have a single job returning an exit code after every request. On shutdown, it needs to:

1. Stop or restrict accepting new requests per web server mechanism.
2. Give in-flight requests time to complete.
3. Stop consumers and background workers.
4. Close connection pools, files/sockets, and other resources.
5. Let the process exit under infrastructure orchestration.

In supported Spring Boot versions, configure:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Actual duration also depends on the web server and the deadline granted by Docker, Kubernetes, or the process supervisor.

### Do Not Terminate the JVM from a Failed HTTP Request

~~~java
@RestController
public class OrderController {

    @PostMapping("/orders")
    public void createOrder() {
        System.exit(1); // Do not do this.
    }
}
~~~

A failing request should normally return an HTTP error and let the server continue serving other requests. Stopping the entire process belongs to controlled administrative/operational mechanisms.

### Long-Running Web Servers Should Have a Simple main

~~~java
@SpringBootApplication
public class WebApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebApplication.class, args);
    }
}
~~~

Process exit codes are meaningful when the process actually terminates, distinct from individual request status codes.

## 17. OS Signals, SIGTERM, and SIGKILL

Many platforms send signals to request process termination. With controlled shutdown, the JVM usually gets an opportunity to run shutdown hooks and Spring gets an opportunity to close the context.

Distinguish clearly:

- **Normal termination:** `main` finished or the process received a controlled stop request.
- **Forced stop:** such as `SIGKILL` on Linux, which does not let the JVM run shutdown hooks.
- **JVM crash / power loss:** shutdown may skip cleanup.

Do not assume an `ExitCodeGenerator`-chosen code is always what the shell sees when a process is killed by a forced signal. Some shells represent signal termination using exit statuses based on `128 + signal number`, which is an environment convention rather than a Spring Boot rule.

When investigating an abnormal process exit, combine exit status, logs, signal/restart reasons, and operational telemetry.

## 18. Exit Code Range and OS Compatibility

`ExitCodeGenerator.getExitCode()` returns a Java `int`. However, operating systems and shells may represent codes with narrower bounds.

In many Unix/POSIX environments, shells see process exit statuses within an 8-bit range. A code greater than `255` or a negative code may not appear as the original integer. Windows has its own exit code conventions.

For applications targeting multiple environments, usually pick **a small set of positive integers** such as `0`, `2`, `10`, `20`, avoiding codes with special meanings in the shells or schedulers your organization uses.

Do not use exit codes to cram in full error details. Exit codes are terse signals; logs, metrics, or job reports store specific root causes.

## 19. Exit Codes in Schedulers, CI/CD, and Containers

A job may run from cron, a CI/CD pipeline, a systemd service, Windows Task Scheduler, or a Kubernetes Job. Orchestrators typically use exit status to distinguish success from failure, though retry behavior or result status depends on each platform's own configuration.

Example script:

~~~bash
#!/usr/bin/env bash

java -jar daily-sync.jar --mode=full
code=$?

if [ "$code" -ne 0 ]; then
  echo "Daily sync failed with code $code"
  exit "$code"
fi

echo "Daily sync succeeded"
~~~

If this script runs inside a pipeline, exiting non-`0` typically marks the pipeline step failed per pipeline settings.

### The Code Table Is an Operational Contract

| Code | Suggested name | How callers can handle it |
|---|---|---|
| `0` | `SUCCESS` | Proceed |
| `2` | `INVALID_INPUT` | Fix input; do not blindly retry |
| `10` | `TRANSIENT_FAILURE` | Bounded retry |
| `20` | `PERMANENT_FAILURE` | Alert / manual intervention needed |
| `30` | `PARTIAL_FAILURE` | Inspect processed data |

This is an illustrative table, not a Spring Boot standard. If code meanings change, update scripts, schedulers, and runbooks accordingly.

### Retries Require Idempotency

If a job writes partial data before returning code `10`, retrying can create duplicate records or repeat side effects. Therefore, a retry-signaling exit code **does not solve data consistency by itself**. Jobs need transactions, checkpoints, or appropriate idempotency keys.

## 20. A Clear Workflow for Determining Exit Codes

If a job has multiple outcome types, use an outcome enum:

~~~java
public enum JobOutcome {
    SUCCESS(0),
    INVALID_INPUT(2),
    TEMPORARY_FAILURE(10),
    PERMANENT_FAILURE(20);

    private final int code;

    JobOutcome(int code) {
        this.code = code;
    }

    public int code() {
        return code;
    }
}
~~~

Generator bean mapping the final outcome:

~~~java
@Component
public class JobResult implements ExitCodeGenerator {

    private volatile JobOutcome outcome = JobOutcome.SUCCESS;

    public void complete(JobOutcome outcome) {
        this.outcome = outcome;
    }

    @Override
    public int getExitCode() {
        return outcome.code();
    }
}
~~~

With multiple parallel tasks, aggregate outcomes under a clear rule: which failure takes precedence, when the overall job counts as successful, and how to stop a late-finishing task from overwriting an earlier error.

A single generator reading an aggregated outcome is usually easier to reason about than multiple competing generators if the application has complex status rules.

## 21. Testing ExitCodeGenerator and SpringApplication.exit

Never call `System.exit(...)` directly inside a unit test sharing the JUnit JVM, because it can terminate the entire test runner.

### Unit Testing the Generator

~~~java
@Test
void shouldReturnFailureCode() {
    JobResult result = new JobResult();

    result.complete(JobOutcome.TEMPORARY_FAILURE);

    assertEquals(10, result.getExitCode());
}
~~~

This tests pure Java mapping logic.

### Context Test for Exit

You can create a minimal Spring context:

~~~java
@Test
void closesContextAndReturnsCode() {
    AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext();

    context.registerBean(
            ExitCodeGenerator.class,
            () -> () -> 12
    );
    context.refresh();

    int code = SpringApplication.exit(context);

    assertEquals(12, code);
    assertFalse(context.isActive());
}
~~~

This test verifies integration between a generator bean and `SpringApplication.exit`. It does not call `System.exit`.

### Testing the Exception Mapper

~~~java
@Test
void mapsKnownFailure() {
    ExitCodeExceptionMapper mapper = exception -> {
        if (exception instanceof IllegalArgumentException) {
            return 2;
        }
        return 0;
    };

    assertEquals(
            2,
            mapper.getExitCode(
                    new IllegalArgumentException("Invalid input")
            )
    );
}
~~~

The test above only verifies the mapping function. To prove Spring Boot actually loads the mapper and returns the code on startup failure, write an integration test.

### End-to-End Process Test

To confirm the OS exit status, launch the application in a **child process**:

~~~bash
java -jar report-job.jar --input=missing.csv
status=$?
echo "status = $status"
~~~

Now calling `System.exit` terminates only the job process, not the test runner JVM. Bound execution time and manage external dependencies (databases, filesystems, network) if used.

## 22. Common Mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| Context closes yet shell sees success code | Called `SpringApplication.exit` without passing code to OS | Call `System.exit(code)` in the batch app's `main` |
| Job always returns code 42 | Hardcoded bean generator `() -> 42` | Switch to a generator reading the actual outcome |
| Web server starts then exits immediately | Called exit right after `SpringApplication.run` | Use standard `main` for web services |
| Runner fails yet script sees 0 | Caught error and returned success | Map failure to a non-`0` code |
| Unexpected exit code | Multiple generators return non-zero | Check `Ordered`, `@Order`, and precedence |
| Exception mapper ignored for HTTP errors | Mapper does not handle HTTP requests | Use controller exception handling |
| Job outcome read too early | Runner only submitted an async task | Wait for work completion before exiting |
| Cleanup skipped when process is killed | Shutdown hooks bypassed | Protect data with persistence/transactions |
| Test suite terminates abruptly | Called `System.exit` inside test JVM | Test codes/results or spawn a child process |
| Different error code on Unix | Large or negative numbers truncated by OS/shell | Use small, non-negative codes |
| Cannot diagnose cause from exit code | Code carries too little detail | Combine logs, metrics, job IDs |
| Process stays alive after `context.close` | Non-daemon threads or non-context resources remain | Identify owner and stop resources per lifecycle |

### Do Not Use Exit Codes to Represent Individual Requests

If an HTTP request fails, handle it via HTTP status codes and exception handlers. Exit codes are for the lifecycle of the entire process or a job executed by that process.

### Do Not Treat Shutdown Callbacks as Business Transactions

`@PreDestroy` may not run during forced termination. Persist critical results and checkpoints while the job is running instead of waiting until process exit.

### Do Not Terminate the JVM from Business Services

Calling `System.exit` from a domain service blurs dependencies and complicates testing. Services should return outcomes or throw meaningful exceptions; the `main`/lifecycle layer decides when to terminate the process.

## 23. A Complete Operational Scenario

Suppose a customer-data sync app is run nightly by a scheduler:

~~~text
Scheduler
    |
    v
java -jar customer-sync.jar
    |
    v
Spring Boot creates context
    |
    v
ApplicationRunner invokes SyncService
    |
    +--> Validate input
    +--> Read data source
    +--> Sync database
    +--> Write checkpoint
    |
    v
JobResult holds final outcome
    |
    v
SpringApplication.exit(context)
    |
    +--> Read JobResult.getExitCode()
    +--> Stop beans and close resources
    |
    v
System.exit(code)
    |
    v
Scheduler reads exit status
    |
    +--> 0: complete
    +--> 2: fix input
    +--> 10: bounded retry
    +--> 20: alert
~~~

If the job writes 80% of data and returns a retry code, the next run must rely on checkpoints or idempotent upserts so data is not corrupted. Exit status only reports outcome; consistency must be solved in business design.

If the scheduler only understands two statuses (success/failure), using `0` and a single error code `1` works fine. Do not invent complex code tables when callers have no need to classify failures.

## 24. Pre-Deployment Checklist

1. **Identify application type:** one-shot job or long-running web server?
2. **Define exit code contract:** `0` for success; error codes with stable meanings.
3. **Pick one owner for outcome:** avoid competing unprioritized generators.
4. **Ensure synchronous runners finish:** do not close the context while tasks still run.
5. **Use `SpringApplication.exit` when you need both code calculation and context closure.**
6. **Call `System.exit` only at the right process boundary**, typically a batch app's `main`.
7. **Map startup exceptions when needed:** exceptions implementing generator or `ExitCodeExceptionMapper`.
8. **Verify OS-returned codes in child-process tests.**
9. **Do not use HTTP statuses as process exit codes.**
10. **Ensure resource cleanup follows lifecycle** with bounded timeouts.
11. **Do not rely on shutdown hooks to persist durable state.**
12. **Choose small, non-negative numbers** for shell/OS compatibility.
13. **Log error causes** and retain sufficient diagnostic info.
14. **Align code conventions with schedulers/CI/CD**, especially if they trigger retries.
15. **Test multi-step failures and retries**, avoiding duplicate data processing.

## Conclusion

`SpringApplication.exit(context)` is Spring Boot's tool for computing the result code and closing `ApplicationContext`. `ExitCodeGenerator` lets beans or directly passed objects supply exit codes, while `ExitCodeExceptionMapper` maps exceptions along the startup failure path. When multiple generators exist, Spring Boot picks the **first non-`0` code** in the order defined by `Ordered` or `@Order`.

`System.exit(code)` is what actually asks the JVM to terminate and sends the status code to the operating system. In batch applications, combining synchronous runners, `SpringApplication.exit`, and `System.exit` lets schedulers observe outcomes accurately. In web services, keep the context alive until a proper shutdown request arrives and clearly separate HTTP request status from process lifecycle.

A good exit code is a **testable operational contract**: unambiguous numbers, reflecting real outcomes, independent of lucky cleanup, and consistently understood across scripts and workers. Designing clear boundaries between business outcomes, Spring lifecycle, and the JVM helps applications terminate safely and makes incidents easy to diagnose.
