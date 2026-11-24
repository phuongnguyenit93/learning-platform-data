# JWT Structure, Signatures, and Why the Payload Is Not Encrypted by Default

> **Topic:** Spring Security – Fundamentals → **Tokens and Protocols**. Goal: accurately read JSON Web Token (JWT) structure, understand Base64url, distinguish signatures/MAC from encryption, know which JWTs are JWS/JWE, verify signatures **and** claims before trusting a token, and apply them safely in Spring Security OAuth2 Resource Server. Examples use Java 17+ and Spring Boot 3.x / Spring Security 6.x.

## 1. What Is a JWT? JWT Does Not Mean "Encrypted Data String"

**JWT (JSON Web Token)** is a format for transmitting **claims** (assertions about a subject) in JSON, packaged under JOSE standards. Claims can be **signed or integrity-protected** using JSON Web Signature (JWS), or **encrypted** using JSON Web Encryption (JWE). A JWT can even be unprotected if using the unsecured form per the specification; such JWTs are **not suitable to be trusted as authentication credentials** without a clearly designed independent protection layer.

Three commonly confused statements:

1. **JWT is a token format**, which does not by itself guarantee the token is trusted, unexpired, intended for the right audience, or carrying appropriate permissions.
2. **JWS protects integrity and issuing origin** when algorithms and keys are properly chosen/verified, yet a standard JWS payload is **not confidential**. Anyone holding a compact JWS JWT string can Base64url-decode the header and payload.
3. **JWE provides content confidentiality via encryption**; only a recipient with the matching key can decrypt it. JWE still requires validating algorithms, keys, authentication tags, claims, and recipient policies.

The claim "a JWT has a signature so its payload is encrypted" is **false**. Digital signatures and encryption solve different goals. In APIs using OAuth2 JWT access tokens, the common form is a **signed JWT/JWS**, because the API needs to know whether claims were altered without necessarily hiding the payload from the token holder. Conversely, if claims must stay secret from parties lacking the decryption key, design with **JWE or a different sensitive-data delivery model**.

## 2. Three Security Goals That Must Not Be Equated

| Goal | Question | Typical Mechanism | What Must Not Be Inferred |
|---|---|---|---|
| **Integrity** | Has the token content been modified? | JWS signature/MAC verified with a trusted key | That the contents inside are hidden |
| **Authenticity of the signer** | Did an authorized system issue/sign it? | Signature + trusted key, issuer binding, algorithm policy | That the current holder is the legitimate owner or has sufficient permissions |
| **Confidentiality** | Can others read the claims? | JWE encryption, key management, TLS in transit | That encryption automatically determines what the caller may do |
| **Claims validity** | Are issuer/audience/lifetime/token type right for the purpose? | `iss`, `aud`, `exp`, `nbf`, token type, and dedicated policies | That a valid signature alone is enough |
| **Authorization** | Which APIs and data may this subject/scope/role access? | Spring Security rules + business authorization | That holding a valid JWT allows doing anything |

**Operational rule:** an access token is accepted only when **all three layers pass**: valid structure/algorithm/key → verified signature or JWE and valid claims → checked permissions for the request/resource. Do not skip the final layer because a JWT contains `role=ADMIN`.

## 3. Structure of a Compact JWS JWT: Three Parts

For a JWT using **JWS Compact Serialization**, the typical format is:

```text
BASE64URL(UTF-8(JOSE header))
.
BASE64URL(UTF-8(claims payload))
.
BASE64URL(signature-or-MAC)
```

Written compactly:

```text
xxxxx.yyyyy.zzzzz
  1     2     3
  │     │     └─ signature/MAC
  │     └─────── JWT claims payload
  └───────────── JOSE header
```

Separated by **two dots** into **three segments**. All three parts in the example are Base64url-encoded, yet **Base64url is not secret encryption**. It simply converts bytes into a string suitable for safe transport in URLs/headers.

### 3.1. JOSE Header: Metadata on How the Token Is Protected

Example:

```json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "key-2026-11"
}
```

- `alg`: algorithm used for JWS; `RS256` is RSA signature with SHA-256, `ES256` is ECDSA P-256/SHA-256, `HS256` is HMAC-SHA-256. **The server must not blindly trust the `alg` value sent by an attacker**; accept only algorithms configured in policy.
- `typ`: object type hint, e.g., `JWT`. Having `typ=JWT` alone **does not prove the token is an access token**, nor does it prove issuer, signature, or permissions.
- `kid`: key identifier helping select a key from a **trusted key set** (such as a configured JWKS). It is **not a command for the server to download keys from an arbitrary URL**; this value is also sender-controlled until the token is verified.
- Other header parameters such as `jwk`, `jku`, `x5u`, `crit` must be handled per policy/specification; if unsupported, reject them rather than fetching external URLs from the header.

