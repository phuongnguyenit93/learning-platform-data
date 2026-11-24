# Request Scope, Session Scope, and Shared Data Across Requests in Spring MVC

## 1. From the Nature of HTTP to the State Management Problem

An HTTP request is an independent exchange: the client sends a method, URI, headers, and optionally a body; the server processes it and returns a status, headers, and body. HTTP **does not automatically carry all Java variables from a previous request to the next request**. Meanwhile, web applications often need to remember data:

- **Within a single request:** tracking IDs, authenticated tenant, intermediate data computed by a filter or interceptor.
- **Across multiple requests from the same user/session:** language selection, current step of a wizard, a small shopping cart, or UI preferences.
- **Across requests from all users:** read-only configuration, feature catalog, application-wide counters, or a shared cache.
- **Across restarts, across multiple servers, or over long periods:** user profiles, orders, shopping carts requiring durability, records in a database or external store.

Spring MVC provides **Servlet request/session** and **Spring bean scopes** to represent the corresponding lifecycles. However, "scope" does not mean "data is automatically persisted durably"; you must choose the right owner, lifetime, and storage location.

Imagine three requests:

```text
Browser A                           Server
   | GET /api/scope/request  -------> request R1
   |                                  @RequestScope -> Bean R1
   | <------- response --------------- R1 ends
   |
   | GET /api/scope/session  -------> request R2, session S-A
   |                                  @SessionScope -> Bean S-A
   | <------- Set-Cookie session-id -- session S-A remains alive
   |
   | GET /api/scope/session + cookie -> request R3, session S-A
   |                                  @RequestScope -> new Bean R3
   |                                  @SessionScope -> existing Bean S-A
   | <------- response --------------- R3 ends

Browser B
   | GET /api/scope/session  -------> request R4, session S-B
                                      Bean S-B differs from S-A

@ApplicationScope / singleton:
the same web application can be used by R1, R2, R3, R4
(but is not shared by default with another JVM or deployment node).
```

**Lesson objectives:** distinguish the lifetime and visibility scope of data, use `@RequestScope`/`@SessionScope`/`@ApplicationScope` properly, avoid confusing them with `HttpSession`/request attributes, understand session IDs and cookies, test with Java 17+ Spring MVC, and choose safe state storage strategies in multi-instance systems.

## 2. Distinguishing Servlet Scopes from Spring Bean Scopes

There are two layers of concepts that both use the words "request" and "session":

1. **Servlet attributes:** key-value pairs stored in `HttpServletRequest`, `HttpSession`, or `ServletContext`, typically set via `setAttribute(name, value)`.
2. **Spring bean scopes:** the container decides whether a bean definition creates one instance per request/session/application or uses one shared instance.

The two layers have a lifecycle relationship, but **they are not synonymous APIs**. When you call `request.setAttribute("trace", "abc")`, Spring does not automatically turn that string into a `@RequestScope` bean. When you annotate a bean with `@SessionScope`, you do not need to manually call `session.setAttribute` to register the bean; Spring manages the instance through the container's scope.

| Scope | Value exists within | Typically used by | Crosses to a new request? | Shared across users? |
| --- | --- | --- | --- | --- |
| Method local variable | A single method invocation | Any Java method | No | No |
| Servlet **request attribute** | A single Servlet request | Filter, interceptor, controller | No, unless the same request is forwarded/dispatched | No |
| Spring **request-scoped bean** | A single request in a web-aware context | Injected controller/service | No | No |
| Servlet **session attribute** | HTTP session | Controller, auth/session manager | Yes, if the new request resolves the same valid session | No by default |
| Spring **session-scoped bean** | HTTP session | Component holding per-session state | Yes, while the same session and state remain valid | No by default |
| Spring **application-scoped bean** | A single `ServletContext` | Web app-level data component | Yes | Yes, within the same ServletContext |
| Spring **singleton bean** | A single Spring IoC container | Typical controller, service, repository | Yes | Yes, within the same container |
| Database/shared cache | Per key, TTL, and business logic | Repository/service/cache | Yes | Depends on key and authorization |

**Common point of confusion:** `@ApplicationScope` and a Spring singleton can have a similar lifecycle in a simple Spring Boot web app, but their contracts are not identical. A singleton is **one instance per bean definition in a Spring IoC container**; application scope is **one instance per ServletContext**. When there are multiple Spring ApplicationContexts or multiple web applications, the behavior can differ.

For **Spring WebFlux**, the session abstraction is `WebSession`, not Servlet `HttpSession`. The examples below are strictly for Spring MVC Servlet; do not copy the imports as-is into WebFlux.

## 3. Request Scope: Data Needed Only Within One HTTP Request

### 3.1. Servlet Request Attributes

`HttpServletRequest#setAttribute` stores an object under a key in the **current request**:

```java
// A Servlet Filter or HandlerInterceptor sets the information:
request.setAttribute("traceId", "trace-42");

// A downstream component reads it back:
String traceId = (String) request.getAttribute("traceId");

// Can be removed:
request.removeAttribute("traceId");
```

This is a **Java fragment**, assuming `request` is the `jakarta.servlet.http.HttpServletRequest` being processed. Values do not automatically survive an HTTP redirect (a redirect creates a new request). When a Servlet **forwards** a request to another resource, the request can continue to be used and its attributes remain meaningful; distinguish forward from redirect.

In a controller, instead of using the Servlet API directly, you can declare:

```java
@GetMapping("/trace")
String trace(@RequestAttribute("traceId") String traceId) {
    return traceId;
}
```

`@RequestAttribute` on a parameter retrieves **an attribute that was set earlier**. It does not directly read a JSON body, query parameter, or HTTP header of the same name. If the data may be absent, use `@RequestAttribute(name="traceId", required=false)` or `Optional<String>`, and provide clear fallback logic.

This is useful for server-computed data within a request: correlation IDs, tenant resolution results, or authenticated and normalized information. If an attribute relates to authentication/authorization, its trusted source must be verified; an arbitrary header from the client **does not automatically become an authenticated identity**.

### 3.2. Spring `@RequestScope` Bean

A request-scoped bean is created when Spring needs it within an eligible web request and is kept for reuse **within that request**. A different request creates a new target bean.

```java
import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
class RequestMarker {
    private final String id = UUID.randomUUID().toString();

    String getId() {
        return id;
    }
}
```

