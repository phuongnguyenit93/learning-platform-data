# Customizing Login Results, Callback Errors, and the Provider Selection Page

## 1. Objectives, Scope, and Context

A **Spring Security Reactive (Spring WebFlux)** application may let users log in with multiple identity providers (IdPs): an employee provider, an enterprise customer provider, or a public OIDC provider. Once the user chooses a provider, the browser is sent to the IdP; after authentication completes, the IdP sends the browser back to the application's **callback**. The end result is not just “did login succeed or not”, but also:

- Displaying a **provider selection page** with only permitted client registrations.
- Handling **successful login**: saving `Authentication`, picking a valid redirect target, and preserving the UX of returning to the requested resource.
- Handling **failed login**: bad tokens, user-canceled consent, state mismatch, misconfigured redirect URI, or unresponsive IdP; showing a friendly message without exposing codes/tokens/internal exceptions.
- Ensuring the browser retains **`WebSession`** across the login-initiation request and the callback request.
- Distinguishing a plain OAuth 2.0 callback success from **OpenID Connect** authentication with an ID token.
- Testing decisions and redirects in **WebFlux** without mixing Servlet APIs.

This lesson focuses on **“Customizing login results, callback errors, and the provider selection page”**, in the **OAuth2/OIDC Login** chapter of the **Spring Security - reactive** module.

After this lesson, you will be able to:

1. Draw the authorization code flow from `/signin` → `/oauth2/authorization/{registrationId}` → IdP → `/login/oauth2/code/{registrationId}` → success/failure.
2. Distinguish **authentication entry point**, **authorization request resolver**, **callback authentication filter**, **success handler**, and **failure handler**.
3. Use `ServerHttpSecurity.oauth2Login(...)` with `ServerAuthenticationSuccessHandler` / `ServerAuthenticationFailureHandler` and `RedirectServerAuthenticationEntryPoint`.
4. Design a provider selection page that reads `ClientRegistration` entries from the repository, renders only server-allowed registration IDs, and escapes HTML.
5. Use `RedirectServerAuthenticationSuccessHandler` and understand why a **saved request** can take precedence over the fallback destination.
6. Return callback errors using a safe public error code without reflecting raw `error_description` or `AuthenticationException.getMessage()`.
7. Distinguish `state`, PKCE, OIDC `nonce`, redirect URI, issuer, audience, and session binding; avoid “fixing” callback errors by disabling security checks.
8. Run a Spring Boot 3.5.x/Java 17+ project with two mock providers to **test offline** the provider chooser page and authorization redirects, unit-test success/failure handlers independently, and know how to wire a real IdP for end-to-end testing.
9. Identify the limits of mock callbacks, real IdP integration tests, and production requirements for HTTPS, cookies, proxies, logging, and account linking.

**Version scope:** Java code applies to **Spring Boot 3.x, Spring Security 6.5.x, Java 17+**, inbound **WebFlux**. Spring Security 7.x may change APIs/behavior; always check the dependency tree and Javadocs of the version you use. Only classes in `org.springframework.security.web.server...` and `ServerHttpSecurity` belong to inbound reactive code; never copy Servlet's `HttpSecurity.oauth2Login().loginPage(...)` or `AuthenticationSuccessHandler` here.

## 2. Background Mechanics: What Role Does the Application Play?

### 2.1. OAuth 2.0 Client vs. OIDC Login vs. Resource Server

A website application that lets users log in via an IdP is an **OAuth 2.0 Client** using the Authorization Code Flow. When the registration includes the `openid` scope and the IdP supports OIDC, Spring Security uses **OIDC login** components to verify the ID token/claims and build identity. Without `openid`, OAuth2 login can rely on the UserInfo endpoint per provider strategy.

Do not confuse the three roles:

| Role | Function |
|---|---|
| OAuth 2.0 Client / OIDC Relying Party | Sends browser to IdP, exchanges code for tokens, establishes `Authentication` for the website |
| Authorization Server / OpenID Provider | Authenticates users, issues authorization codes, tokens, ID tokens, and metadata |
| Resource Server | Protects APIs based on access tokens in requests; not itself a website login page |

An application can act as both client and resource server, but **`oauth2Login` differs from `oauth2ResourceServer`**. This lesson covers browser login via authorization codes and callbacks, not validating Bearer JWTs on every API request.

### 2.2. Two Easily Confused Default URLs

For a `ClientRegistration` with `registrationId = "alpha"`:

- **Initiate login:** `GET /oauth2/authorization/alpha`. This is a URL **on the application**, handled by Spring Security to build the authorization request and redirect the browser to the IdP.
- **Receive callback:** `GET /login/oauth2/code/alpha`. This is the **application's** redirect URI, where the IdP sends the user back after authenticating/canceling/denying.

Default template used in registrations:

```text
{baseUrl}/login/oauth2/code/{registrationId}
```

`{baseUrl}` is computed from the application's effective address (scheme, host, port, context path depending on environment and framework). When deployed behind a reverse proxy, ensure this address matches the redirect URI registered with the IdP. Never change the callback path only at the IdP while forgetting `ClientRegistration.redirectUri` and Spring Security's matcher.

### 2.3. Complete Login Flow

```text
1. Browser: GET /private
      |
      v
   Authorization requires authenticated
      |
      v
   RedirectServerAuthenticationEntryPoint -> 302 /signin

2. Browser: GET /signin
      |
      v
   Chooser page:
      "Alpha Identity" -> /oauth2/authorization/alpha
      "Beta Identity"  -> /oauth2/authorization/beta

3. Browser: GET /oauth2/authorization/alpha
      |
      v
   OAuth2AuthorizationRequestRedirectWebFilter
   DefaultServerOAuth2AuthorizationRequestResolver
      |
      +-- resolve ClientRegistration "alpha"
      +-- generate random state (and other params as appropriate)
      +-- save authorization request to match callback
      +-- redirect browser -> IdP authorization endpoint

4. Browser at IdP:
      -> authenticate / consent / select account
      -> IdP redirects browser back to app callback

5. Browser: GET /login/oauth2/code/alpha?code=...&state=...
      |
      v
   Reactive authentication flow:
      -> load saved authorization request
      -> verify correlation (state, client, redirect ...)
      -> exchange code with token endpoint
      -> if OIDC: validate ID token/claims via corresponding components
      -> obtain verified Authentication
      |
      +-- SUCCESS
      |     -> save security context per strategy
      |     -> ServerAuthenticationSuccessHandler
      |     -> redirect saved URL or /home
      |
      +-- FAILURE
            -> ServerAuthenticationFailureHandler
            -> redirect /signin?error=oauth2
            -> public message without code/token/stacktrace
```

This is a **conceptual diagram**, not a guarantee of internal filter ordering across every version/provider. The callback carries `error=access_denied` instead of `code` if the user cancels or the IdP denies access. Never call the token endpoint manually from a callback controller; Spring Security already provides the authentication pipeline.

## 3. Provider Selection Page: Default vs. Custom

### 3.1. Default Page Generated by Spring Security

When OAuth2 Login is enabled with no custom login page, Spring Security Reactive can use `LoginPageGeneratingWebFilter` to generate an automatic login page listing configured OAuth Clients.

The default page takes display labels from `ClientRegistration.clientName` and renders links like:

```html
<a href="/oauth2/authorization/google">Google</a>
```

Important requirement: the repository used to discover clients for the **generated page** must support iterating via `Iterable<ClientRegistration>`. `InMemoryReactiveClientRegistrationRepository` implements both `ReactiveClientRegistrationRepository` and `Iterable<ClientRegistration>`. If you use a pure reactive repository exposing only `findByRegistrationId(...)`, the default page may fail to list providers as expected.

The generated page is great for quick experiments. A real product needs branding/logos, account-usage descriptions, accessibility, error display, i18n, tenant selection, and safety rules.

### 3.2. WebFlux Custom Page: Different from Servlet

For Spring Security Reactive 6.5, documentation guides custom login pages via:

```java
.exceptionHandling(ex -> ex
    .authenticationEntryPoint(
        new RedirectServerAuthenticationEntryPoint("/signin")))
.oauth2Login(oauth -> oauth
    // Required OIDC/OAuth2 configurations.
)
```

This is a **configuration fragment**, not a standalone class. You must provide a controller serving `GET /signin` and permit that route in authorization rules. Do not look for Servlet's `.loginPage("/signin")` in `OAuth2LoginSpec` and copy it blindly: the **WebFlux** approach is a custom `ServerAuthenticationEntryPoint` and an application-rendered page.

By keeping `/oauth2/authorization/{registrationId}` at its default, you do not need a custom authorization request resolver just to change the provider selection UI. If you want to change the login-initiation URL, configure `ServerOAuth2AuthorizationRequestResolver` with a matching exchange matcher and update all links; never just change the link HTML and assume Spring Security will follow automatically.

### 3.3. Data Source for the Selection Page

A trustworthy strategy:

1. Read the list of configured registrations **on the server**, never from a client-supplied `?providerUrl=...` query param.
2. Use stable `registrationId` values containing only allowed characters, or URL-encode the path segment.
3. Render only providers permitted for the current **tenant or business context** in multi-tenant apps; never turn a user-entered provider into a trusted endpoint.
4. Escape names/labels for HTML context to prevent XSS if configs ever hold untrusted values.
5. Never put `clientSecret`, access tokens, refresh tokens, JWKS private keys, or OIDC ID tokens onto the page.
6. Link to the local relative path `/oauth2/authorization/{registrationId}`, **never** directly to an authorize URL supplied arbitrarily by the client.
7. Consider accessibility: real `<a>` links, clear names, keyboard focus, and `role="alert"` on error messages.
8. When a provider is deprecated or employee-only, enforce hide/allow via server-side policy; merely hiding it in the UI is insufficient to block that provider's OAuth2 start endpoint.

### 3.4. Never Create an Open Redirect

A dangerous pattern:

```text
/signin?next=https://attacker.example/collect
```

If login succeeds and the success handler calls `redirect(next)` without validating origin/target, an attacker can send users to a phishing site, steal info via URLs, or cause OAuth flow confusion.

In the demo code, the redirect target is **fixed** to `/home`, with optional precedence for Spring Security's managed saved request. If real business needs require `returnTo`, accept only valid local paths from an allowlist, forbid schemes/hosts/`//`/encoded bypasses, normalize the URI, and test for open redirects. Never reflect raw `Referer` or `redirect_uri` from requests as the post-login redirect target.

## 4. Customization Points: Entry Point, Success Handler, and Failure Handler

### 4.1. Authentication Entry Point: Not Yet Logged In

`ServerAuthenticationEntryPoint` runs when a request reaches a protected resource **without a valid Authentication**. For browser websites, we usually redirect to the provider selection page:

```java
ServerAuthenticationEntryPoint entry =
    new RedirectServerAuthenticationEntryPoint("/signin");
```

This is a code snippet; import `org.springframework.security.web.server.ServerAuthenticationEntryPoint` and `org.springframework.security.web.server.authentication.RedirectServerAuthenticationEntryPoint`. It differs from a failure handler: lacking login **is not the same** as a failed OAuth2 login attempt.

Examples:
- Anonymous hits `GET /private` → redirects to `/signin`.
- Authenticated user lacking a role → normally 403, **not** always a login redirect.
- SPA/API clients typically prefer 401 JSON over HTML redirects; **separate security chains/entry points** may be needed for UI vs. APIs.

### 4.2. ServerAuthenticationSuccessHandler: Successful Callback

In Spring Security WebFlux:

```java
public interface ServerAuthenticationSuccessHandler {
    Mono<Void> onAuthenticationSuccess(
        WebFilterExchange webFilterExchange,
        Authentication authentication);
}
```

This is an **API description**; do not declare the interface in your project. The handler runs after authentication succeeds in the corresponding flow. It can redirect, record an audit category, or pick a safe landing page; it **must never trust client-asserted authentication results**.

DSL:

```java
.oauth2Login(oauth2 -> oauth2
    .authenticationSuccessHandler(
        new RedirectServerAuthenticationSuccessHandler("/home")))
```

`RedirectServerAuthenticationSuccessHandler("/home")` uses `/home` as a **fallback**. Per Javadoc, the handler normally prioritizes a **saved request** cached before login if present; otherwise it redirects to `/home`. So do not read the constructor and conclude “every login always goes to /home”.

If requirements demand **always redirecting to `/home` regardless of saved request**, explicitly disable/skip the request cache on the handler or across the security chain, e.g.:

```java
RedirectServerAuthenticationSuccessHandler handler =
    new RedirectServerAuthenticationSuccessHandler("/home");
handler.setRequestCache(NoOpServerRequestCache.getInstance());
```

This is an **illustrative snippet** for specialized configs; import `NoOpServerRequestCache`. The trade-off is that users may not return to their originally requested protected URL. Never write a handler that saves `returnUrl` from an unvalidated query parameter.

### 4.3. ServerAuthenticationFailureHandler: Failed Callback / Login Attempt

WebFlux contract:

```java
public interface ServerAuthenticationFailureHandler {
    Mono<Void> onAuthenticationFailure(
        WebFilterExchange webFilterExchange,
        AuthenticationException exception);
}
```

Example:

```java
.oauth2Login(oauth2 -> oauth2
    .authenticationFailureHandler(
        new RedirectServerAuthenticationFailureHandler(
            "/signin?error=oauth2")))
```

It sends the user back to a **friendly error page** after an authentication attempt handled by the login filter fails. The query param `error=oauth2` is a **fixed server-chosen code**, not taken from the IdP. The `/signin` page renders only a generic message; never reflect raw `error_description`, `code`, `state`, `id_token`, `access_token`, or `exception.getMessage()`.

The 6.5 Javadoc for `OAuth2LoginSpec` notes the default failure handler is `RedirectServerAuthenticationFailureHandler` redirecting to `/login?error`. When introducing a custom page, update the failure target as well to avoid redirecting to an obsolete default page.

### 4.4. Differences in Timing and Failure Modes

| Scenario | Primary Handler/Component | UI Behavior |
|---|---|---|
| Anonymous hits `/private` | Authentication entry point | Redirects to `/signin` |
| User clicks provider link | Authorization-request redirect filter | Redirects to IdP |
| Valid callback, tokens/user verified | OAuth2 authentication filter/manager + success handler | Redirects to saved URL or `/home` |
| Callback handled by filter but auth failed | Failure handler | Redirects to `/signin?error=oauth2` |
| Authenticated user lacks permission | Authorization + access denied handler | 403 or flow per client type |
| IdP URL unresponsive in browser | Browser/network/IdP, no callback yet | Server-side failure handler may not run |
| Route/callback config misses filter | Different router/chain or 404 | Unlikely to hit success/failure handlers |
| Server error outside `AuthenticationException` | Error handling/container | May return 5xx, not always OAuth2 failure redirect |

**Avoid a major misconception:** not every failing `/login/oauth2/code/...` request goes through `ServerAuthenticationFailureHandler`. If the request misses the matcher, hits another chain, or fails outside an authentication attempt, handling may go to an exception filter, 404, or error handler. Test each error type accurately.

### 4.5. Do Not Call subscribe() Inside Handlers

A custom handler pattern:

```java
ServerAuthenticationSuccessHandler handler =
    (exchange, authentication) -> {
        return auditService.recordLogin(authentication.getName())
            .then(new RedirectServerAuthenticationSuccessHandler("/home")
                .onAuthenticationSuccess(exchange, authentication));
    };
```

This is a **snippet** requiring an `auditService` returning `Mono<Void>`. Never call `auditService.recordLogin(...).subscribe()` and return a redirect independently: that detaches error handling, cancellation, and lifecycle. If the audit backend fails, explicitly decide fail-open vs. fail-closed for login rather than silently dropping logins or leaking tokens in logs.

