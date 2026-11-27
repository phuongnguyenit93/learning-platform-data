# Testing Failover, Reconnect, and Recovery Time in Spring Data Redis

In systems using Redis for caching, session state, counters, or business data, a Redis **primary** (often called *master* in older documentation and configuration) can stop operating due to process crashes, host power loss, network partitions, or maintenance. **Replication** creates data copies on replicas; **Redis Sentinel** monitors the primary, runs elections, and executes failover when needed. Spring Data Redis uses a client—typically Lettuce—to connect to and work with that topology.

Successfully configuring Sentinel is not enough to declare high availability. You must **test failover**, observe the client **reconnect and discover the new primary**, and measure how long the application genuinely cannot serve Redis operations. Your tests must answer:

1. Under what conditions does Sentinel detect an unresponsive primary and promote a replica to be the new primary?
2. Does the Spring Data Redis client rediscover the new primary address after failover, or keep sending write commands to the old endpoint?
3. During the transition window, what errors does the API emit: timeouts, connection errors, `READONLY`, or inconsistent responses?
4. How soon after the outage can the application perform **verified writes and reads** on the new primary?
5. How many write commands reported to the application as successful **have disappeared** after the primary switch?
6. Once the old primary rejoins, do the topology and application remain stable?

This lesson builds a repeatable test procedure on a Redis Sentinel test cluster integrated with Spring Data Redis, measuring both **recovery time (observed RTO)** and **data-loss exposure (observed RPO)**.

> **Scope:** Redis Sentinel for a single-primary-with-replicas model. Redis Cluster uses different routing and failover mechanics; do not assume Cluster commands, events, or metrics behave like Sentinel. Never kill processes or change quorum in production without an approved operational plan.

## 1. Replication and Sentinel Architecture

A basic topology:

```text
                        Spring Boot application
                        StringRedisTemplate
                                |
                                | ask Sentinel: where is the primary for "mymaster"?
                                v
                   +------------+------------+
                   |            |            |
                Sentinel 1   Sentinel 2   Sentinel 3
                  :26379       :26380       :26381
                   |            |            |
                   +------------+------------+
                                |
                      Monitors and elects
                                |
                      Redis primary :6379
                         /          \
                        / replication \
                       v               v
                  Replica A        Replica B
                    :6380            :6381
```

Role of each component:

| Component | Responsibility |
|---|---|
| Redis primary | Accepts write commands; serves read commands per configuration |
| Redis replica | Replicates data from the primary; can be selected by Sentinel for promotion |
| Redis Sentinel | Monitors primary/replicas, detects failures, coordinates elections, announces address changes |
| `RedisConnectionFactory` | Provides Redis connections for Spring Data Redis |
| Lettuce/Jedis | Redis client handling connections, reconnects, and command execution |
| `RedisTemplate`/`StringRedisTemplate` | Synchronous application APIs |
| `ReactiveRedisTemplate` | Reactive API when the application uses Reactor/WebFlux |

### 1.1. Replication Is Not Transactional Synchronization

In common Redis replication setups, data is copied **asynchronously** from primary to replicas:

```text
Client             Primary              Replica
  | SET k v --------> |                     |
  | <----- OK --------|                     |
  |                   | ---- replication -->|
```

An `OK` reply from the primary **does not automatically prove** a replica has received and stored that command. If the primary dies right after returning `OK`, the promoted replica may lack some data the client was told succeeded.

Therefore, measure both **availability** and **data loss**. A working failover does not guarantee zero lost writes.

### 1.2. Sentinel Is a Monitoring and Coordination Mechanism, Not Application Data Storage

Sentinel does not store Redis values. It tracks topology and participates in electing a new primary. Applications still run `GET`, `SET`, and `INCR` against Redis data nodes.

Sentinel does not turn Redis into a distributed transactional database or consensus-based commit engine. Running three Sentinels strengthens failover decision-making, but **does not alter the asynchronous nature of replication**.

## 2. Failover Consists of Multiple Phases

When a primary becomes unreachable, the sequence of events typically includes these stages:

```text
t0     Primary becomes unavailable
        |
        v
t1     One Sentinel marks subjectively down (+sdown)
        |
        v
t2     Enough Sentinels confirm objectively down (+odown)
        |
        v
t3     Sentinel leader is elected; eligible replica is nominated
        |
        v
t4     Replica is promoted to new primary
        |
        v
t5     Remaining replicas are reconfigured to follow the new primary
        |
        v
t6     Client detects topology change and reconnects/reroutes
        |
        v
t7     Business write/read operations resume succeeding stably
```

These milestones are an **observational model**, not a promise that Redis always emits exactly seven events on a fixed timeline. Some steps may overlap or appear in a different order in logs depending on version, network state, and the order in which Sentinels observe the failure.

### 2.1. Subjectively Down and Objectively Down

- **SDOWN (*subjectively down*):** an individual Sentinel concludes an instance is unresponsive under its monitoring criteria.
- **ODOWN (*objectively down*):** enough Sentinels agree the primary is down per the configured quorum, allowing failover to proceed.
- **Leader election and failover authorization:** beyond failure-detection quorum, executing failover requires majority authorization among Sentinels to avoid competing decisions.

If only one Sentinel is alive or Sentinels are partitioned, **automatic failover may not occur** even if the Redis primary truly died. Thus, testing must verify live Sentinel counts and inter-Sentinel connectivity, not merely surviving Redis replicas.

### 2.2. Failover Can Fail

Common causes:

- No eligible replica remains for promotion.
- Replicas are too far out of sync or configured with priority disabling promotion.
- Sentinels fail to reach quorum/majority due to network disconnection.
- Promotion encounters errors or cascading disconnections.
- Asymmetric bidirectional networking among data nodes, Sentinels, and clients.
- Overloaded host resources causing monitoring timeouts.
- Security/TLS/authentication misconfigurations blocking role-change commands.

Treat failover as **a process to verify empirically**, not a feature enabled by a single config line and forgotten.

## 3. Two Core Metrics: RTO and RPO

### 3.1. RTO – How Long the Application Cannot Serve Expected Operations

**Recovery Time Objective (RTO)** is the target recovery time defined for a system. During testing, we measure an **observed recovery duration** according to an explicit definition of operational success.

Example:

```text
t0: inject fault by stopping the Redis primary
t1: first SET call fails
t2: Sentinel announces the new primary
t3: Spring Data Redis SET + GET probe succeeds stably
```

You can compute:

```text
Observed recovery duration = t3 - t0
Observed user-visible unavailability = t3 - t1
```

These two values differ:

- `t3 - t0` measures from **fault injection** to recovery.
- `t3 - t1` measures the window from when **the application first observes an error** until operations succeed again.

