# A call through a proxy or gateway

## Learning objectives

After this lesson, you can:

- Describe the path of a gRPC RPC from a Spring client, through a proxy/gateway, to the backend and back.
- Distinguish an L4 proxy forwarding TCP from an L7 proxy that understands HTTP/2 and routes by gRPC method.
- Recognize gRPC's requirements on HTTP/2: pseudo-headers, path, content type, message framing, and trailers.
- Explain TLS passthrough, TLS termination, and re-encryption between gateway and backend.
- Configure a basic gRPC route through Envoy and connect from a Spring client.
- Coordinate deadlines, timeouts, streaming, metadata, health, retries, and graceful draining across multiple hops.
- Diagnose errors originating at the gateway rather than mistaking them for server business errors.

## 1. End-to-end path of a gRPC call

In the **SPRING_GRPC** ecosystem, a Spring client calls a service via a generated stub. In deployed environments, the client rarely connects directly to a single instance; the call passes through a reverse proxy, ingress, API gateway, or service mesh before reaching the gRPC server.

~~~mermaid
sequenceDiagram
    participant App as Spring client
    participant Proxy as Proxy / Gateway
    participant Server as Spring gRPC server
    App->>Proxy: HTTP/2 + gRPC request
    Note over App,Proxy: TLS may terminate at gateway
    Proxy->>Server: HTTP/2 upstream + gRPC request
    Server-->>Proxy: Response DATA + trailers
    Proxy-->>App: Response DATA + trailers
    Note over App,Server: grpc-status ends RPC
~~~

A proxy can perform several tasks along the path:

- Select backends by hostname/authority, gRPC service, and method.
- Load balance, run health checks, and remove unready endpoints.
- Terminate TLS, authenticate at the edge, or open new TLS connections to backends.
- Enforce timeout policies, connection/stream limits, and rate/load throttling.
- Record access logs, traces, and metrics per RPC.
- Enforce network or centralized authentication policies.

Clarify whether the proxy operates at **L4** or **L7**, whether it understands gRPC or only forwards TCP bytes, and how HTTP/2 is used on each hop. Those choices determine whether the gateway can route by method, inspect status, or forward trailers.

## 2. How is a gRPC request structured on HTTP/2?

A gRPC method is normally transmitted as an HTTP/2 POST. Example:

~~~text
:method: POST
:scheme: https
:authority: orders.example.com
:path: /demo.orders.v1.OrderService/GetOrder
content-type: application/grpc
te: trailers
grpc-timeout: 800m
x-request-id: req-7f3a
~~~

Important fields:

| Component | Role |
| --- | --- |
| **:authority** | Host/service authority of the request; tied to routing and TLS identity |
| **:path** | Full RPC path: /package.Service/Method |
| **content-type** | Usually application/grpc or a supported variant |
| **te: trailers** | Signals to the receiver that the caller supports trailers |
| **grpc-timeout** | Remaining time budget if the client set a deadline |
| **custom metadata** | Request ID, trace context, or permitted application context |

The body is not plain JSON. Each gRPC message has a 5-byte prefix containing a compression flag and message length, followed by protobuf-serialized bytes. For streaming RPCs, HTTP/2 DATA can carry multiple gRPC messages sequentially.

Responses typically consist of initial headers, one or more DATA messages, and trailing HEADERS. Trailers carry **grpc-status**; code 0 is OK. HTTP status 200 does not guarantee the RPC succeeded.

~~~text
Response:
  HEADERS: :status=200, content-type=application/grpc
  DATA:    [gRPC message prefix][protobuf response]
  HEADERS (trailers, END_STREAM):
           grpc-status: 0
~~~

An L7 proxy must properly handle HTTP/2 and gRPC framing while preserving trailer semantics. If a proxy only checks HTTP status or strips trailers, the client can lose the real RPC status.

## 3. How do L4 proxies and L7 gateways differ?

