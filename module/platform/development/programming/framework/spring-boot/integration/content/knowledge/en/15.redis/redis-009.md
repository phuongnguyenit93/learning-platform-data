# SSL, Authentication, and Access Control for Redis

## 1. Why Does a Spring Boot Application Need to Secure Redis?

In Spring Boot Integration systems, Redis commonly stores HTTP client caches, temporary adapter state, webhook deduplication locks, rate-limit counters, or login sessions. Those components often span multiple instances, pods, or servers. Redis is fast, yet a successful network connection does not mean that connection is secure.

For example, an `order-integration` service stores cache entries at keys:

~~~text
integration:orders:tenant-42:ORD-1001
integration:orders:tenant-42:ORD-1002
integration:dedup:partner-a:evt-198
~~~

Without encryption, data and credentials can be intercepted in transit. If all services share a single superuser account, a bug in one service can read or delete another service's data. If the Redis port is exposed to the public Internet, even a strong password is no substitute for network access controls.

This lesson builds a security model around four questions: **who can reach the port, does the client verify the true server, which identity does it authenticate with, and which commands, keys, or channels is that identity allowed to touch?** Examples use ACL-capable Redis (Redis 6+), Spring Boot 3.x, and Spring Data Redis/Lettuce; cross-check properties and features if running other versions.

## 2. Distinguishing TLS, Authentication, Authorization, and Network Controls

| Defense Layer | Question Addressed | Mechanism | What It Does Not Guarantee Alone |
| --- | --- | --- | --- |
| **Network access** | Which clients can open TCP to Redis? | Private subnets, firewalls, security groups, Kubernetes NetworkPolicy, bind/port | Least-privilege Redis account permissions |
| **TLS/SSL** | Is transport encrypted and the server verified? | TLS certificates, CA trust, hostname validation, mTLS if needed | Which commands or keys are permitted |
| **Authentication** | Which Redis user is this client? | `AUTH`, ACL username/password | Which keys that user may read or write |
| **Authorization** | Which commands, keys, or channels may the user access? | Redis ACL command/category/key/channel rules | End-user tenant authorization or cross-system transactions |

~~~mermaid
flowchart LR
    A["Spring Boot / Lettuce"] --> B{"Network allowed?"}
    B -->|No| X["TCP refused"]
    B -->|Yes| C{"TLS and certificate valid?"}
    C -->|No| Y["TLS handshake failed"]
    C -->|Yes| D{"Redis AUTH valid?"}
    D -->|No| Z["NOAUTH / WRONGPASS"]
    D -->|Yes| E{"Redis ACL permits command/key?"}
    E -->|Yes| F["GET/SET succeeds"]
    E -->|No| G["NOPERM"]
~~~

TLS protects the wire, ACLs constrain actions, and firewalls stop unauthorized sources from initiating connections. All three must work together. A client over TLS with `+@all` permissions can still wipe everything; conversely, strict ACLs over plaintext still leak credentials in transit.

## 3. SSL/TLS on the Redis Server

### 3.1. Encrypting Connections and Verifying the Server

TLS encrypts traffic and lets clients verify server certificates signed by a trusted CA with DNS/SAN entries matching the actual endpoint. Redis OSS must be built/packaged with TLS support. Enabling TLS **does not automatically disable the plaintext TCP port**; operators must verify config and listening ports.

Partial `redis.conf` example for a self-managed server:

~~~conf
# Bind only to the server's actual private interface.
bind 10.10.1.12
protected-mode yes

# Disable unencrypted TCP port; enable TLS on sample port 6380.
port 0
tls-port 6380
tls-cert-file /etc/redis/tls/server.crt
tls-key-file /etc/redis/tls/server.key
tls-ca-cert-file /etc/redis/tls/ca.crt

# One-way TLS: server presents certificate for client verification.
# Client certificates not required; AUTH/ACL configured separately.
tls-auth-clients no
~~~

