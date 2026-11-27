# Timeouts, Deadlines, and Cancellation Propagation

In a cloud system, an API rarely performs all its work inside a single process. It may call databases, caches, payment services, internal APIs, message brokers, or many other services. Every network call can be slow, unresponsive, or interrupted. If each layer waits for an arbitrary duration, the system easily holds requests too long, exhausts threads/connections, continues working after the user has given up, and amplifies outages through retries.

Three mechanisms must be designed together:

- **Timeout:** a time limit on how long an operation is allowed to wait or execute before the caller stops waiting.
- **Deadline:** the final point in time by which an entire request or journey still has value if completed.
- **Cancellation:** a signal asking in-flight work to stop because it is no longer needed or no longer has enough time.

In the **CLOUD_ARCHITECTURE** module, these are essential principles for designing APIs with predictable latency, protecting resources, reducing cascading failures, and operating reliably. The goal is not merely to fail fast, but to ensure work stops at the right time, data remains in a valid state, and dependencies do not become overloaded.

## 1. Why must timeouts, deadlines, and cancellation go together?

Consider a scheduling API:

~~~mermaid
flowchart LR
    Client["Client"] --> Gateway["API Gateway"]
    Gateway --> Booking["Booking API"]
    Booking --> Inventory["Availability service"]
    Booking --> Payment["Payment service"]
    Booking --> DB["Database"]
~~~

The client sends a request and waits at most 2 seconds. The gateway might wait 3 seconds for Booking; Booking in turn waits 2 seconds for Inventory, 5 seconds for Payment, and 3 seconds for the database. Once the client has timed out, downstream layers may keep waiting or executing work. A single request can tie up resources for many seconds after its result is no longer useful.

Common consequences:

1. **Threads or connections held too long:** slow requests accumulate and reduce capacity to serve new requests.
2. **Queues swell:** the server accepts work faster than it completes, driving latency even higher.
3. **Retry storms:** many callers retry after timing out, piling extra load onto an already struggling system.
4. **Useless work keeps running:** the caller cancelled or the user closed the page, yet dependencies keep processing.
5. **Ambiguous business outcomes:** the caller timed out while the server-side operation may have already committed.
6. **Cascading failures:** one slow dependency forces dependent layers to hold resources, degrading the entire system.

Timeouts, deadlines, and cancellation solve different parts of the problem. A timeout bounds a single wait; a deadline sets an overall limit for the journey; cancellation propagates the signal that work no longer needs to continue. Without any one of the three, layers can fall out of alignment on a request's timing and intent.

## 2. Distinguishing concepts and time scopes

| Concept | Scope | Question answered |
| --- | --- | --- |
| **Connect timeout** | Establishing a connection to a dependency | How long to wait before giving up if a connection cannot be established? |
| **Read/response timeout** | Waiting for data/response after connecting | How long without progress before the caller stops waiting? |
| **Request timeout** | A single request at one layer | What is the maximum duration one request may hold resources? |
| **Deadline** | Entire journey from start until expiration timestamp | Until when is the result still useful? |
| **Cancellation** | In-flight work across one or more layers | When the caller no longer needs the result, how do we tell the system to stop? |
| **Execution limit** | Runtime/job/function or execution platform | What is the maximum duration a process is allowed to run? |
| **Idle timeout** | An inactive connection or session | After how long should an idle connection be closed? |

**A timeout is not a deadline.** A layer might set a 1-second timeout per call yet perform 3 retries, exceeding 3 seconds total. A deadline is the overall cap; every call and retry must consume from the remaining time.

**Cancellation is not a rollback.** Cancelling a request can halt unexecuted work, but cannot by default undo a committed transaction or a payment already confirmed by a provider. For side-effecting operations, idempotency, transaction states, and separate reconciliation must be designed.

### Timeline example

Suppose a client starts at 10:00:00.000 and requires a response within 2 seconds:

| Timestamp | Event | Remaining budget |
| --- | --- | ---: |
| 10:00:00.000 | Client creates request, deadline at 10:00:02.000 | 2,000 ms |
| 10:00:00.120 | Gateway forwards to Booking | 1,880 ms |
| 10:00:00.300 | Booking calls Inventory | 1,700 ms |
| 10:00:01.050 | Inventory returns result | 950 ms |
| 10:00:01.100 | Booking calls Payment | 900 ms |
| 10:00:01.850 | Payment has not responded yet, 150 ms left | 150 ms |
| 10:00:02.000 | Deadline expires | 0 ms |

At expiration, Booking must stop waiting or transition to a pre-designed business state. It should not start an auxiliary request with a 1-second timeout because that cannot complete within the original deadline.

