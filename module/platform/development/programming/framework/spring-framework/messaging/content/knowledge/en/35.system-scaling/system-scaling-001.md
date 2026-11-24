# Multi-Instance Distribution and In-Memory State

> Scope: horizontally scaling Spring Messaging applications, distinguishing local state from shared state, handling long-lived RSocket connections, load-balancing consumers, and ensuring correctness when multiple instances process messages concurrently.

## 1. Objectives

After this lesson, you will be able to:

- Explain why in-memory variables of one instance are not automatically shared with other instances.
- Classify state by request, connection, session, cache, and business data.
- Design stateless applications so instances can be added or removed safely.
- Choose among shared stores, distributed caches, partitioning, sticky connections, and replication.
- Understand the impact of long-lived RSocket connections, reconnection, and session resumption.
- Scale Spring AMQP/Spring Integration consumers while controlling ordering, prefetch, and duplicates.
- Use shared message stores and distributed locks when a workflow requires shared state or ownership.
- Handle idempotency, retries, rolling deployments, and instance failures.

## 2. Why Does In-Memory State Become a Problem?

A Spring Boot application instance has its own JVM, heap, thread pool, singleton beans, caches, and data structures. When three instances are deployed, the system has three independent copies of those memory areas.

For example:

```java
@Service
class ConnectionRegistry {
    private final Map<String, ClientState> clients = new ConcurrentHashMap<>();

    void register(String clientId, ClientState state) {
        clients.put(clientId, state);
    }

    ClientState find(String clientId) {
        return clients.get(clientId);
    }
}
```

The `ConnectionRegistry` bean is a singleton within a single Spring `ApplicationContext`, but a singleton is only scoped to that instance/JVM. If the first request is handled by pod A and the next request goes to pod B, the map on B does not contain the entry stored on A.

Increasing the number of instances increases processing capacity, but it also exposes wrong assumptions about local memory. A single-node system may accidentally work because every request sees the same map; when running multiple nodes, the result becomes dependent on which instance receives the request.

Local memory is still very useful for temporary data, caches, or connection-bound state. What matters is clearly defining its scope, lifetime, and recovery mechanism.

## 3. Classifying State Before Scaling

Not all state needs to go into Redis or a database. Classify it first:

| State Type | Examples | Proper Scope | What Happens When an Instance Is Lost? |
| --- | --- | --- | --- |
| Request-local | Local variables, DTOs, validation results | One processing execution | Can be discarded; the client retries if needed |
| Connection-local | RSocket requester, subscriptions, connection attributes, flow-control state | One live connection | Connection is lost; the client reconnects and recovers per protocol/application rules |
| Process-local cache | Lookup caches, loaded configuration, compiled metadata | One JVM | Cache is reloaded; must not be the authoritative data source |
| User/session state | Login, temporary shopping cart, user workflow | One user/session across multiple requests | Must have a shared storage location if node switching or surviving restarts is required |
| Shared coordination state | Locks, leader, claims, message groups, idempotency keys | Multiple instances | Must be stored in a shared coordination system |
| Durable business state | Orders, payments, processing status | Multiple instances and multiple application versions | Must be stored durably and recovered after restarts |

A useful rule of thumb: if losing an instance means that data cannot be lost, local memory cannot be the sole storage location.

## 4. Stateless Instances and Horizontal Scaling

### 4.1. The Stateless Model

A stateless instance does not depend on data that exists only in its own memory to process the next request. It may hold local caches or temporary data, but the authoritative data source lives in a shared location or can be reconstructed.

A common processing flow:

1. The load balancer picks a healthy instance.
2. The instance authenticates the request and reads the required data from the shared database/cache.
3. The instance executes the business logic within a transaction or according to a durable state machine.
4. The result is stored in the shared store.
5. The response is returned to the client; the next request may go to a different instance.

With this model, scaling out is primarily adding instances and updating service discovery/the load balancer. Scaling in can remove an instance after stopping new requests and finishing in-flight requests.

### 4.2. What Should Live in Local Memory?

Can be kept in local memory:

- Reloadable reference data caches.
- Objects created during a single request or a single message processing execution.
- Buffers and temporary state of a running stream.
- Connection state tied to a specific connection.
- Process-scoped circuit breakers, local rate limiters, or metric registries, if per-instance semantics are acceptable.

Should not be kept only in local memory:

- Committed payment or order state.
- Idempotency keys needed to prevent duplicate processing across instances.
- Sessions that need to continue after a request is routed to another node.
- Aggregator/message group state that must be visible to multiple consumers.
- Locks used to ensure an action happens only once across the entire cluster.
- Workflow state that must survive rolling restarts or crashes.

### 4.3. Avoid Using a Static Map as a Distributed Store

A `static ConcurrentHashMap` is shared only within a single classloader/JVM. It does not automatically replicate across pods, containers, or other machines. A static map also does not handle persistence, eviction, memory bounds, schema migration, or synchronization.

If using a local cache, set a TTL/maximum size, monitor the hit rate, and define an invalidation strategy. For data modified on another node, the local cache can become stale. Choose TTL, event invalidation, or version checks according to consistency requirements.

## 5. Choosing Where to Store Shared State

| Requirement | Common Choice | Characteristics to Consider |
| --- | --- | --- |
| Business data requiring transactions and durability | Relational database | Transactions, constraints, optimistic locking, backups, and schema migration |
| Session or ephemeral shared state | Redis or distributed cache | TTL, eviction, persistence mode, failover, and consistency |
| Message group/aggregator state | Spring Integration `MessageGroupStore` backed by JDBC/Redis or an appropriate store | Correlation, expiry, cleanup, locking, and query patterns |
| Coordination/critical section | Database lock, `RedisLockRegistry`, ZooKeeper, or coordination system | Lease, TTL, owner, fencing, failover, and lock expiry |
| Event history and replay | Durable message log/event store | Retention, partition key, ordering, and consumer offsets |
| Large files or payloads | Object storage | Object versioning, checksums, access control, and lifecycle |

Do not choose Redis merely because it is fast. Data that requires multi-record transactions, uniqueness constraints, or durable history is usually a better fit for a database. A cache is only a reconstructible copy; do not use a cache as the authoritative source if the system has no plan for handling eviction or cache loss.

### 5.1. Shared Sessions with Spring Session

If a WebFlux application needs a shared `WebSession` across multiple instances, Spring Session can store sessions in Redis:

```java
@Configuration
@EnableRedisWebSession
class SessionConfiguration {
}
```

You need to configure an appropriate `ReactiveRedisConnectionFactory` and a Spring Session Redis dependency compatible with your Spring Boot version. Once enabled, Spring Session provides a Redis-backed `WebSession` instead of the web server's local session store.

For the Servlet stack, Spring Session provides a corresponding integration for `HttpSession`. Both integrations solve HTTP sessions. They do not automatically turn the state of an RSocket connection or `@ConnectMapping` into shared state. If RSocket runs over WebSocket, the HTTP handshake session and the RSocket connection state remain two separate scopes that must be designed explicitly.

A shared session needs timeouts, stable serialization, namespaces, and a revocation policy. When multiple instances read/write the same session concurrently, define how concurrent updates and flush mode are handled.

### 5.2. Shared Message Groups in Spring Integration

Components such as aggregators and resequencers can hold message group state. If each instance uses an in-memory `SimpleMessageGroupStore`, each node only sees the portion of the group it has received.

When shared group state is needed, use a persistent `MessageGroupStore` such as a JDBC-backed store or Redis-backed store, and configure all instances to use the same backend with the same namespace/table prefix. Spring Integration provides `JdbcMessageStore` for message/group state and corresponding Redis implementations.

A shared store allows multiple instances to see the same group state, but it does not automatically solve every race condition. When multiple nodes can update the same group, coordinate with locks, transactions, or an appropriate claim mechanism.

## 6. RSocket Connections and Load Balancing

### 6.1. One `RSocketRequester` Is Bound to One Connection

`RSocketRequester` provides the API to make requests over an `io.rsocket.RSocket`. When created with `RSocketRequester.builder().tcp(...)` or `.webSocket(...)`, the connection is established on the first request and reused for subsequent requests.

