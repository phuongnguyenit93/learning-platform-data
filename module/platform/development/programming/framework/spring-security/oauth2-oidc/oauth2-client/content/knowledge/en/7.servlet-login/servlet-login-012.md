# 7.12. SecurityMatcher, Multiple Filter Chains, and Chain Selection for Callbacks

## 1. Why Does an OAuth2 Login Callback Need the Right SecurityFilterChain?

In a Spring Security Servlet application, OAuth 2.0/OIDC login paths are normally not handled directly by a custom-written controller. Spring Security registers **security filters**, including the filter that builds the authorization request and the filter that receives the authorization response containing <code>code</code> and <code>state</code> at the callback.

When an application has only a single <code>SecurityFilterChain</code> applying to all requests, routing to these filters is straightforward. In real-world applications, however, security configurations are often split by area:

- <code>/api/**</code>: API authenticated via bearer tokens, potentially without using HTTP sessions.
- <code>/admin/**</code>: admin pages requiring a separate policy.
- <code>/app/**</code>: web UI logging in via OAuth2/OIDC using sessions.
- <code>/oauth2/authorization/{registrationId}</code>: endpoint initiating OAuth2 login.
- <code>/login/oauth2/code/{registrationId}</code>: endpoint receiving the callback after the provider issues an authorization code.

At this point, a decisive question arises: **which filter chain does the callback request belong to?** If the callback enters a chain that lacks <code>OAuth2LoginAuthenticationFilter</code>, Spring Security will not process the authorization code as expected, even though another chain in the application enables <code>oauth2Login()</code>.

Example symptom:

1. The user visits <code>/app/dashboard</code> and is redirected to the OpenID Provider.
2. The user logs in successfully at the provider.
3. The provider redirects back to <code>/login/oauth2/code/company?code=...&amp;state=...</code>.
4. The application returns 404, 401, 403, loops back to the login page, or fails to create authentication.

A common root cause is that **<code>FilterChainProxy</code> selected the wrong chain or no chain matched the callback**, because <code>securityMatcher</code> configurations were too narrow or chain ordering was incorrect.

> **Core rule:** <code>FilterChainProxy</code> picks the **first matching filter chain** in registered order. There is no fallback mechanism to try a second chain when the first chain's filters fail to handle the callback.

## 2. FilterChainProxy Architecture and Chain Selection

<code>DelegatingFilterProxy</code> connects the application's servlet filters to Spring Security. Inside, <code>FilterChainProxy</code> holds a list of <code>SecurityFilterChain</code>s. Each chain has a <code>RequestMatcher</code> and its corresponding security filters.

When a request arrives:

1. <code>FilterChainProxy</code> tests the request against the matcher of the highest-priority chain.
2. If it matches, it executes that chain's filter list.
3. If it does not match, it tests the next chain.
4. As soon as the **first matching chain** is found, selection stops.
5. If no chain matches, the request is not protected by the Spring Security filter chains in this list.

~~~mermaid
flowchart TD
    R["HTTP Request"] --> P["FilterChainProxy"]
    P --> A{"Does @Order(1) chain match?"}
    A -->|Yes| F1["Run only chain 1 filters"]
    A -->|No| B{"Does @Order(2) chain match?"}
    B -->|Yes| F2["Run only chain 2 filters"]
    B -->|No| C{"Does fallback chain match?"}
    C -->|Yes| F3["Run fallback filters"]
    C -->|No| N["No matching Spring Security chain"]
    F1 --> X["Do not try subsequent chains"]
    F2 --> X
    F3 --> X
~~~

One chain may enable <code>oauth2Login()</code> while another enables only JWT bearer or HTTP Basic. **Chain selection** determines which filters exist for that request. <code>authorizeHttpRequests</code> rules in another chain cannot compensate for missing filters.

### 2.1. Role of @Order

When defining multiple <code>SecurityFilterChain</code> beans, Spring Security needs an explicit order:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    // specific matcher for API
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    // chain for web and OAuth2 Login
    return http.build();
}
~~~

**Smaller <code>@Order</code> values are evaluated earlier.** Because chain selection stops on the first match, place narrow matchers before broad matchers; a chain without a <code>securityMatcher</code> acts as a catch-all for remaining requests and should be placed after specific chains.

Never rely on method declaration order in a Java file or bean names to determine priority. When multiple chains have overlapping scopes, ordering is a critical part of security design.

## 3. How Does SecurityMatcher Differ from requestMatchers?

Both APIs have similar names yet operate at **two different layers**.

| Configuration | Execution layer | Question answered |
|---|---|---|
| <code>http.securityMatcher(...)</code> | Selecting the <code>SecurityFilterChain</code> in <code>FilterChainProxy</code> | Which **chain does this request enter**? |
| <code>authorizeHttpRequests(auth -&gt; auth.requestMatchers(...))</code> | Authorization rules **inside the selected chain** | Is the user/request allowed to access this URL? |
| <code>authorizeHttpRequests(auth -&gt; auth.anyRequest()...)</code> | Final authorization rule in the chain | For requests in this chain not matched by earlier rules, what is the decision? |

Example:

~~~java
http
    .securityMatcher("/app/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/app/public/**").permitAll()
        .anyRequest().authenticated())
    .oauth2Login(Customizer.withDefaults());
~~~

Here:

- The chain is only considered a match for <code>/app/**</code> URLs.
- Within that scope, <code>/app/public/**</code> is accessible without authentication.
- All other <code>/app/**</code> URLs require authentication.
- The URL <code>/login/oauth2/code/company</code> **lies outside the chain's scope**, so the default callback is not handled by <code>OAuth2LoginAuthenticationFilter</code> in this chain.

Even if you add:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/login/oauth2/code/**").permitAll()
    .anyRequest().authenticated())
~~~

the problem **persists**: the chain's security matcher already excluded the callback before reaching authorization. Editing <code>requestMatchers(...).permitAll()</code> alone does not route the URL into the chain.

> <code>permitAll()</code> is an authorization decision. It does not route requests into another chain, nor does it create an OAuth2 Login filter.

### 3.1. What part of the URL does a matcher evaluate?

Normally Spring Security path matchers inspect the **application-side request path** (depending on servlet mapping and matcher type), rather than matching literal patterns against protocol, host, or query string.

Example callback:

~~~text
GET /login/oauth2/code/company?code=abc123&state=xyz456
~~~

The path matcher <code>/login/oauth2/code/**</code> matches against <code>/login/oauth2/code/company</code>; the <code>code</code> and <code>state</code> parameters are processed by the filter once the chain is selected. If the app is deployed under a context path like <code>/portal</code>, pattern matching is also subject to servlet/context path rules; do not manually prepend the context path to patterns without verifying actual matcher behavior.

Spring Security versions and MVC environments may use different matcher implementations, such as MVC-aware matchers or PathPattern-based matchers. For consistent results, use simple patterns, inspect the actual request path, and use the `RequestMatcher` API appropriate for your version.

## 4. Default Servlet OAuth2 Login Endpoints

When enabling:

~~~java
http.oauth2Login(Customizer.withDefaults());
~~~

Spring Security configures the OAuth2/OIDC Login components inside the **current chain**.

| Default endpoint | Related component | Function |
|---|---|---|
| <code>GET /oauth2/authorization/{registrationId}</code> | <code>OAuth2AuthorizationRequestRedirectFilter</code> | Looks up ClientRegistration, builds authorization request, and redirects browser to Authorization Server |
| <code>/login/oauth2/code/{registrationId}</code> | <code>OAuth2LoginAuthenticationFilter</code> | Receives authorization response at callback, verifies state, and performs token exchange |
| <code>/login</code> | Default login page generated when applicable, or app-supplied login page | Lets users choose a login method |
| <code>/login?error</code> | Login page / failure handling path per configuration | Displays failed authentication outcome |

Important framework constants/APIs:

~~~java
OAuth2AuthorizationRequestRedirectFilter.DEFAULT_AUTHORIZATION_REQUEST_BASE_URI
// "/oauth2/authorization"

OAuth2LoginAuthenticationFilter.DEFAULT_FILTER_PROCESSES_URI
// "/login/oauth2/code/*"
~~~

<code>DEFAULT_FILTER_PROCESSES_URI</code> is the filter's callback-processing **pattern**; for example, the concrete redirect URI after template expansion is <code>/login/oauth2/code/company</code>. The <code>registrationId</code> must correspond to an application-configured ClientRegistration.

Typically the Client's redirect URI is declared as:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

And the concrete URL is registered at the provider, e.g.:

~~~text
https://app.example.org/login/oauth2/code/company
~~~

Note that **three configuration layers must align**:

1. <code>ClientRegistration.redirectUri</code> generates the URL sent to the provider.
2. The provider registers/accepts that exact callback URL.
3. <code>OAuth2LoginAuthenticationFilter</code> inside the **selected chain** matches the corresponding callback path.

A URL permitted by the provider that falls outside every chain containing the OAuth2 Login filter still cannot complete login.

## 5. A Clear Design: API Chain First, Web Chain as Fallback

When an application has JWT-protected APIs and a web UI with OIDC login, a common layout is:

- Chain 1: matches only <code>/api/**</code>, using OAuth2 Resource Server JWT for APIs.
- Chain 2: handles all remaining requests, enabling <code>oauth2Login()</code> for the web; this ensures both the authorization start URL and default callback land in this chain.

### 5.1. Complete Java configuration

Spring Boot 3 / Spring Security 6 example:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityChainsConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api", "/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        // No securityMatcher called: webChain catches all remaining requests.
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

This configuration illustrates **two roles**: API JWT Resource Server and web OAuth2 Client. Running the API part requires <code>spring-boot-starter-oauth2-resource-server</code> along with a <code>JwtDecoder</code> or <code>spring.security.oauth2.resourceserver.jwt.issuer-uri</code> property. Running web OIDC requires <code>spring-boot-starter-oauth2-client</code> and a valid <code>ClientRegistration</code>. Both issuers may be identical if using the same provider, yet the two configs serve separate responsibilities.

Example <code>application.yml</code> when the same issuer validates both API JWTs and web OIDC:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/company
      client:
        registration:
          company:
            provider: company
            client-id: web-app
            client-secret: replace-with-secret-from-secure-configuration
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

URLs and credentials here are placeholders. In real apps, load the client secret from a secret store or environment variable; never store real secrets in source control.

In this example, each request is routed as follows:

| Request | First matching chain | Main outcome |
|---|---|---|
| <code>GET /api/orders</code> | <code>@Order(1)</code> API | Validates bearer token via resource-server JWT |
| <code>GET /</code> | <code>@Order(2)</code> Web | Public access |
| <code>GET /dashboard</code> | <code>@Order(2)</code> Web | Requires authentication; may initiate login |
| <code>GET /oauth2/authorization/company</code> | <code>@Order(2)</code> Web | Handled by authorization redirect filter |
| <code>GET /login/oauth2/code/company?code=...&amp;state=...</code> | <code>@Order(2)</code> Web | Handled by OAuth2 Login callback filter |

The key design point is that the API chain **does not overlap the callback**; the web chain comes afterward with no restrictive matcher, so it catches supporting login URLs outside <code>/dashboard</code>.

### 5.2. Why not place the catch-all first?

If you reverse the order:

~~~java
@Order(1) // web chain without a matcher restriction
@Order(2) // api chain securityMatcher("/api/**")
~~~

the web chain matches **every** request first; the API chain is virtually never selected. This can inadvertently send API calls through login/session handling instead of the intended JWT policy. Therefore, place **specific chains first, fallback chains last**.

### 5.3. Notes on CSRF and sessions

In the example, only the API chain avoids browser sessions and disables CSRF. The web chain retains default CSRF protection because it uses sessions/cookies and handles state-changing requests. Never disable CSRF application-wide simply because some bearer-token APIs need a different policy.

Servlet OAuth2 Login typically stores the authorization request and <code>state</code> in the HTTP session via the default <code>HttpSessionOAuth2AuthorizationRequestRepository</code>. The web chain needs to preserve session cookies while the user leaves for the OP and returns to the callback. If the callback is captured by a stateless chain lacking OAuth2 Login, both the filter and authorization request lookup will break.

## 6. When the Web Chain Also Uses securityMatcher: Include the Callback

Some systems require each app area to have its own scoped chain rather than using a broad web fallback. In that case, include **every OAuth2 Login-related URL** in the right chain's security matcher.

Example three-chain configuration:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ScopedSecurityChains {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api", "/api/**")
            .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain oidcWebChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher(
                "/", "/app", "/app/**",
                "/login", "/login/**",
                "/oauth2/authorization/**",
                "/assets/**", "/error")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/login", "/error",
                    "/assets/**", "/oauth2/authorization/**",
                    "/login/oauth2/code/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth.anyRequest().denyAll());
        return http.build();
    }
}
~~~

In the web chain:

- <code>/app</code>, <code>/app/**</code> are application pages requiring login.
- <code>/oauth2/authorization/**</code> allows the OAuth2 Login initiation filter to run.
- <code>/login</code> and <code>/login/**</code> cover the login page, error path, and **<code>/login/oauth2/code/{registrationId}</code> callback**.
- <code>/assets/**</code>, <code>/error</code> serve login and error pages.
- The fallback chain handles unmatched requests; avoid leaving requests outside Spring Security with no policy.

In this example the web chain includes <code>/login/**</code>, so the callback is already covered. To be even more explicit, you can list <code>/login/oauth2/code/**</code> directly in <code>securityMatcher</code>. What matters is that the **chain's match scope** covers the callback before authorization is even evaluated.

Similarly, if you have a custom login page at <code>/signin</code> or logout URLs, assets, CSS, or helper endpoints for login, include them in chain and authorization design to prevent redirect loops or 404s.

If you only define a web chain with <code>securityMatcher("/app/**")</code> and no fallback handling login endpoints, the callback may belong to no chain at all. Then the callback-handling filter never runs even when the provider redirects to a valid URL.

## 7. Customizing the Callback Path: Synchronize All Three Sides

The default callback is <code>/login/oauth2/code/{registrationId}</code>. Sometimes an app needs a custom path, e.g.:

~~~text
/signin/oauth2/callback/{registrationId}
~~~

To change the callback, synchronize:

1. **The redirect URI** the Client sends to the Authorization Server.
2. **The endpoint processing matcher** of <code>OAuth2LoginAuthenticationFilter</code>.
3. **The <code>securityMatcher</code> of the chain** containing the OAuth2 Login filter.
4. **Allowed redirect URIs** configured at the Authorization Server/IdP.

### 7.1. Configuring redirectionEndpoint().baseUri()

Example:

~~~java
@Bean
@Order(2)
SecurityFilterChain oidcWebChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher(
            "/", "/app/**", "/login", "/signin",
            "/signin/oauth2/callback/**",
            "/oauth2/authorization/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(
                "/", "/login", "/signin",
                "/oauth2/authorization/**",
                "/signin/oauth2/callback/**").permitAll()
            .anyRequest().authenticated())
        .oauth2Login(oauth2 -> oauth2
            .redirectionEndpoint(redirect -> redirect
                .baseUri("/signin/oauth2/callback/*")));

    return http.build();
}
~~~

The snippet above is an **alternative configuration** for the web chain in earlier examples; other parts of the app like API/fallback chains can remain unchanged. With this pattern, <code>redirectionEndpoint().baseUri()</code> uses <code>/*</code> to match the single <code>registrationId</code> segment in the callback, while <code>securityMatcher</code> can match the URL with <code>/**</code>. Actual patterns must fit the Spring version and `RequestMatcher` type in use.

Correspondingly, in `ClientRegistration`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: web-app
            client-secret: replace-with-secret-from-secure-configuration
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/signin/oauth2/callback/{registrationId}"
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

And the provider must allow the concrete callback, e.g.:

~~~text
https://app.example.org/signin/oauth2/callback/company
~~~

If you only change <code>redirect-uri</code> in YAML, the provider redirects to the new URL while the OAuth2 Login filter still listens on <code>/login/oauth2/code/*</code>. If you only change <code>redirectionEndpoint().baseUri()</code>, the provider still redirects to the old URL. If you sync those two yet forget <code>securityMatcher</code>, the callback still misses the right chain. **All three settings plus the registration at the IdP must be consistent.**

### 7.2. Changing authorizationEndpoint().baseUri()

The login initiation endpoint can also be customized:

~~~java
.oauth2Login(oauth2 -> oauth2
    .authorizationEndpoint(endpoint -> endpoint
        .baseUri("/sso/start")))
~~~

Then the login initiation URL is typically:

~~~text
/sso/start/{registrationId}
~~~

If the web chain has a restricted matcher, include <code>/sso/start/**</code> instead of <code>/oauth2/authorization/**</code> (or both during migration). Customizing the authorization base URI is **separate** from customizing the callback base URI: one endpoint starts the flow, the other receives the result.

When using a custom login page, login links must point to the new authorization base URI. The login page is an application-rendered endpoint, whereas the filter handles redirecting to the provider under its own rules.

## 8. Two Chains Match the Callback: Why Does @Order Matter?

Consider this broken configuration:

~~~java
@Bean
@Order(1)
SecurityFilterChain broadChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/login/**", "/api/**")
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain oidcChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/app/**", "/login/oauth2/code/**",
                         "/oauth2/authorization/**")
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults());
    return http.build();
}
~~~

The callback <code>/login/oauth2/code/company</code> **matches both** matchers:

- The <code>@Order(1)</code> chain matches <code>/login/**</code> first.
- Even though the <code>@Order(2)</code> chain has <code>oauth2Login()</code>, it is **never tried**.
- The first chain only has HTTP Basic and its filters, so there is no OAuth2 Login callback processing.

Fix this by **narrowing the first chain** to only paths genuinely belonging to HTTP Basic/API, or redesigning namespaces so the callback belongs exclusively to the intended web chain. Simply moving <code>oidcChain</code> earlier is sometimes insufficient, as that can create new conflicts with other endpoints. Map out paths and security goals for each chain in a table.

### 8.1. Chain decision table

| Path | Desired chain | Has oauth2Login filter? | Has valid session? |
|---|---|---|---|
| <code>/api/orders</code> | API bearer/JWT | Not needed | Usually no |
| <code>/app/dashboard</code> | OIDC web | Yes | Yes |
| <code>/oauth2/authorization/company</code> | OIDC web | Yes | Yes, needs to save authorization request |
| <code>/login/oauth2/code/company</code> | **Same OIDC web chain** | **Yes** | **Yes, to retrieve state/authorization request** |
| <code>/login</code> | OIDC web (if using this page) | Per config | Per flow |
| Unmapped URLs | Fallback | Depends on goal | Explicit deny/allow policy |

The order of the callback and authorization start path should be verified as a pair. If the start request hits the web chain while the callback hits the API chain, the app can create an authorization request yet never complete login. Conversely, if the callback hits the right chain while the start path is missed by the filter, users cannot initiate a valid flow.

## 9. State, Session, and SecurityContext Across Multiple Chains

In the Authorization Code Flow for Servlet apps, the Client sends a <code>state</code> parameter when initiating login. When the provider redirects back to the callback, Spring Security verifies <code>state</code> and retrieves the original authorization request. The default repository for OAuth2 Login is typically **<code>HttpSessionOAuth2AuthorizationRequestRepository</code>**.

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant W as Web SecurityFilterChain
    participant S as HTTP Session
    participant OP as OpenID Provider
    B->>W: GET /oauth2/authorization/company
    W->>S: Save OAuth2AuthorizationRequest + state
    W-->>B: 302 redirect to OP
    B->>OP: Authorization Request
    OP-->>B: 302 callback with code + state
    B->>W: GET /login/oauth2/code/company
    W->>S: Retrieve saved authorization request
    W->>W: Verify state, exchange code for tokens
    W-->>B: Establish authentication / redirect on success
~~~

To complete the flow:

- **Start and callback** should be processed within a properly configured OAuth2 Login chain.
- The browser must send back the matching session cookie when redirected from the IdP to the app.
- Across multiple instances, use an appropriate session-sharing or sticky-routing strategy depending on architecture and session store.
- Cookie <code>Secure</code>, <code>SameSite</code>, domain, path, and reverse proxy configuration all affect whether the browser sends cookies back.
- A custom <code>AuthorizationRequestRepository</code> must preserve the full authorization request, state, and required attributes such as PKCE verifiers when used.

**Do not blame every <code>invalid_state</code> error on SecurityMatcher.** A callback can enter the right chain yet still fail due to a lost session cookie, expired authorization request, already-consumed request, or a callback belonging to another login attempt. Chain routing is one essential check in the diagnostic chain.

### 9.1. SessionCreationPolicy and stateless chains

<code>SessionCreationPolicy.STATELESS</code> fits JWT APIs, where every request is authenticated independently via a bearer token. For standard Servlet OAuth2 Login, authorization request state must survive browser redirects. Routing the callback into a stateless chain can mean either the OAuth2 Login filter is missing or login state is not persisted as expected.

If architecture requires sessionless login, explicitly design a matching <code>AuthorizationRequestRepository</code> and authentication persistence mechanism. That is an architectural change—you cannot just flip <code>STATELESS</code> on and expect default OAuth2 Login to keep working as before.

### 9.2. Relationship with SecurityContextRepository

Successful OAuth2 Login creates an <code>Authentication</code> for the user and must make it available on subsequent requests. In session-based apps, Spring Security typically persists `SecurityContext` via the session per configuration.

If the web chain and another chain use different `SecurityContextRepository` implementations or session policies, callback login can succeed while the destination page still views the user as unauthenticated. Check **both the chain handling the callback and the chain protecting the destination page**, not just the callback request alone.

## 10. How to Diagnose Why a Callback Is Not Working

### 10.1. Confirming whether requests enter the right chain

In development, enable scoped logging:

~~~yaml
logging:
  level:
    org.springframework.security.web.FilterChainProxy: TRACE
~~~

Depending on version, logs show which chain was evaluated/selected and which filters ran. When broader visibility is needed, temporarily enable DEBUG on <code>org.springframework.security</code> in a test environment.

Inspect the two requests separately:

~~~text
GET /oauth2/authorization/company
GET /login/oauth2/code/company?code=...&state=...
~~~

The goal is to confirm **which chain each request hits** and that the chain contains the right filters. Never record raw authorization codes, states, access tokens, ID Tokens, refresh tokens, or client secrets in logs or tickets. When tracing, use paths, registration IDs, request correlation IDs, and sanitized error types.

### 10.2. Ordered diagnostic steps

1. **Determine the exact callback** the IdP redirects to, including hostname, scheme, context path, and path.
2. **Check `ClientRegistration.redirectUri`** and the redirect URI registered at the IdP to confirm they match that URL.
3. **List all `SecurityFilterChain` beans in `@Order` sequence**, along with each chain's security matcher.
4. **Find the first chain matching the callback.** Never assume the chain with <code>oauth2Login()</code> is picked just because its matcher matches.
5. **Check the filter processing URI** of <code>OAuth2LoginAuthenticationFilter</code> inside the selected chain to ensure it matches the callback.
6. **Verify the authorization start URL** and confirm <code>OAuth2AuthorizationRequestRedirectFilter</code> sits in the right chain with the right base URI.
7. **Check state/session**, cookies, and the authorization request repository if the filter ran the callback yet authentication failed.
8. **Check token exchange / ID Token validation errors** once callback routing and sessions are confirmed healthy.

A hand-crafted test request with <code>code=abc</code> will naturally fail because the code is invalid. That **does not prove the callback filter is broken**. End-to-end login testing requires running a real flow with a test Authorization Server or dev environment.

### 10.3. Error and resolution table

| Symptom | Where to check | Resolution |
|---|---|---|
| Callback returns 404, no login processing | No chain matches, or selected chain lacks OAuth2 Login filter | Expand `securityMatcher` to cover callback or use web fallback |
| Callback returns 401 with HTTP Basic challenge | API/basic chain has too broad a matcher and ran before web chain | Narrow API chain; fix `@Order` scopes |
| Callback returns 403 | Authorization rule in selected chain, CSRF on custom callback method, or another handler | Check chain first, then method/filters and authorization |
| Login redirect loop | Login/start/callback pages belong to different chains, or auth not saved/loaded for target page | Check routing, session, `SecurityContextRepository`, and success URL |
| Provider reports <code>redirect_uri_mismatch</code> | Wrong redirect URI in `ClientRegistration` or IdP | Sync template, actual URL, scheme/host/path |
| OAuth2 Login filter receives callback, yet reports state error | Lost session cookie, missing authorization request, or wrong state | Check cookies, session store, and whether callback belongs to same flow |
| Token endpoint returns <code>invalid_grant</code> | Wrong/expired/reused code, invalid redirect URI/PKCE | Troubleshoot token exchange after confirming callback hits right chain |
| Authentication succeeds, yet user is still anonymous | Target page chain differs from callback chain, or mismatched session/security context policy | Check persistence and matcher of subsequent request |
| Authorization start URL returns 404 | Start path outside chain containing <code>OAuth2AuthorizationRequestRedirectFilter</code> | Bring start URL into right chain and check custom authorization base URI |
| Web chain is never selected | Catch-all chain has higher priority (`@Order`) | Put specific chains first, fallback chain last |

## 11. Misconceptions to Avoid

**"Just add permitAll for the callback."** Not enough. <code>permitAll</code> governs authorization after a chain has been selected. The chain must also match the callback URL and contain the callback-handling filter.

**"If a request matches two chains, both chains run."** False. <code>FilterChainProxy</code> uses the first match; subsequent chains are never evaluated.

**"If the provider redirects to the right URL, Spring Security will definitely handle it."** False. Provider URL, `ClientRegistration` redirect URI, `securityMatcher`, and the OAuth2 Login filter's processing URI must all align.

**"We can move the callback to the stateless API chain because it's just a GET URL."** The callback needs state/authorization request retrieval and OAuth2 Login authentication mechanics. Putting it in a JWT-bearer-only chain breaks the flow.

**"Matching /app/** in the web chain is enough for logging into /app pages."** False if authorization initiation and callbacks sit outside <code>/app/**</code>. The chain's scope must cover those supporting login endpoints too.

**"Any chain at the bottom is safe because unmatched requests are auto-protected by the framework."** Not guaranteed. If no chain matches a request, Spring Security applies none of its security filters to that request. A fallback chain with an explicit policy avoids unintended gaps.

**"`@Order` only affects speed."** False. It changes which authentication policies apply, which filters activate, and whether OAuth2/OIDC Login can complete.

## 12. Practice Exercises

### Exercise 1 — Identify which chain handles each request

Given three chains:

~~~text
Chain A: @Order(1), securityMatcher("/api/**"), JWT resource server
Chain B: @Order(2), securityMatcher("/app/**"), oauth2Login()
Chain C: @Order(3), catch-all, denyAll
~~~

Which chain receives the default callback <code>/login/oauth2/code/company</code>?

**Explanation:** The callback matches neither A nor B and falls into C. Because C has no OAuth2 Login callback filter, login will not complete. Add <code>/login/oauth2/code/**</code> and <code>/oauth2/authorization/**</code> to B's `securityMatcher` (along with any needed login paths), or make B the web fallback and redesign C.

### Exercise 2 — Overlapping matchers

Given:

~~~text
Chain A: @Order(1), securityMatcher("/login/**"), httpBasic()
Chain B: @Order(2), securityMatcher("/login/oauth2/code/**"), oauth2Login()
~~~

Which chain processes <code>/login/oauth2/code/company</code>?

**Explanation:** Chain A matches first. Chain B never runs. Instead of editing <code>permitAll</code>, narrow A's matcher so it does not capture the callback, or move HTTP Basic to a separate namespace.

### Exercise 3 — Customizing the callback

An application wants the callback <code>/sso/callback/{registrationId}</code>. Identify the places to update:

1. <code>ClientRegistration.redirectUri</code>: <code>{baseUrl}/sso/callback/{registrationId}</code>.
2. <code>oauth2Login().redirectionEndpoint().baseUri("/sso/callback/*")</code>.
3. The OIDC chain's <code>securityMatcher</code> must include <code>/sso/callback/**</code>.
4. Configure allowed redirect URIs at the IdP, e.g., <code>https://app.example.org/sso/callback/company</code>.

If the app has a proxy or context path, verify the actual URL seen by the browser and Authorization Server as well.

### Exercise 4 — Lost session after redirect

Both the start URL and callback hit the right web chain, yet the callback reports the authorization request cannot be found. List three things to check.

**Answer hint:** (1) whether the browser sends back the session cookie when returning from the IdP; (2) whether the session exists on the instance handling the callback, especially behind a load balancer; (3) whether a custom authorization request repository or cookie config dropped <code>state</code>, the authorization request, or the PKCE verifier. Do not tweak chains when chain routing is already right.

### Exercise 5 — Reading diagrams and designing a fallback

Design an application with these URLs:

~~~text
/api/orders
/app/dashboard
/oauth2/authorization/company
/login/oauth2/code/company
/health
~~~

Requirements: API uses JWT, web uses OIDC Login, and <code>/health</code> is accessed only under a dedicated operational policy. Put the API chain first, the web chain next, and either an explicit chain/matcher for health or place health under a controlled fallback. Draw a path-to-chain mapping table and determine the callback chain before writing Java config.

## 13. Core Takeaways Summary

In Spring Security Servlet, **<code>SecurityFilterChain</code> selection precedes every authorization decision and filter execution inside the chain**. <code>securityMatcher</code> decides which chain gets to handle a request; <code>requestMatchers</code> decides access permissions after the chain is chosen.

For OAuth 2.0/OIDC Login, account for **both the authorization start endpoint and the callback endpoint** in addition to application pages. If enabling <code>oauth2Login()</code> on a chain scoped to <code>/app/**</code>, include the login infrastructure endpoints in that chain's scope or use the web chain as an appropriate fallback. Always verify <code>@Order</code>: a request matching an earlier chain never runs later chains.

When customizing callbacks, synchronize the **redirect URI in ClientRegistration**, **registration at the IdP**, **<code>redirectionEndpoint().baseUri()</code>**, and **<code>securityMatcher</code>** on the chain containing OAuth2 Login. After routing, check session/state, token exchange, and OIDC ID Token validation for complete diagnostics.

### References

- **Spring Security Reference — Servlet Architecture:** <code>FilterChainProxy</code>, <code>SecurityFilterChain</code>, matching order, and multiple filter chains.
- **Spring Security Reference — Java Configuration / HttpSecurity:** <code>securityMatcher</code>, <code>authorizeHttpRequests</code>, and <code>requestMatchers</code>.
- **Spring Security Reference — OAuth2 Login (Servlet):** authorization endpoint, redirection endpoint, callback filter, and authorization request repository.
- **Spring Security Java API:** <code>OAuth2AuthorizationRequestRedirectFilter</code>, <code>OAuth2LoginAuthenticationFilter</code>, <code>HttpSessionOAuth2AuthorizationRequestRepository</code>, and <code>SecurityFilterChain</code>.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Authorization Code Grant, redirect URI, and token requests.
- **OpenID Connect Core 1.0:** Authorization Code Flow, ID Token, and OIDC validation rules.
