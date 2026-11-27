# Access Token Issuance, Not-Before, and Expiration Times

In **Spring Security OAuth 2.0 / OIDC Resource Server**, an Access Token has a time-based lifecycle: when it was issued, from when it is allowed to be used, and when it must stop being accepted. Three common JWT claims are **`iat`**, **`nbf`**, and **`exp`**. An OAuth token response can also contain **`expires_in`**, representing the lifetime duration starting from when the Authorization Server generated the response.

These values are not synonymous:

- **`iat` (Issued At):** the time when the token was issued. It indicates the token's age; it does not by itself state when the token becomes valid or when it expires.
- **`nbf` (Not Before):** the earliest time the token is allowed to be accepted. If this claim is present, the token is invalid before that time.
- **`exp` (Expiration Time):** the time when the token is no longer accepted. According to JWT, a token is rejected when the current time is equal to or after `exp`, possibly with a small clock-skew leeway according to policy.
- **`expires_in`:** the lifetime duration returned by the Authorization Server in the token response, in seconds from when the response was generated. It is not a JWT claim and does not replace `exp`.

A token may have already been issued but **not yet reached the time it becomes valid**. A token may also be issued and become valid immediately, then expire at a different timestamp. The Resource Server must validate time according to the token's contract, with synchronized clocks and an explicit clock skew policy.

This lesson belongs to the **Lifecycle and Revocation** chapter, using **Java 17+, Spring Boot 3.x, and Spring Security 6.x**. It covers NumericDate semantics, validity windows, token responses, JWT and opaque tokens, clock skew, `JwtTimestampValidator`, refresh, revocation, in-flight requests, and testing.

## 1. The Three Timestamps in a JWT

A JWT Access Token may contain:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "person-42",
  "aud": ["orders-api"],
  "iat": 1893452400,
  "nbf": 1893452460,
  "exp": 1893456000,
  "scope": "orders.read"
}
~~~

The numeric time values are **NumericDate**: the number of seconds since the Unix epoch (1970-01-01T00:00:00Z), not Java milliseconds.

~~~text
UTC Time ------------------------------------------------------------->

        iat                    nbf                      exp
         |                      |                        |
         v                      v                        v
---------+----------------------+------------------------+-------->
       Issued               Allowed to use            Expired

      Token exists          Token may be              Token must be
      but not yet active    accepted                  rejected
~~~

If a token has both `nbf` and `exp`, ignoring clock skew, the accepted validity window is:

~~~text
nbf <= now < exp
~~~

If `nbf` is absent, the token does not declare a not-before boundary; the verifier must still check expiration and other conditions. **`iat` does not replace `nbf`**.

### 1.1. iat: Issued At

`iat` indicates when the token was issued. An application can use it to display token age, investigate whether a token was issued before or after a security incident, enforce a maximum age policy, or apply a minimum-issued-at/epoch to invalidate older tokens per user/tenant.

However, `iat` **does not determine when the token starts being accepted**. If `iat` is 10:00 and `nbf` is 10:05, the token still cannot be used before 10:05. A token with an older `iat` is also not necessarily expired if `exp` is still in the future and policy does not restrict token age.

### 1.2. nbf: Not Before

`nbf` (Not Before) is the timestamp before which the token **must not be accepted**:

~~~json
{
  "iat": 1893452400,
  "nbf": 1893452700,
  "exp": 1893456000
}
~~~

The token was created at `iat`, but can only start being used at `nbf`. Before that time, the JWT validator must reject the token under the not-before rule. Use cases may include tokens prepared ahead of a rollout or access that begins at a scheduled time.

Do not add `nbf` to every token unnecessarily if the system does not need it; the more timestamps included, the more strictly clocks and semantics must stay consistent between the AS and RS.

### 1.3. exp: Expiration Time

`exp` is the timestamp after which the token is no longer accepted. According to RFC 7519, a JWT must not be accepted **on or after** the expiration time, except for a small leeway that parties may agree upon to handle clock skew.

~~~json
{
  "iat": 1893452400,
  "exp": 1893456000
}
~~~

