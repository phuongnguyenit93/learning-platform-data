# Inconsistent Metadata Errors in Spring Batch

Spring Batch stores the operational information of jobs and steps in the metadata repository through `JobRepository`. Metadata tells whether a job instance has been created, which executions have taken place, which steps have completed, what the current status is, and where the checkpoint is. When this information does not reflect the same execution history, the application may encounter errors in launching, restarting, monitoring, or recovering data.

**Inconsistent metadata** is a condition in which the records or states that Spring Batch uses no longer agree with each other or with the actual business process. The causes can lie in transactions, database configuration, concurrent runs, schema upgrades, or manual operations. You need to identify the right kind of discrepancy before recovering, because correcting metadata wrongly can lose history or cause the job to process data in duplicate.

## 1. What Does the Metadata Repository Store?

In the common JDBC configuration, Spring Batch stores metadata in tables with the `BATCH_` prefix. The main tables represent different parts of a run:

| Table | Role |
| --- | --- |
| `BATCH_JOB_INSTANCE` | Stores the identity of the job instance, determined by the job name and identifying parameters. |
| `BATCH_JOB_EXECUTION` | Stores each execution of a job instance, including status and time milestones. |
| `BATCH_JOB_EXECUTION_PARAMS` | Stores the parameters used when launching the execution. |
| `BATCH_STEP_EXECUTION` | Stores the status, counters, and result of each step execution. |
| `BATCH_JOB_EXECUTION_CONTEXT` | Stores the execution context at the job scope. |
| `BATCH_STEP_EXECUTION_CONTEXT` | Stores the execution context at the step scope. |

The logical relationships among them can be pictured as follows:

```text
JobInstance
    |
    +---- JobExecution 1
    |          |
    |          +---- StepExecution A
    |          +---- StepExecution B
    |          +---- JobExecutionContext
    |
    +---- JobExecution 2 (for example, a restart)
               |
               +---- StepExecution A
               +---- StepExecution B
               +---- JobExecutionContext

Each StepExecution can have its own StepExecutionContext.
```

A `JobInstance` can have multiple `JobExecution`s, for example when a run fails and is restarted. Each `StepExecution` belongs to a specific `JobExecution`. The `ExecutionContext` stores the state needed for batch components to restore progress.

Metadata is not business data. For example, the orders table contains the orders that were imported; `BATCH_STEP_EXECUTION` stores the number of items read, written, skipped, or rolled back. The two places can be in two different databases, and therefore a situation can arise in which one side has committed while the other has not been updated.

## 2. How Does Inconsistent Metadata Manifest?

Discrepancies can appear in many forms:

- An execution still has the `STARTED` status even though the application process stopped long ago.
- The job execution and step execution have statuses or time milestones that do not agree with each other.
- A metadata record references an instance or execution that no longer exists, usually due to manual data deletion or unprotected foreign key constraints.
- Metadata says the job or step has completed but the business result has not been fully written, or the data has been written but the checkpoint does not reflect it.
- A restart cannot restore the `ExecutionContext`, for example because the context data is missing, corrupted, or cannot be deserialized.
- The application cannot create a new execution because the metadata's primary key, sequence, or unique constraint is out of line.
- Two processes update the same execution, causing optimistic locking to detect that the data version has changed.

Not every metadata-related error proves the database is corrupted. For example, `JobInstanceAlreadyCompleteException` can be the correct result when the application tries to re-run an instance that has completed. `JobExecutionAlreadyRunningException` can indicate that an execution of the same instance is active. Before concluding there is a discrepancy, you need to check the job's status and identifying parameters.

## 3. Common Causes

### 3.1. Metadata Transactions and Business Transactions Out of Sync

Spring Batch updates metadata in the operations that create or update job execution, step execution, and checkpoints. With chunk processing, the transaction usually surrounds reading, processing, writing a chunk, and updating the necessary state.

If business data and metadata share a database, share a transaction manager, and are configured to take part in the right transaction, the updates can be committed or rolled back together. But if they use two datasources or two different transaction managers, the two parts can commit independently.

For example:

```text
Step processes a chunk
       |
       +---- Write orders to the business database
       |
       +---- Update the checkpoint in the metadata database
                       |
                       v
                One side commits,
                the other fails
```

If business data has committed but the checkpoint has not, a restart may re-read part of the data and write duplicates. If the checkpoint has committed but the business data has not been written, the job may skip records that were not actually saved. This is a problem of transaction boundaries across resources.

### 3.2. The Application Stops Abruptly

A server can lose power, a container can be killed, the JVM can crash, or a database connection can be dropped. If an execution has written its start status but has no chance to write its end status, the metadata may still show `STARTED`.

An old `STARTED` status does not by itself prove the metadata is corrupted. The job may still be running on another node, or the process may have stopped before updating the final status. You need to verify the process, logs, host, and the last update time before deciding to stop or restart the execution.

