# Event-Emitting Listener Order

In a finite-running **Spring Cloud Task** application, Spring Cloud Task records the process lifecycle in **TaskRepository**; if running **Spring Batch**, Batch also records `JobExecution`, `StepExecution`, and checkpoints in **JobRepository**. When integrated with **Spring Cloud Stream**, the application can emit events from Task and Batch listeners so monitoring or orchestration services can track progress.

A common question is: *if the same Job has both a business listener and an event-emitting listener, which listener is invoked first?* Spring Cloud Task supports **`spring.cloud.task.batch.events.*-order`** properties to adjust the priority of auto-configured **Batch event listeners**. Misunderstanding this parameter easily leads to the false assumption that all messages arrive at the broker in exact order, or that changing `order` can reverse Job and Step execution order.

This lesson belongs to the **Events** chapter and explains three distinct kinds of ordering, configuration for each listener, the relationship with Task lifecycle, an `Ordered` example in Spring Batch, how to observe execution order, and delivery limits across a broker. From this, learners can pick priorities when one listener must update results before another listener emits an event, while still ensuring the task exits safely.

## 1. Three Concepts of "Order" to Distinguish

| Order Type | Question It Answers | Who Determines It? |
| --- | --- | --- |
| **Lifecycle order** | When do `beforeJob`, `beforeStep`, `beforeChunk`, item, `afterStep`, and `afterJob` occur? | Spring Batch and Step execution flow |
| **Listener priority order** | When **multiple listeners receive the same callback**, which listener executes first? | `Ordered`/composite listener mechanism and `*-order` properties |
| **Broker-to-consumer message order** | Does the receiving service see messages in the exact order they were sent? | Broker, partitions/queues, producer, consumer, retries, and topology |

**The focus of `spring.cloud.task.batch.events.*-order` is the second kind.** This property does not make a Step run before a Job, does not sort business records, and does not guarantee consumers process messages across multiple channels in a global order.

For example, a report run might produce the following callback sequence on the producer side:

~~~text
Task starts
  └─ Batch Job starts
       ├─ beforeJob
       ├─ Step A
       │    ├─ beforeStep
       │    ├─ beforeChunk
       │    ├─ item read / process / write
       │    ├─ afterChunk
       │    └─ afterStep
       ├─ Step B ...
       └─ afterJob
Task ends
~~~

The sequence above illustrates **a sequential Job with one successful chunk**. In Jobs with parallel Steps, retries, skips, rollbacks, or failing items, callbacks will be more numerous or interleaved; do not assume a single linear timeline always exists.

## 2. Which Listeners Can Emit Events?

According to the Spring Cloud Task documentation, when proper Spring Cloud Stream integration is present, Spring Cloud Task can auto-configure event-emitting listeners across multiple Batch levels:

| Batch Listener | Documented Event Channel | Example Observable Content |
| --- | --- | --- |
| `JobExecutionListener` | `job-execution-events` | Job start/end and `JobExecution` |
| `StepExecutionListener` | `step-execution-events` | Step start/end and `StepExecution` |
| `ChunkListener` | `chunk-events` | Chunk start/completion/error |
| `ItemReadListener` | `item-read-events` | Before/after item read or read error |
| `ItemProcessListener` | `item-process-events` | Before/after item process or process error |
| `ItemWriteListener` | `item-write-events` | Before/after chunk write or write error |
| `SkipListener` | `skip-events` | Record skipped per Step policy |

**Batch event listeners** differ from **`TaskExecutionListener`**. At the Task layer, Spring Cloud Task has `onTaskStartup`, `onTaskFailed`, and `onTaskEnd` callbacks, along with the Task event mechanism on the `task-events` channel. At the Batch layer, listeners are invoked along the `Job`, `Step`, `Chunk`, and `Item` lifecycle.

An application with only an `ApplicationRunner` performing a simple operation can emit Task events yet have **no Batch events**, because no Spring Batch Job runs. Conversely, if a Job has millions of items and enables both `ItemReadListener` and `ItemProcessListener`, event volume can be massive.

### Conditions for Events to Reach the Broker

