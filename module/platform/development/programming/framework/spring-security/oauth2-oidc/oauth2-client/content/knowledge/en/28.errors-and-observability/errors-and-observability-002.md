# 28.2. OAuth2AuthenticationException, OAuth2AuthorizationException, and OAuth2Error

## 1. The Problem: All OAuth2 Errors, Yet Handled at Different Layers

A Spring Boot application uses **Spring Security OAuth 2.0/OIDC Client** to sign in via an OpenID Provider (OP). After signing in, the backend uses the issued access token to call the Reports API. One day, the operations team encounters three situations:

1. The user clicks **Deny** on the consent screen. The browser returns to the callback with <code>error=access_denied</code>. Spring Security handles the login error.
2. The user has a valid login, but the access token used to call the Reports API is about to expire. The backend calls refresh token; the Token Endpoint returns <code>invalid_grant</code>.
3. The backend has an unexpired access token, but the Resource Server returns HTTP 403 with Bearer <code>insufficient_scope</code>.

If all three are lumped into "OAuth2 error → clear session → redirect to login", the application can cause login loops, mistakenly log out users, lose a newer token saved by another node, or mask the real configuration issue.

To handle them accurately, we need to distinguish three types in Spring Security:

- **<code>OAuth2Error</code>:** an object carrying details of an error according to the OAuth2 model.
- **<code>OAuth2AuthenticationException</code>:** an exception tied to the authentication process, containing an <code>OAuth2Error</code>.
- **<code>OAuth2AuthorizationException</code>:** an exception tied to an OAuth2 authorization or authorized-client/token operation, also containing an <code>OAuth2Error</code>.

The same error code can appear at multiple stages. **Exception name, OAuth2 error code, and HTTP status are three different dimensions of information.**

> **Guiding principle:** To react properly, you must know whether the error occurred at the **Authorization Endpoint callback**, **Token Endpoint**, **UserInfo Endpoint**, **authorized-client manager**, or **Resource Server**; only then look at <code>getError().getErrorCode()</code>.

## 2. Lesson Objectives

After this lesson, you will be able to:

1. Read <code>error</code>, <code>error_description</code>, and <code>error_uri</code> in the OAuth2 protocol and map them to <code>OAuth2Error</code>.
2. Distinguish <code>OAuth2AuthenticationException</code> and <code>OAuth2AuthorizationException</code> by origin and failure handling.
3. Understand why <code>invalid_grant</code> during authorization-code login differs from <code>invalid_grant</code> during token refresh.
4. Configure Spring Security OAuth2 Login failure handlers for **Servlet** and **Reactive WebFlux**.
5. Handle <code>OAuth2AuthorizationException</code> when calling <code>OAuth2AuthorizedClientManager</code> or its reactive counterpart.
6. Avoid equating Resource Server HTTP 401/403 responses with Token Endpoint exceptions.
7. Design error classification, HTTP mapping, retry, reauthorization, and token cleanup policies.
8. Record logs, metrics, and traces safely without leaking credentials, authorization codes, or personal data.
9. Build unit tests and integration scenarios for callbacks, token requests, refresh, and downstream APIs.

## 3. Error Handling Map

~~~mermaid
flowchart TD
    B["Browser"] --> INIT["OAuth2/OIDC Login"]
    INIT --> OP["OpenID Provider"]
    OP -->|"Callback error=access_denied"| AUTH["Authentication failure pipeline"]
    OP -->|"Authorization code"| TOKEN["Token Endpoint"]
    TOKEN -->|"invalid_client / invalid_grant"| GRANT["Token/authorization processing"]
    GRANT -->|"When error belongs to login"| AUTH
    AUTH --> AE["OAuth2AuthenticationException or other AuthenticationException"]
    GRANT --> AZ["OAuth2AuthorizationException or translated error"]
    AE --> ERR["OAuth2Error"]
    AZ --> ERR
    B --> APP["Authenticated Application"]
    APP --> M["OAuth2AuthorizedClientManager"]
    M -->|"Refresh/client credentials"| TOKEN
    M -->|"Authorize failure"| AZ
    APP --> API["Resource Server"]
    API -->|"HTTP 401 / 403"| H["HTTP client error handling"]
~~~

This diagram is **conceptual**. Spring Security may wrap, translate, or handle exceptions inside an authentication provider/filter, so you should not assume every OAuth2 Login error is thrown directly as the exact same class across all versions.

### 3.1. Comparison Table

| Component | Nature | Where Commonly Seen | Key Information |
|---|---|---|---|
| <code>OAuth2Error</code> | Value object | Token errors, authorization errors, validation errors | Error code, description, URI |
| <code>OAuth2AuthenticationException</code> | <code>AuthenticationException</code> | OAuth2/OIDC Login, authentication providers | <code>getError()</code>, cause |
| <code>OAuth2AuthorizationException</code> | Exception for OAuth2 authorization | Token request, refresh, authorized-client operation | <code>getError()</code>, cause |
| HTTP client exception | HTTP communication error | WebClient/RestClient calling Resource Server | HTTP status, headers, response |
| <code>AccessDeniedException</code> | Spring Security authorization | Role, tenant, method security, route security | Access permission denied |

**Do not equate:** <code>OAuth2AuthenticationException</code> = HTTP 401, <code>OAuth2AuthorizationException</code> = HTTP 403. These names reflect framework context, not HTTP conversion rules.

## 4. OAuth2Error: A Data Object, Not Yet an Exception

Class:

~~~java
org.springframework.security.oauth2.core.OAuth2Error
~~~

An OAuth2 protocol error typically has three fields:

~~~json
{
  "error": "invalid_grant",
  "error_description": "The authorization code is expired",
  "error_uri": "https://auth.example.org/docs/errors/invalid-grant"
}
~~~

In Spring Security:

| OAuth2 field | Java method | Role |
|---|---|---|
| <code>error</code> | <code>getErrorCode()</code> | Machine-classifiable error code |
| <code>error_description</code> | <code>getDescription()</code> | Additional description, may be null |
| <code>error_uri</code> | <code>getUri()</code> | Documentation URI, may be null |

### 4.1. Creating OAuth2Error

~~~java
import org.springframework.security.oauth2.core.OAuth2Error;

OAuth2Error error = new OAuth2Error(
    "invalid_grant",
    "Authorization code is no longer valid",
    "https://auth.example.org/docs/errors/invalid-grant");

String code = error.getErrorCode();
String description = error.getDescription();
String uri = error.getUri();
~~~

There is also a code-only constructor:

~~~java
OAuth2Error simple = new OAuth2Error("invalid_request");
~~~

### 4.2. OAuth2Error Is Not an HTTP Response

The <code>OAuth2Error</code> object does not itself carry the HTTP status of the original response or the status the Portal should return to the browser.

For example, <code>invalid_grant</code> at the Token Endpoint is usually in an HTTP 400 JSON response, but when the Client encounters the same code during a browser login, the failure handler may redirect back to the login page. In an authenticated BFF request, a failed refresh may require a separate response or reauthorization.

Do not infer:

~~~text
error.getErrorCode() == "invalid_grant"
⇒ Portal must always return HTTP 401
~~~

### 4.3. OAuth2ErrorCodes Are Constants, Not Specific Errors

Spring Security provides <code>OAuth2ErrorCodes</code> containing several standard codes:

~~~java
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;

OAuth2Error error = new OAuth2Error(
    OAuth2ErrorCodes.INVALID_GRANT);
~~~

