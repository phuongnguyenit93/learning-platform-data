# Shared Session Store When Running Multiple Application Nodes

> **Module:** Spring Security - fundamentals  
> **Group:** Sessions and cookies  
> **Core:** A login session can span multiple instances when all of them share an `HttpSession` store and look up the same session ID from the cookie. Sharing the cookie without sharing server-side state is not enough.

## 1. Learning Objectives

After reading this lesson, you will be able to:

- Explain why logging in on node A can still prompt for login when a request hits node B.
- Distinguish session cookies, session IDs, session attributes, and Spring Security's `SecurityContext`.
- Compare sticky sessions and a shared (distributed) session store.
- Configure Spring Session Redis for Spring Boot Servlet/Spring Security and run two independent instances sharing the same Redis.
- Test login, cross-node A/B access, logout, timeouts, and handling Redis failures.
- Identify security, consistency, serialization, and operational requirements for a shared session store.

## 2. The Multi-Node Problem

Web applications are commonly deployed as multiple replicas behind a load balancer:

~~~text
                Browser
             Cookie: SESSION=xyz
                    |
                    v
              Load Balancer
                /       \
               v         v
           App Node A  App Node B
            port 8081   port 8082
~~~

If each instance uses the Servlet container's default in-memory sessions, the following sequence can happen:

1. Alice logs in via node A; node A stores session state and authentication info in local memory.
2. The browser holds the cookie containing the server-issued session ID.
3. The next request lands on node B and sends the same cookie.
4. B does not have a session matching that ID in its own RAM.
5. B cannot restore Alice's security context and may redirect back to the login page.

Symptoms: flaky sessions, getting logged out on refresh, disappearing shopping carts, multi-step workflows restarting, or bugs appearing only when scaling replica count up.

**Key distinction:** the cookie arriving at B does not mean B has the session data. A cookie usually holds only an opaque identifier to look up server-side state, not the entire user object.

### Three layers involved

| Component | Location | Meaning |
| --- | --- | --- |
| Session cookie, e.g. `SESSION` | Browser, sent per Domain/Path/SameSite/Secure | Holds the session ID for server lookup |
| Server-side session | Container RAM, Redis, or shared store | Holds attributes, metadata, expiration, workflow state |
| Spring `SecurityContext` | Per-request security context; may be persisted into session | Holds `Authentication` and authorities for subsequent processing |

A session ID is an important bearer credential. Anyone capturing a still-valid ID can impersonate the session; never log IDs publicly or return session IDs in JSON responses.

## 3. Sticky Sessions vs. Distributed Sessions

### Sticky sessions

The load balancer uses session affinity to route Alice's requests consistently to node A:

~~~text
Alice -> LB -> A -> A -> A
Bob   -> LB -> B -> B -> B
~~~

This can keep legacy apps using local sessions working while routing holds steady. However, if A restarts, scales in, crashes, or the load balancer changes routes, B still lacks A's RAM. Sticky routing also skews load distribution and creates coupling to LB policy.

### Shared session store

Nodes read/write sessions to a shared store such as Redis:

~~~text
               Browser: SESSION=sid-42
                         |
                         v
                    Load Balancer
                       /     \
                      v       v
                    Node A   Node B
                      \       /
                       v     v
                        Redis
               sid-42 -> session attributes
                         SecurityContext
                         expiry metadata
~~~

Node A can write a session, and Node B can use the same cookie/session ID to read it back. Instances must align on backend, namespace, serializer, and cookie handling. Once data is persisted in the shared store, switching nodes no longer drops the session automatically.

Sticky sessions and a Redis store are not mutually exclusive, yet correctness for apps requiring failover **should not depend** on sticky routing.

## 4. How Do Spring Session and Spring Security Integrate?

In a **Servlet/Spring MVC** application, Spring Session provides a filter and `SessionRepository` replacing the standard `HttpSession` implementation. With a Redis backend:

~~~text
HTTP request + Cookie SESSION
         |
         v
Spring Session filter reads session ID
         |
         v
