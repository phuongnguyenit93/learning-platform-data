# Choosing gRPC for Low-Latency Internal RPC

## Learning Objectives

After this lesson, you can:

- Identify workloads suited for internal RPC communication with low-latency requirements.
- Explain the benefits and limitations of gRPC, HTTP/2, and Protocol Buffers.
- Compare gRPC with REST/JSON and message brokers by communication characteristics.
- Evaluate the impact of channel reuse, serialization, deadlines, streaming, and load balancing.
- Identify operational prerequisites before choosing gRPC in the Spring ecosystem.
- Make decisions based on percentile latency, throughput, resource cost, and compatibility.

## 1. The Low-Latency Internal Communication Problem

In a microservices architecture, a user request may pass through multiple services: an API gateway calls profile, profile calls permissions, and orders call inventory and payment. Each hop adds network transmission, processing, serialization, queueing, and dependency wait time. When a request has multiple sequential hops, the latency of each RPC accumulates into the final latency.

**SPRING_GRPC** focuses on developing gRPC services in the Spring ecosystem using Protocol Buffers contracts, Java code generation, and client/server implementation for unary or streaming RPCs. Within this scope, choosing gRPC is suitable when internal services need to call each other frequently, payloads have clear structure, stable latency is required, and both sides can use generated client/server contracts.

gRPC does not automatically make every request faster. It provides a suitable transport and serialization for efficient RPC; actual results also depend on connection reuse, message size, server processing, hop count, network topology, TLS, proxies, and resource contention.

## 2. What Does gRPC Provide?

gRPC combines several components:

- **Protocol Buffers** defines services, methods, and messages; from that contract, Java code is generated for client stubs and server base classes.
- **HTTP/2** transports RPCs over a connection capable of multiplexing multiple streams.
- **Unary RPC** sends one request and receives one response, suitable for most short service-to-service calls.
- **Streaming RPC** allows one or both sides to exchange multiple messages on the same call.
- **Metadata** carries contextual information such as authorization, trace ID, and correlation ID.
- **Deadlines and status codes** represent the time budget and call outcome according to the RPC contract.

Protobuf contracts help clients and servers share clear data types, reducing the need to serialize JSON and parse string fields at each hop. Code generation also catches many compatibility errors at build time rather than waiting until runtime.

## 3. Why Is gRPC Often Suited for Low-Latency Internal RPC?

### Binary Serialization

Protobuf encodes messages into a binary wire format, which is often more compact than JSON for the same structured data. Smaller messages can reduce bytes sent over the network and parse/serialize costs. The savings depend on the schema, field types, actual data, and how JSON is compressed.

### HTTP/2 Multiplexing

HTTP/2 allows multiple RPC streams to operate concurrently over a single TCP connection. Clients do not need to open a new connection for each call; a channel can reuse the transport and avoid repeating connection setup costs.

Multiplexing reduces contention caused by creating many connections, but it does not eliminate all head-of-line blocking at the TCP layer. Packet loss on a TCP connection can still affect all streams on that connection. Therefore, you need to measure on the real network topology.

### Contracts and Code Generation

Generated stubs provide a Java API with predefined data types, methods, and request/response structures. This reduces boilerplate, minimizes field-name mistakes, and provides a foundation for controlling API evolution across services.

### Deadlines and Status Codes with RPC Semantics

Clients can set a deadline for a call; servers detect cancellation/deadline to stop work that is no longer useful. Standard status codes help clients distinguish transient errors, authentication errors, validation failures, and business states.

These characteristics are especially useful when a request traverses multiple services and needs consistent latency budget control end-to-end.

## 4. Comparing gRPC, REST/JSON, and Message Brokers

| Criterion | gRPC | REST/JSON | Message broker |
| --- | --- | --- | --- |
| Model | Synchronous or streaming RPC | HTTP request/response | Asynchronous message send/receive |
| Contract | Protobuf service/message | OpenAPI/JSON or equivalent contract | Event/message schema |
| Common serialization | Binary Protobuf | Text JSON | Depends on broker and serializer |
| Connection | HTTP/2, reusable channel | HTTP/1.1 or HTTP/2 depending on stack | Connection to broker |
| Latency | Suited for direct RPC, often fewer bytes/less parsing | Simple and fast enough for many APIs | Adds broker/queue; not the default choice for immediate request-response |
| Streaming | Unary, client/server/bidirectional streaming | Can use SSE/WebSocket or other mechanisms | Event/consumer streams |
| Coupling | Client depends on service contract | Client depends on HTTP API contract | Producer/consumer decoupled in time and often lifecycle |
| Browser | Needs gRPC-Web/proxy or gateway | Supported directly | Usually needs backend or gateway |
| Best fit | Service-to-service RPC with clear schema | Public APIs, broad integration, and convenient debugging | Event-driven workflows, buffering, and background processing |

