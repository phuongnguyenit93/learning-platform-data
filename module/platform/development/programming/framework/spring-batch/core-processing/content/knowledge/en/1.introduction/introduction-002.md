# How Does Batch Processing Differ from Online Request Processing?

Batch processing and online request processing both execute business logic on data. The differences lie in how the work is launched, the unit of data being processed, the completion time the caller expects, and how the system manages errors.

With an online request, the application usually handles a small request while a user or another system is waiting for the result. With batch processing, the application groups many records into a job with a clear start and end, processes them step by step, and then stores the results and the run state. A batch job can take minutes or hours without needing to keep an HTTP connection open for that whole time.

## 1. How Does Online Request Processing Work?

In the online request processing model, a client sends a request to the application, usually over HTTP. The server executes the necessary logic and returns a response to that very request.

A typical flow looks like this:

```text
Client
  |
  | HTTP request
  v
Controller / API
  |
  v
Business service
  |
  +----> Database / Cache / External service
  |
  v
HTTP response
  |
  v
Client
```

For example, when a user views the details of an order, the application receives `GET /orders/123`, looks up the order in the database, applies the display rules, and returns the data to the browser. When a user creates an order, the application validates the data, records the order, and returns the order creation result.

Common characteristics of online processing:

- **Starts from a specific request:** a request from a user or a service is the direct cause of the logic being executed.
- **Small, bounded unit of work:** usually a single query, a single update statement, or a single business operation.
- **A caller is waiting:** the client expects to receive the result within a short period, consistent with the timeout of HTTP or the protocol in use.
- **Latency matters:** the response time of each request directly affects user experience and the system's responsiveness.
- **Errors are returned to the caller:** for example, a `4xx` response when the data is invalid or a `5xx` when the server runs into a problem. The caller can display the error or decide to retry.

An online request does not necessarily read just one record. It can run multiple queries or update multiple tables. Even so, the scope of work is usually kept small enough to finish within the time the request is allowed to live.

## 2. How Does Batch Processing Work?

Batch processing starts from a predefined piece of work. The work can be triggered on a schedule, by an operator, by an event, or by a request that creates a job. Instead of returning a business result immediately to a waiting client, the system processes a set of data and then records the result of the whole run.

A typical batch flow:

```text
Scheduler / Operator / Job launcher
                |
                v
             Batch Job
                |
                v
         Step 1: Read data
                |
                v
         Step 2: Process data
                |
                v
         Step 3: Write results
                |
                v
        Save state and results
```

For example, at the end of the day the system needs to calculate fees for 800,000 accounts. The job can read the list of accounts in the billing period, calculate the amount to collect, write the resulting transactions, and generate a report. This work may run for a long time, needs to divide the data into many portions, and needs to know how far it has gotten if the process is stopped.

Common characteristics of batch processing:

- **Starts from a job:** a run schedule, an operational action, or a launch command determines the work to perform.
- **The unit of work is a data set:** a job can process thousands, millions, or more records.
- **The caller does not need to wait until processing completes:** the job can run in the background. The system stores the state so that operators or other applications can look it up later.
- **Throughput matters:** the goal is usually to finish a volume of data within an allowed processing window (batch window).
- **Progress management and rerunnability are needed:** a job may have to continue from a checkpoint or reprocess part of the data after an error.

Batch does not mean always running at night. A job can run every minute, every hour, on an event, or be launched right after data becomes available. The batch nature comes from processing a piece of work/data set with a defined scope, not just from the time of day it runs.

## 3. Direct Comparison

| Aspect | Online request | Batch processing |
|---|---|---|
| How it is launched | A client sends a request | A scheduler, operator, event, or job launcher launches the job |
| Unit of processing | A single business operation or a single request | A data set or a piece of work made up of multiple steps |
| Caller waits for the result | Usually yes | Usually no; the job runs independently and stores its state |
| Time goal | Low latency for each request | Complete the entire volume within the batch window |
| Volume | Usually small and bounded per request | Can be very large, divided into portions |
| Transaction boundary | Usually tied to a single business operation | Usually divided per chunk or per step |
| Error handling | Return the error to the caller; the caller can retry | Can retry, skip bad records, stop the job, or restart from saved state |
| Monitoring | Request ID, logs, and metrics per request | Job/step execution, number of records read/written, time, and status of each step |
| Examples | Order lookup, login, order creation | Data import, reconciliation, payroll calculation, statement generation |

