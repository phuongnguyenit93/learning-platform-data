# Hashing Keys When Only Verification Is Needed and Separating Identifiers from Secrets

## 1. Problem: An API key is an authentication secret, yet the server usually only needs to answer "does it match?"

An API key is typically a **bearer credential**: anyone possessing the valid key string can perform the actions granted to that key. For example, a partner calls an order management API using an `X-API-Key` header or an integration calls an internal endpoint. If the database table stores API keys in plaintext, a single leaked database backup can immediately expose **every active key**. When authenticating a request, the server usually does not need to know what the original secret is; it only needs to confirm whether the value presented by the client corresponds to an issued and still-valid credential.

Two key design decisions:

1. **Separate the key identifier (`key_id`) from the secret portion (`secret`):** `key_id` serves for lookup, administration, auditing, display, and database indexing. `secret` is held solely by the client to prove permission to use the key.
2. **Store a one-way verification value instead of plaintext:** generate a high-entropy secret, store a hash/HMAC computed from the secret, and compare again when the client presents the credential. Show the secret **only once at issuance**, with no "view again" feature for hashed secrets.

Illustrative key structure:

~~~text
ak_v1_m9u2Ujmt0V-2qGWl.3AF0eXlzh_8qd0C_g1LmdEX_sxfweTmO3t8yWgQ4d3M
|_____| |______________| |_________________________________________|
  prefix       key_id                 secret (illustrative example)

ak_v1_      = namespace/version format
key_id      = public identifier to look up the exact record
secret      = random string, must be strictly protected
~~~

This is only an **illustrative structure**, not a real key. In real-world designs, `key_id` and `secret` should be generated **independently** from a cryptographic random number generator. For example, 12–16 bytes for the public ID suffices to avoid collisions with a DB unique check; the secret portion can use **32 random bytes (256 bits)**, unpadded Base64url-encoded to fit HTTP headers cleanly.

With the `ak_v1_<id>.<secret>` format, the server performs two steps: extract `id` to locate a single record; compute the verification value from the presented `secret` and compare it against the stored value. **Never use `key_id` as proof of authentication** and never use a prefix or the last 4 characters of the secret to grant permissions.

## 2. Public identifiers and secrets have two different lifecycles

| Component | Public? | Stored in database? | Role |
|---|---|---|---|
| `key_id` | Can be public | Yes, with unique index | Key record lookup, revocation, reporting, per-key rate-limiting/auditing. |
| `secret` | No | **No** if only comparison is needed | Proof to authenticate the client. Returned to the client exactly once. |
| `secret_verifier` | Should not be public | Yes | One-way HMAC/hash to verify the secret when re-presented. |
| `pepper_version` | Can be metadata | Yes | Identifies which HMAC key was used to compute the verifier. |
| `owner_id` / `service_id` | Not a credential | Yes | Account/service principal that owns the key. |
| `permissions` / `scopes` | Sensitive metadata | Yes, policy-managed | Limits key permissions; never encode arbitrarily inside the secret. |
| `status`, `expires_at`, `revoked_at` | Metadata | Yes | Whether the key is still accepted. |
| `created_at`, `last_used_at` | Metadata | Yes | Governance, auditing, detecting stale unused keys. |

**Separating the ID from the secret does not mean the ID has to be secret.** A leaked `key_id` alone must not grant API access. However, avoid embedding emails, customer names, tenants, or sensitive internal IDs directly inside `key_id`, because it may appear in logs, admin URLs, screenshots, or customer support systems.

Choose random identifiers (or non-revealing identifiers) large enough to avoid collisions; the DB enforces a unique constraint and retries generating a new ID on collision. **Do not use sequential IDs in a way that reveals customer scale** unless explicitly required. `key_id` is the identity of the *credential*, distinct from `owner_id`, which is the identity of the *user/service*.

One owner can have multiple independent keys to ease application categorization and individual revocation: `partner-a-integration`, `ci-pipeline`, `data-export`. Display labels are only metadata; never use labels as secrets.

## 3. When is a one-way hash sufficient, and when is it not?

**One-way hash/HMAC fits when the server only needs to perform a comparison:**

~~~text
Client presents API key  ──►  Server
                             |
                       parse key_id
                             |
                    lookup credential row
                             |
                      HMAC(secret) / hash
                             |
                   constant-time compare
                             |
                   owner + scope + status
                             |
                     allow or deny
~~~

There is no step that decrypts the original secret.

**Unsuitable if the server must reuse the secret to act:** for instance, the application needs to read a third-party vendor's API key to call `https://vendor.example/api`; the server needs the original credential to place in the outbound request's Authorization header. If only a hash is stored, **the secret cannot be recovered**. In that case, store the secret **encrypted decryptable via KMS/secret manager with segregated access rights**, rotation governance, and auditing, or use delegation/OAuth to avoid storing long-lived bearer secrets. Never store plaintext just because it "needs to be reused."

Also distinguish **ordinary bearer API keys** from **keys used to sign every request**. In some request-signing protocols, the client computes an HMAC signature over method/path/body/timestamp and the server needs a shared secret (or public-key verification mechanism). A hash cannot substitute for the secret used to compute HMACs over arbitrary messages. For asymmetric signatures, the server can store the public key for verification, unlike HMAC shared secrets.

| Requirement | Appropriate storage | Why |
|---|---|---|
| Match API key sent by client in header | One-way HMAC/hash of a high-entropy secret | No need to retrieve the original secret. |
| Use secret to call another vendor's API | Encrypt at rest via KMS/secret manager; strict read permissions | Must retrieve valid secret for outbound calls. |
| Verify per-HTTP-request HMAC signature | Manage shared secret usable by verifier, or matching key-management solution | A hash of an API key cannot compute signatures for new messages. |
| Verify client asymmetric signature | Trusted public key/certificate + policy | Client private key is not needed. |
| User-chosen short, guessable key | Avoid this design; if unavoidable, use a password KDF like Argon2id with appropriate policy | Low-entropy secrets require offline guessing resistance; never arbitrarily use fast SHA-256. |

**The one-way nature of hashing is a data-protection feature**, not an inconvenience to be "reversed" later. When a client loses a key, the only option is to **create a new key and revoke the old key**, when the design stores only a verifier.

## 4. Entropy: the condition for SHA-256/HMAC to be safe for API keys

Server-generated API keys should have long, random secrets produced by a CSPRNG. In Java, use `java.security.SecureRandom`:

~~~java
byte[] randomBytes = new byte[32];      // 256 random bits
new java.security.SecureRandom().nextBytes(randomBytes);
String secret = java.util.Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(randomBytes);
~~~

The snippet above is an **illustrative snippet**, not a standalone Java program. 32 input bytes become **43 ASCII characters** in unpadded Base64url. Do not assume a 43-character string is cryptographically random just because of its length: the randomness source is the critical condition. Never use timestamps, usernames, `UUID.nameUUIDFromBytes`, `Math.random()`, sequential numbers, or transformations of guessable passwords as secrets.

For sufficiently strong randomly generated keys, **SHA-256 of the secret** is an acceptable one-way verifier under the threat model: an attacker with only the DB cannot feasibly brute-force the 256-bit space. However, with unkeyed `SHA-256(secret)`, anyone with the DB can check exposed or weak secrets with fast hashes; they can also probe if actual issuance had poor randomness.

A commonly useful design stores **HMAC-SHA-256 with a server-side pepper**:

~~~text
verifier = HMAC-SHA-256(pepper, "api-key:v1:" || secret)
                                      ▲
                              domain separation

Database: key_id, verifier, pepper_version, owner, permissions, status...
Secret manager/KMS: pepper v1, v2, ...    (NOT stored in the same DB)
Client: api_key has the original secret
~~~

A **pepper** is a secret key independent of the DB, used for HMAC. Never hardcode the pepper in source code, embed it in browser/mobile apps, or store the pepper in the same table as the verifier. If only the DB leaks, an attacker lacking the pepper cannot verify guessed secrets against the HMAC. However, if both the DB and pepper leak, this extra layer is lost; with 256-bit random secrets, entropy remains the primary defense.

**Salt** and **pepper** are not synonymous:

- **Salt** is a per-record random value, usually non-secret; especially critical for low-entropy password hashing.
- **Pepper** is a system-wide secret key managed outside the DB; HMAC uses the pepper to turn the verifier into a keyed value.
- For sufficiently random API keys, adding a per-record salt is not strictly necessary since the secret is already unique with overwhelming probability; if compliance or a specific algorithm requires it, explicitly define versions and metadata rather than mixing ad hoc.

**Do not mandate Argon2id for every bearer API key.** Password KDFs are designed for low-entropy human credentials; for 256-bit CSPRNG secrets, HMAC/SHA-256 has lower cost while guessing remains practically impossible. Depending on threat model or operational requirements, a slow KDF may be considered, but authentication load must be controlled. If keys are user-chosen, do not reason about them as 256-bit secrets.

## 5. Database structure: look up by `key_id`, never scan hashes across the table

Illustrative SQL table:

~~~sql
CREATE TABLE api_key_credentials (
    key_id           VARCHAR(64) PRIMARY KEY,
    owner_id         VARCHAR(80) NOT NULL,
    tenant_id        VARCHAR(80) NOT NULL,
    secret_verifier  BYTEA NOT NULL,              -- 32-byte HMAC-SHA-256
    pepper_version   SMALLINT NOT NULL,
    status           VARCHAR(16) NOT NULL,       -- ACTIVE / REVOKED / ...
    created_at       TIMESTAMPTZ NOT NULL,
    expires_at       TIMESTAMPTZ,
    revoked_at       TIMESTAMPTZ,
    last_used_at     TIMESTAMPTZ,
    label            VARCHAR(128)
);
CREATE INDEX idx_api_key_credentials_owner
    ON api_key_credentials(owner_id);
~~~

This is **PostgreSQL**-style SQL (e.g., `BYTEA`, `TIMESTAMPTZ`), omitting full foreign keys, permission tables, and check constraints. In a real system, store key permissions in tables constrained by `key_id`/scope/tenant or an approved policy model. If uniqueness across multiple environments is required, define namespace/issuer/tenant and matching DB schemas.

Verification flow:

1. Extract the credential over HTTPS from the **designated header** (e.g., `X-API-Key`), validating header count, size, and syntax. Never pass keys in URLs/query strings as they easily enter logs/caches/referrers.
2. Parse prefix, version, `key_id`, and `secret`; **do not let the client dictate the server's HMAC algorithm/key name** via an un-allowlisted value.
3. Query using the uniquely indexed `key_id`, fetching `secret_verifier`, `pepper_version`, status, and owner. If no key is found, reject and log only a truncated key ID if needed.
4. Retrieve the matching pepper version from the secret manager; compute the HMAC on the presented secret (using the same format and domain separator as at issuance).
5. Compare fixed-size tags using a non-short-circuiting byte comparison, such as `MessageDigest.isEqual` on equal-length HMAC arrays. DB lookup and status checks are not necessarily constant-time end-to-end; limit enumeration, rate limit, and return uniform error responses.
6. Only when the MAC matches, verify `status=ACTIVE`, `expires_at`, `revoked_at`, active owner, tenant, and endpoint permissions; create the Authentication and let application authorization proceed.
7. Update `last_used_at`/audits via a bounded or asynchronous mechanism to reduce write amplification, without logging the full key.

**Never query with `WHERE secret = ?`** because secrets are not stored. **Never query by hashing the entire random API key** when a public ID gives O(1)/indexed lookup; some variants can look up by an indexed hash, yet separating `key_id` makes administration, rotation, and logging clear without exposing the secret part.

### Example schema of an issued key

~~~json
{
  "key_id": "m9u2Ujmt0V-2qGWl",
  "owner_id": "service-partner-42",
  "tenant_id": "tenant-acme",
  "status": "ACTIVE",
  "pepper_version": 3,
  "permissions": ["ORDERS_READ", "ORDERS_CREATE"],
  "expires_at": "2027-01-01T00:00:00Z"
}
~~~

This JSON represents **credential record** metadata, **not the API key the client must send**. The `secret_verifier` field must not appear in admin APIs or client responses. A management endpoint may display `key_id`, name, scopes, status, and expiration date so users can locate/revoke keys.

## 6. Complete Java 17 example: issuing keys, HMAC, and safe comparison

The Java 17 program below uses the **Java Standard Library**, has no Spring dependencies, and runs via `javac`/`java`. It generates an independent random ID and secret, computes an HMAC of the secret, never prints the raw key, and tests four authentication conditions. **The code uses a random in-memory sample pepper for demonstration; real products must fetch a stable, managed pepper from KMS/secret manager.**

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class ApiKeyHashingDemo {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final Base64.Encoder URL_ENCODER =
            Base64.getUrlEncoder().withoutPadding();
    private static final String PREFIX = "ak_v1_";

    record StoredKey(String id, byte[] verifier, boolean active) {}
    record IssuedKey(String presented, StoredKey stored) {}

    static String randomUrlText(int bytes) {
        byte[] random = new byte[bytes];
        RANDOM.nextBytes(random);
        return URL_ENCODER.encodeToString(random);
    }

    static byte[] hmacSha256(byte[] pepper, String secret) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(pepper, "HmacSHA256"));
            String input = "api-key:v1:" + secret;  // domain separation
            return mac.doFinal(input.getBytes(StandardCharsets.UTF_8));
        } catch (Exception ex) {
            throw new IllegalStateException("HMAC unavailable", ex);
        }
    }

    static IssuedKey issue(byte[] pepper) {
        String publicId = randomUrlText(12);
        String secret = randomUrlText(32); // 256 secret bits
        String presented = PREFIX + publicId + "." + secret;
        StoredKey stored = new StoredKey(
                publicId, hmacSha256(pepper, secret), true);
        return new IssuedKey(presented, stored);
    }

    static boolean verify(String presented, StoredKey record, byte[] pepper) {
        if (presented == null || record == null
                || presented.length() > 160) {
            return false;
        }
        int dot = presented.indexOf('.');
        if (dot < 0 || dot != presented.lastIndexOf('.')) {
            return false;
        }
        String first = presented.substring(0, dot);
        if (!first.equals(PREFIX + record.id())) {
            return false;
        }
        String secret = presented.substring(dot + 1);
        if (!secret.matches("[A-Za-z0-9_-]{43}")) {
            return false;
        }
        byte[] actual = hmacSha256(pepper, secret);
        return record.active()
                && MessageDigest.isEqual(record.verifier(), actual);
    }

    public static void main(String[] args) {
        byte[] pepper = new byte[32];
        RANDOM.nextBytes(pepper);

        IssuedKey issued = issue(pepper);
        String apiKey = issued.presented();
        StoredKey record = issued.stored();

        int secretStart = apiKey.indexOf('.') + 1;
        char original = apiKey.charAt(secretStart);
        char different = original == 'A' ? 'B' : 'A';

        String wrongSecret = apiKey.substring(0, secretStart)
                + different + apiKey.substring(secretStart + 1);
        String wrongId = PREFIX + "another-id."
                + apiKey.substring(secretStart);
        StoredKey disabled = new StoredKey(
                record.id(), record.verifier(), false);

        System.out.println("correct: " + verify(apiKey, record, pepper));
        System.out.println("wrong secret: "
                + verify(wrongSecret, record, pepper));
        System.out.println("wrong id: "
                + verify(wrongId, record, pepper));
        System.out.println("disabled: "
                + verify(apiKey, disabled, pepper));
    }
}
~~~

Save under the exact name `ApiKeyHashingDemo.java`, then run:

~~~bash
javac ApiKeyHashingDemo.java
java ApiKeyHashingDemo
~~~

**Exact stdout**, even though key strings are random on every run:

~~~text
correct: true
wrong secret: false
wrong id: false
disabled: false
~~~

Explanation:

- `SecureRandom` generates two independent strings; `randomUrlText(32)` creates a 256-bit secret before Base64url encoding.
- `IssuedKey.presented` exists only as a transient issuance result to hand to the client; the `StoredKey` record keeps only the ID, verifier, and status.
- HMAC processes the exact same `api-key:v1:<secret>` string during both creation and verification. If changing format/algorithm, attach a version and migration strategy; never change silently.
- `MessageDigest.isEqual` compares the two HMAC byte arrays; for standard 32-byte tags, this avoids early-exit sequential character comparisons. **The `verify` function as a whole does not promise strictly constant time**, since parsing/lookup/validation have branching logic.
- `wrongSecret` preserves length and syntax while altering one character; the HMAC differs and is rejected. `wrongId` fails the record-matching check. `disabled` shows that a cryptographic match alone is insufficient when the credential is disabled.
- For clarity, the code holds byte arrays in a record and generates a RAM pepper each run. In production, use defensive copies/bounded memory lifetimes for byte arrays, manage the pepper outside the process/DB, store records in a DB with uniqueness, and control the lifecycle. Never print `apiKey` in logs or return it via normal lookup endpoints.

**Example boundary:** this program demonstrates API key hashing/verification; it does not create an HTTP server, Spring filter, authorization, DB access, auditing, or KMS. The following sections explain how to integrate cleanly with Spring Security.

## 7. Why is an HMAC with a "pepper" different from HMAC request signing?

The term HMAC can cause two purposes to be confused:

1. **HMAC as a storage verifier for API keys:** `HMAC(serverPepper, secretPresented)`. The server does not need to recover `secretPresented`; the client sends the bearer key directly in a header. HMAC is computed solely on the server for one-way comparison against the record.
2. **HMAC request signing:** the client holds a shared secret and signs a canonical string of HTTP method, path, timestamp/body, etc. The server must have a way to compute/verify signatures using the matching shared secret, alongside nonce/timestamp/replay protection. You cannot take only a bearer key's verifier and expect it to compute arbitrary request signatures.

Hashing the secret for comparison does not turn an API key into a replay-resistant token. **A stolen bearer API key can still be used until revoked/expired**, even though the database stores only the verifier. Therefore TLS, scoped permissions, rate limits, rotation, and log controls remain vital.

### HMAC versus password hashing

A 256-bit randomly server-generated API key has high entropy; no dictionary list can effectively guess it like user passwords. Fast `SHA-256` can suffice in some threat models; `HMAC-SHA-256` with an out-of-DB pepper adds a barrier if the DB leaks. If the credential is instead a user-invented word or short PIN, treat it as a **low-entropy password** and use Argon2id/scrypt/bcrypt appropriately instead of calling it an "API key" to justify a fast hash. The best approach is **never allowing users to pick guessable secrets**.

### Where is pepper rotation tricky?

A record has `pepper_version=v1` and stores only `HMAC(v1, secret)`. When creating v2, the server **cannot compute `HMAC(v2, secret)` from `HMAC(v1, secret)`** without the original secret. There are two approaches:

- **Rehash when the key is validly presented:** keep v1 temporarily active per policy, verify with pepper v1, then in a transaction update the verifier to v2 using the secret just presented by the client. Bound versions, concurrency, and the transition window.
- **Require issuing new keys:** when v1 is suspected compromised or v1 must be retired completely, require clients to rotate keys; revoke old records by a deadline.

Do not delete an old pepper before handling un-rehashed keys, unless the intent is to invalidate them. If the pepper is lost while only verifiers remain in the DB, old keys cannot be verified; the pepper must be restored from secure backups or credentials must be reissued. Peppers require versioning, secret-manager ACLs, backups, and controlled recovery/rollout procedures.

## 8. Workflow for issuing and returning an API key once

1. A client authorized to create keys on the admin API (authenticated via an appropriate mechanism, requiring MFA/step-up for sensitive keys) submits a key creation request with a label, least-privilege scopes, and expiry.
2. The server verifies **who is authorized to issue** for that tenant/service; never let the requester freely pick unauthorized owners/roles.
3. Generate `key_id` and `secret` with a CSPRNG, independently. Format versioning enables controlled migrations.
4. Compute `HMAC(pepperVersion, secret)`; persist the record with unique ID, owner, permissions, created/expiry/status inside a transaction. **Never store the original secret, even temporarily in the DB.**
5. Return the **full key once** in the HTTPS response to the authenticated caller. The UI must warn that it will not be displayed again and instruct the recipient to store it in a secret manager; never put it in email, analytics, error reporting, browser history, or console logs.
6. After that response, the application only displays metadata and partial ID/label; if a key is lost, issue a new key and revoke the old one.

Example response **illustrating structure, not a real credential**:

~~~json
{
  "key_id": "m9u2Ujmt0V-2qGWl",
  "api_key": "ak_v1_<public-id>.<secret-shown-once>",
  "label": "Partner order sync",
  "permissions": ["ORDERS_READ"],
  "expires_at": "2027-01-01T00:00:00Z",
  "warning": "Store this value securely; it will not be shown again."
}
~~~

