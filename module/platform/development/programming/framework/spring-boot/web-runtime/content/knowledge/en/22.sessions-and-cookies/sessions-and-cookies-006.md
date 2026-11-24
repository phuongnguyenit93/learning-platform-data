# In-Memory Sessions and the Impact of Server Restarts

In a Spring Boot application, an **HTTP session** allows the server to retain a small amount of state across requests from the same browser. For example, the first request writes a visitor's name or cart state into the session; on the next request, the browser sends back the **session ID** via a cookie, and the server uses that ID to look up the stored data. However, if the session lives only **in the memory of the Java process**, when the process terminates or the container/pod is replaced, that session data usually disappears. The cookie may still remain in the browser, yet it is only a lookup key, **not a backup copy of the session data**.

The immediate consequences are visible: users lose session-based login state, temporary shopping carts vanish, multi-step wizards must start over, or a request arrives carrying an old cookie whose ID the server no longer recognizes. **Do not conclude that every session storage strategy loses data on restart**: Spring Boot has persistence options for servlet containers, and Spring Session can store sessions in Redis/JDBC. This lesson clearly distinguishes the **default memory-only configuration** from those alternatives.

The content uses **Spring Boot 3.x, Spring MVC/Servlet, and Java 17+** for the main examples, and briefly compares against WebFlux `WebSession` at the end. Details for other Boot versions should be checked against their respective documentation.

## 1. Learning objectives

After this lesson, you will be able to:

- Distinguish browser cookies, session IDs, and server-side `HttpSession` contents.
- Explain how an embedded servlet container keeps sessions in memory and looks them up by ID.
- Use `HttpServletRequest.getSession(true)`, `getSession(false)`, `HttpSession.setAttribute/getAttribute`, `invalidate()`, and inspect stale sessions.
- Run a Spring Boot example and prove that session data survives across requests yet vanishes upon **server restart** under memory-only configuration.
- Recognize impacts on login, multi-step forms, shopping carts, load balancing, rolling deployments, and failover.
- Distinguish timeout, logout, restart, and cookie loss; understand why these events can share symptoms while having different root causes.
- Choose properly among in-memory sessions, local session persistence, Spring Session Redis/JDBC, and stateless designs, along with each option's operational requirements.
- Design tests, monitoring, and graceful handling when a session is lost.

## 2. Sessions and cookies: where does the data live?

HTTP is a protocol where each request carries its own information; a sequence of requests does not inherently form a remembered "login session". When an application needs state across requests, the server can create a **session**:

```text
Request 1: Browser                            Spring Boot / Tomcat
POST /session/start?visitor=Lan ----------------------->
                                            Create session ID S-abc...
                                            Memory map:
                                              S-abc... -> {visitor:"Lan", views:0}
                         <------------------------------
                         Set-Cookie: JSESSIONID=S-abc...
                         
Request 2: Browser                            Spring Boot / Tomcat
GET /session/status
Cookie: JSESSIONID=S-abc... -------------------------->
                                            Find S-abc... in memory
                                            Read visitor and views
                         <------------------------------
                         session=active; visitor=Lan

After server restart:
Browser still holds JSESSIONID=S-abc...
GET /session/status ------------------------------->
                                            New memory map: empty
                                            Cannot find S-abc...
                         <------------------------------
                         session=missing
```

This diagram is illustrative only; real session IDs are random values that should never be disclosed. With standard embedded Tomcat servlets, the session cookie is named **`JSESSIONID`** by default. With **Spring Session**, the cookie may be **`SESSION`**, depending on `HttpSessionIdResolver`/`CookieSerializer` and configuration. With default WebFlux, `CookieWebSessionIdResolver` uses `SESSION`. Therefore, never hardcode tests assuming all projects share one cookie name.

| Component | Where does it live? | What does it contain? | Survives app restart? |
| --- | --- | --- | --- |
| Session ID cookie | Browser, sent in HTTP `Cookie` | Usually an opaque ID | May **still exist**, depending on cookie lifetime/browser |
| In-memory `HttpSession` | Process/Servlet container memory | Map of attributes keyed by ID | By default **gone** after process restart |
| Java object stored in session | Inside the session store | E.g., `cartId`, `locale`, temporary objects | Depends on store and serialization/persistence |
| Business database | Separate data service | Orders, users, durable state | Independent of web instance restarts if DB remains |
| Spring Session Redis/JDBC | Session store external to the app | Session attributes + expiration/metadata | Can resume after app restart if store remains, data is unexpired, and compatible |
| Stateless token cookie | Browser/client | Signed or reference token depending on design | Independent of in-memory `HttpSession`, depends on validation, expiry, and revocation |

**A cookie is not the Session.** The `JSESSIONID` cookie typically holds only an identifier. You cannot "restore a shopping cart" merely by keeping the cookie if the corresponding data existed only in freed memory. Conversely, deleting the cookie can prevent the browser from finding a session that is still alive in the store, even before server-side expiration.

## 3. How does HttpSession work in Spring MVC/Servlet?

Spring MVC uses the Servlet API. Core methods of `jakarta.servlet.http.HttpServletRequest` and `jakarta.servlet.http.HttpSession` are:

```java
HttpSession created = request.getSession(true);  // Create if absent
HttpSession maybe = request.getSession(false);   // Lookup only, do not create
created.setAttribute("cartId", "CART-42");       // Put data into session
Object value = created.getAttribute("cartId");  // Read attribute back
created.removeAttribute("cartId");              // Remove an attribute
created.invalidate();                           // Invalidate session
```

