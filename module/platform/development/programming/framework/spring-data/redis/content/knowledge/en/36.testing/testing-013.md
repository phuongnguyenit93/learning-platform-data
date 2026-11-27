# Testing Sentinel, Cluster, and Failure Recovery

## 1. Why Testing That Redis Runs Is Not Enough

Suppose a Spring Boot application uses Spring Data Redis to store caches, check login sessions, and record processing state. On a developer machine with a single Redis server, tests like these usually pass:

```java
redisTemplate.opsForValue().set("demo:status", "READY");
assertEquals("READY", redisTemplate.opsForValue().get("demo:status"));
```

Yet when deploying Redis with **Sentinel** or **Redis Cluster**, situations emerge that never occur in single-node tests:

- The primary suddenly stops responding.
- A replica is promoted to become the new primary.
- The Redis client still holds stale connections or the old node address.
- A write executed on the server, yet the application timed out before receiving the reply.
- Replicas have not replicated the most recent write yet.
- Redis Cluster moves a hash slot to another node and returns `MOVED` or `ASK`.
- Intermittent networking, DNS changes, or repeated client reconnects occur.
- Some cached keys survive failover while others disappear.
- Redis Streams workers must recover pending messages.
- A wave of concurrent retries overloads the newly recovered Redis.

A dependable test does not merely ask **“do GET and SET work?”** It asks:

> When topology changes or failures strike mid-operation, does the application recover service, does data uphold its guarantees, and do side effects avoid unwanted duplication?

This lesson belongs to the **Testing** chapter of **Spring Data Redis**, focusing on integration tests, failure tests, and recovery tests in **Sentinel**, **Redis Cluster**, and client layers such as **Lettuce**.

## 2. Distinguish Three Redis Deployment Modes Before Testing

### 2.1. Standalone Redis

```text
Spring Boot
     |
     v
Redis server
```

One server handles reads and writes. Standalone testing verifies serializers, `RedisTemplate`, commands, and basic business logic. However, it **does not verify Sentinel failover or hash-slot routing in Cluster**.

### 2.2. Redis Replication + Sentinel

```text
                    Spring Boot / Lettuce
                             |
                   Query Sentinel topology
                             |
          +------------------+------------------+
          |                  |                  |
       Sentinel 1         Sentinel 2         Sentinel 3
          |                  |                  |
          +------------------+------------------+
                             |
                      Redis primary P
                      /             \
                     v               v
                Replica R1      Replica R2
```

Sentinel monitors Redis primary health, coordinates failover decisions, and publishes the current primary to clients.

In this mode:

- **Sentinel is not a proxy** handling every `GET`/`SET`.
- Applications normally connect directly to Redis data nodes discovered via Sentinel/the driver.
- Replicas can experience **replication lag** since Redis replication is asynchronous by default.
- When the primary fails, Sentinel needs time to detect, elect, and promote.
- Clients must refresh topology and reconnect to the new primary.

### 2.3. Redis Cluster

```text
                 Spring Boot / cluster-aware client
                               |
        +----------------------+----------------------+
        |                      |                      |
        v                      v                      v
    Primary A              Primary B              Primary C
    slots ...              slots ...              slots ...
        |                      |                      |
        v                      v                      v
    Replica A1             Replica B1             Replica C1
```

Redis Cluster partitions **16,384 hash slots** across primaries. Clients route commands according to each key's slot.

In this mode:

- There are **multiple primaries**, each owning a slice of the keyspace.
- Keys can migrate to new owners during resharding.
- Redis can respond with `MOVED` or `ASK` redirections.
- Clients must refresh cluster topology when slots move.
- Failover affects the primary/replica of a specific shard.
- Never treat a Redis Cluster as “one big standalone Redis” when reasoning about multi-key commands.

**Sentinel and Cluster are two distinct architectures.** Never test one topology and claim the other is protected.

## 3. Recovery Testing Must Define Contracts First

Before writing tests, specify **what is permitted to happen during a failure**.

Example of a system holding different kinds of data:

| Data Category | Acceptable Recovery Requirement |
|---|---|
| Cache backed by PostgreSQL | Partial cache loss acceptable; subsequent reads reload |
| Session with TTL | Must honor login/expiration policy; never auto-extend privileges |
| Displayed product catalog | Bounded staleness acceptable |
| Redis-only counters | Must explicitly state whether post-failover write loss is acceptable |
| Redis Stream holding jobs | Needs pending/retry handling and idempotency |
| Distributed locks | Must prevent stale owners from overwriting resources after lease loss |
| Idempotency keys | Must prevent unintended duplicate business side effects |
| Payment workflows | Must rely on an authoritative source with proper transactions/idempotency |

Commonly measured guarantees:

- **Availability:** how long can timeouts or interruptions last?
- **Recovery Time Objective (RTO):** time to restore service within acceptable thresholds.
- **Recovery Point Objective (RPO):** maximum acceptable data or update loss during an incident.
- **Consistency:** how long stale reads remain tolerable?
- **Idempotency:** can retries produce duplicate side effects?
- **Degradation:** when Redis is unavailable, does the API return errors, fall back, or degrade gracefully?

No default RTO/RPO fits every application. Numbers in this lesson are **illustrative test targets** to tailor to your real requirements.

## 4. Keep Test Tiers Clearly Separated

| Tier | Purpose | Environment |
|---|---|---|
| Unit test | Verify error classification, retries, fallbacks, idempotency in code | Controlled mocks/fakes |
| Standalone integration test | Verify serializers, templates, Redis commands, TTL | Real single-node Redis |
| Sentinel integration test | Verify Sentinel discovery, primary switchover, reconnect | Multiple Redis nodes + multiple Sentinels |
| Cluster integration test | Verify slot routing, `MOVED`, `ASK`, per-shard failover | Multiple primaries + replicas |
| Fault-injection test | Verify mid-flight errors, timeouts, partitions, process crashes | Isolated controllable topology |
| Soak/load test | Verify recovery under traffic without resource leaks | Near-production environment |
| Disaster recovery drill | Verify backup/restore, wide failovers, runbooks | Dedicated operational environment |

### 4.1. Unit Tests Do Not Replace Real Topologies

You can mock a `RedisConnectionFailureException` to verify a service returns 503 or falls back. Yet mocks cannot confirm:

- Which node Sentinel promoted.
- How fast Lettuce detects the new topology.
- Whether Cluster clients follow `MOVED`/`ASK` properly.
- Which commands were lost during failover.
- Whether reconnection stalls command queues excessively.

Therefore, at least one integration test group needs **real Redis running the exact topology in use**.

### 4.2. A Single Testcontainers Redis Is Only a Smoke Test

Baseline example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import org.springframework.data.redis.core.StringRedisTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Testcontainers
@SpringBootTest
class RedisStandaloneSmokeIT {

    @Container
    static final GenericContainer<?> redis =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine")
            ).withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", redis::getHost);
        registry.add(
                "spring.data.redis.port",
                () -> redis.getMappedPort(6379)
        );
    }

    @Autowired
    StringRedisTemplate template;

    @Test
    void canWriteAndRead() {
        String key = "it:standalone:probe";
        try {
            template.opsForValue().set(key, "alive");
            assertEquals(
                    "alive",
                    template.opsForValue().get(key)
            );
        } finally {
            template.delete(key);
        }
    }
}
```

This test confirms standalone Redis connectivity, dependencies, and serializers. It **does not test Sentinel or Cluster** because a single container lacks Sentinel quorum, replicas, and hash-slot routing.

When implementing real tests, match Spring Boot/Testcontainers versions and isolate test profiles so you never write to other environments' Redis.

## 5. Building Sentinel Infrastructure for Testing

A meaningful Sentinel topology typically includes:

```text
Redis P1       Redis R1        Redis R2
  primary       replica         replica
     \             |               /
      +------------+--------------+
                   |
       +-----------+-----------+
       |           |           |
    Sentinel 1  Sentinel 2  Sentinel 3
                   |
                   v
             Spring Boot test
