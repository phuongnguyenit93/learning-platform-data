# Login Succeeds, Yet Subsequent Requests Are Unauthenticated — Spring Security Diagnostics

A very common bug in Spring Security applications is: **POST /login reports success, or logs show Authentication is authenticated, yet the next GET request receives 401, 403, or redirects to /login**. The issue is not necessarily the password. Often a successful authentication **proves only that one request or one flow step obtained an Authentication**, while the next request needs an identity-persistence mechanism: a session cookie sent back, `SecurityContext` saved in `SecurityContextRepository`, or a valid Bearer token sent on stateless requests.

This lesson walks through ordered diagnostics in Spring Security Servlet: distinguishing symptoms, inspecting requests/responses and sessions, understanding `SecurityContextHolderFilter`, fixing custom logins that fail to save context, handling cookies/CORS/proxies/clusters, avoiding mixed `SecurityFilterChain`s, checking OAuth2/OIDC/SAML, and writing integration tests. It includes a standalone Java 17+ persistence simulation and clearly scoped Spring Boot snippets.

**First principle:** `SecurityContextHolder.clearContext()` at the end of a Servlet request is usually the **right** behavior to protect thread pools. The fix is not keeping ThreadLocal alive across requests; the fix is choosing the right **persist or re-authenticate** mechanism per your architecture.

## 1. Precisely Defining "Login Succeeded" vs "Unauthenticated"

The outcomes below can have different root causes:

| Observation | Cannot Yet Conclude | What to Check |
| --- | --- | --- |
| Login POST returns 200 | Not sure Spring Security created `Authentication` | Response contract, `AuthenticationManager`, and success handler |
| Login POST returns 302 | Not sure session was saved | `Location` header, `Set-Cookie`, repository |
| `AuthenticationSuccessEvent` fired | Not sure browser got session/cookie/token | Context-saving step and flow-completion step |
| Next request returns 302 to `/login` | May be unauthenticated under form login | Cookie, saved context, filter chain |
| Next request returns 401 | May lack credentials/token or session | `WWW-Authenticate`, `Authorization` header, cookie |
| Next request returns 403 | May already be **authenticated** but lack role or CSRF | Principal, authorities, `CsrfFilter`, `AccessDeniedHandler` |
| API returns 200 yet UI redirects to login | May be frontend state/route guard | Which request failed and which component redirected |
| First login works, page refresh loses login | Persistence/session cookie/token storage or frontend hydration | Network tab, cookie jar, session repository |
| Only one node/tenant fails | Session sharing/filter matcher/proxy or tenant scope | Node, host, context path, cookie, chain |

**Do not start by disabling CSRF, creating sessions manually, or turning every route into `permitAll()`.** Those actions mask symptoms and open vulnerabilities. First identify **which request failed**, the actual HTTP code, and where `Authentication` is restored.

## 2. Mental Model: Authentication in Request A Does Not Automatically Carry Over to Request B

A standard stateful login:

~~~text
Browser                        Spring Security Servlet
   |                                      |
   |-- POST /login + credentials -------->|
   |                                      | AuthenticationManager verifies
   |                                      | SecurityContext holds Authentication
   |                                      | SAVE to SecurityContextRepository
   |<-- 302 /dashboard + Set-Cookie ------|
   |                                      |
   |-- GET /dashboard + Cookie ---------->|
   |                                      | LOAD SecurityContext from repository
   |                                      | Authorization checks privileges
   |<-- 200 protected page ---------------|
   |                                      |
~~~

A standard stateless login:

~~~text
Client -> POST /token + credentials
Server -> token issued after verification

Client -> GET /api/me
          Authorization: Bearer <access-token>
Server -> verifies token EVERY REQUEST and builds Authentication

Client -> GET /api/me without Bearer
Server -> 401 is expected behavior
~~~

**Do not mix the two contracts.** If you choose `SessionCreationPolicy.STATELESS` for an API, subsequent requests not remembering the user is expected; clients must send credentials/tokens on every call. If you choose session-based form login, clients must retain the session cookie and the server must save context.

## 3. Servlet Lifecycle and `SecurityContextHolderFilter`

In Spring Security 6.x and modern versions, `SecurityContextHolderFilter` reads context from `SecurityContextRepository` into `SecurityContextHolder` at the start of a request by default. Once the filter chain completes, the holder is cleared from the thread:

~~~text
Request B
  -> SecurityContextHolderFilter
     -> repository.loadDeferredContext(request)
     -> SecurityContextHolder holds Authentication if present
  -> authentication/authorization filters
  -> controller
  -> SecurityContextHolder is cleared on completion
~~~

**Key point:** `SecurityContextHolderFilter` **does not automatically save modified context** at the end of a request. If you build login manually in a controller or filter, calling only:

~~~java
SecurityContextHolder.getContext().setAuthentication(authentication);
~~~

may let request A see the user, while **request B has nothing to reload**. In Spring Security 6 with explicit-save semantics, you must call `SecurityContextRepository.saveContext(...)` if you want session persistence.

Spring Security documentation distinguishes:

- `SecurityContextPersistenceFilter` in older configurations could auto-save context when the request finished/response committed.
- `SecurityContextHolderFilter` (default in Spring Security 6+) is **read-only**, requiring explicit save when persistence is needed.
- Built-in Spring Security authentication filters already include the context-saving logic required for their mechanisms; explicit-save bugs stand out in custom/manual authentication.
- When using Spring Security 7 or alternative configs, read the actual chain and version-specific API rather than relying on memory from older Spring Security releases.

**Never propose "disabling `SecurityContextHolderFilter`" to keep users logged in**; this filter clears ThreadLocal so Alice's identity never leaks into Bob's request when the container reuses threads.

## 4. Distinguishing "Context Exists in Request A" From "Context Was Saved"

Three states must be verified separately:

| State | Check | Meaning |
| --- | --- | --- |
| `Authentication` verified by provider | `authenticationManager.authenticate(...)` returns valid `Authentication` | Credentials/policy passed verification |
| Context set for current request | `SecurityContextHolder.setContext(context)` | Logic in the same request can read the principal |
| Context saved for later requests to load | `securityContextRepository.saveContext(context, req, resp)` | Session repository holds a record linked to the client |

**Writing to the holder != writing to the session.** Likewise, calling `saveContext` does not guarantee request B is authenticated if the cookie is not sent back, the session expired, or request B uses a different repository/filter chain.

A root-cause flow:

~~~text
Did Login A really authenticate?
  |
  +-- NO --> fix AuthenticationManager/provider/flow
  |
  +-- YES
       |
       v
Was context saved to repository?
  |
  +-- NO --> explicit save or use standard auth filter
  |
  +-- YES
       |
       v
Did browser receive and send back cookie / token?
  |
  +-- NO --> inspect Set-Cookie, credentials, Domain/Path/SameSite/Secure
  |
  +-- YES
       |
       v
Did Request B reach the right service/chain and repository?
  |
  +-- NO --> chain/proxy/session store configuration
  |
  +-- YES
       |
       v
Was Authentication loaded yet rejected?
  |
  +-- YES --> authorization/CSRF/role/tenant, not lost login
  |
  +-- NO --> check session invalidation, expiry, repository load
~~~

This is a diagnostic sequence, **not** an algorithm replacing Spring Security's security checks.

## 5. Inspect Real HTTP Traffic Before Editing Code

Open Browser DevTools → Network and compare request A (login) with request B (protected resource). In a test environment, record **non-sensitive metadata**:

- URL, method, status code, redirect chain, and `Location`;
- Does the login response include `Set-Cookie`? Cookie name (usually `JSESSIONID`, or `SESSION` with Spring Session), `Domain`/`Path`/`SameSite`/`Secure`/`HttpOnly`;
- Did the browser store the cookie in the right cookie jar or flag it as blocked? Why?
- Does request B carry a `Cookie` header for the right host/path?
- If the API uses Bearer, does request B carry an `Authorization` header?
- Do login and request B share the same scheme (HTTPS), origin, base path, and environment?
- Is response B 401, 403, 302, or 200 followed by a frontend redirect?

**Only inspect presence, cookie names, and attributes; never put session cookie values, passwords, access tokens, or raw `Authorization` headers into logs/tickets.**

Quick conclusion table:

| Login Response | Request B | Priority Diagnosis |
| --- | --- | --- |
| 302, no session cookie and server has no session | Likely unsaved / stateless session policy |
| 302, `Set-Cookie` present yet B omits `Cookie` | Browser/proxy cookie policy |
| 302, B sends cookie yet server finds no session | Session store/expiry/lifecycle/cluster |
| 302, session exists yet `Authentication` is null | Repository did not save, wrong repository, or cleared before save |
| 302, valid `Authentication` yet 403 | Authorization or CSRF, not lost context |
| 302, Auth OK on domain A yet request B goes to domain B | Cookie `Domain`/`Path`/`SameSite`/CORS or architecture |
| API token response 200, request B lacks Bearer | Client omits token in stateless flow |
| OIDC/SAML login redirected, state/session error | Callback cookie, state correlation, proxy host, or incomplete flow |

## 6. Custom Login Forgetting `saveContext`: A Very Common Bug

**Wrong** example in a custom login handler:

~~~java
// Code excerpt only; authentication is verified by manager first.
Authentication authentication =
        authenticationManager.authenticate(loginToken);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);

// Missing repository.saveContext(...)
// Current request sees the user; subsequent requests may be anonymous.
response.sendRedirect("/account");
~~~

Fixed following the Spring Security 6+ model:

~~~java
// Snippet inside a Servlet login controller/filter, not standalone main.
Authentication loginToken =
        UsernamePasswordAuthenticationToken.unauthenticated(
                submittedUsername, submittedPassword);

// Never build authenticated=true tokens directly from client data.
Authentication verified =
        authenticationManager.authenticate(loginToken);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);

// Use the exact repository used by the matching SecurityFilterChain.
securityContextRepository.saveContext(context, request, response);

// Redirect or commit the response ONLY AFTER saving succeeds.
response.sendRedirect(request.getContextPath() + "/account");
~~~

**Especially important:** this snippet assumes `submittedUsername`, `submittedPassword`, `authenticationManager`, `securityContextRepository`, `request`, and `response` are provided by a properly configured Servlet component. It is a **framework snippet**, not compilable/runnable with plain `javac` alone.

In custom logins, calling `AuthenticationManager.authenticate()` and saving context **does not automatically replace** the full session lifecycle managed by standard login filters. Also check:

1. Is `SessionAuthenticationStrategy` called properly to handle session fixation/concurrency policy (if the custom flow owns it)?
2. Does the session ID rotate properly after login?
3. Is context saved to the repository of the chain handling request B?
4. Does saving happen before redirect/response commit?
5. Are account status/authorities accurate, without turning a client-supplied username into an "authenticated" `Authentication` directly?
6. Are credentials kept out of HTTP responses and logs?

**Prefer standard Spring Security authentication filters/flows** whenever possible. A custom login endpoint can miss session fixation protection, concurrent session control, saved requests, or failure handling if it only copies a few lines creating a context.

## 7. `SecurityContextRepository` Must Match the Purpose

Common repositories in Spring Security Servlet:

| Repository | Purpose | Consequence for Next Request |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Stores context in `HttpSession` | Requests with the same valid session can load `Authentication` |
| `RequestAttributeSecurityContextRepository` | Holds context within a single request/dispatch | Does not persist session login across requests |
| `DelegatingSecurityContextRepository` | Combines multiple repositories | Modern Spring Security defaults often combine request attributes + HTTP session |
| `NullSecurityContextRepository` | Does not persist auth for subsequent requests | Suitable for certain stateless mechanisms |

A common mistake:

~~~text
Custom login saves to RequestAttributeSecurityContextRepository
    -> redirect /dashboard starts a new HTTP request
    -> context from prior request is gone
    -> /dashboard is anonymous
~~~

If the app needs sessions, it must have a repository that saves to the session. If the app is intentionally stateless, do not switch to sessions just to make a "stay logged in" test pass.

When a custom controller injects `new HttpSessionSecurityContextRepository()` while the web chain uses `NullSecurityContextRepository` or a different custom repository, you can "save successfully" yet request B's chain **reads from the wrong place**. Configure **the same instance or storage contract** for the authentication component and `SecurityFilterChain`.

Example configuring a unified repository (Spring Security Servlet):

~~~java
@Bean
SecurityContextRepository securityContextRepository() {
    return new HttpSessionSecurityContextRepository();
}

@Bean
SecurityFilterChain webChain(
        HttpSecurity http,
        SecurityContextRepository securityContextRepository)
        throws Exception {

    return http
            .securityContext(context -> context
                    .securityContextRepository(securityContextRepository))
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/login", "/error").permitAll()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
~~~

The snippet above must reside in a `@Configuration` class with required imports and beans/services. It is **not a standalone runnable application**. In many apps, Spring Security's default repository is already right; **do not swap defaults just to "try"** without evidence of a repository mismatch.

## 8. `SessionCreationPolicy` Options Do Not Mean the Same Thing

Spring Security provides session policies:

| Policy | Practical Meaning | Symptom |
| --- | --- | --- |
| `ALWAYS` | Spring Security proactively creates a session | Usually keeps stateful context if repository supports it |
| `IF_REQUIRED` | Creates a session when needed | Fits most form-login apps |
| `NEVER` | Spring Security will not create a session to store auth, but may use an existing one | Not equivalent to `STATELESS` |
| `STATELESS` | Does not create or use HTTP sessions to obtain `SecurityContext` for auth | Next request must carry auth material |

Example of a Bearer-token API:

~~~java
@Bean
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                    .jwt(Customizer.withDefaults()))
            .build();
}
~~~

This is a **Spring Security Servlet configuration snippet**, requiring the resource-server dependency, properly configured `JwtDecoder`, `@Configuration`, and imports. It does not make form login on a separate chain stateless if matchers are cleanly separated. With a JWT resource server, clients must send `Authorization: Bearer ...` on every API request.

Remember:

- `STATELESS` typically pairs with `NullSecurityContextRepository` for auth persistence; do not expect request B to authenticate via a session cookie.
- `NEVER` can still use an existing session; `RequestCache` in some configurations can still create a session, so do not deduce exact behavior from the enum name alone.
- If `SessionCreationPolicy` is set on an overly broad chain, even form login may fail to save authentication as you expect.
- In a hybrid web + API app, draw a clear boundary between session-based browser routes and token-based API routes.

**Never change `STATELESS` → `ALWAYS` just to get rid of 401** if the original API contract relies on Bearer tokens; that alters the security architecture and can increase CSRF/session fixation risks.

## 9. Missing Cookie: `Domain`, `Path`, `Secure`, `SameSite`, and Browsers

A stateful session works only when the browser **stores and sends back the right session identifier**. Cookie attributes to check in DevTools:

| Attribute | Possible Failure |
| --- | --- |
| `Domain` | Cookie scoped to host A, request B goes to host B |
| `Path` | Cookie issued under `/auth`, yet request B hits `/app` |
| `Secure` | Cookie is not sent over HTTP; requires HTTPS |
| `HttpOnly` | JavaScript cannot read the cookie; **this is a security control, not a bug** |
| `SameSite=Lax/Strict/None` | Affects sending cookies in cross-site contexts |
| `Expires/Max-Age` | Cookie expired or was evicted by the browser |
| Session cookie without `Expires` | May end with the browser session depending on browser policy |
| Cookie name `JSESSIONID` vs `SESSION` | Different app/server session stores |

