# Distinguishing Session State from Request-Local Data in Spring Boot

## 1. Objective

HTTP is a protocol that **does not automatically retain application state across requests**. Nevertheless, a web application often needs to remember a logged-in user, UI language, or an active workflow step. At the same time, each individual request carries temporary data such as a request ID, validation results, search parameters, tracing context, or intermediate handler values.

These two kinds of data have **different lifetimes, sharing scopes, and risks**:

- **Session state:** tied to an HTTP session, accessible across *multiple requests* carrying the same session identifier until the session expires, is invalidated, or is rotated by the system.
- **Request-local state:** belongs strictly to a *single HTTP request* and normally does not survive to the next request. It can be passed among filters, interceptors, controllers, and components participating in processing that same request.

This lesson focuses on **Spring Boot 3.x, Spring MVC/Servlet, and Java 17+**, covering `HttpSession`, `HttpServletRequest`, request/session-scoped beans, session cookies, and testing. The end of the lesson compares this with Spring WebFlux.

After completing it, you will know how to place **the right data in the right scope**, avoid stuffing temporary data into sessions, prevent cross-user state leaks, and avoid assuming HTTP keep-alive or a Java thread represents a user login session.

## 2. A visual example: two requests, one session

Suppose a user chooses the `vi` language on the first request, then opens another page in the same browser:

```text
Browser A                                     Spring Boot
    |                                             |
    | POST /lab/language value=vi                 |
    |-------------------------------------------->|
    |                                       Create HttpSession S1
    |                                       Session attribute:
    |                                         uiLanguage = "vi"
    |                                       Request attribute:
    |                                         requestTraceId = "R1"
    |<--------------------------------------------|
    | Set-Cookie: JSESSIONID=<server-generated-id>|
    |                                             |
    | GET /lab/state                              |
    | Cookie: JSESSIONID=<same-id>                |
    |-------------------------------------------->|
    |                                       Find HttpSession S1
    |                                       uiLanguage = "vi"
    |                                       requestTraceId = "R2"
    |<--------------------------------------------|
    |                                             |
    | GET /lab/state (without sending cookie)     |
    |-------------------------------------------->|
    |                                       Cannot find S1
    |                                       requestTraceId = "R3"
    |<--------------------------------------------|
```

`R1`, `R2`, and `R3` are merely symbolic labels. The core takeaway: **session values persist when the client sends back a valid session ID**, whereas a new request ID is generated for each request. The second HTTP request is not “the same request” as the first.

**The `JSESSIONID` cookie usually holds only the session identifier**, not the full Java objects stored on the server. In a traditional Servlet container setup, session data lives on the server/container; with Spring Session, it may live in a shared store like Redis or JDBC. Never confuse the session cookie with “where every session value is stored”.

## 3. Scope and lifecycle: comparison table

| Criterion | Request state | Session state |
| --- | --- | --- |
| Direct Servlet object | `HttpServletRequest` and request attributes | `HttpSession` and session attributes |
| Spring bean scope | `@RequestScope` | `@SessionScope` |
| Lifetime | During the processing of one request; with nuances on async dispatch | Across requests using the same session, until timeout/invalidation/rotation |
| Who sees it? | Components handling **the current request** | Requests accessing **the same session** |
| Suitable examples | Request ID, parse results, validation, tracing data, intermediate values | Temporary UI language, small workflow state, framework-managed authentication |
| Automatically carries over to next request? | **No** | **Yes**, while the session remains valid and resolved |
| Common risks | Confusing state with threads, leaking into singletons | Stale data, two tabs overwriting, session fixation/hijacking, memory, multi-server distribution |
| Requires a cookie? | No | Typically uses a session ID cookie, though containers may support other tracking modes |
| Is it a durable database? | No | **No** |

**Additional distinctions:**

- **Java local variables:** scoped to a method invocation; best for data used within a single step, often removing any need for request attributes.
- **`@RequestParam`, `@PathVariable`, `@RequestBody`:** *input* data for the current request; they do not automatically become session state.
- **Spring MVC `Model`:** primarily passes data to a view while rendering the current request; not automatically session state.
- **`RedirectAttributes.addFlashAttribute`:** temporary data carried across a single redirect, normally held temporarily in the session and consumed at the target request; **distinct from both ordinary request attributes and longer-lived session state**.
- **`@SessionAttributes` on a controller:** a Spring MVC mechanism to store **specific model attributes** in the session across a controller workflow, typically a multi-step form; not synonymous with `@SessionScope` beans and should not be used as a general cross-component session store.
- **Singleton beans:** Spring's default scope, shared across requests and users. Never store user-specific data in mutable instance fields of controllers or singletons.

