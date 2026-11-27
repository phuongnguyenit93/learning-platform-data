# Metadata Interceptors

In **Spring gRPC**, a call often passes through multiple cross-cutting concerns outside business logic: attaching a request ID, passing tokens, reading trace context, measuring latency, checking tenants, or resolving locales. If every RPC method reads and writes `io.grpc.Metadata` on its own, this logic becomes duplicated, hard to test, and easy to miss in streaming methods. A **metadata interceptor** centralizes these common operations at a unified client or server processing point.

Interceptors are a **grpc-java** component. Spring gRPC uses this infrastructure to implement clients and servers from Protocol Buffers contracts, so a well-designed `ClientInterceptor` or `ServerInterceptor` applies to both unary RPCs and streaming RPCs. However, an interceptor only helps **read, write, or propagate** metadata; a value present in a header does not by itself prove validity, identity, or access permission.

After this lesson, you will be able to:

- Explain where interceptors fit in a gRPC call's lifecycle and distinguish client-side from server-side interceptors.
- Write a `ClientInterceptor` to add request metadata per RPC and observe response headers/trailers.
- Write a `ServerInterceptor` to validate metadata, create `io.grpc.Context`, and append response trailers.
- Register interceptors on the right channel, stub, or server in a Spring gRPC system.
- Handle interceptor ordering, call cancellation, deadlines, retries, streaming, async context, and sensitive data.
- Test actual metadata behavior with a gRPC client/server and detect common configuration mistakes.

## 1. Where Do Metadata Interceptors Live?

In gRPC, metadata is a set of **key–value** pairs residing in headers or trailers of an **RPC call**. Protobuf messages carry business data; metadata serves auxiliary information such as `x-request-id`, `authorization`, or `traceparent`.

Basic flow:

```text
Client application                      gRPC transport                     Server application
       |                                       |                                     |
       |  [ClientInterceptor]                  |                                     |
       |   - receives method/call options      |                                     |
       |   - writes request headers            |                                     |
       |------- headers + protobuf message --->|--------> [ServerInterceptor]       |
       |                                       |          - validates headers        |
       |                                       |          - creates Context          |
       |                                       |          - allows/rejects RPC       |
       |                                       |                     |               |
       |                                       |                     v               |
       |                                       |               gRPC service method    |
       |<------ response headers/message ------|<------------------------------------|
       |<------ status + response trailers ----|<------------------------------------|
       |  [ClientCall.Listener]                 |                                     |
       |   - onHeaders(...)                     |                                     |
       |   - onClose(status, trailers)          |                                     |
```

An interceptor can:

1. **Read and add** request metadata before the call is sent over the transport.
2. **Observe or modify** response headers/trailers according to policy.
3. **Reject early** calls with invalid metadata using a gRPC `Status`.
4. **Attach context** for logging, tracing, or business processing.

Interceptors **do not** automatically execute business logic or resource authorization. For instance, validating a token is the authentication step; deciding which specific orders a user may edit still requires an appropriate policy.

## 2. Key `grpc-java` APIs

| API | Called on which side? | Primary responsibility |
| --- | --- | --- |
| `ClientInterceptor.interceptCall(...)` | Client | Wraps a new call, sees `MethodDescriptor` and `CallOptions` |
| `ClientCall.start(listener, headers)` | Client | Starts the call and sends request metadata |
| `ClientCall.Listener.onHeaders(...)` | Client | Receives initial response metadata |
| `ClientCall.Listener.onClose(status, trailers)` | Client | Receives terminal status and response trailers |
| `ServerInterceptor.interceptCall(...)` | Server | Reads request metadata before running the service |
| `ServerCall.sendHeaders(...)` | Server | Sends initial response headers |
| `ServerCall.close(status, trailers)` | Server | Ends the RPC, returning status and trailers |
| `Contexts.interceptCall(...)` | Server | Runs the next step with the attached `io.grpc.Context` |
| `Metadata.Key<T>` | Both sides | Defines the key name and marshaller for the value |

