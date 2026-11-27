# Message Count in Streaming

A streaming RPC can exchange hundreds or millions of messages over the lifetime of a single call. Counting RPCs only tells you how many streams were opened; it does not tell you how much data each stream is sending, which direction is congested, or whether message flow has suddenly stopped. Message count adds visibility into traffic at the message level to operate and optimize gRPC services.

**Message count in streaming** is the count of request/response messages observed at client and server boundaries during a streaming RPC. This lesson belongs to the **Observability** chapter of the **SPRING_GRPC** module: developing gRPC services in the Spring ecosystem using Protocol Buffers contracts, generating Java code, and implementing client/server for unary or streaming RPCs; learners work with metadata, deadlines, statuses, interceptors, TLS, integration testing, and monitoring performance and reliability. The focus is on counting messages by send/receive direction, distinguishing message count from RPC count and byte throughput, and using metrics to detect abnormal data flows.

## 1. Message Count Differs from RPC Count

An RPC is a single invocation of a service method. A message is one unit of request or response exchanged within a call. The relationship between the two quantities depends on the RPC type:

| RPC Type | Request Messages | Response Messages | RPC Count |
| --- | ---: | ---: | ---: |
| Unary | 1 | 1 | 1 |
| Client streaming | Many | 1 | 1 |
| Server streaming | 1 | Many | 1 |
| Bidirectional streaming | Many | Many | 1 |

For example, a bidirectional stream exchanging 500 request messages and 480 response messages is still one RPC. Looking only at RPC count, the system appears to handle just one call; message count reveals the actual exchange volume.

In this lesson, message count focuses on the three streaming RPC types. Unary has exactly one request and one response per contract, so it can be tracked via RPC metrics; if you want message statistics for all method types, clearly specify how `rpc_type` is separated so interpretations remain accurate.

## 2. Clearly Defining the Counted Boundaries

A message can be observed at multiple points in its lifecycle:

- Client calls `ClientCall.sendMessage`: request message is handed to the client call to send.
- Server receives `ServerCall.Listener.onMessage`: request message has been decoded by transport and delivered to the server call listener.
- Server calls `ServerCall.sendMessage`: response message is handed to the server call to send.
- Client receives `ClientCall.Listener.onMessage`: response message has been decoded by transport and delivered to the client listener.

These points produce four distinct metrics:

| Metric | Observation Boundary | Interpretation |
| --- | --- | --- |
| Client messages sent | Client calls sendMessage for a request | Number of request messages accepted by the client call for sending. |
| Server messages received | Server listener receives onMessage | Number of request messages reaching the server listener. |
| Server messages sent | Server calls sendMessage for a response | Number of response messages accepted by the server call for sending. |
| Client messages received | Client listener receives onMessage | Number of response messages reaching the client listener. |

Do not assume the four numbers are always equal. A client may send messages and then cancel before all messages reach the server. The server may send messages, yet the client disconnects before receiving them. A message counted at the send boundary is not proof that the peer received or that the peer application processed the message.

If you need to know whether a message was durably processed, the application must have acknowledgements at the protocol or business layer. Metrics at the transport boundary cannot replace acknowledgements.

## 3. Why Separate Inbound and Outbound?

With bidirectional streaming, both sides can send messages independently. With only a single combined counter, it is hard to tell which direction stopped working:

- Client sent rises while server received is low: the call may be interrupted, flow-controlled, or transport may have issues.
- Server sent rises while client received is low: responses may not have reached the peer or the client is slow to read.
- Client received exceeds server sent in a short window: numbers may diverge due to scrape timing, multiple instances, or metrics collected at different boundaries.
- Message count stays steady while bytes rise: average message size is increasing.

Therefore, name metrics separately by direction and observation side. Avoid a generic `messages_total` metric that does not specify sent vs. received or client vs. server.

## 4. Basic Metrics for Streaming

A metric set you can use:

~~~text
grpc.client.stream.messages.sent
  type: Counter
  tags: service, method, rpc_type

grpc.client.stream.messages.received
  type: Counter
  tags: service, method, rpc_type

grpc.server.stream.messages.sent
  type: Counter
  tags: service, method, rpc_type

grpc.server.stream.messages.received
  type: Counter
  tags: service, method, rpc_type
~~~

Counters are appropriate because cumulative message counts only increase. The metrics backend computes `rate` to express messages/second over a time window. If you need per-stream message counts, do not put stream ID into labels; use sampled traces or logs to investigate individual calls.

