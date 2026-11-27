# Measuring Context Switches, Queue Wait, and Handler Time

When a Spring Integration flow is slow, looking only at total request duration is rarely enough to pinpoint the cause. A message might wait in a queue, wait for an executor thread, be delayed because a scheduler is busy, or actually spend a long time inside a handler. The operating system may also switch the CPU frequently across many threads, yet **an application-level thread handoff is not the same as an OS context switch**.

Three groups of metrics should be separated:

- **Context switches and thread scheduling** reveal whether threads frequently change state, wait for CPU, or block.
- **Queue wait** measures how long a message or task waits before a consumer or worker begins processing it.
- **Handler time** measures how long the handler actually spends executing its logic.

By measuring each interval accurately, the development team can determine whether the bottleneck lies in the channel, executor, scheduler, handler, or external dependency, and then pick an appropriate fix rather than guessing at thread pool sizes.

## 1. Distinguishing the Time Intervals

A message moving through a flow can pass through several stages:

~~~mermaid
flowchart LR
    A["Source creates message"] --> B["Channel send"]
    B --> C["Queue wait"]
    C --> D["Consumer receives"]
    D --> E["Handler starts"]
    E --> F["Handler finishes"]
    F --> G["Next channel / endpoint"]
~~~

Core measurements:

| Metric | Start point | End point | Meaning |
|---|---|---|---|
| Queue wait | Message enters the queue | Consumer retrieves the message | Time the message waits in the queue |
| Executor queue wait | Task is submitted | Worker begins running the task | Time the task waits for a worker thread |
| Handler time | Handler begins processing | Handler completes or throws | Execution cost of handler logic |
| End-to-end latency | Event starts at the source | Final result completes | Total time the business operation waits |
| Scheduler lateness | Scheduled trigger time | Actual task start time | Delay caused by scheduler or system load |
| OS context switch | A thread yields CPU or is preempted | Another thread runs | OS activity switching CPU across threads |

Do not sum metrics mechanically if they measure overlapping intervals. For example, a handler may run synchronously inside a polling task; that handler's duration is then also included in the polling task's duration. Define measurement boundaries before building dashboards.

## 2. A Thread Handoff Is Not an OS Context Switch

In Spring Integration, a message can pass through multiple execution contexts:

- `DirectChannel` typically invokes the handler on the message-sending thread.
- `QueueChannel` holds the message until a consumer receives it, usually via a polling endpoint.
- `ExecutorChannel` hands dispatching off to a `TaskExecutor`.
- `PublishSubscribeChannel` can invoke subscribers on the sending thread or dispatch via an executor depending on configuration.
- A poller is triggered by a `TaskScheduler`; synchronous handlers downstream can continue running on the polling task's thread.

Moving from thread A to thread B is an application-level **thread handoff**. When B runs, the OS may perform a context switch, yet not every handoff corresponds one-to-one with a context switch attributable to that message. Thread B may already be running on a CPU, be runnable, or be delayed by other threads.

An OS context switch is an action of the operating system scheduler. A thread can be switched out due to time-slice expiration, waiting on I/O, waiting on a lock, or preemption. High context-switch rates can indicate too many threads or blocking workloads, but by themselves they do not prove Spring Integration has a bug.

Combine these signals:

- OS context switches and CPU migrations.
- Thread counts and runnable/blocked/waiting states.
- CPU usage and CPU throttling when running in containers.
- Executor active count, queue size, and rejected tasks.
- Queue wait, handler duration, and end-to-end latency.

## 3. Channels Determine Whether Queue Wait Exists

Not every channel has the same queue wait behavior.

