# Use Cases: Data Import, Reporting, and Maintenance

Spring Cloud Task fits jobs **with a clear start and end point**: reading a data file and importing it into the system, generating periodic reports, or cleaning up expired data. Each launch is an independent execution; the application completes the work and terminates the process. Spring Cloud Task records execution information in a database via **TaskRepository**, helping answer: which task ran, when did it start, has it ended yet, what was the exit code, and if it failed, what was the error.

This lesson focuses on **designing and operating three real-world task groups**, not just how to bootstrap a Spring Boot application. After completing it, you will be able to choose how to structure tasks, define input arguments, organize safe re-runs, integrate Spring Batch when needed, and observe outcomes through metadata.

## 1. Identifying the Problem Properly

An HTTP server serves requests continuously; a Spring Cloud Task is typically launched to complete **a finite unit of work**. It can be triggered manually, on demand from another system, or on a schedule by an external tool. **Spring Cloud Task does not provide a scheduler itself**; Cron, Kubernetes CronJob, a workflow orchestrator, or a task-invoking service is responsible for triggering the process.

| Use Case | Inputs and Outputs | Completion Criteria | Re-run Risks |
| --- | --- | --- | --- |
| **Data Import** | CSV file, objects on object storage, partner records → business tables | All valid records accepted or clear error-handling results recorded | Duplicate writes, reprocessing already-imported records, repeated side effects |
| **Reporting** | Time range, business unit, report type → summary table or exported file | Results calculated, validated, and stored in an accessible location | Generating uncontrolled versions, sending duplicate reports, using mismatched data periods |
| **Maintenance** | Cutoff timestamp, retention policy, batch size → cleaned-up data | No remaining records to process within defined scope or work limit reached | Deleting beyond scope, long table locks, impacting actively used data |

**Design principle:** each run must have a *business identity* such as a source file ID, report date, or data cutoff date. **TaskExecution ID** technically distinguishes runs; it does not replace the business key used to prevent duplicates.

### General Execution Flow

~~~mermaid
flowchart LR
    A["Cron / API / Operational action"] --> B["Launch Spring Boot process"]
    B --> C["Spring Cloud Task"]
    C --> D["Import / report / maintenance logic"]
    C --> E[("TaskRepository: execution metadata")]
    D --> F[("Business DB / object storage")]
    D --> G["Logs, metrics, business outcomes"]
    C --> H["Process termination / exit code"]
~~~

TaskRepository stores **process metadata**; meanwhile, imported record counts, report file paths, or lists of deleted records should be stored in business tables, structured logs, or an appropriate observability system. Do not assume Spring Cloud Task's metadata tables are the place to store all detailed results.

## 2. Common Foundation for the Three Task Types

The sample application uses Spring Boot, Spring Cloud Task, JDBC, and PostgreSQL. When building a real project, choose **compatible** Spring Boot and Spring Cloud Task versions according to the ecosystem BOM you use, and manage TaskRepository table schemas via an initialization or migration mechanism suitable for the environment.

Example of important Maven dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Spring Cloud version management is declared in **dependencyManagement** using a compatible BOM; the example above only illustrates the required dependencies.

Typical configuration:

~~~yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: ${DB_URL}
    username: ${DB_USER}
    password: ${DB_PASSWORD}
  cloud:
    task:
      name: data-operations
~~~

Connection values are supplied via environment variables or a secret management system—never hardcode passwords in source code. The metadata database must have **the Spring Cloud Task schema matching the library version and database engine** before running in production. When metadata and business data reside in separate datasources, explicitly configure which DataSource is dedicated to TaskRepository.

An application can accept the operation type via arguments. For clear illustration, the example below uses three business services: **ImportService**, **ReportService**, and **MaintenanceService**. These services correspond to the implementations for the three scenarios in the following sections.

~~~java
@SpringBootApplication
@EnableTask
public class DataOperationsApplication {
    public static void main(String[] args) {
        SpringApplication.run(DataOperationsApplication.class, args);
    }

