# Sharing Sessions Across Nodes with Spring Session and Reactive Redis

## Learning Objectives

In a **Spring Security - reactive** application, a user may log in through instance A while the next request is routed by a load balancer to instance B. If login state sits only in A's RAM, B will not see the `SecurityContext` and may prompt for login again. **Spring Session with reactive Redis** places `WebSession` state in a shared store so WebFlux nodes access the same session by session ID.

After this lesson in the **Sessions and Logout** group, you will be able to:

1. Explain why sessions must be shared when horizontally scaling a Spring WebFlux application.
2. Distinguish `WebSession`, `ServerSecurityContextRepository`, `ReactiveSessionRepository`, `WebSessionManager`, Redis, and the `SESSION` cookie.
3. Set up Spring Boot WebFlux using `spring-session-data-redis` and a **reactive** Redis connection.
4. Run **two application instances** on different ports, verifying the cookie is preserved and session data flows across node A -> B -> A.
5. Confirm that Spring Security form login's `SecurityContext` is loaded on node B after the user logs in on node A.
6. Understand expiration/TTL, logout, session ID rotation, concurrent session writes, serialization, Redis outages, and consistency limits.
7. Run basic automated tests with `WebTestClient`, then perform cross-node verification over real HTTP.
8. Design safe operations: namespaces, cookies, Redis ACL/TLS, deployment versioning, rate limiting, observability, and fail-closed behavior.

This guide is for **WebFlux**. Spring Session in the Servlet world also stores sessions in Redis, yet uses `HttpSession`, `SessionRepositoryFilter`, and `@EnableRedisHttpSession`; those are **not** the reactive `WebSession` APIs.

## 1. The Problem: Why Does Logging In on A and Routing to B Lose the Session?

Suppose a WebFlux service has two pods:

```text
                         Browser
                    Cookie: SESSION=S123
                              |
                              v
                       Load balancer
                         /         \
                        v           v
                  Node A           Node B
                  :8081            :8082
                     |                |
                  Memory A         Memory B
                  S123 has auth    No S123

Result: user logs in on A; subsequent request to B fails to restore
        SecurityContext if each node uses local in-memory sessions.
```

In a RAM-only model, sessions can be lost on node restart/scale-down and requests switching nodes typically receive a different session. "Sticky sessions" at the load balancer can reduce node-hopping, yet do not protect when a node dies, do not create a shared session store, and do not handle many deployment changes.

Desired architecture:

```text
                            Browser
                     Cookie: SESSION=S123
                               |
                               v
                        Load balancer
                         /          \
                        v            v
                   Node A          Node B
                   WebFlux         WebFlux
                       \             /
                        \           /
                         v         v
                       Shared Redis
                   session key for S123
                   + attributes
                   + SecurityContext

A saves data under session S123. B receives the same session ID and
loads that data from Redis. Both nodes can serve valid requests.
```

**Important:** The cookie carries only a **session identifier** used by the server to look up the session. Redis stores session data server-side rather than sending the raw `SecurityContext` to the browser. Sharing Redis does not automatically make a request "authenticated": Spring Security must still check the context and the selected chain's policy.

## 2. Classes and Roles

| Component | Which layer? | Role |
| --- | --- | --- |
| `ServerWebExchange` | Spring WebFlux | Holds HTTP request/response, exchange attributes, and access to `WebSession` |
| `WebSession` | Spring WebFlux | Session attributes map, ID, started state, `lastAccessTime`, and `maxIdleTime` |
| `WebSessionManager` | Spring WebFlux | Decides how to obtain/create/save `WebSession` for an exchange |
| `ReactiveSessionRepository<? extends Session>` | Spring Session | Creates, finds, saves, and deletes `Session`s using reactive publishers |
| `ReactiveRedisSessionRepository` | Spring Session Data Redis | Implements `ReactiveSessionRepository` using reactive Redis |
| `ReactiveRedisConnectionFactory` | Spring Data Redis | Non-blocking Redis connection via reactive APIs, typically through Lettuce |
| `ServerSecurityContextRepository` | Spring Security reactive | Saves/loads `SecurityContext` per `ServerWebExchange` |
| `WebSessionServerSecurityContextRepository` | Spring Security reactive | Stores `SecurityContext` **as an attribute of `WebSession`** |
| `ReactiveSecurityContextHolder` | Spring Security/Reactor | Propagates security context within the Reactor Context of **one request** |
| `SESSION` cookie | HTTP client | Provides the session ID so nodes locate the same session |

The two uses of the word "repository" do not perform the same job:

- `ServerSecurityContextRepository` at the **security** layer knows how to save/load Spring Security's `SecurityContext`.
- `ReactiveSessionRepository` at the **session storage** layer knows how to save/load Spring Session's `Session`, including its attributes.
- `WebSessionServerSecurityContextRepository` uses `WebSession`. When `WebSessionManager` is swapped for a Redis-backed implementation, the context inside `WebSession` is written to Redis as well.
- `ReactiveSecurityContextHolder` does not persist sessions; it supplies context to the running publisher/subscriber.

Therefore, merely adding a `ReactiveRedisTemplate` bean to the app **does not automatically share sessions**. Spring Session must be configured so `WebSessionManager` is replaced with one backed by `ReactiveSessionRepository`.

