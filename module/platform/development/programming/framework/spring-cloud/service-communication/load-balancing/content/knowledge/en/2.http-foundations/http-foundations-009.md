# Network Latency, Processing Time, and Time Budgets

An HTTP request between two microservices consumes time in multiple places: the client may wait for a connection, data travels across the network, and the server may wait in queues, execute business logic, and call downstream services. Simply setting a large timeout on each individual call without considering total request duration can leave the microservice chain responding far slower than users tolerate.

When designing service communication with Spring Cloud LoadBalancer, it is essential to understand **network latency**, **processing time**, and **time budgets**. These three concepts help choose appropriate timeouts, bound retries, and pinpoint the true cause of slowdowns.

## 1. Distinguishing Network Latency from Processing Time

**Latency** is the elapsed time from when an operation starts until a result arrives. In HTTP communication, the duration observed by the client usually includes many components rather than server code execution time alone.

**Network latency** is the portion of time data spends traveling over the network between client and server. It can be affected by geographic distance, hop count, routing, network congestion, packet loss, and retransmissions. Round-trip time (RTT) is the time for a packet to travel from sender to receiver and back; RTT does not include the HTTP server's full business processing time.

**Server-side time** is the span from when the server receives the request until it sends the response. Within this span, distinguish queueing wait time (queueing) from actual processing time (processing). Processing can include:

- Waiting for a worker thread or event loop to handle the request.
- Authentication, authorization, and input validation.
- Executing business logic.
- Querying a database, cache, or calling another service.
- Building the response and writing bytes to the socket.

Thus, a request can be slow even on a fast network, such as when the server waits for a database connection. Conversely, the server may process quickly while the client still observes a slow response due to network delay, TLS, or waiting to borrow a connection.

### Latency, response time, and throughput

Three metrics commonly appear in system observability:

| Metric | Meaning | Example |
|---|---|---|
| Latency | Time an operation takes end-to-end between chosen measurement points | An HTTP call takes 280 ms |
| Response time | Time from sending the request until receiving the response from the client's perspective | Client sends at 10:00:00.000 and finishes receiving at 10:00:00.280 |
| Throughput | Number of requests completed per unit of time | 800 requests/second |

High throughput does not imply low latency. A service can process many requests per second while some requests still wait a long time in queues. Conversely, a service receiving few requests may respond quickly yet have low throughput due to resource limits.

In practice, specify the start and end measurement points whenever stating a request's latency. Timings measured at the browser, API gateway, HTTP client, and server can differ because each observes a different slice of the flow.

## 2. Where Does an HTTP Request Spend Time?

A call from client to server typically passes through the following stages:

1. The client prepares the request and acquires a connection from the connection pool.
2. If needed, the client resolves the hostname via DNS or runs endpoint resolution.
3. If no suitable connection exists, the client establishes a TCP connection and optionally performs a TLS handshake.
4. The client sends the request over the network.
5. The server receives the request; the request may wait in a queue.
6. The server runs business logic and dependent operations.
7. The server sends the response over the network.
8. The client reads the body, decodes the payload, and continues processing.

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant N as Network
    participant S as HTTP Server
    participant D as Database
    C->>C: Acquire connection / prepare request
    opt New connection
        C->>N: DNS, TCP connect, TLS handshake
        N-->>C: Connection ready
    end
    C->>N: Send HTTP request
    N->>S: Request arrives at server
    S->>S: Queue wait and processing
    S->>D: Query data
    D-->>S: Return data
    S-->>N: HTTP response
    N-->>C: Response reaches client
    C->>C: Read body and decode
~~~

Client-observed time can be modeled as:

~~~text
T_request =
    T_pool_wait
  + T_name_resolution
  + T_connection_setup
  + T_request_transfer
  + T_server_queue
  + T_server_processing
  + T_response_transfer
  + T_client_decode
~~~

This is a decomposition model for analysis. Not every term appears in every request:

- When reusing a keep-alive connection, DNS, TCP connect, and TLS handshake may be skipped.
- Some HTTP clients perform DNS or connection acquisition with their own mechanisms.
- Server processing may include multiple downstream calls.
- Some steps may overlap; in that case, do not sum parallel step durations as if they ran sequentially.

**Ping does not represent HTTP latency.** Ping typically measures RTT using ICMP, whereas an HTTP request may also wait on a connection pool, TLS setup, server queues, data queries, and response body reading. Low ping is a useful network signal, not proof that an API will respond fast.

## 3. Factors That Increase Latency

### Distance and network path

The farther apart client and server are geographically, or the more network hops lie between them, the longer data transmission typically takes. Routing, firewalls, NAT, proxies, and service meshes can also add processing steps.

