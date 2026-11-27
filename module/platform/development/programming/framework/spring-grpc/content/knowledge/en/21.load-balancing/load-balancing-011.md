# Load balancing via proxy

## 1. A proxy sits between the client and multiple backends

In **SPRING_GRPC**, clients call services using gRPC Java, with stubs generated from Protocol Buffers contracts and usually running inside a Spring application. When a proxy sits in the middle, the client connects to a stable proxy address; the proxy accepts connections or individual RPCs and picks a downstream server instance.

~~~text
Spring gRPC client
       |
       | HTTP/2 + gRPC
       v
  Proxy / Envoy
       |
       +----> Orders instance A
       +----> Orders instance B
       +----> Orders instance C
~~~

The proxy can perform load balancing, health checking, retries, timeouts, TLS termination, metadata-based routing, and traffic observability. The client does not need to know individual replica addresses if the proxy owns discovery and backend selection.

Two selection layers can coexist:

1. Client-side load balancing picks one proxy endpoint when multiple proxies exist.
2. Proxy-side load balancing picks a backend server instance behind it.

Clearly define what each layer is load-balancing to avoid duplicate configuration or nested retries.

## 2. Distinguishing an L4 proxy from an L7 gRPC-aware proxy

The most important distinction is whether the proxy operates at the TCP connection layer or the HTTP/2/gRPC protocol layer:

| Characteristic | L4 TCP proxy | L7 gRPC-aware proxy |
|---|---|---|
| Visibility | TCP connections and network addresses | HTTP/2 streams, `:path`, headers/metadata, trailers |
| Typical backend-selection unit | TCP connection | Individual HTTP/2 stream/RPC |
| Reads gRPC method | No | Yes |
| Routes by metadata | Impossible with plain TCP passthrough | Possible if proxy is configured |
| TLS passthrough | Can forward encrypted bytes | Must terminate TLS at proxy to inspect RPCs |
| Behavior with HTTP/2 multiplexing | Many RPCs on one connection usually hit the same backend | Can route different streams to different backends |

gRPC multiplexes many RPCs over one HTTP/2 connection. Hence, an L4 proxy picks a backend when the TCP connection is established; every stream on that connection generally goes to that chosen backend. If a client holds a long-lived channel, many RPCs can concentrate on one backend even when the proxy uses round robin per **connection**.

An L7 proxy understands HTTP/2 and can pick backends per RPC. For instance, the same client-to-proxy connection can send `GetOrder` to A and `WatchOrder` to B if routes and policies permit. This is why connection-level load balancing must be distinguished from RPC-level load balancing.

## 3. Path of an RPC through an L7 proxy

A gRPC-aware proxy typically terminates the client-side HTTP/2 connection, inspects request headers, selects an upstream cluster/endpoint, and opens or reuses an HTTP/2 connection to the backend:

~~~mermaid
sequenceDiagram
    participant C as Spring gRPC client
    participant P as L7 proxy
    participant L as Upstream load balancer
    participant B as Backend instance
    C->>P: HTTP/2 stream /orders.v1.OrdersService/GetOrder
    P->>P: Read authority, path, metadata
    P->>L: Select endpoint in orders cluster
    L->>B: Forward stream over HTTP/2
    B-->>P: Message + gRPC trailers
    P-->>C: Message + grpc-status
~~~

The proxy must support gRPC/HTTP/2 properly. It needs to preserve stream semantics, flow control, headers, and trailers containing `grpc-status`/`grpc-message`. If a proxy downgrades upstream or downstream to incompatible HTTP/1.1, RPCs can fail even while TCP connections remain open.

gRPC method paths take the form `/package.Service/Method`, such as `/orders.v1.OrdersService/GetOrder`. An L7 proxy can route based on path, authority, metadata, or combinations thereof.

## 4. Example proxy cluster with Envoy

Envoy can act as an L7 proxy for gRPC. The upstream cluster definition must declare endpoints and enable HTTP/2 for backend connections. Example configuration fragment:

~~~yaml
clusters:
  - name: orders
    type: STRICT_DNS
    connect_timeout: 1s
    lb_policy: ROUND_ROBIN
    load_assignment:
      cluster_name: orders
      endpoints:
        - lb_endpoints:
            - endpoint:
                address:
                  socket_address:
                    address: orders-a.internal
                    port_value: 9090
            - endpoint:
                address:
                  socket_address:
                    address: orders-b.internal
                    port_value: 9090
            - endpoint:
                address:
                  socket_address:
                    address: orders-c.internal
                    port_value: 9090
    typed_extension_protocol_options:
      envoy.extensions.upstreams.http.v3.HttpProtocolOptions:
        "@type": type.googleapis.com/envoy.extensions.upstreams.http.v3.HttpProtocolOptions
        explicit_http_config:
          http2_protocol_options: {}
~~~

This is an illustrative cluster fragment, not a complete Envoy configuration file. A listener, HTTP connection manager, and routes must also be configured to accept HTTP/2/gRPC on the client side and forward to cluster `orders`. `STRICT_DNS` instructs Envoy to resolve upstream hostnames; other environments may supply endpoints via EDS/xDS or another discovery mechanism.

`ROUND_ROBIN` distributes upstream selection across eligible endpoints. If weighted clusters, locality routing, outlier detection, or consistent hashing are required, configure the corresponding extensions/policies and verify support in your running Envoy version.

## 5. Spring client only needs to connect to the proxy endpoint

When the proxy exposes a stable hostname, the Spring client can create a channel to that address:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersGrpcClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel ordersChannel() {
        return ManagedChannelBuilder
                .forTarget("dns:///orders-proxy.internal:443")
                .useTransportSecurity()
                .build();
    }
}
~~~

Stubs are created from the shared channel:

~~~java
import com.example.orders.rpc.OrdersGrpc;
import io.grpc.ManagedChannel;
import org.springframework.stereotype.Component;

@Component
public class OrdersClient {
    private final OrdersGrpc.OrdersBlockingStub stub;

    public OrdersClient(ManagedChannel ordersChannel) {
        this.stub = OrdersGrpc.newBlockingStub(ordersChannel);
    }
}
~~~

The client does not need to list the IPs of A, B, and C if the proxy manages upstream discovery. If multiple proxy endpoints exist, the channel can use its own resolver and policy to pick a proxy, and the proxy then picks a backend. Do not create a new channel per RPC.

In a service mesh sidecar setup, the target address may be a local proxy port. Clarify whether traffic is intercepted by the sidecar via iptables/transparent proxy or the client connects directly to a sidecar listener; the two models have different TLS and authority configurations.

## 6. Proxy and TLS: passthrough, termination, re-encryption

A proxy needs an explicit TLS model:

| Model | Client → proxy | Proxy → backend | Can proxy inspect RPCs? |
|---|---|---|---|
| TCP/TLS passthrough | End-to-end TLS through proxy | Same TLS stream to server | Cannot read gRPC path/metadata |
| TLS termination | Client TLS ends at proxy | Possibly plaintext on trusted network | Yes, proxy handles HTTP/2/gRPC |
| TLS termination + re-encryption | TLS ends at proxy | Proxy opens fresh TLS to backend | Yes, while also encrypting upstream |

If routing by method or metadata is needed, the proxy must see HTTP/2 headers, so TLS typically terminates at the proxy. With re-encryption, the proxy must verify backend certificates and send the right SNI/authority. Never disable certificate validation to resolve connection errors.

In production environments, consider mTLS on both hops:

- Client authenticates the proxy.
- Proxy authenticates the backend.
- Backend can authenticate the proxy's workload identity if the security model requires it.

gRPC requires HTTP/2. With TLS, ALPN must negotiate `h2`; the proxy must not downgrade upstream or downstream protocols to HTTP/1.1 for native gRPC.

## 7. Health checking and excluding unhealthy backends

Proxies can often combine active health checking and passive outlier detection:

- **Active health check:** the proxy periodically calls a health endpoint/RPC to determine whether a backend can serve.
- **Passive outlier detection:** the proxy observes errors or latency on live traffic and temporarily ejects abnormal backends.
- **Endpoint discovery:** registry/xDS updates advertised instances.
- **Load balancing:** the picker chooses from the remaining eligible endpoints.

Health checks should reflect business serving ability. A successful TCP connect does not prove the database or required dependencies are healthy. With gRPC, you can use `grpc.health.v1.Health/Check` or a compatible health mechanism supported by the proxy.

Avoid running active checks too frequently or hitting heavy dependencies on every check. When a backend flaps between healthy and unhealthy, use appropriate thresholds, stabilization windows, and ejection durations to keep it from entering and leaving the pool continuously.

## 8. Retries, deadlines, and timeouts at the proxy

A proxy can apply retries to eligible requests, but this must be coordinated with retries in the gRPC client and application layer. If all three layers retry multiple times, one logical RPC can generate far more attempts than expected.

Example time budget:

~~~text
Client deadline: 3 seconds
  Proxy route timeout: up to 2.5 seconds
    Upstream attempt A: 0.8 seconds
    Backoff: 0.2 seconds
    Upstream attempt B: remaining time
~~~

Guidelines:

- The client deadline must encompass total time across the proxy and backend.
- Per-try timeouts must be smaller than the logical RPC's remaining budget.
- The proxy must handle `grpc-timeout` and statuses/trailers properly.
- Retry only statuses and methods that are safe to retry.
- For side effects, use idempotency keys to avoid duplicate execution.
- Pick one primary retry layer or explicitly budget total attempts across layers.

`UNAVAILABLE` does not always mean the backend is dead; a well-connected backend can still return this status due to an internal dependency. Retries do not remove a backend from the pool by themselves. Ejection requires health, outlier, or discovery policies.

## 9. Server streaming and proxy timeouts

A server streaming RPC is a long-lived HTTP/2 stream passing through the proxy. The proxy must preserve the stream and flow control for its entire lifetime:

~~~text
Client
  -> Proxy
      -> Backend A
      <- event 1
      <- event 2
      <- event 3
  <- Proxy
<- Client
~~~

Standard HTTP timeouts may be unsuitable for long streams. Consider:

- **Idle timeout:** period of no data before the proxy closes the stream.
- **Maximum stream duration:** cap on total stream lifetime, if configured.
- **Connection drain:** how the proxy handles HTTP/2 connections when upstream or proxy shuts down.
- **Flow control/buffers:** memory limits when consumers read slowly.
- **Keepalive:** dead-connection detection that must be coordinated across client, proxy, and server.

Do not disable all timeouts by default. Pick an idle timeout suited to event cadence while enforcing deadlines or stream lifetime limits at the business layer. If a backend is ejected or stops mid-stream, the proxy cannot move the remainder of that RPC to another backend; the client must reconnect/resume using a cursor or sequence.

## 10. Routing by method, metadata, and version

An L7 proxy can route by gRPC path, authority, or metadata. Examples:

- `/orders.v1.OrdersService/GetOrder` to the stable cluster.
- `/orders.v1.OrdersService/WatchOrder` to a stream-capable cluster.
- Metadata `x-tenant-tier` selects backend pools by tier.
- Metadata `x-canary: true` routes a subset of requests to a canary version.

Metadata only takes effect when the proxy is configured to inspect that field. A gRPC client sending `x-routing-key` does not automatically create sticky routing. The proxy needs a hash/affinity policy or explicit route rule.

Do not use access tokens, emails, or sensitive data as routing keys. A proxy also does not replace authorization: the backend still needs to authenticate callers and verify permissions. If the proxy modifies or strips metadata, align that contract across gateway, client, and backend.

## 11. Graceful shutdown and updating the upstream pool

When a backend is about to stop, the proxy must stop sending new RPCs to that endpoint while giving active RPCs time to complete:

1. Backend reports readiness false or deregisters from the registry.
2. Proxy receives endpoint/health update and removes the backend from new-RPC selection.
3. Backend/proxy drains active connections and streams within the grace period.
4. Remaining RPCs finish or end with a defined status.
5. Clients reconnect/resume streams if supported by the contract.

