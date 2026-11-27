# RequestHandlerRetryAdvice in Spring Integration Adapters

> **Chapter:** Reliability  
> **Topic:** RequestHandlerRetryAdvice  
> **Module scope:** Connecting external systems with **Spring Integration** via inbound/outbound adapters, gateways, pollers, and MessageChannels; practicing File, SFTP, HTTP, JMS, AMQP, Kafka, and databases. This lesson focuses on retrying at the right handler boundary, message contracts, error handling, consistency, and connection lifecycles.

## 1. Learning objectives

After this lesson, learners can:

1. Explain **`RequestHandlerRetryAdvice`** as the mechanism that wraps a Spring Integration message handler invocation with Spring Retry.
2. Distinguish **`RetryTemplate`, `RetryPolicy`, `BackOffPolicy`, `RetryContext`, `RetryCallback`, and `RecoveryCallback`** by their exact responsibilities.
3. Attach advice to a **message-handling endpoint** using Java DSL, understanding what gets re-executed and what does not.
4. Choose attempt counts, retryable exceptions, wait intervals, timeouts, and deadlines; avoid infinite retries or multiplying load on external systems.
5. Design **recovery** without losing messages or silently acking/committing unpersisted messages.
6. Distinguish handler retry, **broker redelivery**, **Kafka offset/seek**, poller schedules, and replay from a durable queue.
7. Apply these concepts to File/SFTP, HTTP, JMS, AMQP, Kafka, and JDBC, paired with **idempotency, transactions, and acknowledgement**.
8. Write tests verifying invocation counts, exception classification, recovery, negative cases, side effects, crash/restart, and observability.

## 2. The problem: a handler calling a temporarily failing partner

Consider a flow that receives SFTP files, transforms them into messages, and syncs orders to an ERP system:

~~~text
SFTP inbound adapter + poller
    -> rawFileChannel
    -> parse / validate records
    -> orderChannel
    -> HTTP outbound gateway (ERP)
    -> database status update
    -> AMQP outbound adapter
~~~

The HTTP outbound gateway may encounter:

- **Connection reset:** temporary connection drop.
- **HTTP 503:** partner under maintenance or overloaded.
- **HTTP 429:** partner rate-limiting requests.
- **Read timeout after POST:** target may have created the order, but the response was lost.
- **HTTP 400/403:** invalid payload or permissions—usually not fixed by retrying.
- **Failures after ERP succeeds:** database or broker may fail, though the ERP order should not be resent.

A poor design wraps retry around the entire flow: if the last step fails, the file is re-read and HTTP POST is sent again. A sound design specifies **which operation is retried**, what results are already committed, and how duplicate side effects are prevented.

**`RequestHandlerRetryAdvice`** fits when the unit to retry is **the invocation of a single message handler**. It does not automatically recover an entire transaction spanning multiple systems.

## 3. What is RequestHandlerRetryAdvice?

In Spring Integration, a **message-handling endpoint** connects a message channel to handler logic: a transformer, service activator, router, outbound adapter/gateway, or specialized component handler.

**`RequestHandlerRetryAdvice`** is a message handler advice that applies Spring Retry to an eligible endpoint. Whenever the handler throws an exception, **`RetryTemplate`** coordinates `RetryPolicy` and `BackOffPolicy` to decide whether to invoke the handler again.

| Component | Duty | Does not automatically guarantee |
|---|---|---|
| Inbound adapter / `MessageSource` | Receives or creates messages from a source system | That messages are always re-received after any error |
| `MessageChannel` | Delivers messages to subscribers/handlers | Durable delivery across all channel types |
| `MessageHandler` | Processes messages or performs external I/O | That repeating the operation is safe |
| **`RequestHandlerRetryAdvice`** | Wraps invocations of the advised handler | Retrying the whole `IntegrationFlow` or managing broker offsets |
| `RetryTemplate` | Coordinates attempts, callbacks, and recovery | Idempotency, distributed transactions |
| `RetryPolicy` | Decides which exceptions and how many attempts can retry | Wait intervals, business recovery |
| `BackOffPolicy` | Waits between attempts | Network timeouts or retryability |
| `RetryContext` | State of the current retry sequence | Durability across app restarts |
| `RecoveryCallback` | Handles exhaustion when retries run out | Automatic durable DLQ and proper acks |
| Error channel/container | Error-handling route or redelivery source | That every error can be safely replayed |

Distinguish this advice from **`@Retryable`** on methods/services, HTTP client retries, Kafka listener error handlers, JMS/AMQP broker redelivery, and subsequent poll cycles. Several can coexist, each with its **own scope and counter**.

### Questions before attaching advice

- Does the handler have **one** clearly identifiable side effect?
- If the call times out, can we tell what the remote already did?
- Does the message carry a **stable business ID** for deduplication?
- Does any layer below the handler already retry on its own?
- Should final failures be rethrown, sent to a DLQ, or placed in delayed retry?
- When will the caller/container ack/commit?
- If the app restarts mid-retry, can the source safely redeliver?

## 4. Retry scope: the handler, not the entire flow

~~~mermaid
flowchart LR
    S["SFTP inbound"] --> C["MessageChannel"]
    C --> P["Parse + validate"]
    P --> H["HTTP outbound handler"]
    H --> R["RequestHandlerRetryAdvice"]
    R --> E["ERP API"]
    H --> D["Database update"]
    D --> A["AMQP send"]
    X["Poller / SFTP state"] -.->|"Outside advice scope"| S
    R -.->|"Only re-executes wrapped handler"| H
~~~

When advice is attached to the **HTTP outbound handler**:

- Upstream transformers do not automatically re-run due to handler retry.
- The HTTP handler may be called multiple times.
- When HTTP finally succeeds, the flow continues.
- If the downstream database or AMQP step fails, advice on the HTTP handler **does not** resolve that error.
- The next SFTP poll does not automatically ensure the file is downloaded again.
- If retries are exhausted and the exception propagates, the caller or consumer/container applies its configured error handling.

### Why not wrap the entire orchestration?

Suppose a composite handler performs:

~~~text
handler.process():
    createOrderAtERP()
    updateLocalDatabase()
    publishNotification()
~~~

If ERP succeeds and DB succeeds, but `publishNotification()` fails, re-running **the whole handler** can create another order and another DB update. Only wrap an entire block in retry when every step is idempotent and outcome states are tightly tracked.

Usually the better solution is: **state machine + per-step retries + outbox/inbox + reconciliation**.

## 5. Lifecycle of an invocation with RequestHandlerRetryAdvice

~~~mermaid
flowchart TD
    A["Message arrives at endpoint"] --> B["Open RetryContext"]
    B --> C{"RetryPolicy still allows?"}
    C -->|"Yes"| D["Execute handler invocation"]
    D -->|"Success"| S["Finish and return result"]
    D -->|"Throws error"| E["Classify exception and update context"]
    E --> F{"Retryable and attempts remaining?"}
    F -->|"Yes"| W["BackOffPolicy waits with bounds"]
    W --> C
    F -->|"No"| R{"RecoveryCallback present?"}
    R -->|"Yes"| G["Recovery per contract"]
    R -->|"No"| X["Exception surfaces to caller/container"]
    G --> Z["End"]
    X --> Z
~~~

This diagram shows the logical flow. Backoff only controls **when to try next**; it does not guarantee that the error can recover or that repeating the operation is safe.

### Attempts vs. retries

With `maxAttempts = 4`:

| Execution | Name | Backoff beforehand? |
|---|---|---|
| 1 | Initial attempt | No |
| 2 | First retry | Yes if attempt 1 failed and is retryable |
| 3 | Second retry | Yes if attempt 2 failed and is retryable |
| 4 | Third retry | Yes if attempt 3 failed and is retryable |
| Failed after #4 | Exhausted/recovery | No fifth attempt |

**4 attempts total = 1 initial call + at most 3 retries**, not 4 additional retries.

## 6. RetryPolicy: only valid errors get retried

