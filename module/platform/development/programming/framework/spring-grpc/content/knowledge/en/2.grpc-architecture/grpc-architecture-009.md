# Interceptors on the client and server

## Learning objectives

After this lesson, you can:

- Explain interceptors as extension points for executing cross-cutting logic around an RPC.
- Distinguish the lifecycles and responsibilities of **ClientInterceptor** and **ServerInterceptor** in grpc-java.
- Attach metadata on the client, authenticate/authorize on the server, and propagate verified identity via **io.grpc.Context**.
- Observe status, latency, cancellation, and errors via callbacks without altering RPC behavior.
- Register interceptors with **ManagedChannel** and Spring-managed gRPC servers.
- Test interceptors on each side, control execution order, and avoid threading, metadata, and security pitfalls.

## 1. Where do interceptors sit in an RPC?

In **SPRING_GRPC**, generated stubs and the gRPC runtime convert Java calls into RPCs over HTTP/2. Applications often need to apply common behaviors across many methods: attaching request IDs, authenticating callers, recording latency, creating traces, or standardizing errors. **Interceptors** provide RPC-layer hooks for these concerns.

- **ClientInterceptor** runs while the client creates and executes an RPC. It can add request metadata, wrap response callbacks, and observe the terminal status.
- **ServerInterceptor** runs when the server receives an RPC, before invoking the service implementation. It can inspect metadata, authenticate callers, build context, and wrap server call callbacks.

~~~mermaid
sequenceDiagram
    participant App as Spring client service
    participant CI as ClientInterceptor
    participant Stub as Generated stub / Channel
    participant SI as ServerInterceptor
    participant Impl as Spring gRPC implementation
    App->>CI: Invoke RPC
    CI->>CI: Create request metadata
    CI->>Stub: Forward call
    Stub->>SI: HTTP/2 request
    SI->>SI: Inspect metadata / create Context
    SI->>Impl: Forward call
    Impl-->>SI: Response or Status
    SI-->>Stub: RPC result
    Stub-->>CI: Terminal callback
    CI-->>App: Return result to caller
~~~

Interceptors operate at the **RPC boundary** and do not replace business services. For example, an interceptor can verify a token and place the principal into Context; permission to view a specific order still needs to be checked in the service/domain layer based on that principal.

## 2. ClientInterceptor lifecycle and API

In grpc-java, **ClientInterceptor** implements:

~~~java
<ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
        MethodDescriptor<ReqT, RespT> method,
        CallOptions callOptions,
        Channel next);
~~~

Whenever a stub initiates an RPC, the interceptor can inspect **MethodDescriptor** (which method, request/response types, RPC type), **CallOptions** (deadline, credentials, and call options), and the next Channel. It returns a **ClientCall** for the runtime to use.

Key observation points:

| API/callback | Timing | Common use |
| --- | --- | --- |
| **interceptCall(...)** | When creating the call | Select logic by method, wrap ClientCall |
| **ClientCall.start(...)** | Starting the call | Add request headers, wrap listener |
| **sendMessage(...)** | Client sends a request message | Count messages/sizes at call level if needed |
| **halfClose()** | Client finishes send direction | Observe end of request stream |
| **cancel(...)** | Call cancelled from client | Record cancellation |
| **Listener.onHeaders(...)** | Initial response headers received | Read initial metadata |
| **Listener.onMessage(...)** | Response message received | Observe messages if genuinely needed |
| **Listener.onClose(status, trailers)** | RPC ends | Record status, latency, trailing metadata |

You do not need to override every callback. An interceptor should handle cross-cutting concerns with low overhead. Parsing payloads, querying databases, or running business logic inside an interceptor typically increases coupling and latency.

### 2.1. Attaching a request ID with ClientInterceptor

The following example generates a request ID for each RPC and adds it to metadata:

~~~java
package dev.example.orders.client;

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

        return new ForwardingClientCall
                .SimpleForwardingClientCall<ReqT, RespT>(delegate) {

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

**start(...)** is the right place to add request headers before the call is sent. The code above generates a new ID per RPC. In distributed systems, if the caller already has a correlation/trace ID, propagate that existing ID from request context instead of always generating a new ID at every service.

Never create a shared singleton mutable **Metadata** object and overwrite values for each RPC. Concurrent calls could send the wrong ID or credentials. Create/populate metadata within each call's scope.

### 2.2. Observing status and latency

A client interceptor can also wrap the listener to measure elapsed time from call start until the terminal callback arrives:

~~~java
package dev.example.orders.client;

import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.ForwardingClientCallListener;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import io.grpc.Status;

public final class RpcMetricsClientInterceptor
        implements ClientInterceptor {

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions options,
            Channel next) {

        ClientCall<ReqT, RespT> delegate = next.newCall(method, options);

        return new ForwardingClientCall
                .SimpleForwardingClientCall<ReqT, RespT>(delegate) {

            private long startedAtNanos;

            @Override
            public void start(
                    Listener<RespT> listener,
                    Metadata headers) {

                startedAtNanos = System.nanoTime();

                Listener<RespT> wrapped =
                        new ForwardingClientCallListener
                                .SimpleForwardingClientCallListener<RespT>(
                                        listener) {
                            @Override
                            public void onClose(
                                    Status status,
                                    Metadata trailers) {

                                long elapsedNanos =
                                        System.nanoTime() - startedAtNanos;

                                recordRpc(
                                        method.getFullMethodName(),
                                        status.getCode(),
                                        elapsedNanos);

                                super.onClose(status, trailers);
                            }
                        };

                super.start(wrapped, headers);
            }
        };
    }

    private void recordRpc(
            String fullMethodName,
            Status.Code code,
            long elapsedNanos) {
        // Send to the injected/configured metrics system.
    }
}
~~~

This illustrates where to measure, not a full metrics backend. In real applications, inject a thread-safe recorder; avoid synchronous I/O or heavy logging inside callbacks. Use **full method name** and **Status.Code** as bounded-cardinality labels; avoid using order IDs, request IDs, or tokens as metric labels.

**onClose(...)** is the call-completion callback. It receives status and trailers; always call **super.onClose(...)** so the stub/caller's listener still runs. If an interceptor swallows the callback, the caller may never receive a result.

## 3. ServerInterceptor lifecycle and API

**ServerInterceptor** implements:

~~~java
<ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
        ServerCall<ReqT, RespT> call,
        Metadata headers,
        ServerCallHandler<ReqT, RespT> next);
~~~

The server interceptor receives **ServerCall**, request headers, and the next handler. It can:

- Reject the call before the service implementation runs.
- Verify metadata/credentials and build a principal.
- Put a request ID or verified principal into **Context**.
- Wrap ServerCall to add response headers/trailers or observe status.
- Wrap ServerCall.Listener to monitor messages, half-close, cancellation, and completion.

| Callback | Meaning |
| --- | --- |
| **interceptCall(...)** | Server entry point for each RPC |
| **Listener.onMessage(...)** | Request message received |
| **Listener.onHalfClose()** | Client finished its send direction |
| **Listener.onCancel()** | RPC cancelled by client or transport closed in context |
| **Listener.onComplete()** | Call finished per server lifecycle |
| **Listener.onReady()** | Server can send more messages per flow control |
| **ServerCall.sendHeaders(...)** | Sends initial response metadata |
| **ServerCall.close(status, trailers)** | Terminates RPC and sends status/trailers |

A **ServerInterceptor** is not the same as an HTTP servlet filter. It handles RPCs routed by the gRPC runtime; it does not automatically apply to REST endpoints or every connection in a Spring application.

### 3.1. Reading metadata and placing a principal into Context

The example below requires **x-request-id** metadata and propagates the value into gRPC Context so the handler can read it:

~~~java
package dev.example.orders.server;