**Distinguishing the two callback pairs:** on the client side there are `ClientCall` and `ClientCall.Listener`; on the server side there are `ServerCall` and `ServerCall.Listener`. They are **different** interception points. For example, a client wanting to add `authorization` must do so before calling `super.start(...)`; a server wanting to add trailers must intercept when `close(...)` is called.

An interceptor can wrap a call using `ForwardingClientCall`, `ForwardingClientCallListener`, or `ForwardingServerCall`. These classes forward most operations to the delegate, allowing you to override only the callbacks you actually need.

## 3. Metadata Rules Before Writing Interceptors

Do not write interceptors before agreeing on keys and value lifecycles.

| Property | Example | Rule |
| --- | --- | --- |
| Key name | `x-request-id` | Use lowercase names, avoid the protocol-reserved `grpc-` prefix |
| Value type | `String` | Use `Metadata.ASCII_STRING_MARSHALLER` for ASCII strings |
| Binary key | `x-proof-bin` | Must end with `-bin` and use the corresponding binary marshaller |
| Value count | One request ID per RPC | Define how duplicate keys are handled |
| Provisioning source | Gateway or client application | Define trust boundaries and generation/override policies |
| Scope | Per RPC | Never share mutable metadata across multiple calls |
| Sensitive data | `authorization` | Never put tokens into logs or response headers |

Example keys:

```java
import io.grpc.Metadata;

Metadata.Key<String> requestIdKey =
    Metadata.Key.of(
        "x-request-id", Metadata.ASCII_STRING_MARSHALLER);

Metadata.Key<byte[]> proofKey =
    Metadata.Key.of(
        "x-proof-bin", Metadata.BINARY_BYTE_MARSHALLER);
```

Names like `x-request-id` are **application conventions**, not mandatory gRPC headers. Other headers such as `grpc-timeout` or `grpc-status` are managed by the protocol library: use the deadline and `Status` APIs instead of attaching them manually.

## 4. Client Interceptor: Adding Request Metadata per Call

Suppose a service requires an `x-request-id` on every RPC. Let's create a client interceptor so that:

- If the call has a request ID passed by the application via `CallOptions`, use that ID if valid.
- If no valid ID is provided, generate a new UUID **for the RPC currently starting**.
- Write a single value for this key to avoid conflicts with other interceptors.
- Forward the call's final status and optionally observe the request ID in response trailers.

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
import java.util.UUID;

public final class RequestIdClientInterceptor implements ClientInterceptor {

    public static final CallOptions.Key<String> REQUEST_ID_OPTION =
        CallOptions.Key.create("request-id");

    private static final Metadata.Key<String> REQUEST_ID_HEADER =
        Metadata.Key.of(
            "x-request-id", Metadata.ASCII_STRING_MARSHALLER);

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
                    Metadata headers) {

                String supplied = options.getOption(REQUEST_ID_OPTION);
                final String requestId =
                    supplied != null
                        && supplied.matches("[A-Za-z0-9._-]{1,64}")
                    ? supplied
                    : UUID.randomUUID().toString();

                // This interceptor owns the x-request-id key.
                headers.discardAll(REQUEST_ID_HEADER);
                headers.put(REQUEST_ID_HEADER, requestId);

                ClientCall.Listener<RespT> observingListener =
                    new ForwardingClientCallListener
                        .SimpleForwardingClientCallListener<RespT>(
                            responseListener) {
                        @Override
                        public void onClose(Status status, Metadata trailers) {
                            String returnedId = trailers.get(REQUEST_ID_HEADER);
                            // Log selectively if needed: RPC name,
                            // requestId, returnedId, and status.getCode().
                            // Do not dump entire metadata.
                            super.onClose(status, trailers);
                        }
                    };

                super.start(observingListener, headers);
            }
        };
    }
}
```

`CallOptions.Key` carries per-call options, not an HTTP/2 header. The value is only converted to metadata when the interceptor calls `headers.put(...)`. Downstream calls belonging to the same task can intentionally reuse a correlation ID, while two independent RPCs can generate distinct IDs.

In the example, `discardAll(...)` establishes this interceptor's exclusive ownership of `x-request-id`. If the system allows multiple interceptors to modify the same key, define clear precedence rules instead of letting overrides depend arbitrarily on interceptor ordering.

### Attaching the Interceptor to a Generated Stub

Suppose a `channel` to the server exists and `GreeterGrpc` was generated from a `.proto` file:

```java
GreeterGrpc.GreeterBlockingStub baseStub =
    GreeterGrpc.newBlockingStub(channel)
        .withInterceptors(new RequestIdClientInterceptor());