The token may have been issued and usable since `iat`, but must be rejected when the verifier's clock reaches `exp`, subject to the leeway policy.

`exp` is the upper time bound of the token; a token can still lose validity earlier if the Authorization Server revokes the token/grant, the user/client/tenant is disabled, the signing key is revoked, introspection returns `active:false`, or the Resource Server applies a denylist/token epoch.

**Expiration and revocation are two different causes.** A token that has not yet reached `exp` can still be rejected because it was revoked.

## 2. How Does expires_in Differ from exp?

An OAuth 2.0 token response typically contains:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "orders.read"
}
~~~

`expires_in` is **the number of seconds the token remains valid**, counted from when the response was generated according to RFC 6749. It is metadata in the token response, not a JWT claim.

| Value | Form | Meaning |
| --- | --- | --- |
| `iat` | Absolute NumericDate | When the token was issued. |
| `nbf` | Absolute NumericDate | When the token is allowed to start being used. |
| `exp` | Absolute NumericDate | When the token expires. |
| `expires_in` | Duration in seconds | Lifetime advertised by the AS in the token response. |

If a JWT token has `exp`, the Resource Server uses that absolute claim during verification. The client can use `expires_in` to schedule a refresh; never fabricate `exp` by modifying the token.

### 2.1. Computing Expiration Time from expires_in

Suppose the AS generates the response at 10:00:00 and returns `expires_in: 600`. The expiration time according to this information is around 10:10:00. The client receives the response after network latency; if it computes **response-received time + 600 seconds**, it may estimate a later time than the actual expiration.

Therefore, the client should start counting from when it receives the response and subtract a safety margin, or use the verified `exp` if it can read the token per the contract. Do not rely on an unsynchronized local clock, and do not use `expires_in` to extend a token after the AS has revoked it.

### 2.2. Token Response and JWT May Not Use the Same Representation

An AS may issue opaque tokens. In that case, the client still receives `expires_in`, but cannot read `exp` from the token itself. The Resource Server calls the introspection endpoint to learn whether the token is active.

A JWT token response can simultaneously contain `expires_in` and a JWT with an `exp` claim. Both values should be consistent per the issuance contract; if there is an unexpected discrepancy, investigate the AS/token profile rather than arbitrarily choosing the longer value.

## 3. Token Validity Window

~~~text
iat = 09:00:00
nbf = 09:05:00
exp = 10:00:00

09:00:00  Issued, but not yet at nbf
09:04:59  Not yet accepted
09:05:00  Allowed to be accepted
09:59:59  Still within validity window
10:00:00  Expired; must be rejected
~~~

The `iat` timestamp indicates when it was issued. If the verifier wants to reject tokens whose `iat` is too far in the future or tokens that are too old, that is an **additional policy** that must be explicitly implemented.

### 3.1. Token Before nbf

If a token is issued before it becomes valid, the Resource Server rejects authentication when a request arrives too early. The client can wait until the allowed time and retry according to policy. It should not retry continuously every few milliseconds; use the not-before time, backoff, and a clock margin.

### 3.2. Token at or Past exp

When a token expires, a JWT Resource Server must reject it based on the timestamp validator; an opaque Resource Server must receive an inactive introspection result or apply a trusted expiration policy. The client needs to obtain a new token through the appropriate refresh/authorization flow. Never modify the `exp` claim or reuse an old token by changing the client-side clock.

### 3.3. Token with Old iat but Distant exp

A token can live a long time if the AS issues a long lifetime. If policy requires that an Access Token must not live longer than 15 minutes, checking only `exp` is insufficient if a token was misconfigured and issued with a multi-hour lifetime. You can additionally enforce:

~~~text
now - iat <= maximumTokenAge
~~~

This is an application **token-age policy**, not a reinterpretation of `exp`. Apply it only if the token profile requires `iat` and clocks are synchronized.

## 4. NumericDate and Conversion in Java

JWT time claims use NumericDate in Unix epoch seconds. Java typically works with `Instant`:

~~~java
import java.time.Instant;

long expSeconds = 1_893_456_000L;
Instant expiresAt = Instant.ofEpochSecond(expSeconds);

