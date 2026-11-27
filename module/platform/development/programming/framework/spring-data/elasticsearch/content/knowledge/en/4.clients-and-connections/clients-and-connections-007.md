# Connect Timeout, Socket Timeout, and Request Wait Time

When Spring Data Elasticsearch sends an operation to Elasticsearch, the application waits across several stages: acquiring a connection from the connection pool, establishing a network connection if needed, sending the HTTP request, waiting for Elasticsearch to process it, receiving the response, and converting the response into Java objects. Each stage can have its own time limit.

If timeouts are configured too short, the application may report errors even though Elasticsearch is functioning normally. If timeouts are too long, threads and requests may remain blocked for extended periods during cluster or network incidents. To configure timeouts properly, first distinguish **connect timeout**, **socket/read timeout**, **connection-pool acquisition timeout**, and **request deadline**.

## 1. Request lifecycle and potential timeout points

An operation such as:

```java
Product product = productRepository.findById("1001").orElse(null);
```

can pass through the following high-level steps:

```text
Spring Application
      |
      v
Spring Data Elasticsearch
      |
      v
Elasticsearch Java Client
      |
      v
HTTP client / connection pool
      |
      +---- Wait to acquire an available connection
      |
      +---- DNS, TCP connect, and TLS handshake
      |
      v
Send HTTP request to Elasticsearch
      |
      v
Elasticsearch receives and processes request
      |
      v
HTTP response streamed back
      |
      v
Client reads body, decodes JSON, and returns result
```

Not every request opens a new TCP connection. The HTTP client normally reuses connections from a pool. When a suitable connection is already available, the request can skip the TCP connect and TLS handshake phases.

Timeouts can occur at different points:

| Timeout Type | Stage Bounded | Question Answered |
|---|---|---|
| Connection-pool acquisition timeout | Waiting to borrow a connection from the pool | Is a connection available to send the request? |
| Connect timeout | Establishing a new network connection | Can a connection to Elasticsearch be established in the allowed time? |
| Socket/read timeout | Reading data from the connection | Did the client receive subsequent data within the allowed time? |
| Request deadline | Total request processing time at a given layer | Did the request complete before the overall deadline? |
| Elasticsearch-side timeout | An internal processing operation inside Elasticsearch | How long is Elasticsearch allowed to wait or process that operation? |

Names vary across Apache HttpClient, Elasticsearch Java API Client, Reactor Netty, Spring WebClient, and gateways. When reading configuration, determine which layer a timeout belongs to rather than relying solely on property names.

## 2. Connect timeout

**Connect timeout** is the maximum duration the HTTP client waits to establish a connection to the server. Depending on how a library implements timeouts, this phase can cover opening the TCP connection and, for HTTPS, completing the TLS handshake.

For example, suppose an application sets a connect timeout of 3 seconds:

- If the connection is established in 100 ms, the request proceeds normally.
- If the server is unreachable and connecting exceeds 3 seconds, the client stops waiting and raises a timeout error.
- If the server rejects the connection immediately, the application may receive a connection refused error before 3 seconds elapse. That is a different connection failure from a connect timeout.

Connect timeout mainly affects requests that need to open a new connection. If a request reuses an existing connection from the pool, connect timeout does not bound that entire request.

### Common causes

- Elasticsearch is not running or not listening on the configured host/port.
- The application uses the wrong hostname, port, or HTTP/HTTPS protocol.
- DNS resolution is slow or fails.
- A firewall, network policy, proxy, or security group blocks the connection.
- The server is overloaded or the network between the application and Elasticsearch has high latency.
- The TLS handshake fails or stalls due to certificate, proxy, or network configuration.

### Distinguishing connection errors

| Symptom | Common Meaning |
|---|---|
| Connection refused | Network destination was reached, but the port is not accepting connections—often because the service is down or the port is wrong. |
| Connect timed out | Client could not establish a connection within the configured limit; check network, host, and server status. |
| Unknown host / DNS resolution failure | Hostname could not be resolved to an IP address. |
| SSL handshake exception | TLS connection encountered certificate, protocol, or security configuration issues. |

Do not immediately increase connect timeout when an error appears. First check hostname, port, protocol, Elasticsearch status, and reachability from the exact machine/container running the application.

## 3. Socket timeout and read timeout