This is a complete class in a Spring MVC project (used in the application example in Section 8). When two method calls invoke `getId()` on the same scoped bean within the **same request**, they receive the same ID; on a new request, a new ID is normally returned. UUID is only for observing the lifecycle and must not be treated as a security token or user identifier.

**Do not confuse** `@RequestScope` with `@RequestAttribute`:

| `@RequestScope` | `@RequestAttribute` |
| --- | --- |
| Spring annotation placed on a **bean class/factory method** | Spring MVC annotation placed on a **handler parameter** |
| Spring IoC manages the **bean instance** lifecycle | MVC argument resolver reads an object by key from the Servlet request |
| Can inject a proxy into a singleton bean | Requires the attribute to be set before the handler resolves it |
| Suitable for a component holding the context of a request | Suitable for passing a short, clearly keyed value from a filter/interceptor |

If you only need a single `traceId` string, you do not have to create an entire scoped bean. Conversely, when a request object has multiple dependencies and needs to be injected across several layers, a request-scoped bean is easier to manage.

## 4. Session Scope: Multiple Requests Can Share State of the Same Session

### 4.1. HTTP Session and Session ID

`HttpSession` is a Servlet container abstraction. In the standard mechanism, the server creates a session and issues the browser a **session identifier** (for example, the `JSESSIONID` cookie). Subsequent requests carry the valid session ID so the server recognizes the same session.

```text
Browser                 Server
POST /preferences
  no cookie              create Session S-1
       ----------------->
  <--------------------- Set-Cookie: JSESSIONID=<opaque-id>

GET /preferences
  Cookie: JSESSIONID=...  look up Session S-1
       ----------------->
  <--------------------- read stored language

Another browser / incognito
  no valid cookie         new Session S-2 (if the app needs one)
       ----------------->
```

The cookie typically stores the **session ID**, not the entire Java object inside the session. Attributes in `HttpSession` typically live on the server/container side or in an external session store. This differs from cookie designs that store client-readable data or self-contained JWTs.

A session can become invalid due to timeout, logout, invalidation, loss of data in the session store, or application redeployment. **Never treat the presence of a `JSESSIONID` cookie as proof of a valid or authenticated session.**

### 4.2. Reading and Writing Servlet Session Attributes

```java
@PostMapping("/preferences")
String save(@RequestParam String language, HttpSession session) {
    session.setAttribute("language", language);
    return "saved";
}

@GetMapping("/preferences")
String read(
        @SessionAttribute(name = "language", required = false)
        String language) {

    return language == null ? "unset" : language;
}
```

The snippets above are **controller method fragments** requiring the corresponding imports. `@SessionAttribute` reads an attribute already present in the HTTP session; `required=false` allows it to be absent. To write or remove attributes, `HttpSession#setAttribute` / `removeAttribute` or `WebRequest` is typically used.

**Be careful with session creation:**

```java
// May create a session if one does not exist yet:
HttpSession session = request.getSession();

// Only read an existing session, do not create a new one:
HttpSession existing = request.getSession(false);
if (existing != null) {
    Object value = existing.getAttribute("language");
}
```

Here `request` is an `HttpServletRequest`. Injecting an `HttpSession` parameter into a handler or accessing a `@SessionScope` bean can cause a session to be created when none exists; when an endpoint needs to **only check existing state**, use `getSession(false)` to avoid creating unnecessary sessions.

When you want to log out or discard all data associated with a session:

```java
HttpSession existing = request.getSession(false);
if (existing != null) {
    existing.invalidate();
}
```

`invalidate()` terminates the session; it does not just remove a single key. If you only want to clear a language selection, `existing.removeAttribute("language")` is more appropriate. In systems using Spring Security, logout, session fixation, and concurrent session control should go through the official security management mechanisms rather than treating an arbitrary `invalidate()` call as a complete logout flow.

### 4.3. Spring `@SessionScope` Bean

`@SessionScope` is a shortcut for `@Scope("session")` and **creates a class-based scoped proxy by default** (TARGET_CLASS). The actual target bean is created per HTTP session and reused within that same session.

```java
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.SessionScope;

@Component
@SessionScope
class SessionPreferences {
    private String language = "vi";

    synchronized String getLanguage() {
        return language;
    }

    synchronized void setLanguage(String language) {
        this.language = language;
    }
}
```

This is an illustrative class managing preferences for a session. Synchronization protects the two methods within the **same JVM and the same bean instance**, but does not guarantee multi-node synchronization when the session object is serialized/copied across Redis or another backend. For data shared across servers, a consistency design suited to the storage backend is required.

Spring does not automatically write every mutable field of a session bean to a database. In an external session store, the object may require **serialization** and change-detection aligned with the `Spring Session` configuration. A mutable session bean implementation is not automatically suitable for clustering.

## 5. Why Can a Session-Scoped Bean Be Injected into a Singleton Controller?

Spring `@Controller`/`@Service` beans are normally **singletons**, created once per Spring IoC container. If a real object with a shorter request/session lifecycle were injected directly into a singleton, a *scope mismatch* would occur: the singleton would hold a reference to one instance while a later request/session needs a different instance.

The standard solution is a **scoped proxy**:

```text
Singleton controller (one instance)
       |
       +--- injected RequestMarker proxy -------------+
       |                                              |
       |  Request R1: proxy.getId() -> RequestMarker-R1|
       |  Request R2: proxy.getId() -> RequestMarker-R2|
       |                                              |
       +--- injected SessionPreferences proxy --------+
                                                      |
          Session S-A: proxy.getLanguage() -> Bean S-A
          Session S-B: proxy.getLanguage() -> Bean S-B
```

`@RequestScope` and `@SessionScope` use `proxyMode=ScopedProxyMode.TARGET_CLASS` by default. The proxy can be injected once into the singleton; each method call within a valid request delegates to the **target of the current scope**.

Example of controller constructor injection:

```java
@RestController
class ContextController {
    private final RequestMarker requestMarker;
    private final SessionPreferences preferences;

    ContextController(
            RequestMarker requestMarker,
            SessionPreferences preferences) {
        this.requestMarker = requestMarker;
        this.preferences = preferences;
    }

    @GetMapping("/context")
    String context() {
        return requestMarker.getId() + ":" + preferences.getLanguage();
    }
}
```

This is an **illustrative class**, without full imports/config. `ContextController` remains a singleton; the objects received by its constructor are scoped proxies, **not the same target state for every user**.

Keep the following in mind:

1. A class-based proxy normally needs to subclass the target class. **Do not declare a scoped bean class as `final` or mark proxied methods as `final`** when using TARGET_CLASS, because CGLIB cannot override them.
2. If the bean is accessed outside an eligible HTTP request (for example, in a background job), Spring may throw a *scope not active* error because it cannot locate the current request/session.
3. An alternative is to inject `ObjectProvider<ScopedBean>` and call `getObject()` only inside a valid request; this does not make request scope global.
4. Do not retain a **target scoped object** or `HttpServletRequest` as a field in a singleton/static/global map after the request/session ends.
5. Plain `@Scope("request")` may not enable a proxy by default, unlike the `@RequestScope` shortcut. Check the exact annotation API and configured proxy mode.

## 6. Application Scope, Singleton, Prototype, and Shared Data

### 6.1. `@ApplicationScope`

An `@ApplicationScope` bean has a lifecycle tied to the web application's `ServletContext`. Requests from different clients **within the same ServletContext** can share the instance.

```java
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.ApplicationScope;

@Component
@ApplicationScope
class ApplicationCounter {
    private final AtomicLong total = new AtomicLong();

    long increment() {
        return total.incrementAndGet();
    }
}
```

`AtomicLong` makes integer increment operations thread-safe when multiple threads share the instance in one JVM. It **does not** provide a cluster-wide total when two JVMs run on two independent nodes. For cluster-wide counters, use atomic operations on a database, Redis, or an appropriate metrics system.

### 6.2. Singleton Does Not Mean One Instance for the Entire Internet

`@Service`, `@Component`, and `@Controller` are singletons by default:

```java
@Service
class CatalogService {
    // Good: other dependencies are injected and methods do not hold user state.
}
```

A singleton is **one instance per bean definition in a Spring container**, not a single instance across multiple service instances, pods, or JVMs. Never put a mutable `String currentUserId` field in a singleton controller/service: two requests can overwrite each other, leading to cross-user data leakage.

Instead, obtain the authenticated user ID via parameters/`Principal`, keep request/session context in its proper lifecycle, and persist durable state in an appropriate store.

### 6.3. Prototype Is Also Not Equivalent to Request Scope

`@Scope("prototype")` creates a new instance **when the Spring container resolves the bean**. If a singleton injects a prototype directly into its constructor once, the singleton will hold **that one prototype instance injected when the singleton was created**. It does not mean every HTTP request or every method call automatically gets a new prototype.

If you need a new object on each use, call `ObjectProvider.getObject()`/a factory at the appropriate time; if you need exactly one object per HTTP request, prefer `@RequestScope`.

### 6.4. Where Should Shared Application Data Live?

| Data type | Recommendation |
| --- | --- |
| Read-only config, immutable objects, stateless services | Singleton bean / configuration properties |
| Shared mutable values within one JVM | Application/singleton bean with concurrency control |
| Shared cache across multiple application instances | Redis / distributed cache or an appropriate caching service |
| Business data requiring durability and transactions | Database |
| System counters / metrics | Metrics backend, database atomic operations, or an aggregation mechanism |
| Per-user shopping cart needing to survive logout/devices | Domain storage keyed by user ID, not just HttpSession |
| UI language only for the current request | LocaleResolver, `Accept-Language`, or a validated query/header per contract |
| Per-user language preference across many requests | Session, appropriately configured cookie, or user profile DB |

## 7. Different "Data-Holding" Mechanisms in Spring MVC

### 7.1. `@RequestAttribute` vs `@SessionAttribute`

These two annotations on **controller parameters** only **read attributes**:

```java
@GetMapping("/context")
String context(
        @RequestAttribute(name = "trace", required = false) String trace,
        @SessionAttribute(name = "language", required = false) String language) {

    String left = trace == null ? "none" : trace;
    String right = language == null ? "none" : language;
    return left + ":" + right;
}
```

This is a controller method fragment. `trace` belongs only to the request currently being processed; `language` may come from a previous request's session. These annotations do not declare bean lifecycles and do not write attributes automatically.

### 7.2. `@SessionAttributes` — With an "s", for Model Workflows

`@SessionAttributes` is placed **on the controller class**, telling Spring MVC to automatically store certain **model attributes** in the session for use across multiple steps of a form/controller. It **differs** from `@SessionAttribute` (which reads an existing session key).

```java
@Controller
@SessionAttributes("draft")
class DraftController {

    @ModelAttribute("draft")
    DraftForm draft() {
        return new DraftForm();
    }

    @GetMapping("/draft")
    String start() {
        return "draft/form";
    }

    @PostMapping("/draft/finish")
    String finish(
            @ModelAttribute("draft") DraftForm draft,
            SessionStatus status) {

        // Persist the draft according to business logic before completing.
        status.setComplete();
        return "redirect:/draft/done";
    }
}
```

This is an **MVC form fragment**, requiring an application-defined `DraftForm` type, templates/views, and imports; it is not a standalone runnable program. `SessionStatus#setComplete()` ends **the management of model attributes declared by @SessionAttributes** in that controller; it **does not invalidate the entire HTTP session** and does not remove any other attributes.

### 7.3. Flash Attributes — Only for the Next Request After Redirect

In a Post-Redirect-Get flow:

```java
@PostMapping("/preferences")
String save(RedirectAttributes redirects) {
    redirects.addFlashAttribute("notice", "Preferences saved");
    return "redirect:/preferences";
}
```

A flash attribute is typically kept **temporarily** in the session by `FlashMapManager`, then moved into the model of the request receiving the redirect and removed from flash storage. It is **not a long-lived session attribute**. Use it for short success notices, not as a database.

If you use `redirects.addAttribute("notice", "...")` instead of `addFlashAttribute`, the data may be converted into a query/path parameter in the URI — you must consider logging, browser history, URL length, and sensitive data.

### 7.4. `RequestContextHolder` — Thread-Bound Context

`RequestContextHolder` can provide the `RequestAttributes` of the current request via a thread-bound mechanism:

```java
RequestAttributes attributes = RequestContextHolder.currentRequestAttributes();
Object traceId = attributes.getAttribute("traceId", RequestAttributes.SCOPE_REQUEST);
```

This snippet is a **fragment**, requiring imports for `org.springframework.web.context.request.RequestAttributes` and `RequestContextHolder`. It is not an application-wide data store and can throw an exception if the current thread has no request context. `@Async`, custom executors, and `CompletableFuture` do not automatically guarantee context propagation to another thread. Avoid designing services that depend heavily on thread-local web context; pass required data through explicit parameters whenever possible.

