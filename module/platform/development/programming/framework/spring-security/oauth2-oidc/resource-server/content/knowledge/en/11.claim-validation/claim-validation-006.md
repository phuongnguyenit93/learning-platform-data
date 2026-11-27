# `JwtTimestampValidator` and Boundary Timestamp Testing

In a **Spring Security OAuth 2.0 Resource Server**, a JWT access token is accepted only when it satisfies security requirements such as signature, issuer, audience, timestamps, and authorization permissions. Three common time claims are **`exp` (Expiration Time)**, **`nbf` (Not Before)**, and **`iat` (Issued At)**. Spring Security provides **`JwtTimestampValidator`** to evaluate a JWT's valid time window while supporting **clock skew**, a tolerance margin for clock drift between the Authorization Server and Resource Server.

Time validation might look like comparing two numbers. Yet when a token expires at the exact moment a request arrives, or misses the allowed boundary by a single nanosecond, choosing **greater than**, **less than**, or **equal to** determines whether the token is accepted or rejected. That is why tests relying on real wall-clock time and `Thread.sleep(...)` are notoriously flaky.

This lesson examines **the semantics and units of time claims**, how `JwtTimestampValidator` evaluates `exp`/`nbf`, configuring clock skew, writing boundary unit tests with `Clock.fixed(...)`, and wiring the validator into `NimbusJwtDecoder` without dropping other security checks. Always verify exact API signatures and equality rules against the **Spring Security version in your project**.

## 1. Where `JwtTimestampValidator` Sits in a Resource Server

A client calls the Orders API:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <access-token>
~~~

For a JWT access token, the Servlet authentication flow looks like this:

~~~mermaid
flowchart TD
    A["Client sends Bearer JWT"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["JwtAuthenticationProvider"]
    C --> D["JwtDecoder / NimbusJwtDecoder"]
    D --> E["Verify signature, algorithm, and trusted key"]
    E --> F["OAuth2TokenValidator<Jwt>"]
    F --> G["JwtTimestampValidator: exp / nbf"]
    F --> H["Issuer / audience / token profile validators"]
    G --> I{"All conditions valid?"}
    H --> I
    I -- "No" --> J["Authentication error: typically 401"]
    I -- "Yes" --> K["JwtAuthenticationToken"]
    K --> L["Authorization: scope, tenant, and object permissions"]
    L --> M["Controller or access denied: typically 403"]
~~~

| Component | Responsibility |
| --- | --- |
| `JwtDecoder` | Decodes, verifies JWS, and invokes configured token validators |
| `JwtTimestampValidator` | Validates `exp` and `nbf` timestamps against a reference clock and clock skew |
| `JwtIssuerValidator` | Verifies the accepted issuer |
| Audience/profile validator | Verifies the token targets this API and matches the expected token profile |
| Authorization rules | Enforces scopes, roles, and permissions on specific resources |

**`JwtTimestampValidator` never issues or refreshes tokens.** When a token fails timestamp checks, the Resource Server rejects the request. Obtaining a new access token is the responsibility of the **OAuth 2.0 Client and Authorization Server**. Likewise, valid timestamps do not mean the user can access every order.

## 2. NumericDate: Prerequisite for Comparing Timestamps

In JWT (RFC 7519), `exp`, `nbf`, and `iat` have type **NumericDate**: a **JSON number representing seconds since the Unix epoch** (`1970-01-01T00:00:00Z`). NumericDate may contain a fractional part, though many Authorization Servers emit integer seconds.

Illustrative JWT Claims Set:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "iat": 1763164800,
  "nbf": 1763164800,
  "exp": 1763165700,
  "scope": "orders.read"
}
~~~

This is a **JSON payload for illustrating claims**, not a validly signed JWT. Base64URL-decoding a payload never replaces JWS verification.

| Claim | Full Name | Meaning |
| --- | --- | --- |
| `exp` | Expiration Time | Time when the JWT ceases to be valid. RFC 7519 states the current time must be **before** `exp` for the token to be valid, possibly with a small leeway |
| `nbf` | Not Before | JWT must not be accepted **before** this timestamp, outside allowed tolerance |
| `iat` | Issued At | Time the token was issued, often used to check token age or custom policies |

NumericDate uses **seconds**, whereas many Java APIs return **milliseconds**:

| Representation | Unit | Example for 2024-01-01T00:00:00Z |
| --- | --- | --- |
| JWT `NumericDate` | Seconds | `1704067200` |
| `Instant.getEpochSecond()` | Seconds | `1704067200L` |
| `Instant.toEpochMilli()` | Milliseconds | `1704067200000L` |
| `Date.getTime()` | Milliseconds | `1704067200000L` |
| `System.currentTimeMillis()` | Milliseconds | A 13-digit value around that era |

If a token issuer puts `System.currentTimeMillis()` into `exp` without converting units, expiration will be drastically wrong. Conversely, reading a NumericDate with `Instant.ofEpochMilli(...)` shifts the timestamp back near 1970 instead of the intended year.

Spring Security normally converts standard time claims on `Jwt` into `Instant`. When reading a verified JWT, prefer:

~~~java
import java.time.Instant;
import org.springframework.security.oauth2.jwt.Jwt;

Instant expiresAt = jwt.getExpiresAt();
Instant notBefore = jwt.getNotBefore();
Instant issuedAt = jwt.getIssuedAt();
~~~

These getters return `null` if the corresponding claim is absent. Avoid `(Long) jwt.getClaims().get("exp")` because the claim may already have been converted to `Instant` rather than `Long`.

## 3. What Is Clock Skew?

Suppose the Authorization Server and Resource Server process a token at the same physical instant, yet the Resource Server's clock is **20 seconds fast**. A token could be rejected prematurely if the API compares `exp` and `nbf` without any margin. NTP synchronization reduces drift but does not eliminate all clock discrepancies and network latency between systems.

**Clock skew** is a tolerance margin `S` applied during comparison. For instance, configuring `Duration.ofSeconds(30)` can:

- Accept a token for a brief period **after nominal `exp`**.
- Accept a token for a brief period **before nominal `nbf`**.

This is purely a verification rule inside the Resource Server. Skew does not alter the JWT, extend the user session, or ask the Authorization Server to mint a new token.

In many Spring Security versions, `JwtTimestampValidator`'s default clock skew is around **60 seconds**. Never assume that exact default holds across all versions or decoder configurations. Whenever you need a deterministic policy, pass an explicit `Duration` to the validator.

**The larger the clock skew, the wider the acceptance window.** A 10-minute skew lets the API accept tokens nearly 10 minutes past nominal expiration. Sync clocks properly, pick a small practical tolerance, and never use skew to mask seconds-vs-milliseconds bugs.

### Do Not Confuse Timezone with Clock Skew

`Instant` represents an absolute UTC point in time. Two machines displaying one in UTC and one in `Asia/Ho_Chi_Minh` still share the exact same `Instant.now()` when their clocks are synchronized. Timezones are purely for display and **do not introduce a seven-hour offset** in JWT NumericDate values.

Therefore, never add or subtract 7 hours from `exp` to "fix" an error. If timestamps appear shifted, fix the `Instant` conversion or OS clock synchronization.

## 4. Comparison Formulas and Boundary Equality

Let:

- `T` = current time from the validator's `Clock`.
- `S` = clock skew duration.
- `E` = `exp` timestamp.
- `N` = `nbf` timestamp.

Common versions of `JwtTimestampValidator` behave equivalently to:

~~~java
Instant now = Instant.now(clock);

boolean expirationFailure =
    expiresAt != null && now.minus(clockSkew).isAfter(expiresAt);

boolean notBeforeFailure =
    notBefore != null && now.plus(clockSkew).isBefore(notBefore);
~~~

This illustrates **one implementation's behavior**, not guaranteed source code for every version. Under that comparison logic:

~~~text
Reject on exp if: T - S > E
Reject on nbf if: T + S < N

Pass exp check if: T - S <= E
Pass nbf check if: T + S >= N
~~~

With `Instant.isAfter(...)` and `Instant.isBefore(...)`, **exact equality does not trigger a failure**. Thus `T - S == E` and `T + S == N` sit right on the valid edge in that implementation.

Understand the difference between that behavior and RFC 7519's phrasing that current time must be **before** `exp`. Versions may differ on exact equality handling. When strict rejection at the exact expiration instant matters, check your version's implementation and lock down expectations with tests.

### Boundary Table With 30-Second Skew

Suppose `T = 2026-11-15T10:00:00Z` and `S = 30 seconds`.

| Claim | Value | Expectation Under `isAfter/isBefore` Logic Above |
| --- | --- | --- |
| `exp` | `09:59:29Z` | **Rejected**, beyond skew |
| `exp` | `09:59:30Z` | **Accepted at boundary** |
| `exp` | `09:59:31Z` | Accepted within skew |
| `exp` | `10:00:00Z` | Accepted under the comparison above |
| `exp` | `10:10:00Z` | Accepted if other conditions hold |
| `nbf` | `10:00:31Z` | **Rejected**, before allowed window after skew |
| `nbf` | `10:00:30Z` | **Accepted at boundary** |
| `nbf` | `10:00:29Z` | Accepted within skew |
| `nbf` | `10:00:00Z` | Accepted |
| `nbf` | `09:50:00Z` | Accepted if other conditions hold |

When a token carries **both `exp` and `nbf`**, both checks must succeed. A token before `nbf` is rejected even if `exp` is far in the future. A token past `exp` is rejected even if `nbf` passed long ago.

### Are Missing Claims Allowed?

In common implementations, `JwtTimestampValidator` validates `exp` and `nbf` **when present**, without always requiring every JWT to carry both. Whether `exp`, `nbf`, or `iat` is mandatory belongs to your token profile and contract.

If an API requires `exp`, add a validator ensuring the claim exists and has a valid type/value. `iat` is not `nbf`; rules capping future `iat` or maximum token age require their own validator.

## 5. Fixing the Clock in Tests

In Java, `java.time.Clock` decouples "now" from the machine's wall clock. Using `Clock.fixed(...)` ensures a test always evaluates the exact instant `T`, unaffected by slow CI runners or scheduling jitter.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

Instant reference = Instant.parse("2026-11-15T10:00:00Z");
Clock fixedClock = Clock.fixed(reference, ZoneOffset.UTC);

JwtTimestampValidator validator =
    new JwtTimestampValidator(Duration.ofSeconds(30));
validator.setClock(fixedClock);
~~~

This uses `setClock(Clock)` when your project's Spring Security version provides it. On versions with a different API, use the matching mechanism instead of relying on real system time in boundary tests.

| Clock | Behavior | When to Use |
| --- | --- | --- |
| `Clock.systemUTC()` | Real advancing wall clock | Production runtime |
| `Clock.fixed(T, ZoneOffset.UTC)` | Always returns `T` | Testing equality, ±1ns, ±1s |
| `Clock.offset(base, Duration.ofSeconds(20))` | Shifts reference time | Simulating fast/slow servers |
| `Clock.tick(...)` | Fixed-resolution stepping clock | Scenarios simulating quantized time |

**Never use `Thread.sleep(...)` to wait for token expiration near boundaries.** Tests coupled to real elapsed time fail sporadically whenever OS thread scheduling shifts.

## 6. Unit-Testing `JwtTimestampValidator` with JUnit 5

When testing only the timestamp validator, you can build a `Jwt` directly with `Jwt.withTokenValue(...)`. No private key, real signed token, or mock HTTP server is needed because this is a **unit test of time-validation logic**, not JWS signature verification.

Example:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

class JwtTimestampValidatorBoundaryTest {

    private static final Instant T =
        Instant.parse("2026-11-15T10:00:00Z");
    private static final Duration SKEW = Duration.ofSeconds(30);

    private JwtTimestampValidator validatorAt(Instant now) {
        JwtTimestampValidator validator =
            new JwtTimestampValidator(SKEW);
        validator.setClock(Clock.fixed(now, ZoneOffset.UTC));
        return validator;
    }

    private Jwt token(Instant expiresAt, Instant notBefore) {
        Jwt.Builder builder = Jwt.withTokenValue("jwt-for-validator-test")
            .header("alg", "RS256")
            .subject("user-42")
            .issuedAt(T.minusSeconds(120));

        if (expiresAt != null) {
            builder.expiresAt(expiresAt);
        }
        if (notBefore != null) {
            builder.notBefore(notBefore);
        }

        return builder.build();
    }

    private boolean valid(Instant exp, Instant nbf) {
        OAuth2TokenValidatorResult result =
            validatorAt(T).validate(token(exp, nbf));
        return !result.hasErrors();
    }

    @Test
    void expirationBeyondSkewIsRejected() {
        // T - 30 seconds - 1 nanosecond: past the boundary.
        Instant exp = T.minus(SKEW).minusNanos(1);
        assertFalse(valid(exp, T.minusSeconds(60)));
    }

    @Test
    void expirationExactlyAtSkewBoundaryIsAccepted() {
        // In an isAfter-based implementation, equality does not error.
        Instant exp = T.minus(SKEW);
        assertTrue(valid(exp, T.minusSeconds(60)));
    }

    @Test
    void expirationJustInsideSkewIsAccepted() {
        Instant exp = T.minus(SKEW).plusNanos(1);
        assertTrue(valid(exp, T.minusSeconds(60)));
    }

    @Test
    void notBeforeBeyondSkewIsRejected() {
        Instant nbf = T.plus(SKEW).plusNanos(1);
        assertFalse(valid(T.plusSeconds(600), nbf));
    }

    @Test
    void notBeforeExactlyAtSkewBoundaryIsAccepted() {
        // In an isBefore-based implementation, equality does not error.
        Instant nbf = T.plus(SKEW);
        assertTrue(valid(T.plusSeconds(600), nbf));
    }

    @Test
    void notBeforeJustInsideSkewIsAccepted() {
        Instant nbf = T.plus(SKEW).minusNanos(1);
        assertTrue(valid(T.plusSeconds(600), nbf));
    }

    @Test
    void bothConditionsMustPass() {
        // Good exp, nbf too far in the future.
        assertFalse(valid(T.plusSeconds(60), T.plusSeconds(31)));

        // Good nbf, exp too far in the past.
        assertFalse(valid(T.minusSeconds(31), T.minusSeconds(60)));

        // Both exp and nbf valid.
        assertTrue(valid(T.plusSeconds(60), T.minusSeconds(60)));
    }
}
~~~

Here `"jwt-for-validator-test"` is not a validly signed JWT; the manually constructed `Jwt` only exercises the validator. This test **does not prove the decoder verifies signatures, issuer, or audience**. Equality assertions reflect `isAfter/isBefore` semantics; check and adapt to your actual library version.

### Matrix Testing with `@ParameterizedTest`

Instead of repeating test methods, you can parameterize the `exp` offset relative to `T`. Example:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

class ExpirationMatrixTest {

    private static final Instant T =
        Instant.parse("2026-11-15T10:00:00Z");

    static Stream<Arguments> cases() {
        return Stream.of(
            Arguments.of(-31L, false),
            Arguments.of(-30L, true),
            Arguments.of(-29L, true),
            Arguments.of(0L, true),
            Arguments.of(60L, true)
        );
    }

    @ParameterizedTest(name = "offset={0}s, valid={1}")
    @MethodSource("cases")
    void validateAtOffsets(long offsetSeconds, boolean expectedValid) {
        JwtTimestampValidator validator =
            new JwtTimestampValidator(Duration.ofSeconds(30));
        validator.setClock(Clock.fixed(T, ZoneOffset.UTC));

        Jwt token = Jwt.withTokenValue("jwt-test")
            .header("alg", "RS256")
            .subject("user-42")
            .issuedAt(T.minusSeconds(120))
            .notBefore(T.minusSeconds(120))
            .expiresAt(T.plusSeconds(offsetSeconds))
            .build();

        boolean valid = !validator.validate(token).hasErrors();
        assertEquals(expectedValid, valid);
    }
}
~~~

You can build a similar matrix for `nbf` at offsets `+29s`, `+30s`, and `+31s`. The ±1 nanosecond cases are usually clearer as dedicated tests, since whole-second offsets will not expose sub-second boundary differences.

## 7. Zero Skew and Strict Expiration Rules

If you configure:

~~~java
JwtTimestampValidator validator =
    new JwtTimestampValidator(Duration.ZERO);
validator.setClock(Clock.fixed(T, ZoneOffset.UTC));
~~~

then in an `isAfter`-based implementation, at exact `T == exp`, `T.isAfter(exp)` returns `false`—meaning no expiration error occurs at **exact equality**. Yet RFC 7519 expresses `exp` as requiring the current time to be **before** the expiration time.

This raises two separate questions:

1. **What does the JWT profile require?** When may the token be used, how much leeway is permitted, and are there extra time limits?
2. **Which comparison operator does the library version implement?** Is equality accepted in that version's code?

Test the exact boundary instead of assuming zero skew automatically enforces strict `now < exp`. If an API requires rejecting tokens at the exact instant `exp`, express that policy explicitly via configuration or a validator suited to your version and security requirements.

On live requests, clock precision rarely matches an issuer's integer NumericDate to the exact nanosecond; boundary tests deliberately construct that equality case to uncover subtle implementation differences.

## 8. Time Constraints Beyond `JwtTimestampValidator`

A complete time-validation suite may need more checks than comparing `exp` and `nbf` against `now`.

### 8.1. Required Claims

Under general JWT rules, `exp`/`nbf`/`iat` are not automatically mandatory in every token. Specific profiles like OAuth 2.0 JWT access tokens (RFC 9068) mandate particular claims. If the API requires `exp`, include a validator ensuring it is present, properly typed, and meaningful.

Never assume `JwtTimestampValidator` automatically rejects every JWT missing `exp`. Also, `nbf` may be optional in a profile; omitting `nbf` does not automatically invalidate a token.

### 8.2. Future `iat`

`iat` is the **issuance** time, not the start of validity. A token with `iat` in the future may need to be rejected per profile or API policy, yet you should not assume the default timestamp validator checks this rule. When needed, add a dedicated check for:

~~~text
iat <= now + issuedAtAllowedSkew
~~~

### 8.3. Relationship Between `nbf` and `exp`

A token could carry `nbf > exp`:

~~~json
{
  "iat": 1763164800,
  "nbf": 1763165700,
  "exp": 1763165400
}
~~~

Logically, the nominal validity window is inverted. `JwtTimestampValidator` typically checks `exp` and `nbf` **independently** against the clock. If your profile requires `exp > nbf` or `exp > iat`, enforce that relationship in a validator.

Example policy validator requiring both `exp` and `nbf` to be present with `exp` after `nbf`:

~~~java
import java.time.Instant;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

class TimeWindowPolicyValidator implements OAuth2TokenValidator<Jwt> {

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        Instant exp = jwt.getExpiresAt();
        Instant nbf = jwt.getNotBefore();

        if (exp == null || nbf == null || !exp.isAfter(nbf)) {
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Invalid token window", null)
            );
        }
        return OAuth2TokenValidatorResult.success();
    }
}
~~~

**This is an illustrative policy**, not a universal requirement for every JWT. If the issuer is permitted to omit `nbf`, do not apply a validator mandating `nbf` indiscriminately.

### 8.4. Maximum Token Lifetime

A token with an `exp` far in the future is still "unexpired" under a simple expiration check, yet an API can cap issued lifetime—for example, at most 15 minutes from `iat`. That condition is:

~~~text
exp - iat <= maximumTokenLifetime
~~~

It differs from clock skew and requires a separate policy validator. Never stretch clock skew to adjust maximum token age.

## 9. Wiring the Validator into `NimbusJwtDecoder`

### 9.1. Default Resource Server Configuration

A Spring Boot Servlet application typically includes:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Example `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

Spring Security uses the issuer to resolve verification metadata/keys and applies default validators per version. **API-specific audience and JWT profile rules still need to be explicitly defined and configured as needed.**

Illustrative security filter chain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurity {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

This configuration illustrates Bearer JWT authentication. Real applications must add scope, method authorization, and record-level access checks, while configuring CSRF/session policy appropriately for their client types and auth flows. Not every API should disable CSRF.

### 9.2. Customizing Clock Skew

When you need a 30-second skew instead of the default, instantiate `JwtTimestampValidator(Duration)` and place it inside a **complete validator chain**:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class OrdersJwtDecoderConfiguration {
    private static final String ISSUER =
        "https://auth.example.com/realms/shop";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withIssuerLocation(ISSUER)
            .build();

        JwtTimestampValidator timestamps =
            new JwtTimestampValidator(Duration.ofSeconds(30));

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token", "Invalid audience", null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                timestamps,
                new JwtIssuerValidator(ISSUER),
                audience
            )
        );
        return decoder;
    }
}
~~~

**Be careful with `setJwtValidator(...)`:** it **replaces** the validator chain attached to the decoder, so ensure you include timestamp, issuer, audience, profile/`typ`, and required claims matching your version. If your application accepts RFC 9068 `at+jwt` access tokens, checking only those three conditions is **not enough** to enforce the full token profile.

Avoid combining `JwtValidators.createDefaultWithIssuer(ISSUER)` (which already includes a timestamp validator) with another 30-second `JwtTimestampValidator`, accidentally creating **two overlapping timestamp policies**. Be explicit about which validator owns each check while preserving every built-in safeguard your version provides.

### 9.3. What Does the HTTP Response Look Like When a Token Expires?

If a JWT fails timestamp validation, the request is typically rejected during **authentication**:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Content-Length: 0
~~~

This is an illustrative response; exact headers and body depend on the entry point, exception handler, and Spring Security version. An authenticated token lacking scopes or business permissions normally produces **403 Forbidden**. A `401` does not solely imply `exp`: it can also stem from signature, issuer, audience, profile, or Bearer parsing failures.

## 10. Unit Tests, Decoder Tests, and HTTP Integration Tests Serve Different Purposes

| Test Type | Verifies | Does Not Prove |
| --- | --- | --- |
| `JwtTimestampValidator` unit test with fixed `Clock` | `exp`/`nbf`/skew logic and boundary equality | JWS signature, issuer, audience, or HTTP status |
| `JwtDecoder` test with real signed JWT | Decoding/signature verification and attached validators | Endpoint security rules if no HTTP request is sent |
| Integration test through Spring Security filter chain | Bearer parsing, `401`/`403`, and request authorization | Must ensure the real decoder is invoked |
| MockMvc using Spring Security Test's `jwt()` | Scope/authorities/endpoint rules given a mock `Authentication` | Normally skips real signature and timestamp validators |

Example authorization test using a mock JWT:

~~~java
// Illustrates authorization testing only, not JWT timestamp testing.
// mockMvc.perform(get("/api/orders")
//     .with(jwt().authorities(
//         new SimpleGrantedAuthority("SCOPE_orders.read"))))
//     .andExpect(status().isOk());
~~~

This test is useful for checking `SCOPE_orders.read` authorization, yet it does not prove expired `exp` tokens are rejected. To verify **401 on an expired JWT**, you need a token signed with a test key, a real decoder wired with your policy validator/Clock, and a request flowing through the filter chain.

In JUnit unit tests, never rely on wall-clock time. In decoder/integration tests, inject a fixed `Clock` into the validator rather than waiting for tokens to expire in real time.

### Simulating Clock Drift Without Changing System Time

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

Clock issuerClock = Clock.fixed(
    Instant.parse("2026-11-15T10:00:00Z"),
    ZoneOffset.UTC
);
Clock resourceClock = Clock.offset(
    issuerClock, Duration.ofSeconds(25)
);

Instant issuerNow = Instant.now(issuerClock);     // 10:00:00Z
Instant apiNow = Instant.now(resourceClock);      // 10:00:25Z
~~~

Pass `resourceClock` to `JwtTimestampValidator` and mint the JWT with `nbf`/`exp` relative to `issuerClock` to simulate an API running 25 seconds ahead. A 30-second skew absorbs that drift; zero skew produces a different outcome near the boundary.

## 11. Scenario Matrix for Boundary Testing

Let `T` be a fixed instant and `S = 30s`. The table below lists scenarios to cover regardless of whether you implement tests in JUnit or another framework:

| Scenario | Test Data | Purpose |
| --- | --- | --- |
| Clearly expired token | `exp = T - 5 minutes` | Confirm expiration rejection |
| `exp` on skew boundary | `exp = T - 30s` | Distinguish equality from past-skew |
| `exp` 1ns past boundary | `exp = T - 30s - 1ns` | Verify strict boundary |
| `exp` inside skew window | `exp = T - 29s` | Confirm tolerance works |
| Far-future `nbf` | `nbf = T + 5 minutes` | Confirm premature-token rejection |
| `nbf` on skew boundary | `nbf = T + 30s` | Check equality handling |
| `nbf` 1ns past boundary | `nbf = T + 30s + 1ns` | Verify strict boundary |
| `nbf` inside skew window | `nbf = T + 29s` | Confirm tolerance works |
| Both claims valid | `nbf = T - 1m`, `exp = T + 1m` | Accepted on timestamps |
| Valid `exp`, invalid `nbf` | `exp = T + 1m`, `nbf = T + 1m` | Ensure `nbf` is not skipped |
| Valid `nbf`, invalid `exp` | `nbf = T - 1m`, `exp = T - 1m` | Ensure `exp` is not skipped |
| Missing `exp` | `exp` claim absent | Distinguish timestamp validator from required-claim validator |
| Future `iat` | `iat = T + 5m` | Check dedicated policy if applicable |
| Wrong unit in payload | `exp` encoded as milliseconds instead of seconds | Catch JSON contract bugs |
| Differing skew across APIs | Same token with `0s` and `30s` policies | Verify operational consistency |

Pay special attention to **time resolution**: `Instant` supports nanoseconds, while a JWT issuer may emit integer seconds only. ±1ns unit tests clarify the comparison operator, while integration tests verify how the library converts JSON NumericDate values into `Instant`.

## 12. Frequently Asked Questions

### "The access token has reached `exp`, so why does the Resource Server sometimes still accept it?"

The Resource Server may have clock skew enabled. When skew is allowed, validation time can fall within a short grace window after nominal `exp`. In addition, exact **equality** behavior depends on the version. Inspect your actual configuration and never mistake clock skew for token refresh.

### "Does increasing skew fix all JWT expiration errors?"

No. Errors may be caused by seconds-vs-milliseconds unit bugs, severe system clock drift, bad `exp` values emitted by the issuer, or rejection due to signature, audience, or issuer. Blindly widening skew extends token usability and can introduce security exposure.

### "Does `JwtTimestampValidator` validate `iat` and maximum token age?"

Do not assume so. In common versions, this validator focuses on `exp` and `nbf`. If your token profile restricts future `iat` or caps `exp - iat`, add a dedicated validator per contract.

### "If `Clock.fixed` tests pass, why does calling the live API still return 401?"

Timestamp unit tests do not verify signatures, algorithms, JWKS, issuer, audience, JWT type, or Bearer syntax. Separate decoder/validator errors from authorization errors. Never log raw access tokens when debugging.

### "Can a client edit `exp` inside a JWT to keep using it?"

No. A JWS-signed JWT protects both header and payload; changing `exp` invalidates the signature. The client must obtain a new access token from the Authorization Server via an appropriate grant. The Resource Server only validates incoming tokens.

### "Does a valid `exp` guarantee the endpoint returns 200?"

No. An unexpired token can still fail signature, issuer, audience, or type/profile checks, or the caller may lack required scopes or record-level permissions. `JwtTimestampValidator` handles only one part of JWT validation.

## 13. Principles for Production Systems

1. **Read NumericDate properly:** JWT uses Unix epoch seconds; Java `Instant` compares absolute points in time. Never mix in epoch milliseconds.
2. **Define an explicit policy:** specify which claims are required, exact skew, and whether `iat`, max token lifetime, or `nbf < exp` must be checked.
3. **Test with a fixed `Clock`:** use `T`, `T-S`, `T+S`, and ±1ns to catch boundary differences without `sleep`.
4. **Verify against your exact version:** especially equality semantics and `setClock(Clock)`/`JwtDecoder` APIs—never extrapolate from examples targeting another version.
5. **Keep the full validator set intact:** signature and trusted keys, issuer, audience, timestamps, token profile, required claims, and business authorization. `setJwtValidator(...)` must never drop critical checks.
6. **Separate token validation from authorization:** timestamp failures typically yield `401`; authenticated tokens lacking permissions typically yield `403`.
7. **Test at the right layer:** validator unit tests, decoder tests with real signed JWTs, and HTTP integration tests through the real filter chain answer distinct questions.

**Key takeaway:** `JwtTimestampValidator` uses a reference clock and clock skew to decide whether a JWT falls within its valid time window. Subtle bugs usually hide in **NumericDate units**, **`exp`/`nbf` boundary edges**, and **exact-equality comparisons**. Using `Clock.fixed(...)` at ±1 second and ±1 nanosecond offsets lets you specify and verify your time policy accurately, deterministically, and reproducibly.
