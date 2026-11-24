# Spring Session, Multiple Application Nodes, and Limitations of Local Session Stores

## Lesson Objectives

A Spring Boot application running a single JVM can store HTTP sessions in the Servlet container's memory. When the system scales to **multiple instances/pods/nodes** behind a load balancer, that storage approach hits a limit: each node knows only the sessions it manages itself. A user can log in on node A, then have the next request routed to node B and be treated as unauthenticated. If A restarts or goes down, local session data can be lost.

**Spring Session** provides an abstraction layer and **SessionRepository** implementations to move session data into a shared store, such as Redis or JDBC. When properly configured, multiple nodes look up the session using the browser-sent ID, while most code continues working with the Servlet API's **HttpSession**.

After this lesson, you will be able to:

1. Explain why local HttpSession struggles with load balancing, failover, and rolling deployments.
2. Describe the flow **cookie → SessionRepositoryFilter → Redis/JDBC SessionRepository → Spring Security SecurityContext**.
3. Distinguish **sharing HttpSession** from **sharing all JVM state**, and identify what Spring Session does not solve on its own.
4. Run two Spring Boot Servlet instances sharing **the same Redis**, log in on instance A, and continue using the session on B.
5. Distinguish **RedisSessionRepository** from **RedisIndexedSessionRepository**, and understand SessionRegistry limitations in multi-node environments.
6. Assess risks around Redis unavailability, session expiration, object serialization, application version changes, and large-scale session storage.

**Scope:** Spring Boot 3.5.x, Spring Security Servlet 6.x, Spring Session 3.5.x, Java 17+, examples using Redis. Newer versions may rename starters or properties; when applying to a real project, cross-check documentation for your exact version. Reactive WebFlux uses **WebSession** and its own reactive repositories, so Servlet configurations should not be copied verbatim.

## 1. The Problem: Each JVM Has Its Own Session Store

Imagine a load balancer distributing requests across two instances of the same application:

~~~text
                     Browser
            Cookie: JSESSIONID=abc
                        |
                 Load balancer
                  /           \
                 v             v
          App Node A       App Node B
          JVM / Pod A      JVM / Pod B
          Local session    Local session
          {abc -> Alice}   {no abc}
                 |             |
          GET /me -> Alice    GET /me -> unauthenticated
~~~

In a Servlet container configuration using a local session store, the cookie holds only the **session identifier**; the corresponding data resides in that instance's memory or local storage mechanism. A request arriving at B with a cookie issued by A **has no default way** for B to read session data inside A's JVM.

Common consequences:

- After logging in successfully, users are occasionally redirected back to the login page when requests hit another node.
- Shopping carts, form state, multi-step flows, or SecurityContext appear to "vanish."
- When the node holding the session stops or is replaced, active sessions there become inaccessible.
- Scaling out increases the probability of requests switching nodes; bugs can be hard to reproduce if dev environments run only one node.

**Do not confuse this with failing to save SecurityContext on login:** even on the *same* node, if custom authentication code only calls SecurityContextHolder.setContext without saving via SecurityContextRepository, the next request can still lose login state. Spring Session solves **where sessions are stored**, while the authentication mechanism must still save the context properly first.

### Are Sticky Sessions Enough?

**Session affinity/sticky routing** forces the load balancer to prefer sending a client back to the node that created its session.

Pros: easy to enable and reduces cross-node requests; can help legacy applications.

Limitations:

- If node A fails or is replaced during a rolling deployment, sessions tied to A can still be lost.
- Load distribution skews when users have varying session lifetimes.
- Users must stay on the same load balancer/route; multiple proxy layers or affinity changes can cause requests to switch nodes.
- Local sessions still complicate cluster-wide concurrent login management.

Sticky routing can be a temporary workaround, yet **does not turn local session stores into a shared session store**. When failover with preserved state is required, a proper shared storage/replication mechanism is needed.

## 2. What Does Spring Session Change?

Spring Session provides **SessionRepository** and Servlet integration to replace how HttpSession is stored. In a Redis-backed application, requests pass through a filter typically registered as **springSessionRepositoryFilter**.

~~~text
                       Browser
                    Cookie: SESSION=xyz
                            |
                       Load balancer
                         /       \
                        v         v
                  App Node A   App Node B
                       \         /
                        \       /
                  SessionRepositoryFilter
                     (on each node)
                           |
                 Redis SessionRepository
                           |
                         Redis
                   {xyz -> session data}
                       /       \
                      v         v
               both A and B can read
             session xyz by the same ID
~~~

What happens during a request:

1. The browser sends the session identifier cookie.
2. **SessionRepositoryFilter** wraps the request/response so **HttpSession** operations use the Spring Session repository.
3. The repository reads the session by ID from Redis/JDBC instead of a single-JVM default session store.
4. If the session is still valid, Spring Security can read the **SecurityContext** saved inside that session.
5. The controller runs and can read/write session attributes using the Servlet API.
6. Session changes are written back to the shared store by the repository at the point matching the save/flush mode.
7. A subsequent request hitting another node uses the same ID and namespace to load session data.