```

### 5.1. Why Run Three Sentinels?

Redis Sentinel detects primary outages and decides failovers cooperatively. Understand how quorum works:

- **Quorum** is the count of Sentinels needed to agree a primary is unreachable.
- Performing a failover also requires **authorization via Sentinel majority/election** per Sentinel rules.

Running only one Sentinel in a test can exercise basic discovery, yet misses the quorum and network-partition dynamics of real Sentinel deployments.

### 5.2. Sample Redis Data Node Configurations

The primary can listen on port 6379 inside an isolated test network.

Replica R1:

```conf
port 6379
replicaof redis-primary 6379
appendonly yes
```

Replica R2:

```conf
port 6379
replicaof redis-primary 6379
appendonly yes
```

These are minimal illustrative excerpts; full configurations also set bind/protected-mode, ACLs, persistence, paths, and networking to match infrastructure.

### 5.3. Sample Sentinel Configuration

Each Sentinel's `sentinel.conf` might include:

```conf
port 26379
sentinel monitor mymaster redis-primary 6379 2
sentinel down-after-milliseconds mymaster 5000
sentinel failover-timeout mymaster 30000
sentinel parallel-syncs mymaster 1
```

Meaning:

- `mymaster`: primary group name.
- `redis-primary`: initial primary address in the test network.
- `2`: Sentinel quorum needed to flag the primary down.
- `down-after-milliseconds`: observation window before marking subjectively down.
- `failover-timeout`: coordination parameter for failover stages, not an app-level recovery SLA.
- `parallel-syncs`: limits how many replicas resync simultaneously during failover.

**Important:** Sentinel requires write permission to persist topology updates into its config file. Mounting `sentinel.conf` read-only can break topology updates across failovers. Give test environments writable config storage.

In Docker topologies, container names/hostnames advertised by Sentinel must be **reachable by the test application and driver**.

### 5.4. Keep the Test Environment Isolated

Use Docker Compose or Testcontainers on a dedicated Docker network with stable container aliases. Never share a Redis instance used for active team development.

**Do not confuse Docker port mapping with addresses advertised by Sentinel.** Sentinel can reply with:

```text
redis-replica-1:6379
```

If Java tests run outside Docker and cannot resolve `redis-replica-1`, data connections fail even though connecting to the host-mapped Sentinel port worked.

Two ways to handle this:

1. Run both the test application and Redis/Sentinel inside the **same container network**, so advertised hostnames/ports resolve directly.
2. Intentionally configure announce/NAT/DNS mappings so addresses returned by Sentinel are reachable from the test JVM.

Exposing Sentinel port 26379 alone is never enough; ensure primaries and replicas are reachable too.

## 6. Configuring Spring Boot for Sentinel in Tests

For Spring Boot 3.x, example config:

```yaml
spring:
  data:
    redis:
      sentinel:
        master: mymaster
        nodes:
          - sentinel-1:26379
          - sentinel-2:26379
          - sentinel-3:26379
      connect-timeout: 2s
      timeout: 2s
```

This assumes the hostnames above are reachable from the test JVM.

Notes:

- `master` is the **Sentinel-monitored primary group name**, not a fixed primary IP.
- `nodes` lists **Sentinel** addresses, not Redis replica addresses.
- Spring Data Redis routes data traffic to the Redis nodes discovered from Sentinel.
- Older Spring Boot versions use `spring.redis` instead of `spring.data.redis`.
- If the app constructs a custom `RedisConnectionFactory`, verify that bean respects the configuration rather than editing YAML alone.

In many projects, Lettuce is the default driver. It supports topology discovery and exposes version-specific timeout/reconnect options.

### 6.1. Checking the Current Primary via Sentinel

Against one Sentinel:

```bash
redis-cli -h sentinel-1 -p 26379 \
  SENTINEL get-master-addr-by-name mymaster
```

Inspect replicas:

```bash
redis-cli -h sentinel-1 -p 26379 \
  SENTINEL replicas mymaster
```

Inspect a data node's role:

```bash
redis-cli -h redis-primary -p 6379 ROLE
```

These commands verify topology before injecting faults. Never treat a successful cache read alone as proof failover happened.

## 7. Testing Sentinel: Controlled Failover Procedure

### 7.1. Core Test Case

**Assumptions:** 3 Sentinels, 1 primary, 2 replicas; test app uses a Sentinel-aware connection factory.

**Step 1 — Verify initial state**

- All Sentinels recognize `mymaster`.
- One primary exists; replicas are connected and replicating.
- Spring Boot executes a baseline write successfully.

Example:

```redis
SET it:sentinel:status before-failover EX 120
GET it:sentinel:status
```

**Step 2 — Trigger primary switchover**

You can ask a Sentinel to initiate a failover for testing:

```bash
redis-cli -h sentinel-1 -p 26379 SENTINEL FAILOVER mymaster
```

`OK` from this command **does not mean failover is complete or the app has reconnected**. Poll topology until a new primary is elected and the client connects.

Another scenario stops the primary process/container in an isolated lab to test **real failure detection**, rather than relying solely on manual failover commands.

**Step 3 — Observe interruption window**

During switchover, record:

- Fault injection timestamp.
- Timestamp of first failed request.
- Count of timeouts or connection errors.
- Timestamp when Sentinel confirms the new primary.
- Timestamp when the app writes successfully again.
- Time until API metrics return within SLO.

**Step 4 — Verify fresh writes on the new primary**

Once topology stabilizes:

```redis
SET it:sentinel:status after-failover EX 120
GET it:sentinel:status
```

Use **the exact Spring Redis client under test** for reads and writes, not only `redis-cli`. If CLI succeeds while Spring Boot stays stuck on the old node, the test fails.

**Step 5 — Check pre-incident data**

Inspect which pre-failover keys survived or vanished, evaluating against your RPO contract:

- Rebuildable cache: losing some keys may be acceptable.
- Zero-loss data: requires proper durability or an authoritative source.
- Writes right before failover may not have reached the promoted replica due to asynchronous replication.

Never blame the driver simply because a write acknowledged `OK` by the old primary vanished after failover. Separate replication limits from business requirements.

### 7.2. What Failure Signals to Verify?

| Event | Expected Signal |
|---|---|
| Primary stops responding | Errors/timeouts classified cleanly |
| Sentinel detects primary down | Sentinel group state transitions |
| Replica promoted | `ROLE` or `INFO replication` confirms new primary |
| Lettuce reconnects | Application operations succeed again |
| Writes during switchover | May fail; never report false success |
| Writes after recovery | Succeed against new primary |
| Timed-out writes | Non-idempotent operations not blindly retried |
| Lagging replica | Replica read path may observe stale values |
| Old connections | Replaced/closed cleanly without unbounded leaks |

## 8. Never Test Failover Using Fixed `Thread.sleep`

Anti-pattern:

```java
triggerFailover();
Thread.sleep(10000);
assertEquals("OK", redis.opsForValue().get(key));
```

Three problems:

1. Failover may finish in 2 seconds, wasting test time.
2. Failover may take over 10 seconds, making the test flaky.
3. Waking up after a sleep does not prove topology converged or the client reconnected.

Prefer **polling conditions with an explicit deadline**.

Example with Awaitility:

```java
import java.time.Duration;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertEquals;

