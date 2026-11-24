# Cookies, Starting a Session, and Invalidating a Session in Spring WebFlux

> **Module:** Spring Framework – reactive · **Parent topic:** Filters and Sessions. This lesson explains two mechanisms that often appear together but play different roles: HTTP cookies are sent by the browser via request/response, whereas `WebSession` is server-side state accessed by session ID. The content covers `@CookieValue` and `ResponseCookie` through creating a session, storing attributes, changing the session ID, expiration, logout, resolver/store configuration, security, and testing across multiple HTTP requests.

## 1. Learning Objectives

After this lesson, you can:

1. Read cookies from an annotated controller with `@CookieValue` or from the request with `ServerWebExchange`/`ServerRequest`.
2. Create, configure, and delete cookies with `ResponseCookie`, `ServerHttpResponse.addCookie`, or `ServerResponse.cookie`.
3. Distinguish a cookie containing application data from a cookie carrying only a **session ID**.
4. Get `WebSession` with `ServerWebExchange.getSession()` or the `WebSession` controller parameter.
5. Understand when a session is actually started, when attributes are saved, and when the session ID is sent back to the client.
6. Implement login/session rotation, read and update session attributes, log out with `invalidate()`, and set an idle timeout.
7. Choose `WebSessionIdResolver`, `WebSessionStore`, and Spring Session Redis when sessions must be shared across multiple instances.
8. Apply `HttpOnly`, `Secure`, `SameSite`, CSRF protection, and safe session ID handling rules.
9. Test cookies/sessions with HTTP integration tests that have a cookie jar, rather than only calling Java methods.

**Core distinction:** a cookie is data the client sends in the `Cookie` header; `WebSession` is a server-side state abstraction. A session cookie usually carries only an opaque ID for the server to look up the session. Do not confuse the session ID with the entire session data.

## 2. How Do HTTP Cookies Work?

A cookie is a name/value pair the server asks the browser to store. The server sends cookies in the `Set-Cookie` response header; on matching requests, the browser sends the cookies back via the `Cookie` header.

~~~text
First time:
Browser  -- GET /profile --------------------------> Server
Browser  <-- 200 + Set-Cookie: theme=dark; Path=/ -- Server

Next request:
Browser  -- GET /profile
             Cookie: theme=dark -------------------> Server
Browser  <-- 200 ----------------------------------- Server
~~~

The two directions use different headers:

| Direction | Header | Content |
| --- | --- | --- |
| Server → browser | `Set-Cookie` | Instructs the browser to save/update/delete a cookie and its attributes. |
| Browser → server | `Cookie` | Sends the cookie name/value pairs applicable to the current request. |

The browser decides whether to send a cookie based on domain, path, expiration, `Secure`, `SameSite`, and browser cookie rules. JavaScript cannot read cookies with `HttpOnly`; `Secure` cookies are sent only over HTTPS connections (the localhost exception depends on browser rules).

**A cookie is not a trustworthy secret store.** Users can modify unprotected cookies and send arbitrary values. The server must validate every incoming cookie; if client-side data needs to be trusted, it must be signed/MACed or encrypted and still checked for authorization on the server.

### 2.1. Important Attributes

| Attribute | Meaning | How to choose |
| --- | --- | --- |
| `Path` | Which request paths may send the cookie | Choose the narrowest path that still fits the application; `/` applies to the whole host/path. |
| `Domain` | Allows the cookie to apply to the host and matching subdomains | Usually omit to make the cookie host-only; avoid expanding to all subdomains if unnecessary. |
| `Max-Age` | Lifetime measured from when the cookie is received | Positive number is duration; `0` deletes immediately; negative means no Max-Age, usually a browser session cookie. |
| `Expires` | Absolute expiration timestamp | Browsers can use it alongside Max-Age; Max-Age usually takes precedence. |
| `Secure` | Send cookie only over HTTPS | Enable for production cookies, especially session/auth cookies. |
| `HttpOnly` | Disallow JavaScript reading the cookie via `document.cookie` | Enable for session ID and credential cookies. |
| `SameSite` | Restrict sending cookies in cross-site contexts | `Strict`, `Lax`, or `None` per navigation flow; `None` requires `Secure` in modern browsers. |
| `Partitioned` | Cookie partitioned by top-level site in certain contexts | Use only when there is a specific third-party/embedded requirement. |

`HttpOnly` reduces the chance of scripts stealing the cookie via XSS, but does not prevent XSS from making requests on the user's behalf. `SameSite` helps reduce CSRF, but does not replace CSRF tokens/Origin validation and appropriate security policies.

### 2.2. Session Cookies and Application-Data Cookies Differ

| Type | Example | Who holds the primary data? |
| --- | --- | --- |
| UI preference cookie | `theme=dark` | Browser holds the value; server reads each request. |
| Choice-remembering cookie | `locale=vi` | Browser holds non-sensitive value. |
| Session ID cookie | `SESSION=<opaque-id>` | Browser holds the ID; server looks up `WebSession`. |
| Authentication token cookie | Access/refresh token | Must follow its own token design, signature, rotation, expiration, and threat model. |

Do not put passwords, raw access tokens, payment information, or the entire session object into ordinary cookies. With `WebSession`, the cookie carries only the session ID; attributes reside in the server-side `WebSessionStore`/repository.

## 3. Reading Cookies in WebFlux

### 3.1. Annotated Controller with `@CookieValue`

`@CookieValue` binds a cookie value to a method argument. Spring supports type conversion if the parameter is not `String`.

~~~java
@RestController
class ThemeController {