### Queueing and resource utilization

When requests arrive faster than capacity can process them, requests wait. This wait time can spike sharply as CPU, thread pools, connection pools, or databases approach saturation.

For example, actual business logic takes only 40 ms, yet the request waits 250 ms for a worker thread. Measuring only inside the business method misses most of the latency felt by the client.

### Connection pools and new connections

HTTP clients usually reuse connections to avoid TCP/TLS setup on every request. However, when the pool is exhausted, the client must wait for a connection to be returned. If the pool is sized too small or response bodies are not consumed/closed properly, connection acquire wait time climbs.

### Payloads and data processing

Large requests or responses increase transmission and decoding time. Compression reduces network bytes at the cost of CPU time. Evaluate both sides rather than assuming compression is always faster.

### Downstream dependencies

An API may call databases, caches, and several other microservices. Just one slow dependency can stretch the parent API's response time. When many concurrent requests wait on that dependency, queues can cascade upstream to its callers.

## 4. Time Budgets and Deadlines

A **time budget** is the maximum amount of time a request is permitted to spend to accomplish a goal. Budgets are typically derived from user-experience requirements or API SLOs.

For example, an order lookup API must return a result within at most 1,200 ms. That entire duration is the request's budget, covering work in the current API plus any necessary downstream calls.

A **deadline** marks when the budget runs out. Once the deadline arrives, the request has no remaining time to keep waiting. A system can represent a deadline as an end timestamp or as remaining duration.

Distinguish clearly:

- **Timeout:** a wait limit for a single operation or stage. Once exceeded, the client stops waiting and reports a timeout error.
- **Deadline:** the final time limit for the entire unit of work. Sub-operations must draw from the remaining budget.
- **Time budget:** the total time allocated to the work, from which step deadlines and timeouts are derived.

Setting a 1-second timeout on three sequential downstream calls does not mean the parent request finishes within 1 second. In the worst case, three sequential calls can consume nearly 3 seconds combined, excluding local processing and retries.

### Allocating budget across sequential steps

Suppose an API has a 1,200 ms deadline and makes two sequential downstream calls:

| Stage | Maximum budget |
|---|---:|
| Authentication and request preparation | 100 ms |
| Call Catalog Service | 350 ms |
| Call Inventory Service | 400 ms |
| Aggregate and serialize response | 150 ms |
| Buffer for gateway, network, and variance | 200 ms |
| **Total** | **1,200 ms** |

Each service call budget must account for the full time the client waits on that call: connection pool wait, endpoint resolution if any, connect, network, server processing, response transfer, and decoding.

If Catalog Service takes 310 ms instead of 350 ms, the parent request retains 40 ms more remaining time. When starting the Inventory Service call, the client should recalculate the remaining budget and never grant that call more time than remains before the parent deadline.

### Parallel calls

If Catalog and Inventory are called in parallel, overall wait time approximates the slowest branch plus pre/post processing, rather than the sum of both branches:

~~~text
T_total ≈ T_prepare + max(T_catalog, T_inventory) + T_aggregate
~~~

This formula holds only when the two calls truly run concurrently without sequential dependencies between them. They still share the parent request's deadline; one slow branch must not exceed the deadline merely because the other branch finished early.

## 5. Timeouts Across HTTP Stages

Timeouts must be configured per operation type as well as against the overall deadline. Common types include:

| Timeout type | What does it bound? | When exceeded |
|---|---|---|
| Connection pool/acquire timeout | Wait time to borrow an available connection | Client cannot obtain a connection from the pool |
| DNS/name resolution timeout | Time to resolve a hostname | Client cannot determine the target address |
| Connect timeout | Time to establish a TCP connection | Cannot connect to the endpoint |
| TLS handshake timeout | Time to complete the TLS handshake | Secure channel is not ready |
| Response/read timeout | Time waiting for response data per HTTP client semantics | Client stops waiting for data |
| Overall request timeout | Total time for one request execution | The entire call is bounded |

Exact names and semantics vary by HTTP client library. For example, a read timeout in one client may cap the maximum idle gap waiting for the next chunk of data, not necessarily total time to download the entire response body. Read the documentation of your specific implementation to know from which point to which point a timeout measures.

A configuration with a 200 ms connect timeout and a 500 ms read timeout can still take more than 700 ms once connection pool wait, DNS, TLS, retries, or other steps are included. Therefore, per-stage timeouts do not replace an overall timeout or deadline.

### A timeout does not mean the server stopped processing

When a client times out, the only certainty is that the client stopped waiting per its timeout policy. You cannot conclude the server halted processing or rolled back its transaction.

Example:

1. Client sends an order creation request.
2. Server receives and persists the order in the database.
3. Response is delayed on the network.
4. Client hits its timeout and reports an error.
5. User retries, generating a second request.

Without idempotency or deduplication on the API, the system can create two orders. Therefore, timeouts must be designed together with retry handling and operation idempotency.

## 6. Applying Time Budgets to Spring Cloud LoadBalancer

Spring Cloud LoadBalancer handles finding and selecting a `ServiceInstance` for a service ID. It does not guarantee that the chosen instance will respond within a fixed time.

In a load-balanced call, client-observed time can include:

- Time to retrieve the instance list from `ServiceInstanceListSupplier`.
- Time to filter or select an instance according to configuration.
- HTTP client connection pool wait and connection setup time.
- Network transit and server processing time.
- Retry time if a retry policy is enabled.

The instance source may be cached or queried from discovery depending on configuration and integration. Do not assume every HTTP request issues a fresh network query to the service registry; nor assume discovery cost is always zero.

### Timeouts belong to the HTTP client and the overall call

When integrating RestClient, WebClient, or OpenFeign, connect/response timeouts are typically configured on the underlying HTTP client or request factory. Exact configuration depends on the client implementation and Spring version in use.

Clearly define three bounds:

1. Timeout for a single attempt to one instance.
2. Total time for the whole call, including retries and backoff.
3. Deadline of the parent request, shared with other downstream calls.

For example, if a parent API has 600 ms of budget left, it should not launch a downstream call with a 1,000 ms timeout, because the child call could keep waiting after the parent request has already expired. A child call's timeout must be less than or equal to the remaining parent budget after reserving necessary overhead.

### Example of calculating remaining budget

Use a monotonic clock to measure elapsed time within a single process. `System.nanoTime()` suits duration measurement because it is unaffected by wall-clock adjustments.

~~~java
import java.time.Duration;

final class RequestBudget {
    private final long deadlineNanos;

    RequestBudget(Duration budget) {
        this.deadlineNanos = System.nanoTime() + budget.toNanos();
    }

    Duration remaining() {
        long nanos = deadlineNanos - System.nanoTime();
        return Duration.ofNanos(Math.max(0, nanos));
    }

    boolean isExpired() {
        return remaining().isZero();
    }
}
~~~

Usage:

~~~java
RequestBudget budget = new RequestBudget(Duration.ofMillis(1200));

// After authentication and calling Catalog Service:
Duration remaining = budget.remaining();

// Reserve 100 ms for response aggregation and buffer.
Duration usable = remaining.minus(Duration.ofMillis(100));
if (usable.isZero() || usable.isNegative()) {
    throw new IllegalStateException("No remaining budget for downstream call");
}

// Cap timeout at 400 ms or the actually usable remaining budget.
Duration phaseCap = Duration.ofMillis(400);
Duration inventoryTimeout = usable.compareTo(phaseCap) < 0
        ? usable
        : phaseCap;
~~~

This example manages a budget within one process. When propagating deadlines across machines, `System.nanoTime()` values from different hosts cannot be compared directly because each host has its own monotonic epoch. Systems must pass remaining time or an agreed deadline format; if passing absolute timestamps, account for clock skew across hosts.

In HTTP, headers carrying deadlines or remaining budgets are usually system-specific conventions rather than a single universal standard header understood automatically by every HTTP client and server. Services must agree on how budgets are created, validated, and decremented so they do not blindly trust values sent by external clients.

## 7. Retries Must Fit Inside the Time Budget

Retries improve success rates on transient failures, yet each retry consumes time and resources. Unbounded retries can overload a system further when a dependency is struggling.

Total time for a call with retries can be modeled as:

~~~text
T_call =
    T_attempt_1
  + T_backoff_1
  + T_attempt_2
  + ...
  + T_attempt_n
~~~

Here each attempt may include instance selection, connection wait, network transit, and server processing. Total duration must stay below the parent request's remaining budget.

When designing retries:

- Retry only errors likely to be transient, under an explicit policy.
- Cap the attempt count and total retry duration.
- Use backoff, usually paired with jitter, to prevent many clients from retrying simultaneously.
- Retry only safe operations or operations protected by an idempotency key/deduplication mechanism.
- Subtract backoff and prior attempt durations from the remaining deadline.
- Avoid enabling independent retries across multiple layers without calculating multiplicative attempt counts.

For example, if the HTTP client tries three times and an upper layer also retries three times, one logical request can generate up to nine calls at the lower layer depending on how policies nest. This increases load and stretches completion time.