Do not retry every exception, because many errors never change no matter how long you wait.

| Error or symptom | Retry? | Conditions |
|---|---|---|
| Connection reset / temporary unreachable | Possibly | With timeouts and backoff |
| HTTP 503 / 429 | Possibly | Deadline, jitter, rate limit, and `Retry-After` if present |
| HTTP 502 / 504 | Depends on operation | Response may be lost after remote committed |
| Connect timeout | Possibly | Check whether the operation could have reached target |
| Read timeout after POST | Do not retry blindly | Idempotency key or status lookup |
| HTTP 400 / validation | Usually no | Fix schema/payload |
| HTTP 401 / 403 | Usually do not retry with same credentials | Refresh token/permissions in a dedicated flow |
| HTTP 404 / 409 | Depends on business logic | Possible eventual consistency or already processed |
| JDBC deadlock / serialization conflict | Possibly | Retry appropriate fresh transaction |
| SFTP auth / host key error | Do not retry blindly | Fix trust/credentials |
| File permission denied | Usually no | Fix ACLs or system permissions |
| Poison message | Not with unchanged payload | Quarantine/manual review |

**Retryability is a property of both the error type and the operation.** An `IOException` may be transient, yet if an HTTP POST is non-idempotent, retrying remains dangerous.

### Exception wrappers

Spring Integration may throw **`MessagingException`/`MessageHandlingException`**, wrapping client errors such as `ResourceAccessException` or `SocketTimeoutException`. Inspect the **cause chain** per `RetryPolicy` semantics.

~~~text
MessageHandlingException
  caused by ResourceAccessException
    caused by SocketTimeoutException
~~~

Do not retry every `MessagingException`, as it can wrap validation or permission errors as well. Tests must verify the **actual exception types raised by your adapter/version**.

## 7. BackOffPolicy: choosing wait intervals

Backoff prevents firing continuous requests at an unhealthy system.

| Policy | Idea | Notes |
|---|---|---|
| `NoBackOffPolicy` | Retries almost immediately | Easily causes retry storms over networks |
| `FixedBackOffPolicy` | Waits a fixed interval | Clients tend to wake up in lockstep |
| `ExponentialBackOffPolicy` | Wait grows by multiplier up to `maxInterval` | Usually does not add jitter automatically |
| `ExponentialRandomBackOffPolicy` | Exponential with randomization per implementation | Suits spreading load across instances |
| `UniformRandomBackOffPolicy` | Picks random wait within configured bounds | Needs sensible min/max and deadline |

Suppose `initialInterval=250 ms`, `multiplier=2`, `maxAttempts=4`, and no jitter:

~~~text
Attempt 1 --fail--> 250 ms
Attempt 2 --fail--> 500 ms
Attempt 3 --fail--> 1000 ms
Attempt 4 --fail--> exhausted
~~~

Total sleep = **1,750 ms**. If each HTTP attempt has a 2-second max timeout, worst-case latency is roughly **4 × 2,000 + 1,750 = 9,750 ms**, excluding overhead.

**`BackOffPolicy` does not set HTTP connect/read timeouts**, does not replace a total deadline, and its state does not persist across restarts.

### Jitter and retry storms

If 500 workers all hit HTTP 503 at 10:00, a 1-second fixed backoff can make all 500 retry almost simultaneously at 10:00:01. Exponential backoff with jitter, combined with **rate limits** and **concurrency caps**, spreads the load.

No jitter replaces **idempotency, `maxAttempts`, deadlines, circuit breakers, or durable recovery** during prolonged external outages.

## 8. Java pattern: RetryTemplate with classified errors

The following sample uses Spring Retry and example Spring Web exceptions. It is a reference config; verify against your dependency versions and your HTTP adapter's actual exceptions.

~~~java
import java.util.HashMap;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;

@Configuration
public class PartnerRetryConfig {

    @Bean
    public RetryTemplate partnerRetryTemplate() {
        Map<Class<? extends Throwable>, Boolean> retryable =
                new HashMap<>();

        // Example list; do not blindly apply to every HTTP operation.
        retryable.put(ResourceAccessException.class, true);
        retryable.put(
                HttpClientErrorException.TooManyRequests.class, true);
        retryable.put(
                HttpServerErrorException.ServiceUnavailable.class, true);

        // 4 attempts total; traverse cause chain; other errors default to false.
        SimpleRetryPolicy retryPolicy =
                new SimpleRetryPolicy(4, retryable, true, false);

        ExponentialBackOffPolicy backoff =
                new ExponentialBackOffPolicy();
        backoff.setInitialInterval(250L);
        backoff.setMultiplier(2.0);
        backoff.setMaxInterval(2_000L);

        RetryTemplate template = new RetryTemplate();
        template.setRetryPolicy(retryPolicy);
        template.setBackOffPolicy(backoff);
        return template;
    }
}
~~~

### Limitations of the example

- `ResourceAccessException` can cover many I/O errors. Being technically retryable **does not prove** an order-creating POST is safe to resend.
- The HTTP client may use different exceptions; inspect wrappers and the cause chain.
- The snippet omits jitter, total retry budgets, connect/read timeouts, `Retry-After` parsing, circuit breakers, and idempotency keys.
- Never assume the retryable status list above is standard for every partner.
- One misclassified exception can turn a permanent error into repeated wasted calls; test each status and operation.

### When randomization is needed

Replace `ExponentialBackOffPolicy` with **`ExponentialRandomBackOffPolicy`** per your library version, keeping appropriate `initialInterval`, `multiplier`, and `maxInterval`. Measure actual backoff, since delays will not follow exact deterministic values like non-jittered examples.

## 9. Creating a RequestHandlerRetryAdvice bean

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.support.RetryTemplate;

@Configuration
public class IntegrationRetryAdviceConfig {

    @Bean
    public RequestHandlerRetryAdvice partnerRetryAdvice(
            RetryTemplate partnerRetryTemplate) {
        RequestHandlerRetryAdvice advice =
                new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(partnerRetryTemplate);

        // No RecoveryCallback specified in the basic example;
        // once retries are exhausted, the error propagates per endpoint/caller rules.
        return advice;
    }
}
~~~

For retry advice to take effect, it must be **attached to an endpoint**. Creating the bean without wiring it into an endpoint does not make the flow retry.

### Choosing a RecoveryCallback

By default, errors propagate per endpoint handling; to customize post-exhaustion recovery, configure a `RecoveryCallback`. However, understand **how upper layers interpret the callback's return**. If the callback returns normally, the source/container may mark the message as processed. Never use recovery just to log and swallow errors without durable storage.

## 10. Attaching advice in IntegrationFlow Java DSL

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.integration.http.dsl.Http;

@Configuration
public class PartnerStatusFlow {

    @Bean
    IntegrationFlow partnerStatusFlow(
            RequestHandlerRetryAdvice partnerRetryAdvice) {
        return IntegrationFlow.from("partnerStatusRequests")
            .handle(
                Http.outboundGateway(
                        "https://partner.example.invalid/api/status")
                    .httpMethod(HttpMethod.GET)
                    .expectedResponseType(String.class),
                endpoint -> endpoint.advice(partnerRetryAdvice)
            )
            .channel("partnerStatusResponses")
            .get();
    }
}
~~~

In this flow:

1. The input channel receives a message.
2. The HTTP outbound gateway calls the partner.
3. The advice wraps this endpoint's **HTTP message handler**.
4. On retryable handler failures, `RetryTemplate` waits/backs off and re-invokes the handler.
5. On success, the response flows to the next channel.
6. If exhausted and the exception propagates, the caller or error handling responds per configuration.

The **`example.invalid`** domain is a placeholder. The sample uses GET to focus on wiring; for side-effecting POSTs, add idempotency, outcome reconciliation, deadlines, and authentication.

### Why not attach one shared advice to the whole flow?

Because a downstream handler failing after an upstream step succeeded does not justify blindly repeating the upstream step. Each external touchpoint usually needs its **own retry policy and recovery strategy**.

