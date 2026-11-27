# 3.10. Authentication Information in the ID Token and Profile Information from UserInfo

## Lesson Objectives

After this lesson, you will be able to:

- Distinguish **authentication information** that OpenID Connect (OIDC) places in the **ID Token** from **profile information** that an application can retrieve from the **UserInfo Endpoint**.
- Read key ID Token claims such as `iss`, `sub`, `aud`, `exp`, `iat`, `auth_time`, `nonce`, `acr`, `amr`, and `azp`, and understand when they appear.
- Explain why decoding a JWT payload is insufficient to trust an ID Token, and what an OIDC Client must validate before establishing a login session.
- Use an access token properly to call UserInfo, compare `sub` between UserInfo and the ID Token, and handle missing or changed claims.
- Determine whether data originated from the ID Token or UserInfo in Spring Security via `OidcUser`, `OidcIdToken`, `OidcUserInfo`, and `oauth2Login()`.
- Design identity mapping, privacy policies, and application authorization safely.

## 1. Context: Two Information Sources with Two Different Jobs

Suppose **Learning Portal** is a Spring Boot application allowing students to log in through **Campus Identity**. Campus Identity is the OpenID Provider (OP), while Learning Portal is the Relying Party (RP)—the application relying on the authentication result issued by the OP.

After a user logs in via the OIDC Authorization Code Flow, Learning Portal may receive:

1. **ID Token:** structured proof issued by the OP **for the Client/Relying Party itself**, indicating the user authentication event and subject identifier.
2. **Access Token:** a credential authorizing the client to access appropriate resources; in some cases used to query the **UserInfo Endpoint**.
3. **UserInfo response:** profile claims about the user that the OP permits returning, such as display name, email, language, and avatar.

These three objects must not be treated as three names for the same token or the same JSON.

| Object | Primary Purpose | Intended Recipient | Question It Helps Answer |
| --- | --- | --- | --- |
| **ID Token** | Authenticate the login event and End-User identity per OIDC | OIDC Client / RP designated by `aud` | "Which subject did the OP authenticate, for which client, when, and in what context?" |
| **Access Token** | Authorize access to resources | Target Resource Server or UserInfo Endpoint | "Is the client authorized to call this protected endpoint?" |
| **UserInfo response** | Provide End-User profile claims | OIDC Client calling UserInfo with an access token | "What name, email, or profile details does the OP permit sharing?" |

**Key principle:** the ID Token serves the Relying Party to understand the authentication outcome; UserInfo is a source of profile claims; the Access Token is a credential authorizing access. Never send an ID Token in place of an access token when calling business APIs.

### 1.1. Overall Flow

```mermaid
sequenceDiagram
    autonumber
    actor U as End-User
    participant C as Learning Portal (OIDC Client)
    participant OP as Campus Identity (OpenID Provider)
    participant UI as UserInfo Endpoint

    U->>C: Start login
    C-->>U: Redirect to OP with openid, scope, state, nonce
    U->>OP: Authenticate / consent if needed
    OP-->>C: Callback with authorization code
    C->>OP: Exchange code at token endpoint
    OP-->>C: ID Token + Access Token (and other tokens if issued)
    C->>C: Validate ID Token, correlate transaction with state/nonce
    opt Profile claims needed; provider supports UserInfo
        C->>UI: GET /userinfo, Bearer Access Token
        UI-->>C: Claims containing sub and permitted claims
        C->>C: Compare UserInfo sub against ID Token
    end
    C->>C: Establish principal / login session
    C-->>U: Application UI
```

In real deployments, the UserInfo Endpoint is usually an endpoint belonging to the same OP; the diagram separates it to clarify its function. Having an ID Token does not mean UserInfo must always be called: the client calls it only when needed and permitted by configuration, token, scopes, and provider.

## 2. What Is an ID Token?

According to OIDC, an **ID Token** is a token containing claims about the authentication of an End-User by an OpenID Provider, and may contain other claims. This token is typically in **JSON Web Token (JWT)** format, signed with JWS, or additionally protected with JWE encryption when configured.

An ID Token typically has three JWT segments:

```text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
```

The string above illustrates a three-part signed JWT (JWS). Reading the payload after Base64URL-decoding only lets you **inspect the contents**; to **trust** the contents, the OIDC Client must validate the token according to protocol rules.

Example decoded **header** (values are illustrative only):

```json
{
  "alg": "RS256",
  "kid": "campus-key-01",
  "typ": "JWT"
}
```

Example decoded **payload**:

```json
{
  "iss": "https://login.example.org",
  "sub": "student-8fa3b7",
  "aud": "learning-portal",
  "exp": 1893456300,
  "iat": 1893456000,
  "auth_time": 1893455900,
  "nonce": "n-7fb32acb",
  "acr": "urn:example:assurance:mfa",
  "amr": ["pwd", "otp"]
}
```

This is **not a valid token** for actual use; no signature is provided and timestamps, key, and subject are hypothetical. Never store real secrets, ID Tokens, or production values in documentation or logs for examples.

### 2.1. Core Claims of an ID Token

| Claim | Meaning | What to Watch When Interpreting |
| --- | --- | --- |
| `iss` (*issuer*) | Identifier of the OP issuing the ID Token, typically an HTTPS URL | Must match the issuer configured and trusted by the Client |
| `sub` (*subject*) | End-User identifier supplied by the issuer | Never assume it is an email, username, or ID shared across OPs |
| `aud` (*audience*) | Client ID or set of Client IDs the token is intended for | Must contain the current application's Client ID; may be a string or an array |
| `exp` (*expiration time*) | Timestamp when the token expires, in Unix time | Client must reject expired tokens, accounting for reasonable clock skew |
| `iat` (*issued at*) | Time when the ID Token was issued | Does not equal when the user entered a password or completed MFA |

The five claims above play the central role in an OIDC ID Token. The optional claims below can be very important under specific authentication policies.

| Claim | Usage Scenario | Proper Interpretation |
| --- | --- | --- |
| `auth_time` | Need to know when the OP authenticated the user; especially when using `max_age` | Authentication timestamp, not token issuance date |
| `nonce` | Client sent a nonce in the authentication request to bind the ID Token to the transaction | If the client sent a nonce, the returned nonce must match the stored value |
| `acr` | Requests/records authentication context class or assurance level | Exact meaning depends on policy and agreement with the OP |
| `amr` | Records authentication methods applied | E.g. `pwd`, `otp`; do not infer "MFA completed" just from familiar strings |
| `azp` (*authorized party*) | Supplementally identifies the authorized party, especially when the token has multiple audiences | Apply `azp` validation rules when issuance conditions require it |
| `at_hash` | Links the ID Token to the Access Token in responses/flows that include this claim | Not present in every ID Token of the Authorization Code Flow |
| `c_hash` | Links the ID Token to the authorization code in applicable flows/responses | Not a default claim of every Authorization Code Flow |
| `sid` | Some OPs support session management and logout based on a session ID | Not synonymous with the Spring application's session cookie |
| `jti` | A JWT identifier that may be issued by the provider | Not a mandatory ID Token claim under OIDC Core |

**`iss` + `sub` is typically the identifier pair linking a local account to an OIDC identity.** Two different OPs can both return `sub = "123"` for two different people. An OP can also issue *pairwise subject identifiers* so the same user receives different `sub` values across different client groups. Therefore, never use `sub` alone as a global key across multiple issuers.

### 2.2. How Does `auth_time` Differ from `iat`?

Suppose a user completed SSO login at 09:00, opened Learning Portal at 09:20, and the OP issued an ID Token at 09:20:

```text
auth_time = 09:00   // when the OP authenticated the user
iat       = 09:20   // when the OP issued the ID Token for Learning Portal
```

If the Portal requires sufficiently recent authentication to access a sensitive feature, it can send the OIDC `max_age` parameter. Then `auth_time` must be checked per OIDC rules to confirm the OP authenticated the user within the permitted window. The fact that an ID Token was just issued **does not guarantee** the user just entered a password or completed MFA.

In some cases, the client requests `acr_values` or a specific `acr` claim to obtain an appropriate authentication assurance level. However, the client and OP must agree on the meaning of `acr` values and how unmet requests are handled. Never hardcode an assumption like "any `acr` value containing `mfa` carries the same assurance" without a trust contract.

### 2.3. Does `amr` Always Prove MFA?

`amr` is typically an array of authentication methods used by the OP, for example:

```json
{
  "amr": ["pwd", "otp"]
}
```

It can be helpful for auditing or policy-driven access conditions, yet its representation and assurance level depend on the OP. If a business process needs stepped-up authentication, use a clearly defined policy covering trusted issuer, agreed `acr` or `amr` rules, `auth_time`, and other contextual details. Never check only for the mere existence of an `amr` claim.

### 2.4. Can Profile Information Appear in the ID Token?

**Yes.** In addition to authentication claims, an ID Token may carry standard or provider-specific claims issued by the OP, such as `name` or `email`. A claim appearing in the ID Token does not make it a mandatory OIDC requirement for all clients.

Never assume that:

- The ID Token always contains `email`, `name`, `picture`, or `roles`.
- The `email` field is an immutable identifier key.
- Having `email` means the email is verified; inspect `email_verified` when policy requires it while keeping the OP's semantics in mind.
- Having `groups`, `roles`, or `permissions` means the application was granted API permissions. Those claims may be custom extensions requiring mapping and policy verification.

## 3. Validating the ID Token Before Trusting Identity

A client must never trust a payload merely because a JWT decodes to JSON. Before creating an `Authentication`/session from an ID Token, apply the appropriate OIDC checks.

### 3.1. Identifying the Right Issuer and Signing Key

The client identifies the configured OP, typically via OIDC Discovery:

```http
GET /.well-known/openid-configuration HTTP/1.1
Host: login.example.org
```

The OP's metadata can advertise `issuer`, `authorization_endpoint`, `token_endpoint`, `userinfo_endpoint`, `jwks_uri`, and other capabilities. For asymmetrically signed ID Tokens, the client fetches trusted verification keys from the JWKS corresponding to the issuer. `kid` is a hint to select a key, **not a trust source on its own**.

Restrict algorithms to those agreed upon by the client and OP. Never accept an arbitrary algorithm solely because the JWT header declares it, nor trust keys fetched from arbitrary URLs supplied inside an untrusted payload/header. For encrypted ID Tokens, the client must also decrypt per configuration and verify the corresponding protection layers.

### 3.2. Verifying the ID Token Belongs to the Right Client

`aud` must contain the Client ID registered by the application with the OP. If the token has multiple audiences or `azp` is present, execute OIDC's `azp` validation rules.

For example, Learning Portal has `client_id = learning-portal`, yet the token contains:

```json
{
  "iss": "https://login.example.org",
  "sub": "student-8fa3b7",
  "aud": "another-application"
}
```

Even if the token was issued by a trusted issuer with a valid signature, it **must not be used** as an authenticating ID Token for Learning Portal because the audience is wrong.

### 3.3. Checking Timestamps and Request Correlation

The OIDC Client needs to verify:

1. The token is still valid per `exp` and its timestamps satisfy policy.
2. `iat` complies with validation rules, including token freshness if enforced by the client.
3. If the request sent a `nonce`, the ID Token contains a nonce matching the value stored by the client for that authorization session.
4. If `max_age` was requested, check `auth_time`; when a specific assurance level is required, check `acr` per agreement.
5. For flows/responses involving `at_hash` or `c_hash`, apply the corresponding binding checks.

Beyond the ID Token, the client must also verify **`state` on the authorization response** to bind the callback to the initiated request. `state` lives at the OAuth authorization response layer; it is not a mandatory ID Token claim.

### 3.4. Why Not Manually `Base64.decode()` and Log In?

Example that is wrong in principle:

```java
// DO NOT DO THIS: decoding the payload without validating the token.
String[] parts = idTokenString.split("\\.");
String json = new String(
    Base64.getUrlDecoder().decode(parts[1]),
    StandardCharsets.UTF_8
);
// Wrong to read "sub" directly from json and create a login session.
```

Anyone can craft a JWT string that looks valid as JSON. A dedicated OIDC library must verify the signature/issuer, audience, and related constraints before trusting claims. Spring Security handles OIDC validation inside `oauth2Login()` when properly configured; there is no need to write custom JWT decoding for login.

## 4. What Is the UserInfo Endpoint?

The **UserInfo Endpoint** is an OAuth 2.0 protected resource defined by OIDC that returns claims about the authenticated End-User. The client calls this endpoint with an appropriate **access token** issued by the OP over a direct HTTPS connection.

Example:

```http
GET /userinfo HTTP/1.1
Host: login.example.org
Authorization: Bearer <access-token>
Accept: application/json
```

Illustrative JSON response:

```json
{
  "sub": "student-8fa3b7",
  "name": "Nguyen Anh",
  "given_name": "Anh",
  "family_name": "Nguyen",
  "preferred_username": "anh.nguyen",
  "email": "anh@example.org",
  "email_verified": true,
  "picture": "https://profile.example.org/avatar/8fa3b7",
  "locale": "vi-VN"
}
```

Every field besides `sub` is a **possible example**, not a guarantee. UserInfo may also return a **signed and/or encrypted JWT** if the OP and client are configured for that response format, so not every integration receives plain JSON with the same HTTP content type.

### 4.1. Why Need UserInfo If the ID Token Already Has `sub`?

Because most applications need profile data beyond core authentication info:

- Displaying name and avatar.
- Pre-filling an email shared by the OP.
- Choosing UI language, timezone, or formatting from `locale`.
- Linking the profile from the identity system with business data in the application.

The ID Token should be treated as the authentication result for the client, whereas UserInfo lets the client retrieve profile data when permitted. The OP may place some claims in the ID Token, some in UserInfo, in both, or omit them, depending on scopes, claim requests, consent, and data policies.

### 4.2. Is UserInfo a Place to Validate an Access Token?

**No.** UserInfo is a profile data endpoint, not a token introspection endpoint. It validates the incoming access token internally to decide which profile to return. A client must not call UserInfo as a substitute for ID Token validation, nor use UserInfo to validate JWTs for its own APIs.

**Never send an ID Token to UserInfo** in the Bearer header. An ID Token's audience is the OIDC Client; UserInfo requires an access token with appropriate permissions.

### 4.3. `sub` from UserInfo Must Match the ID Token

This is a foundational security condition:

```text
ID Token.sub   = "student-8fa3b7"
UserInfo.sub   = "student-8fa3b7"
Result         = match, safe to continue processing claims
```

If:

```text
ID Token.sub   = "student-8fa3b7"
UserInfo.sub   = "student-different"
Result         = mismatch, MUST refuse to use the UserInfo response
```

OIDC Core requires the UserInfo response to include `sub` and the client to compare it with the ID Token's `sub`. A discrepancy may indicate token mix-up, session mix-up, misconfiguration, or identity substitution risk. Never "fix" it by overwriting the ID Token–authenticated principal with UserInfo's `sub`.

If the OP returns UserInfo as a signed/encrypted JWT, the client must also process the protection and validation checks applicable to that response type. With JSON responses over HTTPS, access tokens and transport still need protection.

## 5. Common Profile Claims in UserInfo

OIDC Standard Claims support several categories of End-User data. They may appear in UserInfo or be placed in the ID Token by the OP per policy.

| Claim | Meaning | Application Notes |
| --- | --- | --- |
| `sub` | End-User identifier belonging to the OP | Must match ID Token `sub` |
| `name` | Full display name | Unsuitable as an identity key |
| `given_name` | Given / first name | May be absent, depending on culture and profile source |
| `family_name` | Family / last name | Do not impose rigid first/last name formats on all users |
| `middle_name` | Middle name | Optional |
| `nickname` | Nickname | Optional |
| `preferred_username` | Preferred username | May collide, change, or be omitted |
| `profile` | Profile page URL | Handle URL safely when rendering |
| `picture` | Avatar image URL | Data may change; avoid loading from untrusted domains in risky ways |
| `website` | Website URL | Optional |
| `email` | Email address | May change; verify verification status if used in security workflows |
| `email_verified` | OP indicates it verified the email address under its own definition | Boolean field; does not replace current business verification |
| `gender` | Shared gender info | Sensitive data; process only with a clear need |
| `birthdate` | Birthdate in an OIDC-supported format | Sensitive personal data; validate format/accuracy |
| `zoneinfo` | Time zone | Can assist with time display |
| `locale` | User's language/region | E.g. `vi-VN` |
| `phone_number` | Phone number | Never assume it is verified |
| `phone_number_verified` | Phone verification status per OP | May be absent |
| `address` | Structured address object | Personal data; minimize collection |
| `updated_at` | Time profile was updated at source | Does not mean all claims are always fresh when the client reads them |

Complex JSON claims like `address` have their own object structure; never assume every claim is a string. Extended claims such as `department`, `student_code`, `employee_id`, `groups`, or `roles` are **provider conventions**, not part of the core OIDC Standard Claims list.

**A claim missing from the response is not necessarily an error.** It may be restricted by scope, consent, privacy policy, missing user input, or lack of OP support.

## 6. How Do Scopes Affect Claims?

An OIDC request is identified by the **`openid`** scope. Standard scopes commonly request additional information groups:

| Scope | Information Group Typically Requested | What Is Not Guaranteed? |
| --- | --- | --- |
| `openid` | Initiates an OIDC authentication request; receives an ID Token per flow | Does not guarantee email, name, or picture |
| `profile` | Profile claims such as `name`, `family_name`, `given_name`, `preferred_username`, `picture`, `locale`... | Does not guarantee all claims or where they are returned |
| `email` | `email`, `email_verified` | Does not guarantee email is present or verified |
| `address` | `address` claim | Does not guarantee address exists or is shared |
| `phone` | `phone_number`, `phone_number_verified` | Does not guarantee phone number exists or is verified |

An example request:

```text
scope=openid profile email
```

This means the client **requests** OIDC authentication and sharing of profile/email claims subject to policy. The Authorization Server / OpenID Provider may require consent, restrict permissions, strip claims, or withhold specific claims.

OIDC also supports the **`claims`** parameter to request specific claims for `id_token` and/or `userinfo` when supported by the OP. Illustrative JSON example of this parameter:

```json
{
  "id_token": {
    "auth_time": { "essential": true }
  },
  "userinfo": {
    "email": { "essential": true },
    "email_verified": null
  }
}
```

`essential` conveys the claim's importance to the request, yet it is not a license forcing the OP to disclose data outside policy, nor do all OPs support identical handling. The client must determine provider support and how the application handles omitted data.

### 6.1. When to Read Claims from the ID Token vs. Call UserInfo?

A common design approach:

- **Authenticated identity:** use the validated ID Token; key account mapping by issuer and subject.
- **Display data:** prefer profile claims permitted by the provider, potentially from UserInfo when the client needs them.
- **Attributes for sensitive permissions:** source from an authoritative system; never treat profile claims as authorization rules by default.
- **Data freshness:** if name/email can change, define a clear refresh or sync strategy rather than fetching once and keeping forever.

There is no mandatory rule to "always call UserInfo" or "always use only the ID Token" for every application. What matters is preserving **trust provenance, purpose, data permissions, and `sub` consistency**.

## 7. A Complete Example: From ID Token to UserInfo

Suppose Learning Portal has `client_id = learning-portal` and sent scopes `openid profile email`.

### Step 1: Redirect to the OpenID Provider

The client initiates the Authorization Code Flow:

```http
GET /oauth2/authorize?response_type=code
  &client_id=learning-portal
  &redirect_uri=https%3A%2F%2Fportal.example.org%2Flogin%2Foauth2%2Fcode%2Fcampus
  &scope=openid%20profile%20email
  &state=<random-state>
  &nonce=<random-nonce>
  &code_challenge=<pkce-challenge>
  &code_challenge_method=S256 HTTP/1.1
Host: login.example.org
```

This example only illustrates parameters; when building a real request, the URL must be properly encoded and constructed per HTTP standards. `state`, `nonce`, and the PKCE verifier/challenge must be generated per transaction, never using fixed strings.

### Step 2: Receive Tokens from the Token Endpoint

After the client validates `state` and successfully exchanges the authorization code (with PKCE and client authentication when applicable), the OP returns:

```json
{
  "access_token": "access_token_example",
  "token_type": "Bearer",
  "expires_in": 300,
  "id_token": "<signed-id-token>",
  "scope": "openid profile email"
}
```

The response may include a `refresh_token` if policy permits. It is **not mandatory** in every Authorization Code Flow.

### Step 3: Validate the ID Token

The client verifies signature, issuer, audience, timestamps, sent nonce, and any flow-specific conditions; then determines identity:

```text
issuer    = https://login.example.org
subject   = student-8fa3b7
local key = (https://login.example.org, student-8fa3b7)
```

This is the basis for linking the user at the RP. Never use email or display name alone to automatically merge accounts across issuers.

### Step 4: Fetch Profile Data When Needed

The client calls UserInfo using the **access token**:

```http
GET /userinfo HTTP/1.1
Host: login.example.org
Authorization: Bearer <access-token>
```

The OP returns:

```json
{
  "sub": "student-8fa3b7",
  "name": "Nguyen Anh",
  "email": "anh@example.org",
  "email_verified": true,
  "locale": "vi-VN"
}
```

The client checks:

```text
userinfo.sub == id_token.sub
```

When they match, the client can use `name` for display, `locale` for UI selection, and `email` per applicable policy. If UserInfo omits `name`, the application can fall back to an internal identifier or generic greeting.

### Step 5: Establish Principal and Access the Application

Learning Portal establishes the authenticated principal/local session after valid OIDC login. A business endpoint must still enforce its own authorization: even though a user is logged in, they do not automatically gain access to all student records.

## 8. Spring Security: How Are ID Token and UserInfo Represented?

In a Spring Boot application using Spring Security OAuth2/OIDC Client:

- `ClientRegistration` holds client/provider configuration.
- `oauth2Login()` executes the OAuth2 login flow; if scopes include `openid`, Spring Security executes the corresponding OIDC flow.
- `OidcUser` is the authenticated OIDC principal.
- `OidcIdToken` represents the ID Token processed during the OIDC flow.
- `OidcUserInfo` represents claims retrieved from UserInfo, when present.
- `OidcUserService` loads and merges OIDC UserInfo data per Spring Security configuration and conditions.
- `OidcUser.getClaims()` exposes the aggregated claims for the application; if you need the **origin** of a specific claim, inspect `getIdToken().getClaims()` and `getUserInfo().getClaims()` separately.

### 8.1. Configuring an OIDC Client in Spring Boot

Example in `application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          campus:
            provider: campus
            client-id: ${CAMPUS_CLIENT_ID}
            client-secret: ${CAMPUS_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          campus:
            issuer-uri: https://login.example.org
```

This example assumes a backend **confidential client** with its secret stored securely. For public clients such as SPAs or mobile apps, embedded client secrets cannot be protected and configuration must match that client type.

`issuer-uri` allows Spring Security to discover provider metadata if the OP supports OIDC Discovery. The actual issuer, endpoints, client authentication method, redirect URI, and scopes must match registration at the OP.

Example security filter chain:

```java
@Configuration
class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/me").authenticated()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

With this login setup, the OIDC flow can start at:

```text
/oauth2/authorization/campus
```

Default callback for `registrationId`:

```text
/login/oauth2/code/campus
```

These snippets focus on the relevant APIs and configuration, assuming the project has appropriate Spring Boot / Spring Security dependencies and imports.

### 8.2. Reading the OIDC Principal in a Controller

After a successful login, Spring Security can inject the principal:

```java
@RestController
class MyProfileController {

    @GetMapping("/me")
    Map<String, Object> me(@AuthenticationPrincipal OidcUser user) {
        Map<String, Object> response = new LinkedHashMap<>();

        response.put("subject", user.getSubject());
        response.put("name", user.getClaimAsString("name"));
        response.put("email", user.getClaimAsString("email"));
        response.put("emailVerified", user.getClaims().get("email_verified"));
        response.put("hasUserInfo", user.getUserInfo() != null);

        return response;
    }
}
```

This example returns only a few selected fields of the user **to themselves** on a protected endpoint. In a real application, enforce access control, avoid exposing out-of-scope PII, and never include tokens in the response.

Note that `OidcUser.getClaimAsString("name")` may return `null`. If the OP does not provide a name, the UI should have a sensible fallback. Returned claims may be merged from the ID Token and UserInfo; read each source separately if provenance matters.

### 8.3. Clearly Distinguishing Claims from the ID Token vs. UserInfo

Example of a backend-only inspection component that **does not expose all raw claims via an API**:

```java
@Service
class OidcClaimInspector {

    boolean idTokenContainsEmail(OidcUser user) {
        OidcIdToken idToken = user.getIdToken();
        return idToken.getClaims().containsKey("email");
    }

    boolean userInfoContainsEmail(OidcUser user) {
        OidcUserInfo userInfo = user.getUserInfo();
        return userInfo != null
            && userInfo.getClaims().containsKey("email");
    }

    String authenticatedSubject(OidcUser user) {
        return user.getIdToken().getSubject();
    }
}
```

- `user.getIdToken()` holds the ID Token Spring used to construct the principal.
- `user.getUserInfo()` may be `null` if UserInfo was not called or returned no data.
- `user.getClaims()` may reflect merged data. Do not rely on it to assume all claims came from the ID Token.
- `user.getSubject()` is the authenticated subject's OIDC identifier; when UserInfo is used, `sub` must match.

In business logic, if a verified email is required, define explicit rules covering the provider, `email_verified` claim, processing purpose, and missing-claim cases. Never treat a missing email as proof that OIDC login failed.

### 8.4. Does Spring Security Call UserInfo Automatically?

Spring Security includes `OidcUserService`, which can retrieve claims from the UserInfo Endpoint depending on provider capabilities and configured conditions. In typical versions and setups, querying UserInfo depends on `userinfo_endpoint` metadata, the access token, and profile-related scopes such as `profile`, `email`, `address`, or `phone`.

**Never assume every OIDC request calls UserInfo.** An application requesting only `openid`, a provider without a UserInfo endpoint, restricted scopes, or custom policies can result in `OidcUserInfo` being absent. Exact behavior also depends on the Spring Security version and OIDC service configuration. To be certain of claim provenance, verify your specific integration setup and inspect the ID Token / UserInfo objects individually.

You can customize it using this hook:

```java
http.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(userInfo -> userInfo
        .oidcUserService(customOidcUserService)
    )
);
```

Here `customOidcUserService` is an application-provided `OAuth2UserService<OidcUserRequest, OidcUser>`, typically delegating to the standard `OidcUserService` to preserve built-in validation and UserInfo loading before adding domain rules. Never write a custom implementation that calls UserInfo over HTTP on its own while bypassing subject checks, token checks, and the library's built-in security safeguards.

### 8.5. Example Custom OidcUserService When an App Requires a Verified Email

Only enforce this requirement **if product policy genuinely demands a verified email**. Some OPs do not issue `email` or `email_verified`, and logging in with a valid ID Token does not inherently require an email.

```java
@Configuration
class OidcProfilePolicyConfig {

    @Bean
    OAuth2UserService<OidcUserRequest, OidcUser> verifiedEmailOidcService() {
        OidcUserService delegate = new OidcUserService();

        return request -> {
            OidcUser user = delegate.loadUser(request);

            if (!Boolean.TRUE.equals(
                    user.getClaimAsBoolean("email_verified"))) {
                throw new OAuth2AuthenticationException(
                    new OAuth2Error("unverified_email"),
                    "This application requires a verified email"
                );
            }

            return user;
        };
    }
}
```

To use it, wire the bean above into `.userInfoEndpoint(...oidcUserService(...))`. This policy also rejects cases where `email_verified` is absent; that is an **application-specific decision**, not a mandatory OIDC rule. With multiple OPs, evaluate whether each OP's email verification process can be trusted before relying on it in business logic.

Do not write `email`, raw claims, or tokens into error logs just to explain why login was rejected.

## 9. Local Identity Management and Access Control

### 9.1. Identifying Accounts by `(issuer, subject)`

A multi-provider system should store relationships like:

| Local User ID | OIDC Issuer | OIDC Subject |
| --- | --- | --- |
| `user-101` | `https://login.example.org` | `student-8fa3b7` |
| `user-202` | `https://idp.partner.example.org` | `student-8fa3b7` |

The two rows above **do not necessarily represent the same person** because the issuers differ. Never merge automatically simply because `sub`, `email`, or `preferred_username` matches.

A simple application model:

```text
LocalAccount
  id                   // stable internal key
  displayName          // display data, updatable

ExternalIdentity
  localAccountId       // links to LocalAccount
  issuer               // OIDC iss
  subject              // OIDC sub
  linkedAt             // timestamp when linked
```

Enforce an appropriate uniqueness constraint on `(issuer, subject)` and a clear account-linking workflow. With OPs issuing pairwise subject identifiers, a single user may have different `sub` values across different clients; that is normal OIDC behavior, not a bug.

### 9.2. Authentication Does Not Equal Authorization

OIDC verifies that an OP authenticated a subject within the context of an ID Token. It **does not automatically grant** permissions for Learning Portal's business operations.

For example:

- A valid ID Token identifies student `student-8fa3b7`.
- UserInfo supplies the name "Nguyen Anh" and a verified email.
- An `/admin/users` endpoint must still verify administrative roles/permissions from an authoritative source per policy.
- A `/courses/123/grades` endpoint must still check whether the user is allowed to view grades for that specific course/record.

If a provider puts `roles` or `groups` in tokens/UserInfo, design an explicit mapping across issuer, claim, value, and internal permissions. Never blindly treat self-asserted values or profile claims as sufficient authorization.

### 9.3. Using `email_verified` Appropriately

`email_verified: true` means the OP indicates it verified the email address under its own process. It does not mean:

- The email can never change.
- The email belongs exclusively to that person across all systems at all times.
- The user is authorized to access data solely because their email uses the campus domain.
- It is safe to automatically link to an internal account sharing that email without checking for account-takeover risks.

For sensitive actions like account linking, changing recovery addresses, or domain-based access grants, implement explicit business rules, required verification, and auditing.

## 10. Privacy, Freshness, and Handling Missing Data

### 10.1. Data Minimization

Only request scopes and claims needed for features. If the UI only needs a display name, there is no need to request `address`, `phone`, or `birthdate`. Protect personal data everywhere:

- Never log raw ID Tokens, access tokens, or full UserInfo responses in logs, telemetry, or exceptions.
- Send only necessary claims to the browser; the backend can filter/omit sensitive fields.
- Consider encrypted storage, access controls, retention periods, and data deletion workflows.
- Never embed profile/image URLs from untrusted sources in contexts that could cause XSS or uncontrolled resource fetching.
- Separate claims used for display from data used for access control.

### 10.2. Profiles Can Change Between Logins

`name`, `picture`, `email`, `locale`, verification status, and other claims may be updated by the OP. An old ID Token or UserInfo response does not update automatically when the OP edits a profile. If the application needs fresh data, define when to re-query UserInfo, check current permissions, and manage cache expiration.

**Changed claims do not always mean a changed identity.** The `(iss, sub)` pair serves a different identity role than email or name.

### 10.3. What If UserInfo Is Unavailable?

That can be completely normal. The application should:

1. Continue using the validated ID Token to identify the subject when the login flow is valid.
2. Use only the profile claims actually returned by the provider.
3. Provide sensible fallbacks for name/avatar/email and avoid crashing on `null`.
4. If a feature strictly requires an attribute the OP does not return, show guidance or apply a supplemental collection/verification workflow per policy.

Never fabricate fake emails or user IDs and treat them as OP-verified data.

## 11. Common Integration Errors

| Symptom | Possible Cause | How to Handle |
| --- | --- | --- |
| ID Token decodes yet Spring rejects login | Wrong issuer, audience, signature, time, or nonce | Check registration/issuer, public keys, system clock, and OIDC transaction |
| Login succeeds yet `OidcUserInfo == null` | UserInfo was not called, or no endpoint/condition/scope matched | Check metadata, granted scopes, and OIDC User Service configuration |
| UserInfo returns HTTP 401 | Access token expired, wrong token, or rejected by UserInfo | Check access token and ensure the right provider is called |
| ID Token and UserInfo have different `sub` | Session/token mix-up or broken provider implementation | Refuse to use UserInfo; investigate session/client/issuer |
| `name` or `email` is missing | Provider does not supply claim or scope/consent restricted it | Check scopes, consent, provider mapping, and use fallbacks |
| Same email yet two separate accounts | Two distinct issuers/subjects or different mapping history | Design an account-linking flow; never auto-merge |
| User logged in yet API returns 403 | Authentication succeeded, but lacks business permissions or access token lacks required scope | Check API authorization; never try to fix with an ID Token |
| After profile update, UI still shows old name | App caches claims from previous session/login | Define a data-refresh and cache strategy |
| After token refresh, app assumes profile updated | Refreshing an access token does not force re-fetching UserInfo/ID Token or updating profiles | Refresh profile data via a dedicated mechanism when needed |
| Account A sees Account B's data | Keying by name/email instead of subject, or broken ownership check | Fix `(iss, sub)` mapping and per-resource authorization |

### 11.1. Observing Errors Safely

In logs/metrics, prefer storing non-sensitive technical info: registration ID, configured issuer, OIDC error type, HTTP status code, correlation ID, and timestamp. For user-related data, apply minimization and protection policies; never log tokens or full PII-bearing claims.

When debugging claim provenance, inspect `getIdToken()` and `getUserInfo()` with specific claim names locally. Never expose a public endpoint returning the entire ID Token payload or UserInfo response.

## 12. Practical Scenarios

### Scenario A — ID Token Contains No Email

The Portal receives an ID Token with `iss`, `sub`, `aud`, `exp`, `iat`, `nonce`, and no `email`. After calling UserInfo with the access token, the Portal receives `email`, `email_verified`, and `name`.

**How to handle:** Validate the ID Token first, match `userinfo.sub` against `id_token.sub`, and then use `email` for permitted purposes. Do not treat an ID Token lacking `email` as a login error.

### Scenario B — ID Token Has an Email, Yet the User Changed Their Email

The Portal retains an old profile from a prior login, while the OP updated the email at the source. A fresh UserInfo response may reflect the update, depending on the provider and caching.

**How to handle:** use `(iss, sub)` for stable identity; define refresh, notification, and email verification policies if business workflows rely on email. Never create a new account just because an email changed.

### Scenario C — ID Token Has a Fresh `iat` Yet an Old `auth_time`

The user started an SSO session 10 hours ago; the OP just issued a new ID Token now. A sensitive feature requires authentication within the last 5 minutes.

**How to handle:** consider requesting `max_age` or an appropriate authentication context, and check `auth_time` per policy. Never use `iat` alone to infer fresh authentication.

### Scenario D — UserInfo Returns a Different `sub` Than the ID Token

The client validated an ID Token for `student-A`, yet UserInfo returns `student-B`.

**How to handle:** refuse to use the UserInfo response. Investigate accidental reuse of an access token from another session, token store bugs, registration, and provider configuration. Never change the principal to `student-B`.

### Scenario E — Profile Contains Group `ADMIN`

UserInfo also returns `groups: ["ADMIN"]` as an OP-specific extension.

**How to handle:** map it to administrative privileges only if the application has a clear contract with the OP regarding trustworthiness, scope, claim freshness, and access control. OIDC Standard Claims do not automatically turn the string `ADMIN` into a valid privilege.

## 13. Self-Check Questions

**1. Both the ID Token and UserInfo contain `sub`. Must they be compared?**

> Yes. The OIDC Client must verify that `sub` in the UserInfo response matches `sub` in the ID Token; if they differ, the UserInfo response must be rejected.

**2. Can you send the ID Token in `Authorization: Bearer` to the Course API?**

> No. The ID Token is meant for the OIDC Client/RP; the API needs an appropriate access token with the right permissions, audience, and validity.

**3. Why does `iat` not prove the user just completed MFA?**

> `iat` is when the token was issued, not when the user authenticated. Inspect `auth_time` and `acr`/`amr` policies when specific authentication assurance is required.

**4. Does `scope=openid profile email` guarantee UserInfo returns all of `name`, `email`, and `picture`?**

> No. Scopes are requests for groups of information; actual claims depend on the provider, user, consent, and policies. Clients must handle missing data.

**5. In Spring Security, how do you distinguish whether an email came from the ID Token or UserInfo?**

> Check `user.getIdToken().getClaims()` and, if `user.getUserInfo()` is non-null, check `user.getUserInfo().getClaims()`. `user.getClaims()` is an aggregated map and does not show exact provenance.

**6. Two people at two different OPs share `sub = "123"`. Can they be merged into one account?**

> Not based on `sub` alone. Use both issuer and subject, and link accounts only through an explicitly designed workflow.

**7. Why not Base64URL-decode the JWT yourself and grab `sub` to log in?**

> Decoding does not check signature, issuer, audience, expiration, nonce, or OIDC constraints. Use a proper OIDC validation library such as Spring Security's `oauth2Login()` integration.

---

## Takeaways

**The ID Token answers who the OpenID Provider authenticated, for which Relying Party, at what time, and in what context.** Clients must fully validate the ID Token before trusting `iss` and `sub`. **UserInfo returns permitted profile claims**, retrieved with an access token via the UserInfo Endpoint; `sub` from UserInfo must match the ID Token. In Spring Security, `OidcUser` provides separate access to `OidcIdToken` and `OidcUserInfo`, alongside merged claims for the application. Identity linked via `(iss, sub)` should remain separate from mutable profile attributes and business authorization decisions.
