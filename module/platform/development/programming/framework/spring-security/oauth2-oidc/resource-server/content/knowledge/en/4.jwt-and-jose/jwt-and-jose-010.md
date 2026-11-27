# NumericDate, JSON Data Types, and Mapping to Java Types

In a **JWT (JSON Web Token)**, details such as the user, issuer, access permissions, and expiration time are represented as **claims** inside a JSON object. JWT is a format in the **JOSE (JSON Object Signing and Encryption)** ecosystem; a JWT can be protected by a JWS signature or JWE encryption. Although the token travels as a character string, **each claim's value must still be interpreted according to JSON types and the rules of the JWT/OIDC specifications**.

A detail that very easily causes bugs when working with **Spring Security OAuth 2.0 Resource Server** is that the three time claims `exp`, `iat`, and `nbf` use the **NumericDate** type: seconds since the Unix epoch, **not milliseconds**. When Java applications use `Instant`, `Date`, `Long`, `BigDecimal`, or a JWT decoding library, you must clearly distinguish the original wire representation from the type converted by the library.

This lesson explains NumericDate, how JSON types map to Java, common conversion bugs, and how to read claims in a Resource Server while respecting token validation boundaries.

## 1. Where Do JSON Claims Sit in JWT and JOSE?

A JWT in **JWS Compact Serialization** usually has three dot-separated parts:

~~~text
BASE64URL(Protected Header).BASE64URL(Claims Payload).BASE64URL(Signature)
~~~

Example internal structure:

**JOSE protected header:**

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "signing-key-01"
}
~~~

**JWT Claims Set (payload):**

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "iat": 1704067200,
  "nbf": 1704067200,
  "exp": 1704070800,
  "scope": "orders.read",
  "email_verified": true,
  "permissions": ["orders:view", "orders:export"],
  "profile": {
    "tenant_id": "tenant-7"
  }
}
~~~

In this example, `iat` is **2024-01-01T00:00:00Z** and `exp` is **2024-01-01T01:00:00Z**: the token has a designed validity window of one hour. The time values are **JSON numbers**, without quotation marks.

The JOSE header holds information needed for cryptographic protection such as `alg` and `kid`. The JWT Claims Set holds claims such as `iss`, `sub`, `aud`, and `exp`. JSON data types in both parts matter, yet **never trust a claim merely because you can Base64URL-decode and read it**. The Resource Server must verify the signature and token conditions per configuration before using claim data for authorization.

> Note: A JWT can be encrypted as a JWE instead of a three-part JWS; claim contents are only readable after valid decryption. Never assume every JWT string can be split into three parts and read directly as JSON.

## 2. What Is NumericDate?

By the JWT definition (RFC 7519), **NumericDate** is a **JSON number** representing the number of seconds from:

~~~text
1970-01-01T00:00:00Z
~~~

This is the **Unix epoch**. NumericDate counts seconds following POSIX time semantics: leap seconds are ignored during conversion. NumericDate **can contain fractional parts** and is not required to be an integer.

Examples:

| NumericDate in JSON | Meaning in UTC |
| --- | --- |
| `0` | `1970-01-01T00:00:00Z` |
| `1` | `1970-01-01T00:00:01Z` |
| `-1` | `1969-12-31T23:59:59Z` |
| `1704067200` | `2024-01-01T00:00:00Z` |
| `1704067200.5` | `2024-01-01T00:00:00.500Z` |
| `1704067200.125` | `2024-01-01T00:00:00.125Z` |

Here `Z` denotes UTC, **not the server's local time zone**. The number `1704067200` has the exact same meaning whether the API runs in Vietnam, Europe, or the United States. Time zones only affect how time is **displayed**, never the timestamp inside the token.

### The Three Registered Claims Using NumericDate

| Claim | Full name | Meaning | Typical handling condition |
| --- | --- | --- | --- |
| `exp` | Expiration Time | Time when the token **expires** | Current time must be **before** `exp` (configured leeway/clock skew may apply) |
| `nbf` | Not Before | Time when the token **becomes valid for use** | Reject the token before `nbf`, outside permitted leeway |
| `iat` | Issued At | Time when the token **was issued** | Used to determine token age; additional rules must be defined by policy |

Under the base JWT specification, these registered claims are not automatically mandatory for **every** JWT: individual systems or protocol profiles define which claims must appear. For example, an **OIDC ID Token** requires certain time claims such as `exp` and `iat`; a Resource Server should also clearly specify its requirements for access tokens issued by its issuer.