| Channel | Typical processing thread | Has queue wait? | What to measure |
|---|---|---|---|
| `DirectChannel` | Thread calling `send()` | No internal queue | Send duration and handler time |
| `PublishSubscribeChannel` without executor | Message-sending thread calls subscribers | No internal queue | Total dispatch time and per-subscriber time |
| `PublishSubscribeChannel` with executor | Worker provided by executor | May have executor queue wait | Task submit-to-start and handler time |
| `QueueChannel` | Polling consumer receives message | Has queue wait | Enqueue-to-dequeue and backlog |
| `PriorityChannel` | Consumer retrieves by priority order | Has queue wait | Queue wait by priority and backlog |
| `ExecutorChannel` | Worker provided by `TaskExecutor` | May have executor queue wait | Executor queue wait and handler time |

`ExecutorChannel` does not guarantee a persistent business queue. Whether tasks must wait depends on the configured `TaskExecutor`. With a direct-executing executor, queue wait is virtually zero; with a queued thread pool, tasks can wait for an idle worker.

`QueueChannel` can have a bounded capacity. When the queue is full, send operations can block until timeout or fail depending on configuration and invocation. Measure producer blocking time during send as well, since that is a form of backpressure at the channel boundary.

## 4. Measuring Queue Wait in QueueChannel

Queue wait is calculated as:

\[
T_{queue}=T_{dequeue}-T_{enqueue}
\]

To measure accurately within the same JVM, record `System.nanoTime()` when the message passes through `preSend`, then read it back in `postReceive`. A monotonic clock is suitable for measuring elapsed time because it is unaffected by system wall-clock adjustments.

Example of a `ChannelInterceptor` dedicated to measuring queue wait:

~~~java
final class QueueWaitInterceptor implements ChannelInterceptor {

    private static final String ENQUEUED_AT =
            "diag.enqueuedAtNanos";

    private final MeterRegistry registry;