### 3.3. Multiple Processes Launch or Update the Same Job

In a multi-node environment, a scheduler or operator can send launch requests simultaneously. Spring Batch uses `JobRepository`, transactions, and synchronization mechanisms to protect the creation of executions for the same `JobInstance`.

If nodes use their own metadata repositories, each node may believe the instance has not run and launch the same work. If they share a repository but the transaction or database configuration is unsuitable, conflicts can arise when creating or updating records.

Spring Batch also uses an optimistic locking mechanism on execution records. The `VERSION` column is used to detect updates based on an old version. When two threads modify the same record, one operation can fail with an optimistic locking error instead of silently overwriting the new data.

### 3.4. Using the Wrong Database, Schema, or Table Prefix

An application can inadvertently read metadata from a test database while the job writes to the production database, or one node uses a different datasource/schema than the other nodes. A custom table prefix configuration can also cause the application to read one group of tables and write to another group.

The consequence is that `JobExplorer` may not find an execution that `JobLauncher` just created, or the application believes there is no instance while the instance actually lives in another schema. This is usually an environment configuration error rather than corrupted data.

### 3.5. Editing or Deleting Metadata Directly

Deleting a `BATCH_JOB_EXECUTION` record while keeping `BATCH_STEP_EXECUTION`, or deleting the execution context while the step needs it to restart, can break the relationships among records. If the database has foreign keys, the delete operation may be rejected; if constraints are turned off or do not exist, orphaned data can appear.

Manually updating `STATUS`, `END_TIME`, `VERSION`, or other fields can also make the framework misunderstand the execution lifecycle. You should not directly edit metadata records just to make a job appear to have completed or be re-runnable.

### 3.6. Upgrading Spring Batch but the Schema Is Incompatible

When upgrading the Spring Batch version, the metadata schema and how parameters or the execution context are stored can change. If the application runs the new library with the old schema, or multiple application versions write to one schema in an incompatible way, SQL errors, column-mapping errors, or context deserialization errors can appear.

Use the schema script and upgrade guide that correspond to the Spring Batch version that is running. Do not copy a schema from a different version or rename columns yourself just to make an immediate error go away.

### 3.7. Corrupted Sequences, Primary Keys, and Context Data

Some database management systems use sequences or sequence tables to allocate IDs for job execution and step execution. If the sequence value is set back relative to existing IDs, an operation that creates a new record can hit a duplicate key error.

The execution context can also be affected if the stored data is truncated, the serializer changes, or the classes stored in the context are no longer compatible after deploying a new version. In that case, the job may find the execution but cannot restore the state needed to restart.

## 4. Common Errors and How to Interpret Them

Error messages need to be read together with the execution status and the logs at the time they arose:

| Error or Sign | Common Interpretation |
| --- | --- |
| `JobExecutionAlreadyRunningException` | An execution of the same job instance is considered running. Check whether it is still active or is a stale state after an incident. |
| `JobInstanceAlreadyCompleteException` | The instance has completed with the current identifying parameters. This can be correct behavior, not corrupted metadata. |
| `JobRestartException` | The instance or execution does not meet the restart conditions, or the stored state does not allow continuing. |
| `NoSuchJobExecutionException` / `NoSuchJobInstanceException` | The requested execution or instance was not found in the repository that the application is querying. Check the ID and datasource/schema. |
| `OptimisticLockingFailureException` | An execution update based on an old version was rejected because the record was updated concurrently. |
| `DuplicateKeyException` | May be due to creating a duplicate execution or a skewed metadata sequence/ID. You need to look at the constraint and the SQL statement that caused the error. |
| `ExecutionContext` deserialization error | The context data cannot be read with the current serializer or class. Check version changes and the stored data. |
| SQL error about a metadata table or column | The application may be using the wrong schema, missing a migration, or incompatible with the version. |

The specific exception names can differ depending on the Spring Batch version, Spring Framework, and database driver. Use the stack trace and the actual SQL statement to identify the failing operation.

## 5. Distinguishing Metadata Errors from Valid Job State

Before investigating deeply, you need to understand some Spring Batch rules:

- A `JobInstance` is determined by the job name and the identifying `JobParameters`. Changing an identifying parameter creates a different instance; changing a non-identifying parameter does not change the instance identity.
- An instance can have multiple `JobExecution`s, for example the first run `FAILED` and the restart `COMPLETED`.
- `BatchStatus` describes the framework's lifecycle status; `ExitStatus` describes the exit code and message. The two fields do not necessarily have the same value.
- `END_TIME` having no value in a running execution is normal. For an execution that stopped abruptly, the end time may not have been recorded.
- A step that has completed may not run again in a restart under the default rules. This is not a sign that metadata is missing the step.

