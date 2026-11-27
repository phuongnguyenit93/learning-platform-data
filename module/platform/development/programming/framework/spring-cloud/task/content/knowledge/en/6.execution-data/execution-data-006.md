# Persisting Launch Arguments in TaskExecution

In **Spring Cloud Task**, each launch of a finite-lived processing application creates a **TaskExecution** to track the lifecycle and outcome of that run. Beyond the task name, start/end timestamps, and exit code, **TaskExecution also retains the list of command-line arguments used to launch the application**. This makes it possible, when investigating a data import or report generation run, to tell which file, data period, and processing mode it was invoked with.

This lesson belongs to the **Execution Data** chapter and focuses on passing, persisting, reading back, and governing **launch arguments** in a Spring Cloud Task system backed by a database **TaskRepository**. The examples also clarify boundaries with Spring Boot, Spring Batch, execution errors, and safe operational practices.

## 1. Why Persist Arguments per Run?

Suppose an application is deployed as a short-lived Java process to import orders from partners. Two runs can share the same artifact and task name yet carry different arguments:

~~~bash
java -jar order-import-task.jar \
  --source-id=partner-a-2026-11-23 \
  --business-date=2026-11-23 \
  --dry-run=false

java -jar order-import-task.jar \
  --source-id=partner-b-2026-11-23 \
  --business-date=2026-11-23 \
  --dry-run=true
~~~

Here:

| Argument | Business Meaning | Benefit of Persisting |
| --- | --- | --- |
| `--source-id` | Identifier of the source file or data batch | Cross-check which source was processed |
| `--business-date` | Business date of the dataset | Detect wrong-period processing and support reruns |
| `--dry-run` | Validate only instead of writing data | Distinguish test runs from live runs |

Knowing only the task name `order-import` prevents operators from explaining why order counts differed between two runs. Persisting **arguments linked to the exact TaskExecution ID** keeps history traceable without depending entirely on whether logs are still retained.

Persisting arguments is not the same as **persisting business outcomes**. For instance, lists of imported orders, output report paths, and result checksums typically belong in dedicated business tables or storage.

## 2. What Arguments Does TaskExecution Store?

In the Spring Cloud Task API, `TaskExecution` has an `arguments` property of type **`List<String>`** and a `getArguments()` getter. This is the list of **command-line arguments received by the Spring Boot application**, for example:

~~~text
[
  "--source-id=partner-a-2026-11-23",
  "--business-date=2026-11-23",
  "--dry-run=false"
]
~~~

Typically, when Spring Cloud Task initializes an execution, the framework persists this list via **TaskRepository**. There is no need to write manual `INSERT` statements to store individual arguments.

Distinguish three concepts commonly lumped together as "parameters":

| Kind | Example | Automatically included in `TaskExecution.arguments`? |
| --- | --- | --- |
| **Application command-line arguments** | `--source-id=abc`, `--dry-run=true`, positional arguments | **Yes**: this is the list recorded by Spring Cloud Task |
| **Settings from environment / application.yml** | `DB_URL`, `spring.datasource.url`, YAML file properties | **No** merely because they exist in the environment; they must be passed as arguments to appear in the list |
| **Spring Batch JobParameters** | `businessDate` as string/date, `run.id` for a Batch Job | **Not automatically equivalent**: this is `JobRepository` metadata and requires separate mapping if integrating Batch |

For example, `java -Dmy.property=x -jar task.jar --source-id=abc` passes `-Dmy.property=x` as a **JVM system property**, whereas `--source-id=abc` is an **application argument**. Do not expect every value injected via `@Value` or `Environment` to be saved automatically.

**Key takeaway:** `TaskExecution.arguments` is evidence of *which arguments were passed*. It does not guarantee those values were validated, nor does it capture all environment configuration at runtime.

## 3. Argument Persistence Flow in TaskRepository

~~~mermaid
flowchart TD
    A["Scheduler / API / operator"] --> B["Launch app with command-line arguments"]
    B --> C["Spring Boot receives args"]
    C --> D["Spring Cloud Task creates TaskExecution"]
    D --> E[("TASK_EXECUTION: run metadata")]
    D --> F[("TASK_EXECUTION_PARAMS: each argument")]
    C --> G["ApplicationRunner / CommandLineRunner"]
    G --> H["Process business logic with validated arguments"]
    H --> I["Complete or throw error"]
    I --> J["TaskRepository updates execution outcome"]
