# Topology Discovery and Handling MOVED and ASK Redirects

When an application uses **Spring Data Redis** to connect to **Redis Cluster**, a Redis key does not necessarily live on the first node the client connects to. The Cluster partitions the keyspace into **16,384 hash slots**, with each slot owned by one primary at a time. The Redis client must know which node currently owns a key's slot in order to send the command to the right place. That information is called the **cluster topology**.

Topology can change when adding/removing nodes, migrating slots (*resharding*), or during failover. If a client uses stale information, Redis may return a **`MOVED`** or **`ASK`** redirection error. For Spring Data Redis using Lettuce, the driver typically handles these redirects and updates the slot map rather than forcing business code to manually parse error strings.

This lesson explains how Redis Cluster routes keys, how topology is discovered and refreshed in Spring Data Redis, the exact meaning of `MOVED`/`ASK`, restrictions around multi-key commands, error/retry handling, and verification steps using Redis CLI.

## 1. Why must an application know the Redis Cluster topology?

Standalone Redis has a single primary data endpoint. Redis Cluster consists of multiple nodes, typically primaries and replicas:

```text
                 Spring Data Redis + Lettuce
                            |
                   Cluster slot map
                            |
         +------------------+------------------+
         |                  |                  |
         v                  v                  v
     Primary A          Primary B          Primary C
     slots 0..5460      5461..10922       10923..16383
         |                  |                  |
         v                  v                  v
      Replica A          Replica B          Replica C
```

The slot ranges in the diagram are merely an **example of one allocation**. Redis Cluster does not require always dividing into three contiguous ranges; in practice nodes may own multiple slot ranges and topology changes during resharding.

When the application runs:

```java
stringRedisTemplate.opsForValue().get("user:42:status");
```

the client logically needs to:

1. Calculate the hash slot of the key `user:42:status`.
2. Look up that slot in its current slot map.
3. Choose the appropriate node for the command type (typically primary for writes).
4. Send the command to that node.
5. If Redis reports misrouting, handle the redirection and refresh topology according to driver policy.
6. Return the final result or error to the application.

If the application only opens a TCP connection to one seed node and sends all keys there, keys belonging to other slots will routinely trigger `MOVED`. Having a cluster-aware driver avoids a redirect round-trip for every operation under normal conditions.

## 2. Redis Cluster uses 16,384 hash slots

Redis Cluster maps a key name to an integer from **0 to 16383**:

```text
slot = CRC16(keyBytes) mod 16384
```

In practice, the hash tag rule can cause Redis to use **only the substring inside the first valid pair of braces** to calculate the slot, instead of the entire key.

Example:

```text
cart:{user-42}:items
cart:{user-42}:total
```

Both keys share the hash tag `{user-42}`, so both map to the same hash slot. This is an important design tool when business logic needs multi-key Redis commands within the same slot.

Redis does not distribute individual keys by looking up a `key name → node` table for every key. It maps **hash slot → node**. A primary node can own many slots and very many keys within those slots.

### Checking slots with Redis CLI

```bash
redis-cli -p 7000 CLUSTER KEYSLOT 'cart:{user-42}:items'
redis-cli -p 7000 CLUSTER KEYSLOT 'cart:{user-42}:total'
redis-cli -p 7000 CLUSTER KEYSLOT 'user:42:status'
```

The first two commands must yield the same slot if the cluster and Redis CLI are working properly. You do not need to guess or hardcode slot numbers in the application; the driver calculates the slot from the serialized key bytes.

**Important note:** Spring Data Redis uses a key serializer. If Java uses `StringRedisSerializer`, the key bytes normally correspond to the UTF-8 string. If it uses the JDK serializer or a custom codec, the actual byte sequence of the Redis key differs, so the slot may differ from the CLI result for the human-readable string. Always verify the exact **wire format of the key** when debugging routing.

## 3. What information does topology include?

A complete topology snapshot for a cluster client typically needs details such as:

- The ID of each node in the cluster.
- Host/port endpoints that the client can connect to.
- Whether a node is a primary or replica; which primary a replica follows.
- Hash slots and slot ranges owned by each primary.
- Status related to failover, node availability, and slot migrations.
- The topology version/state the client is using to make routing decisions.

You can visualize the client-side map as:

```text
slot 0..5460       -> redis-a:7000 (primary)
slot 5461..10922   -> redis-b:7001 (primary)
slot 10923..16383  -> redis-c:7002 (primary)

Redis replica endpoints are also in the topology
for failover or read-from-replica when configured.
```

A **seed node** address is only a starting point to discover the cluster. It does not mean all commands will be sent to the seed, nor does it mean the seed acts as a load balancer that routes every key.

### The seed list is not the slot map

Configuration:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-a:7000
          - redis-b:7001
          - redis-c:7002
        max-redirects: 5
