# Executor observation in Spring Boot

When Spring Boot offloads work to a thread pool, the initial request may finish before the background work completes. If you only observe HTTP requests, you see the response return, but you do not know how long the task took, whether it waited in a queue, or whether it failed on a worker thread. **Executor observation** adds visibility into the task lifecycle: wait time, execution time, outcome, errors, and associated context. It helps distinguish queue delay from execution time, detect pool saturation, and correlate tasks with the requests that initiated them.

In the **SPRING_BOOT_OBSERVABILITY** module, Executor observation belongs to the **Messaging and task observability** chapter, combining Micrometer Observation, metrics, logs, and distributed tracing. This lesson focuses on observing tasks through `Executor`/`ThreadPoolTaskExecutor`, integrating `ObservationRegistry`, propagating trace/MDC context across thread boundaries, measuring queue and pool health, handling exceptions/cancellations/rejections, avoiding duplicate instrumentation, and testing in a Spring environment.

## Learning objectives

1. Describe the task lifecycle from submission, queuing, and execution to completion.
2. Distinguish queue wait time, task execution time, and end-to-end duration.
3. Use Micrometer Observation to describe task operations.
4. Configure Spring `ThreadPoolTaskExecutor` and `TaskDecorator`.
5. Propagate tracing/MDC context properly across thread boundaries.
6. Monitor pool size, active threads, queue depth, and rejected tasks.
7. Handle exceptions, cancellation, timeouts, and shutdown.
8. Avoid duplicate spans/metrics when the executor is already instrumented.
9. Write tests for Observation lifecycle, context restoration, and executor saturation.

## 1. Task lifecycle and three types of duration

An executor accepts a task and decides whether it runs immediately or waits in a queue.

~~~text
Caller
  └─ submit(task)
       ├─ accepted -> worker available -> execute
       ├─ accepted -> queue -> worker takes task -> execute
       └─ rejected -> rejection policy
  Task execution
       ├─ completed
       ├─ failed with exception
       └─ cancelled/interrupted
~~~

| Duration | Start/end | Meaning |
| --- | --- | --- |
| Queue wait | Task enqueue → worker starts | Time the task spent waiting |
| Execution time | Worker starts → task finishes | Time spent running code |
| End-to-end task time | Submit → task finishes | Total time from submission |

For example, if a task is submitted at 10:00:00.000, the worker starts at 10:00:00.250, and it finishes at 10:00:01.000: queue wait is 250 ms, execution is 750 ms, total is 1,000 ms. Measuring only execution time misses backlog; measuring only total time makes it hard to tell queue delay apart from slow code.

Executor metrics describe the pool: active threads, pool size, queue depth, completed task count. Task Observation describes a specific operation: name, duration, outcome, and context. Both types of data complement each other.

## 2. Task lifecycle and context boundaries

~~~mermaid
sequenceDiagram
    participant Caller
    participant Executor
    participant Queue
    participant Worker
    participant Observation
    Caller->>Observation: Capture task context
    Observation->>Executor: submit(task)
    Executor->>Queue: enqueue if no worker
    Queue-->>Worker: dequeue task
    Worker->>Observation: Activate task scope
    Worker->>Worker: Execute business logic
    Worker->>Observation: Record outcome/error and stop
    Observation-->>Caller: Future completion
~~~

A task may run on a different thread than the caller. `ThreadLocal` values from the caller do not automatically follow the task. Tracing context, MDC, and other context must be captured and restored using an appropriate mechanism.

With fire-and-forget, the caller submits the task and moves on; the HTTP Observation may finish before the task. With `Future`/`CompletableFuture`, the caller may await the result or compose continuations. If the task runs independently after the response, create a separate task span/Observation and link it to the source context according to business semantics.

If the task is a direct continuation of the request, a child span may fit. If the task runs much later, has multiple triggers, or aggregates multiple messages, a span link may be more suitable. Do not keep an HTTP server span open solely to wait for a background task when the API contract does not require it.

## 3. Configuring ThreadPoolTaskExecutor