The header **can be read** prior to verification; however, "readable" does not mean "trustworthy". Reading `kid` to select a key from a trusted list is a technical step, whereas deciding to accept `alg`/keys/claims must originate from server configuration.

### 3.2. Payload: JSON Claims

Illustrative claims payload example:

```json
{
  "iss": "https://issuer.example.com",
  "sub": "user-123",
  "aud": ["orders-api"],
  "iat": 1793491200,
  "nbf": 1793491200,
  "exp": 1793494800,
  "scope": "orders.read orders.write",
  "tenant_id": "tenant-a"
}
```

This is **example JSON**, not proof that a real token was signed by a trusted issuer. The `iat`/`nbf`/`exp` values are **NumericDate in seconds**, not milliseconds; the example above only illustrates the shape. Whether claims are sufficient or valid for an application depends on actual issuance and verification policies.

Common claims:

| Claim | Meaning | Key Checks |
|---|---|---|
| `iss` (issuer) | Who issued the token | Must match the trusted issuer exactly |
| `sub` (subject) | Who the token is about | Bound to the right user/service; does not imply that person owns the browser |
| `aud` (audience) | Which resource/service the token was issued for | Must contain the current API's audience |
| `exp` (expiration time) | Expiration timestamp | Reject expired tokens, aside from a small defined clock skew |
| `nbf` (not before) | Timestamp when the token becomes active | Reject tokens not yet active |
| `iat` (issued at) | Issuance timestamp | Supports sanity/token-age checks; not all systems enforce the same policy |
| `jti` (JWT ID) | Token ID | Useful for auditing/denylists/replay protection by design |
| `scope`/`scp` | OAuth2 permissions | Format and authority mapping depend on issuer/framework |
| `roles`/`permissions` | Custom roles/permissions | No single unified schema across all issuers |
| `tenant_id` | Tenant per system design | Must rely on a trusted issuer and enforce server-side ownership/tenant checks |

**Beware of sensitive data:** a JWS payload should not contain passwords, secret keys, card numbers, unnecessary personal data, or tokens usable to access other systems. Even with HTTPS protecting transport, the **holder of the token** can still decode a JWS payload. Placing JWTs in logs, tickets, URLs, or external tools also risks exposing their contents.

### 3.3. Signature or MAC: Not an "Encryption Password"

With JWS, the third part is the result of computing a signature/MAC over **encoded header + dot + encoded payload**:

```text
signingInput =
    BASE64URL(header bytes) + "." + BASE64URL(payload bytes)

signatureBytes =
    SIGN_OR_MAC(private-or-secret-key, signingInput)

compactJws =
    BASE64URL(header) + "." +
    BASE64URL(payload) + "." +
    BASE64URL(signatureBytes)
```

**HMAC (HS256)**: the issuer and verifier can share the same **secret key**; anyone holding the secret can produce a valid MAC. Do not share an HMAC secret broadly across many services.

**Asymmetric signatures (RS256/ES256)**: the issuer keeps the **private key** to sign, and the resource server uses the trusted **public key** to verify; knowing the public key does not allow signing valid tokens. This model fits when many APIs must verify tokens without having permission to issue them.

For a signature to mean anything, you must verify the **right algorithm**, **right trusted key**, **right signing input**, and **right claims**. A string that looks like a signature proves nothing unless it has been verified.

## 4. Base64url Differs from Standard Base64 and from Encryption

Base64url is a Base64 variant using a URL-safe alphabet: typically replacing `+` with `-`, `/` with `_`, and omitting `=` padding in compact tokens. Both are data encodings, not ciphers or hashes.

| Operation | Reversible from Input Alone? | Secret? | Example |
|---|---|---|---|
| Base64 / Base64url | **Yes**, decoder alone suffices | **No** | JWS header/payload |
| SHA-256 hash | Not directly reversible | Not encryption | Fingerprint/digest |
| HMAC-SHA256 | Requires secret to compute/verify valid MAC | Does not hide payload | `HS256` |
| RSA/ECDSA signature | Verified with public key, signed with private key | Does not hide payload | `RS256`, `ES256` |
| Authenticated encryption | Requires matching key and tag | Yes, by design | JWE with AES-GCM |

**Do not confuse:** "Base64url-encoding JSON into a hard-to-read string" only makes the data less human-readable, not confidential. Any webpage or code snippet can decode a JWS payload **without the signing key**. Decoding a payload for display is merely reading a string; it **creates no authentication**.

## 5. Standalone Java 17 Example: HMAC Signing and Proving the Payload Remains Readable

This example has two goals: (1) build a 3-part compact JWS to observe its structure, and (2) tamper with the payload after signing to watch MAC verification fail. It uses **plain JDK 17**, with no Spring or Maven required.

