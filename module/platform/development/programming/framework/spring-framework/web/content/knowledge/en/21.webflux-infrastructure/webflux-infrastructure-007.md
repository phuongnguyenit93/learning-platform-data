# WebSession, LocaleContext, and Reactor Context in Spring WebFlux

## 1. Objectives and context

When moving from Spring MVC Servlet to **Spring WebFlux**, you still need to handle user state, UI language, tracing, correlation IDs, security, and information flowing through an asynchronous pipeline. Yet you cannot carry over the `HttpSession`, `LocaleContextHolder`, or `ThreadLocal` assumptions of the old request-per-thread model into Reactor without verifying data lifecycles.

Spring WebFlux provides three related yet **fundamentally distinct** concepts:

- **`WebSession`**: server-side session carrying session attributes across **multiple HTTP requests** from the same client when a valid session ID is presented; it has a lifecycle and backing store.
- **`LocaleContext`**: language/region information (and depending on the resolver, optionally timezone) determined for the **current HTTP exchange**; typically based on `Accept-Language`.
- **Reactor `Context`/`ContextView`**: an immutable key/value metadata container following **one reactive subscription**, propagating across async operators without requiring a fixed thread. It is neither a database session nor an HTTP session.

After this article, you will be able to:

1. Distinguish **`WebSession`**, `ServerWebExchange`, `LocaleContext`, Reactor `Context`, and `ThreadLocal` by scope/lifetime.
2. Use `ServerWebExchange.getSession()` or a `WebSession` argument to read, write, invalidate, rotate session IDs, and set idle timeouts properly.
3. Know that **reading a session does not create a new session cookie**; a session only starts when writing attributes or calling `start()` explicitly.
4. Use `ServerWebExchange.getLocaleContext()` and `LocaleContextResolver`; understand the default `AcceptHeaderLocaleContextResolver` and why `setLocaleContext` may be unsupported.
5. Use `Mono.deferContextual`, `contextWrite`, and `WebFilter` to propagate request correlation IDs across `publishOn`/`flatMap` per Reactor semantics.
6. Integrate reactive Spring Security via `ReactiveSecurityContextHolder` without confusing it with `SecurityContextHolder`/Servlet sessions.
7. Build a **Java 17+, Spring Boot 3.x + Spring WebFlux** app with stateful endpoints, Locale, Reactor Context, and real HTTP tests using `WebTestClient`.
8. Identify risks of storing mutable data in sessions, clients omitting cookies, losing context via manual subscribe, session ID leaks, caching/CORS/SameSite issues, and multi-instance scaling.

**Target versions:** Spring Framework **6.x**, Spring Boot **3.x**, Reactor 3.x, Java 17+. Examples run WebFlux on a reactive HTTP server; omit `spring-boot-starter-web` so Boot does not pick MVC when both web starters are present. Syntax/conventions may change in Spring Framework 7/Boot 4; check documentation for your exact version.

## 2. Lifecycle map: three non-interchangeable contexts

| Object | Scope | Persists across HTTP requests? | Where is data stored? | Typical access |
| --- | --- | --- | --- | --- |
| `WebSession` | Client/server session | **Yes**, while valid and ID is returned | `WebSessionStore`, in-memory by default or Spring Session backend | `exchange.getSession()`/`WebSession` |
| `ServerWebExchange` attributes | **One** HTTP exchange | Not automatically | Request/exchange-scoped map | `exchange.getAttributes()` |
| `LocaleContext` | HTTP exchange locale | Not automatically | Resolver reading request/strategy | `exchange.getLocaleContext()` |
| Reactor `Context` | **One reactive subscriber/subscription** | Not automatically | Context attached to subscriber chain | `Mono.deferContextual`, `contextWrite` |
| Java `ThreadLocal` | One JVM thread | No guarantee aligned with requests/reactive signals | Current thread | `ThreadLocal.get()` |
| Reactive security context | Reactive subscription/request security chain | Only if security has a persistence/auth mechanism | Reactor Context, security repository when configured | `ReactiveSecurityContextHolder` |

A real request can involve all four simultaneously:

~~~text
Browser ---- Cookie: SESSION=... ----> ServerWebExchange
                                        |
                                        +-- WebSession
                                        |     savedTheme=dark
                                        |
                                        +-- LocaleContext
                                        |     locale=vi-VN (Accept-Language)
                                        |
                                        +-- exchange.attributes
                                        |     requestId=req-001
                                        |
                                        +-- WebFilter
                                              |
                                              v
                                        Reactor subscription Context
                                              requestId=req-001
                                              security context ...
                                              |
                                  publishOn / flatMap / WebClient...
                                              |
                                              v
                                        HTTP response
~~~

**Important:** Reactor Context does not turn data into long-lived user state. Once the request ends, request-scoped Context is not automatically saved. When a preference must survive into subsequent requests, choose an appropriate mechanism such as WebSession, a database/user profile, or cookies depending on the use case and threat model.

## 3. What is WebSession?

`org.springframework.web.server.WebSession` is WebFlux's server-side session contract. It is **not** `jakarta.servlet.http.HttpSession`, and running WebFlux on a Servlet container does not mean reactive controllers should depend directly on HttpSession.

Notable APIs:

| API | Meaning | Notes |
| --- | --- | --- |
| `getId()` | Session ID | Treat as sensitive data; do not expose in JSON/logs |
| `getAttributes()` | Map holding attributes | Can hold mutable objects; design concurrency/state carefully |
| `getAttribute(name)` | Reads one attribute | Does not guarantee existence or exact type |
| `getAttributeOrDefault(...)` | Reads with fallback | Handy for small preferences |
| `getCreationTime()` | Session creation timestamp | Not login time |
| `getLastAccessTime()` | Most recent access timestamp | Depends on store and session activity |
| `getMaxIdleTime()` | Maximum idle interval | Not cookie max-age or absolute expiry |
| `setMaxIdleTime(Duration)` | Updates idle duration | Consider global policy |
| `isStarted()` | Whether the session has started | Calling `getSession()` alone does not start it |
| `start()` | Forces the session to start | Leads to cookie/session ID on save |
| `invalidate()` | Invalidates and clears session storage | **Returns `Mono<Void>`**, must compose/subscribe |
| `changeSessionId()` | Rotates session ID | **Returns `Mono<Void>`**, must complete |
| `save()` | Saves session to store | Usually invoked automatically by framework before response commit |

### 3.1. Obtaining a session without starting storage

`ServerWebExchange.getSession()` returns:

~~~java
Mono<WebSession> sessionMono = exchange.getSession();
~~~

Illustrative method form with `ServerWebExchange exchange`. WebSessionManager ensures a new `WebSession` or one matching the client ID (if existing and unexpired), yet **reading/receiving a WebSession object does not automatically issue a session cookie**.

Read example:

~~~java
public Mono<String> theme(ServerWebExchange exchange) {
    return exchange.getSession()
            .map(session ->
                    session.getAttributeOrDefault("theme", "light"));
}
~~~

If the request does not have a started session yet, this code normally does not instruct the browser to store a new session. When the request carries a valid existing session cookie, it can read the previously saved `theme`.

### 3.2. Adding an attribute → implicitly starts the session

~~~java
public Mono<Void> chooseTheme(ServerWebExchange exchange) {
    return exchange.getSession()
            .doOnNext(session ->
                    session.getAttributes().put("theme", "dark"))
            .then();
}
~~~

When an attribute is added to a new session, `WebSession` is normally started implicitly. By default in WebFlux, the framework invokes session save at the right lifecycle point before response commit. **Never call `session.save().block()` on the event loop**; `save()` is reactive and managed by the framework.

Remember: putting an attribute into a Map is an in-memory operation on the session object, not a database transaction. With distributed session stores, persistence/serialization/synchronization are separate concerns.

### 3.3. start() without attributes

~~~java
public Mono<String> start(ServerWebExchange exchange) {
    return exchange.getSession().map(session -> {
        session.start();
        return "started";
    });
}
~~~

This is an illustrative method. `start()` forces the session to begin even if the attributes Map is empty. Use it only when business logic genuinely requires creating a session; **do not start a session on every request out of habit**, which creates unnecessary sessions/cookies and storage overhead.

### 3.4. Invalidating and rotating session IDs reactively

~~~java
@PostMapping("/logout")
public Mono<Void> logout(WebSession session) {
    return session.invalidate();
}
~~~

~~~java
@PostMapping("/rotate")
public Mono<Void> rotate(WebSession session) {
    return session.changeSessionId();
}
~~~

Both snippets are illustrative handlers needing a controller class and imports. Because `invalidate()`/`changeSessionId()` return `Mono<Void>`, **you must return or compose the Publisher**. Calling the method and discarding its return value:

~~~java
session.invalidate(); // wrong: not subscribed/returned
return Mono.empty();
~~~

can leave invalidation unexecuted. Likewise, never call `.subscribe()` fire-and-forget as it breaks error propagation, cancellation, and response lifecycles.

Session ID rotation is one layer of session fixation defense when authentication state changes; **do not treat calling rotate alone as a complete security design**. When an application uses Spring Security, let the security framework manage session/authentication policies through its chain.

## 4. WebSessionManager, WebSessionStore, and cookie/session IDs

Session management flow:

~~~text
Browser
  | Cookie: SESSION=<opaque-id>
  v
WebSessionIdResolver
  | resolveSessionIds(exchange)
  v
WebSessionManager (DefaultWebSessionManager)
  | lookup or create session object
  v
WebSessionStore
  | retrieve/store/expire
  v
WebSession.getAttributes()

Before HTTP response commit:
  WebSession.save() -> store + WebSessionIdResolver response cookie
~~~

Components:

- **`WebSessionManager`**: retrieves sessions per HTTP exchange. Default is `DefaultWebSessionManager`.
- **`WebSessionIdResolver`**: reads/sends the ID between client and server. By default this is usually `CookieWebSessionIdResolver`, with cookie name **`SESSION`** in standard WebFlux setups.
- **`WebSessionStore`**: stores and retrieves sessions. By default WebFlux can use an **in-memory store**, not shared across instances.
- **Spring Session**: can supply persistent/distributed reactive session stores (e.g., Redis) when configured with compatible dependencies and repositories.

**Do not confuse the session ID cookie with session data:** in the default model, values like `theme` or `cart` reside server-side; the cookie mainly carries an opaque/random lookup ID. Anyone obtaining a valid session ID can attempt session hijacking, so enforce TLS, Secure/HttpOnly/SameSite, session rotation, and proper XSS/CSRF defenses.

### 4.1. Setting lifetime

Two distinct concepts:

- **Idle timeout on WebSession**: if there is no user activity after `getLastAccessTime()` within `maxIdleTime`, the session is considered expired.
- **Cookie Max-Age/Expires**: how long the browser keeps/sends the cookie. An existing cookie does not prove the server-side session is unexpired, and deleting the cookie does not necessarily clear server storage immediately without a logout request.

Spring Boot 3.5 provides reactive session properties, for example:

~~~properties
server.reactive.session.timeout=30m
server.reactive.session.cookie.same-site=lax
server.reactive.session.cookie.secure=true
~~~

This configuration **illustrates HTTPS production deployment**, not a mandatory setup for running locally on `http://localhost`: a `Secure` cookie may not be sent by clients over plain HTTP. Always verify property names against your **running Spring Boot version** (Boot 3.x varies across minor versions and auto-configuration). These properties follow Boot 3.5 docs; on Boot 3.0/3.1 consult the matching reference.

Do not call `setMaxIdleTime(Duration.ofMinutes(...))` on every request when a centralized policy exists without good reason; you lose consistent session TTL control across endpoints. Some stores have distinct expiration semantics and lazy cleanup that must be monitored.

### 4.2. Cookie security and CORS

When a frontend on another origin calls a backend with a session cookie:
- `fetch` may need `credentials: "include"`, and server CORS must allow the specific origin + `Access-Control-Allow-Credentials: true`.
- Cookies must still satisfy `SameSite`, `Secure`, `Domain`, `Path`, expiry, and third-party cookie restrictions.
- **CORS does not replace CSRF protection**. With cookie auth, unsafe methods POST/PUT/DELETE still require appropriate CSRF defenses.
- `HttpOnly` prevents JavaScript from reading cookies; it does not stop browsers from attaching cookies on eligible requests.
- Never use `allowedOrigins("*")` with credentialed CORS; Spring/browsers reject that combination.

If testing with `curl` without saving cookies, each request gets a fresh WebSession. If testing via a browser with cookies while the session store is in-memory on node A and a load balancer routes to node B, sessions can vanish; you need policy-aligned sticky sessions or a shared session repository.

## 5. Session attributes: data types, concurrency, and memory

Avoid storing heavy object graphs or hard-to-serialize objects in sessions. Better:

~~~java
session.getAttributes().put("preferredLanguage", "vi");
session.getAttributes().put("favoriteColor", "blue");
~~~

Do not store:

~~~java
session.getAttributes().put("password", rawPassword);
session.getAttributes().put("request", exchange);
session.getAttributes().put("openStream", inputStream);
~~~

Those three lines are **anti-patterns** with undefined variables. Sessions can outlive many requests; holding requests/streams can leak resources, credentials in sessions can be compromised if storage/logs leak, and distributed serialization will fail.

### 5.1. Mutable session state can race

Suppose two concurrent AJAX requests share the same session and update an `ArrayList` or cart-count map. `session.getAttributes()` does **not** make nested session objects automatically thread-safe, nor does it provide database transactions. Two requests can suffer lost updates or overwrite the shared store with stale session versions.

