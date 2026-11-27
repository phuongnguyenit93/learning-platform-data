# Spring Session and Session Sharing Across Multiple Replicas

## 1. The Problem: A User Moves from Gateway A to Gateway B

A **Spring Cloud Gateway** deployment may start as a single process handling every request. As traffic grows, the operations team deploys two or more Gateway replicas behind a load balancer:

~~~text
Browser ──> Load Balancer ──> Gateway A ──> microservices
                         └──> Gateway B ──> microservices
~~~

If Gateway A stores login session data in **its own process memory**, a subsequent request routed by the load balancer to Gateway B may fail to find the session. The user just logged in on A, yet on B appears unauthenticated. One solution is storing session data in a **shared store** so both A and B read/write under the same session ID.

**Spring Session** integrates with Spring WebFlux via `WebSession` and `WebSessionManager`, and can use Redis as a shared session store. This lesson belongs to the **Sessions and Tokens** chapter of the **SPRING_CLOUD_GATEWAY** module. It connects running multiple Gateway replicas with route predicates, filter chains, path/header transforms, service discovery, authentication, rate limiting, circuit breakers, retries, TLS, and request observability.

After this lesson, you will:

1. Distinguish **session cookie, session ID, session data, access token**, and sticky sessions.
2. Understand why Spring Session + Redis allows multiple Gateway replicas to share state.
3. Distinguish Spring WebFlux `WebSession` from Servlet `HttpSession`; avoid inappropriate annotations/modules.
4. Configure different Spring Boot / Spring Cloud Gateway versions without mixing namespaces.
5. Run **two Gateway processes sharing one Redis**, testing cookie jars, cross-replica counters, timeouts, and logout.
6. Know when to use `SaveSession` to persist a session before the Gateway forwards a request.
7. Evaluate production risks: cookies, serialization, consistency, Redis outages, security, and observability.

> **Scope:** This lesson focuses on **Spring Cloud Gateway Server WebFlux**. Lab session examples store only a counter to verify state sharing; **they are not a real login system and do not prove callers are authenticated**.

## 2. Distinguishing Sessions and Tokens Before Designing

| Component | Example | Who Holds and Verifies It? |
|---|---|---|
| **Session ID** | Long server-generated random identifier | Client sends it back via cookie; Gateway looks up the matching key |
| **Session cookie** | `Set-Cookie: SESSION=...; Path=/; HttpOnly; Secure` | Browser stores per host/path/scheme and sends `Cookie: SESSION=...` |
| **Session data** | Verified authentication details, CSRF state, or small state | Server/Gateway stores in Redis via Spring Session |
| **Access token** | `Authorization: Bearer ...` | Resource Server validates token per standard; may not use sessions |
| **Refresh token** | Credential used to request new access tokens | Must be stored and protected separately; not identical to a session ID |
| **Sticky session** | LB prefers routing the same client to the same replica | LB routing behavior, not a session store |

A model using **session cookies** can work like this:

1. The user logs in; Spring Security verifies credentials.
2. The Gateway generates/rotates a secure session ID and saves the associated authentication state inside `WebSession`.
3. Spring Session writes session data under the session ID into Redis.
4. The browser holds only a cookie containing the **session ID**, not the full authentication state directly.
5. Subsequent requests hitting any Gateway replica use the cookie to load the same session from Redis.

Meanwhile, for a **purely stateless Bearer JWT** API, every request carries a JWT and the Gateway validates signatures/claims; **Spring Session is not necessarily needed**. Do not add Redis sessions to every API merely because multiple replicas exist.

### Tokens do not turn into sessions on their own

JWT access tokens and session IDs can both be viewed as credentials users must protect, yet their mechanisms differ:

- A **signed JWT** can be verified offline using public keys, issuer, audience, and expiration; immediate revocation usually requires additional design.
- A **Session ID** typically references server-side state; invalidating the session record can invalidate the credential across all replicas.
- **Spring Session** shares the application's `WebSession`; it **does not turn JWT tokens into session cookies**, does not authenticate users on its own, and does not grant business permissions.

## 3. Multi-Gateway Architecture with Redis

~~~mermaid
flowchart TD
    C["Browser<br/>Cookie: SESSION=opaque-id"] --> L["Load Balancer / Ingress<br/>Public HTTPS"]
    L --> A["Gateway replica A<br/>WebFlux + Spring Session"]
    L --> B["Gateway replica B<br/>WebFlux + Spring Session"]
    A <-->|"ReactiveSessionRepository"| R[("Redis<br/>shared session store")]
    B <-->|"ReactiveSessionRepository"| R
    A --> S["Microservices"]
    B --> S
~~~

**Conditions for a session to work on both A and B:**

