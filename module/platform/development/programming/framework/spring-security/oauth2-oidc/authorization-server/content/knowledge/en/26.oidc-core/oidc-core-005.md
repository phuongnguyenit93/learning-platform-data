# Meaning of azp, acr, amr, and Extended Authentication Claims

> **Chapter:** OIDC Core and ID Token  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Module objective:** Learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application.  
> **Reference versions:** OpenID Connect Core 1.0 incorporating Errata Set 2, RFC 8176, Spring Boot 3.x, Spring Security 6.x, and Spring Authorization Server 1.5.x (Servlet stack). When using Spring Security 7.x with built-in Authorization Server support, verify against the APIs of your actual version.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish `azp` (*Authorized Party*), `acr` (*Authentication Context Class Reference*), and `amr` (*Authentication Methods References*).
2. Understand these claims in relation to `iss`, `sub`, `aud`, `nonce`, `auth_time`, `iat`, and `exp` of an **OIDC ID Token**.
3. Explain the issuance and verification rules for `azp` without confusing it with audience or client authorization.
4. Design an `acr` vocabulary agreed upon by the OpenID Provider (OP) and Relying Party (RP), without inferring it from user roles.
5. Use `amr` values registered in IANA/RFC 8176 with accurate semantics.
6. Distinguish `acr_values`, `claims.id_token.acr` with `essential:true`, `max_age`, and `prompt`.
7. Design authentication evidence, step-up, and MFA so claims only reflect **actually succeeded** authentication events.
8. Customize ID Tokens via `OAuth2TokenCustomizer<JwtEncodingContext>` in Spring Authorization Server.
9. Verify ID Tokens and enforce `acr`, `amr`, and `auth_time` at the RP per policy.
10. Test scenarios involving multiple audiences, client mismatches, stale authentication, refresh tokens, and missing MFA evidence.

**Key message:** `azp` identifies the ID Token's **authorized party**; `acr` identifies the **achieved authentication context class**; `amr` lists **the methods actually used**. They do not replace JWT signatures, issuer, audience, nonce, access tokens, or application authorization checks.

## 2. An ID Token Is an Assertion About Authentication

OIDC adds an identity layer on top of OAuth 2.0. In the Authorization Code + PKCE Flow:

1. The RP sends an Authorization Request containing `scope=openid`.
2. The OP authenticates the End-User and handles consent/authorization.
3. The RP exchanges the authorization code at the Token Endpoint.
4. The RP receives an ID Token carrying assertions about the user/authentication event, plus an access token for the Resource Server.
5. The RP validates the ID Token, establishes an application session, and evaluates assurance/freshness requirements.
6. When calling APIs, the RP uses the **access token**, not the ID Token.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as End-User
    participant RP as OIDC Client / RP
    participant OP as OpenID Provider / Spring AS
    participant API as Resource Server

    U->>RP: Sign in
    RP->>OP: Authorization Code + PKCE + nonce
    OP->>U: Login and MFA if policy requires
    U-->>OP: Authentication proof
    OP->>OP: Verify, record auth_time/acr/amr
    OP-->>RP: Authorization code
    RP->>OP: Exchange code at Token Endpoint
    OP-->>RP: ID Token and access token
    RP->>RP: Verify ID Token and authentication claims
    RP->>API: Authorization: Bearer access token
    API->>API: Check scope and business permissions
~~~

### 2.1. Core Claims

| Claim | Meaning | Requirement |
| --- | --- | --- |
| `iss` | Issuer of the OP | REQUIRED |
| `sub` | Subject identifier of the End-User | REQUIRED |
| `aud` | Audience; must contain the RP's `client_id` | REQUIRED |
| `exp` | Expiration time of the ID Token | REQUIRED |
| `iat` | Time the token was issued | REQUIRED |
| `nonce` | Binds the ID Token to the Authentication Request | Required when request contained `nonce` |
| `auth_time` | Time the End-User actually authenticated | Required when `max_age` or Essential `auth_time` is requested |
| `azp` | Authorized party | OPTIONAL |
| `acr` | Satisfied authentication context class | OPTIONAL |
| `amr` | Authentication methods used | OPTIONAL |

The absence of `acr`/`amr` **does not by default** make an ID Token invalid under OIDC. However, if the RP requires a specific assurance class, their absence may require the RP to reject the operation/login per policy.

### 2.2. What an ID Token Might Contain

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-4831",
  "aud": ["booking-bff"],
  "exp": 1893457200,
  "iat": 1893456300,
  "auth_time": 1893456210,
  "azp": "booking-bff",
  "acr": "urn:example:acr:mfa",
  "amr": ["pwd", "otp"]
}
~~~

This is only an example; Spring Authorization Server does not automatically assert `acr=mfa` or `amr=["pwd","otp"]` without corresponding authentication policy/evidence. `urn:example:acr:mfa` is an illustrative internal value, not a global standard assurance level.

### 2.3. Authentication Is Not Authorization

| Component | What Does It Prove? | What Does It Not Prove? |
| --- | --- | --- |
| `sub` | Subject authenticated by the OP | Permissions on specific bookings |
| `azp` | Authorized party per OIDC/profile | User admin role |
| `acr` | Satisfied assurance class | Scopes to call APIs |
| `amr` | Methods performed | Freshness, authority, or ownership |
| `scope` in access token | Permissions granted in OAuth2 grant | That user just completed MFA |
| Verified roles/permissions | Permissions per business policy | Valid token audience/signature |

Even after the user completes MFA, the Resource Server still must check permissions on each object/tenant. Conversely, an access token with `booking.read` does not prove the End-User logged in within the last 5 minutes.

## 3. azp — Authorized Party

### 3.1. Definition

Per OpenID Connect Core 1.0, `azp` is an **OPTIONAL** claim. If present, it **MUST** contain the OAuth 2.0 `client_id` of the authorized party to which the ID Token was issued. The value is case-sensitive and represented as a JSON string.

OIDC Core notes that `azp` usually appears when implementing extensions beyond Core scope; systems without such an extension are advised not to emit `azp` arbitrarily.

### 3.2. azp Differs From aud and sub

| Claim | Represents | Example |
| --- | --- | --- |
| `sub` | End-User | `user-4831` |
| `aud` | List of ID Token audiences; must include RP `client_id` | `["booking-bff"]` |
| `azp` | Authorized party when declared | `booking-bff` |

