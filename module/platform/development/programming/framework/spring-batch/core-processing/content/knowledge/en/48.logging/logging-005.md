# Attaching Job Execution ID to Logs in Spring Batch

## 1. Why Do Batch Logs Need a Job Execution ID?

A Spring Batch application often runs the same job many times: on a daily schedule, on operator request, on restart after a failure, or when multiple data partitions run concurrently. If logs only include the job name, such as `importOrdersJob`, it is hard to tell which run a log line belongs to.

Example without an execution identifier:

~~~text
02:00:01 INFO  Import started
02:00:03 INFO  Loaded 1000 orders
02:00:05 WARN  Risk service timeout
02:00:06 INFO  Import started
02:00:09 INFO  Loaded 1000 orders
02:00:12 INFO  Import finished
02:00:13 ERROR Import failed
~~~

In this example, two runs interleave; it is impossible to determine with certainty which execution `Import finished` and `Import failed` belong to just by reading the message text.

After attaching the **job execution ID**:

~~~text
02:00:01 INFO  jobExecutionId=801 jobName=importOrdersJob event=job.started
02:00:03 INFO  jobExecutionId=801 jobName=importOrdersJob event=orders.loaded count=1000
02:00:05 WARN  jobExecutionId=801 jobName=importOrdersJob event=risk.timeout
02:00:06 INFO  jobExecutionId=802 jobName=importOrdersJob event=job.started
02:00:09 INFO  jobExecutionId=802 jobName=importOrdersJob event=orders.loaded count=1000
02:00:12 INFO  jobExecutionId=802 jobName=importOrdersJob event=job.finished
02:00:13 ERROR jobExecutionId=801 jobName=importOrdersJob event=job.failed
~~~

Now you can filter all logs by `jobExecutionId=801`, join them with Spring Batch metadata, and investigate which steps, chunks, retries, or service calls contributed to the failure.

In the context of **Spring Batch Core Processing → Logging**, attaching this ID aims to:

- **Accurately trace a single execution** even when multiple jobs share a name or run concurrently.
- **Link logs to JobRepository** via the `BATCH_JOB_EXECUTION.JOB_EXECUTION_ID` key.
- **Isolate errors by Step**, chunk, item, or data source without mixing two runs.
- **Distinguish restarts**: a single JobInstance can have multiple JobExecutions.
- **Support operations**: starting from an alert, trace logs, statuses, counters, exceptions, and the output of the relevant execution.

The job execution ID is **technical metadata issued by Spring Batch**, not a business data key. Never generate a custom UUID and label it `jobExecutionId` if that value does not correspond to JobRepository.

## 2. Distinguishing Common IDs

Spring Batch provides several levels of identification:

| Field | Meaning | Changes on Restart? | Example |
|---|---|---|---|
| `jobName` | Definition name of the job | Usually no | `importOrdersJob` |
| `jobInstanceId` | Logical work unit defined by job name and identifying JobParameters | Usually **no** when restarting the same instance | `200` |
| `jobExecutionId` | Key of **one run attempt** of a JobInstance | **Yes**: restart creates a new execution | `801`, then `805` |
| `stepName` | Step name inside the job | Usually no | `loadOrdersStep` |
| `stepExecutionId` | Key of **one run attempt of a Step** | Can change on subsequent runs/restarts | `3401` |
| `batchId` | Application-defined business batch key | Depends on domain; usually stays the same when restarting the same batch | `ORD-20261116` |
| `traceId` / `correlationId` | Links requests, messages, and service calls | Depends on tracing mechanism | `trace-...` |

Example of a JobInstance processing order batch `ORD-20261116`:

~~~text
JobInstance 200: importOrdersJob
identifying JobParameters: batchId=ORD-20261116
       |
       +-- JobExecution 801
       |       StepExecution 3401: loadOrdersStep
       |       Status: FAILED
       |
       +-- JobExecution 805 (restart)
               StepExecution 3419: loadOrdersStep
               Status: COMPLETED
~~~

The two runs share `jobInstanceId=200` but have different `jobExecutionId`s. Therefore:

- Use **jobExecutionId** when analyzing a single run and its exceptions.
- Use **jobInstanceId** or **batchId** when tying together the attempt history of the same logical job.
- Use **stepExecutionId** when multiple steps or partitions share the same name across multiple executions.
- Use **traceId** for cross-service calls; it can coexist with Spring Batch IDs.

Do not place `jobExecutionId` inside `JobParameters` to identify an instance: the framework generates this ID when registering a JobExecution. Adding a new identifying parameter on retry can accidentally create a **different JobInstance** and fail to resume from the old checkpoint.

