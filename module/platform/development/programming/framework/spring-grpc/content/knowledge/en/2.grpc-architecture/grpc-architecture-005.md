# Metadata and headers in a call

## Learning objectives

After this lesson, you can:

- Explain what **metadata** in gRPC is and distinguish **request headers**, **response headers**, and **trailers** from **protobuf request/response messages**.
- Describe HTTP/2 pseudo-headers, runtime-managed gRPC headers, and custom metadata traveling through a unary or streaming call.
- Declare, read, and write metadata using **io.grpc.Metadata** in Java; distinguish **ASCII metadata** from **binary metadata** with the **-bin** suffix.
- Attach metadata on the client using **ClientInterceptor**, read metadata on the server using **ServerInterceptor**, and propagate a request ID through **io.grpc.Context**.
- Understand the relationship between **authorization**, **deadlines**, **grpc-status**, **TLS**, and header size limits.
- Design integration tests that verify metadata propagation, handle errors cleanly, and prevent leaking sensitive information.

## 1. What is metadata in Spring gRPC architecture?

In the **SPRING_GRPC** module, clients and servers exchange business data via **Protocol Buffers** and call each other through unary or streaming RPCs. Alongside protobuf messages, each call also needs contextual information such as trace IDs, authentication tokens, locale, deadlines, or diagnostic details. gRPC calls this supplemental information **metadata**.

Metadata is a set of **key–value** pairs accompanying an RPC, typically mapped onto **HTTP/2 headers** and **trailers**. It is not a field that automatically appears in **.proto**. Two clients calling the same RPC method can send different metadata without changing the **GetOrderRequest** or **GetOrderResponse** types.

Suppose a Spring service calls:

~~~proto
syntax = "proto3";

package shop.orders.v1;

option java_package = "com.example.orders.v1";
option java_multiple_files = true;

service OrderService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);
}

message GetOrderRequest {
  string order_id = 1;
}

message GetOrderResponse {
  string order_id = 1;
  string state = 2;
}
~~~

In a specific call, the client might send:

- **Request message**: **order_id = "A-102"**.
- **Metadata**: **x-request-id = "req-7f2a"**, **authorization = "Bearer …"**.
- **Deadline/call options**: maximum time limit for the RPC, which the runtime can convey via **grpc-timeout**.

The server returns **GetOrderResponse** or an error gRPC status. It can also return metadata in **initial response headers** and **trailers**, such as service version or safe diagnostic details.

**Important distinction:** protobuf messages hold schema-defined business data; metadata holds call context; gRPC status determines whether the call succeeded or failed. Do not use metadata as storage for large payloads or as a replacement for message contracts.

## 2. Where does metadata appear in an RPC?

A unary RPC over HTTP/2 typically looks like:

~~~mermaid
sequenceDiagram
    participant C as Spring client + stub
    participant H as gRPC Channel/HTTP2
    participant S as gRPC server
    C->>H: Request metadata + GetOrderRequest
    H->>S: HEADERS (path, content-type, x-request-id)
    H->>S: DATA (protobuf request)
    Note over H,S: Client finishes send direction
    S-->>H: HEADERS (response metadata)
    S-->>H: DATA (GetOrderResponse)
    S-->>H: HEADERS trailers (grpc-status, metadata)
    H-->>C: Message + final status
~~~

Lifecycle table:

| Stage | Kind of information | Who typically uses it? |
| --- | --- | --- |
| **Request headers** | RPC path, content type, timeout, custom metadata, authentication | Server runtime, server interceptor, handler via context |
| **Request DATA** | One or more encoded request messages | Deserializer and implementation |
| **Response headers** (*initial metadata*) | Server-side metadata returned before payload | Client interceptor/low-level callback |
| **Response DATA** | One or more response messages | Client stub/observer |
| **Response trailers** (*trailing metadata*) | **grpc-status**, sometimes **grpc-message**, end-of-call custom metadata | Client runtime, interceptor, error handling |

Both response headers and trailers are transmitted using HTTP/2 **HEADERS frames**, yet they differ in **timing** and **role**. Trailers arrive at the end of the RPC. If a call fails very early, the server can return **trailers-only**, meaning the response has only a single final HEADERS block with status and no response DATA or separate initial headers.

With **streaming**, client and server can exchange many messages in the DATA phase, but initial metadata still belongs to **when the RPC opens**, and trailers still belong to **when the RPC ends**. There is no standard mechanism in gRPC for sending fresh metadata headers per message mid-stream. To send information that varies per message, declare fields inside the protobuf message.

## 3. Distinguishing three header groups

Not every header appearing on HTTP/2 is custom metadata that an application can freely invent.

### 3.1. HTTP/2 pseudo-headers

Example of a gRPC request going to **OrderService**:

~~~text
:method: POST
:scheme: https
:path: /shop.orders.v1.OrderService/GetOrder
:authority: orders.internal.example:443
~~~

Fields starting with **:** are **HTTP/2 pseudo-headers**, describing the request/authority. The gRPC runtime and transport manage them. Do not add these names manually via **Metadata.Key** to change the target service.

**:path** reflects the protobuf package, service, and method. It does **not** come from **java_package**; host/port belong to Channel/transport configuration. When deploying behind a proxy, ensure the proxy preserves the RPC path and supports HTTP/2.

### 3.2. Headers defined by gRPC

Common protocol headers/metadata:

| Header or metadata | Meaning | Typical manager |
| --- | --- | --- |
| **content-type: application/grpc** | Identifies content as gRPC | Runtime |
| **te: trailers** | Indicates support for HTTP trailers | Runtime/transport |
| **grpc-timeout** | Remaining deadline duration in protocol-specified units | Runtime from deadline/call options |
| **grpc-encoding** | Message compression algorithm used | Runtime, depending on compression config |
| **grpc-accept-encoding** | Compression formats supported by the receiver | Runtime |
| **user-agent** | Client/runtime info if sent | Runtime |
| **grpc-status** | RPC termination code, usually in response trailers | Runtime and server status |
| **grpc-message** | Error description, if provided | Runtime/server |

**grpc-*** headers belong to a namespace reserved by gRPC. Applications should not define custom metadata starting with **grpc-**, and should not write **grpc-status** manually instead of using the **Status** API.

**Deadlines** are configured at the call level, such as **stub.withDeadlineAfter(...)**. gRPC can express the remaining time via **grpc-timeout**; the application does not need to compute and insert **grpc-timeout** into a Metadata map itself.

### 3.3. Custom application metadata

Fields like the following can be agreed upon by the application:

~~~text
x-request-id: req-7f2a
x-tenant-id: tenant-a
x-client-version: 2026.11
authorization: Bearer <redacted>
~~~

These are examples of naming and value conventions. **x-** is not mandatory in gRPC; custom metadata names simply must follow transport/library rules and avoid reserved fields. **authorization** is a familiar field passed via metadata, though real systems should use **CallCredentials**/proper authentication mechanisms.

Do not trust an **x-tenant-id** value sent by the client if the server uses it for authorization. The server must authenticate the identity and verify which tenants the caller is allowed to access. Metadata is merely a transport channel for data, not authentication on its own.

## 4. Rules for metadata names, types, and values

In gRPC, metadata keys are ASCII names, usually using **lowercase letters**, digits, and valid characters like **-**, **_**, **.**. HTTP/2 requires lowercase header names; grpc-java normalizes/manages them per library rules. Keep names simple, clear, and consistent.

There are two groups of metadata values:

| Group | Naming convention | Application data | grpc-java API |
| --- | --- | --- | --- |
| **ASCII metadata** | Normal name, e.g., **x-request-id** | Protocol-valid ASCII string | **Metadata.ASCII_STRING_MARSHALLER** |
| **Binary metadata** | Name must end with **-bin**, e.g., **x-trace-bin** | Byte array | **Metadata.BINARY_BYTE_MARSHALLER** |

Example Java key declarations:

~~~java
import io.grpc.Metadata;

public final class RpcMetadataKeys {
    private RpcMetadataKeys() {}

    public static final Metadata.Key<String> REQUEST_ID =
            Metadata.Key.of(
                    "x-request-id",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Metadata.Key<String> CLIENT_VERSION =
            Metadata.Key.of(
                    "x-client-version",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Metadata.Key<byte[]> TRACE_BYTES =
            Metadata.Key.of(
                    "x-trace-bin",
                    Metadata.BINARY_BYTE_MARSHALLER);
}
~~~

For binary metadata, gRPC transport over HTTP/2 uses **base64** representation when encoding bytes into a header value. In Java, you work directly with **byte[]**; do not base64-encode manually before passing to **BINARY_BYTE_MARSHALLER**, as that can cause double encoding or misinterpretation between client and server.

**ASCII_STRING_MARSHALLER** is for metadata-safe ASCII, not a mechanism for arbitrary Unicode strings. If you need to send Vietnamese text or binary structures, prefer a protobuf field in the message; or use binary metadata when it is truly RPC context.

### 4.1. Using Metadata in Java

~~~java
Metadata metadata = new Metadata();

metadata.put(RpcMetadataKeys.REQUEST_ID, "req-7f2a");
metadata.put(RpcMetadataKeys.CLIENT_VERSION, "2026.11");
metadata.put(
        RpcMetadataKeys.TRACE_BYTES,
        new byte[] {0x01, 0x02, 0x03});

String requestId = metadata.get(RpcMetadataKeys.REQUEST_ID);
byte[] trace = metadata.get(RpcMetadataKeys.TRACE_BYTES);
~~~

**Metadata** is a mutable data container used by gRPC for each headers/trailers exchange. Do not share one mutable object and mutate it concurrently across multiple RPCs without synchronization. Keys can repeat in the protocol and the API can read multiple values; if business logic requires a single request ID, define a rule for duplicate values rather than assuming safety just because **get()** returns one value.

For security-sensitive data, avoid printing **Metadata.toString()** or all headers to logs. Tokens, cookies, customer details, and correlation IDs can inadvertently appear in logs/traces.

## 5. Attaching request metadata from a Spring client

Clients often want to generate a **new request ID per RPC**. You can use a **ClientInterceptor** to intercept call initialization and add headers centrally.

### 5.1. ClientInterceptor sending a request ID

~~~java
package com.example.orders.client;

import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import java.util.UUID;

public final class RequestIdClientInterceptor
        implements ClientInterceptor {

    private static final Metadata.Key<String> REQUEST_ID =
            Metadata.Key.of(
                    "x-request-id",
                    Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        ClientCall<ReqT, RespT> delegate =
                next.newCall(method, callOptions);

        return new ForwardingClientCall.SimpleForwardingClientCall
                <ReqT, RespT>(delegate) {

            @Override
            public void start(
                    Listener<RespT> responseListener,
                    Metadata headers) {

                headers.put(REQUEST_ID, UUID.randomUUID().toString());
                super.start(responseListener, headers);
            }
        };
    }
}
~~~

At **start(...)**, the interceptor receives the RPC's headers container and adds **x-request-id**. A new UUID is generated **for every call**, suitable for tracing independent RPCs. In distributed systems, you sometimes need to **propagate** an existing correlation ID instead of generating a new one at every hop; fetching the ID from request context must be designed accordingly.

You can build a stub using the interceptor in Spring configuration:

~~~java
package com.example.orders.client;

import com.example.orders.v1.OrderServiceGrpc;
import io.grpc.ClientInterceptors;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderGrpcClientConfig {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel orderChannel() {
        // Use plaintext only in local examples.
        return ManagedChannelBuilder.forAddress("localhost", 9090)
                .usePlaintext()
                .build();
    }

    @Bean
    OrderServiceGrpc.OrderServiceBlockingStub orderStub(
            ManagedChannel orderChannel) {

        return OrderServiceGrpc.newBlockingStub(
                ClientInterceptors.intercept(
                        orderChannel,
                        new RequestIdClientInterceptor()));
    }
}
~~~

**ClientInterceptors.intercept(...)** creates a Channel wrapper for the stub that inserts logic when sending calls; it does not open a new TCP connection. **ManagedChannel** is still shared and must be shut down when the Spring context closes.

For projects using **Spring gRPC** auto-configuration, registering interceptors/stub beans may be provided by the framework; follow the API of your version to avoid double configuration. The example above illustrates the core grpc-java layer beneath Spring.

### 5.2. When to use MetadataUtils?

grpc-java provides helpers like **MetadataUtils.newAttachHeadersInterceptor(metadata)** to attach a pre-built metadata set. This helper is convenient in tests or when values are relatively static.

For rotating tokens, request IDs, or data that varies per RPC, you need a **per-call** update mechanism. Avoid keeping a shared mutable **Metadata** object and mutating it across threads: that can send the wrong token or request ID. A **ClientInterceptor** generating values inside **start()**, or **CallCredentials** for authentication, is usually much clearer.

## 6. Authentication and CallCredentials

Authentication credentials such as bearer tokens are commonly sent via metadata, yet issuing, refreshing, and attaching tokens requires a clear mechanism. **CallCredentials** is grpc-java's abstraction for **per-call** credentials. It is much better suited than hardcoding tokens in Channel configuration or inside protobuf request messages.

Minimal example fetching a token from a **Supplier** and adding **authorization**:

~~~java
package com.example.orders.client;

import io.grpc.CallCredentials;
import io.grpc.Metadata;
import io.grpc.Status;
import java.util.concurrent.Executor;
import java.util.function.Supplier;

public final class BearerTokenCredentials extends CallCredentials {

    private static final Metadata.Key<String> AUTHORIZATION =
            Metadata.Key.of(
                    "authorization",
                    Metadata.ASCII_STRING_MARSHALLER);

    private final Supplier<String> tokenSupplier;

    public BearerTokenCredentials(Supplier<String> tokenSupplier) {
        this.tokenSupplier = tokenSupplier;
    }

    @Override
    public void applyRequestMetadata(
            RequestInfo requestInfo,
            Executor appExecutor,
            MetadataApplier applier) {

        appExecutor.execute(() -> {
            try {
                String token = tokenSupplier.get();

                if (token == null || token.isBlank()) {
                    applier.fail(
                            Status.UNAUTHENTICATED
                                    .withDescription(
                                            "No token available for RPC"));
                    return;
                }

                Metadata headers = new Metadata();
                headers.put(AUTHORIZATION, "Bearer " + token);
                applier.apply(headers);
            } catch (Exception ex) {
                applier.fail(
                        Status.UNAUTHENTICATED
                                .withDescription(
                                        "Failed to obtain token for RPC")
                                .withCause(ex));
            }
        });
    }
}
~~~

Attaching credentials to a stub for a call:

~~~java
GetOrderResponse response = stub
        .withCallCredentials(
                new BearerTokenCredentials(tokenSupplier))
        .withDeadlineAfter(2, TimeUnit.SECONDS)
        .getOrder(
                GetOrderRequest.newBuilder()
                        .setOrderId("A-102")
                        .build());
~~~

In this example, **stub** is **OrderServiceGrpc.OrderServiceBlockingStub** and **tokenSupplier** is an application-provided **Supplier<String>**; you will also need to import **java.util.concurrent.TimeUnit** and the generated request/response classes.

Points that must hold:

- **TLS/mTLS** protects the transport; tokens on the wire cannot be considered safe if sent over plaintext to untrusted environments.
- **CallCredentials** attaches credentials, yet **the server must still verify the token, identity, permission scope, and expiration**.
- Tokens must not appear in logs, exception descriptions, metric labels, or tracing span attributes.
- Credential providers must handle expired tokens, token-fetch errors, and controlled cancellation; the example above only illustrates attaching headers.

**Do not manually set authorization headers inside every business method** if your organization already has a unified credential mechanism. Authentication should be implemented consistently, tested, and backed by a rotation policy.

## 7. Reading request metadata with ServerInterceptor

On the server side, the **ServerInterceptor** API has **interceptCall(...)** which receives the RPC's **Metadata headers**. Interceptors are ideal for capturing request IDs, authenticating callers, enforcing limits, or propagating context to handlers.

### 7.1. Reading a request ID and propagating it via gRPC Context

~~~java
package com.example.orders.server;

import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class RequestIdServerInterceptor
        implements ServerInterceptor {

    private static final Metadata.Key<String> REQUEST_ID =
            Metadata.Key.of(
                    "x-request-id",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Context.Key<String> REQUEST_ID_CONTEXT =
            Context.key("request-id");

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String requestId = headers.get(REQUEST_ID);

        if (requestId == null || requestId.isBlank()) {
            call.close(
                    Status.INVALID_ARGUMENT.withDescription(
                            "Missing x-request-id"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        Context context = Context.current()
                .withValue(REQUEST_ID_CONTEXT, requestId);

        return Contexts.interceptCall(context, call, headers, next);
    }
}
~~~

In this example, the server requires a request ID to demonstrate validation. **In real designs, the system may generate a request ID at ingress when the client omits one**; choosing to accept or reject is an application policy, not a gRPC rule.

grpc-java's **Context** carries data along the RPC execution context. It lets handlers read the request ID without adding **request_id** to every protobuf message:

~~~java
String requestId =
        RequestIdServerInterceptor.REQUEST_ID_CONTEXT.get();
~~~

The value is accessible within callbacks running under the corresponding gRPC Context. When offloading work to another executor/thread, you must **propagate or re-attach the Context** properly; do not assume an arbitrary **ThreadLocal** will follow the request across threads automatically.

The server must distinguish a **correlation ID** from authenticated identity. An **x-request-id** header sent by a caller does not prove identity; you may need to sanitize its length/characters and regenerate it if untrusted.

### 7.2. Registering an interceptor with a Spring gRPC server

Example using Spring-managed grpc-java ServerBuilder:

~~~java
package com.example.orders.server;

import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.ServerInterceptors;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderGrpcServerConfig {

    @Bean(initMethod = "start", destroyMethod = "shutdown")
    Server orderServer(OrderEndpoint endpoint) {
        return ServerBuilder.forPort(9090)
                .addService(
                        ServerInterceptors.intercept(
                                endpoint,
                                new RequestIdServerInterceptor()))
                .build();
    }
}
~~~

**OrderEndpoint** here is an implementation of the **OrderServiceGrpc.OrderServiceImplBase** base class; it can be managed with **@Component**. **ServerInterceptors.intercept(...)** attaches the interceptor to the registered service.

A Spring gRPC starter may provide automatic service/interceptor registration; do not start a second manual server on the same port. When adding multiple interceptors, verify their application order so authentication, logging, and error handling execute as intended.

### 7.3. When should metadata enter the handler?

Common choices:

| Need | Suitable approach |
| --- | --- |
| Track **x-request-id** through business layers | Server interceptor reads it and places it into **Context** or a request-scoped abstraction |
| Authenticate a token | Security interceptor / authentication component, then pass the authenticated principal |
| Business data that must be stored or returned | Put it in the protobuf message |
| Time limits | Use gRPC Context deadline/cancellation |
| Record latency/status metrics | Interceptor or framework instrumentation |

Avoid making business services depend directly on every header name; create clear abstractions for authenticated context and what the service truly needs.

## 8. Sending response headers and trailers from the server

The server can send metadata back **before messages** or **when the RPC ends**. In grpc-java, working with both stages is usually done via **ServerCall** inside an interceptor.

### 8.1. ServerInterceptor writing headers and trailers

Example adding a version name to initial headers and a node identifier to trailers:

~~~java
package com.example.orders.server;

import io.grpc.ForwardingServerCall;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class ResponseMetadataServerInterceptor
        implements ServerInterceptor {

    private static final Metadata.Key<String> SERVICE_VERSION =
            Metadata.Key.of(
                    "x-service-version",
                    Metadata.ASCII_STRING_MARSHALLER);

    private static final Metadata.Key<String> SERVER_NODE =
            Metadata.Key.of(
                    "x-server-node",
                    Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata requestHeaders,
            ServerCallHandler<ReqT, RespT> next) {

        ServerCall<ReqT, RespT> decorated =
                new ForwardingServerCall
                        .SimpleForwardingServerCall<ReqT, RespT>(call) {

                    @Override
                    public void sendHeaders(Metadata responseHeaders) {
                        responseHeaders.put(
                                SERVICE_VERSION,
                                "orders-v1");
                        super.sendHeaders(responseHeaders);
                    }

                    @Override
                    public void close(Status status, Metadata trailers) {
                        trailers.put(
                                SERVER_NODE,
                                "node-a");
                        super.close(status, trailers);
                    }
                };

        return next.startCall(decorated, requestHeaders);
    }
}
~~~

**sendHeaders(...)** runs when the runtime prepares to send initial metadata. **close(...)** is where status/trailers are emitted. Custom metadata **x-service-version** and **x-server-node** are illustrative only: do not expose internal node names, topology, or sensitive version details externally if operational policy forbids it.

The interceptor can be registered just like the example in section 7. On errors occurring **before the handler sends headers**, some paths return **trailers-only**, so clients must not assume initial response headers are always present separately.

### 8.2. gRPC status belongs to RPC termination

The server reports errors via the **Status** API, for example:

~~~java
responseObserver.onError(
        Status.NOT_FOUND
                .withDescription("Order not found")
                .asRuntimeException());
~~~

The runtime closes the RPC with that status. **grpc-status** is part of the protocol and usually travels in trailers; the application should not manually put **"grpc-status": "5"** into custom Metadata. On success, call **onNext(...)** then **onCompleted()** for unary; on failure, call **onError()**, and never send anything further after a terminal event.

Structured business error details can use **google.rpc.Status** / error details if client and server support it. This differs from raw custom headers and from **grpc-message**, which should never contain stack traces or tokens.

## 9. Client reading initial headers and trailers

Client stubs usually return a **protobuf response** or throw **StatusRuntimeException**. To inspect response headers and trailers on both successful and failed calls, use a **ClientInterceptor** with listener callbacks.

The example below reads two custom metadata keys:

~~~java
package com.example.orders.client;

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

    private static final Metadata.Key<String> SERVICE_VERSION =
            Metadata.Key.of(
                    "x-service-version",
                    Metadata.ASCII_STRING_MARSHALLER);

    private static final Metadata.Key<String> SERVER_NODE =
            Metadata.Key.of(
                    "x-server-node",
                    Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions options,
            Channel next) {

        return new ForwardingClientCall.SimpleForwardingClientCall
                <ReqT, RespT>(next.newCall(method, options)) {

            @Override
            public void start(
                    Listener<RespT> listener,
                    Metadata outgoingHeaders) {

                Listener<RespT> decorated =
                        new ForwardingClientCallListener
                                .SimpleForwardingClientCallListener<RespT>(
                                        listener) {

                            @Override
                            public void onHeaders(Metadata headers) {
                                String version =
                                        headers.get(SERVICE_VERSION);
                                // Forward value to a safe metric/log system.
                                super.onHeaders(headers);
                            }

                            @Override
                            public void onClose(
                                    Status status,
                                    Metadata trailers) {
                                String node =
                                        trailers.get(SERVER_NODE);
                                // Handle status and node if policy permits.
                                super.onClose(status, trailers);
                            }
                        };

                super.start(decorated, outgoingHeaders);
            }
        };
    }
}
~~~

The snippet above shows **where** to read metadata inside callbacks; the **version**/**node** variables are unused to avoid baking logging/metrics decisions into sample code. In real applications, forward needed data to tracing/metrics or a collector scoped per RPC.

If you only need **trailers on error** with a blocking stub, you can use:

~~~java
try {
    stub.getOrder(request);
} catch (io.grpc.StatusRuntimeException ex) {
    io.grpc.Metadata trailers = ex.getTrailers();
    // trailers can be null; check before reading.
    if (trailers != null) {
        String node = trailers.get(SERVER_NODE);
    }
}
~~~

Here **SERVER_NODE** is a previously defined **Metadata.Key<String>**. **StatusRuntimeException.getTrailers()** is not guaranteed to be non-null (for example, if the error occurred before receiving any response). To capture headers/trailers on successful RPCs, use an interceptor or appropriate capture mechanism rather than relying only on exceptions.

Never use **client-visible headers** for security decisions such as self-asserted tenant/access privileges. Authorization decisions must be enforced by trusted mechanisms on the server.

## 10. Deadlines, cancellation, streaming, and metadata

### 10.1. Deadlines are not application-managed custom headers

The client can configure:

~~~java
GetOrderResponse response = stub
        .withDeadlineAfter(2, TimeUnit.SECONDS)
        .getOrder(
                GetOrderRequest.newBuilder()
                        .setOrderId("A-102")
                        .build());
~~~

**TimeUnit** is from **java.util.concurrent.TimeUnit**. In gRPC, deadlines are managed at the call-options/context layer; **grpc-timeout** expresses the remaining duration as a protocol header when needed. The server receives the remaining processing budget and can observe cancellation when the deadline expires.

If the client receives **DEADLINE_EXCEEDED**, never assume the request was definitely not processed. The server may have performed a write before the response reached the client; use idempotency/reconciliation for RPCs with side effects.

### 10.2. Headers have a different lifecycle from streaming messages

In a server-streaming RPC, the server may send thousands of response messages, yet it cannot continuously alter initial metadata after headers have been sent. Information that updates per message must reside inside the protobuf message.

Example:

~~~proto
message OrderEvent {
  string order_id = 1;
  string event_id = 2;
  int64 sequence = 3;
  string state = 4;
}
~~~

**event_id** and **sequence** are per-event data. If placed in initial metadata, the client only sees the values from the start of the RPC and misses mid-stream updates.

Client-streaming/bidirectional streaming also has **half-close**: **onCompleted()** on the request observer marks the end of outbound client data; final trailers/status still arrive only when the RPC finishes. Do not treat request half-close as meaning response/trailers are already ready.

### 10.3. Call cancellation and connection errors

Cancelling an RPC terminates that call's stream without closing the shared Channel. Losing a connection can affect many in-flight RPCs; in that case status and trailers may not arrive intact. Therefore, clients should be prepared for **absent server response metadata**, even after sending request headers.

## 11. Security and operational limits

Metadata helps carry context, yet it is also a common place for security, reliability, and performance issues.

### 11.1. Avoiding sensitive data exposure

- **Never log raw request/response metadata** if it contains authorization headers, cookies, session IDs, or personal data.
- Use **TLS** on the link between client and server, or mTLS when mutual authentication is required. Interceptors only add metadata; they **do not encrypt** the connection.
- **Verify identity and authorization on the server**. A metadata key like **x-user-role: admin** from the caller cannot grant access by itself.
- Only forward headers that are genuinely needed; do not send tokens to unrelated backends or proxies.
- When returning errors, keep descriptions safe; never expose access tokens, stack traces, internal paths, or infrastructure details.

Tokens must have their own lifecycle management. When using a gateway/proxy, verify where TLS terminates, how the gateway forwards metadata, and the trust boundary between gateway and backend.

### 11.2. Header size and count limits

Headers and trailers must be encoded inside **HTTP/2 header blocks**. Peers and libraries can enforce metadata size limits; the exact limit depends on server, client, and proxy configuration. Exceeding metadata limits can fail calls, sometimes mapped to **RESOURCE_EXHAUSTED** or a transport error depending on the situation.

Therefore:

- Never place large lists, long JSON payloads, certificates, or binary documents in metadata. Use protobuf messages or dedicated storage.
- For custom headers, validate length/format, count, and validity at ingress.
- Binary metadata still counts toward the header budget, including transport encoding overhead.
- Set separate message limits for protobuf payloads; **header limits** and **message size limits** are distinct mechanisms.

### 11.3. Beware of normalization and duplicate keys

HTTP/2 header names are lowercase; gRPC custom metadata keys should likewise consistently use lowercase. Keys like **X-Request-Id** and **x-request-id** may be normalized by libraries, but avoid relying on that conversion in your design.

A key can appear multiple times. If the application expects **a single unique value**, define a duplicate-handling policy instead of implicitly taking the first or last value. For authorization, deciding how to accept and check multi-valued headers must align with security policy.

## 12. End-to-end metadata testing

Testing handlers via direct Java calls skips interceptor-based metadata handling. Use **grpc-inprocess** to test request headers, routing, and statuses through the gRPC runtime without opening network ports.

The JUnit 5 example below creates a minimal unary service, attaches a server interceptor that checks the request ID, and calls it through a client interceptor:

~~~java
package com.example.orders;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.example.orders.v1.GetOrderRequest;
import com.example.orders.v1.GetOrderResponse;
import com.example.orders.v1.OrderServiceGrpc;
import io.grpc.ClientInterceptors;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.ServerInterceptors;
import io.grpc.Status;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.Test;

class MetadataIntegrationTest {

    @Test
    void interceptorPassesRequestIdToServerContext() throws Exception {
        String serverName = InProcessServerBuilder.generateName();

        OrderServiceGrpc.OrderServiceImplBase handler =
                new OrderServiceGrpc.OrderServiceImplBase() {
                    @Override
                    public void getOrder(
                            GetOrderRequest request,
                            StreamObserver<GetOrderResponse> observer) {

                        String id =
                                RequestIdServerInterceptor
                                        .REQUEST_ID_CONTEXT.get();

                        // Use context to verify the interceptor ran.
                        if (id == null || id.isBlank()) {
                            observer.onError(
                                    Status.INTERNAL
                                            .withDescription(
                                                    "Missing request context")
                                            .asRuntimeException());
                            return;
                        }

                        observer.onNext(
                                GetOrderResponse.newBuilder()
                                        .setOrderId(request.getOrderId())
                                        .setState("PENDING")
                                        .build());
                        observer.onCompleted();
                    }
                };

        Server server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(
                        ServerInterceptors.intercept(
                                handler,
                                new RequestIdServerInterceptor()))
                .build()
                .start();

        ManagedChannel channel = InProcessChannelBuilder.forName(
                        serverName)
                .directExecutor()
                .build();

        try {
            OrderServiceGrpc.OrderServiceBlockingStub stub =
                    OrderServiceGrpc.newBlockingStub(
                            ClientInterceptors.intercept(
                                    channel,
                                    new RequestIdClientInterceptor()));

            GetOrderResponse response = stub.getOrder(
                    GetOrderRequest.newBuilder()
                            .setOrderId("A-102")
                            .build());

            assertEquals("A-102", response.getOrderId());
            assertEquals("PENDING", response.getState());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

This test assumes **RequestIdClientInterceptor** and **RequestIdServerInterceptor** from sections 5 and 7 are declared in matching packages/imports. Compatible **grpc-inprocess**, grpc-java, and JUnit 5 dependencies are required. **directExecutor()** is only suitable for simple tests and does not fully simulate real concurrency or transport behavior.

Additional scenarios to test:

| Test | Expectation |
| --- | --- |
| Call server **without x-request-id** per example policy | **INVALID_ARGUMENT**; handler does not execute |
| Call with valid request ID | Server reads the exact value via **Context** |
| Server returns custom initial headers/trailers | Client interceptor observes them in the right callbacks |
| Server returns **NOT_FOUND** | Client receives accurate gRPC status; trailers may or may not be present |
| Missing/expired token | **UNAUTHENTICATED**, token not leaked in messages/logs |
| Oversized or malformed header | Call rejected according to real limits/config |
| Streaming completion/cancellation | Initial metadata stays constant across messages; final status/trailers handled cleanly when present |
| Backend behind reverse proxy | Proxy forwards permitted metadata accurately and uses HTTP/2/TLS |

**In-process** testing validates metadata/interceptor APIs. It **does not prove** TLS, ALPN, proxy header limits, gRPC-Web translation, or multi-backend behavior are correct. For those, add tests using a real network transport and corresponding infrastructure.

## 13. Common mistakes and troubleshooting

| Symptom | Possible cause | Remediation |
| --- | --- | --- |
| Server reads **headers.get(key) == null** | Client did not attach metadata, interceptor not registered, key name mismatch | Check interceptor wiring and key names/marshallers on both sides |
| **UNAUTHENTICATED** despite valid request message | Missing/expired/wrong-audience token; credentials not invoked | Verify CallCredentials, TLS, and server authentication policy |
| **PERMISSION_DENIED** after successful authentication | Caller lacks permission on the resource | Check authorization based on the authenticated principal |
| Duplicate Request ID across RPCs | Reused mutable metadata or generated ID at bean startup | Generate/propagate ID per call; verify scope |
| Client sees no response headers | Server returned trailers-only with no separate initial headers | Allow headers to be absent and handle status/trailers |
| Client only checks HTTP **200** and assumes RPC succeeded | Not reading **grpc-status** | Handle StatusRuntimeException / onClose callback |
| Binary header decoded as garbled string | Used ASCII marshaller or wrong manual base64 encoding | Align on **-bin** key and BINARY_BYTE_MARSHALLER |
| Streaming tries to update headers per event | Metadata only exists at start/end of RPC | Put per-event fields in the protobuf message |
| Call fails when sending lots of metadata | Exceeded peer/proxy header limit | Reduce metadata, cap sizes, and measure header budget |
| Tracing loses context with custom executor | Not propagating gRPC **Context** | Wrap/re-attach Context or use proper instrumentation |
| Sensitive metadata appears in logs | Logging all request headers | Redact/allowlist keys; never log tokens |
| RPC works locally but fails through proxy | Proxy strips headers, misconfigured HTTP/2/TLS, auth setup | Check metadata forwarding policy and actual network path |

When troubleshooting, verify in order: **did the client create metadata?** → **is the interceptor attached to the right stub?** → **did transport/proxy forward the request?** → **did the server interceptor read the headers?** → **does the handler have the right Context?** → **were status/trailers returned?**. Layer-by-layer inspection pinpoints the root cause before tweaking configs.

## 14. Hands-on lab and self-check questions

### Hands-on lab: adding metadata to OrderService

1. From the **OrderService/GetOrder** contract in section 1, create a client and server running with Spring and grpc-java. Use a single **ManagedChannel** for multiple calls.
2. Add **RequestIdClientInterceptor** to generate **x-request-id** per RPC. Attach **RequestIdServerInterceptor**, read the value into **Context**, and verify tracing logic in the handler.
3. Have the server return **x-service-version** in initial headers and a non-sensitive custom trailer. Write **ResponseMetadataClientInterceptor** to capture both values.
4. Send a request without a request ID and verify the server rejects it per the example policy. Then change the policy to generate a request ID at ingress if missing, and describe the pros and cons of both approaches.
5. Add a bearer token using **CallCredentials** or a framework-supported auth mechanism. Test missing, expired, and under-privileged principal cases; never log tokens.
6. Set a 2-second deadline on **GetOrder**, simulate a slow server, and observe **DEADLINE_EXCEEDED**. Explain why you should not set **grpc-timeout** manually as custom Metadata.
7. Switch the method to server-streaming in a separate example, emitting multiple events; pass per-message changing data in protobuf fields rather than trying to modify initial headers.
8. Run in-process tests, then test over real TLS/proxy to verify metadata forwarding and header limits.

### Self-check questions

**1. How does metadata differ from protobuf messages?**  
Metadata travels in headers/trailers to carry **RPC** context; protobuf messages are data payloads structured by the **schema** declared in .proto.

**2. What information can gRPC request headers contain?**  
HTTP/2 pseudo-headers, protocol info such as **content-type** and **grpc-timeout**, and custom metadata like **x-request-id** or **authorization**.

**3. Should you define a custom header named grpc-status?**  
No. **grpc-status** belongs to the protocol and is handled by the runtime at RPC termination. The server uses the **Status** API to report errors.

**4. Why do binary metadata keys require the -bin suffix?**  
The suffix lets gRPC distinguish binary metadata from ASCII metadata and apply the corresponding transport encoding. In Java, use **BINARY_BYTE_MARSHALLER** with **byte[]**.

**5. Does a server-streaming RPC sending 100 messages send 100 sets of initial headers?**  
No. Initial metadata belongs to **one RPC**, and messages travel as DATA on the same stream. Data that varies per message belongs in the message payload.

**6. Can the client always read response headers when an RPC fails?**  
No. An error may produce **trailers-only** or fail before receiving any response metadata. Clients must handle missing headers/trailers.

**7. Why use CallCredentials for tokens instead of putting them in every request message?**  
Tokens are call authentication context requiring issuance, expiration, security, and per-call attachment. **CallCredentials** supports this without polluting business schemas.

**8. Why can't x-tenant-id be trusted as soon as the server reads the header?**  
Because callers can set metadata values themselves. The server must authenticate the caller and verify actual authorized scope before using a tenant for access decisions.

## Summary

In Spring gRPC, **metadata** carries RPC context through **request headers**, **response headers**, and **trailers**. Reserved HTTP/2 and gRPC fields belong to the runtime; custom application metadata is managed via **Metadata.Key**, **interceptors**, and **CallCredentials** where appropriate. **Protocol Buffers** request/response messages remain responsible for business data, while **grpc-status** conveys the final outcome. Good metadata design requires per-call scoping, token security, size limits, awareness of initial vs. trailing metadata, and testing both interceptors and real transport paths.
