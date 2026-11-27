# Routing Queries to the Instance Holding the Appropriate State Store

Kafka Streams partitions the data of a stateful application across multiple partitions. When the application runs across multiple instances, each instance holds only the subset of state stores corresponding to the partitions it owns. A key-based query must therefore reach the specific instance holding that key's partition. Calling the local state store on an arbitrary instance may return null or find no data even though the key exists on another instance.

Kafka Streams provides Interactive Queries to read local state stores and look up metadata about which instance holds a key. The Spring Cloud Stream Kafka Streams Binder wraps these APIs in `InteractiveQueryService`. Applications use metadata to decide whether to read directly within the JVM or forward the query over the network to the data-owning instance.

## 1. Why Is Query Routing Needed?

Suppose a topology builds the `order-summary-store` state store from the `orders.events` topic. The topic has six partitions and the application runs three instances. Kafka Streams distributes tasks and partitions across the instances:

~~~text
Kafka topic: orders.events
Partitions:  0   1   2   3   4   5
             |   |   |   |   |   |
             +---+---+   +---+---+
                 |           |
          Instance A    Instance B    Instance C
          P0, P1        P2, P3         P4, P5
          local store   local store    local store
~~~

Each instance holds one slice of the state store data. If a lookup request for `orderId=ORD-2005` arrives at Instance A while that key belongs to a partition managed by Instance C, A's local store will not have the result. The application must locate the instance owning the key and route the query there.

There are two separate parts:

- **Discovery:** finding which instance holds the key in a given state store.
- **RPC:** calling that instance over HTTP, gRPC, or another internal protocol to read its local state store.

Kafka Streams provides discovery metadata, but does not automatically create REST endpoints or forward requests between instances. The application must implement the appropriate network communication layer.

## 2. Interactive Queries Only Read Local State

Interactive Queries let an application query state stores materialized by the topology. For a key-value store, the read API typically uses `ReadOnlyKeyValueStore`; for a window store or session store, use the corresponding store type.

The state store must have a stable name to be queryable. For instance, when aggregating a stream by key, declare the store name with `Materialized.as(...)`:

~~~java
import java.util.function.Function;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.kstream.Grouped;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KTable;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.state.KeyValueStore;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderEvent(String orderId, String status, long amountDeltaMinorUnits) {}

record OrderSummary(long totalMinorUnits, String latestStatus) {
    static OrderSummary empty() {
        return new OrderSummary(0L, "NEW");
    }

    OrderSummary apply(OrderEvent event) {
        return new OrderSummary(
                totalMinorUnits + event.amountDeltaMinorUnits(),
                event.status());
    }
}

@Configuration
class OrderSummaryTopology {

    @Bean
    Function<KStream<String, OrderEvent>, KTable<String, OrderSummary>>
    orderSummary(OrderEventSerde orderEventSerde,
                 OrderSummarySerde orderSummarySerde) {

        return orders -> orders
                .groupByKey(Grouped.with(
                        Serdes.String(),
                        orderEventSerde))
                .aggregate(
                        OrderSummary::empty,
                        (orderId, event, current) -> current.apply(event),
                        Materialized.<String, OrderSummary,
                                KeyValueStore<Bytes, byte[]>>as(
                                        "order-summary-store")
                                .withKeySerde(Serdes.String())
                                .withValueSerde(orderSummarySerde));
    }
}
~~~

`OrderEventSerde` and `OrderSummarySerde` are application-provided Serdes. The example focuses on the store name and key/value types; configure Serdes matching your topic's actual schemas.

Enable the function and map bindings:

~~~yaml
spring:
  cloud:
    function:
      definition: orderSummary
    stream:
      bindings:
        orderSummary-in-0:
          destination: orders.events
        orderSummary-out-0:
          destination: orders.summary
~~~

The binder creates the `orderSummary-in-0` input binding for the input topic. `Materialized.as("order-summary-store")` sets the queryable state store name. When the application starts, Kafka Streams builds the store and updates it from topology records.

