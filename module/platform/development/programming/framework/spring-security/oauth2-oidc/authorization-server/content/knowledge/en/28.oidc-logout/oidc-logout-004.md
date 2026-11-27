# Logout Confirmation and Handling Insufficient Requests

## 1. Context and Goals

In an **OAuth 2.0/OpenID Connect Authorization Server** system using **Spring Security**, **Spring Authorization Server**, and **Spring Boot**, a user can log into multiple applications (Relying Parties — RPs) through a single OpenID Provider (OP). When the user clicks Logout in one application, the RP can redirect the browser to the OP's Logout Endpoint to request terminating the central login session. This mechanism is called **RP-Initiated Logout**.

A logout request typically carries `id_token_hint`, `post_logout_redirect_uri`, `client_id`, and `state`. However, not every request contains all of those parameters. Some older RPs do not send an ID Token; some users open the logout URL directly; some requests carry an unregistered redirect URI; and in some cases the ID Token belongs to a different session or the user currently logged in at the OP cannot be determined.

Running example: a user logs into `customer-portal` and `billing-console` via `https://auth.example.com`. When clicking Logout in the portal, the application sends `id_token_hint` along with `post_logout_redirect_uri`. Meanwhile, a kiosk device opens `/connect/logout` directly without an `id_token_hint`. The OP must distinguish between these two scenarios, avoid terminating another user's session merely because a URL was invoked, and still give the user the option to perform central logout when the request lacks information.

After this lesson, you will be able to:

1. Explain the RP-Initiated Logout flow and the role of the Logout Endpoint.
2. Distinguish required, recommended, and optional parameters in OIDC RP-Initiated Logout 1.0.
3. Determine when the OP must ask the user to confirm logout.
4. Handle requests missing `id_token_hint`, `client_id`, `post_logout_redirect_uri`, or `state`.
5. Validate the ID Token's issuer, audience, client binding, session ID, and session state.
6. Verify `post_logout_redirect_uri` via exact match against registered URIs.
7. Design a confirmation page, an approve/decline flow, and a secure one-time ticket.
8. Customize `OidcLogoutEndpointConfigurer`, `OidcLogoutAuthenticationProvider`, the validator, and success/error handlers in Spring Authorization Server.
9. Distinguish OP session logout from revoking access tokens/refresh tokens.
10. Test scenarios involving missing data, invalid redirects, session mismatches, and repeated requests.

**Version Scope:** Examples use Spring Authorization Server 1.5.x (referencing API 1.5.8), Spring Security 6.x, and the Servlet stack. `OidcLogoutAuthenticationProvider.setAuthenticationValidator(...)` has been available since Spring Authorization Server 1.4. If using an older version, check the corresponding API or upgrade before applying the custom validator examples.

## 2. What Is RP-Initiated Logout?

### 2.1. Who Requests Logout?

The RP is the application the user is currently using, such as `customer-portal`. The OP is the Authorization Server that authenticated the user, such as `https://auth.example.com`. RP-Initiated Logout allows the RP to navigate the User Agent to the OP's Logout Endpoint to request terminating the central login session.

The RP normally retrieves the Logout Endpoint from OpenID Provider Discovery metadata via the `end_session_endpoint` field. If the OP supports RP-Initiated Logout and Discovery, the metadata must advertise this endpoint over HTTPS.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as End-User
    participant RP as customer-portal
    participant OP as OpenID Provider
    participant S as SessionRegistry
    U->>RP: Click Logout
    RP->>RP: End or mark local session
    RP-->>U: Redirect to end_session_endpoint
    U->>OP: Logout request + id_token_hint
    OP->>OP: Verify hint, client, and session
    OP->>U: Is OP logout confirmation needed?
    U->>OP: Approve
    OP->>S: Look up session and end OP session
    OP-->>RP: Logout notification if mechanism registered
    OP-->>U: Completion page or valid redirect to RP
~~~

The RP may log out locally before redirecting to the OP or wait for a logout notification from the OP. Each choice has a trade-off: if the RP logs out locally first, the user is already out of the RP even if they decline OP logout; if the RP waits for a notification, an unreliable notification mechanism could leave the RP local session active. The design must clearly communicate to the user which logout state has completed.

### 2.2. Logout Does Not Mean Revoking All Tokens

RP-Initiated Logout primarily terminates the OP login session and coordinates logout notifications to RPs that registered a corresponding mechanism. Logging out does not automatically ensure that all issued access tokens or refresh tokens are immediately revoked.

If the system needs to revoke tokens, a separate revocation/authorization policy must be used, such as:

- Revoking the corresponding refresh token or authorization.
- Marking the session/authorization ended so introspection returns `active=false`.
- Using back-channel logout so RPs receive notifications and end local sessions.
- Applying short TTLs, token family revocation, or session-checking policies at the Resource Server.

Do not display a "You have logged out" page if only the OP cookie was deleted while refresh tokens or sessions in another system remain active by design.

## 3. Logout Request Parameters

OIDC RP-Initiated Logout 1.0 defines the following parameters:

| Parameter | Level | Role | Handling |
| --- | --- | --- | --- |
| `id_token_hint` | RECOMMENDED | ID Token previously issued by the OP to the RP; hints at the user and RP session to log out. | Verify the OP is the issuer, check client/audience, and correlate with a current or recent session. |
| `client_id` | OPTIONAL | Client Identifier registered at the OP. | If present alongside `id_token_hint`, must match the client used when issuing the ID Token. |
| `post_logout_redirect_uri` | OPTIONAL | URI the RP wants the browser returned to after logout. | Must match a registered URI exactly or be permitted by the OP via an equivalent mechanism. |
| `state` | OPTIONAL | Opaque value for the RP to correlate the logout callback. | Return only when performing a valid redirect to the RP. Do not use as proof of identity. |
| `logout_hint` | OPTIONAL | Hint about the user, such as username or session identifier. | Only a hint per OP policy; does not replace `id_token_hint` or user authentication. |
| `ui_locales` | OPTIONAL | Preferred UI languages per BCP 47. | Unsupported locales may be ignored without error. |

