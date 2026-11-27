# Delivering Claims for profile, email, address, and phone Scopes

## 1. From OIDC Scopes to User Information

In OAuth 2.0, `scope` represents the range of permissions a client requests and the Authorization Server may grant. In **OpenID Connect (OIDC)**, the standard scopes `profile`, `email`, `address`, and `phone` also let a Relying Party (RP) ask the OpenID Provider (OP) for **standard claims** about the authenticated user.

An Authorization Server built with Spring Boot, Spring Security, and Spring Authorization Server (SAS) must answer three distinct questions:

1. **Which scopes is the client allowed to request?** — depends on client registration and policy.
2. **Which scopes did the user/Authorization Server actually agree to grant?** — depends on authentication, consent, and data policies.
3. **Which claims can actually be returned to the RP, and at which endpoint?** — depends on available data, verification state, intended purpose, and ID Token/UserInfo implementation.

For instance, a booking app might request `openid profile email` to display a name and send confirmations. A delivery app might also request `address phone`, yet that does not mean every user has an address/phone on file or every client is authorized to receive that data.

This lesson belongs to the **OIDC Core and ID Token** chapter of the `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER` module, aiming to teach designing, configuring, securing, testing, and operating an OAuth 2.0/OIDC Authorization Server in Spring Boot. The focus is **delivering claims accurately for the four standard scopes**, rather than equating a requested scope with guaranteed data disclosure.

After completing this lesson, you should be able to:
- Accurately recall the OIDC standard claims associated with each scope.
- Distinguish `openid`, claim-requesting scopes, granted scopes, and actually released claims.
- Choose appropriately between **ID Token**, **UserInfo Response**, and **access token**.
- Return a stable `sub`, never spoof email/phone verification status, and avoid leaking excess PII.
- Design mappers driven by **authorized scopes**, client policy, and data state.
- Configure SAS to restrict scopes/consent, customize UserInfo, and test with an RP.

### 1.1. Delivery Flow Overview

~~~mermaid
sequenceDiagram
    autonumber
    participant RP as Relying Party
    participant BR as Browser
    participant AS as Spring Authorization Server / OP
    participant U as User
    RP->>BR: Redirect authorization: scope=openid profile email
    BR->>AS: Authorization Code + PKCE request
    AS->>U: Login and prompt consent per policy
    U-->>AS: Approve permitted scopes
    AS->>AS: Determine authorized scopes
    AS-->>BR: Authorization code + state
    BR-->>RP: Callback
    RP->>AS: POST token endpoint + code_verifier
    AS-->>RP: ID Token, access token (granted scopes)
    RP->>AS: GET UserInfo with access token
    AS->>AS: Filter claims by scope + client policy + data
    AS-->>RP: JSON with sub and permitted claims
    RP->>RP: Compare UserInfo sub with ID Token sub
~~~

## 2. Claim-Requesting Scopes Differ From Granted Claims

OIDC Core 1.0 defines these scopes:
- `openid`: required marker requesting OIDC authentication; establishes the ID Token baseline.
- `profile`: requests the standard profile attribute set.
- `email`: requests email and email verification status.
- `address`: requests structured postal address information.
- `phone`: requests phone number and phone verification status.

These are **scope values for requesting claims**, not proof that the user possesses the data or consented to every client reading all claims.

| Concept | Example | What Can Be Concluded |
| --- | --- | --- |
| **Requested scope** | Client sends `scope=openid profile email phone` | Client desires those information groups |
| **Registered/allowed scopes** | Client is registered for `openid`, `profile`, `email` | Client cannot self-elevate to `phone` |
| **Authorized/granted scopes** | AS actually grants `openid profile email` | Only these scopes govern claim release |
| **Available claims** | User has `name`, `email` but no `picture` | Cannot fabricate `picture` from scope |
| **Released claims** | UserInfo returns `sub`, `name`, `email` | Real policy-filtered data, not necessarily every claim in the scope |

In SAS, `RegisteredClient.getScopes()` is the set of scopes **registered for the client**. That set does not substitute for the **authorized scopes** of a specific authorization or access token.

### 2.1. Without the openid Scope, It Is Not an OIDC Authentication Request

Examples:
- `scope=openid profile email`: valid OIDC request in terms of scope (all other conditions must still hold).
- `scope=profile email`: these scope names alone **do not convert** an OAuth request into an OpenID Connect request; never default to issuing an ID Token just because `profile` is present.
- `scope=openid`: performs OIDC login with `sub` in the ID Token, without implying email, name, or phone number will be returned.

### 2.2. Scopes Authorize Requesting, Not Forcing the OP to Disclose Data

OIDC Core section `5.4` uses `profile`/`email`/`address`/`phone` scopes to request **standard claims**, and scope-requested claims are processed as **Voluntary Claims**. An OP may omit a claim if data does not exist, is unverified, is restricted by policy, or was denied by the user.

Therefore, the RP should never write logic like:

~~~java
// WRONG: email scope does not guarantee a non-null email
String email = oidcUser.getClaimAsString("email");
sendVerificationMail(email); // may be null or unverified
~~~

Handle missing claims gracefully, distinguish verification state, and provide an application flow to collect missing data if genuinely needed.

## 3. Standard Table: Which Scopes Request Which Claims?

This is the core table per **OpenID Connect Core 1.0, section `5.4 Requesting Claims using Scope Values`**.

| OIDC Scope | Requested Standard Claims | Data Format / Notes |
| --- | --- | --- |
| `profile` | `name`, `family_name`, `given_name`, `middle_name`, `nickname`, `preferred_username`, `profile`, `picture`, `website`, `gender`, `birthdate`, `zoneinfo`, `locale`, `updated_at` | Profile claims; fields may be absent |
| `email` | `email`, `email_verified` | `email` is string; `email_verified` is boolean |
| `address` | `address` | JSON object with `formatted`, `street_address`, `locality`, `region`, `postal_code`, `country` |
| `phone` | `phone_number`, `phone_number_verified` | Phone number as string; verification is boolean |
| `openid` | Does not request profile/email/address/phone sets; activates OIDC semantics and ID Token with `sub` | `sub` is the user's subject identifier at the issuer |

**Do not confuse scope names with claim names:** the `profile` scope includes a claim also named `profile` (typically a profile page URL), yet that scope requests many other claims as well. Conversely, `address` is both a scope and the name of a claim whose value is an **object**, not a plain string.

### 3.1. Example Scope Combinations

| Requested Scopes | Claim Groups the RP May Receive (If Granted and Available) |
| --- | --- |
| `openid` | `sub` and standard ID Token authentication claims |
| `openid profile` | Adds name, nickname, locale, avatar, profile URL, etc. |
| `openid email` | Adds `email` and `email_verified` |
| `openid address` | Adds the `address` object |
| `openid phone` | Adds `phone_number` and `phone_number_verified` |
| `openid profile email address phone` | Requests all groups; does not mean all will be returned |

If the server defines custom scopes such as `orders.read`, `role.read`, or `tenant.admin`, they are **not** standard OIDC scopes. Any custom claims tied to those scopes need explicit policy, schema, and documentation—never stuff arbitrary data into `profile`.

## 4. The profile Scope: Profile Data, Not Full Account Access

Standard claims requested by `profile` carry distinct semantics:

| Claim | Description | Handling |
| --- | --- | --- |
| `name` | Full display name | Do not treat as a unique identifier |
| `family_name` | Surname / family name | May not fit all naming cultures |
| `given_name` | First / given name | May be absent |
| `middle_name` | Middle name | May be absent |
| `nickname` | Casual name | May collide across users |
| `preferred_username` | Shorthand name user prefers | Not inherently globally unique |
| `profile` | Profile page URL | A URL, not a JSON object |
| `picture` | Profile picture URL | May change; protect privacy when fetching |
| `website` | User's website URL | Do not treat as trusted for server-side fetches |
| `gender` | Self-asserted gender per OIDC format | Sensitive personal data; never force entry |
| `birthdate` | Birthday in ISO 8601 format | May contain year only or month/day; avoid inferring age when incomplete |
| `zoneinfo` | Time zone from IANA database | E.g., `Asia/Ho_Chi_Minh` |
| `locale` | BCP 47 locale tag | E.g., `vi-VN`, `en-US` |
| `updated_at` | Unix time (NumericDate) profile was last updated | Do not equate with token issuance time |

Example partial UserInfo response when only `openid profile` is granted:

~~~json
{
  "sub": "user-7c92",
  "name": "Nguyen An",
  "given_name": "An",
  "family_name": "Nguyen",
  "preferred_username": "an.nguyen",
  "locale": "vi-VN",
  "zoneinfo": "Asia/Ho_Chi_Minh",
  "picture": "https://cdn.example.com/avatars/user-7c92.png",
  "updated_at": 1794800000
}
~~~

Not every profile claim needs to appear. A user might have no website, no nickname stored, or decline to share birthdate. **Do not emit `null` across all fields to "pad the schema" when product policy expects omitted claims**; the RP must handle absent claims.

### 4.1. Pitfall of Identifying Users by Display Name

**Never use** `name`, `preferred_username`, or `picture` as the RP's account primary key. These values can change, collide, or be user-chosen. The RP should use the verified **`(iss, sub)`** pair to identify OIDC users.

### 4.2. Do Not Turn profile Into a Default PII Dump

The `profile` scope can request `gender` and `birthdate`. They are highly sensitive and unnecessary for most apps. The OP should enforce data minimization: disclose claims only within available data, authorized purpose, and active policy. If an app only needs age verification, consider returning a threshold boolean via a dedicated extension rather than exact birthdates.

## 5. The email Scope: email and email_verified

### 5.1. Two Claims With Distinct Roles

~~~json
{
  "sub": "user-7c92",
  "email": "an@example.com",
  "email_verified": true
}
~~~

- `email`: end-user's email address, string. Not guaranteed unique, immutable, or a global identifier key.
- `email_verified`: boolean indicating whether the OP verified control of the email via its verification mechanism (`true` if verified, `false` otherwise).

**`email_verified=true` does not mean the OP guarantees permanent control over the email**, nor does it make email strong enough to auto-link two accounts across different OPs.

### 5.2. Representing Verification State

| Case | JSON to Return | How the RP Interprets It |
| --- | --- | --- |
| Email available and verified by OP | `email` + `email_verified: true` | Usable per OP trust level and product policy |
| Email available but unverified | `email` + `email_verified: false` | Must not assume proven ownership |
| No email / user disallows sharing | Omit `email`; handle verified flag per data policy | RP must support missing-email flows |
| Verification state unknown | Never default to `true` | Avoid overstating trust |

Especially in federated login, **never merge accounts solely by comparing emails** without an independent linking workflow backed by strong evidence. Two OPs can assign the same email to different subjects, or an email address can be recycled to another person.

### 5.3. Email Does Not Guarantee Deliverability

An address verified at sign-up may no longer receive mail later. If the app uses email for password resets, payments, or sensitive notifications, apply additional checks, rate limiting, and contextual security policies.

## 6. The address Scope: Structured Claim Object

`address` is both a scope name and a standard claim name. **The value of the `address` claim is a JSON object** following the OIDC Core address model, not merely a single address string.

Example:

~~~json
{
  "sub": "user-7c92",
  "address": {
    "formatted": "12 Hoa Sen Street\nCentral Ward, Ho Chi Minh City\nVietnam",
    "street_address": "12 Hoa Sen Street",
    "locality": "Ho Chi Minh City",
    "region": "Ho Chi Minh",
    "postal_code": "700000",
    "country": "Vietnam"
  }
}
~~~

### 6.1. Field Meanings

| Key | Meaning |
| --- | --- |
| `formatted` | Full mailing address formatted for display, using newlines where needed |
| `street_address` | Street number, street name, and street-level details |
| `locality` | City or locality |
| `region` | State, province, prefecture, or region |
| `postal_code` | Zip code or postal code |
| `country` | Country name component per OIDC Core; **not by default an ISO-3166 alpha-2 code** |

OIDC Core describes `country` as a country name value (e.g., `"USA"`). An internal system may store ISO-3166 codes, yet you cannot assume every OIDC Provider emits two-letter codes. For interoperability, document the actual format and normalize data before issuing the claim.

An address object may contain only `formatted` or only a subset of component keys. **Not every key is required** to appear. Address data is sensitive and easily becomes stale; never treat a "profile address" as a user-confirmed shipping address for every transaction.

### 6.2. Shipping or Billing Addresses Need Separate Policy

Real orders need recipient name, delivery details, administrative validation, and transaction-time confirmation. The OP's `address` claim may simply be a stored contact address. The RP should ask the user to confirm/update it rather than silently repurposing OIDC profile data.

## 7. The phone Scope: phone_number and phone_number_verified

~~~json
{
  "sub": "user-7c92",
  "phone_number": "+84901234567",
  "phone_number_verified": false
}
~~~

- `phone_number`: end-user's telephone number; OIDC Core recommends **E.164** format whenever possible to avoid country-code ambiguity.
- `phone_number_verified`: boolean indicating whether the OP verified control of the phone number via its own method.

| State | Handling |
| --- | --- |
| `phone_number_verified=true` | OP reports the number was verified per policy; RP still weighs trust/context |
| `phone_number_verified=false` | Never treat the number as a trusted channel for sensitive transaction confirmation |
| Missing `phone_number` | Never assume a number exists or pull one from unauthorized sources |
| Changed/recycled number | Requires re-verification and re-evaluating linking per product policy |

A previously verified phone number can be reassigned by carriers. Therefore, `phone_number_verified=true` should not automatically serve as permanent strong MFA, especially for financial actions or account recovery.

## 8. Where to Deliver Claims: ID Token, UserInfo, or Access Token?

A common OIDC mistake is seeing `profile`/`email`/`address`/`phone` scopes and stuffing **all PII into the ID Token or access token**. This widens data exposure and sends unnecessary personal data to downstream services.

| Carrier | Purpose | Recommendation for Standard Profile Claims |
| --- | --- | --- |
| **ID Token** | Proves authentication result to the RP; asserts issuer, subject, audience, and login context | Keep minimal; add claims only if genuinely needed and permitted by policy |
| **UserInfo Endpoint** | Returns end-user info to the RP presenting an eligible access token | Natural place to return claims per standard scopes |
| **Access Token (JWT/opaque)** | Credential/authorization for protected resources | Should carry only token-related claims and minimal authorization data; never copy OIDC PII by default |
| **Introspection** | Returns token state metadata to authenticated resource servers | Not intended by default as a full OIDC profile source |
| **Consent record** | Records scopes approved for a client | Not a UserInfo response and does not fabricate claims |

### 8.1. Authorization Code Flow: Minimal ID Token, Scoped UserInfo

In the OIDC Authorization Code Flow, the OP can return an ID Token with foundational claims:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-7c92",
  "aud": "portal-client",
  "iat": 1794800100,
  "exp": 1794803700
}
~~~

This is a minimal payload; actual ID Tokens may include claims required by the flow and configuration, such as `auth_time`, `nonce` (if sent by RP), `azp` in certain cases, or `at_hash` per profile. Tokens must be signed/verified per OIDC Core.

The RP uses the access token to call `/userinfo` and retrieve only the claims the OP actually permits. This keeps the ID Token compact while gating UserInfo access by the access token's scope and lifetime.

**Important:** OIDC Core allows certain claims to be returned in the ID Token depending on flow/profile and `claims` parameter requests; there is no rule forcing all profile claims into the ID Token. Conversely, returning claims at UserInfo still requires checking consent, scopes, and policy.

### 8.2. UserInfo Must Include sub and Prevent Token Substitution

A standard UserInfo response must contain the user's `sub`. **The RP MUST verify that `sub` in the UserInfo response matches `sub` received in the ID Token exactly**; if they differ, never use the UserInfo response.

~~~text
ID Token:  iss = https://auth.example.com
           sub = user-7c92

UserInfo:  sub = user-7c92        -> safe to use claims

UserInfo:  sub = other-user       -> MUST reject response
~~~

Even if both documents share the same email, a subject mismatch is a security failure. The `(iss, sub)` pair is the RP's identity correlation key, not email or phone number.

### 8.3. UserInfo Uses an Access Token, Not an ID Token

HTTP requests to UserInfo typically look like:

~~~http
GET /userinfo HTTP/1.1
Host: auth.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
Accept: application/json
~~~

Never send an ID Token in the `Authorization` header in place of an access token. The OP must verify that the access token is valid, of the right type/context, unexpired/unrevoked per policy, and carries appropriate scopes before releasing claims.

### 8.4. The email Scope Does Not Grant API Permission to Send Email

`email` is an OIDC scope requesting standard claims. It does **not** grant operational permissions such as `mail.send`, `contacts.write`, or `orders.read`, does not grant mailbox access, and cannot replace dedicated OAuth API permissions.

## 9. Claim Release Decision Pipeline

A sound design avoids logic like "if the client was ever registered for this scope, return all claims." Instead, for each request, evaluate:

~~~mermaid
flowchart TD
    A[UserInfo request receives access token] --> B{Valid token belonging to OIDC authorization?}
    B -->|No| X[Reject]
    B -->|Yes| C[Look up subject sub and effective authorized scopes]
    C --> D[Check RegisteredClient and policy/consent]
    D --> E[Read profile data from trusted source]
    E --> F{Data exists and disclosure allowed?}
    F -->|No| G[Omit claim or reject per contract]
    F -->|Yes| H[Select claims matching scopes]
    H --> I[Verify schema, data types, and PII policy]
    I --> J[Return UserInfo with valid sub]
    G --> J
    B --> K[Never bypass token validation]
~~~

A useful mental model is:

~~~text
released_claims =
    standardClaimsFor(authorized_scopes)
    ∩ claimsActuallyAvailableFor(subject)
    ∩ claimsAllowedByPolicy(client, subject, tenant, purpose)
    ∩ claimsAllowedByUserConsent(...)
~~~

This formula expresses **policy design**, not a set intersection SAS executes automatically. Consent may be scope-level or granular claim-level depending on the system. Even when consent grants the `profile` scope, you can still apply data minimization and omit sensitive claims.

### 9.1. Where Do Effective Scopes Come From?

In the Authorization Code Flow, the client sends `scope` when initiating authorization. The Authorization Server must determine the final valid scope set and record it in the authorization/token. When UserInfo is called, **never** use a caller-supplied `scope` query parameter to decide claims; rely strictly on the verified authorization of the presented access token.

Layers to keep distinct:

| Source | Usable as a Check Source? | Why |
| --- | --- | --- |
| `RegisteredClient.scopes` | Yes, to check what the client may request | Only an upper bound, not the granted scopes |
| Requested `scope` at authorize endpoint | Yes, after validation/normalization | Only expresses the client's request |
| Stored consent/authorization | Yes | Shows approval outcome per AS model |
| Scopes bound to verified access token | **Yes; authoritative source at UserInfo** | Restricts data to the exact token presented |
| Arbitrary header like `X-Scope: email` | **No** | Can be spoofed by the client |
| Unverified JWT claims | **No** | No proof of issuer/authorization |

### 9.2. Difference Between Consent, Client Policy, and Availability

Suppose:
- Client is registered for `openid profile email address phone`.
- User only approved `openid profile email`.
- User's email is unverified.
- System has both address and phone number stored.

Expected result: do not return `address` or `phone_number` just because the server stores them; return `email` with `email_verified: false` if policy allows. `profile` fields need not all be populated either.

### 9.3. Claims Parameter for Finer Precision

OIDC Core also provides the `claims` authorization request parameter so an RP can request individual claims at `userinfo` and/or `id_token`:

~~~json
{
  "userinfo": {
    "given_name": null,
    "email": {"essential": true}
  },
  "id_token": {
    "auth_time": {"essential": true}
  }
}
~~~

This is the **JSON payload** of the `claims` parameter (which must be properly URL-encoded in the authorization URL). It does not grant extra permissions by itself. `essential: true` indicates importance to the RP; the OP must still enforce permissions, consent, and policy, handling unmet essential claims per the appropriate protocol/profile.

For example, an RP wanting `given_name` and `email` may combine `openid profile email` with `claims` if the OP supports it. Before relying on this feature, check `claims_parameter_supported` metadata and the actual behavior of your SAS version. **Never assume every SAS version supports the full Claims Parameter simply because OIDC is enabled.**

## 10. End-to-End Example: Client Requests profile/email, Not address/phone

### 10.1. Authorization Request

The client registers Authorization Code + PKCE, and consent is configured per policy. The browser visits:

~~~http
GET /oauth2/authorize?response_type=code&client_id=portal-web&redirect_uri=https%3A%2F%2Fportal.example.com%2Flogin%2Foauth2%2Fcode%2Fportal&scope=openid%20profile%20email&state=OPAQUE_TRANSACTION_STATE&code_challenge=PKCE_S256_CHALLENGE&code_challenge_method=S256&nonce=OIDC_NONCE HTTP/1.1
Host: auth.example.com
~~~

`OPAQUE_TRANSACTION_STATE`, `PKCE_S256_CHALLENGE`, and `OIDC_NONCE` are placeholders replaced with randomly generated/valid PKCE values in real requests.

After login/consent, the server redirects to the registered `redirect_uri` with an authorization code and state. The client verifies state, then exchanges the code at the token endpoint with the verifier:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_OF_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=AUTHORIZATION_CODE&redirect_uri=https%3A%2F%2Fportal.example.com%2Flogin%2Foauth2%2Fcode%2Fportal&code_verifier=ORIGINAL_PKCE_VERIFIER
~~~

### 10.2. Token Response and Granted Scopes

Illustrative response:

~~~json
{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "openid profile email",
  "id_token": "SIGNED_ID_TOKEN_VALUE"
}
~~~

The granted scopes are `openid profile email`, excluding `address` and `phone`. If `scope` is omitted from the token response, the client applies standard OAuth rules for interpreting granted scopes; never assume extra scopes were silently added.

The ID Token carries `sub` and required authentication claims; it does not necessarily contain email, name, or other PII groups.

### 10.3. UserInfo Response

The client calls:

~~~http
GET /userinfo HTTP/1.1
Host: auth.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

A valid response might be:

~~~json
{
  "sub": "user-7c92",
  "name": "Nguyen An",
  "given_name": "An",
  "family_name": "Nguyen",
  "locale": "vi-VN",
  "email": "an@example.com",
  "email_verified": true
}
~~~

Neither `address` nor `phone_number` appears. The fact that the OP happens to store shipping address or phone data **does not permit** including them when the corresponding scopes were not granted, absent a separate standardized authorization and consent.

### 10.4. When the Client Requests Scopes That Are Not Granted

If the client sends `openid profile email phone` yet policy only grants `openid profile email`, tokens and UserInfo must honor only the effective granted scopes. The OP may reject a policy-violating authorization request or grant a subset per grant rules and user consent; the RP must read the actual outcome rather than assuming `phone` was granted from its original request.

## 11. Configuring RegisteredClient and Consent in Spring Authorization Server

### 11.1. Allowing the Right OIDC Scopes

SAS 1.5.x example for a confidential web client:

~~~java
@Bean
RegisteredClient portalRegisteredClient(PasswordEncoder passwordEncoder,
                                        ClientSecrets secrets) {
    return RegisteredClient.withId(UUID.randomUUID().toString())
            .clientId("portal-web")
            .clientSecret(passwordEncoder.encode(secrets.portalClientSecret()))
            .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                    AuthorizationGrantType.AUTHORIZATION_CODE)
            .authorizationGrantType(
                    AuthorizationGrantType.REFRESH_TOKEN)
            .redirectUri(
                    "https://portal.example.com/login/oauth2/code/portal")
            .scope(OidcScopes.OPENID)
            .scope(OidcScopes.PROFILE)
            .scope(OidcScopes.EMAIL)
            .scope(OidcScopes.ADDRESS)
            .scope(OidcScopes.PHONE)
            .clientSettings(ClientSettings.builder()
                    .requireProofKey(true)
                    .requireAuthorizationConsent(true)
                    .build())
            .build();
}
~~~

`ClientSecrets` is an application-built interface/service retrieving secrets from a secret manager; this code focuses on the `RegisteredClient` builder and omits repository imports/beans needed for a standalone runnable project.

**Key reminders:**
- Registering `scope(OidcScopes.EMAIL)` only means the client **is allowed to ask for the email scope**.
- `requireAuthorizationConsent(true)` enables SAS consent, yet your consent UI/policy must still present clear disclosures to the user.
- Registering `address` and `phone` for every client is a poor default; real products should grant them only to clients with approved purposes.
- `requireProofKey(true)` protects the Authorization Code Flow with PKCE; it does not replace consent or PII policies.

### 11.2. Enabling the OIDC UserInfo Endpoint

In SAS 1.5.x, OpenID Connect is disabled by default; you must enable `oidc(...)` alongside Authorization Server infrastructure, signing keys, issuer, client repository, and user login.

~~~java
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        Function<OidcUserInfoAuthenticationContext, OidcUserInfo> mapper)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .oidc(oidc -> oidc
                .userInfoEndpoint(userInfo -> userInfo
                    .userInfoMapper(mapper)
                )
            )
        )
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .exceptionHandling(ex -> ex.authenticationEntryPoint(
                new LoginUrlAuthenticationEntryPoint("/login")));

    return http.build();
}
~~~

`OidcUserInfoEndpointConfigurer.userInfoMapper(...)` is SAS's extension point for building UserInfo claims from the authenticated authorization. This snippet focuses on OIDC/UserInfo; a real app also needs `RegisteredClientRepository`, `OAuth2AuthorizationService`, `JWKSource<SecurityContext>`, `JwtDecoder`, a user login chain, and related configuration.

**Never protect UserInfo with "just a login session."** The UserInfo Endpoint accepts an **access token**; the framework's default provider/filter must authenticate the token and authorization before the mapper returns claims. A custom mapper may only transform authenticated data—never bypass token validation or scope checks.

### 11.3. Data Sources and Retrieval Timing

A real OP can read claims from:
- An internal user profile store with stable identity mapping.
- An email/phone verification system.
- An address store with clear consent and provenance.
- User attributes obtained via federation, tracking trustworthiness and timestamps.

Never put passwords, OTPs, secrets, private keys, access tokens, or session internals into UserInfo. `email_verified`/`phone_number_verified` must come strictly from verified evidence. If data is missing or sharing consent was revoked, omit the claim per policy—never fall back to another user's data.

## 12. Building a Scope-Filtering UserInfo Mapper in Java

### 12.1. Data Model and Policy

This example uses Java 17+ and illustrative SAS **1.5.x** APIs. `ProfileRepository`, `DisclosurePolicy`, and data validation mechanisms are application-implemented components. The goal is to avoid both pitfalls: **reading registered scopes instead of granted scopes** and **returning the full profile regardless of consent/policy**.

~~~java
record ProfileSnapshot(
        String name,
        String givenName,
        String familyName,
        String preferredUsername,
        String locale,
        String email,
        Boolean emailVerified,
        Map<String, ?> address,
        String phoneNumber,
        Boolean phoneNumberVerified) {
}

interface ProfileRepository {
    ProfileSnapshot loadByInternalPrincipal(String principalName);
}

@FunctionalInterface
interface DisclosurePolicy {
    boolean allows(String clientId, String claimName);
}
~~~

A production system will also track tenant, consent version, verification timestamps, and dedicated access policies; this record is intentionally concise. The profile repository must load data for the exact internal principal without using email as a unique key.

### 12.2. Helper Allowing Only Granted-Scope Standard Claims

~~~java
private static void putString(
        Map<String, Object> target,
        String claim,
        String value,
        String clientId,
        DisclosurePolicy policy) {

    if (value != null && !value.isBlank() && policy.allows(clientId, claim)) {
        target.put(claim, value);
    }
}

static Map<String, Object> buildUserInfoClaims(
        String idTokenSubject,
        Set<String> authorizedScopes,
        String clientId,
        ProfileSnapshot data,
        DisclosurePolicy policy) {

    Map<String, Object> result = new LinkedHashMap<>();

    // Always use the exact subject the OP issued in the ID Token.
    result.put("sub", idTokenSubject);

    if (authorizedScopes.contains(OidcScopes.PROFILE)) {
        putString(result, "name", data.name(), clientId, policy);
        putString(result, "given_name", data.givenName(), clientId, policy);
        putString(result, "family_name", data.familyName(), clientId, policy);
        putString(result, "preferred_username",
                data.preferredUsername(), clientId, policy);
        putString(result, "locale", data.locale(), clientId, policy);
    }

    if (authorizedScopes.contains(OidcScopes.EMAIL)) {
        putString(result, "email", data.email(), clientId, policy);
        if (result.containsKey("email")
                && data.emailVerified() != null
                && policy.allows(clientId, "email_verified")) {
            result.put("email_verified", data.emailVerified());
        }
    }

    if (authorizedScopes.contains(OidcScopes.PHONE)) {
        putString(result, "phone_number", data.phoneNumber(),
                clientId, policy);
        if (result.containsKey("phone_number")
                && data.phoneNumberVerified() != null
                && policy.allows(clientId, "phone_number_verified")) {
            result.put("phone_number_verified", data.phoneNumberVerified());
        }
    }

    if (authorizedScopes.contains(OidcScopes.ADDRESS)
            && data.address() != null
            && policy.allows(clientId, "address")) {
        Set<String> allowedKeys = Set.of(
                "formatted", "street_address", "locality",
                "region", "postal_code", "country");
        Map<String, Object> address = new LinkedHashMap<>();
        for (String key : allowedKeys) {
            Object value = data.address().get(key);
            if (value instanceof String s && !s.isBlank()) {
                address.put(key, s);
            }
        }
        if (!address.isEmpty()) {
            result.put("address", address);
        }
    }

    return result;
}
~~~

This helper only illustrates common claims. If your app supports full `profile`, add `middle_name`, `nickname`, `profile`, `picture`, `website`, `gender`, `birthdate`, `zoneinfo`, and `updated_at` with proper data validation. Never conclude from omitted fields in this sample that OIDC Core lacks them.

**Why read `sub` from the ID Token instead of `principalName`?** In OPs using pairwise subject identifiers or federation, the `sub` seen by an RP may differ from the internal username. UserInfo must return **the exact OIDC subject** that the ID Token issued to that RP. This function accepts `idTokenSubject` from the OP-issued source rather than letting an HTTP caller pick it.

### 12.3. Mapper Accessing the Verified Authorization and Access Token

One way to wire the helper into SAS's UserInfo endpoint:

~~~java
@Bean
Function<OidcUserInfoAuthenticationContext, OidcUserInfo> userInfoMapper(
        ProfileRepository profiles,
        DisclosurePolicy policy) {

    return context -> {
        OAuth2Authorization authorization = context.getAuthorization();

        var idTokenHolder = authorization.getToken(OidcIdToken.class);
        if (idTokenHolder == null) {
            throw new IllegalStateException("OIDC ID Token is missing");
        }

        String subject = idTokenHolder.getToken().getSubject();
        Set<String> scopes =
                authorization.getAccessToken().getToken().getScopes();

        ProfileSnapshot data =
                profiles.loadByInternalPrincipal(
                        authorization.getPrincipalName());

        Map<String, Object> released = buildUserInfoClaims(
                subject,
                scopes,
                context.getRegisteredClient().getClientId(),
                data,
                policy
        );

        return new OidcUserInfo(released);
    };
}
~~~

Points to verify before deploying to production:
- `OidcUserInfoAuthenticationContext` comes from the **UserInfo authentication flow** after the provider verifies the access token; the mapper must never become a public unauthenticated endpoint.
- `authorization.getAccessToken()` represents the access token on the retrieved authorization. With custom token persistence or multiple tokens under one authorization, ensure the scope set used for filtering is the scope set of the **actual token authenticated in this request**, not the broadest historical scope of the authorization.
- `OidcIdToken` supplies the `sub` of that OIDC authorization; if absent or invalid, fail safely rather than returning UserInfo for a guessed principal.
- `ProfileRepository` and `DisclosurePolicy` are not built-in Spring Security classes; they are application contracts that must enforce tenant/client/user isolation.
- When no profile fields exist for a subject, still return the exact `sub` on valid requests; optional claims can be omitted per policy.
- Never return `email_verified=true`/`phone_number_verified=true` without verification evidence.

A mapper returning `new OidcUserInfo(idToken.getClaims())` directly appears as a quick demo in some guides, yet you must audit **which claims sit in the ID Token**, the active token's scopes, and data-minimization goals. In real systems, do not treat every ID Token claim as automatically authorized for every UserInfo caller.

### 12.4. Unit-Testing the Helper Directly

~~~java
@Test
void releaseOnlyGrantedAndAllowedClaims() {
    ProfileSnapshot profile = new ProfileSnapshot(
            "Nguyen An", "An", "Nguyen", "an.nguyen", "vi-VN",
            "an@example.com", true,
            Map.of("locality", "Hanoi", "country", "Vietnam"),
            "+84901234567", false
    );

    DisclosurePolicy allowAll = (clientId, claim) -> true;

    Map<String, Object> claims = buildUserInfoClaims(
            "pairwise-sub-123",
            Set.of(OidcScopes.OPENID, OidcScopes.PROFILE, OidcScopes.EMAIL),
            "portal-web",
            profile,
            allowAll
    );

    assertEquals("pairwise-sub-123", claims.get("sub"));
    assertEquals("Nguyen An", claims.get("name"));
    assertEquals("an@example.com", claims.get("email"));
    assertEquals(true, claims.get("email_verified"));

    assertFalse(claims.containsKey("address"));
    assertFalse(claims.containsKey("phone_number"));
}
~~~

Even though the user profile holds both address and phone number, the helper omits them because their scopes were not granted.

## 13. When Should Claims Be Put Into the ID Token?

In many OPs, the RP needs to establish a session or show a name right after login without always calling UserInfo. OIDC allows including certain user claims in the ID Token, yet you must manage the risk of **emitting long-lived, logged, copied PII that is hard to revoke from clients**.

### 13.1. Differences Between ID Token and UserInfo Claims

| Criterion | ID Token | UserInfo |
| --- | --- | --- |
| Delivery mechanism | Token response or authorization response per flow | Endpoint call with access token |
| Primary audience | OIDC Relying Party | RP authorized to use the token |
| Core purpose | Authentication assertions: `iss`, `sub`, `aud`, `exp`, etc. | User claims such as name, email, address, phone |
| Data freshness | Claims are a snapshot at issuance time | Can read fresh data per policy/cache |
| Exposure risk | Emitted PII-bearing tokens may remain stored at the RP | Gated by access token, policy, and lifetime |
| `sub` field | Required | Required; must match ID Token `sub` |

Recommendation: keep the ID Token minimal with what the RP needs to verify authentication, and use UserInfo for mutable or sensitive claims. If a real use case genuinely needs `email` in the ID Token, check granted scopes, consent, client policy, verification source, and lifetime/logging rules.

### 13.2. JWT Token Customizer in SAS Is a Separate Extension Point

When using JWT ID Tokens, `OAuth2TokenCustomizer<JwtEncodingContext>` can customize claims. A careful design:

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> idTokenCustomizer(
        ProfileRepository profiles,
        DisclosurePolicy policy) {

    return context -> {
        if (!OidcParameterNames.ID_TOKEN.equals(
                context.getTokenType().getValue())) {
            return;
        }

        // Keep ID Token minimal. Example only: release email for
        // the right client and granted scope if the use case truly requires it.
        Set<String> grantedScopes = context.getAuthorizedScopes();
        String clientId = context.getRegisteredClient().getClientId();

        if (grantedScopes.contains(OidcScopes.EMAIL)
                && policy.allows(clientId, "id_token.email")) {
            ProfileSnapshot profile = profiles.loadByInternalPrincipal(
                    context.getPrincipal().getName());
            if (profile.email() != null && !profile.email().isBlank()) {
                context.getClaims().claim("email", profile.email());
                if (profile.emailVerified() != null) {
                    context.getClaims().claim(
                            "email_verified", profile.emailVerified());
                }
            }
        }
    };
}
~~~

This example is a **policy choice**, not an OIDC mandate to put email into ID Tokens. When applying it:
- Never overwrite `iss`, `sub`, `aud`, `exp`, or framework-managed security claims.
- Use `context.getPrincipal().getName()` to look up internal profiles only if your application maintains an exact principal mapping.
- `getAuthorizedScopes()` must reflect the valid grant at token issuance time.
- Check your SAS version: classes/providers/customizer DSLs may move packages or evolve in Spring Security 7.x.
- Never use an access token JWT customizer to accidentally dump email, address, and phone into every API access token.

### 13.3. Avoiding Duplication and Stale Data

If an ID Token carried `email` at login time and UserInfo later returns a newer email after the user updated their profile, the RP needs a defined source-of-truth precedence and safe update handling. Never assume the old email is the root identity; **`sub` is the identifier RPs use for account linking**.

## 14. Safely Handling Claims in Spring Security on the Relying Party

### 14.1. Reading OIDC Claims From OidcUser

After OIDC login, Spring Security can populate `OidcUser` as the principal. UserInfo data is not always present, so RP code must handle nulls and verify identity:

~~~java
@GetMapping("/account/summary")
Map<String, Object> accountSummary(@AuthenticationPrincipal OidcUser user) {
    // Spring Security OIDC login has already run token verification per config.
    String subject = user.getSubject();
    String issuer = user.getIssuer().toString();

    OidcUserInfo userInfo = user.getUserInfo(); // May be null.
    String email = userInfo == null ? null : userInfo.getEmail();
    Boolean verified = userInfo == null
            ? null : userInfo.getEmailVerified();

    return Map.of(
            "identity", issuer + "|" + subject,
            "hasEmail", email != null,
            "emailVerified", Boolean.TRUE.equals(verified)
    );
}
~~~

This snippet returns status flags only, avoiding echoing sensitive emails to APIs unnecessarily. `@AuthenticationPrincipal` can be null for unauthenticated requests; protect the controller with Spring Security. In real apps, use a composite key type with separate `issuer` and `subject` fields instead of string concatenation if delimiter collisions are possible.

**Do not ignore a null UserInfo:** an RP can log in using just the ID Token without calling UserInfo (e.g., if the provider exposes no endpoint or the client requested no extra data). Never throw a 500 error just because `email`, `address`, or `phone_number` is absent.

### 14.2. OidcUser Merges Claims, Yet Does Not Replace Validation

`OidcUser.getClaims()` is Spring Security's unified view of relevant OIDC claims, potentially combining ID Token and UserInfo claims. When your app needs to know where a claim originated, inspect `getIdToken()` and `getUserInfo()` explicitly instead of assuming `getClaims()` always shares the same source or freshness.

For email:
- When `email_verified=true`, the RP may rely on it according to OP trust level and agreed policy.
- When false/missing, require independent verification before sensitive operations.
- Never auto-assign roles based on email domain without an explicit trust agreement and account lifecycle controls.

### 14.3. Never Use Personal Claims for Resource Authorization

An orders API must not authorize requests simply because `email` in UserInfo matches the email on an order. Authorization must rely on tokens carrying the right resource audience, scopes/authorities, and system access policies. Identity from `(iss, sub)` is only the account-resolution input.

## 15. Security, Privacy, and Operational Rules

### 15.1. Data Minimization and Consent

OIDC profile data can constitute PII. Define for every client:
- Purpose of each claim, not just each scope.
- Legal/consent basis per organizational and regulatory requirements.
- Which attributes belong in the ID Token vs. UserInfo only.
- Whether claim-level disclosures must appear on the consent screen.
- When consent expires, requires re-prompting, or stops releasing a claim.
- RP data retention/caching duration and deletion/correction rights.

**Scope consent is not a guarantee that the OP will release all claims.** Show phrasing like "This app may access your email" rather than "This app is guaranteed your verified email." If a UI says only "Profile information" while disclosing birthdate or gender, make the UI disclosures more granular.

### 15.2. Data Freshness and Verification State

Profile `updated_at` does not tell you when email/phone was verified. To track verification age, a system may maintain internal metadata such as `email_verified_at`, though that is **not a standard claim** of the OIDC Core `email` scope. Never advertise custom claims as standard.

When a user changes their email:
1. Per policy, mark the new email unverified.
2. Run the verification workflow.
3. Update `email_verified` based on actual status.
4. Never let old tokens/sessions mutate data already signed in existing ID Tokens.
5. The RP may re-fetch UserInfo or require re-verification depending on the use case.

### 15.3. Avoid Exposing Claims in Logs, Tokens, and Telemetry

Never log full UserInfo responses or complete ID Tokens in production application logs. Risks include:
- Emails/phone numbers exposed in APM traces.
- Full postal addresses stored in API gateway access logs.
- PII-bearing ID Tokens pasted into tickets or crash dumps.
- Browser analytics capturing response payloads.
- Debug endpoints echoing all claims.

Use correlation IDs, `client_id`, `issuer`, and standardized rejection reason codes; if profile debugging is required, mask emails/phones and restrict log access. Never place private signing keys or secrets in UserInfo.

### 15.4. Do Not Use a Resource Server Access Token as a UserInfo Profile Token

Resource Servers typically need scopes like `orders.read`, `orders.write`, or resource-specific claims, whereas UserInfo returns end-user profile data to the RP. Mixing the two can expose PII to unrelated APIs. Configure audience, scopes, and token handling cleanly per consumer type.

For OIDC UserInfo, the access token must represent an eligible OP-issued authorization validated by the UserInfo endpoint; never allow any validly signed token with the wrong audience or issuer to read profile data.

### 15.5. UserInfo Fetches Fresh Data, Yet Grants No Extra Permissions

UserInfo can read the latest profile, yet it must always bound claims by the scope/consent of the presented access token. For instance, if a user adds a phone number after an `openid email` token was issued, UserInfo must not return `phone_number` merely because the profile now contains one.

When a user revokes consent, enforce clear token revocation and authorization state policies; never let a UserInfo cache serve revoked claims for an extended period.

### 15.6. Tenant Isolation and Subject Identifiers

In multi-tenant systems or OPs using pairwise subjects:
- The `(iss, sub)` pair identifies an identity within a trust domain.
- `sub` may differ between two RPs per pairwise subject sector policy.
- Never use username or email as `sub` across all clients if the profile requires pairwise subjects.
- The UserInfo mapper must use the exact subject from the active authorization/ID Token, never substituting an internal principal when they differ.
- User repositories, consent, scope policies, and response caches must isolate by tenant/client/subject.
- Two users sharing an `email` across two issuers are not automatically the same account.

### 15.7. Authorization Server and UserInfo Errors

Handle these scenarios distinctly:
- Missing/invalid access token: HTTP `401` and appropriate OAuth bearer challenge/error; **never** return UserInfo with a synthetic `sub`.
- Valid token lacking policy permission for UserInfo: deny appropriately without escalating scopes or leaking sensitive claims.
- Absent optional claim: usually **omit the claim**, rather than failing the entire UserInfo request.
- Temporarily unavailable data source: fail-closed for sensitive claims or return a controlled error; never serve another user's cached entry.
- UserInfo subject differs from ID Token: RP must discard the response even if other fields look valid.

## 16. Scope-to-Claims Test Matrix

### 16.1. Unit Tests for the Policy Mapper

| Test Case | Authorized Scopes / Data | Expected Result |
| --- | --- | --- |
| `openid` only | User has full profile | Only `sub`; no profile/email/address/phone |
| `openid profile` | Has name, locale, picture | Returns allowed profile claims, no email |
| `openid email` | Verified email | Returns `email`, `email_verified: true` |
| `openid email` | Unverified email | `email_verified: false`; never flips to true |
| `openid email` | Missing email | Omits `email`; never fabricates one |
| `openid address` | Has address object | Returns `address` object matching schema |
| `openid address` | No address data | Omits `address`; no null or empty object per policy |
| `openid phone` | Has E.164 number, unverified | `phone_number`, `phone_number_verified: false` |
| `openid phone` | No phone number | Omits phone claims |
| `openid profile email` | Data has address and phone | Never exposes `address`/`phone_number` |
| Requested ≠ granted | Client requests phone, AS omits phone | Never returns `phone_number` |
| Registered ≠ granted | Client registered for address, token lacks address | Never returns `address` |
| Consent revoked | Revoked token/authorization or denied policy | Stops disclosing claims once policy takes effect |
| Client policy denies | Granted `email` but client barred from email | Never returns `email` |
| Pairwise subject | Internal username differs from ID Token `sub` | UserInfo `sub` matches ID Token subject |
| Data type bug | `email_verified="true"` as string | Never emits wrong type; catches data error |
| Tenant A/B | Two subjects share username | Never mixes profiles/claims |
| Extended scope | `orders.read` without email | Never infers email disclosure |
| Missing `openid` | OAuth request with `profile` only | Never becomes OIDC login/ID Token |
| JSON schema | `address` mapped as a string | Detected and fixed to object |

### 16.2. Authorization Code + UserInfo Integration Tests

| Step | Test | Expectation |
| --- | --- | --- |
| Registration | Client has only `openid profile` | Cannot request `email` when unregistered |
| Authorization | User declines `phone` | `phone` scope is not granted |
| Token response | Inspect granted `scope` | Reflects grant per protocol |
| ID Token | Inspect `iss`, `sub`, `aud`, `exp` | Valid OIDC, free of unauthorized PII |
| UserInfo | GET with `openid profile email` token | Returns `sub` and allowed profile/email |
| UserInfo | GET with `openid`-only token | Returns no email/phone/address |
| UserInfo | Called with ID Token | Rejected; never replaces access token |
| UserInfo | Called with expired/revoked token | Rejected |
| UserInfo | Access token for another user | Never returns the first user's profile |
| UserInfo | RP sees UserInfo `sub` ≠ ID Token `sub` | RP rejects |
| Data update | Email changes after login | Fresh UserInfo follows profile policy |
| Concurrent sessions | Two tabs hold tokens with different scopes | Each request sees only its token's claims |
| Claims Parameter | Client requests essential email without grant | Never bypasses consent; handled per profile |
| OAuth-only | Token outside OIDC authorization | Disallowed from UserInfo as an OIDC token |
| Multi-node | Data and consent consistency | No scope leakage or cross-user cache hits |
| Multi-tenant | Identical `sub` string across issuers | Claims never mix |
| Privacy | Inspect HTTP/access logs and APM | No full UserInfo or raw tokens exposed |

### 16.3. Mandatory Data Type Tests

~~~json
{
  "sub": "subject-from-id-token",
  "email": "user@example.com",
  "email_verified": false,
  "phone_number": "+84901234567",
  "phone_number_verified": true,
  "address": {
    "formatted": "Example address",
    "country": "Vietnam"
  },
  "updated_at": 1794800000
}
~~~

Verify:
- `email_verified` and `phone_number_verified` are JSON **booleans**, not `"true"`/`"false"` strings.
- `address` is a JSON **object**, not a plain text string or list.
- `updated_at` is a NumericDate, not a formatted date string.
- `phone_number` is a string (preserving `+`), never cast to an integer that strips `+` and leading zeros.
- `email`, `name`, and `given_name` are strings; absent values follow policy.
- `sub` is a string matching the OP's stable subject identifier.

## 17. Common Integration Pitfalls

### 17.1. Mistaking `RegisteredClient.scope(...)` for Granted Scope

**Wrong:**

~~~java
if (registeredClient.getScopes().contains("phone")) {
    userInfo.put("phone_number", profile.phoneNumber());
}
~~~

A client registered for `phone` might not have been granted `phone` on the current token. Use the **effective authorized scopes** of the authenticated request/token, then apply client disclosure policy.

### 17.2. Assuming the email Scope Means `email_verified=true`

Never set `email_verified=true` when the email lacks a verification record. Nor should RPs use `email_verified` as sufficient proof to auto-link accounts across multiple issuers.

### 17.3. Returning address as a String

**Wrong:**

~~~json
{"address": "12 Hoa Sen Street, Ho Chi Minh City"}
~~~

**Correct data type:**

~~~json
{
  "address": {
    "formatted": "12 Hoa Sen Street, Ho Chi Minh City"
  }
}
~~~

If an internal API stores addresses as strings, write an adapter producing the OIDC object structure rather than publishing a schema-invalid `address` standard claim.

### 17.4. Emitting phone_number as a Number

**Wrong:**

~~~json
{"phone_number": 84901234567}
~~~

**Correct:**

~~~json
{"phone_number": "+84901234567"}
~~~

Phone numbers are text containing `+` and leading zeros; converting to integers loses information.

### 17.5. Returning a UserInfo sub That Differs From ID Token sub

If `UserInfo.sub` is an internal username while ID Token `sub` is a pairwise subject ID, the RP must reject the response. The mapper must read the exact subject identifier issued for that client/authorization rather than swapping in a repository field.

### 17.6. Calling UserInfo With an ID Token

The ID Token is issued to the RP to prove authentication. It is not an OAuth access token and must never replace `Authorization: Bearer ...` at UserInfo.

### 17.7. Leaking PII Inside JWT Access Tokens

When Resource Servers or multiple downstream services receive the same access token, putting `address` and `phone_number` inside it exposes that data to every recipient. Scope token claims to the audience and granted scopes; use UserInfo for OIDC user claims where appropriate.

### 17.8. Checking Scopes While Forgetting Tenant/Client Policy

Two clients sharing `openid email` need not receive identical data. Policy may require a trust tier, valid user consent, or registered purpose. Never let `context.getRegisteredClient().getScopes()` become "unconditional permission to read every profile."

### 17.9. Mixing Claims Across Two Identity Providers

A user connected via Google and a corporate OP might share an email yet have different issuers and subjects. When displaying data, the RP must track data provenance and **never** merge two subjects just because emails match.

### 17.10. Emitting Profile Claims When Only openid Was Granted

`openid` only activates OIDC authentication; it does not implicitly authorize releasing `birthdate`, `gender`, `picture`, or `email`. Any extra consent or `claims` request mechanism must enforce explicit policy.

## 18. Case Study Exercise: Booking Portal and Delivery System

Suppose an internal OP powered by Spring Authorization Server serves two Relying Parties:

| Aspect | Booking Portal | Delivery App |
| --- | --- | --- |
| Client ID | `portal-web` | `delivery-mobile` |
| Registered scopes | `openid profile email` | `openid profile email address phone` |
| Requested scopes | `openid profile email` | `openid profile email address phone` |
| User consent | `openid profile email` | User approves only `openid profile phone` |
| Available data | Name, email, address, phone | Same user |
| Verification | Email verified; phone unverified | Same data source |

OP stores this snapshot:

~~~json
{
  "internal_user_id": "u-839",
  "public_subject": "pairwise-sub-for-client",
  "name": "Nguyen An",
  "email": "an@example.com",
  "email_verified": true,
  "phone_number": "+84901234567",
  "phone_number_verified": false,
  "address": {
    "formatted": "12 Hoa Sen Street, Ho Chi Minh City",
    "country": "Vietnam"
  }
}
~~~

Answer the following:

1. Should the Booking Portal see `phone_number` and `address`? Why or why not?
2. The Delivery App is registered for `address` and `email`, yet the user declined both scopes. May UserInfo return those claims?
3. The Delivery App receives `phone_number_verified=false`. Should it treat that number as trustworthy enough for password resets?
4. When the OP uses pairwise `sub`, where must UserInfo obtain the subject?
5. If the user updates their email after receiving the ID Token, what discrepancy might the RP see between the ID Token and UserInfo?
6. Can `email` be used to automatically link the Portal and Delivery App subjects?
7. The Delivery App needs an accurate delivery address. Is reading the OIDC `address` claim alone enough to guarantee a valid shipping address?
8. Propose at least eight tests covering granted scopes, data availability, verified flags, tenant/client isolation, and schema types.
9. If skipping UserInfo, what policies and checks are needed to put `email` into the Portal's ID Token?
10. Describe how to use `RegisteredClient`, `OidcUserInfoAuthenticationContext`, and `OidcIdToken` to build the right response.

**Answer hints:** Portal does not receive address/phone when holding only profile/email; Delivery App receives only phone (and possibly profile) per actually granted scopes. Verification flags must never be flipped to `true` artificially. UserInfo `sub` must equal ID Token `sub`, never a different internal subject. Email is not a trusted linking key. OIDC address is not automatically a user-confirmed delivery address for a transaction.

## 19. Production Deployment Checklist

1. **Standard scopes:** advertise `openid`, `profile`, `email`, `address`, and `phone` only when backed by implementation and policy.
2. **Client registration:** grant minimal allowed scopes per `RegisteredClient`; never enable `address`/`phone` across the board.
3. **Consent:** show clear access scopes to users; provide granular PII disclosures where needed.
4. **Effective scopes:** decide claim release using the actual authorization/access token scopes, never requested or registered scopes alone.
5. **Subject:** `sub` in UserInfo equals the ID Token's `sub`, separate from username, email, and internal tenant ID.
6. **Profile mappings:** adhere to standard schemas for advertised claims; allow omitting optional claims rather than fabricating data.
7. **Email:** derive boolean `email_verified` from the verification store, never from email presence.
8. **Address:** `address` is an object; limit granular address exposure and enforce purpose limitation.
9. **Phone:** store numbers as text, preferring E.164; `phone_number_verified` does not replace MFA policy.
10. **UserInfo:** protect with valid access tokens; check issuer, grant, expiry, revocation, and scopes before the mapper runs.
11. **ID Token:** carry required authentication claims; never turn it into a full user database dump.
12. **Access Token:** intended solely for protected resources without full OIDC profiles embedded; validate audience and scopes.
13. **Spring extensions:** use version-appropriate `userInfoMapper` and `OAuth2TokenCustomizer`; retain default OAuth/OIDC validators.
14. **PII policy:** enforce client/tenant/subject isolation, claim allowlists, retention, masking, and consent/token revocation.
15. **Verification/freshness:** maintain email/phone re-verification policies and update `updated_at` accurately.
16. **Testing:** unit + integration tests for every scope, requested vs. granted, missing data, schema types, subject mismatch, and privacy leaks.
17. **Operations:** emit PII-free UserInfo/claim-mapping error metrics; verify caching and token lifetimes when profile data changes.

## 20. Official Standards for Reference

- [OpenID Connect Core 1.0 — Final](https://openid.net/specs/openid-connect-core-1_0.html): `5.1 Standard Claims`, `5.3 UserInfo Endpoint`, `5.4 Requesting Claims using Scope Values`, `5.5 Claims Parameter`, subject, and ID Token validation.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): `scopes_supported`, `claims_supported`, and OP capability metadata.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): semantics of scopes, authorizations, and token responses.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636.html): PKCE in the Authorization Code Flow.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html): JWT payload and registered claims, including NumericDate.
- [Spring Authorization Server 1.5.x — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): OIDC UserInfo endpoint and `userInfoMapper` customization.
- [Spring Authorization Server 1.5.x — Core Model / RegisteredClient](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): client allowed scopes and `ClientSettings` consent.
- [Spring Authorization Server — JwtEncodingContext](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/token/JwtEncodingContext.html): JWT token customizer and authorized scopes.
- [Spring Security — OAuth2 Login / OIDC](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): RP login and OIDC claims.
- [Spring Security — OidcUserInfo](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUserInfo.html): UserInfo claims model in Spring Security.

**Takeaway:** `openid` activates OIDC, while `profile`, `email`, `address`, and `phone` **request** their respective standard claim groups without guaranteeing the OP will return all of them. Actual release decisions must depend on the **access token's authorized scopes**, available data, user consent, and client/tenant privacy policies. UserInfo must return the exact `sub` matching the ID Token; `email_verified`/`phone_number_verified` are booleans reflecting actual verification state, and `address` is a JSON object. In SAS, `RegisteredClient` bounds allowed scopes while the UserInfo mapper and token customizer control released claims—never turn ID Tokens or access tokens into a broadcast of the entire user profile.
