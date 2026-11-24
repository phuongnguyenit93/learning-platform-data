# Spring Session and Choosing a Session Store Compatible with Each Web Stack

## 1. Learning objectives and core question

A Spring Boot application can store a value such as `cartId` or `visits` in a session so subsequent requests from the same browser can read it back. Once the application runs on two instances, a harder question arises: **which instance stores the session, how are sessions shared, and does the session API belong to Spring MVC or WebFlux?**

**Spring Session** decouples session management from individual web server memory, providing APIs and integrations to store sessions in Redis, databases, or other backends. However, **Servlet/MVC and WebFlux have two different repository contracts**. You cannot pick a backend solely because “we already have Redis/JDBC”; you must examine the web stack and whether the adapter operates in a blocking or reactive manner.

After this lesson, you will be able to:

1. Distinguish **a session ID in a cookie**, server-side session state, and stateless authentication tokens.
2. Explain how Spring Session replaces Servlet `HttpSession` via `SessionRepositoryFilter` and integrates with WebFlux `WebSession` via `WebSessionManager`.
3. Recognize that `SessionRepository` (synchronous) differs from `ReactiveSessionRepository` (reactive), and select the right session store for each web stack.
4. Configure **Spring MVC + Spring Session JDBC** and **Spring WebFlux + Spring Session Data Redis** in Spring Boot 3.3.x.
5. Observe sessions using `curl`, cookie jars, consecutive requests, port/instance switching, and inactivity timeouts.
6. Reason through the trade-offs of Redis, JDBC, MongoDB, and in-memory repositories, along with serialization, TTL, security, performance, and operational pitfalls.

The examples use **Java 17+, Spring Boot 3.3.5, and Spring Session 3.3.x** via Spring Boot dependency management. Starter names or auto-configured store sets may change in other Spring Boot lines; do not copy Spring Boot 4.x configuration into a 3.3.x lab without checking.

## 2. Sessions, cookies, and where the real data lives

HTTP by itself does not remember that two requests came from the same user. A session mechanism usually consists of:

- **Session ID**: an unpredictable string representing a session; the app commonly delivers it to the browser via a cookie, such as `SESSION` when using Spring Session.
- **Session attributes**: data stored **on the server side**, such as `visits=2` or a cart ID. The browser normally does not directly receive the full attribute map.
- **Session repository**: the component that creates, reads, updates, expires, or deletes sessions; it may live in local RAM, Redis, a SQL database, etc.
- **Session expiration**: the inactivity limit (idle timeout), tied to last-accessed time and storage/cleanup policies.

Illustrative sequence:

~~~text
First request (no session cookie yet)
  Browser -- GET /counter --> Server A
  Server A -- create session id S, set visits=1 --> Repository
  Server A -- Set-Cookie: SESSION=<opaque-id> --> Browser

Next request
  Browser -- Cookie: SESSION=<opaque-id> --> Server B
  Server B -- read session S from Repository --> visits=1
  Server B -- set visits=2 and save session --> Repository
  Server B -- response {visits: 2} --> Browser
~~~

If Server A and Server B share the **same session mechanism and properly configured repository**, the second request can continue the session even when routed to another instance. If each instance keeps only an in-memory map in its own RAM, Server B cannot see A's sessions. Load balancer sticky sessions can steer requests back to A, yet do not fully handle failover, restarts, or instance loss.

A cookie containing only a session ID **is not a JWT**. JWTs normally carry signed claims that a server can verify statelessly; a session ID is a lookup key pointing to server-stored state. Spring Session does not automatically turn sessions into JWTs. Nor should a cookie be trusted as proof that the user is logged in: access rights must be established by authentication/authorization mechanisms.

**Avoid confusing “session cookie” with “session timeout”:**

- A cookie may omit `Max-Age`, causing browsers to treat it as a browser-session cookie; that does not mean the server-side session never expires.
- `spring.session.timeout=20m` (in compatible Boot configs) sets the session inactivity limit, not a guarantee that the browser deletes the cookie after exactly 20 minutes.
- Once the server sees a session ID has expired, the session is invalid even if the browser keeps sending the old cookie.
- When the underlying record is physically removed by Redis TTL or a SQL cleanup job may lag behind when the session becomes logically invalid.

## 3. Which mechanisms does Spring Session replace?

### 3.1. Servlet / Spring MVC

In traditional Servlet applications, the public API is `jakarta.servlet.http.HttpSession`. Without Spring Session, sessions are typically managed by the servlet container (e.g., Tomcat) per container settings.

When adding a synchronous Spring Session repository to Boot MVC, the central integration is **`SessionRepositoryFilter`**: a filter wrapping request/response so `request.getSession()` / `HttpSession` parameters use sessions managed by **`SessionRepository<S>`**. Servlet controllers still read and write attributes via the familiar `HttpSession` API.

~~~text
HTTP request + cookie
    |
    v
Servlet Filter chain
    |
    v
SessionRepositoryFilter
    |
    +--> read/create Session from SessionRepository
    |
    v