A safer choice for critical data is a **DB with transactions/optimistic locking**, storing minimal identifiers in the session:

~~~java
session.getAttributes().put("cartId", cartId);
~~~

This snippet uses a server-generated and validated `cartId`. Never use mutable session attributes as the source of truth for inventory, balances, permissions, or multi-step operations needing strong consistency.

### 5.2. @SessionAttribute and @SessionAttributes

- `@SessionAttribute` on a method argument reads an **existing attribute** from the session and works well when managed outside the controller, such as by a filter.
- `@SessionAttributes` on a **`@Controller` class** supports multi-request workflows, retaining model attributes across requests, often paired with `SessionStatus.setComplete()` to mark completion.
- For explicitly adding/removing attributes, using `WebSession` directly is usually clearer.

Do not confuse `@SessionAttributes` (plural) with `@SessionAttribute` (singular), or think either annotation configures security or session TTLs.

## 6. Where does WebFlux get LocaleContext?

`LocaleContext` resides in `org.springframework.context.i18n.LocaleContext`. In WebFlux, `ServerWebExchange.getLocaleContext()` returns info from the configured **`LocaleContextResolver`** bean.

As of Spring Framework 6.2, the default strategy is **`AcceptHeaderLocaleContextResolver`**, reading `Accept-Language` from the request. For example:

~~~http
GET /api/context/state HTTP/1.1
Accept-Language: vi-VN,vi;q=0.9,en-US;q=0.5
~~~

Without a restricted list of supported locales, the resolved locale can be `vi-VN`. Another request from an `en-US` browser receives a different locale **without changing any WebSession attribute**.

Reading in a handler:

~~~java
@GetMapping("/language")
public Mono<String> language(ServerWebExchange exchange) {
    LocaleContext context = exchange.getLocaleContext();
    Locale locale = context.getLocale();
    String tag = locale == null ? "und" : locale.toLanguageTag();
    return Mono.just(tag);
}
~~~

This is an illustrative controller method needing `LocaleContext`, `Locale`, `Mono`, and annotation imports. `"und"` is the language tag for **undetermined** when no locale exists, not a guaranteed response from every resolver.

### 6.1. Locale differs from timezone

`Locale` typically describes display language/country (e.g., `vi-VN`, `en-US`), **not** timezone. `LocaleContext` can be extended by `TimeZoneAwareLocaleContext`, yet the default **`AcceptHeaderLocaleContextResolver` does not supply a timezone** via that mechanism.

Illustrative conditional timezone extraction:

~~~java
LocaleContext lc = exchange.getLocaleContext();
TimeZone zone = lc instanceof TimeZoneAwareLocaleContext aware
        ? aware.getTimeZone()
        : null;
~~~

This snippet requires `java.util.TimeZone`, `TimeZoneAwareLocaleContext`, `LocaleContext`, and `exchange`. Never infer `Asia/Ho_Chi_Minh` solely from `Locale.forLanguageTag("vi-VN")`; locale and timezone are independent data points.

### 6.2. AcceptHeaderLocaleContextResolver is not an arbitrary locale store

`LocaleContextResolver` defines:
- `resolveLocaleContext(ServerWebExchange)`
- `setLocaleContext(ServerWebExchange, LocaleContext)`

However, `AcceptHeaderLocaleContextResolver` **does not support storing/changing locale via `setLocaleContext`**: the `Accept-Language` request header is sent by the client. Calling `setLocaleContext` can throw `UnsupportedOperationException` per API. If a user picks a language in the UI and you want to remember it, you must:
- Store the preference in a user profile database, WebSession, or cookie per business design.
- Build a resolver/filter/controller with an explicit selection policy (e.g., preferring profile/session over Accept-Language).
- Define precedence clearly and apply the effective locale when formatting.
- Never call `LocaleContextHolder.setLocale(...)` and assume the reactive pipeline preserves it across async thread hops.

### 6.3. Configuring supported locales

Spring Framework 6.2 example:

~~~java
@Configuration
public class LocaleWebConfig {
    @Bean(name = "localeContextResolver")
    public LocaleContextResolver localeContextResolver() {
        AcceptHeaderLocaleContextResolver resolver =
                new AcceptHeaderLocaleContextResolver();
        resolver.setSupportedLocales(
                List.of(Locale.forLanguageTag("vi-VN"),
                        Locale.forLanguageTag("en-US")));
        resolver.setDefaultLocale(Locale.forLanguageTag("vi-VN"));
        return resolver;
    }
}
~~~

**This is an additional illustrative class, not required in the section 10 demo.** Required imports: `Configuration`, `Bean`, `LocaleContextResolver` from `org.springframework.web.server.i18n`, `AcceptHeaderLocaleContextResolver`, `List`, `Locale`. In an app with Spring Boot auto-configuration, verify bean-overriding/conditional-config policies if Boot or a library already provides a resolver; do not create two beans with the same name.

Javadoc for `setSupportedLocales` emphasizes that matching can require exact compatibility of **language and country**. For instance, if only `en-US` is supported, `en-GB` or `en` may not match and fall back to default/first requested locale depending on config. To support language-only matching, include `Locale.ENGLISH` in supported locales or implement appropriate normalization.

**Never assume** a controller automatically saves `Accept-Language` into the session. They are two independent mechanisms.

## 7. Reactor Context: per-subscription metadata, not WebSession

Reactor `Context` is an **immutable** key/value structure tied to a subscriber. `ContextView` offers a read-only view, while `Context` supports `put` and `delete` by producing a new context.

A pure Reactor example:

~~~java
Mono<String> message =
        Mono.deferContextual(view ->
                Mono.just(view.getOrDefault("requestId", "missing")))
            .contextWrite(ctx ->
                ctx.put("requestId", "req-42"));
~~~

When subscribed, `message` emits **`req-42`**. Key points:

- `Mono.deferContextual` reads Context **at subscription time**, not necessarily when the controller method is invoked.
- `contextWrite` does not mutate a global variable; it produces a new Context for upstream operators per Reactor subscriber semantics.
- Context **does not send cookies automatically** and does not persist across subsequent requests.
- A Reactor Context key is an `Object`; `String` works, though in large libraries avoid collisions by using unique constants or class keys.

### 7.1. Propagation direction of contextWrite

An easily confused rule: **Context flows from the subscriber upstream toward the publisher** during subscription, whereas signals/data flow from publisher downstream to subscriber.

~~~text
Source publisher --- map --- flatMap --- contextWrite --- Subscriber
                 <------------------- Context -------
                 -------------------- onNext ------->
~~~

A `contextWrite` placed **downstream** in a chain expression generally makes context visible to `deferContextual`/operators **upstream**. Operators below it do not necessarily see context written above them.

Correct example:

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("correlationId", "missing")))
    .contextWrite(c -> c.put("correlationId", "abc123"));
~~~

On subscription, `result` emits **`abc123`**.

### 7.2. Never treat ThreadLocal like Reactor Context

Error-prone example:

~~~java
static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

Mono<String> result = Mono.just("start")
        .publishOn(Schedulers.parallel())
        .map(v -> REQUEST_ID.get());
~~~

This is a **conceptual anti-pattern**, not a standalone file. If a request ID is set on the HTTP-receiving thread, `publishOn` can move execution to another thread where `REQUEST_ID.get()` becomes `null` (or carries another task's stale value if mismanaged). Never rely on `InheritableThreadLocal` for Reactor event loops/worker pools.

Replace with:

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("correlationId", "missing")))
    .publishOn(Schedulers.parallel())
    .flatMap(id -> Mono.deferContextual(ctx ->
            Mono.just(id + "/" +
                    ctx.getOrDefault("correlationId", "missing"))))
    .contextWrite(c -> c.put("correlationId", "abc123"));
~~~

The subscriber receives **`abc123/abc123`** because Context follows the reactive subscriber even when scheduling switches threads. Do not assume arbitrary custom libraries propagate context if they escape the Reactor chain into independent callbacks/executors.

### 7.3. Never create orphaned side subscriptions

Avoid:

~~~java
@GetMapping("/wrong")
public Mono<String> wrong() {
    service.call().subscribe(); // fire-and-forget
    return Mono.just("accepted");
}
~~~

This anti-pattern can lose cancellation, errors, trace context, and does not guarantee the task completed before the response. Prefer **returning a composed Publisher**:

~~~java
@GetMapping("/right")
public Mono<String> right() {
    return service.call().thenReturn("done");
}
~~~

This is a snippet with an external `service`, not standalone runnable. For real background jobs, use queues/schedulers with clear ownership, retries, auditing, and idempotency rather than arbitrary fire-and-forget from HTTP handlers.

## 8. Injecting Reactor Context into the pipeline from a WebFilter

A Spring WebFlux `WebFilter` receives `ServerWebExchange` and `WebFilterChain`:

~~~java
public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain) {

    String id = "req-42";
    return chain.filter(exchange)
            .contextWrite(ctx -> ctx.put("requestId", id));
}
~~~

This is an illustrative method. It places `requestId` into Context **for the upstream chain upon subscription**, which typically covers downstream handlers/services and nested reactive operators.

Keep the two storage places distinct:

1. `exchange.getAttributes().put("requestId", id)` stores metadata **on the current HTTP exchange**; convenient for filters/handlers sharing the exchange, yet it does not automatically travel into arbitrary nested reactive requests.
2. `.contextWrite(ctx -> ctx.put("requestId", id))` stores metadata **in the reactive subscriber context**; convenient for `Mono.deferContextual` and participating chain operators/filters.

When using `WebClient`, an `ExchangeFilterFunction` can also read Reactor Context when the WebClient publisher is subscribed within the same pipeline:

~~~java
WebClient client = WebClient.builder()
        .filter((request, next) ->
                Mono.deferContextual(ctx -> {
                    String id = ctx.getOrDefault(
                            "requestId", "missing");

                    ClientRequest updated = ClientRequest
                            .from(request)
                            .header("X-Request-Id", id)
                            .build();

                    return next.exchange(updated);
                }))
        .build();
~~~

This is an illustrative snippet requiring `WebClient`, `ClientRequest`, `Mono` imports, and an HTTP URI for real calls. Forward validated correlation IDs only to **trusted** systems; never attach tokens/session IDs automatically to every outbound request or call unvalidated URLs.

## 9. Reactive Security Context and WebSession

Spring Security provides reactive APIs:
- `ReactiveSecurityContextHolder.getContext()`: reads security context from the Reactor subscriber Context.
- `ReactiveSecurityContextHolder.withAuthentication(...)` or `withSecurityContext(...)`: attaches context per security contract.
- `SecurityWebFilterChain`: WebFlux filter chain (distinct from Servlet `SecurityFilterChain`).
- `ServerSecurityContextRepository`: contract to save/load context when the app uses stateful authentication.
- `WebSessionServerSecurityContextRepository`: an implementation that can store `SecurityContext` inside WebSession when configured appropriately.
- `ReactorContextWebFilter`: uses the security context repository to populate Reactor Context with security context.

**Do not equate these three things:**
- `WebSession` exists;
- the user is authenticated;
- a Reactor `SecurityContext` is present on the current subscriber.

A WebSession may hold only UI preferences without authentication. A stateless bearer-token resource server API may **need no server-side session** yet still have a Reactive SecurityContext on every request.

Illustrative code reading the username via reactive security:

~~~java
public Mono<String> currentUser() {
    return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName())
            .defaultIfEmpty("anonymous");
}
~~~

This is an **illustrative method** requiring the reactive Spring Security dependency. When `Authentication` is null or unauthenticated, the application needs a clear policy; never rely on `getName()` as an authorization check. Let Security chains/authorization rules protect endpoints rather than relying on a name string.

### Session security and fixation prevention

- On session-based login, the security framework must enforce an appropriate session fixation protection policy.
- Use `WebSession.changeSessionId()` per lifecycle; never pass session IDs in query parameters.
- Set cookie `Secure`, `HttpOnly`, and `SameSite` flags per use case and deployment; HTTPS is foundational.
- Logout must invalidate or clear server-side authentication state per policy, not merely clear frontend localStorage.
- Enforce CSRF protection whenever using browser cookie-based authentication with state-changing operations.
- Never forward `Authentication`, cookies, or tokens via custom Reactor Context to untrusted services; Context does not encrypt data.

## 10. Runnable Spring Boot 3.x application

This lab uses:
- **WebSession** to write/read a `favoriteColor` choice across two HTTP requests.
- **LocaleContext** from `Accept-Language` to return language tags `vi-VN` / `en-US`.
- **Reactor Context** to propagate `X-Request-Id` across `WebFilter`, `publishOn`, and nested `flatMap`.
- `WebTestClient` to verify session cookies, headers, JSON, and context propagation against a **real HTTP server on a random port**.

The project needs only Java 17+, Spring Boot 3.x with `spring-boot-starter-webflux`, and `spring-boot-starter-test`. Spring Security/Micrometer are omitted because this runnable demo's goal is verifying the three concepts **without depending on an external auth or tracing system**.

### 10.1. Maven and project structure

Use Spring Initializr to create a Java 17+, Maven project in package `com.example.demo`. In `pom.xml`, include dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

This is a **fragment** inside a Maven project generated by Spring Initializr (with parent/BOM, Java version, and build plugins), not a complete standalone `pom.xml`. Avoid adding `spring-boot-starter-web` so the web application type stays reactive.

Create:

~~~text
src/main/java/com/example/demo/
  DemoApplication.java
  RequestContextFilter.java
  ContextController.java
src/test/java/com/example/demo/
  ContextControllerTest.java
~~~

### 10.2. DemoApplication.java

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 10.3. RequestContextFilter.java

~~~java
package com.example.demo;

import java.util.UUID;

import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
public class RequestContextFilter implements WebFilter {

    public static final String REQUEST_ID_CONTEXT_KEY =
            RequestContextFilter.class.getName() + ".requestId";

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String supplied = exchange.getRequest()
                .getHeaders().getFirst("X-Request-Id");

        String id = supplied != null &&
                supplied.matches("[A-Za-z0-9_-]{1,48}")
                ? supplied : UUID.randomUUID().toString();

        exchange.getAttributes().put("requestId", id);
        exchange.getResponse().getHeaders().set("X-Request-Id", id);

        return chain.filter(exchange)
                .contextWrite(context ->
                        context.put(REQUEST_ID_CONTEXT_KEY, id));
    }
}
~~~

**Explanation:**

1. The filter generates a request ID or accepts a client header only if it matches a 1–48 character allowlist, preventing CR/LF and arbitrary data in logs/headers.
2. The same `id` is placed in **exchange attributes**, **response header**, and **Reactor Context**. Each has its own lifecycle.
3. The filter does not create a `WebSession`, does not call a database, and does not store the request ID in a global static mutable field.
4. `contextWrite` sits **after** `chain.filter(exchange)` in the chain because context flows from subscriber upstream.
5. In production, never treat a client-supplied ID as proof of identity; even correlation IDs from a trusted gateway must be validated and never used as authorization tokens.
6. The `HttpHeaders` import in this file is unused (not referenced directly) yet causes no compilation error; it can be removed if style checks forbid unused imports.

### 10.4. ContextController.java

~~~java
package com.example.demo;

import java.util.Locale;

import org.springframework.context.i18n.LocaleContext;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebSession;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
@RequestMapping("/api/context")
public class ContextController {

    @GetMapping("/state")
    public Mono<StateView> state(
            WebSession session,
            ServerWebExchange exchange) {

        String language = localeTag(exchange);
        String color = session.getAttribute("favoriteColor");

        return Mono.deferContextual(context ->
                Mono.just(new StateView(
                        language,
                        color,
                        context.getOrDefault(
                                RequestContextFilter.REQUEST_ID_CONTEXT_KEY,
                                "missing"),
                        session.isStarted())));
    }

    @PostMapping("/favorite/{color}")
    public Mono<StateView> favorite(
            @PathVariable("color") String color,
            ServerWebExchange exchange) {

        if (!color.matches("[a-z]{1,16}")) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "invalid color"));
        }

        return exchange.getSession()
                .flatMap(session -> {
                    session.getAttributes().put("favoriteColor", color);

                    return Mono.deferContextual(context ->
                            Mono.just(new StateView(
                                    localeTag(exchange),
                                    color,
                                    context.getOrDefault(
                                      RequestContextFilter.REQUEST_ID_CONTEXT_KEY,
                                      "missing"),
                                    session.isStarted())));
                });
    }

    @PostMapping("/invalidate")
    public Mono<Void> invalidate(WebSession session) {
        return session.invalidate();
    }

    @PostMapping("/rotate")
    public Mono<Void> rotate(WebSession session) {
        return session.changeSessionId();
    }

    @GetMapping("/hop")
    public Mono<HopView> hop() {
        return Mono.deferContextual(context ->
                        Mono.just(context.getOrDefault(
                                RequestContextFilter.REQUEST_ID_CONTEXT_KEY,
                                "missing")))
                .publishOn(Schedulers.parallel())
                .flatMap(before -> Mono.deferContextual(context ->
                        Mono.just(new HopView(
                                before,
                                context.getOrDefault(
                                  RequestContextFilter.REQUEST_ID_CONTEXT_KEY,
                                  "missing")))));
    }

    private static String localeTag(ServerWebExchange exchange) {
        LocaleContext context = exchange.getLocaleContext();
        Locale locale = context.getLocale();
        return locale == null ? "und" : locale.toLanguageTag();
    }

    public record StateView(
            String locale,
            String favoriteColor,
            String requestId,
            boolean sessionStarted) {}

    public record HopView(
            String beforeHop,
            String afterHop) {}
}
~~~

**Observing the three mechanisms in action:**

- `state`: the framework injects `WebSession` into the handler and reads `favoriteColor` if present. Calling this handler **does not start a session** when only reading attributes.
- `favorite`: `exchange.getSession()` returns `Mono<WebSession>`; adding attribute `favoriteColor` starts the session, and the framework writes a session ID cookie upon saving.
- `localeTag`: reads locale from `LocaleContextResolver`, driven by `Accept-Language` in default config; does not alter session data.
- `Mono.deferContextual`: reads request ID from the reactive subscriber Context without `ThreadLocal`.
- `hop`: uses `publishOn(Schedulers.parallel())` to hop execution across schedulers; `beforeHop` and `afterHop` are still retrieved from the same Reactor Context. Do not assert thread names since scheduler implementations/timing are not business contracts.
- `invalidate` and `rotate`: return the underlying publishers for the framework to subscribe to. Never call `.block()` on an event-loop thread.

**Design warning:** the demo uses `favoriteColor`, which is small, non-sensitive data. Never let clients inject arbitrary serialized objects into sessions or store tokens/passwords/raw requests there.

### 10.5. ContextControllerTest.java

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive
        .AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ContextControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void readOnlyRequestDoesNotStartNewSession() {
        EntityExchangeResult<ContextController.StateView> result =
                client.get()
                        .uri("/api/context/state")
                        .header(HttpHeaders.ACCEPT_LANGUAGE, "vi-VN")
                        .header("X-Request-Id", "req-read")
                        .exchange()
                        .expectStatus().isOk()
                        .expectHeader().valueEquals(
                                "X-Request-Id", "req-read")
                        .expectBody(ContextController.StateView.class)
                        .returnResult();

        ContextController.StateView body = result.getResponseBody();
        assertNotNull(body);
        assertEquals("vi-VN", body.locale());
        assertEquals("req-read", body.requestId());
        assertFalse(body.sessionStarted());
    }

    @Test
    void webSessionPersistsAcrossRequestsWithCookie() {
        EntityExchangeResult<ContextController.StateView> created =
                client.post()
                        .uri("/api/context/favorite/blue")
                        .header("X-Request-Id", "req-save")
                        .exchange()
                        .expectStatus().isOk()
                        .expectBody(ContextController.StateView.class)
                        .returnResult();

        ContextController.StateView saved = created.getResponseBody();
        assertNotNull(saved);
        assertTrue(saved.sessionStarted());
        assertEquals("blue", saved.favoriteColor());

        ResponseCookie cookie =
                created.getResponseCookies().getFirst("SESSION");
        assertNotNull(cookie);

        client.get()
                .uri("/api/context/state")
                .cookie("SESSION", cookie.getValue())
                .header(HttpHeaders.ACCEPT_LANGUAGE, "en-US")
                .header("X-Request-Id", "req-read-again")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.locale").isEqualTo("en-US")
                .jsonPath("$.favoriteColor").isEqualTo("blue")
                .jsonPath("$.requestId").isEqualTo("req-read-again")
                .jsonPath("$.sessionStarted").isEqualTo(true);
    }

    @Test
    void reactorContextSurvivesSchedulerHop() {
        client.get()
                .uri("/api/context/hop")
                .header("X-Request-Id", "req-hop")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.beforeHop").isEqualTo("req-hop")
                .jsonPath("$.afterHop").isEqualTo("req-hop");
    }

    @Test
    void invalidColorIsRejected() {
        client.post()
                .uri("/api/context/favorite/RED123")
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

**Why is this test useful?**

- `@SpringBootTest(RANDOM_PORT)` and `@AutoConfigureWebTestClient` create HTTP integration tests against an embedded reactive server rather than invoking Java methods directly.
- The first test verifies **reading an unstarted session** and Locale from the request; if another security filter/library intentionally starts a session, adjust conditions accordingly since policy changed.
- The second test extracts the `SESSION` cookie from the **first** response, explicitly sends it back on the **next** request, and verifies `favoriteColor` persisted.
- The `hop` test confirms Reactor Context remains available after `publishOn` and `flatMap`, without relying on ThreadLocal or thread names.
- The last test demonstrates controller validation, unrelated to session IDs.
- The tests do not assume an HTTP client maintains a cookie jar automatically; they **extract and pass cookies explicitly** to verify request isolation.

In production or when adding Spring Security, update tests for authentication/CSRF rules. The example omits Security dependencies so simple `POST`s work directly.

### 10.6. Running and testing with curl

Run:

~~~bash
./mvnw spring-boot:run
~~~

On Windows use `mvnw.cmd spring-boot:run`; if no wrapper exists and Maven is installed, run `mvn spring-boot:run`.

Read state without a cookie:

~~~bash
curl -i   -H "Accept-Language: vi-VN"   -H "X-Request-Id: req-001"   http://localhost:8080/api/context/state
~~~

Expected body with corresponding fields:

~~~json
{
  "locale": "vi-VN",
  "favoriteColor": null,
  "requestId": "req-001",
  "sessionStarted": false
}
~~~

The `favoriteColor: null` field may be omitted by Jackson if the project configures excluding null properties. What matters is that there is no color and WebSession has not started. Do not rely on JSON key order.

Save cookie when picking a color:

~~~bash
curl -i -c cookies.txt   -X POST   -H "X-Request-Id: req-save"   http://localhost:8080/api/context/favorite/blue
~~~

Browsers/clients typically receive `Set-Cookie: SESSION=...` once the session starts/saves. `-c cookies.txt` tells curl to save cookies to a jar file.

Read the session back:

~~~bash
curl -i -b cookies.txt   -H "Accept-Language: en-US"   -H "X-Request-Id: req-next"   http://localhost:8080/api/context/state
~~~

Expected: `favoriteColor` stays **blue**, locale is **en-US**, and `requestId` is **req-next**. This clearly demonstrates three independent scopes: session persists state across HTTP requests, locale changes per request header, and Reactor Context is created fresh per subscription.

Test scheduler hop:

~~~bash
curl -i   -H "X-Request-Id: rid-hop"   http://localhost:8080/api/context/hop
~~~

Expected JSON:

~~~json
{"beforeHop":"rid-hop","afterHop":"rid-hop"}
~~~

**Never send session IDs to public logs or copy cookie files containing IDs to other systems.** Curl cookie jars should only be used for local testing as they may contain sensitive tokens.

## 11. Propagating Context through nested WebClient calls

Reactor Context is useful when a `WebFilter` captures correlation metadata and later `WebClient` calls another microservice. Spring WebFlux supports reading Context inside an `ExchangeFilterFunction` via `Mono.deferContextual`.

Illustrative service:

~~~java
@Service
public class PartnerClient {
    private final WebClient client;

    public PartnerClient(WebClient.Builder builder) {
        this.client = builder
                .baseUrl("https://partner.example.com")
                .filter((request, next) ->
                        Mono.deferContextual(context -> {
                            String rid = context.getOrDefault(
                                RequestContextFilter.REQUEST_ID_CONTEXT_KEY,
                                "missing");
                            ClientRequest withId = ClientRequest
                                    .from(request)
                                    .header("X-Request-Id", rid)
                                    .build();
                            return next.exchange(withId);
                        }))
                .build();
    }

    public Mono<String> getInfo(long id) {
        return client.get()
                .uri("/data/{id}", id)
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

**This is an additional illustrative class** and does not run standalone with section 10's example because `partner.example.com` is a sample domain; a real service and dependencies are needed. Imports include `@Service`, `WebClient`, `ClientRequest`, `Mono`. In real code, verify upstream trust boundaries, timeouts, retries, TLS, and avoid leaking sensitive data in headers inadvertently.

Important note: context propagation through a Reactor chain works when the **WebClient Publisher is subscribed to as part of a chain holding the right Context**. If a service breaks out into `new Thread(...)`, `CompletableFuture.supplyAsync(...)`, or a standalone `subscribe()`, context propagation is not automatic. When switching concurrency models, capture immutable metadata explicitly or use Micrometer Context Propagation properly.

## 12. Reactor Context, MDC, and Micrometer: observability

Many systems use SLF4J MDC:

~~~java
MDC.put("requestId", "rid-1");
~~~

Yet MDC is mostly backed by **ThreadLocal**. In WebFlux, signals for one request can traverse different threads. Setting MDC once in a filter and assuming every callback reads it is **unsafe**.

Recommended approach:
1. Keep correlation metadata in **Reactor Context** or tracing/observation contexts supported by instrumentation.
2. Use **Micrometer Context Propagation** and registered `ThreadLocalAccessor`s when bridging to MDC/ThreadLocal-based APIs.
3. Explicitly choose automatic vs explicit context propagation fitting your Reactor/Spring versions; avoid accidentally enabling multiple uncontrolled global hooks.
4. When using a custom `TaskDecorator`, capture/restore inside `finally` and do not assume it automatically propagates all Reactor subscriber Context.
5. Never place bearer tokens, raw session IDs, passwords, or PII in tracing baggage/logs.
6. Test trace IDs across `publishOn`, `flatMap`, WebClient, retries, and errors/cancellations.

A safer way to read IDs in business pipelines is `Mono.deferContextual(ctx -> ...)` instead of `MDC.get(...)`. When Spring Boot Actuator, Micrometer tracing, and security integration are present, follow your exact version's docs before writing a manual global context mechanism.

## 13. Relationship with reactive Spring Session and scaling

An in-memory session store suits demos or single-instance apps. In multi-replica deployments:

~~~text
Browser
   |
Load balancer
   +---- Pod A: local WebSessionStore
   +---- Pod B: local WebSessionStore
   +---- Pod C: local WebSessionStore
~~~

If a browser sends a session ID stored on Pod A and the next request hits Pod B, Pod B may not find that session. Solutions include:
- Infrastructure-level sticky sessions (with limitations; failover is harder).
- **Spring Session** with Redis/a compatible reactive session repository to share storage across app instances.
- Stateless auth or storing preferences in a profile database and avoiding HTTP sessions when unnecessary.

With reactive Spring Session:
- Ensure dependencies/repositories support WebFlux, reactive connection factories, serialization, and expiration.
- Never store non-serializable object graphs or mutable data modified concurrently across requests without conflict control.
- Measure Redis/session-store latency and availability — session lookup becomes I/O on every request needing to read it.
- Enforce TTLs and security for Redis credentials, network access, backups, and key namespaces.
- If Spring Security stores `SecurityContext` in WebSession, test the behavior of the security context repository, session fixation, and logout.

**Do not assume WebSession is a Redis database session by default.** It is merely an interface; the backing storage depends on configuration.

## 14. Should Locale be chosen from user profile or WebSession?

Suppose a multilingual app lets users choose Vietnamese directly in the web UI. Multiple locale sources exist:

1. Browser's `Accept-Language` — a hint sent by the client per request.
2. Language preference in the **user profile** (durable across devices and logins).
3. Language preference in **WebSession** (relevant only to the current session).
4. URL locale segment such as `/vi/.../` or query param `lang=vi`.
5. Product default locale.

You must design a priority order, for instance:

~~~text
Authenticated user profile
   > explicit validated language selection in current session
   > Accept-Language compatible supported locale
   > product default
~~~

This is only an **illustrative policy**: an app may prioritize URL locale over session for SEO/bookmarking depending on design.

When handling user language choices:
- Accept only locales from an allowlist (`vi-VN`, `en-US`, etc.).
- If saving into the session, apply it explicitly in the locale resolution pipeline for subsequent requests. Simply calling `put("language", "vi")` **does not make** `AcceptHeaderLocaleContextResolver` read the session automatically.
- Never infer timezone from locale; store the user's timezone separately, e.g., an IANA ZoneId.
- For cached responses, `Content-Language`, `Vary: Accept-Language`, and user-specific caching must be consistent.
- When localization affects API error messages, ensure two language variants never share the same shared cache key.

## 15. When to use session, exchange attributes, or Reactor Context?

| Scenario | Preferred solution | Rationale |
| --- | --- | --- |
| User selects dark-mode UI persisted across requests | WebSession or profile DB | Needs state outliving a single request |
| Correlation ID of the current HTTP request | Reactor Context + HTTP response header | Propagates through reactive pipeline, request-scoped |
| A filter needs to set a flag for a handler in the same exchange | `exchange.getAttributes()` | Shares the current exchange object |
| Formatting dates/times per current locale | `LocaleContext` + timezone policy | Request-scoped locale; handle timezone separately |
| Storing cart/inventory requiring concurrency transactions | DB, not just session attributes | Consistency/locking |
| Authentication principal in reactive code | `ReactiveSecurityContextHolder` | Consistent security model |
| OAuth bearer token clients | Security filter/authentication, typically stateless | Avoids unnecessarily creating a WebSession |
| Passing request ID through nested WebClient calls | Reactor Context + WebClient filter | Subscriber metadata travels along the chain |
| Separate Java thread outside the Reactor chain | Explicit immutable snapshot/propagation bridge | Reactor Context does not magically jump arbitrary threads |
| System-wide fixed locale | Fixed/accept-header locale resolver config | No need to store locale in session |
| Logging inside an MDC-only library | Micrometer context propagation/bridge | MDC thread-local is not automatically preserved |
| Forwarding session ID to upstream services | **Generally avoid** | Credential leakage / trust boundary violation |

Do not create a stateful session just to pass a request ID, and do not store a shopping cart in Reactor Context expecting the next request to still see it.

## 16. Common pitfalls and diagnostics

| Symptom | Common cause | How to check |
| --- | --- | --- |
| `getSession()` called yet no SESSION cookie | Session was only read, not started | Check `isStarted()`, write an attribute or call `start()` |
| Color picked yet next GET forgets it | Client omitted cookie, session expired, or hit another node | Inspect Cookie/Set-Cookie, store, load balancer |
| Session ID exists yet state is wrong | Concurrent writes, store reset, mutable attributes | Check store and races/lifecycle |
| Logout calls `invalidate()` yet session stays | Ignored publisher, never returned/subscribed | Return `session.invalidate()` in the chain |
| `getLocaleContext()` always matches request header | Default AcceptHeader resolver | Custom resolver needed to override preference |
| `setLocaleContext` throws UnsupportedOperationException | AcceptHeader resolver forbids altering client header | Custom policy or profile/session storage |
| Locale is vi-VN yet timezone is wrong | Locale does not determine timezone | Use separate ZoneId, TimeZoneAware context if needed |
| `MDC.get("rid")` disappears after publishOn | Thread-local does not cross scheduler hops | Reactor Context or propagation bridge |
| `contextWrite` never reaches intended target | Placed on wrong side relative to subscribe or separate chain | Inspect `deferContextual` and operator ordering |
| Request returns response yet background task fails silently | Standalone `subscribe()` inside handler | Return/compose Publisher, or use proper job queue |
| Spring Security `SecurityContextHolder` is null | Confusing servlet thread-local with reactive security model | Use ReactiveSecurityContextHolder / SecurityWebFilterChain |
| WebSession cookie works locally yet fails on scale | In-memory store not shared across pods | Reactive Spring Session Redis or sticky sessions |
| HTTP response committed, session changes lost | Writing session too late after response | Order async lifecycle and session save properly |
| SameSite/CORS stops cookie sending | Cross-site policy/credentials mismatch | DevTools, cookie flags, allow-origin/credentials |
| Session holds sensitive secrets | Storing credentials/PII unnecessarily | Minimize session data, encrypt storage, access policies |
| Enabling Secure cookie on HTTP tests drops cookie | Browser blocks Secure over plain HTTP | Test over HTTPS or configure per environment |
| Request ID from header contains CRLF | Unvalidated input | Regex allowlist, or generate ID server-side |
| Endpoint returns Mono yet JDBC blocks | Blocking library stays blocking | Use reactive driver or appropriate bounded scheduler |

### Systematic debugging

1. Capture exact request and response headers with DevTools/curl: `Cookie`, `Set-Cookie`, `Accept-Language`, `X-Request-Id`.
2. Check whether the session has **started**, whether the browser sends the ID back, which node holds the store, and its TTL.
3. Inspect actual `WebSession` attributes, stored data types, concurrent requests, and saved versions.
4. Check which `LocaleContextResolver` is registered, how supported locales match, timezone strategy, and default locale.
5. Inspect the Reactor pipeline before and after `publishOn`/`flatMap` via `Mono.deferContextual`; never infer from MDC.
6. If Spring Security is present, check `SecurityWebFilterChain` and the repository used by reactive auth rather than setting state manually.
7. Test authorization/CSRF/CORS in browsers, session cookie rotation/logout, and session timeouts beyond unit demos.
8. When scaling, monitor Redis/store, evictions, serialized session sizes, cookie counts, p95 latency, and failure modes.

## 17. Security and performance: review checklist

### Security

- Session cookies use `Secure` on HTTPS, plus `HttpOnly`/`SameSite` aligned with the app and auth flow.
- Session ID is a sensitive credential: never log it, put it in URLs, or pass it to third parties via Reactor Context.
- Session fixation protection and logout/invalidation are coordinated by security policies.
- CSRF protection is active for cookie-based session auth and unsafe methods.
- WebSession storage enforces TTLs, quotas, and network access controls; avoid storing credentials/passwords or heavy object graphs.
- CORS allows only authorized origins, especially with `credentials: include`.
- Correlation ID inputs are validated and never used as user identity or ACLs.
- Never leak security contexts in JSON/logs; principal extraction must accompany proper authorization.
- User preference inputs (language, timezone, theme, etc.) are validated.
- In multi-tenant systems, sessions and caches stay strictly bound to tenant/user; never mix session state into static singleton mutable fields.

### Performance

- Do not start a session on every anonymous GET unnecessarily.
- Do not store large lists/carts in WebSession, inflating memory/Redis traffic.
- With Redis-backed Spring Session, measure lookup/save latency and serialization cost; the session store itself can become a bottleneck.
- Never use ThreadLocal to pass request state across Reactor scheduler hops.
- Bound `WebClient` connections, Reactor schedulers/buffers, and API concurrency; context propagation does not replace quotas.
- For frequent cross-request preferences, consider a profile DB/cache with clear invalidation.
- Align session idle timeout and cookie max-age consistently.
- Separate request-scoped correlation IDs from profile state; avoid stuffing oversized baggage into traces.
- Test in real multi-node/proxy environments, not just a single local embedded server.

## 18. Review questions

**1. Does `ServerWebExchange.getSession()` always create a cookie?**

No. It returns an existing or new WebSession object; a new session only starts when attributes are added or `start()` is called, and is saved per lifecycle.

**2. Why is `session.invalidate(); return Mono.empty();` wrong?**

Because `invalidate()` returns a reactive Publisher; without composing/returning it, subscription/execution is not guaranteed. Return the Publisher from the handler.

**3. Is `WebSession` Servlet's `HttpSession`?**

No. WebSession is Spring WebFlux's reactive session contract with its own resolver/store. Never cast it to Servlet HttpSession.

**4. Does locale `vi-VN` automatically imply timezone `Asia/Ho_Chi_Minh`?**

No. Locale and timezone are independent; the default resolver reads Accept-Language and provides no timezone automatically.

**5. If a user picks `en-US` stored in WebSession, does the default resolver use it automatically?**

No. `AcceptHeaderLocaleContextResolver` relies on request headers and configured supported/default locales. Custom logic/resolver is needed to apply session preferences.

**6. Does Reactor Context survive across HTTP requests?**

Not automatically. It is bound to a reactive subscription. To persist preferences across requests, use sessions, profile DBs, or cookies.

**7. Why are `ThreadLocal`/MDC lost after `publishOn`?**

Signals can run on a different thread; ThreadLocal is bound to a JVM thread rather than the subscriber. Use Reactor Context and a propagation bridge when needed.

**8. In which direction does `contextWrite` propagate context?**

During subscription, Context flows from the subscriber (downstream) toward upstream operators; `onNext` data flows in the opposite direction.

**9. Must a stateless bearer-token API create a WebSession to have a security context?**

No. Reactive Spring Security can populate SecurityContext per request/subscription without creating a server-side session.

**10. What is the risk of using an in-memory session store across three pods?**

A cookie ID created on Pod A may not find its state on Pod B. You need a shared reactive session store or appropriate infrastructure routing.

**11. In the demo test, what does having `vi-VN` on the first request and `en-US` on the second while keeping `blue` demonstrate?**

`WebSession` retains `favoriteColor` across requests via the cookie, Locale changes per request, and Reactor Context request IDs are also created per subscription.

**12. Should Reactor Context be used to store a session shopping cart?**

Not appropriate. It does not persist across requests; store carts in a database or state store/session per consistency requirements.

## 19. Practical implementation checklist

1. Identify **scope** first: multi-request user state → WebSession/profile; single-exchange metadata → exchange attributes; reactive subscription metadata → Reactor Context; request locale → LocaleContextResolver.
2. When only reading a session, avoid `start()` unnecessarily; when writing or logging out, compose reactive operations along the lifecycle.
3. For session IDs, enforce TLS, cookie flags, CSRF, rotation, invalidation, and auth policies.
4. Bound session attribute sizes; avoid mutable state, secrets, and hard-to-serialize object graphs.
5. Design a shared session repository when scaling multiple instances; test cookies, TTL, failover, and concurrency.
6. Use `exchange.getLocaleContext()` in reactive handlers; never infer timezone from locale.
7. Define language precedence across URL/profile/session/Accept-Language and implement a custom resolver when needed.
8. Use `Mono.deferContextual`/`contextWrite` to propagate correlation/tracing metadata across Reactor chains; never rely on request ThreadLocals.
9. Never call `subscribe()` inside controllers for work whose outcome must be reported; return a composed Publisher.
10. Integrate `ReactiveSecurityContextHolder` in WebFlux security, keeping it distinct from Session and Servlet SecurityContextHolder.
11. Test with `WebTestClient` over real HTTP sockets: session cookies before/after, locale headers, context scheduler hops, logout, and invalid data.
12. Evaluate CORS, CSRF, session store/Redis, latency, memory, context propagation, and tracing under production-like load.

## Official references

- [Spring Framework 6.2 — WebFlux reactive core, WebSessionManager and LocaleContextResolver](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — WebSession Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/server/WebSession.html)
- [Spring Framework 6.2 — ServerWebExchange Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/server/ServerWebExchange.html)
- [Spring Framework 6.2 — LocaleContextResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/server/i18n/LocaleContextResolver.html)
- [Spring Framework 6.2 — AcceptHeaderLocaleContextResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/server/i18n/AcceptHeaderLocaleContextResolver.html)
- [Spring Framework 6.2 — WebClient Reactor Context](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-context.html)
- [Spring Framework 6.2 — WebFlux @SessionAttributes](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/sessionattributes.html)
- [Spring Boot 3.5 — Common Application Properties (reactive session)](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [Spring Security 6.x — Reactive SecurityContextHolder](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/index.html)
- [Project Reactor — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Spring Session — WebFlux custom cookies](https://docs.spring.io/spring-session/reference/guides/boot-webflux-custom-cookie.html)
