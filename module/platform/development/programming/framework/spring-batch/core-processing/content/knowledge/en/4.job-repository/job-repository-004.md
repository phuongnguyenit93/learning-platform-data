# Repository Schema and Metadata Tables

In Spring Batch, `JobRepository` is where metadata about Jobs, Job runs, and Step runs is stored. With a JDBC configuration, metadata is stored in a group of relational tables that usually have the `BATCH_` prefix. These tables help Spring Batch identify a Job instance, track each run, record status and counters, store launch parameters, and keep checkpoints to support restart.

The metadata tables are the foundation for important Spring Batch capabilities: preventing a duplicate run of a Job instance that is already active, viewing execution history, controlling restart, tracking progress, and looking up errors. Therefore, the repository schema needs to be created in the correct version, stored durably, and managed as part of the application infrastructure.

## 1. JobRepository and the Metadata Repository

`JobRepository` is the abstraction Spring Batch uses to store and retrieve execution information. When JobLauncher launches a Job, the framework uses the repository to find or create a `JobInstance`, create a `JobExecution`, create a `StepExecution`, and update status throughout the run.

With a JDBC JobRepository, metadata is stored in a relational database. This is a common implementation in applications that need to keep history across restarts, support multiple processes, or need operational tools to look up executions.

The metadata repository stores information that controls how a Batch runs, for example:

- The Job name and the identity of a Job instance.
- The JobParameters used to launch the Job.
- The start time, end time, and last update time of each execution.
- The `BatchStatus`, `ExitStatus`, and error messages.
- The number of items read, written, filtered, skipped, and the number of commits and rollbacks.
- The `ExecutionContext` of the Job and Step, including checkpoints for restart.

The metadata repository is not where all the processed business data is stored. Orders, transactions, customers, or the content of input files still belong to the application's database or business systems. The `BATCH_*` tables only store the state and information needed to orchestrate, monitor, and recover the Batch process.

## 2. The Main Metadata Tables

A standard JDBC JobRepository usually uses the following six groups of tables:

| Table | Role |
|---|---|
| `BATCH_JOB_INSTANCE` | Stores the identity of each JobInstance. |
| `BATCH_JOB_EXECUTION` | Stores each run of a JobInstance. |
| `BATCH_JOB_EXECUTION_PARAMS` | Stores the launch parameters of a JobExecution. |
| `BATCH_STEP_EXECUTION` | Stores each Step run belonging to a JobExecution. |
| `BATCH_JOB_EXECUTION_CONTEXT` | Stores the ExecutionContext at the JobExecution scope. |
| `BATCH_STEP_EXECUTION_CONTEXT` | Stores the ExecutionContext at the StepExecution scope. |

Table names can change if a different table prefix is configured. For example, the prefix `APP_BATCH_` will produce corresponding names such as `APP_BATCH_JOB_INSTANCE` and `APP_BATCH_STEP_EXECUTION`, depending on the repository configuration.

General relationship diagram:

```text
BATCH_JOB_INSTANCE
  JOB_INSTANCE_ID (PK)
       |
       | 1 - N
       v
BATCH_JOB_EXECUTION
  JOB_EXECUTION_ID (PK)
  JOB_INSTANCE_ID (FK)
       |
       +--------------------------+
       |                          |
       | 1 - N                    | 1 - 1
       v                          v
BATCH_STEP_EXECUTION       BATCH_JOB_EXECUTION_PARAMS
  STEP_EXECUTION_ID (PK)     JOB_EXECUTION_ID (FK)
  JOB_EXECUTION_ID (FK)
       |
       | 1 - 1
       v
BATCH_STEP_EXECUTION_CONTEXT

BATCH_JOB_EXECUTION
       |
       | 1 - 1
       v
BATCH_JOB_EXECUTION_CONTEXT
```

The diagram shows the main logical relationships. The details of keys, indexes, data types, and how IDs are generated depend on the schema script for the database management system and the Spring Batch version in use.

## 3. The BATCH_JOB_INSTANCE Table

