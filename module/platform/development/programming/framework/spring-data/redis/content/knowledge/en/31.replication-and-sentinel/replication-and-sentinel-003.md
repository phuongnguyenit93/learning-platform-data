# Configuring Redis Sentinel Connections in Spring Data Redis

## 1. Goal: Application Finds the Right Redis Master After Failover

A Spring Boot application often connects to Redis using a fixed host and port pair:

```yaml
spring:
  data:
    redis:
      host: redis-primary.internal
      port: 6379
```

This approach is easy to understand, but has a limitation: if the Redis master fails and a replica is **promoted to master**, the valid write address has changed. An application that keeps sending commands to the old address may encounter connection errors or `READONLY`.

**Redis Sentinel** is a monitoring and failover coordination mechanism for the Redis primary–replica model. When using Sentinel, the application does not hard-code a single master address. It knows the **master group name** and a set of Sentinel addresses, queries Sentinel to discover the current master, and then connects to the corresponding Redis data node.

```text
                         Spring Boot
                             |
                             | 1. Ask Sentinel:
                             |    where is master "mymaster"?
                             v
                +---------------------------+
                | Sentinel A / B / C        |
                | ports typically 26379     |
                +-------------+-------------+
                              |
                              | 2. Return Redis master address
                              v
                      +---------------+
                      | Redis Master  |
                      | 10.10.0.11    |
                      | port 6379     |
                      +-------+-------+
                              |
                  asynchronous replication
                         /           \
                        v             v
               +-------------+ +-------------+
               | Replica 1   | | Replica 2   |
               +-------------+ +-------------+
```

When the master changes, a Redis client configured with Sentinel can discover the new master and restore connections according to the driver's mechanism.

**Key takeaway:** Sentinel helps *discover and switch masters*, but does not turn Redis into a zero-loss distributed transactional database, does not guarantee zero downtime, and does not automatically retry every business operation safely.

This lesson focuses on how to **configure Redis Sentinel connections in Spring Data Redis**, along with required infrastructure conditions, Spring Boot examples, pure Java configuration, authentication, failover testing, and operational troubleshooting.

## 2. Three Distinct Components: Master, Replica, Sentinel

| Component | Function | Illustrative Port |
| --- | --- | --- |
| Redis master | Receives write commands and serves as the replication source | `6379` |
| Redis replica | Replicates data from the master; can be promoted | `6379` |
| Redis Sentinel | Monitors health, coordinates election/failover, provides the current master address | `26379` |

Sentinel **is not a Redis proxy for every GET/SET command**. With standard Sentinel configuration, the connection flow is:

1. Spring Data Redis/Lettuce connects to one of the known Sentinels.
2. The driver asks Sentinel which node currently serves the master named `mymaster`.
3. The driver opens data connections directly to the returned Redis node.
4. During failover, the client must detect the change and connect to the appropriate node.

Diagram of the two connection paths:

```text
Spring application
    |
    +-- Discovery/control --> Sentinel :26379
    |
    +-- Data operations ---> Redis master :6379
```

Practical consequences:

- Firewalls must allow **both connections to Sentinel and connections to all Redis data nodes that could become master**.
- The DNS/IP returned by Sentinel must be **reachable from the exact environment running Spring Boot**.
- Opening port `26379` alone is not enough; the application must reach the Redis data node ports.
- If the application configuration still uses only a fixed `host/port`, deploying Sentinel in infrastructure **will not automatically make the application aware of a new master**.

## 3. How Does Sentinel Monitor and Execute Failover?

Redis Sentinel monitors the master, replicas, and other Sentinels. It uses master health evaluation, required agreement, and leader election to execute failover.

Key concepts:

- **Subjectively Down (SDOWN):** an individual Sentinel judges a node unresponsive according to its configured threshold.
- **Objectively Down (ODOWN):** enough Sentinels agree the master is unavailable according to the configured quorum.
- **Quorum:** the minimum number of Sentinels that must confirm the master is down to reach ODOWN state.
- **Authorization/leader election:** beyond quorum, failover requires appropriate approval/majority among the known Sentinels for a leader to execute the transition.
- **Promotion:** selects an eligible replica as the new master; remaining replicas are reconfigured to follow the new master.

Example with three Sentinels and quorum two:

```text
Sentinel A ----\
Sentinel B -----+---- monitor mymaster, quorum = 2
Sentinel C ----/
```

A quorum of `2` **does not mean two Sentinels in every scenario guarantees failover will always occur**; you must consider the number of active Sentinels, majority authorization, and connectivity.

A typical deployment has **at least three Sentinels across independent failure domains**, alongside one master and replicas. Running three Sentinel processes on the same physical machine does not provide the same availability as three independent hosts.

### Sentinel and Redis Cluster Are Not the Same

| Criterion | Sentinel | Redis Cluster |
| --- | --- | --- |
| Primary goal | HA for a master–replicas group | Data partitioning across hash slots and HA per shard |
| Data distribution | No automatic sharding | Sharding included |
| Client config | Master name + Sentinel addresses | Cluster seed nodes |
| Normal writes | To the elected master | To the node owning the key's slot |
| Scaling capacity via sharding | Not built-in | Included |
| Spring connection configuration | `RedisSentinelConfiguration` | `RedisClusterConfiguration` |

A large Redis deployment may have multiple independent Sentinel groups, but should not be treated as a unified Redis Cluster simply because there are multiple masters.

## 4. Preparing the Topology Before Configuring Spring Boot

Illustrative environment:

| Role | Host | Port |
| --- | --- | --- |
| Initial Redis master | `10.10.0.11` | `6379` |
| Redis replica 1 | `10.10.0.12` | `6379` |
| Redis replica 2 | `10.10.0.13` | `6379` |
| Sentinel A | `10.10.0.21` | `26379` |
| Sentinel B | `10.10.0.22` | `26379` |
| Sentinel C | `10.10.0.23` | `26379` |

These addresses are **illustrative only**; substitute addresses provided by your infrastructure. Logical Redis master group name monitored by Sentinel:

```text
mymaster
```

`mymaster` is a **logical name configured by the Redis Sentinel administrator**, not a hostname. The name used by the client must match the name known to Sentinel exactly.