<code>OAuth2ErrorCodes.INVALID_GRANT</code> is the string <code>"invalid_grant"</code>; <code>OAuth2Error</code> is the object holding details of a specific error.

Provider-specific error codes do not necessarily have constants in <code>OAuth2ErrorCodes</code>; do not force every unfamiliar code into <code>invalid_grant</code>.

### 4.4. Do Not Fully Trust error_description

<code>error_description</code> can originate from the OP, a gateway, or an external integration. It may:

- Contain internal configuration details, usernames, or user-submitted data.
- Change wording when the provider is upgraded.
- Contain characters that cause log injection or unsafe HTML if rendered directly.
- Be too long to use as a metric label.

Do not return directly:

~~~java
response.getWriter().write(error.getDescription());
~~~

without encoding controls, validation, and a user-facing policy.

### 4.5. error_uri Is Not a Trusted Redirect Target

Do not write:

~~~java
response.sendRedirect(error.getUri());
~~~

with an unvalidated URI. An <code>error_uri</code> is documentation metadata, not a redirect URI trusted by the Portal. If a help link is needed, map the error category to an internal help page or an allowlisted URI controlled by the backend.

## 5. OAuth2AuthenticationException: Error During Authentication

Class:

~~~java
org.springframework.security.oauth2.core.OAuth2AuthenticationException
~~~

This is a type of Spring Security <code>AuthenticationException</code>. It carries an <code>OAuth2Error</code>, allowing the framework to handle the error within the **authentication pipeline**.

~~~java
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;

OAuth2Error error = new OAuth2Error(
    "invalid_id_token",
    "Unexpected ID Token issuer",
    null);

throw new OAuth2AuthenticationException(error);
~~~

This is an example for a **custom validation component**; it is not advice to replace default OIDC signature/issuer/nonce verification yourself.

### 5.1. Where Can OAuth2 Login Fail?

In Servlet OAuth2 Login, the components may include:

~~~text
OAuth2AuthorizationRequestRedirectFilter
OAuth2LoginAuthenticationFilter
OAuth2LoginAuthenticationProvider
OidcAuthorizationCodeAuthenticationProvider
OAuth2UserService / OidcUserService
AuthenticationFailureHandler
~~~

Typical errors:

1. OP returns <code>access_denied</code> when the user denies consent.
2. Authorization response fails to correlate with <code>state</code> and the original authorization request.
3. Token Endpoint rejects the code or Client authentication.
4. ID Token has wrong issuer, audience, signature, expiry, or nonce.
5. UserInfo endpoint returns an unacceptable response.
6. Internal mapping rejects an inactive/disabled account after identity verification.

Not all of the errors above are guaranteed to have the same exception class or error code across every Spring Security version. In particular, technical I/O, session storage, or custom mapping errors may be wrapped/translated.

### 5.2. Browser Consent Denied

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant OP as OpenID Provider
    participant RP as Spring Security Client
    participant FH as AuthenticationFailureHandler
    B->>RP: GET /oauth2/authorization/company
    RP-->>B: Redirect OP, state=S1
    B->>OP: Authorization request state=S1
    U->>OP: Deny consent
    OP-->>B: Redirect error=access_denied&state=S1
    B->>RP: GET /login/oauth2/code/company?error=access_denied&state=S1
    RP->>RP: Validate request correlation, process OAuth2 error
    RP->>FH: Authentication failure
    FH-->>B: Redirect /login?error=oauth2
~~~

A user declining consent is a valid possible outcome, not necessarily a system intrusion or OP outage.

### 5.3. Reading OAuth2Error from an Exception

~~~java
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;

void classify(AuthenticationException failure) {
    if (failure instanceof OAuth2AuthenticationException oauthFailure) {
        OAuth2Error error = oauthFailure.getError();
        String code = error.getErrorCode();
        // Translate code into a safe category and message.
    } else {
        // May be another authentication exception.
    }
}
~~~

Do not blindly cast every <code>AuthenticationException</code> to <code>OAuth2AuthenticationException</code>, because login can also fail with other exception types.

### 5.4. Authentication Failure Does Not Allow Skipping Trust Validation

Do not write:

~~~text
ID Token signature/issuer validation failed
    → ignore
    → read email from unverified JWT
    → create authenticated principal
~~~

An OIDC Client must reject authentication when essential validation fails. Availability cannot be improved by marking a user as authenticated from untrusted claims.

## 6. OAuth2AuthorizationException: Authorization/Authorized-Client Error

Class:

~~~java
org.springframework.security.oauth2.core.OAuth2AuthorizationException
~~~

This exception also contains an <code>OAuth2Error</code>, but is typically used when **OAuth2 authorization or a token operation** cannot complete.

~~~java
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;

OAuth2Error error = new OAuth2Error(
    OAuth2ErrorCodes.INVALID_GRANT,
    "Refresh token rejected",
    null);

throw new OAuth2AuthorizationException(error);
~~~

### 6.1. Role of OAuth2AuthorizedClient

<code>OAuth2AuthorizedClient</code> represents a ClientRegistration that has been issued an access token for a principal:

~~~text
clientRegistrationId
principalName
accessToken
refreshToken (if present)
~~~

<code>OAuth2AuthorizedClientManager</code> can load an existing token, decide to refresh/request a token when needed, and save the new token. During that process, Token Endpoint or authorization provider errors can be represented by <code>OAuth2AuthorizationException</code> or handled via the authorized-client failure infrastructure.

### 6.2. A Failed Refresh Token Flow

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Browser
    participant APP as Portal
    participant M as AuthorizedClientManager
    participant DB as Authorized Client Store
    participant OP as Token Endpoint
    participant API as Reports API
    U->>APP: GET /reports, authenticated session
    APP->>M: authorize(company, user-123)
    M->>DB: Load authorized client
    DB-->>M: Access expired, refresh token R0
    M->>OP: grant_type=refresh_token&refresh_token=R0
    OP-->>M: 400 invalid_grant
    M-->>APP: OAuth2AuthorizationException / failure handling
    APP-->>U: Policy-based response, no token leakage
    Note over API: API may not have been called yet
~~~

**The Portal HTTP session and the OAuth2 authorized client are two distinct states.** A rejected refresh token does not by itself prove the user is unauthenticated in the Portal; depending on the product, you may need to reauthorize the specific registration or terminate the session.

### 6.3. AuthorizationException Is Not Business Access Denied

If a user lacks the <code>ROLE_BILLING_ADMIN</code> role to call a business API, that is an application or Resource Server permission/authorization issue. Do not create:

~~~java
throw new OAuth2AuthorizationException(
    new OAuth2Error("invalid_grant"));
~~~

to represent every HTTP 403 case. <code>invalid_grant</code> means an OAuth2 grant was rejected, not that the user lacks arbitrary business permissions.

### 6.4. Comparing When Error Codes Are Identical

~~~java
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;

OAuth2Error error = new OAuth2Error("invalid_grant");

var loginFailure = new OAuth2AuthenticationException(error);
var tokenFailure = new OAuth2AuthorizationException(error);

System.out.println(loginFailure.getError().getErrorCode());
System.out.println(tokenFailure.getError().getErrorCode());
~~~

Both return <code>invalid_grant</code>. However, **how the application reacts must be based on the operation and stage**, not solely on the code.

## 7. Error Sources in the OAuth2/OIDC Protocol

### 7.1. Authorization Endpoint Callback

The browser may receive a redirect:

~~~http
HTTP/1.1 302 Found
Location: https://portal.example.org/login/oauth2/code/company?error=access_denied&state=STATE_VALUE
~~~

