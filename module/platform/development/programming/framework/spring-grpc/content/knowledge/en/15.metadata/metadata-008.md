# Metadata from Server to Client

Metadata does not only flow from client to server. In gRPC, the server can send auxiliary information back to the client via **initial response headers** and **response trailers**. Both types of metadata belong to the same RPC, but are sent at different times: headers appear when the server begins responding; trailers are sent when the RPC finishes alongside the gRPC status.

In Spring gRPC, these APIs come from `grpc-java`. A service can send response headers using `ServerCallStreamObserver.sendHeaders(...)`; a server interceptor can append trailers during `ServerCall.close(...)`; the client receives headers in `ClientCall.Listener.onHeaders(...)` and receives trailers along with status in `onClose(...)`.

## 1. Distinguishing Response Headers and Trailers

| Feature | Initial response headers | Response trailers |
| --- | --- | --- |
| Timing | Start of the response, before the first message | When the RPC finishes |
| Server-side API | `ServerCall.sendHeaders(...)` or `ServerCallStreamObserver.sendHeaders(...)` | `ServerCall.close(status, trailers)` |
| Client-side callback | `ClientCall.Listener.onHeaders(...)` | `ClientCall.Listener.onClose(status, trailers)` |
| Suitable data | Server version, negotiated capabilities, initial diagnostic codes | Request ID for correlation, short app error codes, completion info |
| Frequency | At most once per RPC | Once when the call closes |

Diagram of a unary RPC:

```text
Client                                             Server
  |                                                  |
  |---------------- request ------------------------>|
  |                                                  |
  |<------------- initial response headers ----------|  onHeaders(...)
  |<------------- response message ------------------|  onMessage(...)
  |<------------- trailers + grpc-status ------------|  onClose(status, trailers)
  |                                                  |
```

With server streaming, response headers are still sent at most once before the first message; multiple response messages follow over the stream; trailers appear only when the stream completes or terminates with an error. Client streaming and bidirectional streaming follow the same rule that metadata attaches to the **entire RPC**, not per individual message.

Some errors may finish as **trailers-only**: the client receives status and trailers without initial response headers or a message. Therefore, error-handling logic must never depend on `onHeaders(...)` always being called.

## 2. Server Sending Initial Response Headers

Inside a service implementation, gRPC provides `ServerCallStreamObserver` to send headers before the first message. Example:

```java
import io.grpc.Metadata;
import io.grpc.stub.ServerCallStreamObserver;
import io.grpc.stub.StreamObserver;

private static final Metadata.Key<String> SERVER_VERSION =
    Metadata.Key.of(
        "x-server-version",
        Metadata.ASCII_STRING_MARSHALLER);

@Override
public void getInfo(
        InfoRequest request,
        StreamObserver<InfoReply> responseObserver) {

    ServerCallStreamObserver<InfoReply> serverObserver =
        (ServerCallStreamObserver<InfoReply>) responseObserver;

    Metadata responseHeaders = new Metadata();
    responseHeaders.put(SERVER_VERSION, "1.4.0");

    // Must send headers before the first message.
    serverObserver.sendHeaders(responseHeaders);

    InfoReply reply = InfoReply.newBuilder()
        .setMessage("Service is ready")
        .build();
    serverObserver.onNext(reply);
    serverObserver.onCompleted();
}
```

`InfoRequest`, `InfoReply`, and `getInfo` are example names generated or implemented from a Protobuf contract. In an actual gRPC server, the runtime supplies `ServerCallStreamObserver` to the service; call `sendHeaders(...)` only once and before emitting any message. Do not call it after `onNext(...)` or after the call has closed.

Only place short data in response headers that the client needs early, such as server version or a negotiated option. Never send tokens, sensitive internal details, or large business payloads. If the server needs no initial metadata, let gRPC send default headers when starting the response.

## 3. Server Adding Trailers via Interceptor

The `StreamObserver`-based service API typically does not expose a direct trailers parameter when calling `onCompleted()` or `onError()`. A `ServerInterceptor` can wrap `ServerCall` and append metadata at `close(status, trailers)`.

The example below echoes back the request ID validated at the start of the call:

