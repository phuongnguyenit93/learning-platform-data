# When server streaming is the right fit

## 1. Start from business needs, not from the `stream` keyword

In the **SPRING_GRPC** module, learners build gRPC services in the Spring ecosystem: declaring **Protocol Buffers** contracts, generating Java code, implementing clients/servers for unary and streaming RPCs, and handling metadata, deadlines, statuses, interceptors, TLS, integration testing, and reliability monitoring. In the **Server streaming** chapter, the key design question is: **when should a single request produce a stream of multiple responses instead of returning exactly one response?**

A **server streaming RPC** has the following message flow direction:

- The client sends **one request** to specify the task, dataset, or topic to watch.
- The server sends **zero, one, or more responses** over time, over the same RPC.
- The server terminates the RPC with a success status, an error status, or the RPC stops due to cancellation, deadline expiration, or connection loss.

In protobuf, the `stream` keyword is placed on the response side:

~~~proto
service ReportService {
  rpc WatchReport(WatchReportRequest) returns (stream ReportEvent);
}
~~~

For example: the client sends a `WatchReportRequest` containing a job ID, then receives sequential events "queued", "processed 20%", "processed 70%", "completed". The client can update the UI or process results as soon as each event arrives, rather than waiting until the entire job finishes.

What makes server streaming valuable is not just the **number of responses**, but **when each response becomes useful**. If the receiver only uses the data after all results have arrived, switching to streaming may bring no benefit.

## 2. Five signs you should choose server streaming

### 2.1. One request is enough to describe the entire session

After the initial request, the server has enough context to continue emitting data on its own: the job ID to watch, log filter criteria, time range to scan, or product SKU to receive updates for.

Example:

~~~text
Client: WatchJob(job_id = "job-731")
Server: QUEUED
Server: RUNNING, 15%
Server: RUNNING, 55%
Server: SUCCEEDED, 100%
Server: End of RPC
~~~

The client does not need to send additional messages for the server to move to the next step. Conversely, if the client must continuously send commands like "pause", "change filter", or "resume" within the **same RPC session**, bidirectional streaming may be more suitable. A new independent request can still be sent via another RPC, but that differs from continuous two-way exchange on the same stream.

### 2.2. Data arrives incrementally and each piece is immediately useful

Common cases:

- **Progress tracking:** number of processed records, task phase, raised warnings.
- **Batched results:** scanning many records and returning batches progressively as each becomes ready.
- **Event watching:** order status updates, inventory changes, or new log entries.
- **Long computations:** streaming completed chunks of results to the client.

Suppose the server takes 30 seconds to process 3,000 records, but can produce the first 100 records after 1 second. With a unary call returning the entire list, the client usually receives the payload only after the server finishes constructing the single response. With server streaming, the client can start processing the first batch after about 1 second (timings are illustrative only).

We need to distinguish two metrics:

| Metric | Unary returning full list | Server streaming |
|---|---|---|
| Time to first data | Usually after full result is ready | Potentially as soon as the first part is ready |
| Time to **complete** result | After one response | After final message and terminal status |
| Memory held on server | Potentially large if assembling full list | Potentially small with bounded processing and buffers |
| Lifecycle management complexity | Lower | Higher: flow control, cancellation, timeouts, partial data |

**Streaming does not automatically guarantee faster total duration.** The server still performs the same amount of processing; the benefit usually lies in lower latency to the first result, pipelined processing, and reduced need to buffer the entire dataset in memory.

### 2.3. Unfixed message count or results generated over a long period

A query might return 2, 20, or 2,000 results; or new events might appear at any time. Server streaming lets the client process each message without knowing the total message count upfront.

There are two models to distinguish:

| Model | Lifecycle | Example | Termination condition |
|---|---|---|---|
| **Finite stream** | Progressively returns a bounded result set | Reading 10,000 records, emitting processing steps | Data exhausted, task completed |
| **Watch stream** | Waits for new events, may run long | Watching logs or progress of a running job | Client cancels, job finishes, deadline expires, or server closes stream |