Spring MVC Controller -> HttpSession.setAttribute(...)
    |
    v
SessionRepository (Redis / JDBC / ...)
    |
    v
HTTP response + session cookie (when needed)
~~~

This does not convert controllers into reactive APIs. Synchronous JDBC or Redis repositories still perform blocking I/O; in Spring MVC, that fits the common thread-per-request model provided connection pools, timeouts, and databases are properly managed.

### 3.2. Reactive / Spring WebFlux

In Spring WebFlux, the public API is **`org.springframework.web.server.WebSession`**, not Servlet `HttpSession`. Spring Session provides **`ReactiveSessionRepository<S>`** and integrates via **`WebSessionManager`**. Repository read/write operations are modeled with Reactor `Mono`/`Flux`, remaining compatible with the reactive pipeline.

~~~text
HTTP request + cookie
    |
    v
WebFlux ServerWebExchange
    |
    v
WebSessionManager
    |
    +--> ReactiveSessionRepository (reactive Redis / reactive Mongo)
    |
    v
Reactive Controller -> WebSession.getAttributes().put(...)
    |
    v
Reactive persistence + complete response
~~~

WebFlux can run on Reactor Netty **or** on a Servlet container via a runtime adapter. **The web stack is determined by Spring MVC vs. WebFlux, not just the server name.** Running WebFlux on Tomcat does not turn `WebSession` into `HttpSession`.

### 3.3. The two repositories are two distinct contracts

| Characteristic | Servlet / MVC | WebFlux |
| --- | --- | --- |
| Session web API | `HttpSession` | `WebSession` |
| Core repository contract | `SessionRepository<S extends Session>` | `ReactiveSessionRepository<S extends Session>` |
| Repository call style | Synchronous, returns data directly | Reactive, returns publishers |
| Integration component | `SessionRepositoryFilter` | `WebSessionManager` and WebSessionStore |
| In-memory for demos/tests | `MapSessionRepository` | `ReactiveMapSessionRepository` |
| Redis | `RedisSessionRepository` / indexed Redis repository | `ReactiveRedisSessionRepository` / reactive indexed repository |
| Common SQL/JDBC | `JdbcIndexedSessionRepository` | **No equivalent reactive Spring Session JDBC adapter in typical Boot 3.3 setups** |
| Reading/writing in controller | `session.getAttribute` / `setAttribute` | `session.getAttribute` / `getAttributes().put`; `invalidate` returns `Mono<Void>` |

Understand this: having `spring-boot-starter-data-r2dbc` or a reactive SQL driver in a project **does not automatically create** a Spring Session repository implementation over R2DBC. Similarly, pulling `spring-session-jdbc` into WebFlux does not create a `ReactiveSessionRepository`. The datastore and session adapter must match the contract.

## 4. Session store selection matrix in Spring Boot 3.3.x

For Spring Boot 3.3, typical auto-configured session store options documented for this release line include:

| Backend | Servlet/MVC | WebFlux | Remarks |
| --- | --- | --- | --- |
| **Redis** | Yes, synchronous session repository | Yes, reactive Redis repository | Popular choice when multiple replicas share sessions, with TTL and low latency |
| **JDBC/SQL** | Yes, `spring-session-jdbc` | No auto-configured reactive JDBC session repository | Fits teams already operating an RDBMS at moderate scale; watch SQL connection pools |
| **MongoDB** | Yes, with compatible module/conditions | Yes, reactive Mongo repository in supported line | Fits teams already running Mongo; verify indexes and expiry |
| **Hazelcast** | Yes in Boot 3.3 with matching module | Not a Boot 3.3 reactive auto-config option | Consider when an organization already runs a data grid |
| **In-memory map** | Yes in Spring Session core | Reactive variant for demos | Data lost on restart; does not share across instances automatically |
| **Apache Geode (separate integration)** | Module/integration dependent | Not default | Consider only if already in use with compatible versions |

**Version note:** Spring Boot 3.3/3.4 documentation lists more store choices than some newer Boot releases. Never assume every store in the table is auto-configured across **all** Boot versions or uses identical starter names. Always check the support matrix for your exact Spring Boot and Spring Session versions.

**Simple selection rule:**

1. **First identify the web stack**: genuine MVC/Servlet vs. WebFlux.
2. **Choose the repository contract**: synchronous `SessionRepository` for MVC, `ReactiveSessionRepository` for WebFlux.
3. **Pick a datastore with a compatible adapter and driver**: Redis for both; JDBC normally for Servlet only.
4. **Evaluate operations**: existing Redis/Mongo/SQL infrastructure, latency constraints, quotas, eviction, failover, cleanup, metrics, and backups.
5. **Evaluate feature needs**: lookup by principal, session events, bulk session invalidation, security, and serialization. Indexed repositories are sometimes required, at extra cost/complexity.

There is no universal rule that “Redis is always fastest” or “JDBC is always safest” for every workload. Redis involves network/TTL/eviction; JDBC involves locks/transactions, queries, and connection pools; Mongo involves indexes and TTL cleanup. Measure each choice under realistic load.

