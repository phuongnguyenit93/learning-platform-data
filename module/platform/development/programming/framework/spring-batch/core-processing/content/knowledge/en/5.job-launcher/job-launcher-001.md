# JobLauncher Launches a JobExecution

In Spring Batch, a `Job` describes a batch process, while a `JobExecution` represents one specific execution of that process. The component that receives the request to run a job and starts the execution is the `JobLauncher`.

A `JobLauncher` is usually called from an application service, a scheduler, a REST endpoint, or another orchestrating component. It receives a `Job` together with `JobParameters`, works with the `JobRepository` to create the execution information, and then asks the job to run. The result is returned as a `JobExecution` object containing metadata about that run.

To understand the role of the JobLauncher correctly, you need to distinguish **launching** from **defining and carrying out business logic**. The JobLauncher does not decide which steps a job must perform, and it does not read or write business data. Those responsibilities belong to the `Job`, its `Step`s, and the reader, processor, writer, or tasklet components.

## 1. Where does JobLauncher sit in the architecture?

A basic launch flow can be pictured as follows:

```text
User / REST API / Scheduler / Application
                     |
                     v
                JobLauncher
                     |
                     v
          JobRepository creates execution
                     |
                     v
                    Job
                     |
              +------+------+
              |             |
              v             v
            Step 1        Step 2
              |             |
              +------+------+
                     |
                     v
              JobExecution
              (status and result)
```

The related components have different responsibilities:

| Component | Role |
|---|---|
| `Job` | Defines the batch process and its steps. |
| `JobLauncher` | Receives a request to run a job with a specific set of parameters and starts the execution. |
| `JobRepository` | Stores metadata about JobInstance, JobExecution, StepExecution, and ExecutionContext. |
| `JobParameters` | Provides input data for the run and identifies the JobInstance through identifying parameters. |
| `JobExecution` | Represents one specific execution, storing its status, timing, ExitStatus, and error information. |
| `Step` | Performs one phase of the job. |

Typically, the application injects the `JobLauncher` and the `Job` bean into a service or orchestrating component. The JobLauncher uses the JobRepository to register the execution before calling the job to run.

## 2. JobInstance and JobExecution at launch time

Two calls to the JobLauncher can create executions that belong to the same JobInstance or to two different JobInstances. This depends on the job name and the identifying `JobParameters`.

For example, the job `importOrdersJob` processes orders by business date:

```text
Job: importOrdersJob

JobParameters:
  businessDate = 2026-11-15 (identifying)
  inputFile    = orders.csv (identifying)

                |
                v
JobInstance: importOrdersJob / 2026-11-15 / orders.csv
                |
                +-- JobExecution #1
                +-- JobExecution #2 (if restart is allowed)
```

A `JobInstance` identifies a logical unit of processing. A `JobExecution` records each specific execution. When a run fails and is restarted with the same identifying parameters, Spring Batch creates a new JobExecution belonging to the same JobInstance.

If you change an identifying parameter, such as the business date, the JobLauncher will work with a different JobInstance. Therefore, the way you build parameters directly affects whether a run is new or a restart.

## 3. Calling JobLauncher to run a Job

The main API of `JobLauncher` is:

```java
JobExecution run(Job job, JobParameters jobParameters)
```

The method takes two arguments:

- `job`: the Job bean configured in the Spring application context.
- `jobParameters`: the set of input parameters for the run.

An example of creating parameters and launching a job:

```java
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

    public JobExecution launch(String inputFile, String businessDate)
            throws Exception {

        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", inputFile, true)
                .addString("businessDate", businessDate, true)
                .toJobParameters();

        return jobLauncher.run(importOrdersJob, parameters);
    }
}
```

In the example, `inputFile` and `businessDate` are marked as identifying. These two values, together with the job name, identify the JobInstance. The service does not perform the import steps itself; it only prepares the parameters and hands the execution request to the JobLauncher.

The `JobLauncher` and `importOrdersJob` beans must be configured in the application context. With Spring Boot, Spring Batch auto-configuration can provide the infrastructure components if the application has the appropriate dependencies and configuration. In an application that configures Spring Batch directly, you need to declare the JobRepository and the corresponding launcher.