For long-lived watch streams, you must account for open connection costs and recovery strategies. For finite datasets, you must also evaluate snapshot consistency, data limits, and whether pagination is a better fit.

### 2.4. The client genuinely needs continuous reception

A backend system consuming events and updating state in real time can benefit from server streaming. However, if a UI opens a report page once and only renders once all numbers are available, unary is easier to operate.

For instance, ask: **"If the first message arrives 10 seconds earlier while the final result arrives at the same time, does the user gain a clear benefit?"** If not, that is a sign to reconsider.

### 2.5. Infrastructure and clients can sustain HTTP/2 RPCs

gRPC server streaming relies on gRPC connections and HTTP/2 mechanisms, so all hops must support incremental message delivery, deadlines, and cancellation. Java backend-to-Java backend communication is usually a favorable case. For browsers, mobile devices, or traffic passing through gateways/proxies, verify support for **gRPC-Web, streaming proxies, timeouts, and buffering**; do not assume all clients and proxies behave like a native Java gRPC client.

If the primary channel is a web browser and the requirement is strictly one-way event delivery, **Server-Sent Events (SSE)** over HTTP may be more convenient. If continuous two-way exchange in a browser is needed, **WebSocket** is worth evaluating.

## 3. Decision tree for choosing a communication style

~~~mermaid
flowchart TD
    A["Start: a business operation needs data"] --> B{"Does the client only need one final result?"}
    B -- "Yes" --> U["Unary RPC"]
    B -- "No" --> C{"Does the client need to send multiple messages in the same RPC?"}
    C -- "Yes" --> D{"Does the server also need to respond incrementally?"}
    D -- "Yes" --> BI["Bidirectional streaming"]
    D -- "No" --> CI["Client streaming"]
    C -- "No" --> E{"Is data valuable as it arrives piece by piece?"}
    E -- "No" --> F["Unary / pagination depending on needs"]
    E -- "Yes" --> G{"Need durable history and replay after disconnect?"}
    G -- "No" --> SS["Server streaming"]
    G -- "Yes" --> H["Design history/cursor storage; can use server streaming as delivery channel"]
~~~

The decision tree yields a **candidate**, not a final implementation decision. You must further evaluate update frequency, concurrent client scale, recoverability, security, and infrastructure requirements.

| Option | Use when | Do not choose merely because |
|---|---|---|
| **Unary RPC** | One request, one final result; error and completion handling are relatively simple | Every method in the system currently uses unary |
| **Unary with `repeated`** | A small list that needs to be viewed/returned all at once | You want to call a list "streaming" even though there is only one message |
| **Paginated unary** | Client controls the next page, needs random access, caching, or page-based resume | Data having many elements forces you to use streaming |
| **Server streaming** | One request, useful results sent incrementally, client only receives | You want to save time without any actual early data available |
| **Client streaming** | Client sends multiple messages, server aggregates into one result | Server needs to return multiple updates for one request |
| **Bidirectional streaming** | Both sides actively send multiple messages within one RPC | Only the server needs to push one-way updates |
| **Message broker + consumer** | Need durable storage, replay, producer-consumer decoupling, large fan-out | You only need to push a few transient updates within one RPC |

**Important comparison:** `repeated ReportEvent events = 1;` inside a unary message is *not* the same as `returns (stream ReportEvent)`. A `repeated` field causes the client to receive **one** response containing a list; server streaming causes the client to receive **multiple** distinct responses as progress unfolds.

## 4. Real-world use cases

### Case A — Tracking progress of a long-running job

A reporting system processes data over tens of seconds to several minutes. The client needs to know whether the job is still running, failing, or completed.

**Good fit:** once a job ID exists, the client can send one `WatchReport(job_id)`; the server emits progress without the client having to poll continuously. Step-by-step data provides immediate value for the UI, operations, and error monitoring.

**Point to note:** if the job must keep running even when the user closes the app, separate the **job creation command** (unary) from the **watch stream** (server streaming). Closing the stream should not automatically cancel the background job unless the product requires it. This is a business lifecycle decision.