`10.10.1.12` and `6380` are illustrative values, not mandatory defaults; managed Redis services may use different endpoints and ports. Firewalls/NetworkPolicies must restrict actual traffic sources. `protected-mode` is a fallback safety net, not a replacement for network rules.

**This TLS snippet alone does not enable Redis authentication.** A fresh Redis setup may still permit the `default` user with no password and broad privileges. Configure dedicated ACL users as shown below, create and verify a fallback admin account, then restrict or disable the `default` user per plan; persist ACLs via your deployment's supported mechanism. Skipping this leaves unauthenticated access open even over a TLS port.

With **mutual TLS (mTLS)**, Redis sets `tls-auth-clients yes`, requiring clients to present a CA-accepted certificate and private key. mTLS authenticates at the TLS layer; the application still needs `AUTH`/ACL policies. Never bake TLS private keys into repositories or public Docker images; mount them via a secret manager with restricted file permissions and certificate rotation.

If Redis uses Cluster or replication over TLS, also check `tls-cluster yes`, `tls-replication yes`, internal node traffic, and endpoint certificates. Securing only Spring Boot → Redis does not automatically encrypt inter-node links.

### 3.2. Testing with Redis CLI

Once network rules permit access and `redis-cli` supports TLS:

~~~bash
redis-cli --tls \
  -h redis.internal.example \
  -p 6380 \
  --cacert /run/secrets/redis/ca.crt \
  --user order-cache \
  --askpass
~~~

`--askpass` prompts interactively for the password, keeping it out of command-line arguments. If the server requires mTLS, add `--cert /run/secrets/redis/client.crt --key /run/secrets/redis/client.key`. Never skip CA or hostname verification just to "get connected": doing so defeats detection of spoofed servers.

Once connected, test `PING` and ACL-permitted data commands. Distinguish failures carefully:

- `Connection refused` or timeout: DNS, routing, firewall, service/port, or Redis not ready.
- TLS handshake / certificate verify failed: wrong CA, incomplete chain, expired certificate, hostname mismatch, or missing client certificate under mTLS.
- `WRONGPASS`/`NOAUTH`: Redis requires login or username/password is invalid.
- `NOPERM`: authenticated, yet ACL rejected the command, key, or channel.

## 4. Redis ACLs: Creating Least-Privilege Users

### 4.1. How Redis ACLs Differ from `requirepass`?

Since Redis 6+, **Access Control Lists (ACLs)** support multiple independent users, each with passwords, `on/off` status, command permissions, and key/channel patterns. Legacy `requirepass` only protects the `default` user without per-service isolation.

Example recommended roles:

| Redis User | Role | Key Namespace | Data Permissions |
| --- | --- | --- | --- |
| `order-cache` | Order status cache | `integration:orders:*` | `GET`, `SET`, and specific TTL commands actually used |
| `order-dedup` | Temporary webhook dedup | `integration:dedup:*` | `SET NX EX`, read/TTL commands as needed |
| `order-reader` | Read-only service | `integration:orders:*` | `GET`, `MGET` |
| `redis-admin` | Redis administration | Per operational policy | Provisioned separately; never used as runtime app user |

Log in with the Redis admin account and run in an **interactive `redis-cli` session**:

~~~redis
ACL SETUSER order-cache reset on >REPLACE_WITH_LONG_RANDOM_SECRET ~integration:orders:* +get +set +del +pttl +ping +hello
~~~

Meaning:

- `reset` clears prior permissions/passwords/patterns before reconfiguring; use intentionally as it can affect live clients.
- `on` enables the user; `>...` sets the password. Always replace the placeholder with a long random secret.
- `~integration:orders:*` restricts accessible keys.
- `+get +set +del +pttl` grants data commands; `+ping +hello` are example handshake/connection commands. Unlisted commands remain denied after `reset`.

The `>` character in Redis ACL syntax can be interpreted as shell output redirection if pasted directly into an OS terminal. Use an interactive Redis CLI session, securely managed ACL files, or provisioning automation; avoid leaking secrets into shell history, CI logs, or Git.