## 3. When Is the Job Execution ID Assigned?

Spring Batch persists JobExecution in **JobRepository** and assigns the execution key. When a job actually starts through standard infrastructure, `JobExecution.getId()` is already populated inside `JobExecutionListener` callbacks.

Overview flow:

~~~text
Scheduler / REST endpoint / CLI
             |
             v
       JobLauncher.run(...)
             |
             v
JobRepository creates JobExecution
  - assigns jobExecutionId
  - links JobInstance
             |
             v
JobExecutionListener.beforeJob(...)
             |
             v
        StepExecution
             |
             v
      Reader -> Processor -> Writer
             |
             v
JobExecutionListener.afterJob(...)
             |
             v
       JobRepository saves status
~~~

Logs may be emitted **before JobExecution is created**, such as when the application receives a batch launch request or validates parameters. Those logs do not yet have a `jobExecutionId`; use a **requestId/correlationId** to connect them to the `job.created` log once JobRepository returns the ID.

Example:

~~~text
event=batch.launch.requested requestId=req-27 jobName=importOrdersJob
event=batch.launch.accepted  requestId=req-27 jobExecutionId=801
event=job.started             jobExecutionId=801
~~~

If the launcher operates asynchronously, `run(...)` may return before the job finishes. The ID and status returned at that moment are not guaranteed to be the final outcome. The ID remains the key to track execution later via JobExplorer.

## 4. Basic Approach: Logging the ID Directly in Messages

Inside callbacks that already receive a `JobExecution` object, the simplest approach is passing the ID as a logger argument:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;

public class SimpleJobLogListener implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(SimpleJobLogListener.class);

    @Override
    public void beforeJob(JobExecution execution) {
        log.info("event=job.started jobExecutionId={} jobName={}",
                execution.getId(),
                execution.getJobInstance().getJobName());
    }

    @Override
    public void afterJob(JobExecution execution) {
        log.info("event=job.finished jobExecutionId={} status={}",
                execution.getId(),
                execution.getStatus());
    }
}
~~~

The advantage is simplicity, zero reliance on MDC configuration, and ease of testing with basic loggers. The drawback is that every `log.info(...)` call across readers, processors, writers, and service classes must explicitly receive/pass the ID. It is easy to miss places, making logs hard to filter.

When you want the ID to appear automatically in every log line on a processing thread, use SLF4J's **Mapped Diagnostic Context (MDC)** with a supporting logging backend, typically Logback.

## 5. What Is MDC and How Does It Work?

**MDC** is a key/value map bound to the current thread's logging context. When a log entry is written, patterns or JSON encoders can pull these values into the log record without code passing them in every statement.

Example:

~~~java
import org.slf4j.MDC;

MDC.put("jobExecutionId", "801");
MDC.put("jobName", "importOrdersJob");

log.info("Reading input file");
log.info("Writing approved orders");

MDC.remove("jobExecutionId");
MDC.remove("jobName");
~~~

If the Logback pattern includes `%X{jobExecutionId}`, both log lines above contain `jobExecutionId=801`.

**Key point:** MDC is normally bound to a **thread**, not automatically bound to a JobInstance or JobExecution. This creates three requirements:

1. **Set the right values** when a thread begins processing an execution.
2. **Clean up values in `finally` or end callbacks** so reused pool threads do not carry old IDs into new jobs.
3. **Propagate MDC to other threads** if steps, task executors, async processors, or workers use thread pools.

MDC does not turn JobRepository into a log store. It only helps the logger attach context; actual state metadata remains in Spring Batch's repository.

### Why Not Use a Static Variable to Hold the ID?

~~~java
// Do not use:
static Long currentJobExecutionId;
~~~

Multiple JobExecutions can run simultaneously in one JVM. A global variable gets overwritten and causes logs from job A to carry job B's ID. Thread-local MDC or explicit parameter passing through well-designed components avoids this bug.

## 6. Attaching MDC via JobExecutionListener and StepExecutionListener

In a batch application, **JobExecutionListener** is suited for logging job start/finish events; **StepExecutionListener** is suited for attaching context while a Step's logic executes.