State the exact definition in reports, because if the first command occurs long after `t0`, a `t1`-based metric hides the full outage window.

A successful `PING` does not prove write traffic has recovered: it could hit a replica, or connections may not point to the new primary yet. **Probes should include a write and a verification read**, executed through the exact connection factory/template used by the real application.

### 3.2. RPO – How Much Acknowledged Data Was Lost

**Recovery Point Objective (RPO)** describes the acceptable data-loss bound. In tests, rather than counting time alone, record every write confirmed as successful to the application, then reconcile against the primary after failover.

Example:

```text
Before outage:
    SET ha:test:run-1:seq:100 ... -> OK
    SET ha:test:run-1:seq:101 ... -> OK
    SET ha:test:run-1:seq:102 ... -> OK

After failover:
    key seq:100 still present
    key seq:101 still present
    key seq:102 missing

Observed acknowledged-write loss = 1
```

In this test, do not set TTLs and do not manually delete these keys. With TTLs or eviction active, missing keys cannot immediately be attributed to replication loss.

**RTO and RPO are distinct:** a system may resume writes very quickly yet lose the final writes, or lose zero writes while waiting a long time for failover.

### 3.3. Recording a Baseline

Before injecting faults, measure:

- p50/p95/p99 latency of GET/SET.
- Steady-state read/write throughput.
- Count of healthy Redis nodes and Sentinels.
- Replication offsets/lag and link status.
- Application timeout frequency.
- Redis client connection/reconnect metrics.

Without a baseline, it is hard to tell whether high post-failover latency stems from failover itself or from pre-existing saturation.

## 4. What Does a Test Environment Require?

A sensible practice environment:

- **1 Redis primary**.
- **2 Redis replicas**, on separate nodes or containers.
- **3 Sentinels**, each running as an independent process.
- **1 Spring Boot application** connecting through Sentinel.
- **1 load/probe generator** issuing identifiable reads and writes.
- **1 result recorder external to the Redis cluster under test**, such as a local log file or telemetry store, so test logs aren't lost alongside Redis.
- Reasonably synchronized clocks across hosts when correlating multi-source logs.

A minimal demo can run on a laptop. However, running all processes on one machine **cannot simulate physical host loss, network partitions, or power outages**. It only tests part of the failover flow when a Redis process stops.

### 4.1. Distinguishing Demos from Production Scenarios

| Environment | What Can Be Tested | What Cannot Be Inferred |
|---|---|---|
| All processes on localhost | Primary switching and basic client reconnects | Multi-host/AZ fault tolerance |
| Single-host Docker Compose | Controlled topology startup, stopping containers | Real physical infrastructure failures |
| Multi-VM/AZ testbed | Networking, quorum, leader election, realistic failovers | Production traffic characteristics |
| Production-like staging | Close to real app behavior, auth/TLS, monitoring | Does not replace controlled production testing over time |
| Managed Redis service | Failover testing via provider APIs | Direct Sentinel control or full internal logs |

**Never run `SHUTDOWN`, `DEBUG SEGFAULT`, `kill -9`, network partitions, or quorum changes in production just to "see what happens."** Proceed only after verifying test environment, ownership, and blast radius.

## 5. Building a Local Redis Sentinel Lab

This example provides **minimal configuration files** for a loopback-only lab using distinct ports:

```text
Primary Redis:    127.0.0.1:6379
Replica A:        127.0.0.1:6380
Replica B:        127.0.0.1:6381

Sentinel 1:       127.0.0.1:26379
Sentinel 2:       127.0.0.1:26380
Sentinel 3:       127.0.0.1:26381

Sentinel master name: mymaster
Quorum: 2
```

Processes will update their own runtime/configuration files. Each Sentinel needs write access to its config file; never share one Sentinel config file across three processes.

### 5.1. Primary Config

File `redis-primary.conf`:

```conf
bind 127.0.0.1
port 6379
protected-mode yes

# Lab: disable persistence for simplicity;
# DO NOT copy this setting to production.
save ""
appendonly no
```

**For lab use only.** Disabling persistence changes restart data behavior; when testing production RPO, configure persistence to match the real environment.

### 5.2. Replica A and B

`redis-replica-a.conf`:

```conf
bind 127.0.0.1
port 6380
protected-mode yes

replicaof 127.0.0.1 6379

save ""
appendonly no
```

`redis-replica-b.conf`:

```conf
bind 127.0.0.1
port 6381
protected-mode yes

replicaof 127.0.0.1 6379

save ""
appendonly no
```

Upon startup, replicas connect to the primary and begin synchronizing data. Before injecting faults, check `INFO replication` to confirm both links are healthy.

### 5.3. Sentinel Configs

`sentinel-26379.conf`:

```conf
port 26379
bind 127.0.0.1

sentinel monitor mymaster 127.0.0.1 6379 2
sentinel down-after-milliseconds mymaster 3000
sentinel failover-timeout mymaster 15000
sentinel parallel-syncs mymaster 1
```

`sentinel-26380.conf` is similar, changing only the port:

```conf
port 26380
bind 127.0.0.1

sentinel monitor mymaster 127.0.0.1 6379 2
sentinel down-after-milliseconds mymaster 3000
sentinel failover-timeout mymaster 15000
sentinel parallel-syncs mymaster 1
```

`sentinel-26381.conf`:

```conf
port 26381
bind 127.0.0.1

sentinel monitor mymaster 127.0.0.1 6379 2
sentinel down-after-milliseconds mymaster 3000
sentinel failover-timeout mymaster 15000
sentinel parallel-syncs mymaster 1
```

`down-after-milliseconds 3000` is an **experimental value**, not a production recommendation. Too low causes Sentinels to mistake brief network/CPU hiccups for primary failure; too high lengthens detection time.

### 5.4. Starting the Lab

On a host with Redis installed, open separate terminal sessions and run:

```bash
redis-server redis-primary.conf
redis-server redis-replica-a.conf
redis-server redis-replica-b.conf

redis-server sentinel-26379.conf --sentinel
redis-server sentinel-26380.conf --sentinel
redis-server sentinel-26381.conf --sentinel
```

You can launch these via a process manager script or Docker Compose instead of six terminals; what matters is keeping **processes and runtime directories/files separate**.

With Docker, you cannot simply change ports while keeping `127.0.0.1` in every config: each container has its own loopback. Configure hostnames/container networks and Sentinel announce addresses so the **Spring client can connect**. If Sentinel returns an internal container address unreachable from the JVM host, the app discovers the primary yet fails to reconnect.

Remember never to expose unauthenticated Redis/Sentinel ports to public networks. This setup is strictly for loopback/testing.

### 5.5. Verifying the Initial Topology

Redis CLI:

```bash
redis-cli -p 6379 INFO replication
redis-cli -p 6380 INFO replication
redis-cli -p 6381 INFO replication

redis-cli -p 26379 SENTINEL get-master-addr-by-name mymaster
redis-cli -p 26379 SENTINEL masters
redis-cli -p 26379 SENTINEL replicas mymaster
redis-cli -p 26379 SENTINEL sentinels mymaster
```

Expected state:

- Port 6379 has `role:master` (Redis still uses `master` in many APIs and INFO fields).
- Ports 6380 and 6381 have `role:slave`/replica in Redis output.
- Both replicas have active links to the primary.
- Sentinel returns `127.0.0.1` and port `6379` for `mymaster`.
- Sentinel sees its peer Sentinels and expected replicas.

**Do not begin measuring failover until initial replication is stable**, otherwise measurements do not reflect a healthy HA cluster.

## 6. Configuring Spring Boot to Use Sentinel

In Spring Boot, a sample Spring Data Redis configuration is:

```yaml
spring:
  data:
    redis:
      connect-timeout: 2s
      timeout: 3s
      sentinel:
        master: mymaster
        nodes:
          - 127.0.0.1:26379
          - 127.0.0.1:26380
          - 127.0.0.1:26381
```

If servers use authentication, configure credentials for Redis data nodes and Sentinels according to your Spring Boot version's capabilities. **Sentinel passwords and Redis data-node passwords are two separate authentication scopes**; do not assume one property covers every environment.

In Spring Boot 3.x, `spring.data.redis.*` is the standard prefix. Projects on older Boot versions may use a different prefix; verify against your exact dependencies/version.

### 6.1. Meaning of `mymaster`

Here:

```yaml
spring:
  data:
    redis:
      sentinel:
        master: mymaster
```

`mymaster` is the **master group name in Sentinel**, not a Redis server hostname. All Sentinels must monitor the matching name. If Spring config uses `mymaster` while Sentinel monitors `primary-1`, primary lookup will fail.

### 6.2. Why Multiple Sentinel Endpoints Are Needed

If the application only knows:

```yaml
nodes:
  - 127.0.0.1:26379
```

then Redis may fail over cleanly yet the client cannot query topology if **Sentinel on :26379 also dies**.

Listing multiple endpoints gives the client alternatives to discover the primary address, depending on Redis driver and retry mechanics. However, verify every endpoint is reachable from the app environment with valid authentication.

**Do not treat the number of YAML endpoints as proof the client will reconnect fast.** Test the scenario where the first configured Sentinel fails too.

### 6.3. Avoid Fixed Redis Endpoints Alongside Sentinel

A classic misconfiguration leaves the app pointing directly at:

```yaml
spring:
  data:
    redis:
      host: redis-primary-old
      port: 6379
```

while expecting Sentinel tracking. If the app actually creates a connection factory with a fixed host, it keeps sending commands to the old Redis after failover.

When using Sentinel, verify that the **`RedisConnectionFactory` actually used by your templates** is initialized from Sentinel topology, rather than overridden by another bean using standalone host/port.

## 7. Explicitly Configuring `LettuceConnectionFactory`

Spring Data Redis typically uses Lettuce for synchronous and reactive connections. When declaring a custom connection factory, use `RedisSentinelConfiguration`.

Example:

```java
package com.example.redis;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisSentinelConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration(proxyBeanMethods = false)
public class SentinelRedisConfiguration {

    @Bean
    public RedisConnectionFactory redisConnectionFactory() {
        RedisSentinelConfiguration sentinel =
                new RedisSentinelConfiguration()
                    .master("mymaster")
                    .sentinel("127.0.0.1", 26379)
                    .sentinel("127.0.0.1", 26380)
                    .sentinel("127.0.0.1", 26381);

        LettuceClientConfiguration client =
                LettuceClientConfiguration.builder()
                    .commandTimeout(Duration.ofSeconds(3))
                    .build();

        return new LettuceConnectionFactory(sentinel, client);
    }
}
```

This illustrates common Spring Data Redis APIs. When defining this bean manually, also configure authentication, TLS, pooling, client resources, or replica-read policies as required by your environment.

**Be careful with Spring Boot auto-configuration:** declaring a custom `RedisConnectionFactory` stops Boot properties from auto-applying as before. Never create a separate standalone connection bean while assuming all templates still route via Sentinel.

### 7.1. Lettuce Reconnect and Redis Sentinel Cooperate

- **Reconnect**: restores TCP/Redis connections after a connection drops.
- **Master discovery**: finds the current primary via Sentinel when node roles change.
- **Command retry**: app/client policy when a command fails or its execution is uncertain.
- **Application recovery**: when business operations actually resume succeeding.

These are related yet **not identical**. Reopening a TCP connection to an **old replica** is not enough for writes to succeed; Redis can return `READONLY`.

Conversely, Sentinel knowing the new primary does not guarantee stale client connections are replaced instantaneously. Measuring both Sentinel state and Spring template outcomes separately is essential.

### 7.2. Read-From-Replica Complicates Measurements

If the client configures replica reads for higher throughput, a successful `GET` after failover **neither proves** write recovery **nor proves** the latest data exists on every replica.

For write-RTO and RPO tests, ensure reads target the **new primary** or verify the serving node's role, rather than concluding "zero data loss" from a `GET` against a potentially stale replica.

## 8. Designing a Probe from the Spring Data Redis Application Itself

A good probe uses the **same connection factory, serializers, and call path** as real services. It writes a unique key and reads it back to verify both write and read paths.

Example using `StringRedisTemplate`:

```java
package com.example.redis;

import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class RedisFailoverProbe {

    private static final Logger log =
            LoggerFactory.getLogger(RedisFailoverProbe.class);

    private final StringRedisTemplate redis;
    private final String runId = UUID.randomUUID().toString();
    private final AtomicLong sequence = new AtomicLong();

    public RedisFailoverProbe(StringRedisTemplate redis) {
        this.redis = redis;
    }

    @Scheduled(fixedDelayString = "${ha.probe.delay-ms:250}")
    public void verifyWriteAndRead() {
        long seq = sequence.incrementAndGet();
        String key = "ha:probe:" + runId + ":" + seq;
        String expected = "probe-" + seq;

        long start = System.nanoTime();

        try {
            Boolean written = redis.opsForValue()
                    .setIfAbsent(key, expected);

            if (!Boolean.TRUE.equals(written)) {
                throw new IllegalStateException(
                    "Probe key unexpectedly exists: " + key
                );
            }

            String actual = redis.opsForValue().get(key);

            if (!expected.equals(actual)) {
                throw new IllegalStateException(
                    "Probe readback mismatch for " + key
                );
            }

            long elapsedMillis =
                    (System.nanoTime() - start) / 1_000_000;

            log.info(
                "REDIS_PROBE_OK run={} seq={} latency_ms={}",
                runId, seq, elapsedMillis
            );
        } catch (Exception ex) {
            long elapsedMillis =
                    (System.nanoTime() - start) / 1_000_000;

            log.warn(
                "REDIS_PROBE_FAIL run={} seq={} latency_ms={} type={}",
                runId,
                seq,
                elapsedMillis,
                ex.getClass().getSimpleName()
            );
        }
    }
}
```