## 11. Which handlers should get retry advice?

| Handler | Retryable? | Conditions |
|---|---|---|
| HTTP outbound GET | Usually fits transient network errors | Timeouts, `maxAttempts`, and rate limits |
| HTTP outbound POST | Only if replay-safe | Idempotency key or query/reconcile |
| SFTP outbound upload | Possible for transient errors | Temp files, checksums, and remote state |
| File outbound write | Possible on temporary I/O errors | Stable names and atomic publish when supported |
| JDBC outbound update | Depends on transaction | Properly scoped rollback, unique constraints |
| Service activator calling remote | Possible | Small handler, one clear operation |
| JMS/AMQP outbound send | Must understand publish outcomes | Confirms, deduplication, and broker retry |
| Kafka outbound send | Must understand producer semantics | Broker acks, client retries, and idempotency |
| Pure data validator | Do not retry invalid inputs | Quarantine |
| Email/webhook sender | Use extreme caution | May already have sent before timing out |
| Handler coordinating multiple side effects | Do not wrap blindly | State machine and per-step retries |

**One identical policy for every handler is an anti-pattern**: invalid parser data and HTTP 503 should not be handled alike.

## 12. Advice chains and transaction boundaries

An endpoint can carry multiple advice items, such as retry, transactions, and metrics/tracing. Wrapping order around the handler changes how many transactions open.

~~~text
A. Retry on the outside:
   attempt 1 -> BEGIN tx1 -> handler -> ROLLBACK
   backoff
   attempt 2 -> BEGIN tx2 -> handler -> COMMIT

B. Transaction on the outside:
   BEGIN tx1
     attempt 1 -> handler -> exception, may mark rollback-only
     attempt 2 -> handler -> still inside tx1
   COMMIT may fail
~~~

For many deadlocks, you want to retry in a **fresh transaction**, not repeat SQL inside a `rollback-only` transaction. Yet a new transaction does not roll back an earlier HTTP POST: cross-system side effects require their own mechanisms.

### Questions you must answer

1. Does retry wrap outside or inside the transaction?
2. When an attempt fails, is the transaction marked `rollback-only`?
3. Did an external non-DB call already succeed before the error?
4. Does the handler send AMQP/Kafka before the DB commits?
5. Does source ack/commit depend on exception propagation?
6. Is there an outbox/inbox to prevent loss/duplication on crashes?
7. Are there integration tests with real deadlocks/rollbacks and the real advice chain?

**There is no universal advice order.** Changing order without testing can silently change transaction semantics and send counts.

## 13. Comparing RequestHandlerRetryAdvice and @Retryable

Both use Spring Retry ideas, but their boundaries differ.

| Criterion | `RequestHandlerRetryAdvice` | `@Retryable` on methods |
|---|---|---|
| Unit | Invocation of a message-handling endpoint | Invocation of a method via proxy |
| Where attached | Endpoint advice chain / Integration DSL | Service method / AOP configuration |
| Goal | Govern a handler inside a message flow | Retry a service method across contexts |
| Pitfalls to watch | Channel/source acks, retrying entire handler | Proxy/self-invocation and method scope |
| Combining both | Possible, easily multiplies attempts | Possible, needs a combined budget |
| Recovery | Configured callback/error flow | Method-level retry recovery |

If the endpoint retries up to 4 attempts and an inner method also retries 3 attempts, **12 method invocations** can happen per message—excluding HTTP client/broker redeliveries.

Only combine both layers with a **clear reason, overall deadline, idempotency, and per-layer metrics**.

## 14. MessageChannel and how exceptions travel

### DirectChannel

**`DirectChannel`** typically dispatches synchronously on the sender's thread. If the handler fails and exceptions propagate, the caller sees the failure on the same call stack. `RetryAdvice` holds that thread across attempts and backoffs.

~~~text
HTTP inbound gateway
  -> DirectChannel
  -> HTTP outbound handler + RetryAdvice (multiple attempts)
  -> response / error
~~~

If total retry time exceeds the HTTP caller's timeout, the caller may resend the request. Hence an end-to-end budget is required.

### ExecutorChannel

**`ExecutorChannel`** hands off work to an executor, creating an asynchronous boundary. Exceptions do not necessarily return to the sender's thread like `DirectChannel`; error channels and task/rejection handling must be designed.

`ExecutorChannel` **is not a durable queue by itself**. Process restarts can lose queued in-memory messages unless backed by source redelivery or durable persistence.

### QueueChannel

`QueueChannel` buffers messages as configured; durability depends on the `MessageStore`/transactions and how pollers fetch/ack messages. Do not assume every `QueueChannel` guarantees at-least-once across crashes.

### Topology checklist questions

| Question | Why it matters |
|---|---|
| Which thread waits during backoff? | Measures stalls and timeouts |
| Is a caller waiting for a reply? | Deadlines and caller retries |
| When handler exhausts retries, where does the exception go? | Error channel/container |
| Has the source acked or committed yet? | Prevents silent message loss |
| Is there a message store/durable queue? | Survives restarts |
| Who preserves the business event ID? | Idempotent redelivery |

## 15. Poller schedules differ from handler retry

A poller checks a source on a trigger such as `fixedDelay`/`fixedRate`/`cron`. **`RequestHandlerRetryAdvice`** does not turn a poller into a durable retry scheduler.

~~~text
SFTP poller:
  checks remote directory every 5 seconds.

HTTP handler:
  attempt 1 -> error
  wait 250 ms
  attempt 2 -> error
  wait 500 ms
  attempt 3 -> success
~~~

These events differ in **unit of work and timing**.

- When a poller finds no messages, that is normal—not an exception to retry.
- If a file was recorded by an accept-once filter, the next poll is **not guaranteed** to re-read that file.
- Downstream handler retries do not regenerate upstream messages.
- For prolonged source outages, adjust the polling schedule/pause the adapter and route failed messages to durable retry.
- Long backoffs can tie up poller threads, cutting throughput.
- Handler retry advice differs from polling endpoint advice; inspect your actual topology.

## 16. RecoveryCallback: exhaustion must not drop messages

This is a major risk with `RequestHandlerRetryAdvice`.

### Path 1: propagate the error

With no custom recovery, or a recovery callback that rethrows, the caller/container sees the terminal exception and reacts per source contract: HTTP error, JMS rollback, AMQP nack, Kafka error handler, or error channel.

### Path 2: recovery returns normally

If the callback logs and returns `null`, upper layers may treat the handler as done, triggering ack/commit **even though the business task failed and the message was not saved**.

~~~java
// Anti-pattern: watch out for swallowing exceptions.
advice.setRecoveryCallback(context -> {
    logger.error("Partner unavailable", context.getLastThrowable());
    return null; // Container may treat the message as processed.
});
~~~

### Example propagating terminal failure

~~~java
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.support.RetryTemplate;

RequestHandlerRetryAdvice advice =
        new RequestHandlerRetryAdvice();
advice.setRetryTemplate(retryTemplate);

advice.setRecoveryCallback(context -> {
    throw new IllegalStateException(
            "Partner handler exhausted retry policy",
            context.getLastThrowable());
});
~~~

This snippet is an illustrative configuration fragment, not a complete standalone Java file. When choosing **durable parking/DLQ** instead of rethrowing, verify persistence succeeds and align source ack/commit accordingly.

### ErrorMessage and error channels

Spring Integration provides `ErrorMessage` and recovery options that route errors to an error channel—such as **`ErrorMessageSendingRecoverer`** when configured properly. Yet **an error channel is not durable storage by itself**:

- In-memory channels can lose messages on restart.
- Missing subscribers or failing error flows can break recovery guarantees.
- Payloads/headers containing secrets must be protected.
- Persist business event IDs, exception categories, attempt counts, and recovery status.
- If the recoverer returns normally, verify whether the source acks and whether the message was genuinely persisted.