This is a **snippet** inside a handler/servlet with `HttpServletRequest request`, not a complete class. `request.getSession()` is equivalent to the mode that may create a session. When you only want to check “does the user already have a valid session?”, use **`getSession(false)`** to avoid accidentally generating huge numbers of sessions for public requests.

Two other useful APIs:

- `request.getRequestedSessionId()` reports the session ID the client supplied, if any; **it does not mean the ID is valid**.
- `request.isRequestedSessionIdValid()` reports whether the client-supplied ID corresponds to a currently valid server-side session for this request.

For example, when a browser sends a stale cookie after a server restart: `getRequestedSessionId()` may still return a value while `isRequestedSessionIdValid()` returns `false`. A request with no valid cookie also yields `getSession(false) == null`, so checking null alone cannot distinguish “first visit”, “timeout”, “logout”, or “restart”. Giving users an exact explanation requires lifecycle tracking, observability, and context.

### 3.1. Session attributes live in container memory

Under memory-only servlet session configuration, the container keeps a session manager holding `HttpSession` instances and their attributes. The session manager enforces timeouts and removes sessions after prolonged inactivity. This is **memory inside the server process**, not the browser's cookie store.

If attributes are large objects, growing session counts can pressure heap and GC. Storing entire order lists, 10 MB images, or large query results per session causes RAM consumption to scale roughly with active users and per-session payload size. Unexpired sessions continue occupying memory per container policy.

### 3.2. Sessions are not the entirety of user state

Data that must **persist long-term**—paid orders, account details, work records, and shopping carts recoverable after days—should normally reside in a database or durable store keyed by user/cart ID. The session can hold just an **identifier** referencing that data. When a session is lost, the app can help the user sign back in and reload their data from the database instead of losing everything kept solely in session memory.

## 4. Boot 3.x defaults: why does a restart lose sessions?

Spring Boot 3.3 provides the following servlet session settings (relevant keys excerpted):

```properties
server.servlet.session.persistent=false
server.servlet.session.timeout=30m
```

According to Boot 3.3's official properties reference, `persistent` defaults to **false** and the default timeout is **30 minutes**. The timeout can be reconfigured. The timeout value is the maximum inactivity interval per container rules; it **does not** guarantee a session survives a full 30 minutes across server restarts, pod terminations, or store wipes.

When the application stops and a new process starts:

1. The old process's heap and session map are gone.
2. The new embedded container initializes a fresh empty in-memory session manager/store.
3. The browser may continue sending the old session ID cookie.
4. The old ID is not found in the new session manager, so the server-side session is not recovered.
5. If code calls `getSession(false)`, the result is `null`. If code calls `getSession(true)`, the server creates a brand-new session and returns a new cookie.
6. Prior attributes such as `visitor`, `cartId`, form progress, or authentication context attached to the old session do not automatically migrate to the new session.

### 4.1. Types of restarts to distinguish

| Scenario | What happens to memory-only sessions |
| --- | --- |
| Stopping with Ctrl+C and re-running `bootRun` | Sessions from the old instance are lost |
| Deploying a new JAR version launching a new JVM | Local sessions from the old instance are lost |
| Container/pod deleted and recreated | Local sessions are lost; volumes do not automatically preserve Java heap |
| Process crash / OOM kill | Local sessions are lost and cleanup may not run cleanly |
| Rolling restart across multiple replicas | Each replica loses its own sessions when replaced, unless store/routing is designed accordingly |
| Restarting only the browser | May lose session cookies if the cookie lacks long-term expiry; even if server keeps data, client may lose the ID |
| Brief network blip without server restart | Does not necessarily lose the session, depending on timeout and connectivity |
| External Redis/JDBC store stays alive | Can resume sessions via the new instance, depending on timeout, config, and store reachability |

**Important exception:** Spring Boot and servlet containers have options to **persist sessions to disk** across stop/start cycles, so saying “all HttpSessions are always lost on restart” is false. What is true is that **under the default memory-only model, there is no mechanism preserving sessions across restarts**.

## 5. Complete Java 17+ example: creating, reading, and losing a session on restart

The example runs a standalone Spring Boot MVC application with three core functions: creating a session, incrementing a counter, and inspecting an existing session. It intentionally avoids real login/checkout so session lifecycle is isolated from authentication business logic.

### 5.1. Create the project

Use Spring Initializr to generate a **Spring Boot 3.x**, **Java 17+**, Gradle/Groovy app with the **Spring Web** (Servlet MVC) dependency. In the generated `build.gradle`, the key section is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

This is the **dependencies block**, not a full Gradle file; Initializr provides plugins, repositories, Spring Boot version, and the Gradle Wrapper. Boot 4 uses a different MVC starter name than Boot 3, so do not mix versions across the same project.

Create file **`src/main/java/demo/SessionMemoryApplication.java`**:

```java
package demo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SessionMemoryApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionMemoryApplication.class, args);
    }
}

@RestController
@RequestMapping(
        path = "/session",
        produces = MediaType.TEXT_PLAIN_VALUE
)
class SessionController {

    @PostMapping("/start")
    public String start(
            @RequestParam(defaultValue = "Lan") String visitor,
            HttpServletRequest request) {

        HttpSession session = request.getSession(true);
        session.setAttribute("visitor", visitor);
        session.setAttribute("views", 0);
        return "session=started\n";
    }

    @GetMapping("/status")
    public String status(HttpServletRequest request) {
        HttpSession session = request.getSession(false);

        if (session == null) {
            return "session=missing\n";
        }

        String visitor = (String) session.getAttribute("visitor");
        Integer views = (Integer) session.getAttribute("views");

        return "session=active\n"
                + "visitor=" + visitor + "\n"
                + "views=" + views + "\n";
    }

    @PostMapping("/visit")
    public String visit(HttpServletRequest request) {
        HttpSession session = request.getSession(false);

        if (session == null) {
            return "session=missing\n";
        }

        Integer previous = (Integer) session.getAttribute("views");
        int next = previous == null ? 1 : previous + 1;
        session.setAttribute("views", next);
        return "views=" + next + "\n";
    }

    @PostMapping("/end")
    public String end(HttpServletRequest request) {
        HttpSession session = request.getSession(false);

        if (session == null) {
            return "session=missing\n";
        }

        session.invalidate();
        return "session=invalidated\n";
    }
}
```