**Never disable `HttpOnly` so JavaScript can "see the cookie".** HTTP-only session cookies are still sent automatically by the browser on matching requests; JS does not need to read them.

For same-origin web apps, `SameSite=Lax` or stricter is usually sufficient. For **genuinely cross-site cookies**, you may need `SameSite=None; Secure`, HTTPS, and CORS credentials; however, browsers can still block **third-party cookies**. Never apply `SameSite=None` to every cookie without evaluating threat models and CSRF.

**Cross-origin differs from cross-site:** `https://app.example.org` and `https://api.example.org` are **cross-origin**, yet can be **same-site** under schemeful site/eTLD+1 rules. CORS still applies to cross-origin `fetch`, while `SameSite` classifies differently. Test in practice rather than assuming "different subdomain = `SameSite=None`".

## 10. SPA/`fetch`: Credentials and CORS

With a frontend at `https://app.example.org` calling backend `https://api.example.org`, `fetch()` defaults to `credentials: "same-origin"`. Because the origins differ, the browser will not send cross-origin cookies unless the client asks for it.

Example:

~~~javascript
const response = await fetch("https://api.example.org/account/me", {
    method: "GET",
    credentials: "include"
});
if (!response.ok) {
    throw new Error("Request failed");
}
const me = await response.json();
~~~

Login requests from an SPA also need `credentials: "include"` when using cross-origin cookies; otherwise the browser may ignore `Set-Cookie`. Even when the login request returns 200, confirm the cookie was actually stored and sent on the next request.

Server CORS for credentialed requests must:

- Return `Access-Control-Allow-Credentials: true` where appropriate.
- Allow only **specific approved origins**, never `*` with credentials.
- Allow only required methods/headers.
- Handle `OPTIONS` preflight before security authentication logic, because preflights usually **carry no cookies**.
- Keep CSRF policy intact for session cookies; CORS does not replace CSRF.

Example Spring Security 6.x Servlet configuration:

~~~java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://app.example.org"));
    config.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
    config.setAllowedHeaders(
            List.of("Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"));
    config.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", config);
    return source;
}

@Bean
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http.cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .build();
}
~~~

This is a **configuration snippet**, not a complete application; it needs imports (`java.util.List`, Spring Web CORS types, Spring Security) and route/login settings. When an app has multiple `SecurityFilterChain`s or `CorsConfigurationSource`s, check which bean/source the chain uses. Never configure allowed origins blindly by echoing the client-sent `Origin` header.

**CORS errors can mask auth errors.** The browser reports "blocked by CORS", while on the network `OPTIONS` returned 401 or a 302 redirect to `/login` was blocked. Inspect status codes and headers on both preflight and main requests instead of rushing to change password encoders.

## 11. CSRF 403 Differs From Unauthenticated

In a session-based web app, `POST /login` and state-changing POSTs may undergo CSRF protection. Situations:

- `GET /me` without a cookie → 401/302 because unauthenticated.
- `POST /orders` with a cookie but no valid CSRF token → 403 **even though the session is still authenticated**.
- Cross-origin `fetch` missing the CSRF header → 403, easily mistaken by the frontend for "session lost".
- Endpoint requiring `ADMIN` role → 403 due to authorization, not cookies.

**Never disable CSRF globally to eliminate 403.** Check whether the form/SPA receives and sends the token properly with cookie-based auth, whether session ID rotation invalidated an old token, and whether the request hit the right chain.

For stateless Bearer-token APIs that do not use session cookies, CSRF policy may differ; decide based on the client model rather than simply assuming "REST APIs are safe so disable it".

## 12. Different Filter Chains: Login via Chain A, Resource via Chain B

An app with multiple `SecurityFilterChain`s may attach different policies:

~~~text
Chain 1: securityMatcher("/api/**")
         STATELESS + JWT resource server

Chain 2: securityMatcher("/**") or fallback
         Session-based formLogin()
~~~

If the login response came from the session-based chain, yet request B is `/api/me` on the stateless chain, the session cookie **may have no effect** on the API route. The issue is not that the user was randomly dropped, but that the two chains have different identity models.

In Spring Security, `@Order` and `securityMatcher` determine which chain matches a request; usually specific chains must precede catch-all chains. An overly broad matcher can "swallow" requests intended for another chain.

Cases to check:

| Mismatch | Consequence |
| --- | --- |
| `/api/**` uses `STATELESS` while UI sends cookie | API requests remain unauthenticated |
| Login route `/login` is not inside the form-login chain | Form-login filter does not handle POST as expected |
| `securityMatcher` accidentally excludes `/oauth2/**` callback | OIDC callback misses the right filter |
| `web.ignoring()` applied to a protected endpoint | Security filters do not run |
| Custom filter added twice or in wrong order | Context is set/cleared incorrectly |
| Custom `AuthenticationSuccessHandler` redirects before saving | Next request loses auth |
| Two different repositories in chains A and B | Save succeeds, yet B loads from the wrong store |

Enable controlled logging to see which chain `FilterChainProxy` selects and which filters run, while **never dumping credentials/headers/bodies**. Verify route/matcher config at runtime rather than guessing from config method names.

## 13. Proxies, HTTPS Termination, and Load Balancers

When deployed behind ingress, Nginx, an API gateway, or a load balancer:

~~~text
Browser -> https://app.example.org
            |
            v
         Reverse proxy (TLS termination)
            |
            v
         http://service:8080
