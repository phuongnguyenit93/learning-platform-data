# RP-Initiated Logout and the OIDC Logout Endpoint

## 1. Why Is RP-Initiated Logout Needed?

A Spring Boot application using OpenID Connect (OIDC) typically has two separate login states:

- **Session at the Relying Party (RP):** the session/cookie of the application currently in use, such as a portal or web application.
- **Session at the OpenID Provider (OP):** the user's SSO session at the Authorization Server/Identity Provider, which may be shared by multiple RPs.

When a user clicks "Sign out" on one RP, clearing the RP's cookie only terminates the local session. If the OP still has an active SSO session, the next time the user opens another RP or logs in again, the OP can authenticate them automatically without asking for a password. This is normal SSO behavior, though it sometimes does not match the user's expectation of "logging out of the system."

**OpenID Connect RP-Initiated Logout 1.0** defines how an RP redirects the user's browser to the OP's **Logout Endpoint** to request that the OP end the login session. The OP can identify the session/application requesting logout using a previously issued ID Token, prompt the user for confirmation when needed, perform the logout, and redirect the browser back to the RP if the redirect is permitted.

This lesson belongs to the **OIDC Logout** chapter in the `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER` module and focuses on **RP-Initiated Logout and the OIDC Logout Endpoint** using Spring Security and Spring Authorization Server (SAS).

After this lesson, you should be able to:
1. Distinguish between local logout, RP-Initiated Logout, OP logout, and logout notifications.
2. Locate `end_session_endpoint` from the OpenID Provider Configuration.
3. Construct a logout request with `id_token_hint`, `post_logout_redirect_uri`, `state`, and optional parameters.
4. Understand the rules for validating an ID Token hint and protecting post-logout redirects.
5. Enable and customize the Logout Endpoint in Spring Authorization Server.
6. Connect Spring Security local logout with the OP using `OidcClientInitiatedLogoutSuccessHandler`.
7. Test session lifecycle, redirects, logout idempotency, and attack scenarios.

### 1.1. Three Logout Layers in an OIDC System

| Layer | Action | Scope |
| --- | --- | --- |
| **RP local logout** | Clears the application's session/cookie and SecurityContext | Only the current RP |
| **OP logout** | OP terminates the user's SSO session | Session at the OP; affects subsequent SSO |
| **RP logout notification** | OP notifies other RPs that they need to end their corresponding sessions | RPs that implement a compatible front-channel/back-channel/session-management mechanism |

An RP-Initiated Logout operation typically coordinates both local logout and an OP logout request. However, these layers have independent mechanisms and outcomes. Clearing a session at the RP does not automatically clear the OP session; an OP logout also does not automatically guarantee that every other RP has processed the notification; logout does not mean all access tokens have been revoked.

## 2. RP-Initiated Logout Flow

The RP requests logout by navigating the User Agent (usually a browser) to the Logout Endpoint published by the OP. The OP validates the request, processes the session, and may navigate the browser back to the RP.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as User / Browser
    participant RP as Spring Boot RP
    participant OP as Spring Authorization Server / OP
    participant Other as Other RP
    U->>RP: POST /logout (CSRF token)
    RP->>RP: Invalidate local session, clear SecurityContext
    RP->>RP: Build logout request from stored ID Token
    RP-->>U: Redirect to end_session_endpoint
    U->>OP: GET/POST logout with id_token_hint, redirect URI, state
    OP->>OP: Validate ID Token hint and client/redirect
    OP->>U: Display confirmation if needed
    U->>OP: Confirm logout
    OP->>OP: Terminate OP session
    OP->>Other: Logout notification if a supported mechanism is configured
    OP-->>U: Redirect to post_logout_redirect_uri + state
    U->>RP: Post-logout callback
    RP->>RP: Verify state and display logged-out page
~~~

The diagram illustrates a flow with a confirmation step; the OP may skip prompting again if the ID Token hint accurately identifies the current session and the OP's policy allows it. The RP may perform local logout before redirecting or coordinate the timing of local logout based on the desired product experience. You must have handling for cases where the browser closes, the network fails, the OP rejects the logout, or notifications do not arrive.

## 3. Discovery: Finding the Logout Endpoint via end_session_endpoint

### 3.1. Do Not Guess the Logout URL

The RP needs to know the Logout Endpoint URL. According to RP-Initiated Logout 1.0, when the OP supports Discovery, the OpenID Provider Configuration must publish the metadata:

~~~json
{
  "issuer": "https://auth.example.com",
  "authorization_endpoint": "https://auth.example.com/oauth2/authorize",
  "token_endpoint": "https://auth.example.com/oauth2/token",
  "jwks_uri": "https://auth.example.com/oauth2/jwks",
  "end_session_endpoint": "https://auth.example.com/connect/logout"
}
~~~