Reading a key on the current instance:

~~~java
import org.apache.kafka.streams.state.QueryableStoreTypes;
import org.apache.kafka.streams.state.ReadOnlyKeyValueStore;

ReadOnlyKeyValueStore<String, OrderSummary> store =
        interactiveQueryService.getQueryableStoreType(
                "order-summary-store",
                QueryableStoreTypes.keyValueStore());

OrderSummary summary = store.get("ORD-2005");
~~~

This is a local query. The API does not automatically look up data on another instance. State stores are queried in read-only mode; data mutations must flow through the topology and input topics, never written directly into the store from a REST controller.

## 3. The Kafka Streams Binder's InteractiveQueryService

The Spring Cloud Stream Kafka Streams Binder provides `InteractiveQueryService` as a Spring bean. Applications can inject this service to:

- Obtain a local store via `getQueryableStoreType(...)`.
- Find the host holding a key via `getHostInfo(store, key, serializer)`.
- Obtain the current instance's host via `getCurrentHostInfo()`.
- Retrieve `KeyQueryMetadata` via `getKeyQueryMetadata(store, key, serializer)`.
- Obtain the corresponding `KafkaStreams` instance via `getKafkaStreams(store, key, serializer)`.

Constructor injection example:

~~~java
import org.springframework.cloud.stream.binder.kafka.streams.InteractiveQueryService;
import org.springframework.stereotype.Service;

@Service
class OrderQueryMetadata {

    private final InteractiveQueryService interactiveQueryService;

    OrderQueryMetadata(InteractiveQueryService interactiveQueryService) {
        this.interactiveQueryService = interactiveQueryService;
    }
}
~~~

Do not confuse the Kafka Streams Binder's `InteractiveQueryService` with Spring for Apache Kafka's `KafkaStreamsInteractiveQueryService`. The two classes belong to different integrations; in an application using the Spring Cloud Stream Kafka Streams Binder, use the API provided by the binder.

## 4. Declaring application.server on Each Instance

Kafka Streams needs to know the network address each instance uses to receive queries from other instances. Configuring `application.server` publishes a host/port pair for the instance's RPC endpoint:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            applicationId: order-summary-v1
            brokers: localhost:9092
            configuration:
              application.server: ${QUERY_HOST:localhost}:${QUERY_PORT:8080}
~~~

In a multi-instance environment:

- `applicationId` must be identical across replicas of the same Kafka Streams application so they belong to the same logical application.
- `application.server` must differ for each running instance, pointing to an address directly reachable from the remaining instances.
- The application's HTTP or RPC server must actually listen on the advertised address/port.
- The hostname must resolve on the internal network; the port must be open through network policies, security groups, or matching infrastructure rules.

For example, three pods might advertise `order-stream-0.internal:8080`, `order-stream-1.internal:8080`, and `order-stream-2.internal:8080` respectively. Sharing the same port is normal if each pod has its own hostname/IP.

The `localhost` placeholder value is only for running a single instance on a developer machine. Production must supply a distinct `QUERY_HOST` and `QUERY_PORT` per replica; if every instance advertises `localhost`, metadata will point to the wrong process.

`application.server` is neither `bootstrap.servers` nor does it start a web server by itself. `bootstrap.servers` is the Kafka broker address; `application.server` is the RPC address the instance uses to serve state queries. Do not put a shared load balancer across all instances if that load balancer can send requests to an arbitrary pod: metadata must identify the exact instance owning the partition.

## 5. Key-Based Query Routing Flow

An endpoint receiving queries can execute these steps:

1. Receive the key and the state store name to read.
2. Use `getHostInfo(...)` to find the host owning the key.
3. Call `getCurrentHostInfo()` to identify the current instance.
4. If both hosts match, read the local state store directly.
5. If the host differs, call the internal endpoint on that host.
6. If metadata is not ready yet or the host is no longer reachable, return a retryable error or refresh metadata within bounded retries.