Before writing Java code, verify:

1. Redis master and replicas are properly configured for replication.
2. The Sentinel ensemble monitors the same `mymaster` name.
3. The Spring client has network connectivity to the Sentinels.
4. The Spring client has network connectivity to the current Redis master **and all replicas eligible for promotion**.
5. Which credentials are used to log into Redis data nodes versus Sentinel.
6. DNS/IPs announced by Sentinel can be resolved and connected to by the Spring client.
7. Redis server, Spring Data Redis, and Lettuce/Jedis use compatible versions for the intended auth/TLS options.

Only when these conditions are clear does `application.yml` become meaningful.

## 5. Illustrative Configuration for Redis Master, Replica, and Sentinel

This is an infrastructure configuration **to understand the mechanics**, not a complete production setup. Production requires ACLs, bind/listen addresses, firewalls, persistence, monitoring, and secret management.

A Redis master may use a standard configuration file, such as:

```conf
port 6379
appendonly yes
```

A replica must follow the initial master:

```conf
port 6379
replicaof 10.10.0.11 6379
appendonly yes
```

When authentication is enabled between Redis master and replicas, replicas need matching credentials to authenticate to the master, such as `masterauth` in traditional password mode or a properly authorized ACL user.

On **each Sentinel**, the configuration file may contain:

```conf
port 26379

sentinel monitor mymaster 10.10.0.11 6379 2
sentinel down-after-milliseconds mymaster 10000
sentinel failover-timeout mymaster 60000
sentinel parallel-syncs mymaster 1
```

The monitor directive has the structure:

```text
sentinel monitor <master-name> <master-ip> <master-port> <quorum>
```

Here:

- `mymaster` is the name the client must use.
- `10.10.0.11:6379` is the initial master address monitored by Sentinel.
- `2` is the quorum used to evaluate ODOWN.
- `down-after-milliseconds` is the threshold for evaluating unresponsiveness.
- `failover-timeout` governs several milestones and failover/retry pacing in Sentinel.
- `parallel-syncs` limits how many replicas synchronize with the new master concurrently during failover.

**Note:** Sentinel actively updates and rewrites its stateful config file when topology changes. Do not distribute config files and forcibly overwrite them periodically without understanding how Sentinel persists the new master. The Sentinel config file must reside in a location writable by the process when needed.

### Sentinel Authentication to Master Differs from App Authentication to Sentinel

If Redis data nodes require a password, Sentinel needs credentials to monitor and execute failover commands. Traditional configuration example:

```conf
sentinel auth-pass mymaster REDIS_DATA_NODE_PASSWORD
```

If using Redis ACLs, Sentinel may need `sentinel auth-user` and `sentinel auth-pass` with appropriate permissions on data nodes.

Those credentials are for **Sentinel logging into Redis master/replicas**. They do not grant the Spring Boot application permission to connect to **Sentinel port 26379**. If Sentinel itself also requires client authentication, Spring needs separate Sentinel credentials configured.

## 6. Configuring Spring Boot with application.yml

In modern Spring Boot versions using the `spring.data.redis` namespace, the basic configuration is:

```yaml
spring:
  data:
    redis:
      client-type: lettuce
      sentinel:
        master: mymaster
        nodes:
          - sentinel-a.internal:26379
          - sentinel-b.internal:26379
          - sentinel-c.internal:26379
      connect-timeout: 3s
      timeout: 3s
```

Key items:

| Property | Role |
| --- | --- |
| `spring.data.redis.sentinel.master` | Logical master name monitored by Sentinel |
| `spring.data.redis.sentinel.nodes` | Sentinel addresses for client discovery |
| `spring.data.redis.client-type` | Selects Lettuce/Jedis per dependencies and Boot version |
| `spring.data.redis.connect-timeout` | Connection establishment timeout per client/config |
| `spring.data.redis.timeout` | Wait limit for Redis operations per client/config |

With Spring Boot auto-configuration enabled and suitable dependencies, the application receives `RedisConnectionFactory`, `StringRedisTemplate`, and `RedisTemplate` to run Redis commands.

Usage example:

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SessionFlagService {

    private final StringRedisTemplate redis;

    public SessionFlagService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void markActive(String id) {
        redis.opsForValue().set("session:active:" + id, "1");
    }

    public boolean isActive(String id) {
        return "1".equals(
            redis.opsForValue().get("session:active:" + id)
        );
    }
}
```

This service **does not need** to manually invoke `SENTINEL get-master-addr-by-name`. When Spring Data Redis is configured with Sentinel, the driver handles master discovery and connection management.

### Spring Boot Versions and Prefixes

In older Spring Boot applications, you may encounter the `spring.redis.*` namespace instead of `spring.data.redis.*`. Use the **exact prefix for your running Boot version**, and do not mix both property styles expecting both to take effect.

Additionally, do not simultaneously supply standalone host/port, Redis URL, and Sentinel properties while assuming no precedence rules apply. Prefer configuration belonging to one clear connection model, and verify the actual values Spring Boot binds into the connection factory.

## 7. Using Environment Variables Instead of Storing Passwords in Git

In real applications, do not hard-code Redis passwords or Sentinel passwords in YAML committed to a repository.

Example:

```yaml
spring:
  data:
    redis:
      username: ${REDIS_DATA_USERNAME:default}
      password: ${REDIS_DATA_PASSWORD}
      sentinel:
        master: mymaster
        nodes:
          - sentinel-a.internal:26379
          - sentinel-b.internal:26379
          - sentinel-c.internal:26379
        username: ${REDIS_SENTINEL_USERNAME:default}
        password: ${REDIS_SENTINEL_PASSWORD}