    QueueWaitInterceptor(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public Message<?> preSend(
            Message<?> message, MessageChannel channel) {

        return MessageBuilder.fromMessage(message)
                .setHeader(ENQUEUED_AT, System.nanoTime())
                .build();
    }

    @Override
    public Message<?> postReceive(
            Message<?> message, MessageChannel channel) {

        if (message == null) {
            return null;
        }

        Object value = message.getHeaders().get(ENQUEUED_AT);
        if (value instanceof Long enqueuedAt) {
            long elapsed = System.nanoTime() - enqueuedAt;

            Timer.builder("integration.channel.queue.wait")
                    .tag("channel", "orders.queue")
                    .register(registry)
                    .record(elapsed, TimeUnit.NANOSECONDS);
        }

        return MessageBuilder.fromMessage(message)
                .removeHeader(ENQUEUED_AT)
                .build();
    }
}
~~~

Register the interceptor for the specific channel to measure:

~~~java
@Bean
@GlobalChannelInterceptor(patterns = "orders.queue")
QueueWaitInterceptor queueWaitInterceptor(MeterRegistry registry) {
    return new QueueWaitInterceptor(registry);
}
~~~

In this example, the interceptor stamps the timestamp before sending to the channel and records the elapsed duration when a consumer receives the message. The measurement header is removed afterward so it does not leak to downstream endpoints or adapters.

This is an approximate measurement from before the enqueue call to dequeue. `preSend` runs before the channel actually inserts the message into the queue; if a bounded `QueueChannel` is full and the producer waits for capacity, the measurement also includes the time the producer blocked on send. Measure `send()` separately or instrument deeper in the queue implementation if you need pure queue residence time. When the queue has spare capacity and sends do not block, that difference is typically small.

Apply this interceptor only to the pollable channels you need to measure. Attaching it to every channel turns the metric into something other than pure queue wait and can add unnecessary overhead. Verify your Spring Integration version and ensure the interceptor applies to the intended channel bean.

### Limits of nanoTime Measurements

`System.nanoTime()` is only meaningful for comparisons within the same process/JVM. Do not serialize this value into a message sent over a broker or persisted to storage and subtract it in another process; `nanoTime` origins across two JVMs do not share a reference frame.

For messages crossing brokers or persistence:

- Record timestamps at enqueue and at consume if cross-process measurement is required.
- Synchronize clocks across machines using infrastructure time synchronization.
- Prefer distributed tracing or broker-native metrics when accurate in-broker wait times are needed.
- Separate broker time, network transit time, and local consumer wait time.

If using wall-clock `Instant`, account for clock skew and clock adjustments. For intra-JVM durations, a monotonic clock remains the better choice.

## 5. Measuring TaskExecutor Queue Wait

For `ExecutorChannel` or endpoints dispatching through a thread pool, a message may have been submitted while a worker has not yet started running it. This is **executor queue wait**, not `QueueChannel` wait.

A Spring `TaskDecorator` can wrap the task at submission time and measure when the task starts executing:

~~~java
@Bean
ThreadPoolTaskExecutor integrationExecutor(MeterRegistry registry) {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(8);
    executor.setMaxPoolSize(16);
    executor.setQueueCapacity(500);
    executor.setThreadNamePrefix("integration-worker-");

    executor.setTaskDecorator(task -> {
        long submittedAt = System.nanoTime();

        return () -> {
            long wait = System.nanoTime() - submittedAt;

            Timer.builder("integration.executor.queue.wait")
                    .tag("executor", "integration-worker")
                    .register(registry)
                    .record(wait, TimeUnit.NANOSECONDS);

            task.run();
        };
    });

    return executor;
}
~~~

Attach this executor to the `ExecutorChannel` or endpoint to measure. `TaskDecorator` captures the submission time and computes elapsed wait when the worker begins. This duration approximates worker wait time, including time in the executor queue and worker scheduling delay.

To make the measurement meaningful, separate rejected tasks from accepted tasks that had to wait. If the executor rejects a task when the queue is full, the task never has a start time to record queue wait; count rejected executions separately.

Not every `TaskExecutor` has a queue. With an executor that runs directly on the caller thread, tasks start immediately and queue wait is near zero. With a virtual-thread-per-task executor, the thread-pool queue-wait concept may no longer apply; measure downstream resource wait times and actual scheduling delays instead of assuming a worker queue exists.

## 6. Measuring Handler Time

Handler time runs from when handler logic starts to when it ends:

\[
T_{handler}=T_{finish}-T_{start}
\]

Use a Micrometer `Timer` to record duration and classify outcomes as success/error.

~~~java
@Service
class OrderHandler {

    private final MeterRegistry registry;
    private final OrderRepository repository;

    OrderHandler(
            MeterRegistry registry,
            OrderRepository repository) {
        this.registry = registry;
        this.repository = repository;
    }

    public void process(Order order) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            repository.saveProcessed(order);
        }
        catch (RuntimeException ex) {
            outcome = "error";
            throw ex;
        }
        finally {
            sample.stop(Timer.builder("integration.handler.duration")
                    .tag("handler", "process-order")
                    .tag("outcome", outcome)
                    .register(registry));
        }
    }
}
~~~

A `Timer` provides count, total time, max, and percentiles/histograms depending on registry configuration. Use low-cardinality tags such as handler name, flow, or outcome. Never use `orderId`, `correlationId`, user ID, or payload values as tags because time-series cardinality will grow without bound.

### Handler Time Is Not End-to-End Latency

A handler may take 5 ms while the message already waited 2 seconds in a queue. Conversely, a handler may run for 500 ms while the message is dispatched immediately and still meets its SLA.

Dashboards should therefore place these metrics side by side:

- Queue wait P50/P95/P99.
- Executor queue wait P50/P95/P99.
- Handler duration P50/P95/P99.
- Message throughput and error rate.
- Queue depth and executor active/queued/rejected counts.
- Business end-to-end latency.

If the handler calls a database or HTTP client, measure dependency duration separately. When handler time rises, that breakdown shows whether time is spent in application code, locks, connection pools, or remote calls.

## 7. Measuring Scheduler Lateness