~~~mermaid
flowchart TD
    A[Request: orderId] --> B[InteractiveQueryService.getHostInfo]
    B --> C{Owner metadata available?}
    C -->|No| D[Bounded retry or return 503]
    C -->|Yes| E{Owner is current instance?}
    E -->|Yes| F[Read local state store]
    E -->|No| G[Call RPC to owner]
    G --> H{Owner still holds partition?}
    H -->|Yes| I[Return result]
    H -->|No| J[Refresh metadata and retry once]
    F --> I
~~~

Do not broadcast a query to every instance and take the first answer. That amplifies network load, forces many instances to check stores that do not own the key, and masks routing bugs. Use key-based metadata to pick the exact owner before querying.

## 6. Finding the Host Holding a Key

For a `String` key, use the corresponding serializer:

~~~java
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.state.HostInfo;

HostInfo owner = interactiveQueryService.getHostInfo(
        "order-summary-store",
        "ORD-2005",
        Serdes.String().serializer());

HostInfo current = interactiveQueryService.getCurrentHostInfo();
~~~

`owner` is the host managing the key according to Kafka Streams metadata; `current` is the host of the instance handling the request. If both are equal, read the local store. If they differ, send the query to `owner.host()` and `owner.port()`.

The serializer must match the key type and how keys are serialized in the topology. For example, if keys are `Long`, use `Serdes.Long().serializer()`. Do not pass a `String` serializer for a `Long` key or alter key normalization between producers and the query service.

Metadata is computed based on Kafka Streams' partitioning strategy. If the topology uses a custom partitioner, ensure partition lookup for queries matches the real partitioner. Kafka Streams offers `metadataForKey` overloads accepting a `StreamPartitioner` when a custom partitioning algorithm must be specified; do not assume a default serializer always describes a custom partitioner.

## 7. Distinguishing Active Host, Standby Hosts, and Partition

The `getKeyQueryMetadata(...)` API returns a `KeyQueryMetadata` containing:

- `activeHost`: the instance currently holding the partition and authoritative for the key's data.
- `standbyHosts`: instances holding standby replicas of the state store if standby tasks are configured.
- `partition`: the partition corresponding to the key in the state store.

This is a point-in-time snapshot of metadata. During rebalances or instance shutdowns, the active host can change. Normal read paths should route to `activeHost`.

In the lower-level Kafka Streams API, `KeyQueryMetadata.NOT_AVAILABLE` signals that metadata cannot currently be determined, typically during a rebalance. When encountering this state, do not read `activeHost`; perform a bounded retry or return a transient status to the caller.

Standby hosts can help reduce service disruption when an active host fails, yet standby data may lag behind the latest records. Only read from standby hosts when business rules tolerate stale reads and the application configures query policies for stale stores. Never silently fall back to a standby instead of the active host and treat the result as up to date.

## 8. Configuring an Internal Endpoint for Remote Queries

Kafka Streams only provides host metadata. The application must expose a network endpoint for other instances to call. A clean design separates two kinds of endpoints:

- Public endpoint receiving queries from API clients and performing discovery/routing.
- Internal endpoint reading only the local state store on the called instance.

Example interface for network communication:

~~~java
import org.apache.kafka.streams.state.HostInfo;

interface RemoteOrderStateClient {
    OrderSummary fetch(HostInfo owner, String orderId);
}
~~~

Implement the interface with an HTTP client, gRPC client, or internal RPC mechanism. Obtain the target address from `HostInfo`; never construct hostnames from pod names or pick a random replica.

Example HTTP client implementation using `RestClient` in Spring Framework 6.1+:

~~~java
import org.apache.kafka.streams.state.HostInfo;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class HttpRemoteOrderStateClient implements RemoteOrderStateClient {

    private final RestClient restClient;

    HttpRemoteOrderStateClient(RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    @Override
    public OrderSummary fetch(HostInfo owner, String orderId) {
        return restClient.get()
                .uri(uriBuilder -> uriBuilder
                        .scheme("http")
                        .host(owner.host())
                        .port(owner.port())
                        .path("/internal/state/orders/{orderId}")
                        .build(orderId))
                .retrieve()
                .body(OrderSummary.class);
    }
}
~~~

If your Spring Framework version does not yet include `RestClient`, use `RestTemplate` or `WebClient` with the same principles: host and port from `HostInfo`, request timeouts, and service-to-service authentication.

Example controller serving only the local store:

~~~java
import java.util.Optional;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

interface OrderStateStoreReader {
    Optional<OrderSummary> readLocalOnly(String orderId);
}

@RestController
@RequestMapping("/internal/state/orders")
class LocalOrderStateController {

    private final OrderStateStoreReader storeReader;

    LocalOrderStateController(OrderStateStoreReader storeReader) {
        this.storeReader = storeReader;
    }

    @GetMapping("/{orderId}")
    OrderSummary getLocal(@PathVariable String orderId) {
        return storeReader.readLocalOnly(orderId)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND));
    }
}
~~~

`readLocalOnly` only queries the local store. The internal endpoint must never call back into the router, otherwise instances can enter a routing loop. In real deployments, verify the instance is still the owner before returning data; if the partition moved away, return a status code signaling stale metadata so the caller re-queries discovery.

A local reader implementation should verify ownership right before reading:

~~~java
import java.util.Optional;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.errors.InvalidStateStoreException;
import org.apache.kafka.streams.state.HostInfo;
import org.apache.kafka.streams.state.QueryableStoreTypes;
import org.apache.kafka.streams.state.ReadOnlyKeyValueStore;
import org.springframework.cloud.stream.binder.kafka.streams.InteractiveQueryService;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
class BinderOrderStateStoreReader implements OrderStateStoreReader {

    private static final String STORE_NAME = "order-summary-store";
    private final InteractiveQueryService interactiveQueryService;

    BinderOrderStateStoreReader(InteractiveQueryService interactiveQueryService) {
        this.interactiveQueryService = interactiveQueryService;
    }

    @Override
    public Optional<OrderSummary> readLocalOnly(String orderId) {
        HostInfo owner = interactiveQueryService.getHostInfo(
                STORE_NAME, orderId, Serdes.String().serializer());
        HostInfo current = interactiveQueryService.getCurrentHostInfo();

        if (owner == null || current == null || !current.equals(owner)) {
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT, "This instance no longer owns the key");
        }

        ReadOnlyKeyValueStore<String, OrderSummary> store =
                interactiveQueryService.getQueryableStoreType(
                        STORE_NAME, QueryableStoreTypes.keyValueStore());
        try {
            return Optional.ofNullable(store.get(orderId));
        }
        catch (InvalidStateStoreException ex) {
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT, "The local store is changing ownership", ex);
        }
    }
}
~~~

## 9. Router Example: Local or Remote

The code below shows the routing decision. `OrderStateStoreReader` reads the local store; `RemoteOrderStateClient` calls the internal endpoint on the host advertised by Kafka Streams.

~~~java
import java.util.Optional;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.state.HostInfo;
import org.springframework.cloud.stream.binder.kafka.streams.InteractiveQueryService;
import org.springframework.stereotype.Service;

@Service
class OrderStateQueryRouter {

    private static final String STORE_NAME = "order-summary-store";

    private final InteractiveQueryService interactiveQueryService;
    private final OrderStateStoreReader localReader;
    private final RemoteOrderStateClient remoteClient;

    OrderStateQueryRouter(
            InteractiveQueryService interactiveQueryService,
            OrderStateStoreReader localReader,
            RemoteOrderStateClient remoteClient) {
        this.interactiveQueryService = interactiveQueryService;
        this.localReader = localReader;
        this.remoteClient = remoteClient;
    }

