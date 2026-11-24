# Synchronous and Asynchronous Launching

In Spring Batch, the `JobLauncher` is the component that receives a `Job` together with `JobParameters` and asks the framework to execute the Job. How the Job is executed depends on the `TaskExecutor` that the JobLauncher uses. With **synchronous** execution, the thread that calls `run()` also executes the Job and continues only after the Job finishes. With **asynchronous** execution, the Job is handed to another execution thread; the `run()` call may return while the Job is still running.

Both ways of running have the same goal of executing a Job, and both create `JobExecution` metadata in the `JobRepository`. The difference lies mainly in the execution thread, how long the call waits, and how the application monitors the result.

## 1. What does JobLauncher do when launching a Job?

The application does not call the Steps directly to manage the entire Job lifecycle itself. Instead, the application passes the Job definition and the input parameters to the `JobLauncher`:

```java
JobExecution execution = jobLauncher.run(importOrdersJob, jobParameters);
```

When it receives a request, the JobLauncher works with the `JobRepository` to validate the JobParameters, find or create the `JobInstance`, create a new `JobExecution` if the request is valid, and then hand the execution work to the configured executor.

The JobExecution records the specific run: ID, JobInstance, timestamps, `BatchStatus`, `ExitStatus`, and the StepExecutions. This metadata allows the application to monitor the Job even when the original calling thread has ended or when the application needs to look up the run history later.

General flow:

```text
Application
   |
   | JobLauncher.run(job, parameters)
   v
JobLauncher
   |
   +--> JobRepository: identify the JobInstance and create the JobExecution
   |
   +--> TaskExecutor: execute the Job
              |
              +--> Job and Steps
              |
              +--> Update status, ExitStatus, and metadata
```

The `TaskExecutor` decides whether the task runs right on the calling thread or is handed to another thread. Therefore, you can change the synchronous/asynchronous behavior without rewriting the business logic in the Steps.

## 2. Synchronous launching

In synchronous mode, the `TaskExecutor` performs the task right on the calling thread. Spring Batch typically uses `SyncTaskExecutor` for this configuration. When the application calls `JobLauncher.run()`, the calling thread enters the Job execution process and waits until the Job finishes.

```text
Calling thread
   |
   +--> JobLauncher.run()
          |
          +--> Create JobExecution
          |
          +--> Run Step 1
          |
          +--> Run Step 2
          |
          +--> Complete Job
   |
   +--> Receive JobExecution after the Job finishes
   |
   +--> Continue processing
```

An example of configuring a JobLauncher that uses `SyncTaskExecutor`:

```java
@Bean
public JobLauncher jobLauncher(JobRepository jobRepository) throws Exception {
    TaskExecutorJobLauncher launcher = new TaskExecutorJobLauncher();
    launcher.setJobRepository(jobRepository);
    launcher.setTaskExecutor(new SyncTaskExecutor());
    launcher.afterPropertiesSet();
    return launcher;
}
```

With this launcher, the following call continues only when the Job has completed:

```java
JobExecution execution = jobLauncher.run(importOrdersJob, jobParameters);

if (execution.getStatus() == BatchStatus.COMPLETED) {
    log.info("Import completed: executionId={}", execution.getId());
} else {
    log.warn("Import ended with status={}", execution.getStatus());
}
```

If the Job takes several minutes to process, the calling thread is also held for that whole time. In a web application, the request thread can be tied up until the Job finishes.

### When should you use synchronous?

Synchronous is suitable when the Job is short, the result is needed immediately to complete an operation, or the application deliberately wants the calling thread to wait for the result. For example, a small data-import step in an internal tool can run synchronously so that the caller receives the final status in the same call.

The advantage is a simple control flow: after `run()`, the application can read the final status and continue based on the result. Error handling and logging are also easy to tie to the calling flow.

The limitation is that the caller's wait time grows with the Job's run time. If the caller is an HTTP request, you need to consider the timeouts of the gateway, web server, and client. If the Job is long-running or may run in parallel multiple times, holding request threads for a long time reduces the ability to serve other requests.

## 3. Asynchronous launching

In asynchronous mode, the JobLauncher hands the task to a `TaskExecutor` that runs it on another thread. The `run()` call may return after the task has been accepted and scheduled, while the Steps are still executing.

```text
Request / caller thread                Batch thread
       |                                   |
       +--> JobLauncher.run()              |
       |       |                           |
       |       +--> Create JobExecution    |
       |       +--> Hand off task ---------+
       |                                   +--> Run Step 1
       +<-- Receive JobExecution           +--> Run Step 2
       |                                   +--> Update result
       +--> Return response / continue     |
                                           v
                                      Job finishes
```

