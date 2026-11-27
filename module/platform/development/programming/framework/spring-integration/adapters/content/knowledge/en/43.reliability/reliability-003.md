# BackOffPolicy on Connection Failures in Spring Integration Adapters

> **Chapter:** Reliability  
> **Lesson:** BackOffPolicy on connection failures  
> **Scope:** Connecting external systems with **Spring Integration** through inbound/outbound adapters, gateways, pollers, and MessageChannels. Applies to **File, SFTP, HTTP, JMS, AMQP, Kafka, and database** flows, while explaining message contracts, connection failures, retries, processing acknowledgements, and connection lifecycles.

## 1. Learning objectives

After this lesson, learners can:

1. Distinguish **RetryPolicy**, which decides *whether to retry*, from **BackOffPolicy**, which decides *how long to wait before the next attempt*.
2. Explain how **RetryTemplate, RetryContext, BackOffContext, RetryCallback, RecoveryCallback**, and **RequestHandlerRetryAdvice** work together in Spring Integration.
3. Choose between **no backoff, fixed, exponential, and randomized/jitter** based on error type, system load, recovery time, and source/target characteristics.
4. Calculate **attempts**, wait intervals, and total **latency budget**; combine connection/read timeouts, deadlines, rate limits, circuit breakers, and bulkheads.
5. Classify transient connection errors, authentication/authorization errors, data errors, and **unknown outcomes** to avoid pointless retries or duplicate business effects.
6. Identify the right retry boundaries for **HTTP outbound gateways, SFTP, File inbound pollers, JMS/AMQP, Kafka, and JDBC**.
7. Design **idempotency, acknowledgement, transactions, DLQ/parking, and delayed retry** so messages are not lost once in-process retries exhaust their budget.
8. Build metrics, alerts, and tests for connection failures, overload, restarts, prolonged outages, poison messages, and recovery.

## 2. Why is backoff needed when connections fail?

A Spring Integration Flow may read order files over SFTP, transform them into messages, call a partner HTTP API, save results in a database, and send notifications over AMQP.

~~~text
SFTP inbound adapter
   -> MessageChannel
   -> transformer / validator
   -> outbound HTTP gateway
   -> JDBC status update
   -> outbound AMQP adapter
~~~

When the outbound HTTP gateway fails to connect because the partner is overloaded, a naive approach is to retry immediately in a tight loop.

~~~text
08:00:00.000  Connection failed
08:00:00.005  Retry
08:00:00.010  Retry
08:00:00.015  Retry
...
~~~

If 1,000 instances do this simultaneously, the target system gets hit with an **extra wave of requests** right when it is unhealthy. The retry mechanism, built to improve reliability, can itself prolong the outage.

**Backoff** inserts an intentional pause between attempts. The pause can be fixed or progressively growing, and sometimes randomized so many clients do not retry at the exact same instant.

**`BackOffPolicy` does not make a request idempotent, does not determine which exceptions deserve retrying, and does not guarantee whether the external system already processed the request before timing out.**

The crucial question is not "should we wait 500 ms or 1,000 ms?", but:

> "Can this error recover on retry; and if so, **when should we retry, how many times, and is repeating the operation safe?**"

### A realistic scenario

- At 09:00, 300 messages must call an invoice-creation API.
- The Partner API returns **HTTP 503** for 20 seconds.
- If all clients retry immediately, the system is easily pushed into repeated overload.
- If all clients use an **exact 1-second fixed backoff**, they may still all retry in lockstep at the next second.
- If they use **exponential backoff with jitter**, attempts spread out over a window.
- If the partner is down for hours, **do not keep hundreds of worker threads sleeping**; persist the messages and use delayed retry or an appropriate queue.

## 3. Distinguishing RetryPolicy, BackOffPolicy, and recovery

In Spring Retry, each component has a distinct responsibility.

| Component | Answers the question | Example |
|---|---|---|
| **RetryTemplate** | Orchestrates the multi-attempt lifecycle | Runs handler up to 4 times per config |
| **RetryPolicy** | Can we still retry? | Max 4 attempts; transient errors only |
| **BackOffPolicy** | How long to wait before the next attempt? | 250 ms, 500 ms, 1,000 ms |
| **RetryCallback** | What unit of work is re-executed? | Calling the partner's HTTP GET |
| **RetryContext** | Which attempt is the sequence on, and what was the last error? | `retryCount` and `lastThrowable` |
| **BackOffContext** | Private state of the wait strategy | Current exponential pause interval |
| **RecoveryCallback** | How to handle exhausted retries? | Move to parking, report error, or rethrow |
| **RequestHandlerRetryAdvice** | Where does Spring Integration apply retry? | Wraps an advised message handler |

A `BackOffPolicy` does not decide to re-invoke a request if **`RetryPolicy` no longer allows it**. When the callback succeeds, no further backoff occurs. When a failure is non-retryable, the policy can stop immediately without waiting.

### Distinguishing attempts and retries

If `RetryPolicy` sets **maxAttempts = 4**:

| Execution | Name | Is there a backoff before this call? |
|---|---|---|
| 1 | Initial attempt | No |
| 2 | First retry | Yes, after failure #1 |
| 3 | Second retry | Yes, after failure #2 |
| 4 | Third retry | Yes, after failure #3 |
| Still failing after #4 | Exhausted/recovery | Does not open a fifth attempt |

Hence **4 attempts = 1 initial attempt + at most 3 retries**, not 4 retries after the first call.

## 4. BackOffPolicy lifecycle inside RetryTemplate

In the Spring Retry API, **`BackOffPolicy.start(RetryContext)`** creates a **`BackOffContext`** for a retry sequence, and **`BackOffPolicy.backOff(BackOffContext)`** executes the pause strategy before the next attempt.

This mechanism gives each retry sequence its own backoff state while allowing the policy object to be shared as implemented. It **does not turn sleep duration or `RetryContext` into data that persists across restarts**.

~~~mermaid
flowchart TD
    A["Message arrives at handler"] --> B["RetryTemplate opens RetryContext"]
    B --> C["BackOffPolicy.start: create BackOffContext"]
    C --> D{"RetryPolicy allows attempt?"}
    D -->|"Yes"| E["Invoke handler / RetryCallback"]
    E -->|"Success"| F["Finish, return result"]
    E -->|"Exception"| G["Classify error, update RetryContext"]
    G --> H{"Retryable and budget left?"}
    H -->|"Yes"| I["BackOffPolicy.backOff"]
    I --> D
    H -->|"No"| J{"RecoveryCallback?"}
    J -->|"Yes"| K["Intentional recovery"]
    J -->|"No"| L["Return/throw error to caller, container"]
    K --> M["End retry sequence"]
    L --> M
~~~

This diagram is conceptual; exception classification and exhaustion decisions are coordinated by `RetryPolicy` and `RetryTemplate`. **Backoff only adjusts timing**—it does not guarantee retry success.

### State variables typically worth observing

- Number of attempts executed, not confused with retry count.
- Most recent error and classified error category.
- Wait interval applied before the next attempt.
- Total elapsed time so far.
- Remaining business/request deadline.
- Idempotency key and stable event ID.
- Final outcome: `SUCCESS`, `EXHAUSTED`, `CANCELLED`, `PARKED`, or `DLQ`.

## 5. Common BackOffPolicy types

Spring Retry offers backoff strategies suited to different needs. Check exact class names and configuration capabilities against your project's dependency version when applying them.

| Type | Idea | When suitable | Risks |
|---|---|---|---|
| **NoBackOffPolicy** | No wait between attempts | Some very cheap internal cases known to recover instantly | Retry storm, CPU/request bursts |
| **FixedBackOffPolicy** | Waits a fixed interval each time | Brief glitches, low load, steady traffic | Many clients synchronize retry timing |
| **ExponentialBackOffPolicy** | Wait grows by multiplier, capped by `maxInterval` | Overloaded remote service, brief disconnects | Without jitter, clients still stay synchronized |
| **ExponentialRandomBackOffPolicy** | Based on exponential backoff plus randomization per implementation | Multiple instances calling a partner | Need to understand actual distribution/bounds |
| **UniformRandomBackOffPolicy** | Picks random wait within configured bounds | Want to spread attempts without necessarily growing intervals | Must pick sensible min/max |

### 5.1. NoBackOffPolicy

No wait between a failure and the next attempt. Useful for ultra-short contention errors in cheap internal operations, but **should not be the default for network failures**.

Even with capped attempts, 500 clients retrying 3 times back-to-back can multiply load abruptly on an unhealthy service.

### 5.2. FixedBackOffPolicy

If the interval is 500 ms and max attempts is 4:

~~~text
Attempt 1 --fail--> sleep 500 ms
Attempt 2 --fail--> sleep 500 ms
Attempt 3 --fail--> sleep 500 ms
Attempt 4 --fail--> exhausted
~~~