**Socket timeout** is commonly used to refer to the maximum time the client waits for data when reading from a socket. In many HTTP clients, it corresponds to read timeout or socket `SO_TIMEOUT`.

After sending the request, the client waits for Elasticsearch's response. If no data arrives within the configured window, the read operation can raise an error like:

```text
java.net.SocketTimeoutException: Read timed out
```

For example, with a socket timeout of 20 seconds:

1. The client sends the request successfully.
2. Elasticsearch starts processing.
3. For the next 20 seconds, the client receives no further data to read.
4. The client reports a read timeout.

This does not automatically prove Elasticsearch stopped processing. The request may have reached the server, and the server may still be executing the query after the client stopped waiting. Thus, a client-side timeout does not guarantee the server-side operation never occurred.

### Is socket timeout the total request time?

Not necessarily. In many HTTP clients, socket timeout limits waiting for a single read or the inactivity interval without receiving data, rather than acting as an absolute deadline measured from the start of the request.

For example, a large response might stream in multiple chunks. As long as data keeps arriving steadily, each read can complete within the socket timeout even if total response transfer time exceeds that value. Conversely, if the server pauses sending data for too long, the client can time out mid-stream.

Exact behavior depends on the HTTP client and version in use. Read the documentation for your actual transport before treating socket timeout as a total duration cap.

### Common causes

- Elasticsearch is executing an expensive query.
- The query scans too much data, runs heavy aggregations, or hits many shards.
- The cluster lacks CPU, RAM, or I/O, or is under heavy load.
- The response is huge or the network path is slow.
- A gateway, proxy, or load balancer interrupts the response.
- The timeout is set lower than the normal processing time of the business operation.

When encountering read timeouts, inspect processing duration, the query, response size, cluster state, and logs on both the application and Elasticsearch sides. Increasing timeout can suit an inherently long-running query, but it will not fix underlying issues like inefficient queries or an overloaded cluster.

## 4. Connection-pool acquisition timeout

HTTP clients normally maintain a pool of connections for reuse. Each connection currently in use may be unavailable to other requests, depending on how the pool and protocol manage connections.

When all available connections are busy or the pool reaches its limit, a new request must wait for a connection to return to the pool. This wait time can be bounded by a **connection request timeout**, **connection-pool timeout**, or similar setting.

For example:

- The pool can serve only a certain number of concurrent requests.
- Concurrent requests occupy all connections.
- The next request must wait.
- If no connection is released before the deadline, the client throws a connection acquisition timeout error.

This is not a connect timeout. When a pool is exhausted, the client has not even begun opening a network connection to Elasticsearch.

Common causes:

- Concurrent request volume exceeds pool capacity.
- Earlier requests are slow and hold connections for a long time.
- Response bodies were not read/closed properly in code managing HTTP responses manually.
- The pool is configured too small for the workload.
- Slow Elasticsearch or network responses keep connections leased longer.

If errors spike under load, examine concurrent request count, connection hold times, leased/available/pending connection counts, and pool limits. Simply raising connection limits can shift pressure onto Elasticsearch; check cluster capacity and load limits at the same time.

## 5. Request timeout and request deadline

The phrase **request timeout** often causes confusion because libraries and system layers use it with different meanings.

At the application level, a request deadline may represent the total time budget from when an operation starts until the application must return a result. That budget can include:

- Waiting for a connection from the pool.
- Establishing a new connection if needed.
- Sending the request.
- Waiting for Elasticsearch processing.
- Reading the response.
- Decoding the response and handling the result in the application.

For example, an application API has a 25-second deadline. If acquiring a connection takes 2 seconds, establishing the connection takes 1 second, and waiting for the response takes 20 seconds, total elapsed time is nearly out of budget. A 20-second socket timeout does not guarantee the entire request finishes within 20 seconds.

Not every Spring Data Elasticsearch version exposes a single unified `requestTimeout` property in `ClientConfiguration`. `withConnectTimeout(...)` and `withSocketTimeout(...)` are two commonly used settings; overall deadlines, pool-wait timeouts, or other dedicated timeouts may need configuration on the underlying HTTP client or at the application layer.

### Deadlines across layers

A request from a browser may traverse multiple layers:

```text
Browser
  |
  v
API Gateway / Load Balancer
  |
  v
Spring Boot Controller
  |
  v
Spring Data Elasticsearch
  |
  v
HTTP Client
  |
  v
Elasticsearch
```

