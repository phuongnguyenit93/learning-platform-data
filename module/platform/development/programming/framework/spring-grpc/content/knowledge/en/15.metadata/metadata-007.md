# Metadata from Client to Server

In a gRPC call, the client often needs to send extra information so the server understands the **call context**: a request ID for log correlation, application version, locale, or credentials. This information can be sent as **request metadata** via HTTP/2 headers. The server receives it in the `io.grpc.Metadata` API before processing the Protobuf message.

In Spring gRPC, this path is implemented on top of `grpc-java`. The client can attach metadata per call using a `ClientInterceptor` or credentials mechanism; the server reads metadata in a `ServerInterceptor`, validates the values, and passes accepted data into `io.grpc.Context` for the service. Understanding this boundary avoids repeating boilerplate in every RPC and prevents blindly trusting client-declared data.

After this lesson, you will be able to:

- Describe the path of request metadata from client through transport to server.
- Create ASCII and binary metadata keys, and attach values to a call on the client.
- Read, validate values, and handle duplicate keys in a server interceptor.
- Pass validated metadata to the service using `io.grpc.Context`.
- Understand that metadata is sent once at the start of a unary or streaming RPC and does not automatically propagate to downstream RPCs.
- Register interceptors in a Spring gRPC application and test the client–server path.

## 1. The Path of Request Metadata

Request metadata belongs to **a single RPC call**. The client prepares metadata when starting the call; gRPC transfers it via HTTP/2 request headers; the server receives and populates the key–value pairs into a `Metadata` object.

```text
Client application          ClientInterceptor        HTTP/2 transport        ServerInterceptor        Service
       |                           |                       |                       |                   |
       | calls stub.method(...)    |                       |                       |                   |
       |-------------------------->|                       |                       |                   |
       |                           | adds request metadata |                       |                   |
       |                           |---------------------->|                       |                   |
       |                           |                       | request headers       |                   |
       |                           |                       |---------------------->|                   |
       |                           |                       |                       | reads/validates   |
       |                           |                       |                       | Metadata          |
       |                           |                       |                       | creates Context   |
       |                           |                       |                       |------------------>|
       |                           |                       |                       |                   |
       |                           |                       |       Protobuf message|------------------>|
       |                           |                       |                       |                   |
```

Significant sequence:

1. The application invokes a method on the generated stub.
2. The client interceptor is invoked to create the `ClientCall`; when the call starts, the interceptor can add request headers.
3. gRPC sends headers along with opening the RPC. Metadata already sent cannot be modified by mutating the Java object afterward.
4. The server interceptor receives `Metadata headers` in `interceptCall(...)`, before the service processes the request message.
5. The server validates metadata, creates an appropriate context, and forwards the call to the next interceptor or service.
6. The service processes the Protobuf message within the call scope that already has context attached.

The server does not receive raw HTTP/2 header strings to parse manually. `grpc-java` already converts transport data into `Metadata` and applies the corresponding marshallers. Therefore, server code should use `Metadata.Key<T>` instead of manually decoding headers at the socket layer.

## 2. Choosing What Data to Send via Metadata

Metadata is suitable for information **auxiliary to the entire RPC**, for example:

| Information | Key example | Reason |
| --- | --- | --- |
| Request ID | `x-request-id` | Correlates logs of a call |
| Client version | `x-client-version` | Compatibility analysis or troubleshooting |
| Preferred language | `x-locale` | Chooses display content if the API has a localization policy |
| Credentials | `authorization` | Transfers authentication info per agreed mechanism |
| Trace context | `traceparent`, `tracestate` | Links spans in distributed tracing |

If data is **business content** that the service must process, put it in the Protobuf message. For example, `order_id`, `quantity`, `shipping_address`, and product lists belong in the request message. Never move these fields to metadata just to avoid editing `.proto`.

A helpful rule: metadata is determined when opening the call and applies to the whole RPC; Protobuf messages are sent according to the payload and message cadence of a unary or streaming method.

## 3. Declaring Keys on Client and Server

Both sides must agree on key names and value types. `Metadata.Key<T>` pairs a name with a marshaller that converts Java data when sending/receiving.

### ASCII Metadata

Short strings like request ID and client version use `Metadata.ASCII_STRING_MARSHALLER`:

```java
import io.grpc.Metadata;

static final Metadata.Key<String> REQUEST_ID =
    Metadata.Key.of(
        "x-request-id",
        Metadata.ASCII_STRING_MARSHALLER);

static final Metadata.Key<String> CLIENT_VERSION =
    Metadata.Key.of(
        "x-client-version",
        Metadata.ASCII_STRING_MARSHALLER);
```

Metadata key names use lowercase and valid ASCII characters. Keys starting with `grpc-` belong to the protocol's reserved namespace; never create custom application keys like `grpc-my-request-id`.

### Binary Metadata

If you genuinely need to send a byte sequence, the key must end with `-bin` and use `Metadata.BINARY_BYTE_MARSHALLER`:

```java
static final Metadata.Key<byte[]> CAPABILITIES =
    Metadata.Key.of(
        "x-client-capabilities-bin",
        Metadata.BINARY_BYTE_MARSHALLER);
```

On the wire, gRPC handles Base64 representation of binary metadata. In Java code, the client puts the original `byte[]` via `put(...)`, and the server receives `byte[]`; do not manually Base64-encode before using the binary marshaller. Binary metadata does not equate to security encryption.

### Agreement Between Both Sides

A metadata contract should specify at least:

- Key name and ASCII/binary type.
- Meaning, format, and length limits of the value.
- Whether the key is required or optional; default value if absent.
- Policy when a key appears multiple times.
- Which component is allowed to create or overwrite the value.
- How the server responds when a value is malformed or unauthorized.

No set of custom metadata keys is automatically generated from `.proto` files. This contract is typically documented in API specs, client/server configurations, and integration tests.

## 4. Attaching Metadata on the Client with `ClientInterceptor`

`ClientInterceptor` sees the RPC method, `CallOptions`, and the next channel. It can wrap `ClientCall` to add headers inside `start(...)`, right before the call begins sending the request.

The example below sends `x-request-id` per RPC. If the application does not supply an ID via `CallOptions`, the interceptor generates a new UUID:

```java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import java.util.UUID;

public final class RequestMetadataClientInterceptor
        implements ClientInterceptor {

    public static final CallOptions.Key<String> REQUEST_ID_OPTION =
        CallOptions.Key.create("request-id");

    private static final Metadata.Key<String> REQUEST_ID_HEADER =
        Metadata.Key.of(
            "x-request-id",
            Metadata.ASCII_STRING_MARSHALLER);

    private static final Metadata.Key<String> CLIENT_VERSION_HEADER =
        Metadata.Key.of(
            "x-client-version",
            Metadata.ASCII_STRING_MARSHALLER);

    private final String clientVersion;

    public RequestMetadataClientInterceptor(String clientVersion) {
        this.clientVersion = clientVersion;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        ClientCall<ReqT, RespT> delegate =
            next.newCall(method, callOptions);

        return new ForwardingClientCall.SimpleForwardingClientCall<ReqT, RespT>(
                delegate) {
            @Override
            public void start(
                    ClientCall.Listener<RespT> responseListener,
                    Metadata headers) {

                String suppliedId =
                    callOptions.getOption(REQUEST_ID_OPTION);
                String requestId =
                    suppliedId != null
                        && suppliedId.matches("[A-Za-z0-9._-]{1,64}")
                    ? suppliedId
                    : UUID.randomUUID().toString();

                // This interceptor owns the two application keys below.
                headers.discardAll(REQUEST_ID_HEADER);
                headers.put(REQUEST_ID_HEADER, requestId);

                headers.discardAll(CLIENT_VERSION_HEADER);
                headers.put(CLIENT_VERSION_HEADER, clientVersion);

                super.start(responseListener, headers);
            }
        };
    }
}
```

`CallOptions.Key` is where an option for a single call is stored; it does not automatically become a header. The interceptor reads the option and writes the value to `Metadata`. Using `discardAll(...)` here explicitly establishes that this interceptor owns these two keys and prevents unintentionally sending multiple values.

Attaching the interceptor to a generated stub:

```java
GreeterGrpc.GreeterBlockingStub baseStub =
    GreeterGrpc.newBlockingStub(channel)
        .withInterceptors(
            new RequestMetadataClientInterceptor("2.4.0"));

GreeterGrpc.GreeterBlockingStub callStub =
    baseStub.withOption(
        RequestMetadataClientInterceptor.REQUEST_ID_OPTION,
        "req-order-42");

// callStub.sayHello(...) will send request metadata.
```

