# Spring Session for multiple nodes and the limits of local session stores

## Lesson objectives

In a Spring Security Servlet application, form login is typically tied to an **HTTP session**: after successful authentication, the user carries a session cookie across subsequent requests and the server restores `SecurityContext` for authorization. When the application runs on a single JVM, storing sessions in the Servlet container's memory may suffice. However, when running **multiple nodes** behind a load balancer, a session sitting only on node-A does not automatically appear on node-B.

**Spring Session** provides an API and mechanism replacing how `HttpSession` is stored with a `SessionRepository`, which can use Redis or JDBC. Multiple nodes sharing the same repository can read each other's session data. Still, this is not magic: Redis/DB availability, serializers, cookies, timeouts, session fixation, concurrent updates, and privilege revocation still must be designed and tested.

After this lesson, you will be able to:

1. Describe `HttpSession`, session IDs, cookies, and `SecurityContext` in Spring Security Servlet.
2. State the limitations of per-node in-memory sessions and load-balancer sticky sessions.
3. Explain `SessionRepositoryFilter`, `SessionRepository`, and how `SecurityContext` is restored from a shared session.
4. Configure an example with Spring Boot 3.x, Spring Security 6.x, Java 17+, and Redis; run two instances on two ports.
5. Verify that a single login on A still permits accessing the authenticated session from B, even after A stops.
6. Compare Redis, JDBC, local memory, affinity, and the stateless API model.
7. Handle failure scenarios involving TTL, cookies, Redis outages, serialization, rolling deploys, and session revocation.
8. Build a safe rollout checklist with cross-node testing, observability, and session data protection.

Scope: **Servlet stack**, not WebFlux. The example uses session-based form login, not JWT. Local Redis configurations and passwords in this lesson are strictly for development machines, never for production.

## 1. How does HttpSession preserve state across HTTP requests?

HTTP is a request/response protocol. A server does not automatically know two requests from a browser belong to the same user without an identification mechanism. In session-based applications, the server issues an **unpredictable session ID**. The browser stores the ID in a cookie and sends it back on subsequent requests. The server looks up the corresponding session and restores login info or application data.

~~~text
Browser                                   Spring Security Server
   | GET /private                                  |
   |---------------------------------------------->|
   | not yet authenticated => 302 /login           |
   |<----------------------------------------------|
   | GET /login, then POST /login + CSRF token     |
   |---------------------------------------------->|
   | AuthenticationManager verifies credentials    |
   | SecurityContext is saved via HttpSession      |
   | Set-Cookie: SESSION=<opaque-id> (example)     |
   |<----------------------------------------------|
   | GET /private + Cookie: SESSION=<opaque-id>    |
   |---------------------------------------------->|
   | server finds session and restores Auth        |
   | checks authorization -> response              |
   |<----------------------------------------------|
~~~

The cookie name is not immutable: default Servlet containers typically use `JSESSIONID`; Spring Session using `DefaultCookieSerializer` typically uses `SESSION`. **Inspect the actual `Set-Cookie` header** rather than hardcoding a name and guessing. The cookie normally carries only an opaque ID, **not** the entire `SecurityContext` or roles. From a security standpoint, this ID remains a bearer credential because anyone holding a valid ID can try to replay the session.

| Concept | Responsibility |
| --- | --- |
| Session cookie | Browser stores and sends the session ID per domain/path/Secure/HttpOnly/SameSite |
| HttpSession | Servlet API to read/write attributes, invalidate the session, and inspect lifetime |
| SecurityContext | `Authentication` data used by Spring Security during authorization |
| SecurityContextRepository | How Spring Security loads/saves `SecurityContext` across the request lifecycle |
| SessionRepository | Spring Session mechanism to save, read, create, and delete sessions independently of container memory |
| Redis/JDBC | Actual backing data store allowing multiple JVMs to share sessions |

**`SecurityContextRepository` is not synonymous with `SessionRepository`**. The former handles the security context; the latter handles `HttpSession`. When `SecurityContext` is stored inside `HttpSession`, they work together.

