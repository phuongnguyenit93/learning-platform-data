# Should You Wait for Every Recipient?

## 1. Short Answer: It Depends on What Completion Means

In **Recipient List** (an Enterprise Integration Pattern), one message is sent to **a set of recipients** determined by configuration or conditions. However, sending to multiple recipients **does not automatically mean waiting for all of them to finish**, nor does it mean the framework automatically combines their results into a single response.

You must decide based on the business contract:

- **Do not wait for every recipient** if each branch is an independent task—such as updating metrics, sending non-critical notifications, or collecting telemetry; the main request can proceed once a clearly defined **acceptance milestone** is reached.
- **Wait for all results** if the next decision requires all independent conditions to pass—for example, confirming an order only after both **inventory check** and **fraud check** complete.
- **Wait only for a subset**, or apply a **quorum rule**, when business rules allow. In that case, also design handling for incomplete branches, late replies, and partial failures.

The word "wait" must be defined precisely: **wait for the message to be handed off to the channel**, **wait for the handler to receive it**, **wait for the handler to finish**, or **wait for side effects to commit and be durably recorded**? These four milestones are not the same.

In the `SPRING_INTEGRATION_PATTERN` module, we use Spring Integration to implement Enterprise Integration Patterns, building loosely coupled and extensible messaging flows. Recipient List connects closely with Router, Filter, Transformer, Gateway, Splitter, Aggregator, retry, error channels, and correlation—especially when multiple branches must be tested and observed independently.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish **fan-out**, **dispatch acknowledgement**, and **business completion**.
2. Explain why waiting behavior depends on channel type and execution model, not merely on having a Recipient List.
3. Configure a Recipient List Router in Spring Integration Java DSL.
4. Know when to choose fire-and-forget, synchronous execution, Scatter–Gather, or Aggregator.
5. Design correlation, release strategy, timeouts, missing results, late results, retries, and idempotency.
6. Test per-recipient behavior without confusing "sent" with "processed."

## 2. Recipient List: One Message, Multiple Receiving Targets

### 2.1. Basic Diagram

~~~mermaid
flowchart LR
    P[Order Gateway / Publisher] --> I[(orders.received)]
    I --> R{Recipient List Router}
    R -->|Audit| A[(orders.audit)]
    R -->|Notification| N[(orders.notification)]
    R -->|Analytics| M[(orders.analytics)]
    A --> HA[Audit Handler]
    N --> HN[Notification Handler]
    M --> HM[Metrics Handler]
~~~

Here, the Router determines the **list of target channels**; handlers connected to each channel perform the actual processing. A message can be sent to all targets or a conditional subset. Recipient selection order and handler completion are **two separate concerns**.

Example for a newly created order:

| Recipient | Work | Must it complete before returning the order-creation API response? |
|---|---|---|
| `orders.audit` | Record event trail for traceability | Depends on compliance requirements and write guarantees. |
| `orders.notification` | Notify the user | Usually does not need to block order creation, provided reliable delivery exists. |
| `orders.analytics` | Daily statistics | Usually no; delayed processing is acceptable. |
| `orders.inventoryCheck` | Verify stock availability | Yes, **if** the response contract states "order confirmed in stock." |
| `orders.fraudCheck` | Score risk | Yes, **if** approval depends on this result. |

You cannot decide "all recipients must complete" simply because the list has three items. Define the **business completion condition** first, then select the technical mechanism.

### 2.2. Recipient List vs. Content-Based Router and Publish–Subscribe

| Pattern | Core Behavior | Appropriate When |
|---|---|---|
| **Content-Based Router** | Chooses a channel based on content/headers, commonly a single branch. | High-value order → review; normal order → automated processing. |
| **Recipient List Router** | Determines a list of recipients, optionally with conditions. | Send to audit and notification; also send to compliance for international orders. |
| **Publish–Subscribe Channel** | Broadcasts to registered subscribers of a channel. | Multiple independent listeners care about the same event. |
| **Scatter–Gather** | Distributes a request to multiple parties and gathers replies per policy. | Business decision only after both inventory and fraud checks finish. |
| **Splitter / Aggregator** | Splits a message into parts and gathers correlated results. | A multi-line order needs processing results for all line items. |

A Recipient List Router **is not automatically an Aggregator**. It selects targets; waiting for multiple results requires a separate aggregation component or mechanism.

### 2.3. Not every recipient receives the message in every situation

The configured list is a **distribution intent**, not a guarantee that all targets processed the message:

- A recipient may be excluded by a condition.
- A target channel may not exist or may have no running consumer.
- A queue may be full; an executor may reject tasks.
- A synchronous handler may throw an exception, affecting dispatch to subsequent targets depending on configuration.
- An asynchronous recipient may accept the message into a queue and fail later.

Therefore, never record "processed by all recipients" merely because the Router selected three channels.

## 3. Four Completion Milestones Often Confused

To decide **whether to wait or not**, distinguish these milestones:

| Milestone | Example | Sufficient to declare business success? |
|---|---|---|
| **1. Recipient selected** | Router computes `audit, notification, analytics`. | Not yet; only a destination decision. |
| **2. Message dispatched/accepted** | Send to channel succeeded or executor accepted task. | Not necessarily; may still be waiting to run. |
| **3. Handler completed** | Handler finished running and returned. | Depends; external side effects may still lack commit/ack. |
| **4. Durable/business outcome committed** | Transaction recorded or broker/database confirmed per contract. | Stronger, though still depends on delivery/idempotency and final contract. |

