# Issuing and Revoking API Keys for Service Accounts in Spring Security

An **API key** is a secret credential allowing an application or machine process to call APIs under an assigned identity and policy. In Spring Security systems, API keys for **service accounts** are commonly used to authenticate ETL jobs, workers, integration backends, monitoring systems, or service-to-service callers. Generating a random string is only the first step; a complete implementation manages **ownership, tenant binding, scopes, expiration, verifier storage, per-request verification, rotation, prompt policy-driven revocation, and auditing**.

This exercise walks from data design to REST APIs, a Spring Security Servlet filter, a standalone Java 17 demo, SQL examples, testing, and operational runbooks. It separates **secret credentials** from **identities/service accounts** and **resource access rights**, preventing possession of a key from becoming unbounded admin access.

**Learning outcomes:** you will be able to issue high-entropy API keys, **return the raw key only once**, store verifiers instead of plaintext, configure stateless authentication for service API paths, enforce least privilege, roll out replacement keys without downtime, and revoke old keys verifiably. Learning examples are not complete production systems; places requiring a real database, KMS, queue, Spring Boot wiring, or business logic are stated explicitly.

## 1. Three Concepts to Keep Separate

| Concept | Example | Responsibility |
| --- | --- | --- |
| **Service account** | `svc-order-sync` in tenant A | Machine identity, status, owner, baseline entitlements |
| **API key record** | Public Key ID `9c...`, expiry, and scopes | One credential belonging to an account, revocable individually |
| **Raw API key** | `sk_live_v1_{keyId}.{randomSecret}` | Bearer secret the caller presents to prove possession |
| **Authentication** | Verified principal `svc-order-sync` | Identifies which service is calling |
| **Authorization** | `orders:read` on tenant A | Checks whether the endpoint/resource/action is permitted |
| **Key management actor** | Administrator or workload with `keys:manage` | Who is allowed to issue/revoke credentials |

One service account can own **multiple API keys** to support rotation. Revoking **one key** does not necessarily lock the entire account; disabling the account must invalidate **every key** under it, even unexpired ones.

**An API key is not a staff password**, not a human account, and typically has no per-call MFA. Never allow a service key to sign into interactive admin pages unless a dedicated protocol was explicitly designed for it.

### Effective Permission Model

An API key must never elevate privileges beyond its owning service account. Model it as:

~~~text
Effective permissions =
    service_account.permissions
  ∩ api_key.scopes
  ∩ tenant/resource policy
  ∩ endpoint/action requirements
~~~

If the account only holds `orders:read`, a client requesting `scope=orders:write` when issuing a key cannot obtain write access. If the account is disabled or the tenant suspended, all requests must be denied regardless of key signature/digest validity.

## 2. Problem Statement and Acceptance Requirements

Suppose worker `order-exporter` needs to **read orders** for tenant A, without deleting or modifying orders. The system needs:

1. An authorized admin creates a service account inside tenant A.
2. The admin creates an API key with a label, scope `orders:read`, and a 30-day TTL per policy.
3. The server generates the secret via CSPRNG, stores a **hash/HMAC verifier**, and returns the raw key **only in the creation response**.
4. The worker stores the raw key in a secret manager; requests send it over HTTPS, never in URLs.
5. The server authenticates the key, verifying it is active, unexpired, and owned by an active account, tenant, and scope.
6. The worker rotates to a replacement key before the old key expires.
7. The admin revokes the old key; subsequent requests using the old key are rejected.
8. Audit who issued/revoked, key ID, reason, timestamp, and outcome; **never log the raw key**.

### Test Criteria

| Action | Expected Outcome |
| --- | --- |
| Valid key creation | 201, returns `keyId`, one-time `apiKey`, `expiresAt` |
| Creation by unauthorized actor | 403, no key issued |
| Requesting scope exceeding account entitlement | 403/422 per contract, no privilege expansion |
| GET with valid key holding scope | 200 if resource policy also allows |
| GET with wrong/nonexistent key | Generic 401 |
| POST requiring write scope using read-only key | 403 |
| Expired key | 401 |
| Revoked key | 401 once the node observes the updated state |
| Disabled account | Rejected even with matching key digest |
| Old key revoked, new key active | Old gets 401; new succeeds |
| Request missing key on machine API | 401 |
| Key leaked in logs/repo | Must revoke/rotate and investigate; "deleted the log" is insufficient |

Note: **401** means unauthenticated or invalid credential; **403** means authenticated yet insufficient privileges. When anti-disclosure policies apply, keep error bodies for different invalid-key causes generic.

## 3. Using API Keys Appropriately Without Overuse

API keys fit certain machine-to-machine integrations when paired with proper credential lifecycle and authorization controls. Still, they are **bearer secrets**: anyone possessing the secret can use it until expiration/revocation or an extra control blocks them.

Do not rely solely on API keys for financial or highly sensitive resources where higher assurance is needed. Consider **mTLS**, OAuth2 client credentials with short-lived access tokens, workload identity/federation, or signed requests with replay protection when the threat model demands it.

| Need | Tool to Consider |
| --- | --- |
| Simple internal worker with narrow scopes | Random API key + rotation/revocation |
| Cloud workloads with managed identity | Workload identity instead of static secrets |
| Client credentials and short-lived tokens | OAuth2 client credentials |
| Binding clients to certificates | mTLS or certificate-bound tokens |
| Human login with MFA | OIDC/SAML/password + MFA, not service API keys |
| Message-level replay protection | Signed requests with nonces/timestamps |

The goal is using credentials with manageable lifecycles, not forcing one pattern onto every system.

## 4. Pre-Implementation Threat Model

| Threat | Entry Point | Mitigation |
| --- | --- | --- |
| Secret exposure | Git, CI logs, stack traces, support tickets | Show once, secret manager, scanning, redaction, revoke |
| Bulk key guessing | Public endpoints | 256-bit CSPRNG, rate limiting, auditing |
| Stolen key used externally | Attacker machine | Reasonably short TTL, narrow scopes, optional mTLS/IP allowlist |
| Valid key crossing tenant boundary | Missing resource authorization | Backend account/tenant/resource checks |
| Privilege escalation at creation | Caller requests overly broad scopes | Admin privilege checks + scope intersection |
| Revoked key remains usable | Stale auth caches | Cache invalidation and bounded TTL |
| Expired key still accepted | Checking digest only, skipping expiry | Enforce expiry on every authentication |
| Disabled account yet key still works | Skipping account state check | Verify active account during authentication |
| Database/secret store outage | Fallback pass-through | Fail closed, return 503 where appropriate |
| API key treated as admin token | Conflated credential classes | Separate admin management auth from service APIs |
| Replay of captured request | Request-unbound bearer secret | TLS + consider mTLS/signed requests if needed |
| Log injection | Label/header containing CRLF | Structured logs, validation, allowlisted fields |

There is no "inherently unbreakable API key" merely because the string looks long. Protect it **from issuance to revocation** across client, transit, server, storage, and operations.

## 5. End-to-End Architecture

~~~text
Signed-in administrator (admin OIDC/session + MFA per policy)
        |
        | POST /admin/service-accounts/{accountId}/keys
        | {label, scopes, expiresAt}
        v
Management API
        | Verify actor permission + tenant ownership
        | Validate scope <= account permission policy
        | Generate random key secret
        | Store keyed verifier, metadata, expiration, audit
        v
201 Created {keyId, apiKey ONE TIME, expiresAt}
        |
        | Operator stores raw key in Secret Manager
        v
Worker / service client
        | HTTPS Authorization: ApiKey <raw-secret>
        v
Spring Security machine API (/svc/**)
        | Parse public keyId / secret
        | Lookup key metadata by ID
        | Verify HMAC/digest (constant-time comparison)
        | Check revokedAt, expiry, account active, tenant
        | Construct authenticated service principal
        v
Authorization: key scopes + account entitlement + resource policy
        |
        +--> 200 data (if permitted)
        +--> 401 unknown/invalid/revoked/expired
        +--> 403 authenticated but insufficient permissions
~~~

**Management vs. execution boundary:** key-creation/revocation endpoints must require strong admin authentication; never allow a `/svc/**` key to expand its own scopes by default.

### Suggested Endpoint Separation

| Endpoint | Caller | Meaning |
| --- | --- | --- |
| `POST /admin/service-accounts/{id}/keys` | Actor with key-management permission | Issue a key for the account |
| `GET /admin/service-accounts/{id}/keys` | Authorized actor | List **metadata**, never raw secrets |
| `DELETE /admin/service-accounts/{id}/keys/{keyId}` | Actor with revoke permission | Revoke a key |
| `POST /admin/service-accounts/{id}/keys/{keyId}/rotate` | Authorized actor, per API contract | Issue new key and manage overlap |
| `GET /svc/orders/{id}` | Service with active key and scope | Read tenant/resource-scoped data |

`rotate` must never silently invalidate the old key before the caller saves and rolls out the new key, unless performing an emergency rotation. Rotation workflows need explicit **states, timelines, owners, and rollback plans**.

## 6. Key Format: Public ID + High-Entropy Secret

A practical format:

~~~text
sk_live_v1_{keyId}.{randomSecret}
~~~

Where:

- `sk_live_v1_` is a prefix identifying key type, environment, and syntax version—**not security proof**.
- `keyId` is a public UUID used to look up metadata in the DB; it is **not a secret**.
- `randomSecret` holds at least 32 CSPRNG bytes (256 bits), unpadded base64url-encoded to 43 characters.
- The `.` separator splits ID from secret so parsing avoids scanning all records.

Synthetic example, **not a real credential**:

~~~text
sk_live_v1_01234567-89ab-4def-8012-3456789abcde.{43-base64url-chars}
~~~

Never use `UUID.randomUUID()` alone as the whole secret when policy requires high, upgradable entropy. UUID v4 carries lower entropy than a 256-bit random token; UUID fits the **public identifier**, while the secret should be generated separately.

Avoid: human passwords, timestamps, sequential numbers, MAC addresses, account IDs, hostnames, Java's `Random`, or client-supplied strings as secrets.

**Guessability:** with 256 bits of independent random entropy, direct brute-force guessing is practically infeasible. Yet a key leaked via logs/CI/Git is immediately usable; entropy never protects against exposure.

### Never Embed Privileges Inside the Token String

Raw keys do not need mutable embedded roles, admin flags, or tenant IDs. The server stores key → service account → tenant and scope metadata and checks them from a trusted store. A simple opaque random token allows **instant revocation by ID** without a JWT denylist.

## 7. Database Design with Tenant Isolation

PostgreSQL example (illustrative schema; add migrations, indexes, audit columns, and RLS for real environments):

~~~sql
CREATE TABLE service_account (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    name VARCHAR(120) NOT NULL,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('ACTIVE', 'DISABLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id, tenant_id)
);

CREATE TABLE service_api_key (
    id UUID PRIMARY KEY,
    service_account_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    label VARCHAR(120) NOT NULL,
    verifier BYTEA NOT NULL,
    verifier_key_version SMALLINT NOT NULL,
    created_by_actor_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    FOREIGN KEY (service_account_id, tenant_id)
        REFERENCES service_account (id, tenant_id),
    CHECK (expires_at > created_at)
);

CREATE TABLE service_api_key_scope (
    key_id UUID NOT NULL REFERENCES service_api_key(id),
    scope VARCHAR(120) NOT NULL,
    PRIMARY KEY (key_id, scope)
);

CREATE INDEX idx_api_key_account
    ON service_api_key (tenant_id, service_account_id);
~~~

Constraint rationale:

- Key IDs are queried directly by primary key; **never search by raw secret**.
- `verifier BYTEA` stores the HMAC/digest bytes, never the full key.
- `verifier_key_version` supports versioning the server-side pepper key.
- The composite foreign key guarantees a key never attaches to an account from another tenant.
- Nullable `revoked_at` records durable revocation state.
- `expires_at` is mandatory to prevent unintended perpetual keys.
- Scopes live in a dedicated table for auditing, reviews, and privilege management.
- `last_used_at` is operational metadata only; avoid synchronous updates on every call if that creates row contention.

**Deleting the row is rarely better than revoking it.** Retaining `revoked_at` supports auditing, incident response, and preventing accidental re-issuance. Raw secrets **must never resurrect** simply because an admin resets `revoked_at=NULL`.

If soft-deleting accounts, ensure the verifier always checks account status. You can also add RLS on admin queries and composite tenant checks in the application/service layer.

## 8. Verifiers: Why Never Store Plaintext API Keys?

If the database stores raw `sk_live_...` strings, a single DB dump lets attackers use every active key. For high-entropy random tokens, store a **cryptographic digest** of the token instead of plaintext, or use **HMAC-SHA-256** with a server/KMS-managed secret key (pepper).

HMAC workflow with a public key ID:

~~~text
raw key: prefix + keyId + "." + randomSecret

lookup: keyId -> keyRecord
verify:
    presentedVerifier = HMAC-SHA256(pepper, keyId + "." + randomSecret)
    compare constant-time to keyRecord.verifier

then:
    check expiresAt, revokedAt, serviceAccount.status,
    tenant/scope/resource policy
~~~

**HMAC is not encryption:** the server cannot decrypt the raw secret back out of the verifier. `GET /keys` APIs must return metadata only. If a raw key is lost, the solution is to **create a new key**, not "view the old password".

### Is SHA-256 Enough?

For genuinely random 256-bit secrets, fast SHA-256 digests are sound verifiers: attackers cannot run human-password dictionary attacks against 256 bits of entropy. HMAC with a server-side pepper adds defense-in-depth if the database leaks while the KMS key remains protected.

Comparison:

| Credential Type | Typical Entropy | Verifier Storage |
| --- | --- | --- |
| Human-chosen password | Low / guessable | Slow salted password hash (Argon2id/bcrypt/PBKDF2 per policy) |
| 32-byte CSPRNG API key | High, 256 bits | SHA-256 digest or HMAC-SHA-256 keyed verifier |
| Signed JWT | Carries claims/signature | Verify signature/issuer/audience/expiry; separate revocation strategy |
| mTLS client certificate | Public/private key cryptography | Certificate and trust policy, not an API key hash |

**Pepper rotation:** if you change the HMAC key without retaining raw API keys, you cannot recompute verifiers under the new pepper. Keep pepper versions for unexpired keys in KMS, force rotation/reissuance, or schedule revocation. Never simply overwrite the env var and break every existing key without notice.

**Constant-time comparison:** use `MessageDigest.isEqual(byte[],byte[])` for fixed-length verifiers; never use `Arrays.equals` or string equality on secret comparisons. Check key length/syntax before computing HMAC to avoid processing oversized inputs; note that constant-time comparison alone does not eliminate timing differences from DB lookups, account state, or network latency.

## 9. Issuing Keys: Binding the Right Owner and Privileges

Illustrative key-creation API contract:

~~~http
POST /admin/service-accounts/123e4567-e89b-42d3-a456-426614174000/keys HTTP/1.1
Authorization: Bearer <admin-access-token>
Content-Type: application/json

{
  "label": "order-export-prod",
  "scopes": ["orders:read"],
  "expiresInDays": 30
}
~~~

First and **only** response returning the key (placeholder values):

~~~http
HTTP/1.1 201 Created
Cache-Control: no-store
Content-Type: application/json

{
  "keyId": "123e4567-e89b-42d3-a456-426614174999",
  "apiKey": "<new-raw-key-shown-once>",
  "label": "order-export-prod",
  "scopes": ["orders:read"],
  "expiresAt": "2026-12-06T00:00:00Z"
}
~~~

Never put the full key into `Location`, query parameters, audit events, tracing baggage, plain emails, or response logs. If the UI offers a copy button, display it only on the creation result view and warn the admin to save it securely; **there is no "show again" API**.

Server workflow:

1. Authenticate the admin actor via a separate channel; enforce MFA/step-up per policy.
2. Verify the actor is authorized to manage this service account and its tenant.
3. Validate label, expiration, max keys per account, and scopes against a server-managed allowlist.
4. Compute permitted privileges: requested scopes must be a subset of account entitlements and actor grantable permissions.
5. Generate a new `keyId` + secret with `SecureRandom`; never accept raw secrets from browsers.
6. Compute HMAC/digest verifier; commit DB transaction with key metadata, scopes, and audit event.
7. Return the raw secret **only after commit succeeds**; avoid returning a key that does not exist in the DB.
8. Return `Cache-Control: no-store`; never log raw bodies to logs/APM.
9. Operator moves the secret into Secret Manager rather than pasting into source code or unprotected CI variables.

**Atomicity condition:** if the key-saving transaction fails, never report a key as issued. If the HTTP response drops after commit, the raw key cannot be recovered from the verifier—the admin must create another key; design UX/idempotency carefully to prevent accumulating orphaned keys.

### Blocking Privilege Escalation

A request asking for `["orders:read","orders:delete","keys:manage"]` is not valid merely because the JSON parses. Server policy enforces:

~~~text
account entitled:       orders:read, orders:write
actor may grant:        orders:read
requested:              orders:read, orders:delete
result:                 DENY (never silently grant delete)
~~~

Silently narrowing scopes instead of denying can mask misconfigurations; pick one explicit contract and report requested vs. granted scopes only to authorized actors, **never disclosing other tenants' data**.

## 10. Calling APIs with a Key: Strictly Over HTTPS and Headers

Example worker request:

~~~http
GET /svc/orders/42 HTTP/1.1
Host: api.example.org
Authorization: ApiKey <sk_live_v1_keyId.secret>
Accept: application/json
~~~

`ApiKey` here is an application-specific **custom authorization scheme**, not OAuth2 `Bearer`. If another API contract uses `X-API-Key`, all redaction and TLS rules still apply. Avoid mixing `Authorization: Bearer` for JWTs with opaque API keys in the same filter and guessing token types by prefix without explicit policies.

Never send keys in:

~~~text
GET /svc/orders?api_key=...
GET /svc/orders#api_key=...
Cookie: api_key=...   (unless using a dedicated cookie/CSRF design)
~~~

Queries and fragments risk landing in browser history, referrers, proxy logs, APM, or analytics. Header keys can still leak into logs; configure **`Authorization` header redaction** at ingress, app, and tracing layers.

Command line:

~~~bash
# Syntax example; populate the variable from a secret manager.
curl --fail-with-body \
  --header "Authorization: ApiKey $SERVICE_API_KEY" \
  "https://api.example.org/svc/orders/42"
~~~

Never paste raw keys into shell history, tickets, or CI logs. Variable syntax differs across shells; the snippet assumes a Bash-like shell. Avoid `curl -v` where output could print `Authorization` or tokens in shared environments.

## 11. Standalone Java 17: Lifecycle of Issuance, Verification, and Revocation

The program below runs on **JDK 17+ without Spring**, demonstrating end-to-end:

- Generating 32 bytes from `SecureRandom`.
- Token format with prefix + UUID ID + base64url secret; **never printing the raw token**.
- Storing HMAC-SHA-256 verifier, tenant, service account, scopes, expiry, and revoked timestamp.
- Looking up by key ID and verifying HMAC with `MessageDigest.isEqual`.
- Allowing only active, unexpired keys with matching verifiers.
- Issuing a replacement key before revoking the old key.
- Testing expiration with a deterministic clock for stable stdout.

**This is an in-memory lab**, omitting DB transactions, KMS, HTTP/TLS, rate limiting, tenant/account state, authorization, and production auditing. The simulated HMAC key is generated in-JVM; production loads peppers securely from KMS/secret managers with key versions.

### File ServiceApiKeyLifecycleDemo.java

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Arrays;
import java.util.Base64;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class ServiceApiKeyLifecycleDemo {

    private static final String PREFIX = "sk_demo_";
    private static final SecureRandom RANDOM = new SecureRandom();

    record Issued(String id, String token) {}

    record KeyRow(
            String owner,
            String tenant,
            Set<String> scopes,
            byte[] verifier,
            Instant expiresAt,
            Instant revokedAt) {}

    record Identity(String owner, String tenant, Set<String> scopes) {}

    static final class DemoClock extends Clock {
        private Instant now = Instant.parse("2026-01-01T00:00:00Z");

        public ZoneId getZone() { return ZoneOffset.UTC; }

        public Clock withZone(ZoneId zone) {
            return Clock.fixed(now, zone);
        }

        public Instant instant() { return now; }

        void advance(Duration duration) { now = now.plus(duration); }
    }

    private final Map<String, KeyRow> store = new ConcurrentHashMap<>();
    private final byte[] pepper;
    private final Clock clock;

    ServiceApiKeyLifecycleDemo(byte[] pepper, Clock clock) {
        if (pepper == null || pepper.length < 32) {
            throw new IllegalArgumentException("HMAC key too short");
        }
        this.pepper = pepper.clone();
        this.clock = Objects.requireNonNull(clock);
    }

    private byte[] verifierFor(String publicId, String secret) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(pepper, "HmacSHA256"));
            return mac.doFinal(
                    (publicId + "." + secret)
                            .getBytes(StandardCharsets.US_ASCII));
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException("HMAC unavailable", ex);
        }
    }

    Issued issue(
            String owner, String tenant, Set<String> scopes, Duration ttl) {

        if (ttl == null || ttl.isZero() || ttl.isNegative()) {
            throw new IllegalArgumentException("Invalid TTL");
        }

        String id = UUID.randomUUID().toString();
        byte[] randomSecret = new byte[32];
        RANDOM.nextBytes(randomSecret);

        String encoded = Base64.getUrlEncoder()
                .withoutPadding().encodeToString(randomSecret);
        Arrays.fill(randomSecret, (byte) 0);

        byte[] verifier = verifierFor(id, encoded);
        KeyRow row = new KeyRow(
                owner, tenant, Set.copyOf(scopes), verifier,
                clock.instant().plus(ttl), null);
        store.put(id, row);

        return new Issued(id, PREFIX + id + "." + encoded);
    }

    Optional<Identity> authenticate(String presented) {
        if (presented == null
                || presented.length() != PREFIX.length() + 36 + 1 + 43
                || !presented.startsWith(PREFIX)) {
            return Optional.empty();
        }

        int dot = presented.indexOf('.', PREFIX.length());
        if (dot != PREFIX.length() + 36) {
            return Optional.empty();
        }

        String id = presented.substring(PREFIX.length(), dot);
        String secret = presented.substring(dot + 1);
        try {
            UUID.fromString(id);
            byte[] decoded = Base64.getUrlDecoder().decode(secret);
            if (decoded.length != 32
                    || !Base64.getUrlEncoder().withoutPadding()
                            .encodeToString(decoded).equals(secret)) {
                return Optional.empty();
            }
            Arrays.fill(decoded, (byte) 0);
        } catch (IllegalArgumentException ex) {
            return Optional.empty();
        }

        KeyRow row = store.get(id);
        if (row == null) {
            return Optional.empty();
        }

        byte[] candidate = verifierFor(id, secret);
        if (!MessageDigest.isEqual(candidate, row.verifier())
                || row.revokedAt() != null
                || !clock.instant().isBefore(row.expiresAt())) {
            return Optional.empty();
        }

        return Optional.of(
                new Identity(row.owner(), row.tenant(), row.scopes()));
    }

    boolean revoke(String id) {
        return store.computeIfPresent(id, (key, row) ->
                row.revokedAt() != null ? row : new KeyRow(
                        row.owner(), row.tenant(), row.scopes(),
                        row.verifier(), row.expiresAt(), clock.instant()))
                != null;
    }

    public static void main(String[] args) {
        DemoClock clock = new DemoClock();
        byte[] pepper = new byte[32];
        RANDOM.nextBytes(pepper);

        ServiceApiKeyLifecycleDemo service =
                new ServiceApiKeyLifecycleDemo(pepper, clock);
        Arrays.fill(pepper, (byte) 0);

        Issued oldKey = service.issue(
                "svc-export", "tenant-a",
                Set.of("orders:read"), Duration.ofHours(1));

        System.out.println("Key format valid = "
                + oldKey.token().startsWith(PREFIX));
        System.out.println("Old key active = "
                + service.authenticate(oldKey.token()).isPresent());
        System.out.println("Read scope = "
                + service.authenticate(oldKey.token()).orElseThrow()
                        .scopes().contains("orders:read"));
        System.out.println("Write scope = "
                + service.authenticate(oldKey.token()).orElseThrow()
                        .scopes().contains("orders:write"));

        int secretStart = oldKey.token().indexOf('.') + 1;
        char first = oldKey.token().charAt(secretStart);
        String tampered = oldKey.token().substring(0, secretStart)
                + (first == 'A' ? "B" : "A")
                + oldKey.token().substring(secretStart + 1);

        System.out.println("Tampered accepted = "
                + service.authenticate(tampered).isPresent());

        Issued replacement = service.issue(
                "svc-export", "tenant-a",
                Set.of("orders:read"), Duration.ofHours(2));

        System.out.println("Replacement active = "
                + service.authenticate(replacement.token()).isPresent());

        service.revoke(oldKey.id());

        System.out.println("Revoked old accepted = "
                + service.authenticate(oldKey.token()).isPresent());
        System.out.println("New key still active = "
                + service.authenticate(replacement.token()).isPresent());

        clock.advance(Duration.ofHours(3));

        System.out.println("Expired accepted = "
                + service.authenticate(replacement.token()).isPresent());
    }
}
~~~

Compile and run:

~~~bash
javac ServiceApiKeyLifecycleDemo.java
java ServiceApiKeyLifecycleDemo
~~~

**Exact** stdout, independent of random raw keys/UUIDs:

~~~text
Key format valid = true
Old key active = true
Read scope = true
Write scope = false
Tampered accepted = false
Replacement active = true
Revoked old accepted = false
New key still active = true
Expired accepted = false
~~~

Outcome breakdown:

- Randomly generated key with matching HMAC verifier authenticates.
- Identity carries `orders:read`; it does not get `orders:write`.
- Flipping one character in the secret causes HMAC verification to fail.
- New key is issued **before** revoking the old key; both work during the brief overlap window.
- Revoking the old key does not affect the new key under the same account.
- Advancing the clock 3 hours expires the remaining key's TTL.

**Lab limitations to remember:** `ConcurrentHashMap` does not replace DB transactions; `revoke(id)` in the lab skips actor/tenant/permission checks, so **never expose it as a REST endpoint**. `Arrays.fill(randomSecret)` shrinks the lifetime of `byte[]` in memory, though immutable `String` values already created remain until GC; production Java code still must protect heap dumps, logs, and secret exposure.

## 12. From Lab to Database Service: Mandatory Invariants

A production key service should guarantee:

- `issueKey(accountId, requestedScopes, ttl, actor)` succeeds only after actor/tenant/account/scope validation and DB transaction commit.
- `findById(keyId)` returns verifier/metadata solely to the internal verifier; public admin lists never return verifiers or raw secrets.
- `verify(raw)` rejects malformed syntax, unknown keys, bad digests, revoked keys, expired keys, disabled accounts, and invalid tenants.
- `revoke(tenantId, accountId, keyId, actor)` enforces ownership/permissions and uses an atomic update.
- `listKeys(accountId)` returns only labels, key IDs, created/expiry/revoked/lastUsed timestamps, and scopes—with no "show raw" path.
- `rotate(...)` issues a new record and coordinates traffic cutover before revoking the old record.
- Audit records commit in the same transaction/outbox when durable proof is required.

**Separating verification from access control:** a matching digest proves only that the caller knows the secret. Tenant/account/resource authorization must still be enforced **afterward**. A valid key for tenant A must never read tenant B's data just because an ID in the URL matches.

## 13. Revocation: Endpoint Design and Atomic Updates

Illustrative REST contract:

~~~http
DELETE /admin/service-accounts/123e4567-e89b-42d3-a456-426614174000/keys/123e4567-e89b-42d3-a456-426614174999 HTTP/1.1
Authorization: Bearer <admin-access-token>
~~~

The response can be `204 No Content` once revocation is durably persisted. With idempotent DELETEs, repeating the call after revocation may still return 204 per contract; retries must **never restore ACTIVE state**.

Illustrative SQL pattern (executed after actor/tenant checks):

~~~sql
UPDATE service_api_key
SET revoked_at = now()
WHERE id = :key_id
  AND service_account_id = :account_id
  AND tenant_id = :tenant_id
  AND revoked_at IS NULL
RETURNING id, revoked_at;
~~~

When 0 rows return, the key may be nonexistent, already revoked, or owned by another tenant/account; the management API returns 204/404 per policy and **never discloses other tenants' resources**. To keep auditing idempotent without duplicate events, track explicit state versions inside the transaction.

For high-privilege separation, keep `keys:revoke` distinct from `keys:create`. Never let a compromised service account issue broad keys for itself via the management API without proper permissions and step-up auth.

### Revoking One Key vs. Disabling an Account

- Revoke key K1: K1 becomes invalid; K2 can remain active.
- Disable account A: every key K under A must be rejected by the verifier.
- Revoke all keys of an account: transactional/batch tenant-scoped update with auditing.
- Delete a resource or update tenant policy: never alter key bytes; resource authorization enforces the new policy.

Never wait out key expiration to remediate lost privileges, especially on suspected secret exposure.

## 14. Immediate Revocation and the Cache Problem

"Immediate revocation" holds true only when every node observes the new revoked state before accepting requests. If a service caches `keyId -> authenticated=true` for 30 minutes, a DB revocation can take up to 30 minutes to take effect.

| Lookup Strategy | Pros | Cons / Conditions |
| --- | --- | --- |
| DB lookup per request | Revocation effective right at commit | DB latency/load and availability coupling |
| Redis metadata cache with very short TTL | Cuts DB load | Stale window up to TTL |
| Event-driven cache invalidation | Fast propagation | Must handle dropped events and offline nodes |
| Local cache with unbounded TTL | Fast | **Cannot guarantee timely revocation** |
| Long-lived signed self-contained token | Zero lookup | Pre-expiry revocation needs denylist/introspection |

If policy mandates revocation takes effect within `N` seconds, measure propagation delay across nodes and enforce bounded staleness or strong consistency. Never promise "instant" revocation while retaining unbounded stale caches.

Requests already authenticated **before** the revocation timestamp may complete in-flight operations unless sensitive actions re-check state. Define the boundary between "new requests after revocation" and in-flight sensitive operations explicitly.

## 15. Zero-Downtime Rotation with Two Overlapping Keys

**Key rotation** is planned credential replacement, not just revocation. Safe workflow:

~~~text
T0: K1 active, worker uses K1
 |
T1: Create K2 on same account, minimal scopes, new TTL
 |   K1 active, K2 active
 |
T2: Save K2 into secret manager, roll out to workers
 |
T3: Smoke-test API calls with K2, monitor traffic and errors
 |
T4: Confirm zero workloads still need K1
 |
T5: Revoke K1, invalidate caches
 |
T6: Test K1 -> 401, K2 -> 200; audit complete
~~~

Keep the overlap window **short, time-boxed, and owned**; never let multiple active keys pile up indefinitely. If K1 is compromised, skip overlap and revoke immediately, handling any downtime via the emergency playbook.

**Never "reveal" K1 again** from the database during rotation: verifiers cannot be decrypted. K2 is a brand-new secret, never derived from K1. If K2 rollout fails before revocation, roll back to K1 while active; once revoked, never "unrevoke" K1—issue a fresh key instead.

### Managing TTLs and Expiration Alerts

Example policy:

- Default 30-day TTL for steady integrations;
- Shorter TTLs for test/ephemeral workloads;
- Alerts at 7, 3, and 1 days remaining;
- Old key revoked after rollout and overlap window;
- Account owners audit inventories and unused keys regularly.

These are **policy examples**, not universal mandates. Choose TTLs based on threat model, automation maturity, and operational cost; never create non-expiring keys without formal exception approval.

## 16. Spring Security Servlet: Filter Authenticating API Keys

Spring Security **does not automatically know where your custom API key lives or how to verify its verifier**. Implement the right authentication hook: a custom filter + verifier, or `AuthenticationFilter`/`AuthenticationProvider` with a custom token. The example below uses a clean filter for **machine-only stateless endpoints**.

### Internal Contract

Application interface and record:

~~~java
package demo.servicekeys;

import java.util.Set;

public record ServiceIdentity(
        String serviceAccountId,
        String tenantId,
        Set<String> scopes) {}

public interface ServiceApiKeyVerifier {
    // Return null when key is invalid/revoked/expired/account disabled.
    // Real infrastructure failures must throw to fail closed.
    ServiceIdentity verify(String rawApiKey);
}
~~~

**These are two separate Java files** (`ServiceIdentity.java` and `ServiceApiKeyVerifier.java`); never place two `public` top-level declarations in one file. A real `ServiceApiKeyVerifier` implementation queries the DB, computes HMAC, compares constant-time, verifies expiry/account/tenant, and returns server-derived identity. It **never reads authorities from the request**.

For simplicity, the contract returns `null` on bad credentials; production can use a sealed result or typed exceptions to distinguish invalid keys from infrastructure failures, without leaking sensitive details to callers.

### Filter Class

File **`ServiceApiKeyFilter.java`**:

~~~java
package demo.servicekeys;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.HttpHeaders;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class ServiceApiKeyFilter extends OncePerRequestFilter {

    private final ServiceApiKeyVerifier verifier;

    public ServiceApiKeyFilter(ServiceApiKeyVerifier verifier) {
        this.verifier = verifier;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String header = request.getHeader(HttpHeaders.AUTHORIZATION);

        if (header == null) {
            // Let AuthorizationFilter reject requests missing credentials.
            chain.doFilter(request, response);
            return;
        }

        if (header.length() > 256 || !header.startsWith("ApiKey ")) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        String raw = header.substring("ApiKey ".length());
        ServiceIdentity identity = verifier.verify(raw);

        if (identity == null) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        var authorities = identity.scopes().stream()
                .map(scope -> new SimpleGrantedAuthority("SCOPE_" + scope))
                .toList();

        Authentication authenticated =
                new PreAuthenticatedAuthenticationToken(
                        identity, null, authorities);

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authenticated);
        SecurityContextHolder.setContext(context);

        try {
            chain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
~~~

**Notes:**

- The filter accepts only the `ApiKey ` scheme on service paths governed by this chain.
- It never puts the raw key in `Authentication.getCredentials()`, never logs headers, and creates no session.
- `PreAuthenticatedAuthenticationToken` with the 3-argument constructor represents an identity **already verified by a trusted verifier**; never construct an authenticated token from unverified raw input.
- Authorities derive from **server-side DB scopes**, never client headers.
- `SecurityContextHolder.clearContext()` inside `finally` protects the thread; Spring Security's chain also runs cleanup lifecycles. The filter never reuses stale context on invalid keys.
- If the verifier/database fails, never let the request pass as valid; add an infrastructure error handler and ensure stack traces expose no sensitive data.
- For brevity, the sample does not yet enforce tenant resource ID checks inside the controller/service: **you must add that**.

**Never register the filter twice.** In Spring Boot, a `@Component` Filter bean can be auto-registered on the Servlet container alongside `SecurityFilterChain`. Here, instantiate `new ServiceApiKeyFilter(verifier)` inside the chain and **do not declare an extra `@Component` bean for the filter**.

## 17. Configuring a Dedicated Stateless SecurityFilterChain

Spring Security Servlet 6.x/7.x configuration snippet:

~~~java
@Bean
@Order(1)
SecurityFilterChain serviceApiChain(
        HttpSecurity http, ServiceApiKeyVerifier verifier)
        throws Exception {

    return http
            .securityMatcher("/svc/**")
            .sessionManagement(session -> session
                    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                    .securityContextRepository(
                            new NullSecurityContextRepository()))
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers(HttpMethod.GET, "/svc/orders/**")
                        .hasAuthority("SCOPE_orders:read")
                    .anyRequest().denyAll())
            .exceptionHandling(exceptions -> exceptions
                    .authenticationEntryPoint(
                            (req, res, error) ->
                                    res.sendError(HttpServletResponse.SC_UNAUTHORIZED)))
            .addFilterAfter(
                    new ServiceApiKeyFilter(verifier),
                    LogoutFilter.class)
            .build();
}
~~~

Place this method inside a Spring `@Configuration` class with imports:

~~~java
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.security.web.authentication.logout.LogoutFilter;
~~~

**This snippet requires a real Spring Boot Servlet app**, `ServiceApiKeyFilter`/`ServiceApiKeyVerifier`, and a verifier bean. There is no user/password store on this machine-only chain. Spring Security 6/7 uses the lambda DSL; the custom filter is inserted **after `LogoutFilter` and before `AuthorizationFilter`** so the principal is populated before authorization checks. Spring Security docs recommend placing custom authentication filters relative to standard filter ordering.

**Regarding CSRF:** disable CSRF on `/svc/**` only when those endpoints are **strictly stateless, accept client-controlled header credentials only, and never rely on browser-sent session cookies**. Never copy `csrf.disable()` to a cookie-backed web/admin chain. Keep CSRF enabled on browser admin management APIs per their auth model.

**Missing key:** `AuthorizationFilter` evaluates the unauthenticated request and the entry point returns 401 here. **Valid key lacking scope:** authorization returns 403 (assuming `AccessDeniedHandler`/entry point are configured properly). Tests must verify both.

### Controller and Resource Authorization

Example endpoint (Spring MVC snippet):

~~~java
@GetMapping("/svc/orders/{id}")
public OrderDto readOrder(
        @PathVariable String id,
        @AuthenticationPrincipal ServiceIdentity caller) {

    return orderService.findOrderForTenant(
            caller.tenantId(), id, caller.serviceAccountId());
}
~~~

`@AuthenticationPrincipal` injects the principal built by the filter; `orderService` must enforce tenant and record-level access. Never assume `/orders/{id}` is safe just because the key holds `orders:read`: a key belonging to tenant A must never read tenant B's order.

When an account has multiple scopes, `hasAuthority("SCOPE_orders:read")` provides one layer; backend services must still enforce action/resource/tenant boundaries at the data layer.

## 18. Should You Use an AuthenticationProvider Instead of Verifying in the Filter?

For larger systems, you can separate:

~~~text
HTTP filter: parse Authorization header
      |
      v
Unauthenticated ServiceApiKeyAuthenticationToken(rawKey)
      |
      v
AuthenticationManager / ProviderManager
      |
      v
ServiceApiKeyAuthenticationProvider
      | supports(custom token class)
      | verify digest/account/tenant
      v
Authenticated ServiceAccountPrincipal + authorities
      |
      v
SecurityContext, authorization
~~~

Advantages:

- Follows Spring Security's `AuthenticationManager` contract;
- Provider is unit-testable in isolation;
- Supports event publishers and auth metrics;
- Cleanly coordinates multiple credential types when boundaries are explicit.

However, **do not assume Spring ships a `ServiceApiKeyAuthenticationToken` class**; your app must write it, typically extending `AbstractAuthenticationToken`. The provider must return an authenticated token **only after verification**, keep `supports(...)` narrow, and attach an `AuthenticationEventPublisher` if constructing a custom Manager.

This exercise verifies directly in the filter for clarity; when refactoring to a provider, retain all cryptographic, revocation, authorization, and stateless-context invariants. Packing raw keys into `UsernamePasswordAuthenticationToken` invites confusion with password login; a dedicated token is cleaner.

## 19. Scopes Are Not Roles, and Tenants Are an Independent Dimension

Some systems assign `ROLE_SERVICE` and let callers hit everything. That is an anti-pattern when a service account only needs to read a few resources.

Distinguish:

| Field | Example | Source |
| --- | --- | --- |
| Principal type | `SERVICE_ACCOUNT` | Server verification outcome |
| Service account ID | Opaque UUID | Trusted database |
| Tenant ID | tenant A | Account/key metadata, never trusted from client input |
| Key ID | UUID key record | Token public prefix + lookup |
| Key scopes | `orders:read` | Granted in DB, not query params |
| Account entitlements | `orders:read`, `inventory:read` | Service account policy |
| Resource authorization | Does order belong to tenant A? | Controller/service/repository |

Case study:

~~~text
Key K1:
  owner = svc-export
  tenant = A
  scopes = orders:read

Request:
  GET /svc/orders/999
  order 999 belongs to tenant B

Authentication: VALID
Scope authorization: ORDERS_READ = YES
Resource authorization: TENANT_MATCH = NO
HTTP result: 403 or 404 per policy
~~~

Never let a client pick a tenant via an `X-Tenant-ID` header and treat that as authorization. At most, a header selects a requested tenant; the server must verify the principal is authorized for it. If impersonation/delegation exists, audit both actor and subject separately.

## 20. Testing with MockMvc and a Test Verifier

A realistic test suite needs **two layers**:

1. **Verifier tests**: cryptographic secret generation/digests, active/expired/revoked/disabled-account checks, tenant/scopes.
2. **HTTP filter tests**: missing/invalid key → 401; valid key → right principal and authorities; valid key missing scope → 403; no session; controller tenant/resource checks.

Spring Boot Servlet + Spring Security Test snippet (requires test app, verifier stub, and protected endpoint):

~~~java
// JUnit/MockMvc pseudocode: ServiceApiKeyVerifier stub from test context.
when(verifier.verify("valid-test-key"))
        .thenReturn(new ServiceIdentity(
                "svc-export", "tenant-a", Set.of("orders:read")));

mockMvc.perform(get("/svc/orders/42")
        .header("Authorization", "ApiKey valid-test-key"))
        .andExpect(status().isOk());

mockMvc.perform(get("/svc/orders/42"))
        .andExpect(status().isUnauthorized());

mockMvc.perform(get("/svc/orders/42")
        .header("Authorization", "ApiKey invalid-test-key"))
        .andExpect(status().isUnauthorized());
~~~

This is a **test snippet**, not standalone compilable code; add Mockito/Spring Test imports, app controllers/service stubs, and the registered filter chain. If testing the real verifier requiring `sk_demo_...` syntax, either stub at the HTTP layer or issue a real fixture key rather than sending the placeholder string.

To test 403 with a read-only key, configure a write route:

~~~java
.requestMatchers(HttpMethod.POST, "/svc/orders/**")
    .hasAuthority("SCOPE_orders:write")
~~~

For POST from stateless machine-only clients, ensure CSRF policy aligns with the chain. Send a POST using a key with `orders:read` and assert 403. Never test only `GET` and claim "scopes are enforced".

### Testing Zero Context Leakage Across Requests

~~~text
Request A: GET /svc/orders/42 + valid key -> 200, service principal
Request B: GET /svc/orders/42 WITHOUT key -> 401
Request C: GET /svc/orders/42 + revoked key -> 401
~~~

These must be three independent HTTP requests traversing `FilterChainProxy`. Never slap `@WithMockUser` onto the test class, as it can make a missing-key request appear authenticated and hide bugs. In production tests, also verify user A never bleeds into request B.

## 21. Testing Database, Expiration, and Concurrency

| Test | Expected Result |
| --- | --- |
| 32-byte CSPRNG | Valid secret format, distinct keys |
| Same account issued K1 and K2 | Distinct IDs and verifiers |
| Raw secret not stored in DB | Only verifier/metadata persisted |
| Correct HMAC key version | Verifier selected by version |
| Flipping one char in secret | Verification fails |
| Token with URL encoding / bad format | Rejected before DB or via strict parser |
| Unknown Key ID | Generic 401 |
| Exact TTL boundary | Active only while `now < expiresAt`; inactive at expiry |
| Non-null `revokedAt` | 401 |
| Disabled account | 401 even with matching verifier |
| K1 revoked, K2 active | K1 401, K2 200 |
| Tenant A key accessing B | 403/404 even with matching scope |
| Requested scope not granted by actor/account | Key not issued |
| Concurrent revoke/authenticate | Requests after commit observe policy state |
| Database unavailable | Fails closed; never passes on unbounded stale cache |
| Multi-node | K1 revocation takes effect within system SLO |
| Pepper version rotation | Old keys still verify per policy or migrate via reissue |
| Duplicate create API retries | Does not mint unexpected extra credentials |
| Delete key retry | Idempotent, never reactivates credential |
| Admin key listing | Contains zero raw keys or verifiers |
| Credentials in logs | Absent from access logs, traces, and tickets |

**Property test note:** excessively long or malformed tokens must fail fast without being parsed/logged verbatim, and exception messages must never feed audit payloads directly. Syntactically valid tokens with wrong secrets must fail even when the key ID exists.

## 22. Last-Used Tracking, Observability, and Auditing

Key events:

| Event Type | Safe Metadata to Store | Must Never Store |
| --- | --- | --- |
| `API_KEY_CREATED` | `actorRef`, `serviceAccountId`, `keyId`, `tenantRef`, scopes, expiry, time | Raw key, pepper, full response body |
| `API_KEY_ROTATION_STARTED` | old `keyId`, new `keyId`, owner, deadline | Raw K1/K2 |
| `API_KEY_REVOKED` | `actorRef`, `keyId`, reason code, timestamp | Raw key |
| `API_KEY_AUTH_SUCCESS` | `keyId`/opaque ref, service `principalRef`, route template, time | Credential header |
| `API_KEY_AUTH_FAILURE` | category INVALID/EXPIRED/REVOKED per internal policy, request ID | Raw key or untrusted ID |
| `API_KEY_EXPIRY_WARNING` | owner, `expiresAt`, `keyId` | Full token |
| `SERVICE_ACCOUNT_DISABLED` | actor, `accountId`, tenant, time | Credential material |

To avoid disclosing account/key existence, external responses can remain generic auth errors; **internal telemetry** categorizes failures only from trusted sources. Never put user-supplied tokens or keyIds into Prometheus labels—that explodes cardinality and risks credential leaks.

Updating `last_used_at` synchronously in the DB on every request creates row contention and hurts throughput. Batch or throttle updates via an event queue, keeping in mind `last_used` becomes **approximate** when async. Never rely solely on imprecise `last_used` timestamps to auto-revoke critical keys.

Audit logs need dedicated RBAC and retention. Spring's in-memory event publisher **does not guarantee durable auditing**; use a transactional outbox or reliable delivery mechanism when compliance requires durability.

## 23. Managing Raw Keys on the Client Side

Workers should receive secrets from a Secret Manager or workload secret injection:

~~~text
CI/CD provisions key -> Secret Manager version
                       |
                       v
                Deployment references secret version
                       |
                       v
                 Worker reads at startup/refresh
                       |
                       v
               HTTPS Authorization: ApiKey ...
~~~

Never put secrets into:

- Source code or `application.yml` committed to Git;
- Container image layers;
- Terminal shell history or screenshots;
- Query parameters or logged URLs;
- Crash reports or exception contexts;
- CI artifacts, test reports, or debug logs;
- Raw environment dumps;
- Tracing baggage or telemetry attributes.

Environment variables are an injection vector on some platforms, yet are not inherently safe if process dumps, diagnostics, or host users can read them. Evaluate per threat model, preferring RBAC-protected secret stores with rotation and strict logging hygiene.

During rotation, update the secret manager **by version**, roll out deterministically, and watch 401 rates. Never send raw keys to support over chat or email. If exposed, revoke and issue a new key; "deleting the commit containing the key" never guarantees Git history or CI caches are clean.

## 24. Service Accounts and Lifecycle Ownership

Every machine account still needs human accountability:

| Field | Why It Matters |
| --- | --- |
| Owner team / on-call | Receives expiration or exposure alerts |
| Purpose / description | Identifies which worker uses the key |
| Allowed tenants | Bounds data blast radius |
| Approved scopes | Enforces least privilege and periodic reviews |
| Environment | Prevents staging keys in production |
| Last used / status | Detects abandoned or misused keys |
| Creation actor / approver | Audit trail |
| Expiry / rotation deadline | Prevents unintended perpetual keys |
| Revocation contact / runbook | Fast incident response |

**Never issue all keys under a shared `system-admin` service account.** If one key leaks, you cannot tell which workload leaked it, and the blast radius is massive. Each workload or integration boundary should own its own account/key with narrow scopes.

When a service account loses its owner or a job retires, schedule reviews to disable the account and revoke its keys rather than leaving them active until expiration.

## 25. Common Anti-Patterns

| Anti-Pattern | Why It Is Wrong | Replacement |
| --- | --- | --- |
| Storing raw API keys in plaintext in DB | DB leak = credential compromise | SHA-256 / HMAC verifier |
| Key is just a UUID or timestamp | Likely lacks policy-required entropy | UUID ID + 32-byte CSPRNG secret |
| Generating tokens with `Random` | Not cryptographically secure | `SecureRandom` |
| API returns raw key on every GET | Secret spreads permanently across systems | Show once |
| Key without expiry or revocation | Impossible to handle incidents cleanly | TTL + revoked state |
| Letting keys self-select arbitrary scopes | Privilege escalation | Actor/account scope intersection |
| Checking scope while skipping tenant/resource | Cross-tenant data leak | Resource-layer authorization |
| Passing key in query parameter | Leaks via logs and referrers | TLS + header |
| Putting key in metric labels | Leaks + high cardinality | Opaque `eventId`/`reasonCode` |
| Bypassing auth on DB outage | Fail-open vulnerability | Fail closed, monitor infra failures |
| Unbounded verdict caching | Revoked keys keep working | Bounded TTL / invalidation |
| Missing issuer/revoker audit trail | Zero traceability | Durable audit trail per policy |
| Using API keys like human web passwords | Skips MFA/session policies | Separate machine and human flows |
| Registering the filter twice | Broken auth/cleanup lifecycle | Register once in `SecurityFilterChain` |
| Disabling CSRF across all chains | Exposes browser sessions | Separate machine-only chain config |
| Disabling account only in UI status | Keys still call APIs | Verifier checks account state |
| Using slow password hashing for random keys | Easily abused for CPU exhaustion | Digest/HMAC matching entropy |
| Changing HMAC key without versioning | Breaks all existing keys abruptly | Pepper versions and migration |
| Revoking K1 before deploying K2 | Outage/downtime | Rotation with brief overlap |
| Unrevoking a leaked key | Restores a compromised credential | Issue a new key; never revive old ones |

## 26. Incident Response: Detecting an Exposed API Key

If a secret appears in logs, Git, tickets, CI, or is suspected exfiltrated:

1. **Identify the key ID/owner and blast radius** via protected metadata without spreading the raw key further.
2. **Revoke immediately** if risk warrants; never wait for scheduled rotation.
3. Purge or quarantine leaked copies and inspect repo history, CI artifacts, and backups; never assume deleting a file makes the secret safe.
4. Issue a replacement key with minimal scopes, store it in Secret Manager, and roll out safely.
5. Audit key usage logs by time, route, resource/tenant, and trusted sources.
6. Assess whether sibling keys on the account must be revoked or the account disabled.
7. Notify owner/on-call/security per runbook; never paste the raw key into incident channels.
8. Identify root cause: body logging, URL queries, crash-dump credentials, copy-paste, or overbroad CI permissions.
9. Update detection rules, secret scanning, retention policies, and tests to prevent recurrence.
10. Record incident/audit outcomes without storing raw credentials as public evidence.

Any calls made before revocation may already have modified data; revoking a credential **never undoes completed actions**. Investigate resource access and run separate remediation.

## 27. Step-by-Step Capstone Exercise

**Step 1 — Design the account and privileges.** Create service account `svc-export` permitted only to read tenant A orders, with an owner team and ACTIVE status.

**Step 2 — Design the data model.** Create `service_account`, `service_api_key`, and `service_api_key_scope` tables with composite tenant FKs, expiry, and `revokedAt`, plus policy indexes/auditing.

**Step 3 — Write the issuer.** 32-byte CSPRNG secret, public key ID, format version; never accept client-supplied raw secrets. Compute HMAC with a KMS pepper and store the key version.

**Step 4 — Write the management API.** Issue keys only after actor auth, RBAC, tenant ownership, and scope allowlist checks; return the raw key once with `no-store`.

**Step 5 — Configure the client.** Store in secret manager, send via HTTPS `Authorization` header, and never log the raw key.

**Step 6 — Write the verifier.** Bounded parsing, lookup by key ID, constant-time HMAC check, revocation/expiry/account/tenant validation; return trusted `ServiceIdentity` or failure.

**Step 7 — Wire Spring Security.** Add a stateless authentication filter on the `/svc/**` chain, map scopes to authorities, and ensure the filter runs before `AuthorizationFilter` without double registration.

**Step 8 — Enforce resource authorization.** Combine `hasAuthority("SCOPE_orders:read")` with service/repository tenant + row ID checks.

**Step 9 — Test.** Exercise valid/invalid keys, revoked keys, expired keys, disabled accounts, differing scopes, differing tenants, and missing-key requests.

**Step 10 — Rotate.** Issue K2, roll out, confirm traffic, revoke K1, and test both K1 401 and K2 200.

**Step 11 — Operate.** Auditing, expiry alerts, owner inventory, secret scanning, revocation cache SLOs, incident runbooks, and secret-free metrics.

### Completion Criteria

- No public API endpoint can ever re-read an old raw key.
- A service needing only order reads cannot manage keys.
- Revoking an old key takes effect within the published SLO.
- Key rotation completes without disabling authentication.
- Tenant isolation is tested and zero credentials appear in logs.
- HMAC pepper/versioning has a documented rotation plan.
- Zero unauthenticated requests reach `/svc/**`.

## 28. Frequently Asked Questions

**Why not hash API keys with BCrypt like passwords?**

When an API key consists of 32 CSPRNG random bytes, its high entropy makes dictionary attacks infeasible. Fast cryptographic digests/HMACs paired with public key-ID lookup fit well. Human passwords have low entropy and thus require costly salted password hashing. Every choice still depends on threat modeling, DB protection, and key security.

**Does the Key ID need to be kept secret?**

No. It locates the record. Still, public IDs are operational metadata and shouldn't be scattered gratuitously in out-of-scope URLs. **Knowing the key ID must never authenticate a caller** without the random secret.

**Should already-expired keys still be revoked?**

Expiration already invalidates them; revoking can still explicitly record a compromise and feed audits. Never skip incident recording or inventory cleanup just because a key expired.

**Can privileges be reduced by deleting a scope from the record?**

Yes if policy allows, provided caches/authorization sync cleanly and it is audited. Many systems prefer issuing a new key with updated scopes and revoking the old key so privilege changes keep clean history. **Never silently widen an existing key's scopes** when its account gains new roles.

**Why did a request still return 200 after revoking a key?**

The request may have passed authentication before the revocation committed, a node may hold a stale cache, a session may have been created improperly from the key, or the service failed to check revocation on new calls. Inspect timelines, cache TTLs, nodes, and token/session architecture.

**If an API key is lost, can it be displayed again?**

No, if only a one-way verifier is stored. Create a new key, update client config, and revoke the lost key. "Show once" is a security feature, not a missing UX convenience.

**Must every request hit the DB?**

Depends on latency, availability, and revocation SLOs. Short caches or event invalidation can work if you explicitly bound the stale window. For highly sensitive resources, prefer introspection/DB checks or stronger bound credentials.

## 29. Final Checklist

1. Does the service account have an explicit ID, tenant, owner, status, and entitlements?
2. Is the admin actor authenticated/authorized before issuing or revoking keys?
3. Does the token separate a public key ID from at least 256 bits of random secret?
4. Is the secret generated via `SecureRandom` and shown exactly once?
5. Does the DB store only the verifier (SHA-256/HMAC), metadata, scopes, and timestamps—never the raw key?
6. Is the pepper sourced from KMS/secret manager with versioning and a rotation plan?
7. Does the verifier use bounded parsing, constant-time comparison, and fail closed on store errors?
8. Are revoked/expired/disabled-account keys rejected on new requests?
9. Does authorization intersect scopes with account, tenant, and resource policies?
10. Do machine endpoints use headers over HTTPS with zero queries, cookies, or secret logging?
11. Does the stateless Spring Security chain run the filter before authorization without double registration or mixing web admin flows?
12. Does K1→K2 rotation use a short overlap, deadline, and both K1 401 / K2 200 verification?
13. Does revocation cache TTL/invalidation meet the SLO and get measured across nodes?
14. Are admin lists, logs, and audits free of plaintext keys with no show-again endpoint?
15. Do regression tests cover invalid/expired/revoked/cross-tenant/privilege-escalation/concurrency cases?
16. Are owners, expiry alerts, inventory, secret scanning, and incident runbooks in place?

**Conclusion:** Issuing API keys for service accounts goes far beyond generating a random secret string. A safe design combines **service account identity**, **credential records**, **one-time secret display**, **one-way verifiers**, **expiration and least-privilege scopes**, **stateless Spring Security authentication**, **tenant/resource authorization**, and **verifiable rotation/revocation**. By consistently checking key activity and owner policy, keeping raw secrets out of observability pipelines, and rotating keys on schedule, API keys become controlled operational credentials rather than "permanent passwords" nobody dares revoke.

### References

- OWASP — Secrets Management Cheat Sheet (creation, rotation, revocation, expiration): https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- OWASP — REST Security Cheat Sheet (API keys, rate limiting): https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP — API Security Top 10: https://owasp.org/API-Security/editions/2023/en/0x11-t10/
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Servlet Security Filters and Custom Filters: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — SecurityContext Persistence: https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Authentication Events: https://docs.spring.io/spring-security/reference/servlet/authentication/events.html
- Spring Security — MockMvc Authentication Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html
- Oracle Java SE 17 — SecureRandom API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html
- Oracle Java SE 17 — MessageDigest API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html
- Oracle Java SE 17 — Mac API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html