**Do not equate `iat` with the time a token becomes valid.** The claim representing "do not use before" is `nbf`. Likewise, never infer a token is valid from a timestamp alone: signature/issuer, audience, scope, and other conditions must still be verified.

### Why Does NumericDate Not Use Milliseconds?

The ecosystem uses multiple time representations:

| Source/type | Unit of numeric value | Same instant example |
| --- | --- | --- |
| JWT `NumericDate` | **Seconds** since Unix epoch | `1704067200` |
| Java `Instant.getEpochSecond()` | **Seconds** | `1704067200L` |
| Java `Instant.toEpochMilli()` | **Milliseconds** | `1704067200000L` |
| Java `Date.getTime()` | **Milliseconds** | `1704067200000L` |
| JavaScript `Date.now()` | **Milliseconds** | `1704067200000` |

Passing `System.currentTimeMillis()` or `Date.getTime()` directly into `exp` creates a timestamp **1,000 times larger in unit** than the expected NumericDate value. Conversely, taking a NumericDate and passing it directly into Java's `new Date(long)` constructor causes Java to treat it as **milliseconds**, resulting in a date in 1970 instead of the actual time.

## 3. NumericDate Is a JSON Number, Not a Java `long`

JSON has only a single **number** data type, making no syntactic distinction between `int`, `long`, `float`, and `double`. All of the following are syntactically valid JSON numbers:

~~~json
{
  "wholeSeconds": 1704067200,
  "fractionalSeconds": 1704067200.125,
  "scientificNotation": 1.7040672e9
}
~~~

In Java applications, a JSON parser may map these to `Integer`, `Long`, `Double`, `BigInteger`, or `BigDecimal` depending on configuration and magnitude. **You cannot assume from JSON syntax that the resulting Java object will always be a `Long`.**

These encodings mean different things:

~~~json
{
  "exp_number": 1704067200,
  "exp_string": "1704067200",
  "exp_milliseconds": 1704067200000,
  "exp_iso_string": "2024-01-01T00:00:00Z"
}
~~~

- `exp_number` has the right format and unit for NumericDate.
- `exp_string` is a **JSON string**, not a valid NumericDate for a standard `exp` claim.
- `exp_milliseconds` is a JSON number, yet has the wrong **unit** if meant to represent a 2024 timestamp.
- `exp_iso_string` is an ISO-8601 string—useful for display, yet the wrong type for a standard NumericDate `exp` claim.

Therefore, an API should reject or fail wrong-typed claims per policy and verification library rather than **auto-"guessing" that a date string or millisecond number is a valid NumericDate**. Arbitrary coercion can mask broken token issuance from issuers while accepting tokens inconsistently.

### Note on Fractional Seconds

NumericDate permits non-integer values. For example, `1704067200.125` carries an extra **125 milliseconds**. If code calls `longValue()`, the fractional part is truncated.

~~~java
double numericDate = 1704067200.125;
long seconds = (long) numericDate;  // 1704067200, loses 0.125 seconds
~~~

For real token validation, let a trusted JWT library parse and validate time claims. If you must convert directly at a data layer, define the required **precision** (seconds, milliseconds, nanoseconds) and fractional handling; `BigDecimal` is usually better than `double` when floating-point rounding errors must be avoided.

## 4. Other JSON Types in JWT and How Java Interprets Them

A JWT Claims Set is a **JSON object** that can contain standard JSON types:

| JSON type | Payload example | Typical Java representation |
| --- | --- | --- |
| **string** | `"sub": "user-42"` | `String` |
| **number** | `"exp": 1704070800` | `Integer`, `Long`, `BigDecimal`... or `Instant` after library conversion |
| **boolean** | `"email_verified": true` | `Boolean` |
| **array** | `"roles": ["USER", "ADMIN"]` | `List<String>` or `List<?>` |
| **object** | `"profile": {"tenant_id": "tenant-7"}` | `Map<String, Object>` or DTO depending on parsing |
| **null** | `"nickname": null` | `null` or library-specific null representation |

For example:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api", "reports-api"],
  "exp": 1704070800,
  "iat": 1704067200,
  "jti": "token-abc-123",
  "scope": "orders.read orders.write",
  "roles": ["USER", "REPORT_VIEWER"],
  "email_verified": true,
  "account": {
    "id": 42,
    "tier": "standard"
  }
}
~~~

Data types must be interpreted **according to each claim's contract**, not merely whether JSON parses:

- `iss` (issuer), `sub` (subject), and `jti` (JWT ID) are **string** claims per their definitions.
- `aud` (audience) under JWT can be **a single string** or **an array of strings**. JWT libraries often normalize it into a list for the application.
- `exp`, `nbf`, and `iat` are **NumericDate**.
- `scope` in many OAuth 2.0 access tokens is represented as **a space-delimited string of scopes**. Some providers use an array-typed `scp` claim; never assume both always exist or share the same schema.
- `roles` and `account` here are **custom claims**. Their types and semantics depend on the issuer/API design; JWT does not require every token to include them.
- `email_verified` is an example boolean claim in OIDC; do not treat the string `"true"` as equivalent to boolean `true` when the contract requires a boolean.

**A claim starting with digits can still be a string.** For example, `"sub": "123456"` is a string: `sub` is an identifier, not an arithmetic quantity. Converting `sub` to a number can strip leading zeros or corrupt the identifier.

## 5. Converting NumericDate to Java Types

### 5.1. Use `Instant` for Absolute Instants

In modern Java, `java.time.Instant` represents a point on the UTC timeline and is the right choice for storing/comparing token timestamps.

~~~java
import java.time.Instant;

long numericDate = 1704067200L;
Instant instant = Instant.ofEpochSecond(numericDate);

System.out.println(instant);
// 2024-01-01T00:00:00Z

long secondsBack = instant.getEpochSecond();
// 1704067200
~~~

The crucial part is calling **`Instant.ofEpochSecond(...)`** when the input is a NumericDate, **never `Instant.ofEpochMilli(...)`** with that same number.

When producing a NumericDate from the current time:

~~~java
Instant now = Instant.now();
long issuedAt = now.getEpochSecond();
long expiresAt = now.plusSeconds(900).getEpochSecond();

// issuedAt and expiresAt are in seconds, e.g., for iat/exp
~~~

`Instant.getEpochSecond()` returns a `long`. This avoids the 32-bit `int` overflow limit around January 2038. However, when JSON input includes fractional seconds, `getEpochSecond()` reflects only the whole-second part; if sub-second precision is needed, combine it with `getNano()`.

### 5.2. Distinguishing `Date` from `Instant`

`java.util.Date` is still used by several JOSE/JWT libraries. Both the `Date(long)` constructor and `Date.getTime()` use **milliseconds** since the epoch.

~~~java
import java.time.Instant;
import java.util.Date;

long numericDate = 1704067200L;       // SECONDS

Date correct = Date.from(Instant.ofEpochSecond(numericDate));
Date alsoCorrect = new Date(numericDate * 1000L);

Date incorrect = new Date(numericDate); // WRONG: Java interprets this as milliseconds

long seconds = correct.toInstant().getEpochSecond();
long milliseconds = correct.getTime();
~~~

Around current dates, millisecond values are **1,000 times** larger than second values. However, **never use a digit-count heuristic to auto-guess units in authentication logic**: that can fail on historical dates, negative values, or unusual timestamps. Enforce explicit types and units right at the input/output boundary.

### 5.3. Preserving Fractional Parts with `BigDecimal`

If you are processing **raw JSON** or building a custom converter, `BigDecimal` preserves fractional parts up to a defined limit. The example below converts a NumericDate JSON number to `Instant`, enforcing precision no finer than **nanoseconds** (9 significant decimal digits).

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;

public final class NumericDateConverter {

    private NumericDateConverter() {}

    public static Instant fromNumericDate(BigDecimal numericDate) {
        if (numericDate == null) {
            throw new IllegalArgumentException("NumericDate must not be null");
        }

        // FLOOR handles timestamps prior to 1970 as well.
        BigDecimal wholeSeconds = numericDate.setScale(0, RoundingMode.FLOOR);
        long epochSeconds = wholeSeconds.longValueExact();

        BigDecimal fractionalNanos = numericDate
            .subtract(wholeSeconds)
            .movePointRight(9);

        // intValueExact() rejects fractional parts smaller than 1 nanosecond.
        int nanos = fractionalNanos.intValueExact();

        return Instant.ofEpochSecond(epochSeconds, nanos);
    }

    public static BigDecimal toNumericDate(Instant instant) {
        BigDecimal seconds = BigDecimal.valueOf(instant.getEpochSecond());
        if (instant.getNano() == 0) {
            return seconds;
        }
        return seconds.add(BigDecimal.valueOf(instant.getNano(), 9));
    }
}
~~~

Usage example:

~~~java
Instant t1 = NumericDateConverter.fromNumericDate(
    new BigDecimal("1704067200.125")
);
// 2024-01-01T00:00:00.125Z

Instant t2 = NumericDateConverter.fromNumericDate(
    new BigDecimal("-0.5")
);
// 1969-12-31T23:59:59.500Z

BigDecimal value = NumericDateConverter.toNumericDate(t1);
// 1704067200.125000000 (numerically equivalent to 1704067200.125)
~~~

Because `Instant` stores nanosecond precision, the method above **rejects** NumericDates with sub-nanosecond fractions that cannot be represented exactly. Applications can choose another rounding policy if required by business rules, but should never silently round during token validation.

Subtle detail: for the negative number `-0.5`, the `Instant` seconds component is `-1` and the nanoseconds component is `500000000`. Splitting the integer part by truncating toward zero without adjusting the fractional part produces wrong pre-epoch timestamps.

### 5.4. Reading Raw JSON with Jackson

When Java code receives JSON prior to a JWT converter, inspect the JSON node type before casting:

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.json.JsonMapper;
import java.time.Instant;

JsonMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS)
    .build();

JsonNode claims = mapper.readTree(
    "{\"exp\":1704067200.125,\"sub\":\"user-42\"}"
);

JsonNode exp = claims.get("exp");
if (exp == null || !exp.isNumber()) {
    throw new IllegalArgumentException("exp must be a JSON number");
}

Instant expiresAt = NumericDateConverter.fromNumericDate(
    exp.decimalValue()
);

String subject = claims.path("sub").asText();
~~~

This example demonstrates **data types and conversion**, not how to build a custom JWT verifier. In production, the Resource Server must use a properly configured `JwtDecoder` to validate tokens before trusting claims. Splitting a payload manually and reading it with `ObjectMapper` does not protect the API.

When working with a `Map<String, Object>`, avoid assuming `(Long) claims.get("exp")` will always succeed: parsed values may be `Integer`, `Long`, `BigDecimal`, or another type depending on the parser and conversion stage.

## 6. Claim Conversion in Spring Security Resource Server

Spring Security typically performs a **claim type normalization** step after verifying and decoding a JWT so developers can work comfortably with Java APIs.

Example JWT Resource Server configuration:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

For tokens from a trusted issuer, Spring Security can invoke the corresponding JWT decoder (such as `NimbusJwtDecoder`) and construct an `org.springframework.security.oauth2.jwt.Jwt` object.

### 6.1. Prefer Reading Timestamps with Typed Getters

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.security.oauth2.jwt.Jwt;

public final class ClaimExamples {

    public static void inspect(Jwt jwt) {
        String subject = jwt.getSubject();
        String issuer = jwt.getIssuer() == null
            ? null : jwt.getIssuer().toString();

        Instant issuedAt = jwt.getIssuedAt();   // iat
        Instant notBefore = jwt.getNotBefore();  // nbf
        Instant expiresAt = jwt.getExpiresAt();  // exp

        List<String> audiences = jwt.getAudience();
        String scope = jwt.getClaimAsString("scope");
        List<String> roles = jwt.getClaimAsStringList("roles");

        // Use these values according to application policy.
    }
}
~~~

`Jwt.getIssuedAt()`, `getNotBefore()`, and `getExpiresAt()` return **`Instant`** (or `null` if the claim is absent, depending on API and token contents). These methods prevent controller authors from manually dividing by 1,000 or casting `Long` from `getClaims()`.

In Spring Security's standard claim converter (`MappedJwtClaimSetConverter`), time claims `exp`, `iat`, and `nbf` are normalized to `Instant`; `aud` is normalized into an audience list. Therefore, **the JSON type on the wire and the Java type inside the `Jwt` object do not have to be identical**.

For example, given JSON input:

~~~json
{
  "exp": 1704070800,
  "aud": "orders-api"
}
~~~

After conversion by the appropriate converter, the application can use:

~~~java
Instant expiresAt = jwt.getExpiresAt();
List<String> audiences = jwt.getAudience();
~~~

Avoid writing:

~~~java
// Type-unsafe when reading a normalized Jwt object.
Long exp = (Long) jwt.getClaims().get("exp");
~~~

Custom claims are not automatically converted into domain-specific Java types you might expect. For example, `"account": {"id":42}` may remain a `Map`, and `"roles": ["USER"]` may remain a raw list. If you need DTOs or custom type mappings, define explicit policies and converters aligned with the issuer.

### 6.2. How Does Spring Security Validate Timestamps?

