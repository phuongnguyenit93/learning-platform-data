# Managing RSocket Connection Counts and Load Distribution by Application Model

RSocket supports multiple concurrent requests over a single connection. Therefore, request count does not equal TCP connection count: one `RSocketRequester` can send multiple Request-Response, Request-Stream, Request-Channel, and Fire-and-Forget interactions concurrently over an established connection. Creating a new requester or a new TCP connection for every request usually increases handshake, socket, keepalive, and memory overhead without adding proportional processing capacity.

As a system scales, choose a connection model based on how the application communicates: a client bound to one backend, many clients distributed through a network-layer load balancer, a single client distributing individual requests across multiple backends, or an RSocket session pinned to one specific instance. Each model manages connections, state, and retries differently.

This lesson focuses on Spring Framework `RSocketRequester` and RSocket Java load balancing. Examples use Java 17, Spring Framework 7.0.8, and RSocket Java 1.1.5.

## 1. Connection, Request, and Stream Are Three Distinct Concepts

An RSocket connection is established over TCP, WebSocket, or another transport. After `SETUP`, both peers can initiate interactions over the same connection. RSocket multiplexes multiple streams over a single transport connection, each with its own stream ID and lifecycle.

- Connection is the physical/logical channel between two RSocket endpoints. It holds handshake state, keepalive, setup state, metadata MIME types, and close state.
- Request is an interaction such as Request-Response or Fire-and-Forget. A request may create a stream on the connection.
- Stream is the data flow of a Request-Stream or Request-Channel. Multiple streams can run concurrently on one connection; backpressure is applied per stream.

Consequently, having 2,000 pending requests in a service does not mean the application needs 2,000 TCP connections. One RSocket connection can carry many concurrent interactions. Practical limits depend on CPU, network, active stream count, buffers, payload size, latency, and server processing capacity.

Diagram:

~~~text
Client process
  |
  +-- RSocketRequester (service A)
  |      |
  |      +-- one shared RSocket connection
  |              +-- request-response stream 1
  |              +-- request-response stream 2
  |              +-- request-stream 3
  |              +-- request-channel 4
  |
  +-- RSocketRequester (service B)
         |
         +-- another shared RSocket connection
~~~

An `RSocketRequester` is a request-sending abstraction. It is not equivalent to a single request and should not be constructed anew on every API call.

## 2. Default: One Requester Shares One Connection

For a fixed endpoint, Spring provides a simple way to create a requester:

~~~java
RSocketRequester requester = RSocketRequester.builder()
        .tcp("orders.internal", 7000);
~~~

Or using WebSocket:

~~~java
RSocketRequester requester = RSocketRequester.builder()
        .websocket(URI.create("wss://orders.example.com/rsocket"));
~~~

Both create an `RSocketRequester` that shares one connection for concurrent requests. The connection is established lazily on the first request; if the connection drops, subsequent requests can trigger re-establishing the connection. This does not mean an in-flight stream is seamlessly migrated to the new connection. Active streams can receive errors when the old connection closes.

In a Spring Boot application, you can create the requester once and inject it into services:

~~~java
@Configuration
class RSocketClientConfig {

    @Bean
    RSocketRequester ordersRequester(RSocketRequester.Builder builder) {
        return builder.tcp("orders.internal", 7000);
    }
}

@Service
class OrdersClient {
    private final RSocketRequester requester;

    OrdersClient(RSocketRequester ordersRequester) {
        this.requester = ordersRequester;
    }

    Mono<OrderReply> find(String orderId) {
        return requester.route("orders.find")
                .data(orderId)
                .retrieveMono(OrderReply.class);
    }
}
~~~

Do not create a requester inside every `find()` call. Reusing the requester lets multiple requests share the connection and keeps codecs, MIME types, setup metadata, and connector settings consistent.

`RSocketRequester.Builder` is a stateful builder. In Spring Boot, the `Builder` bean is prototype-scoped so each injection point gets its own builder. Configure a builder and construct a requester per remote service or per connection policy; do not share a single builder and repeatedly mutate setup/metadata across different requesters.

When the application owns a requester, dispose of it when the application stops or when its owning component is destroyed. Do not dispose after a single request because other requests may still be using the connection.

