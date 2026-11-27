# id_token_hint, client_id, post_logout_redirect_uri, and state

> **Chapter:** OIDC Logout  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Module Goal:** Learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in Spring Boot applications.  
> **Technical Scope:** OpenID Connect RP-Initiated Logout 1.0 Final (2022), Spring Boot 3.x, Spring Security 6.x, and Spring Authorization Server 1.5.x on the Servlet stack. Verify APIs against your actual patch version.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain how a Relying Party (RP) requests an OpenID Provider (OP) to log out an End-User using RP-Initiated Logout.
2. Locate the correct `end_session_endpoint` from OpenID Provider Discovery and distinguish it from the OAuth2 Token Revocation Endpoint.
3. Understand the roles, requirement levels, and validation rules of four parameters: `id_token_hint`, `client_id`, `post_logout_redirect_uri`, and `state`.
4. Distinguish an ID Token hint from an access token, refresh token, OAuth2 `redirect_uri`, authorization `state`, and OIDC `nonce`.
5. Understand how the OP validates the ID Token hint, client identity, current session, and post-logout redirect target.
6. Design a redirect allowlist to prevent open redirects, phishing, and logout request forgery.
7. Configure the OIDC Logout Endpoint in Spring Authorization Server and register post-logout redirect URIs for each RegisteredClient.
8. Use `OidcClientInitiatedLogoutSuccessHandler` in Spring Security OAuth2 Client so the RP directs the browser to the OP.
9. Combine local logout, OP session logout, front-channel/back-channel notifications, and token revocation into a clear workflow.
10. Write tests for invalid/expired ID Tokens, client mismatches, unregistered URIs, state mismatches, missing sessions, and multiple simultaneously logged-in RPs.

**Key Message:** `id_token_hint` helps the OP identify the user/client/session; `client_id` identifies the client and must match the ID Token if both appear; `post_logout_redirect_uri` is the pre-registered return destination; `state` helps the RP correlate the callback. These four parameters have distinct roles and do not replace one another.

## 2. The Problem: Logging Out of an RP Does Not Mean Logging Out of the OP

Suppose a user logs into three applications: `booking-web`, `expense-portal`, and `support-console`. All three share the same OpenID Provider `https://auth.example.test`. The user logged in once, and the OP holds a browser session cookie.

When the user clicks Logout in `booking-web`:

1. The RP can clear its own local session/cookie.
2. The browser still holds the session cookie at the OP.
3. If the user visits `expense-portal`, the OP can perform SSO without prompting for a password.
4. The user thinks they logged out completely, when in reality they only logged out of one RP.

RP-Initiated Logout allows the RP to redirect the browser to the OP's Logout Endpoint to request that the OP terminate the End-User session.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as End-User / Browser
    participant RP as Booking RP
    participant OP as OpenID Provider
    participant RP2 as Expense RP

    U->>RP: Click Logout
    RP->>RP: Terminate local session
    RP-->>U: Redirect to OP Logout Endpoint
    U->>OP: id_token_hint + post_logout_redirect_uri + state
    OP->>OP: Validate hint/client/session/redirect
    OP->>U: Confirm logout if needed
    U-->>OP: Approve
    OP->>OP: Terminate OP session
    OP-->>RP2: Logout notification if configured
    OP-->>U: Redirect to RP with state
    U->>RP: Post-logout callback
    RP->>RP: Verify state and display result
~~~

**RP-Initiated Logout does not mean revoking all OAuth2 tokens.** The OP session, RP local session, access token, refresh token, and sessions of other RPs are related but separate states.

## 3. Components and Endpoints

| Term | Role |
| --- | --- |
| RP (Relying Party) | An OIDC application using authentication provided by the OP |
| OP (OpenID Provider) | The system authenticating the user and issuing ID Tokens |
| End-User | The logged-in user |
| Logout Endpoint | The OP endpoint receiving RP-Initiated Logout requests |
| `end_session_endpoint` | Metadata field advertising the Logout Endpoint URL |
| `id_token_hint` | An ID Token issued by the OP to the RP, used as a hint to identify the user/session |
| `client_id` | The OAuth2 Client Identifier at the OP |
| `post_logout_redirect_uri` | The URL to which the RP requests the browser return after logout |
| `post_logout_redirect_uris` | The list of pre-registered URIs permitted by the OP |
| `state` | An opaque value used by the RP to correlate the request and callback |
| `sid` | Session identifier in OIDC session/logout profiles if issued |

### 3.1. RP-Initiated Logout Redirects Through the User Agent

The RP usually navigates the browser to the OP so the browser carries the current OP session cookie:

1. The RP retrieves `end_session_endpoint` from the OpenID Provider Configuration or trusted discovery.
2. The RP constructs the Logout Request.
3. The browser navigates to the OP via HTTP GET or POST.
4. The OP validates the request and processes the End-User session.
5. The OP may ask the user to confirm logging out of the OP.
6. The OP sends logout notifications to RPs registered with a supported mechanism.
7. The OP redirects the browser back to the RP if the redirect target is valid.

OIDC RP-Initiated Logout requires the OP to support both GET and POST. The RP MAY choose either method.

### 3.2. Retrieving the Logout Endpoint from Discovery

The OP publishes `end_session_endpoint` in the OpenID Provider metadata when supporting RP-Initiated Logout and Discovery:

~~~json
{
  "issuer": "https://auth.example.test",
  "authorization_endpoint": "https://auth.example.test/oauth2/authorize",
  "token_endpoint": "https://auth.example.test/oauth2/token",
  "jwks_uri": "https://auth.example.test/oauth2/jwks",
  "end_session_endpoint": "https://auth.example.test/connect/logout"
}
~~~

This is illustrative JSON. The exact URL depends on `AuthorizationServerSettings` and your deployment. The RP should not manually concatenate the issuer with `/connect/logout` because the endpoint path/host/proxy route can change. Use verified metadata from the correct OP.

### 3.3. Do Not Confuse the Endpoints