## 4. What happens inside a run() call?

At a conceptual level, the launch process goes through the following steps:

1. The caller passes the `Job` and `JobParameters` to `JobLauncher.run`.
2. The JobLauncher works with the `JobRepository` to create or find the corresponding `JobInstance` and register a new `JobExecution`.
3. Spring Batch checks the execution conditions, including the validity of the parameters and whether the instance can be run or restarted given its current state.
4. The job is executed with the newly created JobExecution.
5. The job orchestrates the steps. Each step updates its own metadata and execution status through the JobRepository.
6. When the job finishes, the JobExecution reflects the status and result of the run.

The detailed sequence of validation, metadata registration, and execution may depend on the implementation and the Spring Batch version. The key point is that the JobLauncher works with the JobRepository to manage the run, while the Job and Step contain the processing logic.

The JobLauncher does not create a new JobInstance for every call. It relies on the job name and identifying parameters, and also respects the persisted state. For example, an instance that is currently running may be rejected when you try to launch an additional execution; a completed instance also usually cannot be run again with the same parameters as a new run.

## 5. What information does the returned JobExecution contain?

`JobLauncher.run` returns a `JobExecution`. This object represents the execution that the launcher registered. It provides important information that the application can use to monitor and respond to the result.

| Information | Meaning |
|---|---|
| `id` | The identifier of the JobExecution in the metadata repository. |
| `jobInstance` | The JobInstance this execution belongs to. |
| `jobParameters` | The set of parameters used to launch the run. |
| `status` | The execution status, such as `STARTING`, `STARTED`, `COMPLETED`, `FAILED`, or `STOPPED`. |
| `startTime` | The time the execution started. |
| `endTime` | The time the execution ended, if it has ended. |
| `exitStatus` | The exit result, which may contain a custom code and a description. |
| `stepExecutions` | The collection of StepExecutions belonging to this execution. |
| `executionContext` | Key-value state at the job execution scope. |
| `failureExceptions` | The exceptions recorded during execution. |

An example of reading some of this information after calling the launcher:

```java
JobExecution execution = jobLauncher.run(job, parameters);

System.out.println("Execution ID: " + execution.getId());
System.out.println("Job status: " + execution.getStatus());
System.out.println("Exit status: " + execution.getExitStatus());
System.out.println("Start time: " + execution.getStartTime());
System.out.println("End time: " + execution.getEndTime());
```

If the launcher runs synchronously, when `run` returns the job has usually finished and the status information reflects the final result. If the launcher runs asynchronously, `run` may return when the job has just started or is still running. In that case, you must not treat the initial state of the returned object as the final result.

## 6. Synchronous and asynchronous execution

A `JobLauncher` can execute a job on the calling thread or hand the work to another executor. This difference affects how the application waits for the result and responds to the user.

### Synchronous execution

With synchronous execution, the thread that calls `run` waits for the job to finish before it receives the result. This approach is easy to understand and convenient for short jobs or scheduled batch programs that do not need to answer a request immediately.

```text
Calling thread
    |
    +---- JobLauncher.run() ----------------------+
    |                                             |
    |                                      Job executes
    |                                             |
    +<----------- JobExecution completed ---------+
    |
    v
Handle the final result
```

The advantage is that the caller can read the final status immediately after `run` returns. The disadvantage is that the calling thread has to wait for the whole time the job runs. If it is called from an HTTP request and the job is long-running, the request may hold a thread for a long time or exceed the gateway timeout.

### Asynchronous execution

With asynchronous execution, the launcher uses a `TaskExecutor` to execute the job on another thread. The `run` method may return the JobExecution before the steps complete.

```text
Calling thread                         Worker thread
     |                                      |
     +-- JobLauncher.run() ---------------->|
     |                                      +-- run Job
     |                                      +-- run Steps
     |<-- JobExecution in progress          |
     |                                      +-- update metadata
     v                                      +-- finish Job
Return execution ID
```

