# 7.7. SecurityContext, HttpSession, and Principal After Login

## Lesson Objectives

In a Servlet application using **Spring Security OAuth 2.0 Client and OpenID Connect (OIDC) Login**, after the OpenID Provider (OP) authenticates the user and returns an authorization code, Spring Security must convert the protocol result into **application login state**. The three most important concepts are:

- **`SecurityContext`:** holds the `Authentication` object for the request/security context.
- **`HttpSession`:** can maintain login state across multiple HTTP requests in a Servlet web application.
- **Principal:** represents the authenticated entity; for OIDC Login, typically an `OidcUser` containing the ID token and processed claims.

After this lesson, you will be able to explain the lifecycle of these three components, read user information after OIDC Login, distinguish the application session from the Single Sign-On (SSO) session at the OP, and avoid confusing login state with access tokens used to call APIs.

## 1. One OIDC Login and Many HTTP Requests

Suppose an **Employee Portal** application built with Spring Boot has a `/profile` page requiring login. The corporate OP manages employee accounts.

The first time the browser visits the page:

1. Spring Security sees the request has no authenticated user.
2. The application redirects the browser to the OP to perform OIDC Authorization Code flow.
3. The user authenticates at the OP; the browser returns to Spring Security's callback with an authorization code.
4. Spring Security exchanges the code for tokens, verifies the OIDC result, and creates an `Authentication` object.
5. The application persists the authentication result via the session mechanism so subsequent requests recognize the user is logged in.

When the user reloads `/profile`, **there is no need to exchange an authorization code and verify an ID token from scratch on every request**. The application can restore login state from the Servlet session if the session remains valid and configuration permits.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant APP as Spring Boot Servlet App
    participant OP as OpenID Provider
    U->>B: Open /profile
    B->>APP: GET /profile, no valid session yet
    APP-->>B: 302 initiate OIDC Login
    B->>OP: Authorization Request
    OP->>U: Authenticate / consent if needed
    OP-->>B: Redirect with code and state
    B->>APP: GET /login/oauth2/code/corporate
    APP->>OP: Exchange code for tokens
    OP-->>APP: ID token + access token (if issued)
    Note over APP: Create Authentication containing OidcUser
    Note over APP: Save SecurityContext per configuration
    APP-->>B: Response and session cookie
    B->>APP: GET /profile, sends session cookie
    Note over APP: Restore SecurityContext
    APP-->>B: /profile content for principal
~~~

Distinction to keep in mind: **OIDC authenticating the user at the OP** and **Spring Security maintaining local login state in the application** are related tasks, not the same thing.

## 2. Three Layers of State After OIDC Login

| Component | Question it answers | Where does it live? | What not to confuse it with |
|---|---|---|---|
| `Authentication` | Who is authenticated by Spring Security and what authorities do they hold? | Inside `SecurityContext` | Not an ID token or access token |
| `SecurityContext` | Which `Authentication` does the current security context contain? | Typically bound to request execution; saved/restored via repository | Not synonymous with the entire `HttpSession` |
| `HttpSession` | What server state must persist across multiple requests in the same session? | Servlet server or integrated session store | Not the login session at the OP |
| `OidcUser` | Who is the OIDC principal, and which ID token and claims apply? | The principal of `Authentication` after OIDC Login | Does not replace business authorization logic |
| `OAuth2AuthorizedClient` | Which access token/refresh token did the client receive under the authorization grant? | Separate authorized client store | Not `SecurityContext` or principal |

You can visualize it as:

~~~text
HttpSession (when using session to maintain login)
└── SecurityContext
    └── Authentication
        ├── principal -> OidcUser
        │   ├── OidcIdToken
        │   ├── OidcUserInfo (if present)
        │   └── claims / attributes
        ├── authorities
        └── authenticated = true
~~~

This is a **conceptual diagram**, not a description of every session attribute or storage layout. Spring Security uses abstractions and repositories to restore/save state; applications should not depend directly on internal session layout.

## 3. What Is `SecurityContext`?

### 3.1. `SecurityContext` holds `Authentication`

The central interface is:

~~~java
org.springframework.security.core.context.SecurityContext
~~~

It provides reading/writing of `Authentication`:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
~~~

For a logged-in request, `authentication` typically contains the principal and authorities established by Spring Security.

Commonly used `Authentication` methods:

| API | Meaning |
|---|---|
| `getPrincipal()` | Authenticated entity; for OIDC Login typically `OidcUser` |
| `getAuthorities()` | `GrantedAuthority` instances mapped for the principal |
| `getName()` | Identifier name per the `Authentication` implementation |
| `isAuthenticated()` | Authentication status of the object |
| `getCredentials()` | Credential data if present; never treat as a password source |
| `getDetails()` | Additional authentication-mechanism details |

**`Authentication.isAuthenticated()` does not mean the user is authorized to access every feature.** Access decisions still depend on request matchers, authorities, roles, business rules, and other checks.

