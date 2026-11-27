# Choosing Deadlines by RPC Type

You should not use the same deadline for every RPC. A unary call typically completes after one request and one response; client streaming may upload many chunks; server streaming may emit a large result set or hold a long-lived subscription; bidirectional streaming may maintain an interactive two-way session. Each type has a different lifetime, data rate, and recovery model.

In **Spring gRPC**, deadlines are set on the gRPC Java stub and apply to the **entire RPC**. The right approach is to start from the SLA or the wait time the user accepts, measure actual latency/throughput, and then allocate budgets by RPC type and downstream services. For long-lived streams, explicitly define session lifetimes and reconnection policies; never leave a stream waiting indefinitely simply because someone forgot to set a deadline.

## 1. General principle: budget according to call behavior

A deadline is the end timestamp for the entire RPC, not server processing time alone. The budget can be consumed by channel/resource wait, request transmission, queuing, business processing, downstream calls, and response transmission.

You can start with an allocation formula:

\[
D_{\text{rpc}} \leq D_{\text{caller}} - D_{\text{overhead}}
\]

Where:

- **D_rpc** is the budget allocated to the RPC being designed.
- **D_caller** is the time the caller or SLA grants for the overall operation.
- **D_overhead** is headroom for gateways, queues, post-RPC processing, and returning the result to the caller.

If a service calls downstream, the child budget must fit within the parent request's remaining time. Do not grant the full initial timeout again at each hop.

Do not choose a deadline based solely on average latency. Look at p95/p99 under valid load, variance under high load, request/response sizes, queue wait times, and required headroom. A deadline that is too short causes false failures; one that is too long holds resources longer when the system runs into trouble.

## 2. Deadline selection table by RPC type

| RPC Type | Timing Characteristics | How to Choose the Deadline |
| --- | --- | --- |
| **Unary** | One request, one response; typically relatively short processing | Based on p95/p99 latency, queue/network time, and operation SLA |
| **Client streaming** | Many request messages, one final response | Account for transmitting all data, processing, durable write, and returning acknowledgement |
| **Finite server streaming** | One request, many responses, then ends | Account for querying, emitting all results, and client consumption rate |
| **Server streaming subscription** | One subscription request; stream may stay open long | Use a finite session lifetime or intentional exception with reconnect/cursor |
| **Bidirectional streaming** | Interleaved two-way send/receive within a session | Define session limit, idle timeout, heartbeat, and resume capability |

Cardinality alone does not determine how long an RPC should live. A server-streaming export of a few thousand rows may finish in seconds; a server-streaming event subscription may need to run for hours. Base the decision on **business semantics and session lifecycle**, not merely on the word stream.

## 3. Unary: short, clear, and measurable budgets

Unary fits queries or commands with a single result. RPC time typically consists of:

1. Client sends the request and waits for the server to accept it.
2. Server authenticates, validates conditions, and runs business logic.
3. Server calls the database or downstream services if needed.
4. Server serializes and returns the response.

Choose the deadline according to the operation's SLA and observed latency percentiles. Example:

~~~java
GetCustomerResponse response = customerStub
    .withDeadlineAfter(450, TimeUnit.MILLISECONDS)
    .getCustomer(request);
~~~

450 ms is only an illustrative number. For fast reads, the budget can be short; transactional commands need enough time to validate, commit, and return the result. Do not set a server-side timeout equal to the client's full deadline if the request already consumed part of the budget in transit or in queues.

For commands with side effects, a timeout does not prove the server did not commit. Use an idempotency key or operation ID so the client can safely retry or query status.

## 4. Client streaming: include upload and processing time

Client streaming is commonly used when the client sends multiple messages, such as chunked file uploads, batch imports, or sensor telemetry. The deadline covers the **entire stream**, from starting the RPC until the server returns the final response.

The budget must account for:

- Time to establish the RPC and send chunks.
- Total payload size and minimum acceptable throughput.
- Time for the server to validate and process each chunk.
- Time for durable persistence or commit.
- Time to build and send the final acknowledgement.

Initial estimate for transfer time:

\[
T_{\text{upload}} \approx
\frac{\text{payload bytes}}{\text{minimum acceptable bytes/second}}
\]

Then add processing time and headroom. For example, if a client sends an 80 MB file over a link with 8 MB/s minimum throughput, transfer time alone is roughly 10 seconds; a 2-second deadline is unrealistic.