Enable scheduling in a configuration class:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
public class ProbeSchedulingConfiguration {
}
```

### 8.1. Why Does the Probe Use a Unique Key?

Repeatedly writing the same `healthcheck` key risks a read returning stale data and falsely reporting success even when the latest write failed or was misrouted.

Keys incorporating `runId` and a sequence make each probe easy to trace in logs:

```text
ha:probe:<runId>:1
ha:probe:<runId>:2
ha:probe:<runId>:3
```

For RPO tests, retain keys until reconciliation finishes. That is why this snippet **sets no TTL**, should run only in labs, and requires cleanup afterward.

### 8.2. Why Use `setIfAbsent`?

The probe needs to confirm a fresh key was actually created. With a unique key, `setIfAbsent` returns `true` when the write succeeds. If it returns `false`, a duplicate key or unexpected condition occurred; never mark the probe healthy blindly.

However, `SET NX` does not guarantee replicas received the write, and `SET NX` → `GET` remains **two commands**, not an atomic transaction.

### 8.3. Limitations of the Illustrative Probe

- Run only in test environments under the `ha:probe:*` namespace.
- Creating keys without TTLs grows memory usage; bound run duration and clean up afterward.
- `@Scheduled` on a single thread skips scheduled ticks while a call is timing out. Log frequency therefore indicates **measurement resolution**, not fixed-interval traffic.
- When a command timeout occurs, the application cannot tell whether Redis executed the write. `REDIS_PROBE_FAIL` means end-to-end verification failed, not proof Redis didn't receive the command.
- `System.nanoTime()` is only valid for **intra-JVM durations**, not cross-host timestamps comparable to Sentinel logs on other machines. To correlate timelines, log `Instant.now()` with synchronized clocks.
- In production-like load tests, record histogram metrics rather than logging a line per call under high throughput.
- If multiple instances run probes, give each a unique `runId` and avoid using high-cardinality `runId` directly as a metric label.

## 9. Fault Injection: Stopping the Primary Abruptly

Once all nodes are confirmed healthy and the probe is running, inject a fault in the **test environment** by terminating the Redis primary process.

One approach in a process-managed Unix lab:

```bash
# Run in lab only; verify exact PID of Redis primary :6379.
# Never run on production hosts or guess PIDs.
kill -9 <LAB_PRIMARY_PID>
```

If running via Docker Compose or a container runtime, stop **the exact test primary container** via your container tool:

```bash
docker kill <LAB_PRIMARY_CONTAINER_NAME>
```

Never use vague container names or "kill all Redis." Before injecting a fault, verify the targeted container is currently the active primary, because after an earlier failover port 6379 **may no longer be the primary**.

### 9.1. What to Record in the Timeline

When triggering the fault, record `t0` outside Redis:

```text
2026-11-13T10:00:00.000Z  INJECTED_PRIMARY_FAILURE
2026-11-13T10:00:00.100Z  REDIS_PROBE_FAIL connection error
2026-11-13T10:00:03.500Z  SENTINEL +sdown
2026-11-13T10:00:03.700Z  SENTINEL +odown
2026-11-13T10:00:04.500Z  SENTINEL +switch-master
2026-11-13T10:00:05.200Z  REDIS_PROBE_OK
```

This is **illustrative data**, not real Redis benchmark output or a guarantee that events happen at these exact timings.

Also record:

- Old primary and new primary.
- IDs/connections of participating Sentinels.
- Full Java exceptions with timestamps.
- Counts of failed and successful requests.
- p95/p99 latency of Redis-backed endpoints.
- Replication health after replica promotion.
- Whether probe keys reported successful before the failure still exist.

### 9.2. When Failover Succeeds

Query Sentinel:

```bash
redis-cli -p 26379 SENTINEL get-master-addr-by-name mymaster
```

Suppose post-failover output returns:

```text
127.0.0.1
6380
```

Verify node roles:

```bash
redis-cli -p 6380 INFO replication
redis-cli -p 6381 INFO replication
```

Expect port 6380 to report `master`, with the remaining replica following the new primary. The exact node chosen depends on Sentinel's selection.

**Never hardcode "failover always picks replica A."** Sentinel selects based on replica status, replication lag, priority, and other criteria.

### 9.3. Verify the Application, Not Just Topology

After Sentinel reports the new primary, keep watching for `REDIS_PROBE_OK`.

Topology may finish switching while Spring Data Redis still fails for several seconds because:

- Clients are waiting out command timeouts.
- Stale connections have not been closed or rerouted yet.
- The address returned by Sentinel is unreachable from the application.
- The driver fails authentication against the new endpoint.
- Connection pools are exhausted waiting on resources.
- An old replica is mistakenly addressed as primary and returns `READONLY`.

The moment **the application probe recovers** reflects when users can genuinely operate again.

## 10. Controlled Fault Injection: Requesting Sentinel Failover

Besides killing the process, Redis Sentinel supports an administrative command to trigger failover:

```bash
redis-cli -p 26379 SENTINEL FAILOVER mymaster
```

This tests a different case from power loss or abrupt primary disappearance:

- Sentinel is explicitly asked to switch roles.
- The current primary may still be running.
- Duration and error types seen by the app may differ from killing the process.
- Never use manual failover results to claim full SDOWN/ODOWN detection has been tested.

Maintain **two separate reports**:

1. **Planned failover** (controlled primary switch).
2. **Unplanned failover** (abrupt primary loss).

Manual failover still runs only when Sentinel and replica preconditions allow; errors from the admin command must be recorded as part of the experiment.

## 11. Testing Sentinel Failure Scenarios

An HA system can also lose a **Sentinel** while Redis data nodes stay healthy. This is a distinct scenario to test.

Scenario:

1. Confirm all three Sentinels see one another.
2. Stop **one Sentinel** in the lab.
3. Keep the Redis primary operating normally.
4. Verify the application can still read and write.
5. Verify the remaining two Sentinels still return the primary address.
6. Restart the stopped Sentinel afterward.

Normally, **losing one Sentinel does not interrupt Redis data nodes**. However, if the client was configured with only that dead Sentinel for discovery, creating new connections will be impacted.

### 11.1. Quorum and Majority

With three Sentinels and quorum 2, losing one Sentinel leaves two active Sentinels able to coordinate. Losing two Sentinels prevents automatic failover from gaining authorization, even though the Redis primary continues serving until it fails.

Do not equate:

```text
Redis data nodes can read/write
```

with:

```text
Sentinel quorum is sufficient to execute a new failover
```

These two states are related yet distinct.

Testing network partitions between Sentinel and Redis is an advanced scenario: asymmetric network views can make one side declare the primary down while clients still reach it. Use controlled chaos/network tooling to avoid creating an unrecoverable test state.

## 12. Testing When the Old Primary Rejoins

After failover, a replica has become the new primary. When the old primary restarts, Sentinel can reconfigure it to become a **replica of the new primary** once topology is detected.

Expected flow:

```text
Before failure:
  :6379 primary
  :6380 replica
  :6381 replica

