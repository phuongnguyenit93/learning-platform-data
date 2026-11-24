# Implementing ReactiveAuthenticationManager for API Keys

## 1. Context, Objectives, and Scope

This lesson belongs to **Advanced Authentication** in **Spring Security - reactive / Spring WebFlux**.

Many APIs for integration services, scheduled jobs, CLIs, or partners use an **API key**: a secret string sent by the client with each request, for example in an `X-API-Key` HTTP header. The server must check that the key exists, matches the secret, is still valid, has not been revoked, and carries specific permissions. With Spring Security WebFlux, you can integrate this mechanism into the **standard authentication pipeline** instead of writing a custom `WebFilter` that assigns an arbitrary principal.

Three core components:
- **`ServerAuthenticationConverter`**: extracts the credential from the HTTP request and builds an **unauthenticated** `Authentication`.
- **`ReactiveAuthenticationManager`**: verifies the credential via an asynchronous repository/service and returns an **authenticated** `Authentication` or an error.
- **`AuthenticationWebFilter`**: connects the converter and manager, stores the result in the reactive `SecurityContext`, and handles success/failure.

After this lesson, you will be able to:

1. Explain why an API key is a **bearer secret**, not a JWT carrying claims or a user password.
2. Understand the `Mono<Authentication>` contract of `ReactiveAuthenticationManager.authenticate(...)`: `Mono.just` when valid, `Mono.empty` when the manager does not handle that `Authentication` type, and `Mono.error(AuthenticationException)` when the credential matches the supported type but is invalid.
3. Design an API key with a **public key ID** and a **≥256-bit random secret**, storing its **digest** instead of the raw API key and verifying the hash with constant-time comparison.
4. Write a custom `ApiKeyAuthenticationToken` with **unauthenticated → authenticated** states, never placing the secret into the principal or authorities.
5. Write a `ServerAuthenticationConverter` that reads `X-API-Key` and rejects empty, oversized, duplicated, or malformed headers.
6. Write a `ReactiveAuthenticationManager` without calling `block()` or synchronous I/O on the Netty event loop, reading key records and checking `enabled`, `expiresAt`, and authorities.
7. Configure `AuthenticationWebFilter` via `ServerHttpSecurity.addFilterAt(..., SecurityWebFiltersOrder.AUTHENTICATION)`, a stateless security context, and a 401/403 policy.
8. Run a **Java 17+, Spring Boot 3.3.5** example using Gradle, curl, and `StepVerifier` + `WebTestClient` tests.
9. Identify limitations of an in-memory demo store, how to replace it with Redis/R2DBC, key rotation/revocation, rate limiting, auditing, TLS, and preventing key leaks via logs/proxies.
10. Distinguish API key authentication from authorization by scope, ownership, tenant, and browser/CORS/CSRF integration scenarios.

**Important:** This demo uses **a single API key provisioned at startup via an environment variable** and a single-JVM repository to focus on learning the pipeline. It is not a production key management solution: production requires secure provisioning, a shared store, revocation state, auditing, rotation, scoped permissions, and a consistency model.

## 2. What Is an API Key Used For?

An integrating client might send:

```http
GET /api/data HTTP/1.1
Host: api.example.test
X-API-Key: ak_demo_<SECRET_BASE64URL>
Accept: application/json
```

`<SECRET_BASE64URL>` is a documentation placeholder, **not a real key**. Servers should not pass keys in query parameters:

```http
GET /api/data?api_key=real-secret HTTP/1.1
```

because query strings are easily captured in access logs, browser history, analytics, `Referer` headers, or support screenshots. Keep API keys out of URLs, logs, and response bodies. Always use **valid HTTPS/TLS** when sending keys over a network; plain HTTP on localhost is for demos only.

### How Do API Keys, HTTP Basic, OAuth2, and JWT Differ?

| Mechanism | Credential | How It Is Verified | Typical Use Case |
| --- | --- | --- | --- |
| API key | Application secret issued by the system | Look up key ID, check secret + status + permissions | Machine-to-machine, partner integration |
| HTTP Basic | Username/password or credential pair | UserDetails/password validation | Legacy APIs/protocols, requires TLS |
| OAuth2 Client Credentials | Access token issued by an Authorization Server | JWT verification or introspection | Delegated/service authorization with token lifecycle |
| JWT bearer | Signed token carrying claims/time/audience | Signature/issuer/audience/expiry | Self-contained access token |
| Opaque bearer token | Non-self-decoding string | Online token introspection | Centralized token status/revocation |

**An API key is usually a bearer credential:** anyone possessing the full key string can attempt to use it until it expires or is revoked. It does not inherently include MFA, signed claims, auto-expiry, or rotation; those features must be built into the server-side key registry.

### Do Not Confuse Authentication with Authorization

**Authentication:** "Does the string `ak_demo_...` genuinely belong to client `demo-client` and is it still valid?"

**Authorization:** "Is client `demo-client` allowed to call `GET /api/data` or `POST /api/admin`? Does it have permission on the requested tenant/resource?"

In Spring Security, the authentication step populates authorities such as `SCOPE_data:read`. Afterward, `authorizeExchange(...)` or method/business authorization evaluates those authorities and the current data. A valid API key **does not automatically allow everything**.

## 3. Spring Security Reactive Processing Flow

```text
HTTP request
      |
      v
WebFlux SecurityWebFilterChain
      |
      v
AuthenticationWebFilter
      |
      +--> requiresAuthenticationMatcher("/api/**")?
      |         |
      |        No -> skip filter
      |         |
      |        Yes
      |         v
      |    ApiKeyHeaderConverter
      |         |
      |         +-- Missing header -> Mono.empty()
      |         |    (unauthenticated, handled downstream by authorization)
      |         |
      |         +-- Malformed/duplicate header -> AuthenticationException
      |         |
      |         v
      |    ApiKeyAuthenticationToken (authenticated=false)
      |         |
      |         v
      |    ApiKeyReactiveAuthenticationManager.authenticate(...)
      |         |
      |         +-- Unsupported token type -> Mono.empty()
      |         +-- Wrong/disabled/expired key -> Mono.error(...)
      |         +-- Valid key -> authenticated Mono<Authentication>
      |         |
      |         v
      |    AuthenticationWebFilter places result into Reactor Context
      |
      v
authorizeExchange:
    authenticated / hasAuthority / denyAll
      |
      +-- Unauthenticated --> 401
      +-- Authenticated, insufficient authority --> 403
      +-- Authorized --> Controller
```

### Why Not Just Write a Custom WebFilter and Set a Header?

Spring Security already provides:
- Clear separation between **authentication failure** and **authorization denial**.
- Standardized `Authentication`, `GrantedAuthority`, and `ReactiveSecurityContextHolder`.
- Placing authentication in the **Reactor Context**, fitting reactive pipelines.
- Compatibility with `@PreAuthorize` (when reactive method security is enabled), `ServerHttpSecurity.authorizeExchange`, tests, and security entry points.
- Guardrails against writing a filter that skips full key-status checks or marks `authenticated=true` before verification.

If you only check headers inside controllers, new routes easily miss validation; if you leave `permitAll()` on the chain and guard each endpoint manually, a single oversight can expose the API. Placing authentication in the filter chain and **denying by default** is far safer.

### Reactor Context Is Not Directly ThreadLocal

In WebFlux, authentication is propagated through `ReactiveSecurityContextHolder`/Reactor Context. Do not use traditional ThreadLocal `SecurityContextHolder.getContext()` in custom reactive code and expect it to survive `publishOn`/`flatMap`. Let `AuthenticationWebFilter` populate the context; controllers can accept `Principal` or services can read the reactive context.

## 4. The ReactiveAuthenticationManager Contract

Interface:

```java
@FunctionalInterface
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
```

Three outcomes you must understand precisely:

| Scenario | Result | Meaning |
| --- | --- | --- |
| Manager successfully authenticates a supported credential | `Mono.just(authenticatedAuthentication)` | Principal and authorities are verified |
| Manager **does not support** this `Authentication` type | `Mono.empty()` | No decision; another manager can handle it if composed |
| Manager supports this type, but credential is **wrong, expired, or revoked** | `Mono.error(AuthenticationException)` | Authentication failed, returns 401 via failure handler |
| Repository/network error | Typically propagate error per policy | Store errors must never be treated as "valid key" |

**Crucial distinction:** Never return `Mono.empty()` for an **invalid API key**. In a chain with multiple authentication managers, empty can cause another manager to run or lose failure context. Never use `Mono.just(authentication)` to return an **unauthenticated** token, as that is not a successful authentication.

### A Minimal Manager (Illustrative, Not Complete Source)

```java
@Override
public Mono<Authentication> authenticate(Authentication candidate) {
    if (!(candidate instanceof ApiKeyAuthenticationToken token)
            || token.isAuthenticated()) {
        return Mono.empty(); // Does not handle this type
    }
    return keyRepository.findById(...)
            .flatMap(record -> verifyThenBuildAuthentication(record, token));
}
```

This is a **contract-illustration fragment**; runnable source is in Section 9 and does not use `...` placeholders. It shows branching by **authentication type** before querying the key registry.

### Marking Authenticated at the Right Time

A custom `Authentication` typically has two states:
- **Before authentication:** principal is untrusted; credentials hold the raw API key; `isAuthenticated() == false`; authorities are empty.
- **After authentication:** principal is the client ID/identity verified by the repository; credentials are **null/erased**; `isAuthenticated() == true`; authorities are granted by the server from the record, **never from HTTP headers**.

