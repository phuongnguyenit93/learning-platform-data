# Configuring Server Host, Port, Logical Database, and Connection URL

When a Spring Boot application uses Spring Data Redis, every read/write operation must go to **the right Redis server**, through **the right port**, and in the case of standalone Redis, must also use **the right logical database**. These parameters can be declared separately with `host`, `port`, `database` or partially combined into `url`. Choosing a wrong parameter can produce very different symptoms: failing to connect, connecting successfully but not finding keys, or the application accidentally writing data into a different environment.

This lesson focuses on connection configuration in **Spring Boot 3.3.x and Spring Data Redis 3.3.x**, with **Lettuce** as the default driver when using the starter. The goal is to understand which values Spring Boot reads, which values are actually passed to `RedisConnectionFactory`, and how to verify the effective configuration. The YAML examples are for Boot 3.x; if using Boot 2.x or 4.x, you must cross-check the corresponding prefixes and APIs.

## 1. Four Key Components of a Redis Connection

Consider a simple read command:

~~~text
Spring Service
    │
    ▼
StringRedisTemplate
    │
    ▼
RedisConnectionFactory
    │
    ├── Host: redis.internal.example
    ├── Port: 6379
    ├── Logical DB: 2
    └── Authentication/TLS if configured
    │
    ▼
Redis server → database 2 → key "app:product:42"
~~~

| Component | Role | Example | Common errors when misconfigured |
|---|---|---|---|
| **Host** | IP address or DNS name of Redis | `localhost`, `redis`, `redis.example.internal` | Unresolved DNS, connection refused, timeout |
| **Port** | TCP port Redis is listening on or the port published to clients | `6379`, `6380` | Connecting to the wrong service, connection refused, or timeout |
| **Logical database** | Selects a keyspace by index within a standalone Redis | `0`, `2` | Command succeeds but keys written in another DB are not found |
| **URL** | Represents the connection endpoint and may include credentials | `redis://redis.example:6379` | URL overrides individual fields; may point to the wrong endpoint |

**Host and port point to the Redis server; the logical database selects a key collection inside that server.** A URI of the form `redis://...` is a Redis URI, not an HTTP address. Connecting to a Redis port requires the Redis protocol and a driver such as Lettuce/Jedis; a web browser cannot send an HTTP GET to query Redis keys.

Default connection examples commonly use port `6379`, but this is not a mandatory port. In real infrastructure, the port is determined by the Redis server, service provider, or network forwarding configuration.

## 2. Starting with Spring Boot Configuration

### 2.1. Minimal Dependency

For a Gradle project using Spring Boot's plugin/dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

The starter provides Spring Data Redis and Lettuce in a typical configuration. When the classpath, configuration, and bean conditions match, Spring Boot automatically creates a `RedisConnectionFactory` along with the default Redis templates. Therefore, there is no need to manually create a factory just to replace `localhost` with another Redis hostname.

### 2.2. Explicitly Declaring host, port, and database

File `src/main/resources/application.yml`:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      database: 0
      connect-timeout: 2s
      timeout: 3s
~~~

Key properties:

| Spring Boot 3.x Property | Common Default Value | Meaning |
|---|---|---|
| `spring.data.redis.host` | `localhost` | Redis host in a standalone connection |
| `spring.data.redis.port` | `6379` | Redis port in a standalone connection |
| `spring.data.redis.database` | `0` | Selected logical database index |
| `spring.data.redis.url` | Not set | Connection URL; takes precedence over individual endpoint fields |
| `spring.data.redis.username` | Not set | Redis ACL username when required |
| `spring.data.redis.password` | Not set | Redis password when required |
| `spring.data.redis.connect-timeout` | Depends on library/version default | Timeout when establishing a connection |
| `spring.data.redis.timeout` | Depends on library/version default | Read/operation timeout as supported by the driver and factory |
| `spring.data.redis.ssl.enabled` | `false` | Enables TLS for the connection when required by the endpoint |

The timeout numbers in the example are **illustrative choices**, not a standard configuration for every system. A short timeout can cause false failures on a slow network; a timeout that is too long can keep application requests blocked for too long.

With the configuration above, Spring Data Redis uses a `RedisConnectionFactory` to connect to `localhost:6379` and select database `0`. Even when declared in YAML, **the Redis server must exist and be reachable from the application process**; the starter does not automatically start a Redis server on the network.