## 3. Designing time budgets from SLOs

Do not pick timeouts by intuition or apply one uniform value to every API. Start from the **journey SLO**, analyze p50/p95/p99 latency, and allocate budgets across layers.

Example of a search API needing p99 under 1,500 ms:

| Component | Illustrative budget |
| --- | ---: |
| Edge, authentication, and gateway | 100 ms |
| API processing | 150 ms |
| Search dependency | 700 ms |
| Database/metadata lookup | 250 ms |
| Serialization, network, and headroom | 300 ms |
| **Total** | **1,500 ms** |

This is a budgeting framework, not permission for each component to consume its budget independently. If search takes 650 ms instead of 400 ms, the API must recognize that remaining time has shrunk. Sequential calls add latencies together; parallel calls can finish in the time of the slowest branch, but consume higher concurrency.

### Sequential vs. parallel

If a request calls two dependencies sequentially:

\[
T_{\text{total}}\approx T_A+T_B+T_{\text{overhead}}.
\]

If two independent dependencies are called in parallel:

\[
T_{\text{total}}\approx\max(T_A,T_B)+T_{\text{overhead}}.
\]

Parallel calls can reduce latency, but **they are not free**: they create more concurrent work, more connections, and potential fan-out amplification. If one branch fails, the system should cancel the remaining branch when its result is no longer needed and cancellation is safe.

### Timeouts must be smaller than the remaining deadline

When calling a dependency, calculate the time left until the deadline, minus what is needed for response handling, commit, serialization, and returning the response. The dependency timeout must stay within that remaining budget.

For example, if 400 ms remain on the deadline and 80 ms are needed to process the response and finish the request, the dependency timeout can be at most around 320 ms, or less if other branches remain. Actual values must rely on latency distributions and SLOs, not just a single isolated p99 measurement.

### Avoid stacking default timeouts across layers

A common flawed design:

- API Gateway timeout: 30 seconds.
- Service A timeout: 20 seconds.
- Service B timeout: 20 seconds.
- Database timeout: 15 seconds.
- Each service retries twice.

Those numbers do not produce a clear journey bound. Each layer should receive a deadline or budget from its caller and set local timeouts based on the remainder. A gateway timeout shorter than downstream timeouts must also be coordinated so the client does not receive a 504 while the server keeps doing unnecessary work.

## 4. Calculating timeouts from real latency and load distributions

Latency has a distribution, not just an average number. Analyze:

- p50, p90, p95, p99, or p99.9 by endpoint and dependency.
- Connect time, TLS handshake, connection pool wait, queue wait, and processing time.
- Normal load, peak hours, cold starts, cache misses, and slow-downstream scenarios.
- Timeout errors by region, AZ, client type, and application version.
- Caller SLO and dependency SLO, along with remaining error budget.

Timeouts that are too short abort valid requests, trigger unnecessary retries, and increase load. Timeouts that are too long hold resources, grow queues, and delay incident detection. Choose thresholds that balance the **false-timeout rate** against the **maximum acceptable wait time**.

One starting point is observing dependency percentiles under representative load, then adding a safety margin for network and processing variance. However, do not blindly treat a dependency's p99 as the optimal timeout: if only 300 ms remain on the end-to-end deadline, a 1-second timeout is meaningless; if a write operation needs to finish safely, an overly aggressive timeout can produce indeterminate outcomes.

### Distinguishing timeouts from overload

Timeouts can stem from:

1. A genuinely slow dependency.
2. Exhausted connection pools or overly deep queues.
3. Network packet loss, DNS, or TLS handshakes.
4. CPU, memory, I/O, or lock contention.
5. Clients setting timeouts too tightly for the workload profile.

Do not simply raise timeouts when seeing spikes in timeouts. Identify where requests are waiting and which resource is saturated. If queues are growing, raising timeouts can hold even more requests and worsen the outage.

## 5. Deadline propagation across layers

In a distributed request, every layer must know the **shared expiration point**. Two common representations exist:

- **Absolute deadline:** an expiration timestamp on a wall clock, such as a Unix timestamp or timestamp with suitable precision.
- **Remaining timeout/budget:** remaining duration measured from send time, such as 450 ms remaining.

Absolute deadlines keep layers aligned on the exact same cutoff if clocks are adequately synchronized. Remaining timeouts avoid direct clock dependencies across machines, though each hop must subtract elapsed time and overhead. Some protocols provide built-in metadata for deadlines/timeouts; use proper semantics rather than inventing undocumented headers.

### Deadline propagation principles