Each layer can enforce its own timeout. If the gateway stops waiting after 15 seconds while the application and Elasticsearch are configured to wait 60 seconds, the user still receives a gateway error before lower layers finish. The server-side request may continue running depending on each layer's cancellation behavior.

A sound design keeps time budgets consistent: inner layers should have a chance to fail cleanly before outer layers expire. Also leave room in the budget for processing and returning the response rather than spending the entire budget on the Elasticsearch call alone.

### Application-layer timeouts

With asynchronous APIs, some abstractions let you impose a deadline on the result. For example, with Reactor:

```java
Mono<Product> productMono =
    reactiveProductRepository.findById("1001")
        .timeout(Duration.ofSeconds(25));
```

Or with a `CompletableFuture`:

```java
future.orTimeout(25, TimeUnit.SECONDS);
```

These examples show result wait limits at the respective abstraction level. How timeouts propagate down to the transport and whether the underlying HTTP request is actually cancelled depend on the client, version, and integration. Completing a future with a timeout does not prove the underlying work stopped.

For synchronous operations, do not simply offload a blocking call onto another thread and time out waiting on that thread. If the underlying HTTP call keeps running, threads and connections can remain occupied. Prefer timeouts supported by the HTTP transport and verify actual cancellation behavior.

## 6. Elasticsearch-side timeouts

Client-side timeouts and Elasticsearch-side timeouts serve two different purposes.

For example, the Search API accepts a `timeout` parameter:

```http
POST /products/_search?timeout=2s
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  }
}
```

This limits how much time Elasticsearch devotes to the search execution. When time runs out, the response may contain:

```json
{
  "timed_out": true,
  "hits": {
    "total": {
      "value": 0,
      "relation": "eq"
    },
    "hits": []
  }
}
```

This sample response shows you must inspect the `timed_out` field, shard details, and returned hits to know whether the query completed fully. A server-side search timeout differs from a socket timeout: in the first case, Elasticsearch reports its search execution state; in the second, the client failed to receive data on time.

Other Elasticsearch APIs may accept their own timeout parameters, such as waiting for a cluster condition or administrative operation. Each parameter's semantics must be checked per API. Do not append `timeout=...` to every endpoint expecting it to act as a total HTTP request deadline.

## 7. Configuring connect timeout and socket timeout in Spring Data Elasticsearch

With Spring Data Elasticsearch using the Elasticsearch Java API Client, both values can be configured via `ClientConfiguration`.

Illustrative configuration example:

```java
import java.time.Duration;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;

@Configuration
public class ElasticsearchClientConfig extends ElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
            .connectedTo("localhost:9200")
            .withConnectTimeout(Duration.ofSeconds(3))
            .withSocketTimeout(Duration.ofSeconds(20))
            .build();
    }
}
```

In this example:

- `connectedTo("localhost:9200")` declares the Elasticsearch address.
- `withConnectTimeout(Duration.ofSeconds(3))` limits time to establish a new connection.
- `withSocketTimeout(Duration.ofSeconds(20))` limits read wait time according to HTTP transport behavior.

These values illustrate a development setup, not defaults or universal recommendations for every system. Adjust them based on network latency, load, response size, and business requirements.

Configuration class names and packages may vary between Spring Data Elasticsearch generations. The example above uses the Java API Client configuration for corresponding Spring Data versions. For legacy projects using `AbstractElasticsearchConfiguration`, `RestHighLevelClient`, or another transport, use the API supported by your exact dependency version; do not mix configurations from two client types.

### Checking whether the configuration takes effect

After configuring, confirm the application actually creates its client from this bean/configuration:

- Verify the Spring context contains only the intended client configuration.
- Verify repositories and `ElasticsearchOperations` use the same configured client.
- Check client initialization logs and active environment settings.
- Check whether profiles, environment variables, or other beans override the configuration.

Creating a new client for every repository call defeats connection pooling and can open excessive connections. The client should follow the application lifecycle via Spring beans.

## 8. Customizing the underlying HTTP client

When finer control is needed over pool wait times or transport-specific settings, you may need to customize the HTTP client used by the Elasticsearch client.

In some Elasticsearch REST Client generations based on Apache HttpClient 4, lower-level configuration APIs expose concepts such as:

```java
requestConfigBuilder
    .setConnectTimeout(3_000)
    .setSocketTimeout(20_000)
    .setConnectionRequestTimeout(2_000);
```

This snippet merely illustrates setting names at the Apache HttpClient 4 layer. How this is wired into Spring Data depends on the version and callbacks it exposes. Versions using another transport have different APIs; do not copy this snippet into a project whose actual dependencies do not use Apache HttpClient 4.

Identify the exact dependencies in use—such as Elasticsearch Java API Client, Elasticsearch REST Client, Apache HttpClient, or Reactor Netty—and configure according to that transport's documentation. Avoid creating a second HTTP client while Spring Data continues using the original one, as the new settings will have no effect.

For reactive applications, transport may be managed by WebClient/Reactor Netty. In that case, examine limits separately, including connect timeout, response timeout, connection-provider pending acquire timeout, and cancellation. Do not assume imperative `withSocketTimeout` settings automatically apply to a reactive client.

## 9. How to choose timeout values

There is no single set of values suitable for every application. Selection should start with business time budgets and real measurements.

Suppose an API must respond within roughly 25 seconds. An illustrative allocation might look like:

| Stage | Illustrative Budget |
|---|---:|
| Waiting for a connection in the pool | 2 seconds |
| Establishing a new connection | 3 seconds |
| Waiting for response/read | 15–20 seconds |
| Processing result and returning response | Remaining time |

This is a conceptual example for budgeting, not an exact additive formula across every HTTP client. Because socket timeout may apply per read interval between incoming chunks, it does not necessarily equal total response transfer time.

Some practical guidelines:

1. **Connect timeout should be short enough to detect unreachable network targets quickly.** Opening a network connection normally does not need to wait as long as a complex search query.
2. **Socket/read timeout must fit the longest valid request.** Aggregations or large responses may need more time than point lookups by ID.
3. **Pool acquisition timeout should reflect acceptable wait time.** Long pool waits typically indicate high concurrency or undersized pooling.
4. **Overall deadline must include steps before and after Elasticsearch.** Never let the gateway expire before the application has a chance to return a controlled error.
5. **Do not raise every timeout at once.** If failures stem from an exhausted pool or slow queries, raising socket timeout may simply hold resources longer.

Measure latency percentiles such as p50, p95, and p99 under realistic load. The p99 metric helps surface slow tail requests. Combine these numbers with API SLAs, gateway limits, and cluster capacity when tuning timeouts.

## 10. Diagnosing timeout errors

When a timeout occurs, pinpoint which stage failed before changing configuration.

| Symptom or Exception | Likely Area | What to Check |
|---|---|---|
| `ConnectTimeoutException`, connect timed out | Establishing a new connection | Host, port, DNS, firewall, network route, node status. |
| `ConnectException: Connection refused` | Server not accepting connections | Whether Elasticsearch is running, port is right, and service is listening. |
| `SocketTimeoutException: Read timed out` | Waiting to read response | Query, cluster load, response size, network, proxy, and socket timeout. |
| Connection pool timeout / timeout waiting for connection | Waiting to acquire connection | Concurrency level, pool capacity, connection hold duration, and slow responses. |
| Reactor `TimeoutException` | Timeout in reactive chain or transport | Placement of `timeout(...)`, Reactor Netty config, and cancellation. |
| HTTP 429 | Server rejecting or throttling load | Cluster pressure, thread pools, request limits, and retry policy. |
| HTTP 502/503/504 | Gateway, proxy, or upstream service | Gateway logs, upstream health, per-layer deadlines, and Elasticsearch health. |

### An ordered investigation workflow

**Step 1 — Verify address and basic connectivity**

From the exact machine or container running the application, check hostname, port, DNS, protocol, and reachability. Verify Elasticsearch is ready to accept requests. If requests cannot even connect, do not investigate queries yet.

**Step 2 — Identify the root exception**

Spring may wrap HTTP client exceptions inside other exceptions. Inspect the full cause chain and stack trace logs to find the root error. Distinguish connect timeout, read timeout, pool timeout, DNS errors, and TLS errors.

**Step 3 — Compare timing across layers**

Record operation start/end timestamps in the application, HTTP wait time, Elasticsearch-side processing time where observable, and gateway timing. If the gateway times out after 15 seconds while the client timeout is 30 seconds, revisit the deadline hierarchy.

