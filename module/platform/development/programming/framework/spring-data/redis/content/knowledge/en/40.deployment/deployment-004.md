# Startup, Readiness Checks, and Graceful Shutdown in Spring Data Redis

In a **Spring Data Redis** application, creating a `RedisTemplate` or `ReactiveRedisTemplate` bean does not mean Redis is ready to serve every operation. When deployed to servers, Docker, or Kubernetes, an application goes through multiple phases: **initializing configuration**, **establishing connections**, **warming required resources**, **accepting traffic**, **entering shutdown**, **finishing in-flight work**, and **releasing connections**.

Managing these stages is a **lifecycle** problem, not just calling `PING` at startup. Redis can lose connectivity after the application is already ready; an optional Redis cache has a different policy from a Redis instance holding login sessions; and a Redis Streams consumer must stop polling new messages and finish or leave pending entries properly before the JVM exits.

This lesson explains how to design the lifecycle of **Spring Boot + Spring Data Redis + Lettuce**, combining Spring Boot Actuator, graceful shutdown, Kubernetes probes, Redis Streams/Pub/Sub, and failover scenarios.

## 1. Goals of a Safe Redis Lifecycle

A reliable deployment must answer these questions:

1. **At startup:** has the application loaded configuration, secrets, and TLS certificates and built a valid connection factory?
2. **Before accepting requests:** is Redis actually reachable via the required endpoint and authorized to run essential commands?
3. **When Redis fails temporarily:** should the application wait, return errors, use a fallback, or leave the ready state?
4. **At shutdown:** has the load balancer stopped routing new requests to the instance?
5. **For background workers:** have they stopped polling/subscribing, finished in-flight work, and ACKed only after side effects succeed?
6. **For connections:** does the application let Spring and the driver release resources in the right order, rather than closing the connection pool while handlers are still running?
7. **During rolling deployments:** can at least one other instance handle traffic and carry out critical work?
8. **During failover:** does the application handle unknown command outcomes, reconnect, and recover required state?

The phases can be illustrated as follows:

```text
Container/process created
           |
           v
Load config and create Spring context
           |
           v
Initialize RedisConnectionFactory / Lettuce
           |
           v
Verify essential dependencies
and initialize groups/workers as needed
           |
           v
Readiness = ACCEPTING_TRAFFIC
           |
           v
Serve HTTP + background processing
           |
           v
Receive stop / rollout / scale-down signal
           |
           v
Readiness = REFUSING_TRAFFIC
           |
           v
Stop accepting new requests and work
           |
           v
Drain in-flight work with deadline
           |
           v
ACK/commit completed work;
incomplete work remains recoverable
           |
           v
Stop listeners, schedulers, workers, and
release Redis connections
           |
           v
JVM/container exits
```

**Core point:** “the application started” is different from “the application is ready for traffic”; “shutting down” is different from “all tasks have finished”; and “sent a Redis command” is different from “received a definite result.”

## 2. Three Signals to Distinguish: Startup, Liveness, Readiness

In orchestrators like Kubernetes, three probe types serve distinct goals:

| Signal | Question | Typical Reaction |
|---|---|---|
| **Startup** | Has the process had enough time to finish initialization? | Avoid failing liveness prematurely during slow startups |
| **Liveness** | Is the process still capable of running, or is it fatally wedged? | Restart the container only when truly unrecoverable |
| **Readiness** | Should this instance receive new requests/work **right now**? | Stop routing new traffic to an unready instance |

A common mistake is putting every dependency into the liveness check:

```text
Redis temporarily loses connection
       |
       v
Liveness returns DOWN
       |
       v
Kubernetes restarts every API pod
       |
       v
New pods start simultaneously and connect to Redis
       |
       v
Redis faces heavier load; pods keep restarting
```

If an application is still healthy internally and can recover when Redis returns, **a Redis outage is usually not a good reason to fail liveness**. Readiness or a degraded mode is more appropriate, depending on Redis's business role.

Conversely, if Redis is a mandatory login session store and the app cannot authenticate requests while Redis is unavailable, API readiness may need to transition to unready. That still does not necessarily require restarting the process.

### Operational Rules

- **Liveness:** focus on the process's internal health, not every remote system.
- **Readiness:** reflect the ability to accept new work; include essential dependencies only when failure truly prevents the instance from serving.
- **Startup:** give a dedicated budget for slow starts such as JVM initialization, secret loading, or mandatory warm-up.
- **Business health:** measure worker health, backlogs, and sources of truth separately; a `PONG` does not prove business health.

## 3. Creating a Redis Bean Does Not Mean Redis Is Connected

Spring Boot can auto-configure `LettuceConnectionFactory` and `StringRedisTemplate`:

```text
Spring Boot application context
          |
          v
    Redis properties
          |
          v
 LettuceConnectionFactory
          |
          +--> StringRedisTemplate
          +--> RedisTemplate<K,V>
          +--> ReactiveRedisTemplate<K,V>
```

Depending on the driver, configuration, and lifecycle, a connection may be created or used **lazily** on the first command execution. Even when the connection factory initializes successfully, that does not prove:

- Redis DNS resolves from the application.
- TLS handshakes will succeed.
- The Redis ACL user has permissions for the required commands.
- Redis Cluster seed nodes advertise reachable addresses.
- Sentinel discovery returns a reachable current primary.
- Active namespaces, serializers, and scripts are compatible.
- Redis will still be available one second later.

For instance, a successfully injected bean:

```java
@Service
public class ProductCache {

    private final StringRedisTemplate redis;

    public ProductCache(StringRedisTemplate redis) {
        this.redis = redis;
    }
}
```

is not proof that `GET` works. Readiness is only meaningful when it validates the capabilities the instance truly needs to serve, with bounded timeouts and clear error policies.

## 4. Configuring the Redis Client with Timeouts and Security

Example Spring Boot configuration using Lettuce and a TLS-enabled internal Redis endpoint:

```yaml
spring:
  data:
    redis:
      client-type: lettuce
      host: ${REDIS_HOST}
      port: ${REDIS_PORT:6379}
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
      connect-timeout: 2s
      timeout: 2s
```

Environment variables shown are examples and contain no real credentials.

Things to confirm:

1. `REDIS_HOST` points to the private endpoint for the right environment.
2. The port speaks the expected protocol, including TLS vs. plain TCP.
3. Server certificates are trusted and hostnames are verified.
4. Username/password are valid Redis ACL credentials.
5. Timeouts fit within the application's latency budget.
6. The driver and Redis server support the configured topology.
7. Passwords and connection URIs containing credentials are never logged.
8. Excessively long timeouts are not set, which could hang shutdown or readiness checks.

**The two timeout settings serve different purposes:** connect timeout bounds connection establishment; command timeout bounds waiting for an operation's response. In addition, an HTTP request has its own overall deadline. Design timeouts together rather than inflating everything to minutes to mask a network issue.

### 4.1. Redis Standalone, Sentinel, and Cluster

Even with Spring Data Redis, endpoints differ by topology:

- **Standalone:** connects to a single Redis address; without HA, outages can last longer.
- **Sentinel:** the client must reach Sentinel as well as the discovered primary/replica Redis nodes.
- **Cluster:** the client routes by hash slot and must reach all Redis nodes advertised by the topology.

A `PING` to one seed node does not prove an entire Redis Cluster can serve every slot. When readiness demands stronger guarantees, probe representative operations or monitor topology via driver mechanisms—avoid turning every HTTP health check into a heavy scan across all shards.

## 5. Spring Boot Actuator and Health Endpoints

Spring Boot Actuator provides health endpoints and health groups for deployment integration.

Common dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

With an appropriate Redis connection factory and auto-configuration, Actuator can register a Redis health contributor. That contributor checks the Redis connection/command according to the Spring Boot/Spring Data Redis version contract.

Example:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info

  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
```

Typical endpoints:

```text
GET /actuator/health
GET /actuator/health/liveness
GET /actuator/health/readiness
```

When probes are enabled, Spring Boot uses application availability state to drive liveness and readiness. **Do not assume the Redis health contributor is automatically included in the readiness group**: default probe groups primarily reflect availability state. To make readiness depend on Redis, configure it explicitly and understand the impact.

### 5.1. Add Redis to Readiness Only When Mandatory

Example where the app cannot process requests if Redis is unavailable:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,redis
```

This assumes the Redis health contributor is registered under the name `redis` in the current version and configuration. If the application lacks that contributor or uses a different name, adjust it to match the actual contributors rather than misconfiguring the health group.

Intended effect:

```text
ReadinessState = ACCEPTING_TRAFFIC
                  +
Redis health = UP
                  |
                  v
Readiness group = UP

ReadinessState = ACCEPTING_TRAFFIC
                  +
Redis health = DOWN
                  |
                  v
Readiness group = DOWN
```

Keep in mind: if **all pods** share the same Redis and Redis fails, every pod can turn unready simultaneously, leaving the service with zero endpoints. That may be the right choice when every request depends on Redis, but it is wrong if Redis is only an optional cache with a safe database read path.

### 5.2. What If Redis Is an Optional Cache?

If Redis only accelerates a catalog cache and the app has a protected fallback:

- Keep readiness `UP` during temporary Redis errors.
- Record dedicated metrics: `redis_unavailable`, `cache_fallback_total`, database p95/p99.
- Cap fallback concurrency to prevent cascading failures.
- Alert on degradation rather than disguising it as normal cache misses.
- If fallback load approaches capacity limits, the instance may still need to shed traffic under a separate policy.

**Optional at the data level does not mean infinite fallback capacity.** A Redis outage can overwhelm the database if thousands of instances bypass the cache at once.

## 6. `PING` Only Tests a Fraction of Capability

A `PING` operation is commonly used to verify Redis answers a basic command:

```bash
redis-cli --host private-redis.example.internal \
  --port 6379 PING
```

With TLS/ACL connections, use the proper authentication and certificate trust flags; never pass real passwords on the command line or leave them in shell history.

A `PONG` result is useful, yet **does not prove**:

- The ACL user has `GET`/`SET` permissions on the keys the app needs.
- Lua scripts or Redis Streams work.
- Session repositories read/write with the right schema and serializer.
- All Redis Cluster slots are reachable.
- Replica reads meet freshness requirements.
- Downstream databases and business handlers are healthy.
- Background workers are still polling and ACKing messages.

Readiness can be layered:

| Check Level | Content | Cost/Impact |
|---|---|---|
| Process availability | Spring started and no shutdown requested | Light |
| Redis basic health | `PING` / simple command | Usually light, still needs a timeout |
| Capability check | Commands matching permissions and namespace | May require test keys/cleanup |
| Business readiness | Workers can process, sources of truth available | Can be costly if called too frequently |
| End-to-end synthetic | Test event traverses full pipeline | Run at low frequency in controlled environments |

Never put a complex write transaction inside a liveness probe invoked every few seconds. Use separate synthetic checks or an indicator reading state measured in the background.

## 7. Checking Redis Before Accepting Traffic

If Redis is a mandatory startup dependency, you can run a lightweight check in an `ApplicationRunner`. Runners execute during startup before Spring Boot marks the application fully ready.

Example:

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
public class RedisStartupCheckConfiguration {

