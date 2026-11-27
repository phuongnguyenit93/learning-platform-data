# 12.2. `OidcUserService` and OIDC UserInfo Loading

In **Spring Security OAuth 2.0/OIDC Client**, logging in with OpenID Connect (OIDC) is not just redirecting the user to an identity provider and receiving an access token. The client needs to **verify the ID Token**, identify the logged-in user, and optionally **load additional profile information** from the **UserInfo Endpoint**. On the Servlet stack, the **`OidcUserService`** component plays a central role in building the `OidcUser` principal from the ID Token along with permitted claims obtained via UserInfo.

This lesson explains where `OidcUserService` operates in the OAuth2 Login flow, when UserInfo is loaded, how `sub` is matched between the ID Token and UserInfo, how Spring represents data with `OidcUser`/`OidcUserInfo`, and key considerations when customizing the service in real-world applications.

> **Key Focus:** The ID Token proves the authentication result under OIDC; UserInfo provides authorized profile claims. `OidcUserService` combines the data to create the logged-in user, **and must never skip identity verification or treat UserInfo as an uncontrolled independent source of truth**.

## 1. Placing `OidcUserService` in the Login Flow

With the Authorization Code Flow, the Spring Security application acts as an **OIDC Relying Party**: it trusts a registered OpenID Provider (OP), rather than verifying the user's password itself.

A typical Servlet login session includes:

1. The user navigates to `/oauth2/authorization/company` or accesses a protected resource requiring login.
2. Spring Security builds an authorization request containing `client_id`, `redirect_uri`, `scope=openid ...`, `state`, and appropriate flow-protection parameters.
3. The browser is redirected to the OP's Authorization Endpoint.
4. The OP authenticates the user and returns an authorization code to Spring's callback, typically `/login/oauth2/code/company`.
5. Spring exchanges the authorization code at the Token Endpoint, receiving an access token and an ID Token.
6. Spring **verifies the ID Token** according to relevant OIDC rules such as signature, issuer, audience, timestamps, and nonce when applicable.
7. **`OidcUserService`** handles the profile-loading request; if eligible, it uses the access token to call the **UserInfo Endpoint**.
8. Spring verifies that the UserInfo data belongs to the **same `sub` subject** as the ID Token, builds the `OidcUser`, and completes `Authentication`.
9. The application uses this principal to display name, email, picture, or combine with internal permission sources for authorization.

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant C as Spring Security Client
    participant OP as OpenID Provider

    U->>B: Open application
    B->>C: GET /oauth2/authorization/company
    C-->>B: 302 to Authorization Endpoint
    B->>OP: Authorization Request (openid, state, PKCE...)
    OP->>U: Login/consent
    OP-->>B: 302 callback?code=...&state=...
    B->>C: GET /login/oauth2/code/company
    C->>OP: POST Token Endpoint, exchange code
    OP-->>C: access_token + id_token (+ refresh_token?)
    C->>C: Verify ID Token and protocol claims
    C->>C: Call OidcUserService.loadUser(...)
    opt UserInfo endpoint available and policy requires loading
        C->>OP: GET UserInfo, Authorization: Bearer access_token
        OP-->>C: JSON with sub, name, email...
        C->>C: Match UserInfo sub against ID Token
    end
    C->>C: Create OidcUser, map authorities
    C-->>B: Complete login, create session/redirect
```

**Key distinction:** `OidcUserService` is not the class that sends the authorization code to the Token Endpoint, nor is it the class that handles redirects from the browser. It runs **after the Client has already obtained a valid ID Token and access token** during the login process.

## 2. What Is `OidcUserService`?

The `OidcUserService` class belongs to package:

```java
org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService
```

By contract, it implements an `OAuth2UserService` specialized for OpenID Connect:

```java
OAuth2UserService<OidcUserRequest, OidcUser>
```

Main method:

```java
OidcUser loadUser(OidcUserRequest userRequest)
    throws OAuth2AuthenticationException;
```

Where:

| Component | Meaning |
|---|---|
| `OidcUserRequest` | Input containing ClientRegistration information, access token, ID Token, and necessary token response data |
| `OidcUserService` | Can load UserInfo and build an OIDC principal based on received/verified data |
| `OidcUserInfo` | Object representing UserInfo claims, when data has been loaded |
| `OidcUser` | OIDC principal received by the application after successful login |
| `DefaultOidcUser` | Common `OidcUser` implementation holding authorities, ID Token, and UserInfo |
| `OidcUserAuthority` | OIDC-specific authority that can carry ID Token/UserInfo claim information |
| `DefaultOAuth2UserService` | Component typically used to call the UserInfo Endpoint with the access token and read OAuth2 user attributes |

These types belong to **Spring Security OAuth2 Client**, not controllers or business services written by your project.

### 2.1. Distinguishing `OidcUserService` and `DefaultOAuth2UserService`

| Characteristic | `OidcUserService` | `DefaultOAuth2UserService` |
|---|---|---|
| Responsibility | Handles OIDC login, combining ID Token with UserInfo | Loads user information from an OAuth2 UserInfo/user attributes endpoint |
| Input | `OidcUserRequest` | `OAuth2UserRequest` |
| Output | `OidcUser` | `OAuth2User` |
| Uses OIDC ID Token as foundation? | Yes | Not a core requirement |
| Example | Google/Keycloak OIDC Login | Standard GitHub OAuth2 Login |
| Relationship | Can **delegate the UserInfo call** to an internal OAuth2UserService | Can be used by `OidcUserService` as the UserInfo loading component |

Do not confuse `DefaultOAuth2UserService` with an ID Token validator. A successful UserInfo HTTP call returning JSON is **not sufficient** to prove a valid OIDC login session.

### 2.2. `OidcUserService` Differs from Internal Account Management

`OidcUserService` returns a principal to Spring Security. It does not automatically:

- Create a user record in the business database.
- Assign `ROLE_ADMIN` to users whose email belongs to a particular domain.
- Synchronize all profile information across multiple systems.
- Determine whether an employee still belongs to the organization or has left.
- Automatically call the UserInfo Endpoint again on every subsequent request.
- Keep all claims up to date throughout the lifetime of the HTTP session.

If the application needs user provisioning, profile synchronization, or permission mapping, design dedicated business services with clear data boundaries and error policies.

## 3. What Information Does `OidcUserRequest` Contain?

After the Token Endpoint returns a valid response in an OIDC flow, Spring Security constructs an `OidcUserRequest` for the service to process.

Conceptually, this object provides:

| Data | Common Accessor | Purpose |
|---|---|---|
| Client registration | `getClientRegistration()` | Identifies provider, endpoints, issuer, and registered Client |
| Access token | `getAccessToken()` | Used to call the UserInfo Endpoint when appropriate |
| ID Token | `getIdToken()` | Identifies the verified subject and OIDC claims |
| Additional token response parameters | `getAdditionalParameters()` | Supports extensions when available |

Illustrative logic example:

```java
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;

void inspectRequest(OidcUserRequest request) {
    String registrationId =
        request.getClientRegistration().getRegistrationId();

    OidcIdToken idToken = request.getIdToken();
    OAuth2AccessToken accessToken = request.getAccessToken();

    String subject = idToken.getSubject();

    // For illustration only; do not log tokenValue in production.
    System.out.println("registrationId=" + registrationId);
    System.out.println("subject present=" + (subject != null));
    System.out.println("access token type=" +
        accessToken.getTokenType().getValue());
}
```

In practice, you do not need to instantiate `OidcUserRequest` manually to run the default flow; Spring Security passes it to `OidcUserService` at the right time.

**Do not log raw `getAccessToken().getTokenValue()` or `getIdToken().getTokenValue()`.** These values are security credentials or contain private claims.

## 4. ID Token and UserInfo: Two Different Data Sources

An OIDC Client usually receives claims in two places:

1. **ID Token:** A JWT issued by the OP and verified by the Client. It contains required protocol claims such as `iss`, `sub`, `aud`, `exp`, and `iat`.
2. **UserInfo response:** Profile claims provided by the OP via an HTTP endpoint when the Client holds a valid access token and is permitted to access it.

An ID Token might contain only:

```json
{
  "iss": "https://id.example.test/realms/company",
  "sub": "user-782",
  "aud": "spring-web-client",
  "exp": 1794794700,
  "iat": 1794791100
}
```

The corresponding UserInfo response might contain:

```json
{
  "sub": "user-782",
  "name": "Nguyễn Thị Lan",
  "preferred_username": "lan.nguyen",
  "picture": "https://cdn.example.test/avatars/782.png",
  "email": "lan@example.test",
  "email_verified": true,
  "locale": "vi-VN"
}
```

These values are illustrative only. `sub` appears in **both sources** and must refer to the exact same principal.

### 4.1. Why Not Put Every Claim in the ID Token?

The ID Token is designed to prove the authentication result to the Client, not necessarily to be a complete copy of the user profile. Separating UserInfo allows the OP to:

- Provide only fields permitted by the granted consent and scopes.
- Return attributes that do not belong directly inside the ID Token.
- Enforce disclosure policies at the UserInfo Endpoint.
- Reduce the number of claims the Client must receive in an authentication token.

However, UserInfo is not a "guaranteed channel for every claim". The provider may lack the data, not be permitted to share it, or not support the endpoint.

### 4.2. Is UserInfo Required for Every OIDC Login?

**No.** An OIDC Login can succeed without loading UserInfo if the ID Token and required verification steps are valid. Some providers intentionally place certain profile claims in the ID Token; others do not publish a UserInfo Endpoint in their metadata.

If the Client needs `email` and does not see it in the ID Token, the next step is to check **UserInfo configuration**, scopes, and the provider; do not assume Spring is broken.

## 5. How Is the UserInfo Endpoint Called?

Under OIDC, the Client can use the access token to request user information. A common HTTP request:

```http
GET /realms/company/protocol/openid-connect/userinfo HTTP/1.1
Host: id.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
Accept: application/json
```

Illustrative response:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "sub": "user-782",
  "name": "Nguyễn Thị Lan",
  "email": "lan@example.test",
  "email_verified": true
}
```

The **access token** is the credential for calling UserInfo; the **ID Token** must not be substituted as the Bearer token for this endpoint.

For Spring Security Servlet OAuth2 Login, calling UserInfo is normally handled through the `OAuth2UserService` component used by `OidcUserService`. The application does not need to write its own `RestTemplate` call in a controller just for the default login flow.

### 5.1. Where Are Parameters Sent?

- The `scope` parameter was requested at the Authorization Endpoint; the Provider grants the appropriate permissions.
- The access token is received from the **Token Endpoint**.
- When calling UserInfo, the Client puts the access token in the HTTP `Authorization` header as a Bearer token when supported by the provider.
- The UserInfo response may contain claims from OIDC Standard Claims and provider-specific claims.
- `sub` in UserInfo must match `sub` in the ID Token.

Do not place the access token in the query string such as `/userinfo?access_token=...`. Putting credentials in URLs increases leakage risk through logs, browsers, proxies, and observability systems.

### 5.2. Can the UserInfo Response Be JSON or JWT?

OIDC defines a standard JSON UserInfo response and also supports signed/encrypted responses depending on configuration/provider. **Do not assume every Spring Security Client automatically handles every UserInfo protection variant a provider might emit.**

If an OP returns UserInfo as a signed/encrypted JWT or with custom content, check support in your Spring Security version and the corresponding registration/metadata requirements. Never skip signature verification just to parse the payload, and never treat JSON fetched over the network as verified identity data without proper identity checks.

## 6. When Does `OidcUserService` Decide to Load UserInfo?

This is a very common point of confusion when integrating an IdP.

`OidcUserService` can only load UserInfo when the necessary data and conditions are met, such as:

- `ClientRegistration` provides a **UserInfo Endpoint URI** (via OIDC discovery or provider configuration).
- A valid access token is present and usable to call UserInfo.
- The OIDC user service policy in the current version/configuration permits loading UserInfo.
- Granted scopes and matching configuration justify requesting profile information.
- The provider actually accepts the request and returns data according to the UserInfo contract.

In the default configuration of many Spring Security versions, the service checks standard profile-related scopes such as **`profile`, `email`, `address`, `phone`** when deciding whether to call UserInfo. Customization options for the retrieval condition depend on the API of the Spring Security version in use.

### 6.1. The `openid` Scope Does Not Mean UserInfo Is Always Called

Example:

```yaml
scope:
  - openid
```

This configuration requests **OIDC login**, but does not itself indicate that full profile details must be loaded. In common default configurations, if no profile-related scopes or endpoint are present, UserInfo may **not be called**.

If the application needs name and email:

```yaml
scope:
  - openid
  - profile
  - email
```

Then the service can load UserInfo if the provider publishes the endpoint and other conditions are satisfied. However, **requesting a scope does not guarantee claims will appear**. To know the exact behavior, verify the actually granted scopes, metadata, and provider policies.

### 6.2. Common OIDC Profile Scopes

| Scope | Commonly Requested Claims | Notes |
|---|---|---|
| `openid` | Triggers OIDC authentication and ID Token request | Not a promise to provide a full profile |
| `profile` | `name`, `given_name`, `family_name`, `picture`, `locale`, `preferred_username`, ... | Claims may be missing or withheld by the provider |
| `email` | `email`, `email_verified` | Email may be missing, mutable, or unverified |
| `address` | `address` | Usually an object with multiple nested fields |
| `phone` | `phone_number`, `phone_number_verified` | Does not prove the phone number was used as MFA |

For example, an application that only needs to display name/email should not necessarily request `address` and `phone`. Apply the **data minimization principle** to avoid accessing user data beyond what is needed.

### 6.3. If the ID Token Already Has `name`, Is UserInfo Still Needed?

No. If the provider already includes all required claims in the ID Token and OIDC verification succeeds, the application may not need an extra HTTP request just to fetch duplicate data. However, **whether UserInfo is called is governed by `OidcUserService` configuration**, and does not automatically turn off just because you observe `name` inside the ID Token.

If you need to reduce latency or avoid dependency on that endpoint, review the customization points in your Spring Security version and the provider's capabilities. Do not blindly block UserInfo when the application actually depends on claims that only exist there.

## 7. Checking `sub`: Binding UserInfo to the ID Token

**This is one of the most important security constraints of OIDC UserInfo.**

According to OpenID Connect Core, the **`sub`** claim in the UserInfo response **must match exactly** the subject identifier in the ID Token. The Client must verify that condition; if they do not match, **the UserInfo response must not be used**.

Valid example:

```text
ID Token:
  iss = https://id.example.test
  sub = user-782

UserInfo:
  sub = user-782

=> Same subject according to the OP
```

Invalid example:

```text
ID Token:
  iss = https://id.example.test
  sub = user-782

UserInfo:
  sub = user-999

=> Mismatch: must reject UserInfo data
```

The issue is not merely displaying the wrong name. If the Client trusts UserInfo belonging to someone else, an attacker could exploit that confusion to swap a user's profile, email, or permissions.

### 7.1. Why Cannot Email Replace `sub`?

Suppose:

```json
{
  "sub": "user-782",
  "email": "lan@example.test"
}
```

Email can change, be absent, be unverified, or be reused. In OIDC, stable identity should be based on **issuer and subject**:

```text
(iss, sub)
```

Example:

```text
("https://id.example.test/realms/company", "user-782")
```

When supporting multiple OPs or multiple tenants, a bare `sub` alone is also insufficient: two different issuers can assign the same `sub` value to two completely different subjects.

### 7.2. Do Not "Patch" `sub` to Bypass Errors

If UserInfo returns a subject that does not match the ID Token, **never** write code like:

```java
// WRONG: mutating a claim received over the network to force it to match the ID Token.
userInfoClaims.put("sub", idToken.getSubject());
```

That hides an identity error and disables the protection mechanism. You must investigate the provider, token, tenant configuration, or mispointed UserInfo endpoint. Never swallow the exception or use any other claims from a subject-mismatched response.

### 7.3. How Does Spring Security Help Verify This?

In the standard OIDC Login path, `OidcUserService` checks that the UserInfo response matches the ID Token subject. When customizing the service or replacing the internal UserInfo loader, **you must preserve the security checks** performed by the framework.

Do not treat a naive custom implementation that just does "HTTP GET then map JSON to user" as equivalent to the default `OidcUserService` if it omits `sub` comparison and OIDC checks.

## 8. From `OidcUserInfo` to `OidcUser`

When conditions are met, the service puts the ID Token and UserInfo into an `OidcUser`, typically `DefaultOidcUser`. This principal gives the application an interface to access:

- `getIdToken()`: the ID Token stored on the principal.
- `getUserInfo()`: the UserInfo data if loaded; may be `null`.
- `getClaims()`: the set of claims exposed by the OIDC principal, potentially combined from the ID Token and UserInfo.
- `getSubject()`: the OIDC subject.
- `getAuthorities()`: the `GrantedAuthority` instances created/mapped by Spring Security.
- `getName()`: the principal name based on the configured attribute, typically derived from `sub`.

### 8.1. An Example Comparing the Three Sources

ID Token:

```json
{
  "iss": "https://id.example.test",
  "sub": "u-123",
  "aud": "spring-client",
  "iat": 1794791100,
  "exp": 1794794700
}
```

UserInfo:

```json
{
  "sub": "u-123",
  "name": "Nguyễn Thị Lan",
  "email": "lan@example.test",
  "email_verified": true
}
```

Principal in the application:

```text
OidcUser:
  subject = u-123
  idToken = {iss, sub, aud, iat, exp, ...}
  userInfo = {sub, name, email, email_verified}
  claims = OIDC data provided by Spring from the corresponding sources
  authorities = GrantedAuthority set per authentication configuration
```

Do not rely on claim merge order when a name appears in both the ID Token and UserInfo with different values. If your project needs to know specifically where a field came from, read **`getIdToken()` and `getUserInfo()` separately**, and define consistent usage rules.

### 8.2. `getUserInfo()` Can Be Null

A common mistake:

```java
// May throw NullPointerException if UserInfo is absent.
String email = user.getUserInfo().getEmail();
```

Safe way to read it:

```java
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

String emailFromUserInfo(OidcUser user) {
    OidcUserInfo userInfo = user.getUserInfo();
    if (userInfo == null) {
        return null;
    }
    return userInfo.getClaimAsString("email");
}
```

The absence of `OidcUserInfo` **does not automatically mean login failed**. The provider may not publish an endpoint, the service may not need to load it, or the data may already be sufficient in the ID Token.

### 8.3. Address, Phone, and Boolean Values

A UserInfo response might contain:

```json
{
  "sub": "u-123",
  "email": "lan@example.test",
  "email_verified": true,
  "phone_number": "+84901234567",
  "phone_number_verified": false,
  "address": {
    "formatted": "12 Street A, Ho Chi Minh City",
    "locality": "Ho Chi Minh City",
    "country": "VN"
  }
}
```

Notes on data types:

- `email_verified` and `phone_number_verified` are **Booleans** when returned per specification; they may be absent.
- `address` is an **object**, not always a String.
- `phone_number` is personal data; do not display or log it without purpose.
- Having a phone number does not mean the user completed MFA.
- A provider does not necessarily possess every claim within the granted scopes.

Check `Boolean.TRUE.equals(value)` when business policy requires the provider to have verified an attribute; do not treat a missing claim as a positive confirmation from the provider.

## 9. Reading OIDC Info in Spring MVC

An application can receive the principal using `@AuthenticationPrincipal` after OAuth2 Login succeeds:

```java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class ProfileController {

    @GetMapping("/me")
    public Map<String, Object> me(@AuthenticationPrincipal OidcUser user) {
        if (user == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("subject", user.getSubject());
        result.put("issuer", user.getIdToken().getIssuer().toString());

        String displayName = user.getClaimAsString("name");
        if (displayName != null) {
            result.put("displayName", displayName);
        }

        String email = user.getClaimAsString("email");
        if (email != null) {
            result.put("email", email);
        }

        Boolean emailVerified = user.getClaimAsBoolean("email_verified");
        if (emailVerified != null) {
            result.put("emailVerified", emailVerified);
        }

        OidcUserInfo userInfo = user.getUserInfo();
        result.put("userInfoLoaded", userInfo != null);
        return result;
    }
}
```

Example response:

```json
{
  "subject": "user-782",
  "issuer": "https://id.example.test/realms/company",
  "displayName": "Nguyễn Thị Lan",
  "email": "lan@example.test",
  "emailVerified": true,
  "userInfoLoaded": true
}
```

This endpoint is **only for authenticated users**; enforce `authenticated()` in `SecurityFilterChain`. In production, do not return `issuer` or `userInfoLoaded` if the UI does not use them. Never return all of `user.getClaims()` to every frontend by default, as claims can include personal data or unnecessary internal details.

### 9.1. Distinguishing Each Claim's Source When Debugging

```java
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

void inspectSources(OidcUser user) {
    Object idTokenEmail = user.getIdToken().getClaim("email");

    OidcUserInfo userInfo = user.getUserInfo();
    Object userInfoEmail =
        userInfo == null ? null : userInfo.getClaim("email");

    // Only illustrates data source, do not print real email to logs.
    boolean inIdToken = idTokenEmail != null;
    boolean inUserInfo = userInfoEmail != null;
}
```

This helps determine "email is in ID Token", "email comes from UserInfo", or "both are missing". In operational logs, record **claim presence/absence** rather than PII values.

## 10. Configuring Spring Boot to Use OIDC UserInfo

A typical `ClientRegistration`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
              - email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          company:
            issuer-uri: https://id.example.test/realms/company
```

Explanation:

- `openid` specifies an OIDC request.
- `profile`, `email` request profile-related claim groups.
- `issuer-uri` allows Spring to discover the OpenID Provider's metadata, including endpoints and JWKS when the provider supports discovery.
- `client-id` and `client-secret` belong to the application's own registration, not UserInfo data.
- `redirect-uri` is the callback to complete the authorization code flow, not the UserInfo Endpoint.

The provider publishes metadata at a well-known path matching the issuer, for example with a Keycloak realm:

```text
https://id.example.test/realms/company/.well-known/openid-configuration
```

The content may include:

```json
{
  "issuer": "https://id.example.test/realms/company",
  "authorization_endpoint": "https://id.example.test/realms/company/protocol/openid-connect/auth",
  "token_endpoint": "https://id.example.test/realms/company/protocol/openid-connect/token",
  "userinfo_endpoint": "https://id.example.test/realms/company/protocol/openid-connect/userinfo",
  "jwks_uri": "https://id.example.test/realms/company/protocol/openid-connect/certs"
}
```

URLs are for illustration only. Spring cannot reliably infer a trustworthy UserInfo Endpoint if metadata is incorrect or restricted. Verify the actual issuer and provider configuration.

### 10.1. Enabling OAuth2 Login

For a Spring MVC/Servlet application:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

When OIDC login succeeds, the application can access `OidcUser` in the SecurityContext. There is no need to write a custom `OidcUserService` if the default already fits the provider and claim-reading needs.

### 10.2. If the Provider Does Not Support Discovery

When a provider supports OIDC integration but does not expose metadata that Spring can auto-discover, endpoints can be configured manually:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          manual-oidc:
            provider: custom-op
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [openid, profile, email]
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          custom-op:
            authorization-uri: https://op.example.test/oauth2/authorize
            token-uri: https://op.example.test/oauth2/token
            jwk-set-uri: https://op.example.test/oauth2/keys
            user-info-uri: https://op.example.test/oauth2/userinfo
            user-name-attribute: sub
```

Endpoints must come from **trusted provider documentation/registration** and align issuer/JWK/signing algorithms with the actual ID Token. Do not treat an OAuth2 provider that has `/userinfo` as an OIDC provider if it does not issue and verify standard ID Tokens.

A misconfigured UserInfo endpoint can cause login failures or return data from the wrong system. For OIDC providers with accurate discovery, `issuer-uri` remains the easier-to-maintain configuration.

## 11. Customizing `OidcUserService` via `userInfoEndpoint`

Many applications only need the default behavior. When additional logic is required for the user principal — such as mapping roles from a business system or controlling exposed fields — Spring Security allows supplying a custom `OAuth2UserService<OidcUserRequest, OidcUser>`.

Servlet configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OAuth2UserService<OidcUserRequest, OidcUser> customOidcUserService)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(oauth2 -> oauth2
                .userInfoEndpoint(userInfo -> userInfo
                    .oidcUserService(customOidcUserService)
                )
            );

        return http.build();
    }
}
```

In Java code, the `OAuth2UserService` interface lives in package `org.springframework.security.oauth2.client.userinfo`. Even though the DSL method name contains `userInfoEndpoint`, the custom service still sits in the **OIDC user principal** processing flow, not an HTTP controller.

### 11.1. Do Not Replace the Entire Flow When You Only Need Small Additions

The right approach is to **delegate default OIDC processing** to an `OidcUserService`, then modify only what is needed.

The example below adds authorities from a **trusted internal permission source**. The lookup API is an application-defined abstraction, not a built-in Spring Security feature.

```java
import java.util.HashSet;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public final class EnrichingOidcUserService
        implements OAuth2UserService<OidcUserRequest, OidcUser> {

    private final OidcUserService delegate = new OidcUserService();
    private final InternalEntitlementService entitlements;

    public EnrichingOidcUserService(InternalEntitlementService entitlements) {
        this.entitlements = entitlements;
    }

    @Override
    public OidcUser loadUser(OidcUserRequest request) {
        // Preserve Spring Security's OIDC/UserInfo mechanics, including sub checking.
        OidcUser original = delegate.loadUser(request);

        String issuer = original.getIdToken().getIssuer().toString();
        String subject = original.getSubject();

        Set<GrantedAuthority> authorities =
            new HashSet<>(original.getAuthorities());

        // Internal entitlement source must be independently authenticated and governed.
        if (entitlements.isApplicationAdmin(issuer, subject)) {
            authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
        }

        if (original.getUserInfo() == null) {
            return new DefaultOidcUser(authorities, original.getIdToken());
        }

        return new DefaultOidcUser(
            authorities,
            original.getIdToken(),
            original.getUserInfo()
        );
    }

    public interface InternalEntitlementService {
        boolean isApplicationAdmin(String issuer, String subject);
    }
}
```

Bean registration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

@Bean
OAuth2UserService<OidcUserRequest, OidcUser> customOidcUserService(
        EnrichingOidcUserService.InternalEntitlementService entitlements) {
    return new EnrichingOidcUserService(entitlements);
}
```

Condition for the example to work: the project must have a real `InternalEntitlementService` implementation, such as a service querying the application's membership/role table with proper authentication and authorization. Do not infer `ROLE_ADMIN` merely because UserInfo has a company email domain or an arbitrary claim editable by the user.

### 11.2. Why Keep the Delegate?

The default `OidcUserService` handles critical OIDC UserInfo responsibilities, including data-loading logic and subject consistency checks. When custom code only needs to assign roles, delegating prevents accidentally dropping security behaviors.

If you replace it with a custom implementation that calls `/userinfo` manually and constructs `OidcUser` from scratch, developers must handle many additional concerns: HTTP errors, token types, claim types, subject matching, security exceptions, and version compatibility. Do not do that just to add an internal role.

### 11.3. Do Not Mix Claims from Untrusted Sources into Authorities

Dangerous example:

```java
// BAD PRACTICE: using email/profile claim as proof of admin privilege.
if (user.getClaimAsString("email").endsWith("@company.test")) {
    authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
}
```

Email may be missing, unverified, changed, or the provider may not enforce the organizational policy the application assumes. Even `email_verified=true` does not prove employee status or administrative privileges. Use a managed permission system keyed by the stable `(iss, sub)` identity.

## 12. Customizing the UserInfo Call Step for Special Providers

`OidcUserService` can delegate UserInfo loading to an internal `OAuth2UserService<OAuth2UserRequest, OAuth2User>`. In supported Spring Security versions, you can replace this component via `setOauth2UserService(...)` when you need custom HTTP client settings or controlled data normalization from a valid provider.

Example of configuring a default delegate for OIDC:

```java
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.DefaultOAuth2UserService;

OidcUserService service = new OidcUserService();

DefaultOAuth2UserService userInfoLoader =
    new DefaultOAuth2UserService();

service.setOauth2UserService(userInfoLoader);
```

This example only illustrates the **extension point**; without actual customizations, creating a new `DefaultOAuth2UserService` like this provides no meaningful benefit.

Customization needs may include:

- Limiting connection timeouts to the UserInfo Endpoint in infrastructure with specific SLO requirements.
- Supporting an HTTP response format supported by the provider that requires controlled conversion.
- Applying telemetry that logs metadata only, without logging tokens or PII.
- Handling a specialized endpoint published by the provider.

**Do not** use a custom loader to turn a UserInfo response with a mismatched `sub` into a valid one. Subject comparison must still be properly enforced. If a provider returns non-OIDC-compliant data, resolve the integration issue with the provider rather than removing security safeguards.

### 12.1. UserInfo Does Not Always Need to Be Loaded

Some Spring Security versions allow configuring the condition deciding when UserInfo is loaded or which scopes are considered eligible. **Method names and default behavior vary across version branches**, so before using customization APIs such as a UserInfo retrieval policy, check the Javadoc for the **exact Spring Security version** in use.

If the provider has no UserInfo Endpoint while still issuing a valid ID Token, do not try to fabricate a dummy UserInfo URI to fetch additional claims. If the application truly needs profile data, determine the proper OP/API mechanism and token permissions required.

### 12.2. Bounding UserInfo Call Duration

The UserInfo HTTP request occurs during login. If the endpoint is slow or unresponsive, users may experience slow or failing logins even though the Token Endpoint already returned tokens.

Therefore, in production systems, consider:

- Appropriate connect and read timeouts.
- Bounded retries, and only when safe.
- Circuit breaker/telemetry where appropriate.
- Distinguishing transient 5xx errors from authentication errors 401/403.
- A policy that allows login via ID Token when UserInfo is not essential, designed explicitly.
- Never swallowing `sub` mismatch errors or ID Token verification failures to "preserve user experience".

Do not retry UserInfo requests indefinitely when the token lacks permission or the provider rejects them. Also do not automatically skip UserInfo during login when its claims are required for critical application decisions.

## 13. Mapping Claims and Permissions: Separating Authentication from Authorization

After the service returns `OidcUser`, Spring can create authorities such as `OidcUserAuthority` and scope authorities consistent with OAuth2 Login mechanics. However, **OIDC `profile`, `email`, `address`, and `phone` do not automatically grant business permissions**.

Keep three layers separate:

| Layer | Input | Permitted Conclusion |
|---|---|---|
| **Authentication** | Verified ID Token | An authenticated principal `(iss, sub)` according to the OP |
| **Profile** | ID Token/UserInfo claims | Profile data shared by the OP |
| **Authorization** | Roles/permissions governed by application policy | Whether the user is allowed to perform action `X` |

Example:

```text
ID Token: sub = user-782
UserInfo: email = lan@example.test, email_verified = true
Application database:
  (iss, sub) -> accountId = 1001
  accountId 1001 -> roles = [READER]
```

The application can display the email from UserInfo and grant only `READER` based on the database. Never grant `ADMIN` based solely on email.

### 13.1. Can Provider-Specific Custom Claims Be Used?

Yes, if the provider contract and trust level permit it. Some enterprise IdPs include `groups`, `roles`, or `department` claims in tokens or UserInfo. However, you must verify:

- Which issuer issued the claim?
- Was the claim taken from a verified ID Token or a subject-checked UserInfo response?
- Which provider is authorized to assert this value?
- Is the mechanism for updating or revoking permissions timely enough?
- Are tenant and application client mappings accurate?
- Do the claim values align accurately with the application's business permissions?

A String claim containing `"admin"` should not automatically become `ROLE_ADMIN` without a governed authorization contract and controlled mapping.

## 14. UserInfo in Multi-Provider Applications

An application might support Google OIDC, Keycloak OIDC, and GitHub OAuth2 Login:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          google:
            client-id: ${GOOGLE_CLIENT_ID}
            client-secret: ${GOOGLE_CLIENT_SECRET}
            scope: [openid, profile, email]

          company:
            provider: keycloak-company
            client-id: ${COMPANY_CLIENT_ID}
            client-secret: ${COMPANY_CLIENT_SECRET}
            scope: [openid, profile, email]

          github:
            client-id: ${GITHUB_CLIENT_ID}
            client-secret: ${GITHUB_CLIENT_SECRET}
            scope: [read:user, user:email]

        provider:
          keycloak-company:
            issuer-uri: https://id.example.test/realms/company
```

In this example:

- Google/Keycloak with `openid` follow OIDC, producing an `OidcUser` and passing through `OidcUserService`.
- A standard GitHub OAuth App uses OAuth2 login, so the principal may be `OAuth2User` rather than `OidcUser`.
- The UserInfo address, claim names, and access policies differ for each provider.
- Do not cast every `Authentication#getPrincipal()` to `OidcUser` when the application also supports non-OIDC OAuth2.

### 14.1. Distinguishing Principals by Type and Registration ID

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.OAuth2User;

void describe(Authentication authentication) {
    if (!(authentication instanceof OAuth2AuthenticationToken oauth)) {
        return;
    }

    String registrationId = oauth.getAuthorizedClientRegistrationId();
    OAuth2User principal = oauth.getPrincipal();

    if (principal instanceof OidcUser oidc) {
        String issuer = oidc.getIdToken().getIssuer().toString();
        String subject = oidc.getSubject();
        // Use (issuer, subject) as the OIDC identity key.
    } else {
        String providerSpecificId = principal.getName();
        // Map ID according to the trusted provider/registration.
    }
}
```

This is an illustrative method; local variables must not be logged indiscriminately in production. If a non-OIDC OAuth2 account comes from GitHub, use the provider and ID issued by GitHub per its API contract; do not fabricate a fake OIDC issuer just to unify data.

## 15. Claims Can Become Stale: UserInfo Does Not Continuously Sync Automatically

`OidcUserService` is normally invoked during **login** or OAuth2/OIDC authentication flows triggered by Spring. Once the HTTP session is established, the principal may live in the session. That means:

- A user changes their name on the OP after logging in, while the UI still shows the old name.
- A new email is verified at the IdP, while `OidcUser` in the session still holds the old snapshot.
- An internal role is revoked, while the session still retains authorities assigned at login if the application lacks a refresh strategy.
- The access token may expire while the HTTP session remains active; the two have different lifecycles.

### 15.1. What Should You Do If Fresh Profile Data Is Needed?

Depending on requirements:

1. **Display-only data:** can be refreshed on re-login or according to a profile TTL defined by the application.
2. **Data requiring periodic sync:** use an authorized backend mechanism, appropriate APIs, and secure access/refresh token management.
3. **Sensitive permissions:** check against the trusted permission source at action time rather than relying solely on a role snapshot in the session.
4. **Business personal data:** define which system is the source of truth; do not equate UserInfo profile data with shipping/billing profiles.

Do not call UserInfo on every request by default: it increases latency, rate-limit pressure, failure risk, and cost. If you need to refresh tokens to call UserInfo after login, use the appropriate `OAuth2AuthorizedClient`/`OAuth2AuthorizedClientManager` infrastructure.

### 15.2. UserInfo and `OAuth2AuthorizedClient` Are Two Different Things

`OAuth2AuthorizedClient` stores the association between a ClientRegistration and the issued access token and optional refresh token. `OidcUser` holds the authenticated user's information. Both are involved in login, but they are not the same:

```text
OAuth2AuthorizedClient
  -> registration
  -> access token
  -> refresh token (if issued)

OidcUser
  -> ID Token
  -> UserInfo (if loaded)
  -> claims / authorities / subject
```

Refreshing an access token via `OAuth2AuthorizedClientManager` **does not automatically update every claim** in the `OidcUser` stored in the HTTP session. If the application wants to update the principal, build an explicit strategy rather than refreshing tokens and assuming the profile updates automatically.

## 16. Common UserInfo Errors and How to Narrow Them Down

| Symptom | Possible Cause | Diagnostic Step |
|---|---|---|
| OIDC login succeeds but `getUserInfo() == null` | Endpoint not published, or service did not call it per scope/policy | Check discovery metadata, granted scopes, `OidcUserService` version |
| `openid` present but `email` missing | `email` not requested, IdP does not release it, or email is in uncalled UserInfo | Check scopes, ID Token, and UserInfo separately |
| UserInfo returns `401 Unauthorized` | Invalid access token, wrong audience/token type, or provider disallows UserInfo | Check Token Endpoint, UserInfo URI, token used, and permissions |
| UserInfo returns `403 Forbidden` | Token lacks scope/permission or IdP policy denies access | Check granted permissions and consent configuration |
| UserInfo reports `sub` mismatch | UserInfo and ID Token belong to different subjects, wrong tenant/endpoint, or provider bug | **Do not use the data**; check issuer, endpoint, token, and Client configuration |
| UserInfo returns HTML/XML instead of JSON | Wrong URL or provider returned an error/proxy page | Check Content-Type, endpoint, and HTTP error |
| Slow UserInfo slows down login | Slow network endpoint, unsuitable timeouts, excessive retries | Set timeouts, observe latency, check availability |
| `OidcUser` has `name` while `getUserInfo()` is null | Name may come from the ID Token | Check ID Token and UserInfo sources separately instead of guessing |
| `email_verified` parsed as String | Provider returned wrong type or custom mapper coerced it | Verify Boolean type and mapping policy |
| `address` coerced to String | Standard claim is an object | Handle map/structured claims |
| Google login works while GitHub `OidcUser` cast fails | GitHub OAuth App does not use an OIDC principal | Handle by `OAuth2User`/`OidcUser` type |
| Custom service drops authorities/scopes | Created a new `DefaultOidcUser` without retaining original authorities | Delegate and preserve `getAuthorities()` |
| Login fails after customizing user loader | Custom HTTP/claim mapping skipped checks or changed endpoint incorrectly | Inspect delegate configuration and exact error |
| Email/role does not update while session is active | `OidcUser` is a login-time snapshot | Design separate profile sync and authorization checks |
| Business API returns 401 after login | Access token expired or wrong resource | Distinguish refreshing access tokens from loading UserInfo |

### 16.1. Sensible Troubleshooting Order

1. **Confirm whether OIDC Login succeeded.** If the ID Token fails signature/issuer/audience/nonce validation, UserInfo is not the primary problem.
2. **Verify ClientRegistration.** Are `registrationId`, issuer, and provider metadata correct?
3. **Check the UserInfo Endpoint.** Does metadata contain `userinfo_endpoint`, and are the host and URL correct?
4. **Check granted scopes.** Do not look only at scopes configured in YAML.
5. **Determine whether UserInfo was called.** Observe HTTP status/latency safely without logging tokens.
6. **If called, inspect the response.** Content-Type, HTTP status, JSON structure, `sub` claim.
7. **Compare `sub` with the ID Token.** On mismatch, stop using the response and fix the root cause.
8. **Check whether the application reads claims from the right source/type.** `email_verified` Boolean, `address` object, `getUserInfo()` may be null.
9. **If claims are used for permissions, verify the authoritative source.** Do not confuse profile attributes with authorization.

### 16.2. Debugging Without Exposing Sensitive Data

In development environments, Spring Security logging can be enabled at an appropriate level:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
```

Diagnostic fields that are useful without recording full tokens:

```text
registrationId=company
userinfoEndpointConfigured=true
userinfoRequestAttempted=true
userinfoHttpStatus=200
userinfoSubMatchesIdToken=true
userinfoContainsEmail=true
```

Do not log `Authorization: Bearer <token>`, raw ID Tokens, refresh tokens, full UserInfo JSON, session cookies, emails, phone numbers, or addresses. If you need to share examples with a support team, synthesize dummy data and redact all credentials.

## 17. Security and Privacy When Loading Profiles

### 17.1. Data Minimization Principle

Ask before requesting scopes: which feature actually needs that claim?

- A welcome page may only need `name` or `preferred_username`.
- Sending email notifications requires `email` and possibly `email_verified` status.
- Shipping may need an address, though a UserInfo address is not necessarily a confirmed shipping address.
- Phone numbers can be sensitive PII; do not request them without a clear purpose.

Do not automatically dump `user.getClaims()` into frontend responses; extract only the fields needed by the UI or business logic per policy.

### 17.2. Protecting the UserInfo Endpoint and Access Token

UserInfo must be called over HTTPS and directed to a provider endpoint configured/discovered from a trusted source.

- Do not allow users to supply an arbitrary UserInfo URL for the backend to call (SSRF risk).
- Do not send the access token to endpoints outside the provider allowlist.
- Do not put the access token in URL query parameters.
- Do not copy tokens into logs or observability systems.
- When using a custom loader, preserve subject verification and proper error handling.
- Do not arbitrarily accept UserInfo data from a different issuer or tenant.

### 17.3. Verifying Email and Phone Number

Claims `email_verified=true` or `phone_number_verified=true` are assertions from the provider that they performed verification according to their own process. They do not themselves prove:

- The user is an active employee at an organization.
- The email address/phone number cannot change.
- The user completed MFA in the current login session.
- The user is authorized to view data or perform administrative actions.

If the application uses these claims as business conditions, explicitly define the trust level and make authorization decisions separately.

## 18. Practice Exercises

### Exercise 1: Is UserInfo Loaded When Only `openid` Is Configured?

Configuration:

```yaml
scope: [openid]
```

After login, `OidcUser#getUserInfo()` returns `null`.

**Question:** Can you conclude that OIDC Login failed?

**Suggested answer:** No. The ID Token may already have been verified and the principal created; the service does not necessarily call UserInfo under this configuration. If a profile is needed, check scopes, provider metadata, and the retrieval policy of your Spring Security version.

### Exercise 2: Email Missing from the ID Token

The ID Token contains only `iss`, `sub`, `aud`, `exp`, `iat`. UserInfo contains `email` and `email_verified`.

**Question:** Where should email be read from?

**Suggested answer:** After Spring Security completes OIDC Login and verifies UserInfo against the subject, the application can read `OidcUser#getClaimAsString("email")` or `getUserInfo()` if it needs source specificity. Do not conclude that missing email in the ID Token is an authentication error.

### Exercise 3: `sub` Mismatch

```text
ID Token: sub = u-100
UserInfo: sub = u-200
```

**Answer:** Do not use UserInfo. Do not force `sub` to `u-100`, and do not take email from this response. Inspect the access token, UserInfo Endpoint, tenant, and provider errors.

### Exercise 4: Provider Returns a Phone Number Without Verification Status

UserInfo:

```json
{
  "sub": "u-100",
  "phone_number": "+84901234567"
}
```

**Answer:** Do not assume the number is verified. If a feature requires a verified phone number, check `phone_number_verified` as a Boolean and handle the missing-claim case.

### Exercise 5: Customizing Permissions from an Internal Source

An application wants to assign `ROLE_ADMIN` to internal accounts, while login emails can change.

**Suggested answer:** Use `(iss, sub)` to link to the internal account and query roles from a trusted permission system. A custom `OidcUserService` can delegate to preserve the UserInfo flow and then add `GrantedAuthority` from internal permissions, instead of mapping roles by email.

### Exercise 6: UserInfo Does Not Update After Profile Change

A user updates their picture on the OP while the application session is still active.

**Suggested answer:** `OidcUser` may hold a snapshot from login time. The application needs an explicit update strategy (re-login, profile refresh by TTL, or an appropriate API). Refreshing the access token does not automatically refresh all claims on the principal.

### Exercise 7: Diagnosing Login Latency

The Token Endpoint responds quickly, while total login time increases by 4 seconds. Observations show the UserInfo Endpoint consistently takes 3.8 seconds.

**Suggested answer:** Measure latency at the UserInfo step, inspect timeouts/availability, required scopes, and whether the data can come from the ID Token per policy. Do not disable `sub` checking or ID Token verification to save time.

## 19. Key Takeaways

| Point to Remember | Practical Meaning |
|---|---|
| `OidcUserService` handles the OIDC user principal | It runs after receiving and verifying the ID Token in OAuth2 Login |
| `OidcUserRequest` contains ID Token and access token | Access token can call UserInfo; ID Token establishes identity |
| UserInfo is not always required | Endpoint/scopes/policy may cause the service not to call UserInfo |
| `sub` must match exactly | Never use UserInfo when its subject differs from the ID Token |
| `OidcUser#getUserInfo()` can be null | Always handle missing UserInfo |
| `getClaims()` may combine multiple sources | Use `getIdToken()`/`getUserInfo()` when you need the exact source |
| `OAuth2User` differs from `OidcUser` | Non-OIDC OAuth2 login does not default to having an ID Token |
| Profile claims differ from business authorities | Email or `profile` does not automatically grant `ROLE_ADMIN` |
| Customizations should keep the delegate | Preserve Spring's UserInfo invocation and OIDC checks |
| UserInfo is usually a login-time snapshot | Profiles do not automatically sync throughout the HTTP session |
| Access tokens/responses contain sensitive data | Never log tokens or dump all claims to the frontend |
| OIDC discovery reduces manual configuration | Use the proper `issuer-uri`/metadata of a trusted provider |

## 20. References

1. [OpenID Connect Core 1.0 — UserInfo Endpoint](https://openid.net/specs/openid-connect-core-1_0.html#UserInfo): endpoint purpose, bearer access token, claims, and `sub` requirement.
2. [OpenID Connect Core 1.0 — UserInfo Response](https://openid.net/specs/openid-connect-core-1_0.html#UserInfoResponse): response model and subject comparison against the ID Token.
3. [OpenID Connect Core 1.0 — Standard Claims](https://openid.net/specs/openid-connect-core-1_0.html#StandardClaims): `profile`, `email`, `address`, `phone`, and standard claims.
4. [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer metadata and `userinfo_endpoint`.
5. [Spring Security Reference — OAuth2 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): OAuth2/OIDC Login flow, `ClientRegistration`, and `OidcUser`.
6. [Spring Security Reference — Advanced OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): customizing user services via `userInfoEndpoint`.
7. [Spring Security API — OidcUserService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/userinfo/OidcUserService.html): `loadUser` contract and OIDC UserInfo extension points.
8. [Spring Security API — OidcUserRequest](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/userinfo/OidcUserRequest.html): ID Token, access token, and ClientRegistration.
9. [Spring Security API — OidcUser](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUser.html): accessing claims, ID Token, and UserInfo.
10. [Spring Security API — DefaultOidcUser](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/DefaultOidcUser.html): default OIDC principal.
11. [Spring Security API — DefaultOAuth2UserService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/userinfo/DefaultOAuth2UserService.html): component that fetches user data from the UserInfo endpoint.

**Summary:** `OidcUserService` bridges verified OIDC login with fetching profile details through UserInfo. The ID Token tells you which subject logged in, while UserInfo supplies shared profile claims when appropriate permissions and endpoints exist. Applications should preserve `sub` matching, handle absent UserInfo safely, use `(iss, sub)` for identity linking, and extend the service only when genuinely needed — never trading OIDC security for convenience when reading profiles.