## 5. When Spring Session is not needed yet

A single-instance demo app can use default `HttpSession` (MVC) or `WebSession` (WebFlux) backed by the framework's local store. If you only hold trivial session state that does not need to survive restarts or scale out, adding Spring Session infrastructure may not be worthwhile.

Conversely, these requirements justify considering Spring Session:

- Multiple replicas must read the same session data as a load balancer distributes requests across instances.
- Sessions must survive restarting or replacing an instance, subject to the store's durability mechanisms.
- Standardized session management and instrumentation decoupled from Tomcat/Netty container specifics.
- Integration with Spring Security session management, concurrency control, or principal-based lookup when the repository supports indexing.

**Stateless APIs** using self-verifiable access tokens with no server-side session needs may **not need** Spring Session. Do not install Spring Session merely because a project uses Spring Security: stateless vs. stateful authentication are separate architectural decisions.

## 6. Lifecycle of a distributed session

A session-enabled request typically passes through these phases:

~~~text
Request with session ID cookie (or none yet)
       |
       v
Load session from repository
       |
       +-- missing / expired ID -> create new session when app needs one
       |
       '-- valid ID -> fetch attributes and metadata
       |
       v
Controller/service reads/writes attributes
       |
       v
Persist changes + lastAccessedTime per save/flush policy
       |
       v
Send response + cookie if needed
       |
       v
Idle timeout / logout / invalidation -> session no longer valid
       |
       v
Backend cleanup/TTL removes remaining data via its own mechanism
~~~

**A performance detail:** updating `lastAccessedTime`, modifying attributes, or save/flush policies can trigger I/O to the session store on every request. At high RPS, storing sessions remotely adds **dependency and network/DB overhead**, rather than being zero-cost.

Never assume a session is written **exactly once** per HTTP request: repository types, `FlushMode`, and `SaveMode` govern write frequency differently. When multiple parallel requests arrive from one browser, account for **race conditions** and lost updates on the same attribute. For instance, incrementing a counter in a session is not an atomic distributed counter.

### 6.1. Sharing a session ID does not mean serialization is compatible

Two apps pointing at the same Redis may still fail to read each other's sessions if:

- Namespaces or cookie names differ; a session ID from App A points to a namespace missing in App B.
- Serializers differ (Java serialization vs. JSON, class types, package names, `serialVersionUID`).
- Two frameworks or versions have incompatible session schemas or attribute/security-context models.
- Cookie `Domain`, `Path`, `Secure`, or `SameSite` prevents the browser from sending the ID as expected.

In particular, **never assume MVC and WebFlux can share sessions just because both use Redis**. The two stacks have different abstractions and stored structures; cross-stack interoperability requires deliberate design, serialization/cookie/principal testing, and often SSO/OIDC instead of directly sharing session attributes.

## 7. Lab A — Spring MVC + Spring Session JDBC (Java 17+)

Lab A demonstrates a **synchronous** SQL repository. It uses **in-memory** H2 so no external database setup is needed while learning. H2 loses all data when the app stops; this is **not** a promise of restart persistence. To share data across multiple replicas, switch to a properly configured and migrated PostgreSQL/MySQL database.

### 7.1. Project structure

~~~text
mvc-session-jdbc/
├── pom.xml
└── src/main/
    ├── java/com/example/mvcsession/
    │   ├── MvcSessionApplication.java
    │   └── VisitController.java
    └── resources/
        └── application.properties
~~~

**File `pom.xml`** (Spring Boot 3.3.5; dependency versions managed by parent):

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>mvc-session-jdbc</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.session</groupId>
            <artifactId>spring-session-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
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
~~~

`spring-boot-starter-web` enables MVC/embedded Tomcat. `spring-boot-starter-jdbc` supplies `DataSource` and JDBC infrastructure, `spring-session-jdbc` supplies the SQL session repository, and H2 acts as the lab database. Do not add `spring-boot-starter-webflux`, as this lab verifies `HttpSession`.

**File `src/main/resources/application.properties`:**

~~~properties
server.port=8081

spring.datasource.url=jdbc:h2:mem:sessiondemo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.session.timeout=20m
spring.session.jdbc.initialize-schema=always
~~~

`spring.session.jdbc.initialize-schema=always` makes sense only in the H2 lab. In production, manage the `SPRING_SESSION` and `SPRING_SESSION_ATTRIBUTES` schema via migration tools and DBA processes to avoid unexpected schema initialization during deployments. Consult exact DDL and default table names for your dialect and version.

**File `src/main/java/com/example/mvcsession/MvcSessionApplication.java`:**

~~~java
package com.example.mvcsession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcSessionApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcSessionApplication.class, args);
    }
}
~~~

**File `src/main/java/com/example/mvcsession/VisitController.java`:**

~~~java
package com.example.mvcsession;

import java.util.Map;