Distinguish **callbacks invoked inside the JVM** from **messages sent externally**. For the documented integration mechanism, you need Spring Cloud Task, Spring Batch if Batch events are needed, Spring Cloud Stream, and a **compatible binder** (e.g., RabbitMQ or Kafka), along with channel/binding configuration for your running version.

~~~mermaid
flowchart LR
    S["Spring Cloud Task process"] --> T["TaskExecutionListener"]
    S --> J["Spring Batch Job / Step / Chunk"]
    J --> L["Batch listeners"]
    T --> O["Task event publisher"]
    L --> B["Batch event publishers"]
    O --> C[("Spring Cloud Stream binder")]
    B --> C
    C --> M[("Broker destinations")]
    M --> U["Monitoring / orchestration consumer"]
    S --> R[("TaskRepository")]
    J --> Q[("JobRepository")]
~~~

State saved in repositories and messages emitted to a broker are **two separate data streams**. A `TaskExecution`/`JobExecution` record may exist as completed while an event was lost or not yet read by the consumer.

## 3. Default Order of Batch Event Emission

Spring Cloud Task documentation specifies: **Batch event-emitting listeners default to `Ordered.LOWEST_PRECEDENCE`**.

In Spring Framework, `Ordered` uses integers to represent priority:

- **Smaller numbers** represent **higher** priority.
- `Ordered.HIGHEST_PRECEDENCE` is first priority (smallest integer value).
- `Ordered.LOWEST_PRECEDENCE` is last priority (largest integer value).

For example, suppose two `JobExecutionListener`s are registered in the same composite:

~~~text
Business listener: getOrder() = 10
Event-emitting listener: order = LOWEST_PRECEDENCE

beforeJob:
    business listener runs first
    event-emitting listener runs second

afterJob:
    in CompositeJobExecutionListener, invocation order reverses
    event-emitting listener runs first
    business listener runs second
~~~

**Key point:** Spring Batch's **`CompositeJobExecutionListener`** invokes listeners in priority order in `beforeJob`, then **reverses the order** in `afterJob`. With `CompositeStepExecutionListener`, `beforeStep` and `afterStep` follow the same pattern. This is why you cannot look solely at an `order` number and conclude an event will be emitted "before" or "after" every callback in both phases.

For `ChunkListener`, item listeners, or Batch implementations in other versions, verify exact registration, sorting, and callback timing behavior. Do not assume `afterJob`'s reversal rule applies to every callback or every middleware.

## 4. Properties for Adjusting Order

Spring Cloud Task provides **seven properties** for Batch event-emitting listener order:

~~~properties
spring.cloud.task.batch.events.job-execution-order=5
spring.cloud.task.batch.events.step-execution-order=5
spring.cloud.task.batch.events.chunk-order=5
spring.cloud.task.batch.events.item-read-order=5
spring.cloud.task.batch.events.item-process-order=5
spring.cloud.task.batch.events.item-write-order=5
spring.cloud.task.batch.events.skip-order=5
~~~

The value `5` is **illustrative only**, not a universal recommendation for every app.

| Property Suffix Under `spring.cloud.task.batch.events.` | Applies to Listener |
| --- | --- |
| `job-execution-order` | Listener emitting `JobExecution` events |
| `step-execution-order` | Listener emitting `StepExecution` events |
| `chunk-order` | Listener emitting `Chunk` events |
| `item-read-order` | Listener emitting `ItemRead` events |
| `item-process-order` | Listener emitting `ItemProcess` events |
| `item-write-order` | Listener emitting `ItemWrite` events |
| `skip-order` | Listener emitting `Skip` events |

Setting `job-execution-order=5` changes the priority of the `JobExecution` event-emitting listener **relative to other `JobExecutionListener`s in the same registration mechanism**. It does **not** guarantee Job events always reach the broker before Step events; emission timing still follows Job/Step lifecycle, and transport has its own delivery rules.

### 4.1. YAML Example

~~~yaml
spring:
  application:
    name: orders-import-task
  main:
    web-application-type: none
  cloud:
    task:
      batch:
        events:
          enabled: true
          job-execution-order: 5
          step-execution-order: 5
          chunk-order: 100
          item-read-order: 200
          item-process-order: 200
          item-write-order: 200
          skip-order: 50
~~~

This YAML illustrates **priority configuration values**. For events to actually be emitted, the application still needs Batch/Task/Stream dependencies, a binder, bindings, and auto-configured listeners matching your version. Do not assume setting `enabled: true` creates a broker or consumer endpoint.

Also do not read the table above as an execution sequence `job (5) → step (5) → skip (50) → chunk (100) → item (200)`. Each listener belongs to **a different callback type**: comparing `order` across different listener types does not sort a global queue.

### 4.2. When Should You Keep the Default?

Keeping `Ordered.LOWEST_PRECEDENCE` is usually sufficient when events only serve logging/monitoring, business listeners finish their work before returning from callbacks, and there is no special ordering requirement. Only change `*-order` when:

1. A **specific business listener** must run before or after the event-emitting listener in the **same callback phase**.
2. You have verified that your Batch version actually honors `Ordered` in the corresponding composite/registry.
3. Tests confirm the event carries the desired state and is not emitted before results are verified by the business flow.

Avoid tuning all seven properties just because one Job event needs reordering. The more callbacks you reorder, the harder it becomes to reason about a failed run.

## 5. Example: Business Listener and `JobExecution` Event Listener

Suppose `dailyReportJob` needs to send a summary event at Job end. A business listener enriches `ExitStatus` or logs reconciliation info before the summary event is created.

Write the business listener implementing `Ordered`:

~~~java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;

@Component
public class ReportAuditListener
        implements JobExecutionListener, Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void beforeJob(JobExecution execution) {
        System.out.printf("AUDIT beforeJob: jobExecutionId=%s%n",
                execution.getId());
    }

    @Override
    public void afterJob(JobExecution execution) {
        System.out.printf("AUDIT afterJob: status=%s%n",
                execution.getStatus());
        // If reconciliation is needed, place logic at a layer that already
        // has the data and knows exact transaction/commit boundaries.
    }
}
~~~

For this listener to participate, the Job must register it via Job configuration or the corresponding mechanism for your version:

~~~java
@Bean
Job dailyReportJob(
        JobRepository jobRepository,
        @Qualifier("reportStep") Step reportStep,
        ReportAuditListener reportAuditListener) {

    return new JobBuilder("dailyReportJob", jobRepository)
            .listener(reportAuditListener)
            .start(reportStep)
            .build();
}
~~~

The snippet uses the **Spring Batch 5.x** API style. `reportStep`, `JobRepository`, and Task–Batch/Stream integration infrastructure must be supplied in a complete project. Registering the business listener does not register the event-emitting listener; the event-emitting listener comes from auto-configuration.

Now examine two options **when both listeners reside in `CompositeJobExecutionListener` applying `Ordered`**:

| `ReportAuditListener` | Event-Emitting Listener | `beforeJob` | `afterJob` |
| --- | --- | --- | --- |
| `10` | `Ordered.LOWEST_PRECEDENCE` | Audit → Publish | Publish → Audit |
| `10` | `5` | Publish → Audit | Audit → Publish |

If you want **Audit's `afterJob` callback to run before the event-emitting callback**, setting `job-execution-order=5` makes sense in this composite model. However, the consequence is that **the `beforeJob` phase will emit the event before Audit runs**. Reordering can solve a goal in the `after*` phase while changing behavior in the `before*` phase; always evaluate both.

Even so, **callback order does not guarantee the event contains all committed changes**: if the Audit listener writes in a separate transaction or dispatches async work, data may not yet be ready when the publisher runs. For events serving as critical business signals, design completion evidence and recoverable emission.

### 5.1. Test Configuration

~~~properties
spring.cloud.task.batch.events.job-execution-order=5
~~~

With `ReportAuditListener` at order `10`, the expected composite sequence is:

~~~text
beforeJob:
  PUBLISHER_JOB_EVENT (order=5)
  AUDIT_BEFORE_JOB    (order=10)

afterJob:
  AUDIT_AFTER_JOB     (order=10)
  PUBLISHER_JOB_EVENT (order=5)
~~~

This is an **expectation of in-JVM callback invocations**, not a built-in log printed automatically by Spring Cloud Task, nor a prediction of the order consumers will see messages on the broker. Confirm via application logs/instrumentation in your actual version.

## 6. Batch Lifecycle Order Is Still Preserved

Whether listener order is configured as `5`, `100`, or the default, callbacks only run when Batch reaches the **corresponding lifecycle point**.

### 6.1. Job, Step, and Chunk

~~~mermaid
sequenceDiagram
    participant L as JobLauncher
    participant J as JobExecutionListeners
    participant S as StepExecutionListeners
    participant C as Chunk/Item listeners
    participant R as JobRepository

    L->>J: beforeJob
    J->>S: beforeStep
    S->>C: beforeChunk
    loop Item in chunk
        C->>C: beforeRead / afterRead
        C->>C: beforeProcess / afterProcess
        C->>C: beforeWrite / afterWrite (per chunk)
    end
    C->>C: afterChunk or afterChunkError
    C->>S: afterStep
    S->>J: afterJob
    J->>R: finalize Job metadata
~~~

The diagram shows a simple chunk-oriented Job/Step; `beforeWrite` and `afterWrite` typically fire per **item group/chunk**, not necessarily once per item. On errors with rollbacks, Spring Batch may repeat some read/process/write calls, so callback counts do not always match unique business records.

**Do not use `item-read-order=1` to "make ItemRead happen before JobExecution events"**. It only changes the position of the item-read event listener **among `ItemReadListener`s for the same callback**, if the listener mechanism applies that priority.

### 6.2. Registering Multiple Listeners of the Same Type

Spring Batch uses composite listeners to coordinate multiple callbacks. For `CompositeStepExecutionListener` and `CompositeJobExecutionListener`, the API docs clearly state **before runs in priority order, after runs in reverse order**.

If two listeners share the **same order**, or are registered via mechanisms outside the same composite, do not rely on accidental ordering from bean scan order or class names. When order truly matters, assign distinct order numbers, register explicitly, and write tests asserting the expected behavior.

Spring's `@Order` can influence how certain bean lists are sorted, but for listeners coordinated via **`Ordered`**, implementing `getOrder()` directly makes priority explicit. Do not assume `@Order` on arbitrary beans automatically controls Batch event adapters.

## 7. Distinguishing from `TaskExecutionListener` and Task Events

At the Spring Cloud Task layer, three callbacks follow this lifecycle sequence:

~~~text
Success:
  onTaskStartup → ApplicationRunner/Batch Job → onTaskEnd

Unhandled failure:
  onTaskStartup → ApplicationRunner/Batch Job fails
                → onTaskFailed → onTaskEnd
~~~

The Task documentation states:

- `onTaskStartup`/`@BeforeTask` runs during startup, before the repository records the startup state.
- `onTaskFailed`/`@FailedTask` runs when an unhandled exception occurs, **before `onTaskEnd`**.
- `onTaskEnd`/`@AfterTask` runs before the repository updates the final state.

Across release versions, exact ordering between `TaskExecution` creation and startup callbacks should be verified against the implementation; what matters for Task authors is that startup callbacks run before runners, and end callbacks run before the final completion state. An abnormally killed process may **skip** the end callback.

### 7.1. `exitMessage` Priority Is a Different Mechanism

If multiple Task callbacks set `exitMessage`, Spring Cloud Task defines a storage precedence:

~~~text
onTaskEnd  >  onTaskFailed  >  onTaskStartup
~~~

This means a message set by `onTaskEnd` can overwrite an earlier failure message. **This is the priority of the `exitMessage` field in `TaskRepository`**, not the `spring.cloud.task.batch.events.*-order` properties.

For example, avoid writing a summary listener like:

~~~java
@AfterTask
public void after(TaskExecution execution) {
    execution.setExitMessage("SUCCESS"); // Wrong if Job/Task already failed.
}
~~~

Only record success after checking status, and preserve existing failure messages. Setting `exitMessage="SUCCESS"` also **does not change the exit code** from failure to success.

### 7.2. Task Events Differ from Batch Events

Spring Cloud Task has a mechanism to emit **`TaskExecution` events** on the `task-events` channel at **start and end** when integrated with Spring Cloud Stream. That mechanism uses a framework-provided task listener.

~~~properties
# Disable emitting Task events via Stream if not needed:
spring.cloud.task.events.enabled=false

# Disable Batch events integrated by Task:
spring.cloud.task.batch.events.enabled=false
~~~

The two flags control **two separate event groups**. Disabling event emission does not disable `TaskRepository` or `JobRepository` metadata persistence. Nor is there any reason to invent a property like `spring.cloud.task.events.job-execution-order`: `job-execution-order`, `step-execution-order`, etc., are documented under the **`spring.cloud.task.batch.events`** prefix.

Within the same process, the Task **start** event occurs during Task startup, while Batch Job events belong to the Job run inside. The Task **end** event relates to process completion. Still, consumers reading from different topics/queues are **not guaranteed** to receive events in the same order as internal callbacks.

## 8. Emission Order vs. Broker Receipt Order

Suppose listeners inside a Pod fire in sequence:

~~~text
T1  JobExecutionListener.beforeJob → sends JOB_STARTED
T2  StepExecutionListener.beforeStep → sends STEP_STARTED
T3  StepExecutionListener.afterStep  → sends STEP_COMPLETED
T4  JobExecutionListener.afterJob   → sends JOB_COMPLETED
~~~

A consumer can **observe a different order** when:

- `job-execution-events` and `step-execution-events` travel through **two destinations**.
- Messages are routed to **multiple partitions** or different queues.
- Producers resend, consumers retry, or dead-letter/replay happens.
- Multiple worker instances emit events concurrently.
- Events are sent successfully yet the consumer processes slowly or hits transient errors.

For instance, the consumer sees `STEP_COMPLETED` before `JOB_STARTED` because two channels process at different speeds. That **does not prove Batch ran the Step before the Job**.

If business logic requires processing events **with before/after ordering**, each event should carry:

| Field | Purpose |
| --- | --- |
| `taskExecutionId` | Links to a single Spring Cloud Task run, if present |
| `jobExecutionId` | Groups events of the same Batch Job run |
| `stepExecutionId` or Step name | Distinguishes events by Step |
| `eventType` | `JOB_STARTED`, `STEP_COMPLETED`, `JOB_COMPLETED`, ... |
| `eventTime` | Aids investigation, **does not guarantee strict ordering** |
| `sequence` within a controlled scope | Used when the producer can genuinely assign sequence numbers |
| `eventId` | Prevents duplicate processing on the consumer |

This is a **suggested data model** for a custom event envelope; these fields are **not a guarantee** that Spring Cloud Task emits all of them by default with exact names.

### 8.1. Designing Consumers to Tolerate Out-of-Order Events

A consumer managing a dashboard should read events **idempotently** and tolerate late arrivals:

1. Classify events by `eventType`, identifying `JobExecution` ID and related IDs.
2. Check `eventId` to avoid processing twice.
3. Advance progress only if the event represents a newer state under **valid state transition rules**, not merely by timestamp.
4. If `JOB_COMPLETED` arrives before `STEP_COMPLETED`, still handle the late Step event cleanly.
5. When an **authoritative final state** is needed, query `JobRepository`/`TaskRepository` or business tables rather than trusting a single message.

When using a broker with **per-partition ordering**, choosing a stable partition key for the same `JobExecution` ID can preserve order **within that scope**. There is still no global ordering guarantee across partitions/topics/destinations; retries and reprocessing on the consumer still require idempotency.

### 8.2. Does an Emitted Event Mean Data Committed?

**Not always.** Listeners may fire **before** metadata status or business transactions finish committing, depending on callbacks and integration setup. A `JOB_COMPLETED` message appearing on the broker should not automatically be treated as proof that another report table was durably written.

For events carrying business decisions such as "report published", use a more reliable pattern, such as:

- Writing **`READY` status** and an **outbox event** in the same business database transaction.
- Having a worker publish from the outbox post-commit with retries and idempotency keys.
- Having the consumer verify the artifact/report key exists rather than re-emitting notifications indefinitely.

Configuring `*-order` can sort callbacks, but **it does not replace distributed transactions, outboxes, or result verification**.

## 9. Adjusting Priority Per Event Type

You do not need to enable all high-granularity events. You can use these flags:

~~~properties
spring.cloud.task.batch.events.enabled=true

# Only need Job + Step events; disable Item/Chunk/Skip if unneeded:
spring.cloud.task.batch.events.chunk.enabled=false
spring.cloud.task.batch.events.item-read.enabled=false
spring.cloud.task.batch.events.item-process.enabled=false
spring.cloud.task.batch.events.item-write.enabled=false
spring.cloud.task.batch.events.skip.enabled=false