```

gives the application several endpoints it can contact to reach the cluster. After connecting/discovering, the driver obtains the topology and learns which slot belongs to which primary.

These endpoints are examples. Replace them with real hosts/ports and configure TLS/ACL for your environment. If using a different Spring Boot version, check the Redis property prefixes for that version.

Do not assume every `GET` call tries each node in the seed list sequentially. A cluster-aware client supports **slot-based routing**.

## 4. Which Redis CLI commands discover topology?

Useful inspection commands:

```bash
redis-cli -h redis-a -p 7000 CLUSTER INFO
redis-cli -h redis-a -p 7000 CLUSTER NODES
redis-cli -h redis-a -p 7000 CLUSTER SLOTS
redis-cli -h redis-a -p 7000 CLUSTER SHARDS
```

Meaning:

| Command | Key Information |
|---|---|
| `CLUSTER INFO` | Cluster state, total active slots, cluster-wide metrics |
| `CLUSTER NODES` | List of nodes, IDs, roles, link states, and slot/ranges from the queried node's perspective |
| `CLUSTER SLOTS` | Mapping of slot ranges to primary/replica endpoints; historically used by many Redis clients |
| `CLUSTER SHARDS` | Structured shard/slot/node information; recommended in Redis versions that support it |
| `CLUSTER KEYSLOT key` | Calculated slot for a Redis key |
| `CLUSTER MYID` | Node ID of the currently connected Redis node |

`CLUSTER SHARDS` exists in newer Redis versions, while `CLUSTER SLOTS` is widespread and supported by many drivers. Do not write application logic expecting every cluster to return one exact output format; let Lettuce handle discovery according to Redis/driver capabilities.

### Cluster status ok does not mean application routing works

For instance, `cluster_state:ok` indicates the cluster meets operational requirements from Redis's perspective, but it **does not prove**:

- the client has refreshed the latest slot map;
- endpoints advertised by Redis are reachable from the application network;
- all application instances use the same configuration;
- all commands have sufficient ACL permissions;
- Redis replicas are allowed and caught up enough to serve reads;
- a multi-key operation has keys in the same slot.

Combine Redis cluster state, client routing logs, endpoint reachability, and end-to-end tests through the actual Spring application path.

## 5. How does initial topology discovery happen?

A typical flow with the Lettuce cluster client:

```text
Spring Boot starts up
        |
        v
Lettuce receives list of seed endpoints
        |
        v
Connect to one or more available seed nodes
        |
        v
Fetch cluster topology (slot ranges, node endpoints)
        |
        v
Build/update slot map in Redis client
        |
        v
GET keyA -> route to primary of slotA
SET keyB -> route to primary of slotB
```

The application does not need to manually implement:

```java
try {
    getFromNodeA(key);
} catch (MovedException e) {
    parseHostAndRetry(e);
}
```

Once Redis cluster is configured properly with Lettuce, let the driver handle redirects, connection routing, and slot map refreshes. Business logic simply uses `RedisTemplate`, `StringRedisTemplate`, or `ReactiveRedisTemplate` according to the data type and use case.

However, the driver cannot fix a topology that advertises **unreachable** endpoints. For example, Redis returns `10.0.0.5:7001` in topology, whereas the application container can only reach `redis-service.internal:7001`. In that case, the cluster client discovers the nodes but fails to open connections to the target nodes.

## 6. What is MOVED?

`MOVED` is a Redis response indicating that **the slot accessed by the command belongs to another node**.

Example response:

```text
-MOVED 12182 redis-b:7001
```

Meaning:

- `MOVED`: redirection type name;
- `12182`: slot number of the accessed key;
- `redis-b:7001`: endpoint that the responding node believes owns that slot.

The example message only illustrates the structure; the slot number is not tied to any specific key name in this lesson.

### MOVED processing flow

```text
Client believes slot 12182 -> redis-a
        |
        | GET key in slot 12182
        v
redis-a
        |
        +--> "-MOVED 12182 redis-b:7001"
                              |
                              v
                   Client reroutes command
                              |
                              v
                          redis-b
                              |
                              v
                      Returns result
```

A cluster-aware client can typically:

1. Receive `MOVED`.
2. Re-execute the command at the target endpoint, within configured redirection/retry limits.
3. Recognize that the current slot map may be stale.
4. Trigger or schedule a topology refresh to update the slot mapping for subsequent commands.

Key takeaway: **`MOVED` concerns slot ownership**, not merely "the current node is temporarily busy". If a client keeps sending all commands for that slot to the old node, it may suffer continuous redirects.

### When does MOVED occur?

- The client only knows a seed node and does not yet have the slot map.
- The cluster was resharded and the slot moved to another primary.
- The client has not refreshed topology after failover/primary change.
- The client holds an older topology compared to the new state known by Redis nodes.
- The application configured a non-cluster-aware driver, sending all commands to a single endpoint.

An occasional `MOVED` during a topology change is not necessarily an incident. However, a **continuously high volume of MOVED responses** is a signal to check topology refresh, endpoint discovery, failover, and cluster client configuration.

## 7. What is ASK?

`ASK` is a **temporary** redirection, primarily occurring during the **migrating/importing hash slot** phase when Redis Cluster is moving keys from a source primary to a target primary.

Illustrative response:

```text
-ASK 12182 redis-b:7001
```

Unlike `MOVED`, `ASK` **does not assert that official ownership of the entire slot has shifted to the target node**. It indicates that **this specific command** should be sent temporarily to the target node.

### Migrating and importing states

When resharding a slot from A to B:

```text
Primary A: slot is MIGRATING to B
Primary B: slot is IMPORTING from A

Keys in the slot may be partially moved
during the transition window.
```

During this window, some keys may still reside on A while others have moved to B. The source node can return `ASK` for relevant requests so the client tries the command on B, while official slot ownership has not yet been fully transitioned to B.

### ASK and ASKING processing flow

```text
Client uses current slot map: slot 12182 -> A
       |
       | GET key
       v
       A
       |
       +--> "-ASK 12182 B:7001"
                    |
                    v
           Connect to B
                    |
                    +--> ASKING
                    |      (B allows the next command
                    |       to access the importing slot)
                    |
                    +--> GET key
                    |
                    v
                Returns result