import jakarta.servlet.http.HttpSession;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class VisitController {

    @GetMapping("/counter")
    public Map<String, Object> counter(HttpSession session) {
        Object stored = session.getAttribute("visits");
        int previous = stored instanceof Integer n ? n : 0;
        int current = previous + 1;
        session.setAttribute("visits", current);

        return Map.of(
                "visits", current,
                "sessionId", session.getId()
        );
    }

    @PostMapping("/reset")
    public Map<String, String> reset(HttpSession session) {
        session.invalidate();
        return Map.of("status", "invalidated");
    }
}
~~~

This is a **working Spring MVC controller**. You still use `jakarta.servlet.http.HttpSession` without writing raw SQL in the controller. Spring Session and Boot wire the JDBC repository beneath the request's session layer.

`visits` is an `Integer`, making it easy for the repository's serializer to store. Never store `Connection`, `EntityManager`, `HttpServletRequest`, or request/thread-bound objects in the session. This counter is a **sequential demo**, not safe for concurrent requests hitting the same session.

### 7.2. Run and verify

From the created project root directory, with JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

In a second terminal, save the cookie to a file:

~~~bash
curl -i -c mvc-cookies.txt http://localhost:8081/counter
curl -i -b mvc-cookies.txt -c mvc-cookies.txt http://localhost:8081/counter
curl -i -b mvc-cookies.txt -c mvc-cookies.txt http://localhost:8081/counter
~~~

Expect JSON responses for the same session with `visits` returning **1, 2, 3** respectively; `sessionId` is dynamically generated, so there is no fixed string to match. The first response typically emits a session `Set-Cookie`; subsequent calls send the cookie from the file. The cookie value may be encoded differently from the `sessionId` string returned in the example; verify session continuity rather than expecting two identical byte strings.

Test invalidation (do not use GET for state-changing actions):

~~~bash
curl -i -X POST -b mvc-cookies.txt -c mvc-cookies.txt http://localhost:8081/reset
curl -i -b mvc-cookies.txt -c mvc-cookies.txt http://localhost:8081/counter
~~~

The `/reset` response has JSON body:

~~~json
{"status":"invalidated"}
~~~

The next `/counter` call creates/saves a new session with `visits=1`. To test completely without cookies, omit `-b` and use a fresh cookie jar or a client without prior cookies.

**Limitation of Lab A:** H2 runs inside the memory of a **single JVM**. Launching a second instance creates a separate H2 database, so this lab cannot demonstrate two replicas sharing sessions. To verify multi-instance JDBC, configure **the same real SQL database server**, schema, and compatible session serialization.

## 8. Lab B — Spring WebFlux + reactive Spring Session Redis

Lab B uses a **reactive** repository. Unlike Lab A, the controller accepts `WebSession` and does not use `HttpSession`. Redis must be running on `localhost:6379`; you can use Docker or an installed Redis service.

### 8.1. Structure and dependencies

~~~text
webflux-session-redis/
├── pom.xml
└── src/main/
    ├── java/com/example/reactivesession/
    │   ├── ReactiveSessionApplication.java
    │   └── ReactiveVisitController.java
    └── resources/
        └── application.properties
~~~

**File `pom.xml`:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>webflux-session-redis</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <artifactId>spring-boot-starter-data-redis-reactive</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.session</groupId>
            <artifactId>spring-session-data-redis</artifactId>
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
~~~

These dependencies supply WebFlux, reactive Redis connection infrastructure (typically Lettuce), and Spring Session Data Redis; Boot 3.3 can auto-configure the corresponding Redis-backed `WebSession` repository. Do not add `spring-session-jdbc` to this lab. In Boot 3.3, `spring-session-data-redis` and `spring-session-jdbc` are declared directly as shown; do not use new session starter names from other Boot versions without checking.

**File `src/main/resources/application.properties`:**

~~~properties
server.port=8082

spring.data.redis.host=localhost
spring.data.redis.port=6379
spring.session.timeout=20m
spring.session.redis.namespace=spring:session:webflux-lab
~~~

The namespace keeps lab session keys separate from other apps sharing the same Redis. Never store Redis passwords in source-controlled files for production; supply them via a secret manager or environment configuration.

Start Redis (if Docker is available) in a separate terminal:

~~~bash
docker run --rm --name webflux-session-redis -p 6379:6379 redis:7-alpine
~~~

This runs the container in the foreground; run the Spring Boot app in another terminal. If local Redis already occupies port 6379, reuse that server or change ports consistently; do not run two servers on the same port.

**File `src/main/java/com/example/reactivesession/ReactiveSessionApplication.java`:**

~~~java
package com.example.reactivesession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveSessionApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveSessionApplication.class, args);
    }
}
~~~

**File `src/main/java/com/example/reactivesession/ReactiveVisitController.java`:**

~~~java
package com.example.reactivesession;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.WebSession;

import reactor.core.publisher.Mono;

@RestController
public class ReactiveVisitController {

    @GetMapping("/counter")
    public Mono<Map<String, Object>> counter(WebSession session) {
        int previous = session.getAttributeOrDefault("visits", 0);
        int current = previous + 1;
        session.getAttributes().put("visits", current);

        return Mono.just(Map.of(
                "visits", current,
                "sessionId", session.getId()
        ));
    }