Never accept request headers like `role=ADMIN` or `scope=admin:write` and turn them into authorities: clients can forge headers. Authorities must come from **trusted server-side metadata**.

## 5. Designing Secure API Keys

### 5.1. Separating Public Identifier and Secret

A convenient format:

```text
ak_<keyId>_<base64url-of-32-random-bytes>
```

For example `ak_demo_...`, where:
- `ak_` is a prefix identifying the credential type.
- `keyId` is an identifier used for lookup, **not a secret**. The demo limits it to 1–32 alphanumeric or `-` characters.
- The secret part contains **32 random bytes from SecureRandom** (256 bits of entropy), unpadded Base64URL-encoded to 43 characters.

Benefits:
1. Look up the record by key ID instead of scanning all hashes.
2. Revoke or rotate individual keys independently.
3. Audit by **key ID** (without storing raw keys).
4. Enforce permissions per client, expiry, tenant, and policy.

**Key takeaway:** A prefix/key ID adds **zero** security if the secret is guessable. True 256-bit randomness is required; never use `password123`, timestamps, name-based UUIDs, emails, sequential numbers, or `Math.random()` as secrets.

### 5.2. Store Only the Secret Digest

Logical table example:

| Field | Meaning | Is It Secret? |
| --- | --- | --- |
| `key_id` | Public identifier | No |
| `client_id` | Authenticated principal | Not directly |
| `secret_sha256_hex` | Digest of the 32-byte secret | Security-sensitive, never expose publicly |
| `scopes` | Server-assigned permissions | Must never be trusted from request |
| `enabled` | Revocation/lock status | Internal policy |
| `expires_at` | Expiration timestamp | Internal policy |
| `tenant_id` | Tenant/scope boundary | Business data |
| `created_at`/`last_used_at` | Audit without raw secrets | Per retention/privacy policy |

Because the secret is **randomly generated with high entropy**, SHA-256 of the secret bytes can serve as a verifier rather than a slow password hash. For **human-chosen passwords**, you must use proper password hashing (Argon2/bcrypt/scrypt) due to low entropy; do not copy the API key hashing approach for storing passwords.

Some systems use **HMAC-SHA-256 with a server-side pepper** for an extra layer of defense if the verifier database is leaked. In that case, manage the pepper via KMS/secret manager with rotation and versioning support. Do not treat SHA-256 as encryption; the raw key is shown once at provisioning and cannot be recovered from the database.

### 5.3. Constant-Time Digest Comparison

Wrong:

```java
// ANTI-PATTERN: naive String comparison of raw secret/digest.
if (storedSecret.equals(rawApiKeyFromRequest)) {
    // allow
}
```

Better for fixed-length verifier digests:

```java
byte[] expectedDigest = HexFormat.of().parseHex(storedSha256Hex);
byte[] actualDigest = MessageDigest
        .getInstance("SHA-256")
        .digest(secretBytes);
boolean same = MessageDigest.isEqual(expectedDigest, actualDigest);
```

This is a **fragment**; you must handle `NoSuchAlgorithmException`, metadata lookup, expiry, and identity, as shown in the complete source in Section 9. `MessageDigest.isEqual` avoids naive byte-by-byte short-circuiting, though it **does not by itself prevent** timing leaks from whether a key ID exists. If your threat model requires resisting timing-based enumeration, hash against a dummy digest even when the key ID does not exist, return uniform client errors, and apply rate limiting.

### 5.4. What Permissions Should One Key Have?

For an integration application's API key:
- Client identity: `demo-client`, not a browser user.
- Authorities: `SCOPE_data:read`, not `ROLE_ADMIN` unless business policy specifically requires it.
- Tenant/owner: in multi-tenant systems, metadata must record tenant scope and the business layer must verify resource ownership.
- Allowed routes/methods: expressible via authorization policy.
- Expiration/revocation: must be checked per request or via a cache with a clear SLA.
- Rate limit/quota: per key ID + client/tenant; prevent attackers from making unlimited brute-force attempts.

Grant **least privilege**. Never share a single system-wide admin API key across all partners.

## 6. An API Key Is a Bearer Secret: Commonly Overlooked Risks

| Risk | Mechanism | Mitigation |
| --- | --- | --- |
| Leaked in logs | Access logs, reverse proxies, APM recording headers | Redact `X-API-Key`, never log Authorization/cookies |
| Leaked in URLs | Key placed in query string | Use headers only, avoid URLs/history |
| Leaked in Git/CI | Key hardcoded in source or env output | Secret manager, scanning, rotation |
| Replay if stolen | Bearer key reused from another client | TLS, TTL/revocation, network/mTLS binding when needed |
| Brute-force/credential stuffing | Guessing weak keys or predictable IDs | 256-bit CSPRNG, generic 401, rate limiting |
| Verifier digest leak | Exposed database backups | High-entropy secrets, strict DB access, HMAC pepper per threat model |
| Excessive scopes | Single key holds overly broad privileges | Least privilege, allowlisted scopes/tenants |
| Immortal keys | No expiration/rotation | Expiry, rotate/revoke, audit last use |
| Multiple instances | Unshared in-memory registry | Redis/R2DBC/central registry with consistency |
| Blocking lookup | Blocking JDBC on Netty event loop | Reactive driver/WebClient, timeouts |
| API key in public frontend | Browser JS bundle exposes secret | Never embed shared secrets in SPA/mobile binaries |
| Proxy drops header | Gateway strips `X-API-Key` | Verify hops, schema, and secret redaction |
| Browser preflight OPTIONS returns 401 | CORS runs after auth | Configure WebFlux CORS properly |
| Conflating API keys with user login | Skipping tenant/user authorization | Separate client identity and permissions |

If an API key lives inside browser JavaScript, users can read it via DevTools or the bundle. **Never use a shared server API key to protect individual browser user data**; consider OAuth2/OIDC with PKCE, Backend-for-Frontend, or proper session authentication.

## 7. Three-Layer WebFlux Design

### 7.1. Converter Handles Only HTTP Protocol Details

`ApiKeyHeaderConverter`:
- Reads only the `X-API-Key` header.
- Returns `Mono.empty()` when the **header is absent**, because the converter creates no authentication attempt.
- Returns `AuthenticationException` when the header is present but malformed or duplicated.
- Creates an **unauthenticated** `ApiKeyAuthenticationToken.request(rawKey)`.
- Does not query databases, check scopes, or set `authenticated=true`.

Isolating the converter lets you test parsing without booting a Spring context.

### 7.2. Manager Handles Only Credentials and Key Metadata

`ApiKeyReactiveAuthenticationManager`:
- Accepts only unauthenticated `ApiKeyAuthenticationToken` instances.
- Parses the key format with length and character bounds.
- Computes the digest of the secret part.
- Calls `ReactiveApiKeyRepository.findById(keyId)` returning `Mono<ApiKeyRecord>`.
- Compares digests in constant time and checks enabled/expiry.
- Returns principal `clientId` and authorities from the trusted record, with raw credentials = null.
- Wrong key/disabled/expired/unknown → generic `BadCredentialsException`.
- Unsupported Authentication types → `Mono.empty()`.
- Store errors → propagate; never silently allow the request.

### 7.3. Filter Manages Context and Failure Behavior

`AuthenticationWebFilter`:
- Runs only on `/api/**` (matcher) so public routes do not parse keys.
- Wires together the manager and converter.
- Uses `NoOpServerSecurityContextRepository` so authentication is not persisted across requests.
- Generic 401 on invalid keys; the authorization layer returns 403 when a valid key lacks permission.
- Placed at `SecurityWebFiltersOrder.AUTHENTICATION` **before the authorization filter**.
- Never manually invokes `subscribe()`, `block()`, or ThreadLocal authentication setters.

A common point of confusion: `ServerHttpSecurity.authenticationManager(manager)` configures a default manager, but **does not automatically create an API key header converter or filter**. To handle custom `X-API-Key`, the demo explicitly constructs an `AuthenticationWebFilter`.

## 8. Distinguishing 401/403 Outcomes and HTTP Scenarios

| Request | Authentication Stage | Authorization Stage | Expected HTTP |
| --- | --- | --- | --- |
| GET `/public`, no header | Filter matches `/api/**` only, skipped | `permitAll` | 200 |
| GET `/api/data`, no key | Converter `Mono.empty()` | Requires authenticated/scope | 401 |
| GET `/api/data`, wrong key | Manager errors `BadCredentialsException` | Stops | 401 |
| GET `/api/data`, expired/disabled key | Manager rejects generically | Stops | 401 |
| GET `/api/data`, valid key with `data:read` | Creates authenticated principal | `SCOPE_data:read` present | 200 |
| POST `/api/admin`, valid key with only `data:read` | Auth succeeds | Missing `SCOPE_admin:write` | 403 |
| GET `/api/data` after prior keyed GET, this one without header | No new auth, no session | Unauthenticated | 401 |
| GET `/api/unknown` | May succeed auth | `denyAll` | 403 if authenticated, 401 if anonymous |

**Never return HTTP 200 with a JSON `"error invalid key"` payload**: it misleads middleware, caches, and clients. Never disclose "this ID exists", "wrong digest", "key disabled", or internal scopes in 401 responses; the server can audit internal reasons using safe codes **without the key**.

## 9. Runnable Project: Spring Boot 3.3.5 + WebFlux + Java 17