GreeterGrpc.GreeterBlockingStub requestStub =
    baseStub.withOption(
        RequestIdClientInterceptor.REQUEST_ID_OPTION,
        "req-checkout-42");

// requestStub.sayHello(...) sends x-request-id: req-checkout-42
```

The names `GreeterGrpc` and `sayHello` merely illustrate a class/method from a Protobuf contract. `withOption(...)` and `withInterceptors(...)` create derived stubs; configure them according to the caller's scope. Avoid keeping a stub with a fixed request ID or one user's credentials and sharing it across other users.

**Safety note:** a client interceptor runs at the beginning of each RPC, but **does not** replace an authentication system. If you need to supply a dynamic bearer token, `CallCredentials` is the dedicated API for applying credentials per call; never use a request ID as a token.

## 5. Server Interceptor: Validating Metadata and Creating Context

The server receives request metadata before dispatching processing to the RPC method. The example below **requires exactly one** valid `x-request-id`; it places the ID into `io.grpc.Context` and echoes that ID in response trailers for client correlation.

```java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.ForwardingServerCall;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.Iterator;

public final class RequestContextServerInterceptor implements ServerInterceptor {

    public static final Context.Key<String> CURRENT_REQUEST_ID =
        Context.key("request-id");

    private static final Metadata.Key<String> REQUEST_ID_HEADER =
        Metadata.Key.of(
            "x-request-id", Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        Iterable<String> values = headers.getAll(REQUEST_ID_HEADER);
        if (values == null) {
            return reject(call, "Missing x-request-id");
        }

        Iterator<String> iterator = values.iterator();
        if (!iterator.hasNext()) {
            return reject(call, "Missing x-request-id");
        }

        final String requestId = iterator.next();
        if (iterator.hasNext()
                || requestId == null
                || !requestId.matches("[A-Za-z0-9._-]{1,64}")) {
            return reject(call, "Invalid x-request-id");
        }

        Context scopedContext = Context.current()
            .withValue(CURRENT_REQUEST_ID, requestId);

        ServerCall<ReqT, RespT> decoratedCall =
            new ForwardingServerCall.SimpleForwardingServerCall<ReqT, RespT>(
                    call) {
                @Override
                public void close(Status status, Metadata trailers) {
                    // Only echo the validated ID; status is handled by gRPC.
                    trailers.discardAll(REQUEST_ID_HEADER);
                    trailers.put(REQUEST_ID_HEADER, requestId);
                    super.close(status, trailers);
                }
            };

        return Contexts.interceptCall(
            scopedContext, decoratedCall, headers, next);
    }