**Security limitation:** the secret in source code is for demonstration only, never for production. The program illustrates integrity only; it **does not perform full JWT validation** (`iss`, `aud`, `exp`, `nbf`, rotation, token type, etc.) and must not be used as authentication for a real API. Production should use a standard, up-to-date JOSE/JWT library and manage keys via a vault/KMS.

File `JwtStructureDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class JwtStructureDemo {

    // FOR LESSON USE ONLY; hardcoded secrets are unsuitable for production.
    private static final byte[] DEMO_SECRET =
        "demo-only-secret-with-32-plus-bytes!".getBytes(
            StandardCharsets.UTF_8);

    private static final String HEADER =
        "{\"alg\":\"HS256\",\"typ\":\"JWT\"}";

    private static String encode(String text) {
        return Base64.getUrlEncoder().withoutPadding()
            .encodeToString(text.getBytes(StandardCharsets.UTF_8));
    }

    private static String decode(String segment) {
        return new String(
            Base64.getUrlDecoder().decode(segment),
            StandardCharsets.UTF_8
        );
    }

    private static byte[] hmac(String signingInput)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(DEMO_SECRET, "HmacSHA256"));
        return mac.doFinal(
            signingInput.getBytes(StandardCharsets.US_ASCII));
    }

    private static String issue(String payload)
            throws GeneralSecurityException {
        String input = encode(HEADER) + "." + encode(payload);
        String signature =
            Base64.getUrlEncoder().withoutPadding()
                .encodeToString(hmac(input));
        return input + "." + signature;
    }

    private static boolean signatureValid(String token)
            throws GeneralSecurityException {
        String[] parts = token.split("\\.", -1);
        if (parts.length != 3) {
            return false;
        }
        try {
            // Accept only the fixed header in this illustrative model.
            if (!HEADER.equals(decode(parts[0]))) {
                return false;
            }
            byte[] received =
                Base64.getUrlDecoder().decode(parts[2]);
            byte[] expected = hmac(parts[0] + "." + parts[1]);

            return MessageDigest.isEqual(received, expected);
        } catch (IllegalArgumentException invalidBase64) {
            return false;
        }
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        String payload = "{\"sub\":\"alice\",\"scope\":\"read\"}";
        String token = issue(payload);
        String[] parts = token.split("\\.", -1);

        System.out.println("Parts: " + parts.length);
        System.out.println("Header: " + decode(parts[0]));
        System.out.println("Payload: " + decode(parts[1]));
        System.out.println("Valid signature: " + signatureValid(token));

        String changedPayload =
            "{\"sub\":\"admin\",\"scope\":\"read\"}";
        String tampered = parts[0] + "." +
            encode(changedPayload) + "." + parts[2];

        System.out.println("Tampered valid: " +
            signatureValid(tampered));
    }
}
```

Compile and run (JDK 17+):

```bash
javac JwtStructureDemo.java
java JwtStructureDemo
```

Exact stdout of the program:

```text
Parts: 3
Header: {"alg":"HS256","typ":"JWT"}
Payload: {"sub":"alice","scope":"read"}
Valid signature: true
Tampered valid: false
```

Analysis:

1. `Header` and `Payload` can be printed **without the secret**, because JWS does not encrypt those two parts.
2. A valid MAC proves the bytes in those two parts have not been altered **relative to the demo key**, yet does not prove the token contains a valid identity, issuer, audience, or expiration.
3. Changing the payload to `sub=admin` while keeping the old signature causes HMAC verification to return `false`.
4. An attacker **possessing the HMAC secret** can sign new payloads themselves, so secret protection, rotation, and distribution scope are critical.
5. The program fixes the algorithm to HS256 for illustration. In real applications, **do not write your own decoder/validator**, do not rely on a token's header to accept arbitrary algorithms, and do not use demo data in production.

## 6. How Signed JWTs (JWS) Differ from Encrypted JWTs (JWE)

A JWT can use **JWS** or **JWE**, per RFC 7519. Compact JWS has **3 parts**; compact JWE has **5 parts**:

```text
JWS (commonly seen in APIs):
BASE64URL(protectedHeader)
.
BASE64URL(payload)
.
BASE64URL(signature)

JWE Compact Serialization:
BASE64URL(protectedHeader)
.
BASE64URL(encryptedKey)
.
BASE64URL(initializationVector)
.
BASE64URL(ciphertext)
.
BASE64URL(authenticationTag)
```

Note that `encryptedKey` may be **empty** under certain key management modes such as direct encryption, yet compact JWE format still has all **five positions**, separated by four dots.

### 6.1. JWS: Protects Integrity, Yet Typical Payloads Are Visible