The example below uses a single listener implementing both interfaces:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class BatchExecutionMdcListener
        implements JobExecutionListener, StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(BatchExecutionMdcListener.class);

    private static String value(Object object) {
        return object == null ? "unknown" : object.toString();
    }

    @Override
    public void beforeJob(JobExecution execution) {
        logJobEvent("job.started", execution);
    }

    @Override
    public void afterJob(JobExecution execution) {
        logJobEvent("job.finished", execution);
    }

    private void logJobEvent(String event, JobExecution execution) {
        // Set MDC only within this callback's scope.
        // MDC.MDCCloseable automatically removes entries on try exit.
        try (MDC.MDCCloseable id =
                     MDC.putCloseable("jobExecutionId",
                             value(execution.getId()));
             MDC.MDCCloseable name =
                     MDC.putCloseable("jobName",
                             execution.getJobInstance().getJobName())) {

            log.info("event={} status={}", event, execution.getStatus());
        }
    }

    @Override
    public void beforeStep(StepExecution stepExecution) {
        JobExecution jobExecution = stepExecution.getJobExecution();

        MDC.put("jobExecutionId", value(jobExecution.getId()));
        MDC.put("jobInstanceId",
                value(jobExecution.getJobInstance().getId()));
        MDC.put("jobName",
                jobExecution.getJobInstance().getJobName());
        MDC.put("stepExecutionId", value(stepExecution.getId()));
        MDC.put("stepName", stepExecution.getStepName());

        log.info("event=step.started");
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        try {
            log.info(
                    "event=step.finished status={} read={} write={} skip={}",
                    stepExecution.getStatus(),
                    stepExecution.getReadCount(),
                    stepExecution.getWriteCount(),
                    stepExecution.getSkipCount());
        } finally {
            // Remove only keys managed by this listener.
            MDC.remove("stepName");
            MDC.remove("stepExecutionId");
            MDC.remove("jobName");
            MDC.remove("jobInstanceId");
            MDC.remove("jobExecutionId");
        }
        return null; // Do not alter the Step's ExitStatus.
    }
}
~~~

The two job callbacks set MDC **only for the duration of logging the job event**. The two Step callbacks set MDC for the Step's execution window under the standard sequential model. Consequently, logs from readers, processors, and writers running on **the same thread** as the Step pick up `jobExecutionId` and `stepExecutionId` from MDC.

This design deliberately avoids assuming `beforeJob` and Steps always execute on the same thread. For async job flows, partitions, or thread pools, see how to propagate MDC in the sections below.

**Lifecycle note:** `afterStep` is the normal cleanup point, but if the process is killed or the framework cannot invoke the callback due to a fatal error, that cleanup path will not run. For code that spawns its own threads/tasks, use `try/finally` to clear or restore MDC at task boundaries. Never call `MDC.clear()` indiscriminately if the same thread also holds a `traceId` or context from another observability library.

### Registering the Listener on Job and Step

Assuming `orderReader`, `orderProcessor`, `orderWriter`, `jobRepository`, and `transactionManager` beans are already configured:

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> orderReader,
        ItemProcessor<OrderRow, ImportedOrder> orderProcessor,
        ItemWriter<ImportedOrder> orderWriter,
        BatchExecutionMdcListener batchLoggingListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderRow, ImportedOrder>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .listener((StepExecutionListener) batchLoggingListener)
            .build();
}

@Bean
public Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep,
        BatchExecutionMdcListener batchLoggingListener) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(importOrdersStep)
            .listener((JobExecutionListener) batchLoggingListener)
            .build();
}
~~~

`OrderRow` and `ImportedOrder` are illustrative domain types; the configuration snippet above must be placed in an appropriate `@Configuration` class. The builder syntax illustrates Spring Batch 5+ APIs.

Casting to `JobExecutionListener` and `StepExecutionListener` disambiguates the `.listener(...)` overload when a class implements both interfaces. If different Steps use different listeners or the project has its own convention, keep MDC key naming consistent.

## 7. Displaying Job Execution ID with Logback

Putting MDC on the thread is only half the job; the logger must be configured to **emit MDC keys in logs**. With Spring Boot using Logback, declare a custom pattern in `logback-spring.xml`:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>
                %d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX}
                %-5level
                [thread=%thread]
                [jobExecutionId=%X{jobExecutionId:-none}]
                [stepExecutionId=%X{stepExecutionId:-none}]
                [jobName=%X{jobName:-none}]
                %logger{36} - %msg%n
            </pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

This example deliberately uses a standalone XML snippet to highlight MDC fields; in a project that already has `logback-spring.xml`, integrate the pattern into the existing appender while keeping existing profiles, async appenders, and rotation policies.

The `%X{jobExecutionId:-none}` syntax reads the key from MDC; if absent, it renders `none`. Expected log output:

~~~text
2026-11-16T02:00:03.120+07:00 INFO
[thread=main] [jobExecutionId=801]
[stepExecutionId=3401] [jobName=importOrdersJob]
c.example.OrderProcessor - Reading order O001
~~~