    @PostMapping("/reset")
    public Mono<Map<String, String>> reset(WebSession session) {
        return session.invalidate()
                .thenReturn(Map.of("status", "invalidated"));
    }
}
~~~

Here:

- `WebSession` belongs to Spring WebFlux; the framework resolves the argument via the reactive request pipeline.
- Calling `getAttributes().put` marks the session as having state so it is persisted according to the WebFlux lifecycle.
- `Mono.just(...)` represents the response payload; Spring WebFlux and `WebSessionManager` coordinate committing the session when finalizing the response.
- `session.invalidate()` **returns `Mono<Void>`**, so `thenReturn` emits the response only after the operation completes. Never call `block()` on an event-loop thread.
- The counter only illustrates session round-trips; concurrent requests can race under non-atomic read-modify-write.

### 8.2. Run and verify

From the project directory, once Redis is ready:

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -i -c reactive-cookies.txt http://localhost:8082/counter
curl -i -b reactive-cookies.txt -c reactive-cookies.txt http://localhost:8082/counter
curl -i -b reactive-cookies.txt -c reactive-cookies.txt http://localhost:8082/counter
~~~

Expect `visits` to be **1, 2, 3** with the same logical session ID. If the first response does not set a cookie or subsequent requests reset to 1, verify that the repository was actually auto-configured, Redis is connected, cookie headers and namespace match, and the session was started/modified.

Reset:

~~~bash
curl -i -X POST -b reactive-cookies.txt -c reactive-cookies.txt http://localhost:8082/reset
curl -i -b reactive-cookies.txt -c reactive-cookies.txt http://localhost:8082/counter
~~~

Expect the reset response to show `status=invalidated`, and the next counter request to start again at `visits=1`. Use `curl.exe` instead of `curl` when older PowerShell versions map an incompatible alias.

### 8.3. Testing two instances sharing Redis

You can build a JAR and run two instances **from two terminals** (same Redis/namespace and same code):

~~~bash
mvn clean package
java -jar target/webflux-session-redis-0.0.1-SNAPSHOT.jar --server.port=8082
~~~

In the second terminal:

~~~bash
java -jar target/webflux-session-redis-0.0.1-SNAPSHOT.jar --server.port=8083
~~~

Send the cookie obtained from the first instance to the second instance:

~~~bash
curl -i -c shared-cookies.txt http://localhost:8082/counter
curl -i -b shared-cookies.txt -c shared-cookies.txt http://localhost:8083/counter
curl -i -b shared-cookies.txt -c shared-cookies.txt http://localhost:8082/counter
~~~

When Redis is working, both instances run identical code/config, and the client retains a valid cookie, `visits` normally progresses **1 → 2 → 3**, even across the two different processes. HTTP cookies are not scoped by **port**, so two ports on `localhost` share cookies matching domain/path/secure policy. Never extrapolate from two `localhost` ports that separate production domains share cookies automatically.

If both instances use the same Redis yet specify different `spring.session.redis.namespace` values, they effectively have isolated sessions. Namespace is part of the session identity layout in the datastore.

## 9. Redis options: default, indexed, TTL, and events

With Spring Session Data Redis, there is a difference between the standard Redis repository and the **indexed** repository:

- **Default Redis repository**: suitable when you mainly need lookup by session ID, create/save/delete, and expiration.
- **Indexed Redis repository**: adds secondary indexes and capabilities like looking up sessions by principal or created/deleted/expired events (depending on implementation/version); in exchange, consider Redis keyspace notifications, cleanup, and index overhead.

In Spring Boot 3.3, properties such as the following are documented:

~~~properties
spring.session.redis.repository-type=default
# Or only when the application genuinely needs indexing:
# spring.session.redis.repository-type=indexed
~~~

Do not enable `indexed` merely because the name sounds “more complete”. If you have features like “log out all sessions for an account”, concurrent session limits, or closing WebSocket connections when a session is deleted, check whether the repository supports the required index/events, principal policy, and Spring Security config.

**Operational Redis notes:**

1. **Expiration:** TTL expires sessions, yet key-deletion events are not guaranteed to fire at the exact second; do not rely on keyspace events as an exact business timer.
2. **Eviction:** Redis running out of memory may evict keys early under `maxmemory-policy`, logging users out before timeout.
3. **Persistence and failover:** Redis runs in memory; survival across restarts depends on persistence/replication/managed-service configuration. Sharing sessions in Redis does not automatically guarantee zero data loss.
4. **Serialization:** attributes may use Java serialization by default; incompatible class/package/version changes cause deserialization errors. Standardize small DTOs, serializers, namespacing/versioning, and migration strategies.
5. **Network:** a remote store adds network RTT; timeouts or disconnects can fail session-dependent endpoints. Monitor Redis latency, connection pools, and failover health.
6. **Namespace:** isolate apps, tests, and prod when sharing a Redis instance; do not share namespaces across apps unless intentionally designed to share sessions.
7. **Data minimization:** sessions should hold only small IDs/state—never full user objects, large DB caches, or unnecessary sensitive secrets/tokens.