Total wait time is **3 × 500 ms = 1,500 ms** if all four fail and `RetryPolicy` permits retrying.

Advantage: simple and predictable. Limitation: multiple clients failing at the same time tend to **wake up in lockstep**.

### 5.3. ExponentialBackOffPolicy

With `initialInterval = 250 ms`, `multiplier = 2`, `maxInterval = 2,000 ms`, and 6 attempts, the wait sequence is roughly:

~~~text
Attempt 1 --fail-->  250 ms
Attempt 2 --fail-->  500 ms
Attempt 3 --fail--> 1000 ms
Attempt 4 --fail--> 2000 ms
Attempt 5 --fail--> 2000 ms (capped at ceiling)
Attempt 6 --fail--> exhausted
~~~

Total wait = **250 + 500 + 1,000 + 2,000 + 2,000 = 5,750 ms**.

Mental model for the *i*-th wait interval (*i* starting at 1):

**delay(i) = min(maxInterval, initialInterval × multiplier^(i−1)).**

This formula describes the exponential backoff concept, ignoring rounding, implementation bounds, or randomization. **Wait intervals only occur between attempts**, so for N attempts there are at most N−1 pauses.

### 5.4. Randomized backoff and jitter

Jitter adds randomness to wait intervals to reduce **thundering herd**, when hundreds of clients retry concurrently after a shared outage.

For example, two workers both retrying an API:

~~~text
Without jitter:
  Worker A: 250 ms -> 500 ms -> 1000 ms
  Worker B: 250 ms -> 500 ms -> 1000 ms
  Requests tend to keep colliding at the same instants.

With jitter (illustrative):
  Worker A: 210 ms -> 670 ms -> 940 ms
  Worker B: 330 ms -> 450 ms -> 1220 ms
  Requests are more spread out.
~~~

The jittered numbers above are illustrative only and **do not describe the exact formula of a specific Spring Retry class**. Full jitter, equal jitter, decorrelated jitter, and randomized exponential algorithms have different distributions. Rely on your library's contract and test your deployed configuration.

**Do not let jitter turn into unbounded delay**; you still need `maxInterval`, `maxAttempts`, and a total deadline.

## 6. Calculating the time budget when connections fail

A major mistake is configuring `BackOffPolicy` while forgetting that **each attempt can itself wait a long time to time out**.

Suppose:

- `maxAttempts` = 5;
- each HTTP attempt has a maximum timeout of 1.5 seconds;
- exponential backoff is 250, 500, 1,000, 2,000 ms;
- no jitter.

Approximate total duration if all five attempts time out:

**5 × 1.5 s + (0.25 + 0.5 + 1 + 2) s = 11.25 seconds**.

That excludes connection setup, TLS handshake, scheduling, dispatch, queuing, and data processing. If the HTTP inbound gateway caller only waits 5 seconds, such a retry policy **exceeds the request budget**.

### General formula

For N attempts:

**T_total ≈ Σ T_attempt(i) + Σ delay(i),** where the delay sum has at most N−1 terms.

To stay safe, you need:

1. A dedicated connection timeout for establishing connections.
2. A read/response timeout for in-flight calls.
3. A **total deadline** for the business action or request.
4. Max attempts per error/operation type.
5. Capped backoff with appropriate randomization.
6. A shared budget across layers (client, gateway, adapter, broker).
7. A way to cancel or stop when the caller is no longer waiting and the operation should not continue.

**`BackOffPolicy` does not cap the duration of a hung network call.** Without network timeouts, execution may never reach the backoff step.

### Suggested time layering

| Layer | Example target | Notes |
|---|---|---|
| TCP connect | Small bound, tuned to network and partner | Not identical to read timeout |
| HTTP response | Tailored to specific API | Weigh expensive operations and unclear outcomes |
| Handler attempts | 2–4 attempts as illustration | Not a universal standard |
| In-process backoff | Hundreds of ms to a few seconds where sensible | Depends on SLA and worker concurrency |
| Durable delayed retry | Minutes or hours during extended outages | Backed by durable state and monitoring |
| Business deadline | Point at which the operation is no longer meaningful | Do not keep sending expired tasks |

## 7. Classifying errors before choosing wait intervals

Do not send every exception through the same `BackOffPolicy`. **Retryability** depends on both error type and the safety of repeating the operation.

| Error/symptom | Should you retry? | Reference backoff | What to verify |
|---|---|---|---|
| Connection reset, temporary network unreachable | Possibly | Exponential + jitter | Is the previous request's outcome known? |
| Connect timeout | Possibly | Bounded, progressive | DNS, firewall, connection limits |
| Read timeout after HTTP POST | Not necessarily | Do not retry blindly | Target may have processed it; need idempotency/reconciliation |
| HTTP 429 | Usually conditionally | `Retry-After`/rate-limit-aware | Quota, request type, deadline |
| HTTP 503 | Possibly | Exponential + jitter | Avoid piling load onto overloaded partner |
| HTTP 502/504 | Possibly, safety uncertain | Budgeted | Upstream may have committed side effects |
| HTTP 400, invalid schema | Usually no | No backoff | Fix payload or contract |
| HTTP 401/403 | Usually do not retry with same credentials | No backoff | Refresh credentials via valid flow, fix permissions |
| SFTP authentication/host-key failure | Do not retry with same config | No infinite backoff | Authenticate and verify host properly |
| Temporary SFTP/AMQP/JMS connectivity | Possibly | Exponential + jitter, per client | Session/failover/ack state |
| Kafka broker temporarily unavailable | Depends on adapter/container | Error handler/container backoff | Partition, commit, rebalance, and version |
| JDBC deadlock/serialization conflict | Possibly with clean new transaction | Short backoff with jitter | Rollback/recreate transaction |
| Unique constraint/validation failure | Usually no | None | Data conflict or duplicate requiring classification |
| Disk full/permission denied | Usually do not retry continuously | Stop/alert | Requires human or system remediation |
| Poison message | Not with the same payload | None | Quarantine/DLQ, fix data |
| Service rate-limited for extended period | Do not hold threads indefinitely | Durable delayed retry | Respect retry budget and message age |

### Unknown outcome differs from transient error

**Transient** means the cause may disappear on its own. **Unknown outcome** means we do not know whether the previous call already took effect. These two properties are independent.

For example, a partner times out after successfully recording an order. The network glitch may be transient, yet resending POST may **create two orders**. Thus alongside `RetryPolicy`/`BackOffPolicy`, you need one of:

- Partner-supported idempotency keys;
- Status lookup by business transaction ID;
- Upsert keyed by business key;
- Transactions/outbox/inbox or reconciliation;
- Manual review when safety cannot be verified.

## 8. Java example: configuring ExponentialRandomBackOffPolicy

The example uses Spring Retry with several Spring Web exceptions. It is an **illustrative configuration**; verify Spring Retry/Spring Integration/Spring Web versions and how your HTTP client throws or wraps exceptions.

~~~java
import java.util.HashMap;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.backoff.ExponentialRandomBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;

@Configuration
public class PartnerRetryConfig {

    @Bean
    public RetryTemplate partnerRetryTemplate() {
        Map<Class<? extends Throwable>, Boolean> retryable = new HashMap<>();

        // Example: classification based on actual HTTP client exceptions.
        retryable.put(ResourceAccessException.class, true);
        retryable.put(HttpClientErrorException.TooManyRequests.class, true);
        retryable.put(HttpServerErrorException.ServiceUnavailable.class, true);

        // 4 attempts TOTAL. Inspect nested causes inside wrappers when appropriate.
        // Other exceptions: do not retry under this sample config.
        SimpleRetryPolicy retryPolicy =
                new SimpleRetryPolicy(4, retryable, true, false);

        ExponentialRandomBackOffPolicy backOff =
                new ExponentialRandomBackOffPolicy();
        backOff.setInitialInterval(250L);
        backOff.setMultiplier(2.0);
        backOff.setMaxInterval(2_000L);

        RetryTemplate retryTemplate = new RetryTemplate();
        retryTemplate.setRetryPolicy(retryPolicy);
        retryTemplate.setBackOffPolicy(backOff);

        return retryTemplate;
    }
}
~~~

### Limitations to understand in this example

- **`ResourceAccessException`** can represent connection or I/O errors; for HTTP POST with side effects, marking it retryable in the map **is not enough** to prove safety.
- **`HttpClientErrorException.TooManyRequests`** only reflects a 429 status translated by the HTTP client into that exception; `Retry-After` requires separate handling to honor server-requested wait times.
- An HTTP client or endpoint may wrap errors in **`MessagingException`** or custom exceptions; inspect the cause chain and real runtime exceptions.
- **`ExponentialRandomBackOffPolicy`** adds randomization but does not cap attempts; **`SimpleRetryPolicy`** enforces that cap.
- No **end-to-end deadline**, circuit breaker, rate limiter, persistent queue, or idempotency is configured in this snippet.
- If the partner returns 500/502/504 and those are not in the classifier, they may not be retried; make explicit choices per API contract rather than adding a catch-all.
- For error responses **that should not be retried**, defining backoff does not make them retryable; check `RetryPolicy`.