~~~

The logical sequence is:

1. **The launcher** starts the Java process with arguments, such as `--source-id=abc`.
2. **Spring Boot** initializes the application and exposes arguments to components such as `ApplicationArguments`, `ApplicationRunner`, or `CommandLineRunner`.
3. **Spring Cloud Task** writes a new `TaskExecution` along with the argument list when the Task lifecycle starts, before runners execute.
4. **Business logic** validates, parses types, and uses the arguments; if an error occurs, the execution is updated with failure details via the lifecycle mechanism.
5. **TaskExplorer** or administrative tools read back the run's metadata and argument list.

`TaskRepository` can persist input metadata successfully even if business logic later fails due to invalid arguments. Conversely, if **ApplicationContext fails to initialize far enough for the Spring Cloud Task lifecycle to start**, there may be no matching `TaskExecution` record; in that case, inspect startup logs and container/job status from the orchestrator.

### 3.1. Related Tables

Under the default relational schema, data is split across two tables:

| Table | Key Columns | Role |
| --- | --- | --- |
| `TASK_EXECUTION` | `TASK_EXECUTION_ID`, `TASK_NAME`, `START_TIME`, `END_TIME`, `EXIT_CODE` | One record per execution |
| `TASK_EXECUTION_PARAMS` | `TASK_EXECUTION_ID`, `TASK_PARAM` | Rows holding the execution's arguments, linked by execution ID |

In the schema published in Spring Cloud Task documentation, `TASK_PARAM` is `VARCHAR(2500)`. Do not use this table to store large JSON payloads or binary data. When choosing a framework version and DBMS, check the DDL bundled with your actual version; configuring a custom **table prefix** also changes table names.

Illustrative sample data:

**TASK_EXECUTION**

| TASK_EXECUTION_ID | TASK_NAME | EXIT_CODE |
| ---: | --- | ---: |
| 4101 | order-import | 0 |
| 4102 | order-import | 1 |

**TASK_EXECUTION_PARAMS**

| TASK_EXECUTION_ID | TASK_PARAM |
| ---: | --- |
| 4101 | `--source-id=partner-a-2026-11-23` |
| 4101 | `--business-date=2026-11-23` |
| 4101 | `--dry-run=false` |
| 4102 | `--source-id=partner-b-2026-11-23` |
| 4102 | `--business-date=2026-11-23` |
| 4102 | `--dry-run=true` |

The IDs and exit codes in these tables are **hypothetical examples**, not data pulled from a running system.

## 4. Spring Boot Example: Receiving and Persisting Arguments

Assume the project already includes a Spring Cloud Task dependency matching your Spring Boot version, a database configured for `TaskRepository`, and the corresponding metadata schema created.

Example `application.yml`:

~~~yaml
spring:
  application:
    name: order-import
  main:
    web-application-type: none
  datasource:
    url: ${DB_URL}
    username: ${DB_USER}
    password: ${DB_PASSWORD}
  cloud:
    task:
      name: order-import
~~~

Supply passwords via a secrets manager or secure environment variables. Never pass passwords as command-line arguments because arguments can remain in **TaskRepository**, shell history, process listings, or logs.

Below is an `ApplicationRunner` that reads arguments. The `OrderImportService` interface represents the business service to implement in a real application:

~~~java
import java.time.LocalDate;
import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class OrderImportTaskApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderImportTaskApplication.class, args);
    }

    @Bean
    ApplicationRunner importOrders(OrderImportService service) {
        return args -> {
            String sourceId = requiredOne(args, "source-id");
            LocalDate businessDate =
                    LocalDate.parse(requiredOne(args, "business-date"));
            boolean dryRun = parseBoolean(
                    requiredOne(args, "dry-run"));

            service.importOrders(sourceId, businessDate, dryRun);
        };
    }

    private static String requiredOne(
            ApplicationArguments args, String key) {
        List<String> values = args.getOptionValues(key);
        if (values == null || values.size() != 1
                || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Expected exactly one --" + key + "=value");
        }
        return values.get(0);
    }

    private static boolean parseBoolean(String value) {
        if ("true".equalsIgnoreCase(value)) {
            return true;
        }
        if ("false".equalsIgnoreCase(value)) {
            return false;
        }
        throw new IllegalArgumentException(
                "--dry-run must be true or false");
    }
}