Seeing `none` is normal for application startup logs or requests arriving before a JobExecution is created. Never assign a fake ID to events that do not yet belong to any execution.

### Structured JSON Logging

In centralized log aggregation platforms, **JSON logs** are convenient because `jobExecutionId` becomes a queryable field. Example desired log format:

~~~json
{
  "timestamp": "2026-11-16T02:00:03.120+07:00",
  "level": "INFO",
  "logger": "com.example.batch.OrderProcessor",
  "message": "order processed",
  "jobName": "importOrdersJob",
  "jobExecutionId": "801",
  "jobInstanceId": "200",
  "stepName": "importOrdersStep",
  "stepExecutionId": "3401",
  "orderId": "O001"
}
~~~

This is an example of the desired log structure, **not the default output of every Spring Boot version**. With a JSON encoder or structured logging supported by your project, configure inclusion of MDC fields and inspect actual emitted logs. Some encoders include all MDC keys automatically at the root, some require allowlisting fields, and some nest MDC inside a nested object.

Field naming conventions, ID formats, and timezones should align across the application, log pipeline, and dashboard queries. If `jobExecutionId` is emitted as a string, queries should treat it as a string rather than letting collectors vary data types.

## 8. Accessing the ID in Code Inside a Step

In `StepExecutionListener`, you receive `StepExecution` directly. In Step-scoped beans, Spring Batch also provides **StepContext** for tasks needing metadata access.

Example when code executes on a thread with a Spring Batch **StepContext**:

~~~java
import java.util.Optional;

import org.springframework.batch.core.scope.context.StepContext;
import org.springframework.batch.core.scope.context.StepSynchronizationManager;

public final class BatchExecutionIds {

    private BatchExecutionIds() {
    }

    public static Optional<Long> currentJobExecutionId() {
        StepContext context = StepSynchronizationManager.getContext();
        if (context == null) {
            return Optional.empty();
        }
        return Optional.ofNullable(
                context.getStepExecution()
                        .getJobExecution()
                        .getId());
    }
}
~~~

This helper is useful inside components with a valid Step context, but should not be called arbitrarily from schedulers, background callbacks, or manually spawned threads: **StepSynchronizationManager is bound to the execution thread**, not a global store.

In components that frequently need the ID, passing it via method parameters or injecting an appropriately scoped object is better than reading context ad hoc. Likewise, never store a mutable `currentExecutionId` field on a singleton processor when multiple executions can run concurrently.

### Adding an Item Key for a Short Log Scope

For an item requiring investigation, you can set an MDC key for a tight scope:

~~~java
import org.slf4j.MDC;

public ImportedOrder process(OrderRow order) {
    try (MDC.MDCCloseable ignored =
                 MDC.putCloseable("orderId", order.orderId())) {

        log.debug("event=order.processing");
        return transform(order);
    }
}
~~~

`transform` is an illustrative business method. Upon exiting the `try` block, the `orderId` MDC key is removed even if the processor throws an exception. This sample assumes no outer scope uses the **same key** `orderId`; if nested scopes share the key name, save and restore the prior value rather than just removing it.

Never put full item contents, payment card numbers, tokens, or personal data into MDC. Even business keys should be evaluated against sensitivity levels and the system's logging policy.

## 9. MDC and Multiple Threads in Spring Batch

A common misconception is thinking `MDC.put(...)` in `beforeJob` will automatically appear in every Step, partition, and async request. In practice, standard MDC relies on **ThreadLocal**: other threads do not receive the new context unless explicitly propagated.

Example:

~~~text
JobLauncher thread A
  JobExecution 801
  MDC(jobExecutionId=801)
      |
      +-- Step running on thread A
      |     --> Logs normally see the ID
      |
      +-- Worker thread B (task executor)
      |     --> Does not inherit thread A's MDC by default
      |
      +-- Remote worker process C
            --> Must pass correlation/context across the protocol
~~~

For a Step using a `taskExecutor` to run chunks in parallel, a standard approach is using a **TaskDecorator** that copies MDC at task creation time and **restores the worker thread's previous MDC** after the task finishes.

### TaskDecorator to Propagate and Restore MDC

~~~java
import java.util.Map;

import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable delegate) {
        // Snapshot from the task-submitting thread.
        Map<String, String> callingContext =
                MDC.getCopyOfContextMap();

        return () -> {
            // Worker thread may have been reused from the pool.
            Map<String, String> previousContext =
                    MDC.getCopyOfContextMap();

            try {
                if (callingContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(callingContext);
                }

                delegate.run();
            } finally {
                // Prevent this batch's ID from leaking into the next task.
                if (previousContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previousContext);
                }
            }
        };
    }
}
~~~