For example, the same job `importOrders` run with `businessDate=2026-11-15` will target the same `JobInstance` if this parameter is identifying. If the instance is `COMPLETED`, re-running with the same parameters may be rejected. If the goal is to import data for a different day, pass the corresponding identifying parameter instead of editing the old instance's metadata.

## 6. A Safe Diagnostic Process

You should investigate in order from broad scope to a specific record. First, determine the job name, identifying parameters, execution ID, the time of the error, and the node that ran the job. Collect the application and database logs to know which operation failed.

### Step 1: Identify the Right Repository

Check the datasource, schema, table prefix, and transaction manager configuration of `JobRepository`. Compare the configuration across the running nodes or profiles. If the application uses multiple datasources, determine exactly which datasource stores metadata and which stores business data.

### Step 2: Look Up with the Spring Batch API

Prefer using `JobExplorer` to read history instead of arbitrarily querying or modifying data. You can get the instances and executions by job name, then look at the related status and step executions.

```java
List<JobInstance> instances = jobExplorer.getJobInstances("importOrders", 0, 20);

for (JobInstance instance : instances) {
    List<JobExecution> executions = jobExplorer.getJobExecutions(instance);
    for (JobExecution execution : executions) {
        System.out.println(
            execution.getId() + " " + execution.getStatus()
                + " " + execution.getStartTime()
                + " " + execution.getEndTime()
        );
    }
}
```

The code illustrates how to view the executions of a job. When investigating a specific instance, you need to compare identifying parameters, run times, step executions, and the execution context. The API may differ slightly between library versions.

### Step 3: Cross-Check the Metadata Relationships

When you need to inspect the database directly, start only with read queries. The example below uses the default table names and one job name; you may need to adjust the schema name, prefix, or syntax per the database:

```sql
SELECT
    ji.JOB_INSTANCE_ID,
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.START_TIME,
    je.END_TIME,
    je.LAST_UPDATED
FROM BATCH_JOB_INSTANCE ji
LEFT JOIN BATCH_JOB_EXECUTION je
    ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'importOrders'
ORDER BY ji.JOB_INSTANCE_ID, je.JOB_EXECUTION_ID;
```

To view the steps belonging to a specific execution:

```sql
SELECT
    se.STEP_EXECUTION_ID,
    se.JOB_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS,
    se.START_TIME,
    se.END_TIME,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION se
WHERE se.JOB_EXECUTION_ID = :jobExecutionId
ORDER BY se.STEP_EXECUTION_ID;
```

These queries only read the status and the relationships among job instance, job execution, and step execution. Do not use the result of a single query to conclude by yourself that a restart is safe. You need to cross-check against logs, the executing node, transactions, and business results.

### Step 4: Check the Context and Schema Version

If the error occurs on restart, check whether the execution context was stored and read successfully. If the error began after a deployment, compare the Spring Batch version, schema migration, serializer, and the classes stored in the context. Do not edit the context payload by hand.

### Step 5: Verify the Business Data

Compare the counters in `StepExecution` with the target data, the writer's logs, and the committed transactions. If metadata and business data are in two systems, you need to consider the possibility that one side committed while the other rolled back or lost its connection.

## 7. How to Recover in Each Situation

There is no single fix for every metadata error. The handling approach must be based on the identified cause.

### Execution Is Still STARTED but the Process Has Stopped

First confirm that no node is actually still running that execution. Check the heartbeat, logs, process, container, and the last metadata update time. If the execution is still active, use the supported stop mechanism instead of changing the state in the database.

If the process has died, determine whether the execution can be restarted or needs to be marked abandoned per the rules of the Spring Batch version in use. You can use operational actions through `JobOperator` when the current state allows. Only restart after understanding which data was committed and whether the reader/writer can recover safely.

### Metadata and Business Data Committed Out of Step

If business data has been written but the checkpoint has not been updated, you need to determine the scope of data that may be reprocessed. If the checkpoint has advanced but the target data has not been written, you need to determine how to bring the skipped data back into the processing flow.

For write operations to external systems, use an idempotency key, a unique constraint, upsert, or a suitable reconciliation mechanism so reprocessing does not create duplicate data. When the two resources are not in the same transaction, you may need a compensation or business reconciliation process.

### Incorrect Schema or Database Configuration

Fix the datasource, schema, prefix, or transaction manager configuration according to the actual environment. If the schema is missing a migration, perform the supported migration for the correct version after backing up and following the application's database deployment process. Do not add or drop columns by guesswork.

### Skewed Sequence or Primary Key

Determine the database's ID-allocation mechanism and its current value compared with existing IDs. Only adjust the sequence following guidance for the exact database, schema, and Spring Batch version, after having a backup and confirming no concurrent writing processes remain. Do not set the sequence to an arbitrary value.

### Execution Context Cannot Be Deserialized