With a Base64url-encoded JWS payload, anyone holding the token can decode the JSON. Do not treat `iat`, `sub`, email, role, tenant ID, or business metadata as secret merely because they reside inside a token.

For example, when QA sees:

```json
{"alg":"RS256","typ":"JWT"}
```

and a payload:

```json
{"sub":"alice","scope":"orders.read"}
```

being able to read `sub=alice` **does not mean** someone can change it to `sub=admin` and still have a valid token: altering the payload invalidates the signature if the server verifies properly. **Tamper protection is not data hiding.**

### 6.2. JWE: Encrypts Data, Yet Still Requires Validating Claims

JWE uses key management and content encryption algorithms, typically with an authentication tag to detect ciphertext tampering. An authorized recipient decrypts to obtain the payload; outsiders without the corresponding key cannot easily read the claims. Even after decryption, however, the backend **must still validate** issuer/audience/expiration, token purpose, permissions, and other constraints. Never accept a token merely because it "decrypted cleanly".

If you need both **issuer signature** and **secrecy from outsiders**, you can use a **nested JWT**, such as signing a JWS and then encrypting that JWS inside a JWE per an appropriate profile. Both layers must be verified in the right order and per application policy, avoiding custom cryptographic protocol implementations.

### 6.3. JWTs Do Not Automatically Have to Be Signed

The specification permits **Unsecured JWTs** as JWS with `alg=none` and an empty signature segment. This **does not** mean a Resource Server should accept them; for authentication/authorization, design a policy that accepts only permitted algorithms and verifies signatures/MACs or a clearly defined protection mechanism. For ordinary bearer access tokens, **reject `alg=none`**.

There is no rule saying "three parts equals secure". Three segments only indicate compact JWS syntax; **keys and verification logic determine trustworthiness**.

## 7. JWT Is Not an Access Token, and an Access Token Is Not Automatically a JWT

There are three independent concepts:

- **JWT:** a format for claims.
- **Access token:** a credential presented by a client to a resource server when calling an API; it can be a JWT **or an opaque token** whose structure cannot be read by the client.
- **ID token (OpenID Connect):** a JWT enabling the client to verify a user authentication event under OIDC; its audience is typically the client application. **Do not default to using an ID token as an access token** to call APIs.

Especially dangerous is **cross-JWT confusion**: a validly signed ID token for the frontend can have a very convincing `sub` and `iss`, yet **`aud` is not the API**. If an API only checks signatures and skips audience/token-purpose checks, it may accept the wrong kind of token.

Every JWT used for authentication at a Resource Server must be evaluated against a concrete **profile**: is it an access token meant for this API, is the issuer trusted, does the token type/`typ` match if required by the profile, which claims/scopes apply, and is there client binding or proof-of-possession? Do not equate "cryptographically valid token" with "token valid at every endpoint".

## 8. What a Resource Server Must Verify

Logical steps for a bearer JWT received over HTTP:

```text
Request
  └─ Authorization: Bearer <access-token>
          ↓
       JWT Decoder
          ├─ Valid compact syntax, base64url, JSON
          ├─ Permitted algorithm, never trusting arbitrary alg
          ├─ Select key from preconfigured trust store/JWKS
          ├─ Verify signature or MAC
          └─ Validate claims: iss, aud, exp, nbf, ...
          ↓
       Verified Authentication
          ↓
       Convert scope/role/permission → GrantedAuthority
          ↓
       HTTP authorization: method/path/authority
          ↓
       Resource authorization: tenant/owner/state
          ↓
       Controller / service
```

If any mandatory condition fails, reject the request. Never "fall back" to parsing an unsigned payload to allow access. Also never let the client supply an issuer/JWKS URL for the server to decide where to fetch public keys.

### 8.1. `iss` — Correct Issuer

An API should accept only issuers configured as trusted token sources. An attacker can create a JWT and sign it with their own key; that still **does not make them an issuer the API trusts**. `iss` must be checked alongside the signature/key chain tied to that issuer.

### 8.2. `aud` — Token Issued for the Right API

One issuer can issue tokens for multiple resource servers. A token valid for `billing-api` is **not automatically valid** for `orders-api`. If a resource server omits `aud`, a token from one service can be presented to another service (**token substitution / confused deputy**).

`aud` can be a string or an array of strings. The API must verify that the expected audience **is present** according to the issuer and profile rules; do not use `sub` or `client_id` as a substitute for audience unless policy defines it.

### 8.3. `exp`, `nbf`, and `iat`

- `exp`: expiration; reject the token once current time reaches/passes expiration per clock skew policy.
- `nbf`: before this timestamp, the token must not be used.
- `iat`: issuance time; can check maximum age or reasonable issuance time, though **`iat` alone does not replace `exp`**.
- All use **seconds** in JWT NumericDate, not UNIX milliseconds as many Java/JavaScript applications mistakenly assume.
- Synchronize clocks across systems and configure a **small, intentional** leeway/clock skew; never widen leeway excessively to mask system bugs.