Client's long-term slot map does not change
just from receiving a single ASK.
```

**`ASKING` is a Redis command that applies to the next request on the appropriate connection.** The client must send `ASKING` followed by the redirected command to the importing node in a way that preserves connection context. Do not simply catch `ASK` and send `GET` to the target node over an arbitrary connection without `ASKING`.

After resharding finishes and official slot ownership changes, nodes direct clients according to the new topology, and `MOVED` may appear if the client's slot map is still stale.

## 8. Comparison table: MOVED vs. ASK

| Attribute | `MOVED` | `ASK` |
|---|---|---|
| Meaning | The slot belongs to another node | This command must be processed temporarily on another node |
| Common context | Wrong/stale slot map, ownership change, failover | Resharding while slot is migrating/importing |
| Update long-term slot map from redirect alone? | Grounds to update/refresh topology | **Do not** permanently change slot owner from ASK alone |
| Where do subsequent requests go? | Node owning the slot in new topology | Current command goes to the node specified by ASK |
| Require `ASKING` before command on target? | No, for MOVED | **Yes**, per the ASK protocol |
| Client objective | Retry on new owner and refresh topology | Temporary retry with ASKING, continue tracking topology |
| When errors persist | Check slot map/endpoints/redirect loop | Check stuck resharding, importing state, and retries |
| Considered business execution complete? | Routing rejection redirect, not a successful business result | Temporary redirect; must re-execute per protocol |

An easy rule of thumb:

> **MOVED: "this slot belongs elsewhere." ASK: "for this command, temporarily ask that other node and say ASKING first."**

Both are normally handled by the Redis client within configured redirect limits. A Spring Data Redis application does not need to manually send `ASKING` when Lettuce handles ASK properly.

## 9. Why shouldn't ASK change the entire slot map?

Consider slot S migrating from A to B. Some keys in S are still on A, while others are already on B:

```text
Slot S is MIGRATING A -> B

A: keyX (not yet moved)
B: keyY (already moved)
```

If the client receives an `ASK` for `keyY` and updates all of slot S to point to B, the next request for `keyX` might be sent erroneously to B while that key is still on A.

Therefore:

- `ASK` should be handled **per command**.
- The slot map should be updated when topology/ownership has actually changed, not merely on an isolated ASK.
- Once migration finishes, topology discovery will reflect the new slot owner.
- If migration drags on, the client may see many `ASK` responses while the cluster has not yet finalized ownership.
- Monitoring prolonged ASK rates helps detect stalled resharding.

## 10. At which layer do Spring Data Redis and Lettuce handle redirects?

In a typical configuration:

```text
Business Service
        |
        v
StringRedisTemplate / RedisTemplate
        |
        v
LettuceConnectionFactory
        |
        v
Lettuce cluster client
        |
        +--> hash slot lookup
        +--> node routing
        +--> MOVED/ASK redirection
        +--> topology refresh
        +--> connection/retry handling
        |
        v
Redis Cluster
```

`StringRedisTemplate` does not need to know whether a key lives on primary A or primary B. It sends commands through the Redis connection abstraction. Topology management and redirection reside primarily in the **cluster-aware driver**.

When errors occur:

- A valid `MOVED` is usually rerouted by the driver and does not necessarily surface as an exception to the service.
- `ASK` can be handled by the driver issuing `ASKING` followed by the command on the target node.
- If the redirect limit is exceeded, the endpoint is unreachable, the cluster is unavailable, or the driver lacks a valid topology, the application may still receive a Redis error.
- Avoid catching every Redis exception and parsing `MOVED`/`ASK` strings to retry at the business layer; doing so easily conflicts with the driver and causes retry storms.

What must be configured right from the start is that the connection factory is actually built for **Redis Cluster**, not a standalone connection factory pointed at one cluster node.

## 11. Configuring Redis Cluster via Spring Boot properties

Example using Spring Boot and Lettuce:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-a.internal:7000
          - redis-b.internal:7001
          - redis-c.internal:7002
        max-redirects: 5
      connect-timeout: 2s
      timeout: 3s
```

Meaning:

- `cluster.nodes` is the list of seed endpoints.
- `max-redirects` caps the number of cluster redirects per supported Spring/driver mechanism.
- `connect-timeout` and `timeout` prevent requests from hanging indefinitely when a network/node is unresponsive.
- Spring Boot and Lettuce use the discovered topology for routing.
- You must use DNS/IPs/ports actually reachable from the application runtime environment.

These values are examples; adjust them according to latency, retry budgets, deployment, and Spring Boot version. Do not set an excessively high redirect limit to "solve" persistent topology errors. A redirect loop can indicate inconsistent node configuration or a broken reshard/failover.

### Do all primaries need to be listed as seeds?

Not necessarily. A few seed nodes can suffice to discover the cluster if they are reachable and provide full topology. However, **multiple seeds increase the chance of successful initial connection** if one seed is down.

You do not need to manually list every Redis replica for individual keys to find their paths, but you should configure enough stable seed endpoints, DNS, and ACL/TLS so the client learns the correct topology. The seed list does not replace refreshing when the cluster changes nodes.

## 12. Configuring proactive Lettuce topology refresh

When topology changes, a previously valid slot map can go stale. Lettuce supports scheduled refreshes and adaptive refreshes triggered by cluster change signals.

Explicit Java configuration example, for applications wanting to manage the connection factory directly instead of relying solely on Boot auto-config:

```java
package example.redis.cluster;

import java.time.Duration;
import java.util.List;

import io.lettuce.core.cluster.ClusterClientOptions;
import io.lettuce.core.cluster.ClusterTopologyRefreshOptions;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisClusterConfiguration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
public class RedisClusterConfigurationExample {

    @Bean
    public LettuceConnectionFactory redisConnectionFactory() {
        RedisClusterConfiguration cluster =
                new RedisClusterConfiguration(
                        List.of(
                                "redis-a.internal:7000",
                                "redis-b.internal:7001",
                                "redis-c.internal:7002"));

        cluster.setMaxRedirects(5);

        ClusterTopologyRefreshOptions refreshOptions =
                ClusterTopologyRefreshOptions.builder()
                        .enablePeriodicRefresh(Duration.ofSeconds(30))
                        .enableAllAdaptiveRefreshTriggers()
                        .build();

        ClusterClientOptions clientOptions =
                ClusterClientOptions.builder()
                        .topologyRefreshOptions(refreshOptions)
                        .build();

        LettuceClientConfiguration clientConfiguration =
                LettuceClientConfiguration.builder()
                        .clientOptions(clientOptions)
                        .commandTimeout(Duration.ofSeconds(3))
                        .build();

        return new LettuceConnectionFactory(
                cluster, clientConfiguration);
    }

    @Bean
    public StringRedisTemplate stringRedisTemplate(
            RedisConnectionFactory redisConnectionFactory) {
        return new StringRedisTemplate(redisConnectionFactory);
    }
}
```