Example of creating an order via API:

~~~text
POST /orders
    |
    +-- Order persisted (committed)
    |
    +-- Recipient List
          |-- audit
          |-- email
          |-- analytics
~~~

If the API contract only requires confirming **the order was saved** and remaining tasks can run later, waiting for email/analytics is unnecessary. However, if compliance requires **durable audit persistence before confirmation**, merely sending an audit message to an in-memory queue is insufficient. You need guarantees at the proper storage layer—for example, a transaction with an outbox or a designed durable recording mechanism.

### 3.1. Three concepts frequently conflated

**Fire-and-forget:** the sender does not expect a business reply from each recipient. This **does not guarantee** sending never blocks: a synchronous `DirectChannel` can still block the sending thread until the handler finishes.

**Async dispatch:** submitting a task to an executor/broker for later execution. The sender can return early once work is accepted, yet **there is no guarantee the handler succeeded** and no automatic durability.

**Wait-for-all:** needing to gather results from the expected recipient set. Requires **correlation**, a completeness policy, timeouts, and missing/error handling. A Router emitting multiple messages **does not automatically create** a wait-for-all contract.

### 3.2. "Wait for all" must define what "all" means

A Recipient List can select dynamically. For example:

~~~text
Domestic order:
  expected recipients = {inventory, fraud}

International order:
  expected recipients = {inventory, fraud, compliance}
~~~

If the Aggregator always waits for **three** results for both order types, domestic orders with only two recipients will never finish. `expectedRecipients` must be fixed **per request** at fan-out time and passed to the aggregation step in a reliable format.

## 4. Waiting Behavior Depends on Channel Type and Execution Model

### 4.1. Two flows that look similar yet have different semantics

~~~mermaid
flowchart TD
    subgraph S[Synchronous DirectChannel]
        P1[Producer] --> R1[Recipient List]
        R1 --> D1[DirectChannel audit]
        R1 --> D2[DirectChannel notify]
        D1 --> H1[Handler audit]
        D2 --> H2[Handler notify]
    end
    subgraph A[Asynchronous ExecutorChannel]
        P2[Producer] --> R2[Recipient List]
        R2 --> E1[ExecutorChannel audit]
        R2 --> E2[ExecutorChannel notify]
        E1 --> Q1[Executor task audit]
        E2 --> Q2[Executor task notify]
    end
~~~

When recipients go through `DirectChannel` with synchronous handlers, the send call may only complete **after synchronously dispatched handlers finish running**, assuming no error interrupts the path. That is a consequence of **channel/handler synchronous semantics**, not a "wait for all results" feature of Recipient List.

With `ExecutorChannel` or queue/poller setups, `send` can complete as soon as the task is **accepted**, while business handlers have not started or are still running. When an async branch fails, the original caller usually does not receive an exception directly on the same call stack; you must design appropriate error/recovery/notification flows.

### 4.2. Channel Selection Table

| Channel/Consumer Type | When Send Succeeds | What Must Not Be Inferred |
|---|---|---|
| `DirectChannel` + synchronous handler | Synchronous dispatch/handler on the call path completed without error. | Does not assume external side effects committed durably across all systems. |
| `ExecutorChannel` | Executor may have accepted the task per its rejection policy. | Does not mean the handler finished or worker thread kept caller's MDC/transaction. |
| `QueueChannel` + poller | Message was enqueued if `send` actually returned true. | Does not mean a handler polled/committed or in-memory queue survives restarts. |
| Broker/JMS/Kafka/AMQP | Confirmed per the corresponding producer/adapter/broker contract. | Does not mean consumers completed business work or redelivery cannot duplicate. |
| Synchronous `PublishSubscribeChannel` | Subscribers were dispatched per policy and context. | Does not mean all subscribers produced aggregatable replies or avoided partial errors. |

**Note:** An asynchronous mechanism can still **block or reject under overload** if the task queue fills up, the broker slows down, backpressure applies, or the rejection policy runs tasks on the caller thread. "Async" does not mean "never waits."

### 4.3. Impact on latency

Suppose three recipients take 25 ms, 80 ms, and 150 ms:

- If processed **sequentially and synchronously**, dispatch time is roughly the sum of steps: around **255 ms**, excluding overhead.
- If tasks truly execute **in parallel** and you must wait for all of them, ideal completion time is roughly the slowest step: **150 ms**, plus overhead and resource contention.
- If **dispatched asynchronously without waiting for results**, the response can return earlier, yet it only confirms **acceptance**, not that all three recipients finished processing.

This is an illustrative comparison of models, **not a latency guarantee of Spring Integration**: thread pools, transactions, network calls, conditional branches, and real load can change results.

## 5. Configuring Recipient List with Spring Integration Java DSL

### 5.1. Problem

After an order is recorded, the application wants to independently notify **audit** and **notification**. The initial example uses two `DirectChannel`s to highlight fan-out; no combined business reply is needed.

~~~mermaid
flowchart LR
    P[Producer] --> I[(orders.received)]
    I --> R[Recipient List Router]
    R --> A[(orders.audit)]
    R --> N[(orders.notify)]
    A --> HA[Audit handler]
    N --> HN[Notification handler]
