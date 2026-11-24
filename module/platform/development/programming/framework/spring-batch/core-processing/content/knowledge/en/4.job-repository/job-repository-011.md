# Cleaning Up Old Metadata and Retention in Spring Batch

Spring Batch stores the execution history of Jobs and Steps in the database through the **JobRepository**. This metadata lets the application know when a Job ran, which Step completed, which run failed, and where to restore the checkpoint on restart.

Over time, the metadata tables can grow significantly, especially in systems that run many scheduled Jobs or process many small batches each day. Therefore, the application needs a **retention** policy: determining which metadata must be kept, for how long, when it may be deleted, and how to clean up data safely.

Cleaning up metadata is an operational task that directly affects the ability to restart and look up history. If you delete too early, a Job may lose the information it needs to continue; if you delete in the wrong order, you may violate the relationships among tables or leave orphaned data.

## 1. Why Is Retention Needed for JobRepository?

Each time a Job is launched, Spring Batch writes more metadata. In a system that runs continuously, the data can grow with the number of runs, the number of Steps, and the number of items processed.

Metadata is used for many purposes:

- Identifying the JobInstance by Job name and identifying JobParameters.
- Recording each JobExecution and StepExecution.
- Tracking status such as COMPLETED, FAILED, STOPPED, or STARTED.
- Storing start and end times and the counters for read, write, skip, commit, and rollback.
- Storing the ExecutionContext so readers, writers, or custom components restore state.
- Looking up history for operations, error investigation, and reconciliation.

When metadata grows uncontrolled, the system may face these problems:

- The BATCH_* tables take up a lot of storage capacity.
- History queries, dashboards, and operational tools become slower.
- Database backup, restore, replication, or maintenance takes more time.
- The context tables can grow quickly if Jobs store a lot of state.
- Old metadata makes it difficult to manage lifecycle and retention requirements.

Retention helps limit the portion of history that needs to be kept in the operational database. The goal is to keep enough data for restart, operational support, and audit requirements, and then clean up the executions that have passed their retention period.

You need to distinguish **Spring Batch metadata** from **the business data that the Job produces**. Deleting execution history does not mean deleting orders, reports, output files, or imported data. The two kinds of data need separate retention policies.

## 2. What Kinds of Metadata Does JobRepository Store?

JobRepository is the central component for Spring Batch to store and retrieve metadata. With the common JDBC configuration, the tables with the `BATCH_` prefix are used.

The main tables commonly seen:

| Table | Contents |
|---|---|
| `BATCH_JOB_INSTANCE` | The JobInstances, determined by Job name and identifying JobParameters |
| `BATCH_JOB_EXECUTION` | Each execution of a JobInstance |
| `BATCH_JOB_EXECUTION_PARAMS` | The JobParameters of a JobExecution |
| `BATCH_JOB_EXECUTION_CONTEXT` | The ExecutionContext at the JobExecution scope |
| `BATCH_STEP_EXECUTION` | Each execution of a Step |
| `BATCH_STEP_EXECUTION_CONTEXT` | The ExecutionContext at the StepExecution scope |

Table names and column structure can change depending on the version, database, schema, or table prefix the application configures. When writing a retention script, you must base it on the actual schema being deployed.

### Relationships Among the Tables

A JobInstance can have multiple JobExecutions. For example, the first run fails, and the later run restarts and completes. Each JobExecution can contain multiple StepExecutions. The context and parameters tables store data that depends on the corresponding execution.

~~~mermaid
flowchart TD
    A["BATCH_JOB_INSTANCE"] --> B["BATCH_JOB_EXECUTION"]
    B --> C["BATCH_JOB_EXECUTION_PARAMS"]
    B --> D["BATCH_JOB_EXECUTION_CONTEXT"]
    B --> E["BATCH_STEP_EXECUTION"]
    E --> F["BATCH_STEP_EXECUTION_CONTEXT"]
~~~

The relationships can be understood as follows:

- A JobInstance can be linked with multiple JobExecutions.
- Each JobExecution can have multiple StepExecutions.
- A JobExecution has one Job ExecutionContext area.
- Each StepExecution has one Step ExecutionContext area.
- JobExecution parameters are attached to a specific execution.