| Endpoint | Purpose |
| --- | --- |
| `authorization_endpoint` | Starts OAuth2/OIDC authorization |
| `token_endpoint` | Exchanges a code/refresh token for tokens |
| `end_session_endpoint` | Requests the OP to log out the End-User |
| `revocation_endpoint` | Revokes access/refresh tokens per RFC 7009 |
| `introspection_endpoint` | Queries token status per RFC 7662 |
| Back-Channel Logout URI | RP receives server-to-server Logout Tokens if supported |

RP logout does not replace revocation. If refresh tokens need to be revoked, implement Token Revocation separately according to policy.

## 4. The Four Core Parameters

| Parameter | Requirement Level | Who Creates It? | Purpose |
| --- | --- | --- | --- |
| `id_token_hint` | RECOMMENDED | RP holding the ID Token issued by the OP | OP identifies the End-User, client, and session |
| `client_id` | OPTIONAL | RP | Identifies the client; if paired with an ID Token hint, the OP MUST verify a match |
| `post_logout_redirect_uri` | OPTIONAL | RP | Destination to return the browser to after logout |
| `state` | OPTIONAL | RP | Correlates the logout request and callback |

The keywords `RECOMMENDED`, `OPTIONAL`, `MUST`, and `SHOULD` carry normative meanings per OIDC RP-Initiated Logout 1.0.

### 4.1. GET Request Example

~~~http
GET /connect/logout?id_token_hint=eyJ...ID_TOKEN...&client_id=booking-bff&post_logout_redirect_uri=https%3A%2F%2Fapp.example.test%2Flogout%2Fcallback&state=RANDOM_STATE HTTP/1.1
Host: auth.example.test
~~~

### 4.2. POST Request Example

~~~http
POST /connect/logout HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

id_token_hint=eyJ...ID_TOKEN...&client_id=booking-bff&post_logout_redirect_uri=https%3A%2F%2Fapp.example.test%2Flogout%2Fcallback&state=RANDOM_STATE
~~~

GET uses URI Query String Serialization; POST uses Form Serialization. Do not send a client secret in the Logout Request.

## 5. id_token_hint — Identifying the User and Session

### 5.1. Definition and Purpose

`id_token_hint` is an ID Token **previously issued by the OP to the RP**, sent to the Logout Endpoint as a hint about the End-User's current login session with the client.

The OP can use it to identify:

- Subject/user.
- Client/RP that received the ID Token.
- Associated session, if the ID Token includes `sid`.
- Authorization/registration context to verify the redirect target.

`id_token_hint` is **RECOMMENDED**, especially when the RP wants to redirect the browser back after logout.

### 5.2. Send the Right Token Type

Send the ID Token issued by the OP itself to the RP. Do not substitute:

- An OAuth2 access token.
- A refresh token.
- An authorization code.
- A JWT self-signed by the RP.
- An ID Token from another issuer.
- An ID Token of another user/client.

An access token proves authorization to access a Resource Server; an ID Token is an identity assertion meant for the RP. The Logout Endpoint requires an ID Token hint per OIDC RP-Initiated Logout.

### 5.3. The OP Must Verify the ID Token Hint

When `id_token_hint` is present, the OP **MUST** verify that it is the issuer of the ID Token.

The OP needs to verify that the token was issued by itself and check the client/session relationship per the protocol. Do not merely decode the JWT payload and trust `sub`. The signature/issuer, client identity, and session context must all be verified.

### 5.4. Is an Expired ID Token Hint Rejected?

This is a critical point: OIDC RP-Initiated Logout specifies that the OP **SHOULD** accept an ID Token when the RP identified via `aud` and/or `sid` has a current or recent session at the OP, **even if `exp` has passed**.

Reason: the ID Token hint is used to identify the session to log out; a user may log out after the ID Token expires while the OP session is still active.

- Do not reject a hint by default just because `exp` has passed.
- The OP must still verify that the token was issued by itself.
- An expired token does not by itself prove the user still has a session.
- If `sid` does not match a current/recent session, the OP SHOULD treat the request as suspicious and MAY reject it.
- The OP can ask the user for confirmation when the hint is not tied to a current session.

These semantics are specific to logout hints and do not apply to access tokens calling APIs.

### 5.5. A Hint Does Not Replace Logout Confirmation

The ID Token hint helps the OP identify the session, not prove that the user consented to log out of the OP.

The OP SHOULD ask the End-User whether they want to log out of the OP. The OP MUST ask if `id_token_hint` is absent or if the ID Token does not belong to the current OP session with the RP and/or the currently logged-in user. If the user responds yes, the OP MUST log out the End-User.

### 5.6. Protecting the ID Token Hint

- Do not write raw ID Tokens to application logs.
- Do not include tokens in analytics/tracing.
- Protect the session/cookie where the RP stores the ID Token.
- With GET, the token can appear in URLs, browser history, and proxy logs; consider POST.
- Do not use the hint to authenticate the user for other features.
- Retain the token only as long as necessary according to your retention policy.

## 6. client_id — Identifying the OAuth2 Client

### 6.1. Definition

`client_id` is a valid OAuth 2.0 Client Identifier at the OP. This parameter is OPTIONAL.

It is useful when:

- The RP explicitly specifies the client requesting logout.
- The RP sends `post_logout_redirect_uri` without sending `id_token_hint`.
- The OP needs the client identifier to decrypt a symmetrically encrypted ID Token.
- A deployment has multiple clients/tenants and needs to identify the registration.

### 6.2. When Both client_id and id_token_hint Are Present

This is a MUST rule: when both parameters appear together, the OP MUST verify that the client identifier matches the client used when the ID Token was issued.

Valid example:

~~~text
id_token_hint = ID_TOKEN_ISSUED_TO_booking-bff
client_id     = booking-bff
~~~

Invalid example:

~~~text
id_token_hint = ID_TOKEN_ISSUED_TO_booking-bff
client_id     = expense-portal
~~~

If the OP accepts a mismatched pair, another client could try to use one RP's ID Token to control another RP's logout/redirect.

### 6.3. client_id Is Not client_secret

`client_id` is a public identifier. Do not send `client_secret` to the Logout Endpoint in the query or form body.