Here:

1. `RedisClusterConfiguration` declares the seed nodes and redirect limit.
2. `ClusterTopologyRefreshOptions.enablePeriodicRefresh(...)` instructs Lettuce to update topology periodically.
3. `enableAllAdaptiveRefreshTriggers()` enables the adaptive refresh triggers supported by Lettuce, such as when redirections or topology anomalies are detected.
4. `ClusterClientOptions` attaches the refresh options to the cluster client.
5. `LettuceClientConfiguration` sets the command timeout.
6. `LettuceConnectionFactory` creates cluster-mode connections.
7. `StringRedisTemplate` uses that factory at the Redis operations layer.

**Note:** Lettuce/Spring Data Redis versions may offer additional options or alter builder APIs; check the managed dependencies in your project before applying this in production code. This Java configuration **must not be deployed alongside** another auto-configured factory bean if that would cause duplicate beans. It also omits ACL/TLS credentials; production must configure security from appropriate environment sources.

### Periodic refresh vs. adaptive refresh

| Refresh Method | When Triggered | Benefit |
|---|---|---|
| **Periodic** | On a predetermined schedule | Limits slot map staleness when changes produce few redirects |
| **Adaptive** | When signals like multiple redirects or topology changes are observed by the driver | Reacts faster to failover/reshard |
| **Initial discovery** | When the cluster client starts or needs initial topology | Supplies the slot map for initial routing |
| **MOVED handling** | When a command is directed to a new owner by the server | Fixes the current command's route and hints the map needs refresh |
| **ASK handling** | When a command must go temporarily to an importing node | Completes the command during reshard without changing full slot ownership |

Adaptive refresh typically includes rate limiting/throttling so not every redirect sparks a burst of topology discovery requests. Do not set polling intervals too short without assessing load on the nodes and the number of client instances.

## 13. Configuring applications to use RedisTemplate without manually handling MOVED/ASK

With a cluster-aware connection factory, services call Redis normally:

```java
package example.redis.cluster;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class UserStatusService {

    private final StringRedisTemplate redis;

    public UserStatusService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void updateStatus(String userId, String status) {
        redis.opsForValue()
                .set("user:{" + userId + "}:status", status);
    }

    public String readStatus(String userId) {
        return redis.opsForValue()
                .get("user:{" + userId + "}:status");
    }
}
```

Business code contains no node addresses, hash slots, or redirect parsing logic. That is the strength of a cluster-aware client. If the Redis topology changes or slots are resharded, this service in principle does not need to change.

However, the code must honor the **serializer and key naming** contract. In the example, a hash tag per user ID keeps keys related to the same user in the same slot if needed, though this should only be applied when business logic justifies it. Never use a single shared hash tag for all users, as that concentrates the entire application's load onto one slot/primary.

### Cluster routing and the reactive API

If the application uses `ReactiveRedisTemplate`, slot selection and redirect handling also live in the Lettuce cluster client. The difference is that results are emitted through `Mono`/`Flux` rather than blocking the caller synchronously. Errors exceeding routing/retry limits are signaled through the publisher.

Maintain the reactive pipeline properly; an unsubscribed publisher will not send commands merely because a service constructed it.

## 14. How do MOVED/ASK differ from CROSSSLOT?

A very common mistake when moving from standalone to Redis Cluster is running multi-key commands whose keys do not belong to the same slot.

Example:

```bash
redis-cli -c -p 7000 MGET user:42:profile user:43:profile
```

The two keys can belong to different slots. Redis Cluster cannot execute a multi-slot `MGET` as a regular single atomic command, so it may return:

```text
-CROSSSLOT Keys in request don't hash to the same slot
```

**`CROSSSLOT` is not `MOVED` or `ASK`.** The driver cannot simply retry on another node to turn an invalid multi-slot command into a valid one.

### Hash tags when multi-key commands are needed

Example for a single user:

```text
user:{42}:profile
user:{42}:settings
user:{42}:balance
```

These keys share the hash tag `{42}`, so they share the same slot. Multi-key commands can be used when supported by the Redis command and all keys belong to the same slot:

```bash
redis-cli -c -p 7000 CLUSTER KEYSLOT 'user:{42}:profile'
redis-cli -c -p 7000 CLUSTER KEYSLOT 'user:{42}:settings'
```

Notes:

- Hash tags only solve **slot placement**.
- They do not guarantee business consistency across multiple keys' data.
- They do not solve Redis node crashes, network failures, or transactions with other databases.
- Forcing all keys under a tag like `{global}` turns a single slot into a hotspot.
- When using a binary Redis serializer, inspect the actual key bytes to confirm hash tags apply as intended.

Some high-level APIs may split an operation across multiple nodes or issue multiple independent commands where supported. Do not infer that they carry the same atomicity as a single Redis command: know the exact contract of the API and driver.

## 15. MOVED, ASK, and other Redis Cluster errors

Not every cluster error is a redirection. When designing error handling, categorize them:

| Error / State | Common Cause | Handling Approach |
|---|---|---|
| `MOVED` | Slot belongs to a primary other than the receiving node | Cluster-aware routing, refresh topology, driver-level retry |
| `ASK` | Temporary redirect while slot is migrating/importing | Send `ASKING` then command to target; do not permanently change slot owner |
| `CROSSSLOT` | A multi-key command violates the slot constraint | Redesign keys/tags or split operations; do not blindly retry |
| `TRYAGAIN` | Temporary cluster state unable to serve command, possibly during resharding | Bounded retry/backoff if appropriate; check reshard status |
| `CLUSTERDOWN` | Cluster cannot serve commands due to cluster state | Check node/slot coverage, failover, and infrastructure |
| `READONLY` | Write sent to a replica/read-only endpoint | Check primary/replica routing and topology |
| Timeout / connection lost | Node unresponsive, DNS/TLS/network error | Distinguish unsent commands from uncertain execution outcomes |
| `NOAUTH` / `NOPERM` | Invalid authentication or ACL permissions | Fix credentials/permissions; do not retry redirects |
| Too many redirects | Oscillating slot map, node disagreement, or max redirects too low | Inspect topology/failover; do not simply raise limit infinitely |

In a resharding Redis Cluster, some multi-key commands on the same slot may encounter `TRYAGAIN` if the keys are temporarily in different migration phases. This differs from `CROSSSLOT`: with `TRYAGAIN`, the slot placement can be valid, yet a transient state prevents completing the command right now.

### Do not classify every error as "retryable"

An exception caused by a bad schema/serializer, missing ACL permissions, or `CROSSSLOT` will not disappear by retrying repeatedly. Retrying uncategorized errors adds extra load right when the cluster is struggling.

Distinguish **transient routing errors**, **transient infrastructure errors**, and **design/configuration errors** to choose the right response.

## 16. When failover happens, how does topology change?

Redis Cluster can promote a replica to primary during failover. Example:

```text
Before failover:
  Primary A -> slot S
  Replica A1 -> replicates A

After failover:
  A1 is elected new primary for slot S
  A may be unavailable or rejoin in another role
```

A client still believing slot S belongs to endpoint A may encounter:

- Connection errors to A.
- `MOVED` from nodes aware of the new topology.
- Topology refresh results showing A1 as the new owner.
- A brief window of failed commands during failover.

The Lettuce cluster-aware client is designed to track routing/topology, but **cannot guarantee every command during the failover window will succeed**. Applications need timeouts, retry budgets, and handling for uncertain outcomes.

### Failover does not provide strong consistency by default

Redis Cluster typically replicates data from primary to replica **asynchronously**. If a primary fails before an acknowledged write finishes replicating, there is still a risk of losing writes near the failover boundary under the actual durability/consistency model.

Therefore, "the client successfully handled `MOVED`" does not equate to "every write before failover was preserved". These are two separate dimensions: **routing** and **durability**.

If Redis holds critical business data, evaluate replication, persistence, backups, and acknowledgment mechanisms against your requirements; do not rely solely on redirect handling.

## 17. Reading from Redis replicas and staleness implications

Redis Cluster write paths normally go to the primary responsible for the slot. Some applications configure Lettuce to allow **reading from replicas** to distribute read load.

Example client option, to be used only when the consistency trade-off is understood:

```java
import io.lettuce.core.ReadFrom;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;

LettuceClientConfiguration clientConfiguration =
        LettuceClientConfiguration.builder()
                .readFrom(ReadFrom.REPLICA_PREFERRED)
                .build();
```

When choosing replica reads:

- Reads can return **stale values** due to replication lag.
- Failover can change replica/primary roles.
- Read-your-writes cannot be assumed just because the client just wrote to the primary.
- Routing must rely on updated topology and proper driver support for the read mode.
- Never use replica reads for business decisions requiring confirmation of the latest state without additional guarantees.

Customizing read preference on a `LettuceClientConfiguration` must be paired with appropriate cluster settings. This example illustrates the option, not a recommendation for replica reads in all applications.

## 18. Are node addresses advertised by Redis always reachable?

One of the hardest Redis Cluster issues to diagnose appears in Kubernetes, Docker, NAT, or across VPC networks.

Suppose the application connects to the seed endpoint:

```text
redis-gateway.example.internal:7000
```

But when querying topology, Redis returns node addresses:

```text
10.1.0.8:7000
10.1.0.9:7001
10.1.0.10:7002
```

If the application runs outside the network containing `10.1.0.0/16`, those addresses may be unreachable. Cluster discovery succeeds in returning data, yet commands to the slot owner fail.

Symptoms:

- Seed connects, yet `GET` on certain keys times out.
- `CLUSTER NODES`/`CLUSTER SHARDS` shows different hostnames/IPs than reachable service endpoints.
- Error rates spike when commands target slots on other nodes.
- Application instances inside the internal network work fine while instances from another network fail.
- TLS hostname verification mismatches the address advertised by Redis.

Operational fixes:

1. Ensure endpoints Redis advertises in topology are reachable from all cluster clients that must connect.
2. Correctly configure DNS, NAT, service discovery, and Redis/server cluster announce settings.
3. Align TLS certificates with the hostnames used by clients.
4. For managed Redis, follow the provider's endpoint/discovery documentation.
5. Avoid turning a single node into a routing-blind proxy while expecting the driver to magically fix all misconfigured NAT addresses.

Redis offers server-level settings for announcing cluster addresses/ports. Do not change them haphazardly in production just because you see a `MOVED`; inspect the entire network model first.

### Client port vs. cluster bus port

Redis Cluster also uses a **cluster bus** channel for nodes to exchange cluster state. The bus port is separate from the client port—in traditional default setups, following a port offset rule. However, **application Redis clients do not send GET/SET over the cluster bus port**.