The important point when cleaning data is **not to delete a JobInstance while there are still executions that need to be kept**. The restart history and the relationships among tables must be treated as one unified group of data.

### How Do JobInstance and JobExecution Differ in Retention?

Suppose the Job `dailyImportJob` runs with the identifying parameter `businessDate=2026-11-01`:

1. The first run creates a JobInstance and a JobExecution.
2. The JobExecution fails after the data-import Step has committed some chunks.
3. The Job is restarted with the same identifying JobParameters, creating a new JobExecution belonging to that JobInstance.
4. The new run completes and has the corresponding additional StepExecutions.

If you only delete the failed JobExecution without considering the JobInstance and the completed execution, the history of the same logical processing will be split. If you delete the entire JobInstance, the application no longer has metadata to restart or look up the executions belonging to that instance.

Therefore, retention usually selects and deletes by **JobInstance group**, after all of the instance's executions are eligible for cleanup.

## 3. Classifying Status Before Cleanup

Not every old execution can be deleted right away. You need to look at the status and the end time of each execution.

| Status | Operational Meaning | How to Handle in Retention |
|---|---|---|
| COMPLETED | The execution has completed | Can be put into retention after the retention period |
| FAILED | The execution failed | Keep for a period that allows investigation or restart |
| STOPPED | The execution has stopped | Keep if it can still be restarted or needs investigation |
| ABANDONED | The execution is marked as not continuing | Can be cleaned up per policy after the retention period |
| STARTING / STARTED | The execution is starting or running | Do not put into the delete list |
| STOPPING | The execution is in the process of stopping | Do not put into the delete list |
| UNKNOWN | A reliable status cannot be determined | Keep for investigation |

FAILED and STOPPED usually still matter for restart capability. An execution that failed today may be restarted by the operations team tomorrow. Therefore, you should not set the simple rule that anything FAILED gets deleted.

You can design different retention periods by status:

- COMPLETED: keep 30, 60, or 90 days depending on operational requirements.
- FAILED: keep longer for investigation and restart, for example 90 or 180 days.
- STOPPED: keep for a period similar to FAILED or per the system's stop procedure.
- ABANDONED: keep long enough for audit before cleaning up.
- STARTED or unknown status: do not delete automatically.

The numbers above are only examples. The actual period must be based on the time allowed for restart, audit requirements, retention regulations, and the system's storage capacity.

### Minimum Conditions for a JobInstance to Be Eligible

A JobInstance should only be put into the purge list when it satisfies all the defined conditions, such as:

1. The Job name is in the list allowed to be cleaned up.
2. The JobInstance has at least one JobExecution.
3. Every JobExecution of the instance has ended.
4. Every execution has a status that the retention policy allows.
5. The end time of every execution is older than the corresponding cutoff.
6. There is no remaining restart, investigation, or audit requirement that needs that metadata.
7. No operational process is using the instance for reconciliation or recovery.

Applying the conditions across all the JobExecutions of a JobInstance helps avoid deleting part of the history. If an instance has an old execution that is FAILED but a newer execution is still running, the whole instance must be kept.

## 4. Designing a Retention Policy

A good retention policy needs to answer four questions: which Jobs to clean up, which data to clean up, how long to keep it, and who is responsible for operating it.

### Retention by Job Name

Not every Job has the same data lifecycle. For example:

| Job Group | Reference Policy |
|---|---|
| Daily data import Job | Keep completed metadata for 60 days |
| Financial reconciliation Job | Keep per audit requirements, possibly longer |
| Temporary report-generation Job | Keep metadata for a shorter period |
| Error-handling Job that needs restart | Keep FAILED and STOPPED until the end of the restart window |
| One-off Job for migration | Keep history per release policy and audit |

You should not apply a single period to every Job if the business requirements differ.

### Retention by End Time

For executions that have completed, the end time is usually a suitable basis for computing the age of the data. For example, keeping completed metadata for 90 days:

~~~text
cutoff = current time - 90 days

eligible when:
    end_time < cutoff
    and status belongs to the group allowed to be cleaned up
~~~

You should not rely only on create_time. A JobExecution may have started long ago but run for many hours or many days; deleting by create_time can delete an execution that has not ended.

An execution without an end_time must be kept for inspection. For an unusually long STARTED status, verify the process, host, and database state before handling it.

### Retention by Count or Size

Besides the period, the system can set a threshold on the number of executions or the metadata size. For example, only keep the 100 most recent runs of a Job after the minimum period has been met.

Be careful with this approach:

- Do not delete a running execution just because it exceeds the count threshold.
- Do not delete a failed execution that is still within the restart window.
- Do not delete an individual execution if it belongs to a JobInstance that still needs to be kept.
- Always apply the minimum period before applying the count limit.

### Archiving Before Deletion

If you need to keep history long-term, you can archive metadata before purging it from the operational database. The archive can be a history database, a separate audit table, or an export file with controlled access.

The archive should keep at least:

- The Job name and JobInstance ID.
- The JobExecution ID, status, and start/end times.
- The JobParameters, sanitized of sensitive data.
- The StepExecution and the counters needed for audit.
- The ExitStatus and the error information needed for lookup.
- Reference codes to the related business data or reports.

You do not always need to archive the entire ExecutionContext. The context may contain internal state, sensitive data, or serialized objects that depend on the application version. Only archive the fields that truly have value for audit and investigation.

## 5. Consequences of Deleting Metadata

Cleaning up metadata affects Spring Batch's operability. Before designing retention, you need to understand the following consequences.

### A Deleted JobInstance Cannot Be Restarted

Spring Batch relies on JobRepository to find the JobInstance and its previous executions. When a JobInstance's metadata is deleted, the framework no longer has the history to continue the old instance.

If the Job is launched again with the same identifying JobParameters after the metadata has been deleted, the system may create a new JobInstance. The Job may reprocess business data that was processed before.

Therefore, you need to design output data to be idempotent or to have a business key to avoid creating duplicate data when re-running the same batch.

### Loss of History in Operational Tools

Screens or lookup APIs based on JobExplorer and JobRepository will no longer return executions that have been purged. If the operations team needs to look up long-term history, archive before deleting.

### Do Not Delete Business Data by Default

Spring Batch metadata and business data have different lifecycles. For example:

- BATCH_JOB_EXECUTION stores the history of a run.
- The CUSTOMER table stores the imported customer data.
- The IMPORT_AUDIT table may store the batch code, record count, and reconciliation result.
- Output files may be stored in object storage.

Purging metadata should not automatically delete business tables or files. If business data also needs retention, design a separate process with reference keys and the retention requirements of that data itself.

### Consider Sensitive Data

JobParameters and ExecutionContext can contain file paths, customer codes, tokens, or other information depending on how the application uses them. You should not store passwords or secrets in metadata. When you need to delete sensitive data on request, you need to determine which tables, which archives, and which logs the data lives in; the overall retention must meet the corresponding security requirements.

## 6. A Safe Order for Deleting Metadata

When the schema has foreign key constraints, you must delete child records before parent records. Even when the current schema does not declare foreign keys, this order still helps maintain consistency and avoid orphaned data.

With the common standard tables, the logical order is:

1. `BATCH_STEP_EXECUTION_CONTEXT` — the context of each StepExecution.
2. `BATCH_STEP_EXECUTION` — the Step executions.
3. `BATCH_JOB_EXECUTION_CONTEXT` — the context of each JobExecution.
4. `BATCH_JOB_EXECUTION_PARAMS` — the parameters of each JobExecution.
5. `BATCH_JOB_EXECUTION` — the Job executions.
6. `BATCH_JOB_INSTANCE` — the JobInstance last.

~~~mermaid
flowchart TD
    A["Select eligible JobInstances"] --> B["Delete Step ExecutionContext"]
    B --> C["Delete StepExecution"]
    C --> D["Delete Job ExecutionContext"]
    D --> E["Delete JobExecutionParams"]
    E --> F["Delete JobExecution"]
    F --> G["Delete JobInstance"]
    G --> H["Record audit and the number cleaned up"]
~~~

The order above applies to the standard metadata tables. If the application has custom tables that reference JobExecution ID, StepExecution ID, or JobInstance ID, you must identify and handle those tables according to the actual relationships. You must not delete a parent record while dependent child records remain.

Sequence or generator tables used to allocate IDs usually do not need to be deleted per JobInstance. Do not reset a sequence to a lower value because that can cause ID collisions with the data that remains.

## 7. Identifying the Set of Eligible JobInstances

The most important step in the retention process is identifying candidates accurately. You should not start with a direct DELETE statement on an execution table.

A candidate should be identified at the JobInstance level, and only then delete all the related executions and child data.

Example of the logical condition:

~~~sql
SELECT ji.JOB_INSTANCE_ID
FROM BATCH_JOB_INSTANCE ji
WHERE ji.JOB_NAME = :jobName
  AND EXISTS (
      SELECT 1
      FROM BATCH_JOB_EXECUTION je
      WHERE je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
  )
  AND NOT EXISTS (
      SELECT 1
      FROM BATCH_JOB_EXECUTION je
      WHERE je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
        AND (
            je.END_TIME IS NULL
            OR je.END_TIME >= :cutoff
            OR je.STATUS NOT IN (:allowedTerminalStatuses)
        )
  );
~~~

This is an example describing the candidate-selection condition; the syntax for binding the list of statuses depends on the JDBC framework and database in use.

Meaning:

- Only consider the specified Job name.
- The JobInstance must have executions.
- If any execution has not ended, is newer than the cutoff, or has a status not allowed to be cleaned up, the JobInstance is not eligible.
- Only when all executions satisfy the policy is the instance put into the purge list.

In practice, the policy may need different cutoffs for COMPLETED, FAILED, STOPPED, and ABANDONED. In that case, the candidate condition needs to evaluate the age and status of each execution under the exact rules instead of using one common list of statuses.

### Why Must Executions That Have Not Ended Be Kept?

An execution with an END_TIME of NULL may be running or may have hit an incident that left the metadata not completely updated. Deleting it can corrupt the operational state or delete metadata that another process is still using.

You should not conclude that an execution is hung just because its START_TIME is old. Check the actual process, heartbeat, application logs, and the database lock state. If you need to stop or abandon an execution, use a controlled operational procedure before considering retention.

## 8. Example SQL Purge Process

The example below illustrates using a temporary candidate table or staging table to hold the list of approved JobInstances. How to create a temporary table and the transaction syntax depend on the database; adjust to the management system in use.

Suppose the staging table `PURGE_JOB_INSTANCE` contains the `JOB_INSTANCE_ID`s selected per the policy in the previous section and exists only within the scope of one maintenance run.

~~~sql
-- 1. Delete StepExecutionContext first.
DELETE FROM BATCH_STEP_EXECUTION_CONTEXT
WHERE STEP_EXECUTION_ID IN (
    SELECT se.STEP_EXECUTION_ID
    FROM BATCH_STEP_EXECUTION se
    JOIN BATCH_JOB_EXECUTION je
      ON je.JOB_EXECUTION_ID = se.JOB_EXECUTION_ID
    JOIN PURGE_JOB_INSTANCE p
      ON p.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
);

-- 2. Delete StepExecution.
DELETE FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID IN (
    SELECT je.JOB_EXECUTION_ID
    FROM BATCH_JOB_EXECUTION je
    JOIN PURGE_JOB_INSTANCE p
      ON p.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
);

-- 3. Delete JobExecutionContext.
DELETE FROM BATCH_JOB_EXECUTION_CONTEXT
WHERE JOB_EXECUTION_ID IN (
    SELECT je.JOB_EXECUTION_ID
    FROM BATCH_JOB_EXECUTION je
    JOIN PURGE_JOB_INSTANCE p
      ON p.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
);

