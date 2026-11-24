# 401, 403, and Login Redirects Across Application Types

> **Context:** Spring Security 6 on the **Servlet stack**, Java 17+, Spring Boot 3.x. Topic belongs to **Error Responses**: when to return **401 Unauthorized**, **403 Forbidden**, when to send a **302 Redirect to the login page**, why the same unauthenticated user may see different behavior across a traditional web application, an HTTP Basic API, an OAuth2 Resource Server/Bearer API, and an SPA. Explains the roles of `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, `AccessDeniedHandler`, `SecurityContext`, CSRF, and multiple `SecurityFilterChain`s. Includes a runnable Spring Boot example with two endpoint styles, MockMvc allow/deny tests, and a practical error-handling scenarios set.

## 1. Decision Map: Three Response Types, Three Meanings

You cannot deduce solely from the phrase "the user has no permission" that the server must always return 403. First, determine **whether the user already has valid authentication**, **whether the application talks to a browser or an API client**, and **which authentication entry point** is configured.

| Scenario | Form-login/session web | HTTP Basic API | OAuth2 Resource Server using Bearer |
| --- | --- | --- | --- |
| Not logged in, calling protected endpoint | Typically **302** to `/login` | **401**, `WWW-Authenticate: Basic ...` header | **401**, `WWW-Authenticate: Bearer ...` header |
| Wrong credentials or invalid token | Form login fails, typically **302** to `/login?error` | **401** with Basic challenge | **401** with Bearer challenge and appropriate error |
| Authenticated but lacking authority/role/scope | Typically **403** | Typically **403** | Typically **403**; may include Bearer `insufficient_scope` |
| Browser POST missing CSRF token | Typically **403**; details depend on chain/context | Can be **403** when CSRF is enabled | For pure stateless bearer APIs, CSRF is typically evaluated separately and disabled only within appropriate scope |
| Non-existent URL on a protected path | May redirect to login **before** MVC returns 404 | May return **401** before MVC returns 404 | May return **401** before MVC returns 404 |
| Authenticated, non-existent URL allowed past chain | MVC typically returns **404** | MVC typically returns **404** | MVC typically returns **404** |

**Rule of thumb:** **401 = valid authentication required**, **403 = request denied access**, **302 to login = a browser UX to initiate authentication**, not a REST API authorization error code. Actual HTTP statuses depend on the exception, entry point, handler, and configuration.

Note that the historical name `401 Unauthorized` can mislead: its HTTP meaning is *unauthenticated or invalid authentication*. `403 Forbidden` generally means the server understood the request yet refuses authorization, though HTTP does not restrict it strictly to authenticated users; in Spring Security, default branching also depends on anonymous/remember-me recognition and exception handling.

## 2. HTTP 401: Authentication Challenge, Not Every Error Is 401

In HTTP semantics, `401 Unauthorized` indicates the request lacks valid authentication for the requested resource. The server should supply an authentication challenge in the `WWW-Authenticate` header when using HTTP authentication schemes.

HTTP Basic example:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
```

The client understands it must send credentials matching the Basic scheme, such as `Authorization: Basic ...`. The Base64 string of Basic credentials is **not secure encryption**: production must use HTTPS.

OAuth2 Bearer example when token is missing:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

Invalid token example, if the Authorization Server/Resource Server publishes errors per RFC 6750:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token",
                  error_description="The access token expired"
```

These are **illustrative samples**. How `realm`, `error_description`, and headers are set depends on configuration; not every 401 contains this exact text. **Never** use error descriptions to leak raw tokens, user existence, signing keys, or internal metadata.

### 2.1. When Is a Request Unauthenticated?

- No valid session/cookie and the endpoint requires authentication.
- Missing `Authorization` header when the API requires Basic/Bearer.
- Wrong Basic username/password, or rejected credentials.
- Expired Bearer token, invalid signature, wrong issuer/audience, revoked by policy, or rejected by the resource server.
- No prior authentication or it fails an entry point's requirements.

Not every token check failure is due to a **missing scope**. A token can be valid for authentication yet lack the scope for the resource; that case is typically **403** rather than 401 once the resource server has established an `Authentication`.

### 2.2. 401 and Expired Sessions

An SPA calling `fetch("/api/me")` can receive 401 when the session expires if the backend API entry point is configured for 401. However, a default form-login app may return 302 to `/login`; browser `fetch` follows the redirect and receives an HTML login page, tricking code expecting a valid JSON response.

Therefore, do not inspect only the final status in JavaScript. Check the **initial status**, `Location`, `Content-Type`, and any redirects performed by `fetch`/the browser.

### 2.3. Do Not Use 401 for Normal Business Errors

Input validation errors should return 400/422 per the API contract; resource not found is typically 404; state conflicts may be 409. Just because a request runs inside a secured system does not mean every application error is 401/403.

## 3. HTTP 403: Denied, Not a Reason to Force Repeated Re-Login

`403 Forbidden` is typically used when the request has been identified yet **fails policy**:

- User has `ROLE_USER` while the endpoint requires `ROLE_ADMIN`.
- Valid Bearer token lacking the `orders:write` scope.
- Logged in, yet not belonging to the tenant owning the resource.
- User is not the document owner, or clearance is below classification.
- Method security `@PreAuthorize` denies and the exception is translated to 403 at the web layer.
- `POST`/`PUT`/`DELETE` request blocked by CSRF protection, depending on the flow and entry point.

Web/API example after authentication:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "Access denied"
}
```

This is a **suggested JSON body for an API**, not necessarily what Spring Security returns by default. Default responses may be empty, an HTML error page, or a custom schema.

### 3.1. 403 Does Not Identify Its Root Cause by Itself

A `POST /api/orders` receiving 403 can originate from:

1. Missing/invalid CSRF token; the request is blocked **before** role authorization logic runs.
2. User has authentication yet lacks `ORDER_WRITE` authority.
3. User has the role yet accesses the wrong tenant (ABAC).
4. A custom handler returns 403 itself.
5. CORS/preflight or a reverse proxy blocks the request before the app, potentially yielding a different status.

When testing roles, **provide a valid CSRF token if CSRF is enabled** before concluding a 403 is due to missing permissions. Never disable CSRF just to make an authorization test return 200.

### 3.2. Should 403 Redirect to Login?

Normally, a user who is **authenticated yet lacks permissions** should see 403/a permission page rather than being pulled into a re-login loop. Redirecting every `AccessDeniedException` to `/login` can create an endless loop: login succeeds -> visit admin page -> missing role -> redirect to login -> re-login still lacks role.

Web UX can show a page explaining "You do not have permission to access this", while distinguishing **not logged in** from **not permitted**, and ensuring the error page leaks no sensitive information.

## 4. 302 Redirect: A UI Choice, Not Successful Authorization