**Spring Session does not authenticate users itself.** It provides session storage/restoration. **Spring Security** remains responsible for authentication, authorization, saving SecurityContext, session fixation protection, CSRF, and logout per configuration.

### Default Cookie: SESSION or JSESSIONID?

With a standard Servlet container HttpSession, the common cookie is **JSESSIONID**. With Spring Session Servlet and **DefaultCookieSerializer**, the default cookie name is **SESSION**. This can be changed via CookieSerializer if compatibility requires.

Therefore, when debugging, inspect **the actual cookie issued** rather than assuming it is always named JSESSIONID. The cookie holds the ID used to look up the session, **not the entire SecurityContext or session contents**.

### What Must Be Consistent Across All Nodes?

- The same application or compatible versions of session data.
- The same Redis/JDBC session store, namespace, and encoding/serialization.
- The same cookie domain/path, HTTPS, proxy, and session timeout policies.
- The same authentication model and SecurityContextRepository able to read the stored data.
- Reasonably synchronized clocks, especially if the application enforces absolute lifetimes beyond inactivity timeouts.

If node A writes sessions to a different Redis database/namespace than node B, even though both "use Spring Session," B still cannot load A's session.

## 3. Comparing Three Approaches to Organizing Session Storage

| Model | Where Does the Session Live? | When Request Switches Nodes? | When a Node Dies? | Key Trade-Offs |
| --- | --- | --- | --- | --- |
| **Local HttpSession** | Each node's JVM / Servlet container | Can lose login if routed to a node lacking the session | Local sessions can be lost | Simple, no external store, yet scaling/failover is hard |
| **Sticky + local session** | Still on each node, LB tries to keep client there | Normally switches less often, yet no failover guarantee | Usually still lost or needs separate replication | Depends on affinity, uneven load distribution |
| **Spring Session + Redis/JDBC** | Shared session store outside instances | Can restore on another node using the same ID | Usually survives if the shared store stays up | Adds latency, cost, dependency, and operational overhead |

**An application node being replaced** is different from **the session store being lost**. Spring Session can preserve sessions when application JVMs churn, but if the primary Redis loses data or suffers severe downtime, the system is still impacted. Spring Session does not automatically provide high availability for Redis.

### Redis vs. JDBC

**Redis** typically suits high-frequency session read/write workloads, TTLs, and fast access. You must manage memory, eviction, replication/failover, authentication/TLS, serializers, and connection counts.

**JDBC** can fit when an organization already operates a stable database and wants to manage sessions via tables. It requires schema migrations, connection pooling, indexing, expired-session cleanup, contention management, and read/write performance tuning.

Spring Session may support other stores depending on version. Choosing a store depends on SLAs, throughput, cost, consistency requirements, data structure, and existing infrastructure. Do not pick Redis solely because there are multiple nodes while ignoring Redis operational capability.

## 4. How Is Spring Security Involved?

A session-backed form login flow typically looks like:

~~~text
POST /login (credentials + CSRF token)
      |
      v
AuthenticationManager authenticates
      |
      v
SessionAuthenticationStrategy
  e.g., session fixation protection
      |
      v
SecurityContext containing Authentication
      |
      v
SecurityContextRepository saves to HttpSession
      |
      v
Spring Session writes session to Redis
      |
      v
Browser receives SESSION cookie
      |
      v
GET /me reaches node B
      |
      v
Spring Session reads Redis by SESSION ID
      |
      v
Spring Security restores Authentication
      |
      v
Authorization -> Controller -> 200
~~~

With Spring Security-managed **formLogin**, the framework handles authentication and persistence steps per configuration. When writing a custom JSON login controller or authentication filter, you must ensure **SessionAuthenticationStrategy** (if using sessions) and **SecurityContextRepository.saveContext(...)** are called at the right time. Simply adding the Spring Session dependency will not turn a custom login controller into a complete context-persistence mechanism.

### SessionCreationPolicy Must Match

| SessionCreationPolicy | Impact on Maintaining Login via Redis |
| --- | --- |
| **ALWAYS** | Spring Security can create sessions eagerly; usually unnecessary just to use Redis |
| **IF_REQUIRED** | Fits session login: creates only when needed, uses a repository capable of saving context |
| **NEVER** | Does not proactively create, yet can use an existing session; not a common choice for new logins from sessionless clients |
| **STATELESS** | Spring Security does not use HttpSession to restore SecurityContext; **unsuitable** when wanting to use SESSION cookies to maintain login |

An application can use Redis for other purposes while simultaneously running a stateless Bearer token API. However, **do not choose STATELESS and expect a SecurityContext from a Redis session to appear on new requests**.

### What Is Not "Shared" Just Because You Use Spring Session

- The current thread's **SecurityContextHolder**; it has a per-request lifecycle.
- **Singleton** bean fields, static maps, and local **Caffeine/ConcurrentHashMap** caches.
- Data sitting on the call stack, request attributes, and in-flight transactions.
- **SessionRegistryImpl** stored in a single node's RAM if used directly.
- Rate limiters, locks, idempotency keys, or cart data stored outside HttpSession.
- Temporary file uploads, WebSocket connections, and tasks running in local threads/executors.