## 8. Spring Boot 3.x + Java 17 Application: Observing All Three Scopes

The application below demonstrates at the same time:

1. `@RequestScope`: the same request receives the same ID; a new request gets a different ID.
2. `@SessionScope`: language selection and visit count persist when reusing the same HTTP session.
3. `@ApplicationScope`: a shared counter for requests hitting **one ServletContext**.
4. `@RequestAttribute`: a value provided by a Servlet Filter.
5. `@SessionAttribute`: reading a key stored directly in the Servlet session.

This uses **Spring Boot 3.x / Spring Framework 6.x on Servlet MVC**. `spring-boot-starter-web` includes Tomcat and standard MVC; the application does not need Redis or a database.

### 8.1. Dependencies

In a Gradle project that already has the Boot plugin, dependency management, repositories, and Java toolchain configured:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **`build.gradle` configuration snippet**, not a standalone build file. Do not invoke `javac` directly without a classpath for this project; run it through Spring Boot's Gradle/Maven tooling.

### 8.2. Single Java File Containing Application, Beans, and Controller

Create **`src/main/java/demo/scope/ScopeApplication.java`**:

```java
package demo.scope;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import java.io.IOException;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.SessionAttribute;
import org.springframework.web.context.annotation.ApplicationScope;
import org.springframework.web.context.annotation.RequestScope;
import org.springframework.web.context.annotation.SessionScope;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class ScopeApplication {

    public static void main(String[] args) {
        SpringApplication.run(ScopeApplication.class, args);
    }

    @Bean
    OncePerRequestFilter serverTagFilter() {
        return new OncePerRequestFilter() {
            @Override
            protected void doFilterInternal(
                    HttpServletRequest request,
                    HttpServletResponse response,
                    FilterChain chain) throws ServletException, IOException {

                // Set by the server side, not read from a client-supplied header.
                request.setAttribute("serverTag", "from-filter");
                chain.doFilter(request, response);
            }
        };
    }
}

@Component
@RequestScope
class RequestMarker {
    private final String id = UUID.randomUUID().toString();

    String getId() {
        return id;
    }
}

@Component
@SessionScope
class SessionPreferences {
    private String language = "vi";
    private int visits;

    synchronized String getLanguage() {
        return language;
    }

    synchronized void setLanguage(String language) {
        this.language = language;
    }

    synchronized int nextVisit() {
        return ++visits;
    }
}

@Component
@ApplicationScope
class ApplicationCounter {
    private final AtomicLong total = new AtomicLong();

    long next() {
        return total.incrementAndGet();
    }
}

@RestController
@RequestMapping("/api/scope")
class ScopeController {
    private final RequestMarker requestMarker;
    private final SessionPreferences preferences;
    private final ApplicationCounter counter;

    ScopeController(
            RequestMarker requestMarker,
            SessionPreferences preferences,
            ApplicationCounter counter) {
        this.requestMarker = requestMarker;
        this.preferences = preferences;
        this.counter = counter;
    }

    @GetMapping("/request")
    Map<String, String> requestInfo(
            @RequestAttribute("serverTag") String tag) {

        return Map.of(
                "first", requestMarker.getId(),
                "second", requestMarker.getId(),
                "tag", tag);
    }

    @GetMapping("/session")
    Map<String, Object> sessionInfo() {
        return Map.of(
                "language", preferences.getLanguage(),
                "visits", preferences.nextVisit());
    }

    @PostMapping("/session/language")
    Map<String, String> setLanguage(
            @RequestParam String language,
            HttpSession session) {

        if (!language.equals("vi") && !language.equals("en")) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Unsupported language");
        }

        preferences.setLanguage(language);
        session.setAttribute("uiLanguage", language);
        return Map.of("language", language);
    }

    @GetMapping("/session/raw")
    Map<String, String> rawSessionAttribute(
            @SessionAttribute(name = "uiLanguage", required = false)
            String language) {

        return Map.of(
                "language", language == null ? "not-set" : language);
    }

    @PostMapping("/session/end")
    ResponseEntity<Void> endSession(HttpServletRequest request) {
        HttpSession current = request.getSession(false);
        if (current != null) {
            current.invalidate();
        }
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/application")
    Map<String, Long> applicationInfo() {
        return Map.of("total", counter.next());
    }
}
```

**This is a valid Java 17 file when placed in the Boot 3 project described above:** only `ScopeApplication` has the `public` modifier; the other beans and controller are package-private in the same `demo.scope` package. Spring Boot component scanning from this package discovers all three `@Component` classes and the `@RestController`.

Flow explanation:

- `ScopeController` is a singleton by default and holds the injected **proxies** for the request-, session-, and application-scoped beans.
- `GET /api/scope/request` calls `requestMarker.getId()` twice within the same request, so `first` and `second` are equal. The next request gets a different request-scoped target, so the ID differs (UUID does not carry an absolute mathematical guarantee of uniqueness, though random collisions are practically negligible).
- The Servlet Filter sets `serverTag`; `@RequestAttribute("serverTag")` reads that exact attribute. If the controller runs through a pipeline without that filter and the required attribute is missing, the request can fail binding.
- `GET /api/scope/session` uses the `@SessionScope` bean of the current session and increments the visit count. A new client starts with the default language `vi` and an initial visit count of `1`.
- `POST /api/scope/session/language` writes the same choice to two places **solely to contrast the APIs**: a field on the `@SessionScope` bean and the `uiLanguage` key in `HttpSession`. They are two distinct mechanisms and do not stay synchronized automatically if one is changed independently.
- `GET /api/scope/session/raw` uses `@SessionAttribute(required=false)` to read only the `uiLanguage` attribute. For a new session without that key, it returns `not-set`; it does not force session creation.
- `POST /api/scope/session/end` invalidates an existing session and returns **204 No Content**. Do not use the session-scoped bean proxy after invalidating within the same method.
- `GET /api/scope/application` increments the counter belonging to the current `ServletContext`. Different clients can observe the shared incrementing total; since there is no database, a restart or another node has its own counter.

**The language choice is not automatically applied to `MessageSource` in this example.** The `language` field is merely a demo state string. To drive real localization, you must integrate `LocaleResolver`/`LocaleChangeInterceptor` or an appropriate i18n solution; see Section 12.