For a browser-based web app, `LoginUrlAuthenticationEntryPoint` normally uses a redirect:

```http
HTTP/1.1 302 Found
Location: /login
```

The browser then requests `GET /login` to display the login page. After the user submits the login form successfully, the request cache/success handler can return the user to the previously requested resource.

```text
Browser: GET /web/me (no session yet)
       |
       v
Authorization requires authenticated()
       |
       v
AuthenticationEntryPoint: 302 Location /login
       |
       v
Browser GET /login -> form page
       |
       v
POST /login + CSRF token + credentials
       |
       +--> success: authentication + session + redirect per success handler
       +--> failure: typically redirect /login?error
```

**A 302 redirect does not mean the user has permission.** It is merely a step in the flow requesting authentication. If the user logs in successfully yet lacks permission for the original page, the subsequent request upon returning can receive 403.

### 4.1. Redirects Must Suit the Client Type

For a browser navigating HTML pages, a 302 login redirect is natural. For mobile apps, SPAs calling JSON APIs, background jobs, or service-to-service clients, redirecting to an HTML login page is normally **inappropriate**:

- An API client may follow the redirect automatically and receive 200 containing HTML instead of JSON.
- A mobile app does not know which web form to open.
- A client using Bearer tokens cannot resolve the error via the server's login form.
- CORS can block redirect responses pointing to an IdP on another domain.
- Monitoring may mistake the login page's 200 for API success.

Configure entry points matching each `SecurityFilterChain` and URL/API contract.

### 4.2. Saved Request and Post-Login Redirect

Spring Security has a `RequestCache` mechanism to store an unauthenticated request before redirecting to login. Upon successful login, `SavedRequestAwareAuthenticationSuccessHandler` can route the browser back to the prior URL.

Never trust an arbitrary user-supplied `redirect` URL for post-login navigation. Open redirects can be abused for phishing and state leaks. When supporting a custom return URL, allowlist internal paths, validate scheme/host, and avoid passing tokens in query strings.

### 4.3. The Login Page Must Be Accessible

If `/login` is also protected by a policy requiring authentication without an appropriate exception, users can hit a redirect loop. With Spring Security's generated login form, use `formLogin(form -> form.permitAll())`, or explicitly permit both the login page and login processing endpoint when customized.

Also permit static assets for the login page narrowly, without bypassing security headers/filters unnecessarily.

## 5. Where Does Spring Security Decide 401, 403, or Login Redirect?

Key components on the Servlet stack:

- `SecurityContextHolder`: holds the current `Authentication`.
- `AnonymousAuthenticationFilter`: may create an `AnonymousAuthenticationToken` when no other authentication exists.
- `AuthorizationFilter`: enforces `authorizeHttpRequests` rules.
- `ExceptionTranslationFilter`: bridges exceptions from the security chain to appropriate HTTP responses.
- `AuthenticationEntryPoint`: initiates the authentication challenge/redirect when needed.
- `AccessDeniedHandler`: handles access denials per response policy.
- `AuthenticationTrustResolver`: distinguishes anonymous and remember-me/full authentication when choosing how to respond.
- `RequestCache` and `SavedRequestAwareAuthenticationSuccessHandler`: help browsers return to the pre-login page when appropriate.

```text
HTTP request
    |
    v
Authentication filters (session/form/basic/bearer...)
    |
    v
SecurityContext / Authentication
    |
    v
ExceptionTranslationFilter
    |
    v
AuthorizationFilter + authorization rule
    |
    +--> ALLOW -> Controller/Service
    |
    +--> DENY -> AccessDeniedException
                   |
                   +--> anonymous/insufficiently authenticated?
                   |       |
                   |       +--> AuthenticationEntryPoint
                   |                |
                   |                +--> web form: 302 /login
                   |                +--> Basic API: 401 + WWW-Authenticate
                   |                +--> Bearer: 401 + WWW-Authenticate
                   |
                   +--> authenticated but insufficient permissions?
                           |
                           +--> AccessDeniedHandler
                                    |
                                    +--> typically 403
                                    +--> Bearer: may report insufficient_scope
```

**Important:** `AuthenticationException` is also handled to initiate authentication; credential errors can arise directly inside an authentication filter and be handled by the corresponding failure handler/entry point. The diagram above depicts the common authorization path—**it does not imply every exception originates at `AuthorizationFilter`**.

### 5.1. AuthenticationException vs. AccessDeniedException

`AuthenticationException` represents missing/failed authentication; `AuthenticationEntryPoint.commence(...)` handles initiating authentication when invoked. With form login, a login request with wrong credentials normally goes through `AuthenticationFailureHandler` to redirect to `/login?error`, rather than necessarily throwing straight to `ExceptionTranslationFilter`.

`AccessDeniedException` typically arises when an authorization rule denies access, yet `ExceptionTranslationFilter` can branch: if the principal is anonymous or below the required authentication level, it **initiates authentication via the entry point** instead of returning 403. If the principal is fully authenticated yet lacks the authority, it calls `AccessDeniedHandler`.

### 5.2. Remember-Me and fullyAuthenticated()

`RememberMeAuthenticationToken` differs from authentication immediately after a user enters credentials. A `fullyAuthenticated()` endpoint may reject remember-me. In that case, the entry point may be invoked so the user re-authenticates rather than treating remember-me as sufficient. Exact behavior depends on the trust resolver, handler, entry point, and remember-me configuration.

Do not rely solely on `authentication.isAuthenticated()` to judge "recently re-entered password", because remember-me authentication can still have `authenticated` state while carrying a lower trust level than full authentication.

### 5.3. When a Controller Throws an Exception

Spring MVC `@ControllerAdvice` handles exceptions at the controller/service layer under MVC mechanics, but **does not automatically handle all exceptions thrown inside Servlet security filters before the controller**. To make API security responses consistent, configure `AuthenticationEntryPoint` and `AccessDeniedHandler` in Spring Security, alongside dedicated MVC error handling where business logic requires it.

Do not merely write `@ExceptionHandler(AccessDeniedException.class)` and claim every filter-level 401/403 has been converted to JSON.

## 6. Form-Login Browser App: 302 When Anonymous, 403 When Missing Permissions

Traditional web app configuration normally uses sessions:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/", "/public").permitAll()
        .requestMatchers("/web/admin").hasRole("ADMIN")
        .anyRequest().authenticated());