    private static <ReqT, RespT> ServerCall.Listener<ReqT> reject(
            ServerCall<ReqT, RespT> call, String description) {
        call.close(
            Status.INVALID_ARGUMENT.withDescription(description),
            new Metadata());
        return new ServerCall.Listener<ReqT>() {};
    }
}
```

This is an **illustrative policy**: requiring a request ID is not a gRPC rule. For systems with external clients, the server can also generate an ID if the header is missing or untrusted. Endpoints such as health checks or reflection may require separate policies.

`Contexts.interceptCall(...)` executes subsequent steps and related callbacks with the attached `Context`. Inside the service:

```java
String id = RequestContextServerInterceptor.CURRENT_REQUEST_ID.get();
// Use id as a format-validated log field.
```

Do not arbitrarily use `ThreadLocal` instead of `io.grpc.Context` to hold per-RPC data. For tasks offloaded to a self-managed executor, propagate context across threads as shown later.

## 6. Response Headers and Trailers: Intercepting at the Right Callback

An RPC's return data can consist of **initial response headers**, **messages**, and **trailers**. gRPC `Status` is sent when closing the call.

| Location | Server-side callback | Client-side callback | Example |
| --- | --- | --- | --- |
| Request metadata | Read from `headers` parameter of `interceptCall(...)` | Write before `ClientCall.start(...)` | `authorization`, `x-request-id` |
| Initial response headers | `ServerCall.sendHeaders(...)` | `ClientCall.Listener.onHeaders(...)` | `x-server-version` |
| Response trailers | `ServerCall.close(status, trailers)` | `ClientCall.Listener.onClose(status, trailers)` | `x-request-id` for error diagnostics |

To add information to **initial response headers**, a server interceptor can wrap `sendHeaders(...)`:

```java
// Illustrative snippet inside ForwardingServerCall.
@Override
public void sendHeaders(Metadata responseHeaders) {
    responseHeaders.put(
        Metadata.Key.of(
            "x-server-version", Metadata.ASCII_STRING_MARSHALLER),
        "1.2.0");
    super.sendHeaders(responseHeaders);
}
```

`sendHeaders(...)` must obey call lifecycle rules; never call it multiple times or send headers after the call has closed. A failed RPC can end as **trailers-only**, so clients should not assume initial response headers are always present.

In the server example from section 5, the ID is added to trailers inside `close(...)`; the client reads it in `onClose(...)`. Response trailers are suitable for information needed at the end of an RPC, even when the application produces no success message.

Never create `grpc-status`, `grpc-message`, or `grpc-timeout` as custom metadata. Use gRPC's `Status` and deadline APIs.

## 7. Registering Interceptors in Spring gRPC

Writing a class that implements `ClientInterceptor` or `ServerInterceptor` **is not enough** to make it run. The interceptor must be attached to the actual client call path or server call path.

### Client Side

One way at the `grpc-java` layer is attaching directly to the stub:

```java
GreeterGrpc.GreeterBlockingStub stub =
    GreeterGrpc.newBlockingStub(channel)
        .withInterceptors(
            new RequestIdClientInterceptor());
```

When a Spring application manages stubs/channels, attach the interceptor through the client configuration supported by the Spring gRPC version or starter you are using. Check the scope: an interceptor may apply only to a single stub/channel, or to multiple clients if registered globally.

### Server Side

At the pure `grpc-java` layer, you can wrap the service:

```java
import io.grpc.ServerInterceptors;
import io.grpc.ServerServiceDefinition;

// GreeterService is an application BindableService.
ServerServiceDefinition interceptedService =
    ServerInterceptors.intercept(
        new GreeterService(),
        new RequestContextServerInterceptor());

// Register interceptedService with ServerBuilder or an appropriate server factory.
```

In Spring gRPC, the method for registering server interceptors (via bean configuration, annotations, or server factories) depends on the version and starter in use. Pick **one** official mechanism in your project, check interceptor scope/order, and verify with a test RPC. Never assume that merely defining a Spring `@Bean ServerInterceptor` always means it is automatically attached to every service across every starter.

### Ordering Multiple Interceptors

An application might need:

```text
Inbound request
  -> tracing / correlation
  -> authentication
  -> authorization metadata policy
  -> service method
  -> response metadata / status / tracing close