### Case B — Progressively returning large query results

A search or event-scanning service returns thousands of records that can be processed one by one as they arrive.

**Good fit:** the client consumes sequentially and does not need to load the entire dataset into memory. Streaming can allow the first result to appear quickly and reduce buffering if the server genuinely reads data via cursors/chunks.

**Consider paginated unary:** if users need to jump to page 8, go back to page 3, share page links, or maintain per-page caches. Cursor-based pagination is also often more convenient for retries and resuming. Streaming does not automatically solve snapshot consistency when source data changes mid-read.

### Case C — Streaming logs, audits, or state changes

An internal tool needs to tail a service's logs during incident investigation.

**Good fit:** the initial request contains filters, and the server sends each log entry as it appears. The client can display them immediately instead of polling every second.

**Alternative design consideration:** if the requirement is querying logs from months ago with search and durable retention, you need a log query/storage system. Streaming is only the delivery pipe to the viewer; the RPC itself is not a log store.

### Case D — Real-time status updates

A backend application needs to receive order updates, inventory levels, or device metrics.

**Good fit:** a subscription with clear filters where each independent update is useful and latency matters.

**Re-evaluate when:** there are millions of subscribers, a requirement to replay all events after going offline, or consumption by many disparate systems. In that case, you may need pub/sub or a broker with retention, then use gRPC streaming as a delivery layer for certain clients.

### Case E — Server-generated incremental responses

An inference or text-processing engine generates chunks of output over time. The client wants to render them as each chunk is produced.

**Good fit:** users see content early and can react/cancel immediately, while the client does not need to send extra messages in the same RPC.

**Not automatically suitable when:** the output must be validated as a whole before use (such as money transfers, approvals, or data requiring atomicity). For those operations, the server should return a final decision with a clear status; progress updates, if needed, should be a secondary channel.

## 5. Design example: watching a report generation task

Suppose a Spring gRPC service allows starting a long report and watching its progress. Choose two separate RPCs:

1. Unary `StartReport`: starts the background job and returns `job_id`.
2. Server streaming `WatchReport`: takes `job_id` and sends status updates in order until the job ends or the subscription is closed.

This design allows the job to live independently of a single observation connection's lifetime.

~~~mermaid
sequenceDiagram
    participant C as Java client
    participant G as Spring gRPC service
    participant J as Report job worker
    C->>G: StartReport(input)
    G->>J: Create job, save job_id
    G-->>C: StartReportReply(job_id)
    C->>G: WatchReport(job_id, after_sequence)
    G-->>C: ReportEvent(1, QUEUED, 0%)
    J-->>G: Progress 25%
    G-->>C: ReportEvent(2, RUNNING, 25%)
    J-->>G: Completed
    G-->>C: ReportEvent(3, SUCCEEDED, 100%)
    G-->>C: onCompleted / gRPC OK
~~~

### 5.1. Defining the contract

~~~proto
syntax = "proto3";

package report.v1;

option java_multiple_files = true;
option java_package = "example.report.rpc";

service ReportService {
  rpc StartReport(StartReportRequest) returns (StartReportReply);
  rpc WatchReport(WatchReportRequest) returns (stream ReportEvent);
}

message StartReportRequest {
  string report_type = 1;
}

message StartReportReply {
  string job_id = 1;
}

message WatchReportRequest {
  string job_id = 1;
  // Fetch only events with sequence greater than this value.
  // Server MUST support history storage/retrieval if it advertises resume capability.
  int64 after_sequence = 2;
}

enum ReportPhase {
  REPORT_PHASE_UNSPECIFIED = 0;
  QUEUED = 1;
  RUNNING = 2;
  SUCCEEDED = 3;
  FAILED = 4;
}

message ReportEvent {
  string job_id = 1;
  int64 sequence = 2;   // Monotonically increasing per job.
  ReportPhase phase = 3;
  int32 percent = 4;    // 0..100 if estimable.
  string message = 5;
}
~~~