## 3. Session Path Within an HTTP Request

### 3.1. First access

```text
GET /public/touch  (no SESSION cookie yet)
        |
        v
WebSessionManager opens/creates WebSession
        |
        v
Handler sets session attribute demo.visits = 1
        |
        v
Spring Session writes session to Redis
        |
        v
Response Set-Cookie: SESSION=<session-id>
        |
        v
Browser keeps ID, does not hold demo.visits data
```

Spring Session typically **only needs to save a session when the session has been used/started and modified accordingly**; do not infer that every anonymous request creates a Redis record. In the example below, `/public/touch` explicitly calls `start()` and sets an attribute so the session has a reason to be saved.

### 3.2. Subsequent request to another node

```text
GET /public/touch  Cookie: SESSION=S123
        |
        v
Node B -> Spring Session WebSessionManager
        |
        v
ReactiveSessionRepository.findById("S123")
        |
        v
Redis returns session attributes from previous request
        |
        v
Node B updates demo.visits 1 -> 2
        |
        v
Response JSON: node-b, visits=2
        |
        v
Session is persisted per save/flush configuration
```

The exact timing of the end-of-request write is the responsibility of the `WebSession`/Spring Session infrastructure. Do not manually call `ReactiveSessionRepository.save(...)` from every controller just to ensure saving; let the framework manage `WebSession` and use `exchange.getSession()`.

### 3.3. With Spring Security form login

```text
POST /login (valid credentials + valid CSRF) on Node A
        |
        v
ReactiveAuthenticationManager authenticates
        |
        v
SecurityContext contains authenticated Authentication
        |
        v
WebSessionServerSecurityContextRepository.save(...)
        |
        v
WebSession attribute holds SecurityContext
        |
        v
Spring Session Redis-backed WebSessionManager
        |
        v
Redis writes session data
        |
        v
Browser receives current SESSION cookie
        |
        v
GET /me to Node B with same cookie
        |
        v
Redis-backed WebSession is loaded
        |
        v
WebSessionServerSecurityContextRepository.load(...)
        |
        v
ReactiveSecurityContextHolder + authorization
        |
        v
Handler on Node B sees the same principal
```

**Two distinct "loads":** Spring Session **loads `WebSession`** by ID; Spring Security **loads `SecurityContext` from `WebSession`**. When working properly, authentication survives across multiple nodes without the application sharing Java objects in RAM across processes.

## 4. Configuring Reactive Spring Session Redis with Spring Boot

With Spring Boot WebFlux 3.3.x, when Spring Session Redis is on the classpath and a reactive Redis connection is available, auto-configuration can create the appropriate `ReactiveSessionRepository` and `WebSessionManager`. **Do not manually add `@EnableRedisWebSession` in the Boot auto-config example**, because a manual annotation can make auto-configuration back off and change property-binding mechanics. For plain Java configuration without Boot auto-config, `@EnableRedisWebSession` enables the Redis-backed `WebSessionManager`.

### 4.1. Required dependencies

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
    implementation 'org.springframework.session:spring-session-data-redis'
}
```

With Boot 3.3.13, use the BOM to manage compatible Spring Session, Spring Data Redis, and Lettuce versions. Do not use synchronous `spring-boot-starter-data-redis` alone and assume every API is already reactive; verify that `ReactiveRedisConnectionFactory` and `ReactiveSessionRepository` are present.

If using a newer Boot version that ships a dedicated starter for Spring Session Redis, dependencies may be grouped under the official starter; align content and APIs with the deployed Boot version. This example pins **Spring Boot 3.3.13** for consistent dependency coordinates.

### 4.2. Properties that must match across nodes

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
  session:
    timeout: 30m
    redis:
      namespace: spring:session:webflux-lab
      flush-mode: on_save
```

Meaning:

- `spring.data.redis.host/port`: both node A and node B must point to **the same shared Redis service** (or a supported Redis HA/cluster setup).
- `spring.session.redis.namespace`: Redis key prefix dedicated to **the same application**. A and B must use the **same namespace** to see the same sessions; distinct applications should use distinct namespaces to avoid overwriting or mixing data.
- `spring.session.timeout`: maximum inactivity duration per policy; after inactivity timeout, old authentication must no longer be accepted. Read the real value from configuration/observation rather than guessing TTL from a single Redis line.
- `spring.session.redis.flush-mode=on_save`: data is written at repository/session pipeline save time rather than attempting to write every mutation immediately. Measure consistency and latency under concurrent requests.

Every node must also agree on the **session data schema version and serializer**. Sharing Redis with incompatible deserialization still causes load errors and effective session loss.

### 4.3. If configuring manually without Boot auto-config

You can declare:

```java
// Plain Java config snippet; DO NOT add alongside
// Boot auto-config in the full runnable example.
@Configuration
@EnableRedisWebSession
class RedisSessionConfig {
    // Requires a suitable ReactiveRedisConnectionFactory.
}
```