    @Bean
    ApplicationRunner execute(
            ImportService imports,
            ReportService reports,
            MaintenanceService maintenance) {

        return args -> {
            String operation = required(args, "operation");

            switch (operation) {
                case "import" -> imports.importSource(
                        required(args, "source-id"),
                        required(args, "input"));

                case "report" -> {
                    String reportDate = optional(
                            args, "date",
                            LocalDate.now(ZoneId.of("Asia/Ho_Chi_Minh"))
                                    .minusDays(1)
                                    .toString());
                    reports.generate(LocalDate.parse(reportDate));
                }

                case "cleanup" -> {
                    String mode = optional(args, "mode", "preview");
                    if (!mode.equals("preview") && !mode.equals("execute")) {
                        throw new IllegalArgumentException(
                                "mode must be preview or execute");
                    }
                    maintenance.clean(
                            Instant.parse(required(args, "cutoff")),
                            mode.equals("execute"));
                }

                default -> throw new IllegalArgumentException(
                        "Unsupported operation: " + operation);
            }
        };
    }

    private static String required(ApplicationArguments args, String name) {
        List<String> values = args.getOptionValues(name);
        if (values == null || values.size() != 1 || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Expected exactly one --" + name + "=value");
        }
        return values.get(0);
    }

    private static String optional(
            ApplicationArguments args, String name, String defaultValue) {
        if (!args.containsOption(name)) {
            return defaultValue;
        }
        return required(args, name);
    }
}
~~~

Java imports and service implementations are omitted to highlight the task entry point. The **--** prefix passes options to the application; for example:

~~~bash
java -jar data-operations.jar --operation=import --source-id=partner-A-2026-11-24 --input=/data/orders.csv
java -jar data-operations.jar --operation=report --date=2026-11-23
java -jar data-operations.jar --operation=cleanup --cutoff=2026-10-01T00:00:00Z --mode=preview
~~~

In large environments, the three task types can be split into **three separate applications or three images** to deploy, scope permissions, and allocate resources independently. Combining them into one application here is primarily to illustrate argument-based routing.

Input errors must lead to an explicit failure; do not catch all exceptions only to log and continue as if processing succeeded. The orchestrator needs the process exit code, while operators need logs and metadata for diagnosis.

## 3. Scenario A: Importing Data from a Partner

### 3.1. Problem and Design Decisions

Every night, a partner sends a transaction file. The file might be redelivered due to timeouts, or the system might need to re-run due to a database connection drop. If the program simply loops through rows and runs INSERT, a re-run will easily generate duplicate data.

A reliable import process needs to separate three kinds of state:

1. **Import source:** file identifier, checksum, version, ingestion timestamp.
2. **Business record:** external key provided by the partner and normalization/validation results.
3. **Execution:** TaskExecution ID, start/end timestamps, exit code, and errors.

For example, the partner re-sends a file with the same **source-id**. If the checksum is unchanged, you can skip the already-completed source entirely or resume unprocessed portions. If the checksum differs, treat it as a conflict or a new version according to defined rules; do not silently overwrite data.

### 3.2. Proposed Processing Flow

~~~mermaid
flowchart TD
    A["Receive source-id and file location"] --> B{"Already completed this source?"}
    B -- Yes, matching checksum --> C["Record already processed; finish"]
    B -- No --> D["Validate file, format, checksum"]
    B -- Different checksum --> X["Report version conflict"]
    D --> E["Read and validate records in batches"]
    E --> F["Upsert using business key"]
    F --> G{"More records?"}
    G -- Yes --> E
    G -- No --> H["Reconcile totals and mark completed"]
~~~

Example target table using PostgreSQL:

~~~sql
CREATE TABLE imported_order (
    source_id    varchar(200) NOT NULL,
    external_id  varchar(200) NOT NULL,
    amount       numeric(18, 2) NOT NULL,
    PRIMARY KEY (source_id, external_id)
);

INSERT INTO imported_order (source_id, external_id, amount)
VALUES (:source_id, :external_id, :amount)
ON CONFLICT (source_id, external_id)
DO UPDATE SET amount = EXCLUDED.amount;
~~~

The unique key constraint ensures re-running the same data does not create extra rows. However, **upsert is only part of idempotency**: if each row also triggers sending an email, charging money, or calling a partner API, you must have separate deduplication mechanisms for those side effects. If source transactions can change, clarify whether business rules allow updating, rejecting, or creating versions.

For small files, the service can use a compliant CSV parser, validate each row, and invoke JDBC. Do not split CSV lines manually by commas because field values can contain commas, quotes, and newlines. For large files, **Spring Batch** is a better fit thanks to chunk-oriented reading/writing, step-level state, and controlled restartability.