~~~

The backend may see a different scheme/host/path than the public URL. This affects `Secure` cookies, redirect URLs, callback URLs, context paths, and session stickiness.

Check:

1. Are public `Host`, forwarded scheme, and path configured properly?
2. Does the proxy strip/overwrite `Forwarded`, `X-Forwarded-Proto`, and `X-Forwarded-Host` coming from the Internet?
3. Does the backend trust forwarded headers only from trusted proxies?
4. Does response `Set-Cookie` have `Domain`/`Path`/`Secure`/`SameSite` matching the public deployment?
5. Do sessions live on a single node or a shared store?
6. Do requests A and B reach the same app deployment/namespace with matching session serializers and signing/encryption keys?
7. Does the proxy strip cookie headers or alter paths during URL rewriting?

**Never trust arbitrary `X-Forwarded-*` headers to "fix login".** If browsers control those headers, attackers can cause host spoofing, open/wrong-domain redirects, or corrupted audit logs.

### Multi-Node Clusters

Suppose:

~~~text
Login A -> node-1 -> local HttpSession holds SecurityContext
GET B   -> node-2 -> lacks that HttpSession
            -> unauthenticated
~~~

The production solution is a **shared session store** (e.g., Spring Session with Redis/database per policy) or well-understood sticky-session infrastructure with a failover plan. Sticky sessions only mask some issues and do not replace durable session lifecycles when HA is required.

Verify all nodes use the same cookie/session naming, serialization/security context model, version, and tenancy. With Spring Session and the `SESSION` cookie, do not mistake the name difference from `JSESSIONID` for an error.

## 14. Session Fixation, Expiry, Logout, and Concurrent Session Control

Spring Security typically rotates the session identifier upon successful authentication to protect against **session fixation**. Thus:

~~~text
Before login: JSESSIONID=old-session
After login:  JSESSIONID=new-session
~~~

This can be **expected** behavior. If a test client/cURL/SPA accidentally keeps sending the old cookie, the next request will lack the new session's context. Inspect the **final** cookie after redirects and confirm the browser accepts the new `Set-Cookie`.

Other causes:

- Session timeout too short or clock/TTL skew.
- User logged out in another tab, invalidating the session.
- A second login triggered `maximumSessions`/expired-session policy, invalidating the first session.
- Redis session store restarted/evicted/lost data.
- Custom logout handler or success handler cleared the session/context after login.
- Session attribute overwritten with an empty context by a filter/custom code.
- App switched domain/tenant, creating a separate unrelated session.

If using Spring Security concurrent-session support, inspect `SessionRegistry`/session event listeners or actual Spring Session settings. A request rejected by expired-session policy does not mean password verification just failed.

**Clearing `SecurityContextHolder` at the end of a request is right, while logout must delete or invalidate state in the repository/session.** Never call `clearContext()` alone and assume the browser is logged out, and never delay cleanup to keep users "still logged in".

## 15. OAuth2/OIDC and SAML: Callback Redirect Does Not Mean Session Persisted

With `oauth2Login()` or `saml2Login()`, the flow involves multiple redirects, state correlation, and callback endpoints. Points to verify:

- Does the browser preserve the session/correlation cookie across the IdP redirect/callback?
- Does the HTTP callback arrive at the right public origin/path and the right Spring Security filter chain?
- Do origin/`SameSite`/cookie rules cause the callback to arrive without a session so state/nonce is lost?
- Did provider login succeed while the RP application failed to finish authentication, invoke the success handler, and save context?
- Did a custom success handler redirect too early, log out/invalidate the session, or create the wrong new context?
- Does request B hit the web session chain or a stateless API chain requiring Bearer?

A flow can look like "IdP login success" in the provider's logs while the RP callback fails on state/issuer/audience/signature/metadata. In that case **the RP does not have a valid `Authentication` yet**; never try to save a session from unverified IdP data.

In OAuth2/OIDC, `redirect_uri` is the protocol callback, whereas the post-login target is an application route. Never arbitrarily use `next` as the callback or copy tokens into URLs to avoid losing context.

With SAML, `SAMLResponse`/`RelayState` handling must pass verification before creating `Authentication`. Never fix failed callbacks by disabling signature/origin/issuer/audience checks.

## 16. Difference Between `SecurityContext` and Frontend Auth State

An SPA might display "Login succeeded" simply because:

~~~javascript
if (loginResponse.status === 200) {
    uiState.loggedIn = true;
}
~~~

Yet the backend may not have persisted auth or tokens. A frontend route guard can also wipe auth state on page refresh because state lived in memory even though the backend cookie/session still exists.

Test independently:

1. Browser performs a real login.
2. Send `GET /me` from **the same browser with the same cookie/token**.
3. If backend returns the right user while UI still shows the login screen → frontend state/hydration/router issue.
4. If backend returns 401/302 → investigate cookie/repository/chain/auth material.
5. If backend returns 403 → check authorization/CSRF.

Never store passwords or access tokens in `localStorage` just to "survive page refresh" without evaluating XSS/CSRF threat models. Choose cookie-based sessions or token-based client storage per architecture and policy.

## 17. ThreadLocal Cleanup and Async Propagation

