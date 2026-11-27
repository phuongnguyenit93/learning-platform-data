# Differences between logical RPCs and network exchanges

## Learning objectives

After this lesson, you can:

- Distinguish a **logical RPC** at the application layer from a **network exchange** at the HTTP/2 and transport layers.
- Describe the relationship among generated stubs, ClientCall, attempts, HTTP/2 streams, frames, TCP connections, TLS records, and packets.
- Explain why one logical RPC can generate multiple network attempts, while one stream can carry multiple messages and multiple frames.
- Read request/response headers, DATA, and trailers of a unary or streaming RPC.
- Understand the impact of retries, deadlines, cancellation, and reconnection on attempt counts and the states observed on client and server.
- Design metrics, logs, and tracing so you do not miscount RPCs, streams, connections, and packets in Spring gRPC applications.

## 1. A logical RPC is the operation requested by the application

In **SPRING_GRPC**, a service contract defines methods such as `GetOrder` or `WatchOrder`. When Spring code invokes a generated stub, the application requests a **logical RPC**: a remote operation with a method, request, response or stream, deadline, metadata, and final outcome.

Example:

~~~java
GetOrderResponse response = orderStub
        .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
        .getOrder(
                GetOrderRequest.newBuilder()
                        .setOrderId("order-42")
                        .build());
~~~

From the application's perspective, this is one `GetOrder` call. The caller cares about the response or final error; it does not need to know whether the runtime had to resolve DNS, open a connection, send multiple HTTP/2 frames, or perform retries.

A logical RPC has these characteristics:

- Identified by service/method, such as **demo.orders.v1.OrderService/GetOrder**.
- Has request types and communication mode declared in Protocol Buffers.
- Has call options such as deadline, credentials, and compressor.
- Has a start/end lifecycle at the gRPC API: response completion or call termination with a status.
- May traverse resolvers, load balancers, proxies, and multiple transport components.

A logical RPC is an API/application-layer concept. It is not synonymous with a TCP connection, an HTTP/2 frame, or a network packet.

## 2. A network exchange is how the RPC is transported

A **network exchange** is the actual exchange between client and server across protocol layers. With native gRPC over HTTP/2, one attempt is typically represented by one HTTP/2 stream on an HTTP/2 connection.

~~~mermaid
flowchart TB
    A["Spring application call"]
    B["Generated stub"]
    C["Logical RPC / ClientCall"]
    D["Attempt 1"]
    E["HTTP/2 stream"]
    F["HTTP/2 HEADERS + DATA + trailers"]
    G["TCP connection"]
    H["TLS records"]
    I["IP packets / network"]
    A --> B --> C --> D --> E --> F --> G --> H --> I
~~~

The layers do not have a one-to-one mapping:

| Layer | Unit | Meaning |
| --- | --- | --- |
| Application | **Logical RPC** | A single operation requested by the caller |
| gRPC runtime | **ClientCall / attempt** | Manages the call and one execution attempt |
| HTTP/2 | **Stream** | Logical bidirectional channel for one attempt |
| HTTP/2 | **Frame** | HEADERS, DATA, RST_STREAM, WINDOW_UPDATE... |
| Transport | **TCP connection** | Byte-stream connection capable of carrying many HTTP/2 streams |
| Security | **TLS record** | TLS encryption unit |
| Network | **IP packet** | IP-layer transmission unit |

Therefore, you cannot conclude that one RPC equals one connection or one packet. One connection can carry hundreds of concurrent RPCs; one RPC can produce many frames; and frames and TLS records can be split or coalesced into packets by the transport.


## 3. Relationship between logical RPC, attempt, and HTTP/2 stream

For a call without retries, the typical pattern is:

~~~text
One call to generated stub
    |
    +-- one logical RPC
           |
           +-- one attempt
                  |
                  +-- one HTTP/2 stream
                         |
                         +-- HEADERS
                         +-- one or more DATA frames
                         +-- trailing HEADERS
~~~

An **attempt** is one try by the runtime to execute the logical RPC. Normally, one attempt uses one HTTP/2 stream. When a gRPC retry policy creates a new attempt, the runtime opens a new stream; the old stream may have finished or been cancelled depending on the situation.