Spring Session shares **only data actually stored via SessionRepository**. If one node still writes session data into a static map, the other node cannot see it.

## 5. Practical Runnable Example: Two Spring Boot Nodes Sharing Redis

The example uses **Java 17+**, **Spring Boot 3.5.x**, Servlet stack, **Spring Security form login**, and **Spring Session Data Redis**. Spring Boot 3.5 provides auto-configuration for Spring Session when the right modules are present; with this setup, **adding @EnableRedisHttpSession is unnecessary**.

We will run **the exact same application code** in two processes on two different ports. Each process points to the same Redis at localhost:6379 and the same namespace. The user logs into A, then accesses node B using the cookie retained in the same client.

### 5.1. Initialize the Gradle Project

Create a Spring Boot project with the structure:

~~~text
session-shared-demo/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/example/session/SharedSessionApplication.java
~~~

**settings.gradle**:

~~~groovy
rootProject.name = 'session-shared-demo'
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.session:spring-session-data-redis'
}
~~~

The four dependencies have distinct roles:

- **spring-boot-starter-web**: runs Spring MVC on the Servlet container.
- **spring-boot-starter-security**: filter chain, form login, SecurityContext.
- **spring-boot-starter-data-redis**: Redis client and connection factory.
- **spring-session-data-redis**: Redis SessionRepository and Servlet HttpSession integration.

Use Spring Boot's dependency version management instead of pinning an incompatible Spring Session version yourself.

### 5.2. Configure Redis and Session Timeout

**src/main/resources/application.properties**:

~~~properties
spring.data.redis.host=127.0.0.1
spring.data.redis.port=6379

spring.session.timeout=20m
spring.session.redis.namespace=spring:session:multi-node-demo
spring.session.redis.repository-type=default

server.port=8081
demo.node=A
~~~

**spring.session.timeout=20m** sets the session inactivity timeout to 20 minutes in the example. The timeout tracks session access, rather than promising the session lives exactly 20 minutes on the clock from initial login. If spring.session.timeout is omitted, Spring Boot Servlet can fall back to server.servlet.session.timeout.

**spring.session.redis.namespace** must match across A/B so they look up shared session data together. If multiple unrelated applications share Redis, assign separate namespaces and ensure one app cannot accidentally read or modify another's sessions.

**spring.session.redis.repository-type=default** selects RedisSessionRepository in this configuration; section 7 explains when to switch to indexed.

In production, never commit Redis passwords into the repository. Pull connection settings from secret management/environment variables, restrict networking, enable auth/TLS per infrastructure, and constrain Redis permissions.

### 5.3. Complete Java Application

Create the file **src/main/java/example/session/SharedSessionApplication.java**:

~~~java
package example.session;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SharedSessionApplication {

    public static void main(String[] args) {
        SpringApplication.run(SharedSessionApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/node", "/csrf").permitAll()
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            .requestCache(cache -> cache.disable());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder passwordEncoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("demo")
                .password(passwordEncoder.encode("demo-pass"))
                .roles("READER")
                .build()
        );
    }

    @RestController
    static class Api {
        private final String node;

        Api(Environment environment) {
            this.node = environment.getProperty("demo.node", "unknown");
        }

        record NodeInfo(String node) {}
        record CsrfInfo(String headerName, String token) {}
        record WhoAmI(String node, String username,
                      boolean sessionPresent) {}

        @GetMapping("/node")
        NodeInfo node() {
            return new NodeInfo(node);
        }

        @GetMapping("/csrf")
        CsrfInfo csrf(CsrfToken csrfToken) {
            return new CsrfInfo(
                csrfToken.getHeaderName(),
                csrfToken.getToken()
            );
        }

        @GetMapping("/")
        String home(Authentication authentication) {
            return "signed in: " + authentication.getName();
        }

        @GetMapping("/me")
        WhoAmI me(Authentication authentication,
                  HttpServletRequest request) {
            HttpSession session = request.getSession(false);
            return new WhoAmI(
                node,
                authentication.getName(),
                session != null
            );
        }
    }
}
~~~

**Why these code choices?**

- Spring Security's **formLogin** provides the GET /login page and POST /login processing filter. Login results are stored in the session via standard mechanisms, fitting the shared-session demo.
- **IF_REQUIRED** does not force session creation on every request. When login or CSRF needs a session, Spring can create one.
- **/csrf** lets the client fetch a token for POST login. The example keeps CSRF enabled; login bodies/URLs must send the token along with the session cookie.
- **/node** exposes the node identifier to distinguish whether a request hit A or B.
- **/me** is protected and reads the principal from the request's Authentication. If B returns the username logged in on A, we have proof that application B restored the proper authentication.
- **request.getSession(false)** only observes the session without creating a new one inside /me.
- **requestCache.disable()** skips saving rejected URLs for post-login redirects, keeping the demo flow predictable; this is an API choice, not a requirement for Spring Session to work.
- User **demo/demo-pass** is for learning environments only. In production use a real identity store, password encoder, MFA, and proper secrets management.