`id_token_hint` is **recommended**, not mandatory for every logout request. Therefore, a missing hint does not automatically mean the request is syntactically invalid. However, a missing hint makes it harder for the OP to identify the RP/user/session that the request intends to terminate; the specification requires the OP to prompt the user before logging out of the OP in this case.

### 3.1. GET and POST

The OP's Logout Endpoint must support both HTTP GET and POST:

- GET uses URI Query String Serialization.
- POST uses Form Serialization.

GET example:

~~~http
GET /connect/logout?id_token_hint=<id-token>&post_logout_redirect_uri=https%3A%2F%2Fportal.example.com%2Flogged-out&state=abc123 HTTP/1.1
Host: auth.example.com
~~~

POST example:

~~~http
POST /connect/logout HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

id_token_hint=<id-token>&post_logout_redirect_uri=https%3A%2F%2Fportal.example.com%2Flogged-out&state=abc123
~~~

A POST request from the RP is still a **logout request**, not proof that the user clicked the "Confirm" button on the OP's confirmation page. The OP must not treat the RP sending a POST as interactive confirmation from the user.

## 4. When Is Confirmation Required?

### 4.1. Rules from OIDC RP-Initiated Logout 1.0

At the Logout Endpoint, the OP SHOULD ask the user whether they want to log out of the OP. In the following two cases, the OP **MUST** ask:

1. The request does not provide `id_token_hint`.
2. The provided ID Token does not belong to the current OP session with the RP and/or the currently logged-in user.

If the user responds affirmatively, the OP MUST log out the End-User. If the user declines, the OP must not terminate the OP session based solely on that request.

If the ID Token contains a `sid` that does not match a current RP session or a recent session at the OP, the OP SHOULD treat the request as suspicious and MAY refuse to process it. If the ID Token's `exp` has passed, yet the RP identified via `aud` and/or `sid` still has a current or recent session, the OP SHOULD accept that ID Token as a logout hint. Therefore, do not mechanically enforce a rule that "an expired ID Token cannot be used for logout."

### 4.2. Decision Table

| Scenario | User Confirmation | OP Logout | Redirect to RP |
| --- | --- | --- | --- |
| Valid ID Token, right issuer/client, tied to current session | Should ask; spec requires asking if OP policy applies confirmation to all logouts. | When user approves. | If URI is valid and registered. |
| No `id_token_hint`, active OP login session | **Mandatory to ask.** | Only when user approves. | Only if OP has another way to confirm redirect target validity. |
| No `id_token_hint`, no OP session | No session to log out; may display logged-out state. | No session action; idempotent handling. | Do not redirect if RP and URI are unverified. |
| Valid signature ID Token hint, but does not match current user/session | **Mandatory to ask.** | Only if current user approves; do not silently log out the user named in the hint. | Only if redirect target is independently verified. |
| `client_id` and hint mismatch | Suspicious request; reject operations relying on mismatched data. | Do not log out based on invalid request. | Do not redirect. |
| `post_logout_redirect_uri` unregistered or not exact-match | May display an error or ask whether user wants to log out of OP without returning to RP. | May proceed if user confirms and policy permits. | **Do not redirect** to invalid URI. |
| Only `logout_hint` present | Do not treat hint as identity proof; ask current user if a session exists. | Only when current user approves. | Do not redirect without verified client/URI. |
| Only `state` present | State does not authenticate client or user. | Do not auto-logout based on state. | Do not echo state without a valid redirect. |

### 4.3. Designing the Confirmation Page

The confirmation page should clearly state what the user is confirming:

- "Do you want to sign out of your account across all applications using this login session?"
- Name the initiating application if the OP has identified a trusted client.
- Provide two clear choices: "Sign out" and "Stay signed in".
- Do not display sensitive identity details derived solely from `logout_hint`.
- If the request contained an invalid redirect URI, explain that the OP will not redirect the browser to that address.

Do not show an ambiguous "Continue" button and automatically log out. Users must understand they are ending the central OP session, which can affect multiple RPs.

## 5. Classifying Sufficient and Insufficient Requests

### 5.1. id_token_hint Present and No post_logout_redirect_uri

This request allows identifying the RP/user from the ID Token. The OP validates the token and maps the session. After logging out, the OP displays a completion page at the OP. No redirect back to the RP is needed.

### 5.2. id_token_hint Present and post_logout_redirect_uri Present

The OP must:

1. Verify the ID Token was issued by the OP itself.
2. Identify the client from audience/session.
3. If the request also includes `client_id`, confirm the client ID matches the client used when issuing the ID Token.
4. Verify `post_logout_redirect_uri` matches a registered URI for the client exactly.
5. Verify session/user context and decide whether confirmation is needed.
6. Redirect only after logout is complete and necessary logout notifications have been processed.

### 5.3. Missing id_token_hint, Present client_id

`client_id` can help the OP look up `RegisteredClient` and check registered URIs. However, a client ID does not prove that the sender of the request is the logged-in user of that client. Per the standard, the OP must still prompt the user before logging out of the OP because `id_token_hint` is absent.

If `post_logout_redirect_uri` is present, the OP may redirect only when it has another means of confirming target legitimacy. A safe policy may require all of the following:

- `client_id` exists and is permitted.
- The URI exact-matches `RegisteredClient.postLogoutRedirectUris`.
- The browser holds a valid OP session linked to the RP context or other evidence managed by the OP.
- The user has confirmed the logout.

Do not assume that a `client_id` in the query string alone is enough to allow redirection.

### 5.4. Missing Both id_token_hint and client_id

If the user is logged in at the OP, the OP can display a confirmation page allowing the user to actively log out of the current session. There is no basis to identify the initiating RP, so it should not redirect to a URI supplied by the request.