~~~text
One logical RPC: GetOrder(order-42)
    |
    +-- Attempt 1: stream 17 on connection A
    |      +-- upstream reset / UNAVAILABLE
    |
    +-- Attempt 2: stream 23 on connection A or B
           +-- grpc-status: 0

Caller receives one final outcome for the logical RPC.
~~~

This is an example of internal retries by the gRPC runtime. The application still calls the stub once and receives one final outcome. However, the server or proxy may observe multiple attempts, depending on how far the first attempt got and whether the retry policy permits retrying.

Distinguish two cases:

- **Internal gRPC retry:** the runtime makes additional attempts within the same logical call according to retry/service config and commitment rules.
- **Application retry:** application code calls the stub method again after receiving an error. That is a new logical RPC, potentially with its own deadline and trace.

Not every error is retried. Once response headers are received or the call is committed under the runtime's retry rules, further retries are no longer performed. For streaming RPCs that have already exchanged messages, never assume the runtime can replay the entire stream like a fresh unary request.

## 4. What does an HTTP/2 stream contain?

Native gRPC typically uses HTTP/2 POST. An attempt carries request headers, request message data, and response completion:

~~~text
Client -> Server
  HEADERS
    :method: POST
    :scheme: https
    :authority: orders.example.com
    :path: /demo.orders.v1.OrderService/GetOrder
    content-type: application/grpc
    te: trailers
    grpc-timeout: 800m

  DATA
    [compressed flag][4-byte message length][protobuf request]

Server -> Client
  HEADERS
    :status: 200
    content-type: application/grpc

  DATA
    [compressed flag][4-byte message length][protobuf response]

  HEADERS (trailers, END_STREAM)
    grpc-status: 0
~~~

Key points:

- **HEADERS** carry HTTP/2 pseudo-headers and gRPC metadata. HTTP/2 uses HPACK to compress header blocks.
- **DATA** carries the gRPC message byte stream; each message has a 5-byte prefix: 1 byte compression flag and 4 bytes message length.
- **Trailers** typically carry `grpc-status` and end-of-RPC metadata.
- HTTP status 200 alone does not prove the logical RPC succeeded; inspect `grpc-status`.
- An early-failing RPC may return **trailers-only**, where a single final HEADERS block carries the status with no response DATA.

### 4.1. Frames are not messages

A gRPC message has a length prefix and a protobuf payload. An HTTP/2 DATA frame is merely a transport unit for bytes. Therefore:

- One message may span multiple DATA frames if the payload is large or the transport fragments data.
- One DATA frame may contain bytes belonging to multiple parts of the message stream.
- DATA frame boundaries do not necessarily align with protobuf message boundaries.
- TCP segments, TLS records, and IP packets also do not preserve gRPC message boundaries.

Applications should decode according to gRPC framing and protobuf rather than assuming one DATA frame equals one complete message. Network-layer packet captures are likewise not direct records of logical RPCs.

## 5. Streaming changes message count, not the logical call nature

The four RPC types in Protocol Buffers describe message counts in each direction:

| RPC type | Request messages | Response messages | Logical call |
| --- | --- | --- | --- |
| **Unary** | One | One | One method invocation |
| **Server-streaming** | One | Many | One method invocation, multiple responses |
| **Client-streaming** | Many | One | One method invocation, multiple requests |
| **Bidirectional-streaming** | Many | Many | One method invocation, both directions active |

Example contract:

~~~proto
service OrderService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);
  rpc WatchOrder(WatchOrderRequest) returns (stream OrderUpdate);
  rpc UploadEvents(stream OrderEvent) returns (UploadSummary);
  rpc SyncOrders(stream OrderCommand) returns (stream OrderUpdate);
}
~~~

When the client calls **WatchOrder** once, that is one logical RPC. The server may send thousands of `OrderUpdate` messages on that same stream. Message count is neither the logical RPC count nor the HTTP/2 stream count.

With bidirectional streaming, client and server can emit messages independently under flow control on the same RPC stream. The RPC ends only when one side closes per semantics and the other finishes, or the call fails/is cancelled. Each new business message does not create a new stream.

## 6. One TCP connection can hold many streams

HTTP/2 multiplexing lets multiple streams coexist on a single connection:

~~~text
TCP/TLS connection A
  HTTP/2 stream 1  -> GetOrder, attempt 1
  HTTP/2 stream 3  -> WatchOrder, attempt 1
  HTTP/2 stream 5  -> UploadEvents, attempt 1
  HTTP/2 stream 7  -> GetCustomer, attempt 1
  HTTP/2 stream 9  -> SearchOrders, attempt 1