http.formLogin(form -> form.permitAll());
```

This is a **configuration fragment**, not a standalone class.

If an anonymous user calls `GET /web/admin`, Spring Security may redirect to `/login` because anonymous access requires authentication. If logged in with role `USER` and calling `GET /web/admin`, the `hasRole("ADMIN")` policy denies it and the response is typically 403.

Same URL, yet **different principal states** yield different responses; that is by design.

### 6.1. Form Login with Wrong Credentials

The user submits `POST /login` with a wrong username/password. With default form login, the response typically redirects to `/login?error`. This is a **login-processing authentication failure**, distinct from an anonymous request hitting a protected endpoint (302 to `/login`).

Do not configure overly detailed messages like "Email exists but password is wrong", as that enables account enumeration. Protect against brute force with rate limiting, session fixation protection, secure cookie flags, and CSRF per your threat model.

### 6.2. Session Expiration and Redirects

When the `JSESSIONID` session expires, requests to protected web pages lose session authentication. Behavior can match anonymous access and redirect to login. However, if the app uses remember-me, `RememberMeAuthenticationFilter` may re-authenticate automatically from the persistent/long-lived cookie; thus not every expired session redirects to login.

To test "anonymous", do not reuse the same session or a valid remember-me cookie from a previous login.

### 6.3. 403 Page for Logged-In Users

A web app can customize:

```java
// Fragment inside HttpSecurity configuration:
http.exceptionHandling(ex -> ex
        .accessDeniedPage("/access-denied"));
```

If using an access-denied page, configure permit/mapping properly without creating an error loop. Depending on version and configuration, the handler may forward to the view while preserving status 403; **never** accidentally return 200 "success" for a denied error. Test both status and content—do not merely verify that an HTML page renders.

## 7. HTTP Basic API: 401 Challenge Instead of Redirect

HTTP Basic is an HTTP authentication mechanism suited for illustrating API clients (though production requires HTTPS, and Basic credentials do not auto-expire like tokens).

```java
// API chain fragment:
http.httpBasic(Customizer.withDefaults());
```

Default cases:

| API request | Expected |
| --- | --- |
| `GET /api/me` without `Authorization` | **401** with `WWW-Authenticate: Basic...` |
| `GET /api/me` wrong Basic password | **401** |
| `GET /api/me` valid Basic for role `USER` | **200** |
| `GET /api/admin` valid Basic for `USER`, requires `ADMIN` | **403** |
| `GET /api/admin` valid Basic for `ADMIN` | **200** |

API clients use 401 to prompt/supply credentials, taking care not to retry infinitely or forward secrets to other hosts. There is no reason to redirect to an HTML `/login` page when the endpoint contract is machine-to-machine.

### 7.1. 401 Does Not Always Have a JSON Body

The default `BasicAuthenticationEntryPoint` can return 401 and the Basic challenge header without the JSON body you might expect. If the API contract requires `application/problem+json`, configure a custom entry point on the right filter chain; do not expect Spring to build JSON automatically for every exception.

### 7.2. CSRF with Basic

Browsers can also send HTTP Basic credentials automatically after a user authenticates in the browser. Thus **HTTP Basic alone does not make it safe to disable CSRF**. For APIs called strictly by machine clients that do not attach browser credentials automatically, evaluate your threat model before configuring CSRF.

In the sample project, CSRF stays enabled on **both chains**; `POST /api/orders` requires a valid token, allowing tests to separate missing CSRF from missing role. The project uses Basic mainly to test statuses easily; it is not claimed to be an optimal production API configuration.

## 8. OAuth2 Resource Server/Bearer: 401 or 403 by Token and Scope

With Spring Security Servlet and OAuth2 Resource Server:

```java
http.oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults()));
```

This is a **fragment**; it requires the resource-server dependency and trusted issuer/JWK or decoder configuration. Bearer APIs normally do not redirect to the resource server's own login form; clients obtain a valid access token from an Authorization Server through a separate flow.

### 8.1. Missing Token

`GET /api/orders` without `Authorization: Bearer ...` when the resource requires authentication may receive:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

This is the appropriate OAuth2 Bearer challenge. Do not assume the backend will send a redirect to the IdP. A resource server is not an OAuth2 Login client.

### 8.2. Invalid or Expired Token

`BearerTokenAuthenticationEntryPoint` can return 401 and indicate `invalid_token` per RFC 6750. Example:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

A token with a bad signature, expired timestamp, wrong issuer/audience, or rejected by the decoder/validator has no valid authentication. Never use an unverified JWT to grant authorities. Never echo raw Bearer tokens in error bodies or logs.

### 8.3. Valid Token Lacking Scope

If the token is authenticated yet lacks `SCOPE_orders.write`, a rule can deny it:

```java
.requestMatchers(HttpMethod.POST, "/api/orders")
.hasAuthority("SCOPE_orders.write")
```

With `BearerTokenAccessDeniedHandler`, the response can be 403 with `WWW-Authenticate: Bearer error="insufficient_scope"`, depending on OAuth2 authentication state and configured scope details.

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope",
                  scope="orders.write"
```

**Do not** assert that every 403 includes `insufficient_scope` or fabricate headers regardless of cause. Handlers may differ if there is no authenticated OAuth2 token, if custom handlers are used, or if policy denied due to tenant/resource ownership rather than scope.

### 8.4. JWT Has the Scope Yet Is Still Denied by ABAC

`hasAuthority("SCOPE_orders.write")` only checks a broad authority. A user with the right scope still must not modify another tenant's order. When `@PreAuthorize` method security checks ownership/tenant and denies, the API typically returns 403; avoid disclosing another tenant's resources in error details.

### 8.5. Do Not Enable OAuth2 Login on a Resource Server Just to Handle 401

`oauth2Login()` is for apps logging users in via browser/authorization code flow; `oauth2ResourceServer().jwt()` is for requests carrying Bearer access tokens. Both can coexist in a well-designed system, but they do not replace each other. An API accepting JWTs should not arbitrarily return an HTML login page for every 401.

## 9. SPA, Mobile, and Machine-to-Machine: Choosing the Right Error Contract

### 9.1. SPA with Session Cookies

An SPA sharing an origin with a Spring Boot backend may use session cookies. When the session expires, REST endpoints should return a response JavaScript can handle reliably—typically **JSON 401**—while HTML page URLs can redirect to login.

Solutions include **multiple `SecurityFilterChain`s** partitioned by `/api/**` and `/web/**`, or a custom `DelegatingAuthenticationEntryPoint` with appropriate request matchers. Avoid configuring a single global entry point that breaks redirects for HTML pages or feeds HTML login pages to API calls.

### 9.2. SPA with Bearer Access Tokens

The API returns 401 when the token is missing/expired; the frontend can navigate to login or perform a token refresh per the app's authorization design. A 401 is **not** a command to retry token refreshes indefinitely; cap retries and distinguish issuer, audience, token revocation, and network failures.

If an access token is valid yet lacks permissions, 403 should show a "not permitted" UI or trigger an admin permission-request flow—never refresh endlessly hoping to gain extra scopes.