Pollers are triggered by a `TaskScheduler`. If a task begins later than its expected trigger time, that difference is scheduler lateness.

\[
T_{lateness}=T_{actualStart}-T_{scheduledStart}
\]

This can be measured by wrapping the `Runnable` or instrumenting at the scheduler abstraction. With Spring Integration, combine actual poll timestamps, source `receive()` durations, and message send durations. If the scheduled trigger time is not exposed directly by the abstraction in use, record timestamps at the start of the polling task using advice or a version-appropriate wrapper.

Do not use the time since message creation as scheduler lateness. A message may be created after multiple I/O steps in the source; those two intervals measure completely different phenomena.

## 8. Measuring OS Context Switches and CPU Scheduling

Spring Integration's Micrometer metrics do not automatically provide an exact per-message context-switch counter. That is an operating-system metric that must be observed via OS or profiling tools.

### On Windows

Use Performance Monitor (PerfMon) to track the ~System\Context Switches/sec~ counter. This counter reflects system-wide context-switch activity and does not automatically split by individual messages or Spring Integration channels.

For deeper investigation, use Windows Performance Recorder and Windows Performance Analyzer with CPU scheduling/context-switch traces. ETW tooling shows which threads were preempted, which waited for CPU, and how long threads spent in ready or waiting states.

### On Linux

Commonly used commands:

~~~bash
pidstat -w -p <java-pid> 1
~~~

This command shows voluntary and non-voluntary context switches per process/thread depending on the sysstat version.

~~~bash
perf stat -e context-switches,cpu-migrations -p <java-pid>
~~~

This command counts context switches and CPU migrations for the process over the observation window. Appropriate system permissions are required to run `perf`.

~~~bash
vmstat 1
~~~

`vmstat` reports system-wide context switches per interval alongside CPU and runnable-process metrics. It offers a system-wide view and does not replace per-process analysis.

### Interpreting Context Switch Numbers Properly

- **Voluntary context switches** typically happen when a thread explicitly waits on I/O, locks, conditions, or sleep.
- **Involuntary context switches** typically happen when a thread is preempted or exhausts its time slice.
- **CPU migration** is when a thread moves to a different CPU core; it is not the same as a context switch.
- Higher context switching can result from too many threads, blocking, lock contention, or other system workloads.

There is no single context-switches/sec threshold that fits every application. Compare against a baseline at equivalent load, CPU usage, latency, and throughput. If context switches rise while latency and throughput stay stable, changes may not be needed. If context switches rise alongside queue wait, CPU saturation, and handler latency, look for thread contention or improper pool sizing.

## 9. Using Java Flight Recorder and Thread Dumps

Java Flight Recorder (JFR) is useful for finding why threads fail to make progress. Events to inspect depend on the workload:

- `jdk.ThreadPark`: threads parking while waiting on a synchronizer or executor.
- `jdk.JavaMonitorEnter`: time spent waiting for a monitor lock.
- `jdk.JavaMonitorWait`: time spent waiting on a monitor.
- `jdk.ThreadSleep`: thread sleep durations.
- `jdk.ExecutionSample`: stack samples of executing threads.
- `jdk.ThreadCPULoad`: per-thread CPU load if supported by your runtime/version.

JFR reveals threads executing code, waiting on locks, or parked. It does not replace OS context-switch counters; use OS tracing when exact context-switch counts are needed.

A thread dump is a point-in-time snapshot of thread states. You can capture one with:

~~~bash
jcmd <java-pid> Thread.print
~~~

Capture several thread dumps spaced a short interval apart. A thread continuously in `BLOCKED` may be contending for a monitor; `WAITING` or `TIMED_WAITING` may indicate waiting on queues, conditions, or I/O. `RUNNABLE` does not guarantee a thread is currently on CPU; it may be runnable while waiting for the OS scheduler to grant CPU time.

Match thread names against configured prefixes:

- `integration-scheduler-`: scheduler threads.
- `integration-worker-`: executor workers.
- Threads of HTTP clients, JDBC pools, or broker clients: external dependencies.

Thread names help narrow the search; inspect stack traces and actual states before drawing conclusions.

## 10. Reading Queue Depth and Executor Saturation

High queue wait often accompanies high queue depth or executor saturation, yet the two metrics do not replace each other.

| Metric | Question answered |
|---|---|
| Queue depth | How many messages are waiting? |
| Queue wait | How long has a message waited before being received? |
| Arrival rate | At what rate are messages arriving? |
| Completion rate | At what rate are consumers completing messages? |
| Executor active count | How many workers are actively running tasks? |
| Executor queue size | How many tasks are waiting for a worker? |
| Rejected count | How many tasks were not accepted by the executor? |

If arrival rate consistently exceeds completion rate, queue depth grows. As the queue grows, queue wait usually grows as well. If queue depth is small while queue wait is high, consumers may be paused for long stretches, the scheduler may be delayed, or the queue may have only one very slow consumer.

With `ThreadPoolTaskExecutor`, observe pool size, active count, and queue size from the executor implementation or Micrometer executor instrumentation. With `QueueChannel`, monitor queue capacity and current message count using mechanisms suited to the implementation; not every channel exposes the same metrics.

## 11. Designing Metrics and Tags

A useful metric suite should have stable names and bounded tags:

| Metric | Suggested tags | Purpose |
|---|---|---|
| `integration.channel.queue.wait` | `channel`, `flow` | Measure time messages wait in a channel |
| `integration.executor.queue.wait` | `executor`, `flow` | Measure time tasks wait for a worker |
| `integration.handler.duration` | `handler`, `outcome` | Measure handler execution duration |
| `integration.poll.duration` | `endpoint`, `outcome` | Measure duration of a poll cycle |
| `integration.message.processed` | `flow`, `outcome` | Count succeeded/failed processed messages |
| `integration.message.backlog` | `channel` | Track count of waiting messages |
| `integration.executor.rejected` | `executor` | Detect rejected tasks |

These metrics are illustrative application naming conventions; do not assume Spring Integration registers all of these names automatically. Use Micrometer Timers, Counters, and Gauges or the observation instrumentation of your running version.

Keep tag values stable. Avoid putting high-cardinality values such as message ID, order ID, correlation ID, full URLs, or exception messages into tags. Those values belong in controlled traces and logs.

## 12. Observation and Tracing in Spring Integration

Spring Integration integrates with Micrometer Observation in supported versions. Observation can link message send/receive activity to tracing and metrics when the application configures an `ObservationRegistry` and corresponding integration management.

When enabling instrumentation:

- Choose which components to monitor instead of instrumenting everything without considering overhead.
- Use trace context to connect steps in the flow and outbound calls.
- Give spans/observations meaningful names such as the channel, handler, or adapter.
- Verify context propagation when messages cross executors or brokers.
- Never record sensitive payloads in span attributes.

Tracing shows which spans a message traversed and which span was slow. Metrics show trends and distributions over time. OS profiling shows how threads and CPUs are behaving. The three perspectives complement each other.

## 13. Analyzing Common Bottleneck Patterns

| Observation | Likely cause | Next check |
|---|---|---|
| Queue wait rises, handler time steady | Consumer lacks concurrency or queue backlog is growing | Compare arrival/completion rates, active consumers, and queue capacity |
| Executor queue wait rises, CPU high | Pool lacks workers or tasks are CPU-bound | Profile CPU, inspect pool size and task duration |
| Executor queue wait rises, CPU low | Workers are blocked on I/O or waiting on locks | Use JFR and thread dumps to locate waits/parks |
| Handler time rises, queue wait low | Handler logic or dependency is slow | Measure DB/API/locks separately inside the handler |
| Context switches rise, throughput flat | Too many threads or contention | Inspect voluntary/involuntary switches, runnable threads, and locks |
| Scheduler lateness rises | Scheduler pool is occupied or tasks are blocking | Check scheduler thread dumps and per-poller duration |
| Queue depth low yet end-to-end latency high | Delay before enqueue or inside handler/downstream | Place timestamps at source, handler, and completion |
| CPU low yet queue wait high | Consumer is not triggered, thread is blocked, or endpoint is stopped | Check lifecycle, poller schedule, and consumer state |

