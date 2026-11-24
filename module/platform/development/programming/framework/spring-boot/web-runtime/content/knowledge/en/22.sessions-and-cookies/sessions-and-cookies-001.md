# Servlet HttpSession and WebFlux WebSession in Spring Boot

## 1. What are sessions used for?

HTTP is a request–response protocol. By default, the server does not automatically remember a previous request when receiving the next one. When an application needs to retain a temporary shopping cart, an in-progress form step, UI preferences, or login state across requests, it can use a **server-side session**.

Spring Boot provides two session APIs corresponding to its two web stacks:

- **`jakarta.servlet.http.HttpSession`** for **Jakarta Servlet / Spring MVC**, typically running on Tomcat or Jetty.
- **`org.springframework.web.server.WebSession`** for **Spring WebFlux / Reactive**, typically running on Reactor Netty while also supporting other compatible HTTP runtimes.

Both store attributes on the server side and associate requests with a session via a **session ID**, usually exchanged using a **cookie**. The core differences lie in how a session is created/started, how lifecycle operations are handled, the APIs, and the storage mechanism.

After completing this lesson, you will be able to:
1. Distinguish between a session, a session ID, a cookie, a request attribute, and authentication state.
2. Correctly use `HttpSession` in MVC and `WebSession` in WebFlux.
3. Understand `request.getSession(false)`, `WebSession.start()`, and `isStarted()`.
4. Practice with two complete Java 17+ Spring Boot examples and verify cookies using `curl`.
5. Configure timeout, Secure, HttpOnly, and SameSite per stack.
6. Analyze session fixation, logout, concurrency, local stores, and Spring Session Redis.

> **Practice versions:** the two sample applications are **two separate projects** using Java 17+, Spring Boot **3.5.x** with Gradle, and the appropriate MVC/WebFlux starter. With Spring Boot 4.x, the MVC starter changed to `spring-boot-starter-webmvc`; verify dependencies according to your version. The examples do not integrate Spring Security yet, so that the plain session lifecycle can be observed easily.

## 2. How do cookies and session IDs travel over HTTP?

~~~text
Browser                               Spring Boot
  |                                       |
  | POST /visit (no session cookie yet)   |
  |-------------------------------------->|
  |                           create/start session
  |                           store visits=1 on the server
  | HTTP 200                              |
  | Set-Cookie: SESSION_ID=<id>; ...      |
  |<--------------------------------------|
  |                                       |
  | GET /visit                            |
  | Cookie: SESSION_ID=<id>               |
  |-------------------------------------->|
  |                           lookup ID -> session -> visits
  | HTTP 200                              |
  |<--------------------------------------|
~~~

`SESSION_ID` and `<id>` in the diagram are placeholders only. The actual cookie is typically named `JSESSIONID` for a Servlet container or `SESSION` for the default WebFlux resolver; the name, Domain, Path, and flags can be customized.

**A cookie is not the session object.** A cookie usually only carries an ID so the server can look up attributes from memory, Redis, JDBC, or another session store. The client holds the cookie; data such as `visits` is stored on the server. Because the ID allows association with a session, treat the session ID as an **authentication-grade secret**: do not log it verbatim, and do not expose it in URLs, query parameters, JSON responses, or public error pages.

| Artifact | Where does it live? | Scope |
|---|---|---|
| Request attribute | Within the processing of one HTTP request | Does not automatically persist to the next request |
| Session attribute | Server-side session store | Across multiple requests in the same session until expired/deleted |
| Session ID | Server knows the ID; client typically holds it via a cookie | Identifier used to look up the session |
| Cookie | Browser/client | Sent according to Domain, Path, Secure, and SameSite rules |
| JWT or access token | Client and authentication system depending on architecture | Not automatically equivalent to a server-side session |

The presence of a `JSESSIONID` cookie **does not prove** that the user is logged in. An anonymous session can also use a cookie; permission checks must still be determined by authentication/authorization.

## 3. Comparing HttpSession and WebSession APIs