interface OrderImportService {
    void importOrders(
            String sourceId, LocalDate businessDate, boolean dryRun);
}
~~~

Launch command:

~~~bash
java -jar order-import-task.jar \
  --source-id=partner-a-2026-11-23 \
  --business-date=2026-11-23 \
  --dry-run=false
~~~

In this example, `ApplicationArguments` **extracts and validates** values by name, while **Spring Cloud Task automatically saves the raw argument list** in `TaskRepository`. Calling `requiredOne` is not an "argument-writing" operation; it simply prevents missing, blank, or duplicated keys. `LocalDate.parse` and `parseBoolean` ensure valid types for business logic.

Note for production use: the project must provide a bean implementing `OrderImportService`; the example only demonstrates argument handling. Input arguments should undergo further validation for length limits, source code formats, resource access permissions, and business rules.

## 5. Reading Arguments Back by TaskExecution ID

Once an execution ID is known, **TaskExplorer** can read `TaskExecution` from the repository. This API is purpose-built for querying execution history; there is no need to parse tables manually in application code.

~~~java
import java.util.List;

import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.cloud.task.repository.TaskExplorer;
import org.springframework.stereotype.Service;

@Service
public class TaskExecutionLookup {

    private final TaskExplorer taskExplorer;

    public TaskExecutionLookup(TaskExplorer taskExplorer) {
        this.taskExplorer = taskExplorer;
    }

    public List<String> findLaunchArguments(long executionId) {
        TaskExecution execution =
                taskExplorer.getTaskExecution(executionId);

        if (execution == null) {
            throw new IllegalArgumentException(
                    "TaskExecution not found: " + executionId);
        }
        return List.copyOf(execution.getArguments());
    }
}
~~~

Example output from `findLaunchArguments(4101L)`:

~~~text
--source-id=partner-a-2026-11-23
--business-date=2026-11-23
--dry-run=false
~~~

The result is a list of **String**. If an admin portal wants to render a "key → value" form, it must parse entries per application conventions and handle positional arguments, repeated keys, or values containing `=`. Never blindly assume every element follows `--key=value`.

On security: `TaskExecutionLookup` is an internal access class illustrating the API. If exposed via an HTTP endpoint, authorize requests before returning data, and return a **view with sensitive parameters masked** rather than dumping the entire list verbatim.

### 5.1. SQL Query for Investigation

When reconciling directly in the database, you can use:

~~~sql
SELECT e.TASK_EXECUTION_ID,
       e.TASK_NAME,
       e.START_TIME,
       e.END_TIME,
       e.EXIT_CODE,
       p.TASK_PARAM
FROM TASK_EXECUTION e
LEFT JOIN TASK_EXECUTION_PARAMS p
       ON p.TASK_EXECUTION_ID = e.TASK_EXECUTION_ID
WHERE e.TASK_EXECUTION_ID = :execution_id;
~~~

The `:execution_id` notation is a **bind parameter** for a data access layer (such as named-parameter JDBC); when running in a SQL client, substitute the placeholder supported by your client.

Each `TaskExecution` can appear across **multiple rows** when it has multiple arguments. `LEFT JOIN` ensures the execution record remains visible even if it has zero arguments. Do not rely on SQL row order to determine argument order, because the parameter table has no explicit sequence column by default.

When searching for runs matching a specific `source-id`, you can query the parameter table for ad-hoc investigation. However, if you need **frequent lookups, uniqueness enforcement, or duplicate-run prevention by source-id**, design a business table with structured keys; running `LIKE` queries against `TASK_PARAM` strings is not a reliable idempotency mechanism.

## 6. Arguments, Business Identity, and Reruns

Running the exact same command twice creates **two distinct TaskExecutions** if each invocation starts a new Task process:

~~~text
Run A: executionId = 4101
       source-id = partner-a-2026-11-23
       status = COMPLETED

Run B: executionId = 4103
       source-id = partner-a-2026-11-23
       status = COMPLETED
~~~

Spring Cloud Task **records runs**; it does not automatically infer that a repeated `--source-id` should skip the second execution. Duplicate-handling rules belong to business logic.

For the order-import task, state per `source-id` can be managed in a dedicated table:

~~~sql
CREATE TABLE import_run (
    source_id        varchar(200) PRIMARY KEY,
    source_checksum  varchar(128) NOT NULL,
    status           varchar(30) NOT NULL,
    completed_at     timestamp NULL
);
~~~