`service` should be the full Protobuf service name, `method` the method name, and `rpc_type` one of the three finite values `client_streaming`, `server_streaming`, or `bidi_streaming`. These labels are stable per API and support aggregation by method.

## 5. Counting Messages on the Server with ServerInterceptor

`ServerInterceptor` can observe request messages when the listener receives `onMessage` and response messages when `ServerCall` calls `sendMessage`. This approach does not require modifying individual service implementations:

~~~java
import io.grpc.ForwardingServerCall;
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

import java.util.Locale;

public final class StreamMessageCountServerInterceptor
        implements ServerInterceptor {

    private final MeterRegistry registry;

    public StreamMessageCountServerInterceptor(
            MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        MethodDescriptor<ReqT, RespT> descriptor =
                call.getMethodDescriptor();
        MethodDescriptor.MethodType type = descriptor.getType();

        if (type == MethodDescriptor.MethodType.UNARY) {
            return next.startCall(call, headers);
        }

        String fullMethod = descriptor.getFullMethodName();
        int separator = fullMethod.lastIndexOf('/');
        String service = separator < 0
                ? "unknown"
                : fullMethod.substring(0, separator);
        String method = separator < 0
                ? fullMethod
                : fullMethod.substring(separator + 1);
        String rpcType = type.name().toLowerCase(Locale.ROOT);

        Counter received = Counter.builder(
                        "grpc.server.stream.messages.received")
                .description("Streaming request messages received at the server listener")
                .tags(
                        "service", service,
                        "method", method,
                        "rpc_type", rpcType)
                .register(registry);

        Counter sent = Counter.builder(
                        "grpc.server.stream.messages.sent")
                .description("Streaming response messages sent from the server call")
                .tags(
                        "service", service,
                        "method", method,
                        "rpc_type", rpcType)
                .register(registry);

        ServerCall<ReqT, RespT> monitoredCall =
                new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
                    @Override
                    public void sendMessage(RespT message) {
                        super.sendMessage(message);
                        sent.increment();
                    }
                };

        ServerCall.Listener<ReqT> listener =
                next.startCall(monitoredCall, headers);

        return new ForwardingServerCallListener
                .SimpleForwardingServerCallListener<>(listener) {
            @Override
            public void onMessage(ReqT message) {
                received.increment();
                super.onMessage(message);
            }
        };
    }
}
~~~

The interceptor skips unary methods so the metrics reflect streaming only. Counters are obtained once per call, while `increment` is called per message. `MeterRegistry` reuses meters with the same name and tags, so calls with the same `service`/`method`/`rpc_type` contribute to the same time series.

`sendMessage` is counted after calling `super.sendMessage`. This means the call API accepted the send operation without throwing a synchronous error; it does not prove bytes were written to the socket or the client received the message. `onMessage` indicates the message reached the server listener. If the application needs to measure messages finished processing, place a separate metric at the handler layer after processing completes.

## 6. Counting Messages on the Client with ClientInterceptor

`ClientInterceptor` observes request messages via `ClientCall.sendMessage` and response messages via `ClientCall.Listener.onMessage`:

~~~java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.ForwardingClientCallListener;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

import java.util.Locale;

public final class StreamMessageCountClientInterceptor
        implements ClientInterceptor {

    private final MeterRegistry registry;

    public StreamMessageCountClientInterceptor(
            MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        MethodDescriptor.MethodType type = method.getType();
        if (type == MethodDescriptor.MethodType.UNARY) {
            return next.newCall(method, callOptions);
        }

        String fullMethod = method.getFullMethodName();
        int separator = fullMethod.lastIndexOf('/');
        String service = separator < 0
                ? "unknown"
                : fullMethod.substring(0, separator);
        String methodName = separator < 0
                ? fullMethod
                : fullMethod.substring(separator + 1);
        String rpcType = type.name().toLowerCase(Locale.ROOT);

        Counter sent = Counter.builder(
                        "grpc.client.stream.messages.sent")
                .tags(
                        "service", service,
                        "method", methodName,
                        "rpc_type", rpcType)
                .register(registry);

        Counter received = Counter.builder(
                        "grpc.client.stream.messages.received")
                .tags(
                        "service", service,
                        "method", methodName,
                        "rpc_type", rpcType)
                .register(registry);

        return new ForwardingClientCall
                .SimpleForwardingClientCall<>(
                        next.newCall(method, callOptions)) {
            @Override
            public void sendMessage(ReqT message) {
                super.sendMessage(message);
                sent.increment();
            }

            @Override
            public void start(
                    Listener<RespT> responseListener,
                    Metadata headers) {
                Listener<RespT> monitored =
                        new ForwardingClientCallListener
                                .SimpleForwardingClientCallListener<>(
                                        responseListener) {
                            @Override
                            public void onMessage(RespT message) {
                                received.increment();
                                super.onMessage(message);
                            }
                        };
                super.start(monitored, headers);
            }
        };
    }
}
~~~