## 4. `HttpServletRequest`: data bound strictly to the current request

The Servlet API lets you store attributes via:

```java
request.setAttribute("traceId", "some-request-id");
Object trace = request.getAttribute("traceId");
request.removeAttribute("traceId");
```

This illustrates the API; it requires a `request` variable of type `jakarta.servlet.http.HttpServletRequest`. A filter can set `traceId` so a controller on the same request can read it. When the browser issues a new HTTP request, the controller receives a new request object; prior attributes are **never automatically copied to the new request**.

When to use request attributes:

- A filter computes a correlation/request ID so controllers and interceptors can read it during the request lifecycle.
- Middleware records a start timestamp or temporary metrics to compute duration.
- Validation/parsing results shared across components participating in the same request.
- An internal flag for the current rendering pass with no meaning across subsequent requests.

**Do not overuse:** if data is only needed in one method, use local variables or method parameters. Request attribute keys are plain strings and can collide; prefer namespaced keys such as `"demo.requestTraceId"`.

### Request scope is not thread scope

A servlet request typically executes on a worker thread, yet **a thread is not a request**:

- A platform thread in a pool can finish serving Request A and immediately serve Request B.
- Virtual threads in Spring Boot may spin up distinct threads for subtasks or requests, and they are not sessions either.
- Async servlet dispatches or asynchronous execution can move work across threads within one logical request lifecycle.

Therefore, **do not use `ThreadLocal` as a substitute for `HttpSession` or `HttpServletRequest`**. If you manually introduce `ThreadLocal`, you must manage scope, `finally` cleanup, context propagation, and async boundaries very carefully. For tracing, prefer dedicated observability/context-propagation libraries.

## 5. `HttpSession`: state accessible across multiple requests

A servlet controller can obtain a session:

```java
// Create a new session if none exists.
HttpSession session = request.getSession(true);

// Get only an existing session; return null if absent.
HttpSession existing = request.getSession(false);

session.setAttribute("uiLanguage", "vi");
String language = (String) session.getAttribute("uiLanguage");

// Remove a single value:
session.removeAttribute("uiLanguage");

// Invalidate the entire session (e.g., when ending a session):
session.invalidate();
```

This is an illustrative snippet in a servlet web context, not a standalone application. Java class names reside in `jakarta.servlet.http` for Spring Boot 3.x.

**Critical difference between `getSession(true)` and `getSession(false)`:**

- `getSession(true)`: if no valid session exists, requests session creation; the server may emit a session cookie so the browser retains the ID.
- `getSession(false)`: returns only an existing valid session, or `null` if none exists. Use this on endpoints that **only observe state** to avoid accidentally creating sessions for every anonymous request.

In Spring MVC, declaring `HttpSession` directly as a controller parameter is convenient, yet often causes the container to resolve/create a session for that argument. To inspect **without creating** a session, accept `HttpServletRequest` and call `getSession(false)` explicitly.

### Session timeout and cookie expiry are not the same thing

A session can be invalidated/logged out, expire from inactivity, be dropped on server restart, or be lost when using non-durable storage. The browser cookie may remain while the server **no longer has the corresponding session**.

Conversely, the browser closing a window or deleting a cookie does not guarantee the server-side session object is immediately cleaned up; cleanup depends on timeout and the session manager.

Example in `application.properties`:

```properties
server.servlet.session.timeout=20m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

This is a common baseline for cookie-based Servlet apps; it is **not sufficient for production security** without HTTPS, authentication, CSRF, proper session management, and other headers. When serving over real **HTTPS**, you normally also need:

```properties
server.servlet.session.cookie.secure=true
```

Do not apply `secure=true` to a plain HTTP localhost demo and wonder why the browser fails to send the cookie back; `Secure` cookies require HTTPS (some browsers have localhost exceptions, which must never be relied upon). Ensure proxies/forwarded headers, TLS termination, and domains are designed properly; never weaken `Secure` in production to “fix login”.

`HttpOnly` restricts JavaScript from directly reading the session cookie, yet **does not by itself stop XSS from triggering actions under the active session**. `SameSite=Lax` mitigates certain CSRF scenarios, yet **does not replace CSRF tokens** in cookie-authenticated apps performing state changes.

## 6. Runnable example: proving both scopes with two requests

This sample app uses no database. A POST endpoint stores the **UI language** in `HttpSession`, a filter attaches a new **`requestTraceId`** on `HttpServletRequest`, and a GET endpoint returns both values so you can observe the difference.

### 6.1. Project initialization

Use **Java 17+**, **Spring Boot 3.x** (e.g., an actively maintained 3.x release), and the **Spring Web** starter (`spring-boot-starter-web`). Add **Spring Boot Starter Test** (`spring-boot-starter-test`) to run tests.

File structure:

```text
src/
├─ main/
│  ├─ java/com/example/demo/
│  │  ├─ SessionRequestApplication.java
│  │  ├─ RequestTraceFilter.java
│  │  └─ StateLabController.java
│  └─ resources/
│     └─ application.properties
└─ test/
   └─ java/com/example/demo/
      └─ StateLabControllerTest.java
```

This is a **local demo focused purely on session/request lifecycles**, with Spring Security disabled. POST endpoints in the demo **are not protected by CSRF tokens** and **must not be used directly for account data or public apps**. Section 10 lists what must be added before real deployment.

### 6.2. Main application class

**`src/main/java/com/example/demo/SessionRequestApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionRequestApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionRequestApplication.class, args);
    }
}
```

### 6.3. Filter storing a trace ID in the request, not the session

**`src/main/java/com/example/demo/RequestTraceFilter.java`**

```java
package com.example.demo;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class RequestTraceFilter extends OncePerRequestFilter {

    public static final String ATTRIBUTE_KEY = "demo.requestTraceId";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        request.setAttribute(
            ATTRIBUTE_KEY,
            UUID.randomUUID().toString()
        );
        filterChain.doFilter(request, response);
    }
}
```

`OncePerRequestFilter` ensures the filter executes once per request dispatch according to filter rules; async/error dispatches follow their own dispatch rules. The demo does not use async. Every new HTTP request passing through the filter gets a fresh `UUID` in attribute `demo.requestTraceId`. The filter **never writes** to `HttpSession`.

In production, request IDs may come from an edge proxy or tracing framework; never treat a client-supplied ID as a trusted identifier for authorization or sensitive data decisions.

### 6.4. Controller: session value surviving across requests

**`src/main/java/com/example/demo/StateLabController.java`**

```java
package com.example.demo;

import java.util.Set;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/lab")
public class StateLabController {

    private static final String LANGUAGE_KEY = "demo.uiLanguage";
    private static final Set<String> ALLOWED = Set.of("vi", "en");

    @PostMapping("/language")
    public StateView setLanguage(
            @RequestParam String value,
            HttpServletRequest request) {

        if (!ALLOWED.contains(value)) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Only vi or en is allowed"
            );
        }

        HttpSession session = request.getSession(true);
        session.setAttribute(LANGUAGE_KEY, value);
        return snapshot(request, session);
    }

    @GetMapping("/state")
    public StateView state(HttpServletRequest request) {
        // Do not create a session just to read state.
        HttpSession session = request.getSession(false);
        return snapshot(request, session);
    }

    @PostMapping("/end")
    public ResponseEntity<Void> end(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
        return ResponseEntity.noContent().build();
    }

    private StateView snapshot(
            HttpServletRequest request,
            HttpSession session) {

        String requestTraceId = (String) request.getAttribute(
            RequestTraceFilter.ATTRIBUTE_KEY
        );

        String language = session == null
            ? null
            : (String) session.getAttribute(LANGUAGE_KEY);

        // Do not include session.getId() in the API response.
        return new StateView(
            requestTraceId,
            language,
            session != null
        );
    }

    public record StateView(
        String requestTraceId,
        String language,
        boolean sessionPresent
    ) {}
}
```

Key takeaways:

- `POST /lab/language` validates `value` is only `vi` or `en`, then creates/retrieves the session and stores `demo.uiLanguage`. This is **session state**, not a property of the singleton `StateLabController` bean.
- `GET /lab/state` uses `request.getSession(false)` so it does not create a session just for reading. With no valid cookie/session, the response has `sessionPresent=false` and `language=null`.
- `requestTraceId` comes from the **request attribute** placed by the filter on the current request. The next request receives a brand-new UUID, even while carrying the same session cookie.
- `POST /lab/end` calls `session.invalidate()`; subsequent requests using the old ID can no longer access the old session. This is a session-termination demo, **not a full replacement for Spring Security logout** when real authentication exists.
- Never return `session.getId()` in JSON or plaintext logs. A session ID is a sensitive credential: anyone holding a valid ID may hijack the session unless additional controls prevent it.

### 6.5. Configuration for the demo

**`src/main/resources/application.properties`**

```properties
server.port=8080
server.servlet.session.timeout=20m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