An example of configuring `TaskExecutorJobLauncher` with `ThreadPoolTaskExecutor`:

```java
@Bean
public ThreadPoolTaskExecutor batchTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("batch-");
    return executor;
}

@Bean
public JobLauncher jobLauncher(
        JobRepository jobRepository,
        ThreadPoolTaskExecutor batchTaskExecutor) throws Exception {

    TaskExecutorJobLauncher launcher = new TaskExecutorJobLauncher();
    launcher.setJobRepository(jobRepository);
    launcher.setTaskExecutor(batchTaskExecutor);
    launcher.afterPropertiesSet();
    return launcher;
}
```

`ThreadPoolTaskExecutor` manages a group of reusable threads. `corePoolSize`, `maxPoolSize`, and `queueCapacity` help control the number of tasks running concurrently and the number of tasks waiting in the queue. The `batch-` thread name prefix also helps identify the logs of batch tasks.

After calling the launcher, the application should keep the JobExecution ID for monitoring:

```java
JobExecution execution = jobLauncher.run(importOrdersJob, jobParameters);

Long executionId = execution.getId();
log.info("Job accepted for execution, id={}", executionId);
```

In the example above, the log should express that the request has been launched or accepted. You should not log that the Job has completed just because the `run()` method has returned.

### When should you use asynchronous?

Asynchronous is suitable for long-running Jobs, Jobs started from an API or user interface, Jobs triggered on a schedule, or cases where multiple Jobs need to run without the calling thread waiting. For example, an API that receives a request to import a large file can return an execution ID so the client can query the status later.

The advantage is that the caller can continue other work while the Job runs. The limitation is that the application must have a mechanism for monitoring status, handling errors, limiting concurrency, and notifying about the result when the Job finishes.

## 4. Comparing synchronous and asynchronous

| Criterion | Synchronous | Asynchronous |
|---|---|---|
| Execution thread | The same thread that calls `run()` | A thread managed by the TaskExecutor |
| When `run()` returns | Usually after the Job finishes | Possibly right after the task is handed off/scheduled |
| Status when the result is received | Usually the final status | May still be `STARTING` or `STARTED` |
| Does the caller have to wait for the Job? | Yes | No need to wait for the Job to complete |
| Progress monitoring | The result can be read right after the call | Usually requires querying JobRepository/JobExplorer or a notification mechanism |
| Resources | Occupies the calling thread for the entire run | Occupies a worker thread during the run; the caller is released |
| Suitable cases | Short Jobs that need an immediate result | Long Jobs, APIs, schedulers, background processing |

Both modes use `JobExecution` and `JobRepository`. The difference is not in the Job definition or the business data, but in how the task is executed and when the caller regains control.

## 5. TaskExecutor determines how execution happens

Spring Batch uses Spring's `TaskExecutor` abstraction to decide where the task runs. Some common implementations:

| TaskExecutor | Behavior | When to use |
|---|---|---|
| `SyncTaskExecutor` | Runs right on the calling thread | You want synchronous execution that is easy to follow |
| `SimpleAsyncTaskExecutor` | Creates a new thread for each task; does not reuse a thread pool | Simple background tasks, with a controlled number of them |
| `ThreadPoolTaskExecutor` | Uses a thread pool, with limits on threads and queue | Applications that need to control concurrency and resources |

You should not choose an executor solely because you want to "run faster". An asynchronous executor can make many Jobs run at the same time, increasing the load on the database, file system, or external services. You need to configure limits that fit the system's capacity.

With `ThreadPoolTaskExecutor`, you need to consider:

- The number of Jobs that can run concurrently and the maximum number of threads.
- The queue capacity when all workers are busy.
- The policy when the queue is full or the executor has shut down.
- The shutdown time and how the application handles Jobs that are still running when it stops.
- Shared resources such as the connection pool, API rate limits, and memory capacity.

If you configure a pool that is too large, many Jobs may compete for database connections or I/O resources. If the pool is too small or the queue is too long, launch requests may have to wait a long time before starting. Measure the actual load and set limits deliberately.

## 6. Reading the status when a Job runs asynchronously

In asynchronous mode, the `JobExecution` object returned from `run()` may not yet contain the final status. Depending on when the executor starts executing, the observed status may be `STARTING` or `STARTED`. `endTime` is also not available while the Job has not finished.

The application can use `JobExplorer` to read the latest metadata by execution ID:

```java
JobExecution latest = jobExplorer.getJobExecution(executionId);

if (latest != null) {
    BatchStatus status = latest.getStatus();

    if (status == BatchStatus.COMPLETED) {
        log.info("Job completed: {}", executionId);
    } else if (status == BatchStatus.FAILED) {
        log.error("Job failed: {}", executionId);
    } else {
        log.info("Job is still in progress: status={}", status);
    }
}
```

`JobExplorer` is the API for reading the JobRepository's metadata. It is suitable for status-query endpoints, operations dashboards, or monitoring tasks. If you need to read the latest status, query again instead of holding on to an old object and assuming that object always reflects every update written by other execution threads.

You should not create a continuous polling loop with too high a frequency. You can limit the query frequency, use a notification mechanism when the Job finishes, or build a status endpoint so that clients check proactively at a reasonable interval.

## 7. Designing an asynchronous Job launch API

An API that launches a long Job should usually not hold the HTTP connection until all the data has been processed. Instead, the API acknowledges that the request has been accepted and returns an ID so the client can query the progress.

An illustrative service example:

```java
@Service
public class BatchJobService {

    private final JobLauncher jobLauncher;
    private final Job importOrdersJob;

    public BatchJobService(JobLauncher jobLauncher, Job importOrdersJob) {
        this.jobLauncher = jobLauncher;
        this.importOrdersJob = importOrdersJob;
    }

    public Long startImport(String businessDate, String inputFile)
            throws JobExecutionException {

        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", businessDate, true)
                .addString("inputFile", inputFile, true)
                .toJobParameters();

        JobExecution execution = jobLauncher.run(importOrdersJob, parameters);
        return execution.getId();
    }
}
```

The controller can return HTTP `202 Accepted` together with the execution ID:

```java
@RestController
@RequestMapping("/batch/imports")
public class ImportController {

    private final BatchJobService batchJobService;

    public ImportController(BatchJobService batchJobService) {
        this.batchJobService = batchJobService;
    }

    @PostMapping
    public ResponseEntity<Map<String, Object>> startImport(
            @RequestParam String businessDate,
            @RequestParam String inputFile) throws JobExecutionException {

        Long executionId = batchJobService.startImport(businessDate, inputFile);

        return ResponseEntity.accepted().body(Map.of(
                "executionId", executionId,
                "statusUrl", "/batch/imports/" + executionId
        ));
    }
}
```

A separate GET endpoint can use `JobExplorer` to return the current status. A `202 Accepted` response means the request has been accepted for processing; it does not mean the Job has completed successfully.

In a real system, you need to authenticate the caller, check access permissions for the execution ID, and limit duplicate launches. You should not allow users to arbitrarily look up other people's JobExecutions just by guessing IDs.

## 8. Distinguishing launch errors from errors during execution

When calling `JobLauncher.run()`, you need to distinguish two groups of errors:

**Errors that prevent the request from being launched validly:** for example invalid JobParameters, a JobInstance that has already completed, an execution of the JobInstance that is still running, or a Job that does not allow restart. These cases can be represented by exceptions such as `JobParametersInvalidException`, `JobInstanceAlreadyCompleteException`, `JobExecutionAlreadyRunningException`, or `JobRestartException`.

**Errors that occur while the Job is executing:** for example a file that cannot be read, a database write error, or an error from an external service. These errors are usually reflected through `BatchStatus.FAILED`, `ExitStatus`, and the JobExecution's exception metadata. In synchronous mode, the caller usually receives the JobExecution after the Job finishes with a failed status. In asynchronous mode, the caller may have received the initial JobExecution before the error occurred; you need to query the metadata afterward to learn the result.

In addition, the executor may refuse to accept a task if it has shut down or cannot accept more work. This is an error at the task hand-off stage and needs to be handled separately in operations.

An example of handling launch exceptions:

```java
try {
    JobExecution execution = jobLauncher.run(importOrdersJob, jobParameters);
    log.info("executionId={}, status={}", execution.getId(), execution.getStatus());
} catch (JobExecutionAlreadyRunningException ex) {
    log.warn("This JobInstance is already running", ex);
} catch (JobInstanceAlreadyCompleteException ex) {
    log.info("This JobInstance has already completed", ex);
} catch (JobParametersInvalidException | JobRestartException ex) {
    log.error("Job could not be launched", ex);
}
```

The specific exceptions can be grouped or converted into an appropriate response at the API layer. However you handle them, you need to distinguish a launch-request error from the FAILED status of an execution that has already started.

## 9. JobParameters and concurrent launching