This example includes:
- Key format `ak_<id>_<Base64URL(32 random bytes)>`.
- Small CLI to generate a demo API key (printed **once** for provisioning, not for production).
- In-memory repository holding only the SHA-256 digest, client ID, scopes, enabled flag, and expiry.
- Custom Authentication token (unauthenticated/verified).
- Converter for `X-API-Key` and reactive manager.
- Stateless `SecurityWebFilterChain` with illustrative GET and POST routes.
- Unit tests for the manager + HTTP tests via `WebTestClient`.

### 9.1. Directory Structure

```text
reactive-api-key-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/dev/example/apikey/
    │   │   ├── ApiKeyApplication.java
    │   │   ├── ApiKeyMaterial.java
    │   │   ├── ApiKeyAuthenticationToken.java
    │   │   ├── ApiKeyRecord.java
    │   │   ├── ReactiveApiKeyRepository.java
    │   │   ├── DemoApiKeyRepository.java
    │   │   ├── ApiKeyReactiveAuthenticationManager.java
    │   │   ├── ApiKeyHeaderConverter.java
    │   │   ├── SecurityConfig.java
    │   │   ├── DemoController.java
    │   │   └── DemoApiKeyGenerator.java
    │   └── resources/application.yml
    └── test/java/dev/example/apikey/
        ├── ApiKeyReactiveAuthenticationManagerTests.java
        └── ApiKeyHttpTests.java
```

### 9.2. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'reactive-api-key-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Do not add `spring-boot-starter-web` to a pure WebFlux demo.** When both MVC and WebFlux starters are present, Spring Boot defaults to the Servlet/MVC stack, breaking intended WebFlux security configuration.

### 9.3. Runtime Configuration

`src/main/resources/application.yml`:

```yaml
server:
  port: 8080

demo:
  api-key: ${DEMO_API_KEY}
```

The demo application **requires** the `DEMO_API_KEY` environment variable generated by `DemoApiKeyGenerator`. If the variable is missing or malformed, the application should **fail at startup** rather than falling back to an insecure hardcoded credential.

In production, replace the demo property with a secure provisioning/storage source: KMS/secret manager, key registry, encrypted-at-rest DB, and digests; do not load all raw keys from environment variables and hold them indefinitely in memory.

### 9.4. Entry Point

`src/main/java/dev/example/apikey/ApiKeyApplication.java`:

```java
package dev.example.apikey;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ApiKeyApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiKeyApplication.class, args);
    }
}
```

### 9.5. Key Parser and SHA-256 Digest

`src/main/java/dev/example/apikey/ApiKeyMaterial.java`:

```java
package dev.example.apikey;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;
import java.util.HexFormat;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.springframework.security.authentication.BadCredentialsException;

public final class ApiKeyMaterial {

    private static final Pattern FORMAT = Pattern.compile(
            "^ak_([A-Za-z0-9-]{1,32})_([A-Za-z0-9_-]{43})$");

    private ApiKeyMaterial() {
    }

    public record Parts(String keyId, byte[] secretBytes) {
        public Parts {
            secretBytes = secretBytes.clone();
        }

        @Override
        public byte[] secretBytes() {
            return secretBytes.clone();
        }
    }

    public static Parts parse(String rawKey) {
        if (rawKey == null || rawKey.length() > 128) {
            throw new BadCredentialsException("Invalid API key");
        }

        Matcher matcher = FORMAT.matcher(rawKey);
        if (!matcher.matches()) {
            throw new BadCredentialsException("Invalid API key");
        }

        String secretEncoded = matcher.group(2);
        final byte[] bytes;
        try {
            bytes = Base64.getUrlDecoder().decode(secretEncoded);
        } catch (IllegalArgumentException ex) {
            throw new BadCredentialsException("Invalid API key");
        }

        // 32 random bytes, canonical Base64URL without padding.
        if (bytes.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(bytes).equals(secretEncoded)) {
            throw new BadCredentialsException("Invalid API key");
        }

        return new Parts(matcher.group(1), bytes);
    }

    public static byte[] sha256(byte[] secretBytes) {
        try {
            return MessageDigest.getInstance("SHA-256")
                    .digest(secretBytes);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                    "SHA-256 is unavailable in this JVM", ex);
        }
    }

    public static String digestHex(byte[] secretBytes) {
        return HexFormat.of().formatHex(sha256(secretBytes));
    }
}
```

**Protective measures:**
- Regex constrains key ID, Base64URL secret, and length.
- Raw key parsing happens only after the converter; never log the raw string.
- Secret must decode to exact **32 bytes**, using canonical Base64URL to disallow alternate encodings of the same bytes.
- Java `record Parts` defensively clones arrays on construction and access to prevent external mutation.
- `SHA-256` digests **random secret bytes**, not human passwords. Java 17's `HexFormat` encodes bytes to hex for DB verifiers.
- `BadCredentialsException` on malformed keys is an authentication failure, not a 500 error.
- The digest omits the public `keyId` since the repository already looks up by ID; production can use HMAC/pepper if needed.

**Note:** The raw secret array and key string still exist temporarily on the heap; Java does not guarantee immediate erasure of all strings from memory. Minimize lifetime, avoid copying/logging, and protect heap dumps and secret management.

### 9.6. Creating a Custom Authentication Token

`src/main/java/dev/example/apikey/ApiKeyAuthenticationToken.java`:

```java
package dev.example.apikey;

import java.util.Collection;
import java.util.List;

import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;

public final class ApiKeyAuthenticationToken
        extends AbstractAuthenticationToken {

    private final String principal;
    private String credentials;

    private ApiKeyAuthenticationToken(
            String principal,
            String credentials,
            Collection<? extends GrantedAuthority> authorities,
            boolean authenticated) {

        super(authorities);
        this.principal = principal;
        this.credentials = credentials;
        super.setAuthenticated(authenticated);
    }

    public static ApiKeyAuthenticationToken request(String rawKey) {
        return new ApiKeyAuthenticationToken(
                "unverified-api-key", rawKey, List.of(), false);
    }

    public static ApiKeyAuthenticationToken verified(
            String clientId,
            Collection<? extends GrantedAuthority> authorities) {

        return new ApiKeyAuthenticationToken(
                clientId, null, authorities, true);
    }

    @Override
    public Object getPrincipal() {
        return principal;
    }

    @Override
    public Object getCredentials() {
        return credentials;
    }

    @Override
    public void eraseCredentials() {
        this.credentials = null;
        super.eraseCredentials();
    }

    @Override
    public void setAuthenticated(boolean authenticated) {
        if (authenticated) {
            throw new IllegalArgumentException(
                    "Use verified(...) factory after authentication");
        }
        super.setAuthenticated(false);
    }
}
```

**Explanation:**
- `request(rawKey)` creates a token with `authenticated=false` and principal merely set to an `"unverified"` label; **raw credentials are never treated as identity**.
- Only the manager calls `verified(clientId, authorities)` after checking the key record. The private constructor calls `super.setAuthenticated(...)`; external code cannot flip false to true via `setAuthenticated(true)`.
- The verified token **carries no raw API key** (`credentials=null`), reducing leak risk during authentication debugging.
- `getName()` inherited from `AbstractAuthenticationToken` returns the verified principal name.
- Never log `authentication` or serialize the security context. Never return the authentication object directly in JSON.

A custom token can also use an immutable `ApiClientPrincipal` record containing id/tenant as its principal, provided fields are minimal and hold no secrets. The demo uses a `String` `clientId` for clarity.

### 9.7. Key Record and Reactive Repository

`src/main/java/dev/example/apikey/ApiKeyRecord.java`:

```java
package dev.example.apikey;

import java.time.Instant;
import java.util.Set;

public record ApiKeyRecord(
        String keyId,
        String clientId,
        String secretSha256Hex,
        Set<String> scopes,
        boolean enabled,
        Instant expiresAt) {

    public ApiKeyRecord {
        scopes = Set.copyOf(scopes);
    }
}
```

`src/main/java/dev/example/apikey/ReactiveApiKeyRepository.java`:

```java
package dev.example.apikey;

import reactor.core.publisher.Mono;

public interface ReactiveApiKeyRepository {
    Mono<ApiKeyRecord> findByKeyId(String keyId);
}
```

The repository is a **custom-defined abstraction**, not a built-in Spring interface. It decouples the manager from persistence infrastructure; swap `DemoApiKeyRepository` for a reactive Redis/R2DBC adapter without changing the security filter.

### 9.8. Demo Repository Storing Only the Digest

`src/main/java/dev/example/apikey/DemoApiKeyRepository.java`:

```java
package dev.example.apikey;

import java.time.Instant;
import java.util.Map;
import java.util.Set;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Repository;

import reactor.core.publisher.Mono;

@Repository
public final class DemoApiKeyRepository
        implements ReactiveApiKeyRepository {

    private final Map<String, ApiKeyRecord> records;

    public DemoApiKeyRepository(
            @Value("${demo.api-key}") String demoKey) {

        ApiKeyMaterial.Parts parts =
                ApiKeyMaterial.parse(demoKey);

        ApiKeyRecord record = new ApiKeyRecord(
                parts.keyId(),
                "demo-client",
                ApiKeyMaterial.digestHex(parts.secretBytes()),
                Set.of("data:read"),
                true,
                Instant.MAX);

        records = Map.of(record.keyId(), record);
    }

    @Override
    public Mono<ApiKeyRecord> findByKeyId(String keyId) {
        return Mono.justOrEmpty(records.get(keyId));
    }
}
```