`BATCH_JOB_INSTANCE` stores one identity for each JobInstance. A JobInstance is determined by the Job name and the set of JobParameters that have the identifying attribute.

The important columns usually include:

| Column | Meaning |
|---|---|
| `JOB_INSTANCE_ID` | Primary key, the ID of the JobInstance. |
| `VERSION` | A version value used to control concurrent updates. |
| `JOB_NAME` | The Job name. |
| `JOB_KEY` | An identifying value generated from the identifying JobParameters. |

Usually, the pair `JOB_NAME` and `JOB_KEY` is protected by a unique constraint so that two JobInstances with the same identity are not created. `JOB_KEY` is not the Job's display name; it represents the set of parameters used to distinguish business runs.

For example, the Job `dailySettlementJob` is run with the identifying parameter `businessDate=2026-11-15`. If you launch the same Job name with the same identifying parameters again, Spring Batch finds the same JobInstance. If the business date changes, that is a different JobInstance.

The point to remember is that not every JobParameter necessarily takes part in identification. Non-identifying parameters can change without creating a new JobInstance. Therefore, when designing parameters and investigating `JobInstanceAlreadyCompleteException` or `JobExecutionAlreadyRunningException` errors, you need to check the correct Job name and identifying parameters.

## 4. The BATCH_JOB_EXECUTION Table

`BATCH_JOB_EXECUTION` stores each execution of a JobInstance. A JobInstance can have multiple JobExecutions, for example the first fails and the next is restarted.

Common columns:

| Column | Meaning |
|---|---|
| `JOB_EXECUTION_ID` | Primary key of the JobExecution. |
| `VERSION` | Version for optimistic locking. |
| `JOB_INSTANCE_ID` | Foreign key to the JobInstance. |
| `CREATE_TIME` | Time the execution was created. |
| `START_TIME` | Time execution started. |
| `END_TIME` | End time, if it has ended. |
| `STATUS` | The BatchStatus of the JobExecution. |
| `EXIT_CODE` | The exit code of the execution result. |
| `EXIT_MESSAGE` | Description of the result or error information. |
| `LAST_UPDATED` | Time the metadata was last updated. |

Some older schema versions differ in time columns or in how nullability is declared. Use the exact script of the Spring Batch version rather than assuming all versions have the same structure.

For example, a JobInstance can have this history:

| JobExecution | Status | Meaning |
|---|---|---|
| 9001 | `FAILED` | The first run hit an error while processing data. |
| 9002 | `COMPLETED` | The restart completed successfully. |

The two executions above reference the same `JOB_INSTANCE_ID`, but have different `JOB_EXECUTION_ID`s. This is why, when looking up history, you must distinguish JobInstance from JobExecution.

`EXIT_CODE` and `EXIT_MESSAGE` are results stored for the execution. You should not edit these columns with SQL to force a Job to succeed or fail. The status must reflect the actual execution result and be updated through Spring Batch's mechanisms.

## 5. The BATCH_JOB_EXECUTION_PARAMS Table

`BATCH_JOB_EXECUTION_PARAMS` stores the parameters passed when launching a JobExecution. Parameters can include a business date, a file name, a customer code, a data region, or other configuration values.

In Spring Batch 5, the standard schema uses a generic parameter structure with common columns such as:

| Column | Meaning |
|---|---|
| `JOB_EXECUTION_ID` | The JobExecution that owns the parameter. |
| `PARAMETER_NAME` | The parameter name. |
| `PARAMETER_TYPE` | The data type of the parameter. |
| `PARAMETER_VALUE` | The value stored in a suitable representation. |
| `IDENTIFYING` | Marks whether the parameter takes part in identifying the JobInstance. |

The schemas of versions before Spring Batch 5 may use separate columns such as `STRING_VAL`, `DATE_VAL`, `LONG_VAL`, `DOUBLE_VAL`, along with other name/type fields. This is a change to pay special attention to when upgrading the framework. You should not take the Spring Batch 5 DDL and run it directly on a Spring Batch 4 application or vice versa.

Example launch parameters:

```java
JobParameters jobParameters = new JobParametersBuilder()
        .addString("inputFile", "orders-2026-11-15.csv", true)
        .addLocalDate("businessDate", LocalDate.of(2026, 11, 15), true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
```

In this example, `inputFile` and `businessDate` are marked identifying, while `requestedBy` does not take part in identifying the JobInstance. The builder API may differ slightly depending on the version; the important thing is to understand the identifying flag clearly and use a suitable parameter type.

When looking up parameters, use `JobExplorer` or Spring Batch's metadata API when possible. How values and types are stored in the table can change by version, so you should not build an application that hard-depends on manually decoding `PARAMETER_VALUE`.

## 6. The BATCH_STEP_EXECUTION Table

`BATCH_STEP_EXECUTION` stores each Step execution inside a JobExecution. A JobExecution usually has multiple StepExecutions, corresponding to the Steps in the Job flow.

Common columns include:

| Column | Meaning |
|---|---|
| `STEP_EXECUTION_ID` | Primary key of the StepExecution. |
| `VERSION` | Version used for optimistic locking. |
| `STEP_NAME` | The Step name. |
| `JOB_EXECUTION_ID` | Foreign key to the parent JobExecution. |
| `CREATE_TIME`, `START_TIME`, `END_TIME` | The StepExecution's time milestones. |
| `STATUS` | The BatchStatus of the StepExecution. |
| `COMMIT_COUNT` | Number of commits. |
| `READ_COUNT` | Number of items read successfully. |
| `FILTER_COUNT` | Number of items filtered by the processor. |
| `WRITE_COUNT` | Number of items written. |
| `READ_SKIP_COUNT` | Number of items skipped at the reader. |
| `PROCESS_SKIP_COUNT` | Number of items skipped at the processor. |
| `WRITE_SKIP_COUNT` | Number of items skipped at the writer. |
| `ROLLBACK_COUNT` | Number of rollbacks. |
| `EXIT_CODE`, `EXIT_MESSAGE` | The result and description of the Step's ending. |
| `LAST_UPDATED` | Time the metadata was last updated. |

The counters in the table help track progress and analyze errors. For example, if `READ_COUNT` is high but `WRITE_COUNT` is low, you need to consider whether the processor filters many items or whether a skip policy is being applied. If `ROLLBACK_COUNT` increases abnormally, you need to investigate the transaction, writer errors, deadlocks, or timeouts.

You should not infer the number of successfully processed items from a single counter. You need to combine `READ_COUNT`, `FILTER_COUNT`, the skip counts, `WRITE_COUNT`, error logs, and the actual results in the business system.

## 7. The Two ExecutionContext Tables

Spring Batch stores state in `ExecutionContext` to support sharing execution data and restart. The JDBC JobRepository stores context at two different scopes.

### BATCH_JOB_EXECUTION_CONTEXT

This table stores the ExecutionContext belonging to a JobExecution. It suits information that needs to be shared among Steps in the same Job run, for example the import batch code or preparation results that a later Step needs to read.

Common columns:

| Column | Meaning |
|---|---|
| `JOB_EXECUTION_ID` | Primary key and foreign key to the JobExecution. |
| `SHORT_CONTEXT` | A shortened representation of the context stored in the metadata. |
| `SERIALIZED_CONTEXT` | The fully serialized portion of the context, depending on the schema and data length. |

### BATCH_STEP_EXECUTION_CONTEXT

This table stores the ExecutionContext belonging to a StepExecution. This is usually where a reader, writer, or Tasklet keeps its own checkpoint, such as the line position read, the next page number, or internal state that needs recovery.

Common columns:

| Column | Meaning |
|---|---|
| `STEP_EXECUTION_ID` | Primary key and foreign key to the StepExecution. |
| `SHORT_CONTEXT` | A shortened representation of the context. |
| `SERIALIZED_CONTEXT` | The fully serialized context data if the schema uses this column. |

`ExecutionContext` is serialized before being stored. The specific structure depends on the serializer and the version's schema. You should not read or edit the serialized string directly with SQL as if it were ordinary business data.

