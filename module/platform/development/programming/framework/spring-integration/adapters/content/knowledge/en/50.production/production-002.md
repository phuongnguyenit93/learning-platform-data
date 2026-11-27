# Timeouts for All Remote Connections in Spring Integration Adapters

> **Chapter:** Production  
> **Topic:** Timeouts for all remote connections  
> **Module:** Spring Integration Adapters  
> **Scope:** Inbound/outbound adapters, gateways, pollers, and MessageChannel when exchanging data via File, SFTP, HTTP, JMS, AMQP, Kafka, JDBC, and external services.

## 1. Objectives and Production Problem

After this lesson, you will be able to:

1. Distinguish **connection timeout, pool acquisition timeout, TLS/SSH handshake timeout, read/write timeout, response/reply timeout, acknowledgement timeout, transaction timeout**, and **whole-flow deadline**.
2. Locate the exact layer where each timeout must be set in a Spring Integration flow: adapter, client library, broker, database driver, gateway, poller, or scheduler.
3. Design a **time budget** for an integration transaction that aligns with the sender's SLA and the receiver's retry/backoff policy.
4. Configure timeouts per technology—HTTP, SFTP, JMS, AMQP, Kafka, JDBC—and understand why local File has no remote connection timeout.
5. Prevent message loss and duplicate side effects when an operation times out after the external system has already completed processing.
6. Monitor timeouts by stage, test network faults, backpressure, and rolling deployments, and make evidence-based go/no-go decisions.
7. Build runbooks for hung connections, exhausted pools, timeout storms, and downstream outages.

**Context:** A Spring Boot application uses Spring Integration to receive files via SFTP, write to a DB, call partner HTTP APIs, publish Kafka events, and still runs JMS/AMQP consumers. When SFTP stops responding, workers can hang for minutes. When an HTTP client times out, the partner may have already created the transaction. When the DB pool is exhausted, requests wait for connections longer than the SLA. Therefore, configuring a single property named **timeout** is insufficient: you must control every waiting stage and understand the effects of cancellation or retries.

## 2. What Boundary Is a Timeout?

A **timeout** is a time limit on a defined stage or waiting state. It does not mean "cancel all processing on the other side", nor is it automatically an **end-to-end deadline**.

| Timeout Type | What Is Waiting? | When It Expires | Common Configuration Point |
|---|---|---|---|
| **DNS / name resolution** | Hostname lookup | No address to connect to | Resolver/OS/client, sometimes hard to set separately |
| **Connection establishment** | TCP socket setup | Cannot connect within allowed window | HTTP/SFTP/broker client, JDBC driver |
| **TLS/SSH handshake** | Security session negotiation and peer auth | Cannot establish secure channel | Client/transport, SSH/SFTP session |
| **Connection acquisition** | Waiting to borrow a connection from pool | Pool overloaded; request not yet sent | HTTP connection manager, JDBC pool |
| **Socket read / inactivity** | Waiting to read data, often time between new bytes | Data did not arrive in time | Socket/client/driver |
| **Write / send** | Waiting to write bytes or send request/broker record | Unclear how much the receiver got | Client or API with write limits |
| **Response / request** | Waiting for a response to a request | Caller gives up waiting for reply | HTTP gateway, request/reply messaging |
| **Message channel send** | Waiting to hand message to channel/buffer | Could not hand off before deadline | Spring Integration channel/gateway |
| **Poll / receive** | Waiting to fetch message/file/record from source | May simply mean no data is available | Poller, JMS receive, Kafka poll |
| **Ack / commit** | Waiting for broker ack, offset, or transaction | Delivery state may be ambiguous | JMS/AMQP/Kafka/DB |
| **Transaction / query / lock** | Waiting on query, lock, or transaction | Rollback/exception per engine support | JDBC/DB/transaction manager |
| **Idle / lease / keepalive** | Closing idle connections or keeping session alive | Connection lifecycle management | HTTP pool, broker, DB pool |
| **Whole-flow deadline** | Entire workflow from intake to contract completion | SLA violated even if no single leg timed out | Application logic, workflow, and monitoring |

### 2.1. Common Misconceptions

- **Connect timeout** does not replace **read timeout**: a socket can connect while the server never sends a response and still block for a long time.
- **Read timeout** in many clients measures the gap between incoming data packets, not total download duration. A server trickling a few bytes steadily can stretch total duration without an overall deadline.
- **Pool acquisition timeout** differs from connect timeout: you haven't even obtained a connection to start connecting yet.
- **Gateway reply timeout** does not necessarily abort low-level HTTP sockets, broker clients, or database queries.
- **Poll interval** does not cap how long a single poll takes when SFTP/DB hangs.
- **Heartbeat/keepalive** detects or limits idle connections; it is not a per-business-operation deadline.
- **Thread interruption / Future timeout** does not guarantee the remote side canceled its side effects.
- **An API returning a timeout** does not tell you whether the server already processed the request.

**Core takeaway:** Timeouts must be placed on the **exact stage that can block**, while flow-level deadlines must be based on total elapsed time and business outcomes.

### 2.2. Diagram of Waiting Points

~~~mermaid
flowchart LR
    A["Inbound request / message"] --> Q["Channel queue / executor"]
    Q --> P["Pool acquisition"]
    P --> C["DNS + TCP connect"]
    C --> H["TLS / SSH handshake"]
    H --> W["Write request"]
    W --> R["Read response"]
    R --> D["DB transaction"]
    D --> O["Ack / outbound event"]
    A -. "Whole-flow deadline" .-> O
    C -. "Connect timeout" .-> FAIL["Retry / error path"]
    H -. "Handshake timeout" .-> FAIL
    R -. "Read/response timeout" .-> FAIL
    P -. "Pool wait timeout" .-> FAIL
    D -. "Query/transaction timeout" .-> FAIL
    O -. "Ack timeout" .-> FAIL
~~~

Not every stage appears in every adapter. File inbound typically opens no remote socket, whereas HTTP outbound requires DNS/connect/TLS/write/read; a Kafka producer also has internal queues, metadata waits, and broker acknowledgements.

## 3. Deriving a Time Budget from the End-to-End Flow SLA

A system with many disconnected timeouts can still breach its SLA. Therefore, start from business objectives:

- How long can an HTTP caller afford to wait at most?
- By when must an SFTP file be processed?
- How long can Kafka/JMS messages sit in backlog?
- After a transient DB error, does the system retry synchronously within the request or hand off asynchronously?
- How long may a thread, connection, or transaction be held?

### 3.1. Illustrative Budget

Suppose an outbound HTTP gateway sits inside a request with a **25-second** deadline. The design estimates:

| Line Item | Planned Budget |
|---|---:|
| Pre-processing queue/handoff | 2 seconds |
| Validate/transform | 1 second |
| Partner HTTP call: 2 attempts, each connect ≤ 2 s + response ≤ 4 s | 12 seconds |
| Backoff between attempts | 1 second |
| DB transaction and result persistence | 4 seconds |
| Buffer for orchestration/serialization/network variance | 4 seconds |
| **Approximate total budget** | **24 seconds** |

These numbers are **examples only**, not an optimal configuration. You must align semantics: does response timeout include connect or only reading the response, is TLS handshake covered, can DNS take extra time, and is pool acquisition inside the total? When stages exceed the budget, reduce attempts, tighten step budgets, decouple asynchronously, or renegotiate the SLA explicitly.

A **conservative estimation** formula when stages do not overlap:

\[
T_{\mathrm{flow}} \lesssim T_{\mathrm{queue}} + T_{\mathrm{validation}} + \sum_{i=1}^{N} \left(T_{\mathrm{pool},i} + T_{\mathrm{connect},i} + T_{\mathrm{request},i}\right) + \sum_{i=1}^{N-1} T_{\mathrm{backoff},i} + T_{\mathrm{DB}} + T_{\mathrm{reserve}}.
\]