```

Four distinct values to differentiate:

- **Redis data username**: user the application uses to log into Redis master/replicas.
- **Redis data password**: corresponding password for the data user.
- **Sentinel username**: user the application uses to log into Sentinel, if Sentinel requires it.
- **Sentinel password**: password for application → Sentinel connections.

Depending on the Spring Boot/Spring Data Redis version, Sentinel username/password properties should be verified in configuration metadata; some older versions have different support. If the framework does not expose a required property, configure `RedisSentinelConfiguration` in Java.

In `${REDIS_DATA_USERNAME:default}`, `default` is the Spring placeholder default value; `${REDIS_DATA_PASSWORD}` requires the actual environment/properties to provide a value.

**Security note:** do not put real passwords in documentation, logs, command history, or publicly saved command URLs. Use a secret manager, Kubernetes Secret, or your organization's configuration management system according to operational policy.

## 8. Pure Java Configuration Using RedisSentinelConfiguration

When fine-grained control is needed beyond auto-configuration, Spring Data Redis provides `RedisSentinelConfiguration`.

Example declaring `LettuceConnectionFactory`:

```java
package com.example.redis;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisPassword;
import org.springframework.data.redis.connection.RedisSentinelConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class RedisSentinelConnectionConfig {

    @Bean
    public LettuceConnectionFactory redisConnectionFactory() {

        RedisSentinelConfiguration sentinel =
            new RedisSentinelConfiguration()
                .master("mymaster")
                .sentinel("sentinel-a.internal", 26379)
                .sentinel("sentinel-b.internal", 26379)
                .sentinel("sentinel-c.internal", 26379);

        // If Redis data nodes use ACLs:
        sentinel.setUsername("app-redis-user");
        sentinel.setPassword(
            RedisPassword.of("DATA_NODE_PASSWORD_FROM_SECRET")
        );

        // If Sentinel ports also enable ACLs:
        sentinel.setSentinelUsername("app-sentinel-user");
        sentinel.setSentinelPassword(
            RedisPassword.of("SENTINEL_PASSWORD_FROM_SECRET")
        );

        LettuceClientConfiguration client =
            LettuceClientConfiguration.builder()
                .commandTimeout(Duration.ofSeconds(3))
                .shutdownTimeout(Duration.ofMillis(100))
                .build();

        return new LettuceConnectionFactory(sentinel, client);
    }
}
```

**Note:** the password strings above are placeholders solely to illustrate the API; in real deployments, load credentials via configuration/secret injection instead of committing them to source code.

If your system does not require authentication on one side, omit the corresponding credential lines; do not assume all environments have two sets of usernames/passwords.

The example selects **Lettuce** because it is the Redis client commonly used by Spring Boot. For specific versions, check the API/constructors and Sentinel ACL/TLS support in your Spring Data Redis and Lettuce versions.

### Why Not Call `new RedisStandaloneConfiguration()`?

`RedisStandaloneConfiguration` fits when a single fixed Redis address is known. With Sentinel, `RedisSentinelConfiguration` carries the master name and the list of Sentinel discovery endpoints.

Using a standalone factory and manually changing the host after failover defeats the main benefit of a Sentinel-aware driver and introduces an unnecessary custom topology-refresh mechanism.

## 9. Separating Configuration from Source Code with @ConfigurationProperties or @Value

The Java snippet above illustrates the APIs, but production code should externalize addresses and credentials into configuration.

Minimal example using `@Value`:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisPassword;
import org.springframework.data.redis.connection.RedisSentinelConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class SentinelWiringConfig {

    @Bean
    LettuceConnectionFactory redisConnectionFactory(
            @Value("${app.redis.master}") String master,
            @Value("${app.redis.sentinel-a}") String sentinelA,
            @Value("${app.redis.sentinel-b}") String sentinelB,
            @Value("${app.redis.password}") String password) {

        RedisSentinelConfiguration config =
            new RedisSentinelConfiguration()
                .master(master)
                .sentinel(sentinelA, 26379)
                .sentinel(sentinelB, 26379);

        config.setPassword(RedisPassword.of(password));
        return new LettuceConnectionFactory(config);
    }
}
```

Application configuration:

```yaml
app:
  redis:
    master: mymaster
    sentinel-a: sentinel-a.internal
    sentinel-b: sentinel-b.internal
    password: ${REDIS_DATA_PASSWORD}
```

This example omits Sentinel client authentication, assuming Sentinel allows application discovery on a test network. When Sentinel requires ACLs, add the corresponding credentials.

In systems with multiple Sentinel nodes, prefer list-based configuration and iterate to register endpoints rather than fixed `sentinel-a`, `sentinel-b` names as in this minimal example.

**Do not simultaneously define a custom `RedisConnectionFactory` and expect Spring Boot to automatically apply all `spring.data.redis.*` properties to that bean.** When creating the factory yourself, the application is responsible for configuring its properties.

## 10. Registering StringRedisTemplate When Creating a Custom Connection Factory

If the application declares a `RedisConnectionFactory` manually, Spring Boot may still create templates via auto-configuration when conditions match. To be explicit, you can also declare:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
public class RedisTemplateConfig {

    @Bean
    public StringRedisTemplate stringRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        return new StringRedisTemplate(connectionFactory);
    }
}
```

`StringRedisTemplate` uses serializers suitable for string keys/values. Redis Sentinel only affects how the connection factory locates Redis nodes; it **does not change** how Java serializes payloads, handles TTLs, or executes template-level operations.

Usage example:

```java
String key = "demo:sentinel:ping";
redis.opsForValue().set(key, "ok");

String value = redis.opsForValue().get(key);
```

When the master is up and the client has discovered the right address, the expected read value is `"ok"`.

If you want to store JSON objects, configure dedicated serializers on `RedisTemplate`. Do not let Sentinel connectivity mask serializer compatibility issues.

## 11. Lettuce and Jedis: Different Integration, Same Sentinel Contract

Spring Data Redis can connect via Lettuce or Jedis depending on dependencies and configuration.

| Topic | Lettuce | Jedis |
| --- | --- | --- |
| Client type | Client supporting Lettuce's modern connection and I/O model | Redis client with corresponding pool/connection configuration |
| Spring Data Redis integration | `LettuceConnectionFactory` | `JedisConnectionFactory` |
| Sentinel | Supported via appropriate Sentinel configuration | Supported via appropriate Sentinel configuration |
| Timeout, pool, SSL, reconnect | Uses Lettuce configuration | Uses Jedis configuration |
| Choice | Per app dependencies/capabilities | Per app dependencies/capabilities |

Jedis initialization snippet (illustrative, assuming Jedis dependency and supported Spring Data Redis version):

```java
import org.springframework.data.redis.connection.RedisSentinelConfiguration;
import org.springframework.data.redis.connection.jedis.JedisConnectionFactory;

