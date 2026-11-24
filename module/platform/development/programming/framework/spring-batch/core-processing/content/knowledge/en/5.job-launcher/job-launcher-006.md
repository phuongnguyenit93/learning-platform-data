# A Running Job and Duplicate Launches

When an application calls JobLauncher to launch a Spring Batch Job, the same request may be sent multiple times: a user clicks a button twice, a browser retries an HTTP request, a scheduler runs in duplicate on multiple nodes, or a message broker redelivers a message. Without control, the system may create multiple runs for the same batch of data.

Spring Batch has a protection mechanism based on JobInstance, JobExecution, and JobRepository. This mechanism helps prevent two JobExecutions from running for the same JobInstance, and distinguishes a new run from a restart. However, it works correctly only when the JobParameters are designed appropriately and the processes share a JobRepository capable of coordination.

## 1. Distinguishing JobInstance and JobExecution

Two JobLauncher calls with the same Job name are not necessarily two different runs. Spring Batch identifies a JobInstance by:

- The Job name.
- The identifying JobParameters of the run.

A JobInstance can have multiple JobExecutions. Each JobExecution represents one specific execution of the JobInstance.

~~~text
Job: importOrders
Identifying parameters:
  businessDate = 2026-11-15
  sourceFileId = file-8421

JobInstance A
  JobExecution 101: FAILED
  JobExecution 108: STARTED
  JobExecution 108: COMPLETED
~~~

In the example, three executions belong to the same JobInstance. Execution 108 is the restart after execution 101 failed.

It can be understood as:

- **JobInstance** identifies the logical work to be performed, for example importing one day's orders or processing a specific file.
- **JobExecution** records one execution of that logical work, including the run time, status, errors, and StepExecutions.
- **JobRepository** stores the metadata of JobInstance, JobExecution, StepExecution, and ExecutionContext.

Therefore, "the same Job" and "the same JobInstance" are two different concepts. Spring Batch recognizes a duplicate launch based on the same JobInstance, not only on the Job name.

## 2. What happens when you launch the same JobInstance?

When JobLauncher receives a Job together with JobParameters, the JobRepository checks the execution history of the corresponding JobInstance. The result depends on the state of the previous executions.

| Previous execution state | Common result when re-launching with the same identifying parameters |
|---|---|
| Running (STARTING, STARTED) | Throws JobExecutionAlreadyRunningException |
| Completed (COMPLETED) | Throws JobInstanceAlreadyCompleteException |
| Abandoned (ABANDONED) | The JobInstance cannot be restarted in the usual way; usually receives JobInstanceAlreadyCompleteException |
| Failed (FAILED) | A new JobExecution can be created to restart if the Job allows restart |
| Stopped (STOPPED) | A new JobExecution can be created to continue if the state and configuration allow it |

This means a duplicate call while the Job is running does not create an additional JobExecution running concurrently for the same JobInstance. The second call receives an error so the application knows the work has already been launched.

If the previous execution has completed, Spring Batch also does not rerun that JobInstance by itself. If the previous execution failed or stopped, a call with the same parameters can be a valid restart request. When restarting, Spring Batch uses the stored metadata and checkpoints to continue according to the Job's and Step's restart rules.

A Job configured not to restart can reject a rerun after a failure with JobRestartException.

## 3. Recognizing duplicate launches through JobParameters

The example below creates parameters for an order import Job:

~~~java
JobParameters jobParameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("sourceFileId", "file-8421", true)
        .addString("requestId", requestId, false)
        .toJobParameters();
~~~

The third argument of the addString methods is the identifying flag:

- businessDate and sourceFileId are identifying. They identify the business batch to be processed.
- requestId is non-identifying. It can be used to trace the request or for logging but does not change the identity of the JobInstance.

If two requests have the same Job name, the same businessDate, and the same sourceFileId, they point to the same JobInstance even though requestId differs.

If you mark requestId as identifying, each request can create its own JobInstance. In that case, two requests that actually ask to process the same file can still run as two different JobInstances.

### Choose identifying parameters according to the business

An identifying parameter should represent the unit of work that the system wants to process only once at a time or once in its lifetime.

For example:

| Job | Suitable identifying parameters |
|---|---|
| Import an order file | An immutable file ID or the file checksum |
| Aggregate daily revenue | Business date and tenant code |
| Synchronize one account | Account code and the version of the data to synchronize |
| Process a batch of messages | Batch code or offset range |
| Generate a periodic report | Report period and report type |