Before importing, check/claim processing rights on the `source_id` key using an appropriate transaction and unique constraint. Then process idempotently, save checkpoints if needed, reconcile totals, and mark completion. If a new run arrives with the same `source-id` but a different checksum, handle it according to versioning/conflict policy instead of silently ignoring it.

| Concept | Example | Responsibility |
| --- | --- | --- |
| **TaskExecution ID** | `4101` | Distinguishes each technical run |
| **Task name** | `order-import` | Categorizes the job type |
| **Launch argument** | `--source-id=partner-a-2026-11-23` | Records the request input passed to the run |
| **Business key** | `partner-a-2026-11-23` | Reconciles data, prevents duplicate processing, decides reruns |
| **Business status** | `IMPORTED`, `REJECTED` | Indicates source or output processing outcome |

Seeing the same `--source-id=...` entry across multiple `TaskExecution` records is **normal** during retries. History tracking should correlate each attempt with the business state at that time.

## 7. Interaction with Spring Batch

When Spring Cloud Task launches a **Spring Batch Job**, two distinct metadata layers exist:

- **TaskExecution / TaskRepository:** stores **application** launch arguments and process lifecycle.
- **JobExecution, JobInstance, and JobParameters / JobRepository:** stores **Batch Job** details and parameters used to identify/restart Jobs according to Spring Batch rules.

Example orchestrator invocation:

~~~bash
java -jar order-import-task.jar \
  --source-id=partner-a-2026-11-23 \
  --business-date=2026-11-23
~~~

The application can validate both arguments and construct corresponding `JobParameters` for the Batch Job. That mapping must be explicit or driven by configured launcher mechanics; **never treat `TASK_EXECUTION_PARAMS` and `JobParameters` metadata as a shared table**.

This matters for restarts: a new `TaskExecution` only indicates **a new process** ran; Spring Batch uses the Job configuration and **identifying JobParameters** to decide which `JobInstance` the invocation belongs to, and whether to restart or create a new instance.

To reconcile when the system supports Task–Batch linking, use `TaskExplorer.getJobExecutionIdsByTaskExecutionId(executionId)` rather than guessing a `JobExecution` ID from a `TaskExecution` ID.

## 8. Security and Reliability of Argument Data

### 8.1. Never Pass Secrets as Arguments

**Unsafe** example:

~~~bash
# DO NOT do this: the token becomes an application argument.
java -jar task.jar --api-token=actual-secret-token
~~~

These values can appear in **TASK_EXECUTION_PARAMS**, process management tools, shell history, and logs. Masking them with `***` on a UI screen after the run **does not erase** the value already saved in the repository.

Instead, supply secrets through a secret store or secure deployment configuration. Pass only **non-secret** reference identifiers as arguments, for example:

~~~bash
java -jar task.jar \
  --source-id=partner-a-2026-11-23 \
  --credential-ref=partner-a-import
~~~

The application fetches credentials from the appropriate vault/store and never logs tokens or writes them into `TaskExecution` results, exception messages, or business tables. Even file names, paths, and IDs can leak data; choose minimal identifiers.

### 8.2. Limits and Validation Policies

| Risk | Mitigation |
| --- | --- |
| Arguments contain tokens/passwords/PII | Do not pass secrets; restrict allowed keys; control read access to TaskRepository |
| String exceeds `TASK_PARAM` capacity | Validate input length; store payloads in object storage and pass only a reference |
| Missing or duplicated keys | Enforce presence and single value for required options |
| Invalid or out-of-range dates | Parse strict formats, enforce time zone handling, and bound allowed ranges |
| Two tasks share the same business key | Business unique constraints/locks and duplicate-handling logic |
| Logs accidentally dump all `args` | Log only approved arguments, mask sensitive data, and manage log retention |
| TaskRepository purged too early | Align retention policies with audit requirements and related tables |

### 8.3. Principles for Designing Good Arguments

Prefer **stable, self-explanatory, and reproducible** arguments:

~~~text
--source-id=partner-a-2026-11-23
--business-date=2026-11-23
--operation=import
--dry-run=false
~~~

Avoid arguments whose meaning shifts over time without pinning, such as `--date=today`. When rerunning days later, `today` could point to a different dataset. It is far better for the orchestrator to compute the concrete business date and pass that value to the application.