A JWT Resource Server typically uses validators to check token validity, including **timestamp validation** for `exp` and `nbf`, along with an issuer validator when an issuer is configured.

Conceptual flow:

~~~text
         JWT access token
                |
                v
     Decode & verify signature
                |
                v
    Normalize JSON claims to Java
                |
                v
      Validate timestamps/token
       exp, nbf, issuer...
                |
                v
    Authenticate & check API permissions
                |
                v
       Controller / Service
~~~

Some systems configure **clock skew/leeway** to tolerate minor clock drift between the Authorization Server and Resource Server. For example, a validator may permit a few tens of seconds of skew on `exp` or `nbf` per policy. This is a **verification tolerance window**, not modifying `exp` inside the token or refreshing the token.

`iat` is commonly provided to indicate issuance time, yet do not assume every default configuration rejects a token merely because `iat` is slightly in the future; if your system needs rules like "not issued in the future" or "maximum token age," define and configure a dedicated validator.

A valid JWT signature and valid timestamps are still not enough to allow calling every API. The Resource Server must still check **issuer, audience, scopes/permissions**, and access rights on the specific target object. For example, a token with `aud` for the Payments API must not be accepted by the Orders API merely because it shares the same issuer and is unexpired.

### 6.3. Do Not Manually Convert NumericDate in Controllers Instead of Validation

Code like:

~~~java
// Unsafe pattern: never use as an API authentication mechanism.
String[] parts = bearerToken.split("\\.");
String payload = new String(
    java.util.Base64.getUrlDecoder().decode(parts[1])
);
// Then reading exp, sub from JSON without verifying the signature...
~~~

only reads untrusted data. If JOSE signature, issuer, audience, and lifetime verification are skipped, an attacker can craft an arbitrary JSON payload. Spring Security Resource Server provides the authentication pipeline specifically so you never have to do this manually.

## 7. Common Conversion Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `System.currentTimeMillis()` as `exp` | Token expires in the wrong unit, potentially absurdly far in the future | Use **seconds**, e.g., `Instant.now().getEpochSecond()` |
| Using `new Date(numericDate)` | Java treats numericDate as milliseconds, producing a date near 1970 | Use `Date.from(Instant.ofEpochSecond(numericDate))` |
| Using `Instant.ofEpochMilli(numericDate)` | Wrong instant because NumericDate is in seconds | Use `Instant.ofEpochSecond(...)` |
| Casting `(Long) jwt.getClaim("exp")` | May throw `ClassCastException` because the claim was converted to `Instant` | Use `jwt.getExpiresAt()` |
| Treating `"exp": "1704067200"` as NumericDate | Masks invalid JSON typing in the token | Require a JSON number per contract |
| Casting `(int) epochSeconds` | Integer overflow around the year 2038 | Use `long` or `Instant` |
| Calling `longValue()` on fractional values | Loses sub-second precision | Define precision rules; use `BigDecimal`/`Instant` when needed |
| Converting `sub` to a number | Strips leading zeros, corrupts ID, or overflows | Keep identifiers as `String` |
| Assuming `aud` is always a `String` | Fails when the issuer sends an array of audiences | Use `jwt.getAudience()` |
| Comparing `LocalDateTime.now()` against UTC without conversion | Breaks across system time zones | Use `Instant.now()` for comparing absolute instants |
| Checking only `exp` from a self-decoded payload | Bypasses signature and trust boundaries | Use the Resource Server's `JwtDecoder` and token validators |

### Example of the Seconds vs. Milliseconds Bug

~~~java
import java.time.Instant;

long expFromJwt = 1704070800L;

Instant correct = Instant.ofEpochSecond(expFromJwt);
// 2024-01-01T01:00:00Z

Instant wrong = Instant.ofEpochMilli(expFromJwt);
// 1970-01-20T17:07:50.800Z — wrong unit
~~~

### NumericDate Is Not an ISO-8601 String

In Java, `Instant.toString()` returns ISO-8601, such as `"2024-01-01T01:00:00Z"`. That **string** representation is well suited for logs and display DTOs, yet **is the wrong type for a JWT NumericDate** if placed into the `exp` claim.

In particular, if an application creates JWTs itself and serializes a Java object to JSON, never assume an `Instant` will automatically serialize as **epoch seconds**. JSON output depends on Jackson configuration and time modules; use a JOSE library's JWT builder API or an explicit NumericDate converter.

## 8. OIDC: Time Claims and Data Types to Watch