The Logout Endpoint handles browser sessions and ID Token hints; it is not the Token Endpoint. Do not use the Token Endpoint's HTTP Basic client authentication as a substitute for the OIDC logout mechanism.

### 6.4. When id_token_hint Is Absent

`client_id` often helps identify the RP when `post_logout_redirect_uri` is sent without a hint. However, knowing a client ID does not mean the OP is allowed to redirect to an arbitrary URL.

If `id_token_hint` is missing alongside `post_logout_redirect_uri`, the OP MUST NOT redirect unless it has another means of confirming the legitimacy of the redirect target. A registered client ID and exact-match URI may be part of that mechanism depending on the implementation; never treat a client ID by itself as a secret or proof of user/session.

## 7. post_logout_redirect_uri — Return Destination After Logout

### 7.1. Definition

`post_logout_redirect_uri` is the URI the RP requests the browser navigate to after the OP completes logout. This parameter is OPTIONAL.

When used:

- The URI MUST be pre-registered with the OP via `post_logout_redirect_uris` or another registration mechanism.
- The URI SHOULD use HTTPS.
- HTTP may be allowed under restricted conditions for confidential clients when permitted by the OP.
- Native apps may use an appropriate alternate scheme.
- The OP MUST match the requested URI exactly against a registered URI.
- The OP MUST NOT redirect if validation fails.

### 7.2. Exact Match, No Wildcards

Suppose the client registered:

~~~text
https://app.example.test/logout/callback
~~~

This URI matches exactly. The following URIs do not match automatically:

~~~text
https://app.example.test/logout/callback/
https://app.example.test/logout/callback?next=/admin
https://app.example.test.evil.test/logout/callback
http://app.example.test/logout/callback
~~~

The OP must perform an exact match against registered URIs, not prefix matching or hostname wildcards. Do not use `startsWith` on the host for validation, as spoofed hostnames can bypass it.

### 7.3. Registering Post-Logout URIs in SAS

~~~java
RegisteredClient bookingBff = RegisteredClient
    .withId("booking-bff-registration")
    .clientId("booking-bff")
    .clientSecret(passwordEncoder.encode(secretFromSecretManager))
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(
        AuthorizationGrantType.AUTHORIZATION_CODE)
    .authorizationGrantType(
        AuthorizationGrantType.REFRESH_TOKEN)
    .redirectUri(
        "https://app.example.test/login/oauth2/code/booking")
    .postLogoutRedirectUri(
        "https://app.example.test/logout/callback")
    .scope("openid")
    .scope("profile")
    .build();
~~~

This is a registration fragment; it requires the corresponding imports/beans and must not store plaintext client secrets. `RegisteredClient.Builder.postLogoutRedirectUri` has been available since SAS 1.1.

### 7.4. post_logout_redirect_uri Differs from redirect_uri

| Parameter | Used At | Purpose |
| --- | --- | --- |
| `redirect_uri` | Authorization Request | Where the OP returns the authorization response/code |
| `post_logout_redirect_uri` | Logout Request | Where the OP sends the browser back after logout |

Both URIs may share the same origin, but they are separate registrations. Do not use the Authorization Code Flow's `redirectUri` in place of a post-logout URI.

### 7.5. Redirect URI Without id_token_hint

OIDC RP-Initiated Logout specifies:

- `id_token_hint` is RECOMMENDED when requesting a post-logout redirect.
- If no hint is provided, the OP MUST have another means of confirming the legitimacy of the redirect target.
- The OP MUST NOT redirect if the URI does not exact-match a registered URI.
- When request validation fails, the OP MUST NOT redirect back to the RP.

Do not fall back to a URL supplied by an arbitrary query parameter.

## 8. state — Correlating Requests and Callbacks

### 8.1. Definition

`state` is an OPTIONAL opaque value generated by the RP to correlate the Logout Request with the callback. If the request includes `state` and the OP redirects the browser back to the RP, the OP returns that exact value via the `state` parameter.

The OP does not need to understand its contents; the RP must manage and verify it on its own.

### 8.2. Generating state Securely

Generate an unpredictable random string (e.g., 256 bits from a secure random generator), Base64URL-encode it, and store the original value tied to the browser session/transaction with a TTL.

Do not put the following inside `state`:

- Refresh/access tokens.
- Client secrets.
- Session cookies.
- Unnecessary personal data.
- Unvalidated arbitrary redirect URLs.

### 8.3. Verifying state at the RP

1. Generate a random state.
2. Store the state tied to the session/transaction.
3. Redirect to the OP.
4. The OP processes logout and echoes `state`.
5. The RP extracts `state` from the callback.
6. Compare it strictly against the stored value.
7. Consume the state after use or upon TTL expiration.
8. Only complete the callback if `state` matches.

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant RP as Relying Party
    participant OP as OpenID Provider
    RP->>RP: Generate random state S
    RP->>RP: Store S with TTL
    RP-->>B: Redirect to OP with state S
    B->>OP: Logout Request
    OP->>OP: Validate and end session
    OP-->>B: Redirect with state S
    B->>RP: GET /logout/callback?state=S
    RP->>RP: Compare callback state with stored state
    alt State matches
        RP->>RP: Consume state and finish
    else Missing, mismatch or replay
        RP->>RP: Reject callback correlation
    end
~~~

### 8.4. Logout state Differs from Login state

The OIDC Authorization Code Flow also uses `state`, but login and logout are two distinct transactions. Do not reuse a login request's `state` for logout. Each logout request requires its own correlation value, a short TTL, and single-use enforcement.

### 8.5. The OP Echoing state Does Not Mean the OP Signs state

The OP returns `state` verbatim, without signing or validating `state` on the RP's behalf. The RP still needs random state, HTTPS, session binding, and one-time validation.

## 9. GET and POST

### 9.1. GET

~~~http
GET /connect/logout?id_token_hint=ID_TOKEN_VALUE&client_id=booking-bff&post_logout_redirect_uri=https%3A%2F%2Fapp.example.test%2Flogout%2Fcallback&state=RANDOM_STATE HTTP/1.1
Host: auth.example.test
~~~

