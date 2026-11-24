# JobLauncher with TaskExecutor

In Spring Batch, `JobLauncher` is the component that receives a request to launch a `Job` together with a set of `JobParameters`. How the job is executed depends on the `TaskExecutor` that the launcher uses. If a synchronous executor is used, the job runs right on the thread that calls `JobLauncher.run`, and the method returns only after the job finishes. If an asynchronous executor is used, the launcher sends the work to another thread and can return the `JobExecution` right after the task is accepted.

Combining `JobLauncher` with `TaskExecutor` lets the application control how batch is launched: run synchronously for a simple flow, or run in the background so that a web request, scheduler, or orchestrating component does not have to wait for the entire job to complete. `TaskExecutor` only decides which thread the job is executed on; it does not by itself make the steps inside the job run in parallel.

## The role of JobLauncher

`JobLauncher` provides the API to launch a job:

```java
JobExecution execution = jobLauncher.run(job, jobParameters);
```

When it receives the call, the launcher works with the `JobRepository` to identify the `JobInstance`, check the run history, and create an appropriate `JobExecution`. The launcher then asks the executor to execute the job. The repository stores metadata about the instance, the execution, the status, and the information needed for restart.

The main responsibilities can be summarized as follows:

| Component | Responsibility |
| --- | --- |
| `JobLauncher` | Receives a request to run a job, validates the launch conditions, and creates a `JobExecution` through the repository |
| `JobRepository` | Stores metadata, controls instance identity and the execution history |
| `TaskExecutor` | Executes the job task on a synchronous thread or a thread managed by the executor |
| `Job` | Orchestrates the steps and the configured processing flow |
| `JobExecution` | Represents one specific execution and provides the status, timestamps, and exit status |

`JobLauncher` does not itself define how to run steps in parallel. It orchestrates starting one job execution. If you need multiple steps to run concurrently within the same job, you need to configure a parallel flow, partitioning, or an appropriate concurrency mechanism at the step level.

## What is a TaskExecutor?

`TaskExecutor` is Spring's abstraction for executing a `Runnable`. It is similar to the executor concept in Java but integrated with the Spring ecosystem. `TaskExecutorJobLauncher` uses this abstraction to run jobs.

Common implementations:

| Implementation | How it works | Use case |
| --- | --- | --- |
| `SyncTaskExecutor` | Runs the task right on the thread that calls `execute` | Synchronous default, tests, or simple flows |
| `SimpleAsyncTaskExecutor` | Creates a new thread for each task, can limit concurrency | Small examples or low load; the number of threads needs to be controlled |
| `ThreadPoolTaskExecutor` | Reuses threads from a pool, has a queue and a thread limit | Production applications that need to control resources |
| `ConcurrentTaskExecutor` | Adapter for a `java.util.concurrent.Executor` | Integrating an existing Java executor |

One thing to remember is that the name `TaskExecutor` is not synonymous with asynchronous. `SyncTaskExecutor` executes synchronously. Only when you configure an executor that executes on another thread, for example `ThreadPoolTaskExecutor`, does the `JobLauncher.run` call have the early-return, background-style behavior.

## Synchronous and asynchronous

### Synchronous execution

With `SyncTaskExecutor`, the job runs on the current thread. The `run` call ends only when the job execution has completed or failed.

```text
Calling thread
    |
    v
JobLauncher.run(job, parameters)
    |
    v
Job executes the steps
    |
    v
Job completes or fails
    |
    v
Return JobExecution to caller
```

The advantage of this way of running is an easy-to-understand control flow: the caller can receive the final result right after `run` returns. It suits command-line runners, small batches, or cases where the calling component needs to wait for the result to perform the next step.

The disadvantage is that the calling thread has to wait. If the caller is a thread handling an HTTP request, the request may hold the connection for the whole time the job runs. A long job can also occupy a scheduler thread or the thread of an orchestrating component.

### Asynchronous execution

With an executor such as `ThreadPoolTaskExecutor`, the launcher sends the work to the pool. The calling thread can receive the `JobExecution` before the job completes.

```text
HTTP request / Scheduler thread
          |
          v
JobLauncher.run(job, parameters)
          |
          +----> JobRepository creates JobExecution
          |
          +----> TaskExecutor receives task
          |                 |
          v                 v
   Return JobExecution  Worker thread
                            |
                            v
                       Job executes
                            |
                            v
                       Update status
                       in JobRepository
```