Deregistering from a registry does not necessarily close existing HTTP/2 connections immediately. The proxy may need to actively drain upstream connections. Likewise, restarting a proxy can impact many streams even when backends are healthy; deploy multiple proxy replicas and drain carefully to minimize disruption.

## 12. Testing proxy load balancing

A test calling one backend through a proxy does not prove the proxy distributes load. You need multiple backends with instance IDs, a real proxy or equivalent fixture, and observation of selection:

| Scenario | What to verify |
|---|---|
| Multiple healthy backends | New RPCs are distributed according to configured policy |
| One unhealthy backend | New RPCs are not sent to the excluded backend |
| L4 proxy with one HTTP/2 connection | Multiple multiplexed RPCs may all hit one backend |
| L7 proxy with multiple streams | RPCs can be routed independently per policy |
| TLS termination/re-encryption | ALPN `h2`, certificates, and authority verified on both hops |
| Metadata routing | Only permitted metadata influences routing |
| Proxy retries | Attempt counts stay within budget and avoid repeating side effects |
| Short deadline | Proxy does not hold RPCs longer than client deadline |
| Long-lived streams | Idle timeout/flow control do not sever valid streams |
| Backend drain | New RPCs shift away; in-flight RPCs follow grace period |
| Proxy restart | Clients reconnect and streams resume if needed |

Verify gRPC trailers/status codes as well, not just HTTP status or TCP connections. In-process gRPC tests do not fully simulate proxy HTTP/2, TLS, routing, and timeouts; those behaviors require integration tests with Envoy or your production proxy.

## 13. Observability and diagnostics

To isolate failures, observe each hop separately:

- Client-to-proxy and proxy-to-backend connection counts.
- RPCs by method, route, cluster, and upstream instance.
- Proxy latency, upstream duration, and queue wait times.
- HTTP status alongside `grpc-status` in trailers.
- Healthy/ejected backend counts and state-change timestamps.
- Retry attempts, timeouts, resets, and connection drains.
- Open stream counts, stream age, and idle timeouts.
- TLS/ALPN errors on client-proxy or proxy-backend hops.

If all RPCs land on one backend, check whether the proxy runs in L4 or L7 mode, whether HTTP/2 upstream is enabled, and whether the policy distributes by connection or stream. If RPCs receive `UNAVAILABLE`, correlate gRPC trailers with proxy and backend logs to find where the failure originated.

## 14. Common implementation mistakes

| Mistake | Consequence | How to fix |
|---|---|---|
| Assuming L4 round robin distributes per RPC | Many streams on one connection hit the same backend | Use an L7 gRPC-aware proxy when per-RPC routing is needed |
| Proxy upstream uses HTTP/1.1 | Native gRPC fails or breaks semantics | Enable upstream HTTP/2 and ALPN `h2` |
| TLS passthrough while expecting metadata routing | Proxy cannot read encrypted headers | Use controlled TLS termination/re-encryption |
| Proxy timeout shorter than stream cadence | Valid streams get closed mid-flight | Configure idle/max duration per stream contract |
| Client and proxy both retry unboundedly | Load amplification, missed deadlines | Coordinate end-to-end retry budgets |
| Checking only TCP health | Backends with broken dependencies still accept RPCs | Use appropriate gRPC health/readiness checks |
| Routing on unvalidated caller-supplied metadata | Can be spoofed to bypass quotas or shift backends | Authenticate, normalize, and restrict routing metadata |
| Draining backends without draining connections | In-flight RPCs/streams reset abruptly | Perform graceful draining and support resume |

**Key takeaway:** A proxy can load balance at the TCP layer or the HTTP/2/gRPC layer. L4 usually picks backends per connection so multiplexed RPCs hit one instance; L7 understands individual streams and can route by method or metadata. Spring clients connect to the proxy endpoint with one shared channel while the proxy manages upstream discovery, health, and policies. Keep HTTP/2, TLS authority, gRPC trailers, deadlines, and stream timeouts accurate, and coordinate retries, draining, and resume end to end.