GET is simple to implement, but query parameters can appear in browser history, reverse proxy/access logs, APM, and URL telemetry. Do not log Logout Endpoint queries, or redact sensitive parameters.

### 9.2. POST

~~~http
POST /connect/logout HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

id_token_hint=ID_TOKEN_VALUE&client_id=booking-bff&post_logout_redirect_uri=https%3A%2F%2Fapp.example.test%2Flogout%2Fcallback&state=RANDOM_STATE
~~~

POST places parameters in the form body. The OP MUST support POST and GET; the RP MAY use either. POST reduces placing the ID Token hint in URLs, though the body can still be logged by proxies/APM if not redacted.

### 9.3. Local Logout CSRF Is a Separate Mechanism

The CSRF token protecting the RP's local logout endpoint is not OIDC `state` and does not need to be sent to the OP. Do not disable CSRF for local logout simply because `state` is used in RP-Initiated Logout.

## 10. OP Processing of the Logout Request

### 10.1. Validation Steps

1. Parse the GET query or POST form.
2. If `id_token_hint` is present, verify that the OP is the issuer of the token.
3. If both `client_id` and the hint are present, verify the client match.
4. Identify the End-User/session from the token and session registry.
5. Verify that `post_logout_redirect_uri` belongs to the client's allowlist.
6. If there is no hint, identify the client via a valid mechanism and require confirmation as needed.
7. Only redirect if the target is verified.
8. Terminate the OP session according to processing/consent results.
9. Send logout notifications to RPs registered with a supported mechanism.
10. Redirect back to the RP after processing notifications if the target is valid.

### 10.2. Logout Is Idempotent

OIDC RP-Initiated Logout specifies that an RP requesting logout when the OP no longer considers the user logged in at that RP is not in itself an error. For example, the user already logged out in another tab, the OP session timed out, or the RP retried after a timeout.

### 10.3. When Must the OP Prompt the User?

- The OP SHOULD ask the End-User whether they want to log out of the OP.
- The OP MUST ask if `id_token_hint` is absent.
- The OP MUST ask if the ID Token does not belong to the current OP session with the RP and/or the currently logged-in End-User.
- If the user responds yes, the OP MUST log out the End-User.

### 10.4. When Must the OP Not Redirect?

The OP MUST NOT perform a post-logout redirect if the URI does not exact-match, validation fails, or there is no hint and no other means of confirming the redirect target. The OP may display an error/confirmation page, but must not redirect to an unverified URL.

## 11. Distinguishing Session and Token Layers

| State | How It Ends | Does RP-Initiated Logout Handle It Automatically? |
| --- | --- | --- |
| RP local session | Invalidate HTTP session/cookie | Handled by the RP itself |
| OP browser session | Logout Endpoint | Yes, this is the primary purpose |
| Other RPs | Front-/Back-Channel Logout or Session Management | OP notifies if supported |
| JWT access token | Expiry/denylist/introspection/revocation | Not automatically |
| Refresh token | RFC 7009 revocation or separate policy | Not automatically |
| Remember-me cookie | Local logout handler | Handled by RP/OP respectively |

### 11.1. Local Logout Before or After OP Logout?

OIDC leaves it to the RP to decide whether to perform local logout before redirecting to the OP.

**Local logout first:** the user immediately loses their RP session. If the user declines OP logout, the RP local session is still logged out.

**Local logout afterward:** can wait for the OP to finish, but closing the browser or a failed redirect can leave the local session intact.

A practical choice is often to invalidate the local session immediately, retain the needed ID Token hint in the logout transaction, and then redirect the browser to the OP. If the user declines OP logout, the RP local session has still ended as originally intended.

### 11.2. OP Logout Does Not Automatically Revoke Access Tokens

If an RS verifies JWTs locally, a token can remain valid until `exp`. Logging out the OP session does not modify the JWT or remove the token from the RS.

If logout is required to cut off API access early, use token revocation, opaque tokens + introspection, a denylist/event strategy, or short access token TTLs. This is a separate policy.

### 11.3. RP-Initiated vs. Front-/Back-Channel Logout

- **RP-Initiated:** user clicks logout on RP; RP requests OP logout.
- **Front-Channel:** OP navigates the browser to the RP's logout URI.
- **Back-Channel:** OP calls a server-to-server logout URI with a Logout Token.

RP A calling the OP Logout Endpoint does not guarantee RP B deletes its session unless B implements an appropriate notification mechanism.

## 12. Spring Authorization Server: Enabling the OIDC Logout Endpoint

### 12.1. Enabling OIDC

SAS does not enable OIDC by default. Configuration example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class AuthorizationServerSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurity(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, as ->
                as.oidc(Customizer.withDefaults()))
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

        return http.build();
    }
}
~~~

This is a fragment. A complete application requires `RegisteredClientRepository`, `OAuth2AuthorizationService`, `AuthorizationServerSettings`, issuer/JWK if issuing JWTs, and an application `SecurityFilterChain` for user login.

You can customize `logoutEndpoint` individually through the OIDC configurer if needed. When OIDC is enabled with defaults, OIDC endpoints are configured according to the version/framework.

### 12.2. Configuring the Path

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://auth.example.test")
        .oidcLogoutEndpoint("/connect/logout")
        .build();
}
~~~

The default path is typically `/connect/logout` in SAS 1.x. If you change the path, ensure the OIDC Provider Configuration advertises the corresponding `end_session_endpoint` and that proxies route it correctly.

### 12.3. Registering URIs for a Client

~~~java
RegisteredClient bookingBff = RegisteredClient
    .withId("booking-bff-id")
    .clientId("booking-bff")
    .clientSecret(passwordEncoder.encode(secretFromSecretManager))
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(
        AuthorizationGrantType.AUTHORIZATION_CODE)
    .authorizationGrantType(
        AuthorizationGrantType.REFRESH_TOKEN)
    .redirectUri(
        "https://app.example.test/login/oauth2/code/booking")
    .postLogoutRedirectUri(
        "https://app.example.test/logout/callback")
    .scope("openid")
    .scope("profile")
    .build();
~~~