| Aspect | Servlet `HttpSession` | Reactive `WebSession` |
|---|---|---|
| Package | `jakarta.servlet.http.HttpSession` | `org.springframework.web.server.WebSession` |
| Web stack | Spring MVC / Servlet | Spring WebFlux |
| Obtaining a session | `request.getSession()` or `request.getSession(false)` | Inject `WebSession` or `exchange.getSession()` |
| When it starts | `getSession()` creates a session if none exists | Obtaining `WebSession` alone does not start it; add an attribute or call `start()` to begin |
| Reading an attribute | `getAttribute(String)` returns `Object` | `getAttribute(String)` / `getAttributeOrDefault(String,T)` |
| Writing an attribute | `setAttribute(String,Object)` | `getAttributes().put(String,Object)` |
| Removing an attribute | `removeAttribute(String)` | `getAttributes().remove(String)` |
| Reading the ID | `getId()` | `getId()` |
| State flag | `isNew()`: whether the client has joined the session yet | `isStarted()`: whether the session has been started |
| Time-to-idle | `getMaxInactiveInterval()` returns seconds | `getMaxIdleTime()` returns `Duration` |
| Changing timeout | `setMaxInactiveInterval(int)` | `setMaxIdleTime(Duration)` |
| Creation/access time | `long` values (milliseconds since epoch) | `Instant` |
| Rotating the ID | `HttpServletRequest.changeSessionId()` | `WebSession.changeSessionId()` returns `Mono<Void>` |
| Logout/invalidate | `invalidate()` returns `void` | `invalidate()` returns `Mono<Void>` |
| Saving at end of request | Handled by container/SessionRepository | WebFlux normally calls `save()` before committing the response |
| Default local store | Servlet container's session manager | `InMemoryWebSessionStore` via `DefaultWebSessionManager` |
| Shared store | Spring Session with Redis or JDBC | Spring Session with `ReactiveSessionRepository`, e.g., Redis |

**Important distinction:** Servlet's `isNew()` is not equivalent to WebFlux's `isStarted()`. `isNew()` reflects whether the client has joined the session under the Servlet contract; `isStarted()` indicates whether a `WebSession` has been started explicitly or implicitly by adding an attribute.

Spring Boot selects the web stack based on the classpath and configuration. If both MVC and WebFlux are present, Boot normally prioritizes Servlet/MVC. Therefore, running on Tomcat or Netty **is not enough** to decide the session API; you must check the web application type and the framework handling the request.

## 4. HttpSession: creating, reading, updating, and ending

### 4.1. Controlled session retrieval

In a Spring MVC controller:

~~~java
HttpSession createdOrExisting = request.getSession(); // May create a new session
HttpSession onlyExisting = request.getSession(false);  // Does not create, may be null
~~~

The two calls differ in side effects:
- `getSession()` or `getSession(true)` looks up a valid session, and creates a new one if none exists.
- `getSession(false)` returns `null` if no valid session exists.
- A controller accepting `HttpSession` as a parameter is typically supplied a session through argument resolution; if you want to ensure **no session is created on read-only paths**, accept `HttpServletRequest` and call `getSession(false)`.

Typically after creating a new session, the Servlet container emits `Set-Cookie: JSESSIONID=...`. Exact cookie emission depends on the tracking mode, response state, and container.

### 4.2. Attributes and lifetime

~~~java
HttpSession session = request.getSession();
session.setAttribute("theme", "dark");
String theme = (String) session.getAttribute("theme");
session.removeAttribute("theme");
~~~

`getAttribute` returns `Object`, so casting or type checking is required. Timing:
- `getCreationTime()` and `getLastAccessedTime()` return values in milliseconds.
- `getMaxInactiveInterval()` and `setMaxInactiveInterval(int seconds)` allow reading/changing the inactivity interval.
- A session is considered expired when inactivity exceeds the limit according to the container/store mechanism.
- `invalidate()` renders the session invalid. Calling subsequent methods on an invalidated session may throw `IllegalStateException`.

### 4.3. Rotating the ID after login

~~~java
// Fragment in MVC when the request already has a valid session:
request.changeSessionId();
~~~

`changeSessionId()` is on `HttpServletRequest`, **not** a method on `HttpSession`. It is an effective measure against session fixation when a user is authenticated. If you use Spring Security, let Security's session fixation protection coordinate it; do not add duplicate rotation logic.

## 5. WebSession: obtaining a session does not necessarily create a cookie

### 5.1. Injecting WebSession

Spring WebFlux allows passing `WebSession` directly into a handler method:

~~~java
// Fragment in a WebFlux @RestController:
@GetMapping("/theme")
public String theme(WebSession session) {
    return session.getAttributeOrDefault("theme", "light");
}
~~~

This call is **read-only**. When there is no prior session, creating the `WebSession` object does not automatically start a persisted session or emit an ID cookie. A WebSession starts:
- **Implicitly**: when an attribute is added to `session.getAttributes()`.
- **Explicitly**: by calling `session.start()`.
- You can check `session.isStarted()` to see whether it has started.

~~~java
session.getAttributes().put("theme", "dark");
session.start();
boolean started = session.isStarted();
~~~

The snippet above only illustrates the API inside a handler, not a standalone Java class. Writing an attribute is already sufficient to start the session; calling `start()` in addition is not required.

### 5.2. WebSession returns Mono for lifecycle operations

~~~java
Mono<Void> rotated = session.changeSessionId();
Mono<Void> removed = session.invalidate();
~~~

WebFlux operates on publishers: the `Mono<Void>` result **must become part of the subscribed reactive chain**. For example:

~~~java
@PostMapping("/logout")
public Mono<String> logout(WebSession session) {
    return session.invalidate().thenReturn("logged out");
}
~~~

If you only call `session.invalidate()` and discard the `Mono` while returning another result, the asynchronous operation may **never execute**. Do not call `block()` on the Reactor event loop to force execution; compose using `then`, `flatMap`, and `thenReturn` along the processing flow.

`WebSession.save()` also returns a `Mono`, though the framework normally calls it before committing the response. You do not need to call `save()` manually in every controller. When using Spring Session with reactive Redis, appropriate non-blocking connections/storage are required; the name `WebSession` itself does not make arbitrary I/O in a handler non-blocking.

## 6. Runnable Example A — Spring Boot MVC and HttpSession

Create a project using Spring Initializr: **Spring Boot 3.5.x, Java 17+, Gradle**, dependency **Spring Web**. Do not add Spring Security for this exercise. If the project already has the Boot plugin and dependency management, the dependency fragment is:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Create the file `src/main/java/demo/servlet/ServletSessionDemo.java`:

~~~java
package demo.servlet;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ServletSessionDemo {

    public static void main(String[] args) {
        SpringApplication.run(ServletSessionDemo.class, args);
    }

    @PostMapping("/visit")
    public Map<String, Integer> visit(HttpServletRequest request) {
        HttpSession session = request.getSession();
        Integer current = (Integer) session.getAttribute("visits");
        int next = (current == null ? 0 : current) + 1;
        session.setAttribute("visits", next);
        return Map.of("visits", next);
    }

    @GetMapping("/visit")
    public Map<String, Integer> read(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        Integer visits = session == null ? null
                : (Integer) session.getAttribute("visits");
        return Map.of("visits", visits == null ? 0 : visits);
    }

    @PostMapping("/logout")
    public Map<String, Boolean> logout(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
        return Map.of("loggedOut", true);
    }
}
~~~

This is a complete Java class inside a project with the proper dependencies. The example only manages a `visits` counter to observe session behavior; the `/logout` endpoint does not represent the logout workflow of a real security system.

Run from the project root directory:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Once Boot is running on `localhost:8080`, send sequentially:

~~~bash
curl -sS -c servlet-cookies.txt -X POST http://localhost:8080/visit
curl -sS -b servlet-cookies.txt -c servlet-cookies.txt -X POST http://localhost:8080/visit
curl -sS -b servlet-cookies.txt http://localhost:8080/visit
curl -sS -b servlet-cookies.txt -X POST http://localhost:8080/logout
curl -sS -b servlet-cookies.txt http://localhost:8080/visit
~~~

**Five expected JSON response bodies, each line being the result of an independent request:**

~~~text
{"visits":1}
{"visits":2}
{"visits":2}
{"loggedOut":true}
{"visits":0}
~~~

Why?
1. The first request sends no prior cookie, so `getSession()` creates a session and stores 1; `curl -c` saves the cookie.
2. The second request uses `curl -b` to send the cookie, so the server looks up the session and increments it to 2.
3. GET uses `getSession(false)` and reads 2.
4. POST logout invalidates the session.
5. GET with the invalidated ID finds no valid session and returns 0.