1. The entry layer determines the deadline from product or client requirements, capped by a server-enforced maximum.
2. Each layer receives the deadline and checks remaining time before starting work.
3. Every outbound dependency call uses a timeout no larger than the remaining budget.
4. If the deadline has expired, refuse to start new work and return an appropriate error.
5. If in-flight work is still cancellable, propagate a cancellation signal downstream.
6. Record the original deadline, remaining time, and where the request terminated for investigation.

### Never trust client deadlines unconditionally

A client might send a very long timeout or a malformed value. APIs should enforce a **maximum request duration** and normalize deadlines based on server policy. Never allow a single caller to arbitrarily hold backend resources for minutes just by setting a distant deadline. Even for internal callers, validate permissions and caps so misconfigurations do not spread.

### Example HTTP header for remaining budget

A system may define an internal header such as X-Request-Timeout-Ms: 450, though this is **not a universal HTTP standard**. Producers and consumers must agree on:

- Exact unit (ms, seconds, or timestamp).
- How the header is decremented at each hop.
- Maximum cap and behavior when missing/malformed/negative.
- Whether it is overwritten by the gateway.
- Whether internet clients can spoof the header.
- How it correlates with request IDs and trace context.

Do not give a header the same name with different semantics across teams. If the platform/protocol has a standard deadline mechanism, prefer the documented contract.

## 6. Cancellation: stopping work when results are no longer needed

Cancellation is a signal that can flow from client to server, gateway to service, and service to dependencies. It is usually **cooperative**: each layer must observe the signal and stop cleanly at a safe checkpoint. Cancelling a task does not mean the runtime can forcibly terminate any thread, transaction, or I/O call instantaneously.

### Common triggers for cancellation

- Client closes the connection, cancels navigation, or user abandons the action.
- API gateway times out or the client disconnects.
- End-to-end journey deadline expires.
- One parallel branch fails, making remaining branches unnecessary.
- Operators stop a job, perform a rollout, or shut down a process.
- System is overloaded and triggers load shedding.
- A request is superseded by a newer operation.

### Behaviors to define

| Stage | How can it stop? | What must be preserved? |
| --- | --- | --- |
| Not yet started | Skip queueing or reject immediately | Do not spend resources on expired work |
| Waiting in pool/queue | Remove from queue or skip when dequeued by worker | Do not corrupt queue ordering or state |
| Calling dependency | Cancel request/stream if client and server support it | Clean up connections and release resources |
| Computing | Check cancellation between steps/chunks | Do not leave temp files or half-written state |
| Inside transaction | Roll back if transaction is still open and engine supports it | Never assume a committed transaction can roll back |
| Side effects occurred | Complete, reconcile, or run compensating actions | Accurate business state, no duplicate execution |

### Cancellation is not synonymous with dropping TCP

Closing a client socket does not guarantee downstream knows right away. Proxies may buffer requests, multiplexed connections may stay alive, or the server may have already read the full body and continued processing. Therefore, applications need explicit cancellation APIs or framework context/deadline mechanisms, while always keeping dependency timeouts as a final safety net.

### When should you not cancel?

A background task that has been accepted with a completion commitment does not necessarily depend on the initial HTTP connection. For example, a user submits a long report-generation request and the API returns 202 Accepted with a job ID. If the client subsequently closes the connection, the job must still run according to its committed lifecycle. In this case, the job-creation request ended; **the job has its own deadline, cancellation policy, and ownership**, rather than mechanically inheriting client connection cancellation.

## 7. Propagating deadlines/cancellation by protocol

### HTTP/1.1 and HTTP/2

HTTP has timeouts at clients, proxies, gateways, and server frameworks, yet lacks a single universal deadline header understood by all implementations. Clients can close connections or streams; servers need framework support to detect disconnects/cancellations and propagate them to child tasks.

With HTTP/2, a client can reset a single stream without closing the entire connection; servers and libraries must handle stream reset/cancellation events per framework semantics. Never assume an open TCP connection means every request on that connection is still wanted.

### gRPC

gRPC supports deadlines and cancellation natively in its RPC model. The client sets a deadline on the call; the deadline is propagated via internal metadata per gRPC mechanics; the server can inspect deadline/cancellation context to halt processing. Use gRPC's native deadline API rather than inventing custom headers and expecting every client/server to interpret them identically.

Illustrative Java example creating a call with a deadline:

~~~java
import io.grpc.Deadline;
import io.grpc.ManagedChannel;
import java.util.concurrent.TimeUnit;