long nowSeconds = Instant.now().getEpochSecond();
boolean expired = nowSeconds >= expSeconds;
~~~

**Do not use `Instant.ofEpochMilli(expSeconds)`**: that interprets seconds as milliseconds, throwing the timestamp off drastically.

Converting in the reverse direction:

~~~java
Instant expiresAt = Instant.parse("2030-01-01T01:00:00Z");
long exp = expiresAt.getEpochSecond();
~~~

A JWT NumericDate is an absolute point in time and carries no server timezone. In code, use `Instant` for absolute timestamps, `Duration` for durations, and `Clock` for testing time. Do not use `LocalDateTime.now()` as a source for token expiration decisions because it lacks an offset/zone and easily causes bugs across environments with different timezones.

### 4.1. Clock Abstraction for Testing

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock clock = Clock.fixed(
    Instant.parse("2030-01-01T00:00:00Z"),
    ZoneOffset.UTC);

Instant now = clock.instant();
~~~

A custom service can accept a `Clock` via constructor injection instead of calling `Instant.now()` directly in many places. In tests, advance time using a clock fixture to verify `nbf`/`exp` boundaries.

## 5. Clock Skew: Why Can Two Servers Disagree?

The Authorization Server and Resource Server may have skewed clocks:

~~~text
AS clock:  10:00:00.000
RS clock:  09:59:40.000  (20 seconds behind)
~~~

If a token has `nbf` at exactly 10:00:00 according to the AS, an RS that is 20 seconds behind may think the token is still in the future. Conversely, if the RS is ahead of the AS, the RS may think the token expired early.

**Clock skew/leeway** allows the verifier to tolerate a small difference:

~~~text
accept if:
  now + skew >= nbf
  AND
  now - skew < exp
~~~

This is a general description of timestamp leeway. Variable names and comparison details may differ across libraries; you must understand the exact semantics of the validator you are using.

### 5.1. Leeway Is Not Token Extension

If `exp` is 10:00:00 and the verifier allows 30 seconds of leeway, a request at 10:00:10 may be accepted by that verifier. This **does not change the `exp` claim on the token**, but it causes the Resource Server to accept the token beyond the issued timestamp within the tolerance window.

Choose a small skew based on actual clock measurements; do not set several minutes or hours just to mask clock misconfiguration. Use the same consistent policy across replicas, monitor NTP/clock drift, and account for leeway when designing maximum token lifetime and revocation windows.

### 5.2. The Client Does Not Control Server-Side Leeway

The client may assume the token remains valid for an extra 30 seconds, but the Resource Server does not necessarily use the same leeway. **The server decides whether to accept the token.** The client should refresh early to avoid sending tokens right on the edge of expiration; it has no authority to demand the server accept expired tokens.

## 6. iat Is Not nbf: Separate Issued-At Policies

Some systems need to check `iat`: a token must not be issued in the future beyond clock tolerance, must be newer than a bulk revocation timestamp, or must not exceed the profile's maximum age.

~~~text
iat <= now + allowedClockSkew
now - iat <= maxTokenAge
~~~

Do not assume every JWT contains `iat` or that every profile enforces the same maximum age. **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens** defines profile claims for JWT Access Tokens; a generic JWT may have a different contract.

### 6.1. Minimum Issued-At / Token Epoch

If a user is locked or a refresh-token family is revoked, the application can store:

~~~text
user.minimumTokenIssuedAt = 2030-01-01T10:00:00Z
~~~

When verifying a token, if `iat` is earlier than this timestamp, reject it. This can invalidate a group of older tokens before `exp` without storing every individual `jti`. However, the state must be stored in a trusted source, synchronized across replicas, scoped by user/client/tenant, compared against `iat` only after JWT validation succeeds, and paired with clear semantics for tokens missing `iat`.

This is **an additional revocation policy**, not an automatic function of `iat`.

## 7. Spring Security: Checking exp and nbf with JwtTimestampValidator

A Spring Security JWT Resource Server uses `JwtDecoder` to verify JWTs. Timestamp validation can be performed by `JwtTimestampValidator`, which checks time claims such as `exp` and `nbf` according to the clock-skew policy.