`SecurityContextHolder` in Servlet usually stores context per thread. Request B does not necessarily run on request A's thread, and even if it shares a thread, the framework **must clear it** so principals never leak.

With `@Async`, executors, or `CompletableFuture`:

~~~text
Request thread: SecurityContext = Alice
       |
       +--> executor worker thread
               |
               +--> SecurityContext usually DOES NOT automatically contain Alice
~~~

Do not confuse "async task does not see principal" with "request B lost the session". Those are two separate boundaries. Spring Security supports `DelegatingSecurityContextRunnable/Callable/Executor` to propagate context with cleanup. Never use `MODE_INHERITABLETHREADLOCAL` as a blanket fix for thread pools, because reused worker threads can retain stale identities.

An async callback reading `SecurityContext` on another thread and seeing null does not prove the session failed to save; to test persistence, send a **new HTTP request** with the matching cookie/token.

## 18. Standalone Java 17+: Modeling Why Sessions Must Be Saved

Create **LoginPersistenceBoundaryDemo.java**. It models a per-thread holder and a session store using Java Collections, without Spring Security. This is an **educational model**, not a credential verifier, and does not replace `SecurityContextRepository` or a real HTTP session store.

~~~java
import java.util.HashMap;
import java.util.Map;

public class LoginPersistenceBoundaryDemo {

    private final Map<String, String> sessionStore = new HashMap<>();
    private final ThreadLocal<String> currentPrincipal = new ThreadLocal<>();

    void login(String sessionId, String principal, boolean save) {
        try {
            // Assumes principal was already verified elsewhere.
            currentPrincipal.set(principal);
            System.out.println("Login handler = " + currentPrincipal.get());

            if (save) {
                sessionStore.put(sessionId, principal);
            }
        } finally {
            currentPrincipal.remove();
        }
    }

    String nextRequest(String sessionId) {
        try {
            String saved = sessionStore.get(sessionId);
            if (saved != null) {
                currentPrincipal.set(saved);
            }

            String principal = currentPrincipal.get();
            return principal == null ? "anonymous" : principal;
        } finally {
            currentPrincipal.remove();
        }
    }

    void logout(String sessionId) {
        sessionStore.remove(sessionId);
    }

    public static void main(String[] args) {
        LoginPersistenceBoundaryDemo demo =
                new LoginPersistenceBoundaryDemo();

        demo.login("not-saved", "alice", false);
        System.out.println("Without save = "
                + demo.nextRequest("not-saved"));

        demo.login("saved-session", "alice", true);
        System.out.println("With same session = "
                + demo.nextRequest("saved-session"));
        System.out.println("With other session = "
                + demo.nextRequest("different-session"));

        demo.logout("saved-session");
        System.out.println("After logout = "
                + demo.nextRequest("saved-session"));

        System.out.println("Thread context clear = "
                + (demo.currentPrincipal.get() == null));
    }
}
~~~

Compile and run:

~~~bash
javac LoginPersistenceBoundaryDemo.java
java LoginPersistenceBoundaryDemo
~~~

Exact stdout:

~~~text
Login handler = alice
Without save = anonymous
Login handler = alice
With same session = alice
With other session = anonymous
After logout = anonymous
Thread context clear = true
~~~

Interpretation:

- `login("not-saved", ...)` sets the principal properly during request A, yet does not save ⇒ new request is anonymous.
- `login("saved-session", ...)` saves to the session store ⇒ requests carrying the same session ID read Alice.
- A different session cannot obtain Alice.
- Logout removes the session record ⇒ subsequent request is anonymous.
- `finally` clears the current thread's ThreadLocal; that is right behavior and does not erase state saved in the repository.

**Never use this code in production.** It does not verify passwords, generate/validate secure cookies, encrypt sessions, enforce TTLs, synchronize across nodes, or use Spring Security. It merely helps distinguish **holder lifecycle** from **persistence lifecycle** in a runnable Java example.

## 19. MockMvc: Test Two Real Requests, Do Not Use `mockUser` to Mask Bugs

A testing trap:

~~~java
mvc.perform(get("/private").with(user("alice")))
        .andExpect(status().isOk());
~~~

The `with(user("alice"))` `RequestPostProcessor` **injects an `Authentication` for that request**. It does not prove form login saved the context. Class-level `@WithMockUser` can similarly mask the bug if every request gets a mock user automatically.

To test persistence properly:

1. Send a real login POST through the Spring Security filter chain.
2. Grab `MockHttpSession` from the **login result**.
3. Send a protected GET with **that exact session**, without `with(user(...))`.
4. Send another GET without a session; it must be anonymous/unauthorized.
5. Optionally add logout and verify the old session no longer grants access.

Example instructional test class for a Spring Boot app with form login, test user `"alice"`/`"correct-password"`, and protected `/private` endpoint:

~~~java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

@SpringBootTest
@AutoConfigureMockMvc
class LoginPersistsSecurityContextTest {

    @Autowired MockMvc mvc;

