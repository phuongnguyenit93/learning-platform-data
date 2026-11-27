# Metadata Limits

## Learning Objectives

After this lesson, you can:

- Explain gRPC metadata and distinguish metadata from the protobuf message body.
- Distinguish inbound metadata limits on server and client from outbound metadata control.
- Configure inbound metadata limits using the grpc-java Netty builder.
- Design metadata keys/values, ASCII, and binary metadata according to the rules.
- Limit entry counts, key/value lengths, and duplicate data at the application boundary.
- Use metadata for authentication, tracing, and correlation without turning headers into a payload channel.
- Understand streaming RPC metadata and trailing metadata.
- Test metadata near and above the threshold and verify actual Spring gRPC configuration.

## 1. What is metadata and why limit it?

In **SPRING_GRPC**, metadata is a set of key/value pairs accompanying an RPC. Clients usually send initial metadata alongside request headers; the server can send initial metadata and trailing metadata (trailers) back to the client. Metadata typically carries control information such as credentials, trace context, correlation IDs, locale, or routing hints.

Metadata is not the protobuf message body. A unary RPC may have a small protobuf request while its headers carry a huge token, claim list, or arbitrary values. Conversely, a protobuf message may be large while metadata has only a few entries. Both data types must be limited independently.

If metadata is unbounded, callers can send very many headers or very long values. The transport has to buffer and process them before the service handler runs; this consumes memory, CPU, and can inflate parsing, logging, and authentication cost. Large response metadata can also cause client errors or leak data that should not be returned in headers.

**Metadata limits** control the metadata size an endpoint accepts receiving. You should combine transport-level receive limits with application-level validation of keys, values, entry counts, and content.

~~~mermaid
flowchart TD
    A["RPC starts"] --> B["HTTP/2 headers / gRPC metadata"]
    B --> C{"Inbound metadata below limit?"}
    C -- "No" --> D["Reject at transport"]
    C -- "Yes" --> E["Authentication and interceptors"]
    E --> F["Validate key/value and policy"]
    F --> G["Service handler"]
    G --> H["Response headers / trailers"]
    H --> I["Client inbound metadata limit"]
~~~

Limits must be configured on both ends: the server protects against oversized request metadata; the client protects against oversized response metadata or trailers.

## 2. Inbound metadata limits by request and response direction

Always identify sender and receiver for each direction:

| Metadata | Sender | Receiver | Limit to consider |
| --- | --- | --- | --- |
| Request headers | Client | Server | Server inbound metadata limit |
| Response initial headers | Server | Client | Client inbound metadata limit |
| Response trailers | Server | Client | Client receive-side metadata handling/limit per transport |
| Metadata of outbound call from service A | Service A client stub | Service B server | Server B inbound limit and validation in A |

The inbound limit on the server does not bound metadata the server itself sends. Similarly, the inbound limit on the client does not bound request metadata the client sends out. If the server needs to return large response headers, the client must have a suitable receive limit; however, response metadata should still stay small and contain only control data.

A sender can produce metadata larger than the receiver accepts. Therefore, the client SDK should follow the server's contract and validate data before attaching it to Metadata. The receiver remains the final barrier because callers can use other clients or send raw HTTP/2/gRPC requests.

Do not assume a connection limit or message body limit automatically bounds metadata. Message size, metadata size, and HTTP/2 frame/header limits are separate layers.

## 3. Configuring inbound metadata in grpc-java

With the Netty transport, grpc-java builders provide inbound metadata size configuration. Example of limiting request metadata on the server:

~~~java
import io.grpc.Server;
import io.grpc.netty.shaded.io.grpc.netty.NettyServerBuilder;

public final class GrpcServerFactory {

    private static final int MAX_INBOUND_METADATA_BYTES = 16 * 1024;

    public Server createServer(int port) {
        return NettyServerBuilder.forPort(port)
                .maxInboundMetadataSize(MAX_INBOUND_METADATA_BYTES)
                .build();
    }
}
~~~

On the client, limit metadata received from the server:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.netty.shaded.io.grpc.netty.NettyChannelBuilder;

public final class GrpcChannelFactory {

    private static final int MAX_INBOUND_METADATA_BYTES = 16 * 1024;

    public ManagedChannel createChannel(String host, int port) {
        return NettyChannelBuilder.forAddress(host, port)
                .maxInboundMetadataSize(MAX_INBOUND_METADATA_BYTES)
                .build();
    }
}
~~~

The 16 KiB figures are examples only, not universal defaults or recommendations for every system. Choose the threshold based on real headers, token sizes, tracing baggage, interceptor count, and client requirements.

The exact API depends on the grpc-java version and transport. If using a transport other than Netty, check the corresponding builder. Do not copy a property name from another starter without confirming your project's version supports it.

In Spring gRPC, a starter typically manages the server/channel lifecycle. Apply the limit through a builder customizer/configurer or extension point supported by your starter version. Do not create a second server just to set the limit. Write a Spring application integration test to confirm the builder actually used by Spring received the expected value.

Do not rely on library defaults as part of a long-term contract. Set explicit values and document metadata limits in client/server specifications.

## 4. Metadata size is not message size or HTTP/2 frame size

gRPC metadata maps onto HTTP/2 headers and trailers. HTTP/2 uses HPACK to compress header blocks; the transport can split a header block into multiple frames. Therefore, do not equate:

- **Metadata size:** size of the key/value list as calculated by gRPC/transport.
- **Compressed header bytes:** actual bytes after HPACK on the wire.
- **HTTP/2 frame size:** size of an individual transport frame.
- **gRPC message size:** size of the protobuf message body.
- **Total RPC bytes:** total data of the entire call or stream.

grpc-java's metadata limit is enforced according to builder/transport semantics; do not infer it from HPACK byte counts on the network. Overhead accounting and binary metadata calculation may depend on implementation/version. Test on the actual running transport.

Metadata is typically sent when a call starts, while subsequent streaming messages travel in the message body. Sending more protobuf messages does not increase the call's metadata headers; nevertheless, total stream volume still requires separate message/byte quotas.

## 5. Key and value rules in grpc-java

Metadata keys are lowercase ASCII names. Keys for binary values must end with the **-bin** suffix. Keys with the **grpc-** prefix are reserved for the protocol; applications must not define custom transport-reserved keys.

Example of creating keys:

~~~java
import io.grpc.Metadata;

public final class AppMetadataKeys {