`RegisteredClient.Builder.postLogoutRedirectUri` has been available since SAS 1.1. If using a JDBC repository, the schema/serialization must persist and read back the registration properly.

### 12.4. Key Components

SAS 1.5.x provides:

- `OidcLogoutEndpointConfigurer`: configures the endpoint and extension points.
- `OidcLogoutEndpointFilter`: receives logout requests.
- `OidcLogoutAuthenticationConverter`: converts the request into an authentication token.
- `OidcLogoutAuthenticationProvider`: validates the request.
- `OidcLogoutAuthenticationSuccessHandler`: handles successful logout and response/redirect.
- `OidcLogoutAuthenticationValidator`: default validator for logout parameters, including post-logout redirect URI.
- `SessionRegistry`: looks up the End-User's session.

Do not create your own controller that takes a redirect URL and redirects directly. Doing so bypasses `RegisteredClient` validation and introduces an open redirect.

### 12.5. Customizing the Endpoint

`OidcLogoutEndpointConfigurer` offers extension points for converter, provider, success handler, and failure handler:

~~~java
authorizationServer.oidc(oidc ->
    oidc.logoutEndpoint(logout ->
        logout
            .logoutRequestConverter(customLogoutRequestConverter)
            .authenticationProvider(customLogoutProvider)
            .logoutResponseHandler(customSuccessHandler)
            .errorResponseHandler(customFailureHandler)
    )
);
~~~

This is a fragment inside the AS configurer. Custom components must preserve protocol validation and the redirect allowlist; do not replace the success handler just to redirect to arbitrary URLs.

### 12.6. Customizing Validation

`OidcLogoutAuthenticationProvider.setAuthenticationValidator(...)` lets you add logic via `OidcLogoutAuthenticationContext`.

~~~java
oidc.logoutEndpoint(logout ->
    logout.authenticationProviders(providers ->
        providers.forEach(provider -> {
            if (provider instanceof OidcLogoutAuthenticationProvider oidcProvider) {
                oidcProvider.setAuthenticationValidator(context -> {
                    OidcLogoutAuthenticationToken request =
                        context.getAuthentication();

                    RegisteredClient registeredClient =
                        context.getRegisteredClient();

                    // Add necessary policy checks.
                    // If validation fails, throw OAuth2AuthenticationException.
                });
            }
        })
    )
);
~~~

This is an illustrative skeleton. The default validator already checks the post-logout redirect URI. Only override when genuinely needed and preserve all required checks. The validator MUST throw `OAuth2AuthenticationException` when validation fails.

## 13. SessionRegistry in SAS

### 13.1. Role

`OidcLogoutAuthenticationProvider` uses `SessionRegistry` to locate the `SessionInformation` associated with the End-User requesting logout. The OIDC Authorization Endpoint also needs to track authenticated sessions.

### 13.2. SessionRegistryImpl and HttpSessionEventPublisher

If no bean is registered, SAS uses the default `SessionRegistryImpl`. If the application registers its own `SessionRegistryImpl`, you should add `HttpSessionEventPublisher` so the registry receives lifecycle events and clears destroyed session metadata.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.web.session.HttpSessionEventPublisher;

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

If using concurrent session control, sharing the same `SessionRegistry` keeps session management and logout aligned on a consistent view of state.

### 13.3. Multi-Instance Deployment

`SessionRegistryImpl` is by default a single-instance in-memory registry. In multi-node systems, a shared session registry/store or proper session clustering is needed.

If login hits node A but the logout request routes to node B, node B may fail to find `SessionInformation`. Test logout during failover/rolling deployments; sticky sessions do not replace shared state design if the system requires failover.

## 14. RP Using Spring Security OAuth2 Client

### 14.1. OidcClientInitiatedLogoutSuccessHandler

Spring Security provides `OidcClientInitiatedLogoutSuccessHandler` for the RP to redirect the browser to the OP after local logout succeeds.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.LogoutSuccessHandler;

@Configuration
class RelyingPartySecurityConfig {

    @Bean
    SecurityFilterChain applicationSecurity(
            HttpSecurity http,
            ClientRegistrationRepository registrations)
            throws Exception {

        LogoutSuccessHandler handler = oidcLogoutSuccessHandler(registrations);

        http
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .logout(logout ->
                logout.logoutSuccessHandler(handler));

        return http.build();
    }

    private LogoutSuccessHandler oidcLogoutSuccessHandler(
            ClientRegistrationRepository registrations) {

        OidcClientInitiatedLogoutSuccessHandler handler =
            new OidcClientInitiatedLogoutSuccessHandler(registrations);

        handler.setPostLogoutRedirectUri("{baseUrl}");
        return handler;
    }
}
~~~

`{baseUrl}` is a placeholder replaced by Spring Security with the application's base URL when processing the request. The resulting URL must be in the allowlist registered at the OP. With multiple hosts/domains, do not let untrusted `Host` headers determine the callback URL.

### 14.2. What Does the Handler Do?

In an OAuth2 Login/OIDC session, the handler can:

- Retrieve the ID Token from the OIDC authentication.
- Read provider metadata to find the OP Logout Endpoint.
- Build a redirect with `id_token_hint`.
- Add `post_logout_redirect_uri` if configured.
- Navigate the browser to the OP using GET by default.

Spring Security **6.5 and above** supports a POST redirect strategy via `FormPostRedirectStrategy` if the application wants to send a form POST. In earlier versions, you need to implement an equivalent redirect strategy yourself or use GET.

### 14.3. Registering the URI on Both Sides

RP configuration:

~~~java
handler.setPostLogoutRedirectUri("{baseUrl}");
~~~

The OP `RegisteredClient` must have the URI matching the actual public base URL, for example:

~~~java
.postLogoutRedirectUri("https://app.example.test")
~~~

If the handler generates `https://app.example.test` while the OP only registered `https://app.example.test/logout/callback`, the request will not match. Choose an explicit callback and register it accurately.

### 14.4. state with the Spring Handler

OIDC Logout defines `state` as OPTIONAL and requires the OP to echo it back. If the application requires explicit state, ensure the handler/flow generates, stores, and validates state according to policy.