In Spring Security 6, if you write a custom authentication filter instead of standard `formLogin`, merely placing `Authentication` into `SecurityContextHolder` does not keep it alive across requests. You must save the context via `SecurityContextRepository` per the active version's contract. Spring Security's built-in form login handles the appropriate saving steps.

## 2. Why do local session stores fail when scaling out?

Suppose a load balancer distributes requests across two JVMs, each with an in-memory session manager:

~~~text
                        Load Balancer
                       /             \
                  node-A             node-B
                  :8081              :8082
              session map A       session map B

POST /login  -> A: creates session XYZ in map A
GET /account -> B: XYZ not present in map B
                 => treats request as unauthenticated
~~~

Both nodes may share the same user database and password encoder, yet that does not mean **the session map is shared**. Users can get redirected back to `/login` right after logging in successfully, depending on which node handles the next request.

Typical limitations:

- **No default data sharing:** a session created on A does not automatically exist on B.
- **Session loss on process death:** JVM restarts, container terminations, or rolling deploys wipe sessions stored in heap.
- **Failover cannot recover sessions:** when A dies and the LB shifts to B, B may not recognize the old session ID.
- **Memory pressure:** large attributes, overly long idle timeouts, or session leaks increase heap/GC/`OutOfMemoryError`.
- **Hard distributed logout management:** when each node keeps its own copy, deleting on A does not guarantee deletion on B.
- **Scale-out tied to routing:** login flow correctness becomes dependent on load balancer behavior.

Some Servlet containers support native session replication, but **never assume** Tomcat/Jetty has that enabled by default. Replication also incurs network, serialization, and consistency costs; inspect the actual container/topology.

### How do sticky sessions help?

Sticky sessions, also called session affinity, instruct the LB to prefer routing requests from the same client to one node:

~~~text
Browser session XYZ --> Load Balancer --> always to A while A is healthy
~~~

This approach can reduce login loops under normal conditions, yet **it does not copy A's data to B**. When A crashes, updates, or scales down, sessions can be lost. It can also skew load if many users stick to one node for a long time. Therefore sticky sessions are not equivalent to a shared session store and do not guarantee failover.

Spring Session does not force you to abandon affinity: you can still keep routing preference for performance. However, once a shared store is chosen, session **correctness** should no longer depend on every request always landing on the initial node.

## 3. Spring Session architecture on Servlet

Spring Session wraps/replaces `HttpSession` through a Servlet filter so upper-layer code continues using familiar APIs while data is stored out-of-process.

~~~text
                         Load Balancer
                          /           \
                       node-A         node-B
                         |              |
              Spring Session       Spring Session
              + Spring Security   + Spring Security
                         \              /
                            Redis/JDBC
                       shared SessionRepository
~~~

Flow on a single node:

~~~text
Servlet container
    |
springSessionRepositoryFilter
    |-- wraps HttpServletRequest/HttpServletResponse
    |-- HttpSession is backed by SessionRepository
    |
springSecurityFilterChain / FilterChainProxy
    |-- SecurityContextRepository loads SecurityContext
    |-- formLogin / CSRF / authorization handle request
    |
DispatcherServlet, controller, application service
    |
SessionRepository -> Redis/JDBC
~~~

The prominent filter name is **SessionRepositoryFilter**. In a proper Spring Boot integration, Spring Session is registered so Spring Security's filters use the corresponding session wrapper. Do not manually add a second `SessionRepositoryFilter` into `SecurityFilterChain` thinking it is “safer”: duplicate registration can cause lifecycle errors.

Functionally:

1. When a session is needed, Spring Session creates an object representing a session and persists it into `SessionRepository` per configuration.
2. During form login, `Authentication` is verified by Spring Security and `SecurityContext` is saved through the appropriate workflow.
3. On a later request to another node, the cookie carries the ID pointing to a session entry in Redis/JDBC; Spring Security reads back `SecurityContext` and checks permissions.
4. After logout/timeout/invalidation, the session is no longer accepted per repository rules.