When using Protocol Buffers, the `ReportServiceGrpc` class and message classes are generated from the proto via `protoc` and the build's gRPC Java plugin. The service implementation is integrated with Spring according to the bean/service registration mechanism of the Spring gRPC library in use.

Rationale behind the contract decisions:

- `job_id` decouples watching from starting, while also providing a key for authorization checks.
- `sequence` enables the client to detect duplicates, order events, and spot gaps after reconnecting.
- `after_sequence` is a **commitment you must implement**, not a built-in capability of gRPC. The server needs to retain history long enough, read records after the checkpoint, and bridge smoothly into the live event stream without creating handoff gaps.
- `FAILED` is a **business state** of the job. If the server can normally deliver the failure notification, it can send the `FAILED` event and terminate the RPC with gRPC `OK`. Conversely, if the RPC itself breaks (unable to reach datastore, unauthorized to view job, system failure), use an appropriate gRPC status such as `UNAVAILABLE`, `PERMISSION_DENIED`, or `INTERNAL`.

### 5.2. Consuming the stream from a Java client

The snippet below assumes the application already has a `ManagedChannel channel` and `jobId`, and that Java classes have been generated from the proto. The example uses the blocking stub to focus on stream semantics:

~~~java
long lastProcessedSequence = 0L; // Restore from saved checkpoint if available.

WatchReportRequest request = WatchReportRequest.newBuilder()
        .setJobId(jobId)
        .setAfterSequence(lastProcessedSequence)
        .build();

var updates = ReportServiceGrpc.newBlockingStub(channel)
        .withDeadlineAfter(60, TimeUnit.SECONDS)
        .watchReport(request);

try {
    while (updates.hasNext()) {
        ReportEvent event = updates.next();

        if (event.getSequence() <= lastProcessedSequence) {
            continue; // Deduplicate replayed records.
        }

        System.out.printf("[%s] #%d: %s (%d%%)%n",
                event.getJobId(),
                event.getSequence(),
                event.getPhase(),
                event.getPercent());

        // In a real system, persist the checkpoint after successful processing.
        lastProcessedSequence = event.getSequence();
    }
} catch (StatusRuntimeException error) {
    System.err.println("WatchReport failed: " + error.getStatus());
    // After an error, can retry from checkpoint if the contract supports replay.
}
~~~

Types to import in this context: `WatchReportRequest`, `ReportEvent`, `ReportServiceGrpc`, `TimeUnit`, and `StatusRuntimeException`. The channel should be Spring-managed/reused, especially when multiple RPCs share a connection.

**Important:** the 60-second deadline in the example applies to the **entire RPC**, not reset after each event. Longer-running jobs may need appropriate timeouts, a reconnect mechanism from a checkpoint, and retry limits with backoff. If the client needs to control mid-stream cancellation, use the gRPC cancellation API; cancelling `WatchReport` does not mean deleting the job in this design.

### 5.3. Responsibilities of the Spring gRPC server

The server must perform the following steps in the appropriate business order:

1. Validate `job_id`, authenticate the caller via metadata/interceptors, and authorize access to the job.
2. Check whether the job exists and whether the history store still retains enough data to satisfy `after_sequence`; if not, return an error status or provide a snapshot path per contract.
3. Bridge **reading history** with **subscribing to new events**, avoiding missed events in the gap between the two operations.
4. Send messages with `StreamObserver.onNext(...)` in strict order, without concurrent writes to the same observer from uncoordinated threads.
5. When the job reaches a terminal state, send the final business event and call `onCompleted()` once. When the server encounters an RPC error, call `onError(...)` with the appropriate `Status`.
6. When the client cancels, the deadline expires, or the connection drops, cancel subscriptions, timers, and per-RPC buffers; decide whether to keep or cancel the **background job** based on the designed business policy.

When multiple workers emit events simultaneously, an ordering/sequence-assignment mechanism is needed at the data layer. A gRPC stream preserves **the order of messages sent on that stream**, but it does not establish a global order for events arriving from multiple sources, nor does it persist messages lost during a connection interruption.