An OIDC ID Token is also a JWT carrying protocol identity claims. Beyond `exp` and `iat`, OIDC can include `auth_time` to indicate **when the user authenticated**.

Abbreviated example of an ID Token Claims Set:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-42",
  "aud": "orders-web-app",
  "iat": 1704067200,
  "exp": 1704070800,
  "auth_time": 1704067000,
  "nonce": "random-nonce-value",
  "email_verified": true
}
~~~

In this example:

- `iat` and `exp` are NumericDates.
- `auth_time`, when present, is a NumericDate for **when user authentication occurred**, which can differ from `iat`.
- `nonce` is a string used in related OIDC flows, not a timestamp.
- `email_verified` is a boolean, not a string.
- An ID token's `aud` typically targets the **OIDC client**, whereas an API access token must be verified against the audience for the **Resource Server**.

Never use an **ID token in place of an access token** when calling an API. The OIDC client is responsible for validating ID tokens under OIDC rules, while Spring Security Resource Server validates **access tokens** under the API's contract. Both token types may contain NumericDates, yet they serve different purposes.

## 9. Applying This When Designing DTOs, Databases, and API Contracts

In multi-service systems, standardize **data types, units, and conversion points** at every boundary:

1. **In standard JWT/ID tokens:** `exp`, `iat`, `nbf` (and `auth_time` when used by OIDC) are **JSON numbers in seconds**.
2. **In the Java domain:** use `Instant` to represent absolute instants; use `long` when a contract specifies integer epoch seconds; use `BigDecimal` if fractional seconds must be handled exactly.
3. **In legacy Java:** `Date`/epoch milliseconds must undergo explicit unit conversion at API boundaries.
4. **In custom HTTP DTOs:** you may choose ISO-8601 strings or epoch seconds, provided **the schema/unit is explicitly documented**. Never implicitly impose DTO conventions onto standard JWT claims.
5. **In databases:** choose consistent timestamp types and time-zone/precision policies; avoid mixing second and millisecond timestamps in a poorly defined column.

Example of two distinct DTO contracts, both valid **if defined by the DTO's own schema**:

~~~json
{
  "expiresAt": "2024-01-01T01:00:00Z"
}
~~~

~~~json
{
  "expiresAtEpochSeconds": 1704070800
}
~~~

However, for the **JWT `exp` claim**, the standard contract is:

~~~json
{
  "exp": 1704070800
}
~~~

## 10. Illustrating a Complete Token Lifecycle

~~~mermaid
sequenceDiagram
    autonumber
    participant AS as Authorization Server
    participant C as OAuth2 Client
    participant RS as Spring Security Resource Server

    C->>AS: Request token via permitted grant
    AS-->>C: JWT access token (iat/exp as NumericDate)
    C->>RS: GET /api/orders + Bearer JWT
    RS->>RS: Verify signature, issuer, audience
    RS->>RS: Map NumericDate to Instant
    RS->>RS: Check exp/nbf, scope, business permissions
    alt Token and permissions valid
        RS-->>C: 200 OK + data
    else Token invalid or expired
        RS-->>C: 401 Unauthorized
    else Authenticated but insufficient permissions
        RS-->>C: 403 Forbidden
    end
~~~

If the access token is expired, the Resource Server rejects the request. Obtaining a new access token (via refresh token grant, Client Credentials, or the appropriate authorization flow) is handled by **the Client and Authorization Server**. **Converting NumericDate to `Instant` only supports time validation**; it does not renew the token or alter granted permissions.

## 11. Takeaways When Working with Spring Security

- In JWT, `exp`, `iat`, and `nbf` are **NumericDate — JSON numbers in seconds since the Unix epoch**.
- A JSON **number** and a Java `Long` are two distinct concepts; parsers and JWT libraries may convert numbers into different Java types.
- When using Spring Security `Jwt`, prefer `getExpiresAt()`, `getIssuedAt()`, and `getNotBefore()` to obtain **`Instant`**; `getAudience()` returns the audience list.
- Never confuse JWT **seconds** with the **milliseconds** of `Date.getTime()`, `System.currentTimeMillis()`, or `Instant.toEpochMilli()`.
- Use `BigDecimal` when fractional NumericDates must be processed precisely; avoid casts that silently lose precision.
- Claims in a JWT are trustworthy only after **token verification** and enforcing the right issuer, audience, lifetime, and permissions. Never grant access from data read out of a self-decoded payload.

Mastering NumericDate and JSON types helps you handle all three layers accurately: **the JWT wire format, Java data types, and security checks in Spring Security Resource Server**.