Spring Session **does not replace `AuthenticationManager`, `AuthenticationProvider`, or `PasswordEncoder`**. It does not know whether usernames/passwords are right or wrong; it simply enables using `HttpSession` across multiple nodes.

Spring Session also does not automatically synchronize user databases, roles, password-change policies, custom session registries, token revocation, or other configuration across applications.

## 4. Runnable example: Spring Boot + Spring Security + Redis

We deploy a Spring Boot 3.3.x app using Java 17+, default `formLogin`, and Spring Session Data Redis. Run two independent JVMs:

- Node A runs on port 8081, `app.node-id=node-a`.
- Node B runs on port 8082, `app.node-id=node-b`.
- Both connect to the same Redis at `localhost:6379`, sharing namespace `demo:sessions`.
- A user logs in once on node A and then calls `GET /me` on node B without logging in again.

Requires JDK 17+, Gradle wrapper in the project, and Docker or a compatible local Redis. The code below covers the listed files completely; Spring Boot starters manage security and MVC dependencies.

### 4.1. Project structure

~~~text
session-cluster-demo/
  settings.gradle
  build.gradle
  compose.yaml
  gradlew / gradlew.bat    (Gradle wrapper if generated)
  src/main/java/dev/example/cluster/
    SessionClusterApplication.java
    SecurityConfig.java
    SessionController.java
  src/main/resources/
    application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'session-cluster-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

If using a different Boot version, let Boot's dependency management select aligned Spring Security/Spring Session versions. Do not manually mix Spring Session/Security artifacts across major versions. To run with `./gradlew`, the project needs the Gradle Wrapper; you can initialize the project using Spring Initializr or Gradle.

### 4.2. Local Redis for learning only

`compose.yaml`:

~~~yaml
services:
  redis:
    image: redis:7.4-alpine
    ports:
      - "127.0.0.1:6379:6379"
~~~

Run:

~~~bash
docker compose up -d
docker compose ps
~~~

This is local Redis without authentication, bound to the host loopback port. **Never deploy such an unauthenticated, non-TLS, non-HA setup to the Internet or production.** When running multiple containers in the same Docker network or Kubernetes, the Redis host should normally be the appropriate service name, not each container's `localhost`.

### 4.3. Main class

File `src/main/java/dev/example/cluster/SessionClusterApplication.java`:

~~~java
package dev.example.cluster;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionClusterApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionClusterApplication.class, args);
    }
}
~~~

### 4.4. Spring Security stateful form login

File `src/main/java/dev/example/cluster/SecurityConfig.java`:

~~~java
package dev.example.cluster;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("student")
                        .password(encoder.encode("local-lab-password"))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public").permitAll()
                        .anyRequest().authenticated())
                .formLogin(withDefaults())
                .logout(withDefaults())
                .build();
    }
}
~~~

This snippet enables `formLogin` with the framework-generated login page and default `POST /login`. `/public` has `permitAll` to verify which node responds; `/me` requires `Authentication`. Do not use `SessionCreationPolicy.STATELESS`, because this lesson needs to persist `SecurityContext` across `HttpSession`.

`InMemoryUserDetailsManager` here creates the same demo user on both nodes. This is **not** a shared identity store: changing roles/passwords on node-A will not automatically update node-B's user store. In production, use a consistent user/identity source via a database or proper identity provider. Spring Session only handles sessions, not synchronizing `InMemoryUserDetailsManager`.

The sample password is for local use only. Never hardcode production credentials in source code.

### 4.5. Controller verifying which node handles the request

File `src/main/java/dev/example/cluster/SessionController.java`:

~~~java
package dev.example.cluster;

import java.util.Map;

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

    @GetMapping("/public")
    public Map<String, String> publicPage() {
        return Map.of(
                "message", "PUBLIC",
                "node", environment.getProperty("app.node-id", "unknown"));
    }

    @GetMapping("/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of(
                "user", authentication.getName(),
                "node", environment.getProperty("app.node-id", "unknown"));
    }
}
~~~

Never return session IDs, raw `Cookie` headers, or full `Authentication` objects to the client. `node-id` is only for verifying routing in the demo and does not need to be exposed publicly in real systems.