~~~

Each stream has its own ID scoped to that connection. A stream ID is not a business request ID, is not globally unique, and cannot correlate logs across multiple connections like a correlation ID.

A `ManagedChannel` can manage one or more Subchannels/connections depending on the resolver and load-balancing policy. If backends or connections change, new RPCs can be sent over another connection. An active stream generally stays bound to the connection that created it; it does not automatically migrate to another connection mid-flight.

HTTP/2 also has connection-level control frames such as **SETTINGS**, **PING**, **GOAWAY**, and **WINDOW_UPDATE**. These frames do not necessarily correspond to a single logical RPC:

- SETTINGS negotiates HTTP/2 limits and capabilities.
- PING supports connection health checks per policy.
- WINDOW_UPDATE drives flow control.
- GOAWAY tells the peer to stop opening new streams on the connection.
- RST_STREAM terminates a specific stream.

Consequently, a packet capture may contain interleaved data from many RPCs alongside connection control frames.


## 7. Deadlines, cancellation, and retries from both layers

**Deadlines** belong to the logical call: the caller sets a total budget for the operation. If the runtime makes multiple attempts, retry/backoff time also consumes the logical call's budget. Never assume every attempt gets a fresh full deadline equal to the original one.

**Cancellation** is also applied by the caller to the logical call. The runtime cancels the active attempt and tries to propagate the cancel signal to the server. If work has already spawned downstream or on custom threads, cleanup still depends on propagating `Context` and supporting cancellation properly.

**Retries** create additional attempts/network exchanges for the same logical call when policy allows. That has an important consequence: the server may see multiple nearly identical executions even though the caller called the stub only once.

For instance, an order-writing RPC loses its connection after the server commits but before the client receives trailers. The client may observe a transport or deadline error; if retried unsafely, the write operation could execute twice. Use idempotency keys or result-lookup mechanisms for RPCs with side effects.

| Event | Logical RPC layer | Network layer |
| --- | --- | --- |
| Caller invokes stub | Starts one logical call | A stream may not exist immediately |
| Channel is CONNECTING | Call may wait per policy/deadline | Resolver and transport establish connection |
| Internal retry | Still the same logical call | New attempt / HTTP/2 stream |
| Application calls again after error | New logical call | New exchange |
| Caller cancels | Logical call ends due to cancellation | Active stream cancelled if already created |
| Deadline expires | Logical call exhausts wait budget | Runtime cancels/terminates active attempt |
| One stream receives many messages | Still one logical call | Multiple DATA bytes/messages on the same stream |

## 8. Why can server logs count more requests than the client?

A client interceptor usually counts a logical call when the application invokes the stub and records the outcome in the final callback. A server interceptor records each time a request attempt reaches the server. The two counts can differ because:

- One logical call can have multiple attempts due to retries.
- An attempt can fail before reaching the server, so the server never records it.
- The client can cancel or hit its deadline while the request is in transit.
- A gateway may retry upstream, creating an extra backend exchange.
- A streaming RPC produces many messages while still being one logical call.

Example:

~~~text
Client metrics:
  GetOrder logical calls = 100

Server metrics:
  GetOrder requests observed = 108

Possible explanation:
  6 calls had one retry reaching the server
  2 calls had their first attempt fail before the server while a subsequent attempt reached the server
~~~

These numbers are illustrative. To explain actual discrepancies, you need trace/correlation IDs and separate attempt metrics; do not infer retry counts simply by subtracting two counters.

## 9. Designing observability at the right granularity

Separate three telemetry groups:

| Telemetry group | Examples | Answers |
| --- | --- | --- |
| **Logical RPC metrics** | Calls, final status, end-to-end latency by method | Did callers succeed and finish on time? |
| **Attempt/stream metrics** | Attempt count, retry reason, stream duration, resets | How many times did the runtime/gateway have to try? |
| **Connection metrics** | Active connections, reconnects, TLS handshakes, GOAWAY | Are transport and topology stable? |

A trace can model one logical RPC span with child spans/events for attempts or downstream calls. Record full method name, status, duration, and attempt number where instrumentation supports it.