`GreeterGrpc`, `channel`, and `sayHello(...)` are illustrative names for code generated from `.proto`. In a real application, use the stub corresponding to your service. The interceptor can be attached to a specific stub or a shared channel; that scope determines which RPCs receive the metadata.

### Attaching Metadata Directly for a Single Call

When there is only one simple call, you can build `Metadata` and use the `MetadataUtils` helper of your `grpc-java` version to attach headers:

```java
Metadata headers = new Metadata();
headers.put(REQUEST_ID, "req-manual-42");

GreeterGrpc.GreeterBlockingStub oneCallStub =
    GreeterGrpc.newBlockingStub(channel)
        .withInterceptors(
            MetadataUtils.newAttachHeadersInterceptor(headers));
```

This is a concise choice for static cases. If metadata must change per RPC, pay attention to lifecycle and stub/interceptor reusability. For credentials, prefer `CallCredentials` or an appropriate security integration to handle token issuance, refresh, and per-call application.

## 5. Server Receives Metadata in `ServerInterceptor`

`ServerInterceptor.interceptCall(...)` receives three key parameters:

- `ServerCall`: server-side call, used to send headers or close the call with status/trailers.
- `Metadata headers`: request metadata sent by the client.
- `ServerCallHandler next`: forwards to the next interceptor or the service.

The example below checks request ID and client version, rejects duplicate headers, and puts accepted values into `io.grpc.Context`:

```java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.Iterator;

public final class RequestMetadataServerInterceptor
        implements ServerInterceptor {

    public static final Context.Key<String> REQUEST_ID =
        Context.key("request-id");
    public static final Context.Key<String> CLIENT_VERSION =
        Context.key("client-version");

    private static final Metadata.Key<String> REQUEST_ID_HEADER =
        Metadata.Key.of(
            "x-request-id",
            Metadata.ASCII_STRING_MARSHALLER);
    private static final Metadata.Key<String> CLIENT_VERSION_HEADER =
        Metadata.Key.of(
            "x-client-version",
            Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        final String requestId;
        final String clientVersion;
        try {
            requestId = singleValue(headers, REQUEST_ID_HEADER);
            clientVersion = singleValue(headers, CLIENT_VERSION_HEADER);
        } catch (IllegalArgumentException ex) {
            return reject(call, "Repeated request metadata");
        }

        if (requestId == null
                || !requestId.matches("[A-Za-z0-9._-]{1,64}")) {
            return reject(call, "Missing or invalid x-request-id");
        }

        if (clientVersion == null
                || clientVersion.length() > 32
                || !clientVersion.matches("[A-Za-z0-9.+_-]+")) {
            return reject(call, "Missing or invalid x-client-version");
        }

        Context context = Context.current()
            .withValue(REQUEST_ID, requestId)
            .withValue(CLIENT_VERSION, clientVersion);

        return Contexts.interceptCall(context, call, headers, next);
    }

    private static String singleValue(
            Metadata headers, Metadata.Key<String> key) {
        Iterable<String> values = headers.getAll(key);
        if (values == null) {
            return null;
        }
        Iterator<String> iterator = values.iterator();
        if (!iterator.hasNext()) {
            return null;
        }
        String value = iterator.next();
        if (iterator.hasNext()) {
            throw new IllegalArgumentException("Duplicate metadata");
        }
        return value;
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

Requiring request ID and client version here is an **illustrative policy**. If a valid client lacks a client version, the application may allow it to be omitted and default to `unknown`; if request ID is missing, the server can generate an ID instead of rejecting. Choose a policy fitting your API contract and apply it consistently.

### Why Use `getAll` Instead of Only `get`?

`Metadata` can contain multiple values for the same key. `get(key)` returns the last value or `null` if absent; `getAll(key)` lets the server detect duplicate keys. For keys expected to be unique like request ID, authorization, or tenant selection, accepting multiple values without a policy can cause different layers to interpret them differently.

Not every key must be unique. If a key is designed to repeat, define the ordering and meaning of each value. Do not manually join or split headers at the string level when `Metadata` already provides a typed API.

## 6. Service Reads Validated Metadata

Once the server interceptor binds the context, the service method can read call-scoped values:

```java
String requestId =
    RequestMetadataServerInterceptor.REQUEST_ID.get();