    Optional<OrderSummary> find(String orderId) {
        HostInfo owner = interactiveQueryService.getHostInfo(
                STORE_NAME,
                orderId,
                Serdes.String().serializer());

        HostInfo current = interactiveQueryService.getCurrentHostInfo();

        if (owner == null || current == null) {
            throw new IllegalStateException(
                    "Kafka Streams host metadata is not available");
        }

        if (current.equals(owner)) {
            return localReader.readLocalOnly(orderId);
        }

        return Optional.ofNullable(remoteClient.fetch(owner, orderId));
    }
}
~~~

In real applications, extract local reading into a separate service so the internal endpoint can call it directly without triggering remote routing. The simplified example above highlights the decision point: read the local store only when `current` equals `owner`.

`getHostInfo` or store queries can fail while Kafka Streams is still initializing, state stores are restoring, or metadata is shifting. Do not treat every exception as "key not found"; distinguish missing keys from unready stores or unavailable metadata.

## 10. Handling Startup and Unready State Stores

During startup, Kafka Streams must build the topology, join the group, receive partitions, and restore state stores. Requests arriving too early may encounter a store that is not yet queryable.

The Kafka Streams Binder includes retries for fetching stores and resolving hosts. You can configure retry attempts and backoff intervals:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            stateStoreRetry:
              maxAttempts: 5
              backOffInterval: 1000
~~~

The binder's default documented in current releases is one attempt with a one-second interval. Increasing attempts helps absorb brief startup races, but does not replace readiness probes or HTTP request timeouts. Keep total retry duration below the request time budget and consider returning `503 Service Unavailable` when state is not ready.

Pair this with readiness indicators so an instance receives query traffic only after Kafka Streams enters a healthy state and required state stores finish restoring. Do not use liveness checks to repeatedly restart pods merely because a store is undergoing normal restoration.

## 11. Handling Stale Metadata During Rebalances

Routing metadata is point-in-time data. While a request is in flight, Kafka Streams may rebalance because:

- A new instance joins or an existing instance stops.
- A consumer loses connectivity or exceeds heartbeat/poll intervals.
- Partition assignments change after scaling the application.
- A task moves to another instance for recovery.

Consequently, a freshly discovered host may no longer own the key by the time the request arrives. The internal endpoint should verify ownership or local store queryability and return a recognizable error such as `409 Conflict` or `503 Service Unavailable`.

The caller can refresh metadata and retry once within a time budget. Avoid infinite retries or ping-pong forwarding between two hosts. If the second routing attempt still fails, return a retryable error to the caller and log the store name, key, old host, new host, and partition if available.

## 12. HostInfo Is Not the Kafka Broker Address

`HostInfo` holds the host and port of a Kafka Streams instance's query endpoint. It is neither the broker address nor the address of a Kafka topic partition.

| Value | Purpose |
|---|---|
| `bootstrap.servers` | Connecting to Kafka brokers |
| `application.id` | Identifying the Kafka Streams application group |
| `application.server` | Advertising each instance's RPC endpoint |
| `HostInfo` | Host/port metadata for routing state store queries |
| `partition` in metadata | Partition containing the state store key |

Do not send REST queries to the broker. Nor should you assume the Kafka broker forwards HTTP requests to partition-owning instances. Discovery and RPC are coordinated by your application.

## 13. Securing Internal Query Endpoints

Internal endpoints can expose business data from state stores. Therefore, never expose them directly to the public internet or allow arbitrary services on the network to call them.

Safeguards to consider:

- Allow traffic only from peer instances of the same application or trusted service gateways.
- Use TLS/mTLS or service-to-service authentication.
- Enforce tenant, user, and data-scope authorization before routing.
- Cap request rates, timeouts, and response sizes.
- Never allow clients to supply arbitrary hostnames/ports to prevent SSRF; target hosts must come from validated Kafka Streams metadata.
- Audit-log sensitive queries while avoiding unnecessary logging of payloads or PII.
- Never let internal endpoints become an authorization bypass around public APIs.

