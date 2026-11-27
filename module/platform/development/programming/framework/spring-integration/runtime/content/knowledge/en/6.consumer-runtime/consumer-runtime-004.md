# fixedDelay, fixedRate, and cron Triggers

In Spring Integration, a polling endpoint does not randomly loop asking a channel for messages. It is triggered on a schedule by a **poller**. The poller's trigger determines when a polling cycle begins: after a pause following the previous execution (`fixedDelay`), on a fixed time cadence (`fixedRate`), or at times matching a schedule expression (`cron`).

Choosing a trigger affects message-receiving latency, system load, how a long-running cycle is handled, and alignment with business schedules. However, the trigger only decides when to poll; how many messages are fetched per cycle, handler processing duration, the scheduler thread, executors, and transactions remain separate configuration concerns.

After this lesson, you will be able to:

- Distinguish the execution timing of `fixedDelay`, `fixedRate`, and `cron`.
- Configure triggers in Java DSL and understand `initialDelay` and `maxMessagesPerPoll`.
- Analyze the impact of processing time on polling cadence.
- Distinguish the scheduler thread from message-processing threads.
- Choose the right trigger and diagnose delayed, overloaded, or mis-scheduled polling.

## 1. Poller and Polling Cycle

A poller is the scheduling mechanism for an endpoint that needs to actively pull messages. It is commonly used with a `PollableChannel` such as `QueueChannel`, or with an inbound channel adapter whose data source is queried on a schedule.

```text
TaskScheduler
     |
     | trigger fires
     v
Polling endpoint
     |
     | receive / read source
     v
Message (if available)
     |
     v
MessageHandler / downstream flow
```

Each trigger firing starts a **polling task**. Within that task, the endpoint can fetch one or more messages depending on `maxMessagesPerPoll` and the source/channel mechanism. When no more messages remain, the fetch loop usually ends early instead of waiting until the limit is reached. Afterward, the trigger determines when the next task is invoked.

Do not confuse these three milestones:

- **Trigger time:** when the scheduler fires the polling task.
- **Receive time:** when the endpoint actually obtains a message from the channel/source.
- **Processing time:** how long the handler and downstream steps take to process the message.

If the queue is empty, a poll can still run without producing any message. If the handler is slow, the polling task can take longer and affect the next poll's timing, depending on the trigger and scheduler.

## 2. fixedDelay: Wait an Interval After the Previous Run Completes

`fixedDelay` defines the interval between the **end of one execution** and the **start of the next**. For example, a 2-second delay means that after the polling task finishes, the scheduler waits about 2 seconds before firing the next task.

```text
Task 1: [---- processing 3s ----]  rest 2s  Task 2: [---- ...
        ^ start                  ^          ^ start
```

If a polling task takes 3 seconds and the fixed delay is 2 seconds, the gap between two start times is roughly 5 seconds (excluding scheduling jitter). Because the pause is measured after the task finishes, `fixedDelay` automatically adapts its pace to actual processing duration.

Java DSL example:

```java
@Bean
IntegrationFlow pollOrders(OrderHandler handler) {
    return IntegrationFlow.from(
            "ordersQueue",
            endpoint -> endpoint.poller(
                    Pollers.fixedDelay(2_000)
                            .maxMessagesPerPoll(10)))
            .handle(handler, "handle")
            .get();
}
```

In this example, the endpoint polls `ordersQueue` with a fixed delay of 2,000 milliseconds and processes up to 10 messages in one polling cycle. If the queue runs out of messages before reaching 10, the task can finish early; the next delay starts counting from when the task ends.

`fixedDelay` is suitable when:

- You want a steady rest interval between polls.
- Query or processing times can vary significantly.
- You want to avoid polls piling up immediately after a long poll.
- System load should naturally throttle down when each cycle takes longer.

In return, the polling cadence is not an absolute frequency. When the handler takes longer, the next poll shifts back accordingly.

## 3. fixedRate: Maintain Cadence by Scheduled Start Times

`fixedRate` defines the interval between **expected start times**. For example, a 2-second fixed rate schedules starts at 0s, 2s, 4s, 6s... on the scheduling clock.

```text
Expected schedule: 0s       2s       4s       6s
                   |--------|--------|--------|

Short task:        [--]     [--]     [--]     [--]
Long task:         [------ 3s task ------][------ 3s task ------]
                   0s                    ~3s
```