**There is no manual SessionRepository bean** in the example because Spring Boot auto-configures it from the dependencies and properties. Adding @EnableRedisHttpSession switches to annotation-driven configuration and can back off Boot auto-configuration; do not mix both approaches casually.

### 5.4. Start Redis and Two Nodes

Use an existing local Redis or run a dedicated Redis container for the demo:

~~~bash
docker run --rm --name session-demo-redis \
  -p 127.0.0.1:6379:6379 redis:7-alpine
~~~

Bind the port only on loopback during practice; never expose an unprotected Redis to the Internet.

In two separate terminals, from the project directory containing the Gradle wrapper:

**Terminal A:**

~~~bash
./gradlew bootRun --args='--server.port=8081 --demo.node=A'
~~~

**Terminal B:**

~~~bash
./gradlew bootRun --args='--server.port=8082 --demo.node=B'
~~~

On Windows PowerShell, replace **./gradlew** with **.\gradlew.bat** and quote --args if needed. Both processes point to the same Redis and namespace.

Check the two unauthenticated endpoints:

~~~bash
curl -sS http://localhost:8081/node
# {"node":"A"}

curl -sS http://localhost:8082/node
# {"node":"B"}
~~~

The two JSON snippets above are expected outputs for the demo configuration, not logs captured from a live run.

### 5.5. Log In on A, Continue the Session on B

The examples below use **Bash/WSL/Git Bash, curl, and Python 3** to extract the token field from JSON. Reuse the same cookie file across all requests; avoid printing or sharing the cookie file's contents.

**Step 1. Fetch the CSRF token on A and save the session cookie.**