RedisSentinelConfiguration sentinel =
    new RedisSentinelConfiguration()
        .master("mymaster")
        .sentinel("sentinel-a.internal", 26379)
        .sentinel("sentinel-b.internal", 26379);

JedisConnectionFactory factory =
    new JedisConnectionFactory(sentinel);
```

When using Spring Boot, do not select `client-type: jedis` if the required Jedis dependency is absent. Do not mix Lettuce and Jedis timeout/pool settings; each driver has its own API and behavior.

In this lesson, the primary examples use Lettuce to keep a single consistent configuration path.

## 12. Logical Master Name Is Not a Hostname

A very common configuration mistake:

```yaml
spring:
  data:
    redis:
      sentinel:
        master: sentinel-a.internal
```

The `master` field is **not the Sentinel hostname**. It must be the **Redis master group name** from:

```conf
sentinel monitor mymaster 10.10.0.11 6379 2
```

So the correct value must be:

```yaml
sentinel:
  master: mymaster
```

The `nodes` list is where Sentinel hosts/ports belong so the client can look up the master.

A Sentinel can monitor multiple master groups with different names. Using the wrong master name causes master discovery to fail, even when the Sentinel port is reachable.

## 13. Inspecting Topology via redis-cli

Before debugging Spring Boot errors, inspect Sentinel with Redis CLI:

```bash
redis-cli -h sentinel-a.internal -p 26379 \
  SENTINEL get-master-addr-by-name mymaster
```

Example output:

```text
1) "10.10.0.11"
2) "6379"
```

This is the Redis **data master** reported by Sentinel, not the Sentinel endpoint.

Commonly used commands:

```bash
redis-cli -h sentinel-a.internal -p 26379 \
  SENTINEL masters

redis-cli -h sentinel-a.internal -p 26379 \
  SENTINEL master mymaster

redis-cli -h sentinel-a.internal -p 26379 \
  SENTINEL replicas mymaster

redis-cli -h sentinel-a.internal -p 26379 \
  SENTINEL sentinels mymaster
```

On the Redis data node:

```bash
redis-cli -h 10.10.0.11 -p 6379 INFO replication
redis-cli -h 10.10.0.11 -p 6379 ROLE
```

In this example:

- Sentinel reports `10.10.0.11:6379` as the current master.
- `INFO replication`/`ROLE` on the data node shows the role the node itself sees.
- Different Sentinels may temporarily show divergent metadata during failures/failover, so check multiple nodes when diagnosing.

The lines above show readable shell syntax; in Windows PowerShell, enter the entire command on one line without `\` line continuations.

### If Passwords Are Enabled

Use secure secret input methods supported by your infrastructure; avoid putting passwords directly in shell history or process lists. Sentinel passwords and Redis data-node passwords may **differ**, so use the right credential for each port.

## 14. Verifying Network Access to the Address Announced by Sentinel

A typical scenario:

1. The application connects to Sentinel `sentinel-a.internal:26379`.
2. Sentinel returns `10.10.0.11:6379` as the master.
3. The Spring Boot container cannot reach `10.10.0.11:6379`.
4. The application reports connection timeout errors, even though Sentinel is healthy.

Diagram:

```text
Spring container ---- OK ----> Sentinel :26379
Spring container ---- FAIL --> Redis master :6379
```

When debugging, check **both paths**. Do not just ping Sentinel.

Questions to ask:

- Can the returned master address be resolved/routed from the Spring app's network?
- Is the Redis data node port open to the application?
- After failover, is the address of any promoted replica also reachable?
- Are Sentinel and replicas advertising proper LAN/internal addresses rather than `127.0.0.1`?
- Is there NAT, overlay networking, Docker port mapping, or a service mesh altering the address seen by clients?
- Are IPv4/IPv6 differences causing clients to receive an unreachable address?

**Sentinel discovers addresses; it does not proxy traffic**, so advertised addresses are a critical part of the design.

## 15. Localhost Mistakes in Docker/Kubernetes

In Docker, `127.0.0.1` inside the Spring container is the **Spring container itself**, not the Redis container. Thus:

```yaml
spring:
  data:
    redis:
      sentinel:
        nodes:
          - 127.0.0.1:26379
```

is only valid if Sentinel actually runs in the same network namespace as the Spring process.

Example replacing with internal service DNS:

```yaml
spring:
  data:
    redis:
      sentinel:
        master: mymaster
        nodes:
          - sentinel-0.redis.svc.cluster.local:26379
          - sentinel-1.redis.svc.cluster.local:26379
          - sentinel-2.redis.svc.cluster.local:26379
```

These names are templates; real Kubernetes/Docker topologies may use different names.

**More importantly:** even if `sentinel-0.redis.svc.cluster.local` is reachable, Sentinel might return a Redis master address on a different private network that is inaccessible from the application. Ensure Sentinel **advertises data node addresses that are genuinely reachable**.

In environments with NAT/port mapping, you may need proper announce configuration, replica/Sentinel address management, or a Redis service/operator supporting Sentinel across network boundaries. Do not assume host port mapping `6379:6379` automatically fixes all announced Redis addresses.

## 16. Authentication: Two Different Connection Paths

A deployment can have at least three credential scopes:

```text
Spring App -----------> Sentinel :26379
   uses Sentinel ACL/password

Spring App -----------> Redis master :6379
   uses Redis data ACL/password

Sentinel -------------> Redis master/replicas :6379
   uses monitoring/failover credential
```

**Do not confuse them**:

- `spring.data.redis.password`: credential the application uses for Redis data nodes.
- `spring.data.redis.sentinel.password`: credential the application uses to authenticate to Sentinel, if supported by your version.
- `sentinel auth-pass mymaster ...`: credential the Sentinel process uses to connect to Redis nodes; not the password Spring uses to access the Sentinel port.
- Redis data-node ACL users and Sentinel ACL users may differ.

### Example Configuration Separating Credentials

```yaml
spring:
  data:
    redis:
      username: ${REDIS_DATA_USER:default}
      password: ${REDIS_DATA_PASSWORD}
      sentinel:
        master: mymaster
        nodes:
          - sentinel-a.internal:26379
          - sentinel-b.internal:26379
          - sentinel-c.internal:26379
        username: ${REDIS_SENTINEL_USER:default}
        password: ${REDIS_SENTINEL_PASSWORD}