The `Set-Cookie` header and random ID will change between runs. Do not try to compare the exact ID string against sample outputs. If the application has Spring Security, POST requests by default may require a CSRF token; this example intentionally omits Security.

## 7. Runnable Example B — Spring WebFlux and WebSession

Create **another separate project**, Spring Boot 3.5.x, Java 17+, Gradle, dependency **Spring Reactive Web (WebFlux)**. Do not add the MVC starter to this project. Dependency fragment:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Create the file `src/main/java/demo/reactive/ReactiveSessionDemo.java`:

~~~java
package demo.reactive;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.WebSession;
import reactor.core.publisher.Mono;

@SpringBootApplication
@RestController
public class ReactiveSessionDemo {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveSessionDemo.class, args);
    }

    @PostMapping("/visit")
    public Mono<Map<String, Integer>> visit(WebSession session) {
        int next = session.getAttributeOrDefault("visits", 0) + 1;
        session.getAttributes().put("visits", next);
        return Mono.just(Map.of("visits", next));
    }

    @GetMapping("/visit")
    public Mono<Map<String, Integer>> read(WebSession session) {
        int value = session.getAttributeOrDefault("visits", 0);
        return Mono.just(Map.of("visits", value));
    }

    @PostMapping("/logout")
    public Mono<Map<String, Boolean>> logout(WebSession session) {
        return session.invalidate()
                .thenReturn(Map.of("loggedOut", true));
    }
}
~~~

Run with the same `./gradlew bootRun` or `.\gradlew.bat bootRun` command from the reactive project. Stop the Servlet project before running the reactive one if both use port 8080.

~~~bash
curl -sS -c reactive-cookies.txt -X POST http://localhost:8080/visit
curl -sS -b reactive-cookies.txt -c reactive-cookies.txt -X POST http://localhost:8080/visit
curl -sS -b reactive-cookies.txt http://localhost:8080/visit
curl -sS -b reactive-cookies.txt -X POST http://localhost:8080/logout
curl -sS -b reactive-cookies.txt http://localhost:8080/visit
~~~

**Expected JSON response bodies:**

~~~text
{"visits":1}
{"visits":2}
{"visits":2}
{"loggedOut":true}
{"visits":0}
~~~

Explaining the similarities and differences:
- The request flow and results can match Servlet because both maintain state via a cookie.
- WebFlux `getAttributeOrDefault` only reads and does not automatically start the session.
- `session.getAttributes().put` starts the session the first time state is needed; the framework saves it automatically when the response is committed.
- `session.invalidate().thenReturn(...)` performs session cancellation inside the reactive chain.
- The default WebFlux cookie is typically named `SESSION`, and should not be hardcoded in the client; `curl` stores whatever cookie the server issues.

**Try more:** run `curl -i http://localhost:8080/visit` before any POST and inspect the `Set-Cookie` header. In default WebFlux, merely reading a new unstarted `WebSession` does not need to create a cookie. Compare this with a Servlet handler that calls `request.getSession()` even when only reading: Servlet may create a session earlier.

## 8. Configuring timeout and cookies in Spring Boot

### 8.1. Servlet

Example `application.yml` configuration for an **HTTPS production** environment:

~~~yaml
server:
  servlet:
    session:
      timeout: 20m
      cookie:
        name: JSESSIONID
        http-only: true
        secure: true
        same-site: lax
~~~

Important properties:
- `server.servlet.session.timeout`: inactivity duration (idle timeout) before the session can expire.
- `server.servlet.session.cookie.name`: name of the session cookie.
- `http-only`: browser restricts JavaScript from reading the cookie.
- `secure`: cookie is only sent over HTTPS according to browser policy.
- `same-site`: mitigates certain cases where cookies are automatically sent in cross-site requests.

### 8.2. Reactive

Corresponding HTTPS production example:

~~~yaml
server:
  reactive:
    session:
      timeout: 20m
      cookie:
        name: SESSION
        http-only: true
        secure: true
        same-site: lax
~~~

`server.reactive.session.timeout` and `server.reactive.session.cookie.*` are the **WebFlux session** properties in Spring Boot 3.5. Do not set `server.servlet.session.*` and expect Reactor Netty/WebFlux to apply them.