## 3. When Are Multiple Connections Needed?

Multiple connections are useful when a single connection becomes a measured bottleneck, when workloads need isolation, or when requests must be distributed across multiple backends. They also increase operational overhead.

Each connection typically maintains state on both client and server: sockets/file descriptors, buffers, keepalives, event-loop registrations, protocol state, and session context. With TLS or connection-level authentication, there is also handshake cost and security state. Too many connections can increase memory, CPU, file descriptor count, and heartbeat traffic.

Common models:

| Application Model | Usually Suitable Connection Approach | Reason |
|---|---|---|
| One client service calling a fixed backend | One requester sharing one connection | Multiplexes many requests with low overhead |
| Many independent clients calling a cluster | One connection per client through a TCP/L4 load balancer | Backends are distributed at connection creation; clients do not connect to every node |
| One client distributing requests across multiple instances | Client-side load balancing with multiple targets | Selects an RSocket from the pool for each interaction |
| Client requiring session pinned to a backend | One connection with affinity or session-based routing | Prevents sending session requests to a different instance |
| Long-lived streams and short requests contending | Separate requesters/pools per workload when contention is proven | Isolates latency and resources |
| Server needing to send requests back to a connected client | Keep a requester bound to that client's connection | The connection serves as the communication session identity |

There is no universal optimal connection count for every system. Start with one shared connection, measure latency, throughput, pending streams, CPU, and network; add connections only when evidence shows a single connection is the limiting factor.

## 4. Estimating Connection Counts by Topology

Calculate connection counts from the number of processes/clients and the distribution model:

- With one fixed requester per client process, connection count is close to the number of active client processes, plus separate admin/health connections if any.
- With client-side load balancing, one requester maintains a pool of RSockets to multiple targets. As the target count grows, connections maintained by each client can also grow with active targets.
- With N client processes and M backend targets, do not assume a client-side pool creates only N connections. Build capacity estimates from the actual pool; if every client holds a connection to every target, counts can approach N × M.
- With an L4 load balancer or service VIP, each client may hold only one connection at a time; the load balancer spreads different connections across different backends.

Illustrative example: 20,000 clients, each holding one connection through an L4 LB, create roughly 20,000 client-side connections to the cluster. If each client holds one connection to 8 backends in a client-side pool, scale can approach 160,000 connections. This is a topology calculation example, not measurements from a specific deployment.

Spring's `RSocketRequester.Builder` does not expose a generic pool-size `maxConnections` property. Its `transports()` method uses `LoadbalanceRSocketClient` and a list of `LoadbalanceTarget` instances to manage RSocket targets. `LoadbalanceRSocketClient`'s builder lets you configure the connector and strategy; if a requirement calls for a fixed number of multiple TCP connections to the exact same host, design a custom pool/client or multiple deliberate requesters, then measure and manage each connection's lifecycle.

## 5. Network-Layer vs. Client-Side Load Balancing

### 5.1. Network-Layer Load Balancing

A client connects to a service hostname or VIP:

~~~text
Client
  |
  | one TCP/WebSocket connection
  v
L4 load balancer / service VIP
  |
  +---- backend A
  +---- backend B
  +---- backend C
~~~

The load balancer typically picks a backend when the TCP connection is established. Because RSocket multiplexes many request streams over the same connection, requests on that connection generally continue going to the same backend. This is per-connection distribution, not automatic per-request distribution.

This model fits a very large number of clients where each client maintains a steady session or connection. The load balancer spreads connections across instances. If the application needs connection-level affinity, retain matching stickiness settings.

### 5.2. Client-Side Load Balancing

Spring provides an API for a single `RSocketRequester` to select across multiple targets:

~~~java
RSocketRequester requester = RSocketRequester.builder()
        .transports(targetPublisher, new RoundRobinLoadbalanceStrategy());
~~~

`targetPublisher` emits lists of `LoadbalanceTarget`. Each target has a unique identifying key and a `ClientTransport`. `LoadbalanceRSocketClient` maintains a pool of RSockets and uses a `LoadbalanceStrategy` to pick an RSocket for each interaction.

