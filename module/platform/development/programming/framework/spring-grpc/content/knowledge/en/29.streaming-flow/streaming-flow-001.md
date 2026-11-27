# Flow Control in HTTP/2

## Learning Objectives

After this lesson, you will be able to:

- Explain why HTTP/2 needs flow control when multiple streams transmit data concurrently.
- Distinguish between a **stream-level window** and a **connection-level window**.
- Describe the roles of **DATA**, **WINDOW_UPDATE**, and **SETTINGS_INITIAL_WINDOW_SIZE**.
- Calculate the amount of data that can be sent based on the transmission window and understand how the window is replenished.
- Distinguish HTTP/2 flow control from TCP congestion control and manual flow control in the gRPC API.
- Apply backpressure to avoid exhausting memory when handling streaming in Spring gRPC.

## 1. What Problem Does Flow Control Solve?

In gRPC, RPC data is transmitted over HTTP/2. An HTTP/2 connection can carry multiple concurrent streams; each stream can send many data frames. If the sender continuously transmits faster than the receiver can read or process, queued data accumulates in buffers, increasing memory usage and latency.

**Flow control** limits the amount of data one side can send before the receiver permits it to send more. The receiver adjusts the limit by updating the transmission window. This mechanism helps protect the peer's capacity to receive data and allows multiple streams to share a single connection.

In **SPRING_GRPC**, this is especially important for client-streaming, server-streaming, and bidirectional streaming. A fast producer can generate data faster than the service or client can process it; flow control provides backpressure at the transport layer, while the application must coordinate so it does not accumulate unbounded queues at its own layer.

## 2. The Two Window Levels of HTTP/2

HTTP/2 uses two independent windows for each transmission direction:

1. **Stream-level flow-control window**: limits the DATA sent on a specific stream.
2. **Connection-level flow-control window**: limits the total DATA sent across the entire connection.

Each DATA frame consumes capacity from both windows. The sender can only send more DATA when both the stream window and the connection window have sufficient remaining capacity.

~~~mermaid
flowchart TD
  S["Sender"] --> D["DATA frame on stream A"]
  D --> SW["Subtract stream window A"]
  D --> CW["Subtract connection window"]
  SW --> G{"Both windows sufficient?"}
  CW --> G
  G -->|Yes| R["Continue sending DATA"]
  G -->|No| W["Wait for WINDOW_UPDATE"]
  W --> U["Receiver increases window"]
  U --> R
~~~

For example, the connection window has 20 KiB remaining, but stream A only has 2 KiB remaining. Stream A can send at most 2 KiB of DATA before needing a window update for stream A. Conversely, if stream A has 20 KiB remaining but the connection window only has 1 KiB remaining, the total data sent over the connection is limited to 1 KiB.

These two windows prevent two different situations: a single stream overflowing the buffer allocated for itself, and multiple streams combined overflowing the receiving capacity of the entire connection.

## 3. Windows Are Measured in DATA Bytes

HTTP/2 flow control applies to **DATA frames**, not to every frame type. Frames such as HEADERS, SETTINGS, PING, and WINDOW_UPDATE do not consume the flow-control window.

The window unit is octets (bytes) of the DATA payload, calculated according to HTTP/2 rules:

- The data payload of a DATA frame is subtracted from the window.
- If the frame has padding, the Pad Length field and padding are also included in the flow-controlled length.
- The 9-byte frame header is not counted toward the window.

Therefore, flow control does not count the number of frames, RPCs, or Protobuf messages. It limits the number of DATA bytes that can be in flight without having been replenished by a window update.

## 4. Default Window Size

According to HTTP/2, the default initial window size is **65,535 octets** for each stream and for the connection. The window is not a limit on the total size of an RPC or the total number of bytes a stream is allowed to transmit over its lifetime; it is the amount of DATA that can be sent before a window update is required.

A peer can adjust the stream window using the **SETTINGS_INITIAL_WINDOW_SIZE** setting. This setting applies to existing streams and streams created afterward. It does not change the connection-level window. The connection window is adjusted separately using **WINDOW_UPDATE** frames.