String clientVersion =
    RequestMetadataServerInterceptor.CLIENT_VERSION.get();

logger.info(
    "RPC received: requestId={}, clientVersion={}",
    requestId,
    clientVersion);
```

This example only logs two format-validated values. If identity authentication is needed, a separate interceptor/credentials mechanism must exist, and user identity must never be inferred from request ID or client version.

`io.grpc.Context` binds data to the call rather than storing it in global variables. When code moves to a separate executor, propagate context properly:

```java
import io.grpc.Context;
import java.util.concurrent.Executor;

Context callContext = Context.current();
Executor executor = applicationExecutor;

executor.execute(callContext.wrap(() -> {
    String requestId =
        RequestMetadataServerInterceptor.REQUEST_ID.get();
    // Continue processing within the right RPC context.
}));
```

`io.grpc.Context` is not automatically synchronized with OpenTelemetry context, Spring `LocaleContextHolder`, or SLF4J MDC. If trace/span or locale is needed on another thread, use the corresponding propagation mechanisms and restore state after processing.

## 7. Client Metadata Does Not Automatically Propagate to Downstream RPCs

An important point when building microservices: request metadata received on a server is attached only to the **current call**. If OrderService calls InventoryService, that is a new RPC with a new `ClientCall`. gRPC does not automatically copy all inbound metadata onto outbound calls.

Correct flow:

```text
Client A                 OrderService                    InventoryService
   |                          |                                  |
   | x-request-id: req-42     |                                  |
   |------------------------->|                                  |
   |                          | read, validate, store in Context |
   |                          |                                  |
   |                          | create downstream RPC            |
   |                          | x-request-id: req-42             |
   |                          |--------------------------------->|
   |                          |                                  | read metadata
   |                          |                                  |
```

OrderService must **selectively** choose which keys are permitted to forward. Never copy all headers blindly: inbound metadata may contain an audience-specific token, self-declared public client data, or sensitive values.

Example retrieving the validated request ID from context and attaching it to a downstream call:

```java
String verifiedRequestId =
    RequestMetadataServerInterceptor.REQUEST_ID.get();

InventoryGrpc.InventoryBlockingStub downstream =
    InventoryGrpc.newBlockingStub(inventoryChannel)
        .withInterceptors(
            new RequestMetadataClientInterceptor("2.4.0"))
        .withOption(
            RequestMetadataClientInterceptor.REQUEST_ID_OPTION,
            verifiedRequestId);

// downstream.reserveStock(...) sends the selectively chosen request ID.
```

In a real application, you can design a client interceptor that reads correlation context from a shared propagation mechanism instead of calling `withOption(...)` at every call site. Whichever approach you use, preserve a clear boundary: only **validated inbound values** are allowed to become outbound metadata.

Trace context should be injected/extracted using an OpenTelemetry propagator or corresponding instrumentation. Never copy `traceparent` manually as a static string if doing so breaks the parent span of the downstream call.

## 8. Request Metadata with Unary and Streaming RPCs

Metadata is attached at the start of the RPC, so receiving it in a server interceptor works the same across method types:

| RPC Type | When is request metadata sent? | When are messages sent? |
| --- | --- | --- |
| Unary | Once when starting the call | One request message |
| Server streaming | Once when opening the call | One request message, followed by multiple response messages |
| Client streaming | Once when opening the call | Multiple request messages |
| Bidirectional streaming | Once when opening the call | Multiple independent request and response messages over the stream |

The server interceptor processes metadata before the service receives the first message. For streaming, subsequent `onMessage(...)` callbacks still execute within that call's context. There is no need to repeat `x-request-id` in every message just so the server knows they belong to the same RPC.

If tenant, sequence number, or an attribute genuinely changes per message, that belongs in the Protobuf message and must be validated per message. Never try to modify request metadata after a stream has started.

## 9. Spring gRPC: Registering Client and Server Interceptors

`ClientInterceptor` and `ServerInterceptor` are `grpc-java` APIs; Spring gRPC provides ways to integrate them into channels/clients and servers according to the version, starter, and application configuration in use.

### Client

At the generated stub level, interceptors can be attached directly:

```java
GreeterGrpc.GreeterBlockingStub stub =
    GreeterGrpc.newBlockingStub(channel)
        .withInterceptors(
            new RequestMetadataClientInterceptor("2.4.0"));
