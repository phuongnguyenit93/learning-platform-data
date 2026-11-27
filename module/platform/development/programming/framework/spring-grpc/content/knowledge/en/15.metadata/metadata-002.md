# ASCII Metadata and Binary Metadata

In gRPC, **metadata** carries auxiliary information for an RPC call as **key–value** pairs. The two primary value types are **ASCII metadata** (character strings) and **binary metadata** (byte sequences). Both are transported via HTTP/2 headers or trailers, but they differ in key naming, wire encoding, and the data types manipulated by the Java application.

In the Spring gRPC ecosystem, both types of metadata are handled using the `grpc-java` API, particularly `io.grpc.Metadata` and interceptors. Understanding the exact differences helps transmit request IDs, client information, and small binary payloads consistently, while avoiding encoding bugs, information leaks, and header size limits.

**Learning objectives:**

- Distinguish ASCII metadata and binary metadata by key name, value type, encoding, and use cases.
- Create `Metadata.Key<String>` and `Metadata.Key<byte[]>` properly with their respective `Marshaller`.
- Send, receive, and inspect data via `Metadata.put`, `get`, and `getAll` in Java.
- Recognize limits regarding size, access control, Unicode data, and duplicate metadata keys.
- Integrate with gRPC client/server interceptors in a Spring application and build appropriate tests.

## 1. Why Does gRPC Need Two Types of Metadata?

Consider an `OrderService` written with Spring gRPC. When a client calls `PlaceOrder`, the Protobuf message carries `order_id` and the list of items. Beyond business data, the client wants to send:

- `x-request-id: req-2026-0042` to correlate logs for the same request.
- `x-client-version: 3.2.1` to analyze the calling application version.
- A set of bytes describing client capabilities (`x-capabilities-bin`), e.g., data in a format agreed upon by both sides.

The first two values are short strings representable in ASCII. The third value consists of arbitrary bytes, so binary metadata should be used. If arbitrary bytes are stuffed into an ASCII header, some bytes are non-printable characters and conversion may alter the content.

Metadata belongs to the **RPC call scope**, not individual messages. For unary and all streaming RPCs, headers are sent when starting the call; response trailers are sent upon completion. Values that vary per record in a stream should belong to the Protobuf message.

## 2. Comparing ASCII Metadata and Binary Metadata

| Criterion | ASCII metadata | Binary metadata |
| --- | --- | --- |
| Key name | E.g., `x-request-id` | **Must** end with `-bin`, e.g., `x-capabilities-bin` |
| Value in Java | `String` | `byte[]` |
| Common marshaller | `Metadata.ASCII_STRING_MARSHALLER` | `Metadata.BINARY_BYTE_MARSHALLER` |
| Representation over HTTP/2 | ASCII string in header value | Bytes Base64-encoded according to gRPC rules |
| Suitable for | IDs, language codes, versions, short flags | Small byte payloads, binary formats agreed by both sides |
| Common pitfalls | Unicode or unsuitable control characters; overly long values | Double Base64-encoding; wrong key suffix; unaligned byte format |
| Security | Not automatically encrypted | Also not automatically encrypted |

A common misconception is that **binary metadata means security encryption**. Base64 merely converts bytes into a representation suitable for HTTP/2 headers; anyone able to read the headers can decode them back to the original bytes. Therefore, both types still require appropriate transport protection, such as TLS over a network.

### 2.1. General Key Rules

According to the gRPC format, metadata key names use lowercase ASCII letters `a–z`, digits `0–9`, hyphens `-`, underscores `_`, and periods `.`. HTTP/2 requires lowercase header names; some APIs may normalize input names, but application code should proactively use lowercase.

Keys starting with `grpc-` are reserved for the protocol. Examples:

| Key | Assessment | Reason |
| --- | --- | --- |
| `x-request-id` | Valid, ASCII type | No `-bin` suffix |
| `x-capabilities-bin` | Valid, binary type | Has `-bin` suffix |
| `authorization` | Valid, ASCII type | Typically used for authentication credentials per the chosen scheme |
| `grpc-custom-id` | Do not use for application metadata | The `grpc-` prefix is reserved |
| `x-capabilities` for raw bytes | Incorrect design | Lacks `-bin` suffix so cannot be used as binary metadata |
| `Tên-Người-Dùng` | Invalid | Key contains characters outside the allowed ASCII alphabet |

The `-bin` suffix is a **data type** rule, not just a naming preference. With `Metadata.Key.of(...)`, the ASCII marshaller goes with regular keys, while the binary marshaller goes with `-bin` keys.

### 2.2. Value Rules

**ASCII values:** In the gRPC protocol, custom ASCII header values are represented using printable ASCII characters (byte range `0x20` to `0x7E`). Avoid putting accented Vietnamese text, control characters, or multi-line content directly into ASCII metadata. If Unicode text is needed, consider a `string` field in Protobuf; if a secondary protocol strictly requires metadata, agree on an encoding scheme with the receiver.

**Binary values:** Can contain any byte value, including `0x00`, `0x80`, and `0xFF`. The gRPC library encodes/decodes them during transport, so in Java the application still works directly with `byte[]`.

## 3. How Are ASCII and Binary Transmitted Over HTTP/2?

Conceptually:

```text
                 Java Application                  HTTP/2                     Java Application

ASCII    "req-42" --------------------------> x-request-id: req-42 -----------> "req-42"

Binary   byte[] {0x00, 0x7F, 0xFF} ---------> x-data-bin: AH// --------------> byte[] {0x00, 0x7F, 0xFF}
                           gRPC encodes Base64                        gRPC decodes Base64
```

In this example, `AH//` is the Base64 representation of the three bytes `00 7F FF`. This illustrates the wire value; code using `grpc-java` **does not add a Base64 step itself**.

For binary metadata, the protocol may accept Base64 with or without `=` padding characters; the library is responsible for compatibility and handling these details. Do not write application logic assuming that an observed header will always have one exact Base64 representation.

**Transport limits:** Metadata resides in HTTP/2 headers/trailers and is subject to size limits enforced by the gRPC server, client, reverse proxy, or load balancer. The gRPC protocol specification recommends a default limit of around 8 KiB for request headers, though actual limits depend on each component's configuration. Binary metadata also incurs representation overhead when transmitted via Base64. Therefore, only send small values; files, large JSON payloads, and complex business data belong in messages or appropriate storage.

## 4. Declaring Metadata Keys and Values in Java

`io.grpc.Metadata` is a mutable collection of key–value pairs. `Metadata.Key<T>` binds a key name to a data conversion mechanism via a marshaller.

### 4.1. ASCII Metadata Example

```java
import io.grpc.Metadata;

public class AsciiMetadataExample {
    private static final Metadata.Key<String> REQUEST_ID =
        Metadata.Key.of("x-request-id", Metadata.ASCII_STRING_MARSHALLER);

    private static final Metadata.Key<String> CLIENT_VERSION =
        Metadata.Key.of("x-client-version", Metadata.ASCII_STRING_MARSHALLER);

    public static void main(String[] args) {
        Metadata metadata = new Metadata();

        metadata.put(REQUEST_ID, "req-2026-0042");
        metadata.put(CLIENT_VERSION, "3.2.1");

        System.out.println(metadata.get(REQUEST_ID));    // req-2026-0042
        System.out.println(metadata.get(CLIENT_VERSION)); // 3.2.1
    }
}
```

In the example above, the Java type is `String`, the key does not end with `-bin`, and the marshaller is `ASCII_STRING_MARSHALLER`. When the receiving side knows the exact key name and ASCII rule, it can read the value without assuming any extra binary format.

### 4.2. Binary Metadata Example