### 9.3. Mobile Applications

Mobile apps should not rely on 302 HTML redirects returned from JSON APIs. Authentication can be handled in a dedicated browser session via OAuth2 Authorization Code + PKCE, while the **resource server API** still uses 401/403 per the HTTP contract. Mobile renders login/permission UX from status codes rather than having the backend secretly return HTML forms.

### 9.4. Machine-to-Machine

Service accounts call APIs using Bearer tokens or the client credentials flow. 401/403 are normally handled via logs, metrics, and token management—there is no browser to display a login page. If a token lacks a scope, operator/client configuration must change; retrying with the same token after a 403 is usually pointless.

### Suggested Client Behavior Table

| Client | 401 | 403 | 302 login |
| --- | --- | --- | --- |
| Traditional browser page | Often converted to redirect by entry point | Display access denied | Usually appropriate |
| SPA `fetch` REST API | Surface unauthenticated state, route frontend/login | Display missing permissions | Easily auto-followed into unexpected HTML |
| Mobile API client | Trigger app-controlled authentication flow | Display missing permissions / disallow action | Should not return HTML login from API |
| M2M API client | Inspect/fetch new token if policy permits | Do not retry infinitely; report missing scope/permission | Inappropriate |
| OAuth2 Resource Server | Bearer challenge | Bearer insufficient scope / ABAC deny | Not the default |

## 10. Multiple SecurityFilterChains to Separate API and Web

Spring Security Servlet supports multiple filter chains ordered by `@Order`. Example:

```text
Request /api/me
  -> SecurityFilterChain @Order(1) securityMatcher("/api/**")
  -> HTTP Basic entry point
  -> missing authentication -> 401

Request /web/me
  -> SecurityFilterChain @Order(2) catch-all
  -> formLogin entry point
  -> missing authentication -> 302 /login
```

This is not "the more specific rule automatically wins." `FilterChainProxy` selects the **first matching chain**. If the catch-all chain precedes the API chain, it can shadow the API chain, causing the API to redirect to login instead of returning 401.

### 10.1. securityMatcher Differs from requestMatchers

- `securityMatcher("/api/**")`: determines which requests enter **the entire chain** and use its filters/entry points.
- `requestMatchers("/api/admin")` inside `authorizeHttpRequests`: selects **an authorization rule inside** the already-chosen chain.

A `requestMatchers("/api/admin").hasRole("ADMIN")` rule **cannot protect** `/api/admin` if it lives inside a chain that only matches `/web/**`.

### 10.2. Fallback Chain

If you define only an API chain `securityMatcher("/api/**")` with no fallback for other URLs, requests outside `/api/**` may bypass all Spring Security chains. Design a fallback chain for web traffic or deny-by-default according to application scope.

## 11. CSRF: Why Can a POST Return 403 Before Role Checks?

Spring Security enables CSRF by default for relevant unsafe requests. When browsers rely on session cookies or credentials sent automatically by the browser, CSRF is an essential protection layer.

```text
POST /api/orders (already HTTP Basic ADMIN user)
    |
    +--> Missing CSRF token
    |
    v
CsrfFilter -> AccessDeniedException / CSRF failure path
    |
    v
Typically 403
    |
    +--> hasRole("ADMIN") rule does not even need to run
```

Therefore, "an ADMIN request still returned 403" is **not enough** to conclude the admin role is misconfigured. In MockMvc, test role rules with `with(csrf())`, and separately test whether missing CSRF is rejected.

### 11.1. When to Consider Disabling CSRF?

For purely stateless APIs using Bearer tokens in the `Authorization` header and **not** relying on browser auto-sent credentials, an organization may decide CSRF is unnecessary on that specific API chain. If disabled, disable it only on the **appropriate chain** after evaluating authentication mechanisms, cookies, and CORS. Never disable CSRF across an entire web app using sessions/form login just to make an API call work.

### 11.2. CSRF 403 vs. Missing-Permission 403

A test asserting only `status().isForbidden()` on a POST does not prove it tested authorization. Test design should include:

1. Authorized user + **no** CSRF → rejected.
2. Unauthorized user + **with** CSRF → rejected by authorization.
3. Authorized user + **with** CSRF → succeeds.
4. Anonymous + CSRF → appropriate entry point/unauthenticated response.

Then verify whether the request actually mutated data. Test negative statuses alongside zero side effects.

## 12. API JSON Errors and Problem Details

REST APIs often want a consistent error schema, such as RFC 9457 Problem Details:

```json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication required"
}
```

Or:

```json
{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "Access denied"
}
```

`Content-Type` may be `application/problem+json`. Fields `type`, `title`, `status`, and `detail` are a common structure, though organizations may extend the contract. Never use `detail` to leak "User alice belongs to tenant north while document 102 belongs to south" if that exposes sensitive metadata.

**Important:** a JSON body does not replace the `WWW-Authenticate` obligation when using HTTP Basic/Bearer challenges. If customizing 401, preserve the scheme-appropriate challenge header so clients know which authentication type the request needs.

### 12.1. Configuring Custom Handlers on the Right Chain

This fragment illustrates customizing responses on an **API chain**. Do not paste it directly into the Basic demo project below without analyzing Basic's entry point and expected `WWW-Authenticate`:

```java
http.exceptionHandling(ex -> ex
        .authenticationEntryPoint((request, response, authError) -> {
            response.setStatus(401);
            response.setContentType("application/problem+json");
            response.setCharacterEncoding("UTF-8");
            response.setHeader("WWW-Authenticate", "Basic realm=\"api\"");
            response.getWriter().write(
                    "{\"type\":\"about:blank\",\"title\":\"Unauthorized\",\"status\":401}");
        })
        .accessDeniedHandler((request, response, denied) -> {
            response.setStatus(403);
            response.setContentType("application/problem+json");
            response.setCharacterEncoding("UTF-8");
            response.getWriter().write(
                    "{\"type\":\"about:blank\",\"title\":\"Forbidden\",\"status\":403}");
        }));
```

This snippet is a **fragment inside `HttpSecurity` configuration**, assuming a Basic API. Do not use a `Basic` header for a Bearer resource server; for Bearer, preserve RFC 6750 semantics and prefer `BearerTokenAuthenticationEntryPoint`/`BearerTokenAccessDeniedHandler` or verified extensions. In production, use a proper serializer, avoid manual JSON string concatenation from inputs, avoid double-committed responses, and track error metrics.

### 12.2. MVC ControllerAdvice Does Not Cover All Filters

`@ControllerAdvice` can return `ProblemDetail` for domain/controller errors, yet an `AuthenticationException` caught inside the security filter chain may never reach the MVC exception handler. For uniform API responses, configure both security entry points/denied handlers **and** MVC error handlers, and test both paths.