The critical detail is capturing `callingContext` **before the task runs** and restoring the previous context in `finally`. Calling `MDC.setContextMap()` without restoring it causes the thread pool to retain stale IDs for a task from another job.

Registering the decorator on a `ThreadPoolTaskExecutor`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Bean
public TaskExecutor batchTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(32);
    executor.setThreadNamePrefix("batch-worker-");
    executor.setTaskDecorator(new MdcTaskDecorator());
    executor.initialize();
    return executor;
}
~~~

For a multi-threaded Step, configure `taskExecutor` on the step builder and ensure the reader/writer and any stateful components are thread-safe for concurrent access. **TaskDecorator only solves logging context**; it does not make a reader thread-safe or guarantee transaction/checkpoint safety.

If the application uses other executors for `@Async`, `CompletableFuture`, `AsyncItemProcessor`, or async HTTP clients, inspect where tasks are actually submitted and apply context propagation on **that executor**. A decorator on one executor does not automatically apply to others.

### When Copying MDC Is Still Not Enough

If a task is submitted **before** the ID is placed into MDC or a callback executes on a thread bypassing the decorated executor, the snapshot will lack the ID. In that case:

1. Pass the ID as a data field inside the internal command/request.
2. Set MDC at the worker/task entry point based on that field.
3. Run the logic inside `try/finally` to clear context.
4. Integrate with trace context propagation if the app already uses OpenTelemetry/Micrometer Tracing.

Do not blindly copy the entire MDC across system boundaries: forward only permitted, meaningful fields of bounded size.

## 10. Multi-Threaded Steps, Partitioning, and Remote Chunking

Spring Batch supports multiple parallelism models, and each needs accurate IDs at execution boundaries.

| Execution Mode | Where to Set Logging Context | Recommended IDs |
|---|---|---|
| Sequential Step | StepExecutionListener on the Step thread | jobExecutionId, stepExecutionId, stepName |
| Multi-threaded chunk via TaskExecutor | Step listener + TaskDecorator on chunk executor | Current JobExecution and StepExecution IDs |
| Parallel flows | Listener on each Step running on its respective thread | One jobExecutionId, multiple stepExecutionIds |
| Local partitioning | Context in worker Steps/partitions | jobExecutionId and the partition's own stepExecutionId |
| Remote partitioning | Pass metadata to workers or read StepExecution from shared repository | ID matching the assigned execution |
| Remote chunking | Message headers/correlation for chunk and JobExecution | jobExecutionId, stepExecutionId, and messageId if applicable |

### Partitioning Log Example

~~~text
jobExecutionId=801 stepExecutionId=3401 stepName=load:partition0 read=5000
jobExecutionId=801 stepExecutionId=3402 stepName=load:partition1 read=5000
jobExecutionId=801 stepExecutionId=3403 stepName=load:partition2 read=5000
~~~

All belong to the same JobExecution, yet each partition has its own StepExecution. If only `stepName=load` is attached, logs mix together and you can no longer tell which partition failed.

### Passing Context via Messages

In remote chunking, workers receiving messages may run in another JVM/process. Manager MDC does not travel with the message automatically. Illustrative envelope:

~~~json
{
  "headers": {
    "correlationId": "req-27",
    "jobExecutionId": "801",
    "stepExecutionId": "3401",
    "chunkId": "chunk-18"
  },
  "payload": {
    "orders": ["O100", "O101"]
  }
}
~~~

Workers should only use validated headers matching the assigned work. If workers share the JobRepository, they can verify execution IDs via metadata; if repositories are separate, maintain explicit correlation and never assume numeric keys in two databases share the same meaning.

The worker receives the request, sets MDC for the message-handling scope, logs, and restores the previous MDC. When sending a response, preserve `correlationId` and the chunk ID so the manager correlates results with the original request.

**Never use jobExecutionId as the unique key for a single message**: one JobExecution can emit many chunks/messages. A message ID or chunk ID is still required for disambiguation and idempotency.

## 11. Attaching IDs to Chunk, Retry, Skip, and Error Events

The job execution ID is most valuable when key logs share a consistent field layout:

~~~text
event=chunk.completed jobExecutionId=801 stepExecutionId=3401 read=100 write=98
event=item.skipped jobExecutionId=801 stepExecutionId=3401 reason=INVALID_AMOUNT
event=api.retry jobExecutionId=801 stepExecutionId=3401 attempt=2 dependency=risk-service
event=step.failed jobExecutionId=801 stepExecutionId=3401 errorCode=DB_TIMEOUT
~~~