### 8.4. Authority, Scope, and Business Authorization

Spring Security by default typically maps token scopes into authorities of the form `SCOPE_<scope>`. For example, a token containing `"scope": "orders.read orders.write"` can produce `SCOPE_orders.read` and `SCOPE_orders.write` with an appropriate converter.

**Do not assume**:

- Claim `role=ADMIN` automatically becomes `ROLE_ADMIN`.
- `scope=orders.read` means reading all orders across all tenants.
- Holding a valid token is sufficient to modify a record by ID.
- A matching `aud` without the user having the role still grants admin access.

Per-record permissions must rely on the verified principal and check `owner/tenant/state` in the service/data layer, never trusting `tenant_id` or `userId` from a JSON request body when it conflicts with the authenticated identity.

## 9. Security Pitfalls When Handling JWTs

### 9.1. Decoding Only Without Verifying

**Wrong:**

```text
token.split(".")
→ Base64url decode payload
→ parse JSON
→ if roles contains ADMIN then allow
```

Clients can freely forge the `roles` claim if the backend does not verify the signature. "Reading a JWT" with a simple decoder is not "authenticating a JWT". Even if a decoder returns plausible-looking claims, **never use claims to grant permissions** before verification completes.

### 9.2. `alg=none` and Algorithm Confusion

Never let a JWT skip verification because its header says `"alg":"none"`. Never automatically switch between HS256/RS256 merely based on the token's `alg` string. Some legacy implementation flaws mistakenly treated an RSA public key as an HMAC secret when engines mixed algorithms and key types; safe libraries must bind algorithm/key kind via configuration, never via attacker-supplied input.

**Rule:** on the API, valid keys and algorithms must be determined by **trusted configuration**. Support only the specific algorithms your system actually needs; never allow "all JOSE algorithms".

### 9.3. `kid`, `jku`, and Key-Selection Attacks

`kid` helps rotate keys, yet a new `kid` value does not automatically make a JWT trustworthy. Look up keys only in the preconfigured **JWKS/trust store** of the issuer, over HTTPS with proper trust chain validation. Never take `jku` or `x5u` from a token and issue an HTTP GET to an arbitrary URL (SSRF/trust injection). Never use `kid` directly as an unchecked file path or SQL string.

When an issuer rotates keys, JWKS can change over time; caching/refreshing must behave properly, yet **never fall back to an untrusted key** when a key is not found.

### 9.4. Missing Audience, Token Type, and Issuer Binding

A token signed with an accepted key yet meant for another client/API must still be rejected by `aud`/purpose. Maintain dedicated test cases for valid vs. invalid issuer, valid vs. invalid audience, expired tokens, and not-yet-active tokens. Do not mix identity tokens with access tokens merely because their JSON claims look similar.

### 9.5. Leaking Payloads or Tokens via Auxiliary Systems

Bearer tokens are credentials: whoever obtains one can try using it while valid. JWS payloads are trivial to decode. Never put tokens into query parameters, crash reports, support tickets, error responses, browser consoles, access logs, analytics, screenshots, or third-party decoding tools with production tokens. Mask/redact `Authorization` in proxies, observability, and all client logs.

### 9.6. Token Still Valid After User Logout or Role Change

Self-contained signed JWTs can be verified locally by an API without querying the issuer on every request. Consequently, a token whose `exp` has not passed can remain valid even after the user clicks logout or loses a role, **unless** the system has revocation/denylisting, token versioning, introspection, or dedicated controls. Remedies depend on the threat model: short-lived access tokens, refresh token rotation, revocation with event-driven cache invalidation, or opaque tokens with introspection when immediate control is required. Do not assume the mere presence of `jti` makes a token revocable automatically.

## 10. Spring Boot MVC Example: Resource Server Validating JWTs

Below is a configuration **usable in a Spring Boot Servlet/MVC application**. It does not issue tokens itself: it requires a **real authorization server/issuer**, JWKS or trusted public keys, and a valid JWT access token issued by that issuer. URLs like `issuer.example.com` are **illustrative addresses, not live issuers you can run against directly**.

### 10.1. Maven Dependencies

In your Spring Boot 3.x application's `pom.xml`, include the corresponding starters:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
</dependencies>
```

You need the Spring Boot parent/BOM to manage compatible versions and Java 17+. Do not add a separate JWT parsing library and bypass the Resource Server decoder when the framework already handles it.

### 10.2. `application.yml` with Issuer and Audience

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://issuer.example.com"
          audiences:
            - "orders-api"
```