### 12.3. Never Redirect to User-Supplied URLs

If an API or web endpoint accepts a `returnUrl` parameter, never redirect arbitrarily to external domains or open-redirect URLs. Accept only relative internal paths or an allowlist, and avoid query strings carrying tokens. Especially with OIDC login, redirect URIs must be registered with the IdP.

## 13. Runnable Spring Boot Project: Same App, Web 302 and API 401

This demo uses **Java 17+**, **Spring Boot 3.3.5** (Spring Security 6.x managed by Boot), **Gradle 8.5**, HTTP Basic for `/api/**`, and form login for web. No database or IdP is needed.

Practice goals:

- Anonymous `GET /api/me` → **401** + Basic challenge.
- Anonymous `GET /web/me` → **302** to `/login`.
- Alice logs in via form then `GET /web/admin` → **403**.
- Alice uses Basic to call `GET /api/admin` → **403**.
- Admin with proper role accesses `/web/admin` and `/api/admin` → **200**.
- API POST with right role but **missing CSRF** → **403**.
- API POST with wrong role **and valid CSRF** → **403**.
- API POST with right role **and valid CSRF** → **200** (note: controller returns 201 Created).
- Wrong form credentials → redirect with `error`; not confused with API 401.
- `/api/public` is public without exposing other endpoints.
- Web logout after login with CSRF invalidates the session.

### 13.1. Directory Structure

```text
security-response-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    SecurityConfig.java
    DemoController.java
  src/test/java/demo/
    SecurityResponseTest.java
```

### 13.2. settings.gradle

```groovy
rootProject.name = 'security-response-demo'
```

### 13.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

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

### 13.4. DemoApplication.java