Check changes in classes, data types, serializer, and the application version. If possible, deploy backward-compatible code to read the old context and then convert it through a controlled process. If the context cannot be recovered, plan a re-run or compensating processing based on business data; do not delete the context just to get past a launch error.

### Metadata Records Deleted or Edited by Mistake

Stop processes that could continue writing to the affected data area. Cross-check the backup, database logs, and the time of the operation to identify the lost or changed records. Recover using an approach consistent with the entire key relationships and execution history. Do not create fake rows with a `COMPLETED` or `FAILED` status to make the relationships look valid.

## 8. Preventing Inconsistent Metadata

### Use One Consistent Metadata Repository

Nodes that coordinate a group of jobs should share a durable repository and uniform configuration. Do not let each node write metadata to its own database if they need to coordinate one job history. Manage the datasource, schema, and table prefix with centralized, per-environment controlled configuration.

### Configure Transactions Clearly

Determine the step's transaction manager and the `JobRepository`'s transaction manager. If metadata and business data need atomicity, design them to take part in the same transaction when the architecture allows. If they are in independent resources, you need an idempotency, reconciliation, or compensation mechanism.

### Avoid Duplicate Launches

Use identifying parameters to describe the unit of work correctly. Coordinate the scheduler and operational requests to limit concurrent launches of the same instance. In a multi-node environment, rely on the shared repository and Spring Batch's locking/transaction mechanisms; do not assume an in-memory lock on one node can coordinate the entire cluster.

### Protect Metadata and Backups

Limit direct write permissions on the `BATCH_*` tables. Track migration, cleanup, and schema-change operations. Back up metadata together with the related business data, especially before upgrading versions or performing major maintenance.

### Maintain Compatibility When Deploying

When upgrading Spring Batch, check the schema migration, how `JobParameters` are stored, and the ability to read old `ExecutionContext`s. During a rolling deployment, avoid letting incompatible application versions write to the same metadata schema.

### Monitor State and Alerts

Monitor executions with a `STARTED` status for too long, executions lacking updates, the restart rate, optimistic locking failures, database errors, and the gap between processing counters and business results. Alert thresholds need to be based on each job's normal duration, not one common time threshold for all.

## 9. Actions to Avoid

- Do not delete rows in `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, or the context tables to force a job to run again.
- Do not edit `STATUS`, `END_TIME`, `VERSION`, or identifying parameters yourself with SQL in a running environment.
- Do not restart an old execution before confirming the old process has completely stopped.
- Do not use a `COMPLETED` `JobInstance` for a new business unit just by changing metadata.
- Do not delete the execution context if the step needs the checkpoint to restore progress.
- Do not upgrade the library while skipping the schema migration and the compatibility of context data.

If you must repair the database outside the normal API, you need a recoverable backup, a write-stop plan, a post-recovery verification approach, and approval under the system's operations process. The operation must be based on the specific schema and state, not one generic SQL statement for every case.

## 10. Example Scenario: A Job Is Stopped Midway Through a Data Import

Suppose the job `importOrders` processes data in chunks of 100 orders. After two chunks, 200 orders have been written and the checkpoint has been saved. In the next chunk, the application is abruptly killed.

```text
Chunk 1: read 1..100     -> written successfully -> commit
Chunk 2: read 101..200   -> written successfully -> commit
Chunk 3: read 201..300   -> application stops abruptly
```

After the incident, the metadata may still have the `STARTED` status or a status reflecting the last update before the process stopped. The operator needs to:

1. Confirm that no `importOrders` process is still handling the same instance.
2. Look at the most recent `JobExecution` and `StepExecution`, the checkpoint in the `ExecutionContext`, the reader/writer logs, and the committed transactions.
3. Cross-check the business database to confirm the first 200 orders were fully written and there are no half-finished writes outside the transaction.
4. Determine whether the reader can reopen the data source from the checkpoint and whether the writer handles it safely if a chunk is re-run.
5. Use the supported restart action when the execution is eligible, then monitor the record counts and the completion status.

If the writer writes to an API outside the database and the API had received some requests in the chunk before the application stopped, the metadata checkpoint cannot by itself prove which requests succeeded. You need to reconcile by order code or idempotency key before resending.

## 11. Principles for Handling in Production

When you hit a metadata error, treat the repository as the application's important operational history. Identify the right job instance and execution, verify the running node, check the datasource and transactions, and then cross-check metadata against business data. Only choose stop, restart, abandon, migration, or backup recovery once you understand its impact on the checkpoint and the committed data.

`JobRepository` helps Spring Batch manage execution history and progress, but ultimate consistency also depends on transactions, database configuration, how multiple nodes are coordinated, and the design of the reader/writer. Protecting metadata, using appropriate operational APIs, and designing business operations that can be reprocessed will help a job recover reliably after an incident.