~~~bash
csrf=$(curl -fsS -c session-cookies.txt \
  http://localhost:8081/csrf \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

test -n "$csrf"
~~~

Fetching the token may create an HttpSession before login. The default cookie with Spring Session is usually named **SESSION**, not JSESSIONID.

**Step 2. POST /login to A with demo credentials and CSRF.**

~~~bash
curl -i -b session-cookies.txt -c session-cookies.txt \
  -H "X-CSRF-TOKEN: $csrf" \
  --data-urlencode "username=demo" \
  --data-urlencode "password=demo-pass" \
  http://localhost:8081/login
~~~

Successful form login typically returns **HTTP 302** to the default page or saved-request target; since requestCache is disabled, it usually redirects to **/**. Spring Security may rotate the session ID for session fixation protection. Depending on the container, Set-Cookie may appear in the response and the cookie file must be updated.

**Step 3. Use the saved cookie to call node B.**

~~~bash
curl -sS -b session-cookies.txt http://localhost:8082/me
# {"node":"B","username":"demo","sessionPresent":true}
~~~

If session data was saved properly and both nodes share Redis, B can return JSON with **node B**, logged-in username **demo**, and sessionPresent **true**. This is the fundamental sign that **SecurityContext was restored from the shared session**.

**Step 4. Return to A with the exact same cookie.**

~~~bash
curl -sS -b session-cookies.txt http://localhost:8081/me
# {"node":"A","username":"demo","sessionPresent":true}
~~~

The requests in steps 3 and 4 hit two different JVMs yet carry the same login session. JSON key order may vary by serializer; compare field values rather than key order.

**Step 5. Without sending the cookie, login is not inherited.**

~~~bash
curl -i http://localhost:8082/me
# HTTP/1.1 302 ... Location: /login (common with form login)
~~~

Because the example enables form login, unauthenticated requests are usually **redirected to /login**. Do not assume 401 by default; the status depends on the application's authentication entry point.

### 5.6. Verify Logout from One Node Takes Effect on the Other

Fetch a fresh CSRF token on B with the current cookie, then log out via POST:

~~~bash
csrf=$(curl -fsS -b session-cookies.txt -c session-cookies.txt \
  http://localhost:8082/csrf \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

curl -i -b session-cookies.txt -c session-cookies.txt \
  -H "X-CSRF-TOKEN: $csrf" \
  -X POST http://localhost:8082/logout
# Usually returns 302 to /login?logout
~~~

Once the session is destroyed, the same old cookie no longer proves Authentication. If you request **/me** on A after logout, the app treats it as an unauthenticated client (usually redirecting to /login).

Reason for fetching a new token: Spring Security may clear the old CSRF token upon successful authentication. Do not reuse a pre-login token for all subsequent POSTs.

### 5.7. Local Session Case: How to Compare

Use **a separate copy of the demo project**, remove the two Redis and Spring Session dependencies, and remove the spring.session.* properties. Keep Spring Web and Spring Security.

Run A/B again as two processes, log in on A, and try **/me** on B with A's cookie:

- With local container sessions, A has Authentication in A's session store.
- B lacks that session; the result is usually a redirect to login (or 401 if an API entry point is configured).
- The container cookie at this point is typically **JSESSIONID**.

If a load balancer uses sticky sessions, requests may always land on A and temporarily hide the flaw. When A goes down, clients are forced onto another node and lose state. Actual behavior also depends on any separate replication/persistence mechanism if the Servlet container was configured with one; do not label every Tomcat setup as "RAM-only" regardless of configuration.

## 6. How Spring Session Stores Data and Consistency Limits

### 6.1. SessionRepository Does Not Automatically Share Every Kind of State

In Spring Session, HttpSession operations are routed through the repository. This normally applies to:

- Session ID, creation time, last accessed time, and max inactive interval.
- **Session attributes** set by the application via HttpSession.setAttribute.
- SecurityContext when Spring Security uses a repository capable of storing into HttpSession.

Singleton beans, static fields, ThreadLocals, local caches, and WebSocket connections **do not become distributed state** just because the session repository stores data in Redis.

Bug example:

~~~java
// Illustrates the WRONG APPROACH in a multi-node app:
static final Map<String, Cart> cartsBySessionId =
    new ConcurrentHashMap<>();
~~~

That map belongs to each individual JVM. With two nodes, A's Cart does not automatically appear on B. To share Cart, move it to an appropriate business datastore or a size/serialization-controlled session attribute, depending on business and consistency needs.

### 6.2. Serialization and Rolling Deployments

When sessions leave the JVM, the server must **serialize session data**. Spring Session Redis defaults to Java serialization in common setups; serializers can be customized, e.g., JSON with Jackson and the appropriate Spring Security module.

Consequences:

- Custom classes stored in the session must be structured to serialize under the active serializer.
- If code versions on A and B differ during a rolling deployment, a session written by A may fail to deserialize on B when schemas or classes change incompatibly.
- Never put JPA entities attached to a persistence context, huge object graphs, files, or connections into HttpSession.
- Never treat native Java deserialization of untrusted external data as safe; restrict types/sources, keep libraries updated, and configure serializers per recommendations.
- Changing serializers is a stateful data change; plan a session migration/invalidation strategy rather than switching abruptly across nodes.

**Best practice:** store small, stable session attributes, such as a user ID or compact workflow state. Large or frequently changing business data belongs in a datastore with a clear concurrency model; do not dump everything into the session by default.

### 6.3. TTL and Deletion Timing

Session timeout usually represents **maximum inactivity time**. When a request accesses the session, last accessed time can be updated and the corresponding TTL refreshed by the repository.

Redis has key expiration and Spring Session has cleanup/event mechanisms; **the timing of Redis emitting expired events is not guaranteed to be accurate to an absolute wall-clock**. Therefore:

- Do not rely on "session expired" callbacks firing to the exact second for high-precision or legal business actions.
- Requests reading an expired session must be treated as having no valid session.
- If you need a maximum login lifetime even when the user is continuously active, implement a separate **absolute session lifetime**; inactivity TTL does not satisfy that requirement.

### 6.4. Concurrent Writes to the Same Session

If two concurrent requests hit A and B, both reading the same session and modifying an attribute, the outcome does not automatically become a perfectly serialized transaction:

~~~text
A reads counter=5            B reads counter=5
A writes counter=6           B writes counter=6
Final result may be 6, not 7
~~~

This is a **lost update**, not a Redis-specific bug. **SaveMode** and **FlushMode** control which fields are saved and when flushes happen, yet do not automatically provide transactional logic for every session attribute. For counters, balances, reservations, or concurrent business mutations, use database transactions, atomic Redis operations, or proper concurrency controls; **do not rely on HttpSession as a transactional store**.

## 7. RedisSessionRepository and RedisIndexedSessionRepository

Spring Session Redis has two common repository types:

| Repository | Primary Capability | Suitable Use Case |
| --- | --- | --- |
| **RedisSessionRepository** | Saves/reads sessions by session ID; no secondary index by default | Standard HTTP session sharing across multiple nodes |
| **RedisIndexedSessionRepository** | Adds indexes to find sessions by attributes such as principal name, plus event/lifecycle support | Listing/revoking sessions per user, synchronizing concurrent session policies |

In Spring Boot 3.5 and Spring Session 3.5, you can choose:

~~~properties
# Default: store session by ID
spring.session.redis.repository-type=default
~~~

Or:

~~~properties
# Indexed to look up sessions by principal
spring.session.redis.repository-type=indexed
~~~

**Do not switch to indexed merely because you have two nodes.** For logging in on A and using the session on B, the non-indexed repository is sufficient for lookups **by session ID**. Switch to indexed only when you need to find all sessions for a user, enforce session limits, or handle lifecycle events as required.

### Index/Event Limitations on Redis Cluster

Spring Session documents that **RedisIndexedSessionRepository** has limitations when subscribing to keyspace events in Redis Cluster: if events are only received on one selected Redis node, events emitted on other nodes may be missed, preventing expired session indexes from being cleaned up as expected.

Therefore, if a system runs Redis Cluster and requires accurate session revocation/limits, specifically test event propagation, your Spring Session version, and cleanup/repair mechanisms. Never assume "enabling indexed means every event is received cluster-wide."

### SessionRegistry for Concurrent Sessions

Spring Security provides an in-memory **SessionRegistryImpl**. If each app node has its own registry, concurrent-session counting only sees sessions on that node. For example, a "one session per account" limit can be bypassed when a user logs into A and B in turn.

Spring Session provides **SpringSessionBackedSessionRegistry**, which uses **FindByIndexNameSessionRepository** to query sessions by principal against the shared store.

**Illustrative** configuration sample, requiring an indexed repository bean:

~~~java
// In an appropriate @Configuration class of the application:
@Bean
<S extends Session> SpringSessionBackedSessionRegistry<S> sessionRegistry(
        FindByIndexNameSessionRepository<S> repository) {
    return new SpringSessionBackedSessionRegistry<>(repository);
}

// In SecurityFilterChain that already has sessionRegistry:
http.sessionManagement(session -> session
    .maximumSessions(1)
    .sessionRegistry(sessionRegistry)
);
~~~

This is an **excerpted configuration snippet**, not a standalone Java class: it requires importing **org.springframework.session.Session**, **FindByIndexNameSessionRepository**, **SpringSessionBackedSessionRegistry**, configuring HttpSecurity, and matching beans in the application context. In practice, separate the registry bean and pass it into SecurityFilterChain, while ensuring an indexed repository, principal index, and session expiration handling.

**Important limitation:** SpringSessionBackedSessionRegistry does not support every method of the local registry; for example, **getAllPrincipals()** is unsupported according to Spring Session documentation. If the application calls that API to list online users, design a different solution.

If writing a **custom JSON login/controller** instead of form login, configuring maximumSessions alone may not be enough: the authentication mechanism must call SessionAuthenticationStrategy and save the context properly. Moreover, session expiration events/registry lifecycle, fixation protection, and rejected-session handling must be tested in a multi-node cluster.

## 8. Redis Is a Critical Application Dependency: How to Operate It?

Moving sessions to Redis makes application nodes stateless regarding **session storage**, yet introduces a shared dependency. Every request needing a session may have to access Redis.

### 8.1. Redis Outage

When Redis loses connectivity or times out:

- Requests needing to read a session may fail to restore Authentication.
- The application may return 5xx/503 errors, time out, or behave differently depending on error handling; **no single fixed HTTP code is guaranteed**.
- Automatically falling back to local sessions when Redis fails without clear design can create split-brain state and security/consistency bugs.
- Never treat the request as anonymous and let it proceed into sensitive endpoints if identity cannot be proven. Fail closed per security requirements.

Configure connect/read timeouts, bounded retries, circuit breakers where appropriate, health/readiness probes, and incident playbooks. Unbounded retries can overload Redis even further.

### 8.2. Availability, Durability, and Eviction

A single standalone Redis is not an automatically fault-tolerant session store. Consider replication/Sentinel/managed Redis/Cluster as appropriate. Define expectations after failover:

- If Redis fails over before data replicates, some sessions may be lost.
- Memory eviction can delete session keys earlier than the inactivity timeout.
- Backups/persistence aid recovery, yet assess sensitivity of session data; restoring stale backups can reintroduce unwanted session states.
- If accepting that users must re-login when the session cache is lost, state that SLA clearly instead of assuming zero-loss.

Sessions hold security data; manage ACLs, TLS, network segmentation, credential rotation, secret vaults, namespaces, and never expose Redis ports publicly. Never log SESSION cookies, session IDs, SecurityContext, or credential data.

### 8.3. Performance and Cost

With a shared store, every session-using request can trigger read/write operations and serialization. Request volume, session size, lifetime, concurrent users, and network latency all impact load.

Useful metrics:

- Redis latency/p99, connection pool saturation, error/timeout rates.
- Active session count and data growth per namespace.
- Average/p95/p99 size of session attributes.
- Serialization/deserialization CPU, deserialization errors, failures during rollouts.
- Sudden spikes in re-logins, abnormal logouts, sessions not found.
- Redis memory fragmentation, eviction counts, key expirations, replica lag.

Optimize by shrinking session payloads, avoiding rewriting large attributes on every request, separating business data from the session, tuning save/flush modes to your workload, and benchmarking. A huge Redis dataset or misconfigured replication can become the bottleneck instead of the JVM.

## 9. Cookies, CSRF, Session Fixation, and Security Properties to Preserve

**Cookie:** Spring Session uses a cookie carrying the session ID. In HTTPS environments, configure **Secure**, **HttpOnly**, **SameSite**, domain/path, and proxy forwarding appropriately. Never put tokens/session IDs in URLs or logs. If using multiple hosts/subdomains, verify actual cookie behavior; never widen the domain excessively just so "both nodes receive the cookie."

**Session fixation:** after login, Spring Security should rotate the session ID if a prior session existed. Even with session data in Redis, keeping a pre-login ID known to an attacker remains dangerous; Spring Session does not replace session fixation protection.

**CSRF:** browsers usually send cookies automatically, so state-changing requests must still be protected. For instance, keep CSRF for POST /login and POST /logout. APIs using Bearer headers have a different threat model; **never deduce that CSRF can be disabled just because you use Redis or multiple nodes**.

**Logout:** destroying a logged-in session through the proper SecurityContextRepository/HttpSession prevents the old cookie from restoring Authentication; verify cross-node behavior. If a user logs in on multiple devices with distinct sessions, destroying **one** session does not automatically destroy all of them.

**Permissions and user state:** a session can retain an Authentication issued before a role/account changed. When permissions are revoked, you need a refresh/invalidation policy; Spring Session does not automatically update old SecurityContexts when user records change.

**Session ID and principal:** never let the client choose an account/role via self-supplied session attributes. Authentication data must come from a trusted authentication flow, never copied from client-sent JSON fields into SecurityContext.

## 10. Testing Multi-Node Behavior and Failures

A proper test must send requests to **two distinct instances**; a single JVM with two controllers does not prove session sharing.

| Scenario | Local HttpSession Without Replication | Properly Configured Spring Session + Redis |
| --- | --- | --- |
| Login on A, cookie request to A | Usually succeeds | Succeeds |
| Login on A, cookie to B | B may not know the session | B reads session from Redis and can restore Authentication |
| Restart A, cookie request to B | A's session may be lost | Usually still works if Redis session remains valid |
| Session expires | Request is no longer authenticated | Request is no longer authenticated |
| B uses a different namespace than A | Not applicable | B cannot find A's session |
| B cannot deserialize A's session | Objects not shared directly | May fail to restore session/Authentication |
| Redis loses connectivity | Local session may still work on that node | Requests needing Redis may fail or cannot read session |
| Authority changed in DB after login | Old context may retain old roles | Old context may also retain old roles; needs revocation policy |
| Concurrent logins on A/B, local registry | Session limits may be inconsistent | Consistent only with a shared registry/index and proper policy |

### Advanced Scenarios to Test

1. **Alternate A-B-A-B** after login to observe seamless sessions across nodes.
2. **Restart A** while keeping Redis and B running, verifying B still reads Authentication.
3. **Let a session expire** via a short timeout in a test environment, verifying both nodes reject the old cookie.
4. **Temporarily change B's namespace** in a test environment; requests with the same cookie must fail to find the context. Restore the namespace before continuing tests.
5. **Stop Redis** in a test environment, observing status codes, controlled logs, and recovery time; do not hardcode assumptions of 500/503 if error handling differs.
6. **Rolling deployment across versions** with custom session attributes, verifying backward/forward serializer compatibility.
7. **Concurrent writes** to the same session from A and B, checking for lost updates and atomic storage strategies.
8. **Concurrent session control** with logins on A and B, if the application actually enforces a maximumSessions policy.
9. **Log out on B, reuse cookie on A**, verifying the session was revoked in the shared store.
10. **Cookie mismatch**: differing path/domain/SameSite/Secure/proxy scheme, checking whether the browser sends cookies to the right host.

**Automated testing tip:** applications can use **Testcontainers Redis** or a shared Redis test service for two Spring Boot processes/containers, routing requests to two different base URLs while maintaining one HTTP cookie jar. Never mock SessionRepository and deduce that real failover works.

## 11. Common Errors and How to Diagnose

### 11.1. Redis Is Present, Yet Node B Requests Still Prompt for Login

Check in order:

1. Does B receive the **SESSION cookie** in the request? Are domain/path/proxy/HTTPS blocking the cookie?
2. Do A and B share the exact same Redis host, database, namespace, and session serializer?
3. Does Redis contain the corresponding session ID, and is it still valid or deleted?
4. Does node B actually have **springSessionRepositoryFilter** configured, or only a Redis client dependency?
5. Does Spring Security on B use HttpSession SecurityContextRepository and an appropriate stateful policy?
6. Did login on A **save SecurityContext**, or only set the holder temporarily during the request?
7. Can node B deserialize the SecurityContext/principal classes serialized by A?
8. Are there differences in the Spring Security filter chains between the two nodes?

Do not start by disabling CSRF or changing roles before verifying sessions and cookies.

### 11.2. First Login Works, Logged Out After Deployment

Check whether sessions live in RAM or Redis, whether Redis restarted/evicted keys, or whether new code cannot deserialize old session data; inspect TTLs, Redis persistence/replication, and changes to cookie domain/name. For incompatible serialization upgrades, plan a compatibility bridge or controlled session invalidation.

### 11.3. Configured maximumSessions(1), Yet User Logs In on Two Nodes

Very likely **SessionRegistryImpl** is still local; logins on the two nodes do not see each other. With Spring Session, inspect **indexed session repository**, **SpringSessionBackedSessionRegistry**, exact indexes, session events/lifecycle, and how the login mechanism calls the session strategy. Test cross-node logins in real tests.

### 11.4. Redis Memory Grows Rapidly

Check session payload size, session count, TTLs, uncleaned idle sessions, large data or redundant object graphs in attributes, index/event cleanup, and eviction. Never delete all Redis keys with a wildcard in production as a "quick fix"; diagnose by namespace partition and impact on other applications.

### 11.5. Spring Session Works, Yet Business Data Still Vanishes

Check whether that data is actually stored in HttpSession via the repository or sits in a singleton/static map/Caffeine cache/local file. Spring Session does not share every JVM variable. Move shared state to a datastore designed for that type of state.

### 11.6. User Logs Out on One Node, Yet Another Node Still Allows Access

Check the actual cookie used, Authentication/custom token caches, session invalidation, SecurityContextRepository, TTL, replica lag, and independent auth sources such as remember-me/Bearer tokens. A system can have both sessions and Bearer tokens: destroying a session does not automatically revoke all other tokens.

## 12. Architectural Decision: When Do You Need Spring Session?

**Evaluate Spring Session** when:

- The application uses session login/cookies to maintain Authentication and needs to scale across multiple instances.
- You want failover and rolling deployments with minimal session loss.
- You need controlled sharing of HttpSession attributes across nodes.
- You have the operational capability to run a shared store reliably, securely, and at scale.

**It may be unnecessary for Authentication** when:

- APIs use Bearer tokens/API keys verified on **every request** without relying on HttpSession.
- No business data must be stored in HttpSession.
- The application runs as a single instance without requiring session survival across restarts/failovers, accepting session loss per system design.

Whichever solution you choose, separate three concerns:

1. **Authentication:** who is calling and is the proof valid?
2. **Session state persistence:** where are login results/session data kept so subsequent requests can read them?
3. **Authorization and lifecycle:** how are current permissions, logout, revocation, concurrency, expiration, and auditing handled?

Spring Session solves cross-node session storage and provides session-management integrations. It does not by itself complete authentication, authorization, distributed business data, or high availability of the session store.

## 13. Self-Check Questions

**1.** A user logs into node A, the browser sends the cookie when requesting B, yet B prompts for login. Why does this happen with local HttpSession?

**Answer:** The cookie holds only the ID; the corresponding session lives in A's store. B does not automatically have A's session data without configuring replication or a shared store.

**2.** Do sticky sessions guarantee preserving login if A dies?

**Answer:** No. Sticky routing only prefers returning to A while A is alive; it does not replicate session data from A to B.

**3.** Does Spring Session + Redis automatically make node A's SecurityContextHolder appear in node B's thread?

**Answer:** No. Each request has its own SecurityContextHolder. B restores the SecurityContext **saved in HttpSession** via the shared repository.

**4.** How do cookies named SESSION and JSESSIONID differ?

**Answer:** Both can carry a session identifier. Servlet containers typically use JSESSIONID; Spring Session with DefaultCookieSerializer uses SESSION by default. The name is configurable.

**5.** Is merely having the spring-session-data-redis dependency on both nodes enough?

**Answer:** No. Both need the same Redis/namespace, cookie policy, session serializer, and compatible SecurityContext mechanism, plus verification that the filter is registered.

**6.** When should you use RedisIndexedSessionRepository?

**Answer:** When you need to index/search sessions by principal, handle events, or manage sessions across multiple nodes; sharing sessions by ID normally only needs RedisSessionRepository. With Redis Cluster, account for event/cleanup limitations.

**7.** Why can SessionRegistryImpl allow a user to log in on two nodes despite setting maximumSessions(1)?

**Answer:** If the registry is in local memory, each node sees only a subset of sessions. You need a registry backed by the shared session store with matching lifecycle setup.

**8.** A and B share Redis but use different namespaces. Do they share login sessions?

**Answer:** No. B looks up keys in a different namespace and cannot find the session data stored by A.

**9.** For a REST API using stateless JWTs, is Spring Session mandatory just because the system runs multiple pods?

**Answer:** No. If Authentication is verified independently via token on every request and HttpSession is not needed, Spring Session is not required to scale pods.

**10.** If Redis goes down, should requests automatically be accepted as recently logged-in users?

**Answer:** No. If Authentication cannot be verified from the session, access must not be granted arbitrarily; handle errors fail-closed and restore the service.

## Official Documentation for Further Reading

- [Spring Boot 3.5 — Spring Session auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-session.html)
- [Spring Session 3.5 — Redis configurations, indexed repository, events, namespace](https://docs.spring.io/spring-session/reference/3.5/configuration/redis.html)
- [Spring Session — Spring Boot + Redis guide](https://docs.spring.io/spring-session/reference/guides/boot-redis.html)
- [Spring Session — HttpSession integration](https://docs.spring.io/spring-session/reference/httpsession.html)
- [Spring Session — Common configurations and cookie serializer](https://docs.spring.io/spring-session/reference/configuration/common.html)
- [Spring Session — Spring Security integration, distributed session registry](https://docs.spring.io/spring-session/reference/spring-security.html)
- [Spring Security 6.5 — Authentication persistence and session management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — CSRF token and servlet integration](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