### Fixed backoff example for small environments

~~~java
import org.springframework.retry.backoff.FixedBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

RetryTemplate template = new RetryTemplate();

SimpleRetryPolicy retryPolicy = new SimpleRetryPolicy(3);
FixedBackOffPolicy fixedBackOff = new FixedBackOffPolicy();
fixedBackOff.setBackOffPeriod(400L);

template.setRetryPolicy(retryPolicy);
template.setBackOffPolicy(fixedBackOff);

// 3 attempts total, up to 2 pauses x 400 ms.
// Note: SimpleRetryPolicy(3) does not restrict the exception list.
~~~

This snippet is for understanding wiring; **do not use an unconditional "retry all exceptions" config** on production adapters.

## 9. Attaching BackOffPolicy to Spring Integration

In Spring Integration, the usual pattern is configuring `BackOffPolicy` on **`RetryTemplate`** and attaching that `RetryTemplate` to an endpoint's **`RequestHandlerRetryAdvice`**.

### 9.1. Creating RequestHandlerRetryAdvice

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.support.RetryTemplate;

@Configuration
public class IntegrationAdviceConfig {

    @Bean
    public RequestHandlerRetryAdvice partnerRetryAdvice(
            RetryTemplate partnerRetryTemplate) {

        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(partnerRetryTemplate);

        // Do not swallow errors here. When exhausted, the exception must still
        // be handled by the caller / error flow / consumer container
        // according to source semantics.
        return advice;
    }
}
~~~

If you choose a custom `RecoveryCallback`, distinguish **successful recovery** from **ending with an error**. A `RecoveryCallback` that logs and returns normally can make the caller treat the handler as finished, affecting ack/commit.

### 9.2. Retrying only an outbound HTTP gateway

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
    IntegrationFlow partnerStatusIntegrationFlow(
            RequestHandlerRetryAdvice partnerRetryAdvice) {

        return IntegrationFlow.from("statusRequestChannel")
                .handle(
                    Http.outboundGateway(
                            "https://partner.example.invalid/api/status")
                        .httpMethod(HttpMethod.GET)
                        .expectedResponseType(String.class),
                    endpoint -> endpoint.advice(partnerRetryAdvice)
                )
                .channel("statusReplyChannel")
                .get();
    }
}
~~~

**GET** is used to separate backoff mechanics from a state-mutating POST. The `example.invalid` domain is illustrative only.

In this flow:

- **`MessageChannel`** receives the message.
- **Outbound HTTP gateway** sends the request to the partner.
- **`RequestHandlerRetryAdvice`** wraps the invocation of the advised handler.
- **`RetryTemplate`** decides whether to retry; `BackOffPolicy` controls the wait interval.
- Successful results pass to the next channel.
- When exhausted, failures follow the configured exception/error handling path.

**What does NOT happen automatically:** retry advice **does not** re-read an upstream SFTP file, **does not** retry upstream transformers before the endpoint, **does not** manage Kafka offsets, and **does not** make a non-idempotent HTTP operation safe to repeat.

### 9.3. Why advice placement matters so much

~~~text
SFTP.inboundAdapter
    -> parse file
    -> transform record
    -> HTTP.outboundGateway [retry advice]
    -> JDBC.outboundAdapter
    -> AMQP.outboundAdapter
~~~

If the HTTP outbound gateway fails, the advice retries the **HTTP handler**. It does not re-run preceding or succeeding steps.

If retry is placed at a service level spanning HTTP + JDBC + AMQP, a late AMQP failure can repeat the HTTP and DB calls—meaning the **retry scope is wrong**. Split business units or apply outbox and explicit state transitions.

## 10. BackOffPolicy vs. poller: two different timing mechanisms

Spring Integration provides **pollers** to periodically fetch messages from a `MessageSource` such as File/SFTP/JDBC. A poller uses **`fixedDelay`/`fixedRate`/`cron` or another trigger**, which is a **source-checking schedule**, not `RetryTemplate`'s `BackOffPolicy`.

### Example

~~~text
SFTP Poller: checks remote directory every 5 seconds.
At 10:00: SFTP server times out.

Mechanisms that may exist:
  A. Poller tries again on its next schedule at 10:00:05.
  B. A specific SFTP operation is wrapped with 3 retry attempts.
  C. Scheduler adjusts the poll interval when upstream is down long-term.
~~~

**A, B, and C are not equivalent.** If each poll runs 3 attempts with a 2-second backoff while polling every 5 seconds, request volume to SFTP can exceed expectations. Sum all layers and clarify who owns reconnecting.

### Poller characteristics

- When a poller finds no messages, that is normal, **not an exception for `RetryTemplate`**.
- If the poller fetches a file and downstream fails, the next poll **is not guaranteed to pick up the same file again** if an accept-once filter or metadata store already recorded it.
- A concurrent poller may run multiple tasks in parallel; backoff holding worker threads can hurt throughput.
- For prolonged source outages, adjusting the **polling schedule** or pausing the adapter can be far more effective than sleeping threads inside `RetryTemplate`.
- Upon recovery, avoid having all pollers across every instance wake up simultaneously and overwhelm the source.

**Handler retry backoff differs from poll schedules and from internal client-library retry/reconnect.**

## 11. Backoff for File adapters: do not retry corrupt content like a connection error

Filesystems differ from remote APIs: a file may **still be mid-write**, lose read permissions, or contain invalid content.

### Inbound File

| Scenario | Strategy | Role of backoff |
|---|---|---|
| File still uploading | Use temp names, ready markers, proper filters | Wait for next poll; do not continuously retry parsing |
| Transient filesystem I/O | Bounded retry if safe | Short fixed/exponential depending on load |
| Permission denied | Fix permissions/ACLs | Backoff alone will not fix it |
| Invalid JSON/CSV | Quarantine with reason code | Do not retry same payload |
| Downstream HTTP fails after file ingested | Persist records durably, retry right handler | Outbound backoff, do not rely on re-polling |
| File moved/archived prematurely | Recover from staging/backup | Retry only after verifying state |

### Complete file contract

A sound workflow:

1. Partner writes **`orders-45.part`**.
2. Once finished, publishes to **`orders-45.ready`** using an appropriate guaranteed mechanism.
3. File inbound adapter only picks up ready files.
4. Assign a **stable business event ID** per record or file.
5. Parse/validate; route invalid data to quarantine.
6. Downstream retries per operation and independent budget.
7. After completion or durable error preservation, archive per business state.

**Do not treat a file accept-once filter as an end-to-end exactly-once guarantee**: worker restarts, non-durable metadata stores, or replays alter behavior. Business-layer idempotency remains necessary.

### Outbound File

If writing a file hits an I/O error mid-way, directly retrying the same destination can leave partial files or overwrite data. Use **temporary output + publish/rename where the filesystem supports it**, with filenames tied to event IDs. Backoff only prevents tight I/O loops; it does not make file writes atomic.

## 12. Backoff for SFTP: connections, sessions, and transfer state

SFTP is where `BackOffPolicy` is often helpful because remote links drop intermittently. However, the adapter has several distinct stages:

- Opening a session and authenticating host/user;
- Listing the remote directory;
- Downloading files to local staging;
- Uploading files to remote;
- Renaming/moving remote files;
- Closing/returning sessions to the pool or cache.

### Classification by operation

| Operation | Retryable errors | What to avoid |
|---|---|---|
| SFTP connect | Temporary timeouts, connection resets | Retrying invalid private keys or unverified host keys |
| List files | Busy server, brief network instability | Overlapping polls adding load or double-collecting |
| Download | Disconnect mid-transfer | Treating a local partial file as complete |
| Upload | Disconnect near end of transfer | Duplicating/overwriting remote files of unknown state |
| Remote rename | Server timeout | Assuming rename did not run if response was lost |
| Remote delete | Network timeout after delete | Retrying into missing-file errors and mishandling |

### Recoverable upload workflow

~~~text
Message eventId=invoice-882-v4
   -> pick remote tempName derived from eventId
   -> upload payload
   -> verify result/size/checksum if available
   -> publish/rename to final name
   -> record CONFIRMED status
~~~

If an upload times out, check **whether the temp or final file already exists**, whether size/hash matches, and what the overwrite policy is. **Do not assume every SFTP server supports atomic rename with identical semantics**, especially across filesystems or indirect backends.

### Reconnect is not replay

An SFTP client may automatically open a new session when the old one breaks. However:

- A new session **does not tell you** how many bytes the previous transfer wrote.
- Remote accept-once or local metadata may already have recorded the file.
- Retrying an outbound HTTP handler **does not re-download an SFTP file**.
- Backoff does not replace host-key checks, credential rotation, or directory permissions.

You must define where **transfer state** and **message state** are stored, how the session factory/cache behaves, and when connections are retired and refreshed.

## 13. Backoff for HTTP outbound gateways

An HTTP outbound gateway is usually the clearest candidate for `RequestHandlerRetryAdvice` because it represents a remote call that can time out.

### Distinguishing status codes and operations

| Response/error | Backoff? | Key conditions |
|---|---|---|
| 429 Too Many Requests | Possibly; prioritize valid `Retry-After` | Quota, wait limit, endpoint, and idempotency |
| 503 Service Unavailable | Possibly, exponential + jitter | Avoid amplifying overload |
| 502 Bad Gateway | Possibly depending on error source | Check whether prior attempt may have completed |
| 504 Gateway Timeout | Possibly, but outcome may be unknown | Mutating POST must be reconciled |
| Connect timeout | Possibly bounded | Network/DNS/connectivity and retry budget |
| Read timeout | Possibly, must understand side effects | Do not infer target did not receive it |
| 400 Validation | Usually no | Fix schema/payload |
| 401/403 | Usually do not retry with same credentials | Check authentication/permissions |
| 404 | Depends on contract | Some eventually consistent systems |
| 409 | Depends on business logic | Conflict may mean already processed or require manual fix |
| 500 | Do not auto-retry every request | Target may have committed before failing |

### Retry-After: guidance from the target system

If the server returns **`Retry-After`** as delay seconds or an HTTP-date, the client must parse it per protocol, validate the input, and **bound it by the total deadline**.

Example:

~~~text
Response: HTTP 429
Retry-After: 10

Client budget:
  Remaining deadline is 4 seconds.
  Server suggests waiting 10 seconds.

Reasonable decision:
  Do not hold the inbound HTTP request past its deadline.
  Move message to durable delayed retry,
  or return a handleable error to caller per contract.
~~~

**Default `ExponentialBackOffPolicy` does not automatically read the HTTP `Retry-After` header.** To honor it, add logic tied to the HTTP response/error and an appropriate wait scheduling mechanism.

### POST and idempotency keys

~~~text
10:00:00  POST /orders, Idempotency-Key=order-782-v2
10:00:01  Partner records order successfully
10:00:02  Response lost
10:00:03  Client sees timeout
10:00:04  Client retries same idempotency key after backoff
10:00:05  Partner returns same already-processed order result
~~~

This is the expected behavior **if the partner implements a genuine idempotency contract**, including result caching, key TTL, and handling mismatched payloads under the same key. Without that contract, **query status or reconcile** rather than blindly resending POST.

## 14. JMS/AMQP: handler backoff differs from broker redelivery

JMS and AMQP carry built-in delivery, acknowledgement/commit, rollback/requeue, and dead-letter mechanics. Backoff can be placed at:

1. **Inside the handler:** `RetryTemplate` retries a few times with short pauses.
2. **At the listener container/broker:** message is rolled back/nacked and redelivered.
3. **Via a delayed queue/retry destination:** message is stored and redelivered after a longer delay.

All three layers can multiply attempt counts. If:

- Handler: 4 attempts;
- Broker: up to 5 deliveries;
- Manual replay: 3 additional rounds;

total handler invocations can reach **4 × 5 × 3 = 60** if every layer exhausts its turns, excluding retries inside the HTTP client. Therefore, enforce an **end-to-end retry budget** and count every round.

### JMS listener

Clarify:

- Is the session transacted?
- Do handler errors propagate to the listener/container?
- How does the container roll back and the broker redeliver?
- When is the message acknowledged?
- Is there a DLQ/poison-message policy when attempts run out?
- If the handler already made an outbound HTTP call and then JMS rolls back, will redelivery cause duplicate side effects?

**In-handler `BackOffPolicy` typically holds the processing thread.** For prolonged broker/downstream outages, favor configured container/broker redelivery or delayed processing rather than sleeping indefinitely.

### AMQP/RabbitMQ

Distinguish:

- **Immediate requeue:** can cause a hot loop and spike CPU/broker load.
- **Delayed retry:** use TTL/DLX, a delayed exchange where supported, or proper container retry mechanisms.
- **Dead-letter:** messages exhausting budget move somewhere with an owner and replay path.
- **Prefetch and concurrency:** if messages sleep in handler backoff for long periods, occupied consumer slots pile up.
- **Publisher confirms** and consumer acks are separate; successfully publishing does not prove downstream processed the message.

### Reference strategy

~~~mermaid
flowchart TD
    B["JMS/AMQP broker delivers message"] --> H["Handler with short retry"]
    H --> V{"Succeeded?"}
    V -->|"Yes"| A["Ack/commit per config"]
    V -->|"No"| R{"Attempts remaining?"}
    R -->|"Yes"| W["Bounded backoff then retry"]
    W --> H
    R -->|"No"| P{"Durable parking/DLQ?"}
    P -->|"Yes"| D["Write DLQ/delayed queue then ack source per contract"]
    P -->|"No"| E["Propagate error -> rollback/nack per policy"]
    E --> B
~~~

Do not assume **writing to a DLQ on another broker and acking the source message form an atomic transaction**. Without distributed transactions, design for deduplication and mid-step crashes.

## 15. Kafka: backoff must fit offsets and partition ordering

Kafka stores records in partitions; when a consumer fails to process a record, the system must decide **block/seek/retry, retry topics, DLT, and offset commits**.

Spring Integration Kafka adapters typically work with **Spring for Apache Kafka** components; retry mechanisms on the listener container/error handler can differ from `RequestHandlerRetryAdvice` on a handler inside an Integration Flow.

### Boundaries not to confuse

- **Handler retry:** re-runs message-handling code in the same flow.
- **Container error handler:** manages failed records/batches, seeking/backing off/recovering per configuration.
- **Retry topic:** sends records to another topic for later processing depending on architecture.
- **DLT:** destination holding records that cannot be processed in the main flow.
- **Offset commit:** consumer group progress marker on the broker, not proof that external business side effects committed.

### Why long backoff inside a consumer is dangerous

- Consumer threads can be held for long stretches.
- A failing record can block later records in the same partition.
- Batching and retries can interact awkwardly with ordering.
- Consumer group heartbeats, poll intervals, and rebalances impose operational bounds.
- A timeout after writing to a DB or calling outbound HTTP can cause duplicates when the record replays.

For retries longer than appropriate on a consumer thread, you may need **retry topics/delayed scheduling**. Moving records to a retry topic, however, can alter **processing order** among records sharing a key; decide whether the business permits that.

### Example: failed record processing

~~~text
Partition 2:
  offset 100: order-created
  offset 101: order-updated
  offset 102: order-cancelled

If offset 100 hits a transient error:
  A. In-place retry preserves order but blocks the partition.
  B. Moving offset 100 to a retry topic may let offset 101
     run ahead unless ordering guards exist.

Do not pick A vs. B on latency alone.
Define a state machine by orderId and business version.
~~~

**`BackOffPolicy` does not seek or commit offsets**, nor does it make database/HTTP processing system-wide exactly-once.

## 16. JDBC: backoff when database connections or transactions fail

Database retry must separate connection errors from errors in **transactions that already modified data**.

| Case | Handling approach |
|---|---|
| Connection pool temporarily exhausted | Bound concurrency, timeouts, backoff; analyze pool sizing |
| Brief DB failover | Bounded retry if operation is safe and connection refreshes |
| Deadlock / serialization conflict | Roll back appropriate entire transaction, open fresh transaction, then retry |
| Unique constraint violation | Usually inspect duplicate/business conflict; do not retry unconditionally |
| Syntax/schema error | Fix SQL/migration; do not retry |
| DB timeout with unclear commit | Query by business key, reconcile outcome |
| `rollback-only` transaction | Do not repeat operations inside an uncommittable transaction |

### Common mistake

~~~text
@Transactional
processOrder():
    HTTP POST creates order successfully
    DB UPDATE hits deadlock

Retry entire processOrder():
    HTTP POST is sent again
    DB UPDATE succeeds

Result without idempotency:
    Partner may end up with two orders.
~~~

Better design direction:

- Retry the **database transaction unit** separately when it can roll back and reopen cleanly.
- Partner calls must have an **idempotency key**, status lookup, or durable state machine.
- Use **transactional outbox** to persist message-sending intent alongside data changes.
- Consumers/updaters use stable event IDs and proper unique constraints.
- Backoff for deadlocks should usually be short with jitter so two transactions do not keep colliding.

### JDBC inbound polling