Import `org.springframework.session.data.redis.config.annotation.web.server.EnableRedisWebSession`. The annotation exposes a reactive Redis-backed `WebSessionManager`. If session events/indexing are needed on a supported version, `@EnableRedisIndexedWebSession` exists with its own constraints; do not use the indexed variant just for "ordinary session sharing".

**Do not confuse with `@EnableRedisHttpSession`:** that annotation belongs to Servlet and does not replace WebFlux `WebSession`.

## 5. Complete Two-Node Example with Java 17+

The example proves two things:

- **`/public/touch`:** requires no login, yet writes a counter into `WebSession`. You can use `curl` to prove session data flows A -> B -> A.
- **`/me`:** requires form login; after logging in on A, the browser sends the cookie to B and still sees the authenticated user.

This is a local development demo, not a full production configuration. The passwordless Redis container binds only to `127.0.0.1` to avoid network exposure.

### 5.1. Structure

```text
redis-webflux-session-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/ClusterSessionApplication.java
      resources/application.yml
    test/
      java/example/ClusterSessionApplicationTests.java
```

Create `settings.gradle`:

```groovy
rootProject.name = 'redis-webflux-session-demo'
```

Create `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
    implementation 'org.springframework.session:spring-session-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 5.2. Configuring application.yml

Create `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  data:
    redis:
      host: localhost
      port: 6379
  session:
    timeout: 30m
    redis:
      namespace: spring:session:webflux-lab
      flush-mode: on_save

app:
  node-id: node-local