Only `SessionMemoryApplication` is `public`, so having two classes in one Java file is valid. `SessionController` in the same `demo` package is discovered by Spring Boot component scanning. Every endpoint returns plain text; Thymeleaf is unnecessary because `@RestController` writes directly to the response body.

Create `src/main/resources/application.properties`:

```properties
server.port=8080
server.servlet.session.persistent=false
server.servlet.session.timeout=15m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

`persistent=false` is set explicitly so the experiment yields consistent results even if someone changes defaults later. `timeout=15m` is the maximum inactivity window, not a guaranteed survival time. For local HTTP, `server.servlet.session.cookie.secure=true` is omitted because browsers restrict `Secure` cookies to HTTPS; production uses TLS and matching cookie security settings.

### 5.2. Run the program

From the project directory:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

If another app already occupies port 8080, stop it or change `server.port`. Once the server is up, open a second terminal to send HTTP requests. Standalone `javac SessionMemoryApplication.java` will not run because Spring/Servlet dependencies are needed; the Gradle Wrapper supplies the classpath.

### 5.3. Before creating a session

```bash
curl -s http://localhost:8080/session/status
```

**Exact** body from the example endpoint:

```text
session=missing
```

In this request `getSession(false)` only checks and does not force creating a new session.

### 5.4. Create a session and save the cookie to a file

On Linux/macOS, use `curl`:

```bash
curl -i -c session.cookies -b session.cookies \
  -d 'visitor=Lan' http://localhost:8080/session/start
```

On Windows PowerShell, run on a single line:

```powershell
curl.exe -i -c session.cookies -b session.cookies -d "visitor=Lan" http://localhost:8080/session/start
```

Returned body:

```text
session=started
```

The response headers include `Set-Cookie` containing a new `JSESSIONID` (the exact ID varies across runs). `-c session.cookies` saves the cookie jar; `-b session.cookies` sends stored cookies back. **Do not publish or put real session IDs from cookie jars into docs or logs** because they act like temporary credentials if real authentication is enabled.

### 5.5. Read the session again and increment visits

```bash
curl -s -b session.cookies http://localhost:8080/session/status
```

Body:

```text
session=active
visitor=Lan
views=0
```

Call:

```bash
curl -s -b session.cookies -X POST http://localhost:8080/session/visit
```

Body:

```text
views=1
```

Reading `/session/status` again with the same cookie shows `views=1`. Calling `/session/status` with a **different** cookie jar or no cookie returns `session=missing`, because that browser/client does not present the created session ID.

### 5.6. Stop the server, restart it, and reuse the same cookie jar

Stop the running process with Ctrl+C, then start it again:

```bash
./gradlew bootRun
```

Do not delete `session.cookies` or change the port/context path during the test. Once the new server is ready:

```bash
curl -s -b session.cookies http://localhost:8080/session/status
```

Expected body:

```text
session=missing
```

This confirms the central point: **the cookie jar still holds the old ID, yet the in-memory map in the new server does not contain that session**. Sending `POST /session/start` right after restart creates a new session with a new ID and returns a new `Set-Cookie`; if the new cookie is not saved, later requests may keep sending the old ID.

Because of `getSession(false)`, the app does not create a session just to check status. Had `getSession(true)` been used inside `status`, a post-restart request carrying the stale cookie would **silently create a new empty session**; to the user, this can look like “my cart reset to 0” instead of a clear error.

### 5.7. Distinguishing explicit logout from restart

While the app is running and you have a valid cookie:

```bash
curl -s -b session.cookies -X POST http://localhost:8080/session/end
```

Body:

```text
session=invalidated
```

`HttpSession.invalidate()` actively invalidates the session on the server. The browser may still retain the old ID cookie until replaced or cleared; the server will no longer recognize that ID as a valid session. Real login systems should also expire/delete cookies appropriately and use Spring Security's logout mechanisms rather than treating `/end` as a complete authentication logout.

### 5.8. What conditions does this example's outcome depend on?

- A single memory-only Spring Boot JVM; no Spring Session, custom session store, or disk persistence.
- `server.servlet.session.persistent=false` to guarantee no disk restoration.
- Reusing the same cookie jar across HTTP requests and across the **server** restart; not restarting the browser, which might discard session cookies itself.
- No Spring Security or other middleware auto-creating sessions.
- Simple test traffic, without multiple servers behind a load balancer.

If conditions differ (such as Redis Spring Session), the post-restart result may be `session=active`; that demonstrates a more durable store, not a flaw in the example.

## 6. Not every lost session is caused by a restart

Several situations can cause a request to miss its session:

| Cause | Symptom | Diagnostic hint |
| --- | --- | --- |
| Server/JVM restart | Sessions vanish en masse on the replaced instance | Correlate startup timestamps, deployments/pod restarts |
| Session idle timeout | Only an inactive user loses their session | Check `server.servlet.session.timeout`, last access |
| Logout/`invalidate()` | Lost immediately after a logout action | Trace logout flow, cookie expiration, server logs |
| Browser cleared cookies / switched browser or profile | Client does not send the old ID | Inspect `Cookie` header via client/DevTools |
| Misconfigured cookie domain/path/SameSite/Secure | Cookie omitted on certain routes or origins | Check domain, path, HTTPS, and site context |
| Routed to another instance in a cluster | Session resides only in the old instance's RAM | Check routing/affinity and session store |
| Load balancer failover | Requests shift nodes when the old node dies | Check health/routing and local memory |
| Redis/JDBC TTL expired or store error | External session becomes unreachable | Check datastore/TTL/connectivity and error metrics |
| Session ID rotated upon authentication | Pre-login ID is no longer valid | Check session fixation protection |
| Serializer/class version mismatch | Store still has bytes, yet attribute fails to deserialize | Check serializer/schema compatibility errors |

A `JSESSIONID` still present in a request proves only that the browser sent an ID. It **does not** prove the user holds a valid session or that the server recovered data. Never automatically tell users “you were logged out because the server restarted” unless the application has concrete proof of the cause.

### 6.1. Timeout is not cookie Max-Age

`server.servlet.session.timeout` controls the inactivity lifecycle of the **server-side session**. `server.servlet.session.cookie.max-age` controls whether the browser retains the cookie for a set duration; these two limits are distinct. A cookie with a `Max-Age` longer than session lifetime cannot revive a server-expired session. Conversely, a browser deleting a session cookie can leave the session alive in memory while the client has no ID to locate it.

Timeout is typically evaluated against server-side session activity and access timestamps, rather than a fixed clock starting at login. For strict security requirements, consider both **idle timeout** and **absolute lifetime** if needed, rather than letting activity extend sessions indefinitely.

## 7. Impact on UI and business workflows

### 7.1. Users “logged out” after deployment

In apps using Spring Security form login, authentication is commonly persisted via a security context bound to the session under standard config. When local sessions are lost, the next request finds no authentication; users may be redirected to the login page or receive 401/403 depending on security config, endpoint, and client. **Never promise every app returns 302**: the response depends on the authentication/authorization setup.

When Spring Security is configured as stateless (e.g., an API using bearer tokens without storing auth in `HttpSession`), a server restart **does not automatically** invalidate token state just because in-memory sessions vanish; token validity depends on verification, expiry, signing keys, and revocation.

### 7.2. Shopping carts and multi-step workflows

If a shopping cart or multi-step wizard exists only in session memory, a restart wipes its contents. For important carts, one option is persisting data in a database tied to an account ID or durable cart ID while the session holds only a short identifier. After logging back in, the user can recover the data and continue.

If a long form contains sensitive data, clarify policies for autosave, TTL, deletion, and consent; do not assume session memory is safe and durable. Losing a session can also invalidate session-bound CSRF tokens, causing open tabs to fail on submit after a restart. Prompt users to reload the form and avoid partially executing side effects.

### 7.3. Multiple concurrent tabs

Multiple tabs in the same browser usually share session cookies for matching domain/path, so they can share the same `HttpSession`. If one tab calls logout/`invalidate()` or the server restarts, another tab may continue displaying stale UI until its next request. Seeing “logged in” on screen **does not** prove the server still holds authentication state.

### 7.4. Interrupted in-flight requests

A server restart can sever in-flight requests regardless of where sessions are stored. Moving sessions to Redis does not magically complete or roll back an interrupted HTTP transaction. For order creation or payments, use database transactions, idempotency keys, and status checks before retrying. Session persistence addresses only **state across requests**, not business operation durability.

## 8. Multiple replicas, load balancing, and rolling deployments

Suppose a system runs two Spring Boot instances A and B behind a load balancer:

```text
Browser: Cookie JSESSIONID=S-100
          |
          v
      Load balancer
       /         \
      v           v
 Instance A     Instance B
 Memory:        Memory:
 S-100 ->       (does not have S-100)
  {visitor:Lan}
