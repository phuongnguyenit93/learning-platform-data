# Monitoring Results from JobLauncher

In Spring Batch, the **JobLauncher** is the component that receives a request to run a Job. When you call the **run()** method, the application receives a **JobExecution** representing the execution that was just requested. From this object, you can see the Job status, the result code, the run times, the Steps that were executed, and processing metrics.

How you monitor depends on how the JobLauncher executes the Job:

- With a synchronous launcher, the run() call usually returns only after the Job finishes. You can read the final result right from the returned JobExecution.
- With an asynchronous launcher, run() can return while the Job is still running. You need to store the execution ID and query the latest status through JobExplorer, or receive a notification when the Job finishes.

Do not treat run() returning as proof that the Job has completed. Read the JobExecution status and understand whether the launcher runs synchronously or asynchronously.

## 1. JobLauncher returns a JobExecution

JobLauncher does not return a boolean value indicating success or failure. It returns a JobExecution, an object containing the information of one Job run.

An example of a service that launches a customer import Job:

~~~java
@Service
public class CustomerImportService {

    private final JobLauncher jobLauncher;
    private final Job customerImportJob;

    public CustomerImportService(
            JobLauncher jobLauncher,
            Job customerImportJob) {
        this.jobLauncher = jobLauncher;
        this.customerImportJob = customerImportJob;
    }

    public JobExecution launch(String inputFile)
            throws JobExecutionException {

        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", inputFile, true)
                .toJobParameters();

        return jobLauncher.run(customerImportJob, parameters);
    }
}
~~~

In the example:

1. The application creates JobParameters containing the file path.
2. JobLauncher receives the Job together with the parameter set.
3. Spring Batch checks the JobInstance and the launch conditions.
4. If the request is valid, the framework creates a JobExecution for the run.
5. The JobExecution is returned to the caller.

Each attempt to run a Job has its own JobExecution ID. When restarting a JobInstance, Spring Batch creates a new JobExecution belonging to the same JobInstance. Therefore, when storing history or monitoring a specific run, store the **JobExecution ID**, not just the Job name.

## 2. Information to read from a JobExecution

A JobExecution contains the following important information:

| Property | Meaning |
|---|---|
| id | The ID of the Job execution |
| jobInstance | The JobInstance the execution belongs to |
| status | The execution status at the framework level |
| exitStatus | The exit result of the Job |
| createTime | The time the JobExecution was created |
| startTime | The time execution started |
| endTime | The time it ended |
| lastUpdated | The time the metadata was most recently updated |
| executionContext | The Job-level state |
| stepExecutions | The collection of Step executions |
| failureExceptions | The exceptions held on the current execution object |

An example of reading the information:

~~~java
JobExecution execution = jobLauncher.run(job, parameters);

Long executionId = execution.getId();
BatchStatus status = execution.getStatus();
ExitStatus exitStatus = execution.getExitStatus();

System.out.println("Execution ID: " + executionId);
System.out.println("Status: " + status);
System.out.println("Exit code: " + exitStatus.getExitCode());
System.out.println("Exit description: " + exitStatus.getExitDescription());
~~~

These values answer different questions:

- **ID** tells you which run to query.
- **BatchStatus** tells you whether the framework is running, completed, failed, or stopped.
- **ExitStatus** tells you the result code that the Job emits.
- **Time** helps measure the duration and determine the most recent update.
- **StepExecutions** help find the specific stage that caused an error or processed less data than expected.

## 3. Distinguishing BatchStatus and ExitStatus

These are two pieces of information that need to be viewed together when monitoring the result.

**BatchStatus** represents the execution state of a Job or Step. Common values include:

| BatchStatus | Meaning |
|---|---|
| STARTING | Preparing to start |
| STARTED | Executing |
| STOPPING | A stop has been requested |
| STOPPED | Stopped as requested |
| COMPLETED | Completed according to the framework state |
| FAILED | Execution failed |
| ABANDONED | The execution has been marked as not to be restarted |
| UNKNOWN | A reliable status cannot be determined |