- Both replicas use the **same Redis service/cluster and same session namespace**.
- Both replicas run **compatible Spring Session versions and session attribute serializers**.
- The client sends the **same session cookie** to the public URL without inadvertently altering cookie name/Path/Domain.
- The session has not expired or been invalidated; Redis connectivity and security policies remain valid.
- Both replicas share compatible authentication configs, session timeouts, encryption, and deployment policies.

**Sticky sessions are not required to share state if all replicas read the same session store**, though sticky sessions are sometimes enabled for optimization or other infrastructure reasons. Sticky sessions **alone** cannot solve restarts, autoscaling, or replica loss: if sessions live only in A's RAM, when A dies the session is still lost.

### 3.1. HTTP lifecycle of a session

~~~mermaid
sequenceDiagram
    participant C as Browser
    participant L as Load Balancer
    participant A as Gateway A
    participant R as Redis
    participant B as Gateway B

    C->>L: POST /lab/session/increment
    L->>A: Request without cookie
    A->>R: Create session + counter=1
    R-->>A: Save succeeded
    A-->>C: 200 + Set-Cookie: SESSION=...
    C->>L: POST /lab/session/increment<br/>Cookie: SESSION=...
    L->>B: Route to replica B
    B->>R: Load session by ID
    R-->>B: counter=1
    B->>R: Write counter=2
    B-->>C: 200 + counter=2
~~~

Key point: **Redis stores session attributes, not the browser cookie itself**. The cookie carries the ID locating the record; each Gateway queries Redis via Spring Session when processing requests.

## 4. How Does Spring Session Replace WebSession?

In **Spring WebFlux**, the standard API is `WebSession`. Applications retrieve the session via `ServerWebExchange.getSession()` or declare a `WebSession` parameter in a controller. Spring Session plugs in a `WebSessionManager` backed by `ReactiveSessionRepository`; for Redis, an appropriate reactive implementation is used.

| Spring WebFlux / Gateway | Servlet Spring MVC | Notes |
|---|---|---|
| `WebSession` | `HttpSession` | Two different application stacks |
| `WebSessionManager` | `SessionRepositoryFilter`/Servlet session | Different integration mechanisms |
| `ReactiveSessionRepository` | `SessionRepository` | Reactive API returns `Mono`/publishers |
| `@EnableRedisWebSession` | `@EnableRedisHttpSession` | Use only the reactive variant for Gateway WebFlux if configuring manually |
| `CookieWebSessionIdResolver` | `DefaultCookieSerializer`/Servlet cookie integration | Cookie configuration also differs |

Modern Spring Boot lines provide **Spring Session auto-configuration** once the dependency and a matching Redis connection factory are on the classpath. Under standard auto-configuration, **adding `@EnableRedisWebSession` is not mandatory**. If you manually declare the annotation to customize the repository, Boot may back off auto-configuration, requiring you to manage the corresponding configuration explicitly.

**Do not block the reactive thread:** never call `block()` to read Redis sessions on the Netty event loop, and never use Servlet `HttpSession` as a workaround in Gateway WebFlux. Use the reactive APIs of Spring Session/WebFlux.

### 4.1. Redis is a state store, not a default JWT vault

Spring Session typically stores serialized attributes keyed by session ID. Never stuff request/response objects, streams, connections, secrets, or large payloads into sessions. Stored objects must use a clean, stable format that survives rolling application upgrades.

Reading/writing sessions via Redis also incurs **network I/O, latency, connection errors, and memory overhead**. A stateless JWT architecture avoids those costs, while facing different revocation/rotation challenges. Choose your model based on business requirements, not trends.

## 5. Choosing the Right Versions, Dependencies, and Configuration

### 5.1. Spring Cloud Gateway Server WebFlux 4.2/4.3 with Spring Boot 3.x

When using Spring Boot 3.5 and compatible Gateway WebFlux 4.3 via the Spring Cloud BOM, typical Maven dependencies are:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.session</groupId>
        <artifactId>spring-session-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis-reactive</artifactId>
    </dependency>
</dependencies>
~~~

Declare a Spring Cloud BOM compatible with your chosen Spring Boot version; never mix arbitrary Gateway and Boot versions by guesswork. Newer Gateway starters may use `spring-cloud-starter-gateway-server-webflux`; verify against your release.

With Boot 3.x, the standard Redis session namespace property is `spring.session.redis.namespace`:

~~~yaml
server:
  port: ${GATEWAY_PORT:8081}

spring:
  application:
    name: shared-session-gateway
  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
  session:
    timeout: 20m
    redis:
      namespace: spring:session:gateway-lab

demo:
  replica-id: ${REPLICA_ID:A}
~~~

In this lab, Gateway A and B share **the same `application.yml`** while passing different `GATEWAY_PORT`/`REPLICA_ID` values. They must share identical Redis host/port and namespace settings.