For a single RP:

~~~json
{
  "aud": "booking-bff",
  "sub": "user-4831"
}
~~~

This can be a valid ID Token even **without `azp`**.

With a multi-audience extension:

~~~json
{
  "aud": ["booking-bff", "partner-rp"],
  "azp": "booking-bff",
  "sub": "user-4831"
}
~~~

The RP must:

1. Verify `aud` contains the RP's own `client_id`.
2. Reject tokens containing additional audiences the RP does not trust.
3. If `azp` is present, apply validation per the extension's contract/profile.
4. For simple profiles, typically check `azp == client_id`; never skip `aud` validation.

**Spec note:** Do not state that "OIDC Core mandates `azp` for every ID Token with multiple `aud` values." Under Core incorporating Errata Set 2, `azp` remains OPTIONAL; detailed validation when an extension emits `azp` depends on that extension, and the RP should verify a trusted authorized party per contract.

### 3.3. azp Does Not Indicate User Permissions

If:

~~~json
{
  "aud": "booking-bff",
  "azp": "booking-bff",
  "sub": "user-4831"
}
~~~

you **cannot infer** that the user may view another tenant's bookings or holds admin privileges. `azp` is neither `scope` nor `roles`.

### 3.4. Do Not Take azp From Raw HTTP Parameters

Wrong example:

~~~java
// Wrong: unverified client_id from request.
String azp = request.getParameter("client_id");
claims.claim("azp", azp);
~~~

If an extension requires `azp`, obtain it from the authenticated OAuth2 Client:

~~~java
String clientId = context.getRegisteredClient().getClientId();

// Only when extension/profile applies and audience is valid:
// context.getClaims().claim("azp", clientId);
~~~

Do not add the claim simply because a `clientId` variable exists. Emitting `azp` requires an explicit policy and consistency checks with `aud`.

## 4. acr — Authentication Context Class Reference

### 4.1. acr Identifies an Authentication Class

`acr` is **OPTIONAL**, a JSON string. It identifies the Authentication Context Class satisfied by the actual authentication event.

Example organization-defined values:

| Example ACR | Internal Definition |
| --- | --- |
| `urn:example:acr:password` | User logged in under password policy |
| `urn:example:acr:mfa` | User completed multiple independent factors per MFA policy |
| `urn:example:acr:phishing-resistant` | User used a mechanism verified by the OP to meet anti-phishing policy |

These strings **do not carry a universal standard assurance level**. The RP and OP must agree on their meaning, profile, factor requirements, session lifetime, and policy version. If using an ACR from an external standard, do not redefine its meaning ad hoc.

### 4.2. acr Is Not a Numeric Score

Do not compare ACRs as strings:

~~~java
// Unsafe: lexicographical order is not guaranteed.
if (acr.compareTo("urn:example:acr:mfa") >= 0) {
    approveSensitiveAction();
}
~~~

If the OP defines an assurance hierarchy, create an **explicit, versioned** mapping. For example:

~~~java
Map<String, Integer> policyLevels = Map.of(
    "urn:example:acr:password", 1,
    "urn:example:acr:mfa", 2,
    "urn:example:acr:phishing-resistant", 3);
~~~

This is only an illustrative mapping once an **audited policy engine** has established that relationship. Never assume every hardware key or OTP method automatically equates to a high-tier ACR.

### 4.3. Why Not Compute acr by Counting amr Entries?

`amr=["pwd","otp"]` may indicate two methods, yet it still depends on:

- Did the OP verify the OTP successfully?
- Do the two steps represent **two independent factors**?
- Were the authenticators pre-registered/verified?
- Is there phishing resistance, device binding, or origin binding?
- Is the session fresh enough for the sensitive transaction?
- Is there a weaker recovery/fallback path that lowers assurance?

The OP must evaluate all evidence and policy before placing `acr` into the ID Token. Never emit `acr=mfa` simply because the RP sent `acr_values=mfa`.

### 4.4. acr Equal to "0"

OIDC Core defines `acr="0"` when End-User authentication **does not meet ISO/IEC 29115 Level 1**. Do not assume `"0"` means "anonymous user" across all systems.

When choosing ACR values, you may use absolute URIs or registered names per profile, and never use a registered name with a meaning contrary to its standard.

### 4.5. acr and scope Are Different

`acr` describes the assurance of **Authentication**; `scope` describes the boundaries of **Authorization**.

A user who signed in with MFA may still lack `booking.write`. A user with `booking.read` may view ordinary data yet still be required by policy to step up before changing a bank account number.

## 5. amr — Authentication Methods References

### 5.1. Definition

`amr` is **OPTIONAL**, a JSON array of strings naming the methods used during authentication. Values are case-sensitive.

For example:

~~~json
{"amr":["pwd","otp"]}
~~~

It describes which methods occurred; it **does not by itself assert an assurance class** or grant permissions.

### 5.2. Values From RFC 8176 / IANA

| Value | Interpretation |
| --- | --- |
| `pwd` | Password-based authentication |
| `otp` | One-Time Password |
| `mfa` | Multiple-Factor Authentication |
| `sms` | Confirmation via SMS |
| `hwk` | Proof-of-Possession of a hardware-protected key |
| `swk` | Proof-of-Possession of a software-protected key |
| `fpt` | Fingerprint biometric |
| `face` | Facial biometric |
| `pin` | PIN/pattern |
| `sc` | Smart card |
| `user` | User presence check |
| `rba` | Risk-Based Authentication |
| `kba` | Knowledge-Based Authentication |
| `tel` | Confirmation via telephone call |

IANA maintains the registry; custom values such as `"webauthn"` or `"push"` require explicit OP/RP agreement and must not be claimed as RFC 8176-defined values.

### 5.3. amr Is Not a Chronological Audit Log

~~~json
{"amr":["pwd","otp","mfa"]}
~~~

This does not mean element positions represent timestamps or the formal order of challenges. If you need proof that an MFA step-up happened after initial sign-in, store event timestamps and transaction bindings server-side rather than inferring from array order.

### 5.4. amr and Authentication Assurance