    @Test
    void secondRequestUsesSavedLoginSession() throws Exception {
        MvcResult login = mvc.perform(
                formLogin("/login")
                        .user("alice")
                        .password("correct-password"))
                .andExpect(authenticated().withUsername("alice"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/private").session(session))
                .andExpect(authenticated().withUsername("alice"));

        mvc.perform(get("/private"))
                .andExpect(unauthenticated());
    }
}
~~~

This test **can compile/run inside a properly configured Spring Boot Servlet project** with Spring Security Test, JUnit 5, a user fixture, and a `SecurityFilterChain`. Adjust test setup for your Spring Boot version; imports follow common Spring Boot 3.x structure. It does not run standalone with `javac`.

**Note:** expecting a session is valid only if this is **stateful form login** and the app creates sessions. Do not use this test as criteria for stateless Bearer-token APIs. If `@WithMockUser` is placed on the whole test class, remove that annotation when testing real login persistence.

For custom JSON login, replace the first request with `post("/auth/login")` including the right CSRF token/content type and the same repository; never construct an authenticated fixture to call the "login succeeded" test green.

## 20. Real Browser or HTTP Client Testing

MockMvc does not fully test browser cookie policies, HTTPS proxies, domains, and `SameSite`. Therefore, after app tests pass, run E2E checks:

~~~text
1. Browser opens login page under the real public HTTPS hostname.
2. Log in with a valid test account.
3. Observe Set-Cookie response: was the session cookie received?
4. Inspect cookie storage: any block reason?
5. Refresh a protected page.
6. Check that the GET request carries the matching Cookie or Authorization.
7. Verify the backend principal on /me.
8. Log out; new requests with the old session must lose access.
9. Repeat across each critical gateway/node.
~~~

With `curl` for cookie-jar diagnostics, the rule is `-c cookie-jar` on the login request and `-b cookie-jar` on the next request. However, Spring Security form login usually requires a **CSRF token fetched from the form/cookie before POSTing**; do not run a `curl` command omitting the token and blame persistence for login failure. Use HTTPS and test accounts, guard the cookie jar like a secret, and delete it after testing.

In the browser, follow the full redirect chain; a final 200 response from the login page can hide a 302 from the protected page back to `/login`.

## 21. Diagnostic Logging Without Exposing Credentials

When diagnosing production, record only **allowed** fields:

| Log Field | Safe Example | Do Not Log |
| --- | --- | --- |
| `requestId`/`traceId` | Opaque generated identifier | Raw session ID |
| request path template | `GET /private` | Full URL containing tokens/query secrets |
| auth state | authenticated/anonymous | Password, JWT text |
| authentication type | Form/OIDC/Bearer | Raw `Authentication` object |
| repo state | loaded/missing/saved | Full serialized `SecurityContext` |
| selected chain | web/api chain label | Request headers containing secrets |
| session observed | exists/absent, cookie present/absent | `JSESSIONID`/`SESSION` value |
| denial category | CSRF / authorization / authentication | Exception messages containing PII |
| node identity | service instance label | Credentials/config secrets |

You can enable Spring Security loggers in test environments or during a controlled incident window, without dumping `Authorization`, `Cookie`, passwords, or session attributes.

**An `AUTH_SUCCESS` event does not prove session persistence.** Log auth verification outcome, repository save, response commit, request B repository load, and authorization outcome separately.

Correlation IDs help link A/B, though **two HTTP requests have two different request IDs**. To link a flow, use a separately protected opaque flow ID — never expose raw session IDs or usernames.

## 22. Symptom-Based Diagnostic Tree

| Symptom | Priority Check | Grounded Fix |
| --- | --- | --- |
| Login handler logs right principal, next request is null | `saveContext` and repository | Explicit save after `authenticate` |
| No session cookie in response | Session policy, response commit, login flow | Use session-aware flow or fix cookie config |
| Cookie set yet rejected by browser | `Secure`, `Domain`, `Path`, `SameSite`, third-party policy | Fix deployment/cookie attributes properly |
| SPA login 200 yet next API gets 401 | `credentials:"include"`, CORS, API chain | Send credentials properly or Bearer token |
| Preflight `OPTIONS` gets 401 | CORS handled after security | Integrate CORS before auth |
| Protected POST 403, GET on same session OK | CSRF | Fix CSRF token flow; do not disable blindly |
| Protected GET 403, valid `Authentication` | Role/authority/tenant | Fix authorization policy |
| Works locally, fails behind production load balancer | Session store/stickiness | Shared sessions, node consistency |
| Session ID changes after login | Session fixation rotation | Client uses new cookie rather than reusing old session |
| Page refresh on API loses auth | Frontend lost token/session or API is stateless | Check storage and Bearer per request |
| OIDC callback succeeds at IdP, RP stays logged out | State/session callback/filter | Check RP callback and cookie before save |
| Multiple `SecurityFilterChain`s | Matcher/order/repository mismatch | Check which chain handles A and B |
| Only one account fails | Status, authorities, concurrent session policy | Do not assume a general cookie bug |
| Request B unauthenticated yet A just succeeded | B may run before save/redirect finishes | Check races and response commit order |
| Session lost after logout in another tab | Expected session invalidation | Update frontend UX; do not "resurrect" session |

## 23. Regression Test Matrix

| Test | Expectation |
| --- | --- |
| Custom login valid credentials | Provider returns verified `Authentication` |
| Custom login invalid credentials | No authenticated context created/saved |
| Login session mode | `saveContext` runs before response commit |
| Request B same session | User has expected principal and authorities |
| Request B no session | Does not pick up A's user |
| Request B different session | Does not pick up A's user |
| `ContextHolder` cleared at end of request | No user leaks across threads/requests |
| Cookie `Secure`/`Path`/`Domain` | Browser sends on the right public routes |
| Cookie `SameSite` cross-site flow | Works per policy and browser support |
| SPA cross-origin `fetch` without credentials | 401/redirect per policy, not mistaken for outage |
| SPA `fetch` with `credentials: "include"` | Valid session cookie is sent |
| `OPTIONS` preflight | Not wrongly rejected by auth filter |
| Protected POST missing CSRF | 403 CSRF, must not be misdiagnosed as lost auth |
| Protected GET missing role | 403 authorization |
| `STATELESS` API request without Bearer | Expected 401 |
| `STATELESS` API request with valid Bearer | 200 with principal from token |
| Multi-chain web login vs API | Right chain and identity model |
| Proxy spoofed headers | Does not alter host/cookie/redirect outside policy |
| Request hits node-1 then node-2 | Shared session works |
| Session rotation after login | New cookie valid, old cookie does not grant access |
| Logout/session expiry | `Authentication` is not resurrected |
| OAuth2/SAML callback succeeds | RP `Authentication` completes with right session/token |
| MockMvc without `with(user(...))` on request B | Genuinely tests persistence |
| Login success event before save fails | Event is not treated as proof login persisted |

Test separately: **unit tests for custom auth components**, **MockMvc for filters/repositories**, **E2E browser tests for cookies/CORS**, and **integration under load balancers** for session sharing. A unit test calling only `SecurityContextHolder.getContext()` cannot replace E2E.

## 24. Anti-Patterns to Avoid

- Setting `SecurityContextHolder.setStrategyName(MODE_GLOBAL)` to "keep `Authentication`" across all requests: risks sharing principals across users.
- Enabling `MODE_INHERITABLETHREADLOCAL` to cure all async/pooled-thread problems: pooled threads can retain stale principals.
- Disabling `SecurityContextHolderFilter` or skipping context clearing so subsequent requests see the user: breaks isolation.
- Disabling `csrf()`/CORS or setting `anyRequest().permitAll()` to make HTTP 403 vanish.
- Calling `UsernamePasswordAuthenticationToken.authenticated(...)` directly from client-sent username/password, bypassing `AuthenticationManager`.
- Adding `HttpSession` into a `STATELESS` API without revisiting the threat model.
- Placing access tokens/refresh tokens/session IDs in URL query strings or application logs.
- Trusting arbitrary `X-Forwarded-*` headers from the Internet to construct cookies/redirects.
- Testing only one request with `@WithMockUser` and concluding the session persisted.
- Trying to let JavaScript read `HttpOnly` cookies.
- Setting `SameSite=None` or `allowCredentials=true` + wildcard origins without evaluating CSRF/cross-site threats.
- Reading raw `SecurityContext` from a session store and mutating shared objects across requests.
- Treating a login event, 302 redirect, or UI "success" as proof the user is authenticated across all routes.

**Security requires clean boundaries:** each request must receive its `Authentication` only from a verified session/token, never from accidental thread state.

## 25. First-10-Minutes Investigation Checklist

1. Did the real login request succeed through the Spring Security auth filter/manager?
2. Does request B return 401, 403, or 302? Is the browser stuck in a redirect loop?
3. Is the app expected to be **session-based** or **stateless Bearer**?
4. If session-based, was `Authentication` saved via `saveContext` into the right repository before commit?
5. Did the login response set `Set-Cookie`, and did the browser store and send the cookie back on B?
6. Did the session ID change due to session fixation protection?
7. Do cookie `Domain`/`Path`/`Secure`/`SameSite`, origins/CORS, and `fetch` credentials match?
8. Do the `SecurityFilterChain`s for A and B share the same identity contract/repository?
9. Do proxies/clusters/session stores route B to somewhere that can read the session?
10. Does request B have a valid `Authentication` yet get 403 due to authorities/CSRF?
11. Did the OAuth2/SAML callback complete RP authentication and state correlation?
12. Does the MockMvc test execute a second request with the same session **without mock users**?
13. Do logs keep cookies, tokens, passwords, and PII private?
14. After fixing the root cause, were logout/expiry/concurrent sessions tested and re-verified in a real browser?

**Conclusion:** "Login succeeds, yet subsequent requests are unauthenticated" must be diagnosed as a **saving and restoring state across request boundaries** problem, not assumed to be a wrong password or Spring Security "accidentally deleting the user". In stateful Servlet apps, authenticate → create `SecurityContext` → **save to `SecurityContextRepository`** → browser keeps/sends cookie → new request loads context. In stateless APIs, the client must send a Bearer token every time. If both session and principal are right yet you still get 403, investigate authorization or CSRF. Guarding these boundaries fixes the bug without sacrificing user isolation.

### Official References

- Spring Security — Authentication Persistence: https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html
- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Form Login: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html
- Spring Security — CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — Servlet CORS: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security — Multiple SecurityFilterChains: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — MockMvc Authentication Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html
- Spring Security — MockMvc RequestPostProcessors: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/request-post-processors.html
- Spring Session — HTTP Session with Redis: https://docs.spring.io/spring-session/reference/guides/boot-redis.html
- MDN — Request credentials mode: https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials
- MDN — Set-Cookie header: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie
