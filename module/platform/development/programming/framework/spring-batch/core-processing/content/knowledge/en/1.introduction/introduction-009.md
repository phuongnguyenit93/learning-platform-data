# The Role of the Metadata Repository in Spring Batch

In a Spring Batch application, a job needs to know more than just which data to read and how to process it. The framework also has to know whether the job has been launched, which step it is currently at, how the previous run ended, and whether it can continue after an incident. Spring Batch stores this operational information in the **metadata repository**.

The central component of that mechanism is the `JobRepository`. This is where Spring Batch writes and queries metadata about jobs, steps, and execution state. The metadata repository helps the framework manage the job lifecycle, identify a logical run, support restart, and provide data for operational monitoring.

## 1. What Is a Metadata Repository?

Metadata is data that describes the batch processing. For example, metadata can tell you:

- Which job has been defined and which logical job a run belongs to.
- When the job was launched, when it ended, and what its status is.
- Which step has started, and which step has completed or failed.
- How many items were read, written, skipped, or rolled back.
- The most recent checkpoint of a step so that processing can continue.

In Spring Batch, `JobRepository` is the abstraction responsible for storing and retrieving this information. Applications usually use a JDBC-based repository and a relational database so that the metadata remains after the application process stops or restarts. The specific configuration depends on the Spring Batch version and the application configuration.

The metadata repository is not where the business data that the job is processing is stored. For example, when a job imports one million orders, the order content and the business results belong to the application's data systems; the repository stores information about how many orders the job has read, processed, and written, what the current state is, and where it can continue from.

## 2. Distinguishing Job, JobInstance, and JobExecution

To understand the role of the repository, you need to distinguish the job definition from a specific execution.

| Concept | Meaning |
| --- | --- |
| `Job` | Defines the batch process, consisting of one or more steps and how they are orchestrated. |
| `JobParameters` | The parameters passed in when launching the job. Each parameter can be marked as identifying or non-identifying. |
| `JobInstance` | A logical run of a job, determined by the job name together with the identifying parameters. |
| `JobExecution` | One specific execution of a `JobInstance`. An instance can have multiple executions if a restart is needed after an unsuccessful run. |
| `StepExecution` | Information about one specific execution of a step within a `JobExecution`. |
| `ExecutionContext` | A key-value state store that lets batch components restore progress on restart. |

For example, an application has a job `importOrders` that imports orders by day. When run with the identifying parameter `businessDate=2026-11-15`, Spring Batch determines a `JobInstance` corresponding to that job and that business date.

If the first run fails, relaunching with the same job and the same identifying parameters can create a new `JobExecution` belonging to the same `JobInstance`. The repository keeps the history of the previous run and the metadata needed for the restart. If the business date changes, that is a different `JobInstance`.

This relationship can be pictured as follows:

```text
Job: importOrders
  + identifying parameter: businessDate=2026-11-15
                 |
                 v
          JobInstance A
             /     \
            v       v
    JobExecution 1  JobExecution 2
        FAILED       COMPLETED
            |           |
            +-- restart-+

Each JobExecution has StepExecutions corresponding to the steps
executed in that run.
```

`JobInstance` expresses the identity of the logical piece of work; `JobExecution` expresses one attempt to perform that work. Separating the two concepts lets Spring Batch distinguish a new job from a restart.

## 3. Managing State and Execution History

When a job is launched, Spring Batch creates and updates metadata records through the `JobRepository`. Throughout the job lifecycle, the repository stores the state of the job and of each step, along with timestamps and processing counters.

Some commonly seen `BatchStatus` values include:

| Status | General meaning |
| --- | --- |
| `STARTING` | The job or step is being initialized. |
| `STARTED` | The job or step is executing. |
| `COMPLETED` | The execution completed successfully according to the framework's state. |
| `FAILED` | The execution ended because of an error. |
| `STOPPING` | A stop request is being processed. |
| `STOPPED` | The execution has stopped on request or through a controlled stop mechanism. |
| `ABANDONED` | The execution is marked as not to be restarted. |
| `UNKNOWN` | The execution state cannot be determined with certainty. |

Spring Batch also stores the `ExitStatus`. These two pieces of information serve different purposes:

- `BatchStatus` describes the lifecycle state managed by the framework, such as `COMPLETED` or `FAILED`.
- `ExitStatus` contains the exit code and the exit message. The application can use the exit code to represent a business result or to control the next flow.

For example, a job can complete technically but find that there are no new records. The job can still have `BatchStatus.COMPLETED`, while the `ExitStatus` carries a custom code such as `NO_DATA`. Therefore, when viewing the run history, you should not treat these two fields as one.

The metadata of a `StepExecution` also has counters such as the number of items read, written, filtered, skipped, committed, and rolled back. This information helps determine how much data each step has processed and supports investigation when results are not as expected.

## 4. Supporting Restart and Progress Recovery

An important role of the metadata repository is supporting restart. A batch job can run for a long time; the process can hit errors due to input data, connections, resources, or infrastructure incidents. If all progress lived only in memory, restarting the application could force the job to reprocess from the beginning.

Spring Batch uses the `ExecutionContext` to store the state needed for continuation. There are two commonly seen scopes:

- **Job `ExecutionContext`** stores state at the whole-job scope and can be used to share information between steps or to restore the processing flow.
- **Step `ExecutionContext`** stores the step's own state and is usually used to remember the read position or the reader's checkpoint.

For a step that processes in chunks, the framework processes a group of items and then commits according to the configured transaction boundary. Components that support restart, such as a reader that implements `ItemStream`, can write the current position into the `ExecutionContext`. When the step is restarted, the saved state is loaded back so that the reader continues from the appropriate position.

For example, a reader reads a CSV file line by line. After a chunk is committed, the reader can save the number of lines read. If the application stops afterward, a restart can reopen the file and continue from the checkpoint instead of re-reading the entire file.

```text
First run
  Read lines 1..100  -> process -> commit
  Read lines 101..200 -> process -> commit
  Read lines 201..   -> an error occurs
                         |
                         v
               Save metadata/checkpoint
                         |
                         v
Restart            Restore state
  Continue from the appropriate checkpoint
```

The repository only stores and provides metadata. Actual restartability also depends on how the reader, writer, and processor are designed. Processing components must support saving/restoring state when needed; write operations to external systems should also be designed to be idempotent or to have a duplicate-write prevention mechanism. Saving a checkpoint does not automatically guarantee that every external side effect is performed exactly once.

The `ExecutionContext` should contain small, stable values that are necessary to continue processing, for example a record sequence number or the last key processed. Do not use it as a place to store all business data or large objects.

## 5. Determining Run Identity with JobParameters

The `JobRepository` relies on the job name and the `JobParameters` marked as identifying to determine the `JobInstance`. Therefore, the choice of identifying parameters directly affects the ability to run anew and to restart.

Example:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("requestedBy", "scheduler", false)
    .toJobParameters();

jobLauncher.run(importOrdersJob, parameters);
```

In this example:

- `businessDate` is an identifying parameter. Two calls to the same job with the same business date target the same `JobInstance`.
- `requestedBy` is a non-identifying parameter. Changing the person or source that launched the run does not create a new `JobInstance`.

Mark a parameter as identifying if that value truly distinguishes a logical unit of work. For example, if each input file is a separate piece of work, the file name or the batch code may need to be marked identifying. If a parameter only records operational information such as the requester or a tracking label, it usually does not need to determine the instance identity.

When a `JobInstance` is already `COMPLETED`, relaunching the same job with the same identifying parameters is usually not treated as a new job, and Spring Batch rejects rerunning a completed instance. To perform a new business run, you need to provide a new identifying parameter, such as a batch code or a processing version. Conversely, when an instance ends in a restartable state such as `FAILED` or `STOPPED`, rerunning with the same identity can continue that instance according to Spring Batch's rules.

A poorly designed parameter set can cause two problems: inadvertently creating many instances for the same piece of work, or inadvertently causing two different pieces of work to be treated as the same instance. Therefore, you need to clearly determine the unit of work before choosing identifying parameters.

## 6. Supporting Orchestration and Avoiding Duplicate Runs

The repository is part of Spring Batch's execution orchestration mechanism. When launching a job, the framework checks the metadata to know whether the corresponding instance already exists, whether any execution is running, and whether the previous state allows restart.

With a database-based repository, the operations that create executions are protected by transactions and by synchronization mechanisms appropriate to the repository, transaction manager, and database configuration. This helps limit two processes concurrently creating conflicting executions for the same `JobInstance`.

In a multi-node environment, nodes need to share a single metadata repository with a consistent configuration if they jointly orchestrate a group of jobs. If each node writes to its own metadata store, they do not share the same view of execution history and state; the risk of duplicate runs or incorrect restarts increases.

The repository also does not replace duplicate-processing prevention at the business layer. For messages, APIs, or external target systems, the application still needs a business key, a unique constraint, an idempotency key, or an equivalent mechanism where appropriate.

## 7. Supporting Monitoring and Operational Actions

The metadata repository provides the underlying data for job query and control tools:

- `JobExplorer` provides a read-only API to look up stored job instances, job executions, step executions, and execution contexts.
- `JobOperator` provides job-level operational actions, such as launching, stopping, or restarting an execution when the framework's conditions are met.

For example, a monitoring page can use the metadata to display the start time, end time, current status, run duration, and number of records processed. When a job fails, an operator can view the related execution and step to find where the error occurred before deciding whether to restart.

`JobRepository` is the core metadata management component; `JobExplorer` and `JobOperator` are other abstractions that help applications read or operate on the execution history. They are closely related but are not the same role.

## 8. Where Is Metadata Usually Stored?

With the common JDBC configuration, Spring Batch stores metadata in tables belonging to the batch schema. The default table names usually have the prefix `BATCH_`, for example:

| Table | Main information |
| --- | --- |
| `BATCH_JOB_INSTANCE` | The identity of job instances. |
| `BATCH_JOB_EXECUTION` | Job executions, their status, and timestamps. |
| `BATCH_JOB_EXECUTION_PARAMS` | The parameters of each job execution. |
| `BATCH_STEP_EXECUTION` | The step's state, counters, and execution information. |
| `BATCH_JOB_EXECUTION_CONTEXT` | The execution context at the job scope. |
| `BATCH_STEP_EXECUTION_CONTEXT` | The execution context at the step scope. |

The specific table names, columns, and schema can change depending on the Spring Batch version, the database, and the prefix configuration. When deploying, you need to use the schema script that corresponds to the library version and manage schema changes along with the application's upgrade lifecycle.

Because the metadata is the basis for restart and monitoring, this database needs to be managed as an important part of the batch application. You need a policy for backup, access control, and appropriate history cleanup. Do not delete the metadata of jobs that still need restartability or that are being operated.

## 9. Limitations to Understand Correctly

The metadata repository supports execution management, but it does not by itself solve every problem of a batch system:

- The repository does not replace the storage of the application's business data, input files, or output results.
- Having metadata does not mean the job restarts automatically. The job must be launched again and the processing components must support recovery.
- A checkpoint does not guarantee that side effects in external systems are performed exactly once. You need to consider transactions, idempotency, and reprocessability.
- Metadata is accurate only when the application records state correctly and the repository has an appropriate transaction configuration. If the metadata and the business data live in different transaction managers or systems, you need to design how to handle the situation where one side commits while the other fails.
- Directly editing or deleting metadata records can destroy restartability or leave the job state inconsistent. You should use Spring Batch's APIs and operational procedures when working with executions.

## 10. Applying This When Designing a Job

When building a new job, determine the logical unit of work first, and then choose appropriate identifying parameters. Next, decide which state needs to be stored in the `ExecutionContext`, make sure the reader or writer can restore from that state, and check how the metadata transaction coordinates with the data-processing transaction.

In a production environment, you should use a durable metadata repository that is shared consistently among the nodes with the same job-running responsibility. You need to monitor `BatchStatus`, `ExitStatus`, the step counters, and the execution history so that operators have enough information to investigate. Finally, try the scenario where a job fails midway and is then restarted, to confirm that the checkpoint and the data-writing operations work as expected.

When these mechanisms are configured correctly, the metadata repository becomes the foundation that lets Spring Batch track each run, distinguish a new job from a restarted job, recover progress, and support operating batch processes in a controlled way.
