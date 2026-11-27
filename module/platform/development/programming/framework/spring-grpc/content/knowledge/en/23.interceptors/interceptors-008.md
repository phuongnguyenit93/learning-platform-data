# Interceptors for Unary and Streaming

gRPC Java uses the same interceptor mechanism for both unary RPCs and streaming RPCs. The difference lies in **message count and call lifecycle**: unary typically has one request and one response; streaming can exchange many messages before the call finishes. Therefore, interceptors must be designed per RPC while properly observing message callbacks, completion states, and flow control.

In Spring gRPC, endpoints are registered by the framework, yet interceptors still wrap gRPC Java's `ClientCall`/`ServerCall` and listeners. This lesson covers how one interceptor handles all four RPC types, how to distinguish call-level from message-level concerns, and notes on cancellation, deadlines, backpressure, and testing.

## 1. Four RPC types and observation points

Protocol Buffers defines the RPC type through the method signature:

```proto
service CatalogService {
  // One request, one response.
  rpc GetProduct(GetProductRequest) returns (Product);

  // One request, many responses.
  rpc WatchProduct(WatchProductRequest) returns (stream ProductEvent);

  // Many requests, one response.
  rpc ImportProducts(stream ImportProductRequest)
      returns (ImportSummary);

  // Many requests, many responses.
  rpc SyncProducts(stream SyncProductRequest)
      returns (stream SyncProductEvent);
}
```

| RPC type | Client sends | Server sends | Main observation points |
| --- | --- | --- | --- |
| Unary | One request | One response | One message sent/received and one completion |
| Server streaming | One request | Many responses | Server calls `sendMessage` multiple times; client listener receives multiple `onMessage` |
| Client streaming | Many requests | One response | Server listener receives multiple `onMessage`; client calls `sendMessage` multiple times then half-closes |
| Bidirectional streaming | Many requests | Many responses | Both sides exchange multiple messages independently until the call closes |

You can read the RPC type from the descriptor:

```java
MethodDescriptor.MethodType rpcType =
        call.getMethodDescriptor().getType();
String fullMethodName =
        call.getMethodDescriptor().getFullMethodName();
```

`interceptCall` is invoked only once per RPC, not once per message. To observe individual messages, an interceptor must wrap `ServerCall.Listener`, `ServerCall`, `ClientCall`, or `ClientCall.Listener` depending on data direction.

## 2. Call lifecycle and message lifecycle

On the server side:

```text
interceptCall
  -> next.startCall
      -> Listener.onMessage (0..n)
      -> Listener.onHalfClose
      -> ServerCall.sendMessage (0..n)
      -> ServerCall.close(status, trailers)
  -> Listener.onCancel if client cancels the call
```

On the client side:

```text
interceptCall
  -> ClientCall.start(listener, headers)
  -> ClientCall.sendMessage (0..n)
  -> ClientCall.halfClose
  -> Listener.onHeaders
  -> Listener.onMessage (0..n)
  -> Listener.onClose(status, trailers)
```

Callbacks do not have identical meanings:

- `onMessage` is a single message delivered to the receiving side's listener.
- `onHalfClose` on the server indicates the client has stopped sending request messages; for client streaming or bidi, the server may still continue processing and sending responses.
- `ServerCall.close` closes the RPC from the server side, carrying the final status and trailers.
- `ClientCall.Listener.onClose` is the final outcome observed by the client.
- `onCancel` informs the server that the call was cancelled by the client or terminated by the transport due to cancellation.

Do not treat `onHalfClose` as the end of the entire call. For client streaming, it is typically the point where the server can aggregate received requests; the server still has to send the final response and close the call.

## 3. Server interceptor counting messages for all RPC types

A server interceptor can wrap both `ServerCall` and the listener:

- `ServerCall.Listener.onMessage` counts request messages received from the client.
- `ServerCall.sendMessage` counts response messages sent by the server.
- `ServerCall.close` records the final status; `onCancel` records cancellation if the call has not already closed.

The following example writes one summary log per call:

```java
package com.myshop.grpc.observability;

import io.grpc.ForwardingServerCall;
import io.grpc.ForwardingServerCallListener;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Consumer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class ServerStreamMetricsInterceptor
        implements ServerInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(ServerStreamMetricsInterceptor.class);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String method = call.getMethodDescriptor().getFullMethodName();
        String rpcType = call.getMethodDescriptor()
                .getType().name().toLowerCase(Locale.ROOT);
        AtomicLong inbound = new AtomicLong();
        AtomicLong outbound = new AtomicLong();
        AtomicBoolean recorded = new AtomicBoolean();

        Consumer<Status> finish = status -> {
            if (recorded.compareAndSet(false, true)) {
                log.info(
                        "grpc.server.call method={} rpc_type={} inbound_messages={} outbound_messages={} status={}",
                        method, rpcType, inbound.get(), outbound.get(),
                        status.getCode());
            }
        };

        ServerCall<ReqT, RespT> wrappedCall =
                new ForwardingServerCall.SimpleForwardingServerCall<>(call) {
                    @Override
                    public void sendMessage(RespT message) {
                        outbound.incrementAndGet();
                        super.sendMessage(message);
                    }

                    @Override
                    public void close(Status status, Metadata trailers) {
                        finish.accept(status);
                        super.close(status, trailers);
                    }
                };

        final ServerCall.Listener<ReqT> listener;
        try {
            listener = next.startCall(wrappedCall, headers);
        } catch (RuntimeException ex) {
            finish.accept(Status.fromThrowable(ex));
            throw ex;
        }

        return new ForwardingServerCallListener
                .SimpleForwardingServerCallListener<>(listener) {
            @Override
            public void onMessage(ReqT message) {
                inbound.incrementAndGet();
                super.onMessage(message);
            }

            @Override
            public void onCancel() {
                try {
                    super.onCancel();
                } finally {
                    finish.accept(Status.CANCELLED);
                }
            }
        };
    }
}
```

