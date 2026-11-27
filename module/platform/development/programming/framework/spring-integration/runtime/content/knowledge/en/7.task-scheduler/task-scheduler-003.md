# Fixed Rate, Fixed Delay, and Cron Triggers

In **SPRING_INTEGRATION_RUNTIME**, a poller is the component that helps a consumer retrieve messages from a source on a schedule. This schedule is driven by a trigger and executed through **TaskScheduler**. Spring Integration provides three common schedule types: **fixed rate**, **fixed delay**, and **cron**. Choosing the right trigger type directly affects latency, throughput, predictability of execution times, and how the application responds when a poll runs long.

These three triggers can be used in Java DSL via `Pollers.fixedRate(...)`, `Pollers.fixedDelay(...)`, and `Pollers.cron(...)`. They determine **when the polling endpoint is invoked**. The number of messages fetched per poll, handler processing duration, and level of parallelism depend on the poller, channel, executor, and handler configuration. Understanding each layer separately prevents confusing the polling cadence with message processing speed.

## 1. Poller, Trigger, and TaskScheduler

### 1.1 How Does a Polling Endpoint Work?

With a `PollableChannel` or a `MessageSource`, the consumer is not called directly by the channel when a message arrives. The polling endpoint must actively pull messages on a schedule.

A general poll pass can be visualized as:

~~~mermaid
flowchart TD
    A["TaskScheduler"] --> B["Trigger becomes due"]
    B --> C["Polling endpoint runs"]
    C --> D["receive() from MessageSource / PollableChannel"]
    D --> E{"Message available?"}
    E -->|Yes| F["Invoke MessageHandler"]
    F --> G{"Quota remaining in poll?"}
    G -->|Yes| D
    G -->|No| H["End poll pass"]
    E -->|No| H
    H --> A
~~~

Each component has a distinct responsibility:

- **Trigger** determines when a task is due.
- **TaskScheduler** schedules and invokes the task at the appropriate time.
- **Polling endpoint** performs the message receive operation and passes the message to the handler.
- **TaskExecutor** can be used to execute the polling task or asynchronous work according to configuration.
- **MessageHandler** processes the payload or message after it is received.

In an event-driven flow using a `SubscribableChannel`, the channel dispatches messages to subscribers when the producer sends them. With a polling consumer, the endpoint actively calls `receive()`; thus the trigger schedule determines when the consumer checks the source.

### 1.2 TaskScheduler Differs from TaskExecutor

`TaskScheduler` manages when tasks run. `TaskExecutor` manages executing tasks on threads.

| Component | Answers the Question | Example |
|---|---|---|
| Trigger | When is the task due? | Every 5 seconds, 2 seconds after the previous pass finishes, or 8:00 AM on weekdays |
| TaskScheduler | Who schedules and invokes the task? | `ThreadPoolTaskScheduler` |
| TaskExecutor | Which thread does the task run on? | `ThreadPoolTaskExecutor` |
| Poller | How are messages fetched when invoked? | `maxMessagesPerPoll`, `receiveTimeout` |
| Handler | How is the message processed? | Service activator, transformer, filter |

Do not increase the TaskExecutor pool to fix a misconfigured poller schedule. Nor should you increase trigger frequency when handlers are bottlenecked on a database or external API. First identify whether the delay lies in the poll schedule, receive wait time, executor, or processing logic.

## 2. Fixed Rate: Scheduling at a Fixed Cadence

### 2.1 Meaning

Fixed rate targets start times of consecutive executions separated by a fixed time interval. For example, a 5-second fixed rate has planned marks:

~~~text
Planned time:       00s    05s    10s    15s    20s
                    |------|------|------|------|
Poll pass:          P1     P2     P3     P4     P5
~~~

The interval is measured between the planned start times of passes, rather than waiting a delay after the previous pass finishes before scheduling the next one.

Fixed rate is suitable when you want to check a source on a steady cadence, such as periodic state synchronization, periodic data reads, or checking whether a source has new messages.

### 2.2 Configuration in Spring Integration

~~~java
@Bean
IntegrationFlow fixedRateFlow(
        MessageSource<Order> orderSource,
        OrderService orderService) {

    return IntegrationFlow.from(
            orderSource,
            endpoint -> endpoint.poller(
                Pollers.fixedRate(5_000)
                    .maxMessagesPerPoll(10)))
        .handle(orderService, "process")
        .get();
}
~~~

This example schedules the polling endpoint at a 5-second fixed rate. Each time it is invoked, the poller can fetch up to 10 messages per the `maxMessagesPerPoll` setting, if messages remain in the source.