### 5.2. Spring Cloud Gateway Server WebFlux 5.x with Spring Boot 4.x

Spring Boot 4.x provides a dedicated starter for Spring Session Redis and updates several configuration namespaces. Sample dependencies for Boot 4.x + Gateway WebFlux 5.x:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-session-data-redis</artifactId>
    </dependency>
</dependencies>
~~~

Spring Boot can auto-configure reactive Redis sessions with the right starter without necessarily adding `@EnableRedisWebSession`. The Redis session namespace property in Boot 4.x is **`spring.session.data.redis.namespace`**:

~~~yaml
server:
  port: ${GATEWAY_PORT:8081}

spring:
  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
  session:
    timeout: 20m
    data:
      redis:
        namespace: spring:session:gateway-lab

demo:
  replica-id: ${REPLICA_ID:A}
~~~

**Do not mix** `spring.session.redis.namespace` (Boot 3.x) with `spring.session.data.redis.namespace` (Boot 4.x) assuming both are read. Both examples are **separate version-specific choices**, not two YAML blocks to paste into the same app.

| Component | Boot 3.5 + Gateway WebFlux 4.3 | Boot 4.x + Gateway WebFlux 5.x |
|---|---|---|
| Common Gateway starter | `spring-cloud-starter-gateway` | `spring-cloud-starter-gateway-server-webflux` |
| Route namespace | `spring.cloud.gateway.routes` | `spring.cloud.gateway.server.webflux.routes` |
| Sample Redis session dependencies | `spring-session-data-redis` + reactive Redis starter | `spring-boot-starter-session-data-redis` |
| Session timeout | `spring.session.timeout` | `spring.session.timeout` |
| Redis session namespace | `spring.session.redis.namespace` | `spring.session.data.redis.namespace` |
| Redis host | `spring.data.redis.host` | `spring.data.redis.host` |

These choices follow documentation for their **respective lines** and do not replace checking the compatibility matrix and configuration metadata of your exact patch release.

### 5.3. Manual annotation configuration when needed

If you specifically prefer not to rely on Spring Boot auto-config, you can write:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.annotation.web.server.EnableRedisWebSession;

@Configuration(proxyBeanMethods = false)
@EnableRedisWebSession(
        redisNamespace = "spring:session:gateway-lab",
        maxInactiveIntervalInSeconds = 1200)
class RedisWebSessionConfiguration {
}
~~~

This snippet assumes a **`ReactiveRedisConnectionFactory`** already exists (created by Boot from `spring.data.redis.*` or defined explicitly). When using the annotation, session repository configuration may prioritize annotation attributes over auto-config properties; **do not combine both approaches expecting all properties to behave identically**.

In the lab below, **prefer Boot auto-configuration** and omit the annotation class above.

## 6. Lab: Running Two Gateway Replicas Sharing One Redis

This lab **needs no Authorization Server or backend microservice** to prove session sharing. We create a diagnostic API directly on the Gateway to read and write a counter in `WebSession`. When working, the response reveals which replica handled the request.

### 6.1. Prerequisites

- A Gateway Server WebFlux project with dependencies and `application.yml` for **one** of the version lines in section 5.
- Redis running at `localhost:6379` reachable by both Gateway processes.
- Compatible Java, Maven/Maven Wrapper, and Spring Cloud BOM.
- Two free ports `8081` and `8082` on the test machine.

If using Docker for local Redis:

~~~bash
# Lab Redis, never exposed to the public Internet:
docker run --rm --name redis-session-lab \
  -p 127.0.0.1:6379:6379 redis:7
~~~

If Docker or the image is unavailable, use a locally installed Redis or a managed test Redis. **Never use a public production Redis, and never disable authentication/network protections just to run a lab.** When the two Gateways run in separate containers, `localhost` inside each container refers to that container itself; replace the Redis host with the proper service/container DNS name.

### 6.2. Creating the Gateway application

`src/main/java/demo/gateway/SessionGatewayApplication.java`:

~~~java
package demo.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionGatewayApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionGatewayApplication.class, args);
    }
}
~~~

### 6.3. Controller using WebSession

`src/main/java/demo/gateway/SessionLabController.java`:

~~~java
package demo.gateway;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.WebSession;
import reactor.core.publisher.Mono;

@RestController
public class SessionLabController {

    private final String replicaId;

    public SessionLabController(
            @Value("${demo.replica-id:A}") String replicaId) {
        this.replicaId = replicaId;
    }

    @PostMapping("/lab/session/increment")
    public Mono<Map<String, Object>> increment(WebSession session) {
        session.start();
        int previous = session.getAttributeOrDefault("counter", 0);
        int current = previous + 1;
        session.getAttributes().put("counter", current);

        // Do not expose session.getId() externally: it is a credential.
        return Mono.just(Map.of(
                "replica", replicaId,
                "counter", current));
    }