Distinguish:

- Client port used for RESP commands.
- Cluster bus port used for inter-node Redis communication.
- Endpoints advertised to clients must point to the port serving Redis commands.

Opening the cluster bus port by mistake for a Spring application will not resolve MOVED/ASK.

## 19. Safe retries during redirects and connection loss

An important principle is distinguishing an **explicit redirect response** from a **timeout with unknown execution status**.

### 19.1. Redirect responses

If Redis returns `MOVED` or `ASK` instead of executing the business command on the wrong node, the driver can re-execute the command per the redirect protocol. This is normal behavior for a cluster-aware client.

Still, redirect limits and unreachable endpoints can cause a final error. Applications should usually let the client handle routing rather than adding a "retry three more times" wrapper around every exception.

### 19.2. Lost response after a command was sent

Suppose:

```text
App -> Redis primary: INCR billing:counter
Redis: INCR succeeds
Network: response lost before app receives it
App: times out, outcome unknown
```

If the application retries `INCR` without an idempotency mechanism, the counter may be incremented twice.

| Command | Retry After Timeout | Notes |
|---|---|---|
| `GET` | Usually low side-effect risk | May observe a newer value on retry |
| `SET key value` | Depends on contract | Overwriting the same value may repeat, though TTL/version could change |
| `DEL` | Usually idempotent for final state | Count of deleted keys returned may differ |
| `INCR`/`DECR` | Do not retry blindly | Can cause duplicate execution |
| `LPUSH`/`XADD` | Do not retry blindly | Can create duplicate entries |
| Lua with side effects | Depends on design | Atomicity does not guarantee idempotency |

Enforce retry limits, appropriate backoff, an overall timeout, and a way to detect already-executed operations when business logic has side effects.

### Do not use MOVED as an excuse to swallow errors

If a command still fails after Lettuce processes redirects, preserve the root error, hostname, slot/namespace (if available), and topology state. Never turn every exception into a cache miss or default value without telemetry.

## 20. Lab: observing MOVED with redis-cli

Use a **test Redis Cluster** with multiple active primaries. The ports and hostnames below are examples; substitute your lab environment's values.

### Step 1 — Discover topology

```bash
redis-cli -h 127.0.0.1 -p 7000 CLUSTER INFO
redis-cli -h 127.0.0.1 -p 7000 CLUSTER NODES
redis-cli -h 127.0.0.1 -p 7000 CLUSTER SLOTS
```

If supported by your Redis version:

```bash
redis-cli -h 127.0.0.1 -p 7000 CLUSTER SHARDS
```

Identify the slot ranges owned by each primary.

### Step 2 — Compute the hash slot of a key

```bash
redis-cli -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'course:redis:352'
```

Compare the result with the ranges in Step 1 to identify the owner.

### Step 3 — Send a command to a node that does not own the slot

Choose a test node **that does not own the slot** for `course:redis:352`, and run without `-c`:

```bash
redis-cli -h 127.0.0.1 -p 7000 GET 'course:redis:352'
```

If node 7000 does not own the slot, Redis may return:

```text
(error) MOVED <slot> <owner-host>:<owner-port>
```

`<slot>` and `<owner-host>` in the example are explanatory placeholders, not literal output.

If node 7000 happens to own the slot, the command will return a value or nil **without MOVED**. To observe MOVED, select a node that is not the owner per topology.

### Step 4 — Let redis-cli follow redirects automatically

```bash
redis-cli -c -h 127.0.0.1 -p 7000 SET 'course:redis:352' 'ready'
redis-cli -c -h 127.0.0.1 -p 7000 GET 'course:redis:352'
```

Depending on slot state, the CLI may display a redirect notice and automatically connect to the new owner. The `-c` flag enables cluster mode so `redis-cli` follows redirects, including proper ASK handling.

This illustrates the server protocol; in a Spring Data Redis application, Lettuce typically performs the equivalent at the driver layer without the business service seeing individual steps.

### Step 5 — Verify keys sharing a hash tag

```bash
redis-cli -c -p 7000 CLUSTER KEYSLOT 'cart:{lab-user}:items'
redis-cli -c -p 7000 CLUSTER KEYSLOT 'cart:{lab-user}:total'
```

Both results must be equal. Try `MGET` on two keys with the same hash tag after setting values, then compare against keys without a shared hash tag to understand `CROSSSLOT`.

## 21. Lab: observing ASK during resharding

`ASK` usually appears only during a **slot migration window**, making it harder to observe than `MOVED` on a steady cluster.

Observation steps in a **dedicated lab cluster**:

1. Create a multi-primary Redis Cluster with some keys in slot S.
2. Record the current owner of slot S using `CLUSTER SLOTS`/`CLUSTER SHARDS`.
3. Use the cluster administration tool to reshard slot S from primary A to primary B.
4. While the slot is in the migrating/importing state, send commands targeting keys in slot S.
5. Observe whether `ASK S B:port` appears, depending on whether each key has already moved and the exact command timing.
6. Use `redis-cli -c` to watch the client follow the redirect automatically.
7. Once resharding finishes, verify the slot's new owner and observe `MOVED` from a client holding stale topology.

Because the ASK window is often brief, not every attempt will catch it. Failing to see ASK once **does not mean the system is broken**.

Never initiate resharding tests on a production Redis Cluster merely to observe errors. Moving slots can impact routing, latency, and live application data.

### Why shouldn't ASKING and GET be sent as two separate redis-cli commands?

`ASKING` must be paired with the redirected command **on the exact same connection**. Running two separate `redis-cli` processes can use different TCP connections, so the ASKING state will not apply as intended.

To observe at the protocol level, use a single interactive connection session or let a cluster-aware client like `redis-cli -c`/Lettuce execute the `ASKING` + command sequence properly.