The caller does not have to wait for the entire job. It can return the `JobExecution` ID to the client, record the request, or continue handling other tasks. The final status is updated in the repository after the worker finishes executing.

Right after the launcher returns, the `JobExecution` may still be in a state such as `STARTING` or `STARTED`. You must not treat receiving the `JobExecution` object as proof that the job has completed. To learn the final result, you need to look up the status afterward through `JobExplorer`, an administration API, or an equivalent monitoring mechanism.

## Configuring TaskExecutorJobLauncher

In modern Spring Batch versions, `TaskExecutorJobLauncher` is the implementation that uses a `TaskExecutor` to execute jobs. When no asynchronous executor is specified, the launcher usually uses a synchronous executor. To run jobs on a thread pool, you need to configure an executor and attach it to the launcher.

An example configuration with `ThreadPoolTaskExecutor`:

```java
@Configuration
public class BatchLauncherConfiguration {

    @Bean
    public ThreadPoolTaskExecutor batchJobTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("batch-job-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(60);
        return executor;
    }

    @Bean(name = "jobLauncher")
    public JobLauncher jobLauncher(
            JobRepository jobRepository,
            ThreadPoolTaskExecutor batchJobTaskExecutor) throws Exception {

        TaskExecutorJobLauncher launcher = new TaskExecutorJobLauncher();
        launcher.setJobRepository(jobRepository);
        launcher.setTaskExecutor(batchJobTaskExecutor);
        launcher.afterPropertiesSet();
        return launcher;
    }
}
```

In the example:

- `JobRepository` is provided to the launcher to create and update metadata.
- `ThreadPoolTaskExecutor` manages the worker threads that execute jobs.
- `corePoolSize` is the base number of threads kept in the pool.
- `maxPoolSize` limits the maximum number of threads when the pool needs to expand.
- `queueCapacity` limits the number of tasks waiting before the pool expands to its limit or rejects tasks.
- `threadNamePrefix` helps identify workers in logs and thread dumps.
- `waitForTasksToCompleteOnShutdown` together with `awaitTerminationSeconds` help wait for running tasks when the application shuts down.

This is an illustrative configuration for an application that manages the launcher itself. If Spring Boot has already auto-configured the `JobLauncher`, you need to check the auto-configuration mechanism and the bean-creation conditions of the version you are using before declaring a replacement bean. You should not accidentally create multiple launchers with different names or configurations, which causes calling components to use the wrong launcher.

The configuration API may differ between Spring Batch versions. Older examples may use `SimpleJobLauncher`; in newer versions, prefer the implementation recommended by the documentation for your project's version, usually `TaskExecutorJobLauncher`.

## Launching a job from the application

After configuring the launcher, a business component can inject `JobLauncher` and call `run` with an appropriate set of parameters.

```java
@Service
public class SettlementJobService {

    private final JobLauncher jobLauncher;
    private final Job dailySettlementJob;

    public SettlementJobService(
            JobLauncher jobLauncher,
            Job dailySettlementJob) {
        this.jobLauncher = jobLauncher;
        this.dailySettlementJob = dailySettlementJob;
    }

    public JobExecution start(LocalDate businessDate) throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", businessDate.toString(), true)
                .toJobParameters();

        return jobLauncher.run(dailySettlementJob, parameters);
    }
}
```

`businessDate` is marked identifying because it identifies the logical settlement unit. If the job runs asynchronously, the `start` method usually returns before the settlement completes. The caller can take `execution.getId()` to give the client a lookup code or store it for monitoring.

Do not add a new identifying timestamp for every call just to avoid a duplicate-launch error. If an execution is already running for the same business date, the repository needs to recognize that it is the same `JobInstance` and apply the duplicate-run prevention rule. If you need a new logical run, add an identifying parameter with a clear business meaning.

## Monitoring the JobExecution after the launcher returns

When using an asynchronous executor, the caller usually receives only the information that the run has been created and sent to the executor. To learn whether the job has finished, you can use `JobExplorer` to look up the execution by ID.

```java
@Service
public class BatchExecutionQueryService {

    private final JobExplorer jobExplorer;

    public BatchExecutionQueryService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public JobExecution findExecution(Long executionId) {
        return jobExplorer.getJobExecution(executionId);
    }
}
```

An example of an API that can return the execution ID right after launching:

```java
@RestController
@RequestMapping("/batch/settlements")
public class SettlementController {

    private final SettlementJobService jobService;

    public SettlementController(SettlementJobService jobService) {
        this.jobService = jobService;
    }

    @PostMapping
    public ResponseEntity<Map<String, Object>> start(
            @RequestParam LocalDate businessDate) throws Exception {

        JobExecution execution = jobService.start(businessDate);

        return ResponseEntity.accepted().body(Map.of(
                "executionId", execution.getId(),
                "status", execution.getStatus().toString()
        ));
    }
}
```

HTTP `202 Accepted` indicates that the request has been accepted for background processing. The `status` value in the response is only the status at the time the response is returned; the client needs to call a status-lookup endpoint to learn the final result. A production API usually also returns a tracking URL or provides a GET endpoint that takes an `executionId`.

When reading the status, you should query the repository through `JobExplorer` or an administration service instead of holding a `JobExecution` object in memory and assuming it will always reflect the latest status. In a multi-node system, the metadata database is the reliable shared source of status.

## Handling errors when launching asynchronously

You need to distinguish errors that occur while accepting the request from errors that occur while the job executes.

### Errors before the task is accepted

Some errors are detected right in the calling thread, for example an invalid job, a parameter that does not match the existing instance, an instance that has already completed, an execution that is already running, or the repository failing to create the execution. The executor can also reject a task when the pool and queue are full; with a Spring executor, this situation is usually represented by `TaskRejectedException`.

The caller needs to handle these errors to return an appropriate response, write logs, and report that the request was not launched successfully. You should not return an execution ID as if the task had definitely been accepted if the `run` call throws an exception.

### Errors in the worker thread

After the task has been sent to the worker, errors in the reader, processor, writer, or step occur on the execution thread. Spring Batch updates the status of the `JobExecution` and `StepExecution` according to the execution result. The original caller has usually already finished the request, so it cannot receive an asynchronous exception like an ordinary exception from the `run` call.

The application needs to monitor the final status in the repository, write logs with the execution ID, and provide a notification or monitoring mechanism if the business needs to know the result. A failed job is usually represented by `BatchStatus.FAILED` and the corresponding exit status in the metadata; you should not rely only on the HTTP response at launch time.

An example of handling acceptance errors:

```java
try {
    JobExecution execution = jobLauncher.run(job, parameters);
    return execution.getId();
} catch (JobExecutionAlreadyRunningException ex) {
    // The same JobInstance already has a running execution.
    throw ex;
} catch (JobInstanceAlreadyCompleteException ex) {
    // This logical job has already completed.
    throw ex;
} catch (JobParametersInvalidException ex) {
    // The parameter set is invalid.
    throw ex;
} catch (TaskRejectedException ex) {
    // The executor cannot accept more tasks at this time.
    throw ex;
}
```

The specific exceptions may differ by API version and by how the application wraps errors. In practice, you should handle them in an appropriate orchestration layer, record the cause, and map it to an easy-to-understand business response.

## Limiting concurrency and managing the thread pool

`ThreadPoolTaskExecutor` helps control the number of jobs that can run concurrently within one application instance. If the pool has 4 worker threads, at most 4 tasks can be executed concurrently in that pool; subsequent tasks can wait in the queue or be rejected depending on the configuration.

Important parameters:

| Parameter | Meaning | Considerations |
| --- | --- | --- |
| `corePoolSize` | Base number of worker threads | Choose according to the number of jobs that must run regularly and the machine's resources |
| `maxPoolSize` | Maximum number of workers when load increases | Limited by CPU, memory, and the database connection pool |
| `queueCapacity` | Number of tasks that can wait | A queue that is too large can make jobs wait a long time and consume memory |
| `keepAliveSeconds` | How long to keep threads above the core size when idle | Useful when load rises and falls over time |
| Rejection policy | How to handle the case when both pool and queue are full | There must be a clear rejection or back-pressure behavior |

With `ThreadPoolTaskExecutor`, once the number of workers has reached the core size, new tasks are usually placed in the queue. Only when the queue is full does the pool expand up to the max size; if both the pool and the queue are full, the task is rejected according to the rejection policy. Therefore, increasing `maxPoolSize` does not mean every task will immediately create an additional thread if the queue still has room.

You should not configure the number of workers based only on the number of CPUs. Jobs usually consume database connections, locks, memory, file descriptors, and the resources of external systems. If 20 jobs run at the same time and each job opens many connections or holds transactions for a long time, the database can be overloaded even if the application machine still has CPU.