```

This example targets Spring Boot versions supporting these properties. Check the configuration metadata/driver in use during real deployment, especially in older Spring Boot applications.

If only a data password is set and Sentinel does not require client authentication, **do not** assign the same password as the Sentinel password.

## 17. TLS/SSL and Sentinel

In environments requiring encrypted connections, configure TLS for **both the data path** and **the Sentinel discovery path**, not just a single port.

```text
Spring -- TLS? --> Sentinel :26379
Spring -- TLS? --> Redis master :6379
Sentinel -- TLS? --> Redis data nodes
```

In Spring Boot versions supporting Redis SSL properties, you may see:

```yaml
spring:
  data:
    redis:
      ssl:
        enabled: true
```

However, **do not assume enabling one property automatically configures full TLS across all Sentinel/data paths, CAs, and hostname verification**. Details depend on Spring Boot, Spring Data Redis, Lettuce/Jedis versions, and the Redis/Sentinel infrastructure.

When TLS is required:

1. Verify both Redis data nodes and Sentinel ports support TLS.
2. Provide the appropriate truststore/CA to the JVM/client.
3. Ensure certificate hostnames match the addresses used by the client.
4. Test Sentinel discovery and node failover behavior over TLS.
5. Test connections to **replicas after promotion**, not just the initial master.
6. Do not disable certificate/hostname verification just to make the connection "work."

If a Redis provider requires specific combinations of Sentinel authentication and TLS, follow the official guidance for that provider and client library version.

## 18. Pools, Timeouts, and Reconnect During Failover

In a Sentinel setup, connections to the current master may drop while failover is in progress. The application must handle transient errors.

Parameters to consider:

- **Connect timeout:** wait limit for opening a connection to Sentinel or a Redis data node.
- **Command timeout:** wait limit for a Redis command.
- **Pool sizing** if using connection pooling: limits on active/idle connections and connection wait time.
- **Reconnect behavior:** Lettuce/Jedis behavior when an endpoint disconnects or changes roles.
- **Read preference:** whether to read from replicas.
- **Circuit breaker/backoff:** whether to keep hammering Redis or shed/slow requests during prolonged failures.

Java client configuration example:

```java
LettuceClientConfiguration client =
    LettuceClientConfiguration.builder()
        .commandTimeout(Duration.ofSeconds(3))
        .shutdownTimeout(Duration.ofMillis(100))
        .build();
```

`3s` is illustrative; tune according to latency, SLA, and real load. Too low a timeout causes false failures; too high stalls HTTP requests or workers during failover.

### Retries Are Not Always Safe

Suppose a client sends:

```redis
INCR billing:counter
```

Redis executed the command, but the response was lost during failover. If the client blindly retries, the counter can increment a second time.

Similarly, `LPUSH`, `INCRBY`, job enqueueing, or Lua scripts with side effects are not automatically safe under blind retries.

Distinguish:

| Operation | How Can It Be Retried If Response Is Lost? |
| --- | --- |
| `GET` | Usually safe to re-read per consistency policy |
| `SET key value` | Usually idempotent if same key/value and no time-dependent conditions |
| `INCR` | Unsafe under unconditional retry |
| `LPUSH` | Can insert duplicate elements |
| `SET key value NX` | Retry must account for whether the key was already created and who the owner/token is |
| Lua reserve/charge | Requires an idempotency key and a way to verify whether the effect was already applied |

Sentinel helps connect to the new master; it **does not define idempotency for Redis commands**.

## 19. Why Failover Does Not Guarantee Zero Downtime

The failover process takes time for Sentinel to:

1. Detect the master is unresponsive.
2. Reach quorum/authorization.
3. Select an eligible replica.
4. Promote the replica to master.
5. Update topology so clients locate the new master.

During this window:

- Existing connections may error or time out.
- Some requests may receive `READONLY` if the client still holds the old endpoint.
- Clients may need to reconnect/resubscribe.
- Network splits can create states that are difficult to synchronize.
- Previously ACKed writes may not have reached the elected replica due to asynchronous replication.

Therefore:

> Sentinel provides **high availability and automated role transition**, which does not mean zero data loss, zero failed requests, or zero interruption in all cases.

The application must decide what to do when Redis is unavailable:

- Fail the request or return a retry-later response?
- Fall back to a database?
- Can cache reads bypass Redis and read the authoritative source?
- Does a critical operation need persistence in another system before returning success?
- Can the command be retried safely or must it check idempotency state?

## 20. Asynchronous Replication and Risk of Write Loss

Standard Redis replication is asynchronous. A master can accept a write and reply to the client before the replica elected during failover has received that write.

Example:

```text
T0: App SET order:42 = "PAID" to master A
T1: Master A returns OK
T2: Master A fails before replica B receives the write
T3: Sentinel promotes replica B
T4: New Redis does not have order:42 = "PAID"
```

This does not happen every time, but it **is not eliminated** simply by using Sentinel.

Redis offers mechanisms like `WAIT` to await a level of replication confirmation in specific scenarios, yet that **does not create an absolute durable transaction** or eliminate all failover/persistence risks. Evaluate separately when Redis data is an authoritative business store.

If Redis is only caching PostgreSQL, the application can rebuild the cache on a miss. If Redis holds the sole state of a payment, durability requirements must be designed much more carefully.

## 21. Replica Reads: Optimizing Reads at the Risk of Stale Data

With Lettuce and Spring Data Redis, certain configurations allow reading from replicas using the corresponding client mechanism.

Conceptual example:

```java
import io.lettuce.core.ReadFrom;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;

LettuceClientConfiguration client =
    LettuceClientConfiguration.builder()
        .readFrom(ReadFrom.REPLICA_PREFERRED)
        .build();