Attach the interceptor to the channel via `ManagedChannelBuilder.intercept` or the corresponding Spring gRPC starter extension point. On the server, register `ServerInterceptor` via the server builder or the extension point managed by the starter. Do not create a separate channel/server just for metrics if the starter already owns that lifecycle.

Client `sendMessage` measures request messages accepted by the call for sending; client listener `onMessage` measures response messages arriving at the listener. These metrics are not business acknowledgements and do not guarantee the peer committed the data.

## 7. Choosing the Right Measurement Point in the Application

There are three layers commonly observed:

| Layer | Measurement Point | Question |
| --- | --- | --- |
| gRPC call API | sendMessage/onMessage in interceptor | How many messages crossed the call boundary? |
| Business handler | When handler starts/finishes processing a message | How many messages were processed successfully? |
| Application protocol | When sending/receiving acknowledgements or commits | How many messages were durably confirmed? |

A message may be received on the server but fail during processing. Therefore `messages.received` is not synonymous with `messages.processed`. If you need to track business processing, add `messages.processed` and `messages.processing.errors` at the service layer with separate semantics.

Similarly, `messages.sent` does not prove the client received them. If you need to measure delivery/acknowledgement, design acknowledgements into the Protobuf contract or application protocol. Do not attempt to infer delivery from sender-side counters.

## 8. Message Count, Byte Count, and Throughput

Message count measures the number of message units, while byte count measures data volume. The two quantities can fluctuate independently:

- 1,000 small messages can consume less bandwidth than 10 messages carrying large payloads.
- Compression makes wire bytes differ from uncompressed message size.
- Protobuf serialization has varying overhead depending on schema and field values.
- TLS/HTTP2 framing adds extra bytes beyond the Protobuf payload.

If you need to observe byte throughput, create separate metrics such as `bytes sent`/`received` at a boundary with clear semantics. Do not label message count as throughput if you are not measuring bytes/second. If you only measure serialized message size, clearly state whether it is payload size before or after compression; do not call it wire bytes.

## 9. Reading Message Rate and Average Messages per RPC

Counters can be converted into a message rate over time. If the exporter is Prometheus and the metric is normalized to `grpc_server_stream_messages_received_total`, you can query:

~~~promql
# Request messages per second received by the server, by service/method.
sum by (service, method, rpc_type) (
  rate(grpc_server_stream_messages_received_total[5m])
)
~~~

Response message rate sent by the server:

~~~promql
sum by (service, method, rpc_type) (
  rate(grpc_server_stream_messages_sent_total[5m])
)
~~~

Total messages received in one hour:

~~~promql
sum by (service, method, rpc_type) (
  increase(grpc_server_stream_messages_received_total[1h])
)
~~~

If you have a completed RPC counter with matching labels, you can estimate average messages per call over a window:

~~~promql
sum by (service, method, rpc_type) (
  rate(grpc_server_stream_messages_received_total[5m])
)
/
sum by (service, method, rpc_type) (
  rate(grpc_server_calls_total[5m])
)
~~~

This query assumes the completed RPC counter is exported as `grpc_server_calls_total` and shares the `rpc_type` label with the message counter. If the current counter only has `service`/`method`/`status`, add `rpc_type` or use a compatible streaming RPC counter metric before computing the ratio. You must use the exact names after exporter normalization and ensure the denominator counts the same streaming RPC types, same direction, and same boundary. If the denominator includes unary calls or mixes client/server metrics, the ratio will be wrong. When no compatible call counter exists, do not derive average messages per stream from an incompatible denominator.

## 10. Observing Message Flow Alongside Backpressure

A low message rate does not automatically mean the service is failing. The client may have no data to send, the server may be waiting for events, or flow control may be throttling speed. Combine message count with these signals:

- Active stream count and stream duration.
- Time between messages (inter-message gap).
- Client/server readiness and the `onReady` callback.
- Number of times the producer is paused/resumed due to flow control.
- Queue depth and message processing wait time.
- Deadlines, cancellations, and terminal status.