This formula is for **budget planning**, not a guarantee of actual execution time: DNS, TLS, machine load, client timer granularity, and cleanup time may differ from simple summation. Some timeouts enclose others rather than adding independently.

### 3.2. Deadlines Must Propagate Remaining Time

For example, a gateway receives a request at 10:00:00 with a deadline of 10:00:25. After 6 seconds in queue + validation, it must not call the partner with another fixed 25-second client timeout. The flow must check the **remaining budget** at each step.

~~~text
deadline = requestStart + totalAllowedDuration

beforeEachRemoteOperation:
    remaining = deadline - monotonicElapsedSinceStart
    if remaining <= minimumUsefulTime:
        failWithDeadlineExceeded()
    else:
        operationBudget = min(configuredPerAttemptTimeout, remaining - reserve)
        executeWithAppropriateClientTimeouts(operationBudget)
~~~

This is pseudocode. In a real system, use a monotonic clock to measure **duration** so system clock adjustments do not interfere, while recording wall-clock timestamps for audit logs. Not all Spring Integration APIs support passing dynamic deadlines directly to every client; you may need a wrapper/custom gateway or separate execution paths.

### 3.3. Synchronous or Asynchronous?

If the inbound HTTP SLA is 10 seconds while a partner SFTP/HTTP call can take 30 seconds, do not hold the request open with a 60-second timeout and hope for the best. Use an **accept + tracking ID** contract for asynchronous processing, persist the request durably, deliver results on completion, and provide a status query or callback channel.

Moving to async does not remove message reliability obligations: you still need deduplication, durable queues/outboxes, retries, auditing, and backlog limits.

## 4. Building a Timeout Matrix Per Connection

Instead of writing a generic "timeout = 30 s", build a matrix grounded in the application's actual execution paths.

| Endpoint/Operation | Timeouts to Review | Configuration Owner | Failure Mode to Test |
|---|---|---|---|
| SFTP inbound download | Connect, SSH handshake, session/operation, read stall, poll execution | Spring Integration SFTP + SSH client | Server stops responding mid-transfer |
| SFTP outbound upload | Connect, remote write, rename/ack, session | SFTP client + application | Upload may succeed before timeout fires |
| HTTP outbound gateway | Pool wait, connect, TLS, response/read, overall request | HTTP client/request factory | Server finishes processing but client times out |
| HTTP inbound gateway | Proxy timeout, servlet thread, integration reply timeout | Web server/proxy + gateway | Client disconnects while handler keeps running |
| JMS request/reply | Connection/receive/reply timeout, broker failover | JMS provider + gateway | Late reply; request was already processed |
| JMS listener | Broker/session/reconnect, receive wait, transaction/ack | JMS listener container/provider | Listener stuck or redelivery loop |
| AMQP RPC / publish | Connect, handshake, RPC reply, publisher confirm, heartbeat | Rabbit client + adapter | Confirm timeout, ambiguous publish |
| Kafka producer | Metadata wait, max block, request, delivery, future wait | Kafka client + integration endpoint | Producer times out before broker ack |
| Kafka consumer | Poll wait, API request, heartbeat/session, max poll interval | Kafka client/listener | Consumer rebalance or stuck processing |
| JDBC inbound/outbound | Pool wait, socket connect/read, query, lock, transaction | DataSource/driver/DB | DB pool exhausted or lock wait |
| Local File | No default remote socket; poll cadence, file-ready wait, I/O, and filesystem | File adapter + host/filesystem | File not ready yet or hung NFS/SMB mount |

**Note:** Real APIs may not expose timeouts for every row. Where a client lacks a hard bound, apply compensating controls: isolation, watchdogs, verified worker cancellation, task-level deadlines, circuit breakers, or pause/recovery mechanisms.

## 5. Combining Timeouts with Retries, Circuit Breakers, and Backpressure

### 5.1. Retries Can Exceed the Total Budget

Suppose each attempt has a 5 s connect and 10 s read timeout, 4 retry attempts, and backoffs of 2 s, 4 s, 8 s. Worst-case duration can exceed **74 seconds**, not counting DNS, queues, TLS, DB, or cleanup. An inbound request with a 30 s proxy timeout will drop while the backend is still working.

Checklist:

- [ ] Designate one layer as the **primary retry owner** for each operation.
- [ ] Ensure total attempts + backoff + per-attempt timeouts + reserve fit within the deadline.
- [ ] Never infinitely retry permanent errors like invalid schema, 401/403, or host key mismatch.
- [ ] Apply bounded exponential backoff and jitter for 429/503/network errors when appropriate.
- [ ] Reduce remaining attempts if the remaining budget is insufficient.
- [ ] Use a retry queue/durable handoff if time is insufficient within a synchronous request.
- [ ] Ensure retries do not duplicate side effects if downstream already succeeded.
- [ ] Emit metrics for timeout stage, attempt count, exhausted retries, and deadline exceeded.

**Retry storm:** If the HTTP client retries 3 times, retry advice retries 3 times, and broker redelivery runs 5 times, total calls multiply dramatically. Never inspect only one layer's config and assume load is controlled.

### 5.2. Timeouts Do Not Replace Circuit Breakers

A timeout terminates a single wait, whereas a circuit breaker can **stop calling a consistently failing dependency**; a bulkhead caps occupied workers/connections; a rate limiter governs call volume; backpressure slows message intake.

A complete control set may combine:

- Finite connection/read timeouts;
- Bounded retries with backoff;
- Circuit breakers driven by timeout/error rates;
- Semaphore/thread-pool bulkheads;
- Bounded queues on `MessageChannel`;
- Throttling or pausing pollers when backlog rises;
- DLQ/quarantine and operator replay for poison messages.

Do not route a timed-out request to an error flow while also automatically retrying elsewhere without a single owner and deduplication logic.

### 5.3. When Is a Timeout an Ambiguous Outcome?

When calling an API that **performs a side effect**, a timeout can occur **before sending**, **mid-send**, **after the server commits**, or **while waiting for the response**.

~~~text
Client           Remote service
  | --- request ----> |
  |                   | commit business operation
  |     X response    |  (response lost)
  | timeout           |
  | --- retry? -----> |  (risk of 2nd side effect)
~~~

Mitigations: mutually agreed idempotency keys, querying business state after timeout, unique constraints, transactional outboxes, or compensating workflows. **A timeout is not proof that the command never executed.**

## 6. Spring Integration Layer: Endpoints, Gateways, Channels, and Pollers

### 6.1. Inbound Adapters and Pollers

For File/SFTP/JDBC polling:

- **Poll cadence**: schedules periodic fetches; does not determine how long a hung network request stays blocked.
- **Per-poll work budget**: caps duration/batch per poll cycle if your design uses a watchdog or equivalent control.
- **Adapter/client timeouts**: bound waits on remote sessions, requests, or queries.
- **Max messages per poll**: caps batch volume per cycle; does not set network timeouts.
- **Scheduler/thread pool**: ensure one slow source cannot starve all workers; monitor inflight count and queue depth.
- **Retry/backoff**: identify source-unavailable errors and re-fetch without dropping data.
- **Multi-replica**: use distributed claims/filters and idempotency; a timeout can expire a lease while the old worker is still processing.

**Scenario to test:** SFTP transfer takes longer than the poll interval. Does the system start overlapping transfers? Do threads block forever? If the scheduler/pool runs out of workers, how do backlogs and alerts reflect it?

### 6.2. MessageChannel and Send Timeouts

| Component | Timeout to Distinguish | Key Point |
|---|---|---|
| **DirectChannel** | Synchronous handler execution duration | Channel does not cancel blocked downstream HTTP/DB calls |
| **ExecutorChannel** | Executor acceptance wait, queue saturation | Transaction/thread context and cancellation are limited |
| **QueueChannel** | Message offer/poll wait and capacity | In-memory queues are not durable by default |
| **Messaging gateway** | Send request timeout, reply wait timeout (API/config-dependent) | Does not replace remote client connect/read timeouts |
| **PublishSubscribeChannel** | Fan-out duration across subscribers | Async and sync have different failure/latency profiles |