    @GetMapping("/api/theme")
    Map<String, String> theme(
            @CookieValue(
                name = "theme",
                required = false,
                defaultValue = "system"
            ) String theme) {

        return Map.of("theme", theme);
    }
}
~~~

- If the request has `Cookie: theme=dark`, the method receives `"dark"`.
- If there is no cookie, `defaultValue` is used and `required` implicitly becomes `false`.
- If `required=false` is omitted and there is no `defaultValue`, the cookie is required by default; a missing cookie causes an argument resolution error.
- If you declare a parameter of type `int`, `long`, enum, or a type with a converter, Spring can convert the value from string to the target type.

Do not use `@CookieValue` to read WebFlux's session ID if your goal is to access the session; use `WebSession`. Reading the ID directly is only needed for special protocol integration cases.

### 3.2. Reading Cookies via `ServerWebExchange`

`ServerWebExchange` provides the request and response of the HTTP exchange. Request cookies can be read via `ServerHttpRequest.getCookies()`:

~~~java
@GetMapping("/api/cookie-map")
Map<String, String> readCookie(ServerWebExchange exchange) {
    HttpCookie cookie = exchange.getRequest()
        .getCookies()
        .getFirst("theme");

    String value = cookie == null ? "system" : cookie.getValue();
    return Map.of("theme", value);
}
~~~

`getCookies()` is a `MultiValueMap<String, HttpCookie>`; one cookie name can appear with multiple values depending on request/path/domain. `getFirst` gets the first value, so if the system accepts multiple cookies with the same name, you must define a clear rule rather than assuming there is always only one.

### 3.3. WebFlux.fn Reading Cookies with `ServerRequest`

With functional endpoints, the request provides `cookies()`:

~~~java
Mono<ServerResponse> theme(ServerRequest request) {
    HttpCookie cookie = request.cookies().getFirst("theme");
    String value = cookie == null ? "system" : cookie.getValue();

    return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("theme", value));
}
~~~

Annotated controllers and functional handlers use the same request cookie model; the difference lies in how the data is retrieved.

## 4. Creating and Deleting Cookies in the Response

### 4.1. Using `ResponseCookie`

`ResponseCookie` extends `HttpCookie` with attributes that only make sense in a `Set-Cookie` response. Create a cookie with the builder:

~~~java
ResponseCookie cookie = ResponseCookie.from("theme", "dark")
    .path("/")
    .httpOnly(true)
    .secure(true)
    .sameSite("Lax")
    .maxAge(Duration.ofDays(30))
    .build();
~~~

The builder lets you set name/value, path, domain, max-age, secure, http-only, same-site, and partitioned. In a production example, `Secure=true` requires HTTPS. If a demo runs on HTTP localhost, separate the configuration by profile instead of turning off `Secure` in production.

### 4.2. Writing Cookies via `ServerHttpResponse`

~~~java
@PostMapping("/api/theme")
Mono<ResponseEntity<Void>> setTheme(ServerHttpResponse response) {
    ResponseCookie cookie = ResponseCookie.from("theme", "dark")
        .path("/")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .maxAge(Duration.ofDays(30))
        .build();

    response.addCookie(cookie);
    return Mono.just(ResponseEntity.noContent().build());
}
~~~

`addCookie` adds the `ResponseCookie` to the response before the response commits. Do not call it after the response has committed. Because the response is reactive, create the cookie before returning the Publisher; do not open a secondary subscription to try writing headers afterward.

### 4.3. Deleting a Cookie

To make the browser delete a cookie, the server sends back the same name and same scope (`Path`, `Domain`) with `Max-Age=0` or `Expires` in the past:

~~~java
ResponseCookie expired = ResponseCookie.from("theme", "")
    .path("/")
    .httpOnly(true)
    .secure(true)
    .sameSite("Lax")
    .maxAge(Duration.ZERO)
    .build();

response.addCookie(expired);
~~~

If the original cookie had `Domain=example.com` and `Path=/app`, the deletion cookie must use the same scope. Sending a cookie with the same name but a different path/domain can create a new cookie instead of deleting the old cookie.

### 4.4. Functional Endpoint Writing a Cookie

~~~java
Mono<ServerResponse> setTheme() {
    ResponseCookie cookie = ResponseCookie.from("theme", "dark")
        .path("/")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .maxAge(Duration.ofDays(30))
        .build();

    return ServerResponse.noContent()
        .cookie(cookie)
        .build();
}
~~~

`ServerResponse` builder has `cookie(ResponseCookie)` and `cookies(...)`; the server will write `Set-Cookie` when the response is written. Choose one response builder to own the status/headers/body/cookies of that response.


## 5. What Is WebSession?

`WebSession` is Spring WebFlux's abstraction for server-side state that persists across multiple HTTP requests. A session usually has:
- A unique session ID.
- An attribute map (`getAttributes()`).
- Creation time, last access time.
- Maximum idle time.
- Started/expired state.
- Operations to change ID, save, and invalidate.

`ServerWebExchange.getSession()` returns `Mono<WebSession>` for the current request. `WebSession` can also be injected directly into an annotated controller method:

~~~java
@GetMapping("/api/session/profile")
Mono<Profile> profile(WebSession session) {
    return Mono.justOrEmpty(session.<Profile>getAttribute("profile"));
}
~~~

A session does not create data by itself just because a method receives `WebSession`. Getting the session ensures there is an object matching the request's session ID or a new session; **it does not automatically start the session**.

### 5.1. Session ID Cookie and Server-Side Data

~~~text
Browser
  Cookie: SESSION=<opaque-session-id>
             |
             v
       WebSessionManager
             |
       WebSessionIdResolver
             |
       WebSessionStore / repository
             |
             v
     WebSession + attributes
       user = "Ada"
       cart = ...
       csrf state = ...