```

If the first request lands on A to create the session, and the next lands on B, B cannot find `S-100`. This can happen even **without a restart** whenever the load balancer does not maintain affinity.

### 8.1. How much does sticky sessions solve?

**Sticky sessions** (session affinity) try to route requests for the same client/session back to the same instance. They can reduce session loss caused by node hopping while the node stays alive, yet **offer no protection** when instance A restarts, a pod is replaced, autoscale-in occurs, or a node crashes. Affinity also couples users to specific instances, complicating scale-out and rolling deployments.

| Scenario | Sticky + memory-only | Shared Redis/JDBC store |
| --- | --- | --- |
| Two consecutive requests, A and B both healthy | Can work when consistently routed to A | Both apps can read the same session from the shared store |
| A crashes and browser fails over to B | Session on A is lost | Can continue if the store remains up and session is unexpired |
| Rolling deploy replaces A | Session on A is lost when pod terminates | New app instance can read the session from the external store |
| Redis store wiped/restarted without persistence | Redis not used, so A retains session while alive | Sessions may be lost due to store data loss |
| New version changes session attribute class incompatibly | Each node keeps separate memory; migration risk still applies | Deserialization/compatibility must be solved cluster-wide |

Understand that **adding more replicas does not turn memory-only sessions into distributed sessions**. Choosing a shared store requires aligning application versions/serialization, TTLs, cookies, secrets, networking, and health policies.

### 8.2. Readiness and graceful shutdown

Readiness probes keep new requests away from unready or terminating instances, while graceful shutdown gives in-flight requests time to finish. Neither **preserves a Java heap session** once the process exits. When users must stay logged in across rolling deployments, you need an out-of-process session store or an authentication mechanism independent of local memory.

## 9. Option 1: keep using in-memory sessions

Memory-only makes sense when:

- Learning projects, small internal apps, or prototypes where losing sessions on restart is acceptable.
- Ephemeral, low-value state that can be rebuilt easily.
- Single instance, low traffic, no cross-node session sharing required.
- Operational simplicity is prioritized and UX accepts re-login on deploy.

Pros: no Redis/JDBC session store needed, fast memory access, fewer moving parts. Cost: sessions vanish on JVM death, weak failover, memory footprint grows with user count and attribute size, unsuitable when logins must survive deployments.

Do not try to “fix” this with huge timeouts: long timeouts keep objects on the heap longer without saving them across restarts. Minimize attribute size, set timeouts per security risk, and avoid storing files/blobs or data recoverable from the database.

## 10. Option 2: persistent servlet sessions on disk

Spring Boot 3.x has properties for servlet container session persistence, for example:

```properties
server.servlet.session.persistent=true
server.servlet.session.store-dir=/path/to/durable/sessions
```

This is an **optional configuration example**, not to be combined with the memory-only demo in Section 5. The path must be a valid directory for the runtime and container. Actual behavior depends on the embedded container (Tomcat/Jetty/Undertow), clean stop/start timing, attribute serializability, read/write permissions, app version, and file lifecycle. With Tomcat, clean shutdown persistence can serialize sessions to files and reload them on startup; non-`Serializable` objects, crashes, or mismatched configs can prevent clean recovery.

**Do not treat local disk persistence as a default HA session solution**:

- A pod/container's local disk is normally wiped on instance replacement unless durable storage is attached.
- Node A's local directory is not automatically shared with Node B.
- Crashes/power losses are not graceful shutdowns.
- Deserializing objects written by older app versions can fail when classes change.
- Session files must be secured because they can contain sensitive data.

This option can serve restarts of the **same instance with durable storage** under clear constraints, whereas failover and multi-replica scaling generally favor a shared session store. Boot defaults to `server.servlet.session.persistent=false`, so never assume Tomcat automatically saves sessions in every Boot app.

## 11. Option 3: Spring Session backed by Redis

**Spring Session** provides an externalized session storage mechanism outside the servlet container. For Servlet MVC apps with Redis, Spring Session replaces the `HttpSession` implementation with a Redis-backed store; application code continues calling `HttpSession.setAttribute/getAttribute`. Spring Boot 3.x auto-configures it when the proper modules and Redis connection are present.

Diagram:

```text
                Browser
                   |
               SESSION cookie
                   |
                Ingress
                 /   \
                v     v
             Pod A   Pod B
                \     /
                 \   /
                 Redis
             Session store
                S-1 -> {cartId:42, ...}
```

If Pod A is replaced, Pod B can look up the same session ID in Redis—**provided** Redis stays up, the session hasn't expired, apps share compatible namespaces/configs, and attributes deserialize properly. The Spring Session cookie name may differ from the container default; Spring Session Redis guides commonly show `SESSION`. Always inspect actual responses.

### 11.1. Dependencies for Boot 3.x

Keep `spring-boot-starter-web`, and add Spring Session Redis and the Redis client. Gradle example:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.session:spring-session-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

This is a **configuration snippet** for a project using the Spring Boot 3.x BOM; not a full setup with a Redis server. Spring Session 3.x documentation uses `org.springframework.session:spring-session-data-redis`; Spring Boot 4.x introduces dedicated session starters, so do not mix dependency names from a different major version.

### 11.2. Redis connection and session timeout

Example `application.properties`:

```properties
spring.data.redis.host=localhost
spring.data.redis.port=6379

# Spring Session timeout in Boot 3.x
spring.session.timeout=15m
spring.session.redis.namespace=demo:sessions
```

A reachable, running Redis server is required. Production apps must configure authentication, TLS, network policies, and secret management; never store plaintext passwords in source control. Modules, drivers, and timeout properties must match the Spring Boot version.

If only **one** Spring Session store module is on the classpath in Boot 3.3, Boot auto-selects it; having multiple store modules without understanding precedence can select the wrong store. Verify via startup logs, Redis keys/TTLs, and real reload behavior.

### 11.3. What conditions are required for sessions to survive restarts?

- Redis does not lose data during the app restart; if Redis also restarts without persistence/replication, sessions can still be lost.
- Sessions have not exceeded TTL/idle timeout and clocks/time policies align.
- Session attribute formats remain serialization/deserialization-compatible across app versions.
- Cookie domain/path and cookie names are consistent across instances.
- Users still present the right cookie or session ID mechanism.
- Redis has sufficient capacity and does not evict keys prematurely due to memory pressure.
- The session store is secured, monitored, and backed up/HA-configured commensurate with criticality.

Avoid putting full entity graphs, sensitive tokens, or fragile classes into sessions. Store small values (user ID, locale, cart ID) with explicit namespaces/versioning. **Spring Session does not turn Redis into permanently durable storage by itself**; designing Redis persistence, TTL, backups, failover, and app policies remains your responsibility.

### 11.4. Consequences when Redis fails

A web app that previously stored sessions in RAM now depends on Redis on every stateful request. If Redis becomes unavailable, session-dependent requests can stall or fail depending on config. You need timeouts, capacity planning, Redis latency/availability metrics, and a failure plan. Simply “adding Redis” without operating Redis properly can trade **pod restarts losing sessions** for **a session store single point of failure**.

## 12. Option 4: Spring Session JDBC

Spring Session can also use a **relational database** to store sessions. In Boot 3.x, you can add the Spring Session JDBC module and configure a `DataSource`/driver and schema:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.session:spring-session-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
```

