# Login Loops, Lost Authorization Requests, and Wrong Filter Chain Order

In Spring Authorization Server, a client typically begins with a request to **/oauth2/authorize**. If the user is not yet logged in, Spring Security redirects the browser to the login page. After successful authentication, the browser must return to the original authorization request so the server can proceed with validating the client, redirect URI, scope, consent, and issuing an authorization code.

If a link in this chain breaks, the user may bounce back and forth between **/oauth2/authorize** and **/login**, land on the home page after signing in, or receive **invalid_request**, **authorization_request_not_found**, and **state_mismatch** errors.

Three common groups of causes are:

- Sessions or cookies are not preserved across redirects, causing the saved request and authentication state to vanish.
- RequestCache, the authentication success handler, or AuthorizationRequestRepository is misconfigured, losing the request that needs to continue.
- SecurityFilterChain has incorrect matchers or ordering, routing login, callback, or Authorization Server endpoint requests into the wrong chain.

This lesson walks through distinguishing request types, tracing redirects, inspecting sessions and cookies, fixing filter chain order, and verifying with logs and integration tests.

## 1. Understanding the Login Flow in the Authorization Code Flow

An authorization request typically contains parameters such as **client_id**, **response_type**, **redirect_uri**, **scope**, **state**, **nonce**, and a PKCE challenge. The Authorization Server must retain that context while the user logs in.

Simplified flow when the user logs in via the application's own form:

~~~mermaid
sequenceDiagram
    participant C as OAuth/OIDC Client
    participant B as Browser
    participant AS as Authorization Server
    participant L as Login Page

    C->>B: Redirect to /oauth2/authorize
    B->>AS: GET /oauth2/authorize?client_id=...&state=...
    AS->>AS: No Authentication yet
    AS->>AS: Save original request into RequestCache
    AS-->>B: 302 Location: /login
    B->>L: GET /login
    L-->>B: Login form
    B->>AS: POST /login + credentials + CSRF
    AS->>AS: Authenticate and save SecurityContext
    AS-->>B: 302 back to saved authorization request
    B->>AS: GET /oauth2/authorize with original request
    AS->>AS: Continue authorize/consent
    AS-->>B: Redirect to redirect_uri with code and state
    B->>C: Client callback
~~~

The crucial point is that the returning request after login must still have its full context. If the server only knows the user has logged in without knowing which request was pending, the user may be sent to the default landing page instead of continuing the authorization flow.

In this flow, distinguish three things:

| Component | Role | Where Typically Stored |
|---|---|---|
| Inbound authorization request | Request from client entering **/oauth2/authorize** | RequestCache/session during the redirect to login; afterward Spring Authorization Server processes and persists authorization state for the flow |
| SecurityContext | User identity after login | HTTP session via SecurityContextRepository, if the application uses sessions |
| Outbound OAuth2/OIDC authorization request | Request sent by the application itself to an external IdP when using **oauth2Login()** | AuthorizationRequestRepository, defaulting to HttpSessionOAuth2AuthorizationRequestRepository |

Do not use the generic term "authorization request" interchangeably for all three. RequestCache handles the pending HTTP request after login; AuthorizationRequestRepository holds the OAuth2 request created by the application to send to an identity provider; SecurityContext stores the authentication result.

## 2. Identifying Symptoms Before Changing Configuration

Open the browser's Network tab or capture the request/response sequence. Note the URL, status, Location, cookies sent, and cookies returned.

| Symptom | Common Cause | First Check |
|---|---|---|
| **/oauth2/authorize** → **/login** → **/oauth2/authorize** → **/login** loop | Session lost, SecurityContext not persisted, or login request caught by another chain | Session cookie, session store, and chain handling **/login** |
| Login succeeds, but redirects to **/** or dashboard | Success handler uses default target and ignores saved request | AuthenticationSuccessHandler and RequestCache |
| After login, receives **invalid_request** or missing **client_id**/**redirect_uri** | Saved request was lost or request was altered | Location after login and original query parameters |
| **/login** redirects back to **/login** | Login page requires Authentication or is mistakenly caught by Authorization Server chain | securityMatcher, requestMatchers, permitAll |
| Login succeeds, but IdP callback reports **authorization_request_not_found** | Session or AuthorizationRequestRepository cannot find outbound request | Cookie, state, repository, and callback chain |
| **state_mismatch** or **invalid_state_parameter** | Request state and callback state no longer match | Session, multiple tabs, proxy, and request repository |
| Login POST returns **403** | Missing/invalid CSRF token or wrong form action | Hidden CSRF field, cookie, and request method |
| Fails only with multiple replicas | Session or request state resides in one pod's memory | Shared session store and routing across pods |
| Fails only behind ingress | Cookie Secure/SameSite, forwarded headers, or wrong path rewrite | Set-Cookie header, X-Forwarded-*, and public URL |