~~~

The browser sends the ID; the server uses the ID to find the session. The client must not treat the ID as business data and should not modify that value itself. If the ID is missing, invalid, or the session has expired, the manager creates a new session.

### 5.2. `getSession()` Does Not Mean the Session Has Started

~~~java
@GetMapping("/session-check")
Mono<String> check(ServerWebExchange exchange) {
    return exchange.getSession().map(session ->
        "started=" + session.isStarted());
}
~~~

If a new session has no attributes yet and `start()` has not been called, `isStarted()` can be `false`. Not started means the ID does not need to be sent to the browser; session `save()` in that state essentially does nothing.

There are two ways to start a session:
1. Call `session.start()` if you need to create a session even without attributes yet.
2. Add a session attribute; this starts the session implicitly.

~~~java
Mono<String> startExplicitly(ServerWebExchange exchange) {
    return exchange.getSession().map(session -> {
        session.start();
        return "started=" + session.isStarted();
    });
}
~~~

There is no need to call `start()` if you add an attribute immediately afterward. Choose explicit start when the session truly needs to exist before any data is stored.

## 6. Storing and Reading Session Attributes

### 6.1. Writing Attributes

~~~java
Mono<SessionView> createSession(WebSession session) {
    session.getAttributes().put("user", "Ada");
    session.getAttributes().put("cartCount", 2);
    return Mono.just(new SessionView("Ada", 2));
}
~~~

`getAttributes()` returns a mutable map. Attributes are kept in the session store and can be read on the next request with the same session ID. Use stable key names, clear data types, and small data; do not put a large domain graph into the session.

### 6.2. Reading Attributes Safely

~~~java
Mono<SessionView> readSession(WebSession session) {
    String user = session.getAttribute("user");
    int cartCount = session.getAttributeOrDefault("cartCount", 0);

    if (user == null) {
        return Mono.empty();
    }

    return Mono.just(new SessionView(user, cartCount));
}
~~~

- `getAttribute(name)` returns `null` if there is no value.
- `getAttributeOrDefault(name, defaultValue)` provides a fallback.
- `getRequiredAttribute(name)` throws `IllegalArgumentException` if the attribute is missing.
- `getAttributes()` allows reading/writing the map directly.

If a missing session attribute is a normal business case, use `getAttribute` and handle it explicitly. Use `getRequiredAttribute` when missing data is an invariant violation.

### 6.3. When Is the Session Saved?

`WebSession.save()` returns `Mono<Void>`, but the Javadoc specifies this **is not a method applications normally call directly**. WebFlux automatically calls save right before the response is committed. For a new session, if `start()` has not been called or no attribute exists, save has no effect.

This helps the session cookie be added to the response at the right point in the lifecycle. Do not call `session.save().subscribe()` inside a controller; doing so detaches the save operation from the HTTP response, can race with commit, and makes errors hard to observe. Return the business Publisher for the framework to manage.

## 7. Starting, Rotating the ID, and Invalidating a Session

### 7.1. Creating a Session in a Controller

~~~java
@PostMapping("/api/session/start")
Mono<SessionView> start(WebSession session) {
    session.setMaxIdleTime(Duration.ofMinutes(10));
    session.getAttributes().put("user", "Ada");
    session.getAttributes().put("visits", 0);

    return Mono.just(new SessionView("Ada", 0));
}
~~~

Adding an attribute marks the session as started. When the response commits, WebFlux saves the session and the session ID resolver sends the ID to the browser (by default via cookie). The client saves the cookie and sends it back on later requests.

### 7.2. Changing the Session ID After Login

After successful authentication, you should rotate the session ID to reduce session fixation risk:

~~~java
Mono<Void> rotateAfterLogin(WebSession session) {
    return session.changeSessionId();
}
~~~

`changeSessionId()` emits `Mono<Void>`, creates a new ID, and updates storage. After succeeding, `getId()` returns the new ID. Do not return the session ID in JSON, logs, or URLs. In a login flow, perform rotation after successful authentication and before returning the login confirmation response.

### 7.3. Logout with `invalidate()`

~~~java
@PostMapping("/api/session/logout")
Mono<ResponseEntity<Void>> logout(WebSession session) {
    return session.invalidate()
        .thenReturn(ResponseEntity.noContent().build());
}
~~~

`invalidate()` removes the current session from session storage and returns completion/error via `Mono<Void>`. The session ID resolver coordinates so the browser stops using the current ID. After logout, a subsequent request with the old cookie must not recover the invalidated session data.

**Do not just delete the cookie in the browser and leave the server-side session.** If you only delete the cookie, the session record still exists until it expires or is cleaned up; a previously stolen ID may still be usable. Logout must invalidate the server-side session.

### 7.4. Setting Idle Timeout

~~~java
session.setMaxIdleTime(Duration.ofMinutes(15));
~~~

`maxIdleTime` is the maximum duration without activity before the session is considered expired. `getLastAccessTime()` gives the most recent access; `isExpired()` checks whether the session has exceeded its idle time. When a session is retrieved, the store is responsible for checking expiration and updating last access time.

Server-side idle timeout and browser-side cookie Max-Age are two different clocks:
- The browser may still hold the session ID cookie while the server has already expired the session; the next request will receive a new session.
- Closing the browser window may delete a session cookie if Max-Age is not set, but the server session record may still exist until idle time expires.
- A persistent cookie can outlive the server session; the browser sends the ID, but the server no longer has state.

Therefore, set the server-side timeout according to login policy and choose an appropriate cookie Max-Age. Do not treat the continued existence of a cookie as proof that the session is still valid.

