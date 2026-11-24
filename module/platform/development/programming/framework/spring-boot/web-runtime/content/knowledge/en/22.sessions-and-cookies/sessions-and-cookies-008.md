# Load Balancing, Sticky Sessions, and Shared Session Stores in Spring Boot

## 1. The problem: a single user can hit multiple instances

When Spring Boot runs on a **single JVM**, Servlet applications typically store a user's `HttpSession` in the web server's memory. The browser receives a **session cookie** carrying an ID; on the next request, the server looks up the ID to retrieve attributes such as a temporary shopping cart, wizard form data, or a `SecurityContext` when authentication uses sessions.

When deploying **multiple instances** behind a load balancer (LB), requests from the same browser can be routed to different JVMs. If session state lives only in each JVM's RAM, Node B does not automatically know about data created on Node A.

~~~text
Browser (holds session cookie)
             |
             v
       Load balancer
         /       \
        v         v
   Spring A     Spring B
   RAM: S123    RAM: no S123
   cart=3       no cart
~~~

This is a **session-state distribution problem**, not a cookie bug or a specific `@GetMapping` controller bug. There are two classic ways to solve it:

1. **Sticky sessions (session affinity):** the LB tries to route requests from the same client/session back to Node A. The session stays in A's RAM.
2. **Shared/distributed session store:** A and B both read and write sessions via Redis or JDBC using the same ID. Requests can land on any eligible node.

The two options can be combined, yet they solve different problems. Sticky sessions are a **routing rule**; a shared store is a **data storage strategy**. Never equate "having sticky sessions" with "sessions are backed up and fail over automatically".

This lesson primarily examines Spring Boot 3.x + Spring MVC/Servlet (`HttpSession`), and separately contrasts Spring WebFlux (`WebSession`).

## 2. What do HTTP cookies carry, and where are sessions stored?

In the server-side session model:

~~~text
Response after creating a session:
Set-Cookie: JSESSIONID=<opaque-id>; Path=/; HttpOnly

Next request:
Cookie: JSESSIONID=<opaque-id>

Server:
ID from cookie -> session repository -> attribute map + expiration
~~~

`JSESSIONID` is typically the default cookie name of a servlet container when using local `HttpSession`. **Spring Session** with its default cookie resolver normally uses the name **`SESSION`**. The actual name can be customized and does not determine where sessions are stored: always inspect `Set-Cookie` and the active configuration.

Normally, the cookie **carries only the session ID** (an unpredictable string), while session attributes live in RAM/container memory or in Redis/JDBC. Do not mix this up with another architecture that stores signed/encrypted full state inside the cookie; this lesson focuses on **server-side sessions**.

Data flows across layers:

1. The browser receives `Set-Cookie` when the application creates a session.
2. The browser sends `Cookie` on subsequent requests if domain, path, `Secure`, `SameSite`, and browser rules allow.
3. The LB decides whether to route to A or B (with or without affinity).
4. The chosen node resolves the ID in the container-local session manager or shared repository.
5. The server reads/updates attributes and may refresh the inactivity expiration.

**Cookies are not bound to a TCP port.** On the same hostname `localhost`, `http://localhost:8081` and `http://localhost:8082` can both receive cookies matching Domain/Path; this makes local two-node experiments possible. However, `localhost` and `127.0.0.1` are two distinct hosts for cookies. In real systems, cookie domain/path and LB/HTTPS configuration must be consistent.

## 3. What happens without sticky sessions and without a shared store?

Suppose a user is checking out, and Node A stores `cartSize=3` in its local `HttpSession`:

~~~text
T1 Browser -> LB -> A: Cookie=S123, A reads cartSize=3
T2 Browser -> LB -> B: Cookie=S123, B does not have S123
T3 B creates a new session or treats the user as unauthenticated
T4 Browser returns to A or B: state flickers unpredictably
~~~

Depending on configuration, Node B may issue a different session/cookie, reject the request as unauthenticated, lose the cart, or reset form progress. Even when the LB uses round-robin and both nodes are "healthy", **state is not consistent**.

Visible failure symptoms can include:

- Users are randomly logged out or prompted to sign in again.
- Shopping cart or session banners change on page refresh.
- Multi-step workflows lose progress between requests.
- CSRF tokens or session-backed security contexts mismatch after switching nodes.
- Single-instance tests always pass, while multi-instance LB tests pass intermittently.

The first thing to check is not tweaking cookie flags blindly: record **which node handled the request**, which session ID cookie was sent, and whether the backend repository has that session ID (never log raw ID values to public logs).

## 4. Sticky sessions: pinning requests to one node

**Session affinity** is the LB's ability to remember or stabilize backend selection for a client based on some key. An LB may use:

- An **LB-issued affinity cookie**: the LB sets its own routing cookie, e.g., encoding the target backend or mapping. It does not have to be `JSESSIONID` or `SESSION`.
- Source IP hashing: requests from the same IP usually go to the same node.
- Hashing on a normalized attribute, or ID lookup supported by the LB.

~~~text
Browser affinity cookie -> LB
                            |
                            +--> A (nearly all requests from this client)
                            |
                            +--> B (handles other clients)