~~~

The example targets **Java 17+, Spring Boot 3.x, and Spring Integration 6.x** with the `spring-boot-starter-integration` dependency. Types can live in the same package; top-level `public` types should be placed in separate Java files as appropriate in your project.

### 5.2. Basic Java DSL Fan-Out

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

record OrderCreated(String eventId, String orderId) {}

final class RecipientProbe {
    final AtomicInteger audits = new AtomicInteger();
    final AtomicInteger notifications = new AtomicInteger();

    void audit(OrderCreated event) {
        audits.incrementAndGet();
    }

    void notifyUser(OrderCreated event) {
        notifications.incrementAndGet();
    }
}

@Configuration
@EnableIntegration
class RecipientListConfiguration {

    @Bean(name = "orders.received")
    MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "orders.audit")
    MessageChannel auditChannel() {
        return new DirectChannel();
    }

    @Bean(name = "orders.notify")
    MessageChannel notifyChannel() {
        return new DirectChannel();
    }

    @Bean
    RecipientProbe recipientProbe() {
        return new RecipientProbe();
    }

    @Bean
    IntegrationFlow distributeOrder() {
        return IntegrationFlow.from("orders.received")
                .routeToRecipients(routes -> routes
                        .recipient("orders.audit")
                        .recipient("orders.notify"))
                .get();
    }

    @Bean
    IntegrationFlow auditFlow(RecipientProbe probe) {
        return IntegrationFlow.from("orders.audit")
                .handle(OrderCreated.class, (event, headers) -> {
                    probe.audit(event);
                    return null; // One-way handler; no reply emitted.
                })
                .get();
    }

    @Bean
    IntegrationFlow notificationFlow(RecipientProbe probe) {
        return IntegrationFlow.from("orders.notify")
                .handle(OrderCreated.class, (event, headers) -> {
                    probe.notifyUser(event);
                    return null;
                })
                .get();
    }
}
~~~

**Reading the example correctly:**

- `.routeToRecipients(...)` defines a **Recipient List Router**, here with two static recipients.
- Both `DirectChannel` beans are target channels; the last two `IntegrationFlow` beans register separate consumers.
- `RecipientProbe` only increments counters for lesson observation. A real application must replace it with audit/notification services and design side effects, retries, tracing, and security.
- Handlers use `return null` to finish **one-way** processing; do not attempt to return two distinct replies to the same Gateway.
- Because both branches use `DirectChannel`, the demo can observe both handlers ran when `send` succeeds and returns without error; do **not** generalize this to asynchronous branches.

### 5.3. Sending a message from a producer

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

boolean accepted = input.send(
        MessageBuilder.withPayload(
                new OrderCreated("EVT-1001", "ORD-1001"))
                .setHeader("traceId", "trace-ord-1001")
                .build(), 1_000);

// In the demo's DirectChannel configuration,
// check both counters in tests to verify fan-out.
~~~

`accepted` is the result of **sending into the flow** under the semantics of the channels and connected endpoints. Do not turn this boolean into "the user received the email and audit committed durably"; those two conclusions require separate evidence from each corresponding recipient.

### 5.4. Dynamic and conditional recipients

In addition to static lists, a Recipient List can select **a subset** conditionally. For example:

~~~text
OrderCreated
  -> orders.audit            (all orders)
  -> orders.notify           (if customer enabled notifications)
  -> orders.exportCompliance (if international order)
~~~

Conditions must be evaluated from **verified payload/headers**, never trusting arbitrary external flags for security-sensitive checks. When selecting targets conditionally, record the **expected recipient set for each event** if results must be aggregated later; do not assume a constant recipient count for every request.

In Java DSL, you can configure conditional recipients matching your Spring Integration version. Because expression syntax and overloads differ across DSL versions, the `routeToRecipients` example above keeps a static list to illustrate the core mechanism clearly; write dedicated tests for conditional logic rather than assuming an untested expression always works.

## 6. Not Waiting for Every Recipient: Controlled Fire-and-Forget

### 6.1. When is it appropriate?

Tasks such as sending emails, updating dashboards, and analytics usually **do not determine** the validity of the primary transaction. After saving an order, the application can publish an event and respond without waiting for all receivers to finish.

~~~mermaid
sequenceDiagram
    participant API
    participant DB
    participant OUT as Outbox / Broker
    participant A as Audit Consumer
    participant N as Notification Consumer
    API->>DB: Commit order
    API->>OUT: Write/emit event per delivery contract
    OUT-->>API: Confirm acceptance per contract
    API-->>API: Respond acknowledged
    OUT->>A: Delivery (may be delayed)
    OUT->>N: Delivery (may be delayed)
~~~

This diagram illustrates a **design target**, not a guarantee that simply using `RecipientListRouter` automatically provides an outbox, broker, or atomic commit. When events must not be lost across restarts or between DB commit and publish, consider a **transactional outbox** or an equivalent mechanism with verified delivery semantics.

### 6.2. Moving one recipient to async execution

The example in Section 5 currently uses a `DirectChannel` for `orders.notify`. To offload that work to an executor, you can **replace** that channel bean definition with:

~~~java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.messaging.MessageChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Bean
ThreadPoolTaskExecutor notificationExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(50);
    executor.setThreadNamePrefix("notify-");
    executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy());
    executor.initialize();
    return executor;
}