    public static final Metadata.Key<String> CORRELATION_ID =
            Metadata.Key.of(
                    "x-correlation-id",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Metadata.Key<byte[]> SIGNED_CONTEXT =
            Metadata.Key.of(
                    "x-signed-context-bin",
                    Metadata.BINARY_BYTE_MARSHALLER);

    private AppMetadataKeys() {}
}
~~~

Use the ASCII marshaller for text values per metadata rules; use the binary marshaller for bytes. Do not manually Base64-encode a value and attach it to a text key when the API can use binary metadata, unless an external contract specifically requires a text representation.

Metadata can contain multiple values for the same key. If the application allows only one correlation ID or one authorization credential, check for duplicate keys and reject ambiguous cases. Never assume every key appears at most once.

Do not create custom keys starting with grpc-. Do not use uppercase letters in metadata keys. Do not use metadata keys to simulate method names or override transport information already present in the server-side call descriptor.

## 6. Limiting entry counts and individual value lengths

The inbound metadata size limit is a total barrier at the transport. The application still needs an allowlist of accepted keys and per-value limits.

Example validation for correlation ID:

~~~java
private static final int MAX_CORRELATION_ID_LENGTH = 128;

static String validateCorrelationId(String value) {
    if (value == null || value.isBlank()) {
        throw new IllegalArgumentException("Correlation ID is required");
    }

    if (value.length() > MAX_CORRELATION_ID_LENGTH) {
        throw new IllegalArgumentException("Correlation ID is too long");
    }

    if (!value.matches("[A-Za-z0-9._-]+")) {
        throw new IllegalArgumentException("Correlation ID has invalid characters");
    }

    return value;
}
~~~

A metadata policy should define:

- Allowlist of keys per service/method.
- Maximum length of each text value.
- Maximum size of binary values.
- Maximum occurrences for repeatable keys.
- Total entry count for application metadata.
- Rules for handling unknown keys or duplicate keys.
- Which data is permitted to be forwarded downstream.

Do not check only total bytes. A metadata block can be below the total limit yet contain many tiny entries that add parsing and logging cost. Conversely, a single binary value can consume most of the budget. Combine total limits with per-key limits and entry counts.

Avoid logging full Metadata. Tokens, signed contexts, and binary values can contain sensitive data. Log allowed keys, sizes, and sanitized correlation IDs; never log credentials.

## 7. Authentication and tracing are no excuse for unbounded metadata

Metadata often carries bearer tokens, mTLS-related context, traceparent, baggage, or correlation IDs. These values are useful, yet they must be bounded.

For authentication:

- Accept only credentials per contract, e.g., a single authorization value.
- Bound token length before calling the verifier if the application receives metadata.
- Do not forward tokens to services that do not need to verify them.
- Do not put access tokens or full claims into response headers.
- If tokens grow large due to many claims, consider token references or minimal claim design.

For tracing:

- Limit the number of baggage entries and the length of each value.
- Propagate only necessary fields.
- Do not put user IDs, emails, or personal data into baggage unless necessary.
- Avoid turning trace baggage into a transport for objects or long lists.

Metadata arriving at the server is received by the transport before application interceptors can inspect individual keys. Therefore, application validation does not replace the inbound transport limit. Transport limits block oversized header blocks; application policy controls content once metadata is accepted.

## 8. Sending metadata on the client and checking before attaching

Clients can populate metadata via interceptors or per-call headers. Centralize header creation to control entry counts and value lengths before sending.

Example client interceptor:

~~~java
public final class CorrelationClientInterceptor
        implements ClientInterceptor {

    private final Supplier<String> correlationIdSupplier;

    public CorrelationClientInterceptor(
            Supplier<String> correlationIdSupplier) {
        this.correlationIdSupplier = correlationIdSupplier;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        ClientCall<ReqT, RespT> call =
                next.newCall(method, callOptions);

        return new ForwardingClientCall
                .SimpleForwardingClientCall<ReqT, RespT>(call) {

            @Override
            public void start(
                    Listener<RespT> responseListener,
                    Metadata headers) {

                String id = validateCorrelationId(
                        correlationIdSupplier.get());

                headers.put(AppMetadataKeys.CORRELATION_ID, id);
                super.start(responseListener, headers);
            }
        };
    }
}
~~~

This example only adds a correlation ID. If multiple interceptors attach metadata, a shared policy is needed to prevent duplicates or budget overruns. Do not allocate a huge metadata object per call and do not copy all HTTP request headers into gRPC.

If outbound metadata exceeds the server's receive limit, the server may reject the call before the handler runs. Client-side checks help catch errors early, but do not replace server receive limits.

## 9. Server response headers and trailers must also stay small

The server can send initial metadata before the first response and trailing metadata when the call finishes. Use them for small control details such as version, request correlation, or reason codes published in the contract.

Do not put full validation error lists, record lists, stack traces, or business payloads into trailers. Large data belongs in protobuf response messages or a suitable API.

For server response metadata, the client is the receiver. The client inbound metadata limit must accommodate valid headers/trailers. However, do not raise the client limit indefinitely to accept abnormal responses. The server should also check key/value counts and emit only permitted metadata.

With streaming RPCs, initial metadata is usually sent once at the start of the call; trailers are sent at the terminal event. Do not attach metadata headers per message. If each event must carry its own cursor, sequence, or status, place them in the protobuf message schema.

## 10. Metadata in streaming RPCs

A streaming call can last a long time and carry many messages, yet the call's metadata has its own lifecycle:

- Request metadata is sent when the client opens the RPC.
- Server can send initial response metadata before or when responses begin.
- Message stream carries data in protobuf bodies.
- Trailers end the call and can carry final status details/metadata.

Therefore, a metadata limit does not replace message-size limits, message-count limits, total stream bytes, or deadlines. A stream can open with tiny headers yet transmit millions of messages; separate resource limits are required.

For long-lived streams, do not put large session state into metadata. Send only credentials, trace context, and small verified selectors. Stream state should live in application objects or storage with clear quotas/lifecycles.

## 11. Handling metadata limit exceedance

When inbound metadata exceeds the transport limit, the gRPC runtime usually rejects the call before the service handler runs. A common status is **RESOURCE_EXHAUSTED**, though exact status/description and detection point depend on the grpc-java version and transport.

Distinguish:

| Scenario | Typical outcome | Handling |
| --- | --- | --- |
| Total inbound metadata exceeds transport limit | RESOURCE_EXHAUSTED | Reduce headers or adjust receive limit in a controlled way |
| A key/value violates application policy | INVALID_ARGUMENT or contract status | Reject the specific key/value |
| Disallowed key present | INVALID_ARGUMENT or PERMISSION_DENIED depending on meaning | Enforce allowlist |
| Caller missing credentials | UNAUTHENTICATED | Provide valid credentials |
| Caller has credentials but lacks permission | PERMISSION_DENIED | Grant appropriate permission |
| Response metadata exceeds client receive limit | Client rejects response | Reduce server-returned metadata or align contract |

Do not rely on specific status descriptions to drive client logic; use status codes and stable reason codes if provided by the API. Do not retry the exact same oversized metadata block because retrying does not shrink headers.

If metadata contains tokens or baggage, limit-exceeded errors must never dump entire headers into logs. Log only method, status, total size if exposed by the runtime, and safely sanitized correlation IDs.

## 12. Choosing limits by contract and real-world observation

There is no single number suitable for every system. Thresholds depend on token sizes, tracing baggage, interceptor count, key counts, and client compatibility requirements.

When choosing limits:

1. Collect valid header sizes from real clients.
2. Measure p50/p95/p99 and the largest valid token cases.
3. Reserve reasonable headroom for trace context and new metadata.
4. Set consistent server and client limits per direction.
5. Set per-key length and entry-count policies.
6. Test older clients and intermediate gateways/proxies between both sides.
7. Monitor rejection rates after deployment.

Do not raise the limit just because a client is forwarding all cookies or unnecessary HTTP headers. Fix the client to propagate only metadata needed for the RPC.

Useful metrics:

- Inbound metadata rejections by method.
- Metadata size buckets by request/response.
- Rejected entry counts and duplicate keys.
- Metadata-related RESOURCE_EXHAUSTED rate.
- Response trailers nearing the threshold.
- Authentication/tracing latency when metadata is large.

Do not use raw tokens, arbitrary user IDs, or full metadata as metric labels. Avoid logging payloads and credentials.

## 13. Testing metadata boundaries

Tests must check both server inbound and client inbound, while distinguishing transport limits from application policy:

| Scenario | Expected result |
| --- | --- |
| Request metadata smaller than server limit | Server receives and dispatches RPC |
| Request metadata exceeds server limit | Transport rejects; handler does not run |
| Response metadata smaller than client limit | Client receives response |
| Response headers/trailers exceed client limit | Client receive path rejects |
| Valid key but value too long per policy | Application interceptor rejects |
| Duplicate authorization key present | Rejected per policy |
| Key not in allowlist | Rejected or ignored per explicit contract |
| Valid binary metadata | Decoded via binary marshaller |
| Small metadata but large message body | Message-size limit handles independently |
| Streaming with small headers and many messages | Metadata limit does not replace stream quotas |

Use grpc-java in-process or transport integration tests to verify real behavior. If the in-process transport does not accurately model Netty's metadata limit, add tests with a Netty server/channel in the test environment. Do not assume tests that hand-assemble an interceptor chain prove transport receive limits.

Key assertions:

1. Requests exceeding the inbound metadata limit do not enter the handler.
2. Responses exceeding the client receive limit are not accepted by the client.
3. Application per-key validation is distinct from transport-level size rejection.
4. Binary metadata uses the correct marshaller.
5. Duplicate/unknown keys are handled per contract.
6. Message bodies and stream quotas are checked independently.
7. Spring application tests confirm the actual builder customizer configured the expected value.

## 14. Integration in Spring gRPC

In a Spring application, clearly separate three parts:

- **Transport configuration:** inbound metadata limits on server/channel builders.
- **Metadata policy:** key allowlists, per-key lengths, duplicate handling, and validation.
- **Interceptor wiring:** authentication, tracing, and application metadata policy.

Register interceptors using the extension point of the Spring gRPC starter in use. Verify the order: transport has accepted headers within the receive limit; authentication reads credentials; metadata policy validates application keys; authorization decides permissions; handler runs last.

Do not let every service invent its own set of keys and policies. Place shared Metadata.Key definitions in one class, using consistent naming conventions and per-method/service policies. If there is a gateway or proxy, check header limits at each hop because requests can be rejected before reaching the gRPC server.

A Spring application integration test should start the real Spring context, send request metadata near and above the threshold, and verify handler invocation, status, and logs/metrics. In-process tests add fast coverage for interceptor logic, while transport tests verify real limits.

## 15. Common implementation pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Confusing metadata with protobuf body | Only configuring message-size limit | Configure metadata receive limit separately |
| Thinking server inbound limit bounds response headers | Client still receives oversized response metadata | Configure client inbound metadata limit |
| Limiting only total bytes | A key repeats too many times or invalid values slip in | Add entry-count and per-key policies |
| Forwarding all HTTP headers | Large tokens/cookies/baggage and data exposure | Allowlist required metadata |
| Using arbitrary grpc- keys | Conflicts with transport-reserved fields | Use application-namespaced keys |
| Using ASCII marshaller for binary values | Wrong decoding or corrupted data | Use binary keys with -bin suffix |
| Logging full metadata | Leaks credentials and personal data | Redact, log safe sizes and keys |
| Raising limits to fix clients sending extra headers | Increases DoS surface | Fix client, propagate only needed fields |
| Testing only application interceptors | Misses transport receive limits | Add Netty transport integration tests |
| Assuming trailers need no control | Client may reject final response | Check both response headers and trailers |

## 16. Hands-on exercises and self-check questions

### Hands-on exercises

1. Configure inbound metadata limits for Netty server and client using the builder appropriate for your version.
2. Create a text key for correlation ID and a binary key for signed context.
3. Write a validator limiting length, entry count, duplicate keys, and allowlist.
4. Create a client interceptor attaching only a validated correlation ID.
5. Create a server interceptor checking application metadata after transport accepts headers.
6. Test server response initial metadata and trailers, checking client inbound limits.
7. Write tests with request headers below, near, and above the threshold; verify the handler does not run when transport rejects.
8. Start the Spring application context to verify builder configuration and real interceptor wiring.

### Self-check questions

**1. How does metadata differ from the protobuf message body?**  
Metadata consists of key/value pairs in RPC headers/trailers; the protobuf message body carries request/response data.

**2. Which direction does the server inbound metadata limit protect?**  
It protects the server when receiving request metadata from clients.

**3. Who limits response metadata sent back by the server?**  
The client is the receiver and needs its own inbound metadata limit.

**4. Does a metadata limit replace a message-size limit?**  
No. The two limits protect different parts of an RPC.

**5. What format must binary metadata keys have?**  
The key name ends with the -bin suffix and uses a binary marshaller.

**6. Why is per-key validation needed when a total metadata limit already exists?**  
To control overly long values, duplicate keys, and abnormal entry counts within the total budget.

**7. Is streaming RPC metadata re-sent with every message?**  
No. Metadata belongs to the call lifecycle; subsequent messages travel in the protobuf body.

**8. Which status commonly appears when inbound metadata exceeds the transport limit?**  
Usually RESOURCE_EXHAUSTED; exact details depend on transport/version.

## Summary

Metadata limits protect gRPC headers and trailers, separate from protobuf message body limits. The server inbound limit controls request metadata received from clients; the client inbound limit controls response metadata received from servers. Combine transport limits with key allowlists, value limits, entry counts, and duplicate handling. Use metadata for credentials, traces, and small correlations; do not forward all HTTP headers or put business payloads into headers. Test requests, response headers/trailers, binary metadata, and Spring builder wiring on the actual transport to prove limits are genuinely enforced.