`RoundRobinLoadbalanceStrategy` rotates sequentially across RSockets in the pool. `WeightedLoadbalanceStrategy` selects based on availability and RSocket usage/latency statistics. The weighted strategy does not simply read pod CPU; it uses connection availability and usage stats observed by the client.

For Request-Response, each interaction is sent over the selected RSocket. For Request-Stream or Request-Channel, the entire created stream stays bound to the RSocket selected for that interaction; items within a stream are not redistributed across backends.

## 6. Creating a Static Target List

Example with two TCP backends:

~~~java
List<LoadbalanceTarget> targets = List.of(
        LoadbalanceTarget.from(
                "orders-a",
                TcpClientTransport.create("orders-a.internal", 7000)),
        LoadbalanceTarget.from(
                "orders-b",
                TcpClientTransport.create("orders-b.internal", 7000))
);

RSocketRequester requester = RSocketRequester.builder()
        .transports(Flux.just(targets), new RoundRobinLoadbalanceStrategy());
~~~

The `rsocket-transport-netty` dependency is required to use `TcpClientTransport`. Each `LoadbalanceTarget` key must uniquely identify the target. If an instance's DNS/IP/port changes, update the target list with a new key matching service discovery.

Use `Flux.just(targets)` when the topology is static over the requester's lifetime. For clusters that change due to autoscaling, rolling deployments, or discovery updates, provide a `Publisher` that emits fresh snapshots.

## 7. Updating Targets from Service Discovery

`RSocketRequester.Builder.transports` accepts a `Publisher<List<LoadbalanceTarget>>`; the list can be refreshed periodically. This is the integration point for Eureka, Consul, Kubernetes, or another discovery service.

Illustrative example using `ReactiveDiscoveryClient` and TCP transport:

~~~java
Flux<List<LoadbalanceTarget>> targetUpdates =
        Flux.interval(Duration.ZERO, Duration.ofSeconds(5))
                .concatMap(tick -> discoveryClient.getInstances("orders")
                        .map(instance -> LoadbalanceTarget.from(
                                instance.getHost() + ":" + instance.getPort(),
                                TcpClientTransport.create(
                                        instance.getHost(), instance.getPort())))
                        .collectList()
                        .onErrorResume(error -> {
                            log.warn("Could not refresh RSocket targets", error);
                            return Mono.empty();
                        }));

RSocketRequester requester = builder
        .transports(targetUpdates, WeightedLoadbalanceStrategy.create());
~~~

This snippet is an integration pattern; it requires Spring Cloud Discovery and `rsocket-transport-netty`. When discovery succeeds with zero instances, `collectList()` emits an empty list. When discovery fails, `Mono.empty()` keeps the update publisher alive without replacing the current snapshot with a failure. Depending on operational requirements, you may choose a fail-fast policy if zero targets remain.

A publisher for dynamic topology must stay alive and emit new snapshots. If you use `Flux.just(initialTargets)` and the publisher completes, the client will receive no updates when backends disappear or reappear. The pool can run dry if all nodes are removed and no further updates arrive.

Distinguish two events:

- A backend is temporarily unresponsive while still listed in discovery.
- A backend has been removed from discovery and no longer appears in the new target list.

Health checks, discovery TTL, and polling intervals determine how fast clients detect changes. Polling too frequently loads the registry; polling too slowly prolongs stale targets. If the registry offers a watch/event stream, prefer event-driven updates over polling.

## 8. Choosing Round Robin or Weighted?

| Strategy | Selection Method | Best Suited When |
|---|---|---|
| `RoundRobinLoadbalanceStrategy` | Cycles sequentially through RSockets in the pool | Backends are relatively homogeneous and simple distribution is desired |
| `WeightedLoadbalanceStrategy` | Based on availability and usage statistics | Backends differ in capacity or latency and busy targets should be avoided |

Round robin does not guarantee each backend receives the same bytes or CPU time. One 10-minute stream can consume far more resources than hundreds of short request-responses. Round robin is purely a connection-selection strategy per interaction, not an exact business-cost balancing algorithm.

The weighted strategy can leverage availability, pending request counts, and latency statistics to pick an appropriately weighted RSocket. When the server supports leasing, availability can reflect admission capacity. Do not treat the weighted strategy as a replacement for autoscaling, quotas, or application-level admission control.

