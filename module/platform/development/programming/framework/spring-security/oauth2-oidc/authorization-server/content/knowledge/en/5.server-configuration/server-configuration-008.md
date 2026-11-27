# Configuring the Login Entry Point and Handling Unauthenticated Requests

> **Chapter:** Server Configuration  
> **Scope:** Designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in a Spring Boot application.  
> **Focus:** Deciding when to redirect the browser to the login page, when to return OAuth2/OIDC protocol errors or HTTP 401/403, and configuring `SecurityFilterChain` beans so unauthenticated requests are handled properly.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the roles of `AuthenticationEntryPoint`, `ExceptionTranslationFilter`, and `AccessDeniedHandler` in Spring Security.
2. Distinguish between an **unauthenticated user** at the authorization endpoint and a **failed client authentication** at the token endpoint.
3. Configure one `SecurityFilterChain` for Spring Authorization Server endpoints and another chain for form login.
4. Choose `302 /login` redirects for interactive HTML requests while preserving appropriate error responses for APIs, token endpoints, and Bearer tokens.
5. Understand the relationship among `SavedRequest`, HTTP sessions, request cache, CSRF, cookies, and the Authorization Code + PKCE flow.
6. Test unauthenticated scenarios, insufficient permissions, OAuth2 errors, and misconfigurations that lead to redirect loops.

This lesson uses Servlet stack examples from Spring Boot, Spring Security 6.x, and Spring Authorization Server 1.x, with the `HttpSecurity.with(...)` configuration API. When using the Spring Security 7.x generation with integrated Authorization Server, verify dependency names, packages, and APIs in the matching version's documentation; the principles regarding entry points and request boundaries remain valid.

## 2. The Problem: "Unauthenticated" Does Not Always Share One Response

An Authorization Server must handle multiple request types with different expectations:

- A user visits `GET /oauth2/authorize` in a browser. If not logged in, they are normally **redirected to the login page** and then returned to continue the authorization request.
- An OAuth2 client calls `POST /oauth2/token` over HTTP. If client credentials are wrong, it needs an **explicit OAuth2 error**; you cannot return an HTML login page and treat that as valid handling.
- A Resource Server receives `GET /api/orders` without a Bearer token. The standard response is **HTTP 401** with a `WWW-Authenticate: Bearer` challenge, not a redirect to the Authorization Server's login page.
- A logged-in user is denied access to an administrative feature. That is usually **HTTP 403** or an appropriate access-denied page; asking them to log in again will not solve missing permissions.
- A user denies consent at the authorization endpoint. That is an **OAuth2 authorization error** handled according to protocol redirect/error response rules, not simply "user not logged in."

Therefore, the architecture must clearly separate **where authentication happens**, **where authorization happens**, and **the response format**.

| Scenario | Involved actor | Common expected response |
| --- | --- | --- |
| Valid authorization request, user has no login session | Resource Owner | `302` redirect to `/login` in browser flow |
| User submits wrong credentials on login form | Resource Owner | Redirect back to `/login?error` or configured error view |
| Invalid client authentication at token endpoint | OAuth2 Client | Protocol `invalid_client` error; typically HTTP `401` with appropriate challenge |
| Wrong/expired authorization code or PKCE mismatch | OAuth2 Client | `invalid_grant` error, typically HTTP `400` |
| Invalid authorization request | OAuth2 Client | `invalid_request` or corresponding OAuth2 error; redirect only when safe and protocol-valid |
| API missing Bearer token | API caller | HTTP `401` with Bearer challenge per Resource Server |
| Authenticated principal lacks sufficient authority | User or Client | HTTP `403` or protocol/context-appropriate error response |
| Resource Owner denies consent | Resource Owner | OAuth2 `access_denied` error handled per authorization response rules |

Codes in the table reflect **typical contextual behavior**; concrete filters, custom handlers, and RFC requirements determine the final response. In particular, **never automatically redirect to a `redirect_uri` supplied by an invalid request** before validating the client and redirect URI.

## 3. What Does `AuthenticationEntryPoint` Do?

In Spring Security Servlet, `AuthenticationEntryPoint` is the interface that defines how to **commence authentication** when a request requires login yet currently lacks an appropriate `Authentication`.

~~~java
public interface AuthenticationEntryPoint {
    void commence(
        HttpServletRequest request,
        HttpServletResponse response,
        AuthenticationException authException
    ) throws IOException, ServletException;
}
~~~

Meaning of the parameters:

- `request`: the intercepted HTTP request.
- `response`: object used to emit a redirect, status code, or challenge.
- `authException`: the reason authentication must be initiated.

Key implementations to remember:

| Entry point | Behavior | When appropriate |
| --- | --- | --- |
| `LoginUrlAuthenticationEntryPoint` | Returns a redirect to the configured login URL | HTML pages and authorization endpoints requiring user interaction |
| `HttpStatusEntryPoint` | Returns a fixed HTTP status, e.g. 401 | APIs not using Bearer challenges, depending on policy |
| `BearerTokenAuthenticationEntryPoint` | Responds with a Bearer authentication challenge | OAuth2 Resource Server receiving requests without valid Bearer authentication |
| `BasicAuthenticationEntryPoint` | Returns an HTTP Basic challenge | APIs actually using HTTP Basic; not a universal default for every token endpoint |
| `RequestMatcherDelegatingAuthenticationEntryPoint` | Selects an entry point based on a matcher | Separating HTML requests from other request groups within the same context |

**An entry point is not an HTML page.** It is an **HTTP response behavior**. `LoginUrlAuthenticationEntryPoint("/login")` only sends the browser to `/login`; rendering the page and handling login POST submissions still require configuration in the appropriate filter chain.

### 3.1. How Does an Entry Point Differ from an Authentication Filter?

For example:

- `UsernamePasswordAuthenticationFilter` receives a POST with username/password and attempts authentication.
- `ExceptionTranslationFilter` catches certain authentication/authorization exceptions inside the wrapped chain portion and decides whether to commence authentication or handle denial.
- `AuthenticationEntryPoint` performs the "commence authentication" step requested by `ExceptionTranslationFilter`.
- Form login's `AuthenticationFailureHandler` handles a **submitted login attempt that failed**.
- `AccessDeniedHandler` handles **access denied** when restarting login is not appropriate.

Therefore:

- `GET /oauth2/authorize` while not logged in → usually invokes the entry point leading to login.
- `POST /login` with wrong password → usually invokes form login's **failure handler**.
- Logged-in user lacking admin page authority → usually handled by the **access denied handler**.

### 3.2. `AuthenticationException` and `AccessDeniedException`

Simplified decision flowchart:

~~~mermaid
flowchart TD
    A["Request enters SecurityFilterChain"]
    B{"Exception to translate into security response?"}
    C["Continue to handler / endpoint"]
    D{"AuthenticationException?"}
    E["AuthenticationEntryPoint"]
    F{"AccessDeniedException?"}
    G{"Anonymous or remember-me<br/>insufficient trust level?"}
    H["AuthenticationEntryPoint"]
    I["AccessDeniedHandler"]
    J["Response handled by other filter/protocol"]

    A --> B
    B -->|"No"| C
    B -->|"Yes"| D
    D -->|"Yes"| E
    D -->|"No"| F
    F -->|"Yes"| G
    F -->|"No"| J
    G -->|"Yes"| H
    G -->|"No"| I
~~~

In practice, `ExceptionTranslationFilter` uses `AuthenticationTrustResolver` to detect anonymous/remember-me tokens and may use `RequestCache` when commencing authentication. Individual Spring Authorization Server endpoints also have **OAuth2/OIDC-specific filters and exception handlers**; not every error passes through the diagram above.

Do not write manual checks relying solely on `authentication.isAuthenticated()` to replace these mechanisms: `AnonymousAuthenticationToken` can report an authenticated flag at the object level even though no real user has logged in.

## 4. Designing Two SecurityFilterChains for the Authorization Server

A standard Spring Authorization Server configuration separates:

1. **Authorization Server chain**: applies only to OAuth2/OIDC endpoints such as `/oauth2/authorize`, `/oauth2/token`, metadata, JWK Set, and enabled endpoints.
2. **Application/login chain**: serves `/login` and other web application requests, configuring form login or the Resource Owner login mechanism.

They are chosen by `securityMatcher` and `@Order`. **A request is processed by the first filter chain that matches it**, rather than passing sequentially through every chain.

~~~mermaid
flowchart TD
    R["HTTP request arrives at Spring Boot"]
    S{"Matches Authorization Server<br/>endpointsMatcher?"}
    AS["Chain @Order(1)<br/>OAuth2/OIDC endpoint filters"]
    W["Chain @Order(2)<br/>Form login and web app"]
    U{"/oauth2/authorize request<br/>needs user login?"}
    L["LoginUrlAuthenticationEntryPoint<br/>Redirect /login"]
    T["Token / metadata / OAuth2 endpoint<br/>Handled by matching filters and RFCs"]
    LF["GET /login<br/>Form login page"]
    AUTH["POST /login<br/>Performs authentication"]
    X["Authorization Code/consent continues"]

    R --> S
    S -->|"Yes"| AS
    S -->|"No"| W
    AS --> U
    U -->|"Yes, HTML request"| L
    U -->|"No or other endpoint"| T
    L --> LF
    LF --> AUTH
    AUTH --> X
~~~

### 4.1. Sample Configuration for Spring Security 6 and Spring Authorization Server 1.x