The counters are created inside `interceptCall`, so each RPC has its own isolated state. Never store shared `AtomicLong` fields on a singleton interceptor: concurrent calls would mix message counts.

In this example, `outbound_messages` is how many times the server called `sendMessage`, and `inbound_messages` is how many `onMessage` callbacks were delivered to the listener. These are counts at the API boundary, not proof that messages were successfully processed by the client application or durably persisted.

## 4. Client interceptor observing two-way messages

On the client, outbound messages pass through `ClientCall.sendMessage`; inbound messages arrive via `ClientCall.Listener.onMessage`. `onClose` records the final status:

```java
package com.myshop.grpc.observability;

import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.ForwardingClientCallListener;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import io.grpc.Status;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicLong;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class ClientStreamMetricsInterceptor
        implements ClientInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(ClientStreamMetricsInterceptor.class);

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        String fullMethodName = method.getFullMethodName();
        String rpcType = method.getType().name().toLowerCase(Locale.ROOT);
        AtomicLong outbound = new AtomicLong();
        AtomicLong inbound = new AtomicLong();

        ClientCall<ReqT, RespT> delegate =
                next.newCall(method, callOptions);

        return new ForwardingClientCall.SimpleForwardingClientCall<>(delegate) {
            @Override
            public void sendMessage(ReqT message) {
                outbound.incrementAndGet();
                super.sendMessage(message);
            }

            @Override
            public void start(Listener<RespT> listener, Metadata headers) {
                Listener<RespT> wrappedListener =
                        new ForwardingClientCallListener
                                .SimpleForwardingClientCallListener<>(listener) {
                            @Override
                            public void onMessage(RespT message) {
                                inbound.incrementAndGet();
                                super.onMessage(message);
                            }

                            @Override
                            public void onClose(Status status, Metadata trailers) {
                                log.info(
                                        "grpc.client.call method={} rpc_type={} outbound_messages={} inbound_messages={} status={}",
                                        fullMethodName, rpcType, outbound.get(),
                                        inbound.get(), status.getCode());
                                super.onClose(status, trailers);
                            }
                        };
                super.start(wrappedListener, headers);
            }
        };
    }
}
```

Client-side `outbound_messages` counts how many times the application called `sendMessage`; `inbound_messages` counts messages received by the listener. With streaming, the client can send multiple messages and call `halfClose` to signal it is done sending while still waiting for responses. Do not treat `halfClose` as the end of the RPC; the final status only arrives at `onClose`.

## 5. Unary interceptors remain useful

For unary RPCs, the message wrappers still work, though counts are normally one request and one response. A shared interceptor can:

- Record method, status, and duration across all RPC types.
- Attach correlation IDs or trace metadata.
- Apply shared authentication.
- Count request/response messages without unary-specific logic.

However, do not force every metric into the same interpretation. Unary `message_count` is typically 1/1, whereas streaming can reach thousands of messages. If dashboards compare calls, keep the `rpc_type` label or split metrics by purpose.

## 6. Flow control and backpressure: interceptors must not break them

Streaming RPCs can transfer large numbers of messages. gRPC provides flow control so a sender does not push data faster than the receiver can process it. An observing interceptor must keep this mechanism intact:

- Do not call extra `request(n)` or increase demand on behalf of the application.
- Do not invoke `sendMessage` again, retain message copies, or buffer unboundedly.
- Do not delay `onMessage` callbacks with blocking I/O.
- Do not alter `isReady()`, `onReady()`, or `setOnReadyHandler` behavior without a clear reason.
- If buffering is necessary, enforce memory limits, overflow policies, and stream cancellation handling.

For server streaming, the application should respect readiness before emitting further large data. For client streaming/bidi, the client should pace sending according to demand and readiness instead of pushing endlessly in a synchronous loop.

An interceptor that merely counts messages as shown above does not alter demand or buffering. That is the safer choice for cross-cutting concerns.

## 7. Cancellation, deadlines, and status

A stream may finish normally, fail with an error, be cancelled by the client, or hit its deadline:

| Scenario | Server typically observes | Client typically observes |
| --- | --- | --- |
| Normal completion | `close(OK)` | `onClose(OK)` |
| Server returns business error | Corresponding status at close | Same status propagated to client |
| Client explicitly cancels | `onCancel` | `onClose(CANCELLED)` |
| Deadline expires | Server usually sees call cancelled | Client usually sees `DEADLINE_EXCEEDED` |

Statuses on the two sides can differ on deadlines/cancellations because the client knows the call's deadline while the server may only observe transport cancellation. Do not infer the exact root cause solely from server `onCancel`.

All per-call state must be released upon completion. Never keep references to messages, listeners, or context in global collections after `close`/`onClose`. If an interceptor records metrics/logs in both `close` and `onCancel`, use an atomic flag to avoid recording twice.

## 8. Registering the interceptor in Spring gRPC

Core gRPC Java lets you attach interceptors to servers and channels:

```java
Server server = ServerBuilder.forPort(9090)
        .intercept(new ServerStreamMetricsInterceptor())
        .addService(catalogService)
        .build();

ManagedChannel channel = ManagedChannelBuilder
        .forAddress("catalog.internal", 9090)
        .useTransportSecurity()
        .intercept(new ClientStreamMetricsInterceptor())
        .build();
```

In Spring gRPC, servers/channels are usually auto-configured by the framework. Register interceptors through the extension point supported by your project's Spring gRPC version; declaring a class as a bean alone does not guarantee it is attached to every server/channel. Verify with integration tests covering both unary and streaming methods.

If there are multiple channels to different backends, decide which interceptors are global and which attach to a single channel. Metrics may be shared, whereas credentials, tenant context, and policies can differ by destination.

## 9. Testing all four RPC types

A single unary test is not enough to prove an interceptor works for streaming. Test the following:

| Test case | Result to verify |
| --- | --- |
| Unary | Counts one request/response and records status once |
| Server streaming | One request, many responses; outbound count matches server sends |
| Client streaming | Many requests, one response; `onHalfClose` is not treated as call completion |
| Bidirectional streaming | Accurate two-way counts with interleaved messages |
| Cancelled stream | Cancellation recorded once and state released |
| Expired deadline | Client sees `DEADLINE_EXCEEDED`; server handles cancellation safely |
| Flow control | Interceptor does not alter demand/readiness or grow buffers unboundedly |
| Multiple concurrent calls | Per-call counters do not mix |
| Exception/close | Original status is preserved and not recorded twice |

You can use an in-process server/channel for pure gRPC tests. For Spring integration tests, boot the application context and perform RPCs through the real configuration to confirm the interceptor is registered properly. Use multi-message streams and mid-stream cancellations to test real lifecycles.

## 10. Implementation checklist

- [ ] Use `MethodDescriptor.getType()` to classify unary/server streaming/client streaming/bidi streaming.
- [ ] `interceptCall` creates per-RPC state.
- [ ] Server counts requests in listener `onMessage` and responses in `ServerCall.sendMessage`.
- [ ] Client counts requests in `ClientCall.sendMessage` and responses in listener `onMessage`.
- [ ] `onHalfClose` is treated only as the client stopping request sends.
- [ ] Final status is recorded in `ServerCall.close` or client `onClose`.
- [ ] Cancellations/deadlines are handled without double-recording metrics.
- [ ] Do not interfere with demand, readiness, or buffering if the interceptor is purely observational.
- [ ] Never hold per-call state in shared fields of a singleton interceptor.
- [ ] Tests cover all four RPC types, concurrency, cancellations, and deadlines.
- [ ] Verify interceptor registration via Spring integration tests.

**Self-check**

**Question 1.** Is `interceptCall` invoked once per message in a streaming RPC or once for the whole call?

*Answer:* Once for the whole RPC. To observe individual messages, you must wrap the listener/call and intercept message callbacks/send operations.

**Question 2.** On the server, which callback counts request messages and which method counts response messages?

*Answer:* `ServerCall.Listener.onMessage` counts requests received from the client; `ServerCall.sendMessage` counts responses sent by the server.

**Question 3.** In client streaming, does `onHalfClose` mean the RPC has finished?

*Answer:* No. It only signals the client finished sending its request stream; the server can still process and send the final response before closing the call.

**Question 4.** Why shouldn't a message-counting interceptor call `request(n)` on its own?

*Answer:* `request(n)` drives flow control/demand. Altering it can change backpressure and the application's stream consumption behavior.

**Question 5.** Why must counters live inside `interceptCall` rather than as interceptor fields?

*Answer:* An interceptor is normally shared concurrently across many RPCs. Local state created per `interceptCall` guarantees message counts and statuses never mix across calls.

Interceptors for unary and streaming share the same extension point, but must respect the difference between call-level and message-level behavior. Wrapping the right calls/listeners, leaving flow control intact, scoping state per RPC, and testing all four exchange patterns ensures interceptors behave consistently in Spring gRPC.