    @GetMapping("/lab/session")
    public Mono<Map<String, Object>> read(WebSession session) {
        int count = session.getAttributeOrDefault("counter", 0);
        return Mono.just(Map.of(
                "replica", replicaId,
                "counter", count));
    }

    @PostMapping("/lab/session/logout")
    public Mono<Void> logout(WebSession session) {
        return session.invalidate();
    }
}
~~~

In the `increment` endpoint, updating the attribute marks `WebSession` as dirty/needing persistence; Spring Session persists it within the request lifecycle. The `read` endpoint only reads state; if no session has ever been created, it sees `counter=0`.

**Important note:** Incrementing a counter via **read → increment → write** in a session suffices for a sequential lab, **not as an atomic update** when two concurrent requests hit two replicas. Production systems must guard against *lost updates* if the same session can be mutated concurrently.

### 6.4. Running Gateway A and Gateway B

Two Bash terminals in the **same project**:

~~~bash
# Terminal A
GATEWAY_PORT=8081 REPLICA_ID=A ./mvnw spring-boot:run

# Terminal B
GATEWAY_PORT=8082 REPLICA_ID=B ./mvnw spring-boot:run
~~~

Or in two PowerShell windows:

~~~powershell
# Window A
$env:GATEWAY_PORT = "8081"
$env:REPLICA_ID = "A"
.\mvnw.cmd spring-boot:run

# Window B
$env:GATEWAY_PORT = "8082"
$env:REPLICA_ID = "B"
.\mvnw.cmd spring-boot:run
~~~

Both processes must connect to the **same Redis** and run with the **same session namespace**. Two ports in the lab stand in for placing a LoadBalancer in front of the Gateway. This lets you explicitly target A or B without configuring sticky routing.

### 6.5. Creating a session on replica A

~~~bash
curl -i -X POST "http://localhost:8081/lab/session/increment" \
  -c session-jar.txt
~~~

**Expected** response:

~~~http
HTTP/1.1 200 OK
Set-Cookie: SESSION=<opaque-random-value>; Path=/; HttpOnly; SameSite=Lax
Content-Type: application/json

{"replica":"A","counter":1}
~~~

Actual `Set-Cookie` attributes depend on WebFlux/Spring Session version and cookie configuration; do not compare attribute order verbatim. What matters is that `curl -c session-jar.txt` saved the session ID and the JSON returned `counter=1`.

### 6.6. Reading and incrementing on replica B with the same cookie

~~~bash
# B must see the state saved by A:
curl -i "http://localhost:8082/lab/session" \
  -b session-jar.txt

# B increments from 1 to 2:
curl -i -X POST "http://localhost:8082/lab/session/increment" \
  -b session-jar.txt -c session-jar.txt

# A reads again:
curl -i "http://localhost:8081/lab/session" \
  -b session-jar.txt
~~~

| Call | Replica | Expected Value |
|---|---|---|
| POST increment without cookie | A (8081) | `counter=1`, response includes `Set-Cookie` |
| GET with saved cookie | B (8082) | `counter=1` |
| POST increment with cookie | B (8082) | `counter=2` |
| GET with cookie | A (8081) | `counter=2` |
| GET **without cookie** | A or B | `counter=0`, not the old session |

**Why does the cookie jar work across both ports?** Cookies are not scoped by port; `localhost:8081` and `localhost:8082` share the same hostname `localhost` and path `/`. In production, browsers normally see only one public load-balancer hostname while multiple replicas sit behind it.

Test strictly in the **sequential order** shown in the table first; avoid firing concurrent updates while confirming basic session persistence.

### 6.7. Invalidating on B and re-checking A

~~~bash
curl -i -X POST "http://localhost:8082/lab/session/logout" \
  -b session-jar.txt -c session-jar.txt

curl -i "http://localhost:8081/lab/session" \
  -b session-jar.txt
~~~

After `session.invalidate()`, the old session record is invalidated per repository mechanics; subsequent requests carrying the old ID should no longer retrieve `counter=2`, typically observing `counter=0`. Depending on resolver/version, the old cookie may be cleared on the response or updated in the cookie jar. Test against your actual runtime rather than guessing solely from the logout status code.

In real login systems, **logout** may also need to revoke access/refresh tokens, expire cookies with matching `Path`/`Domain`, destroy server sessions, and clean up related app state. The lab example only invalidates `WebSession`.

## 7. Session Cookies: Keeping What the Browser Holds Consistent

Browsers match cookies based on the **public URL**, never seeing internal backend or Redis addresses. If a load balancer exposes `https://api.example.test`, all Gateway replicas must agree on cookie name, `Path`, `Domain`, `SameSite`, and `Secure`.

