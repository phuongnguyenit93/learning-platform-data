# Redirecting to a Login Page vs Returning HTTP 401 for APIs

## 1. Problem Statement: One Application, Two Ways to Respond When Unauthenticated

A Spring Security application can simultaneously serve **HTML pages for users** and **REST APIs for frontends/mobile apps/services**. Both have resources requiring authentication, yet when credentials are missing or invalid, the appropriate response can be completely different:

- A browser opening `GET /web/profile` without a session: usually needs **HTTP 302 Found**, header `Location: /login`. The browser automatically opens the login page; after logging in, the application can resume accessing the original resource.
- An API client calling `GET /api/profile` without a bearer access token: usually needs **HTTP 401 Unauthorized** with the `WWW-Authenticate: Bearer` challenge; do not send an HTML login page and do not redirect to a web form.
- An authenticated client lacking the scope/role to access an API: normally **HTTP 403 Forbidden**, not a login redirect and not a 401 merely for insufficient permissions.

This lesson belongs to the **Authentication Responses** section of the **Spring Security - authentication** module. The goal is to understand HTTP semantics, the execution path in Spring Security Servlet, proper web/API configuration, avoiding out-of-context redirects, and thoroughly testing all scenarios.

**Key takeaway:** returning `302` or `401` is **a decision of the interaction protocol and resource policy** when authentication is required. It does not replace password/token verification; nor does it mean the application is allowed to weaken security just because a request "looks like an API".

## 2. Comparison Table of HTTP 302, 401, and 403

| HTTP Code | Standard Name | Meaning in Application | Typical Header | Client Handling |
| --- | --- | --- | --- | --- |
| **302** | Found | Web resource requires login, directs browser to login page | `Location: /login` | Browser navigates to the login page |
| **303** | See Other | Redirects client with GET to another URL, typically after a successful POST | `Location: /somewhere` | Follows new URI via GET |
| **401** | Unauthorized | Request lacks valid credentials for the resource | `WWW-Authenticate: Bearer` or `Basic ...` | Client obtains/refreshes credential, retries if appropriate |
| **403** | Forbidden | Request is authenticated but not authorized, or rejected by another policy | Usually no `Location` | Do not auto-retry login repeatedly; handle missing permission |
| **429** | Too Many Requests | Quota/rate limit exceeded, e.g. login throttling | Possibly `Retry-After` | Back off per policy, do not spam retries |
| **500/503** | Server/Service Unavailable | Authentication system or dependency is failing | Varies by error | Do not confuse with "wrong password" or "log in again" |

**Detail:** the standard name of HTTP 401 is "Unauthorized", yet in practice it is commonly used for **unauthenticated**; 403 is commonly used for authenticated but **not permitted**. HTTP also allows 403 for certain other policy reasons; the actual status from Spring Security also depends on the entry point, CSRF, access denied handler, and credential type.

**Do not swap 302 and 401 arbitrarily.** An API client may automatically follow 302, receive the login page HTML with status 200, and assume the API call succeeded. Conversely, a browser opening a web page that only receives JSON 401 usually does not get an appropriate login experience.

## 3. Two Illustrative HTTP Exchanges

### 3.1. Web Browser: Redirect to Login Page

Request without a session:

```http
GET /web/profile HTTP/1.1
Host: app.example.test
Accept: text/html
```

Common response when form login is configured:

```http
HTTP/1.1 302 Found
Location: /login
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
```

The browser will issue **another** request to `GET /login`. This is not 401, and the login page is not the response of the `/web/profile` endpoint. The `Location` header may contain an absolute URL in some deployments/proxies, so tests should check the expected destination rather than assuming one exact string always holds.

After successful login, Spring Security can use the saved request to return to the original resource. This is UX for **browser navigation**; it should not be copied verbatim into a JSON API.

### 3.2. REST API: Return 401 Challenge

```http
GET /api/profile HTTP/1.1
Host: app.example.test
Accept: application/json
```

