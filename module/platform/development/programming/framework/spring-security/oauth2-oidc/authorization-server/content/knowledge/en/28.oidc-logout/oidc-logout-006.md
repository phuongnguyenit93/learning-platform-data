# Terminating the Authorization Server Session and Clearing SecurityContext

> **Chapter:** OIDC Logout  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Module Goal:** Learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in Spring Boot applications.  
> **Scope:** Spring Boot 3.x, Spring Security 6.x, and Spring Authorization Server 1.5.x on the Servlet stack. Content focuses on login sessions at the OpenID Provider/Authorization Server (OP/AS), OIDC RP-Initiated Logout, and the `SecurityContext` lifecycle. Verify APIs against your actual patch version.

## 1. Context and Goals

An OIDC system often has multiple login states existing simultaneously. A user may have an SSO session at the Authorization Server, local sessions at each Relying Party (RP), as well as issued access tokens and refresh tokens.

For example, a user logs into Portal through the Authorization Server. Portal creates a local session; the Authorization Server also creates an SSO session. The user opens Admin Console and is logged in automatically because the SSO session is still active. When the user clicks Logout in Portal, if Portal only deletes cookies and its local session, the SSO session at the Authorization Server remains intact. Next time the user opens Portal or another RP, the OP can continue SSO without asking them to log in again.

Inside the Authorization Server, logout must also clean up Spring Security's authentication state. Calling only `SecurityContextHolder.clearContext()` in a controller may not be enough if the Authentication is still persisted in `SecurityContextRepository`. Conversely, merely invalidating `HttpSession` does not clear every reference to the context currently being used by the request.

After this lesson, you will be able to:

1. Distinguish local RP sessions, OP/AS sessions, `SecurityContext`, and OAuth2 token state.
2. Describe RP-Initiated Logout and the role of `end_session_endpoint`.
3. Understand how Spring Authorization Server's OIDC Logout Endpoint validates requests and locates sessions.
4. Distinguish `LogoutFilter`, `LogoutHandler`, `LogoutSuccessHandler`, and the OIDC logout filter/provider.
5. Explain the lifecycle of `SecurityContextHolder` and `SecurityContextRepository`.
6. Use `SecurityContextLogoutHandler` to invalidate sessions, clear Authentication, and save an empty context.
7. Configure the same repository for the filter chain and logout handler when using a custom repository.
8. Integrate `SessionRegistry`, `HttpSessionEventPublisher`, and distributed sessions.
9. Handle remember-me, CSRF, cookies, concurrent requests, and async tasks.
10. Write tests proving that post-logout requests do not restore the old Authentication.

**Core Principle:** A complete logout at the Authorization Server must terminate the right HTTP session, clear Authentication from the current context, and remove persisted state from the repository. OIDC logout, local logout, logout notifications, and token revocation are related mechanisms with distinct scopes.

## 2. States to Distinguish

| Component | Role | Where Commonly Managed | What Must Logout Do? |
| --- | --- | --- | --- |
| RP local session | Maintains login at an individual application | RP, Servlet session, or application session | RP terminates its own session |
| OP/AS SSO session | Allows the user to continue SSO at the Authorization Server | OP's `HttpSession`/session store | OP terminates the session via the logout flow |
| Current `SecurityContext` | Supplies Authentication for the current request/thread | `SecurityContextHolder` | Clear the holder and Authentication appropriately |
| Persisted `SecurityContext` | Restores Authentication on subsequent requests | `SecurityContextRepository` | Save empty state or delete context |
| `SessionRegistry` entry | Links principal/session for session lookup | `SessionRegistry` | Update/remove per session lifecycle |
| Access token | Credential for calling Resource Servers | Authorization Server and Resource Server | Revocation/denylist/introspection/expiry per policy |
| Refresh token | Requests new access tokens | Authorization Server | Revoke if preventing new token issuance is required |
| OAuth2 authorization/consent | Grant and consent state | Authorization/consent service | Has its own policy; not automatically removed on browser logout |
| Session at another RP | Maintains local login in other applications | Each RP | Requires logout notifications or separate flows |

A single logout action does not automatically terminate all the states above. Clearing Portal's cookie does not end the SSO session at the OP; ending the OP session does not automatically delete Admin Console's local session; clearing `SecurityContext` in a stateless request does not invalidate already-issued JWTs.

### 2.1. Local Logout and OP Logout

**Local logout** ends the session of a single application. The user is no longer authenticated at that RP, yet the OP session may remain.

**RP-Initiated Logout** allows the RP to navigate the browser to the OP's Logout Endpoint to request ending the End-User session. The OP verifies the request, processes the session, and may navigate the browser back to the RP.

### 2.2. Session Logout Differs from Token Revocation

Already-issued JWT access tokens can continue to be accepted by a Resource Server until `exp` if the Resource Server verifies signatures and claims locally. Refresh tokens can continue requesting new tokens if they have not been revoked.

If policy requires cutting off API access early, you need token revocation, introspection, a denylist, event propagation, or short access token TTLs. Do not describe browser logout as "all tokens invalidated" if the system has not implemented those steps.

## 3. RP-Initiated Logout at the Authorization Server

OpenID Connect RP-Initiated Logout 1.0 describes how an RP requests the OP to log out an End-User via the User Agent (typically a browser).

The RP retrieves the Logout Endpoint URL from OpenID Provider Configuration via the `end_session_endpoint` metadata field:

~~~json
{
  "issuer": "https://auth.example.test",
  "end_session_endpoint": "https://auth.example.test/connect/logout"
}
~~~

This URL is just an example. SAS typically uses `/connect/logout`, though it can be changed via `AuthorizationServerSettings`. The RP should read `end_session_endpoint` from verified issuer metadata rather than concatenating paths manually.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as End-User / Browser
    participant RP as Relying Party
    participant OP as OpenID Provider / AS
    participant REG as SessionRegistry

    U->>RP: Click Logout
    RP->>RP: End local session if policy requires
    RP-->>U: Redirect to end_session_endpoint
    U->>OP: Logout Request
    OP->>OP: Verify id_token_hint, client, and redirect
    OP->>REG: Look up SessionInformation
    REG-->>OP: Associated session
    OP->>OP: Terminate OP session
    OP-->>U: Redirect to post-logout URI if valid
    U->>RP: Callback with state
    RP->>RP: Verify state and display result