### 8.3. Observing with curl and Cookie Jars

Run the project:

```bash
./gradlew bootRun
```

Two requests that do not need a session:

```bash
curl -sS 'http://localhost:8080/api/scope/request'
curl -sS 'http://localhost:8080/api/scope/request'
```

Illustrative body (UUID varies per request):

```json
{"first":"<uuid-A>","second":"<uuid-A>","tag":"from-filter"}
```

The JSON line above is a **value schematic**; `<uuid-A>` is not a literal UUID. On the next request, `first` and `second` will contain UUID B, different from A. **Specific stdout cannot be declared** for randomly generated UUIDs before execution.

Use a cookie jar to retain the same session:

```bash
curl -i -c session-a.txt \
  'http://localhost:8080/api/scope/session'

curl -i -b session-a.txt -c session-a.txt \
  -X POST \
  -d 'language=en' \
  'http://localhost:8080/api/scope/session/language'

curl -sS -b session-a.txt \
  'http://localhost:8080/api/scope/session'

curl -sS -b session-a.txt \
  'http://localhost:8080/api/scope/session/raw'
```

Response bodies in order, assuming a fresh server and no other client touching the same session:

```json
{"language":"vi","visits":1}
{"language":"en"}
{"language":"en","visits":2}
{"language":"en"}
```

JSON key order may differ and is not part of the contract. `-c session-a.txt` saves cookies returned by the server; `-b session-a.txt` sends those cookies in subsequent requests. Without sending the cookie from session A, a new request will not automatically use session A.

Create client B's session using a separate cookie jar:

```bash
curl -i -c session-b.txt \
  'http://localhost:8080/api/scope/session'
```

Expected value (session B has never been used before): `{"language":"vi","visits":1}`, independent of session A. Do not commit `session-a.txt` / `session-b.txt` into the repository: they contain sensitive session identifiers.

End session A:

```bash
curl -i -b session-a.txt \
  -X POST \
  'http://localhost:8080/api/scope/session/end'
```

Expect status **204 No Content**. After this, the old session ID is no longer valid; a subsequent request with the old cookie may create a new session if the endpoint requires a session, depending on the container and cookie settings. Do not rely on the server "automatically retaining" data after invalidation.

## 9. MockMvc Tests to Prove Request/Session/Application Scope

In the project above, add **`src/test/java/demo/scope/ScopeApplicationTests.java`**:

```java
package demo.scope;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ScopeApplicationTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper; // Jackson 2 from the Spring Boot 3 baseline.

    @Test
    void requestTargetReusedWithinOneRequestButNotTheNext()
            throws Exception {

        MvcResult first = mvc.perform(get("/api/scope/request"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.tag").value("from-filter"))
                .andReturn();

        MvcResult second = mvc.perform(get("/api/scope/request"))
                .andExpect(status().isOk())
                .andReturn();

        JsonNode a = mapper.readTree(
                first.getResponse().getContentAsString());
        JsonNode b = mapper.readTree(
                second.getResponse().getContentAsString());

        assertEquals(a.get("first").asText(), a.get("second").asText());
        assertEquals(b.get("first").asText(), b.get("second").asText());
        assertNotEquals(a.get("first").asText(), b.get("first").asText());
    }

    @Test
    void sessionStateSurvivesOnlyWhenSameSessionIsReused()
            throws Exception {

        MvcResult first = mvc.perform(get("/api/scope/session"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.language").value("vi"))
                .andExpect(jsonPath("$.visits").value(1))
                .andReturn();

        MockHttpSession session = (MockHttpSession)
                first.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/api/scope/session/language")
                        .session(session)
                        .param("language", "en"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.language").value("en"));

        mvc.perform(get("/api/scope/session").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.language").value("en"))
                .andExpect(jsonPath("$.visits").value(2));

        mvc.perform(get("/api/scope/session/raw").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.language").value("en"));

        // Request without reusing the old session -> separate state.
        mvc.perform(get("/api/scope/session"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.language").value("vi"))
                .andExpect(jsonPath("$.visits").value(1));
    }

    @Test
    void unknownSessionAttributeIsOptional() throws Exception {
        mvc.perform(get("/api/scope/session/raw"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.language").value("not-set"));
    }

    @Test
    void invalidSessionChoiceReturns400() throws Exception {
        mvc.perform(post("/api/scope/session/language")
                        .param("language", "unknown"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void applicationCounterIsSharedInsideTheWebApp()
            throws Exception {
        mvc.perform(get("/api/scope/application"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").isNumber());

        mvc.perform(get("/api/scope/application"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").isNumber());
    }

    @Test
    void sessionCanBeInvalidated() throws Exception {
        MvcResult first = mvc.perform(get("/api/scope/session"))
                .andExpect(status().isOk())
                .andReturn();

        MockHttpSession session = (MockHttpSession)
                first.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/api/scope/session/end").session(session))
                .andExpect(status().isNoContent());
        // Do not reuse an invalidated MockHttpSession.
    }
}
```

Run:

```bash
./gradlew test
```

With **Spring Boot 3.x**, `spring-boot-starter-web`, `spring-boot-starter-test`, and the exact code in Section 8, **the six tests are designed to pass**. This is an expectation from code review, **not an actual Gradle execution result**.

Explanation of some assertions:

- Two calls to `getId()` in the **same HTTP request** return the same ID; the second request gets a new marker. Different UUIDs are the expected practical behavior in the sample test.
- In `MockMvc`, `.session(session)` resends the same `MockHttpSession` across multiple requests. **Without** reusing the session instance, a new request has independent state.
- `@SessionScope` resolves the target bean automatically per request/session. The test does not rely on Java static variables or controller fields to simulate a session.
- `@SessionAttribute(required=false)` returns the fallback when the key does not exist yet.
- The application counter is tested at the level of returning a number; a multi-test suite or parallel requests should not assert an absolute total starting from 1.
- The invalidation test avoids reusing a session already marked invalid; if you want to test the aftermath, send a request with a new session.

**Limitations:** `MockMvc` does not verify browser cookie flags, network proxies, Redis, clustering, multiple JVMs, or session serialization/deserialization failures. Those properties require integration tests in an appropriate environment. The test uses `ObjectMapper` from Jackson 2 because the baseline is Boot 3; Boot 4 switches the default JSON path to Jackson 3 `JsonMapper`, so test imports/mappers must be reviewed during migration.