A `sendTimeout` may only bound the wait to **place a message into a channel** (when the channel can block); it does not set a deadline for downstream steps. Likewise, `replyTimeout` on a messaging gateway limits **waiting for a reply message**—it does not automatically cancel an in-flight HTTP/JMS request or DB query.

### 6.3. Inbound Gateways When the Caller Has Timed Out

For an HTTP inbound gateway:

1. The proxy/client may close the request once its wait expires.
2. The application handler may continue executing.
3. If the handler has side effects, the client may retry because it received no response.
4. To avoid duplicating effects, use a stable idempotency key and durable state.
5. For long-running work, prefer accept + tracking ID over synchronous waiting.

This is why timeouts **outside the service** (load balancers, proxies, clients) must be aligned with timeouts **inside the service**.

## 7. Layered Configuration and Testing Real Values

Good configuration states **explicit units and meaning**, avoiding lumping everything under a single `timeout` key.

~~~yaml
# ILLUSTRATIVE application-defined configuration.
# NOT properties automatically bound by Spring Integration.
app:
  integration:
    deadlines:
      http-ingress: 25s
      order-processing: 20s
    http-client:
      pool-acquire: 1s
      connect: 2s
      response: 4s
    sftp:
      connect: 5s
      handshake: 5s
      operation: 30s
    jdbc:
      pool-acquire: 2s
      query: 8s
    messaging:
      reply: 10s
    retry:
      max-attempts: 2
      initial-backoff: 1s
      max-backoff: 3s
~~~

These values are **illustrative suggestions for a specific flow**, not universal defaults for every connection. In code, bind/validate properties, pick clients that enforce those limits, and test effectiveness under network faults. Some clients use internal timers and cannot map every property one-to-one.

### 7.1. Checking Zero, Negative, and Very Large Values

Libraries may interpret **0** as "infinite", "no wait", "disable timeout", or "use default"; negative values are equally inconsistent. Therefore:

- [ ] Read the **exact method and version** semantics for 0/negative/null values.
- [ ] For critical remote I/O, avoid infinite waits unless justified and protected by other controls.
- [ ] Validate `Duration`, ms/s units, and integer conversions to prevent overflow.
- [ ] Do not set every timeout to 30 seconds if the upstream proxy errors at 20 seconds.
- [ ] Do not configure retry/backoff totals that exceed shutdown grace periods or SLAs.
- [ ] Do not set timeouts so short that slow-but-healthy networks constantly abort.
- [ ] Support per-environment, dependency, and operation overrides; review every change.

### 7.2. Java Example for an HTTP Client

A Spring Framework example using `RestTemplate` and a simple request factory:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestTemplate;

@Configuration
class PartnerHttpClientConfig {

    @Bean
    RestTemplate partnerRestTemplate() {
        var factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(2_000); // milliseconds
        factory.setReadTimeout(4_000);    // milliseconds
        return new RestTemplate(factory);
    }
}
~~~

This example **focuses on connect/read timeouts** and APIs should be checked when upgrading Spring Framework versions. `SimpleClientHttpRequestFactory` does not demonstrate pool acquisition or overall deadlines of a pooled HTTP client. For high HTTP throughput, you typically need a pooled HTTP client with corresponding timeouts, and configure the Spring Integration gateway to use the reviewed client/request factory.

**Do not** set only `replyTimeout` on an integration gateway and conclude the HTTP call has network timeouts: those are separate layers.

## 8. Security and Availability Principles

Timeouts limit held resources, but must never weaken authentication, TLS, or flow control:

- [ ] Verify TLS certificates/hostnames/CA chains; never disable verification because handshakes are slow.
- [ ] For SFTP, verify SSH host keys; never skip known-hosts to avoid timeouts.
- [ ] Store credentials in a secret manager with rotation and ownership.
- [ ] Retries after 401/403/certificate mismatch must follow policy rather than tight-loop hammering.
- [ ] Size connection/session pools properly so one failing dependency cannot exhaust all workers.
- [ ] Apply throttling/backpressure to avoid overwhelming a remote system as it recovers.
- [ ] Logs/traces should record only endpoint, stage, elapsed time, and business ID—never Authorization headers, private keys, raw tokens, or unnecessary PII.
- [ ] When timeouts leave files/queues/messages in an ambiguous state, enforce idempotency and replay audits.
- [ ] Alerts must separate transient/infrastructure faults from authentication/authorization or permanent data errors.

**Criterion:** A timed-out connection must transition into an **observable, handleable, and recoverable** state—not a hung thread or a vanished message.

## 9. SFTP: Connection Timeouts Differ from Remote Operation Timeouts

SFTP runs over SSH. A file transfer spans multiple steps: DNS → TCP connect → SSH handshake → authentication → open subsystem/session → list/stat → read/write → rename/close. **No single timeout inherently covers all of these steps.**

| Stage | Wait Check | Risk |
|---|---|---|
| TCP connect | Connect timeout and client DNS resolver | Host unreachable, SYN dropped |
| SSH handshake | Handshake/authentication/session timeout | TCP connects but SSH never completes |
| Remote list/stat | Operation timeout | Server hangs while listing directory |
| Download/upload | Stall/read/write timeout, total transfer budget | Connection stays open with zero progress |
| Rename/close | Operation/confirmation timeout | File may complete even though client timed out |
| Session reuse | Pool checkout, idle eviction, keepalive | Stale dead session or held too long |

Spring Integration SFTP uses a session factory and underlying SSH client that vary by version. **Read the API for your actual version** to configure each timeout; do not confuse SSH session options with an `IntegrationFlow` timeout.

### 9.1. Inbound Checklist

- [ ] Finite connect, SSH handshake, and remote operation timeouts configured per client capabilities.
- [ ] Never use poll interval as a substitute for network timeouts.
- [ ] Producers follow `.tmp` → rename or ready-marker conventions so partial files are never read.
- [ ] Limit file sizes, session counts, transfer concurrency, and bound memory usage.
- [ ] Emit metrics for byte progress/rate, stall duration, and oldest pending file.
- [ ] Host-key verification is enabled; known-hosts has an owner and rotation procedure.
- [ ] Use persistent metadata/filters and business idempotency; "downloaded" does not mean "processed".
- [ ] When multiple pods poll the same source, use distributed claims or valid partitioning.
- [ ] On transfer timeout, allow safe retries without marking files DONE prematurely.
- [ ] Test TCP blackholes, handshake stalls, hung list/stat calls, mid-transfer drops, and server-closed sessions.

### 9.2. Outbound Checklist

- [ ] Connect/operation/transfer timeouts are tested against a real server.
- [ ] Upload using a temporary name then rename/mark ready per contract.
- [ ] When rename/close response times out, check remote state before blindly re-uploading.
- [ ] Use unique filenames/versions/checksums/manifests for reconciliation.
- [ ] Never delete local source files before verifying remote handoff.
- [ ] Retries must not overwrite someone else's file or duplicate business effects.
- [ ] Do not assume atomic rename behaves identically across all servers/filesystems.

**Failure drill:** The server finished writing the full file, but the client lost the response during rename. The system must inspect the remote path/checksum and decide whether to finalize or idempotently retry—not silently create a second file.

## 10. HTTP: Multiple Timeout Layers Within One Request

### 10.1. HTTP Outbound Gateway