If there is no OP session, the logout operation can be handled idempotently: show a logged-out status or prompt to log in again if the user wants to manage sessions. Never look up a user by an arbitrary `logout_hint` and terminate that account's session.

### 5.5. Present post_logout_redirect_uri, Missing id_token_hint

OIDC RP-Initiated Logout 1.0 states that the OP MUST NOT perform a post-logout redirect without `id_token_hint`, unless the OP has another method of confirming the validity of the redirect target. Even if the URI is already in the registered list, the OP must evaluate the client and request context according to its policy.

If legitimacy cannot be verified, the safe option is:

- Complete OP logout after user confirmation, then display an OP page.
- Do not redirect to the requested URI.
- Do not return `state` since no callback occurs.

### 5.6. logout_hint Does Not Replace ID Token

`logout_hint` is a hint with OP-defined semantics, such as a username, email, phone number, or session identifier. It is not a credential and does not prove the sender is authorized to log out that account.

Do not use `logout_hint` as the sole key to:

- Look up a user and immediately delete their session.
- Select an account when the browser is logged in as a different user without confirmation.
- Bypass verification of `id_token_hint`, `client_id`, or session binding.

## 6. Verifying ID Token Hint and Session Binding

### 6.1. Checking the Issuer

When `id_token_hint` is present, the OP MUST verify that the OP itself is the issuer of the ID Token. Do not merely decode the payload and read `sub`. Depending on storage and architecture, the OP can match the token against issued authorizations/ID Tokens or verify the JWS using internal keys.

Checks to perform:

- Issuer `iss` matches the current OP.
- Signature is valid if the token is verified via JWS.
- `aud` contains the corresponding client identifier.
- If the request includes `client_id`, that value matches the client used when issuing the ID Token.
- `sid`, if present, is associated with the corresponding OP session.
- The resolved principal/session does not conflict with the user currently logged into the browser.

### 6.2. aud May Contain Multiple Values

Do not assume `aud` is always a single string. An OIDC ID Token may have one audience or multiple audiences. When checking `client_id`, verify that the client ID is within the accepted audience set per token policy, while handling `azp` when required per OIDC Core.

Illustrative example:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-123",
  "aud": [
    "customer-portal",
    "shared-client"
  ],
  "azp": "customer-portal",
  "sid": "session-9c82",
  "iat": 1794800000,
  "exp": 1794803600
}
~~~

This is a sample payload. When multiple audiences exist, the OP must apply OIDC rules properly for the authorized party and registered client; do not arbitrarily pick the first element.

### 6.3. An Expired ID Token Is Not Always Useless for Logout

ID Tokens typically have short lifetimes for authentication at the RP. However, the RP may keep the received ID Token to send as `id_token_hint` when the user logs out later. RP-Initiated Logout 1.0 states that the OP SHOULD accept the ID Token if the RP identified by `aud` and/or `sid` has a current or recent session at the OP, even if `exp` has passed.

This does not mean skipping all token checks:

- Still verify the token was issued by the OP.
- Still verify signature/issuer and client binding per policy.
- Still require a current/recent session to tie the hint to the logout context.
- Do not accept a long-expired token with no remaining session solely because its signature is valid.

Do not reuse a JWT validator that only checks `exp` as the sole mechanism for validating logout hints. Separate logout token hint verification policy from standard login ID Token acceptance policy, accounting for current/recent sessions.

### 6.4. Checking sid and Current User

If the ID Token contains `sid`, the OP should compare it against the session registry/session store. If `sid` does not correspond to a current RP session or a recent session at the OP, the request may be suspicious and the OP may reject it.

Additionally, compare the principal in `id_token_hint` with the principal currently in `SecurityContext`/OP session:

- Same user and same session: the request can proceed per confirmation policy.
- Same user but different session: confirm logout scope explicitly and avoid accidentally terminating all sessions if policy targets a single session.
- Different user: do not log out the current user based on the hint; require confirmation or reject per policy.
- No current session: do not infer an active user solely from an old token hint.

## 7. Validating post_logout_redirect_uri and state

### 7.1. Exact Match with Registered URIs

RP-Initiated Logout 1.0 requires the OP not to redirect if the submitted URI does not match a URI registered in `post_logout_redirect_uris` or an equivalent registration mechanism exactly.

For example, the client registered:

~~~text
https://portal.example.com/logout/callback
~~~

The following values must not be treated as equivalent automatically:

~~~text
https://portal.example.com/logout/callback/
https://portal.example.com/logout/callback?next=/home
http://portal.example.com/logout/callback
https://portal.example.com:8443/logout/callback
https://evil.example.net/logout/callback
~~~

Do not use prefix matching, suffix matching, host wildcards, or custom URI normalization to allow near-matches. For native app custom schemes, accept only schemes/URIs registered under your client-type policy.

### 7.2. client_id Without an ID Token

If `id_token_hint` is absent, `client_id` is the common way for the OP to identify the client when `post_logout_redirect_uri` is present. The OP can look up `RegisteredClient` and check the URI. However, simply finding a client does not mean the user has been verified or that the request came from the legitimate RP.

If the redirect target cannot be confirmed by another means, do not redirect. The user can still confirm OP logout and see a completion page at the OP.

### 7.3. state Is Strictly a Correlation Value

`state` is an opaque string created by the RP to link the request and callback. The OP must return the exact value upon a successful redirect to the RP. The OP must not:

- Use `state` to authenticate the client.
- Use `state` to decide which user to log out.
- Redirect to a URL embedded inside `state`.
- Echo `state` when the redirect target has not been verified.

The RP must validate `state` at its callback to defend against request mix-up/CSRF in its own flow. The OP does not need to interpret `state` contents.

### 7.4. Do Not Redirect Before Logout Completes

Post-logout redirection occurs only after the OP has completed the logout steps and notified relevant RPs according to registered mechanisms. Do not send the redirect immediately upon receiving the request, before user confirmation, or before session invalidation completes.

## 8. Secure Confirmation Flow

### 8.1. Two-Step Model