With the Step listener and MDC configured, log statements can focus purely on **the event and outcome**, as `jobExecutionId` is added automatically by the log encoder.

Example using `ChunkListener` to log checkpoint/chunk events:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.scope.context.ChunkContext;

public class BatchChunkLoggingListener implements ChunkListener {

    private static final Logger log =
            LoggerFactory.getLogger(BatchChunkLoggingListener.class);

    @Override
    public void afterChunk(ChunkContext context) {
        log.debug("event=chunk.committed stepName={}",
                context.getStepContext().getStepName());
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        log.warn("event=chunk.failed stepName={}",
                context.getStepContext().getStepName());
    }
}
~~~

Under a sequential Step with the MDC listener registered, both messages carry `jobExecutionId`. In a multi-threaded Step, a decorator or worker-thread context setup is required to achieve the same result.

Do not log INFO after **every chunk** unnecessarily: jobs with millions of chunks generate massive log volume. Use DEBUG for normal chunks, INFO for record-count milestones, and WARN/ERROR when skips or rollbacks exceed thresholds. Metrics are usually better suited than dense logs for tracking throughput.

### Distinguishing Retries from Multiple Executions

When retrying an item within the same JobExecution, `jobExecutionId` **does not change**. `attempt=1/2/3` is the attempt number of retry logic, not another JobExecution.

When restarting after `FAILED`/`STOPPED`, the new JobExecution gets a different ID even for the same business data. Therefore, when investigating duplicates or API side effects, preserve both the business `batchId`/idempotency key and `jobExecutionId`.

### Failures Before the afterStep Callback

Never rely solely on `step.finished` logs to know whether a Step completed. If the process crashes, the callback does not run and the final log may be missing. Monitoring must combine JobRepository metadata, heartbeats, and process health; logs serve as supporting diagnostic evidence.

## 12. Tracing Restarts from JobRepository and Logs

Suppose the first run failed and was restarted:

~~~text
jobInstanceId=200 jobExecutionId=801 event=job.started
jobInstanceId=200 jobExecutionId=801 event=step.failed
jobInstanceId=200 jobExecutionId=801 event=job.finished status=FAILED

jobInstanceId=200 jobExecutionId=805 event=job.started
jobInstanceId=200 jobExecutionId=805 event=job.finished status=COMPLETED
~~~

To view all executions of a JobInstance, query the default metadata tables:

~~~sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
  ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
WHERE ji.JOB_INSTANCE_ID = :jobInstanceId
ORDER BY je.JOB_EXECUTION_ID;
~~~

Sample result:

| JOB_INSTANCE_ID | JOB_EXECUTION_ID | STATUS |
|---:|---:|---|
| 200 | 801 | FAILED |
| 200 | 805 | COMPLETED |

This is a read-only reporting query; table names and parameter syntax must match your actual database. To isolate the failing Step:

~~~sql
SELECT
    STEP_EXECUTION_ID,
    JOB_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    READ_SKIP_COUNT,
    PROCESS_SKIP_COUNT,
    WRITE_SKIP_COUNT
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
~~~

Once `JOB_EXECUTION_ID` and `STEP_EXECUTION_ID` are identified, filter the corresponding log records. Never use job name as the sole filter when multiple executions of the same job run concurrently.

### Practical Investigation Steps

1. Receive an alert with `jobName`, `jobExecutionId`, and status.
2. Look up the JobExecution in JobRepository by `jobExecutionId`.
3. Identify the failing StepExecution and its counters/exceptions.
4. Filter logs by `jobExecutionId`, then narrow down by `stepExecutionId`.
5. If the error involves HTTP/Kafka, use `traceId`, `correlationId`, or messageId to trace across services.
6. Reconcile output by `batchId` after remediation; completion logs alone do not prove data completeness.

## 13. Distinguishing MDC from Tracing and Metric Labels

These three contexts are often used together but serve different purposes:

| Tool | Primary Role | Appropriate IDs |
|---|---|---|
| **Structured logs/MDC** | Find detailed events and tie them to an execution | jobExecutionId, stepExecutionId, traceId, approved batchId |
| **Distributed tracing** | Observe activity chains across threads/services | traceId, spanId; Batch IDs may be added as controlled span attributes |
| **Metrics** | Aggregate counts, latency, error rates | jobName, stepName, status, and low-cardinality labels |

**Do not put jobExecutionId/stepExecutionId as Prometheus metric labels by default.** Every execution creates a new time series, causing cardinality and retention problems. Dynamic IDs belong in logs, traces, or audit details.

