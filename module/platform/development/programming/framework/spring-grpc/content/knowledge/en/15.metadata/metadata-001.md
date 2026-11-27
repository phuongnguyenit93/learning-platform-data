# Metadata Keys and Values in gRPC

In a gRPC call, Protocol Buffers messages describe **business data**, while **metadata** carries auxiliary information for handling the call: trace identifiers, authentication credentials, preferred language, client version, or observability signals. With Spring gRPC, we still work with the `grpc-java` metadata model; client-side and server-side interceptors are the common places to create, read, and control this data.

After this lesson, you will be able to:

- Distinguish metadata from Protobuf message fields and from RPC status.
- Choose proper `key` names, ASCII or binary `value` types, and understand how duplicate `key` values are handled.
- Read and write metadata using `io.grpc.Metadata` in Java; attach metadata on the client and read it on the server via interceptors.
- Identify whether metadata travels in request headers, response headers, or trailers; avoid interfering with headers managed by gRPC.
- Design testing and protection strategies for metadata when using Spring gRPC in a multi-service system.

## 1. Where Does Metadata Live in a gRPC Call?

Metadata is a collection of **key–value** pairs attached to *a single RPC call*. It is not part of the message declared in the `.proto` file. Therefore, routine metadata changes do not require modifying the message contract or regenerating Java code from Protobuf.

In the gRPC protocol over HTTP/2, metadata is transmitted via headers and trailers. A unary call can be visualized as follows:

```text
Client                                      Server
  |                                          |
  |-- Request headers ---------------------->|  incoming metadata:
  |   x-request-id: 7b9...                  |  x-request-id, authorization, ...
  |   authorization: Bearer ...             |
  |-- Protobuf request message ------------->|  business data
  |                                          |
  |<--------------------- Response headers --|  initial outgoing metadata
  |<-------------- Protobuf response message |  business data
  |<---------------------------- Trailers ---|  grpc-status, grpc-message, ...
  |                                          |
```

This is a logical diagram: some failed calls may end with **trailers-only**, without a response message or separate response headers. For server streaming, client streaming, or bidirectional streaming, call-opening metadata remains attached to the **RPC**, and does not automatically reappear on each message in the stream.

Comparison of the three types of data:

| Type | Example | When to use |
| --- | --- | --- |
| Protobuf message fields | `order_id`, `quantity`, `customer_note` | Business data belonging to the API contract that requires type checking and version compatibility |
| Application metadata | `x-request-id`, `x-client-version`, `authorization` | Control, security, or tracing information attached to the entire call |
| Protocol metadata managed by gRPC | `grpc-timeout`, `grpc-status`, `grpc-message` | Deadline, result, and status details of the RPC; use the corresponding gRPC APIs |

**Rule of thumb for choosing where to store data:** if the information is part of the meaning of the request or response that API consumers need to understand, place it in the Protobuf message. If the information serves the infrastructure handling a call, metadata is usually more appropriate.

## 2. Naming Rules for Metadata Keys

A metadata key determines how its value is interpreted. In gRPC Java, a key is represented by `Metadata.Key<T>`, where `T` is the Java type after data conversion.

| Rule | How to apply |
| --- | --- |
| Key names are case-insensitive at the protocol level | Proactively use lowercase for consistency, e.g., `x-request-id` |
| Valid names use ASCII letters, digits, `-`, `_`, and `.` | Choose short, clear names; avoid spaces and Unicode characters |
| Binary keys **must have the suffix** `-bin` | For example, `x-proof-bin` corresponds to a `byte[]` value |
| Names starting with `grpc-` are reserved for the protocol | Do not define custom keys such as `grpc-my-token` |
| HTTP/2 headers like `:method`, `:path`, `:authority` are transport components | Do not add them manually via `Metadata` |
| Multiple values may appear for the same key | Clearly define whether the application accepts one or multiple values |

Some examples:

| Key | Value type | Purpose |
| --- | --- | --- |
| `x-request-id` | ASCII string | Correlate logs across services |
| `x-client-version` | ASCII string | Record client version to support compatibility |
| `authorization` | ASCII string | Carry authentication credentials, e.g., bearer token |
| `x-proof-bin` | Binary bytes | Carry binary data in a format agreed upon by both sides |

Using the `x-` prefix in names is a recognizable application convention, **not** a mandatory requirement of gRPC. Custom key–value pairs still require both sides to agree on their meaning and data type.

## 3. How Do ASCII and Binary Values Differ?

### 3.1. ASCII Metadata

The value of a standard key is an ASCII string. They are suitable for trace IDs, language codes, versions, or short identifiers. Do not assume that Unicode strings such as Vietnamese text can be sent verbatim in ASCII metadata; if the data needs to represent Unicode or complex structures, consider putting it in Protobuf or using a well-defined encoding format.