This means a typical requester is a single connection to a single server endpoint. If the load balancer picks pod A when the TCP/WebSocket connection is established, requests multiplexed over that connection continue going to pod A. The load balancer does not pick a new pod for each message on the same TCP/WebSocket connection.

### 6.2. Load Balancing at Connection Creation Time

For RSocket over TCP, you can place an L4 load balancer in front of server instances or use service discovery to select an endpoint when creating the connection. For RSocket over WebSocket, the HTTP/WebSocket load balancer picks a backend during the handshake; the WebSocket connection then persists with that chosen backend.

Spring Cloud LoadBalancer provides an abstraction for selecting a service instance, including round-robin and random implementations. However, `RSocketRequester.Builder` does not automatically become a load-balanced requester merely by adding the Spring Cloud LoadBalancer dependency. If you want client-side instance selection via service discovery, the application must integrate `ServiceInstance` selection, manage connections/pools, and handle reconnection.

One strategy is to create a pool of `RSocketRequester` instances, each connected to a selected instance. When borrowing a requester from the pool, consider current load, connection count, health, timeouts, and eviction policy for failed connections. Do not create a new connection per message if the goal is to leverage multiplexing.

### 6.3. Sticky Sessions and Connection Affinity

Connection affinity arises naturally with TCP and WebSocket because a connection stays pinned to one backend. Sticky sessions at the HTTP layer can help related HTTP requests return to the same node, but they do not replace shared state.

The advantage of affinity is that local state tied to a connection can still be found when requests travel over that same connection. Disadvantages:

- When a node dies, local state is lost along with the connection.
- Rolling deployments may force clients to reconnect to a different node.
- One node can become hotter than others if some clients hold long-lived connections and traffic is uneven.
- It does not solve requests from another client or background workers that need access to the same state.

Use affinity when needed for connection-local state or cache optimization, but critical state must still have a recovery mechanism.

### 6.4. RSocket Session Resumption

RSocket has a session resumption extension to recover connections after certain network drops. Resumption requires protocol state to be retained on both ends. It is not a mechanism that automatically migrates a connection to any arbitrary pod.

If a connection reconnects to a different instance, the new instance must have the appropriate resumption state to continue the session. Do not assume that state is shared across instances just because they run the same Spring application. Check the capabilities of your RSocket Java version, transport, resume store, and topology; if not supported, design application-level reconnection instead.

With application-level reconnection, the client can re-authenticate, create a new requester, re-register subscriptions, and fetch business state from the shared store. Commands whose execution status is unknown require an idempotency key.

## 7. Scaling Message Broker Consumers

### 7.1. Competing Consumers

With brokers that support queues and competing consumers, multiple consumers across multiple instances can read from the same queue. The broker distributes messages to registered consumers, increasing overall processing capacity.

A Spring AMQP deployment approach is to run the same `@RabbitListener` on every instance and configure concurrency:

```java
@RabbitListener(queues = "orders")
public void handle(OrderMessage message) {
    orderService.process(message);
}
```

Example listener container configuration:

```java
@Bean
SimpleRabbitListenerContainerFactory rabbitListenerContainerFactory(
        ConnectionFactory connectionFactory) {
    var factory = new SimpleRabbitListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setConcurrentConsumers(2);
    factory.setMaxConcurrentConsumers(8);
    factory.setPrefetchCount(20);
    return factory;
}
```

This is an illustrative configuration. As you add more application instances, the total number of consumers is the sum of listener container concurrency across all instances. You must account for the total number of consumers, channels, connections, and the capacity of the broker and downstream databases.

### 7.2. Prefetch and Memory

Prefetch is the number of unacknowledged deliveries the broker may push ahead to a consumer. High prefetch can increase throughput when handlers are fast, but it also places more messages in client memory and can cause uneven distribution.

Spring AMQP has a default prefetch of 250 since version 2.0; this value may need to be lowered when messages are large, processing is slow, or strict ordering is required. With many consumers, a prefetch of 1 helps distribute work more evenly but may reduce throughput due to increased round trips/idle time.