Choose the pool size based on:

- The number of jobs that can run concurrently according to business requirements.
- The CPU and memory consumed by each type of job.
- The connection pool and the processing capacity of the database.
- Transaction hold time, locks, and the level of access to external systems.
- The number of deployed nodes; the concurrency limit on each node needs to be multiplied by the number of nodes to understand the load on the whole system.

## The relationship between TaskExecutor and JobRepository

`TaskExecutor` controls the execution thread; `JobRepository` manages metadata and the identification rules. The two components have different roles and need to cooperate correctly.

In a production application, multiple launchers or multiple nodes may send requests to run jobs at the same time. The nodes should share a single durable `JobRepository`. The repository uses transactions and appropriate constraints to prevent two concurrent requests from creating or running conflicting executions for the same `JobInstance`.

If the job name and identifying parameters are the same, the calls point to the same logical job. When an execution is running, another request for the same instance is usually rejected with a corresponding error such as `JobExecutionAlreadyRunningException`. If the identifying parameters differ, they are different `JobInstance`s and can run concurrently if resources and configuration allow.

The executor does not replace the repository's locking and transaction mechanism. Limiting the number of threads in one JVM is not enough to prevent duplicate jobs across multiple nodes or multiple independently launched applications.

## TaskExecutor does not make steps run in parallel automatically

This is an easy point of confusion when configuring `JobLauncher` with an executor.

When the launcher uses `ThreadPoolTaskExecutor`, the whole job is executed on a single worker thread provided by the pool. Inside the job, the steps still run according to the configured flow, usually sequentially. For example:

```text
JobLauncher
    |
    v
Worker thread A
    |
    v
Step 1 -> Step 2 -> Step 3
```

If you want multiple different jobs to run concurrently, you can use one launcher with a thread pool and launch independent `JobInstance`s. If you want multiple steps or flow branches of the same job to run in parallel, you need to configure `split` with an executor or another parallel processing approach supported by Spring Batch. If you want to divide large data into parts that run concurrently, you can use partitioning or remote chunking.

You should not increase the `JobLauncher` pool expecting a single job to speed up by running all steps at once. The launcher pool controls concurrency between job executions submitted to the pool.

## Calling JobLauncher from a web request or scheduler

### From a web request

For long-running jobs, the asynchronous model is usually more suitable: the API receives the request, creates a `JobExecution`, returns the ID, and provides a status-lookup endpoint. The client does not need to hold the HTTP connection until the job finishes.

The API should authenticate launch permission, validate input, determine identifying parameters, and handle duplicate requests. If possible, apply an idempotency key at the API layer so that two requests retried because of a timeout do not unintentionally create two independent business requests.

### From a scheduler

A scheduler can call the launcher to send jobs into the pool. You need to clearly determine whether the schedule allows overlapping runs. If the previous day's job is still running when the next day's schedule arrives, the application needs to decide whether to queue, skip, reject, or let it run in parallel with a different parameter.

Using an asynchronous executor does not by itself solve overlapping schedules. You need to combine identifying parameters, a shared repository, and an appropriate scheduler policy. If the scheduler can replay triggers after a failure, the job design must tolerate repeated launch requests.

## Thread context and supporting components

When a task moves to a worker thread, data attached to the calling thread is not automatically passed to the new thread. For example, `ThreadLocal`, the security context, the MDC logging context, the locale, or some tracing contexts may not exist in the worker.

If the job needs to know which user requested the run, pass the necessary identifier through `JobParameters` or a controlled context mechanism. You should not rely on the HTTP request or the security context of the calling thread, because the request may have ended by the time the job starts executing.

For logging/tracing, you can configure a `TaskDecorator` for `ThreadPoolTaskExecutor` to copy the necessary contexts from the task-submitting thread to the worker, and also restore the thread state after the task completes. Pass only the necessary data and make sure to clear the context after each task to avoid leaking information between jobs running on the same worker thread.

`@Async` and `@EnableAsync` are asynchronous processing mechanisms at the Spring method invocation layer. They are not a required condition for `TaskExecutorJobLauncher` to run jobs asynchronously. The launcher directly uses the configured `TaskExecutor`. Avoid wrapping the same call with an additional `@Async` without a clear reason, because it can create two layers of executors, making the queue and errors hard to control.