## 6. When **not** to choose server streaming?

### 6.1. Only one short result that must be returned whole

Examples include `GetProductById`, verifying permissions, calculating tax for an order, or looking up a configuration. Unary has a simpler contract and is easier to invoke, retry, cache, and handle errors for.

### 6.2. The user controls each data fetch

Examples include a data grid with a "Next page" button, frequently changing filters, and the requirement to share URLs for specific pages. Paginated unary with a page token/cursor is usually a better fit than a long-lived stream. The client controls page size, cache context, and resumption point.

### 6.3. Durable history and replay for multiple consumer groups are needed

A streaming RPC only maintains a delivery pipe while the connection exists. If you must retain millions of events, replay by offset, support multiple consumer groups, handle offline clients, and enforce retention periods, use appropriate storage/broker infrastructure. Server streaming can still serve as a read API on top of that infrastructure, but it does not replace durable storage.

### 6.4. The client frequently sends updates in the same session

Examples include continuously sending device locations, updating filter settings mid-session, or two-way streaming control. If the client also produces multiple messages on the same RPC, consider bidirectional streaming. If only the client sends multiple messages and the server returns a single aggregated result, consider client streaming.

### 6.5. Partial results cannot be tolerated or there is no recovery strategy

Server streaming might send 9 messages and then fail with `UNAVAILABLE` on the 10th message. The client must distinguish **partially processed** from **RPC completed successfully**. If the business operation requires atomicity, full verification before applying results, or repetition has side effects, only use streaming if you have designed checkpoints, idempotency, transaction boundaries, and clear final outcome signaling.

## 7. Technical trade-offs to determine before implementation

### Flow control and backpressure

gRPC over HTTP/2 has flow control, but it is not an automatic mechanism protecting all application queues. A slow-reading client can still cause server buffers to grow if the producer writes faster than the transport rate.

On the Java gRPC server side, `ServerCallStreamObserver.isReady()` and `setOnReadyHandler(...)` let the application observe when the write path can accept more data. **Do not interpret `isReady() == false` as an unconditional license to drop data.** For best-effort logs, you may coalesce or drop old updates under an explicit policy; for event streams that must be complete, you need bounded queues, upstream backpressure, or a replay mechanism.

### Lifetime, deadlines, and cancellation

Every open stream consumes resources: RPC state, HTTP/2 stream, callbacks/subscriptions, buffers, and observability resources. A client can disappear on network change before the application notices the close event. The server should handle cancellation, deadlines, and cleanup on all exit paths. Set maximum lifetimes/idle timeouts appropriate for the business domain, while avoiding proxy configurations that prematurely kill all streams.

### Terminal messages and errors

Define clearly:

- Is "business completion" a **data event** or merely stream `onCompleted()`?
- Is "Job FAILED" a business failure reported via an event, or a gRPC error?
- When some messages are received and then the RPC fails, is the client allowed to use the data received so far?
- If the client retries, could old events be re-sent, and how does the client deduplicate them?

Without agreeing on these points, the two sides may interpret the same stream differently even though the proto is valid.

### Metadata, interceptors, TLS

Metadata carries caller identity, access tokens, correlation/trace IDs, and RPC-level control info; continuously changing events belong in the protobuf payload. With Spring gRPC, interceptors are typically appropriate for authentication, logging termination status codes, and measuring call duration. Long-lived streams need checks for token expiration, revoked permissions, sensitive data, and session termination policies.

TLS protects gRPC data on the network. Local plaintext examples used during development must not be copied verbatim to production. Verify the server certificate; if infrastructure requires it, implement mTLS. Authorization to view `job_id` must be verified per caller—do not assume anyone who knows the ID is allowed to watch it.

### Performance and scalability

Server streaming can reduce polling frequency but increases the number of concurrently open RPCs. Cost depends on event rate, message size, client count, buffering mechanism, event subscription mechanism, and network infrastructure. Do not spin up a dedicated busy-waiting thread per RPC in a system with thousands of subscriptions; use an appropriate executor, scheduler, or publisher system and bound resources.