Fixed rate does not mean each message is processed 5 seconds apart. The trigger schedules **one poll pass**; a single poll pass can receive multiple messages. If the handler takes 200 ms per message and the poller fetches 10 messages, the processing time for one pass can be significantly longer than the time to receive a single message.

### 2.3 When a Poll Pass Runs Longer Than the Period

Suppose the period is 5 seconds but a poll pass takes 8 seconds. With a scheduler based on `ScheduledExecutorService`, the same periodic task does not execute concurrently with itself; the next execution may be delayed past its planned mark. The scheduler does not automatically spawn an extra copy of the running task in parallel.

However, distinguish between the callback invoked by the scheduler and work that the callback delegates to an executor or asynchronous component. If the poller or downstream uses an asynchronous executor/channel, work from the previous pass may still be processing when the next poll pass starts. In that case, concurrency depends on the executor and endpoint configuration, not just fixed rate.

Use fixed rate when regular start times are meaningful. If each pass needs a pause after processing finishes, fixed delay is usually more predictable.

## 3. Fixed Delay: Waiting After the Previous Pass Completes

### 3.1 Meaning

Fixed delay measures the wait time from when one execution finishes until the next one starts.

~~~text
Poll pass 1:       [--- 3s processing ---]
                                          <--- 5s delay --->
Poll pass 2:                                                [--- ... ---]
                                                                         <--- delay --->
Poll pass 3:                                                                            [...]
~~~

If processing takes 3 seconds and fixed delay is 5 seconds, the gap between two start times will be roughly 8 seconds. If processing takes 7 seconds, the gap between two start times will be roughly 12 seconds.

Fixed delay is suitable when you need a rest interval after processing finishes, for example:

- Calling an external API with rate limits.
- Polling a slow source and wanting to avoid continuous load.
- Running a task whose processing duration varies significantly.
- Wanting to maintain a stable pause between two sync passes.

### 3.2 Configuration in Spring Integration

~~~java
@Bean
IntegrationFlow fixedDelayFlow(
        MessageSource<Order> orderSource,
        OrderService orderService) {

    return IntegrationFlow.from(
            orderSource,
            endpoint -> endpoint.poller(
                Pollers.fixedDelay(5_000)
                    .maxMessagesPerPoll(20)))
        .handle(orderService, "process")
        .get();
}
~~~

Here, the poller waits 5 seconds after an execution finishes before scheduling the next pass. Each pass can receive up to 20 messages per the configured quota.

Fixed delay is typically well-suited for polling sources that need to limit pressure on external systems. In return, if processing drags on, the effective poll frequency drops as processing time grows. This can increase detection latency for new messages.

## 4. Cron: Scheduling by Calendar Time

### 4.1 Meaning

A cron trigger determines execution times using a calendar expression rather than a uniform interval. For example:

- Every 5 minutes.
- Every day at 02:00.
- Monday through Friday at 09:00.
- At the top of every hour.

A Spring cron expression uses 6 fields in order:

~~~text
second minute hour day-of-month month day-of-week
   |      |    |       |          |       |
   |      |    |       |          |       +-- Day of week
   |      |    |       |          +---------- Month
   |      |    |       +--------------------- Day of month
   |      |    +----------------------------- Hour
   |      +---------------------------------- Minute
   +----------------------------------------- Second
~~~

Example expressions:

| Cron expression | Schedule |
|---|---|
| `0 */5 * * * *` | Every 5 minutes, at second 0 |
| `0 0 * * * *` | At the start of every hour |
| `0 0 2 * * *` | Every day at 02:00 |
| `0 0 9 * * MON-FRI` | 09:00 Monday through Friday |
| `0 30 8 1 * *` | 08:30 on the first day of every month |

Spring cron expressions have a leading seconds field, unlike some cron schedulers that use only 5 fields. Do not copy expressions from Linux crontab or cloud services without checking the format.

### 4.2 Configuring a Poller with Cron

~~~java
@Bean
IntegrationFlow cronFlow(
        MessageSource<ReportRequest> reportSource,
        ReportService reportService) {

    return IntegrationFlow.from(
            reportSource,
            endpoint -> endpoint.poller(
                Pollers.cron("0 0 2 * * *")
                    .maxMessagesPerPoll(50)))
        .handle(reportService, "generate")
        .get();
}
~~~

This example schedules the poller to run at 02:00 every day and process up to 50 messages in one pass. If the source has more than 50 messages, the remainder will be processed in subsequent passes according to the next schedule or how the poller is configured.