In this case, the caller should store or return the execution ID so that the user can look up the status later. You should not read `execution.getStatus()` immediately and then conclude that the job succeeded if the job is still running.

Spring Batch provides `TaskExecutorJobLauncher` to configure a launcher that uses a `TaskExecutor`. In a Spring Boot application, the launcher can be auto-configured; if you need asynchronous behavior or your own executor, configure it according to the Spring Batch and Spring Boot versions you are using.

An example of configuring a launcher with an executor:

```java
@Bean
TaskExecutorJobLauncher jobLauncher(
        JobRepository jobRepository,
        TaskExecutor taskExecutor) throws Exception {

    TaskExecutorJobLauncher launcher = new TaskExecutorJobLauncher();
    launcher.setJobRepository(jobRepository);
    launcher.setTaskExecutor(taskExecutor);
    launcher.afterPropertiesSet();
    return launcher;
}
```

The `taskExecutor` bean needs to be configured separately. In a production environment, you should choose an executor with an appropriately bounded number of threads and queue size, and also manage its lifecycle and shutdown capability. You should not default to creating unlimited threads when users can submit many launch requests at the same time.

## 7. Handling the launch result and common exceptions

The `run` method can throw exceptions indicating that the launch request could not be accepted:

| Exception | Common cause |
|---|---|
| `JobExecutionAlreadyRunningException` | The corresponding JobInstance already has an active execution. |
| `JobInstanceAlreadyCompleteException` | The JobInstance has already completed and cannot be run again in the usual way with the same identifying parameters. |
| `JobRestartException` | The instance or execution cannot be restarted given the current state and configuration. |
| `JobParametersInvalidException` | The parameter set is invalid according to the job's validation rules. |

An example of handling these in the orchestration layer:

```java
public JobExecution launchImport(Job job, JobParameters parameters) {
    try {
        return jobLauncher.run(job, parameters);
    } catch (JobExecutionAlreadyRunningException ex) {
        throw new IllegalStateException(
                "Job instance is already running", ex);
    } catch (JobInstanceAlreadyCompleteException ex) {
        throw new IllegalStateException(
                "Job instance has already completed", ex);
    } catch (JobRestartException ex) {
        throw new IllegalStateException(
                "Job instance cannot be restarted", ex);
    } catch (JobParametersInvalidException ex) {
        throw new IllegalArgumentException(
                "Invalid job parameters", ex);
    }
}
```

In a real application, you can map these cases to API response codes or messages appropriate for the calling system. You should not collapse all exceptions into a single "job failed" message, because some errors occur right at the request-acceptance stage, before the job can run any business logic.

Besides launch exceptions, a job can be launched successfully but later end with `BatchStatus.FAILED`. These are two different kinds of outcomes:

- **Failed to launch:** the launcher cannot accept the request, for example because the instance is already running or the parameters are invalid.
- **Launched but execution failed:** the JobExecution has been created and the job has run, but a step or logic within the job raised an error.

For the second case, read the JobExecution status, StepExecution, ExitStatus, and failure exceptions to find the cause.

## 8. JobLauncher is not a scheduler and not a JobOperator

Batch orchestration components can have similar names but different roles:

| Component | Responsibility |
|---|---|
| `JobLauncher` | Launches a Job with JobParameters. |
| Scheduler (for example Spring Scheduling or Quartz) | Decides when to send a request to run a job. |
| `JobExplorer` | Looks up the metadata and status of stored job executions. |
| `JobOperator` | Provides higher-level operational APIs such as start, restart, stop, or looking up executions, depending on the version's capabilities. |
| `JobRepository` | Stores execution metadata so the framework can manage and recover state. |

For example, a scheduler can call a service at midnight. The service prepares the JobParameters and calls the JobLauncher. The scheduler is responsible for when the job runs; the JobLauncher is responsible for accepting and starting the execution.

If the application needs an administration interface to find failed executions and then restart or stop jobs, `JobOperator` and `JobExplorer` may be a better fit. You should not use the JobLauncher as a scheduler or as a full administration API.

## 9. Launching from a REST API