~~~java
var uploadStub = fileServiceStub
    .withDeadlineAfter(30, TimeUnit.SECONDS);

StreamObserver<FileChunk> requestObserver =
    uploadStub.uploadFile(uploadResponseObserver);
~~~

30 seconds is only an example. You must also bound file size, chunk size, send rate, queues, and processing time. Do not extend the deadline after each chunk; if uploads need longer, design an upload session with an ID, sequence numbers, and resume so the client continues from the last acknowledged chunk.

If the deadline expires mid-upload, the server may have already received and saved part of the data. Use an upload ID, chunk sequence, and deduplication so retries do not write duplicates or corrupt upload state.

## 5. Finite server streaming: account for emitting all results

Server streaming can return a large result set across multiple messages, such as exporting reports or loading lists of records. Even though the response spans many messages, the RPC still has one overall deadline.

Completion time depends on:

- Time to query or prepare the data.
- Number and size of response messages.
- Server emission rate and client consumption capacity.
- Backpressure, network latency, and client-side processing time.

~~~java
var exportStub = reportServiceStub
    .withDeadlineAfter(45, TimeUnit.SECONDS);

exportStub.exportReport(
    exportRequest,
    reportResponseObserver);
~~~

45 seconds is an example for a finite export, not a default value. If the result set is unbounded or clients can read very slowly, a longer deadline does not fix the root cause. You need pagination, record/byte limits, backpressure, and per-batch processing time limits.

The client may have received partial results before the deadline expires. If results need to continue after an error, responses should carry a sequence/cursor or export ID so the client knows what was received and how to resume.

## 6. Server streaming subscription: session limits and reconnect

An event subscription may be designed to stay open for a long time. Setting a short unary-like deadline forces frequent reconnects; having no deadline and no lifecycle limits lets the stream hold subscriptions, queues, and server resources indefinitely.

An appropriate policy typically includes:

- **Session lifetime:** maximum duration for a stream session, chosen according to the client's reconnection capability.
- **Idle timeout:** maximum duration without messages or meaningful activity before closing the stream.
- **Heartbeat:** a rate-limited signal to detect dead connections or inactive consumers.
- **Cursor/sequence:** the last position the client received so it can reconnect and resume.
- **Cancellation cleanup:** stop the producer, close the subscription, and release queues.

If the business genuinely requires a subscription with no absolute time limit, it must be an explicitly configured and monitored exception. Even then, idle timeouts, concurrent stream limits, backpressure, leases, or reconnection must still govern the lifecycle.

## 7. Bidirectional streaming: managing a two-way session

Bidirectional streaming fits interactive sessions, such as a client sending commands while the server returns interleaved results/events. Both directions belong to the same RPC and share the overall deadline.

When choosing a deadline, determine:

1. Does the session have a maximum lifetime, or can it be renewed by lease?
2. How long without messages makes the session idle?
3. Are heartbeats needed to detect a disconnected peer?
4. Which session ID and sequence can the client use to resume?
5. When the deadline expires, how is the state of already-sent commands determined?

~~~java
var sessionStub = collaborationServiceStub
    .withDeadlineAfter(10, TimeUnit.MINUTES);

StreamObserver<ClientMessage> outbound =
    sessionStub.openSession(inboundObserver);
~~~

10 minutes merely illustrates a bounded session. Do not stretch deadlines indefinitely just to avoid reconnecting. For long sessions, split them into finite sessions, store session ID/cursor state, and reconnect when a session ends. An idle timeout is still needed separately because a session may go silent well before the overall deadline expires.

## 8. Distinguishing deadline, idle timeout, and keepalive

These three mechanisms solve three different problems:

| Mechanism | What Does It Bound? | Example Purpose |
| --- | --- | --- |
| **RPC deadline** | Total lifetime of an RPC | A unary call must return a result within budget |
| **Idle timeout** | Inactivity period of a session | Close a subscription no longer sending/receiving data |
| **HTTP/2 keepalive** | Liveness of the transport connection | Detect unresponsive connections or peers |

Keepalive does not replace an RPC deadline; a live connection does not mean a business request is making progress. Nor does an idle timeout replace the overall deadline: a stream can keep sending heartbeats yet live beyond business limits. Combine them according to their respective purposes.

## 9. Setting child deadlines from remaining budget

In nested calls, a downstream deadline must not exceed the parent RPC's remaining deadline. You can set a shorter child limit and reserve headroom for the parent service:

~~~java
Deadline parent = Context.current().getDeadline();
long childLimit = TimeUnit.MILLISECONDS.toNanos(250);
long responseReserve = TimeUnit.MILLISECONDS.toNanos(40);

if (parent != null) {
    long remaining = parent.timeRemaining(TimeUnit.NANOSECONDS);
    childLimit = Math.min(childLimit, remaining - responseReserve);
}

if (childLimit <= 0) {
    throw Status.DEADLINE_EXCEEDED
        .withDescription("insufficient downstream budget")
        .asRuntimeException();
}

var boundedStub = inventoryStub.withDeadlineAfter(
    childLimit, TimeUnit.NANOSECONDS);
InventoryResponse result =
    boundedStub.checkAvailability(request);
~~~

250 ms and 40 ms are examples. For downstream streaming, also account for session lifetime or switch to a cursor-based session model; do not mechanically apply a short unary budget to a stream that needs continuous data delivery.

## 10. Handling timeouts and retries by RPC type

Deadline expiration typically results in **DEADLINE_EXCEEDED**, yet does not prove the server has not processed the data:

- **Unary read:** can usually be retried in a controlled way if the operation is safe.
- **Unary command:** use an idempotency key or query the operation ID before resending.
- **Client streaming:** use an upload ID, sequence numbers, and per-chunk acknowledgements; do not blindly resend the entire upload.
- **Server streaming:** store the last processed cursor/sequence to resume; handle duplicates safely if delivery may repeat.
- **Bidirectional streaming:** use a session ID, message ID, and acknowledgement state for each command/event.

Retries must fit within the caller's overall deadline. Do not start a retry attempt with a budget longer than the remaining time.

## 11. Testing deadlines by cardinality and lifecycle

Each RPC type needs dedicated test scenarios:

| Type | Scenarios to Verify |
| --- | --- |
| Unary | Completes on time; slow processing; status when deadline expires |
| Client streaming | Full data upload; expiration mid-chunk; resume without duplicate writes |
| Finite server streaming | Emits all results; slow client; expiration after partial responses |
| Server streaming subscription | Idle timeout; session lifetime; cursor-based reconnect; cleanup on cancel |
| Bidirectional streaming | Both directions active; one side silent; session expiration; reconnect and deduplication |

Use in-process tests or a controllable mock server to test deadlines and cancellation. For streams, use latches/futures to simulate slow consumers or pause at specific chunks instead of relying on long sleeps. Spring integration tests should confirm the deadline policy is actually applied to the application's stubs/channels.

## 12. Choosing and tuning deadlines in production

Track by full method name and RPC type:

- p50/p95/p99 latency and **DEADLINE_EXCEEDED** rate.
- Queue, server processing, and downstream durations.
- For client streaming: bytes received, throughput, chunk processing time, and interrupted uploads.
- For server streaming: messages/bytes emitted, readiness wait time, and stream age.
- For bidirectional: session lifetime, idle duration, heartbeats, and reconnect counts.
- Tasks still running after cancellation and cleanup duration.

When timeouts increase, find which layer is consuming the budget before raising the deadline. When long streams drop frequently, inspect session lifetime and reconnection. When streams fail to terminate and resource usage climbs, inspect idle timeouts, backpressure, and cancellation cleanup.

## 13. Summary and self-check

Choose deadlines according to **the lifetime and data exchange pattern of each RPC type**:

- Unary: short budget based on latency and SLA.
- Client streaming: include upload, processing, and final acknowledgement.
- Finite server streaming: include emitting all results; long subscriptions need session lifetimes and resume.
- Bidirectional streaming: manage session lifetime, idle timeout, heartbeat, and reconnect.

A deadline is the overall limit of an RPC; idle timeout bounds inactivity periods; keepalive checks transport liveness. They complement one another and cannot substitute for one another.

Self-check:

1. Why must a client streaming deadline include both upload time and chunk processing time?
2. How does a finite server streaming export differ from a long-lived event subscription when choosing a deadline?
3. Why does sending continuous heartbeats not replace a session lifetime?
4. When a bidirectional stream hits its deadline, which IDs/sequences are needed to reconnect safely?
5. Why must nested calls use the parent request's remaining budget?

Tailoring deadlines to each RPC type helps Spring gRPC balance responsiveness, reliability, and server resources, while establishing a clear foundation for cancellation, retries, and reconnection.