**Do not set `server.servlet.session.cookie.secure=true` when running this example over HTTP localhost.** In production, run HTTPS and enable `Secure` cookies appropriately for the deployment context.

### 6.6. Testing with curl: persisting cookies across requests

Start from the project directory containing the Maven Wrapper:

```bash
java -version
./mvnw spring-boot:run
```

Windows: `mvnw.cmd spring-boot:run`. Open another terminal. The examples below use Bash/Unix; on Windows, use `curl.exe` and adjust cookie file paths as needed.

**Step 1 — no cookie:**

```bash
curl -s http://localhost:8080/lab/state
```

JSON output similar to:

```json
{"requestTraceId":"RANDOM-UUID-1","language":null,"sessionPresent":false}
```

`RANDOM-UUID-1` is an explanatory placeholder for a real UUID, not a literal fixed output. To inspect status codes, use `curl -i`.

**Step 2 — send POST and save cookie to a cookie jar:**

```bash
curl -i -c session-cookies.txt \
  -X POST "http://localhost:8080/lab/language" \
  --data-urlencode "value=vi"
```

When the session is created, the response typically includes `Set-Cookie: JSESSIONID=...` and JSON:

```json
{"requestTraceId":"RANDOM-UUID-2","language":"vi","sessionPresent":true}
```

This response is **illustrative**. Exact IDs, header ordering, cookie attributes, and JSON formatting depend on the runtime. **Never post real session cookies to issue trackers, chats, or logs.**

**Step 3 — send the cookie jar back on subsequent requests:**

```bash
curl -s -b session-cookies.txt http://localhost:8080/lab/state
curl -s -b session-cookies.txt http://localhost:8080/lab/state
```

Both responses should share `"language":"vi"` and `"sessionPresent":true`, while `requestTraceId` will be **two different UUIDs** because the filter runs for each new request.

**Step 4 — a different client sending no cookie:**

```bash
curl -s http://localhost:8080/lab/state
```

Expect `"sessionPresent":false` and `"language":null`. This simulates another client **not carrying the same session identifier**, not proof that the system authenticated two distinct users.

**Step 5 — invalidate the session:**

```bash
curl -i -b session-cookies.txt \
  -X POST http://localhost:8080/lab/end

curl -s -b session-cookies.txt http://localhost:8080/lab/state
```

Expect the final request not to retrieve `demo.uiLanguage` from the old session. The cookie jar may still retain the old ID, yet the server considers that session invalid.

**Remember:** opening another terminal/curl without `-b session-cookies.txt` gives the server no basis to continue any prior session; sharing an IP address **does not** mean sharing a session.

## 7. Testing with MockMvc rather than relying solely on manual JSON checks

With `spring-boot-starter-test` in test scope, write tests proving that request-local IDs change while session values persist:

**`src/test/java/com/example/demo/StateLabControllerTest.java`**