## 8. `@SessionAttribute` and `@SessionAttributes`

The two annotations have different purposes.

### 8.1. `@SessionAttribute`: Reading an Attribute Managed Elsewhere

Use this when the attribute has already been created by a filter, authentication flow, or global component:

~~~java
@GetMapping("/api/current-user")
Mono<String> currentUser(
        @SessionAttribute(name = "user", required = false) String user) {
    return Mono.just(user == null ? "anonymous" : user);
}
~~~

This annotation reads an attribute already present in `WebSession`; it is not the primary API for adding/removing session attributes.

### 8.2. `@SessionAttributes`: Keeping Model Attributes in a Controller Workflow

~~~java
@Controller
@SessionAttributes("checkout")
class CheckoutController {

    @GetMapping("/checkout")
    String checkout(Model model) {
        model.addAttribute("checkout", new CheckoutDraft());
        return "checkout";
    }

    @PostMapping("/checkout/complete")
    String complete(CheckoutDraft checkout, SessionStatus status) {
        // Finish checkout processing...
        status.setComplete();
        return "redirect:/checkout/done";
    }
}
~~~

Spring promotes the `checkout` model attribute into `WebSession` across requests. `SessionStatus.setComplete()` marks the controller workflow complete and clears the session attributes declared via `@SessionAttributes` on that controller.

**`SessionStatus.setComplete()` is not equivalent to `WebSession.invalidate()`.** It cleans up the model state managed by the controller; the overall session can still remain for authentication or other purposes.

## 9. Session Lifetime and Where Sessions Are Stored

In Spring Framework, common default components are:

| Component | Role |
| --- | --- |
| `WebSessionManager` | Gets the session corresponding to a `ServerWebExchange`. |
| `DefaultWebSessionManager` | Coordinates resolver and store to find/create a session. |
| `WebSessionIdResolver` | Reads the ID from the request and sends/clears the ID in the response. |
| `CookieWebSessionIdResolver` | Cookie-based resolver; default cookie name is `SESSION`. |
| `HeaderWebSessionIdResolver` | Header-based resolver, useful for certain API clients. |
| `WebSessionStore` | Strategy to create, retrieve, remove, and update last access time of a session. |
| `InMemoryWebSessionStore` | Default map-based store in process memory. |

`DefaultWebSessionManager` uses `CookieWebSessionIdResolver` and `InMemoryWebSessionStore` by default. The default session cookie is named `SESSION`; default Max-Age is negative, meaning no Max-Age attribute is set and browsers usually remove it when the browser session closes. `InMemoryWebSessionStore` has a default limit of 10,000 sessions and a default idle time of 30 minutes in Spring Framework 7.x.

**The in-memory store is suitable for local development or single-instance applications with fitting requirements.** Sessions are lost when the process restarts and are not automatically shared across multiple replicas. For multi-instance production, use a distributed session repository if sticky-session independence is needed.

### 9.1. Spring Session with Redis

Spring Session integrates transparently with `WebSession`; the application can replace the default store with an implementation backed by `ReactiveSessionRepository`. With Redis, configuration usually uses `@EnableRedisWebSession` and `ReactiveSessionRepository` provided by Spring Session Data Redis.

~~~java
@Configuration(proxyBeanMethods = false)
@EnableRedisWebSession
class RedisWebSessionConfiguration {

    @Bean
    LettuceConnectionFactory redisConnectionFactory() {
        return new LettuceConnectionFactory(
            new RedisStandaloneConfiguration("localhost", 6379));
    }
}
~~~

This is a fragment that needs Spring Session Data Redis, Spring Data Redis, and a Redis server. `@EnableRedisWebSession` registers a `WebSessionManager` backed by Redis. In a real Boot application, configure the connection factory, password/TLS, timeout, serialization, and TTL according to your deployment environment.

Spring Session allows multiple instances to read the same session repository. Redis does not automatically make business state transaction-safe; you still need to control concurrent requests on the same session, races when updating attributes, and logout/revocation policies.


## 10. Customizing the Session ID Cookie

### 10.1. Changing the Cookie Name and Setting Attributes

You can register a `WebSessionIdResolver` bean to customize the session cookie:

~~~java
@Bean
WebSessionIdResolver webSessionIdResolver() {
    CookieWebSessionIdResolver resolver =
        new CookieWebSessionIdResolver();

    resolver.setCookieName("__Host-SESSION");
    resolver.addCookieInitializer(builder -> builder
        .path("/")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax"));

    return resolver;
}
~~~

`CookieWebSessionIdResolver` provides:
- `setCookieName(...)` to change the session cookie name.
- `setCookieMaxAge(...)` to set Max-Age.
- `addCookieInitializer(...)` to add `Path`, `Domain`, `Secure`, `HttpOnly`, `SameSite`, and other cookie attributes.
- `expireSession(exchange)` to instruct the client to end the current session.

The example using the `__Host-` prefix has strict browser rules: the cookie must have `Secure`, `Path=/`, and no `Domain`. Only use this prefix when the application runs over HTTPS and the host scope and path meet the conditions. If the app sits behind a reverse proxy, configure forwarded headers/proxy scheme accurately so the server understands the original request is HTTPS.

### 10.2. HeaderWebSessionIdResolver

Some native clients or internal systems may pass the session ID in an HTTP header instead of a cookie. `HeaderWebSessionIdResolver` is a built-in option; you must set the header name and ensure the header only travels over TLS and is not logged or forwarded to untrusted systems.

Do not pass the session ID in URL query/path. URLs often appear in browser history, proxy/access logs, analytics, and Referer; cookies or headers are safer for sensitive IDs.

## 11. Cookie and Session Security in Production

### 11.1. Cookie Hardening

For cookies containing a session ID or authentication information, a baseline usually includes:

~~~text
Set-Cookie: __Host-SESSION=<opaque-id>;
            Path=/;
            Secure;
            HttpOnly;
            SameSite=Lax
~~~

- **Secure:** mandatory over HTTPS to avoid sending credentials over HTTP.
- **HttpOnly:** prevents JavaScript from reading the session cookie directly.
- **SameSite:** choose Strict/Lax/None based on navigation flows, SSO, and cross-site integration.
- **Path/Domain:** restrict cookie scope.
- **Max-Age:** align with session timeout and remember-me policy.
- **Rotation:** change the session ID after authentication/privilege elevation.
- **Logout:** invalidate server-side state and expire the ID cookie.

`SameSite=None` requires `Secure` per modern browser requirements. If using OAuth/OIDC redirects or cross-site flows, choose SameSite according to the protocol and test on real browsers; do not switch to `SameSite=None` arbitrarily just to "fix cookies".

### 11.2. CSRF and Cookie Authentication

Browsers automatically send cookies to matching domains. Therefore, state-changing endpoints such as POST/PUT/PATCH/DELETE must consider CSRF:
- Use Spring Security CSRF protection according to application type.
- Check Origin/Referer in appropriate flows.
- You can use a CSRF token/header or cookie-to-header pattern if the client needs it.
- Do not treat `SameSite` as the sole protection layer.
- CORS does not replace CSRF protection; CORS mainly controls whether the browser lets JavaScript read the response.

If an API uses a bearer token in the Authorization header actively attached by the client, the threat model differs from automatic cookie authentication. Do not apply the same security assumptions to every kind of credential.

### 11.3. Session Fixation and Session Hijacking

- Rotate the session ID after login using `changeSessionId()`.
- Do not put the session ID in response JSON, URLs, logs, or tracing baggage.
- Enable TLS and Secure cookies.
- Set a reasonable idle timeout and absolute lifetime if the domain requires it.
- Invalidate the session on logout, account revocation, or major privilege changes.
- Restrict access to Redis/the session repository and enable network encryption/authentication.
- Do not store raw credentials or overly large objects in the session.
- Do not use the session ID as the sole proof for authorization; check user/permissions according to policy.

### 11.4. Races When Multiple Requests Use the Same Session

A browser can send multiple parallel requests with the same session ID. Two requests both read `cartCount=2`, both increment to 3, and both save; one update can overwrite the other depending on store/logic. Do not use session attributes as a transactional counter or a data store requiring atomicity.

For important state:
- Use database/Redis atomic operations or appropriate transactions.
- Keep session attributes small, mostly context/UI state.
- Avoid storing mutable object graphs shared across multiple requests.
- If versioning is needed, use optimistic locking or commands/idempotency.
- Do not assume Reactor serializes all requests of the same session on one thread.

## 12. WebFlux.fn: Cookies and Sessions in Functional Endpoints

Functional handlers read cookies from `ServerRequest.cookies()` and get the session with `ServerRequest.session()`:

~~~java
Mono<ServerResponse> sessionProfile(ServerRequest request) {
    return request.session().flatMap(session -> {
        String user = session.getAttribute("user");

        if (user == null) {
            return ServerResponse.notFound().build();
        }

        return ServerResponse.ok()
            .bodyValue(Map.of("user", user));
    });
}
~~~

Writing a cookie via `ServerResponse`:

~~~java
Mono<ServerResponse> setTheme() {
    ResponseCookie cookie = ResponseCookie.from("theme", "dark")
        .path("/")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .maxAge(Duration.ofDays(30))
        .build();

    return ServerResponse.noContent()
        .cookie(cookie)
        .build();
}
~~~

With `RouterFunction`, handlers can combine routes, filters, and error mapping. The session API is still `WebSession`; the only difference is getting the session from `request.session()` instead of a method argument or `exchange.getSession()`.

## 13. Cookie and Session Lifecycle: Complete Diagram

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant R as WebFlux
    participant M as WebSessionManager
    participant S as WebSessionStore

    B->>R: POST /login
    Note over B,R: No SESSION cookie yet
    R->>M: getSession(exchange)
    M->>S: retrieveSession(id) or createWebSession()
    S-->>M: New WebSession
    M-->>R: WebSession
    R->>R: Authenticate user, write attributes
    R->>R: changeSessionId() if login needs rotation
    R-->>B: 200 + Set-Cookie: SESSION=<opaque-id>
    Note over R,S: save session before response commit

    B->>R: GET /profile + Cookie: SESSION=id
    R->>M: resolve session id
    M->>S: retrieveSession(id), check expiry
    S-->>R: WebSession + attributes
    R-->>B: 200 + profile

    B->>R: POST /logout + Cookie: SESSION=id
    R->>S: invalidate/remove session
    R-->>B: 204 + expired cookie
    B->>R: GET /profile + old cookie (if still present)
    R-->>B: new session, no user attribute
~~~

The diagram shows the logical lifecycle. The timing of writing cookies/sessions is coordinated by the framework with response commit; the application does not need to call `save()` itself in every controller.

## 14. Realistic HTTP Example

Suppose the server uses the default `SESSION` cookie.

**1. Create a session**

~~~http
POST /api/session/start HTTP/1.1
Host: localhost:8080
~~~

The response may include:

~~~http
HTTP/1.1 200 OK
Set-Cookie: SESSION=<opaque-id>; Path=/; HttpOnly
Content-Type: application/json

{"user":"Ada","visits":0}
~~~

Specific cookie attributes depend on the resolver/configuration; the example above only illustrates the cookie name and session ID.

**2. Send the cookie back**

~~~http
GET /api/session/me HTTP/1.1
Host: localhost:8080
Cookie: SESSION=<opaque-id>
~~~

The server finds the same session and reads the `user` and `visits` attributes.

**3. Logout**

~~~http
DELETE /api/session HTTP/1.1
Host: localhost:8080
Cookie: SESSION=<opaque-id>
~~~

The server invalidates the session and the resolver instructs the browser to expire the ID cookie. Subsequent requests cannot recover the deleted session state.

## 15. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Confusing cookies with WebSession | Putting all session data on the client | Cookie holds only the ID; state resides in the store. |
| Calling `exchange.getSession()` and thinking the session has started | Browser does not receive a session ID when not started | Add an attribute or call `start()`. |
| Calling `session.save().subscribe()` yourself | Save runs outside the HTTP lifecycle; errors/races are hard to track | Return the Publisher; let the framework save before commit. |
| Logout only deletes the browser cookie | Server-side session remains valid | Call `WebSession.invalidate()`. |
| Only invalidating storage while forgetting session ID rotation on login | Session fixation risk | Call `changeSessionId()` after authentication. |
| Leaving auth cookies without Secure/HttpOnly | Increases credential theft risk | Use HTTPS, Secure, HttpOnly, and appropriate SameSite. |
| Using SameSite as the only CSRF protection | CSRF paths still exist depending on browser/flow | Use Spring Security CSRF and check Origin per threat model. |
| Deleting a cookie with the wrong Path/Domain | Old cookie still exists | Send Max-Age=0 with the same scope. |
| Cookie with an overly broad Domain | Other subdomains may receive the cookie | Prefer host-only cookies when possible. |
| Using cookies as an authorization source | Client can modify the value | Validate, sign/encrypt if needed, and check permissions server-side. |
| Session timeout too long | Abandoned sessions may remain valid | Set reasonable idle timeout and absolute lifetime. |
| Using InMemoryWebSessionStore for multiple replicas | Other instances cannot find the session | Spring Session with Redis or a distributed repository. |
| Putting large objects in the session | Wastes memory, serialization, and network | Store only small state or reference IDs. |
| Updating a session counter like transactional data | Concurrent requests can overwrite | Use atomic storage/transactions for critical data. |
| Putting the session ID in the URL | ID leaks via history/logs/Referer | Use cookies or headers over TLS. |
| Using `JSESSIONID` as WebFlux's default name | Debugging confusion between Servlet and reactive stacks | WebFlux's `CookieWebSessionIdResolver` defaults to `SESSION`. |

## 16. Production Checklist

- [ ] Clearly distinguish application cookies and cookies carrying a WebSession ID.
- [ ] Cookie input is treated as untrusted and validated.
- [ ] Session cookies have appropriate Secure, HttpOnly, SameSite, and Path.
- [ ] Cookie deletion uses the right name/path/domain and Max-Age=0.
- [ ] Sessions start only when needed; avoid accidentally creating sessions for every anonymous request.
- [ ] Session attributes are small, well-typed, and contain no raw credentials.
- [ ] `save()` is managed by the framework; no manual subscribe.
- [ ] Login/privilege elevation rotates the session ID.
- [ ] Logout/revocation invalidates the session server-side.
- [ ] Idle timeout and cookie lifetime are designed separately yet compatibly.
- [ ] CSRF protection is configured for cookie-authenticated state-changing endpoints.
- [ ] In-memory store is used only when lifecycle/single-instance fits; multi-instance has a shared session repository.
- [ ] Important concurrent updates use atomic operations or transactions.
- [ ] Integration tests verify Set-Cookie, Cookie requests, session continuity, rotation, and logout.

## 17. Practice Exercises

**Exercise 1 – Reading a cookie.** Write GET `/api/theme` using `@CookieValue` with default `system`. Send requests with and without the cookie; compare the bodies.

**Exercise 2 – Set-Cookie.** Create cookie `theme=dark` with `ResponseCookie`; enable HttpOnly, Secure, SameSite, and Path. Inspect the response header.

**Exercise 3 – Deleting a cookie.** Send a cookie with Max-Age=0 and the matching Path/Domain. Verify the browser/cookie jar does not send the cookie back on the next request.

**Exercise 4 – Session lifecycle.** Create POST `/start` adding a `user` attribute. Send GET `/me` with the same cookie; confirm the server reads `user` back.

**Exercise 5 – Session rotation.** Call `changeSessionId()` after login. Confirm the response sends a new ID and session attributes still exist.

**Exercise 6 – Logout.** Call `invalidate()`; use a cookie jar to check that the next request no longer has the old attributes.

**Exercise 7 – Idle timeout.** Set a short max idle time, use an appropriate `Clock`/store in tests or time-controlled integration tests to observe session expiration. Avoid unnecessary long `Thread.sleep`.

**Exercise 8 – Redis session.** Replace the in-memory store with Spring Session Redis; run two instances and verify a session created on instance A is read on instance B.

**Exercise 9 – CSRF.** Enable Spring Security CSRF for cookie-using endpoints; send POST missing the token and with the token, and verify status codes.

## 18. Official References

1. Spring Framework 7.0.8 Javadoc – `WebSession`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebSession.html
2. Spring Framework – `@CookieValue` in WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/cookievalue.html
3. Spring Framework – `@SessionAttribute`: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/sessionattribute.html
4. Spring Framework – `@SessionAttributes`: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/sessionattributes.html
5. Spring Framework Javadoc – `CookieWebSessionIdResolver`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/session/CookieWebSessionIdResolver.html
6. Spring Framework Javadoc – `WebSessionManager` / `DefaultWebSessionManager`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/session/DefaultWebSessionManager.html
7. Spring Framework Javadoc – `WebSessionStore` / `InMemoryWebSessionStore`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/session/WebSessionStore.html
8. Spring Framework Javadoc – `ResponseCookie`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseCookie.html
9. Spring Session – WebSession Integration and Redis: https://docs.spring.io/spring-session/reference/web-session.html
10. Spring Security – Reactive WebFlux Security and CSRF: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html

**Final self-assessment:** Why might `getSession()` not have sent a cookie yet? What differs between `changeSessionId()` and `invalidate()`? Why is deleting the browser cookie without invalidating the server-side session not enough? If the session exceeds idle time while the browser still sends the old ID, how does the server handle it? When you can explain the cookie flow, session store, and logout lifecycle together, you understand how to manage cookies/sessions in WebFlux.


## 19. Runnable Java 17+ Project: Cookie and Session Lifecycle

The project uses Spring Boot 4.0.9, Java 17+, and WebFlux. It illustrates:
- Creating a session and writing attributes.
- Reading the session on a later request with the same cookie jar.
- Changing the session ID after authentication.
- Logging out with invalidate.
- Reading a custom cookie with `@CookieValue`.
- Writing/deleting a cookie with security attributes.
- Testing HTTP with JDK `HttpClient` and `CookieManager`.

### 19.1. Directory Structure

~~~text
webflux-cookie-session/
├── pom.xml
├── src/main/java/com/example/session/SessionCookieApplication.java
├── src/main/java/com/example/session/SessionView.java
├── src/main/java/com/example/session/SessionController.java
├── src/main/java/com/example/session/CookieController.java
└── src/test/java/com/example/session/SessionCookieIntegrationTest.java
~~~

### 19.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-cookie-session</artifactId>
    <version>1.0.0</version>

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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

### 19.3. SessionCookieApplication.java

~~~java
package com.example.session;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionCookieApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionCookieApplication.class, args);
    }
}
~~~

### 19.4. SessionView.java

~~~java
package com.example.session;

public record SessionView(String user, int visits) {}
~~~

### 19.5. SessionController.java

~~~java
package com.example.session;

import java.time.Duration;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.WebSession;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/session")
public class SessionController {

    @PostMapping("/start")
    public Mono<SessionView> start(WebSession session) {
        session.setMaxIdleTime(Duration.ofMinutes(10));
        session.getAttributes().put("user", "Ada");
        session.getAttributes().put("visits", 0);

        return Mono.just(new SessionView("Ada", 0));
    }

    @GetMapping("/me")
    public Mono<ResponseEntity<SessionView>> me(WebSession session) {
        return Mono.defer(() -> {
            String user = session.getAttribute("user");

            if (user == null) {
                return Mono.just(
                    ResponseEntity.<SessionView>notFound().build());
            }

            int visits = session.getAttributeOrDefault("visits", 0) + 1;
            session.getAttributes().put("visits", visits);

            return Mono.just(ResponseEntity.ok(
                new SessionView(user, visits)));
        });
    }

    @PostMapping("/rotate")
    public Mono<ResponseEntity<SessionView>> rotate(WebSession session) {
        String user = session.getAttribute("user");

        if (user == null) {
            return Mono.just(
                ResponseEntity.<SessionView>notFound().build());
        }

        int visits = session.getAttributeOrDefault("visits", 0);

        return session.changeSessionId()
            .thenReturn(ResponseEntity.ok(
                new SessionView(user, visits)));
    }

    @DeleteMapping
    public Mono<ResponseEntity<Void>> logout(WebSession session) {
        return session.invalidate()
            .thenReturn(ResponseEntity.noContent().build());
    }
}
~~~

Explanation:
- `/start` adds attributes, so the session is started implicitly; `setMaxIdleTime` sets a 10-minute idle timeout.
- `/me` reads the existing session, increments visits, and returns `404` if there is no user.
- `/rotate` changes the ID while keeping session attributes; in a real flow only call after successful authentication.
- `DELETE /api/session` invalidates the session. The framework handles saving/expiring the ID cookie according to the response lifecycle.

The controller does not subscribe itself and does not call `session.save()`.

### 19.6. CookieController.java

~~~java
package com.example.session;

import java.time.Duration;
import java.util.Map;

import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/cookies")
public class CookieController {

    @GetMapping("/theme")
    public Map<String, String> theme(
            @CookieValue(
                name = "theme",
                required = false,
                defaultValue = "system"
            ) String theme) {
        return Map.of("theme", theme);
    }

    @PostMapping("/theme")
    public ResponseEntity<Void> setTheme(
            ServerHttpResponse response) {

        ResponseCookie cookie = ResponseCookie.from("theme", "dark")
            .path("/")
            .httpOnly(true)
            .secure(true)
            .sameSite("Lax")
            .maxAge(Duration.ofDays(30))
            .build();

        response.addCookie(cookie);
        return ResponseEntity.noContent().build();
    }

    @DeleteMapping("/theme")
    public ResponseEntity<Void> clearTheme(
            ServerHttpResponse response) {

        ResponseCookie expired = ResponseCookie.from("theme", "")
            .path("/")
            .httpOnly(true)
            .secure(true)
            .sameSite("Lax")
            .maxAge(Duration.ZERO)
            .build();

        response.addCookie(expired);
        return ResponseEntity.noContent().build();
    }
}
~~~

The `theme` cookie is set Secure for use over HTTPS. Tests send the cookie manually when testing `@CookieValue`; browsers/HTTP clients do not normally send Secure cookies over plain HTTP connections.