With `grpc-java`, the standard marshaller is `Metadata.ASCII_STRING_MARSHALLER`:

```java
import io.grpc.Metadata;

Metadata.Key<String> requestIdKey =
    Metadata.Key.of("x-request-id", Metadata.ASCII_STRING_MARSHALLER);

Metadata headers = new Metadata();
headers.put(requestIdKey, "req-2026-00042");

String requestId = headers.get(requestIdKey);
System.out.println(requestId); // req-2026-00042
```

### 3.2. Binary Metadata

Binary metadata is used for byte sequences. Keys must end with `-bin`; in Java, use `Metadata.BINARY_BYTE_MARSHALLER`:

```java
Metadata.Key<byte[]> proofKey =
    Metadata.Key.of("x-proof-bin", Metadata.BINARY_BYTE_MARSHALLER);

byte[] proof = new byte[] {0x01, 0x02, 0x7F};
headers.put(proofKey, proof);

byte[] receivedProof = headers.get(proofKey);
```

When transmitted over HTTP/2, binary metadata is encoded according to protocol rules (using Base64 on the wire). **The gRPC library handles this**: in Java code, you work with `byte[]` and do not need to manually Base64-encode before calling `put`. If you Base64-encode it yourself and put the string into a binary key, both sides can easily misinterpret the data.

Binary metadata does not equate to securely encrypted data. If carrying sensitive information, TLS, access control, and appropriate logging policies are still required.

### 3.3. Duplicate Keys and Retrieving Values

A `Metadata` object can hold multiple values for the same key:

```java
Metadata.Key<String> tagKey =
    Metadata.Key.of("x-tag", Metadata.ASCII_STRING_MARSHALLER);

Metadata metadata = new Metadata();
metadata.put(tagKey, "internal");
metadata.put(tagKey, "priority");

String oneValue = metadata.get(tagKey);       // Last value: priority
Iterable<String> allValues = metadata.getAll(tagKey);
// allValues contains both "internal" and "priority"
```

`get(key)` returns the last value written for the key, or `null` if absent; `getAll(key)` returns the corresponding values, or `null` if absent. Do not assume that every key only has a single value; for critical keys like `authorization`, the application should clearly define its policy when multiple values appear, avoiding accidentally picking an unintended value.

`Metadata` is a mutable object. You should create metadata scoped to the call or let an interceptor populate it per call; avoid sharing a single object that is mutated across multiple threads.

## 4. Request Headers, Response Headers, and Trailers

Even though all are metadata, **where they appear** determines when they are used:

| Location | Direction | Examples | When read/written? |
| --- | --- | --- | --- |
| Request headers | Client → server | `x-request-id`, `authorization` | Client adds before starting the RPC; server reads before dispatching to the service |
| Initial response headers | Server → client | `x-server-version`, routing info | Server sends when starting the response; client receives before or during result processing |
| Response trailers | Server → client | `grpc-status`, `grpc-message`, custom error details | Sent when the RPC finishes, including failed RPCs |

At the API layer, `grpc-status` is the result code of the RPC, such as `OK`, `INVALID_ARGUMENT`, `UNAUTHENTICATED`, or `DEADLINE_EXCEEDED`. In Java, you should use `io.grpc.Status` and gRPC methods to close the call, rather than creating a custom metadata key named `grpc-status`.

For application-defined error information, a separate trailer (e.g., `x-error-id`) can be used if both sides agree. Most structured business errors should still consider using the standard gRPC error details mechanism or a clear API design, instead of stuffing all error data into headers.

## 5. Attaching Metadata to a gRPC Client Using an Interceptor

Suppose the project has generated `GreeterGrpc` from a `.proto` file and already has a `Channel` connected to the server. The goal is to generate a **new request ID for every RPC**, even when reusing the same stub:

```java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import java.util.UUID;

public final class RequestIdClientInterceptor implements ClientInterceptor {

    private static final Metadata.Key<String> REQUEST_ID_KEY =
        Metadata.Key.of("x-request-id", Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        ClientCall<ReqT, RespT> delegate = next.newCall(method, callOptions);

        return new ForwardingClientCall.SimpleForwardingClientCall<ReqT, RespT>(
                delegate) {
            @Override
            public void start(
                    ClientCall.Listener<RespT> responseListener,
                    Metadata headers) {

                headers.put(REQUEST_ID_KEY, UUID.randomUUID().toString());
                super.start(responseListener, headers);
            }
        };
    }
}
```

Attaching the interceptor and deadline to the stub:

```java
import java.util.concurrent.TimeUnit;

GreeterGrpc.GreeterBlockingStub stub = GreeterGrpc.newBlockingStub(channel)
    .withInterceptors(new RequestIdClientInterceptor())
    .withDeadlineAfter(2, TimeUnit.SECONDS);

// stub.sayHello(...) will send x-request-id in the request headers.
```

In this example, each call to `start(...)` adds a new UUID. The `withDeadlineAfter(...)` mechanism uses the gRPC API to set the deadline; the library handles the corresponding protocol metadata. You should not set `grpc-timeout` manually via `Metadata.put`.

If you only need **static** metadata for a simple case, `io.grpc.stub.MetadataUtils.newAttachHeadersInterceptor(metadata)` can also attach a prepared set of headers. A custom interceptor generating a request ID like the one above is more suitable when the value must change per call.

## 6. Reading and Validating Metadata on the gRPC Server

A server interceptor receives request headers **before** forwarding the call to the service. The example below requires `x-request-id` and places it into `io.grpc.Context` so handler code can read it:

```java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class RequestIdServerInterceptor implements ServerInterceptor {

    private static final Metadata.Key<String> REQUEST_ID_KEY =
        Metadata.Key.of("x-request-id", Metadata.ASCII_STRING_MARSHALLER);

    private static final Context.Key<String> REQUEST_ID_CONTEXT =
        Context.key("request-id");

    public static String currentRequestId() {
        return REQUEST_ID_CONTEXT.get();
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String requestId = headers.get(REQUEST_ID_KEY);
        if (requestId == null || requestId.isBlank()) {
            call.close(
                Status.INVALID_ARGUMENT.withDescription(
                    "x-request-id is required"),
                new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        Context context =
            Context.current().withValue(REQUEST_ID_CONTEXT, requestId);

        return Contexts.interceptCall(context, call, headers, next);
    }
}
```

Inside a server-side RPC method, you can call `RequestIdServerInterceptor.currentRequestId()` to retrieve the request ID assigned by the interceptor. `Context` belongs to the gRPC execution thread of the call; if you switch to another executor or asynchronous thread, you must propagate the context properly to avoid losing the value.

**Note on the example:** requiring a request ID is an **illustrative policy**. In a real system, the server can also generate an ID if the client does not send one. If the client supplies an ID for logging, its length and format should be validated/bounded before passing it into the observability system.

### Integration in Spring gRPC

Spring gRPC builds services on top of `grpc-java`, so the `ClientInterceptor` and `ServerInterceptor` above can be reused. Register interceptors using the server/client configuration mechanism of the Spring gRPC version or starter you are using. How global interceptors are declared, their scope, and their execution order may vary by version; check your application's actual configuration.

On the client side, configure the interceptor to be attached to the appropriate stub/channel. On the server side, ensure the interceptor runs on the services that need metadata validation. If there are multiple interceptors (authentication, tracing, logging), clearly design their order and responsibilities.

## 7. How Does Metadata Relate to Authentication, Deadlines, and Tracing?

### Authentication

`authorization` typically holds authentication credentials sent by the client. However, **having the header** does not mean the client is authenticated: the server must verify the signature, expiration, issuer, and permissions according to the system's security scheme. A custom header such as `x-user-id` should not be treated as a trusted identity unless verified by a trusted component.

In `grpc-java`, `CallCredentials` is an option for attaching per-call authentication credentials. For network connections, use TLS to protect data in transit; metadata itself does not guarantee confidentiality. Never log tokens, cookies, or sensitive data into logs/traces, even at the debug level.

### Deadlines and Call Cancellation

`grpc-timeout` is metadata managed by the protocol. Instead of filling in this header manually, a Java client calls `withDeadlineAfter(...)` or `withDeadline(...)`. When the deadline expires, the client may receive `DEADLINE_EXCEEDED`; server code should check cancellation status and stop unnecessary work. When making downstream RPCs to other services, make sure to propagate an appropriate deadline so child calls do not run indefinitely.

### Distributed Tracing

An application request ID helps correlate logs per call, but it **does not replace** the trace ID and span ID of distributed tracing. Systems using OpenTelemetry can propagate trace context through metadata via a configured propagator. Prefer configuring unified instrumentation/propagators across services rather than having each interceptor invent its own trace header format.

### Streaming

With streaming RPCs, the client sends metadata when initiating the call, then transmits multiple Protobuf messages. If a piece of information changes **per message** (such as sequence number, measurement timestamp, or per-record attributes), put it in the Protobuf message. Do not try to use request metadata to carry values that change continuously within a stream. The final outcome of a streaming RPC is still reported via status/trailers.