```java
package com.example.demo;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class StateLabControllerTest {

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    @Test
    void sessionValueSurvivesButRequestIdChanges() throws Exception {
        MvcResult first = mvc.perform(
                post("/lab/language").param("value", "vi"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.language").value("vi"))
            .andExpect(jsonPath("$.sessionPresent").value(true))
            .andReturn();

        MockHttpSession session = (MockHttpSession)
            first.getRequest().getSession(false);
        assertNotNull(session);

        String idA = mapper.readTree(
            first.getResponse().getContentAsString()
        ).get("requestTraceId").asText();

        MvcResult second = mvc.perform(
                get("/lab/state").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.language").value("vi"))
            .andExpect(jsonPath("$.sessionPresent").value(true))
            .andReturn();

        String idB = mapper.readTree(
            second.getResponse().getContentAsString()
        ).get("requestTraceId").asText();

        assertNotEquals(idA, idB);
    }

    @Test
    void readOnlyRequestDoesNotCreateSession() throws Exception {
        MvcResult result = mvc.perform(get("/lab/state"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.sessionPresent").value(false))
            .andReturn();

        assertNull(result.getRequest().getSession(false));
    }

    @Test
    void stateIsNotSharedWithoutSameSession() throws Exception {
        MvcResult first = mvc.perform(
                post("/lab/language").param("value", "en"))
            .andExpect(status().isOk())
            .andReturn();

        MockHttpSession session = (MockHttpSession)
            first.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/lab/state").session(session))
            .andExpect(jsonPath("$.language").value("en"));

        mvc.perform(get("/lab/state"))
            .andExpect(jsonPath("$.sessionPresent").value(false));
    }

    @Test
    void invalidLanguageIsRejectedBeforeSessionCreation()
            throws Exception {
        MvcResult result = mvc.perform(
                post("/lab/language").param("value", "unknown"))
            .andExpect(status().isBadRequest())
            .andReturn();

        assertNull(result.getRequest().getSession(false));
    }
}
```

Run:

```bash
./mvnw test
```

With the right Spring Boot 3.x, Spring Web/Starter Test dependencies, and files above, **all four tests are expected to pass**. This is a **designed exercise for learners to run**, not a claim of test execution against an existing repository. If errors occur, verify you enabled Spring MVC rather than WebFlux, test packages match, the filter class is component-scanned, and the test passes the **same `MockHttpSession`** to the second request.

To test `POST /lab/end`, add checks confirming the session is invalidated and a follow-up request no longer sees old values; note that in MockMvc an invalidated `MockHttpSession` must not be casually reused as an active session.

## 8. `@RequestScope` and `@SessionScope` in Spring IoC

In addition to Servlet attributes, Spring supports **bean scopes** tied to request and session lifecycles:

```java
// Illustrative snippet; each class must reside in its own file.
@Component
@RequestScope
public class RequestContext {
    private final String traceId =
        java.util.UUID.randomUUID().toString();

    public String traceId() {
        return traceId;
    }
}

@Component
@SessionScope
public class SessionPreferences {
    private String language = "vi";

    public String language() {
        return language;
    }

    public void language(String language) {
        this.language = language;
    }
}
```

This is a **snippet**, not two top-level classes placed in a single `.java` file. Requires importing `org.springframework.stereotype.Component`, `org.springframework.web.context.annotation.RequestScope`, and `SessionScope`.

- **`@RequestScope`**: one bean instance per current request; other requests get different instances. Suitable for request-processing data.
- **`@SessionScope`**: one bean instance bound to the HTTP session, reused across requests in that session until the session ends.
- These convenience scope annotations create **scoped proxies** by default in the appropriate proxy mode, allowing a singleton bean to inject them so each method call delegates to the current request/session instance.
- Never treat `@SessionScope` as inherently thread-safe; **requests sharing a session can still run concurrently**. If mutable state is read and written by parallel requests, add proper synchronization or atomic operations in an appropriate store.
- **“Scope 'request' is not active”** errors occur when a request-scoped bean is accessed outside an active web request, such as in a background job or manually spawned thread without context propagation. Never retain proxies/request objects for execution after the HTTP request finishes.

In many APIs, local variables and immutable DTOs are sufficient; do not introduce request/session-scoped beans just because Spring provides the annotations.

## 9. Do `Model`, `@SessionAttributes`, and flash attributes differ?

### 9.1. `Model` is for rendering the current request

`@Controller` methods often populate `Model`:

```java
@GetMapping("/hello")
public String show(Model model) {
    model.addAttribute("message", "Hello");
    return "hello";
}
```

This is **only a snippet**, omitting the controller class and template. `Model` data helps render the **current request's view**, and does not automatically persist across future requests. Reloading in the browser creates/populates a fresh model.