If a poller reads `NEW` rows and marks them `PROCESSING`, handler failures need a mechanism to transition to `RETRY_WAIT`, set `nextAttemptAt`, or let leases expire. **In-memory `RetryTemplate` does not preserve attempt counts across application restarts.**

~~~text
NEW -> CLAIMED -> PROCESSING -> DONE
                    |
                    +-> RETRY_WAIT -> PROCESSING
                    |
                    +-> PARKED (requires human handling)
~~~

You need atomic claims/transactions, worker identity, leases, timeouts, **restart-durable max attempts**, and idempotency at side effects.

## 17. When should you switch to durable delayed retry?

**Standard `BackOffPolicy` in `RetryTemplate` coordinates pauses for a retry sequence running in-process.** It is not a durable job scheduler and does not preserve pending attempts across crashes.

Use **short in-process retry** when:

- Errors can recover within a few hundred milliseconds to a few seconds.
- Attempt counts are small and timeouts are tight.
- Threads/concurrency comfortably handle expected load.
- The operation is safe to repeat.
- The caller or message handler still has sufficient deadline remaining.

Use **durable delayed retry** when:

- The partner may be down for minutes or hours.
- `Retry-After` requires waiting longer than the request deadline.
- Thousands of messages are waiting and should not tie up threads.
- Pending work must survive process restarts or redeployments.
- Operators need to inspect, pause, replay, and manage message age.
- Business expiration rules differ from connection hold times.

### Comparison

| Aspect | `RetryTemplate` + `BackOffPolicy` | Durable delayed retry |
|---|---|---|
| Retry state | In-process/call stack | Queue/topic/job store/DB |
| Suitable duration | Typically short | Can be long |
| Holds worker thread while waiting | Usually yes | Not necessarily |
| Survives restart | Not automatically | Yes with proper storage/transactions |
| Per-attempt observability | `RetryListener`/metrics | Job/queue status and events |
| Preserves message ordering | Depends on handler/container | Must be explicitly designed |
| Lifecycle attempt count | In-memory context | Attempt count persisted durably |
| Terminal state | Exception or `RecoveryCallback` | DLQ/`PARKED` + owner/retention |
| Fits high load + long target outage | Usually limited | Usually better when controlled |

### Example state for delayed retry

~~~json
{
  "eventId": "invoice-sync-882-v4",
  "targetSystem": "partner-erp",
  "operation": "invoice.upsert",
  "state": "RETRY_WAIT",
  "attemptCountPersisted": 6,
  "nextAttemptAt": "2026-11-23T09:30:00Z",
  "deadlineAt": "2026-11-24T00:00:00Z",
  "lastErrorCategory": "REMOTE_SERVICE_UNAVAILABLE",
  "payloadRef": "secured-store/item-882",
  "idempotencyKeyRef": "invoice-sync-882-v4",
  "correlationId": "corr-77ab"
}
~~~

This is an illustrative schema, not a built-in Spring Integration message type. Never store access tokens, private keys, or raw sensitive data in retry records.

## 18. Combining timeouts, rate limiters, circuit breakers, and bulkheads

Backoff is **one of several reliability controls**.

| Control | Question addressed | Relation to backoff |
|---|---|---|
| **Connection/read timeout** | How long may one attempt wait? | Without timeouts, total retry time cannot be bounded |
| **Total deadline** | How long is the entire operation still meaningful? | Stop retrying if backoff would exceed deadline |
| **Rate limiter** | How many requests/sec may be sent? | Prevents quota breaches and retry bursts |
| **Circuit breaker** | Target is failing en masse—should we keep calling? | When open, typically halts new attempts |
| **Bulkhead/concurrency limit** | How many workers may one dependency tie up? | Stops one down partner from exhausting all threads |
| **Backpressure** | Is upstream pushing faster than downstream handles? | Requires queue bounds and flow control |
| **Idempotency** | Does repeating an operation duplicate side effects? | Independent safety requirement |
| **DLQ/parking** | When retries run out, are messages kept for triage/replay? | Consequence after exhaustion |
| **Transaction/outbox** | Are business data and events preserved consistently? | Prevents loss/duplication on rollback/crash |

### When a circuit breaker is open

If every request to a down dependency still runs 4 attempts, system load multiplies severalfold. A circuit breaker fails fast on new requests while open per policy. In half-open state, only limited probe requests should pass through.

**The composition order of circuit breaker, `RetryAdvice`, rate limiter, and transaction advice directly determines actual call counts.** Measure with tests; never assume different orderings behave identically.

### Backoff can exhaust threads

Suppose a handler has 20 worker threads. The partner fails, and each message holds a thread for 10 seconds across attempt timeouts and backoff. Meanwhile, if the incoming rate exceeds current throughput, backlog builds up.

Do not merely tweak `maxInterval`; you also need to:

- Reduce synchronous-layer attempts.
- Cap concurrency toward the partner.
- Use delayed retry for prolonged outages.
- Monitor queue depth, oldest-message age, and retrying threads.
- Bound in-flight messages or apply backpressure.
- Ensure bounded memory and explicit terminal states.

## 19. Retry storms and attempt multiplication across layers

Consider an originating request:

~~~text
HTTP Client:
   retries up to 3 attempts
      -> API Gateway:
          retries up to 4 attempts
             -> Spring Integration HTTP handler:
                 retries up to 5 attempts
~~~

In the worst case, the partner API can receive **3 × 4 × 5 = 60 calls** for a single business operation if each layer exhausts its attempts without additional caps.

If the operation is a non-idempotent POST, the consequences can be severe. Even for safe GETs, 60 calls can prevent an overloaded target from recovering.

### Rules for end-to-end budget design

1. Clearly designate the **retry owner** per error type and boundary.
2. Avoid overlapping retries across HTTP client, proxy, gateway, advice, and broker.
3. Sum **approximate max attempts** across layers that can nest.
4. Set a total deadline matching the business contract.
5. Use a **shared idempotency key across all repetitions**.
6. Base circuit breakers/rate limits on **actual target load**, not just per-instance views.
7. Add jitter whenever multiple instances may fail simultaneously.
8. Beyond a short budget, switch to durable retry if the processing contract remains active.

### Distinguishing retry counts at each layer

If a metric on `RequestHandlerRetryAdvice` reports three retries, that does not prove the broker delivered the message only once. Log/track separately:

- **Handler attempts**;
- **Container deliveries/redeliveries**;
- **Durable redrives**;
- **HTTP client-level attempts**;
- **Completed business events**.

**One order should only be counted once in business metrics**, regardless of how many technical attempts it took.

## 20. Error channels, RecoveryCallback, and safe stopping points

Once `RetryPolicy` is exhausted, choose a **terminal outcome**:

- Propagate the exception so the caller or listener container handles rollback/nack.
- Write to durable DLQ/parking.
- Persist a delayed retry job with `nextAttemptAt`.
- Move invalid payloads to quarantine.
- Return a fallback only when the **business contract** allows it.
- Alert and open an incident for prolonged disconnects or credential failures.

### Recovery paths must not drop messages

An anti-pattern:

~~~text
RecoveryCallback:
    logger.error("Retried many times")
    return null

Caller/consumer:
    handler completes normally
    container may ack/commit

Result:
    Message was never processed
    yet source thinks it is done.
~~~

**A `RecoveryCallback` returning normally does not automatically mean the message was safely persisted.** If saving to DLQ/parking before ack, verify the save **succeeded durably**. If saving fails, propagate the exception or execute the designed rollback/ack path.

### Example RecoveryCallback that intentionally rethrows

~~~java
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.support.RetryTemplate;

RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
advice.setRetryTemplate(retryTemplate);

advice.setRecoveryCallback(context -> {
    Throwable last = context.getLastThrowable();

    // Do not treat failure as success; caller/container must handle terminal failure.
    throw new IllegalStateException(
            "Outbound handler exhausted retry attempts", last);
});
~~~

This example intentionally omits DLQ writing because proper DLQ persistence depends on **source type, transaction/ack model, channel, and broker**. In production, classify terminal failures and attach correlation IDs for support investigation.

### ErrorChannel is not automatically a durable queue

**`ErrorChannel`** in Spring Integration is a configured route for error messages. If it is an in-memory channel, it cannot be treated as durable storage. When recovery must survive restarts, use a controlled message store, broker DLQ, or database parking table.

## 21. Idempotency and "processed but response never received" failures

Backoff spaces calls farther apart, but **it does not eliminate duplicate side-effect risks**. The most dangerous incident is **unknown outcome**.

### Layers to separate

1. **Message redelivered:** the same event appears again.
2. **Handler re-invoked:** the same business event gets another attempt.
3. **Destination reprocesses:** may create a second side effect.
4. **Confirmed business effect:** must be idempotent within the chosen scope.

For example, an `order.updated` event is retried from a broker after a timeout. If each send generates a fresh order code for the partner, the partner creates multiple records. You must use a **stable business event ID** or contract-defined idempotency key.