### 4.6. Redis SessionRepository configuration

File `src/main/resources/application.yml`:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
  session:
    redis:
      namespace: demo:sessions

server:
  servlet:
    session:
      timeout: 30m
~~~

Both nodes must point to **the same Redis and the same namespace**. If A uses `demo:sessions` while B uses `demo:other`, they do not share a logical session store. Do not share namespaces across different applications unless they are designed to share data, serializers, and cookie policies.

Spring Boot with the matching Spring Session Data Redis dependency can auto-configure `SessionRepositoryFilter` and the repository. The example omits adding `@EnableRedisHttpSession` or another Spring Session filter manually to avoid conflicting configurations.

`server.servlet.session.timeout` sets the session timeout for the Servlet environment; when deploying, confirm the actual `maxInactiveInterval` and TTL of your active Spring Session version. **Cookie lifetime differs from session timeout.** When changing cookie protection settings, inspect `Set-Cookie` on real responses.

### 4.7. Running both applications

In two separate terminals:

Node A:

~~~bash
./gradlew bootRun --args="--server.port=8081 --app.node-id=node-a"
~~~

Node B:

~~~bash
./gradlew bootRun --args="--server.port=8082 --app.node-id=node-b"
~~~

On Windows PowerShell, use `.\gradlew.bat` and keep the matching arguments. Ensure both processes start cleanly and connect to local Redis.

Test:

~~~bash
curl -i http://localhost:8081/public
curl -i http://localhost:8082/public
~~~

The two separate HTTP response bodies typically yield equivalent data:

~~~json
{"message":"PUBLIC","node":"node-a"}
~~~

~~~json
{"message":"PUBLIC","node":"node-b"}
~~~

These are **sample bodies matching program logic**, without guaranteeing specific JSON key ordering or exact headers. If both responses show `node-a`, you have not genuinely tested two separate processes.

### 4.8. Testing session portability across two nodes

1. Using **the same browser profile**, visit `http://localhost:8081/me` while logged out. Normally the browser is redirected to `/login`.
2. On node A's login page, enter username `student` and password `local-lab-password`. Spring Security provides the default form and handles CSRF accordingly.
3. After logging in, visit `http://localhost:8081/me`. Expected body contains `"user":"student"`, `"node":"node-a"`.
4. In **that very same browser**, open `http://localhost:8082/me` without logging in a second time. Expected body still shows `"user":"student"` yet `"node":"node-b"`.
5. Stop the node A process. Call `http://localhost:8082/me` again. As long as Redis remains available and the session has not expired/been invalidated, node B still authenticates the same session.
6. Test logging out via a valid `POST /logout` with a CSRF token or the corresponding logout UI/endpoint; once the session is invalidated, new requests to A/B must no longer appear logged in.

In this local test, **port is not a cookie boundary**; cookies are scoped by domain/path/attributes, so one browser can send matching cookies to both `localhost:8081` and `localhost:8082`. Two separate browser profiles or incognito windows isolate cookies and will not demonstrate sharing the same session.

Never print or paste session IDs into chats, logs, or screenshots. A valid session ID can be used to hijack the session.

### 4.9. What truly proves a shared session?

All four conditions must hold:

- The user authenticates **only once** on A.
- The request to B uses **the same post-login session cookie**, without re-entering a password.
- The response from B shows the right user and `node-b`, proving the request hit the other process.
- After shutting down A, B can still use the session from Redis.

Both nodes sharing identical usernames/passwords **does not prove** session sharing if the browser logged in separately on each node. Nor can you rely on `/public` returning 200 to conclude the Redis session repository is healthy; `/public` may not touch any session.

### 4.10. Safely inspecting Redis

In a local environment, the Redis CLI can verify that the namespace and keys exist:

~~~bash
redis-cli --scan --pattern "demo:sessions:*"
~~~

Use this only in environments you are authorized to access. Never dump session/`SecurityContext` values into documents, as they can hold sensitive security data. Key structure and TTL may vary by repository, version, and indexed-session features; do not treat a hardcoded key pattern as a stable API contract.

## 5. Redis, JDBC, local memory, and sticky sessions: comparing choices

| Option | Shares sessions across nodes? | Primary risk | When to consider |
| --- | --- | --- | --- |
| Container in-memory `HttpSession` | Not by default | Lost on restart; only current node knows session | Dev, single-node apps, simple setups |
| Sticky session + local | Not truly shared | Failover/node switch loses session, load skew | Temporary workaround or accepted limitation |
| Spring Session + Redis | Yes when sharing repository/namespace | Redis/network outage, TTL, memory, serializer | Stateful clusters needing speed and shared storage |
| Spring Session + JDBC | Yes when sharing DB/schema | DB load, cleanup, lock contention, latency | Existing RDBMS, moderate session load, centralized ops |
| Container session replication | Depends on container config | Replication cost, serialization, topology | Certain clusters/legacy applications |
| Stateless bearer token | Does not depend on `HttpSession` for authentication | Token revocation, key management, bearer token protection | Stateless-by-design REST APIs/Resource Servers |

**Redis is a critical data store**, not simply an expendable cache: losing Redis sessions can log out all users en masse. HA/replication/persistence can reduce risk, yet failover must be tested; zero session loss cannot be assumed blindly.

With Spring Session JDBC, you need the JDBC dependency plus matching datasource/schema/session tables/cleanup for your version. Session reads/writes generate DB load; indexing, capacity planning, and tuning are necessary. Whether using Redis or JDBC, the application acquires a network dependency; no backend automatically solves every distributed systems issue.

## 6. Timeout, cookies, SessionRepository, and SecurityContext

Distinguish at least three timelines:

1. **Max inactive interval:** inactivity duration after which the session is considered expired by repository policy.
2. **Physical TTL/cleanup of the session store:** Redis uses key expiration; JDBC uses cleanup jobs. A key may not physically vanish the instant a session becomes expired.
3. **Browser cookie lifetime:** cookies can be browser-session cookies or configured with `Max-Age`/`Expires`. A cookie still existing does not mean the server-side session still exists.

If the browser keeps sending a cookie yet Redis no longer holds the session, the user is typically treated as unauthenticated. Conversely, if the session still exists in Redis yet the cookie was lost or Path/Domain mismatched, requests also fail to restore `Authentication`.

Lifetime policies must balance UX and security. Do not raise TTL indefinitely to avoid re-logins; that increases the window during which a stolen session ID remains useful.

### Cookie flags and reverse proxies

For production, verify:

- **Secure:** session cookies must travel only over HTTPS when the public site uses TLS.
- **HttpOnly:** browser JavaScript should not read session cookies.
- **SameSite:** pick a setting matching topology/frontend and pair with CSRF defenses.
- **Path/Domain:** do not widen cookie sharing to unnecessary apps or subdomains.
- **Session fixation:** after login, Spring Security by default rotates session IDs appropriately for Servlet; never disable it just because you see the ID change.
- **Forwarded headers:** behind a TLS-terminating proxy, trust only trusted proxies and verify scheme/cookies/redirects resolve accurately.

Session IDs are credentials; access logs must not log entire `Cookie` headers, `Set-Cookie`, or session IDs. Use an independent log correlation ID that cannot be replayed as a credential.

## 7. Problems Spring Session does not solve automatically

### 7.1. Redis outages and failure policies

If Redis shuts down, both node A and node B may fail to load or save sessions. **Never assume the framework safely falls back to local sessions**. A silent fallback causes inconsistent authentication behavior across nodes, and failing open creates vulnerabilities.

Minimum design: connection timeouts, bounded retries, health/readiness probes, failover, latency/error monitoring, safe error responses, and guiding users to log in again if session data is lost. When a valid session cannot be proven, never grant access to protected requests.

Do not rely solely on a `/public` health endpoint because it may return 200 even when Redis is down. Check the backend or run synthetic authenticated-session workflows, especially prior to rollout.

### 7.2. Serialization and rolling deploys

Sessions can hold `SecurityContext`, `Authentication`, `UserDetails`, and custom attributes. Those values must be readable/writable by Spring Session's serializer on both nodes.