RAM A: user1, user2 sessions
RAM B: user3, user4 sessions
~~~

Sticky routing can let a **local `HttpSession`** system function for a while because requests return to where the data lives. Initial setup cost is relatively low and avoids calling a shared store on every request. However, it creates **client ↔ node coupling**:

- **Node A dies/restarts:** A loses RAM; the LB must route to B, which lacks A's local sessions. Users lose state or must log in again.
- **Scale-in / rolling deploy:** draining a node and closing connections does not migrate RAM sessions to another node.
- **Load imbalance:** one node with several "heavy" clients stays overloaded while another node sits idle. Source-IP affinity is especially unfair behind NAT, proxies, or mobile carrier networks.
- **IP / routing-cookie changes:** users can land on another node and lose their session.
- **Multi-region:** pinning a session to a single node/zone is a major bottleneck for cross-zone routing or failover.
- **Background work:** sticky routing does not move in-RAM objects, running threads, WebSockets, or in-progress uploads to another node.

Do not mistake sticky sessions for fault tolerance. If A dies, affinity only meant the LB tried routing to A until learning A was down; **it does not copy data to B**.

### Illustrative NGINX `ip_hash` affinity example

~~~nginx
upstream spring_nodes {
    ip_hash;
    server 127.0.0.1:8081;
    server 127.0.0.1:8082;
}

server {
    listen 8090;

    location / {
        proxy_pass http://spring_nodes;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
~~~

`ip_hash` is **IP-based affinity**, not a per-user sticky cookie. Multiple browsers behind NAT share an IP and may all pile onto one node; when a client's source IP changes, its backend changes too. Sticky-cookie policies on other LBs/cloud platforms must be configured per vendor documentation rather than inferred from this example.

Trust forwarded headers only from controlled reverse proxies. Never use client-supplied `X-Forwarded-For` directly to verify user identity. Configure health checks, timeouts, retries, and connection draining appropriate for committed requests.

## 5. Shared session store: multiple instances sharing one session

Instead of storing all attributes inside a single JVM:

~~~text
 Browser --Cookie: SESSION=S123-->
                   Load balancer
                      /    \
                     v      v
                Spring A  Spring B
                     \      /
                      v    v
                 Redis / JDBC
                key S123 -> attributes
~~~

When Node A receives `SESSION=S123`, it reads the session from the repository; a later request to Node B retrieves the same ID. If A fails **after state has been successfully persisted to the store**, B can continue processing using that persisted data.

Spring Session provides an abstraction replacing the session repository:

- For **Servlet**, it integrates with `HttpSession` via a filter, so most controllers/services using `HttpSession` do not need to rewrite against Redis APIs directly.
- For **WebFlux**, it supports `WebSession` via a reactive session repository.
- Redis suits high-frequency session access with TTLs; JDBC can be convenient when leveraging an existing relational DB infrastructure and transactional/operational model.
- Using a shared store **does not make all application state distributed**. JVM caches, in-memory locks, mutable singleton fields, temp files, and WebSocket connections remain local to each node.

Main benefit: **switching nodes without losing persisted sessions**, enabling flexible rollouts/scaling and reducing affinity dependence. Cost: every node now depends on the availability, latency, serialization compatibility, security, and operation of the session store.

## 6. Architecture comparison: Local, sticky, and shared store

| Criterion | Local session + no sticky | Local session + sticky | Shared Redis/JDBC + any-node LB |
| --- | --- | --- | --- |
| User requests hitting another node | State easily lost/missed | Usually avoided, yet can still happen | Can still read persisted session |
| Node holding session crashes | RAM sessions vanish | RAM sessions vanish | Sessions can continue if store and records survive |
| External session store dependency | No | No | Yes |
| Scale-in / rolling deploy | Easily loses sessions | Needs draining/affinity rules; loses sessions when A terminates | Less node coupling |
| Request load balancing | Flexible, but state breaks | Risk of uneven load | More flexible |
| Store read/write cost | Mostly RAM | Mostly RAM | Network + serialization + storage |
| Data across process restart | Lost unless special persistence enabled | Still lost | Retained within store TTL if saved cleanly |
| Concurrent updates to same session | Race risk within one JVM | Race risk within one JVM | Additional cross-node lost-update risk |
| Deployment complexity | Simplest for single node | Requires LB affinity | Requires library, HA store, and operations |

**There is no universally optimal choice.** For a small single-instance app where losing sessions on restart is acceptable, local sessions suffice. For multi-instance apps requiring failover and zero-logout rollouts, a shared store is usually appropriate. Sticky sessions can serve as a transitional choice or routing optimization, yet never replace shared storage when sessions must survive node failures.

Another option is a **stateless** architecture (e.g., independently verified access tokens), though it does not automatically solve cart storage, token revocation, CSRF, refresh tokens, or workflow state. Pick the model based on business and security contracts.

## 7. Spring Boot Servlet: from local `HttpSession` to Spring Session + Redis

### 7.1. Single-codebase example app run as two instances

Example uses Spring Boot 3.3.x + Java 17+, Spring MVC, and embedded Tomcat. The controller increments a `visits` counter in the session and returns which node processed the request. The goal is to **observe routing and persistence**, not to treat this counter as an atomic commercial transaction.

Project structure:

~~~text
session-lab/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/session/SessionLabApplication.java
    └── resources/application.properties
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'session-lab'
~~~

`build.gradle` — **phase 1: local session**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('bootJar') {
    archiveFileName = 'session-lab.jar'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.port=8080
server.servlet.session.timeout=30m
~~~

`src/main/java/demo/session/SessionLabApplication.java` — **runnable Java 17+**:

~~~java
package demo.session;

import jakarta.servlet.http.HttpSession;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SessionLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionLabApplication.class, args);
    }
}