Benchmark according to message size, processing time, consumer count, and in-flight message count. Prefetch is a message count rather than a byte limit, so large messages can cause memory usage to grow rapidly.

### 7.3. Ordering and Partitioning

When multiple consumers process messages in parallel, you should not assume completion order equals publish order. Two messages for the same entity may be delivered to two different consumers and processed in different amounts of time.

If ordering by a key such as `accountId` or `orderId` is required, use key-based partitioning/sharding or a single-consumer mechanism for that partition. Every message with the same key must go through the same partition/serial executor to preserve the required ordering.

Partitioning has trade-offs: skewed key distribution creates hot partitions; a single partition typically limits concurrency for that key. Global ordering is unnecessary if business logic only requires ordering per aggregate key.

### 7.4. Scaling Listeners Does Not Automatically Share State

If a listener uses a `HashMap` to hold aggregation state, each consumer instance has its own separate map. Messages from the same message group can be split across multiple nodes and no single instance sees the entire group.

Use a persistent shared `MessageGroupStore` or partitioning to ensure messages in the same group are processed under a consistent strategy. For aggregators, add locking/claiming to prevent two instances from releasing or updating the same group simultaneously.

## 8. Coordination Across Multiple Instances

### 8.1. A Local Lock Is Not a Distributed Lock

`synchronized`, `ReentrantLock`, or Spring Integration's `DefaultLockRegistry` only coordinate threads within the same JVM/component. Two instances have two independent lock objects; both can enter the critical section simultaneously.

When cluster-wide exclusive access is needed, use a distributed coordination mechanism backed by a shared backend, such as database locks, Redis, ZooKeeper, or an appropriate coordination service.

Spring Integration provides the `LockRegistry` abstraction with implementations such as JDBC, Redis, and ZooKeeper. `RedisLockRegistry` can coordinate instances when using the same Redis backend and the same lock key.

### 8.2. `LockRegistry` Example

```java
@Service
class ReconciliationService {

    private final LockRegistry lockRegistry;

    ReconciliationService(LockRegistry lockRegistry) {
        this.lockRegistry = lockRegistry;
    }

    void reconcile(String accountId) {
        Lock lock = lockRegistry.obtain("reconcile:" + accountId);
        if (!lock.tryLock()) {
            return;
        }
        try {
            performReconciliation(accountId);
        } finally {
            lock.unlock();
        }
    }

    private void performReconciliation(String accountId) {
        // Read and update durable state using a transaction.
    }
}
```

The `LockRegistry` bean must be configured with the appropriate implementation. If `DefaultLockRegistry` is used, this code only locks within a single JVM. To lock across instances, inject `RedisLockRegistry`, `JdbcLockRegistry`, or an equivalent distributed implementation.

### 8.3. TTL, Leases, and Fencing

Distributed locks typically have a TTL so the lock expires automatically if the process dies. A TTL that is too short may expire while the lock holder is still running; another instance acquires the lock and both execute side effects. A TTL that is too long slows down recovery after a crash.

For critical operations, consider fencing tokens or monotonically increasing versions. The target storage accepts operations only from the newest token, preventing an old process from continuing to write after its lease has expired.

Do not use distributed locks as a replacement for database transactions or constraints. Whenever possible, protect invariants with unique constraints, optimistic versioning, or atomic updates in the authoritative data store. A lock is only an additional coordination layer.

### 8.4. Singleton Jobs and Leader Election

If a scheduled task must run on only one node, `@Scheduled` on every instance will run multiple times. Options include:

- Designing the task to be idempotent and allowing any/all nodes to run it if the work can be distributed.
- Using a distributed lock/leader election so only one node holds the right to run.
- Using a scheduler or workflow engine with persistence and explicit ownership.

If using a lease/lock, handle dead nodes, TTL, renewal, clock skew, fencing, and cases where a task runs longer than the lease. Do not rely on an `isLeader` boolean in local memory as the cluster-wide source of truth.

## 9. Idempotency and Handling Duplicate Messages

When scaling across multiple instances, retries and redeliveries are normal. A consumer may complete side effects but crash before sending an ACK; the broker redelivers the message to another instance. Therefore, never assume a message is processed only once.