Only store data needed to recover or share execution state. You should not store a list of millions of items or large business data in the context. Store a key, position, page number, or lightweight checkpoint; the main data still lives in the business data store.

## 8. Primary Keys, Foreign Keys, Unique Constraints, and Indexes

The constraints in the schema help protect the relationships among metadata records.

### Primary Keys

Each execution table has its own ID. For example `JOB_EXECUTION_ID` identifies a JobExecution, while `STEP_EXECUTION_ID` identifies a StepExecution. These IDs help the framework link state and context accurately to the corresponding execution.

### Foreign Keys

Common relationships:

- `BATCH_JOB_EXECUTION.JOB_INSTANCE_ID` references `BATCH_JOB_INSTANCE.JOB_INSTANCE_ID`.
- `BATCH_STEP_EXECUTION.JOB_EXECUTION_ID` references `BATCH_JOB_EXECUTION.JOB_EXECUTION_ID`.
- `BATCH_JOB_EXECUTION_PARAMS.JOB_EXECUTION_ID` references the corresponding JobExecution.
- `BATCH_JOB_EXECUTION_CONTEXT.JOB_EXECUTION_ID` references the corresponding JobExecution.
- `BATCH_STEP_EXECUTION_CONTEXT.STEP_EXECUTION_ID` references the corresponding StepExecution.

Foreign keys help prevent orphaned metadata and maintain relational integrity. When cleaning historical data, you must follow these relationships and an appropriate deletion order. Do not delete a parent JobInstance or JobExecution while dependent child records still exist.

### Unique Constraints and Indexes

The unique constraint on the Job name and Job key helps ensure a JobInstance identity is not created twice. Indexes on foreign keys and commonly queried fields support looking up JobExecutions, StepExecutions, and execution history.

Do not arbitrarily drop a unique constraint or index to handle a concurrent launch error. If you encounter a conflict, you need to determine the cause from the JobParameters, the transaction, or multiple launchers launching the same JobInstance.

## 9. Sequences and How IDs Are Generated

The metadata tables need unique IDs for JobInstance, JobExecution, and StepExecution. How IDs are generated depends on the database management system and the corresponding schema script.

Some scripts use database sequences, usually named like:

- `BATCH_JOB_SEQ`
- `BATCH_JOB_EXECUTION_SEQ`
- `BATCH_STEP_EXECUTION_SEQ`

Some other databases or scripts use identity/auto-increment or their own key generation mechanism. Not every database management system has the same sequence objects or the same DDL syntax.

When installing the schema, use exactly the script packaged for the database in use. Do not copy the sequence-creation part from Oracle to MySQL or vice versa. If a sequence is missing, misnamed, or not granted permission, the JobRepository may be unable to create an execution even though the main tables already exist.

## 10. Installing the Metadata Schema

Spring Batch provides schema scripts for many database management systems. The scripts are usually found in the Spring Batch artifact, under the library's schema package, with names by database platform. For example, the group of scripts may distinguish H2, HSQLDB, MySQL, PostgreSQL, Oracle, SQL Server, and other management systems depending on the release version.

The important principle is to use the schema script that ships with the exact Spring Batch version. Table structure, data types, column names, sequences, and constraints can change between versions.

### Spring Boot Initializes the Schema Automatically

With Spring Boot, the configuration property `spring.batch.jdbc.initialize-schema` controls Batch schema initialization in supported environments. Commonly used values:

| Value | Meaning |
|---|---|
| `embedded` | Initializes the schema for an embedded database per Boot's default policy. |
| `always` | Requests that the schema initialization script be run. |
| `never` | Does not initialize the schema automatically. |

Example configuration:

```yaml
spring:
  batch:
    jdbc:
      initialize-schema: always
```

The `always` setting is useful in development or test environments that need to stand up a database quickly. In production, you should manage DDL with a controlled migration process, clearly defining the deployment timing and the schema version. Do not let the application re-run the table-creation script on a database that contains metadata you need to keep.

### Manual Initialization with a Script