### 2.3. Access Example Using `StringRedisTemplate`

~~~java
import java.time.Duration;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisNoteService {

    private final StringRedisTemplate redis;

    public RedisNoteService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String noteId, String text) {
        redis.opsForValue().set(
                "note:" + noteId,
                text,
                Duration.ofMinutes(15)
        );
    }

    public String load(String noteId) {
        return redis.opsForValue().get("note:" + noteId);
    }
}
~~~

There is no `host` or `port` in the service. The template receives a Spring-managed factory, and the factory uses the endpoint from the effective configuration. This is why connection parameters should be kept outside business logic.

Data saved by the code above resides in the logical database selected by the connection factory. If you run two instances of the application with `database: 0` and `database: 2`, the same `GET note:1` command can return two different results even though both access the same Redis server.

## 3. `host` and `port`: Address Seen from Where the Application Runs

### 3.1. `localhost` Always Refers to the Client Process's Machine/Container

This is a common cause of errors when moving from a development environment to Docker or Kubernetes.

Suppose Redis runs on a developer machine and the Spring Boot application also runs directly on that machine:

~~~yaml
spring:
  data:
    redis:
      host: 127.0.0.1
      port: 6379
~~~

This configuration makes sense because `127.0.0.1` points to the very machine running the application.

However, if Spring Boot runs inside a **container**, `localhost` points to the application container itself, **not** to the host machine or an adjacent Redis container. When two services are in the same Docker Compose network, use the service name as DNS:

~~~yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6380:6379"

  app:
    build: .
    environment:
      SPRING_DATA_REDIS_HOST: redis
      SPRING_DATA_REDIS_PORT: "6379"
    depends_on:
      - redis
~~~

Assuming this file is used in a project with a valid Dockerfile and both services belong to the same Compose network:

- **Spring Boot running in service `app`:** connects to `redis:6379`.
- **Spring Boot running directly on the host machine:** can use `localhost:6380`, because Compose published host port `6380` to container port `6379` in the Redis container.
- **Another machine on the network:** can only access it if the host, firewall, publish configuration, and network policy allow it; it is not automatically reachable via that machine's `localhost`.

`depends_on` in a basic configuration determines container startup order; it does not guarantee Redis is ready to accept commands at the exact moment Spring Boot connects. If you need to wait for the service to be ready, use a health check and an appropriate retry/readiness strategy.

### 3.2. Distinguishing Server Port, Container Port, and Host Port

~~~text
Host machine                        Docker network
┌─────────────────────┐            ┌───────────────────────────┐
│ Spring Boot (host)  │            │ Redis container           │
│ localhost:6380      │ ─────────► │ redis:6379                │
└─────────────────────┘  mapping   └───────────────────────────┘
                                        ▲
                                        │ TCP redis:6379
                                  ┌─────┴───────────┐
                                  │ Spring Boot app │
                                  │ container       │
                                  └─────────────────┘
~~~

In the example `6380:6379`, **the left side is the host port**, **the right side is the container port**. Spring Boot in another container typically uses the right-hand port, not the port published on the host.

The same applies to Kubernetes: an application pod typically connects using the Service DNS and Service port, not `localhost`, unless Redis actually runs in the same network namespace and the design requires it.

### 3.3. Hostname and Networking Are Not Security Configuration

Choosing the right host/port is not enough to establish a secure connection. A Redis server can restrict listening addresses, protected mode, ACLs, firewalls, or private networks. Do not expose Redis to the Internet just to fix an application connection error; instead, verify the network path, DNS, routes, service discovery, and TLS/authentication of the deployment environment.

## 4. Logical Database: How to Choose the Right `database`

### 4.1. What Is a Logical Database?

Standalone Redis can provide multiple logical databases numbered with non-negative integers. In a typical Redis OSS configuration, the server has **16 logical databases** by default, from `0` to `15`, and clients select `0` by default. The actual count depends on the server/provider configuration; not every Redis deployment allows using all these indices.

~~~text
Same Redis server localhost:6379
┌────────────────────────────────────────┐
│ db0:  key "profile:1"  → "Alice"       │
│ db1:  key "profile:1"  → "Bob"         │
│ db2:  key "profile:1"  → "Carol"       │
│ ...                                    │
└────────────────────────────────────────┘
~~~