Example Servlet Resource Server configuration:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtSecurityConfiguration {

    private static final String ISSUER =
        "https://identity.example.test";

    private static final String JWK_SET_URI =
        "https://identity.example.test/oauth2/jwks";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(JWK_SET_URI).build();

        JwtTimestampValidator timestamps =
            new JwtTimestampValidator(Duration.ofSeconds(30));

        OAuth2TokenValidator<Jwt> issuer =
            new JwtIssuerValidator(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        OAuth2ErrorCodes.INVALID_TOKEN,
                        "Required audience is missing",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                timestamps,
                issuer,
                audience));

        return decoder;
    }
}
~~~

In this example, `JwtTimestampValidator` applies a 30-second clock skew; `JwtIssuerValidator` checks the configured issuer; the audience validator ensures the token is intended for `orders-api`; and `NimbusJwtDecoder` verifies the signature using the trusted JWK Set URI.

**Note:** the example uses a static JWKS URI for illustration. In production, issuer/JWKS must come from trust configuration; never read URIs from the JWT header or the request. When using `JwtValidators.createDefaultWithIssuer`, the default validators already include timestamp validation; if you need custom clock skew, configure the validators explicitly as shown above, avoiding accidentally applying two timestamp validators with different policies.

### 7.1. iat Needs Its Own Validator if Policy Requires It

`JwtTimestampValidator` focuses on expiration/not-before; if the system wants to restrict issued-at in the future or enforce a maximum age, add a dedicated validator:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

Clock clock = Clock.systemUTC();
Duration allowedSkew = Duration.ofSeconds(30);
Duration maximumAge = Duration.ofMinutes(15);

OAuth2TokenValidator<Jwt> issuedAtValidator = jwt -> {
    Instant issuedAt = jwt.getIssuedAt();
    Instant now = clock.instant();

    if (issuedAt == null
            || issuedAt.isAfter(now.plus(allowedSkew))
            || issuedAt.isBefore(now.minus(maximumAge))) {
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                OAuth2ErrorCodes.INVALID_TOKEN,
                "Issued-at time violates token age policy",
                null));
    }

    return OAuth2TokenValidatorResult.success();
};
~~~

This is an **illustrative policy validator**, not mandatory for all Access Tokens. If used, it must be wired into the decoder's `DelegatingOAuth2TokenValidator`. Only require `iat` when the token profile mandates that claim; otherwise, clearly define how to handle tokens missing `iat`.

### 7.2. Timestamp Validation Must Happen Before Authorization

An expired JWT or one before `nbf` must not become an authenticated principal and only fail later during scope checks. The timestamp validator runs in the decode/authentication path; invalid tokens fail before the authorization filter.

## 8. Opaque Access Token: Introspection Determines Active Status

Opaque tokens do not contain claims readable by the Resource Server. Instead, the RS calls the Authorization Server:

~~~http
POST /oauth2/introspect HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Authorization: Basic RESOURCE_SERVER_CREDENTIALS

token=OPAQUE_ACCESS_TOKEN
~~~

Response:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "sub": "person-42",
  "exp": 1893456000,
  "iat": 1893452400,
  "nbf": 1893452460,
  "aud": ["orders-api"]
}
~~~

The AS is responsible for evaluating token status and returning `active`. If the token has expired according to the AS, the response must reflect inactive. The RS does not decode the opaque string itself to infer `exp`.

### 8.1. Spring Boot Configuration

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://identity.example.test/oauth2/introspect
          client-id: orders-resource-server
          client-secret: SECRET_FROM_SECRET_MANAGER
~~~

Spring Security uses an opaque-token introspector to build the principal/authorities from the response. **`active:true` is an authentication condition; it does not replace audience/scope/domain authorization**.

### 8.2. Introspection Response and Time

If the AS returns `active:true` while `exp` has already passed according to the RS clock, review AS/RS clocks, leeway, NumericDate seconds, metadata caches, and the `active` contract. Do not alter the response or force active to true. For opaque tokens, the AS is the source of truth for token state; if a local maximum-age or audience policy is needed, implement an explicit adapter validator based on trusted metadata.