**Step 4 — Compare a simple request against the failing query**

Compare a lightweight call like cluster health or get-by-ID against the query timing out. If only a specific query is slow, inspect its mapping, query, aggregations, shard count, and response size.

**Step 5 — Inspect concurrency and pool utilization**

Observe active request counts, connection acquisition wait times, active/leased connections, and pending requests. If errors rise with concurrency, investigate pool sizing and load throttling.

**Step 6 — Adjust one variable and re-measure**

Change one timeout or performance variable at a time, then rerun the same load scenario. Compare latency, error rate, and client/cluster resources. This confirms which change actually improved the system.

## 11. Retrying on timeout

Retries can overcome transient network failures, but a timeout creates ambiguity: the client does not know whether the request reached the server and was executed.

For example, the application sends a document write. Elasticsearch receives and indexes it successfully, but the response is lost in transit. The client times out. If the application sends another write request, it could create duplicate records or apply the same effect twice.

Make clear distinctions:

- **Read requests** like searches or get-by-ID are generally safer to retry on transient failures, though retry count and total time must still be bounded.
- **Indexing a document with an explicit ID** can be designed to retry more safely when repeating the request overwrites the same document with desired semantics.
- **Creating a document with an auto-generated ID** can create duplicate documents on retry.
- **Bulk requests** can partially succeed. Inspect item-level responses to retry only eligible items rather than blindly resending the whole batch.
- **Scripted updates or increment/decrement operations** may not be idempotent. Retries can apply the mutation multiple times.

A retry policy needs a maximum attempt cap, exponential backoff, jitter, and a total retry budget. Never retry infinitely or in a tight immediate loop, as that amplifies load on an already stressed cluster.

Before retrying writes, confirm idempotency, document ID strategy, and whether the prior attempt might already have taken effect. A timeout represents an indeterminate outcome, not definitive proof of failure.

## 12. Common mistakes

- **Increasing only socket timeout on a connect timeout.** The errors occur in different stages; raising read timeout will not fix connection establishment failures.
- **Treating socket timeout as total request duration.** Many transports enforce it as a read-wait limit, not an end-to-end deadline.
- **Ignoring pool acquisition wait time.** Requests can time out before ever sending bytes to Elasticsearch because no connection was available from the pool.
- **Setting gateway timeouts shorter or longer than inner layers without coordination.** External clients may give up while server work continues holding resources.
- **Creating a new Elasticsearch client per operation.** This undermines connection reuse and can spawn excessive connections.
- **Retrying all write operations after timeout.** The server may already have processed the request before the response was lost.
- **Using Elasticsearch-side timeouts instead of network timeouts.** Search timeouts do not replace connect or socket timeouts.
- **Setting excessively long timeouts to hide slow queries.** Requests hold threads and connections longer, degrading service capacity for other requests.

## 13. Configuration and operations checklist

When deploying a Spring Data Elasticsearch client, verify:

- Cluster addresses, ports, HTTP/HTTPS, authentication, and TLS match the environment.
- The client is managed by Spring and reused across operations.
- Connect timeout suits the network environment.
- Socket/read timeout matches expected processing duration and response sizes.
- Pool acquisition timeout is reviewed if configurable on the transport.
- Deadlines across the application, gateway, and related services are aligned.
- Reactive and imperative clients are configured for their respective transports.
- Logs capture root exception types and request durations.
- Metrics track latency, timeout rates, concurrency, and connection pool health.
- Retries are bounded and safe for the operation types involved.

## 14. Quick reference table

| Question | Timeout to Check |
|---|---|
| Cannot open a connection to Elasticsearch | Connect timeout |
| Request waits for an available connection in the pool | Connection-pool acquisition timeout |
| Request sent, waiting too long for response | Socket/read timeout |
| Want to bound total operation duration at the application layer | Request deadline / application timeout |
| Want to cap execution time of a Search query on Elasticsearch | Search API timeout |
| External request expires before backend finishes | Gateway and inner-layer deadlines |

Connect timeout, socket timeout, and request deadlines bound different stages. When Spring Data Elasticsearch reports a timeout, determine whether the request was waiting for a pool connection, establishing a connection, reading a response, or awaiting the entire business flow. From there, choose the right configuration point, investigate root causes, and decide whether to retry or optimize the query.