### Inbox/outbox

- **Inbox/dedupe:** receiver stores processed event IDs and outcomes, using unique constraints/transactions where appropriate.
- **Transactional outbox:** persists business updates and send intent in one database transaction; worker may republish, and consumers must be idempotent.
- **Stateful workflow:** separates `OUTBOUND_PENDING`, `OUTCOME_UNKNOWN`, `CONFIRMED`, `PARKED` steps so the whole flow is never blindly repeated.
- **Reconciliation:** asks the target whether the previous request succeeded when the response was lost.

### Example of proper boundaries

~~~text
SFTP file containing eventId=inv-882-v4
    -> parse, validate
    -> inbox records RECEIVED
    -> HTTP upsert with same idempotency key
       -> if timeout: QUERY status
       -> if transient error: retry with backoff
       -> if exhausted: PARKED
    -> confirm ERP_CONFIRMED
    -> DB transaction saves DONE + outbox notification
    -> AMQP publisher sends outbox event
    -> partner receives and deduplicates
~~~

**Never place this entire sequence inside a single `RetryCallback`** because an error at the final step can re-run the earlier HTTP step and cause unintended effects.

## 22. Connection lifecycle: reconnect, failover, and resource cleanup

When connections fail, beyond retry/backoff, inspect the **connection and session lifecycle**.

### States to watch

- Connection could not open.
- Connection opened but authentication failed.
- Connection was used but closed by the remote side.
- Connection pool handed out a stale session.
- Remote call succeeded but response was lost.
- Connection was aborted during backoff.
- Service was redeployed while messages were waiting to retry.

### Guarantees to enforce

1. **Do not reuse broken sessions/connections** when the client/pool requires invalidation.
2. Close/return resources cleanly on error and cancellation.
3. Check credential rotation, TLS/SSH host keys, and auth failures; never weaken security "just to reconnect."
4. Avoid opening excessive new connections during a retry burst.
5. Ensure backoff can stop cleanly on application shutdown or job cancellation; handle interruption per library contract.
6. When a remote service changes IPs/endpoints on failover, align retry policies with DNS/caching and client connection pooling.
7. After reconnecting, check **business state** rather than assuming the remote did not process the previous request.

### Interruption and shutdown

In Java, a worker sleeping in backoff can be **interrupted** during shutdown. If the policy uses `Sleeper`/thread sleep, interruption may surface as a backoff/interruption exception depending on the API. Never catch all exceptions and keep retrying regardless of shutdown. Propagate cancellation, release resources, and preserve unfinished messages via the source/parking per design.

## 23. Observability: logging enough to understand backoff and final outcomes

Observe **message reliability**, not just exception counts.

### Recommended log fields

| Field | Meaning |
|---|---|
| `eventId`/`businessKey` | Stable identifier across retries, broker redeliveries, restarts |
| `correlationId`/`traceId` | Links inbound, outbound, retry, and recovery |
| `adapter`/`flow`/`endpointId` | Identifies which point is retrying |
| `targetSystem` | Safe name for SFTP host alias, HTTP partner, broker, topic, or DB |
| `attemptIndex`/`maxAttempts` | Accurately counts invocations |
| `errorCategory`/`exceptionType` | Classifies transient, permanent, unknown |
| `scheduledDelayMs`/`actualDelayMs` | Distinguishes policy target from actual elapsed delay |
| `elapsedMs`/`deadlineRemainingMs` | Detects latency budget overruns |
| `policyType`/`policyVersion` | Fixed/exponential/jitter and configuration |
| `finalOutcome` | `SUCCESS`, `EXHAUSTED`, `PARKED`, `DLQ`, `CANCELLED` |
| `sourceAck`/`commitOutcome` | Whether source message/offset was confirmed |
| `idempotencyKeyRef` | Links attempts to one business action without exposing secrets |

**Never log raw sensitive payloads, access tokens, passwords, SFTP private keys, or security headers.** For metrics, never put `eventId`/`transactionId` in labels to avoid **high-cardinality** explosions.

### Suggested metric set

| Metric | Measurement | Purpose |
|---|---|---|
| **`retry_attempts_total`** | Handler attempts by endpoint/error category | Detects dependency failure rates |
| **`retry_success_after_failure_total`** | Sequences succeeding after at least one retry | Measures benefit of retries |
| **`retry_exhausted_total`** | Retry sequences exhausting budget | Tracks recovery load |
| **`backoff_requested_seconds`** | Distribution of delays requested by policy | Validates delay configuration |
| **`backoff_actual_seconds`** | Observed actual wait times | Spots scheduling/runtime issues |
| **`handler_latency_seconds`** | Total latency including attempts/backoff, P50/P95/P99 | Evaluates SLA impact |
| **`source_redelivery_total`** | Messages redelivered by broker/file/job | Separates redelivery from in-process retries |
| **`delayed_retry_backlog`** | Messages waiting in durable retry schedule | Measures scale of prolonged outages |
| **`dlq_or_parked_age_seconds`** | Age of halted messages | Surfaces neglected critical tasks |
| **`duplicate_business_effect_total`** | Confirmed duplicate business effects | Verifies retry safety |
| **`circuit_breaker_open_count`** | Times a dependency tripped breaker open | Identifies widespread outages |
| **`pool_waiting_threads`** | Threads held/waiting in integration pools | Prevents backoff-induced starvation |
| **`reconnect_failures_total`** | Connection/session setup failures per adapter | Pinpoints network/client faults |

**Rising retry attempts are neither inherently good nor bad.** They often signal target instability; interpret them alongside request volume, success rate, latency, and duplicate effects.

## 24. Designing reliable BackOffPolicy tests

Tests should not merely assert "eventually succeeded." Verify **attempt counts, stop conditions, wait intervals, and side effects**.

### Unit test for fixed backoff

~~~java
import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.retry.backoff.FixedBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

// Illustrative snippet inside a test method.
RetryTemplate template = new RetryTemplate();

SimpleRetryPolicy policy = new SimpleRetryPolicy(3);
FixedBackOffPolicy backOff = new FixedBackOffPolicy();
backOff.setBackOffPeriod(1L); // 1 ms so tests do not wait long.

template.setRetryPolicy(policy);
template.setBackOffPolicy(backOff);

AtomicInteger calls = new AtomicInteger();

String result = template.execute(ctx -> {
    if (calls.incrementAndGet() < 3) {
        throw new IOException("Temporary connection issue");
    }
    return "OK";
});

// Expected assertions:
// result.equals("OK")
// calls.get() == 3
// 2 pauses between attempts.
~~~

This example verifies attempts; when you need to assert **exact wait intervals or exponential sequences**, use a **`Sleeper`/test double or clock/scheduler abstraction** suited to your Spring Retry version to record delays without depending on wall-clock time (which is flaky). Never run real integration tests with multi-minute delays just to count a backoff series.

### Test matrix

| ID | Scenario | Expected outcome |
|---|---|---|
| B1 | Succeeds on first attempt | One invocation, no backoff |
| B2 | Two transient errors then success | Three attempts, two pauses |
| B3 | Always fails with maxAttempts=4 | Four attempts, three pauses, enters recovery |
| B4 | `ValidationException` or HTTP 400 | No retry, no backoff |
| B5 | HTTP 401/403 | Does not repeat requests with invalid credentials |
| B6 | HTTP 429 and valid `Retry-After` | Does not call earlier than server policy/deadline allows |
| B7 | `Retry-After` exceeds total deadline | Stops or routes to durable retry per contract |
| B8 | Exponential backoff with `maxInterval` | Intervals grow then hit ceiling |
| B9 | Multiple workers fail concurrently | Jitter/rate limit prevents over-budget bursts |
| B10 | Backoff interrupted by shutdown | Cancels cleanly, preserves unfinished messages |
| B11 | HTTP POST wrote data then timed out | Retry creates no second record when contract is idempotent |
| B12 | Repeated 503s, partner down long-term | Does not hold threads forever; moves to `PARKED`/delayed |
| B13 | `RecoveryCallback` returns normally | Acks only when message is persisted per design |
| B14 | DLQ/parking write fails | Message not lost by swallowing exception |
| B15 | SFTP disconnects mid-upload | Remote partial file detected/reconciled |
| B16 | SFTP wrong host key | Does not retry past host authentication checks |
| B17 | Inbound file still uploading | Does not parse partial file or create duplicate work |
| B18 | Poller runs alongside handler retry | Call counts and schedule progress stay predictable |
| B19 | JMS broker redelivery × handler retry | Total attempts stay within budget |
| B20 | Continuous AMQP requeue | No hot loop; routes to DLQ per policy |
| B21 | Kafka error handler backoff | Does not miscommit offsets or break contract ordering |
| B22 | JDBC deadlock | Opens fresh transaction and commits once |
| B23 | Application restarts mid-backoff | In-memory state lost; durable recovery takes over |
| B24 | Circuit breaker open | No new remote calls violating policy |
| B25 | Concurrent retries exceed pool | Backpressure/metrics/alerts engage, memory stays bounded |
| B26 | Nested retries in client and gateway | Actual total attempts measured and capped by budget |
| B27 | Misconfigured delay (0 or huge) | Validation test catches and warns on config |
| B28 | Poison message after exhaustion | Quarantined/DLQ'd with reason code and owner |