| Characteristic | L4 proxy / TCP load balancer | gRPC-aware L7 proxy |
| --- | --- | --- |
| Operating layer | TCP/transport | HTTP/2 and HTTP semantics |
| Route by gRPC method | No | Possible, based on :path |
| Read custom metadata | Cannot inspect HTTP/2 internals | Can read/allowlist metadata |
| Observe grpc-status/trailers | Cannot parse when purely passing through | Can record if gRPC is supported |
| TLS termination | Passthrough or terminate per config | Usually terminates to process HTTP/2; can re-encrypt upstream |
| Best suited for | Forwarding connections, preserving end-to-end TLS | RPC-level routing, policy, auth, observability |

An L4 proxy can distribute TCP connections across backends, yet gRPC typically multiplexes many RPCs onto one long-lived HTTP/2 connection. Hence a connection routed to backend A may carry many RPCs to A for the life of that connection. L4 load balancing does not equate to per-RPC balancing.

An L7 proxy can route by hostname and path, but must support HTTP/2 on both the client and upstream sides. A gateway that only supports HTTP/1.1 upstream will not automatically become a valid gRPC proxy merely because it accepts HTTP requests.

**gRPC-Web is a separate case.** Browsers usually do not open native gRPC HTTP/2 streams the way Java clients do; they use gRPC-Web and require a proxy/translator to convert traffic. Do not confuse gRPC-Web with transparently downgrading native gRPC to HTTP/1.1.

## 4. Two HTTP/2 hops and routing

When an L7 gateway terminates client-side connections, there are usually two independent hops:

~~~text
Spring client
  -- HTTP/2 over TLS -->
Gateway / Envoy
  -- HTTP/2 over TLS or h2c -->
Spring gRPC server
~~~

The gateway reads authority and path, then selects a cluster/backend. Example route by service prefix:

~~~text
/demo.orders.v1.OrderService/
    -> cluster: orders_grpc
        -> orders-1.internal:8443
        -> orders-2.internal:8443
~~~

Route by **published service/method** rather than overly broad wildcards. Configuration must keep an authority and TLS server name matching the upstream certificate. If the gateway rewrites authority for internal routing, distinguish the value used for routing from the value used for TLS identity verification.

For native gRPC, the upstream cluster must negotiate HTTP/2. A proxy can terminate TLS on its listener and open a new TLS connection to the backend, or use upstream cleartext HTTP/2 (h2c) inside a controlled internal network. Choosing `h2c` must stay within a trusted network boundary and should not be the default over untrusted networks.

## 5. Envoy configuration example for a gRPC route

The trimmed configuration below illustrates an HTTP/2 listener, a route by service path, and an HTTP/2-enabled upstream cluster. This is the routing skeleton; production needs listener TLS/certificates, access logs, health checks, limits, and deployment policies.

~~~yaml
static_resources:
  listeners:
    - name: grpc_listener
      address:
        socket_address:
          address: 0.0.0.0
          port_value: 8443
      filter_chains:
        - filters:
            - name: envoy.filters.network.http_connection_manager
              typed_config:
                "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
                stat_prefix: grpc_ingress
                codec_type: AUTO
                route_config:
                  name: grpc_routes
                  virtual_hosts:
                    - name: orders
                      domains: ["orders.example.com"]
                      routes:
                        - match:
                            prefix: "/demo.orders.v1.OrderService/"
                          route:
                            cluster: orders_grpc
                            timeout: 0s
                http_filters:
                  - name: envoy.filters.http.router
                    typed_config:
                      "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router

  clusters:
    - name: orders_grpc
      type: STRICT_DNS
      connect_timeout: 1s
      load_assignment:
        cluster_name: orders_grpc
        endpoints:
          - lb_endpoints:
              - endpoint:
                  address:
                    socket_address:
                      address: orders.internal
                      port_value: 8443
      typed_extension_protocol_options:
        envoy.extensions.upstreams.http.v3.HttpProtocolOptions:
          "@type": type.googleapis.com/envoy.extensions.upstreams.http.v3.HttpProtocolOptions
          explicit_http_config:
            http2_protocol_options: {}
~~~