import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class RequestContextServerInterceptor
        implements ServerInterceptor {

    private static final Metadata.Key<String> REQUEST_ID =
            Metadata.Key.of(
                    "x-request-id",
                    Metadata.ASCII_STRING_MARSHALLER);

    static final Context.Key<String> REQUEST_ID_CONTEXT =
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

This example uses a request ID to demonstrate context propagation. In real systems, ingress may generate an ID if the client omits one; whether it is required or optional should be an agreed policy. A caller-supplied request ID **does not prove identity** and cannot be used to grant permissions.

The handler can read it:

~~~java
String requestId =
        RequestContextServerInterceptor.REQUEST_ID_CONTEXT.get();
~~~

**Contexts.interceptCall(...)** keeps the context attached across RPC callbacks. If the handler offloads work to a custom executor, propagate context to that thread using APIs like **Context.wrap(...)**; do not assume custom `ThreadLocal` variables propagate automatically.

### 3.2. Authentication and authorization

Interceptors are an appropriate place to verify common credentials across methods. When a token is invalid, the server can terminate with **UNAUTHENTICATED**; when the caller is authenticated but lacks permission to call a method, it can return **PERMISSION_DENIED**.

Distinguish clearly:

- **Authentication** verifies caller identity.
- **Authorization** decides whether a principal may invoke a service/method or act on a resource.
- **Business authorization** may require per-order or per-tenant data and usually collaborates with the service/domain layer.

Never trust headers like **x-user-role: admin** sent directly by a client. Principals must be constructed from verified credentials. Interceptors can gate access at the service/method level; implementations still need to check permissions on specific resources.

For per-call tokens, consider **CallCredentials** on the client to attach authorization metadata through the authentication mechanism. A `ClientInterceptor` can assist with tracing or common headers, but should not store long-lived tokens in a shared mutable object.

## 4. Wrapping calls and listeners properly

Interceptors typically use **ForwardingClientCall**, **ForwardingClientCallListener**, **ForwardingServerCall**, and **ForwardingServerCallListener**. These classes let you add behavior while forwarding callbacks that do not need changes.

Rules:

1. Create a delegate via **next.newCall(...)** on the client or receive **ServerCall** on the server.
2. Wrap the delegate/listener at the right lifecycle hook.
3. Call **super** or forward the corresponding callback unless intentionally terminating the RPC.
4. Never emit terminal callbacks twice.
5. Do not store per-RPC state in a singleton interceptor field unless it is isolated per call.

Example server interceptor adding end-of-call metadata in **ServerCall.close(...)**:

~~~java
package dev.example.orders.server;

import io.grpc.ForwardingServerCall;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class ServiceVersionInterceptor
        implements ServerInterceptor {

    private static final Metadata.Key<String> SERVICE_VERSION =
            Metadata.Key.of(
                    "x-service-version",
                    Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        ServerCall<ReqT, RespT> wrapped =
                new ForwardingServerCall
                        .SimpleForwardingServerCall<ReqT, RespT>(call) {
                    @Override
                    public void close(Status status, Metadata trailers) {
                        trailers.put(SERVICE_VERSION, "orders-v1");
                        super.close(status, trailers);
                    }
                };

        return next.startCall(wrapped, headers);
    }
}
~~~

The example adds a custom trailer to every terminal outcome. If you only want to add it on error, check **status.isOk()** before writing. Do not overwrite **grpc-status**, as it is a protocol field managed by the runtime.

## 5. Registering interceptors in a Spring application

### 5.1. Client: wrapping the Channel before creating stubs

With core grpc-java, **ClientInterceptors.intercept(...)** creates a Channel wrapper. Spring can manage the underlying Channel and stubs as beans:

~~~java
package dev.example.orders.client;

import dev.example.orders.v1.OrderServiceGrpc;
import io.grpc.ClientInterceptors;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderGrpcClientConfig {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel orderChannel() {
        return ManagedChannelBuilder
                .forAddress("localhost", 9090)
                .usePlaintext()
                .build();
    }

    @Bean
    OrderServiceGrpc.OrderServiceBlockingStub orderStub(
            ManagedChannel orderChannel) {

        return OrderServiceGrpc.newBlockingStub(
                ClientInterceptors.intercept(
                        orderChannel,
                        new RequestIdClientInterceptor(),
                        new RpcMetricsClientInterceptor()));
    }
}
~~~

The stub is built from the wrapped Channel so every RPC through that stub passes through the registered interceptors. The underlying **ManagedChannel** is still reused, and Spring shuts it down when the context closes. **usePlaintext()** is only for local demos or controlled environments; production requires TLS/mTLS and proper credentials.

Do not create a new ManagedChannel per request. That increases connections, handshakes, and resolver overhead, while losing continuous Subchannel/load-balancing state.

### 5.2. Server: wrapping the service implementation

With grpc-java `ServerBuilder`:

~~~java
package dev.example.orders.server;

import dev.example.orders.v1.OrderServiceGrpc;
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
                                new RequestContextServerInterceptor(),
                                new ServiceVersionInterceptor()))
                .build();
    }
}
~~~

**OrderEndpoint** is a Spring bean extending **OrderServiceGrpc.OrderServiceImplBase**. **ServerInterceptors.intercept(...)** creates a service wrapper with interceptors attached before registering with the server.

This is the direct grpc-java integration style. If the project uses a Spring gRPC starter with server/service auto-configuration, register interceptors via that starter version's extension point and avoid starting an extra manual server on the same port. Starter property/API names may differ across versions.

### 5.3. Interceptor ordering

When multiple interceptors exist, ordering affects behavior:

- Outermost interceptors can initialize context or correlation IDs for inner layers.
- Authentication should happen before principal-based authorization.
- Logging/metrics need to observe the final status without recording secrets.
- Error-handling interceptors must not mask original statuses or swallow callbacks.