Assume the Spring Boot project already has Authorization Server, Spring Security, Spring Web dependencies, and required AS beans (registered clients, authorization/consent services, key management, user authentication). The snippet below **focuses on the two filter chains**; it is not sufficient by itself to run a complete production Authorization Server.

~~~java
@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http) throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server ->
                server.oidc(Customizer.withDefaults())
            )
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated()
            )
            .exceptionHandling(exceptions ->
                exceptions.defaultAuthenticationEntryPointFor(
                    new LoginUrlAuthenticationEntryPoint("/login"),
                    new MediaTypeRequestMatcher(MediaType.TEXT_HTML)
                )
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurityFilterChain(
            HttpSecurity http) throws Exception {

        http
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Key imports (the IDE can supply them):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.util.matcher.MediaTypeRequestMatcher;
~~~

Explanation of each meaningful configuration line:

| Component | Purpose |
| --- | --- |
| `@Order(1)` | Prioritizes the AS-dedicated chain ahead of the general chain |
| `authorizationServer.getEndpointsMatcher()` | Scopes requests to protocol endpoints configured by the AS |
| `with(authorizationServer, ...)` | Applies Spring Authorization Server filters/handlers |
| `server.oidc(Customizer.withDefaults())` | Enables OIDC support per the corresponding configuration |
| `anyRequest().authenticated()` | Requires authentication for matched endpoints, with OAuth2 filters handling protocol specifics |
| `defaultAuthenticationEntryPointFor(...)` | Assigns the login redirect for requests matching the HTML media type matcher |
| `new LoginUrlAuthenticationEntryPoint("/login")` | Target address to begin interactive Resource Owner login |
| `@Order(2)` + `formLogin(...)` | Configures login on the general chain, where `/login` is outside the AS endpoints matcher |

When no custom login page is configured, `formLogin(Customizer.withDefaults())` provides a **default login page generated by Spring Security**. To use a custom page, create the page and configure `loginPage("/login")` on the application chain as shown later.

**Example limitation:** using `MediaTypeRequestMatcher(MediaType.TEXT_HTML)` is an entry-point selection strategy for HTML browser flows, not a universal handler for all OAuth2 errors. `/oauth2/token`, token introspection, revocation, metadata, and OIDC endpoints have dedicated handling; never add a blanket login redirect to every request merely because it is unauthenticated.

### 4.2. Why Is `/login` Not Placed in the Authorization Server Chain?

`authorizationServer.getEndpointsMatcher()` targets protocol endpoints, whereas `/login` serves interactive user login in the application.

Putting both on a single filter chain or using an overly broad matcher can cause:

- `GET /login` itself requiring authentication, creating an infinite redirect back to `/login`.
- The OAuth2 token endpoint returning an HTML login page instead of an OAuth2 error.
- Browser interactions and HTTP APIs mixing session, CSRF, and error-response policies.
- Difficulty determining which filter owns request handling at each endpoint.

Always verify **exact matchers** and **chain order**, rather than looking solely at the `formLogin()` call.

## 5. Unauthenticated Request Flow at the Authorization Endpoint

A Client using Authorization Code + PKCE directs the browser to the AS:

~~~http
GET /oauth2/authorize?response_type=code&client_id=booking-web&redirect_uri=https%3A%2F%2Fclient.example.test%2Fcallback&scope=openid%20profile&state=state-random&code_challenge=valid-pkce-challenge&code_challenge_method=S256 HTTP/1.1
Host: auth.example.test
Accept: text/html
~~~

The `state` and `code_challenge` values in the example are **format illustrations**, not valid random/PKCE values for direct use. In real applications, the client must generate an unpredictable `state`, a high-entropy `code_verifier`, and compute `code_challenge` via S256; the AS must register and strictly validate `redirect_uri`.

### 5.1. Processing Steps

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Resource Owner
    participant B as Browser
    participant AS as Authorization Server chain
    participant RC as RequestCache/Session
    participant LOGIN as Login chain
    participant STORE as Authorization/Consent services
    participant C as OAuth2 Client

    U->>B: Click "Sign in to grant access"
    C-->>B: Redirect to /oauth2/authorize
    B->>AS: GET /oauth2/authorize (Accept: text/html)
    AS->>AS: Validate OAuth2 request, detect unauthenticated user
    AS->>RC: Save original request when cache is enabled
    AS-->>B: 302 Location: /login
    B->>LOGIN: GET /login
    LOGIN-->>B: 200 login page
    U->>B: Enter username/password
    B->>LOGIN: POST /login + CSRF token
    LOGIN->>LOGIN: Authentication succeeds
    LOGIN->>RC: Save SecurityContext/session per configuration
    LOGIN-->>B: Redirect to saved request
    B->>AS: GET /oauth2/authorize (now with session)
    AS->>STORE: Check client, consent, grant
    opt Consent required
        AS-->>B: Display consent
        U->>B: Approve
        B->>AS: Submit consent decision
    end
    AS-->>B: Redirect to valid redirect_uri + code + state
    B->>C: Callback with authorization code
~~~

The diagram is a **logical model**. The request cache and success handler only restore the original URL if configured and working properly; customized flows may use different request persistence or authorization completion mechanisms. The AS must never issue a code before satisfying the flow's authentication/consent requirements.

### 5.2. What Do `RequestCache` and `SavedRequest` Provide?

When a request arrives at a resource requiring login, `ExceptionTranslationFilter` can save the original request via `RequestCache` (e.g., `HttpSessionRequestCache`) before invoking the entry point. After successful login, an appropriate success handler can redirect the browser back to the saved request.

Related components:

- `RequestCache`: abstraction for storing/retrieving an HTTP request to resume.
- `HttpSessionRequestCache`: standard implementation storing the request in the HTTP session.
- `SavedRequest`: record of the original request (URL, parameters, and required attributes).
- `SavedRequestAwareAuthenticationSuccessHandler`: can prioritize redirecting back to the saved request after login succeeds.

This prevents users from landing on the home page after login and abandoning the authorization request carrying `client_id`, `scope`, `state`, `redirect_uri`, and PKCE challenge.

**Never treat `SavedRequest` as an authorization grant.** It only aids browser navigation, unlike OAuth2 state persisted via `OAuth2AuthorizationService`. Nor does the request cache replace validating client, redirect URI, scope, state, or PKCE.

### 5.3. Never Trust Callback URLs from Client-Supplied Parameters Blindly

`LoginUrlAuthenticationEntryPoint("/login")` sends the user to an **internal** login page. The OAuth2 callback path is `redirect_uri` registered by the Client and validated by the AS; the two URLs are not synonymous.

Never implement something like:

~~~java
// UNSAFE: directly redirects to the URL supplied by the request.
response.sendRedirect(request.getParameter("redirect_uri"));
~~~

Instead, let Spring Authorization Server verify client registration, redirect URI, and construct the standards-compliant authorization response. If a request is invalid, the AS must reject it or return an error as appropriate; never allow unauthenticated requests to become an **open redirect** vulnerability.

## 6. Customizing the Login Page and Entry Point

### 6.1. Default Login Page vs. Custom Login

With `formLogin(Customizer.withDefaults())`, Spring Security can generate a simple login page for development. When you want a branded UI, such as Thymeleaf, implement `GET /login` yourself and tell the form login filter the login URL.

~~~java
@Bean
@Order(2)
SecurityFilterChain applicationSecurityFilterChain(
        HttpSecurity http) throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/login", "/assets/**").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(form -> form
            .loginPage("/login")
            .permitAll()
        );

    return http.build();
}
~~~

A controller returning the `login.html` template:

~~~java
@Controller
class LoginPageController {

    @GetMapping("/login")
    String login() {
        return "login";
    }
}
~~~

For a Thymeleaf view, you can use an illustrative form:

~~~html
<form th:action="@{/login}" method="post">
    <label>
        Username
        <input name="username" autocomplete="username" required>
    </label>
    <label>
        Password
        <input type="password" name="password"
               autocomplete="current-password" required>
    </label>
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">
    <button type="submit">Sign in</button>
</form>
~~~

In the form, the hidden `_csrf` field is populated from the server-provided token. Depending on Thymeleaf/Spring Security integration, the framework may also auto-insert the CSRF token when rendering forms. What matters is that the POST login request carries the matching token **when CSRF protection is enabled**.

**Distinguishing URLs:**

| URL | Who handles it? | Role |
| --- | --- | --- |
| `GET /login` | Controller or default login page | Renders UI |
| `POST /login` | `UsernamePasswordAuthenticationFilter` in default setup | Authenticates credentials |
| `GET /oauth2/authorize` | AS authorization endpoint | Receives authorization request and prompts login if needed |
| `POST /oauth2/token` | AS token endpoint + client authentication | Accepts grant to issue tokens; never renders a login form |

If you change `loginPage("/sign-in")` or `loginProcessingUrl("/sign-in")`, update the entry point, GET controller, HTML form action, exception handling, and permit-all rules in sync.

### 6.2. Redirect Only HTML Requests; Preserve Protocol Semantics

In the AS chain we had:

~~~java
.exceptionHandling(exceptions ->
    exceptions.defaultAuthenticationEntryPointFor(
        new LoginUrlAuthenticationEntryPoint("/login"),
        new MediaTypeRequestMatcher(MediaType.TEXT_HTML)
    )
)
~~~

The crux is the **matcher**. It selects the login entry point for request types representing interactive user sessions. Understand its limits:

- `Accept: text/html` is an HTTP content-negotiation signal; it does not guarantee every request comes from a real browser.
- Some clients send `Accept: */*`; test the behavior of your specific Spring Security version instead of assuming every client is HTML.
- `Content-Type` describes the request body and **does not substitute for `Accept`** when choosing the response format.
- Do not force every request hitting the AS to redirect to login. OAuth2/OIDC filters must be able to emit standards-compliant responses for `invalid_client`, `invalid_grant`, and other protocol errors.
- If stricter separation between browser flows and API flows is required, design matchers by path, HTTP method, and media type, and choose entry points per policy; test against real endpoints.

In Spring Security, `defaultAuthenticationEntryPointFor` registers a matcher-based choice. It does not turn all exceptions into HTTP 302, nor does it guarantee 401 fallback responses for non-matching requests. Remaining behavior depends on the configurer and request-handling filters; verify via tests.

### 6.3. Dedicated API Handling When the Same App Exposes REST Endpoints

If the same application acts as both AS and protected API, declare a chain for the API **before** the default web chain. Example of an API using JWT Resource Server:

~~~java
@Bean
@Order(2)
SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
        throws Exception {

    http
        .securityMatcher("/api/**")
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .oauth2ResourceServer(resourceServer ->
            resourceServer.jwt(Customizer.withDefaults()));

    return http.build();
}

@Bean
@Order(3)
SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
        throws Exception {
    http
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults());
    return http.build();
}
~~~

This **replaces** the `@Order(2)` application chain from the previous example with two chains: API `@Order(2)` and web `@Order(3)`. Do not declare duplicate beans from both examples in the same configuration. Add imports for `SessionCreationPolicy` and JWT decoder/issuer configuration, while ensuring the AS issues access tokens intended for that API.

When a token is missing on `/api/**`, the Resource Server uses Bearer authentication to return the appropriate 401/challenge. Never let REST APIs accidentally match a chain with `formLogin()` and receive an HTML redirect.

## 7. 401, 403, Redirects, and Protocol Errors: Choosing the Right Handler

### 7.1. HTTP 401 Typically Means Authentication Is Required

`401 Unauthorized` has a misleading name, but in practice means **missing or invalid authentication credentials** for the resource, typically paired with `WWW-Authenticate`.

Resource Server example:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Distinguish clearly:

- Missing/invalid Bearer access token → Resource Server returns a Bearer challenge.
- Failed HTTP Basic client authentication at the token endpoint → AS generates an `invalid_client` error, potentially with an appropriate HTTP authentication challenge.
- Browser not logged in at the authorization endpoint → normally returns `302` redirect to form login for user interaction.

### 7.2. HTTP 403 Typically Means Authenticated Yet Denied

For example, a validly logged-in user attempts to open a restricted admin endpoint:

~~~http
HTTP/1.1 403 Forbidden
~~~

On a Resource Server, if the Bearer token is valid yet lacks the required scope, it can return `403` with `insufficient_scope` depending on configuration and specification details. If a user denies consent, the AS handles it with an **authorization error response**, not necessarily a direct 403.

### 7.3. The Token Endpoint Needs Standards-Compliant OAuth2 Errors

Common examples:

| Error at token endpoint | OAuth2 error | Typical HTTP status | Handled by |
| --- | --- | --- | --- |
| Client authentication failed | `invalid_client` | 401 or per applicable RFC rules | AS client authentication filter and error response |
| Authorization code wrong/expired/reused | `invalid_grant` | 400 | Token endpoint rejects grant |
| PKCE `code_verifier` mismatch | `invalid_grant` | 400 | Code's PKCE binding check |
| Unsupported grant type | `unsupported_grant_type` | 400 | Token endpoint |
| Missing or malformed grant parameter | `invalid_request` | 400 | Token endpoint |

A programmatic HTTP request encountering an error at the token endpoint **cannot be rescued by opening `/login`**. The OAuth2 client must read the HTTP status and error JSON response to decide whether to stop, fix its configuration, or initiate a new authorization flow if valid.

### 7.4. Do Not Write One Global Handler Redirecting Every Exception to Login

Anti-pattern:

~~~java
// Misused: turns every authentication/authorization error into a redirect.
.exceptionHandling(exceptions ->
    exceptions.authenticationEntryPoint(
        new LoginUrlAuthenticationEntryPoint("/login")
    )
)
~~~

Slapping this setting onto a chain handling browsers, token endpoints, and APIs can cause machine clients to receive unexpected HTML/302 responses. Explicitly define which request group may redirect. On OAuth2 endpoints, preserve Spring Authorization Server's protocol handlers and semantics.

## 8. Request Cache, Sessions, and CSRF in the Login Flow

### 8.1. Sessions Are a Legitimate Part of Browser Login

At the authorization endpoint, users normally log in through a browser, authenticate, and proceed to consent. An HTTP session can hold login state and the original request; the session cookie brings the browser back into the flow.

At the token endpoint, the client authenticates via its registered method and presents an authorization code/PKCE or another grant. It **does not need the Resource Owner's login cookie** to exchange the code. The necessary authorization grant state is already persisted on the AS side.

Do not blindly apply `SessionCreationPolicy.STATELESS` across the entire AS application if browser login/consent still depends on sessions. Conversely, a REST Resource Server using Bearer tokens can remain stateless as in the API chain example.

### 8.2. CSRF Must Be Handled Per Endpoint

Browsers send session cookies automatically, so state-changing requests such as `POST /login` and consent submissions need proper CSRF protection. Spring Authorization Server configures protocol endpoints according to protocol semantics; the application chain still needs CSRF protection for form login and web actions.

**Never fix a 403 on POST login by disabling CSRF for the entire application**:

~~~java
// Avoid applying indiscriminately to login and consent pages:
http.csrf(csrf -> csrf.disable());
~~~

Instead:

1. Verify the form actually sends the `_csrf` token or that the framework's integration supplies it properly.
2. Confirm the field/header name, session/cookie, and CSRF token lifetime for your chosen mechanism.
3. Exempt CSRF only on endpoints justified by protocol/authentication mechanics, within a narrow, reviewed matcher.
4. Run tests for both successful POST login/consent and rejection when the token is missing.

### 8.3. Protecting Sessions and Redirects Behind a Reverse Proxy

In production:

- Use HTTPS on public endpoints; session cookies should set `Secure` and `HttpOnly`, with a `SameSite` policy suited to browser/redirect flows.
- Configure a stable issuer URL (typically HTTPS) and accept forwarded headers **only from trusted reverse proxies**, preventing clients from spoofing host/proto.
- Enforce `redirect_uri` through strict registration; never allow wildcards or user-controlled redirect variables.
- Protect against session fixation using Spring Security's built-in mechanisms and test session rotation upon login.
- Define timeouts for sessions, authorization requests, authorization codes, and re-authentication policies.
- Across multiple instances, design session affinity or a distributed session store compatible with security context persistence and request caching.
- Never log raw authorization codes, passwords, client secrets, session cookies, or access tokens, or place them in URLs where secrets could leak.

A common reverse proxy bug: the server sees an internal HTTP scheme and generates wrong redirect URLs even though clients connect via HTTPS. Check proxy config, forwarded-header handling, and proxy allowlists—never "fix" it by trusting all `X-Forwarded-*` headers from the Internet.

## 9. Observing and Troubleshooting Common Errors

### 9.1. `/login → /login` Loop

**Symptom:** the browser reports too many redirects or repeated URLs.

**Likely causes:** the login route requires authentication, the custom login page lacks `permitAll()`, or `/login` matches the wrong chain.

**Checks:** which chain handles `GET /login`; does the custom page have a controller/template; does form login use the expected login URL and processing URL.

### 9.2. Login Succeeds Yet Does Not Return to `/oauth2/authorize`

**Symptom:** form login authenticates properly yet the client receives no authorization code and the user lands on the home page.

**Likely causes:** original request was not cached, an overridden success handler, lost session cookie, or invalid initial redirect.

**Checks:** `RequestCache` and `SavedRequestAwareAuthenticationSuccessHandler`, session ID/cookies, cookie policy, load balancer, and custom login handlers. Never force redirects to URLs from arbitrary query parameters.

### 9.3. Token Endpoint Returns an HTML Page Instead of JSON

**Symptom:** OAuth2 SDK encounters a 302 or receives HTML while exchanging the code.

**Likely causes:** global login entry point, wrong chain order/matcher, or reverse proxy misrouting.

**Checks:** AS endpoints matcher, filter chain priority, `Accept` headers, expected OAuth2 error, and any global `authenticationEntryPoint` configuration. Restore protocol-compliant error handling.

### 9.4. `POST /login` Returns 403

**Symptom:** GET login renders normally, yet POST returns 403.

**Likely causes:** missing/wrong CSRF token, session cookie not sent, security matcher mismatch, or denying security rule.

**Checks:** CSRF token in form, cookies, headers, form action, and filter chains. Distinguish a 403 due to CSRF from a login failure due to a wrong password (normally handled by the failure handler).

### 9.5. Login Succeeds Yet Authorization Endpoint Still Sees Anonymous

**Symptom:** after `POST /login` succeeds, `GET /oauth2/authorize` redirects back to login.

**Likely causes:** `SecurityContext` not saved, session/cookie not retained, host/domain changed, or a stateless chain applied by mistake.

**Checks:** session creation policy, `SecurityContextRepository`, session cookie domain/path, proxy, success handler, and custom login logic. With explicit-save mechanics, custom authentication logic may need to call `SecurityContextRepository.saveContext(...)` to persist authentication across requests.

### 9.6. API in the Same App Returns `/login` for Every Error

**Symptom:** REST client receives HTML.

**Likely causes:** the API is matching the web chain with form login.

**Remediation:** separate `/api/**` into a Resource Server chain with Bearer authentication returning appropriate HTTP 401/403 responses. If the API is an internal non-OAuth2 endpoint, still choose an API entry point matching its response contract.

## 10. Testing Entry Points and Unauthenticated Behavior

### 10.1. Applicable Test Matrix

| Test case | Condition | Result to verify |
| --- | --- | --- |
| Unauthenticated browser calls valid authorization endpoint | `Accept: text/html`, registered client/redirect URI | Redirects to `/login`, with a mechanism to resume the request after login |
| Accessing `GET /login` while unauthenticated | Application/login chain | Login page is served without a redirect loop |
| POST login with wrong credentials, valid CSRF | Form login | Failure handler runs; no code/token issued |
| POST login with valid credentials, valid CSRF | Form login | User is authenticated and resumes the matching authorization request |
| POST login missing CSRF | Cookie/session + form login | Rejected per CSRF policy |
| Client fails authentication at token endpoint | HTTP client | OAuth2 `invalid_client` error response; no HTML login page |
| Token endpoint receives wrong code or wrong PKCE verifier | Authorization code grant | `invalid_grant`, no token issued |
| Authorization request has unregistered redirect URI | Browser | AS rejects; never redirects to a dangerous URL |
| API missing Bearer token | Resource Server chain | 401/challenge, no login redirect |
| API has valid Bearer token yet lacks scope | Resource Server chain | Access denied per authorization policy |

### 10.2. MockMvc Test Checking Browser Redirect

This is a test template for a setup with AS, registered client, and a validly constructed authorization request. Use `client_id`, `redirect_uri`, scopes, and PKCE challenge matching your actual test fixture.

~~~java
@Test
void unauthenticatedBrowserIsSentToLogin() throws Exception {
    mockMvc.perform(get("/oauth2/authorize")
            .param("response_type", "code")
            .param("client_id", "booking-web")
            .param("redirect_uri", "https://client.example.test/callback")
            .param("scope", "openid", "profile")
            .param("state", "fixture-state")
            .param("code_challenge", "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")
            .param("code_challenge_method", "S256")
            .accept(MediaType.TEXT_HTML))
        .andExpect(status().is3xxRedirection())
        .andExpect(header().string(
            "Location", org.hamcrest.Matchers.containsString("/login")));
}
~~~

The `code_challenge` in the example can correspond to a valid `code_verifier` generated per PKCE; `state` is just a test fixture and must never be a fixed value in production. To prevent assertions from failing due to missing registration or mismatched parameters, prepare a matching `RegisteredClient`, an unauthenticated user, and cookie/session handling like the real app.

### 10.3. MockMvc Test Checking Public Login Access

~~~java
@Test
void loginPageIsAvailableToAnonymousUser() throws Exception {
    mockMvc.perform(get("/login").accept(MediaType.TEXT_HTML))
        .andExpect(status().isOk());
}
~~~

If using a custom login page, tests should also verify the rendered template and provided CSRF field. If using the default generated page, you can inspect the HTML response while avoiding brittle coupling to Spring Security's internal markup.

### 10.4. Testing the Difference Between Authentication and Authorization

Do not test HTTP status alone; prove the system neither issues tokens nor leaks information on invalid requests:

~~~text
[1] Unauthenticated user + valid authorization request:
    -> browser redirects to login.

[2] Authenticated user + client requests unpermitted scope:
    -> AS rejects or handles consent/authorization per policy,
       never automatically granting scopes beyond registration.

[3] Client sends wrong client_secret to token endpoint:
    -> OAuth2 error, no HTML login.

[4] Authorization code already used once:
    -> cannot be exchanged again for new tokens.

[5] Resource Server without Bearer token:
    -> 401, challenge matching token type.

[6] Resource Server with Bearer token lacking scope:
    -> 403 or contract authorization error, never sent to login.
~~~

Some `MockMvc` tests using `@WithMockUser` or `oauth2Login()` only mock `Authentication`; they do not validate real login/sessions, post-consent redirects, or PKCE verification. For an AS system, include full integration tests covering registration, sessions, authorization codes, the token endpoint, and real clients.

### 10.5. Inspecting Filter Chains Without Leaking Sensitive Info

When bugs are hard to reproduce, temporarily enable Spring Security logging in a test environment and verify:

1. Which `SecurityFilterChain` the request matched.
2. Whether the current `Authentication` is anonymous, an authenticated user, or an authenticated client.
3. Which handler produced the redirect or status code.
4. Whether `RequestCache` saved the request and which URL the success handler selected.
5. Which protocol error the OAuth2 endpoint filter returned.
6. Whether session/CSRF stayed consistent after login.

Avoid logging raw HTTP `Authorization` headers, cookies, bodies containing passwords/client secrets, codes, refresh tokens, ID tokens, or access tokens. Log only request ID, endpoint, principal type, error code, handler type, and necessary non-sensitive metadata.

## 11. Self-Check Questions

**Question 1.** Why does `GET /oauth2/authorize` without a session normally redirect to login, whereas `POST /oauth2/token` with a wrong client secret should not redirect?

**Answer:** The authorization endpoint runs a browser flow with a Resource Owner who needs interactive authentication. The token endpoint is a machine-to-machine OAuth2 protocol request; client authentication failures must return `invalid_client` per specification for the OAuth2 client to handle.

**Question 2.** Does `LoginUrlAuthenticationEntryPoint("/login")` generate the `/login` HTML page and authenticate username/password itself?

**Answer:** No. It only defines the redirect response. Serving the page and processing form submissions are handled by the login chain, form login filter, and controller/template per configuration.

**Question 3.** What happens if an `anyRequest().authenticated()` chain does not allow anonymous access to a custom `/login` page?

**Answer:** It can cause a `/login` redirect loop. Scope chains properly and configure the login page as public within the required bounds.

**Question 4.** How do `AuthenticationEntryPoint` and `AccessDeniedHandler` differ?

**Answer:** The entry point commences authentication when a request lacks sufficient authentication. The access denied handler handles rejected requests when already authenticated enough not to restart login. For anonymous users, `AccessDeniedException` can also lead to the entry point.

**Question 5.** Why is `RequestCache` or a continuation strategy needed after login for an authorization request?

**Answer:** The browser must return to the original OAuth2 request with valid client ID, scopes, state, redirect URI, and PKCE challenge. Being sent to the home page abandons the code-issuance flow.

**Question 6.** Why should CSRF not be disabled globally just to make POST form login succeed?

**Answer:** Form login and consent over sessions/cookies have a CSRF attack surface. You must provide/verify appropriate CSRF tokens and exempt only endpoints with protocol justification rather than removing protection everywhere.

**Question 7.** An application hosts both an AS and a REST API. How do you prevent API calls missing a token from receiving an HTML login page?

**Answer:** Configure a dedicated API `SecurityFilterChain` with an appropriate matcher and Resource Server/Bearer entry point ordered ahead of the web chain, so API calls return HTTP 401/403 and challenges per contract.

## 12. Pre-Deployment Configuration Checklist

- [ ] Authorization Server endpoints are matched by a dedicated chain with high priority.
- [ ] Unauthenticated browser authorization requests redirect to the exact login page URL.
- [ ] `GET /login` is reachable when anonymous, with no redirect loop.
- [ ] `POST /login` authenticates and handles CSRF success/failure per policy.
- [ ] After login, the browser resumes the original authorization request when needed.
- [ ] OAuth2 token endpoint returns properly formatted OAuth2 errors, never HTML login pages.
- [ ] API/Resource Server returns appropriate 401/403 responses without the web chain stealing the matcher.
- [ ] Never redirect to an unverified `redirect_uri`.
- [ ] Sessions/cookies, HTTPS, proxy headers, and issuer URL align with the deployment environment.
- [ ] Tested HTML/JSON scenarios, wrong client credentials, wrong PKCE, insufficient authority, and consent denial.
- [ ] Diagnostic logging exists without exposing secrets, cookies, or tokens.

## 13. Summary and References

In an Authorization Server, **the login entry point is the mechanism for commencing interactive authentication**, typically used when an unauthenticated Resource Owner reaches the authorization endpoint. Proper configuration must account for **the selected `SecurityFilterChain`, endpoint type, principal type requiring authentication, and HTTP response format**. Spring Security provides `AuthenticationEntryPoint` and `ExceptionTranslationFilter` to handle commencing authentication, while Spring Authorization Server provides dedicated filters and responses to enforce OAuth 2.0/OIDC.

The two most helpful design principles are: **HTML requests to the authorization endpoint can redirect to `/login`; token/API requests must receive their protocol-appropriate responses**, and **never bypass security boundaries just to make a login flow more convenient**. Combining chain setup, request cache, session/CSRF protections, redirect URI validation, and integration tests ensures the Authorization Code + PKCE flow works accurately from unauthenticated arrival through token issuance.

Official references—select the documentation version matching your project:

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Handling Security Exceptions](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — Servlet Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)

Code samples illustrate principles on the Spring Security 6/Spring Authorization Server 1.x branch and assume client registration, user authentication, signing keys, and authorization/consent persistence are configured elsewhere in the application. If using a newer Spring Security release, verify package/API changes before copying code.