### 9.2. `@SessionAttributes` is for intentional controller workflows

Spring MVC's `@SessionAttributes("draft")` on a controller class stores specified model attributes **temporarily in the HTTP session** across requests, commonly for multi-step form drafts. When the flow completes, call `SessionStatus.setComplete()` so Spring stops managing those attributes. It is **not the same** as a `@SessionScope` bean:

- `@SessionAttributes` manages **controller model attributes**, typically for a form workflow.
- `@SessionScope` manages **Spring IoC bean lifecycles**.
- `HttpSession` provides direct read/write access to attributes by name.

Avoid putting full entities or secrets into `@SessionAttributes` by default; sessions can live long, undergo serialization, or be modified concurrently by two tabs.

### 9.3. Flash attributes: surviving temporarily across a redirect

Example after a successful POST:

```java
@PostMapping("/save")
public String save(RedirectAttributes redirect) {
    redirect.addFlashAttribute("notice", "Saved successfully");
    return "redirect:/result";
}
```

This is an illustrative snippet, not an endpoint with real persistence logic. `addFlashAttribute` passes a message across a redirect in the **Post/Redirect/Get** pattern. Spring MVC usually stores flash data temporarily **in the session** while managing its lifecycle and target request automatically; it should not be treated as long-term session preferences.

Clear distinctions:

- **Request attribute:** serves only the current request.
- **Flash attribute:** short-lived message across a redirect, intended for the **exact target** next request.
- **Session attribute:** persists until modified, removed, or expired.
- **Database record:** durable per business rules, independent of sessions/cookies.

Flash attributes can misbehave when multiple requests overlap (polling, asset loads, concurrent redirects), so never use them to carry critical transaction state or multi-step payloads.

## 10. What goes in request, session, or database?

| Data | Preferred location | Reason |
| --- | --- | --- |
| Request/correlation ID | Request context or tracing context | Unique per request; must not carry over like user data |
| Validation results and intermediate variables | Local variable, `Model`/request attribute | Needed only during current request handling |
| Temporary display language/units | Session (or DB for long-term preference) | May need to persist across multiple requests |
| Session authentication | Spring Security + standard session management | Never invent custom password/token storage in sessions |
| Small shopping cart or short wizard | Controlled session, or DB if durability is required | Consider size, concurrency, timeout, and multi-device access |
| Orders, balances, access rights, canonical prices | Authoritative database/service | Never trust mutable session data as durable/authoritative |
| “Saved” banner across PRG | Flash attribute | Consumed once after redirect |
| Identity context for a single request | Request-scoped context, immutable security principal | Never use static fields or mutable controller instance fields |

**Minimize session data**: many sessions holding large objects pressure memory or distributed stores; never store uploaded files, large response bodies, or database connections in sessions. Never store non-serializable objects if the session backend requires serialization. Avoid placing passwords, high-value access tokens, or sensitive PII in sessions unless genuinely necessary; rely on security framework mechanisms.

## 11. Common errors and subtle risks

### 11.1. Storing the current user in a singleton controller field

```java
// ANTI-PATTERN: A Spring @RestController is normally a singleton.
@RestController
class BadController {
    private String currentUser;

    @GetMapping("/set-user")
    String setUser(@RequestParam String name) {
        currentUser = name;
        return currentUser;
    }
}
```

This is a dangerous example, **never use it in real code**. The `currentUser` field is shared across all requests and users and can be overwritten concurrently. Replace it with method parameters, local variables, request scope, or querying the security principal/session appropriately. **A singleton controller is not a per-session controller.**

### 11.2. Unsynchronized counters on a session

Two tabs in the same browser normally share the same session cookie. Both can fire requests concurrently:

```text
Session: counter = 4
Request A reads counter = 4
Request B reads counter = 4
Request A writes counter = 5
Request B writes counter = 5
Expected 6, yet actual result is 5
```

Even though the container provides a session access API, it **does not make a read–modify–write attribute sequence atomic**. Avoid using mutable `Integer` counters in a session for transactional counts; use storage with proper concurrency control or atomic primitives suited to your environment and distributed constraints. With a multi-node session store, in-JVM `synchronized`/`AtomicInteger` is still insufficient.