class InventoryCaller {
    static InventoryGrpc.InventoryBlockingStub withDeadline(
            ManagedChannel channel, long remainingMs
    ) {
        InventoryGrpc.InventoryBlockingStub stub =
                InventoryGrpc.newBlockingStub(channel);
        return stub.withDeadline(
                Deadline.after(remainingMs, TimeUnit.MILLISECONDS)
        );
    }
}
~~~

This snippet illustrates applying a local deadline to a stub. In a production system, pass the **remaining time from the original request**, rather than creating a fresh full deadline at every hop; verify the proto-generated API and library version; handle DEADLINE_EXCEEDED/CANCELLED; and never swallow exceptions and continue executing side effects.

### Message brokers and queues

Message queues typically have a different lifecycle from HTTP:

- The job-submission request may have a deadline to confirm enqueueing.
- Messages/jobs can carry expiresAt, notAfter, or a business expiration if defined by the contract.
- Consumers must check job expiration before starting or before critical side effects.
- Cancellation can be signaled via control messages, job status in a store, or a management API; deleting a message from a queue does not automatically stop a running consumer.
- Retries, visibility timeouts/ack deadlines, leases, and job deadlines are distinct mechanisms and must be designed consistently.

An expired job can be routed to a dead-letter queue or an expired status for auditing. Never silently drop critical jobs if the product requires notification or reconciliation.

### Event streaming

For long-lived streams like WebSockets, server-sent events, or gRPC streams, deadlines may apply to session duration or per-message delivery. Cancellation/reset must release subscribers, cursors, and server resources. If a stream delivers durable events, distinguish **cancelling client delivery** from **cancelling event creation/storage**.

## 8. Implementing timeouts and cancellation in Java applications

Java offers different mechanisms depending on whether APIs are blocking, asynchronous, or reactive. Choose the right mechanism for your application stack and propagate deadlines down to child calls.

### HTTP client with connect timeout and request timeout

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

class CatalogClient {
    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofMillis(200))
            .build();

    HttpResponse<String> getItem(URI uri, Duration remaining)
            throws Exception {
        if (remaining.isZero() || remaining.isNegative()) {
            throw new IllegalStateException("Request deadline exceeded");
        }

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(remaining)
                .GET()
                .build();

        return client.send(
                request,
                HttpResponse.BodyHandlers.ofString()
        );
    }
}
~~~

In this example, connect timeout bounds connection establishment; request timeout bounds the request per the HTTP client API. The remaining value must be computed from the **original deadline**. This simplified snippet omits status-code handling, response parsing, caller cancellation, and handling indeterminate business outcomes. Reuse client instances rather than creating a new client per request.

### Cooperative cancellation in compute tasks

For CPU-intensive tasks, you can pass a cancellation flag or use interrupts. Workers must check at safe points:

~~~java
import java.util.concurrent.CancellationException;

class ReportBuilder {
    byte[] buildReport(CancellationToken token) {
        ReportAccumulator result = new ReportAccumulator();

        for (int page = 0; page < 10_000; page++) {
            if (token.isCancellationRequested()
                    || Thread.currentThread().isInterrupted()) {
                throw new CancellationException("Report generation cancelled");
            }

            result.add(renderPage(page));
        }

        return result.toByteArray();
    }
}
~~~

CancellationToken here is an illustrative interface/pattern, not a built-in core Java class. In production code, determine who owns the token, thread-safe signaling, resource cleanup, and behavior if cancelled mid-file/database write. Do not delete final output files if already committed and published to users; you can write to a temporary file and atomically publish upon completion.

### Future, interrupts, and limits of cancel

ExecutorService/Future supports requesting cancellation. However, Future.cancel(true) usually only sends an interrupt to the running thread if the task has already started; the task must cooperate by checking interrupt status or calling interruptible blocking methods. Some native calls, I/O operations, or libraries do not react promptly to interrupts. Calling cancel cannot be treated as proof that work has stopped or side effects were undone.

A safe pattern:

1. Keep a reference to the task/future by request or job ID.
2. When the deadline expires, issue cancellation once and mark cancellation-pending state.
3. Tasks check interrupt/cancellation at safe boundaries and close resources.
4. Track the lag from cancellation request until the worker actually stops.
5. If a task cannot stop in time, isolate or bound resources and handle late outcomes according to business rules.

### Transaction and connection pool timeouts

APIs can configure timeouts for acquiring connections, queries, transactions, and lock waits. These are distinct timeouts:

- **Connection acquisition timeout:** waiting for a connection from the pool.
- **Statement/query timeout:** limiting query execution duration.
- **Lock timeout:** maximum time waiting on a lock.
- **Transaction timeout:** limiting transaction duration via framework/engine where supported.