```

Use this only when your driver version and Sentinel/replica connection setup support it; verify actual application behavior.

When reading from replicas:

- Data may **lag** behind the master due to asynchronous replication.
- Write commands still require the master.
- A request that writes and immediately reads a replica may see stale values.
- During failover, replica topology and read preferences can shift.

For workflows requiring **read-your-writes** or financial decisions, do not assume replica reads are sufficient. Separate cache/display read paths from authoritative state checks.

## 22. Sentinel with Transactions, Lua, and Pipelines

High-level Spring Data Redis APIs continue to work when connecting via Sentinel:

- `StringRedisTemplate`/`RedisTemplate`.
- `opsForValue`, `opsForHash`, `opsForSet`, `opsForZSet`.
- Lua scripts via `RedisScript`.
- Pipelining.
- Pub/Sub listeners.

However, during failover, any workflow can suffer a dropped connection.

**Pipeline:** not a transaction; failover mid-stream can leave the client unsure which commands executed before the connection broke.

**Lua:** when running on a master, scripts execute per Redis Lua scripting semantics, yet client timeouts can still happen after the script has executed. Retries require idempotency.

**MULTI/EXEC:** transactions are bound to a connection and Redis node; losing the connection or switching masters can leave the outcome ambiguous from the client's perspective.

**Pub/Sub:** subscriptions may need recovery; messages published while a listener is offline are not replayed by Redis.

Sentinel does not upgrade any API's semantics to "exactly once." Analyze failure scenarios individually for critical operations.

## 23. Observing Redis and Spring When Using Sentinel

Do not only watch the initial Redis master's health. Monitor three layers:

| Layer | Important Signals |
| --- | --- |
| Sentinel | Number of online Sentinels, quorum, leader/failover events, current master address |
| Redis nodes | Role, replication offset/lag, master link status, persistence, memory, evictions |
| Spring client | Connection failures, command timeouts, reconnects, errors like `READONLY`, request latency |

Useful Redis/Sentinel commands:

```bash
redis-cli -h sentinel-a.internal -p 26379 SENTINEL master mymaster
redis-cli -h sentinel-b.internal -p 26379 SENTINEL master mymaster
redis-cli -h redis-node.internal -p 6379 INFO replication
redis-cli -h redis-node.internal -p 6379 INFO stats
```

Monitor Lettuce/Jedis and Spring Data Redis logs at an appropriate level during failover. Avoid overly broad debug logging that leaks connection details or credentials in production.

Suggested metrics:

```text
redis_connection_errors_total
redis_command_timeouts_total
redis_command_latency_seconds
redis_failover_events_total
redis_reconnects_total
redis_replication_lag_seconds
redis_role_changes_total
redis_fallback_reads_total
```

Metric names are design suggestions only; not all names are provided out of the box by Spring Boot Actuator. Add instrumentation appropriate for your client and monitoring stack.

### Liveness and Readiness Are Different

A service may still be **live** even when Redis is temporarily unreachable. **Readiness** determines whether it should continue accepting traffic that depends on Redis.

Do not restart all pods repeatedly just because Redis is undergoing a brief failover; mass restarts can worsen the outage. Readiness/fallback policies should match business needs and application resilience.

## 24. Testing Sentinel Connectivity Before Testing Failover

In a test environment:

1. Confirm there is one master and at least one replica.
2. Confirm all Sentinels agree on the name `mymaster`.
3. Run the Spring app with Sentinel configuration.
4. Write a test key using `StringRedisTemplate`.
5. Read the key back to confirm the data path works.
6. Confirm Sentinel reports the expected current master address.
7. Ensure the test key is not in a production namespace.

Java smoke test example:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;

@SpringBootTest
class SentinelConnectionSmokeTest {

    @Autowired
    StringRedisTemplate redis;

    @Test
    void canReadAndWriteUsingSentinelDiscoveredMaster() {
        String key = "test:sentinel:smoke";

        redis.opsForValue().set(key, "connected");

        assertThat(redis.opsForValue().get(key))
            .isEqualTo("connected");

        redis.delete(key);
    }
}
```

This is an illustrative smoke test. It requires a running test Redis/Sentinel environment and Spring Boot configured with valid network/credentials. Passing proves the read/write path works at that moment; it **does not prove failover works**.

Do not run tests that delete shared keys in production.

## 25. Testing Failover in an Isolated Environment

A thorough integration test should use a real topology with a Redis master, replicas, and multiple Sentinels. Testcontainers can help run Redis/Sentinel containers, but building a multi-process topology requires configuring networking, persistence, and advertised addresses; do not assume running a single default Redis `GenericContainer` provides Sentinel.

### Scenario

```text
1. Start Redis master + replicas + 3 Sentinels
2. Spring app connects via Sentinel master name
3. SET smoke:sentinel = "before"
4. Verify GET returns "before"
5. Trigger a controlled failover
6. Observe the current master switch to a replica
7. Wait for client to rediscover the new master
8. SET smoke:sentinel:after = "after"
9. GET confirms new data commands work
10. Record transient errors during failover
```

On Sentinel **in a test environment only**, you can run:

```bash
redis-cli -h sentinel-a.internal -p 26379 \
  SENTINEL FAILOVER mymaster
```

This command asks Sentinel to perform a controlled failover if conditions allow. It is not an operation to run casually against production Redis. To simulate a real crash, stop the master in a test environment and observe promotion.

### What Must Be Verified?

- The client receives the new master address.
- Post-failover writes go to the new master.
- Transient errors such as timeouts/connection failures occur within the failover window.
- Critical commands have appropriate retry/idempotency policies.
- Replica reads are not confused with master writes.
- Endpoints announced by Sentinel are reachable from the application.
- No secrets are leaked in logs/metrics.
- The system does not execute side effects twice when a write response is lost.

Tests must not be judged solely by "after failover the app is still running"; inspect the exact Redis operations and business semantics.

## 26. Designing Retries Around Failover

Suppose a service uses Redis as a database cache:

```text
GET product:42
     |
     +-- Redis reachable -> read cache
     |
     +-- Redis unavailable -> read authoritative database
```

This fallback can work well if Redis is strictly a cache and the business permits bypassing it.