```java
import io.grpc.Metadata;
import java.util.Arrays;

public class BinaryMetadataExample {
    private static final Metadata.Key<byte[]> CAPABILITIES =
        Metadata.Key.of(
            "x-capabilities-bin",
            Metadata.BINARY_BYTE_MARSHALLER
        );

    public static void main(String[] args) {
        byte[] bytes = new byte[] {0x00, 0x7F, (byte) 0xFF};

        Metadata metadata = new Metadata();
        metadata.put(CAPABILITIES, bytes);

        byte[] received = metadata.get(CAPABILITIES);
        System.out.println(Arrays.equals(bytes, received)); // true
    }
}
```

Casting `(byte) 0xFF` is necessary because `byte` in Java is signed and only accepts integer literals from `-128` to `127` without a cast. Even though it prints as `-1` as a `byte`, the actual bit pattern is still `0xFF`.

In this example, `byte[]` is data whose format is defined by the application. Both sides must agree on the structure, version, and meaning of each byte. Using `-bin` only solves transport; it **does not automatically define a schema** for the byte sequence.

### 4.3. Why Not Base64-Encode Before Calling `put`?

Suppose the original bytes are `{0x00, 0x7F, 0xFF}`. If the application Base64-encodes them into the string `"AH//"`, extracts the ASCII bytes of this string, and passes them into `BINARY_BYTE_MARSHALLER`, gRPC will encode *those ASCII bytes themselves* a second time on the wire. The receiver gets back the bytes of `"AH//"`, not the original three bytes.

Do it right:

```java
byte[] raw = new byte[] {0x00, 0x7F, (byte) 0xFF};
metadata.put(CAPABILITIES, raw);
byte[] restored = metadata.get(CAPABILITIES);
```

Only perform Base64 encoding yourself when the **application** format has been explicitly specified by both sides as a Base64 string. In that case, consider whether an ASCII key is more appropriate; do not confuse application rules with gRPC transport encoding.

## 5. A Single Key Can Hold Multiple Values

`Metadata` is not a regular `Map<String, String>`. It can contain multiple entries with the same key name. The `put` method adds a value, `get` returns the last corresponding value, and `getAll` returns an iterable of the values.

```java
Metadata.Key<String> TAG =
    Metadata.Key.of("x-tag", Metadata.ASCII_STRING_MARSHALLER);

Metadata headers = new Metadata();
headers.put(TAG, "web");
headers.put(TAG, "canary");

String latestTag = headers.get(TAG);          // canary
Iterable<String> tags = headers.getAll(TAG); // web and canary
boolean exists = headers.containsKey(TAG);   // true
```

Notes when reading:

- If the key does not exist, `get` or `getAll` returns `null`.
- If only one value is allowed (e.g., a client version code), check the value count and reject ambiguous requests according to your API policy.
- Do not assume that headers merged or split at an intermediate HTTP layer will retain their exact original text layout; the application should interact via the `Metadata` API.
- Metadata is not designed for concurrent modification of a single instance across threads. Create metadata per call and avoid retaining references to a `byte[]` that may be mutated after being added to metadata; copy the array if the data lifecycle requires it.

**Same name with a different type is not a conversion:** `Metadata.Key.of("x-data-bin", Metadata.ASCII_STRING_MARSHALLER)` is not a valid way to read binary metadata as a string. Both sides must agree on the key name and marshaller type, and then decode the `byte[]` content themselves if there is an internal format.

## 6. Attaching ASCII and Binary Metadata to a gRPC Client

In Spring gRPC, clients typically use stubs generated by Protobuf/gRPC. A `grpc-java` interceptor can add metadata **per call** before the client sends request headers.

The following example adds an ASCII request ID and a byte representing client capabilities. The sample format for `x-capabilities-bin` is **one byte**, where the lowest bit indicates that the client supports an optional feature. This is an illustrative format proactively agreed upon by client and server.