This is a **Gradle snippet**; you still need `spring.datasource.url`, securely configured credentials, a real PostgreSQL instance, and the session schema. Demos may use Spring Session JDBC's schema initializer for the matching version; production should manage migrations via Flyway/Liquibase with controlled DDL permissions rather than leaving auto-create enabled. Consult Boot 3.3 and Spring Session JDBC docs for exact table/schema details.

**Trade-offs:** a database shares sessions across app instances, yet increases read/write queries, connection usage, expired-session cleanup load, lock contention, and storage growth. For high session traffic, size connection pools, optimize cleanup/TTL queries and indexes, and never assume “durable JDBC” requires no capacity planning.

## 13. Option 5: separating sessions from business data or using stateless auth

There are two separate questions:

1. Do users need to **stay authenticated** across restarts?
2. Do users need **business data** preserved across restarts?

They can be solved at two different layers. For instance, authentication can use Redis sessions while carts live in the database keyed by cart ID. Or APIs can use stateless bearer-token auth while business data stays in the database. A valid signed token can be verified on a new instance if signing keys, expiry, and validation policies align; however, logout/revocation, rotation, and token theft require dedicated strategies. **“JWT” does not automatically equal security, nor does it store carts or server-side state by itself.**

| Option | Pros | Limitations |
| --- | --- | --- |
| In-memory `HttpSession` | Simple, fast, no external store | State lost on process restart/failover |
| Servlet container disk persistence | Can recover across restarts on the same storage under right conditions | Not HA by default; requires serializability and durable disk |
| Spring Session + Redis | Shares sessions across replicas; fits high traffic | Introduces Redis availability/TTL/eviction/serialization concerns |
| Spring Session + JDBC | Shares and persists sessions in SQL DB | Database throughput, schema, cleanup, and connection costs |
| Stateless token auth + business DB | Web instances hold no auth sessions on heap | Token expiry/revocation, CSRF if cookie-borne, key management |
| Sticky sessions + local memory | Avoids hopping nodes while nodes stay healthy | Still loses sessions when a node is replaced or crashes |

Choose based on SLOs, tolerance for re-login, instance count, traffic, infrastructure cost, security requirements, and deployment model. Never swap session stores to paper over a business bug that actually needs transactions or real persistence.

## 14. WebFlux: WebSession faces similar lifecycle issues

**Spring WebFlux** applications do not use Servlet `HttpSession` on reactive processing paths. They use `org.springframework.web.server.WebSession`, accessed asynchronously via `ServerWebExchange.getSession()`. Spring Framework includes the map-based `InMemoryWebSessionStore`; with this in-memory store, app process restarts also lose sessions. `CookieWebSessionIdResolver` defaults to the cookie name `SESSION`.

The snippet below applies only to a **separate WebFlux project**, not the MVC project in Section 5:

```java
@GetMapping("/reactive/visit")
public Mono<String> visit(ServerWebExchange exchange) {
    return exchange.getSession().map(session -> {
        Integer old = session.getAttribute("views");
        int next = old == null ? 1 : old + 1;
        session.getAttributes().put("views", next);
        return "views=" + next;
    });
}
```

This is a **snippet** inside a reactive controller with imports for `Mono`, `ServerWebExchange`, and `@GetMapping`; not standalone runnable. Writing an attribute can start the session per the WebFlux API. If sessions must survive restarts/replicas, Spring Session supports a reactive Redis store with an appropriate `WebSessionManager`; do not assume you can reuse Servlet `HttpSession` inside WebFlux.

Comparison:

| MVC / Servlet | WebFlux |
| --- | --- |
| `HttpSession` | `WebSession` |
| `HttpServletRequest.getSession(false)` | `ServerWebExchange.getSession()` returning `Mono<WebSession>` |
| Cookie commonly `JSESSIONID` with container | Cookie resolver commonly `SESSION` |
| Embedded container local session manager | `InMemoryWebSessionStore` when no external store is configured |
| Spring Session can replace the `HttpSession` store | Spring Session can provide a reactive session store |
| Memory-only sessions lost on restart | Memory-only `WebSession` also lost on restart |

**Do not mix starters and APIs arbitrarily**: the sample app above uses Spring MVC with `spring-boot-starter-web`, whereas WebFlux requires `spring-boot-starter-webflux` and reactive APIs.

## 15. Security of session IDs and stored session data

### 15.1. Session IDs act like credentials

If a session is tied to an authenticated user, anyone who obtains that ID can try to impersonate the user unless other controls prevent it. Never place session IDs in URLs, public logs, analytics, HTTP error bodies, or screenshots. Session cookies need policies for:

- **HttpOnly**: browser JavaScript cannot read the cookie via `document.cookie`; XSS defenses are still required.
- **Secure**: send cookie only over HTTPS; pair with TLS deployment and proper reverse proxy headers.
- **SameSite**: restrict browser cookie sending in cross-site contexts; pick `Lax`/`Strict`/`None` per need, with `None` usually requiring `Secure`.
- **Domain/Path**: restrict cookie scope to necessary hostnames/routes, avoiding overly broad scope.
- **Timeout**: limit idle sessions and absolute lifetimes if business policy requires.