## Shutting down the application while jobs are running

With a background executor, a job may still be active when the application receives a shutdown signal. If the pool stops immediately, workers may be interrupted mid-processing. You need to configure the lifecycle and shutdown policy to fit the job run time.

`waitForTasksToCompleteOnShutdown` lets the executor wait for tasks that have been accepted to complete during shutdown; `awaitTerminationSeconds` limits the wait time. This is not an absolute guarantee that every job will complete: the wait time is limited, the process can be killed, and infrastructure failures can still occur.

Long jobs need a proper restart and checkpoint strategy. When the process stops abruptly, Spring Batch may need to analyze the execution state and recover according to an operational procedure. You should not mark a job as completed just because the executor has been shut down or the task has left the queue.

## When should you use a TaskExecutor with JobLauncher?

| Need | Suggested configuration |
| --- | --- |
| Short job, caller needs the result immediately | `SyncTaskExecutor` or a synchronous launcher |
| API receiving requests for long-running jobs | `ThreadPoolTaskExecutor` and return the execution ID |
| Scheduler launching many independent jobs | A bounded thread pool and a shared repository |
| Low load, such as experiments | A simple executor; still control the number of threads if running in the background |
| Need multiple steps to run in parallel within the same job | Configure a separate parallel flow/step; do not just change the launcher executor |
| Need to process multiple partitions | Configure the partition handler and executor at the step level |

Before choosing asynchronous, determine who monitors the final status, how to handle errors after the task is accepted, the concurrency limit, and the behavior when the application shuts down.

## Common errors

### Calling run but the job still runs on the request thread

The cause is usually that the launcher is using `SyncTaskExecutor` or the auto-configuration is still synchronous. Check the actual launcher implementation and whether the `TaskExecutor` bean has been attached to the launcher.

### The API returns STARTING or STARTED

This is normal behavior when the launcher runs asynchronously. The response is returned when the job has just been sent to the executor; the client needs to look it up again through `JobExplorer` or a status endpoint.

### Tasks are rejected when load increases

The pool and queue may be full. Check `corePoolSize`, `maxPoolSize`, `queueCapacity`, the rejection policy, and how long jobs wait. You need to return an appropriate acceptance error or apply back-pressure instead of silently dropping requests.

### Two requests launch the same logical job

If two requests have the same job name and identifying parameters, they point to the same `JobInstance`. When an execution is already running, the second request is usually rejected by the repository. Check the identifying parameters and handle the exception at the API layer.

### The job fails but the request already returned success

A successful response only indicates that the request was accepted. The worker may encounter an error later. Monitor `BatchStatus`, `ExitStatus`, logs, and metadata using `JobExplorer`; provide a notification mechanism when the business needs to know the result.

### Parallel jobs overload the database

The pool may allow many jobs to open transactions or read/write the database at the same time. Reduce concurrency, optimize queries, and check the connection pool and lock contention. Do not just increase the number of workers without measuring the database load.

## Deployment principles

When bringing an asynchronous `JobLauncher` into production, you need to agree on the following points:

1. Choose the executor explicitly; configure the pool, queue, and rejection policy according to the system's capacity.
2. Use a durable `JobRepository` shared among the relevant nodes.
3. Design identifying parameters to prevent duplicate launches and support restart.
4. Return the execution ID to the caller; provide an API or mechanism to monitor the final status.
5. Distinguish task-acceptance errors from errors that occur in the worker thread.
6. Control thread context, logging, tracing, and security context when they need to be passed to the worker.
7. Configure graceful shutdown and ensure the job can be restarted after the process stops.
8. Measure concurrency together with the load on the database, memory, CPU, and external systems.
9. Configure a separate parallel flow or partitioning if the goal is parallelism within a single job.

## Key takeaways

`JobLauncher` receives the job and parameters, while `TaskExecutor` decides how the task is executed. With `SyncTaskExecutor`, `run` executes synchronously on the calling thread. With `ThreadPoolTaskExecutor`, the job can run in the background on a worker thread and the launcher returns the `JobExecution` before the job completes. In that case, the final status must be monitored through the `JobRepository` or `JobExplorer`, errors in the worker need to be observed through metadata and logs, and task-acceptance errors must be handled right at the caller. The thread pool needs to be bounded according to actual resources; the launcher's executor controls concurrency between jobs and does not by itself make the steps within a job run in parallel.