**ExitStatus** describes the exit result. It has an exit code and may have an exit description. The default codes usually include COMPLETED, FAILED, and EXECUTING; the application can also use its own codes such as NO_DATA or COMPLETED_WITH_WARNINGS.

For example:

~~~java
BatchStatus status = execution.getStatus();
ExitStatus exitStatus = execution.getExitStatus();

if (status == BatchStatus.COMPLETED) {
    System.out.println("The Job completed at the framework level.");
}

if ("NO_DATA".equals(exitStatus.getExitCode())) {
    System.out.println("The Job completed but there was no data to process.");
}
~~~

A Job can have a BatchStatus of COMPLETED but an ExitStatus carrying a custom business code. That allows the application to distinguish a Job that ran successfully from a technical standpoint from different business outcomes.

Conversely, a BatchStatus of FAILED indicates that the Job failed at the framework level. When you encounter this case, look at the ExitStatus and the logs to understand the cause.

In a flow, transitions are declared with on(), which matches the exit code of the ExitStatus. Therefore, if a flow branch does not run as expected, look at the ExitStatus of the Step and Job instead of looking only at BatchStatus.

## 4. Monitoring the result of each Step

A JobExecution contains the StepExecutions belonging to that run. Each StepExecution represents one specific execution of a Step and provides the status, timing, read/write metrics, and error information.

An example of iterating over the Steps:

~~~java
for (StepExecution stepExecution : execution.getStepExecutions()) {
    System.out.println("Step: " + stepExecution.getStepName());
    System.out.println("Status: " + stepExecution.getStatus());
    System.out.println(
            "Exit code: " + stepExecution.getExitStatus().getExitCode());

    System.out.println("Read: " + stepExecution.getReadCount());
    System.out.println("Write: " + stepExecution.getWriteCount());
    System.out.println("Filter: " + stepExecution.getFilterCount());
    System.out.println("Commit: " + stepExecution.getCommitCount());
    System.out.println("Rollback: " + stepExecution.getRollbackCount());
}
~~~

Commonly used metrics:

| Metric | How to interpret it |
|---|---|
| readCount | Number of items read |
| writeCount | Number of items written |
| filterCount | Number of items filtered by the processor |
| readSkipCount | Number of items skipped in the read phase |
| processSkipCount | Number of items skipped in the process phase |
| writeSkipCount | Number of items skipped in the write phase |
| commitCount | Number of transactions committed |
| rollbackCount | Number of transactions rolled back |
| startTime / endTime | The start and end time of the Step |

These metrics help determine which Step processes slowly, has many filtered records, or encounters many rollbacks.

You should not assume readCount always equals writeCount. A processor can return null to filter an item, a writer can write in batches, and a skip policy can skip failed items. When reconciling the numbers, look at the skip counts, the filter count, and the application's logs as well.

## 5. Monitoring when JobLauncher runs synchronously

When the JobLauncher uses a synchronous execution mechanism, the run() call waits for the Job to finish before returning control to the caller.

Processing flow:

~~~text
Application
   |
   v
JobLauncher.run()
   |
   v
Job executes the Steps
   |
   v
Job finishes
   |
   v
Return JobExecution
   |
   v
Read the final status and exitStatus
~~~

For example:

~~~java
JobExecution execution = jobLauncher.run(job, parameters);

if (execution.getStatus() == BatchStatus.COMPLETED) {
    // Handle the completed result.
} else if (execution.getStatus() == BatchStatus.FAILED) {
    // Record the error and handle it according to the application's policy.
}
~~~

This is a simple approach when the Job is short and the application can wait for the result. The caller can return the final result to the user or perform the next step after the Job finishes.

However, a long Job can make an HTTP request or the application's processing thread wait a long time. For tasks that run for minutes or hours, consider launching asynchronously and providing a separate status-query mechanism.

## 6. Monitoring when JobLauncher runs asynchronously

A JobLauncher can be configured with a TaskExecutor to run the Job on another thread. In that case, run() can return the JobExecution while the Job is still STARTING or STARTED.