| Stage | Timeout | Why Separate It |
|---|---|---|
| Waiting for pooled connection | Pool acquisition | Request not sent yet; connect timeout does not cover this |
| DNS/TCP | Resolver/connect | Hostname or socket fails to establish |
| TLS | Handshake/transport | TCP is open but TLS can hang |
| Request body | Write/streaming budget | Large uploads when remote reads slowly |
| Response headers/body | Response/read timeout | Server replies slowly or streams indefinitely |
| Whole request | Overall deadline if client supports it | Read timeout may only cap idle intervals |
| Messaging gateway | Spring Integration reply timeout | Does not automatically cancel the HTTP socket |

### 10.2. HTTP Outbound Checklist

- [ ] Identify the actual client: `RestTemplate`, `RestClient`, `WebClient`, or a custom HTTP library.
- [ ] Pool acquisition/connect/response timeouts are set on the right factory/client.
- [ ] If the client supports an overall request timeout, use it alongside the flow deadline.
- [ ] Total attempts + backoff fit within the caller's SLA; never let proxies time out before the handler.
- [ ] Retry only retryable errors; never tight-loop retry 401/403/certificate mismatches.
- [ ] POST/PUT calls carry partner idempotency keys or have a status lookup API on timeout.
- [ ] Size connection pools, bulkheads/rate limits, and circuit breakers as needed.
- [ ] Cap request/response sizes and streaming durations.
- [ ] Test TCP blackholes, TLS stalls, 429, 503, slow headers/bodies, and timeouts after server commit.

### 10.3. HTTP Inbound Gateway

- [ ] Client, reverse proxy, gateway, and servlet container SLAs and timeouts align with the budget.
- [ ] Request/reply has a defined response/error contract and policy deadline.
- [ ] Bound request sizes, concurrent requests, and thread pools.
- [ ] When a client disconnects, the backend may **still execute side effects**; enforce idempotency.
- [ ] For long processing, use durable handoff + tracking ID instead of holding synchronous requests.
- [ ] Never log Authorization headers, session cookies, or raw sensitive payloads.
- [ ] Test duplicate POSTs after gateway 504s and late responses.

~~~text
T=0s   Client sends POST /payments
T=2s   IntegrationFlow calls partner
T=10s  Partner commits payment
T=12s  Response lost on return path
T=13s  Client reports timeout
T=14s  Client retries the same request
~~~

**A timeout does not prove non-execution:** without a stable idempotency key, two payments may be created.

## 11. JMS: Receive Wait, RPC Reply, and Broker Recovery

JMS must be configured per the **JMS provider** and container in use; no single timeout applies across all brokers.

| Stage | Time Limit | Key Consideration |
|---|---|---|
| Broker connect/TLS | Connection timeout, failover/reconnect | Provider-specific |
| Pull `receive(timeout)` | Receive wait | Expiration may simply mean the queue is empty |
| Listener container | Poll/recovery/backoff | Does not automatically cap business handler runtime |
| JMS request/reply | Gateway reply timeout | Request may already have been processed by consumer |
| Session transaction/ack | Provider commit/ack | Ambiguous state when connection drops |
| Late reply | Correlation/reply destination cleanup | Reply may arrive after caller gave up |

**`JmsTemplate.receiveTimeout`** governs the `JmsTemplate` receive call—not the whole-flow limit or service activator execution time.

### 11.1. JMS Checklist

- [ ] Broker connection, authentication, TLS, and recovery/backoff are tested under outages.
- [ ] Receive timeout and gateway reply timeout are never confused.
- [ ] Transacted session / acknowledgement modes are explicitly documented.
- [ ] Request/reply configures correlation, late-reply policy, and caller timeout handling.
- [ ] Consumers enforce business idempotency on message redelivery.
- [ ] Broker retries and DLQs are bounded; poison messages are not retained indefinitely.
- [ ] Metrics track oldest queue age, DLQ, redeliveries, connections, and handler duration.
- [ ] Test broker restarts, late replies, and listener crashes after DB commit but before ack.

**Warning:** An RPC gateway timing out while waiting for a reply does not mean the receiver did no work. When retrying, send the **same business request identity** to prevent duplicate effects.

## 12. AMQP / RabbitMQ: Confirm Timeout Does Not Mean Publish Failed

With Spring AMQP, distinguish TCP/TLS connect, heartbeats, request/reply gateways, publisher confirms, and consumer acknowledgements.

| Timeout / Liveness | Purpose | Does Not Replace |
|---|---|---|
| Connection timeout | Bounds socket/broker connection setup | Publisher confirm deadline |
| Heartbeat | Detects broken connections on broker cadence | Per-message processing timeout |
| RPC reply timeout | Waits for a reply to an AMQP request | Proof the consumer hasn't processed it |
| Publisher confirm wait | Waits for broker publish confirmation | Verification of downstream business effects |
| Consumer ack/failure policy | Controls redelivery | Business idempotency |
| Reconnect backoff | Prevents storms after broker outages | Overall flow deadline |

### 12.1. AMQP Checklist

- [ ] Exchanges, queues, bindings, and routing keys exist accurately per environment.
- [ ] TCP/TLS, heartbeats, recovery, and connection timeouts are tested.
- [ ] RPC reply timeouts have late-reply handling and proper correlation.
- [ ] Publisher confirms/returns record unknown outcomes on timeout.
- [ ] Consumer ack/prefetch/concurrency settings prevent messages from lingering unacked too long.
- [ ] Poison messages have bounded retries, DLX/DLQ, or appropriate quarantine.
- [ ] Producer/consumer handle redeliveries idempotently.
- [ ] Metrics cover ready/unacked counts, confirmation latency, reconnects, and DLQ.
- [ ] Test cases where broker accepts publish but confirm is lost; retries do not double business effects.

**Key point:** Heartbeats assess connection health, not per-message timeouts. A publisher confirm timeout represents an **ambiguous broker receipt**.

## 13. Kafka: Producer Delivery Timeout, Polling, and Consumer Liveness

The following property names belong to the Apache Kafka client; verify exact semantics against your deployed version.

### 13.1. Kafka Producer

| Property | Purpose | Do Not Assume |
|---|---|---|
| `request.timeout.ms` | Wait for broker response to one request | Not the whole-flow SLA |
| `delivery.timeout.ms` | Total delivery time cap per producer semantics | Does not cover HTTP/DB outside Kafka |
| `max.block.ms` | Blocks waiting for metadata or buffer on certain calls | Not ack time for already enqueued records |
| `linger.ms` | Wait to batch records before sending | Not a failure timeout |
| `retry.backoff.ms` | Backoff between eligible retries | Does not replace application deadlines |
| `Future.get(timeout)` | Limits caller waiting on future | Does not reliably stop record transmission |

`delivery.timeout.ms` must obey the Kafka producer constraint relative to `request.timeout.ms + linger.ms`. The values below are **illustrative only**, not universal tuning:

~~~properties
request.timeout.ms=10000
delivery.timeout.ms=30000
max.block.ms=5000
linger.ms=5
retry.backoff.ms=500
enable.idempotence=true
acks=all
~~~

Kafka producer idempotence/transactions do not replace business idempotency in DBs or HTTP calls. If the application times out waiting on `Future.get`, the record may still be sent and accepted by the broker later.

### 13.2. Kafka Consumer

| Property / Behavior | Primary Meaning | Not Equivalent To |
|---|---|---|
| `poll(Duration)` | Single wait to fetch records | Business handler deadline |
| `default.api.timeout.ms` | Default timeout for certain synchronous consumer APIs | Application-wide network timeout |
| `session.timeout.ms` | Detects dead consumer group member | Maximum handler duration |
| `heartbeat.interval.ms` | Heartbeat cadence per group config | Broker publish timeout |
| `max.poll.interval.ms` | Maximum time between valid group polls | Socket read timeout |
| Offset commit timeout | Wait for commit ack per API/client | Guarantee against DB duplicates |

### 13.3. Kafka Checklist