An idempotency pattern:

1. The producer generates a stable `messageId` or `idempotencyKey` for a logical operation.
2. The consumer opens a transaction and inserts the key into an inbox/dedup table with a unique constraint.
3. If the key already exists and has been processed, the consumer does not execute the side effect again.
4. If it does not exist, the consumer updates business state and records the processing result within the same transaction.
5. After commit, the consumer ACKs the message.

Example schema:

```sql
CREATE TABLE processed_message (
    message_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

The unique constraint is the final line of defense when two instances receive the same message concurrently. If the dedup record and the business update live in two different systems, design explicit consistency and retry semantics.

On the producer side, the transactional outbox pattern writes business changes and the event-to-publish in the same database transaction. A separate publisher reads the outbox and sends messages; the publisher may send duplicates, so the consumer still needs idempotency.

## 10. Caching Across Multiple Instances

Local caches reduce latency, but each instance may hold a different value. There are three common strategies:

| Strategy | How It Works | Trade-offs |
| --- | --- | --- |
| Shared cache | All instances read/write the same Redis or cache server | Network hop and the cache backend become a shared dependency |
| Local cache + TTL | Each node caches independently for a short period | Can be stale within the TTL window |
| Local cache + invalidation event | One node emits an event for other nodes to evict/update | Must handle lost events, duplicates, ordering, and reconnection |

Cache invalidation events should carry the key or version rather than broadcasting a potentially stale state object. If an event is lost, TTL or periodic refresh must bring the cache back to the correct state.

Do not cache authorization decisions longer than the permission lifecycle if revocation must take effect quickly. Define TTL and invalidation explicitly for security-sensitive data.

## 11. Failures, Reconnection, and Rolling Deployments

### 11.1. When an Instance Dies

An instance can die due to OOM, a crash, node failure, deployment, or removal by a health check from the load balancer. The system must ensure:

- New requests are routed to healthy instances.
- In-flight requests have clear timeouts/cancellation.
- Unacknowledged messages can be redelivered by the broker.
- Local cache/connection state is rebuilt or recovered.
- Shared business state is not lost.
- Retries do not produce duplicate side effects.

### 11.2. RSocket Reconnection

Clients need a reconnection strategy with exponential backoff and jitter, a cap on attempts or retry duration, re-authentication when needed, and subscription re-registration. When creating a new connection, the load balancer may choose a different instance; therefore, any state that must continue has to be recovered from a shared store or supported protocol resume state.

Do not blindly retry every request. If a previous request might already have been processed while the response was lost, the client needs an idempotency key or a status query before re-sending the command.

### 11.3. Graceful Shutdown

During a rolling deployment:

1. Mark the instance as no longer accepting new connections/requests via readiness/draining mechanisms.
2. Stop accepting new deliveries or stop listeners according to the appropriate lifecycle.
3. Finish in-flight requests/handlers within the allowed timeout.
4. ACK successfully processed messages; let unfinished messages be redelivered.
5. Close RSocket connections, channels, executors, and resources in an orderly manner.
6. If unable to finish before the deadline, shut down cleanly and rely on idempotency during retry.

Do not delete shared state merely because one instance is shutting down; cleanup should rely on TTL, owner/lease, or workflow state.

## 12. Architecture Example

A Spring Messaging system can be structured into the following parts:

```text
                 +----------------------+
Client ----------> Load Balancer / Edge |
                 +----------+-----------+
                            |
              +-------------+-------------+
              |             |             |
         +----v----+   +----v----+   +----v----+
         | App A   |   | App B   |   | App C   |
         | local   |   | local   |   | local   |
         | cache   |   | cache   |   | cache   |
         +----+----+   +----+----+   +----+----+
              |             |             |
              +-------------+-------------+
                            |
              +-------------+-------------+
              | Shared DB / Redis / Store |
              +---------------------------+

              +---------------------------+
              | Message Broker / Queue    |
              +-------------+-------------+
                            |
                 consumers across A/B/C
```

Apps A/B/C handle requests statelessly, maintain reconstructible local caches, and use shared stores for session/workflow/business state. The broker distributes messages to consumers across nodes. The database is the authoritative business data source; Redis or a coordination service holds state appropriate to its semantics.

## 13. Troubleshooting Scaling Issues

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Login succeeds on node A, but node B treats it as anonymous | Session lives only in A's memory | Check the session repository, cookie/session id, and shared store |
| RSocket client works until a pod restarts | State or connection existed only in-process | Check reconnection, resubscription, and state recovery |
| A message group is processed with missing elements | Group state is in a local `MessageGroupStore` | Use a persistent shared `MessageGroupStore` or partition key |
| Two nodes run the same job simultaneously | Only using `synchronized`/local lock | Use distributed coordination or an idempotent design |
| Consumer throughput does not increase when adding pods | Bottleneck is in the broker, database, hot partition, or prefetch | Measure consumer capacity, downstream pools, queue depth, and key skew |
| Messages for the same order complete out of order | Multiple consumers process in parallel or high prefetch | Partition by aggregate key and limit concurrency appropriately |
| Duplicate side effects after retry | Non-idempotent consumer or error between side effect and ACK | Use inbox/dedup keys, transactions, and redelivery tests |
| One node has much higher load | Long-lived connections pinned to one backend or hot key partition | Monitor connection counts, traffic per instance, and key distribution |
| Redis lock expires while job is still running | TTL too short or process paused | Check lease renewal, fencing tokens, and critical section duration |

## 14. Multi-Instance Deployment Checklist

- [ ] Classified request-local, connection-local, cache, session, coordination, and durable business state.
- [ ] Not using local maps/static fields as the source of truth for state that must be shared.
- [ ] Business state is persisted in a database or store with appropriate durability.
- [ ] Shared sessions have explicit repository, TTL, serialization, and namespace settings.
- [ ] RSocket connections are treated as long-lived and pinned to one backend at connect time.
- [ ] Plans exist for load balancing new connections, connection pools, and reconnection.
- [ ] Not assuming Spring Cloud LoadBalancer automatically load-balances `RSocketRequester`.
- [ ] RSocket session resumption has been verified against the actual implementation and topology.
- [ ] Message group/aggregator state is stored in a shared store if multiple instances process the same group.
- [ ] Distributed locks use a shared backend; TTL, renewal, and fencing are considered.
- [ ] Consumer concurrency, prefetch, ordering, and memory have been benchmarked.
- [ ] Idempotency/deduplication is in place for retries and redeliveries.
- [ ] Local caches have TTL/invalidation and do not retain revoked access permissions.
- [ ] Readiness, draining, graceful shutdown, and reconnection have been tested.
- [ ] Dashboards include per-instance metrics as well as cluster-wide aggregate metrics.

## 15. References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): `RSocketRequester`, shared connections, `SETUP`, session resumption, and interaction models.
- [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): service instance selection, round-robin/random, same-instance preference, and sticky session capabilities.
- [Spring Session — WebSession Integration](https://docs.spring.io/spring-session/reference/web-session.html): sharing WebFlux `WebSession` via a repository such as Redis.
- [Spring Session — Redis Configuration](https://docs.spring.io/spring-session/reference/configuration/redis.html): serialization, namespace, flush mode, and session storage.
- [Spring Integration — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): persistent `MessageStore`/`MessageGroupStore` for stateful integration patterns.
- [Spring Integration — Distributed Locks](https://docs.spring.io/spring-integration/reference/distributed-locks.html): `LockRegistry` and JDBC, Redis, and ZooKeeper implementations.
- [Spring Integration — Redis Support](https://docs.spring.io/spring-integration/reference/redis.html): `RedisLockRegistry` and cross-instance lock coordination.
- [Spring AMQP — Listener Concurrency](https://docs.spring.io/spring-amqp/reference/amqp/listener-concurrency.html): scaling consumer counts and tuning concurrency.
- [Spring AMQP — Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): prefetch, concurrency, and acknowledgement settings.

Configuration details and APIs depend on the versions of Spring Boot, Spring Framework, Spring Integration, Spring AMQP, Spring Session, and RSocket Java. Verify against your project's exact dependency versions and test under scale-out, reconnection, or rolling restarts.