### 8.3. Introspection Caching and Expiration

If caching positive introspection results, the TTL must not exceed:

~~~text
min(
  configuredPositiveCacheTtl,
  exp - now - safetyMargin
)
~~~

If there is no reliable `exp` in metadata, use a TTL compliant with the approved revocation policy or do not cache positive results. Even before `exp`, the AS can revoke a token early; caching `active` can create a stale window. **Expiration is not a substitute for revocation.**

## 9. Access Token Expiration and Refresh

Clients typically need to refresh an Access Token before expiration to avoid failed requests:

~~~text
Access Token issued
        |
        v
Use token
        |
        +------------------------------+
        |                              |
        v                              v
Approaching exp                  Token revoked
        |                              |
        v                              v
Refresh/reauthorize              Refresh may fail / grant invalid
        |                              |
        v                              v
New Access Token                 Re-authentication or error handling
~~~

### 9.1. Refresh Before exp, Not at the Last Second

The client should apply a safety margin:

~~~text
refreshAt = expiresAt - refreshMargin
~~~

For example, if a token has a 10-minute lifetime, the client can start refreshing earlier by an interval suited to system latency and reliability. Account for network latency to the AS, token endpoint load/latency, clock skew, request duration, retry budget, Refresh Token rotation, and concurrency.

If multiple concurrent requests detect that a token is about to expire, use a single-flight mechanism or an authorized client manager to avoid a refresh stampede.

### 9.2. expires_in Is a Client Hint; the Server Still Validates

A client may think a token is still alive based on a timer, but the server always validates the token. If the client sends an expired token, the Resource Server rejects it. If the client forgets to refresh, the request fails; that is not a reason for the Resource Server to relax `exp`.

### 9.3. Refresh Tokens Have Their Own Lifecycle

Refresh Tokens may have their own expiration, rotation, reuse detection, and revocation policies. When refresh succeeds, the AS may issue a new Access Token with new `iat`/`exp` and replace the Refresh Token according to the rotation policy. The client must store the new tokens securely and discard old ones per the contract. Do not assume the old Access Token is automatically revoked on every AS.

## 10. Expiration vs. Revocation

| Property | Expiration | Revocation |
| --- | --- | --- |
| Cause | Reached the `exp` timestamp. | AS/admin/user/security policy revoked it early. |
| Predictable in advance? | Yes, from the token's timestamps. | Not necessarily. |
| Detected offline by JWT? | Yes, via timestamp validation. | No, unless an online/denylist/epoch mechanism exists. |
| Opaque introspection | AS returns inactive upon expiration. | AS returns inactive once revocation is visible. |
| New token needed? | Yes, refresh/reauthorization. | Usually requires a new token after access is re-granted. |

An Access Token can be revoked at 10:02 even if `exp` is 10:10. If the Resource Server only checks JWT signature and expiration offline, it may continue accepting the token until 10:10. That is the trade-off of self-contained JWTs and must be addressed according to revocation requirements.

### 10.1. Minimum Lifetime and Maximum Lifetime

The AS may enforce policies for maximum Access Token lifetime per client/resource, shorter lifetimes for sensitive privileges, when a grant is active, and token revocation when a user/client/tenant is disabled. The Resource Server can additionally enforce maximum token age or a revocation epoch, provided policies are aligned with the AS.

## 11. Requests Started Before exp but Finishing After exp

~~~text
10:00:00.000  Request starts
10:00:00.020  JWT exp validation succeeds
10:00:00.100  Domain transaction starts
10:00:01.000  Token exp
10:00:02.000  Transaction commits
~~~

JWT timestamp validation typically occurs during authentication at the start of the request. A token expiring **after authentication has already succeeded** does not automatically abort an in-flight transaction. If business requirements also need to bound execution time, re-check account/tenant/token state at commit or domain boundaries, bound request/job duration, design idempotent side effects, and define policies for WebSockets/SSE/background jobs.

Do not confuse **token expiration** with **automatically canceling all previously authenticated work**.

## 12. ID Tokens and Access Tokens Have Separate Lifetimes

In OIDC, an **ID Token** and an **Access Token** are two distinct token types. The ID Token informs the client/Relying Party of the user's authentication result; the Access Token is intended for the Resource Server to access APIs.

Both may contain `iat` and `exp`, but you must not use the ID Token's expiration to infer that the Access Token is still alive, nor use an ID Token in place of an Access Token for API calls.

~~~text
ID Token:
  aud = web-client
  exp = 10:15

Access Token:
  aud = orders-api
  exp = 10:05
~~~

A web session may still exist after the Access Token expires, and the client can refresh the token according to policy. Conversely, a valid ID Token does not prove that the Access Token is still valid.

## 13. Testing Time Validation in Spring Security

Timestamp tests should verify boundary conditions:

| Test case | Expectation |
| --- | --- |
| `now < nbf` outside clock skew | Reject: not yet valid. |
| `now == nbf` | Accepted per not-before boundary and policy. |
| `nbf < now < exp` | Valid timestamp. |
| `now == exp` | Reject per expiration boundary, unless leeway is configured. |
| `now > exp` outside leeway | Reject. |
| `iat` in the future beyond skew | Reject if profile/policy has an issued-at validator. |
| `iat` too old | Reject if a maximum-age policy applies. |
| NumericDate mistaken for milliseconds | Test must catch incorrect conversion. |
| Small clock skew within tolerance | Result matches validator policy. |
| Clock skew exceeding tolerance | Reject. |
| Opaque introspection active=false | Reject. |
| Opaque active cache TTL expired | Re-introspect; do not serve stale result. |

### 13.1. The jwt() Test Helper Does Not Run the Real Timestamp Decoder

~~~java
mockMvc.perform(get("/api/orders/42")
        .with(jwt().jwt(jwt -> jwt
            .claim("scope", "orders.read"))))
    .andExpect(status().isOk());
~~~

The `jwt()` helper creates an already-authenticated test `Authentication`. It **does not prove** that `NimbusJwtDecoder` verified the signature, `exp`, `nbf`, issuer, or audience. Use the helper to test authorization rules; use signed JWT integration tests or test `JwtDecoder` directly to verify timestamp validation.

### 13.2. Testing Timestamp Policy with a Fixed Clock

A small policy class can accept a `Clock` to test boundaries without relying on the real system clock:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public final class TokenTimePolicy {

    private final Clock clock;
    private final Duration skew;

    public TokenTimePolicy(Clock clock, Duration skew) {
        this.clock = clock;
        this.skew = skew;
    }

    public boolean isWithinValidityWindow(
            Instant notBefore, Instant expiresAt) {
        Instant now = clock.instant();
        boolean afterNbf = notBefore == null
            || !now.plus(skew).isBefore(notBefore);
        boolean beforeExp = expiresAt == null
            || now.minus(skew).isBefore(expiresAt);
        return afterNbf && beforeExp;
    }
}
~~~

Test:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class TokenTimePolicyTest {

    @Test
    void acceptsInsideValidityWindow() {
        Clock clock = Clock.fixed(
            Instant.parse("2030-01-01T00:05:00Z"),
            ZoneOffset.UTC);
        TokenTimePolicy policy =
            new TokenTimePolicy(clock, Duration.ZERO);

        assertTrue(policy.isWithinValidityWindow(
            Instant.parse("2030-01-01T00:00:00Z"),
            Instant.parse("2030-01-01T00:10:00Z")));
    }

    @Test
    void rejectsBeforeNotBefore() {
        Clock clock = Clock.fixed(
            Instant.parse("2030-01-01T00:04:59Z"),
            ZoneOffset.UTC);
        TokenTimePolicy policy =
            new TokenTimePolicy(clock, Duration.ZERO);

        assertFalse(policy.isWithinValidityWindow(
            Instant.parse("2030-01-01T00:05:00Z"),
            Instant.parse("2030-01-01T00:10:00Z")));
    }

    @Test
    void rejectsAtExpirationBoundary() {
        Clock clock = Clock.fixed(
            Instant.parse("2030-01-01T00:10:00Z"),
            ZoneOffset.UTC);
        TokenTimePolicy policy =
            new TokenTimePolicy(clock, Duration.ZERO);

        assertFalse(policy.isWithinValidityWindow(
            Instant.parse("2030-01-01T00:00:00Z"),
            Instant.parse("2030-01-01T00:10:00Z")));
    }
}
~~~