The error arrives on the **authorization response via the browser**. The Client must correlate state/request and never accept a forged callback from an attacker's website as valid.

### 7.2. Token Endpoint

The Client sends:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=SECRET_VALUE
~~~

The server returns:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_grant",
  "error_description": "Refresh token expired or revoked"
}
~~~

In code, the error can be converted by the token response client into an <code>OAuth2AuthorizationException</code> and propagated up to the authorized-client manager.

### 7.3. UserInfo Endpoint

An OIDC Client may call the UserInfo endpoint with the access token. HTTP 401/403 from UserInfo differs from a browser callback state mismatch. You must verify token audience/scope, UserInfo contract, and claims policy.

### 7.4. Resource Server

The backend calls:

~~~http
GET /v1/reports HTTP/1.1
Host: api.example.org
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

The Resource Server returns:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope",
                  scope="reports.write"
~~~

This is a **downstream HTTP response**, which does not necessarily throw <code>OAuth2AuthorizationException</code> directly. <code>WebClient</code>/<code>RestClient</code> may throw its own HTTP response exception.

### 7.5. Internal Application Policy

OIDC Login is verified, but the user belongs to an internal account that is disabled:

~~~text
OP authentication succeeds
    ↓
Internal user profile says DISABLED
    ↓
Portal denies application login
~~~

This is the **Portal's** policy, not a reason to attribute <code>invalid_grant</code> to the OP. If the application creates a custom <code>OAuth2AuthenticationException</code>, use a distinct internal error code rather than faking an error returned by the Token Endpoint.

## 8. Common Error Codes and Their Contexts

| Error Code | Common Source | Meaning | First Investigation Step |
|---|---|---|---|
| <code>invalid_request</code> | Authorization/Token Endpoint | Missing/invalid request parameter | Check converter, scope, URI, and form encoding |
| <code>unauthorized_client</code> | Authorization/Token Endpoint | Client not allowed to use grant/flow | Check ClientRegistration policy |
| <code>access_denied</code> | Authorization Endpoint | User/OP denied authorization | Return to login; do not blindly retry |
| <code>unsupported_response_type</code> | Authorization Endpoint | Response type not supported | Fix registration/flow |
| <code>invalid_scope</code> | Authorization/Token Endpoint | Invalid or disallowed scope | Check consent and provider policy |
| <code>server_error</code> | Authorization Endpoint, some extensions | OP encountered a server error | Assess upstream availability |
| <code>temporarily_unavailable</code> | Authorization Endpoint | OP temporarily unavailable | Bounded retry/backoff per flow |
| <code>invalid_client</code> | Token Endpoint | Client authentication failed | Secret/key/JWT client assertion/mTLS |
| <code>invalid_grant</code> | Token Endpoint | Code/refresh grant invalid | Expiry, reuse, PKCE, revocation, race |
| <code>unsupported_grant_type</code> | Token Endpoint | Grant type not supported | Provider capability and registration |
| <code>invalid_token</code> | Resource Server Bearer challenge | Access token rejected | Issuer/audience/expiry/revocation |
| <code>insufficient_scope</code> | Resource Server Bearer challenge | Missing scope | Scope/consent/Resource Server policy |
| <code>login_required</code> | OIDC Authorization Endpoint | Cannot perform silent login | Switch to interactive flow when appropriate |
| <code>interaction_required</code> | OIDC Authorization Endpoint | UI interaction required | Do not loop prompt=none retries |
| <code>consent_required</code> | OIDC Authorization Endpoint | Consent required | Let user interact if policy permits |

These codes come from multiple RFCs/profiles. **Not all of them are valid in Token Endpoint JSON**, and there is no one-to-one mapping to Portal HTTP statuses.

### 8.1. invalid_client

Causes:

- Client secret was rotated, but some nodes still hold the old secret.
- Wrong or disabled Client ID.
- OP requires <code>private_key_jwt</code>, while Client sends <code>client_secret_basic</code>.
- JWT client assertion has wrong <code>iss</code>/<code>sub</code>/<code>aud</code>, expiry, key, or signature.
- mTLS certificate is wrong or expired.

This is usually a **Client authentication/infrastructure configuration** issue, not something re-entering a user password will fix.

### 8.2. invalid_grant in Authorization Code

Can be caused by:

- Code expired or reused.
- Callback/redirect URI mismatch.
- <code>code_verifier</code> fails PKCE match.
- Code was issued for a different ClientRegistration.
- Grant rejected by OP policy.

Do not disable <code>state</code> or PKCE checks just to make login work when encountering <code>invalid_grant</code>.

### 8.3. invalid_grant in Refresh Token

Can be caused by:

- Refresh token expired or revoked.
- OP enables rotation and R0 was already used by another request.
- OP detected token reuse and revoked the token family.
- Refresh token bound to a different Client/issuer.
- Refresh result was not persisted properly, causing reuse of R0.

With multiple replicas, **do not assume invalid_grant means the user intentionally logged out**.

### 8.4. insufficient_scope

A JWT access token with a valid signature and expiry can still lack the <code>reports.write</code> scope. The Resource Server returns 403; refreshing with the same scope generally does not elevate permissions. Check grant consent, Resource Server audience, and role/tenant ownership.

## 9. Servlet OAuth2 Login: AuthenticationFailureHandler

In the Servlet stack, <code>oauth2Login()</code> can attach an <code>AuthenticationFailureHandler</code> to handle errors in the login filter.

### 9.1. Dependencies and OIDC Registration

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

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

### 9.2. Failure Handler Returning a Safe Message

~~~java
package example.security;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;

public final class SafeLoginFailureHandler
        implements AuthenticationFailureHandler {

    private static final Logger log =
        LoggerFactory.getLogger(SafeLoginFailureHandler.class);

    @Override
    public void onAuthenticationFailure(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException failure) throws IOException {

        String category = "authentication_failed";

        if (failure instanceof OAuth2AuthenticationException oauth2Failure) {
            String code = oauth2Failure.getError().getErrorCode();
            category = "access_denied".equals(code)
                ? "user_denied" : "oauth2_failure";
        }

        // Log only bounded category; do not log raw code/state/token.
        log.warn("oauth2_login_failed category={}", category);

        // Fixed internal redirect; do not use error_uri or arbitrary nextUrl.
        response.sendRedirect(
            request.getContextPath() + "/login?error=oauth2");
    }
}
~~~

In production, you can add a correlation ID, provider alias, and metric tags, while avoiding raw error descriptions or URL queries containing <code>code</code> or <code>state</code>.