```java
import io.grpc.ForwardingServerCall;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class ResponseTrailersInterceptor
        implements ServerInterceptor {

    private static final Metadata.Key<String> REQUEST_ID =
        Metadata.Key.of(
            "x-request-id",
            Metadata.ASCII_STRING_MARSHALLER);
    private static final Metadata.Key<String> RESPONSE_REQUEST_ID =
        Metadata.Key.of(
            "x-response-request-id",
            Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata requestHeaders,
            ServerCallHandler<ReqT, RespT> next) {

        String requestId = requestHeaders.get(REQUEST_ID);
        // Only echo IDs that passed format validation at the trust boundary.
        final String safeRequestId =
            requestId != null
                && requestId.matches("[A-Za-z0-9._-]{1,64}")
            ? requestId
            : null;

        ServerCall<ReqT, RespT> wrappedCall =
            new ForwardingServerCall.SimpleForwardingServerCall<ReqT, RespT>(
                    call) {
                @Override
                public void close(Status status, Metadata trailers) {
                    if (safeRequestId != null) {
                        trailers.discardAll(RESPONSE_REQUEST_ID);
                        trailers.put(RESPONSE_REQUEST_ID, safeRequestId);
                    }
                    // Preserve original status and other trailers.
                    super.close(status, trailers);
                }
            };

        return next.startCall(wrappedCall, requestHeaders);
    }
}
```

The interceptor above only illustrates appending trailers. In a real application, the request ID should be validated at the trust boundary; if missing or invalid, the server can generate its own ID instead of echoing a client-sent value. Never use trailers to return bearer tokens, personal data, or stack traces.

The crucial point is calling `super.close(status, trailers)` with the **original status**. Adding diagnostic metadata must not alter business outcomes or mask `UNAUTHENTICATED`, `PERMISSION_DENIED`, `DEADLINE_EXCEEDED`, or other statuses.

## 4. Client Receiving Response Headers and Trailers

A client interceptor can wrap the listener to observe returned metadata. `onHeaders(...)` receives initial response headers; `onClose(...)` receives the final status and trailers:

```java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.ForwardingClientCallListener;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import io.grpc.Status;

public final class ResponseMetadataClientInterceptor
        implements ClientInterceptor {

    private static final Metadata.Key<String> SERVER_VERSION =
        Metadata.Key.of(
            "x-server-version",
            Metadata.ASCII_STRING_MARSHALLER);
    private static final Metadata.Key<String> RESPONSE_REQUEST_ID =
        Metadata.Key.of(
            "x-response-request-id",
            Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions options,
            Channel next) {

        ClientCall<ReqT, RespT> delegate =
            next.newCall(method, options);

        return new ForwardingClientCall.SimpleForwardingClientCall<ReqT, RespT>(
                delegate) {
            @Override
            public void start(
                    ClientCall.Listener<RespT> responseListener,
                    Metadata requestHeaders) {

                ClientCall.Listener<RespT> listener =
                    new ForwardingClientCallListener
                        .SimpleForwardingClientCallListener<RespT>(
                            responseListener) {
                        @Override
                        public void onHeaders(Metadata headers) {
                            String version = headers.get(SERVER_VERSION);
                            // You may record the version into telemetry/logs
                            // per allowlist; do not dump all headers.
                            super.onHeaders(headers);
                        }

                        @Override
                        public void onClose(Status status, Metadata trailers) {
                            String requestId =
                                trailers.get(RESPONSE_REQUEST_ID);
                            // Correlate requestId with logs when needed.
                            // Status remains the official RPC outcome.
                            super.onClose(status, trailers);
                        }
                    };

                super.start(listener, requestHeaders);
            }
        };
    }
}
```

This snippet only reads metadata and forwards callbacks. If the application needs to surface information back to the caller layer, pass the **extracted values** via a result object or telemetry mechanism; do not retain the mutable `Metadata` object for use after the callback.

The client should process status first. Custom trailers are auxiliary information: they may be absent, especially if the server/proxy terminates the call early or responds with trailers-only. Never treat `x-response-request-id` as proof of server authenticity; server identity is protected via TLS/mTLS and proper trust configuration.

## 5. Returned Metadata in Common Scenarios

| Scenario | What the client may receive | How to handle |
| --- | --- | --- |
| Successful unary | Headers, one message, trailers, and `OK` | Read server version in `onHeaders`, final status in `onClose` |
| Unary error before message | Possibly trailers-only with error status | Do not rely on initial headers or response message |
| Server streaming | Headers once, multiple messages, trailers when stream ends | Use headers for shared info; handle each message individually |
| Client/bidirectional streaming | Response headers when server starts replying, trailers at the end | Do not wait for trailers to process individual messages |
| Deadline expired or client cancelled | Corresponding status, metadata depending on termination path | Preserve status; custom trailers may be absent |
| Proxy/gateway rejected before server | May lack server-generated application metadata | Do not assume every response passed through the service interceptor |

Some ordering notes:

- The server sends initial headers only once. If the service calls `sendHeaders(...)`, that call must happen before the first message.
- The server sends trailers when closing the call. After closing, no further messages or metadata may be sent.
- The client receives message and metadata callbacks according to the gRPC lifecycle. `onClose(...)` signals call termination; do not process further messages after this callback.
- In streaming, trailers arrive only when the stream finishes, not after each message.

## 6. Designing Safe Response Metadata

Response metadata is often inspected by proxies, gateways, SDKs, and observability systems. Therefore, return only values the client genuinely needs.