If a task runs longer than the period, the next execution may start late relative to its expected mark. Under standard scheduler behavior, the same periodic task does not overlap with itself; delayed runs may execute back-to-back to catch up with the schedule, depending on the scheduler. `fixedRate` does not automatically spawn multiple consumers or parallel threads for the same endpoint.

Example:

```java
@Bean
IntegrationFlow pollInventory(InventoryHandler handler) {
    return IntegrationFlow.from(
            "inventoryQueue",
            endpoint -> endpoint.poller(
                    Pollers.fixedRate(5_000)
                            .initialDelay(1_000)
                            .maxMessagesPerPoll(5)))
            .handle(handler, "refresh")
            .get();
}
```

`initialDelay(1_000)` waits about 1 second before the first poll; afterward, the 5-second fixed rate drives the cadence of subsequent runs. Integer arguments in `Pollers.fixedRate(long)` and `fixedDelay(long)` are in milliseconds. Overloads accepting `Duration` may be available depending on the Spring Integration version.

`fixedRate` is suitable when:

- You want to poll at a target cadence, such as checking status every 5 seconds.
- Work per poll is typically short and relatively stable.
- You want even scheduling anchored to expected start times.

If each poll frequently runs longer than the period, fixed rate can cause the task to run nearly continuously without the desired rest intervals. In that case, review the period, messages per poll, handler duration, or processing capacity.

## 4. cron: Run on a Wall-Clock Schedule

`cron` triggers the polling task at times matching a schedule expression. It suits work tied to specific hours or days, such as fetching a report at 01:00 daily or syncing data on business days.

A standard Spring cron expression has six fields:

```text
second minute hour day-of-month month day-of-week
```

Examples:

| Expression | Meaning |
|---|---|
| `0 */5 * * * *` | Every 5 minutes, at second 0. |
| `0 0 2 * * *` | Every day at 02:00. |
| `0 30 8 * * MON-FRI` | 08:30 Monday through Friday. |
| `0 0 0 1 * *` | 00:00 on the first day of every month. |

Java DSL example:

```java
@Bean
IntegrationFlow nightlyReconciliation(ReconciliationHandler handler) {
    return IntegrationFlow.from(
            "reconciliationQueue",
            endpoint -> endpoint.poller(
                    Pollers.cron("0 0 2 * * *")
                            .maxMessagesPerPoll(100)))
            .handle(handler, "reconcile")
            .get();
}
```

The flow above is scheduled at 02:00 in the timezone of the active trigger/scheduler. When business requirements specify a particular time zone, configure the timezone explicitly using the trigger/builder API appropriate for your Spring Integration version. Do not assume the server's timezone always matches the business timezone.

Cron follows wall-clock calendar time, not elapsed intervals. Daylight Saving Time (DST) transitions, timezone changes, or system clock adjustments can shift actual execution times. Skipped or repeated hours during DST transitions must be accounted for if a task must run once per business day. Furthermore, Spring's cron syntax can differ from Quartz or Unix cron; use Spring's six-field format rather than copying a seven-field Quartz expression.

## 5. Comparing the Three Triggers

| Criterion | `fixedDelay` | `fixedRate` | `cron` |
|---|---|---|---|
| Scheduling anchor | After the previous run completes. | By expected start times. | By calendar expression. |
| Depends on processing time? | Yes; the longer the task, the further the next run shifts. | Can be delayed if a task exceeds the period; does not run concurrently by default. | A long task can delay the next firing or wait per scheduler behavior. |
| Rest interval after task | Preserved according to configured delay. | Not guaranteed; a delayed task may run back-to-back with the next. | Depends on spacing between cron ticks. |
| Used for | Polling with a pause after processing. | Periodic tasks on a steady cadence. | Hourly/daily/weekly/monthly schedules. |
| Example | Rest 2 seconds after each queue check. | Check every 5 seconds. | Reconcile at 02:00 every day. |

No trigger alone determines throughput. Throughput also depends on messages per poll, processing time, channel, executor, number of endpoints, data source speed, and downstream limits.

## 6. maxMessagesPerPoll: Messages in One Cycle

The trigger answers "when to poll?", while `maxMessagesPerPoll` answers "how many messages at most can each polling task fetch?". These two settings must be considered together.