- [ ] Producer request/delivery/max-block timeouts align with retries, SLOs, and buffer memory.
- [ ] Never treat a future timeout as "the record definitely didn't reach the topic".
- [ ] Consumer group/offset and max-poll intervals fit batch processing duration.
- [ ] Failed records have DLT/recovery matching partition/business-key ordering policies.
- [ ] Consumers updating DBs enforce unique business keys/idempotency.
- [ ] Metrics track delivery latency, buffer waits, consumer lag, rebalances, and commit errors.
- [ ] Tested Kafka broker blackholes, unavailable metadata, lost acks, and consumer rebalances.
- [ ] When scaling concurrency/partitions, ordering and retry semantics remain intact.

Example: consumer commits DB then gets killed before committing offset. When Kafka redelivers the record, business idempotency must block duplicate inserts. Tweaking `request.timeout.ms` does not fix that window.

## 14. JDBC: Separate Pool, Socket, Query, Lock, and Transaction Timeouts

| Timeout Type | Configuration Level | Meaning |
|---|---|---|
| Pool acquisition | HikariCP `connectionTimeout` | Waiting to borrow a connection from pool |
| Connection validation | HikariCP `validationTimeout` | Checking connection liveness |
| Socket connect/read | JDBC driver/DataSource | Connecting to DB and waiting on network I/O |
| Statement/query | JDBC `Statement.setQueryTimeout`, `JdbcTemplate.setQueryTimeout` | Query limit enforced via driver |
| Lock wait | DB/transaction/session config | Waiting for row/table locks |
| Transaction timeout | Spring transaction manager / DB | Transaction limit per supported mechanism |
| Pool idle/max lifetime | HikariCP `idleTimeout`, `maxLifetime` | Connection lifecycle, does not cap queries |

**Important:** HikariCP `connectionTimeout` primarily bounds **waiting to acquire a connection from the pool**, not total SQL execution time. `maxLifetime` is not a query timeout and will not kill a slow query.

### 14.1. Query Timeout Example

~~~java
import javax.sql.DataSource;
import org.springframework.jdbc.core.JdbcTemplate;

JdbcTemplate jdbc = new JdbcTemplate(dataSource);
jdbc.setQueryTimeout(8); // seconds; enforcement depends on JDBC driver
~~~

This snippet illustrates statement timeout on `JdbcTemplate`; it does not cover pool acquisition, socket read, or database-side lock waits. Server-side lock/statement setting names depend on PostgreSQL, MySQL, SQL Server, or other engines.

### 14.2. JDBC Checklist

- [ ] Pool wait timeout aligns with thread pools, connection count, and traffic.
- [ ] Driver connect/socket timeouts are configured and tested with network faults.
- [ ] Query/lock/transaction timeouts have clear relationships to SLAs and batch limits.
- [ ] Queries have proper indexes, pagination, and query plans; never mask slow SQL with infinite timeouts.
- [ ] Never hold transactions/locks open across slow remote HTTP/SFTP calls unless necessary.
- [ ] Multi-replica JDBC pollers use row claims/leases and recovery when workers time out.
- [ ] Unique constraints/idempotency protect against ambiguous transaction outcomes.
- [ ] Metrics cover active/idle/pending pool counts, slow queries, lock waits, and timeouts/rollbacks.
- [ ] Test DB failover, lock contention, pool starvation, and network loss during commit.

If the client loses connectivity during commit, reconcile business state before retrying. Never assume every database timeout definitely rolled back.

## 15. File Adapter and Network Filesystems

The File adapter reads/writes the filesystem via local APIs, so it normally has **no TCP remote connection timeout** like SFTP/HTTP. However, NFS/SMB and remote volumes can still stall I/O due to network or filesystem issues.

- [ ] File-ready protocol and completion wait times are defined.
- [ ] Poll interval, batch size, maximum file size, and processing duration are bounded.
- [ ] If using network mounts, test server disappearance while files are open/being written.
- [ ] Java Future timeouts/thread interruption **do not guarantee** aborting kernel or remote filesystem I/O.
- [ ] Metadata/claims/filters and post-crash retries exist; never mark DONE prematurely.
- [ ] Never delete/move files before business commit and recovery obligations are met.
- [ ] Alerts monitor oldest pending file age, stalled file progress, and disk/inode usage.
- [ ] Multiple pods sharing a volume must use distributed claims/partitioning and idempotency.

For outbound files, if an error occurs after bytes were written, inspect the target file/checksum/manifest before rewriting. Rename may not have identical atomic semantics across all filesystems.

## 16. Summary of Timeouts to Review by Technology

| Technology | Wait Layers to Check | Do Not Confuse |
|---|---|---|
| **File** | File readiness, poll, filesystem, total operation | TCP-style connect timeout |
| **SFTP** | TCP, SSH handshake, session, list/read/write, transfer deadline | Poll interval, heartbeat |
| **HTTP** | Pool, connect/TLS, request write, response, gateway reply | `replyTimeout` with entire remote request |
| **JMS** | Broker connection, receive, RPC reply, transaction/ack, failover | Receive wait with handler deadline |
| **AMQP** | TCP/TLS, heartbeat, RPC reply, publisher confirm, ack | Heartbeat with publish timeout |
| **Kafka producer** | Max block, request, delivery, future wait | Future timeout meaning broker didn't receive |
| **Kafka consumer** | Poll wait, API, heartbeat/session, max poll interval, commit | Poll timeout with business processing timeout |
| **JDBC** | Pool acquire, connect/read, query, lock, transaction | Pool maxLifetime with query timeout |

For **every remote call**, documentation should record: endpoint owner, actual client, timeouts + units, retry owner, remaining deadline, side-effect/ack boundary, ambiguous-outcome handling, alerts, runbook, and rollback triggers.

## 17. Startup, Graceful Shutdown, and Scaling Under Slow Remotes

### 17.1. Startup/Readiness

- [ ] Required configs and secrets are validated before accepting traffic.
- [ ] Readiness and liveness serve distinct roles; do not endlessly restart pods over temporary broker outages.
- [ ] Reconnect backoff includes jitter to stop replicas from reconnecting in lockstep.
- [ ] Certificate/host-key/auth failures are not masked by long infinite retries.
- [ ] Pollers/listeners can be paused and reopened post-incident per runbook.

### 17.2. Shutdown/Rolling Deployment

- [ ] Stop accepting new messages on shutdown per endpoint lifecycle.
- [ ] Inflight work finishes or has safe replay/recovery within the grace period.
- [ ] Remote calls have timeouts so they cannot hold workers forever; test hung sockets.
- [ ] Never ack sources before side effects meet contract criteria.
- [ ] Version rollbacks include reconciliation for already-executed outbound side effects.
- [ ] Multiple pods do not compete to claim the same file/row outside design rules.

### 17.3. Capacity and Pool Saturation

Suppose an HTTP connection pool has 20 connections while 300 workers call the API concurrently. Most workers can stall in **pool acquisition** even if connect timeout is 2 seconds. Increasing connect timeout will not solve pool exhaustion. Combine bounded executors, pool sizing, rate limits, circuit breakers, backpressure, and alerts to protect both the app and the remote server.

**Technology section takeaway:** Do not pick timeouts by property name; choose them by the **exact waiting state created by the protocol/client** and test that state directly.

## 18. Observability: Pinpointing Which Stage Timed Out

A dashboard showing only total "timeout errors" cannot distinguish whether the fault lies in DNS, pool, broker, remote server, or database.

### 18.1. Mandatory Log Fields