In this example, **timeout: 0s** disables Envoy's overall route timeout for this route; it does not mean the application should omit deadlines. The client still needs per-RPC **gRPC deadlines**, and the gateway/server need separate resource, stream-duration, or idle limits by policy. For streaming, avoid applying a short blanket timeout that severs legitimate streams mid-flight.

**codec_type: AUTO** lets the HTTP connection manager detect the negotiated protocol; a real TLS listener config needs ALPN `h2` for native gRPC over TLS. Upstream **http2_protocol_options** ensures Envoy speaks HTTP/2 to backends. Verify exact syntax against your deployed Envoy version, as config APIs can vary across versions.

## 6. Connecting from a Spring client through a gateway

The Spring client only needs the gateway target if the gateway is a stable entry point. grpc-java example:

~~~java
package dev.example.orders.client;

import dev.example.orders.v1.OrderServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderGrpcClientConfig {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel orderChannel() {
        return ManagedChannelBuilder
                .forTarget("dns:///orders.example.com:8443")
                .useTransportSecurity()
                .build();
    }

    @Bean
    OrderServiceGrpc.OrderServiceBlockingStub orderStub(
            ManagedChannel orderChannel) {
        return OrderServiceGrpc.newBlockingStub(orderChannel);
    }
}
~~~

The service uses the injected stub and sets a deadline per RPC:

~~~java
GetOrderResponse response = orderStub
        .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
        .getOrder(
                GetOrderRequest.newBuilder()
                        .setOrderId("order-42")
                        .build());
~~~

In production, the Channel must trust the gateway's certificate and verify hostname/authority against the certificate. If the gateway uses mTLS to the backend, upstream certificates are configured on the gateway; the client does not automatically authenticate backends directly once TLS terminates at the gateway.

Do not create a Channel per request. Reusing the Channel keeps resolver/transport state stable, reduces handshakes, and leverages HTTP/2 multiplexing.

## 7. TLS passthrough, termination, and re-encryption

There are three common models:

~~~text
A. TLS passthrough
Client == TLS end-to-end == Gateway L4 == TLS == Server

B. TLS termination
Client == TLS ==> Gateway -- h2c/internal network --> Server

C. TLS termination + re-encryption
Client == TLS ==> Gateway == TLS/mTLS ==> Server
~~~

| Model | What does the gateway see? | When suitable |
| --- | --- | --- |
| **Passthrough** | Does not decrypt HTTP/2/gRPC payload | Want end-to-end TLS and only need TCP/SNI forwarding |
| **Termination** | HTTP/2 headers, path, and metadata after decryption | Need L7 routing, auth, policy, or edge observability |
| **Re-encryption** | Reads request at gateway; re-encrypts upstream hop | Need L7 features plus TLS/mTLS protection for internal traffic |

With passthrough, the gateway cannot route by gRPC method or read `grpc-status` because the TLS payload stays encrypted. With termination, the gateway becomes a trust boundary: it must protect private keys, restrict metadata inspection and logging, and verify upstream certificates when re-encrypting.

TLS termination does not mean backends are automatically trusted. If the gateway calls backends over `h2c`, internal network protection, network policies, and backend access controls must still be designed explicitly. For systems requiring workload identity between services, upstream mTLS is a common choice.

## 8. Deadlines, timeouts, and streaming through a gateway

An RPC crosses multiple hops:

~~~text
Client deadline: 1200 ms
   |
   +-- Gateway routing/queue/connect: 100 ms
   |
   +-- Upstream server processing: 850 ms
   |
   +-- Response via gateway to client: 100 ms
       Example total: 1050 ms
~~~

The client deadline is the total budget. The gateway may apply a route timeout, upstream connect timeout, idle timeout, or max stream duration; these are distinct limits that must be coordinated with the gRPC deadline.

- **Client deadline**: bounds how long the caller waits for the RPC result.
- **Gateway route timeout**: limits route/request duration at the proxy; defaults may not suit streaming.
- **Connect timeout**: limits time spent establishing an upstream connection.
- **Idle timeout**: limits how long a stream can sit without activity.
- **Max stream duration**: caps total stream lifetime, if configured.