Do not assume every version of `OidcClientInitiatedLogoutSuccessHandler` provides full state transaction handling out of the box. You can extend the success handler or implement a redirect strategy with a random state stored alongside the session/transaction.

### 14.5. Form POST Redirect

~~~java
import org.springframework.security.web.FormPostRedirectStrategy;

OidcClientInitiatedLogoutSuccessHandler handler =
    new OidcClientInitiatedLogoutSuccessHandler(clientRegistrationRepository);

handler.setPostLogoutRedirectUri("{baseUrl}");
handler.setRedirectStrategy(new FormPostRedirectStrategy());
~~~

This is a fragment; check the class/package for your Spring Security version. The OP must support POST. POST does not replace HTTPS, URI validation, or state correlation.

## 15. Complete Logout Workflow

~~~mermaid
flowchart TD
    START["User clicks Logout"]
    TOKEN["RP retrieves ID Token hint from OIDC session"]
    STATE["Generate and store state if callback needed"]
    LOCAL["Invalidate local session + clear cookie"]
    DISC["Use end_session_endpoint from metadata"]
    REQ["Send id_token_hint, client_id, redirect URI, state"]
    OP["OP validates hint/client/session/redirect"]
    CONF{"OP requires confirmation?"}
    ASK["Ask user to log out of OP?"]
    DEC{"User agrees?"}
    ENDOP["Terminate OP session"]
    NOTIFY["Send logout notifications if supported"]
    REDIR["Redirect to registered URI with state"]
    CALLBACK["RP verifies state"]
    DONE["Complete"]
    CANCEL["OP session may remain"]

    START --> TOKEN --> STATE --> LOCAL --> DISC --> REQ --> OP --> CONF
    CONF -->|"Yes"| ASK --> DEC
    CONF -->|"No"| ENDOP
    DEC -->|"Yes"| ENDOP --> NOTIFY --> REDIR --> CALLBACK --> DONE
    DEC -->|"No"| CANCEL
    CONF -->|"No prompt needed"| ENDOP
~~~

The diagram depicts one UX option; the order of local logout may vary depending on the application. The OP only redirects after processing notifications and protocol validations.

### 15.1. Without post_logout_redirect_uri

The OP can display a logout completion page. The RP needs a fallback UX, must not redirect to a URL from an untrusted query, and must not claim all other RPs are logged out without notifications/acknowledgements.

### 15.2. Expired OP Session

The RP can still send an ID Token hint so the OP can identify the user/client. Logout requests are idempotent; the absence of an active session is not necessarily an error. The OP may display a result or confirmation page depending on state.

## 16. Securing state, Redirects, and ID Token Hints

### 16.1. Open Redirect

If the OP accepts `post_logout_redirect_uri=https://attacker.example/phishing` without checking an allowlist, an attacker can send the browser away from the OP to a spoofed page.

Defenses:

- Register each URI explicitly.
- Exact match.
- No host/path wildcards.
- No prefix matching.
- Do not let the client alter the allowlist via query parameters.
- Do not redirect when token/client/URI validation fails.

### 16.2. Logout CSRF and Forced Logout

A logout request without a valid hint can be abused to force a user out of the OP, causing denial of service. The spec requires the OP to ask for confirmation when the hint is missing or does not belong to the current session under the stated conditions.

The RP must also protect its local logout endpoint per CSRF policy. Typically, use POST for local logout and keep Spring Security's CSRF protection enabled.

### 16.3. ID Token Hint Is Sensitive Data

An exposed ID Token hint can leak subject/client/session context and be replayed to initiate logout requests. Do not log raw tokens, do not use them as API credentials, and validate issuer/client/session and redirects.

### 16.4. state and Callback CSRF

The RP only completes the callback when `state` matches a pending transaction and has not already been used. Do not use static states like `logout` or `success`. `state` must be random, short-lived, one-time, and session-bound.

### 16.5. Query Strings and Logging

GET requests containing an ID Token hint can expose query parameters in access logs. Redact `id_token_hint` and `state`, disable query capture or filter at the proxy/APM, consider POST form redirects, and do not store raw requests in audit logs.

## 17. Testing RP-Initiated Logout

### 17.1. Parameter Test Matrix

| Test Case | Setup | Expected Result |
| --- | --- | --- |
| Valid ID Token hint | Hint issued by OP, valid RP/session | OP identifies the correct user/session |
| Hint from another issuer | Token not issued by current OP | OP refuses to use the hint |
| Tampered signature hint | Tampered JWT | Validation fails |
| Expired hint, recent session | `exp` passed but `aud`/`sid` has recent session | OP SHOULD accept per spec |
| Expired hint, unrelated session | `sid` does not match current/recent | OP SHOULD treat as suspect, MAY reject |
| `client_id` matches hint | Both belong to same client | Processed normally |
| `client_id` mismatch | Token for `booking-bff`, `client_id` `expense-portal` | OP MUST reject mismatched pair |
| No `client_id` | Valid hint present | OP determines client from token |
| No hint, `client_id` present | Registered client | Identifies client and prompts confirmation when needed |
| Registered URI | Exact match | Can redirect after logout |
| Unregistered URI | Different host/path | Does not redirect |
| Prefix lookalike URI | Attacker domain using prefix | Does not redirect |
| No hint + URI | No other verification means | MUST NOT redirect |
| State present | Random state | OP echoes accurately |
| State mismatch at RP | Different callback state | RP rejects correlation |
| State replay | Reusing old state | RP rejects |
| No `post_logout_redirect_uri` | Valid logout | OP displays result/fallback |
| GET request | Query serialization | OP processes |
| POST request | Form serialization | OP processes |
| Local logout | User logs out at RP | RP session invalidated |
| OP logout | User approves | OP session terminated |
| User declines | Confirmation declined | Do not assume OP session ended |
| Multiple RPs | OP session shared by multiple clients | Notifications sent per registered mechanism |
| Refresh/access token | OP session logout | Do not assume tokens are revoked by default |

### 17.2. MockMvc Test for Redirect URI