If using a service mesh or gateway, ensure internal calls still reach the exact target instance. A round-robin load balancer will break `HostInfo`-based routing if it replaces the target host with a shared VIP.

## 14. Querying from an API Gateway or Another Application

Initial requests do not have to land directly on a Kafka Streams instance. An API gateway or dedicated query service can hold discovery logic:

1. Receive `orderId` from the client.
2. Call a coordinator endpoint on the Kafka Streams application to look up the owner.
3. Read locally if the coordinator endpoint happens to reside on the owner.
4. Otherwise, make an RPC call to the endpoint indicated by `HostInfo`.
5. Return the result to the client.

Another option is having every instance expose the same API and self-route. When a request hits the wrong instance, that instance looks up metadata and forwards to the owner. This is simple for clients, though forwarding endpoints and local-only endpoints must remain separate to avoid loops.

If using a gateway, keep discovery inside trusted services rather than leaking internal `HostInfo` lists to external clients. Instance addresses can change during scaling or redeployments.

## 15. Considering Standby Stores and Stale Reads

Kafka Streams can configure standby replicas so secondary instances keep copies of state stores. Standbys shorten recovery time when active instances fail, though standby data may lag behind active stores.

For queries requiring the latest data:

- Prefer `activeHost` from metadata.
- Do not automatically fall back to a standby on active-host failure unless semantics are explicitly defined.
- Return `503` or retry discovery after rebalancing completes.

For queries tolerating bounded staleness:

- Clearly define the maximum staleness allowed by business rules.
- Configure standby tasks and appropriate store query parameters.
- Use `StoreQueryParametersCustomizer` if your binder version supports it and the application needs stale stores enabled.
- Return the state's timestamp or version so callers can judge freshness.

Never use stale stores for financial decisions or inventory checks when business rules demand reading the latest state.

## 16. Performance and Scalability

Routing directly to the owner avoids fanning out to every instance, yet query costs still need bounds:

- Configure separate timeouts for local and remote queries.
- Use connection pooling for the internal HTTP client.
- Consider batch queries when reading many keys at once; group keys by owner to cut network round-trips.
- Cache metadata briefly if needed, with invalidation/refresh when hosts change.
- Do not cache state results too long when callers expect fresh data.
- Track local-to-remote query ratios, discovery latency, RPC latency, and stale metadata errors.
- Avoid turning state stores into ad-hoc query databases with unbounded scans.

If an endpoint serves multiple keys, group keys by partition or owner before making remote calls. This reduces request count while keeping batch sizes and response times bounded.

## 17. Observability and Troubleshooting

Useful metrics:

The names below are illustrative application-level metrics you can instrument; the Kafka Streams Binder does not automatically emit metrics with these exact names.

| Metric | Meaning |
|---|---|
| `interactive_query.lookup` | Count of owner metadata lookups |
| `interactive_query.local` | Queries served locally on the current instance |
| `interactive_query.remote` | Queries forwarded to another instance |
| `interactive_query.metadata_unavailable` | Metadata not ready or no owner found |
| `interactive_query.stale_route` | Target endpoint no longer owns the key |
| `interactive_query.rpc_latency` | Remote call latency |
| `interactive_query.store_not_ready` | State store not yet queryable |

Logs should record `storeName`, `partition`, owner `HostInfo`, current host, request ID, and routing outcome. Never log sensitive state values.

When a query yields no result, distinguish among:

- Key does not exist in the store.
- Key belongs to a partition on another instance.
- State store has not finished restoring.
- Metadata unavailable during a rebalance.
- Remote RPC endpoint unreachable.
- Request rejected due to authorization.

Only the first case should return `404 Not Found`. The rest usually warrant operational errors such as `503 Service Unavailable`, `409 Conflict`, or `403 Forbidden` depending on the root cause.