In Spring Boot 3.5, `issuer-uri` configures trust toward the issuer/metadata/JWKS per settings, while `audiences` sets the audience the resource server expects in `aud`. With standard Spring Security configuration, the JWT decoder also verifies signatures and timestamps like `exp`/`nbf`. If the application uses a custom `JwtDecoder` or different security configuration, verify that all validators are properly attached.

If the issuer exposes JWKS at a custom URI, you can additionally configure `jwk-set-uri` per provider docs **together with `issuer-uri`** so `iss` is still validated while avoiding startup discovery dependency. Point JWKS only to a **trusted configured endpoint**, never taking a URL from `jku` in a token.

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://issuer.example.com"
          jwk-set-uri: "https://issuer.example.com/oauth2/jwks"
          audiences:
            - "orders-api"
```

This snippet is an **alternative configuration option**, not meant to duplicate both YAML blocks. The JWKS address must be the issuer's real endpoint, compatible with TLS, key rotation, and deployment policy.

### 10.3. `JwtApiSecurityConfig.java`

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class JwtApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
```

This is a **Spring configuration class** that must reside in a Java 17+/Boot 3.x application package with the starters above; it does not compile standalone with just `javac`. It demonstrates **bearer JWT authentication** via `Authorization: Bearer <token>`, not HTTP Basic or self-signing tokens.

Explanation:

1. Incoming API requests carry `Authorization: Bearer <access-token>`. The Resource Server decoder verifies signatures and claims against configured issuer/audience/time rules.
2. After verification, Spring Security creates an `Authentication` with authorities mapped from claims, such as `SCOPE_orders.read`. Exact `scope` claims and authority formats must be verified against the real issuer.
3. `GET /api/orders/**` requires `SCOPE_orders.read`; `POST` requires `SCOPE_orders.write`. A validly signed token lacking the permission still receives **403**.
4. `anyRequest().denyAll()` denies unlisted methods/routes to reduce the risk of new endpoints being exposed unintentionally.
5. `SessionCreationPolicy.STATELESS` instructs Spring Security not to use an HTTP session to store the security context; it **does not mean** the whole application cannot create state in other components.
6. The example does not disable CSRF. With a pure header-based bearer token API without cookies/sessions automatically sent by browsers, the threat model can differ from cookie-based apps; evaluate CSRF policy **based on actual architecture**, rather than disabling it out of habit.
7. The resource server only protects the HTTP layer. If a holder of `orders.read` may only view orders belonging to their own tenant, the service/repository must also check tenant/owner/state.

### 10.4. Calling the API with a Valid JWT

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.example.signature
```

**The token string above is an illustrative shape only, not a valid JWT.** In practice, use a JWT issued by your issuer over HTTPS. When a token is missing or signature/claims are invalid, the API typically returns `401` with `WWW-Authenticate: Bearer...` per RFC 6750; when the token is valid but lacks permissions, typically `403`. Do not rely solely on HTTP status codes instead of checking logs/exceptions/test fixtures, because other security policies can produce the same status.

### 10.5. Controllers Only Work with the Verified Principal

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class JwtDemoController {

    @GetMapping("/api/orders/whoami")
    public String whoAmI(@AuthenticationPrincipal Jwt jwt) {
        return jwt.getSubject();
    }
}
```

Under the route policy in the example, `GET /api/orders/whoami` requires `SCOPE_orders.read`. Spring Security injects the `Jwt` after verification; the controller does not need `Base64url.decode` to decide who the caller is. Never log the raw JWT, and never turn `sub` directly into permission to access every order. This method must be called inside an application configured with OAuth2 Resource Server and a real issuer.

## 11. Spring WebFlux: Same Principles, Different Reactive Chain

A WebFlux Resource Server uses `ServerHttpSecurity` and `SecurityWebFilterChain` instead of `HttpSecurity`/`SecurityFilterChain`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveJwtSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

- Use `spring-boot-starter-webflux` + `spring-boot-starter-security` + `spring-boot-starter-oauth2-resource-server`.
- The same `spring.security.oauth2.resourceserver.jwt.issuer-uri` and `audiences` properties apply to both Servlet and Reactive in Spring Boot.
- JWT verification executes inside the reactive security pipeline. If custom logic must perform async IO/repository calls, use `Mono`/`Flux` and Reactor Context; **never manually call `block()`/`subscribe()`** to check permissions.
- The WebFlux snippet is configuration for a **separate reactive application**, not to be placed alongside MVC configuration as if both builders handled the same HTTP runtime.
- `@AuthenticationPrincipal Jwt` or the appropriate reactive principal mechanism reads the verified subject; business authorization is still required before returning data.

## 12. JWT Validation and Authorization: Required Test Matrix

Design test fixtures with a valid issuer, trusted signing keys, the current API audience, and negative cases. Never check only "token parses" or "endpoint returns 200".