In Spring Boot Servlet, properties include `server.servlet.session.cookie.http-only`, `.secure`, `.same-site`, `.domain`, `.path`, and `.max-age`. When using Spring Session, check whether it uses its own cookie serializer/ID resolver before relying solely on container properties.

### 15.2. Session fixation

If a session ID remains unchanged across authentication in insecure setups, an attacker may force a victim to use an ID known to the attacker (*session fixation*). Spring Security supports rotating the session ID upon login via appropriate session fixation protection. Never implement real login with `session.setAttribute("loggedIn", true)` from a demo and ship it to production. If implementing custom auth flows, use a security framework and rotate IDs on login per Servlet/Spring Security contracts.

### 15.3. Sensitive data and serialization

Avoid storing passwords, unnecessary access tokens, full personal profiles, or objects holding connections/resources in sessions. With external stores or disk persistence, objects may require serialization, and version changes can cause restore errors or unintended exposure. Keep session attributes minimal, simple, TTL-bounded, and reconstructible; enforce store encryption, ACLs, and retention policies.

### 15.4. CSRF and cookie authentication

Cookies can be sent automatically by browsers with requests. When authentication relies on cookies/sessions, state-changing requests need proper CSRF protection (such as Spring Security CSRF). Moving to Redis does not solve CSRF; moving to tokens is also not automatically safe if tokens reside in cookies sent automatically. When a session is lost after restart, old CSRF tokens may no longer match: UIs should guide users to refresh/reload instead of silently resubmitting critical operations.

## 16. Designing behavior when a session is lost

### 16.1. User experience

When a session is required and no valid session remains:

- Server-rendered pages can redirect to login or a page explaining the session expired.
- APIs should return status codes matching the authentication/authorization contract—for instance 401 if unauthenticated—never an unhandled 500 just because a session disappeared.
- For multi-step forms, save drafts in a durable store with proper permissions and TTL if recovery is needed.
- Before retrying a transaction, check transaction/idempotency status to prevent duplicate side effects.
- Avoid claiming “the server just restarted” without evidence; a message like “Your session has expired or is no longer valid, please sign in again” is usually more accurate.

In Section 5's sample API, `GET /session/status` returns plain text `session=missing` for learning. It is **not** a production authentication/authorization endpoint; real apps must use Spring Security and appropriate HTTP statuses.

### 16.2. Avoid creating unnecessary sessions

If every public page request calls `getSession(true)`, the server can create sessions even for bots and health checks, bloating heap usage. Use `getSession(false)` when merely checking for an existing session; create sessions only when state is genuinely required. For health probes, static assets, or stateless APIs, avoid creating sessions needlessly.

### 16.3. Do not use sessions for long-running processes

Background jobs, lengthy uploads, or report exports should use a task ID and durable status in an appropriate database/queue. When a web instance restarts, workers or jobs can continue based on that durable store; sessions carry no guarantee for completing interrupted work. If users must log back in, verify task ownership by identity rather than relying solely on the old session ID.

## 17. Monitoring and testing session restarts in deployed environments

Valuable tests to include:

1. **Normal flow:** create session via request, store cookie, read attributes, and increment counter while the process stays up.
2. **Restart:** stop and restart the exact JVM in memory-only mode, send the old cookie, confirm the session is missing, and create a new session cleanly.
3. **Timeout:** set a short timeout in a test environment, send no requests past the timeout, verify the server invalidates the session.
4. **Logout:** call `invalidate()`, resend the old cookie, verify old data is gone.
5. **Two-node:** send first request to A and second to B; confirm memory-only does not share state without affinity.
6. **Rolling deploy:** check whether users are logged out during pod replacement; compare against shared store behavior.
7. **Redis/JDBC failure:** simulate store timeout/unavailability, ensuring bounded failure behavior and clear alerts.
8. **Serializer upgrade:** when changing app versions, test reading sessions written by the old version before rollout.
9. **High concurrency:** active session count, memory footprint/GC, session creation/expiration rates, and cookie cardinality.
10. **Security:** `HttpOnly`/`Secure`/`SameSite`, cookie scope, session ID rotation, logout, CSRF, and unauthorized requests.

### 17.1. Metrics and logs to track

- Process restart counts, JVM uptime, container/pod replacements, deployment timestamps.
- Active session count, session creation/expiration/invalidation rates if exposed by container/store.
- Heap usage, GC pauses, session object sizes, or retention hotspots if memory-only.
- Redis/JDBC latency, errors, availability, eviction, and TTL/expired keys if using an external store.
- 401/302-to-login rates or “session expired” error rates following deployments.
- User-visible error rates during forms, carts, or checkout.
- Never log raw session IDs or sensitive session attributes; use separate correlation IDs and controlled aggregate metrics.

Do not judge health solely by the count of `JSESSIONID` cookies sent: browsers keep sending stale IDs after server-side sessions vanish. What matters is **whether IDs resolve valid state** and **whether the app handles missing sessions cleanly**.

## 18. Common misconceptions and corrections