### 19.7. SessionCookieIntegrationTest.java

~~~java
package com.example.session;

import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SessionCookieIntegrationTest {

    @Value("${local.server.port}")
    int port;

    private HttpResponse<String> send(
            HttpClient client, String method, String path)
            throws Exception {

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://localhost:" + port + path))
            .method(method, HttpRequest.BodyPublishers.noBody())
            .build();

        return client.send(
            request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void sessionPersistsRotatesAndIsInvalidatedOnLogout()
            throws Exception {

        CookieManager cookieManager =
            new CookieManager(null, CookiePolicy.ACCEPT_ALL);

        HttpClient client = HttpClient.newBuilder()
            .cookieHandler(cookieManager)
            .build();

        HttpResponse<String> start =
            send(client, "POST", "/api/session/start");

        assertEquals(200, start.statusCode());
        assertTrue(cookieManager.getCookieStore().getCookies()
            .stream().anyMatch(cookie ->
                cookie.getName().equals("SESSION")));

        String originalId = cookieManager.getCookieStore().getCookies()
            .stream()
            .filter(cookie -> cookie.getName().equals("SESSION"))
            .findFirst()
            .orElseThrow()
            .getValue();

        HttpResponse<String> firstRead =
            send(client, "GET", "/api/session/me");

        assertEquals(200, firstRead.statusCode());
        assertTrue(firstRead.body().contains("\"user\":\"Ada\""));
        assertTrue(firstRead.body().contains("\"visits\":1"));

        HttpResponse<String> rotate =
            send(client, "POST", "/api/session/rotate");

        assertEquals(200, rotate.statusCode());

        String rotatedId = cookieManager.getCookieStore().getCookies()
            .stream()
            .filter(cookie -> cookie.getName().equals("SESSION"))
            .findFirst()
            .orElseThrow()
            .getValue();

        assertNotEquals(originalId, rotatedId);

        HttpResponse<String> secondRead =
            send(client, "GET", "/api/session/me");

        assertEquals(200, secondRead.statusCode());
        assertTrue(secondRead.body().contains("\"visits\":2"));

        HttpResponse<String> logout =
            send(client, "DELETE", "/api/session");

        assertEquals(204, logout.statusCode());

        HttpResponse<String> afterLogout =
            send(client, "GET", "/api/session/me");

        assertEquals(404, afterLogout.statusCode());
    }

    @Test
    void cookieValueCanBeReadAndResponseCookieCanBeHardened()
            throws Exception {

        HttpClient client = HttpClient.newHttpClient();

        HttpRequest readRequest = HttpRequest.newBuilder(
                URI.create("http://localhost:" + port + "/api/cookies/theme"))
            .header("Cookie", "theme=dark")
            .GET()
            .build();

        HttpResponse<String> read = client.send(
            readRequest, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, read.statusCode());
        assertTrue(read.body().contains("\"theme\":\"dark\""));

        HttpResponse<String> set = send(
            client, "POST", "/api/cookies/theme");

        assertEquals(204, set.statusCode());

        String setCookie = set.headers()
            .allValues("Set-Cookie")
            .stream()
            .filter(value -> value.startsWith("theme="))
            .findFirst()
            .orElseThrow();

        assertTrue(setCookie.contains("Path=/"));
        assertTrue(setCookie.contains("Secure"));
        assertTrue(setCookie.contains("HttpOnly"));
        assertTrue(setCookie.contains("SameSite=Lax"));

        HttpResponse<String> clear = send(
            client, "DELETE", "/api/cookies/theme");

        assertEquals(204, clear.statusCode());

        String expiredCookie = clear.headers()
            .allValues("Set-Cookie")
            .stream()
            .filter(value -> value.startsWith("theme="))
            .findFirst()
            .orElseThrow();

        assertTrue(expiredCookie.contains("Max-Age=0"));
    }
}
~~~

The test uses a real cookie jar for the session flow:
1. POST `/start` receives the `SESSION` cookie.
2. GET `/me` sends back the cookie and sees the attribute.
3. POST `/rotate` receives a new session ID while keeping the data.
4. GET `/me` continues reading the same session.
5. DELETE logout invalidates; the subsequent GET no longer has the user attribute.

The `theme` cookie test verifies `@CookieValue`, `Set-Cookie` flags, and `Max-Age=0`. The `Secure` cookie is verified via the response header; the test does not rely on sending it over HTTP.

### 19.8. Running and Trying with curl

Requires JDK 17+ and Maven:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

You can use curl's cookie jar to keep the session ID across multiple requests:

~~~bash
curl -i -c cookies.txt -X POST http://localhost:8080/api/session/start
curl -i -b cookies.txt http://localhost:8080/api/session/me
curl -i -b cookies.txt -c cookies.txt -X POST http://localhost:8080/api/session/rotate
curl -i -b cookies.txt -X DELETE http://localhost:8080/api/session
curl -i -b cookies.txt http://localhost:8080/api/session/me
~~~

For the theme cookie, because the example sets Secure=true, test over HTTPS or send the cookie manually when using localhost HTTP:

~~~bash
curl -i --cookie "theme=dark" http://localhost:8080/api/cookies/theme
curl -i -X POST https://localhost:8080/api/cookies/theme
curl -i -X DELETE https://localhost:8080/api/cookies/theme
~~~

**Expected result:** session `/start` creates the `SESSION` cookie; `/me` returns user Ada; `/rotate` changes the ID; `/logout` returns 204 and deletes server-side state; the next request returns 404. The theme cookie is returned with `Path`, `Secure`, `HttpOnly`, `SameSite=Lax`, and when deleted has `Max-Age=0`.