Conversely, if Redis holds a distributed lock or counter preventing overselling, you cannot arbitrarily "skip Redis" and treat the check as passed. When Redis is unavailable, fail closed or defer to another authoritative coordination mechanism.

Decision guide:

| Redis Purpose | During Sentinel Failover |
| --- | --- |
| Read cache | Can fall back to database, per policy |
| Session | Define login/session availability policy |
| Rate limit | Choose fail-open or fail-closed based on risk |
| Distributed lock | Never assume lock ownership when Redis state is unknown |
| Idempotency key | Keep the same request ID across retries |
| Financial counter | Do not unconditionally retry `INCR` |
| Queue/Streams | Re-check ACK/write outcome after reconnect |
| Pub/Sub | Accept gaps or implement reconciliation |

Handling Redis unavailability must be driven by data requirements, not simply adding a `@Retryable` annotation.

## 27. Common Configuration Mistakes

### Wrong Master Name

Symptoms: Sentinel is reachable, but the client cannot find the master. Check `SENTINEL get-master-addr-by-name mymaster`. The value must match `sentinel monitor` in infrastructure.

### Configuring Only One Sentinel Address

If only one Sentinel endpoint is configured and it becomes unavailable, the client cannot discover the current master even if other Sentinels are up. Configure multiple Sentinels across different failure domains.

### Using a Sentinel Hostname as a Fixed Redis Host

```yaml
spring:
  data:
    redis:
      host: sentinel-a.internal
      port: 26379
```

This is not valid Sentinel configuration. Port `26379` serves Sentinel commands, not standard Redis data operations like `GET/SET`.

### Opening Only Port 26379

The application discovers the master, but connecting to `6379` fails. Open network paths to all Redis data nodes that could be promoted.

### Using Localhost Inside Containers

`127.0.0.1` can point to the Spring container itself. Use proper DNS/service networking and verify the address returned by Sentinel.

### Swapping Sentinel and Redis Data Passwords

Symptoms: `NOAUTH`, `WRONGPASS`, authentication failures. Verify credentials per path: app→Sentinel, app→Redis data, Sentinel→Redis data.

### Incorrect Redis ACL Permissions

The app may discover the master yet lack permission for `GET/SET`; or Sentinel may authenticate yet lack permissions to monitor/fail over. Do not fix this by opening all ACLs unnecessarily; grant role-appropriate permissions.

### Enabling TLS on Only One Side

Sentinel and Redis data nodes may have distinct TLS settings. Successfully connecting to Sentinel does not prove the data path is properly encrypted. Verify both data and discovery paths.

### Client Continues Writing to the Old Node

During failover, `READONLY` or timeouts can occur. Check driver reconnect, topology state, stale connections, and retry handling.

### Reading Stale Data from Replicas

Replica reads can lag behind the master. Do not use replica reads for decisions requiring the latest writes unless adequate guarantees exist.

### Running All Sentinels on One Server

Three processes on a single machine do not eliminate that machine as a single point of failure. Separate failure domains.

### Confusing Redis Sentinel with Redis Cluster

Using the wrong connection configuration causes the client to handle topology with the wrong protocol. Choose `RedisSentinelConfiguration` for a Sentinel master name, not Cluster configuration.

## 28. Symptom-Based Troubleshooting Guide

| Symptom | Likely Areas to Check | First Diagnostic Step |
| --- | --- | --- |
| Cannot connect to Sentinel | DNS, firewall, port, TLS | Test TCP connectivity to each `:26379` |
| Connects to Sentinel, cannot find master | Wrong master name, Sentinel not monitoring | `SENTINEL get-master-addr-by-name` |
| Master discovered, Redis times out | Returned address/port unreachable | Test path to data node `:6379` |
| `NOAUTH`/`WRONGPASS` | Wrong user/password on one of the paths | Separate Sentinel auth and Redis auth |
| `READONLY` after failover | Client still hitting replica/old node | Check role/master discovery, reconnect |
| Occasional lost commands on failover | Disconnects, replica lag, retries | Inspect timestamps, error logs, idempotency |
| GET returns stale data | Replica reads or cache TTL | Check `ReadFrom` and source of truth |
| Failover does not happen | Quorum/majority, no eligible replica | Inspect `SENTINEL master` and Sentinel logs |
| App runs, writes fail after failover | New Redis unreachable/ACL mismatch | Check address, ACLs, and role |
| One Sentinel returns a different master | Topology converging or config drift | Query multiple Sentinels and failover state |

Do not change multiple variables at once (password, DNS, TLS, master name) and lose track of what caused the error. Verify layer by layer: network/discovery → Redis data connection → Spring factory → business operation.

## 29. Production Deployment Checklist

**Redis Infrastructure**

- Master and replicas sized to HA requirements.
- At least three Sentinels across appropriate failure domains for common deployments.
- Quorum, timeouts, replica priority, and failover policy actively managed.
- Master/replica replication and persistence configured per requirements.
- Redis data nodes have addresses reachable from all app nodes.
- Sentinel announce and data-node advertise settings match network topology.
- Monitoring in place for role changes, replica lag, failovers, and persistence health.

**Spring Data Redis**

- `sentinel.master` has the exact logical name.
- `sentinel.nodes` lists multiple discovery endpoints.
- Property prefix matches the Spring Boot version.
- Lettuce/Jedis client explicitly chosen with the right dependencies.
- Auth for Redis data and Sentinel properly separated.
- TLS/CA/hostname validation matches topology.
- Timeouts, pools, and reconnect tested under real load.
- No conflicting hardcoded standalone host as the primary connection path.
- Template serializers not altered unintentionally.

**Application and Business Logic**

- Idempotent retries for writes that could execute prior to a timeout.
- Fallbacks when Redis is strictly a cache; avoid unsafe fallbacks when Redis is an authoritative coordinator.
- No assumptions of zero downtime or zero data loss.
- Controlled failover tested in a dedicated environment.
- Logs, metrics, and alerts covering Sentinel + Redis + app.
- Operational runbook for simultaneous Sentinel or multi-node Redis outages.

## 30. Practice Exercises

### Exercise A — Configuring Spring Boot Auto-Configuration

