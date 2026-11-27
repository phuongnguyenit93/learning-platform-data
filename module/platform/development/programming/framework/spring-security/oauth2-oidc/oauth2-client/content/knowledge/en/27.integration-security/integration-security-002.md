# 27.2. CSRF at the Authorization Endpoint, Callback, and Logout

## 1. The Problem: If You Have OAuth2 Login, Do You Still Need CSRF?

A Spring Security application lets users log in with OpenID Connect (OIDC). The developer sees that the OAuth2 flow already has a <code>state</code> parameter, so they decide:

~~~java
http.csrf(csrf -> csrf.disable());
~~~

Application login still works. However, a user already logged in with a **session cookie** can be tricked by an external website into sending a state-changing request to the application, for example:

~~~html
<form action="https://portal.example.org/account/change-email"
      method="post">
    <input name="email" value="attacker@example.org">
</form>
<script>document.forms[0].submit();</script>
~~~

If the browser automatically attaches the authentication cookie for <code>portal.example.org</code> and the endpoint does not check CSRF, the server may process the request as if the user intentionally changed their email. Having <code>state</code> in OIDC Login **does not** protect the <code>/account/change-email</code> endpoint.

On the other hand, if Spring Security's CSRF protection is mechanically enabled for **every POST**, the application may fail on an OIDC callback using <code>response_mode=form_post</code> or an endpoint receiving **Back-Channel Logout** from an OpenID Provider (OP), because those requests do not come from a regular browser form carrying the portal's CSRF token.

Therefore, the real problem is **identifying the right CSRF model for each point in the protocol**:

1. **Authorization initiation and Authorization Endpoint:** How do users start OAuth2 login, who controls the authorization request, and how does the OP's CSRF differ from the Client's CSRF?
2. **Callback:** How do we know an authorization response truly comes from an authorization request that the browser initiated?
3. **Logout:** Can a browser be forced to terminate someone else's session via cross-site GET/POST, and how is Back-Channel Logout from the OP authenticated?
4. **Post-login business actions:** Do cookie/session-based POST, PATCH, and DELETE requests still need a CSRF token?

> **Core principle:** Spring Security's CSRF token, OAuth2 <code>state</code>, OIDC <code>nonce</code>, and PKCE are distinct mechanisms. They complement each other, but they must never be treated as one generic protection key while ignoring their boundaries of use.

## 2. Learning Objectives

After this lesson, you will be able to:

- Explain CSRF for web applications using cookie-based authentication.
- Distinguish <code>/oauth2/authorization/{registrationId}</code> at the Client from <code>/authorize</code> (Authorization Endpoint) at the Authorization Server/OP.
- Explain the role of <code>state</code> in the OAuth2 Authorization Code Flow and callback binding conditions.
- Understand how <code>nonce</code>, PKCE, <code>iss</code>, and ID Token validation complement <code>state</code>.
- Configure CSRF for business endpoints in **Spring Security Servlet** and **Reactive WebFlux**.
- Handle <code>response_mode=form_post</code> callbacks when supported by the framework/provider using a **narrow** exception without disabling CSRF globally.
- Implement logout via POST with CSRF protection; understand the differences among OIDC RP-Initiated, Front-Channel, and Back-Channel Logout.
- Handle <code>SameSite</code>, <code>Secure</code>, proxies, session affinity, multiple tabs, and multiple providers.
- Diagnose HTTP 403 errors by their true cause; avoid confusing CSRF failures with missing roles/scopes or bearer token errors.
- Write CSRF/logout/callback tests and design defenses suitable for scaling out.

## 3. CSRF Threat Model

### 3.1. What Is Cross-Site Request Forgery?

**CSRF** occurs when an attacker causes the browser of a user who already has an authenticated relationship with an application to send a request to that application, where the request **does not reflect the user's legitimate intent**.

Browsers can automatically send credentials associated with the destination, especially:

- Session cookies.
- HTTP authentication caches in certain mechanisms.
- Client certificates automatically selected per browser/mTLS configuration.
- Other credentials automatically attached by the browser without JavaScript on a third-party site needing to read them.

Example:

~~~mermaid
sequenceDiagram
    autonumber
    actor User
    participant Browser
    participant Evil as Site attacker.example
    participant Portal as portal.example.org

    User->>Browser: Log in to Portal via OIDC
    Portal-->>Browser: Session cookie
    User->>Browser: Open attacker.example
    Evil-->>Browser: Auto-submitting HTML form to Portal
    Browser->>Portal: POST /account/change-email with cookie if browser allows
    Note over Portal: If trusting only the cookie without CSRF check, the request may succeed
    Portal-->>Browser: Response
~~~

An attacker **does not need to know the password or session cookie value** to attempt CSRF; they just need a way to make the browser send credentials it already holds.

### 3.2. Same-Origin Policy Does Not Prevent CSRF by Itself

The Same-Origin Policy primarily restricts scripts from another origin from **reading** response contents or interacting with unauthorized DOMs. It does not block all cross-origin requests: HTML forms, navigations, and certain fetch types can still issue requests under browser rules.

**CORS does not replace CSRF protection either.** CORS controls whether scripts may read responses and certain cross-origin requests. A cross-site HTML form can issue a POST even when reading the response is disallowed.

### 3.3. Conditions for CSRF to Have Impact

A forged request is dangerous when these combine:

1. The browser automatically sends a valid credential to the target server.
2. The server uses that credential to authenticate the request.
3. The request mutates state or performs a sensitive action.
4. The server lacks reliable proof that the request originated from a legitimate user flow.

Not every cross-site GET is an impactful CSRF. However, if the server uses **GET to mutate data**, a link/image/redirect can become an attack vector.

### 3.4. Distinguishing CSRF from XSS

CSRF does not require the attacker to execute JavaScript in Portal's origin. XSS, if present, can let an attacker read the CSRF token or issue requests with the page's full privileges, rendering CSRF defenses ineffective. Thus, CSRF tokens **do not replace** output encoding, CSP, input validation, and XSS mitigations.

## 4. Four Protection Boundaries in an OIDC Login

Consider the system:

~~~text
Browser
  |
  v
Spring Security Portal (OAuth2/OIDC Client)
  |
  | authorization request, code exchange, logout
  v
OpenID Provider / Authorization Server
  |
  | access token
  v
Resource Server / Business API
~~~

We must distinguish the endpoints:

| Endpoint | Owner | Typical request | Primary protection mechanism |
|---|---|---|---|
| <code>/oauth2/authorization/company</code> | Spring Security **Client** | Browser GET starting login | Registration allowlist, server-generated authorization request, state/correlation |
| OP's <code>/authorize</code> | **Authorization Server** | Browser GET, login/consent interaction | OP session/login CSRF, redirect URI, PKCE, authorization policy |
| <code>/login/oauth2/code/company</code> | Spring Security **Client** | Browser GET callback code/state | Verifying state bound to authorization request, PKCE, issuer, ID Token validation |
| <code>/login/oauth2/code/company</code> with form_post | Spring Security **Client** | Browser cross-site POST callback | OIDC/OAuth state + narrow CSRF handling + session correlation |
| <code>/logout</code> | Spring Security **Client** | Browser POST | Spring Security CSRF token, logout handlers |
| <code>end_session_endpoint</code> | **OP** | Browser redirect/POST per profile | OIDC RP-Initiated Logout, ID Token hint/OP policy/state |
| <code>/logout/connect/back-channel/company</code> | Spring Security **Client** | OP server-to-server POST | Signed Logout Token validation, issuer/audience/events/sid/sub |
| <code>/api/orders</code> | **Client/API** | Cookie/session-authenticated POST | CSRF token or equivalent anti-CSRF mechanism |

A common mistake is lumping all of these together as "OAuth endpoints" and disabling CSRF with:

~~~java
.csrf(csrf -> csrf.ignoringRequestMatchers("/oauth2/**", "/login/**", "/logout/**"))
~~~

Such a broad exception can leave application-defined state-changing routes under those prefixes unprotected. Instead, you need to understand the **exact method, path, and authentication protocol** of each endpoint.

## 5. Authorization Initiation at the Spring Security Client

### 5.1. URL Selecting the ClientRegistration

In Servlet or Reactive WebFlux, Spring Security OAuth2 Login typically exposes an authorization initiation URL:

~~~text
GET /oauth2/authorization/company
~~~