## 8. How to measure whether this choice is effective?

To decide whether to use server streaming, build a small benchmark with near-realistic load comparing unary/polling and server streaming toward the same business goal.

| Metric | Question to answer |
|---|---|
| **Time to first response** | Does the client receive the first useful piece earlier? |
| **End-to-end completion** | Is total time to receive all results lengthened? |
| **Per-event latency** | When an event occurs, how long until the client sees it? |
| **Active RPCs / subscriptions** | How many open streams can each instance sustain? |
| **Memory / queue depth** | Do slow clients cause data accumulation? |
| **Rate of CANCELLED / DEADLINE_EXCEEDED / UNAVAILABLE** | Are streams closing due to users, timeouts, or infrastructure errors? |
| **Messages and bytes per RPC** | How much do traffic load and serialization cost increase? |
| **Retry, gap, duplicate rates** | How well do continuation and deduplication mechanisms perform? |

With Spring gRPC, metrics/tracing can be integrated via interceptors and the application's observability stack. When reporting reliability, separate **job FAILED** from **RPC error**: a business job that fails but is accurately reported by the server over the stream can still be a successful communication RPC.

## 9. Testing the assumptions behind choosing streaming

Beyond testing the proto, Java stub generation, and Spring gRPC wiring, verify the exact benefits used to justify streaming:

1. **Incremental emission:** create a data source with pauses between events; prove the client receives and processes the first event before the source produces the last event, rather than waiting to collect a list.
2. **Ordering:** send multiple events and verify `sequence` increments per contract; for concurrent sources, test the serialization mechanism.
3. **Proper termination:** test zero events, one event, multiple events, `SUCCEEDED` and `FAILED` jobs, and calling `onCompleted()` or `onError(...)` exactly once.
4. **Mid-stream interruption:** client cancels or deadline expires; verify subscriptions, timers, cursors, and per-RPC memory are released.
5. **Slow client:** throttle reading speed; verify memory and buffer limits do not grow unboundedly.
6. **Recovery:** disconnect after `sequence = 5`, reconnect with `after_sequence = 5`; verify no required events are lost and the client tolerates duplicates.
7. **Security:** prevent viewing another user's job, test missing/invalid auth metadata, TLS scenarios, and interceptors.
8. **Concurrent load:** measure many open streams and emission rates; monitor CPU, heap, threads, connections, latency, and error rates.

gRPC **in-process** testing is useful for verifying stubs, serialization, statuses, and message ordering. Integration tests that start the Spring context verify service registration, interceptor configuration, and dependencies. Real TLS, proxy, network cancellation, and timeout scenarios should be tested in an environment with the corresponding transport stack.

## 10. Pre-decision checklist

Before choosing `returns (stream Response)`, make sure you can answer:

- [ ] After the first request, does the server have enough data to emit subsequent responses on its own?
- [ ] Does the client gain a clear benefit from receiving the first message early or receiving updates over time?
- [ ] Can responses be processed individually, in order, and with clear completion rules?
- [ ] Have you defined when the stream ends, cancels, expires its deadline, and errors?
- [ ] Do you have a backpressure strategy and memory/resource limits for slow clients?
- [ ] If reconnect/replay is needed, do you have sequences, checkpoints, and durable storage?
- [ ] Can clients, gateways, and proxies pass gRPC streaming as required?
- [ ] Have you evaluated unary, pagination, SSE/WebSocket, or a broker based on real needs?
- [ ] Do you have plans for authentication, authorization, TLS, testing, and observability?

**Conclusion:** Server streaming is best suited when **one request leads to multiple useful results over time**, the client primarily receives, early rendering or processing creates value, and the system can manage long-lived connections alongside partial data. In Spring gRPC, the right choice lies not in adding `stream` to the proto, but in designing the complete contract, RPC lifecycle, data flow, recovery, and operations.