If you only set an HTTP timeout without cancelling queries, the database can keep running the query after the caller gave up. Configure JDBC drivers, ORMs, databases, and pools according to what they support; verify by observing whether the database server actually terminates the query.

Never cancel a transaction after commit and claim it rolled back. If the response is lost after commit, the client must look up the outcome using a request ID/idempotency key.

## 9. Retry budgets, timeouts, and idempotency

Retries are commonly used to survive transient network errors, but they must be bound to deadlines and safety under repetition.

### Retry only while time remains

Suppose 500 ms remain on the deadline, a call needs a 300 ms timeout, and 50 ms are reserved for response processing. Do not initiate a second retry if backoff plus timeout exceeds the remaining 150 ms. A retry guaranteed not to return before the deadline only adds load.

Retry design should specify:

- Maximum attempt count and retry budget per request/service.
- Retryable error types (timeouts, connection resets, specific statuses like 503 per contract).
- Which operations are safe to repeat; mutating operations require idempotency keys or deduplication.
- Exponential backoff and jitter; honor Retry-After when provided.
- A single layer responsible for retries, avoiding retry amplification across layers.
- The original deadline applied to the entire chain, including backoff delays.

### Write timeouts create unknown outcomes

For example, a client sends POST /payments, the payment provider processes and charges the card, and the response times out. The client cannot conclude the transaction failed. Retrying with a new idempotency key could charge the customer twice.

A safe workflow:

1. Generate a stable operation ID/idempotency key for the transaction and persist it durably.
2. Send the request with that key per the provider's contract.
3. If confirmation arrives, update business state.
4. On timeout or disconnect, record **UNKNOWN/PENDING_RECONCILIATION** rather than assuming failure.
5. Poll provider status or wait for webhooks; if retrying, use the exact same key.
6. Reconcile unresolved transactions before permitting a new operation.

### Not all timeout outcomes are the same

| Scenario | Meaning | Response |
| --- | --- | --- |
| Connect timeout before sending request | Connection to server likely not established | Bounded retry if operation is safe |
| Timeout while sending request | Server may have received part or all of request | Treat outcome as unknown unless proven otherwise |
| Timeout waiting for response | Server may have processed/committed | Look up via request ID/idempotency key |
| Deadline expired before starting | Do not send more work | Reject early |
| Caller cancels after commit | Business outcome already exists even though caller missed response | Query/reconcile, do not assume rollback |

## 10. API error codes and expressing timeouts

Do not use a single status code for every situation. Choices should match the component's role and the API contract:

| Code | Common meaning | When to consider |
| --- | --- | --- |
| **408 Request Timeout** | Server did not receive full request within wait window | Client sent request body too slowly or failed to finish within server limit |
| **504 Gateway Timeout** | Gateway/proxy did not receive timely response from upstream | API gateway waited on backend service past timeout |
| **503 Service Unavailable** | Service temporarily unable to handle request | Overload, maintenance, or dependency failure; may include Retry-After |
| **429 Too Many Requests** | Caller exceeded rate/concurrency limit | Rate limit or quota; client must back off per contract |
| **500 Internal Server Error** | Unclassified server error | Use only for genuine internal errors, not as a catch-all for timeouts |

An API server encountering a database query timeout can map it per product contract; there is no rule forcing every internal timeout to return 504. 504 usually fits a gateway/proxy waiting on an upstream. Provide dedicated business error codes such as REQUEST_DEADLINE_EXCEEDED or OPERATION_PENDING when clients need to distinguish unknown outcomes.

Never return stack traces, internal hostnames, tokens, or infrastructure details in responses. Responses should include a request/correlation ID so support can safely inspect logs.

### Retry-After and caller guidance

If the server wants the client to retry, specify when and under what conditions. Retry-After can express wait duration using HTTP semantics. Nevertheless, clients must still obey user-side deadlines, backoff, and idempotency. If a write operation's outcome is unknown, the API should direct clients to query operation status before initiating a new operation.

## 11. Cancellation in asynchronous tasks

For APIs returning 202 Accepted and a job ID, the job lifecycle must be managed independently of the HTTP connection that created it. A state model:

~~~mermaid
stateDiagram-v2
    [*] --> QUEUED
    QUEUED --> RUNNING: Worker picks up job
    QUEUED --> CANCELLED: Cancelled before running
    RUNNING --> SUCCEEDED: Completed
    RUNNING --> FAILED: Non-retryable error
    RUNNING --> CANCELLING: Cancellation requested
    CANCELLING --> CANCELLED: Stopped safely
    CANCELLING --> SUCCEEDED: Side effect already committed
    RUNNING --> EXPIRED: Job deadline expired before side effect
    FAILED --> QUEUED: Retried per policy
    SUCCEEDED --> [*]
    FAILED --> [*]
    CANCELLED --> [*]
    EXPIRED --> [*]