When choosing a strategy, measure request distribution, p95/p99 latency, pending requests, and stream durations per target. If backends are identical and workloads uniform, round robin is usually predictable. If load and latency vary significantly, evaluate weighted via benchmarking.

## 9. Affinity and Per-Connection State

RSocket is a bidirectional protocol. After `SETUP`, either side can send requests to the other. The server can hold per-connection state or use `@ConnectMapping` to handle `SETUP` and create a session context. In that case, a connection can represent a client session.

If a client-side load balancer sends the first request to backend A and the next request to backend B, backend B may lack the session state created on A. Cases requiring special care:

- Authentication or session metadata processed only during `SETUP`.
- Server keeping subscriptions or client state in memory per connection.
- Server sending reverse requests to the client over the connection-bound requester.
- Requests needing temporary data that exists on only one backend.
- Long-lived streams requiring consistent producer/consumer state throughout their lifetime.

If requests require affinity, use a dedicated requester/connection pinned to the right backend or sticky routing. If you want per-request load balancing, business state must live in a shared store or be designed statelessly. Do not use a client-side pool if switching backends breaks session context.

Session resumption is also not a load-balancing mechanism. Resumption requires matching session state at the receiving endpoint; it does not automatically migrate an active session to any new backend in the cluster. When moving across nodes is needed, build an explicit session/state strategy.

## 10. Connection Lifecycle, Keepalive, and Cleanup

A connection lifecycle covers transport creation, `SETUP`, requests/streams, keepalive, and close. Define clearly which component owns the requester and which is responsible for disposing it.

Principles:

- Create one requester per remote service and connection policy.
- Do not create a new requester on every `route()` call.
- Do not dispose a requester when a single request finishes.
- Dispose the requester when the application context or owning component stops.
- Set keepalive intervals and max lifetimes compatible with network timeouts and server policies.
- Monitor connection close and reconnect; active streams can fail when a connection closes.
- When using a dynamic target publisher, stop the publisher and requester together on application shutdown.
- Set timeouts on requests and streams; do not keep connections or streams open indefinitely unless business logic requires it.

Spring lets you configure `RSocketConnector` via the `rsocketConnector()` callback on `Builder`. There you can customize keepalive, session resumption, interceptors, and low-level options. Keep settings consistent across all targets in a pool because the same connector template is used to connect to targets.

## 11. Backpressure and Leasing Are Not Connection Pools

Backpressure regulates data emission speed per stream. The requester asks for elements via `request(n)`; the responder must respect demand. This protects slow stream consumers from being flooded by fast producers, but it does not limit total TCP connections in the application.

RSocket Leasing is an extension allowing one peer to advertise how many requests the other peer may initiate within a time window. It helps with admission control or protecting an overloaded server. Leasing throttles accepted requests on a connection; it does not replace load balancing across backends and does not cap client connection counts.

They can be combined:

- Load balancing chooses an RSocket target for an interaction.
- Backpressure regulates stream data flow rate.
- Leasing caps new requests according to peer admission capacity.
- Application-level rate limits/quotas enforce per-user, per-tenant, or business limits.

Do not open extra connections just to bypass leasing or backpressure. Determine whether the server is limiting due to resources, quotas, or protection policies.

## 12. Retries and Failover on Connection Failure

If a connection drops, in-flight interactions on that connection may fail. New requests may go over a new connection or another target depending on the requester and pool. A request failing does not prove the server never processed it: the server may have committed side effects while the response was lost.

Retries must follow the business contract:

- Read requests can usually be retried on transient failures if timeouts and load permit.
- Write requests need an idempotency key or operation ID to prevent duplicate writes.
- Fire-and-Forget has no business response; send completion does not confirm the handler finished processing.
- Active streams need an explicit resume/restart policy; retrying an entire stream can replay data or side effects.
- Use backoff, jitter, retry caps, and appropriate circuit breakers.
- Do not retry validation errors, authentication failures, or non-transient business errors.

Example retry for an idempotent read operation:

~~~java
Mono<Order> order = requester.route("orders.find")
        .data(orderId)
        .retrieveMono(Order.class)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(200))
                .filter(this::isTransientTransportFailure));