await()
        .atMost(Duration.ofSeconds(60))
        .pollInterval(Duration.ofMillis(250))
        .ignoreExceptions()
        .untilAsserted(() -> {
            String key = "it:recovery:probe";
            redis.opsForValue().set(key, "after-recovery");
            assertEquals(
                    "after-recovery",
                    redis.opsForValue().get(key)
            );
        });
```

Using `ignoreExceptions()` in bounded polling **does not mean production code should swallow errors**. Inside recovery tests, it lets the probe retry while Redis switches over. Record error counts and types separately so slow recovery is never hidden.

Never treat the first successful `GET` as proof **every** feature recovered. Write paths, replica reads, Stream consumers, and multi-key commands may require separate checks.

## 9. Java Integration Test with Spring Data Redis

A test class using a `sentinel-it` profile provisioned by test infrastructure:

```java
package com.example.redis.integration;

import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.data.redis.core.StringRedisTemplate;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@ActiveProfiles("sentinel-it")
@Tag("sentinel-it")
class SentinelRecoveryIT {

    @Autowired
    StringRedisTemplate redis;

    @Test
    void redisWorksAgainstCurrentPrimary() {
        String key = "it:sentinel:" + UUID.randomUUID();

        try {
            redis.opsForValue().set(
                    key,
                    "ready",
                    Duration.ofMinutes(2)
            );

            assertEquals(
                    "ready",
                    redis.opsForValue().get(key)
            );
        } finally {
            redis.delete(key);
        }
    }

    @Test
    void eventuallyAcceptsWritesAfterExternalFailover() {
        String key = "it:sentinel:recovery:" + UUID.randomUUID();

        // Test infrastructure drives fault injection and coordinates
        // test start timing. This is a recovery probe;
        // this method itself DOES NOT trigger failover.
        try {
            await()
                    .atMost(Duration.ofSeconds(60))
                    .pollInterval(Duration.ofMillis(250))
                    .ignoreExceptions()
                    .untilAsserted(() -> {
                        redis.opsForValue().set(
                                key,
                                "healthy",
                                Duration.ofSeconds(90)
                        );

                        assertEquals(
                                "healthy",
                                redis.opsForValue().get(key)
                        );
                    });
        } finally {
            try {
                redis.delete(key);
            } catch (RuntimeException ignored) {
                // Cleanup of demo key; isolated test environment
                // is torn down if Redis remains unavailable.
            }
        }
    }
}
```

Key notes:

- The first test verifies `RedisTemplate` against the active Sentinel topology.
- The second test is only a **recovery probe**; without a real orchestrator triggering failover at the right moment, this method alone **does not prove** failover.
- For an automated end-to-end failover test, orchestration records the *initial primary*, injects the fault, verifies the *new primary*, and then runs the probe until the app recovers.
- Keys carry unique namespaces and UUIDs to avoid parallel collisions.
- Tests never call `FLUSHALL` on shared Redis.
- Cleanup failures when infrastructure is down must not mask the primary failure measurements; design environment teardown separately.

### 9.1. Separate Fault Control from Application Logic

Define an independent test harness component:

```java
public interface SentinelFaultController {
    String currentPrimaryAddress();
    void requestFailover();
    boolean isDifferentPrimary(String previousAddress);
}
```

A test orchestrator calls:

```text
oldPrimary = currentPrimaryAddress()
verify app writes/reads
requestFailover()
await until currentPrimaryAddress() != oldPrimary
await until app writes/reads successfully
record duration and failure count
```

This interface **only describes the contract**; implement it against Docker/your test environment with explicit synchronization. Never pretend failover is tested just by defining the interface.

## 10. Testing Replica Reads and Stale Data

When configuring Lettuce with:

```java
ReadFrom.REPLICA_PREFERRED
```

a `SET` on the primary followed immediately by a `GET` can return stale data from a replica.

```text
t0: SET profile:42 = v2 on primary
t1: Primary returns OK
t2: GET from replica -> may still see v1
t3: Replica receives v2
```

A sound integration test:

- Uses an `UPSTREAM` template to verify authoritative writes.
- Uses a `REPLICA_PREFERRED` template for stale-tolerant read paths.
- Writes incrementing versions.
- Records when replicas observe new versions.
- Measures replication lag distribution under test load.
- Verifies business paths requiring *read-your-writes* **never rely on potentially stale replicas**.

### 10.1. Do Not Force Tests to Observe Stale Reads

In lightly loaded local labs, replication can be nearly instantaneous. A test writing:

```java
assertNotEquals("v2", replicaTemplate.opsForValue().get(key));
```

will fail sporadically whenever the replica syncs immediately.

Instead of demanding the replica **must be stale**, verify:

- The system tolerates eventual consistency on allowed read paths.
- Primary read paths reflect writes as expected.
- If simulating lag, use controlled fault injection to introduce delay.
- Critical business decisions never rely on potentially stale replica reads.

### 10.2. Fallback Does Not Check Data Freshness

`REPLICA_PREFERRED` falls back to the primary when no eligible replica is available, **not** when an online replica simply lags behind recent writes. Tests must separate node loss from replication lag.

## 11. Building a Test Redis Cluster with Proper Networking

A Redis Cluster test typically uses several primaries and replicas so failover is observable.

Example:

```text
redis-7000   redis-7001   redis-7002   (primaries)
    |            |            |
redis-7003   redis-7004   redis-7005   (replicas)
```

Command creating the Cluster once nodes are running in cluster mode:

```bash
redis-cli --cluster create \
  redis-7000:7000 redis-7001:7001 redis-7002:7002 \
  redis-7003:7003 redis-7004:7004 redis-7005:7005 \
  --cluster-replicas 1 --cluster-yes
```

**Note:** nodes must already be booted with `cluster-enabled yes`, valid node IDs, config files, cluster bus ports, and networking. This shows topology initialization, not a full container setup guide.

### 11.1. Cluster Announced Addresses Are a Classic Test Failure

A Redis Cluster node might advertise:

```text
172.19.0.4:7000
```

A test JVM outside Docker often cannot route to that IP. When `GET` targets a key on another slot, the driver gets `MOVED` pointing to that unreachable address and fails to connect.

Symptoms:

- Tests on one random key succeed.
- Tests on another key fail with connection errors.
- Redis nodes still report `cluster_state:ok`.
- Testcontainers/Docker port mappings appear valid.
- Client fails to follow redirects because announced node addresses are unreachable from the JVM.

Solutions:

1. Run the test app inside the same Docker network as the Cluster, or
2. Configure `cluster-announce-ip`, `cluster-announce-port`, and bus addresses reachable from the client network, or
3. Use a verified NAT/endpoint-translation mechanism in your driver/test infrastructure.

**Exposing seed node ports alone is insufficient.** The client must reach the cluster-announced endpoints of every node participating in routing.

### 11.2. Inspecting Topology

Use Redis CLI:

```bash
redis-cli -h redis-7000 -p 7000 CLUSTER INFO
redis-cli -h redis-7000 -p 7000 CLUSTER NODES
redis-cli -h redis-7000 -p 7000 CLUSTER SHARDS
```

Check a key's slot:

```bash
redis-cli -h redis-7000 -p 7000 \
  CLUSTER KEYSLOT it:cluster:alpha