You can get the suitable script from the Spring Batch library and run it with a database administration tool or the project's migration tool. Before doing so, you need to determine:

- The database engine and version in use.
- The actual Spring Batch version in the dependency tree.
- The schema/database owner and the permissions to create tables, sequences, and indexes.
- The table prefix configured for the repository.
- Whether the metadata tables or objects already exist.
- Whether the environment needs to keep old execution data or is a completely new database.

If the schema already exists, do not blindly run the initialization script. A table-creation script is usually not a data-upgrade script. You need to use a migration corresponding to the version or perform a tested upgrade procedure.

## 11. Configuring the Table Prefix and a Separate Schema

Default table names usually start with `BATCH_`. In some systems, you need to change the prefix to distinguish multiple applications or multiple repositories, or to avoid table-name conflicts.

Example of prefix configuration:

```yaml
spring:
  batch:
    jdbc:
      table-prefix: APP_BATCH_
```

The table names used by the repository must match the names created in the database. If the prefix is configured as `APP_BATCH_` but the script only creates `BATCH_` tables, the JobRepository will report a table-not-found error.

The prefix is the leading part of a table name; it is not equivalent to a database schema or catalog. If you want to put the tables in a separate schema, you need to configure the datasource, access permissions, or object names according to the database's capabilities and the application configuration. You should not assume that changing the table prefix automatically moves tables to a different schema.

In Java configuration that customizes the JDBC JobRepository, the table prefix can also be configured on the corresponding factory/repository infrastructure. With Spring Boot, prefer configuring the property supported by the Boot version to avoid creating two conflicting repository configurations.

## 12. Transactions and Metadata Consistency

JobRepository is not only a place to store history. The operations that create and update metadata take part in Spring Batch's execution coordination mechanism.

For example, when starting a Job, the framework needs to determine whether the JobInstance already exists, whether a JobExecution is running, and whether a new execution is allowed to be created. The unique constraint together with an appropriate transaction and isolation helps prevent two processes from creating the same JobInstance unintentionally.

Execution records also have a `VERSION` field to support optimistic locking. When a process tries to update metadata based on an old version, the repository can detect the conflict instead of silently overwriting a newer state.

Some JDBC JobRepository configurations allow adjusting the isolation level for the execution-creation operation. The default level and how to configure it depend on the version/how the repository is built. Only change the isolation after understanding the concurrent load, the database behavior, and the actual errors; do not lower the isolation level just to hide JobInstance-creation conflict errors.

The metadata repository is usually configured with a transaction manager suited to the database that stores metadata. If business data lives in a different database, you need to understand clearly the transaction boundary between metadata and business data. A JDBC transaction manager does not by itself create a distributed transaction across multiple databases or HTTP systems.

## 13. Querying Metadata to Monitor Jobs

In operations, you can use `JobExplorer` to query metadata through the Spring Batch API. This is the right choice when you need to view executions, the list of StepExecutions, and status without depending directly on the SQL structure of each version.

SQL is also useful for reports or investigations. The queries below only illustrate a schema with common table and column names; adjust them according to the actual script of the version.

### Listing Recent Job Runs

```sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.START_TIME,
    je.END_TIME,
    je.EXIT_CODE
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
    ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
ORDER BY je.JOB_EXECUTION_ID DESC;
```

The query joins a JobInstance with its corresponding runs. A JobInstance can appear in multiple rows if it has had multiple JobExecutions.

### Viewing the Steps of a JobExecution

```sql
SELECT
    STEP_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    FILTER_COUNT,
    READ_SKIP_COUNT,
    PROCESS_SKIP_COUNT,
    WRITE_SKIP_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT,
    START_TIME,
    END_TIME
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = 9002
ORDER BY STEP_EXECUTION_ID;
```

This query helps identify which Steps ran, what their status is, and whether the counters are abnormal. Replace the illustrative ID with the `JOB_EXECUTION_ID` you need to investigate.

### Looking Up an Execution's Parameters

With the Spring Batch 5 schema, you can view the new parameter fields:

```sql
SELECT
    PARAMETER_NAME,
    PARAMETER_TYPE,
    PARAMETER_VALUE,
    IDENTIFYING
FROM BATCH_JOB_EXECUTION_PARAMS
WHERE JOB_EXECUTION_ID = 9002;
```

If the application uses the older schema, you need to adjust the query to the parameter structure of that version. You should not use a single SQL statement for every Spring Batch version.

### Using the API Instead of Direct SQL

Example of reading a JobExecution with `JobExplorer`:

```java
@Service
public class BatchMetadataService {

    private final JobExplorer jobExplorer;

    public BatchMetadataService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public void printExecution(long executionId) {
        JobExecution execution = jobExplorer.getJobExecution(executionId);
        if (execution == null) {
            return;
        }

        System.out.println("Job: " + execution.getJobInstance().getJobName());
        System.out.println("Status: " + execution.getStatus());

        for (StepExecution step : execution.getStepExecutions()) {
            System.out.printf("%s: %s, read=%d, write=%d%n",
                    step.getStepName(),
                    step.getStatus(),
                    step.getReadCount(),
                    step.getWriteCount());
        }
    }
}
```

`JobExplorer` is the API for reading metadata. `JobRepository` is responsible for storing and updating metadata during execution. When an execution is running, the data read from the repository may reflect the most recent update and is not necessarily the instantaneous in-memory state of the process.

## 14. Upgrading the Schema When Changing Spring Batch Versions

The metadata schema is part of the contract between the Spring Batch version and the database. When upgrading the framework, you need to check DDL changes before deploying.

A notable example is the structure of `BATCH_JOB_EXECUTION_PARAMS`: Spring Batch 5 switched to a generic way of storing parameters with a name, type, value, and identifying flag; older versions use value columns per data type. Therefore, upgrading only the dependency while keeping the old schema can cause errors when reading or writing JobParameters.

The upgrade process should include:

1. Determine the current Spring Batch version and the target version.
2. Read the migration guide and the schema script of the target version.
3. Back up the metadata database before making changes.
4. Create DDL/DML migrations suited to the existing data; do not delete history if the business needs to keep it.
5. Try the migration on a copy of the database with representative data.
6. Deploy the migration and the application in the defined order, avoiding two incompatible application versions writing to the same schema.
7. Test launching a Job, storing parameters, creating a StepExecution, updating context, and restart in a test environment.

You should not edit the schema manually by guesswork or copy a `schema-*.sql` file of the new version onto a running production database. The initialization script is usually for an empty database; an upgrade migration needs to preserve and convert the existing metadata.

## 15. Managing the Schema and Metadata Data in Production

The metadata repository needs to be operated as an important database of the Batch application.

### Access Permissions

The application account needs permissions to read, write, and update the necessary tables/sequences. The migration account may need higher DDL permissions, but it does not have to be the same account as the application at runtime. Apply least privilege suited to the deployment process.

### Backup and Recovery

If metadata is lost, the application may lose the ability to determine which JobInstances have run, Step status, checkpoints, and execution history. Therefore, the metadata database needs to be included in the backup/restore plan. When restoring, you need to consider consistency between the metadata and the business data that was written earlier.

### Retaining History

Over time, the metadata tables can grow in size because they store many JobExecutions, StepExecutions, and contexts. A retention policy may be needed to keep history for an appropriate period.

Metadata cleanup must be done in a controlled way. You need to use an API or cleanup tool designed for your Spring Batch version, or an SQL procedure that clearly understands the foreign key relationships. If deleting manually, you must handle child records before parent records and must not delete running executions or data still needed for restart/reconciliation.

### Protecting Data in Context and Parameters

JobParameters and ExecutionContext can contain file paths, identifier codes, operational information, or sensitive data if the application stores it there. Only store necessary information, control read access to metadata, and avoid writing secrets such as passwords, tokens, or access keys into the context or exit message.

### Monitoring Growth and Performance

Monitor the number of executions, the growth rate of the context tables, history query time, and index performance. If a Job runs at high frequency, metadata can grow quickly even if each run processes little data. The retention, index, and backup plan needs to match the execution frequency.