Given three Sentinels:

```text
sentinel-1.internal:26379
sentinel-2.internal:26379
sentinel-3.internal:26379
```

Master name `catalogmaster`. Write `application.yml` and a service using `StringRedisTemplate` to write/read `catalog:test`. Explain why a fixed master IP does not need to be known.

### Exercise B — Debugging a Master Name Mismatch

Sentinel uses:

```conf
sentinel monitor inventorymaster 10.10.0.11 6379 2
```

Spring uses:

```yaml
sentinel:
  master: mymaster
```

Explain why master discovery fails and how to fix it. Verify with `SENTINEL get-master-addr-by-name inventorymaster`.

### Exercise C — Checking Announced Addresses

Spring runs in Kubernetes and reaches Sentinel, but Sentinel returns a private IP only reachable from another network. State the cause, distinguish discovery endpoints from data endpoints, and propose an appropriate network/announce change.

### Exercise D — Testing Failover

In a test environment with one master, two replicas, and three Sentinels:

1. Write a key using `StringRedisTemplate`.
2. Trigger a test failover.
3. Observe Sentinel's master address change.
4. Write and read again through the Spring connection factory.
5. Record any timeouts/`READONLY` errors that appear.
6. Explain why a smoke test does not prove all pre-failover writes were preserved.

### Exercise E — Retrying an INCR Command

An application sends `INCR billing:count`; Redis may have executed it, but the response was lost. Design a business-level approach to prevent double-counting using an idempotency key or stored request state. Explain why blind retries are insufficient.

### Exercise F — Authentication and TLS

An application requires different Redis data user/password and Sentinel user/password. Diagram the two connection paths and distinguish credentials for app→Sentinel, app→Redis, and Sentinel→Redis. Verify TLS configuration for each path rather than checking only a single SSL flag.

## 31. Frequently Asked Questions

**Is Sentinel a single Redis proxy address?**

No. Sentinel helps clients discover the current master; clients generally connect directly to Redis data nodes to execute commands.

**Does Spring Boot need to manually call SENTINEL get-master-addr-by-name on every request?**

No. Configure Sentinel with Lettuce/Jedis via Spring Data Redis so the driver manages discovery and reconnection.

**Is the master name in YAML the hostname of the Redis master?**

No. It is the logical name configured in `sentinel monitor`, such as `mymaster`.

**Why does connecting to Sentinel succeed while GET/SET still fails?**

The client must also reach the Redis data node reported by Sentinel. Check firewalls, DNS/IPs, TLS, and credentials on the Redis `:6379` path.

**Should both a Redis host and Sentinel nodes be configured?**

Choose one clear connection model. With Sentinel, the master name and Sentinel nodes provide discovery. Do not rely on mixing standalone host/port settings to patch failover issues.

**Can StringRedisTemplate be used normally with Sentinel?**

Yes. If `RedisConnectionFactory` is properly configured for Sentinel, the template uses those connections like any other Redis operation.

**Does Sentinel guarantee zero write loss during failover?**

No. Standard Redis replication is asynchronous; writes ACKed by the master can still fail to reach the promoted replica.

**Why do timeouts or READONLY errors happen during failover?**

Clients may hold connections to the old node, topology takes time to converge, and the new Redis node needs promotion. Handle transient errors and safe retries.

**Should replica reads always be enabled for performance?**

Not by default. Replicas can return stale data. Only enable them when the use case tolerates eventual consistency and the client is configured accordingly.

**Can Redis Sentinel and Redis Cluster share the same connection configuration?**

No. They are different topology models; Spring Data Redis has separate configurations for Sentinel and Cluster.

**Do we need three Sentinels?**

Deploying three Sentinels across independent failure domains is a common HA choice. Actual count and quorum must fit fault-tolerance, network, and operational design; a single Sentinel is a single point of failure for discovery/failover.

**Does enabling TLS on Redis data nodes mean Sentinel automatically uses TLS?**

Do not assume so. Verify Redis/Sentinel server configuration and Spring client TLS support on each path.

## 32. Summary

Configuring Redis Sentinel in Spring Data Redis requires understanding **discovery**, **Redis data connections**, and **failover**:

1. **Redis Sentinel is a control plane** monitoring master/replicas and providing the current master address; it does not proxy every Redis command.
2. **Spring Boot uses `spring.data.redis.sentinel.master` and `sentinel.nodes`** according to your Boot version to configure discovery.
3. **Spring Data Redis provides `RedisSentinelConfiguration`**, paired with `LettuceConnectionFactory` or `JedisConnectionFactory` for pure Java configuration.
4. **Master name is a logical identifier**, not a hostname; the Sentinel list holds discovery endpoints, while data operations connect to Redis nodes.
5. **Authentication and TLS must separate app→Sentinel, app→Redis, and Sentinel→Redis paths**.
6. **Every node eligible to become master must be reachable** from the application; Docker/Kubernetes/NAT/announce addresses are frequent sources of errors.
7. **Failover introduces a transient error window**, and asynchronous replication can lose some writes; never assume zero downtime or zero data loss.
8. **Retries must consider idempotency**, especially for `INCR`, queue operations, Lua scripts, and transactions.
9. **Test failover on a real topology in an isolated environment**, observing roles, reconnects, and post-switch read/write behavior.

When these principles are applied, Spring Boot can continue operating against a Redis master changing via Sentinel without hard-coding master addresses, while keeping a clear design for handling the unavoidable failure windows of distributed systems.

## Official References

- [Spring Data Redis – Redis Sentinel Support](https://docs.spring.io/spring-data/redis/reference/redis/connection-modes.html)
- [Spring Data Redis – RedisSentinelConfiguration API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/connection/RedisSentinelConfiguration.html)
- [Spring Data Redis – LettuceConnectionFactory API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/connection/lettuce/LettuceConnectionFactory.html)
- [Spring Data Redis – RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Boot – Redis Auto Configuration](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.redis)
- [Redis – High Availability with Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/)
- [Redis – Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [Redis – WAIT](https://redis.io/docs/latest/commands/wait/)
- [Redis – Sentinel Commands](https://redis.io/docs/latest/commands/sentinel/)