```

`CLUSTER INFO` must confirm topology is healthy before testing, while `CLUSTER SHARDS` or `CLUSTER NODES` shows primary/replica roles and slot ownership.

## 12. Configuring Spring Data Redis for Cluster

For Spring Boot 3.x:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-7000:7000
          - redis-7001:7001
          - redis-7002:7002
      connect-timeout: 2s
      timeout: 2s
```

`nodes` lists **seed addresses**. A cluster-aware driver discovers the remaining nodes through topology queries.

You do not need every node in the seed list, yet seeds must be reachable and discovery must resolve to JVM-reachable addresses.

### 12.1. Lettuce Topology Refresh

When slot ownership changes, clients must refresh topology. Lettuce provides periodic refresh and adaptive refresh options.

Example configuration with Lettuce APIs:

```java
package com.example.redis.cluster;

import java.time.Duration;

import io.lettuce.core.cluster.ClusterClientOptions;
import io.lettuce.core.cluster.ClusterTopologyRefreshOptions;

import org.springframework.boot.autoconfigure.data.redis
        .LettuceClientConfigurationBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class LettuceClusterRefreshConfig {

    @Bean
    public LettuceClientConfigurationBuilderCustomizer
    clusterTopologyCustomizer() {

        return builder -> {
            ClusterTopologyRefreshOptions refresh =
                    ClusterTopologyRefreshOptions.builder()
                            .enableAllAdaptiveRefreshTriggers()
                            .enablePeriodicRefresh(
                                    Duration.ofSeconds(30)
                            )
                            .build();

            ClusterClientOptions clientOptions =
                    ClusterClientOptions.builder()
                            .topologyRefreshOptions(refresh)
                            .build();

            builder.clientOptions(clientOptions);
        };
    }
}
```

In a real Java file, write the full import on one line:

```java
import org.springframework.boot.autoconfigure.data.redis.LettuceClientConfigurationBuilderCustomizer;
```

Never insert a line break inside a package or class name in an `import` statement.

Exact APIs and defaults vary across Lettuce/Spring Boot versions. The snippet illustrates topology refresh setup; 30 seconds is not a universal production default.

**Do not refresh overly aggressively** on large Clusters, because topology discovery carries its own overhead.

## 13. Testing Slot Routing and Multi-Key Commands

### 13.1. Reading/Writing Across Multiple Hash Slots

Cluster tests should not use just one fixed key. Pick keys spanning multiple slots:

```redis
CLUSTER KEYSLOT it:cluster:A
CLUSTER KEYSLOT it:cluster:B
CLUSTER KEYSLOT it:cluster:C
```

Then read and write them through the **cluster-aware Spring Data Redis client**:

```java
String keyA = "it:cluster:A";
String keyB = "it:cluster:B";

redis.opsForValue().set(keyA, "A");
redis.opsForValue().set(keyB, "B");

assertEquals("A", redis.opsForValue().get(keyA));
assertEquals("B", redis.opsForValue().get(keyB));
```

Check real slot numbers to ensure keys did not accidentally land on the same slot. To test every primary, craft keys per slot and record each key's owner.

### 13.2. Multi-Key Commands Must Account for Same-Slot Rules

Redis Cluster requires multi-key atomic commands to map to the same hash slot.

Example:

```text
order:{42}:header
order:{42}:items
```

Both keys use hash tag `{42}`, guaranteeing the same slot.

Verify:

```redis
CLUSTER KEYSLOT order:{42}:header
CLUSTER KEYSLOT order:{42}:items
```

For `MULTI/EXEC`, Lua scripts, or multi-key commands, tests must verify:

- Co-located keys share a slot where required.
- The driver routes to the right owning node.
- No unexpected `CROSSSLOT` occurs.
- Key namespace changes preserve same-slot grouping.
- Resharding works without hardcoding static slot owners.

**Never share one global hash tag across all keys**, as doing so funnels all traffic onto a single slot.

### 13.3. Never Treat `CROSSSLOT` as a Transient Error Worth Retrying

If a script receives two keys in different slots, `CROSSSLOT` is a **key-design bug**, not a transient network glitch.

Retrying 10 times will not fix it. Tests should catch it early and ensure code reports a clear failure.

## 14. Testing `MOVED` and `ASK` During Resharding

Redis Cluster uses two redirection responses:

- **`MOVED`**: the node reports the slot permanently moved elsewhere; the client must update its routing table.
- **`ASK`**: temporary redirection mid-migration; the client must send `ASKING` followed by the command to the target node.

A cluster-aware client like Lettuce handles these internally when properly configured. Application code should not parse raw `MOVED` error strings manually.

### 14.1. Resharding Test Case

1. Identify a test key in slot S on Primary A.
2. Read and write the key through the Spring client.
3. Begin migrating slot S to Primary B in an isolated topology.
4. Keep issuing controlled reads and writes while migration runs.
5. Track error counts, timeouts, and latency.
6. Once migration finishes, verify slot S belongs to the new owner.
7. Verify the Spring client reads/writes on the new owner cleanly.

```text
Before reshard:
  key K -> slot S -> Primary A

During reshard:
  Client may encounter MOVED / ASK
  Topology cache may briefly lag

After reshard:
  key K -> slot S -> Primary B
  Client must reach B cleanly
```

### 14.2. Do Not Test Only After Everything Settles

Running `GET` only after resharding finishes tests final routing while missing requests sent **while the slot is actively migrating**.

A thorough fault-injection test collects metrics throughout migration:

```text
requests sent
requests succeeded
requests timed out
redirect-related failures
max/p95/p99 latency
time to stable recovery
```

Do not assume zero failures during resharding. Pass criteria depend on your system's stated timeout, retry, and availability budgets.

### 14.3. Never Reshard Production Slots to Run Integration Tests

Resharding and `CLUSTER SETSLOT` are admin mutations affecting live data. Run them only inside isolated controllable test Clusters or approved operational procedures.

## 15. Testing Single-Shard Failover in Redis Cluster

### 15.1. Procedure

Suppose Primary A has replica A1.

**Setup:**

- Cluster reports `cluster_state:ok`.
- Primary A holds test keys in its assigned slots.
- Replica A1 is replicating A.
- App reads and writes keys owned by A.

**Triggering controlled failover in tests:**

One option instructs the replica to take over:

```bash
redis-cli -h redis-replica-a1 -p 7003 \
  CLUSTER FAILOVER
```

This only works on a healthy Cluster replica eligible for failover. Options like `FORCE`/`TAKEOVER` carry different semantics and risks; **never use them casually** just to speed up tests.

Alternatively, stop Primary A's process/container to verify automatic failover, provided the Cluster retains quorum and healthy replicas.

**Observe:**

```redis
CLUSTER INFO
CLUSTER NODES
CLUSTER SHARDS
```

Verify afterward:

- The replica promoted to primary for those slots.
- The app's Cluster client picked up the new topology.
- Keys in the affected shard recovered per contract.
- Unrelated shards continued serving normally.
- Retries and pending commands stayed bounded.

### 15.2. Test Unaffected Shards as Well

A bug in client topology refresh or retry logic can take down **the entire application** even when only one shard fails over.

Use two sets of keys:

```text
affectedKeys   -> slots on Primary A
unaffectedKeys -> slots on Primary B/C
```

During A's failover:

- Verify requests to `unaffectedKeys` keep succeeding.
- Verify errors on `affectedKeys` remain bounded and recover.
- Verify no retry storm floods every shard.

This is a major advantage of Cluster testing over basic “is Redis up?” checks.

## 16. Network Partitions, Process Pauses, and Asymmetric Faults

Not every outage is a clean process crash.