## 17. Terminal recovery contract

A state table helps operate after retries are exhausted:

| State | Meaning | Required evidence |
|---|---|---|
| `SUCCESS` | Handler produced a valid outcome | Result, confirmed side effects |
| `RETRY_EXHAUSTED` | In-process budget spent | Last exception and next step |
| `PARKED` | Message saved for investigation | Durable storage, owner, retention, event ID |
| `DELAYED_RETRY` | Message awaiting scheduled retry | `nextAttemptAt`, attempt count, deadline |
| `DEAD_LETTERED` | Message moved to DLQ/DLT | Persisted confirmation and replay policy |
| `OUTCOME_UNKNOWN` | Unclear if remote committed | Query/reconciliation |
| `INVALID` | Invalid payload | Reason code, quarantine |
| `CANCELLED` | Business action expired | Reason and audit trail |

Example error schema:

~~~json
{
  "eventId": "order-312-v2",
  "correlationId": "corr-e92c",
  "flowId": "sftp-to-erp",
  "endpointId": "erpOutboundGateway",
  "operation": "order.upsert",
  "attemptsCurrentInvocation": 4,
  "errorCategory": "REMOTE_UNAVAILABLE",
  "lastErrorType": "ServiceUnavailable",
  "outcome": "PARKED",
  "payloadReference": "secure-message-store/order-312",
  "nextReviewAt": "2026-11-23T12:00:00Z"
}
~~~

This is an illustrative business schema, not a default framework format. **Do not log tokens, private keys, passwords, or full customer payloads in error logs.**

## 18. Idempotency: safe retry requires a stable business key

**Idempotent** means repeating the same operation with the same semantics creates no unintended extra business effects. This is critical for HTTP POST, database writes, file uploads, emails, or event publishing.

### Stable business event ID

Never use `MessageHeaders.ID`, which can be regenerated after transformations/redeliveries, as a business key. Use a stable ID defined by the source or business domain.

~~~text
businessEventId = partner-X:order-312:v2
operation = ERP.order.upsert

Attempt 1:
    Idempotency-Key = partner-X:order-312:v2
    ERP committed, but response was lost.

Attempt 2:
    Idempotency-Key = partner-X:order-312:v2
    ERP returns the previous result, creating no second order.
~~~

This example holds only if **ERP genuinely supports idempotency keys**, with rules for TTL, scope, and mismatched payloads under the same key. Otherwise, query status by `orderId` or move to **`OUTCOME_UNKNOWN`** for reconciliation.

### Inbox/dedupe

A table tracking processed events can enforce uniqueness via a constraint:

~~~sql
-- Illustrates a consumer-scoped business key.
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    business_event_id VARCHAR(160) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, business_event_id)
);
~~~

When marking processed and updating business data share **one DB transaction**, duplicate side effects in that DB are prevented. However, if the handler calls remote HTTP first and updates `processed_events` in the local DB afterward, crashing in between still leaves the remote potentially updated without local awareness.

### Transactional outbox

A flow updating a DB and publishing to AMQP/Kafka can:

1. Write business data;
2. Write an outbox event in the **same DB transaction**;
3. Commit;
4. Have an outbox publisher deliver to the broker, retrying on failure;
5. Have target consumers deduplicate by stable event ID.

Outbox preserves **sending intent**; it does not automatically make publishing exactly-once across every system. Consumers must still be idempotent.

### Why not retry one huge callback?

~~~text
RetryCallback:
    createERPOrder();       // already succeeded
    updateLocalDatabase();  // already succeeded
    sendNotification();     // failed

Retrying the callback:
    createERPOrder();       // may create duplicate
    updateLocalDatabase();
    sendNotification();
~~~

Break this into states—`ERP_PENDING`, `ERP_CONFIRMED`, `DB_UPDATED`, `NOTIFICATION_PENDING`, `DONE`—with `OUTCOME_UNKNOWN` and `PARKED` so each step has its own retry scope.

## 19. Transactions, acknowledgement, and redelivery

In an integration flow, distinguish:

1. **Handler attempt:** one execution of handler code;
2. **Transaction:** which updates commit/roll back together;
3. **Source acknowledgement/checkpoint:** when the source believes the message is finished.

`RetryAdvice` does not automatically align these three boundaries.

| Source | On success | On exhaustion | Questions to verify |
|---|---|---|---|
| HTTP inbound gateway | Request–reply response | Return proper error | Will the client resend? |
| File inbound | File processed/marked per flow | No default broker ack | Accept-once, metadata, archiving? |
| SFTP inbound | Download/filter per config | No automatic re-download | Are transfer/remote states durable? |
| JMS listener | Ack/commit per container | Rollback/redelivery/DLQ | Does recovery swallow exceptions? |
| AMQP listener | Ack/commit per mode | Nack/reject/requeue/DLX | Could a hot loop form? |
| Kafka | Offset/ack per container | Seek/retry topic/DLT | Partition ordering and side effects? |
| JDBC poller | Claim/update per transaction | Row needs retry/lease | Can the row be safely re-claimed? |

**Never assume every source automatically redelivers when a handler throws an exception.** Inspect exact configurations and test failures/restarts.

### DB transactions and retry

Deadlocks or serialization conflicts can mark a transaction `rollback-only`. Running more statements inside that transaction will fail to commit; you must **roll back and open a fresh transaction** at the right boundary. Because external HTTP side effects do not roll back automatically, never wrap them inside a coarse callback just to retry DB transactions.

### Source ack and durable recovery

When routing a message to parking/DLQ before letting the source ack:

1. Write a record with a stable `eventId`, payload reference, and enough metadata to redrive;
2. Confirm durable write succeeded;
3. Ack the source per contract;
4. Enforce idempotency in case of a crash between parking and source ack.

**Writing to another broker and acking the source are not atomic by default** without a matching transaction/guarantee contract.

## 20. HTTP outbound gateway: a classic use case

An HTTP gateway handles request–reply and suits message-handler advice as long as the operation is safe to retry.

| Error | Reference handling | Extra safeguards |
|---|---|---|
| 429 | Delayed retry when fitting | `Retry-After`/rate limit/deadline |
| 503 | Exponential backoff and jitter | Avoid amplifying overload |
| 502/504 | Depends on operation | Outcome may be unknown |
| Connect timeout | Retryable | Check network/client layers |
| Read timeout after POST | Do not resend blindly | Idempotency/reconciliation |
| 400 / invalid schema | Do not retry | Fix data |
| 401/403 | Do not retry with same credentials | Fix authentication/permissions |
| 404/409 | Per business contract | Do not assume transient |
| 500 | Do not retry every POST by default | Server may commit before failing |

### Retry-After and deadlines

If a partner returns 429 with `Retry-After: 30` seconds while the HTTP inbound caller only waits 4 seconds, do not hold the synchronous request for 30 more seconds. Return an error to the caller or persist the message into durable delayed retry per contract.

**`ExponentialBackOffPolicy` does not automatically read the `Retry-After` header.** Honoring server directives requires response-specific logic bounded by the total deadline.

### POST timeout after commit

~~~mermaid
sequenceDiagram
    participant C as HTTP Handler
    participant P as Partner ERP
    participant D as ERP Database
    C->>P: POST order eventId=order-312-v2
    P->>D: Commit order
    D-->>P: Success
    Note over C,P: Response lost, read timeout
    C->>C: RetryAdvice evaluates error
    C->>P: POST same idempotency key if supported
    P-->>C: Returns previous result
~~~

The diagram assumes the partner genuinely supports idempotency. Otherwise, transition the message to `OUTCOME_UNKNOWN` to query/reconcile before resending.

## 21. File inbound/outbound: handler retry is not poller retry

### Inbound File

- File may still be mid-write: use temporary names/ready markers or manifests.
- Invalid JSON/CSV: quarantine; never retry the same payload endlessly.
- If a downstream HTTP handler fails, advice on HTTP **does not make the file get re-polled**.
- An accept-once filter may have recorded the file before the downstream failure.
- In-memory metadata changes behavior across restarts; use stable business event IDs and persistence.
- Archive/delete files only upon approved processing states, never prematurely.