Redis SessionRepository finds session attributes
         |
         v
Wrapped HttpServletRequest/HttpSession
         |
         v
Spring Security restores SecurityContext if using session persistence
         |
         v
Controller/service reads or updates HttpSession
         |
         v
Spring Session saves changed data back to Redis
~~~

Spring Security is responsible for **authentication** and **authorization**; Spring Session is responsible for storing and looking up sessions. Redis does not verify usernames/passwords on its own.

With form login, `SecurityContext` after successful authentication is typically persisted to `HttpSession` via the appropriate Spring Security mechanism. When Spring Session swaps the backend to Redis, nodes can restore the same context.

Do not assume every app must store `SecurityContext` in a session: stateless JWT/Bearer APIs can authenticate each request without needing sessions to identify users.

## 5. Hands-On Java 17+ Example: Two Processes Sharing Redis

The following example uses Java 17+, Gradle 8.x, Spring Boot 3.3.5, Spring Security 6.x, and Spring Session Redis managed by the Boot BOM. It uses default form login so authentication restoration can be observed directly.

Test setup: A runs on port 8081, B on 8082, local Redis on 6379. The same browser hits **localhost** on both ports; cookies are scoped by host, not by port.

### 5.1. Project structure

~~~text
shared-session-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/cluster/
    │   ├── SharedSessionApplication.java
    │   ├── SecurityConfig.java
    │   └── SessionController.java
    └── resources/
        └── application.properties
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'shared-session-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.session:spring-session-data-redis'
}
~~~

Explanation:

- Starter Web provides Tomcat and the Spring MVC/Servlet stack.
- Starter Security provides the security filter chain and form login.
- Starter Data Redis provides `RedisConnectionFactory` and the Redis client.
- `spring-session-data-redis` integrates the Redis-backed `SessionRepository` and matching filter; Spring Boot handles auto-configuration.
- Use Boot-managed dependency versions to avoid pairing incompatible Spring Session/Security releases.

### 5.2. Main application

File `src/main/java/demo/cluster/SharedSessionApplication.java`:

~~~java
package demo.cluster;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SharedSessionApplication {
    public static void main(String[] args) {
        SpringApplication.run(SharedSessionApplication.class, args);
    }
}
~~~

### 5.3. Spring Security form login

File `src/main/java/demo/cluster/SecurityConfig.java`:

~~~java
package demo.cluster;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/health").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }
}
~~~

The password `demo-pass` is solely for local demo use; never expose this account in a public environment. Both instances share the same user configuration, yet session sharing between nodes comes from the **Redis session store**, not from having the same password.

CSRF protection stays enabled by default for form login. Do not disable CSRF to avoid session friction; Spring Security's default login page handles the form token automatically.

### 5.4. Controller storing a counter in `HttpSession`

File `src/main/java/demo/cluster/SessionController.java`:

~~~java
package demo.cluster;

import java.util.Map;
import jakarta.servlet.http.HttpSession;
import org.springframework.core.env.Environment;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionController {

    private final Environment environment;

    public SessionController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/public/health")
    public String health() {
        return "ok";
    }

    @GetMapping("/")
    public Map<String, Object> home(
            Authentication authentication, HttpSession session) {
        Integer oldCount = (Integer) session.getAttribute("counter");
        int count = (oldCount == null ? 0 : oldCount) + 1;
        session.setAttribute("counter", count);

        return Map.of(
            "node", environment.getProperty("server.port", "8081"),
            "user", authentication.getName(),
            "counter", count
        );
    }
}
~~~

Important: the counter is stored in `HttpSession`, **not** a controller field or static variable. If A writes `counter` to the session and B reads that counter back, they are sharing state. The response never exposes the session ID.

`oldCount + 1` is only safe as an illustration for sequential requests; with two concurrent requests, read-modify-write can lose updates. Never use `HttpSession` like a transactional database for real balances/quotas.

### 5.5. Redis and session configuration

File `src/main/resources/application.properties`:

~~~properties
server.port=8081

# Both instances use the same Redis.
spring.data.redis.host=localhost
spring.data.redis.port=6379

# Server-side inactivity timeout.
server.servlet.session.timeout=30m

# Same namespace across all nodes, isolated from other applications.
spring.session.redis.namespace=learning:shared-session-demo

# Illustrative flush mode configuration.
spring.session.redis.flush-mode=on_save

# Basic cookie protection on local demo.
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
~~~

In Spring Boot with the Spring Session Redis dependency and matching Redis auto-config, you usually **do not need** to add `@EnableRedisHttpSession` manually to your project. The Spring Session filter is registered by Boot auto-configuration.

Instances must remain consistent:

| Configuration | Node A | Node B |
| --- | --- | --- |
| Redis host/port | `localhost:6379` | `localhost:6379` |
| Redis namespace | `learning:shared-session-demo` | `learning:shared-session-demo` |
| Security/session serializer | Same version / compatible config | Same version / compatible config |
| Public hostname | `localhost` | `localhost` |
| HTTP port | `8081` | `8082` |

When running on two separate machines, `localhost` **no longer** points to the same Redis. Both must point to a shared Redis hostname over a private network. That is a frequent source of failure when moving from local demos to Kubernetes or multiple VMs.

### 5.6. Running Redis

If Docker is installed and local port 6379 is free:

~~~bash
docker run --name shared-session-redis -d -p 127.0.0.1:6379:6379 redis:7
~~~

The Redis port in the demo binds only to host loopback to avoid accidentally exposing the Redis server publicly. If a container already exists or your environment provides its own Redis, use that instance instead of creating a new one.

Verify Redis:

~~~bash
docker exec shared-session-redis redis-cli ping
~~~

Expected stdout:

~~~text
PONG
~~~

### 5.7. Build once, run two instances

In the project directory:

~~~bash
gradle bootJar
~~~

With the example configuration, the JAR is expected at `build/libs/shared-session-demo-0.0.1-SNAPSHOT.jar`.

Terminal A:

~~~bash
java -jar build/libs/shared-session-demo-0.0.1-SNAPSHOT.jar --server.port=8081
~~~

Terminal B:

~~~bash
java -jar build/libs/shared-session-demo-0.0.1-SNAPSHOT.jar --server.port=8082
~~~

These are **two processes** running the same JAR; overriding the port does not affect the Redis namespace. In production, the two processes may live in separate containers behind a load balancer.

### 5.8. Testing in the browser

1. Open `http://localhost:8081/`. Because you are not logged in, Spring Security redirects to the login form.
2. Enter username `alice` and password `demo-pass`. Default form login handles the CSRF token and creates/saves the needed session.
3. After returning to `/`, example body:

~~~json
{"node":"8081","user":"alice","counter":1}
~~~

4. In the same browser profile, open `http://localhost:8082/`. **Without logging in again**, example output:

~~~json
{"node":"8082","user":"alice","counter":2}
~~~

5. Go back to `http://localhost:8081/`, example output:

~~~json
{"node":"8081","user":"alice","counter":3}
~~~

JSON key order is not guaranteed; only the values matter here. Counter values assume sequential requests without extra prefetch/refresh calls hitting `/`.

**PASS criteria:** moving the same browser from A to B remains authenticated, and the `counter` state keeps incrementing instead of resetting to 1. Visiting two different hostnames (`localhost` and `127.0.0.1`) may not send the same cookie; that is cookie policy, not proof that Redis is broken.

### 5.9. Inspecting the Redis namespace

In the demo environment:

~~~bash
docker exec shared-session-redis redis-cli --scan --pattern 'learning:shared-session-demo:*'
~~~

Actual session keys may contain session IDs. Never copy them into logs, tickets, or public docs. Never run `FLUSHALL` or `KEYS *` followed by bulk deletion on a shared Redis instance.

To verify the dependency on Redis, try stopping Redis **in your learning environment** and observe that the app cannot read/write sessions; never test that on a system with real users.