~~~

### 3.1. Logout Request Parameters

| Parameter | Requirement Level | Purpose |
| --- | --- | --- |
| `id_token_hint` | RECOMMENDED | ID Token issued by the OP, helping identify the user/client/session |
| `client_id` | OPTIONAL | Identifies the client; if paired with `id_token_hint`, must match the client that received the ID Token |
| `post_logout_redirect_uri` | OPTIONAL | URI the RP wants the browser returned to after logout |
| `state` | OPTIONAL | Opaque value used by the RP to correlate the request and callback |
| `logout_hint` | OPTIONAL | Hint identifying the End-User when the RP lacks an ID Token hint |

OIDC RP-Initiated Logout requires the OP to support both HTTP GET and POST. The RP can send query parameters or a form-urlencoded body. Do not send a client secret in the Logout Request.

### 3.2. id_token_hint and Session

`id_token_hint` must be an ID Token issued by the OP itself. The OP must verify that the token belongs to its issuer and check the relationship with the associated client/session. Do not use an access token, refresh token, authorization code, or RP self-signed JWT in place of an ID Token hint.

The OP **SHOULD** accept an expired ID Token hint if it can still confirm that the RP via `aud` and/or the session via `sid` is a current or recent session. Users may log out after the ID Token has expired while the OP session remains active. This rule is solely for logout hints; it does not mean expired access tokens can still be used to call APIs.

If the request includes both `client_id` and `id_token_hint`, the OP **MUST** verify that the client ID matches the client used when issuing the ID Token. Without a hint, the OP may use another client/identifier per policy, but must not infer a user session solely from a client ID string.

### 3.3. post_logout_redirect_uri

If the RP sends `post_logout_redirect_uri`, the OP must verify that the URI matches one registered for the corresponding client exactly. Do not use wildcards, prefix matching, or substring matching.

Example registered URI:

~~~text
https://app.example.test/logout/callback
~~~

The following values must not be treated as matches automatically:

~~~text
https://app.example.test/logout/callback/
https://app.example.test/logout/callback?next=/admin
https://app.example.test.evil.test/logout/callback
http://app.example.test/logout/callback
~~~

If `id_token_hint` is absent, the OP **MUST NOT** redirect to the requested URI unless it has another means of confirming the legitimacy of the redirect target. Never redirect to an arbitrary URL supplied by the browser.

SAS stores these URIs on `RegisteredClient` via `postLogoutRedirectUri(...)`. This is a separate registration; do not use the Authorization Code Flow's `redirectUri(...)` as a substitute.

~~~java
RegisteredClient portalClient = RegisteredClient
    .withId("portal-client-registration")
    .clientId("portal-client")
    .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .redirectUri("https://portal.example.test/login/oauth2/code/portal")
    .postLogoutRedirectUri("https://portal.example.test/logout/callback")
    .scope(OidcScopes.OPENID)
    .clientSettings(ClientSettings.builder()
        .requireProofKey(true)
        .build())
    .build();
~~~

This is a fragment for a public client using Authorization Code + PKCE. Confidential clients require a client authentication method and their own credentials. Registrations must be stored in a durable repository in production.

### 3.4. state and Confirmation

The RP generates a random `state`, stores it tied to the browser session/transaction, and sends it in the Logout Request. When the OP redirects back to the callback, the RP strictly compares the received `state` against the pending `state` and consumes the value. Use a dedicated state for logout with a short TTL and one-time use; never put access tokens, refresh tokens, client secrets, or arbitrary URLs inside `state`.

The OP echoes `state` per the protocol without verifying it for the RP. The RP must still verify `state` itself.

The OP **SHOULD** ask the End-User whether they want to log out of the OP and **MUST** ask in the cases specified by RP-Initiated Logout, including when there is no ID Token hint or when the hint does not belong to the corresponding current session. If the user declines, the RP local session may already have been ended, yet you must not claim the OP session was logged out.

### 3.5. Logout Request Examples

GET:

~~~http
GET /connect/logout?id_token_hint=ID_TOKEN_VALUE&client_id=portal-client&post_logout_redirect_uri=https%3A%2F%2Fportal.example.test%2Flogout%2Fcallback&state=RANDOM_STATE HTTP/1.1
Host: auth.example.test
~~~

POST:

~~~http
POST /connect/logout HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

id_token_hint=ID_TOKEN_VALUE&client_id=portal-client&post_logout_redirect_uri=https%3A%2F%2Fportal.example.test%2Flogout%2Fcallback&state=RANDOM_STATE
~~~

GET is simple, but query strings can appear in browser history, proxy/access logs, or APM. POST places parameters in the form body, though redaction is still needed at proxies/APM. Do not log raw ID Token hints or `state`.

## 4. The OIDC Logout Endpoint in Spring Authorization Server

### 4.1. Enabling OIDC

Spring Authorization Server does not enable OIDC by default. In SAS 1.5.x, enable OIDC on the Authorization Server configurer:

~~~java
@Configuration(proxyBeanMethods = false)
class AuthorizationServerSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http) throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, as ->
                as.oidc(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

This is a fragment for the Authorization Server endpoints. A complete application still needs `RegisteredClientRepository`, `OAuth2AuthorizationService`, issuer/JWK configuration, and an application `SecurityFilterChain` for user login.

You can configure the path with `AuthorizationServerSettings`:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://auth.example.test")
        .oidcLogoutEndpoint("/connect/logout")
        .build();
}
~~~

If you change the path, the OIDC Provider Configuration must advertise the new `end_session_endpoint` and reverse proxies must route it properly.

### 4.2. Logout Processing Pipeline

In SAS 1.5.x, `OidcLogoutEndpointConfigurer` configures `OidcLogoutEndpointFilter`. By default, the filter uses:

- `OidcLogoutAuthenticationConverter` to convert the HTTP request into `OidcLogoutAuthenticationToken`.
- `AuthenticationManager` containing `OidcLogoutAuthenticationProvider` to validate the request.
- `OidcLogoutAuthenticationSuccessHandler` to execute logout and handle the response.
- A failure handler returning an OAuth2 error when validation fails.

`OidcLogoutAuthenticationProvider` uses `SessionRegistry` to look up `SessionInformation` associated with the End-User. The default validator checks logout parameters, including `post_logout_redirect_uri`. If customizing the validator, throw `OAuth2AuthenticationException` when validation fails.

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant F as OidcLogoutEndpointFilter
    participant C as OidcLogoutAuthenticationConverter
    participant P as OidcLogoutAuthenticationProvider
    participant R as SessionRegistry
    participant H as OidcLogoutAuthenticationSuccessHandler
    participant L as LogoutHandler

    B->>F: GET/POST /connect/logout
    F->>C: Convert HTTP request
    C-->>F: OidcLogoutAuthenticationToken
    F->>P: authenticate(token)
    P->>P: Validate ID Token/client/redirect
    P->>R: Find SessionInformation
    R-->>P: Session information
    P-->>F: Authenticated logout token
    F->>H: Authentication success
    H->>L: Perform logout
    L->>L: Invalidate session and clear context
    H-->>B: OIDC logout response/redirect
~~~

### 4.3. Customizing the OIDC Logout Success Handler

SAS provides `OidcLogoutAuthenticationSuccessHandler` and the `setLogoutHandler(...)` setter. If you need to control the repository or add cleanup, you can configure this handler:

~~~java
@Bean
OidcLogoutAuthenticationSuccessHandler oidcLogoutSuccessHandler(
        SecurityContextRepository repository) {

    SecurityContextLogoutHandler contextLogoutHandler =
        new SecurityContextLogoutHandler();

    contextLogoutHandler.setSecurityContextRepository(repository);

    OidcLogoutAuthenticationSuccessHandler successHandler =
        new OidcLogoutAuthenticationSuccessHandler();

    successHandler.setLogoutHandler(contextLogoutHandler);
    return successHandler;
}
~~~

Then attach the handler to the OIDC configurer:

~~~java
authorizationServer.oidc(oidc ->
    oidc.logoutEndpoint(logout ->
        logout.logoutResponseHandler(oidcLogoutSuccessHandler)
    )
);
~~~

This is a fragment integrated into the AS configuration. If replacing the default success handler, ensure the new handler still performs session/context cleanup and preserves OIDC response/redirect behavior. Never replace it with a lambda that only redirects the browser.

## 5. Local Logout in Spring Security

### 5.1. LogoutFilter, LogoutHandler, and LogoutSuccessHandler

Spring Security local logout is orchestrated by `LogoutFilter`:

| Component | Responsibility |
| --- | --- |
| `LogoutFilter` | Receives logout requests and coordinates the handler chain |
| `LogoutHandler` | Performs cleanup of session, context, remember-me, CSRF, or other state |
| `SecurityContextLogoutHandler` | Invalidates `HttpSession`, clears holder, Authentication, and repository |
| `CsrfLogoutHandler` | Clears the CSRF token |
| `LogoutSuccessEventPublishingLogoutHandler` | Publishes `LogoutSuccessEvent` |
| `LogoutSuccessHandler` | Redirects or produces a response after cleanup |

When CSRF protection is enabled (the default for browser/session configurations), Spring Security requires POST `/logout` with a CSRF token. GET `/logout` renders a logout confirmation page and can provide a form containing the CSRF token; it does not directly perform logout in the default CSRF-enabled setup.

~~~java
@Bean
SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
        throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/logged-out").permitAll()
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .logout(logout -> logout
            .logoutUrl("/logout")
            .invalidateHttpSession(true)
            .clearAuthentication(true)
            .deleteCookies("JSESSIONID")
            .logoutSuccessUrl("/logged-out"));

    return http.build();
}
~~~

This handles local logout for a browser application. If the same application also hosts an Authorization Server chain with `/connect/logout`, ensure each `SecurityFilterChain` matches the right endpoints.

Do not disable CSRF just to allow GET logout. An external page could trick the browser into sending a GET request and logging the user out unintentionally.

### 5.2. Processing Order

With the default configuration, `LogoutFilter` invokes the `LogoutHandler`s before calling `LogoutSuccessHandler`. Typical operations include:

1. Invalidate the HTTP session.
2. Clear `SecurityContextHolder`.
3. Clear `SecurityContextRepository`.
4. Clean up remember-me authentication.
5. Clear the CSRF token.
6. Publish the logout event.
7. Invoke the success handler.

Exact ordering can vary depending on added handlers, yet cleanup must complete before the response reports logout success.

### 5.3. Do Not Create a Custom Controller That Only Redirects

Insufficient example:

~~~java
@PostMapping("/my/logout")
String logout() {
    return "redirect:/logged-out";
}
~~~

That snippet only redirects; it does not invalidate the session or remove the context from the repository. If you truly need a custom endpoint, invoke `SecurityContextLogoutHandler`:

~~~java
@Controller
class CustomLogoutController {

    private final SecurityContextLogoutHandler logoutHandler;

    CustomLogoutController(SecurityContextLogoutHandler logoutHandler) {
        this.logoutHandler = logoutHandler;
    }

    @PostMapping("/my/logout")
    String logout(
            Authentication authentication,
            HttpServletRequest request,
            HttpServletResponse response) {

        logoutHandler.logout(request, response, authentication);
        return "redirect:/logged-out";
    }
}
~~~

Custom endpoints must be protected by CSRF and appropriate authorization. If there is no special requirement, use the Logout DSL instead of writing a custom controller.

## 6. Lifecycle of SecurityContext

### 6.1. SecurityContextHolder

`SecurityContextHolder` is the facade through which code accesses the current `SecurityContext`:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
~~~

In Servlet applications, the default strategy typically uses `ThreadLocal` to hold context per request thread. The strategy can be changed; do not assume every application uses the same strategy.

The context normally holds the authenticated `Authentication`/principal, authorities/roles, and authentication details if any. When the request finishes, filter lifecycle code clears the context from the holder to prevent leaking Authentication to another request reusing the thread. Clearing the holder at the end of a request does not delete a context already saved in the session.

Never store `SecurityContext` in static fields, mutable singleton fields, or caches shared across users.

### 6.2. SecurityContextRepository

`SecurityContextRepository` determines where Spring Security loads and saves the context between requests.

| Implementation | Behavior |
| --- | --- |
| `HttpSessionSecurityContextRepository` | Stores the context in `HttpSession` |
| `RequestAttributeSecurityContextRepository` | Keeps the context in request attributes for the same request/dispatch |
| `DelegatingSecurityContextRepository` | Combines multiple repositories |
| `NullSecurityContextRepository` | Does not persist the context for reuse on subsequent requests |

Stateful browser login applications usually store the context in `HttpSession`. Stateless API applications can use `NullSecurityContextRepository` or another mechanism.

### 6.3. Spring Security 6 and Explicit Save

In Spring Security 6, `SecurityContextHolderFilter` reads the context from the repository by default and places it in the holder; it does not automatically save every change made to the context. Authentication mechanisms that want to persist the context across subsequent requests must call `SecurityContextRepository.saveContext(...)` when needed.

~~~java
SecurityContext context =
    SecurityContextHolder.createEmptyContext();

context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);

securityContextRepository.saveContext(context, request, response);
~~~

Logout must also update the repository. Calling only `SecurityContextHolder.clearContext()` without removing the saved context allows the next request to reload the old Authentication.

## 7. SecurityContextLogoutHandler

### 7.1. Default Behavior

`SecurityContextLogoutHandler` is the `LogoutHandler` implementation that terminates the HTTP session and clears `SecurityContext`.

| Configuration | Default | Effect |
| --- | --- | --- |
| `invalidateHttpSession` | `true` | Invalidates the session if it exists |
| `clearAuthentication` | `true` | Removes Authentication from the old context |
| `SecurityContextHolderStrategy` | Strategy from `SecurityContextHolder` | Clears the current context |
| `SecurityContextRepository` | `HttpSessionSecurityContextRepository` | Saves an empty context |

The core logic can be summarized as:

~~~java
public void logout(
        HttpServletRequest request,
        HttpServletResponse response,
        Authentication authentication) {

    if (invalidateHttpSession) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
    }

    SecurityContext context = securityContextHolderStrategy.getContext();
    securityContextHolderStrategy.clearContext();

    if (clearAuthentication) {
        context.setAuthentication(null);
    }

    SecurityContext emptyContext =
        securityContextHolderStrategy.createEmptyContext();

    securityContextRepository.saveContext(
        emptyContext, request, response);
}
~~~

This is a condensed version to explain behavior, not a full copy of the framework source.

The handler uses `request.getSession(false)` to avoid creating a new session during logout. It invalidates the session if configured, clears the holder, removes Authentication from the old context, and saves an empty context through the handler's repository.

### 7.2. Why Does clearAuthentication Matter?

A concurrent request might still hold a reference to the same `SecurityContext` object. By default, `clearAuthentication=true` removes Authentication from the old context to reduce the risk of another request continuing to use that reference.

However, logout does not automatically abort in-flight requests or already-started business transactions. Sensitive operations should verify permissions/session/token state at execution time.

### 7.3. Using the Same SecurityContextRepository

If an application uses a custom repository, the logout handler must save empty state to the repository matching the filter chain. For example, a repository combining request attributes and session:

~~~java
@Bean
SecurityContextRepository securityContextRepository() {
    return new DelegatingSecurityContextRepository(
        new RequestAttributeSecurityContextRepository(),
        new HttpSessionSecurityContextRepository());
}
~~~

Attach the repository to the filter chain:

~~~java
http.securityContext(securityContext ->
    securityContext.securityContextRepository(repository));
~~~

And pass the same instance to the logout handler:

~~~java
SecurityContextLogoutHandler logoutHandler =
    new SecurityContextLogoutHandler();

logoutHandler.setSecurityContextRepository(repository);
~~~

`SecurityContextLogoutHandler` defaults to `HttpSessionSecurityContextRepository`. If the filter chain uses a different repository, configure it explicitly so the handler does not clear one place while the next request reads the old context from another.

With `NullSecurityContextRepository` or stateless authentication, explicitly identify which HTTP session (if any) needs invalidation and which tokens need revocation; do not introduce session state solely to support logout.

## 8. SessionRegistry and OIDC Logout

### 8.1. Role of SessionRegistry

When OIDC is enabled, Spring Authorization Server uses `SessionRegistry` to track authenticated sessions. `OidcLogoutAuthenticationProvider` uses the registry to locate `SessionInformation` tied to the End-User requesting logout.

`SessionRegistry` does not itself replace invalidating `HttpSession` or clearing `SecurityContext`. The registry helps look up the session; the success handler and `LogoutHandler` perform the cleanup.

If the application does not register a `SessionRegistry` bean, SAS uses the default `SessionRegistryImpl`. If the application registers its own `SessionRegistryImpl`, register `HttpSessionEventPublisher` so the registry receives session lifecycle events, such as `SessionDestroyedEvent`, and removes the corresponding `SessionInformation`.

~~~java
@Configuration
class SessionRegistryConfiguration {

    @Bean
    SessionRegistry sessionRegistry() {
        return new SessionRegistryImpl();
    }

    @Bean
    HttpSessionEventPublisher httpSessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }
}
~~~

### 8.2. Session Registration

The default `SessionAuthenticationStrategy` attached to SAS's Authorization Endpoint registers authenticated sessions. If an application replaces it with a custom authentication flow or session strategy, ensure sessions are still registered in the registry used by the OIDC Logout provider.