Typical response when using OAuth2 Resource Server:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Cache-Control: no-store
```

Spring Security can append appropriate parameters to `WWW-Authenticate`; for example, a bearer token rejected due to expiration/bad signature may receive `error="invalid_token"` per RFC 6750. It is **not** mandatory for every 401 response to have a JSON body. HTTP clients must rely on status and challenge per the contract; the body is supporting data, not a credential.

### 3.3. Valid Token but Lacking Permissions: 403

Suppose the token has already been verified by the Resource Server for signature, issuer, audience, and lifetime, yet only has `SCOPE_profile.read` while `/api/admin` requires `SCOPE_admin.read`.

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

This is an **example header format you may encounter**, not a byte-for-byte guarantee across all versions and custom handlers. Key point: a valid token does not imply sufficient permissions. Do not turn missing scope into a 302 to web login; logging in again with the same permissions will not necessarily resolve it.

## 4. Who Decides the Response in Spring Security?

In the Servlet stack, a request passes through `FilterChainProxy` and the filters of the matching `SecurityFilterChain`. Involved components:

| Component | Role |
| --- | --- |
| `AuthorizationFilter` / method security | Enforces permission policy; can throw `AccessDeniedException` |
| `ExceptionTranslationFilter` | Translates security exceptions into HTTP responses / initiates authentication |
| `AuthenticationEntryPoint` | Selects **how to start authentication**: redirect, 401 + challenge, HTTP status… |
| `LoginUrlAuthenticationEntryPoint` | Redirects to the form login URL for browsers |
| `BearerTokenAuthenticationEntryPoint` | Returns OAuth2 Bearer status/challenge for Resource Server |
| `BasicAuthenticationEntryPoint` | Sends 401 with `WWW-Authenticate: Basic ...` challenge |
| `HttpStatusEntryPoint` | Returns only the configured status, e.g. 401; does not emit a Bearer challenge |
| `AccessDeniedHandler` | Handles denied permissions after authentication, usually 403 |
| `RequestCache` | Can save the web request before redirect to resume after login |
| `AuthenticationFailureHandler` | Handles **failed POST login**; distinct from entry point when hitting a protected resource |

### 4.1. ExceptionTranslationFilter Does Not Verify Passwords

A common scenario:

```text
GET /web/profile (anonymous)
    |
    v
AuthorizationFilter: requires authenticated → denied
    |
    v
ExceptionTranslationFilter:
    request not authenticated → AuthenticationEntryPoint
    |
    v
LoginUrlAuthenticationEntryPoint
    |
    v