```

This is the **target policy order**, not a guarantee of order when registering interceptors through any arbitrary API. Multiple interceptors wrap one another, so the actual order also affects response callbacks flowing in the reverse direction. Test the configured order on both client and server, especially if an interceptor relies on data placed in `Context` by another interceptor.

If tracing and authentication are auto-registered by multiple frameworks, avoid accidentally creating duplicate spans or authenticating twice. Clearly separate "who creates metadata", "who validates metadata", and "who enforces permissions".

## 8. Metadata Interceptors with Authentication, Tracing, and Locale

Interceptors are a convenient place to handle cross-cutting data, but each metadata category needs a distinct policy:

| Metadata | What can an interceptor do? | What should it not do? |
| --- | --- | --- |
| `authorization` | Apply `CallCredentials` on client; verify token in server interceptor/auth layer | Log tokens; treat header presence as authenticated |
| `x-correlation-id` | Normalize ID, bind to `Context`, assist log search | Treat ID as proof of identity |
| `traceparent`, `tracestate` | Inject/extract via OpenTelemetry propagator | Manually alter trace ID/span ID, install two overlapping tracing layers |
| `x-tenant-id` | Receive requested tenant, check against trusted principal | Allow data reads solely based on client-sent ID |
| `x-locale` | Resolve permitted locale and put into context | Call `Locale.setDefault(...)` JVM-wide per RPC |
| `x-proof-bin` | Read/write `byte[]` with binary marshaller | Double Base64-encode or stuff large payloads into headers |

If bearer tokens need to change per call, `CallCredentials` fits the job of providing credentials on the client. Do not build an interceptor holding a single user's fixed token inside a singleton and reusing it across requests.

**Security:** metadata travels over gRPC connections and is not secured merely because it is binary metadata. Use TLS/mTLS per architecture, verify trusted sources, and log only keys on an allowlist. Fields such as tokens, cookies, personal data, and sensitive baggage should never be dumped into logs or traces.

## 9. Deadlines, Cancellation, Retries, and Streaming

### 9.1. Deadlines and Cancellation

Interceptors can observe completion status but should never manually set the `grpc-timeout` header. On the client, use:

```java
import java.util.concurrent.TimeUnit;

GreeterGrpc.GreeterBlockingStub timedStub =
    baseStub.withDeadlineAfter(2, TimeUnit.SECONDS);
```

When a deadline expires, the caller may receive `DEADLINE_EXCEEDED`. If the user or framework cancels a call, server logic should respect cancellation state and avoid unnecessary work. Inside `onClose(...)`, an interceptor can record the status code and measured duration, but should not turn failed calls into `OK` or swallow callbacks.

### 9.2. Retries

One logical RPC can have multiple attempts if gRPC retry configuration permits. Interceptors registered high or low in the stack may observe different scopes depending on the interceptor type and how retries are executed. **Do not assume** "every attempt definitely generates a new request ID" solely from a `ClientInterceptor`.

Define whether a request ID identifies the **logical RPC** or each **attempt**. If per-attempt tracking is needed, add observability via instrumentation/retry policies without altering business idempotency semantics. An ID used for logging does not replace an idempotency key used to prevent duplicate processing.

### 9.3. Streaming RPCs

`start(...)` on the client and `interceptCall(...)` on the server execute when the stream opens. Metadata is attached at the **RPC** level, not automatically re-sent on each `onNext(...)` message.

| RPC | When is metadata sent? | Where does per-message varying data go? |
| --- | --- | --- |
| Unary | Start of a call | Inside request/response Protobuf |
| Server streaming | When opening the RPC | Inside each response message |
| Client streaming | When opening the RPC | Inside each request message |
| Bidirectional streaming | When opening the RPC | Inside each bidirectional message |

For long-lived streams, account for token expiration, revoked permissions, deadlines, and resource control. Do not expect to swap tokens or tenants simply by mutating the `Metadata` object after the call has started.

## 10. Context Propagation and Async Processing

`io.grpc.Context` is designed to hold call-scoped information such as correlation IDs, deadlines, or cancellation state. A server interceptor can use `Contexts.interceptCall(...)` so subsequent gRPC callbacks see the right context.

If a service offloads work to a thread pool, propagate context:

```java
import io.grpc.Context;
import java.util.concurrent.Executor;

// Inside a gRPC callback while the current context is still attached:
Context grpcContext = Context.current();
Executor applicationExecutor = /* application-managed executor */;