The repository:
- Reads the raw key **once at app startup** solely for the demo and stores its digest. Never writes the raw key to a database or log.
- Fixed `Map.of` containing a single key and `data:read` scope.
- `Mono.justOrEmpty(...)` adheres to the reactive repository contract.
- `Instant.MAX` means the demo key does not expire; **production requires real expiration and revocation**.
- Has no create/delete/rotate APIs because this is an authentication lesson, not a full secret provisioning system.
- Never use this store in multi-instance production: each restart or provisioning event could change keys and desynchronize state.

**Production option:** Store digests generated during provisioning in the DB and **do not** load raw keys from environment variables. Allow admins to create keys with expiration, display once, store the hash, rotate with a controlled grace window, and revoke when needed.

### 9.9. ReactiveAuthenticationManager

`src/main/java/dev/example/apikey/ApiKeyReactiveAuthenticationManager.java`:

```java
package dev.example.apikey;

import java.security.MessageDigest;
import java.time.Instant;
import java.util.HexFormat;
import java.util.List;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public final class ApiKeyReactiveAuthenticationManager
        implements ReactiveAuthenticationManager {

    private final ReactiveApiKeyRepository repository;

    public ApiKeyReactiveAuthenticationManager(
            ReactiveApiKeyRepository repository) {
        this.repository = repository;
    }

    @Override
    public Mono<Authentication> authenticate(
            Authentication authentication) {

        if (!(authentication instanceof ApiKeyAuthenticationToken token)
                || token.isAuthenticated()) {
            // Different Authentication type -> this manager does not handle it.
            return Mono.empty();
        }

        return Mono.defer(() -> {
            String rawKey = (String) token.getCredentials();
            ApiKeyMaterial.Parts presented =
                    ApiKeyMaterial.parse(rawKey);
            byte[] candidateDigest =
                    ApiKeyMaterial.sha256(presented.secretBytes());

            return repository.findByKeyId(presented.keyId())
                    .switchIfEmpty(Mono.error(
                            new BadCredentialsException(
                                    "Invalid API key")))
                    .flatMap(record -> {
                        byte[] expectedDigest = HexFormat.of()
                                .parseHex(record.secretSha256Hex());

                        boolean matches = MessageDigest.isEqual(
                                expectedDigest, candidateDigest);
                        boolean active = record.enabled()
                                && Instant.now().isBefore(
                                        record.expiresAt());

                        if (!matches || !active) {
                            return Mono.<Authentication>error(
                                    new BadCredentialsException(
                                            "Invalid API key"));
                        }

                        List<SimpleGrantedAuthority> authorities =
                                record.scopes().stream()
                                        .map(scope ->
                                                new SimpleGrantedAuthority(
                                                        "SCOPE_" + scope))
                                        .toList();

                        return Mono.<Authentication>just(
                                ApiKeyAuthenticationToken.verified(
                                        record.clientId(),
                                        authorities));
                    });
        });
    }
}
```

**Step-by-step analysis:**

1. Verify the token has the **right type and is unauthenticated**. If it is not an API key token, return `Mono.empty()` because this manager does not take responsibility.
2. `Mono.defer(...)` defers parsing and hashing until subscription; never call `subscribe()` or `block()`.
3. `ApiKeyMaterial.parse(...)` enforces bounded formatting. Parse errors produce `BadCredentialsException` inside the reactive subscription.
4. `sha256(...)` computes digest bytes of the secret; never compare raw keys directly against DB data.
5. Repository looks up the record by `keyId`. If missing, the manager returns an **authentication error**, not empty.
6. `MessageDigest.isEqual` compares the verifier digest with the candidate digest without naive short-circuiting; both SHA-256 digests have equal length.
7. Checks `enabled` and `expiresAt` at request evaluation time. In production, a stale cache entry could still grant old permissions; design cache/revocation SLAs accordingly.
8. Scopes come strictly from the **server-side record** and map to `SCOPE_data:read`. No scopes are accepted from client headers.
9. Success returns `ApiKeyAuthenticationToken.verified(...)` with principal `demo-client`, **null** credentials, and authenticated true.
10. Wrong secret, disabled, or expired keys all return the **same message**: `Invalid API key`. The HTTP failure handler does not leak the detailed cause.
11. If the repository itself errors, the Mono error propagates; never convert it into `Mono.just(verified)`. Production distinguishes infrastructure errors from bad credentials in secure monitoring.
12. SHA-256 over 32 bytes is tiny CPU work; repository I/O must use a reactive driver. Switching to synchronous JDBC directly inside `flatMap` can stall the Netty event loop.
13. `record.scopes()` and expiry are read from trusted metadata rather than constructing permissions from a request-provided `clientId` string.
14. The demo only checks account-level active status; business authorization per resource/tenant must still be enforced separately.

**Unmasked issue:** If the key ID does not exist, the code errors before hash comparison; response times may differ. For sensitive environments, consider performing dummy digest work and normalizing timing/responses within reasonable bounds, while still applying rate limits and abuse monitoring. Never use arbitrary random sleeps as a substitute for real controls.

### 9.10. ServerAuthenticationConverter for X-API-Key

`src/main/java/dev/example/apikey/ApiKeyHeaderConverter.java`:

```java
package dev.example.apikey;

import java.util.List;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

public final class ApiKeyHeaderConverter
        implements ServerAuthenticationConverter {

    private static final String HEADER = "X-API-Key";

    @Override
    public Mono<Authentication> convert(ServerWebExchange exchange) {
        List<String> values =
                exchange.getRequest().getHeaders().get(HEADER);

        // No credential -> filter does not attempt authentication.
        // Routes requiring a key will receive 401 at the authorization layer.
        if (values == null || values.isEmpty()) {
            return Mono.empty();
        }

        if (values.size() != 1) {
            return Mono.error(new BadCredentialsException(
                    "Invalid API key"));
        }

        String rawKey = values.get(0);

        // Exact key structure is validated in the manager.
        // Reject empty/oversized/comma-joined headers early.
        if (rawKey == null || rawKey.isBlank()
                || rawKey.length() > 128
                || rawKey.indexOf(',') >= 0) {
            return Mono.error(new BadCredentialsException(
                    "Invalid API key"));
        }

        return Mono.just(
                ApiKeyAuthenticationToken.request(rawKey));
    }
}
```

**Cases to note:**
- `X-API-Key` absent: converter returns empty. The secured route still requires a principal, so 401 is returned.
- Header present but malformed: returns a generic 401 error.
- Duplicate header or proxy comma-joined header: reject, never arbitrarily take "the first value".
- Never read secrets from URL queries or cookies to avoid leak channels.
- Converter checks only headers/paths and **assigns no authorities**.
- Key ID and secret are validated more strictly inside `ApiKeyMaterial.parse`.

Some reverse proxies canonicalize HTTP header names; `X-API-Key` is case-insensitive per HTTP. Test end-to-end through your real gateway and ensure the gateway does not log the header value.

### 9.11. Configuring AuthenticationWebFilter and SecurityWebFilterChain

`src/main/java/dev/example/apikey/SecurityConfig.java`:

```java
package dev.example.apikey;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.HttpStatusServerEntryPoint;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ApiKeyReactiveAuthenticationManager manager) {

        var noSession =
                NoOpServerSecurityContextRepository.getInstance();
        var unauthorized =
                new HttpStatusServerEntryPoint(
                        HttpStatus.UNAUTHORIZED);

        AuthenticationWebFilter apiKeyFilter =
                new AuthenticationWebFilter(manager);

        apiKeyFilter.setRequiresAuthenticationMatcher(
                ServerWebExchangeMatchers.pathMatchers("/api/**"));

        apiKeyFilter.setServerAuthenticationConverter(
                new ApiKeyHeaderConverter());

        apiKeyFilter.setSecurityContextRepository(noSession);

        apiKeyFilter.setAuthenticationFailureHandler(
                new ServerAuthenticationEntryPointFailureHandler(
                        unauthorized));

        return http
                .securityContextRepository(noSession)
                .csrf(csrf -> csrf.disable())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .logout(logout -> logout.disable())
                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint(unauthorized)
                        .accessDeniedHandler((exchange, error) -> {
                            exchange.getResponse()
                                    .setStatusCode(HttpStatus.FORBIDDEN);
                            return exchange.getResponse().setComplete();
                        }))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/data")
                            .hasAuthority("SCOPE_data:read")
                        .pathMatchers(HttpMethod.POST, "/api/admin")
                            .hasAuthority("SCOPE_admin:write")
                        .anyExchange().denyAll())
                .addFilterAt(
                        apiKeyFilter,
                        SecurityWebFiltersOrder.AUTHENTICATION)
                .build();
    }
}
```

**Why does this configuration matter?**