## 6. Cookies, TTL, Timeouts, and Session Fixation

Browsers normally hold a cookie named `SESSION` when using Spring Session; with only Servlet container local sessions, the name is usually `JSESSIONID`. Names can be customized; **never infer the entire backend architecture solely from the cookie name**.

### The cookie does not contain the whole session

~~~http
GET / HTTP/1.1
Host: example.com
Cookie: SESSION=<opaque-id>
~~~

The cookie carries the ID used to look up the session in Redis. Never put passwords, principal details, shopping carts, or `SecurityContext` directly inside a session ID cookie by default.

### Important cookie attributes

| Attribute | Purpose |
| --- | --- |
| `HttpOnly` | Reduces ability of JS to read cookies via `document.cookie`; does not solve all XSS |
| `Secure` | Sends cookie only over HTTPS in browser-supported contexts |
| `SameSite` | Restricts certain cross-site cookie-sending cases; does not replace CSRF |
| `Path` | Restricts request paths receiving the cookie |
| `Domain` | Controls domains/subdomains sharing the cookie; avoid overly broad scope |
| `Max-Age`/`Expires` | Browser-side cookie lifetime, **distinct** from server-side idle timeout |

Production should run HTTPS and set `Secure`, `HttpOnly`, and appropriate SameSite/Domain/Path. When TLS terminates at a reverse proxy, configure trusted forwarded headers/transport so the server determines the scheme accurately.

### Server-side timeout

`server.servlet.session.timeout=30m` specifies the max inactive interval in the demo. A session can expire in Redis even while the browser still holds the old cookie; the request must be treated as lacking a valid session.

Redis TTL/expiry events do not guarantee cleanup notifications fire at the exact millisecond. Applications must rely on valid session state during lookup, not treat a Redis pub/sub event as the sole proof.

### Session fixation protection

When a user logs in, Spring Security normally rotates the session ID on modern Servlet containers to reduce session fixation risk. With Spring Session, ID rotation must work cleanly with the session repository and new cookie. Never "pin" a session ID on the client or store the ID as an immutable business key.

### Cross-node logout

Try this: log in on A, access B successfully, log out on B, then go back to A. Requests to protected resources on A must prompt for login again once the session has been invalidated. A shared store makes invalidation visible across all nodes, yet the application must also implement logout and cookie handling properly.

## 7. Two Redis Session Repository Options

Spring Session Redis supports two primary implementations:

| Repository | Characteristics | When suitable |
| --- | --- | --- |
| `RedisSessionRepository` | Saves/retrieves sessions by ID without maintaining extra indexes | Most basic session lookup needs |
| `RedisIndexedSessionRepository` | Maintains extra indexes to look up sessions by principal and handle certain expiry/deletion events | When you need to find all user sessions or event-driven lifecycle flows |

In modern Spring Boot configurations, `RedisSessionRepository` is typically the default; properties like `spring.session.redis.repository-type=default` or `indexed` select the mode in corresponding releases.

Do not enable `indexed` assuming it is "faster." It adds index/event overhead and carries Redis Cluster caveats. Spring Session docs warn that the indexed repository can subscribe to expiry events on a single random cluster node, leaving incomplete index cleanup when keys expire on other nodes. Features such as index-based global logout must be tested on your actual topology.

This demo only needs the basic repository to look up sessions by ID.

## 8. Serialization and Rolling Deployments

Session attributes must serialize when written to Redis and deserialize when read by another node. By default, Spring Session Redis uses Java serialization; stored objects must be serializable and compatible across instances.

Example:

~~~text
Node A running CartState version v1
    -> serializes into Redis session

Node B just rolled out incompatible CartState v2
    -> deserialization error or reads corrupted data
    -> request/session fails
~~~

Guidelines:

- Never store overly large objects, repositories, datasources, sockets, or service beans in sessions.
- Keep only necessary data with stable structures, and verify version compatibility during rolling deployments.
- Never swap serializers mid-flight without a migration or session invalidation plan.
- For custom serialization, Spring Session supports a `springSessionDefaultRedisSerializer` bean, which must stay compatible with `SecurityContext` and Spring Security types.
- Never allow untrusted parties to write session keys; deserializing untrusted data is a security vulnerability.

Simply connecting two nodes to the same Redis is not enough if classpaths, schemas, or serializers are incompatible.

## 9. Concurrent Session Writes and Data Consistency

A shared session store solves cross-node state lookup; **it does not provide a distributed transaction across all operations**.

Example of two requests both reading `counter=4`:

~~~text
Node A: read 4 -> set 5
Node B: read 4 -> set 5
Node A: save 5
Node B: save 5

Two requests yet final counter may be 5, not 6.
~~~

This is a lost update from read-modify-write on the same session. If balances, quotas, or shopping carts require strict concurrency semantics, use atomic updates, optimistic locking, or separate transactional business storage rather than expecting `HttpSession` to solve every race.

### Flush mode

- `ON_SAVE`: saves when the repository saves; in web flows, usually before the response commits.
- `IMMEDIATE`: attempts to flush session changes to Redis earlier as values are mutated.

Flush mode affects write frequency and visibility timing between requests, yet does not automatically provide atomicity or resolve conflicts across nodes.

## 10. Operating Redis as a Security Component

Once sessions are stored in Redis, Redis is no longer an optional cache—it is a **critical login dependency**.

### Availability

- A Redis outage can cause request errors or make sessions unrecoverable.
- Consider Redis Sentinel, Cluster, or managed HA services depending on SLA.
- Monitor latency, memory, evictions, connection pools, errors, backups/restores, and failover.
- Choose eviction/memory policies deliberately; an eviction can log users out unexpectedly.
- With Redis Cluster, review indexed repository limitations, expiry events, and topology constraints.

### Connection security

- Never expose the Redis port to the public Internet.
- Prefer private networks, TLS, ACLs/passwords, and secret rotation per deployment policy.
- Isolate namespaces and access privileges per application.
- Never dump/log session data, credentials, serialized `SecurityContext`, or session IDs unnecessarily.
- Use proper auditing to detect unauthorized session access.

### Permission changes while a session is active

Sharing a store does not mean every session immediately updates its authorities when a role is revoked in the database. Sessions can retain the `Authentication` captured at login. For sensitive operations, you need revalidation, session invalidation, or context refresh policies.

### Stateless JWT is a different case

If all endpoints verify JWT/Bearer tokens on every request and use `SessionCreationPolicy.STATELESS`, a Redis-backed `HttpSession` may not be needed to recognize users across nodes. Nodes only need to trust the same issuer/keys/policies. Do not mix the stateless model with expectations of form-login session persistence without explicit design.

## 11. Distinguishing Servlet `HttpSession` and WebFlux `WebSession`

The demo uses **Spring MVC/Servlet**. Spring WebFlux applications use `WebSession` and reactive Spring Session integration, which differ in API and filters from `HttpSession`.

Do not copy `@EnableRedisHttpSession` or Servlet-specific filters verbatim into a pure WebFlux app and assume reactive sessions are properly shared. Reactive security contexts use Reactor Context; when server-side sessions are needed, choose a reactive Redis session repository and matching configuration.

On both stacks, the core principle remains: one client holds a session ID and multiple nodes must access the same shared session state rather than relying on a single node's local RAM.

## 12. Multi-Node Acceptance Test Suite

| Scenario | Test action | Expected |
| --- | --- | --- |
| Login | Browser hits A, logs in | Valid session cookie issued, A returns user Alice |
| Cross-node | Same browser hits B | No re-login required, B returns user Alice |
| Shared state | A increments counter, B visits | Counter keeps incrementing across both nodes |
| Back to A | B then A | Session does not reset |
| Logout | Log out on B, access protected route on A | A prompts to log in again |
| Restart | Restart A while Redis stays up | B continues the still-valid session |
| Timeout | Inactivity interval elapses | Neither A nor B accepts the old session |
| Different cookie host | Switch `localhost` to `127.0.0.1` | Cookies are not automatically shared across different hosts |
| Concurrent updates | Two requests edit the same session simultaneously | Understand lost-update risk; do not assume +2 |
| Redis down | Stop Redis in test environment | Errors handled per policy; never assume fail-open |