```

If channels or stubs are managed by Spring, register the interceptor at the client configuration point supported by your Spring gRPC version. Verify the interceptor actually sits on the call path used by the bean; creating a Java bean without attaching it to the channel will not make metadata appear automatically.

### Server

With `grpc-java`, you can wrap a service with an interceptor:

```java
import io.grpc.ServerInterceptors;
import io.grpc.ServerServiceDefinition;

ServerServiceDefinition interceptedService =
    ServerInterceptors.intercept(
        new GreeterService(),
        new RequestMetadataServerInterceptor());

// Register interceptedService via ServerBuilder/server factory.
```

In Spring gRPC, use the server interceptor registration mechanism of the version/starter you are deploying. Never assume a `@Bean ServerInterceptor` automatically applies to every service in every version. Check:

- Is the interceptor attached to the right server/service?
- Does it apply to all methods or only a subset of methods?
- Is its ordering with tracing, authentication, and authorization correct?
- Do health/reflection endpoints need different policies?
- Is there a test confirming request metadata actually reaches the interceptor?

### Interceptor Ordering and Responsibilities

A processing chain typically requires tracing/correlation, authentication, authorization, and the service method. Exact ordering depends on the registration mechanism and how interceptors wrap calls. Define who creates IDs, who verifies credentials, who selects tenants, and who logs; never let multiple interceptors overwrite the same key without a convention.

## 10. Errors and Security When Receiving Metadata

| Scenario | Suggested response or handling | Reason |
| --- | --- | --- |
| Missing required metadata | `INVALID_ARGUMENT` or default value per contract | Request does not meet application requirements |
| Key has multiple values violating policy | `INVALID_ARGUMENT` | Avoids ambiguous interpretation |
| Missing or invalid credentials | `UNAUTHENTICATED` | Caller could not be authenticated |
| Authenticated caller lacks permission | `PERMISSION_DENIED` | Not permitted to perform the operation |
| Dependent verification service failed | `UNAVAILABLE` or appropriate infrastructure status | Never treat infrastructure failures as valid credentials |
| Deadline exceeded | `DEADLINE_EXCEEDED` | Use gRPC's deadline API |

These codes are returned via `io.grpc.Status`; never write `grpc-status` manually as a custom key. Error descriptions should not contain tokens, secret tenant details, or all received headers.

**Trust boundary:** clients can send `x-tenant-id`, `x-user-id`, `x-role`, or `x-client-version` themselves. Some values are merely descriptive metadata; they are not authenticated identities. The server must verify credentials and check permissions before using data to access resources.

**TLS and proxies:** TLS protects metadata over encrypted connections. If a proxy terminates TLS and opens another connection to the server, evaluate protection of the next hop and proxy trust policies. Never log entire `Metadata` objects, especially `authorization`, cookies, baggage, or personal data.

**Size limits:** request metadata travels via HTTP/2 headers and is subject to limits from the gRPC client/server, proxy, or load balancer. Only send small values—never send large JSON payloads, files, or permission lists in headers. Actual limits depend on the configuration of deployed components.

## 11. Testing the Client-to-Server Path

Unit tests for `Metadata.put/get` only verify local storage behavior. To prove the client interceptor is invoked and the server interceptor actually receives metadata, you need an **integration test with a gRPC channel and server**.

`grpc-java`'s `InProcessServerBuilder` and `InProcessChannelBuilder` are useful for tests without opening network ports. They work well for verifying interceptor paths and context; TLS, proxies, HTTP/2 network behavior, and header limits still require a real network environment.

| Test case | How to run | Expected result |
| --- | --- | --- |
| ASCII metadata | Client sends `x-request-id: req-42` | Server reads exact `req-42` |
| Missing optional metadata | Omit `x-client-version` | Server uses default or handles per contract |
| Missing required metadata | Omit request ID if policy requires it | Server returns defined status |
| Duplicate key | Send two `x-request-id` values | Server detects via `getAll` and handles consistently |
| Binary metadata | Send `x-client-capabilities-bin` with `byte[]` | Server receives the exact bytes |
| Two concurrent RPCs | Each call has a different request ID | No context mixing between the two calls |
| Downstream RPC | Server receives validated ID then calls another service | Downstream client sends only selectively allowed keys |
| Streaming | Multiple messages in one stream | Metadata belongs to the call, context stays stable across stream |
| Authentication | Send invalid/expired token | `UNAUTHENTICATED`, service does not run |
| TLS/proxy | Run over deployment network path | Metadata reaches server accurately and secrets do not leak |

### Minimal Integration Test Example

Suppose `.proto` generated `GreeterGrpc`, `HelloRequest`, and `HelloReply`. The test service returns the request ID placed into context by the server interceptor:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.ServerInterceptors;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.Test;

class ClientToServerMetadataTest {

    static class TestGreeter extends GreeterGrpc.GreeterImplBase {
        @Override
        public void sayHello(
                HelloRequest request,
                StreamObserver<HelloReply> observer) {
            String id =
                RequestMetadataServerInterceptor.REQUEST_ID.get();
            observer.onNext(
                HelloReply.newBuilder().setMessage(id).build());
            observer.onCompleted();
        }
    }

    @Test
    void clientMetadataReachesServerContext() throws Exception {
        String name = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(name)
            .directExecutor()
            .addService(ServerInterceptors.intercept(
                new TestGreeter(),
                new RequestMetadataServerInterceptor()))
            .build()
            .start();

        ManagedChannel channel =
            InProcessChannelBuilder.forName(name)
                .directExecutor()
                .build();
        try {
            GreeterGrpc.GreeterBlockingStub stub =
                GreeterGrpc.newBlockingStub(channel)
                    .withInterceptors(
                        new RequestMetadataClientInterceptor("2.4.0"))
                    .withOption(
                        RequestMetadataClientInterceptor.REQUEST_ID_OPTION,
                        "req-42");

            HelloReply reply = stub.sayHello(
                HelloRequest.newBuilder().setName("Mai").build());
            assertEquals("req-42", reply.getMessage());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
```