@RestController
class VisitController {
    private final String node;

    VisitController(@Value("${demo.node-id:local}") String node) {
        this.node = node;
    }

    @GetMapping("/visit")
    VisitReply visit(HttpSession session) {
        Object current = session.getAttribute("visits");
        int next = current instanceof Integer count ? count + 1 : 1;
        session.setAttribute("visits", next);
        return new VisitReply(node, session.getId(), next);
    }

    @PostMapping("/logout-demo")
    void invalidate(HttpSession session) {
        session.invalidate();
    }

    record VisitReply(String node, String sessionId, int visits) {
    }
}
~~~

Explanation:

1. `HttpSession` is provided by Spring MVC/Servlet. On a client's first request without a valid session, the container creates a new session; `session.setAttribute` saves the visit count.
2. `@Value("${demo.node-id:local}")` reads the node label from the command line; this is **solely a diagnostic label**, not LB routing configuration.
3. `session.getId()` is returned **only for lab observation**. **Never return session IDs in production JSON**, because the ID is a bearer credential for the session and poses a session hijacking risk if leaked.
4. `POST /logout-demo` demonstrates calling `invalidate()`. In apps with Spring Security, use the official logout flow to clean up authentication, CSRF, cookies, and related state properly.
5. An `Integer` counter is easy to store in Redis. In production, keep session state as compact as possible and design concurrent updates carefully if strict accuracy is required.

### 7.2. Running two nodes from the same executable JAR

Build once:

~~~bash
./gradlew clean bootJar
~~~

Open **two separate terminals** and run the same JAR with different ports and labels:

~~~bash
# Terminal A
java -jar build/libs/session-lab.jar --server.port=8081 --demo.node-id=A
~~~

~~~bash
# Terminal B
java -jar build/libs/session-lab.jar --server.port=8082 --demo.node-id=B
~~~

With two JVMs running separate container session managers, `HttpSession` attributes are not synchronized automatically. **Never** assume two instances share RAM/sessions simply because both were built from the same JAR.

Test with cURL, saving the cookie from the first call and sending that exact cookie to B:

~~~bash
# First call to A: save cookie to a dedicated file
curl -s -c cookies.local.txt http://localhost:8081/visit

# Second call to A: send saved cookie
curl -s -b cookies.local.txt http://localhost:8081/visit

# Send the SAME session cookie from A to B
curl -s -b cookies.local.txt http://localhost:8082/visit
~~~

**Illustrative** responses (IDs are random, not fixed):

~~~json
{"node":"A","sessionId":"id-on-A","visits":1}
~~~

~~~json
{"node":"A","sessionId":"id-on-A","visits":2}
~~~

~~~json
{"node":"B","sessionId":"new-id-on-B","visits":1}
~~~

The same cookie from A reaches B, yet B has no matching RAM session and thus creates a new session or handles the request without an existing session. In this lab, `@GetMapping` takes `HttpSession`, so the app creates a new session. If a sticky LB kept routing requests to A, `visits` would keep incrementing—**as long as A stays alive and the affinity cookie remains valid**.

cURL sends session cookies only for matching host/path; the commands use `localhost` for both ports without switching to `127.0.0.1`. During testing, omit `-c cookies.local.txt` on the request sent to B if you want to preserve A's original cookie for subsequent checks.

## 8. Phase 2: using Redis as a shared session store

### 8.1. Adding Spring Session and Redis for Spring Boot 3.3.x

In the **same `build.gradle`** from Phase 1, replace the `dependencies` block with:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.session:spring-session-data-redis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Spring Boot manages compatible versions for Spring Session and Spring Data Redis. `spring-boot-starter-data-redis` brings the Redis client/infrastructure (Lettuce by default); `spring-session-data-redis` provides the session repository and filter.

**Version note:** Spring Boot 4.x documentation introduces a starter named `spring-boot-starter-session-data-redis`, whereas this **Spring Boot 3.3.x** example uses `org.springframework.session:spring-session-data-redis` per the 3.x ecosystem. Do not copy starter names from another major release into an older build without verifying compatibility.

In a Spring Boot Servlet configuration, adding the proper Spring Session module normally enables Redis session **auto-configuration**. Adding `@EnableRedisHttpSession` is not mandatory. Manually adding that annotation can cause part of Spring Boot's auto-configuration to back off; stick to one consistent configuration style to avoid conflicts.

### 8.2. Configuring connection, namespace, and timeout

`src/main/resources/application.properties`:

~~~properties
server.port=8080