```java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import java.util.UUID;

public final class ClientMetadataInterceptor implements ClientInterceptor {
    private static final Metadata.Key<String> REQUEST_ID =
        Metadata.Key.of("x-request-id", Metadata.ASCII_STRING_MARSHALLER);

    private static final Metadata.Key<byte[]> CAPABILITIES =
        Metadata.Key.of("x-capabilities-bin", Metadata.BINARY_BYTE_MARSHALLER);

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

                headers.put(REQUEST_ID, UUID.randomUUID().toString());
                headers.put(CAPABILITIES, new byte[] {0x01});
                super.start(responseListener, headers);
            }
        };
    }
}
```

Attaching the interceptor to a stub:

```java
// channel is configured by the Spring gRPC application or grpc-java.
OrderServiceGrpc.OrderServiceBlockingStub stub =
    OrderServiceGrpc.newBlockingStub(channel)
        .withInterceptors(new ClientMetadataInterceptor());

// Each time stub.placeOrder(...) starts, the interceptor adds request headers.
```

The names `OrderServiceGrpc` and `placeOrder` are just examples of classes/methods generated from a `.proto` contract; in a real project, replace them with your actual stub. The interceptor above generates a new request ID inside `start(...)` so reusing the stub will not unintentionally cause RPCs to share the same ID.

If the system needs to preserve **a single correlation ID across multiple RPCs** of the same user request, obtain the ID from a trusted context and reuse it intentionally rather than always generating a new one. Distributed tracing should use a configured propagation mechanism rather than trying to replace all trace headers with custom request IDs.

## 7. Reading and Validating Both Types of Metadata on the Server

`ServerInterceptor` receives `Metadata headers` before gRPC dispatches the call to the service. You can validate ASCII values and byte payloads here.

```java
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class ServerMetadataInterceptor implements ServerInterceptor {
    private static final Metadata.Key<String> REQUEST_ID =
        Metadata.Key.of("x-request-id", Metadata.ASCII_STRING_MARSHALLER);

    private static final Metadata.Key<byte[]> CAPABILITIES =
        Metadata.Key.of("x-capabilities-bin", Metadata.BINARY_BYTE_MARSHALLER);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String requestId = headers.get(REQUEST_ID);
        byte[] capabilities = headers.get(CAPABILITIES);

        boolean badRequestId = requestId == null
            || requestId.isBlank()
            || requestId.length() > 64;

        // Illustrative protocol: payload is exactly 1 byte, bit 0 describes a capability.
        boolean badCapabilities = capabilities == null
            || capabilities.length != 1;

        if (badRequestId || badCapabilities) {
            call.close(
                Status.INVALID_ARGUMENT.withDescription(
                    "Invalid request metadata"),
                new Metadata()
            );
            return new ServerCall.Listener<ReqT>() {};
        }

        boolean supportsFeature = (capabilities[0] & 0x01) != 0;
        // From here, validated information can be attached to Context if the service needs it.
        // Do not log sensitive bytes.
        return next.startCall(call, headers);
    }
}
```

This is an example of **application policy**: the server decides to require both keys and a binary payload of exactly one byte. The gRPC protocol does not mandate these custom keys. Another service might treat a missing capability as a default value and validate it only when provided by the client.

In a Spring gRPC system, register `ClientInterceptor` and `ServerInterceptor` according to the mechanism of the Spring gRPC/starter version in use, and verify they apply to the right channel, stub, or service. Ensure interceptor registration is actually tested; merely declaring a Java class does not make the interceptor run automatically.

## 8. Using Metadata in Response Headers and Trailers

Both metadata types do not only appear in requests. The server can also send them:

| Location | Examples | When the client reads |
| --- | --- | --- |
| Request headers | `x-request-id`, `x-capabilities-bin` | Server receives when the RPC starts |
| Initial response headers | `x-server-version`, `x-negotiated-bin` | Client receives when the server starts responding |
| Response trailers | `x-error-id`, `x-diagnostic-bin` | Client receives when the RPC finishes |