| Attribute | Recommendation and Meaning |
|---|---|
| **Cookie name** | Commonly `SESSION`; must match across replicas to look up the same ID |
| **Host / Domain** | Prefer host-only cookies; avoid overly broad domains |
| **Path** | Match the public path called by browsers, e.g., `/` or `/api` if required |
| **Secure** | Required on public HTTPS; never rely on internal HTTP hops to decide whether the browser uses HTTPS |
| **HttpOnly** | Restricts JavaScript from reading the session ID, though it does not prevent CSRF |
| **SameSite** | Typically `Lax`/`Strict` per flow; `None` requires `Secure` and remains subject to third-party cookie policies |
| **Max-Age/Expires** | Governs client cookie lifetime; not identical to Redis session record TTL |

### 7.1. Customizing cookies in WebFlux

Spring Session WebFlux uses `WebSessionIdResolver`, typically defaulting to `CookieWebSessionIdResolver`. You can declare a bean **when needed for production HTTPS**:

~~~java
package demo.gateway;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration(proxyBeanMethods = false)
public class WebSessionCookieConfig {

    @Bean
    WebSessionIdResolver webSessionIdResolver() {
        CookieWebSessionIdResolver resolver =
                new CookieWebSessionIdResolver();

        resolver.setCookieName("__Host-SESSION");
        resolver.addCookieInitializer(builder ->
                builder.path("/")
                        .secure(true)
                        .httpOnly(true)
                        .sameSite("Lax"));
        return resolver;
    }
}
~~~

The `__Host-` prefix requires the cookie to be set over HTTPS, with `Secure`, `Path=/`, and **no `Domain`**. This configuration **will not work as-is on an HTTP localhost lab** if the browser/cookie jar rejects `Secure` cookies over plain HTTP; test it in an HTTPS environment or omit this bean from the local lab.

For **Servlet Spring Session**, `DefaultCookieSerializer` is used, so **never copy Servlet code into Gateway WebFlux**. If multiple apps share one host through the Gateway, check for cookie name and path collisions.

### 7.2. Cookies are not shared across arbitrary domains

A cookie for `api.example.test` is not automatically sent to `service.internal` or `auth.other-example.test`. If the Gateway holds sessions in Redis, backend microservices **do not automatically know about that session** merely because the Gateway proxied an HTTP request to them. An architecture where backends share the same session store is possible, but requires explicitly designing cookies/namespaces/serializers/security boundaries and never treating one app's session data as automatic authorization in another app.

Similarly, if the Gateway strips `/api` with `StripPrefix`, the path seen by the backend differs from the path called by the browser. Cookie `Path` is **evaluated by the browser against the public URL**, not the rewritten path.

## 8. SaveSession GatewayFilter Factory: When to Use It?

Spring Cloud Gateway Server WebFlux provides the **`SaveSession` GatewayFilter Factory**. Spring documentation describes it as forcing **`WebSession.save()` before forwarding the request downstream**, useful when Spring Session uses a lazy persistence mechanism and modified state must be flushed before downstream runs.