| Field | Purpose |
|---|---|
| `correlationId`, `eventId`, business key | Link attempts and side effects of a single request |
| `adapterType`, endpoint ID | Identify File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC |
| `remoteHost`/target alias | Identify dependency without leaking credentials |
| `stage` | DNS, pool-acquire, connect, handshake, write, read, reply, ack, query |
| `timeoutConfiguredMs` | Show which threshold was actually enforced |
| `elapsedMs`, `remainingDeadlineMs` | Distinguish a slow step from overall flow budget exhaustion |
| `attempt`, `retryDelayMs` | Track retry storms and budgets |
| `outcome`, `errorClass` | Success, timeout, retry, unknown, quarantined |
| `sideEffectState` | Not sent, unknown, committed, acknowledged |
| `mappingVersion`, `clientVersion` | Investigate regressions after config/library upgrades |
| `pod`/instance, traceId | Identify which replica stalled and trace end-to-end |

Never log passwords, tokens, private keys, cookies, Authorization headers, or full payloads containing PII. When operators need to verify remote endpoints, use aliases and safe metadata.

### 18.2. Per-Stage Metrics

| Metric | Usage |
|---|---|
| `remote_connect_duration` p95/p99 | Detect network/TCP issues |
| `tls_ssh_handshake_duration` | Detect auth failures or slow handshakes |
| `pool_acquire_wait` | Detect connection shortages and pool starvation |
| `remote_request_duration` | Detect slow services or timeouts near threshold |
| `gateway_reply_wait` | Separate time-to-reply from network read |
| `retry_attempts` and `retries_exhausted` | Measure fault tolerance and retry storms |
| `timeout_count_by_stage` | Route alerts to the right owner |
| `executor_queue_depth` and rejections | Detect flow congestion |
| `inflight_requests` and pool active/pending | Monitor held resources |
| `DLQ_age` / quarantine backlog | Detect non-self-healing errors |
| `Kafka_consumer_lag`, AMQP/JMS queue age | Measure backlog when remotes slow down |
| `SFTP_oldest_pending_file_age` | Spot stuck pollers/file transfers |
| `JDBC_query_duration` and lock wait | Distinguish slow SQL from pool wait |
| `business_completion_latency` | Prove whether end-to-end SLA is met |

The metric names above are **illustrative**; use the concrete metrics provided by Micrometer, Spring Boot Actuator, clients, and brokers in your chosen stack. Verify that instrumented metrics are actually exported to your observability backend with useful filter tags, without exploding cardinality by putting user IDs or event IDs into tags.

### 18.3. Recommended Alerts

- Timeout rate and p95/p99 rise above baseline across consecutive windows.
- Any remote target shows `pool_acquire` near threshold or rising pending queues.
- Kafka producer delivery errors, consumer lag, or offset commit failures spike.
- SFTP has ready files sitting too long without being downloaded/completed.
- JMS/AMQP oldest message age or DLQ exceeds target.
- DB connection pool pending count rises and lock timeouts appear frequently.
- Retry counts/attempts rise while business completions fall.
- **Unknown outcomes** remain unreconciled past deadline.
- A configured timeout fails to free threads under fault injection.

Alerts must have **severity, owner, runbook, and silencing/noise-reduction criteria**. Base thresholds on product SLAs and baselines rather than a single universal number across all environments.

## 19. Pre-Production Fault-Injection Testing

Timeouts are validated by reproducing the exact slow network/target conditions—not merely by unit-testing a `Duration` property.

### 19.1. Testing Principles

1. Stand up real dependencies or high-fidelity test environments (SFTP server, broker, DB, HTTP stub).
2. Preserve business IDs and correlation IDs to trace impact after timeouts.
3. Inject faults at the exact stage: connect, TLS, pool wait, read stall, write stall, broker ack, DB lock.
4. Measure **actual time for the caller to exit** and verify threads/connections are released.
5. Verify retries stop per budget and error paths lead to recoverable states.
6. Inspect actual side effects on remote targets post-timeout; never guess from exceptions.
7. Re-test with multiple replicas, concurrent traffic, rolling deploys, and retry queues.
8. Record evidence: elapsed time, configured timeout, logs, metrics, business outcome, and version.

Network fault proxies, mock servers, or testcontainers help simulate faults, but choose ones faithful to real dependencies and **do not assume mocks completely replace staging/real brokers**.

### 19.2. Numbered Test Matrix

| ID | Scenario | Expected Outcome |
|---|---|---|
| **T01** | DNS fails to resolve hostname | Classified error raised; does not hang forever within resolver limits |
| **T02** | TCP SYN dropped/blackholed | Connect timeout triggers; worker recovers |
| **T03** | TCP connects but TLS handshake hangs | Appropriate handshake/transport limit triggers |
| **T04** | Invalid TLS certificate / hostname mismatch | Fails closed; never bypassed due to timeout |
| **T05** | Untrusted SSH host key | SFTP rejects connection and raises security alert |
| **T06** | Connection pool exhausted | Pool acquisition timeout and backpressure engage |
| **T07** | Connection held too long | Pool metrics/alerts reflect state |
| **T08** | HTTP server never sends response headers | Response timeout fires at the proper layer |
| **T09** | HTTP server trickles body indefinitely | Overall deadline/size limit bounds total duration |
| **T10** | HTTP request body upload blocked | Write/operation budget or isolation handles it |
| **T11** | HTTP POST committed at partner, response lost | Idempotency/reconciliation prevents duplicate |
| **T12** | Continuous HTTP 429 and 503 responses | Bounded retries, backoff/jitter, no storm |
| **T13** | HTTP client disconnects before backend finishes | Side effect recorded; retry does not duplicate |
| **T14** | Proxy timeout shorter than backend | Mismatch detected and deadline budget fixed |
| **T15** | SFTP connects but list/stat hangs | Operation timeout or watchdog verified |
| **T16** | SFTP download stalls mid-file | File not treated as ready/processed; safe recovery |
| **T17** | SFTP upload completes but rename response lost | Remote state inspected before retry |
| **T18** | SFTP session cache hands out dead session | Bounded reconnect; no tight retry loop |
| **T19** | SFTP server limits connections | Pool/concurrency does not saturate server |
| **T20** | Local file still being written | Not processed before ready marker/rename |
| **T21** | NFS/SMB mount unresponsive | Runbook detects file I/O block and isolates impact |
| **T22** | JMS receive finds no message | Receive timeout means "no message", not business failure |
| **T23** | JMS RPC reply arrives after timeout | Late reply handled; retry causes no double effect |
| **T24** | JMS broker failover mid-transaction | Reconnect/redelivery follows policy; no lost state |
| **T25** | JMS consumer killed after DB commit, before ack | Idempotent redelivery |
| **T26** | AMQP publisher confirm never arrives | Unknown outcome recorded; consumer idempotent |
| **T27** | AMQP heartbeat breaks while request is active | Reconnect does not duplicate side effects |
| **T28** | AMQP RPC reply arrives late | Safe correlation/late-reply handling |
| **T29** | AMQP unacked count climbs with slow handler | Alerts/backpressure engage; proper prefetch/concurrency |
| **T30** | Kafka broker rejects/drops producer request | Request/delivery timeout and proper error/retry |
| **T31** | Kafka metadata/buffer unavailable | Max-block timeout measured and monitored |
| **T32** | Kafka `Future.get` times out, record later succeeds | Record not assumed canceled |
| **T33** | Kafka consumer exceeds interval between polls | Rebalance/partition handling controlled |
| **T34** | Kafka offset uncommitted after DB commit | Redelivery creates no business duplicate |
| **T35** | Failed Kafka record mid-partition | DLT/retry upholds ordering policy |
| **T36** | JDBC connection pool exhausted | Pool wait timeout triggers without blocking all threads |
| **T37** | JDBC query locked for long duration | Query/lock/transaction timeout fires per config |
| **T38** | JDBC network drops right at commit | Result reconciled; idempotent retry |
| **T39** | JDBC polling two replicas claim same row | No unintended double processing |
| **T40** | ExecutorChannel queue full | Bounded rejection/backpressure; no OOM |
| **T41** | `replyTimeout` shorter than HTTP client read timeout | Design catches side effects continuing after caller timeout |
| **T42** | Retries enabled across client, advice, and broker | Total attempts stay within budget; no storm |
| **T43** | Poison message retries repeatedly | Bounded retry, quarantine/DLQ, and replay |
| **T44** | Pod receives SIGTERM during pending remote call | Graceful stop/recovery with no lost messages |
| **T45** | Flow deadline expires before next retry | Insufficient-budget attempt skipped; terminal state set |
| **T46** | Remote API recovers after outage, multiple replicas retry | Jitter/throttling prevents thundering herd |
| **T47** | Rotating TLS/SSH certificate or service secret | New connections succeed; old revoked safely |
| **T48** | Response has massive payload | Size/streaming limits and deadline protect memory |
| **T49** | Circuit breaker opens due to timeouts | Stops sending uncontrolled traffic |
| **T50** | Replay after timeout with original business key | No duplicate side effects; full audit trail |