- `amr=["sms"]` does not by itself prove MFA.
- `amr=["pwd","pwd"]` is not two factors.
- `amr=["hwk"]` is insufficient to infer phishing resistance without knowing the authenticator/protocol.
- `amr=["fpt"]` may describe local device user verification, not necessarily a fingerprint processed directly by the OP.
- `amr=["mfa"]` is an assertion about MFA under the OP's policy, requiring trust in the issuer and its issuance process.

An OP might emit:

~~~json
{
  "acr": "urn:example:acr:password",
  "amr": ["pwd"]
}
~~~

or after actually completing MFA:

~~~json
{
  "acr": "urn:example:acr:mfa",
  "amr": ["pwd", "otp", "mfa"]
}
~~~

Never construct the latter combination if the authentication challenge has not succeeded.

## 6. auth_time, iat, and Session Freshness

### 6.1. Three Timestamps to Keep Separate

- `auth_time`: when the End-User actually authenticated.
- `iat`: when the ID Token was issued.
- `exp`: when the ID Token expires.

~~~json
{
  "auth_time": 1893456000,
  "iat": 1893459600,
  "exp": 1893460200
}
~~~

An ID Token can be issued an hour after the authentication event. Therefore, a freshly signed ID Token does not mean the user just signed in again.

### 6.2. When Is auth_time Required?

Per OIDC Core, `auth_time` must be present:

- When the RP sends the `max_age` parameter.
- When the RP requests `auth_time` as an Essential Claim.

Otherwise `auth_time` is OPTIONAL.

Never insert `auth_time=Instant.now()` at the Token Endpoint merely to populate the claim when only a refresh token or old session was used.

### 6.3. max_age and Reauthentication

~~~text
GET /oauth2/authorize?response_type=code
  &client_id=booking-bff
  &scope=openid%20profile
  &max_age=300
  &code_challenge=...
  &code_challenge_method=S256
~~~

This request is wrapped across lines for readability; a real request must include `redirect_uri`/`state`/`nonce` per policy and be properly URL-encoded.

`max_age=300` requires an authentication event within at most 300 seconds. When the session is older, the OP must trigger reauthentication. `max_age=0` forces fresh authentication per OIDC semantics. The OP returns `auth_time` so the RP can evaluate freshness.

### 6.4. prompt=login and prompt=none

- `prompt=login` asks the OP to prompt for reauthentication.
- `prompt=none` forbids UI interaction. If the user needs MFA/reauthentication that cannot happen silently, the OP returns an error such as `login_required` or `interaction_required` per flow.
- `max_age` requires freshness and `auth_time`; never substitute `iat`.

Never emit `acr=mfa` to "satisfy" a `prompt=none` request that cannot be fulfilled.

### 6.5. Refreshing an ID Token Does Not Refresh Authentication

OIDC may issue a new ID Token when using a refresh token, depending on profile/flow. In that case:

- `iat` reflects when the new token was issued.
- `auth_time`, if present, must reflect the **original authentication** time.
- Refreshing does not perform fresh MFA.
- `acr`/`amr` must not be upgraded without a new verified authentication event.

If an RP requires user MFA within the last 5 minutes, an ID Token newly re-issued from an old refresh token **does not satisfy** that requirement merely because `iat` is recent.

## 7. acr_values, the claims Parameter, and Essential Claims

### 7.1. acr_values Is a Preference Request

~~~text
acr_values=urn:example:acr:mfa urn:example:acr:password
~~~

`acr_values` is a space-separated string in order of preference. The OP is **asked** to consider those values when processing the Authentication Request, but `acr_values` requests `acr` as a **Voluntary Claim**, not an Essential Claim.

The RP must not assume that simply sending `acr_values=mfa` guarantees the user completed MFA. It must check the actual `acr` in the verified ID Token.

### 7.2. Requesting Essential ACR via the claims Parameter

If the OP supports the `claims` request parameter, the RP can send the following JSON (URL-encoded in the actual request):

~~~json
{
  "id_token": {
    "acr": {
      "essential": true,
      "values": [
        "urn:example:acr:mfa",
        "urn:example:acr:phishing-resistant"
      ]
    },
    "auth_time": {
      "essential": true
    }
  }
}
~~~

Per OIDC Core, when `acr` is an Essential Claim with specific `values`:

- The OP **MUST** return an `acr` matching one of the requested values if it supports the `claims` parameter.
- The OP **MAY** ask the End-User to reauthenticate with additional factors.
- If the requirement cannot be met, the OP **MUST** treat it as an authentication failure.
- The RP must still verify the returned value, never trusting the request alone.
- Essential `auth_time` makes `auth_time` mandatory in the ID Token.

**Do not assume** Spring Authorization Server 1.x implements all `claims`/Essential ACR semantics and step-up workflows automatically. Verify your version/extensions and integrate an authentication policy.

### 7.3. Do Not Send Conflicting ACR Requests Simultaneously

OIDC Core notes that combining `acr_values` with an individual `acr` request via `claims` specifying a `values` list has unspecified/non-standardized behavior. Pick one request mechanism per your OP/RP contract and always verify the outcome.

### 7.4. Decision Table

| Parameter | Purpose | Consequence If Unmet |
| --- | --- | --- |
| `acr_values` | Preferred ACRs, voluntary | RP decides based on actual result |
| `claims.id_token.acr.essential=true` | Requires an ACR from the listed set | An OP supporting `claims` must satisfy it or fail authentication |
| `claims.id_token.auth_time.essential=true` | Requires authentication timestamp | ID Token must include `auth_time` |
| `max_age` | Caps maximum age of authentication event | OP reauthenticates when needed; returns `auth_time` |
| `prompt=login` | Requests re-login | Does not prove MFA; still check claims |
| `prompt=none` | Disallows interaction | Returns error if interactive reauth/step-up is needed |

## 8. Case Study: Step-Up Before a Sensitive Action

Suppose a BFF app lets users view bookings after password login, but requires MFA to edit payment details.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as End-User
    participant BFF as Booking BFF
    participant OP as OpenID Provider
    participant S as Server-side Evidence Store

    U->>BFF: Sign in
    BFF->>OP: OIDC Authorization Code + PKCE
    OP->>U: Password login
    U-->>OP: Valid password
    OP->>S: auth_time, amr=pwd, acr=password
    OP-->>BFF: ID Token acr=password
    BFF->>BFF: Allow regular session
    U->>BFF: Request payment account change
    BFF->>OP: Step-up request + Essential acr=mfa + max_age
    OP->>U: MFA challenge
    U-->>OP: Valid second factor
    OP->>S: Record completed MFA evidence
    OP-->>BFF: ID Token acr=mfa, amr=pwd+otp
    BFF->>BFF: Verify token, acr, auth_time, and permissions
    BFF-->>U: Allow to proceed if business authorization passes