### 11.3. Confusing browser tabs, HTTP connections, and sessions

- **Tab A and Tab B** in the same browser profile usually share session cookies for the same site; there is no automatic per-tab session isolation.
- **HTTP keep-alive** reuses a network connection for multiple requests; it does not mean “same user session”.
- **Changing IPs** does not necessarily change sessions; **sharing an IP** does not guarantee sharing a session.
- **Request IDs** used for tracing are neither session IDs nor authentication credentials.
- **Load balancer connections** to backend nodes do not automatically synchronize session state.

### 11.4. Login and session fixation

When users log in, applications must defend against **session fixation** (an attacker fixes an ID beforehand and tricks the user into authenticating under that ID). Spring Security includes session fixation protection: rotating the session ID on modern Servlet containers (such as `changeSessionId`) or applying an equivalent policy. Never disable this protection. On logout, use Spring Security's standard mechanisms to invalidate the session and clear authentication/security contexts and cookies per config.

An authenticated session is not merely a `"loggedIn"` string placed in the session by hand. Access control must be decided by the authentication/authorization system; every resource must verify permissions rather than relying on an “unguessable” session ID alone.

### 11.5. Session hijacking, cookies, and CSRF

Session cookies act as credentials: enforce **HTTPS + `Secure` + `HttpOnly` + appropriate `SameSite`**, restrict domain/path, and keep session IDs out of URLs, referrers, analytics, and logs. If the app uses cookie-based authentication, POST/PUT/PATCH/DELETE requests need CSRF protection matching the threat model (typically Spring Security CSRF). XSS can trigger actions within an active session even when `HttpOnly` blocks cookie reads; apply proper output encoding and CSP.

**The Section 6 demo does not configure Spring Security**, so never deploy it publicly as a real data-mutating endpoint. In production, configure the security filter chain, authentication/authorization, CSRF tokens, and dedicated tests for session-mutating POSTs.

### 11.6. Session timeouts and multi-instance distribution

On a single instance, the embedded servlet container normally manages sessions in the local process. When running multiple replicas:

```text
Request 1 -> Node A (session lives only on A)
Request 2 -> Node B (does not see session unless B shares a store)
```

Load balancer **sticky sessions** can help, yet do not replace shared session storage (a crashed node or rebalancing still loses state). With Spring Session, repositories such as Redis/JDBC let multiple nodes access the same session. When doing so, evaluate:

- TTL/timeouts and deletion mechanics.
- Serialization, payload size, and compatibility across class upgrades.
- Concurrent updates, lost updates, and session save policies.
- Store security, TLS connectivity, authentication, and outage handling.
- Avoiding turning the session into the source of truth for transactional business data.

**Sessions are not databases**: never fake data durability by stretching timeouts to days and storing entire workflows or orders in the session.

## 12. Notes for WebFlux applications

The Java examples in Section 6 use the **Servlet stack**. Spring WebFlux uses **`WebSession`** and the reactive stack's request context (`ServerWebExchange`), not `jakarta.servlet.http.HttpSession`.

The concepts remain parallel:

- The current request holds attributes on `ServerWebExchange`.
- Web sessions are accessed asynchronously via `exchange.getSession()`, following reactive runtime session semantics.
- Spring WebFlux supports request/session-scoped components in supported framework areas, yet **never mix Servlet APIs with Netty WebFlux**.
- Reactor has its own context propagation; never assume a `ThreadLocal` tied to an HTTP request survives across every operator or scheduler.
- When using reactive Spring Session, repositories and configuration differ from Servlet; always follow Spring Session's reactive documentation.

Conceptual snippet (inside a WebFlux handler):

```java
// Inside a reactive handler, not the MVC controller from Section 6.
Mono<String> result = exchange.getSession()
    .map(session -> {
        session.getAttributes().put("uiLanguage", "vi");
        return session.getId();
    });
```

This snippet illustrates the API only, omitting the `exchange` variable and imports; **it does not compile standalone**. Real apps must never return the session ID to clients via JSON; here it merely shows `WebSession` exposes an ID and attributes, so replace `return session.getId()` with a non-sensitive value in production code.

## 13. Checklist for choosing scope and verifying behavior