For critical auditing, use a proper queue/outbox system rather than making synchronous calls inside the handler that could time out the callback.

### 4.6. Success Handler List in 6.3+

`OAuth2LoginSpec.authenticationSuccessHandler(...)` has an overload taking a single `ServerAuthenticationSuccessHandler` and an overload taking `Consumer<List<ServerAuthenticationSuccessHandler>>` since Spring Security 6.3. Javadoc warns that the single-handler setter can **replace/clear** handlers added via the list overload. This matters for other mechanisms such as session-concurrency/registration.

If your app uses an OIDC session registry, maximum sessions, or event handlers, review **the entire list of success handlers** and their ordering when configuring custom redirects. Never assume the single-handler setter preserves other handlers; test logout/session tracking and framework upgrades.

## 5. OAuth2/OIDC Callbacks and Where Things Can Break

### 5.1. Default Callback URL

For `registrationId="alpha"`:

```text
Application authorization start:
  GET /oauth2/authorization/alpha

IdP callback to application:
  GET /login/oauth2/code/alpha?code=...&state=...
```

`code` is a short-lived, typically single-use authorization code. `state` binds the response to the previously initiated authorization request to mitigate CSRF/login injection/response mix-up. These are **sensitive values**; never write raw values to additional logs/URLs or display them on error pages.

### 5.2. Authorization Request Repository and WebSession

At login start, `OAuth2AuthorizationRequestRedirectWebFilter` builds an authorization request, typically with a random `state` and optional PKCE/OIDC parameters. `ServerAuthorizationRequestRepository` saves the request for comparison at callback. In Spring Security Reactive, the default implementation is `WebSessionOAuth2ServerAuthorizationRequestRepository`.

Consequences:

- The browser must retain the same `WebSession`/cookie between login start and callback.
- If the browser blocks cookies, `WebSession` expires, the user switches profiles/incognito, or a load balancer routes to another node without a shared store, state correlation fails.
- Users may open multiple tabs and start logins in parallel; test actual repository and browser behavior rather than assuming unlimited concurrent authorization requests are stored.
- With SameSite cookies, top-level GET callbacks usually work with `Lax` in most browsers; if the IdP uses `response_mode=form_post`, cookie semantics differ and require strict evaluation.
- Never “fix state mismatch” by disabling state validation or accepting callbacks when the authorization request does not exist.

### 5.3. Common Failure Points

| Failure Point | Example | Safe Handling |
|---|---|---|
| User at IdP | Cancels login/consent, IdP returns `error=access_denied` | Generic message; let user pick another provider or retry |
| Authorization request | Missing/disallowed `registrationId` | Never redirect to user-entered URL; render error/generic 404 |
| Correlation | Missing/wrong/replayed `state` or session mismatch | Reject, never skip check; debug cookies/session |
| Redirect URI | IdP reports `redirect_uri_mismatch` | Cross-check registration, app `baseUrl`, HTTPS/proxy |
| Authorization code | Expired, reused, rejected by token endpoint | Never retry with old code; start a new authorization flow |
| Client authentication | Wrong client-id/secret, expired secret | Fix config/secret manager; never log secret |
| PKCE | `code_verifier` fails to match `code_challenge` | Never disable PKCE if required by policy/client; check session/repo |
| OIDC ID token | Invalid signature/JWK/issuer/audience/nonce/time | Deny; inspect IdP metadata and bounded clock skew |
| UserInfo | Endpoint 401/403/timeout, missing data | Never create user from unverified claims; handle error |
| Authentication persistence | Login succeeds but session/context missing on next request | Check `ServerSecurityContextRepository` read/write |
| Network | IdP unreachable, proxy timeout | Error page supporting controlled retry, observability |
| Security chain | Callback 404 or redirect loop | Check matchers, routes, chain order, context path |
| Browser | Cookie blocked/replaced, wrong SameSite | Inspect DevTools cookies and redirect chain |
| Multiple replicas | Node B doesn't see request saved on node A | Shared WebSession store / distributed session strategy |

### 5.4. OIDC vs. OAuth2 UserInfo

In OIDC, the ID token holds user authentication claims and must be verified for issuer, audience, expiry, signature, and flow-specific parameters. Scope `openid` signals OIDC in Spring Security; `profile` and `email` scopes grant claim access, **never automatically creating `ROLE_ADMIN`**.

Never use unverified emails as an account-linking key. Stable identifiers should rely on `iss + sub` or an equivalent trusted mapping. Two IdPs can emit the same `sub` string; storing only `sub` without issuer/provider context risks mixing identities. Never escalate privileges based on email domain or unvalidated claims.

### 5.5. Provider Redirect Errors Are Not Always “Server Callback Failures”

If the browser cannot reach the IdP page, DNS fails, or the user closes the tab before the callback, the backend may never receive a callback request. `authenticationFailureHandler` knows nothing about that event. The UI should help users retry; monitoring can track initiation-to-callback ratios with safe correlation (never logging raw codes/states).

## 6. Post-Login Redirects: Saving Intent and Avoiding Dangerous Redirects

### 6.1. Saved Request

An unauthenticated user opens `/reports/2026`, the security chain requires authentication, and the request cache may save the original URL in `WebSession`. After OAuth2 login, `RedirectServerAuthenticationSuccessHandler` can redirect the user back to the saved URL instead of the `/home` fallback.

```text
GET /reports/2026
  -> redirect /signin
  -> user chooses Alpha
  -> browser /oauth2/authorization/alpha
  -> IdP login and callback succeed
  -> success handler:
       if valid saved request => /reports/2026
       otherwise              => /home
```

This is the **behavior when the request cache is configured/applicable**; it does not guarantee every request is cached. An API `POST` with a large body should not be naively “replayed” via redirect under unsafe assumptions. Inspect `WebSessionServerRequestCache` and your app's policy.

### 6.2. Fallback Landing Page

`RedirectServerAuthenticationSuccessHandler("/home")` specifies the fallback destination. Use a fixed local relative path instead of a user-supplied external URL. If the product routes admins vs. customers differently, use verified claims/authorities and a server-side allowlist; never trust `role=admin` on a callback query param.

### 6.3. Login Completes, Yet Authentication Isn't Saved

If the callback authenticates and the handler redirects successfully, yet the next request is anonymous again, check:

- Are `OAuth2LoginSpec.securityContextRepository(...)` (saves after OAuth2 login) and `ServerHttpSecurity.securityContextRepository(...)` (loads into Reactor context) using compatible strategies?
- Did the browser keep the session cookie issued by the app?
- Did the session ID rotate after login? The browser must send the **new cookie**.
- Does the multi-node app have a shared session store?
- Are different security chains using stateful vs. no-op repositories?

**Never** “fix” this by passing tokens in URL query params to `/home`. OAuth2/OIDC tokens must remain in proper storage with controlled access/expiry, never reflected into browser URLs or logs.

### 6.4. RedirectURI and Behind-Proxy

The IdP compares `redirect_uri` against its registered allowlist. If the external site is `https://app.example` while the Spring backend sees `http://service:8080`, `{baseUrl}` can be wrong.

Configure forwarded headers **trusting only verified reverse proxies**, proper TLS termination, and exact host/port/context path, then register the matching IdP callback. Never trust `Host`/`X-Forwarded-Host` supplied by public clients to build arbitrary redirects.

## 7. Runnable Java 17+ WebFlux Project, Tested Offline Without a Real IdP

The example uses **two mock registrations** solely to demonstrate:

- `/signin` rendering the Alpha/Beta list with safe links.
- Requests `/oauth2/authorization/alpha` and `/oauth2/authorization/beta` redirecting to fake IdP endpoints with `state`.
- Protected `/private` redirecting to `/signin`.
- `ServerAuthenticationSuccessHandler` / `ServerAuthenticationFailureHandler` producing proper redirects without exposing exception details.
- A **real successful callback** cannot complete against fake IdP hostnames because there is no real authorization/token/JWKS server. End-to-end tests need a real IdP or a trusted test IdP server.