Common mistakes:

- Placing JPA entities, service objects, or request objects into `HttpSession`; they are too large or non-serializable.
- A new node changes a class/package or `serialVersionUID`, making old nodes unable to deserialize it.
- Configuring a Jackson serializer missing required type information or allowing overly broad deserialization.
- Two nodes using different serializers/namespaces while sharing the same session cookie.
- Failing to test two code versions running simultaneously during a rolling deploy.

Recommendations: keep session attributes **small, simple, and versioned**; avoid storing entire object graphs; never enable unsafe deserialization as a quick fix. Test mixed-version compatibility in both A→B and B→A directions. When forced to make an incompatible format change, plan migration/invalidation and clear UX messaging.

### 7.3. Concurrent session updates

A shared session is not automatically a **transactional distributed object**. Two requests can concurrently load the same session and modify an attribute, causing the last write to overwrite the earlier one:

~~~text
Request 1 reads cart.count = 0
Request 2 reads cart.count = 0
Request 1 writes cart.count = 1
Request 2 writes cart.count = 1
Expected two increments = 2, final value can be = 1
~~~

Depending on repository and save mode, lost updates/overwrites can happen. Never use the session as the single source of truth for orders, balances, inventory, or transactional data. Move such data into a business database with proper concurrency control, keeping only references in the session.

### 7.4. Logout, permission changes, and revocation

Logging out on A can invalidate the session in Redis. Subsequent requests on B with the same session ID will not be treated as authenticated. However, **in-flight requests** that started before invalidation may have already loaded `SecurityContext` and will not necessarily halt mid-execution.

If a user's roles or status are revoked, `SecurityContext` saved in the session may still contain old authorities. Spring Session does not re-query `UserDetailsService` on every request automatically. For strict revocation requirements, design permission-version checks, central session revocation, or re-authentication policies as needed.

When limiting concurrent login sessions, verify principal/index lookup capabilities and your application's `SessionRegistry`. `SpringSessionBackedSessionRegistry` can support certain setups, but **merely adding the Spring Session dependency does not guarantee concurrent session control auto-configures properly**; you need an index-capable repository, wiring, tests, and lifecycle-event awareness.

### 7.5. Flush/save mode and write overhead

Spring Session has options controlling when session data is written back to the repository (save/flush mode) depending on backend/version. You cannot assume “every HTTP GET writes the whole session” or “every attribute syncs instantaneously” without inspecting configuration. Switching to immediate flush can increase round trips and hurt performance.

Monitor session size, session create/update request rates, Redis/JDBC latency, TTL/expirations, connection pools, and memory/evictions. Optimize only based on evidence from real traffic.

### 7.6. Synchronizing user data

Spring Session shares `HttpSession`, not `InMemoryUserDetailsManager` or user databases. If each node configures different users/passwords/roles, **a fresh authentication** can succeed on A yet fail on B even though sessions are shared. Production needs a shared identity source and consistent authentication providers/password policies.

## 8. Stateful sessions or stateless APIs?

For server-rendered apps using `formLogin` and cookies, a shared session repository enables scaling out and centralized server-side logout/revocation.

For resource server APIs receiving Bearer tokens, users may not need server-side HTTP sessions per request: a stateless design fits that need. Still, tokens must have signature/issuer/audience/expiry checks, secure client storage, and revocation strategies when required.

Spring Security's **`SessionCreationPolicy.STATELESS`** tells the chain not to use `HttpSession` to retain `SecurityContext` in the traditional stateful manner. Adding `spring-session-data-redis` does not turn stateless authentication into cookie-persisted login. If an app has both a web session chain and a stateless API chain, clearly separate `securityMatcher` and per-chain settings.

Never switch to JWTs just to “fix” a local session bug without evaluating revocation requirements, token risks, lifetimes, and UX.

## 9. Cross-node testing, failover, and operations