Processing flow:

~~~text
Application
   |
   v
JobLauncher.run()
   |
   +----> Send the work to the TaskExecutor
   |                |
   |                v
   |           Job runs in the background
   |
   v
Return the initial JobExecution
   |
   v
Store the execution ID
   |
   v
Query the new status through JobExplorer
   |
   v
Job COMPLETED / FAILED / STOPPED
~~~

For example, right after run() returns:

~~~java
JobExecution execution = jobLauncher.run(job, parameters);

Long executionId = execution.getId();

System.out.println("Execution ID: " + executionId);
System.out.println("Current status: " + execution.getStatus());
~~~

If the launcher runs asynchronously, the status at this point may not be the final status. You should not rely on the initial JobExecution object to conclude that the Job has completed. Query the latest metadata again using the execution ID.

How to configure the specific executor depends on the application's Batch infrastructure configuration. The point to remember is that synchronous or asynchronous mode is determined by the TaskExecutor that the JobLauncher uses.

## 7. JobExplorer: querying the latest status

**JobExplorer** provides a read-only API to query execution information from the JobRepository. It is a suitable choice for monitoring asynchronous Jobs, displaying run history, or building a status endpoint.

An example of querying a JobExecution by ID:

~~~java
@Service
public class JobMonitoringService {

    private final JobExplorer jobExplorer;

    public JobMonitoringService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public JobExecution findExecution(Long executionId) {
        return jobExplorer.getJobExecution(executionId);
    }
}
~~~

When you obtain the latest JobExecution, you can read the status and the Steps:

~~~java
JobExecution latest = jobExplorer.getJobExecution(executionId);

if (latest == null) {
    throw new IllegalArgumentException(
            "JobExecution not found: " + executionId);
}

System.out.println("Status: " + latest.getStatus());
System.out.println("Exit code: " + latest.getExitStatus().getExitCode());

for (StepExecution step : latest.getStepExecutions()) {
    System.out.println(
            step.getStepName() + ": " + step.getStatus());
}
~~~

JobExplorer queries the metadata stored in the repository. When using it to monitor progress, make sure the JobRepository and JobExplorer access the same metadata store.

With an asynchronous launcher, a common implementation approach is:

1. Launch the Job.
2. Get the execution ID from the returned JobExecution.
3. Store the ID along with the business request information.
4. Use JobExplorer to query the latest status when needed.
5. Stop polling when the Job reaches a terminal status.

You should not query continuously at too high a frequency. Use a reasonable polling schedule, limit the monitoring time, and avoid holding an HTTP request open for the entire time the Job runs.

### Finding running Jobs

JobExplorer can also help find running JobExecutions by Job name:

~~~java
Set<JobExecution> running =
        jobExplorer.findRunningJobExecutions("customerImportJob");

for (JobExecution execution : running) {
    System.out.println(
            execution.getId() + " - " + execution.getStatus());
}
~~~

This is useful when building an operations page to display active Jobs. If a Job has multiple JobInstances or multiple restarts, distinguish each JobExecution by its ID.

## 8. JobExecutionListener: receiving the result when the Job finishes

If the application needs to perform an action after the Job finishes, you can use a **JobExecutionListener**.

The listener has two main callbacks:

- beforeJob(): called before the Job executes.
- afterJob(): called after the Job finishes, regardless of whether the result is success or failure.

For example:

~~~java
@Component
public class CustomerImportListener implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(CustomerImportListener.class);

    @Override
    public void beforeJob(JobExecution jobExecution) {
        log.info(
                "Starting JobExecution id={}",
                jobExecution.getId());
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        log.info(
                "Finished JobExecution id={}, status={}, exitCode={}",
                jobExecution.getId(),
                jobExecution.getStatus(),
                jobExecution.getExitStatus().getExitCode());

        if (jobExecution.getStatus() == BatchStatus.COMPLETED) {
            log.info("Customer import completed.");
        } else if (jobExecution.getStatus() == BatchStatus.FAILED) {
            log.error("Customer import failed.");
        }
    }
}
~~~