# Session expires after 30 minutes of inactivity.
spring.session.timeout=30m

# Nodes must use the same Redis, database, and namespace to share sessions.
spring.data.redis.host=127.0.0.1
spring.data.redis.port=6379
spring.session.redis.namespace=demo:session-lab

# Example write mode when the repository saves a session.
spring.session.redis.flush-mode=on_save
~~~

Key points:

- `spring.session.timeout` sets the maximum inactivity interval for the session. If omitted, Spring Boot Servlet may fall back to `server.servlet.session.timeout`; verify the effective property in your version.
- The Redis namespace separates this app's data from other apps. **Both nodes must use the same namespace** to read the same sessions; two separate apps should not accidentally share a namespace unless designed to share sessions.
- Both nodes must point to the same **logical** Redis, same database/cluster, and compatible serialized attribute formats.
- `flush-mode=on_save` specifies that changes are flushed to the store when the session is saved (typically at request end via the filter). Do not assume every `setAttribute` call is instantly durable prior to a JVM crash.
- Supply Redis connection, auth, TLS, and secrets per environment. Never commit passwords into sample `application.properties` files in source control; use a secret manager or runtime config injection in production.
- When Redis is unavailable, session-dependent requests can fail or appear unauthenticated; **Spring Session does not safely fall back to local RAM while preserving sessions**.

To run local Redis, use an installed Redis service listening on `127.0.0.1:6379`, or a lab container (if Docker is installed):

~~~bash
docker run --rm --name session-lab-redis \
  -p 127.0.0.1:6379:6379 redis:7
~~~

This runs in the foreground; keep a separate terminal for Redis and stop it when finished. Binding the port to loopback ensures **Redis is not exposed to the whole network**. Do not treat this container command as a production Redis recommendation, as it lacks authentication, persistence, TLS, failover, and monitoring.

### 8.3. Run both nodes again and observe the same session read from Redis

Rebuild the JAR after adding dependencies:

~~~bash
./gradlew clean bootJar
~~~

Once Redis is ready, start A and B in two terminals as in Section 7.2. Save cookies to a new file so you do not reuse the Phase 1 local-session cookie:

~~~bash
curl -s -c cookies.redis.txt http://localhost:8081/visit
curl -s -b cookies.redis.txt http://localhost:8082/visit
curl -s -b cookies.redis.txt http://localhost:8081/visit
~~~

**Illustrative** responses:

~~~json
{"node":"A","sessionId":"same-shared-id","visits":1}
~~~

~~~json
{"node":"B","sessionId":"same-shared-id","visits":2}
~~~

~~~json
{"node":"A","sessionId":"same-shared-id","visits":3}
~~~

Observe closely: the returned `node` alternates A → B → A, while the logical session ID and `visits` persist **because both nodes read and write the same Redis**. The cookie name in this phase is typically `SESSION` rather than `JSESSIONID`; use `curl -i` if you want to inspect the actual `Set-Cookie` header.

**Limitation of this experiment:** these requests run **sequentially** to avoid read-modify-write races when two requests increment the counter at once. It proves session sharing, not atomicity of incrementing a value under concurrent requests.

## 9. How does Spring Session replace `HttpSession`?

In Servlet web apps:

~~~text
Browser -- Cookie: SESSION=S123 --> Node B
       |
       v
springSessionRepositoryFilter
       |
       v
SessionRepository.findById("S123")
       |
       v
Redis: attributes / lastAccessedTime / maxInactiveInterval
       |
       v
HttpServletRequest + HttpSession wrapper
       |
       v
Controller (HttpSession) -> setAttribute("visits", n)
       |
       v
Session saved according to repository/save/flush lifecycle
       |
       v
Response + cookie when needed
~~~

Spring Session uses `springSessionRepositoryFilter` to alter how the Servlet API retrieves and saves sessions. Consequently, the lab controller still uses `jakarta.servlet.http.HttpSession` as before. **Controller code never has to call Redis directly** to increment the counter or invalidate the session.

When the session expires in the repository, is deleted, or the ID does not exist, the request may be treated as a new/unauthenticated session depending on the endpoint and Spring Security. A shared store guarantees **retrieving state previously written to that store within its valid lifetime**, not that sessions live forever.

### Timeout: idle TTL differs from cookie lifetime

- `maxInactiveInterval` / `spring.session.timeout` expresses how long a server-side session may stay idle; accessing or modifying the session can refresh activity and TTL per repository rules.
- Default browser session cookies may live until the browser closes; persistent cookies have their own `Max-Age`.
- A cookie still being present **does not mean** the session remains in Redis. Conversely, deleting the cookie while Redis still holds the key prevents the browser from finding its session ID.
- A `SESSION` cookie lasting longer than Redis TTL causes the browser to send an expired ID; the app creates a new session or asks the user to sign in again.
- Never use `spring.cache.redis.time-to-live` to control Spring Session TTL; that property belongs to the cache abstraction, **not** session configuration.

For high-security requirements, consider adding an **absolute lifetime** from login, idle timeouts, logout policies, and session revocation alongside idle TTL.

## 10. A shared store does not automatically solve all race conditions