| Fault | Behavior to Observe |
|---|---|
| Kill Redis primary | Client sees disconnect; triggers failover/reconnect |
| Pause Redis process | Sockets stay open while commands time out |
| Block app → Redis traffic | Client cannot send/receive commands |
| Block Sentinel ↔ primary traffic | Sentinel may mark primary down depending on quorum |
| Block primary → replica replication | Replica lag grows |
| Broken DNS resolution | Client cannot resolve advertised endpoints |
| Packet loss / high latency | Tail latency, timeouts, and retries surge |
| Broken Cluster bus connectivity | Nodes fail to exchange topology state |
| Application restart | Connections, subscriptions, and pending state must recover |

Simulate these with fault-injection tools, network rules, or container orchestration inside an isolated environment.

### 16.1. Why Is a Pause Different from a Crash?

Crashes close sockets or fail rapidly. Process pauses keep sockets open while dropping responses. Meanwhile:

```text
Application sends INCR
        |
        v
Command may reach Redis
        |
        v
No reply before timeout
        |
        v
App cannot tell if command ran
```

Tests must distinguish **timeouts with uncertain outcomes** from **commands guaranteed never to have executed**. That matters more than measuring raw reconnect seconds.

### 16.2. Network Faults Do Not Always Trigger Sentinel Failover

If only the application loses connectivity to Redis while Sentinels still reach the primary cleanly, Sentinel will not trigger a failover. That behaves completely differently from a dead primary.

Tests must specify:

```text
Which path did the fault break?
App -> Redis?
Sentinel -> primary?
Replica -> primary?
Node -> Cluster bus?
```

Never label every network glitch a “failover,” because mechanics and expected behavior differ.

## 17. Testing Write Ambiguity: Writes Can Run While Replies Drop

A fundamental distributed systems rule: **client timeouts never prove Redis did not execute the command**.

Example:

```text
Client                        Redis
   |                            |
   | INCR metrics:counter -----> |
   |                            | Counter increments
   |        [reply lost]        |
   |                            |
   | timeout                    |
```

If the application retries:

```redis
INCR metrics:counter
```

the counter increments **twice** for one business event.

### 17.1. Operations Needing Dedicated Testing

| Operation | Risk When Retrying After Timeout |
|---|---|
| `GET` | Usually no side effect; adds load |
| `SET` same value | Value-idempotent, yet check TTL/timing |
| `INCR` | Can double-increment |
| `LPUSH` | Can push duplicate items |
| `XADD` | Can append duplicate entries |
| `ZINCRBY` | Can add score twice |
| Write Lua script | Depends on whether the script itself is idempotent |
| `XACK` | Redis may already have ACKed; retries must expect `0` |
| Payment workflow | Never retry side effects without idempotency |

### 17.2. Idempotency via Operation IDs

Business commands can carry a dedicated `operationId`:

```json
{
  "operationId": "payment-42-confirm",
  "orderId": 42,
  "action": "CONFIRM"
}
```

The receiver or authoritative store uses `operationId` to prevent double execution even when:

- Requests are retried.
- Redis fails over mid-flow.
- HTTP responses drop.
- Consumers reprocess pending entries.

**Never assume Redis locks or Lettuce retries grant exactly-once guarantees.** Tests must verify idempotency at the exact boundary where side effects persist.

### 17.3. Write Ambiguity Test Criteria

A fault-injection test can:

1. Submit a command with an operation ID through the service.
2. Drop the reply after the server may have processed it.
3. Let the client retry per policy.
4. Read business state from the authoritative store.
5. Verify side effects did not duplicate beyond contract.
6. Log requests that hit uncertain outcomes.

Checking only “the final retry returned 200” proves nothing about correctness.

## 18. Redis Persistence, Replication, and Zero-Loss Limits

A common myth is “having Sentinel or Cluster replicas means zero write loss.”

Redis replication is **asynchronous** by default:

```text
Primary P             Replica R
    |                      |
SET K=V2
    |
Returns OK to client
    |
[Primary dies before R gets V2]
                           |
                           v
                       R promoted
                           |
                      K may still be V1
```

Integration tests must specify:

- Which data is rebuildable cache.
- Which data cannot tolerate loss.
- How RDB/AOF persistence is configured.
- Under what conditions replicas sync and fail over.
- How ambiguous commands right around a crash are handled.

Mechanisms like `WAIT` or Redis durability options reduce risk in certain scenarios, yet never turn Redis into a consensus database guaranteeing zero lost writes.

### 18.1. Do Not Write Tests Asserting Impossible Guarantees

An assertion like:

```java
assertEquals(
    "latest",
    redis.opsForValue().get("it:critical:before-failover")
);
```

immediately after killing the primary right when it returned `OK` may demand **stronger guarantees** than async replication provides.

When zero loss is mandatory, change the architecture/authoritative store instead of raising test timeouts.

### 18.2. Measuring RPO with Sequenced Writes

A writer test sends monotonically increasing `sequenceNumber` records while recording every acknowledged write in an external test coordinator log.

After failover:

1. Read surviving sequences.
2. Reconcile against writes acknowledged to the application.
3. Identify missing sequences.
4. Measure the time gap between the last preserved write and the fault.
5. Evaluate against your published RPO.

Do not compare only total key counts; distinct keys can be overwritten or expire via TTL.

## 19. Testing Redis Streams After Failover

Applications using Redis Streams normally rely on consumer groups and the Pending Entries List (PEL).

Example:

```redis
XGROUP CREATE it:orders billing 0 MKSTREAM
XADD it:orders * type paid orderId O-42
XREADGROUP GROUP billing consumer-a COUNT 1 STREAMS it:orders >
```

When `consumer-a` reads without calling `XACK`, the entry sits in the group's PEL.

### 19.1. Essential Test Cases

1. Create an isolated test Stream and group.
2. Append an event with a unique `eventId`.
3. Have a consumer read it without ACKing.
4. Stop the consumer or trigger a controlled Redis fault.
5. Allow recovery.
6. Inspect actual pending state.
7. Have another consumer reclaim/re-read using an appropriate mechanism like `XAUTOCLAIM`.
8. Execute idempotent business logic.
9. Call `XACK` only after business completion.
10. Verify zero duplicate side effects.

### 19.2. Why Not Just Poll `XREADGROUP` with `>`?

```redis
XREADGROUP GROUP billing consumer-b STREAMS it:orders >
```

`>` delivers **new undelivered entries**. It does not pull pending entries already handed to a dead consumer.

Recovery requires `XPENDING`, pending history reads, or claiming commands such as:

```redis
XAUTOCLAIM it:orders billing consumer-b 60000 0-0 COUNT 10
```

A 60-second idle threshold is illustrative only. Too low steals in-flight work; too high slows recovery.

### 19.3. Retention and the PEL Can Also Be Affected

If the Stream trims or deletes entries while pending, the PEL may reference IDs whose payloads are gone depending on Redis version and deletion method.

Recovery tests must distinguish:

- Pending because unACKed.
- Original payload still intact vs. trimmed.
- Consumer group metadata preserved vs. lost after restore/config reset.
- Retries completable vs. needing dead-letter/reconciliation handling.

Restarting Redis does not automatically resolve delivery and business processing consistency.

## 20. Pub/Sub and Keyspace Notifications Across Outages

Standard Redis Pub/Sub retains no queue for offline subscribers.

Example:

```text
Subscriber connected
      |
      | Disconnects for 5 seconds
      |
Publisher emits event X during those 5 seconds
      |
Subscriber reconnects
      |
      v
Does not automatically receive event X
```

The exact same limit applies to **keyspace/keyevent notifications**, such as:

```text
__keyevent@0__:expired
```

### 20.1. Pub/Sub Test Cases

- While online, relevant events arrive.
- While disconnected, events emitted offline are lost.
- After reconnecting, the subscriber receives **new events**.
- Never assume old events replay.

If business logic cannot lose events, never mark tests passing simply because “the listener reconnected.” Use Redis Streams/durable queues or authoritative reconciliation.

### 20.2. Keyevents in Redis Cluster

Keyspace notifications fire on the **node executing the mutation**. Subscribing to one node does not automatically capture events from other primaries.

Test by:

1. Determining slot owners for test keys.
2. Enabling notifications on every relevant node.
3. Subscribing listeners across watched nodes.
4. Creating short-TTL keys across multiple slots.
5. Observing which node emits each event.
6. Performing failover or resharding.
7. Verifying subscriptions update.
8. Recording the gap window where events can drop.

Never use keyevents as precise timers: `expired` fires when Redis actually deletes the expired key, not at the exact millisecond TTL reaches zero.

## 21. Testing Caches and TTL During Redis Recovery

### 21.1. Post-Failover Cache Misses

When a cache loses partial state:

```text
Redis failover
      |
      v
Some cache entries disappear
      |
      v
API cache misses
      |
      v
Database receives surge of read traffic
```

Recovery tests should verify:

- Cache misses stay distinct from Redis connection errors.
- Database fallbacks bound concurrency.
- No thundering herd overwhelms the database.
- Once Redis recovers, the cache warms back up within budget.
- Errors or overly stale data never get cached.

### 21.2. Do Not Accidentally Extend TTL

Suppose a session starts with a 30-second TTL. A fallback or retry calling `SET EX 30` again **unintentionally extends the session lifetime**.

Tests must clarify whether TTL is sliding or fixed at an absolute deadline:

```text
createdAt + lifetime = expiresAt
```

Do not assume seeing a non-null `GET` proves session expiry remained intact.

### 21.3. Testing Serialization After Restarts

An app might restart with new code/serializers while Redis still holds older data.

Verify:

- Key serializers match.
- Value serializers decode existing entries.
- No `WRONGTYPE` from String/Hash changes.
- Deserialization errors are surfaced clearly rather than swallowed as cache misses.
- Legacy keys follow a migration path if needed.

A Redis node coming back online does not mean **every application version can read its stored entries**.

## 22. Testing Distributed Locks and Stale Owners

A Redis lock with TTL cannot prevent an expired worker from still writing to a database.

Test scenario:

```text
Worker A acquires lease, TTL=5s
Worker A stalls for 8s
Redis grants new lease to Worker B
Worker B updates resource
Worker A wakes up and sends stale update
```

If the system uses `SET NX PX` without target-side protection, A overwrites B.

Meaningful tests verify:

- Worker A cannot delete B's lock on release (compare-and-delete).
- With fencing tokens, the receiver rejects stale tokens **once a newer epoch/token is active per protocol**.
- Ordered updates/operation IDs within a lease are validated properly.
- Durable writes at the receiver cannot be corrupted by stale workers.
- Redis failover can regress asynchronous `INCR` sequences; never blindly assume `INCR` provides absolute durable fencing.

For critical resources, test **the final write target**, not just the Redis lock key.

## 23. Redis Failover and Preserving Root Causes in Error Handling

During Redis timeouts or primary switches, Spring Data Redis/Lettuce emits various exception categories:

```text
Connection failure
Command timeout
Topology/redirect failure
Serialization failure
Redis command error
```

Well-behaved services never swallow all errors into `null`:

```java
try {
    return redis.opsForValue().get(key);
} catch (Exception ignored) {
    return null;
}
```

That disguises Redis outages as cache misses, triggering heavy DB reads while erasing diagnostic clues.

Instead:

- Separate connection/timeout errors from genuine cache misses.
- Preserve the original cause when wrapping exceptions.
- Retry sparingly according to command semantics.
- Never log Redis keys carrying tokens, raw values, URIs with passwords, or full command arguments.
- Track failure categories and root-cause types safely.

Example:

```java
catch (DataAccessException ex) {
    throw new CacheAccessException(
            "product_cache_read",
            RedisFailureCategory.CONNECTION,
            ex
    );
}
```

`CacheAccessException` and `RedisFailureCategory` here are **application-defined types**. The point is preserving the root cause—not treating every `DataAccessException` as a connection fault; real code should classify specific subtypes accurately.

## 24. Retries After Failover: Avoiding Retry Storms

Common incident pattern:

```text
Primary dies
   |
   v
Many requests time out
   |
   v
All retry immediately
   |
   v
Newly promoted primary gets slammed with traffic
   |
   v
Timeouts continue
```

This is a **retry storm**. Recovery tests must verify retry policies do not prolong outages.

Typical safeguards:

- Retry only eligible transient errors.
- Cap maximum retry attempts.
- Use exponential backoff with jitter.
- Enforce total per-request timeouts.
- Apply rate limits/bulkheads around Redis.
- Fail fast once error budgets exhaust.
- Enforce idempotency on side-effecting writes.
- Use circuit breakers with sensible open intervals and half-open probes.

### 24.1. Never Sleep Indefinitely Inside Request Handlers

Bug:

```java
while (true) {
    try {
        return redisRead();
    } catch (RuntimeException ex) {
        Thread.sleep(1000);
    }
}
```

This pins resources with no deadline. In WebFlux, `Thread.sleep` on the event loop stalls unrelated requests too.

If an API must respond under 2 seconds, requests cannot wait 30 seconds for Sentinel failover inline. Return an appropriate error/fallback and let subsequent requests or background workers resume once Redis recovers.

### 24.2. Evaluate Recovery Under Real Traffic

Sending one `GET` per second may make failover look effortless, whereas 500 req/s resuming at once can spike latency and pending queues dramatically.

Test by:

1. Applying steady baseline load before the fault.
2. Injecting the fault.
3. Observing error counts and queue buildup.
4. Allowing failover to finish.
5. Sustaining target load.
6. Confirming throughput/p99 return within bounds.
7. Confirming no multi-minute retry tail persists.

## 25. Scenario Testing Matrix

| Code | Topology | Fault | What to Prove |
|---|---|---|---|
| S1 | Sentinel | Normal reads/writes | Client hits current primary |
| S2 | Sentinel | `SENTINEL FAILOVER` | Client updates to new primary |
| S3 | Sentinel | Kill primary | Outage detected and recovered within deadline |
| S4 | Sentinel | Lose one Sentinel | System obeys quorum/majority rules |
| S5 | Sentinel | Replica lag | Read path tolerates staleness without bad decisions |
| S6 | Sentinel | Pause primary | Timeouts and write ambiguity handled safely |
| S7 | Sentinel | App restart | Connections and subscriptions re-establish |
| C1 | Cluster | Multi-slot read/write | Client routes by hash slot |
| C2 | Cluster | Cross-slot multi-key command | `CROSSSLOT` recognized cleanly |
| C3 | Cluster | Reshard slot | `MOVED`/`ASK` and topology refresh work |
| C4 | Cluster | Single-shard failover | Affected shard recovers; other shards stay up |
| C5 | Cluster | Node IP/hostname change | Announced endpoints remain reachable |
| C6 | Cluster | Lose replica | Read-from/fallback policy behaves properly |
| C7 | Cluster | Pause node | Timeouts and bounded pending commands |
| R1 | Sentinel/Cluster | Timeout after write | No duplicate side effects beyond contract |
| R2 | Sentinel/Cluster | Stream pending | Reclaim/idempotency/ACK work cleanly |
| R3 | Sentinel/Cluster | Subscriber disconnect | No false expectation of Pub/Sub replay |
| R4 | Sentinel/Cluster | Cache outage | Fallback avoids overloading database |
| R5 | Sentinel/Cluster | Failover under heavy load | RTO, p99, and retry counts stay within SLA |
| R6 | Sentinel/Cluster | Backup restore | Schema, TTL, and business state remain valid |