### Controlled end-to-end testing with real connection errors

1. Set up an authorized HTTP/SFTP stub or test container to simulate failures.
2. Attach stable `eventId`/`correlationId` to messages.
3. Have the stub return transient errors twice, then succeed.
4. Record call counts, timestamps, exceptions, results, and side effects.
5. Verify max attempts and wait intervals match the policy.
6. Switch the stub to "written, response lost" mode and verify deduplication/reconciliation.
7. Kill the consumer mid-backoff, restart, and verify no messages are lost.
8. Fail terminal recovery and verify the source does not wrongly ack/commit.
9. Increase test concurrency and measure queue depth and retry rate.
10. Capture evidence alongside policy configuration in the test report, not just PASS/FAIL.

## 25. Hands-on scenario: SFTP → HTTP ERP → JDBC → AMQP

### Background

An enterprise receives `invoices.csv` via SFTP, where each record represents an invoice to sync to ERP.

Spring Integration Flow:

~~~text
SFTP inbound adapter + poller
    -> staging file
    -> parser / validator
    -> MessageChannel
    -> HTTP outbound gateway -> ERP
    -> JDBC update status
    -> AMQP outbound adapter (notification)
    -> archive file
~~~

Business requirements:

- Every invoice has a unique **`invoiceId + version`**.
- Never create duplicate ERP invoices.
- Invoices with data errors must be isolated with a reason.
- Invoices sent with uncertain outcomes must be reconciled.
- When ERP is down for several minutes, do not tie up all worker threads.
- If the application restarts, pending messages must not vanish.

### Simulated timeline

| Time | Event |
|---|---|
| 08:00 | Partner is uploading `invoices.csv.part`, file not ready |
| 08:02 | Partner publishes `invoices.csv.ready` |
| 08:03 | Poller picks up file, parses; invoice A is valid, invoice B lacks customer code |
| 08:04 | ERP returns HTTP 503 on some requests |
| 08:05 | Invoice A's HTTP POST succeeds in ERP, but response times out |
| 08:06 | Multiple workers retry concurrently; ERP remains overloaded |
| 08:08 | Local database hits a deadlock updating status for A |
| 08:09 | RabbitMQ temporarily disconnects |
| 08:10 | An application instance restarts while still in backoff |
| 08:15 | Partner SFTP hits an authentication error due to rotated keys |
| 08:30 | ERP recovers and requests reduced send rates for a few minutes |

### Tasks

1. Specify exactly **which errors should be retried** and **which should not**.
2. Propose an appropriate `BackOffPolicy` for **HTTP 503**, including initial interval, multiplier, cap, jitter, and max attempts.
3. Show the formula for **maximum total duration** of the HTTP retry sequence given per-attempt timeouts.
4. Explain why **HTTP POST timeout after ERP writes** needs different handling from a connect failure.
5. Distinguish **SFTP poll schedule**, **HTTP handler backoff**, and **delayed retry after exhaustion**.
6. Design durable state to survive restarts and avoid creating two ERP invoices.
7. Explain at **which boundary** JDBC deadlocks and AMQP errors should be retried.
8. Design retry-storm prevention and recovery when ERP is down long-term.
9. Propose metrics, alerts, and at least eight test cases to verify end-to-end results.

### Solution guide

**1. Classification.** HTTP 503 is a candidate for retry with backoff; connect timeouts can retry when safe. Invoice B missing customer code is a validation error—**do not** retry the same payload. SFTP auth error from key rotation requires updating credentials via security procedures. JDBC deadlocks can usually roll back and open a new transaction. Temporary AMQP errors may need durable publishing. POST unknown outcomes must **query/reconcile** or use an idempotency key.

**2. Reference policy.** Example values: `maxAttempts=4`, `initialInterval=250 ms`, `multiplier=2`, `maxInterval=2,000 ms`, with randomization; these are **illustrative values**, not mandatory standards. Set connect/response timeouts and overall deadlines per ERP SLA; if the partner sends `Retry-After`, factor it in alongside the business budget.

**3. Timing math.** Ignoring randomization for clarity, waits across four attempts are 250, 500, 1,000 ms, totaling **1,750 ms**. With a max 1.5-second timeout per attempt, total is roughly **4 × 1.5 s + 1.75 s = 7.75 seconds**, excluding overhead. With jitter, bound calculations using the policy's **actual limits** rather than claiming an exact 7.75 seconds.

**4. Unknown outcome.** ERP may have committed invoice A before the response was lost. Resend with **`Idempotency-Key=invoiceId-version`** per ERP contract or query by business key. If no verification mechanism exists, move A to `OUTCOME_UNKNOWN` and investigate; never blindly recreate the invoice.

**5. Three distinct timings.** The poller checks SFTP on a schedule, which is not retrying the same message. `RetryTemplate` pauses briefly between ERP calls. Delayed retry persists messages and schedules processing when ERP recovers without holding threads continuously.

**6. Durable state.** Each record stores `eventId`, status (`RECEIVED`/`VALIDATED`/`ERP_PENDING`/`OUTCOME_UNKNOWN`/`ERP_CONFIRMED`/`NOTIFICATION_PENDING`/`DONE`/`PARKED`), attempt count, and `nextAttemptAt`. Use unique constraints and inbox/outbox. On restart, workers resume non-terminal states without duplicating work.

**7. Transaction boundaries.** JDBC deadlocks roll back and retry **only the database transaction**. Since the AMQP outage occurs after the DB update, write the notification event to a **transactional outbox** so a publisher delivers it when the broker returns. Do not retry from the SFTP step when only AMQP fails.

**8. During overload.** Use exponential backoff with jitter, rate limiters, concurrency caps/circuit breakers. Once in-process attempts are exhausted, move to stateful delayed retry with alerts. When ERP recovers, drain backlog smoothly rather than unleashing the entire queue at once.

**9. Metrics/tests.** Track `retry_attempts_total`, exhausted counts, actual backoff, handler latency, delayed backlog age, duplicate effects, event processing latency, outbound HTTP 503s, SFTP reconnect failures, and AMQP publish outcomes. Test invalid data, 503 then success, prolonged 503, timeout after commit, SFTP auth error, DB deadlock, AMQP outage, crash mid-backoff, DLQ failure, and concurrent retry storms.

### A target architecture

~~~mermaid
flowchart LR
    S["SFTP file ready"] --> V["Stage + validate"]
    V -->|"Invalid"| Q["Quarantine with reason code"]
    V -->|"Valid"| I["Inbox: stable eventId"]
    I --> E["ERP state machine"]
    E --> H{"What error / outcome?"}
    H -->|"Transient + safe retry"| R["Short retry: RetryTemplate + backoff"]
    H -->|"Outcome unknown"| C["Lookup / reconciliation"]
    R -->|"Success"| D["ERP_CONFIRMED"]
    C -->|"Verified"| D
    R -->|"Exhausted"| P["Durable RETRY_WAIT / PARKED"]
    P -->|"Due, not expired"| E
    D --> T["DB transaction: DONE + outbox"]
    T --> A["AMQP outbox publisher"]
    A -->|"Broker temporarily down"| W["Delayed publish + backoff"]
    W --> A
    A --> N["Notification confirmed"]
    N --> Z["Archive per policy"]
~~~

This diagram shows responsibilities only. Every delayed loop must enforce **attempt caps, message expiration, rate control, and terminal states**; never run an unbounded busy loop.

## 26. Common anti-patterns