Exact execution order depends on how interceptors are nested/wrapped and the registration API used. Declare ordering explicitly in configuration, write tests for order dependencies, and avoid letting security logic depend on an implicit order.

## 6. What interceptors should and should not do

| Good fit for interceptors | Keep in another layer |
| --- | --- |
| Attaching request/correlation IDs | Order business rules |
| Verifying common credentials | Fine-grained authorization on individual resources |
| Placing principals into Context | Pricing, inventory, transactions |
| Recording per-method latency/status | Logging entire payloads or business events |
| Standardizing metadata/tracing | Mutating request/response schemas |
| Blocking disallowed methods | Retrying non-idempotent write operations |

Interceptors should be **lightweight, fast, and minimally coupled**. A synchronous interceptor that calls a database or external service on every RPC can become a shared bottleneck for the entire service. When permission checks depend on business data, use the principal verified by the interceptor and perform the check in the service/domain layer.

An interceptor also does not replace **deadlines**, **cancellation**, **TLS**, or **health checking**. It can observe and cooperate with those mechanisms, yet each mechanism still needs proper configuration and enforcement at its own layer.

## 7. Testing interceptors

Test observable behavior through the gRPC runtime, not only by calling interceptor methods directly.

Core cases:

| Test | Expectation |
| --- | --- |
| Client interceptor attaches request ID | Server interceptor reads exact key/value |
| Request missing required metadata | Server returns policy status; implementation is not invoked |
| Invalid token | **UNAUTHENTICATED**, token not exposed |
| Principal lacks permission | **PERMISSION_DENIED** |
| Successful RPC | Client receives response and OK status |
| Failed RPC | Client interceptor observes final status |
| Server adds custom trailer | Client reads trailer if transport delivers it |
| Caller cancels stream | Cancel callback handled, data sources cleaned up |
| Concurrent RPCs | Request IDs/principals/metrics never bleed across calls |

### 7.1. In-process testing with JUnit

Simple example using **InProcessServerBuilder** and **InProcessChannelBuilder** to verify the request ID is propagated into Context and the service returns a response:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import dev.example.orders.v1.GetOrderRequest;
import dev.example.orders.v1.GetOrderResponse;
import dev.example.orders.v1.OrderServiceGrpc;
import io.grpc.ClientInterceptors;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.ServerInterceptors;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.Test;

class InterceptorIntegrationTest {