This example requires the `grpc-inprocess` dependency, JUnit 5, and classes generated from `.proto`; package/method names depend on your project. `directExecutor()` keeps the test compact but does not fully simulate production scheduling and concurrency. Add tests for duplicate keys, missing metadata, and error statuses.

To verify response trailers, create a client listener observing `onClose(status, trailers)` and inspect keys added by the server. To verify TLS or proxies, use an integration environment with the same transport type and deployment-equivalent configuration.

## 12. Practice Exercise

A Spring gRPC system has `CheckoutService.PlaceOrder`. The client needs to send a request ID, application version, and a small byte array describing capabilities. The server must read these values before executing the service and record the request ID in logs.

**Requirements:**

1. Declare `x-request-id` and `x-client-version` as ASCII keys and `x-client-capabilities-bin` as a binary key.
2. Write a client interceptor to attach metadata in `ClientCall.start(...)`; the request ID must be generated or retrieved per call.
3. Write a server interceptor to detect missing, malformed, and duplicate metadata; return clear statuses.
4. Pass the validated request ID and client version into `io.grpc.Context`; the service reads context without manually parsing headers.
5. If CheckoutService calls InventoryService, forward only permitted metadata after validation; never blindly copy all inbound headers.
6. Write an integration test proving metadata reaches server context from the client and a test verifying the rejection case.

**Self-check questions:**

- In which callback does a client interceptor add metadata?
- Does a server interceptor receive request metadata before or after the service processes the first message?
- Why is `Metadata` not a regular `Map<String, String>`?
- When should `getAll(...)` be used instead of `get(...)`?
- Why is inbound metadata not automatically present on downstream RPCs?
- With streaming RPCs, is metadata sent once or once per message?
- Why must client-sent `x-user-id` not be used as proof of identity?
- What must an integration test verify that a `Metadata.put/get` unit test cannot prove?

**Key takeaway:** Request metadata travels from client to server when an RPC starts. The client interceptor prepares headers; gRPC transports them; the server interceptor receives `Metadata`, validates it, and transfers accepted data into context for the service. In Spring gRPC, register interceptors with the right scope, forward only permitted metadata, check for duplicate keys and untrusted data, and verify the entire path with integration tests.