Cron fits tasks tied to a business calendar such as end-of-day reports, reconciliation, start-of-day synchronization, or scheduled time-window checks. It is not suitable if the actual goal is simply running every 5 seconds; fixed rate or fixed delay is easier to understand and control.

### 4.3 Time Zones and Daylight Saving Time

Cron is typically interpreted according to the time zone of the trigger or scheduler. If a business schedule is tied to a specific time zone, configure the time zone explicitly rather than relying on the host machine's default time zone.

For example, a report schedule at 02:00 in Vietnam should be specified as `Asia/Ho_Chi_Minh`. If the application runs across regions or in containers using UTC, execution times may differ from the local time operators expect.

Regions with daylight saving time can have days where a local hour is skipped or occurs twice. Decide whether the business schedule should follow local wall-clock time or UTC. For financial or reconciliation jobs, clearly define how clock-transition days are handled.

When you need to specify a time zone directly, Spring Framework provides `CronTrigger`, which accepts a cron expression along with a time zone. For the poller DSL, check the overloads and trigger configurations supported by your version of Spring Integration; do not assume every version exposes the exact same time zone configuration API.

## 5. Comparing the Three Triggers

| Criterion | Fixed rate | Fixed delay | Cron |
|---|---|---|---|
| Calculation | Fixed time interval between planned marks | Delay measured after the previous pass finishes | Calendar date/time expression |
| Best suited for | Steady periodic checks | Resting after processing finishes | Calendar-based business schedules |
| Impact of long runs | Ticks may lag; offloaded async work may overlap | Next pass starts later based on processing time | Executions depend on trigger and missed-tick handling |
| Timing predictability | Good when tasks are short and scheduler is stable | Depends on processing duration | Good by calendar time and time zone |
| Example | Every 10 seconds | Wait 5 seconds after each pass | 02:00 every day |

A quick way to choose:

- Use **fixed rate** if you want poll passes on a fixed cadence and tasks generally complete quickly.
- Use **fixed delay** if you always want a pause after each pass finishes.
- Use **cron** if execution times are tied to dates, hours, or business days.

Do not pick a trigger solely based on the period number. Account for processing duration, source load, acceptable latency, behavior during application shutdown, and time zone requirements.

## 6. How Many Messages Does One Poll Pass Process?

The trigger only decides when the polling endpoint is invoked. Within each pass, the poller can call `receive()` multiple times depending on `maxMessagesPerPoll`.

Example:

~~~java
Pollers.fixedDelay(1_000)
    .maxMessagesPerPoll(25)
~~~

This means the poller is scheduled with a 1-second fixed delay and has a maximum quota of 25 messages per pass. It is not a guarantee of processing exactly 25 messages every second. If the source is empty, the poll pass may yield no messages; if the handler is slow, a pass can take longer than expected.

Consider these cases:

- **Small quota**: reduces how long a poll pass occupies the scheduler, but can allow backlogs to grow if receive rate falls behind message arrival rate.
- **Large quota**: increases messages processed per pass and reduces scheduling overhead, but one pass can run long and make other tasks wait if the scheduler pool is small.
- **Empty source**: the poller may still be invoked on trigger without producing business work.
- **Continuously populated source**: a large or unlimited quota can cause a processing pass to run continuously; maintain fairness with other endpoints.

`maxMessagesPerPoll` caps how many messages a polling consumer receives in a single execution. It does not replace executor concurrency limits, nor does it guarantee parallel message processing.

## 7. Configuring TaskScheduler for Polling Endpoints

### 7.1 ThreadPoolTaskScheduler

TaskScheduler executes scheduled callbacks. You can declare a `ThreadPoolTaskScheduler` to control how many threads are dedicated to scheduler tasks:

~~~java
@Bean
ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(4);
    scheduler.setThreadNamePrefix("si-scheduler-");
    scheduler.setWaitForTasksToCompleteOnShutdown(true);
    scheduler.setAwaitTerminationSeconds(30);
    return scheduler;
}
~~~

This example uses a 4-thread pool so the scheduler can run multiple scheduled tasks. The bean name and how Spring Integration selects the scheduler should be consistent with your application's infrastructure configuration; do not create multiple redundant scheduler beans unintentionally.

A scheduler pool that is too small can cause other periodic tasks to wait when one callback holds a thread for a long time. A pool that is too large creates extra threads and unnecessary context switching. Measure execution duration, schedule lag, and the number of scheduled tasks before changing pool size.

### 7.2 Scheduler Is Not a Business Worker Pool

If a polling endpoint invokes its handler synchronously, processing time can occupy the scheduler thread. To separate polling from processing, configure an executor on the poller or place an asynchronous channel in the flow.