In `grpc-java`'s `ServerCall` API, initial metadata can be sent using `sendHeaders(...)` and trailers returned via `close(status, trailers)`:

```java
// Illustrative snippet inside a class managing ServerCall.
Metadata responseHeaders = new Metadata();
responseHeaders.put(
    Metadata.Key.of(
        "x-server-version",
        Metadata.ASCII_STRING_MARSHALLER),
    "1.4.0"
);
call.sendHeaders(responseHeaders);

Metadata trailers = new Metadata();
trailers.put(
    Metadata.Key.of(
        "x-error-id",
        Metadata.ASCII_STRING_MARSHALLER),
    "err-42"
);
// When completing the RPC, call.close(status, trailers) sends status and trailers.
```

In a real call, `sendHeaders` must follow `ServerCall` lifecycle ordering and must not be called repeatedly in an invalid state. `grpc-status` and `grpc-message` are managed by gRPC through `Status`; do not add them manually as custom keys. Failed calls can return **trailers-only**, so clients should not assume initial response headers are always present.

In a client interceptor, response headers can be observed via `ClientCall.Listener.onHeaders(Metadata)` and trailers via `ClientCall.Listener.onClose(Status, Metadata)`. For failed RPCs, the completion metadata is often more important than a return message because no message may exist.

## 9. Deciding Between ASCII, Binary, or a Protobuf Field

Choose the type based on **data meaning**, even before choosing an encoding tool:

| Requirement | Recommended storage | Explanation |
| --- | --- | --- |
| Short request ID | ASCII metadata | Value is context for the entire RPC |
| Client version `3.2.1` | ASCII metadata | Short string, readable and useful for observability |
| Small binary flag data with an agreed schema | Binary metadata `-bin` | Preserves raw bytes without manual Base64 |
| Accented user name | Protobuf `string` if business data | Explicit Unicode support and typed contract |
| List of products and quantities | Protobuf message | Business payload requiring a schema and compatibility testing |
| Large image or file | Appropriate message/stream | Metadata is constrained by header size limits |
| Access token | Credentials and protected transport | Requires identity verification and security policy, not just metadata type selection |
| Deadline | gRPC deadline API | The library creates `grpc-timeout`; applications do not write system keys manually |
| RPC status | `io.grpc.Status` | gRPC generates the final status code in trailers |

If a binary format is complex or needs to evolve across multiple fields, a Protobuf message with a `bytes` field or dedicated schema is usually easier to manage. Binary metadata does not carry schema information or automatic compatibility like Protobuf.

## 10. Common Pitfalls and How to Fix Them

| Symptom | Likely cause | Resolution |
| --- | --- | --- |
| `Metadata.Key.of(...)` fails to create key | Using binary marshaller with a name lacking `-bin`, or vice versa | Match the proper suffix and marshaller |
| Server receives unexpected bytes | Client Base64-encoded before writing binary metadata | Pass raw bytes directly to `put` |
| Accented ASCII string or newlines get corrupted | Value is not valid ASCII | Use Protobuf `string` or an explicit encoding convention |
| `get(key)` returns `null` | Missing key, wrong key name, interceptor not attached | Check key name/type, sender side, and interceptor configuration |
| Only one of multiple values is read | Using `get` when key is allowed to repeat | Use `getAll`, apply value count policy |
| Works in test environment but fails through proxy | Proxy modifies/strips headers or enforces size limits | Test over the actual deployment path, reduce metadata size |
| Secrets appear in logs | Logging all headers/trailers | Use a log allowlist for keys, mask tokens and sensitive bytes |
| Value unexpectedly changes during processing | Reusing mutable `byte[]` or `Metadata` across calls | Copy bytes that must stay stable; create metadata per call |

Two additional safety principles:

1. **Do not trust data just because it is in metadata.** Clients can set custom keys themselves; the server still needs to validate format, size, permissions, and authenticity where appropriate.
2. **Do not confuse Base64 with TLS or end-to-end encryption.** Binary metadata can be read if transport is unprotected. Avoid placing secrets in error messages, logs, or traces.

## 11. Testing ASCII and Binary Metadata

You can test `Metadata` logic with pure Java unit tests, then test interceptors using an in-process gRPC server/channel or a Spring gRPC integration environment. Tests involving TLS, proxies, and header limits should run over the corresponding network path since in-process transport does not simulate all HTTP/2 behavior.

Example JUnit 5 test for basic data operations:

```java
import static org.junit.jupiter.api.Assertions.*;
import io.grpc.Metadata;
import java.util.Arrays;
import org.junit.jupiter.api.Test;

class MetadataTypesTest {
    @Test
    void asciiAndBinaryRoundTrip() {
        Metadata.Key<String> idKey =
            Metadata.Key.of(
                "x-request-id", Metadata.ASCII_STRING_MARSHALLER);
        Metadata.Key<byte[]> dataKey =
            Metadata.Key.of(
                "x-data-bin", Metadata.BINARY_BYTE_MARSHALLER);

        byte[] original = {0x00, 0x7F, (byte) 0xFF};
        Metadata headers = new Metadata();
        headers.put(idKey, "req-42");
        headers.put(dataKey, original);

        assertEquals("req-42", headers.get(idKey));
        assertArrayEquals(original, headers.get(dataKey));
        assertTrue(headers.containsKey(dataKey));
    }
}
```

For integration testing, include these cases:

1. **Valid ASCII:** client sends `x-request-id`, server reads the exact value.
2. **Binary with special bytes:** send an array containing `0x00`, `0x7F`, `0xFF` and verify received bytes.
3. **Missing key:** server applies the expected policy: uses a default value or returns `INVALID_ARGUMENT`.
4. **Multiple values:** send a repeated key, verify `get` and `getAll` are not misunderstood.
5. **Per-RPC interceptor:** two calls sharing a stub still attach separate metadata per call.
6. **Failure termination:** client receives status and, when present, error metadata in trailers.
7. **Over proxy/TLS:** metadata is preserved accurately and sensitive data is not leaked in logs.
8. **Streaming:** headers are not misinterpreted as information changing per message.

## 12. Practice Exercise

You are building `RecommendationService` with Spring gRPC. The client needs to send:

- Request ID `"req-875"`.
- Application version `"4.0.1"`.
- Four bytes `{0x00, 0x10, 0x7F, 0xFF}` describing features supported by the client.
- A list of hundreds of products used as input for the algorithm.

**Practice tasks:**

1. Choose ASCII key names for the request ID and client version.
2. Choose a key with the `-bin` suffix for the four bytes, and declare the corresponding `Metadata.Key<byte[]>` and `BINARY_BYTE_MARSHALLER`.
3. Write a snippet creating `Metadata`, calling `put`, and proving `get` retrieves the exact bytes, including `0xFF`.
4. Explain why the product list belongs in the Protobuf request message rather than request headers.
5. Describe how to verify metadata when the server receives a request and how to test in a real environment with a proxy.

**Self-check questions:**

- What does the `-bin` suffix determine?
- Why should `"AH//"` not be put into binary metadata as ASCII bytes if the original payload is `00 7F FF`?
- What will `Metadata.get(...)` do if the key is absent or appears multiple times?
- Can binary metadata carry sensitive tokens without TLS?
- When streaming, where should data that changes per message be placed?

**Key takeaway:** ASCII metadata serves short string values; binary metadata preserves raw bytes with `-bin` keys. Both are metadata of the *RPC call*, transferred by `grpc-java` over HTTP/2. Choosing the right marshaller, keeping payloads small, validating data on the server, and using TLS/credentials when needed form the foundation for implementing reliable metadata in Spring gRPC.