If Spring Security Concurrent Session Control is also used, share the same `SessionRegistry` so concurrent session management and OIDC logout see consistent state.

~~~java
http.sessionManagement(session -> session
    .maximumSessions(3)
    .sessionRegistry(sessionRegistry));
~~~

This is a fragment for the browser login `SecurityFilterChain`. Do not assume merely declaring a `SessionRegistry` bean suffices for every custom authentication flow to register sessions automatically.

### 8.3. Principal and Tenant Mapping

The registry tracks principal/session pairs. If an application uses pairwise subjects, multiple issuers, or multi-tenancy, unify how principals are mapped across `Authentication`, `SessionRegistry`, and the ID Token. Two tenants may share the same username; never let logout in one tenant close a session in another tenant.

## 9. Cookies, Remember-Me, and CSRF

### 9.1. Invalidating a Session vs. Deleting Cookies

`HttpSession.invalidate()` ends the server-side session. The browser may still send the old session cookie on the next request, yet that session ID no longer maps to a valid session.

Deleting the `JSESSIONID` cookie is a browser-side operation. When needed, the cookie must be deleted with a Path/Domain matching the original cookie. Server-side session invalidation remains the decisive step.

### 9.2. Remember-Me

If the application enables remember-me, clean up the remember-me cookie/token. If you only invalidate `HttpSession` while keeping the remember-me credential, the browser can be re-authenticated automatically.

Spring Security includes matching handlers for `TokenRememberMeServices` or `PersistentTokenBasedRememberMeServices`; use the Logout DSL so default handlers are coordinated.

### 9.3. CSRF Tokens

`CsrfLogoutHandler` clears the stored CSRF token. The next page needs to obtain a fresh token per repository/policy. Never reuse an old CSRF token from a terminated session.

### 9.4. Clear-Site-Data

Some browser applications can send the `Clear-Site-Data` header to instruct the browser to clear cache/cookies/storage within an appropriate scope. This option has a broad blast radius; do not wipe storage or cache if the application relies on retaining client-side data. This header does not replace session invalidation or token revocation.

## 10. Concurrent Requests, Expiration, and Async Tasks

### 10.1. Requests Concurrent with Logout

Suppose request A is reading data while request B executes logout. Request A may already have loaded `Authentication` into its context and begun processing before B clears the context.

By default, `SecurityContextLogoutHandler` removes `Authentication` from the old context object, reducing certain risks with shared references. However, logout does not automatically stop in-flight requests, roll back committed transactions, or cancel already-dispatched business tasks.

For sensitive operations, re-check permissions/session/token state immediately before critical side effects.

### 10.2. expireNow vs. Immediate Invalidation

`SessionInformation.expireNow()` marks a session as expired. `ConcurrentSessionFilter` can detect that state on the next request and trigger logout handling. Marking a session expired does not necessarily mean `HttpSession.invalidate()` is called synchronously at the moment of marking.

If immediate session termination is required, ensure an appropriate invalidation/handler action runs. Do not assume the OIDC Logout Provider always uses the exact same handling as concurrent session control; verify your provider version and write integration tests.

### 10.3. SecurityContext Propagated to Executors

Spring Security provides wrappers such as `DelegatingSecurityContextRunnable` and `DelegatingSecurityContextExecutor` to propagate context to other tasks. A task already launched with a propagated context can keep running after the logout request finishes.

Never treat a `SecurityContext` snapshot as indefinite proof of authorization. For sensitive background tasks, establish cancellation policies or re-verify permissions/session/token state at execution time.

## 11. Multi-Instance Authorization Server

`SessionRegistryImpl` is by default an in-memory registry for a single application instance. In a cluster:

- A user logs in on node A.
- The logout request is routed to node B.
- Node B's registry may not know about the session registered on node A.
- The session store and local registries can drift out of sync.
- Node restarts can wipe local registry entries while the shared session persists.

~~~mermaid
flowchart LR
    B["Browser"] --> LB["Load Balancer"]
    LB --> A["Authorization Server Node A"]
    LB --> C["Authorization Server Node B"]
    A --> S["Shared Session Store"]
    C --> S
    A --> R["Shared Session Registry"]
    C --> R
~~~

### 11.1. Shared Session Store

Spring Session with Redis/JDBC or a suitable distributed session solution lets multiple nodes access the same session state. When one node invalidates a session, other nodes must see that the session is no longer valid.

`SpringSessionBackedSessionRegistry` can be used for concurrent session/session lookups in compatible Spring Session setups. Verify your version and how SAS OIDC logout uses the registry; a shared session store alone does not turn every local `SessionRegistryImpl` into a distributed registry.

### 11.2. Synchronizing the Registry and Session Store

Verify that:

1. Sessions are registered after authentication on every node.
2. Session destruction/expiration propagates to the registry.
3. The OIDC Logout provider uses the right registry.
4. Other nodes cannot load `SecurityContext` from an invalidated session.
5. Caches/session metadata do not retain stale Authentication beyond policy limits.
6. Stale registry entries have TTL/lifecycle cleanup.
7. A logout request on another node still locates the right user/session/tenant.

Sticky sessions only reduce the chance of requests hitting another node; they do not replace shared state when failover or rolling deployments are needed.

## 12. Stateless APIs, JWTs, and Token Revocation

A stateless Resource Server receives an access token on every request:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN
~~~

In this model, Spring Security builds a `SecurityContext` for the request after validating the token and clears the context when the request ends. There is no browser session at the Resource Server to invalidate.

Calling `SecurityContextHolder.clearContext()` clears only the current request's context. The client can still send the JWT again on the next request, and the Resource Server will re-validate the token.

If tokens must be prevented from being used prior to expiration, consider:

- The Token Revocation Endpoint per RFC 7009 if supported by the token type/implementation.
- Opaque/reference tokens with introspection.
- A denylist by `jti` or token hash, with propagation and cache policies.
- Event-driven invalidation for Resource Servers.
- Short access token TTLs.
- Revoking refresh tokens to block issuing new access tokens.