This matrix is a starting point. For each case, document exact **setup, fault, wait condition, assertions, metrics, and cleanup**.

## 26. Measuring RTO, RPO, and Recovery Quality

### 26.1. RTO Is More Than Time to Elect a New Primary

Timeline:

```text
T0: Primary fails
T1: Sentinel/Cluster elects new primary
T2: Redis data node accepts commands
T3: Spring client reconnects/routes properly
T4: API p95/p99 returns within SLO
```

Measuring only `T1 - T0` measures **Redis-layer** failover, not **application RTO**.

For user experience, `T4 - T0` is what truly counts.

### 26.2. RPO Must Be Measured Against Meaningful Data

RPO cannot be measured by “Redis answered `PING`.” Use timestamped/sequenced datasets and verify which writes previously acknowledged to the application survive recovery.

Separate:

- Writes never sent.
- Writes sent that timed out (ambiguous).
- Writes confirmed by old primary.
- Writes present on new primary.
- Writes backed by business/authoritative stores.

Checking only a single aggregate counter can hide missing or overwritten records.

### 26.3. Sample Test Report Format

```text
Scenario: Sentinel primary crash under read/write load
Topology: 1 primary, 2 replicas, 3 Sentinels
Fault at: T0
New primary elected: T1
Client first successful write: T2
API p99 back within target: T3

Observed:
  recovery duration = T3 - T0
  timeout count
  retry count
  successful writes
  ambiguous writes
  data revisions missing after failover
  number of duplicated business effects
```

All milestones and numbers must be **actually measured**, never filled in optimistically to declare success.

## 27. Designing Isolated, Repeatable Tests

### 27.1. Never Run Destructive Fault Injection on Production Redis

Commands like:

```redis
SHUTDOWN
SENTINEL FAILOVER
CLUSTER FAILOVER
CLUSTER SETSLOT
FLUSHALL
```

severely impact live environments serving real data.

Run them only when test infrastructure is isolated and dedicated. Never trust an environment label “test” if the actual Redis endpoint still points to production.

### 27.2. Do Not Abuse `FLUSHALL` for Cleanup

Instead of wiping all of Redis:

```redis
FLUSHALL
```

use unique key prefixes:

```text
it:<runId>:sentinel:...
it:<runId>:cluster:...
```

paired with sensible TTLs. Delete only created keys or tear down the run's dedicated containers/volumes afterward.

For Redis Streams/consumer groups, cleanup may delete the test namespace's Stream key once consumers stop.

### 27.3. Parallel Tests Need Independent Namespaces

If two tests share:

```text
it:order:42
```

they overwrite each other, flaking or distorting failover results.

Use:

```text
it:<testRunId>:order:42
```

Additionally, failover/resharding tests require **exclusive topology ownership**, since two tests altering roles/slots simultaneously collide even when keys are prefixed.

### 27.4. Poll Observable Conditions Instead of Long Sleeps

Conditions can include:

- New node reports `ROLE` = primary.
- `CLUSTER INFO` reports healthy topology.
- Slot ownership updated.
- Spring Redis client successfully writes a key with TTL.
- API maintains target success rate over an observation window.

Every poll must enforce a maximum timeout. On timeout, fail with safe diagnostics: roles, node IDs, timestamps, and error categories.

### 27.5. Cleanup After Failover

In an isolated test setup, tearing down and recreating the entire topology guarantees every run starts from a known baseline.

If reusing containers:

- Sentinel may have rewritten its master config.
- Redis replicas may have switched roles.
- Cluster slot ownership may have shifted.
- App connection pools may retain old endpoints.
- Subscriptions may still be alive.

Merely restarting one container does not automatically restore original topology. **Full resets or verified baseline checks** are vital for repeatable tests.

## 28. Avoiding CI Environment Flakiness

Some integration failures stem from infrastructure rather than business code:

| Cause | Symptom |
|---|---|
| Throttled CI CPU | Sentinel failover runs abnormally slowly |
| Unstable Docker DNS | Client cannot resolve advertised nodes |
| Wrong port mappings | Seeds connect, redirects fail |
| Containers not yet ready | Tests write before Cluster covers all slots |
| Read-only Sentinel config | Topology updates fail unpredictably across failovers |
| Incompatible Redis version | Commands/flags behave unexpectedly |
| Overly tight timeouts | False failures under CI load |
| Parallel tests sharing one topology | Competing primary/slot changes produce chaos |
| Reused Redis volumes | Leftover data/config from prior runs |
| Replicas not synced before fault | Higher data loss than expected |
| Clock skew across hosts | Wall-clock duration measurements turn inaccurate |

### 28.1. Wait for Meaningful Readiness

“Container port is open” does not mean a Redis Cluster is ready.

Readiness criteria should check:

- All required Redis nodes accept connections.
- Sentinels discovered the master group.
- Replicas are in the replication state required by the test.
- Cluster assigned all 16,384 hash slots and reports healthy state.
- Test JVM can reach **every advertised Redis endpoint**.
- Spring Data Redis initialized its connection factory and runs commands cleanly.

### 28.2. Use a Monotonic Clock for Elapsed Time

Measure recovery duration with a monotonic timer such as `System.nanoTime()` in the JVM:

```java
long started = System.nanoTime();

triggerFault();

awaitRecovery();

long elapsedMillis =
        java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - started
        );
```

Wall clocks like `System.currentTimeMillis()` remain useful for log timestamps, yet can jump during clock syncs; never rely solely on wall clocks for precise durations.

## 29. Common Mistakes When Testing

### Mistake 1: Calling a Single Redis Container a Sentinel Test

Without Sentinel quorum and replicas, Sentinel failover is untested. Use standalone containers only for baseline tests.

### Mistake 2: Checking Only `PING` After Failover

A passing `PING` does not prove read/write routing works, data survived, or APIs recovered.

### Mistake 3: Sleeping 10 Seconds and Assuming Failover Finished

Duration varies with load, network, and Sentinel/Cluster settings. Poll conditions with a deadline.

### Mistake 4: Sentinel Advertises an Unreachable Hostname

The JVM reaches Sentinel yet fails connecting to the returned data nodes. Verify the full network path.

### Mistake 5: Cluster Seed Connects, `MOVED` Fails

The driver cannot reach node addresses returned in redirects. Test with keys across multiple slots.

### Mistake 6: All Test Keys Land in One Slot

Misses cross-shard routing bugs. Pick and verify keys across multiple slots/primaries.

### Mistake 7: Testing Only After Resharding Completes

Misses `ASK` redirects during migration and timeouts on in-flight requests.

### Mistake 8: Treating Every `GET` Error as a Cache Miss

Hides connection outages and database overloads. Separate misses from Redis errors.

### Mistake 9: Retrying `INCR` or `XADD` Unconditionally

Can duplicate side effects if the first reply dropped. Test idempotency via operation IDs.

### Mistake 10: Expecting Async Redis Replication to Never Lose Writes

Demands stronger guarantees than the architecture offers and creates broken tests. Define RPO and authoritative sources explicitly.

### Mistake 11: Requiring Replica Reads to Always Return Stale Data in Tests