This is an illustrative response. `end_session_endpoint` is an HTTPS URL at the OP that receives logout requests. The RP obtains this value from a discovery document whose issuer/TLS has been verified, or from another trusted configuration channel permitted by the specification.

Do not manually append `/logout` or `/connect/logout` to the issuer. The endpoint path can change depending on the OP's configuration.

### 3.2. If the Metadata Does Not Contain end_session_endpoint

If the OP does not publish `end_session_endpoint`:
- The RP must not assume that the OP supports RP-Initiated Logout.
- The RP can still terminate the local session.
- If an organization configures the endpoint via an out-of-band channel outside Discovery, it must verify that the endpoint belongs to the correct OP and has a compatible contract.
- Do not redirect to a logout URL supplied by a query parameter or untrusted data.

Discovery metadata may contain other endpoints for authorization, token, UserInfo, or revocation; they do not replace the Logout Endpoint.

## 4. Parameters of an RP-Initiated Logout Request

RP-Initiated Logout 1.0 defines the following parameters:

| Parameter | Requirement Level | Purpose |
| --- | --- | --- |
| `id_token_hint` | **RECOMMENDED** | ID Token previously issued by the OP to the RP, serving as a hint to identify the user/session and the client requesting logout |
| `logout_hint` | OPTIONAL | Hint about the user/session; semantics are determined by the OP |
| `client_id` | OPTIONAL | OAuth Client Identifier; can identify the client when no ID Token hint is sent |
| `post_logout_redirect_uri` | OPTIONAL | URI to which the browser will be redirected after logout |
| `state` | OPTIONAL | Opaque value for the RP to correlate the logout request with the callback |
| `ui_locales` | OPTIONAL | Preferred UI languages for the user, per BCP 47 |

`id_token_hint` is an important recommendation because it helps the OP know which RP and which subject/session are requesting logout. If both `client_id` and `id_token_hint` are present, the OP **MUST** verify that the client ID matches the client used when that ID Token was issued.

`logout_hint` is not proof of authentication. For example, an email, phone number, username, or session identifier passed by the RP is only a hint; the OP must not treat it as a verified ID Token.

### 4.1. id_token_hint

An ID Token hint is an ID Token previously issued by the OP to the RP. The OP must verify that it is the issuer of that token. The OP should accept the ID Token even if `exp` has passed if the token's `aud` and/or `sid` indicate that the RP has a current or recent session at the OP.

Logout should not be rejected merely because the ID Token hint is expired. The ID Token is used as a **hint to look up the session**, not as a fresh access token to call an API. However, if `sid` does not match a current or recent session of the RP at the OP, the OP should treat the request as suspicious and may reject processing it.

If the ID Token's `aud` contains multiple values, the OP must still identify the exact client to which the token was issued. If the request also sends `client_id`, the two pieces of information must be consistent.

### 4.2. post_logout_redirect_uri

This is the URI to which the RP asks the OP to redirect the browser after logout completes. The URI:
- Should use HTTPS.
- Must be pre-registered with the OP via `post_logout_redirect_uris` or another registration mechanism.
- Must match a registered URI **exactly**; do not use wildcard domains or prefix matching.
- May include port, path, and query according to the rules of the specification.
- May use another scheme for a native application callback if supported by the OP and that URI is registered.

HTTP can only be accepted for confidential clients when the OP allows HTTP RP URIs; HTTPS remains the recommended choice in production.

If `post_logout_redirect_uri` is sent without `id_token_hint`, the OP **MUST NOT** redirect back to the RP unless the OP has another way to confirm the validity of the redirect target. This prevents attackers from using the Logout Endpoint as an open redirect.

### 4.3. state

`state` is an opaque string generated by the RP to correlate the request with the callback. You should:
- Generate a random value with sufficient entropy.
- Store the association between `state` and the browser session/logout transaction.
- Make it single-use and time-limited.
- Perform an exact comparison when the OP returns `state`.
- Not include access tokens, refresh tokens, ID Tokens, or PII data.

Do not use `state` as a replacement for validating `post_logout_redirect_uri`. `state` protects transaction correlation; the redirect allowlist protects the navigation target.

## 5. Sending a Logout Request via GET or POST

The OP must support both HTTP GET and POST at the Logout Endpoint. The RP may choose either one:
- GET: parameters are serialized as a query string.
- POST: parameters are serialized using form encoding, typically `application/x-www-form-urlencoded`.

### 5.1. GET Example

~~~http
GET /connect/logout?id_token_hint=SIGNED_ID_TOKEN&post_logout_redirect_uri=https%3A%2F%2Fportal.example.com%2Flogged-out&state=OPAQUE_STATE HTTP/1.1
Host: auth.example.com
~~~