~~~

These states are illustrative and must fit the domain. For example, a report-generation job can be cancelled while rendering; a bank-transfer job cannot be treated as CANCELLED if the bank has already executed the order.

### Job API contract

A design can provide:

- POST /reports to create a job, returning 202 and a job ID.
- GET /reports/{jobId} to read status, creation time, deadline, and result.
- DELETE /reports/{jobId} or a dedicated cancel endpoint to request cancellation if state permits.

A DELETE request only **submits a cancellation request**; the response should reflect cancelling or cancelled status per contract semantics. If the job has already finished, the system must never pretend it erased side effects. Verify job ownership, prevent cancelling another tenant's job, and audit actions.

### Job deadlines and message expiry

A job may sit in a queue longer than its business validity window. Persist expiration timestamps in durable metadata and check them upon dequeue. Message broker TTLs may simply purge messages from the queue per broker semantics; they do not replace worker-side checks, especially once a message has been received or started running.

## 12. Observing timeouts and cancellation

Counting 504 responses alone is not enough to find root causes. Measure across each layer and the full journey.

| Metric | Meaning |
| --- | --- |
| Request latency p50/p95/p99 | End-to-end duration distribution and tail latency |
| Deadline exceeded rate | Percentage of requests expiring at each endpoint |
| Timeout by phase | Connect, pool wait, TLS, response/read, database query |
| Cancellation requested/completed | Count of cancel signals vs. tasks that actually stopped |
| Cancellation lag | Time from cancel request until worker frees resources |
| Work after caller gone | Work continuing after client disconnect/deadline |
| Retry attempts per request | Load amplification caused by retries |
| In-flight requests and queue depth | Held resources and backlog |
| Late result rate | Rate of responses/results arriving after deadline |
| UNKNOWN operation count | Unresolved write transactions awaiting reconciliation |

### Tracing and logs

Each request should record trace ID/correlation ID, original deadline, remaining budget at hops, configured timeouts, upstream target, status/error category, and cancellation reason. Log connection pool wait time separately from query execution time to distinguish client pool exhaustion from database bottlenecks.

Avoid high-cardinality metric labels like raw request IDs, user IDs, or full URLs. Those belong in access-controlled traces/logs; metrics should use endpoint classes, dependencies, regions, error categories, and aggregate states.

### Alerting

- Deadline exceeded rate rising or breaching error budget.
- p99 rising while throughput drops or queue depth grows.
- Cancellation requested rising without a corresponding rise in cancellation completed.
- Queries/calls continuing after caller timeout increasing.
- Sudden spike in retry attempts per request.
- UNKNOWN payment/booking operations accumulating or exceeding reconciliation SLA.

Base alerts on user impact and trends rather than firing on a single isolated timeout.

## 13. Case study: a booking API with a 2-second deadline

Suppose a booking platform has a create-booking API. Illustrative goals:

- Client receives a response within at most **2,000 ms**.
- Booking must avoid creating duplicate records on client retries.
- Availability is called synchronously because slot availability must be confirmed.
- Confirmation email is sent asynchronously.
- Payment provider has variable latency and may respond late.
- System must distinguish uncommitted bookings, committed bookings, and bookings awaiting payment verification.

### Step 1 — Allocate the deadline

| Component | Illustrative budget |
| --- | ---: |
| Gateway and authentication | 100 ms |
| Booking checks/validation | 150 ms |
| Availability | 350 ms |
| Payment provider | 900 ms |
| Commit and status update | 250 ms |
| Serialization, network, and headroom | 250 ms |
| **Total** | **2,000 ms** |

These budgets are initial assumptions and must be replaced with real latency distributions and benchmarks. The payment provider might have a p99 above 900 ms; in that case, the API must define policy: return pending status, use an asynchronous verification flow, or reject before side effects occur according to business requirements. You cannot simply bump the timeout to 5 seconds if the client SLO remains 2 seconds.

### Step 2 — Define cancellation behavior

- If cancelled **before starting**: do no further work.
- If waiting on Availability with no side effects yet: cancel the call when the deadline expires.
- If waiting on Payment: cancel the wait/connection where protocol supports it; payment outcome may remain unknown.
- If the booking transaction has not committed: roll back if still open and safe.
- If the booking has committed: do not pretend to roll back just because the client disconnected; look up the operation by idempotency key.
- Email is written to the outbox after commit; the email job has its own lifecycle and is not cancelled with the initial HTTP request.