@Bean(name = "orders.notify")
MessageChannel asyncNotificationChannel(
        ThreadPoolTaskExecutor notificationExecutor) {
    return new ExecutorChannel(notificationExecutor);
}
~~~

This is a **replacement configuration**; do not keep both synchronous and asynchronous `orders.notify` beans with the same name in one context. With an executor, `send` usually finishes after the task is accepted without waiting for the notification handler to finish; when the executor saturates, `AbortPolicy` can reject and raise an exception via Spring infrastructure. `ExecutorChannel` is **not** a durable message store: restarts can lose in-memory queued tasks.

### 6.3. Fire-and-forget does not mean ignoring errors

If email fails after the API responded, the system must have **observability and recovery**:

- Attach a stable event/business ID so retries do not send unintended duplicates.
- Track enqueue results, backlog, retry counts, timeouts, and per-recipient error handling.
- Decide whether dead-letter/quarantine storage is needed.
- Never claim "all notifications sent" when only the event was emitted.
- Define queue/executor bounds, backpressure, and behavior when a recipient is slow.

Fire-and-forget only removes the **waiting constraint on the primary response path**, not operational responsibility for the branches.

## 7. Needing to Wait for Every Recipient: Scatter–Gather and Aggregator

### 7.1. An example requiring all results

Suppose the `confirmOrder` API may only return `CONFIRMED` after:

- The **inventory** system confirms sufficient stock.
- The **fraud** system confirms the order is not rejected.

With only one result, the system cannot decide to confirm the order yet. You need **Scatter–Gather**: *scatter* sends the request to recipients, and *gather* collects replies for that specific request. Recipient List can participate in the **scatter** phase, yet **Recipient List Router alone is not enough**.

~~~mermaid
flowchart TD
    G[Gateway confirmOrder] --> S[Scatter to 2 recipients]
    S --> F[Fraud Check]
    S --> I[Inventory Check]
    F --> FR[FraudResult + correlation]
    I --> IR[InventoryResult + correlation]
    FR --> A[Aggregator / Gatherer]
    IR --> A
    A --> D{Complete per release policy?}
    D -->|Not yet| W[Wait more / timeout]
    D -->|Complete| O[CombinedDecision]
    O --> G
~~~

Spring Integration provides **Scatter–Gather** and **Aggregator** components supporting this pattern. Depending on the scatterer type (Recipient List, Publish–Subscribe, or other configurations), design how replies, correlation, and sequences are formed. Do not merely call `routeToRecipients(...)` and expect a list of responses automatically.

### 7.2. Four components you must define

1. **Expected recipient set to await**: `{inventory, fraud}` for this request. With conditional selection, this set varies per message and must be locked in at fan-out time.
2. **Correlation key**: e.g., a unique `validationRequestId` per check attempt. Using bare `orderId` across concurrent check attempts can mix replies from different attempts.
3. **Release strategy**: when is a group considered complete? One **valid result from every required recipient**, a quorum, or does a single `FAIL` justify rejecting early?
4. **Group expiration and reply contract**: on expiration, return failure, return partial results, or hand off to recovery? How are late messages handled?

An example request:

~~~text
validationRequestId = check-ORD-1001-v3
expectedRecipients  = {inventory, fraud}
deadline            = 2026-11-21T10:00:05+07:00

inventory -> PASS, validationRequestId=check-ORD-1001-v3
fraud     -> PASS, validationRequestId=check-ORD-1001-v3

Aggregator -> CONFIRMED
~~~

The timestamp in the example is **illustrative data**, not a default Spring Integration deadline. `validationRequestId` must propagate across adapters and be checked at the gatherer; never assume message IDs stay intact across external systems.

### 7.3. Correlation vs. message ID

| ID Type | Purpose | Risk When Misused |
|---|---|---|
| `orderId` | Identifies the order. | Two verification rounds for the same order can be merged together. |
| `messageId` | One specific message. | Each recipient/reply may construct a new message with a different ID. |
| `validationRequestId` | Groups one verification attempt for aggregation. | Must avoid collisions across attempts and survive transport boundaries. |
| `traceId` | Traces execution across steps. | Using trace ID as release key can accidentally merge groups within the same trace. |
| `recipientId` | Identifies which branch produced a result. | If you only count messages, duplicates from one branch look like two results. |

For accuracy, a release strategy usually needs to **count unique responding recipients**, not just message count. For example, if inventory sends two duplicate replies while fraud has sent none, message count is 2, yet two recipients have **not** responded.

### 7.4. Illustrating the aggregation policy in plain Java

The code below illustrates **business logic after the Aggregator has collected** a set of results. It does not replace configuring Spring Integration's `AggregatingMessageHandler`, `MessageGroupStore`, or Scatter–Gather:

~~~java
import java.util.Map;
import java.util.Set;

enum CheckStatus { PASS, FAIL, TIMEOUT }

record CheckResult(
        String validationRequestId,
        String recipientId,
        CheckStatus status) {}

record CombinedDecision(String requestId, boolean confirmed) {}

final class DecisionPolicy {
    private static final Set<String> REQUIRED =
            Set.of("inventory", "fraud");

    CombinedDecision combine(
            String requestId,
            Map<String, CheckResult> latestByRecipient) {

        if (!latestByRecipient.keySet().containsAll(REQUIRED)) {
            throw new IllegalStateException(
                    "Required recipients have not all responded");
        }

        boolean allPassed = REQUIRED.stream()
                .map(latestByRecipient::get)
                .allMatch(result ->
                        requestId.equals(result.validationRequestId())
                                && result.status() == CheckStatus.PASS);

        return new CombinedDecision(requestId, allPassed);
    }
}
~~~

**Meaning:**

- Using `Map<recipientId, CheckResult>` confirms **each recipient has a result**, rather than just checking collection size.
- `combine` only receives inputs already grouped by the right request. **Collecting messages, waiting, locking groups, and expiration** are integration-layer Aggregator/Scatter–Gather configuration responsibilities.
- In production, verify the key set **contains no spoofed results**, each recipient has trusted identity and status, and duplicate results follow an explicit policy.
- `confirmed=false` alone does not explain why. Production systems typically return status and error codes like `FRAUD_REJECTED`, `OUT_OF_STOCK`, or `CHECK_TIMEOUT` to distinguish business declines from infrastructure failures.

### 7.5. Do you really have to wait for *every* recipient if one branch already rejected?

Not always. If a `FAIL` result definitely causes the transaction to be rejected, you can use **fail-fast**: emit an early rejection without waiting for remaining checks, **provided** unfinished branches can be cancelled or safely left to complete and business rules allow it.

Example:

| Inventory | Fraud | Decision | Need to keep waiting? |
|---|---|---|---|
| PASS | PASS | CONFIRMED | Both results received; complete. |
| FAIL | Not yet received | REJECTED_OUT_OF_STOCK | Can fail-fast if business rules allow. |
| Not yet received | FAIL | REJECTED_FRAUD | Can fail-fast, though in-flight work still needs control. |
| PASS | Not yet received | Incomplete | Must wait for fraud or timeout. |
| TIMEOUT | PASS | Cannot be CONFIRMED | Apply timeout/recovery contract. |

**Fail-fast does not automatically cancel already-dispatched work.** Other recipients may keep running, writing logs, and causing side effects; late results must be recognized and ignored or recorded per policy. If checks trigger external actions that cannot be undone, "replying early" does not exempt you from cleanup.

### 7.6. Gateway timeout vs. Aggregator timeout

Plan a **time budget** for the entire request:

~~~text
Client HTTP timeout
   └─ Gateway reply timeout
        └─ Scatter–Gather / Aggregator deadline
             ├─ Inventory downstream timeout
             └─ Fraud downstream timeout
~~~

If the Gateway times out **before** the Aggregator expires, the caller already received a timeout while the group still exists and keeps running. If the Aggregator emits a result after the caller left, you need a policy for **late replies**, cleanup, and updating status asynchronously where appropriate.

Budgets should leave headroom for error handling and response delivery, though no single timeout figure is a silver bullet. Monitor **message group store** resources and pending groups.

## 8. Partial Results, Duplicates, and Failed Branches

### 8.1. Scenarios during fan-out

~~~mermaid
flowchart TD
    S[Recipient List / Scatter] --> A[Recipient A]
    S --> B[Recipient B]
    A --> AR{Result A}
    B --> BR{Result B}
    AR -->|Success| G[Gatherer]
    AR -->|Failure/timeout| E[Error/recovery policy]
    BR -->|Success| G
    BR -->|Failure/timeout| E
    E --> G
    G --> D{Release policy}
    D -->|Complete| O[Combined outcome]
    D -->|Missing past deadline| T[Timeout / partial / recovery]
~~~

Not every error causes a recipient to return a `CheckResult`. An outbound gateway can throw an exception, a broker consumer can redeliver, or a thread can terminate. **If the Aggregator only counts successful results**, a failed branch can stall the group until timeout. Choose explicitly:

- **Turn errors into structured results**, such as `CheckResult(recipient=fraud, status=TIMEOUT)`, when the contract fits.
- **Await bounded retries**, then transition to `FAILED`/recovery if still incomplete.
- **Expire the group** with a clear policy for missing results so groups never linger forever.
- **Cancel** remaining recipients if cancellation is truly supported without corrupting side effects.

### 8.2. Duplicates distort counting

One recipient can emit multiple times due to retries or broker redelivery:

~~~text
request=REQ-7 inventory -> PASS (attempt 1)
request=REQ-7 inventory -> PASS (attempt 2, duplicate)
request=REQ-7 fraud     -> not received yet
~~~

If the release strategy uses "2 messages received," the group releases prematurely. Check **unique recipient ID**, **request ID**, event/result ID, and replacement policy when the same recipient replies again. Never assume every repeated message is an error: it could be an updated version, so the contract must specify whether updates are permitted.

### 8.3. Partial success and no shared transaction

Suppose audit saved successfully while notification failed. Recipient List does not perform a **distributed transaction** to roll back audit. Even when branches run synchronously, one handler throwing an exception does not guarantee another handler's side effects are undone.

For multi-service integration, prefer appropriate patterns: **idempotency**, bounded retries, outbox, explicit business state, or **compensation/Saga** when distributed effects must be reconciled. Never place `@Transactional` on one application service and assume email, Kafka, and downstream HTTP calls participate in one ACID transaction.

### 8.4. Should a failed branch be awaited?

If the goal is independent audit or telemetry, you may allow notification to fail while still confirming the order was saved, **provided you record the failure state and retry mechanism**. If the goal is an approval decision, a failed mandatory branch normally cannot be treated as "qualified."

| Task | Wait for success? | On failure |
|---|---|---|
| Save order | Yes, if API returns "saved." | Return error or uncertain status per transaction contract. |
| Emit event to outbox | Must align with downstream processing commitments. | Retry/recover; do not claim emitted without proof. |
| Welcome email | Usually do not wait. | Retry/DLQ, report error separately; do not roll back order over email. |
| Mandatory fraud check | Yes before "confirmed." | Fail/timeout/review per policy. |
| Mandatory inventory check | Yes before "confirmed." | Out of stock/timeout/recovery. |
| Analytics | Usually no. | Monitor lag and data loss against corresponding SLOs. |

## 9. Gateway, Error Channel, and Reply: Three Distinct Paths

### 9.1. Recipient List does not automatically produce one valid reply

When a request–reply Gateway sends a message into a Router fanning out to multiple targets, if each handler sends a reply back to the same `replyChannel` without an appropriate Gatherer, you can hit **competing replies**, undefined responses, or timeouts depending on flow/transport. Never grab the first reply and treat it as the result of all branches.

To use a Gateway synchronously with multiple reply-producing recipients:

1. Define a **Scatter–Gather** model and expected recipient set.
2. Propagate appropriate correlation/reply metadata.
3. Define **one** final combined result or business error.
4. Configure timeouts, missing-result handling, and late-reply handling.

If you only want one-way event broadcast, avoid forcing a synchronous Gateway to wait on recipients that have no reply contract.

### 9.2. Synchronous exceptions differ from asynchronous errors

With a Recipient List dispatching over `DirectChannel`, handler exceptions can propagate along the sender's call stack and affect forwarding to remaining targets. **Never assume** the entire list was called, nor assume side effects prior to the exception rolled back.

When dispatching to executors, pollers, or brokers, consumer errors can happen **after the sender returned**, and may surface as `ErrorMessage`/`errorChannel` in configured contexts. Failed sends due to full queues also differ from a handler receiving a message and failing.

Whether one recipient failing stops remaining recipients or is skipped depends on **the router/channel type and send-failure policy** in use. Always inspect and test your configuration rather than guessing from the Recipient List name that it always continues or always halts.

### 9.3. Retries must be scoped

A failure in notification does not require **resending the entire Recipient List**. Retrying the whole fan-out can re-run audit and analytics, creating duplicates. It is usually better to place retries/recovery on the **failed branch** with per-recipient idempotency keys:

~~~text
deliveryKey = eventId + ":" + recipientId

EVT-1001:audit        -> completed
EVT-1001:notification -> retrying
EVT-1001:analytics    -> completed
~~~

This is an **application convention**, not an automatically generated header. It distinguishes the three branches spawned from the same event during retries/redeliveries. When intentional re-emissions of the same event occur, include a version/operation ID per contract.

## 10. Observing Timing and Per-Recipient Status

### 10.1. Tracking dispatch decisions and outcomes

A structured log set might include:

~~~text
event=RECIPIENTS_SELECTED requestId=REQ-8
  expected={inventory,fraud}

event=RECIPIENT_ACCEPTED requestId=REQ-8 recipient=inventory

event=RECIPIENT_COMPLETED requestId=REQ-8
  recipient=inventory outcome=PASS durationMs=42

event=RECIPIENT_FAILED requestId=REQ-8
  recipient=fraud outcome=TIMEOUT attempt=2

event=GROUP_EXPIRED requestId=REQ-8
  expected=2 receivedUnique=1 missing={fraud}
~~~

This is an **application-proposed schema**, not Spring Integration's default output. Specifically, `RECIPIENT_ACCEPTED` **must never be labeled `RECIPIENT_COMPLETED`** when only enqueuing a task.

Keep four identifiers distinct:

- `businessId` such as `orderId` to look up business entities.
- `eventId` / `messageId` to identify business events and technical messages.
- `correlationId` / `validationRequestId` to group related results accurately.
- `traceId` to follow execution across threads, processes, and services.

### 10.2. Appropriate Metrics

| Metric | Question Answered |
|---|---|
| Selected recipients by type | What is the average fan-out branch count? |
| Accepted/rejected send count | Which branch is refusing messages? |
| Processed/failed count by recipient | Which branch is succeeding or failing? |
| Processing latency by recipient | Which target is the bottleneck when waiting for all? |
| Queue depth / oldest-message age | Is an async branch building up backlog? |
| Pending group count | How many groups is the Aggregator waiting on? |
| Group completion / expiry rate | What is the completion vs. timeout ratio? |
| Retry/duplicate/late-reply count | Are delivery and recovery stable? |

Do not use high-cardinality IDs like `orderId` or `traceId` as metric labels. Access-controlled logs and distributed tracing handle specific IDs much better.

### 10.3. Message History does not replace business outcomes

`Message History` shows which Spring Integration components were traversed, yet it does not automatically record **which recipient committed a transaction**, aggregate distributed traces, or confirm all replies. In flows with `ExecutorChannel`, sender-thread ThreadLocal/MDC values do not propagate automatically; trace context needs explicit propagation.

In a fan-out/gather model, record telemetry at all three points:

1. **Before scatter:** expected recipient set, correlation key, deadline.
2. **At each recipient:** started, accepted/processed/failed, attempt, latency.
3. **At gatherer:** unique result count, release reason, outcome, late replies, expiry.

That way, a timed-out request can be diagnosed cleanly: wrong recipients selected, sent to a full queue, handler failed to run, or aggregator waited on the wrong group.

## 11. Testing: Verifying Exactly What You Are Waiting For

### 11.1. Integration test for synchronous Recipient List

With `RecipientListConfiguration` from Section 5, a JUnit 5 + Spring Test can verify both recipients are invoked:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(RecipientListConfiguration.class)
class RecipientListFlowTest {

    @Autowired
    @Qualifier("orders.received")
    private MessageChannel input;

    @Autowired
    private RecipientProbe probe;

    @Test
    void twoDirectRecipientsAreHandledWhenSendReturns() {
        int beforeAudit = probe.audits.get();
        int beforeNotify = probe.notifications.get();

        boolean sent = input.send(
                MessageBuilder.withPayload(
                        new OrderCreated("EVT-1", "ORD-1"))
                        .build(), 1_000);

        assertTrue(sent);
        assertEquals(beforeAudit + 1, probe.audits.get());
        assertEquals(beforeNotify + 1, probe.notifications.get());
    }
}
~~~

**What does this test prove?** In **the example's synchronous `DirectChannel` configuration** with no errors, each handler incremented its counter before the send call returned. It does not prove a real notification reached a user, audit persisted to a durable database, or an executor/broker branch finished before `send` returned.

To verify **the exact channels received messages**, use interceptors or test-only handlers in test configuration. Never use log line counts as sole proof, especially with executors and parallel processing.

### 11.2. Unit test for the wait-for-all policy

Using `DecisionPolicy` from Section 7 to distinguish "enough messages" from "enough recipients":

~~~java
import java.util.Map;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DecisionPolicyTest {
    private final DecisionPolicy policy = new DecisionPolicy();

    @Test
    void confirmsOnlyWhenBothRecipientsPassed() {
        CombinedDecision result = policy.combine(
                "REQ-1",
                Map.of(
                        "inventory",
                        new CheckResult("REQ-1", "inventory",
                                CheckStatus.PASS),
                        "fraud",
                        new CheckResult("REQ-1", "fraud",
                                CheckStatus.PASS)));

        assertTrue(result.confirmed());
    }

    @Test
    void doesNotConfirmIfFraudRejected() {
        CombinedDecision result = policy.combine(
                "REQ-2",
                Map.of(
                        "inventory",
                        new CheckResult("REQ-2", "inventory",
                                CheckStatus.PASS),
                        "fraud",
                        new CheckResult("REQ-2", "fraud",
                                CheckStatus.FAIL)));

        assertFalse(result.confirmed());
    }

    @Test
    void missingFraudResultCannotBeTreatedAsComplete() {
        assertThrows(IllegalStateException.class, () ->
                policy.combine(
                        "REQ-3",
                        Map.of("inventory",
                                new CheckResult("REQ-3", "inventory",
                                        CheckStatus.PASS))));
    }
}
~~~

These tests **do not yet test Aggregator infrastructure**. They only verify application decision logic **once a set of results has arrived**. To test Scatter–Gather end-to-end, add reply-handling flows, group store, timeouts, release strategy, and tests for missing, duplicate, and late replies.

### 11.3. Asynchronous tests must not rely on fixed sleeps

When replacing a recipient with `ExecutorChannel`, do **not** assert `notificationCount == 1` immediately after `send` as a general rule. Use a `CountDownLatch` or bounded await utility to confirm the handler actually completed.

Example test plan:

1. Send a message with an explicit `eventId`.
2. Use a test handler recording `received` and `completed` events, gated by a latch.
3. Hold the handler before completion; verify the sender receives **task accepted** per contract without confusing it with business completion.
4. Release the latch; await `completed` with a finite timeout.
5. Saturate the executor and verify the rejection policy/exception or backpressure is reported properly.
6. Ensure the executor shuts down in `finally` or via the Spring context lifecycle.

Do not expect an already-committed external action to "disappear" when a test cancels a `Future`; Java cancellation does not guarantee rolling back side effects.

### 11.4. Test Matrix for Wait-for-All

| Scenario | What to Verify |
|---|---|
| Both recipients reply PASS | Aggregator releases one successful combined result. |
| One PASS, one FAIL | Rejection or fail-fast per policy, never CONFIRMED. |
| One PASS, one silent | Deadline expires and returns clear timeout/partial/recovery outcome. |
| One recipient sends two duplicate replies | Not counted as two completed recipients. |
| Reply arrives after group expiry | Late reply is ignored or handled per policy without falsely re-confirming. |
| Concurrent requests with same `orderId` | Distinct correlation IDs prevent mixing groups. |
| Recipient List picks a subset | Expected count/set matches the subset **actually selected**. |
| One sync handler throws an exception | Do not assume remaining recipients ran; inspect partial side effects. |
| Executor/broker accepts, then consumer fails | Do not treat accepted send as business success. |
| Gateway reply times out before group expiry | Group and late replies remain controlled after caller times out. |
| Message loses correlation header across adapter | Groups do not merge incorrectly; clear error/recovery path triggers. |
| Retrying entire fan-out | Verify whether already-succeeded recipients suffer duplicates. |