The browser navigates to the URL constructed from `end_session_endpoint` and the URL-encoded parameters.

### 5.2. POST Example

~~~http
POST /connect/logout HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

id_token_hint=SIGNED_ID_TOKEN&post_logout_redirect_uri=https%3A%2F%2Fportal.example.com%2Flogged-out&state=OPAQUE_STATE
~~~

POST can reduce placing the ID Token hint in query strings, access logs, and browser history, though it does not turn the ID Token into an unconditionally safe secret. Form bodies can still appear in logs if the system logs request bodies.

### 5.3. Choosing GET vs. POST

| Criterion | GET | POST |
| --- | --- | --- |
| Simple redirect compatibility | Good | Requires a form-post strategy or form page |
| Parameters | Query string | Form body |
| Browser history/access logs | Risk of logging query containing hint | Typically less exposed in URLs |
| CSRF | Top-level navigation still needs an appropriate logout policy | Requires controlling form submission and origin/CSRF policy |
| Specification | OP MUST support | OP MUST support |

Whichever approach is chosen, the RP must use the exact endpoint from metadata and must not treat the redirect response as proof that every session/token in the system has been destroyed.

## 6. How Does the OP Process a Logout Request?

### 6.1. Validating id_token_hint

When `id_token_hint` is present, the OP:
1. Checks the format and verifies the signature/issuer using keys managed by the OP itself.
2. Confirms that the token was issued by the OP.
3. Identifies the client from `aud` and related client information.
4. If the request includes `client_id`, verifies that it matches the client that was issued the ID Token.
5. Identifies the session via `sid` and/or existing user/client session relationships.
6. Checks whether the request relates to a current or recent session.
7. If it cannot be securely associated, treats the request as suspicious according to the specification and policy.

The ID Token hint may be expired. The OP should accept an expired token if the RP named in `aud` and/or `sid` has a current or recent session at the OP. Do not mechanically apply a rule of "always reject logout if the ID Token is expired."

### 6.2. User Confirmation

The OP should ask the End-User whether they want to log out of the OP. The OP **MUST** ask if:
- The request has no `id_token_hint`; or
- The submitted ID Token does not belong to the current OP session with the RP and/or the currently logged-in user.

If the user responds affirmatively, the OP must perform the logout. Confirmation is especially useful when there is insufficient evidence to identify the RP/subject/session requesting logout, preventing forged requests from causing mass logouts or denial of service.

If the user declines, the OP does not perform the OP logout for that request. If the RP already terminated its local session before redirecting, the user remains logged out of the initiating RP; the RP should not automatically create a new session merely because the OP retained the SSO session.

### 6.3. Idempotent Logout

RP-Initiated Logout is designed to be idempotent. If the OP no longer considers the End-User logged in with the requesting RP, sending a logout request from the RP is not in itself a protocol error. The OP may display an appropriate page or proceed according to policy.

However, if request validation fails, the OP must not use the invalid data and **MUST NOT** perform a post-logout redirect back to the RP. Do not turn idempotency into an excuse to accept arbitrary redirect URIs.

### 6.4. Terminating the OP Session

When logout is approved:
- The OP terminates the corresponding login session according to the OP's session model.
- Clears/expires cookies and server-side SecurityContext/session according to the implementation.
- Executes logout notifications for logged-in RPs if the OP/RPs support a corresponding mechanism.
- Only after processing notifications according to the rules does the OP perform the post-logout redirect, provided the request is valid and the redirect has been verified.

The OP clearing the browser session does not mean already-issued JWT access tokens vanish or that every resource server immediately rejects those tokens. Token revocation and session logout are different mechanisms.

## 7. Protecting Post-Logout Redirects

### 7.1. Pre-Registering Redirect URIs

A client registration may contain the list:

~~~json
{
  "client_id": "portal-web",
  "post_logout_redirect_uris": [
    "https://portal.example.com/logged-out",
    "https://portal.example.com/session/ended"
  ]
}
~~~

When receiving a request:

~~~text
requested = post_logout_redirect_uri
registered = client.post_logout_redirect_uris

if requested exactly matches one registered URI:
    allow post-logout redirect
else:
    reject request and do not redirect to RP
~~~

Do not allow:
- `https://portal.example.com.attacker.example/` just because the string starts with a valid domain.
- `https://portal.example.com@attacker.example/`.
- Wildcards like `https://*.example.com/logout` without a specific, secure validation/registration mechanism.
- HTTP redirect targets not permitted by policy.
- URIs overridden by another query parameter or cookie.

### 7.2. Do Not Redirect Without Client Evidence