~~~java
@Test
void unregisteredPostLogoutRedirectUriMustNotRedirect() throws Exception {
    mockMvc.perform(get("/connect/logout")
            .param("id_token_hint", validIdTokenHint)
            .param("client_id", "booking-bff")
            .param(
                "post_logout_redirect_uri",
                "https://attacker.example/callback")
            .param("state", "random-state"))
        .andExpect(result ->
            assertThat(result.getResponse().getRedirectedUrl())
                .isNotEqualTo("https://attacker.example/callback"));
}
~~~

This is an illustrative test body; a real test needs `@SpringBootTest`/`@AutoConfigureMockMvc`, session/`RegisteredClient`, an ID Token, and the real filter chain. Do not check status alone; verify that it does not redirect to a host outside the allowlist.

### 17.3. Testing Client Mismatch

Generate an ID Token issued for `booking-bff` and send:

~~~http
GET /connect/logout?id_token_hint=TOKEN_FOR_BOOKING&client_id=expense-portal
~~~

Expected:

- The OP detects the mismatch.
- Does not process it as if the token were issued for `expense-portal`.
- Does not redirect to the other client's URI.
- Does not leak user/session details in the error response.

### 17.4. Testing state at the RP

- Generate a random state and save the transaction.
- Callback with matching state: succeeds, state is consumed.
- Callback with wrong state: rejected.
- Callback without state when transaction requires it: rejected.
- State replay: rejected.
- Expired TTL state: rejected.
- State contains no tokens/secrets/arbitrary URLs.

### 17.5. Testing Local and OP Sessions Independently

1. Log into the RP and OP.
2. Perform local RP logout without calling the OP yet.
3. Confirm the RP local session is gone.
4. Open a second RP; while the OP session remains, the OP can SSO.
5. Perform RP-Initiated Logout.
6. Confirm the OP session ends after user approval.
7. Verify logout notifications to the second RP if configured.
8. Verify access/refresh tokens according to the separate revocation strategy.

## 18. Operations and Troubleshooting

### 18.1. Common Issues

| Symptom | Cause | How to Check |
| --- | --- | --- |
| OP returns 404 at `/connect/logout` | OIDC not enabled or different path | OIDC configurer/`AuthorizationServerSettings` |
| Discovery missing `end_session_endpoint` | OIDC discovery/logout not configured | Provider Configuration endpoint |
| Does not redirect back to RP | URI unregistered or mismatched | `RegisteredClient.postLogoutRedirectUris` |
| Client mismatch | `client_id` does not match ID Token hint | Token audience/client registration |
| Expired hint rejected | Session not recognized or version behavior | SAS version/session store |
| User still logged in at OP | Only local logout ran or user declined OP logout | OP session cookie/confirmation |
| State mismatch | State lost, altered, expired, or different session | Correlation store/TTL/proxy |
| Redirect to unknown host | Weak open redirect validator | Exact-match allowlist |
| RP handler cannot find endpoint | `ClientRegistration` missing discovery metadata | OIDC provider configuration |
| Inconsistent multi-node logout | Local `SessionRegistry` | Shared session/registry |
| GET token appears in logs | Query capture in proxy/APM | Redaction or POST |
| RP2 still has a session | Front/back-channel notification not configured | Logout registration |
| API still accepts JWT after logout | Logout does not revoke JWTs | Introspection/denylist/TTL |
| Handler redirects to wrong host | `{baseUrl}` built from untrusted headers | Trusted public base URL/forwarded headers |
| POST does not work | Proxy/filter only allows GET | Method routing/form serialization |

### 18.2. Runbook When Logout Does Not Return to the RP

1. Fetch `end_session_endpoint` from the OIDC metadata of the right issuer.
2. Check that the Logout Endpoint is enabled and routed via public HTTPS.
3. Read redacted request parameters.
4. Verify the ID Token hint belongs to the right issuer/client.
5. Verify `client_id` matches the ID Token if both are present.
6. Verify `post_logout_redirect_uri` exact-matches `RegisteredClient`.
7. Check whether the OP required confirmation and whether the user agreed.
8. Check that OP notifications completed before redirecting.
9. Verify the browser callback receives `state` intact.
10. Check the RP state store, TTL, and session binding.

Never work around issues by adding wildcard URIs or disabling the validator.

### 18.3. Metrics and Auditing

| Metric | Purpose |
| --- | --- |
| Logout request count by client | Know which clients use logout |
| ID Token hint validation failures | Detect issuer/client/session mismatches |
| `client_id` mismatch count | Detect malformed requests/abuse |
| Redirect URI validation failures | Detect open redirect attempts/misconfigurations |
| Confirmation accepted/declined | Track OP logout UX |
| `SessionRegistry` lookup miss | Detect stale session/cluster issues |
| RP callback state mismatch | Detect correlation/CSRF problems |
| Front/back-channel notification failures | Track propagation |
| Logout endpoint 4xx/5xx | Availability/protocol issues |
| Access token still active after logout | Distinguish logout from revocation |

Do not log raw ID Token hints, `state`, session cookies, or access/refresh tokens. Audit logs can record client ID, correlation ID, redirect registration identifier, and protected outcome codes.

## 19. Common Mistakes

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Sending an access token as `id_token_hint` | OP cannot properly identify the OIDC session | Use the ID Token issued by the OP |
| Omitting hint on every request | OP struggles to identify the session; redirect needs other verification | Send the hint when available |
| Trusting `client_id` even when hint belongs to another client | Client/session confusion | MUST verify client match |
| Using Authorization Code `redirect_uri` for logout | Wrong registration contract | Register `post_logout_redirect_uri` separately |
| Allowing arbitrary redirect URIs | Open redirect/phishing | Exact-match allowlist |
| Prefix-matching domains | Spoofed hosts bypass check | Match URIs exactly |
| Using static `state` | Callback forgery/replay | Random state, session-bound, one-time |
| Assuming OP signs `state` | RP skips verifying callback | RP verifies state itself |
| Assuming OP logout revokes JWTs | APIs still accept tokens locally | Revocation/denylist/introspection |
| Assuming RP logout logs out every RP | OP session still remains | RP-Initiated + notification mechanisms |
| Rejecting all expired hints | Logging out recent sessions may fail | Recent-session semantics |
| Logging full logout query strings | Exposes ID Token/state | Redaction/POST |
| Disabling local logout CSRF | Logout CSRF | Protect local logout endpoint |
| Not controlling `baseUrl` | Redirect mismatch/host poisoning | Trusted public base URL |
| Testing only HTTP response status | Does not prove session termination | Test local/OP/`SessionRegistry` |
| Using only an in-memory registry in a cluster | Other nodes cannot see the session | Shared session/registry |
| Custom handler skipping the validator | Open redirect | Keep validation and test it |