An application can provide an endpoint for users to request a batch run. The endpoint should validate input, create parameters that have business meaning, and return a result appropriate to the synchronous or asynchronous mode.

An illustrative example of a launch endpoint:

```java
@RestController
@RequestMapping("/batch")
public class BatchController {

    private final OrderImportService orderImportService;

    public BatchController(OrderImportService orderImportService) {
        this.orderImportService = orderImportService;
    }

    @PostMapping("/orders")
    public ResponseEntity<Map<String, Object>> importOrders(
            @RequestParam String inputFile,
            @RequestParam String businessDate) throws Exception {

        JobExecution execution = orderImportService.launch(
                inputFile, businessDate);

        Map<String, Object> body = Map.of(
                "executionId", execution.getId(),
                "status", execution.getStatus().toString());

        return ResponseEntity.accepted().body(body);
    }
}
```

This is a simple example of how to connect an HTTP request to the launch service. In a real application, you need to check access permissions, validate file paths, control which job types are allowed to run, and handle exceptions at the web layer.

If the launcher is asynchronous, a `202 Accepted` response together with the execution ID is usually more appropriate than waiting for the job to complete within the request. The application can provide a separate status endpoint that uses `JobExplorer` to look up the execution from the repository. If the launcher is synchronous, returning only `202` does not mean the job is running asynchronously; the HTTP code should reflect the actual contract of the API.

You should not allow clients to pass arbitrary class names, bean names, or system paths to select a job. Use a set of jobs that the application allows, and validate all input parameters.

## 10. JobParameters and avoiding duplicate launches

The JobLauncher works with the JobRepository to protect the identity and state of the JobInstance. Therefore, the design of JobParameters needs to be tied to business meaning.