Spring provides `ThreadPoolTaskExecutor` to configure a pool as a bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class TaskExecutorConfiguration {
    @Bean("applicationTaskExecutor")
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(12);
        executor.setQueueCapacity(200);
        executor.setKeepAliveSeconds(60);
        executor.setThreadNamePrefix("app-task-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }
}
~~~

Values are illustrative only. Pool sizing must be based on workload, CPU/IO profile, downstream capacity, and available resources. A large queue can hide saturation and increase queue wait; a large max pool can overload databases or remote services.

- Core pool size: baseline number of workers retained per policy.
- Max pool size: maximum worker limit.
- Queue capacity: number of tasks that can wait.
- Keep-alive: how long workers above core can stay idle before reclamation.
- Rejection policy: behavior when capacity is exhausted.

With `ThreadPoolExecutor`, tasks are typically queued once core threads are busy; the pool only expands past core toward max when the queue is full. Therefore, queue capacity strongly affects whether the pool ever scales up.

### 3.1. Rejection policies

- `AbortPolicy`: throws `RejectedExecutionException`.
- `CallerRunsPolicy`: the caller runs the task itself, creating backpressure but potentially forcing request threads to do heavy work.
- `DiscardPolicy`: silently drops the task.
- `DiscardOldestPolicy`: drops the oldest task in the queue.

Do not pick a discard policy for critical work without detection and compensation mechanisms. Rejections must be recorded and handled according to business semantics.

## 4. Micrometer Observation for tasks

Micrometer Observation provides a unified lifecycle. An Observation can generate metrics/spans via configured handlers. Example custom task observation:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Component;

@Component
public class ObservedTaskRunner {
    private final ObservationRegistry registry;

    public ObservedTaskRunner(ObservationRegistry registry) {
        this.registry = registry;
    }

    public void run(String taskType, Runnable task) {
        Observation.createNotStarted("application.task", registry)
                .lowCardinalityKeyValue("task.type", taskType)
                .observe(task);
    }
}
~~~

### 4.1. Where should Observation be placed?

Place observation at a meaningful operation boundary:
- Submit boundary if measuring submit-to-completion;
- Worker boundary if measuring execution;
- Business task method if naming by business operation.

Do not place observations with the same name at the caller, executor wrapper, and worker without clearly defining which phase each span represents. If you need separate queue wait time, measure it separately rather than creating multiple redundant spans covering the entire task.

### 4.2. Low-cardinality task metadata

Appropriate tags can be `task.type` (`email-delivery`, `invoice-export`), `task.queue` (`notifications`, `reports`), and `task.outcome` (`success`, `failure`, `cancelled`). Avoid task IDs, user IDs, file names, message bodies, and exception messages as metric tags. If a task ID is needed to locate a specific task, use trace/span context or governed log fields.

## 5. Context propagation through executors

MDC and tracing context are typically bound to the execution context. When a task runs on a worker thread, caller context must be captured at submit time and restored on the worker when running the task.

With Spring Framework 6.1+ and Micrometer Context Propagation, `ContextPropagatingTaskDecorator` can capture and restore registered context accessors:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class PropagatingExecutorConfiguration {
    @Bean("observedTaskExecutor")
    ThreadPoolTaskExecutor observedTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("observed-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

The decorator does not automatically turn every `ThreadLocal` into a propagatable context. Tracing/MDC accessors must be registered and the corresponding integration must be active. Check your Spring/Micrometer versions and actual context registry.

A proper context propagation mechanism must capture context on the submitting thread, attach it to the worker during task execution, restore the previous context afterward even if an exception is thrown, and prevent task A's values from leaking into task B due to worker thread reuse.

Tracing context holds span context and parent relationships. MDC is a map for logging. Copying `traceId`/`spanId` into MDC does not create a parent span. Use tracing context propagation to establish the proper hierarchy; logging integration will automatically include correlation fields in log events.

Spring Security context has its own propagation mechanism. Do not assume `TaskDecorator` automatically replaces all security propagation. If a task needs principal/authorization context, configure and test it separately, restrict privileges, and avoid keeping context active longer than needed.

## 6. Async methods and CompletableFuture

Spring `@Async` executes methods on a configured executor:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import java.util.concurrent.CompletableFuture;

@Service
public class ReportService {
    @Async("observedTaskExecutor")
    public CompletableFuture<String> generateReport() {
        return CompletableFuture.completedFuture("generated");
    }
}
~~~

Async processing must be enabled via appropriate configuration and reference the right executor bean. Self-invocation within the same bean bypasses the Spring proxy, so `@Async` may not apply if one method directly calls another on the same instance.

A continuation may run on a different thread depending on overloads and executors. For example, `thenApplyAsync` without specifying an executor uses the common `ForkJoinPool`. To maintain context and metrics management, pass the executor explicitly:

~~~java
CompletableFuture.supplyAsync(this::loadData, observedExecutor)
        .thenApplyAsync(this::transform, observedExecutor);
~~~

Each continuation can have its own lifecycle. Do not assume context automatically propagates through every `CompletableFuture` chain unless the executor/instrumentation supports it.

Scheduled tasks normally have no incoming HTTP parent. You can start a root task observation on each run with a stable task name. Observe duration, schedule lag, failures, and missed executions; never keep a single span open across multiple runs.

## 7. Executor metrics and saturation

Exact meter names depend on binder/framework/version; inspect the actual registry.

| Measurement | Meaning | Warning signs |
| --- | --- | --- |
| Pool size | Current number of workers | Growing continuously or hitting max |
| Active threads | Workers currently executing tasks | Staying near max for extended periods |
| Queue size | Number of waiting tasks | Growing continuously |
| Remaining capacity | Number of free queue slots | Near 0 |
| Completed task count | Tasks finished | Stops increasing when pool is stuck |
| Rejected count | Tasks rejected | Spiking abnormally |
| Task duration | Execution time | P95/p99 rising |
| Queue wait | Waiting time | Rising during backlog |

Spring Boot can instrument managed/recognized executors via auto-configuration or Micrometer binders. Manually created executors may need explicit binding/registration. Do not assume every `Executor` bean automatically exports full metrics.

A growing queue while active threads stay at max indicates tasks arrive faster than they can be processed. A large queue can hold unprocessed work for a long time and increase memory pressure. Capacity should reflect latency budgets and load tolerance.

If all workers block waiting on another `Future` submitted to the same pool, the pool can experience starvation/deadlock. Avoid blocking waits within the same pool when dependent tasks cannot run.

Rejections signal that the system is out of capacity. Depending on business semantics, reject requests synchronously, retry with limits/backoff, persist tasks to a durable queue, throttle producers, or apply a dedicated bulkhead. Never retry infinitely on the caller thread.

## 8. Errors, cancellation, and shutdown

A task may finish successfully, throw an exception, be cancelled, or be interrupted during shutdown. Observations must record the corresponding outcome and close the scope on every branch.

If a wrapper catches an exception, logs it, and ignores it, the tracing handler may never see the error outcome. Record the exception and rethrow or translate it into an explicit business error result. Never swallow exceptions without recording them.

Cancelling a `Future` does not necessarily stop running code immediately. `cancel(true)` requests interruption; the task must cooperate by checking interrupt status or using interruptible APIs. Record cancellation separately if significant, and do not misclassify it as success.

When the application shuts down, stop accepting new tasks per lifecycle, give in-flight tasks time to finish, bound await termination, record rejected/cancelled tasks, and avoid hanging the process indefinitely. Choose `waitForTasksToCompleteOnShutdown` and `awaitTerminationSeconds` based on SLAs. An in-memory queue is not durable storage; tasks that cannot be lost require persistent messaging or a durable job store.

## 9. Cardinality and privacy

| Value | Metric tag? | Reason |
| --- | --- | --- |
| task.type | Yes, if finite set | Grouping operations |
| executor.name | Yes | Stable pool name |
| task.outcome | Yes | Success/failure/cancelled |
| queue.name | Yes, if finite | Workload category |
| task.id | No | Nearly unique |
| user.id | No | High cardinality/PII |
| file path/name | No | Dynamic, potentially sensitive |
| message body | No | Business content |
| exception message | No | Unbounded free-form value |
| traceId/spanId | No | Correlation fields, not metric labels |

Trace attributes can hold additional controlled context, but size and access must be restricted. Do not copy the entire MDC, `SecurityContext`, or message headers into Observations.

## 10. Testing Executor observation

### 10.1. Testing custom Observations

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.tck.TestObservationRegistry;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class TaskObservationTest {
    @Test
    void recordsTaskOperation() {
        TestObservationRegistry registry = TestObservationRegistry.create();
        Observation.createNotStarted("application.task", registry)
                .lowCardinalityKeyValue("task.type", "report")
                .observe(() -> { });
        assertThat(registry.getCompletedObservationContexts()).hasSize(1);
    }
}
~~~

The assertion API depends on Micrometer version. This test only proves the Observation lifecycle; it does not prove executor metrics or trace export.

### 10.2. Testing context propagation and cleanup

Use a single-worker executor to force thread reuse:
1. Set a parent span/MDC value in the caller.
2. Submit task A through the context-propagating executor.
3. Assert task A sees the expected trace context and MDC.
4. Finish task A and its scope.
5. Submit task B without context.
6. Assert task B does not see task A's `traceId`/MDC.
7. Throw an exception in task C and verify context is still restored.

### 10.3. Queue wait, rejection, and cancellation tests

Use a single-threaded executor. Task A holds the worker in a controlled way; submit task B and measure B's wait time. Assert ordering/lifecycle rather than exact millisecond values because test runtimes have jitter.

For rejection, use a single-worker pool, small queue, and blocking tasks with a latch. Submit enough tasks to fill the pool/queue and verify the policy. Always release latches in `finally` so tests do not hang.

For exceptions/cancellation, verify failure outcomes, confirm `Future` cancellation differs from success, and verify interrupted tasks leave no lingering scope/context on the worker.

## 11. Troubleshooting Executor observation

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Task logs lack traceId | Context not captured/propagated | Check `TaskDecorator` and accessors |
| Task carries old request's traceId | Worker context not restored | Test thread reuse |
| Executor metrics exist but no task spans | Binder only measures the pool | Add task Observation/instrumentation |
| Duplicate task spans | Auto-instrumentation and custom wrapper both create spans | Pick one owner |
| Queue wait not measured | Only measuring execution inside worker | Instrument submit-to-start |
| Active threads at max, queue growing | Pool saturation | Inspect task duration, arrival rate, downstream |
| RejectedExecutionException increasing | Queue/pool capacity exhausted | Backpressure, capacity, rejection policy |
| Task runs on common pool | `CompletableFuture` didn't specify executor | Pass executor explicitly |
| @Async runs synchronously | Self-invocation or wrong proxy/config | Check bean boundaries and `@EnableAsync` |
| Exceptions missing from traces | Wrapper swallows exceptions | Record error and propagate outcome |
| Shutdown loses tasks | In-memory queue or short timeout | Graceful shutdown/durable queue |
| Context lost in Reactor | `ThreadLocal` insufficient for reactive context | Micrometer Context Propagation |
| Security principal missing | Security context propagation not configured | Configure and test separately |

### 11.1. Investigation workflow

1. Identify the actual executor the task uses.
2. Inspect pool metrics: active, queue, remaining capacity, completed, and rejections.
3. Measure queue wait separately from execution time.
4. Verify the task Observation/span is created exactly once.
5. Check trace parent/context on both caller and worker.
6. Test cleanup on success, error, cancellation, and thread reuse.
7. Check whether `CompletableFuture` switches to another executor.
8. Review shutdown policy against durable delivery requirements.

## 12. Production checklist

| Criterion | Evidence |
| --- | --- |
| Executor named and clearly configured | Managed bean/configuration |
| Pool sized for workload | Core/max/queue based on load tests |
| Queue wait and execution separated | Appropriate measurements exist |
| Executor metrics exposed | Active, pool, queue, completed, rejections |
| Task observation has stable name | Low-cardinality `task.type` and outcome |
| Context propagation tested | Trace/MDC captured and restored |
| No context leakage | Thread reuse tests pass |
| Exceptions/cancellations recorded | Clear outcome and error semantics |
| Rejections have backpressure | Critical tasks not silently discarded |
| Bounded shutdown | Graceful timeout and policy |
| Durable tasks have suitable storage | Do not rely on RAM queues when guarantees are required |
| Privacy/cardinality controlled | No task ID/user ID/body in metric tags |
| No duplicate spans | One instrumentation owner per boundary |

## 13. Lab exercise: observing a background report-generation task

**Scenario:** `order-service` receives a report-generation request. The HTTP endpoint enqueues a task into `ThreadPoolTaskExecutor` and returns `202 Accepted`. The task reads JDBC data, generates a file, and writes a completion status. Operations needs visibility into queue backlog, execution latency, errors, and the originating request.

**Tasks:**
1. Create a `ThreadPoolTaskExecutor` bean with explicit core/max/queue/rejection/shutdown policies.
2. Enable executor metrics and verify active threads, queue size, completed count, and rejections.
3. Create a custom Observation `report.generate` for the task lifecycle.
4. Separate queue wait from execution duration.
5. Configure `ContextPropagatingTaskDecorator` and verify trace/MDC on the worker.
6. Decide whether the task should be a child span or a span linked to the originating request per business semantics.
7. Record exception/cancellation outcomes and ensure scope cleanup.
8. Use a single worker and small queue to trigger controlled saturation/rejection.
9. Verify `CompletableFuture`/`@Async` uses the right executor.
10. Check that logs do not put user IDs, sensitive file paths, or message bodies into tags.
11. Test thread reuse to confirm subsequent tasks do not inherit old context.
12. Write a runbook for queue backlog, rejected tasks, missing trace context, and shutdown.

**Expected deliverables:** executor configuration, task Observation, pool metrics, trace/log correlation, lifecycle/context/rejection tests, and an operations runbook.

## 14. Takeaways

**Executor observation** shows how tasks are submitted, queued, executed, and completed. Queue wait time identifies backlogs; execution time pinpoints slow tasks; executor metrics show whether the pool has capacity or is saturated. Micrometer Observation describes task operations and produces metrics/spans through handlers, but must be placed at the right boundary to avoid duplicate measurement.

Thread boundaries require context propagation with proper capture, restoration, and cleanup. Use `TaskDecorator`/accessors appropriate for your version to pass tracing/MDC; do not mistake copying `traceId` into MDC for propagating a parent span. Specify explicit executors for async continuations, record rejections/exceptions/cancellations, and design shutdown according to durability requirements. Use metrics to operate the pool, traces to link tasks with requests, and logs to investigate outcomes; keep tags low-cardinality and never export sensitive data.

**References:**
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — Context Propagation](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Boot — Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html)
- [Micrometer Observation — Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [Java ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