Suppose two **concurrent** HTTP requests from the same browser are routed by the LB to A and B:

~~~text
Initial Redis state: visits=3
A reads visits=3             B reads visits=3
A computes 4                 B computes 4
A saves 4                    B saves 4
Result can be 4 (one increment lost), not 5
~~~

Session attributes are **not distributed atomic counters**. If you need strict accuracy for order totals, inventory, financial transactions, or quotas, store that data in a DB or Redis primitive with atomic operations and proper transactions, locking, or optimistic concurrency. Never use `HttpSession` for cross-node business transactions.

Additional risks:

- **Serialization:** the Redis repository must serialize session attributes. `String`/`Integer` are simple; custom objects can break across nodes when class versions change or fail deserialization. By default, Spring Session Redis typically uses Java serialization; evaluate compatibility, serializer security, and synchronized version rollouts. A JSON Redis serializer can be configured, yet JSON is not automatically safe if unrestricted polymorphic type metadata is enabled.
- **Save mode:** repositories have modes that save only changed attributes or always save; choose per version and semantics, and never assume internal mutations inside a nested object are detected automatically. The safest habit in demos is calling `setAttribute` with a new value.
- **Network partitions:** a session readable on Node A can fail requests if Redis slows down or times out. Configure timeouts, bulkheads/circuit breakers as needed, and ensure auth never fails open when the store errors.
- **Redis failover:** asynchronous replication or persistence can lose recent unreplicated writes; “shared” does not mean “zero lost writes”.
- **Session size:** large session payloads force every request to transfer and serialize more bytes, increasing latency and Redis memory pressure. Store only small metadata—never complex full carts, uploaded files, or bulky query results.
- **Multi-version deploys:** Node A runs an old class version while B runs a new one; serialized objects may fail to decode. Verify backward compatibility or use JVM-class-independent versioned schemas.

## 11. Cookies, security, TLS, and session fixation

**A session ID is a bearer credential.** Anyone who can present a valid ID within the cookie/session store scope can hijack the session unless other defenses block them. Therefore:

1. Enforce **HTTPS** from browsers to public endpoints; set `Secure` on production cookies. Behind TLS termination, the app may see internal HTTP; configure forwarded headers and trusted proxies properly so the server detects scheme/cookie security accurately. Never let arbitrary clients spoof headers the app trusts.
2. Enable `HttpOnly` so page JavaScript cannot read the session cookie directly; this **does not eliminate all XSS risks**.
3. Choose `SameSite=Lax/Strict/None` suited to your traffic flows. `SameSite=None` in modern browsers usually requires `Secure`. **SameSite does not replace CSRF defenses** when cookies are sent automatically with requests.
4. Scope cookie `Domain` and `Path` as narrowly as needed, avoiding sharing cookies/sessions with untrusted apps or subdomains.
5. Rotate the session ID upon login or privilege elevation to mitigate session fixation; when using Spring Security, rely on its built-in session fixation protection and logout.
6. Logout/invalidation must delete or invalidate **the record in the shared store** as well as handle cookies; clearing the browser cookie without invalidating the store leaves the old session usable until timeout.
7. Never print raw `SESSION`/`JSESSIONID` values in logs, URLs, analytics, production JSON responses, or metrics labels.
8. Restrict Redis access to authorized apps only, with network isolation, ACL/auth, TLS where appropriate, patching, backups, and HA aligned with goals. Namespaces only separate keys; they are **not a security boundary replacing Redis ACLs**.

### Cookie configuration must match your version and resolver

For local Servlet container sessions, Spring Boot provides `server.servlet.session.cookie.*`. When Spring Session replaces the session filter/resolver, certain cookie details are governed by Spring Session's **`CookieSerializer`**. Do not assume changing a Tomcat property will always change Spring Session's `SESSION` cookie.

Example customization **in a Spring Session Servlet configuration class** (snippet to place inside an application `@Configuration` class, not standalone):

~~~java
@Bean
CookieSerializer cookieSerializer() {
    DefaultCookieSerializer cookie = new DefaultCookieSerializer();
    cookie.setCookieName("SESSION");
    cookie.setCookiePath("/");
    cookie.setUseHttpOnlyCookie(true);
    cookie.setUseSecureCookie(true); // production HTTPS
    cookie.setSameSite("Lax");
    return cookie;
}
~~~

Requires imports for `org.springframework.context.annotation.Bean`, `org.springframework.session.web.http.CookieSerializer`, and `org.springframework.session.web.http.DefaultCookieSerializer`. This snippet targets **production HTTPS**; if you enable `Secure` and test over local plain HTTP, browsers/cURL may omit the cookie. Test over HTTPS or adjust intentionally for dev environments. Never change cookie names differently between two nodes, or requests will not carry the same session key to both.

## 12. Session affinity is the LB's job; the session store is the app's job

Architecture diagram:

~~~text
                    Client
                      |
             HTTPS / Set-Cookie
                      |
                      v
                Load balancer
              routing + health
                /           \
               v             v
          Spring A         Spring B
       same app/version   same app/version
               \             /
                \           /
                   Redis HA
                   same namespace
~~~