| Anti-pattern | Why it is dangerous | Remedy |
|---|---|---|
| Retrying immediately on connection failure | Amplifies load | Bounded backoff and jitter |
| Setting backoff without `maxAttempts` | Can loop too long or forever | Explicit `RetryPolicy` |
| Setting `maxAttempts` without network timeouts | First attempt can hang | Connect/read timeouts + deadline |
| Uncapped exponential backoff | Huge delays violating SLAs | `maxInterval`/total deadline |
| Identical fixed delay across thousands of clients | Synchronized request waves | Jitter/rate limiting |
| Retrying all exceptions | Invalid data and auth errors cannot self-heal | Exception classifier |
| Retrying HTTP POST on unknown outcome | Creates duplicate side effects | Idempotency/outcome lookup |
| Using `RetryTemplate` as a durable job scheduler | Retry state lost on restart | Delayed queue/job store |
| Wrapping the whole flow in advice | Repeats earlier succeeded operations | Retry only the target handler/operation |
| Forgetting broker redelivery | Total attempts grow out of control | End-to-end retry budget |
| Swallowing exceptions in `RecoveryCallback` | Source may ack before message is safe | Confirmed DLQ/parking or rethrow |
| Confusing poller with retry | Re-poll does not guarantee re-reading the same message | Separate message state/replay |
| Long backoff inside Kafka consumers | Blocks partitions and risks rebalances | Proper error handler/retry topics |
| Retrying JDBC in a `rollback-only` transaction | Transaction cannot commit | Open fresh transaction at proper scope |
| Resending SFTP uploads without checking remote state | Duplicate or partial files | Temp file + checksum/reconcile |
| Reconnecting by disabling SSH host-key checks | Exposes system to spoofing | Protect trust/keys and fix credentials |
| Logging tokens/secrets on every attempt | Information disclosure risk | Minimal structured logging |
| Not measuring threads in backoff | System stalls mysteriously | Pool metrics, bulkheads, backpressure |
| DLQ with no owner/retention | Poison messages forgotten | Alerts, triage, controlled redrive |
| Retrying without business expiration | Keeps running obsolete actions | Deadlines and `CANCELLED` state |

## 27. Implementation checklist

- [ ] Identified all inbound/outbound adapters, gateways, pollers, channels, and handlers in the flow.
- [ ] Know exactly **which points are allowed to retry** and which retry automatically via broker/client libraries.
- [ ] `RetryPolicy` selects errors by transient/permanent/unknown and operation idempotency.
- [ ] `maxAttempts` **includes the initial attempt**; no unbounded retries.
- [ ] `BackOffPolicy` chooses fixed/exponential/jitter matched to load and partner traits.
- [ ] Configured `initialInterval`, `multiplier`, `maxInterval`, and validated settings.
- [ ] Set connection/read timeouts, total deadlines, and end-to-end retry budgets.
- [ ] HTTP 429/503 considers `Retry-After`, rate limits, and circuit breakers.
- [ ] Avoided simultaneous client/gateway/advice/broker retries without summing attempts.
- [ ] `RequestHandlerRetryAdvice` wraps only the handler that needs retry.
- [ ] Poller schedules are not mistaken for guaranteed same-message retries.
- [ ] File/SFTP defines publish-completion rules, transfer state, metadata, and replay.
- [ ] HTTP POST/upserts have idempotency keys or outcome reconciliation.
- [ ] JMS/AMQP broker redelivery, ack/nack/rollback, and DLQ match requirements.
- [ ] Kafka consumer offsets, ordering, error handler, and DLT match business rules.
- [ ] JDBC retries align with transaction boundaries, avoiding `rollback-only` traps.
- [ ] Short retries are in-memory; long delayed retries persist durably across restarts.
- [ ] `RecoveryCallback` does not swallow errors before messages are safely persisted.
- [ ] `PARKED`/DLQ states have retention, owners, alerts, and controlled redrive.
- [ ] Logs include event ID, correlation ID, attempts, delay, error category, and terminal outcome.
- [ ] Credentials, private keys, tokens, and raw customer data are excluded from logs.
- [ ] Track retry attempts, exhaustion, actual delays, backlog age, pool saturation, and duplicate effects.
- [ ] Tested error classification, HTTP unknown outcomes, SFTP partial transfers, Kafka/JMS/AMQP redelivery, JDBC deadlocks, restarts, and recovery failures.
- [ ] Runbooks exist for prolonged partner outages, retry storms, credential errors, and SLA-breaching backlogs.

## 28. Key terms to remember

| Term | Meaning |
|---|---|
| **BackOffPolicy** | Defines the wait strategy before the next attempt in a retry sequence |
| **RetryPolicy** | Decides whether retrying can continue based on count, exception, or conditions |
| **RetryTemplate** | Coordinates `RetryCallback`, `RetryPolicy`, `BackOffPolicy`, and recovery |
| **BackOffContext** | State of a backoff session, e.g., current exponential interval |
| **RetryContext** | State of an active retry sequence |
| **FixedBackOffPolicy** | Constant wait interval |
| **ExponentialBackOffPolicy** | Wait interval growing by a multiplier up to a ceiling |
| **ExponentialRandomBackOffPolicy** | Exponential strategy with library-defined randomization |
| **Jitter** | Randomizing retry timing to prevent clients from bunching requests |
| **Retry storm / thundering herd** | Many clients retrying in sync, overwhelming the target |
| **Retry budget** | Cap on attempts/load/time spent retrying across the processing path |
| **RequestHandlerRetryAdvice** | Spring Integration advice wrapping a message handler with retry |
| **Poller** | Component fetching messages on a schedule from a `MessageSource` |
| **Redelivery** | Source/broker re-delivering a message due to failure or missing ack |
| **DLQ / DLT** | Dead-letter queue/topic holding failed messages for separate handling |
| **Delayed retry** | Retries scheduled via storage/queues without necessarily holding threads |
| **Idempotency key** | Stable key identifying the same business request across retries |
| **Outcome unknown** | Uncertainty about whether the previous call took effect at the destination |
| **Transactional outbox/inbox** | Patterns persisting send intent and/or deduplicating receipts with transactions |
| **Circuit breaker** | Stops calling a dependency when failures spread according to policy |
| **Bulkhead** | Limits resources for a dependency group so faults do not spill into other flows |

## 29. References and self-assessment questions

### References

- **Spring Retry Reference:** `RetryTemplate`, `RetryPolicy`, `BackOffPolicy`, `RetryContext`/`BackOffContext`, `RetryListener`, and recovery.
- **Spring Integration Reference — Message Handler Advice:** `RequestHandlerRetryAdvice` and advice chains on endpoints.
- **Spring Integration Reference — Polling Consumer, Message Channels, Error Handling:** poll schedules, sync/async boundaries, and error channels.
- **Spring Integration Reference — File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC Adapters:** source/target semantics, filters, transactions, and message lifecycles.
- **Spring AMQP and Spring for Apache Kafka Reference:** listener retry, nack/requeue, DLQ/DLT, consumer errors, and offset management.
- **Spring Framework Transaction Management:** transaction propagation/rollback and retry boundaries relative to commits.
- **Enterprise Integration Patterns:** Idempotent Receiver, Dead Letter Channel, Transactional Client, Guaranteed Delivery, Message Store, and Retry.

### Self-assessment questions

1. For a `RetryPolicy` with `maxAttempts = 5` and non-jittered exponential backoff, what is the maximum number of pauses?
2. Why can an HTTP read timeout after a payment-creating POST be more dangerous than a connect timeout before sending the request?
3. When is `FixedBackOffPolicy` better than `ExponentialRandomBackOffPolicy`, and vice versa?
4. If 100 consumers retry simultaneously after a 503, what does jitter help with and what does it **not** help with?
5. Why does `RequestHandlerRetryAdvice` on an HTTP gateway not guarantee the SFTP poller will pick up the file again?
6. When both the JMS broker redelivery and the handler retry, how do you calculate maximum attempts?
7. Why can keeping a Kafka consumer sleeping in backoff for a long time increase lag?
8. If a JDBC transaction is already `rollback-only`, how must the retry boundary change?
9. When `RecoveryCallback` returns normally, why must ack/commit behavior be reviewed?
10. If ERP returns `Retry-After: 30` seconds while the HTTP inbound deadline only has 3 seconds left, what should the architecture do?

### Short answers

1. **At most 4 pauses**, because the initial attempt has no wait before it.
2. The target may have processed the request while the response was lost, so retrying risks creating duplicate side effects.
3. Fixed suits low load or faults with predictable recovery times; randomized exponential suits multiple clients and spreading overload failures.
4. Jitter spreads call timestamps out, but does not remove the need for idempotency, max attempts, rate limits, and deadlines.
5. Advice only wraps the specified handler; source polling and metadata have independent lifecycles.
6. Multiply **handler attempts per delivery × deliveries × redrives** plus any other retry layers.
7. Consumer slots/partitions stay tied up, delaying processing and interacting with poll limits and rebalances.
8. Roll back and open a **new transaction** for the appropriate attempt, avoiding repeating prior side effects.
9. The caller/container may treat the handler as succeeded and ack even if the message never entered recovery storage.
10. Return an error per contract or hand off to **durable delayed retry**—never hold the inbound request past its deadline.

**Key takeaway:** **`BackOffPolicy` does not decide whether to retry**; it controls **timing** for retries already allowed by `RetryPolicy`. In Spring Integration Adapters, backoff delivers real reliability only when placed at the **right handler boundary**, paired with timeouts, retry budgets, idempotency, transactions/acks, error handling, and durable recovery. The ultimate goal is not "retry as much as possible," but **recovering from transient faults without amplifying overload, losing messages, or duplicating business effects**.