Do not use HTTP/2 stream IDs, request IDs, or user IDs as high-cardinality metric labels. Stream IDs only have meaning within one connection; request IDs are better suited for correlating logs/traces rather than metric labels. Redact authorization metadata and sensitive payloads.

## 10. Troubleshooting by symptom

| Symptom | How to analyze |
| --- | --- |
| Client counts one call, server counts two requests | Check retry policy, proxy retries, and attempt traces |
| A streaming RPC emits thousands of messages | Count logical calls and messages separately; do not treat each message as an RPC |
| One connection holds many concurrent RPCs | Check HTTP/2 stream multiplexing; do not assume connection misuse |
| Packet capture shows many DATA frames | Inspect gRPC framing; frames do not map one-to-one to fixed messages |
| Client sees DEADLINE_EXCEEDED, server logged a commit | Compare commit timestamp, response/trailers, and deadline |
| Server has no logs even though client called stub | Call may be waiting on resolver, failed connecting before server, or cancelled before reaching backend |
| Server sees CANCELLED while client reports DEADLINE_EXCEEDED | Correlate cancellation source, deadline, and when each side received signals |
| Retries duplicate a write operation | Check idempotency and client or gateway retries |
| Active stream drops on connection reset | One attempt/stream ended; app must open a new logical call and resume if contract supports it |

When investigating, follow the sequence: **application invocation → ClientCall → attempt → HTTP/2 stream → connection → gateway/upstream → server handler**. Finding the first layer where the call is no longer observed narrows the fault to the right layer.

## 11. Hands-on lab and self-check questions

### Hands-on lab

1. Create a service with one unary method `GetOrder` and one server-streaming method `WatchOrder`.
2. Call `GetOrder` with a blocking stub, recording one logical-call metric on the client and one request metric on the server.
3. Call `WatchOrder` and emit multiple `OrderUpdate` messages; verify message count increases while logical-call count increases by one.
4. Configure retries for a safe read method in a test environment; observe attempt count and the number of HTTP/2 streams seen by the server.
5. Simulate a connection failure before trailers arrive; compare the client's final status with server logs.
6. Use packet capture or proxy access logs to inspect HEADERS, DATA, trailers, and connection multiplexing; do not assume frames/packets equal messages.
7. Add correlation IDs/trace context to link client, gateway, and server; distinguish logical call IDs from attempt/stream IDs.
8. For a write RPC, test retrying after timeout and implement an idempotency key to prevent duplicate side effects.

### Self-check questions

**1. Is a logical RPC the same as an HTTP/2 stream?**  
Not entirely. One attempt usually uses one HTTP/2 stream; one logical RPC can have multiple attempts if retries occur.

**2. Can one HTTP/2 connection carry many logical RPCs?**  
Yes. HTTP/2 multiplexes multiple streams over one connection.

**3. Does a streaming RPC create one logical RPC per message?**  
No. Messages belong to the same logical call and typically travel over the same stream for that attempt.

**4. Does one DATA frame always contain exactly one protobuf message?**  
No. DATA frames carry a byte stream; frame boundaries do not necessarily match gRPC message boundaries.

**5. How do internal client retries differ from application retries?**  
Internal retries can create new attempts within the same logical call. Calling the stub again in application code after an error creates a new logical call.

**6. Why can a server record more requests than the client's call count?**  
Due to internal retries or proxy retries; also account for attempts that never reach the server and failures before the handler runs.

**7. Can a stream ID serve as a cross-service correlation ID?**  
No. It is scoped to a single HTTP/2 connection. Use an application-layer request/trace ID to correlate across hops.

**8. Is the full deadline reset for every retry attempt?**  
Never assume so. The deadline bounds the overall logical call; backoff and prior attempts consume the remaining budget.

## Summary

A **logical RPC** is the remote operation requested by the application through a generated stub; a **network exchange** is how the runtime transports that operation across attempts, HTTP/2 streams, frames, and connections. One attempt typically maps to one stream, though retries can create multiple streams for the same logical call; one stream can carry multiple messages and multiple DATA frames. A TCP connection multiplexes many streams, while TLS records and IP packets do not preserve RPC/message boundaries. When developing and operating Spring gRPC services, measure logical calls, attempts, streams, and connections separately, coordinate deadlines/cancellation/retries, and use correlation IDs to trace across layers.
