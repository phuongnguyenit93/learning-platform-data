# CommandLineRunner and ApplicationRunner in Spring Cloud Task

## 1. Role in the Processing Flow of a Short-Lived Task

A **Spring Cloud Task** application is typically launched from the command line, a Kubernetes CronJob, an orchestrator, or a request from another system; it processes a finite piece of work and then terminates. To start business logic right after Spring Boot finishes setting up the application environment, two very common extension points are **`CommandLineRunner`** and **`ApplicationRunner`**.

Both belong to **Spring Boot**, not APIs exclusive to Spring Cloud Task. Spring Cloud Task adds lifecycle management and persists **`TaskExecution`** via **`TaskRepository`**; a runner is a convenient place to invoke **specific business logic** such as file import, report export, transaction reconciliation, or data synchronization.

For example, at 02:00 every day, a CronJob runs:

~~~bash
java -jar revenue-task.jar --date=2026-11-23 --dry-run
~~~

When the process starts, Spring Boot creates the application context, configures beans, and invokes the runner with the received arguments. The runner validates the date, invokes the data export service, and terminates. Spring Cloud Task records metadata about the execution for monitoring, status lookup, and failure investigation. With `--dry-run`, the application can inspect the execution plan without writing business data; the exact behavior must be implemented by the service itself.

**Key takeaway:** the runner defines **the business logic that runs at startup**, while Spring Cloud Task defines **how a single application run is tracked**. Runners should not be treated as a scheduling mechanism or a persistent queue system.

## 2. Where Are Runners Called in the Spring Boot Lifecycle?

Spring Boot invokes beans of type `ApplicationRunner` and `CommandLineRunner` after the application context has been refreshed, required beans have been created, and before announcing that the application is fully ready (`ApplicationReadyEvent`). In a typical startup flow, runners execute synchronously; `SpringApplication.run(...)` returns only after they have completed or startup fails.

Conceptual processing flow:

~~~mermaid
flowchart TD
    A["CLI / CronJob / orchestrator launches JVM"] --> B["SpringApplication.run(args)"]
    B --> C["Create and refresh Spring ApplicationContext"]
    C --> D["Spring Boot invokes runners in order"]
    D --> E["Runner validates arguments and calls business service"]
    E --> F{"Business logic completed?"}
    F -- "Success" --> G["SpringApplication.run returns"]
    F -- "Unhandled exception" --> H["Startup fails; error handling"]
    G --> I["Close context and terminate process"]
    H --> I
    I --> J["Orchestrator receives result/exit code"]
~~~

With Spring Cloud Task enabled and metadata connectivity available, the framework tracks the start/end of the task and persists metadata via `TaskRepository`. The diagram above illustrates **the overall business and lifecycle flow**, not the exact order of every internal Spring Cloud Task callback across all versions. Whether the repository can record failure information depends on when the error occurs and database availability.

### Events Not to Confuse

| Phase | Significance for Runners |
|---|---|
| Bean creation and dependency injection | A runner is a Spring bean; its constructor, configuration, and dependent beans must be constructed before running business logic |
| Context refreshed | Most infrastructure is ready, including datasources/services if configured successfully |
| `ApplicationStartedEvent` | Published before runners are invoked in the standard Spring Boot startup sequence |
| `CommandLineRunner.run(...)` / `ApplicationRunner.run(...)` | Executes startup logic, parses arguments, and calls services |
| `ApplicationReadyEvent` | Signals after runners have completed successfully |
| Context closed, application terminated | Releases resources, completes the short-lived application lifecycle, and provides a result to the runtime environment |

If a runner throws an unhandled exception, Spring Boot startup fails and `ApplicationReadyEvent` does not occur along the success path. Therefore, this is the right place to **surface critical business failures**, rather than merely logging "failed" and letting the application return a success code.

> **Lifecycle note:** "The runner has returned" does not automatically mean "the JVM has exited". A web server, non-daemon threads, a scheduler, or resources keeping the process alive can keep the application running. Spring Cloud Task applications typically need a non-web configuration and an explicit context-closing mechanism.