Fast replication often syncs replicas right away. Test consistency policies rather than demanding flaky races.

### Mistake 12: Forgetting Redis Streams Pending Entries

Restarting consumers reading only `>` strand pending work. Test reclaiming and idempotency.

### Mistake 13: Assuming Pub/Sub Replays After Reconnect

Pub/Sub stores no history. Recovery tests must account for dropped offline events.

### Mistake 14: Measuring Only Redis Server Failover Time

The app can still hit routing errors or stalled command queues after Redis picks a new primary. Measure end-to-end recovery.

### Mistake 15: Ignoring Unaffected Shards

One failing shard can stall the whole app if client bounds/bulkheads are missing. Test both affected and unaffected keys.

### Mistake 16: Running Failover Tests in Parallel on One Topology

Two tests mutating primaries/slots simultaneously make outcomes uninterpretable. Isolate environments or run sequentially.

### Mistake 17: Running `FLUSHALL` on Shared Test Redis

Wipes data belonging to other tests or real apps. Namespace keys and scope cleanup.

### Mistake 18: Not Verifying Redis and Driver Versions

Commands and options vary across Redis/Lettuce/Spring Data Redis versions. Record exact dependencies and modes in test reports.

### Mistake 19: Measuring Only p50

During incidents, p99, timeout counts, and error rates matter far more than median latency.

### Mistake 20: Assuming Timeouts Mean Writes Never Executed

Outcomes may be ambiguous; retries require idempotency and business-state checks.

## 30. End-to-End Testing Plan

### Phase A — Verify Basic Functionality

- Run standalone integration tests with real Redis.
- Verify key/value/hash serializers.
- Verify TTL and cache hit/miss behavior.
- Verify commands and error classification.
- Record Redis and driver versions.

### Phase B — Verify Sentinel

- Provision 1 primary, 2 replicas, 3 Sentinels.
- Verify discovery and primary routing.
- Verify replica reads per application policy.
- Trigger failover in the test environment.
- Wait for primary change, client reconnect, and resumed writes.
- Reconcile pre/post-failover data against RPO.

### Phase C — Verify Cluster

- Provision multi-primary/replica Cluster.
- Verify all 16,384 slots are assigned.
- Test routing across multiple slots.
- Test multi-part keys sharing hash tags.
- Run resharding and observe `MOVED`/`ASK`.
- Fail over one shard and verify unaffected shards.

### Phase D — Verify Application Error Handling

- Separate cache misses from Redis errors.
- Verify fallbacks trigger only on approved error categories.
- Test write ambiguity, idempotency, and retries.
- Test Streams pending/reclaim flows.
- Test Pub/Sub event loss during subscriber disconnects.
- Test lock/fencing protections at target stores where required.

### Phase E — Measure Recovery and Load

- Generate representative baseline traffic.
- Inject timestamped faults.
- Collect latency, error rates, and retry/pending counts.
- Measure API-level RTO and data-level RPO.
- Verify the system self-recovers to steady state.
- Archive reports alongside topology, versions, and test settings.

## 31. Self-Check Questions

**1. Can a test with one Redis container verify Sentinel failover?**  
No. It only tests standalone Redis; Sentinel failover requires Sentinels, a primary, and replicas.

**2. Does Sentinel act as a proxy forwarding every command from Spring Boot?**  
No. Sentinel handles discovery and failover; clients typically connect directly to Redis data nodes.

**3. Why can a newly promoted Redis primary lack a write acknowledged `OK` by the old primary?**  
Because replication is asynchronous by default; the promoted replica may not have received that write before the old primary died.

**4. Does waiting for `CLUSTER INFO` to report OK prove the application recovered?**  
Not yet. The application must still reach advertised nodes, route commands properly, and meet SLOs.

**5. Do `MOVED` and `ASK` mean the same thing?**  
No. `MOVED` points to the current permanent slot owner; `ASK` handles temporary redirections mid-migration.

**6. Why can Cluster tests fail even when Docker mapped ports look right?**  
Because node addresses advertised in redirects/topology may be unreachable from the JVM.

**7. Should you use `Thread.sleep(10000)` to assume failover finished?**  
No. Poll conditions with a bounded deadline to avoid flakiness and get real topology/app recovery proof.

**8. Why shouldn't a test require replicas to always return stale data right after a write?**  
Because fast replication can sync immediately; the race is not guaranteed on every run.

**9. Does a timeout after `INCR` allow safe automatic retries?**  
Not necessarily. Redis may have incremented the counter while the reply dropped; retrying can double-increment.

**10. If a Redis Streams consumer dies with pending messages, does a new worker reading `>` recover them?**  
No. You need pending reads or claiming such as `XAUTOCLAIM`, paired with idempotency and ACK on completion.

**11. Does a reconnecting Pub/Sub subscriber receive events emitted while offline?**  
No. Standard Redis Pub/Sub provides no replay or ACK for missed messages.

**12. How does application RTO differ from Sentinel's primary election time?**  
The application must also reconnect, route accurately, drain backlogs, and recover SLOs. Measure until service truly stabilizes.

**13. Which keys should a single-shard Cluster failover test monitor?**  
Both keys in the affected shard and keys in unaffected shards, checking fault isolation alongside recovery.

**14. Why must `FLUSHALL` be avoided on shared test Redis?**  
Because it erases data outside the test's scope, breaking sibling tests or real data.

**15. If Redis stops erroring yet the database overloads from mass cache misses, is recovery considered successful?**  
Not fully. Recovery must be evaluated end-to-end across error rates, latency, downstream load, and application SLOs.

## 32. Key Takeaways

- **Sentinel and Redis Cluster are distinct topologies:** Sentinel monitors/promotes primaries; Cluster routes by hash slot and reassigns slot ownership.
- **Standalone Redis tests are not failover tests.** Proving recovery requires real Redis, matching topology, and controlled fault injection.
- **Poll real conditions instead of fixed sleeps:** verify primary/slot owner updates, client reconnection, and working application reads/writes.
- **Redis replication is asynchronous by default;** never assume every write confirmed by an old primary survives on the new primary.
- **Redis Cluster tests must span multiple slots**, advertised endpoints, `MOVED`/`ASK`, resharding, and single-shard failovers.
- **Write timeouts are ambiguous:** never retry `INCR`, `XADD`, or side-effecting business operations without idempotency.
- **Test Streams pending/reclaim**, remember Pub/Sub has no replay, and bound cache fallbacks and warm-up surges.
- **Measure RTO/RPO at the business layer**, tracking error rates, p95/p99, retry storms, lost writes, and duplicate effects.
- **Inject faults only inside isolated test infrastructure**, using unique namespaces, TTLs, and repeatable cleanup.

### References

- [Spring Data Redis — Redis connection modes](https://docs.spring.io/spring-data/redis/reference/redis/connection-modes.html).
- [Spring Data Redis — Redis Configuration](https://docs.spring.io/spring-data/redis/reference/redis/redis-configuration.html).
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html).
- [Redis — Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/).
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/).
- [Redis — Cluster tutorial](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/).
- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/).
- [Redis — CLUSTER FAILOVER](https://redis.io/docs/latest/commands/cluster-failover/).
- [Redis — CLUSTER SHARDS](https://redis.io/docs/latest/commands/cluster-shards/).
- [Redis — XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/).
- [Lettuce — High Availability and Sharding](https://redis.github.io/lettuce/ha-sharding/).
- [Testcontainers Java — Documentation](https://java.testcontainers.org/).
- [Awaitility — Project site](https://github.com/awaitility/awaitility).