**Acceptance evidence:** record expected vs actual result, configured timeout, measured elapsed time, target/adapter, client version, attempt count, remaining held connections/threads, side-effect state, correlation ID, and verifier. Passing a test merely by observing an exception **is insufficient** unless you confirm the worker was freed and the external system was not left in a corrupt state.

## 20. Runbook for Abnormal Timeout Spikes

### 20.1. Diagnostic Order

1. **Scope:** Which adapter, target, cohort/pod, and since when?
2. **Which stage is stuck:** DNS, pool, connect, TLS/SSH, write, read, reply, ack, DB query?
3. **Capacity:** What are thread pool, executor queue, connection pool, inflight, and backlog levels?
4. **Remote health:** Is the server/broker/DB failing, rate-limiting, or changing certs/credentials?
5. **Timeout budget:** Is the proxy/client deadline shorter than the server handler/gateway?
6. **Retry owner:** How many layers are retrying, and what are actual attempts and backoffs?
7. **Business state:** Are side effects committed even though the caller only got timeouts?
8. **Error path:** Are messages in retry queues, DLQ, outbox, or already acked/offset-committed?
9. **Decision:** Lower concurrency, pause poller, trip circuit breaker, switch async, or fail over.
10. **Recovery:** Replay with idempotency, reconcile remote state, and close incident with evidence.

### 20.2. Operational Response Table

| Observation | Do Not Do | Do Instead |
|---|---|---|
| Sudden HTTP timeouts | Increase read timeout infinitely | Check remote latency/pool and budget; apply backpressure |
| Pool acquisition timeouts | Only increase connect timeout | Measure active/idle/pending, sizing, and inflight |
| SFTP list/download stalls | Disable host-key verification | Separate network vs security faults; manage sessions and retries |
| Kafka producer delivery timeouts | Reset topic/offset arbitrarily | Check broker/metadata/buffer and publish status |
| JMS/AMQP RPC reply timeouts | Retry request with a new ID | Reuse stable business ID and reconcile processed requests |
| DB lock wait timeouts | Infinitely retry the same query | Find blocking transactions, indexes, concurrency, isolation |
| Error flow loses messages | Swallow exception and log | Verify ack/commit, route to durable quarantine |
| Restart re-runs many flows | Delete pending files/queues | Reconcile state and replay idempotently |

### 20.3. Replay After Timeout

- Verify downstream side effects by business key.
- If already completed, update state accordingly and avoid sending a second time.
- If not completed, replay per contract and retry limits.
- If undetermined, transition to **UNKNOWN_OUTCOME** with an owner/ticket; do not blindly apply risky actions.
- Check ordering, data version, and request validity before replaying.
- Perform final reconciliation and record an audit entry.

## 21. Case Study: SFTP → DB/Outbox → Kafka and Partner HTTP

An example system receives order CSVs via SFTP; parses/validates them, writes to a JDBC database, stores an outbox record, and publishes to Kafka. A secondary step calls a partner HTTP API. Files must be processed within **10 minutes** of being marked ready; the partner API has its own SLA.

### 21.1. Flawed Initial Design

- SFTP poller runs every 2 seconds with no remote read timeout.
- Two replicas share a session pool with no connection cap.
- JDBC connection pool has only a few connections while workers scale to hundreds.
- HTTP outbound sets only gateway reply timeout, with no connect/read timeout on the client.
- Both HTTP client and Integration advice retry 5 times each.
- DB commits then sends directly to Kafka without an outbox.
- Errors are not tagged by stage, so everything shows up as "integration timeout".

The system may pass locally, but when the partner slows down it suffers thread starvation, timeout storms, duplicate records, and unrecoverable messages.

### 21.2. Improved Design

**SFTP ingress:** Producer uploads a temp name then renames on completion; client configures connect, handshake, and operation budgets; poller caps batch size and inflight work. Two pods use distributed claims or partitioned remote paths; each order carries an idempotency key.

**JDBC:** Connection pool acquisition has a finite timeout; query/lock/transaction timeouts are set per driver/DB. Unique keys block duplicate orders. Business record and outbox event are written in one local DB transaction.

**Kafka:** Outbox publisher uses producer request/delivery timeouts aligned with SLA, handles callbacks/unknown outcomes, and assigns stable event IDs. Downstream Kafka consumers remain idempotent.

**Partner HTTP:** Invoked in a separately budgeted step with pool acquisition/connect/read timeouts and capped concurrency. For POST retries, reuse the same idempotency key or query business state after timeouts.

**Error flow:** Data errors route to quarantine; transient errors use bounded retries, moving to a durable queue for async processing if the synchronous budget runs out. Dashboards track pending file age, DB pool wait, HTTP p95 response time, outbox lag, Kafka delivery failures, and `UNKNOWN_OUTCOME` counts.

### 21.3. Illustrative Budget

| Stage | Design Limit | Meaning |
|---|---:|---|
| SFTP connect | 5 s | Single socket/SSH setup per supported API |
| SFTP transfer operation | 30 s | Requires realistic bounds and recovery |
| CSV parse/validation | 5 s (target) | Bounded file size and row count |
| DB pool acquisition | 2 s | Prevents 200 workers from waiting forever |
| DB query/transaction | 8 s (driver/DB-dependent) | Applies to DB operations only |
| HTTP per attempt | Connect ≤ 2 s, response ≤ 4 s | Single partner call |
| HTTP retry | 2 attempts, 1 s backoff | ~13 s under assumed worst case |
| Kafka outbox publish | Delivery timeout 30 s/attempt | Handled separately without holding DB transaction open |
| Business SLA | 10 minutes from ready file | Tracked end-to-end to business completion |

These are **illustrative values**, not copy-paste production settings. Many stages run asynchronously or overlap; total formulas must be derived from the actual topology. A 10-minute business SLA does not permit hanging an SFTP or HTTP thread for 10 minutes.

### 21.4. Failure Drills

**Drill A — SFTP hangs on list/stat:** Poller does not lock up the entire scheduler forever; metrics, retry/backoff work, and files remain re-processable.

**Drill B — HTTP timeout after remote commit:** Retry with the same idempotency key or check state; no second transaction created.

**Drill C — DB pool exhausted:** Workers stop accepting more work cleanly; pool wait timeouts and alerts surface the exact cause without tight-loop retries.

**Drill D — DB committed, Kafka publish failed:** Outbox retains the event; publisher recovers and safely resends.

**Drill E — Pod killed mid-send:** Metadata and message state allow replay; never falsely marked complete.

**Lesson:** Timeouts are part of the recovery protocol. Cutting wait times without managing side-effect state can be more dangerous than letting requests run slow.

## 22. Reusable Production Timeout Review Form

~~~yaml
# ILLUSTRATIVE review form, NOT Spring Boot auto-config.
flow: orders-sftp-to-db-kafka-http
owner:
  application: integration-team
  onCall: platform-operations
businessSla:
  from: remote-file-ready
  to: order-processed
  maximum: 10m