**Note:** the `<...>` syntax here is a **placeholder notation in the JSON example**, not a valid key for sending requests. In a real API, the response includes `api_key` only upon creation; GET list/detail endpoints **never** return the full key or secret verifier. Public mobile/browser applications are generally unsuitable for storing long-lived static API keys because keys can be extracted; consider OAuth2/PKCE or short-lived token models.

## 9. How requests flow through Spring Security

In a **Spring Boot 3.x + Spring Security 6.x (Servlet)** application, a `OncePerRequestFilter` can handle the API key path. Logical steps:

~~~text
HTTP request /partner-api/orders
      |
      v
TLS (HTTPS) + gateway request policy
      |
      v
Spring Security FilterChain
      |
      +-- Extract X-API-Key from header (reject duplicate/malformed)
      +-- Parse: format version + key_id + secret
      +-- ApiKeyVerifier queries DB by key_id
      +-- HMAC(server pepper, secret) + MessageDigest.isEqual
      +-- Check ACTIVE, expiry, revocation, owner/tenant
      +-- Create Authentication(principal=owner, authorities=permissions)
      |
      v
Authorization: hasAuthority("ORDERS_READ"), tenant/resource policy
      |
      v
Controller/service
~~~

**Authentication** answers "which integration/owner's identity does this key prove?". **Authorization** answers "is this integration allowed to access this specific resource?". Never assign a `ROLE_ADMIN` principal to every valid API key.

Spring Security considerations:

- `X-API-Key` is a custom-defined header; a gateway might use `Authorization: ApiKey ...`. Pick one consistent convention, handle duplicated/combined headers, and bound header length.
- Isolate parsing/crypto/repository logic into an independent service; the filter only coordinates and updates `SecurityContext`.
- For custom filters, use `HttpSecurity.addFilterAfter(filter, LogoutFilter.class)` or an appropriate auth position in the filter chain order. Authentication must be established **before `AuthorizationFilter`**. Avoid registering the same filter both as an auto-registered servlet filter and inside Spring Security, as it may run twice or out of order.
- Scope the API key chain only to required paths using `securityMatcher("/partner-api/**")`; if the same app also serves browser logins/OIDC, use another properly scoped and ordered chain.
- If the API is strictly header-based and does not rely on cookies/sessions, configure `SessionCreationPolicy.STATELESS`. Consider disabling CSRF **only for strictly stateless API chains without browser auto-sent credentials**, never globally for websites with forms/cookies.
- Return **401 Unauthorized** for missing/wrong credentials and **403 Forbidden** when credentials are valid but lack permission, generally without revealing whether `key_id` exists. If the filter sends errors directly, handle 401 proactively because exceptions raised before `ExceptionTranslationFilter` may not be translated into HTTP responses as expected.

### Spring Security configuration example

The following is **application integration code**, assuming you have `ApiKeyVerifier`, `ApiKeyFilter`, and proper principal mapping. It is not a standalone `javac` program:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.LogoutFilter;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;

@Configuration
public class ApiKeySecurityConfig {

    @Bean
    SecurityFilterChain apiKeyChain(HttpSecurity http,
                                    ApiKeyVerifier verifier) throws Exception {
        http
            .securityMatcher("/partner-api/**")
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/partner-api/orders/create")
                    .hasAuthority("ORDERS_CREATE")
                .requestMatchers("/partner-api/orders/**")
                    .hasAuthority("ORDERS_READ")
                .anyRequest().authenticated())
            .addFilterAfter(new ApiKeyFilter(verifier), LogoutFilter.class);
        return http.build();
    }
}
~~~

The configuration above **assumes API keys are the sole authentication mechanism for the `/partner-api/**` chain** with no policy-violating fallback. In applications with multiple `SecurityFilterChain` beans, configure match order and a catch-all chain explicitly; missing a chain for other endpoints can introduce vulnerabilities. `ApiKeyFilter` must itself reject missing/invalid keys or delegate to an entry point, ensuring endpoints are never bypassed simply because the header is absent.

### Filter sketch using a controlled verifier

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Collections;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.web.filter.OncePerRequestFilter;

public final class ApiKeyFilter extends OncePerRequestFilter {
    private final ApiKeyVerifier verifier;