## 16. Common Errors When Configuring the Metadata Schema

### BATCH_* Tables Not Found

The cause is usually that the schema has not been initialized, the datasource points to the wrong database/schema, the account lacks permissions, or the table prefix in the configuration does not match the actual table names. Check the database URL, the schema owner, the `initialize-schema` configuration, and the table prefix.

### Wrong Schema Version

The application may fail when querying a nonexistent column, writing data of the wrong type, or reading incompatible parameters. Compare the Spring Batch version with the deployed DDL and use the migration of the correct version.

### Missing Sequence or Permission to Generate IDs

The tables may exist but the repository still cannot create a JobExecution or StepExecution because the sequence/identity was not created correctly or the runtime account lacks permission to use it. Check the script by database and the access permissions to the ID-generating objects.

### Table Prefix Mismatch

If the repository accesses `APP_BATCH_JOB_INSTANCE` but the database only has `BATCH_JOB_INSTANCE`, the query will fail. The configuration and DDL must use the same prefix.

### Unique Constraint Violated

Two launchers may both be creating a JobInstance with the same Job name and identifying parameters, or another process may have created the instance earlier. Check the parameters, the state of existing executions, and the concurrent launch mechanism. Do not remove the constraint to ignore the error.

### Optimistic Locking Failure

A version error can occur when metadata is updated concurrently or an execution is controlled from multiple processes incorrectly. Identify which process is writing, check the launcher, and avoid directly editing the `VERSION` column.

### Context Cannot Be Read After an Upgrade

Changes to the serializer, data type, or schema can make an old context incompatible. You need to check the serialize/deserialize mechanism and the migration process. Do not delete the context tables if old checkpoints are still needed for restart.

### Repeated Schema Initialization in Production

If the application always runs the table-creation script on an existing database, startup can fail or interrupt the deployment. Production should have versioned migrations that run only once per the release process.

## 17. Process for Setting Up the Repository for a New Application

When introducing Spring Batch into a new application, you can proceed in this order:

1. Choose the database for metadata and configure a suitable datasource.
2. Determine the Spring Batch version that goes with the project's Spring Boot version.
3. Get the schema script for the right database and the right version.
4. Create the necessary tables, keys, indexes, and sequences/identities in the database.
5. Configure the JDBC JobRepository to use the right datasource, transaction manager, and table prefix.
6. Configure runtime permissions so the application can read/write metadata.
7. Launch a test Job to confirm that JobInstance, JobExecution, JobParameters, and StepExecution are stored.
8. Try a failing Job that can be restarted, and confirm the ExecutionContext is stored and read back correctly.
9. Check queries with JobExplorer and the backup/retention process.

A Job that runs successfully once is not enough to prove the repository schema is fully configured. You should check execution history, parameters, Step counters, context, and the restart scenario as well.

## 18. How to Choose Where to Store Metadata

In development, an embedded database can be convenient because it is easy to initialize and needs no separate database service. However, if metadata exists only in memory or in a temporary database, history and checkpoints can be lost when the application stops.

For production, a JDBC JobRepository using a durable database is usually appropriate when you need restart, multiple application instances, execution history, and operational queries. You need to ensure that all related launchers/workers share the repository correctly and that the database can handle the metadata load.

Choosing the metadata database needs to consider:

- The level of durability and the restart requirements.
- The number of Job and Step executions created per day.
- The number of processes that can launch Jobs concurrently.
- The requirements for storing history and the retention period.
- The ability to back up, restore, monitor, and migrate.
- Access permissions and how to isolate metadata from business data.

## Conclusion

The schema of the JDBC JobRepository consists of tables that store JobInstance, JobExecution, JobParameters, StepExecution, and ExecutionContext. The tables are linked by primary keys, foreign keys, and constraints to keep metadata consistent and to support monitoring and restart. You need to use the right schema script for the Spring Batch version and the database, configure the table prefix to match the DDL, manage migrations in a controlled way, and protect metadata as important operational data of the Batch application.
