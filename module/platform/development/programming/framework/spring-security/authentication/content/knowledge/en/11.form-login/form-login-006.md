# RequestCache, SavedRequest, and Restoring Requests After Login

An unauthenticated user opens a link to an internal report:

```text
GET /reports/summary?period=2026
```

The application requires authentication and redirects them to the login page. After entering the right password, the user usually expects to **return to the exact report they tried to open**, rather than always landing on the home page. In Spring Security Servlet, this behavior is built through the coordination of **`ExceptionTranslationFilter`, `RequestCache`, `SavedRequest`, `SavedRequestAwareAuthenticationSuccessHandler`, and `RequestCacheAwareFilter`**.

This is a Knowledge lesson in the **Form Login** group of *Spring Security - authentication*. It explains precisely **when a request is saved, what metadata is retained, why post-login redirects recover the original URL, and when the cache is cleared**, along with security boundaries and a Java 17+/Spring Boot 3.x example with MockMvc integration tests. Pay special attention to **the `continue` parameter change in Spring Security 6**, unsafe requests such as POST, open redirects, multiple tabs, and stateful/stateless sessions.

**Summary:** `RequestCache` is not a user database and not `SecurityContextRepository`. It stores *information about a request interrupted due to missing authentication*. `SavedRequestAwareAuthenticationSuccessHandler` uses that information to **redirect** after successful login; `RequestCacheAwareFilter` can restore a request wrapper when the browser follows the redirect to the matching URL. This **does not mean automatically replaying the raw HTTP body, resubmitting a payment, or bypassing authorization**.

## 1. Learning Objectives

After this lesson, you can:

1. Describe the exact chain from a protected-area request to the first request after login.
2. Explain `RequestCache`/`SavedRequest`/`DefaultSavedRequest`/`HttpSessionRequestCache` and the methods `saveRequest`, `getRequest`, `getMatchingRequest`, and `removeRequest`.
3. Distinguish the responsibilities of `ExceptionTranslationFilter`, `LoginUrlAuthenticationEntryPoint`, `SavedRequestAwareAuthenticationSuccessHandler`, `RequestCacheAwareFilter`, and `SecurityContextRepository`.
4. Explain the difference between Spring Security 5 and 6 in optimizing request lookup with the `continue` query parameter.
5. Predict the redirect path when a saved request exists, when none exists, or with `alwaysUseDefaultTargetUrl`, `targetUrlParameter`, or `NullRequestCache`.
6. Understand why GET bookmarks are the primary scenario, whereas POSTs with bodies, CSRF tokens, streams, and state-mutating transactions **are not automatically re-executed** after login.
7. Configure stateful form login with a shared `HttpSessionRequestCache` across the security chain and success handler.
8. Run integration tests: anonymous GET saved → valid form login → redirect to URL with `continue` → follow-up request authenticated → cache consumed.
9. Design URL caching limits, prevent open redirects/host-header poisoning, avoid caching sensitive query strings, and handle multi-tab overwrites.
10. Decide when to disable request caching for stateless APIs, SPAs, or sensitive endpoints.

## 2. Concept: "Saving a Request" Is Not "Saving Operation Payload"

`SavedRequest` represents **the necessary metadata** about an interrupted request so the application can return to the original location after authentication. It is not a full recording capable of replaying every byte of a network stream in the future.

Example incoming request:

```http
GET /reports/summary?period=2026 HTTP/1.1
Host: app.example.test
Accept: text/html
```

If unauthenticated, the system may remember:

```text
Scheme/host/port/path = https://app.example.test/reports/summary
Query string          = period=2026
Method                = GET
Headers/parameters    = partial metadata retained by DefaultSavedRequest
Session ID            = session where RequestCache stores the request
```

After login, the browser receives **302 to the saved URL**. The browser sends a **new request** to that URL, and authorization re-evaluates the newly logged-in principal. It does not "resume" the exact old servlet thread. The original request ended with the redirect to login; subsequent steps are separate HTTP exchanges.

### 2.1 Two Things Often Confused as "Session"

| Concept | Data | Purpose |
| --- | --- | --- |
| **Saved request** | Target URL, query, method, and metadata for returning. | Decides where to redirect after login. |
| **Authentication in `SecurityContext`** | Verified principal, authorities, authenticated state. | Allows subsequent requests to pass authentication/authorization. |
| **`HttpSession`** | Server-side container that can store both types of data under separate keys. | Maintains state across HTTP requests via session ID. |
| **Browser cookie `JSESSIONID`** | Reference to a server-side session. | Links independent browser requests to the same session. |

**Having `SPRING_SECURITY_SAVED_REQUEST` in the session does not prove the user is logged in.** Conversely, being authenticated without a saved request is completely normal—for instance, when a user navigates directly to `/login` and signs in.

### 2.2 Key Classes

| Component | What it does |
| --- | --- |
| `ExceptionTranslationFilter` | Detects `AuthenticationException` or `AccessDeniedException` requiring authentication start; calls `RequestCache.saveRequest` before `AuthenticationEntryPoint.commence`. |
| `AuthenticationEntryPoint` | Chooses how to prompt login, e.g., `LoginUrlAuthenticationEntryPoint` redirects to `/login`. |
| **`RequestCache`** | Interface to save, read, match, and remove saved requests. |
| **`SavedRequest`** | Interface representing a remembered request; `DefaultSavedRequest` is the common implementation. |
| **`HttpSessionRequestCache`** | Implementation storing `SavedRequest` in `HttpSession`. |
| `SavedRequestAwareAuthenticationSuccessHandler` | On login success, looks up the saved request and chooses the redirect target. |
| `RequestCacheAwareFilter` | On the redirected request, calls `getMatchingRequest` to restore a wrapper if matched and consumes the cache. |
| `SavedRequestAwareWrapper` | Wrapper exposing saved request metadata downstream per implementation semantics. |

### 2.3 RequestCache Interface

Conceptual signature from Spring Security 6.x (for study, do not redeclare this interface):

```java
public interface RequestCache {
    void saveRequest(HttpServletRequest request, HttpServletResponse response);

    SavedRequest getRequest(
            HttpServletRequest request, HttpServletResponse response);

    HttpServletRequest getMatchingRequest(
            HttpServletRequest request, HttpServletResponse response);

    void removeRequest(
            HttpServletRequest request, HttpServletResponse response);
}
```

- `saveRequest`: records the blocked request, if the implementation/policy allows.
- `getRequest`: **reads the saved request while keeping it in the cache**; the success handler can use it to decide the redirect target.
- `getMatchingRequest`: checks whether the current request matches the saved one; on a match, returns a wrapped request and **removes the saved request from the cache**.
- `removeRequest`: explicitly deletes the saved request, such as when ignoring the old target or forcing a default target.

Do not confuse `getRequest` with `getMatchingRequest`. One is used to **look up the destination**, while the other is used to **match the returning request and consume it**. That is the key to understanding why a saved request can **still exist in the session right after the login redirect**.

## 3. Full Chain Before Login and After Login

```text
T0: Browser -> GET /reports/summary?period=2026
                |
                v
       SecurityFilterChain
                |
                v
       AuthorizationFilter -> request requires authenticated
                |
                v
       ExceptionTranslationFilter catches relevant exception
                |
                +--> RequestCache.saveRequest(request, response)
                |        |
                |        +--> HttpSession holds DefaultSavedRequest
                |
                +--> LoginUrlAuthenticationEntryPoint
                         |
                         v
                    HTTP 302 /login

T1: Browser -> GET /login
                |
                v
       Form login page; user enters username/password

T2: Browser -> POST /login + valid CSRF token
                |
                v
       UsernamePasswordAuthenticationFilter
       AuthenticationManager / ProviderManager
       DaoAuthenticationProvider + UserDetailsService + PasswordEncoder
                |
                +--> Invalid: failure handler -> saved request not used
                |
                +--> Valid: SessionAuthenticationStrategy
                          SecurityContext saved to appropriate repository
                          SavedRequestAwareAuthenticationSuccessHandler
                               |
                               +--> RequestCache.getRequest(...)
                               +--> redirect to savedRequest.getRedirectUrl()
                                    (in Spring Security 6 may include ?continue)
                          HTTP 302 to /reports/summary?period=2026&continue

T3: Browser -> GET /reports/summary?period=2026&continue
                |
                v
       SecurityContextRepository loads Authentication from session
       RequestCacheAwareFilter.getMatchingRequest(...)
                |
                +--> checks query marker / URL match
                +--> removeRequest(...) if matched
                +--> SavedRequestAwareWrapper passed downstream
                |
                v
       AuthorizationFilter re-checks permissions
                |
                v
       Report controller -> HTTP 200
```

