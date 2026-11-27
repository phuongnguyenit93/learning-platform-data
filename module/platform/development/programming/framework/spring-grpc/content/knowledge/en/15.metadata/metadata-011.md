# Metadata Lost Across Proxies

When a client sends gRPC metadata but the server never receives it, the cause may lie in a gateway, reverse proxy, load balancer, or protocol-translation layer in between. The client interceptor may have added the header properly, yet that alone does not prove the header reached the server. With Spring gRPC, you must understand that metadata travels inside HTTP/2 headers/trailers, identify which layer the proxy operates at, and inspect each boundary without leaking credentials.

This lesson focuses on diagnosing and resolving metadata that is stripped, renamed, merged, size-limited, or dropped across proxies.

## 1. The Path of Metadata Through a Proxy

In native gRPC, request metadata is represented as HTTP/2 request headers; response metadata resides in initial response headers and trailing headers. A proxy may simply forward the TCP stream or terminate HTTP/2, parse headers, and open a new upstream connection.

```text
gRPC client             Proxy / gateway                    gRPC server
    |                          |                                  |
    |-- HTTP/2 headers ------->|                                  |
    |   x-request-id           |                                  |
    |   authorization          |-- upstream HTTP/2 headers ------>|
    |                          |   x-request-id?                  |
    |                          |   authorization?                 |
    |                          |                                  |
    |-- Protobuf messages ---->|-- HTTP/2 DATA frames ----------->|
    |                          |                                  |
    |<-- response headers -----|<-- response headers -------------|
    |<-- messages -------------|<-- DATA frames ------------------|
    |<-- trailers/status ------|<-- trailers/status --------------|
```

Proxies can alter headers or trailers depending on configuration. Seeing a key in the client interceptor before sending only proves the application prepared the metadata. Only the server interceptor confirms the key actually arrived at the server.

## 2. Distinguishing L4 and L7 Proxies

| Proxy type | How it works | Typical impact on metadata |
| --- | --- | --- |
| L4 TCP pass-through | Forwards TCP connections without parsing HTTP/2 headers | Generally preserves the byte stream; metadata rarely modified directly |
| L4 TLS pass-through | Forwards TLS connection to upstream | Proxy cannot read metadata inside TLS |
| L7 HTTP/2-aware | Terminates HTTP/2, reads headers/trailers, creates upstream request | May apply allowlists, removals, rewrites, size limits, or modify trailers |
| Protocol-translating gateway | Converts gRPC to another protocol or gRPC-Web | May map, filter, or lack full support for custom metadata/trailers |

**Native gRPC requires HTTP/2 on gRPC connection paths.** If a proxy accepts HTTP/2 from the client but connects upstream using plain HTTP/1.1, it is no longer a transparent native gRPC forwarding path. Configure HTTP/2 upstream properly or use a gRPC-Web translation gateway designed for that purpose.

If TLS is terminated at the proxy, verify both hops: client → proxy and proxy → server. A successful TLS handshake on the client side does not prove upstream uses HTTP/2 or preserves metadata.

## 3. Common Reasons Metadata Disappears

### Header Allowlists or Removal Rules

A gateway may forward only headers on an allowlist, or be configured to strip unwanted keys. Custom keys like `x-request-id`, `x-tenant-id`, or `x-client-version` may be dropped if the proxy permits only a specific header set.

Check:

- The list of headers permitted from downstream to upstream.
- Header removal rules by name, prefix, or route.
- Header rewrite/rename rules and their evaluation order.
- Policies specific to gRPC routes, virtual hosts, or individual services.

Never allow forwarding all headers unconditionally. In particular, `authorization`, cookies, and custom credential headers require dedicated security rules.

### HTTP/2 or gRPC Incompatibility

A proxy may receive a request yet forward upstream using a protocol or mode that does not support native gRPC. Check:

- Do both downstream and upstream use HTTP/2 as required by gRPC?
- Does the proxy preserve the `application/grpc` content type and required gRPC control attributes?
- Are attributes such as `te: trailers` and status/trailers handled properly?
- Is any gRPC-Web transcoding or HTTP/JSON transcoding layer involved?

Do not look solely at HTTP success codes from the proxy. A request can reach the gateway while metadata or gRPC trailers fail to reach the service intact.

### Header Size Limits

Total header-list size may be capped at the client, proxy, or server. Adding more metadata can push a request past the threshold and get it rejected before the server interceptor runs. Binary metadata uses Base64 representation on the wire, so its transport size can exceed the original byte length.

Proxy limits and gRPC metadata limits are two distinct configuration layers. Raising Protobuf message limits does not fix header limits; raising header limits is also not the way to send large payloads.

### Key/Value Normalization and Handling

gRPC metadata key names are normalized to lowercase. Proxies may normalize header names, coalesce duplicate header values, or apply their own parsers. Common errors include:

- Client and server using different key names, e.g., `x-request-id` vs. `x-requestid`.
- Binary key missing `-bin` suffix or being processed arbitrarily as text by the proxy.
- Multiple values for a key being merged or only one value retained.
- Custom key starting with `grpc-`, which is reserved for the protocol.
- Value too long or containing characters invalid for ASCII metadata.

Never assume every proxy treats duplicate headers identically. For keys expected to be unique like request ID or tenant selection, mandate a single value and enforce that on the server.

### Lost Response Trailers

Metadata from server to client can be affected independently of request headers. A proxy/gateway might forward initial response headers and messages yet fail to preserve trailers or gRPC status properly. The client may then see unexpected statuses or miss custom trailers.

Check the proxy's gRPC configuration, HTTP/2 trailers support, and how the gateway maps errors. Do not conclude request metadata was lost merely because response trailers are missing; those are two separate directions.

## 4. Diagnosing Boundary by Boundary

Instead of logging entire metadata, check the **presence of an allowlisted set of keys** at each hop:

| Observation point | What to verify | How to collect |
| --- | --- | --- |
| Client before transport | Did the interceptor add the key? | Check `headers.containsKey(...)` inside the client interceptor |
| Proxy receiving request | Did the key reach the listener/downstream? | Access logs or telemetry recording only permitted key names |
| Proxy sending upstream | Was the key removed/rewritten? | Compare upstream request header names against proxy config |
| Server interceptor | Did the key actually reach the gRPC server? | Check `headers.containsKey(...)` or read permitted values |
| Server sending response | Were headers/trailers created? | Observe `sendHeaders(...)` and `close(status, trailers)` |
| Client receiving response | Which callbacks fired, which keys are present? | Inspect `onHeaders(...)` and `onClose(...)` |

### Server-Side Check Example Without Logging Values

An interceptor can record key presence and RPC name without dumping entire `Metadata`:

```java
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class MetadataPresenceInterceptor implements ServerInterceptor {
    private static final Logger log =
        LoggerFactory.getLogger(MetadataPresenceInterceptor.class);

    private static final Metadata.Key<String> REQUEST_ID =
        Metadata.Key.of(
            "x-request-id", Metadata.ASCII_STRING_MARSHALLER);
    private static final Metadata.Key<String> CLIENT_VERSION =
        Metadata.Key.of(
            "x-client-version", Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        log.debug(
            "grpc_metadata_presence method={} request_id={} client_version={}",
            call.getMethodDescriptor().getFullMethodName(),
            headers.containsKey(REQUEST_ID),
            headers.containsKey(CLIENT_VERSION));

        return next.startCall(call, headers);
    }
}
```

This is a diagnostic interceptor, not a replacement for request ID validation or authentication interceptors. Never log values of authorization, cookies, API keys, or entire metadata. If request ID correlation is needed, log only format-validated IDs or trusted system-generated correlation IDs.

### Interpreting Findings

- Client has the key, server lacks the key: inspect proxy, route, upstream protocol, and header sizes.
- Proxy ingress has the key, egress lacks it: focus on allowlists/removals/rewrites and route configuration.
- Server receives request headers, client lacks response trailers: investigate response path, trailer forwarding, and error termination paths.
- Neither proxy nor server sees the key: verify the client interceptor is attached to the stub/channel actually being called.
- Only specific routes fail: compare route config, virtual hosts, gateway policies, and upstream clusters between working and failing routes.

## 5. Fixing by Root Cause

1. **Headers filtered out:** add the exact required custom keys to the route's allowlist; remove inappropriate strip/rewrite rules. Do not open all headers when only two or three keys are needed.
2. **Wrong upstream protocol:** configure the proxy to use HTTP/2 toward the gRPC server; if HTTP/1.1 or browser clients are required, use a gRPC-Web/transcoding gateway with proper support.
3. **Exceeding limits:** reduce metadata count and size, remove redundant values; adjust header limits only on necessary hops while maintaining finite bounds.
4. **Binary metadata mishandled:** use keys with the `-bin` suffix, proper binary marshallers, and verify proxy support. Never Base64-encode a second time yourself.
5. **Duplicate keys altered:** design keys requiring uniqueness, send a single value, and ensure the server rejects or handles duplicates per contract.
6. **Trailers dropped:** enable appropriate gRPC/HTTP/2 modes, verify trailer handling, and test both success and trailers-only error paths.
7. **TLS termination differences:** inspect protocol and TLS per hop; configure proper upstream transport and authenticate proxies/services per trust model.

After updating proxy settings, verify both request metadata and response metadata. A fix that only preserves request headers may still drop trailers.

## 6. Reviewing Proxy Configuration

There is no universal config snippet applicable to every proxy. Directive names and defaults vary across Envoy, NGINX, ingress controllers, service meshes, and cloud load balancers. When reviewing configuration, look for the right setting groups:

| Configuration group | What to confirm |
| --- | --- |
| Listener/downstream protocol | Accepts gRPC over HTTP/2; TLS/ALPN if TLS is enabled |
| Route/virtual host | Routes the gRPC service/method accurately without unsuitable plain-HTTP policies |
| Header mutation | Required custom metadata is not stripped or rewritten |
| Header allowlist | `x-request-id`, `x-client-version`, and application keys are explicitly allowed |
| Upstream cluster | Connects via HTTP/2 to the gRPC server or uses a supported bridge |
| Header size limits | Bounds large enough for valid metadata yet still finite |
| Response handling | Preserves initial headers, trailers, and gRPC status |
| Access logging | Does not record credentials or tokens; logs only allowlisted fields |

For example, if a route policy only allows certain request headers, add custom keys to the forwarded list on **that specific route** instead of altering a global policy for all services. If the proxy supports request/response header removal, verify no overlapping rules exist across listener, route, and upstream.

For service meshes, check both inbound and outbound sidecar configurations. A header may survive the ingress gateway only to be stripped by a service sidecar or egress gateway on a subsequent hop.

## 7. Testing Through a Proxy

In-process gRPC tests are useful for verifying interceptors and `Metadata` in Java, but they bypass proxies, HTTP/2 termination, and header mutations. To verify this class of bug, you need integration tests running through the **same proxy type and production-like configuration**.

| Test case | How to run | Result to verify |
| --- | --- | --- |
| Basic ASCII metadata | Send `x-request-id` through proxy | Server interceptor receives exact key/value |
| Custom header allowlist | Send allowed key and disallowed key | Allowed key reaches server; blocked key follows defined behavior |
| Stripped header | Test a route with a removal rule | Test detects the key fails to reach server |
| Header size boundary | Increase total metadata up to and past test threshold | Error is caught at expected hop; server does not assume partial receipt |
| Binary metadata | Send `-bin` key with `byte[]` | Server receives exact bytes back |
| Duplicate metadata | Send multiple values for same key | Proxy/server behavior matches contract |
| Response headers | Server sends initial metadata | Client receives it in `onHeaders(...)` |
| Response trailers | Server closes call with custom trailer and status | Client receives trailer in `onClose(...)` |
| Error/trailers-only | Server or gateway rejects before message | Client handles status even without initial headers |
| TLS and HTTP/2 upstream | Call via production-like listener and upstream | ALPN/protocol and metadata are preserved accurately |

When testing header limits, never use real tokens or sensitive data as test payloads. Use dummy strings and record only sizes or statuses. Collect evidence from client, proxy ingress/egress, and server to pinpoint the exact hop dropping metadata.

## 8. Incident Investigation Checklist

- [ ] Confirm the client interceptor is attached to the right stub/channel.
- [ ] Record the names of metadata keys to track, without logging secret values.
- [ ] Identify whether the proxy is L4 pass-through, L7 HTTP/2-aware, or protocol-translating gateway.
- [ ] Verify HTTP/2 from client to proxy and from proxy to gRPC server.
- [ ] Inspect header allowlists, removal rules, rewrites, and route scopes.
- [ ] Inspect header size limits at client, proxy, server, and load balancer.
- [ ] Verify ASCII/binary rules, `-bin` suffix, and duplicate keys.
- [ ] Observe the server interceptor to confirm actually received request metadata.
- [ ] If failing on return path, inspect `onHeaders(...)`, `onClose(...)`, trailers, and status.
- [ ] Run integration tests through the proxy after changing configuration.
- [ ] Verify access logs, traces, and debug logs do not record credentials/tokens.

## 9. Practice Exercise

A Spring gRPC client sends `x-tenant-id` and `x-request-id` through an API gateway to `OrderService`. Calling the service directly delivers all metadata; going through the gateway causes `x-tenant-id` to vanish. In some cases, the client also fails to receive the custom response trailer `x-response-request-id`.

**Requirements:**

1. Sketch both the direct path and the gateway path, identifying where to observe header names.
2. Check whether the gateway is L4 or L7, the upstream protocol, and allowlist/removal policies for the gRPC route.
3. Verify `x-tenant-id` is used only after cross-checking against an authenticated principal; never treat header forwarding as proof of permission.
4. Separately inspect response trailers and status on the server → client path.
5. Design an integration test through the gateway covering ASCII metadata, duplicate keys, header size, and trailers.
6. Propose a way to log key presence without logging tokens or entire metadata.

**Self-check questions:**

- Why does a client interceptor seeing metadata not mean the server received it?
- How does an L4 pass-through differ from an L7 HTTP/2 proxy?
- Why is plain HTTP/1.1 upstream not a transparent native gRPC forwarding path?
- How can header allowlists and header removal strip custom metadata?
- How do header limits differ from Protobuf message limits?
- Why must request headers and response trailers be investigated separately?
- What can an in-process test prove, and what can it not prove when the bug lies in a proxy?

**Key takeaway:** When metadata is lost across proxies, identify the proxy type and inspect each hop along client → proxy → server. Focus on HTTP/2/gRPC upstream, allowlists/removals/rewrites, header sizes, binary keys, and trailers. Use integration tests through a real proxy to verify results; log only the presence of permitted keys and never dump credentials or tokens.