## 18. Testing Query Routing

Tests should cover both local and remote paths:

1. Run a single instance, query a key held by that instance, and verify the local store returns the expected result.
2. Run multiple instances with distinct `application.server` values; query a key owned by another instance and verify the request forwards to the right host.
3. Use the key serializer matching the topology; verify owner metadata corresponds to the expected partition.
4. Stop an instance or trigger a rebalance mid-query; verify stale routes are handled with bounded retries.
5. Query while a state store is restoring; verify retries/`503` instead of returning wrong results.
6. Verify the internal endpoint only reads local state and never self-forwards.
7. Verify unauthorized requests are blocked before reading state.
8. Verify remote timeouts and network errors do not trigger infinite retries.
9. If using standby/stale stores, verify responses accurately reflect data freshness.

`TopologyTestDriver` is useful for testing transformations and state store contents in a single topology. It does not replace integration tests for discovery metadata, `application.server`, network routing, rebalances, and RPC across multiple instances. Use a Kafka broker and multiple processes/containers in integration tests to validate the real execution path.

## 19. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `getHostInfo` finds no host | Missing `application.server` or metadata not ready yet | Configure per-instance endpoints and bounded retries |
| Every instance advertises the same host | Shared hostname or load balancer used for `application.server` | Advertise each instance's directly reachable address |
| Local store returns null even though key exists | Request landed on an instance not owning the partition | Use key metadata and forward to the owner |
| Remote endpoint unreachable | Port closed, DNS failure, or web server not listening | Check network, DNS, listeners, and ports |
| Queries fail after rebalance | Stale host metadata | Refresh metadata and retry once |
| Queries always return old data | Reading standby/stale store or state lagging behind | Route to active host and inspect freshness |
| Queries return 404 while store is unready | Conflating store readiness errors with missing keys | Classify exceptions and return appropriate status codes |
| Query loops across instances | Internal endpoint also calls the router | Separate local-only endpoints from routing endpoints |
| Wrong partition host resolved | Mismatched serializer or partitioning strategy | Use the topology's exact key serializer/partitioner |

## 20. Implementation Checklist

- State store materialized with a stable name and matching queryable type.
- Every instance of the same application shares the same `applicationId`.
- Each instance advertises its own `application.server` reachable by all other instances.
- RPC server actually listens on the advertised address and port.
- `InteractiveQueryService` uses the right store name, key, and serializer.
- Local queries run only when current host equals owner host.
- Remote queries use internal HTTP/gRPC targeting a local-only endpoint.
- Timeouts, stale metadata handling, and bounded retries during rebalances are in place.
- Active hosts and standby hosts are distinguished with clear freshness rules.
- Internal endpoints are secured with authentication, TLS/mTLS, and network policies.
- Local/remote queries, metadata lookups, store readiness, and RPC latency are monitored.
- Integration tests run across multiple instances and a real Kafka broker.

Routing queries to the right instance is essential whenever state stores are distributed across multiple Kafka Streams instances. `InteractiveQueryService` helps locate the host holding a key and read local state; `application.server` advertises each instance's RPC address. Applications must implement their own HTTP/gRPC layer to forward queries from the receiving instance to the owner, handle shifting metadata during rebalances, secure internal endpoints, and distinguish active from standby state. When discovery, RPC, and local queries work together cleanly, APIs can query the entire distributed state without broadcasting requests to every instance.

## References

- [Spring Cloud Stream — Interactive Queries](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/interactive-queries.html)
- [Apache Kafka — Interactive Queries](https://kafka.apache.org/documentation/streams/developer-guide/interactive-queries.html)
- [Spring for Apache Kafka — Kafka Streams Support](https://docs.spring.io/spring-kafka/reference/streams.html)
- [Apache Kafka — KeyQueryMetadata API](https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/KeyQueryMetadata.html)