~~~mermaid
flowchart TD
    A["RP or User Agent calls Logout Endpoint"] --> B["Parse GET/POST parameters"]
    B --> C["Validate issuer, client, session, and redirect"]
    C --> D{"Trusted info sufficient and policy allows?"}
    D -->|Yes| E["Display confirmation if policy requires"]
    D -->|Missing hint or session mismatch| E
    D -->|Invalid redirect/client data| F["Do not use invalid data; do not redirect"]
    E --> G{"User confirms?"}
    G -->|No| H["Keep OP session; display cancelled"]
    G -->|Yes| I["Terminate OP session and process logout notifications"]
    I --> J{"Verified redirect target present?"}
    J -->|Yes| K["Redirect to exact URI and return state"]
    J -->|No| L["Display completion page at OP"]
    F --> M["Error page or local logout option with confirmation"]
~~~

### 8.2. GET Must Not Perform Logout Automatically When Confirmation Is Needed

A GET request can be triggered by browser prefetching, link scanners, crawlers, or a third-party page. If `id_token_hint` is missing and the OP needs to ask the user, GET should display a confirmation page rather than deleting the session immediately.

Even when an RP uses POST to send the logout request, that POST still does not prove the user consented at the OP. The user's confirmation action must be a separate operation protected by CSRF.

### 8.3. POST Confirmation Must Be Protected

The confirmation page needs:

- A Spring Security CSRF token for the POST form.
- A random, unpredictable, one-time, short-TTL ticket if state must be stored across a redirect.
- The ticket bound to the current OP session ID and principal.
- Verification that the user is still in the same session when clicking "Sign out".
- Atomic ticket consumption to prevent replay.
- A "Stay signed in" button that does not perform logout and does not redirect to the RP.
- Disallowing the client request from supplying `confirmed=true` in the initial logout request.

Do not use GET like `/logout/confirm?yes=true` to execute the action. Browsers can automatically fetch that URL and cause unintended logouts.

### 8.4. Storing Pending Requests on the Server

There is no need to put the entire `id_token_hint`, `state`, or redirect URI into the confirmation page URL. One approach is:

1. After initial parsing/validation, generate a random ticket.
2. Save the pending logout in a server-side store with the ticket hash, session ID, principal, validated request context, expiration timestamp, and redirect eligibility.
3. Redirect to an internal URL such as `/logout/confirm?ticket=<opaque-ticket>`.
4. The confirmation page POSTs the ticket + CSRF token.
5. The server consumes the ticket once and verifies the session/principal still match.
6. If approved, execute logout; if declined, delete the pending request and keep the session.

Do not log raw tickets or ID Token hints in access logs. If you must keep request state in the session, store it briefly and delete it once handled.

## 9. Error Handling and Invalid Requests

### 9.1. Do Not Use Data When Validation Fails

OIDC RP-Initiated Logout 1.0 specifies that if a validation step fails, operations relying on the invalid data must be aborted and the invalid data must not be used. Specifically, if the request has an error, the OP MUST NOT post-logout redirect to the RP.

The OP may decide what content to show after an error:

- Display an error message.
- Ask whether the user wants to log out of the OP.
- Allow terminating the OP session after confirmation without redirecting.
- Reject completely if the request is suspicious or risks targeting another user.

### 9.2. Distinguishing Syntax Errors and Missing Information

| Case | Classification | Handling Approach |
| --- | --- | --- |
| Missing `id_token_hint` | Missing recommended info, not necessarily a syntax error. | Mandatory to ask the user before logging out of the OP. |
| Missing `post_logout_redirect_uri` | Valid request; RP does not request returning. | Display an OP page after logout. |
| Missing `state` | Valid request; no callback correlation value. | Do not invent or fabricate a state. |
| Missing `client_id` with ID Token hint present | Can identify client from token/session. | Verify issuer, audience/session, and redirect if present. |
| `client_id` does not match ID Token | Conflicting data. | Reject operations relying on the request; do not redirect. |
| Unregistered `post_logout_redirect_uri` | Invalid redirect target. | Do not redirect; show an error or confirm OP logout without redirecting. |
| ID Token not issued by OP | Invalid hint. | Do not use token to select user/session; reject or require manual logout per policy. |
| ID Token `sid` no longer tied to current/recent session | Suspicious request. | May reject; if prompting the user, log out only the current user's session after confirmation. |
| Repeated logout request after session already ended | Idempotent case. | Do not treat "no session left" as a mandatory error; do not cause unintended side effects. |
| Only `logout_hint` present | Insufficient evidence. | Do not auto-select user and log out; prompt the currently logged-in user. |

### 9.3. Avoid Information Leakage Through Error Messages

Do not return detailed messages such as "user X exists but session Y does not match" to an untrusted request. Return a generic error to the client and record minimal details in internal audit logs.

Do not log raw ID Token hints, session cookies, full session IDs, CSRF tokens, confirmation tickets, or full `state` values if policy treats them as sensitive data.

## 10. How Does Spring Authorization Server Process Logout?

### 10.1. Enabling OIDC and the Logout Endpoint

Spring Authorization Server configures OIDC via `OAuth2AuthorizationServerConfigurer.oidc(...)`. The Logout Endpoint can be customized using `OidcLogoutEndpointConfigurer`:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .oidc(oidc -> oidc
                .logoutEndpoint(logout -> logout
                    .authenticationProviders(
                        configureLogoutValidation())
                )
            )
        );

    return http.build();
}
~~~

This snippet focuses on logout configuration; the application still needs other Authorization Server beans such as `RegisteredClientRepository`, `OAuth2AuthorizationService`, key/JWK source, user authentication, and session management.

### 10.2. Default Components

`OidcLogoutEndpointFilter` is the filter handling RP-Initiated Logout. The default setup includes:

| Component | Class | Role |
| --- | --- | --- |
| Request converter | `OidcLogoutAuthenticationConverter` | Reads GET/POST requests and creates `OidcLogoutAuthenticationToken`. |
| Authentication provider | `OidcLogoutAuthenticationProvider` | Processes logout authentication, linking `RegisteredClient`, authorization, and session. |
| Success handler | `OidcLogoutAuthenticationSuccessHandler` | Executes logout when the provider authenticates successfully. |
| Failure handler | Internal `OAuth2ErrorAuthenticationFailureHandler` | Returns an OAuth error when processing fails. |
| Session registry | `SessionRegistry` | Looks up the End-User's session to perform logout. |

Spring Authorization Server exposes extension points for the converter, provider, success handler, and error handler. This is where additional policies should be integrated; there is no need to rewrite the entire OIDC protocol endpoint from scratch.

### 10.3. What Does the Default Validator Do?

Since Spring Authorization Server 1.4, `OidcLogoutAuthenticationProvider` has `setAuthenticationValidator(Consumer<OidcLogoutAuthenticationContext>)`. In Spring Authorization Server 1.5.8:

- `OidcLogoutAuthenticationValidator` is the default validator.
- The default validator checks the `post_logout_redirect_uri` parameter.
- When validation fails, the validator throws `OAuth2AuthenticationException`.
- `OidcLogoutAuthenticationContext` holds `OidcLogoutAuthenticationToken` and `RegisteredClient`.

Do not assume the default validator enforces every OIDC confirmation policy. The application should verify how its active version handles issuer, client binding, current/recent sessions, and missing-hint cases, adding policies where needed.

### 10.4. SessionRegistry

`OidcLogoutAuthenticationProvider` uses `SessionRegistry` to look up the End-User's `SessionInformation`. When OIDC is enabled, Spring Authorization Server uses `SessionRegistry` to track authenticated sessions.

If registering `SessionRegistryImpl`, register `HttpSessionEventPublisher` so `SessionRegistry` receives `HttpSession` destruction events and cleans up corresponding entries:

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

If the application uses Spring Session or a distributed session store, ensure the session registry shares state properly across nodes. If Concurrent Session Control and OIDC Logout both use session tracking, share a single `SessionRegistry`.

## 11. Custom Validation for Logout Requests

### 11.1. Keeping the Default Validator While Adding Policies

A custom validator should preserve the framework's standard checks and then add custom conditions. The example below:

- Calls the default validator to preserve `post_logout_redirect_uri` checking.
- If both `client_id` and ID Token are present, checks that `client_id` is in the ID Token's audience.
- If a redirect URI is present, requires `RegisteredClient` and a registered URI.
- Does not verify tokens merely by decoding the payload; ID Token/session verification must rely on the OP's trusted token/authorization mechanisms.

~~~java
private Consumer<List<AuthenticationProvider>>
        configureLogoutValidation() {

    return providers -> providers.forEach(provider -> {
        if (provider instanceof OidcLogoutAuthenticationProvider logoutProvider) {
            logoutProvider.setAuthenticationValidator(context -> {
                // Preserve default post_logout_redirect_uri validation.
                new OidcLogoutAuthenticationValidator().accept(context);

                OidcLogoutAuthenticationToken logout =
                    context.getAuthentication();
                RegisteredClient registeredClient =
                    context.getRegisteredClient();

                OidcIdToken idToken = logout.getIdToken();
                String clientId = logout.getClientId();

                if (idToken != null && clientId != null
                        && !idToken.getAudience().contains(clientId)) {
                    throw new OAuth2AuthenticationException(
                        new OAuth2Error("invalid_request"));
                }

                String redirectUri = logout.getPostLogoutRedirectUri();
                if (redirectUri != null
                        && (registeredClient == null
                        || !registeredClient.getPostLogoutRedirectUris()
                            .contains(redirectUri))) {
                    throw new OAuth2AuthenticationException(
                        new OAuth2Error("invalid_request"));
                }
            });
        }
    });
}
~~~

This example adds client/redirect validation and is not a complete validator for every deployment. `RegisteredClient` is resolved by the provider/context per request; the application should verify behavior when `id_token_hint` is present but `client_id` is absent. If an ID Token has multiple audiences, use membership checks rather than reading only the first element.

### 11.2. Do Not Turn a Missing Hint into a Validation Error

`id_token_hint` is RECOMMENDED, not REQUIRED. A custom validator should not reject every request merely because the hint is missing. Instead, the request should proceed into the confirmation policy.

~~~java
boolean requiresConfirmation(OidcLogoutAuthenticationToken logout) {
    if (logout.getIdToken() == null) {
        return true;
    }
    return !sessionBindingPolicy.belongsToCurrentOrRecentSession(logout);
}
~~~

`sessionBindingPolicy` is an application-implemented component that must inspect session/principal/`RegisteredClient` using trusted data. Never infer "matching session" solely from the ID Token having a valid signature.

### 11.3. A Validator Is Not a Confirmation UI

A validator only decides whether the request passes authentication/validation conditions. When a confirmation page needs to be shown, use `logoutResponseHandler` or a dedicated UI flow securely integrated with the endpoint. Never throw fake errors to force the framework into rendering a confirmation page; the error handler is for errors, not logout consent.

## 12. Integrating Confirmation via the Success Handler

### 12.1. Why Use the Success Handler?

After `OidcLogoutAuthenticationProvider` processes the request, `logoutResponseHandler` receives the `OidcLogoutAuthenticationToken` accepted by the provider. The default handler `OidcLogoutAuthenticationSuccessHandler` performs the logout.

An application can replace the success handler to:

1. Check whether policy requires user confirmation.
2. If needed, create a pending logout and display the confirmation page.
3. If confirmation is not needed, delegate to the default success handler.
4. After the user confirms via a separate POST, retrieve the pending logout once and perform the logout.

### 12.2. Illustrative Handler