Keys with the same name can exist in different logical databases without overwriting each other. A client that selects `db2` and reads `profile:1` will not see the value in `db0`. Therefore, **a successful connection where `GET` returns null** can be a sign that the client is selecting the wrong logical database.

Redis uses the `SELECT` command to switch the current database on a connection in modes that support logical databases:

~~~bash
redis-cli -h localhost -p 6379 -n 2
~~~

After entering the Redis CLI:

~~~text
127.0.0.1:6379[2]> SET lesson:greeting "Hello"
OK
127.0.0.1:6379[2]> GET lesson:greeting
"Hello"
127.0.0.1:6379[2]> SELECT 0
OK
127.0.0.1:6379> GET lesson:greeting
(nil)
~~~

The example above assumes the server allows DB 2 and does not require authentication. `(nil)` in DB 0 does not mean the initial `SET` command failed; the key was written in DB 2.

Use the corresponding Spring Boot configuration:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      database: 2
~~~

### 4.2. Logical Databases Are Not a Resource Isolation Mechanism

Databases within the same Redis server still share the process, CPU/RAM resources, `maxmemory` limits, eviction policies, persistence schedules, and most operational conditions. They are **not** independent physical Redis instances and do not replace authorization or tenant isolation measures.

Some practical consequences:

- DB 1 does not have “dedicated RAM” separated from DB 0. A large set of keys can put resource pressure on the entire server.
- `FLUSHDB` affects the current database, while `FLUSHALL` affects every database on the instance; these commands are dangerous if run against the wrong environment.
- TTLs, evictions, and disk/server errors still involve shared resources.
- Redis ACLs should not be assumed to isolate permissions by DB number; if secure isolation is needed, design separate instances/deployments and corresponding permission rules.
- When scanning or inspecting keys, verify that the client is in the database you intend to observe.

In real applications, it is usually better to use **intentional key prefixes** such as `dev:catalog:42`, `cache:product:42` and clearly identify instances/environments. Prefixes help organize keys, though they are **not a security boundary** either.

### 4.3. Redis Cluster Does Not Support Multiple Logical Databases

A fundamental limitation: **Redis Cluster only supports database 0**. The `SELECT` command to choose another DB is not available in Redis Cluster. Therefore, you cannot rely on `spring.data.redis.database: 3` as a data partitioning method when migrating an application from standalone to Cluster.

~~~yaml
# Illustrates a Redis Cluster connection; do not set database other than 0
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-node-1:6379
          - redis-node-2:6379
          - redis-node-3:6379
      database: 0
~~~

The endpoints are examples; use them only when the corresponding Redis cluster exists. With Redis Cluster, data separation typically relies on key naming conventions, Redis ACLs, and separate clusters/instances when true isolation is required.

**Redis Sentinel is not synonymous with Redis Cluster.** Sentinel monitors and fails over primary/replica nodes; standalone Redis managed by Sentinel still has logical database semantics according to that Redis server's configuration. Do not infer support for other DB numbers solely from the phrase “Redis cluster” in infrastructure docs; you need to know whether the service actually uses Redis Cluster, Sentinel, or a managed service with its own limitations.

### 4.4. Do Not Arbitrarily Change DB on Framework-Managed Connections

Spring Data Redis configures the database at `RedisConnectionFactory`. Avoid borrowing a connection from a template/pool, manually sending `SELECT 2` for one request, and forgetting to restore the original state. Connections can be reused, so mutating connection state can cause subsequent requests to read/write the wrong DB.

If an application genuinely must access multiple logical databases, define separate connection factories/templates per DB and inject them by name/`@Qualifier`. If multiple logical databases are only used to simulate environments such as dev/test/prod, isolating with **separate Redis instances/deployments** is usually clearer and safer.

## 5. Configuring `url`: When to Use It and What It Overrides

### 5.1. Common Redis URI Formats

A typical standalone Redis URI:

~~~text
redis://<host>:<port>
redis://:<password>@<host>:<port>
redis://<username>:<password>@<host>:<port>
rediss://<host>:<port>
~~~

Example without sensitive information:

~~~yaml
spring:
  data:
    redis:
      url: "redis://redis.example.internal:6379"
      database: 0
~~~

A URI can contain a username and password per the userinfo convention. An example like `redis://app-user:secret@redis.example:6379` only illustrates **syntax**; do not put real passwords in Git, logs, URLs shown on dashboards, or documentation.