If `post_logout_redirect_uri` is present without `id_token_hint`, the OP must have another mechanism to confirm that the redirect target belongs to the client actually making the request. For example, a `client_id` verified through an appropriate flow together with registered redirect URIs may serve as input to the decision, but the OP's legitimacy verification requirement must not be bypassed.

### 7.3. Checking state at the RP

When the browser returns to `post_logout_redirect_uri`, the OP returns the original `state` value if the request included one:
- The RP reads `state`.
- Matches it against the pending transaction in the server-side session/cookie.
- Rejects callbacks without a matching state or with an already-used/expired state.
- Does not use callback query parameters to restore an access token or create a new login session.
- Deletes the transaction after processing.

The logged-out page should be a simple informational page that does not automatically log the user back in or redirect to an arbitrary URL supplied by the callback.

## 8. Local Logout at the Relying Party with Spring Security

### 8.1. What Does Spring Security Local Logout Do?

For Servlet applications, Spring Security provides a Logout Filter. Upon a valid POST logout, the default handlers typically:
- Invalidate the HTTP session.
- Clear `SecurityContextHolder` and `SecurityContextRepository`.
- Clean up remember-me authentication.
- Clear the CSRF token.
- Publish `LogoutSuccessEvent`.
- Forward to the logout success handler.

When CSRF protection is enabled, the RP should use POST logout with a CSRF token. A GET logout by default can display a confirmation page to obtain a CSRF token; do not arbitrarily turn GET into a state-changing operation without considering CSRF.

### 8.2. Integrating OidcClientInitiatedLogoutSuccessHandler

Spring Security OAuth2 Client provides `OidcClientInitiatedLogoutSuccessHandler`. This handler uses `ClientRegistrationRepository`, OIDC login information (including the ID Token), and provider metadata to redirect to `end_session_endpoint` when the provider publishes that endpoint.

Servlet configuration example:

~~~java
@Bean
LogoutSuccessHandler oidcLogoutSuccessHandler(
        ClientRegistrationRepository clientRegistrationRepository) {

    OidcClientInitiatedLogoutSuccessHandler handler =
            new OidcClientInitiatedLogoutSuccessHandler(
                    clientRegistrationRepository);

    // This URI must be pre-registered with the OpenID Provider.
    handler.setPostLogoutRedirectUri("{baseUrl}/logged-out");

    return handler;
}

@Bean
SecurityFilterChain applicationSecurity(
        HttpSecurity http,
        LogoutSuccessHandler oidcLogoutSuccessHandler) throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        )
        .oauth2Login(Customizer.withDefaults())
        .logout(logout -> logout
            .logoutSuccessHandler(oidcLogoutSuccessHandler)
        );

    return http.build();
}
~~~

`{baseUrl}` is a placeholder supported by the handler that is replaced with the application's base URL at processing time. If using the `/logged-out` path, the full URI must be registered with the OP, for example `https://portal.example.com/logged-out`.

The handler performs Spring Security local logout and then redirects the browser to the OP. The RP should test with a `ClientRegistration` whose provider metadata contains `end_session_endpoint`. If the OP does not publish the endpoint or the `Authentication` is not an OIDC login, the application needs to configure an appropriate logout fallback.

### 8.3. GET Redirect vs. POST Form

`OidcClientInitiatedLogoutSuccessHandler` uses an HTTP GET redirect to the OP by default. If you want to send the request via a POST form, Spring Security provides `FormPostRedirectStrategy`:

~~~java
@Bean
LogoutSuccessHandler oidcLogoutSuccessHandler(
        ClientRegistrationRepository registrations) {

    OidcClientInitiatedLogoutSuccessHandler handler =
            new OidcClientInitiatedLogoutSuccessHandler(registrations);

    handler.setPostLogoutRedirectUri("{baseUrl}/logged-out");
    handler.setRedirectStrategy(new FormPostRedirectStrategy());

    return handler;
}
~~~

A POST form can be suitable when you do not want the ID Token hint in the query string. You need to test CSP, browser behavior, OP support for POST, and verify that the redirect page/form is generated properly. Do not hand-write an HTML form that accepts an endpoint from untrusted input.

### 8.4. Retaining the ID Token Long Enough for Logout

The RP needs to keep the ID Token in the Authentication/session for the login lifecycle so the handler can send `id_token_hint`. Do not store the ID Token in internal URLs, local storage, or logs solely to support logout. If the application clears the entire Authentication before building the logout request, the handler may no longer have an ID Token to send; let Spring's Logout Filter orchestrate the success handler or design a flow with secure storage.

## 9. Enabling the OIDC Logout Endpoint in Spring Authorization Server

### 9.1. OIDC Must Be Enabled

Spring Authorization Server supports the OIDC Logout Endpoint via `OidcLogoutEndpointConfigurer`. OIDC is not enabled merely because OAuth Authorization Server endpoints are running; you must configure `oidc(...)` on `OAuth2AuthorizationServerConfigurer`.