~~~java
final class ConfirmationAwareLogoutSuccessHandler
        implements AuthenticationSuccessHandler {

    private final OidcLogoutAuthenticationSuccessHandler delegate;
    private final LogoutConfirmationPolicy confirmationPolicy;
    private final PendingLogoutStore pendingLogoutStore;

    ConfirmationAwareLogoutSuccessHandler(
            LogoutConfirmationPolicy confirmationPolicy,
            PendingLogoutStore pendingLogoutStore) {
        this.delegate = new OidcLogoutAuthenticationSuccessHandler();
        this.confirmationPolicy = confirmationPolicy;
        this.pendingLogoutStore = pendingLogoutStore;
    }

    @Override
    public void onAuthenticationSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication)
            throws IOException, ServletException {

        OidcLogoutAuthenticationToken logout =
            (OidcLogoutAuthenticationToken) authentication;

        if (confirmationPolicy.requiresConfirmation(logout)) {
            HttpSession session = request.getSession(false);
            if (session == null) {
                response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
                return;
            }

            String ticket = pendingLogoutStore.create(
                logout,
                session.getId(),
                authentication.getName(),
                Duration.ofMinutes(2));

            response.sendRedirect(
                "/logout/confirm?ticket=" +
                URLEncoder.encode(ticket, StandardCharsets.UTF_8));
            return;
        }

        delegate.onAuthenticationSuccess(
            request, response, authentication);
    }
}
~~~

`LogoutConfirmationPolicy` and `PendingLogoutStore` are application-implemented abstractions. The store should hold the pending authentication/request context server-side with a short TTL, a random ticket, one-time consumption, and session/principal binding. Do not place raw `id_token_hint` or the entire logout request into the URL.

When configuring:

~~~java
.oidc(oidc -> oidc
    .logoutEndpoint(logout -> logout
        .logoutResponseHandler(
            confirmationAwareLogoutSuccessHandler)
    )
)
~~~

This snippet illustrates the extension point. If you replace the success handler, make sure the default handler is still invoked on the branch that does not need confirmation and after the user has confirmed. If using a custom `LogoutHandler`, preserve essential behaviors such as session invalidation, clearing the security context, deleting cookies, and configured notifications.

### 12.3. Confirmation POST

The controller handling confirmation should have semantics similar to:

~~~java
@PostMapping("/logout/confirm")
void confirmLogout(
        @RequestParam String ticket,
        @RequestParam boolean confirm,
        HttpServletRequest request,
        HttpServletResponse response,
        Authentication currentAuthentication) throws IOException, ServletException {

    HttpSession session = request.getSession(false);
    if (session == null) {
        response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
        return;
    }

    PendingLogout pending = pendingLogoutStore.consume(
        ticket,
        session.getId(),
        currentAuthentication.getName());

    if (!confirm) {
        response.sendRedirect("/logout/cancelled");
        return;
    }

    logoutCompletionService.complete(
        request, response, pending);
}
~~~

This is an architectural skeleton; `consume(...)` must verify that the ticket exists, is unused, is unexpired, and matches the session ID and principal, then delete the ticket atomically. `LogoutCompletionService` is an application-implemented component: it delegates to the configured success/logout handler when the redirect has been verified, or performs logout and displays an OP page when no valid redirect exists. Never re-invoke the logout endpoint with a `confirm=true` query parameter.

The POST form needs CSRF protection. Do not disable CSRF for the confirmation route. If the Authorization Server security chain has its own matcher/CSRF policy, configure the confirmation UI route clearly in the appropriate chain.

### 12.4. When There Is No Valid Redirect

If a request lacks `id_token_hint` and the OP has no other way to verify the redirect target, the confirmation page can still allow OP logout. After confirmation:

- Terminate the OP session.
- Notify RPs via front-channel/back-channel logout if registered and configured.
- Display a completion page at the OP.
- Do not redirect to the URI in the request.
- Do not return `state`.

Do not invoke the default redirect handler to redirect to a URI merely because the user clicked "Sign out." Consenting to logout does not turn an invalid redirect target into a valid one.

## 13. Error Responses and UI Pages

### 13.1. Protocol Errors

`OidcLogoutEndpointConfigurer.errorResponseHandler(...)` lets you replace the default failure handler. The default handler uses an OAuth error tied to `OAuth2AuthenticationException`.

An application can customize it to:

- Emit audit events with internal reason codes.
- Return a user-friendly error page to the browser.
- Avoid exposing tokens, session IDs, or account details.
- Never redirect to an RP when validation fails.

### 13.2. Do Not Turn Every Error into Confirmation

Some errors require immediate rejection:

- `client_id` conflicts with `id_token_hint`.
- ID Token was not issued by the OP.
- Redirect URI is not registered.
- Request data is malformed or exceeds limits.
- Session/token hint points to another user and policy forbids it.

A confirmation page is appropriate when a request lacks sufficient evidence yet can still prompt the currently logged-in user. Confirmation cannot fix invalid client/redirect data and must never legitimize an open redirect.

### 13.3. Idempotency

RP-Initiated Logout is designed to be idempotent. A request asking to log out an RP for which the OP no longer holds a login session is not necessarily an error. This allows RPs to retry when unsure whether a logout notification was processed.

However, idempotency does not mean bypassing redirect validation or session binding. Repeated calls must not cause unintended side effects or redirect to unverified URIs.

## 14. Session Tracking and RP Notifications

### 14.1. SessionRegistry Must Be Consistent

Spring Authorization Server uses `SessionRegistry` to locate the End-User's session during logout. In a cluster:

- Use a registry/store suited to your session architecture.
- Ensure the node handling logout can look up sessions registered by the login node.
- Configure `HttpSessionEventPublisher` when using `SessionRegistryImpl`.
- Test session expiration and destruction events.
- Avoid deleting the session registry record before required logout notifications complete.

### 14.2. Front-Channel and Back-Channel Logout

The OP can notify RPs logged in for the End-User using front-channel or back-channel mechanisms supported by both sides. The logout-initiating RP must also be accounted for before the OP redirects back to the RP.

These notifications help RPs end their local sessions. They do not replace user confirmation when the standard requires confirmation and do not by themselves make a redirect URI valid.

### 14.3. RP Misses a Notification

Some logout notifications may not be received because the browser closed, the network failed, or an RP was down. Therefore:

- RPs should have clear local logout behavior.
- The OP should audit notification results/retries if the implementation supports it.
- Access tokens/refresh tokens require separate lifecycle policies.
- Users should be informed if logout was only partial.

## 15. Securing the Confirmation Flow

### 15.1. CSRF and Logout CSRF

Logout CSRF can cause a browser to be logged out unintentionally when visiting a malicious page. A confirmation page mitigates this risk, but only if the confirmation action itself is protected:

- Use a CSRF token on the POST form.
- Never execute logout via GET.
- Never treat a POST sent by an RP to the Logout Endpoint as user confirmation.
- Disallow external sites from embedding the confirmation page unless policy allows; consider CSP `frame-ancestors`.
- Check `Origin`/`Referer` when appropriate for the architecture and browser support, but do not replace CSRF tokens with those headers.

### 15.2. Open Redirect

This is a severe risk in logout flows. Never redirect to arbitrary URLs, never use host wildcards, and never pull URLs from `state` or `logout_hint`. Use only registered exact-match URIs or an independently evaluated verification mechanism.

### 15.3. Ticket Replay and Session Swapping

The confirmation ticket must:

- Have high entropy and be unpredictable.
- Expire quickly.
- Be single-use and consumed atomically.
- Be bound to the session ID and principal.
- Be unusable from another browser/session.
- Be deleted when the user cancels or upon expiration.

If the user switches accounts while the confirmation page is open, the ticket must be rejected because the principal/session changed.

### 15.4. Protecting ID Token Hints in URLs and Logs

`id_token_hint` can appear in the query string of GET logout requests. Minimize leakage:

- Do not log full query strings at ingress/application layers.
- Use `Referrer-Policy: no-referrer` on related pages.
- Do not load third-party analytics/images/scripts on the confirmation page.
- Do not store token hints in flash attributes or browser storage.
- Delete pending state after processing.

RPs can use POST to send logout requests when avoiding tokens in URLs, while the OP must still support GET per the standard.

## 16. Testing RP-Initiated Logout

### 16.1. Validation Unit Tests

Test independently:

- `client_id` matching ID Token audience.
- `client_id` mismatching audience.
- `post_logout_redirect_uri` exact match.
- Redirect URI differing in path, port, scheme, or trailing slash.
- Missing ID Token hint.
- ID Token with valid, invalid, or expired-session `sid`.
- ID Token past `exp` while session remains current/recent.
- `logout_hint` not accepted as proof of identity.

### 16.2. Confirmation Integration Tests

| Scenario | Expected Result |
| --- | --- |
| Valid hint, matching current session | Logs out per confirmation policy; does not log out other users. |
| Missing `id_token_hint` | Displays confirmation; session not terminated before user approves. |
| Hint belonging to another user | Does not log out per hint; prompts confirmation for current session or rejects. |
| Hint not issued by OP | Does not use token; does not redirect. |
| `client_id` and hint mismatch | Rejects; no logout and no redirect. |
| Exact-match redirect | Redirects only after logout completes. |
| Redirect mismatch | Does not redirect; displays error or completes OP logout without redirect after confirmation. |
| Missing `state` | Logout still works; does not fabricate state. |
| Valid `state` and redirect | Returns exact state in callback. |
| Only `logout_hint` | Does not auto-select user; confirmation applies to current session. |
| GET logout request | Can display confirmation; does not auto-logout when confirmation is needed. |
| POST from RP | Does not treat POST as user consent. |
| Confirmation POST missing CSRF | Rejected. |
| Expired confirmation ticket | No logout. |
| Reused ticket | Replay request rejected. |
| Ticket from another session | Rejected. |
| User selects "Stay signed in" | OP session remains intact; pending request deleted. |
| User selects "Sign out" | OP session terminated; redirects only when verified. |
| Session already ended before request | Handled idempotently without unnecessary error. |
| RP notification failure | Logged and handled per retry/policy; no redirect before mandatory steps complete. |

### 16.3. Real Browser Tests

MockMvc checks filters, validators, and controllers, whereas browser integration tests should verify:

1. RP redirects to `end_session_endpoint`.
2. OP reads GET/POST parameters accurately.
3. Confirmation page does not execute logout on initial load.
4. Browser includes a CSRF token in the form.
5. Cancel button preserves the OP session.
6. Confirm button terminates the OP session and clears cookies.
7. Redirect goes only to registered URIs and `state` is returned intact.
8. Opening a confirmation ticket in another browser/session has no effect.
9. A second tab or repeated request does not mistakenly log out a new session.

## 17. Common Pitfalls and How to Fix Them

### Pitfall 1: Rejecting Every Request Missing id_token_hint

**Symptom:** Legacy RPs or directly initiated logouts always receive errors.

**Cause:** Treating `id_token_hint` as REQUIRED even though OIDC only marks it RECOMMENDED.

**Fix:** Allow requests lacking a hint to enter the confirmation flow; perform OP logout only after user confirmation.

### Pitfall 2: Logging Out Immediately on GET

**Symptom:** Users get logged out when the browser prefetches or opens a link from another page.

**Cause:** Treating arrival at the Logout Endpoint as user consent.

**Fix:** For requests missing a hint or not matching the session, display confirmation; execute via CSRF-protected POST.

### Pitfall 3: Treating logout_hint as a Verified Identity

**Symptom:** A request providing only an email/username can terminate that account's session.

**Cause:** Confusing a hint with a credential.

**Fix:** Use the hint only for display/suggestion; bind to the current user's session and require confirmation.

### Pitfall 4: Redirecting via Prefix Matching

**Symptom:** URIs like `https://portal.example.com.evil.test/` are accepted.

**Cause:** Checking `startsWith` or using domain wildcards.