**Note when testing locally over HTTP:** if `secure: true` is enabled on `http://localhost:8080`, many clients will not send the cookie back the same way they do in production HTTPS. Therefore, the runnable examples above use default configuration to avoid interference from browser/cookie policies.

### 8.3. Session timeout and cookie lifetime are not the same

| Mechanism | Who decides? | Meaning |
|---|---|---|
| Session timeout | Server/store | After inactivity duration, the session is no longer valid |
| Cookie Max-Age/Expires | Client/browser | When the browser removes the cookie |
| Cookie Secure | Client/browser | When to send the cookie over a secure channel |
| Cookie HttpOnly | Client/browser | Whether JavaScript can read the cookie |
| Cookie SameSite | Client/browser | Conditions for sending the cookie in cross-site contexts |

Cookie still present while session has expired ⇒ server receives the old ID but cannot retrieve state. Conversely, a cookie deleted early does not necessarily cause the server to immediately delete the session; state may wait for expiration/cleanup.

**Idle timeout is not absolute max lifetime**: each valid activity may update the last-accessed time depending on the store; systems requiring an absolute maximum login duration must add a separate appropriate policy.

## 9. Rotating IDs, invalidation, and safe logout

### Session fixation

Scenario: an attacker knows a session ID before the victim logs in. If the ID does not change after login, the attacker may hijack the session. Once the user is authenticated, one countermeasure is **rotating the session ID**:

~~~java
// Servlet MVC fragment: request already has a valid session.
request.changeSessionId();
~~~

~~~java
// WebFlux fragment: Mono must be included in the pipeline.
return session.changeSessionId().thenReturn("ready");
~~~

Unlike `invalidate()`, changing the ID generally preserves the session's ongoing state while attaching a new ID. In a Spring Security application, use Security's session fixation strategy before writing custom rotation logic.

### Logout

Servlet: `HttpSession.invalidate()` is synchronous. WebFlux: `WebSession.invalidate()` returns `Mono<Void>`, which must be composed into the publisher. However, invalidating a session **does not mean** all access tokens, refresh tokens, or sessions on other devices have been revoked. A real security-enabled application's logout flow needs to clear the security context and manage cookies and tokens according to the actual security contract.

### CSRF / XSS

Session cookies are automatically attached by the browser when cookie conditions allow, so state-changing endpoints need **CSRF** protection. `SameSite` reduces risk in some scenarios but does not fully replace CSRF tokens or Origin checks. `HttpOnly` reduces the risk of stealing the ID via JavaScript, but does not neutralize all XSS attacks; a malicious script on the same origin can still issue requests carrying the valid cookie.

Do not return the session ID from APIs, put the ID in URLs, or write raw tokens into logs or tracing labels.

## 10. Local sessions and Spring Session in multi-instance deployments

### 10.1. When stored only in local memory

Normally, session state resides inside a single instance:

~~~text
Client --cookie--> instance A   session ID -> attributes reside on A
Client --cookie--> instance B   B cannot find attributes on A
~~~

With Servlet, the container manages sessions; with default WebFlux, `DefaultWebSessionManager` uses `InMemoryWebSessionStore`. Load balancing across two replicas without a shared session store can cause users to experience "randomly disappearing" state. Sticky sessions only reduce replica switching; they do not handle failures or shutdowns of the instance holding the session.

### 10.2. Spring Session and shared stores

Spring Session provides a repository layer to replace the default session store:
- For MVC/Servlet: `SessionRepository`, commonly backed by Redis or JDBC.
- For WebFlux: `ReactiveSessionRepository` integrated via `WebSessionManager`; reactive Redis is a popular choice supported by Spring Boot.
- Spring Boot's Spring Session starter can auto-configure the necessary filter/manager, without manually adding `@EnableRedisHttpSession` or `@EnableRedisWebSession` when keeping auto-configuration.

Example Spring Boot 3.5 Gradle fragment (add to the appropriate MVC **or** WebFlux project):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-session-data-redis'
}
~~~

Example connection configuration in a development environment:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
  session:
    timeout: 20m
~~~

`spring.session.timeout` applies when Spring Session is auto-configured; on Servlet, if this property is not set, Boot may fall back to `server.servlet.session.timeout`. For WebFlux and Spring Session Redis, verify the timeout, repository, and configuration properties for the exact version in use.

