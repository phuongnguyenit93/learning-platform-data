# Deadlines Through Proxies and Load Balancers

In a Spring gRPC system, an RPC may pass through a gateway, reverse proxy, service mesh, or load balancer before reaching the server. Each layer can have its own timeouts. If a proxy sets a fresh wait duration instead of preserving the caller's remaining budget, total processing time can exceed the initial deadline. If a proxy uses an overly short timeout or does not understand streaming, it can cut off a valid RPC.

An **end-to-end deadline** is the time limit the caller grants for the entire RPC. Proxies and load balancers must preserve this limit across hops, apply appropriate internal timeouts, and propagate cancellation upstream when the call ends. In gRPC, deadlines are represented on the wire by the **grpc-timeout** protocol header; gRPC-aware L7 proxies must preserve or update the remaining duration properly.

## 1. How do RPCs traverse proxies and load balancers?

A request may follow a path like this:

~~~mermaid
flowchart LR
    C["gRPC client"] --> P["Gateway / L7 proxy"]
    P --> L["Load balancer"]
    L --> S["Spring gRPC server"]
    S --> D["Database / downstream"]
~~~

The client may grant 1,200 ms for the entire RPC. Time spent waiting at the gateway, load balancing, network, queues, and server processing all consume that budget. When the request reaches the Spring gRPC server, the server must receive the **remaining time**, not a fresh full 1,200 ms deadline.

Illustrative example:

| Hop | Time Used | Approx. Remaining Budget |
| --- | ---: | ---: |
| Client starts | 0 ms | 1,200 ms |
| Gateway receives and routes | 100 ms | 1,100 ms |
| Load balancer picks upstream, transmits request | 50 ms | 1,050 ms |
| Spring gRPC processes and calls downstream | 700 ms | 350 ms |
| Return response across hops | 150 ms | 200 ms headroom |

These numbers are illustrative. What matters is that **every layer shares a single total budget**, and each layer only consumes its allotted share.

## 2. L4 and L7 proxies affect deadlines differently

### L4: TCP passthrough

An L4 load balancer typically forwards TCP connections without parsing HTTP/2 or gRPC metadata. When operating as passthrough, the grpc-timeout header travels inside the HTTP/2 stream end-to-end to the gRPC server. The L4 tier may still enforce TCP connection timeouts, idle connection timeouts, or its own connection limits.

A TCP connection timeout does not replace per-RPC deadlines. One HTTP/2 connection can carry many concurrent RPCs; closing the connection can affect every stream active on that connection.

### L7: gRPC-aware proxy

An L7 proxy terminates client-side HTTP/2 and creates a new upstream request to the server. It can inspect routes, methods, and metadata, and apply timeout/retry policies. When doing so, the proxy must:

- Preserve the caller's deadline or translate it into an equivalent upstream timeout.
- Compute the **remaining time** as the request passes through the proxy.
- Never overwrite a shorter deadline set by the caller.
- Preserve appropriate gRPC statuses and trailers when returning results.
- Propagate cancellation/reset upstream when the downstream client cancels or the deadline expires.

Not every proxy handles gRPC identically. For proxies that only understand generic HTTP, verify how they handle the grpc-timeout header, HTTP/2 streams, and gRPC trailers. Do not assume an HTTP route timeout automatically equals an end-to-end gRPC deadline.

## 3. grpc-timeout is a protocol header, not custom metadata

When a gRPC client sets a deadline, the gRPC transport encodes the remaining duration into the **grpc-timeout** header. This value can use different time units according to protocol rules; applications should not manually parse or copy this header string in business code.

~~~java
GetOrderResponse response = orderStub
    .withDeadlineAfter(1200, TimeUnit.MILLISECONDS)
    .getOrder(request);
~~~

If an L7 proxy terminates the HTTP/2 connection and creates a new upstream request, it must forward or recompute the timeout according to the remaining budget. It must not resend the original value after spending time at the gateway. If the caller has 800 ms left upon reaching the proxy, upstream cannot be granted 1,200 ms again.

Metadata such as authorization, tenant ID, request ID, and trace context are separate concerns. Interceptors can manage them, but do not use custom metadata to replace gRPC deadlines.

## 4. Distinguishing proxy and load balancer timeouts

A proxy often has several distinct timeouts. Exact names depend on the product, though common meanings include:

| Timeout | Scope | Role |
| --- | --- | --- |
| **Connect timeout** | Establishing upstream connection | Bounds time spent opening a connection to the backend |
| **Route/request timeout** | One request or logical upstream operation | Bounds total time the proxy waits for a result |
| **Per-try timeout** | One upstream attempt | Bounds each attempt's duration when the proxy retries |
| **Stream idle timeout** | One HTTP/2/gRPC stream | Closes a stream with no activity within the configured period |
| **Maximum stream duration** | Total stream lifetime | Bounds long-lived streaming sessions |
| **TCP idle timeout** | Transport connection | Reclaims inactive connections |

These timeouts cannot substitute for one another. For example, a 200 ms connect timeout only bounds opening the connection; it does not limit how long the server processes the RPC. Nor does a 60-second stream idle timeout mean a unary RPC is allowed to run for 60 seconds.

Route timeout and per-try timeout names and calculations vary across Envoy, ingress controllers, service meshes, and cloud load balancers. Read the specific product documentation and verify with integration tests; never copy a timeout configuration across different proxies without verifying semantics.

## 5. Allocating budgets across caller, proxy, and backend

A practical policy might start with:

| Layer | Example Limit | Purpose |
| --- | ---: | --- |
| Client logical RPC | 1,200 ms | Caller's end-to-end budget |
| Gateway route | max 1,100 ms | Reserve time for client to receive response |
| Upstream per try | max 400 ms | Bound each backend attempt |
| Spring gRPC method | per remaining deadline, max 350 ms for main business step | Do not exceed upstream budget |
| Database query | max 250 ms | Prevent queries from holding connections long |

This is only an allocation example, not a standard configuration. Limits must be chosen based on p95/p99 latency, SLAs, queue times, and processing costs at each layer.

Principles:

1. The proxy route timeout should not exceed the caller's remaining budget.
2. Per-try timeout must be less than or equal to the route timeout and remaining deadline.
3. Backend/downstream timeouts must fit within the budget still granted by the proxy and caller.
4. Reserve headroom for serialization, network response, and caller-side processing.
5. When insufficient time remains for a reasonable attempt, do not start a new attempt.

Do not set every layer's timeout to the same number. If each layer grants a full 1,200 ms again, actual total duration can far exceed the SLA.

## 6. Retries at client and proxy can multiply attempts

A gRPC client may retry per service config; an L7 proxy may also retry upstream. If both retry, requests reaching the backend can grow by the product of each layer's attempts.

For example, up to 3 client attempts and up to 2 proxy attempts per received request can generate up to 6 upstream attempts in the worst case. When many clients encounter errors together, retry amplification can overload the backend further.

Recommendations:

- Pick one primary layer responsible for retries per error type.
- Bound total attempts and retry duration within the logical RPC deadline.
- Use exponential backoff and jitter.
- Only retry statuses that are genuinely recoverable.
- Avoid retrying commands with side effects unless idempotency is in place.
- Monitor logical RPC count compared to upstream attempt count.

DEADLINE_EXCEEDED does not prove the backend has not executed the operation. A proxy may time out after the backend already committed while the response had not yet returned. For commands like order creation or payment, use a stable idempotency key across client, proxy, and backend; do not generate a new key per attempt.

## 7. Cancellation must flow backward from proxy to backend

When a client cancels an RPC or the deadline expires, the L7 proxy must terminate the downstream stream and request cancellation of the upstream call. On the Spring gRPC server, gRPC Java typically surfaces this via context cancellation:

~~~java
Context rpcContext = Context.current();

rpcContext.addListener(cancelled -> {
    downstreamFuture.cancel(true);
    stopProducer();
    releaseTemporaryResources();
}, cleanupExecutor);
~~~

The future, producer, and cleanup method names represent assumed application components. The server must propagate context/cancellation to downstream calls and wire the signal to cancellable databases, HTTP clients, or background tasks.

Cancellation does not automatically roll back committed transactions. If the backend completes side effects before the proxy cancels the call, the client may receive a timeout even though the operation happened. Idempotency and operation status remain necessary.

Proxies may also behave differently on client disconnect: some configurations cancel upstream immediately, while others may let the request continue depending on policy. Test and configure this behavior explicitly, especially for resource-intensive RPCs.

## 8. Streaming requires dedicated timeouts

For server streaming or bidirectional streaming, a proxy might apply a short route timeout suited for unary calls. That cuts off valid streams mid-flight. Conversely, removing all timeouts can hold connections, subscriptions, and buffers indefinitely.