Example boundary:

~~~mermaid
flowchart LR
    A["TaskScheduler"] --> B["Polling endpoint"]
    B --> C["MessageSource"]
    C --> D["Message"]
    D --> E["ExecutorChannel"]
    E --> F["Worker thread"]
    F --> G["Message handler"]
~~~

In this model, the scheduler schedules the poll; the poller fetches the message; ExecutorChannel hands downstream processing off to an executor. The scheduler and worker pool can be tuned independently for load and concurrency requirements.

When adding an executor, the handler may continue running after sending the message to the channel returns. Therefore, transactions, exceptions, completion ordering, and shutdown must be examined at the asynchronous boundary.

## 8. Distinguishing Pollers from @Scheduled

Spring Framework provides the `@Scheduled` annotation to schedule method invocations. A Spring Integration poller is configuration attached to a polling endpoint, where a trigger fires a message receive operation from a MessageSource or PollableChannel.

| Usage | Purpose |
|---|---|
| `@Scheduled` | Schedule invocation of an application method |
| `Pollers.fixedRate(...)` | Schedule a polling endpoint at a fixed rate |
| `Pollers.fixedDelay(...)` | Schedule a polling endpoint with a fixed delay |
| `Pollers.cron(...)` | Schedule a polling endpoint via cron |

`@Scheduled` example:

~~~java
@Component
class CacheRefreshJob {

    @Scheduled(fixedDelay = 30_000)
    void refresh() {
        // Call cache refresh logic.
    }
}
~~~

Poller example:

~~~java
@Bean
IntegrationFlow refreshRequestFlow(
        MessageSource<RefreshRequest> source,
        CacheRefreshService service) {

    return IntegrationFlow.from(source,
            endpoint -> endpoint.poller(Pollers.fixedDelay(30_000)))
        .handle(service, "refresh")
        .get();
}
~~~

Both use Spring's scheduling infrastructure, but a poller integrates directly with the message flow. There is no need to use `@Scheduled` to call `receive()` manually when a polling endpoint already meets the requirement. Conversely, a task that only calls an internal method and needs no message abstraction can fit `@Scheduled`.

## 9. Pollers, Transactions, and Retries

A poller can be configured with advice wrapping the polling operation or message processing. This is where transaction advice, retry advice, or other cross-cutting concerns are typically placed.

Points to determine:

- Does the transaction wrap reading the source, handler processing, or both?
- Is the message taken from the queue before or after the transaction begins?
- If the handler fails, can the source roll back so the message is received again?
- If the external source does not support transactions, what acknowledgment or idempotency mechanism is needed?
- Does retry run on the same thread or via another executor?

With a transactional database source, a poller can coordinate transactions to read and process data within the chosen boundary. With brokers or external APIs, acknowledgment and redelivery mechanisms depend on the connector. Do not assume all MessageSource implementations roll back messages the same way.

Retries must distinguish transient errors from unrecoverable errors. With unlimited retries and a short delay, a failing endpoint can occupy the scheduler or workers continuously. Set attempt limits, backoff, an error channel, and failed-message persistence according to business requirements.

## 10. What Happens When the Application Stops or Misses a Schedule?

TaskScheduler only schedules within the lifetime of the running process. If the application stops at 02:00 and restarts at 02:20, cron does not automatically recreate a durable poll for the missed 02:00 mark. Similarly, fixed rate or fixed delay does not automatically store a history of ticks missed while the process was down.

If the requirement is "a report must be generated every day," do not rely solely on a cron trigger. Persist job state or the most recently completed period timestamp so that when the application restarts, it can detect missed periods and run catch-up processing.

Common patterns:

- Store `lastSuccessfulRun` or a job execution table in the database.
- Create jobs per business date with a unique key to prevent duplicate runs.
- Use a distributed scheduler or durable job store if multiple nodes coordinate work.
- Design idempotent handlers so reruns do not create duplicate data.
- Use a lock/lease if only one instance is allowed to execute a given period's job.

A cron trigger is neither a message broker nor a durable job store. If you need guaranteed execution once per period, build appropriate state persistence, locking, and catch-up mechanisms.

## 11. Observing and Diagnosing Poll Schedules

When a poller does not run on time or backlogs grow, inspect layer by layer:

| Symptom | Checkpoints |
|---|---|
| No poll passes | Is the endpoint running, is autoStartup enabled, is the trigger valid |
| Polls run off-schedule | Time zone, cron expression, whether the scheduler pool is occupied |
| Fixed delay takes longer than expected | Previous pass processing duration, receive duration, and wait time |
| Fixed rate falls behind | Are callbacks running longer than the period, does the scheduler have enough threads |
| Cron missed a period | Did the process stop, does the trigger have lenient behavior, is there a catch-up mechanism |
| Backlog growing | maxMessagesPerPoll, handler throughput, executor queue, and message source |
| Low CPU but high latency | I/O, locks, connection pool, transactions, or remote services |
| Multiple passes processing concurrently | Poller task executor, downstream channel, and worker pool |

Useful metrics:

- Poll count and interval between consecutive polls.
- Execution duration of a single poll pass.
- Number of messages received per pass.
- Processing duration per message.
- Queue depth and backlog at the source.
- Number of active scheduler threads.
- Number of active executor workers and queued tasks.
- Poll error counts, handler error counts, and retries.
- Timestamp of the most recent successful business job run.

Set meaningful thread name prefixes like `si-scheduler-` and `si-order-worker-` for reading logs and thread dumps. Log `messageId`, `correlationId`, and endpoint name to trace a message through the flow.

## 12. Testing Triggers and Polling Endpoints

Schedule tests should not depend on long sleeps or unstable real-time timing. You can:

- Verify the poller configuration is created with the right trigger and quota.
- Use a fake MessageSource to count receive calls and return scripted messages.
- Use a CountDownLatch to wait for the handler to be invoked instead of fixed sleeps.
- Verify fixed delay by recording start/end timestamps for each pass.
- Test cron expressions against representative calendar instants, including time zones and clock-transition days if relevant to the business domain.
- Test stopping the endpoint to confirm the poller stops issuing new poll passes.
- Test handler errors, retries, and the error channel separately from normal schedule tests.

For integration tests, use a test-configured scheduler and bounded wait times. Avoid making tests depend directly on a cron mark far in the future.

## 13. Misconceptions to Avoid

- **Fixed rate is not fixed delay**: fixed rate tracks scheduled start marks; fixed delay waits after the previous pass finishes.
- **Cron is not a fixed interval**: it follows calendar date/time and time zones.
- **The trigger does not decide message count**: `maxMessagesPerPoll` controls the quota of a poll pass.
- **One poll does not equal one message**: one pass can receive multiple messages depending on configuration.
- **TaskScheduler is not TaskExecutor**: one schedules work, the other executes tasks.
- **A poller is not an event-driven consumer**: a poller actively calls receive; an event-driven consumer is dispatched by the channel.
- **Fixed rate does not guarantee parallel processing**: the scheduler and executor determine threads and concurrency.
- **Cron does not persist executions across downtime**: you need a job store or catch-up mechanism if periods cannot be skipped.
- **Increasing poll frequency does not automatically increase throughput**: if the handler or external source is bottlenecked, higher frequency can worsen load.
- **Stopping a poller does not automatically drain the backlog**: you need a shutdown sequence and checks for pending messages.

## 14. Self-Check

1. If one processing pass takes 8 seconds and the desired period is 5 seconds, how do fixed rate and fixed delay produce different start schedules?
2. A polling endpoint uses cron at 02:00 every day. Why might this schedule run at the wrong time when moving environments from Vietnam to another time zone?
3. If you want each poll pass to process at most 20 messages, which property must be configured? Does the trigger decide this number?
4. Why do TaskScheduler and TaskExecutor need to be monitored separately?
5. A fixed-rate poller uses an executor for asynchronous processing. Why might work from the previous pass still be running when the next poll pass starts?
6. The application stops when cron is due and restarts afterward. What mechanism is needed so that the job period is not missed?
7. When the message source is empty, the poller is still scheduled. How does this differ from an event-driven consumer?
8. When a poll pass processes too many messages, how can it affect other scheduled tasks sharing the same scheduler?

## References

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — TaskScheduler API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/TaskScheduler.html)
- [Spring Framework — CronTrigger API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/support/CronTrigger.html)
- [Spring Integration — Poller configuration](https://docs.spring.io/spring-integration/reference/endpoint.html#polling-consumer)
- [Spring Integration — Pollers API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/dsl/Pollers.html)

## Conclusion

Fixed rate, fixed delay, and cron all control when a polling endpoint is invoked, but they represent three distinct schedule models: steady cadence between marks, rest interval after completion, and calendar date/time. TaskScheduler executes the schedule; the poller determines how messages are fetched and the per-pass quota; the executor and channels determine thread boundaries and concurrency. When choosing a trigger, account for processing duration, time zones, backlogs, transactions, retries, and application shutdown scenarios. For business jobs that must never skip a period, persist execution state and design catch-up mechanisms rather than expecting cron to retain missed runs.