| Misconception | Explanation |
| --- | --- |
| “If the cookie exists, the session exists.” | The cookie holds only the ID; server-side storage may have lost the data. |
| “A 30-minute timeout means sessions survive restarts for 30 minutes.” | Timeout is an inactivity policy, not process-restart durability. |
| “Adding sticky sessions ensures logins survive deploys.” | When the node holding the session dies or is replaced, affinity cannot recover that node's RAM. |
| “Spring Boot always saves sessions to disk because it uses Tomcat.” | Boot 3.3 defaults to `server.servlet.session.persistent=false`. |
| “Setting cookie Max-Age to one month keeps logins alive for a month.” | Server-side sessions can expire, be invalidated, or vanish on restart earlier; persistent auth requires dedicated design. |
| “Redis guarantees sessions are never lost.” | Redis still has TTL, eviction, outages, restart/persistence modes, and serialization constraints. |
| “JWT stores the cart and eliminates all server state.” | JWT is only a token format; business data still needs persistence, and expiry/revocation bring trade-offs. |
| “Every 401 after a deploy means sessions were lost.” | Could also be invalid tokens, cookie scope, security config, clocks, store issues, or authorization changes. |
| “Starting a session on every GET is harmless.” | Session objects, cookies, heap, and expiration tracking add significant cost at scale. |
| “Storing full JPA entities in sessions is safe and convenient.” | Can cause stale data, serialization failures, memory pressure, and data leakage. |
| “Switching to Spring Session preserves in-flight HTTP requests.” | Session stores persist state between requests; interrupted requests/transactions need their own mechanisms. |
| “Logout only needs cookie deletion.” | Server sessions must be invalidated and auth/security context cleaned up per security contract; cookie and server state are separate layers. |

## 19. Practice exercises

**Question 1.** A browser holds `JSESSIONID=abc` and the server just restarted in memory-only mode. Does the lingering cookie keep the user logged in?  
**Answer:** No. The new server no longer has the matching session map; the old cookie cannot restore authentication or session attributes.

**Question 2.** A handler only wants to check if a session exists, yet calls `request.getSession()`. What is the issue?  
**Answer:** That call can create a new session. Use `request.getSession(false)` to inspect without creating one.

**Question 3.** A deployment runs 4 pods with sticky sessions; a user is on Pod A. When A is deleted, is the cart in local `HttpSession` preserved?  
**Answer:** No, data in A's memory is lost; sticky sessions do not replicate state to other pods.

**Question 4.** After adding Spring Session Redis and restarting the app, users still lose their sessions. Name at least three things to check.  
**Answer:** Whether Redis still holds the data/TTL, whether apps share the same Redis namespace, whether cookie name/domain/path still match, whether session attributes deserialize cleanly, and whether Redis suffered eviction or restarted without persistence.

**Question 5.** Why shouldn't an important shopping cart live solely in in-memory `HttpSession`?  
**Answer:** Sessions can be lost to restarts, timeouts, or failover and lack durable data contracts; business data should live in a database keyed by a secure identifier.

**Question 6.** If `server.servlet.session.timeout` is raised from 30 minutes to 24 hours, will the app preserve sessions across restarts?  
**Answer:** Not for memory-only sessions. It only changes expiration while the session stays in memory, and increases resource retention.

**Question 7.** Why might a browser retain the old cookie after `session.invalidate()`?  
**Answer:** `invalidate()` destroys the server-side session and does not guarantee browser cookie removal in every setup; cookie deletion/expiration must be managed per logout policy.

**Question 8.** An API uses bearer JWTs with consistent signing keys and no `HttpSession`. Does a web pod restart automatically invalidate existing JWTs?  
**Answer:** Not merely from the pod restart, provided signing keys and verification policies remain compatible. Token expiry, revocation, and key-management incidents still apply.

## 20. Pre-deployment checklist

- [ ] Clarified whether sessions are memory-only, disk-persisted, or stored in a Spring Session external store.
- [ ] Understood that cookies hold only session IDs, distinct from session data.
- [ ] Verified default `server.servlet.session.persistent`/timeout for the Boot version in use.
- [ ] Never call `getSession(true)` when only checking for an existing session.
- [ ] Do not store irreplaceable business data solely inside local `HttpSession`.
- [ ] In multi-instance deployments, tested routing across nodes and failover.
- [ ] For Redis/JDBC, configured TTL, capacity, persistence/HA, serialization, and timeouts.
- [ ] Tested an actual application restart while preserving the same cookie jar.
- [ ] Designed clear UX when sessions become invalid, avoiding duplicate transaction submissions.
- [ ] Implemented logout/invalidation, session fixation protection, `HttpOnly`/`Secure`/`SameSite` cookies, and CSRF per authentication design.
- [ ] Kept session attributes minimal and free of sensitive credentials.
- [ ] Instrumented session errors, deployment timestamps, process restarts, and resource usage.
- [ ] Tested rolling deployments, timeouts, store failures, and version migrations if sessions must survive upgrades.

## Official references

- [Spring Boot 3.3 — Common Application Properties: server.servlet.session](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Boot 3.3 — Servlet Web Applications: Customizing Embedded Servlet Containers](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Spring Boot 3.3 — Spring Session](https://docs.spring.io/spring-boot/3.3/reference/web/spring-session.html)
- [Spring Session 3.3 — Boot with Redis](https://docs.spring.io/spring-session/reference/3.3/guides/boot-redis.html)
- [Spring Session 3.3 — WebSession Integration](https://docs.spring.io/spring-session/reference/3.3/web-session.html)
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Framework 6.1 — WebSession](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/WebSession.html)
- [Spring Framework 6.1 — CookieWebSessionIdResolver](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/session/CookieWebSessionIdResolver.html)
- [Apache Tomcat 10.1 — Manager Component and Persistence Across Restarts](https://tomcat.apache.org/tomcat-10.1-doc/config/manager.html)

**Key takeaway:** with Spring Boot using **in-process memory sessions**, restarts wipe out the old instance's session attributes even if the browser still sends the old ID. To maintain user experience across rollouts and failovers, decide explicitly which data must be durable, deploy an appropriate session store, configure cookies securely, and test actual restarts using the same cookie rather than merely checking that the server port came back up.