## 10. Request, Session, and Application Scope Under Concurrent Threads

### Request Scope Is Normally Isolated Per Request, but Do Not Confuse That with Absolute Thread-Safety

Each request gets its own request-scoped bean per its lifecycle. In standard synchronous processing, this data is not accidentally shared between two HTTP requests. However, a request can involve async dispatch/callbacks; framework and application code must manage context properly and never assume "a request always runs on a single thread" in every model.

If you offload work to an executor, do not hold a reference to `HttpServletRequest` or rely on `RequestContextHolder` on a worker thread that has no context. Extract the required data beforehand and pass immutable values or an explicitly designed context carrier.

### Session Scope Can Be Accessed Simultaneously by Multiple Requests

Two tabs or multiple HTTP calls from the same browser can send requests **concurrently** with the same session ID. Therefore:

```text
Session S-A has cartQuantity = 0

Request 1: reads 0 ----+
                       +---- both write 1
Request 2: reads 0 ----+

The result can be 1 instead of 2 when using unsynchronized read-modify-write.
```

`HttpSession` **does not automatically make mutable objects stored inside it thread-safe**. Solutions:

- Use immutable values + updates via an appropriate atomic mechanism.
- For temporary state within a single JVM, use appropriate locking or atomic counters; evaluate contention and lifecycle.
- For cluster/Redis/DB, use transactions, optimistic locking, compare-and-set, atomic increments, database constraints, or an appropriate consistency strategy.
- Do not synchronize via `synchronized(this)` on a scoped bean and assume it takes effect **across multiple nodes**.
- Do not hold a session lock while calling slow external APIs if unnecessary; this can block other requests from the same user for too long.

### Application Scope and Singletons Require Even Greater Attention to Concurrency

Data shared across all requests in the same instance experiences higher contention. For example, a mutable `HashMap` placed in a singleton is not safe for concurrent writes; use `ConcurrentHashMap` when needed, while also considering the atomicity of the entire business operation.

**Scope determines "who sees the same object"**, not "whether the object is automatically synchronized" or "whether data is persisted durably."

## 11. Session Timeout, Cookies, Security, and Privacy

### 11.1. Session Configuration in Spring Boot Servlet

Common Spring Boot Servlet properties:

```properties
# Example: an inactive session for this duration will expire
server.servlet.session.timeout=30m

# Session cookie is only transmitted over HTTPS (deployment must use real HTTPS)
server.servlet.session.cookie.secure=true

# Restrict JavaScript from reading the session cookie
server.servlet.session.cookie.http-only=true

# Adjust cross-site cookie policy according to the use case
server.servlet.session.cookie.same-site=lax
```

This is a **sample configuration**; do not blindly enable every setting in environments with plaintext HTTP or cross-site frontends. A `Secure` cookie requires an HTTPS connection on the client side; if enabled in a local HTTP-only environment, browser cookie storage/transmission may behave unexpectedly. `SameSite=None` normally requires `Secure` and must be carefully evaluated for CSRF/CORS/authentication.

`server.servlet.session.timeout` is the configured session inactivity timeout; a session can still terminate early due to logout, invalidation, backend store failure, or policy changes. With an external Spring Session backend, TTL and timeout handling also depend on the repository's save/expiration mechanism.

### 11.2. Session ID Is a Bearer Credential That Must Be Protected

- Session IDs should be unpredictable, transmitted over HTTPS, and managed with appropriate cookie policies.
- Avoid putting session IDs in URLs/query strings, access logs, analytics, `Referer` headers, or screenshots.
- Protect against **session fixation** on login; with Spring Security, use the session fixation protection provided by the framework for your version/configuration.
- When relying on cookies for authenticated forms/actions, protect against **CSRF**. `SameSite` helps, but does not replace all appropriate layers of defense.
- Logout must clear authentication state and terminate/revoke the session according to policy; removing only a language key does not log the user out.
- Do not store plaintext passwords, raw refresh tokens, unnecessary PII, or very large objects in the session.
- A session bean/attribute may contain internal non-serializable objects, causing errors during clustering or session persistence. Verify serialization/schema design before using an external store.

### 11.3. Session State Does Not Replace Authorization

A request carrying a valid session cookie does not prove the endpoint is permitted to modify any resource. Authorization must rely on a trusted identity/principal and check permissions for the specific resource. Never accept a `userId` parameter and access another user's state/session based solely on that ID.

Some REST API architectures do not use server-side sessions and instead verify tokens on every request. **Stateless authentication** does not mean the application has zero state: domain data still lives in a DB/cache, and tokens also have lifetimes and revocation policies as required.

## 12. Language State: When to Use Session, Locale, and User Profile?

Language selection is an easy-to-learn example of state, yet it has several valid designs.

### 12.1. Using Only the Client-Requested Language Per Request

The client sends `Accept-Language`, and the server applies an appropriate locale resolution mechanism. In Spring MVC, `LocaleResolver`, `LocaleContextResolver`, and `LocaleContextHolder` play key roles in i18n. When manual selection does not need to be remembered, resolving language per request/header is appropriate.

```http
GET /products HTTP/1.1
Accept-Language: vi-VN,vi;q=0.9,en;q=0.7
```

A client-sent header does not have to be accepted verbatim by the application: the configured locale resolver, supported locales, and fallback policy determine the chosen language.

### 12.2. User Selects a Language Once for the Session

If the UI provides a per-session selector, `@SessionScope`/`HttpSession` can remember the language and use it to configure the locale of subsequent requests. However, **merely storing the string `"en"` in `SessionPreferences` does not automatically make Spring `MessageSource` render English**. The application must integrate with `LocaleResolver`/an appropriate locale change strategy.

Never place an arbitrary language value from a request into the session without whitelisting. When only `vi`/`en` are supported, validate input as shown in Section 8.

### 12.3. Per-User Preference Across Multiple Devices

When a user logs in on both a phone and a laptop, the two browsers normally have separate sessions. To maintain the same language across all devices, store the preference by user ID in the DB and apply it to locale selection after authentication. The session can cache the current preference, but it is not the durable source of truth.

## 13. Multi-Instance Systems: Why Can Sessions "Disappear" When Scaling?

When deploying two pods:

```text
Load balancer
     |
     +---- App A (JVM A) -> local HttpSession A
     |
     +---- App B (JVM B) -> local HttpSession B

Browser sends JSESSIONID from App A
next request is routed to App B
=> App B does not by default have App A's session data.
```

Solutions to consider:

1. **Sticky sessions** (load balancer pins the same client to one node): simple, but if a node fails/restarts sessions can still be lost and load balancing becomes uneven.
2. **Shared session store** (e.g., Spring Session + Redis): replaces the `HttpSession` implementation with a shared backend so both A and B can read the same session ID.
3. **Database/domain store**: if data requires long-term durability, store it per user/resource instead of stuffing everything into the HTTP session.
4. **Stateless API**: avoid HTTP sessions for suitable endpoints, passing authentication/context via tokens and querying the real storage.

**Spring Session** integrates with Servlet `HttpSession` through a filter, backed by stores like Redis/JDBC depending on dependencies/configuration. Once set up, code using `HttpSession` and many Spring MVC session mechanisms can continue working with minimal changes, though you must handle:

- Serialization/versioning of session attributes during rolling deployments.
- TTL, cookie settings, backend availability, memory, and storage costs.
- Concurrent writes to the same session and save/flush strategies.
- Application design adjustments to avoid storing oversized or non-serializable object graphs in the session.
- Observability and disaster recovery for the session store.

Example **Boot 3 dependency snippet** when actually configuring Redis-backed sessions (do not add to the Section 8 demo project without Redis):

```groovy
dependencies {
    implementation 'org.springframework.session:spring-session-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

In a project using the Spring Boot BOM and appropriate auto-configuration, you still need Redis connection properties and version-specific session settings. This is not a complete Redis configuration. **Do not assume "adding dependencies" proves state is safely shared across multiple nodes**; write integration tests verifying two app instances sharing the Redis/session store.

Spring Session 4.x aligns with the Spring Framework 7 / Boot 4 generation, whereas Boot 3.x typically uses Spring Session 3.x managed by the BOM. Do not hardcode two incompatible major versions.

## 14. When Should You Avoid Sessions?

Sessions are useful, but not always the best choice:

- **Stateless APIs needing horizontal scaling:** independent requests; the server fetches domain state from DB/cache keyed by user/resource.
- **Long-running tasks or queued jobs:** job state needs its own identity and persistence; do not turn the session into a job repository.
- **Large data:** storing an identifier and querying DB/cache can make more sense than copying an entire entity list into the session.
- **Application-wide information:** use configuration/singletons/shared caches rather than duplicating it in every session.
- **Long-term preferences:** store user preferences durably; the session is only a temporary cache.
- **Passing state between microservices:** use request metadata or explicit context; do not assume two services share the same Servlet `HttpSession` unless explicitly designed.
- **Secrecy and audit requirements:** do not store sensitive data arbitrarily in the session; consider compliance and data lifecycle management.

A quick selection guide:

| Question | If "Yes" | Design direction |
| --- | --- | --- |
| Is the data only for the current request? | Yes | Method parameter, request attribute, `@RequestScope` |
| Is the data needed in the next request of the **same session**? | Yes | `HttpSession`/`@SessionScope`, if stateful is permitted |
| Only need a message after a redirect? | Yes | Flash attributes |
| Need to keep a model across steps of the same wizard controller? | Yes | `@SessionAttributes` + `SessionStatus` |
| Shared by all users of the same web app? | Yes | Singleton/`@ApplicationScope` with concurrent access protection |
| Must all nodes/pods see it? | Yes | Shared store or distributed coordination |
| Must the data survive restarts/logout or work across devices? | Yes | Database/domain storage keyed by user/resource |
| Is this identity or authorization? | Yes | Official Spring Security / principal / permission checks |

## 15. Common Mistakes to Recognize

### Mistake A — Storing User Information in a Singleton Field

```java
@RestController
class UnsafeController {
    private String currentUserId; // Wrong: singleton shared across multiple requests.

    @PostMapping("/select-user")
    String select(@RequestParam String userId) {
        currentUserId = userId;
        return currentUserId;
    }
}
```

This is an **anti-pattern**; do not use it in production. Two users sending concurrent requests can see each other's state. Obtain the authenticated identity per request, or store it in the proper session/user store with authorization.

### Mistake B — Assuming a Request Attribute Survives a Redirect

```java
request.setAttribute("notice", "Saved");
return "redirect:/summary";
```

The new request to `/summary` will not automatically carry the `notice` attribute from the old request. Use `RedirectAttributes.addFlashAttribute("notice", ...)` if you need a short message for the post-redirect request.

### Mistake C — Injecting an Unproxied Request/Session Bean Directly into a Singleton

If a bean is declared with plain `@Scope("session")` without a scoped proxy or provider, a singleton may encounter an inactive scope at startup or hold onto the wrong object. In Spring MVC, use `@SessionScope`/`@RequestScope` or declare an appropriate `proxyMode`.

### Mistake D — Using `@SessionAttribute` Expecting It to Auto-Create a Value

`@SessionAttribute("language")` does not write `language` when the key does not exist. With `required=true` (the default), a missing attribute fails argument resolution; marking it optional enables fallback logic.

### Mistake E — Confusing `@SessionAttributes` with `@SessionScope`

`@SessionAttributes("draft")` is a controller-class marker for a **model conversation**, cleared with `SessionStatus#setComplete()`. `@SessionScope` is a **bean lifetime** marker. They solve two different problems.

### Mistake F — Using a Mutable Session Bean Without Handling Concurrency

Requests from the same browser/session can run in parallel. `private int cartCount; cartCount++;` does not guarantee atomicity. Use synchronization appropriate to the storage scope, paying special attention to Redis/clustering.

### Mistake G — Session Timeout or Restart Losing State

A session is not a database. App restarts, routing to another node, Redis key TTL expiration, or user logout can all cause state to vanish. For durable information, persist to a DB with a proper contract.

### Mistake H — Session Cookie Not Being Sent

If the browser does not store the cookie, `SameSite`/`Secure` is misconfigured for the environment, domain/path mismatches, or CORS credentials are not enabled cross-origin, new requests may fail to locate the session. Inspect `Set-Cookie`, request `Cookie`, HTTPS scheme, devtools, and gateways.

### Mistake I — Accessing a Scoped Bean from a Background Thread

`@Async`, schedulers, or executors have no HTTP request context by default. Accessing a request/session proxy there can trigger `ScopeNotActiveException` / "No thread-bound request". Pass immutable context via parameters or persist state outside the request.