    @Bean
    ApplicationRunner verifyRedisBeforeReady(
            StringRedisTemplate redis) {

        return args -> {
            String pong = redis.execute(
                    (RedisCallback<String>) connection ->
                            connection.ping());

            if (!"PONG".equalsIgnoreCase(pong)) {
                throw new IllegalStateException(
                        "Redis PING did not return PONG");
            }
        };
    }
}
```

In this example, if Redis is unreachable or `PING` fails, startup fails. This is **one policy** suited for when the app cannot function without Redis, not a universal default for every cache.

### 7.1. Advantages

- Detects misconfigured hosts, TLS, credentials, or ports early.
- Avoids serving requests when a critical dependency is unreachable.
- Logs errors clearly at startup rather than failing the first user request mysteriously.
- Can be combined with creating consumer groups or preparing required structures if the procedure is idempotent.

### 7.2. Limitations and Risks

- A `PING` at one instant does not guarantee Redis stays up.
- Redis-dependent startup can trigger a **restart loop** during brief Redis outages.
- Many pods starting together can create a simultaneous connection spike.
- An optional cache should not normally block the entire application from booting.
- A health check requiring only `PING` can miss ACL errors on business commands.
- If initializing data/consumer groups inside a runner, operations must be idempotent when multiple replicas start concurrently.

Therefore, pick one model clearly:

1. **Fail fast:** without Redis, the application refuses to start; suited for mandatory dependencies with coordinated restarts.
2. **Start but not ready / degraded:** context stays up to reconnect; readiness blocks Redis-dependent traffic or the app uses bounded fallbacks.

Do not mix both models unintentionally—such as failing startup immediately on Redis outage while also expecting Actuator readiness to flip back to `UP` without restarting.

## 8. Startup Retries: Bounds, Backoff, and Jitter

When Redis is not up yet, the application may need to retry connecting. However, if every replica retries every 10 ms, a recovering Redis instance gets hammered.

A bounded retry policy should define:

- Transient errors: connection refused, temporary DNS failure, failover.
- Configuration errors requiring fixes: wrong password, invalid certificate, ACL `NOPERM`, wrong key schema.
- Maximum attempts or startup deadline.
- Exponential backoff with jitter across replicas.
- Total wait time fitting inside the startup probe budget.
- Whether exceeding the deadline fails fast or keeps the app unready.

Illustrative policy example:

```text
Attempt 1: immediately at startup
Attempt 2: after ~200 ms
Attempt 3: after ~500 ms
Attempt 4: after ~1 s
Attempt 5: after ~2 s
Then: stop and report startup failure
```

These timings are examples only. Retrying an idempotent `PING` differs from retrying `INCR` or a script with side effects: **a network timeout on a write command has an unknown outcome**.

If using Redis Cluster, Lettuce can perform reconnects and topology refreshes according to driver configuration. Do not wrap every command in a custom retry loop assuming the driver will prevent duplicate side effects.

## 9. Cache Warm-Up and Data Initialization at Startup

Some applications need to prewarm hot keys, load feature flags, or create consumer groups before accepting traffic.

Distinguish:

| Task | Should It Block Readiness? | Notes |
|---|---|---|
| Mandatory Redis check | Possibly | Avoids false readiness |
| Loading critical configuration | Possibly | Must have timeout and error handling |
| Warming catalog cache | Usually not mandatory | Can run bounded in background |
| Loading millions of cache keys | Should not block startup indefinitely | Batch and rate-limit |
| Creating Redis Streams group | Required before consumer reads | Must be idempotent across replicas |
| Running schema migrations | Usually a separate deploy step | Do not let all pods migrate concurrently |
| Checking a few sample keys | Depends on requirements | Do not let health checks mutate business data |

### 9.1. Do Not Gate Readiness on Full Warm-Up

Suppose a catalog app has 100,000 products. If every pod loads the entire catalog into L1/Redis before becoming ready, rolling deploys can trigger hundreds of thousands of database queries and stall rollouts.

Instead:

- Warm a bounded set of hot keys.
- Allow the cache to warm gradually after accepting traffic if business rules permit.
- Apply concurrency limits to protect the database and Redis.
- Decouple warm-up from the request path where time and resource budgets allow.
- Monitor hit rates during the first few minutes after deployment.

**Readiness should represent ability to serve**, not “every cacheable item is already cached.”

## 10. Redis Streams: Creating Consumer Groups Without Collisions

If an application runs a Redis Streams consumer group, startup configuration must specify:

- Stream key and consumer group name.
- Distinct consumer name per worker/instance.
- Initial offset if the group does not exist yet.
- Policy when the group already exists.
- Pending recovery on worker restart.
- Rules for ACKing after business commits.

Redis CLI example:

```bash
redis-cli XGROUP CREATE stream:orders:v1 order-workers 0 MKSTREAM
```

`0` lets the group receive retained history from the start of the stream; creating with `$` starts from the tail at creation time and can miss older events when reading new messages.

A `BUSYGROUP` error occurs if the group already exists. In multi-replica deployments, this is normal when instances start concurrently.

**Do not delete and recreate the group on every startup** to “fix” `BUSYGROUP`. Doing so wipes delivery progress and the PEL of unACKed events. Group creation must be idempotent and explicitly tolerate only the “group already exists” error; connection or ACL errors must never be swallowed as success.

### 10.1. Having No New Events Does Not Mean Consumer Readiness Is Broken

A consumer polling Redis may receive an empty list simply because the stream has no new events. That is normal provided:

- Group and stream are properly configured.
- Redis remains reachable.
- The consumer is still actively polling on schedule.
- It is not stuck in an error loop.

Do not mark readiness `DOWN` just because `XREADGROUP ... >` returns empty. Distinguish **healthy idle** from **dead worker thread**, **polling halted by errors**, and **stuck PEL**.

## 11. API Readiness Differs from Background Consumer Readiness

A single process can serve HTTP requests while also consuming Redis Streams. In that case there are at least two kinds of “ready”:

```text
Spring Boot process
       |
       +--> HTTP API
       |      |
       |      +-- Can it accept requests?
       |
       +--> Redis Streams consumer
              |
              +-- Is it polling?
              +-- Does it have processing capacity?
              +-- Is PEL recovery working?
```

If the worker fails while the API can still serve requests safely, you can:

- Keep HTTP readiness `UP`.
- Emit an alert `stream_consumer_unhealthy`.
- Recover the worker or scale a dedicated worker pool.
- Split workers into a separate deployment when scaling and failure domains differ.

If the API relies on Redis to validate sessions and a Redis outage breaks every protected request, transitioning HTTP readiness to `DOWN` makes more sense.

**A single readiness endpoint cannot always represent both HTTP and every background task.** Define each probe's purpose clearly before letting Kubernetes orchestrate pods with it.

## 12. Custom `HealthIndicator` for Specific Serving Capabilities

Sometimes `PING` is too shallow—for example, a worker stops polling while Redis still replies `PONG`. You can build a custom health contributor observing worker state, as long as the check is **lightweight and side-effect-free**.

Example:

```java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("orderConsumer")
public class OrderConsumerHealthIndicator
        implements HealthIndicator {

    private final OrderConsumerState state;

    public OrderConsumerHealthIndicator(OrderConsumerState state) {
        this.state = state;
    }

    @Override
    public Health health() {
        if (state.isRunning()
                && state.secondsSinceLastSuccessfulPoll() < 30) {
            return Health.up().build();
        }

        return Health.down()
                .withDetail("reason", "consumer-not-polling")
                .build();
    }
}
```

`OrderConsumerState` is an application-defined state tracker. When a Redis Stream is quiet for a long period, successful empty polls must still update the heartbeat; never update the timestamp only when a message arrives, or a healthy idle consumer will report `DOWN`.

To include the indicator in the readiness group when truly warranted:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,redis,orderConsumer
```

Use this only when both `redis` and `orderConsumer` contributors actually exist in the application context. If the consumer should not dictate HTTP readiness, expose a separate health group rather than marking every API pod unready over a non-essential worker.

### 12.1. Avoid Load-Inducing Health Checks

Every Kubernetes readiness poll must NOT:

- Create and delete consumer groups.
- Scan the entire PEL.
- Run `KEYS *` on Redis.
- Publish a business event.
- Execute a long database transaction.
- Run scripts with side effects.
- Probe every slot/replica with hundreds of commands per second.

Readiness endpoints are polled frequently; if a probe generates heavy load and times out, it can become the cause of an outage.

## 13. Kubernetes Startup, Readiness, and Liveness Probes

Example Deployment for Spring Boot with Actuator on application port 8080:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
    spec:
      terminationGracePeriodSeconds: 75
      containers:
        - name: app
          image: example/catalog-api:1.0
          ports:
            - containerPort: 8080

          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 5
            failureThreshold: 30

          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 10
            failureThreshold: 3

          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
            failureThreshold: 2