The command list above is a **starting point** for `GET`/`SET` adapters; it may not cover every Lettuce version, health check, `RedisCacheManager`, or cluster client. Some clients also issue `CLIENT SETNAME`/`CLIENT SETINFO`, `SELECT`, or `INFO`. On `NOPERM`, inspect the exact command requested and grant the minimum required—never default to `+@all`.

A read-only account can start with:

~~~redis
ACL SETUSER order-reader reset on >REPLACE_WITH_ANOTHER_SECRET ~integration:orders:* +get +mget +pttl +ping +hello
~~~

Because the account lacks `SET`/`DEL`, Redis rejects those writes. Exact behavior for other commands depends on the configured ACL; never infer "read-only" solely from a username.

### 4.2. Key Patterns, Commands, and Pub/Sub Channels

| ACL Syntax | Example | Purpose |
| --- | --- | --- |
| Key pattern | `~integration:orders:*` | Restricts accessible key names |
| Specific commands | `+get +set` | Grants only needed commands |
| Command categories | `+@read`, `+@write` | Grants command groups; may be broader than necessary |
| Channel pattern | `&integration:events:*` | Restricts Pub/Sub channels |
| Admin commands | `FLUSHALL`, `FLUSHDB`, `CONFIG`, `ACL` | Never grant to regular application users |

`~...` restricts **keys**, not **Pub/Sub channels**. When using `PUBLISH`/`SUBSCRIBE`, also audit command permissions and `&...` channel patterns. Supported Redis versions can distinguish read-only vs. write-only key patterns via `%R~` and `%W~`; verify server version before relying on them.

If an application uses Redis Streams, Lua scripts, RedisJSON, Redis Search, or pattern-based Spring Cache clearing, required commands differ from simple `GET`/`SET`. Design ACLs around actual operations and test with the exact Spring Boot client in use.

**Redis ACLs are not end-user authorization.** An API taking `tenantId` from a query string to form `integration:orders:<tenantId>:...` can still reach another tenant's key matching the same pattern. Derive tenants from verified security contexts, enforce business authorization, and validate keys; never hand Redis credentials directly to browsers or mobile clients.

## 5. Spring Boot Configuration and Secure Redis Access

### 5.1. Spring Data Redis with Lettuce

~~~kotlin
// build.gradle.kts — Spring Boot 3.x example
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
}
~~~

Spring Boot 3.x uses Lettuce by default. When the server uses a certificate signed by a default trusted CA:

~~~yaml
# application.yml
spring:
  data:
    redis:
      host: redis.internal.example
      port: 6380
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
      connect-timeout: 3s
      timeout: 2s
~~~

`${REDIS_USERNAME}` and `${REDIS_PASSWORD}` instruct Spring to resolve credentials from environment variables. Never store static passwords in committed config files or in URIs that could appear in logs.

For a **private CA**, Spring Boot 3.1+ supports SSL bundles; verify exact syntax against your Boot version:

~~~yaml
# Alternative configuration when a private CA is required
spring:
  ssl:
    bundle:
      pem:
        redis-client:
          truststore:
            certificate: file:/run/secrets/redis/ca.crt
  data:
    redis:
      host: redis.internal.example
      port: 6380
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
        bundle: redis-client
~~~

The CA certificate must exist at runtime at the specified path with a valid trust chain. For mTLS, add the client certificate and private key to the SSL bundle per your version's schema. If you manually instantiate `LettuceConnectionFactory`, Spring Boot properties may not apply automatically; configure and verify the actual client bean. Similarly, if using `rediss://...` URLs, check precedence rules and keep passwords out of URIs.

Never install a custom "trust-all" trust manager just to bypass handshake errors. That disables server identity verification even though traffic stays TLS-formatted.

### 5.2. Adapter Example Using Only GET/SET Within Its Granted Namespace