Distinguish:

- **RPC deadline:** total lifetime of an RPC.
- **Stream idle timeout:** duration a stream has no activity as defined by the proxy.
- **Maximum stream duration:** maximum lifetime of a stream.
- **HTTP/2 keepalive:** liveness check for the transport connection.

A long-lived subscription can use a finite session lifetime, idle timeout, rate-limited heartbeats, cursor/sequence, and reconnection. If a proxy allows a route-timeout exception for streams, compensate with concurrent stream limits, backpressure, cancellation cleanup, and an explicit session lifetime.

Do not treat heartbeats as proof that business work is progressing. Heartbeats can keep a stream alive at the transport layer without replacing session limits or operation deadlines.

## 9. TLS termination and gRPC metadata

A proxy can terminate TLS at the edge and open a new TLS/mTLS connection to the backend. Terminating TLS does not remove deadlines: an L7 proxy can still read grpc-timeout from HTTP/2 headers and forward an appropriate budget upstream.

When deploying, verify:

- Both downstream and upstream use HTTP/2 compatible with gRPC.
- The proxy preserves the gRPC method path, required metadata, and trailers.
- The grpc-timeout header is preserved or translated with accurate semantics.
- TLS/mTLS is configured separately per hop according to trust boundaries.
- Credentials or sensitive metadata are not logged when debugging timeouts.

With L4 passthrough, the proxy does not decrypt TLS and usually cannot apply per-gRPC-method policies. It can only manage connection-level timeouts/health and forward the byte stream.

## 10. Testing deadlines through proxies and load balancers

Direct client-server testing is not enough to verify behavior with a proxy in the path. Set up a topology close to production and test:

1. Client sets a short deadline; proxy forwards the accurate remaining budget to the backend.
2. Proxy route timeout is shorter than the client deadline; client receives an appropriate status and does not wait beyond SLA.
3. Backend processes slowly; verify proxy timeout and cancellation propagate to the server.
4. Client actively cancels; verify proxy cancels the upstream call and the server stops tasks.
5. Proxy retry and client retry both enabled; measure actual upstream attempts.
6. Streaming exceeds the unary route timeout; verify dedicated stream policy, idle timeout, and reconnect.
7. TLS termination preserves method path, gRPC status, trailers, and timeout semantics.

Use a mock backend with controllable latency, recording timestamps at client/proxy/server and trace IDs end-to-end. Check both the final status and backend execution count; a test that only checks the client receives DEADLINE_EXCEEDED does not prove the backend stopped.

## 11. Observing deadlines hop by hop

Monitor by trace ID, full method name, and upstream cluster:

- Deadline/remaining time when requests enter and leave the proxy.
- Route timeout, per-try timeout, and proxy attempt count.
- Latency and gRPC status at client, proxy, and backend.
- Queue, connect, server processing, and downstream durations.
- Upstream calls still running after client cancellation.
- Stream duration, idle closes, reconnects, and buffer/backpressure.
- Retry amplification ratio and idempotency hit rate.

If the client times out while the backend keeps running, investigate cancellation propagation. If the proxy times out before the client, check the route timeout and headroom. If the backend receives requests with very little budget left, latency may lie in the gateway, load balancer, or earlier queues.

Do not simply raise timeouts when errors spike. First pinpoint the hop consuming the budget, then tune timeouts, capacity, or retry policies at the right layer.

## 12. Summary and self-check

**Deadlines through proxies and load balancers must preserve the caller's end-to-end budget.** L4 passthrough typically forwards the HTTP/2 stream; L7 gRPC-aware proxies must preserve or recompute grpc-timeout, enforce route/per-try timeouts within the remaining budget, and propagate cancellation to the backend. Client and proxy retries must be coordinated to avoid load amplification; streaming needs dedicated idle and session-lifetime policies.

Self-check:

1. How does an L4 proxy differ from an L7 proxy in understanding grpc-timeout?
2. Why must a proxy not grant the full initial timeout again when creating an upstream request?
3. How do route timeout and per-try timeout differ?
4. Why can enabling retries simultaneously at both client and proxy cause the backend to receive more attempts than expected?
5. When a proxy cancels an upstream call, what must the Spring gRPC server do to stop work and protect side effects?

Managing deadlines across proxies and load balancers helps Spring gRPC honor caller-requested time limits, reduce hanging requests, and maintain consistent behavior when routing, retrying, or streaming across infrastructure layers.