Avoid using the current timestamp, a new UUID, or a new request ID as an identifying parameter if the goal is for Spring Batch to recognize repeated requests for the same work. Each new value like that creates a new JobInstance identity.

If a file can be overwritten at the same path, using only the path as an identifying parameter may not be enough. Use an immutable file ID, a checksum, or a version to distinguish the actual content.

## 4. Calling JobLauncher and handling duplicate errors

An application usually calls JobLauncher from a service or controller. The example below illustrates creating stable JobParameters and handling the cases where the launcher rejects the request:

~~~java
@Service
public class OrderImportService {

    private final JobLauncher jobLauncher;
    private final Job importOrdersJob;

    public OrderImportService(
            JobLauncher jobLauncher,
            @Qualifier("importOrdersJob") Job importOrdersJob) {
        this.jobLauncher = jobLauncher;
        this.importOrdersJob = importOrdersJob;
    }

    public JobExecution launch(
            String businessDate,
            String sourceFileId,
            String requestId) throws Exception {

        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", businessDate, true)
                .addString("sourceFileId", sourceFileId, true)
                .addString("requestId", requestId, false)
                .toJobParameters();

        return jobLauncher.run(importOrdersJob, parameters);
    }
}
~~~

At the calling layer, you need to handle the exceptions that JobLauncher can throw:

~~~java
try {
    JobExecution execution =
            orderImportService.launch(businessDate, fileId, requestId);

    return ResponseEntity.accepted()
            .body(execution.getId());
} catch (JobExecutionAlreadyRunningException ex) {
    // The corresponding JobInstance has a running execution.
    return ResponseEntity.status(HttpStatus.CONFLICT)
            .body("The job for this data batch is already running");
} catch (JobInstanceAlreadyCompleteException ex) {
    // The JobInstance has completed.
    return ResponseEntity.status(HttpStatus.CONFLICT)
            .body("This data batch has already been processed");
} catch (JobRestartException ex) {
    // The JobInstance cannot be restarted given its configuration or current state.
    return ResponseEntity.status(HttpStatus.CONFLICT)
            .body("Cannot restart the JobInstance");
} catch (JobParametersInvalidException ex) {
    // The parameters are invalid according to the Job's validator.
    return ResponseEntity.badRequest()
            .body("Invalid job parameters");
}
~~~

The controller snippet only illustrates how to map the result. In a real application, you should return a response DTO containing the JobExecution ID, the JobInstance, or an appropriate request code, and also log the exception and the correlation ID.

JobExecutionAlreadyRunningException is the signal that an execution of the JobInstance already exists and is running. You should not treat this exception as an unspecified system error. The application can respond that the work is being processed, or query the metadata to display the current execution status if there is enough identifying information.

JobInstanceAlreadyCompleteException, on the other hand, means something different: the logical work has completed. If the user wants to see the result, the application should query the business result or the completed execution. If the user truly wants to run a new business pass, you need to create a new JobInstance with a deliberate business identifier.

## 5. JobLauncher running synchronously and asynchronously

JobLauncher does not necessarily perform the work on the same thread as the request that calls it. How it executes depends on the TaskExecutor configured for the launcher.

### Synchronous execution

With a synchronous executor, for example SyncTaskExecutor, the run() call executes the Job on the calling thread and usually returns only when the Job finishes.

~~~text
HTTP request
    |
    v
JobLauncher.run()
    |
    v
Job executes on the request thread
    |
    v
Job completes
    |
    v
HTTP response
~~~

This approach is simple and suitable for short jobs or test environments. However, the request may have to wait a long time and is prone to timeouts if the Job processes a large amount of data.

### Asynchronous execution

With an asynchronous executor, the launcher creates the JobExecution and hands the work to an execution thread. The run() call can return before the Job completes.

~~~text
HTTP request
    |
    v
JobLauncher.run()
    |
    +----> return JobExecution (STARTING/STARTED)
    |
    v
TaskExecutor
    |
    v
Job executes in the background
    |
    v
COMPLETED or FAILED
~~~

In this case, the HTTP response usually only confirms that the request was accepted. The Job status may still be STARTING or STARTED. The client needs to use the JobExecution ID or a job code to query the status afterward.

Configuring an asynchronous executor does not by itself prevent duplicate launches. The JobInstance check and the coordination of the JobRepository remain the important part so that duplicate requests do not run the same JobInstance together.

## 6. Why do two concurrent requests still need the JobRepository to coordinate?

Suppose two nodes receive the same event almost simultaneously:

~~~text
Node A                         Node B
  |                              |
  | launch Job + parameters      | launch Job + same parameters
  v                              v
JobRepository  <------------> JobRepository
  |                              |
  | create JobExecution          | check JobInstance
  v                              v
STARTED                      Already running
  |                              |
  v                              v
Job runs                     JobExecutionAlreadyRunningException
~~~

If both nodes share a durable JobRepository, the repository can coordinate the creation of JobExecutions for the same JobInstance. The execution-creation operations are protected by transactions and an appropriate isolation level. Spring Batch's default configuration uses a strict isolation level for the execution-creation operation to prevent two processes from both creating a running execution for one JobInstance.

This mechanism only makes sense when the nodes actually share the repository and the metadata database. If each node uses its own repository or a repository that exists only in memory, they cannot see each other's state. In that case, both nodes may believe the JobInstance has not run and process the data together.

For an application deployed with multiple instances, you need to ensure:

- All nodes use the same JobRepository and the same durable metadata store.
- The Spring Batch metadata tables are configured and maintained correctly.
- The repository's transaction manager and transaction isolation are configured appropriately for the database.
- Do not manually modify or delete metadata that is being used to coordinate executions.
- Do not create an independent JobRepository for each node if you want to prevent duplicates at the cluster level.

## 7. Duplicate launches from HTTP, a scheduler, and a message broker

Duplicate launches can originate from many different layers. Identifying the right source helps choose the appropriate protective measure.

### A user clicks a button multiple times or an HTTP retry

A request can be resent when the user clicks a button twice, the browser retries, or the gateway does not receive the response in time. The first request may already have launched the Job even though the client thinks it failed.

How to handle it:

- Use a stable business key as the identifying JobParameters.
- Disable the launch button in the UI while the request is being sent to improve the experience.
- You can use an idempotency key in the API to recognize repeated requests.
- Return a job code or the current status so the client can query instead of unconditionally launching again.

Disabling the button is only a UI aid; it does not protect against retries from a proxy or requests from a different client.

### A scheduler running on multiple nodes

If every application instance runs the same schedule, multiple nodes can issue launch requests at the same time. Using identical JobParameters and a shared JobRepository helps Spring Batch recognize the same JobInstance.

However, if each node adds its own timestamp or new run ID, the runs become different JobInstances. In that case, the mechanism that prevents duplicate executions of the same JobInstance cannot merge them.

You can add a distributed scheduler lock or leader election so that only one node fires the trigger. This is a coordination layer at the scheduler level, useful when you want to avoid even multiple nodes issuing requests, including before the JobRepository performs its check.

### A message broker redelivers a message

A broker can redeliver the same message if the consumer disconnects, times out, or has not acknowledged the message. The consumer should convert the message identifier or the business batch code into identifying JobParameters if each message represents its own unit of work.

Besides the JobRepository, you should have an idempotency mechanism at the consumer layer or in the business database. The fact that a JobInstance runs only once at a time does not by itself guarantee that all external effects, such as sending emails, calling APIs, or publishing messages, will not be repeated on restart.

## 8. How far does the JobRepository protect you?

The JobRepository handles the management of metadata and the execution state of JobInstance/JobExecution. It helps prevent executions from running concurrently for the same JobInstance and applies Spring Batch's restart rules.

It does not by itself solve every form of duplication in the business.

| Situation | Handled by JobRepository? | Mechanism to consider |
|---|---|---|
| Two requests with the same Job and the same identifying parameters, execution running | Yes, with a shared and correctly configured repository | Handle JobExecutionAlreadyRunningException |
| Re-launching the same completed JobInstance | Yes | Display the result or deliberately create a new instance |
| Two requests for the same business work but different identifying parameters | Does not recognize them as the same work | Normalize the business key and parameters |
| Two nodes using separate repositories | Cannot coordinate between nodes | Use a shared, durable repository |
| A Writer sends an email and then restarts | Does not prevent duplicate sending by itself | Idempotency or outbox |
| Two differently named Jobs writing the same dataset | Not considered the same JobInstance | Unique constraint or business lock |
| A scheduler fires repeated triggers with a new run ID | Each one may become a new instance | Scheduler lock and a stable job identifier |

Therefore, you should not regard the JobRepository as a general-purpose business locking system. It coordinates executions by the JobInstance identity that Spring Batch receives.

## 9. Deliberately allowing a new JobInstance to run

There are cases where an operator truly wants to rerun work after a JobInstance has completed, for example regenerating a report with a new business version or handling a separate correction run.