```

This is a probe configuration example, omitting `env`/`secretKeyRef`, resource requests/limits, Services, NetworkPolicies, and Redis resources.

Meaning:

- `startupProbe` gives the app enough startup window before regular liveness checks begin.
- `livenessProbe` catches fatally wedged processes needing restart and should not depend directly on every external service.
- `readinessProbe` controls whether the pod is added to traffic-serving endpoints.
- `terminationGracePeriodSeconds` gives the pod time to handle `SIGTERM` and shut down gracefully before forceful termination.

These thresholds are **illustrative values**. For slower-starting apps, Redis TLS failovers, or long in-flight tasks, pick values from actual measurements.

### 13.1. Serving Probes on a Different Management Port?

If Actuator runs on a management port separate from the main HTTP port, checking only the management port can miss failures in the main HTTP connector.

Spring Boot provides mechanisms to expose health probes on the main server port depending on version. Verify your project's exact Actuator setup and confirm Kubernetes calls the real port and path.

Do not assume two ports share the same health merely because they live in the same JVM.

### 13.2. Readiness Failing Does Not Cancel In-Flight Requests

Kubernetes stops routing **new** requests to an unready pod once endpoints and proxies update, yet:

- Requests already delivered to the pod are still executing.
- HTTP keep-alive connections may persist.
- Endpoint propagation has latency.
- Traffic outside Kubernetes Services, such as direct Pod IP callers, behaves differently.

Therefore, shutdown also needs **graceful HTTP draining**, not just flipping readiness to `DOWN`.

## 14. Spring Boot Graceful Shutdown

Spring Boot supports graceful shutdown for embedded web servers. Example:

```yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 25s
```

When asked to stop cleanly, the web server stops accepting new requests and gives in-flight requests time to finish according to server/phase mechanics. Spring's lifecycle can manage `SmartLifecycle` components in phase order.

Things to understand:

- `server.shutdown: graceful` covers the **HTTP web server**; it does **not automatically guarantee all Redis Streams handlers, scheduled tasks, or custom threads have drained**.
- `timeout-per-shutdown-phase` is the budget **per lifecycle phase**, not a single global deadline for the entire shutdown.
- With multiple phases, total shutdown time adds up; align it with `terminationGracePeriodSeconds`.
- A request blocked on Redis for 2 minutes will not finish in 25 seconds; Redis client timeouts and HTTP deadlines must coordinate.
- Once the Kubernetes grace period expires, the container can be killed forcefully; unfinished work needs a recovery mechanism.

### 14.1. Shutdown Ordering Between HTTP and Redis Workers

A safe strategy:

```text
Receive SIGTERM
      |
      v
Readiness stops accepting new traffic
      |
      v
Gracefully stop HTTP web server
      |
      v
Stop polling Redis / subscribing to new streams
      |
      v
Wait for in-flight handlers, ACK completed events
      |
      v
Stop background listeners / schedulers
      |
      v
Close Redis connection factory / driver resources
      |
      v
Process exits
```

Depending on architecture, workers may start draining in parallel with HTTP to shorten total shutdown time. What matters is not millisecond precision, but **never closing Redis connections while code still needs them to ACK or persist results**.

## 15. Spring Lifecycle: `@PreDestroy` vs. `SmartLifecycle`

Spring offers multiple hooks:

| Mechanism | Role | Notes |
|---|---|---|
| `@PostConstruct` | Bean initialization after dependency injection | Should not perform unbounded blocking startup |
| `ApplicationRunner` / `CommandLineRunner` | Run tasks during Spring Boot startup | Can affect when readiness is reached |
| `ApplicationReadyEvent` | Event when application reaches ready stage | Not ideal by default for work that must finish before ready |
| `AvailabilityChangeEvent` | Publish/update availability state | Use proper state transitions |
| `ContextClosedEvent` | Signals context is closing | Can mark draining or signal stop |
| `@PreDestroy` | Bean cleanup before destruction | Does not manage drain order across all dependencies |
| `SmartLifecycle` | Phased start/stop with async stop callback | Useful when background workers need draining |
| Container `SIGTERM` | Process termination signal | Must reach the JVM, not be swallowed by a shell wrapper |

### 15.1. What Is `@PreDestroy` Good For?

Example of a resource **created and owned by the bean itself**:

```java
import jakarta.annotation.PreDestroy;
import java.util.concurrent.ExecutorService;

public class LocalRefreshWorker {

    private final ExecutorService executor;

    public LocalRefreshWorker(ExecutorService executor) {
        this.executor = executor;
    }

    @PreDestroy
    public void requestStop() {
        executor.shutdown(); // Stop accepting new tasks.
    }
}
```

This only **requests** shutdown; it does not prove all tasks finished. If a resource is a Spring-managed shared bean, ownership of closing it must be clear so one component does not shut down an executor still used by another.

**Never call `lettuceConnectionFactory.destroy()` arbitrarily inside a service's `@PreDestroy`** just to “close Redis early.” Spring manages the connection factory lifecycle; premature destruction breaks other services and listeners finishing their work.

### 15.2. When Is `SmartLifecycle` Needed?

If a bean actively runs Redis polling threads or background message listeners, `SmartLifecycle` allows you to:

- Start when the application context reaches the appropriate lifecycle phase.
- Stop **accepting new work** immediately on context shutdown.
- Wait for in-flight tasks up to a deadline.
- Invoke the stop callback once finished so Spring advances to the next phase.
- Ensure the Redis connection factory stays alive until dependent workers no longer need it, via verified phase ordering.

**Do not assume every Redis listener container uses the same phase and stop behavior.** Check the lifecycle contract of your actual Spring Data Redis version.

## 16. `SmartLifecycle` Example for a Redis Streams Worker

The following example illustrates a synchronous worker managing a single thread polling Redis Streams. The consumer group is assumed to be created beforehand via an idempotent step. The worker only sends `XACK` after the handler succeeds.

```java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.SmartLifecycle;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderStreamWorker implements SmartLifecycle {

    private static final Logger log =
            LoggerFactory.getLogger(OrderStreamWorker.class);

    private static final String STREAM = "stream:orders:v1";
    private static final String GROUP = "order-workers";
    private static final String CONSUMER = "order-worker-a";

    private final StringRedisTemplate redis;
    private final OrderEventHandler handler;

    private final AtomicBoolean acceptingWork =
            new AtomicBoolean(false);
    private final AtomicBoolean started =
            new AtomicBoolean(false);

    private final ExecutorService worker =
            Executors.newSingleThreadExecutor(r -> {
                Thread thread = new Thread(r, "redis-order-consumer");
                thread.setDaemon(false);
                return thread;
            });

    public OrderStreamWorker(
            StringRedisTemplate redis,
            OrderEventHandler handler) {
        this.redis = redis;
        this.handler = handler;
    }

    @Override
    public void start() {
        if (started.compareAndSet(false, true)) {
            acceptingWork.set(true);
            worker.execute(this::pollLoop);
        }
    }

    private void pollLoop() {
        while (acceptingWork.get()) {
            try {
                List<MapRecord<String, Object, Object>> records =
                        redis.opsForStream().read(
                                Consumer.from(GROUP, CONSUMER),
                                StreamReadOptions.empty()
                                        .count(10)
                                        .block(Duration.ofMillis(200)),
                                StreamOffset.create(
                                        STREAM,
                                        ReadOffset.lastConsumed()));

                if (records == null || records.isEmpty()) {
                    continue;
                }

                // Entries in the batch have already been delivered by Redis,
                // so stopping mid-batch requires PEL recovery.
                for (MapRecord<String, Object, Object> record : records) {
                    if (Thread.currentThread().isInterrupted()) {
                        return;
                    }

                    handler.handle(record.getValue());

                    // ACK only after the business side effect completes.
                    redis.opsForStream().acknowledge(
                            STREAM, GROUP, record.getId());
                }
            } catch (RuntimeException error) {
                log.warn("Redis Streams poll/handler failed", error);

                if (!acceptingWork.get()) {
                    return;
                }

                try {
                    Thread.sleep(250);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }
    }

    @Override
    public void stop(Runnable callback) {
        acceptingWork.set(false);
        worker.shutdown();

        Thread waiter = new Thread(() -> {
            try {
                boolean terminated =
                        worker.awaitTermination(
                                20, TimeUnit.SECONDS);

                if (!terminated) {
                    log.warn("Worker drain deadline exceeded");
                    worker.shutdownNow();
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                worker.shutdownNow();
            } finally {
                started.set(false);
                callback.run();
            }
        }, "redis-order-consumer-shutdown");

        waiter.setDaemon(true);
        waiter.start();
    }

    @Override
    public void stop() {
        acceptingWork.set(false);
        worker.shutdown();
    }

    @Override
    public boolean isRunning() {
        return started.get() && acceptingWork.get();
    }

    @Override
    public int getPhase() {
        return 10_000;
    }
}
```

The business handler is an application-defined interface:

```java
import java.util.Map;

public interface OrderEventHandler {
    // Return only once the required side effect has committed.
    // Throw an exception if success cannot be confirmed.
    void handle(Map<Object, Object> event);
}
```

### 16.1. What This Example Demonstrates

- `start()` starts the poll loop once during the context lifecycle.
- `acceptingWork=false` stops the loop from beginning another poll after finishing the current batch.
- `block(200ms)` keeps each poll deadline short enough to respond promptly to shutdown.
- `stop(Runnable)` hands control back to Spring and fires the callback after a bounded drain wait.
- The handler runs before `XACK`.
- If the handler fails or is interrupted before ACK, the entry must be recovered from the PEL.
- `getPhase()` is illustrative: higher phases stop before lower phases. Verify the phases of your connection factory and other listeners in the app.
- A fixed consumer name is unsuitable if multiple instances share that name without ownership rules. Production should generate stable consumer identities per instance/slot or use a clear consumer management strategy.
- The example assumes **a single startup per context**; a shut-down executor cannot be reused across stop/restart cycles on the same bean. If repeated start/stop/restart is needed, redesign executor creation and state synchronization.

### 16.2. Limitations of This Demo

This is a lifecycle illustration, not a complete production Redis Streams framework:

- No pending recovery (`XCLAIM`/`XAUTOCLAIM`).
- No poison-message retry/DLQ.
- No business idempotency.
- No multi-worker parallel backpressure.
- No primary/replica coordination or Spring Security integration.
- `worker.shutdownNow()` only sends an interrupt; if the handler ignores interrupts or blocks on I/O, the task may still not exit immediately.
- Invoking the callback after the deadline does not prove every side effect completed; rely on commits/ACKs/PEL to know actual state.
- Exception stop logic and backoff must be tuned to availability requirements.

In production, measure maximum processing durations, choose deadlines carefully, and **design so unACKed entries can always be recovered after forced process termination**.

## 17. Stopping Polling Is Not the Same as ACKing All Received Messages

A Redis Streams consumer group maintains a **Pending Entries List** for delivered but unACKed entries:

```text
XREADGROUP receives e1, e2, e3
          |
          v
PEL = {e1, e2, e3}
          |
          v
Handler commits e1 -> XACK e1
          |
          v
SIGTERM arrives while processing e2
          |
          +-- e2 not committed: DO NOT ACK
          |
          +-- e3 delivered but unprocessed: DO NOT ACK
          |
          v
Shutdown
          |
          v
Next worker starts and recovers e2, e3 from PEL
```

Note two cases:

1. **Stopped before polling:** new messages remain in the stream, undelivered.
2. **Stopped after receiving a batch:** unACKed messages remain in the PEL and will not be re-delivered automatically when reading `XREADGROUP ... >`.

A restarting worker must handle both **new messages** and **pending recovery** appropriately—never simply create a new subscription assuming all unfinished work returns on its own.

### 17.1. Pending Recovery

Useful Redis commands:

```bash
redis-cli XPENDING stream:orders:v1 order-workers

redis-cli XAUTOCLAIM stream:orders:v1 \
  order-workers order-worker-b 60000 0-0 COUNT 100
```

`60000` is a minimum idle threshold in milliseconds (example only). A new consumer should not claim too early while the old worker is still legitimately draining.

`XAUTOCLAIM` returns a cursor, so loop across batches if the pending list is large. Claiming does not ACK; the new worker must process the event and ACK after success.

### 17.2. Crash After DB Commit Before ACK

```text
Worker A:
    DB commit ORDER_PAID succeeds
    JVM dies before XACK

Worker B:
    reclaims event
    handler runs again
```

Therefore, events need an `eventId`/version so handlers are **idempotent**. Redis consumer groups support responsibility recovery; they do not by themselves make business side effects execute once.

## 18. Redis Pub/Sub Listeners: Limitations During Shutdown

For Redis Pub/Sub, many applications use `RedisMessageListenerContainer`. Unlike Redis Streams consumer groups, standard Pub/Sub **has no PEL, ACK, or durable replay** for messages published while a subscriber is offline.

If a process shuts down:

```text
Publisher sends event A
          |
          v
Connected listener -> can receive A

Listener stopped or disconnected
          |
          v
Publisher sends event B
          |
          v
That subscriber may miss B
```

This matters if Pub/Sub is used for:

- Local cache invalidation.
- Best-effort notifications.
- Broadcasting state refresh signals.
- Workloads without replay requirements.

**Never use Pub/Sub as a durable queue** for payments, audits, idempotency, or mandatory business tasks. If messages must not be lost during deploys, use Redis Streams, an ACKable queue, or a durable event system.

### 18.1. Stopping the Listener Container

For Spring-managed listeners:

- Let Spring orchestrate the container lifecycle.
- If necessary, stop per the container's contract before Redis resources are released.
- Stop accepting new callbacks once the service enters the non-accepting state.
- Update local state defensively; never rely on a final notification being guaranteed to arrive.
- Upon restart, rely on TTLs, versions, or reconciliation for missed invalidations.

No default listener stop order guarantees that every Pub/Sub message sent before `SIGTERM` gets processed. Define a missing-data policy and resynchronize after reconnect.

## 19. `ReactiveRedisTemplate`: Subscriptions and Cancellation on Shutdown

In WebFlux applications, reactive Spring Data Redis returns `Mono`/`Flux`. Shutdown must distinguish:

- **Stop creating new subscriptions** for periodic tasks.
- **Cancel** infinite-stream subscriptions per policy.
- **Wait for in-flight async handlers** to complete within bounds.
- **Do not treat cancellation as rolling back** an already-sent Redis command.
- **Do not ACK** a Redis Stream entry before the reactive handler confirms completion.

A conceptual reactive stream pattern:

```java
receiver.receive(
        Consumer.from(group, consumerName),
        StreamOffset.create(
                stream, ReadOffset.lastConsumed()))
    .concatMap(record ->
        handleBusiness(record)
            .then(ackAfterCommit(record)));
```

where `handleBusiness` and `ackAfterCommit` are application-defined publishers.

Using `flatMap` with high unbounded concurrency can leave many handlers mid-flight during shutdown. Bound in-flight concurrency and set timeouts so draining is feasible.

### 19.1. Cancellation Does Not Undo Executed Effects

Suppose:

```text
T0: Reactive subscription sends EVAL script to Redis.
T1: Process receives SIGTERM; subscription is cancelled.
T2: Redis may still execute and finish the script.
T3: Client never receives the result.
```

Never infer from cancellation that a script did not mutate data. With `INCR`, Lua scripts, reservations, or multi-step writes, timeouts/cancellations create an **unknown outcome**. Any retry after restart must rely on idempotency or reconciliation.

### 19.2. Do Not Block the Event Loop to Drain

Never call a long `.block()` on a Reactor Netty event-loop thread just to wait for Redis to finish. Use lifecycle callbacks and proper async coordination; if a blocking adapter is unavoidable, isolate it on an appropriate scheduler/thread with a deadline.

## 20. Connection Pooling and Releasing Resources

Spring Data Redis uses connection factories and drivers to manage Redis connections. With Lettuce, resources may include:

- Netty event loops.
- Redis clients/cluster clients.
- Physical connections to Redis nodes.
- Connection pools if enabled for specific use cases.
- Pub/Sub connections and subscriptions.
- Topology discovery/reconnect tasks.
- Timeouts, pending command buffers, and metrics.

**Ownership** principle:

| Resource | Who Should Own Its Lifecycle? |
|---|---|
| Spring-created `LettuceConnectionFactory` bean | Spring context / infrastructure config |
| `RedisTemplate`/`StringRedisTemplate` | Spring bean using the connection factory |
| `RedisMessageListenerContainer` bean | Spring lifecycle or explicitly managing component |
| `StreamMessageListenerContainer` bean | Spring lifecycle and worker orchestration |
| Service-created `Executor` | That service must shut down and release it |
| Manually created native Lettuce client | The creating component must close it properly |
| Manually obtained `RedisConnection` from factory | Caller releases per API, usually `close()` |
| Service-created reactive subscription/`Disposable` | That service must handle cancellation/cleanup |

### 20.1. Do Not Destroy the Connection Factory After Each Request

Lifecycle mistake:

```java
public String readAndClose(String key) {
    String value = redis.opsForValue().get(key);
    lettuceConnectionFactory.destroy(); // Do not do this here.
    return value;
}
```

The connection factory is shared infrastructure. Destroying it mid-run will break every other request's Redis commands, cache managers, stream listeners, and session services.

### 20.2. Closing Low-Level `RedisConnection` When Acquired Manually

If an operational tool acquires a low-level connection:

```java
import org.springframework.data.redis.connection.RedisConnection;
import org.springframework.data.redis.connection.RedisConnectionFactory;

public String pingRedis(RedisConnectionFactory factory) {
    try (RedisConnection connection = factory.getConnection()) {
        return connection.ping();
    }
}
```

Note that `close()` on this abstraction may return the connection to a pool or release a wrapper depending on implementation; do not assume it always closes the underlying physical socket.

With `RedisTemplate`, you typically do not acquire/close low-level connections manually: the template and connection factory manage per-operation lifecycles.

### 20.3. Lettuce Shared Connections

Lettuce shares connections differently depending on command type and factory configuration. Never manually close a shared native connection inside the driver when the service does not own it.

If using a native Lettuce client directly outside Spring, manage its lifecycle via the driver API and close it **after** all tasks using it have finished.

## 21. Shutdown Order When Running Multiple Workload Types

A real application may concurrently run:

- HTTP requests serving caches.
- Scheduled jobs warming data.
- Redis Pub/Sub listeners for invalidation.
- Redis Streams consumers writing to a database.
- Spring Session storing login sessions.
- Metrics/health endpoints.
- A background cache-refresh executor.

If shut down in the wrong order:

```text
SIGTERM
    |
    v
Close Redis connection factory immediately
    |
    v
Stream handler finishes commit but cannot XACK
Cache refresh tasks fail
In-flight session requests fail while saving
Listeners throw exceptions
```

A controlled strategy:

1. Signal that the application **is no longer accepting new traffic**.
2. Let the HTTP web server drain active requests.
3. Stop schedulers and consumers from taking new tasks.
4. Wait for in-flight tasks within a bounded timeout.
5. ACK/commit only genuinely completed work.
6. Stop Redis listener containers and subscriptions.
7. Close application-created resources.
8. Let Spring close the connection factory once dependent beans have stopped.
9. Emit final metrics/logs **containing no secrets**, reporting remaining pending/in-flight counts.
10. Exit within the container grace period.

Actual order must be verified against the application's phases and dependency graph; a system may drain HTTP and background tasks in parallel to save time. Just **never let Redis shutdown cut off handlers still expected to ACK**.

## 22. Rolling Deployments: Never Take All Replicas Unavailable Simultaneously

In Kubernetes, a rollout typically proceeds as:

```text
Version v1: App A, App B, App C (ready)
              |
              v
Kubernetes creates App D (v2)
              |
              v
App D starts -> readiness UP
              |
              v
Kubernetes terminates App A (v1)
              |
              v
App A gracefully drains and exits
              |
              v
Proceed to replace B/C
```

To minimize downtime:

- Configure `RollingUpdate` with an appropriate `maxUnavailable`.
- Add new pods to the Service only after readiness is `UP`.
- Ensure the startup probe gives enough time for mandatory warm-up.
- Set `terminationGracePeriodSeconds` large enough for request/worker draining.
- Watch resource limits when `maxSurge` creates extra pods.
- Do not let every instance run non-idempotent Redis migrations concurrently.
- For Streams, give each worker a proper consumer name/ownership; old worker pending items are recovered after an idle threshold.
- For cache/session serializers, v1 and v2 may access Redis concurrently for a time; plan compatibility and migration.

### 22.1. `SIGTERM` Must Reach the JVM

A Dockerfile or entrypoint shell can prevent `SIGTERM` from reaching the Java process unless PID 1/`exec` handling is set up properly. Otherwise Kubernetes waits out the timeout and sends `SIGKILL`, bypassing graceful shutdown.

Example standard shell entrypoint:

```sh
#!/bin/sh
exec java -jar /app/app.jar
```

`exec` replaces the shell with the JVM so Java receives signals directly from the container runtime.

When running Java directly via Dockerfile exec form:

```dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

the JVM can also act as PID 1. Signal handling depends on entrypoint, init process, orchestrator, and OS policies; always **test real `SIGTERM` in a test environment** rather than just reading the Dockerfile.

## 23. `PreStop` and `terminationGracePeriodSeconds`

Kubernetes can invoke a `preStop` hook before terminating a container. Some teams use hooks to signal draining or wait for endpoint propagation.

Remember:

- `preStop` duration **counts toward** the container termination grace period.
- A bare `sleep` does not guarantee handlers, transactions, or Redis ACKs have completed.
- If `preStop` hangs, remaining time for the JVM to receive `SIGTERM` and shut down shrinks.
- Any hook calling an internal endpoint should have a deadline and proper auth/policy.
- Do not rely solely on readiness `DOWN` and forget existing persistent connections.

Illustrative budget example:

```text
Container termination grace: 75 seconds

Endpoint propagation / preStop: 5 seconds
Web request graceful drain: 20 seconds
Redis stream worker drain: 20 seconds
Resource cleanup & margin: 10 seconds
Projected total: 55 seconds
Headroom: 20 seconds
```

This is a budgeting method, not a Redis/Spring/Kubernetes default. If shutdown phases run sequentially or a handler hits a long timeout, calculate **actual cumulative time**. Measure worst-case times in load tests and rolling deploys.

## 24. Do Not Equate Redis Unavailable with Application Dead

Redis can fail while the application is serving:

```text
Redis primary failover
        |
        v
Some commands timeout/reconnect
        |
        v
Lettuce updates connections/topology
        |
        v
Redis becomes operational again
```

During the fault:

- App **liveness** can stay `UP` if the process is still healthy.
- **Readiness** can go `DOWN` if Redis is mandatory, then return to `UP` upon recovery.
- Cache-only requests can use bounded fallbacks.
- Session-based auth may need to fail closed.
- Stream consumers must not ACK messages when handlers fail.
- Write commands with side effects may have unknown outcomes if the client timed out after Redis executed them.

### 24.1. Connection Restored Does Not Mean Work Is Recovered

When the driver reconnects successfully:

- Pub/Sub requires subscriptions to be re-established by the container/driver and may still have lost messages during the outage.
- Redis Streams must read new messages **and** recover old pending entries.
- A distributed lock lease may have expired; never assume you still hold the lock just because you reconnected.
- A timed-out batch write may have partially applied; reconcile it.
- Replica reads may be temporarily stale after failover.

**Readiness returning `UP` after reconnect does not prove missed side effects completed.** Business recovery and infrastructure connectivity are distinct responsibilities.

## 25. Redis Sessions: How Shutdown Affects Users

Spring Session Data Redis can store `HttpSession` in Redis. During rolling deployments:

- In-flight requests need time to complete and persist session state per Spring Session mode.
- New pods must use a compatible session namespace, serializer, and schema.
- Browser cookies still point to session IDs stored in Redis.
- Redis failures can prevent validating active sessions.
- Never allow protected requests just because reading the session errored.

A deployment with a shared Redis session store avoids losing sessions when one pod is replaced, yet does not automatically finish in-flight requests. If the JVM receives `SIGKILL` mid-save or during a Redis outage, session updates can be lost.

Test across multiple replicas: log in on v1, hit v2, log out/revoke, test timeouts, and test Redis failover. Never break session schema/serialization compatibility during a rolling deploy.

### 25.1. Do Not Wipe All Sessions When an Instance Stops

Sessions live in a shared repository, **not inside one app instance's lifecycle**. When App A shuts down, it must never run `DEL spring:session:*` or purge sessions just because it is stopping.

Session deletion must come from logout, expiration, revocation, or intentional administration—not container replacement.

## 26. Health Checks Across Multiple Redis Cluster Nodes

In Redis Cluster, keys are partitioned across hash slots:

```text
Client
  |
  v
Lettuce Cluster
  |
  +--> Primary A: slot group A
  +--> Primary B: slot group B
  +--> Primary C: slot group C
```

A health check pinging only one seed node can report `UP` while:

- Primary B is unreachable.
- The client fails to follow `MOVED`/`ASK` after resharding.
- Another node's TLS certificate has a hostname mismatch.
- A slot range is failing.
- Replica lag exceeds limits on replica-read paths.

Yet a readiness probe **hitting every primary on every poll** can create unnecessary load and become a source of latency.

A balanced approach:

1. Basic Actuator health with a short timeout.
2. Dedicated Redis Cluster metrics: cluster state, slot coverage, unavailable nodes, redirect/reconnect failures.
3. Lightweight synthetic checks across a few representative slots at low frequency.
4. Alerts when unavailable slots/shards or command timeouts rise.
5. Readiness policy matched to business capability: some endpoints may degrade while others continue serving.

With Sentinel, health must consider both discovering the new primary and reaching its advertised address. A successful `PING` to Sentinel **does not mean** the client is connected to the Redis primary serving data commands.

## 27. Closing Connections in Redis Cluster/Sentinel

At app shutdown, Lettuce may hold connections to many nodes plus topology/reconnect tasks. The principles match standalone, with extra points:

- Do not manually close a shared native connection managed by the connection factory.
- Stop background stream/pipeline jobs before driver resources are released.
- If commands are awaiting responses at shutdown, define timeout and unknown-outcome policies.
- Stop reconnect tasks when the app exits so native client threads do not keep the JVM alive unexpectedly.
- All topology nodes/replicas should be released via driver lifecycle, not only the seed connection.
- Prevent health probes or scheduled jobs from opening new connections once draining starts.

When Spring Boot manages `LettuceConnectionFactory`, normally let Spring's lifecycle/destruction handle cleanup. If the application creates a manual client, that component must clean it up explicitly and in the proper order.

## 28. Shutdown Mistakes and Data-Loss Risks

| Mistake | Consequence | Fix |
|---|---|---|
| Closing Redis connections immediately on `SIGTERM` | Handlers cannot ACK/persist | Drain workers before connection cleanup |
| ACKing an entire batch when stopping | Unprocessed messages marked done | ACK each event after business success |
| Reading only `>` on restart | Old worker's PEL forgotten | Run pending recovery on startup |
| Waiting indefinitely on blocking reads | Shutdown hangs past deadline | Bounded `BLOCK`/interrupt/lifecycle |
| Tying liveness directly to Redis | Redis outage triggers pod restart storm | Separate process liveness from dependencies |
| Omitting mandatory Redis from readiness | Pods accept traffic and fail constantly | Include appropriate readiness contributor |
| Optional Redis cache marks all pods unready | Zero HTTP endpoints despite fallback | Align dependency policy to business role |
| Using `PING` as a whole-Cluster test | Misses slot/ACL/business failures | Use metrics and targeted synthetic checks |
| Failing startup forever during brief Redis failover | Restart loop / cold-start storm | Bounded retries and readiness policy |
| Prewarming millions of keys before ready | Slow rollouts, DB spike | Bounded/async warm-up |
| Stopping Pub/Sub listener assuming zero missed events | Missed invalidations | TTLs/versions/reconciliation |
| Cancelling reactive publisher and assuming rollback | Side effects may already have run | Idempotency / unknown-outcome handling |
| Using `@PreDestroy` to destroy shared factory | Other beans lose Redis early | Let Spring manage the factory |
| `SIGTERM` not reaching the JVM | `SIGKILL` skips cleanup | Proper entrypoint, test termination |
| Grace period shorter than handler timeout | Killed mid-drain | Align deadlines and recovery |
| Every replica creates group by deleting/recreating | Pending state wiped | Idempotent creation, preserve groups |
| Incompatible session schema change | Users logged out during rollout | Serialization/version migration |
| Health endpoint runs heavy writes/scans | Probes overload Redis | Lightweight probes, separate synthetic tests |
| Blindly retrying write commands after timeout | Duplicate side effects | Operation IDs / idempotent handlers |

## 29. Testing Startup and Shutdown Lifecycles

Do not verify only “ran the app and saw the Started log.” Verify each system-level behavior.

### 29.1. Startup Tests

| Scenario | What to Verify |
|---|---|
| Redis running | Readiness `UP` per policy, real commands succeed |
| Redis not yet up | App fails fast or stays unready/degraded per design |
| Wrong Redis DNS | Bounded timeout, diagnosable error |
| Invalid TLS certificate | Certificate validation is not bypassed |
| Redis ACL user lacks permissions | Not masked as a cache miss |
| Redis Cluster missing a slot | Health/metrics detect issue per SLO |
| Consumer group already exists | Startup is idempotent, group not reset |
| Empty Redis Stream | Healthy idle consumer, no false `DOWN` |
| Cold cache start | Latency/QPS stay within warm-up budget |
| Many pods starting concurrently | No connection storm or migration race |

### 29.2. Readiness/Liveness Tests

- Brief Redis outages must not cause infinite app restarts due to bad liveness.
- Readiness goes `DOWN` when a truly mandatory dependency is unavailable.
- Readiness returns `UP` once the dependency recovers and the process can serve.
- If Redis is only an optional cache, bounded fallbacks still work.
- Health checks do not expose sensitive data to the Internet.
- Probe timeouts do not overload Redis or the database.
- App does not receive traffic before mandatory startup steps complete.

### 29.3. Graceful Shutdown Tests

1. Start multiple API replicas and a Redis Streams worker.
2. Send long HTTP requests or generate a batch of events.
3. Send `SIGTERM` to one instance.
4. Observe readiness stop accepting new traffic.
5. Verify in-flight requests have a chance to finish within the grace period.
6. Verify the worker stops polling new Redis batches.
7. Verify completed events are ACKed while incomplete events remain pending.
8. Start another worker and claim/recover pending events.
9. Verify business side effects are not duplicated.
10. Verify the JVM/process exits within the deadline with no leaked threads or connections.
11. Repeat with a Redis failover timed right during shutdown.
12. Measure actual total duration and tune the grace period.

You do not need one giant monolithic integration test. Split startup, HTTP drain, Redis worker stop, PEL recovery, and failover tests for easier diagnosis.

## 30. Example of a Controlled Deployment Sequence

A typical rollout for an app with an API + Redis Streams worker:

```text
T0: App v1 serves HTTP; consumer v1 is processing.

T1: Kubernetes creates App v2.
    App v2 builds Spring context, Lettuce factory.
    Startup check verifies required Redis.
    Consumer v2 gets proper group/identity.

T2: App v2 passes readiness.
    Kubernetes adds v2 to Service.

T3: App v1 receives SIGTERM.
    Liveness still reports process alive;
    readiness refuses new traffic.

T4: Web server v1 drains requests within deadline.
    Redis Streams consumer v1 stops polling new batches.
    Committed handlers ACK their events.

T5: If an event has not completed:
    do not ACK.
    Redis PEL keeps it pending if payload remains.

T6: Worker v2 after proper idle/ownership threshold
    claims pending entries and processes idempotently.

T7: App v1 stops listeners/executors,
    Spring closes Lettuce factory.
    Process exits within grace period.

T8: Monitor Redis connection count,
    pending age, business success, HTTP p99.
```

Steps do not necessarily execute strictly sequentially in every framework. This is the **desired behavioral contract** for designing phases and lifecycles, not a claim that Spring Boot performs every Redis Streams step automatically.

## 31. Pre-Production Checklist

**Connection Configuration**

- Redis endpoint sits on an allowed network with working TLS/ACL.
- Redis client timeouts are explicitly defined.
- Lettuce topology/discovery matches Standalone, Sentinel, or Cluster.
- No hardcoded secrets; certificates and credentials have rotation plans.

**Startup**

- Clear distinction whether Redis is a mandatory dependency or optional cache.
- Startup deadlines and retries are bounded.
- Dangerous migrations are not executed on every pod startup.
- Consumer group creation is idempotent; pending recovery has a procedure.
- Readiness is not blocked by unnecessary warm-up.

**Health/Readiness**

- Startup, liveness, and readiness each serve distinct purposes.
- Liveness is not tied to transient Redis outages in a way that triggers restart storms.
- Readiness reflects ability to accept new requests.
- Custom health contributors are lightweight and side-effect-free.
- Redis Cluster metrics do not rely solely on `PING`ing one seed node.
- Probe ports and paths match Actuator configuration.

**Shutdown**

- `SIGTERM` actually reaches the JVM.
- `server.shutdown: graceful` and Spring lifecycle timeouts are set appropriately.
- Kubernetes termination grace period covers all required phases.
- HTTP and background work stop accepting new load once draining starts.
- Redis Streams ACK happens after commit, never prematurely.
- Pending events remain recoverable.
- Pub/Sub handles missed notifications safely.
- Reactive cancellation is not mistaken for rollback.
- Connection factory closes after all dependent consumers/handlers stop.

**Testing and Observability**

- Tested Redis outages, failovers, rolling deploys, and `SIGTERM` under load.
- Monitoring p95/p99 HTTP, Redis command timeouts, reconnects, and pending count/age.
- Never log passwords, session IDs, or tokens.
- Alerts configured for stuck workers, aging PEL entries, readiness flapping, and memory/connection spikes.
- Rollback procedure exists when v2 cannot read v1 cache/session schemas.

## 32. Summary

**Startup, readiness checks, and graceful shutdown** in Spring Data Redis require managing both **application state** and **in-flight work state**, not just wiring a connection factory and calling `PING`.

Principles to remember:

1. **Creating a bean does not mean Redis is ready.** Verify permissions, network, TLS, topology, and real operations where needed.
2. **Liveness is not readiness.** A Redis outage may stop an app from taking new traffic while the process remains capable of recovering.
3. **Readiness depends on Redis's role.** An optional cache differs from a mandatory session store or Redis stream.
4. **Graceful shutdown must include background workers.** Stop polling/subscribing, drain in-flight tasks, and ACK only after side effects succeed.
5. **Close connections by ownership and in order.** Let Spring manage `LettuceConnectionFactory`; never destroy a shared factory while handlers still run.
6. **Redis Streams require pending recovery and idempotency.** Driver reconnects or process restarts do not automatically ensure every event was processed.
7. **Pub/Sub has no durable replay.** Stopping listeners can miss messages; invalidation needs TTLs, versions, or reconciliation.
8. **Timeouts and cancellations can leave unknown outcomes.** Commands with side effects may have run even without a client response.
9. **Kubernetes probes, grace periods, and Spring lifecycle must align.** Never let pods get `SIGKILL`ed before committed drain windows finish.
10. **Test the lifecycle like a business flow.** Startup, dependency outages, readiness, rolling deploys, `SIGTERM`, pending recovery, and connection cleanup must all be observed.

**Core rule:** accept new work only when ready to serve; on shutdown, stop taking new work, finish what can be finished, preserve recovery paths for what cannot, and release Redis connections only after dependent components have stopped.