**The LB must not route solely because Redis exists**: routing still needs health checks, retry policies, readiness, connection draining, and load distribution. Redis will not rescue a node suffering from CPU saturation, socket exhaustion, GC pauses, or buggy application code.

### When Node A crashes

**Sticky only + local session**:

~~~text
A dies -> LB routes request to B
B does not see A's RAM session
-> session usually lost / user must create a new session or log in again
~~~

**Shared store, session already saved cleanly**:

~~~text
A dies -> LB routes request to B
B reads session ID from Redis/JDBC
-> can continue using the unexpired session
~~~

Note that at the instant A dies, any in-flight request or unfinished transaction on A can still be lost, and session mutations not yet flushed to the store will not exist on B. Failover **does not mean safely replaying** requests like payments. Side-effecting workflows need their own idempotency and transaction controls.

### Rolling deployments and draining

When replacing nodes:

1. Mark the old node **not ready** so the LB stops sending new requests.
2. Give in-flight requests time to finish (graceful shutdown) within a defined deadline.
3. With shared sessions, new nodes use the same store/namespace and compatible schemas.
4. Monitor session miss/logout rates, store latency, deserialization errors, and error rates after rollout.

Sticky routing does not migrate RAM sessions to new nodes; even with network-level "zero downtime", user state can vanish when old nodes terminate. Shared stores reduce this risk, provided session compatibility holds across versions.

### Can session affinity still help when Redis is present?

Possibly, though it is not required by default. Some systems use affinity to reduce node switching for local cache locality or specialized workloads, while still ensuring every request reads state from the shared store and tolerates node switches. If an app works **only when sticky**, an unaddressed local-state dependency still exists; do not claim Redis has fully solved the problem.

## 13. Session store failover is its own problem

Redis/JDBC is critical infrastructure. If Redis is a **single instance with no persistence** and crashes, every Spring Boot node may lose the ability to read sessions. Moving Redis to Cluster/Sentinel/managed HA raises availability, yet still requires checking:

- **Replication lag/durability:** were recently updated session records replicated before failover?
- **Eviction policy and memory pressure:** Redis evicting keys due to full memory logs users out early before timeout; size memory/quotas and choose eviction policies intentionally.
- **TTL expiration:** keys expire properly, though deletion/expiry timing is not exact to the millisecond; never rely on Redis TTL alone to guarantee “logout at exact legal deadline X” without extra enforcement.
- **Connection pools, timeouts, circuit breakers:** a slow store can stall the entire web fleet; track p95/p99 latency and error rates.
- **Backup/recovery:** sessions can hold sensitive data; backups must be secured with proper retention. Restoring an old backup can resurrect sessions that policy required invalidated—evaluate carefully.
- **Readiness vs. liveness:** transient Redis errors do not necessarily require killing every pod, though nodes cannot serve session-dependent requests. Design health/readiness probes around SLOs and degradation policies to avoid restart storms.

If Redis is unreachable, never “temporarily log in” a user from an unverified cookie ID. For authenticated endpoints, **fail closed** or follow an explicitly verified recovery policy instead of fabricating access.

## 14. Relationship between sticky sessions and Spring Security

When Spring Security configures session-based login, `SecurityContext` is commonly stored in or linked to the server-side session. In a non-sticky multi-node local store, requests hitting B miss the authentication, producing 401s or login redirects. With Spring Session, authentication data lives in the shared repository so nodes behave consistently.

However, **Spring Session does not enable authentication or authorization by itself**. You still need Spring Security to configure the filter chain, login/logout, CSRF, session fixation, concurrency control, and timeouts. For purely stateless bearer-token APIs, the app might not use `HttpSession` for authentication at all; adding sticky routing or Redis just to “keep users logged in” would solve the wrong problem.

Consider session events (`created`/`destroyed`/`expired`) and concurrent-session control: some features require an indexed repository and event processing, which are not automatically identical across all repositories. If requirements include “single-device login” or “admin revokes all sessions”, pick a repository and event configuration that support them and test thoroughly.

Do not store overly complex custom `Authentication` objects without testing serialization and compatibility. Changes to Spring Security versions or domain classes across releases can trigger deserialization failures during rolling deployments.

## 15. Differences in Spring WebFlux applications

WebFlux uses **`WebSession`** from the reactive web stack, not Servlet `HttpSession`. Load balancing fundamentals remain similar: per-node local sessions break when requests switch nodes, while Spring Session can integrate Redis to supply distributed reactive sessions.

Illustrative snippet reading `WebSession` in WebFlux:

~~~java
@GetMapping("/reactive-visit")
Mono<Integer> visit(ServerWebExchange exchange) {
    return exchange.getSession().map(session -> {
        Integer count = session.getAttribute("visits");
        int next = (count == null ? 1 : count + 1);
        session.getAttributes().put("visits", next);
        return next;
    });
}
~~~

This is a **snippet** inside a WebFlux `@RestController`, not a standalone Java class. With WebFlux, declare the webflux + reactive Spring Session Redis dependencies and let Spring Boot auto-configure where appropriate, or explicitly configure `@EnableRedisWebSession` for manual management. **Never** drop `jakarta.servlet.http.HttpSession` into a pure WebFlux app.