1. `AuthenticationWebFilter` integrates cleanly into the framework authentication pipeline. Never write a custom WebFilter that "sets authenticated=true" before verification.
2. `setRequiresAuthenticationMatcher(...)` enables the converter only for `/api/**`; `/public` requires no key.
3. `setServerAuthenticationConverter(...)` uses the **WebFlux** API (different from Servlet `AuthenticationConverter`).
4. `NoOpServerSecurityContextRepository` is configured on both the filter and `ServerHttpSecurity`: authentication is never persisted across requests. **Every new request must present a key**.
5. `ServerAuthenticationEntryPointFailureHandler` turns API key filter failures into a generic 401 without browser redirects to a login form.
6. `exceptionHandling.authenticationEntryPoint(unauthorized)` ensures protected routes missing credentials return 401. `accessDeniedHandler` ensures valid credentials lacking authority return 403.
7. `authorizeExchange` separates `GET /api/data` (requiring `SCOPE_data:read`) and `POST /api/admin` (requiring `SCOPE_admin:write`). The demo key only has read scope, so POST admin must return 403.
8. `anyExchange().denyAll()` fails closed for undeclared paths or methods.
9. `addFilterAt(..., SecurityWebFiltersOrder.AUTHENTICATION)` places the custom filter in the proper phase, before authorization. Never place an auth filter after controllers or authorization.
10. `httpBasic/formLogin/logout.disable()` suits a demo header-only API with no other auth/logout mechanism. If combined with OAuth2 Resource Server or browser login, configure matchers, manager resolvers, or multiple chains explicitly.
11. `csrf.disable()` **applies strictly to completely stateless APIs using API keys explicitly placed in custom headers by clients, with no browser session/cookie credentials**. Never copy it into a browser app with cookies/sessions without assessing CSRF.
12. `NoOpServerSecurityContextRepository` does not mean the server holds zero state: the key registry/digests, rotation/revocation, and rate limits **are still server-side state**.

### 9.12. Controller Demonstrating 200 and 403

`src/main/java/dev/example/apikey/DemoController.java`:

```java
package dev.example.apikey;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Mono<String> publicRoute() {
        return Mono.just("public-ok");
    }

    @GetMapping("/api/data")
    public Mono<Map<String, String>> readData(Principal principal) {
        return Mono.just(Map.of(
                "client", principal.getName(),
                "message", "data-read-ok"));
    }

    @PostMapping("/api/admin")
    public Mono<String> adminOperation() {
        return Mono.just("admin-ok");
    }
}
```

- `Principal` in `readData` is populated by Spring WebFlux from the security context. Its value is `demo-client` from the verified Authentication, **not** the key secret.
- `adminOperation` exists to simulate an action requiring `SCOPE_admin:write`; since the demo key lacks this scope, requests never reach the controller.
- In real applications, you may also need tenant/resource ownership checks beyond authorities. Never use client ID alone to access resources across every tenant.

### 9.13. CLI to Generate a Demo API Key with SecureRandom

`src/main/java/dev/example/apikey/DemoApiKeyGenerator.java`:

```java
package dev.example.apikey;

import java.security.SecureRandom;
import java.util.Base64;

public final class DemoApiKeyGenerator {

    private DemoApiKeyGenerator() {
    }

    public static void main(String[] args) {
        byte[] secret = new byte[32];
        new SecureRandom().nextBytes(secret);

        String encoded = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(secret);

        // Print once only for generating a test credential.
        // DO NOT print live credentials in production applications.
        System.out.println("ak_demo_" + encoded);
    }
}
```

Build and generate a key once:

```bash
gradle classes
java -cp build/classes/java/main dev.example.apikey.DemoApiKeyGenerator
```

The output looks like (intentionally **omitting any real secret value** in this document):

```text
ak_demo_<43_RANDOM_BASE64URL_CHARS>
```

Copy the generated key into your **local environment/secret store**; never commit it to the repo, send it to others, or paste it into chat. Once printed in a terminal, be mindful of terminal logs/scrollback and avoid capturing debug recordings. In production, provisioning must run in a dedicated system that returns the raw key **once** to the recipient.

## 10. Running the Demo with curl

Requires **Java 17+**, compatible Gradle 8.x, and a configured `DEMO_API_KEY` environment variable. After generating a key and setting it in your environment:

```bash
gradle bootRun
```

If the project includes a Gradle Wrapper, use `./gradlew bootRun` (Linux/macOS) or `gradlew.bat bootRun` (Windows).

The commands below reference an **already-set** `DEMO_API_KEY` shell variable, avoiding placing raw credentials in the documentation. For production keys, avoid passing secrets directly in shell flags where they can leak via process lists, debug traces, and terminal history. A safer approach in secure environments is an HTTP client reading the secret from a secret manager without logging request headers.

### 10.1. Public Route

```bash
curl -i http://localhost:8080/public
```

Expected `200 OK` and body:

```text
public-ok
```

### 10.2. Missing API Key

```bash
curl -i http://localhost:8080/api/data
```

Expected `401 Unauthorized`, with no redirect to an HTML login page.

### 10.3. Valid Key

```bash
curl -i -H "X-API-Key: $DEMO_API_KEY" \
  http://localhost:8080/api/data
```

Expected `200 OK` and JSON containing:

```json
{
  "client": "demo-client",
  "message": "data-read-ok"
}
```

Actual JSON field order may vary; `Map` does not guarantee ordering.

### 10.4. Wrong Key

```bash
curl -i -H 'X-API-Key: definitely-invalid' \
  http://localhost:8080/api/data
```

Expected `401 Unauthorized`, without revealing whether the key ID exists.

### 10.5. Valid Key Lacking Scope

```bash
curl -i -X POST \
  -H "X-API-Key: $DEMO_API_KEY" \
  http://localhost:8080/api/admin
```

Expected `403 Forbidden`. The manager successfully authenticated `demo-client`, but `authorizeExchange` requires `SCOPE_admin:write` while the record only grants `SCOPE_data:read`.

### 10.6. Subsequent Request Does Not Inherit Identity

```bash
curl -i -H "X-API-Key: $DEMO_API_KEY" \
  http://localhost:8080/api/data
curl -i http://localhost:8080/api/data
```

Expect the first request to return `200` and the second `401`. No "login session" is created by API key authentication. If you observe `200` on the second request without a header, check the security context repository, whether a gateway is injecting headers, or if another authentication mechanism is active.

**These HTTP outcomes are expected from the source code, not results executed inside your workspace.** In production, always use HTTPS: plain HTTP localhost here is strictly for teaching the flow.

## 11. Unit Tests: ReactiveAuthenticationManager

To test **the manager itself**, you do not need to start Spring Boot or the WebFlux HTTP server. Use `StepVerifier` and a `DemoApiKeyRepository` instantiated directly with a test key. **An all-zero-byte secret is strictly a test fixture** to satisfy formatting, and must never be issued as a real key.

File `src/test/java/dev/example/apikey/ApiKeyReactiveAuthenticationManagerTests.java`:

```java
package dev.example.apikey;

import java.time.Instant;
import java.util.Base64;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ApiKeyReactiveAuthenticationManagerTests {

    private static final byte[] TEST_BYTES = new byte[32];

    private static final String SECRET =
            Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(TEST_BYTES);

    private static final String KEY = "ak_demo_" + SECRET;

    private ApiKeyReactiveAuthenticationManager manager() {
        return new ApiKeyReactiveAuthenticationManager(
                new DemoApiKeyRepository(KEY));
    }

    @Test
    void validKeyProducesAuthenticatedPrincipalAndAuthorities() {
        StepVerifier.create(
                manager().authenticate(
                        ApiKeyAuthenticationToken.request(KEY)))
                .assertNext(auth -> {
                    assertTrue(auth.isAuthenticated());
                    assertEquals("demo-client", auth.getName());
                    assertNull(auth.getCredentials());
                    assertTrue(auth.getAuthorities().stream()
                            .anyMatch(authority ->
                                    authority.getAuthority().equals(
                                            "SCOPE_data:read")));
                })
                .verifyComplete();
    }

    @Test
    void wrongSecretForExistingKeyIdFails() {
        byte[] other = new byte[32];
        other[0] = 1;
        String wrong = "ak_demo_"
                + Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(other);

        StepVerifier.create(
                manager().authenticate(
                        ApiKeyAuthenticationToken.request(wrong)))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void unknownKeyIdFailsWithAuthenticationException() {
        String unknown = "ak_unknown_" + SECRET;

        StepVerifier.create(
                manager().authenticate(
                        ApiKeyAuthenticationToken.request(unknown)))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void malformedKeyIsRejected() {
        StepVerifier.create(
                manager().authenticate(
                        ApiKeyAuthenticationToken.request("bad-key")))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void unsupportedAuthenticationTypeReturnsEmptyMono() {
        Authentication differentType =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "user", "password");

        StepVerifier.create(manager().authenticate(differentType))
                .verifyComplete();
    }

    @Test
    void disabledKeyIsRejected() {
        String digest = ApiKeyMaterial.digestHex(TEST_BYTES);
        ReactiveApiKeyRepository disabledRepository =
                keyId -> Mono.just(new ApiKeyRecord(
                        keyId,
                        "disabled-client",
                        digest,
                        Set.of("data:read"),
                        false,
                        Instant.MAX));

        var target = new ApiKeyReactiveAuthenticationManager(
                disabledRepository);

        StepVerifier.create(target.authenticate(
                ApiKeyAuthenticationToken.request(KEY)))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void expiredKeyIsRejected() {
        String digest = ApiKeyMaterial.digestHex(TEST_BYTES);
        ReactiveApiKeyRepository expiredRepository =
                keyId -> Mono.just(new ApiKeyRecord(
                        keyId,
                        "expired-client",
                        digest,
                        Set.of("data:read"),
                        true,
                        Instant.EPOCH));

        var target = new ApiKeyReactiveAuthenticationManager(
                expiredRepository);

        StepVerifier.create(target.authenticate(
                ApiKeyAuthenticationToken.request(KEY)))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void repositoryErrorIsNotSilentlyAccepted() {
        ReactiveApiKeyRepository failedRepository =
                ignored -> Mono.error(
                        new IllegalStateException("store unavailable"));

        var target = new ApiKeyReactiveAuthenticationManager(
                failedRepository);

        StepVerifier.create(target.authenticate(
                ApiKeyAuthenticationToken.request(KEY)))
                .expectError(IllegalStateException.class)
                .verify();
    }
}
```