OIDC logout also does not automatically delete consents or OAuth2 authorization records. Never delete `UserDetails`, accounts, or audit records merely because a user logged out; those records have their own lifecycles.

## 13. Front-Channel and Back-Channel Logout

RP-Initiated Logout is an RP actively asking the OP to end the session. Front-Channel and Back-Channel Logout are mechanisms for the OP to notify other RPs when the session ends.

### 13.1. Front-Channel Logout

The OP uses the browser to notify participating RPs. This mechanism depends on browser navigation/iframes and cookie policies, and browsers may block third-party cookies. Each RP must identify the associated local session and clean it up properly.

### 13.2. Back-Channel Logout

The OP sends a Logout Token to each RP's registered Back-Channel Logout URI. The RP verifies the signature, issuer, audience, event claim, and session/subject conditions, then deletes the corresponding local sessions.

A Logout Token is a JWT following the Back-Channel Logout profile; it is neither an access token for calling APIs nor an ID Token sent to UserInfo.

### 13.3. Session Correlation

The RP needs proper mapping across issuer (`iss`), subject (`sub`), session ID (`sid`) if issued by the profile, local application session ID, and client/tenant context.

Do not rely solely on username/email, as those values can change or collide. If pairwise subjects are used, mapping must respect client/sector boundaries.

### 13.4. Do Not Infer Features from Enabling OIDC

Spring Authorization Server provides the RP-Initiated Logout Endpoint. Front-Channel and Back-Channel Logout are separate profiles; do not assume they are automatically active just because you called `oidc(Customizer.withDefaults())`. Verify actual framework capabilities, RP support, and notification handlers.

## 14. Combined Reference Configuration

The following example shows how to share `SecurityContextRepository` between the Authorization Server chain and the OIDC logout handler. A real application still needs core beans, a login chain, issuer/JWK setup, and persistence.

~~~java
@Configuration(proxyBeanMethods = false)
class AuthorizationServerLogoutConfiguration {

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository());
    }

    @Bean
    SessionRegistry sessionRegistry() {
        return new SessionRegistryImpl();
    }

    @Bean
    HttpSessionEventPublisher httpSessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }

    @Bean
    OidcLogoutAuthenticationSuccessHandler oidcLogoutSuccessHandler(
            SecurityContextRepository repository) {

        SecurityContextLogoutHandler logoutHandler =
            new SecurityContextLogoutHandler();

        logoutHandler.setSecurityContextRepository(repository);

        OidcLogoutAuthenticationSuccessHandler successHandler =
            new OidcLogoutAuthenticationSuccessHandler();

        successHandler.setLogoutHandler(logoutHandler);
        return successHandler;
    }

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurity(
            HttpSecurity http,
            SecurityContextRepository repository,
            OidcLogoutAuthenticationSuccessHandler successHandler)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .securityContext(securityContext ->
                securityContext.securityContextRepository(repository))
            .with(authorizationServer, as ->
                as.oidc(oidc ->
                    oidc.logoutEndpoint(logout ->
                        logout.logoutResponseHandler(successHandler))
                ))
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

        return http.build();
    }
}
~~~

Points to verify when applying this:

- The repository in the AS chain and the logout handler is the same instance.
- The `SessionRegistry` used by the OIDC provider is the configured registry.
- If using concurrent session control, the registry is shared.
- If running in a cluster, a shared session/registry strategy is chosen.
- If the default success handler already meets requirements, do not replace it just to duplicate cleanup.
- If adding a custom handler, do not drop redirect validation, OIDC response handling, or session cleanup.
- Do not treat the fragment above as a complete Authorization Server configuration.

## 15. Testing Logout and SecurityContext Cleanup

### 15.1. Testing Local Logout

With MockMvc, verify not only the redirect, but also the old session and subsequent requests. Illustrative test body:

~~~java
@Test
void logoutEndsAuthenticatedSession() throws Exception {
    MvcResult loginResult = mockMvc.perform(
            formLogin().user("alice").password("password"))
        .andExpect(authenticated())
        .andReturn();

    MockHttpSession session =
        (MockHttpSession) loginResult.getRequest().getSession(false);

    assertThat(session).isNotNull();

    mockMvc.perform(post("/logout")
            .session(session)
            .with(csrf()))
        .andExpect(status().is3xxRedirection());

    assertThat(session.isInvalid()).isTrue();
}
~~~

The test needs form login configuration, a user fixture, MockMvc, and CSRF. Then send a protected request with the old cookie/session to confirm the user is no longer authenticated. Using only `with(user("alice"))` on a single request does not prove that the context persisted in the session was cleared.

### 15.2. Testing SecurityContextLogoutHandler

~~~java
@Test
void logoutHandlerClearsAuthenticationAndSession() {
    SecurityContext context =
        SecurityContextHolder.createEmptyContext();

    context.setAuthentication(
        new TestingAuthenticationToken("alice", "n/a", "ROLE_USER"));

    SecurityContextHolder.setContext(context);

    MockHttpServletRequest request = new MockHttpServletRequest();
    MockHttpSession session = (MockHttpSession) request.getSession(true);

    SecurityContextLogoutHandler handler =
        new SecurityContextLogoutHandler();

    handler.logout(
        request,
        new MockHttpServletResponse(),
        context.getAuthentication());

    assertThat(SecurityContextHolder.getContext().getAuthentication())
        .isNull();

    assertThat(context.getAuthentication()).isNull();
    assertThat(session.isInvalid()).isTrue();
}
~~~

This is an illustrative test body. To verify repository persistence, inject the same `SecurityContextRepository` into the handler and inspect persisted state after logout; do not assert only that the holder was cleared.

### 15.3. Testing the OIDC Logout Endpoint

Setup:

- OIDC configurer enabled.
- `RegisteredClient` has valid post-logout URIs.
- ID Token hint issued by the right OP.
- Corresponding session/authorization record.
- `SessionRegistry` populated.
- OIDC success handler and `LogoutHandler` configured.
- `SecurityContextRepository` shared properly.

Expectations:

1. Valid request is verified by the provider.
2. Success handler invokes `LogoutHandler`.
3. Associated `HttpSession` is invalidated.
4. `SecurityContextHolder` no longer holds Authentication.
5. Repository does not restore the old Authentication.
6. Redirect goes only to registered URIs.
7. Subsequent requests are not re-authenticated using the old session.

### 15.4. Test Matrix

| Scenario | Expected Result |
| --- | --- |
| POST local logout with CSRF | `LogoutHandler` runs, session invalidated |
| POST local logout missing CSRF | Rejected when CSRF is enabled |
| Calling only `clearContext` | Test shows repository can reload context; not sufficient |
| `SecurityContextLogoutHandler` using the right repository | Empty context is saved |
| Handler using a different repository than filter chain | Test catches lingering old context |
| Old `JSESSIONID` cookie re-sent | Session is no longer valid |
| Remember-me enabled | Token/cookie cleaned up |
| OIDC metadata | Contains `end_session_endpoint` when OIDC logout/discovery enabled |
| ID Token hint with wrong issuer | OP does not process based on that token |
| Client ID mismatch | Logout request rejected |
| Unregistered `post_logout_redirect_uri` | No redirect to that URI |
| Wrong or replayed `state` | RP rejects callback |
| `SessionRegistry` contains session | Provider finds `SessionInformation` |
| `SessionRegistry` missing entry | Test detects missing integration/session strategy |
| Session invalidated | Registry receives lifecycle event |
| Login node A, logout node B | Node B sees shared session/registry state |
| Two RPs share SSO | Local logout at one RP does not delete OP session automatically |
| OP logout succeeds | Token state verified separately |
| JWT access token after logout | Do not assume JWT automatically becomes invalid |
| Async task already received context | Dedicated cancellation/revalidation policy enforced |
| Multi-tenant same username | Only session for the right issuer/tenant is terminated |

## 16. Troubleshooting and Operations

### 16.1. Symptoms and Causes

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Logout redirect succeeds yet user remains logged in | Redirected only, session not invalidated | Check `LogoutHandler` and success handler |
| Post-logout request still authenticated | Repository still holds old context | Use the same repository and save empty context |
| Holder cleared yet session persists | Called only `clearContext` | Invalidate `HttpSession` |
| Session invalid yet registry still holds entry | Missing lifecycle events | Check `HttpSessionEventPublisher` |
| Logout on another node cannot find session | Local `SessionRegistry` | Shared session/registry |
| Other RPs still logged in | Logout notifications not implemented | Front-/Back-Channel Logout |
| API still accepts JWT | Token not revoked or RS verifies offline | Introspection/denylist/TTL/revocation |
| `/connect/logout` returns 404 | OIDC not enabled or different path | OIDC configurer and `AuthorizationServerSettings` |
| Discovery missing `end_session_endpoint` | OIDC metadata not published | Check Provider Configuration |
| Redirect rejected | URI unregistered or not exact match | Check `RegisteredClient` |
| Remember-me logs user back in automatically | Cookie/token not cleared | Configure remember-me logout handler |
| Background task still running | Task captured context before logout | Cancellation and authorization re-check |
| Old cookie remains in browser | Path/domain mismatch or cookie not deleted | Check cookie attributes |

### 16.2. Runbook When Session Does Not End

1. Determine whether the request hits local `LogoutFilter` or OIDC `OidcLogoutEndpointFilter`.
2. Check filter chain and endpoint matchers.
3. Check whether the OIDC provider verified the request successfully.
4. Check which success handler actually ran and whether `LogoutHandler` executed.
5. Inspect `request.getSession(false)` before/after cleanup.
6. Inspect `SecurityContextHolder` after logout.
7. Check which repository is used to load context on the next request.
8. Check `SessionRegistry` mappings and lifecycle events.
9. In a cluster, verify whether session ID/principal are visible across nodes.
10. If APIs still accept tokens, check token revocation/introspection/denylist separately.
11. If other RPs remain logged in, check Front-/Back-Channel Logout and local session mappings.
12. Measure elapsed time from logout until each component stops accepting old state.

Never work around issues by merely redirecting to the login page or deleting one cookie without verifying server-side state.

### 16.3. Metrics and Auditing

Track logout success/failure by client and endpoint, session invalidation latency, `SessionRegistry` lookup misses/stale entries, requests using expired session IDs, OIDC hint validation failures, rejected redirect rate, distributed session propagation delay, and time until Resource Servers stop accepting revoked tokens.

Do not log ID Tokens, access tokens, refresh tokens, session cookies, or full Logout Requests. Use correlation IDs, client ID, issuer, error codes, and protected identifiers.

## 17. Design Mistakes to Avoid

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Calling only `SecurityContextHolder.clearContext()` | Repository can still retain old context | Save empty context |
| Only invalidating the session | Current context reference may still hold Authentication | Clear holder and Authentication |
| Only deleting cookies | Server-side session still exists | Invalidate `HttpSession` |
| Custom controller that only redirects | User remains authenticated | Invoke `LogoutHandler` or use Logout DSL |
| Handler uses a different repository than filter chain | Next request reloads old context | Share the same repository |
| Creating a new session during logout | Leaves behind an unintended new session | Use `getSession(false)` |
| Treating `SessionRegistry` as a session store | Does not invalidate `HttpSession` | Combine with `LogoutHandler` |
| Using local `SessionRegistryImpl` in a cluster | Other nodes cannot see the session | Shared registry/session strategy |
| Omitting `HttpSessionEventPublisher` when needed | Registry retains stale entries | Register lifecycle publisher |
| Disabling `clearAuthentication` without reason | Concurrent requests may retain Authentication references | Keep default and test |
| Assuming OP logout logs out all RPs | Other RPs' local sessions remain | Front-/Back-Channel Logout |
| Assuming OP logout revokes JWTs | APIs still accept unexpired tokens | Token revocation policy |
| Assuming clearing context cancels async tasks | Running tasks continue | Cancellation/authorization re-check |
| Custom success handler only redirects | Skips session/context cleanup | Keep `LogoutHandler` in success flow |
| Disabling local logout CSRF | Logout CSRF | Use POST + CSRF |