-- 4. Delete JobExecution parameters.
DELETE FROM BATCH_JOB_EXECUTION_PARAMS
WHERE JOB_EXECUTION_ID IN (
    SELECT je.JOB_EXECUTION_ID
    FROM BATCH_JOB_EXECUTION je
    JOIN PURGE_JOB_INSTANCE p
      ON p.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
);

-- 5. Delete JobExecution.
DELETE FROM BATCH_JOB_EXECUTION
WHERE JOB_INSTANCE_ID IN (
    SELECT JOB_INSTANCE_ID
    FROM PURGE_JOB_INSTANCE
);

-- 6. Delete JobInstance last.
DELETE FROM BATCH_JOB_INSTANCE
WHERE JOB_INSTANCE_ID IN (
    SELECT JOB_INSTANCE_ID
    FROM PURGE_JOB_INSTANCE
);
~~~

This is a sample SQL illustrated with standard table names, not a script that can be run as-is on every database. You need to confirm the schema, data types, table prefix, column names, and the foreign keys of the Spring Batch version being deployed. Some systems also have custom tables that reference metadata; those tables must be handled before deleting parent records.

### Transactions and Batch Size

If you purge millions of executions in one large transaction, the transaction log can grow sharply, locks can be held long, and rollback becomes expensive.

You can split the work into groups of JobInstances:

1. Select a small batch of candidates.
2. Delete the child tables in the correct order.
3. Delete JobExecution and JobInstance.
4. Record the number processed.
5. Commit the transaction.
6. Repeat for the next batch.

The batch size depends on the database, the metadata size, and the acceptable lock time. Measure on a copy of representative data before applying in production.

If you need to ensure all of a candidate's tables are deleted atomically, keep the candidate's operations in the same transaction. If you split into candidate groups, each group can be an independent transaction unit.

### Do Not Rely on ON DELETE CASCADE Without Confirming

Some schemas may declare foreign keys with cascade, while others do not have it or are customized. You should not assume that deleting a JobInstance will automatically delete all related data.

Check the actual DDL. If you use cascade, you still need to understand clearly whether custom tables get deleted too and whether the deletion affects audit data that needs to be kept.

## 9. Spring Batch APIs Related to Metadata

Spring Batch provides many APIs for looking up and operating Jobs. You need to distinguish their functions when building retention.

### JobRepository

`JobRepository` is where Job and Step metadata is stored. The framework uses it when creating executions, updating status, and storing the ExecutionContext.

JobRepository is not a general retention API for deleting JobInstance history by period. You should not try to call internal methods of the DAO or the repository implementation to delete arbitrarily.

If you need to purge, the application usually implements its own maintenance process using JDBC or database administration tools, based on the defined schema and policy.

### JobExplorer

`JobExplorer` provides a way to read stored JobInstance, JobExecution, and StepExecution information. It is useful for:

- Looking up execution history.
- Finding running Jobs.
- Reading JobParameters and ExecutionContext.
- Viewing Step status and statistics.
- Supporting dashboards or operational tools.

JobExplorer is a lookup API, not an API for deleting metadata. You can use it to serve screens or verification steps before purging, but do not confuse being able to read an execution with having the right to delete it.

### JobOperator

`JobOperator` provides operational actions such as start, restart, stop, or abandon of a JobExecution depending on configuration and version. This is a tool for controlling the Job lifecycle.

JobOperator does not replace a retention policy. For example, abandoning an execution is an operational decision about whether that execution can continue; it does not mean the metadata is deleted or has passed its retention period.

### JDBC and a Separate Retention Service

A retention service can use JdbcTemplate or plain JDBC to:

- Compute the cutoff.
- Select candidates by Job name and status.
- Check execution relationships.
- Archive if needed.
- Delete child and parent data in order.
- Record audit and metrics.

This service needs to run on the exact datasource that holds the JobRepository metadata and use a suitable transaction manager. You should not run the script with a different business datasource and then assume it is operating on the same metadata database.

## 10. Organizing Maintenance as a Separate Job

For a large Spring Batch system, you can build a separate Job to clean up metadata. Using a separate Job helps track maintenance runs, configure a schedule, log, and apply a unified retry or monitoring mechanism.

Example of a Tasklet that calls a retention service:

~~~java
@Bean
Tasklet purgeBatchMetadataTasklet(
        MetadataRetentionService retentionService) {

    return (contribution, chunkContext) -> {
        RetentionResult result = retentionService.purgeEligibleInstances();

        contribution.incrementWriteCount(result.deletedJobInstances());

        return RepeatStatus.FINISHED;
    };
}

@Bean
Step purgeBatchMetadataStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet purgeBatchMetadataTasklet) {

    return new StepBuilder("purgeBatchMetadataStep", jobRepository)
        .tasklet(purgeBatchMetadataTasklet, transactionManager)
        .build();
}

@Bean
Job purgeBatchMetadataJob(
        JobRepository jobRepository,
        Step purgeBatchMetadataStep) {

    return new JobBuilder("purgeBatchMetadataJob", jobRepository)
        .start(purgeBatchMetadataStep)
        .build();
}
~~~

The example focuses on how to organize the Job and Step. The parts for selecting candidates, archiving, transactions, and deleting the tables must be implemented in `MetadataRetentionService` according to the real schema.

Note that the maintenance Job also has its own metadata. While running, the maintenance JobExecution has no END_TIME and must be protected by retention. You must not select the instance of the currently executing Job itself as a candidate. You can limit the list of Job names to clean up or explicitly exclude the maintenance Job.

If the purge service uses its own transaction or commits per batch, do not assume the entire operation is enclosed by the Tasklet's transaction. Configure the transaction boundary deliberately to avoid reporting a completed result when part of the purge has not yet been committed.

### Maintenance Schedule

You can run the retention Job outside peak hours or on a weekly schedule. The frequency depends on the metadata growth rate and the retention requirements.

Some principles:

- Do not run multiple purge instances concurrently on the same schema if there is no locking mechanism.
- Use suitable identifying JobParameters to control each maintenance run.
- Record the cutoff, the list of Jobs considered, and the number of candidates.
- Set a limit on the number of candidates per run.
- Be able to continue after an error without deleting twice or missing anything.
- Monitor run time, the number of rows deleted, and database size.

## 11. Controlling Concurrent Runs and Hung Executions

One of the biggest risks of retention is selecting candidates while another Job is still running or has just been launched.

For example, maintenance reads metadata and sees an old JobExecution. If another application is restarting that JobInstance, retention may delete data exactly when the framework needs to read the checkpoint.

Some control measures:

- Only select executions that have ended and have met the retention period.
- Keep FAILED and STOPPED within the restart window.
- Do not clean up a JobInstance that has any active execution.
- Run maintenance with a suitable lock or singleton mechanism.
- Limit candidates and purge in small batches.
- If possible, use transaction isolation and locks suited to the database to reduce race conditions.
- Do not allow multiple retention processes to run overlapping on the same data set.

### Executions That Have Been STARTED for Too Long

An execution with a very old START_TIME but no END_TIME can be due to:

- The application was shut down abruptly.
- The server or container lost its connection.
- The process died before updating the status.
- An execution is really running for a long time.
- A fault or incident left the metadata in an inconsistent state.

You should not use the condition `START_TIME < cutoff` to automatically delete these executions.

The handling process should be:

1. Look up the related JobExecution and StepExecution.
2. Check the host, process, container, and logs.
3. Confirm whether the execution is still active.
4. If needed, request a stop or handle the state through an operational procedure.
5. Only put the metadata into retention after the final status is clear and the retention period has passed.

Do not update the status in the BATCH_* tables with SQL yourself just to make a candidate eligible. Changing the state directly can cause the metadata to not reflect the Job's reality accurately.

## 12. Archive, Backup, and Audit

Retention does not necessarily mean the data disappears completely. For systems with long-term traceability requirements, you can move metadata to a history storage area before purging.

An archive process can include:

1. Select the eligible JobInstances.
2. Read all the related JobExecutions and StepExecutions.
3. Create archive records or an export file.
4. Record a checksum or archive version code.
5. Confirm the archive can be read back.
6. Record an audit of the number of instances and executions archived.
7. Only after that purge the metadata in the operational database.

The archive needs to preserve the relationships among JobInstance, JobExecution, and StepExecution so that, on lookup, you can understand the history of a logical processing.

You should not archive by arbitrarily copying the BATCH_* tables and then assuming you can restore them as-is into a different database. Restoring metadata can depend on the schema version, sequences, the serialized context data type, and the application configuration. If you need recoverability, design and test a clear restore process.

Backing up the database before a large purge is also a protective measure. A backup is only useful when its restorability has been checked and the backup retention period meets the operational requirements.

## 13. Performance and Database Maintenance After a Purge

Deleting metadata does not always immediately reduce the database file on disk. How the database reclaims space depends on the management system.

After a large purge, you need to monitor:

- The number of rows remaining in each BATCH_* table.
- The size of data and indexes.
- The query time of JobExplorer or dashboards.
- Transaction log and replication lag.
- Lock waits and transaction time.
- The execution plan of the candidate query.
- The growth rate of metadata after applying retention.

Some databases need separate maintenance operations to update statistics or reclaim space. For example, PostgreSQL has the VACUUM mechanism; SQL Server has index and file management operations; Oracle has corresponding segment management methods. Do not run space-reclamation commands out of habit without understanding the impact on locks, I/O, and the system's maintenance time.

### Indexes and the Candidate Query

Retention queries usually filter by Job name, JobInstance ID, JobExecution ID, status, and end_time. Spring Batch's default indexes can support part of the query, but performance depends on the database, the amount of metadata, and the actual filter conditions.

Before adding an index:

1. Measure the candidate query time on representative data.
2. Look at the execution plan.
3. Check the existing indexes in the schema.
4. Determine whether the additional index improves the query.
5. Evaluate the metadata write cost of adding an index.

You should not add duplicate indexes or change the Spring Batch schema without a migration and a compatibility plan.

## 14. Security and Permissions for Executing a Purge

The retention service has permission to delete metadata, so it needs to be controlled.

Some principles:

- The database account used for retention only has the necessary permissions on the metadata schema.
- Do not grant permission to delete the whole schema if you only need to delete the BATCH_* tables.
- Separate the permissions for reading candidates, archiving, and deleting when the process requires multi-step control.
- Store an audit of the person or process that launched it, the time, the cutoff, and the result.
- Do not write secrets or sensitive data from JobParameters into logs.
- Require confirmation or approval for the first purge or a large-scale purge per the organization's process.

If retention runs automatically, the configuration needs safety limits. For example, do not allow the cutoff to exceed a default threshold or delete more than the allowed number of JobInstances in one run without operational confirmation.

## 15. Testing the Retention Process

Before applying in production, you need to test on a test database with the corresponding schema and Spring Batch version.

Scenarios to check:

| Scenario | Expected Result |
|---|---|
| A JobInstance with only COMPLETED executions that are past due | Selected for purge |
| A JobInstance with a COMPLETED execution that is still recent | Kept |
| A JobInstance with a FAILED execution still within the restart window | Kept |
| A JobInstance with a STOPPED execution that has not expired | Kept |
| A JobInstance with a STARTED execution or null END_TIME | Kept |
| A JobInstance with an UNKNOWN status | Kept for investigation |
| A JobInstance with multiple executions, one of which is still recent | Keep the whole instance |
| A JobInstance with all executions terminal and all past due | Selected per policy |
| A custom table references an execution | The dependent records are handled in the right order |
| The purge hits an error mid-transaction | Does not leave a group of metadata half-deleted if the design requires atomicity |
| Re-running maintenance after a successful purge | Does not wrongly delete new data or data that is not eligible |

You also need to test the business consequences:

- A Job that has completed but whose metadata was purged can be launched again with the old identifying parameters as a new JobInstance.
- The writer has idempotency or a business key to prevent duplicate data.
- Dashboards and operational tools no longer display purged executions.
- The archive can be looked up independently if the system has a history-retention requirement.
- The maintenance Job does not select its own running execution.