After failure and failover:
  :6379 down
  :6380 new primary
  :6381 replica of :6380

After :6379 returns:
  :6379 can become replica of :6380
  :6380 remains primary
  :6381 remains replica
```

Critically, **the old primary does not automatically reclaim the primary role simply by restarting**. Any subsequent role change is governed by Sentinel/operational policies.

Checks:

- Confirm only one valid primary exists in the managed topology.
- Inspect `INFO replication` on every node.
- Verify Sentinel updates its replica list.
- Re-run read/write probes via Spring Data Redis.
- Ensure the application is not holding the old endpoint as primary.
- Verify data on the old primary resynchronizes with the new primary.
- Do not compare data mid-sync and prematurely conclude it was permanently lost.

For critical data, remember that the old primary may have held writes that replicas missed before the outage; when it returns as a replica, isolated writes from the old primary cannot be treated as the new source of truth.

## 13. Common Client Errors During Reconnect

### 13.1. Connection Refused / Reset / Timeout

For several seconds after the primary dies, existing connections may reset or stop responding.

Common Java exception types:

```text
RedisConnectionFailureException
RedisCommandTimeoutException
RedisSystemException
```

Exact exception types and wrappers depend on Spring Data Redis/driver/version. Never write handlers matching a single message string while ignoring root causes.

### 13.2. `READONLY` When Sending Writes to a Replica

If the application or a stale connection keeps sending `SET` to a node demoted to replica, Redis may return:

```text
READONLY You can't write against a read only replica
```

That signals **routing does not match the current topology**, not proof that Redis lost all data. Inspect the Redis connection factory, Sentinel discovery, fixed-host overrides, and reconnect state.

Never "fix" this by making replicas writable; that breaks replication assumptions and creates conflicting data.

### 13.3. Sentinel Returns an Unreachable Address

Redis Sentinel may track the new primary at an internal IP:

```text
10.10.0.8:6379
```

While the application on another network only sees a NAT endpoint:

```text
redis.company.example:6379
```

If Lettuce receives an unreachable internal IP, `get-master-addr-by-name` succeeds yet connecting to the new primary fails.

This is common in Docker labs, NAT, overlay networks, or cross-network Sentinel/app setups. Configure valid announce/endpoint routing and network policies **for both Sentinel and Redis data nodes**.

### 13.4. Auth/TLS Differences Across Nodes

Failover might elect a replica lacking complete ACL/TLS or firewall parity with the old primary. The app loses connectivity even though topology switched.

A valid HA test must verify:

- Consistent credentials across all Redis data nodes.
- Sentinel authentication handled separately when required.
- TLS certificates/names matching announced endpoints.
- Firewalls/security groups permitting connections to any promotable replica.

## 14. Timeouts and Retries: Reconnecting Does Not Mean Writes Are Safe to Resend

Suppose Java calls:

```java
redis.opsForValue().increment("orders:created");
```

The Redis primary may have executed `INCR`, yet the client timed out **before receiving the reply**. Retrying the same `INCR` can increment the counter twice.

```text
Client                   Redis primary
  | -- INCR k ----------> |
  |                       | value increments
  | X connection drops    |
  |                       |
  | -- INCR k (retry) --->| value increments a 2nd time
```

Failover widens the unstable connection window, making **unknown outcome** risks on writes even more important to address.

### 14.1. Retry Classification

| Command/Pattern | Safe to Blindly Retry? | Why |
|---|---|---|
| `GET` cached data | Usually safe for transient errors, bounded | No write side effects |
| `SET key fixedValue` | Can fit if value is fixed for the request and won't clobber newer updates | Overwriting older/newer writes still risks races |
| `INCR` | **No** | Can increment a second time |
| `LPUSH` | **No** without deduplication | Can push duplicate items |
| `XADD *` | **No** without event ID/idempotency | Can append two stream entries with different IDs |
| `SET NX` | Depends on outcome/ownership token | Retry may return false even when first attempt succeeded |
| Cache invalidation (`DEL`) | Usually nearly idempotent | Must account for races with cache refills |
| DB write then Redis update | Not a joint transaction | Two resources can commit divergently |

A sound retry policy bounds retry counts, uses backoff, restricts retryable errors, and detects duplicates/unknown outcomes. Never turn on infinite retries and call RTO solved.

### 14.2. Command Timeout Is Not Failover Timeout

`spring.data.redis.timeout` or `LettuceClientConfiguration.commandTimeout(...)` limits wait time for **one command** per client implementation. It is not a parameter forcing Sentinel to finish failover within that duration.

If command timeout is 1 second while Sentinel needs several seconds to promote a replica, requests will throw transient exceptions before recovering. Measure at the application layer and implement proper fallbacks instead of assuming connections shield every request from errors.

## 15. RPO Scenario: Reconciling ACKed Writes

To test data-loss exposure, run a sequenced workload and **log ACKs outside Redis**.

Pseudo-flow:

```text
runId = test-20261113-01
seq = 1, 2, 3, ...

for each seq:
    SET ha:rpo:<runId>:<seq> = <seq>
    if client receives success:
        append seq to local durable ACK log
```

After injecting the fault and application recovery:

```text
for each seq in ACK log:
    GET key from current primary
    if key missing or value differs:
        mark acknowledged-write missing/mismatch