With Spring Cloud LoadBalancer, retries can be configured at the LoadBalancer layer; the HTTP client or application may also have its own retry policy. Inspect all active layers to know the exact attempt count, whether a new instance is selected, and whether timeouts apply per attempt or across the entire chain. Do not assume a single universal default timeout/retry setup across all versions and HTTP clients.

## 8. Measuring Where Time Is Spent

To optimize latency, first measure accurately which part is slow. Logging a single line like "API took 900 ms" is rarely enough to identify the root cause.

Observe both client and server sides:

| Measurement point | Information to collect |
|---|---|
| HTTP client | Total request duration, timeouts, retry count, status code |
| Connection pool | Active connections, idle connections, connection acquire wait time |
| Discovery/LoadBalancer | Service ID, candidate instance count, selected instance, no-instance errors |
| HTTP server | Queue wait time, processing time, in-flight request count |
| Database/downstream | Query duration and downstream service call duration |
| Network/transport | DNS, connect, TLS, retransmissions, and connection errors where tools support them |

Distributed tracing links a request across multiple microservices. Each service emits spans for its own processing and downstream calls. Reading a trace reveals which service spent the time and whether that time went to internal processing or a child call.

Track latency percentiles:

- **p50:** half of requests finish within this duration or faster.
- **p95:** 95% of requests finish within this duration or faster.
- **p99:** 99% of requests finish within this duration or faster.

Averages can hide a subset of very slow requests. In microservices systems, p95 and p99 are particularly useful for evaluating behavior under high load or when a dependency has fluctuating latency.

When measuring elapsed intervals in Java, use `System.nanoTime()` or appropriate metrics/tracing tools. Do not use differences of `System.currentTimeMillis()` as an accurate elapsed-time measurement because wall-clock time can jump due to time synchronization or administrative changes.

## 9. Example Breakdown of a Slow Request

Suppose a client calls Order Service and total response time is 980 ms. A trace shows:

| Component | Duration |
|---|---:|
| Connection pool wait | 20 ms |
| Connect and TLS | 40 ms |
| Network and request/response transfer | 70 ms |
| Server queue wait | 180 ms |
| Business processing in Order Service | 90 ms |
| Call to Inventory Service | 520 ms |
| Read and decode response | 60 ms |
| **Total** | **980 ms** |

Inventory Service accounts for 520 ms, the largest share of the request. Raising Order Service's timeout from 1 second to 2 seconds only makes the client wait longer; it does not make Inventory Service faster.

The next diagnostic step is opening Inventory Service's trace to break down those 520 ms into pool wait, network, queue, database, and processing. If most time sits in the queue, inspect load and capacity. If it sits in the database, check queries, connection pools, and locks. If it sits in networking or connections, check network paths, DNS, TLS, and pooling.

If the API deadline is 1,000 ms, the request above has only about 20 ms of headroom left. Even a minor variance can push the request into a timeout. Reduce the bottleneck latency, allocate budgets explicitly, and decide retries based on the time genuinely remaining.

## 10. Common Mistakes

| Mistake | Consequence |
|---|---|
| Setting the same large timeout for every downstream call | One slow dependency can consume the entire parent request budget |
| Configuring only connect timeout | Client may still wait indefinitely or far too long for responses depending on the HTTP client |
| Treating read timeout as total response download time | A trickling response can exceed the intended total duration |
| Retrying every error | Amplifies load, creates duplicate requests, and exhausts budgets |
| Ignoring backoff time | Total retry time exceeds the deadline |
| Measuring only business logic execution time | Misses pool wait, queueing, network, and TLS |
| Using ping to conclude an API is fast | Ignores HTTP, server processing, and downstream calls |
| Assuming a timeout means the server cancelled the operation | Can create duplicate records when users retry |
| Tracking only average latency | Fails to detect very slow p95/p99 tail requests |

## 11. Time Budget Design Checklist

When an HTTP client calls a service through Spring Cloud LoadBalancer, check:

1. Have you defined an end-to-end request deadline from business requirements or SLOs?
2. Have you decomposed time into pool wait, connection setup, network, queueing, server processing, and response reading?
3. Do per-stage timeouts align with the semantics of the HTTP client in use?
4. Does each downstream call receive a timeout derived from the parent request's remaining budget?
5. Does the combined time of retries and backoff fit within the deadline?
6. Are retryable operations safe against duplicate execution?
7. Do you have traces/metrics to pinpoint which service or dependency consumes time?
8. Are you tracking p95, p99, timeout rate, retry rate, and connection pool wait times?

Network latency tells you how long data takes to travel; processing time tells you how long the server takes to accept and execute work; time budgets set the boundary for the whole request. Combining these three concepts allows clients to set realistic timeouts, bound retries, and keep microservice call chains finishing within committed deadlines.