For example:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("sourceSystem", "ERP", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
```

In this case, the business date and the source system identify the unit of data to be processed. `requestedBy` is only additional information and does not change the JobInstance.

Some common design mistakes:

- Adding a timestamp or UUID as an identifying parameter on every call, which makes every request a new JobInstance and loses the ability to identify the instance that needs to be restarted.
- Using the same identifying parameters for two different business runs, causing the later run to hit an already-completed or already-running instance error.
- Using a default value that does not reflect the business period, causing different requests to unintentionally share the same JobInstance.
- Not validating file paths, processing dates, or data ranges before launching.

If the business needs to create a new run for the same kind of job, design identifying parameters that clearly express the new unit of processing. If the goal is a restart, use exactly the identifying parameters of the old instance.

## 11. Monitoring the execution after the launcher returns

For long-running jobs or an asynchronous launcher, the caller should not keep the `JobExecution` object in memory as the only source of status. The metadata in the JobRepository is the durable store for looking up status.

`JobExplorer` can be used to find an execution by ID and read the latest status:

```java
@Service
public class JobStatusService {

    private final JobExplorer jobExplorer;

    public JobStatusService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public JobExecution findExecution(long executionId) {
        return jobExplorer.getJobExecution(executionId);
    }
}
```

When returning status to a client, you should provide appropriate information such as the execution ID, job name, BatchStatus, ExitStatus, start/end times, and error information that is permitted to be shown. Avoid returning stack traces or sensitive data from exceptions to a public API.

The application can also register a `JobExecutionListener` to log the start and end times, send metrics, or publish internal events. A listener helps observe the job lifecycle, while the JobRepository keeps the execution metadata.

## 12. JobLauncher and concurrency management

In a system with many launch requests, you need to consider how many jobs can run concurrently and the resources they use.

Some important principles:

- Configure a bounded thread pool to control the number of concurrent executions.
- Define a policy for when two requests target the same JobInstance.
- Do not assume that two different jobs can write to the same table or the same file without conflict.
- Use a durable and consistent JobRepository when the application runs multiple instances.
- Design locks, unique constraints, or business coordination mechanisms when multiple jobs may process the same data.
- Monitor the executor queue and the waiting time before a job actually starts.

The JobRepository helps Spring Batch recognize the executions of a JobInstance and prevents some cases of duplicate launches. It does not replace every business data synchronization mechanism between different jobs or between external systems.

## 13. Testing components that call JobLauncher

When testing a service or controller that calls the JobLauncher, you need to define the goal clearly:

- Verify that the service creates the correct JobParameters.
- Verify that the service calls the correct Job with the correct set of parameters.
- Verify how exceptions are handled when the instance is already running or already completed.
- Verify that the endpoint returns an appropriate execution ID and status.
- For integration tests, confirm that the job actually runs and the metadata is stored as expected.

Spring Batch Test provides utilities such as `JobLauncherTestUtils` to help run jobs in integration tests. A test can create its own parameters for each test so that JobInstances sharing the same identifying parameters do not affect each other.

A conceptual testing example:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("testRun", UUID.randomUUID().toString(), true)
        .toJobParameters();

JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
```

The code above assumes the test has configured `JobLauncherTestUtils`, the job under test, and the appropriate test dependencies. If you are only testing the orchestrating service, you can mock the JobLauncher and verify the call instead of running the whole job.

## 14. Common misconceptions

| Misconception | Correct understanding |
|---|---|
| JobLauncher is the Job | The JobLauncher is the launching component; the Job is the process definition. |
| Calling `run()` means the job has completed | This is only certain when the launcher runs synchronously and the method returned after execution. An asynchronous launcher can return while the job is still running. |
| Every launcher call always creates a new JobInstance | An instance is identified by the job name and the identifying JobParameters. |
| JobLauncher schedules runs by itself | A scheduler or orchestrating component decides when to call the launcher. |
| A JobExecution has only a final status as soon as it is created | An execution can pass through several statuses such as STARTING, STARTED, COMPLETED, or FAILED. |
| JobLauncher handles all business errors | It launches the job; errors in the reader, processor, writer, or tasklet are recorded during job execution. |
| JobRepository and JobLauncher have the same responsibility | The launcher starts the execution; the repository stores execution metadata. |
| Use JobLauncher to stop or restart a running execution | These operational actions are usually performed through JobOperator or an appropriate administration mechanism. |

## 15. A job launch workflow in a real application

A launch flow can be organized in the following sequence:

1. **Receive the request:** from a scheduler, REST API, command line, or another service.
2. **Validate the input:** verify the business date, file, source code, and permission to perform the action.
3. **Create JobParameters:** choose identifying parameters according to the business unit of processing; add non-identifying parameters if you need to store request information.
4. **Select the Job:** get the Job bean that has been configured and is allowed to run.
5. **Call the JobLauncher:** pass the Job and JobParameters.
6. **Handle the acceptance result:** record the execution ID, the initial status, or the exceptions indicating the job could not be launched.
7. **Monitor the execution:** for asynchronous jobs, query the metadata through JobExplorer or receive status events.
8. **Respond with the result:** provide the status and appropriate information to the caller or the operations system.

Separating these steps clearly makes the orchestration layer easier to test, while keeping the data-processing logic in the Job and Step.

## 16. Key points to remember

- `JobLauncher` is the entry point for launching a `Job` with `JobParameters`.
- The launcher works with the `JobRepository` to register a `JobExecution` and ask the job to execute.
- A `JobInstance` is identified by the job name and identifying parameters; an instance can have multiple JobExecutions when restarted.
- `JobExecution` provides the ID, status, timing, ExitStatus, StepExecutions, and error information.
- A launcher can run synchronously or asynchronously depending on the configured executor.
- With an asynchronous launcher, you need to look up the latest status from the JobRepository/JobExplorer instead of treating the initially returned result as the final result.
- Launch exceptions such as instance already running, instance already completed, cannot restart, or invalid parameters need to be handled separately.
- JobLauncher does not replace a scheduler, JobOperator, or JobRepository.
- You need to design JobParameters and concurrency policies carefully to avoid creating unintended instances or processing data twice.

When reading a Spring Batch application, look for where `JobLauncher` is injected, see how `JobParameters` are created, and identify which job is passed to `run`. Then check which executor the launcher uses, where the metadata is stored, and how the application monitors the JobExecution. These details show how the job is launched, monitored, and operated across the whole application.