# Adjust Job event listener priority relative to business listeners:
spring.cloud.task.batch.events.job-execution-order=5
spring.cloud.task.batch.events.step-execution-order=20
~~~

`enabled` flags control **whether that event type is emitted**, while `*-order` controls the **priority of the event-emitting listener** within the registration mechanism. If an event type is disabled, setting `*-order` for it generally has no operational effect.

In production environments, emitting events for **every item** can generate huge message traffic. For example, 10 million items with read, process, and write events can produce many millions of messages depending on callbacks, retries, and config. Plan broker capacity, retention, serialization cost, and consumer load; when only batch-level progress is needed, Chunk/Step events or aggregated metrics are preferable.

### 9.1. Routing Different Destinations

Spring Cloud Task allows configuring bindings/destinations for Batch events via Spring Cloud Stream. For instance, to change the Step event binding name, the documentation describes:

~~~properties
spring.cloud.task.batch.events.step-execution-events-binding-name=my-step-execution-events
~~~

Then configure the corresponding Spring Cloud Stream binding per model and version, such as `spring.cloud.stream.bindings.my-step-execution-events.destination=monitoring-step-events`.

**Changing the destination does not alter callback order.** Conversely, changing `step-execution-order` does not move messages to another topic. The two mechanisms are configured independently.

## 10. Common Scenarios and How to Handle Them

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| No Batch events seen at all | Missing Task–Batch/Stream dependency, binder, or binding; feature disabled | Check startup logs, classpath, `spring.cloud.task.batch.events.enabled` |
| Task event present but no Job event | Task ran without launching a Batch Job or missing Batch integration | Check `JobExecution` in `JobRepository` |
| Event emitted before audit listener in `afterJob` | Publisher listener defaults to lowest priority, `after` callbacks reverse | Verify composite/registration; test `job-execution-order=5` vs. audit `10` |
| Changing `job-execution-order` shows no effect | Different listener type/composite, or listener not registered | Check Spring Batch listeners, dependencies, effective config |
| `STEP_COMPLETED` reaches consumer before `JOB_STARTED` | Different topics/queues, latency, retries | Separate **producer callback order** from **consumer delivery order** |
| Duplicate events received after retry | Broker redelivery or consumer processed before ack failed | Use `eventId` / idempotent processing |
| Task/Job `FAILED` yet dashboard stays green | Consumer judges by message presence instead of authoritative status | Reconcile `TaskRepository`, `JobRepository`, exit codes |
| Step fails and no successful `afterChunk` event appears | Error/rollback triggered error callback | Check `afterChunkError`, retry/skip policies |
| Changing `*-order` alters event count | Callback order affected other logic, or listener threw errors | Test business listener independently; avoid side-effect coupling |
| Slow consumer causes queue backlog | Overly granular events enabled or under-provisioned consumer | Disable unneeded event types; aggregate by Step/Chunk |

### When a Listener Throws an Exception

Spring Cloud Task notes that an exception in a **`TaskExecutionListener`** can **stop remaining listeners for the same callback** and also affect the Task's outcome/exit code. With Batch listeners, exceptions can also impact Steps/Jobs depending on callback type and handling.

Therefore, **observability listeners should be brief, stable, and avoid synchronous reliance on unreliable networks**. Never make a multi-second external API call inside `beforeJob` just to log; if the API slows or fails, the entire Job can suffer.

Do not swallow every exception and report "event succeeded" when the message never arrived. Clarify event reliability requirements: best-effort observability vs. mandatory business output. For the latter, use an outbox/idempotency and reconciliation processes.

## 11. Practice Lab: Measuring Listener Order and Verifying the Broker

Design a Spring Cloud Task `daily-report-task` running a `Job` with one `Step` that builds a report from 1,000 records. The Job has:

- `AuditJobListener`: implements `JobExecutionListener` and `Ordered` with `getOrder()=10`.
- Spring Cloud Task's `job-execution-events` listener when Stream is integrated.
- A business `StepExecutionListener` recording processed record count.
- A consumer reading Job/Step events and logging `JobExecution` IDs.

Run the following experiments:

| Experiment | Configuration | What to Observe |
| --- | --- | --- |
| **A — Default** | Do not set `job-execution-order` | Event listener uses `LOWEST_PRECEDENCE` when auto-configured; observe before/after Audit |
| **B — Change priority** | `job-execution-order=5`, Audit `10` | `beforeJob` and `afterJob` phases swap relative positions per composite |
| **C — Change Step listener** | `step-execution-order=5` | Affects only Step event listener priority, does not alter Job event order |
| **D — Disable Item events** | `item-read.enabled=false` | No read events on that channel, Job/Step events still appear |
| **E — Separate destinations** | Route Job/Step to two queues/topics | Consumer may observe lag/interleaving; compare with producer callback logs |
| **F — Failure scenario** | Make Step throw an exception | Job/Task must report failure properly; do not assume all success callbacks run |
| **G — Redelivery** | Trigger consumer retry on same message | Consumer must not update progress twice for the same event |

### 11.1. Listener Logging for Local Observation

Simple Java example used in a test Job with the listener registered:

~~~java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.core.Ordered;

public class AuditJobListener
        implements JobExecutionListener, Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void beforeJob(JobExecution execution) {
        System.out.printf("AUDIT beforeJob id=%s%n", execution.getId());
    }

    @Override
    public void afterJob(JobExecution execution) {
        System.out.printf("AUDIT afterJob id=%s status=%s%n",
                execution.getId(), execution.getStatus());
    }
}
~~~

You must **add your own logging/instrumentation at the emission point** or use Spring Cloud Stream tracing to compare when the publisher runs; Spring Cloud Task does not automatically print the `PUBLISHER_JOB_EVENT` lines shown in the earlier example. Run tests against a test broker and a short sample Job for easy observation.

### 11.2. Interpreting Results Correctly

A thorough analysis must distinguish:

1. **Callback order**: Audit/publisher are called per `Ordered` inside the composite; for Job listeners, `beforeJob` and `afterJob` reverse direction.
2. **Lifecycle order**: `beforeJob` runs before Step execution; `afterJob` runs after that Job's Steps finish.
3. **Message delivery order**: consumers do not automatically see two separate channels in the same order as producer callbacks.
4. **Result correctness**: events serve observability; `JobExecution`, `TaskExecution`, and business result tables still need reconciliation.
5. **Failure behavior**: throwing listeners, broker disconnects, or killed processes can cause missing events, so independent monitoring is required.

## 12. Key Takeaways

- **Batch event emission priority** is configured via `spring.cloud.task.batch.events.*-order` for Job, Step, Chunk, ItemRead, ItemProcess, ItemWrite, and Skip. **Default is `Ordered.LOWEST_PRECEDENCE`**.
- **Smaller `order` numbers mean higher priority.** With `CompositeJobExecutionListener`/`CompositeStepExecutionListener`, **before runs in priority order, after runs in reverse order**.
- This property only adjusts the **event-emitting listener**; it does not alter Step execution order or guarantee messages across a broker are consumed in identical order.
- `TaskExecutionListener` with `onTaskStartup`, `onTaskFailed`, and `onTaskEnd` belongs to the Task lifecycle; the `*-order` properties above belong to **Batch event listeners**, while `exitMessage` precedence is a separate mechanism.
- **Spring Cloud Task manages process lifecycle**, **Spring Batch manages Jobs/Steps**, and **Spring Cloud Stream/broker** delivers messages. Monitoring and delivery guarantees must account for all three layers.
- Events can **arrive late, duplicate, or go missing**. For mandatory business decisions, use an outbox, idempotency, commit verification, and repository reconciliation.
- Before changing order, verify **listener registration, versions, binder, callback logs, and execution status** in a test environment.

### Official References

- [Spring Cloud Task — Spring Cloud Stream Integration: Emit Order for Batch Events](https://docs.spring.io/spring-cloud-task/reference/stream.html)
- [Spring Cloud Task — Features: Task Execution Listener](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Batch — CompositeJobExecutionListener Javadoc](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/listener/CompositeJobExecutionListener.html)
- [Spring Batch — CompositeStepExecutionListener Javadoc](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/listener/CompositeStepExecutionListener.html)
- [Spring Batch — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/intercepting-execution.html)