If the application uses Micrometer Tracing/OpenTelemetry, MDC may already hold `traceId` and `spanId`. The listener in the example removes only batch-specific keys; never wipe the entire MDC or overwrite tracing field names.

Across external APIs, `jobExecutionId` does not replace `traceparent` or tracing propagation mechanisms. You can log both IDs together, while trace context propagation must use the mechanism supported by your tracing library to preserve span linkage.

## 14. Keeping Logs Structured Without Exposing Data

Fields to keep:

| Field | Example | Suitability |
|---|---|---|
| `jobExecutionId` | `801` | Almost always useful |
| `jobInstanceId` | `200` | Useful for restarts |
| `jobName` | `importOrdersJob` | Filtering and dashboards |
| `stepExecutionId` | `3401` | Useful with parallel Steps/partitions |
| `stepName` | `validateOrderStep` | Explains processing location |
| `batchId` | `ORD-20261116` | Use only if it contains no sensitive data |
| `event` | `chunk.committed` | Easy to filter and aggregate |
| `reasonCode` | `INVALID_AMOUNT` | Better than logging raw invalid values |
| `traceId` | Trace ID | Cross-service tracing |

Never put full JobParameters, raw records, access tokens, secrets, passwords, or PII into MDC. MDC is typically attached automatically to **every log line on the thread**, so placing a single sensitive value there by mistake can leak it across many events.

For exception messages:

~~~java
log.error("event=order.import.failed reasonCode={} recordKey={}",
        reasonCode, safeRecordKey, exception);
~~~

Here `safeRecordKey` must be a key permitted in logs. Exception messages and stack traces can still embed URLs, queries, or sensitive payloads generated by libraries; review redaction and logging policies accordingly.

There is no need to log every successful item at INFO when a batch processes millions of records. Log start, finish, milestones, controlled skips, and errors; emit counts via metrics or audit records.

## 15. Testing MDC Attachment and Cleanup

To prevent logs from carrying wrong IDs, test both **setting the right context** and **cleaning it up after the Step finishes**. You can unit-test the listener without starting all of Spring Batch:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.StepExecution;

class BatchExecutionMdcListenerTest {

    private final BatchExecutionMdcListener listener =
            new BatchExecutionMdcListener();

    @AfterEach
    void cleanup() {
        MDC.clear();
    }

    @Test
    void attachesIdsDuringStepAndRemovesThemAfterward() {
        JobInstance jobInstance = mock(JobInstance.class);
        when(jobInstance.getId()).thenReturn(200L);
        when(jobInstance.getJobName()).thenReturn("importOrdersJob");

        JobExecution jobExecution = mock(JobExecution.class);
        when(jobExecution.getId()).thenReturn(801L);
        when(jobExecution.getJobInstance()).thenReturn(jobInstance);

        StepExecution stepExecution = mock(StepExecution.class);
        when(stepExecution.getId()).thenReturn(3401L);
        when(stepExecution.getStepName()).thenReturn("importOrdersStep");
        when(stepExecution.getJobExecution()).thenReturn(jobExecution);

        listener.beforeStep(stepExecution);

        assertEquals("801", MDC.get("jobExecutionId"));
        assertEquals("200", MDC.get("jobInstanceId"));
        assertEquals("3401", MDC.get("stepExecutionId"));
        assertEquals("importOrdersStep", MDC.get("stepName"));

        listener.afterStep(stepExecution);

        assertNull(MDC.get("jobExecutionId"));
        assertNull(MDC.get("jobInstanceId"));
        assertNull(MDC.get("stepExecutionId"));
        assertNull(MDC.get("stepName"));
    }
}
~~~

This example uses Mockito/JUnit 5 and assumes the test logging backend has MDC active, such as Logback. It verifies listener logic, **not that a Logback pattern or JSON encoder actually outputs those fields**. Add a dedicated test reading log events or backend output when you need to verify log formatting.

### Testing Context Propagation via TaskDecorator

A unit test can set `MDC.put("jobExecutionId","801")` on the submitting thread, call `decorate(...)`, run the Runnable on another thread, assert the Runnable sees `"801"`, and after the Runnable finishes assert the worker thread's previous MDC is restored.

Cases to cover:

- Submitting thread has MDC and worker has no MDC.
- Worker already has a different MDC; decorator must restore it properly after the task.
- Runnable throws an exception; `finally` still cleans up context.
- Submitting thread has no MDC; worker must not keep an old ID.
- Two consecutive tasks from JobExecution 801 and 802 on the same worker thread do not mix IDs.