This is a **unit test for an illustrative policy**; it does not replace testing Spring's `JwtTimestampValidator` or verifying JWT signatures. Integration tests still require real signed tokens, a real decoder, and explicitly chosen `nbf`/`exp` timestamps.

## 14. Common Configuration Mistakes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Confusing `iat` with the start of validity. | Accepting tokens before `nbf`. | Validate `nbf` separately. |
| Confusing `expires_in` with a JWT claim. | Looking up the wrong field or fabricating `exp`. | Distinguish token responses from token claims. |
| Using `Instant.ofEpochMilli` for NumericDate. | Token times are wildly inaccurate. | Use `Instant.ofEpochSecond`. |
| Not validating `exp`. | Expired tokens continue to be accepted. | Mandatory timestamp validator. |
| Ignoring `nbf`. | Tokens not yet valid are accepted early. | Validate not-before when the claim is present. |
| Setting excessive leeway. | Expired tokens remain accepted for too long. | Small skew; measure actual clock drift. |
| Using `iat` instead of `exp`. | No proper expiration bound. | `exp` determines expiration. |
| Assuming JWT revocation takes effect offline automatically. | Unexpired tokens may still be accepted. | Use introspection/denylist/epoch when needed. |
| Using a client timer as server validation. | Callers can manipulate their clock. | The server validates the token itself. |
| Refreshing right at `exp`. | Requests fail when the AS/network is slow. | Refresh early with margin/jitter. |
| Using an ID Token for API calls. | Wrong token audience/purpose. | Use Access Tokens for resource APIs. |
| Testing only with the `jwt()` helper. | Real decoder timestamp validation goes untested. | Signed JWT/decoder integration tests. |
| Caching opaque active status past `exp`. | Expired tokens may still be accepted. | Cap TTL by expiration and revocation policy. |

## 15. Runbook for Not-Yet-Valid or Expired Tokens

1. **Identify the token type:** JWT Access Token, opaque Access Token, or ID Token.
2. **Verify issuer/resource:** confirm the token is intended for the right API.
3. **Read verified timestamps:** `iat`, `nbf`, `exp`, or `expires_in` according to the contract.
4. **Check units:** NumericDate is in seconds; Java conversions use epoch seconds.
5. **Check clocks:** NTP, timezone assumptions, and drift between AS, gateway, and RS.
6. **Review clock skew:** verify the policy is small enough and consistent.
7. **If before nbf:** the client waits until the valid time rather than retrying aggressively.
8. **If past exp:** refresh/reauthorize via the OAuth flow; do not relax validators to accommodate stale tokens.
9. **If revoked before exp:** investigate revocation state, not just expiration.
10. **If opaque token:** check introspection `active`, cache TTL, and AS visibility.
11. **If offline JWT:** determine whether denylist/epoch/online checks are needed to support early revocation.
12. **Log errors safely:** never log raw tokens or secrets; distinguish `not_yet_valid`, `expired`, `revoked`, `clock_skew`, and `introspection_unavailable` when sufficient information is available.

**Remember:** `iat` tells when the token was issued, `nbf` tells when the token is allowed to start being used, and `exp` defines when the token must stop being accepted. `expires_in` is a duration in the token response, not a JWT claim. Spring Security uses timestamp validation to check JWT times; opaque tokens rely on introspection. Use NumericDate in seconds, synchronize clocks, configure a small clock skew, and refresh before expiration. **A token can be revoked before `exp`, and a request authenticated before expiration is not automatically canceled.**

## References

- [RFC 7519 — JSON Web Token, NumericDate, exp, nbf and iat](https://www.rfc-editor.org/rfc/rfc7519).
- [RFC 6749 — OAuth 2.0 Authorization Framework, expires_in](https://www.rfc-editor.org/rfc/rfc6749).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662).
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009).
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725).
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — JwtTimestampValidator API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtTimestampValidator.html).
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html).
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html).