| Test | Action | Expectation |
| --- | --- | --- |
| Anonymous | `GET /me` on A/B before login | Redirect/challenge, no authenticated user |
| Single login | Valid POST login on A | Browser receives new session cookie |
| Cross-node | `GET /me` on B with same cookie | `user=student` and `node=node-b` |
| App failover | Stop A, continue `GET /me` on B | B still reads session while Redis is up |
| Logout | Invalidate session, new request on B | No longer authenticated |
| Idle timeout | Wait full timeout/test short timeout | Session no longer valid |
| Redis outage | Disconnect Redis in test | No fail-open, clear/controlled error |
| Rolling deploy | A/B running different code versions | Session readable or intentional migration/invalidation |
| Cookie scope | HTTPS/proxy/context path | Cookie sent to right host/path with safe flags |
| Concurrent changes | Two requests writing session data together | Never rely on session for transactional business state |

A proper cross-node test must **force requests onto two distinct nodes**, rather than relying on a load balancer picking one by chance. Check HTTP status and actual response content, not just cookie counts.

Useful observability metrics: session lookup/write failures, Redis latency/errors, valid session count, key expirations/evictions, attribute sizes, sudden spikes in login redirects, deserialization errors, authentication latency, logout activity, and node failover rates.

### Seeing 200 on /public alone is not enough

`GET /public` may not read `HttpSession` at all. Even if Redis is down, that endpoint can still return 200 in some situations. Thus checking node liveness via public health checks does not prove shared sessions are healthy. Real synthetic auth tests and backend health monitoring carry far more value.

## 10. Common errors and proper fixes

**Error A: Log in on A then bounced back to login on B.** Check whether the session store is local or Redis, whether the cookie is sent to B, whether namespaces match, and whether `SecurityContext` was saved. For custom auth filters, check whether `saveContext` is called per contract.

**Error B: Added Redis client yet sessions remain local.** `spring-boot-starter-data-redis` supplies a client; it does not turn `HttpSession` into a Redis session. You need the Spring Session module, proper auto-configuration, and `SessionRepositoryFilter`.

**Error C: Redis namespaces differ across nodes.** Even on the same host, keys do not share a logical namespace, so sessions cannot be read. Align configuration and test in practice.

**Error D: Browser does not send cookie across hosts or behind a proxy.** Check `Path`, `Domain`, `SameSite`, `Secure`, HTTPS scheme, context path, and reverse-proxy trusted forwarded headers. Never widen the cookie domain hastily as a quick fix.

**Error E: Redis restart logs every user out.** Without appropriate persistence/HA, losing session data is expected. Design recovery and UX rather than expecting the app to resurrect vanished sessions.

**Error F: Class/serializer changed after deploy, session unreadable.** Use stable DTOs, test rolling upgrades, and handle incompatibility intentionally. Never enable unrestricted deserialization for arbitrary types.

**Error G: Session data overwritten during concurrent requests.** Sessions are not transactional databases. Store business state in a DB with concurrency control and keep sessions small.

**Error H: Logged out on A yet B still allows an in-flight request.** Distinguish in-flight requests from new requests after invalidation, verify the specific session ID/cookie, and add extra checks if immediate revocation is required for sensitive operations.

**Error I: Session expires at the “wrong” time.** Distinguish idle timeout, logical TTL/physical cleanup, cookie lifetime, and `lastAccessedTime`; check the backend, real clocks, and caches/proxies.

**Error J: Changed user roles in DB yet session keeps old roles.** The saved `SecurityContext` can hold stale authorities. Implement revalidation and session revocation policies when roles change.

**Error K: Set `SessionCreationPolicy.STATELESS` then expected form login to keep a session.** A stateless chain intentionally avoids using `HttpSession` to hold context for subsequent requests. Pick the right architecture for each chain.

**Error L: Exposed Redis without authentication to the Internet.** Redis session stores contain sensitive data; enforce private networking, ACLs/auth, TLS/secret management, least privilege, backups, and monitoring.

## 11. Production readiness checklist