This diagram shows **a common journey with stateful form login and `HttpSessionRequestCache`**, not a guarantee for every authentication setup. An API using Bearer/JWT, basic auth, a custom entry point returning 401 JSON, or `NullRequestCache` may involve no redirects and create no `SavedRequest`.

### 3.1 Why Is `ExceptionTranslationFilter` Important?

`ExceptionTranslationFilter` is the bridge from *security errors in the filter chain* to *initiating authentication*. When an unauthenticated principal hits an endpoint requiring authentication, it can save the original request before redirecting to login. Thus, the saved request is not created by the `/login` controller when the user submits a password; it originates from the **prior blocked request to the protected resource**.

If policy finds the user is already authenticated yet lacks a role, Spring Security normally handles it with **403 Access Denied**, rather than saving the request and bouncing back to login. Distinguish anonymous/unauthenticated from authenticated-but-forbidden; never turn every 403 into an infinite login loop.

### 3.2 State at Three Points in Time

| Point in time | `SecurityContext` | `RequestCache` | What the user observes |
| --- | --- | --- | --- |
| Anonymous GET blocked | No authenticated principal yet | May contain request to report | Redirected to login. |
| Immediately after successful login | Valid Authentication in session | Saved request may **still remain** | Redirected to original URL. |
| Request returns to valid target | Context loaded from session | `getMatchingRequest` may consume saved request | Original page returned if authorized. |

**Never treat a saved request as proof of authorization.** Even if the URL was saved, when the request returns the system must still verify roles, tenant, ownership, and account status per policy.

### 3.3 Redirect vs. Forward

The standard saved-request flow uses an **HTTP redirect**, meaning the browser creates a new request. It is not a server-side `RequestDispatcher.forward` of the old request or a continuation preserving method/body/transaction. If you need to restore a partially filled form, design an explicitly saved **draft** with replay protection rather than treating `RequestCache` as a "whole-POST" browser memory.

## 4. HttpSessionRequestCache: Where Does the Data Live?

`HttpSessionRequestCache` is the common default implementation for Servlet form login. It stores a `DefaultSavedRequest` in `HttpSession`; the default key is:

```text
SPRING_SECURITY_SAVED_REQUEST
```

This is an internal framework attribute, **distinct** from `SPRING_SECURITY_CONTEXT` used to store authentication. One session can hold both simultaneously:

```text
HttpSession S
├── SPRING_SECURITY_SAVED_REQUEST
│     └── DefaultSavedRequest("/reports/summary?period=2026...")
├── SPRING_SECURITY_CONTEXT
│     └── SecurityContext(Authentication("alice", ROLE_USER))
└── CSRF token / app attributes / session metadata
```

### 4.1 Saving May Create a New Session

`HttpSessionRequestCache` has a `createSessionAllowed` option. By default it typically allows creating an `HttpSession` to remember the original request if no session exists yet. This is a **useful side effect, but not free**: an anonymous GET to a protected resource can cause the server to issue a session cookie just to hold the URL.

If a system receives heavy anonymous API traffic, session-creation overhead can be significant. You can:

- Save only sensible GET/HEAD requests via `RequestMatcher`.
- Set `setCreateSessionAllowed(false)` if you do not want the cache to create sessions automatically, meaning requests without a session may not be saved.
- Use `NullRequestCache` if users always go to a default landing page or APIs handle navigation themselves.
- Use another controlled return mechanism (e.g., signed/allowlisted `returnTo`) when UX requires returning without server sessions.
- Monitor HTTP session size and TTL.

### 4.2 Save Only Appropriate URLs

By default, `HttpSessionRequestCache` may save a broad range of requests requiring authentication. A real application should usually restrict caching to URLs meaningful for post-login redirects:

```java
HttpSessionRequestCache cache = new HttpSessionRequestCache();
cache.setRequestMatcher(
        new AntPathRequestMatcher("/reports/**", "GET"));
cache.setMatchingRequestParameterName("continue");
```

This is a **configuration snippet** requiring Spring Security Servlet imports. Only GET requests under `/reports/**` are saved under this matcher. Avoid accidentally excluding legitimate pages: tune the matcher to product behavior. For HEAD, you may decide not to save it since browsers generally do not use HEAD for page navigation.

### 4.3 Multiple Tabs Sharing One Session

By default, `HttpSessionRequestCache` holds **one saved request under a single key** per session, not an unbounded per-tab queue. For example:

```text
Tab A (anonymous) -> GET /reports/annual   -> saved = A
Tab B (anonymous) -> GET /reports/monthly  -> saved = B (overwrites A)
Tab A submits login -> success handler reads B -> redirects Tab A to monthly
```

This is an important UX limitation. If you strictly need *each tab to return to its own page*, design per-tab state with a correlation ID, integrity, TTL, and ownership checks rather than assuming `SPRING_SECURITY_SAVED_REQUEST` stores a per-tab stack.

Also be mindful that repeated failed logins and interleaved anonymous requests can update the saved request; never allow a sensitive URL to be forced into the session and abused as an open redirect.

## 5. What Does SavedRequest / DefaultSavedRequest Actually Store?

`SavedRequest` holds information needed to reconstruct/match an original request. `DefaultSavedRequest` is the implementation commonly used by `HttpSessionRequestCache`. It can retain the method, redirect URL, query, parameters, selected headers/cookies/locales, and version-specific metadata.

**What you must not assume:**

- A saved request is not a recording of the **entire raw input stream** and cannot resubmit an arbitrary JSON/multipart body with original transaction semantics.
- It is not an authorization grant; the controller must still check permissions upon return.
- It is not an exactly-once guarantee or duplicate-charge prevention mechanism.
- It does not shield query URL contents from browser history, proxy logs, or session dumps.
- It does not automatically verify whether the target host is trustworthy for redirects.
- It does not reattach a suspended operation on an old thread.

### 5.1 `getRedirectUrl`

`SavedRequest.getRedirectUrl()` returns the URL used for post-login navigation. In Spring Security 6 configurations with `HttpSessionRequestCache` and the `continue` marker, the saved request URL can include this parameter so the follow-up request only queries the cache when actually needed.

Example:

```text
Original request:    /reports/summary?period=2026
Post-login redirect: /reports/summary?period=2026&continue
```

Whether `&` or `?` is used depends on whether the original URL already had a query string. This marker is **for optimizing request cache matching**, not an authentication token or proof of permission. A client manually appending `?continue` to a URL **gains no new privileges**; the request still goes through SecurityContext/authorization.

### 5.2 RequestCache-Aware Wrapping

After login succeeds, `SavedRequestAwareAuthenticationSuccessHandler` may **keep the saved request in the session** while issuing the redirect. `RequestCacheAwareFilter` runs on the subsequent GET, calls `getMatchingRequest` to find the saved request, and—if matched—passes a `SavedRequestAwareWrapper` downstream while clearing the cache.

Thus the operations are distinct:

```text
successHandler.getRequest(...)     = reads destination, does not remove
response.sendRedirect(savedUrl)    = browser issues new request
requestCache.getMatchingRequest(...) = if matched, consumes + wraps
```

In Spring Security 6, the `continue` marker avoids having `RequestCacheAwareFilter` read `HttpSession` on every request when there is nothing to restore.

## 6. Spring Security 6: The continue Parameter and Performance Optimization

### 6.1 Problem with the Old Approach