Some URIs in the Redis ecosystem use a `/2` path to denote a logical database. **Do not assume every driver/framework interprets that path segment identically.** With Spring Boot 3.3, the explicit approach is to configure the database via `spring.data.redis.database` separately and verify by reading/writing in the target DB.

### 5.2. Precedence Rules in Spring Boot 3.x

When `spring.data.redis.url` is declared, it is used as the endpoint source and **overrides the individual `host`, `port`, `username`, and `password` fields** for a standalone connection under Boot's Redis auto-configuration.

Example:

~~~yaml
spring:
  data:
    redis:
      host: redis-a.internal
      port: 6379
      url: "redis://redis-b.internal:6380"
      database: 2
~~~

With the default factory created by Boot, the connection endpoint will go to `redis-b.internal:6380` per `url`; it will not go to `redis-a.internal:6379`. The `database: 2` setting is still used to select the logical database in a matching standalone configuration.

This difference explains why developers sometimes change `host` yet the application keeps connecting to the old server: a `url` from another YAML file, environment variable, config server, or active profile is taking effect.

**Simple rule:** Choose **one** style of endpoint declaration per environment. Either use `host + port + username/password`, or use `url`. Avoid maintaining both with conflicting values.

### 5.3. TLS: `redis://` and `rediss://`

By Redis URI convention, `redis://` denotes a plain connection; `rediss://` denotes a TLS-protected connection. When using Spring Boot, explicitly declare SSL/TLS configuration matching the endpoint:

~~~yaml
spring:
  data:
    redis:
      url: "rediss://redis.secure.example:6380"
      ssl:
        enabled: true
      connect-timeout: 3s
      timeout: 5s
~~~

Scheme recognition, truststore configuration, and TLS certificate handling also depend on the driver/framework version and environment. **Enabling TLS successfully does not mean every certificate is valid**; the server certificate, hostname, CA, and verification policy must align. For managed Redis services, use the TLS port published by the provider rather than assuming `6380` is always TLS.

Do not disable certificate verification to “fix” errors in production. If a handshake error occurs, inspect the server certificate, trust chain, DNS, and TLS settings first.

### 5.4. Username, Password, and Special Characters in URLs

Redis 6+ supports ACL users/passwords. If using an ACL account:

~~~yaml
spring:
  data:
    redis:
      host: redis.internal.example
      port: 6379
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
~~~

If the system only uses the default user with a password, the `username` property may be omitted; use the actual authentication parameters provided by the server.

With URLs, special characters in username/password such as `@`, `:`, `/`, `?`, `#` have syntactic roles in URIs and must be encoded according to the URI parser in use. A password containing `@` must not be inserted literally into the userinfo segment. Also note each driver's decoding behavior; test the actual connection rather than guessing whether a string is decoded once or twice.

Using secrets and environment references is generally easier to manage than writing `redis://user:password@host` directly in source files:

~~~yaml
spring:
  data:
    redis:
      url: ${REDIS_URL}
      database: 0
~~~

Here `REDIS_URL` is an environment variable provided at runtime. Avoid printing full URLs containing credentials into logs, command history, or diagnostic reports that might be shared.

### 5.5. A URL Does Not Replace Every Topology Configuration

A typical `redis://host:port` URL describes a standalone endpoint. It does not automatically represent full mechanisms for discovering a primary via Sentinel or listing Redis Cluster nodes.

Example Redis Sentinel configuration:

~~~yaml
spring:
  data:
    redis:
      sentinel:
        master: mymaster
        nodes:
          - sentinel-1:26379
          - sentinel-2:26379
          - sentinel-3:26379
~~~

The hostnames in the example are placeholders. When a system uses Sentinel, you must connect to the Sentinel endpoints and choose the right master name; when using Redis Cluster, you must configure the cluster nodes. Do not combine a standalone URL with another topology simultaneously without carefully reading Spring Boot's precedence rules for your running version.

## 6. Managing Configuration Across Local, Test, Staging, and Production

### 6.1. Prefer Externalized Values for Environment-Specific Endpoints

You can use a shared YAML file and pass endpoints via environment variables:

~~~yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
      database: ${REDIS_DATABASE:0}
      connect-timeout: 2s
      timeout: 3s
~~~

The `${REDIS_HOST:localhost}` syntax is Spring's placeholder mechanism: if the environment variable exists, use its value; otherwise default to `localhost`. In Spring Boot configuration, you can also use environment property names directly via relaxed binding, for example:

~~~text
SPRING_DATA_REDIS_HOST=redis
SPRING_DATA_REDIS_PORT=6379
SPRING_DATA_REDIS_DATABASE=2
~~~

If `SPRING_DATA_REDIS_URL` is set alongside `host` and `port`, URL precedence rules still apply. Setting an environment variable does not guarantee it will be used if a higher-precedence property source exists or the application provides its own connection factory.

### 6.2. Using Profiles for Intentional Differences

Example `application-local.yml`:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      database: 2
~~~

Example `application-prod.yml`:

~~~yaml
spring:
  data:
    redis:
      host: redis.production.internal
      port: 6379
      database: 0
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
~~~

Activate a profile at startup:

~~~bash
java -jar app.jar --spring.profiles.active=local
~~~

There is no need to change Java services when switching profiles. This is the benefit of putting endpoints into `application*.yml` and letting Spring Boot wire the factory automatically.

For production, **separating the Redis deployment** from dev/test Redis remains the most important boundary. Using different DB numbers on the same instance cannot protect production data from `FLUSHALL`, server crashes, or shared-resource issues.

### 6.3. Configuring Directly via Environment Variables

If the infrastructure already provides a URL, you can omit the host/port pair completely in application configuration:

~~~yaml
spring:
  data:
    redis:
      url: ${REDIS_URL}
      database: ${REDIS_DATABASE:0}
~~~

When choosing this approach, the operations team should agree on conventions: the URL must point to the standalone Redis for the right environment, use the proper scheme, include required credentials, and DB selection must be clearly configured/verified. In cloud services, a Redis endpoint may change after failover or be exposed via DNS; do not replace DNS with a hardcoded IP if the provider requires clients to connect by service name.

## 7. Relationship Between Endpoint, Connection Factory, and Connection Pool

Spring Data Redis does not re-read `application.yml` every time `GET` is called. In a standard setup, Spring Boot binds properties, initializes `LettuceConnectionFactory`, and injects that factory into `StringRedisTemplate` and other templates.

~~~mermaid
flowchart LR
    A["application.yml / env"] --> B["RedisProperties"]
    B --> C["LettuceConnectionFactory"]
    C --> D["StringRedisTemplate"]
    C --> E["RedisTemplate"]
    D --> F["GET / SET"]
    E --> F
    F --> G["Redis server / logical DB"]
~~~

If an application declares **its own `RedisConnectionFactory` bean**, the auto-configuration that creates the default factory may back off. In that case, `spring.data.redis.host`, `port`, `database`, and `url` **are not necessarily applied automatically** to the custom factory; your manual configuration code must read and apply them if desired.

### 7.1. Where Is the Database Selected When Using a Pool?

A connection pool manages connection lifecycle and reuse, but it should not be treated as the place that decides which DB each request runs against. **Connections borrowed from the pool must be initialized in accordance with the configured factory, endpoint, and logical database.**

With Lettuce, not every operation needs a separate physical TCP connection. Lettuce can use a shared connection for ordinary operations, whereas certain modes or concurrency requirements need separate connections. Pooling is a choice based on load measurement and driver behavior, not mandatory simply because an application has multiple threads.

Example pool properties when **a pooling dependency has been added** and you genuinely want to use it:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.apache.commons:commons-pool2'
}
~~~

~~~yaml
spring:
  data:
    redis:
      host: redis.internal
      port: 6379
      database: 1
      lettuce:
        pool:
          enabled: true
          max-active: 16
          max-idle: 8
          min-idle: 0
          max-wait: 1s
~~~

This illustrates the configuration syntax, not generally recommended numbers. Pool capacity should be based on the number of connections needed, Lettuce behavior, latency, and client limits on the Redis server.

**A pool does not create extra logical databases** and does not bypass Redis server limits. If an app uses two different databases/endpoints, design separate factories or templates intentionally, rather than running `SELECT` directly on a connection managed by a pool.

### 7.2. When Do You Need to Create a Factory Manually?

Usually `spring.data.redis.*` is sufficient. Define a manual bean when you have requirements that cannot be expressed via properties/customizers or when you need multiple separate connections.

Example illustrating a custom standalone factory:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration(proxyBeanMethods = false)
public class SpecialRedisConfig {