**Fix:** Exact-match against `post_logout_redirect_uris`.

### Pitfall 5: Returning state Without Redirecting

**Symptom:** The RP receives an invalid callback or misinterprets logout status.

**Cause:** Echoing `state` even when the redirect target was rejected.

**Fix:** Return `state` only in a valid, completed redirect.

### Pitfall 6: Rejecting ID Token Hints Solely Because exp Passed

**Symptom:** RPs cannot log out recent sessions because the ID Token expired.

**Cause:** Applying login-flow JWT expiration validation without accounting for the logout profile.

**Fix:** Verify issuer/signature/client/session and apply RP-Initiated Logout's current/recent session rule.

### Pitfall 7: Assuming the Default Validator Implements the Entire Policy

**Symptom:** Redirects are checked, but client/session mismatches are not handled per application policy.

**Cause:** Failing to distinguish `OidcLogoutAuthenticationValidator` from the overall logout provider.

**Fix:** Verify the behavior of your active version; supplement with `setAuthenticationValidator(...)` and a confirmation policy.

### Pitfall 8: Confirmation Ticket Not Bound to the Session

**Symptom:** Another user can confirm a ticket obtained from a URL or log.

**Cause:** The ticket is merely a random URL parameter not bound to a browser session.

**Fix:** Bind the ticket to session ID/principal, give it a short TTL, and consume it once.

### Pitfall 9: Confusing OP Logout with Token Revocation

**Symptom:** The user logs out, yet access tokens keep working until TTL or refresh tokens remain valid.

**Cause:** Deleting only `HttpSession` without addressing authorization/token policy.

**Fix:** Design token revocation and session logout as distinct, clearly related behaviors and test them separately.

## 18. Production Checklist

| Item | Condition to Verify |
| --- | --- |
| Discovery | `end_session_endpoint` advertises the right HTTPS URL. |
| Protocol | Supports GET and POST per RP-Initiated Logout 1.0. |
| ID Token hint | Verifies issuer, audience/client, `sid`, and current/recent session. |
| Missing hint | Confirmation is mandatory before OP logout. |
| Session mismatch | Confirmation or rejection; never log out the wrong principal. |
| Expired hint | Policy accepts when session is current/recent per spec. |
| Client binding | `client_id` and hint match when both are present. |
| Redirect | Exact-match with registered URIs; no open redirect. |
| Redirect without hint | Independent evidence of legitimacy exists before redirecting. |
| State | Echoed only on valid redirects; RP verifies callback itself. |
| Confirmation | GET has no side effects; POST has CSRF. |
| Ticket | Random, short TTL, one-time, bound to session/principal. |
| Spring provider | Custom validator preserves default redirect validation. |
| Success handler | Executes logout only after required confirmation. |
| `SessionRegistry` | Shared and cleans up session lifecycle properly. |
| RP notification | Front/back-channel logout tested per registered client. |
| Token lifecycle | Session logout and token revocation clearly separated. |
| Audit | Logs outcomes/decisions/reasons without logging tokens or cookies. |
| Browser | Tested for prefetch, cross-site, multi-tab, and replay. |

## 19. Hands-On Exercise

An OP using Spring Authorization Server at `https://auth.example.com` serves `customer-portal` and `billing-console`. Both RPs use the Authorization Code Flow. Portal sends `id_token_hint`, `post_logout_redirect_uri`, and `state`; an older version of `billing-console` sends only `client_id` and `post_logout_redirect_uri`. In addition, users can open `/connect/logout` directly from a bookmark.

1. Design a decision matrix for the three requests: full portal request, billing request missing the ID Token hint, and direct request with no parameters.
2. Identify when the OP MUST require confirmation and when it may skip confirmation per policy.
3. Write a custom validator that keeps the default `OidcLogoutAuthenticationValidator`, checking `client_id` against audience and exact-matching the redirect URI.
4. Design `LogoutConfirmationPolicy` to check current/recent sessions.
5. Build `PendingLogoutStore` with a one-time ticket, a two-minute TTL, session ID/principal binding, and CSRF-protected confirmation POST.
6. Replace `logoutResponseHandler` with a confirmation-aware handler that invokes the default handler only after user confirmation.
7. Prove that a request with `post_logout_redirect_uri` but no hint cannot redirect if the OP has not verified legitimacy per policy.
8. Test an ID Token whose `exp` has passed while `sid` still points to a recent session.
9. Test `client_id` mismatching `aud`, a redirect URI differing by one character, a missing `state`, and ticket replay.
10. Distinguish the outcomes of OP session logout, RP local session logout, and access/refresh token revocation.

**Acceptance Criteria:** The OP never logs out a user based solely on an insufficient request; every redirect is verified; when `id_token_hint` is missing or the session mismatches, the user must confirm before the OP ends the session; confirmation actions cannot be replayed or CSRF-exploited.

## 20. Reference Documentation

- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html): logout parameters, user confirmation, current/recent sessions, post-logout redirect, and validation/error handling.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, `iss`, `aud`, `azp`, `sid`, and token verification.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): `end_session_endpoint` metadata.
- [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html): logout notifications via User Agent.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): direct logout notifications to RPs.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): OIDC Logout Endpoint, converter/provider/handler, and custom validation.
- [Spring Authorization Server — OidcLogoutEndpointConfigurer Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OidcLogoutEndpointConfigurer.html): Logout Endpoint extension points.
- [Spring Authorization Server — OidcLogoutAuthenticationProvider Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcLogoutAuthenticationProvider.html): session registry and custom validator.
- [Spring Authorization Server — OidcLogoutAuthenticationContext Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcLogoutAuthenticationContext.html): request context and `RegisteredClient`.
- [Spring Authorization Server — OidcLogoutAuthenticationSuccessHandler Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/web/authentication/OidcLogoutAuthenticationSuccessHandler.html): executing logout and custom `LogoutHandler`.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `SessionRegistry` and `HttpSessionEventPublisher`.