SAS 1.5.x example:

~~~java
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .oidc(oidc -> oidc
                .logoutEndpoint(Customizer.withDefaults())
            )
        )
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        );

    return http.build();
}
~~~

This is the Authorization Server filter chain configuration; a real application also needs a login chain, client repository, authorization service, issuer, JWK source, and other foundational beans. The OIDC Logout Endpoint is handled by SAS's filter, not a custom controller that accepts arbitrary redirect URLs.

### 9.2. Configuring the Path in AuthorizationServerSettings

SAS uses `/connect/logout` by default for the OIDC Logout Endpoint. It can be changed:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .oidcLogoutEndpoint("/connect/v1/logout")
            .build();
}
~~~

When changing the path, the `end_session_endpoint` discovery metadata must reflect the corresponding public URL. RPs must not continue using the old path. With a reverse proxy, check the external scheme/host/path so that metadata does not return an internal address.

### 9.3. What Extension Points Does OidcLogoutEndpointConfigurer Have?

`OidcLogoutEndpointConfigurer` allows customizing:
- `logoutRequestConverter` / `logoutRequestConverters`: reads the HTTP request and creates `OidcLogoutAuthenticationToken`.
- `authenticationProvider` / `authenticationProviders`: authenticates the logout request and validates parameters.
- `logoutResponseHandler`: handles successful logout.
- `errorResponseHandler`: handles authentication errors and returns an OAuth/OIDC error response.

SAS provides by default:
- `OidcLogoutAuthenticationConverter`.
- `OidcLogoutAuthenticationProvider`.
- `OidcLogoutAuthenticationSuccessHandler`.
- An internal error handler tied to `OAuth2Error`.

Do not replace the default converter/provider/handler just to change a small detail if a more appropriate extension point exists. Customizations must preserve required validations, especially checks on `id_token_hint`, client, and redirect URI.

### 9.4. Custom Validation for post_logout_redirect_uri

SAS has a default validator `OidcLogoutAuthenticationValidator` to check logout parameters, including `post_logout_redirect_uri`. If a custom policy is needed, `OidcLogoutAuthenticationProvider` lets you configure a `Consumer<OidcLogoutAuthenticationContext>` via `setAuthenticationValidator(...)`.

A custom validator should:
1. Obtain the client/session context from the verified authentication token.
2. Compare the redirect URI strictly against the registered list.
3. Check the condition of having `id_token_hint` or other evidence when redirecting.
4. Throw `OAuth2AuthenticationException` if validation fails.
5. Never redirect to an unverified URL.

Do not write a validator that checks domains only with `startsWith` or a loose regex. If replacing the default validator, preserve all security rules from the specification and test open redirect scenarios.

## 10. SessionRegistry in Spring Authorization Server

### 10.1. Why Does the Logout Endpoint Need SessionRegistry?

SAS uses `SessionRegistry` to track authenticated user sessions. `OidcLogoutAuthenticationProvider` uses the registry to locate the `SessionInformation` associated with the End-User requesting logout.

When OIDC is enabled:
- If the application does not register a `SessionRegistry` bean, SAS may use the default `SessionRegistryImpl` implementation.
- If you register your own `SessionRegistryImpl`, you should also register `HttpSessionEventPublisher` to publish session lifecycle events such as `SessionDestroyedEvent` and help the registry remove destroyed sessions.
- If Spring Security Concurrent Session Control also uses the registry, share a single bean so session state remains consistent.

Example:

~~~java
@Bean
SessionRegistry sessionRegistry() {
    return new SessionRegistryImpl();
}

@Bean
HttpSessionEventPublisher httpSessionEventPublisher() {
    return new HttpSessionEventPublisher();
}
~~~

Do not create two different `SessionRegistry` instances for the same system and expect the logout endpoint to always find the session registered by the Authorization Endpoint.

### 10.2. Clusters and Distributed Sessions

In multi-instance deployments:
- The session store and registry must have visibility into sessions across nodes.
- Session destruction events must be propagated or synchronized.
- Do not use an independent per-node in-memory registry if requests can hit different nodes.
- Test logout when the authorization request runs on node A but the logout request runs on node B.
- Ensure reverse proxies/load balancers do not corrupt session cookies or the issuer.

A single-node in-memory `SessionRegistry` may suit a demo, but it does not solve distributed session tracking on its own.

## 11. How RP-Initiated Logout Differs from Front-Channel and Back-Channel Logout

RP-Initiated Logout is **an RP requesting OP logout** by navigating the browser to the Logout Endpoint. The OP notifying other RPs is a separate coordination step.