Do not conclude the fault is in OAuth2 just because the browser is on **/oauth2/authorize**. Identify the very first request whose behavior diverges from expectations.

## 3. Checking SecurityFilterChain and Matcher Order

### 3.1. Spring Security Uses Only the First Matching Chain

**FilterChainProxy** evaluates **SecurityFilterChain** beans in order. For a given request, the first chain whose **securityMatcher** matches is selected. Subsequent chains do not add further filters to that request.

This means:

- **@Order(1)** is evaluated before **@Order(2)**.
- **securityMatcher(...)** decides which chain owns the request.
- **requestMatchers(...)** inside **authorizeHttpRequests** decides access rules after the chain has been selected.
- A chain with an **anyRequest()** matcher placed too early can capture all requests and prevent specialized chains behind it from ever running.

This is the single most important distinction when diagnosing filter chain ordering bugs.

### 3.2. Using Separate Chains for the Authorization Server and Login Application

A common structure is:

1. High-priority chain for Authorization Server endpoints.
2. Separate API chain if the application has a stateless API.
3. Web application chain last, handling the login page and HTML pages.

The example below uses Spring Authorization Server's newer configurer API. Check against your project's dependency version.

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        RequestCache requestCache) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
            authorizationServer
                .oidc(Customizer.withDefaults())
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated()
        )
        .requestCache(cache ->
            cache.requestCache(requestCache)
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
        HttpSecurity http,
        RequestCache requestCache,
        AuthenticationSuccessHandler authenticationSuccessHandler)
        throws Exception {

    http
        .requestCache(cache ->
            cache.requestCache(requestCache)
        )
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers(
                "/login",
                "/assets/**",
                "/favicon.ico"
            ).permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(form -> form
            .loginPage("/login")
            .successHandler(authenticationSuccessHandler)
            .permitAll()
        );

    return http.build();
}

@Bean
RequestCache requestCache() {
    return new HttpSessionRequestCache();
}
~~~

In the example:

- The first chain matches only the endpoint matcher provided by the Authorization Server configurer.
- **/login** does not belong to the Authorization Server matcher, so requests fall through to the application chain.
- **RequestCache** is shared to save the original request and restore it after login.
- The login page and static assets are permitted before the user authenticates.
- **LoginUrlAuthenticationEntryPoint** sends unauthenticated HTML requests to **/login**.

If the project uses the older API, configure **OAuth2AuthorizationServerConfiguration.applyDefaultSecurity(http)** in the first chain, then add OIDC, RequestCache, and exception handling appropriately. Do not mix both configurer styles in the same chain.

### 3.3. Never Place a Catch-All Chain Before the Authorization Server

Error-prone example:

~~~java
@Bean
@Order(1)
SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
        throws Exception {
    http
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {
    OAuth2AuthorizationServerConfiguration.applyDefaultSecurity(http);
    return http.build();
}
~~~

The first chain declares no **securityMatcher**, so it matches every request. Endpoints like **/oauth2/authorize**, **/oauth2/token**, or **/oauth2/jwks** may be treated as ordinary application requests. The Authorization Server chain behind it is never selected.

Symptoms can include endpoints returning **404**, wrong login redirects, missing protocol filters, or inconsistent behavior across endpoints.

The fix is to place the Authorization Server chain first with its specific endpoint matcher; the catch-all application chain must come after.

### 3.4. Do Not Let the Authorization Server Chain Capture /login

The opposite error occurs when the Authorization Server chain uses an overly broad matcher:

~~~java
http.securityMatcher("/**");
~~~

If this chain is first and applies filters/rules meant only for the Authorization Server, **/login**, **/assets/**, or the callback **/login/oauth2/code/** may also enter that chain. The login page might fail to render, POST login might not be handled, or requests might redirect continuously.

Use **authorizationServerConfigurer.getEndpointsMatcher()** or an explicit endpoint matcher. Never use a catch-all matcher on a specialized chain.

### 3.5. Isolating Stateless APIs with a Separate Matcher

If the application has a sessionless REST API, place the API chain between the Authorization Server chain and the web chain:

~~~java
@Bean
@Order(2)
SecurityFilterChain apiSecurityFilterChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated()
        )
        .oauth2ResourceServer(resourceServer ->
            resourceServer.jwt(Customizer.withDefaults())
        )
        .sessionManagement(session ->
            session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
        );

    return http.build();
}

@Bean
@Order(3)
SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
        throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/login", "/assets/**").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(form -> form.loginPage("/login").permitAll());

    return http.build();
}
~~~

The API chain matches only **/api/**; it must not capture **/oauth2/authorize** or **/login**. Do not set **SessionCreationPolicy.STATELESS** in the web chain handling form login if the flow needs sessions to store RequestCache and SecurityContext.

## 4. Fixing Lost Inbound Authorization Requests

### 4.1. Understanding RequestCache

When an unauthenticated user accesses a protected URL, **ExceptionTranslationFilter** can save the request into **RequestCache** before invoking the AuthenticationEntryPoint.

For session-based web apps, the default implementation is typically **HttpSessionRequestCache**. The request is stored in the HTTP session so the success handler can redirect the browser back to the original URL after login.

If the application replaces RequestCache with **NullRequestCache**, uses stateless sessions, or its success handler always redirects to a fixed page, the original request can be lost.

Example of explicitly configuring a shared RequestCache:

~~~java
@Bean
RequestCache requestCache() {
    return new HttpSessionRequestCache();
}
~~~

Configure that same bean in both the Authorization Server chain and the form login chain. Sharing it ensures both chains read and write the same saved request in the session.

Do not swap it for **NullRequestCache** in browser authorization flows that need to return to the original URL.

### 4.2. Checking AuthenticationSuccessHandler

Form login's default success handler can use the saved request to send the browser back to the pending request. If the application writes a custom handler like this:

~~~java
.successHandler((request, response, authentication) ->
    response.sendRedirect("/dashboard")
)
~~~

then the original authorization request is ignored. The user logs in successfully, but the Authorization Server never resumes the flow the client initiated.

If post-login custom logic is needed, use **SavedRequestAwareAuthenticationSuccessHandler** as a base and customize only what is strictly necessary:

~~~java
@Bean
AuthenticationSuccessHandler authenticationSuccessHandler(
        RequestCache requestCache) {
    SavedRequestAwareAuthenticationSuccessHandler handler =
            new SavedRequestAwareAuthenticationSuccessHandler();

    handler.setRequestCache(requestCache);
    handler.setDefaultTargetUrl("/dashboard");
    handler.setAlwaysUseDefaultTargetUrl(false);

    return handler;
}
~~~

**alwaysUseDefaultTargetUrl(false)** lets the saved request take precedence when present; **/dashboard** is only the fallback target when there is no request to restore. If implementing a custom success handler, preserve equivalent behavior and do not clear the saved request before using it.

### 4.3. Verifying That RequestCache Actually Saves the Request

When redirected to **/login**, check that a session was created and the saved request exists. Common cases that lose the request:

- RequestCache was replaced with **NullRequestCache**.
- The application set **SessionCreationPolicy.STATELESS** in the chain handling browser authorization.
- A custom **SecurityContextRepository** or success handler clears the session.
- The login page and login endpoint use different cookie paths/domains.
- The session store is not shared across replicas.
- A proxy drops cookies or the browser does not resend the cookie.
- The request is rewritten to another URL before being saved.

RequestCache only holds the pending HTTP request. It does not replace Spring Authorization Server's authorization state persistence, nor does it replace Spring OAuth2 Client's AuthorizationRequestRepository.

### 4.4. Avoiding Parameter Mutation During Redirects

Compare the URL before and after login. Parameters such as **client_id**, **redirect_uri**, **response_type**, **scope**, **state**, **nonce**, **code_challenge**, and **code_challenge_method** must remain identical to the original request.

If the application builds redirect URLs manually by string concatenation, the following can happen:

- Dropped query parameters.
- Double URL encoding.
- **&** characters encoded or stripped.
- **redirect_uri** scheme/host/path altered.
- **state** or PKCE challenge modified.
- PAR request URI lost.

Do not reconstruct the authorization URL from a partial parameter list. Rely on the saved request or the protocol request mechanisms provided by the framework.

## 5. Fixing Lost Outbound OAuth2/OIDC Authorization Requests

Another scenario is when Spring Authorization Server uses **oauth2Login()** to log users in via an external IdP. For example, the application delegates login to Google, Keycloak, or an internal identity provider.

In that case, Spring Security OAuth2 Client creates an **OAuth2AuthorizationRequest** containing **state**, **nonce**, redirect URI, client registration ID, and protocol parameters. By default, **HttpSessionOAuth2AuthorizationRequestRepository** saves the request in the HTTP session so the callback can retrieve it.

Flow:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant APP as Application
    participant IDP as External IdP

    B->>APP: GET /oauth2/authorization/corporate
    APP->>APP: Create OAuth2AuthorizationRequest and save in session
    APP-->>B: 302 to IdP with state
    B->>IDP: Authorization Request
    IDP-->>B: Redirect to /login/oauth2/code/corporate?code=...&state=...
    B->>APP: Callback with session cookie
    APP->>APP: Look up request from session and compare state
    APP->>IDP: Token Request
    IDP-->>APP: Token Response
    APP-->>B: Login succeeded
~~~

If the callback does not carry the right session cookie, the repository cannot find the saved request. The result is typically **authorization_request_not_found** or a state error.

Check:

- Both the initiating request and callback use the same browser profile.
- The session cookie is sent in both requests.
- The callback path **/login/oauth2/code/** belongs to a chain with **oauth2Login()**.
- The session store is shared across replicas.
- No middleware clears the session or changes the cookie path.
- No custom AuthorizationRequestRepository saves requests somewhere different from where the callback reads.
- **state** in the callback matches the saved request.
- If multiple tabs or concurrent logins occur, a custom repository does not overwrite another tab's request.

The web chain configuration can enable **oauth2Login()** alongside form login as required:

~~~java
http
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/login", "/assets/**").permitAll()
        .anyRequest().authenticated()
    )
    .formLogin(form -> form.loginPage("/login").permitAll())
    .oauth2Login(Customizer.withDefaults());
~~~

Ensure the callback is not intercepted by a stateless API chain or an overly broad Authorization Server chain before reaching the web chain.

## 6. Checking Sessions, Cookies, and Reverse Proxies

### 6.1. Verifying the Session Cookie in the Browser

In DevTools, check whether the first redirect response includes **Set-Cookie** and whether subsequent requests send the cookie back.

Check these attributes:

| Attribute | Potential Issue |
|---|---|
| Domain | Cookie is not sent if domain does not match the public host |
| Path | Cookie is not sent to **/login** or **/oauth2/authorize** if path is too narrow |
| Secure | Cookie is only sent over HTTPS; proxy/app scheme mismatch can cause inconsistent behavior |
| SameSite | Browser may omit cookie on cross-site navigations or callbacks |
| HttpOnly | Should be enabled so JavaScript cannot read the session cookie |
| Max-Age/Expires | Session cookie expires before the user finishes logging in |

A common Spring Boot configuration when publicly exposed over HTTPS:

~~~properties
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
server.forward-headers-strategy=framework
~~~

Properties depend on the Spring Boot version. Confirm actual cookie settings in the **Set-Cookie** response header; do not rely solely on properties files.

**SameSite=Lax** usually works for top-level GET navigations to the Authorization Server. If the system has cross-site POST callbacks, such as a flow using **response_mode=form_post**, evaluate which cookies must accompany the callback. Cookies needed in cross-site POSTs may require **SameSite=None; Secure**. Do not switch all cookies to **None** without a real requirement.

### 6.2. Checking HTTPS Termination and Forwarded Headers

When TLS terminates at an ingress or reverse proxy, the application may receive internal requests over HTTP while the browser uses HTTPS. If forwarded headers are not handled properly, the application may:

- Generate redirects to **http://** instead of **https://**.
- Issue Secure cookies inconsistently.
- Build public URLs with the wrong host or port.
- Compare redirect URIs incorrectly.
- Create redirect loops between the proxy and the application.

Configure **server.forward-headers-strategy** to match your infrastructure and trust headers only from controlled proxies. Do not allow Internet clients to spoof **X-Forwarded-Proto** or **X-Forwarded-Host** to dictate the application's security URLs.

Inspect the headers received by the application and the URL in the **Location** response header. **issuer**, discovery endpoints, and redirect URIs must align with the public URL.

### 6.3. Checking Path Prefixes and Rewrite Rules

If the public URL is **https://auth.example.com/security** while the proxy forwards requests to the application at **/**, determine whether the application runs with a context path or the proxy strips the prefix.

Common issues:

- Browser is redirected to **/login** instead of **/security/login**.
- Callback **/login/oauth2/code/corporate** is rewritten to an incorrect path.
- Authorization endpoint is advertised with a different path than what the proxy routes.
- Cookie with **Path=/security** is not sent to **/login** at root.

Inspect ingress rules, context path, **AuthorizationServerSettings**, login page URL, and cookie path together. Avoid patching individual URLs piecemeal without establishing a single consistent public base path.

### 6.4. Multiple Replicas Need a Shared Session Store

If the **/oauth2/authorize** request hits pod A, while the login GET/POST or callback hits pod B, pod B must be able to read the session created by pod A.

Sticky sessions can reduce the chance of requests switching pods, but they do not replace a shared session store. When a pod restarts or scales down, local sessions are still lost.

Spring Session with Redis or JDBC can be used. Check:

- All replicas use the same namespace/session repository.
- Session cookies share the same domain, path, and signing/encryption configuration if any.
- Redis/JDBC is reachable from every pod.
- Session TTL is long enough for login and consent.
- Serialization is compatible across versions during rolling deployments.
- Post-login session fixation strategy does not discard the saved request.

Do not call **session.invalidate()** manually after login if the saved request or OAuth2AuthorizationRequest in the session is still needed. Spring Security provides session fixation protection; keep the appropriate default strategy or configure intentional session migration.

## 7. Checking the Login Page and CSRF

If using a custom login page, the form must submit to the right processing endpoint with a CSRF token.

HTML example:

~~~html
<form method="post" action="/login">
  <label for="username">Username</label>
  <input id="username" name="username" type="text" autocomplete="username">

  <label for="password">Password</label>
  <input id="password" name="password" type="password"
         autocomplete="current-password">

  <input type="hidden" name="_csrf" value="CSRF_TOKEN_FROM_MODEL">
  <button type="submit">Sign in</button>
</form>
~~~

**CSRF_TOKEN_FROM_MODEL** is a placeholder. The template engine must render the actual token value from the request/model per Spring Security configuration. Do not submit the literal placeholder string.

Check:

- Form method is POST.
- Action points to the exact **loginProcessingUrl**.
- Field names match **usernameParameter** and **passwordParameter** if customized.
- CSRF token is rendered and submitted.
- The login page and assets do not require Authentication.
- POST login is not intercepted by another chain before **UsernamePasswordAuthenticationFilter**.
- After login, SecurityContext is persisted so the next request recognizes the user.

Do not disable CSRF application-wide to fix a **403** on the login form. If a protocol endpoint needs custom CSRF rules, apply a narrow matcher following the guidance for your Spring Authorization Server version.

## 8. Diagnosing by Redirect Sequence

A practical approach is to record each step and locate where the loop or break occurs.

### Case A: Session Lost After Redirect

Observed sequence:

~~~text
GET /oauth2/authorize?...        -> 302 /login
GET /login                       -> 200
POST /login                      -> 302 /oauth2/authorize?...
GET /oauth2/authorize?...        -> 302 /login
~~~

The cause is usually that SecurityContext was not retained or the session cookie was not sent back. Check **Set-Cookie**, request Cookie, session ID, session store, and SecurityContextRepository.

### Case B: Login Succeeds, Saved Request Ignored

~~~text
GET /oauth2/authorize?...        -> 302 /login
POST /login                      -> 302 /
GET /                              -> 200
~~~

The cause is usually a custom success handler that always redirects to **/**. Check **SavedRequestAwareAuthenticationSuccessHandler**, RequestCache, and **alwaysUseDefaultTargetUrl**.

### Case C: Login Page Protected by the Wrong Chain

~~~text
GET /oauth2/authorize?...        -> 302 /login
GET /login                       -> 302 /login
GET /login                       -> 302 /login
~~~

The cause may be **/login** being handled by the Authorization Server chain or an improper catch-all chain, or the **/login** rule lacking **permitAll**. Check chain ordering, matchers, and login page configuration.

### Case D: Outbound IdP Callback Cannot Find Request

~~~text
GET /oauth2/authorization/corporate -> 302 external-idp
GET /login/oauth2/code/corporate?... -> 4xx
~~~

Check whether the session cookie is sent in the callback, whether AuthorizationRequestRepository reads from the right session, and whether the callback passes through the chain containing **oauth2Login()**.

### Case E: Login POST Rejected by CSRF

~~~text
GET /login                       -> 200
POST /login                      -> 403
~~~

Check the hidden CSRF field, the CSRF cookie if using a cookie-based repository, the form action, and the request content type. Distinguish **403** from CSRF versus **401** from bad credentials.

## 9. Using Logs to Identify Chain and RequestCache

In development or staging, you can briefly enable Spring Security TRACE logging:

~~~properties
logging.level.org.springframework.security=TRACE
~~~

Logs help identify:

- Which chain **FilterChainProxy** dispatches the request to.
- Which matcher matched the request.
- Whether **AuthorizationFilter** requires Authentication.
- Whether **ExceptionTranslationFilter** invokes AuthenticationEntryPoint.
- Whether RequestCache saves the saved request.
- Whether authentication succeeded or failed.
- Whether SecurityContext was saved and restored.

Do not leave broad TRACE logging enabled in production for extended periods. It increases log volume and can inadvertently log sensitive request details depending on configuration. Never log passwords, session cookies, authorization codes, client secrets, access tokens, refresh tokens, or full query strings containing sensitive data.

You can add sanitized application logs, for example:

- Correlation ID.
- Endpoint name.
- Filter chain name or application version.
- Authentication result.
- Whether a saved request exists.
- OAuth error code.
- Replica/pod handling the request.

Do not log the full session ID; if correlation is needed, use a hash or protected identifier.

## 10. Regression Testing for Login and Authorization Requests

### 10.1. Testing Saved Request Across Form Login

An integration test should verify that the initial request is saved, login succeeds, and the redirect returns to the authorization endpoint.

Illustrative example with MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationLoginFlowTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void shouldReturnToAuthorizationRequestAfterLogin() throws Exception {
        MvcResult authorizationStart = mockMvc.perform(
                get("/oauth2/authorize")
                    .param("response_type", "code")
                    .param("client_id", "web-client")
                    .param("redirect_uri",
                            "https://client.example.com/callback")
                    .param("scope", "openid profile")
                    .param("state", "state-123")
                    .param("code_challenge", "TEST_CHALLENGE")
                    .param("code_challenge_method", "S256"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
                (MockHttpSession) authorizationStart.getRequest().getSession(false);

        assertThat(session).isNotNull();
        assertThat(authorizationStart.getResponse().getRedirectedUrl())
                .contains("/login");

        MvcResult loginResult = mockMvc.perform(
                post("/login")
                    .session(session)
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "test-password"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        assertThat(loginResult.getResponse().getRedirectedUrl())
                .contains("/oauth2/authorize")
                .contains("client_id=web-client")
                .contains("state=state-123");
    }
}
~~~

The example requires a test user, registered client, CSRF support, and endpoint paths matching your application. The PKCE challenge value in the example is an illustrative fixture; end-to-end tests should compute a valid S256 challenge from the verifier.

With session fixation configurations that rotate the session ID, real HTTP tests must continue using the new session cookie from the login response. MockMvc may reuse the same session object depending on strategy; when verifying browser-level cookie behavior, use an embedded server or a test HTTP client with a cookie jar.

### 10.2. Testing Login and Callback Chains

Create separate cases:

| Case | Request | Expected Result |
|---|---|---|
| CHAIN-01 | Unauthenticated **GET /oauth2/authorize** | Redirected to login page |
| CHAIN-02 | Unauthenticated **GET /login** | Returns login page, no redirect loop |
| CHAIN-03 | **POST /login** with valid credentials | Authenticates successfully, redirects to saved request |
| CHAIN-04 | **POST /login** missing CSRF | Rejected per CSRF policy |
| CHAIN-05 | **GET /oauth2/jwks** | Handled by Authorization Server chain |
| CHAIN-06 | **GET /login/oauth2/code/corporate** | Handled by chain with oauth2Login |
| CHAIN-07 | **GET /api/profile** | Handled by API chain if application has a separate chain |
| CHAIN-08 | Load **/assets/login.css** | Does not require login if assets are public |
| CHAIN-09 | Authorization request across another replica | Saved request and SecurityContext are still found |
| CHAIN-10 | Two tabs initiate login concurrently | Each flow's state is not inadvertently overwritten |

### 10.3. Testing Callbacks from an External IdP

If using **oauth2Login()**, test additionally:

- AuthorizationRequestRepository saves the request when redirecting to the IdP.
- Callback carries the session cookie and matching **state**.
- Mismatched state is rejected.
- Callback without a session is not automatically accepted.
- Callback route is handled by the application chain.
- Session store is shared across replicas.
- Custom success handler does not bypass the application's saved request.

Do not mock successful authentication in a way that completely bypasses state validation when the goal is to test lost authorization request bugs.

## 11. Ordered Remediation Checklist

When encountering a login loop or lost authorization request, follow this order:

1. Record the redirect sequence, status codes, and **Location** headers.
2. Identify the very first request that redirects unexpectedly.
3. Identify which chain matches **/oauth2/authorize**, **/login**, **/login/oauth2/code/**, and APIs.
4. Check **@Order** and **securityMatcher** scope.
5. Check whether **/login** and assets have **permitAll**.
6. Check whether RequestCache saves the original request.
7. Check whether the success handler uses the saved request.
8. Check that the session cookie is returned and sent back across redirects.
9. Check **SessionCreationPolicy**, SecurityContextRepository, and session invalidation calls.
10. Check SameSite, Secure, Domain, Path, and HTTPS forwarded headers.
11. If running multiple replicas, check the shared session store and serialization.
12. If using **oauth2Login**, check AuthorizationRequestRepository and state on the callback.
13. Re-test from the authorize request through post-login, not just the login page in isolation.

## 12. Common Errors and Fixes

| Error | Cause | Fix |
|---|---|---|
| **/oauth2/authorize** hits app chain | Catch-all chain comes first | Put Authorization Server chain first, use endpoint matcher |
| **/login** hits Authorization Server chain | Matcher too broad | Narrow the Authorization Server chain matcher |
| Redirects to home page after login | Success handler always uses default target | Use SavedRequestAwareAuthenticationSuccessHandler |
| Original request not saved | NullRequestCache or stateless session | Use HttpSessionRequestCache for browser flows |
| Session lost after redirect | Cookie blocked or session not shared | Fix cookie/proxy and use shared session store |
| Login page loops on itself | **/login** lacks permitAll or caught by wrong chain | Fix chain order and authorization rules |
| Login POST 403 | Missing or wrong CSRF token | Render hidden CSRF token and check form action |
| IdP callback reports request not found | AuthorizationRequestRepository cannot find session state | Preserve cookie/session and use consistent repository |
| Fails only on one pod | Session or state stored in local memory | Use Redis/JDBC shared session and appropriate state store |
| Returning URL loses query parameters | Redirect URL built manually or proxy rewrite | Use saved request and check public path |
| Fails only over HTTPS | Wrong forwarded headers or Secure cookie | Configure proxy trust and forwarded headers properly |
| Multiple tabs cause state mismatch | Custom repository overwrites pending request | Key stored requests by state/correlation key and support concurrent flows |

## 13. Pre-Production Checklist

- [ ] Authorization Server chain uses a specific endpoint matcher and appropriate priority order.
- [ ] Application login chain is ordered after the Authorization Server chain.
- [ ] Stateless API, if present, uses its own matcher and does not capture login/callback.
- [ ] **/login**, login processing URL, and assets are accessible according to desired policy.
- [ ] RequestCache in both the Authorization Server chain and login chain is configured consistently.
- [ ] Success handler preserves restoring the saved request.
- [ ] Browser flows have sessions and SecurityContext persisted across requests.
- [ ] Cookie Domain, Path, Secure, HttpOnly, and SameSite match the public URL.
- [ ] Forwarded headers are trusted only from controlled proxies.
- [ ] Multiple replicas use a shared session store if flows can cross pods.
- [ ] Session fixation protection does not discard the saved request.
- [ ] If using **oauth2Login**, AuthorizationRequestRepository preserves the request until callback.
- [ ] Tests cover login loops, dropped query parameters, state mismatch, CSRF, and multiple replicas.
- [ ] Logs suffice to identify chain and RequestCache without recording credentials/tokens.
- [ ] A synthetic authorization flow can be run after each deployment.

Login loops usually signal that a request was routed through an unintended chain or the session is no longer recognized. Lost authorization requests typically relate to RequestCache, success handlers, cookies, or the repository storing outbound requests. Once you identify the exact request type and handling chain, remediation stays focused on the right matcher, session, and restoration mechanism instead of randomly altering security settings.