You can add an identifying parameter that represents the new business run:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("reportVersion", "revision-2", true)
        .toJobParameters();
~~~

Because reportVersion is identifying, this parameter set creates a JobInstance different from the run with reportVersion=revision-1.

Spring Batch also has the JobParametersIncrementer mechanism, typically used with RunIdIncrementer, to create the next parameter set. For example:

~~~java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .incrementer(new RunIdIncrementer())
            .start(importOrdersStep)
            .build();
}
~~~

An incrementer is appropriate when the business truly needs successive JobInstances. You should not automatically add a new run ID to every request if the goal is to eliminate duplicate launches. Each different run ID makes the JobRepository regard it as a different JobInstance.

If you need to restart a failed JobInstance, you must use exactly the identifying parameters of that instance. Do not add a new run ID just to "retry", because that may start a new instance from scratch and skip the checkpoint of the previous run.

## 10. Checking the status of a running Job

When a request is rejected because the JobInstance is running, the application may need to provide the current status to the user or the calling system.

JobExplorer is the API for reading Spring Batch metadata. For example, you can find the running executions by Job name:

~~~java
@Service
public class BatchStatusQueryService {

    private final JobExplorer jobExplorer;

    public BatchStatusQueryService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public Set<JobExecution> findRunningExecutions(String jobName) {
        return jobExplorer.findRunningJobExecutions(jobName);
    }
}
~~~

The result is the set of running JobExecutions of the Job with the given name. If the Job has multiple JobInstances, you need to compare the identifying JobParameters to find the execution for the right business unit. You should not just take the first execution in the result set and treat it as the current request.

A status response can contain:

- JobExecution ID.
- JobInstance ID.
- Job name.
- BatchStatus and ExitStatus.
- Start time, end time, and the most recent update time if available.
- The running Step and important progress counters.

JobExplorer serves metadata queries. It does not replace JobLauncher and should not be used to directly modify the execution state.

## 11. Distinguishing duplicate launch, restart, and rerun

These three operations are often confused:

**Duplicate launch:** Another request tries to launch the same JobInstance while the current execution is running. Spring Batch rejects the duplicate request with JobExecutionAlreadyRunningException.

**Restart:** A JobInstance whose previous execution failed or was stopped is launched again with the same identifying parameters. Spring Batch creates a new JobExecution and recovers from the metadata/checkpoint according to the configuration.

**Rerun:** The business wants to perform a new pass of the logical work. You need to create a new JobInstance with a new identifying parameter that has business meaning, or an incrementer used deliberately.

For example:

~~~text
businessDate=2026-11-15, sourceFileId=file-8421

JobExecution 101: STARTED
  -> duplicate request: JobExecutionAlreadyRunningException

JobExecution 101: FAILED
  -> call again with the same parameters: restart the JobInstance
  -> JobExecution 108

JobExecution 108: COMPLETED
  -> call again with the same parameters: JobInstanceAlreadyCompleteException

reportVersion=revision-2
  -> new JobInstance, can run a new business pass
~~~

Choosing the right operation is very important. A duplicate launch needs to be answered with "the work already exists"; a restart needs to keep the identity and checkpoint; a rerun needs a new business identifier so the execution history is not ambiguous.

## 12. Checklist for designing duplicate-launch protection

When deploying JobLauncher in a real application, consider the following points:

1. Determine the business key for a unit of work, for example the file ID, business date, or batch ID.
2. Put the business key into the identifying JobParameters.
3. Keep the request ID, correlation ID, and trace information as non-identifying if they do not change the unit of work.
4. Do not create a new timestamp or run ID for every request when you need to recognize repeated requests.
5. Use a durable JobRepository shared among the application nodes.
6. Handle JobExecutionAlreadyRunningException, JobInstanceAlreadyCompleteException, JobRestartException, and JobParametersInvalidException explicitly.
7. Distinguish confirming that the request was accepted from confirming that the Job has completed, especially when the launcher runs asynchronously.
8. Protect business effects outside the transaction with idempotency, a unique constraint, or an outbox.
9. If the scheduler runs on multiple nodes, consider a distributed lock or a mechanism that designates the node that fires the trigger.
10. Provide an API to look up the JobExecution so users know whether the work is running, completed, or failed.

A safe launch system needs to combine stable JobInstance identity, a shared JobRepository, correct exception handling, and idempotency at the business layer. That way, repeated requests can be recognized, restarts are performed correctly, and a new processing pass is created only when there is clear intent.