When SETTINGS_INITIAL_WINDOW_SIZE decreases, the current stream window value can become negative. In that case, the sender must stop sending DATA on the stream until the window becomes positive enough to resume sending. This is not an error if the result follows HTTP/2 rules.

Do not confuse:

- **SETTINGS_MAX_FRAME_SIZE** limits the size of a DATA frame that can be sent.
- **SETTINGS_INITIAL_WINDOW_SIZE** adjusts the stream flow-control window.
- **WINDOW_UPDATE** replenishes flow-control capacity for a stream or connection.

## 5. How Does WINDOW_UPDATE Replenish the Window?

The receiver sends a **WINDOW_UPDATE** frame to allow the sender to send more DATA. The frame carries a 31-bit positive integer called the window size increment.

- A WINDOW_UPDATE with stream ID 0: updates the **connection window**.
- A WINDOW_UPDATE with a non-zero stream ID: updates that stream's window.
- The increment must be greater than 0.
- The window value must not exceed \(2^{31}-1\); if exceeded, the connection or stream encounters a flow-control error according to HTTP/2 rules.

For example, if the stream window has 4,096 bytes remaining and the receiver sends a WINDOW_UPDATE with an increment of 8,192 bytes, the sender gains 8,192 bytes of sending allowance on that stream. Connection window capacity must still be sufficient separately.

The receiver typically replenishes the window when enough data has been consumed to accept more. Applications should not assume that reading one gRPC message will produce exactly one WINDOW_UPDATE; the timing and size of updates are managed by the HTTP/2 implementation.

## 6. Flow Control Is Independent in Each Direction

Both peers can send data and control how much data they are ready to receive. The windows for the client → server and server → client directions are independent:

- The client advertises its receive limit so the server throttles DATA sent downstream.
- The server advertises its receive limit so the client throttles DATA sent upstream.

Therefore, a server-streaming RPC can be constrained by the receive window at the client; a client-streaming RPC can be constrained by the receive window at the server. In bidirectional streaming, the two directions can progress at different speeds.

Flow control is **hop-by-hop** between two direct HTTP/2 endpoints. If there is a proxy or gateway, each hop has its own window mechanism; a window update on one hop is not automatically a window update on another hop.

## 7. A gRPC Message Is Not Identical to an HTTP/2 DATA Frame

A gRPC message has its own framing consisting of:

1. One byte for the compression flag.
2. Four bytes for the message length in big-endian order.
3. The serialized Protobuf message content.

HTTP/2 transports those framing bytes and payload inside DATA frames. One gRPC message can be split across multiple DATA frames; a single DATA frame can also contain the end of a previous message and the start of the next message.

Consequently:

- HTTP/2 flow control counts bytes of the DATA payload, including gRPC framing.
- It does not allocate a separate window per Protobuf message.
- Calling **request(1)** in the gRPC API means allowing one more message to be received at the gRPC layer; it does not mean increasing the HTTP/2 window by one byte or one frame.

This layering distinction is important when diagnosing issues: an RPC might not have received the next message because the application has not requested more, or because the transport does not have enough HTTP/2 window. The two causes reside at two different layers.

## 8. Flow Control Differs from Congestion Control

**HTTP/2 flow control** and **TCP congestion control** both limit data transmission, but they solve two different problems:

| Mechanism | What does it protect? | Controlled by |
| --- | --- | --- |
| HTTP/2 flow control | The peer's and stream's capacity to receive data | Receiver via window updates/settings |
| TCP congestion control | The network's carrying capacity along the transmission path | TCP stack based on network signals |
| Application backpressure | Processing capacity, queues, and business resources | Application logic and gRPC API |

A large HTTP/2 window does not mean the network can transmit faster without causing congestion. Conversely, a large TCP congestion window does not mean the receiving application is ready to accept unbounded data.

Flow control also does not replace message-size limits, deadlines, quotas, or memory limits. Those mechanisms must be configured and checked separately.