**Adding the dependency is not enough** to claim you have shared sessions: Redis must be running, connection configuration must match, and the application must actually be using the Spring Session manager/filter. Test two replicas with the same session cookie, restart one replica, and verify state and expiry.

### 10.3. Do not store everything in the session

Store small IDs or short-lived state; avoid:
- Large data lists, uploaded files, or query results that can be re-fetched from the DB.
- Database connections, streams, request/response objects, or lifecycle-bound beans.
- Objects that are difficult to serialize when moving to Redis/JDBC or when changing Java class versions.
- Data requiring durable persistence for payment/order business workflows.

A session can be invalidated, expire, be lost on store failure, or be evicted. Use a transactional database as the source of truth for core business data.

## 11. Two concurrent requests can update a session incorrectly

For example, `visits=5` and two requests execute concurrently:
1. Request A reads 5; request B also reads 5.
2. Both compute the next value as 6.
3. A writes 6; B writes 6.
4. The final session value may be **6** even though two visits occurred.

Neither `HttpSession` nor `WebSession` turns a read–compute–write sequence into a transaction. The curl demos above send requests **sequentially**, so the bodies are deterministic; do not infer that the counter is safe under concurrent load.

If business logic requires accuracy, use storage that supports atomic increments, optimistic locking, or appropriate transactions. In WebFlux, avoid "fixing" it by calling `block()` on the event loop. With Redis Session, persisting the attributes map also does not automatically make variable increments atomic.

## 12. @SessionAttribute, @SessionAttributes, and SessionStatus

These three APIs have different purposes:

| API | Purpose |
|---|---|
| `HttpSession` / `WebSession` | Manage attributes and session lifecycle |
| `@SessionAttribute` | Retrieve an existing session attribute, typically set by a filter or other code |
| `@SessionAttributes` | Keep model attributes of **a controller workflow** across multiple requests |
| `SessionStatus.setComplete()` | End the state managed by `@SessionAttributes`, **not a system-wide logout** |

Example fragment for an appropriate MVC or WebFlux controller:

~~~java
// Standalone illustrative snippet; UserDraft and imports must exist in the project.
@Controller
@SessionAttributes("draft")
class DraftController {

    @ModelAttribute("draft")
    UserDraft draft() {
        return new UserDraft();
    }

    @PostMapping("/draft/finish")
    String finish(SessionStatus status) {
        status.setComplete();
        return "redirect:/done";
    }
}
~~~

`@SessionAttributes` is a controller class-level annotation for storing model attributes across a workflow. Do not confuse it with the singular `@SessionAttribute`, which only retrieves an existing attribute. If you need to directly modify session-wide state, choose `HttpSession` or `WebSession` according to the stack.

## 13. Security and operations checklist

- [ ] Identify MVC/Servlet vs. WebFlux before choosing session APIs and properties.
- [ ] Avoid creating sessions unnecessarily; MVC read-only paths use `getSession(false)`.
- [ ] WebFlux only starts a session when state needs to be saved; use `start()`/attribute mutation properly.
- [ ] WebFlux `changeSessionId()` and `invalidate()` must be part of the publisher chain.
- [ ] Never log, display, or attach session IDs to metric labels.
- [ ] Configure Secure/HttpOnly/SameSite/Domain/Path appropriately for HTTPS, proxies, and browsers.
- [ ] Handle session fixation on login; logout invalidates both the session and necessary security contexts.
- [ ] Enable CSRF protection when using cookie-based authentication.
- [ ] Understand session timeout and cookie Max-Age as two separate mechanisms.
- [ ] If using multiple replicas, intentionally design a shared session store or stateless architecture.
- [ ] Keep session attributes small, serializable when using a shared store, and not the business source of truth.
- [ ] Measure idle expiry, rejected cookies, store latency, and race conditions under concurrent requests.

## 14. Common troubleshooting table

