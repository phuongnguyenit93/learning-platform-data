# Load Balancing, Shared Session Stores, and Redis Outage Handling in Spring Security WebFlux

## 1. Objectives and Scope

This lesson belongs to the **Secure Deployment** group of **Spring Security – reactive**. After completing it, you should be able to explain why session-based logins can "drop" when requests route to another instance, how Spring Session shares `WebSession` via Redis, how to deploy behind a load balancer, cookie/CSRF security measures, and troubleshooting procedures when Redis fails.

Key concepts:

- In **Spring WebFlux** applications, server-side sessions are accessed via **`WebSession`**, unlike Servlet's `HttpSession`. Spring Session integrates via `WebSessionManager` and `ReactiveSessionRepository`; a Redis backend typically uses `ReactiveRedisSessionRepository`.
- The browser stores a cookie carrying a **session ID**, while session data/authenticated identity lives in the server-side session store. Redis does not turn cookies into JWTs; this remains **stateful authentication**.
- When multiple instances share **one Redis store with the same namespace, session format, and timeout policy**, any instance can retrieve the session using the same session ID. Thus, sticky sessions are generally not required solely to keep users logged in.
- Redis cannot be treated as an "optional cache" if authentication depends on it: losing session read/write capability must be handled safely, never falling back to a default identity or skipping security checks.

## 2. Request Path in a Multi-Instance Cluster

```text
Browser
  | HTTPS, Cookie: SESSION=<opaque-session-id>
  v
Load balancer / reverse proxy (TLS termination, health/routing)
  | round robin / least connections
  +------------------+------------------+
  |                                     |
  v                                     v
Spring WebFlux instance A               Spring WebFlux instance B
SecurityWebFilterChain                  SecurityWebFilterChain
WebSessionManager                       WebSessionManager
  |                                     |
  +------------------+------------------+
                     |
                     v
                Redis shared store
             session ID -> WebSession
                         -> session attributes
                         -> SecurityContext (if using session-based login)
```

An access flow after logging in via form login:

1. The user submits credentials over HTTPS to instance A. Spring Security authenticates, creates/stores `SecurityContext` via a `WebSession`-backed `ServerSecurityContextRepository` (typically `WebSessionServerSecurityContextRepository`).
2. `WebSessionManager`, configured by Spring Session, persists the session in Redis. The response sets a session cookie containing a random session ID.
3. The next request may hit instance B. B reads the ID from the cookie, fetches `WebSession` from Redis, restores `SecurityContext`, and enforces authorization; **B never needs access to A's memory**.
4. Upon logout or session expiration, the corresponding data becomes invalid; a browser carrying the old cookie is not automatically authenticated.

**Critical prerequisite:** every replica uses the same backend/namespace/compatible session serializer and the same authentication mechanism. Sessions stored in one pod's local memory are not automatically shared merely by adding a Redis client dependency; proper Spring Session integration is required.

**Distinction from Bearer JWT:** A purely stateless Resource Server validating Bearer tokens per request typically does not need a Redis session store. Deploy Redis sessions only when flows genuinely use `WebSession`, such as form login, OAuth2 login authorization requests, session-backed CSRF, or session-stateful apps. Do not force every bearer-token API to depend on Redis.

## 3. Why Enabling Sticky Sessions Alone Is Not Enough

**Sticky sessions/session affinity** try to route a client's requests to the same instance using a load-balancer cookie, IP, or other heuristic. It can reduce cross-node hops, but:

- When a pod is replaced, scaled in, loses a node, or undergoes a rolling deploy, sessions stored only in the old pod's RAM are lost.
- IP-based affinity breaks easily behind NAT/proxies; a user's IP can change. LB affinity cookies also cannot save sessions when a node crashes.
- Sticky sessions do not replace replication and reliable session persistence. Shared Redis lets another instance take over when a pod fails or drains.
- Open WebSocket connections are bound to a specific connection; sharing `WebSession` in Redis **does not** automatically distribute WebSocket messages, room subscriptions, or connection state across pods. Those require their own architecture.
- Sessions should not store large business payloads or mutable transactional state; concurrent updates to the same session can race/overwrite each other. Business state belongs in a database or appropriate processing system.