Do not only test the number of rows deleted. You need to confirm that the child and parent tables are both consistent, there are no orphaned records, and the retained JobInstances can still restart as expected.

## 16. Recommended Operating Process

A practical retention process can be organized in the following steps:

1. **Read the policy:** determine the Job names, the statuses allowed to be cleaned up, and the corresponding retention periods.
2. **Compute the cutoff:** use a clear time milestone, a uniform time zone, and record the cutoff value.
3. **Select candidates:** select the JobInstances whose JobExecutions have all ended and meet retention.
4. **Protect active executions:** exclude instances that have executions that have not ended or have an unclear status.
5. **Archive or back up:** do so if audit or recovery requirements need to keep history.
6. **Check counts:** record the expected number of JobInstances, JobExecutions, and StepExecutions to be deleted.
7. **Purge in order:** delete the context, StepExecution, parameters, JobExecution, and JobInstance.
8. **Commit per batch:** limit the transaction size to avoid long-held locks.
9. **Record audit:** store the cutoff, the number of rows deleted, the run time, and errors.
10. **Monitor the database:** check size, locks, transaction log, and metadata queries after the purge.

You can run this process on a daily or weekly schedule. The frequency should be based on the metadata growth rate and the degree to which retention affects the database.

## 17. Common Mistakes

### Directly Deleting Old JobExecutions

A JobInstance can have multiple JobExecutions due to restarts. Deleting individual executions without considering the whole instance can lose the historical relationships and create inconsistent metadata. Select and clean up by JobInstance group.

### Only Checking START_TIME

A long-running Job may have started before the cutoff but still be active. Use END_TIME and a terminal status as the main conditions; executions that have not ended must be kept.

### Deleting FAILED Right After Failure

FAILED can be a state that needs restart. Keep it long enough for investigation and recovery, or only purge after the execution is handled per the operational policy.

### Deleting Only the Parent Table

Deleting a JobInstance or JobExecution while the context, parameters, and StepExecution tables still exist can cause foreign key errors or orphaned data. Always identify the relationships and delete child records first.

### Relying on Cascade Without Checking the Schema

Not every Spring Batch schema has the same foreign keys or cascade. Check the actual DDL before deploying the script.

### Treating Metadata as Business Data

Purging BATCH_* should not delete output data, and keeping BATCH_* also does not replace storing business data. The two policies must be independent.

### Not Accounting for Re-Running the Same JobParameters

When metadata is deleted, the same identifying JobParameters can create a new JobInstance. If the writer is not idempotent, business data can be written in duplicate.

### Running the Purge in One Too-Large Transaction

A too-large transaction can increase locks, the transaction log, and rollback time. Split the candidates into suitable batches and measure performance.

### Not Storing Audit

If you do not record the cutoff, the number, and the scope deleted, it is very hard to explain why a JobInstance is no longer in the dashboard or to trace a purge run.

## 18. Key Points to Remember

- JobRepository stores the metadata needed to identify JobInstance, track JobExecution and StepExecution, and support restart.
- Retention must be based on the Job name, status, end_time, and the restart window of each type of Job.
- Select candidates at the JobInstance level; only purge when all related executions are eligible.
- Executions that are running, have no end_time, or have an UNKNOWN status must be protected.
- Delete child tables before parent tables: StepExecutionContext, StepExecution, JobExecutionContext, JobExecutionParams, JobExecution, and JobInstance.
- JobExplorer is for reading metadata; JobOperator is for operational actions; do not treat them as a general purge API.
- When you need to delete metadata, you can implement a JDBC service or a separate maintenance Job based on the actual schema.
- Archive and audit before purging if operational or audit requirements need to keep history.
- Purging metadata does not delete business data and can make an old JobInstance unrestartable.
- The writer and business processes need appropriate idempotency to avoid duplicate writes when the Job is re-run after the metadata has expired.
- Run in batches, with concurrency control, test on the real schema, and monitor the impact on the database.

A correctly designed retention policy helps JobRepository maintain a reasonable size while still preserving the ability to restart, investigate, and audit for the necessary period.