```java
Pollers.fixedDelay(1_000)
        .maxMessagesPerPoll(20)
```

With the configuration above, each cycle can fetch at most 20 messages. If the queue only has 3 messages, the endpoint processes 3 and finishes the fetch loop; it does not wait for 20. If the queue is always full, one cycle can process all 20 and hold the scheduler thread while the handler runs.

A lower limit keeps each poll shorter and gives the scheduler opportunities to serve other tasks, though it may reduce throughput due to per-cycle overhead. A higher limit allows larger batches, but can cause one task to hold a thread longer and increase latency for other jobs. The optimal value depends on average processing time, message size, and system load.

Some APIs support `-1` to indicate an unlimited number of messages per poll. Use it only when the source terminates the receive loop promptly and you want to drain until empty. With a source that always has data or never returns empty, an unbounded poll can hold a thread for far too long. Verify the exact semantics and default value for your endpoint type and version; when load control is needed, set an explicit bound.

## 7. initialDelay and the First Poll Time

`initialDelay` postpones the trigger's first execution by the configured duration. It is often useful when the application needs time to finish startup, connect datasources, load configuration, or wait for a dependent component to become ready.

```java
Pollers.fixedDelay(10_000)
        .initialDelay(30_000)
        .maxMessagesPerPoll(10)
```

The example above waits about 30 seconds before the first poll, then applies a 10-second fixed delay between polling tasks. `initialDelay` is neither a wait before each message nor a timeout on the receive operation.

Do not use initial delay to mask an unready dependency if the application can check readiness explicitly. For state-dependent requirements, manage lifecycle/health conditions so the endpoint starts only when the condition is truly satisfied.

## 8. Scheduler, Executor, and Processing Threads

Pollers are triggered by a `TaskScheduler`. When a trigger comes due, the scheduler runs the polling task. In simple configurations, receiving and message processing can occur on the polling task's execution thread. You can configure an executor for the poller or use an asynchronous channel to offload work to other threads.

Distinguish three thread roles:

- **Scheduler thread:** triggers the polling task according to the trigger.
- **Poller task execution thread:** runs the message-receiving logic; usually the scheduler thread if no separate executor is configured.
- **Downstream handler thread:** runs the handler; can be the poller thread or handed off to an executor via a channel like `ExecutorChannel`.

Example configuring an executor on a poller (verify builder API against your version):

```java
Pollers.fixedDelay(1_000)
        .taskExecutor(pollerExecutor)
        .maxMessagesPerPoll(10)
```

Separating an executor can increase the ability to run multiple polling tasks, but it also changes ordering, transaction context, and how errors are observed. A thread pool that is too small can make tasks queue up; a task queue that is too large accumulates latency; a queue that is too small can cause rejected executions. Do not increase thread counts before measuring poll duration, handler duration, and queue depth.

A scheduler shared across multiple pollers can also become a bottleneck if polling tasks run long. Check scheduler pool size, per-task duration, and other pollers sharing the scheduler. If using a dedicated executor for the poller, monitor both that executor and any downstream channel executor.

## 9. Transactions and Retries Around a Polling Task

A poller can be combined with an advice chain to apply transactions, retries, or cross-cutting behaviors around a poll. A transaction boundary can be configured via an appropriate transaction advice/transaction manager; retry advice can retry when receiving or processing encounters an error eligible for retry.

```java
@Bean
IntegrationFlow pollPayments(PaymentHandler handler,
                             Advice transactionAdvice) {
    return IntegrationFlow.from(
            "paymentsQueue",
            endpoint -> endpoint.poller(
                    Pollers.fixedDelay(2_000)
                            .advice(transactionAdvice)
                            .maxMessagesPerPoll(1)))
            .handle(handler, "process")
            .get();
}
```

This is an illustrative example attaching advice to a poller; `transactionAdvice` must be created with an appropriate transaction manager and scope. When processing multiple messages in one polling task, understand whether the transaction advice wraps the entire task or each receive/process step depending on endpoint and advice chain configuration. If each message requires its own transaction, configure and verify that boundary explicitly rather than inferring it from `maxMessagesPerPoll`.