~~~

This snippet illustrates retrying a read query. `isTransientTransportFailure` is an application error-classification policy; do not retry every `Throwable`. For write operations, pass a stable operation ID to the server and ensure idempotent server handling before enabling retries.

## 13. Java 17 Example: Distributing Requests Across Two Targets

The following example creates two RSocket servers over `LocalTransport`, each returning a distinct node name. A single `RSocketRequester` uses `transports()` and `RoundRobinLoadbalanceStrategy` to distribute 12 requests. The test verifies both targets receive requests.

### 13.1. Maven Dependencies

Minimal POM to run the test with Java 17:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>rsocket-load-balance-test</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <spring.version>7.0.8</spring.version>
    <rsocket.version>1.1.5</rsocket.version>
    <junit.version>5.12.2</junit.version>
    <reactor.version>3.8.7</reactor.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-messaging</artifactId>
      <version>${spring.version}</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>${spring.version}</version>
    </dependency>
    <dependency>
      <groupId>io.rsocket</groupId>
      <artifactId>rsocket-core</artifactId>
      <version>${rsocket.version}</version>
    </dependency>
    <dependency>
      <groupId>io.rsocket</groupId>
      <artifactId>rsocket-transport-local</artifactId>
      <version>${rsocket.version}</version>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <version>${reactor.version}</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>${junit.version}</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
        <configuration><release>17</release></configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.3</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 13.2. Complete Test

Save as `src/test/java/example/RSocketLoadBalanceTest.java`:

~~~java
package example;

import java.time.Duration;
import java.util.List;

import io.rsocket.core.RSocketServer;
import io.rsocket.loadbalance.LoadbalanceTarget;
import io.rsocket.loadbalance.RoundRobinLoadbalanceStrategy;
import io.rsocket.transport.local.LocalClientTransport;
import io.rsocket.transport.local.LocalServerTransport;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RSocketLoadBalanceTest {

    static final class NodeA {
        @MessageMapping("node")
        public String node() {
            return "node-a";
        }
    }

    static final class NodeB {
        @MessageMapping("node")
        public String node() {
            return "node-b";
        }
    }

    private Disposable startServer(String name, Object handler) {
        RSocketStrategies strategies = RSocketStrategies.create();
        RSocketMessageHandler messageHandler = new RSocketMessageHandler();
        messageHandler.setRSocketStrategies(strategies);
        messageHandler.setHandlers(List.of(handler));
        messageHandler.afterPropertiesSet();

        return RSocketServer.create(messageHandler.responder())
                .bind(LocalServerTransport.create(name))
                .block(Duration.ofSeconds(5));
    }

    @Test
    void balancesRequestsAcrossTwoTargets() {
        String targetA = "load-balance-a";
        String targetB = "load-balance-b";
        Disposable serverA = startServer(targetA, new NodeA());
        Disposable serverB = startServer(targetB, new NodeB());

        RSocketRequester requester = RSocketRequester.builder()
                .transports(
                        Flux.just(List.of(
                                LoadbalanceTarget.from(targetA,
                                        LocalClientTransport.create(targetA)),
                                LoadbalanceTarget.from(targetB,
                                        LocalClientTransport.create(targetB)))),
                        new RoundRobinLoadbalanceStrategy());

        try {
            StepVerifier.create(Flux.range(0, 12)
                            .flatMap(index -> requester.route("node")
                                    .retrieveMono(String.class))
                            .collectList())
                    .assertNext(results -> {
                        assertEquals(12, results.size());
                        assertTrue(results.contains("node-a"));
                        assertTrue(results.contains("node-b"));
                    })
                    .expectComplete()
                    .verify(Duration.ofSeconds(10));
        }
        finally {
            requester.dispose();
            serverA.dispose();
            serverB.dispose();
        }
    }
}
~~~

The test uses `LocalTransport`, so it opens no TCP ports. It still exercises the real RSocket protocol, `RSocketRequester`, and `RSocketMessageHandler`. This test proves client-side target selection works; it does not test a TCP load balancer, TLS, or service discovery.

Run:

~~~bash
mvn test
~~~

Surefire output:

~~~text
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
~~~