| Mechanism | Who Initiates? | Notification Channel | RP Handling |
| --- | --- | --- | --- |
| RP-Initiated Logout | RP | Browser redirect to OP | RP asks OP to end the session |
| Front-Channel Logout | OP | Browser/iframe navigation to RP | RP receives logout via browser context |
| Back-Channel Logout | OP | Server-to-server HTTP | RP receives a Logout Token and ends related sessions |
| Session Management | RP checks OP status via browser | Browser communication/iframe | Detects OP session changes via its own mechanism |
| Local logout | User or application | Internal to RP | Clears session only at the current RP |

### 11.1. Front-Channel Logout

The OP can open the front-channel logout URIs of RPs through the browser. This approach depends on browser, iframe, and cookie policies. Third-party cookie blocking, SameSite, and browser privacy protections can affect whether the RP finds the right session.

An RP should not treat a mere iframe request as strong proof that a user has newly authenticated. The front-channel endpoint must identify the appropriate session via the registered mechanism and handle requests idempotently.

### 11.2. Back-Channel Logout

Back-channel logout is a server-to-server notification from the OP to the RP. The OP sends a Logout Token (JWT) per Back-Channel Logout 1.0; the RP verifies the signature, issuer, audience, timestamps, and event claim before terminating the corresponding sessions.

A Logout Token is not an ID Token hint:
- `id_token_hint` goes from the RP to the OP in an RP-Initiated Logout Request.
- A Logout Token goes from the OP to the RP to notify of logout.
- Never use one token type in place of the other.

If supporting back-channel logout, the RP needs mapping from `sid` and/or `sub` to local sessions, replay protection, and handling for duplicate notifications. Enabling the RP-Initiated Logout Endpoint in SAS **does not automatically prove** that the system has fully implemented Front-Channel or Back-Channel Logout.

## 12. Logout Does Not Mean Token Revocation

The Logout Endpoint primarily handles login sessions. OAuth Token Revocation (RFC 7009) is a separate endpoint/protocol to revoke access tokens or refresh tokens according to the OP's capabilities.

| Resource | RP local logout | OP session logout | Token revocation |
| --- | --- | --- | --- |
| RP session cookie | Can be cleared | Not necessarily | No |
| OP SSO cookie/session | No | Yes | Not necessarily |
| Issued JWT access token | Not automatically invalidated | Not automatically invalidated immediately if RS only checks signature/exp | Depends on RS/token format and revocation support |
| Refresh token | Not automatically revoked | Does not automatically imply revocation | Can be revoked per endpoint/policy |
| Sessions at other RPs | No | Only when a notification mechanism is supported and RPs handle it | Not automatic |
| SecurityContext at current RP | Yes | Not directly | No |

If a business requirement states "once the user logs out, tokens can no longer be used," you also need to design:
- Revocation of the corresponding refresh token or authorization.
- Short access token lifetimes, introspection, or revocation-aware resource servers when needed.
- Logout notifications so RPs clear their local sessions.
- Policies for handling issued tokens, caches, and distributed sessions.
- Auditing to know which components a logout request has terminated.

Do not promise "complete global logout" based solely on a successful redirect to the OP.

## 13. Security and Common Implementation Pitfalls

| Risk | Cause | Mitigation |
| --- | --- | --- |
| Open redirect | OP accepts an arbitrary `post_logout_redirect_uri` | Exact match against registered URIs; fail closed |
| Logout CSRF | Local GET logout endpoint or form missing CSRF protection | POST with CSRF token at RP; appropriate policy at OP |
| Client mix-up | `client_id` does not match ID Token hint | If both are present, enforce match verification |
| Token hint misuse | Using an ID Token from another issuer/client | OP verifies issuer, audience/client, and session |
| ID Token hint exposure | Query URL written to access logs/history | POST form where appropriate, redact logs, do not send URLs to analytics |
| Replay | Replaying callback/state or logout transaction | High-entropy, one-time, expiring state; idempotent handling |
| Session confusion | ID Token `sid` does not belong to current session | Check session registry; treat as suspect request |
| Cross-tenant logout | Same subject string but different issuer/tenant | Bind issuer + subject + session + client |
| Fake `logout_hint` | Trusting email/username as proof | Treat `logout_hint` only as a hint, not a credential |
| Incomplete global logout | Clearing only the current RP | Design separate notification/revocation |
| Stale `SessionRegistry` | Registry does not receive session-destroyed events | `HttpSessionEventPublisher` or distributed session store |
| Host/issuer poisoning | Inferring endpoint from untrusted Host/forwarded headers | Configure a fixed public issuer and trusted proxy |

### 13.1. ID Token Hint May Appear in URLs

When using GET, `id_token_hint` can appear in the query string. JWTs often contain user-identifying claims and may end up in:
- Reverse proxy access logs.
- Browser history.
- APM/tracing.
- Referrer headers if misconfigured.
- URL analytics systems.