For typical session-backed apps, choose balanced load distribution across instances with shared Spring Session Redis, then prove that routing to node B preserves authenticated state. Sticky sessions may exist for other operational reasons, but must never be the sole requirement for session survival.

## 4. Sample Config: Spring Boot 3.5 + WebFlux + Spring Session Redis

The example uses **Java 17+, Spring Boot 3.5.16, Maven**, and local Redis for development. This is a session-backed WebFlux app using form login to test node failover. `demo` / `demo-pass` are **for learning environments only**; never use these credentials in production.

Structure:

```text
reactive-session-demo/
├── pom.xml
└── src/main/
    ├── java/example/sessiondemo/
    │   ├── SessionDemoApplication.java
    │   ├── SecurityConfig.java
    │   ├── SessionCookieConfig.java
    │   └── WhoAmIController.java
    └── resources/application.yml
```

**`pom.xml`**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>reactive-session-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-redis-reactive</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.session</groupId>
            <artifactId>spring-session-data-redis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

In Spring Boot **3.x**, `spring-session-data-redis` combined with the reactive Redis starter and auto-configuration is the clean path. Some Spring Boot **4.x** docs use a starter named `spring-boot-starter-session-data-redis`; do not copy Boot 4 artifacts into a Boot 3 project out of habit. `spring-session-data-redis` has its version managed by Boot's BOM.

**`src/main/java/example/sessiondemo/SessionDemoApplication.java`**:

```java
package example.sessiondemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionDemoApplication.class, args);
    }
}
```

**`src/main/java/example/sessiondemo/SecurityConfig.java`**:

```java
package example.sessiondemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/actuator/health/**").permitAll()
                .anyExchange().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService() {
        UserDetails demo = User.withUsername("demo")
            .password("{noop}demo-pass") // Local example only.
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(demo);
    }
}
```

Spring Security WebFlux enables CSRF by default for protected requests; **never disable CSRF just to make curl easier**. Configured form login uses `WebSession` to record authentication state, and the cookie lets the browser carry the session ID across requests. In production, replace the in-memory user with a proper identity mechanism (IdP/LDAP/user store) and a secure password encoder.

**`src/main/java/example/sessiondemo/SessionCookieConfig.java`**:

```java
package example.sessiondemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration(proxyBeanMethods = false)
public class SessionCookieConfig {

    @Bean
    WebSessionIdResolver webSessionIdResolver(
            @Value("${app.session.cookie-secure:true}") boolean secure) {
        CookieWebSessionIdResolver resolver = new CookieWebSessionIdResolver();
        resolver.setCookieName("SESSION");
        resolver.addCookieInitializer(cookie -> cookie
            .path("/")
            .httpOnly(true)
            .secure(secure)
            .sameSite("Lax"));
        return resolver;
    }
}
```

`WebSessionIdResolver` is the cookie customization mechanism appropriate for **WebFlux**. `DefaultCookieSerializer` and `HttpSession` commonly seen in Servlet docs are not the primary cookie config for this example. `Secure=true` requires HTTPS in production; only for local HTTP testing do we explicitly set `COOKIE_SECURE=false`. Never transmit session cookies over public HTTP. `SameSite=Lax` generally suits same-site logins; if a legitimate flow truly requires `SameSite=None`, it must also set `Secure` and have matching CSRF/CORS design—do not change it arbitrarily.

**`src/main/java/example/sessiondemo/WhoAmIController.java`**:

```java
package example.sessiondemo;

import java.security.Principal;
import java.util.Map;
import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/whoami")
    public Mono<Map<String, String>> whoami(Mono<Principal> principal) {
        return principal.map(identity -> Map.of(
            "user", identity.getName(),
            "instance", System.getenv().getOrDefault(
                "INSTANCE_ID", "local")
        ));
    }
}
```

The response returns only the username and current replica. Never include session IDs, secrets, or raw `SecurityContext` objects in responses/logs for "debugging."

**`src/main/resources/application.yml`**:

```yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
      connect-timeout: 2s
      timeout: 2s
  session:
    timeout: 30m
    redis:
      namespace: "spring:session:reactive-demo"

app:
  session:
    cookie-secure: ${COOKIE_SECURE:true}

management:
  endpoints:
    web:
      exposure:
        include: health,info
```

Spring Boot 3.5 auto-configures reactive Spring Session when the required modules are present, so this sample **does not add `@EnableRedisWebSession`**. If you manually configure via `@EnableRedisWebSession`, Spring Boot backs off its corresponding auto-configuration; in that case you must understand annotation attributes like `redisNamespace` and timeout rather than assuming all auto-config properties still apply as-is.

`spring.session.timeout` is the session timeout when using Spring Session. `spring.session.redis.namespace` isolates data across apps/environments and must be **identical** across all instances of the same application. `spring.data.redis.*` configures the Redis connection, not cookie TTL. In production, supply the Redis endpoint, TLS/certificates, ACL accounts, and secrets via a secure configuration mechanism; never hardcode passwords in YAML. Set reasonable timeouts so a Redis outage does not hang waiting flows indefinitely.

### Running the Two-Instance Demo

On a local machine with Docker, start a test Redis instance:

```bash
docker run --rm --name demo-redis -p 6379:6379 redis:7.4
```

Open two separate terminals in the project directory (syntax below is for Bash):

```bash
# Terminal 1
SERVER_PORT=8081 INSTANCE_ID=node-a COOKIE_SECURE=false mvn spring-boot:run
```

```bash
# Terminal 2
SERVER_PORT=8082 INSTANCE_ID=node-b COOKIE_SECURE=false mvn spring-boot:run
```

Open `http://localhost:8081/whoami` in a browser; Spring Security redirects to the login page. Sign in with user `demo`, password `demo-pass`, then open `http://localhost:8082/whoami` in **the same browser**. When both instances point to the same Redis and same namespace, the expected response keeps `"user": "demo"` while `"instance"` changes from `"node-a"` to `"node-b"`.

Note: cookies are typically scoped by **hostname and path, not TCP port**, so `localhost:8081` and `localhost:8082` share the cookie under `path("/")`. Real browser login handles the form CSRF token automatically; a `POST /login` without a valid CSRF token can fail with 403, which is **not** a Redis error. Redis and Maven must be available in your environment before running. Never treat the unauthenticated/non-TLS Docker command above as a production setup.

## 5. Configuring the Load Balancer and Cookies to Prevent "Dropped Logins"

| Component | Must Align / Verify | Common Pitfalls |
| --- | --- | --- |
| App replicas | Same app, same Redis namespace, compatible serialization schema, synchronized clocks/timezones | Replica B reads a different namespace or fails to deserialize sessions written by A |
| Load balancer | Route only to ready instances; drain active connections on deploy; forward true host and scheme from trusted proxy | Login redirect uses wrong `http`/`https`, 302 loops |
| Cookie | `Secure` on HTTPS, `HttpOnly`, appropriate `SameSite`, exact path/domain, stable name | Browser refuses to send cookie or two apps overwrite the same cookie name |
| Redis | HA if required, accurate DNS/service discovery, ACLs, TLS, bounded latency and timeouts | `READONLY`, `NOAUTH`, timeouts, key loss due to eviction |
| Spring Security | Endpoint protection, CSRF for cookie-backed requests, session fixation protection, logout | Login succeeds but state-changing requests get 403; logout fails to invalidate session |
| Health checks | Liveness reflects process health; readiness reflects ability to serve Redis-dependent traffic | Redis outage triggers mass restarts or LB keeps routing traffic to failing instances |

**Proxy headers:** in deployments with TLS termination, the app may see internal HTTP connections. Configure forwarded headers per platform—such as `server.forward-headers-strategy=framework` in Boot when deployed behind a **trusted proxy**. Trust only `Forwarded`/`X-Forwarded-*` emitted by your own load balancer and strip/overwrite client-spoofed values. Otherwise, redirect URLs, `Secure` cookies, or hostname logic can break, or spoofing can occur if the app uses forwarded headers for security decisions.

**Cookie name and domain:** keep cookies host-only when an app needs only a single hostname. Setting an overly broad domain like `.example.com` widens cookie sharing across subdomains. If multiple apps run under the same domain/path, assign distinct cookie names/namespaces and scope cookies so clients do not send a session ID belonging to a different app.

**CSRF:** in cookie-based apps, browsers automatically attach cookies to matching requests. CSRF protection must work across both replicas. By default, WebFlux Spring Security uses `WebSessionServerCsrfTokenRepository` for expected CSRF tokens; when `WebSession` is shared in Redis, replica B can validate a CSRF token created on A. `SameSite` is an extra defense layer and **does not replace** CSRF policies for risky flows.

**Session fixation:** after login, the session ID should rotate per Spring Security's protection. `WebSessionServerSecurityContextRepository` changes the session ID when saving `SecurityContext` to mitigate session fixation. Never keep a fixed ID, reuse a user-supplied ID, or expose IDs in URLs.

## 6. Redis as a Critical Dependency of Session-Based Authentication

### 6.1. Data, Lifetime, and Memory

Spring Session Redis stores session data under a dedicated namespace, e.g., prefix `spring:session:reactive-demo`. Session keys typically carry the session ID suffix and associated Redis expirations. Sessions have a **max inactive interval**, rather than strictly a hard cutoff fixed at login time. Valid access updates last-accessed time; write optimization depends on repository/version.

- Set timeouts matching risk levels: 15–30 minutes of inactivity may suit authenticated apps; high-sensitivity systems should also consider absolute session lifetimes, re-authentication, and multi-device controls.
- Cookie expiration and server-side session expiration are **two separate concepts**. A cookie still existing does not prove the corresponding session still exists in Redis.
- Do not assume a single key's TTL always equals `spring.session.timeout` at every instant: Spring Session may use auxiliary keys/different expiration strategies; understand the running repository version.
- `maxmemory-policy` and eviction can drop sessions prematurely. A policy that does not proactively evict sessions, paired with capacity headroom and low-memory alerts, is generally better when sessions back authentication; `noeviction` causes writes to fail when memory fills, so alerting and capacity planning remain mandatory.
- Spring Session Redis's default serialization may use Java Serialization. Multi-version rolling deployments must check deserialization compatibility (class names, `serialVersionUID`, principal/authorities structure). If choosing a JSON serializer, configure security type mappings/allowlists compatible with `SecurityContext`; never enable unrestricted polymorphic deserialization.

### 6.2. Redis HA, Failover, and Limitations

A standalone Redis is a single point of failure. Environments requiring high availability typically use managed Redis HA, Sentinel, or Cluster matching their driver/architecture. The app must point to the proper endpoint or topology; never hardcode an old master's address when failover is managed dynamically.

Redis replication is usually asynchronous; after failover, there may be a small window where recent updates are lost. Consequently, some brand-new sessions or logouts might not yet exist on the promoted replica. For strict security requirements, define supplementary consistency/revocation models rather than assuming Redis replication guarantees synchronous transactional auth state.

`RedisIndexedSessionRepository` and its reactive indexed variant add secondary indexes/events; do not enable them just to make "Redis look more production-ready." If querying sessions by principal or handling expired events, study Pub/Sub limits, Redis Cluster node behavior, and expiration event semantics carefully. Never rely on expiration events as the sole trigger for second-accurate business rules.

### 6.3. How to Fail Closed When Redis Errors

When a request requires a session and Redis cannot read/write, that is an **infrastructure dependency failure**. Never fall back to a local `ConcurrentHashMap` or synthesize an arbitrary `SecurityContext` just to "keep returning 200." Nor should you swallow Redis errors into `Mono.empty()` and treat the user as cleanly logged out: that masks incidents, skews observability, and can create unexpected security paths.

Operational strategy:

1. Bound timeouts, connections, and retries cleanly. Use short retries with backoff/jitter for transient errors while respecting the overall request deadline; unbounded retries multiply load on an overloaded Redis.
2. Endpoints requiring session authentication must never execute privileged actions without successfully retrieving/verifying the session. Return a controlled error (e.g., HTTP **503** if the app defines this error mapping) with `Retry-After` when appropriate; in practice the framework may return a different **5xx** if unconfigured. Never claim Spring automatically returns 503 by default.
3. Distinguish Redis errors from `401/403`: 401/login redirects reflect missing or expired sessions, 403 reflects insufficient authority/CSRF; Redis timeouts are dependency failures and must be tracked separately.
4. Readiness should reflect ability to serve Redis-dependent business traffic; liveness should not necessarily fail on brief Redis blips, avoiding restart storms. Design health/readiness with clear policies so all replicas do not drop from the LB unnecessarily if doing so worsens the outage.
5. Resume traffic only once connections, session operations, and LB routing stabilize. Users may need to log in again if sessions were lost to failover/eviction; state this clearly instead of assuming every session survives.

## 7. Production Redis Incident Runbook

**Step 1 — Identify symptoms and blast radius.** Distinguish: users log in on node A then get redirected to `/login` on B; endless login loops; rising 5xx; hanging requests; or mass session loss after failover. Record timestamp, namespace, environment, app/Redis nodes, deployed version, and LB status; never paste raw cookies/session IDs into tickets/logs.

**Step 2 — Inspect application and network path.** Check health, Lettuce connection/command timeouts, DNS/TLS/ACL, shared Redis config across replicas, serialization/deserialization logs, and proxy cookie behavior. If one replica has a mismatched namespace, roll back/fix that replica's config via deployment workflows; do not wipe all of Redis.

**Step 3 — Inspect Redis non-intrusively.** Use appropriate read/observability privileges (commands illustrate local Redis; adjust TLS/ACL/port for real environments):

```bash
redis-cli -h localhost -p 6379 PING
redis-cli -h localhost -p 6379 INFO replication
redis-cli -h localhost -p 6379 INFO memory
redis-cli -h localhost -p 6379 INFO stats
redis-cli -h localhost -p 6379 INFO persistence
redis-cli -h localhost -p 6379 SLOWLOG GET 10
```

`PONG` only proves reachability to one Redis endpoint; it is **insufficient** to conclude all session reads/writes and auth flows are healthy. Inspect `role`, replication lag, `used_memory`, `maxmemory`, `evicted_keys`, `expired_keys`, rejected connections, command latency, slowlog, and CPU/network. `SLOWLOG` may contain sensitive command arguments; restrict read access and never copy it verbatim into public logs.

When inspecting a key in a test environment, use `SCAN` rather than `KEYS *`:

```bash
redis-cli -h localhost -p 6379 \
  --scan --pattern 'spring:session:reactive-demo:sessions:*'
```

For a session ID safely identified via internal tooling, check TTL under the exact namespace:

```bash
redis-cli -h localhost -p 6379 \
  TTL 'spring:session:reactive-demo:sessions:<session-id>'
```

`TTL = -2` means the key does not exist, `TTL = -1` means no expiration is set, and non-negative values are remaining seconds. A missing key may result from expiry/eviction/logout/namespace mismatch—do not jump to "Redis lost sessions" from a single check. Minimize reading sensitive session payloads; sessions may contain principals/user metadata.

**Step 4 — Triage by symptom:**

| Symptom | Likely Cause | Verification and Remediation |
| --- | --- | --- |
| Logged out only when hitting replica B | B is not using Redis Spring Session, wrong namespace, wrong cookie, or serializer | Diff deployed configs; replay same cookie across A/B, inspect session read errors |
| Login repeatedly redirects to `/login` | Browser not saving/sending cookie, `Secure` over HTTP, wrong domain/path/SameSite, wrong proxy `X-Forwarded-Proto` | Inspect Set-Cookie/request Cookie in DevTools and redirect locations without dumping cookie values |
| Sudden spike in 401/login redirects while Redis is up | Session keys expired TTL, eviction, namespace/schema change, logout, lost cookies | Check `evicted_keys`, TTL, recent deployments, and session policies |
| Elevated 5xx and Lettuce timeouts | Redis overloaded, network/TLS/DNS, unavailable connections, failover | Check latency, connection errors, HA endpoints, timeouts, and backoff |
| `READONLY You can't write against a read only replica` | Writing to a replica or stale failover topology | Fix endpoint/Sentinel/Cluster topology and write permissions; never force writes to replicas |
| `NOAUTH`/`WRONGPASS`/`NOPERM` | Wrong/rotated ACL, user, or secret / missing command permissions | Check secret rotation, ACLs, TLS, and required command permissions |
| `OOM command not allowed` | Redis hit `maxmemory`, `noeviction` fails writes | Expand capacity, reduce session payload/TTL appropriately, alert; never mass-delete |
| `ClassNotFoundException`/deserialization errors | Old/new app versions incompatible with stored Redis objects | Design serialization migration/compatibility; roll out carefully |
| 403 on POST after login | Missing/wrong CSRF token, inconsistent session, origin/cookie policy | Compare form/header token and session; never disable CSRF to hide bugs |
| Connection/CPU spike during slow Redis | Retry storms, wrong pool/timeouts, expensive commands | Bound retries, curb thundering herds, scale/repair backend |

**Step 5 — Controlled recovery.** If a Redis endpoint failed, switch to the healthy HA node/endpoint per runbook. If out of memory, scale capacity and audit policies; if a new config broke namespace/serializer, roll back to a compatible version/config. After failovers that lose session data, accept re-authentication as needed and communicate clearly to users. Never run `FLUSHALL`, `FLUSHDB`, `KEYS * | DEL`, or manually edit `sessionAttr:*` values as a standard fix.

**Step 6 — Post-incident verification.** Re-run node-switching, login/logout, expiry, and temporary Redis outage checks; measure 401/403/5xx rates and Lettuce errors post-recovery. Classify root cause: network, topology, capacity, serializer, app, cookie, or CSRF. Record action items with owners and alert thresholds.

## 8. Observability, SLOs, and Redis Security

To detect issues early, monitor at minimum:

- **App/Security:** login success/failure rates; redirect loops; HTTP 401/403/5xx; p95/p99 latency on session-dependent endpoints; session create/read/save/delete error counts; version-tagged serialize/deserialize errors.
- **Redis client:** connection failures, reconnects, command timeouts, pool saturation (if pooling), GET/HSET/EXPIRE command durations, retry counts, and queue depth.
- **Redis/HA:** memory usage, evictions, expired keys, connected clients, ops/sec, replication lag, failovers, `READONLY`/ACL errors, and management endpoint health.
- **Load balancer:** upstream 5xx, healthy backends, latency, drained connections, A/B routing ratios in tests.
- **Security:** TLS to Redis, least-privilege ACLs, never expose Redis directly to the Internet, rotate secrets, isolate namespaces across production/staging and distinct apps. Never write session IDs, cookie values, session payloads, or passwords into logs/traces. Where policy requires request correlation, hash/pseudonymize session IDs.

**Readiness** should reliably verify the service can handle session-dependent requests. Actuator's Redis health indicator can contribute to a health group; verify your probe config and actual deployment rather than assuming it is automatically inside the readiness group. **Liveness** signals whether the app itself can recover; do not tie liveness restarts to every transient Redis error.

## 9. Pre-Deployment Integration Testing

A useful staging environment has at least two instances sharing one test Redis, load balancing without session affinity, and the ability to inject Redis failures. Verify these criteria with real browsers or HTTP-level integration tests:

| Scenario | How to Execute | Expectation |
| --- | --- | --- |
| Node switch after login | Log in on A; reuse same cookie to call `/whoami` on B | B authenticates the same user with no re-login |
| Pod restart | Log in, replace A, call B | Session survives as long as Redis retains data |
| Continuous load balancing | Hit protected endpoint repeatedly via LB, observe instance IDs | Authority never drops across replica hops |
| Logout | Log out on A then send old cookie to B | Access to protected content is denied |
| Expiry | Use a short test-only timeout, idle past limit, call again | Re-authentication required; no synthesized authority |
| Redis connection loss | Block/stop test Redis mid-session | Redis-dependent requests never succeed with fake authority; dependency error logged |
| Redis recovery | Restore connection, check health and requests | Controlled recovery; sessions survive or require re-login per persistence/HA |
| Dual-version rolling deploy | Rolling upgrade altering session classes | Zero deserialize/`ClassNotFoundException` errors |
| Tampered/stolen cookie | Mutate random ID or drop cookie; run authorized security tests | Invalid IDs rejected; cookies protected by TLS, Secure, HttpOnly, and CSRF |
| Concurrent requests | Two requests mutate session attributes concurrently | Last-write/conflict semantics understood; session never used as business source of truth |
| Redis failover | Trigger primary switchover via test HA | Driver reconnects and requests handle safely, alerting if sessions were lost |

For WebFlux, `WebTestClient` can test application-level authorization/CSRF; **to prove real session sharing across replicas**, you need two application contexts/processes (or two server instances) and **real Redis in tests** such as a test container, because `WebTestClient` bound to one context or `mockAuthentication()` does not prove replication. Spring Session does not replace testing the cookie path through a load balancer.

A dangerous mistake is logging in on A and only asserting HTTP 200 on A; it misses that B is using a local session repository. Another mistake is using `mockUser()`/`mockAuthentication()` to fake login on B: the test passes even when Redis is completely down because identity was injected directly.

## 10. Secure Deployment Checklist

1. Every WebFlux instance runs **Spring Session + reactive Redis** with identical namespace/serializer and no accidental Servlet-style `HttpSession` filters.
2. The load balancer checks readiness, enforces TLS, forwards accurate headers from a trusted proxy, drains connections on rollout, and does not rely on stickiness for session survival.
3. Session ID cookies set `HttpOnly`, `Secure` in production, `SameSite`, and accurate domain/path; tested against a production-like domain. CSRF stays enabled for form login/cookie auth.
4. Redis has proper capacity, TTL, eviction policy, isolated internal network, TLS, ACL/secret rotation, HA, and failover plans; replication consistency limits are accounted for.
5. Session payloads are minimal and upgrade-compatible; no long-lived secrets, large objects, or critical business state stored in sessions.
6. Redis failures are treated as infrastructure errors with bounded timeouts and fail-closed behavior. Never fall back to in-memory sessions or skip auth checks.
7. Monitoring/alerts and runbooks distinguish cookie, CSRF, Redis, topology, serializer, and deploy failures. Node switching, logout, expiry, Redis outage, and recovery are all tested.

## Official Reference Documentation

- Spring Boot 3.5 — Spring Session (reactive auto-configuration): https://docs.spring.io/spring-boot/3.5/reference/web/spring-session.html
- Spring Boot 3.5 — Common Application Properties (`spring.session.*`, `spring.data.redis.*`): https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
- Spring Session — WebSession Integration: https://docs.spring.io/spring-session/reference/web-session.html
- Spring Session — `ReactiveSessionRepository`, `@EnableRedisWebSession`: https://docs.spring.io/spring-session/reference/api.html
- Spring Session — Redis configuration, serialization, namespace: https://docs.spring.io/spring-session/reference/configuration/redis.html
- Spring Session — Common Configuration (`CookieWebSessionIdResolver`): https://docs.spring.io/spring-session/reference/configuration/common.html
- Spring Security — CSRF for WebFlux: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Security — `WebSessionServerSecurityContextRepository`: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html