remoteEndpoints:
  - name: supplier-sftp
    protocol: sftp
    clientVersion: REVIEW_REQUIRED
    connect: 5s
    handshake: REVIEW_REQUIRED
    operation: 30s
    retryOwner: sftp-ingress
    ambiguousOutcome: verify-remote-file-state
  - name: partner-http
    protocol: http
    poolAcquisition: 1s
    connect: 2s
    response: 4s
    totalAttempts: 2
    backoff: 1s
    retryOwner: order-partner-client
    ambiguousOutcome: lookup-by-idempotency-key
  - name: order-jdbc
    protocol: jdbc
    poolAcquisition: 2s
    query: 8s
    lock: REVIEW_REQUIRED
    retryOwner: db-transaction-handler
  - name: kafka-producer
    protocol: kafka
    maxBlock: 5s
    requestTimeout: 10s
    deliveryTimeout: 30s
    ambiguousOutcome: outbox-and-business-id
controls:
  boundedInflight: true
  idempotencyKey: source-orderId-revision
  durableErrorRecovery: true
  shutdownRecoveryTested: true
observability:
  timeoutByStage: required
  outstandingUnknownOutcomes: required
  endToEndLatency: required
approval:
  technicalOwner: PENDING
  security: PENDING
  operations: PENDING
~~~

This template is a **decision document**, not framework-recognized properties. Units, client names, capabilities, and thresholds must be enforced and verified; all `REVIEW_REQUIRED` and `PENDING` items must be resolved before GO.

### 22.1. Go/No-Go Decision

| Status | When Applicable |
|---|---|
| **GO** | Layered timeouts tested, budget fits SLA, recovery backed by evidence |
| **GO WITH EXCEPTION** | Exceptions have owner, impact scope, mitigations, and expiration date |
| **HOLD / RETEST** | Missing handshake/pool/read/ack tests or unproven retry budget |
| **NO-GO** | Cannot stop hung resources, uncontrolled data loss/duplication, TLS/host-key bypassed, or unknown side effects |

## 23. Anti-Patterns to Avoid

**One global timeout for every system:** fails to separate pool wait, connect, reply, and query. Maintain a matrix per client/protocol.

**Connect timeout set while read timeout is left unset:** TCP connects while the server stays silent, and threads wait indefinitely.

**Using reply timeout instead of network timeout:** The gateway stops waiting for a reply while the remote operation keeps running and holding a connection.

**Assuming timeout 0 is always safe:** semantics of 0/negative/null vary by API; validate against the actual version.

**Increasing timeouts to hide pool starvation:** 300 workers fighting over 20 connections lengthens pool waits; fix with capacity sizing and backpressure.

**Retrying every timeout as if no side effect occurred:** creates duplicate transactions/files/messages; enforce idempotency and reconciliation.

**Aborting requests without tracking outcome:** reports failure while ignoring completed partner actions. Track unknown outcomes with a runbook.

**Measuring only exceptions, not actual latency:** read timeouts reset when a server trickles bytes slowly. Enforce overall deadlines and payload limits.

**Setting poll interval equal to network timeout:** two distinct concepts; a single poll can still hang.

**Treating JMS receive timeout as a business deadline:** receive timeout may just mean the queue is empty, not a handler limit.

**Treating AMQP heartbeat as a publish timeout:** heartbeats check connection health; publisher confirms are separate.

**Assuming Kafka Future.get timeout means record wasn't sent:** the producer may still transmit it; verify state and use business keys.

**Assuming JDBC connectionTimeout covers all queries:** pool wait differs from lock/query/socket/transaction timeouts.

**Assuming application rollback reverses timed-out requests:** DBs, brokers, files, and remote APIs may already have committed; reconcile and compensate.

## 24. Self-Check Questions

1. How do connect timeout, read timeout, and whole-flow deadline differ?
2. When a server trickles bytes slowly, why might read timeout fail to cap total response duration?
3. Does a gateway reply timeout automatically cancel an underlying waiting HTTP socket?
4. When an HTTP connection pool is exhausted, does increasing connect timeout help?
5. Why can't an SFTP poll interval replace an SSH operation timeout?
6. When an SFTP upload succeeds but the rename response times out, what should the system do?
7. What does JMS `receiveTimeout` mean when the queue is empty?
8. Why doesn't a JMS RPC reply timeout prove the consumer didn't execute the business logic?
9. How does an AMQP heartbeat differ from a publisher confirm timeout?
10. Which wait periods do Kafka's `max.block.ms`, `request.timeout.ms`, and `delivery.timeout.ms` govern?
11. If `Future.get(timeout)` expires, is the Kafka record guaranteed to be canceled?
12. Is `max.poll.interval.ms` a timeout on the Kafka business handler?
13. How does HikariCP `connectionTimeout` differ from a JDBC query timeout?
14. Why might a query timeout fail to protect against network stalls across all drivers?
15. Does a File adapter reading NFS need to account for network I/O stalls?
16. What issue can arise if a request times out after DB commit but before broker ack?
17. Why can multi-layer retries exceed the inbound deadline?
18. When should a transaction move from a synchronous gateway to durable asynchronous processing?
19. Which metrics distinguish pool starvation from slow remote responses?
20. What steps ensure safely replaying a request with an unknown outcome?

**Hint:** Always answer along the chain **where is it waiting → which timeout governs that stage → how far did side effects reach → is retry allowed → how to reconcile/recover**.

## 25. Glossary and References

| Term | Meaning |
|---|---|
| **Connect timeout** | Wait limit for establishing a connection |
| **Pool acquisition timeout** | Wait limit for borrowing a pooled connection |
| **Handshake timeout** | Wait limit for TLS/SSH negotiation/auth |
| **Read / write timeout** | Wait limit for a specific I/O operation |
| **Response/reply timeout** | Wait limit for a request/message reply |
| **Whole-flow deadline** | End-to-end time limit for the business contract |
| **Retry/backoff** | Retrying with bounded attempts and controlled delays |
| **Circuit breaker / bulkhead** | Blocking consistently failing dependencies / capping occupied resources |
| **Backpressure** | Throttling input rate to match processing capacity |
| **Idempotency** | Repeating requests without unintended duplicate business effects |
| **Unknown outcome** | Caller cannot verify whether the receiver executed the side effect |
| **Ack / offset commit** | Broker acknowledgement or processed-position marker |
| **Delivery timeout** | Delivery time limit per client semantics |
| **Reconciliation** | Verifying and aligning actual business and message state |
| **Graceful shutdown** | Stopping new intake and draining/recovering inflight work safely |

Resources to consult **for your exact product version**:

- **Spring Integration Reference Guide:** Message Channels, Gateways, Polling Consumer, Error Handling, File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC.
- **Spring Framework / Spring Boot Reference:** HTTP client request factories, transactions, executors, configuration properties, Actuator/observability.
- **Apache Kafka Client Configuration Documentation:** producer `request.timeout.ms`, `delivery.timeout.ms`, `max.block.ms`; consumer group, poll, heartbeat, and session settings.
- **Spring for Apache Kafka Reference:** listener container, acknowledgements, retries, error handlers, and DLT.
- **Spring AMQP / RabbitMQ documentation:** connection timeout, heartbeat, reply timeout, publisher confirms, and consumer acks.
- **Jakarta Messaging/JMS vendor documentation:** receive, request/reply, connection failover, transactions, and redelivery.
- **JDBC driver/database documentation and HikariCP configuration:** connection pool, query, socket, lock, and transaction timeouts.
- **SSH/SFTP client and server documentation:** handshake, session, remote operations, keepalive, file atomicity, and retry semantics.

**Final criterion:** "Having set a timeout" does not mean a remote connection is safe. A production system must prove every waiting state is properly bounded, total time stays within SLA, retries do not duplicate side effects, workers/connections are reclaimed, ambiguous states can be reconciled, and all errors have metrics, owners, and runbooks.