## 8. Common Design Mistakes

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| Server cannot find metadata | Wrong key name, mixing up ASCII and `-bin`, interceptor not registered | Standardize key and marshaller, verify interceptor configuration on both sides |
| Binary data corrupted after decoding | Manually Base64-encoding before using the binary marshaller | Pass `byte[]` directly; let gRPC handle wire conversion |
| Works in unary but does not update per streaming message | Metadata is attached per RPC only | Move per-message varying values into Protobuf |
| Request ID is always identical | Generating a single ID when creating the stub/interceptor | Generate the ID inside `start(...)` for each call |
| Client receives `UNAUTHENTICATED` despite sending header | Invalid/expired token or server does not trust the submitted value | Verify credential issuance and validation; do not just check for header presence |
| Failure at proxy before reaching the service | Total header/trailer size exceeds infrastructure limits | Keep metadata compact; move large payloads to messages or appropriate storage |
| Secrets leaked in logs | Logging the entire `Metadata` object | Log only allowed keys and mask sensitive values |
| Request ID lost when switching to async processing | Not propagating `Context` across the executor | Use gRPC's context propagation mechanism suited to your execution model |

Metadata is not a free-form data store. Large values increase transmission overhead and can exceed header limits of servers, proxies, or load balancers. Do not use metadata to carry files, large JSON payloads, or complex business objects.

## 9. Testing Strategy

With Spring gRPC, you can test interceptors using a gRPC server/client in integration tests. `grpc-java`'s `InProcessServerBuilder` and `InProcessChannelBuilder` are useful for tests that do not need to open network ports, whereas testing TLS or proxy behavior requires a real network environment.

| Test case | Input | Expected result |
| --- | --- | --- |
| Valid ASCII | Client sends `x-request-id: req-42` | Server reads `req-42` accurately |
| Missing required key per example | Omit `x-request-id` | Server returns `INVALID_ARGUMENT` with an appropriate description |
| Binary round-trip | Send `x-proof-bin` with a byte array containing non-printable bytes | Server receives every byte intact |
| Duplicate keys | Send two values for `x-tag` | `getAll` retrieves both; handled according to the agreed policy |
| Two consecutive RPCs | Reuse a single stub with the interceptor attached | Each RPC has a different request ID |
| Deadline too short | Client sets a deadline shorter than processing time | Caller receives the appropriate deadline status and server can handle cancellation |
| Multi-message streaming | Create a stream with multiple messages | Metadata is attached to the call; varying data is read from each message |
| Security/observability | Send a test token and enable logging | Token is not leaked; only ID and allowed fields are logged |

When testing metadata with trailers, capture metadata at the RPC completion event (`onClose(status, trailers)` of a client interceptor). Values in trailers are only guaranteed to appear when the call finishes, so you should not check for them immediately after receiving the first message.

## 10. Practical Scenario

A Spring gRPC system has a `checkout-service` client calling the unary RPC `InventoryService.ReserveStock` to reserve stock, and may then call a streaming RPC to receive processing progress. The team wants to correlate logs across both services and prevent requests from running too long.

1. Agree on custom key `x-request-id` as ASCII metadata. The client generates an ID per user request and passes the same ID across related RPCs, while keeping tracing span context via its own mechanism.
2. The client configures a deadline using the stub API. `inventory-service` reads the request ID in a server interceptor, validates its format, and places it into `Context` so logs for the RPC can use it.
3. Fields `product_id`, `quantity`, and stock reservation status are defined in Protobuf messages; they are not moved to metadata just because they could be string-encoded.
4. If business logic requires sending a specialized binary verification code, both sides agree on key `x-proof-bin` and represent its value as `byte[]`; for standard tokens, prefer appropriate credentials and authentication mechanisms.
5. For streaming, progress status is placed in each response message. The server ends the stream with a gRPC status; if returning an error, the client reads the status and, when present, error details/trailers.

**Self-check exercises:**

- Why is `x-request-id` more appropriate than `grpc-request-id` for custom metadata?
- If an application sends a binary value containing byte `0x00`, which marshaller should be used and why should you not Base64-encode it yourself?
- When should `getAll` be used instead of `get`?
- Should a `discount_code` field that determines pricing calculation be placed in metadata or in the request message? Explain in terms of the API contract.
- Why is setting the `authorization` header without verifying the token insufficient to protect an RPC?

**Conclusion:** Metadata is the channel for carrying call context in gRPC via key–value pairs. Proper design starts with distinguishing ASCII and binary values, choosing headers vs. trailers, managing per-RPC lifecycles, and using `grpc-java` APIs for status, deadlines, and credentials. When implementing in Spring gRPC, test both metadata flow through interceptors and security, network, and threading boundaries.