## 10. JDBC: schema, connection pool, and cleanup

`spring-session-jdbc` uses relational tables to store session metadata and attributes. In Spring Boot 3.3, `spring.session.jdbc.*` includes example settings like:

~~~properties
spring.session.timeout=20m
spring.session.jdbc.table-name=SPRING_SESSION
spring.session.jdbc.initialize-schema=embedded
# Cleanup frequency for expired data as needed:
# spring.session.jdbc.cleanup-cron=0 * * * * *
~~~

`initialize-schema=embedded` auto-initializes only when the database is detected as embedded per policy. In production, avoid careless `initialize-schema=always`; manage schemas via Flyway/Liquibase or controlled migrations.

**JDBC repository performance** depends on `SELECT`/`INSERT`/`UPDATE`/`DELETE` session speeds, indexing, transactions, HikariCP connection pooling, DB latency, and cleanup. Size `maximumPoolSize` and connection budgets across the **total** replica count. If the business database is already near saturation, putting sessions in the same DB can create severe contention.

**Expired rows differ from expired sessions:** the application treats a session as expired based on metadata before the cleanup job deletes rows. Do not count `SPRING_SESSION` rows as an “exact online user count”.

**Do not use the JDBC repository as if it were non-blocking for WebFlux.** `JdbcIndexedSessionRepository` accesses JDBC synchronously; it does not implement `ReactiveSessionRepository`. If a WebFlux app truly must store sessions in SQL, design a proper reactive adapter or carefully evaluate blocking/offloading, transactions, serialization, and maintenance—rather than adding the JDBC dependency and calling `block()` inside controllers.

## 11. What roles do MongoDB, Hazelcast, and in-memory play?

**MongoDB:** in the Spring Boot 3.3 line, there is session integration for Servlet and a reactive repository for WebFlux when matching modules/drivers are present. Appropriate when MongoDB is already operated, provided you evaluate session documents/indexes, TTL indexes, cleanup delay, write concern, schema/serializers, startup auto-config, and Mongo driver version. Simply having reactive Spring Data Mongo does not guarantee compatible Spring Session repositories if the right module is missing.

**Hazelcast:** can be an option for Servlet in Boot 3.3 when an organization already runs a data grid. Do not assume having a Hazelcast client in WebFlux implies an auto-configured reactive session repository. Evaluate topology, expiration, cluster discovery, and HA.

**MapSessionRepository / ReactiveMapSessionRepository:** useful for tests, demos, or simple local apps. An in-memory map lacks durability, replication, and full automatic TTL cleanup unless configured manually. **Do not use a local map repository as evidence of clustered session support.**

**Portability:** Spring Session standardizes application-side APIs, yet does not automatically convert data formats across backends. Migrating from JDBC to Redis generally requires a migration policy and may invalidate existing sessions; plan deployment, cookies, and user communication accordingly.

## 12. Places where the wrong stack is easily chosen

### 12.1. Having both spring-boot-starter-web and spring-boot-starter-webflux

In standard Boot 3.3 setups, if **both** starters are on the classpath, Boot defaults to a **Servlet Web Application** to support using `WebClient` alongside MVC. Do not spot a Reactor dependency and assume the reactive `WebSession` repository is active.

Confirm via startup logs, `WebApplicationType`, and active beans/handlers. For a pure WebFlux app, keep `spring-boot-starter-webflux` without pulling MVC onto the classpath unintentionally; when explicitly configuring application type, verify `spring.main.web-application-type` with full dependency alignment.

### 12.2. Using HttpSession in WebFlux

`HttpSession` is a Servlet API; WebFlux handlers use `WebSession`. Tomcat can run a reactive adapter, yet that does not turn `HttpSession` into the standard WebFlux session API.

### 12.3. Mismatched JDBC drivers or reactive RedisTemplates

A data library may support both blocking and reactive clients. Always ask **which repository type Spring Session is injecting**. If WebFlux cannot find a `ReactiveSessionRepository`, adding a synchronous `SessionRepository` will not magically externalize reactive Spring Sessions.

### 12.4. Manually adding @EnableRedisHttpSession / @EnableRedisWebSession when Boot already auto-configures

These annotations are for manual Spring Session configuration; in Spring Boot apps with working auto-configuration they are typically **unnecessary**. Adding `@Enable*HttpSession` or `@Enable*WebSession` manually can cause Boot auto-configuration to back off, making properties and custom beans behave differently than expected. Keep a single consistent configuration style and inspect the created beans.

### 12.5. Confusing cookie name, path, or hostname

`SESSION` and `JSESSIONID` are not always interchangeable. Do not hardcode cookie names without checking real `Set-Cookie` headers and version/config. Cookies are bound by domain/path/SameSite/Secure, not by port. A redirect across domains, an HTTPS proxy, or a changed base path can prevent the browser from sending the cookie, resulting in a new session.

## 13. Sessions, Spring Security, and system safety

Spring Session does not replace authentication or authorization. When using Spring Security:

- **Session fixation:** after login, the session ID normally must be rotated; Spring Security provides session fixation protection in the respective stack. On Servlet, `HttpServletRequest.changeSessionId()` exists; on WebFlux, `WebSession.changeSessionId()` returns a publisher to compose.
- **Cookies:** use HTTPS, `Secure`, `HttpOnly`, and `SameSite` appropriately; never set `Secure=true` in an HTTP-only lab expecting cookies to work as in HTTPS. Reverse proxies must forward scheme/forwarded headers accurately.
- **CSRF:** stateful cookie-based apps must evaluate CSRF protection on state-changing requests, especially with Spring Security. `SameSite` reduces risk but is not an unconditional substitute for CSRF protection.
- **Authorization:** a session may store a user ID, yet every sensitive operation still needs authorization checks. Never trust unvalidated attributes.
- **Session ID:** treat it as a bearer credential. Never log raw session IDs, embed them in URLs, or share them via analytics/`Referer`; guard against session hijacking.
- **Logout/invalidation:** beyond deleting cookies, invalidate the server-stored session; with multiple token types or SSO, logout may require extra steps.
- **Timeout:** set inactivity limits fitting risk and UX; expiration/cleanup events can be asynchronous and must not serve as a precise authentication clock.
- **Serialization:** store only essential data; avoid passwords, private keys, resource handles, or excessive personal data.

Cookie properties in Boot 3.3 are split by stack: servlet uses `server.servlet.session.cookie.*`, while reactive uses `server.reactive.session.cookie.*`. Spring Session also provides ways to customize cookie serializers/resolvers. **Verify which configuration actually applies** when Spring Session is active, rather than assuming container properties always govern cookies issued by Spring Session.

## 14. Common errors and how to diagnose them

| Symptom | Possible cause | How to inspect |
| --- | --- | --- |
| Every call to `/counter` returns 1 | Cookie not sent, blocked, session not saved, or wrong namespace | Check `Set-Cookie`/`Cookie`, cookie jar, repository, and Redis/SQL |
| MVC JDBC works; WebFlux JDBC does not initialize a reactive session repository | `spring-session-jdbc` is a synchronous adapter | Choose reactive Redis/Mongo or a WebFlux-supported adapter |
| Using Redis, yet sessions vanish after Redis restart | Persistence/eviction/TTL or Redis failover | Check Redis config, TTL, `maxmemory-policy`, and durability |
| Two replicas do not share sessions | Different backend/namespace/serializer or cookie domain/path | Compare both instances' configs; verify reads/writes hit the same store key |
| Attribute deserialization error after deployment | Incompatible class/schema/serializer across versions | Use small DTOs, versioning, and a migration policy |
| MVC returns 500 when accessing session | DB down, connection pool exhausted, or missing schema | Check `SPRING_SESSION` tables, Hikari, SQL logs, and timeouts |
| High WebFlux latency despite low CPU | Blocking `block()` call or slow remote session dependency | Check event-loop stack traces, Redis latency, and `boundedElastic` |
| Cookie not sent behind HTTPS reverse proxy | Wrong `Secure`/`SameSite`/domain/path or forwarded scheme | Inspect browser Network, proxy headers, and cookie flags |
| Session data stays in DB past idle timeout | Cleanup job hasn't physically deleted rows yet | Check expiration metadata and cleanup schedule, not just row counts |
| Principal-based session lookup fails | Non-indexed repository or principal index not configured | Pick an indexed repository and configure Spring Security/events |
| Client still holds old session after logout | Missing server-side invalidation or lingering other cookies/tokens | Check server invalidation and cookie clearing |
| Added both Web and WebFlux and Session behaves unexpectedly | Boot selected Servlet application type | Identify the active stack from startup logs and dependency tree |

**Layered debugging workflow:**

1. **HTTP:** use DevTools or `curl -i -c jar -b jar` to confirm what cookie subsequent requests send and whether path/domain/secure match.
2. **Web stack:** does MVC receive `HttpSession` or does WebFlux receive `WebSession`? Which auto-configs did Boot activate?
3. **Repository:** is a `SessionRepository` or `ReactiveSessionRepository` bean actually present? Which backend was selected?
4. **Data store:** verify connectivity, namespace/key/table, serializer, TTL, and timeout errors.
5. **Application:** inspect where attributes are updated, logout, session fixation protection, and redirects.
6. **Multi-instance:** run identical code/config on two ports/replicas using one cookie jar to prove continuity; avoid sticky load balancing that masks whether instances actually share state.

## 15. Which features require an indexed repository?

Not all repositories offer the same secondary queries and lifecycle events. `FindByIndexNameSessionRepository` (synchronous) and other indexed repositories can support looking up sessions by principal; reactive indexed implementations offer equivalent APIs where supported by the version.

Features that commonly require this:

- Listing a user's active login sessions to allow “sign out other devices”.
- Limiting concurrent sessions per account.
- Receiving session deleted/expired events to close or clean up related resources.
- Analyzing per-user session lifecycles while protecting personal data.

**Practical limits:**