applicationExecutor.execute(grpcContext.wrap(() -> {
    String requestId =
        RequestContextServerInterceptor.CURRENT_REQUEST_ID.get();
    // Continue processing with the request ID of the right RPC.
}));
```

The snippet above only demonstrates propagating **gRPC Context**. `org.slf4j.MDC`, `io.opentelemetry.context.Context`, and Spring's `LocaleContextHolder` are separate mechanisms; they may need to be propagated, set, and restored separately or handled via an instrumented executor. Avoid letting one request's MDC/locale leak onto a thread reused by another request.

Interceptors must also be careful with async callbacks: when adding logging, metrics, or cleanup, ensure callbacks are forwarded according to lifecycle rules and heavy work never blocks gRPC I/O executors.

## 11. Common Pitfalls

| Symptom | Possible cause | Solution |
| --- | --- | --- |
| Header not visible on server | Client interceptor not registered on the stub/channel actually called | Check stub creation path and test RPC end-to-end |
| Server interceptor bean exists but doesn't run | Server factory/starter did not attach interceptor or wrong scope | Register via the proper mechanism and verify with tests |
| Header has two conflicting values | Multiple interceptors or callers writing the same key | Define key ownership and duplicate-key policy |
| `get(...)` returns `null` | Wrong key name, ASCII/binary mismatch, or header not sent | Check marshaller, key name, and callback |
| Response trailers missing expected data | Server did not add data in `close(...)` or RPC ended via another path | Wrap `ServerCall` properly and test failure paths too |
| Request logs mixed together | Sharing mutable `Metadata` or storing IDs in unmanaged static/global/thread-local | Create data per call, use `Context`, and clean up |
| Some methods are unauthenticated | Interceptor registered only for specific services | Check all sensitive RPCs, including streaming |
| Getting `UNAUTHENTICATED` despite sending token | Expired token, wrong audience/issuer, or credentials not attached to call | Check credentials flow and verifier |
| Calls become slow | Interceptor waits on synchronous I/O in critical callback | Move heavy logic to proper mechanism; set timeouts/deadlines |
| Corrupted binary data | Key missing `-bin` or wrong manual Base64 | Use `byte[]` and binary marshaller per rules |
| Trace broken during async work | Not propagating trace context across executor | Check propagator and context wrappers |
| Security flaw using client headers | Trusting unverified tenant, role, or user ID | Use verified principal and server-side policy |

Do not store very large metadata values. HTTP/2 headers and trailers are constrained by limits at the server, client, proxy, and load balancer. For large business payloads or files, use appropriate Protobuf messages/streams.

## 12. Testing Metadata Interceptors

**Unit tests** verify keys, value validation, and rejection branches. **Integration tests** through a gRPC client/server confirm the interceptor is actually registered and functions within the call lifecycle.

A basic test matrix:

| Scenario | Setup | Expected result |
| --- | --- | --- |
| Client has request ID in option | `withOption(..., "req-42")` | Server sees exact `req-42` |
| Client has no request ID | Option omitted | Client generates a valid ID per RPC |
| Server receives no request ID | Call with client lacking interceptor | `INVALID_ARGUMENT` per illustrative policy |
| Server receives two request IDs | Send two values for the same key | Rejected, not arbitrarily picking one |
| Successful RPC | Valid metadata present | Service runs with accurate `CURRENT_REQUEST_ID` |
| RPC fails after entering service | Service returns error | Client receives status and ID in trailers |
| Two concurrent calls | Same channel, different IDs | No ID cross-talk between the two RPCs |
| Multi-message streaming | One RPC with multiple requests/responses | Metadata attached once, context still belongs to that stream |
| Deadline/cancellation | RPC exceeds deadline or is cancelled | Proper status and cleanup, no hanging |
| Security | Header contains test token | Token does not appear in logs/trailers outside policy |
| Proxy/TLS | Call through production-like environment | Metadata and security work over real network path |

### Integration Test Example with In-Process Transport

Suppose the project has a `Greeter` contract with `GreeterGrpc.GreeterImplBase`, `HelloRequest`, and `HelloReply`. The JUnit 5 test below exercises the **real interceptor path**, not just `Metadata.put/get`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.ServerInterceptors;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.Test;

class MetadataInterceptorIntegrationTest {

    static class GreeterService extends GreeterGrpc.GreeterImplBase {
        @Override
        public void sayHello(
                HelloRequest request,
                StreamObserver<HelloReply> responseObserver) {

            String id =
                RequestContextServerInterceptor.CURRENT_REQUEST_ID.get();
            responseObserver.onNext(
                HelloReply.newBuilder().setMessage(id).build());
            responseObserver.onCompleted();
        }
    }

    @Test
    void passesRequestIdThroughInterceptors() throws Exception {
        String serverName = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(ServerInterceptors.intercept(
                new GreeterService(),
                new RequestContextServerInterceptor()))
            .build()
            .start();

        ManagedChannel channel =
            InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();
        try {
            GreeterGrpc.GreeterBlockingStub stub =
                GreeterGrpc.newBlockingStub(channel)
                    .withInterceptors(new RequestIdClientInterceptor())
                    .withOption(
                        RequestIdClientInterceptor.REQUEST_ID_OPTION,
                        "req-42");

            HelloReply reply = stub.sayHello(
                HelloRequest.newBuilder().setName("Lan").build());
            assertEquals("req-42", reply.getMessage());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
```