`src/main/java/demo/DemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 13.5. SecurityConfig.java

`src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("study123"))
                .roles("USER")
                .build();

        UserDetails editor = User.withUsername("editor")
                .password(encoder.encode("study123"))
                .roles("USER", "EDITOR")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("study123"))
                .roles("USER", "ADMIN", "EDITOR")
                .build();

        return new InMemoryUserDetailsManager(alice, editor, admin);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {

        http.securityMatcher("/api/**");

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                        .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin")
                        .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                        .hasRole("EDITOR")
                .anyRequest().authenticated());

        http.httpBasic(Customizer.withDefaults());

        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        // CSRF is not disabled: even for Basic API, POST requires a token per demo.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/goodbye").permitAll()
                .requestMatchers("/web/admin").hasRole("ADMIN")
                .anyRequest().authenticated());

        http.formLogin(form -> form.permitAll());

        http.logout(logout -> logout
                .logoutSuccessUrl("/goodbye")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .permitAll());

        return http.build();
    }
}
```

**Explanation:**

1. `@Order(1)` API chain with `securityMatcher("/api/**")` precedes the web fallback chain. Thus an unauthenticated API request uses the **HTTP Basic entry point** instead of receiving an HTML redirect from the form-login chain.
2. `@Order(2)` web chain is the fallback, using form login/sessions, so anonymous web page requests normally receive a `/login` redirect.
3. `hasRole("ADMIN")` checks the `ROLE_ADMIN` authority. User `alice` only has `ROLE_USER`, so even logged in she gets 403.
4. `httpBasic(Customizer.withDefaults())` sends a Basic challenge when authentication is needed. The API configuration here is **stateless** regarding security sessions.
5. CSRF is **not disabled** on API or web. Because browsers can auto-send Basic credentials, this is an understandable choice for the demo, even though a production pure-bearer API may adopt a different policy.
6. `.requestMatchers(HttpMethod.POST, "/api/orders")` enforces the `EDITOR` role. `.anyRequest().authenticated()` serves as the API chain's fallback.
7. Web form login and logout use Spring Security's standard endpoints. The `/login` page is generated when no custom login page is set.
8. Usernames/passwords in source are for localhost demo only—never use them in production.

**Never place a catch-all `SecurityFilterChain` ahead of the API chain**, or the API will receive the wrong entry point. **Never add `http.formLogin()` to the API chain** if the API contract expects Basic-only; if both Basic and form exist on the same chain, explicitly define entry-point request matchers.

### 13.6. DemoController.java

`src/main/java/demo/DemoController.java`:

```java
package demo;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "home";
    }

    @GetMapping("/goodbye")
    public String goodbye() {
        return "goodbye";
    }

    @GetMapping("/web/me")
    public String webMe(Authentication authentication) {
        return "web:" + authentication.getName();
    }

    @GetMapping("/web/admin")
    public String webAdmin(Authentication authentication) {
        return "web-admin:" + authentication.getName();
    }

    @GetMapping("/api/public")
    public String apiPublic() {
        return "api-public";
    }

    @GetMapping("/api/me")
    public String apiMe(Authentication authentication) {
        return "api:" + authentication.getName();
    }

    @GetMapping("/api/admin")
    public String apiAdmin(Authentication authentication) {
        return "api-admin:" + authentication.getName();
    }

    @PostMapping("/api/orders")
    @ResponseStatus(HttpStatus.CREATED)
    public String createOrder(Authentication authentication) {
        return "created:" + authentication.getName();
    }
}
```

The `POST /api/orders` API endpoint intentionally returns **201 Created** on success, fitting a creation operation; do not confuse it with `200 OK`. The tests below assert **201** rather than assuming every success is 200.

There is no database in this demo. `@ResponseStatus(HttpStatus.CREATED)` only clarifies the status contract; real products need validation, resource ownership, and transactions.

## 14. SecurityResponseTest: Testing Status, Redirects, and Challenge Headers

`src/test/java/demo/SecurityResponseTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityResponseTest {

    @Autowired
    MockMvc mvc;

    private MockHttpSession loginWeb(String username) throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/login")
                        .session(session)
                        .with(csrf())
                        .param("username", username)
                        .param("password", "study123"))
                .andExpect(status().is3xxRedirection());

        return session;
    }

    @Test
    void publicApiDoesNotChallenge() throws Exception {
        mvc.perform(get("/api/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("api-public"));
    }

    @Test
    void anonymousApiGets401AndBasicChallenge() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        "WWW-Authenticate", containsString("Basic")));
    }

    @Test
    void invalidBasicCredentialsGet401() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "wrong-password")))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        "WWW-Authenticate", containsString("Basic")));
    }

    @Test
    void validBasicUserGets200() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "study123")))
                .andExpect(status().isOk())
                .andExpect(content().string("api:alice"));
    }

    @Test
    void userWithoutAdminRoleGets403Not401() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(httpBasic("alice", "study123")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminGets200OnApiAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(httpBasic("admin", "study123")))
                .andExpect(status().isOk())
                .andExpect(content().string("api-admin:admin"));
    }

    @Test
    void anonymousWebGets302ToLogin() throws Exception {
        mvc.perform(get("/web/me"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void anonymousWebAdminAlsoRedirectsToLogin()
            throws Exception {
        mvc.perform(get("/web/admin"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void loginFormGetsBrowserSession() throws Exception {
        MockHttpSession session = loginWeb("alice");

        mvc.perform(get("/web/me").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("web:alice"));
    }

    @Test
    void loggedInWebUserWithoutAdminRoleGets403()
            throws Exception {
        MockHttpSession session = loginWeb("alice");

        mvc.perform(get("/web/admin").session(session))
                .andExpect(status().isForbidden());
    }

    @Test
    void loggedInWebAdminGets200() throws Exception {
        MockHttpSession session = loginWeb("admin");

        mvc.perform(get("/web/admin").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("web-admin:admin"));
    }

    @Test
    void invalidFormLoginRedirectsWithError() throws Exception {
        MvcResult result = mvc.perform(post("/login")
                        .with(csrf())
                        .param("username", "alice")
                        .param("password", "wrong-password"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        String redirected = result.getResponse().getRedirectedUrl();
        assertNotNull(redirected);
        assertTrue(redirected.contains("/login?error"));
    }

    @Test
    void apiPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/orders")
                        .with(httpBasic("editor", "study123")))
                .andExpect(status().isForbidden());
    }

    @Test
    void apiPostWithCsrfButWithoutRoleIsForbidden()
            throws Exception {
        mvc.perform(post("/api/orders")
                        .with(httpBasic("alice", "study123"))
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void apiPostWithRoleAndCsrfIsCreated() throws Exception {
        mvc.perform(post("/api/orders")
                        .with(httpBasic("editor", "study123"))
                        .with(csrf()))
                .andExpect(status().isCreated())
                .andExpect(content().string("created:editor"));
    }

    @Test
    void webLogoutInvalidatesSession() throws Exception {
        MockHttpSession session = loginWeb("alice");

        mvc.perform(post("/logout")
                        .session(session)
                        .with(csrf()))
                .andExpect(status().is3xxRedirection());

        assertTrue(session.isInvalid());

        mvc.perform(get("/web/me"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void unknownApiPathWithoutLoginCanBe401BeforeMvc404()
            throws Exception {
        mvc.perform(get("/api/unknown"))
                .andExpect(status().isUnauthorized());
    }
}
```

**Expected result:** 17 JUnit tests PASS with the demo's configuration and versions. This is an **expectation after reading and inspecting the code**, not a claim that the tests were run in a live environment. Some responses/headers may change if custom filters/entry points are added or framework versions are upgraded; run the tests when integrating.

### 14.1. Four Things the Tests Clearly Prove

1. **API challenge:** 401 includes `WWW-Authenticate` Basic, distinct from form-login 302.
2. **Authenticated missing role:** Alice receives 403 on `/api/admin` and `/web/admin`; she is not redirected to login again.
3. **Credential failure:** wrong Basic yields 401; wrong form login redirects to `/login?error`.
4. **CSRF vs. authorization:** POST missing CSRF gets 403, POST with CSRF but missing role gets 403, POST with both succeeds with **201**.

### 14.2. What the Tests Do Not Yet Prove

- There is no Bearer JWT decoder/IdP in the project, so these 17 tests cannot claim to verify real RFC 6750 Bearer behavior.
- They do not test browser CORS preflight or reverse proxy/TLS.
- They do not test request cache/saved requests across all browser/session states.
- They do not test custom JSON `ProblemDetail` handlers (the project uses default responses).
- They do not test session fixation/remember-me, object-level authorization (IDOR/BOLA), or rate limiting.

These are the additional suites needed when moving from lesson to production.

## 15. Running the App and Observing HTTP

With JDK 17+ and Gradle 8.5 (or a compatible Gradle Wrapper), in the project directory:

```bash
gradle test
gradle bootRun
```

With Gradle Wrapper on macOS/Linux:

```bash
./gradlew test
./gradlew bootRun
```

Windows PowerShell when the project has a wrapper:

```powershell
.\gradlew.bat test
.\gradlew.bat bootRun
```

Test the localhost API (HTTP is for demo only; never send credentials over real networks):

```bash
curl -i http://localhost:8080/api/public

curl -i http://localhost:8080/api/me

curl -i -u alice:study123 \
     http://localhost:8080/api/me

curl -i -u alice:study123 \
     http://localhost:8080/api/admin

curl -i -u admin:study123 \
     http://localhost:8080/api/admin
```

Expected results in order: **200**, **401** with `WWW-Authenticate: Basic...`, **200**, **403**, **200**.

Try the browser at `http://localhost:8080/web/me`: when unauthenticated, it typically redirects to `/login`. Log in as `alice/study123` and visit `/web/admin`—you will get 403. Log in as `admin/study123` and you can access it.

**Do not** attempt `POST /login` with `curl` without a session/CSRF token; default form login expects a request-bound CSRF token. If you `POST /api/orders` without CSRF, 403 is the demo's expected behavior.

### 15.1. Testing Redirects with curl

By default `curl -i` does not follow redirects; it displays status 302 and `Location`. If you pass `curl -L`, the client automatically sends the next request and may show **200 HTML of the login page**, masking the initial 302 response.

When debugging, inspect every response in the redirect chain. In browser DevTools, inspect the Status/Location/Content-Type columns and request initiator. Never capture or share real session cookies or Basic `Authorization` headers containing credentials.

## 16. Resource Server Bearer: How Should Extra Tests Be Written?

For a real resource server, you need the dependency:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
```

And appropriate security rules:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/public")
                .permitAll()
        .requestMatchers(HttpMethod.POST, "/api/orders")
                .hasAuthority("SCOPE_orders.write")
        .anyRequest().authenticated());

http.oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults()));
```

The snippets above are **configuration fragments** for a separate project—**do not add them to the demo's Basic API chain** without designing multi-scheme behavior. Production requires configuring a trusted JWT decoder/JWK/issuer.

### 16.1. Testing JWT with spring-security-test

You can use `SecurityMockMvcRequestPostProcessors.jwt()` to create an authenticated JWT in **MockMvc tests** and supply controlled authorities/scopes into the security context:

```java
// Fragment inside a MockMvc test with api matcher and Bearer rules:
mvc.perform(post("/api/orders")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.write"))))
   .andExpect(status().isCreated());
```

This is only a **fragment**, requiring static imports for `jwt()` and `SimpleGrantedAuthority` and matching setup. It tests authorization with a simulated `JwtAuthenticationToken`; it does **not** prove real JWT signature/issuer/JWK validation. If CSRF is enabled on that chain, add `with(csrf())` to test roles/scopes; on a pure Bearer stateless chain, decide CSRF based on a reviewed threat model.

### 16.2. Testing Real 401 Challenges

To verify `WWW-Authenticate: Bearer` on requests missing a token or carrying an actually invalid token, call the endpoint **without `jwt()`**, with `BearerTokenAuthenticationFilter` and the resource-server entry point active in the test context. You can configure a mock `JwtDecoder` throwing the appropriate `JwtException` to verify invalid tokens; never infer 401 from a test using `jwt()` since that helper bypasses the decoder.

### 16.3. Testing 403 insufficient_scope

Create a verified JWT authentication per test setup **without** `SCOPE_orders.write`, call the protected action, and expect 403. Inspect the `WWW-Authenticate` Bearer error in integration tests with the corresponding handler, rather than hardcoding that every authorization failure emits the exact same header. If the API uses ownership policies, a 403 does not necessarily include `insufficient_scope`, especially when scopes are sufficient yet the resource belongs to another tenant.

## 17. When Should You Return 404 Instead of 403?

Suppose `GET /api/documents/102` accesses a sensitive document belonging to another tenant. If you return 403 for existing IDs and 404 for non-existent IDs, attackers can enumerate valid document IDs from status codes.

A system may apply **resource concealment**: for resources outside the caller's tenant/ownership scope, return 404 per the API contract to avoid confirming existence. However:

- 404 does not replace real permission enforcement.
- Do not merely swap the status while letting response times or error details leak metadata.
- Never use 404 to mask operational failures or missing authentication; distinguish authentication challenges from resource visibility.
- Rules must be consistent across services/queries (tenant-scoped repositories) and controllers/exception translation.

HTTP 403 remains appropriate when the user is allowed to know the resource exists yet is not permitted to perform the action. Choosing between 403 and 404 requires an explicit security/UX policy, not mere habit.

## 18. 405, 400, 409, and Validation Errors Are Not Security Denials

| Status | Common case | Why not arbitrarily use 401/403? |
| --- | --- | --- |
| **400 Bad Request** | Malformed JSON, invalid parameters, missing required field | Input errors may be unrelated to authentication |
| **401 Unauthorized** | Missing or invalid authentication credentials | Client needs valid authentication |
| **403 Forbidden** | Authenticated yet lacking permission; CSRF failure | Authentication does not auto-grant action rights |
| **404 Not Found** | Resource not found or concealing out-of-scope resource | Does not claim missing credentials |
| **405 Method Not Allowed** | Path has a handler, yet HTTP method is unmapped | Does not mean the user lacks a role |
| **409 Conflict** | Conflicting resource state, duplicate action | Not an access permission issue |
| **429 Too Many Requests** | Rate limiting | Do not use 401 to mask throttling |

Spring Security can reject a request **before it reaches MVC**. For instance, if an anonymous user calls `/api/missing` and the API chain requires authentication first, the request may receive 401 instead of 404; only after authenticating does MVC return 404.

Similarly, a POST missing CSRF can receive 403 before Spring MVC checks whether a handler supports the method. **The observed status is a result of filter order plus MVC, not merely whether a route exists.**

## 19. CORS Preflight and Unexpected Error Responses

Cross-origin browsers may send an `OPTIONS` preflight before the actual `GET`/`POST`, typically without the cookies, session, or `Authorization` header of the main request. If `SecurityFilterChain` requires authentication for every `OPTIONS`, the API may return 401/redirect and the browser blocks the call, making the login API look "broken".

When CORS is needed:

- Configure `http.cors(...)` and `CorsConfigurationSource`/Spring MVC CORS for trusted origins/methods/headers.
- Ensure CORS is handled early enough in the security chain so valid preflight requests are not forced through unnecessary authentication.
- Never default to `permitAll("OPTIONS /**")` across every system without understanding the threat model.
- Never use wildcard origins with credentials arbitrarily.
- Never disable CSRF just because "CORS is enabled." CORS and CSRF address two different threats.

Debug preflight via browser DevTools/Network and response headers such as `Access-Control-Allow-Origin`. Do not conclude "401 wrong user password" when the blocked request was actually an `OPTIONS` preflight.

## 20. Logs and Telemetry: Pinpointing Which Component Returned the Status

When a request behaves unexpectedly, inspect in order:

1. **Actual request:** method, path, query, content type; never log raw `Authorization`/cookies.
2. **Selected chain:** `securityMatcher`, `@Order`, fallback.
3. **Authentication mechanism:** form login, Basic, Bearer, session, remember-me.
4. **`SecurityContext`:** is there a valid `Authentication`? Anonymous or authenticated principal? Which authorities?
5. **Exception:** `AuthenticationException`, `AccessDeniedException`, `InvalidCsrfTokenException`, or an MVC exception?
6. **Entry point/handler:** which `AuthenticationEntryPoint` initiated authentication? Which `AccessDeniedHandler` returned 403?
7. **Response status and headers:** 302 `Location`, 401 `WWW-Authenticate`, 403 and Bearer headers when applicable.
8. **Redirect chain:** did the client auto-follow a redirect to an HTML login page?
9. **Authorization rule:** role/scope/tenant/ownership? Which rule matched first?
10. **CSRF/CORS:** POST missing token or failed `OPTIONS` preflight?
11. **Proxy/IdP:** are redirects and forwarded scheme/host/path accurate and trusted?
12. **Controlled retry:** fix the actual credential/role rather than retrying indefinitely.

In dev environments you can enable:

```properties
logging.level.org.springframework.security=DEBUG
```

**Warning:** never log `Authorization` headers, Bearer JWTs, Basic passwords, session IDs, cookies, CSRF tokens, or private user data. Error responses must not expose raw exceptions or stack traces to public clients.

## 21. Common Pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| JSON API returns 302 to form login | Client follows redirect and gets HTML violating contract | API entry point returns 401/appropriate challenge |
| Traditional web always returns JSON 401 | Browser fails to trigger login flow | Form-login chain and proper redirect |
| Logged-in user missing role redirected to login | Loop/bad UX without elevating permissions | Use `AccessDeniedHandler`/403 |
| Missing `WWW-Authenticate` with HTTP Basic | Client cannot parse auth challenge | Preserve Basic entry point/header |
| Using Basic challenge on a Bearer API | Wrong scheme, breaks client interoperability | RFC 6750 Bearer handlers |
| JWT with invalid signature returns 403 | Confuses invalid authentication with missing scope | Return 401 per token error semantics |
| Valid token missing scope returns 401 | Client refreshes/re-logs in fruitlessly | Return 403 on authorization denial |
| Changing only MVC `@ControllerAdvice` | Security filter errors still emit default HTML/redirects | Configure security entry points/denied handlers |
| Web fallback chain placed before API chain | API traffic handled by form login | Correct `@Order` + `securityMatcher` |
| Missing fallback chain | URLs may go unprotected by Spring Security | Design catch-all/fallback chain |
| Enabling `csrf.disable()` app-wide so POST returns 200 | Exposes form/session endpoints to CSRF | Adjust only on the right chain per threat model |
| Testing POST 403 without `with(csrf())` | Test only proves CSRF blocks it | Add a test with CSRF and verify role separately |
| 200 HTML login after API redirect treated as API success | JSON parser errors / hard-to-debug behavior | Check redirect history/content type |
| Accepting arbitrary redirect URI from query | Open redirect/phishing | Allowlist internal return URLs |
| Logging raw JWT/Basic credentials | Leaks bearer tokens/passwords | Redact and restrict log access |
| 403 reveals another owner/tenant | Information disclosure | Generic error details, resource concealment |
| Anonymous 401 explained as logged-in missing permission | Debugging chases wrong cause | Inspect actual `Authentication` |
| Using 401 for validation errors | Client fruitlessly retries credentials | Match HTTP status to actual error |
| Infinite 403 retries in client apps | Loads system without fixing missing permissions | Route user/permissions through proper flow |

## 22. Pre-Deployment Checklist

- [ ] Classify endpoints: HTML browser page, session API, Basic API, or Bearer Resource Server.
- [ ] Anonymous HTML pages route to the proper login page (when using form UX).
- [ ] Anonymous API calls receive 401/challenge, never unintended HTML login pages.
- [ ] Authenticated callers lacking role/scope/tenant receive appropriate denials, typically 403.
- [ ] Basic 401 includes `WWW-Authenticate: Basic`.
- [ ] Bearer 401/403 includes headers/errors per RFC 6750 where applicable.
- [ ] Invalid credentials and insufficient authorization have separate regression tests.
- [ ] CSRF is enabled/disabled per threat model, never disabled globally just to test APIs.
- [ ] POST with role but missing CSRF, with CSRF but missing role, and with both are tested independently.
- [ ] CORS preflight and `OPTIONS` operate per policy.
- [ ] `securityMatcher`/`@Order` select the right chain, with fallback coverage.
- [ ] Form login page and login processing cause no redirect loops.
- [ ] Custom errors are consistent across Security filters and MVC controllers.
- [ ] API errors follow a JSON contract, use accurate statuses, and leak no secrets.
- [ ] `fetch`/mobile clients handle redirects, 401, and 403 per UX type.
- [ ] Non-existent URLs and resource concealment have clear 404 rules.
- [ ] No open redirects via `returnUrl`/post-login URLs.
- [ ] Test anonymous, authenticated `USER`, `ADMIN`, and Basic invalid login.
- [ ] When upgrading Spring Security/Boot, re-run status/header/redirect tests.
- [ ] Logs/metrics contain no `Authorization`/cookies/JWT/CSRF secrets.

## 23. Self-Check Questions

1. **Why might an anonymous user visiting a web page receive 302 rather than 401?** Because the form-login entry point initiates authentication via a browser redirect to `/login`.
2. **What does an HTTP Basic API without credentials typically return?** 401 and `WWW-Authenticate: Basic`.
3. **What about a logged-in user lacking `ROLE_ADMIN`?** Typically 403 via `AccessDeniedHandler`, without forcing repeated re-login.
4. **What does an expired OAuth2 access token typically return?** 401 with an appropriate Bearer challenge/error, not 403 insufficient scope.
5. **What if the token is valid yet lacks a scope?** Typically 403; the Bearer handler may indicate `insufficient_scope`.
6. **Can a Basic header be used for a JWT resource server?** No, it needs a proper `Bearer` challenge.
7. **Does a 403 on POST prove a missing role?** No; it could be a missing/invalid CSRF token.
8. **Why does `fetch` sometimes see 200 HTML instead of 302?** The client followed the redirect to the login page and returned the final response.
9. **What does `ExceptionTranslationFilter` do?** Connects `AuthenticationException`/`AccessDeniedException` in the security chain to the appropriate `AuthenticationEntryPoint` or `AccessDeniedHandler`.
10. **How does `AuthenticationEntryPoint` differ from `AccessDeniedHandler`?** The entry point initiates authentication; the handler handles denied access when already in an appropriate state.
11. **Can a single form-login chain serve every API?** It can be configured that way, but typically violates API contracts expecting 401 JSON/challenges.
12. **How does `securityMatcher` differ from `requestMatchers`?** Selecting the scope of an entire filter chain versus selecting authorization rules inside a chain.
13. **Is an anonymous call to a non-existent URL guaranteed to get 404?** No; Security may block with 401/redirect before MVC runs.
14. **Does changing `@ControllerAdvice` guarantee handling every error from filters?** No; Security entry points/handlers must be configured.
15. **Why are custom responses needed for SPAs?** To return statuses/bodies JS understands, avoiding unintended HTML login redirects.
16. **Does 401 require a JSON body?** Not mandatory; the challenge header is vital for HTTP auth schemes.
17. **Is a failed default form login a JSON 401?** No; it typically redirects to `/login?error` via the failure handler.
18. **Why not redirect 403 back to login?** The user is already authenticated yet lacks permissions; logging in again will not change policy and creates a loop.
19. **Are CSRF and CORS the same?** No; CORS restricts cross-origin browser access, while CSRF protects state-changing requests using browser credentials.
20. **When a 403 is caused by a tenant resource, should the real tenant ID appear in error details?** No, to prevent information disclosure.
21. **When is 404 better than 403?** When policy aims to conceal the existence of resources outside the user's permissions under a consistent contract.
22. **What should MockMvc Spring Security tests assert?** Status, challenge/`Location` headers, appropriate body, and sometimes state/cookies—not just a generic status.
23. **Can a `jwt()` test prove JWT signature validation?** No; it mocks `Authentication` and bypasses the decoder/cryptographic validation.
24. **Why not disable CSRF for the entire app?** Web sessions/form logins become vulnerable to CSRF requests because browsers attach cookies automatically.
25. **If a client sees 403, should it keep refreshing its token forever?** No; it may be an actual missing permission requiring a permission flow rather than infinite retries.

**Remember:** **401** usually signals missing/invalid authentication and comes with a **challenge header** when using Basic/Bearer; **403** usually signals authorization denied with existing authentication (or a CSRF denial); **302 to `/login`** is how browser web form-login starts signing in. Spring Security Servlet decides this via **`SecurityFilterChain`**, **`AuthenticationEntryPoint`**, **`AccessDeniedHandler`**, and proper exception handling. Choose the contract according to **application type**, test status/headers/redirects/CSRF/roles, never let APIs unexpectedly receive HTML login pages, and never infer root cause from status codes alone.