## 3. CommandLineRunner: Receiving a String Argument List

`CommandLineRunner` is a functional interface in the `org.springframework.boot` package:

~~~java
@FunctionalInterface
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
~~~

The `String... args` parameter contains the arguments passed to the application. This approach is convenient when the job uses **positional arguments** or needs custom control over parsing input strings, such as a source file path.

Example of a runner accepting exactly one argument representing a file path:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class CsvImportRunner implements CommandLineRunner {

    private final CsvImportService importService;

    public CsvImportRunner(CsvImportService importService) {
        this.importService = importService;
    }

    @Override
    public void run(String... args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Usage: java -jar import-task.jar <path-to-file.csv>");
        }

        Path source = Path.of(args[0]);
        if (!Files.isRegularFile(source) || !Files.isReadable(source)) {
            throw new IllegalArgumentException(
                "File does not exist or cannot be read: " + source);
        }

        importService.importCsv(source);
    }
}
~~~

In the example, `CsvImportService` is an application-provided business service that reads/validates/persists data. Arguments:

~~~bash
java -jar import-task.jar ./input/orders.csv
~~~

When using `CommandLineRunner` with `--date=2026-11-23` or `--force` syntax, they remain raw argument strings; you must manually parse values, handle missing or duplicate arguments, and convert types. If an application has multiple named options, `ApplicationRunner` is usually easier to read and maintain.

### When to Use CommandLineRunner

- The application has a small CLI surface with very few arguments, mostly positional.
- You need to process the exact list of input tokens like a command-line utility.
- You already have a dedicated argument parser and want to pass the entire `String[]` to it.

A runner should not directly absorb all file reading, validation, mapping, transaction, and persistence logic. The runner only needs to validate input, construct the business command, and **delegate to a service**.

## 4. ApplicationRunner: Receiving Parsed ApplicationArguments

`ApplicationRunner` is also a functional interface in Spring Boot, but it receives `ApplicationArguments`:

~~~java
@FunctionalInterface
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
~~~

`ApplicationArguments` provides methods to read `--name=value` options, flag options, and non-option arguments:

| API | Meaning | Example |
|---|---|---|
| `getSourceArgs()` | List of original arguments | `["--date=2026-11-23", "--dry-run", "manual"]` |
| `getOptionNames()` | Names of specified options | `date`, `dry-run` |
| `containsOption("dry-run")` | Whether the option was passed | `true` if `--dry-run` is present |
| `getOptionValues("date")` | Values of an option; may be `null` if the option is absent | `["2026-11-23"]` |
| `getNonOptionArgs()` | Arguments that are not options | `["manual"]` |

Example input:

~~~bash
java -jar revenue-task.jar --date=2026-11-23 --dry-run manual
~~~

Do not assume every option has exactly one value. `getOptionValues("date")` can return `null` if missing, an empty list if the option appears without a value, or multiple values if passed repeatedly. Therefore, **validate both the count and content of values before type conversion**.

Example of safely reading arguments:

~~~java
import java.time.LocalDate;
import java.util.List;
import org.springframework.boot.ApplicationArguments;

public final class RevenueTaskOptions {
    private final LocalDate date;
    private final boolean dryRun;

    private RevenueTaskOptions(LocalDate date, boolean dryRun) {
        this.date = date;
        this.dryRun = dryRun;
    }

    public static RevenueTaskOptions parse(ApplicationArguments args) {
        List<String> dates = args.getOptionValues("date");

        if (dates == null || dates.size() != 1
                || dates.get(0) == null || dates.get(0).isBlank()) {
            throw new IllegalArgumentException(
                "Missing valid argument: --date=yyyy-MM-dd");
        }

        LocalDate parsedDate = LocalDate.parse(dates.get(0));
        return new RevenueTaskOptions(
            parsedDate,
            args.containsOption("dry-run")
        );
    }

    public LocalDate date() {
        return date;
    }

    public boolean dryRun() {
        return dryRun;
    }
}
~~~

`LocalDate.parse(...)` throws `DateTimeParseException` if the date value does not conform to ISO-8601 format. Here, the exception is intentionally allowed to propagate to the runner so the entire execution fails observably. In a real application, you can add clearer error messages, restrict valid date ranges, and check for unsupported options.

An important distinction: `ApplicationArguments` helps **read and classify** arguments; it does not automatically validate business rules such as "the date cannot be in the future" or "real writes are disallowed in a staging environment."

## 5. Complete Spring Cloud Task Example with ApplicationRunner

The example below demonstrates a daily revenue report export application with a dry-run mode. To focus on the runner lifecycle, the business service only prints output; in real usage, replace it with actual queries, report generation, and result persistence.

~~~java
package example.task;

import java.time.LocalDate;
import java.util.List;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.stereotype.Service;
import org.springframework.cloud.task.configuration.EnableTask;

@SpringBootApplication
@EnableTask
public class RevenueTaskApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
            SpringApplication.run(RevenueTaskApplication.class, args);

        // Close the context; return exit code to OS/orchestrator.
        System.exit(SpringApplication.exit(context));
    }

    @Bean
    ApplicationRunner exportRevenue(RevenueReportService service) {
        return arguments -> {
            List<String> dates = arguments.getOptionValues("date");
            if (dates == null || dates.size() != 1
                    || dates.get(0) == null || dates.get(0).isBlank()) {
                throw new IllegalArgumentException(
                    "Must provide --date=yyyy-MM-dd");
            }

            LocalDate targetDate = LocalDate.parse(dates.get(0));
            boolean dryRun = arguments.containsOption("dry-run");

            // Run synchronously; return only after the service completes.
            service.export(targetDate, dryRun);
        };
    }
}

@Service
class RevenueReportService {

    public void export(LocalDate date, boolean dryRun) {
        if (dryRun) {
            System.out.printf(
                "DRY RUN: would export report for %s%n", date);
            return;
        }

        // Illustrative example: replace with actual query and report persistence.
        System.out.printf("Processed report for %s%n", date);
    }
}
~~~

Short-lived application configuration:

~~~yaml
spring:
  main:
    web-application-type: none
  application:
    name: revenue-export-task
  cloud:
    task:
      name: revenue-export-task
~~~

Running the task:

~~~bash
# Dry run, without persisting business results
java -jar revenue-task.jar --date=2026-11-23 --dry-run

# Execute report export
java -jar revenue-task.jar --date=2026-11-23
~~~

The example assumes the project has **version-compatible** Spring Boot and Spring Cloud Task dependencies, along with a properly configured `DataSource` and task metadata schema. In a real environment, you need a persistent database for `TaskRepository`, migration/schema configuration, and appropriate access credentials; the Java code above only illustrates the runner and service portions.

### Why Is SpringApplication.exit(...) Needed?

`SpringApplication.exit(context)` closes the context following Spring's lifecycle and retrieves the appropriate exit code from configured `ExitCodeGenerator` beans. `System.exit(...)` passes that exit code to the Java process, allowing CronJobs, shell scripts, or orchestrators to observe the outcome.

In a short-lived task, the target sequence is typically:

~~~text
Launch → receive arguments → execute business logic → wait for completion
→ record result → close context → terminate process
~~~

However, `SpringApplication.exit(context)` only runs when `SpringApplication.run(...)` **returns normally**. If a runner throws an exception during startup, Spring Boot transitions to the startup failure handling flow; do not rely on statements after `run(...)` to handle the failure branch. Ensure errors are reflected by a non-success exit code and configure exception/exit-code mapping when the business domain requires error classification.

Additionally, closing the context does not replace the responsibility of **waiting for child tasks to complete**. If a service merely submits an `@Async` request or `TaskExecutor.execute(...)` and returns, the process may terminate before the actual work completes.

## 6. Comparing CommandLineRunner and ApplicationRunner

| Aspect | CommandLineRunner | ApplicationRunner |
|---|---|---|
| Package | `org.springframework.boot` | `org.springframework.boot` |
| Primary method | `run(String... args)` | `run(ApplicationArguments args)` |
| Input data | Raw argument strings | Arguments grouped by Spring Boot into options and non-options |
| Best suited for | Simple CLIs, positional arguments, custom parsers | Multiple named options, `--dry-run` flags, on-demand run parameters |
| Invocation timing | After context refresh, during startup | Same phase as CommandLineRunner |
| Synchronous by default | Yes | Yes |
| Built-in retry, scheduling, persistence? | No | No |
| Tracked by Spring Cloud Task when used as entry point? | TaskExecution tracks the application lifecycle, not created separately per runner | Same |

**Neither runner has inherently "better Spring Cloud Task integration" by framework design.** The main difference lies in how arguments are read. For a business task accepting `--date`, `--source`, `--dry-run`, or `--tenant`, `ApplicationRunner` usually makes the code easier to understand.

## 7. Multiple Runners: Ordering, Dependencies, and Error Handling

An application can register **multiple beans** of `CommandLineRunner` and `ApplicationRunner` at the same time. Spring Boot invokes all runners present in the context and applies ordering mechanisms such as `Ordered` or `@Order`.

Example:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
class PreflightRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Checking preconditions");
    }
}

@Component
@Order(20)
class ExportRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Executing export");
    }
}
~~~

In the example, `PreflightRunner` takes precedence and runs before `ExportRunner`. Ordering applies **across all runners**; neither interface inherently runs before the other by default. If no order is declared, do not write logic that depends on an implicit execution order.

When a runner throws an exception without proper handling, runner invocation stops along the error branch; subsequent runners may not be called. This prevents executing business logic when input validation fails, but also causes issues if steps of a single transaction are scattered across multiple runners without consistency management.

**Design recommendation:** if "validate → reconcile → persist results" is **a single business task**, use one primary runner as the entry point and invoke an orchestrating service with clear transactions and recovery rules. Use multiple runners only when there are genuinely multiple independent startup activities whose order is explicitly managed.

### Avoiding Accidental Double Registration

A class annotated with `@Component` that is also instantiated via `@Bean` can result in multiple runner instances existing together, causing business logic to run twice. Similarly, if both a file-import runner and a data-export runner are registered in one application, **both may run on every startup** unless explicit enable/disable conditions are configured. You can use `@Profile`, `@ConditionalOnProperty`, or split applications by task.

## 8. Exception Handling and Task Status

For Spring Cloud Task to provide meaningful status, **business exceptions must affect the run outcome**. Some typical scenarios:

| Scenario | Recommended Behavior |
|---|---|
| Missing `--date` | Throw input error, log a safe message, exit unsuccessfully |
| Malformed date format | Reject before writing any data |
| Cannot connect to business DB | Let the error propagate to the runner or map to an error with an appropriate exit code |
| One of several processing partitions fails | Aggregate errors; do not declare the entire task successful |
| Crashed after writing partial data | Design transactions/checkpoints and idempotency for safe reruns |
| Lost connection to TaskRepository during initialization | Do not assume the repository holds a complete record of the failed run |
| Killed by `SIGKILL` or abrupt container termination | May leave an unclosed TaskExecution; requires timeout detection |

Correct handling pattern in a runner:

~~~java
@Override
public void run(ApplicationArguments args) throws Exception {
    var request = parseRequest(args);
    service.process(request); // Throw exception if business logic fails.
}
~~~

Pattern that **can easily mislead about the outcome**:

~~~java
@Override
public void run(ApplicationArguments args) {
    try {
        service.process(parseRequest(args));
    } catch (Exception ex) {
        log.error("Processing failed", ex);
        // If only logged and returned, Spring Boot may treat
        // the runner as having finished normally.
    }
}
~~~

If additional context needs to be logged, **log and rethrow the exception** rather than swallowing it. If different exit codes are required for input errors, transient errors, or business errors, apply Spring Boot's exit code mechanism, such as `ExitCodeGenerator` or `ExitCodeExceptionMapper` depending on the version in use.

Spring Cloud Task metadata such as task name, start/end timestamps, exit code, and error message helps observe runs; **`TaskRepository` does not automatically store reports, exported data, or per-record status**. Those outputs must be stored in the business store and can be tagged with `taskExecutionId` or a correlation ID for traceability.

## 9. Runners with @Async, TaskExecutor, and Spring Batch

### 9.1. Runners and Asynchronous Work

Runners start synchronously; however, the invoked service itself might use `@Async`, `CompletableFuture`, or `TaskExecutor`. In that case, the runner must determine **when the work is considered finished**.

Example of a service returning futures:

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;

@Bean
ApplicationRunner importAll(ImportService importService) {
    return args -> {
        List<CompletableFuture<Void>> tasks =
            importService.submitAllPartitions();

        // Wait for all partitions to complete and surface errors if any.
        CompletableFuture.allOf(
            tasks.toArray(new CompletableFuture<?>[0])
        ).join();
    };
}
~~~

`ImportService` and per-partition processing are business components to implement in the project. `join()` throws an exception if any future fails; therefore, the runner will not complete successfully when a partition reports an error. If using `TaskExecutor.execute(Runnable)` without a future or synchronization mechanism, merely calling `execute` does **not** prove the task has finished.

You must also account for tasks queued but not yet started, tasks holding locks or database connections, and graceful shutdown. Parallel execution does not replace ensuring **idempotency**, load throttling, and resource closure.

### 9.2. Runners and Spring Batch

A Spring Cloud Task application can launch a **Spring Batch Job**. Spring Batch owns the concepts of `Job`, `Step`, checkpoint/restart, and `JobRepository`, while Spring Cloud Task owns `TaskExecution` at the application level.

If the application includes Spring Batch with Spring Boot's automatic job execution enabled, the job may be triggered during startup. When adding a custom runner that also calls `JobLauncher`, you must check the configuration to avoid **duplicate job launches**. You can choose either approach: use controlled automatic job execution, or invoke `JobLauncher` from the runner and disable automatic launch when needed.

Common configuration example to explicitly control jobs via a runner in Spring Boot versions that support this property:

~~~yaml
spring:
  batch:
    job:
      enabled: false
~~~

When applying this, verify the specific Spring Boot/Spring Batch configuration of your project. If the job runs asynchronously, the runner must also handle waiting for the result and checking the `JobExecution` status before letting the task terminate.

## 10. Safe Operation for Scheduled or On-Demand Runs

A runner executes every time the process starts. Therefore, **who triggers it** and **how many times it runs** must be governed by the orchestration layer.

~~~mermaid
sequenceDiagram
    participant C as CronJob / API / CLI
    participant B as Spring Boot
    participant R as Runner
    participant S as Business Service
    participant T as TaskRepository
    C->>B: Launch with --date=2026-11-23
    B->>T: Spring Cloud Task records execution
    B->>R: run(arguments)
    R->>R: Validate arguments, build business request
    R->>S: export(date)
    alt Completed
        S-->>R: Success result
        R-->>B: run() returns normally
    else Error
        S-->>R: Throws exception
        R-->>B: Error propagates to startup
    end
    B->>T: Update metadata when lifecycle permits
    B-->>C: Process terminates, exit code
~~~

### Important Practices

1. **Use explicit parameters and validate early:** specify the target date, data source, tenant, and run mode. Avoid relying on "today" using the container's default timezone if business rules depend on a local date.
2. **Avoid passing secrets via CLI whenever possible:** process arguments can appear in logs, metadata, or monitoring systems. Use a secret manager, secure environment variables, or an appropriate secret provisioning mechanism.
3. **Design for safe reruns:** a CronJob may relaunch; an API may receive duplicate requests; failure after partial writes may lead to backfill runs. Use business keys, upserts, idempotency keys, transactions, or checkpoints depending on the problem.
4. **Monitor both technical status and business outcomes:** combine exit codes, `TaskExecution` history, logs, metrics, and output data. "No exception" does not guarantee correct business results.
5. **Configure time and resource limits:** maximum runtime, thread count, connection pool size, retry policies, and overdue-run alerts should be part of operational design.
6. **Keep the process finite:** use `spring.main.web-application-type: none` if HTTP is not needed, avoid infinite schedulers, and wait for all child tasks before closing the context.
7. **Manage the repository persistently:** version-appropriate schema, controlled migrations, database permissions, and the ability to inspect abnormal runs.

For example, with a backfill request `--date=2026-11-21`, the runner itself does not know whether that date has already been exported. The service should look up the corresponding business key, detect duplicates, and decide whether to perform a controlled overwrite or skip; meanwhile, `TaskRepository` may still record **a new execution** for that request.

## 11. Common Pitfalls and How to Avoid Them

### Runner Does Not Execute

Check whether the class is actually a Spring bean (`@Component` or `@Bean`), lies within a component-scanned package, is disabled by a profile/conditional, and whether the application context started successfully. A plain Java class's `run(...)` method is not automatically called by Spring Boot if it is not registered as a bean.

### Runner Executes More Times Than Expected

There may be two beans of the same type calling a service, multiple processes/containers launched, or overlapping scheduler triggers. Clearly distinguish between **multiple runners in one process** and **multiple TaskExecutions across multiple processes**. Use conditional runner activation, idempotency, and execution-count monitoring.

### Arguments Are Parsed Incorrectly

With `CommandLineRunner`, `--date=2026-11-23` is a string you must parse manually. With `ApplicationRunner`, read `getOptionValues("date")` and verify there is exactly one value; `containsOption("dry-run")` only checks for the presence of the flag and does not automatically parse `true/false` strings.

### Runner Completes but Process Stays Alive

The application may have started a web server, scheduler, or background threads. Choose a non-web configuration when appropriate; wait for required work, close the context, and return the exit code. Do not call `System.exit(0)` before data has been persisted or futures have completed.

### Task Reports Success Despite Missing Data

This commonly happens due to catching an exception without rethrowing, launching asynchronous work without waiting, or treating "request submitted" as "processing completed." Define **business completion criteria** and allow the runner to return normally only when those criteria are met.

### Results Not Found in TaskRepository

Check `@EnableTask`, dependencies, datasource, schema, profiles, and database permissions. Do not confuse metadata tables with business tables. If the JVM is killed too early or the repository connection fails, a complete end record may not exist.

## 12. Choosing the Right Option and Conclusion

| Context | Appropriate Choice |
|---|---|
| Task only takes a file path from CLI, few arguments | `CommandLineRunner` |
| Task takes `--date`, `--source`, `--dry-run`, flags and named arguments | `ApplicationRunner` |
| Need to track start/end/exit code of an application run | Spring Cloud Task + `TaskRepository`, using a single runner as the entry point |
| Need to invoke multiple services in a business sequence | One runner orchestrating a high-level service with clear flow and transactions |
| Need parallel execution within a single run | Runner invokes a service using `TaskExecutor`/`@Async` and **waits for results** |
| Need step-based batch processing, checkpoints, and restart | Spring Batch; can run inside a Spring Cloud Task application |
| Need scheduled execution | CronJob, scheduler, or orchestrator; runners do not create schedules themselves |

Use **`CommandLineRunner`** when handling raw arguments, **`ApplicationRunner`** when needing structured arguments, and **Spring Cloud Task** to manage the lifecycle, metadata, and execution outcomes of short-lived applications. Whichever runner is used, a run should only be marked complete when **the business work has truly finished**, errors are surfaced clearly, and the process can shut down safely.