| Scenario | Expectation |
|---|---|
| Protected endpoint called without bearer token | **401** / appropriate challenge |
| Token with tampered payload keeping original signature | **401** due to invalid signature/MAC |
| Token signed by an unknown issuer with their key | Rejected as outside trust chain |
| Header `alg=none` or disallowed algorithm | Rejected |
| `kid` not found in trusted JWKS | Rejected; do not fetch unknown keys |
| JWT past `exp` | Rejected |
| JWT before `nbf` | Rejected |
| `iss` does not match configured issuer | Rejected |
| `aud` missing `orders-api` | Rejected despite valid signature |
| Valid issuer/audience/time token with only `orders.read` calling POST | **403** due to missing write scope |
| Token with `orders.read` requesting another tenant's order | Denied at business authorization layer |
| JWS payload readable after decode | **Normal behavior**, not a cryptography bug |
| JWE ciphertext unreadable without key | **Expected behavior** of encryption |
| Frontend ID token sent instead of access token to API | Rejected due to wrong purpose/audience |

### 12.1. MockMvc Tests: Separating Authorization Tests from Cryptographic Validation Tests

`spring-security-test` provides the `jwt()` request post-processor to build a mock `JwtAuthenticationToken` in **authorization** tests. Example excerpt with configured `MockMvc` and matching routes:

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

mockMvc.perform(get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
```

**Important warning:** `.with(jwt())` **skips real JWT signature verification** because it mocks authentication for tests; it is only suitable for testing authority/endpoint mappings. To prove invalid signatures/wrong issuers/wrong audiences are blocked, write integration tests sending a **real Bearer header** through `BearerTokenAuthenticationFilter` and `JwtDecoder`/trusted public JWKS keys, using JWTs signed with test keys.

Furthermore, `status().isOk()` passes only if the `/api/orders/42` controller exists, the fixture has data, and it returns 200. If no real route exists yet, the test can return 404 after passing the security gate. Do not mistake 404 for cryptographic validation failure.

### 12.2. Test Cases Requiring Trusted Fixtures

For real integration tests:

1. Create a dedicated test issuer and test key pair. Never use production keys in unit tests.
2. Issue a valid JWT with the right `iss`, `aud`, `exp`; verify the API accepts it and maps scopes properly.
3. Flip one byte of payload/signature; confirm the JWT is rejected.
4. Create a JWT signed with another key, another algorithm, and a `kid` absent from the trusted JWKS; confirm fail-closed behavior.
5. Create an expired JWT and a not-yet-active `nbf` JWT; test the defined small clock skew.
6. Create a token for another audience and an ID-token profile not meant for the API; confirm rejection.
7. Send a token with read scope but without write scope; confirm 403 at the HTTP layer.
8. Send a valid token for an order belonging to another tenant; confirm data cannot be read and no side effects occur.

Equivalent tests in WebFlux can use `WebTestClient` and `mockJwt()` support to test HTTP authorization. Keep mocked security tests clearly separated from cryptographic validation tests.

## 13. TTL, Token Rotation, and Client-Side Security

A JWT signature does not replace lifecycle management:

- **Short-lived access tokens:** reduce the replay window if a token is stolen.
- **Refresh tokens:** use appropriate secure channels and storage; in applications needing revocation control, apply refresh rotation, reuse detection, and revocation.
- **Issuer key rotation:** JWKS can hold multiple public keys by `kid` during transitions; the server trusts only keys from trusted issuers. Have procedures for rotating keys, revoking compromised keys, and managing caches.
- **Logout:** deleting tokens on the client does not automatically invalidate an unexpired JWT if the API verifies offline. If "immediate logout" is required, consider `jti` denylists, introspection/opaque tokens, or other revocation architectures.
- **Least-privilege scopes:** do not issue an access token with every permission merely for frontend convenience.
- **Protect storage:** stolen bearer tokens are typically replayable; assess XSS, `HttpOnly`/`Secure`/`SameSite` cookies, CSRF, token storage, and API gateways against your actual design. No browser-side token storage is completely immune if the page suffers XSS.
- **Keep tokens out of URLs:** query strings easily appear in browser history, referrers, and logs.
- **Avoid sensitive claims in JWS:** any token holder can decode the payload; include only minimal claims.
- **TLS:** HTTPS is required when transmitting bearer tokens, even signed ones; signatures do not prevent eavesdroppers from **copying** a token and replaying it.

## 14. Common Conceptual Mistakes

1. "A JWT has three parts and looks unreadable, so it is encrypted." — **False**; JWS typically only Base64url-encodes header/payload.
2. "If the signature is valid, it's the right user and right API." — **False**; you still must check issuer, audience, subject, expiration, token type, permissions, and key trust.
3. "Just Base64url-decode the payload to log the user in." — **False**; without verification, attackers can alter claims.
4. "Seeing `alg=RS256` means fetching the public key from the token's `jku` URL." — **False**; URLs and keys must come from the issuer's trust configuration.
5. "Setting `alg=none` disables signatures for a demo; it's fine in production." — **Unsafe** for bearer authentication.
6. "HS256 uses a public key like RS256." — **False**; HS256 uses a symmetric secret, while RS256 uses a private/public key pair.
7. "Once a JWT is signed, additional encryption is unnecessary for any data." — **False**; confidential data requires JWE or an appropriate protection mechanism.
8. "If a JWE decrypts, that's enough to trust it." — **False**; you must still validate policies, claims, and sender/recipient authenticity.
9. "`exp` in a JWT is in milliseconds." — **False**; NumericDate is typically in seconds.
10. "Having `sub` means `aud` isn't needed." — **False**; subject and token recipient are distinct.
11. "JWT access tokens and OIDC ID tokens are interchangeable." — **False**; they differ in purpose, profile, and audience.
12. "Having the ADMIN role allows reading all tenants." — **False**; per-resource/tenant policies are still required.
13. "`kid` may point to any key." — **False**; select only from a preconfigured trusted key set.
14. "On logout, all old JWTs are automatically invalidated." — **False**; signed tokens remain usable until expiration without a revocation mechanism.
15. "A validly signed token prevents theft." — **False**; stolen bearer tokens can be replayed.
16. "`MockMvc.with(jwt())` proves the server verifies signatures properly." — **False**; that helper mocks authentication and does not run the real JWT decoder.
17. "Disabling CSRF is mandatory for every API using JWT." — **Not a universal rule**; the threat model depends on browser/cookie auto-submission and the authentication mechanism.
18. "Just take scopes from any string to build authorities." — **False**; trust only claims from verified JWTs and configured mappings.
19. "Having JWE encryption means TLS isn't needed." — **False**; TLS remains essential for metadata, replay defense, bearer token protection, and overall transport security.
20. "A JSON token parsing library alone can replace Spring Security Resource Server." — **False**; full cryptographic verification and security policies are required.

## 15. Pre-Deployment Checklist for a JWT Resource Server

- [ ] Identify whether tokens use JWS or JWE; never treat Base64url as encryption.
- [ ] Accept only the exact JWT profile/algorithms from a trusted issuer; never allow `alg=none` for bearer authentication.
- [ ] Select keys from a configured JWKS/trust store; never trust URLs from token headers.
- [ ] Verify signature/MAC before using claims; for JWE, decrypt and validate protection layers properly.
- [ ] Validate `iss`, `aud`, `exp`, `nbf`, and policy-required claims; NumericDate is in seconds.
- [ ] Enforce token type/purpose; never use OIDC ID tokens as API access tokens.
- [ ] Test mapping `scope`/`roles`/`permissions` to `GrantedAuthority`, without guessing prefixes.
- [ ] Verify HTTP authorization alongside business authorization for owner/tenant/state.
- [ ] Never place passwords, secrets, or unnecessary PII in JWS payloads.
- [ ] Require HTTPS for all bearer token requests; redact `Authorization` in logs/traces/access logs.
- [ ] Explicitly document strategies for token TTL, refresh rotation, key rotation, and revocation/logout.
- [ ] Test valid tokens, bad signatures, wrong issuer/audience, invalid `exp`/`nbf`, unknown `kid`/`alg`, and insufficient permissions.
- [ ] Separate mock JWT authorization tests from integration tests using a real decoder.
- [ ] For Servlet/WebFlux, configure the right builder, filter chain, and decoder type.

## 16. Standards and Spring Security Documentation

- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): defines JWT, claims, JWS/JWE, unsecured JWTs, and validation.
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515): protected header, payload, signature, and compact serialization.
- [RFC 7516 — JSON Web Encryption](https://www.rfc-editor.org/rfc/rfc7516): ciphertext, key management, and five-part compact JWE.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm confusion, token substitution, issuer/audience, and key management.
- [Spring Security — Servlet OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): decoder, issuer, audiences, JWKS, authentication, and scopes.
- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): verifying JWTs in WebFlux.
- [Spring Boot 3.5 — Spring Security / Resource Server](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html): `issuer-uri`, `jwk-set-uri`, `audiences`, and application configuration.

**Remember:** JWTs **are not encrypted by default**. In compact JWS, the header and claims payload are only **Base64url-encoded** and thus publicly readable; the signature/MAC protects **integrity and authenticity under a trusted key**, not information hiding. When content confidentiality is needed, use JWE or an alternative design. In Spring Security, an `Authentication` is created only after the token passes issuer/key/algorithm/claims verification per policy, and endpoint plus resource-level permissions must still be enforced.