A POST form redirect can be used if the OP supports it. Whether using GET or POST, still redact logs and avoid storing raw request bodies/queries containing tokens. Do not treat an ID Token hint as a secret equivalent to an access token, yet still protect it as a sensitive credential.

### 13.2. Logout Requests Without id_token_hint

A request without `id_token_hint` could log out the wrong user if the OP does not ask for confirmation. The specification requires the OP to prompt the user for confirmation when the hint is missing. If the OP cannot establish client/redirect legitimacy, do not redirect back to the RP.

### 13.3. Do Not Use post_logout_redirect_uri as an Arbitrary returnUrl

Do not take `post_logout_redirect_uri` directly from a parameter sent by the user to local `/logout` and forward it to the OP. The RP should use a pre-configured and pre-registered URI. If multiple landing pages must be supported, select from an internal allowlist.

## 14. RP-Initiated Logout Test Matrix

### 14.1. Discovery and Endpoint Tests

| Test | Action | Expected |
| --- | --- | --- |
| Discovery metadata | GET OP Configuration | Contains `end_session_endpoint` when OP supports logout + Discovery |
| HTTPS endpoint | Read `end_session_endpoint` | URL uses HTTPS |
| OIDC disabled | Disable OIDC in SAS | Does not advertise OIDC logout endpoint as active |
| Endpoint path | Configure custom `oidcLogoutEndpoint` | Metadata and actual route match |
| GET request | Send valid GET logout | OP processes it |
| POST request | Send valid POST form | OP processes it |
| Unknown endpoint | Use old path after changing settings | Do not assume old route still works |

### 14.2. Parameter and Redirect Tests

| Test | Input | Expected |
| --- | --- | --- |
| Valid hint | ID Token issued by OP, valid client/session | Identifies the correct session |
| Wrong issuer | Hint from another OP | Rejects/does not log out based on the hint |
| Expired but recent | Expired hint but session is current/recent | OP may accept per specification |
| Stale `sid` | `sid` does not match current/recent session | Treated as suspect, may reject |
| Client mismatch | `client_id` differs from the client issued the hint | Rejects |
| Registered redirect | Exact-match URI | Can redirect after logout |
| Prefix lookalike | Valid domain plus attacker suffix | Rejects |
| Unregistered redirect | Unregistered URI | Rejects and does not redirect |
| No hint + redirect | No `id_token_hint` and no other verification | Does not redirect |
| State | Valid random state | Returns the exact value |
| State replay | Callback reuses an already consumed state | RP rejects callback |
| `logout_hint` only | Sends email/username as hint | Not treated as authentication proof |
| Idempotency | Logout when OP session has already ended | Does not treat absence of session as a protocol error |

### 14.3. Spring Security and Session Tests

- POST local logout with CSRF token terminates the RP session and clears `SecurityContext`.
- Logout success handler retrieves the correct ID Token from the OIDC principal before redirecting.
- Without OIDC Authentication, the RP uses the fallback local logout URL.
- The handler uses the discovered `end_session_endpoint` rather than concatenating paths manually.
- The handler's `post_logout_redirect_uri` matches the URI registered at the OP exactly.
- `SessionRegistry` finds the correct session when the logout request executes on a different node.
- `HttpSessionEventPublisher` updates `SessionRegistry` when a session is destroyed.
- Duplicate logout notifications do not cause errors or mistakenly delete other sessions.
- Access token/refresh token lifecycle is tested separately from session logout.
- Logs do not contain ID Token hints, raw Logout Tokens, refresh tokens, or PII.

## 15. Case Study

An organization has an OP at `https://auth.example.com` and two RPs:
- Portal: `portal-web`.
- Admin Console: `admin-console`.

Both RPs share the same OP session. Portal currently holds an ID Token with `iss` matching the OP, `aud` set to `portal-web`, and `sid` representing the current SSO session.

Portal logs out with the request:

~~~http
GET /connect/logout?id_token_hint=PORTAL_ID_TOKEN&post_logout_redirect_uri=https%3A%2F%2Fportal.example.com%2Flogged-out&state=STATE_123 HTTP/1.1
Host: auth.example.com
~~~

The OP observes:
- `post_logout_redirect_uri` is registered for `portal-web`.
- Session `sid` is still active.
- Admin Console also has a session for the same user.
- Portal's refresh token is still valid.
- The OP has not enabled Back-Channel Logout.

Analyze the following:

1. From what information does the OP identify the client and the logout session?
2. Must the OP prompt the user to confirm OP logout? Why or why not?
3. What should the OP do with the sessions of Portal and Admin Console when Back-Channel Logout is not enabled?
4. Is the still-valid refresh token automatically revoked when the OP session is deleted?
5. If Portal also sends `client_id=admin-console`, what is the outcome?
6. If the redirect URI is changed to `https://portal.example.com.attacker.test/`, how must the OP handle it?
7. If the ID Token hint is expired but `sid` still points to a recent session, how can the OP handle it?
8. Propose additional architecture to meet the requirement of logging out all RPs and revoking refresh tokens.
9. Write a test proving that callback `state` is verified and cannot be reused.
10. Describe how to configure `OidcClientInitiatedLogoutSuccessHandler` at Portal.

**Hint:** `id_token_hint` identifies the token issued by the OP to Portal; `sid` helps correlate the session. If the token hint accurately identifies the current session, the OP is not required to ask for confirmation in all cases. The logout endpoint must terminate the OP session according to policy, while notifications to Admin Console require a separate mechanism; refresh tokens are not automatically revoked solely due to browser session logout. Client mismatches and non-matching redirect URIs must be rejected.

## 16. Production Deployment Checklist

1. **Discovery:** OP publishes HTTPS `end_session_endpoint` in metadata when supporting RP-Initiated Logout.
2. **Client registration:** manage `post_logout_redirect_uris` per client; exact match.
3. **RP logout:** local POST logout with CSRF protection, clearing session and SecurityContext.
4. **ID Token hint:** send the ID Token issued by the right OP for the RP; never construct hints from user input.
5. **Client binding:** if both `client_id` and `id_token_hint` are present, verify they match.
6. **Session lookup:** use `sid`/session registry to locate current or recent sessions; handle expired token hints per specification.
7. **Confirmation:** prompt the user when the hint is missing or does not belong to the current session as required by the spec.
8. **Redirect:** redirect only to registered URIs; do not redirect if validation fails or legitimacy cannot be established.
9. **State:** high entropy, one-time, timeout, and callback verification.
10. **GET/POST:** OP supports both; RP chooses GET/POST based on privacy, compatibility, and browser behavior.
11. **SAS:** enable OIDC and configure `OidcLogoutEndpointConfigurer`; do not confuse OAuth logout with the OIDC endpoint.
12. **SessionRegistry:** share the registry with concurrent session control; add `HttpSessionEventPublisher` when using `SessionRegistryImpl`.
13. **Cluster:** synchronize session store/registry across nodes.
14. **Notifications:** implement Front-Channel/Back-Channel Logout if multi-RP single logout is required; test each mechanism separately.
15. **Token lifecycle:** revoke refresh/access tokens via separate policies if required; do not assume session logout revokes tokens automatically.
16. **Observability:** log client/session correlation and outcome codes, redacting tokens/PII.
17. **Testing:** test issuer/client/sid mismatches, redirect abuse, expired hints, state replay, no-session idempotency, and distributed sessions.
18. **Incident response:** maintain procedures for session compromise, token revocation, session invalidation, and RP notification.

## 17. Standards and Spring References to Consult

- [OpenID Connect RP-Initiated Logout 1.0 — Final](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): logout request, parameters, discovery metadata, redirect validation, and security considerations.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): OpenID Provider Configuration and endpoint metadata.
- [OpenID Connect Session Management 1.0](https://openid.net/specs/openid-connect-session-1_0.html): session state and coordinated logout.
- [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html): logout notifications via browser.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): Logout Token and server-to-server notifications.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html): revoking access/refresh tokens, distinct from session logout.
- [Spring Authorization Server 1.5.x — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OidcLogoutEndpointConfigurer`, converter/provider, and logout response/error handlers.
- [Spring Authorization Server 1.5.x — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): `AuthorizationServerSettings` and the `/connect/logout` endpoint.
- [Spring Authorization Server — SessionRegistry](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): registering authenticated sessions, logout lookup, and `HttpSessionEventPublisher`.
- [Spring Security — OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html): `OidcClientInitiatedLogoutSuccessHandler` and local logout integration.
- [Spring Security — Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): Logout Filter, CSRF, session invalidation, and `LogoutHandler`.

**Key Takeaway:** RP-Initiated Logout is a request from an RP asking the OP to terminate the SSO session via `end_session_endpoint`. `id_token_hint` helps the OP identify the right issuer/client/session; `post_logout_redirect_uri` is only used when verified and matching a registered URI exactly; `state` correlates the callback with the RP's transaction. In Spring Security, `OidcClientInitiatedLogoutSuccessHandler` coordinates local logout with redirecting to the OP. In Spring Authorization Server, `OidcLogoutEndpointConfigurer` processes logout requests and `SessionRegistry` helps locate the corresponding session. Session logout does not automatically revoke all access/refresh tokens or log out all other RPs; separate token revocation and Front-Channel/Back-Channel Logout must be designed when business requirements call for them.