### Outbound File

If writing fails mid-way, retrying the same name can create partial files or overwrite data. Write to temporary output and publish via rename where the filesystem supports proper semantics. Tie filenames to event IDs for reconciliation.

**Backoff helps with transient I/O, but it does not turn file writes into atomic transactions**, nor does it fix invalid content.

## 22. SFTP: sessions, partial transfers, and remote state

Spring Integration SFTP adapters open sessions, list/download/upload, and rename/move/delete. Not all errors should be retried identically.

| Activity | Transient error | Risk |
|---|---|---|
| Open session | Connect timeout/reset | Wrong credentials and host keys are different errors |
| List remote | Server busy | Overlapping polls add load or repeat files |
| Download | Disconnect mid-transfer | Local partial file |
| Upload | Timeout near completion | Remote partial/duplicate |
| Rename | Lost response | Command may have executed |
| Delete/move | Timeout | File may already be moved/deleted |

### Recoverable upload

~~~text
eventId=invoice-882-v3
    -> temp filename derived from eventId
    -> upload
    -> verify size/hash/manifest if applicable
    -> publish to final filename
    -> mark CONFIRMED
~~~

If a response is lost at the rename step, inspect **the remote file's actual state** before retrying. Never disable SSH host-key verification to help reconnect; wrong keys/credentials require fixing trust/config.

### Advice limitations

`RequestHandlerRetryAdvice` on a downstream handler **does not wrap the entire SFTP inbound source operation**. If an error happens before the source builds a message, handle it at the **SFTP session/adapter/poller**. If the file already downloaded and a downstream handler fails, persist and replay the message separately.

## 23. JMS: in-process attempts multiplied by broker deliveries

~~~text
JMS delivery 1:
    handler attempt 1 -> timeout
    handler attempt 2 -> timeout
    handler attempt 3 -> exhausted
    exception propagates

Container:
    if configured with transaction/rollback:
        message may be redelivered

JMS delivery 2:
    handler may run 3 fresh attempts
~~~

With 3 handler attempts per delivery and 5 total broker deliveries, the handler can run **15 times**. Internal HTTP/DB calls require idempotency.

Clarify:

- Whether the session is transacted and its acknowledgement mode;
- What the container does when the handler throws an exception;
- Whether `RecoveryCallback` returns normally and causes an ack;
- How the broker caps redelivery and routes to DLQ;
- Whether poison messages block the consumer;
- How broker message IDs differ from business event IDs.

**Handler retry and JMS broker redelivery are two separate loops**; bound total processing attempts across both.

## 24. AMQP/RabbitMQ: nack/requeue and publisher confirms

### Inbound

- Short handler retry with `RequestHandlerRetryAdvice`.
- Upon exhaustion, the container decides ack/nack/reject/requeue based on configuration and exception.
- **Unbounded immediate requeue** can create a hot loop.
- TTL/DLX, delayed queues, or proper retry mechanisms space out prolonged errors.
- Prefetch/concurrency controls how many messages occupy worker slots.
- If `RecoveryCallback` returns success before durable persistence, the source may ack erroneously.

### Outbound

A publish may reach the broker while its confirm gets lost, creating an **unknown outcome**. Retrying the publish can create duplicate messages. Publisher confirms do not prove downstream consumers completed business work.

Solution: use outbox when originating from a DB transaction, stable event IDs, and consumer deduplication; handle timeouts/confirms per contract.

**Never assume writing to a DLQ on another broker and acking the source form an atomic transaction.**

## 25. Kafka: advice does not replace container error handlers

Spring Integration Kafka adapters pair with Spring for Apache Kafka. `RequestHandlerRetryAdvice` **only retries handler invocations**; it does not seek, commit offsets, or create retry topics or DLTs.

| Layer | Responsibility |
|---|---|
| Kafka consumer/client | Poll records, heartbeats, group membership, offsets |
| Listener container/error handler | Retry/seek/backoff/recovery/DLT per configuration |
| Spring Integration inbound adapter/channel | Feeds records into message flows |
| `RequestHandlerRetryAdvice` | Retries the wrapped handler |
| Business handler | DB/HTTP side effects and idempotency |
| Kafka producer/outbound | Sends/acks records per producer policy |

### Partition ordering

~~~text
offset 100: order-created
offset 101: order-updated
offset 102: order-cancelled
~~~

If offset 100 fails:

- In-place retry preserves order but blocks the partition.
- Moving to a retry topic may let offset 101 run ahead of 100 unless ordering guards exist.
- Early offset commit risks losing tasks.
- Skipping commit and replaying causes duplicates if DB/HTTP already succeeded.

Kafka's transactional/exactly-once features within Kafka do not automatically guarantee exactly-once across external HTTP partners and out-of-transaction databases.

## 26. JDBC: retrying at the right transaction boundary

Potential failures:

- Connection pool temporarily exhausted;
- DB failover;
- Deadlock/serialization conflict;
- Lock timeout;
- Unique constraint violation;
- SQL schema/syntax error;
- Post-commit timeout with unknown outcome.

**Deadlocks** can usually be retried after rollback, but require a fresh transaction if previously marked `rollback-only`.

~~~text
Retry outer:
    attempt 1 -> BEGIN tx1 -> UPDATE -> deadlock -> ROLLBACK
    backoff
    attempt 2 -> BEGIN tx2 -> UPDATE -> COMMIT
~~~

Do not bundle an HTTP POST and a DB update into one blind callback, because retrying on a DB deadlock can resend an already-succeeded HTTP call.

### JDBC inbound polling

~~~text
NEW -> CLAIMED -> PROCESSING -> DONE
                  |
                  +-> RETRY_WAIT -> PROCESSING
                  |
                  +-> PARKED
~~~

Rows need a stable ID, `attempt_count`, `next_attempt_at`, `lease_owner`, `lease_until`, and proper atomic claiming. An in-memory `RetryContext` does not recover a row if a worker dies mid-`PROCESSING`.

## 27. Nested retries and call multipliers

Example:

~~~text
HTTP Client: 3 attempts
  -> API Gateway: 4 attempts
      -> Handler advice: 4 attempts
          -> HTTP client: 2 attempts
~~~

The partner can receive up to **3 × 4 × 4 × 2 = 96 calls** for a single business event in the worst case if every layer uses its full budget without further limits.

### How to coordinate

1. Designate the retry owner at each boundary.
2. Publish `maxAttempts` counting the initial call.
3. Set per-attempt timeouts and a total deadline.
4. Disable or minimize retries at other layers unless justified.
5. Share a single idempotency key.
6. Use backoff/jitter, rate limiters, and circuit breakers.
7. Cap concurrency with bulkheads.
8. Measure handler attempts, broker deliveries, and durable redrives separately.
9. For prolonged outages, transition to durable delayed retry.

| Mechanism | Solves | Does not replace |
|---|---|---|
| Retry | Transient errors | Idempotency |
| Backoff/jitter | Load spreading | Exception classification |
| Circuit breaker | Stops calling failing dependencies | Message persistence |
| Rate limiter | Quotas and bursts | Business correctness |
| Bulkhead | Isolates workers/threads | Outcome reconciliation |
| Delayed retry | Long waits via storage | Transactions/acks |
| DLQ/parking | Holds failed messages | Fixing invalid payloads |
| Inbox/outbox | Preserves send intent / deduplicates | System-wide exactly-once |

## 28. When to move from handler retry to durable delayed retry

`RetryAdvice` with standard `BackOffPolicy` runs **inside an in-process call chain**. On process restart, active `RetryContext` state is not persisted automatically; recovery falls back to the source and system storage.

### Short in-process retry fits when