~~~

This is a **target architecture**, not a feature turned on automatically by calling `OidcConfigurer` or adding a `JwtEncodingContext` customizer.

### 8.1. If the User Already Has an MFA Session

The OP may reuse the authentication context if policy permits and `auth_time` is fresh enough. If MFA is too old or policy requires reauthentication, the OP must run a fresh step-up/reauthentication.

### 8.2. If the Challenge Fails

- Do not upgrade `acr`.
- Do not add `amr=["pwd","otp","mfa"]` as though OTP succeeded.
- Do not issue an ID Token claiming Essential ACR compliance.
- Apply appropriate OIDC error responses, rate limiting, and auditing.

### 8.3. If the RP Does Not Use Essential ACR

If the RP only sends `acr_values=mfa` (voluntary), the OP might not fulfill it completely. The RP must inspect `acr` itself and block sensitive actions if assurance is insufficient.

## 9. Enabling OIDC in Spring Authorization Server

### 9.1. OIDC Configurer

SAS 1.5.x example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurity(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server ->
            server.oidc(Customizer.withDefaults()))
        .authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated());

    return http.build();
}
~~~

This is a fragment: the application still needs an application `SecurityFilterChain` for Resource Owner login, `RegisteredClientRepository`, `OAuth2AuthorizationService`, issuer/JWK signing, and other beans. The OIDC UserInfo Endpoint requires separate JWT/Resource Server configuration depending on setup and version.

### 9.2. Registering a Client for OIDC and PKCE

~~~java
RegisteredClient bookingBff = RegisteredClient.withId("booking-bff-id")
    .clientId("booking-bff")
    .clientSecret(passwordEncoder.encode(secretFromSecureConfig))
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(
        AuthorizationGrantType.AUTHORIZATION_CODE)
    .authorizationGrantType(
        AuthorizationGrantType.REFRESH_TOKEN)
    .redirectUri(
        "https://app.example.test/login/oauth2/code/booking")
    .scope("openid")
    .scope("profile")
    .clientSettings(ClientSettings.builder()
        .requireProofKey(true)
        .requireAuthorizationConsent(true)
        .build())
    .build();
~~~

This is a registration snippet; `passwordEncoder` and `secretFromSecureConfig` come from dependency injection/secret management—never hardcode credentials. Registering `openid` does not verify MFA or guarantee `acr`/`amr` will appear.

### 9.3. JwtEncodingContext Is Where Claims Are Customized

In Spring Authorization Server, `JwtGenerator` can accept an `OAuth2TokenCustomizer<JwtEncodingContext>`.

~~~java
if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
    // Customize access token for Resource Server.
} else if (OidcParameterNames.ID_TOKEN.equals(
        context.getTokenType().getValue())) {
    // Customize ID Token for Relying Party.
}
~~~

`OidcParameterNames` is in package `org.springframework.security.oauth2.core.oidc`. Never blindly add `acr/amr/azp` to every JWT access token when you only intend to customize the ID Token.

## 10. Storing Verified Authentication Evidence

### 10.1. Why Is an Evidence Store Needed?

The user signs in at the Authorization Endpoint, whereas the ID Token is typically minted when the client exchanges the code at the Token Endpoint. Those two requests may use different connections, different server instances, and occur at different times.

Merely reading the `acr_values` request parameter at the Token Endpoint only reflects the RP's wish—**it does not prove the user passed MFA**.

Illustrative internal record:

~~~java
import java.time.Instant;
import java.util.List;

public record VerifiedAuthenticationEvidence(
    String subject,
    Instant authenticatedAt,
    String acr,
    List<String> amr
) {
}
~~~

This is an application-defined model, not a built-in SAS class.

### 10.2. Trustworthy Sources of Evidence

| Data Source | Usable? | Condition |
| --- | --- | --- |
| Successful password authentication event at OP | Yes | OP actually verified credentials |
| Successful MFA challenge with transaction binding | Yes | Independent factor verified per policy |
| Server-side authentication/authorization store | Yes | Properly bound to user/session/client/auth request |
| Unprocessed HTTP `acr_values` | **No** | Only a request preference |
| `X-MFA: true` header from the internet | **No** | Can be spoofed |
| Self-reported user profile field | No | Does not prove authentication method |
| `Instant.now()` when Token Endpoint issues token | No for `auth_time` | Not the authentication time |
| Refresh token grant | No for new MFA | No user challenge occurred |

### 10.3. Evidence Must Be Bound to the Right Event

Production should store:

- User subject + authentication event ID.
- Session/authorization transaction binding and appropriate client/tenant context.
- Timestamp when the user actually authenticated.
- Factors that passed verification, with MFA challenge IDs containing no secrets.
- ACR computed by the policy engine after successful authentication.
- Assurance policy version and appropriate retention/TTL.

Never store a global `lastAcrByUserId` and reuse it across all sessions of a user. Doing so could let an MFA-authenticated session A cause a password-only session B to receive an inflated assurance claim.

## 11. Controlled Customization Code for acr/amr/auth_time

### 11.1. Application-Implemented Service Contract

~~~java
import java.util.Optional;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;

public interface AuthenticationEvidenceService {

    // Return only verified evidence for the exact principal,
    // session, and authorization transaction in context.
    Optional<VerifiedAuthenticationEvidence> findVerifiedFor(
        JwtEncodingContext context);
}
~~~

Implementations must query a trusted server-side store, never directly reading HTTP bodies or untrusted headers.

### 11.2. Customizing the ID Token in a Single Bean

~~~java
import java.util.List;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.oidc.OidcParameterNames;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Configuration
class OidcClaimsConfig {

    @Bean
    OAuth2TokenCustomizer<JwtEncodingContext> oidcClaimsCustomizer(
            AuthenticationEvidenceService evidenceService) {

        return context -> {
            if (!OidcParameterNames.ID_TOKEN.equals(
                    context.getTokenType().getValue())) {
                return;
            }

            Optional<VerifiedAuthenticationEvidence> evidence =
                evidenceService.findVerifiedFor(context);

            if (evidence.isEmpty()) {
                // Never fabricate auth_time/acr/amr. If Essential ACR
                // or max_age is required, policy must reject the flow
                // BEFORE issuing the ID Token.
                return;
            }

            VerifiedAuthenticationEvidence verified = evidence.get();

            if (verified.authenticatedAt() != null) {
                context.getClaims().claim(
                    "auth_time",
                    verified.authenticatedAt().getEpochSecond());
            }

            if (verified.acr() != null && !verified.acr().isBlank()) {
                context.getClaims().claim("acr", verified.acr());
            }

            if (verified.amr() != null && !verified.amr().isEmpty()) {
                context.getClaims().claim(
                    "amr",
                    List.copyOf(verified.amr()));
            }
        };
    }
}
~~~

`AuthenticationEvidenceService` and `VerifiedAuthenticationEvidence` are application-implemented components. This is **not** a complete OIDC application and **does not** generate MFA challenges. You must add an authentication policy engine capable of handling step-up/Essential ACR before issuing authorization codes/ID Tokens.

### 11.3. Adding azp per Extension

If an extension requires `azp` and audience policy has been checked, it can be added inside the same customizer:

~~~java
if (profileRequiresAuthorizedParty
        && OidcParameterNames.ID_TOKEN.equals(
            context.getTokenType().getValue())) {

    String authorizedClientId =
        context.getRegisteredClient().getClientId();

    context.getClaims().claim("azp", authorizedClientId);
}
~~~

`profileRequiresAuthorizedParty` is the result of server configuration/policy, not a client-supplied variable. Do not define a second customizer bean of the same type just to add `azp`; use explicit composition/wiring.

### 11.4. Do Not Overwrite Standard Claims

Never arbitrarily alter:

- `iss`: OP issuer.
- `sub`: user subject (never replace with email).
- `aud`: ID Token audience, which must include client ID.
- `nonce`: binds the authentication request when present.
- `iat`/`exp`: timestamps per protocol/token policy.

A claim customization mistake can produce an ID Token that is **validly signed yet protocol-invalid**.

### 11.5. When Configuring DelegatingOAuth2TokenGenerator Manually

When you do not configure a custom generator, SAS can autodetect an `OAuth2TokenCustomizer<JwtEncodingContext>` bean and attach it to `JwtGenerator`. If you construct a delegating bean yourself, wire it explicitly:

~~~java
JwtGenerator jwtGenerator = new JwtGenerator(jwtEncoder);
jwtGenerator.setJwtCustomizer(oidcClaimsCustomizer);

OAuth2TokenGenerator<?> generator =
    new DelegatingOAuth2TokenGenerator(
        jwtGenerator,
        new OAuth2AccessTokenGenerator(),
        new OAuth2RefreshTokenGenerator());
~~~

This fragment assumes `jwtEncoder` and `oidcClaimsCustomizer` beans already exist. Keep the appropriate access/reference/refresh generators rather than leaving only `JwtGenerator`. With multiple customizers of the same generic type, use explicit composition or qualifiers.

## 12. acr Policy Must Run Before Issuing the ID Token

`JwtEncodingContext` should only reflect **actual verified authentication outcomes**. If `acr` is an Essential Claim and the OP cannot satisfy it, the flow must fail at the authentication/policy layer.

~~~mermaid
flowchart TD
    REQ["OIDC Authorization Request<br/>acr_values / claims / max_age"]
    POLICY["Authentication Policy Engine"]
    EXIST{"Session meets assurance<br/>and freshness?"}
    STEP["Password / MFA / Step-up"]
    PASS{"Authentication passed?"}
    EVID["Verified Evidence Store"]
    AUTHZ["Authorization Code / Consent"]
    JWT["JwtGenerator + JwtEncodingContext"]
    IDT["ID Token"]
    ERR["OIDC authentication error"]

    REQ --> POLICY --> EXIST
    EXIST -->|"Yes"| EVID
    EXIST -->|"No"| STEP --> PASS
    PASS -->|"Yes"| EVID
    PASS -->|"No"| ERR
    EVID --> AUTHZ --> JWT --> IDT
~~~

Important:

1. `acr_values` is a request preference, not an outcome.
2. Essential ACR must never be faked by a customizer.
3. `max_age` requires reauthentication and real `auth_time`.
4. `prompt=none` must never silently bypass challenges requiring user interaction.
5. Evidence must bind to the exact subject/client/authorization transaction.
6. If required evidence is missing, **never** issue an ID Token with fabricated claims; fail properly in the flow.

## 13. RP Verification of azp, acr, amr, and auth_time

### 13.1. Step 1: Core ID Token Validation

Before reading authentication claims, the RP uses an OIDC library to:

- Verify signature/alg/key from the trusted issuer per flow.
- Confirm `iss` matches the OP issuer.
- Confirm `aud` contains the RP's `client_id` and no untrusted additional audiences.
- Confirm `exp` is unexpired; `iat` is reasonable given clock skew.
- Confirm `nonce` matches the request if sent, with replay protection.
- Verify hash claims `at_hash`/`c_hash` when required by flow/profile.

If any mandatory check fails, never use `acr`/`amr` to "rescue" the token.

### 13.2. Step 2: Check azp If Present

Pseudocode:

~~~java
// idToken has already had its signature, iss, and aud verified.
if (!idToken.audiences().contains(clientId)) {
    throw new AuthenticationFailure("Audience mismatch");
}

if (idToken.hasClaim("azp")) {
    String authorizedParty = idToken.getStringClaim("azp");

    if (!authorizedPartyPolicy.allows(clientId, authorizedParty)) {
        throw new AuthenticationFailure("Untrusted azp");
    }
}
~~~

`authorizedPartyPolicy` represents the extension/OP/RP contract. For simple profiles, the rule is typically `authorizedParty.equals(clientId)`, without skipping the audience check.

### 13.3. Step 3: Check ACR

~~~java
Set<String> acceptedAcrs = Set.of(
    "urn:example:acr:mfa",
    "urn:example:acr:phishing-resistant");

if (!acceptedAcrs.contains(idToken.getStringClaim("acr"))) {
    throw new StepUpRequiredException();
}
~~~

This is RP pseudocode after token verification; it does not represent a full OpenID client library. Never compare ACRs alphabetically or by Unicode order; policy must explicitly list allowed classes.

### 13.4. Step 4: Check AMR When Required

If business rules require a specific method, the RP may inspect `amr` per its OP contract. However:

- Some OPs omit `amr` even when authentication is valid.
- `pwd` and `otp` do not by themselves prove phishing resistance.
- `mfa` depends on trusting the OP's policy.
- If `amr` is missing, the RP must have clear fail/fallback/step-up rules.
- `amr` does not replace `acr`/freshness checks for sensitive actions.

### 13.5. Step 5: Check auth_time

~~~java
Instant authenticatedAt =
    Instant.ofEpochSecond(idToken.getLongClaim("auth_time"));

Duration maxAge = Duration.ofMinutes(5);

if (authenticatedAt.isAfter(now.plus(allowedClockSkew))) {
    throw new AuthenticationFailure("Invalid auth_time");
}

if (authenticatedAt.isBefore(
        now.minus(maxAge).minus(allowedClockSkew))) {
    throw new StepUpRequiredException();
}
~~~

`now` and `allowedClockSkew` are configured by the RP. `max_age` checks rely on `auth_time`, not `iat`. Clock skew should never be set so wide as to defeat freshness guarantees.

## 14. Do Not Use an ID Token as an Access Token

| Attribute | OIDC ID Token | OAuth2 Access Token |
| --- | --- | --- |
| Recipient | RP / OIDC Client | Resource Server |
| Purpose | Authentication result, identity info | Authorization for APIs |
| Audience | RP's client ID | Resource/audience per token policy |
| `azp`/`acr`/`amr` | When profile/flow applies | Only when a separate access-token profile/contract requires |
| `scope` | Not a source of API permissions | Used per authorization grant |
| Usage | RP verifies and manages login session | Client sends as Bearer or sender-constrained token |

Wrong:

~~~http
GET /api/bookings HTTP/1.1
Host: api.example.test
Authorization: Bearer ID_TOKEN_VALUE
~~~

The Resource Server must reject an ID Token used in place of an access token per API security policy, even if the OP signature is valid and the ID Token has `acr=mfa`.

### 14.1. UserInfo and sub

If the RP calls the OIDC UserInfo Endpoint, it must verify that `sub` in the UserInfo response matches `sub` in the ID Token. Never use matching `amr` values as a substitute for subject consistency.

`email_verified` is metadata about an email address, **not** proof of MFA authentication.

## 15. Related Extended Authentication Claims

| Claim / Parameter | Role | Note |
| --- | --- | --- |
| `auth_time` | Time of user authentication | Distinct from `iat` and required with `max_age` |
| `nonce` | Anti-replay / binds ID Token to request | Exact-match if request included nonce |
| `at_hash` | Truncated access token hash in certain OIDC flows | Requirement depends on flow |
| `c_hash` | Truncated authorization code hash in Hybrid Flow | Not a signature on the code |
| `sid` | Session ID per OIDC session/logout extensions | Not identical to raw HTTP session ID |
| `email_verified` | Whether OP verified the email | Does not equate to MFA |
| `updated_at` | Time profile was updated | Not login time |
| `acr_values` | Preferred ACR reference request | Not achieved ACR |
| `claims` | Individual claim requests | Essential ACR has specific semantics |
| `prompt` | Controls OP interaction | Does not by itself yield strong authentication |
| `max_age` | Requires sufficiently recent auth | Requires `auth_time` |

`at_hash` and `c_hash` carry different obligations across Authorization Code, Implicit, and Hybrid Flows. With modern Code + PKCE, never add arbitrary claims without checking the profile.

## 16. Case Studies

### 16.1. Password Suffices for Routine Operations

~~~json
{
  "aud": "booking-bff",
  "sub": "user-4831",
  "auth_time": 1893456000,
  "acr": "urn:example:acr:password",
  "amr": ["pwd"]
}
~~~

The BFF can establish a regular session, still checking scopes/permissions when calling APIs.

### 16.2. Successful MFA for Sensitive Operations

~~~json
{
  "aud": "booking-bff",
  "sub": "user-4831",
  "auth_time": 1893456600,
  "acr": "urn:example:acr:mfa",
  "amr": ["pwd", "otp", "mfa"]
}
~~~

The RP treats assurance as sufficient only after verifying the ID Token and confirming policy accepts the ACR/freshness. The API must also check permission to modify the target object.

### 16.3. RP Requests MFA but OP Does Not Satisfy It

If only `acr_values=mfa` (voluntary) was sent, the OP may return `acr=password`. The RP itself must trigger step-up or fail the operation.

If the OP supports `claims` and the RP requests an Essential ACR from a specific set, the OP must satisfy it or fail authentication; never sign an ID Token claiming MFA if OTP failed.

### 16.4. ID Token With Multiple Audiences

~~~json
{
  "aud": ["booking-bff", "untrusted-rp"],
  "azp": "booking-bff"
}
~~~

The RP `booking-bff` must not accept this merely because `azp` matches; untrusted additional audiences must be rejected per ID Token validation.

### 16.5. Refreshing an ID Token After 60 Minutes

~~~json
{
  "auth_time": 1893456000,
  "iat": 1893459600,
  "acr": "urn:example:acr:mfa",
  "amr": ["pwd", "otp"]
}
~~~

`auth_time` still describes the original authentication. A policy requiring MFA within 5 minutes must never rely on the fresh `iat`.

### 16.6. Hardware Key Alone Does Not Prove Policy

~~~json
{
  "amr": ["hwk", "user"]
}
~~~

Do not automatically infer `acr=phishing-resistant`. The OP must verify policy rules on authenticator, user verification, origin binding, and anti-phishing criteria.

## 17. Security Pitfalls and Preventions

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating `azp` as `aud` | Token substitution/mix-up | Always validate `aud`, plus `azp` per profile |
| Always emitting `azp` without an extension | Redundant/contract-breaking claim | Add only when genuinely required |
| Treating `acr_values` as MFA proof | OP asserts false assurance | Separate requests from verified evidence |
| Counting `amr` entries as factor count | MFA false positives | Evaluate factor independence and policy |
| Setting `auth_time=iat` on refresh | Old session looks "fresh" | Preserve original auth event timestamp |
| Using `email_verified` to imply MFA | False assurance | Rely on successful authentication events |
| Reading `X-MFA` from untrusted proxy headers | Claim spoofing | Strip/verify headers; use server-side evidence |
| Storing only `lastAcrByUserId` | Assurance bleeds across sessions | Bind evidence to transaction/session/client |
| Checking `acr` while skipping signature | Forged token can claim MFA | Verify the ID Token first |
| Using ID Token to call Resource Server | Wrong token audience/type | APIs accept only access tokens |
| Treating `OidcConfigurer` as an MFA engine | No real step-up | Implement login/MFA challenge policies yourself |
| Ignoring Essential ACR | Violates OIDC contract | Fail authentication if unmet |
| Comparing ACRs as strings | Broken policy enforcement | Explicit versioned mapping |
| Assuming OTP/SMS is phishing-resistant | Overclaimed assurance | Evaluate authenticators per policy |
| Not testing ID Token refresh | Stale `auth_time` or false assurance bump | Test preservation of auth context |

## 18. Test Matrix

| Scenario | Setup | Expected Result |
| --- | --- | --- |
| OIDC Code + PKCE login | Scope `openid`, valid client | ID Token has `iss`/`sub`/`aud`/`iat`/`exp` |
| `azp` absent | Profile not requiring `azp` | RP does not reject solely because `azp` is absent |
| `azp` present and valid | Extension requires it | RP accepts per contract |
| `azp` mismatch | Value differs from client ID | RP rejects per policy |
| Audience lacks client | ID Token for another RP | RP rejects |
| Untrusted extra audience | `aud` includes another client | RP rejects |
| Password only | Login with `pwd` only | Never emits `acr=mfa` |
| OTP success | MFA challenge passes | `amr`/ACR reflect evidence |
| OTP failure | Challenge fails | Does not elevate `acr`/`amr` |
| Voluntary `acr_values` | OP does not fulfill | RP evaluates actual `acr` |
| Essential ACR | OP supports `claims` | Succeeds with matching class or fails authentication |
| Unsupported `claims` parameter | OP lacks support | Do not assume Essential ACR works automatically |
| `max_age` in request | Stale session | Reauth triggered; ID Token includes `auth_time` |
| `prompt=none` needing MFA | Cannot complete silently | OIDC error |
| `auth_time` differs from `iat` | Token issued after login | Real auth time preserved |
| Refresh ID Token | Refresh grant enabled | `auth_time` keeps original authentication meaning |
| User has two sessions | One MFA session, one password | Evidence never mixes |
| Custom `amr` claim | Unregistered value | Contract exists or RP handles unknown safely |
| ID Token as Bearer at RS | Wrong token type sent | RS rejects |
| OIDC UserInfo | Has `sub` | `sub` matches ID Token |
| Signature tamper | Modified JWT | RP rejects |
| Issuer mismatch | Different OP issuer | RP rejects |
| Nonce mismatch | Differs from request | RP rejects |
| Clock skew | Slight time offset | Governed by bounded skew policy |
| Sensitive PII | Token leaks secrets/excess PII | Test catches regression |

### 18.1. Testing Claims with a Real JwtDecoder

~~~java
@Test
void idTokenContainsVerifiedMfaEvidence() {
    Jwt idToken = jwtDecoder.decode(actualIdTokenValue);

    assertThat(idToken.getAudience()).contains("booking-bff");
    assertThat(idToken.getClaimAsString("acr"))
        .isEqualTo("urn:example:acr:mfa");
    assertThat(idToken.getClaimAsStringList("amr"))
        .contains("pwd", "otp");
    assertThat(idToken.getClaim("auth_time"))
        .isNotNull();
}
~~~

This is an illustrative test body; you must supply `jwtDecoder`, an ID Token issued with test keys, assertion libraries, and real fixtures. Decoding alone only proves the token carries claims and passes decoder signature/issuer checks; **it does not prove MFA actually occurred**. End-to-end challenge tests are required.

### 18.2. Verifying Access Tokens Remain Unaffected

When the same flow issues both an ID Token and an access token:

- The ID Token carries `acr/amr/auth_time` per verified evidence.
- The access token does not automatically inherit ID Token authentication claims unless the RS profile requires them.
- ID Token `aud` is the RP client ID.
- Access token `aud` follows Resource Server policy.
- `iss/sub/nonce/exp` are not overwritten.
- If a custom generator is provided, the customizer remains wired and refresh/reference generators are intact.

### 18.3. End-to-End Step-Up and Refresh Tests

1. Login with password: receive password ACR.
2. Request Essential ACR MFA: OP enforces step-up.
3. Wrong OTP: MFA ACR is not issued.
4. Valid OTP: evidence store records method and ACR.
5. RP validates ACR/freshness and proceeds only when policy passes.
6. Later, refresh the ID Token: `auth_time` is not replaced with `iat`.
7. Request `max_age=0`: OP enforces reauthentication.
8. Test two concurrent sessions for the same user: evidence from one session never bleeds into the other.

## 19. Operations and Auditing

### 19.1. Governing the ACR Vocabulary

Each ACR needs versioned documentation covering:

- Stable string/URI value, never reused with a different meaning.
- Accepted methods/factors.
- Device, authenticator, and phishing-resistance requirements.
- Maximum freshness and reauthentication rules.
- Session/evidence binding and storage retention.
- Fallback, recovery, and step-up rules.
- Migration plan when multiple RPs depend on the same class.
- Security review and regression tests before changing semantics.

Never abruptly change the meaning of `urn:example:acr:mfa` without assessing every RP relying on that claim.

### 19.2. Monitoring

| Metric | Goal |
| --- | --- |
| ID Token issuance count by ACR | Track assurance shifts |
| MFA success/failure | Observe authentication challenges |
| Requested ACR vs. satisfied ACR | Detect OP/RP mismatches |
| Essential ACR failures | Policy unmet |
| `max_age` reauthentication count | Monitor freshness enforcement |
| `auth_time` missing when required | OIDC contract regression |
| `azp` mismatch | Token audience/client mix-up |
| Unknown `amr` values | OP/RP contract drift |
| Refresh `auth_time` anomalies | Detect `auth_time` resets |
| Step-up denied after policy pass | Inspect business authorization |

Never log raw ID Tokens, OTPs, private keys, session cookies, client secrets, biometric details, or authenticator secrets. Audits only need correlation IDs, policy versions, verified client IDs, protected subject identifiers, and outcomes.

### 19.3. Runbook When an RP Reports Insufficient MFA

1. Verify the ID Token's signature, issuer, audience, and nonce first.
2. Read `acr`, `amr`, and `auth_time` from the verified token.
3. Check whether the RP requested `acr_values` (voluntary) or Essential ACR via `claims`.
4. Confirm whether the OP/version supports that request mechanism.
5. Inspect successful authentication events and the evidence store at the OP.
6. Verify evidence binds to the right subject, session, client, and authorization transaction.
7. For `max_age`, inspect actual `auth_time` and clock skew.
8. For refresh flows, verify `auth_time` was not reset to `iat`.
9. Check the RP's ACR allowlist and any extra AMR rules.
10. Run integration tests; never "fix" this by hardcoding `acr=mfa` in the token customizer.

## 20. Self-Check Questions

**Question 1:** How do `azp` and `aud` differ?  
**Answer:** `aud` specifies the ID Token's audiences, which must include the RP's client ID. `azp` is the authorized party and is OPTIONAL; when present, it must hold the OAuth2 Client ID per applicable semantics.

**Question 2:** Does missing `azp` always make an ID Token invalid?  
**Answer:** No. `azp` is OPTIONAL in OIDC Core unless required by a specific extension/profile.

**Question 3:** Can `acr` be computed by counting `amr` elements?  
**Answer:** No. `acr` is a policy/context class; `amr` only describes methods actually used.

**Question 4:** Does `amr=["pwd","otp"]` necessarily prove strong MFA?  
**Answer:** No. The OP must verify factor independence, challenge outcome, authenticator properties, and policy.

**Question 5:** Does `acr_values` force the OP to return the first listed ACR?  
**Answer:** No; it is a voluntary preference-ordered request.

**Question 6:** What happens if Essential ACR is not satisfied?  
**Answer:** On an OP supporting the `claims` parameter, an Essential ACR with requested values must be met or the flow must fail authentication.

**Question 7:** How do `auth_time` and `iat` differ?  
**Answer:** `auth_time` is when the user authenticated; `iat` is when the ID Token was issued.

**Question 8:** Does refreshing an ID Token refresh `auth_time`?  
**Answer:** No; `auth_time`, if present, reflects the original authentication.

**Question 9:** Does a `JwtEncodingContext` customizer enable MFA by itself?  
**Answer:** No; it only attaches claims. MFA requires login challenges, a policy engine, and verified evidence.

**Question 10:** Can an ID Token be used to call APIs instead of an access token?  
**Answer:** No. ID Tokens are for the RP, not for Resource Servers.

**Question 11:** Can an RP skip checking `aud` because `azp` matches?  
**Answer:** No. Audience, issuer, signature, expiration, and nonce checks remain mandatory per profile.

**Question 12:** Can `acr` be taken directly from an HTTP request?  
**Answer:** No. The request expresses what the RP wants; the claim must come from authentication evidence verified by the OP.

## 21. Production Checklist

- [ ] RP/OP understand `azp`, `acr`, `amr`, and their applicability accurately.
- [ ] ID Tokens are signed/verified with valid `iss/sub/aud/iat/exp`.
- [ ] RP verifies signature, issuer, audience, and nonce before reading claims.
- [ ] `azp` is emitted/checked only per extension/profile, never replacing `aud`.
- [ ] ACR vocabulary is documented, versioned, and policy-tested.
- [ ] ACR is confirmed by authentication policy, never copied from `acr_values`.
- [ ] AMR records succeeded methods, using IANA names where appropriate.
- [ ] MFA/phishing resistance is never inferred purely from `amr` count or names.
- [ ] `acr_values` is treated as voluntary.
- [ ] Essential ACR is enforced when the OP supports the `claims` parameter.
- [ ] `max_age` triggers OP reauthentication when needed with real `auth_time`.
- [ ] `auth_time` is preserved from the authentication event, never set to `iat`.
- [ ] Refreshing an ID Token never elevates assurance or spoofs `auth_time`.
- [ ] Evidence is bound to user/session/client/authorization transaction.
- [ ] `JwtEncodingContext` customizer affects only `ID_TOKEN`.
- [ ] Standard claims are not overwritten and secrets/OTP/PII are not leaked.
- [ ] ID Tokens are never used as API access tokens.
- [ ] Tests cover MFA success/failure, `acr` mismatch, multi-audience, refresh, and multiple sessions.
- [ ] Safe metrics/auditing and diagnostic runbooks are in place.

## 22. Official References and Conclusion

- [OpenID Connect Core 1.0 — ID Token claims](https://openid.net/specs/openid-connect-core-1_0.html#IDToken)
- [OpenID Connect Core 1.0 — ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation)
- [OpenID Connect Core 1.0 — Authentication Request / acr_values](https://openid.net/specs/openid-connect-core-1_0.html#AuthRequest)
- [OpenID Connect Core 1.0 — Claims Parameter](https://openid.net/specs/openid-connect-core-1_0.html#ClaimsParameter)
- [OpenID Connect Core 1.0 — Requesting the acr Claim](https://openid.net/specs/openid-connect-core-1_0.html#acrRequests)
- [OpenID Connect Core 1.0 — Refreshing an Access Token](https://openid.net/specs/openid-connect-core-1_0.html#RefreshingAccessToken)
- [RFC 8176 — Authentication Method Reference Values](https://www.rfc-editor.org/rfc/rfc8176)
- [IANA Authentication Method Reference Values Registry](https://www.iana.org/assignments/authentication-method-reference-values/)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
- [Spring Authorization Server — Core Model / JwtEncodingContext](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — Protocol Endpoints / OIDC](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)

**Conclusion:** `azp` describes the authorized party, `acr` describes the authentication context class, and `amr` describes the methods used. They help the RP decide when reauthentication or step-up is needed, yet they are only meaningful after the ID Token is verified and backed by trusted OP evidence. In Spring Authorization Server, enforce `acr_values`, Essential ACR, `max_age`, and MFA in the authentication policy layer, and only then reflect verified events into the ID Token via `JwtEncodingContext`. Never infer from requests, never self-elevate assurance, never confuse ID Tokens with access tokens, and test the entire flow end-to-end.