302 Location: /login
```

For `GET /api/profile`, the Resource Server chain selects the Bearer entry point and returns 401. If an authenticated user lacks a role, `ExceptionTranslationFilter` normally forwards `AccessDeniedException` to `AccessDeniedHandler`, typically 403.

Distinguish **exceptions raised inside the authentication filter flow** (e.g., malformed bearer token handled by the bearer filter/entry point) from exceptions raised during authorization checks. Not every failure follows the same internal call stack, even when they produce the same HTTP code. Configure and test the **final outcome** instead of relying solely on guessed filter ordering.

### 4.2. Entry Point Is Not Success/Failure Handler

- Unauthenticated request to `/web/profile` → entry point decides the 302 redirect.
- User submits `POST /login` with wrong password → `AuthenticationFailureHandler` typically redirects to `/login?error` (or another response if customized).
- User submits valid login → `AuthenticationSuccessHandler` resumes saved request/default URL.
- Authenticated user hits resource without permission → `AccessDeniedHandler` decides 403 or another policy.

If you only customize `AuthenticationEntryPoint` expecting to change the response of a **wrong-password form POST login**, it may not achieve that: that is the failure handler's job. Conversely, changing the failure handler will not automatically turn a tokenless API call into 401.

## 5. Browsers and APIs Need Different Contracts

For **HTML pages using server-side sessions**:

1. The browser sends a session cookie if present.
2. Protected resources require the user to be logged in.
3. If not logged in, the server normally returns a 302 redirect to a form/OIDC login page.
4. The browser displays the login; after valid login, it can return to the previous request.

For **token-based REST APIs**:

1. The client sends `Authorization: Bearer <access_token>` over TLS.
2. The Resource Server verifies the access token by issuer/signature or introspection, audience, timestamps, and policy.
3. If missing/invalid token, return 401 with the appropriate challenge; if valid token lacking scope, typically 403.
4. The client decides whether to request a new token, prompt user interaction via a valid flow, or show an error. The server does not send API requests to an HTML form.

An SPA running in a browser **is still an API client** when calling `fetch("/api/...")`. The fact that the request originates from a browser does not turn a JSON endpoint into web navigation. Distinguish **top-level navigation** from **AJAX/fetch** and **path policy**, rather than guessing from User-Agent alone.

## 6. Why Looking Only at Accept or X-Requested-With Is Not Enough

`Accept: text/html` can hint at rendering intent, yet:

- JavaScript `fetch` can send `Accept: */*`.
- Browser navigation can accept multiple media types.
- A mobile client might send `Accept: text/html` due to a wrong default setting.
- The `X-Requested-With: XMLHttpRequest` header is no longer automatically sent by all clients and can be forged.
- User-Agent, Referer, Origin, and Sec-Fetch-* assist analysis but **are not authentication proof**.

Do not build a security boundary like this:

```java
// ANTI-PATTERN PSEUDOCODE: do not use to lower authentication checks
if (request.getHeader("Accept").contains("text/html")) {
    redirectToLogin();
} else {
    permitOrReturn401();
}
```

Whenever possible, **separate URLs by namespace** and ensure each namespace has an explicit entry point, authentication mechanism, and session policy: `/api/**` uses Bearer, `/web/**` uses form/session. Content negotiation can adjust **presentation** once policy is clear, never to let a weaker mechanism bypass access rules.

If a single URL must support both HTML navigation and APIs, a `DelegatingAuthenticationEntryPoint` with carefully designed/tested `RequestMatcher`s is needed, while keeping the **authentication requirement** identical regardless of response format. Simply switching 302/401 must never alter the authenticated principal/authorities.

## 7. Configuring Multiple SecurityFilterChains: A Reliable Pattern

A Spring Security Servlet application can declare multiple `SecurityFilterChain` beans. Spring Security evaluates them by `@Order` and uses **the first chain** whose `securityMatcher` matches the request.

```text
@Order(1): http.securityMatcher("/api/**")
  oauth2ResourceServer(jwt)
  stateless API, bearer challenge
  /api/private: SCOPE_api.read
  /api/admin:   SCOPE_admin.read
  others: denyAll

@Order(2): chain without securityMatcher
  formLogin
  /, /error: permitAll
  other web URLs: authenticated
  anonymous protected web request → 302 /login
```

**Differences to remember:**

- `securityMatcher("/api/**")` decides **which chain** handles the request.
- `requestMatchers("/api/private")` decides **permission rules** inside the API chain.
- `anyRequest()` covers only requests belonging to the current chain.
- Without a catch-all chain, URLs outside all matchers may remain unprotected by Spring Security.
- Endpoints created by filters, such as `GET /login` and `POST /login`, are also only available in the chain whose scope covers their URLs. Therefore, do not place the only form login inside the `/api/**` chain and expect `/login` to work outside that matcher.
- Do not enable `formLogin()` in a pure Bearer API chain if the API contract requires 401 and has no web session.

This separation also allows **CSRF/session** to be configured properly per client type: browser forms normally use sessions/cookies and CSRF protection; APIs using only bearer headers normally do not need CSRF for that credential model. Do not apply `csrf.disable()` app-wide just to fix a 403 in an API.

## 8. Spring Boot 3.x, Java 17+ Example: Web Redirect and API 401

Example running on Spring MVC/Servlet with Spring Boot 3.x + Spring Security 6.x, Java 17+. It includes a sample local user to try the web form and an OAuth2 Resource Server for the API. **The sample account is for local development only**; JWT tokens for the API must be issued by an external Authorization Server.

### 8.1. Dependencies

In a project with the Spring Boot Gradle plugin and dependency management, add the following `dependencies` block to `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

The JWT Resource Server uses the JOSE library provided by the starter. Only configure `spring-boot-starter-oauth2-client` if the application also needs to actively log in via OAuth2/OIDC or call external APIs; that is **different** from a Resource Server accepting Bearer tokens.

### 8.2. JWT Issuer, JWKS, and Audience

Create `src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${JWT_ISSUER}
          jwk-set-uri: ${JWT_JWK_SET_URI}
          audiences: ${JWT_AUDIENCE}
```

Starting in Spring Boot 3.x / Spring Security 6.5, JWT resource server configuration supports audience validation via the `audiences` property. For a specific version, check the active documentation/BOM. `issuer-uri` must match the `iss` claim, `audiences` must include the current API resource, and `jwk-set-uri` must be published by a **trusted** issuer. Do not take the JWKS URI from an HTTP request or an unverified token.

Illustrative environment variables:

```bash
export JWT_ISSUER='https://issuer.example.test'
export JWT_JWK_SET_URI='https://issuer.example.test/jwks'
export JWT_AUDIENCE='demo-api'
```

The `example.test` URL is not a running IdP; replace it with real configuration from your lab environment. Declaring `jwk-set-uri` avoids performing issuer discovery at startup in some configurations; verifying real tokens still requires a reachable JWKS and valid tokens. Never place the AS private signing key inside a resource server.

### 8.3. Main Application

All Java files under `src/main/java/com/example/responses/` in package `com.example.responses`.

**`ResponseApplication.java`**

```java
package com.example.responses;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResponseApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResponseApplication.class, args);
    }
}
```

### 8.4. SecurityConfig.java: Splitting Two Chains

**`SecurityConfig.java`**

```java
package com.example.responses;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/public")
                        .permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/private")
                        .hasAuthority("SCOPE_api.read")
                        .requestMatchers(HttpMethod.GET, "/api/admin")
                        .hasAuthority("SCOPE_admin.read")
                        .anyRequest().denyAll())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .oauth2ResourceServer(oauth -> oauth
                        .jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService localDemoUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("demo")
                        .password(encoder.encode("LocalOnly-ChangeMe!"))
                        .roles("USER")
                        .build());
    }
}
```

**Exact explanation of each line's role:**

1. The API chain has `@Order(1)` and `securityMatcher("/api/**")`, so requests to `/api/private` do not fall into the form login chain even with `Accept: text/html`. Only JWT Resource Server is enabled in this chain.
2. `oauth2ResourceServer(...jwt(...))` validates bearer access tokens; under default configuration, missing/invalid tokens on a protected API lead to **401 with a Bearer challenge**, not an HTML login redirect.
3. `SCOPE_api.read`/`SCOPE_admin.read` are authorities mapped from JWT scopes per Spring Security convention; endpoints are accessible only when the token is verified and carries the required authority.
4. `SessionCreationPolicy.STATELESS` clarifies that the API does not use web login sessions for auth. `csrf(...disable)` is safe only within the scope of **pure Bearer header-based APIs that do not use cookie authentication**; do not use on cookie-requiring endpoints.
5. The web chain has no dedicated `securityMatcher`, so it covers remaining URLs; `formLogin(...)` enables the default generated login page and form processing. Anonymous GET `/web/private` typically receives a 302 to `/login`.
6. `UserDetailsService` uses a **hardcoded local demo** account/password hashed with BCrypt. In production, use a proper user store, secret management, MFA/rate limiting, and never commit a usable password to a repo.
7. Do not merge `formLogin()` and `oauth2ResourceServer()` into one global chain hoping Spring guesses every request right; without clear entry point/policy declarations, behavior can depend on matchers, handlers, and content negotiation.
8. `permitAll()` on `/api/public` allows tokenless requests, yet if a client sends an **invalid** bearer token, the bearer authentication filter may still reject the request before authorization. It does not mean the endpoint must ignore bad tokens.

### 8.5. Illustrative Controller

**`DemoController.java`**

```java
package com.example.responses;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "Home: public";
    }

    @GetMapping("/web/private")
    public String webPrivate() {
        return "Web: signed in";
    }

    @GetMapping("/api/public")
    public String apiPublic() {
        return "API: public";
    }

    @GetMapping("/api/private")
    public String apiPrivate() {
        return "API: read permitted";
    }

    @GetMapping("/api/admin")
    public String apiAdmin() {
        return "API: admin permitted";
    }
}
```

The example uses plain text for easy observation, whereas production needs a JSON contract for APIs, proper HTML/templates for web, and domain authorization in services. Never return raw access tokens, passwords, or internal security context details in responses.

### 8.6. Expected Results

Run `./gradlew bootRun` (Windows PowerShell: `.\gradlew.bat bootRun`) after configuring environment variables and the appropriate Gradle wrapper.

```bash
curl -i http://localhost:8080/
curl -i http://localhost:8080/web/private
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/private
curl -i -H 'Accept: text/html' http://localhost:8080/api/private
```

Results **expected from the configuration**, not output captured from running against a real AS:

| Request | Expectation |
| --- | --- |
| `GET /` | 200, public content |
| `GET /web/private` anonymous | 302 redirect to `/login` |
| `GET /login` anonymous | 200, Spring Security generated login form |
| `GET /api/public` no token | 200 |
| `GET /api/private` no token | 401 + `WWW-Authenticate: Bearer` |
| `GET /api/private` with `Accept: text/html` but no token | Still 401, no HTML login redirect |
| `GET /api/private` valid token with scope `api.read` | 200 |
| `GET /api/admin` valid token with only `api.read` | 403 |
| `GET /api/admin` valid token with `admin.read` | 200 |

Do not use `curl -L` when directly inspecting a 302 response; `-L` follows redirects and may show only the response from `/login`. Never put real tokens into shell history, logs, or tickets; use a secure terminal and short-lived test tokens.

## 9. MockMvc: Testing 302, 401, and 403 Properly

With `spring-security-test` and `spring-boot-starter-test`, create `src/test/java/com/example/responses/ResponseSecurityTest.java`.

**`ResponseSecurityTest.java`**

```java
package com.example.responses;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.endsWith;
import static org.hamcrest.Matchers.startsWith;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "spring.security.oauth2.resourceserver.jwt.issuer-uri=https://issuer.example.test",
        "spring.security.oauth2.resourceserver.jwt.jwk-set-uri=https://issuer.example.test/jwks",
        "spring.security.oauth2.resourceserver.jwt.audiences=demo-api"
})
@AutoConfigureMockMvc
class ResponseSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousWebNavigationRedirectsToLogin() throws Exception {
        mvc.perform(get("/web/private").accept(MediaType.TEXT_HTML))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string(
                        HttpHeaders.LOCATION, endsWith("/login")));
    }

    @Test
    void anonymousApiReturnsBearer401EvenWithHtmlAccept() throws Exception {
        mvc.perform(get("/api/private").accept(MediaType.TEXT_HTML))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        HttpHeaders.WWW_AUTHENTICATE,
                        startsWith("Bearer")));
    }

    @Test
    void publicApiWorksWithoutToken() throws Exception {
        mvc.perform(get("/api/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("API: public"));
    }

    @Test
    void jwtWithReadScopeIsAccepted() throws Exception {
        mvc.perform(get("/api/private").with(jwt()
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_api.read"))))
                .andExpect(status().isOk())
                .andExpect(content().string("API: read permitted"));
    }

    @Test
    void authenticatedJwtWithoutAdminScopeGets403() throws Exception {
        mvc.perform(get("/api/admin").with(jwt()
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_api.read"))))
                .andExpect(status().isForbidden());
    }
}
```

Run `./gradlew test` or `.\gradlew.bat test`. Expected outcome: the five tests pass when placed in a Boot 3.x project following the example with matching dependencies and security config. These are **simulated tests** at the Spring MVC/security authorization level; this lesson does not claim they were executed in a live project here.

### 9.1. Why Does jwt() Not Test Signatures?

Spring Security Test's `jwt()` injects a mock `JwtAuthenticationToken` into the request. It can test security chain selection and authorization policy, **without validating** JWT signature, issuer, audience, expiration, `kid`, or key rotation.

Integration tests need real JWTs signed with a test key and a test JWKS endpoint, calling the API via `Authorization: Bearer ...` so `BearerTokenAuthenticationFilter`/`JwtDecoder` processes them. Cases to test: forged token, bad signature, wrong issuer/audience, expired, before `nbf`, missing scope, valid JWT issued for a different API.

### 9.2. Testing Real Web Login and Request Cache

To verify redirects and sessions:

- Anonymous GET `/web/private` → 302 `/login`; `GET /login` renders HTML page.
- Correct form login POST using MockMvc `formLogin()` (with CSRF test support) → authenticated session; reuse the same `MockHttpSession` on GET `/web/private`.
- Failed login POST → handler returns error URL per configuration, not confused with anonymous entry point.
- State-changing browser POST **without a CSRF token** → typically 403; not caused by a bad bearer JWT.
- After login, test saved request/back-navigation, session cookie, and logout.

The request cache should store only valid web requests. For APIs, do not create `SavedRequest` or route sensitive POST requests through the login page and replay them unintentionally. Especially test post-login: HTTP method, body, and CSRF of a pre-login action **must not** be replayed unsafely.

## 10. Customizing AuthenticationEntryPoint for APIs

If an API **does not use Bearer** (for example, an integration with its own JSON 401 contract), you can declare `HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)` or a JSON-returning entry point. However, if the API uses OAuth2 Bearer, replacing the entire entry point with a status-only 401 can **drop `WWW-Authenticate`**, preventing the client from receiving the standard challenge.

In Spring Security Servlet, the following code is only a **configuration snippet for a non-Bearer API chain**, not a standalone class:

```java
.exceptionHandling(errors -> errors
        .authenticationEntryPoint(
                new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
```

Imports:

```java
import org.springframework.http.HttpStatus;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
```

Do not add this snippet to the JWT resource server from section 8 and then claim it still emits a Bearer challenge. With Bearer tokens, it is best to keep the default `BearerTokenAuthenticationEntryPoint` or delegate to it when adding a JSON body.

### 10.1. Pattern for Returning JSON While Keeping the Bearer Challenge

If an API requires a consistent JSON body when a Bearer token is missing/invalid, design the entry point to **call BearerTokenAuthenticationEntryPoint first**, then append the body **only when the response is not yet committed**. The following illustrates this inside `SecurityConfig` on the API chain:

```java
var bearerEntryPoint = new BearerTokenAuthenticationEntryPoint();

http.exceptionHandling(errors -> errors
        .authenticationEntryPoint((request, response, exception) -> {
            bearerEntryPoint.commence(request, response, exception);
            if (!response.isCommitted()) {
                response.setHeader("Cache-Control", "no-store");
                response.setContentType("application/json;charset=UTF-8");
                response.getWriter().write(
                        "{\"error\":\"authentication_required\"}");
            }
        }));
```

Corresponding import: `org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint`. This is a **snippet placed inside HttpSecurity configuration**, and needs testing for missing token, bad token, and expired token together with `WWW-Authenticate`. Certain errors may be routed directly by the Resource Server filter to its own entry point depending on configuration, so for exact end-to-end requirements test the filter chain rather than just reading the snippet.

Never put exception messages containing tokens, internal issuer URLs, stack traces, or user information into JSON errors. If the app follows RFC 9457 Problem Details, you can return `application/problem+json` with a stable schema while preserving the appropriate status and challenge.

### 10.2. Should Error Codes Be Returned in the Body?

You can standardize:

```json
{
  "code": "AUTHENTICATION_REQUIRED",
  "message": "Valid access credentials are required"
}
```

For 403:

```json
{
  "code": "ACCESS_DENIED",
  "message": "You are not allowed to access this resource"
}
```

These are **application-defined illustrative bodies**, not Spring Security defaults. Clients should branch on HTTP status, not solely on the `code` string. Never return information revealing whether an account exists, how many wrong password attempts occurred, internal roles of other users, or token validation secrets.

## 11. RequestCache and the Risk of Redirect Loops

When an unauthenticated user hits a web page, `ExceptionTranslationFilter` can save the request via `RequestCache`. After login, the handler can redirect the user back to the requested URL.

Example:

```text
GET /web/private  ──────> not logged in
      │
      ├─ save SavedRequest (session)
      └─ 302 /login
                 │
                 ├─ GET /login: display form
                 └─ POST /login: verify password, CSRF, create session
                          │
                          └─ 302 /web/private
```

Points to protect:

- `GET /login` must be public in the **web chain**, otherwise the browser can enter an endless redirect loop to the login page itself.
- If using a custom `loginPage("/signin")`, **the application must create GET /signin itself** and permit access; without a controller/template, 404 or a loop will occur.
- Do not put API authentication failures into the web `RequestCache` and never redirect `/api/**` through the UI login URL.
- Prevent open redirects: allow return URLs / saved targets only from controlled sources/destinations. Never take an arbitrary attacker-supplied `returnTo` and redirect to an unknown domain.
- For browser sessions, check session fixation, Secure/HttpOnly/SameSite cookies, CSRF tokens, and logout. Behind a reverse proxy, configure trusted public scheme/host safely so `Location` is accurate.
- `RequestCache` may need tuning for special cases like SPA navigation, but never turn a non-idempotent API POST into an auto-replayed action after login.

## 12. Custom Login Page and Redirecting to an OIDC Provider

If using custom form login:

```java
.formLogin(form -> form
        .loginPage("/signin")
        .loginProcessingUrl("/signin")
        .permitAll())
```

This is a DSL snippet placed inside the **web SecurityFilterChain**; you must create the `GET /signin` page and a `POST /signin` form with a CSRF token. When using the default login page as in section 8, **you do not need to create a controller for `/login`**.

With OIDC/OAuth2 Login, the browser may be redirected to:

```text
/oauth2/authorization/<registrationId>
   → Authorization Server / Identity Provider
   → callback /login/oauth2/code/<registrationId>
   → application creates authenticated web session
```

This flow uses state/PKCE and provider-specific OIDC token validation, not just an arbitrary HTTP redirect. Even when browser login redirects to an IdP website, **the Bearer Resource Server API must still return 401** to clients missing a token, rather than redirecting API requests to the IdP and expecting an API client to complete browser interaction.

If a frontend SPA wants to initiate OIDC login, that is a **client/application workflow decision** after the API returns 401, not a hidden redirect from the API backend. Ensure Authorization Code with PKCE/nonce/state per architecture, valid redirect URIs, and never pass access tokens via arbitrary URLs.

## 13. CORS and CSRF: Two Error Types Often Confused with 401

### 13.1. CORS Preflight

A browser may send `OPTIONS /api/...` before a request carrying an Authorization header. If the API protects all OPTIONS requests with Bearer without proper CORS config, preflight can return 401 and the browser blocks the real request.

Configure `CorsConfigurationSource`/`http.cors(...)` properly for allowed origins, methods, and headers, handling preflight before security checks as designed. CORS **is not an authentication mechanism**; letting preflight pass does not allow reading protected resources without a Bearer token.

Never casually set `Access-Control-Allow-Origin: *` alongside credential cookies or let arbitrary origins control sessions. Use policies appropriate for browser APIs and test from real origins.

### 13.2. CSRF and HTTP 403

A web page using cookies/sessions may require a CSRF token for POST/PUT/DELETE. If a form POST or UI action lacks CSRF, Spring Security can return **403 Forbidden**, even when the user is logged in. This does not necessarily mean "user lacks a role". Never disable CSRF to turn the response into 302.

In the section 8 configuration example: CSRF is disabled **only in the API chain** because the API model is pure Bearer header and does not rely on auto-submitted cookies. The web chain keeps CSRF protection. If an API uses session cookies and bearer simultaneously, re-evaluate; do not disable by default.

### 13.3. HTTP Basic Challenge in the Browser

If `httpBasic()` is enabled on a web chain, the browser may pop up a username/password dialog due to the Basic challenge instead of redirecting to a login page, depending on negotiation and entry point. Therefore, the web example in this lesson **enables only formLogin**, while the API example **enables only Resource Server JWT**. Do not enable multiple entry points without defining which client belongs to which route.

## 14. When to Return 401 and When to Return 403?

Decision matrix by authentication and permission state:

| Request State | Web Navigation | Bearer API |
| --- | --- | --- |
| No credentials for protected resource | Usually 302 to login | 401, Bearer challenge |
| Invalid credentials provided | Web login failure handler or entry point | 401, possibly `invalid_token` |
| Valid credentials, lacking authority | Usually 403 or custom access denied UI | Usually 403, possibly `insufficient_scope` |
| Valid credentials, sufficient scope, wrong tenant/ownership | Must deny per domain policy | Must deny; status determined by policy/resource hiding |
| Form POST missing CSRF | Usually 403 due to CSRF | Not applicable if pure Bearer-header API configured properly |
| Accessing public endpoint | 200/3xx per business logic | 2xx if valid endpoint; bad token may still be rejected by auth filter |

For an API that does not want to reveal whether a resource exists, some policies may choose 404 instead of 403 where appropriate. This is an **API contract** decision, not a reason to skip authn/authz.

**Do not use 401 for everything**: it causes clients to refresh/re-login endlessly and masks scope/tenant errors. **Do not return 200 with JSON `{error:401}`**: it breaks HTTP semantics, caches/metrics/monitoring, and complicates SDK handling.

## 15. How Should the Frontend Handle 401 Properly?

An SPA calling an API via JavaScript might look like:

```javascript
async function fetchProfile() {
  const response = await fetch("/api/private", {
    headers: {
      Accept: "application/json",
      Authorization: "Bearer " + getAccessTokenSafely()
    }
  });

  if (response.status === 401) {
    // Do not loop infinitely. Use the designed renewal/login flow.
    showAuthenticationRequired();
    return;
  }
  if (response.status === 403) {
    showInsufficientPermissions();
    return;
  }
  if (!response.ok) {
    showGenericError();
    return;
  }
  const text = await response.text();
  showProfile(text);
}
```

The `getAccessTokenSafely()`/`show...()` functions are **application functions, not built into JavaScript**; this is an illustrative snippet for handling HTTP statuses, not a standalone JS file. The app must choose secure token storage/flows; avoid storing long-lived access tokens where XSS can easily steal them.

**UX notes:**

- On 401, trigger strictly **one** refresh/login flow (single-flight), never refresh infinitely.
- On 403, explain the missing permission and avoid logging the user out when the token is still valid.
- Do not unintentionally follow HTML redirects and parse the login page as JSON.
- If the backend returns 429/503, apply backoff and show an appropriate message instead of treating it as "token expired".
- Never redirect the browser to an untrusted URL from a response; avoid open redirects and token leaks via query/referrer.

## 16. Common Failure Modes and Fixes

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| `fetch("/api/...")` gets HTML login instead of JSON/401 | API falls into formLogin chain or gets 302 redirected | Isolate `/api/**` into a Resource Server chain and verify 401 |
| API called via curl returns 302 | `LoginUrlAuthenticationEntryPoint` applied to API | Pick entry point matching the API contract |
| Browser opening web page only sees 401 JSON | Web chain uses HttpStatusEntryPoint/Bearer | Enable formLogin/OIDC redirect for web navigation |
| API missing bearer header returns 403 | Custom AccessDeniedHandler or wrong CSRF/matcher | Inspect exception type, entry point, CSRF, and chain |
| Valid token lacking permission returns 401 | Catch-all auth failure/handler confuses authz | Keep authentication separate, return 403/insufficient_scope |
| 401 without `WWW-Authenticate` | Replaced Bearer entry point with HttpStatusEntryPoint | Keep Bearer challenge via delegation |
| Form POST wrong password ignores custom entry point | `AuthenticationFailureHandler` handles form login failures | Customize failure handler in the right place |
| `GET /login` returns 404 | Form login sits in a chain not matching `/login` or custom page missing | Fix chain/matcher and controller/template |
| Login page redirect loop | `/login` is not public or caught by another rule | Permit login endpoints, check chain ordering |
| API expired token repeatedly 302s to IdP | Using `oauth2Login()` instead of Resource Server | API returns 401; client coordinates login when appropriate |
| CORS preflight gets 401 | OPTIONS not handled properly by CORS | Configure CORS preflight before auth |
| 403 on web POST despite being authenticated | Missing CSRF token or policy denial | Add CSRF properly, do not disable recklessly |
| Using `Accept` to allow a weaker flow | Header is client-controlled, wrong trust boundary | Enforce security policy by route/credential |
| URL outside every `SecurityFilterChain` | No catch-all chain | Add chain covering all expected requests |
| "Public" API rejects request with bad token | Bearer filter checks bad token before `permitAll()` | Have client omit bad token, or clarify route/chain design |
| Proxy generates HTTP redirect instead of HTTPS | Host/scheme forwarding untrusted/misconfigured | Configure trusted proxy, public URL/forward headers |
| MockMvc `jwt()` test passes yet forged JWTs also get accepted | Test bypasses real decoder | Integration-test signed JWT/JWKS |

Do not fix every failure with global `permitAll()` or `csrf.disable()`. Making an unauthenticated API "return 200" does not solve a response issue—it introduces a vulnerability.

## 17. Matrix-Based Regression Testing

Beyond the five sample tests, a solid suite should cover:

1. Anonymous web `GET /web/private` → `302 Location /login`; anonymous `GET /login` → 200 form.
2. Anonymous API `GET /api/private` → 401 + `WWW-Authenticate: Bearer` with `Accept: application/json` **and** `Accept: text/html`.
3. API bearer token with wrong signature/issuer/audience/exp → 401; must not fall into web chain.
4. Valid API token missing `SCOPE_admin.read` → 403; user is not logged out needlessly.
5. Valid API token with scope → 200; browser session cookie does **not** automatically grant access to the resource server.
6. Successful browser login with CSRF and session → accesses `/web/private`; form login failure goes through failure handler.
7. Web POST missing CSRF → 403; API Bearer POST follows its own policy without disabling web CSRF.
8. Browser accessing API with `Accept: text/html` → still 401 (route matters more than header).
9. Valid CORS OPTIONS → preflight handled properly, while business GET/POST still require a token.
10. URIs outside `/api/**` hit web catch-all without escaping Spring Security; login/logout endpoints sit in the right chain.
11. Redirects through HTTPS reverse proxy, saved requests, and return targets cause no open redirect/loop.
12. Redirect-following clients / SPA SDKs receive accurate HTTP statuses, never reporting 200 after accidentally fetching login HTML.

When testing with `curl`, use `-i` to view status and headers; avoid `-L` when observing the original 302. With MockMvc, assert status, Location, and WWW-Authenticate separately; never assert an HTML body in place of header semantics.

## 18. Operations and Security

- **Define the contract clearly:** which resources return HTML redirects, which return JSON/Bearer 401, which URLs are public, which login paths exist, and which scopes apply.
- **Keep response statuses accurate:** logging/metrics categorizing 302, 401, 403, 429, and 5xx; detect login loops or spikes in invalid tokens.
- **Prevent token/session leaks:** use HTTPS, never place Bearer tokens in URLs, query strings, logs, or Location headers. Verify CORS, referrer policy, and cookie flags.
- **Do not leak failure details:** authentication failure bodies must not contain passwords, tokens, account existence, stack traces, signing keys, or sensitive role info.
- **Do not use HTML redirects for APIs:** clients cannot interact with a login form from a JSON request, easily leading to 302→200 HTML that breaks parsers/SDKs.
- **Do not use 401 for all permissions:** authenticated but lacking scope/tenant belongs to authorization; enforce policy and 403 per contract.
- **Do not drop CSRF on web sessions:** partition chains by exact credential type and test POST as well as GET.
- **Maintain trust in forwarded headers:** the reverse proxy must sanitize client headers, and the backend must trust only defined proxies.
- **Enforce authn/authz on the backend:** choosing 302/401 is the communication layer; it does not protect data if endpoints bypass filters or rely only on frontend checks.

## 19. Self-Check Questions

1. Why is HTTP 302 suitable for top-level browser navigation yet problematic when a `fetch` client expects JSON? Give an example of a 302 followed to HTML 200.
2. Why should an API resource missing a bearer token use 401 and `WWW-Authenticate: Bearer` instead of just returning 302 `Location: /login`?
3. When a JWT is valid yet lacks a scope, why is the response normally 403 rather than 401? What differs if the JWT is expired?
4. What distinct situations do `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, `AccessDeniedHandler`, and `AuthenticationFailureHandler` address?
5. Why is `securityMatcher("/api/**")` different from `requestMatchers("/api/private")`? What happens if no chain covers the remaining URLs?
6. An SPA sends `Accept: text/html` to `/api/profile`. Should it be redirected to login? Why should auth policy not be chosen solely by `Accept`?
7. If a custom API entry point returns JSON 401 yet removes `WWW-Authenticate`, what can go wrong for an OAuth2 Bearer client?
8. Design a test ensuring a web POST CSRF 403 is not confused with an API missing-Bearer 401.
9. With OIDC login, why can the browser redirect to the IdP while the API Resource Server should still return 401?
10. When an app runs behind a reverse proxy, what risks arise from Location headers, Host forwarding, and saved requests?

## 20. Summary and References

- **302 + Location**: typically used to send unauthenticated **browser navigation** to a login page. This is the UX of web apps using form/session or OIDC login.
- **401 + WWW-Authenticate**: appropriate for asking **API clients** to supply credentials under the API's scheme, e.g. `Bearer`. Never return HTML login instead of a challenge.
- **403**: typically used when authenticated yet not authorized; should not trigger a login loop.
- **AuthenticationEntryPoint** decides how to begin authentication; **AccessDeniedHandler** handles denied permissions; **AuthenticationFailureHandler** handles failed login submissions.
- Separate `/api/**` and web pages into `SecurityFilterChain` beans with clear matchers/order, proper session/CSRF policies, and a catch-all protecting remaining URLs.
- Headers like `Accept`, `User-Agent`, or `X-Requested-With` are not authentication proof; do not use them to relax protection rules.
- Test both status **and headers** (Location, WWW-Authenticate) across browsers, API clients, valid/invalid tokens, and insufficient-permission cases.

**Official references:**

- [Spring Security 6.5 – Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 – Java Configuration and Multiple HttpSecurity](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 – OAuth2 Resource Server Bearer Tokens](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security 6.5 – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security – Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security 6.5 – ExceptionTranslationFilter Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html)
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 6750 – OAuth2 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)