In typical Spring Security 5 setups, `RequestCacheAwareFilter` could query `HttpSession` for a saved request **on many requests**, even when most requests were unrelated to a fresh login. Unnecessary session lookups add I/O, especially when sessions live in Redis or distributed stores.

### 6.2 Spring Security 6 Behavior

Per the Spring Security 6 migration guide, `HttpSessionRequestCache` defaults to **`continue`** as the query parameter name indicating that `getMatchingRequest` should check for a saved request. This reduces redundant session lookups solely to search for a restore URL.

```java
HttpSessionRequestCache requestCache = new HttpSessionRequestCache();
requestCache.setMatchingRequestParameterName("continue");

http.requestCache(cache -> cache.requestCache(requestCache));
```

With this setup, **`getMatchingRequest`** can skip querying the cache if the query lacks `continue`. In contrast, **`getRequest`** in the success handler can still read the saved request directly to determine the redirect. Do not assume every `RequestCache` method only works when `continue` is present.

### 6.3 Why Can the Original URL "Add continue by Itself"?

`DefaultSavedRequest` can build the target URL with the marker configured via `matchingRequestParameterName`. On login success, the handler redirects to `savedRequest.getRedirectUrl()` carrying that marker. When the redirected request arrives with the marker, `RequestCacheAwareFilter` queries and matches it.

Simply checking for the marker's presence **is not enough**: the implementation also compares the current URL against the saved URL, checks the session, and matches properly. The marker is neither a password, a CSRF token, nor a new permission.

### 6.4 If You Customized RequestCache Previously

An upgrading application may run into:

- A custom `RequestCache` that does not understand the `continue` marker.
- `HttpSessionRequestCache` with a different marker name configured.
- A custom success handler redirecting to a URL **without the marker**, preventing `RequestCacheAwareFilter` from consuming the saved request as expected.
- `NullRequestCache` in use while the success handler still expects a saved request.
- Multiple `SecurityFilterChain`s using different `RequestCache` instances.
- Frontend/SPA stripping query markers before the next request, preventing matching from running.

**Recommendation:** Configure **the same `RequestCache` instance** on both the filter chain and `SavedRequestAwareAuthenticationSuccessHandler` when customizing, then test the full anonymous GET → login → redirect → target GET flow. Never "fix" this by disabling `SecurityContextRepository` or poking session attributes manually.

## 7. How Does SavedRequestAwareAuthenticationSuccessHandler Choose the Redirect Priority?

`SavedRequestAwareAuthenticationSuccessHandler` extends `SimpleUrlAuthenticationSuccessHandler`. After successful login, it decides:

| Case | Redirect target | Saved request |
| --- | --- | --- |
| `alwaysUseDefaultTargetUrl=true` | Always `defaultTargetUrl` | **Removed** if present. |
| Login request includes configured `targetUrlParameter` with meaningful value | Target value per base handler config | **Removed** if present. |
| `SavedRequest` exists in RequestCache | `savedRequest.getRedirectUrl()` | **Kept in cache** for the redirected request to consume. |
| No saved request | `SimpleUrlAuthenticationSuccessHandler` behavior (default target, etc.) | Nothing to remove. |

### 7.1 `alwaysUseDefaultTargetUrl`

If the product wants every login to land on the dashboard:

```java
SavedRequestAwareAuthenticationSuccessHandler handler =
        new SavedRequestAwareAuthenticationSuccessHandler();
handler.setAlwaysUseDefaultTargetUrl(true);
handler.setDefaultTargetUrl("/home");
```

In this branch, the handler clears the saved request; the original URL **is no longer used** for redirecting. This differs from setting only `defaultTargetUrl`, because **the default target is only a fallback** when there is no saved request, unless `alwaysUse` is forced.

### 7.2 `targetUrlParameter`: Beware of Open Redirects

You can configure a parameter name for the redirect target. However, if the value comes directly from the client without validation, it can become an **open redirect** vulnerability (sending users to an attacker-chosen domain) or cause malicious behavior when parsed by browsers/proxies.

Do not do this:

```java
// NOT RECOMMENDED: arbitrary client-supplied next value.
handler.setTargetUrlParameter("next");
```

without a target validation policy. Prefer server-determined targets from an appropriate cache and an internal route allowlist; if client-supplied `returnTo` is truly required, canonicalize paths and block invalid schemes/hosts, `//evil.example`, backslashes/double encoding, CRLF, and context-path confusion. Never allow arbitrary redirects to external domains just because login succeeded.

### 7.3 `useReferer` Is Not Trusted Proof

`Referer` can be missing or spoofed, stripped by browser policies, altered by proxies, and point to external URLs. It should not be relied on as the primary source for post-login redirects without origin validation. `SavedRequest` in a server session has lifecycle advantages, yet still stems from an **original URL with client-controlled components**; both need safety rules.

### 7.4 Direct User Login

If a user opens `/login` directly (with no prior unauthenticated request), the handler finds no `SavedRequest` and uses the default target, such as `/home`. This is not a `RequestCache` bug; there was simply no "previous page" for Spring to remember.

### 7.5 Saved Request Exists But User Lacks Permission

An unauthenticated user opens `/admin`, then logs in with an account lacking `ROLE_ADMIN`. After login, the success handler may still redirect to `/admin` per the `SavedRequest`. **The new request must return 403**, never bypassing authorization just because the URL was cached. If UX wants a "permission denied" notice and return to dashboard, that is an explicitly designed flow—not a privilege granted by the cache.

## 8. RequestCacheAwareFilter Handles the Returning Request

`RequestCacheAwareFilter` calls `RequestCache.getMatchingRequest(request, response)`; when a matching wrapper is returned, it passes that wrapper down the remainder of the filter chain. The goal is to let downstream layers see request metadata matching the `SavedRequest` under appropriate conditions.

Pseudo-flow:

```java
HttpServletRequest wrapped =
        requestCache.getMatchingRequest(request, response);

if (wrapped == null) {
    chain.doFilter(request, response);
} else {
    chain.doFilter(wrapped, response);
}
```

This is a **logic illustration**, not a suggestion to register a duplicate filter alongside Spring Security. The filter is already part of the chain when request caching is configured. Never register a second `RequestCacheAwareFilter` as a Servlet `@Component` if it is already in `FilterChainProxy`.

### 8.1 Why Isn't the Saved Request Deleted Immediately After Login?

The handler's job is to **send the browser to the target**. If it deleted `SavedRequest` immediately when issuing the redirect, `RequestCacheAwareFilter` would not find it to create `SavedRequestAwareWrapper` for the returning request. That is why the Javadoc notes: when redirecting to the saved URL, the handler **leaves the cache intact** for the next matching request to consume.

### 8.2 If the User Doesn't Follow the Redirect or Closes the Browser

The saved request may remain in the session until overwritten, cleared, session expiration, or removal by another flow. Do not assume it self-expires in milliseconds. With distributed session stores, review retention/TTL; for sensitive data, minimize what the cache retains and clean up on logout/account switch.

### 8.3 If the URL Does Not Match

If the client drops the `continue` query param, alters the path, changes scheme/host, or a proxy rewrites the URL, `getMatchingRequest` may not find a match; the saved request remains until another mechanism cleans it up. Access to the page itself can still be allowed by authorization; **restoring metadata and accessing the endpoint are two separate things**.

## 9. Requests That Must Not Auto-Replay: POST, Upload, Payment, and State-Mutating Operations

This is the most critical safety boundary of `SavedRequest`.

### 9.1 Browser Redirects Typically Issue a GET

Suppose a user submits:

```http
POST /orders/confirm HTTP/1.1
Content-Type: application/json

{"orderId":42,"confirm":true}
```

If unauthenticated and redirected to form login, do not expect `RequestCache` to hold the entire JSON stream and automatically execute `POST /orders/confirm` after login. Redirecting to the original URL is a **new navigation**, usually a GET. The old request's raw body is not guaranteed by the framework to be reconstructed or resubmitted automatically.

Some metadata such as method/parameters may reside in `DefaultSavedRequest`, but the wrapper does not turn it into an exactly-once transaction engine. Do not interpret "replay request" in Javadoc as a promise to **replay arbitrary side effects** byte-for-byte.