- Transient faults typically clear in hundreds of milliseconds to a few seconds.
- Attempt counts are low, timeouts are clear, and total deadline allows.
- The worker pool has capacity.
- The operation is idempotent/replay-safe.
- A caller is waiting on a response within deadline.
- No other broker retry silently multiplies attempts.

### Durable delayed retry fits when

- The partner may be down for minutes or hours.
- Thousands of messages are waiting and should not hold consumer threads.
- Work must survive restarts/redeployments.
- `Retry-After` exceeds the synchronous caller's deadline.
- Operators need inspect, pause, schedule, redrive, retention, and ownership.
- Messages carry business expiry, `OUTCOME_UNKNOWN`, or need manual review.

| Criterion | `RequestHandlerRetryAdvice` | Durable delayed retry |
|---|---|---|
| Unit | Handler invocation | Persisted message/job/event |
| State | In-process `RetryContext` | DB/queue/topic/message store |
| Time horizon | Typically short | Can be long |
| Worker thread | May wait during backoff | Does not hold call stack |
| Restart | State not auto-recovered | Survives with proper store/ack |
| Attempt count | Per current invocation | Persisted across executions |
| Terminal outcome | Exception / recovery callback | Explicit `PARKED`/DLQ/`CANCELLED` |
| Ordering | Depends on handler/container | Must be explicitly designed |
| Idempotency | Required | Still required |

**Combined model:** short bounded handler retry (2–4 attempts); if transient failure persists, persist the message to durable delayed retry with `nextAttemptAt` for another worker to pick up later. For permanent errors, quarantine instead of blindly redriving.

### Sample durable retry record

~~~json
{
  "eventId": "invoice-882-v3",
  "target": "erp-http",
  "operation": "invoice.upsert",
  "state": "RETRY_WAIT",
  "attemptCountPersisted": 6,
  "nextAttemptAt": "2026-11-23T10:30:00Z",
  "deadlineAt": "2026-11-24T00:00:00Z",
  "lastErrorCategory": "SERVICE_UNAVAILABLE",
  "payloadRef": "secure-store/invoice-882",
  "idempotencyKeyRef": "invoice-882-v3"
}
~~~

This is an illustrative schema. Never store bearer tokens, SSH keys, or raw sensitive contents in retry records.

## 29. Logging, tracing, and metrics

Just logging `"retrying..."` per attempt cannot explain total calls or prove zero duplicated business work.

### Log contract

| Field | Purpose |
|---|---|
| `businessEventId` | Tracks the same business action across retry, redelivery, replay |
| `correlationId`/`traceId` | Connects inbound, handler, outbound, recovery |
| `flowId`/`endpointId` | Identifies the advised handler |
| `source`/`targetAlias` | System grouping without exposing secret hosts |
| `attemptIndex`/`maxAttempts` | Accurate handler execution count |
| `exceptionType`/`errorCategory` | Transient/permanent/unknown outcome |
| `backoffRequestedMs`/`elapsedMs` | Controls latency |
| `retryPolicyVersion` | Identifies which policy is active |
| `recoveryOutcome` | `SUCCESS`, `EXHAUSTED`, `PARKED`, `DEAD_LETTERED`, `CANCELLED` |
| `sourceAckOrCommitOutcome` | Whether message/offset was confirmed |
| `idempotencyKeyRef` | Links attempts of the same event |

**Never log** passwords, SFTP private keys, bearer tokens, session cookies, or full customer payloads. Message headers may contain sensitive data; never serialize all headers into error logs.

### Metrics to separate

| Metric | Meaning |
|---|---|
| `handler_attempts_total` | Total handler invocations by endpoint and error category |
| `retry_success_after_failure_total` | Handler retry sequences succeeding after at least one error |
| `retry_exhausted_total` | Retry sequences exhausting their budget |
| `retry_backoff_seconds` | Distribution of policy wait intervals |
| `handler_latency_seconds` | Total handler duration including attempts/backoff |
| `first_attempt_success_rate` | Rate of success without needing retries |
| `broker_redelivery_total` | Source/broker message redeliveries |
| `durable_redrive_total` | Replays from DLQ/parking/job store |
| `parked_backlog_age_seconds` | Age of messages awaiting handling |
| `duplicate_business_effect_total` | Verified duplicate side effects |
| `dedupe_hits_total` | Duplicate events caught by business key |
| `pool_blocked_threads` | Threads held by timeouts/backoff |
| `partner_error_rate` | 429/503/timeouts by dependency |

**Never use `businessEventId`, `orderId`, or `traceId` as metric labels** due to high cardinality. IDs belong in logs/traces; metric labels should use bounded sets like endpoint, target alias, `errorCategory`, and `finalOutcome`.

If first-attempt success plunges while eventual retry success stays high, the system may be **masking a dependency outage**. Read metrics together with latency, queue depth, and duplicate effects.

### RetryListener and tracing

Use `RetryListener`/instrumentation to record open/onError/close on `RetryTemplate`. Verify API version, thread safety, and payload security. A trace for one business event can contain multiple attempt spans; business counters still count **one business event**, never treating each attempt as a new order.

## 30. Testing RequestHandlerRetryAdvice

Meaningful testing does not stop at asserting a mock ran N times; prove **outcome, scope, and side effects**.

### 30.1. RetryTemplate unit test

~~~java
import java.io.IOException;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.retry.backoff.NoBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

// Snippet inside a test method; Java must support Map.of.
RetryTemplate template = new RetryTemplate();
template.setRetryPolicy(new SimpleRetryPolicy(
        3, Map.of(IOException.class, true), true, false));
template.setBackOffPolicy(new NoBackOffPolicy());

AtomicInteger calls = new AtomicInteger();
String result = template.execute(ctx -> {
    if (calls.incrementAndGet() < 3) {
        throw new IOException("Temporary connection failure");
    }
    return "OK";
});

// Expected: result = "OK", calls = 3.
~~~

`NoBackOffPolicy` is only for fast unit tests; **not a configuration for production network failures**. When testing exponential intervals, use a `Sleeper`/test double or measurement mechanism suited to your Spring Retry version, avoiding brittle wall-clock assertions.

### 30.2. Testing real endpoint advice

~~~text
testInputChannel
    -> upstreamTransformer
    -> handlerWithRetryAdvice (simulates 2 errors)
    -> successChannel
~~~

Verify:

1. One message with a stable `eventId` is sent.
2. The handler is invoked **3 times**.
3. The upstream transformer runs **once** in the tested topology.
4. Downstream receives **1 result**.
5. Correlation ID is preserved accurately.
6. The error flow sees no terminal failure since the final attempt succeeded.

### 30.3. Testing exhaustion

Have the handler always fail with a retryable error:

- With `maxAttempts=4`, assert **exactly four invocations**.
- If recovery rethrows, the caller/container observes the terminal exception.
- If recovery parks the message, the record is genuinely durable before source ack.
- If parking fails, do not mark the message successfully processed.
- If the broker later redelivers, idempotency still holds.

### 30.4. Testing wrapped exceptions

Use `MessageHandlingException` wrapping `IOException` in one case and `InvalidPayloadException` in another. Verify the classifier:

- Retries the approved transient cause.
- Does not retry invalid payloads.
- Does not blindly retry every `MessagingException`.

Exact wrapper/exception names depend on adapter/version; test with real exceptions thrown by your project's integration flow.

## 31. End-to-end test matrix