### 9.3. Wiring into SecurityFilterChain

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OAuth2LoginSecurityConfig {

    @Bean
    SafeLoginFailureHandler safeLoginFailureHandler() {
        return new SafeLoginFailureHandler();
    }

    @Bean
    SecurityFilterChain webChain(
            HttpSecurity http,
            SafeLoginFailureHandler failureHandler)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/login", "/error", "/assets/**")
                    .permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .loginPage("/login")
                .failureHandler(failureHandler))
            .csrf(Customizer.withDefaults());

        return http.build();
    }
}
~~~

The <code>/login?error=oauth2</code> page should show a curated message, such as "Sign-in was not completed. Please try again or contact support."

### 9.4. Failure Handler Does Not Manage All Exceptions

<code>oauth2Login().failureHandler(...)</code> operates within the **login authentication pipeline**. It does not automatically catch:

- A service calling <code>OAuth2AuthorizedClientManager</code> whose refresh fails after login.
- HTTP 403 when <code>WebClient</code> calls the Reports API.
- Background job failures.
- Errors in arbitrary controllers outside the authentication filter.

Those points need their own error handling. <code>@ControllerAdvice</code> also **does not replace** the login failure handler because OAuth2 Login callbacks are typically processed in Spring Security filters before reaching a controller.

## 10. Servlet: Handling OAuth2AuthorizationException in the Manager

A service in the Portal might do:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;

OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("company")
        .principal(authentication)
        .build();

try {
    OAuth2AuthorizedClient client = manager.authorize(request);

    if (client == null) {
        throw new IllegalStateException("No authorized client available");
    }

    // Use the access token of the right ClientRegistration/principal.
} catch (OAuth2AuthorizationException ex) {
    String code = ex.getError().getErrorCode();
    // Classify code + operation + registration, then recover.
}
~~~

This is an **abbreviated snippet** assuming the method already has <code>manager</code> and <code>authentication</code>. With <code>DefaultOAuth2AuthorizedClientManager</code> in Servlet, the web repository's request/response context may need to be supplied or obtained from the integration; a service manager for background jobs uses a different store.

### 10.1. A Null Result Is Not an OAuth2Error

<code>OAuth2AuthorizedClientManager.authorize(...)</code> can return <code>null</code> when authorization cannot be performed for the given provider/context. That is not automatically an <code>OAuth2AuthorizationException</code> or <code>OAuth2Error("invalid_grant")</code>.

### 10.2. Do Not Retry Indefinitely

Wrong:

~~~java
while (true) {
    try {
        return manager.authorize(request);
    } catch (OAuth2AuthorizationException ignored) {
        // Resend the same grant/refresh token indefinitely.
    }
}
~~~

<code>invalid_client</code> requires fixing credentials/config; <code>invalid_grant</code> may mean the token was already consumed; an outage may call for bounded backoff, not an infinite loop.

### 10.3. Do Not Return HTTP 401 for Every Token Error

A user has a valid Portal session, yet the Reports API token refresh fails. You may need reauthorization for registration <code>company</code>, or report that the reporting feature is temporarily unavailable. You do not necessarily need to invalidate the entire Portal session.

Policy depends on security requirements: if the token was revoked because the user account was disabled, the Portal may need to destroy the local session per policy. However, that is an **informed decision**, not the default for every <code>OAuth2AuthorizationException</code>.

## 11. Authorized-Client Failure Handler and Token Cleanup

Spring Security provides the abstractions:

~~~text
OAuth2AuthorizationSuccessHandler
OAuth2AuthorizationFailureHandler
RemoveAuthorizedClientOAuth2AuthorizationFailureHandler
~~~

which help the manager coordinate persistence/cleanup based on token issuance or refresh outcomes.

### 11.1. Why Remove an Authorized Client After invalid_grant?

If the OP confirms the refresh token is no longer valid, repeatedly retrying the old token is harmful. A failure handler can remove the stale authorized client and require reauthorization.

### 11.2. However, a Cluster Has Refresh-Token Rotation Races

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Instance A
    participant B as Instance B
    participant DB as Shared Token Store
    participant OP as Token Endpoint

    A->>DB: Load(company,user-123)
    DB-->>A: A0 / R0, version=7
    B->>DB: Load(company,user-123)
    DB-->>B: A0 / R0, version=7
    A->>OP: Refresh R0
    OP-->>A: A1 / R1
    B->>OP: Refresh R0
    OP-->>B: invalid_grant
    A->>DB: Save A1/R1, version=8
    B->>DB: Remove record by principal?
    Note over DB: B may delete version 8 if delete is unconditional
~~~

Sharing a DB **does not automatically serialize** token refresh requests.

### 11.3. Coordinating by Authorized-Client Key

A safer policy:

~~~text
key = registrationId + trustedPrincipalKey

1. Load authorized client.
2. If access token has sufficient remaining lifetime → use it.
3. Acquire distributed lock/single-flight by key.
4. Reload token after acquiring lock.
5. If another node already refreshed → use the new version.
6. If still needed → call Token Endpoint with the latest refresh token.
7. Atomically save both access/refresh token and version/CAS.
8. If invalid_grant → compare against the latest version before removing.
9. Release lock with owner check.
~~~

This is **architectural pseudocode**, not the default behavior of <code>DefaultOAuth2AuthorizedClientManager</code>.

### 11.4. A Custom Failure Handler Can Lose Default Behavior

If:

~~~java
manager.setAuthorizationFailureHandler(customFailureHandler);
~~~

verify whether the custom handler still performs the cleanup steps required by policy. A logging-only handler can retain an invalid token forever; a handler that removes on every error can delete a valid token when the Token Endpoint returns 503.

Never remove an authorized client by a browser-supplied principal or unconditionally when a newer token version has just been saved on another node.

## 12. Reactive WebFlux: OAuth2AuthorizationException Travels Through Mono

In WebFlux:

~~~text
ReactiveOAuth2AuthorizedClientManager.authorize(...)
    → Mono<OAuth2AuthorizedClient>
~~~

An error arrives as a **publisher error signal**, not an exception thrown immediately when constructing the Mono.

### 12.1. Example Reacting to the Error Signal

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import reactor.core.publisher.Mono;

Mono<OAuth2AuthorizedClient> result =
    manager.authorize(authorizeRequest)
        .switchIfEmpty(Mono.error(
            new IllegalStateException("No authorized client")))
        .doOnError(
            OAuth2AuthorizationException.class,
            ex -> recordSafeCategory(ex.getError().getErrorCode()));
~~~

In the example, <code>manager</code>, <code>authorizeRequest</code>, and the <code>recordSafeCategory</code> method are existing service dependencies. <code>doOnError</code> only observes; it does not recover by itself.

### 12.2. onErrorResume Requires Policy-Compliant Recovery

Dangerous:

~~~java
.onErrorResume(OAuth2AuthorizationException.class,
    ex -> Mono.just(authorizedClientOfAnotherUser))
~~~

This is cross-user token leakage. Never use another principal's token to recover from an error.

If the resource is public and the product allows a dedicated fallback, safe public data may be used. For endpoints requiring user authorization, errors must be propagated/recovered via valid reauthorization rather than bypassing permissions.

### 12.3. Avoid block() and Manual subscribe()

Wrong in a reactive handler:

~~~java
OAuth2AuthorizedClient client =
    manager.authorize(authorizeRequest).block();
~~~

Blocking the Netty event-loop can cause latency/starvation or runtime errors.

Wrong:

~~~java
manager.authorize(authorizeRequest)
    .subscribe(client -> callApi(client));

return Mono.just("done");
~~~

The request can return success before authorize/API call finishes, errors are detached from the controller, and the Reactor Context is lost.

Better:

~~~java
return manager.authorize(authorizeRequest)
    .switchIfEmpty(Mono.error(
        new IllegalStateException("Not authorized")))
    .flatMap(client -> callApi(client));
~~~

## 13. WebFlux: Authentication Failure Handler of oauth2Login

Reactive Spring Security provides <code>ServerAuthenticationFailureHandler</code>, used with OAuth2 Login WebFilters.

~~~java
package example.security;

import java.net.URI;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;

@Configuration
@EnableWebFluxSecurity
public class ReactiveOAuth2LoginConfig {

    @Bean
    ServerAuthenticationFailureHandler oauth2FailureHandler() {
        return (webFilterExchange, failure) -> {
            if (failure instanceof OAuth2AuthenticationException oauth2) {
                String code = oauth2.getError().getErrorCode();
                // Record bounded category; do not log raw description.
            }

            var response = webFilterExchange.getExchange().getResponse();
            response.setStatusCode(HttpStatus.SEE_OTHER);
            response.getHeaders().setLocation(
                URI.create("/login?error=oauth2"));
            return response.setComplete();
        };
    }

    @Bean
    SecurityWebFilterChain webChain(
            ServerHttpSecurity http,
            ServerAuthenticationFailureHandler oauth2FailureHandler) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/login", "/error").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .authenticationFailureHandler(oauth2FailureHandler))
            .build();
    }
}
~~~

This is an illustrative pattern for Spring Security versions supporting the corresponding DSL; exact APIs may vary across versions. Unlike Servlet, the handler returns <code>Mono&lt;Void&gt;</code> and operates on <code>ServerWebExchange</code>.

An <code>OAuth2AuthorizationException</code> in a reactive business service is not automatically handled by this handler: it flows through the service/controller publisher chain. Similarly, HTTP 401/403 from a downstream WebClient has its own handling.

## 14. Resource Server HTTP 401/403: Do Not Confuse with Token Endpoint

<code>WebClient.retrieve()</code> typically turns non-2xx statuses into an HTTP client exception by default, rather than automatically creating an <code>OAuth2AuthorizationException</code>.

### 14.1. Classifying Downstream Responses

| Response | Possible Meaning | Handling Direction |
|---|---|---|
| 401 Bearer <code>invalid_token</code> | Token expired/revoked/wrong issuer/audience | Check token/refresh/reauthorize per policy |
| 401 without Bearer error | Missing header, gateway, or different auth scheme | Check HTTP client and proxy |
| 403 <code>insufficient_scope</code> | Token missing scope | Check scopes/consent; do not blindly refresh |
| Other 403 | Role/tenant/ownership/WAF | Check Resource Server authorization |
| 429 | Rate limit | Bounded backoff |
| 502/503 | Downstream outage | Bounded retry if idempotent |

### 14.2. WebClient onStatus

~~~java
return reportsWebClient.get()
    .uri("/v1/reports")
    .retrieve()
    .onStatus(
        status -> status.value() == 401,
        response -> Mono.error(
            new DownstreamAuthenticationException(
                "Reports access token rejected")))
    .onStatus(
        status -> status.value() == 403,
        response -> Mono.error(
            new DownstreamPermissionException(
                "Reports permission denied")))
    .bodyToMono(ReportDto.class);
~~~

<code>DownstreamAuthenticationException</code>, <code>DownstreamPermissionException</code>, and <code>ReportDto</code> are **application-defined types** in the example, not Spring Security built-ins. Define them according to your domain contract.

If you want to accurately distinguish <code>invalid_token</code> and <code>insufficient_scope</code>, parse <code>WWW-Authenticate</code> using an appropriate HTTP parser/contract rather than arbitrary string matching on the body.

### 14.3. OAuth2 WebClient Filters

<code>ServerOAuth2AuthorizedClientExchangeFilterFunction</code> and <code>ServletOAuth2AuthorizedClientExchangeFilterFunction</code> can integrate the token/authorized-client manager with WebClient.

Whether the filter automatically translates HTTP 401/403 into an authorization failure or removes the token depends on **the constructor, failure handler, and Spring Security version**. Do not assume WebClient always removes tokens rejected by a Resource Server.

## 15. Classification by Error Code and Operation

A resilient design separates:

~~~text
Upstream OAuth2Error / AuthenticationException / AuthorizationException
    ↓
Normalize error code
    ↓
Classifier: CATEGORY
    ↓
Policy by operation/stage
    ├── User-facing response
    ├── Reauthorization
    ├── Retry/backoff
    ├── Token cleanup
    └── Metrics/tracing
~~~

### 15.1. Example Classifier

~~~java
package example.oauth2;

import org.springframework.security.oauth2.core.OAuth2Error;

public final class OAuth2FailureClassifier {

    public enum Category {
        USER_DENIED,
        CLIENT_CONFIGURATION,
        GRANT_NOT_VALID,
        INTERACTION_REQUIRED,
        UPSTREAM_TEMPORARY,
        INSUFFICIENT_PERMISSION,
        OTHER
    }

    public Category classify(OAuth2Error error) {
        if (error == null) {
            return Category.OTHER;
        }

        String code = error.getErrorCode();

        if ("access_denied".equals(code)) {
            return Category.USER_DENIED;
        }
        if ("invalid_client".equals(code)
                || "unauthorized_client".equals(code)
                || "unsupported_grant_type".equals(code)) {
            return Category.CLIENT_CONFIGURATION;
        }
        if ("invalid_grant".equals(code)) {
            return Category.GRANT_NOT_VALID;
        }
        if ("login_required".equals(code)
                || "interaction_required".equals(code)
                || "consent_required".equals(code)) {
            return Category.INTERACTION_REQUIRED;
        }
        if ("server_error".equals(code)
                || "temporarily_unavailable".equals(code)) {
            return Category.UPSTREAM_TEMPORARY;
        }
        if ("insufficient_scope".equals(code)) {
            return Category.INSUFFICIENT_PERMISSION;
        }
        return Category.OTHER;
    }
}
~~~

**Category alone does not dictate the action.** <code>invalid_grant</code> at login callback differs from refresh token <code>invalid_grant</code>; <code>invalid_client</code> in a background worker differs from a user authorization policy error.

### 15.2. Context to Pass Alongside Category

~~~text
operation = oauth2_login | token_refresh | client_credentials | api_call
stage = authorization_callback | token_endpoint | userinfo | resource_server
registrationId = company
grantType = authorization_code | refresh_token | client_credentials
principalKey = trusted internal key, never taken from browser
errorCategory = grant_not_valid
~~~

Do not use raw OAuth2Error descriptions as security policy. Use operation + category + trusted context.

### 15.3. Unknown Provider-Specific Errors

A provider may return <code>policy_error_1234</code>, which is not in OAuth2ErrorCodes. Preserve the original code in filtered internal diagnostics and assign the normalized category <code>OTHER</code> for UI/metrics. Do not convert every unfamiliar error into <code>invalid_grant</code>.

## 16. Mapping Safely to HTTP Responses

### 16.1. Browser OIDC Login

An authentication failure handler can redirect:

~~~text
303 /login?error=oauth2
~~~

or use Spring Security's default behavior. The browser should not receive stack traces, Client secrets, raw OP descriptions, or untrusted error URIs.

### 16.2. BFF Calling a Downstream Service

The user is authenticated, but the Reports API integration fails:

~~~json
{
  "type": "https://portal.example.org/problems/reports-unavailable",
  "title": "Unable to load reports",
  "status": 503,
  "detail": "The reporting service is temporarily unavailable."
}
~~~

This is a **Problem Details example**, not a mandatory status for every OAuth2AuthorizationException. If the error requires the user to grant new consent, a reauthorization flow may be more appropriate. If the client secret is wrong, operations must be alerted.

### 16.3. When to Return 401/403?

- **401** at the Portal when the request to the Portal is not authenticated or the Portal credential is invalid.
- **403** when a principal exists but is not allowed to perform the business operation.
- **502/503** when a backend dependency cannot serve its contract and cannot be resolved by user login.

Do not blindly map:

~~~text
OAuth2AuthenticationException -> always 401
OAuth2AuthorizationException  -> always 403
~~~

### 16.4. Do Not Put Upstream error_description in URLs

Wrong:

~~~text
/login?message=<raw upstream description>
~~~

URLs can enter browser history, Referer headers, access logs, analytics, and security alerts. Use a server-curated code/message and a separate correlation ID.

## 17. Multi-Provider and Tenant Isolation

A portal has:

~~~text
company → issuer https://idp.company.example
partner → issuer https://login.partner.example
~~~

When an error occurs:

1. Identify the selected ClientRegistration.
2. Verify the issuer/token endpoint matches the original request.
3. Distinguish Company principals from Partner principals.
4. Clean up tokens only for the exact registration/principal/tenant.
5. Do not "fall back" to another registration's token to salvage the request.

### 17.1. OIDC Identity Is Not Just Email

OIDC uses the pair <code>(iss, sub)</code> to identify a user within the issuer's trust domain. Two providers may share the same email or subject string while still representing two distinct identities.

Do not store authorized-clients by unverified email or use a user-supplied principal key; that risks cross-user/tenant token leakage.

### 17.2. Mix-Up Can Look Like invalid_grant

If a Client processes Provider A's callback against Provider B's Token Endpoint, the OP may return <code>invalid_grant</code>. The root cause is **wrong registration/issuer binding**, not merely an expired code.

Do not "fix" this by trying every Token Endpoint until the code is accepted. That creates OAuth mix-up/credential disclosure risks.

## 18. Observability: Stage Matters More Than Class Name

The **Errors and Observability** chapter needs to distinguish:

~~~text
OAuth2 Login
    authorization initiated
    callback received
    state validation
    token exchange
    authentication success/failure

OAuth2 Authorized Client
    cache hit/miss
    refresh attempted
    refresh success/failure
    client-credentials token request

Downstream API
    HTTP 2xx/401/403/429/5xx
    invalid_token / insufficient_scope
~~~

With only a single metric <code>oauth2_error_total</code>, the operations team can hardly tell whether users are declining consent or a Client secret is broken.

### 18.1. Structured Logging

An appropriate event:

~~~text
event=oauth2_token_refresh_failed
registrationId=company
stage=token_endpoint
grantType=refresh_token
errorCategory=grant_not_valid
errorCode=invalid_grant
correlationId=01EXAMPLE
httpStatus=400
refreshAttempt=1
~~~

Do not log:

~~~text
access_token=...
refresh_token=...
client_secret=...
authorization_code=...
code_verifier=...
id_token=...
state=...
nonce=...
session_cookie=...
client_assertion=...
~~~

Do not log raw <code>error_description</code> by default: a provider might inadvertently include account IDs, endpoints, input data, or infrastructure details in the description.

### 18.2. Cardinality-Bounded Metrics

~~~text
oauth2_login_failure_total{provider,category}
oauth2_token_request_total{provider,grant_type,result}
oauth2_token_refresh_failure_total{provider,error_category}
oauth2_authorized_client_lookup_miss_total{provider}
oauth2_callback_state_mismatch_total{provider}
oauth2_downstream_401_total{service}
oauth2_downstream_403_total{service}
oauth2_token_endpoint_latency_seconds{provider}
~~~

Never attach raw username, email, subject, jti, access token, state, description, or request ID as metric labels. Cardinality can explode and create data exposure risks.

### 18.3. Distributed Tracing

A BFF request may have:

~~~text
traceId=request-123
  ├── span oauth2.authorized_client.lookup
  ├── span oauth2.token.refresh
  └── span reports.api.call
~~~

Span attributes should include provider alias, normalized category, stage, grant type, HTTP status/latency. Never put OAuth2 credentials or HTTP Authorization headers into traces.

### 18.4. Correlation ID Should Not Be the OAuth2 State

<code>state</code> serves security correlation for the authorization flow. Do not use raw state as a tracing ID or write it to URL logs just to ease debugging. Generate an independent, non-secret correlation ID.

## 19. Error Severity Classification

| Scenario | Operational Attention Level |
|---|---|
| User declines consent | Expected user outcome; not an incident by default |
| Sharp rise in <code>invalid_client</code> after deploy | Secret/key configuration alert |
| Refresh <code>invalid_grant</code> rising with replica count | Likely rotation race/token synchronization issue |
| Rising authorization-code <code>invalid_grant</code> | PKCE/callback/code reuse/redirect issue |
| Rising state mismatches | Cookie/SameSite/session store or login CSRF attempts |
| Rising OP <code>server_error</code> and latency | Provider outage |
| Rising API 403 | Scope/role/tenant policy change |
| Rising API 401 | Token expiry/issuer/audience/gateway |

Do not fire a high-severity alert on every <code>access_denied</code> event caused by a user clicking Deny. Conversely, a sudden spike in <code>invalid_client</code> after secret rotation must be closely monitored.

## 20. Retry, Reauthorization, and Cleanup Cannot Be Uniform

### 20.1. Errors That Should Generally Not Be Retried As-Is

- <code>invalid_client</code> due to wrong secret/key.
- <code>unsupported_grant_type</code>.
- <code>unauthorized_client</code>.
- <code>invalid_scope</code> due to registration policy.
- <code>invalid_grant</code> due to already-used code or rotated refresh token.

Retrying with the same input can increase errors/rate limits without solving the problem.

### 20.2. Transient Errors That Can Have Bounded Retries

- HTTP 503/502 from the Token Endpoint.
- HTTP 429 with an appropriate Retry-After.
- Network timeouts after classifying the operation semantics.

Retry design:

1. Overall timeout and maximum retry count.
2. Exponential backoff + jitter.
3. Do not retry operations with side effects without an idempotency policy.
4. Do not log/dump request secrets.
5. Do not resend the same authorization code/refresh token when you do not know whether the OP already processed it.

### 20.3. Refresh Timeout Is a Hard Case

~~~text
Client sends refresh_token=R0
OP issues access A1 + refresh R1
Response is lost due to network timeout
Client does not know whether R0 was consumed
~~~

Retrying R0 may result in <code>invalid_grant</code> or trigger reuse detection. There is no distributed transaction between the OP and the local token DB. Design recovery, single-flight, and conditional token state updates according to policy.

### 20.4. Do Not Automatically Revoke All Tokens

A timeout, 503, or invalid scope does not automatically mean the old token was revoked. Deleting the entire authorized client on every exception both drops sessions and can hide the root cause.

## 21. Security: Preventing Information Leakage Through Error Handling

### 21.1. Do Not Reflect Raw HTML or Query Strings

If the OP returns a description containing special HTML characters, the UI must escape and/or avoid rendering raw content. A login error page must not become a reflected XSS vector.

### 21.2. Do Not Create Open Redirects

<code>OAuth2Error.getUri()</code> is not a vetted, trusted URL. Do not <code>sendRedirect</code> to that URI unless the destination is controlled.

### 21.3. Do Not Skip Token Validation to "Rescue" Login

An ID Token with a bad signature, issuer, audience, or nonce must be rejected. Never read an email from an unverified JWT and create an Authentication to spare the user an error.

### 21.4. Do Not Let the Browser Pick the Token Principal

If user A's refresh fails, do not use:

~~~text
?retryAs=userB
~~~

to look up user B's token. Authorized-client lookups must rely on Authentication and a trusted internal identity context.

### 21.5. Do Not Catch Exception and Grant Access

Wrong:

~~~java
try {
    validateIdToken(idToken);
} catch (Exception ex) {
    return authenticatedFromUnverifiedClaims(idToken);
}
~~~

This bypasses OIDC trust validation. Error recovery must **fail closed** when identity verification fails.

## 22. Testing: Verifying Objects and Exceptions

### 22.1. Unit Testing OAuth2Error

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class OAuth2ErrorTest {

    @Test
    void exposesCodeDescriptionAndUri() {
        var error = new OAuth2Error(
            OAuth2ErrorCodes.INVALID_GRANT,
            "Grant rejected",
            "https://auth.example.org/docs/errors");

        assertEquals("invalid_grant", error.getErrorCode());
        assertEquals("Grant rejected", error.getDescription());
        assertEquals(
            "https://auth.example.org/docs/errors",
            error.getUri());
    }

    @Test
    void codeOnlyErrorHasOptionalFieldsEmpty() {
        var error = new OAuth2Error("invalid_request");
        assertEquals("invalid_request", error.getErrorCode());
        assertNull(error.getDescription());
        assertNull(error.getUri());
    }
}
~~~

### 22.2. Unit Testing Both Exceptions

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.security.oauth2.core.OAuth2Error;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OAuth2ExceptionTest {

    @Test
    void authenticationExceptionCarriesOAuth2Error() {
        var failure = new OAuth2AuthenticationException(
            new OAuth2Error("access_denied"));
        assertEquals(
            "access_denied",
            failure.getError().getErrorCode());
    }

    @Test
    void authorizationExceptionCarriesOAuth2Error() {
        var failure = new OAuth2AuthorizationException(
            new OAuth2Error("invalid_grant"));
        assertEquals(
            "invalid_grant",
            failure.getError().getErrorCode());
    }
}
~~~

### 22.3. Testing the Classifier

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2Error;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OAuth2ClassifierTest {

    @Test
    void separatesClientFailureAndGrantFailure() {
        var classifier = new OAuth2FailureClassifier();

        assertEquals(
            OAuth2FailureClassifier.Category.CLIENT_CONFIGURATION,
            classifier.classify(new OAuth2Error("invalid_client")));

        assertEquals(
            OAuth2FailureClassifier.Category.GRANT_NOT_VALID,
            classifier.classify(new OAuth2Error("invalid_grant")));
    }
}
~~~

### 22.4. Reactive StepVerifier

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReactiveAuthorizationFailureTest {

    @Test
    void propagatesAuthorizationException() {
        var failure = new OAuth2AuthorizationException(
            new OAuth2Error("invalid_grant"));

        Mono<String> result = Mono.error(failure);

        StepVerifier.create(result)
            .expectErrorSatisfies(ex -> {
                if (!(ex instanceof OAuth2AuthorizationException oauth2)) {
                    throw new AssertionError("Wrong exception type");
                }
                assertEquals(
                    "invalid_grant",
                    oauth2.getError().getErrorCode());
            })
            .verify();
    }
}
~~~

Reactive tests require the <code>io.projectreactor:reactor-test</code> dependency. This test verifies propagation and **does not replace** an integration test against the Token Endpoint.

## 23. Stage-by-Stage Integration Tests

| Scenario | Expectation |
|---|---|
| User declines consent | Authentication failure handler, no new session created |
| Callback state mismatch | Login rejected, state validation not bypassed |
| ID Token wrong issuer/audience/nonce | OIDC authentication rejected |
| Code expired/reused | Token Endpoint invalid_grant, login does not complete |
| Wrong Client secret | invalid_client, safe user-facing error + config alert |
| Refresh token revoked | Manager failure, reauthorization/cleanup policy |
| Two nodes refresh R0 | B receiving invalid_grant does not mistakenly delete R1/new state |
| Token Endpoint 503 | Bounded retry, valid token not blindly deleted |
| Reports API 401 invalid_token | Classify as downstream token issue |
| Reports API 403 insufficient_scope | No infinite refresh retries |
| UserInfo 401 | Proper OIDC login/UserInfo policy |
| Cross-domain error_uri | No open redirect |
| error_description contains HTML | No reflected XSS |
| Two providers share email/sub | No principal/issuer mix-up |
| Reactive manager Mono.error | Error propagated, no manual block/subscribe |

### 23.1. Mock Login Does Not Replace OIDC Protocol Tests

Spring Security Test provides:

~~~text
MockMvc.with(oauth2Login()) / with(oidcLogin())
WebTestClient.mutateWith(mockOidcLogin())
~~~

These tools simulate an authenticated user, but **do not actually verify** state, PKCE, Token Endpoint, UserInfo, ID Token signature, or callback error translation. You need proper OP integration tests and token endpoint fixtures.

### 23.2. Test That Failure Handlers Do Not Leak Upstream Data

Verify:

- Redirects go only to allowed internal URLs.
- No raw <code>error_description</code> appears in the response URL/HTML.
- No access token, refresh token, authorization code, state, nonce, or secret appears in logs.
- Login failures do not create an authenticated session.
- Unknown provider errors are still handled safely.

## 24. Troubleshooting

| Symptom | Possible Cause | Investigation Direction |
|---|---|---|
| Login redirects to /login?error | OAuth2 Login authentication failure | Callback/state/token/ID Token validation |
| User clicks Deny yet ERROR logs spike | Incorrect classification | Categorize access_denied as expected user outcome |
| invalid_state after scale-out | Session/correlation not shared | Spring Session, cookie, load balancer |
| invalid_grant right at callback | Code expiry/reuse, PKCE, redirect | Token request and authorization flow |
| invalid_grant during refresh | Expired/revoked/rotation race | Token store, single-flight, OP policy |
| invalid_client after deploy | Secret/key/mTLS rotation mismatch | Client registration and deployment version |
| User still logged in, downstream unavailable | Session and authorized client states differ | Reauthorization/integration error |
| API 401 without OAuth2AuthorizationException | HTTP Resource Server error | WebClient/RestClient and WWW-Authenticate |
| API 403 with continuous refreshes | insufficient_scope mistaken for expiry | Scope/consent/authorization |
| OP server_error spike | Outage/latency | Provider health/circuit breaker |
| UserInfo rejected | Access token/scope/claims | UserInfo configuration |
| error_uri leads to external site | Open redirect | Do not redirect raw error_uri |
| Raw token appears in traces | HTTP instrumentation captures headers/body | Redact credentials |
| WebFlux block() throws error | Blocking reactive publisher | Compose Mono |
| ControllerAdvice misses callback | Security filter handled before MVC | oauth2Login.failureHandler |
| Callback hits API filter chain | Wrong chain matcher/order | Select the right browser chain |
| Client credentials fails, user gets 401 | Wrong upstream→Portal status mapping | Domain-specific error mapping |

### 24.1. Diagnostic Checklist

~~~text
1. Which endpoint did the error occur at?
   - Authorization initiation?
   - Authorization callback?
   - Token Endpoint?
   - UserInfo?
   - Resource Server?
2. Is it the right ClientRegistration/issuer?
3. Is the request already authenticated at the Portal?
4. Did the error code come from the OP, Resource Server, or custom code?
5. Is there an OAuth2Error inside the exception?
6. Is the grant type authorization_code, refresh_token, or client_credentials?
7. Are there network/proxy/session/PKCE/nonce issues?
8. Could there be a token refresh race across nodes?
9. Is retry/reauthorize/alert needed, or just a user message?
10. Are logs/metrics safe and free of credentials?
~~~

## 25. Practice Exercises

### Exercise 1 — Does OAuth2Error Throw Itself?

~~~java
OAuth2Error error = new OAuth2Error("invalid_grant");
~~~

**Answer:** No. It is a data object; an exception or another flow must use it to represent a failure in Java control flow.

### Exercise 2 — Two Exceptions with the Same Code

~~~java
new OAuth2AuthenticationException(new OAuth2Error("invalid_grant"));
new OAuth2AuthorizationException(new OAuth2Error("invalid_grant"));
~~~

**Answer:** You cannot assume identical handling. You must check whether the error occurred during login or when obtaining/refreshing an authorized client.

### Exercise 3 — access_denied from Consent

User selects Deny on the OP.

**Answer:** Redirect back to the login page with an appropriate message; do not infinitely auto-retry consent or trigger critical alerts if this is a normal user outcome.

### Exercise 4 — invalid_client After Secret Rotation

All token requests from node A fail, while node B still succeeds.

**Answer:** Check secret/key versions and deployment config across replicas; do not mechanically force all users to log in again.

### Exercise 5 — invalid_grant During Refresh

Portal session is still valid, but the refresh token was revoked.

**Answer:** Reauthorization of a specific ClientRegistration or policy-based cleanup may be needed; you do not necessarily have to invalidate the entire Portal session.

### Exercise 6 — Refresh Race

Node A has saved R1; node B receives invalid_grant with R0.

**Answer:** Do not unconditionally delete A's token record. Re-read, use version/CAS, and coordinate refresh by key.

### Exercise 7 — error_uri

Provider returns a URI to an unfamiliar website.

**Answer:** Do not call <code>sendRedirect(error.getUri())</code> on untrusted URIs; use an internal help page.

### Exercise 8 — Resource Server 403

Reports API returns insufficient_scope.

**Answer:** This is a downstream authorization error; it requires scopes/consent/policy, not throwing invalid_grant to force login.

### Exercise 9 — Reactive Blocking

~~~java
OAuth2AuthorizedClient client = manager.authorize(request).block();
~~~

**Answer:** Do not block on the Netty event-loop; use flatMap and error signals.

### Exercise 10 — OAuth2 Code and HTTP Status

**Question:** Why is <code>OAuth2ErrorCodes.INVALID_CLIENT</code> not HTTP status 401?

**Answer:** It is a protocol code; endpoint responses and Portal HTTP mappings depend on authentication method, context, and policy.

### Exercise 11 — ControllerAdvice Does Not Catch OAuth2 Login

Callback fails before the request reaches a controller.

**Answer:** Configure a failure handler on the Spring Security authentication filter; ControllerAdvice does not automatically catch all filter exceptions.

### Exercise 12 — Unknown Custom Error

Provider returns <code>policy_error_739</code>.

**Answer:** Normalize into category OTHER, store the filtered code in diagnostics, and check the provider contract. Do not force it into invalid_grant without evidence.

### Exercise 13 — Metric error_description

**Question:** Why shouldn't raw error descriptions be used as metric labels?

**Answer:** They can contain PII, are unstable, have high cardinality, and cause data leaks. Use bounded stage/category/provider alias.

### Exercise 14 — Callback State Mismatch

Callback has state S2; the original authorization request had S1.

**Answer:** Do not skip state verification even if the ID Token might have a valid signature; you must reject uncorrelated flows.

### Exercise 15 — WebClient Error

WebClient receives HTTP 401 from Reports API, yet no OAuth2AuthorizationException is seen.

**Answer:** The HTTP client has its own exception/status pipeline. Check Resource Server headers and OAuth2 filter wiring rather than assuming the manager is the source of the error.

### Exercise 16 — Capstone Practice

Design a system with:

1. OIDC Login with authorization code, state, and PKCE per provider.
2. AuthenticationFailureHandler with neutral messages.
3. Authorized-client manager with a refresh provider.
4. Token store properly partitioned by registration/principal.
5. Refresh rotation handling for two replicas.
6. WebClient calling an API with an access token of the right audience/scope.
7. Classifier separating error code from operation/stage.
8. Safe domain HTTP mapping without returning upstream descriptions.
9. Logs, metrics, and tracing with provider alias, normalized category, and correlation ID.
10. Unit tests for the three types; integration tests for callback, token, UserInfo, and Resource Server.
11. Test that 401/403 errors do not cause refresh loops.
12. Test invalid_grant when node B uses a rotated refresh token and does not delete node A's new token.

Explain why **you cannot use a single rule "every OAuth2Error → logout" across the entire system**.

## 26. Summary

- <code>OAuth2Error</code> is **error data** containing <code>errorCode</code>, <code>description</code>, and <code>uri</code>; it is neither an exception nor an HTTP response.
- <code>OAuth2AuthenticationException</code> is an authentication exception carrying an <code>OAuth2Error</code>, commonly seen in OAuth2/OIDC Login and handled by the Spring Security authentication infrastructure.
- <code>OAuth2AuthorizationException</code> carries an <code>OAuth2Error</code> in OAuth2 authorization/authorized-client/token operations such as token refresh.
- The same <code>invalid_grant</code> can come from code exchange or refresh; you must inspect <code>operation</code>, <code>stage</code>, registration, and principal context.
- Authorization callback, Token Endpoint JSON errors, UserInfo, and Resource Server Bearer 401/403 are **different error sources**.
- Do not equate exception names with HTTP 401/403. HTTP responses must follow the Portal's contract, authentication/authorization policies, and dependency state.
- Servlet <code>oauth2Login().failureHandler(...)</code> handles errors in the login filter; authorized-client failures and downstream HTTP errors have separate handlers.
- WebFlux uses Mono error signals; avoid arbitrary <code>block()</code>/<code>subscribe()</code> calls or falling back to another user's token.
- With refresh-token rotation, <code>invalid_grant</code> can result from concurrent refreshes; do not erase newer token state with unconditional deletes.
- Never log tokens, codes, session cookies, or raw OAuth2 error descriptions; never redirect to an untrusted <code>error_uri</code>.
- Effective observability requires stage, normalized category, grant type, provider alias, correlation ID, and bounded metric labels.
- Unit tests for constructors/getError do not replace integration tests for callbacks/Token Endpoint/Resource Server or multi-instance concurrency.

### References

- **Spring Security Java API — OAuth2Error:** <code>getErrorCode()</code>, <code>getDescription()</code>, <code>getUri()</code>.
- **Spring Security Java API — OAuth2AuthenticationException:** OAuth2 errors in authentication processing.
- **Spring Security Java API — OAuth2AuthorizationException:** OAuth2 errors in authorization/token operations.
- **Spring Security Java API — OAuth2ErrorCodes:** standard error codes.
- **Spring Security Reference — OAuth2 Login (Servlet/Reactive):** callback, authentication failure handler, OIDC validation.
- **Spring Security Reference — OAuth2 Client:** authorized-client manager/providers, token clients, success/failure handlers.
- **Spring Security Reference — Reactive OAuth2 Client:** <code>ReactiveOAuth2AuthorizedClientManager</code> and reactive error handling.
- **Spring Security Reference — OAuth2 Resource Server:** Bearer error responses, 401/403, and <code>WWW-Authenticate</code>.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Authorization/Token Endpoint error responses.
- **RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage:** invalid_token and insufficient_scope.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** code binding and related errors.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** refresh token rotation, replay, mix-up protection.
- **OpenID Connect Core 1.0:** OIDC errors, ID Token validation, and UserInfo.
- **RFC 9457 — Problem Details for HTTP APIs:** stable HTTP error representation for application clients.
- **OWASP Logging Cheat Sheet:** safe logging of security events without credentials/PII.