| Symptom | Common cause | Resolution |
|---|---|---|
| Two curl POSTs still return `visits=1` | Cookie not sent back | Use `curl -c` and `curl -b` |
| Read-only MVC GET creates a new cookie | Code calls `getSession()` or a filter/Security creates a session | Switch to `getSession(false)` where appropriate; inspect the full request pipeline |
| Injecting WebSession produces no cookie | New session has no attributes/has not called `start()` | Normal behavior; only created when state needs to be saved |
| Cookie is present but attributes cannot be retrieved | Session expired, invalid ID, wrong store, or wrong cookie policy | Inspect Cookie header, timeout, Domain/Path, and store |
| Running 2 replicas intermittently keeps and loses sessions | Local state storage | Use a Spring Session shared store or change architecture |
| Still logged in after logout | Only removed one attribute while Security context/token remains | Use Security's logout flow and revoke tokens appropriately |
| Cookie not sent over local HTTP | `Secure=true` or client policy | Use HTTPS or separate dev configuration |
| Cross-origin frontend loses session | CORS/credentials/SameSite/Secure/Domain | Inspect Request/Response cookies and configure CORS for the exact origin |
| WebFlux logout does not invalidate | Mono returned by `invalidate()` was ignored | Return/compose the publisher |
| ClassNotFound `javax.servlet` | Wrong Java package for Spring Boot 3+/4+ | Use `jakarta.servlet.http.HttpSession` |
| Redis session errors after deployment | Serialization/schema/connection | Check Redis, serializer, namespace, and migration |
| Session counter loses updates under concurrent requests | Non-atomic read-modify-write | Update via storage supporting atomic/transactional operations |

To investigate, follow the sequence: **Cookie/Set-Cookie → session API → timeout and store → Security → concurrency**. A single HTTP 200 does not prove the next request can look up the session.

## 15. Review questions

**1.** MVC needs to check whether a session exists without creating a new one. What call should be used?

**Answer:** `request.getSession(false)`. It returns `null` if no valid session exists.

**2.** A WebFlux controller accepts `WebSession` and only reads an attribute. Does it send a new cookie by default?

**Answer:** No. When there is no prior session, `WebSession` is not started if only read. Adding an attribute or calling `start()` starts the session.

**3.** How does `HttpSession.invalidate()` differ from `WebSession.invalidate()`?

**Answer:** The Servlet method returns `void`; the WebFlux method returns `Mono<Void>`. The `Mono` must be subscribed through the reactive flow.

**4.** Does a `JSESSIONID` cookie mean the user is logged in?

**Answer:** No. It carries a session ID; permissions and auth state must be verified independently.

**5.** Will two concurrent requests incrementing a session counter always increase it by two?

**Answer:** No, read–modify–write is not automatically atomic; lost updates can occur.

**6.** Should default WebFlux use `server.servlet.session.timeout` or `server.reactive.session.timeout`?

**Answer:** For default WebFlux sessions, use `server.reactive.session.timeout`. When Spring Session is used, check `spring.session.timeout` and repository configuration.

**7.** Does clearing state with `SessionStatus.setComplete()` expire all user sessions?

**Answer:** No. It cleans up `@SessionAttributes` workflow state; it does not replace `invalidate()`/logout.

**8.** There are 3 replicas using local sessions, and users occasionally lose their shopping cart. Why?

**Answer:** Requests are routed to a replica that does not contain the corresponding session data. A shared session store or a redesigned state model is needed.

### Self-check exercise

Try `curl -i` on the `GET /visit` endpoint without sending any cookie, then POST and GET using a cookie jar. Inspect what is inside `Set-Cookie` (and do not log the ID). Stop the app, change the session timeout in each stack to `1m` in a test profile, and retry after the inactivity period; explain the difference between a cookie still existing and a session having expired.

## 16. Official references

- [Jakarta Servlet — HttpSession](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/HttpSession.html)
- [Jakarta Servlet — HttpServletRequest](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/HttpServletRequest.html)
- [Spring Framework 6.2 — WebSession](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/server/WebSession.html)
- [Spring Framework — MVC @SessionAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattribute.html)
- [Spring Framework — WebFlux @SessionAttribute](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/sessionattribute.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Boot — Spring Session](https://docs.spring.io/spring-boot/reference/web/spring-session.html)
- [Spring Session — WebSession Integration](https://docs.spring.io/spring-session/reference/web-session.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)

**Takeaway:** both `HttpSession` and `WebSession` keep session attributes **on the server side** and typically use a cookie carrying an ID. The differences belong to Servlet versus WebFlux, when the session starts, and how lifecycle operations execute. When deploying, always verify timeout, cookie flags, session fixation, logout, multi-instance stores, and concurrency.