## 22. Integration testing Spring Data Redis with a real cluster

A test that merely mocks `StringRedisTemplate` cannot verify slot calculation or `MOVED`/`ASK` handling. You need a dedicated **lab cluster** with seed nodes, slot ranges, and network DNS mirroring your deployment environment.

Simple service to verify the read/write path:

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ClusterProbeService {

    private final StringRedisTemplate redis;

    public ClusterProbeService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String putAndGet(String key, String value) {
        redis.opsForValue().set(key, value);
        return redis.opsForValue().get(key);
    }
}
```

An integration test can call `putAndGet` on multiple keys across different slots to verify driver routing, then trigger a topology change in the test cluster environment and continue reading/writing.

Scenarios to verify:

- Connecting via one seed node while operating on keys across other primaries.
- Whether the initial slot map covers the full `0..16383` range.
- Behavior when one seed node is unavailable at app startup.
- Cluster resharding triggering `MOVED`/`ASK` while the client continues reading accurately.
- Primary replacement via failover and tracking error/recovery.
- Redirect limit exceeded or unreachable target node.
- Running a multi-key command with keys in different slots to distinguish `CROSSSLOT`.
- Endpoint advertised by Redis being unreachable from the test client.
- Replica reads returning stale versions when read preference is enabled.
- Timeout occurring after a write with side effects and how retries are guarded.

Do not assert "zero errors during every millisecond of failover" when Redis infrastructure does not provide that guarantee. Verify **recovery time**, error bounds, and business correctness once the cluster stabilizes.

## 23. Metrics to monitor when operating topology

An application that only logs "Redis connection failed" makes it hard to distinguish slot map errors, network issues, and reshard errors.

| Signal | What to Investigate |
|---|---|
| `MOVED` count | Stale slot map, ownership change, or non-cluster-aware client |
| `ASK` count | Active resharding; if prolonged, migration may be stuck |
| Topology refresh count/duration | Whether the driver updates the map promptly and successfully |
| Redirect retries/exhausted | Redirect loop, unreachable node, or max redirects |
| Redis command timeouts | Network, overloaded node, latency, or failed routing |
| Redis failover events | Primary role change, connectivity, and availability |
| `CLUSTERDOWN` / `TRYAGAIN` | Slot coverage capability and cluster transition state |
| `CROSSSLOT` errors | Incompatible key patterns or multi-key commands |
| Endpoint connection failures | DNS, NAT, TLS, ACL, or wrong announce address |
| Redis command latency p95/p99 | User-experienced latency across nodes |
| Read-from-replica lag | Risk of returning stale data |
| Node CPU/memory/slot distribution | Skewed load, hot slots/hot keys, reshard pressure |

Not every driver exposes a built-in metric literally named "MOVED count". You may need to configure logs, Lettuce metrics/tracing, or categorized application error tracking. Avoid verbose logging for every single redirect in production, as resharding can cause log floods.

## 24. Diagnosing by symptom

### 24.1. GET works for some keys while others time out

Very likely only certain slots are routing to an unreachable node/endpoint. Check:

1. `CLUSTER KEYSLOT` of the failing key.
2. Slot owner in `CLUSTER SHARDS` or `CLUSTER SLOTS`.
3. Whether the advertised host/port is reachable from the application.
4. DNS/TLS/ACL for that specific node.
5. Whether Lettuce has discovered topology and has proper retry/refresh settings.

Do not assume the entire cluster is down just because a subset of keys fails.

### 24.2. Application sees continuous MOVED responses

Check whether the factory is truly cluster-aware, whether topology refresh is enabled, whether Redis is actively resharding/failing over, whether endpoints are reachable, and whether the slot map is flapping.

If the application connects to the cluster using a standalone factory, it may hit repeated redirects or errors. **Fix the connection topology** rather than merely raising max redirects.

### 24.3. Unusually prolonged ASK responses

Check whether slot migrating/importing is completing. Stuck resharding can force many commands into temporary redirects. Verify state via administrative cluster commands from infrastructure, and monitor migration progress and latency impact.

Never manually alter `CLUSTER SETSLOT` in production without a clear plan and ownership.

### 24.4. Spring Data Redis reports CROSSSLOT

Inspect all Redis keys actually participating in the command, including keys used by Repositories/indexes/metadata or Lua scripts. Use intentional hash tags when multiple keys must share a slot, or split operations according to semantics. Retrying redirects will not fix `CROSSSLOT`.

### 24.5. Still connecting to old primary after failover

Check topology refresh, DNS, driver version, new node roles, Redis Cluster announce endpoints, and how the application selects read/write nodes. When using replica read preferences, distinguish stale cache reads from wrong primary ownership.

### 24.6. Redis CLI -c works, Spring application fails

Possible causes include:

- CLI and application use different DNS/network namespaces.
- CLI uses different TLS/authentication.
- Spring is configured for standalone instead of cluster.
- Spring's key serializer produces different bytes than the string typed in CLI.
- Spring specifies an incompatible Redis database/index (Redis Cluster normally uses database 0).
- Different Lettuce/Spring Data version or client options.
- Application holds a stale topology because refresh is off or node endpoints are unreachable.

Compare **identical key bytes, identical topology, and identical security context** rather than assuming Java must work simply because CLI worked.

## 25. Common misconceptions

**"MOVED means Redis lost the key."** No. MOVED is a slot routing instruction pointing to another node; it says nothing about whether the key exists.

**"ASK is the same as MOVED; just update the slot map."** Wrong. ASK is a temporary redirect during resharding requiring `ASKING` on the target for that command; do not equate it with permanent slot ownership.

**"Lettuce already has seeds so it doesn't need topology refresh."** Seeds only support initial discovery. Slot ownership can change after failover/resharding.

**"MOVED and ASK must always be handled in service code."** Not when using properly configured cluster-aware Lettuce. The driver handles them; services should focus on business logic and remaining errors.

**"CROSSSLOT is a special kind of MOVED."** No. CROSSSLOT reflects a multi-key command incompatible with slot partitioning. There is no single target node to redirect to atomically.

**"Using the same hash tag for all keys is simplest."** That forces all keys into one slot, defeating distribution and creating a hotspot.

**"Failover with MOVED handled means zero writes were lost."** No. Redis Cluster has its own replication/failover semantics, often carrying a risk of losing recent writes near a primary failure if not durably replicated.

**"On client timeout, it is safe to retry INCR."** No. Redis may have already executed INCR before the response was lost; retrying can increment twice.

**"Connecting to one seed endpoint means all nodes are reachable."** No. Endpoints advertised by topology may sit behind NAT, private networks, or hostnames unresolvable by the application.

## 26. Self-assessment questions

**1. Why does Redis Cluster use a slot map instead of connecting to just one host?**

Because Redis Cluster distributes keys across 16,384 slots owned by different primaries; the client must route each command to the appropriate node.

**2. What does MOVED report?**

The node receiving the command indicates the slot belongs to a different node. The client should redirect the command and refresh its topology map via cluster-aware mechanisms.

**3. During which phase does ASK primarily appear?**

When Redis Cluster is actively migrating/importing a slot during resharding, a command may need to be temporarily handled on the receiving node.

**4. What command does ASK require right before the command on the target node?**

`ASKING`, on the exact same appropriate connection, immediately before the redirected command.

**5. Should the permanent owner of the entire slot be updated after a single ASK?**

No. ASK is a per-command temporary redirect; the long-term slot map should only update once ownership/topology has actually changed.

**6. Why can't two keys in different hash slots be combined in every multi-key command?**

Redis Cluster enforces hash-slot constraints on multi-key commands. A cross-slot command such as `MGET` can return `CROSSSLOT`.

**7. What do hash tags help with?**

Keys sharing the same valid tag content inside curly braces map to the same slot, which is useful for multi-key operations scoped to one entity.

**8. Why can MOVED occur even when Redis Cluster reports `cluster_state:ok`?**

The client may hold a stale slot map after reshard/failover, or may have sent a command to a seed node that does not own that slot.

**9. Why might Redis CLI succeed while Spring still fails?**

They may differ in client mode, endpoints, networking, TLS/ACL, serialization, or topology refresh.

**10. Should every timeout after failover be retried?**

No. For writes with side effects like `INCR`, the command may have already executed while the caller lost the reply; idempotency and appropriate retry policies are required.

## 27. Implementation takeaways

- Redis Cluster routes by **16,384 hash slots**; cluster-aware clients maintain a slot → primary mapping.
- Seed nodes are for **topology discovery**, not for receiving every command.
- `MOVED` indicates the slot belongs to another node; the client must redirect and re-evaluate topology.
- `ASK` is a **temporary** redirect during resharding; it requires `ASKING` before the command on the target node and must not permanently change full slot ownership.
- Spring Data Redis with cluster-aware Lettuce typically handles redirects at the driver layer; business services should not manually parse responses to route.
- Configure periodic and adaptive topology refresh to limit stale slot maps; monitor redirect loops and endpoint connectivity.
- `CROSSSLOT` is not a redirect error; multi-key commands must satisfy slot constraints, potentially using sensible hash tags.
- Redis Cluster failover does not eliminate command errors, timeouts, or lost writes per replication semantics.
- Retries must distinguish explicit redirects from **timeouts where command execution is uncertain**.
- Use Redis CLI `CLUSTER INFO`, `CLUSTER SHARDS`/`SLOTS`, `CLUSTER KEYSLOT`, and `redis-cli -c` for diagnostics in appropriate environments.
- In Kubernetes/NAT/TLS environments, verify that **node endpoints advertised by Redis** are genuinely reachable from application instances.
- Never apply one shared hash tag to all keys, and never manually modify slot ownership in production without an orchestrated plan.

A helpful mental model is: **the slot map decides where to send commands, MOVED updates knowledge of the slot owner, and ASK resolves commands while a slot is in transit**. When these three aspects are clearly separated, configuring Lettuce, reading logs, and recovering after reshard/failover become far less confusing.

## References

- [Spring Data Redis — Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html): connecting to Redis Cluster, RedisClusterConfiguration, and Spring Data Redis operations.
- [Spring Data Redis — LettuceConnectionFactory API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/connection/lettuce/LettuceConnectionFactory.html): connection factory for standalone/Sentinel/Cluster.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): Redis operations through templates.
- [Redis — Cluster Specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): hash slots, hash tags, MOVED, ASK, ASKING, migration, and failover.
- [Redis — Redis Cluster Tutorial](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/): configuring and operating a cluster.
- [Redis — CLUSTER SHARDS](https://redis.io/docs/latest/commands/cluster-shards/): shard/slot/node information.
- [Redis — CLUSTER SLOTS](https://redis.io/docs/latest/commands/cluster-slots/): mapping slot ranges to endpoints.
- [Redis — CLUSTER KEYSLOT](https://redis.io/docs/latest/commands/cluster-keyslot/): determining the slot for a key.
- [Redis — ASKING](https://redis.io/docs/latest/commands/asking/): ASK redirect protocol for importing slots.
- [Redis — CLUSTER NODES](https://redis.io/docs/latest/commands/cluster-nodes/): node IDs, roles, and slot ranges.
- [Lettuce — Redis Cluster](https://redis.github.io/lettuce/ha-sharding/): cluster client, routing, and topology refresh.