An illustrative configuration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: portal-web
            client-secret: ${COMPANY_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

Spring Security:

1. Finds the <code>ClientRegistration</code> with ID <code>company</code>.
2. Creates an <code>OAuth2AuthorizationRequest</code>.
3. Generates a random <code>state</code>, along with nonce/PKCE when applicable.
4. Saves the request/correlation in a repository bound to the session.
5. Redirects the browser to the OP's Authorization Endpoint.

This is the **Client's authorization initiation endpoint**, not the Token Endpoint and not the Authorization Endpoint implemented by the OP.

### 5.2. Does GET Initiation Need a CSRF Token?

By default design, <code>GET /oauth2/authorization/company</code> is a navigation that initiates an authorization flow. The Spring Security CSRF filter normally does not require a synchronizer CSRF token for HTTP methods considered safe, such as GET.

Nevertheless, GET initiation can create authorization-request state in the session. An external site might try to **force the browser to navigate** to this URL. Therefore, login initiation needs appropriate safeguards:

- Accept only configured registration IDs.
- Generate authorization requests/state on the server; never take state from the caller.
- Bind the callback to the browser session and original request.
- Verify issuer/client/redirect URI.
- Do not treat an attacker-supplied initiation URL as proof that the user intentionally consented to link an account or switch active identity.

**This does not mean every GET initiation link must be protected by a form-style CSRF token.** If the application has sensitive actions like "switch account," "link identity," or "grant new permissions," add a CSRF-protected POST step and intent confirmation **before** redirecting to the standard initiation URL.

### 5.3. Login CSRF at Initiation Differs from Business CSRF

For instance, an attacker tries to push a user's browser into a login flow that ends up creating a session under the attacker's account. That is **login CSRF/session swapping**. In OAuth2, <code>state</code> generated in the Client session and verified at the callback is an essential line of defense.

Conversely, a POST updating an email in the Portal after login requires the application's CSRF token. **OAuth state must not be attached to business POSTs as a general-purpose CSRF token**.

### 5.4. Do Not Let the Browser Override the Provider Endpoint

Wrong:

~~~text
GET /oauth2/authorization?issuer=https://unknown.example
~~~

if the application takes the issuer URL directly from a query parameter and creates a registration dynamically. An attacker could steer authorization to an untrusted OP or cause SSRF/mix-up.

Better to select from:

~~~text
/oauth2/authorization/company
/oauth2/authorization/partner
~~~

in a backend allowlist. With multiple providers, state must bind the authorization response to the **exact registration/issuer**.

## 6. CSRF at the OP's Authorization Endpoint

The actual Authorization Endpoint lives on the **Authorization Server/OpenID Provider**, for example:

~~~text
https://idp.example.org/realms/company/protocol/openid-connect/auth
~~~

A normal Client application **does not manage** the CSRF token on the OP's login form. The OP is responsible for protecting:

- Login pages and credential submission.
- Consent approval/rejection.
- SSO session management.
- Authentication method selection and step-up/MFA.
- Any state-changing actions occurring within the OP's origin.

### 6.1. The Authorization Endpoint Is the OP's Security Boundary

A conceptual request:

~~~http
GET /authorize?response_type=code&client_id=portal-web&redirect_uri=https%3A%2F%2Fportal.example.org%2Flogin%2Foauth2%2Fcode%2Fcompany&scope=openid%20profile&state=RANDOM_STATE HTTP/1.1
Host: idp.example.org
~~~

The OP must validate Client registration, allowed redirect URIs, response type, scope, user authentication, and consent policy. When the OP displays a POST consent form, the OP must protect that form under the **OP's** CSRF model.

### 6.2. Do Not Confuse OAuth State with the OP's CSRF Token

<code>state</code> is typically data sent by the Client and expected back intact in the authorization response to correlate the callback. It is **not** the OP's synchronizer token protecting the "Approve access" form.

If you are also developing the Authorization Server, you need a separate CSRF design for the Authorization Server's state-changing endpoints. Never expect Spring Security OAuth2 Client configuration on the Portal to automatically protect the consent form on the OP.

### 6.3. Exact Redirect URI Matching

If the OP allows arbitrary redirect URIs or overly broad matching, authorization codes can be redirected to an attacker. For the Authorization Code Flow, the OP must validate the redirect URI per protocol/security profile requirements.

Do not use wildcards recklessly in callbacks:

~~~text
https://*.example.org/*
~~~

just for convenience across environments. Register explicit redirect URIs, use HTTPS, and preserve exact host/path.

### 6.4. PKCE Strengthens Code Binding

PKCE uses:

~~~text
code_verifier         temporary secret held by Client
code_challenge        derived from verifier, sent to OP
code_challenge_method S256
~~~

PKCE mitigates authorization code interception/injection; it does not by itself protect a Portal email-change POST and does not replace Client request correlation when the flow needs <code>state</code>.

Per OAuth2 security best practices, Authorization Code + PKCE is the preferred model, especially for public clients; many deployments also apply PKCE to confidential clients for defense-in-depth.

## 7. OAuth2 Callback: `state` Is the Correlation Defense

After the user authenticates, the OP redirects:

~~~http
HTTP/1.1 302 Found
Location: https://portal.example.org/login/oauth2/code/company?code=AUTH_CODE&state=RANDOM_STATE
~~~

This is normally a **GET callback**. Spring Security's default CSRF protection does not require a CSRF form token for GET, yet that does not mean the callback is "unprotected."

Spring Security OAuth2 Login must:

1. Look up the authorization request saved **before redirecting to the OP**.
2. Compare the callback's <code>state</code> against the stored state.
3. Verify the request is still associated with the right session/browser/registration.
4. Send the authorization code to the right OP's Token Endpoint with the right PKCE verifier/client authentication.
5. For OIDC, verify the ID Token, nonce if present, issuer, audience, signature, and other constraints.
6. Only after passing all steps above, create the Authentication and login session.

### 7.1. Why Is a Spring CSRF Token Not Required on a GET Callback?

A standard callback from the OP carries <code>code</code> and <code>state</code>, not the portal's synchronizer token. Expecting the browser/OP to bring a portal form CSRF token into the authorization callback does not match the protocol flow.

Because the callback is GET, the standard Spring Security CSRF filter does not block it. **The direct anti-CSRF mechanism in the OAuth2 login callback is state/correlation validation**.

This does not permit the application to skip state. If you hand-roll a callback handler like:

~~~java
@GetMapping("/oauth2/callback")
void callback(@RequestParam String code) {
    // Exchange code without checking state/session/registration!
}
~~~

then the application has stripped away a vital defense and becomes vulnerable to login CSRF, code injection, or provider mix-up.

### 7.2. Sequence Diagram

~~~mermaid
sequenceDiagram
    autonumber
    actor User
    participant B as Browser
    participant RP as Spring Security Client
    participant OP as OpenID Provider

    User->>B: Select login
    B->>RP: GET /oauth2/authorization/company
    RP->>RP: Generate state=S1; store request in session
    RP-->>B: Redirect to OP with state=S1
    B->>OP: Authorization request S1
    OP->>User: Authentication/consent per policy
    OP-->>B: 302 code=C1, state=S1
    B->>RP: GET /login/oauth2/code/company?code=C1&state=S1
    RP->>RP: Load request and verify S1
    RP->>OP: Exchange C1 (+ PKCE/client authentication)
    OP-->>RP: Token response
    RP->>RP: Validate ID Token if OIDC
    RP-->>B: Session authenticated
~~~

If the callback sends state <code>S2</code> which does not match <code>S1</code>:

~~~text
Callback S2
    → Authorization request correlation fails
    → Do not exchange code as a valid flow
    → Do not create authenticated session
~~~

### 7.3. `state` Must Have Entropy and Be Unpredictable

<code>state</code> must be generated via a cryptographically secure random mechanism, bound to the authorization request/session, and strictly verified.

Do not set:

~~~text
state=user-123
state=company
state=timestamp
~~~

in predictable ways or without binding. If the application customizes state to embed a return URL/context, it must protect integrity and prevent replay, and never put an arbitrary URL into state and redirect to it post-login without validation.

### 7.4. Authorization Request Repository

In Servlet:

~~~text
OAuth2AuthorizationRequestRepository<OAuth2AuthorizationRequest>
    ↳ HttpSessionOAuth2AuthorizationRequestRepository
~~~

In WebFlux:

~~~text
ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>
    ↳ WebSessionOAuth2ServerAuthorizationRequestRepository
~~~

The repository stores the original request for the callback to verify. In multi-instance deployments, state/correlation must be accessible on the node receiving the callback. If the cookie/session is lost, the callback must fail safely.

Never solve <code>authorization_request_not_found</code> or <code>invalid_state</code> errors by removing the state check.

## 8. OIDC `nonce` and ID Token Validation Are Not CSRF Tokens

OIDC adds <code>nonce</code> in applicable flows to bind the ID Token to the authentication request.

| Mechanism | Where it is exchanged | Purpose |
|---|---|---|
| Spring CSRF token | Form/header from app page to app | Proves a state-changing request originated from a valid browser/session context |
| OAuth2 <code>state</code> | Authorization request and authorization callback | Binds the response to the original request, preventing login CSRF |
| OIDC <code>nonce</code> | Authorization request and ID Token | Prevents ID Token replay/substitution in applicable flows |
| PKCE verifier/challenge | Authorization + Token Endpoints | Binds the authorization code to the Client that initiated the flow |
| OIDC <code>iss</code>/<code>aud</code> | ID Token / authorization response per profile | Proves the issuer and intended audience |

### 8.1. An OIDC Flow Cannot Be "Protected" by `nonce` Alone

If the callback has not been correlated with the request/session, a misused or unchecked nonce cannot stop login CSRF. Spring Security must use **all mechanisms appropriate to the flow**.

### 8.2. An ID Token Does Not Replace an Access Token

After the callback, the ID Token authenticates the End-User to the Client. It does not replace the access token used to call a Resource Server. Separate audience/scope/role checks are needed when calling downstream APIs.

Do not conflate "having a valid JWT" with "the request is safe from all CSRF." Token format is a separate concern from browser request-origin intent.

## 9. Callbacks Using `response_mode=form_post`

OIDC/OAuth deployments may use **<code>response_mode=form_post</code>**, where the OP delivers the authorization response to the Client via an auto-submitting HTML form:

~~~html
<form method="post"
      action="https://portal.example.org/login/oauth2/code/company">
    <input type="hidden" name="code" value="AUTH_CODE">
    <input type="hidden" name="state" value="STATE_VALUE">
</form>
<script>document.forms[0].submit();</script>
~~~

The browser sends a **cross-site POST** from the OP's origin to the RP's callback.

### 9.1. Conflict with the Standard CSRF Filter

Spring Security's default CSRF filter normally requires a token for POSTs. The OP **does not know the RP's CSRF token** and cannot simply inject it into the form like a same-origin page.

The result can be:

~~~text
POST /login/oauth2/code/company
    → CSRF filter rejects with 403
    → OAuth2 Login callback filter never runs
~~~

However, **not every Spring Security version/OAuth2 Login configuration automatically supports form_post callbacks just by changing the CSRF matcher**. You must verify callback processing, form body extraction, response_mode support, and OP registration for the version in use.

### 9.2. The Narrow Exception Principle

If your stack/framework supports form_post callbacks, you may need to exclude **only the POST callback path** from the synchronizer CSRF token check, while still enforcing:

- OAuth2 <code>state</code> validation.
- Correlation with the authorization request stored in the session.
- Registration/issuer binding.
- PKCE and OIDC nonce validation when applicable.
- ID Token/Token Endpoint validation for the right provider.
- Method/path restrictions and no business actions on this endpoint.

**Do not use**:

~~~java
http.csrf(csrf -> csrf.disable());
~~~

just to make a <code>form_post</code> callback work.

### 9.3. Servlet Example of a Narrow Path/Method Exception

Assuming the application **already** has a proper integration handling POST callbacks:

~~~java
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

http.csrf(csrf -> csrf.ignoringRequestMatchers(
    new AntPathRequestMatcher(
        "/login/oauth2/code/*", "POST")));
~~~

This illustrates Spring Security 6.x request matchers; the <code>AntPathRequestMatcher</code> API has changes/deprecations in newer versions. Use the matcher supported by your actual Spring Security version.

**Do not copy this snippet into production by default**:

1. Only use it when POST callbacks are a required feature and the framework handles `response_mode=form_post` securely.
2. Path/method must match the callback registration precisely.
3. Do not broaden the matcher to <code>/**</code>, <code>/login/**</code>, or all POSTs.
4. If there is a proxy/context path, verify servlet path/matcher semantics.
5. Ensure <code>state</code> and all OAuth2/OIDC validations remain enabled.

If the callback is the default GET, **do not add a POST exception** "just in case."

### 9.4. `SameSite` Cookies Can Prevent the Callback from Finding the Session

<code>SameSite=Lax</code> typically allows cookies on **top-level cross-site GET navigations**. However, on a **cross-site POST** from <code>form_post</code>, the browser may withhold the session cookie under SameSite policy.

Result:

~~~text
CSRF filter allowed the callback POST through
    ↓
Spring Security cannot find the authorization request
    ↓
state missing / authorization_request_not_found
~~~

This is no longer a synchronizer CSRF token issue; it is **session/cookie correlation**.

For browsers/flows requiring cookies on cross-site POSTs, you may need <code>SameSite=None; Secure</code> or an alternative correlation design compatible with the browser/provider. Changing SameSite impacts all cookie-based session security, so you must evaluate CSRF defenses on other routes, HTTPS, and domain/path settings.

**Never disable state validation or take state from the callback to fabricate a new authorization request** when the cookie is missing.

### 9.5. A Practical Design Decision

If there is no mandatory requirement to use <code>form_post</code>, the Authorization Code Flow with the default **GET callback** is usually simpler for browser session correlation. When <code>form_post</code> must be used, write integration tests against your exact Spring Security version and production browser/cookie policy.

## 10. Spring Security CSRF for Post-Login Business POSTs

Before discussing logout, we must maintain the right foundation:

~~~text
Cookie-authenticated browser:
    POST /orders
    PATCH /settings
    DELETE /files/{id}
    → CSRF protection must be evaluated and is normally enabled
~~~

### 10.1. Synchronizer Token Pattern

Spring Security CSRF uses a token bound to a trusted context (typically the HTTP session or a cookie repository) and requires the client to send the token in a form parameter or header.

Another attacker website cannot simply read the token from a portal page without XSS or a cross-origin vulnerability.

Example form:

~~~html
<form action="/account/change-email" method="post">
    <label for="email">New email</label>
    <input id="email" name="email" type="email" required>
    <input type="hidden" name="_csrf" value="CSRF_TOKEN_FROM_SERVER">
    <button type="submit">Save</button>
</form>
~~~

In a real template engine, the CSRF value must be generated by Spring Security (e.g., via Thymeleaf integration), not hardcoded as a literal like above.

### 10.2. A CSRF Token Does Not Imply Business Authorization

A POST with a valid CSRF token can still be rejected because:

- The user lacks the required role.
- The user does not belong to the tenant or own the resource.
- The account has been disabled.
- The access token sent to a downstream API has the wrong audience/scope.

A CSRF token defends against forged browser requests; it **does not grant business permissions**.

### 10.3. CSRF and Stateless Bearer APIs

A **truly stateless** API that only accepts Bearer tokens in the HTTP <code>Authorization</code> header—which browsers do not attach automatically—may not need a synchronizer CSRF token per the threat model.

However, if the same API also accepts **session cookies**, browser basic auth, or automatically attached credentials, you cannot claim "it's a REST API so we can disable CSRF."

The criterion is **whether credentials are automatically sent by the browser**, not whether the application is called REST, SPA, or WebFlux.

## 11. Servlet Configuration: Keep CSRF Enabled by Default

A Spring Boot 3/Spring Security 6 configuration for an OIDC Client:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PortalSecurityConfig {

    @Bean
    SecurityFilterChain portalChain(HttpSecurity http) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error", "/assets/**")
                    .permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        return http.build();
    }
}
~~~

In this configuration:

- OAuth2 Login manages authorization initiation/callback.
- The CSRF filter protects state-changing requests within the browser session by default.
- Logout follows standard configuration, typically executed via **POST** when CSRF protection is enabled.
- The OAuth2 Login GET callback still works with <code>state</code> without needing a CSRF form token.

Declaring <code>.csrf(Customizer.withDefaults())</code> is unnecessary when defaults already apply; it is written here to make intent explicit.

### 11.1. Logout Form with a CSRF Token

Thymeleaf example:

~~~html
<form th:action="@{/logout}" method="post">
    <button type="submit">Log out</button>
</form>
~~~

With Spring Security and proper template integration, the hidden CSRF field can be injected automatically. In a custom frontend, you must send the appropriate CSRF token; do not just create a GET link and assume logout is always safe.

### 11.2. Distinguishing a GET Logout Link from POST Logout

When CSRF protection is enabled, Spring Security may show a confirmation page on <code>GET /logout</code>; **POST /logout** actually executes logout per the configured flow.

If an application writes its own controller:

~~~java
@GetMapping("/logout")
public String logout() {
    invalidateSession();
    return "redirect:/";
}
~~~

then GET has a side effect. Another website can force browser navigation to log the user out, causing **logout CSRF** and session disruption.

Avoid creating a GET logout endpoint just to save a POST form.

## 12. What Is the Impact of Logout CSRF?

An attacker does not need to steal data to cause impact:

~~~html
<img src="https://portal.example.org/logout">
~~~

If <code>GET /logout</code> immediately invalidates the session, browsers visiting the attacker's site can be logged out unintentionally (depending on cookies/SameSite and implementation).

Consequences include:

- Session-level denial of service.
- Destroying unsaved work.
- Acting as an auxiliary step in login CSRF/session swapping: forcing the user to log out and steering them into an attacker-influenced login flow.
- Interrupting payment/authorization workflows.
- Causing confusion across multiple accounts or OP sessions.

**Logout must not be treated as a harmless action** simply because it does not modify business records.

### 12.1. POST + CSRF Is the Right Default for Browsers

The browser form sends:

~~~http
POST /logout HTTP/1.1
Host: portal.example.org
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=SESSION_PLACEHOLDER

_csrf=CSRF_TOKEN_PLACEHOLDER
~~~

Spring Security's CSRF filter verifies the token against the configured repository/handler; only then does the logout filter invoke the logout handlers.

### 12.2. What Does Local Logout Handle?

Typically includes:

- Clearing <code>Authentication</code> from the SecurityContext.
- Invalidating the HTTP session as required by default configuration.
- Clearing the SecurityContext stored in the security context repository.
- Running other configured logout handlers.

However, it **does not automatically guarantee**:

- The OpenID Provider SSO session has ended.
- Refresh tokens have been revoked at the Token Endpoint.
- Already-issued JWT access tokens are rejected by the Resource Server.
- Authorized clients in a persistent service have been removed.

Those actions have their own policies and endpoints.

## 13. OIDC RP-Initiated Logout: Where Does CSRF Apply?

**RP-Initiated Logout** occurs when the Client asks the OP to terminate the SSO session, typically after the user logs out of the Portal.

Example flow:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant RP as Spring Security Portal
    participant OP as OpenID Provider
    U->>B: Click Log out
    B->>RP: POST /logout + CSRF token
    RP->>RP: CSRF check; local logout handlers
    RP-->>B: Redirect to OP end_session_endpoint
    B->>OP: OIDC RP-Initiated Logout request
    OP->>OP: Check session/id_token_hint/client policy
    OP-->>B: Redirect to post_logout_redirect_uri if valid
    B->>RP: GET /login?logout
~~~

The **Portal's** CSRF protection applies on the local logout POST. The OP manages security for the **OP's** logout endpoint according to OIDC RP-Initiated Logout and SSO session policy.

### 13.1. Servlet Logout Success Handler

Example when the provider exposes <code>end_session_endpoint</code>:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.oidc.web.logout
    .OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.oauth2.client.registration
    .ClientRegistrationRepository;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcRpInitiatedLogoutConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        var successHandler =
            new OidcClientInitiatedLogoutSuccessHandler(registrations);
        successHandler.setPostLogoutRedirectUri(
            "{baseUrl}/login?logout");

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutSuccessHandler(successHandler));

        return http.build();
    }
}
~~~

**This is an alternative SecurityFilterChain to Section 11**; do not declare two chains with overlapping matchers at the same time.

Explanation:

1. The user triggers local logout per the Portal's method and CSRF policy.
2. Spring Security's logout success handler directs the browser to the OP logout endpoint per ClientRegistration/OIDC metadata.
3. The OP verifies details such as <code>id_token_hint</code> and post-logout redirect per capability/registration.
4. The Portal does not forward the user's local session cookie to the OP.

If the OP does not support RP-Initiated Logout, implement an appropriate local logout fallback; do not construct an OP logout endpoint from an untrusted browser-supplied URL.

### 13.2. `post_logout_redirect_uri`

The OP may require <code>post_logout_redirect_uri</code> to be pre-registered. Never pass a value like <code>returnTo=https://attacker.example</code> directly to the OP or redirect after logout without an allowlist/validation.

### 13.3. When OP Logout Uses GET

OIDC RP-Initiated Logout may use browser navigation to the OP endpoint. That is **part of the logout protocol at the OP**, not a reason to expose local <code>GET /logout</code> as an unguarded side effect without CSRF/user-intent protection.

The OP is responsible for the policy on the OP logout endpoint, including confirmation or session binding when appropriate.

## 14. OIDC Front-Channel Logout and CSRF

Front-Channel Logout uses the browser as the channel for the OP to notify the RP. It may involve iframes or navigations:

~~~text
OP → browser → RP front-channel logout URL
~~~

Characteristics:

- The browser may send RP cookies depending on SameSite/third-party cookie policies.
- The OP may pass <code>iss</code> and <code>sid</code> per profile and registration.
- The RP must validate legitimate messages per design, rather than treating an arbitrary attacker-triggered GET as proof of OP logout.
- Browser privacy restrictions may block third-party cookies, preventing Front-Channel Logout from locating the session.

### 14.1. Do Not Turn a Front-Channel Endpoint into a Public Force-Logout

If anyone can send:

~~~text
GET /frontchannel-logout?sub=user-123
~~~

and the server immediately deletes all sessions for `user-123` without correlation/validation, an attacker can cause mass logouts.

This is not a secure design. You must properly understand the OIDC Front-Channel Logout profile, <code>iss</code>/<code>sid</code> correlation, and browser-channel limitations. Never accept a caller-supplied <code>sub</code> as sole proof.

### 14.2. Front-Channel vs. Back-Channel

| Attribute | Front-Channel Logout | Back-Channel Logout |
|---|---|---|
| Channel | Browser/user agent | Server-to-server POST |
| Browser cookie | May participate, depends on policy | No browser cookie needed |
| Message | Front-channel protocol params | **Signed Logout Token** |
| Primary risks | Third-party cookie restrictions/iframe/forged navigation | JWT validation, session mapping, replay, endpoint availability |
| Spring Security integration | Depends on stack/version/provider | Dedicated OIDC Back-Channel Logout DSL in supported versions |

Do not apply a business HTML form's CSRF policy to Back-Channel Logout without understanding the JWT protocol; likewise, do not use a signed JWT Back-Channel Logout handler to process arbitrary GET iframes.

## 15. OIDC Back-Channel Logout: Server-to-Server POST Without a CSRF Form Token

In **Back-Channel Logout**, the OpenID Provider sends a request like:

~~~http
POST /logout/connect/back-channel/company HTTP/1.1
Host: portal.example.org
Content-Type: application/x-www-form-urlencoded

logout_token=SIGNED_LOGOUT_TOKEN_PLACEHOLDER
~~~

There is no browser session cookie; the OP does not have the local RP form's CSRF token.

Therefore, the primary safeguard is not a synchronizer CSRF token, but **Logout Token JWT validation**.

### 15.1. Logout Token Must Be Verified

Illustrative payload:

~~~json
{
  "iss": "https://idp.example.org/realms/company",
  "aud": "portal-web",
  "iat": 1794800000,
  "exp": 1794800120,
  "jti": "logout-event-01",
  "sid": "op-session-123",
  "sub": "user-456",
  "events": {
    "http://schemas.openid.net/event/backchannel-logout": {}
  }
}
~~~

Claims to verify per the OIDC Back-Channel Logout profile:

- OP signature and trusted algorithm/key.
- <code>iss</code> matches the registered OP.
- <code>aud</code> contains the corresponding Client ID.
- <code>iat</code>, <code>exp</code>, and clock skew per profile.
- <code>events</code> contains the exact logout event URI.
- At least one of <code>sub</code> or <code>sid</code> is present.
- <code>nonce</code> **must not be present**.
- <code>jti</code> and replay/idempotency policy when implemented.

Never accept an access token or ordinary ID Token as a Logout Token simply because it is signed by the same OP.

### 15.2. Why Not Require a Browser CSRF Token on Back-Channel POSTs?

The request is sent by the **OP server**. The OP cannot obtain a browser session's CSRF token at the RP and should never be given access to browser cookies.

Therefore, let the **framework OIDC Back-Channel Logout handler** handle the exact protocol path rather than enforcing a blanket policy that every POST needs a form CSRF token.

However, **exempting the synchronizer CSRF check does not mean the endpoint can skip JWT validation**. If a back-channel endpoint accepts an unsigned/unverified <code>sub=user-123</code> and deletes sessions, that is an exploitable vulnerability via forged requests.

### 15.3. Enabling the DSL for Supported Versions

Servlet Spring Security example:

~~~java
http
    .oauth2Login(Customizer.withDefaults())
    .oidcLogout(oidc -> oidc
        .backChannel(Customizer.withDefaults()));
~~~

Reactive WebFlux:

~~~java
http
    .oauth2Login(Customizer.withDefaults())
    .oidcLogout(oidc -> oidc
        .backChannel(Customizer.withDefaults()));
~~~

The DSL code looks almost identical, but the types are:

~~~text
Servlet:
    HttpSecurity + SecurityFilterChain

Reactive:
    ServerHttpSecurity + SecurityWebFilterChain
~~~

Built-in OIDC Back-Channel Logout arrived in Spring Security 6.2; handlers/configuration and default behaviors vary across 6.2.x, 6.5, and 7.x. **Check the actual API of your version** before copying configuration, especially custom handlers, internal logout URIs, and CSRF/session integration.

### 15.4. Do Not Disable CSRF App-Wide for Back-Channel

If you need to adjust a CSRF matcher/handler for back-channel, only touch the exact protocol path/method handled by the framework. Do not write:

~~~java
.csrf(csrf -> csrf.ignoringRequestMatchers("/logout/**"))
~~~

because that prefix can cover local browser logout or business endpoints. Keep **back-channel protocol endpoints** clearly separated from **local `/logout`**.

### 15.5. Session Registry and Clustering

Back-channel requests carry no browser cookies, so the RP needs the mapping:

~~~text
(issuer, clientId, sid/sub) → local session ID(s)
~~~

Spring Security provides <code>OidcSessionRegistry</code> in Servlet and <code>ReactiveOidcSessionRegistry</code> in WebFlux on supported versions.

If the application has two instances A/B and the registry is only in-memory:

~~~text
Login on A → A stores OP sid ↔ local session S1
Logout Token hits B → B does not know about S1
~~~

Even when Spring Session Redis shares HTTP sessions, the **OIDC session registry may still need its own distributed storage**. This is an availability/consistency issue, not a missing CSRF token.

## 16. Viewing "state", "CSRF token", and "Logout Token" in One Flow

~~~mermaid
flowchart TD
    START["Browser starts OIDC Login"] --> INIT["GET /oauth2/authorization/company"]
    INIT --> STATE["Client generates state, nonce/PKCE"]
    STATE --> OP["OP Authorization Endpoint"]
    OP --> CB["GET callback code + state"]
    CB --> VERIFY{"state + token validations valid?"}
    VERIFY -->|No| FAIL["Reject login"]
    VERIFY -->|Yes| AUTH["Create authenticated browser session"]
    AUTH --> FORM["Browser POST /settings"]
    FORM --> CSRF{"Spring CSRF token valid?"}
    CSRF -->|No| FORBID["403 CSRF"]
    CSRF -->|Yes| BIZ["Check role/tenant, execute business logic"]
    AUTH --> LOGOUT["Browser POST /logout"]
    LOGOUT --> LOGCSRF{"CSRF token valid?"}
    LOGCSRF -->|No| FORBID
    LOGCSRF -->|Yes| LOCAL["Local session logout"]
    AUTH --> BACK["OP POST back-channel Logout Token"]
    BACK --> JWT{"Signed Logout Token valid?"}
    JWT -->|No| BAD["Reject request"]
    JWT -->|Yes| LOCAL
~~~

With a <code>form_post</code> callback, path <code>CB</code> is a POST, yet it still requires **state/nonce/PKCE/issuer validation**; the CSRF matcher must be adjusted **specifically for the protocol** if framework/cookie configuration supports it.

## 17. Spring Security Servlet: Configuring Session, CSRF Repository, and Token Handler

### 17.1. SessionCsrfTokenRepository

Spring Security can store the CSRF token in the HTTP session. Key distinction:

~~~text
HttpSession
   ├── SecurityContext
   ├── OAuth2AuthorizationRequest (state/correlation)
   └── CSRF token (for browser POSTs)
~~~

These are three separate pieces of data, even though they reside in the same session.

For server-rendered browser forms, CSRF token usage can be integrated automatically by the template engine/Spring MVC.

### 17.2. CSRF Tokens in SPAs

For an SPA sharing a BFF backend, one pattern uses a CSRF token cookie sent back in a header. Spring Security provides <code>CookieCsrfTokenRepository</code>:

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

http.csrf(csrf -> csrf
    .csrfTokenRepository(
        CookieCsrfTokenRepository.withHttpOnlyFalse()));
~~~

**Do not copy this snippet by default for every application.** Reasons:

- <code>withHttpOnlyFalse()</code> allows JavaScript to read the CSRF token cookie; suitable for some SPA patterns, but increases the chance of the token being read by scripts in the origin.
- The CSRF token cookie is **distinct from the session cookie**; the session cookie should remain <code>HttpOnly</code> whenever possible.
- Spring Security has deferred CSRF tokens, XOR/BREACH token handling, and version-specific SPA CSRF integration guides.
- An SPA needs a way to obtain a fresh token after login/logout/session rotation and send the right header, avoiding stale tokens.

If building an SPA, consult the SPA CSRF solution for your exact Spring Security version rather than just adding a cookie repository and expecting every request to work.

### 17.3. Do Not Treat an Arbitrary Header as Sufficient

A request:

~~~http
POST /account/change-email HTTP/1.1
X-CSRF-TOKEN: attacker-supplied-value
~~~

is safe only if the value is **compared by the server against the valid token** in the repository/handler. Merely having a header named <code>X-CSRF-TOKEN</code> proves nothing.

## 18. Reactive WebFlux: CSRF and OIDC Flow

The reactive stack uses:

| Servlet | WebFlux |
|---|---|
| <code>HttpSecurity</code> | <code>ServerHttpSecurity</code> |
| <code>SecurityFilterChain</code> | <code>SecurityWebFilterChain</code> |
| <code>HttpSession</code> | <code>WebSession</code> |
| <code>HttpSessionOAuth2AuthorizationRequestRepository</code> | <code>WebSessionOAuth2ServerAuthorizationRequestRepository</code> |
| <code>CsrfTokenRepository</code> | <code>ServerCsrfTokenRepository</code> |
| <code>CsrfFilter</code> | <code>CsrfWebFilter</code> |
| <code>HttpServletRequest</code> | <code>ServerWebExchange</code> |
| <code>SecurityContextHolder</code> | <code>ReactiveSecurityContextHolder</code> |

### 18.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Do not accidentally include <code>spring-boot-starter-web</code> if your target is Reactive WebFlux; when both MVC and WebFlux are present, Spring Boot typically defaults to Servlet MVC.

### 18.2. SecurityWebFilterChain

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class WebFluxSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/login", "/error")
                    .permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            .build();
    }
}
~~~

The same principles as Servlet apply:

- OAuth2 GET callbacks use state/correlation.
- Business browser POSTs and local logout are protected by CSRF.
- Back-channel logout requires the version-specific OIDC handler.
- Reactive sessions/WebFilters must not be mixed with Servlet APIs.

### 18.3. WebSessionServerCsrfTokenRepository

In WebFlux, <code>WebSessionServerCsrfTokenRepository</code> uses WebSession:

~~~java
import org.springframework.security.web.server.csrf
    .WebSessionServerCsrfTokenRepository;

http.csrf(csrf -> csrf
    .csrfTokenRepository(
        new WebSessionServerCsrfTokenRepository()));
~~~

This is an illustrative configuration. In a real project, an equivalent default repository may already be active; do not declare redundant beans/handlers unnecessarily. How the CSRF token is exposed to reactive views/SPAs depends on the Spring Security version and view technology.

### 18.4. Reactive Cookie CSRF Repository

Spring Security WebFlux also provides:

~~~java
import org.springframework.security.web.server.csrf
    .CookieServerCsrfTokenRepository;

http.csrf(csrf -> csrf
    .csrfTokenRepository(
        CookieServerCsrfTokenRepository.withHttpOnlyFalse()));
~~~

The caveats for SPAs and readable CSRF cookies in Section 17.2 still apply. **Do not use a cookie repository just to avoid managing WebSession for OIDC Login**, because authorization request state and login security context still need proper storage/correlation.

### 18.5. Do Not Call `block()` or Manually `subscribe()`

If writing a custom reactive authorization request repository or CSRF token handler, never call:

~~~java
exchange.getSession().block();
~~~

inside the WebFlux request pipeline. Use <code>Mono.flatMap</code> or reactive interfaces. A callback/CSRF handler blocking the Netty event-loop can cause severe contention under load and destabilize logins.

## 19. When Multiple `SecurityFilterChain`s Coexist

An application may serve both:

- Browser OIDC Login: uses cookies/sessions/CSRF.
- Bearer-only APIs: stateless and potentially without needing a CSRF token if the browser does not attach credentials automatically.

### 19.1. Servlet: API Chain and Browser Chain

Example:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SplitSecurityChains {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http)
            throws Exception {

        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .csrf(csrf -> csrf.disable());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        return http.build();
    }
}
~~~

If using a JWT Resource Server in the API chain, you need the <code>spring-boot-starter-oauth2-resource-server</code> dependency and proper issuer/audience validation.

**Only disable CSRF on the API chain when the threat model confirms the API accepts strictly non-automatic bearer credentials.** If <code>/api/**</code> still accepts session cookies, the pattern above must be adjusted.

### 19.2. `securityMatcher` Differs from `authorizeHttpRequests`

- <code>securityMatcher("/api/**")</code>: selects **which chain handles the request**.
- <code>authorizeHttpRequests(...)</code>: defines **authorization rules within the selected chain**.

If the API chain at <code>@Order(1)</code> matches <code>/**</code>, it can swallow:

~~~text
/oauth2/authorization/company
/login/oauth2/code/company
/logout
/logout/connect/back-channel/company
~~~

In that case, the browser chain's login/callback/logout filters never run, and engineers might mistake a 401/403 for a CSRF failure when the root cause is **chain selection**.

### 19.3. WebFlux Follows the Same Principle

In Reactive, use multiple <code>SecurityWebFilterChain</code>s with corresponding <code>securityMatcher(...)</code>s. The API chain must not unintentionally match browser/OIDC protocol routes.

Never use Servlet <code>AntPathRequestMatcher</code> inside a WebFlux exchange matcher; pick the reactive API matching your Spring Security version.

## 20. SameSite, Secure, HttpOnly, and Browser Cookie Policies

CSRF protection operates alongside cookie/session policies.

### 20.1. SameSite=Lax

With <code>SameSite=Lax</code>:

- Cookies are usually sent when the browser performs a top-level cross-site GET navigation from the OP back to the RP.
- Cookies are normally **not** sent on cross-site POSTs, such as an OIDC <code>form_post</code> callback.
- Some browsers have special behaviors for newly created/unspecified SameSite cookies; never rely on inconsistent behavior as a security contract.

### 20.2. SameSite=Strict

<code>SameSite=Strict</code> can break OIDC callbacks because cross-site navigation from the OP back to the RP will not include the session cookie. Do not choose Strict just because it sounds "most secure" while breaking the real login flow.

### 20.3. SameSite=None

<code>SameSite=None; Secure</code> allows cookies to be sent in more cross-site contexts, which some flows/embeddings require. However, it also makes the browser attach cookies on more cross-site requests, making **CSRF tokens and Origin/Referer policies** even more essential to get right.

### 20.4. HttpOnly

<code>HttpOnly</code> restricts JavaScript from reading the session cookie. It **does not** prevent the browser from automatically sending the cookie on cross-site requests, so it does not replace CSRF protection.

### 20.5. Secure

<code>Secure</code> instructs the browser to send the cookie only over HTTPS, reducing cookie exposure over HTTP. It **does not** prevent CSRF if a cross-site HTTPS request still carries a valid cookie.

### 20.6. Domain and Path

Cookie domain/path determine which hosts/routes receive the cookie. Do not use an overly broad domain like <code>.example.org</code> when subdomains do not share the same trust level; a compromised sibling subdomain could affect cookie/session policy.

### 20.7. Illustrative Servlet Configuration

~~~yaml
server:
  servlet:
    session:
      cookie:
        http-only: true
        secure: true
        same-site: lax
~~~

This is a baseline generally suited for **GET callbacks** over HTTPS. If using <code>form_post</code>, re-design and test SameSite/correlation; do not switch to None without evaluating all other routes.

Spring Session may use the cookie name <code>SESSION</code> instead of <code>JSESSIONID</code>; the cookie name does not change the purpose of CSRF tokens, though it relates to callback/session/logout handlers.

## 21. Reverse Proxies, Redirect URIs, and CSRF Login Failures

An application behind a load balancer:

~~~text
Browser → https://portal.example.org
Proxy   → http://app:8080
~~~

If Spring Boot does not know the public scheme/host, the authorization request may generate:

~~~text
redirect_uri=http://app:8080/login/oauth2/code/company
~~~

The OP rejects it due to a redirect URI mismatch. Users may see "OAuth2 Login failed" and misdiagnose it as a CSRF token issue.

### 21.1. Trust Forwarded Headers Only from Trusted Proxies

You can configure handling of <code>Forwarded</code>/<code>X-Forwarded-*</code> headers per Spring Boot/version, but only when the ingress/proxy controls and strips headers sent directly by untrusted clients.

If an attacker-controlled <code>X-Forwarded-Host</code> is trusted, the application may construct redirect URIs pointing to an attacker domain, compromising OAuth security.

### 21.2. Consistent Domain and Cookie Policy

Verify:

- <code>redirect_uri</code> matches the public HTTPS URL.
- Session cookie Domain/Path covers the callback route.
- Browser actually sends the session cookie on the callback.
- CSRF cookie has the right domain and path for business POSTs.
- Multiple app instances share a session store or have session affinity.

Do not confuse a <code>redirect_uri_mismatch</code> with a Spring Security CSRF 403.

## 22. Multi-Instance: Where Do `state` and CSRF Tokens Live?

In a cluster:

~~~text
Browser
   ↓
Load Balancer
   ├── Instance A
   └── Instance B
         ↓
    Shared session store
~~~

Authorization initiation on A may store state/correlation in A's local <code>HttpSession</code>. A callback hitting B will fail to find the original request if sessions are not shared.

### 22.1. Spring Session Redis

Spring Session can share HTTP sessions/WebSessions across nodes. Depending on the repository:

~~~text
Session S123
    ├── SecurityContext
    ├── AuthorizationRequest(state=S1)
    └── CSRF token (if Session CSRF repository)
~~~

Instance B receives S123's cookie, reads the shared session, and can process both the callback and valid POST CSRF checks per the state/repository.

**However, Spring Session does not automatically synchronize every other in-memory store**, such as:

- <code>InMemoryOAuth2AuthorizedClientService</code>.
- Custom in-memory saved requests.
- In-memory OIDC Back-Channel Logout registries.
- Local deduplication/lock caches.

### 22.2. Never Disable `state` or CSRF Because of Clustering

If node B reports <code>invalid_state</code>, the cause is likely session/cookie/storage handling; **removing state validation introduces login CSRF risk**.

If node B reports a CSRF token mismatch on a form POST, the cause is likely session store/token repository/stale SPA tokens; **disabling CSRF app-wide introduces business CSRF risk**.

### 22.3. Multiple Tabs

Within the same browser session:

~~~text
Tab 1 starts Company OIDC login: state=S1
Tab 2 starts Partner OIDC login: state=S2
Tab 1 callback state=S1
~~~

If a custom repository only stores a single authorization request and Tab 2 overwrites Tab 1, callback S1 may fail. Never treat this as a reason to accept any state.

Design the repository to support multiple concurrent requests or guide the UX to avoid simultaneous login flows. A session's business CSRF token must not be used instead of per-flow OAuth2 state.

## 23. Login CSRF When "Switching Accounts" or Account Linking

An application supporting multiple providers typically has:

~~~text
/oauth2/authorization/company
/oauth2/authorization/partner
~~~

If a logged-in user clicks "Link Partner Account," the application is performing a **sensitive action**: attaching a new identity to the current internal account.

### 23.1. GET Authorization Initiation Is Not Linking Consent

A GET link to an OP only starts a login. It does not by itself prove the user consented to link an account.

Better:

1. User is already authenticated to internal account A.
2. User submits a CSRF-protected **POST /account/link/provider**.
3. Backend validates provider allowlist, confirms intent, and requires step-up auth if needed.
4. Backend creates a linking transaction bound to the session and state.
5. Browser starts OAuth2/OIDC authorization to provider B.
6. Callback validates state, issuer, subject, and policy.
7. Backend links only if identity B does not belong to another account and authorization is explicit.

Never auto-merge accounts solely because emails match across two providers.

### 23.2. Account Switching Can Cause Session Swapping

If an attacker forces a logged-in browser into the attacker's account, the user may unwittingly enter sensitive data into a session they do not own. Login-flow CSRF/state validation and UI confirmation are two layers of mitigation.

A POST to switch the active account must be protected by CSRF/session validation per policy. After switching, roles/tenants/caches must be recomputed for the new principal.

### 23.3. Never Take the Issuer from the Browser

A browser-supplied authorization request parameter like <code>provider=https://evil.example</code> must never cause the Client to dynamically spin up a new OP and exchange codes/tokens at an arbitrary endpoint.

With multiple providers, defend against OAuth mix-up via request correlation/registration binding, exact issuer/audience checks, and measures like issuer identification (RFC 9207) when supported by provider/framework.

## 24. Distinguishing CSRF Errors from Authentication/Authorization Failures

When encountering HTTP 403, do not assume every case is CSRF.

| Symptom | Likely failure layer | How to verify |
|---|---|---|
| Browser POST <code>/settings</code> 403, missing <code>_csrf</code> | CSRF filter | Check CSRF token repository, request header/form, session cookie |
| POST <code>/logout</code> 403 | Logout CSRF | Verify form/header includes CSRF token and correct cookie |
| GET OAuth callback reports <code>invalid_state</code> | OAuth2 correlation | Check session, authorization request repository, state |
| Form-post callback 403 before login filter | CSRF matcher | Check response_mode support and narrow exception |
| Callback state missing after switching nodes | Session distribution | Check Spring Session/cookies/session affinity |
| Token Endpoint returns <code>invalid_grant</code> | OAuth grant/code/refresh token | Check token request, code_verifier, expiry, replay |
| Token Endpoint returns <code>invalid_client</code> | Client authentication | Check secret/key, method, ClientRegistration |
| Resource Server returns 401 | Bearer token authentication | Check issuer, audience, expiry, signature, Authorization header |
| Resource Server returns 403 <code>insufficient_scope</code> | OAuth authorization | Check scope/resource policy; do not blindly refresh |
| Browser <code>/admin</code> returns 403 | Spring authorities/business authorization | Check role, tenant, ownership |
| OP consent POST blocked | CSRF/policy at OP | Check OP logs/form/session; do not change RP CSRF |
| Back-channel POST returns 400 | Logout Token JWT validation | Check iss/aud/signature/events/exp/sid/sub/nonce |
| Back-channel POST returns 401 | Wrong chain, API Bearer authentication | Check whether OIDC/logout filter handles that endpoint |

### 24.1. 401 vs. 403

HTTP 401 generally relates to an unauthenticated request or rejected token. HTTP 403 generally relates to insufficient permissions or CSRF protection rejecting the request. However, gateways/WAFs and application handlers can alter status codes, so always inspect the source of the response.

### 24.2. Identify Which Filter Rejected the Request

In Spring Security Servlet, key filters include:

~~~text
CsrfFilter
OAuth2AuthorizationRequestRedirectFilter
OAuth2LoginAuthenticationFilter
LogoutFilter
ExceptionTranslationFilter
AuthorizationFilter
~~~

In WebFlux:

~~~text
CsrfWebFilter
OAuth2AuthorizationRequestRedirectWebFilter
OAuth2LoginAuthenticationWebFilter
LogoutWebFilter
AuthorizationWebFilter
~~~

**Do not infer absolute filter ordering from the order in this list.** Each security chain and Spring Security version has specific filter positions; inspect the actual chain when diagnosing.

A CSRF exception handler can produce a 403 before controller or login handler code runs, whereas a 403 from a Resource Server occurs after OAuth2 Login has already succeeded.

## 25. Diagnostic Workflow by Endpoint

~~~mermaid
flowchart TD
    A["Request failed"] --> B{"Which endpoint?"}
    B -->|"/oauth2/authorization/{id}"| C["Registration/issuer/redirect URI/state creation"]
    B -->|"OP /authorize / consent"| D["OP login/consent CSRF + client/redirect policy"]
    B -->|"GET OAuth2 callback"| E["state, session, code exchange, PKCE, OIDC ID Token"]
    B -->|"POST form_post callback"| F["form_post support, narrow CSRF path, cookie SameSite, state"]
    B -->|"POST /logout"| G["Spring CSRF token, session, logout handlers"]
    B -->|"Back-channel logout"| H["Signed Logout Token validation, session registry"]
    B -->|"Browser POST business"| I["CSRF token + role/tenant/ownership"]
    B -->|"Bearer API"| J["Access token issuer/audience/scope/authorization"]
~~~

### 25.1. Safe Debug Data

Appropriate log fields may include:

~~~text
routeTemplate=/login/oauth2/code/{registrationId}
httpMethod=GET
registrationId=company
securityChain=browser
sessionPresent=true
authorizationRequestPresent=false
oauth2Error=authorization_request_not_found
correlationId=...
~~~

Never log:

~~~text
authorization_code
actual state
actual nonce
code_verifier
CSRF token value
access_token / refresh_token / id_token
session cookie / client secret
~~~

If you need to correlate events, use a dedicated request correlation ID that is not a credential. Avoid using raw session IDs or subjects/emails as metric labels.

## 26. Testing CSRF and OIDC Login in Servlet

Spring Security Test can use MockMvc to verify browser endpoints.

### 26.1. Dependencies

~~~groovy
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.springframework.security:spring-security-test'
~~~

### 26.2. Business POST Without CSRF Must Be Rejected

Test example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oauth2Login;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfBusinessEndpointTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void postWithoutCsrfIsRejected() throws Exception {
        mockMvc.perform(post("/account/change-email")
                .with(oauth2Login())
                .param("email", "new@example.org"))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfPassesCsrfCheck() throws Exception {
        mockMvc.perform(post("/account/change-email")
                .with(oauth2Login())
                .with(csrf())
                .param("email", "new@example.org"))
            .andExpect(status().is2xxSuccessful());
    }
}
~~~

The second test is **only valid if the endpoint exists**, the mocked user is authorized to perform the business action, and the controller returns 2xx. If policy requires specific roles/validation, assertions must reflect them. <code>.with(csrf())</code> proves the request passes the CSRF check; it **does not** grant business authorization.

### 26.3. Testing Logout

Example:

~~~java
@Test
void logoutPostWithoutCsrfIsRejected() throws Exception {
    mockMvc.perform(post("/logout")
            .with(oauth2Login()))
        .andExpect(status().isForbidden());
}

@Test
void logoutPostWithCsrfIsProcessed() throws Exception {
    mockMvc.perform(post("/logout")
            .with(oauth2Login())
            .with(csrf()))
        .andExpect(status().is3xxRedirection());
}
~~~

Depending on <code>logoutSuccessHandler</code>, the logout response may differ from a simple redirect (e.g., OIDC RP-Initiated Logout). Assert your application's actual contract rather than treating every 302 as success.

### 26.4. Mock OIDC Login Does Not Test OAuth Callbacks

<code>oauth2Login()</code>/<code>oidcLogin()</code> in Spring Security Test can simulate an authenticated principal. They **do not verify**:

- Whether the authorization request repository creates/saves state properly.
- How PKCE verifier/challenge are generated and verified.
- Whether the provider callback has a valid state.
- ID Token signature/issuer/audience/nonce verification.
- Browser SameSite and form_post behavior.

Those protocol requirements need integration tests against a test/fixture OP with reliable keys and metadata.

## 27. Testing CSRF in Reactive WebFlux

Spring Security Test supports WebTestClient:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOidcLogin;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveCsrfTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void postWithValidCsrfCanReachHandler() {
        webTestClient
            .mutateWith(mockOidcLogin())
            .mutateWith(csrf())
            .post()
            .uri("/account/update")
            .bodyValue("{\"value\":\"demo\"}")
            .exchange()
            .expectStatus().is2xxSuccessful();
    }
}
~~~

This example assumes <code>/account/update</code> exists and returns 2xx when the mock principal is authorized and the DTO/body matches. This is a **CSRF integration test pattern**, not a test you can copy and run without a controller.

To test missing CSRF, omit <code>.mutateWith(csrf())</code> and expect 403 when the request genuinely uses a cookie-based authenticated context per test setup.

Do not write a test that just hits <code>GET /login/oauth2/code/company</code> with a dummy code expecting 200; a real callback requires state/authorization request/Token Endpoint/ID Token validation.

## 28. Integration Test Matrix for Authorization/Callback/Logout

| Scenario | Expected behavior |
|---|---|
| Browser GET <code>/oauth2/authorization/company</code> | Redirects to OP for the right registration; authorization request is saved |
| Browser hits GET callback with valid state | Correlation succeeds, token exchange/validation occurs |
| GET callback with wrong state | No Authentication created |
| GET callback missing authorization request in session | Code is rejected |
| Callback with already-used code | Token Endpoint/flow rejects per policy |
| Callback ID Token with wrong nonce/issuer/audience | Login fails |
| Browser POST form-post callback without CSRF form token | Can only be processed if path is narrowly scoped and OIDC state validation still passes |
| Form-post callback with incompatible SameSite cookie | Correlation cannot find session; state is not bypassed |
| Browser POST <code>/settings</code> without CSRF | Rejected |
| Browser POST <code>/settings</code> with CSRF, missing role | Still rejected by authorization |
| Browser POST <code>/logout</code> without CSRF | Rejected |
| Browser POST <code>/logout</code> with CSRF | Local logout per policy |
| External site forces GET <code>/logout</code> | Does not perform arbitrary logout side effect |
| OP Back-Channel Logout with invalid JWT signature | Rejected |
| OP Back-Channel Logout with valid JWT | Invalidates the corresponding session mapping |
| Browser GET callback hits different node A/B | State remains accessible if shared session works |
| OP POST back-channel hits different node from login | Shared registry finds session if designed for HA |
| API Bearer 401 <code>invalid_token</code> | Handled as token validation, not confused with CSRF |
| API Bearer 403 <code>insufficient_scope</code> | Handled as permissions, not blindly refreshed |

### 28.1. Real Browser Testing

MockMvc/WebTestClient do not fully simulate SameSite behavior, third-party cookies, or OP UIs. When using <code>response_mode=form_post</code>, test in a real browser/automation with sessions and a test OP.

### 28.2. Multi-Tab Testing

Initiate two authorization requests concurrently in the same browser session. Verify whether the repository supports correlating both or the application handles the UX clearly without "accepting any state."

### 28.3. Rate Limiting and Endpoint Input Testing

Especially for Back-Channel Logout:

- Invalid JWTs must be rejected without invalidating sessions.
- Oversized payloads must be bounded.
- Replayed logout events should be idempotent/handled per policy.
- Never log raw JWTs.

## 29. Scenario Exercises

### Exercise 1 — With `state` Present, Should We Disable CSRF?

An OIDC Client application uses session cookies and has POST <code>/transfer</code>. The developer disables CSRF globally because OAuth2 already has state.

**Question:** What is wrong?

**Answer:** <code>state</code> only binds the OAuth2 callback to the authorization request; it does not protect business POSTs. <code>/transfer</code> must be protected with a CSRF token or an equivalent mechanism fitting the threat model.

### Exercise 2 — Whose Authorization Endpoint Is It?

The Portal app has <code>/oauth2/authorization/company</code> and the OP has <code>/authorize</code>.

**Question:** Which party checks CSRF on the OP's consent form?

**Answer:** The Authorization Server/OP. The Portal manages the OAuth2 Client's authorization initiation and state; it does not manage CSRF tokens inside the OP's consent form.

### Exercise 3 — GET Callback

The browser returns to <code>/login/oauth2/code/company?code=C&amp;state=S</code>. The request has no <code>_csrf</code>.

**Question:** Is this a security bug by default?

**Answer:** No. The Authorization Code Flow GET callback is protected by state/correlation, PKCE, and flow-specific OIDC validation. A browser POST form CSRF token is not required for a GET callback.

### Exercise 4 — Callback State Mismatch

The original authorization request had state S1, and the callback carries S2.

**Question:** Can we skip state validation if the ID Token later has a valid signature?

**Answer:** No. The callback must be bound to the original request/session. A validly signed token does not prove that the user initiated that flow.

### Exercise 5 — Form-Post Callback 403

The OP returns to the callback via a cross-site POST, and Spring Security's CSRF filter returns 403.

**Question:** What should be done?

**Answer:** Verify framework support for form_post and cookie/session correlation, then exclude **only the exact POST callback path** from the synchronizer CSRF check if needed; keep state/nonce/PKCE/issuer validation mandatory. Never disable CSRF app-wide.

### Exercise 6 — SameSite=Lax and form_post

After adjusting the CSRF matcher, the form-post callback still reports missing state.

**Question:** Why?

**Answer:** A cross-site POST may omit the session cookie under SameSite=Lax, so the Client cannot locate the saved authorization request. Check cookie policy, browser, and flow; never fabricate state from the callback.

### Exercise 7 — GET /logout

The application creates its own <code>GET /logout</code> that invalidates the session.

**Question:** What is the impact?

**Answer:** An external site can force navigation to log the user out, causing logout CSRF/disruption. Prefer POST with CSRF protection for local logout.

### Exercise 8 — Back-Channel POST Without `_csrf`

The OP sends a signed Logout Token via POST without a CSRF form token.

**Question:** Should all such requests be rejected simply for lacking <code>_csrf</code>?

**Answer:** Back-Channel Logout uses Logout Token JWT signature/claims validation, not a browser session CSRF token. Configure the handler appropriate to your stack/version so only the protocol endpoint is handled, without skipping JWT validation.

### Exercise 9 — Back-Channel JWT Contains `nonce`

A Logout Token has a valid signature but includes a <code>nonce</code> claim.

**Question:** Should it be accepted?

**Answer:** No. A Logout Token must not contain `nonce` per the OIDC Back-Channel Logout profile; avoid confusing an ID Token with a Logout Token.

### Exercise 10 — API Resource Server and CSRF

<code>/api/**</code> only accepts Bearer tokens in the Authorization header and does not use browser cookies. Browser portal routes use session cookies.

**Question:** Can CSRF be disabled only in the API chain?

**Answer:** Yes, if the threat model confirms no browser-auto-sent credentials are accepted; use a dedicated chain matcher and keep CSRF on browser routes. Never disable CSRF across all chains just because there is an API.

### Exercise 11 — Valid CSRF Token, User Lacks Role

A browser POST to <code>/admin/users</code> has a valid CSRF token and a normal user session, yet the server returns 403.

**Question:** Is this a CSRF error?

**Answer:** Not necessarily; it may be an authorization failure. A CSRF token only proves request-origin intent for the session—it does not grant the ADMIN role.

### Exercise 12 — Two Providers

The browser starts authorization at Company, but the callback tries to use Partner's token/issuer.

**Question:** Is `state` alone enough for complete protection?

**Answer:** You must bind the request to the original registration/issuer/redirect URI, validate state, and perform OIDC issuer/audience/nonce/ID Token checks; evaluate mix-up mitigation per RFC 9207 when supported.

### Exercise 13 — Multi-Instance

Authorization initiation runs on node A, the callback hits node B, and state is missing.

**Question:** Should Spring Security's CSRF filter be disabled?

**Answer:** No. This is typically a session/correlation storage, cookie, or affinity issue. Use a shared session store and inspect the authorization request repository.

### Exercise 14 — Account Linking

An external site forces a browser already logged into Portal to visit the Partner identity-linking URL.

**Question:** Besides callback state, what does Portal need?

**Answer:** Linking should start with a CSRF-protected POST and intent confirmation, then use a linking transaction bound to the current session/identity; the callback must still validate OAuth state, issuer, and subject.

### Exercise 15 — Designing Protection for Five Endpoints

Design an application with:

~~~text
GET  /oauth2/authorization/company
GET  /login/oauth2/code/company
POST /logout
POST /account/change-email
POST /logout/connect/back-channel/company
~~~

**Requirement:** State the primary protection mechanism for each endpoint.

**Suggested answer:**

1. GET initiation: ClientRegistration allowlist, server-generated authorization request, state; never let the caller supply an arbitrary issuer.
2. GET callback: state and request correlation, PKCE/nonce/issuer/audience validation; no browser form CSRF token needed.
3. POST local logout: valid CSRF token and standard logout handlers.
4. POST change email: CSRF token **and** business authorization/validation.
5. POST back-channel: signed Logout Token validation/registry/issuer/audience; no browser form CSRF token.

### Exercise 16 — Spring Security Hands-On Practice

1. Create a Spring Boot Servlet app with <code>spring-boot-starter-oauth2-client</code>.
2. Configure registration <code>company</code> using Authorization Code and OIDC.
3. Enable <code>oauth2Login()</code> and keep default CSRF enabled.
4. Create a page/POST form changing a setting; test without and with a CSRF token.
5. Create a POST logout form; verify missing CSRF is rejected.
6. Log in through a test OP and verify the GET callback uses state/correlation.
7. Test a callback with a forged state; confirm no session is created.
8. Only if the OP/framework supports <code>form_post</code>, test POST callbacks with cookie/SameSite policy and narrow CSRF handling.
9. If using RP-Initiated Logout, verify local POST requires CSRF before redirecting to the OP.
10. If using Back-Channel Logout, enable the version-appropriate DSL and test signed Logout Token/registry handling.
11. Create a separate Bearer-only API chain and verify browser CSRF stays enabled.
12. Test with two instances and observe session/state/CSRF storage when callbacks land on another node.
13. Keep logs free of tokens, authorization codes, session cookies, or CSRF values.

## 30. Summary

- **CSRF** occurs when an attacker causes a browser to automatically send a user's credentials to perform an unintended request. OIDC applications using session cookies still need CSRF protection on side-effecting POST/PATCH/DELETE endpoints.
- <code>/oauth2/authorization/{registrationId}</code> on the **Client** differs from <code>/authorize</code> on the **OP**. The Client manages authorization initiation and state; the OP protects its own login/consent forms.
- **OAuth2 <code>state</code>** binds the callback to the authorization request and browser session; the **Spring CSRF token** protects state-changing browser forms/requests. They do not replace one another.
- **OIDC nonce, PKCE, and issuer/audience validation** add defenses against replay, code injection, and provider mix-up; they do not replace business CSRF tokens.
- A normal GET authorization-code callback **does not need a CSRF form token**, but it must be strictly checked for state/correlation by Spring Security OAuth2 Login.
- For <code>response_mode=form_post</code>, you need framework support for POST callbacks, SameSite-compatible session cookies, and a **narrow CSRF exception for that exact protocol endpoint** when required; never disable CSRF system-wide.
- Local logout should use **POST with CSRF**. A GET that automatically destroys the session can cause logout CSRF.
- OIDC **RP-Initiated Logout** has the Client ask the OP to end SSO after local logout; **Front-Channel Logout** uses the browser; **Back-Channel Logout** uses a server-to-server signed Logout Token, not a browser CSRF token.
- Back-Channel Logout must validate JWT issuer/audience/events/expiry/sid/sub/no-nonce and session mapping; bypassing CSRF while skipping JWT validation is highly dangerous.
- Truly **Bearer-only stateless** APIs may not need a CSRF token, but browser session routes must remain in a security chain with CSRF protection.
- SameSite, Secure/HttpOnly, reverse proxies, multiple tabs, and shared session stores determine whether callbacks/CSRF tokens can be recovered; never fix storage issues by removing protections.
- Testing must separate **browser business CSRF**, **OAuth callback state**, **OIDC token validation**, **logout CSRF**, and **back-channel logout token validation**.

### References

- **Spring Security Reference — Servlet CSRF Protection:** <code>CsrfFilter</code>, token repositories, CSRF request handlers, and SPA integration.
- **Spring Security Reference — Reactive CSRF Protection:** <code>CsrfWebFilter</code>, <code>ServerCsrfTokenRepository</code>, WebSession/cookie approaches.
- **Spring Security Reference — OAuth2 Login (Servlet/Reactive):** authorization initiation, authorization request repository, callbacks, and OIDC validation.
- **Spring Security Reference — Logout (Servlet/Reactive):** local logout handlers, CSRF, and logout success handlers.
- **Spring Security Reference — OIDC Login Logout:** RP-Initiated Logout, Back-Channel Logout, and session registries per supported version.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Authorization Code Flow, Authorization Endpoint, <code>state</code>, and Token Endpoint.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** authorization code binding.
- **RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification:** issuer-based mix-up mitigation.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** browser-based flows, redirect URIs, mix-up, and CSRF considerations.
- **OpenID Connect Core 1.0:** <code>state</code>, <code>nonce</code>, ID Token, issuer, audience, max_age, and OIDC login semantics.
- **OAuth 2.0 Form Post Response Mode 1.0:** cross-site callbacks using HTML form POST.
- **OpenID Connect RP-Initiated Logout 1.0:** <code>end_session_endpoint</code>, <code>id_token_hint</code>, and post-logout redirection.
- **OpenID Connect Front-Channel Logout 1.0:** browser channel and session correlation.
- **OpenID Connect Back-Channel Logout 1.0:** <code>logout_token</code>, signed JWT validation, and session correlation.
- **OWASP Cross-Site Request Forgery Prevention Cheat Sheet:** synchronizer/double-submit tokens, SameSite, Origin/Referer, and defense-in-depth.
- **OWASP Session Management Cheat Sheet:** session cookie configuration, session fixation, authentication/session lifecycle.