## 20. Self-Check Questions

**Question 1.** What is `id_token_hint`?  
**Answer:** An ID Token previously issued by the OP to the RP, used as a hint for the OP to identify the End-User/client/session to log out.

**Question 2.** Can an access token be used instead of `id_token_hint`?  
**Answer:** No. RP-Initiated Logout specifies an ID Token hint; access tokens are for authorizing requests to Resource Servers.

**Question 3.** Is an expired ID Token hint always rejected?  
**Answer:** No. The OP SHOULD accept it if `aud`/`sid` identifies a current/recent session, even if `exp` has passed; the OP still verifies the issuer and session context.

**Question 4.** If both `client_id` and `id_token_hint` are present, what is the mandatory condition?  
**Answer:** The OP MUST verify that `client_id` matches the client used when issuing the ID Token.

**Question 5.** Can `post_logout_redirect_uri` use wildcards?  
**Answer:** Not under the standard mechanism; the OP MUST exact-match a registered URI.

**Question 6.** Without an ID Token hint but with a post-logout URI, can the OP always redirect?  
**Answer:** No. The OP MUST have another means of confirming that the redirect target is legitimate.

**Question 7.** Who verifies `state`?  
**Answer:** The RP creates/stores and checks the callback state; the OP echoes the value verbatim.

**Question 8.** Must the OP support both GET and POST?  
**Answer:** Yes. RP-Initiated Logout 1.0 requires the OP MUST support both.

**Question 9.** Does the Logout Endpoint automatically revoke JWT access tokens?  
**Answer:** No. Token revocation/introspection/denylist/TTL are separate mechanisms.

**Question 10.** Which component does SAS use to look up logout sessions?  
**Answer:** `OidcLogoutAuthenticationProvider` uses `SessionRegistry` to look up `SessionInformation`.

**Question 11.** Which handler in Spring Security OAuth2 Client supports RP-Initiated Logout?  
**Answer:** `OidcClientInitiatedLogoutSuccessHandler`.

**Question 12.** Why not use `redirect_uri` for the post-logout callback?  
**Answer:** `redirect_uri` is for the Authorization Response; `post_logout_redirect_uri` is a separate registration/parameter.

## 21. Production Checklist

- [ ] OP publishes `end_session_endpoint` in OIDC Provider metadata.
- [ ] Logout Endpoint uses HTTPS and supports GET + POST.
- [ ] RP obtains the endpoint from issuer-verified discovery.
- [ ] RP sends the ID Token hint matching the right OP/client when available.
- [ ] OP verifies the ID Token hint was issued by itself.
- [ ] OP handles expired hints per current/recent session semantics.
- [ ] `client_id` matches the client issued the ID Token if both are present.
- [ ] `post_logout_redirect_uri` is registered separately per client.
- [ ] OP exact-matches URIs, with no wildcard/prefix matching.
- [ ] No redirect occurs when URI validation fails.
- [ ] When a hint is missing, another means exists to confirm a valid redirect target.
- [ ] `state` is random, session-bound, short-lived, and one-time.
- [ ] RP verifies callback `state` before completing.
- [ ] Local logout has CSRF protection.
- [ ] ID Token hint/`state` are not logged raw.
- [ ] UX handles OP confirmation/decline.
- [ ] `SessionRegistry` works properly across multiple instances.
- [ ] Front/back-channel logout is configured if logging out other RPs is required.
- [ ] Token revocation is designed separately if APIs must stop accepting tokens early.
- [ ] Tests exist for hint issuer/expiry, client mismatch, redirect mismatch, state replay, and session lookup.
- [ ] Runbook and metrics exist for logout propagation.

## 22. References and Conclusion

- [OpenID Connect RP-Initiated Logout 1.0 Final](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html)
- [RP-Initiated Logout — Section 2: Logout Request Parameters](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html#RPLogout)
- [RP-Initiated Logout — Section 2.1: OP Discovery Metadata](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html#OPMetadata)
- [RP-Initiated Logout — Section 3: Redirection to RP After Logout](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html#Redirection)
- [RP-Initiated Logout — Section 4: Validation and Error Handling](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html#Validation)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html)
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [Spring Authorization Server 1.5.x — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — OidcLogoutEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OidcLogoutEndpointConfigurer.html)
- [Spring Authorization Server — OidcLogoutAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcLogoutAuthenticationProvider.html)
- [Spring Authorization Server — RegisteredClient.Builder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/client/RegisteredClient.Builder.html)
- [Spring Authorization Server — SessionRegistry](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Security — OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html)
- [Spring Security 6.4 — OidcClientInitiatedLogoutSuccessHandler API](https://docs.spring.io/spring-security/site/docs/6.4.8/api/org/springframework/security/oauth2/client/oidc/web/logout/OidcClientInitiatedLogoutSuccessHandler.html)

**Conclusion:** `id_token_hint` helps the OP identify the user/client/session; `client_id` supplements client identification and MUST match the ID Token hint if both appear; `post_logout_redirect_uri` is a pre-registered callback and must match exactly; `state` is an opaque value used by the RP to verify callback correlation. When implementing with Spring Authorization Server, enable the OIDC Logout Endpoint, register separate URIs on `RegisteredClient`, and maintain an accurate `SessionRegistry`. The RP can use `OidcClientInitiatedLogoutSuccessHandler` or an equivalent flow with explicit state/redirect checks. Finally, separate local logout, OP session logout, logout notifications, and OAuth2 token revocation so you do not create the illusion of complete logout while access/refresh tokens or sessions in other applications remain active.