- Session events from Redis may rely on keyspace notifications and do not guarantee delivery like a durable event log.
- Default repositories do not provide all indexes; adding a `username` attribute to the session map does not automatically create a searchable principal index.
- With Spring Security, ensure the principal and security context are stored using a compatible mechanism.
- “Logout all sessions” is a security workflow involving non-session tokens, caches, WebSockets, synchronization, and cookie issuance states.

## 16. Exercises and store selection scenarios

**Question 1.** A Spring MVC app runs four replicas, already uses PostgreSQL, and does not want to operate Redis. Which repository should be considered? Can each replica use its own in-memory H2?

**Question 2.** A reactive WebFlux API uses `WebSession`, already has Redis, and handles heavy I/O requests. Choose `spring-session-jdbc` or `spring-session-data-redis`? Why?

**Question 3.** A team just added `spring-boot-starter-webflux` to an app that already had `spring-boot-starter-web` in order to use `WebClient`. Can they assume the reactive `WebSession` repository will be auto-configured?

**Question 4.** Two WebFlux instances on `localhost:8082` and `localhost:8083` share Redis. The cookie jar carries the right session ID, yet `visits` resets to 1 on the second instance. Name three factors to check.

**Question 5.** You just set `spring.session.timeout=20m`, yet see SQL rows still present after 21 minutes. Does that prove the session is still valid?

**Question 6.** Why shouldn't you put an entire `UserEntity` (with lazy collections, connections, or sensitive fields) into a Redis session instead of a small ID/DTO?

**Question 7.** A user opens two tabs and fires two requests incrementing `visits` simultaneously. Will the final value definitely increase by 2? If exact counting is required, where should it be stored?

**Question 8.** When implementing “log out of all devices”, why might storing attributes in the default Redis repository be insufficient?

**Suggested answers:**

1. `spring-session-jdbc` with `SessionRepository` for Servlet; use a shared PostgreSQL instance with proper schema, cleanup, and connection pooling. Per-instance in-memory H2 does not share data.
2. The **reactive** Redis repository with `ReactiveSessionRepository`; Spring Session JDBC does not provide an equivalent reactive adapter in this setup.
3. No. Spring Boot normally prefers Servlet when both MVC and WebFlux are on the classpath; verify `WebApplicationType` and beans.
4. Check cookie domain/path and sending; Redis namespace/backend/TTL; and serializer/session schema or mismatched instance configs.
5. No. Logical expiration and physical cleanup can occur at different times; check lookup validity and session metadata.
6. Reduces payload size and serialization cost, avoids version/class errors and data leaks, and decouples sessions from the persistence domain.
7. No, read-modify-write on a session is not atomic under concurrency. Use a datastore/operation with atomic support when exact counters are needed.
8. Requires querying by principal/session index and thorough invalidation, likely needing an indexed repository plus auth/token policies.

## 17. Technical takeaways

- **Spring Session is a server-side session management layer**, not an authentication algorithm, and does not turn cookie IDs into JWTs.
- **Servlet MVC:** `HttpSession` API, integrated via `SessionRepositoryFilter` and synchronous **`SessionRepository`**; Redis and JDBC are two common options.
- **Spring WebFlux:** `WebSession` API, integrated via `WebSessionManager` and **`ReactiveSessionRepository`**; reactive Redis is a classic choice, and reactive Mongo is also supported in compatible Boot 3.3 setups.
- **Do not mix adapters**: `spring-session-jdbc` does not automatically supply a `ReactiveSessionRepository`, and Spring Data R2DBC does not automatically create a Spring Session R2DBC repository.
- **Choose stores by requirements**: scale, failover, TTL, indexing/session events, serialization, cookies, security, performance, and operational complexity.
- **Verify empirically** using a cookie jar across multiple requests/instances and checking the repository, rather than merely checking for HTTP `200`.
- **Keep sessions small and governed**; account for network/DB latency, timeouts, concurrency, and version migration plans.

## 18. Official references

- Spring Boot 3.3 — Common Application Properties (Spring Session, Redis, JDBC, Servlet/Reactive session settings): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot 3.3 — Spring Session (in the 3.3 Web reference): https://docs.spring.io/spring-boot/docs/3.3.5/reference/htmlsingle/
- Spring Session 3.3 — HttpSession Integration: https://docs.spring.io/spring-session/reference/3.3/http-session.html
- Spring Session 3.3 — WebSession Integration: https://docs.spring.io/spring-session/reference/3.3/web-session.html
- Spring Session 3.3 — JDBC/Spring Boot Guide: https://docs.spring.io/spring-session/reference/3.3/guides/boot-jdbc.html
- Spring Session 3.3 — Redis/Spring Boot Guide: https://docs.spring.io/spring-session/reference/3.3/guides/boot-redis.html
- Spring Session 3.3 — Reactive Redis Indexed Session: https://docs.spring.io/spring-session/reference/3.3/configuration/reactive-redis-indexed.html
- Spring Session APIs (SessionRepository, ReactiveSessionRepository, CookieSerializer): https://docs.spring.io/spring-session/reference/api.html