When using a real executor, synchronize tests with primitives like `CountDownLatch` or `Future.get` with a timeout. Avoid `Thread.sleep` to guess when a task has run.

### Integration Testing in Spring Batch

With `spring-batch-test` and a dedicated test database, run a small Job via `JobLauncherTestUtils`, then:

1. Verify `JobExecution.getId()` was assigned.
2. Read `StepExecution.getId()` from the corresponding execution.
3. Capture logs emitted in processors/writers or listeners and check that `jobExecutionId` matches the real ID.
4. Run another JobExecution and confirm logs do not reuse the old ID.
5. For a multi-threaded Step, confirm worker logs actually carry the right ID.
6. For a restart of the same JobInstance, confirm the new JobExecution has a different ID and logs trace both attempts.

With Logback, a test appender can **snapshot the MDC map right when the event is logged**. If storing raw logging events for later assertion, keep in mind encoders/appenders may resolve MDC lazily; do not let clearing MDC before asserting mislead test results.

## 16. Common Pitfalls When Attaching Job Execution ID

**Logging only the job name.** Multiple executions with the same name can overlap. Add `jobExecutionId` and, when needed, `stepExecutionId`.

**Using jobInstanceId instead of jobExecutionId.** Restarts of the same JobInstance will mix logs together. Keep both fields when historical investigation is needed.

**Generating jobExecutionId manually.** That ID cannot be reconciled with JobRepository. Always use the ID provided by `JobExecution.getId()`.

**Storing the ID in a mutable static field.** Concurrent jobs overwrite each other. Use thread-local MDC, scoped context, or parameter passing.

**Setting MDC without updating the logging pattern.** Logs still omit the ID. Configure `%X{jobExecutionId}` or a structured encoder supporting MDC.

**Setting MDC only in beforeJob and assuming all worker threads see it.** MDC does not automatically cross executors or JVMs. Use TaskDecorator or correlation messages.

**Forgetting to clear MDC after processing.** Reused thread-pool threads cause new execution logs to carry old IDs. Clear or restore in `finally`.

**Calling MDC.clear() in a shared execution context.** That can wipe out `traceId`/`spanId` from observability libraries. Remove only keys owned by your app or restore the original snapshot.

**Changing identifying JobParameters on restart just to get a new ID.** Spring Batch automatically creates a new JobExecution ID. Altering identifying parameters creates a new JobInstance and breaks checkpoint resumption.

**Using jobExecutionId as a metric label.** Time-series counts grow with every run; keep dynamic IDs in logs, traces, and audits.

**Putting full items or JobParameters into MDC.** Risks leaking PII/secrets and bloating logs. Pick only safe, necessary fields.

**Assuming completion logs always exist.** Process crashes prevent `afterJob`/`afterStep` from running. Cross-check JobRepository and liveness checks before drawing conclusions.

**Failing to distinguish partitions and StepExecutions.** A single job has multiple StepExecutions; `stepExecutionId` pinpoints the exact worker.

## 17. Practical Implementation Checklist

To standardize logging for a Spring Batch application:

1. **Standardize field conventions:** `jobExecutionId`, `jobInstanceId`, `jobName`, `stepExecutionId`, `stepName`; use consistent types and naming across the system.
2. **Attach listeners:** log job events, set MDC on Steps, and clean up after Steps.
3. **Configure the logging backend:** ensure Logback patterns or JSON encoders actually output MDC fields.
4. **Verify parallel paths:** TaskExecutor, AsyncItemProcessor, partitions, remote chunking, and callbacks require context propagation at the exact boundary.
5. **Preserve restart linkage:** log both `jobInstanceId` and `jobExecutionId`; keep a business `batchId` if safe.
6. **Log purposefully:** start, finish, milestones, skips, retries, rollbacks, and exceptions with reason codes; avoid per-item spam.
7. **Correlate with JobRepository:** use IDs from logs to look up the exact JobExecution, StepExecution, counters, and status.
8. **Add tests:** MDC set/remove, pool thread reuse, log patterns, two concurrent executions, restarts, and failure states.
9. **Govern data:** avoid PII/secrets and high-cardinality metric labels.
10. **Define investigation runbooks:** starting from an alert or batch ID, filter logs by execution and step, then join external service traces when needed.

The core takeaway of **attaching job execution IDs** is that every critical log must trace back to **an actual run in JobRepository**. In Spring Batch, combining listeners, MDC, logger configuration, and proper context propagation lets you accurately trace sequential Steps, multi-threaded Steps, and restarts while keeping clear boundaries between technical metadata, business keys, and distributed tracing.