    public ApiKeyFilter(ApiKeyVerifier verifier) {
        this.verifier = verifier;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest req,
            HttpServletResponse res, FilterChain chain)
            throws ServletException, IOException {

        var headers = Collections.list(req.getHeaders("X-API-Key"));
        if (headers.size() != 1 || headers.get(0).isBlank()) {
            res.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        ApiKeyIdentity identity = verifier.authenticate(headers.get(0));
        if (identity == null) {
            res.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        var authentication = new PreAuthenticatedAuthenticationToken(
            identity, null, identity.authorities());

        var context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);
        try {
            chain.doFilter(req, res);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
~~~

Assumed application-implemented contracts:

~~~java
// Illustrative contract, requires real implementation:
public interface ApiKeyVerifier {
    // Return null when record missing, HMAC wrong, revoked, expired,
    // owner disabled, or wrong tenant; enforce DB timeout/load limits.
    ApiKeyIdentity authenticate(String presentedApiKey);
}

// Principal with key ID, owner, tenant, and exact GrantedAuthority.
// This is a contract sketch, not a complete standalone-compilable class.
public interface ApiKeyIdentity {
    java.util.Collection<? extends
        org.springframework.security.core.GrantedAuthority> authorities();
}
~~~

**Do not paste all of these Java blocks into one file expecting standalone compilation.** These snippets illustrate how to organize `ApiKeyFilter.java`, `ApiKeyVerifier.java`, and `ApiKeyIdentity.java` with Spring Security 6.x. For example, `ApiKeyFilter` handles missing/invalid headers with `401`, sets authentication after the verifier has checked all conditions, and clears the context. For async requests or other dispatch types, apply proper security context propagation. When multi-valued headers arrive, proxies must handle them consistently; commas or abnormal characters can be rejected under actual format rules.

Spring's `AuthenticationManager`/`AuthenticationProvider` APIs are also a solid choice for large deployments because they unify success/failure handling, account status, and auditing. There is no need to invent a custom security framework when framework contracts already fit.

## 10. Verification sequence and meaning of 401/403

A proper verifier must follow a sound sequence:

1. **Input limits:** accept the right header, a single value, bounded length, and valid characters. Reject keys sent via query parameters if the contract forbids them.
2. **Public lookup:** parse and query `key_id` in the DB via prepared statement / JPA repository; avoid errors that distinguish non-existent keys from wrong secrets.
3. **Cryptographic proof:** verify the secret via HMAC using the pepper version, comparing byte arrays without early exit.
4. **Credential lifecycle:** active, unexpired, unrevoked, policy-compliant; owner/service account active.
5. **Internal authorization:** resolve tenant/scopes, optionally apply IP allowlists, certificate-bound policies, or quotas; check the specific resource.
6. **Result:** build an Authentication with principal/authorities, or reject consistently.

| Scenario | Typically appropriate HTTP result | What to verify? |
|---|---|---|
| Missing `X-API-Key` on required endpoint | **401** | No accidental fallback to Anonymous or cookies. |
| Non-existent `key_id` | **401** | Do not reveal to the client that "ID exists." |
| Valid ID, wrong secret | **401** | HMAC mismatch; audit/rate limit. |
| Revoked/expired key | **401** | No longer a valid credential; do not serve stale cached Authentication. |
| Valid key, missing `ORDERS_CREATE` permission | **403** | Authentication succeeded, authorization insufficient. |
| Valid key, wrong tenant/resource | **403** or non-disclosing response per policy | Never rely on client-sent tenant headers. |
| Database/pepper manager unavailable | **503** or temporary error under fail-closed policy | Never turn infrastructure failure into an allowed key. |
| Oversized or malformed request | **400/401/413/431** per API/gateway | Bound parsing to prevent DoS. |

HTTP status codes depend on the API contract. The mandatory rule is **never grant access** when verification/lifecycle checks fail; not every failure must return the exact same code if the system has valid operational reasons. Public messages should avoid distinguishing "valid key_id but wrong secret," which helps attackers enumerate keys.

## 11. Rotation, revocation, and managing multiple keys

**Rotating an API key should not just overwrite the verifier in the DB** because clients holding the old secret will not automatically know the new secret. Common workflow:

1. Issue a new key with a new `key_id` and secret, bound to the same owner but with its own policy-compliant permissions and expiry.
2. Return the new secret **once** and instruct the client to store it in a secret manager and update config/deployments.
3. Allow **both keys in parallel** during a short controlled transition window (if risk permits), monitoring `last_used_at`/audits.
4. Once the client confirms using the new key, revoke the old key; if the old key is suspected leaked, **revoke immediately** without overlap.
5. Verify the API no longer accepts the old key; retain required metadata/audits per retention policy, removing the verifier when no longer needed.

Keys belonging to the same owner **do not share a secret**. Separate keys per integration, environment, and scope enable granular revocation and limit blast radius. When revoking a key or disabling an owner, verifier/permission caches must have **TTL, invalidation, and consistency** matching requirements. In multi-instance deployments, DB changes must propagate across instances within the allowed window.

**Never copy production API keys into staging/dev.** Each environment has its own namespace/trust domain, secret manager, and quotas. A prefix like `ak_live_` or `ak_test_` helps identify environments **but is not a cryptographic control**.

## 12. Organizing secrets and preventing key leakage

API keys can leak through many channels outside the database:

- **HTTP logs:** reverse proxies, ingress, APM/tracing, error reporting, servlet logging, or debug tools may capture headers. Define explicit redaction for `X-API-Key` and `Authorization`, including request dumps.
- **URL/query:** keys in URLs can appear in access logs, browser history, reverse proxy caches, and referrers; prefer headers over HTTPS.
- **Repository/CI:** never hardcode keys into Java, YAML, shell scripts, Dockerfiles, GitHub Actions logs, or documentation. Secret scanning/detection and a leak-revocation procedure are mandatory in production.
- **Environment/containers:** secrets in env vars can leak via process inspection/crashes/logs; use secret managers/file mounts appropriate to permissions and platform, without assuming env vars are an impenetrable vault.
- **Users:** keys are shown once; never send them via email/public chat, paste them into tickets/screenshots, and pass only a truncated ID in technical support.
- **Client/browser:** untrusted apps (publicly distributed SPAs/mobile binaries) cannot keep shared static API keys as long-term secrets. Consider OAuth2/PKCE and short-lived tokens.
- **TLS/gateway:** always use HTTPS; a gateway must not automatically bypass authentication/authorization just because TLS succeeded.

Logging `key_id` or a public prefix for investigation may be acceptable, but evaluate identifier/tenant exposure and prevent enumeration. A "last 4" display string from a secret is only an identification convenience, **not data used for authentication**.

## 13. Designing key storage for multi-tenant and multi-service systems

In a multi-tenant environment:

~~~text
Client API key
   |
   +-- parse key_id
   +-- lookup exactly one key row
   +-- verify secret HMAC
   +-- obtain trusted key.tenant_id + owner_id + permissions
   |
   +-- request tries to access /tenant/{tenant}/orders
            |
            +-- compare requested resource tenant against authenticated tenant
            +-- evaluate permission and object-level policy
            +-- allow/deny
~~~

**Never take the tenant from a client-sent `X-Tenant-Id` header and treat it as the authenticated tenant.** A header may help a client select context, yet the system must compare it against the tenant/delegation resolved from the verified credential. Each API key is granted specific permissions per owner/tenant. If a service account supports multiple tenants, a dedicated delegation/allowlist model is required.

When granting permissions, avoid overly broad `ROLE_ADMIN` roles for all internal keys. Example:

~~~text
key_id = abc123
owner  = integration_partner_42
tenant = tenant_acme
authorities:
   - ORDERS_READ
   - ORDERS_CREATE
quota:
   - 200 requests/minute
expiry:
   - 2027-01-01T00:00:00Z
~~~

This is illustrative metadata, not a secret credential. Permissions in the DB are the **policy source of truth**, while using them depends on an HMAC-verified credential that remains valid.

## 14. Common mistakes when hashing API keys

| Mistake | Why it is dangerous | Fix |
|---|---|---|
| Storing raw `ak_v1_id.secret` | A DB leak allows immediate replay of all keys | Store only ID + one-way verifier + metadata. |
| Storing only `secret` without an ID | Hard to look up/manage/revoke and audit accurately | Add a random public ID with a unique index. |
| Using `Math.random()` or timestamps | Predictable / low-entropy secrets | Generate with `SecureRandom` and sufficient random bytes. |
| Using fast SHA-256 for user-chosen keys | Weak keys can be brute-forced if hashes leak | Generate random keys; for low-entropy passwords use a password KDF. |
| Computing HMAC but storing the pepper in the DB | Loses protection if the DB leaks | Manage the pepper outside the DB with versioning/rotation. |
| Comparing secrets with `String.equals` / char-by-char | May introduce a timing side-channel by mismatch position | Compare **fixed-length digests/tags** via `MessageDigest.isEqual` or a trusted primitive. |
| Looking up by `key_id` and treating it as authenticated | A public ID is not proof of possessing the secret | Require secret and lifecycle verification. |
| Re-displaying keys from a GET endpoint | Increases credential exposure risk | One-time reveal; reissue if lost. |
| Mixing key ID with owner ID | Hard to rotate keys, leaks info, conflates permissions | Separate credential ID; owner/tenant are metadata. |
| Parsing keys with no length limit | Parser/DB DoS and log flooding | Enforce max length, character allowlist, reject duplicate headers. |
| Selecting tenant/scopes solely from request | Cross-tenant privilege escalation | Read permissions from the verified credential's record. |
| Revoked key still accepted from cache | Revocation has no effect | TTL/invalidation and rechecks per SLA. |
| Any auth failure falls back to session cookie | Downgrades/bypasses the API key boundary | Separate SecurityFilterChain with explicit policy. |
| Rotating pepper by HMAC-ing the old HMAC value | Not equivalent to HMAC of original secret; breaks old keys | Rehash on re-presented secret or reissue keys. |
| Treating `Base64` as a security mechanism | Base64 only encodes representation; it does not protect secrets | Use proper hashing/HMAC/HTTPS. |

## 15. Testing what actually needs to be proven

Do not just test "API returns 200 with a key"; test every boundary:

| Test | Expectation |
|---|---|
| Key created successfully | Full key returned once; DB contains only ID/verifier/metadata. |
| Query key list/detail | Neither secret nor secret verifier appears. |
| Key with valid ID + secret | HMAC matches, correct owner/principal and authorities. |
| Valid ID, one wrong secret char but valid format | 401, no permissions granted. |
| Non-existent ID, plausible-looking secret | 401, reveals no difference between valid/invalid ID. |
| Send only ID, omit secret | Rejected at parse stage. |
| Weak or overly short key, out-of-alphabet chars | Rejected without broad guessing/unclear normalization. |
| Two records with different IDs for same owner | Remaining key still works when one key is revoked. |
| Expired or revoked key | 401 immediately / per cache policy. |
| Owner disabled while key is still active | Authentication rejected. |
| Valid key missing `ORDERS_CREATE` | 403 on create endpoint; read endpoint still works per permissions. |
| Valid tenant A key calls tenant B resource | Rejected per tenant policy. |
| Pepper v1 and v2 rolled out | Verified per version; never mixes up peppers. |
| Deleting pepper v1 while v1 keys exist | Must have rehash/reissue plan; never auto-grant access. |
| DB/KMS outage | Fail closed, never "temporarily allow" requests. |
| Duplicate or abnormally combined headers | Rejected per canonical parsing policy. |
| Logs/tracing/counters | Contain no plaintext key. |
| Rotating keys | New key issued, old key revoked within SLA. |
| Replaying a stolen bearer API key | Still authenticates before revocation; requires TLS, anomaly detection, rapid revocation. |

**Comparison timing tests:** verify that code uses fixed-length digests + appropriate primitives; external benchmarks alone cannot prove end-to-end HTTP paths are constant-time because DB/cache/network latencies vary. Never rely on "measurements looked similar" to claim absolute security.

**Testing the Java demo:** `correct: true`, `wrong secret: false`, `wrong id: false`, `disabled: false` are deterministic despite random IDs/secrets. When integrating with Spring, use MockMvc to test 401/403 and integration tests with a mock DB/secret manager to verify rotation, concurrency, and no key logging.

## 16. Real-world scenario: partner order synchronization

A partner is issued a key with only `ORDERS_READ` and `ORDERS_CREATE` permissions in tenant A. When the partner calls:

~~~http
POST /partner-api/orders/create HTTP/1.1
Host: api.company.example
X-API-Key: ak_v1_<public-id>.<secret>
Content-Type: application/json

{"externalOrderId": "EXT-2026-001"}
~~~

The request is **illustrative**; strings containing `<...>` are not real credentials. The gateway/app should:

1. Enforce HTTPS and request/header limits; never expose the secret in logs.
2. Parse `key_id`, look up the exact record, compute secret HMAC, and compare digests safely.
3. Permit only if the key is ACTIVE, owner/tenant are valid, `ORDERS_CREATE` authority is present, quota is not exceeded, and the request passes validation.
4. Persist `externalOrderId` with idempotency/domain constraints and enforce business rules in the service. An API key does not replace transaction validation.
5. Audit the credential/owner ID and outcome, never the full bearer key.
6. Upon suspected exposure, administrators revoke that specific key and issue a new one; no need to overhaul the entire partner account.

If the partner calls `/partner-api/orders/delete-all`, even with a valid key, the request must be rejected if the corresponding authority is missing. Protecting the key in the DB is **at-rest credential protection**; permissions and business constraints are an independent control layer.

## 17. Production deployment checklist

Before going live, verify:

1. **Key generation:** secret ≥ 128 bits true entropy, preferably 256-bit CSPRNG; independent random unique ID; versioned format.
2. **At-rest verifier:** HMAC-SHA-256 with out-of-DB managed pepper (or threat-model-appropriate hash), no plaintext, no exposed verifier.
3. **Transport:** HTTPS mandatory; key only in approved headers/mechanisms, never in URLs/logs.
4. **Lookup/compare:** strict parsing, lookup by key ID, HMAC with identical canonical input/version, `MessageDigest.isEqual` on fixed-length digests.
5. **Principal/authority:** owner, tenant, and scopes resolved from the verified record; never create default admins.
6. **Lifecycle:** expiry, revocation, bounded rotation overlap, cache invalidation, owner disabling, and control over who can issue keys.
7. **Pepper management:** KMS/secret manager, versioning, backups, migration/reissue, and a recovery plan for lost peppers.
8. **Monitoring:** audit key IDs rather than secrets, rate limits/abuse detection, last-used tracking, anomaly alerts.
9. **Integration:** Spring Security filter in the right chain/order, clear stateless API policy, no duplicate registration, proper 401/403.
10. **Incident response:** emergency revocation procedure, log/backup/CI sweeps, and owner notification upon suspected leaks.

## 18. Conclusion

When the server **only needs to verify** a client's API key, the most manageable and damage-minimizing design is:

~~~text
public key_id + strong random secret (issued once)
             |
       store key_id + HMAC(secret) + owner/scopes/status
             |
    client presents key over HTTPS
             |
      lookup by key_id
             |
   HMAC + constant-time digest comparison
             |
    validate lifecycle and authorizations
~~~

**Separating `key_id` from `secret`** lets you find the exact record and revoke individual credentials without exposing the secret. **One-way hashing/HMAC** reduces immediate replay risk from database leaks; a server-side pepper adds protection when managed separately. Even so, an API key remains a bearer credential: transport protection, least privilege, lifecycle governance, and abuse monitoring are mandatory.

## References

- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): storing, issuing, rotating, and auditing secrets.
- [OWASP — Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html): protecting keys/peppers with secret management systems and lifecycles.
- [OWASP — Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): CSPRNG, cryptographic algorithms, and key management.
- [Spring Security — Servlet Architecture / Adding Custom Filters](https://docs.spring.io/spring-security/reference/servlet/architecture.html): filter ordering, `HttpSecurity.addFilterAfter`, and integrating custom filters.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `hasAuthority`, authorization, and filter chains.
- [Java 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): cryptographic random byte generator.
- [Java 17 — MessageDigest.isEqual](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html#isEqual(byte%5B%5D,byte%5B%5D)): comparing digests/tags.
- [Java 17 — Mac HmacSHA256](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html): HMAC in JCA.
- [RFC 4648](https://www.rfc-editor.org/rfc/rfc4648): Base64 and Base64url encoding.