~~~java
// OrderCacheAdapter.java
import java.time.Duration;
import java.util.regex.Pattern;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderCacheAdapter {
    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");
    private final StringRedisTemplate redis;

    public OrderCacheAdapter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void putStatus(String tenantId, String orderId, String status) {
        redis.opsForValue().set(key(tenantId, orderId),
                status, Duration.ofMinutes(10));
    }

    public String getStatus(String tenantId, String orderId) {
        return redis.opsForValue().get(key(tenantId, orderId));
    }

    private String key(String tenantId, String orderId) {
        if (!SAFE_ID.matcher(tenantId).matches()
                || !SAFE_ID.matcher(orderId).matches()) {
            throw new IllegalArgumentException("Invalid key component");
        }
        return "integration:orders:" + tenantId + ":" + orderId;
    }
}
~~~

`putStatus` issues `SET` with TTL; `getStatus` issues `GET`. The sample Redis ACL permits both on `integration:orders:*`. The regex stops unexpected delimiters in key segments; **it does not authorize tenants**. `tenantId` must come from an authenticated identity/context validated against business policy.

When Redis serves as a cache, `GET` returning `null` indicates a missing or expired key. Never silently treat `NOPERM`, TLS handshake errors, or timeouts as "cache misses": those require logs, metrics, and explicit fallback behavior.

If Redis handles webhook deduplication, `SET key value NX EX seconds` creates a TTL-bounded marker atomically **within Redis**. Still, markers and DB commits/broker acks are not in one transaction; crashes can leave missing or duplicate effects. For durable exactly-once effects, use DB inboxes/unique constraints and clear replay rules.

## 6. Network Restrictions and Redis Topologies

### Standalone, Sentinel, Cluster, and Managed Services

| Topology | TLS and Permission Points to Verify |
| --- | --- |
| **Standalone** | Private endpoint, TLS port, ACL user, CA trust, firewall/NetworkPolicy |
| **Sentinel** | Clients connect to both Sentinels and Redis data nodes; configure auth and TLS separately for both |
| **Redis Cluster** | Clients follow redirects across nodes; every reachable node needs valid DNS/certificates/ACLs/network access |
| **Managed Redis** | Follow provider docs on TLS endpoints, user/ACL setup, password rotation, and networking; never assume ports 6379 or 6380 |

In Redis Cluster, opening network access from Spring Boot to seed nodes **may not be enough**. After receiving `MOVED`/`ASK`, clients open connections to target nodes. Certificates must match the endpoints clients connect to, and ACLs must be applied consistently across cluster nodes. Never "fix" redirect errors by opening entire subnets unnecessarily wide.

In Redis Sentinel, Sentinel authentication and Redis data node authentication can differ; specify one shared password in Spring Boot only when the topology actually shares it. In multi-tenant setups, separate Redis users/prefixes per service or data boundary and enforce tenant authorization in the backend.

### Secret Management and Rotation

A strong password still leaks through logs, config files, command history, or CI pipelines if mishandled. Credential lifecycles should cover:

1. Provision ACL users and secrets via restricted admin automation; never share passwords in chat, public tickets, or source repositories.
2. Separate credentials across development, staging, and production; separate operator accounts from runtime app accounts.
3. Deliver secrets via a secret manager, protected volumes, or platform-controlled environment variables; redact secrets from logs.
4. During rotation, add the new password alongside the old one on the Redis ACL user if supported, roll out clients/pools, then revoke the old password. Plan rollback in case deployments fail to connect.
5. Monitor certificate expiry, CA/certificate rotations, post-rotation reconnects, and `WRONGPASS`/`NOPERM` rates.

Never disable the `default` user before a tested admin account and recovery path are verified. On self-managed Redis, persist `ACL SETUSER` changes via the configured mechanism (e.g., ACL file/`ACL SAVE` when appropriate); otherwise restarts revert ACLs. Never grant admin commands to an app user so it can rotate its own credentials.

`maxclients`, connection pools, and timeouts bound resources, **not tenant authorization**. Redis should never be directly accessible from browsers or mobile clients; the backend owns Redis credentials and enforces business authorization.

## 7. Testing ACLs and TLS Without Touching Production Data