Be careful with reactive session stores: I/O operations require a reactive repository and must never call `block()` on the Netty event loop. An app carrying both `spring-boot-starter-web` and `spring-boot-starter-webflux` usually causes Boot auto-detection to select Servlet/MVC; verify the active web application type before choosing a solution.

## 16. Meaningful testing: from local state to shared state

### Test A — Local, no affinity

Start two instances without Spring Session/Redis (Section 7). Use A's cookie to call B:

- First call to A creates a local session, `visits=1`.
- Second call to A with the same cookie increments `visits=2`.
- Call to B with A's cookie creates a new session, `visits=1`.

This outcome is **correct behavior for local RAM storage**, and exposes the risk under round-robin LB.

### Test B — Sticky, local session

Configure LB `ip_hash` or vendor sticky-cookie rules, then call **a single LB address** multiple times with a cookie jar:

~~~bash
curl -s -c cookies.lb.txt http://localhost:8090/visit
curl -s -b cookies.lb.txt http://localhost:8090/visit
curl -s -b cookies.lb.txt http://localhost:8090/visit
~~~

You will normally observe the same node and `visits=1,2,3` while the LB preserves affinity without failures. Stop the chosen node and call again: the LB fails over and local state is lost. With `ip_hash`, one IP tends to hit A; if topology changes shift the LB's mapping, results change too.

**Never run container/node-kill tests in production.** Use a lab or staging environment to verify failover.

### Test C — Shared Redis, no affinity required

Start the same two instances with Spring Session + Redis (Section 8) and alternate ports while keeping the same cookie:

~~~bash
curl -s -c cookies.shared.txt http://localhost:8081/visit
curl -s -b cookies.shared.txt http://localhost:8082/visit
curl -s -b cookies.shared.txt http://localhost:8081/visit
~~~

Expect `node=A,B,A` and `visits=1,2,3` with the same logical session ID while unexpired. Because Redis is shared, LB stickiness is unnecessary for this test.

Next, stop Node A and keep calling Node B with the saved cookie: `visits` should keep incrementing as long as earlier writes flushed to the store and Redis retains the data. To test timeout, wait longer than `spring.session.timeout` in the lab (or configure a short value *strictly for testing*) and request again; expect the session to be treated as expired, resetting the count or requiring re-login per policy.

### Test D — Concurrent calls to expose races

Send multiple concurrent requests with the same cookie to A/B and compare the counter. If increments are missing, that proves `getAttribute` → `setAttribute` is a **non-atomic read-modify-write**. Never use a session counter as an exact source of truth; switch to Redis atomic `INCR` or a business DB transaction when accuracy matters.

### Test E — Simulating store failures

In the lab, temporarily make Redis unreachable and observe how session-dependent requests fail and whether the app recovers once Redis returns. Simulate a rolling deploy where Node A and Node B run different versions of a session entity class to catch serializer compatibility issues. Verify that failures never bypass authentication or leak stack traces/session IDs.

## 17. Symptom-based troubleshooting

| Symptom | Likely cause | How to verify |
| --- | --- | --- |
| Login succeeds, then next request randomly logs out | Local session; LB routed to another node | Log node name, cookie name, and session repository; test same cookie against each port directly |
| Even with sticky sessions, rolling deploys log users out | Old node shut down, wiping RAM sessions | Check drain/affinity; need a shared store or session migration policy |
| Redis is configured, yet each node creates a different session | Mismatched cookie name/path/domain, different Redis namespace/DB, or Spring Session not enabled | Compare effective configs, `Set-Cookie`, dependencies, and store keys |
| Redis throws deserialization errors during deployment | Incompatible session attribute class versions across builds | Check serializer, schema, and rolling deployment strategy |
| User logged out after 30m even though browser keeps cookie | Server-side session TTL expired | Check `spring.session.timeout`, clocks, and last-accessed time |
| Configured `spring.cache.redis.time-to-live` yet sessions unchanged | Edited cache abstraction TTL instead of session TTL | Use the proper session timeout property |
| Redis works fine, yet visit counter loses counts under load | Read-modify-write race across concurrent requests | Use atomic business storage or concurrency control |
| NGINX `ip_hash` piles many users onto A | Shared source IP behind NAT/proxy | Choose another affinity mechanism or shared store without stickiness |
| Login loops over HTTPS, works over localhost HTTP | Wrong cookie `Secure`, forwarded proto/host/path, or `SameSite` | Inspect sent/received cookies and trusted proxy config |
| Login works on A, B ignores `SecurityContext` | Session/auth context not shared or inconsistent security config | Check Spring Security session config and shared store |
| Redis evicts keys, logging users out early | Memory pressure / eviction policy | Check Redis memory, evicted keys, TTL, and capacity |
| Redis outage takes down entire fleet | Shared store dependency without proper HA/failover | Review Redis topology, timeouts, retries, and readiness behavior |

**Suggested investigation workflow:**