### Troubleshooting

| Symptom | What to check |
| --- | --- |
| B asks to log in again | Cookie host/path/name, Redis host/namespace, serializer, security persistence |
| Counter is always 1 | Cookie not sent, session not saved, timeout/eviction, or wrong hostname |
| Errors after rolling update | Incompatible session object schema/serialization change |
| Works intermittently | Load balancing, Redis availability, cookie scope, data races |
| Logout does not apply cluster-wide | Session invalidation/persistence, mismatched cookies, local cache |
| Redis full and users logged out | Eviction policy, TTL, memory, error handling |
| Session data updates inconsistently | Concurrent writes, flush/save mode, code using static/local state |

## 13. Practical Checklist

- [ ] Confirm the app **genuinely needs stateful sessions**, rather than being a purely stateless API.
- [ ] All nodes share the same Redis endpoint, session namespace, serializer, and compatible security configuration.
- [ ] Cookie scope matches public host/path; production enforces HTTPS, `Secure`, `HttpOnly`, and appropriate `SameSite`.
- [ ] Never log session IDs or store unnecessary secrets in sessions.
- [ ] Login, A-to-B routing, logout, timeouts, and restarts are tested across at least two instances.
- [ ] Plan session data compatibility/migration during rolling deployments.
- [ ] Never use shared `HttpSession` as the authoritative store requiring atomic consistency.
- [ ] Plan for Redis HA, monitoring, network isolation, credentials, and failure modes.
- [ ] Have an invalidation policy when accounts/roles change.
- [ ] Never disable CSRF or strip security filters just to make session testing easier.

## 14. Self-Check Questions

**Question 1.** Why is the cookie still sent by the browser yet node B asks to log in again?

**Answer:** The cookie carries only the session ID. If B cannot read the attributes/`SecurityContext` matching that ID from the same session store, B cannot restore A's identity.

**Question 2.** Can sticky sessions replace a shared session store?

**Answer:** Not completely. Affinity pins requests to one node while routing is stable; if that node goes down or routes shift, local RAM sessions still cannot migrate automatically.

**Question 3.** Both nodes connect to Redis yet do not share sessions: why?

**Answer:** They may differ in namespace, cookie ID/scope, session repository, serializer, or `SecurityContext` persistence. Inspect both the save chain and the read chain.

**Question 4.** Does Spring Session Redis make incrementing a session counter atomic across nodes?

**Answer:** No. Concurrent read-modify-write can cause lost updates; choose a dedicated mechanism if atomicity is required.

**Question 5.** Does stateless JWT require a Redis-backed `HttpSession` to run across multiple nodes?

**Answer:** No. If verifying bearer tokens on every request without needing stateful sessions, nodes can operate without storing login state in Redis.

**Question 6.** Why shouldn't the `SESSION` cookie value be printed into a JSON response for debugging?

**Answer:** A still-valid session ID can be used to hijack the session. Observe safely, protect logs, and never expose IDs.

## 15. Summary and Further Reading

**A shared session store solves the problem of session data living isolated in each node's RAM.** The cookie carries the session ID; Spring Session Redis maps that ID to attributes on a shared backend; Spring Security can restore `Authentication` via the `SecurityContext` persisted in the session. For the system to operate correctly and securely, nodes need matching Redis/namespace/serializers, proper cookie scopes, and clear policies for timeouts, logout, HA, and concurrency.

Official documentation:

- [Spring Session — Spring Boot + Redis](https://docs.spring.io/spring-session/reference/guides/boot-redis.html)
- [Spring Session — Redis Configurations](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Session — WebSession Integration](https://docs.spring.io/spring-session/reference/websession.html)