Do not choose gRPC solely because Protobuf is smaller than JSON. If communication requires a durable queue, independent consumer retries, or temporal decoupling between producer and consumer, a message broker is a better fit. If clients are browsers or third parties needing accessible HTTP, REST can reduce integration cost.

## 5. When Should You Choose gRPC?

gRPC is a strong candidate when most of the following hold:

- Both ends of communication are controlled by the same organization or share a Protobuf contract workflow.
- The workload is direct service-to-service RPC, frequent, and has clear latency/throughput requirements.
- Messages have a stable schema that can be code-generated and versioned.
- Client/server runtimes properly support HTTP/2 and gRPC.
- Unary or streaming semantics, deadlines, cancellation, and structured statuses are needed.
- You can operate TLS, service discovery, load balancing, observability, and debugging for gRPC.

Examples: OrderService needs to check inventory from InventoryService during checkout; ProfileService calls PermissionService to determine access rights; an internal gateway needs to call multiple backends with Protobuf contracts.

## 6. When Should You Choose REST or a Message Broker?

REST/JSON is often more suitable when an API needs to be called directly from a browser, integrates with many external partners, needs discoverability/debugging with common HTTP tools, or evolves its schema independently of clients. REST can also run over HTTP/2; do not assume REST always uses HTTP/1.1 or is always slow.

A message broker is suitable when the producer does not need to wait for the consumer to process immediately, or when buffering, fan-out, replay, consumer groups, or durable background processing are needed. Synchronous gRPC keeps the client waiting for a result and tightly couples the caller's latency to the called dependency.

A system can use all three: REST at the edge, gRPC between internal services, and a broker for asynchronous events/workflows. Choose per interaction rather than forcing the entire system onto a single protocol.

## 7. Defining a Protobuf Contract for Internal RPC

Example of InventoryService providing a unary RPC:

~~~proto
syntax = "proto3";

package acme.inventory.v1;

option java_package = "com.acme.inventory.grpc";
option java_multiple_files = true;

message GetAvailabilityRequest {
  string sku = 1;
  int32 requested_quantity = 2;
}

message GetAvailabilityResponse {
  bool available = 1;
  int32 available_quantity = 2;
}

service InventoryService {
  rpc GetAvailability(GetAvailabilityRequest)
      returns (GetAvailabilityResponse);
}
~~~

The package/version in the service name is part of the RPC path. When evolving a contract, never reuse removed field numbers and never change field types arbitrarily. Adding optional fields according to compatibility rules is usually safer than changing the meaning of existing fields.

The contract should describe the data needed for the business decision. Avoid sending huge object graphs or data unused by the caller, because large payloads increase serialization, network, and memory costs.

## 8. Reusing ManagedChannel in a Spring Client

One cause of losing gRPC's latency benefits is creating a new channel for every RPC. A channel manages connections, resolvers, load balancing, and transport; it should be reused per endpoint/target across the application lifecycle.

Example client component holding a channel and stub:

~~~java
@Component
final class InventoryGrpcClient implements AutoCloseable {
    private final ManagedChannel channel;
    private final InventoryServiceGrpc.InventoryServiceBlockingStub stub;

    InventoryGrpcClient(InventoryGrpcProperties properties) {
        this.channel = ManagedChannelBuilder
            .forTarget(properties.target())
            .useTransportSecurity()
            .build();

        this.stub = InventoryServiceGrpc.newBlockingStub(channel);
    }

    GetAvailabilityResponse getAvailability(
            String sku, int quantity, Duration timeout) {
        return stub.withDeadlineAfter(
                timeout.toMillis(), TimeUnit.MILLISECONDS)
            .getAvailability(
                GetAvailabilityRequest.newBuilder()
                    .setSku(sku)
                    .setRequestedQuantity(quantity)
                    .build());
    }

    @Override
    public void close() throws InterruptedException {
        channel.shutdown();
        if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
            channel.shutdownNow();
        }
    }
}
~~~

This is an illustrative TLS configuration example; in a real project, trust material, authority, and the channel builder must match actual infrastructure. Register the channel/client as a Spring bean with lifecycle management so Spring closes it on context shutdown. Do not create channels inside every method and leak the transport.

A stub is a lightweight object and can create immutable variants with different deadlines, interceptors, or call options. The channel is the connection resource that needs lifecycle management.

## 9. Setting Deadlines Based on the Latency Budget

If a caller has a 200 ms budget for a request and spends 80 ms on other steps, the RPC to InventoryService cannot arbitrarily wait several seconds. Deadlines should be chosen based on the business flow's latency budget, including network, server processing, queueing, and remaining time for the caller.