### Step 3 — Idempotency and operation state

The client sends a stable idempotency key. Booking API stores the key with a payload hash and processing state. If the same key and payload arrive again, the API returns the stored result or in-progress status. If the same key arrives with a different payload, return a contract error.

If Payment times out, the operation moves to PENDING_RECONCILIATION (illustrative name). A dedicated worker polls the provider or handles webhooks, then updates the outcome. The client can GET operation status instead of initiating a new charge.

### Step 4 — Responses and late arrivals

If the entire transaction finishes before the deadline, return success. If the deadline expires before transaction commit, return an appropriate timeout error and halt unnecessary work. If payment may have succeeded without confirmation arriving, return an unknown/verifying status with the operation ID; never map it to "payment failed" without proof.

### Step 5 — Measure effectiveness

Track end-to-end latency, timeouts by dependency, pending payment ratio, reconciliation duration, retries, cancellation lag, duplicate bookings, and email queue lag. Evaluate against the journey SLO, not just the count of HTTP 200 responses.

## 14. Testing timeouts, deadlines, and cancellation

Resilience tests should prove that the system does not consume unbounded resources, avoids unintended side effects, and keeps data accurate when callers give up.

| Test case | Scenario | Expectation |
| --- | --- | --- |
| Slow dependency | Availability responds after 1.5 seconds | Booking enforces deadline, does not hold request past budget |
| Connect timeout | Cannot establish connection to Payment | Caller stops within timeout, controlled retry |
| Response timeout after commit | Provider processes payment but response is lost | Operation becomes pending/unknown; no new payment created with a different key |
| Client disconnect | Caller closes HTTP connection | Cancellation propagates to cancellable tasks |
| One parallel branch fails | Search metadata fails while recommendation branch is running | Cancel unnecessary branch if safe |
| Expired queue job | Worker dequeues job past deadline | Do not execute expired side effects; audit status |
| Retry storm | Many clients time out simultaneously | Backoff/jitter/rate limits cap retry volume |
| Shutdown while active | Pod receives SIGTERM during active requests | Stop accepting new requests, drain or cancel per grace period |
| Unresponsive query | Database query exceeds timeout | Query is genuinely cancelled/cleaned up per engine mechanics |

### Fault injection

You can simulate latency, packet loss, DNS failures, connection pool limits, database locks, queue backlogs, or provider 5xx responses. Start in test environments under representative load; set abort criteria to avoid cascading outages. After each experiment, verify all of the following:

- Did the caller receive a response within the deadline?
- Did the backend continue doing useless work after the deadline?
- Were connections/threads/queues released?
- Did any side effect occur twice or get left half-done?
- Do logs/traces pinpoint the layer that exhausted the budget?

### Testing with a simulated clock

For unit tests, use a clock abstraction to test remaining/expired deadlines without waiting in real time. Test cases where the deadline expired before calling a dependency, very little deadline remains, retries lack sufficient budget, cancellation happens mid-step, and races between cancellation and commit. In integration tests, still verify that frameworks/clients/databases genuinely react as expected.

## 15. Common mistakes

1. **Per-layer timeouts without an end-to-end deadline:** each layer waits cumulatively for far too long.
2. **Retries resetting timeouts:** each retry receives a fresh full budget, stretching requests and amplifying load.
3. **Raising timeouts to hide errors:** masks overload and holds connections/threads longer.
4. **Setting timeouts too low around p50:** valid requests get cut off in the latency tail.
5. **Not propagating cancellation:** caller expires while downstream layers keep running.
6. **Assuming client disconnect automatically stops server work:** proxies/frameworks may not propagate the signal to workers.
7. **Treating Future.cancel as a rollback:** tasks may not stop immediately; committed side effects are not undone.
8. **Cancelling background jobs on HTTP disconnect:** accepted jobs need their own lifecycle.
9. **Retrying write operations with a new key:** can create duplicate charges or bookings.
10. **Failing to distinguish pre-send timeouts from post-commit timeouts:** mishandles business state.
11. **Ignoring pool wait and queue wait:** looking only at query execution time misses real bottlenecks.
12. **Inconsistent status codes:** callers cannot tell whether to retry, poll, or stop.
13. **Failing to record late outcomes:** backend finishes after the deadline, but nobody knows.
14. **Lack of testing under load:** timeouts/cancellation work in single-request tests but fail under concurrency.

## 16. Practice exercise and guided answers