### 7.1. Using ACL DRYRUN to Check Permissions

Redis 7+ supports `ACL DRYRUN`, allowing an **admin account** to test whether a user is authorized to execute a command with given arguments without running it. In a Redis admin session:

~~~redis
ACL DRYRUN order-cache GET integration:orders:tenant-42:ORD-1001
ACL DRYRUN order-cache SET integration:orders:tenant-42:ORD-1001 PAID
ACL DRYRUN order-cache GET private:payroll:employee-7
ACL DRYRUN order-cache FLUSHALL
~~~

Under the sample `order-cache` rule, the first two pass and the last two must be denied. **Never run a real `FLUSHALL`** to test permissions. `ACL DRYRUN` verifies ACL rules; it does not verify server certificates, firewalls, or Spring Boot's actual connection settings.

`ACL GETUSER` and `ACL LOG` help operators inspect users and denied commands; grant those only to appropriate admin accounts. After upgrading Lettuce or Spring Data Redis, `ACL LOG` may show new handshake or health commands like `CLIENT SETINFO` or `HELLO`. Evaluate newly introduced commands before allowlisting them.

### 7.2. Integration Test Matrix

| Test Scenario | Expected Outcome to Verify |
| --- | --- |
| Valid CA, hostname, user, and password | Spring Boot connects over TLS; `GET`/`SET` on allowed prefix succeeds |
| Untrusted CA or DNS/SAN mismatch | TLS handshake fails; never falls back to plaintext |
| Wrong username/password | Redis rejects authentication; no data commands execute |
| `order-reader` calls `SET` | `NOPERM` on write command |
| `order-cache` calls `GET private:payroll:*` | `NOPERM` due to key pattern |
| Connection from non-allowlisted IP/pod | TCP connection cannot reach Redis |
| Old password revoked after rotation | New connections with old password are rejected |
| Failover to another Redis node | TLS/ACL connections remain valid on new endpoint |
| Redis client or Boot upgraded | No unexpected `NOPERM` errors; no overly broad permissions added |

Test using the **same `LettuceConnectionFactory` or Spring Data Redis client** used in production. Succeeding with `redis-cli` does not guarantee Spring Boot loaded the right SSL bundle, secrets, hostname, or startup handshake commands.

Unit-testing key builders cannot replace testing real TLS, authentication, and Redis ACLs against a server. Use an isolated integration environment or a Redis container configured with matching TLS and ACLs; never test destructive commands or simulate leaked credentials in production.

## 8. Debugging Connection, Permission, and Post-Upgrade Failures

| Symptom | Common Cause | Check / Fix |
| --- | --- | --- |
| `Connection refused` or connect timeout | Wrong hostname/port, DNS, firewall, Redis not ready | Inspect endpoints, network policies, service readiness; never expose Redis publicly |
| `SSLHandshakeException`, certificate verify failed | Invalid CA/chain/SAN, expired cert, missing client cert under mTLS | Fix CA/certificates; keep TLS verification enabled |
| `WRONGPASS invalid username-password pair` | Wrong user/password, user `off`, unsynced rotation | Verify secrets and server ACL user state |
| `NOAUTH Authentication required` | Client did not send valid credentials | Check property bindings and active connection factory |
| `NOPERM this user has no permissions to run command` | Command missing from allowlist (e.g., health checks, cache clear, handshake) | Inspect `ACL LOG` to identify command; grant minimal permission |
| `NOPERM ... access one of the keys ...` | Key prefix mismatch or wrong serializer/policy | Compare actual wire keys against ACL pattern |
| Works in CLI, fails in application | CLI and Java client use different CA/certs/endpoints/credentials | Inspect Spring config, SSL bundles, and injected factory |
| Works Standalone, fails in Cluster | Redirected node lacks open network or has different certs/ACLs | Verify every node endpoint in the cluster |
| `NOPERM` appears after client upgrade | Lettuce or Spring Data sends extra commands | Compare `ACL LOG`, release notes, and actual commands |
| Keys missing from Redis with no error | TTL expired, key prefix, DB index, serializer, or wrong env | Check `GET`/`SET` logic, TTLs, and client configuration |