Register the listener in the Job:

~~~java
@Bean
public Job customerImportJob(
        JobRepository jobRepository,
        Step importCustomersStep,
        CustomerImportListener listener) {

    return new JobBuilder("customerImportJob", jobRepository)
            .start(importCustomersStep)
            .listener(listener)
            .build();
}
~~~

A listener is suitable for logging, updating business status, or publishing a completion event. Because the listener runs within the Job execution process, it also works when the Job is launched asynchronously.

If you send notifications to an external system, consider the possibility of duplicate sending when the Job restarts or the listener is called again. For events that need guaranteed reliability, use a durable event-storage mechanism such as an outbox and idempotent handling on the receiving side.

## 9. Building a Job monitoring endpoint

A web application can return the execution ID right after launching the Job. The client uses this ID to query the status through another endpoint.

An example response at start:

~~~json
{
  "executionId": 125,
  "status": "STARTED",
  "message": "The Job has been accepted"
}
~~~

The monitoring endpoint can return:

~~~json
{
  "executionId": 125,
  "jobName": "customerImportJob",
  "status": "COMPLETED",
  "exitCode": "COMPLETED",
  "startTime": "2026-11-15T10:00:00",
  "endTime": "2026-11-15T10:00:12",
  "steps": [
    {
      "name": "importCustomersStep",
      "status": "COMPLETED",
      "readCount": 1000,
      "writeCount": 980,
      "filterCount": 20
    }
  ]
}
~~~

This is an illustrative response structure designed by the application, not a fixed JSON that Spring Batch returns by itself.

An API design typically has two operations:

- POST /jobs/customer-import: receives the request and returns the execution ID.
- GET /jobs/executions/{id}: queries the latest status and metrics.

When building the endpoint, return only the fields that the user or calling system needs. You should not return the entire ExecutionContext because it may contain internal information or sensitive business data.

If the Job runs synchronously and the request waits until the Job finishes, the POST endpoint can return the final result. If the Job runs asynchronously, returning the execution ID helps the client track progress without keeping a connection open.

## 10. Monitoring history and restarts

A Job can have multiple JobInstances. A JobInstance can have multiple JobExecutions if a previous run failed or was stopped and then restarted.

For example:

~~~text
customerImportJob
   |
   +-- JobInstance A (file=customers-01.csv)
   |       |
   |       +-- JobExecution 101: FAILED
   |       +-- JobExecution 105: COMPLETED
   |
   +-- JobInstance B (file=customers-02.csv)
           |
           +-- JobExecution 110: COMPLETED
~~~

When displaying history, you need to distinguish:

- **JobInstance ID**: identifies one logical run by Job name and identifying parameters.
- **JobExecution ID**: identifies one specific execution.
- **JobExecution status**: the result of that execution.

If you store only the JobInstance ID, you will not know what the result of the most recent restart was. If you store only the Job name, you cannot distinguish the different runs.

JobExplorer provides operations to read history by Job name, JobInstance, and JobExecution. You can use them to build a list of runs, the details of each run, and the corresponding Steps.

## 11. JobLauncher exceptions differ from a FAILED JobExecution

Not every error when calling JobLauncher.run() produces a failed JobExecution.

In some cases the launch request is rejected right from the start:

| Exception | Common cause |
|---|---|
| JobExecutionAlreadyRunningException | A JobInstance with the same identifying parameters is running |
| JobInstanceAlreadyCompleteException | That JobInstance has already completed and cannot be run again as a new run |
| JobRestartException | The JobInstance cannot be restarted given its current state or configuration |
| JobParametersInvalidException | The JobParameters set is invalid |
| TaskRejectedException | The executor refuses to accept the work, if the launcher runs asynchronously |

An example of catching errors at launch:

~~~java
public Long launch(Job job, JobParameters parameters)
        throws JobExecutionException {
    try {
        JobExecution execution = jobLauncher.run(job, parameters);
        return execution.getId();
    } catch (JobExecutionAlreadyRunningException ex) {
        // The corresponding request is already being executed.
        throw ex;
    } catch (JobInstanceAlreadyCompleteException ex) {
        // The JobInstance has completed with these identifying parameters.
        throw ex;
    } catch (JobRestartException ex) {
        // The JobInstance cannot be restarted.
        throw ex;
    } catch (JobParametersInvalidException ex) {
        // The input parameters are invalid.
        throw ex;
    }
~~~

In real code, you can catch a common group of exceptions according to the application's policy. The important thing is to distinguish a launch error from a JobExecution that was created and then ended in the FAILED state.

If run() throws an exception before returning a JobExecution, the caller may not have an execution ID to query. Log the request, the Job name, and the appropriate identifying parameters for investigation, while avoiding logging sensitive data.

## 12. Diagnosing unexpected Job results

When an operator reports that a Job "finished running but there is no data" or "I can't see the result", look at the following information in turn:

| Symptom | Where to check |
|---|---|
| No JobExecution received | The exception when calling JobLauncher, the launcher and executor configuration |
| Job is still STARTED | The executor, the worker process, JobExplorer, and the most recently updated metadata |
| Job has status FAILED | ExitStatus, failure description, StepExecution, and the application log |
| Job COMPLETED but output is empty | Custom ExitStatus, readCount, writeCount, filterCount, and the source data |
| A Step does not appear | The flow transitions, whether the Step was selected to run |
| Read and write counts differ | Processor filter, skip count, and the writer logic |
| Dashboard shows an old status | Using an old JobExecution object instead of re-querying JobExplorer |
| Execution ID not found | Wrong ID, a different JobRepository, or the metadata has been cleaned up |

For errors that occur inside a Step, check the specific StepExecution instead of looking only at the Job status. The ExitDescription can provide additional information, but the full stack trace is usually in the application log. Do not assume that every Throwable held in a Java object is stored and restored intact from the database metadata.

With an asynchronous launcher, if the status does not change for a long time, check the worker thread, the TaskExecutor, the process logs, and the JobRepository. A JobExplorer query does not make the Job continue running by itself; it only reads the status that has been stored.

## 13. Designing an operable monitoring mechanism

A good monitoring mechanism should provide enough information to answer which Job is running, for which business request, how far it has processed, and how it ended.

Some principles:

- Store the JobExecution ID right after the JobLauncher accepts the request.
- Link the execution ID to the business request code so operators can search easily.
- Use JobExplorer to query the latest status when running asynchronously.
- Display both BatchStatus and ExitStatus.
- Display the status, time, and metrics of each Step.
- Log with the execution ID to correlate events between components.
- Keep the JobExecution history long enough for investigation and reconciliation.
- Set a reasonable polling frequency, with a maximum wait time, and handle the case where the execution is not found.
- Distinguish launch errors from errors during execution.
- Design completion callbacks or events that can prevent duplicate sending.

If the system needs to stop or restart a Job from an operations interface, look into JobOperator for control operations. JobExplorer is suitable for reading status and history; it is not an API for changing the execution state.

## 14. A complete monitoring workflow

A typical flow in a data-import application can be organized as follows:

~~~text
User submits a file import request
              |
              v
       Application creates JobParameters
              |
              v
         JobLauncher.run()
              |
              v
         Receive JobExecution
              |
              +---- Store execution ID
              |
              v
        Return ID to client
              |
              v
        Client asks for status
              |
              v
       JobExplorer.getJobExecution(id)
              |
              v
       Read Job and Step status
              |
       +------+------+
       |             |
       v             v
    Running       Finished
       |             |
       v             v
    Continue      Display exit code,
    monitoring    metrics, and result
~~~

When the JobLauncher runs synchronously, the application can read the final result right after run(). When the launcher runs asynchronously, the execution ID is the key to querying the latest status through JobExplorer. In both cases, the JobExecution and the StepExecutions are the main sources of information for understanding how the run went.

Always look at **BatchStatus**, **ExitStatus**, and the metrics of each Step together. A Job is considered to meet the business requirement only when the technical status, the result code, and the output data all match the processing goal.