Do not raise concurrency before finding the bottleneck. If a database connection pool has only 10 connections, increasing an executor to 100 threads can create 90 threads waiting for connections and increase context switches. If handlers are CPU-bound, adding threads beyond core count can hurt efficiency due to contention and scheduling overhead.

## 14. Measurement Workflow During an Investigation

An investigation can proceed in sequence:

1. **Map the path**: record the message's source, channels, endpoints, executors, and handlers.
2. **Place timestamps**: enqueue/dequeue, task submit/start, handler start/end, and completion.
3. **Establish a baseline**: collect P50/P95/P99, throughput, error rate, queue depth, and CPU under normal load.
4. **Reproduce load**: use a production-like workload keeping message sizes, concurrency, and dependencies realistic.
5. **Isolate**: identify which time interval accounts for most of the end-to-end latency.
6. **Correlate threads**: use JFR/thread dumps and OS context-switch data when needed.
7. **Change one factor**: such as batch size, pool size, channel, or timeout.
8. **Re-measure under the same conditions**: compare latency, throughput, CPU, context switches, and error rates.
9. **Test peak load**: verify queues do not grow unbounded and executors do not continuously reject tasks.

Do not draw conclusions from a brief measurement. Allow enough time to observe polling cycles, burst traffic, and dependency variability.

## 15. Testing Instrumentation

Instrumentation should be verified so it does not produce misleading metrics:

- Queue wait must start before enqueue and end after dequeue.
- Executor wait must start at submission and end when the worker begins running.
- Handler time must still stop even when an exception is thrown.
- Internal measurement headers must be stripped before messages cross persistence/broker boundaries.
- Timers must have low tag cardinality.
- Rejected or dropped messages must have separate counters; never let them vanish from statistics.
- Instrumentation must not alter payloads, routing, or channel semantics.
- Measure interceptor/decorator overhead under high load.

Use a test clock or mocked monotonic clock if supported by your test framework. For an interceptor based on `nanoTime`, test that the timestamp is added before send, duration is recorded after receive, and diagnostic headers are stripped from the returned message.

## 16. Production Diagnostic Checklist

When a flow slows down or throughput drops, answer:

- Which channels does the message traverse? Do they buffer or dispatch synchronously?
- How many thread handoffs occur between source and handler?
- Are queue wait and executor queue wait measured at the exact boundaries?
- Does handler time separate dependency I/O and lock wait?
- Do P50/P95/P99 show rising tail latency?
- Do queue depth and completion rate indicate a growing backlog?
- Does the executor show high active threads, a large queue, or rejected tasks?
- Is the scheduler blocked or missing triggers?
- Are OS context switches rising due to this application's workload or another process?
- Do JFR/thread dumps show lock contention, parking, or blocking I/O?
- Do metrics maintain low tag cardinality and avoid sensitive data?
- After a change, do throughput and latency improve under the same load conditions?

Measuring queue wait, handler time, and context switches at the right layers separates messages waiting to be processed from messages being processed slowly. That provides a sound basis for tuning channels, pollers, executors, and thread counts.

## References

The official documents below describe the APIs and tools by version. Cross-check against the versions of Spring Integration, Spring Framework, Micrometer, and JDK used by your application.

- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html)
- [Spring Integration — Message Endpoints and Pollers](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — TaskExecutor and TaskDecorator](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
- [JDK Flight Recorder](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-api.html)