**Recommended:**

- Server version or negotiated capability codes.
- Server-validated or server-generated request/correlation ID.
- Short, non-sensitive diagnostic codes to aid log correlation.
- Metadata required by the API contract with clear length limits.

**Avoid:**

- Access tokens, refresh tokens, cookies, or credentials.
- Stack traces, SQL queries, internal file paths, or implementation details.
- Personal data, tenant secrets, or large business payloads.
- Reserved gRPC keys such as `grpc-status`, `grpc-message`, or `grpc-timeout`.

Metadata travels over HTTP/2 headers/trailers and is subject to size limits from clients, servers, proxies, and load balancers. Never use response trailers as a payload channel. If rich business error structures are needed, consider error messages or error details per API design, while gRPC status still denotes the RPC outcome.

TLS protects metadata on encrypted connections; if a proxy terminates TLS, evaluate the proxy–server hop as well. Never log entire trailers or headers if there is risk of sensitive data. Use an allowlist of safe keys.

## 7. Testing Response Metadata

Unit tests can verify key creation and value reading, but **integration tests through a server/client** are required to confirm headers/trailers are actually sent and client callbacks receive them at the right stage.

| Test case | Setup | Expectation |
| --- | --- | --- |
| Initial headers | Server sends `x-server-version` before `onNext` | Client reads it in `onHeaders` |
| Trailers on success | Server closes call with `x-response-request-id` | Client reads it in `onClose` alongside `OK` |
| Trailers on error | Service finishes with an error status | Original status unchanged; custom trailer present only if server added it |
| Trailers-only | Server/gateway rejects before response message | Client handles status even without initial headers |
| Streaming | Server sends multiple messages then closes stream | Headers arrive once, trailers at the end |
| Duplicate header | Server or interceptor writes a duplicate custom key | Client/server handle per defined policy |
| Missing metadata | Server does not send custom key | Client handles absent value gracefully |
| TLS/proxy | Call over production-like transport | Metadata reaches the right client, no secrets leaked |

### Example Test for Trailer Reception Logic

The core of a client listener can be tested using a fake listener:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import io.grpc.Metadata;
import io.grpc.Status;
import org.junit.jupiter.api.Test;

class ResponseMetadataTest {
    private static final Metadata.Key<String> REQUEST_ID =
        Metadata.Key.of(
            "x-response-request-id",
            Metadata.ASCII_STRING_MARSHALLER);

    @Test
    void readsRequestIdFromTrailersAndKeepsStatus() {
        Metadata trailers = new Metadata();
        trailers.put(REQUEST_ID, "req-42");

        Status status = Status.OK;
        assertEquals("req-42", trailers.get(REQUEST_ID));
        assertEquals(Status.Code.OK, status.getCode());
    }
}
```

This small test only checks metadata and status locally. Integration tests need to spin up an in-process gRPC server/channel or real transport, register the server interceptor, send an RPC, and assert `onHeaders`/`onClose` callbacks. For TLS, proxies, and trailers-only errors, test in an environment matching production since in-process transport does not simulate full HTTP/2 behavior.

## 8. Practice Exercise

An `OrderService.GetOrder` written with Spring gRPC needs to return the server version in response headers and the request ID in response trailers. The client SDK must collect both values to support diagnostics.

**Requirements:**

1. The server sends `x-server-version` via `ServerCallStreamObserver.sendHeaders(...)` before the first response message.
2. A server interceptor wraps `ServerCall.close(...)` to add `x-response-request-id` if the request ID has been validated.
3. A client interceptor reads `x-server-version` in `onHeaders(...)` and `x-response-request-id` in `onClose(status, trailers)`.
4. Preserve the original status when adding trailers; test both `OK` and error statuses.
5. Add a streaming test confirming headers are sent only at the start of the stream and trailers only when the stream closes.
6. Add a trailers-only or gateway error test to ensure the client does not assume `onHeaders(...)` is always invoked.

**Self-check questions:**

- What is the difference between response headers and response trailers?
- When must a service call `ServerCallStreamObserver.sendHeaders(...)`?
- In which callbacks does the client read initial response metadata and trailers?
- Why can you not rely on response headers to handle every RPC error?
- What must an interceptor wrapping `ServerCall.close(...)` preserve?
- Why should response metadata not contain access tokens or stack traces?
- With server streaming, is metadata re-sent after each response message?

**Key takeaway:** Metadata from server to client has two main reception points: **initial response headers** at the start of the response and **trailers** when the RPC ends. The server uses header-sending APIs or wraps call closure; the client reads headers in `onHeaders(...)` and trailers alongside status in `onClose(...)`. In Spring gRPC, preserve the original status, treat custom metadata as auxiliary data, handle trailers-only cases, and test both unary and streaming RPCs.