In a real environment, replace `LocalClientTransport` with `TcpClientTransport` or `WebsocketClientTransport` and feed target lists from discovery. Add integration tests for disappearing targets, newly appearing targets, connection closures, and retries.

## 14. Measuring and Tuning Connection Counts

Before increasing connection counts, collect a baseline:

- Active connections per client instance and per backend.
- Pending streams/requests per connection.
- Request rate and bytes/sec per backend.
- p50/p95/p99 latency and timeout/error rates.
- CPU, memory, direct memory, file descriptors, and network throughput.
- Keepalive traffic and reconnect counts.
- Target count in the pool and how often targets are removed/re-added.

A practical tuning workflow:

1. Start with one requester and one shared connection.
2. Increase request concurrency while keeping connection count constant.
3. Observe CPU, network, latency, and pending streams.
4. If one connection saturates, test splitting workloads or adding connections carefully.
5. If distributing across multiple backends is required, compare L4 load balancing against client-side `transports()`.
6. Run mixed loads with both short requests and long-lived streams to inspect fairness.
7. Test during backend restarts, discovery changes, and flaky networking.
8. Choose the smallest connection count that meets target throughput and latency with sufficient headroom.

Do not use concurrent request count as the sole reason to add connections. RSocket multiplexing and backpressure can handle many streams on one connection; the real bottleneck may be handler CPU, the database, event loops, or downstream dependencies.

## 15. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Creating an `RSocketRequester` per request | Handshake/connection churn, wasted sockets and memory | Reuse one requester per remote service |
| Assuming one requester serves only one request | Creating far too many unnecessary connections | Use a shared connection and multiplexing |
| Using one VIP and expecting each request to hit a different backend | Multiple streams on one connection usually hit the same backend | Use client-side `transports()` if per-interaction distribution is needed |
| Every client connecting to every backend despite huge client counts | Connection count can approach clients × targets | Use an L4 LB or gateway when appropriate |
| Using `Flux.just()` for dynamic discovery | No new snapshots after the publisher completes | Use a periodically refreshing publisher or watch stream |
| Unstable or duplicate target keys | Pool struggles to track target changes | Use unique instance IDs or endpoint keys |
| Using Round Robin for very long streams and expecting balanced bytes | One heavy stream can pin load on one backend for a long time | Measure stream duration/cost, consider weighted or workload isolation |
| Load-balancing requests for a locally stateful session | Later requests can hit a node without state | Use sticky routing or shared session state |
| Retrying every request on connection failure | Can execute side effects multiple times | Idempotency keys, selective retries, and backoff |
| Treating Leasing as a connection pool | Confusing request caps with socket caps | Use leasing for admission control; manage connections separately |
| Not disposing the requester | Connections, timers, and resources may linger after shutdown | Manage ownership and dispose along lifecycle boundaries |

## 16. Design Checklist

- Each remote service has a reused requester.
- Connection counts are sized from client process counts and target pool models.
- Decided between per-connection vs. per-interaction load balancing.
- If using a client-side pool, the target publisher updates properly on discovery changes.
- Target keys are stable and unique identifiers.
- Round Robin or Weighted is chosen based on workload and measured metrics.
- Session/connection affinity is preserved when the application relies on per-connection state.
- Backpressure, leasing, and application rate limits are used for their intended purposes.
- Retries apply only to transient failures and safe/idempotent operations.
- Connection counts, active streams, pending requests, latency, and reconnects are observed.
- Requesters, pools, and target publishers are disposed on application shutdown.
- Integration tests cover target distribution, target removal/addition, and connection failures.

## References

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework API — RSocketRequester.Builder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html)
- [RSocket Java API — LoadbalanceRSocketClient](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/loadbalance/LoadbalanceRSocketClient.html)
- [RSocket Java API — LoadbalanceTarget](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/loadbalance/LoadbalanceTarget.html)
- [RSocket Java API — RoundRobinLoadbalanceStrategy](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/loadbalance/RoundRobinLoadbalanceStrategy.html)
- [RSocket Java API — WeightedLoadbalanceStrategy](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/loadbalance/WeightedLoadbalanceStrategy.html)
- [RSocket — Frequently Asked Questions](https://rsocket.io/about/faq/)