## 18. Self-Check Questions

**Question 1.** How do `SecurityContextHolder` and `SecurityContextRepository` differ?

**Answer:** The holder supplies the context for the current request/thread; the repository persists/loads the context between requests.

**Question 2.** Why is calling `SecurityContextHolder.clearContext()` alone insufficient?

**Answer:** The old context may still be stored in the repository/session and reloaded on the next request.

**Question 3.** What does `SecurityContextLogoutHandler` do by default?

**Answer:** Invalidates `HttpSession` if present, clears the holder, removes Authentication from the old context, and saves an empty context through the handler's repository.

**Question 4.** Why must the handler use the same repository as `SecurityFilterChain`?

**Answer:** Otherwise, the handler may save an empty context somewhere else while the filter still reads the old Authentication from the original repository.

**Question 5.** What did Spring Security 6 change about `SecurityContext` persistence?

**Answer:** `SecurityContextHolderFilter` reads the context by default; applications must save explicitly when persisting changes. Logout must likewise persist empty state.

**Question 6.** Does `SessionRegistry` invalidate `HttpSession` automatically?

**Answer:** No. The registry tracks/looks up session information; `LogoutHandler` performs session/context cleanup.

**Question 7.** Why register `HttpSessionEventPublisher`?

**Answer:** So `SessionRegistryImpl` receives session lifecycle events such as `SessionDestroyedEvent` and cleans up corresponding `SessionInformation`.

**Question 8.** How does SAS OIDC logout differ from `POST /logout`?

**Answer:** OIDC logout uses the OIDC endpoint filter/provider and `SessionRegistry` to handle RP-Initiated Logout; local logout uses Spring Security's `LogoutFilter` and `LogoutHandler` chain.

**Question 9.** Does logout automatically revoke JWT access tokens?

**Answer:** No. JWTs can remain valid until expiry if Resource Servers have no revocation check.

**Question 10.** Why can an async task continue after logout?

**Answer:** The task may already have captured `SecurityContext` or started executing; clearing the request's context does not automatically cancel the task.

**Question 11.** Is `SessionRegistryImpl` suitable for a multi-node cluster?

**Answer:** An in-memory registry is not shared across nodes automatically. A suitable shared registry/session tracking mechanism is needed.

**Question 12.** Is asserting only the redirect sufficient to test logout?

**Answer:** No. You must verify that the session is invalidated, the holder is cleared, the repository does not restore Authentication, and subsequent requests are no longer authenticated with the old session.

## 19. Production Deployment Checklist

- [ ] Distinguish RP local session, OP session, `HttpSession`, `SecurityContext`, and `SessionRegistry`.
- [ ] OIDC Logout Endpoint is enabled and routed accurately in the AS `SecurityFilterChain`.
- [ ] OP advertises `end_session_endpoint` in metadata.
- [ ] ID Token hint is verified from the right issuer/client/session.
- [ ] `post_logout_redirect_uri` is registered separately and exact-matched.
- [ ] RP generates, stores, and verifies one-time `state`.
- [ ] Local logout uses standard `LogoutFilter`/`LogoutHandler`.
- [ ] Local logout POST keeps CSRF protection.
- [ ] `SecurityContextHolder` is cleared.
- [ ] Authentication is cleared from the old context where appropriate.
- [ ] Empty context is persisted through the right `SecurityContextRepository`.
- [ ] Handler and filter chain share the same custom repository.
- [ ] No new session is created during logout.
- [ ] Remember-me, CSRF, and cookies are cleaned up per policy.
- [ ] `SessionRegistry` receives lifecycle events.
- [ ] Concurrent session control shares the registry when needed.
- [ ] Multi-instance deployments have shared session tracking.
- [ ] Custom success handlers do not skip cleanup.
- [ ] Async tasks have dedicated cancellation/revalidation policies.
- [ ] OP logout is separated from RP notifications and token revocation.
- [ ] Integration tests verify session, holder, repository, and post-logout requests.
- [ ] Monitoring tracks logout failures, session registry misses, and stale sessions.
- [ ] Audits do not record raw tokens, cookies, or credentials.

## 20. References and Conclusion

- [OpenID Connect RP-Initiated Logout 1.0 Final](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html)
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Core Model / SessionRegistry](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server 1.5.8 — OidcLogoutAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcLogoutAuthenticationProvider.html)
- [Spring Authorization Server 1.5.8 — OidcLogoutAuthenticationSuccessHandler API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/web/authentication/OidcLogoutAuthenticationSuccessHandler.html)
- [Spring Authorization Server 1.5.8 — OidcLogoutEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OidcLogoutEndpointConfigurer.html)
- [Spring Security 6.5 — Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — SecurityContextLogoutHandler API](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/web/authentication/logout/SecurityContextLogoutHandler.html)
- [Spring Session — Session Registry integrations](https://docs.spring.io/spring-session/reference/api.html)

**Conclusion:** Terminating an Authorization Server session requires coordinating the HTTP session, `SecurityContextHolder`, `SecurityContextRepository`, and `SessionRegistry`. In Spring Authorization Server, the OIDC Logout Endpoint flows through the converter/provider; the provider uses `SessionRegistry` to locate the End-User's session and the success handler performs cleanup via `LogoutHandler`. `SecurityContextLogoutHandler` invalidates the session, clears the holder, clears Authentication from the old context, and saves an empty context. In Spring Security 6, persisting empty state is especially important because `SecurityContextHolderFilter` reads the context by default without automatically saving all mutations. Production setups must keep repositories synchronized, update `SessionRegistry`, handle distributed sessions, and separate OP logout from local RP sessions, logout notifications, and token revocation. Only when all of these states are tested together can a system avoid the bug where a browser sees a logged-out page yet the next request restores the old Authentication.