**Expected:** 8 unit tests pass based on the code. The tests confirm:
1. A valid key creates a verified principal/authority without retaining raw credentials.
2. Matching key ID with wrong secret causes an authentication error.
3. An unissued key ID causes an error (not `Mono.empty()`).
4. Malformed format is rejected.
5. The manager returns `Mono.empty()` for authentication types it does not handle.
6. Disabled/expired records are rejected.
7. A store outage is **never** turned into an authenticated principal.

**Important point:** These test the manager's contract; they do not prove HTTPS, proxy redaction, CORS, multi-node revocation, production key entropy, or tenant isolation. Those require dedicated tests.

## 12. HTTP Integration Tests with WebTestClient

Use `@SpringBootTest(RANDOM_PORT)` to run the full **AuthenticationWebFilter + real manager + demo repository + authorization rules**, without mocking JWTs/tokens and without bypassing the security chain.

File `src/test/java/dev/example/apikey/ApiKeyHttpTests.java`:

```java
package dev.example.apikey;

import java.util.Base64;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ApiKeyHttpTests {

    // TEST FIXTURE ONLY: zero bytes have no entropy,
    // never use as a production API key.
    private static final String SECRET =
            Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(new byte[32]);

    private static final String VALID_KEY =
            "ak_demo_" + SECRET;

    @DynamicPropertySource
    static void demoProperties(DynamicPropertyRegistry registry) {
        registry.add("demo.api-key", () -> VALID_KEY);
    }

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointWorksWithoutApiKey() {
        client.get().uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public-ok");
    }

    @Test
    void protectedEndpointWithoutKeyIs401() {
        client.get().uri("/api/data")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void validKeyGetsDataAndVerifiedClientIdentity() {
        client.get().uri("/api/data")
                .header("X-API-Key", VALID_KEY)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.client").isEqualTo("demo-client")
                .jsonPath("$.message").isEqualTo("data-read-ok");
    }

    @Test
    void malformedKeyIs401() {
        client.get().uri("/api/data")
                .header("X-API-Key", "invalid")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void keyWithUnknownIdIs401() {
        client.get().uri("/api/data")
                .header("X-API-Key", "ak_unknown_" + SECRET)
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void wrongSecretWithKnownIdIs401() {
        byte[] other = new byte[32];
        other[0] = 1;

        String wrong = "ak_demo_"
                + Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(other);

        client.get().uri("/api/data")
                .header("X-API-Key", wrong)
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void duplicatedApiKeyHeadersAreRejected() {
        client.get().uri("/api/data")
                .headers(headers -> {
                    headers.add("X-API-Key", VALID_KEY);
                    headers.add("X-API-Key", VALID_KEY);
                })
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void validKeyWithoutAdminScopeIs403() {
        client.post().uri("/api/admin")
                .header("X-API-Key", VALID_KEY)
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void successfulRequestDoesNotCreateAuthenticationSession() {
        client.get().uri("/api/data")
                .header("X-API-Key", VALID_KEY)
                .exchange()
                .expectStatus().isOk();

        client.get().uri("/api/data")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void unknownRouteDoesNotBecomePublic() {
        client.get().uri("/api/unknown")
                .header("X-API-Key", VALID_KEY)
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

**Expected results:** 10 HTTP tests pass. Each test targets a specific behavior:
- Public route requires no key.
- Protected endpoint missing a key → 401.
- Valid key → 200, correct principal from the record.
- Malformed/unknown/wrong secret → 401.
- Duplicate headers → 401, never taking the first value.
- Authenticated but missing admin scope → 403.
- No WebSession authentication persisted from the prior request.
- Unknown routes fail closed.

**Note on undeclared route status:** The demo uses `anyExchange().denyAll()`. For an authenticated principal, accessing `/api/unknown` returns 403 from the security policy before Spring MVC/WebFlux routing can return 404. This is the intended policy behavior, not a missing controller mapping bug.

### Running All Tests

```bash
gradle test
```

**Expected:** 18 tests (8 manager tests + 10 WebTestClient tests) with the files and dependencies above. This is an **expectation from the example**, not a claim that Gradle was run on your machine; check the actual test report in your workspace before shipping to production.

### What Does Each Test Prove?

| Test Scope | Proves | Does Not Prove |
| --- | --- | --- |
| `StepVerifier` on manager | Mono contract, hash/expiry/enabled, and authorities | WebFilter ordering, HTTP responses |
| `WebTestClient` | Converter → manager → security chain → HTTP authorization | Multi-instance production, TLS/proxy |
| Duplicate/unknown key | Key parser and error status | Absence of timing side-channels |
| No-session test | Second request is not automatically authenticated | Gateways/proxies never inject keys |
| Admin 403 | AuthN succeeded without admin scope | Business ownership/tenant isolation |
| Production security audit | Requires dedicated E2E tests | Cannot be inferred from unit tests |

**Never use `mockUser()` or a fake security context across your entire HTTP suite and claim API key authentication is tested.** A mocked principal bypasses the converter/manager, leading to false confidence. The suite above sends real headers to the embedded WebFlux server and uses the demo repository configured via `@DynamicPropertySource`.

## 13. Why 401/403 Statuses Need Explicit Configuration

### 401 Unauthorized

Three cases:
- `X-API-Key` is not sent, yet the route requires a key.
- Key is malformed, nonexistent, or has a wrong digest.
- Key is disabled or expired.

The goal is the same client-visible **401** status (without leaking record details). Never redirect browsers to a login page, as this is a machine-to-machine API.

### 403 Forbidden

The credential was verified and the client has a principal, but the route requires an authority absent from the key record. For instance, `SCOPE_admin:write` is not in `demo-client`'s scopes.

**Caution:** If you pass an invalid key and observe 403, either the filter did not run properly or exception handling is treating anonymous as access denied. Check matchers, filter order, entry point, other authentication schemes, and tests.

### 5xx on Store Failure

A database/Redis timeout should not be misreported as "wrong key" without evidence; production responses may be a generic 503/500, but the API must never expose database names, raw keys, stack traces, or internal hosts. Trigger internal alerts and metrics, and never automatically **fail open** for sensitive endpoints.

### Never Confuse Empty Monos

- Converter `Mono.empty()` when the header is absent → no authentication attempt.
- Manager `Mono.empty()` when the **Authentication type is unsupported** → manager abstains; in a multi-manager chain, another delegate may handle it.
- Manager `Mono.error(BadCredentialsException)` when the **API key is wrong** → failure that must stop the flow.
- Manager `Mono.just(verified)` when the **API key is valid** → success, carrying principal/authorities.

This is one of the core concepts of this lesson.

## 14. Upgrading the Demo to a Production System

### 14.1. Key Provisioning Is Not an Open API

When creating a new key:
1. Authenticate and authorize the admin/operator before issuing a key.
2. Generate **32 random bytes** using a CSPRNG and create a unique key ID.
3. Choose client/tenant, least-privilege scopes, expiration, and rate limit/quota.
4. Compute the digest/HMAC and store only the verifier, never the raw key.
5. Display the raw API key **once** to the key owner over a secure channel.
6. Audit the issuer, timestamp, policy, and key ID — never log the raw key.
7. Prefer storing keys in a secret manager and avoid passing keys in CLI flags/CI logs.

**Never use the demo generator/env seed to run all partners**, since the demo lacks CRUD lifecycle, provisioning authorization, auditing, and multi-key storage.

### 14.2. Production Schema and Reactive Repository

A logical table:

```sql
CREATE TABLE api_keys (
    key_id             VARCHAR(32) PRIMARY KEY,
    client_id          VARCHAR(120) NOT NULL,
    secret_sha256_hex  CHAR(64) NOT NULL,
    enabled            BOOLEAN NOT NULL,
    expires_at         TIMESTAMP WITH TIME ZONE NOT NULL,
    tenant_id          VARCHAR(120) NOT NULL,
    created_at         TIMESTAMP WITH TIME ZONE NOT NULL
);
```

Scopes can be stored in an auxiliary `api_key_scopes` table or normalized appropriately for your DB. The SQL above is an **illustrative schema**, not a complete migration for every DB (indexes, precision, constraints, auditing, and encryption remain system-specific).

Implement `ReactiveApiKeyRepository.findByKeyId` using:
- R2DBC reactive repositories/clients, never synchronous JDBC on the event loop;
- Reactive Redis if it serves as a trusted store/lookup cache;
- WebClient calling an Authentication/Key Registry service with TLS, timeouts, and a service-availability policy.

**Do not do this in WebFlux:**

```java
// ANTI-PATTERN: blocking I/O directly inside the reactive pipeline.
return Mono.just(jdbcApiKeyRepository.findByKeyId(keyId));
```

`Mono.just(...)` evaluates its argument **eagerly**, so the JDBC call blocks when the method is invoked. If no reactive driver exists yet, a wrapper can use:

```java
// FRAGMENT for unavoidable blocking integration; resource bounds required.
return Mono.fromCallable(
        () -> jdbcApiKeyRepository.findByKeyId(keyId))
        .subscribeOn(Schedulers.boundedElastic());