`onReady` is not a message event. It indicates that the call can resume sending without exceeding gRPC's buffering/flow-control threshold. Do not increment message counters when the `onReady` callback fires.

With bidirectional streaming, monitor both directions separately. If the server receives messages faster than it processes them, queues can grow even though the inbound message rate looks normal. If the client sends too fast, use flow control/backpressure to regulate; counters only help identify rates, not limit load on their own.

## 11. Cardinality and Instrumentation Performance

Message counters increment very frequently, so instrumentation must be lightweight:

- Look up the `Counter` once when the call starts; do not query `MeterRegistry` on every message.
- Only use tags with finite value sets: `service`, `method`, `rpc_type`, and optionally `direction` if sharing a metric.
- Do not put stream ID, request ID, user ID, tenant ID, trace ID, or message sequence number into labels.
- Avoid logging every message at `INFO` level; use sampled tracing or controlled debug logging when investigating.
- If measuring by `instance`/`zone`, evaluate the cardinality budget before adding dimensions.

Do not create a separate meter per stream. Each label combination must be reused across many calls to keep time series counts stable.

## 12. Testing Message Count

Use `SimpleMeterRegistry` and an in-process gRPC server/channel to verify interceptor semantics:

1. Client-streaming sends N request messages; verify client sent and server received increase by N.
2. Server-streaming sends M response messages; verify server sent and client received increase by M.
3. Bidirectional streaming exchanges N requests and M responses; verify all four counters match each direction.
4. Open one stream and send multiple messages; verify RPC count remains one while message counts grow by N/M.
5. Cancel a stream mid-way; verify messages that already crossed the boundary remain in the counters, and unsent messages are not counted.
6. Have the server return an error after receiving several request messages; verify received count reflects messages that reached the listener, not messages planned to be sent.
7. Invoke a unary method; verify the streaming interceptor skips that method.
8. Verify metric labels do not contain stream ID, request ID, or payload data.

For sent message tests, wait for the terminal callback or a test-protocol acknowledgement before reading the registry. Do not use `Thread.sleep` to guess that messages have arrived. For TCP/TLS testing, add peer disconnect and flow-control tests because in-process transport does not fully simulate network buffering or proxies.

## 13. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Message count equals RPC count | Only counting call start/complete. | Count sendMessage and onMessage separately. |
| Assuming server sent equals client received at all times | Mistaking two boundaries for the same event. | Separate API send boundary from peer receive boundary. |
| One multi-message stream counted as multiple RPCs | Counting each onMessage as a call. | Keep RPC counters and message counters separate. |
| Client-streaming has no inbound message metric | Only instrumenting responses or only server sends. | Track requests at server onMessage and client sendMessage. |
| Server-streaming has no response receive metric | Only instrumenting client sendMessage. | Count responses at client listener onMessage. |
| Message rate rises while bytes do not rise proportionally | Average message size decreased. | Observe message count and byte count separately. |
| Messages received interpreted as business processed | Metric sits at transport boundary. | Add a processed counter in the business handler. |
| Metrics backend cardinality grows per stream | Using stream ID or sequence number as tags. | Keep labels bounded; use traces/logs per stream. |
| Counters do not increment in tests | Interceptor not actually registered on channel/server. | Verify starter wiring and invoke RPCs through the right channel/server. |

## 14. Hands-On Exercises

1. Write a `ServerInterceptor` that counts received request messages and sent response messages for the three streaming RPC types.
2. Write a `ClientInterceptor` that counts sent request messages and received response messages; skip unary methods.
3. Create a client-streaming test sending 100 messages; verify client sent and server received at the proper boundaries.
4. Create a server-streaming test returning 50 messages; verify server sent and client received.
5. Create a bidirectional stream with different message counts in each direction; verify the four counters independently.
6. Write PromQL queries to compute messages/second and total messages in one hour by service/method.
7. Combine message rate with active streams, inter-message gap, and queue depth to identify backpressure.
8. Audit cardinality and verify no stream ID, request ID, or message payload appears in labels.

After this lesson, you should be able to distinguish message count from RPC count, byte throughput, and business processing count; measure inbound/outbound at appropriate boundaries on both client and server; and interpret differences between messages sent and messages reaching the peer. Combining message rate with active streams, backpressure, and queue metrics helps operations teams detect abnormal data flows in a Spring gRPC system.