- [ ] Does the value genuinely need to live across **multiple requests**? If not, keep it in a local variable or request attribute.
- [ ] Is `getSession(true)` called when only reading? If so, switch to `getSession(false)` to avoid unnecessary sessions.
- [ ] Do sessions store small, properly scoped values without raw credentials, large files, or DB connections?
- [ ] Is any request-scoped bean accessed outside a request context or from background threads?
- [ ] Does any singleton/controller have mutable fields holding user-specific state?
- [ ] Could two tabs sharing a session overwrite state or cause a race?
- [ ] Are session timeout, invalidation, `Secure`/`HttpOnly`/`SameSite` cookies, and session fixation designed properly?
- [ ] Are cookie-auth POSTs protected against CSRF and covered by authorization checks?
- [ ] Are flash attributes used for one-time post-redirect banners instead of lingering session values?
- [ ] With multiple nodes, are shared session stores, TTLs, serialization, and lost updates accounted for?
- [ ] Do tests reuse the same session across requests A/B and omit the session on request C to verify boundaries precisely?
- [ ] Do logs and tracing include request IDs without leaking session IDs or session cookies?

## 14. Self-check questions

**Question 1:** Does `request.setAttribute("traceId", "R1")` on the first request let the second request see `"R1"`?  
**Answer:** No; each request has its own request attributes. If you need correlation across requests, propagate identifiers via a proper tracing layer rather than expecting request attributes to survive.

**Question 2:** Why is `request.getSession(false)` important on read-only GET endpoints?  
**Answer:** It returns an existing session or `null`, without creating a new session for clients that have none.

**Question 3:** Does the `JSESSIONID` cookie contain the `Cart` or `UserPreferences` object placed in `HttpSession`?  
**Answer:** Normally the cookie holds only the session identifier; session data is managed server-side or via a session repository.

**Question 4:** Do two tabs in the same browser get two separate `@SessionScope` beans?  
**Answer:** Usually no if both tabs share the same session cookie; they hit the same session bean instance and can execute concurrently.

**Question 5:** Can a `private String currentUser` field inside a `@RestController` remember the current user?  
**Answer:** No; controllers are singletons by default, so data would leak and collide across users and requests.

**Question 6:** When a user reloads the page, does `Model.addAttribute("message", "...")` from the previous request remain automatically?  
**Answer:** No; `Model` serves rendering the current request, unless an explicit mechanism like `@SessionAttributes` or flash attributes is used.

**Question 7:** Does logging out by deleting the browser cookie immediately delete session data on the server?  
**Answer:** Not guaranteed. The server must invalidate the session and run proper logout handling; cookies and server-side sessions have separate lifecycles.

**Question 8:** If a load balancer routes the next request to a different node, is the session always readable?  
**Answer:** No. You need sticky sessions or a shared store like Spring Session Redis/JDBC, plus proper recovery handling.

**Question 9:** Do HTTP keep-alive and session authentication mean the same thing?  
**Answer:** No. Keep-alive reuses a TCP/HTTP connection; sessions link multiple requests via IDs/cookies.

**Question 10:** Should you include the session ID in JSON responses for debugging?  
**Answer:** No. Session IDs are sensitive credentials and pose hijacking risks if leaked; use a separate random request ID for tracing.

## 15. Official references

- Spring Framework — **Bean Scopes** (request/session scope and scoped proxies): https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework — **@SessionAttributes**: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattributes.html
- Spring Framework — **Flash Attributes**: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/flash-attributes.html
- Spring Boot — **Common Application Properties** (session timeout, cookie flags): https://docs.spring.io/spring-boot/appendix/application-properties/
- Spring Security — **Session Management and Session Fixation Protection**: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — **CSRF Protection**: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Session — **HttpSession backed by Redis**: https://docs.spring.io/spring-session/reference/guides/java-redis.html
- Jakarta Servlet API — **HttpServletRequest** and **HttpSession**: https://jakarta.ee/specifications/servlet/

**Conclusion:** Use **request-local state** for data meaningful only within a single request, **HTTP sessions** when values truly must span multiple requests in the same session, and a **database/service** for durable business data. Cookies merely identify the session; they do not turn a request into a session, nor do they replace authentication or authorization. Test along the request–session–client boundaries and protect sessions as sensitive credentials.