```

This is a **fragment** requiring imports and proper null/`Optional` handling. It does not replace reactive I/O; set timeouts, concurrency limits, pool metrics, and a migration plan for high throughput. Never call `.block()` inside `ReactiveAuthenticationManager`.

### 14.3. Rotation and Revocation

A key must have:
- A unique `key_id`.
- `enabled`/revoked timestamp.
- Expiration and a renewal plan.
- Audit history and last-used metadata.
- Owner, tenant, scopes, and IP/network policy (if applicable).
- A rotation workflow.

A rotation cycle:
1. Create a **new key** (new ID/secret) with scopes no broader than needed.
2. Deliver the new key to the client over a secure channel.
3. Allow a **bounded transition window** if needed.
4. Monitor whether the old key is still in use.
5. Revoke the old key and confirm all Resource Servers reject it.
6. Purge the old secret from CI secrets, configs, and support docs; audit incidents.

**One key ID should not map to two secrets simultaneously in the demo repository**, because each record holds only one verifier. Production can support multiple active key IDs during an overlap window.

### 14.4. Caching and Immediate Revocation Requirements

If Resource Servers cache `ApiKeyRecord` for 10 minutes, an admin revokes a key at 10:01, yet nodes keep using the stale `enabled=true` record until 10:11. A "reactive" key registry **does not automatically guarantee instant revocation**.

Define clearly:
- When revocation is committed.
- Maximum propagation delay across regions/nodes.
- Cache entry TTL and event-based invalidation.
- Whether requests authenticated prior to revocation may finish.
- Whether Redis/DB outages fail closed or degrade with strict bounds.
- Audit/metric tracking of elapsed time from revocation commit until new requests are rejected.

For high-risk transactions, re-read current policy near transaction commit. Do not rely solely on entrypoint authentication if permissions can change mid-flight on long-lived operations.

### 14.5. Timing and Enumeration

Even with constant-time digest comparison, looking up an existing ID may take slightly longer or shorter than a nonexistent ID. Additional measures:
- Return a generic 401 and uniform response body.
- Perform a dummy digest comparison when the record is missing if needed to reduce timing differences.
- Rate-limit by IP/client/key prefix and detect patterns.
- Avoid exposing unauthenticated key-ID lookup endpoints that return metadata/roles.
- Never log raw keys or full HTTP headers.
- Avoid unbounded random sleeps, which invite DoS without solving the root cause.

A 256-bit random secret makes online guessing practically infeasible when implemented properly; rate limiting is still required against abuse, DoS, and leak detection.

### 14.6. Replay and Channel Binding

Because an API key is a bearer secret, a copied key can still be replayed. HTTPS prevents eavesdropping in transit but cannot rescue credentials leaked in logs or client machines. For sensitive integrations:
- Consider mTLS or private network restrictions.
- Use HMAC request signatures with timestamp/nonce and strict canonicalization if your threat model demands proof-of-possession; enforce replay windows and clock drift checks.
- Consider OAuth2 client credentials/mTLS-bound tokens instead of static keys.
- Never ship keys to public browser frontends.
- Support issuing multiple keys per service for zero-downtime rotation.

**Do not invent ad-hoc "request signing"** without formal specifications for canonicalization, MAC algorithms, anti-replay, and key rotation.

## 15. Combining API Keys with CORS/Browsers or OAuth2

### 15.1. Browser Custom Header Calls Trigger Preflight

Cross-origin JavaScript calling:

```javascript
// HTTP illustration ONLY; DO NOT embed shared secrets in a public frontend.
fetch("https://api.example.test/api/data", {
  headers: { "X-API-Key": "DO_NOT_PUT_SHARED_SECRET_IN_BROWSER" }
});
```

`X-API-Key` is not a CORS-safelisted header, so the browser sends an **OPTIONS preflight** before the real request. The preflight carries no raw API key, only `Access-Control-Request-Headers: x-api-key`.

With Spring Security WebFlux, configure CORS **before authentication**, allowlist valid origins/methods/headers, and do not require preflight requests to carry a key. The Section 9 demo targets `curl`/machine clients and **does not configure CORS for browsers**. If you need browser clients, design separately for user authentication, secret exposure, CORS, and CSRF.

### 15.2. Why Does the Demo Conditionally Disable CSRF?

CSRF typically applies when browsers **automatically attach credentials** (cookies/sessions/HTTP Basic in relevant contexts). An API key is **explicitly placed in a header** by a machine client rather than automatically sent by browsers like cookies. Therefore, a dedicated stateless API-key app can disable CSRF if **no** browser-managed credentials coexist.

If the same app also has cookie/session login:
- Keep CSRF protection enabled for state-changing routes using automatic credentials.
- Split security chains clearly by path/API scheme.
- Never disable CSRF app-wide just to make an API-key POST work.

### 15.3. Combining Bearer JWT and API Keys

If an app supports both Bearer JWT and `X-API-Key`:
- Never let two filters attempt conflicting authentication on the same request.
- Use explicit `securityMatcher`/multiple `SecurityWebFilterChain` beans or a `ReactiveAuthenticationManagerResolver`.
- Define credential precedence when a request carries **both headers**. Rejecting ambiguity is usually safer than picking one arbitrarily.
- Distinguish authorities and principal types; validate tenant scopes.
- Prevent bypasses where one converter returns empty and another mechanism accidentally grants access.
- Write tests for both headers present, missing/wrong single headers, duplicates, and mixed-auth requests.

### 15.4. When a Gateway Authenticates the API Key

If a gateway validates the API key and forwards identity in internal headers:
- Trust the gateway only over mTLS/network policy and strip all client-supplied identity headers.
- If the backend does not verify header origin, attackers can spoof `X-Authenticated-Client`.
- Consider defense-in-depth at the Resource Server for sensitive endpoints.
- Assign responsibilities for rate limiting, revocation, and auditing clearly between gateway and application.

## 16. Common Errors and Diagnostics

| Symptom | Likely Cause | Fix |
| --- | --- | --- |
| Valid key always returns 401 | Converter mismatch/wrong header or registry digest mismatch | Test header→converter→manager and matchers |
| Wrong key returns 200 | Auth set true before validation, wrong `permitAll` | Only manager issues verified principal; deny by default |
| Wrong key returns 403 instead of 401 | Wrong entry point or anonymous/auth flow | Configure failure handler & `exceptionHandling` |
| Valid key returns 403 on data | Wrong scope mapping (`SCOPE_` prefix) | Check scopes from record and `hasAuthority` |
| Key missing inside request | Gateway stripped `X-API-Key` | Check trusted proxy, never log the value |
| Duplicate headers accepted | Converter used `getFirst` | Reject duplicates/comma-joined values |
| App startup fails | Missing `DEMO_API_KEY` or invalid format | Generate 32-byte key and inject env var |
| Key revocation only works on node A | In-memory store or local cache | Shared store/consistency/TTL |
| Key leaked in logs | HTTP header logging/APM | Redact, rotate exposed key |
| Request loop slows down | Blocking JDBC in manager | Reactive I/O, no `block()` |
| Invalid key treated as missing | Manager returned `Mono.empty()` for wrong key | `Mono.error(BadCredentialsException)` |
| Authenticated key still holds raw credentials | Verified token kept raw secret | Clear/null credentials after verification |
| Browser OPTIONS returns 401 | CORS not handled before authentication | Proper `CorsConfigurationSource`/`CorsWebFilter` order |
| CSRF 403 in browser app | Browser session + POST missing token | Keep CSRF, design client properly |
| Auth persists from prior request | `WebSessionSecurityContextRepository` persisting | Use `NoOp` repo for API-key-only chain |
| No auth despite `authenticationManager` | Missing converter/filter for `X-API-Key` | `AuthenticationWebFilter` + `ServerAuthenticationConverter` |
| `@PreAuthorize` sees no auth | Wrong Reactor Context, bypassed chain | Let filter set context; proper reactive method security |
| Unit tests PASS but gateway fails | Ingress TLS/header propagation untested | E2E tests through proxy, including rate limits |
| Key ID/role leaked via 401 | Detailed error returned to client | Generic error, internal audit without secrets |
| Browser integration embeds API key | Secret inside JS bundle | Use OAuth2/OIDC/BFF instead of shared keys |
| Using BCrypt for random 256-bit key spikes CPU | Password KDF chosen without matching threat model | Use SHA-256/HMAC for high-entropy secrets + rate limit |
| No expiry | Key lives forever | Provisioning, expiration, rotation, revocation |

## 17. Security Review Checklist

1. [ ] API keys are generated by a CSPRNG with **at least 256-bit random secrets**, not user passwords or timestamps.
2. [ ] Key ID is a public identifier; real secrets are never logged or serialized.
3. [ ] DB stores a digest/HMAC verifier, never the raw secret.
4. [ ] Hash comparison uses `MessageDigest.isEqual` on equal-length digests.
5. [ ] Converter reads only the **designated header** and rejects duplicates/oversized/malformed values.
6. [ ] `ReactiveAuthenticationManager` returns `Mono.just`/`Mono.empty`/`Mono.error` strictly per contract.
7. [ ] Authentication token has `authenticated=false` before verification and retains no credentials afterward.
8. [ ] Principal, scopes, and tenant metadata come from the server-side registry, never from the request.
9. [ ] `SCOPE_*` mapping and default deny are tested.
10. [ ] 401/403 are properly distinguished; error bodies omit key IDs, secrets, and stack traces.
11. [ ] `AuthenticationWebFilter` is placed before authorization in `SecurityWebFilterChain`.
12. [ ] `NoOpServerSecurityContextRepository` is used properly for stateless API-key-only chains.
13. [ ] CSRF is disabled only when the threat model involves no auto-sent browser credentials.
14. [ ] CORS preflight is handled before auth if cross-origin browser access is supported.
15. [ ] Production key registry tracks multiple key IDs, owner, tenant, scopes, expiry, and enabled/revoked state.
16. [ ] Rotation includes an overlap window and revokes old keys within SLA.
17. [ ] Demo in-memory store is never used in multi-instance production.
18. [ ] Reactive repository never blocks the event loop; timeouts and connection pools are tuned.
19. [ ] HTTPS/TLS on every hop carrying the key; proxies/WAF/APM redact `X-API-Key`.
20. [ ] Rate limiting/quotas/monitoring per client/key ID with anomaly detection.
21. [ ] API keys never appear in query strings, URL history, public browser JS, Git, or CI logs.
22. [ ] Integration tests exercise the **real** manager, not solely `mockUser()`.
23. [ ] Per-resource/tenant permissions and high-risk operations are checked close to business actions.
24. [ ] Store outage policy never silently fails open; monitoring and incident response are ready.

## 18. Self-Check Questions

**1. What is the role of `ServerAuthenticationConverter`?**  
Extracts the API key from the HTTP request and builds an unauthenticated `Authentication`; does not query databases or grant permissions.

**2. What is the role of `ReactiveAuthenticationManager`?**  
Verifies the credential against a reactive repository/policy and returns an authenticated principal/authorities or an authentication error.

**3. When should `Mono.empty()` be returned?**  
When the manager **does not support the Authentication type**; a converter may also return empty when no credential is present. Never use empty to report a wrong key.

**4. What should a manager return for an invalid key?**  
`Mono.error(new BadCredentialsException(...))` or an appropriate `AuthenticationException`.

**5. What does a valid key return?**  
`Mono.just(authentication)` with `isAuthenticated=true`, principal/authorities from the trusted registry, and credentials stripped of the raw key.

**6. How much entropy does an API key need?**  
The demo uses a **256-bit random secret** from `SecureRandom`; what matters is a CSPRNG and an unpredictable secret.

**7. Why separate `keyId` and `secret`?**  
Allows looking up, revoking, rotating, and auditing individual keys by ID without scanning every hash.

**8. Why use a SHA-256 digest instead of BCrypt for the demo key?**  
A 256-bit random key has high entropy unlike human-chosen passwords; a SHA-256/HMAC verifier paired with rate limiting and policies is suitable. Never use this approach for weak passwords.

**9. Why use `MessageDigest.isEqual`?**  
Comparing verifier and candidate digests avoids ordinary String/byte loops that can leak data-dependent timing. It does not eliminate all lookup timing leaks.

**10. May the manager read roles from a header?**  
No. Roles/scopes must come from server-controlled key metadata.

**11. Why shouldn't `X-API-Key` be in the URL?**  
It is a bearer secret, and URLs are easily logged in browser history, `Referer` headers, access logs, and analytics.

**12. What does `NoOpServerSecurityContextRepository` mean?**  
Do not persist authentication across requests; every request must present credentials, though the key registry still holds server-side state.

**13. Why can a valid key receive 403?**  
Authentication succeeded, but the key lacks the required authority/scope for the route or resource.

**14. Why do missing/wrong keys typically return 401?**  
No valid Authentication is present for an endpoint requiring authentication.

**15. Does Spring Security automatically recognize `X-API-Key` with just an `authenticationManager`?**  
No. You need a `ServerAuthenticationConverter`/`AuthenticationWebFilter` or an equivalent mechanism.

**16. Can a raw API key be placed inside a browser SPA bundle?**  
No. Users can inspect the bundle/DevTools; use OAuth2/OIDC/PKCE or a BFF.

**17. May a reactive manager call synchronous JDBC directly?**  
No; it can block the Netty event loop. Use R2DBC/reactive Redis/WebClient or properly isolate blocking calls.

**18. Does the demo in-memory registry support revoking keys across all instances?**  
No. Each JVM has its own map and state is lost on restart.

**19. What happens if a key is disabled while a cache still holds an enabled record?**  
Requests may continue to succeed until the cache refreshes; design revocation SLAs, cache invalidation, and consistency carefully.

**20. Does an HTTP OPTIONS preflight carry the real API key?**  
Typically no; the browser asks permission for the `x-api-key` header before the real request. CORS must be handled before authentication.

**21. Can `@PreAuthorize` be used with an API key principal?**  
Yes, when reactive method security is configured properly and Authentication is placed in the Reactor Context; test authorities and business rules.

**22. Why should one authenticated request not automatically authorize subsequent requests?**  
Header-only API key auth is designed to be stateless: every request must present credentials and be evaluated against current status and permissions.

### Practice Exercises

1. Run the 8 manager tests; explain the difference between an unsupported token (empty Mono) and a wrong key (error Mono).
2. Run the 10 WebTestClient tests; confirm missing key = 401, valid read key = 200, missing admin scope = 403.
3. Add HTTP tests for an empty header, oversized header, comma-containing header, and non-canonical Base64URL.
4. Temporarily remove `NoOpServerSecurityContextRepository` on an experimental branch; inspect session persistence and explain why prior requests should not carry over.
5. Add a new key ID with `admin:write` scope to the test repository and verify POST `/api/admin` returns 200 while GET `/api/data` requires its own scope.
6. Add `tenantId` to `ApiKeyRecord` and check tenant ownership in a service before accessing data.
7. Design a PostgreSQL/R2DBC table for multiple API keys, unique IDs, expiry, `revokedAt`, and scopes.
8. Try disabling a key in the store (in the lab), confirm the next request returns 401, and simulate a stale cache to measure revocation latency.
9. Test the repository returning `Mono.error` and verify the manager does not produce an authenticated token.
10. Add per-key-ID + client-ID quotas/rate limits without storing secrets in metric labels.
11. Evaluate HMAC pepper vs SHA-256 verifier for random API keys and describe how to rotate the pepper safely.
12. Configure HTTPS/mTLS for an integration API and verify the gateway never logs `X-API-Key`.
13. Add CORS for a specific test frontend origin, confirm OPTIONS preflight is handled before key auth, and **never put a shared key into a real SPA**.
14. If the app also supports Bearer JWT, design a rule rejecting requests containing both Bearer and `X-API-Key`, and test credential precedence.
15. Describe a rotation strategy with an overlap window, monitoring of the old key, and revocation within SLA.
16. Compare custom API keys against OAuth2 client credentials for a partner service: threat model, scopes, expiry, revocation, scalability.
17. Add a unit test simulating an unknown key ID with a dummy digest comparison to reduce timing differences while controlling DoS.
18. Write an incident response checklist for a leaked API key: revoke, rotate, audit activity, inspect logs, notify owners, and invalidate dependent secrets.

## 19. Official References

- [Spring Security — Reactive Authentication](https://docs.spring.io/spring-security/reference/reactive/authentication/index.html): how authentication works in WebFlux.
- [Spring Security 6.3 API — ReactiveAuthenticationManager](https://docs.spring.io/spring-security/site/docs/6.3.0-RC1/api/org/springframework/security/authentication/ReactiveAuthenticationManager.html): meaning of `Mono.just`, `Mono.empty`, `Mono.error`.
- [Spring Security 6.3 API — AuthenticationWebFilter](https://docs.spring.io/spring-security/site/docs/6.3.0-M3/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html): matcher, converter, manager, context, and success/failure handlers.
- [Spring Security 6.3 API — ServerAuthenticationConverter](https://docs.spring.io/spring-security/site/docs/6.3.7/api/org/springframework/security/web/server/authentication/ServerAuthenticationConverter.html): converter from exchange to `Mono<Authentication>`.
- [Spring Security 6.3 API — ServerHttpSecurity](https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/config/web/server/ServerHttpSecurity.html): `addFilterAt`, `securityContextRepository`, `authorizeExchange`, `exceptionHandling`.
- [Spring Security 6.3 API — HttpStatusServerEntryPoint](https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/web/server/authentication/HttpStatusServerEntryPoint.html): generic 401 for APIs.
- [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): proper conditions for enabling/disabling CSRF with clients/sessions.
- [Spring Security — Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html): preflight before authentication.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `@EnableReactiveMethodSecurity` and Reactor Context.
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): TLS, authentication/authorization, HTTP statuses, security controls.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): secret storage, rotation, least privilege, auditing.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): generic authentication failure messages, throttling, and logging.
- [Oracle Java 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): CSPRNG for key generation.
- [Oracle Java 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): SHA-256 and `MessageDigest.isEqual`.

**Remember:** Proper API key implementation in **Spring Security reactive** follows **converter (HTTP credential) → `ReactiveAuthenticationManager` (verify against reactive store) → authenticated `Authentication` → authorization by authorities/resource**. Keys must be sufficiently random secrets, stored as digests, compared in constant time, least-privilege scoped, given expiry/rotation/revocation, and kept out of logs. **`Mono.empty()` only means the manager cannot identify/handle that Authentication type; a wrong API key must be `Mono.error(AuthenticationException)`.** With stateless API-key-only auth, every request needs its own credential; success returns 200, missing/wrong key returns 401, and insufficient permissions return 403.