JobParameters take part in identifying the JobInstance if they are marked identifying. When two requests use the same Job and the same identifying parameters, they target the same JobInstance. Spring Batch does not allow two JobExecutions to run concurrently on the same JobInstance in the usual way; the JobRepository checks the state and may reject the second request with `JobExecutionAlreadyRunningException`.

If the application needs to process two different business datasets in parallel, each request needs appropriate identifying parameters to represent a different JobInstance. For example, two different business dates can create two separate JobInstances. You should not add a random timestamp to every run just to avoid the exception, because doing so can unintentionally create multiple JobInstances for the same business task and break restartability.

In an environment with multiple application instances, the JobRepository and database need to be configured to coordinate execution creation and control duplicate launches. Do not rely on a boolean variable or the local memory of a single server to prevent two servers from running the same JobInstance.

## 10. Context and transactions when running asynchronously

When a Job is moved to a worker thread, the execution thread does not implicitly inherit all the state attached to the request thread. For example, a transaction opened in the controller, security information in thread-locals, or the MDC used for logging are not automatically passed to the batch thread.

Therefore:

- Pass the necessary input data through `JobParameters` or store it in a data store accessible from the worker.
- Let the Steps manage their own transactions according to the Spring Batch configuration; do not rely on the HTTP request's transaction to wrap an asynchronous Job.
- If you need information about who launched the run, store an appropriate identifier in JobParameters or business metadata, and control sensitive data.
- If you need to pass the SecurityContext, tracing context, or MDC, configure an explicit propagation mechanism for the executor; do not assume thread-locals are copied automatically.
- Make sure the beans and components shared within the Job are safe when there are multiple concurrent executions. Avoid storing the private state of a single run in mutable fields of a singleton bean.

These points are especially important when converting a Job that originally ran synchronously to asynchronous: the code may still compile and run, but assumptions about transactions, thread-locals, or in-memory data may no longer hold.

## 11. Configuration by version and application environment

The class name implementing the JobLauncher and the way Spring Boot auto-configures it can differ by Spring Batch version. In modern versions, `TaskExecutorJobLauncher` is the implementation that uses a `TaskExecutor`; older projects may encounter `SimpleJobLauncher`. Use the implementation and API appropriate to your project's dependency version.

In a Spring Boot application, the framework may auto-configure the JobLauncher and batch components. If you need to change the executor, check the existing configuration before declaring a replacement bean to avoid creating two launchers or losing the repository settings the application is using.

Some points to confirm when configuring:

- The JobRepository used by the JobLauncher must be the repository that the application's Jobs and Steps use.
- The executor needs to have its lifecycle managed by Spring so that it can shut down properly.
- The pool size needs to fit the database connection limits and downstream resources.
- You need to define the behavior when the application shuts down while a Job is running, including waiting for completion, a controlled stop, or allowing a restart after the application starts again.
- With multiple application instances, the metadata repository must be shared and configured appropriately for concurrency.

## 12. Common misconceptions

**Believing that asynchronous makes the Job process faster.** Asynchronous releases the caller and allows managing multiple tasks, but it does not by itself make a Step process faster. Performance depends on the reader, processor, writer, database, I/O, and the actual degree of parallelism.

**Believing that `run()` returning means the Job has completed.** This is usually true with a synchronous executor, but not with an asynchronous executor. Look at the JobExecution status and query the latest metadata.

**Using too many threads to increase throughput.** Too many concurrent Jobs can exhaust the connection pool, increase contention, and overload external services. Limit concurrency according to the system's capacity.

**Not handling JobExecutionAlreadyRunningException.** Two requests with the same identifying parameters may target the same JobInstance. The application needs to decide whether to report that it is running, reject the duplicate request, or schedule it according to business rules.

**Assuming the request's transaction applies to an asynchronous Job.** The worker thread executes independently of the request thread. The Job/Step transactions must be configured on the batch thread itself.

**Having no way to view the status after returning the response.** When using asynchronous, store the execution ID and provide an API or screen to look it up using JobExplorer/JobRepository.

## 13. Choosing the appropriate launch mode

Use synchronous when the Job is short and the caller needs the result immediately in the same call. Use asynchronous when the Job is long, is triggered through an API or scheduler, or needs to release the caller during processing. With asynchronous, you need to additionally design how to monitor status, handle duplicate requests, limit the number of concurrent Jobs, and manage shutdown.

In both modes, the `JobLauncher` still launches the same Job definition, the `JobRepository` still manages the JobInstance and JobExecution, and the Steps still carry out the business logic. Understanding the role of the `TaskExecutor` helps you choose when the caller waits and organize the execution resources to suit the application's requirements.