1. **Inventory session attributes and sizes**, removing oversized or non-serializable objects.
2. **Choose Redis/JDBC** based on session volume, latency, capacity, SLA, cost, and operability.
3. **Verify `SessionRepositoryFilter` is active**, without uncontrolled fallback to local sessions.
4. **Standardize config across nodes:** endpoints, namespaces, serializers, timeouts, cookie name/domain/path, and security chains.
5. **Shared user/identity store** for new authentications across all nodes; never use in-memory users in production.
6. **`Secure`, `HttpOnly`, `SameSite` cookies, TLS**, session fixation protection, and CSRF protection suited to form login.
7. **Harden Redis/DB** with ACLs, private networks, secret management, HA/persistence, backups, and monitoring.
8. **Test single login on A → B with the same cookie**, shut down A, and verify B still holds the session.
9. **Test Redis outages**, timeouts, session expiration, logout, and revoked permissions.
10. **Test rolling deployments** and serializer compatibility while two versions run concurrently.
11. **Test concurrent writes**, moving high-consistency data to a transactional DB.
12. **Observe and alert**, distinguishing public health from authenticated-session health.
13. **Plan user re-login handling** if namespaces/serializers must change or the session store is lost.
14. **Evaluate stateless APIs separately** when sessions are unnecessary, rather than switching blindly just to avoid cluster setup.

## 12. Self-study questions with explanations

**Question 1.** Two instances run the exact same `SecurityConfig`; why is a session created on A not automatically visible on B?

**Answer:** The local `HttpSession` manager lives in each process's memory. Identical code does not mean a shared session map; a configured shared repository or replication is required.

**Question 2.** Do sticky sessions guarantee failover?

**Answer:** No. They direct requests to the same node while it is available; they do not copy sessions to other nodes.

**Question 3.** What does Spring Session replace and what does it not replace?

**Answer:** It replaces how `HttpSession` is stored/retrieved via `SessionRepository`; it does not replace `AuthenticationManager`, `PasswordEncoder`, or `SecurityContext` authorization logic.

**Question 4.** What happens if a request arrives at B with a session cookie yet Redis no longer holds the session?

**Answer:** The cookie carries an ID, not the full authentication. Session gone → `SecurityContext` cannot be restored from it, and protected requests must be handled as unauthenticated or via appropriate errors.

**Question 5.** Do two nodes sharing Redis with different namespaces share sessions?

**Answer:** Not under normal configuration. Logical keyspaces differ; both nodes must align on repository, namespace, and serializer.

**Question 6.** Does adding Redis automatically keep logins alive when the chain sets `STATELESS`?

**Answer:** No. `STATELESS` is Spring Security's choice not to rely on `HttpSession` for a request's `SecurityContext`.

**Question 7.** Does `GET /public` returning 200 while Redis is down mean sessions are working?

**Answer:** No. Public endpoints may not read sessions; synthetic authenticated requests and backend checks are needed.

**Question 8.** A session object written by a newer node cannot be read by an older node—what kind of bug is this?

**Answer:** Serialization/schema/version compatibility; requires rolling-deploy testing, stable formats, or intentional migration/invalidation.

**Question 9.** Why should unique balances or orders never be stored in `HttpSession`?

**Answer:** The session repository does not guarantee business transactions when two requests update concurrently, risking lost updates. Use a business database.

**Question 10.** Does logging out on A immediately stop every in-flight request on B?

**Answer:** There is no such guarantee. Requests that already loaded context may still be executing; test new requests after invalidation and design additional revocation checks when needed.

## Summary

On a single node, **local `HttpSession`** is simple yet tied to one JVM heap. With multiple nodes behind a load balancer, node routing shifts, restarts, or crashes can lose user sessions; **sticky sessions do not replicate data**.

**Spring Session** moves `HttpSession` to a **shared `SessionRepository`** (typically Redis/JDBC), enabling Spring Security Servlet instances to read the same session after login. Proper deployment requires coordinating cookies, session IDs, `SecurityContext`, namespaces, TTLs, serializers, Redis availability, logout, and access control.

The most decisive proof is not “both nodes are running”, but **logging in once on A, carrying the same cookie to B, stopping A while B still reads the session from the shared store**, and then testing outages, logout, timeouts, and rolling deployments.