```

Short Java snippet for the write step:

```java
public boolean writeRpoSample(
        StringRedisTemplate redis,
        String runId,
        long seq
) {
    String key = "ha:rpo:" + runId + ":" + seq;
    String value = Long.toString(seq);

    Boolean success = redis.opsForValue()
            .setIfAbsent(key, value);

    return Boolean.TRUE.equals(success);
}
```

If it returns `true`, the test harness must **persist `seq` to a file or external log store** reliably. On exceptions or timeouts, record the outcome as **uncertain** rather than grouping it with "not executed."

### 15.1. Pitfalls When Measuring Data Loss

- Do not set short TTLs on RPO test keys.
- Do not allow memory eviction policies to delete keys and miscount that as replication loss.
- Do not read from an unsynchronized replica and assume keys are lost.
- Do not count a `SET` that threw an exception as a successful ACK.
- Do not use the Redis cluster under test as the sole store for the ACK log.
- Do not write so many keys that RAM exhausts and invalidates the experiment.
- Do not compare two runs reusing the same namespace/sequence.
- Do not treat `WAIT` or replica ACK settings as absolute guarantees of durable survival across every failover.

### 15.2. Can `WAIT` Reduce Write Loss?

Redis provides `WAIT` to make a client wait until a number of replicas confirm receiving prior replication data on that connection, within a timeout.

It can **lower the risk** of data loss in certain scenarios, but:

- Does not turn Redis replication into a consensus commit protocol.
- Does not guarantee a particular replica is always chosen by Sentinel.
- Does not guarantee durable fsync in all configurations.
- Requires checking both the returned replica count and timeout.
- Requires managing command sequencing/connection affinity in the framework.

`min-replicas-to-write` and `min-replicas-max-lag` can also stop the primary from accepting writes when too few replicas meet lag criteria, trading availability. Do not change those settings arbitrarily in a test just to force "RPO = 0."

## 16. Structured Failover Test Matrix

An HA test suite should go beyond a single "kill primary." Break it into targeted cases:

| ID | Scenario | Key Observations |
|---|---|---|
| FT-01 | Abrupt primary stop | Failure detection, replica promotion, app RTO |
| FT-02 | Sentinel manual failover | Planned role-switch behavior |
| FT-03 | One Sentinel dies | Client discovery and remaining quorum |
| FT-04 | Old primary restarts | Old node becomes replica, no split-brain in topology |
| FT-05 | Nearest replica lags | Which replica Sentinel picks, tail writes preserved or lost |
| FT-06 | In-flight write during failover | Unknown outcomes, duplicates if retried |
| FT-07 | Application restarts mid-failover | Startup ability and discovery of new primary |
| FT-08 | One configured Sentinel unreachable | Fallback to remaining Sentinels |
| FT-09 | Controlled slow network/packet loss | False failovers, timeouts, and reconnects |
| FT-10 | Network partition loses quorum | Availability, inability to promote |
| FT-11 | Replica reads under lag | Stale reads when splitting reads/writes |
| FT-12 | Sentinel announces unreachable network IP | Reconnect fails even after switch-master |
| FT-13 | High read/write load during failover | p99, errors, timeouts, queue backlogs |
| FT-14 | Uneven auth/TLS across Redis data nodes | Config failures exposed after promotion |
| FT-15 | RPO test with external ACK log | Count of ACKed writes missing on new primary |

For network partition scenarios, use isolated fault-injection tools in staging. Never assume a plain `docker stop` covers network failure modes.

## 17. Generating Load Without Distorting Measurements

With only one probe every 5 seconds, measured RTO has **very coarse resolution**. If probes fire too aggressively, the test itself can overload Redis.

A sensible lab plan:

```text
Warm-up:
    Run probe/read-write for 30–60 seconds.
    Confirm baseline latency and stable replication.

Steady-state:
    Run bounded read/write load.
    Record ACK sequences for RPO checks.

Fault injection:
    Record t0; stop the exact active primary.
    Keep load profile unchanged at injection time.

Recovery:
    Continue probing at the defined interval.
    Record first sustained success and error rate.

Stabilization:
    Observe longer to ensure no continuous flapping.
    Verify replicas synced and clients no longer misroute.

Reconciliation:
    Compare ACK log against the new primary.
    Compile RTO, RPO, p95/p99, errors, and timeline.
```

Here, "first sustained success" can be defined as **N consecutive successful write/read probes within a window**, such as 10. A single isolated success amid timeouts does not mean the system has stably recovered.

Report all of:

- Timestamp of **first success**.
- Timestamp of **stable recovery** per stated criteria.
- Error rate during the failover window.
- Latency of requests that still succeeded.
- Reconnect count.
- Retry and duplicate counts (if applicable).

Never adjust "recovery" criteria after inspecting results just to make RTO look better.

## 18. Measuring RTO with a Monotonic Clock and Correlating Timelines

### 18.1. Within a Single Process

If the fault injector and app probe run in the **same JVM/process**, `System.nanoTime()` measures durations cleanly. In real apps, production code shouldn't kill Redis; an external test harness plus app probe metrics is better.

```java
long started = System.nanoTime();

// An operation controlled by the test harness.

long elapsedNanos = System.nanoTime() - started;
double elapsedMillis = elapsedNanos / 1_000_000.0;
```

`System.nanoTime()` is for elapsed durations, not cross-host UTC timestamps.

### 18.2. Across Processes/Hosts

To align timelines:

```text
Sentinel log timestamp
Redis server log timestamp
Application log timestamp
Fault injection timestamp
```

use timestamps synchronized via NTP/chrony or a matching clock source. Also log the run ID and endpoint/node.

Example output record:

```json
{
  "runId": "ft-01-20261113",
  "scenario": "primary-process-kill",
  "faultAt": "2026-11-13T10:00:00Z",
  "sentinelSwitchAt": "2026-11-13T10:00:04.5Z",
  "firstWriteReadSuccessAt": "2026-11-13T10:00:05.2Z",
  "stableRecoveryAt": "2026-11-13T10:00:06.0Z",
  "observedRecoveryMillis": 6000,
  "acknowledgedWriteLoss": 1,
  "status": "EXAMPLE_ONLY"
}
```

This is an **illustrative format**, not real test results. In real reports, `observedRecoveryMillis` must be computed from verified measurement timestamps; never eyeball unsynchronized log lines.

## 19. Monitoring Sentinel and Replication During Tests

Useful Redis CLI commands:

```bash
# Primary currently known to Sentinel:
redis-cli -p 26379 SENTINEL get-master-addr-by-name mymaster

# Master group state:
redis-cli -p 26379 SENTINEL master mymaster

# Replica state:
redis-cli -p 26379 SENTINEL replicas mymaster

# Other Sentinels:
redis-cli -p 26379 SENTINEL sentinels mymaster