Do not accidentally set a gateway timeout shorter than client deadlines; clients may get proxy errors before the server finishes. Conversely, unbounded routes must not mean unbounded resources: bound concurrent streams, idle streams, and maximum duration per use case.

For server streaming or bidirectional streaming, the proxy must keep the stream open and forward DATA/trailers in order. Timeout/idle policies tuned for short REST requests can sever valid gRPC streams. If long streams need heartbeats, coordinate keepalive/ping policies across client, server, and proxy; HTTP/2 PING does not replace business messages or deadlines.

## 9. Metadata, trailers, and status through a gateway

An L7 gateway can read or add metadata, but should use an allowlist for necessary keys:

- Allow standardized trace context and request IDs.
- Forward authorization metadata to backends only when the architecture requires it and trust boundaries are controlled.
- Never log tokens, cookies, or personal data in access logs.
- Never manually overwrite reserved fields such as **grpc-status**, **grpc-message**, and **grpc-timeout**.
- Preserve needed custom trailers when supported by gateway/policy; test both error and success paths.

When the server returns HTTP/2 trailers with **grpc-status: 5** (NOT_FOUND), the gateway must forward that status to the client. If the gateway turns it into an HTTP 404 without producing a valid gRPC response, a native gRPC client may report **UNKNOWN** or a protocol error instead of NOT_FOUND.

Likewise, errors originating at the gateway itself have no protobuf response from a backend. The gateway must emit a valid gRPC response with status/trailers if native gRPC clients are to receive meaningful error codes. Verify the exact behavior of your gateway and version, especially for upstream resets, route timeouts, and connection failures.

## 10. Retries and health routing at the gateway

A gateway may configure retry policies for certain upstream errors, yet proxy retries carry the same business risks as client retries. If the backend already committed a write before a connection reset, a proxy retry can cause duplicate side effects.

- Retry only methods with safe semantics or an idempotency key.
- Cap attempt count and total retry time within the deadline.
- Use proper backoff/jitter to prevent retry storms.
- Never retry a streaming RPC that has already sent or received partial messages as if it were a fresh unary request.
- Record attempt count and final backend for troubleshooting.

Gateway health checking also differs from gRPC client connectivity. The gateway needs to know which endpoints are eligible for traffic, using health endpoints, the gRPC health protocol, or an appropriate discovery mechanism. An open TCP port alone does not prove the application is SERVING.

When deploying new versions, both gateway and backend need **connection draining**. Backends should stop accepting new RPCs, let active RPCs finish within a limit, and then close connections. In HTTP/2, GOAWAY helps notify peers not to open new streams on that connection; clients and gateways must still handle active RPCs and reconnect per policy.

## 11. Observability and hop-by-hop diagnostics

A request through a gateway can fail at the client, gateway, upstream connection, or server handler. Correlate logs/traces using request IDs or trace context and measure each hop:

| Symptom | Where to check first |
| --- | --- |
| Client cannot connect to gateway | DNS, TCP, TLS, ALPN h2, certificate/authority |
| Gateway returns error before upstream | Route match, authority, listener/filters, auth policy |
| Gateway cannot connect to backend | Cluster endpoints, upstream TLS/HTTP2, connect timeout |
| Client receives UNKNOWN instead of business status | Whether gateway preserves trailers and `grpc-status` |
| Unary RPC times out | Client deadline, route timeout, upstream latency |
| Streaming RPC drops after fixed duration | Idle timeout, max stream duration, proxy drain |
| Metadata missing at backend | Header allowlist, normalization, proxy policy |
| Traffic concentrates on one backend | L4 connection balancing, HTTP/2 reuse, L7 LB policy |
| Errors appear only after deploys | GOAWAY, connection draining, endpoint discovery, version compatibility |

Useful metrics include request count by full method name, status code, upstream cluster, per-hop latency, active streams, connection errors, retries, and timeouts. Avoid using request IDs, user IDs, or tokens as metric labels due to cardinality and data-exposure risks.

## 12. Testing a call through a gateway

Tests should traverse the real deployed network path rather than only calling handlers directly:

1. **Routing:** call valid methods and verify the intended cluster/backend receives requests; test wrong paths/authorities.
2. **HTTP/2:** confirm ALPN `h2` on the TLS listener and HTTP/2 upstream to the server.
3. **TLS:** test valid certificates, wrong hostnames, invalid trust chains, and upstream mTLS if used.
4. **Trailers:** trigger NOT_FOUND/INVALID_ARGUMENT and confirm the client receives the exact `grpc-status` and permitted custom trailers.
5. **Deadlines:** set a deadline shorter than processing time; identify which hop terminates the RPC and which status the client observes.
6. **Streaming:** send many messages over an extended period; test idle timeouts, flow control, and end-of-stream trailers.
7. **Failure/draining:** stop a backend or deploy a new version; observe upstream resets, GOAWAY, reconnection, and active RPCs.
8. **Security/logging:** verify authorization is scoped properly and tokens do not appear in access logs.

**grpcurl** can assist with inspecting gRPC endpoints when the server enables reflection or the caller provides proto descriptors. However, a single successful `grpcurl` call does not replace tests for concurrency, long-lived streaming, retries, and connection draining.

## 13. Hands-on lab and self-check questions

### Hands-on lab

1. Run a Spring gRPC server with **GetOrder** and a Spring client calling through a gateway hostname.
2. Configure an Envoy HTTP/2 listener and a route matching prefix `/demo.orders.v1.OrderService/` to the backend cluster.
3. Inspect the request path, authority, and trailers with a gRPC client; trigger a NOT_FOUND error to confirm `grpc-status` is forwarded.
4. Configure TLS termination at the gateway and TLS/mTLS to the backend; verify hostname/SAN and trust chains.
5. Test an 800 ms client deadline against a slow backend; observe route timeouts and client-side status.
6. Open a server-streaming RPC, tune idle/max stream policies, and verify streams are not cut prematurely.
7. Stop a backend under traffic; verify health routing, connection draining, and that retries apply only to safe operations.
8. Set up trace/log correlation across client, gateway, and server; confirm tokens and sensitive data are redacted.

### Self-check questions

**1. Can an L4 proxy route by gRPC method?**  
Not if it only forwards TCP. Path-based routing requires an L7 proxy that understands HTTP/2 after TLS decryption.

**2. Why must an L7 gateway support HTTP/2 upstream?**  
Native gRPC uses HTTP/2 on every hop. If upstream is plain HTTP/1.1, gRPC framing and trailers are not preserved properly.

**3. Does TLS passthrough let the gateway read metadata and grpc-status?**  
No. The TLS payload stays encrypted; the gateway only forwards transport/SNI per configuration.

**4. Does TLS termination protect the hop from gateway to backend?**  
Not automatically. It requires upstream TLS/mTLS or a controlled trusted network boundary.

**5. Why doesn't HTTP 200 guarantee gRPC success?**  
The RPC status sits in `grpc-status` inside trailers. Clients must receive and process trailers properly.

**6. Can you apply short REST timeouts to every gRPC stream?**  
No. Streaming needs appropriate idle/max duration policies; client deadlines and proxy timeouts must be coordinated.

**7. Is it safe for a gateway to retry a write RPC?**  
Only when method semantics allow it or idempotency protection exists. A connection reset does not prove the backend did not execute the operation.

**8. When should you test through a real gateway?**  
Whenever verifying routing, TLS/ALPN, upstream HTTP/2, trailers, streaming, timeouts, retries, and draining. In-process tests cannot verify these network behaviors.

## Summary

A gRPC call through a proxy/gateway traverses distinct HTTP/2 hops, with authority/path-based routing, TLS transport, and stream lifecycles. L4 proxies mainly forward connections; L7 gateways can inspect gRPC methods, metadata, status, and trailers, provided they support HTTP/2 on both client and upstream sides. In Spring gRPC, clients typically reuse a ManagedChannel pointing to the gateway, set per-RPC deadlines, and verify TLS identity. Gateways must preserve gRPC semantics, coordinate timeouts/streaming/health/retries, protect metadata, and support connection draining. End-to-end testing through a real gateway is the way to confirm all hops work together properly.