## 9. Impact of One Stream on Other Streams

Streams on the same HTTP/2 connection share the connection-level window. If one stream sends a large volume of DATA quickly, it can consume most of the connection window, temporarily preventing other streams from sending DATA even though their individual stream windows still have capacity.

This is why you need to consider:

- Message size and producer speed.
- Number of concurrent streams on a single connection.
- Read/consumption speed at the receiver.
- How the HTTP/2 implementation allocates window updates between streams and the connection.
- Whether to separate heavy workloads onto dedicated connections or appropriate RPCs when isolation is required.

You should not assume that a slow stream only affects itself. At the connection level, multiple streams share the same flow-control budget.

## 10. Backpressure in the gRPC Java API

HTTP/2 flow control is managed at the transport layer. Spring gRPC applications typically interact with backpressure through the gRPC Java API:

- **Outbound readiness**: **isReady()** indicates whether the observer can currently accept more data without accumulating too much pending data in the sending layer.
- **On-ready callback**: **setOnReadyHandler(...)** notifies when sending readiness changes so the producer can resume emitting data.
- **Inbound manual flow control**: the application can disable auto-request and call **request(n)** once it finishes processing the corresponding number of messages.

Example of a server emitting responses based on readiness:

~~~java
ServerCallStreamObserver<Update> out =
    (ServerCallStreamObserver<Update>) responseObserver;

out.setOnReadyHandler(() -> {
    while (out.isReady() && hasNextUpdate()) {
        out.onNext(nextUpdate());
    }

    if (!hasNextUpdate() && !out.isCancelled()) {
        out.onCompleted();
    }
});
~~~

This is an illustrative skeleton: a real producer needs to manage completion state, call cancellation, and synchronized data access if the callback can run on another executor. Do not spin in a busy loop waiting for `isReady()` to become true.

For inbound manual flow control on the client, **ClientResponseObserver.beforeStart(...)** can call **disableAutoRequestWithInitial(1)**, then call **request(1)** after finishing each response. That way, the application only requests more messages when it is ready to receive them.

**isReady()** and **request(n)** are APIs at the gRPC layer, not APIs that directly modify the HTTP/2 stream window. The transport still manages DATA frames, the connection window, and WINDOW_UPDATE underneath.

## 11. Applying to Streaming RPC Types

| RPC Type | Primary data direction | Where to watch flow control |
| --- | --- | --- |
| Unary | One request, one response | Large messages still consume the window; avoid assuming unary needs no backpressure. |
| Server streaming | Server sends multiple responses | Server monitors outbound readiness; client throttles inbound messages if needed. |
| Client streaming | Client sends multiple requests | Client monitors outbound readiness; server processes inbound messages within bounds. |
| Bidirectional streaming | Both directions send multiple messages | Manage backpressure independently for inbound and outbound on both sides. |

With bidirectional streaming, a message-processing callback should not block reading or sending in the other direction if both directions need to progress independently. Use bounded queues, controlled asynchronous processing, and coordinate cancellation/deadlines.

## 12. How to Diagnose a Slow Stream

When you see a streaming RPC slow down or stop emitting messages, inspect layer by layer:

1. **Sending application**: is the producer continuously generating data, or is it blocked by `isReady()` or an internal queue?
2. **gRPC inbound demand**: has the receiving application called `request(n)` enough times, or was auto flow control disabled?
3. **HTTP/2 stream window**: does the specific stream still have enough window to send DATA?
4. **HTTP/2 connection window**: is another stream consuming most of the connection window?
5. **Receiver**: is the application reading and processing messages fast enough for the transport to keep receiving?
6. **TCP/network**: is there retransmission, congestion, or bandwidth throttling?

Observe application metrics alongside transport metrics if the library provides them. Do not conclude “the HTTP/2 window is 0” solely from not seeing `onNext` callbacks; the cause could lie in application demand, the producer, or the network.

## 13. Designing Safe Backpressure in Practice

For a client-streaming upload, you should:

- Split data into reasonably sized chunks instead of bundling the entire file into one large message.
- Only emit the next chunk when the outbound observer is ready.
- On the server, process chunks in order and limit the number of pending chunks.
- If using manual inbound flow control, only request more after the current chunk has been processed or safely buffered.
- Stop the producer when the call is cancelled or the deadline expires.
- Define how to handle duplicate, missing, or out-of-offset chunks and retries at the business layer.

~~~mermaid
sequenceDiagram
  participant C as Client producer
  participant T as HTTP/2 transport
  participant S as Server consumer
  C->>T: DATA chunk 1
  T->>S: Deliver chunk 1
  S->>S: Validate and persist
  S-->>C: Demand / readiness for next chunk
  C->>T: DATA chunk 2
  T->>S: Deliver chunk 2
  S->>S: Validate and persist
  S-->>C: Demand / readiness for next chunk
~~~

Flow control does not replace data validation, total upload size limits, or authorization checks. A client can still send a single very large message if the message-size limit allows it; separate size limits must be enforced.

## 14. Common Mistakes

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Caring only about the stream window | Ignoring the shared connection window limit | Monitor both window levels. |
| Thinking WINDOW_UPDATE is sent after every message | Wrong assumptions about when transmission resumes | Treat it as a byte-level mechanism managed by the transport. |
| Confusing request(1) with increasing the HTTP/2 window | Misdiagnosing which layer is causing the bottleneck | Distinguish gRPC message demand from the HTTP/2 byte window. |
| Sending continuously even when isReady() is false | Increases buffers, latency, and memory pressure | Pause the producer and resume via the on-ready callback. |
| Using an unbounded queue in the application | Transport flow control does not prevent heap from growing unbounded | Use a bounded queue and backpressure. |
| Assuming flow control is congestion control | Overlooking network congestion | Monitor both HTTP/2 and TCP/network. |
| Treating flow control as a message-size limit | A single large message can still cause memory pressure | Configure message-size limits and chunked streaming. |
| Not stopping processing when the RPC is cancelled | Continues consuming resources after the client disconnects | Track cancellation and release resources. |

## 15. Practice Exercises

A Spring gRPC service receives a file over a client-streaming RPC and returns the total number of saved bytes:

1. Explain why HTTP/2 needs both a stream window and a connection window when multiple uploads run concurrently on one connection.
2. With the default window of 65,535 bytes, explain what the sender must do when the stream window is exhausted while the connection window still has capacity.
3. Describe how a WINDOW_UPDATE frame with stream ID 0 differs from a frame with the upload's stream ID.
4. Explain why the 5-byte gRPC message prefix also consumes the HTTP/2 DATA window.
5. Design a producer that only sends the next chunk when the outbound observer is ready.
6. Propose a way to limit the number of pending chunks on the server when using inbound manual flow control.
7. Distinguish between being blocked by `request(n)`, the HTTP/2 window, and TCP congestion.

**Completion criteria:** accurately describe both window levels, calculate the allowed amount of DATA to send, distinguish flow control from other backpressure layers, and design streaming that does not accumulate unbounded data.

## 16. Key Takeaways

- HTTP/2 flow control applies to **DATA frames** and is measured in flow-controlled payload bytes.
- Each transmission direction has a **stream window** and a **connection window**; sending DATA requires sufficient capacity in both.
- **WINDOW_UPDATE** replenishes windows; **SETTINGS_INITIAL_WINDOW_SIZE** adjusts stream windows, not the connection window.
- gRPC messages have their own framing but are transported inside DATA frames; flow control does not count messages.
- HTTP/2 flow control differs from TCP congestion control and from application backpressure.
- In gRPC Java, coordinate **isReady()**, the on-ready callback, and **request(n)** to throttle producers and consumers.
- Use bounded queues, message limits, cancellation, and deadlines to protect the entire streaming pipeline.

Understanding flow control in HTTP/2 helps Spring gRPC services regulate data flow across multiple streams, prevent uncontrolled buffer growth, and maintain stability when the client and server process streaming at different speeds.