~~~java
InventoryServiceGrpc.InventoryServiceBlockingStub bounded =
    stub.withDeadlineAfter(80, TimeUnit.MILLISECONDS);

GetAvailabilityResponse response =
    bounded.getAvailability(request);
~~~

A deadline does not guarantee the server stops immediately; the service must check cancellation and propagate the signal to background work. If the server keeps querying the database after the caller has timed out, resources are wasted on a result that will never be used.

Do not assign the same default deadline to every method without considering semantics. Short read RPCs, long reports, and streaming sessions have different budgets. Deadlines must be tight enough to protect the caller yet realistic for the workload.

## 10. Choosing Unary or Streaming

Unary is usually the simplest choice for a short request needing a single response:

- Easier to retry when the method has safe semantics and has not committed.
- Easier to apply deadlines, record per-RPC metrics, and test.
- Well-suited for lookups, validation, and small commands/queries.

Streaming is suitable when multiple messages need to be transferred on the same call:

- Server-streaming for events or incrementally emitted data.
- Client-streaming for chunked uploads or aggregating inputs.
- Bidirectional streaming when both sides need continuous exchange.

Do not use streaming just to avoid designing pagination or to bundle unrelated requests into one call. Long-lived streams require flow control, cancellation, deadline/lifecycle management, buffer limits, and reconnect/resume strategies.

## 11. Load Balancing and Service Discovery

A channel can represent a logical target rather than a fixed IP. A resolver provides backend addresses; a load balancer selects a subchannel for an RPC according to a policy. This helps clients connect to multiple instances and recover when a backend becomes unavailable.

With gRPC, you need to choose an appropriate balancing strategy. `pick_first` typically uses one ready backend; `round_robin` distributes calls across resolved backends when supported by the resolver and service config. Policy names and capabilities depend on the version/runtime.

Do not hard-code a pod IP or ephemeral port in production clients. Use DNS, a service mesh, a resolver, or a discovery mechanism supported by the platform. Verify HTTP/2 pass-through, idle timeouts, connection draining, and keepalive on proxies/load balancers.

## 12. Securing Internal Communication

Internal communication still requires authentication and data protection. TLS encrypts the transport and authenticates the server; mutual TLS can authenticate both client and server using certificates. Metadata often carries bearer tokens, trace IDs, or tenant context.

Principles:

- Do not send credentials over an untrusted plaintext network.
- Verify the certificate chain and hostname/authority.
- Include only necessary metadata in calls; do not log tokens.
- Use interceptors or CallCredentials for appropriate authentication.
- Enforce authorization on the server; do not trust tenant/role solely from client self-claims.
- Rotate certificates/credentials without disrupting all channels at once.

TLS incurs handshake and encryption overhead, but channel reuse reduces the number of handshakes. Do not disable TLS just to improve benchmarks; measure with security settings equivalent to production.

## 13. Observability for Internal RPC

Low latency must be measured at each hop and across the whole request. At a minimum, collect:

- RPC count and throughput by service/method.
- Latency histograms p50, p95, p99; not just averages.
- Status codes and error rates by method.
- Deadline exceeded, cancellation, and retry attempts.
- Request/response sizes and streaming duration.
- Connection/channel state, backend distribution, and queue depth.
- Trace context propagated via metadata/interceptors.

Do not attach user IDs, request IDs, or high-cardinality values as metric labels. Use traces/logs for detailed identifiers and keep metric labels to a bounded set of values.

A service with good p50 but poor p99 can significantly slow down a request chain. Tail latency is often impacted by GC, lock contention, pool saturation, cold connections, retry storms, or a single slow backend.

## 14. Measure Performance Before Deciding

Compare gRPC and REST using an equivalent workload:

1. Same business operation and same data.
2. Same TLS/security assumptions and network path.
3. Same concurrency, connection reuse, and timeout policies.
4. Warm up the JVM and connections before measuring steady state.
5. Measure p50/p95/p99, throughput, CPU, heap/allocations, and network bytes.
6. Test small, medium, and large payloads; both normal traffic and bursts.
7. Test backend failures, retries, connection draining, and cold starts.

Do not draw conclusions solely from serialization microbenchmarks. End-to-end latency also includes network, queueing, business logic, proxies, and dependencies. If gRPC reduces bytes but the service processes database queries slowly, total latency may remain almost unchanged.

## 15. Costs and Limitations to Account For

gRPC brings operational and development costs:

- Must manage Protobuf schemas, generated code, and compatibility.
- Requires tooling/debugging that supports gRPC/HTTP2.
- Browsers and some integration systems need gRPC-Web, a gateway, or an adapter.
- Proxies/load balancers must properly support HTTP/2 mode; misconfiguration can cause stream resets or timeouts.
- Channels, executors, and streaming calls need clear lifecycles.
- Binary payloads are harder to inspect directly than JSON; selective tracing/logging is needed.
- A shared HTTP/2 channel can be affected when the underlying TCP connection experiences packet loss or overload.

These costs are justified when the gains in contracts, latency, throughput, and streaming are significant. If the system has few calls, small payloads, and latency is not a bottleneck, REST may be simpler.

## 16. Decision Matrix

| Question | If the answer is "yes" | Direction to consider |
| --- | --- | --- |
| Frequent service-to-service RPC with high latency/throughput needs? | Yes | gRPC is a strong candidate. |
| Can both ends share and version a Protobuf contract? | Yes | Code generation and typed stubs provide value. |
| Is server/client/bidirectional streaming needed? | Yes | gRPC has direct semantics. |
| Are clients mainly browsers or general HTTP partners? | Yes | REST or gRPC-Web/gateway. |
| Are durable queues, replay, and independent consumers needed? | Yes | A message broker is a better fit. |
| Does proxy infrastructure lack end-to-end HTTP/2 support? | Yes | Resolve infrastructure first or choose another protocol. |
| Lacking observability, TLS, and deadline management? | Yes | Add operational readiness before scaling gRPC. |

The final decision should be based on workload and measured metrics, not just the reputation that "gRPC is fast".

## 17. Common Mistakes When Choosing gRPC

| Mistake | Consequence | Mitigation |
| --- | --- | --- |
| Assuming gRPC is always faster than REST | Wrong choice when the bottleneck is in the database or business logic | Benchmark end-to-end with an equivalent workload. |
| Creating a channel per RPC | Increases handshakes, sockets, and thread churn | Reuse ManagedChannel per target/lifecycle. |
| Not setting deadlines | Calls hang and consume resources | Choose deadlines according to the latency budget. |
| Retrying every status | Increases load and repeats side effects | Choose retryable statuses and design idempotency. |
| Using streaming for every method | Increases lifecycle/flow-control complexity | Prefer unary if one request/response suffices. |
| Using gRPC directly for browsers without an adapter | Clients cannot call the protocol as expected | Use gRPC-Web or a gateway/REST edge. |
| Hard-coding backend IPs | Clients cannot keep up with scaling/restarts | Use resolvers/service discovery. |
| Skipping TLS for benchmarks | Results are unrepresentative of production and reduce security | Benchmark with TLS equivalent to production. |
| Measuring only average latency | Misses tail latency | Measure p50/p95/p99 histograms and error rates. |
| Not managing schema compatibility | Skewed version deployments cause RPC errors | Version contracts and verify compatibility. |

## 18. Hands-on Exercise

Evaluate communication choices for three flows:

1. OrderService calls InventoryService synchronously to confirm stock availability.
2. A browser calls an API to view order history.
3. OrderService emits an OrderCreated event for multiple background consumers.

For each flow:

- Identify latency requirements, delivery semantics, client type, and coupling.
- Choose gRPC, REST, or a message broker and explain the trade-offs.
- For the gRPC flow, define the Protobuf contract, choose unary/streaming, and set a deadline.
- Design channel reuse, TLS, service discovery, and status handling.
- Measure p50/p95/p99, throughput, CPU, memory, and network bytes compared to an alternative.

**Completion criteria:** protocol choices match the interaction model, have quantitative justification, clearly identify operational constraints, and do not assume gRPC automatically guarantees low latency.

## 19. Takeaways

- gRPC fits internal RPC with clear contracts, high frequency, critical latency/throughput, and controlled client/server ends.
- Protobuf reduces representation/parsing overhead in many workloads; HTTP/2 multiplexes multiple RPCs over a channel.
- Reusing ManagedChannel, setting deadlines, and managing cancellation are key factors for keeping latency stable.
- Unary fits short request/response; streaming is for exchanging multiple messages and requires managing flow control/lifecycle.
- REST fits public/browser APIs and broad integration; brokers fit events, buffering, and asynchronous consumers.
- TLS, service discovery, HTTP/2 proxies, and observability are operational prerequisites, not optional afterthoughts.
- Measure p50/p95/p99, throughput, CPU, memory, and network bytes with an equivalent workload before deciding.
- gRPC is not automatically faster if the bottleneck lies in business logic, database, queues, or network.

Choose gRPC for low-latency internal RPC when the benefits of Protobuf, HTTP/2, typed contracts, and deadlines match the workload, and the team can operate it safely and measure end-to-end performance.