This boundary lets the code **boot and test customizations** without faking a callback that bypasses OIDC validation. Only after replacing endpoints and credentials with real provider settings does the application support end-to-end login.

### 7.1. Dependencies and Structure

Create a Gradle Groovy project from [Spring Initializr](https://start.spring.io/) with Java 17+, Spring Boot 3.5.x, and starters:
- Spring Reactive Web.
- Spring Security.
- OAuth2 Client.
- Spring Boot Starter Test, Spring Security Test, Reactor Test.

The `dependencies` block in `build.gradle` generated by Initializr:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

This is **only the dependencies block**, not a full Gradle file. Keep Gradle plugins, toolchain, and repositories from Initializr. Avoid `spring-boot-starter-web` when the inbound stack must be WebFlux, because when both MVC and WebFlux are present, Boot 3.x defaults to Servlet MVC.

Layout:

```text
src/main/java/demo/oauthlogin/
  OidcLoginApplication.java
  SecurityConfig.java
  LoginRedirects.java
  ProviderPageController.java
  PagesController.java
src/test/java/demo/oauthlogin/
  OAuthLoginWebTests.java
  LoginRedirectHandlerTests.java
```

### 7.2. OidcLoginApplication.java

```java
package demo.oauthlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OidcLoginApplication {

    public static void main(String[] args) {
        SpringApplication.run(OidcLoginApplication.class, args);
    }
}
```

### 7.3. SecurityConfig.java: Client Registrations and WebFlux Security

```java
package demo.oauthlogin;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationEntryPoint;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    public SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET,
                    "/", "/signin").permitAll()
                .pathMatchers(HttpMethod.GET,
                    "/oauth2/authorization/**").permitAll()
                .pathMatchers(HttpMethod.GET,
                    "/login/oauth2/code/**").permitAll()
                .pathMatchers(HttpMethod.GET,
                    "/home", "/private").authenticated()
                .anyExchange().denyAll()
            )
            .exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint(
                    new RedirectServerAuthenticationEntryPoint("/signin")))
            .oauth2Login(oauth2 -> oauth2
                .authenticationSuccessHandler(LoginRedirects.success())
                .authenticationFailureHandler(LoginRedirects.failure()))
            .formLogin(form -> form.disable())
            .httpBasic(basic -> basic.disable())
            .build();
    }

    @Bean
    public InMemoryReactiveClientRegistrationRepository registrations() {
        return new InMemoryReactiveClientRegistrationRepository(
            demo("alpha", "Alpha Identity",
                "https://login.alpha.example.test"),
            demo("beta", "Beta Identity",
                "https://login.beta.example.test")
        );
    }

    private ClientRegistration demo(
            String id, String display, String base) {
        return ClientRegistration.withRegistrationId(id)
            .clientId(id + "-demo-client")
            .clientSecret("not-a-real-secret")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("openid", "profile", "email")
            .authorizationUri(base + "/authorize")
            .tokenUri(base + "/token")
            .jwkSetUri(base + "/jwks")
            .userInfoUri(base + "/userinfo")
            .userNameAttributeName("sub")
            .clientName(display)
            .build();
    }
}
```

**Important warning:** the `.example.test` hosts, client IDs, and client secrets above are **dummy data with no real IdP**, solely for testing locally generated authorization redirects. Never use them in production and never treat receiving a 302 as a completed login. For real integration, register an OAuth/OIDC client with an IdP, replace the endpoints, supply `clientId`/`clientSecret` from a secret manager/env, and configure valid issuer/JWKS and HTTPS callbacks. For OIDC, provider metadata and ID token validation must be genuinely verified, never accepting unsigned tokens.

The configuration above:

1. Permits `GET /signin` and `/oauth2/authorization/**` so the browser can select/start login.
2. Allows callbacks to reach the OAuth2 authentication filter; `permitAll` on the callback **does not allow skipping state/ID token validation**. The security authentication filter still processes the callback before authorization controllers in a properly ordered chain.
3. Protects `/home` and `/private`.
4. Redirects anonymous requests to `/signin` via the entry point.
5. Customizes success/failure redirects via `LoginRedirects`.
6. Keeps default CSRF protection enabled and disables Basic/Form Login. OAuth2 callbacks default to GET; if using POST response mode, review matchers/cookies/CSRF specifically.
7. Both `ClientRegistration` entries are OIDC due to the `openid` scope, though the demo cannot verify ID tokens without a real IdP.
8. `InMemoryReactiveClientRegistrationRepository` implements `Iterable<ClientRegistration>`, making it convenient to render the provider page.

### 7.4. LoginRedirects.java: Shared Success/Failure Targets

```java
package demo.oauthlogin;

import org.springframework.security.web.server.authentication.RedirectServerAuthenticationFailureHandler;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationSuccessHandler;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;
import org.springframework.security.web.server.authentication.ServerAuthenticationSuccessHandler;

public final class LoginRedirects {

    private LoginRedirects() {
    }

    public static ServerAuthenticationSuccessHandler success() {
        // Saved request (if present) takes precedence over fallback /home.
        return new RedirectServerAuthenticationSuccessHandler("/home");
    }

    public static ServerAuthenticationFailureHandler failure() {
        // Always use a fixed error code; never echo IdP/error details.
        return new RedirectServerAuthenticationFailureHandler(
            "/signin?error=oauth2");
    }
}
```

This file holds shared logic for configuration and unit tests. When adding auditing, wrap/compose the handler with `Mono<Void>`, never calling `subscribe()` on a detached side effect.

Never construct a response body containing tokens on success. The redirect target is a fixed **local path**; saved request URIs must be managed within the framework's request cache/allowlist, never taken directly from request query params.

### 7.5. ProviderPageController.java: Rendering Providers from the Repository

```java
package demo.oauthlogin;

import java.util.Comparator;
import java.util.List;
import java.util.Set;
import java.util.stream.StreamSupport;

import org.springframework.http.MediaType;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryReactiveClientRegistrationRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.util.HtmlUtils;
import reactor.core.publisher.Mono;

@RestController
public class ProviderPageController {

    private static final Set<String> ALLOWED =
        Set.of("alpha", "beta");

    private final InMemoryReactiveClientRegistrationRepository clients;

    public ProviderPageController(
            InMemoryReactiveClientRegistrationRepository clients) {
        this.clients = clients;
    }

    @GetMapping(value = "/signin",
                produces = MediaType.TEXT_HTML_VALUE)
    public Mono<String> signIn(
            @RequestParam(name = "error", required = false)
            String error,
            ServerWebExchange exchange) {

        exchange.getResponse().getHeaders()
            .setCacheControl("no-store");

        List<ClientRegistration> providers =
            StreamSupport.stream(clients.spliterator(), false)
                .filter(c -> ALLOWED.contains(c.getRegistrationId()))
                .sorted(Comparator.comparing(
                    ClientRegistration::getClientName))
                .toList();

        StringBuilder html = new StringBuilder("""
            <!doctype html>
            <html lang="en">
            <head><meta charset="utf-8">
            <title>Choose sign-in account</title></head>
            <body>
            <h1>Choose an identity provider</h1>
            """);

        if ("oauth2".equals(error)) {
            html.append("""
                <p role="alert">Unable to complete sign-in.
                Please try again or contact support.</p>
                """);
        }

        html.append("<ul>");
        for (ClientRegistration c : providers) {
            String id = c.getRegistrationId();
            // Allow only fixed registrationIds from ALLOWED.
            html.append("<li><a href=\"/oauth2/authorization/")
                .append(id)
                .append("\">")
                .append(HtmlUtils.htmlEscape(c.getClientName()))
                .append("</a></li>");
        }
        html.append("</ul></body></html>");

        return Mono.just(html.toString());
    }
}
```

This is a **standalone Java 17+ controller**:

- `ALLOWED` is a server-side allowlist. This does not replace policy at the authorization endpoint; for multi-tenant apps, enforce a matching server-side policy permitting login initiation rather than merely hiding the link.
- Uses `StreamSupport` because the demo repository implements `Iterable<ClientRegistration>`. For a repository implementing only `ReactiveClientRegistrationRepository` without `Iterable`, redesign how the provider list is sourced safely (e.g., dedicated config/service). **Never blindly cast** an arbitrary repository to `Iterable`.
- `HtmlUtils.htmlEscape` prevents injecting unescaped provider names into HTML.
- `registrationId` comes strictly from the safe-character allowlist; for non-static provider IDs, validate and URI-encode the path segment.
- The page accepts only allowlisted `error` query values; never render raw `error_description`.
- `Cache-Control: no-store` reduces the risk of caching login error HTML.
- In production HTML, add styling, accessibility/i18n, privacy policy links, and IdP support guidance.

Spring Security 6.5 custom login page configuration **does not need** a `POST /signin` route for passwords, because passwords are entered **at the IdP**. A form accepting passwords in the app's own browser UI switches to a different model (form login) with its own risks.

### 7.6. PagesController.java: Separating Public and Authenticated Routes

```java
package demo.oauthlogin;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class PagesController {

    @GetMapping("/")
    public Mono<String> index() {
        return Mono.just("public landing");
    }

    @GetMapping("/private")
    public Mono<String> privatePage() {
        return Mono.just("private content");
    }

    @GetMapping("/home")
    public Mono<String> home() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .map(name -> "signed in as " + name);
    }
}
```

`/home` requires authentication before being invoked. With OIDC, `Authentication.getName()` is typically a stable principal identifier, not always an email or display name; never assume the name implies a role or a verified email.

### 7.7. Running the Demo

At the project root:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Open:

```text
http://localhost:8080/
http://localhost:8080/signin
http://localhost:8080/private
```

Expected:

- `GET /`: HTTP 200, `public landing`.
- `GET /signin`: HTTP 200 HTML with Alpha and Beta links.
- `GET /private`: anonymous receives redirect to `/signin`.
- `GET /oauth2/authorization/alpha`: HTTP 302 to fake authorization endpoint `https://login.alpha.example.test/authorize`, carrying `client_id`, `response_type=code`, `redirect_uri`, and `state` per flow. Following the link in a browser hits a non-existent IdP: **this is an intentional limitation of the offline demo**.
- `GET /home` before login: redirects to `/signin`.
- No valid successful callback is possible until the demo IdPs are replaced with real ones.

Inspect the initial redirect **without auto-following the IdP**:

```bash
curl -i http://localhost:8080/oauth2/authorization/alpha
```

The response should contain a `Location` pointing to `https://login.alpha.example.test/authorize?...`; query parameters are encoded, `state` changes each time, and the app may set a session cookie. **Never** copy production `state`/`code` values into public logs.

## 8. WebTestClient Tests: Provider Chooser Page and Authorize Redirect

File `src/test/java/demo/oauthlogin/OAuthLoginWebTests.java`:

```java
package demo.oauthlogin;

import java.net.URI;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OAuthLoginWebTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicLandingWorks() {
        client.get().uri("/")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("public landing");
    }

    @Test
    void providerPageContainsOnlyConfiguredChoices() {
        client.get().uri("/signin")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .value(html -> {
                assertTrue(html.contains(
                    "/oauth2/authorization/alpha"));
                assertTrue(html.contains(
                    "/oauth2/authorization/beta"));
                assertTrue(html.contains("Alpha Identity"));
                assertTrue(html.contains("Beta Identity"));
                assertFalse(html.contains("not-a-real-secret"));
            });
    }

    @Test
    void errorPageUsesGenericTextNotProviderDetails() {
        client.get()
            .uri("/signin?error=oauth2&error_description=SECRET_DEBUG")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .value(html -> {
                assertTrue(html.contains(
                    "Unable to complete sign-in"));
                assertFalse(html.contains("SECRET_DEBUG"));
            });
    }

    @Test
    void anonymousPrivatePageRedirectsToProviderPage() {
        var result = client.get().uri("/private")
            .exchange()
            .expectStatus().is3xxRedirection()
            .returnResult(Void.class);

        URI location = result.getResponseHeaders().getLocation();
        assertNotNull(location);
        assertEquals("/signin", location.getPath());
    }

    @Test
    void authorizationLinkRedirectsToProviderWithState() {
        var result = client.get()
            .uri("/oauth2/authorization/alpha")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().exists(HttpHeaders.LOCATION)
            .returnResult(Void.class);

        URI location = result.getResponseHeaders().getLocation();
        assertNotNull(location);
        assertEquals("login.alpha.example.test", location.getHost());

        String query = location.getRawQuery();
        assertNotNull(query);
        assertTrue(query.contains("response_type=code"));
        assertTrue(query.contains("client_id="));
        assertTrue(query.contains("redirect_uri="));
        assertTrue(query.contains("state="));
    }

    @Test
    void secondProviderHasDifferentAuthorizationHost() {
        var result = client.get()
            .uri("/oauth2/authorization/beta")
            .exchange()
            .expectStatus().is3xxRedirection()
            .returnResult(Void.class);

        URI location = result.getResponseHeaders().getLocation();
        assertNotNull(location);
        assertEquals("login.beta.example.test", location.getHost());
    }

    @Test
    void homeRequiresRealAuthentication() {
        var result = client.get().uri("/home")
            .exchange()
            .expectStatus().is3xxRedirection()
            .returnResult(Void.class);

        URI location = result.getResponseHeaders().getLocation();
        assertNotNull(location);
        assertEquals("/signin", location.getPath());
    }
}
```

**7 integration test methods** verify the UI/login entry point/authorization initiation. `WebTestClient` does not auto-follow redirects to `.example.test`, so **no real DNS/IdP is needed** to verify authorization request creation. Nor does it **prove** an OIDC callback succeeded: that requires a test-designed mock IdP or a real provider with a test account.

### 8.1. Why Not Call the Callback with a Made-Up Code to Test Login Success?

Broken mental model:

```http
GET /login/oauth2/code/alpha?code=fake&state=fake
```

There is no matching stored authorization request, the code cannot be exchanged for valid tokens, and the ID token cannot be verified. Spring Security must reject it. If a test expects `GET callback?code=fake` to return authenticated success, the test is **bypassing or over-mocking** authentication. Success redirects should be tested separately at the handler level, while full callbacks require a test IdP returning valid authorization/token/JWK responses with consistent state/nonce/PKCE.

### 8.2. Assert Location Structure, Not a Hardcoded State Value

Random `state` must never be hardcoded in assertions. Tests only need to assert that the redirect includes `state`, the right scheme/host, and no leaked credentials. To verify non-repetition you can compare two requests, avoiding unnecessary probabilistic assertions. Callback tests should cover negative paths for state mismatch/replay rather than faking invalid signed tokens.

## 9. Unit Tests: Decoupling Redirect Handlers from the IdP

To test success/failure handlers without real tokens, invoke the `ServerAuthenticationSuccessHandler` and `ServerAuthenticationFailureHandler` contracts **directly** with a mock exchange. These are **redirect-only** behavior tests; they do not test token exchange, state, or OIDC signatures.

File `src/test/java/demo/oauthlogin/LoginRedirectHandlerTests.java`:

```java
package demo.oauthlogin;

import java.net.URI;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.web.server.WebFilterExchange;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class LoginRedirectHandlerTests {

    private MockServerWebExchange exchange() {
        return MockServerWebExchange.from(
            MockServerHttpRequest
                .get("/login/oauth2/code/alpha").build());
    }

    private WebFilterExchange bridge(MockServerWebExchange exchange) {
        return new WebFilterExchange(
            exchange,
            next -> Mono.empty()
        );
    }

    @Test
    void successHandlerRedirectsToFallbackHome() {
        MockServerWebExchange exchange = exchange();
        Authentication authentication =
            UsernamePasswordAuthenticationToken.authenticated(
                "test-subject",
                "not-used",
                AuthorityUtils.createAuthorityList("ROLE_USER"));

        StepVerifier.create(
                LoginRedirects.success().onAuthenticationSuccess(
                    bridge(exchange), authentication))
            .verifyComplete();

        assertEquals(HttpStatus.FOUND,
            exchange.getResponse().getStatusCode());

        URI location = exchange.getResponse()
            .getHeaders().getLocation();
        assertNotNull(location);
        assertEquals("/home", location.getPath());
    }

    @Test
    void failureHandlerRedirectsWithGenericCodeOnly() {
        MockServerWebExchange exchange = exchange();

        StepVerifier.create(
                LoginRedirects.failure().onAuthenticationFailure(
                    bridge(exchange),
                    new BadCredentialsException(
                        "internal-details-not-for-browser")))
            .verifyComplete();

        assertEquals(HttpStatus.FOUND,
            exchange.getResponse().getStatusCode());

        URI location = exchange.getResponse()
            .getHeaders().getLocation();
        assertNotNull(location);
        assertEquals("/signin", location.getPath());
        assertEquals("error=oauth2", location.getRawQuery());
    }
}
```

`WebFilterExchange` takes a `ServerWebExchange` and a `WebFilterChain`. The lambda `next -> Mono.empty()` is just an empty chain for the unit test. The `Authentication` constructed by the test exists to invoke the **success handler**, not as a valid IdP result: this test **must not be counted as OIDC verification**.

In a real request with a saved request, the success handler may redirect via the request cache instead of the `/home` fallback. The unit test uses an exchange without a saved request, so expecting `/home` is accurate. Testing saved-request redirects requires testing the session/request cache or the full OIDC flow.

Run tests:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

The project defines **9 test methods** (7 WebTestClient + 2 handler unit tests). This is the **expectation from the code and Spring Security 6.5 APIs**, not a claim that Gradle was run in the learner's workspace. If a redirect status/location assertion differs due to framework/redirect strategy, inspect the actual response and your version's Javadocs rather than relaxing protections just to make tests pass.

## 10. Wiring a Real IdP for End-to-End Testing

The demo above runs offline because it only tests **login initiation and handlers**. For real callbacks:

1. Create a **Confidential Web Client** with a trusted OIDC provider; register the external callback URL such as `https://app.example/login/oauth2/code/alpha`.
2. Replace `authorizationUri`, `tokenUri`, `jwkSetUri`, `userInfoUri`/issuer metadata with real IdP endpoints. Never use `.example.test` domains.
3. Store `clientId` and `clientSecret` in a secret manager or environment variables, never in source code. Verify the provider's supported auth method (`client_secret_basic`, `client_secret_post`, or another policy-approved mechanism).
4. Ensure the `openid` scope is present for OIDC; request minimal scopes. Verify signature, issuer, audience, nonce, and expiry using the framework rather than hand-parsing JWTs.
5. Configure HTTPS/proxy/forwarded headers properly and ensure the IdP redirect URI matches identically.
6. Run the browser flow: `GET /private` → `/signin` → IdP → callback → back to the protected page.
7. After login, send a second request **with only the session cookie**, without code/tokens in the URL, confirming Authentication persists.
8. Test user-canceled consent (`access_denied`), state mismatch, deleted cookies, code replay, token endpoint errors, invalid ID tokens, and unavailable providers.
9. Test multiple accounts/tenants: pick another provider, logout/re-login, switch users, unverified emails, identity linking; never auto-link accounts based on untrusted emails.
10. Observe logout/session expiry and session ID rotation; across multiple replicas, use an appropriate shared session store or reliable state strategy.

### 10.1. Testing with a Rigorous Mock IdP

A valid test IdP must be capable of:
- Returning a 302 authorization response carrying the exact `state` from the authorization request.
- Issuing single-use authorization codes bound to the right client, redirect URI, and PKCE when applicable.
- At the token endpoint, accepting valid client auth and codes while rejecting fake codes, reused codes, or wrong code verifiers.
- Returning signed ID tokens containing `iss`, `aud`, `sub`, `exp`, `iat`, and `nonce` when requested by the flow, alongside JWKS public keys.
- Exercising JWK rotation and negative tests (wrong key/kid, stale exp, wrong issuer/audience, nonce mismatch).
- Letting Spring Security's callback filter execute the full path rather than forcing Authentication success via `mockUser`.

Test frameworks like WireMock/MockWebServer can serve the HTTP endpoints; generating signed JWTs for a test IdP requires an appropriate library and dedicated test keys. Never reuse production HMAC secrets in tests, and never deploy a mock token signer as a real IdP.

### 10.2. Error Callback from the IdP

An error response might look like:

```http
GET /login/oauth2/code/alpha?error=access_denied&state=... HTTP/1.1
Host: app.example
Cookie: SESSION=<cookie-from-initiation>
```

This is **illustrative**. When a matched callback is handled as a failure by the authentication pipeline, `oauth2Login`'s failure handler can redirect the user to `/signin?error=oauth2`. Never reflect `error_description` to the UI or log raw codes/states. If no matching saved authorization request exists or the callback misses the filter, the outcome may differ; test separately and ensure fail-closed behavior.

### 10.3. Callback Protection and Login CSRF

`state` binds the OAuth2 authorization response to the previously created session/authorization request, but **does not replace CSRF protection for the application's POST business endpoints**. Cookie-based browser webapps still require CSRF tokens per threat model on state-changing requests.

`PKCE` reduces the risk of stolen authorization codes by binding the code to a verifier; for public clients it is mandatory in modern configurations. OIDC `nonce` binds the ID token to the authentication request, though it may not appear across all providers or non-OIDC OAuth2. Never remove `state`/PKCE/nonce checks when troubleshooting callback errors.

## 11. Securing Login Page Content and Error Handlers

### 11.1. Use Only Allowlisted Public Messages

Example query:

```text
/signin?error=oauth2
```

Render only a static message:

```text
Unable to complete sign-in. Please try again or contact support.
```

Never display:
- Raw query `code` / `state` / `id_token` / `access_token`.
- `AuthenticationException.getMessage()` or stack traces.
- Raw `error_description` text from the IdP.
- `clientSecret`, token endpoint response bodies, or JWT/JWK private material.
- Sensitive emails/claims or internal tenant mappings.

An error page can receive arbitrary query parameters crafted by an attacker; rendering raw unescaped query values risks reflected XSS and phishing. A generic message keeps UX adequate while minimizing internal leakage.

### 11.2. Logging and Correlation IDs

Record controlled metrics: allowlisted provider ID, normalized error category, HTTP status, latency, internal correlation ID, and stage (`initiation`/`callback`/`success`/`failure`). Never log raw codes, state, `Authorization` headers, `Cookie` headers, refresh tokens, ID tokens, `clientSecret`, or exception messages containing sensitive data.

A useful dashboard tracks:
- Clicks on Alpha/Beta.
- Redirect rate to IdP vs. callback return rate.
- Rates of success, cancellation, state mismatch, and token endpoint errors.
- p95/p99 callback latency.
- Login-loop rate and lost session/cookie rate.
- IdP unavailability and token validation failure rates.

Never treat `error=oauth2` on a public URL alone as a reliable audit source since users can type it manually.

### 11.3. Preventing Provider Poisoning and Open Redirects

Do not do this:

```java
// WRONG design example, never use in a real app:
String providerUrl = request.getQueryParams()
    .getFirst("providerUrl");
response.getHeaders().setLocation(URI.create(providerUrl));
```

This is a broken snippet, not a complete class. It risks sending users to attacker-controlled fake endpoints. Providers must come from trusted `ClientRegistration` entries, and `registrationId` must be validated/allowlisted. Likewise, never accept a browser-supplied `redirect_uri` in a callback blindly.

### 11.4. Cookies, SameSite, HTTPS, and Multi-Node

Authorization requests are typically stored in `WebSession`. The initiating session's cookie must return on the callback. Verify:
- `Secure`/`HttpOnly`/`SameSite`, and proper cookie domain/path.
- Browser callback top-level GET vs. form POST, and cross-site context.
- TLS termination and trusted forwarded host/proto headers.
- Distributed session store across multiple replicas.
- Session-fixation protection/rotation after authentication.
- Timeouts and cleanup of consumed requests.
- Concurrent logins across multiple tabs and re-login when switching accounts.

Never store authorization requests or tokens in a global static map without TTL/tenant isolation just to avoid sessions.

### 11.5. Preventing Login Loops

A classic bug:

```text
GET /private -> 302 /signin
GET /signin  -> hit .authenticated() again -> 302 /signin
... infinite loop
```

Fix it by permitting `permitAll` on the custom login page, authorization initiation endpoint, and assets needed to render the page. **Never** open `/home` or sensitive resources. Test with an unauthenticated browser and no cookies.

## 12. Distinguishing Four Types of Navigation Around Login

| Type | Trigger | Typical Target | What to Check |
|---|---|---|---|
| Entry point | Anonymous hits protected resource | `/signin` | `/signin` is permitted, no login loop |
| Authorization request redirect | User clicks provider | IdP `/authorize` URL | Trusted `registrationId`, state/redirectUri/PKCE |
| Callback success redirect | Authentication succeeds | Saved request or `/home` | Local redirect, Authentication persists, no leaked code |
| Callback failure redirect | Authentication attempt fails | `/signin?error=oauth2` | Generic message, no raw error/token echoed |

An HTTP 302 appears in **all four scenarios**. Never treat `expectStatus().is3xxRedirection()` as proof of successful login: inspect `Location` and, for real callback successes, make a follow-up authenticated request.

## 13. Real-World Errors and How to Diagnose Them

| Symptom | Common Cause | Resolution |
|---|---|---|
| Provider chooser page shows empty list | Custom repository doesn't implement `Iterable` or controller pulls wrong list | Use trusted list source; check `ReactiveClientRegistrationRepository` |
| Clicking Alpha doesn't reach IdP | Wrong base link path or changed matcher | Compare `/oauth2/authorization/{registrationId}` with `ServerOAuth2AuthorizationRequestResolver` |
| IdP reports `redirect_uri_mismatch` | External `baseUrl` differs from registered HTTPS/host/port/context path | Compare callback URI, proxy config, and registration |
| Callback returns 404 | `authenticationMatcher` mismatch, different callback path/context path | Synchronize matcher and `redirectUri` |
| Callback reports invalid state | Lost session cookie, timeout, missing saved request, parallel logins | Debug session continuity; **never disable `state`** |
| User cancels login and sees 500 | Error path/handler doesn't handle callback error properly | Check error type, chain, and generic failure redirect |
| IdP/token endpoint times out | Network/TLS/proxy/client config | Timeouts, alerting, safe UI retry |
| Login returns 302 but user stays anonymous | Mismatched security context save/load repo or lost cookie | Check `WebSession`/`securityContextRepository` |
| User lands on `/home` instead of original URL | Saved request not cached, no-op handler, or unmatched request rule | Check request cache/fallback semantics |
| User redirected to external attacker URL | Success handler trusts `returnUrl`/query | Local path allowlist; never use raw input |
| Redirect loop error | Login page not permitted or entry point applies to it | Permit `GET /signin` and static assets |
| 302 to `/login?error` instead of `/signin` | Missing custom OAuth2 failure handler | `authenticationFailureHandler` with generic target |
| Raw `error_description` shown in HTML | Controller echoes query/exceptions | Static generic message, HTML escaping, log redaction |
| Wrong app roles after IdP login | Assumed scopes/email = application roles | Map authorities/ACLs from trusted source |
| Same email from two IdPs merges accounts | Linked by email without checking `issuer`/`sub`/`email_verified` | `iss + sub` identity mapping and account-linking policy |
| Callback works on one pod, fails when scaled | Authorization request kept only in local `WebSession` | Shared session store / distributed strategy |
| CORS error when IdP redirects browser | Confused OAuth2 top-level navigation with browser API CORS | Check callback URL/cookies/matcher; CORS is mainly for `fetch` |
| Old callback succeeds after logout | Unclear authorization request/session cleanup, replay handling | Test state invalidation and code replay |
| `mockUser` tests pass but real OIDC fails | Skipped signature/token/state/cookie flow | Test with real IdP or mock with valid tokens/JWKS |
| Success handler drops session registration handler | Single-handler setter cleared success handler list | Review list overload, session concurrency, and OIDC registry |
| Debug logs contain code/tokens | Logging raw callback queries or exception bodies | Redact, never log secrets |

### 13.1. Ordered Debugging Checklist

1. Confirm **Spring WebFlux** is handling inbound HTTP, not MVC/Servlet.
2. Verify `/signin` returns 200 with no redirect loop.
3. Verify links use real, server-allowlisted registration IDs.
4. Verify `GET /oauth2/authorization/{registrationId}` returns 302 to the right IdP with `state`.
5. Observe the cookie saved at login initiation; never log cookie values.
6. Verify the IdP's registered redirect URI matches the external HTTPS URL.
7. Check whether the callback reaches the Spring app or is blocked by proxy/gateway/404/another chain.
8. Inspect saved authorization request/state per session without exposing raw state in UI/logs.
9. Review token exchange/OIDC signature validation and user info by error category.
10. Verify whether success/failure handlers ran and check the final `Location`.
11. Verify a post-login protected request stays authenticated **using only the cookie**.
12. Verify logout, session expiry, and multi-node sticky/shared stores.

## 14. Exercises with Answers

### Exercise 1 — Provider Selection Page and Entry Point

An unauthenticated user opens `/private`; the app has two providers, Alpha and Beta. Why redirect to `/signin` instead of automatically redirecting to Alpha?

**Answer:** Because the product lets users pick a provider. `RedirectServerAuthenticationEntryPoint("/signin")` sends the user to the chooser page, which offers `/oauth2/authorization/alpha` and `.../beta`. Auto-redirecting to Alpha may not fit the tenant and prevents choosing another account.

### Exercise 2 — Is Every 302 Redirect a Login Success?

**Answer:** No. 302s occur when anonymous users are sent to the chooser page, when initiating OAuth2 to the IdP, on callback success, and on callback failure. You must inspect `Location` and post-callback session state.

### Exercise 3 — Why Does the Login Page Show No Providers?

A custom `ReactiveClientRegistrationRepository` implements only `findByRegistrationId`, and the generated login page displays no links. Why?

**Answer:** `LoginPageGeneratingWebFilter` needs to enumerate registrations via `Iterable<ClientRegistration>` to render links. Use an implementation that supports it or build a custom page backed by a separate trusted server-side provider list.

### Exercise 4 — Callback State Mismatch

The browser starts login with session A, then the callback arrives with session B's cookie. Should `state` validation be disabled to let the callback through?

**Answer:** No. `state` correlation protects against login injection/CSRF and mismatched authorization responses. Fix the session cookie, timeout, SameSite, proxy, and store instead of disabling checks.

### Exercise 5 — User Cancels at the IdP

The IdP returns `error=access_denied`. What should the custom page show?

**Answer:** A generic message such as “Unable to complete sign-in, please try again”. Never display raw `error_description`/stack traces/codes/states; debugging details belong in redacted, access-controlled logs.

### Exercise 6 — Does RedirectServerAuthenticationSuccessHandler Always Go to /home?

The handler uses constructor `("/home")`, yet users still land on `/private`. Is the handler broken?

**Answer:** Not necessarily. The success handler can prioritize a saved request in the request cache first, using `/home` only as a fallback. To always go to `/home`, intentionally change the request-cache behavior and accept losing saved-navigation UX.

### Exercise 7 — Changing the Redirect URI at the IdP

The IdP registers `https://app.example/auth/callback/alpha`, while `ClientRegistration.redirectUri` remains `{baseUrl}/login/oauth2/code/{registrationId}`. Outcome?

**Answer:** Redirect mismatch or the callback misses the authentication filter. Keep registration, callback matcher, and IdP settings synchronized; test the real external URL through the proxy.

### Exercise 8 — Can the Client Secret Be Placed on the Provider Page so the IdP Knows the App?

**Answer:** No. Provider links only need the local authorization initiation URL. OAuth2 client secrets belong on the server/secret manager, never in HTML, JS, URLs, or browser logs.

### Exercise 9 — Without a Real IdP, What Can Be Tested?

**Answer:** You can test `/signin`, provider allowlists, link URLs, state-carrying initiation redirects, entry points, and isolated success/failure handler redirects. You cannot claim real token exchange/ID token validation/callback sessions succeed without a real IdP or a protocol-compliant mock IdP.

### Exercise 10 — Email Claim as Username and Account Linking

Two IdPs return the same email for two different people. Can email be used to auto-merge accounts?

**Answer:** No. Use a trusted identity key such as `issuer + subject` and a verified account-linking workflow. `email_verified` (if present) does not replace authorization for merging accounts or granting roles.

### Exercise 11 — Custom Success Handler and Open Redirect

The app takes `?next=https://evil.example` and redirects straight to it after login. What is the issue?

**Answer:** Open redirect/phishing and potential information leakage. Use a fixed local fallback path, a trusted request cache, or a target allowlist with URI normalization, forbidding user-supplied external schemes/hosts.

### Exercise 12 — Difference Between OAuth2 Login and Resource Server

A website uses `oauth2ResourceServer().jwt()` to validate Bearer tokens. Why doesn't it get a provider selection page automatically?

**Answer:** Resource Server validates incoming access tokens on APIs; it does not perform browser authorization-code login. Website login requires `oauth2Login` and `ReactiveClientRegistrationRepository`.

### Exercise 13 — Missing Cookie on Callback

A user logs in at the IdP successfully, but the callback reports “invalid state”. What should you check first?

**Answer:** Check whether the session cookie from initiation is still sent back on the callback, along with timeouts, browser SameSite, multi-node session stores, redirect scheme/host, and request repository logic. Never enter codes/states manually.

### Exercise 14 — Can a Custom Success Handler Wipe Out Other Session Behavior?

**Answer:** Yes, if you use the single-handler setter that replaces handlers in an integrated multi-component config. Review `authenticationSuccessHandler(...)` Javadocs, your version's handler list, session registration, OIDC session registry, and integration tests.

### Exercise 15 — Unresponsive Provider Error

User clicks Alpha and the browser cannot resolve the IdP hostname; will the backend failure handler definitely run?

**Answer:** No. If the browser never returns to the application's callback, the authentication filter has no failure event for that request. UI and monitoring must handle IdP unavailability at the product/network level.

## 15. Production Deployment Checklist

- [ ] Use `ServerHttpSecurity`/`SecurityWebFilterChain` and `oauth2Login` matching the reactive stack.
- [ ] Have `ReactiveClientRegistrationRepository` with valid registration IDs, issuer/endpoints, and credentials.
- [ ] Store client secrets in a secret manager/env, never in source/HTML/logs/URLs.
- [ ] Provider selection page pulls from a trusted list, escapes HTML, and allowlists registration IDs.
- [ ] Custom `/signin` and assets permit anonymous access without redirect loops.
- [ ] Links to `/oauth2/authorization/{registrationId}` match the resolver/matcher.
- [ ] Callback `/login/oauth2/code/{registrationId}` matches registration and IdP URI identically.
- [ ] `state`/PKCE/OIDC `nonce`/signature/issuer/audience/expiry validation are never bypassed.
- [ ] `WebSession` authorization requests survive from initiation to callback; verify cookies/SameSite and distributed stores.
- [ ] Success redirects use a local allowlist, never trusting raw `next`/`redirect_uri` queries.
- [ ] Saved request vs. `/home` fallback behavior is intentionally chosen and tested.
- [ ] Failure redirect is fixed and never echoes `error_description`/`code`/`state`/exception messages.
- [ ] 401 anonymous, 403 unauthorized, and login success/failure callbacks are cleanly separated.
- [ ] For OIDC, account mapping uses `issuer + subject` and validates required claims.
- [ ] HTTPS/TLS/proxy/forwarded headers are configured only from trusted sources.
- [ ] Post-login security context read/save is consistent and verified with cookie-only follow-up requests.
- [ ] Never call `block()`/`subscribe()` inside custom reactive success/failure handlers.
- [ ] Logs, traces, and analytics are redacted of tokens, client secrets, and session cookies.
- [ ] Browser tests cover logout, expired sessions, provider cancellation, and callback replay.
- [ ] Full OIDC tested with a real/standards-compliant mock IdP, never treating `mockUser` as proof of real login.
- [ ] Review success handler overloads when adding session concurrency/session registries.
- [ ] Enforce rate limiting, security headers, CSRF on app POSTs, and XSS defenses on the login page.

## 16. Quick Summary

```text
CHOOSE IDP:
  GET /signin
  -> local link /oauth2/authorization/alpha | /beta

START LOGIN:
  OAuth2AuthorizationRequestRedirectWebFilter
  -> trusted ClientRegistration
  -> random state, authorization request repository (WebSession)
  -> 302 to IdP

CALLBACK:
  GET /login/oauth2/code/{registrationId}
  -> state correlation + code exchange
  -> for OIDC: verify ID token and claims
  |
  +-- SUCCESS
  |    -> persist Authentication
  |    -> ServerAuthenticationSuccessHandler
  |    -> saved request or /home
  |
  +-- FAILURE
       -> ServerAuthenticationFailureHandler
       -> /signin?error=oauth2 (generic)

ANONYMOUS:
  RedirectServerAuthenticationEntryPoint("/signin")

DISTINCTIONS:
  entry point != OAuth callback failure handler
  302 authorization redirect != login success
  success handler redirect != token verification
  Provider UI link != client secret or issuer validation
  state != CSRF token for all application POSTs
  fake IdP redirect test != end-to-end OIDC login
```

**Core lesson:** Keep **provider selection**, **OAuth2 authorization initiation**, **callback reception and validation**, and **post-success/failure UI navigation** cleanly separated. Spring Security Reactive already provides the corresponding filters and handlers. Customizations should focus on UX, safe redirects, and testing—**never altering or removing** the state, token, or identity checks enforced by the framework.

## 17. Official Documentation

- [Spring Security 6.5 — OAuth2 Login Core Configuration](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/core.html)
- [Spring Security — Reactive OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/advanced.html)
- [Spring Security — Reactive OAuth2 Authorization Code](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorization-grants.html)
- [Spring Security 6.5 — ServerHttpSecurity.OAuth2LoginSpec API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.OAuth2LoginSpec.html)
- [Spring Security 6.5 — RedirectServerAuthenticationSuccessHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/RedirectServerAuthenticationSuccessHandler.html)
- [Spring Security 6.5 — RedirectServerAuthenticationFailureHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/RedirectServerAuthenticationFailureHandler.html)
- [Spring Security 6.5 — RedirectServerAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/RedirectServerAuthenticationEntryPoint.html)
- [Spring Security — InMemoryReactiveClientRegistrationRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/registration/InMemoryReactiveClientRegistrationRepository.html)
- [Spring Security — WebSessionOAuth2ServerAuthorizationRequestRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/server/WebSessionOAuth2ServerAuthorizationRequestRepository.html)
- [Spring Security — OAuth2 Client and Login Overview](https://docs.spring.io/spring-security/reference/reactive/oauth2/)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [OAuth 2.0 Security Best Current Practice (RFC 9700)](https://www.rfc-editor.org/rfc/rfc9700.html)
- [OAuth 2.0 PKCE (RFC 7636)](https://www.rfc-editor.org/rfc/rfc7636)
- [OWASP — OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