```

Command-line arguments `--server.port` and `--app.node-id` override the defaults to run two processes. **Do not configure different namespaces for A and B** because this is session data for the same application.

### 5.3. Spring WebFlux and Spring Security application

Create `src/main/java/example/ClusterSessionApplication.java`:

```java
package example;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class ClusterSessionApplication {

    @Value("${app.node-id:node-local}")
    private String nodeId;

    public static void main(String[] args) {
        SpringApplication.run(ClusterSessionApplication.class, args);
    }

    @GetMapping("/")
    public String index() {
        return "Visit /public/touch, then /me";
    }

    @GetMapping("/public/touch")
    public Mono<VisitResponse> touch(ServerWebExchange exchange) {
        return exchange.getSession().map(session -> {
            session.start();

            Long previous = session.getAttribute("demo.visits");
            long visits = previous == null ? 1L : previous + 1L;

            session.getAttributes().put("demo.visits", visits);
            return new VisitResponse(nodeId, visits);
        });
    }

    @GetMapping("/me")
    public Mono<UserResponse> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
                .map(username -> new UserResponse(nodeId, username));
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/", "/login", "/public/**")
                        .permitAll()
                        .anyExchange().authenticated())
                .formLogin(withDefaults())
                .httpBasic(basic -> basic.disable())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}learn")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(alice);
    }

    public record VisitResponse(String node, long visits) { }
    public record UserResponse(String node, String username) { }
}
```

**Why does the code above prove the lesson properly?**

1. `nodeId` shows whether process A or B handled the request, without storing `nodeId` in the session.
2. `exchange.getSession()` is the standard WebFlux API; it is wired by Spring Session to `ReactiveSessionRepository`/Redis via auto-configuration.
3. `session.start()` starts the session, and `session.getAttributes().put("demo.visits", visits)` creates a change to persist. `Long` is a type handled by the default serializer.
4. `VisitResponse` returns JSON with the node and visit count, **never returning the session ID, cookie, or `SecurityContext` contents**.
5. `/public/touch` requires no login, making it easy to test with `curl` and keeping CSRF/forms out of the session-data test.
6. `/me` requires authentication and reads the username from `ReactiveSecurityContextHolder`, not Servlet `ThreadLocal`. If a session-backed context exists, node B can see the user logged in on A.
7. `formLogin(withDefaults())` enables the default `GET /login` page and handles `POST /login`. They belong to the same security chain; default CSRF stays enabled.
8. `httpBasic(...disable())` avoids accidentally using Basic credentials per request, which **would not prove Redis saved the login**.
9. `{noop}learn` is only a demo password. Production must use appropriate BCrypt/Argon2/PBKDF2/scrypt, a strong password encoder, and HTTPS.
10. The app **has no `@EnableRedisWebSession`**: Boot auto-configures Redis-backed `WebSession` because the dependency and reactive connection are present.
11. The two response records are not stored in the session. The demo session only stores `Long`; upon form login, Spring Security stores the context under a `WebSession` attribute.

**Concurrency note:** The session counter is only for **sequential** request testing. If two requests hit A/B concurrently, both may read the same old count and write back the same new count, causing a lost update. Spring Session does not turn `getAttribute + 1 + put` into an atomic Redis command. For real business counters, use Redis `INCR` or appropriate atomic/locking mechanisms instead of treating `WebSession` as a reliable concurrent counter.

### 5.4. Starting Redis for the lab

Example with Docker installed locally (local run only):

```bash
docker run --name redis-session-lab \
  -p 127.0.0.1:6379:6379 \
  -d redis:7.4-alpine

docker exec redis-session-lab redis-cli PING
```

Output of the second command:

```text
PONG
```

If Redis is already running at `localhost:6379`, there is no need to create a new container. If using Windows PowerShell and you dislike bash's line-continuation `\`, enter `docker run ...` on one line. **Never expose a lab Redis port to the Internet**; real environments require network policies, authentication/ACL, TLS, and data controls.

### 5.5. Running two processes of the same application

Open two terminals in the project directory.

Terminal A:

```bash
./gradlew bootRun --args='--server.port=8081 --app.node-id=node-a'
```

Terminal B:

```bash
./gradlew bootRun --args='--server.port=8082 --app.node-id=node-b'
```

On Windows, use `gradlew.bat bootRun --args="--server.port=8081 --app.node-id=node-a"` and the matching command for B. If no Gradle Wrapper is present, use `gradle bootRun` with the same `--args` and a Gradle version compatible with Spring Boot 3.3.13.

Both processes share **the same Redis configuration and namespace**, differing only in `server.port` and `app.node-id`. When deploying behind a real load balancer, replace the port pair with separate services/pods.

### 5.6. Testing session data A -> B -> A with curl

In a new terminal, use the **same cookie jar** for all three requests. On Linux/macOS or Windows with standard curl:

```bash
curl -sS -c session-cookies.txt -b session-cookies.txt \
  http://localhost:8081/public/touch

curl -sS -c session-cookies.txt -b session-cookies.txt \
  http://localhost:8082/public/touch

curl -sS -c session-cookies.txt -b session-cookies.txt \
  http://localhost:8081/public/touch
```

In PowerShell, invoke `curl.exe` instead of the `curl` alias in older PowerShell versions, or run each command on a single line.

If the cookie jar file does not exist initially, `curl` can still create it via `-c`; if your tool reports an error reading `-b`, create an empty local file first. After **three sequential** successful requests, the expected JSON looks like:

```json
{"node":"node-a","visits":1}
{"node":"node-b","visits":2}
{"node":"node-a","visits":3}
```

This is the **expected output** for a fresh session with no prior counter, not live output from your machine. If reusing an old cookie jar, the starting count may be greater than 1. JSON field order is not guaranteed; check each field's meaning.

**What this proves:** A session ID generated on A is recognized by B and updated continuously. Sticky sessions are not required for this to work. If B returns `visits=1` instead of 2, check the cookies sent, whether both instances point to the same Redis/namespace, and the session expiration.

### 5.7. Testing Spring Security authentication across two nodes

Test with a browser, **keeping the same `localhost` hostname** so cookies can be shared across ports (HTTP cookies do not distinguish ports):

1. Open `http://localhost:8081/me` while logged out. Spring Security redirects to `/login` on node A.
2. On the default form page, enter **`alice` / `learn`**, letting the browser submit the CSRF token and keep the session cookie.
3. After login, visit `http://localhost:8081/me` again. Expected JSON: `{"node":"node-a","username":"alice"}`.
4. Without clearing cookies, open `http://localhost:8082/me` in the **same browser profile**. Expected JSON: `{"node":"node-b","username":"alice"}`.
5. Go back to A; the user is still recognized. Restart A (keeping B running) and request `/me` on B to verify the session did not live only in A's RAM.
6. Open a private/incognito window or delete the `SESSION` cookie and visit B: you must log in again because there is no session ID to look up.

**The strongest proof** is that the `/me` request to B **does not resend username/password** yet still has a principal, while the code uses only form login with HTTP Basic disabled. That is the combination of Spring Security's `WebSessionServerSecurityContextRepository` and Spring Session's Redis-backed `WebSession`.

**Note on session rotation:** After POST login, the session ID may be rotated to prevent session fixation. When testing manually with an HTTP client, preserve the **new cookie from the login response**, rather than capturing a pre-login `SESSION` value and reusing it.

## 6. Spring Security and Spring Session: Two Coordinating Layers

A common shorthand is "Spring Session stores `SecurityContext`". That is true in outcome, yet you need to understand the mechanism:

```text
Spring Security AuthenticationWebFilter
    |
    +-- Authentication success
    +-- WebSessionServerSecurityContextRepository.save(...)
           |
           v
      ServerWebExchange.getSession()
           |
           v
      Spring Session WebSessionManager
           |
           v
      ReactiveSessionRepository<Session>
           |
           v
      ReactiveRedisSessionRepository
           |
           v
          Redis
```

On the next request, the load path runs in reverse:

```text
Cookie SESSION
    -> WebSessionManager loads session from Redis
    -> WebSessionServerSecurityContextRepository.load(...)
    -> ReactorContextWebFilter / ReactiveSecurityContextHolder
    -> AuthorizationWebFilter
    -> Handler permitted
```

Two misconfigurations can cause a mismatch:

**(a) Using `NoOpServerSecurityContextRepository` on the form-login chain**: Spring Session may save regular session attributes fine, yet `SecurityContext` is not saved/restored for the next request. `/public/touch` A -> B succeeds while `/me` on B asks to log in again. Hence test both paths, not just the counter.

**(b) Not enabling Spring Session Redis-backed `WebSession`**: `SecurityContext` can still reside in a local `WebSession` managed per node; node A works yet node B cannot restore it. Check Spring Boot auto-configuration, `WebSessionManager`/`ReactiveSessionRepository` beans, and Redis connectivity.

If using `ServerHttpSecurity.securityContextRepository(...)` to customize the load path, also check the repository used to **save** on each authentication filter. Do not assume every filter automatically syncs its save configuration from a single setter on `ServerHttpSecurity`.

## 7. TTL and Session Lifecycle in Redis

A session has key timestamps:

- **creationTime**: when the session was created.
- **lastAccessedTime**: when the session was most recently active per policy.
- **maxInactiveInterval**: inactivity limit.
- **TTL of Redis keys**: infrastructure mechanism for expiring and cleaning up sessions/metadata.

For instance, setting `spring.session.timeout=30m` defines a 30-minute inactivity policy for the demo. A request properly using the session can update `lastAccessedTime`, shifting expiration forward. Session data does not live forever; you must test new tokens/logins after expiration.

**Do not assume every Redis key's TTL is always exactly 1,800 seconds.** Spring Session may use additional expiration/metadata keys or buffers for expiration events and cleanup. Depending on default/indexed repositories and versions, key TTL, Redis expired events, and `findById` results are not strictly identical. Verify expiration through the Session API and request behavior, using Redis TTL only as supporting evidence.

To inspect metadata in the lab (local Redis only):

```bash
redis-cli --scan --pattern 'spring:session:webflux-lab:*'
```

Once you know a **specific key** belonging to the demo session, you can run `redis-cli TTL "<key>"`. Never run `KEYS *` or `FLUSHALL` on a shared Redis: it can block Redis or wipe another app's sessions. Never dump all session attributes to logs, as they can contain authentication data.

### When a node restarts

If node A dies, the session stays in Redis until it expires or is deleted. B can handle the next request with the valid cookie. **However, Redis is a critical dependency**: if Redis loses data, fails over without durability, or hits a serializer error, continuing authentication can fail.

### When Redis loses connectivity

With Redis-backed sessions, you cannot assume a session is authenticated when lookup fails. Spring Security must **fail closed**: never admit requests to protected endpoints simply because Redis errored. The app may respond 5xx or a configured handler error; add metrics, bounded retries, and alerts rather than turning a `load` error into a fake valid `SecurityContext`.

Redis needs HA/sentinel/cluster suited to your requirements, yet failover still has latency and, depending on replication config, may lose a few recent writes. "Using Redis" **does not mean** sessions can never be lost under any outage.

## 8. Logout and Cluster-Wide Session Invalidation

A logout request may land on node A while the next request hits node B. For logout to take effect across nodes, **the shared authentication state** must be deleted or invalidated, not just an in-memory variable.

```text
Browser POST /logout with valid CSRF
      |
      v
Node A Security LogoutWebFilter
      |
      +-- remove SecurityContext from repository/session
      +-- optionally invalidate entire WebSession per config
      |
      v
Spring Session writes deletion/update to Redis
      |
      v
Browser sends new request to Node B
      |
      v
B can no longer restore old Authentication
      |
      v
Redirect/challenge to log in again
```

**Distinguish two goals:**

1. **Logging the user out of Spring Security:** removes the saved `SecurityContext` so subsequent requests are no longer authenticated.
2. **Invalidating the entire `WebSession`:** also deletes business attributes such as `demo.visits`, request-cache data, and other attributes.

A logout handler that only clears the context **does not necessarily delete all session data**. If business requirements demand wiping the entire session, configure `WebSessionServerLogoutHandler` or the appropriate mechanism for your Spring Security version, and test a new post-logout request on another node.

With default CSRF configuration, logout mutates session state and thus normally requires **POST + CSRF token**—do not turn logout into a GET just for an easy hyperlink.

**Do not confuse session logout with JWT revocation:** If the application also issues standalone Bearer tokens, deleting the `WebSession` in Redis does not invalidate already issued tokens. Design token lifetimes/revocation separately.

### Testing logout properly

- Log in via A, call `GET /me` on B, and confirm the username.
- Perform logout via A using a valid form, keeping the corresponding cookie/session.
- Call `GET /me` on B again: access from the prior login is gone.
- If full invalidation was configured, call `/public/touch` with the old session: old session data must not continue; a fresh session starting at 1 may appear.
- Repeat the test across a node restart to rule out local caches holding stale context.

## 9. Serialization Across Application Versions

Redis stores **session data**, not a live Java object transferable between JVMs without conversion. Session attributes and `SecurityContext` must be compatibly **serialized/deserialized**.

Spring Session Redis defaults to **Java serialization** for session attributes in many Spring Session 3.x setups. This is a choice that requires care during rolling updates.

### Common risks

| Scenario | Possible consequence |
| --- | --- |
| Nodes A and B run two incompatible versions of a class stored in session | Deserialization exception on node B |
| Storing a custom object unsupported by the serializer | Session write fails |
| Changing `serialVersionUID` or class structure during rolling deploy | Old sessions become unreadable |
| Session holds large payloads/objects | Higher Redis memory, network traffic, and GC pressure |
| Configuring a JSON serializer that does not support `SecurityContext`/`Authentication` types | Login succeeds then fails on save/load |
| Allowing untrusted Redis data to undergo arbitrary deserialization | Severe security risk |

**Rule of thumb:** Never store ORM entities, request objects, raw tokens, or complex business objects in the session when you can store **small, stable identifiers and essential data**. If a JSON serializer is needed, check how to configure the `springSessionDefaultRedisSerializer` bean and the Spring Security Jackson modules for your **exact version**; do not simply switch to JSON and assume every `Authentication` class deserializes cleanly.

Spring Session documentation covers custom serializers and emphasizes registering Spring Security Jackson modules when sessions contain `SecurityContext`. When upgrading frameworks, test **old sessions in Redis being read by the new node** before full rollout.

### Namespaces and migrations

If you change `spring.session.redis.namespace`, new nodes will not see sessions under the old namespace. For rolling deployments, plan a cutover/migration strategy or accept requiring users to log in again. Do not deploy A with namespace `webflux-lab-v1` and B with `webflux-lab-v2` and call the resulting "lost session" a Redis bug.

## 10. Concurrent Updates and Consistency

Sharing sessions does not make attribute operations **atomic** when two requests run concurrently.

Suppose A and B both read `visits=10`:

```text
A: load visits=10 ---------> update visits=11 ----> save
B:      load visits=10 ---> update visits=11 ----------> save

Final value may be 11, not 12.
```

Spring Session optimizes writing modified attributes, yet a **read-modify-write** across processes does not automatically become a distributed transaction.

Therefore:

- Use `WebSession` for **user session state**, such as small preferences, `SecurityContext`, or appropriate CSRF/session data.
- For counters, balances, quotas, inventory, or idempotency, use atomic Redis commands (`INCR`/Lua) or storage with dedicated transactions/locks.
- Minimize writing the same attribute across concurrent requests; do not rely on load-balancer stickiness to guarantee atomicity.
- With multiple browser tabs/concurrent requests, design conflict merging/handling or avoid putting critical business state in the session.

**Flush mode and save mode:** `FlushMode.ON_SAVE` (rather than immediate writes) and `SaveMode.ON_SET_ATTRIBUTE` are common choices. They affect write timing and volume, yet **do not guarantee serializable transactions** across concurrent requests. Benchmark and race-test when using sessions under high concurrency.

## 11. Automated Testing and Cross-Node Verification

### 11.1. Single-node WebTestClient test

The test below runs against the application and requires the lab Redis to be running. It verifies an issued cookie works on the next request. It does not prove two separate JVMs reading Redis: that is the purpose of the A -> B test via `curl` or browser.

Create `src/test/java/example/ClusterSessionApplicationTests.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
class ClusterSessionApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void sessionAttributeSurvivesTwoRequests() {
        var first = client.get()
                .uri("/public/touch")
                .exchange()
                .expectStatus().isOk()
                .expectBody(ClusterSessionApplication.VisitResponse.class)
                .returnResult();

        assertNotNull(first.getResponseBody());
        assertEquals(1L, first.getResponseBody().visits());

        ResponseCookie sessionCookie =
                first.getResponseCookies().getFirst("SESSION");
        assertNotNull(sessionCookie);

        client.get()
                .uri("/public/touch")
                .cookie("SESSION", sessionCookie.getValue())
                .exchange()
                .expectStatus().isOk()
                .expectBody(ClusterSessionApplication.VisitResponse.class)
                .value(body -> assertEquals(2L, body.visits()));
    }

    @Test
    void protectedEndpointRequiresLogin() {
        client.get()
                .uri("/me")
                .exchange()
                .expectStatus().is3xxRedirection();
    }
}
```

Run while Redis is running:

```bash
./gradlew test
```

If `@SpringBootTest` cannot reach Redis, the test fails due to the real infrastructure dependency; start local Redis or use Testcontainers/a dedicated CI Redis instance. **Do not** replace it with a mock session if the test goal is Redis persistence.

### 11.2. Two-node integration test

Required checks:

| Step | Sent to | Expectation |
| --- | --- | --- |
| First public request, keep cookie | Node A | `visits=1` |
| Next public request with same cookie | Node B | `visits=2` |
| Subsequent public request with same cookie | Node A | `visits=3` |
| Successful form login with CSRF and cookie | Node A | Creates `SecurityContext` saved in session |
| `GET /me` with cookie after login | Node B | 200, username `alice` |
| `GET /me` without cookie | Node B | Redirects to form login |
| Restart node A while keeping Redis | Node B | Session continues per TTL |
| Logout via node A, new request on node B | Node B | Old authentication is gone |
| Wait past inactivity timeout | Node A/B | Old session is no longer authenticated |
| Redis unreachable | Node A/B | Authorization is not bypassed; error alerted |

**What is NOT enough to prove sharing:**

- Running only one instance.
- Using `mockUser` in unit tests: mocks can bypass form login and the repository.
- Sending HTTP Basic credentials on **every** request: node B re-authenticates from the password, proving nothing about loading sessions from Redis.
- Always routing to A via sticky sessions.
- Only seeing both instances connected to Redis without testing the same cookie/session.
- Only checking Redis has keys without verifying `SecurityContext` is used by node B.

### 11.3. Inspecting Redis key metadata

```bash
redis-cli --scan --pattern 'spring:session:webflux-lab:*'
```

If session keys exist, check TTL on a specific key. Never print attribute/`Authentication` contents to logs, never commit test cookie jars to git, and never store real Redis dumps in shared artifacts. `SCAN` is safer than `KEYS *` for inspecting large stores, yet still requires limits and environment controls.

## 12. Operational Monitoring and Performance

Spring Session Redis removes the node-local session constraint, yet every request needing a session can generate Redis traffic. Across multiple nodes, Redis latency, connection pools, serialization, and networking affect login/API latency.

### 12.1. Recommended metrics

| Layer | Metrics and signals |
| --- | --- |
| HTTP | Login success/failure, `/me` p50/p95/p99, redirect rate, 401/403/5xx |
| Redis client | Command latency, timeouts, connection errors, reconnects, pool saturation |
| Session | Create/load/expire rates, save failures, cache hits, session size, TTL |
| Resources | Redis memory, evictions, CPU, network bandwidth, replication lag |
| Spring Security | Authentication failures, CSRF failures, authorization denials, logout errors |
| Deployment | Node count, node version, namespace/serializer version, session behavior after rolling deploy |

Never log the `SESSION` cookie, raw session ID, passwords, tokens, or the entire `SecurityContext`. If correlating requests across nodes, use an independent correlation ID or controlled session fingerprint that does not expose the ID used to access the session.

### 12.2. Risks under heavy load

- **Redis round trips:** login or session-heavy traffic can increase network cost and latency.
- **Session size:** large objects consume serialization/memory and trigger GC; keep sessions lean.
- **Concurrent requests on the same session:** risk of overwritten writes; do not treat `WebSession` as a distributed business database.
- **Key expiration:** configure sensible timeouts; keyspace events for indexed sessions have caveats and do not replace TTL checks.
- **Capacity:** Redis `maxmemory-policy` may evict session keys before timeout, forcing browsers to log in again.
- **Availability:** Redis HA with async replication can experience a brief write-loss window during failover.
- **Security:** Redis holds sensitive authentication state; enforce network isolation, ACLs, TLS, secret rotation, backups, and access auditing.

A shared Redis cluster **does not replace session fixation, CSRF, and password controls**. Spring Security must still govern authentication/authorization; Spring Session only swaps the session storage infrastructure.

## 13. Common Errors and Fixes

### 13.1. Login on A succeeds, yet B still redirects to login

Check in order:

1. Is the client sending the **same `SESSION` cookie** to B? Do cookie scopes share the same host/path/domain/secure settings?
2. Do A and B share the same Redis endpoint and `spring.session.redis.namespace`?
3. Are the `spring-session-data-redis` dependency, reactive Redis auto-configuration, and `WebSessionManager` actually active?
4. Is Spring Security form login saving `SecurityContext` into `WebSession`? Did `NoOpServerSecurityContextRepository` slip in accidentally?
5. Can B deserialize the `SecurityContext` saved by A? Are there class/version/serializer errors?
6. Did the session time out, get logged out, get deleted, or get evicted by Redis?

If `/public/touch` A -> B succeeds while `/me` fails, the culprit is most likely **SecurityContext persistence/authentication filters**, not Redis cookie routing. If `/public/touch` resets too, check **session cookies, namespace, and `WebSessionManager`** first.

### 13.2. Redis has the key, yet the user is unauthenticated

The session may hold only `demo.visits` or a CSRF token without `SecurityContext`. Having a Redis key **does not mean** logged in. Verify form POST credentials/CSRF succeeded and `SecurityContext` repository save/load are wired.

### 13.3. Servlet annotation configured

`@EnableRedisHttpSession` or `SessionRepositoryFilter` for `HttpSession` does not fit an app using Spring WebFlux `WebSession`. In this Boot WebFlux example, let auto-config handle it; if writing manual Java config, use `@EnableRedisWebSession` and `ReactiveRedisConnectionFactory`.

### 13.4. Two nodes use different namespaces

Node A saves `spring:session:app-a:*` while B searches `spring:session:app-b:*`. Each node works locally yet misses the shared session. Use one namespace across all nodes of the same app; separate namespaces **between distinct applications**.

### 13.5. Sharing Redis while storing unserializable custom objects

Results in `SerializationException`, `ClassNotFoundException`, or invalid class errors during rollout. Keep attributes small and compatible, plan JSON serialization with verified Security modules or session migration, and test across two node versions.

### 13.6. Unexpected TTL expiration

Check session timeout, last accessed time, cookies, Redis eviction, and clock/config—not just a single key's `TTL`. Discrepancies between key TTL and API session state can stem from cleanup/expiration-tracking mechanics.

### 13.7. Logout on A, yet B still allows access

Ensure logout deletes `SecurityContext` on the shared repository, and B does not cache `Authentication` past its valid lifecycle. Test a **fresh request** to B; if "log out all devices" is required, add a policy to find/delete multiple sessions or dedicated token revocation.

### 13.8. Redis outage yet the app still lets requests through

Never use `onErrorResume(...)` to fabricate an authenticated user when the session store fails. The security path must reject or return a controlled infrastructure error, never bypass authorization.

### 13.9. High concurrency breaks counters

Two requests on the same session reading and incrementing separately can lose updates. Redis-backed `WebSession` does not guarantee atomic increments. Use Redis atomic operations for business counters.

### 13.10. Spring Session running blocking calls on the Netty event loop

Use `ReactiveRedisConnectionFactory`/Lettuce and `Mono` APIs; never call `block()` or a blocking Redis client inside a `WebFilter`/handler. Even with the reactive Redis starter, avoid injecting synchronous I/O into the WebFlux pipeline.

### 13.11. Session cookie not sent when switching between localhost and 127.0.0.1

Browser cookies follow host/path/domain/scheme policies; `localhost` and `127.0.0.1` are different hostnames. In the demo, use **`localhost` for both A and B**. Different ports do not separate cookies on the same hostname. In real deployments, use a stable hostname behind a reverse proxy and configure forwarded headers/cookies properly.

### 13.12. Deploying a new app version breaks old sessions

Rolling deployments can break deserialization if classes inside `SecurityContext` change. Plan session compatibility ahead of time or accept invalidating sessions per policy; never assume Redis preserves Java objects across arbitrary upgrades without testing.

## 14. Self-Check Questions

**1. Why can two instances sharing Redis see the same login state?**  
Because the client sends the same session ID; Spring Session's Redis-backed `WebSessionManager` loads the session from Redis, and Spring Security loads the `SecurityContext` stored in `WebSession`.

**2. Are `ReactiveSessionRepository` and `ServerSecurityContextRepository` the same interface?**  
No. Spring Session's repository saves/loads sessions; Spring Security's repository saves/loads security contexts. They connect through `WebSession`.

**3. Is `@EnableRedisHttpSession` needed in WebFlux?**  
No. That is a Servlet API. With Boot WebFlux and appropriate dependencies, auto-config works; if configuring reactive manually, use `@EnableRedisWebSession`.

**4. Why isn't sending Basic auth to both A and B enough?**  
Because each request can re-authenticate from credentials, proving nothing about shared sessions. You must test **form login once** and then a new GET **without resending the password** on the other node.

**5. What does `curl -c/-b` in the example prove?**  
The cookie jar carries `SESSION` across three sequential requests; the counter increments 1 -> 2 -> 3 while alternating between two instances. This verifies shared `WebSession` attributes.

**6. Does logout automatically delete all attributes from Redis?**  
Do not assume so. Clearing `SecurityContext` and invalidating the entire session are two potentially separate goals; configure and test according to security requirements.

**7. Does Spring Session guarantee `visits++` is atomic across two nodes?**  
No. Read-modify-write via `WebSession` can suffer lost updates; use Redis `INCR` or an appropriate transaction for business counters.

**8. Do two nodes sharing Redis with different `namespace`s share sessions?**  
No. Different namespaces cause each node to look up different keys.

**9. If Redis disconnects, can a protected API pass requests through because "session could not be loaded"?**  
No. A load failure is not proof of valid authentication; fail closed and handle the operational error.

**10. Why does the serializer matter when running multiple app versions?**  
Because node B must deserialize attributes serialized by node A; class or format changes can make sessions unreadable.

**11. Does the `SESSION` cookie hold all of a user's permissions?**  
No. It primarily carries the session ID. `SecurityContext`/attributes are stored server-side in Redis per configuration.

**12. If A restarts, why does B still see the session?**  
Because session data is stored outside A's RAM in Redis; it remains valid if not timed out, deleted, or lost by Redis.

**Key takeaway:** In Spring Security WebFlux, **Spring Security manages who is logged in**, while **Spring Session reactive Redis stores `WebSession` so requests across multiple nodes share one session**. To prove it properly, test the same cookie across A/B, form-login on A then verify the principal on B, log out then verify B is unauthenticated, and observe Redis/session expiration. Sharing sessions does not automatically solve concurrency, serialization, Redis HA, or security policy.

## References

- [Spring Session — WebSession Integration](https://docs.spring.io/spring-session/reference/web-session.html): replacing `WebSessionManager` and integrating `ReactiveSessionRepository` into WebFlux.
- [Spring Boot 3.3 — Spring Session](https://docs.spring.io/spring-boot/3.3/reference/web/spring-session.html): Spring Session reactive auto-configuration, Redis, and timeout properties.
- [Spring Session — API Documentation](https://docs.spring.io/spring-session/reference/api.html): `ReactiveSessionRepository`, `ReactiveRedisSessionRepository`, expiration, and session storage.
- [Spring Session — Redis Configuration](https://docs.spring.io/spring-session/reference/configuration/redis.html): namespace, serializer, indexed repository, and session cleanup.
- [Spring Session — Reactive Redis Indexed Configuration](https://docs.spring.io/spring-session/reference/configuration/reactive-redis-indexed.html): indexed sessions and Redis keyspace event caveats, used when indexing is truly needed.
- [Spring Session — EnableRedisWebSession API](https://docs.spring.io/spring-session/docs/3.3.x/api/org/springframework/session/data/redis/config/annotation/web/server/EnableRedisWebSession.html): manual Java configuration for WebFlux.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): form login, `SecurityWebFilterChain`, and authorization.
- [Spring Security — ServerSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ServerSecurityContextRepository.html): exchange-based context load/save contract.