### 8.1. Configuration for Gateway WebFlux 4.2/4.3

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: session-aware-api
          uri: http://localhost:9091
          predicates:
            - Path=/api/**
          filters:
            - StripPrefix=1
            - SaveSession
~~~

### 8.2. Configuration for Gateway WebFlux 5.x

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: session-aware-api
              uri: http://localhost:9091
              predicates:
                - Path=/api/**
              filters:
                - StripPrefix=1
                - SaveSession
~~~

This is a **separate proxy route example**; a backend at `localhost:9091` must be running to call the route. The counter lab in section 6 uses an internal controller and **does not need `SaveSession`** to demonstrate session sharing: Spring Session already saves the session during the WebFlux request lifecycle.

**`SaveSession` is not**:

- An authentication mechanism or automatic session creator for every request.
- A tool for encrypting sessions, refreshing tokens, or issuing access tokens.
- A command that shares Redis across Gateways: that is done by **Spring Session repositories + shared configuration**.
- A way to pass full authentication state to backends: `WebSession.save()` only ensures data is saved; downstream still needs its own mechanism to consume data or receive verified identity over a trusted channel.

When combining Spring Security and Spring Session, state-save ordering can matter, especially when downstream reads that saved state too. Verify your version's filter chain rather than treating `SaveSession` as a universal fix for every race condition.

## 9. Session Timeout, Redis TTL, and Invalidation

### 9.1. Inactivity timeout differs from cookie expiration

`spring.session.timeout: 20m` in the example specifies the **inactivity duration** before expiration per Spring Session policy. It does not necessarily set `Max-Age=1200` on the cookie; many session cookies are deleted by the browser when closed, whereas Redis records carry their own TTL.

Example:

~~~text
10:00  Session created, 20-minute timeout
10:05  Valid request updates lastAccessedTime
10:25  Session expires if inactive for a full 20 minutes
~~~

Exact Redis key deletion timing also depends on Spring Session's TTL/expiration mechanism, latency, and caches. Do not build security guarantees assuming a key vanishes **to the exact millisecond** after expiration.

### 9.2. Logout on one replica affects other replicas

If A and B read the same session key, logout/invalidation on A prevents B from reusing the old session once state updates; subsequent requests to B are re-evaluated. For real users, also verify session fixation protection, CSRF state, token revocation, and "log out from all devices" policies.

### 9.3. Inspecting Redis data in the lab

In local test Redis, use `SCAN` to inspect the namespace, avoiding `KEYS *` on large datasets:

~~~bash
redis-cli --scan --pattern 'spring:session:gateway-lab:*'
~~~

Use this only to confirm **keys exist in the namespace**; never print or paste raw serialized session attributes or real session IDs into logs or screenshots. Redis key names may embed session IDs; redact values when writing reports. In production, use proper access policies and observability tooling instead of ad-hoc key scans.

## 10. Common Pitfalls When Running Multiple Replicas

| Symptom | Possible Cause | How to Verify |
|---|---|---|
| A increments counter, B sees 0 | Different Redis endpoint/namespace, cookie not sent, incompatible serialization | Compare Redis configs, cookie jars, namespaces, and response headers |
| Page reload creates a new session | Cookie `Path`/`Domain`/`SameSite`/`Secure` mismatches public URL | DevTools Storage/Network or `curl -b/-c` |
| Switching ports in lab loses cookie | Cookie jar not reused, or hostname switched between `localhost` and `127.0.0.1` | Keep identical host and reuse cookie jar |
| Logout on A leaves B still seeing session | Replicas use different repositories, invalidation incomplete, or differing state caches | Inspect Redis/traces and follow-up requests |
| Spring Session added, yet still using RAM | Reactive dependencies/auto-config not triggered, or Servlet config used accidentally | Inspect actual `WebSessionManager` and `ReactiveSessionRepository` beans |
| Session expires too early or too late | Mismatched timeouts, clock/TTL drift, or differing cookie vs. server inactivity policies | Compare versioned properties, last-access timestamps, and Redis TTLs |
| Release upgrade breaks deserialization | Incompatible class/`serialVersion`/JSON serializer | Run rolling-upgrade tests with existing sessions; plan schema migrations |
| Sudden 5xx errors when Redis fails | Redis sits on the request critical path | Check latency, timeouts, failover, backpressure, and alerts |
| Counter is lower than concurrent POST count | Lost update from concurrent session mutations | Test concurrent requests; use atomic updates or separate business state |
| Backend misses cookie/session | Cookie scope mismatch or backend lacks shared session infrastructure | Distinguish Gateway sessions from backend sessions |
| CORS errors when sending cookies | Incorrect cross-origin credentials/`SameSite`/CORS headers | Inspect preflight, `allow-credentials`, specific `allow-origin`, and cookie flags |

### 10.1. All replicas must point to the same Redis with deliberate namespaces

For example, if A uses `spring:session:gateway-lab` and B uses `spring:session:gateway-test`, even on the same Redis server they **do not share sessions**. Conversely, two unrelated business apps sharing a namespace risk cookie name collisions and incompatible attribute deserialization. Share a namespace intentionally across replicas of the same Gateway cluster; keep unrelated apps separate.

### 10.2. Sticky sessions do not fix broken shared state

If an LB always sends one client to A, missing state on B can stay hidden. **Test A → B → A directly** as in section 6, or disable affinity in test environments to prove shared session storage genuinely works.

### 10.3. Spring Session is not a business database

Never store large shopping carts, action histories, payment records, or counters needing atomic updates as primary business data inside sessions. Redis sessions fit **small, short-lived session state**; business workflows need proper databases, locking/idempotency, and dedicated consistency guarantees.

## 11. Production Redis: Durability, Security, and Serializer Versions

A centralized Redis session store helps scale Gateways, yet becomes a **shared dependency on the request path**. If Redis fails or slows down, every replica can fail session lookups. Ensure:

1. **Redis availability:** appropriate topology (managed Redis, Sentinel/Cluster if required), monitoring replication/failover, latency, and error rates.
2. **Access restrictions:** private networking, ACLs/authentication, TLS where needed; never expose Redis to the public Internet. Load secrets from secret managers/env vars, never commit real secrets to YAML.
3. **Timeouts and backpressure:** set bounded network timeouts/connection pools; never let requests hang indefinitely. Avoid infinite retries against a failing Redis.
4. **Sensitive data:** evaluate security requirements when storing authentication state; keep session attributes/IDs out of logs and traces, and enforce deletion policies.
5. **Serialization:** depending on version/config, Spring Session Redis may default to Java serialization; review compatibility and trust boundaries, or choose a safe JSON serializer with an explicit allowlist. Replicas during rolling upgrades must read a compatible format, or plan migration/expiration of old sessions.
6. **TTL/eviction:** bound session counts, configure memory policies, and size capacity; prevent unexpected evictions that log out users en masse.
7. **Metrics:** track Redis latency, session create/read/save/delete counts, memory, keyspace, session churn, login failures, and error rates—**never put session IDs in metric labels**.

### 11.1. Be cautious with custom serializers

Spring Session lets you replace the serializer via a bean named **`springSessionDefaultRedisSerializer`**. This is useful when sharing sessions across releases; however, never deploy a Jackson serializer with **broad default typing for untrusted objects** into production without auditing deserialization risks and compatibility.

If sessions hold `SecurityContext` or Spring Security objects, the serializer must support the exact types/mixins for your Spring Security version. **Build and test these setups across rolling upgrades** rather than assuming old serialized Java classes deserialize cleanly after framework upgrades.

### 11.2. Concurrent requests do not get global transactions automatically

Two concurrent requests reading a counter and both incrementing 7 to 8 can cause a **lost update**, even when Redis is completely healthy. Spring Session shares *storage*, not automatic cross-replica locking on every session. For operations requiring strict consistency, use atomic operations, transactions, or dedicated business stores instead of racing on session attributes.

## 12. Spring Security, CSRF, Fixation, and Session Concurrency

### 12.1. Creating a session does not mean authenticated

The lab controller only creates a counter. In real login flows, Spring Security must verify credentials, manage `SecurityContext`, enforce authorization policies, and prevent **session fixation** (such as rotating session IDs when upgrading from anonymous to authenticated via supported mechanisms).

Never store an attribute `"isAdmin": true` and treat it as authorization. Backends must still enforce resource permissions; the Gateway should not grant access solely from an app-assigned header or session attribute.

### 12.2. Cookie-based authentication and CSRF

Browsers attach session cookies automatically whenever cookie scope allows. Therefore, cookie-authenticated APIs are vulnerable to **CSRF** on state-changing requests; `HttpOnly` alone does not stop CSRF. Use Spring Security CSRF protection or equivalent defenses, and audit `SameSite` and frontend workflows.

For cross-origin frontends, configure CORS to allow **specific origins** and credentials only when needed. `Access-Control-Allow-Origin: *` is invalid for credentialed responses. CORS is a browser enforcement mechanism and **does not replace** authentication or CSRF protection.

### 12.3. Multiple sessions per account and concurrent login limits

If you need to cap concurrent devices/sessions per user or support "log out everywhere", pick a Spring Session repository supporting **appropriate indexing/events** and matching Spring Security policies for your version. Do not assume a basic reactive Redis session repository automatically indexes and queries all sessions by principal.

Distinguish clearly:

- **Invalidating the current session:** `WebSession.invalidate()`.
- **Revoking all sessions for a principal:** requires indexing or a dedicated principal-keyed design.
- **Revoking JWT access tokens:** a separate problem from Spring Session requiring token revocation/introspection/short TTLs.

## 13. Relationship to Gateway Routing, Retries, Rate Limiting, and TLS

| Gateway Component | Relationship with Shared Sessions |
|---|---|
| **Route predicates** | Selects routes per request; does not create or share sessions itself |
| **`SaveSession` GatewayFilter** | Ensures the session is saved before forwarding when workflows require it |
| **`StripPrefix`/`SetPath`/`RewritePath`** | Changes the path seen by backends, while browser cookies still match public paths |
| **LoadBalancer `lb://...`** | Selects **backend service instances**, independent of the front LB choosing Gateway replica A/B |
| **Rate limiting** | Can key off verified principals; session IDs should never be exposed/logged as public rate-limit keys |
| **Retry/circuit breaker** | Does not make session or business operations atomic; retrying POSTs can duplicate side effects |
| **TLS/forwarded headers** | Secures client→Gateway HTTPS and Gateway→Redis/backend links; trust `X-Forwarded-Proto` only from trusted proxies |
| **Tracing/metrics** | Track replica ID alongside route IDs and Redis errors; never tag metrics with session IDs or tokens |

**Specifically:** if Gateway A saves a session and proxies a request to `orders-service`, Spring Session at the Gateway **does not automatically supply authentication state to `orders-service`**. To pass identity to services, explicitly design token relay, token exchange, or Gateway-verified identity headers over a secured channel. Services must never trust client-supplied `X-User-Id` headers.

## 14. Self-Practice Scenarios

**Scenario 1 — A saves counter, B returns 0:** Both point to the same Redis, yet B uses namespace `gateway-v2`. Why?

Answer: Because the namespaces differ, B looks under a different key than where A wrote. Align namespaces across the same Gateway cluster, match cookie name/scope, and re-test.

**Scenario 2 — Sticky sessions enabled, yet A restarts:** Can the client keep its session?

Answer: If A stored sessions only in RAM, the session is lost. Sticky routing does not replace a shared store. With shared Redis and an unexpired session, a healthy replica can reload the data.

**Scenario 3 — Both A and B read `counter=5` concurrently and increment:** Is the final value guaranteed to be 7?

Answer: No. Both requests can write 6, causing a lost update. A session repository does not turn read-modify-write patterns into cross-replica atomic transactions.

**Scenario 4 — Gateway uses Spring Session, but the backend needs the user ID:** Is adding `SaveSession` enough?

Answer: No. `SaveSession` ensures `WebSession` state is saved before forwarding; the backend still needs a deliberate mechanism to receive/verify identity. Never trust client-supplied headers.

**Scenario 5 — Stateless JWT access tokens with no cookies:** Is Redis Spring Session mandatory?

Answer: No. If every request authenticates via JWT and the Gateway holds no session state, a session store may be unnecessary; token revocation and authorization still must be addressed separately.

## 15. Pre-Production Checklist

- [ ] Decided clearly between **stateful sessions** and **stateless JWTs**; avoid mixing them accidentally.
- [ ] Gateway is **Server WebFlux** with WebFlux-compatible Spring Session/Redis dependencies.
- [ ] Boot/Gateway/Spring Session versions align; using the exact Boot 3.x or 4.x namespace.
- [ ] All replicas point to the same Redis, namespace, and compatible serializer; no `localhost` mix-ups across containers.
- [ ] Tested A → B → A flows with the **same cookie** without relying on sticky routing.
- [ ] Session IDs are sufficiently random, omitted from URLs/logs/metric tags, and rotated upon privilege/auth changes per policy.
- [ ] Cookies have `Path`/`Domain` matching public URLs; production enforces HTTPS, `Secure`, `HttpOnly`, and appropriate `SameSite`.
- [ ] Handled logout/invalidation and Redis timeouts; never conflate cookie expiration with server session TTL.
- [ ] Tested Redis unavailability, slow queries, failover, evictions, and rolling upgrades.
- [ ] Avoided storing large objects, secrets, or business data requiring atomic transactions inside sessions.
- [ ] Cookie-authenticated APIs enforce CSRF protection; CORS credentials are limited to explicit allowed origins.
- [ ] Backends cannot be bypassed around the Gateway; client identity headers are never trusted blindly.
- [ ] `SaveSession` is applied only where save-before-proxy ordering is needed, with full awareness of its limits.
- [ ] Metrics track per-replica/route/Redis latency and errors without logging tokens or session IDs.
- [ ] Tested concurrent requests on the same session, logout from another replica, and session revocation workflows.

## 16. Official Reference Documentation

1. [Spring Session — WebSession Integration](https://docs.spring.io/spring-session/reference/web-session.html): `WebSessionManager`, `ReactiveSessionRepository`, and integrating Redis with WebFlux.
2. [Spring Boot 3.5 — Spring Session](https://docs.spring.io/spring-boot/3.5/reference/web/spring-session.html): Spring Session auto-configuration in reactive apps.
3. [Spring Boot 4.x — Spring Session](https://docs.spring.io/spring-boot/reference/web/spring-session.html): `spring-boot-starter-session-data-redis` starter and `spring.session.timeout`.
4. [Spring Boot 3.5 — Configuration Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.session.redis.namespace`, `spring.data.redis.*`.
5. [Spring Boot 4.x — Configuration Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): `spring.session.data.redis.namespace`.
6. [Spring Session — Redis Configurations](https://docs.spring.io/spring-session/reference/configuration/redis.html): namespaces, serializers, and expiration mechanics.
7. [Spring Session — WebFlux Custom Cookie](https://docs.spring.io/spring-session/reference/guides/boot-webflux-custom-cookie.html): `WebSessionIdResolver` and `CookieWebSessionIdResolver`.
8. [Spring Cloud Gateway Server WebFlux — SaveSession](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/savesession-factory.html): saving `WebSession` before forwarding.
9. [Gateway WebFlux 4.3 — SaveSession](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/gatewayfilter-factories/savesession-factory.html): legacy routes configuration namespace.

**Takeaway:** **Spring Session + Redis lets Gateway WebFlux replicas share session data under the same session ID**, so a request hitting A and the next hitting B observe consistent state under sequential read/write conditions and healthy infrastructure. The cookie holds the **ID**, Redis holds the **state**, and `SaveSession` only assists with **save-before-forward** in workflows that require it. Sharing sessions does not grant authorization, replace cookie/CSRF/TLS security, or provide transactional consistency for business data.