# Roles and replication offsets on data nodes:
redis-cli -p 6379 INFO replication
redis-cli -p 6380 INFO replication
redis-cli -p 6381 INFO replication
```

For clusters using passwords/ACLs/TLS, pass appropriate auth and transport flags to Redis CLI; avoid exposing passwords in shell history or CI logs when safer secret mechanisms exist.

### 19.1. `INFO replication`

Commonly useful fields:

| Field | Meaning |
|---|---|
| `role` | Whether node is master or replica |
| `connected_slaves` | Number of connected replicas, per version field naming |
| `master_repl_offset` | Replication stream position on the primary |
| `master_link_status` | Link status to primary when node is a replica |
| `slave_repl_offset` | Replica position in Redis output |
| `master_last_io_seconds_ago` | Time since last primary I/O on replica |
| `master_sync_in_progress` | Whether replica is actively resyncing |

Field names may still use `master`/`slave` for legacy compatibility. Do not treat a few bytes of offset difference as a direct count of lost application commands; offsets measure replication stream bytes, not application entries.

### 19.2. Sentinel Pub/Sub Event Channels

Sentinel emits administrative monitoring events such as:

```text
+sdown
+odown
+switch-master
+failover-end
```

Check exact event names for your Redis version. Read individual Sentinel logs or subscribe to events in a lab:

```bash
redis-cli -p 26379 PSUBSCRIBE '*'
```

This collects events in test environments; do not run an unbounded wildcard subscription for production monitoring without evaluating volume and security. Sentinel events help stitch timelines, but **never replace application probe results**.

## 20. Capturing Exceptions and Behavior in Spring Data Redis

During failover, Spring Data Redis translates driver exceptions into `org.springframework.data.redis.*` exceptions. Log:

- `exception.getClass().getName()`.
- Root cause chain (in secure logs).
- Operation (`GET`, `SET`, `INCR`, `EVAL`, Pub/Sub...).
- Timestamp and duration.
- Application retry count.
- Endpoint used by the driver if safely observable.
- Test correlation ID / run ID.

Never include raw keys carrying user data or credentials in production logs. Log **operation group names** instead of full keys.

### 20.1. Fallback When Redis Is Strictly a Cache

When Redis caches rebuildable data, the application may choose:

```text
Redis GET hit   -> use cache
Redis GET miss  -> query data source
Redis GET error -> query data source, and record metric
```

Bear in mind:

- Losing Redis can send a surge of traffic to the database.
- Cache write failures need not fail the API if caching is purely an optimization.
- Cache invalidation failures can leave stale data alive after Redis recovers.
- Throttle fallback requests to prevent retry storms.
- Endpoints using Redis for **locks, idempotency, sessions, or business counters** must never silently bypass Redis like an ordinary cache.

### 20.2. Never Turn All Redis Errors into "Not Found"

Wrong:

```java
try {
    return redis.opsForValue().get(key);
} catch (Exception ex) {
    return null; // Connection error conflated with cache miss.
}
```

If callers treat `null` as "entity does not exist," a Redis failover turns into waves of false 404s.

Keep policies distinct: cache miss, connection error, and data error are different states.

## 21. Redis Pub/Sub, Streams, and Consumers After Failover

Spring Data Redis also supports Pub/Sub listeners and Stream consumers. Testing `StringRedisTemplate` alone is insufficient if the app relies on these mechanisms.

### 21.1. Pub/Sub

Pub/Sub does not retain history for offline subscribers. While the primary switches roles and subscriptions reconnect, messages published while a subscriber is disconnected can **be lost**.

Things to test:

- Does `RedisMessageListenerContainer` re-subscribe to channels/patterns after reconnect?
- Are messages lost by listeners during the outage window?
- After recovery, do listeners reliably receive new events?
- If Pub/Sub carries local cache invalidation notices, are TTLs/reconciliation in place to tolerate missed events?

Never expect Pub/Sub to replay messages just because Sentinel failover succeeded.

### 21.2. Redis Streams

Redis Streams persist entries by ID and provide consumer groups/PELs. Still, they rely on Redis persistence/replication and remain vulnerable if tail writes haven't reached replicas.

Also test:

- Do consumer groups exist on the new primary?
- Were `XADD`ed entries lost if unreplicated?
- Do pending entries remain and get reclaimed/ACKed?
- Does `ReadOffset.lastConsumed()` continue receiving new entries?
- Do consumers handle duplicate delivery after crash/timeout/ACK loss?
- Is retention long enough to cover downtime?

Redis Streams support pending/retry semantics at the consumer layer, but do not turn asynchronous replication into a zero-data-loss commit.

### 21.3. Lua and Transactions During Failover

When invoking Lua scripts or `MULTI/EXEC`:

- Timeouts can occur after the server executed part or all of the work and the reply was lost.
- Never unconditionally retry a script with cumulative side effects.
- Redis transactions do not span two primaries as a distributed atomic transaction.
- If the primary switches mid-processing, inspect which data replicated and how business idempotency applies.

For critical workflows, tests must verify results post-failover via event/operation IDs rather than merely checking for absence of exceptions.

## 22. Success Criteria for an HA Test

A test scenario passes when **predefined acceptance criteria** are met. Example:

| Criterion | Example Acceptance Condition |
|---|---|
| Sentinel quorum | Enough members remain to decide under target topology |
| Failover completes | Sentinel reports new primary and data-node roles match |
| RTO | Below the product's allocated budget |
| Stable recovery | N consecutive successful writes/reads after switch |
| Error rate | Within permitted threshold during transition window |
| Post-recovery latency | p95/p99 returns near baseline within measurement window |
| RPO | Missing acknowledged writes stay within target allowance |
| Rejoin | Old primary returns in replica role when expected |
| No duplicate retries | Side effects properly deduplicated via operation ID |
| Monitoring | Complete timeline/alerts and root-cause evidence |

Do not make generic promises like "RTO is always under 2 seconds." Thresholds must come from system SLAs/SLOs and matching staging/production conditions.

### 22.1. Repeat Multiple Runs

One successful test does not reveal the RTO distribution. Failover timing depends on exact kill timing, Sentinel polling intervals, replica state, and load.

Execute multiple runs of each scenario, collecting:

- Min/median/p95/max recovery duration.
- Error counts and outage durations.
- Missing acknowledged writes per run.
- Rate of runs failing to promote a replica.
- Frequency of "switch-master happened, app hasn't reconnected yet."
- Impact when the old process rejoins.

When comparing two configurations, keep load/topology identical. A setup that fails over faster while losing more writes may not be the right choice.

## 23. Common Configuration Mistakes

**Running only one Sentinel and calling it complete HA.** A single Sentinel is a single point of failure for discovery/failover management; verify quorum/majority and real topology.

**Configuring two Sentinels without understanding majority.** With an even number of Sentinels and network partitions, achieving majority can be harder than expected; deploy an odd number of at least three Sentinels for HA.

**Hardcoding a single Redis primary address in Java.** After failover, that node may become a replica or vanish.

**App reaches Sentinel but cannot reach the new primary address.** Common with Docker/NAT or firewall policies.

**Using a successful `GET` to conclude write failover finished.** Replicas may serve stale reads while writes still fail.

**Assuming every successful `SET` was replicated.** Standard Redis replication is asynchronous.

**Measuring RTO solely by Sentinel `+switch-master` timestamp.** Client reconnect and business recovery occur afterward.

**Using `PING` as the only business probe.** PING does not exercise the write path, serializers, cache invalidation, or transactions.

**Setting ultra-low command timeouts with unbounded retries.** Causes retry storms and duplicates on non-idempotent commands.

**Not keeping ACK logs outside Redis during RPO tests.** Evidence may disappear alongside the tested cluster.

**Counting TTL-expired keys as failover data loss.** RPO tests require non-expiring keys and sufficient memory policies.

**Ignoring differences between planned and unplanned failovers.** The two scenarios have different timelines and client behaviors.

**Skipping old-primary rejoin tests.** Misses routing bugs, role misconfigurations, or data conflicts during rejoin.

**Testing only once under near-zero load.** Gives no visibility into p95/p99 or stability under real app traffic.

**Treating Sentinel as a cross-database transaction coordinator.** Failover does not solve dual writes or cross-system atomic commits.

## 24. End-to-End Practice Workflow

Use the following workflow as a blueprint for staging tests:

### Step 1 – Verify Configuration

Record versions of Redis, Sentinel, Spring Boot, Spring Data Redis, Lettuce/Jedis, topology, and authentication. Verify the Spring app uses a Sentinel-aware connection factory.

### Step 2 – Verify Initial Health

Run `INFO replication` on data nodes, `SENTINEL get-master-addr-by-name`, `SENTINEL replicas`, and `SENTINEL sentinels`. Confirm quorum, replica links, and key read/write health.

### Step 3 – Start Observability

Enable the unique-key probe logging errors and durations. Run bounded background load, persisting ACK sequences outside Redis for RPO verification.

### Step 4 – Measure Baseline

Observe latency and success rate prior to fault injection. Confirm no Redis timeouts, active replica resyncs, or abnormal saturation skew the test.

### Step 5 – Inject One Deliberate Fault

Choose **one** scenario, e.g., stopping the test primary. Log exact timestamp and targeted node. Avoid injecting multiple faults simultaneously unless multi-fault testing is explicitly intended.

### Step 6 – Collect Failover Milestones

Inspect Sentinel logs/events, the new primary address, and replication status. Do not assume `+switch-master` appears simultaneously across all Sentinels.

### Step 7 – Verify End-to-End Recovery

Wait for consecutive `SET NX` + `GET` probes through Spring Data Redis to pass per your defined threshold. Log both first success and stable recovery times.

### Step 8 – Reconcile Data

Use the external ACK log to read back confirmed keys on the new primary and count missing/mismatched entries. Separate timed-out commands into an unknown-outcome bucket.

### Step 9 – Restore Test Topology

Bring the old primary back into the lab and inspect its role and replication. Never manually force the old node back to primary if doing so fights Sentinel topology.

### Step 10 – Compile Report

Sample report template:

```text
Scenario:            FT-01 - sudden primary process failure
Run ID:              ft-01-run-01
Redis/Sentinel:      <versions>
Spring Data/Lettuce: <versions>