This is a difference in operational goals, not an absolute boundary. An online API can still update many records; a batch job can still process a small data set. The design should be based on response-time requirements, data scale, how recovery works, and how users receive results.

## 4. Why Not Process a Large Batch Inside an HTTP Request?

Suppose an API receives a request to recalculate reward points for two million accounts. If the controller performs all of the work before returning the response, the request can last tens of minutes. This approach creates several problems:

1. **Timeout:** the browser, API gateway, load balancer, or HTTP client may close the connection before the server finishes.
2. **Resources held for a long time:** the request occupies a processing thread, a connection, or other resources for a long period. Many similar requests can reduce the ability to serve short operations.
3. **Hard to recover:** if the process dies after processing part of the data, a single request usually has no checkpoint mechanism to know where to continue.
4. **Hard to observe progress:** the caller only sees the request waiting or timed out, while the work on the server side may still be running.
5. **Retrying can cause repeated side effects:** the caller does not know how far the server got before the connection was dropped. Resending the request can create duplicate transactions or updates if the business operation is not designed to be idempotent.

A batch job solves this problem by separating the lifetime of the work from the lifetime of the request connection. The system can store the job ID, state, progress, and results for the caller to check later.

An example of an API that starts a long-running job:

```text
POST /recalculations
        |
        v
Validate request and create job
        |
        +----> Save job ID: 8f31...
        |
        v
Return HTTP 202 Accepted
        |
        v
Job runs in the background

GET /jobs/8f31...
        |
        v
Return status: STARTED / COMPLETED / FAILED
```

In this model, the API still handles the request intake online. The heavy computation is handed to a batch job. The `202 Accepted` response indicates that the request has been accepted for processing, not that the entire business operation has completed.

## 5. How Does Spring Batch Organize Batch Work?

Spring Batch provides a model for defining, running, and monitoring data-processing jobs. The core concepts that distinguish how batch runs from an ordinary request are `Job`, `Step`, `JobInstance`, `JobExecution`, `StepExecution`, `JobRepository`, and `ExecutionContext`.

### Job and Step

A **Job** represents a complete batch process, such as `dailyBillingJob` or `customerImportJob`. A Job is composed of one or more **Steps**. Each Step performs a part of the work that can be managed separately, for example reading a file, validating data, writing to a database, or generating a report.

For a customer import job, the steps might be:

```text
customerImportJob
  |
  +--> validateInputStep
  |
  +--> importCustomersStep
  |
  +--> generateReportStep
```

The job determines the order and flow in which the steps run. A step can run just a single task (a tasklet), or process many items using the chunk model.

### Chunk-Oriented Processing

For data made up of many records, Spring Batch usually uses the chunk-oriented processing model. A step reads item by item, can transform or validate each item, and then writes a group of items once the configured chunk size is reached.

```text
ItemReader
    |
    v
ItemProcessor (optional)
    |
    v
ItemWriter
    |
    v
Commit transaction for the chunk
```

The configuration example below uses the Spring Batch 5 API. The `reader`, `processor`, and `writer` beans are provided separately according to the application's data source and business logic:

```java
@Bean
Job customerImportJob(JobRepository jobRepository, Step importStep) {
    return new JobBuilder("customerImportJob", jobRepository)
            .start(importStep)
            .build();
}

@Bean
Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> reader,
        ItemProcessor<CustomerInput, Customer> processor,
        ItemWriter<Customer> writer) {

    return new StepBuilder("importStep", jobRepository)
            .<CustomerInput, Customer>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

With `chunk(500, transactionManager)`, Spring Batch gathers up to 500 items that have been read and processed into a chunk before calling the writer and committing the transaction. If an error causes the chunk's transaction to roll back, the changes belonging to that transaction are undone. Retry or skip configuration can determine how certain types of errors are handled; these need to be designed according to the business rules and the actual error types.

Chunk size is an operational decision. A small chunk usually produces more commits but limits the amount of work in each transaction. A large chunk can reduce commit overhead but holds transactions and resources longer, and also increases the amount of data that must be reprocessed when a chunk fails. There is no single size that suits every system.

### JobInstance, JobExecution, and JobParameters

Spring Batch distinguishes a logical run from a specific execution:

- **JobInstance:** a logical run of a job, identified by the job name and the identifying `JobParameters`. For example, `dailyBillingJob` for the date `2026-11-15` is an instance for that business period.
- **JobExecution:** one execution of a JobInstance. If a run fails and is restarted, the instance can have a new execution.
- **StepExecution:** the execution information of a step within a JobExecution, including the status and counters such as the number of items read, written, skipped, or committed.
- **JobParameters:** the input data used to determine which job to run, such as the business date, a file code, or a data range. Parameters marked as identifying contribute to determining the JobInstance.

This distinction is very useful in operations. For example, a billing job for November 15 that failed can be restarted with the same identifying parameters to continue the instance for that day. The billing job for November 16 is a different instance because it is a different business period.

### JobRepository and ExecutionContext

The `JobRepository` stores metadata about jobs, steps, and executions. Thanks to this metadata, the application can look up the state, the run history, and the information needed for restart.

The `ExecutionContext` is where Spring Batch stores state that needs to be retained across executions, usually including checkpoint information used by a reader or a processing component. For example, a reader can save its read position so that when the job is restarted, it continues from the appropriate position instead of always starting over from the beginning.

Restartability depends on how the job and its components are configured. Having metadata does not automatically guarantee that every external side effect can be undone or safely resumed. If a job calls an external API, sends email, or writes to a system that does not participate in the same transaction, those actions may already have happened even though the database chunk was rolled back. Therefore, you need to design write operations to be idempotent, store a unique processing key, or have an appropriate reconciliation mechanism.

## 6. Which Model for Which Kind of Work?

Prefer online request processing when the caller needs the result immediately and the scope of work is small enough to finish within the request's time limit. For example:

- Retrieving profile or order information.
- Checking access permissions.
- Creating an order and returning the order code.
- Updating a user setting.

Consider batch processing when the work is large in volume, needs to run periodically, needs multiple steps, or needs monitoring and restart capabilities. For example:

- Importing hundreds of thousands of rows from a CSV file.
- Reconciling transactions between two systems.
- Calculating payroll or fees for all employees/accounts in a period.
- Generating periodic statements.
- Aggregating data and generating end-of-day reports.
- Cleaning or transforming data at large scale.

In practice, the two models often work together. A request can authenticate permissions, check parameters, create a processing request, and launch a batch job. The API returns a job code; another endpoint lets you view the status or download the result after the job completes.

When choosing an architecture, answer the following questions:

1. Does the caller need the business result right within the same request?
2. How large is the data volume and what is the expected processing time?
3. Can the work be divided into independent steps or chunks?
4. If the application stops midway, where does it need to continue from and which data has already been committed?
5. Can part of the work be rerun without creating duplicate side effects?
6. Who needs to monitor the status, progress, errors, and results of the work?

## 7. Points to Remember When Operating Batch

A batch job can run for a long time and process a lot of data, so the design needs to pay attention to several points:

- **Read data as a stream or page by page:** avoid loading an entire large data set into memory unless necessary.
- **Choose an appropriate chunk:** balance commit overhead, transaction hold time, and the amount of data to be reprocessed.
- **Define retry and skip clearly:** only retry errors that are likely to clear on their own; only skip records when the business allows it, and record the reason so it can be handled later.
- **Design for idempotency:** ensure that a restart or rerun does not create unintended duplicate transactions, notifications, or updates.
- **Prevent conflicting runs:** determine whether two jobs for the same period or the same data source are allowed to run concurrently.
- **Monitor with metadata and logs:** observe job/step status, run time, number of records read/written/failed, and the causes of failure.
- **Set operational limits:** take into account the batch window, database capacity, the speed of source/target systems, and the impact on online traffic.

A batch job running concurrently with an application serving requests can contend for CPU, memory, connection pool, and database resources. Therefore, a job that completes with correct logic can still affect API latency if its rate, level of parallelism, or run schedule is not controlled.

## Conclusion

Online request processing is optimized for operations that need a fast response to each request. Batch processing is optimized for work with a clear data scope, large volume, or a need to be monitored, divided, and recovered across multiple steps. In Spring Batch, `Job` and `Step` describe the process; chunks, transactions, the `JobRepository`, and the `ExecutionContext` support controlled data processing and progress management. A real-world system often uses an API to accept requests quickly, and then hands the long-running processing to a batch job when the business case fits.