Retries must also be distinguished from triggers. The trigger decides when the next polling task is scheduled; retry advice can perform multiple attempts within a single processing invocation. Do not use a short `fixedRate` in place of a retry policy, as that approach does not classify errors, does not manage cause-specific backoff, and can keep pulling new work while older messages keep failing.

## 10. Choosing a Trigger by Scenario

| Need | Recommended Choice | Reason |
|---|---|---|
| Check a queue and pause after each batch | `fixedDelay` | The pause starts after the polling task finishes. |
| Check service status at a target cadence | `fixedRate` | Easily expresses expected intervals between start times. |
| Run reconciliation at 02:00 daily | `cron` | Schedule tied to wall-clock hours/days. |
| Task with variable duration where piling up is undesirable | `fixedDelay` | Cadence naturally stretches with execution time. |
| Report on weekend business days | `cron` | Can express schedules by specific days of the week and hours. |

When choosing, answer three questions: should work trigger by elapsed interval or calendar schedule; how long can one poll take; and if a poll runs late, should the system rest, catch up, or skip the missed tick? The answers guide both trigger selection and business-aligned delay handling.

## 11. Diagnosing Mis-Scheduled or Overloaded Pollers

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Polls run slower than expected delay | Task takes long; `fixedDelay` counts delay after task completion. | Measure polling task and handler duration. |
| `fixedRate` runs nearly continuously | Task duration regularly exceeds the period. | Compare task duration to period; shrink batch or increase period. |
| Cron does not fire at expected business hour | Scheduler timezone differs from business timezone or expression is wrong. | Check six-field cron expression, timezone, and firing logs. |
| Queue grows continuously | Producer rate exceeds consumer rate; low `maxMessagesPerPoll` or slow handler. | Measure ingress/throughput, queue depth, processing time, and poll count. |
| Other pollers are also delayed | Shared scheduler thread pool occupied by long tasks. | Inspect scheduler pool, task duration, and dedicated executors. |
| Tasks rejected | Executor queue full or pool maxed out. | Inspect rejection metrics/logs, queue capacity, and worker utilization. |
| Duplicate processing or unexpected transactions | Incorrect transaction boundary, retry, or ack/receive semantics. | Inspect advice chain, transaction manager, and source mechanism. |

Diagnostic checklist:

1. Identify the endpoint type and the effective trigger applied.
2. Record start/end timestamps of polling tasks; compare against the configured period.
3. Check `maxMessagesPerPoll`, queue depth, and per-message processing time.
4. Check scheduler and executor: pool size, active threads, queued tasks, and rejected tasks.
5. For cron, verify timezone, expression, and system clock/DST changes.
6. Check transactions, retries, and error flows if messages are redelivered or fail to complete.

## 12. Self-Check

**Scenario:** A poller uses `fixedRate(2_000)` but each polling task takes around 5 seconds. Logs show the next task starting almost immediately after the previous task finishes.

1. Why is there no 2-second pause after each task?
2. If you always want a 2-second pause after a task finishes, which trigger should you use?
3. If you want to run at 02:00 daily in Vietnam time, what else must you pay attention to besides the cron expression?
4. If one poll fetches at most 50 messages, which property controls this limit?

**Suggested Answers:** (1) Fixed rate targets expected start marks; a task longer than the period delays the next run and can execute back-to-back with the previous one, though it does not run concurrently by default. (2) Use `fixedDelay(2_000)`. (3) Configure the trigger/scheduler timezone to `Asia/Ho_Chi_Minh` using the version-appropriate API. (4) `maxMessagesPerPoll(50)`.

**Hands-on Exercise:** Create a polling flow with `QueueChannel`, a handler intentionally taking about 3 seconds per message, and `maxMessagesPerPoll(2)`. Run it with `fixedDelay(1_000)` and `fixedRate(1_000)` in turn, recording start/end times of each poll. Then configure a cron expression running every minute and verify the timezone. Compare queue depth, rest intervals, scheduler threads, and throughput.

## References

- [Spring Integration Reference — Pollers](https://docs.spring.io/spring-integration/reference/endpoint.html#polling-consumer)
- [Spring Integration Reference — Configuring the Task Scheduler](https://docs.spring.io/spring-integration/reference/configuration/namespace-taskscheduler.html)
- [Spring Integration Java DSL — Pollers](https://docs.spring.io/spring-integration/reference/dsl.html)
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