| ID | Scenario | Expected outcome |
|---|---|---|
| A1 | Handler succeeds on first attempt | One invocation, no backoff |
| A2 | Two transient errors then success | Three attempts, one downstream result |
| A3 | Continuous failure with `maxAttempts=4` | Four attempts, proper recovery |
| A4 | Invalid payload | No retry, quarantined |
| A5 | HTTP 401/403 | Does not retry with same credentials |
| A6 | HTTP 429 + `Retry-After` | Rate/deadline honored |
| A7 | HTTP 503 across multiple instances | Jitter/rate limits prevent abnormal bursts |
| A8 | POST committed but response lost | No duplicate thanks to idempotency/reconciliation |
| A9 | `RetryAdvice` only on HTTP handler | Upstream transformer does not re-run |
| A10 | Downstream JDBC fails after ERP succeeds | HTTP POST is not repeated |
| A11 | `RecoveryCallback` rethrows | Caller/container gets terminal error |
| A12 | `RecoveryCallback` returns normally | Acks only when message is safely persisted |
| A13 | In-memory error channel has no subscriber | Durable DLQ not falsely marked successful |
| A14 | Writing DLQ fails | Source message not lost |
| A15 | SFTP outbound upload finished then timed out | Remote state reconciled |
| A16 | SFTP inbound accept-once filter | Handler retry not mistaken for re-download |
| A17 | File not yet completely published | Partial file not parsed |
| A18 | JMS transacted listener fails | Rollback/redelivery per contract |
| A19 | Continuous AMQP nack/requeue | No hot loop; DLQ/delayed retry |
| A20 | Kafka record fails | Offset/retry topic/DLT behaves properly |
| A21 | Kafka retry topic affects ordering | Test flags issue when business requires strict order |
| A22 | JDBC deadlock | Fresh transaction and single commit |
| A23 | Transaction already `rollback-only` | Broken transaction not reused |
| A24 | Downstream error after `ExecutorChannel` | Error flow handles properly |
| A25 | `DirectChannel` with long backoff | Does not exceed caller deadline |
| A26 | Process restarts mid-retry | Source/durable state recovers |
| A27 | Circuit breaker open | No new remote calls violating policy |
| A28 | Nested retries across layers | Total calls match budget |
| A29 | Broker duplicate delivery | Deduplication prevents duplicate business effects |
| A30 | Error logs encounter tokens | Secrets redacted |
| A31 | Business event past deadline | Redrive stops |
| A32 | Partner down for hours | Uses delayed retry instead of holding all threads |
| A33 | Client times out while handler still runs | Cancellation/side-effect policy clear |
| A34 | DLQ replay after data fix | Audited and idempotent |
| A35 | `RetryPolicy` changed post-rollout | Contract tests catch shifts in attempts/latency |
| A36 | Two flows share one advice | Policies/metrics distinguish endpoints |

### Crash-point testing

Intentionally stop the application between:

1. Receiving a message and writing to inbox;
2. HTTP partner committing and client receiving response;
3. DB committing and publishing to AMQP;
4. Writing DLQ and acking the source;
5. Acking the source and finishing audit logs.

For every point, document how the system recovers, how it deduplicates, and evidence of **zero loss and zero double side effects**. Do not merely assert mock invocation counts.

## 32. Case study: SFTP → HTTP ERP → JDBC → AMQP

### Background

An enterprise receives order files via SFTP and syncs each record to ERP.

~~~text
SFTP inbound adapter + poller
   -> staging
   -> parse + validate
   -> orderMessagesChannel
   -> HTTP outbound gateway (ERP)
   -> JDBC update status
   -> AMQP notification
   -> archive file
~~~

Requirements:

- Zero duplicate ERP orders.
- Zero lost records when the partner is down.
- Invalid records must be quarantined.
- Replays can be triggered by business event ID.
- Process restarts must not lose pending tasks.

### Timeline

| Time | Event |
|---|---|
| 08:00 | Partner is uploading `orders-312.part` |
| 08:02 | File is published as `orders-312.ready` |
| 08:03 | Poller picks up valid record A; record B lacks `customerId` |
| 08:04 | HTTP POST A: ERP commits, but response is lost |
| 08:05 | Second retry risks creating a duplicate order |
| 08:06 | ERP returns 503; multiple workers retry concurrently |
| 08:07 | JDBC status update for A hits deadlock |
| 08:08 | RabbitMQ disconnects |
| 08:09 | App restarts while some handlers are in backoff |
| 08:12 | File is replayed from staging |
| 08:15 | Ops only sees the error channel, unsure if messages were persisted durably |

### Tasks

1. Which endpoint should receive the advice, and why?
2. Which errors should retry, and which should not?
3. Propose `maxAttempts`, backoff, and total deadline for ERP.
4. Explain how timeout after remote commit differs from connect failure.
5. Propose a stable event ID / idempotency key and state machine.
6. What happens when retries are exhausted so no messages are lost?
7. Why should JDBC deadlocks and AMQP downtime not trigger a full-flow retry?
8. How do the SFTP poller, retry advice, and delayed replay differ?
9. If the broker redelivers multiple times, how are total handler calls computed?
10. Pick at least five metrics and eight test cases to verify.

### Reference solution guide

**1. Placement:** attach `RequestHandlerRetryAdvice` to the **ERP HTTP outbound gateway**, provided the operation is retry-safe. JDBC uses separate transaction retry; AMQP publishes via outbox with its own retry/recovery. Do not wrap the entire chain.

**2. Classification:** 503 can use short retries; HTTP timeout after POST commit is `OUTCOME_UNKNOWN`; invalid B does not retry; wrong SFTP host key/credentials require fixing auth; JDBC deadlocks can retry a fresh transaction; AMQP outage needs durable retry.

**3. Sample policy:** `maxAttempts=4` total, exponential 250/500/1,000 ms with jitter, connect/read timeouts, and contracted deadlines. These are **illustrative numbers**, not a universal standard. Prolonged partner outages move to durable delayed retry.

**4. Avoiding duplicates:** `Idempotency-Key = partnerId + orderId + businessVersion`; reuse the exact same key across all attempts and redrives if ERP supports that contract. Otherwise, query/reconcile status before resending.

**5. State:** `RECEIVED` → `VALIDATED` → `ERP_PENDING` → `ERP_CONFIRMED` → `NOTIFICATION_PENDING` → `DONE`; auxiliary states `OUTCOME_UNKNOWN`, `RETRY_WAIT`, `INVALID`, `PARKED`. Inbox with unique business key; outbox for AMQP.

**6. Recovery:** failed messages carry `eventId`, payload reference, reason, attempts, owner/expiry, and terminal state; ack source only after persisting or per contract. If parking fails, propagate the error or use another guaranteed mechanism.

**7. Separating transactions:** DB deadlock retries the properly scoped DB transaction; AMQP outage is handled by the outbox publisher retrying after commit. Never re-call ERP just because notification failed.

**8. Three cycles:** SFTP poller checks for files on a schedule; `RetryTemplate`/backoff retries the HTTP handler briefly; durable replay persists messages across restarts and re-runs on schedule.

**9. Total calls:** e.g., 4 attempts/delivery × 5 deliveries = **20 handler invocations**, excluding HTTP client retries.

**10. Observability/tests:** `handler_attempts_total`, `retry_exhausted_total`, first-attempt success, `duplicate_business_effect_total`, parked backlog age, broker redeliveries, handler latency, and AMQP publish results. Test invalid B, 503 recovery, timeout after commit, JDBC rollback, AMQP outage, restarts, parking failure, SFTP accept-once, broker redelivery, and retry storms.

### Target architecture

~~~mermaid
flowchart TD
    S["SFTP ready file"] --> V["Stage + validate"]
    V -->|"Invalid"| Q["Quarantine reason"]
    V -->|"Valid"| I["Inbox stable eventId"]
    I --> E["ERP operation state"]
    E --> R{"Transient and retry-safe?"}
    R -->|"Yes"| H["HTTP Handler + RetryAdvice"]
    R -->|"Outcome unknown"| C["Query ERP / reconcile"]
    H -->|"Success"| D["ERP_CONFIRMED"]
    C -->|"Confirmed"| D
    H -->|"Exhausted"| P["Durable RETRY_WAIT / PARKED"]
    P -->|"Due and within deadline"| E
    D --> T["DB transaction: update + outbox"]
    T --> A["AMQP outbox publisher"]
    A -->|"Broker down"| W["Delayed publish"]
    W --> A
    A --> Z["DONE + archive"]
    Q --> O["Audit / triage"]
    P --> O