**Quick distinction:** `WRONGPASS`/`NOAUTH` are authentication issues, `NOPERM` is an authorization issue, and TLS handshake failures happen before Redis ACLs run. Never resolve certificate errors by adding `+@all`, and never resolve ACL errors by disabling TLS.

When logging, record only necessary details such as service, hostname without secrets, user name per internal policy, denied command, latency, correlation ID, and error category. Avoid printing Redis URLs containing passwords, full payloads, or keys with personal info. Spring Boot `/actuator/health` may also issue Redis check commands; if ACLs block health commands, adjust the health contributor or grant the exact minimal command after review.

## 9. Combining Security Layers in an Order Integration Flow

Suppose Spring Boot receives a payment webhook, writes to PostgreSQL, and uses a Redis cache for fast lookups:

~~~text
Partner webhook
      |
      v
Spring Boot (validate input, authenticate tenant, transaction)
      |
      +---> PostgreSQL: authoritative order store
      |
      +---> Redis TLS endpoint: redis.internal.example:6380
                |
                +-- ACL user: order-cache
                +-- Key prefix: integration:orders:*
                +-- GET/SET per policy, 10-minute TTL
                +-- Connected from private application network
~~~

Operational decisions:

1. **Network:** Redis listens only on its private interface and TLS port; firewall permits only required workloads.
2. **TLS:** client verifies server certificates via CA; if using mTLS, client holds valid cert/key.
3. **Authentication/ACL:** `order-cache` uses environment-specific credentials and operates only on `integration:orders:*` with tested commands.
4. **App authorization:** `tenantId` comes from the authenticated context; never read another tenant's cache from untrusted request parameters.
5. **Data consistency:** PostgreSQL is the source of truth; Redis write/invalidation errors after DB commit are handled via controlled fallback/invalidation/retry. TLS and ACLs do not turn Redis + PostgreSQL into an atomic transaction.
6. **Observability:** monitor timeouts, latency, TLS errors, `WRONGPASS`, `NOPERM`, certificate expiry, and post-upgrade errors.

If Redis stores idempotency markers for HTTP/Kafka/RabbitMQ messages, also account for TTL windows and crash recovery. ACLs protect markers from unauthorized Redis users, yet do not automatically provide exactly-once guarantees across brokers, databases, and Redis.

## 10. Self-Check Questions

**1. If Redis already has a password, why is TLS needed?** Passwords authenticate the client, whereas TLS encrypts traffic in transit and authenticates the server; they serve different goals.

**2. Does `spring.data.redis.ssl.enabled=true` restrict Redis commands?** No. Redis ACLs must be configured separately.

**3. Does Redis ACL `~integration:orders:*` replace tenant authorization checks?** No. It only restricts keys per Redis user; it has no knowledge of the end HTTP caller.

**4. Password is correct yet `SET` returns `NOPERM`—what is the cause?** The user authenticated successfully, but its ACL forbids `SET` or forbids that key pattern.

**5. Why avoid granting `+@all` when a client upgrade triggers `NOPERM`?** It grants excessive privileges; identify the exact command, review it, and grant only the minimum needed.

**6. If Redis Cluster redirects a client to another node, does that node also need valid certificates and ACLs?** Yes. Clients must connect securely to all reachable cluster nodes.

**7. Is it safe to put passwords straight into `application.yml` assuming TLS protects them?** No. TLS only protects data on the wire; secrets in Git, artifacts, or logs can still leak.

**8. Does a successful Redis cache write guarantee the PostgreSQL transaction succeeded?** No; they have independent commit boundaries requiring proper update/invalidation strategies.

A secure Redis connection in Spring Boot Integration must simultaneously satisfy **restricted networking, verified TLS, dedicated user authentication, and least-privilege ACLs for commands, keys, and channels**. These controls must be tested against real application behavior and monitored continuously whenever Redis or client libraries change.
