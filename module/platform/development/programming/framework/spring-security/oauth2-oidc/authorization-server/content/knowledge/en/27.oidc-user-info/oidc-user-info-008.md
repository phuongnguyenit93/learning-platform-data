# Handling Token Errors, Scope Errors, and Unavailable Users

## Lesson Goals

In the **OIDC UserInfo** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, this lesson guides how to handle errors and user state changes at the **OpenID Connect UserInfo Endpoint** when building an Authorization Server with **Spring Security**, **Spring Authorization Server**, and **Spring Boot**.

UserInfo is an OAuth 2.0 Protected Resource returning claims about an authenticated End-User. The client calls the endpoint using an access token received from the OIDC Authentication Flow. In operations, requests can fail because the token is expired/revoked, the token lacks required scopes, the user was locked or deleted, profile data is absent, or the user directory service is temporarily unreachable.

Do not lump every case into one generic error. Each case has a distinct meaning and handling strategy:

- **Invalid token:** the request lacks a valid credential; return Bearer error **invalid_token**.
- **Missing mandatory permission:** the token is valid, but lacks the scope required for the operation; return **insufficient_scope** per policy.
- **Missing optional claim:** the token remains valid, yet the user lacks a field or the OP chooses not to disclose it; omit that claim from the response.
- **Disabled/deleted user:** apply the deprovisioning policy, invalidate authorizations/tokens, and deny access per policy.
- **User directory temporarily experiencing an outage:** this is an infrastructure failure; do not mark the token or user as invalid merely because data could not be queried.

After this lesson, you will be able to:

1. Explain the UserInfo contract per OpenID Connect Core 1.0 Section 5.3 and Bearer Token Usage RFC 6750.
2. Distinguish **invalid_token (401)** from **insufficient_scope (403)** and service errors (5xx).
3. Understand why **sub** is always mandatory and why the client must compare it against **sub** in the ID Token.
4. Explain how the **openid**, **profile**, **email**, **address**, and **phone** scopes determine returned claims.
5. Recognize the default behavior of **OidcUserInfoAuthenticationProvider** and its mapper in Spring Authorization Server 1.5.8.
6. Customize **userInfoMapper** to read the current profile, filter claims by scope, and handle unavailable users.
7. Distinguish a disabled/deleted account from an empty profile field or a temporarily unavailable data service.
8. Design access/refresh authorization revocation, caching, error handling, logging, and end-to-end testing.

> **Running scenario:** **employee-portal** received an ID Token and access token for user **user-42**. Later, the access token expires; the user is locked; or the email is removed from the profile. When the portal calls **/userinfo**, the Authorization Server must return the right outcome for each scenario, keep **sub** stable, and never disclose data beyond granted scopes.

## 1. UserInfo Is an OIDC Protected Resource

The OIDC UserInfo Endpoint returns claims about the authenticated End-User. The client retrieves the endpoint from Provider Metadata via the **userinfo_endpoint** property, then sends the access token obtained from the OIDC Authentication Request.

### 1.1. Standard Request

OIDC Core requires the UserInfo Endpoint to:

- Use TLS.
- Support HTTP GET and HTTP POST.
- Accept access tokens via OAuth 2.0 Bearer Token Usage.
- Recommend GET and pass the token in the HTTP **Authorization** header.
- Optionally support CORS so browser-based clients can call the endpoint appropriately.

Recommended request example:

~~~http
GET /userinfo HTTP/1.1
Host: auth.example.com
Authorization: Bearer OIDC_ACCESS_TOKEN
Accept: application/json
~~~

Never place the access token in the query string. URLs can appear in reverse proxy logs, tracing, browser history, and analytics systems. Likewise, never send tokens in image URLs, scripts, or referrers.

Clients do not guess the UserInfo path. Obtain **userinfo_endpoint** from OpenID Provider Configuration/Discovery for the verified issuer.

### 1.2. UserInfo Is Not the Token Endpoint

| Endpoint | Credential | Purpose |
|---|---|---|
| Authorization Endpoint | Browser session and authorization request | Authenticate user, collect consent, issue authorization code. |
| Token Endpoint | Authorization code/refresh token and client authentication per client type | Issue access token, ID Token, refresh token. |
| UserInfo Endpoint | OIDC Bearer access token | Return End-User claims per granted scopes. |
| Introspection Endpoint | Token to inspect and caller credentials | Return active state and token metadata. |
| Revocation Endpoint | Token to revoke and client authentication per policy | Invalidate token/authorization. |

UserInfo does not accept an ID Token in place of an access token. The ID Token is the authentication result meant for the OIDC Client; the access token is the credential sent to the UserInfo Protected Resource.

### 1.3. General Processing Flow

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OIDC Client
    participant U as UserInfo Endpoint
    participant AS as Authorization Server
    participant DB as User / Authorization Store

    C->>U: GET /userinfo + Bearer access token
    U->>AS: Validate JWT/access-token state
    AS->>DB: Load authorization and token state
    DB-->>AS: Token active? Scopes? ID Token?
    AS-->>U: Authenticated request context
    U->>DB: Load current user profile (if dynamic mapper)
    DB-->>U: Active user / missing user / unavailable
    alt Token valid and user available
        U-->>C: 200 JSON with sub + allowed claims
    else Token expired, revoked or invalid
        U-->>C: 401 invalid_token
    else Required scope missing
        U-->>C: 403 insufficient_scope
    else User disabled/deleted by policy
        U-->>C: 401 invalid_token after deprovisioning policy
    else User store unavailable
        U-->>C: 503 Service Unavailable
    end
    C->>C: Verify UserInfo sub equals ID Token sub
~~~

The diagram shows that a request may require both access token validation and querying the current profile. If using the default mapper reading claims from the ID Token, the user directory query step may not occur on every request.

## 2. Claims, sub, and Client-Side Verification

### 2.1. sub Is Always Mandatory

Per OIDC Core Section 5.3.2, the UserInfo Response **MUST always contain the sub claim**. **sub** is the subject identifier of the End-User within the issuer.

Example response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "sub": "user-42",
  "name": "Nguyen An",
  "email": "an@example.com",
  "email_verified": true
}
~~~

**sub** must be stable according to the OP's subject identifier rules. Never use email, username, or phone number as **sub** if those values can change, be recycled, or vary by tenant without an explicit pairwise subject design.

### 2.2. Client Must Compare sub with the ID Token

A UserInfo Response is not automatically guaranteed to describe the same End-User the client saw in the ID Token. OIDC Core requires the client to verify that **sub** in UserInfo **matches** **sub** in the ID Token **exactly**. If they differ, the client **MUST not use the UserInfo values**.

This prevents token substitution: a client could accidentally send session A's access token while pairing the data with session B's ID Token.

Client-side pseudocode:

~~~java
String idTokenSubject = oidcIdToken.getSubject();
String userInfoSubject = userInfo.getSubject();

if (!Objects.equals(idTokenSubject, userInfoSubject)) {
    throw new OAuth2AuthenticationException(
            new OAuth2Error("invalid_userinfo_response"));
}

// Use UserInfo only after the subject has been verified.
~~~

The example assumes **oidcIdToken** has already had its signature, issuer, audience, expiry, and nonce verified. Never decode an unverified payload and use **sub** as a trust anchor.

### 2.3. Do Not Return Empty or Null Claims

For privacy reasons, the OP may omit a claim requested by the client. OIDC Core specifies that not returning an optional claim is not an error. If a claim is not returned, **omit the claim key entirely** from the JSON; do not return **null** or an empty string.

Example when the user has not provided an email:

~~~json
{
  "sub": "user-42",
  "name": "Nguyen An"
}
~~~

The response above is valid if email is an optional claim that is missing or undisclosed. Do not return:

~~~json
{
  "sub": "user-42",
  "email": null,
  "email_verified": ""
}
~~~

For **sub**, a different rule applies: it must always be present. If the system cannot determine a stable subject, it must not return a successful UserInfo response with a fake or empty **sub**.

## 3. Scopes Determine Returned Claims

OIDC Core defines standard scopes for requesting claim groups. Scope issuance must obey client registration, consent, policy, and the authorization request.

| Scope | Standard Claims Typically Requested |
|---|---|
| **openid** | **sub** and the OIDC identity layer. |
| **profile** | **name**, **family_name**, **given_name**, **middle_name**, **nickname**, **preferred_username**, **profile**, **picture**, **website**, **gender**, **birthdate**, **zoneinfo**, **locale**, **updated_at**. |
| **email** | **email**, **email_verified**. |
| **address** | **address** object per OIDC schema. |
| **phone** | **phone_number**, **phone_number_verified**. |

### 3.1. Requested Scopes Are Not Always Granted Scopes

A client may send **scope=openid profile email**, yet the Authorization Server may grant fewer scopes based on client policy, consent, or user permissions. UserInfo must rely on the **actual scopes of the access token**, not merely the client's initial query.

Example:

~~~text
Authorization Request:
    scope = openid profile email

Issued Access Token:
    scope = openid profile

UserInfo Response:
    sub, name, given_name, family_name, ...
    does not return email/email_verified
~~~

Do not return email when the **email** scope is missing. If the client needs email, it must perform a new authorization request or appropriate consent flow.

### 3.2. Missing Mandatory Scope vs Missing Scope for Optional Claims

Distinguish two cases:

- **Endpoint/policy requires a mandatory scope**, but the token lacks that scope: may return **403 insufficient_scope**.
- Token is valid and has **openid**, but lacks **profile**, **email**, **address**, or **phone**: typically returns **200** with the corresponding claims omitted.

Do not return **403** just because the user has no email or the OP decides not to disclose email. OIDC Core permits the OP to omit claims for privacy; missing an optional claim is not an error.

### 3.3. Do Not Release Claims Simply Because Data Exists

Suppose the database contains email, phone number, address, and birthdate. If the access token has only **openid profile**, the mapper must not return **email**, **phone_number**, or **address** merely because those fields exist.

Minimum rules:

1. **sub** is always returned.
2. Claims belonging to a scope group are returned only when the corresponding scope is present in the access token.
3. Claims may be omitted for privacy, consent, user preference, or policy.
4. Claims without values are skipped, never returned as null/empty.
5. Extended claims must have dedicated policies, documentation, and tests.

## 4. Error Categories and HTTP Statuses

OIDC Core Section 5.3.3 specifies UserInfo Error Responses per RFC 6750. Therefore, token and scope errors must follow Bearer Token error semantics.

| Scenario | HTTP Status | Bearer Error | Client Action |
|---|---:|---|---|
| No access token sent | 401 | Usually no detailed error code needed if credential is missing | Send request with a valid Bearer token. |
| Malformed/expired/revoked token | 401 | **invalid_token** | Request a new access token if refresh session is still valid. |
| Token has wrong issuer/audience or is not for UserInfo | 401 | **invalid_token** | Check issuer, token audience/resource, and OP configuration. |
| Token missing mandatory scope of endpoint/policy | 403 | **insufficient_scope** | Request authorization with appropriate scopes. |
| Missing only optional email or profile scope | 200 | Not an error | Accept response missing those claims. |
| User disabled/deleted per policy | 401 | **invalid_token** | Start a new authentication or handle invalidated session. |
| User directory/database temporarily unavailable | 503 | HTTP service error | Retry with backoff; do not repeatedly refresh tokens. |
| Response lacks sub or sub mismatches ID Token | Client must reject response | Client-side response validation error | Do not use any claims from that response. |

### 4.1. invalid_token: 401 Unauthorized

RFC 6750 defines **invalid_token** for access tokens that are expired, revoked, malformed, or otherwise invalid. The Resource Server should return HTTP 401 and a **WWW-Authenticate** Bearer challenge.

Example:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
~~~

Do not include raw tokens, signature contents, or internal user details in **error_description**. The client only needs to know the credential is no longer usable.

### 4.2. insufficient_scope: 403 Forbidden

RFC 6750 defines **insufficient_scope** when a request requires higher privileges than granted in the access token. The Resource Server should return HTTP 403.

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="openid email"
Cache-Control: no-store
~~~

Use this error only when a scope is truly a mandatory requirement for the operation. If the OP can return **sub** without email, do not reject the entire UserInfo request simply because email does not exist or was not granted.

### 4.3. Missing Bearer Credential

When a request lacks authentication credentials, RFC 6750 recommends the server omit error codes or extra details in the challenge. Example:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Do not turn a tokenless request into an **invalid_token** response with detailed error info, since the client has not provided a credential to evaluate.

### 4.4. Data Service Errors: 503

If the user directory temporarily loses connectivity, times out, or undergoes database failover, do not return **invalid_token**. The token may still be valid; the system simply cannot complete the profile query right now.

Example:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 5
Content-Type: application/json
Cache-Control: no-store

{
  "error": "temporarily_unavailable"
}
~~~

This is an application HTTP service error, not a Bearer token error. The client should perform bounded retries with exponential backoff; do not spin in a tight loop or automatically keep requesting new tokens while the user directory is down.

## 5. Default Behavior of Spring Authorization Server

Spring Authorization Server 1.5.8 provides the OIDC UserInfo endpoint via **OidcUserInfoEndpointFilter** and **OidcUserInfoAuthenticationProvider**.

### 5.1. Key Components

| Component | Role |
|---|---|
| **OidcUserInfoEndpointFilter** | Receives UserInfo requests and handles responses. |
| **OidcUserInfoAuthenticationToken** | Represents the authentication created for the UserInfo request. |
| **OidcUserInfoAuthenticationProvider** | Checks authorization/token state and produces the UserInfo authentication result. |
| **OAuth2AuthorizationService** | Retrieves the associated authorization and tokens. |
| **OidcUserInfoAuthenticationContext** | Provides authentication, access token, and authorization to the mapper. |
| **OidcUserInfoEndpointConfigurer** | Configures converter, provider, mapper, and success/error handlers. |
| **OidcUserInfo** | Claims object serialized into the UserInfo Response. |

Spring Authorization Server configures a default mapper to extract standard claims from the ID Token based on the scopes requested/granted in the authorization. This makes standard responses work without writing a custom mapper from scratch.

### 5.2. How Do the Default Mapper and a Custom Mapper Differ?

The **default mapper** typically uses claims already issued in the ID Token. Its advantage is that the response is consistent with information at authentication time and avoids querying the user database every time.

A **custom mapper** allows the application to query the latest data from a database, LDAP, or domain service. This is useful when email, name, or user status can change after the token was issued. However, the application must ensure on its own that:

- **sub** always exists and is stable.
- Claims are filtered by actual scopes.
- Claims never exceed consent/privacy policies.
- Disabled/deleted accounts are handled per lifecycle policy.
- Infrastructure errors are not mistaken for invalid tokens.
- Responses contain no null/empty claims.
- Response subject matches the ID Token subject.

**Important:** when replacing **userInfoMapper**, you are responsible for the new mapper's claim logic. Do not assume a custom mapper automatically preserves all scope-filtering behavior of the default mapper.

### 5.3. UserInfo Endpoint Requires JwtDecoder

Spring Authorization Server 1.5.8 documentation notes that enabling OIDC automatically configures Resource Server support to authenticate access tokens at the UserInfo endpoint and requires a **JwtDecoder** bean.

Example:

~~~java
@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

This example uses the Authorization Server's JWK source. In production, signing keys must be persistent and **JwtDecoder** must verify signatures, issuer, and token conditions per configuration.

If the application uses opaque/reference access tokens, do not assume the built-in OIDC UserInfo endpoint of your version handles them identically to generic Resource Server opaque-token introspection. The SAS 1.5.8 guide requires **JwtDecoder**; verify token formats and actual integration. If opaque tokens are needed, design appropriate support and write integration tests specifically for the UserInfo endpoint.

## 6. Configuring the UserInfo Endpoint

### 6.1. Enabling OIDC and the Endpoint

**SecurityFilterChain** skeleton example:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcUserInfoAuthenticationContext;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        Function<OidcUserInfoAuthenticationContext, OidcUserInfo> userInfoMapper)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
            authorizationServer.oidc(oidc ->
                oidc.userInfoEndpoint(userInfo ->
                    userInfo.userInfoMapper(userInfoMapper)
                )
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

This is a configuration skeleton for Spring Authorization Server 1.5.x. A complete application still requires **RegisteredClientRepository**, **OAuth2AuthorizationService**, **AuthorizationServerSettings**, **JWKSource**, **JwtDecoder**, login filter chains, and appropriate persistence.

If you only want the default mapper, enabling **.oidc(Customizer.withDefaults())** is enough for the endpoint in a standard setup; add a custom mapper only when specific domain needs arise.

### 6.2. Customization Hooks

**OidcUserInfoEndpointConfigurer** provides:

- **userInfoRequestConverter(...)** / **userInfoRequestConverters(...)**: converts HTTP requests into authentication tokens.
- **authenticationProvider(...)** / **authenticationProviders(...)**: adds or customizes providers.
- **userInfoMapper(...)**: maps **OidcUserInfoAuthenticationContext** to **OidcUserInfo**.
- **userInfoResponseHandler(...)**: handles successful responses.
- **errorResponseHandler(...)**: handles **OAuth2AuthenticationException** and writes error responses.

For user-and-scope claim mapping, **userInfoMapper** is usually the most direct extension point. For transient user-store errors, you may need a custom **errorResponseHandler** to map infrastructure errors to HTTP 503. Keep standard OAuth2/Bearer error serialization for token errors.

When mapping scope errors, verify the actual HTTP status code emitted by your handler: **insufficient_scope** must produce HTTP 403 per RFC 6750, while **invalid_token** must produce HTTP 401. Never assume merely naming an OAuth2 error guarantees the framework picks the exact status across every configuration.

### 6.3. What Data Can the Mapper Access?

**OidcUserInfoAuthenticationContext** provides:
- **getAuthentication()** — current **OidcUserInfoAuthenticationToken**.
- **getAccessToken()** — access token used for the request.
- **getAuthorization()** — **OAuth2Authorization** tied to the access token; contains the ID Token and access-token state if the flow is OIDC Authorization Code.

**OAuth2Authorization** stores principal name, grant type, authorized scopes, tokens, and attributes. **OAuth2Authorization.Token** exposes **isActive()**, **isExpired()**, **isInvalidated()** along with claims/metadata.

Never take the subject from email or client-supplied query data. The subject source must be the verified ID Token/authorization or a stable subject identifier managed by the Authorization Server.

## 7. Writing a Mapper That Filters Claims by Scope

The example below demonstrates a mapper reading the current profile from **UserDirectory**, keeping **sub**, adding claims to the response only when the corresponding scope exists in the access token, and omitting unpopulated fields.

### 7.1. Application Data Contract

~~~java
import java.util.Optional;

public interface UserDirectory {
    Optional<UserProfile> findBySubject(String subject);
}

public record UserProfile(
        String subject,
        boolean active,
        String name,
        String givenName,
        String familyName,
        String email,
        Boolean emailVerified) {
}
~~~

**UserDirectory** and **UserProfile** are application-defined types, not Spring APIs. In a real system, the subject must map to an immutable user ID. Never use username/email as the linking key if those values can change or be recycled.

### 7.2. Sample Mapper

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcUserInfoAuthenticationContext;

final class CurrentUserInfoMapper {

    private final UserDirectory userDirectory;

    CurrentUserInfoMapper(UserDirectory userDirectory) {
        this.userDirectory = userDirectory;
    }

    OidcUserInfo map(OidcUserInfoAuthenticationContext context) {
        OAuth2Authorization authorization = context.getAuthorization();

        OAuth2Authorization.Token<OAuth2AccessToken> accessToken =
                authorization.getAccessToken();

        if (accessToken == null || !accessToken.isActive()) {
            throw oauth2Error("invalid_token");
        }

        Set<String> scopes = accessToken.getToken().getScopes();

        if (!scopes.contains(OidcScopes.OPENID)) {
            throw oauth2Error("insufficient_scope");
        }

        OAuth2Authorization.Token<OidcIdToken> idTokenHolder =
                authorization.getToken(OidcIdToken.class);

        if (idTokenHolder == null) {
            throw oauth2Error("invalid_token");
        }

        String subject = idTokenHolder.getToken().getSubject();
        if (subject == null || subject.isBlank()) {
            throw oauth2Error("invalid_token");
        }

        UserProfile user = this.userDirectory.findBySubject(subject)
                .orElseThrow(() -> oauth2Error("invalid_token"));

        if (!user.active() || !subject.equals(user.subject())) {
            throw oauth2Error("invalid_token");
        }

        Map<String, Object> claims = new LinkedHashMap<>();
        claims.put("sub", subject);

        if (scopes.contains(OidcScopes.PROFILE)) {
            putIfPresent(claims, "name", user.name());
            putIfPresent(claims, "given_name", user.givenName());
            putIfPresent(claims, "family_name", user.familyName());
            // Add middle_name, nickname, picture, locale...
            // when the domain model and policy actually provide them.
        }

        if (scopes.contains(OidcScopes.EMAIL)) {
            putIfPresent(claims, "email", user.email());
            putIfPresent(claims, "email_verified", user.emailVerified());
        }

        return new OidcUserInfo(claims);
    }

    private static void putIfPresent(
            Map<String, Object> claims, String name, Object value) {
        if (value == null) {
            return;
        }
        if (value instanceof String text && text.isBlank()) {
            return;
        }
        claims.put(name, value);
    }

    private static OAuth2AuthenticationException oauth2Error(String code) {
        return new OAuth2AuthenticationException(new OAuth2Error(code));
    }
}
~~~

Registering the function bean:

~~~java
@Bean
Function<OidcUserInfoAuthenticationContext, OidcUserInfo> userInfoMapper(
        UserDirectory userDirectory) {

    CurrentUserInfoMapper mapper = new CurrentUserInfoMapper(userDirectory);
    return mapper::map;
}
~~~

**Limitations of this example:**
- This mapper handles **openid**, **profile**, and **email**; add **address** and **phone** if your application issues those scopes.
- **UserDirectory** must return profiles by immutable subject. Never look up by email from the access token.
- The example treats a missing/disabled user as **invalid_token** per the application's deprovisioning policy. There must also be a process to revoke related authorizations/refresh tokens.
- Never catch **DataAccessException** and convert it into **invalid_token**; transient data-access errors must follow a 5xx error path.
- The default SAS provider already validates tokens. Checking **isActive()** inside the mapper is defense-in-depth and clarifies the contract; it does not replace JWT decoder checks.
- When replacing the default mapper, you are responsible for preserving scope filtering and the **sub** contract.

### 7.3. Adding the Remaining Scopes

The mapper can be extended following the same rule:

~~~java
if (scopes.contains(OidcScopes.ADDRESS) && user.address() != null) {
    claims.put("address", user.address());
}

if (scopes.contains(OidcScopes.PHONE) && user.phoneNumber() != null) {
    claims.put("phone_number", user.phoneNumber());
    if (user.phoneNumberVerified() != null) {
        claims.put("phone_number_verified", user.phoneNumberVerified());
    }
}
~~~

This extension assumes the domain model has **address()**, **phoneNumber()**, and **phoneNumberVerified()**. Add these methods only if your model actually defines them. Address must follow the OIDC Standard Claims structure—never return an arbitrary string and call it an address object.

## 8. Unavailable Users

"Unavailable" can describe several distinct situations. Policies should never equate an empty profile field with a locked account or an out-of-service directory.

### 8.1. Classifying User States

| State | Meaning | Suggested Handling at UserInfo |
|---|---|---|
| Active user, complete profile | Permitted claims can be returned. | 200, **sub** + claims per scope. |
| Active user, missing email/phone/address | Certain attributes do not exist. | 200, omit missing claims; never return null/empty. |
| Active user, claim hidden by privacy policy | OP is not allowed to disclose that claim. | 200, omit hidden claims. |
| Suspended/disabled user | Identity is no longer permitted to be used. | Revoke/disable authorization per policy; return **invalid_token** (401). |
| Deleted/deprovisioned user | Subject is no longer permitted access. | Revoke related grants/tokens; return **invalid_token** (401). |
| User merged or subject mapping changed | Risk of identity shift between old token and new user. | Never silently remap; preserve old subject or force new authorization. |
| User database timeout/unavailable | Current state cannot be determined. | 503; do not mark token invalid. |
| Corrupt user record / subject contradiction | Cannot build a response with trusted identity. | Reject response; investigate data integrity, never return a different **sub**. |

### 8.2. Locked or Deleted Users

An access token can still be unexpired when a user is locked. If the UserInfo mapper only reads claims stored in the ID Token, it may continue returning the old profile until the token expires.

Upon a deprovisioning event, you should:

1. Mark the user disabled/deleted in the identity source.
2. Prevent the user from creating new authorizations.
3. Revoke authorizations/refresh tokens per policy.
4. Mark related access tokens invalidated if the Authorization Server manages that state.
5. For JWT access tokens verified offline by Resource Servers, ensure introspection/denylist/session-version or a sufficiently short TTL if immediate revocation is required.
6. Have the UserInfo mapper check current user state and reject immediately once the account is unavailable.
7. Have the client handle **invalid_token** and initiate login/reauthorization per UX.
8. Record an internal audit event without logging raw access tokens.

**invalid_token** is a sensible choice once policy decides an access token is no longer accepted because the user was deprovisioned. OIDC does not define a separate error code to reveal "user locked" or "user deleted"; avoid returning detailed reasons to the client.

### 8.3. Do Not Remap Subject When User Identifiers Change

Suppose a user has subject **user-42**, and later their email changes from **an@example.com** to **an.nguyen@example.com**. The subject must never change along with the email.

If an old account is deleted and a new account is created, never reuse **sub=user-42** for a different person. If the organization needs account merging, build a controlled migration process and decide whether existing authorizations remain trustworthy.

The client must always compare **sub** in UserInfo with the ID Token. The mapper must never return a subject from a different user record just because an email lookup matched it.

### 8.4. Temporarily Unavailable User Store

A database timeout does not prove the user was deleted. If the mapper turns a timeout into **invalid_token**, clients may wipe sessions or force mass re-logins during a brief outage.

Separate exceptions cleanly:
- **UserNotFoundException** or **UserDisabledException**: policy can map to **invalid_token**.
- **UserDirectoryUnavailableException**: map to HTTP 503 with an appropriate **Retry-After**.
- **DataIntegrityException**: fail the request, alert, and investigate; never return untrusted claims.

**OidcUserInfoEndpointConfigurer.errorResponseHandler(...)** is the hook for handling **OAuth2AuthenticationException**. If the application needs to return 503 for user-store failures, translate the infrastructure error into an OAuth2AuthenticationException with an agreed internal code, then implement a handler mapping that code to HTTP 503. Keep standard serialization for all remaining Bearer/OAuth2 errors. Never convert every exception into 401.

## 9. ID Token Snapshot vs Dynamic UserInfo

There are two strategies for fetching profiles.

### 9.1. Using Claims from the ID Token

Spring Authorization Server's default mapper uses claims already embedded in the ID Token and filters them by requested/granted scopes.

Advantages:
- Response is consistent with data at login time.
- Fewer database queries at UserInfo.
- Less dependency on the user directory when clients call the endpoint.
- Easier to scale under high traffic.

Disadvantages:
- Profile can go stale after the user changes name/email.
- A user locked after token issuance may still have snapshot claims if access token state has not been invalidated.
- Unsuitable if business rules require the profile to always reflect live data.

### 9.2. Querying Current Profile with a Custom Mapper

A custom mapper queries the user directory by stable **sub** and builds the response at request time.

Advantages:
- Fresher profile data.
- Can detect disabled/deleted users.
- Can enforce current privacy policies and claim visibility.

Disadvantages:
- Increases latency and database/LDAP dependency.
- Requires timeouts, circuit breakers, caching, and 503 handling.
- Can cause the UserInfo response to differ from the ID Token snapshot.
- Must guarantee **sub** still matches the ID Token and is never remapped.

### 9.3. Do Not Arbitrarily Cache Profiles and Account Status

If UserInfo caches responses for several minutes, email/role/privacy state can become stale. If active user status is cached as well, a newly disabled user could continue retrieving their profile.

If caching:
- Cache keys must include issuer, subject, tenant, and profile version.
- TTL must match data sensitivity.
- Invalidate on profile changes, user disable/delete, or consent revocation.
- Never long-cache **invalid_token** errors keyed by raw token.
- Never cache 503 as a disabled-user state.
- Never cache access tokens or UserInfo responses in a shared cache lacking encryption/access control.

## 10. Configuring Error Handling and Deprovisioning

### 10.1. Classifying Errors in the Domain Service

Example contract:

~~~java
public class UserDisabledException extends RuntimeException {
    public UserDisabledException() {
        super("User is not available");
    }
}

public class UserDirectoryUnavailableException extends OAuth2AuthenticationException {
    public UserDirectoryUnavailableException() {
        super(new OAuth2Error(
                "temporarily_unavailable",
                "User directory is temporarily unavailable",
                null));
    }
}
~~~

These are application-defined exceptions; the snippet needs imports for **OAuth2AuthenticationException** and **OAuth2Error**. The mapper or user directory adapter can throw this exception when the backend is temporarily unreachable. Never put email, username, or raw tokens inside exception messages, as messages may appear in logs or telemetry.

The mapper can translate disabled/deleted users into OAuth2 **invalid_token**. User directory errors must be identified distinctly so the error handler returns 503.

### 10.2. errorResponseHandler as an Extension Point

Example configuration placement:

~~~java
.oidc(oidc -> oidc
    .userInfoEndpoint(userInfo -> userInfo
        .userInfoMapper(userInfoMapper)
        .errorResponseHandler(userInfoFailureHandler)
    )
)
~~~

**userInfoFailureHandler** is an application-provided **AuthenticationFailureHandler**. It must:

- Preserve standard Bearer error responses for **OAuth2AuthenticationException** such as **invalid_token** and **insufficient_scope**.
- Map transient user-directory errors to HTTP 503, **Retry-After**, and a body revealing no internal details.
- Never return stack traces or SQL/LDAP exceptions to the client.
- Record metrics/audits by normalized category.
- Never log access tokens or full UserInfo responses.

If replacing the default handler, test the **WWW-Authenticate** header, status code, content type, and response body. Preserve RFC 6750 error semantics.

In a custom handler, keep the Bearer challenge and error body intact for token/scope errors; map only user-directory infrastructure failures to 503. If status/format changes are unnecessary, keep the default handler and handle infrastructure errors through a separately tested adapter.

### 10.3. Deprovisioning Must Also Revoke the Refresh Path

Merely returning **invalid_token** at UserInfo does not stop a client from using a refresh token to obtain a new access token. When a user is locked/deleted, the lifecycle service must revoke corresponding authorizations/refresh tokens and block new token issuance.

For JWT access tokens verified offline by Resource Servers, revocation state at the Authorization Server does not propagate automatically to APIs. Choose among:
- Introspection or online state checks.
- **jti**-based denylist.
- Session/user token versioning.
- Short TTL within an accepted residual window.
- Dynamic authorization checks on sensitive APIs.

UserInfo is one endpoint; deprovisioning must apply consistently across other Resource Servers if security requires immediate user lockout.

## 11. Testing the UserInfo Endpoint

### 11.1. Token Matrix

| Test Case | Expected Result |
|---|---|
| Valid, active access token with **openid** | 200 and **sub** is always present. |
| Missing Authorization header | 401 Bearer challenge, no details leaked. |
| Malformed token | 401 **invalid_token**. |
| Expired token | 401 **invalid_token**. |
| Revoked/invalidated token | 401 **invalid_token** if state is checked by the endpoint. |
| Token with wrong issuer/signature/audience per policy | 401 **invalid_token**. |
| Token missing **openid** scope | Rejected per policy, typically **insufficient_scope** (403). |
| Token with **openid profile** | Contains **sub** and permitted profile claims. |
| Token with **openid email** | Contains **sub** and email claims if data exists/is permitted. |
| Token with **openid** only | Needs only **sub**; no out-of-scope profile/email returned. |

### 11.2. Profile and Scope Matrix

| User Data | Scope | Result |
|---|---|---|
| Has name and email | **openid profile email** | May return **sub**, profile claims, email claims. |
| Missing email | **openid email** | 200, **sub**; omits **email** and **email_verified**. |
| Has email, lacks email scope | **openid profile** | Does not return email. |
| Email hidden by privacy policy | **openid email** | 200, omits email claims. |
| Missing profile fields | **openid profile** | 200, at minimum **sub**. |
| Active user lacking phone | **openid phone** | 200, omits phone claims. |
| Mapper returns **sub** different from ID Token | Any valid scope | Client discards the entire UserInfo response. |

### 11.3. User Lifecycle and Infrastructure Matrix

| Test Case | Expected Result |
|---|---|
| Active user | 200, claims per scope. |
| Disabled user | Authorization/refresh token handled per deprovisioning; UserInfo rejects with **invalid_token**. |
| Deleted user | Never remaps to another user; old token can no longer fetch profile. |
| User changes email | **sub** unchanged; new email reflects dynamic mapper or chosen snapshot policy. |
| User merged into new subject | Never alters **sub** in UserInfo for old tokens. |
| User directory timeout | 503, **Retry-After**; does not mark token invalid. |
| User directory returns inconsistent record | Fail request, alert; never emit an incorrect **sub**. |
| Authorization store unavailable | Do not accept token when state cannot be verified per policy; handle service error. |
| UserInfo response cache stale after disable | Invalidation/TTL must fall within revocation SLA. |

### 11.4. MockMvc Example Checking Error Tokens

Illustrative test template:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class UserInfoEndpointTest {

    @Autowired
    MockMvc mvc;

    @Test
    void expiredTokenIsRejected() throws Exception {
        mvc.perform(get("/userinfo")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer EXPIRED_TEST_ACCESS_TOKEN"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                    HttpHeaders.WWW_AUTHENTICATE,
                    containsString("invalid_token")));
    }

    @Test
    void validTokenWithoutEmailScopeDoesNotExposeEmail()
            throws Exception {
        mvc.perform(get("/userinfo")
                .header(HttpHeaders.AUTHORIZATION,
                        "Bearer OPENID_PROFILE_ONLY_TOKEN"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.sub").value("user-42"))
            .andExpect(jsonPath("$.email").doesNotExist());
    }
}
~~~

This is a sample test; you need fixtures creating real JWTs, JWKs, authorizations, user profiles, and scopes. Never use fake production tokens. For expired tokens, generate a JWT with **exp** in the past or an expired authorization fixture; for the missing-email case, the access token must be valid and have only the **openid profile** scopes.

### 11.5. Checking Subject Binding on the Client

Integration tests should:
1. Receive the ID Token from the Token Endpoint.
2. Verify signature, issuer, audience, expiry, and nonce.
3. Call UserInfo with the access token.
4. Read **sub** from UserInfo.
5. Compare it exactly with **sub** in the ID Token.
6. If different or missing, discard all claims.
7. Verify the client does not persist an unverified profile response into session/database.

## 12. Common Errors and Diagnostics

| Symptom | Possible Cause | Resolution |
|---|---|---|
| UserInfo returns 401 for newly issued token | Wrong token issuer/audience, bad decoder/JWK, or authorization not persisted properly. | Check **JwtDecoder**, issuer, JWK, and authorization persistence. |
| Expired token returns 200 | Mapper/controller bypassed token validation. | Keep standard filters/providers and expiration checks. |
| Revoked token still returns profile | Revocation state unchecked or custom path bypasses provider. | Check **OAuth2AuthorizationService**, token active state, and provider chain. |
| Missing email scope yet response includes email | Custom mapper returns entire profile without scope filtering. | Map email only when access token has **email**. |
| Missing email causes endpoint to return 403 | Confusing optional claim absence with insufficient scope. | Omit missing/unpermitted claims; reserve 403 for mandatory scopes. |
| Disabled user still gets stale profile | Default mapper reads ID Token snapshot or custom mapper skips user state check. | Add deprovisioning and dynamic mapper if live status is required. |
| User directory outage returns 401 | Infrastructure exception converted to invalid token. | Separate exceptions and return 503. |
| UserInfo sub differs from ID Token | Unstable subject mapping or cross-session token mix-up. | Use immutable subjects and client-side sub checks. |
| UserInfo lacks sub | Custom mapper forgot mandatory claim. | Always set sub before adding optional claims. |
| Response has null/empty fields | Mapper serializes all attributes even when unpopulated. | Omit claims without values. |
| Client passes token in query string | SDK/custom client calls improperly. | Use Authorization Bearer over TLS. |
| Opaque token fails with default UserInfo | Assumed SAS endpoint supports same config as generic opaque resource server. | Check JwtDecoder requirement and design version-appropriate custom integration. |
| Profile cache still holds data after disable | Cache not invalidated or TTL too long. | Purge via events, shorten TTL, and verify cache keys. |
| UserInfo returns claims beyond scope | Mapper ignores actual scopes. | Rely on access token scopes and privacy policy. |
| Deleted user recreated with same email gets old data | Email used as subject/lookup key. | Use stable subjects; never reuse sub. |
| API client trusts UserInfo without checking sub | Skipped anti-token-substitution step. | Always match UserInfo sub against ID Token sub. |

## 13. Hands-on Exercise

**Context:** The Authorization Server serves **employee-portal**, **mobile-app**, and **partner-console**. The three clients have different scopes. A user is locked after receiving an unexpired access token; meanwhile, the user directory experiences a brief outage.

### Requirements

1. Enable the OIDC UserInfo endpoint and configure **JwtDecoder** matching the JWK source.
2. Use the default mapper to verify scope-to-claims behavior before customizing.
3. Build **UserDirectory** lookup by immutable **sub**, never by email.
4. Write a custom mapper returning mandatory **sub** and filtering claims by **openid**, **profile**, **email**, **address**, and **phone**.
5. Test tokens missing **openid**, expired tokens, revoked tokens, and tokens with wrong audience/issuer.
6. When the user has no email, return a response without **email/email_verified**, never null/empty.
7. When the user is disabled/deleted, revoke authorizations/refresh tokens per policy and return **invalid_token**.
8. When the user directory times out, return 503 and **Retry-After**; do not revoke tokens due to infrastructure failure.
9. Ensure the client verifies UserInfo **sub** equals ID Token **sub**.
10. Test profile updates: email changes while **sub** stays unchanged.
11. Test account merge/deletion: never remap an old subject to a new user.
12. Test response caching, event invalidation, and multiple Authorization Server instances.
13. Verify logs contain no raw access tokens, emails, or full UserInfo bodies.
14. Measure latency and error rates of the UserInfo endpoint by category.

**Completion criteria:** invalid tokens receive **invalid_token**; missing mandatory scopes receive **insufficient_scope**; unavailable optional claims are omitted; disabled/deleted users are deprovisioned; user store outages return 503; **sub** is always correct and the client verifies it matches the ID Token.

## 14. Pre-Production Deployment Checklist

- [ ] UserInfo endpoint operates exclusively over HTTPS/TLS.
- [ ] Clients send access tokens via Authorization Bearer, never in query strings.
- [ ] Endpoint supports GET and POST per OIDC Core.
- [ ] Clients obtain **userinfo_endpoint** from verified Provider Metadata.
- [ ] **JwtDecoder** and JWK/issuer are properly configured for Spring Authorization Server.
- [ ] Tokens must be valid, unexpired, and not revoked per state policy.
- [ ] **invalid_token** returns 401 and an appropriate Bearer challenge.
- [ ] **insufficient_scope** returns 403 only when a scope is genuinely mandatory.
- [ ] Missing optional scopes do not fail the request; corresponding claims are omitted.
- [ ] **sub** is always present and stable.
- [ ] Clients compare UserInfo **sub** with ID Token **sub**; discard response on mismatch.
- [ ] Claims are filtered by actual scopes of the access token.
- [ ] Claims without values are omitted, never returned as null/empty.
- [ ] PII is returned only per consent, scope, and privacy policy.
- [ ] Disabled/deleted users trigger deprovisioning and revoke authorizations/refresh tokens.
- [ ] Old subjects are never remapped to new users when email/username changes.
- [ ] User directory outages return 503, never converted into invalid tokens.
- [ ] Caching has TTL/invalidation aligned with profile updates and deprovisioning SLAs.
- [ ] Error handlers do not leak SQL, LDAP, user existence, or token details.
- [ ] Logs/traces contain no raw access tokens, UserInfo bodies, or unnecessary PII.
- [ ] Tested JWT expiry/revocation, scopes, missing user, disabled user, and database outage.
- [ ] Tested multiple instances, restarts, cache invalidation, and subject mismatch.
- [ ] Verified behavior matches the actual Spring Authorization Server version in use.

## Summary

The OIDC UserInfo Endpoint must handle **access token validity**, **granted scopes**, **actually disclosable claims**, and **current End-User state** distinctly. RFC 6750 defines **invalid_token** as 401 and **insufficient_scope** as 403; OIDC Core permits omitting unavailable/undisclosed optional claims while requiring **sub** in every UserInfo Response. The client must cross-check that **sub** against the ID Token and discard the response if they do not match.

Spring Authorization Server 1.5.8 provides **OidcUserInfoAuthenticationProvider**, **OidcUserInfoAuthenticationContext**, and **OidcUserInfoEndpointConfigurer.userInfoMapper(...)**. The default mapper extracts standard claims from the ID Token by scope; a custom mapper can fetch the live profile while maintaining scope filtering, subject stability, privacy, and error semantics. When a user is disabled/deleted, the system must deprovision authorizations/refresh tokens and reject tokens per policy; when the user directory is merely temporarily unavailable, return a 503 service error instead of concluding the token is invalid.

The solution is complete only when you have tested the entire path from access token, authorization state, and user directory to the UserInfo response and client-side sub validation.

## References

1. [OpenID Connect Core 1.0 incorporating errata set 2 — Section 5.3 UserInfo Endpoint](https://openid.net/specs/openid-connect-core-1_0.html): UserInfo request, TLS, GET/POST, Bearer token, sub, successful response, error response, and response validation.
2. [OpenID Connect Core 1.0 — Section 5.4 Requesting Claims using Scope Values](https://openid.net/specs/openid-connect-core-1_0.html#ScopeClaims): claims requested via profile, email, address, phone.
3. [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): invalid_token, insufficient_scope, HTTP 401/403, and WWW-Authenticate.
4. [Spring Authorization Server 1.5.8 — How-to: Customize the OpenID Connect 1.0 UserInfo response](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-userinfo.html): enabling endpoint, default claims, custom ID Token, and custom mapper.
5. [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): OidcUserInfoEndpointConfigurer, converters, providers, mapper, and response/error handlers.
6. [Spring Authorization Server 1.5.8 — OidcUserInfoAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcUserInfoAuthenticationProvider.html): provider and setUserInfoMapper.
7. [Spring Authorization Server 1.5.8 — OidcUserInfoEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OidcUserInfoEndpointConfigurer.html): extension points for UserInfo endpoint.
8. [Spring Authorization Server 1.5.8 — OidcUserInfoAuthenticationContext API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcUserInfoAuthenticationContext.html): access token and authorization context.
9. [Spring Authorization Server 1.5.8 — OAuth2Authorization API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2Authorization.html): authorization, token, and scopes.
10. [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): authorization model, token state, scopes, and token lifecycle.
11. [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection and how Resource Server processes access tokens.
12. [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): Provider Metadata and userinfo_endpoint.