~~~

The diagram depicts responsibilities only; any delayed retry loop must enforce deadlines, max attempts, concurrency/rate control, and terminal states. Never implement an unbounded busy loop.

## 33. Anti-patterns to avoid

| Anti-pattern | Harm | Fix |
|---|---|---|
| Retrying every `Exception` | Validation/auth errors repeat needlessly | Classify by exception and operation |
| Advice around a long workflow | Repeats already-succeeded side effects | Retry per handler |
| Confusing `maxAttempts` with extra retries | Exceeds expected call counts | Count the initial attempt |
| No backoff/timeout | Storms or hung threads | Timeouts + backoff + deadline |
| POST without idempotency | Duplicate orders/payments | Stable key/reconciliation |
| `RecoveryCallback` swallowing errors | Broker acks unpersisted messages | Durable recovery or rethrow |
| Treating error channel as a durable DLQ | Messages lost on restart | Message store/broker DLQ |
| Confusing handler retry with broker delivery | Total attempts multiply | Overall retry budget |
| Confusing retry with poller | Does not re-read the same file | Durable message state |
| JDBC retry inside `rollback-only` tx | Commit still fails | Retry a fresh transaction |
| Using message UUID as business key | Deduplication fails | Stable `eventId` |
| Kafka early offset commit | Lost business events | Proper ack/error handler |
| Infinite AMQP requeue | Broker hot loop | Delayed retry/DLQ |
| Re-uploading SFTP without checking remote | Duplicate/partial files | Temp file/checksum/reconcile |
| Holding threads for hours | Exhausts concurrency | Durable delayed retry |
| Never testing crashes | Silent message loss | Fault injection/crash tests |
| Logging tokens/secrets | Data leakage | Redaction/secure logging |
| Never testing cause chains | Retries wrong error types | Wrapped-exception tests |
| Measuring only retry success | Masks partner failures | First-attempt success and latency |

## 34. Implementation checklist

- [ ] Diagrammed inbound/source, channels, handlers, adapters, gateways, and error paths.
- [ ] Attached advice to the right endpoint without blindly wrapping the whole orchestration.
- [ ] Tested `RetryTemplate`/`RetryPolicy`/`BackOffPolicy` configurations.
- [ ] Classified transient/permanent/unknown outcomes.
- [ ] Tested real wrapper exceptions and cause chains.
- [ ] `maxAttempts` **includes the initial call**, paired with timeouts and deadlines.
- [ ] Configured appropriate backoff/jitter, `Retry-After`/rate limits/circuit breakers.
- [ ] Accounted for `@Retryable`, HTTP client retries, and broker redeliveries.
- [ ] Handler has stable `eventId` and idempotency/reconciliation.
- [ ] Verified retry/transaction advice ordering with commits and rollbacks.
- [ ] `DirectChannel`/`ExecutorChannel`/`QueueChannel` have proper error paths.
- [ ] File/SFTP pollers are not confused with durable replay.
- [ ] JMS/AMQP container ack/nack/DLQ does not swallow terminal errors.
- [ ] Kafka offsets/retry/DLT and ordering satisfy contracts.
- [ ] JDBC opens fresh transactions on retry when needed, backed by unique keys/outbox.
- [ ] `RecoveryCallback` never reports success before persisting the message durably.
- [ ] Parking/DLQ has owners, retention, alerts, and controlled redrive.
- [ ] Prolonged failures move to durable retry instead of tying up all threads.
- [ ] Metrics separate attempts, broker deliveries, redrives, and business effects.
- [ ] Logs exclude secrets and unnecessary sensitive payloads.
- [ ] Tested invalid data, auth errors, timeouts after commit, and recovery failures.
- [ ] Tested restarts/crashes, duplicate effects, concurrency, and SLAs.

## 35. Glossary, references, and review questions

### Glossary

| Term | Meaning |
|---|---|
| **`RequestHandlerRetryAdvice`** | Advice retrying message handler invocations in Spring Integration |
| **`RetryTemplate`** | Coordinates `RetryCallback`, `RetryPolicy`, `BackOffPolicy`, and recovery |
| **`RetryPolicy`** | Decides retryable exceptions and attempt limits |
| **`BackOffPolicy`** | Wait intervals between attempts |
| **`RetryContext`** | State of a retry sequence |
| **`RecoveryCallback`** | Action taken after retries are exhausted |
| **`ErrorMessage` / error channel** | Error routing path, not durable by default |
| **Idempotency key** | Key identifying the same business event across retries |
| **Unknown outcome** | Uncertainty over whether the remote committed |
| **DLQ/DLT/`PARKED`** | Destination holding failed messages for triage/replay |
| **Redelivery** | Broker/source re-delivering a message |
| **Ack/offset commit** | Source recording processing progress |
| **`DirectChannel`** | Channel typically dispatching synchronously on the sender's thread |
| **`ExecutorChannel`** | Channel using an executor, changing exception propagation |
| **Poller** | Fetches messages on a trigger/schedule |
| **Inbox/outbox** | Patterns for deduplicating receipts and persisting publish intent with transactions |
| **Circuit breaker/retry budget** | Caps calls to failing dependencies / total retries |
| **Poison message** | A message that cannot succeed unless data or policy changes |

### Conceptual references

- **Spring Integration Reference — Message Handler Advice / Retry and More:** `RequestHandlerRetryAdvice` and advice chains.
- **Spring Retry Reference:** `RetryTemplate`, `RetryPolicy`, `BackOffPolicy`, `RetryContext`, `RecoveryCallback`.
- **Spring Integration Reference — Polling Consumer, Message Channels, Error Handling:** sync/async boundaries and error channels.
- **Spring Integration Reference — File, SFTP, HTTP, JMS, AMQP, Kafka, JDBC adapters/gateways:** per-source/target semantics.
- **Spring for Apache Kafka Reference:** listener error handling, offsets, retry topics, and DLT.
- **Spring AMQP Reference:** nack/requeue, DLQ, and publisher confirms.
- **Spring Framework Transaction Management:** propagation, rollback, and advice ordering.
- **Enterprise Integration Patterns:** Idempotent Receiver, Dead Letter Channel, Message Store, Transactional Client.

### Review questions

1. Why does advice on an HTTP handler not make SFTP inbound re-read a file?
2. How many additional retries at most correspond to `maxAttempts=4`?
3. How can a `RecoveryCallback` returning `null` affect acknowledgement?
4. Why does an HTTP POST timeout after remote commit differ from a connect failure?
5. How many invocations can two stacked retry layers of 3 and 4 attempts produce?
6. How does `DirectChannel` with a long backoff affect an HTTP caller?
7. How does `ExecutorChannel` change error propagation?
8. Where must a JDBC `rollback-only` transaction be retried?
9. How do `RequestHandlerRetryAdvice` and a Kafka consumer error handler differ?
10. When should you move from in-process retry to durable delayed retry?

### Short answers

1. Advice only wraps the handler; pollers/filters have independent lifecycles.
2. **3 retries** after the initial attempt.
3. The container may treat the message as processed and ack before durable recovery exists.
4. The remote may already have applied side effects; idempotency/reconciliation is required.
5. **3 × 4 = 12** when both nested layers exhaust their attempts.
6. It can hold the sender thread longer than the caller's deadline.
7. Async errors need an error flow rather than propagating directly to the synchronous caller.
8. Retry a properly scoped fresh transaction without repeating external non-DB side effects.
9. Advice does not seek/commit offsets or create retry topics/DLTs.
10. When outages last long, load is high, or recovery across restarts is required.

**Key takeaway:** **`RequestHandlerRetryAdvice`** retries **the specific advised message handler invocation** in Spring Integration. Reliability comes not from raising `maxAttempts` alone, but from **error classification, proper handler boundaries, idempotency, transaction/ack alignment, durable recovery, and testing real side effects**. When external connections fail, prove that **no messages are lost, no duplicate side effects occur, and errors are handled at the right layer**.