### 9.2 CSRF May Block POST Before It Is Ever Cached

In cookie-based browser apps, `CsrfFilter` typically runs in the filter chain before unsafe POST processing. If a CSRF token is missing, the request can be rejected with 403 before ever reaching the authentication entry point and request cache; not every anonymous POST enters `SavedRequest`.

Even a POST with a valid CSRF token does not automatically become replayable after login. When identity changes, the CSRF token may be rotated/invalidated, so resubmitting old data without fetching a fresh token fails by design.

### 9.3 Safe Pattern: POST → Require Login → Return to GET/Draft

For multi-step forms:

1. User prepares an **explicitly saved draft** with session/user scope, TTL, and state validation.
2. If login is required, navigate to `GET /drafts/{id}/review` or an allowlisted GET route.
3. After login, the browser returns to the review screen rather than re-running POST automatically.
4. The user reviews the changes and actively clicks Confirm with a fresh CSRF/idempotency key.
5. The server verifies object/tenant authorization and processes the transaction exactly once, preventing duplicate submits.

For APIs, return 401 or redirect per contract so the client only re-sends unsafe requests **after explicit intent** and handles idempotency/confirmation; never stuff transaction bodies into a `next` query string.

### 9.4 GET Must Also Have No Side Effects

Saved-request UX works best when GET respects HTTP **safe** semantics. If an endpoint like `GET /delete?id=42` deletes data, a post-login redirect could unintentionally execute a dangerous operation. Fix the API so mutations use POST/PUT/PATCH/DELETE with proper CSRF/authz/idempotency; never treat `SavedRequest` as a substitute defense.

## 10. Which Configurations Create, Save, or Skip Saved Requests?

### 10.1 Default Form Login

With:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/reports/**").authenticated()
                    .anyRequest().permitAll())
            .formLogin(Customizer.withDefaults())
            .build();
}
```

Spring Security configures default `HttpSessionRequestCache`, login entry point, and saved-request-aware success handler. **You do not need a custom controller to redirect back to the pre-login page.** Customize only for concrete needs: filter chains, routes, post-login UX, performance, or security rules.

### 10.2 Customizing a Shared RequestCache

```java
@Bean
RequestCache requestCache() {
    HttpSessionRequestCache cache =
            new HttpSessionRequestCache();

    cache.setMatchingRequestParameterName("continue");
    cache.setRequestMatcher(
            new AntPathRequestMatcher("/reports/**", "GET"));
    return cache;
}

@Bean
SavedRequestAwareAuthenticationSuccessHandler savedRequestSuccessHandler(
        RequestCache cache) {

    SavedRequestAwareAuthenticationSuccessHandler handler =
            new SavedRequestAwareAuthenticationSuccessHandler();
    handler.setRequestCache(cache);
    handler.setDefaultTargetUrl("/home");
    return handler;
}

@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http, RequestCache cache,
        SavedRequestAwareAuthenticationSuccessHandler handler)
        throws Exception {

    return http
            .requestCache(c -> c.requestCache(cache))
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/reports/**").authenticated()
                    .requestMatchers("/home").permitAll()
                    .anyRequest().denyAll())
            .formLogin(login -> login.successHandler(handler))
            .build();
}
```

These are **sample `@Bean` methods to assemble in `@Configuration`/Spring Boot**, omitting imports/package and controllers. The full runnable version is in Section 13.

### 10.3 Why Must the Same RequestCache Be Used?

If `ExceptionTranslationFilter` saves into cache A, while `SavedRequestAwareAuthenticationSuccessHandler` reads from cache B (e.g., B is `NullRequestCache` or uses a different key), post-login finds no saved URL and falls back to `/home`. If the success handler reads correctly while `RequestCacheAwareFilter` uses cache C, the redirect URL may match, yet request matching/removal never completes. Configure one shared instance or ensure implementations access the same storage/attribute namespace; avoid splitting the saved-request lifecycle across inconsistent stores.

### 10.4 Disabling Request Saving Completely with NullRequestCache

For applications that do not need to return to an old URL:

```java
http.requestCache(cache -> cache
        .requestCache(new NullRequestCache()));
```

`NullRequestCache` neither saves requests nor restores matching requests. After login, `SavedRequestAwareAuthenticationSuccessHandler` finds no saved request and uses the configured default target. This suits apps with fixed navigation, SPAs using client-side routers, JSON-401 APIs, or setups aiming to minimize session allocations for unauthenticated traffic.

**However:** Disabling `RequestCache` does not disable session authentication or `SecurityContextRepository`. Users can still log in via forms and maintain a session; only **remembering the prior URL** is disabled.

### 10.5 CookieRequestCache and Custom Solutions

Some Spring Security versions provide `CookieRequestCache` to store partial URL info in a cookie. When using cookies, evaluate:

- Integrity: cookies are client-carried; never trust an arbitrary redirect target without integrity protection/allowlisting.
- Confidentiality: sensitive URLs should not appear in cookies/logs.
- Cookie flags, TTL, scope, size, and cross-site behavior.
- API version and limitations on retained metadata.
- Logout, user switching, and tenant switching scenarios.

Do not switch to cookies or custom caches merely to avoid `HttpSession` while skipping open-redirect, replay, and privacy checks.

## 11. SecurityContextRepository and RequestCache Are Two Separate Stores

Many "logged in yet didn't return to the old page" bugs stem from **one of these two stores** being misconfigured:

| Store | What does it store? | What goes wrong if missing? |
| --- | --- | --- |
| **`RequestCache`** | SavedRequest / pre-login navigation target. | Login succeeds, yet lands on `/home` forgetting the old page. |
| **`SecurityContextRepository`** | Verified `SecurityContext` and `Authentication`. | Login may redirect to the right old URL, yet **the new request is anonymous**, causing a login loop. |

Specifically:

```text
RequestCache right, SecurityContextRepository wrong:
   /reports -> /login -> login OK -> /reports -> /login -> ...

RequestCache wrong, SecurityContextRepository right:
   /reports -> /login -> login OK -> /home
   (User is still authenticated, just lost original destination.)
```

In Spring Security 6, custom authentication wishing to persist context across requests must call `SecurityContextRepository.saveContext(...)` if the built-in flow does not do it for you. `SavedRequestAwareAuthenticationSuccessHandler` **does not** persist authentication; it only decides navigation.

### 11.1 Distinction from SessionAuthenticationStrategy

`SessionAuthenticationStrategy` runs after successful login to prevent session fixation, enforce concurrent session limits, or reset CSRF tokens per config. `RequestCache` saves the original URL while anonymous. On login success:

1. Provider verifies credentials.
2. `SessionAuthenticationStrategy` (if applicable) handles the session.
3. `SecurityContext` is set/saved.
4. Success handler queries `RequestCache` to pick the target.
5. Response commits/redirects.
6. Browser returns, and `RequestCacheAwareFilter` attempts to match the saved request.

Do not create a logged-in session simply by writing a saved request. Never invoke session strategy on every request containing `continue`.

### 11.2 How Does Session Fixation Change the ID While Keeping the Saved Request?

If the pre-login `HttpSession` already holds a `SavedRequest`, login success may invoke `ChangeSessionIdAuthenticationStrategy` to rotate the session ID. In Servlet 3.1+, this changes **the ID of the logical session** rather than discarding all attributes. As a result, `SavedRequest` can remain intact for the success handler to read after login. If using `newSession`/`migrateSession` with another policy, verify whether saved requests are migrated or dropped; do not assume every fixation strategy behaves identically.

### 11.3 Logout and Identity Switching

When a session logs out, decide which `SavedRequest` entries are kept or cleared, whether the user switched to a different account, and whether the redirect destination remains valid. A saved URL may contain tenant or workspace details from the previous user. Never treat an old cache entry as "proof" that the new user can access the old tenant; authorization must re-check, and saved requests may need clearing on logout/account switch.

## 12. UX Choices: When to Return to the URL vs. Go to the Default Page?

| Scenario | Generally sensible rule |
| --- | --- |
| User clicks GET link to internal report | Save URL and redirect back to that report after login, if still authorized. |
| User clicks Sign In from landing page | No SavedRequest; go to default dashboard. |
| User just registered / needs onboarding | May force mandatory onboarding/password change, discarding saved request per policy. |
| ADMIN role requires step-up or MFA | Redirect only after required authentication level is met; never bypass steps via SavedRequest. |
| User locked or wrong password | Stay in failure flow; never treat saved request as authentication success. |
| User lacks permission for saved resource | Return 403 or permission error UX; never skip authorization. |
| SPA with purely client-side routes | May use validated state/correlation tokens and client navigation instead of HttpSessionRequestCache. |
| Stateless API / JWT | Return 401/WWW-Authenticate or JSON; do not create sessions just to remember URLs. |
| Kiosk / shared public device | Minimize sensitive cached metadata, short session TTL, and clear on logout. |
| Multiple parallel tabs | Design per-tab return flow if needed; by default one SavedRequest can be overwritten. |

There is no single behavior for every product. What matters is that **the flow is explicitly defined, tested, and never turns client-supplied URLs into arbitrary redirects**.

## 13. Runnable Spring Boot 3.x Example: Anonymous GET → Login → Saved Redirect

This learning project uses Java 17+, Spring Boot 3.3.13, Spring Security 6.x, and `MockMvc`. The goal is to accurately reproduce `SavedRequest` with **built-in form login**, keeping focus on `RequestCache` rather than writing a custom login filter.

- `/reports/summary`: GET requires authentication; returns JSON with username and `period`.
- `/admin/panel`: GET requires `ROLE_ADMIN` to prove a saved request does not grant privileges automatically.
- `/home`: public GET, fallback for direct login.
- Two demo accounts: `alice` has `ROLE_USER`, `bob` has `ROLE_ADMIN`.
- One shared `HttpSessionRequestCache` bean used in both `http.requestCache` and `SavedRequestAwareAuthenticationSuccessHandler`.
- Saves only GETs under `/reports/**` or `/admin/**` via a safe `RequestMatcher`, never saving POSTs.
- Spring Security CSRF **stays enabled**; MockMvc supplies tokens with `csrf()`.
- `SavedRequestAwareAuthenticationSuccessHandler` keeps the saved request in cache for the redirected request.

**Scope:** Users are in `InMemoryUserDetailsManager`, sessions are in-memory, and there is no database. This is a Servlet/MockMvc application, not WebFlux. Passwords in code are **for localhost only**; real deployments must use proper secret/config policies and HTTPS.

### 13.1 Structure

```text
saved-request-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/SavedRequestApplication.java
    └── test/java/demo/SavedRequestIntegrationTest.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'saved-request-lab'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Versions are pinned to reproduce the example. This is not a recommendation to pick an end-of-support framework branch for new production work; choose an organizationally supported Spring Boot/Security line for production deployments.

### 13.2 Spring Security Application

File `src/main/java/demo/SavedRequestApplication.java`:

```java
package demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler;
import org.springframework.security.web.savedrequest.HttpSessionRequestCache;
import org.springframework.security.web.savedrequest.RequestCache;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.security.web.util.matcher.OrRequestMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SavedRequestApplication {

    public static void main(String[] args) {
        SpringApplication.run(SavedRequestApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("local-demo-password"))
                .roles("USER")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("different-demo-password"))
                .roles("ADMIN")
                .build();

        return new InMemoryUserDetailsManager(alice, bob);
    }

    @Bean
    RequestCache requestCache() {
        HttpSessionRequestCache cache = new HttpSessionRequestCache();

        // Spring Security 6: query cache when redirect-following request carries marker.
        cache.setMatchingRequestParameterName("continue");

        // Only keep GETs for the two navigation-meaningful areas.
        cache.setRequestMatcher(new OrRequestMatcher(
                new AntPathRequestMatcher("/reports/**", "GET"),
                new AntPathRequestMatcher("/admin/**", "GET")));

        return cache;
    }

    @Bean
    SavedRequestAwareAuthenticationSuccessHandler successHandler(
            RequestCache requestCache) {

        SavedRequestAwareAuthenticationSuccessHandler handler =
                new SavedRequestAwareAuthenticationSuccessHandler();
        handler.setRequestCache(requestCache);
        handler.setDefaultTargetUrl("/home");
        return handler;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            RequestCache requestCache,
            SavedRequestAwareAuthenticationSuccessHandler handler)
            throws Exception {

        return http
                .requestCache(cache -> cache.requestCache(requestCache))
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(HttpMethod.GET, "/reports/**")
                            .authenticated()
                        .requestMatchers(HttpMethod.GET, "/admin/**")
                            .hasRole("ADMIN")
                        .requestMatchers(HttpMethod.GET, "/home")
                            .permitAll()
                        .anyRequest().denyAll())
                .formLogin(form -> form.successHandler(handler))
                .logout(Customizer.withDefaults())
                .build();
    }
}

@RestController
class ReportController {

    @GetMapping("/reports/summary")
    Map<String, String> summary(
            @RequestParam String period,
            Authentication authentication) {
        return Map.of(
                "username", authentication.getName(),
                "period", period);
    }

    @GetMapping("/admin/panel")
    String adminPanel(Authentication authentication) {
        return "admin for " + authentication.getName();
    }

    @GetMapping("/home")
    String home() {
        return "home";
    }
}
```

**Why use `formLogin(...)` instead of writing a custom POST login?** The standard Spring Security filter handles passwords, session strategy, context persistence, and the success handler. This lesson focuses on `RequestCache`; writing a custom filter risks unrelated bugs obscuring the saved-request mechanism.

**Why two matchers for the cache?** `ExceptionTranslationFilter` may want to save GETs into the reports/admin areas. User Alice returns to `/admin/panel` after login if that URL was saved, yet lacking `ROLE_ADMIN`, the follow-up request still gets 403. `RequestMatcher` prevents saving POSTs or unsuitable URLs; adjust to match your app's design.

**Why not instantiate `RequestCacheAwareFilter` manually?** `HttpSecurity.requestCache(...)` integrates properly into the Spring Security chain without registering an extra Servlet filter outside the chain. A filter registered twice can cause inconsistent replay/cleanup.

**Why do the handler and chain share one instance?** The handler reads the saved request from the exact store where `ExceptionTranslationFilter` saved it; `RequestCacheAwareFilter` in the chain matches returning requests against that same store. Applications never need to touch the session attribute key manually.

### 13.3 MockMvc Integration Tests

File `src/test/java/demo/SavedRequestIntegrationTest.java`:

```java
package demo;

import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import org.springframework.security.web.savedrequest.SavedRequest;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SavedRequestIntegrationTest {

    @Autowired
    MockMvc mvc;

    private MockHttpSession sessionFrom(MvcResult result) {
        MockHttpSession session =
                (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }

    private MvcResult signIn(
            MockHttpSession session, String username, String password)
            throws Exception {

        return mvc.perform(post("/login")
                        .session(session)
                        .with(csrf())
                        .param("username", username)
                        .param("password", password))
                .andExpect(status().is3xxRedirection())
                .andReturn();
    }

    @Test
    void originalReportIsSavedAndRestoredAfterLogin() throws Exception {
        // 1. Anonymous GET to protected route.
        MvcResult initial = mvc.perform(
                        get("/reports/summary").param("period", "2026"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        String loginRedirect = initial.getResponse().getRedirectedUrl();
        assertNotNull(loginRedirect);
        assertTrue(loginRedirect.contains("/login"));

        MockHttpSession session = sessionFrom(initial);

        Object stored = session.getAttribute("SPRING_SECURITY_SAVED_REQUEST");
        assertTrue(stored instanceof SavedRequest);
        SavedRequest saved = (SavedRequest) stored;

        assertTrue(saved.getRedirectUrl()
                .contains("/reports/summary?period=2026"));

        // 2. Log in with THE SAME SESSION that stored the prior request.
        MvcResult login = signIn(
                session, "alice", "local-demo-password");

        String location = login.getResponse().getRedirectedUrl();
        assertNotNull(location);

        // Handler does not send to /home because a SavedRequest exists.
        assertTrue(location.contains("/reports/summary?period=2026"));
        assertTrue(location.contains("continue"));

        // 3. After success handler, SavedRequest remains for the follow-up GET.
        assertNotNull(session.getAttribute(
                "SPRING_SECURITY_SAVED_REQUEST"));

        // 4. Browser follows redirect with that session cookie.
        mvc.perform(get(URI.create(location)).session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"))
                .andExpect(jsonPath("$.period").value("2026"));

        // 5. RequestCacheAwareFilter has consumed the saved request.
        assertNull(session.getAttribute("SPRING_SECURITY_SAVED_REQUEST"));
    }

    @Test
    void directLoginWithoutSavedRequestUsesDefaultTarget() throws Exception {
        MockHttpSession session = new MockHttpSession();

        MvcResult login = signIn(
                session, "alice", "local-demo-password");

        String location = login.getResponse().getRedirectedUrl();
        assertNotNull(location);
        assertTrue(location.endsWith("/home"));

        mvc.perform(get("/reports/summary")
                        .session(session)
                        .param("period", "2025"))
                .andExpect(status().isOk());
    }

    @Test
    void savedAdminUrlDoesNotGrantUserAnAdminRole() throws Exception {
        MvcResult initial = mvc.perform(get("/admin/panel"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session = sessionFrom(initial);

        MvcResult login = signIn(
                session, "alice", "local-demo-password");

        String location = login.getResponse().getRedirectedUrl();
        assertNotNull(location);
        assertTrue(location.contains("/admin/panel"));

        // Saved URL does not bypass authorization: Alice still lacks ADMIN.
        mvc.perform(get(URI.create(location)).session(session))
                .andExpect(status().isForbidden());
    }

    @Test
    void postLoginIsProtectedByCsrfAndNotSavedAsNavigation()
            throws Exception {

        mvc.perform(post("/login")
                        .param("username", "alice")
                        .param("password", "local-demo-password"))
                .andExpect(status().isForbidden());

        // RequestCache only saves GET under reports/admin.
        MvcResult initial = mvc.perform(
                        get("/reports/summary").param("period", "2026"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session = sessionFrom(initial);
        MvcResult login = signIn(
                session, "alice", "local-demo-password");

        assertNotNull(login.getResponse().getRedirectedUrl());
        assertFalse(login.getResponse().getRedirectedUrl()
                .contains("/login?error"));
    }
}
```

**Test explanation:**

- Test 1 verifies **all four consecutive requests**: anonymous GET → login redirect → valid POST login with the same session → GET redirected location. It also verifies `SPRING_SECURITY_SAVED_REQUEST` persists immediately after the success handler and is removed once the follow-up request matches.
- Test 2 has no cached URL, so the handler uses `defaultTargetUrl="/home"`. Authentication still persists in the session; a `SavedRequest` is not required for login to be saved.
- Test 3 proves a saved request does not grant privileges. Alice is redirected to the admin URL, yet post-login access still returns HTTP 403.
- Test 4 proves form login POST requires a CSRF token under a browser cookie flow. `RequestCache`'s matcher only caches GETs for reports/admin and is not used to replay a POST.

**These results reflect expectations from the source code**, not a claim to have executed the build/MockMvc in the reader's environment. In newer framework versions, the redirect strategy may pick relative or absolute URLs; tests only assert the required path/query. If a test fails, check the session object, `Location` header, query marker, repository, and `SecurityFilterChain` order—never disable CSRF to "make tests green".

### 13.4 Commands to Run

When a Gradle wrapper is present:

```bash
./gradlew test
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat bootRun
```

Without a wrapper, with a compatible Gradle installed:

```bash
gradle test
gradle bootRun
```

Because the code imports Spring Boot/Web/Security, running `javac SavedRequestApplication.java` alone **is not enough** without the classpath. `MockMvc` tests are the most convenient way to simulate sessions and CSRF; the demo does not expose a separate CSRF-token endpoint for curl. Do not hardcode tokens or disable CSRF app-wide just to test from the terminal.

### 13.5 Checking with a Real Browser/HTTP Client

After starting the app, open a protected URL in a fresh browser with no session:

```text
http://localhost:8080/reports/summary?period=2026
```

The browser redirects to `/login`; use:

```text
Username: alice
Password: local-demo-password
```

After valid form login, if the flow works properly, the browser returns to the `period=2026` report. The `continue` query marker may appear in the URL in Spring Security 6. Visiting `/login` directly first and then logging in takes you to `/home` due to the fallback config.

In a test environment's DevTools Network tab, inspect: status 302 on the initial request, `Location: /login`, Set-Cookie/CSRF/session, `Location` on login POST, and the GET after redirect. Never capture or share full cookie/session IDs, raw passwords, or Bearer tokens with others.

## 14. Pure Java 17 Program: Post-Login Destination Selection

To study priority logic **without Spring dependencies**, the snippet below simulates choosing between "always home", "saved URL exists", and "fallback". It **does not** test real sessions/cookies/redirects; it only illustrates precedence.

File `SavedTargetDemo.java`:

```java
public final class SavedTargetDemo {

    static String choose(
            String savedUrl,
            boolean alwaysDefault,
            String defaultTarget) {

        if (alwaysDefault) {
            return defaultTarget;
        }
        if (savedUrl != null && !savedUrl.isBlank()) {
            return savedUrl;
        }
        return defaultTarget;
    }

    public static void main(String[] args) {
        System.out.println("saved="
                + choose("/reports/summary?period=2026",
                        false, "/home"));
        System.out.println("direct="
                + choose(null, false, "/home"));
        System.out.println("forced="
                + choose("/reports/summary?period=2026",
                        true, "/home"));
    }
}
```

Compile/run:

```bash
javac SavedTargetDemo.java
java SavedTargetDemo
```

Exact stdout:

```text
saved=/reports/summary?period=2026
direct=/home
forced=/home
```

This is a destination-selection exercise; **never use `choose(...)` directly on client-submitted URLs in production**. Canonicalize/allowlist targets, verify endpoint permissions, and disallow arbitrary off-origin redirects. The real `RequestCache`/`SavedRequestAwareAuthenticationSuccessHandler` steps are explained above.

## 15. Security: Open Redirects, URL Injection, and Host/Proxy Headers

### 15.1 SavedRequest Does Not Make Input URLs Trusted

Requests arriving at the app include scheme, host, port, path, and query. Parts of these are influenced by browsers/clients and proxy headers. If an app trusts arbitrary `Host` or `X-Forwarded-Host` headers, an attacker can trick saved redirects into pointing at an external domain or building a cross-origin URL (*host-header poisoning*).

Defenses:

1. At the reverse proxy/load balancer, **allowlist valid Hosts**; never accept arbitrary forwarded headers directly from the internet.
2. Configure forwarded-header handling to trust only legitimate proxies; never blindly trust client-supplied values.
3. Restrict saved-request routes via `RequestMatcher` (GET navigation paths) and enforce HTTPS.
4. When writing custom success redirect logic, validate origin, context path, and path normalization; reject `//example.org`, CRLF, multi-layer percent-encoding, and path traversal.
5. Do not allow unchecked client-supplied `targetUrlParameter`/`returnTo`. If needed, use server-side correlation state with TTL or signed, allowlisted data.
6. Avoid redirecting back to an IdP or external domain based solely on a cached URL without proper validation.
7. Include security tests for malformed hosts/paths/queries, trailing slashes, UTF-8 encoding, and proxy behavior.

**Do not trust a string simply because it sits in `HttpSession`**; its value may have originated from a client-controlled request prior to login.

### 15.2 Preventing Redirect Loops

A loop such as:

```text
/reports -> /login -> login OK -> /reports -> /login -> ...
```

can happen because:

- `SecurityContext` is not persisted across the session.
- Browser fails to store/send `JSESSIONID` after login (SameSite, Secure, Path, Domain, CORS).
- Node B's session store lacks state written on Node A.
- Login and target use different `SecurityFilterChain` or `SecurityContextRepository` configurations.
- The saved target requires an authentication mechanism or MFA not satisfied by the completed login.
- Entry point/redirect target is misconfigured (e.g., login URL is also protected).
- A custom success handler commits the response early before the session/context is saved.

Never fix a loop by doing `permitAll("/reports/**")`, which drops data protection. Verify status codes, cookies, session, context persistence, and policy instead.

### 15.3 Do Not Store Secrets in URLs

Queries such as:

```text
/reports?access_token=...
/reset?otp=...
/billing?cardNumber=...
```

should not be casually cached and redirected back to. URLs can leak via browser history, proxy logs, analytics, Referer headers, session replication, and debug output. Password/reset tokens have their own lifecycles and should not share `RequestCache` with protected GET navigation.

A `RequestMatcher` permitting paths does not automatically strip sensitive query parameters. Design routes without secrets in query strings and sanitize queries if needed; safest of all is **never using saved requests** for those sensitive paths.

### 15.4 Do Not Log Raw DefaultSavedRequest

`DefaultSavedRequest` can retain URL, parameter, and header metadata. Never log `savedRequest.toString()`, full `HttpSession` dumps, or serialized `SecurityContext` in production. Limit logging to: request ID, verified account ID, route category, boolean saved/redirected/matched flags, and error codes; avoid full queries, authorization headers, cookies, or credentials.

## 16. Distinguishing 401, 302, 403, and CSRF Errors

| Scenario | Common behavior | Meaning |
| --- | --- | --- |
| Browser anonymous GET protected | 302 to `/login` + possible GET cache | Starts form login. |
| Stateless API without Bearer token | 401/WWW-Authenticate or 401 JSON | Client must present credentials, usually no HTML redirect. |
| Form login wrong password | Redirect `/login?error` or matching failure response | Not a success; does not consume SavedRequest for a success redirect. |
| Logged in but missing role | 403 | Authenticated but unauthorized; saved URL does not bypass. |
| POST missing/invalid CSRF | Usually 403 before authentication logic | Do not infer wrong password or broken RequestCache. |
| Session expired before follow-up GET | May redirect to login again | Context lost; SavedRequest may or may not remain depending on lifecycle. |
| `NullRequestCache` | No saved URL; login uses fallback | Intentionally skips saving navigation. |
| `alwaysUseDefaultTargetUrl=true` | Always goes to default target, clears cache | Navigation policy prioritizes default. |

**Note:** HTTP status codes depend on the configured entry point/failure handler; not all Spring Security apps return the exact same status. This Boot demo uses default form login and a generated login page, so anonymous GETs typically yield 302.

## 17. Common Misconceptions

### 17.1 "SavedRequest is a feature that auto-resubmits POST forms"

False. The primary flow is a redirect and a new request to the old URL, usually GET; streams/bodies are not guaranteed to be recreated. State-mutating transactions need form drafts/confirmation and idempotency.

### 17.2 "Having a saved request in session means the user is authenticated"

False. `SPRING_SECURITY_SAVED_REQUEST` is navigation state; `SPRING_SECURITY_CONTEXT` is where `Authentication` may reside—and even then, authentication must still pass authorization.

### 17.3 "The success handler redirects and immediately deletes the cache"

Not necessarily. On the `SavedRequest` branch, the handler typically **leaves the saved request** for `RequestCacheAwareFilter` to consume on the follow-up matching request.

### 17.4 "`getRequest` and `getMatchingRequest` are the same"

False. `getRequest` reads while keeping the cache intact. `getMatchingRequest` checks the current request and consumes it on a match.

### 17.5 "continue is a CSRF token or second password"

False. It is a **query marker optimizing saved-request lookup** in Spring Security 6; it grants no authority and provides no CSRF protection.

### 17.6 "Every login returns to the previous page"

False. Without a `SavedRequest`, or when using `alwaysUseDefaultTargetUrl`/`NullRequestCache`, login goes to the default target.

### 17.7 "Restoring the old URL grants access"

False. Authorization still executes on the post-redirect GET. If the account lacks permissions or tenant membership, access must be denied.

### 17.8 "Switching to `NullRequestCache` disables login sessions"

False. `RequestCache` stores **navigation**; `SecurityContextRepository` stores **authentication**. They are separate functions.

### 17.9 "`HttpSessionRequestCache` keeps an unlimited history of tabs"

False. Under default configuration, one session attribute holds one `SavedRequest` at a time, so subsequent anonymous requests can overwrite earlier ones.

### 17.10 "You can freely use `Referer` or `next` as the redirect target"

False. Clients can control or spoof these values; validate origin/path to prevent open redirects.

### 17.11 "Anonymous POST 403 means a RequestCache bug"

No. `CsrfFilter` can reject the POST before it reaches the authentication mechanism. Never disable CSRF just to force POST caching.

### 17.12 "A URL with ?continue makes the server trust the user is logged in"

False. The server still loads `SecurityContext`, checks `Authentication`, and verifies endpoint permissions; the marker only tells `RequestCache` whether to check the session for a `SavedRequest`.

## 18. Practice Exercises with Answers

**Q1.** An anonymous user does GET `/reports/summary?period=2026` and gets redirected to login. What stores the initial request?

**Answer:** `RequestCache` (typically `HttpSessionRequestCache`) stores `SavedRequest`/`DefaultSavedRequest` in `HttpSession`, usually under `SPRING_SECURITY_SAVED_REQUEST`. It is distinct from `SecurityContext`.

**Q2.** After successful login, why can the success handler redirect back to the original URL?

**Answer:** `SavedRequestAwareAuthenticationSuccessHandler` calls `RequestCache.getRequest` to read the `SavedRequest` and uses `getRedirectUrl()`. If no `SavedRequest` exists, it falls back to the base handler's default target.

**Q3.** Why does `SavedRequest` remain in the session immediately after the POST login redirect?

**Answer:** The handler keeps it so `RequestCacheAwareFilter` can match it on the redirected follow-up request and consume the cache. If forced default target or `targetUrlParameter` wins, the cache may be removed immediately.

**Q4.** How does `getMatchingRequest` differ from `getRequest`?

**Answer:** It checks whether the current request matches the `SavedRequest`, builds a wrapper, and removes the saved request on match; `getRequest` reads without consuming.

**Q5.** In Spring Security 6, what is the purpose of the `continue` marker in the post-login URL?

**Answer:** It indicates `HttpSessionRequestCache.getMatchingRequest` should query `HttpSession` for a saved request, avoiding redundant lookups. The marker does not authenticate or authorize.

**Q6.** A user opens A then B in two tabs before logging in, sharing a session. Why does Tab A land on B after login?

**Answer:** A default `HttpSessionRequestCache` usually keeps one saved-request attribute, so the newer request can overwrite the earlier one. For per-tab behavior, design dedicated state with per-tab correlation.

**Q7.** Should `POST /transfer` be automatically replayed right after login?

**Answer:** No. Redirects do not guarantee raw bodies, CSRF tokens, or safe transactions. Use a draft/review/explicit confirmation flow with fresh idempotency and authorization.

**Q8.** A user with `ROLE_USER` has `/admin` as their saved URL. Can they access it after login?

**Answer:** No, if the endpoint requires `ADMIN`; the returning request still gets 403. `SavedRequest` does not bypass authorization.

**Q9.** Login succeeds yet always lands on `/home` despite previously opening a report page. What should you check?

**Answer:** Whether `RequestCache` saved the request; whether the matcher permits that GET; whether the same session was used; whether the handler shares the same cache; and whether `alwaysUseDefaultTargetUrl`/`targetUrlParameter`/`NullRequestCache` overrode it.

**Q10.** Login redirects to the right old URL, yet that request is anonymous again. Where is the bug usually?

**Answer:** Not in the request-cache URL; usually `SecurityContextRepository` failed to save context, cookies didn't reach the browser, or session stores/chains differ. Check context persistence and session cookies.

**Q11.** Why validate Host and path even when `SavedRequest` is stored server-side?

**Answer:** Because the initial metadata can still be influenced by client and proxy URLs/headers. Trusting unvalidated sources allows redirects to be steered toward malicious domains.

**Q12.** How does `alwaysUseDefaultTargetUrl(true)` differ from `setDefaultTargetUrl("/home")`?

**Answer:** Always using the default deletes the saved request and ignores the prior target; setting only the default specifies a fallback when no saved URL exists or when base-handler branches apply.

**Q13.** Does disabling `RequestCache` with `NullRequestCache` make `GET /reports` public?

**Answer:** No. Authorization remains active. Users must still log in; only remembering the prior URL for redirecting back is disabled.

**Q14.** A user hits a URL with an `access_token` query before logging in. Should it be saved in session to redirect back to?

**Answer:** No. Tokens/secrets in URLs risk leaking via logs, history, sessions, and Referer. Design a dedicated credential flow, restrict saved paths, and strip sensitive data.

**Q15.** Why is testing only `POST /login` and asserting status 302 insufficient?

**Answer:** It does not prove `RequestCache` was populated by an anonymous GET, that the redirect target is accurate, that the session persists, that the follow-up request is authorized, and that the cache is consumed. Full-chain integration tests are needed.

## 19. Production Test Matrix

| Scenario | What must be verified |
| --- | --- |
| Anonymous protected GET | Redirects to login; SavedRequest captures exact route/query and creates session per policy. |
| GET outside matcher | No SavedRequest created; login falls back to default. |
| Anonymous GET with existing query | Redirects with exact query + `continue` marker per version/config. |
| Already authenticated hits protected | Does not needlessly add saved request; controller returns 200 if authorized. |
| Wrong password login | Failure flow; does not use saved URL as a successful login redirect. |
| Valid login after anonymous GET | Success handler reads saved URL and 302s to the right target. |
| Following redirect with valid cookie | Principal restored and authorization enforced. |
| Following matching redirect | `RequestCacheAwareFilter` consumes saved request. |
| Request without `continue` in Security 6 | Does not query saved request as a cache-match path per config; grants no privilege. |
| Direct login | Falls back to `/home` without inventing an old URL. |
| Forced default target | Clears cache and goes to dashboard despite saved request. |
| TargetUrlParameter | If enabled, accepts only validated targets; verifies cache removal. |
| User lacks role for saved URL | 403; cached URL never bypasses authorization. |
| Saved URL belongs to another tenant | Post-login access blocked by tenant-scope authorization. |
| Two anonymous tabs | Verify overwrite behavior or per-tab state mechanism. |
| POST missing CSRF | 403; never replays POST via cache. |
| POST with sensitive body | Does not serialize body into navigation state or auto-execute mutation. |
| Logout / user switch | Cache cleaned up per policy; no leaking of prior account's URLs. |
| Session expired | SavedRequest gone or handled per policy; stale sessions rejected. |
| Multi-node, distributed session | Both SavedRequest and SecurityContext read consistently. |
| Abnormal Proxy/Host headers | No open redirect to client-supplied domains. |
| Secure/SameSite/path cookies | Real browser retains and sends matching session ID. |
| NullRequestCache | Does not save/restore navigation; authentication still works independently. |
| Broken SecurityContextRepository | Tests catch redirect loops when sessions fail to persist. |
| Security 5 → 6 migration | `continue` marker, success handler, and custom cache behavior work properly. |
| Logs/observability | Never prints URL queries containing secrets, cookies, tokens, or raw request headers. |

## 20. Design and Operations Checklist

1. **Define scope:** should users return to the pre-login URL or always land on a dashboard?
2. **Cache only sensible navigation:** prefer safe GET/HEAD, narrow request matchers to allowed areas, avoid mutating POSTs and URLs with secrets.
3. **Use the right RequestCache:** know whether you use `HttpSessionRequestCache`, `NullRequestCache`, or custom; do not mix versions/chains.
4. **Share cache with success handler:** `ExceptionTranslationFilter` saves, handler reads, and `RequestCacheAwareFilter` matches against the exact same namespace/storage.
5. **Understand `continue` in Security 6:** an optimization marker for `getMatchingRequest`, not an auth or CSRF token.
6. **Standard form login:** prefer `formLogin` unless special requirements dictate otherwise; custom filters/controllers must handle context persistence and session strategy properly.
7. **Separate context storage:** `SecurityContextRepository` persists authentication; `RequestCache` only persists the navigation target.
8. **Controlled redirects:** allowlist hosts/paths/relative URLs, accept forwarded headers only from trusted proxies, and prevent open redirects/CRLF.
9. **Never replay dangerous operations:** POST/PUT/PATCH/DELETE and uploads need dedicated confirmation/idempotency flows.
10. **Multiple tabs:** one `SavedRequest` per session can be overwritten; design per-tab state if required.
11. **Session fixation/logout:** verify ID rotation and cleanup; saved requests are not authorization.
12. **CSRF/cookies:** cookie-session browser apps need CSRF protection; configure redirect/cookie SameSite/Secure/HttpOnly properly.
13. **Distributed consistency:** check session store/TTL across nodes; never expose `SavedRequest` in logs.
14. **Insufficiently privileged users:** saved URLs remain subject to authorization and tenant scope.
15. **End-to-end testing:** anonymous GET → login → redirect → target GET, verifying data, HTTP status, and cached request removal.
16. **Operations:** monitor redirect loops, cache hit/miss, stale saved requests, and abnormal external targets; log sanitized metadata.
17. **Incident triage:** if login always lands on home by mistake, check matcher/cache/handler; if it redirects right yet returns 401, check `SecurityContextRepository`/session.
18. **Upgrades:** read Javadoc for your exact Security version, especially default matching parameters, redirect strategy, and session persistence.

## 21. Official References and Further Reading

- [Spring Security 6.5 — Servlet Architecture: Saving Requests Between Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): `ExceptionTranslationFilter`, `RequestCache`, `RequestCacheAwareFilter`, and default caching.
- [Spring Security 6.5 — Session Management Migration: Optimize Querying of RequestCache](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html): `continue` changes from Spring Security 5 to 6 and configuration examples.
- [Spring Security 6.5 — SavedRequestAwareAuthenticationSuccessHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/SavedRequestAwareAuthenticationSuccessHandler.html): `alwaysUseDefaultTargetUrl`, `targetUrlParameter`, `SavedRequest`, and fallback branches.
- [Spring Security 6.5 — RequestCache API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/savedrequest/RequestCache.html): `saveRequest`, `getRequest`, `getMatchingRequest`, and `removeRequest`.
- [Spring Security 6.5 — HttpSessionRequestCache API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/savedrequest/HttpSessionRequestCache.html): session attribute, `matchingRequestParameterName`, matcher, and session creation.
- [Spring Security 6.5 — SavedRequest API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/savedrequest/SavedRequest.html): cached request data and `getRedirectUrl`.
- [Spring Security 6.5 — RequestCacheAwareFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/savedrequest/RequestCacheAwareFilter.html): restoring the wrapper after redirect when requests match.
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): form login flow and `AuthenticationSuccessHandler`.
- [Spring Security 6.5 — Authentication Persistence](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html): `SecurityContextRepository` and session state vs. saved-request navigation.
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): protecting unsafe methods and impact on form login.
- [Spring Security 6.5 — MockMvc Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc.html): integration tests for Spring Security.
- [OWASP — Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html): validating redirect targets and preventing open redirects.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookies, session IDs, lifecycle, and privacy.

**Conclusion:** `RequestCache` remembers a **navigation request** blocked due to missing authentication. `ExceptionTranslationFilter` saves it; `SavedRequestAwareAuthenticationSuccessHandler` picks the original URL after login; `RequestCacheAwareFilter` can match and consume it when the browser returns. In Spring Security 6, `continue` primarily optimizes cache lookups. None of these components authenticate users, replace `SecurityContextRepository`, grant permissions, or **auto-replay POST operations with bodies**. The right design is to **return to safe GETs, re-check authorization, validate redirect targets, and protect sessions/CSRF**.