## 12. Common Design Mistakes

| Misconception | Consequence | Right Approach |
|---|---|---|
| "Recipient List automatically waits for all replies." | Gateway misses replies or returns undefined results. | Use Scatter–Gather/Aggregator with correlation, release, and timeout. |
| "Fire-and-forget means `send` always returns immediately." | `DirectChannel` can still block due to synchronous handlers. | Inspect channel and execution model; pick async if truly needed. |
| "Async means durable." | Tasks in executors/queues are lost on restart. | Pick a broker/outbox/store matching delivery guarantees. |
| "Routed to three targets means three branches succeeded." | Misses full queues, dispatch failures, and processing errors. | Track accepted/started/completed/failed per recipient. |
| "Three messages received means three recipients replied." | Duplicates from one recipient trigger premature release. | Track unique recipient IDs and deduplicate. |
| "Every request always has the same recipient count." | Conditional lists cause the Aggregator to wait for the wrong count. | Lock in the expected recipient set per request. |
| "If one branch fails, prior branches rolled back." | Partial side effects, duplicates on retry. | Per-branch idempotency, compensation, and recovery. |
| "Gateway timeout means the group was deleted." | Stale message groups linger, late replies go unhandled. | Design independent group expiration/cleanup. |
| "Retry the whole Recipient List when email fails." | Audit and analytics re-run despite already succeeding. | Retry at the failed recipient with a delivery/idempotency key. |
| "`traceId` can serve as correlation key." | Multiple groups sharing one trace get merged wrongly. | Use a dedicated request/group ID for the Aggregator. |
| "No reply proves the recipient never received it." | Consumer may still be running or the reply was lost. | Observe dispatch, processing, timeouts, and transport. |
| "Must wait for all telemetry before returning API response." | Latency rises, turning secondary branches into hard dependencies. | Define true critical paths and SLOs. |

## 13. Practice Exercises

1. **Basic fan-out:** use `routeToRecipients` to send `OrderCreated` to audit and notification. Write a test verifying both synchronous handlers receive the message.
2. **Async one branch:** replace `orders.notify` with `ExecutorChannel` and measure the gap between when `send` returns and when notification finishes. Add an executor saturation test.
3. **Conditional Recipient List:** for international orders, add `compliance`; domestic orders go only to audit/notification. Record `expectedRecipients` to see why you cannot hardcode recipient count.
4. **Scatter–Gather:** create two recipients `inventory` and `fraud`, using a request ID to gather replies. Return `CONFIRMED` only when both PASS.
5. **Duplicates:** have inventory send two success messages while fraud sends none. Prove the Aggregator must not release without fraud's result.
6. **Timeouts:** simulate fraud not responding; design deadline, group expiry, Gateway response, and late-reply handling.
7. **Fail-fast:** have inventory FAIL before fraud finishes. Compare waiting for all vs. early rejection; explain how the still-running fraud task must be handled.
8. **Retry and idempotency:** make notification fail after audit succeeded. Compare retrying the whole fan-out vs. retrying only notification; use `eventId:recipientId` as the deduplication key.
9. **Preserving correlation:** send results through an adapter that rebuilds messages; verify correlation/request IDs are restored by mappers instead of relying on an in-JVM `replyChannel` object.
10. **Observability:** add `RECIPIENT_ACCEPTED`, `RECIPIENT_COMPLETED`, and `GROUP_EXPIRED` logs; inject random failures into one branch and identify which milestone the system actually reached.

### Self-Check Questions

**Question 1:** A Recipient List Router sends a message to three synchronous `DirectChannel`s. Once `send` finishes, is that enough to prove all three external side effects committed? **No.** You can only reason about synchronous dispatch/handlers per configuration; commit/durability requires separate evidence.

**Question 2:** If a recipient uses `ExecutorChannel`, must the sender wait for the handler to finish? **Not by default.** It may only wait for the executor to accept the task, subject to rejection/backpressure configuration.

**Question 3:** When inventory returns PASS and fraud does not respond, can you return `CONFIRMED`? **No**, if the contract requires both; you need timeout/recovery or an undecided state.

**Question 4:** One branch sends two duplicate replies while the other branch has not replied yet. The Aggregator sees two messages—is that enough to release? **No.** You must check unique recipients and correlation.

**Question 5:** If notification fails after the order committed, must the order be rolled back? **No**, unless business rules and transactions are designed that way. Usually you recover notification independently.

**Question 6:** Does Scatter–Gather automatically guarantee exactly-once processing across a broker? **No.** Delivery, deduplication, idempotency, retries, and transactions are independent responsibilities that must be designed explicitly.

**Conclusion:** There is no blanket rule that "Recipient List must always wait for all" or "should always fire-and-forget." The decision comes from the **business contract**: which outcomes are mandatory to declare success, which completion milestone is acceptable, and what happens if a recipient is slow or fails. In Spring Integration, Recipient List handles **selecting and dispatching to multiple destinations**; channel types determine **synchronous vs. asynchronous execution**; Scatter–Gather/Aggregator handles **waiting and combining results**. Designing correlation, expected recipient sets, timeouts, partial failures, retries, error channels, idempotency, and observability properly keeps flows loosely coupled yet deterministic, testable, and recoverable.