    @Bean
    RedisConnectionFactory redisConnectionFactory() {
        RedisStandaloneConfiguration server =
                new RedisStandaloneConfiguration("redis.internal", 6379);
        server.setDatabase(2);
        return new LettuceConnectionFactory(server);
    }
}
~~~

This factory **hardcodes** the endpoint to illustrate the API, not as a configuration to copy verbatim into production. Once you take ownership of the factory, you must decide how to obtain credentials, TLS, timeouts, topology, and related properties; do not assume Boot will apply all YAML properties to the object you created. When you only need to tweak a Lettuce option, consider a customizer instead of rewriting the entire factory.

## 8. Verifying Connections Reach the Right Host, Port, and DB

### 8.1. Checking the Server from the Application's Runtime Environment

If local Redis has no authentication:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 PING
~~~

The expected output when the server allows the command is `PONG`.

If the application runs in Docker Compose, run the equivalent command from an environment sharing the same network as the application (or via a client container on the same network). Running `redis-cli` successfully on your laptop does not prove the application container can resolve the `redis` hostname or reach the target port.

For TLS, Redis CLI supports `--tls` and the required CA/certificate options depending on the deployment. For Redis requiring authentication, use a secure method to provide credentials rather than putting the password directly after `-a` or in a URI on the command line, as it can leak via command history or process lists.

### 8.2. Checking the Logical Database with a Clearly Named Test Key

Only perform this in a test environment where writes are permitted:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 -n 2 SET lesson:db-check "database-two"
redis-cli -h 127.0.0.1 -p 6379 -n 2 GET lesson:db-check
redis-cli -h 127.0.0.1 -p 6379 -n 0 GET lesson:db-check
redis-cli -h 127.0.0.1 -p 6379 -n 2 DEL lesson:db-check
~~~

Expected behavior in a standalone Redis supporting DB 0 and DB 2:

- `GET` in DB 2 returns `database-two`.
- `GET` in DB 0 returns nil if no key with that name existed previously.
- The final `DEL` removes only the test key in DB 2.

To observe key counts per DB, you can run:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 INFO keyspace
~~~

Example output may include `db0:keys=...` and `db2:keys=...`. These are instance-wide statistics for DBs containing keys; they do not prove which DB a specific Spring client is selecting. To verify the Spring client, write/read a test key using the app's own `StringRedisTemplate`, then inspect it with Redis CLI in the expected database.

### 8.3. Distinguishing Errors When Spring Runs

| Symptom | What to check first | Key takeaway |
|---|---|---|
| `Connection refused` | Host/port, Redis process, published port, or Redis bind address | Reached the destination host, but no listener is accepting connections on that port |
| `UnknownHostException` / DNS resolution failure | DNS/service name from the app's network | The Redis hostname cannot be resolved from the client environment |
| Connection timeout | Firewall, routing, unresponsive service, connect-timeout | Uncertain whether Redis received the request; inspect the network path |
| `NOAUTH` / `WRONGPASS` errors | Username, password, ACL user, URL precedence | Communicating with Redis, but authentication failed |
| TLS handshake/certificate error | Scheme, SSL enabled, truststore, CA, hostname | Establishing the secure channel failed |
| `GET` returns null without exception | `database`, key prefix, TTL, endpoint pointing to another environment | Redis may be working normally, but the key is not at the location being read |
| `ERR DB index is out of range` | Actual DB indices supported by the server | Requested logical database does not exist |
| `SELECT` error in Cluster | Redis Cluster topology | Cluster does not permit using logical DBs other than 0 |
| Changed `host` but still hitting old server | Whether `url` is set, profiles, env overrides | A higher-precedence URL/config source is active |
| Custom factory ignores YAML | Custom `RedisConnectionFactory` bean | Boot yielded factory creation to the application |

**Do not treat every issue by increasing timeouts.** Errors from choosing the wrong host, port, username, or database do not disappear by waiting longer.

### 8.4. Diagnosing Effective Properties

To see which beans Spring Boot loaded, you can enable the condition report:

~~~bash
java -jar app.jar --debug
~~~

Inspect sections for `RedisAutoConfiguration`, `LettuceConnectionConfiguration`, or `JedisConnectionConfiguration` to see whether auto-configuration created the factory/template or backed off for an application bean.

To find the actual endpoint, check in order:

1. Active profiles and corresponding `application*.yml` files.
2. Environment variables, command-line arguments, external configs, and environment-provided secrets.
3. Whether `spring.data.redis.url` is present; if so, individual endpoint fields may no longer apply.
4. Whether there is a custom `RedisConnectionFactory`, Lettuce customizer, or Sentinel/Cluster topology.
5. Whether the network namespace where the app runs can resolve the host and reach the target port.
6. When Redis reads return empty, verify the exact DB and key prefix before concluding that writes failed.

Avoid logging the entire `RedisProperties` or URI because they may contain passwords. Configuration reports should mask credentials and only display non-sensitive fields needed for debugging.

## 9. Two Complete Configurations to Visualize the Real Path

### Scenario A: Learning Application Running on a Developer Machine

Redis runs locally in standalone configuration supporting DB 2:

~~~yaml
spring:
  data:
    redis:
      host: 127.0.0.1
      port: 6379
      database: 2
      connect-timeout: 2s
      timeout: 3s
~~~

When `RedisNoteService.save("42", "hello")` is called:

~~~text
StringRedisTemplate
    → LettuceConnectionFactory (127.0.0.1:6379, DB 2)
    → SET note:42 hello EX 900
    → Redis logical database 2
~~~

`RedisNoteService.load("42")` uses the same template/factory and reads from DB 2. If you open `redis-cli` on DB 0 and do not see the key, that is the expected behavior of logical databases.

### Scenario B: Application Receiving a Redis URL from the Deployment Environment

Infrastructure manages the endpoint and credentials via the `REDIS_URL` secret:

~~~yaml
spring:
  data:
    redis:
      url: ${REDIS_URL}
      database: 0
      ssl:
        enabled: true
      connect-timeout: 3s
      timeout: 5s
~~~

An illustrative secret value format might be `rediss://user:password@managed-redis.example:6380`; **this is only an illustrative string, not real access credentials**.

In this scenario, the application reads the endpoint from `REDIS_URL`, uses DB 0 if the topology supports it, and connects over TLS as configured. In operations, verify that the URL uses the scheme/port required by the provider, the certificate is trusted, and the user has permissions on the keys the application needs to access.

Both scenarios use the exact same Spring Data Redis service class. The difference lies in **the factory and the configuration values the factory receives**, not in the code calling `opsForValue()`.

## 10. Key Principles Before Studying Pooling and Advanced Topologies

1. **Confirm the client's perspective:** `localhost` is the machine or container running the application itself; Docker Compose/Kubernetes hostnames only make sense within the right network.
2. **Distinguish Redis port from forwarded port:** `6380:6379` means the host uses `6380`, while the Redis service inside the container network still listens on `6379`.
3. **Select the logical database explicitly:** `spring.data.redis.database` defaults to 0; other DBs only make sense when the server/topology permits them, and they are not a security isolation boundary.
4. **Do not use DBs other than 0 with Redis Cluster:** design keyspaces and deployments instead.
5. **Do not mix multiple endpoint sources unnecessarily:** in Boot 3.x, `url` overrides `host`, `port`, `username`, and `password` in Boot-managed standalone configuration.
6. **Keep credentials and TLS accurate per environment:** secrets do not belong in source/logs; TLS endpoints require proper certificate/trust configuration.
7. **Prefer configuring via Boot properties:** declare a manual `RedisConnectionFactory` only when truly needed, because an application-owned factory may no longer pick up default properties.
8. **Treat a successful connection as only part of verification:** confirm the actual Redis server, DB, and keyspace are right, especially when reads return null.
9. **A pool is a connection management layer:** a pool does not change host/port/database selection rules and does not create isolation between logical databases.

Once you understand **which Redis the application connects to, on which port, with what authentication, and which logical database it selects**, studying pooling, timeouts, failover, or Redis Cluster will have a clear foundation. Connection pool issues are usually diagnosed accurately only after endpoint and database configuration have been confirmed.

## References for Further Reading

- [Spring Boot 3.3 — Working with NoSQL Technologies: Redis](https://docs.spring.io/spring-boot/3.3/reference/data/nosql.html)
- [Spring Boot 3.3 — Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Data Redis — Redis Support](https://docs.spring.io/spring-data/redis/reference/redis.html)
- [Spring Data Redis — Redis Drivers](https://docs.spring.io/spring-data/redis/reference/redis/drivers.html)
- [Redis — SELECT command](https://redis.io/docs/latest/commands/select/)
- [Redis — Redis Cluster Specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