A product-aggregation API has a **1,200 ms** deadline. The gateway takes 100 ms, internal processing needs 150 ms, leaving the rest for dependencies. The API calls Catalog in 300 ms, Pricing in 400 ms, and Recommendation in 350 ms. The three calls run **in parallel**. An additional 100 ms is needed for serialization and returning the response.

### Question 1 — Do the dependencies fit within the deadline?

**Answer:** The slowest branch is 400 ms. Total estimate is \(100+150+400+100=750\) ms, leaving roughly 450 ms of headroom. However, queue/connection setup, tail latency, and variance must be accounted for; each dependency's timeout must be capped by the remaining deadline.

### Question 2 — Recommendation fails after 250 ms while Catalog/Pricing are still running. What should happen?

**Guided answer:** If recommendation is a secondary feature with a valid fallback, drop the recommendation branch and return data from Catalog/Pricing; send cancellation to any remaining branch only if its result is no longer needed. Do not fail the entire API because of a non-essential feature.

### Question 3 — What if the three dependencies were called sequentially?

**Answer:** Dependency total is \(300+400+350=1,050\) ms. Adding gateway, processing, and serialization: \(100+150+1,050+100=1,400\) ms, exceeding the 1,200 ms deadline. You must change ordering/parallelization, reduce work, or define fallbacks.

### Question 4 — Client calls the create-payment API and gets a timeout. Can payment be assumed failed?

**Answer:** No. The server/provider may have already committed. Retain the idempotency key, store an unknown status, and reconcile; any retry must reuse the same key per contract.

### Question 5 — Client cancels a report-download request after the API returned 202 and queued the job. Should the job be cancelled?

**Answer:** Not automatically. An accepted job has its own lifecycle. Cancel only on an explicit cancel command when state permits; the job checks cancellation at safe checkpoints and cleans up temporary files/outputs properly.

### Question 6 — Why is an HTTP client timeout alone insufficient to protect a database?

**Answer:** Drivers/queries may continue executing if the HTTP timeout merely stops the caller from waiting. Configure query/statement/transaction timeouts, cancel statements via the driver, verify queries actually terminate, and release connections properly.

## 17. API review checklist

- Have end-to-end SLOs and deadlines been defined for each critical journey?
- Are connect, pool wait, read, query, and execution timeouts distinguished?
- Do layers receive the original deadline/remaining budget instead of inventing fresh budgets?
- Is there a server-side maximum request duration cap?
- Do retries have limits, backoff, jitter, budgets, and proper idempotency?
- Do client disconnects/deadlines propagate cancellation to cancellable tasks?
- Do asynchronous jobs have their own lifecycle, expiry, and cancellation policy?
- Do transactions with unknown outcomes have pending/unknown states and reconciliation mechanisms?
- Do status codes/error contracts guide callers to retry, look up status, or stop?
- Are metrics/traces collected for timeout phases, cancellation lag, late results, and retries?
- Have slow dependencies, client disconnects, long-running queries, and post-commit lost responses been tested?
- Are runbooks and owners defined for rising deadline exceeded or unknown operation counts?

At the end of a review, verify **how much time each layer has left, which work gets stopped, which side effects need protection, and how the system handles unknown outcomes**. Timeouts bound waiting; deadlines keep the whole journey within budget; cancellation frees work that is no longer needed. These three mechanisms only truly help when designed and measured as one cohesive contract across layers.

## 18. Well-Architected assessment

| Pillar | Review questions | Evidence |
| --- | --- | --- |
| **Reliability** | Can slow or disconnected dependencies exhaust resources and trigger cascading failures? | Timeout budgets, retry limits, cancellation tests, SLO/error budgets |
| **Security** | Can callers spoof deadlines/headers to hold resources? Do logs expose sensitive data? | Server-side caps, authentication, authorization, logging policy |
| **Performance** | How are tail latency, connection pools, queue waits, and fan-out controlled? | p95/p99, in-flight metrics, pool wait, dependency tracing |
| **Cost optimization** | Does wasted work after caller timeouts keep burning CPU, connections, and money? | Late-work rate, cancellation lag, compute/operation |
| **Operational excellence** | Can on-call teams pinpoint which layer blew the deadline and resolve unknown operations? | Dashboards, correlation IDs, runbooks, reconciliation |
| **Sustainability** | Do workloads keep consuming resources after they no longer deliver value? | Cancellation effectiveness, autoscaling, and capacity utilization |

Timeouts and cancellation are part of the contract between components. They must be designed alongside retries, idempotency, transactions, and observability; configuring a single number on an API gateway is not enough to prove a system can withstand failures.
