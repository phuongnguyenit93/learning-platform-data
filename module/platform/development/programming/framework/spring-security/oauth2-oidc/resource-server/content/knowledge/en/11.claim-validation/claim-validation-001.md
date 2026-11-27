# Checking `exp`, `nbf`, and Choosing Allowed Clock Skew

In a **Spring Security OAuth 2.0/OIDC Resource Server**, a JWT access token should only be accepted within the time window permitted by the Authorization Server. Two key claims are **`exp` (Expiration Time)**, which indicates when the token expires, and **`nbf` (Not Before)**, which indicates the time at which the token becomes valid. The Resource Server must validate these values after verifying the JWT signature using a trusted key.

In a distributed system, the clocks of the Authorization Server, the Resource Server, and different nodes may drift by a few seconds. **Clock skew** (also known as clock leeway) is a small tolerance margin that helps avoid falsely rejecting tokens because clocks are not perfectly aligned. However, this tolerance widens the token acceptance window on **both the `nbf` and `exp` ends**, so choosing it is both a security and an operational decision.

The goal of this lesson is to understand `exp` and `nbf` accurately, distinguish `iat`, handle NumericDate values, configure `JwtTimestampValidator` in Spring Security, and choose a tolerance level suited to the access token TTL and actual clock synchronization conditions.

## 1. Where Does Time Validation Sit in a Resource Server?

~~~text
Client sends Authorization: Bearer <JWT>
              |
              v
Spring Security Resource Server
              |
              +-- Verify JWS signature with trusted key
              |
              +-- Validate issuer (iss)
              |
              +-- Validate audience (aud)
              |
              +-- Check exp: has the JWT expired?
              |
              +-- Check nbf: is the JWT valid yet?
              |
              +-- Validate other profile/business claims
              |
              +-- Map scopes to authorities
              |
              +-- Enforce endpoint and resource authorization
              |
              v
          200 / 401 / 403
~~~

The `exp` and `nbf` timestamps read from a JWS JWT payload can be viewed using a Base64URL decoder. However, **being able to read a claim does not mean the claim is trustworthy**. A sender could craft JSON with an `exp` far in the future. Only a properly configured JWT decoder/verifier can rely on those claims to make an authentication decision.

For example, a token with a valid signature that is expired must still be rejected. A token that has not expired yet but has the wrong `aud` must also be rejected. A valid token with the right audience can still be rejected with `403` due to missing scopes or insufficient permissions on a specific record.

## 2. `exp`: When the Token Expires

RFC 7519 defines `exp` as the expiration time on or after which the JWT **MUST NOT be accepted for processing**. Without considering clock skew, the current time must be **strictly before** `exp`.

Example:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 2000000300
}
~~~

`exp=2000000300` is an **absolute timestamp**, not "the token has 300 seconds left from the moment the API receives the request". If a client reuses the token after it expires, the `exp` value does not automatically shift to a new time.

A client must not try to extend a token by modifying `exp` in the payload: doing so breaks the JWS signature. To continue accessing the API, the client must obtain a new access token from the Authorization Server through the appropriate OAuth 2.0 flow.

### Exact Boundary at `exp`

According to RFC 7519 semantics, if the current time has reached `exp` exactly, the JWT is no longer valid in a **no-leeway** model. Pay attention to seconds and precision, because code may compare `Instant` at nanosecond resolution while the token uses integer-second NumericDate values.

Do not use rounding or timezone offsets to "fix" an expired `exp`. Any tolerance must be an explicitly configured policy.

## 3. `nbf`: When the Token Becomes Valid

RFC 7519 defines `nbf` as the time **before which the JWT MUST NOT be accepted for processing**. Without clock skew, the current time must be **greater than or equal to** `nbf`.

Example:

~~~json
{
  "sub": "alice",
  "nbf": 2000000060,
  "exp": 2000000300
}
~~~

Ideal validity window:

~~~text
                 Not yet valid         Valid             Expired
time -------------------|==================|----------------------->
                       nbf                exp
~~~

A token with `nbf` in the future is a token that **cannot be used yet** under the time policy. For an access token intended for immediate use, the Authorization Server may issue `nbf` equal to or close to the issuance time. Some profiles or providers may omit `nbf`; whether the claim is required depends on your system's contract.

### Do Not Confuse `nbf` with `iat`

`iat` is **Issued At**, the time at which the token was issued. It is not inherently equivalent to the time the token becomes valid. The three claims are distinct:

| Claim | Meaning | Primary Use |
|---|---|---|
| `iat` | Time of issuance | Checking token age, issuance policy, or auditing if needed |
| `nbf` | Time when acceptance begins | Rejecting tokens used too early |
| `exp` | Time when the token expires | Rejecting expired tokens |

If `iat` equals `nbf`, that is the Authorization Server's choice, not because the two claims share the same semantics. Likewise, `iat` is not a substitute for `exp`.

## 4. NumericDate: UTC Seconds, Not Milliseconds

JWT timestamps are represented as RFC 7519 **NumericDate** values: the number of seconds from `1970-01-01T00:00:00Z` UTC as measured by POSIX time, ignoring leap seconds. A NumericDate value may include a fractional part, although many Authorization Servers use integers.

Example:

~~~json
{
  "iat": 2000000000,
  "nbf": 2000000060,
  "exp": 2000000300
}
~~~

Here `exp - iat = 300` seconds, if that reflects how the Authorization Server defines lifetime. Without the `iat` claim, you cannot directly infer the issuance time from `exp` alone.

### Seconds vs. Milliseconds Is a Very Common Bug

JavaScript `Date.now()` returns milliseconds:

~~~javascript
const nowMillis = Date.now();
const nowSeconds = Math.floor(nowMillis / 1000);
~~~

In Java:

~~~java
import java.time.Instant;

long nowSeconds = Instant.now().getEpochSecond();
long expirySeconds = Instant.now()
    .plusSeconds(300)
    .getEpochSecond();
~~~

Do not pass `System.currentTimeMillis()` or `Date.now()` directly as a JWT `exp`. That value is roughly 1,000 times larger than a timestamp in seconds and results in a drastically wrong expiration time.

### Timezones Do Not Affect Expiration

An `Instant` in Java represents an absolute point in time. When displayed in UTC or `Asia/Ho_Chi_Minh`, the clock shown on screen differs by 7 hours, yet both represent the exact same instant.

~~~java
import java.time.Instant;
import java.time.ZoneId;

Instant expiry = Instant.ofEpochSecond(2000000300L);

System.out.println(expiry); // UTC
System.out.println(expiry.atZone(ZoneId.of("Asia/Ho_Chi_Minh")));
~~~

Do not add seven hours to `exp` because the server is hosted in Vietnam. Always compare using `Instant` and `Clock`, not locale-formatted date-time strings.

## 5. Verification Rules Without Tolerance

Notation:

- `now`: the current time at which the Resource Server performs validation;
- `nbf`: the time when validity begins;
- `exp`: the expiration time;
- `S`: the allowed clock skew.

When `S=0`, the RFC semantics are:

~~~text
now >= nbf
now < exp
~~~

With both claims present, the accepted interval is:

~~~text
nbf <= now < exp
~~~

Example with `nbf = T0 + 20 seconds`, `exp = T0 + 180 seconds`:

| Resource Server Time | Meaning |
|---|---|
| `T0` | Not yet valid |
| `T0 + 10 s` | Not yet valid |
| `T0 + 20 s` | Reached `nbf` |
| `T0 + 100 s` | Inside the valid window |
| `T0 + 179 s` | Before `exp` |
| `T0 + 180 s` | Reached `exp` boundary |
| `T0 + 200 s` | Expired |

A timestamp validator must only run **after the token has passed trusted JOSE processing**. If an application reads an unverified payload and trusts `exp` for authorization decisions, an attacker can declare any timestamp they want.

## 6. Why Can Clocks Drift Apart?

Suppose the Authorization Server and two Resource Servers have different clocks:

~~~text
Authorization Server: 10:00:00 UTC
Resource Server A:    09:59:57 UTC
Resource Server B:    10:00:04 UTC
~~~

The AS issues a JWT with `nbf=10:00:00`. When a request arrives at RS A immediately afterward, RS A sees its local time as three seconds earlier than `nbf` and may reject the token, even though the AS issued it for immediate use.

Near expiration, RS B—whose clock is four seconds ahead of the AS—may consider the token expired earlier than expected.

Common causes include:

- NTP/chrony is out of sync or has lost connectivity to a trusted time source.
- The VM/container host suffers from clock drift.
- The system clock was adjusted after startup.
- Multiple geographic regions or nodes have varying synchronization quality.
- Slight request processing and network latency between the AS and RS.

**Clock skew** is designed to absorb such small clock discrepancies. It is not a substitute for OS-level time synchronization and should not be used to mask a node that is several minutes off.

## 7. Clock Skew Affects Both `exp` and `nbf`

Suppose the Resource Server allows a tolerance of `S=30 seconds`.

An approximate interpretation of the check is:

~~~text
now + S >= nbf
now - S < exp
~~~

This has two consequences:

1. A token may be accepted **earlier than `nbf`** within the skew window.
2. A token may be accepted **later than `exp`** within the skew window.

~~~text
                  nbf-S       nbf             exp      exp+S
time ----------------|---------|================|---------|---->
                     |<------- potentially accepted window -->|
                      30s skew                   30s skew
~~~

This illustrates the leeway semantics. Exact boundary comparisons (equal to `exp + S` or `nbf - S`) depend on how the implementation handles equality and precision. In systems with strict timing requirements, verify the behavior of the specific Spring Security version you use.

### Concrete Offset Example

Suppose:

~~~text
nbf = T0 + 60 seconds
exp = T0 + 300 seconds
skew = 30 seconds
~~~

| `now` | Status Considering Timestamp Alone |
|---|---|
| `T0 + 0 s` | 60 seconds before `nbf`: rejected |
| `T0 + 40 s` | 20 seconds before `nbf`: potentially accepted via skew |
| `T0 + 80 s` | Inside valid window |
| `T0 + 280 s` | Inside valid window |
| `T0 + 320 s` | 20 seconds past `exp`: potentially accepted via skew |
| `T0 + 350 s` | 50 seconds past `exp`: rejected |

"Potentially accepted" only refers to **timestamp validation**; the JWT must still have a valid signature, correct issuer, audience, token type, and required permissions.

### Do Not Confuse Leeway with Token Renewal

Tolerance **does not modify `exp` inside the JWT**, does not mint a new token, does not issue a refresh token, and does not perform revocation. It is purely a rule the Resource Server applies when comparing timestamps against its own `Clock`.

## 8. Spring Security Uses `JwtTimestampValidator`

In a Spring Security JWT Resource Server, the primary component that handles `exp` and `nbf` is `JwtTimestampValidator`, an `OAuth2TokenValidator<Jwt>`.

Basic Spring Boot configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
~~~

With standard Resource Server configuration, Spring Security verifies the signature, issuer, and token timestamps. Spring Security documentation specifies a **default clock skew of 60 seconds**. This is the framework's default behavior, **not a mandatory value mandated by RFC 7519**.

`JwtTimestampValidator` provides a constructor accepting a `Duration`:

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

JwtTimestampValidator withThirtySeconds =
    new JwtTimestampValidator(Duration.ofSeconds(30));

JwtTimestampValidator strict =
    new JwtTimestampValidator(Duration.ZERO);
~~~

You can specify the clock used for verification via `setClock(Clock)`:

~~~java
import java.time.Clock;

JwtTimestampValidator validator =
    new JwtTimestampValidator(Duration.ofSeconds(15));

validator.setClock(Clock.systemUTC());
~~~

Using `Clock.systemUTC()` reflects the system clock in UTC; it does not fix NTP drift by itself. In unit tests, you can replace it with `Clock.fixed(...)` to test deterministic instants.

### What If a Claim Is Missing?

In general RFC 7519 JWTs, `exp` and `nbf` are optional claims. An **Authorization Server's access token contract** may require `exp` to always be present; RFC 9068 defines a specific profile for JWT access tokens with required claims.

Do not assume every Spring Security version requires both claims by default. For instance, `JwtTimestampValidator` APIs in Spring Security 7 versions provide dedicated configuration to allow or disallow missing `exp`/`nbf`. If your system requires `exp` to guarantee bounded token lifetimes, **explicitly enforce a required-exp policy**.

## 9. Configuring Custom Tolerance While Keeping Issuer and Audience

If you need to replace the 60-second default with an organization-chosen value, you can build a `JwtDecoder` and attach an explicit validator set.

The following example uses Spring Security Servlet and a trusted JWKS URI to verify signatures; it chooses **20 seconds** purely as an illustrative parameter:

~~~java
package com.example.orders.security;

import java.time.Duration;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtValidationConfig {

    private static final String ISSUER =
        "https://idp.example.com/realms/shop";

    private static final String JWKS_URI =
        "https://idp.example.com/realms/shop/protocol/openid-connect/certs";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(JWKS_URI).build();

        OAuth2TokenValidator<Jwt> timestamps =
            new JwtTimestampValidator(Duration.ofSeconds(20));

        OAuth2TokenValidator<Jwt> issuer =
            new JwtIssuerValidator(ISSUER);

        OAuth2TokenValidator<Jwt> audience =
            new JwtClaimValidator<List<String>>(
                "aud",
                aud -> aud != null && aud.contains("orders-api")
            );

        OAuth2TokenValidator<Jwt> requireExpiry =
            jwt -> jwt.getExpiresAt() != null
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "exp claim is required",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                timestamps,
                issuer,
                audience,
                requireExpiry
            )
        );

        return decoder;
    }
}
~~~

This validator chain clearly enforces:

- `JwtTimestampValidator`: `exp`/`nbf` with a 20-second clock skew.
- `JwtIssuerValidator`: the token must come from a trusted issuer.
- `JwtClaimValidator`: the audience must contain `orders-api`.
- `requireExpiry`: tokens missing `exp` are rejected per the application contract.

**Note:** When you define a custom `JwtDecoder` bean, Spring Boot generally stops auto-configuring the default decoder. YAML properties such as `issuer-uri` and `audiences` may **not automatically apply** to a custom decoder. Moreover, this sample replaces the default validator set with the explicitly declared one: in a real application, you must retain any additional token type/profile checks or validators required by your version, framework, or contract.

### Why Not Append Another Timestamp Validator to the Default Set?

For example:

~~~java
OAuth2TokenValidator<Jwt> validators =
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuerUri),
        new JwtTimestampValidator(Duration.ofSeconds(20))
    );
~~~

`JwtValidators.createDefaultWithIssuer(...)` already includes timestamp validation with the default tolerance. Adding a 20-second validator **does not remove** the existing one; it can cause both to run and create confusion about which skew value is actually taking effect.

When you want to **replace** the timestamp rule, build the validator set to match your requirements, keeping only a single intentional timestamp validator combined with issuer, audience, token type, and any other conditions. Do not drop all validators just to change clock skew.

### Do Not Assume a Spring Boot `clock-skew` Property Exists

Some other frameworks or versions provide a property to adjust leeway, but you should not invent a non-existent property and assume it works. In Spring Security, `JwtTimestampValidator(Duration)` on `JwtDecoder` is the explicit way to configure it. Always check the property list for the exact Spring Boot version you are using.

## 10. Protecting Endpoints After the Token Is Valid

Example filter chain protecting `orders-api`:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

A token with valid timestamps that lacks `SCOPE_orders.write` is still not allowed to POST. Likewise, a JWT with the order-reading scope does not automatically grant access to every other customer's orders; the service must enforce resource-level authorization.

`401 Unauthorized` typically relates to a token that fails authentication, including being expired or not yet valid. `403 Forbidden` typically relates to insufficient permissions after authentication succeeds. The actual HTTP status may depend on error handlers and multi-filter-chain configurations.

## 11. Choosing Clock Skew Based on Actual Clocks and Risk

There is no single standard number of seconds for every system. Your choice should be based on:

1. **Actual measured drift** between the AS and RS nodes via NTP/chrony, not guesswork.
2. **Reasonable buffer** for network latency and minor clock adjustments.
3. **Access token lifetime**: the larger the skew relative to TTL, the less meaningful `exp` becomes in limiting replay.
4. **Operation sensitivity**: payment or privilege-changing APIs may require a tighter acceptance window than ordinary read APIs.
5. **Node count and placement**: account for the node with the worst drift, without using skew to hide severely broken timekeeping.
6. **Revocation and incident response policy**: a locally verified JWT does not automatically know if a token was revoked mid-lifetime.

### Example Scenarios

| System | Considerations |
|---|---|
| Well-synced AS and RS, measured drift only a few seconds | A small tolerance may suffice; monitor NTP continuously |
| Multiple zones with small but fluctuating clock differences | Use a data-backed margin and fix abnormally drifting nodes |
| Short-lived tokens (30–60 seconds) | A 60-second tolerance can be excessive relative to the TTL |
| Tokens lasting tens of minutes, low-sensitivity APIs | Default tolerance can be evaluated, without abandoning monitoring |
| Sensitive operations or fast revocation needs | Minimize clock drift, keep TTL short, consider state checks and dedicated policies |

**Spring Security's 60-second default** is a reference point for framework behavior. Values like 0, 5, 10, 20, or 30 seconds are merely **configuration examples**, not universal prescriptions. Pick the smallest value that fits your observed drift and operational needs.

### Why Not Set Skew to Several Minutes?

If an access token lives for 60 seconds while the RS allows a 180-second skew, the acceptance window stretches far beyond the intended lifetime. If a token is compromised, the replay window lasts longer than expected.

If a node's clock is off by several minutes, you must **fix the time synchronization service** and underlying infrastructure cause. Relaxing validation only masks the failure and weakens the security boundary.

## 12. Deterministic Testing with `Clock.fixed`

Tests that use `Thread.sleep(...)` to wait for token expiration are slow and flaky. `JwtTimestampValidator#setClock` lets you write deterministic tests without waiting in real time.

JUnit 5 example testing **only the timestamp validator logic**, not JWS signature verification:

~~~java
package com.example.orders.security;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class JwtTimestampValidatorTest {

    @Test
    void acceptsTokenSlightlyBeforeNbfWithinLeeway() {
        Instant now = Instant.parse("2026-01-01T00:00:00Z");

        Jwt jwt = Jwt.withTokenValue("unit-test-token")
            .header("alg", "RS256")
            .claim("sub", "alice")
            .notBefore(now.plusSeconds(20))
            .expiresAt(now.plusSeconds(120))
            .build();

        JwtTimestampValidator validator =
            new JwtTimestampValidator(Duration.ofSeconds(30));

        validator.setClock(Clock.fixed(now, ZoneOffset.UTC));

        assertFalse(validator.validate(jwt).hasErrors());
    }

    @Test
    void rejectsTokenExpiredBeyondLeeway() {
        Instant now = Instant.parse("2026-01-01T00:00:00Z");

        Jwt jwt = Jwt.withTokenValue("unit-test-token")
            .header("alg", "RS256")
            .claim("sub", "alice")
            .notBefore(now.minusSeconds(120))
            .expiresAt(now.minusSeconds(40))
            .build();

        JwtTimestampValidator validator =
            new JwtTimestampValidator(Duration.ofSeconds(30));

        validator.setClock(Clock.fixed(now, ZoneOffset.UTC));

        assertTrue(validator.validate(jwt).hasErrors());
    }
}
~~~

The `Jwt` in this test is a synthetic object; the token string is not signed. These tests demonstrate `exp`/`nbf` validation logic and do **not** prove that the Resource Server correctly verifies signatures, issuer, or audience. To verify the full authentication pipeline, write integration tests using a JWT signed with a test key and a correspondingly configured decoder.

Consider testing these cases: token squarely inside the window; earlier than skew; earlier within skew; expired within/beyond skew; missing or mistyped `exp`; `nbf > exp`; nodes with fast/slow clocks; and exact boundary conditions. Such tests help confirm the exact policy of your framework version.

## 13. Multiple Instances May Make Different Decisions

Suppose:

~~~text
Authorization Server: 10:00:00 UTC

orders-rs-1:          09:59:58 UTC
orders-rs-2:          10:00:02 UTC
orders-rs-3:          10:00:48 UTC
~~~

A newly issued token with `nbf=10:00:00` will be evaluated differently across nodes when there is no leeway. However, if only one node is off by 48 seconds, raising skew across the entire system to 60 seconds can hide that node's NTP failure.

The long-term solution is:

- Monitor NTP/chrony and sync status on nodes and VM hosts.
- Investigate nodes with significant clock drift instead of tuning every Resource Server around a broken node.
- Keep skew policies consistent across nodes of the same API to avoid uneven behavior.
- Distinguish clock drift from network latency, JWKS errors, and scope errors in telemetry.

Containers typically share the host kernel's clock. If a pod has the wrong time, you usually need to inspect the **host node** rather than trying to adjust the clock inside individual containers.

## 14. `exp` Does Not Replace Revocation and Logout

A token with a valid `exp` does not mean it **has not been revoked**.

For example:

1. The AS issues a JWT access token valid for 10 minutes.
2. Two minutes later, the user logs out or the account is disabled.
3. The Resource Server only verifies the signature and claims locally, without checking revocation state.
4. The old token can still pass timestamp validation until it expires (plus any configured tolerance).

If near-immediate revocation is required, the system may consider token introspection, a denylist, permission versioning, short TTLs, or other state-checking mechanisms. Clock skew only reconciles small time differences; it **does not check token state at the Authorization Server**.

Similarly, a client cannot extend a token by altering its payload. It must request a new access token using a valid OAuth 2.0 flow.

## 15. Diagnosing Timestamp-Related `401` Errors

| Symptom | Possible Cause | Investigation Steps |
|---|---|---|
| Newly issued token gets 401 for a few seconds, then succeeds | RS clock behind AS, `nbf` appears in the future | Sync NTP, verify `nbf` and skew |
| Nearly expired token gets 401 on one node but passes on another | Clock drift or inconsistent config | Compare clocks and configs across nodes |
| Token past `exp` is still accepted for a few extra seconds | Trailing leeway | Check `JwtTimestampValidator` |
| Token is accepted before `nbf` | Leading leeway | Evaluate skew and activation requirements |
| Unusually large `exp` | Token generator used milliseconds instead of seconds | Check NumericDate format |
| Token missing `exp` is still accepted | Policy does not require the claim or validator allows missing | Add required-exp validation per contract |
| Custom decoder skips issuer/audience checks | Default validators were replaced when configuring skew | Inspect `setJwtValidator` |
| JWT has valid timestamps but still returns 401 | Invalid signature, issuer, audience, or token type | Inspect the full token verification pipeline |
| JWT authenticates successfully but request returns 403 | Missing scope or data-level permission | Check authorities and authorization rules |
| Many requests fail with time errors after deployment | Host NTP/clock issue, new config, or token format change | Inspect metrics by node and release version |

Simple commands on Linux/containers:

~~~bash
date -u
date +%s
~~~

These commands display the machine's current UTC time and Unix seconds. Use infrastructure tooling to inspect NTP offset and sync status. Do not arbitrarily change production clocks manually: system time affects databases, log correlation, schedulers, and TLS certificates.

### Do Not Log Tokens for Debugging

A Bearer JWT is a credential. Avoid logging the raw `Authorization` header or the full JWT. You can log the error type, trace ID, node ID, configured skew value, and non-sensitive diagnostic fields per organizational policy:

~~~text
event=jwt_authentication_failed
path=/api/orders
reason=expired_token
node=orders-rs-2
configuredClockSkewSeconds=20
traceId=75a1...
bearerToken=[REDACTED]
~~~

If you need to inspect timestamp claims of a real token, use secure internal tooling with appropriate access controls. A Base64URL decoder only inspects data and is no substitute for signature verification.

## 16. Practical Scenarios

### Scenario A — AS and RS Differ by 7 Seconds

The AS issues a JWT for immediate use with `nbf` equal to the issuance timestamp. The RS is 7 seconds behind and skew is 0, so the initial request may be rejected. **Resolution:** synchronize the clocks first, then consider a small leeway aligned with observed drift.

### Scenario B — RS Is 45 Seconds Fast

The JWT still has 30 seconds remaining according to the AS clock, but the RS is 45 seconds ahead with a 5-second leeway. The RS may treat the token as expired. **Resolution:** fix clock drift on that node rather than endlessly increasing leeway.

### Scenario C — 30-Second Access Token Lifetime

The AS issues short-lived tokens to reduce replay risk, while the RS still uses a 60-second skew. The tolerance is larger than the lifetime. **Resolution:** align TTL requirements with an appropriately small skew, backed by tight clock synchronization.

### Scenario D — Revoked Token

The JWT has an `exp` in the future, yet the AS has already revoked it. An RS performing purely local verification may still accept it. **Resolution:** design introspection, a denylist, or an appropriate revocation mechanism; `exp` alone does not reflect revocation status.

### Scenario E — Wrong Client Clock

The browser clock is off by 20 minutes, while the AS and RS are properly synced. The client may refresh tokens at suboptimal times, but the RS must still validate against its own trusted clock. Never trust `X-Client-Time` or a request `Date` header as a substitute clock source.

### Scenario F — Developer Attaches Only a Timestamp Validator

~~~java
decoder.setJwtValidator(
    new JwtTimestampValidator(Duration.ofSeconds(15))
);
~~~

This can **replace** all validators currently in use, dropping issuer, audience, or profile validation. You must attach the complete set of validators required by the token contract.

## 17. Misconceptions to Avoid

**"`exp` is the number of seconds a token stays alive."** No. It is an absolute timestamp; lifetime can be derived from the difference between issuance and expiration when those claims are present.

**"`nbf` and `iat` are the same."** No. One states when the token may start being used; the other states when it was issued.

**"In Vietnam, you must add 7 hours to `exp`."** No. NumericDate is an absolute UTC timestamp.

**"Clock skew only extends `exp`."** No. It also allows accepting a token slightly before `nbf`.

**"The 60-second default is an RFC requirement."** No. It is a Spring Security default; the RFC merely permits a small implementation-defined leeway.

**"Increasing skew to several minutes permanently fixes 401 errors on new tokens."** No. You must check clock synchronization and token issuance flows.

**"Adding a `JwtTimestampValidator` to `JwtValidators.createDefaultWithIssuer(...)` definitely overrides the default skew."** No. Both timestamp validators may end up running.

**"Every Spring Boot version has a `jwt.clock-skew` property."** Do not assume that. Use `JwtTimestampValidator` or a property actually documented for your specific version.

**"A JWT missing `exp` is always rejected in every framework version."** No. Check your profile and required-claim configuration.

**"Once the signature is verified, time validation is unnecessary."** Wrong. A signature protects integrity; it does not make a token valid forever.

**"Having `exp` provides instant revocation."** Wrong. An unexpired token can be revoked at the AS without a locally verifying RS knowing.

## 18. Self-Check Questions

**1.** A JWT has `exp=2000000300`. Is this a 300-second TTL starting when the RS receives the token?

> No, it is an absolute NumericDate. The RS compares it against `now` and the configured leeway.

**2.** `nbf` is 12 seconds in the future, and skew is 20 seconds. Can the timestamp validator accept it?

> Yes, due to leeway; however, the signature and all other claims must still be valid.

**3.** A token expired 35 seconds ago, and skew is 20 seconds. Does it pass timestamp validation?

> No, because it is outside the tolerance window.

**4.** Why is a 120-second skew problematic if the access token only lives for 60 seconds?

> A tolerance larger than the lifetime undermines the goal of short-lived tokens and widens the replay window.

**5.** In Spring Security, which component adjusts the tolerance?

> `JwtTimestampValidator(Duration)`, typically configured on `JwtDecoder` alongside the other validators.

**6.** If a node's clock is off by several minutes, should you fix the clock or increase leeway?

> Fix the node's clock/NTP. Leeway should only cover minor drift.

**7.** Why must you verify issuer and audience after customizing `JwtDecoder`?

> Because a custom bean or validator may replace the default configuration. A token with valid timestamps does not necessarily come from a trusted issuer or target your API.

**8.** Can `iat` replace `nbf`?

> No; the two claims serve different purposes.

## 19. References

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): defines `exp`, `nbf`, `iat`, NumericDate, and leeway for handling clock skew.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): claims and requirements for the JWT access token profile.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): JWT verification and security best practices.
- [Spring Security — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): verifying `iss`, `exp`, `nbf`, and custom timestamp validation.
- [Spring Security — JwtTimestampValidator API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtTimestampValidator.html): `Duration`, `setClock`, and timestamp claim handling.
- [Spring Security — JwtValidators API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtValidators.html): default validators.
- [Spring Security — JwtIssuerValidator API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtIssuerValidator.html): issuer validation.
- [Spring Security — NimbusJwtDecoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html): decoder and `setJwtValidator`.
- [Spring Boot — OAuth2 Resource Server](https://docs.spring.io/spring-boot/reference/security/oauth2.html): JWT Resource Server auto-configuration.

When designing a time-validation policy, keep three principles in mind: **the JWT must be verified before trusting `exp`/`nbf`; the Resource Server must have a synchronized clock; and clock skew must be small, chosen based on actual measured drift and token risk**. Choosing leeway well keeps your API reliable without sacrificing the security value of access token expiration.