### 3.2. Role of `SecurityContextHolder`

`SecurityContextHolder` lets code running during a request access the corresponding `SecurityContext`.

In typical Servlet applications, `SecurityContextHolder` uses a strategy binding the context to the **thread handling the request** (by default `MODE_THREADLOCAL`).

Implications:

- Controllers, services, and Spring Security components on the same execution thread can read the current authentication.
- When the request finishes, the framework clears the context so a thread reused by the server does not accidentally retain the previous request's `Authentication`.
- **ThreadLocal does not persist login between two HTTP requests.** Maintaining state requires a repository/session or per-request re-authentication.
- If spawning threads manually, using `@Async`, or running work outside the request thread, **do not assume the context propagates automatically to the new thread**. Use Spring Security-supported context propagation mechanisms, such as `DelegatingSecurityContext...` wrappers, when genuinely needed.

Avoid switching `SecurityContextHolder` to a global application-wide shared mode in a web app. Doing so risks exposing one request's principal to another request.

### 3.3. What is the lifecycle of `SecurityContext` within a request?

Conceptually:

~~~mermaid
flowchart TD
    A["HTTP request arrives at Servlet app"] --> B["Spring Security Filter Chain"]
    B --> C["SecurityContextRepository restores context if present"]
    C --> D["SecurityContextHolder for request thread"]
    D --> E["Authentication / Authorization filters"]
    E --> F["Controller and Service use principal"]
    F --> G["Complete response"]
    G --> H["Save context if changed per configuration"]
    H --> I["Clear SecurityContextHolder for request"]
~~~

Exact filters and save timing depend on the Spring Security version and configuration. In Spring Security 6, `SecurityContextHolderFilter` focuses on **reading/setting the context**; when an application sets `Authentication` manually via a custom mechanism, it may need to **explicitly save the context** via `SecurityContextRepository`. Built-in login filters provided by Spring Security, such as OAuth2 Login, handle persisting authentication results per the framework's flow.

In older versions or certain configurations, you may encounter `SecurityContextPersistenceFilter`. Do not assume "just calling `SecurityContextHolder.setContext(...)` will auto-save the session across every version" when implementing custom authentication.

## 4. How Does `HttpSession` Maintain Login State?

### 4.1. HTTP is a stateless request protocol

Suppose the browser sends:

~~~http
GET /profile HTTP/1.1
Host: portal.example.com
~~~

On each request, the server must know which session the client belongs to. The Servlet container can manage an `HttpSession` and issue a session identifier to the browser via a cookie, commonly named:

~~~http
Set-Cookie: JSESSIONID=<opaque-session-id>; Path=/; HttpOnly; Secure
~~~

Subsequent requests send the cookie:

~~~http
GET /profile HTTP/1.1
Host: portal.example.com
Cookie: JSESSIONID=<opaque-session-id>
~~~

The cookie illustrated here holds a **session identifier**, not `OidcUser` or the entire `SecurityContext`. Session data typically resides on the server or in an integrated session data store.

In practice, cookie names, attributes, and storage mechanisms can vary by Servlet container, Spring Session, and deployment configuration.

### 4.2. From `HttpSession` to `SecurityContextRepository`

Spring Security does not force controllers to interact directly with `HttpSession` to read authentication state. It uses the abstraction:

~~~java
org.springframework.security.web.context.SecurityContextRepository
~~~

In session-enabled Servlet configurations, an implementation such as `HttpSessionSecurityContextRepository` can store a `SecurityContext` in `HttpSession` for later restoration. A common default session attribute key is:

~~~text
SPRING_SECURITY_CONTEXT
~~~

In modern versions, `DelegatingSecurityContextRepository` can combine multiple stores, such as `RequestAttributeSecurityContextRepository` and `HttpSessionSecurityContextRepository`, to handle dispatches and session-based persistence.

**Do not write business logic reading `session.getAttribute("SPRING_SECURITY_CONTEXT")` directly.** Retrieve `Authentication` via controller parameters, `@AuthenticationPrincipal`, or Spring Security APIs. Internal session layout may change depending on configuration.

### 4.3. Why can a session preserve login across multiple requests?

When OIDC Login succeeds, `Authentication` is created and placed into `SecurityContext`; in a session-based web app, the result is persisted via the configured `SecurityContextRepository`.

On the next request:

1. The browser sends the session cookie.
2. The Servlet container or session store looks up the matching `HttpSession`.
3. Spring Security restores the context and places it into `SecurityContextHolder` for that request.
4. The authorization filter sees a valid `Authentication` and lets the request proceed if permissions allow.
5. The controller can read `OidcUser` without calling the OP again.

If the cookie is missing, the session expires or is invalidated, or the session store no longer holds the data, the application treats the request as unauthenticated. At that point, a new OIDC Login flow can begin.

### 4.4. Is a session created on every request?

Not necessarily. The session creation policy governs this:

| `SessionCreationPolicy` | Basic behavior |
|---|---|
| `ALWAYS` | Spring Security always creates a session |
| `IF_REQUIRED` | Creates a session only when needed |
| `NEVER` | Spring Security does not create a session itself, though it may use an existing one |
| `STATELESS` | Spring Security neither creates nor uses `HttpSession` to obtain `SecurityContext` |

An interactive **Servlet OIDC Login** app normally needs state across browser redirects—for example, retaining the original Authorization Request and `state` to validate the callback, and storing the session after login.

Blindly applying `SessionCreationPolicy.STATELESS` to the same filter chain handling `oauth2Login()` can break the assumptions of the default login flow. If you want a sessionless architecture, you must explicitly design how authorization requests are stored, callbacks are protected, and state is maintained/authenticated; it is not just flipping an enum.

## 5. What Is Stored in the Session Before and After the Callback?

In OIDC Authorization Code flow there are **two related yet distinct types of state**.

### 5.1. Before the user logs in successfully

When starting an authorization request, Spring Security must remember enough data to validate the callback:

- Which registration the client is using.
- The `state` value and required authorization request data.
- `nonce`/PKCE values when used in OIDC/Authorization Code flow.
- Potentially the original URL the user requested, to redirect back after login.

In standard default setups, `HttpSessionOAuth2AuthorizationRequestRepository` saves the Authorization Request in `HttpSession` for retrieval when the callback arrives.

This state **does not yet mean the user is authenticated in the application**.

### 5.2. After the OIDC callback succeeds

Spring Security has:

- Verified `state` and authorization response protection conditions.
- Exchanged the authorization code for tokens at the token endpoint.
- Verified the OIDC result according to applicable rules.
- Constructed the OIDC principal and `Authentication`.
- Stored `Authentication` in `SecurityContext` so the app can use it on subsequent requests.

Illustrative table of state types:

| Stage | State | Meaning |
|---|---|---|
| Login initiation | `OAuth2AuthorizationRequest` | Data for redirect flow and callback verification |
| Callback succeeds | `Authentication` with `OidcUser` | Identity authenticated by OP and accepted by Spring Security |
| Post-login | `SecurityContext` | Security context saved/restored across requests |
| When calling APIs | `OAuth2AuthorizedClient` | Tokens issued to client/principal in context |

Do not assume that because these states can involve the session, they live in the same attribute or share the same lifecycle.

## 6. Which Object Is the Principal After OIDC Login?

### 6.1. `OAuth2AuthenticationToken` and `OidcUser`

When OIDC Login succeeds in a Servlet application, `Authentication` typically has type:

~~~java
org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken
~~~

Its principal is typically an implementation of:

~~~java
org.springframework.security.oauth2.core.oidc.user.OidcUser
~~~

Object relationship example:

~~~text
SecurityContext
└── OAuth2AuthenticationToken
    ├── principal: OidcUser
    │   ├── idToken: OidcIdToken
    │   ├── userInfo: OidcUserInfo (if present)
    │   └── claims, attributes
    ├── authorities: Collection<GrantedAuthority>
    ├── authorizedClientRegistrationId: corporate
    └── authenticated: true
~~~

`OidcUser` inherits `OAuth2User` capabilities and provides OIDC methods such as:

| Method | Information |
|---|---|
| `getIdToken()` | Processed `OidcIdToken` object |
| `getUserInfo()` | `OidcUserInfo` object if returned by provider and flow |
| `getClaims()` | OIDC claims exposed by Spring Security on the principal |
| `getSubject()` | Subject (`sub`) per OIDC identity |
| `getIssuer()` or `getIdToken().getIssuer()` | Issuer of the ID token, depending on API used |
| `getEmail()` | Email claim if present |
| `getFullName()` | Name claim if present |
| `getAuthorities()` | Authorities mapped for the principal |

Claims like `email`, `name`, `picture`, and other profile attributes **may be absent** or vary by provider/scope/policy. Never use display name as an account identifier key.

### 6.2. Stable identity: `iss` combined with `sub`

OIDC provides two especially important claims:

- `iss`: issuer that issued the ID token.
- `sub`: End-User identifier scoped to that issuer.

If an application supports multiple providers, two different people may have the same `sub` string across two issuers. Therefore, an internal account-linking key typically relies on the **`iss` + `sub` pair**.

Example:

~~~text
Issuer A: https://id.example.com/realms/employees
Subject:  10042

Issuer B: https://id.example.com/realms/partners
Subject:  10042
~~~

These are not automatically the same person. Conversely, the same person may receive different `sub` values across clients when an OP uses pairwise subject identifiers.

OIDC login data proves identity at a trusted OP; **it does not automatically prove the user is authorized to approve every transaction in the Portal**.

### 6.3. OIDC principal vs. pure OAuth 2.0 principal

Not every OAuth 2.0 Login produces an `OidcUser`:

| Scenario | Typical principal |
|---|---|
| OIDC login with `openid` and valid ID token | `OidcUser` |
| OAuth 2.0 Login without OIDC | `OAuth2User` or corresponding implementation |
| Form Login managed by Spring Security | `UserDetails`, username string, or configured principal |
| JWT Resource Server receiving bearer tokens | `Jwt`/`JwtAuthenticationToken` per JWT mechanism |
| Custom authentication | Principal defined by the application's AuthenticationProvider |

Accordingly, a controller taking `@AuthenticationPrincipal OidcUser` is only suitable if that route is protected by OIDC Login or has clear rules for other login methods.

## 7. Reading the Principal Properly in Spring MVC

### 7.1. Getting `OidcUser` with `@AuthenticationPrincipal`

Suppose the application only allows `/me` access after a successful OIDC Login:

~~~java
import java.util.List;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {

    @GetMapping("/me")
    CurrentUserResponse me(
            @AuthenticationPrincipal OidcUser user,
            Authentication authentication) {

        String registrationId =
                authentication instanceof OAuth2AuthenticationToken oauth
                        ? oauth.getAuthorizedClientRegistrationId()
                        : null;

        List<String> authorities = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .toList();

        return new CurrentUserResponse(
                user.getIdToken().getIssuer().toString(),
                user.getIdToken().getSubject(),
                user.getFullName(),
                registrationId,
                authorities
        );
    }

    record CurrentUserResponse(
            String issuer,
            String subject,
            String displayName,
            String registrationId,
            List<String> authorities) {}
}
~~~

Explanation:

1. `@AuthenticationPrincipal` extracts the principal from the current `Authentication` in `SecurityContext`.
2. For OIDC Login, the principal is `OidcUser`, allowing access to issuer and subject.
3. The `Authentication` parameter lets you inspect authorities and login metadata.
4. `getAuthorizedClientRegistrationId()` identifies which client registration was used to log in.
5. `displayName` may be `null` if the OP did not supply a name claim.

This endpoint returns illustrative data only. In real systems, minimize personal data returned externally and never send raw ID tokens, access tokens, or refresh tokens to the browser.

**Important assumption of the example:** `/me` is accessed exclusively via OIDC Login. If the system also permits Form Login, HTTP Basic, or bearer tokens on the same endpoint, handle non-`OidcUser` principals instead of assuming the cast.

### 7.2. Getting `Authentication` directly