Similarly, passing `--input-uri` pointing to mutable content does not guarantee reproducibility. When strict auditing is required, attach a `source-version`, checksum, or immutable object identifier.

## 9. Operations: Verifying Data After Execution

A verification workflow can follow these steps:

1. Prepare `TaskRepository` in a persistent database with a schema compatible with your Spring Cloud Task version.
2. Launch the task with **secret-free** arguments and note the execution ID via logs/observability or history queries.
3. Call `TaskExplorer.getTaskExecution(id)` to fetch `TaskExecution` and read `getArguments()`, or query `TASK_EXECUTION_PARAMS`.
4. Cross-check `TASK_EXECUTION_ID`, `TASK_NAME`, `EXIT_CODE`, start/end timestamps, arguments, and business state.
5. Rerun with the same business key and verify a **new execution ID** alongside idempotent behavior in target data.
6. Try an invalid `--business-date` value and confirm the failure is reflected in the orchestrator, logs, and metadata if the Task started.

**Observe cautiously:** if `END_TIME` is blank, a run may be **still executing or terminated abnormally before recording final state**. Never assume the process is alive; cross-check with the Job/Pod, timeouts, and monitoring systems.

If arguments are missing, check in sequence:

| Symptom | Possibility and What to Check |
| --- | --- |
| `TaskExecution` exists without rows in `TASK_EXECUTION_PARAMS` | Verify arguments were actually passed to the app; distinguish env/JVM properties from app arguments |
| No `TaskExecution` | Check `ApplicationContext` startup, datasource, schema, DB permissions, and Spring Cloud Task configuration |
| Lookup by ID returns `null` | Verify target environment, repository, table prefix, and execution ID |
| Arguments differ from expectations | Check how the launcher escapes spaces, values with `=`, repeated options, and wrapper shell scripts |
| Query returns multiple rows per execution ID | By design: one row per argument; group/process the result set by execution ID |
| Task reports success yet target data is wrong | Reconcile business logic; argument metadata does not replace output verification |

## 10. Hands-On Exercise

Build an `invoice-report-task` application accepting three arguments:

~~~text
--tenant-id=acme
--report-date=2026-11-23
--format=csv
~~~

Requirements:

1. Use `ApplicationArguments` to validate exactly one `tenant-id`, a `LocalDate` `report-date`, and `format` in `csv` or `json`.
2. Run the task twice with two different dates and use `TaskExplorer` to read both `arguments` lists back; confirm each run has its own execution ID.
3. Omit `--report-date` and observe the failure; cross-check `TaskExecution` metadata and process status.
4. Rerun a report date that already produced output. Place a business key **(`tenant-id`, `report-date`, `format`)** on the report table to prevent unintended duplicate issuance.
5. Test an argument containing a very long string and an argument with a repeated key. Explain how validation prevents repository errors and data ambiguity.
6. Verify that no secrets or sensitive personal data were persisted in `TASK_EXECUTION_PARAMS`.

**Completion criteria:** the learner accurately distinguishes **arguments at invocation**, **the persisted `TaskExecution.arguments` list**, **Spring Batch Job parameters** (if applicable), and **business outcomes**.

## 11. Summary

- **TaskExecution** stores application arguments as `List<String>`; `TaskRepository` persists them in **`TASK_EXECUTION_PARAMS`** linked by execution ID.
- **ApplicationArguments** lets the application read, validate, and convert argument types; there is no need to manually `INSERT` arguments into Spring Cloud Task tables.
- **TaskExplorer** queries history by execution ID; SQL helps investigate runs, keeping in mind each run can have multiple parameter rows.
- **Rerunning with identical arguments** still creates a new technical execution. Business keys, unique constraints, and idempotency determine whether data may be processed again.
- **Never pass secrets in command-line arguments**, as values can persist long-term in `TaskRepository` and related monitoring tools.
- When integrating Spring Batch, keep `TaskExecution` metadata separate from `JobExecution`/`JobParameters` metadata.

### References

- [Spring Cloud Task Reference Guide — TaskExecution, TaskRepository, and schema](https://docs.spring.io/spring-cloud-task/docs/current/reference/htmlsingle/)
- [Javadoc: TaskExecution](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/repository/TaskExecution.html)
- [Javadoc: TaskExplorer](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/repository/TaskExplorer.html)