### 3.3. Error Handling and Re-runs

| Incident | Handling Approach |
| --- | --- |
| File has invalid header or missing required columns | Fail fast, record source validation error; do not mark source as successful |
| Some rows are invalid | Define a policy to reject the whole file or store a list of failed rows; state acceptance thresholds explicitly |
| Database connection drops midway | Roll back current transaction; on next run, rely on business key and checkpoint to continue processing |
| Same file received again | Compare source-id and checksum, ensuring row count does not increase |
| Two versions with the same source-id | Report a conflict or manage versions explicitly; do not automatically pick the latest |

**Verification point:** running the same file twice must produce identical business outcomes; valid row count, rejected row count, and total imported amount must reconcile with the source. TaskRepository indicates whether the **run** succeeded or failed, while the import status table must describe whether the **data source** is complete.

## 4. Scenario B: Generating Periodic Reports

### 4.1. Defining the Data Period Before Computing

Suppose the system needs a revenue report for the previous business day, displayed in Vietnam time. The **date** argument specifies the business day, and the reporting logic converts the time window in the **Asia/Ho_Chi_Minh** timezone into two UTC bounds: **[from, to)**. A half-open interval avoids double-counting transactions right at the day boundary.

Example aggregation query (using the data access layer's named parameter syntax, not literal SQL to run verbatim in psql):

~~~sql
SELECT currency,
       COUNT(*) AS transaction_count,
       SUM(amount) AS total_amount
FROM payment
WHERE status = 'SETTLED'
  AND paid_at >= :from_utc
  AND paid_at <  :to_utc
GROUP BY currency;
~~~

Data rules must specify conventions for late-arriving, canceled, or adjusted transactions after the cutoff day. If a report is allowed to change, use version numbers or cutoff timestamps so readers know which snapshot they are viewing.

### 4.2. Safe Output Delivery

A report generation run should execute in the following order:

1. Determine the **report key** from report type, period, and version; check if a successful release already exists.
2. Snapshot or establish a consistent data cutoff, compute aggregations, and reconcile counts.
3. Write the file to a temporary location; validate size, checksum, and basic content.
4. Move the file to its official location atomically to the extent supported by the storage system, then update status to **READY** in the results table.
5. Only send notifications through a deduplicated mechanism (such as an outbox) after the output is ready.

Example business output model:

| Field | Role |
| --- | --- |
| report_type, business_date, version | Logical identity key of the report |
| source_watermark | Input data watermark used |
| artifact_uri, checksum | Storage location and file integrity |
| status | PENDING, READY, FAILED per business workflow |
| generated_at | Timestamp of successful publication |

If the process crashes after uploading the file but before updating the database, the next run checks the **report key** and existing file to finalize without duplicating work. If the notification step fails, do not mark the entire calculation as failed and re-send old notifications multiple times.

**Distinguishing the two outcomes:** Spring Cloud Task answers "how did the report-generation process end?", while the report table answers "which report version is currently ready for users to download?".

## 5. Scenario C: Data Maintenance and Cleanup

### 5.1. Setting Scope Before Deleting

Maintenance tasks commonly include deleting expired login sessions, archiving old records, recomputing business indexes, or reclaiming temporary data. They may be short, yet they directly impact system integrity and performance.

Policy example: delete sessions that expired **before cutoff**. Do not sample the current time inside every loop iteration because the scope will shift over time; lock the cutoff at the very start and record it in logs/business results.

Before mutating data, run a **preview**: count qualifying records, sample keys, check dependencies, and estimate size. The **execute** mode must be specified explicitly. You can combine this with confirmation from the orchestration system for particularly sensitive tasks.

### 5.2. Bounded Batch Deletion

A single massive DELETE statement can hold locks for a long time and cause I/O spikes. Execute in small batches, each batch in its own transaction, measure duration, and tune batch size to actual load. PostgreSQL example:

~~~sql
WITH victims AS (
    SELECT id
    FROM user_session
    WHERE expires_at < :cutoff
    ORDER BY id
    LIMIT :chunk_size
)
DELETE FROM user_session s
USING victims v
WHERE s.id = v.id;
~~~

Repeat until the deleted row count reaches 0 or the defined time/batch limit is reached. Ensure indexes match the filter predicates and ordering; for large tables, test the execution plan and lock footprint in an equivalent staging environment.

If the job must span multiple runs, save a **checkpoint** or re-query remaining qualifying records. Explicitly design which data may be updated concurrently, which data must be retained for legal/compliance requirements, and when archiving is needed instead of hard deletion. Do not automatically purge Spring Cloud Task's **TASK_EXECUTION** metadata tables as part of business maintenance without a dedicated retention policy.

### 5.3. Safety Rules for Execution

| Mechanism | Purpose |
| --- | --- |
| Preview by default, execute only when specified | Reduces the chance of accidentally running destructive operations |
| Fixed cutoff, clear retention policy | Prevents deletion scope from expanding unintentionally |
| Bounded batch size, timeout, and processing rate | Avoids overload and overly long transactions |
| Overlap prevention or distributed locks | Prevents two processes from acting on the same data range and contending |
| Log expected, processed, failed counts, and duration | Aids reconciliation and performance evaluation |
| Recovery or archive procedure before deletion | Ensures ability to recover from business mistakes |

For data-repair tasks, **safe re-running** also means only processing records that have not yet reached the target state—not merely checking whether a previous process was invoked.

## 6. Scheduled Triggers, On-Demand Triggers, and Overlap Control

The three tasks can share the metadata recording mechanism while **differing in how they are triggered**:

- **Data import:** triggered when a file is received or when an operator requests reprocessing a source-id.
- **Reporting:** run after the data cutoff milestone, on a daily/weekly schedule, or when a user requests regenerating a period.
- **Maintenance:** typically run during off-peak hours and can impose limits on record count or duration per run.

Example Kubernetes CronJob for the report-generation application. The image must be packaged with an entrypoint executing the JAR file; the application selects the report date based on configured business-date rules if no date is passed.

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-report
spec:
  schedule: "0 2 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      backoffLimit: 1
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: task
              image: registry.example/data-operations:1.0.0
              args:
                - "--operation=report"
~~~

**Note:** the timeZone field requires a supported Kubernetes version; if the cluster does not support it yet, convert the schedule in the orchestrator. **concurrencyPolicy: Forbid** prevents overlapping Jobs belonging to the same CronJob, but does not stop a user from launching an equivalent task via an API or CLI. For requirements like "only one release per period", add a unique constraint or business lock in the database.

An API accepting launch requests should not hold an HTTP connection open waiting for several minutes. It can create a request, submit it to the Job launcher, and return an identifier for other systems to query status. Avoid creating a TaskExecution as if the task already succeeded as soon as the request is accepted; distinguish between **requested**, **running**, and **completed**.

## 7. Tracking Execution with TaskRepository

Spring Cloud Task records start/end times, task name, arguments, and execution outcomes. With the standard relational schema, the **TASK_EXECUTION** table provides columns such as **TASK_EXECUTION_ID, TASK_NAME, START_TIME, END_TIME, EXIT_CODE, EXIT_MESSAGE, ERROR_MESSAGE**. Exact column names and DDL must be verified against the schema bundled with the version you are running.

Example query to inspect the most recent runs:

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE,
       EXIT_MESSAGE
FROM TASK_EXECUTION
ORDER BY TASK_EXECUTION_ID DESC
LIMIT 20;
~~~

How to interpret:

| Observation | Meaning and Next Check |
| --- | --- |
| Has END_TIME and success exit code | Process completed; also verify corresponding business outcomes |
| Has END_TIME and error exit code | Inspect logs, ERROR_MESSAGE, arguments, and input data for that run |
| Has START_TIME but no END_TIME yet | May still be running or may have died abnormally; check process/Job status and timeouts |
| No execution record found | Verify the app reached the Task lifecycle, metadata DB connectivity, migrations, and TaskRepository config |

Do not assume that a record with a **blank END_TIME** is always still running: the process could have been killed before updating it. Detecting "hanging" runs requires combining maximum runtime limits, heartbeats/logs, and container or launcher status.

At the application layer, log structured fields with **executionId** (when available), operation, business key, read/written/skipped row counts, duration, and error code. Keep sensitive information out of logs. The orchestrator should monitor execution duration, exit codes, and error rates; use repository queries for historical investigation.

### Handling Exit Codes and Errors

- **Success:** business logic completes, writes results, and lets the process terminate normally.
- **Retryable error:** e.g., temporary connection loss; throw an exception or explicitly report failure so the launcher knows the run failed, then retry within bounds.
- **Permanent data error:** e.g., invalid CSV schema; log a clear reason, stop, and require fixing the source before re-running.
- **Abnormal death:** do not rely solely on end-of-process listeners; have a way to detect expired runs and reconcile incomplete states.

If the application catches all exceptions without propagating errors or an appropriate exit code, the orchestration system may treat the task as successful even though data was never processed.

## 8. When to Combine with Spring Batch?

**Spring Cloud Task** manages the lifecycle and metadata of **processes with finite runtimes**. **Spring Batch** provides the **Job/Step** model, chunk-oriented read–process–write, checkpoints, policy-driven retry/skip, and detailed batch job metadata. Both tools can work together in the same application: one Spring Cloud Task execution runs an appropriate Batch Job or sequence of Jobs.

| Requirement | Recommendation |
| --- | --- |
| Read a small file, call an API, and write simple output | Spring Cloud Task with ApplicationRunner/CommandLineRunner |
| Import millions of records, needing checkpoint-based restarts | Spring Cloud Task combined with Spring Batch |
| Report consisting of a single aggregation query and one output file | Spring Cloud Task may be sufficient |
| Multi-step ETL report processing chunks and needing step tracking | Spring Cloud Task combined with Spring Batch |
| Small-batch data deletion with controlled loop | Spring Cloud Task; consider Batch if complex checkpoints/steps are needed |

When combined, **TaskRepository** and **JobRepository** serve different purposes, requiring corresponding schemas and clear transaction configuration. Do not equate **TaskExecution** with **JobExecution**; one Task process can be associated with one or multiple Job executions. For restartable Jobs, design **JobParameters** to accurately identify the data version and avoid accidentally creating a new Job instance on every retry.

## 9. Pre-Production Operations Checklist

| Category | Verification Question |
| --- | --- |
| Inputs | Are required arguments validated? Do paths, report periods, and cutoffs have valid formats and bounds? |
| Idempotency | Does re-running after completion or partial failure produce duplicate data or side effects? |
| Transactions | Are transaction boundaries short enough? What partial processing states are acceptable? |
| Metadata | Is TaskRepository provisioned with the right schema, read/write permissions, and appropriate backups? |
| Errors | Can data errors, transient errors, timeouts, and process crashes be distinguished and monitored? |
| Orchestration | Are retry limits, timeouts, concurrency limits, and CPU/RAM resources configured? |
| Security | Are only necessary data permissions granted, secrets passed through secure channels, and personal data masked in logs? |
| Reconciliation | Are record counts, checksums, report keys, or recovery details available to confirm outputs? |
| Operations | Is there a runbook for viewing history, re-running by business key, stopping tasks, and handling stale metadata? |

### Hands-On Exercise

Design three practical run commands for a sales/order system:

1. **Import**: accept a file containing 10,000 orders. Run the first time, re-run identically, then simulate a database failure mid-batch. Reconcile total order counts to prove no duplicates occurred.
2. **Report**: generate a report for one day in the business timezone. Re-run for the same date and verify that report key, version, and file checksum are controlled; test transactions occurring right at the day boundary.
3. **Cleanup**: preview the count of expired sessions before cutoff, run execute with small chunks, interrupt the process midway, and resume. Compare row counts before/after and confirm no records newer than cutoff were deleted.

For each run, record **TaskExecution ID**, business key, exit code, output results, and error reasons if any. Then query TaskRepository to distinguish successful runs, failed runs, and runs without an end timestamp.

## 10. Key Takeaways

- Spring Cloud Task is especially useful for **finite work requiring execution traceability**; schedules and triggers are provided by other tools.
- **Import** prioritizes business keys, source validation, idempotency, and recovery after partial failure.
- **Reporting** prioritizes consistent data periods, report keys, safe file delivery, and avoiding duplicate notifications.
- **Maintenance** prioritizes scope limits, previews, batch processing, load control, and recovery plans.
- **TaskRepository** records the technical outcome of a run; **business outcome data** must be managed separately. When large-volume processing with checkpoints and steps is needed, integrate Spring Batch.