1. Confirm which node the LB picked for each request via node labels or trace IDs.
2. Check whether `JSESSIONID` or `SESSION` is sent by the client for the exact domain/path/HTTPS; never paste real IDs into public tickets.
3. Inspect the effective session repository config on both nodes: local vs. Spring Session, Redis endpoint, DB index, namespace, serializer, and timeout.
4. Correlate store metrics, request logs, expirations/evictions, and node restarts around the logout timestamp.
5. Run manual tests with the same cookie from A → B directly to isolate cookie bugs, LB affinity, and shared persistence.
6. Test failover, rolling deploys, concurrent requests, and security flows before claiming the system meets HA requirements.

## 18. Pre-deployment architecture checklist

- **State:** What does the session contain? Is a server-side session truly needed, and are there heavy objects or secrets?
- **Routing:** Does the LB use round-robin, IP hash, cookie affinity, or another algorithm? How are in-flight requests handled when a node loses readiness?
- **Storage:** If using Redis/JDBC, do all nodes share the same store/namespace with HA matching SLOs?
- **Lifecycle:** Are idle timeout, absolute lifetime, cookie `Max-Age`, logout, invalidation, and session fixation defined consistently?
- **Security:** Are HTTPS + `Secure`/`HttpOnly`/`SameSite`, CSRF, trusted proxies, session ID secrecy, authorization, and Redis access controls in place?
- **Consistency:** Two concurrent requests for the same session can hit two nodes; is transactional business data stored outside the session?
- **Serialization:** During rolling deploys, can old and new versions read each other's session attributes?
- **Operations:** Are session counts, session misses, Redis p95 latency, errors, evictions, memory, store failover, and node distribution monitored/alerted?
- **Release:** Were A→B tests with the same cookie, node failures, scale-in, and restarts tested in staging?

Never rely on sticky routing alone when an application requires sessions to survive node failures. Never assume Redis equals “complete HA” if Redis itself or serialization remains a single point of failure.

## 19. Self-check questions

**1.** An LB alternates requests between A and B, and both nodes use only in-memory `HttpSession`. Why can the browser lose its shopping cart?

**Answer:** Session attributes live in A's RAM; B does not automatically have them. The cookie ID still exists, yet B's local repository lacks the corresponding data.

**2.** Does enabling a sticky cookie on the LB move sessions from A to B when A crashes?

**Answer:** No. Stickiness controls routing, not session replication. When A dies, B cannot read A's RAM.

**3.** Does a shared Redis store with two nodes running the same app require sticky routing to keep `HttpSession` working?

**Answer:** Usually no; both A and B can read the saved session using the same ID. Stickiness is only an optional routing/optimization choice if specifically needed.

**4.** Why doesn't a sequential Redis test showing `visits=1,2,3` prove the counter is safe under concurrent requests?

**Answer:** Two concurrent requests can both read 1 and both write 2, causing a lost update. A session repository is not automatically a business transaction.

**5.** The browser sends a `SESSION` cookie, yet the Redis key has expired. Can Node B resume the old session?

**Answer:** No. The cookie carries only the ID, not the attributes. The app may create a new session or require login.

**6.** Is using `HttpSession` and `spring.servlet.session.timeout` appropriate in a Spring Boot WebFlux app?

**Answer:** For pure WebFlux, use `WebSession` and a reactive session repository. Do not transplant Servlet code directly into WebFlux.

**7.** If Redis has an outage, should requests be authenticated using the cookie ID without checking the store?

**Answer:** No; the ID cannot be verified or resolved to authentication state. The system should fail closed or follow an explicitly verified recovery policy.

**8.** The session cookie has `Secure`, yet you are testing over `http://localhost`; why might the A→B test fail?

**Answer:** Secure cookies may not be sent over plain HTTP depending on the client and localhost exceptions; test production policies over HTTPS or adjust local dev configuration intentionally.

## 20. Official references

- [Spring Boot 3.4 — Spring Session](https://docs.spring.io/spring-boot/3.4/reference/web/spring-session.html): auto-configuration of session repositories, timeouts, and when manual config causes Boot to back off.
- [Spring Session 3.1 — Spring Boot Redis Guide](https://docs.spring.io/spring-session/reference/3.1/guides/boot-redis.html): `spring-session-data-redis` dependency, Redis connection config, `springSessionRepositoryFilter`, and session cookies.
- [Spring Session — HttpSession Integration](https://docs.spring.io/spring-session/reference/http-session.html): replacing `HttpSession` via Servlet filter, session repositories, and cluster support.
- [Spring Session — Redis Configurations](https://docs.spring.io/spring-session/reference/configuration/redis.html): namespaces, serializers, `RedisSessionRepository`, indexed repository options, and expiry handling.
- [Spring Session 3.3 — WebSession Integration](https://docs.spring.io/spring-session/reference/3.3/web-session.html): reactive `WebSession` and Redis in WebFlux.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): session fixation protection, invalidation, and authentication policies.

**Conclusion:** In multi-instance Spring Boot deployments, **sticky sessions** pin clients to one node but cannot preserve RAM when a node dies. **Spring Session + Redis/JDBC** externalizes session state to a store accessible by all nodes, supporting node replacement cleanly. Both still require proper cookies, timeouts, security, serialization compatibility, monitoring, and failover testing; sessions are not the place for atomic business transactions.