### Mistake J — Treating Application Scope as a Cluster-Wide Cache

`@ApplicationScope` lives only within a single `ServletContext`. When scaling to two pods, each pod has its own instance. For global state, use shared storage or a coordination mechanism.

### Mistake K — Creating a Session When Only Reading

Calling `request.getSession()` or injecting `HttpSession` when you only need to check "whether an existing session is present" can inflate session counts. Use `getSession(false)` when the goal is checking without creating.

### Mistake L — Neglecting Session Security

Session IDs can be stolen without HTTPS/cookie controls; CSRF can affect cookie-authenticated state-changing endpoints; session fixation must be handled on login. Never assume a `@SessionScope` bean automatically guarantees security.

## 16. Spring Upgrade Notes

| Platform | Practical differences |
| --- | --- |
| Spring Framework 5.x + Spring Boot 2.x | Request/session/application web scopes are available; Servlet API is typically under `javax.servlet.*` |
| Spring Framework 6.x + Spring Boot 3.x | Java 17+, Servlet under `jakarta.servlet.*`; the runnable example in Section 8 uses this baseline |
| Spring Framework 7.x + Spring Boot 4.x | Bean/HTTP session scopes remain available, though starters, Spring Session major version, and JSON/test auto-configuration must be checked against the new BOM |

`@RequestScope`, `@SessionScope`, and `@ApplicationScope` are Spring bean-level annotations independent of the JSON mapper. Therefore, moving from Jackson 2 to Jackson 3 in Boot 4 **does not change the bean scope lifecycles**, though test code reading JSON with `ObjectMapper` will need updating if the project uses the default Jackson 3 mapper.

In **AOT/native image** environments, bean/proxy/reflection initialization should be reviewed for your Spring Boot version; incompatible constructors or proxy targets can break native builds even when running fine on the JVM. Do not skip smoke tests for request/session scoping after a migration.

## 17. Scope-Based State Design Checklist

- [ ] Every piece of data has a clear owner: request, HTTP session, ServletContext/Spring context, database, or shared cache.
- [ ] No user-specific mutable state is stored in singleton controllers/services.
- [ ] Session data belongs strictly to the relevant user/session; self-reported user IDs are never trusted.
- [ ] `@RequestScope` and `@SessionScope` are injected into singletons properly via scoped proxies or providers.
- [ ] No references to request objects/`HttpServletRequest` are retained in async workers after the request finishes.
- [ ] Session-scoped mutable objects are protected against concurrent requests and redesigned for multi-node setups.
- [ ] Session cookies are protected with HTTPS and appropriate Secure/HttpOnly/SameSite settings; authentication, CSRF, and session fixation are handled.
- [ ] Existing sessions are read via `getSession(false)` when you do not want to create a new session.
- [ ] Sessions have timeouts and logout/invalidation policies, and do not store unnecessary secrets/PII.
- [ ] Redirects use flash attributes instead of request attributes to pass one-time notices.
- [ ] `@SessionAttributes` workflows are completed with `SessionStatus#setComplete()`.
- [ ] Data needed after restarts or shared across devices is persisted in a DB.
- [ ] Data needed across multiple nodes uses a shared store or consistency mechanism.
- [ ] Tests cover two distinct HTTP requests, two distinct sessions, and requests reusing the same session.
- [ ] Application-wide counters are not asserted starting from 1 if test suites can run in parallel or receive other requests.

## 18. Self-Assessment Exercises

1. A filter computes `traceId`. Choose between `request.setAttribute` + `@RequestAttribute` and a `@RequestScope` bean. Which is more appropriate for a single string? Which is better if you need a request context object with multiple fields?
2. Two tabs of the same browser send `POST /cart/add` concurrently. Why does `@SessionScope` not guarantee `cartCount++` is safe? Propose solutions for a single-node deployment and for a Redis-backed setup.
3. Add an endpoint to view the language choice using `@SessionAttribute(name="uiLanguage",required=false)`. When the key is absent, should you call `getSession()` to create a new session?
4. In the sample application, why does calling `requestMarker.getId()` twice within the same request return the same value even though the controller is a singleton? What changes when the next request arrives?
5. You set a request attribute `notice` and then redirect to another URL. Why is `notice` lost? Fix it using `RedirectAttributes.addFlashAttribute` and contrast flash attributes with long-lived session attributes.
6. A three-step wizard form uses `@SessionAttributes("draft")`: upon completion, does `SessionStatus#setComplete()` also invalidate the login session?
7. A singleton service has `private String lastUserId` updated on each request. How can data leak? Fix the design using per-request identity and user-ID-keyed domain storage.
8. Two Spring Boot pods use local `HttpSession`, and the load balancer routes requests randomly. What happens to `@SessionScope`? Name two mitigation strategies and their trade-offs.
9. A user wants their language choice to appear on another phone after logging in. Why is storing `language` in the laptop's session insufficient? Design a DB preference + locale resolution flow.
10. Extend the MockMvc tests: save `language=en` in session A, verify `GET` in session B still returns `vi`; invalidate session A and confirm a new request does not see `en`.
11. An `@Async` method calls `RequestContextHolder.currentRequestAttributes()` and fails. Explain why you should not "fix" this by arbitrarily sharing the request object across all threads.
12. Shared configuration data for all users changes every minute. Compare a singleton local cache, `@ApplicationScope`, and a distributed cache; when are TTL/invalidation needed?

## 19. Official References

- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton, prototype, request, session, application, scoped proxies.
- [Spring Framework 6.2 — Web Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html): request/session/application in the Spring 6 platform.
- [Spring Framework — `@RequestScope` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/context/annotation/RequestScope.html): request scope shortcut and scoped proxy.
- [Spring Framework — `@SessionScope` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/context/annotation/SessionScope.html): session bean and default proxyMode.
- [Spring MVC — `@RequestAttribute`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestattrib.html): reading existing request attributes.
- [Spring MVC — `@SessionAttribute`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattribute.html): reading existing attributes in the session.
- [Spring MVC — `@SessionAttributes`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattributes.html): keeping temporary model attributes across multiple requests, `SessionStatus`.
- [Spring MVC — Flash Attributes](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/flash-attributes.html): storing temporary data between a redirect and the next request.
- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html): session timeout and cookie settings.
- [Spring Session — HttpSession Integration](https://docs.spring.io/spring-session/reference/http-session.html): shared session storage and replacing Servlet HttpSession.