This test requires dependencies matching your `grpc-java` version, JUnit 5, and classes generated from `.proto`. It illustrates behavior; if your actual contract uses different services/messages, substitute the corresponding names and methods. `directExecutor()` is convenient in small tests but does not replace testing concurrency, network transport, or TLS.

To test **response trailers**, add a client interceptor capturing metadata inside `onClose(...)` and assert the `x-request-id` key, even when the service returns an error. To test the rejection path, make a call without the interceptor or attach two values for the same key and assert `Status.Code.INVALID_ARGUMENT`.

## 13. Practical Scenario: Monitoring Order Placement RPCs

A Spring gRPC application has `CheckoutService` calling `InventoryService` and then `PaymentService`. Operations needs to locate logs for a transaction, measure latency, and ensure clients cannot impersonate other users via metadata.

**Requirements:**

1. Design a `ClientInterceptor` attaching `x-request-id` with a value generated per RPC or taken from a valid context.
2. Design a `ServerInterceptor` validating format, rejecting duplicate headers, placing the request ID into `io.grpc.Context`, and echoing the ID into response trailers.
3. Register interceptors on both client and server according to the Spring gRPC version in use; verify with tests.
4. Configure `CallCredentials` or an appropriate security mechanism for tokens; authenticate and authorize on the server, avoiding logging tokens.
5. Use OpenTelemetry instrumentation to manage `traceparent`/`tracestate`. Verify the same trace ID across hops while preserving request ID for logs.
6. Test unary and streaming RPCs, error metadata, deadlines, async processing, and proxy header-limit scenarios.

**Self-check questions:**

- What is the difference between `ClientInterceptor.interceptCall(...)` and `ServerInterceptor.interceptCall(...)`?
- Why does the client add metadata inside `start(...)` instead of after sending a message?
- In which callback does the client read response trailers?
- Why is merely writing a Spring bean implementing `ServerInterceptor` not enough to guarantee it runs?
- When two interceptors modify `x-request-id`, what policy should be agreed upon?
- Why does a request ID not replace bearer tokens, authorization, or trace context?
- When a service offloads work to an executor, what must be considered regarding `io.grpc.Context`, MDC, and OpenTelemetry context?
- In bidirectional streaming, does the interceptor run again as each message is sent?

**Key takeaway:** Metadata interceptors centralize logic for **reading, validating, adding, and observing metadata** within `grpc-java`'s RPC lifecycle. Client interceptors prepare request headers and listen to responses; server interceptors validate request headers, create context, and may add response headers/trailers. In Spring gRPC, register them with the right scope, test actual call paths, establish metadata key ownership, and combine appropriate authentication, deadlines, tracing, and TLS for reliable services.