Spring MVC can inject the active `Authentication` as a method parameter:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SecurityStatusController {

    @GetMapping("/who-am-i")
    public String whoAmI(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

For an endpoint requiring authentication, this example reads the principal's name. **`authentication.getName()` does not necessarily equal an email**; it depends on the implementation and configured name attribute. For OIDC, if a durable identifier key is needed, take `iss` + `sub` from the verified OIDC token.

### 7.3. Reading `SecurityContext` via `SecurityContextHolder`

Inside a service executing on the same request thread:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

public class CurrentAuthenticationLookup {

    public Authentication currentAuthentication() {
        return SecurityContextHolder.getContext().getAuthentication();
    }
}
~~~

This is useful where principal injection is unavailable, though it introduces coupling to the ambient security context. For easily testable business logic, passing the user identifier or `Authentication` explicitly from the web/service layer is often cleaner.

Never store an `Authentication` in a `static` field or shared cache for reuse across requests. Doing so risks leaking identities and permissions across users.

### 7.4. Reading `HttpSession` only when genuinely needed

In the Servlet API:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LocalSessionController {

    @GetMapping("/session-present")
    public SessionState sessionState(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        return new SessionState(session != null);
    }

    record SessionState(boolean sessionPresent) {}
}
~~~

`request.getSession(false)` returns `null` if no session exists, unlike `request.getSession()`, which can create a new session.

This endpoint merely illustrates session presence. **Having an `HttpSession` does not by itself prove the user is authenticated**, as a session can exist prior to login to hold an authorization request, CSRF token, request cache, or other application data.

Do not read the session directly to decide access permissions; Spring Security authorization evaluates `Authentication` in the filter chain.

## 8. Configuring Servlet OIDC Login and Sessions in Spring Security

### 8.1. Adding dependencies and registration

With Spring Boot Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

An illustrative OIDC client configuration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corporate-oidc:
            issuer-uri: https://id.example.com/realms/employees
~~~

`corporate` is the registration ID used in `/oauth2/authorization/corporate`. `issuer-uri` is the trusted OP identifier Spring uses to fetch provider metadata via discovery.

This configuration assumes the client is already registered at the OP; `client-secret` is loaded from environment secret management, never hardcoded in source control.

### 8.2. Enabling OIDC login and sessions when needed

Example Servlet Security Filter Chain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PortalSecurityConfiguration {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(requests -> requests
                        .requestMatchers("/", "/error", "/assets/**").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
                .logout(logout -> logout.logoutSuccessUrl("/"))
                .build();
    }
}
~~~

Meaning:

- `authorizeHttpRequests(...)` requires authentication for protected URLs.
- `oauth2Login()` enables the OAuth 2.0/OIDC login flow and callback handling.
- `SessionCreationPolicy.IF_REQUIRED` allows creating a session when the flow needs to persist state.
- `logout(...)` uses Spring Security's local logout mechanism; it does not terminate the OP session by default.

After successful login, the app typically stores `SecurityContext` in an `HttpSession`-backed persistence mechanism so subsequent requests restore `Authentication`.

Do not write a controller for `/login/oauth2/code/corporate` when using Spring Security's default callback. The framework provides a dedicated filter for token exchange, verifying the login result, and establishing `Authentication`.

### 8.3. Configuring session timeout and cookies

Example Spring Boot configuration for an HTTPS environment:

~~~yaml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        http-only: true
        secure: true
        same-site: lax
~~~

Key points:

- `timeout` sets session inactivity expiration per Servlet/Spring Boot config; it is not the `exp` of the ID token or access token.
- `HttpOnly` prevents ordinary JavaScript from reading the session cookie; it does not eliminate all XSS or CSRF risks on its own.
- `Secure` instructs browsers to send the cookie over HTTPS only.
- `SameSite=Lax` works well with many top-level GET login redirect flows, though actual redirects, browsers, and flows should be evaluated.
- Behind a reverse proxy, the application must recognize the public scheme/host via trusted proxy configuration.

In local HTTP-only environments, `secure: true` may prevent browsers from sending the cookie as expected; configure per environment rather than weakening production settings to fix local errors.

### 8.4. Keeping CSRF protection enabled for cookie-based interactions

Because browsers automatically attach session cookies, state-changing requests are vulnerable to CSRF unless protected. Spring Security enables CSRF protection by default for unsafe HTTP methods in typical Servlet setups.

Points to remember:

- Do not disable CSRF globally just because you use OIDC.
- `state` in the authorization flow binds the callback to the initiated request; it does not replace CSRF protection for business forms/actions.
- With default CSRF logout protection, logout usually requires a **POST with a CSRF token**; do not place a plain GET link to `/logout` expecting it to log out immediately.

## 9. `OAuth2AuthorizedClient` and Tokens: Do Not Confuse with the Session Principal

### 9.1. Who holds the access token after login?

During Authorization Code flow, the OP may return:

- **ID token**: lets the RP authenticate the End-User.
- **Access token**: used to call authorized Resource Servers/APIs.
- **Refresh token**: optionally issued per grant, scopes, and OP policy.

Spring Security manages authorized client data using:

~~~java
org.springframework.security.oauth2.client.OAuth2AuthorizedClient
~~~

This object binds a `ClientRegistration` to the authorized principal/context along with the access token and optional refresh token.

This is **OAuth authorized client state**, distinct from `OidcUser` or `SecurityContext`.

### 9.2. Two stores with different responsibilities

| Mechanism | Primary data | Purpose |
|---|---|---|
| `SecurityContextRepository` | `SecurityContext`, `Authentication` | Restore login identity/state |
| `OAuth2AuthorizedClientRepository` | `OAuth2AuthorizedClient` per request/principal context | Manage authorized clients for HTTP requests |
| `OAuth2AuthorizedClientService` | Authorized clients by registration/principal | Save, look up, and remove tokens via service abstraction |

Authorized clients may be stored in the session or another store depending on Spring Security config. **Do not assume the access token is stored in the `SPRING_SECURITY_CONTEXT` attribute.** Having an `Authentication` in the session also does not guarantee the access token is still valid for every API.

### 9.3. Inspecting authorized client state

Example endpoint checking whether an access token exists for the used registration:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OAuthClientStatusController {

    @GetMapping("/authorized-client-status")
    String status(
            @RegisteredOAuth2AuthorizedClient("corporate")
            OAuth2AuthorizedClient client) {

        return "registrationId=" + client.getClientRegistration().getRegistrationId()
                + ", tokenPresent=" + (client.getAccessToken() != null);
    }
}
~~~

This example assumes an authorized client is stored and resolved successfully. In production systems, handle missing authorized clients appropriately and never expose token values in API responses or logs.

To call another API, the client uses an access token matching the API's **audience/scope**; the Resource Server independently validates tokens and enforces authorization. Never send an ID token to an API in place of an access token.

### 9.4. Session loss and token expiration are separate events

Suppose a user has logged in:

- `HttpSession` has 20 minutes remaining before inactivity timeout.
- The ID token has its own expiration time.
- The access token may expire earlier than the session and require refreshing or re-acquisition per policy.
- The OP may keep an SSO session alive longer than the Portal's session.

Consequently:

- An **active session** does not guarantee the access token is still usable.
- An **active access token** does not mean the local login session has not been logged out.
- An **expired ID token** does not automatically destroy `HttpSession` immediately in typical session-based configs.
- **Logging out of the Portal** does not necessarily revoke all issued access tokens or end SSO at the OP.

Design application session policy, token lifecycle, token revocation, and OIDC logout separately when business rules require them.

## 10. Distinguishing the Portal Session from the OP SSO Session

### 10.1. Two sessions with different owners

The **Portal session** is usually `HttpSession` on the application side, identifying the user across requests to the Portal.

The **OP/SSO session** is managed by the OpenID Provider and determines whether the browser must re-authenticate when initiating a new OIDC Authorization Request.

Example:

~~~text
10:00  User logs into OP and Portal
10:30  Portal HttpSession expires
10:31  User visits /profile; Portal starts a new OIDC Login
10:31  OP still has an SSO session and may return a result without prompting for password
10:31  Portal creates a new login session
~~~

The user may experience "still being logged in" thanks to SSO, even though the Portal created a **new session**.

### 10.2. Local logout

With Spring Security Servlet, standard logout typically:

1. Invalidates the local session per configuration.
2. Clears `Authentication` and `SecurityContext`.
3. Redirects the user to the logout success URL.

However, the browser may still hold a valid SSO session at the OP. When revisiting a protected page, the Portal can redirect to the OP and the user is swiftly logged back in via SSO.

To terminate the session at the OP, use an OIDC logout mechanism supported by the provider, such as **RP-Initiated Logout**. This is an extra flow requiring explicit configuration; do not expect local logout alone to sign out of the OP and all other clients.

### 10.3. Switching OIDC accounts

If the Portal supports multiple accounts:

- Do not treat email in `login_hint` as proof of the new account.
- Upon returning from the OP, verify the ID token and read the actual `iss` + `sub`.
- Replace local login state cleanly, without carrying over business session/request data from the old account.
- Never reuse the old principal's `OAuth2AuthorizedClient` or access token for the new account.
- You may prompt the OP for account selection with `prompt=select_account` if supported; still verify identity after the callback.

**Session isolation** is critical when one browser uses multiple accounts on the same Portal.

## 11. Session Fixation and Session Protection

### 11.1. What is session fixation?

Session fixation occurs when an attacker tricks a victim into logging in with a session identifier already known to or controlled by the attacker.

Once a user logs in successfully, the application should rotate the session identifier or apply an equivalent safeguard so a pre-authentication session cannot be reused with elevated privileges.

Spring Security Servlet provides **session fixation protection**; on supporting Servlet containers, the default strategy typically rotates the session ID (`changeSessionId`).

Diagram:

~~~text
Before login:
session ID = abc123     (session may hold the authorization request)

After successful login:
session ID = xyz789     (session identifier rotated)
SecurityContext = authenticated Authentication
~~~

Values are illustrative only. Applications should not invent custom session ID rotation algorithms when using standard Spring Security and a Servlet container.

### 11.2. Cookies and HTTPS

Session protection includes:

- Using HTTPS for the application and OIDC callback.
- Enabling cookie attributes such as `HttpOnly` and `Secure` in production where appropriate.
- Evaluating `SameSite` against actual cross-site redirect flows.
- Keeping session IDs out of URLs, logs, and response bodies.
- Setting reasonable inactivity timeouts; providing expiration/revocation mechanisms where needed.
- Avoiding storing unnecessary secrets in `HttpSession`.
- When sharing sessions across instances, securing the session store and inter-service access.

`HttpOnly` does not stop browsers from automatically sending cookies with requests, so session-based apps still need proper CSRF protection.

### 11.3. Logging in does not grant permission for every action

For example, a portal has:

- `/profile`: any logged-in employee can view their own profile.
- `/orders/123/approve`: only designated reviewers or users with the right authority can approve orders.
- `/admin/users`: restricted to administrators.

Having a valid `OidcUser` and `Authentication.isAuthenticated() == true` only proves authentication state. **Authorization** must still be enforced by Spring Security and business rules.

Authorities may come from scopes or claim mapping depending on provider and configuration. Spring Security **does not automatically treat arbitrary custom OP claims as application business roles**.

## 12. Comparing Session-Based Web Apps and Stateless APIs

One architecture may host both:

- **Web UI** using OIDC Login and `HttpSession`.
- **REST API** accepting `Authorization: Bearer <access_token>` and authenticating per request.

The two flows differ in how `Authentication` is created:

| Feature | Web OIDC Login (Servlet session-based) | Bearer-token Resource Server (commonly stateless) |
|---|---|---|
| Source of state | Session cookie and restored `SecurityContext` | Bearer token sent in request |
| Authentication start | Browser redirect to OP | Client/API caller already holds a token |
| Typical principal | `OidcUser` | `Jwt`/`JwtAuthenticationToken` or equivalent principal |
| Login persistence | Can use `HttpSession` | Typically validates token on every request |
| Client ID and redirect URI | Required for OIDC Login | Not required just to accept pure JWTs |
| CSRF | Essential when browsers send session cookies automatically | Evaluated based on whether the API uses automatic credentials/cookies |

You can separate both endpoint groups with **multiple `SecurityFilterChain`s** if a project serves both UI and APIs. Each chain needs appropriate matchers and authentication/session settings; do not apply `STATELESS` globally if web OIDC Login still requires sessions.

### 12.1. Illustrative configuration separating API and Web

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SeparateChainsSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .csrf(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .oauth2ResourceServer(resource -> resource
                        .jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error", "/assets/**").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
                .build();
    }
}
~~~

This is an **architectural example**, requiring `spring-boot-starter-oauth2-resource-server` and matching JWT Resource Server configuration to run `/api/**`. Disabling CSRF on the API chain as shown is only appropriate when the API strictly uses header-based bearer tokens and not cookies or automatic browser credentials.

The web chain keeps standard CSRF protection; OIDC Login can rely on sessions. If the API is also accessed via cookies, evaluate CSRF separately instead of copying `disable()`.

## 13. Request Threads vs. Asynchronous Work

### 13.1. `SecurityContextHolder` does not automatically follow every thread

Suppose a controller has `OidcUser` and launches a task on an executor:

~~~text
Request thread:
SecurityContextHolder -> Alice

Worker thread:
SecurityContextHolder -> does not automatically have Alice
~~~

Because `SecurityContextHolder` defaults to ThreadLocal, spawning threads manually or running callbacks on another executor **does not automatically copy the context**.

Spring Security provides utilities such as:

- `DelegatingSecurityContextRunnable`.
- `DelegatingSecurityContextCallable`.
- `DelegatingSecurityContextExecutor`.
- Corresponding async integrations depending on environment.

If background work must act on behalf of a user, clearly define the task's identity and permissions. Often it is better to pass the **user ID and needed business data** into the job rather than keeping an entire `SecurityContext` alive beyond the request.

### 13.2. Do not use `MODE_INHERITABLETHREADLOCAL` as a general solution

Inheritable ThreadLocal can pass context to child threads in simple cases, but thread pools reuse workers in complex ways; uncontrolled context propagation risks mixing user identities. Use supported integration wrappers with clear lifecycles when preserving `SecurityContext` is truly required.

## 14. Common Real-World Pitfalls

| Symptom | Likely cause | What to check |
|---|---|---|
| After successful OIDC callback, next request redirects to login again | Session/cookie not maintained; stateless config; `SecurityContext` not saved | Check cookies, session policy, repository, reverse proxy, and redirect logs |
| Controller `@AuthenticationPrincipal OidcUser` receives `null` | Request unauthenticated, different principal type, or endpoint does not use OIDC Login | Inspect `SecurityFilterChain`, `Authentication`, and actual login method |
| `authentication.getName()` differs from email | Username attribute / principal representation is not email | Use `iss` + `sub` for account linking |
| Session exists without a valid `Authentication` | Session created prior to login or context was cleared | Never treat `session != null` as proof of login |
| Reloading the page stays logged in even though token is old | `HttpSession` and tokens have independent lifecycles | Check session timeout, authorized client mechanics, and freshness policy |
| After logout, reopening the page logs right back in | OP still holds an SSO session | Distinguish local logout from OIDC RP-Initiated Logout |
| Two accounts get mixed data | Session/token/authorized client shared across wrong principals | Check `iss` + `sub` keys, cache keys, and account switching |
| Access token expired, yet UI stays logged in | `SecurityContext` still active; authorized client/token has separate state | Check token expiry/refresh and API requirements |
| After custom authentication, next request loses login | Context placed in Holder without saving via configured repository | Check `SecurityContextRepository` and Spring Security 6 persistence strategy |
| Login works intermittently across multiple server nodes | Sessions not shared or cookies/routing inconsistent | Check session store, sticky routing if needed, encryption/serialization, and cookies |
| Async task sees empty principal | Context is bound to request thread | Use `SecurityContext` propagation wrappers or pass safe business data |
| Bearer API returns 302 redirect to OP | API matcher hit the web login chain | Separate the API Resource Server chain from the web session chain |

### 14.1. Observing requests without leaking secrets

When troubleshooting, inspect:

- Which chain the request entered and how it is protected.
- Whether `Authentication` exists; the `Authentication`/principal types.
- Which `registrationId` was used to log in.
- Whether a valid session is sent by the browser.
- Session timeout, cookie attributes, and configured policy.
- Differences between public URLs and internal URLs behind a proxy.

**Never log** session IDs, cookies, authorization codes, client secrets, ID tokens, access tokens, or refresh tokens. If correlation across events is needed for investigation, use a separate non-credential correlation ID.

### 14.2. When customizing login or AuthenticationProvider

With framework-provided login flows, Spring Security handles context persistence and session protection. However, if an application constructs an `Authentication` manually and places it in `SecurityContextHolder`, that **does not guarantee** the context persists to the next request.

In Spring Security 6, explicit persistence may require calling `SecurityContextRepository.saveContext(context, request, response)` on the configured repository. Session fixation protection and corresponding authentication checks must also be applied.

Instead of reimplementing the OIDC callback manually, prefer `oauth2Login()` and Spring Security extension points such as authorization request resolvers, OIDC user services, or authentication success handlers to keep the flow consistent.

## 15. Scenario Questions

### Scenario A: identifying the user in a controller

**Requirement:** after OIDC Login, the profile page needs a stable identifier to query internal data.

**Approach:** obtain `OidcUser` via `@AuthenticationPrincipal`, read `iss` and `sub` from the ID token already verified by Spring Security, and map that pair to the internal account. Name/email can be displayed, but should not be the sole identity key.

### Scenario B: user is logged in, yet the API returns 401

**Requirement:** Portal shows the user is logged in, but calling the Inventory API with an access token returns 401.

**Approach:** check `OAuth2AuthorizedClient`, access token expiration, refresh capability, issuer/audience/scopes accepted by the API, and how the bearer token is attached. **Do not clear `SecurityContext` by default** just because an external API rejected a token; the two states have separate lifecycles and rules.

### Scenario C: wanting stateless APIs alongside session-based web UI

**Requirement:** `/api/**` accepts bearer JWTs, while `/dashboard` logs in via OIDC.

**Approach:** configure `SecurityFilterChain` beans with appropriate request matchers. The API chain validates bearer tokens with stateless policy where architecturally sound; the web chain uses OIDC Login and sessions. Prevent API requests from redirecting to the OP when missing a token.

### Scenario D: logging out, yet the user gets right back in without a password

**Requirement:** after clicking logout in the Portal, the user returns to `/dashboard` and is quickly logged in again.

**Approach:** verify the application session was properly cleared. If so, an SSO session likely remains active at the OP. When business rules require system-wide logout, integrate OIDC logout per provider support instead of confusing local logout with OP logout.

## 16. Self-Check Questions

**Question 1.** `SecurityContextHolder` defaults to storing context in a ThreadLocal. How does the next request still know the user is logged in?

**Answer:** Spring Security restores `SecurityContext` from the configured `SecurityContextRepository`, typically backed by `HttpSession` in session-based web login. ThreadLocal only provides context for the current request thread.

**Question 2.** Does having a session cookie mean the user is authenticated?

**Answer:** No. A session can exist before login to store an authorization request, request cache, or other data. Authentication depends on `SecurityContext`'s `Authentication` and authorization policies.

**Question 3.** With OIDC Login, what is the principal typically?

**Answer:** `OidcUser`, usually inside an `OAuth2AuthenticationToken`. The user is reliably identified by issuer and subject from the verified ID token.

**Question 4.** If `OidcUser` is present, is the API access token always inside `SecurityContext`?

**Answer:** Do not assume that. Tokens are managed through `OAuth2AuthorizedClient` and authorized client repositories/services; storage depends on configuration.

**Question 5.** Does the Portal session expiring mean the SSO session at the OP also expired?

**Answer:** No. They are two separate sessions managed by two systems. Returning to the Portal can trigger a new login flow where the OP still recognizes the user via SSO.

**Question 6.** Should `SessionCreationPolicy.STATELESS` be applied to the same chain running default OIDC Authorization Code Login?

**Answer:** Do not change it blindly. The redirect flow needs state and callback tracking, and web login generally relies on sessions after authentication. A stateless design requires a matching architecture and repositories.

**Question 7.** Why shouldn't `SecurityContextHolder` be used directly inside a thread pool to assume the original request's principal?

**Answer:** Default context is bound to the request thread. Worker threads do not automatically receive it, and thread pools reuse threads. Use supported context propagation wrappers or pass safe business data explicitly.

**Question 8.** A controller sees the user is logged in via `Authentication.isAuthenticated()`. Is that enough to allow approving any order?

**Answer:** No. Resource access permissions and business rules must still be enforced. Authentication and authorization are separate responsibilities.

## Key Takeaways

- **`SecurityContext` holds `Authentication`; `Authentication` holds the principal and authorities.** After OIDC Login, the principal is typically `OidcUser` inside `OAuth2AuthenticationToken`.
- **`SecurityContextHolder` provides context on the request thread**, while `SecurityContextRepository` saves/restores context across requests; in typical Servlet web login, this relies on **`HttpSession`**.
- **`HttpSession` is the application session**, distinct from the OP's SSO session, ID token expiration, and access token lifecycle.
- **`OidcUser` represents an OIDC-authenticated user**; when linking accounts, prefer **`iss` + `sub`** over name or email.
- **`OAuth2AuthorizedClient` manages issued tokens** for API calls and is separate from `SecurityContext`.
- For systems combining web login and bearer APIs, configure filter chains, session policies, and security protections per request type.