Primary before:      <host:port>
Primary after:       <host:port>
Sentinels alive:     3/3
Replicas healthy:    2/2 before injection

Fault timestamp:     <UTC time>
First app failure:   <UTC time>
Sentinel switch:     <UTC time>
First app success:   <UTC time>
Stable app recovery: <UTC time>

Observed RTO:        <duration from fault to stable recovery>
User-visible outage: <duration by probe definition>
Failed operations:   <count>
Client retries:      <count>
p95/p99 after:       <metrics>

Acknowledged writes: <count>
Missing after:       <count>
Unknown outcome:     <count>
RPO observation:     <count or time window>

Rejoin status:       <result>
Overall status:      PASS / FAIL / INCONCLUSIVE
Notes:               <what happened and limitations>
```

If evidence is insufficient to tell whether Redis lost data or simply read from a lagging replica, mark `INCONCLUSIVE` instead of guessing.

## 25. Advanced Considerations for CI Pipelines

### 25.1. Testcontainers and Docker Compose

Testcontainers or Docker Compose can spin up multiple Redis and Sentinel containers. Containerized Sentinel topologies require special attention:

- Sentinels must see hostnames/IPs advertised by Redis data nodes.
- The Spring app inside the test JVM must reach addresses returned by Sentinel.
- Host port mapping **does not automatically rewrite** Redis addresses inside Sentinel responses.
- Network aliases and announce settings must stay consistent.
- Container startup does not automatically mean the group and replicas finished syncing.

A solid integration test uses **role-aware readiness checks**, not just open TCP ports—for example, waiting until `SENTINEL get-master-addr-by-name mymaster` resolves validly and all replicas report healthy links.

### 25.2. Separating Functional Tests from Chaos Tests

Standard CI can run:

- Spring bean and connection configuration tests.
- `SET`/`GET` via Sentinel.
- Controlled manual failover.
- Verification that clients discover the new primary.

Scenarios like network partitions, quorum loss, failover under heavy load, and multi-node kills belong in an isolated **resilience testing pipeline** with dedicated resources. Do not make shared CI flaky or disrupt shared Redis instances.

### 25.3. Set Overall Timeouts on the Test Harness

If failover stalls due to missing quorum or broken topology, a test must never hang forever.

Illustrative limits:

```text
Max wait for baseline healthy:    30 seconds
Max wait for failover outcome:    60 seconds
Max wait for stable app recovery: 60 seconds
Max test execution duration:      5 minutes
```

Adjust thresholds per lab. On timeout, collect full logs and exit with **FAIL** or **INCONCLUSIVE** as defined rather than hanging the suite.

## 26. Conclusion

**Testing failover, reconnect, and recovery time** goes beyond checking whether Sentinel picks a new primary. It is a multi-layer verification:

1. **Replication:** do replicas have sufficient data and eligibility for promotion?
2. **Sentinel:** do monitoring nodes reach quorum/majority, detect failures, and switch roles cleanly?
3. **Spring Data Redis client:** does the connection factory rediscover the primary endpoint, reconnect, and route commands accurately?
4. **Application:** do real requests resume stable `SET`/`GET` execution after failover?
5. **Data:** do acknowledged writes survive on the new primary, and do retries avoid duplicates?

Keep **observed RTO** (time from outage to application recovery under defined criteria) clearly separate from **observed RPO** (acknowledged writes lost across failover). Sentinel improves availability, yet asynchronous replication can still drop writes near the time of failure.

A meaningful test suite uses a multi-Sentinel/replica topology, exercises **Spring Data Redis exactly as the real application uses it**, runs a write–read probe with an external ACK log, monitors reconnects alongside Sentinel events, tests old-primary rejoin, and repeats runs under realistic load. Only with clear success criteria and collected evidence can you confidently state that your system meets its availability and resilience goals.