    @Test
    void requestIdIsAvailableInsideServiceCall() throws Exception {
        String name = InProcessServerBuilder.generateName();

        OrderServiceGrpc.OrderServiceImplBase endpoint =
                new OrderServiceGrpc.OrderServiceImplBase() {
                    @Override
                    public void getOrder(
                            GetOrderRequest request,
                            StreamObserver<GetOrderResponse> observer) {

                        String requestId =
                                RequestContextServerInterceptor
                                        .REQUEST_ID_CONTEXT.get();

                        if (requestId == null || requestId.isBlank()) {
                            observer.onError(
                                    io.grpc.Status.INTERNAL
                                            .withDescription("Missing context")
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

        Server server = InProcessServerBuilder.forName(name)
                .directExecutor()
                .addService(
                        ServerInterceptors.intercept(
                                endpoint,
                                new RequestContextServerInterceptor()))
                .build()
                .start();

        ManagedChannel baseChannel = InProcessChannelBuilder.forName(name)
                .directExecutor()
                .build();

        try {
            OrderServiceGrpc.OrderServiceBlockingStub stub =
                    OrderServiceGrpc.newBlockingStub(
                            ClientInterceptors.intercept(
                                    baseChannel,
                                    new RequestIdClientInterceptor()));

            GetOrderResponse response = stub.getOrder(
                    GetOrderRequest.newBuilder()
                            .setOrderId("order-42")
                            .build());

            assertEquals("order-42", response.getOrderId());
        } finally {
            baseChannel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

This test assumes the interceptors from sections 2 and 3 are placed in matching packages/imports. A compatible **grpc-inprocess** dependency for your grpc-java version and JUnit 5 are required. **directExecutor()** is convenient for small tests, yet does not simulate concurrency, thread pools, or real network transports.

### 7.2. Testing over a real transport

In-process tests do not verify TLS, ALPN, HTTP/2 proxies, metadata limits, or behavior when TCP drops. In production environments, add tests over a real transport setup, especially when interceptors deal with authorization, credentials, tracing, or trailers.

## 8. Common issues and troubleshooting

| Symptom | Possible cause | Remediation |
| --- | --- | --- |
| Server cannot read request ID | Client interceptor not attached to the stub's Channel, or key mismatch | Check wiring and `Metadata.Key` |
| Server returns INVALID_ARGUMENT even though client sent ID | Proxy stripped header or interceptor reads wrong key | Inspect metadata at each hop |
| Client misses terminal callback | Interceptor wrapped listener but forgot to call `super.onClose(...)` | Forward callbacks completely |
| Status turns into INTERNAL/UNKNOWN | Interceptor caught exception and re-wrapped improperly | Preserve original status; map errors intentionally |
| Principals/request IDs mix across RPCs | Stored state in shared mutable field | Keep state per call and use gRPC Context |
| Tokens appear in logs | Logged entire Metadata or exception | Redact/allowlist keys; never log credentials |
| Metrics double-counted | Same interceptor registered multiple times | Check Channel wrappers and server registration |
| Latency rises after enabling interceptor | Unnecessary I/O/blocking or serialization | Keep interceptors light; measure per-callback cost |
| Server interceptor rejects yet handler still runs | Called `next.startCall(...)` before deciding to reject | Close ServerCall and return empty listener before forwarding |
| Behavior changes when adding a new interceptor | Wrapping order undocumented/untested | Declare explicit order and test combinations |

When debugging, trace the path: **does the stub use the wrapped Channel?** → **did ClientInterceptor run?** → **did headers reach the server?** → **is ServerInterceptor registered on the service?** → **is Context attached in callbacks?** → **were listeners/statuses forwarded?**.

## 9. Hands-on lab and self-check questions

### Hands-on lab

1. Create **RequestIdClientInterceptor** to attach a distinct **x-request-id** per RPC.
2. Create **RequestContextServerInterceptor** to validate the request ID and place it in Context; write a handler that reads that value.
3. Create **RpcMetricsClientInterceptor** recording full method name, latency, and **Status.Code**; use a thread-safe recorder and never put personal IDs in metric labels.
4. Create a server token-authentication interceptor. Distinguish **UNAUTHENTICATED** from **PERMISSION_DENIED**, and never trust client-supplied roles.
5. Register the client interceptor via a Channel wrapper and the server interceptor via a service wrapper in a Spring application; confirm there is no duplicate registration.
6. Write in-process tests for valid/missing request IDs, success/error statuses, and concurrent RPCs.
7. Run real-transport tests to verify TLS, proxies, and metadata on deployment.

### Self-check questions

**1. How do ClientInterceptor and ServerInterceptor differ?**  
`ClientInterceptor` runs around client-initiated calls, allowing it to attach request metadata and observe responses/status. `ServerInterceptor` runs before the service implementation, allowing it to inspect headers, authenticate, and build Context.

**2. Why shouldn't you store a request ID in a singleton interceptor field?**  
One interceptor can serve many concurrent RPCs. A shared mutable field lets one call's state overwrite another's.

**3. Which API should pass a verified principal to the handler?**  
Use **io.grpc.Context** and **Contexts.interceptCall(...)** to attach per-RPC data; avoid trusting role headers sent directly by callers.

**4. Why must an interceptor call super.onClose(...)?**  
So the stub/caller's listener receives the terminal status. Swallowing the callback can prevent the caller from receiving a result or completing at the application layer.

**5. Should you use an interceptor to check per-order viewing permissions?**  
Interceptors suit authentication and general policies. Data-specific access checks typically belong in the service/domain layer once a trusted principal is established.

**6. Does ClientInterceptor replace CallCredentials?**  
No. `CallCredentials` is the dedicated abstraction for per-call authentication credentials; interceptors suit cross-cutting RPC behavior such as tracing, request IDs, and metrics.

**7. Do in-process tests prove TLS/proxies work properly?**  
No. They test gRPC APIs and in-process routing; TLS, ALPN, HTTP/2 proxies, and TCP failures require testing on a real transport.

## Summary

**ClientInterceptor** and **ServerInterceptor** are extension points at the RPC boundary for enforcing cross-cutting behavior. Client interceptors typically attach metadata and observe callbacks/status; server interceptors inspect request headers, authenticate, create **Context**, and wrap server calls/listeners. In Spring gRPC, register interceptors via Channel wrappers or service wrappers, keep them lightweight and thread-safe, forward callbacks completely, and test execution ordering. Interceptors standardize tracing, metrics, and security at the RPC layer while keeping business rules in the service/domain layer.
