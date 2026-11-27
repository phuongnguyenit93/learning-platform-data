# Masking Sensitive Information in Keys, Values, Logs, and Traces in Spring Data Redis

## 1. A Redis Key Itself Can Be Sensitive Data

When integrating Redis into a Spring Boot application, developers often focus on protecting the connection password or encrypting traffic. Yet sensitive information can still leak even when connections use TLS and Redis enforces ACLs.

For example, an application caches customer profiles under a key:

```text
customer:email:alice.nguyen@example.org
```

The payload might be a JSON object holding an address and phone number. On every cache miss, the service logs:

```text
Cache miss for key customer:email:alice.nguyen@example.org
```

Distributed tracing automatically creates a Redis span recording the command and key, while an operator runs `MONITOR` to investigate latency. At that moment, the same email address lives in the **Redis keyspace, centralized logs, tracing backend, incident tickets, and backups**.

Even after deleting the cache key, copies already written to logs or traces persist according to each system's own retention window.

> Core principle: **Never put sensitive information into Redis, key names, metric labels, logs, or traces unless the application truly needs it there.** Protecting Redis passwords is essential, but it does not replace data privacy design.

This lesson explains how to reduce leakage across four primary surfaces:

1. **Key names and fields/indexes:** what leaks via key names, channel names, and metadata.
2. **Redis values:** what resides in Strings, Hashes, Streams, Sets, cache entries, snapshots, and backups.
3. **Logs:** what gets recorded by the application, driver, Redis server, or operations tools.
4. **Distributed traces and metrics:** what gets attached to span attributes, events, baggage, exemplars, or labels.

The goal is not merely replacing emails with `***` at the final log sink. A sound design minimizes sensitive data upfront and guards every point the data passes through.

## 2. Identifying Sensitive Data in a Redis Context

What counts as sensitive depends on the business domain, though you can start with these categories:

| Category | Examples | Risk if Exposed |
|---|---|---|
| Personal identifiers | Email, phone, address, government ID | User identification and unwanted contact |
| Authentication secrets | Passwords, API keys, bearer tokens, refresh tokens, OTPs | Unauthorized access |
| Financial data | Payment cards, account numbers, transaction details | Fraud, privacy breach |
| Private records | Health data, personal notes, location | Disclosure of private life |
| Linkable internal identifiers | User ID, tenant ID, session ID, order ID | Tracking/correlation, exposing user activity |
| Business-sensitive data | Custom customer pricing, discounts, internal plans | Commercial leakage |
| Infrastructure credentials | Redis URI, passwords, private keys, certificate keys | System compromise |
| Event contents | Stream/Pub/Sub payloads and DLQs | Replicating business info across many systems |

Not every ID is equally secret. Still, a seemingly "harmless" ID becomes sensitive if it can be correlated back to a customer or used as a bearer access token.

### 2.1. Classifying by Consequence

A development team can classify each data item explicitly:

- **Public:** safe to display to unauthenticated users.
- **Internal:** intended for internal application use only.
- **Confidential:** readership and transmission channels must be restricted.
- **Secret:** exposure directly grants access or causes immediate harm.

This is an **illustrative classification model**, not a universal standard for every company. Actual rules must come from your organization's policies and applicable regulations.

### 2.2. Audit Data Surfaces, Not Just Java Classes

A field like `Customer.email` can end up in:

```text
Customer.email
   ├─ @Cacheable SpEL key="#email"
   ├─ Redis String key name
   ├─ Redis Hash field / secondary index
   ├─ JSON object cached value
   ├─ Stream record / Pub/Sub message
   ├─ Logger.debug("customer={}", customer)
   ├─ Exception.getMessage()
   ├─ OpenTelemetry span attribute
   ├─ Micrometer tag customer_id=...
   ├─ SLOWLOG / MONITOR when command inspection is active
   └─ RDB/AOF, replicas, and backups
```

A feature can be completely secure at the HTTP layer while leaking across all of these operational channels.

## 3. Threat Modeling: Who Can See What?

Not everyone permitted to inspect a Redis data node is authorized to read application logs, and not everyone viewing Grafana dashboards should see raw payloads.

| Surface | Who Can View It | Data at Risk | Control |
|---|---|---|---|
| Redis key names | Redis users with read/list rights, ops | Emails/IDs/tokens embedded in keys | Key naming and ACLs |
| Redis values | Clients permitted `GET`/`HGET`/`XRANGE`... | JSON, tokens, profiles | Minimization, ACLs, encryption |
| Redis Pub/Sub | Permitted subscribers | Channels and message bodies | Channel ACLs, no secrets sent |
| Redis Streams | Consumers/readers, exporters, backups | Event fields, payloads, and DLQs | Schemas, retention, ACLs |
| Application logs | Developers, support, log backends | Keys, values, exceptions, user context | Redaction at source, RBAC, retention |
| Tracing backend | Anyone with trace access | Span attributes, DB statements, exceptions | Attribute allowlists, sampling |
| Metrics backend | Dashboard viewers | Tags, cardinality, correlation IDs | Low-cardinality tag policy |
| Redis MONITOR | Operators with command rights | Observed Redis commands and arguments | Least privilege, runbooks |
| Persistence/backups | Backup jobs, operators, storage admins | Full datasets and metadata | Encryption, access control, retention |
| Memory dumps / diagnostics | Operators, crash collectors | Secrets sitting in memory | Restricted collection procedures |

Even an apparently benign key name carrying an internal ID lets log viewers correlate multiple actions to the same account. **Pseudonymization is not absolute anonymization**: a stable pseudonym can still link records together.

### 3.1. Layered Protection

- **Application design:** decide whether data needs to be stored at all and in what form.
- **Application security:** tenant checks, authorization, input validation, and safe serializers.
- **Redis security:** TLS, ACLs, topology, and backup permissions.
- **Observability security:** log/trace/tag allowlists, sampling, access control, and retention.
- **Operations:** incident response, debugging procedures, and secret rotation.

If the application itself logs a bearer token, TLS between Spring and Redis **cannot undo** that mistake.

## 4. Never Put Emails, Tokens, or Personal Data Directly in Keys

### 4.1. Unsafe Key Patterns

```text
user:alice@example.org:profile
phone:+84123456789:otp
session:eyJhbGciOi...:state
reset-password:raw-reset-token
customer:123456789:medical-history
search:nguyen van a 0912345678:results
```

These can surface in:

- `SCAN`, `KEYS`, and keyspace inspection tools.
- `MONITOR`/diagnostics and logged commands.
- Keyspace notifications when keys expire.
- Certain exceptions or debug statements.
- Backups, RDB/AOF files, and analysis tools.
- Redis Cluster hash tags if identifiers are embedded.
- Dashboard/metric labels if the app exports keys as tags.

Even when values are encrypted, **key names still reveal identities or business relationships**.

### 4.2. Designing Keys with Functional Prefixes and Safe Identifiers

Instead of:

```text
profile:alice@example.org
```

use:

```text
customer:profile:v2:yZgtK5H3eC0y...
```

Here the suffix is an **identifier derived via keyed HMAC** or a random ID not directly linkable to PII. The prefix conveys namespace and schema version without exposing personal data.

A clean key pattern typically follows:

```text
<domain>:<purpose>:<schema-version>:<opaque-id>
```

Examples:

```text
customer:profile:v2:<opaque-id>
auth:session:v1:<opaque-id>
rate-limit:account:v3:<opaque-id>
cache:product-summary:v4:<opaque-id>
```

**An opaque ID is not automatically safe if it is reversible or easily guessable.** Base64-encoding an email is encoding, not security. An unkeyed SHA-256 hash of a phone number or email can still be broken via dictionary attacks because the input space is predictable.

## 5. How Do Hashing, HMAC, Encryption, and Random IDs Differ?

| ID Generation Method | Properties | When Suitable | Limitations |
|---|---|---|---|
| Raw email/phone | Easy correlation | Only inside layers authorized to read PII | Direct exposure |
| Base64(email) | Trivially reversible | Encoding/transport | **Does not hide data** |
| SHA-256(email) | No plaintext stored | High-entropy data fingerprints | Emails/phones are easily guessed offline |
| HMAC-SHA-256(secret, canonical ID) | Deterministic; hard to test guesses without the secret | Stable lookup keys avoiding raw PII | Digest remains linkable across hits |
| Random UUID/ULID | Reveals no PII if generated with sufficient randomness | When mapping lives in another store | Requires storing mapping and managing lifecycle |
| Encryption (AEAD) | Reversible with the key | Payloads needing exact recovery | Needs key management/nonces/rotation |

### 5.1. Why Are Unkeyed Hashes Easily Guessed?

Suppose a key contains:

```text
customer:email-sha256:<sha256(email)>
```

An attacker with a list of common emails can compute SHA-256 for each email, match against observed digests, and identify subjects—no hash inversion required.

With HMAC, testing candidate emails requires knowing the **HMAC secret**. Still, if the secret leaks, offline guessing becomes possible again, and HMAC outputs remain stable identifiers capable of tracking activity.

### 5.2. Never Treat an HMAC ID as an Authorization Token

An HMAC key name masks an identifier—**it does not prove the caller has permission to read the data**. A client with broad Redis access can still read the value of any key it sees.

Always check tenant/user/role permissions in the business layer, while scoping Redis ACLs per service. Never substitute an "unguessable" digest for authorization.

## 6. Java Example: Deriving Redis Keys with HMAC-SHA-256

A factory creating deterministic keys per tenant/customer pair without placing raw IDs into key names:

```java
package com.example.security.redis;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public final class PrivateRedisKeyFactory {

    private static final String ALGORITHM = "HmacSHA256";
    private final byte[] hmacSecret;

    public PrivateRedisKeyFactory(
            @Value("${app.redis.keys.hmac-secret-base64}")
            String secretBase64) {

        this.hmacSecret = Base64.getDecoder()
                .decode(secretBase64);

        if (hmacSecret.length < 32) {
            throw new IllegalArgumentException(
                    "HMAC key material is too short"
            );
        }
    }

    public String customerProfileKey(
            String tenantId,
            String customerId) {

        if (tenantId == null || tenantId.isBlank()
                || customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException(
                    "tenantId and customerId are required"
            );
        }

        // Length-prefix avoids ambiguity between the two components.
        String canonical =
                tenantId.length() + ":" + tenantId
                + customerId.length() + ":" + customerId;

        byte[] digest = hmac(canonical);

        return "customer:profile:v2:"
                + Base64.getUrlEncoder()
                        .withoutPadding()
                        .encodeToString(digest);
    }

    private byte[] hmac(String input) {
        try {
            // Create a fresh Mac per call: Mac is not thread-safe by default.
            Mac mac = Mac.getInstance(ALGORITHM);
            mac.init(new SecretKeySpec(
                    hmacSecret, ALGORITHM));

            return mac.doFinal(
                    input.getBytes(StandardCharsets.UTF_8));
        } catch (GeneralSecurityException ex) {
            // Never include identifiers or secrets in exceptions.
            throw new IllegalStateException(
                    "Cannot derive Redis cache identifier"
            );
        }
    }
}
```

Design notes:

- Both `tenantId` and `customerId` feed into the HMAC so two tenants never accidentally share a key.
- `HmacSHA256` uses a secret key rather than a raw hash.
- Inputs must be **canonicalized consistently** across service versions; if emails are case-insensitive per application policy, normalize in the domain layer per approved rules.
- The `v2` prefix is an independent version allowing format or HMAC key changes; it does not manage data migration automatically.
- The secret must be injected via a secret manager or secure deployment config. The property shows only the config key; never commit real keys to source.
- Avoid logging `canonical`, `customerId`, or full digests unnecessarily; stable digests remain linkable data.

**Note on HMAC rotation:** rotating the secret generates different keys for the same customer, meaning old cache entries either sit until TTL expiry or require migration. If Redis stores non-regenerable data, changing the secret key without a lookup/migration plan for old keys can make data unreachable.

### 6.1. HMAC Does Not Protect Values

The key:

```text
customer:profile:v2:<hmac-digest>
```

no longer exposes plaintext email, yet the value may still be:

```json
{"email":"alice@example.org","phone":"+84000000000"}
```

Anyone permitted to read the value still sees the data. Apply **data minimization, authorization, and encryption where required** to values independently of masking keys.

## 7. Spring Cache: `@Cacheable` Can Accidentally Turn Parameters into Keys

Easy to write, yet risky:

```java
@Cacheable(cacheNames = "customerProfiles", key = "#email")
public CustomerProfile findByEmail(String email) {
    return repository.findByEmail(email);
}
```

If `RedisCacheManager` prefixes with the cache name and uses a String key serializer, the Redis key contains the email:

```text
customerProfiles::alice@example.org
```

Risk does not come only from SpEL. With default key generation, Spring Cache derives keys from method arguments and their `toString()`/serializers. A parameter object holding email/phone can end up inside the Redis key representation depending on configuration.

### 7.1. Using a KeyGenerator to Derive Safe Keys

```java
package com.example.security.redis;

import java.lang.reflect.Method;

import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.interceptor.KeyGenerator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class PrivateCacheKeyConfiguration {

    @Bean("privateCustomerKeyGenerator")
    public KeyGenerator privateCustomerKeyGenerator(
            PrivateRedisKeyFactory factory) {

        return (Object target, Method method, Object... params) -> {
            if (params.length != 2
                    || !(params[0] instanceof String tenant)
                    || !(params[1] instanceof String customerId)) {
                throw new IllegalArgumentException(
                        "Unexpected private cache key arguments"
                );
            }

            return factory.customerProfileKey(
                    tenant, customerId);
        };
    }
}
```

Then:

```java
@Service
public class CustomerProfileQueryService {

    private final CustomerRepository repository;

    public CustomerProfileQueryService(
            CustomerRepository repository) {
        this.repository = repository;
    }

    @Cacheable(
            cacheNames = "customerProfiles",
            keyGenerator = "privateCustomerKeyGenerator"
    )
    public CustomerProfile find(
            String tenantId, String customerId) {

        // Authorization/tenant scope must be enforced
        // at the appropriate service boundary.
        return repository.findForTenant(
                tenantId, customerId);
    }
}
```

This illustrates a pattern where the method takes two String arguments in a fixed order. `CustomerRepository` and `CustomerProfile` are application domain types.

When sharing a key generator across multiple methods, include **method identity/cache region** in the HMAC input if distinct methods could otherwise generate identical keys. Here, `customerProfiles` and a lookup-specific factory keep the scope clear.

### 7.2. A Safe Cache Key Alone Does Not Prevent Cross-Tenant Access

If a cache key omits or fails to bind the tenant, two tenants sharing a customer ID can collide. If authorization runs only **inside the `@Cacheable` method**, on a cache hit Spring **skips invoking the method** and bypasses that check.

Therefore:

- Enforce authorization in a layer invoked before cache interception returns data, such as a service facade/security boundary or properly ordered method security.
- Use verified tenant identities, never trusting arbitrary client-sent headers.
- Include the tenant in key derivation.
- Test cross-tenant access on both cache hits and cache misses.
- Never treat an opaque key as an authorization mechanism.

## 8. Key Names Surface in Many Subtle Places

Even if the service never logs keys, a key carrying PII can still leak through:

### 8.1. Keyspace Notifications

Example Redis expired keyevent:

```text
Channel: __keyevent@0__:expired
Message: session:alice@example.org
```

The message body contains the expired key name. Any authorized subscriber receives the full key string, not just its prefix. Turning off logging in the main app does not eliminate exposure if keyspace notifications are enabled for another application.

### 8.2. SCAN, KEYS, and Redis Insight / Admin Tooling

```redis
SCAN 0 MATCH customer:* COUNT 100
```

Output reveals full key patterns. Never embed emails, phone numbers, tokens, or passwords in key names even if the app only reads one exact key at a time.

`SCAN` avoids some blocking issues of `KEYS` on large datasets, yet **provides zero security isolation**; any sufficiently privileged user can inspect matching key names.

### 8.3. Redis Cluster Hash Tags

Example:

```text
profile:{alice@example.org}:data
profile:{alice@example.org}:settings
```

The hash tag places both keys in the same slot, yet also embeds the email in the key. A less exposed choice uses an HMAC digest or opaque group identifier matching your partitioning design:

```text
profile:{hmac-opaque-identifier}:data
profile:{hmac-opaque-identifier}:settings
```

Never lump all keys under one global hash tag like `{all}` just to hide data; that creates a single-slot hotspot in Redis Cluster.

### 8.4. Redis Command Arguments and URIs

When a Redis client sends `GET key`, the key name travels as a Redis command argument. Anyone authorized to capture commands via debugging tools sees the key at the operational layer regardless of application log redaction.

Lesson: **mask at the data structure level**, not only when formatting logs.

## 9. Minimize Data in Redis Values Before Reaching for Encryption

Storing entire Java entities as JSON is convenient, yet a cached endpoint may need only two fields.

Example object:

```json
{
  "customerId": "c-42",
  "displayName": "A. Nguyen",
  "email": "alice@example.org",
  "phone": "+84000000000",
  "address": "...",
  "accountSecret": "REDACTED_EXAMPLE",
  "marketingSegment": "standard"
}
```

If an endpoint needs only `displayName` and `marketingSegment`, caching `accountSecret` and `address` enlarges the attack surface for zero benefit.

A safer design is a **DTO projection**:

```java
public record CustomerCardCacheValue(
        String displayName,
        String marketingSegment,
        long profileVersion
) {}
```

Cache only fields permitted and required to serve the request. Keep the full record in storage with stricter access controls, retention, and encryption.

### 9.1. `@JsonIgnore` Is Not a General Security Policy

`@JsonIgnore` excludes a field along a Jackson JSON serialization path, yet:

- Other serializers may ignore that annotation.
- Repository Redis Hash mapping does not necessarily follow the same Jackson path.
- `toString()` logging may still print the field.
- Another code path may write raw String payloads directly.
- Tracing may capture raw arguments independently.
- An uncached object can still land in Streams or DLQs.

Define a **dedicated cache DTO type**, backed by tests verifying serialized fields, instead of trusting one annotation to plug every leak.

### 9.2. TTL Does Not Erase Every Copy

`EXPIRE` or `@TimeToLive` removes keys from live Redis after expiration, yet data may still live in:

- Replicas that received the write beforehand.
- RDB/AOF files or snapshots/backups within their retention window.
- Logs, traces, or support systems.
- DLQs, event archives, or duplicate Redis keys.
- Crash dumps or diagnostic captures collected earlier.

TTLs help **shrink lifetime on live Redis**; they do not execute system-wide deletion across every copy. Retention policies must cover all relevant copies.

## 10. Encrypting Redis Values: Distinguish TLS from Application Encryption

Three frequently confused mechanisms:

| Mechanism | Protects | Does Not Protect |
|---|---|---|
| TLS between Spring and Redis | Data in transit | Anyone authorized to read plaintext at Redis/client |
| Infrastructure encryption at rest | Data on storage media/snapshots per provider scope | Redis command readers, process memory, many ops tools |
| Application-level encryption before `SET` | Value contents when Redis readers lack the decryption key | Key names, metadata, payload size/frequency, pre-encryption data in app |

When security requirements state that **users with Redis read access must not see plaintext PII**, application-level encryption before storing can be an appropriate layer. By itself, it cannot solve access control or key-name leakage.

### 10.1. AEAD Instead of Unauthenticated Encryption

When encrypting payloads, protect both **confidentiality and integrity**. A standard choice in Java is `AES/GCM/NoPadding`:

- Use an AES key with sufficient entropy stored in a secret manager/KMS.
- Generate a **fresh nonce/IV** per encryption using a CSPRNG.
- Never reuse a nonce with the same key.
- Use an integrity tag, typically 128 bits.
- Bind *Additional Authenticated Data (AAD)* such as the controlled key name or tenant context to prevent moving ciphertext across contexts.
- Record format/version and manage key rotation.

**Never use AES/ECB**, never invent custom crypto, never reuse fixed IVs, and never embed AES keys in source code.

## 11. Java Example: Encrypting String Values with AES-GCM

This example primarily illustrates a versioned payload format with random nonces and AAD. Production also requires KMS/key-version management, size bounds, rotation/error handling, and security review.

```java
package com.example.security.redis;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Base64;

import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public final class RedisValueProtector {

    private static final int FORMAT_VERSION = 1;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    private final SecretKeySpec encryptionKey;
    private final SecureRandom random = new SecureRandom();

    public RedisValueProtector(
            @Value("${app.redis.values.aes-key-base64}")
            String base64Key) {

        byte[] keyBytes = Base64.getDecoder().decode(base64Key);

        if (keyBytes.length != 32) {
            throw new IllegalArgumentException(
                    "Expected 256-bit AES key"
            );
        }

        this.encryptionKey =
                new SecretKeySpec(keyBytes, "AES");
    }

    public String encrypt(String redisKey, String plaintext) {
        try {
            byte[] nonce = new byte[NONCE_BYTES];
            random.nextBytes(nonce);

            Cipher cipher =
                    Cipher.getInstance("AES/GCM/NoPadding");

            cipher.init(
                    Cipher.ENCRYPT_MODE,
                    encryptionKey,
                    new GCMParameterSpec(TAG_BITS, nonce)
            );

            // Bind the ciphertext strictly to the intended Redis key.
            cipher.updateAAD(
                    redisKey.getBytes(StandardCharsets.UTF_8)
            );

            byte[] ciphertext = cipher.doFinal(
                    plaintext.getBytes(StandardCharsets.UTF_8)
            );

            ByteBuffer payload = ByteBuffer.allocate(
                    1 + NONCE_BYTES + ciphertext.length
            );

            payload.put((byte) FORMAT_VERSION);
            payload.put(nonce);
            payload.put(ciphertext);

            return Base64.getEncoder()
                    .encodeToString(payload.array());

        } catch (GeneralSecurityException ex) {
            // Never log plaintext, secrets, or raw payloads.
            throw new IllegalStateException(
                    "Redis value encryption failed"
            );
        }
    }

    public String decrypt(String redisKey, String encoded) {
        try {
            byte[] bytes = Base64.getDecoder()
                    .decode(encoded);

            if (bytes.length < 1 + NONCE_BYTES + TAG_BITS / 8) {
                throw new IllegalArgumentException(
                        "Invalid encrypted payload"
                );
            }

            ByteBuffer payload = ByteBuffer.wrap(bytes);
            int version = Byte.toUnsignedInt(payload.get());

            if (version != FORMAT_VERSION) {
                throw new IllegalArgumentException(
                        "Unsupported encrypted payload version"
                );
            }

            byte[] nonce = new byte[NONCE_BYTES];
            payload.get(nonce);

            byte[] ciphertext = new byte[payload.remaining()];
            payload.get(ciphertext);

            Cipher cipher =
                    Cipher.getInstance("AES/GCM/NoPadding");

            cipher.init(
                    Cipher.DECRYPT_MODE,
                    encryptionKey,
                    new GCMParameterSpec(TAG_BITS, nonce)
            );

            cipher.updateAAD(
                    redisKey.getBytes(StandardCharsets.UTF_8)
            );

            byte[] plaintext = cipher.doFinal(ciphertext);

            return new String(
                    plaintext, StandardCharsets.UTF_8);

        } catch (GeneralSecurityException
                 | IllegalArgumentException ex) {
            // Never return errors leaking ciphertext, keys, or PII.
            throw new IllegalStateException(
                    "Cannot read encrypted Redis value"
            );
        }
    }
}
```

Example usage:

```java
String key = privateRedisKeyFactory
        .customerProfileKey(tenantId, customerId);

String encryptedValue =
        redisValueProtector.encrypt(key, jsonPayload);

stringRedisTemplate.opsForValue()
        .set(key, encryptedValue, Duration.ofMinutes(10));

String stored = stringRedisTemplate.opsForValue().get(key);

if (stored != null) {
    String json = redisValueProtector.decrypt(key, stored);
    // Deserialize and consume only along authorized code paths.
}
```

**Implementation notes:**

- Never place AES or HMAC keys inside a committed `application.yml`; configure property keys referencing platform-injected secrets.
- Random 96-bit AES-GCM nonces fit many workloads, yet evaluate per-key encryption volume limits and rotation policies under high traffic.
- Because `redisKey` serves as AAD, renaming or copying ciphertext to another key intentionally breaks decryption. Migrations must decrypt and re-encrypt under the new context.
- The version byte here is a **format version**, not a key ID for rotation. Production normally needs a key ID/version and backward-compatible decryption during rotation.
- Plaintext Java `String` inputs sit in JVM memory; pre-Redis encryption does not stop heap dumps or pre-encryption logging leaks.
- Encrypting entire values prevents Redis from running `INCR`, `HINCRBY`, or plaintext queries/filters directly. Choose data models accordingly.

Never copy crypto samples directly into production without threat modeling, key management, and security review. Prefer organization-approved cryptography libraries and patterns when available.

## 12. When to Encrypt Whole Payloads, Individual Fields, or Store Nothing?

| Need | Approach | Trade-Off |
|---|---|---|
| Public pricing, public product catalog | No per-value encryption needed just for Redis; still use TLS/ACLs | Low overhead; readable to authorized Redis users |
| Profile cache with PII needing only 2 fields | Minimal DTO + HMAC key | Shrinks exposure more cleanly than full-entity encryption |
| Cache holding strictly confidential fields | Field-level or whole-value AEAD | Key management, higher CPU/bytes |
| Need Redis `INCR`/`HINCRBY` on values | Keep counters non-sensitive or compute in an appropriate layer | Cannot perform arithmetic directly on AES-GCM ciphertext |
| Need lookup by email | Dedicated token/HMAC index at domain boundary | Equality/frequency leakage, rotation, index consistency |
| Need full-text search on private data | Use a search system with an appropriate security model | Whole-value encryption blocks Redis search |
| Tokens/passwords not needing recovery | Store purpose-built fingerprint/hash | Irreversible, which is usually desired |
| Data that does not need caching | Do not store in Redis | Completely eliminates Redis exposure surface |

**If you do not need to store it, do not encrypt it and store it anyway.** Data minimization is always a powerful risk reducer.

### 12.1. Passwords and Tokens Differ from Recoverable Data

User passwords should use a dedicated password hashing scheme (Argon2id/bcrypt/scrypt per system policy), never reversible encryption. Random tokens can often be verified via hashes/HMACs depending on threat model and token entropy.

For bearer credentials like refresh or access tokens, embedding raw tokens in Redis keys, logs, or traces is especially hazardous. Protections must consider replay risk, lifetimes, rotation, and revocation.

### 12.2. Compression Is Not Encryption

`GZIP`, `LZ4`, and similar compressors only shrink payload size. Anyone with the bytes can decompress them. Base64 and Java serialization likewise **do not** hide information. Never treat "unreadable text in `redis-cli`" as proof of data confidentiality.

## 13. RedisCacheManager, Serializers, and What Actually Gets Stored

Spring Boot auto-configures `RedisCacheManager` and `RedisTemplate` with various serializers. A cached Java object may be:

- Serialized as JSON with readable field names.
- Serialized into a binary format unreadable by eye yet trivially decodable.
- Embedded with type metadata, class names, or extra domain details.
- Accompanied by auxiliary keys from framework indexing or TTL mechanics.

### 13.1. Never Assume a Serializer Hides Data

Example:

```java
@Cacheable(cacheNames = "customerProfile")
public CustomerProfile findProfile(String customerId) {
    return repository.findById(customerId);
}
```

If `CustomerProfile` contains phone and address, Redis stores them per the serializer. Java serialization, JDK binary, or JSON are not encryption.

To cache safely, return a **projection DTO** from the cached method. When encryption is required, wire a designed and tested protecting serializer into `RedisCacheConfiguration`.

### 13.2. Null Values, Exceptions, and Negative Caching

A service may cache a marker indicating a missing customer. Markers must not embed raw inputs either:

```text
customerNotFound:alice@example.org
```

Use an opaque key and a non-PII marker value. Negative caching needs short TTLs aligned with source-of-truth semantics; otherwise a newly created user continues receiving stale "not found" results.

Exception messages containing search queries or user inputs must never be cached or logged verbatim without control.

## 14. Redis Repositories and Easily Overlooked Auxiliary Keys

Spring Data Redis Repositories using `@RedisHash`, `@Indexed`, and `@TimeToLive` create extra Redis keys and auxiliary structures to maintain mappings and indexes.

Example entity:

```java
@RedisHash("customer")
public class CustomerEntity {
    @Id
    private String id;

    @Indexed
    private String email;
}
```

Index sets/keys can contain the **raw email value** inside index structures depending on framework/version. Thus, HMAC-hashing only the primary ID while keeping `@Indexed email` can still leak the email in secondary indexes.

Audit:

1. Primary entity keys created by the Repository.
2. Auxiliary keys and Sets created by indexed fields.
3. Phantom/shadow copies tied to TTLs.
4. Keyspace notifications and expired events carrying IDs or objects.
5. Serializers for Hash fields and values.
6. Cleanup/rebuild mechanisms when expiry notifications are missed.

If lookup by email is required without storing raw emails in keys or indexes, store a **deterministic HMAC lookup token** in a dedicated index field while keeping the real email protected appropriately.

### 14.1. Equality Leakage of Deterministic Tokens

If the same email always yields the same HMAC token:

- Index viewers can spot records sharing the same token.
- Access frequency or correlations may be observed.
- Anyone holding the secret and input space can match values.
- Secret rotation requires index rebuilding or migration.

Never describe a deterministic HMAC index as complete anonymization.

## 15. Safe Logging: Use Allowlists Instead of Trying to Scrub Every String

Logging is often the fastest leak path because logs from many services aggregate into one central store with long retention.

### 15.1. Log Statements to Avoid

```java
log.debug("Redis GET key={}", redisKey);

log.info("Customer cache value: {}", customerProfile);

log.warn("Invalid input {}", requestBody);

log.error("Redis failed for email={} value={}",
        email, jsonPayload, exception);

log.trace("Redis connection {}", redisUri);

log.info("Received Stream event: {}", record.getValue());
```

Why these are dangerous:

- `redisKey` may contain emails or tokens.
- `CustomerProfile.toString()` can print all fields.
- Request bodies can hold passwords or OTPs.
- `exception.getMessage()` or stack traces can contain command arguments or URIs depending on the library.
- Redis URIs can contain credentials.
- Stream event bodies can hold PII or financial data.

Never assume enabling `DEBUG`/`TRACE` "just briefly" is safe: records may already have shipped to a long-retention backend.

### 15.2. Log Standardized Event Types and States

Safer example:

```java
package com.example.customer;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class CustomerCacheObserver {

    private static final Logger log =
            LoggerFactory.getLogger(CustomerCacheObserver.class);

    public void cacheHit() {
        log.debug(
                "redis_cache_lookup cache={} result={}",
                "customerProfile",
                "hit"
        );
    }

    public void cacheMiss() {
        log.debug(
                "redis_cache_lookup cache={} result={}",
                "customerProfile",
                "miss"
        );
    }

    public void cacheFailure(RuntimeException failure) {
        // Never log keys, values, or exception messages
        // to a log channel not authorized for sensitive data.
        log.warn(
                "redis_cache_lookup_failed cache={} exceptionType={}",
                "customerProfile",
                failure.getClass().getSimpleName()
        );
    }
}
```

This example is not meant to ban all stack traces: full exception logs may be needed on a restricted diagnostic channel after verifying whether frameworks/drivers put sensitive data inside throwables. On broadly shared log channels, prefer **event codes, outcomes, latency, and exception class names** over raw arguments.

### 15.3. Source-Level Redaction Beats Post-Hoc Regex Scrubbing

A log collector might apply regexes to replace emails or phone numbers with `[REDACTED]`. That approach has clear gaps:

- Fails to catch every data format or secret type.
- Data still travels through agents/files before scrubbing runs.
- Another field may carry the exact same payload unscrubbed.
- Exception stacks, object formatters, or nested JSON can evade patterns.
- Internal hashes, tokens, and IDs rarely follow easy regex patterns.
- Schema changes cause old filters to miss new fields.

A safer approach is **allowlisting logged fields right in the application**:

```text
Allow: eventType, cacheName, commandType, outcome,
       durationMs, service, environment, requestCorrelationId.

Do not log by default: Redis key, value, request body,
                       access token, email, phone, query text,
                       unvetted exception messages.
```

Collector-side filters remain valuable as a **second line of defense**, never a substitute for clean source design.

## 16. Structured Logging and Correlation IDs

Structured logs often use JSON:

```json
{
  "event": "redis_cache_lookup",
  "cache": "customerProfile",
  "result": "miss",
  "duration_ms": 12,
  "trace_id": "generated-trace-id"
}
```

This avoids embedding emails or Redis keys into messages. For request troubleshooting, attach a correlation ID that does not directly expose PII.

### 16.1. Never Use Emails or Bearer Tokens as Correlation IDs

Wrong:

```text
correlationId = request.getHeader("Authorization")
correlationId = customer.email()
traceId = user.phoneNumber()
```

Better:

- Use a randomly generated tracer ID.
- Use a request ID generated by the app or a trusted gateway per policy.
- Validate format and length if accepting IDs from external headers.
- Never let clients inject unvalidated strings with newlines or JSON into log fields.

If a client sends an arbitrary `X-Request-ID`, constrain its length and character set or replace it with an internal ID. A client-supplied "opaque ID" can still smuggle PII if unvalidated.

### 16.2. MDC Must Have Proper Lifecycle Management

`MDC` attaches trace/request correlation to logs:

```java
try (var ignored = org.slf4j.MDC.putCloseable(
        "operation", "customerProfileLookup")) {
    log.info("redis_cache_lookup result={}", "hit");
}
```

Thread-bound MDC can **leak context across requests** in thread pools if not cleaned up properly. In async/reactive pipelines, use framework-supported context propagation rather than assuming `ThreadLocal` tracks the request.

Never put emails, tokens, session IDs, or full security principals into MDC, because every log line emitted on that thread can inherit them.

## 17. Redis Drivers, Exceptions, and Driver Log Levels

Spring Data Redis commonly uses Lettuce or Jedis. Even if application logs omit keys, drivers and frameworks have their own configurable log levels.

### 17.1. Be Careful Enabling TRACE/DEBUG for Investigations

Normal operations may keep driver logs at WARN:

```yaml
logging:
  level:
    io.lettuce.core: WARN
    org.springframework.data.redis: WARN
```

This is an **example of lowering verbosity**, not a complete security control. Whether a given driver/version logs raw command arguments must be verified for your exact configuration and version.

When enabling DEBUG/TRACE:

- Require a short time limit and owner approval.
- Prefer a test environment with synthetic data when possible.
- Inspect log samples before turning it on in production.
- Restrict viewers and retention.
- Disable debug logging once diagnosis finishes.
- Never embed credentials in connection URLs or command lines.

**Transport encryption does not stop an application from logging data before sending it.**

### 17.2. Exceptions Can Carry Sensitive Context

Code like:

```java
log.error("Failed to write {}", redisKey, ex);
```

directly leaks the key. Yet even:

```java
log.error("Redis request failed", ex);
```

needs inspection because throwable messages can include endpoints, commands, or URIs depending on the error/driver.

Do not suppress error details to the point of making operations blind. Instead:

1. Classify errors and assign safe error codes.
2. Emit only allowlisted fields on standard log channels.
3. When stack traces are required, route them to restricted diagnostic channels with redaction and access controls.
4. Never put secrets or PII into application-created exception messages.
5. Attach a trace ID to correlate context without logging raw payloads.

### 17.3. Logging a Redis URI Can Leak the Password

Example connection URI:

```text
redis://username:password@redis.internal:6379
```

If logged, the password leaks immediately. Prefer Spring Boot property binding with secret injection, and never print full configuration objects or environments.

`spring.data.redis.password` must come from a secret source and never appear in custom status endpoints. Even though Spring Boot Actuator sanitizes certain properties, **never assume every endpoint, custom actuator, or log automatically strips all secrets**.

## 18. Redis MONITOR and SLOWLOG Are Sensitive Diagnostic Channels

### 18.1. MONITOR

`MONITOR` lets an authorized client stream commands processed by the Redis server for debugging. Because command arguments contain keys and values, it is a major exposure surface.

Example application command:

```redis
SET session:alice@example.org "token-or-json-payload"
```

Command-monitoring tools can observe command data depending on Redis version and server-side redaction/filtering features. **Never assume Redis command filtering hides all business keys and values.**

Use `MONITOR` strictly per runbook, in authorized environments, for brief windows, with minimal admin access and synthetic data when possible. It also carries performance overhead; never leave it running continuously as primary monitoring.

### 18.2. SLOWLOG

`SLOWLOG` records slow commands exceeding server thresholds along with their arguments, subject to Redis truncation limits. Keys containing PII can appear in slowlog entries.

`SLOWLOG` measures server-side execution time rather than full application RTT, and **truncation is not data masking**. An argument truncated to 128 bytes can still hold a complete email address or token.

When shipping slowlogs to centralized logging:

- Restrict read access to slowlogs.
- Minimize sensitive data in keys and values at the application layer.
- Review export and redaction pipelines.
- Set tight retention limits.
- Keep raw arguments off broadly accessible dashboards.

### 18.3. INFO, CLIENT LIST, and Diagnostic Endpoints

Some admin commands reveal connection metadata, client IPs, client names, or topology info. Naming a client with PII such as `clientName=alice@example.org` is inappropriate.

Client names should identify services and instances—such as `catalog-service-pod-a3`—never emails or access tokens.

## 19. Tracing: Spans Can Expose Redis Keys and Payloads

Distributed tracing follows requests across HTTP services, databases, Redis, and brokers. Spans may capture:

- `db.system`, `db.operation.name`, Redis command type.
- Statements or command arguments depending on instrumentation.
- Custom application span names.
- Error statuses, exception messages, and stack traces.
- Captured HTTP request parameters or headers.
- Baggage or custom attributes propagated across services.
- Messaging payload attributes if attached manually.

Risky example:

```java
Span.current().setAttribute(
        "redis.key", "profile:" + email);

Span.current().setAttribute(
        "redis.value", jsonPayload);
```

Once exported to the tracing backend, that data persists outside both Redis and log stores.

### 19.1. Allowlisted Span Metadata

A safer span describes the **operation category**, not sensitive subjects:

```text
name: redis.customer-profile.lookup
attributes:
  db.system.name: redis
  db.operation.name: GET
  cache.name: customerProfile
  cache.result: miss
  service.name: customer-service
  app.tenant.tier: enterprise
```

Never add `customer.email`, `session.token`, full Redis keys, or raw JSON as span attributes. Even tenant IDs should be classified before using them as attributes.

### 19.2. Safe Micrometer Observation Example

```java
package com.example.customer;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class CustomerCacheMetrics {

    private final ObservationRegistry registry;

    public CustomerCacheMetrics(
            ObservationRegistry registry) {
        this.registry = registry;
    }

    public <T> T observeLookup(
            java.util.function.Supplier<T> action) {

        return Observation.createNotStarted(
                        "redis.customer.profile.lookup",
                        registry)
                .lowCardinalityKeyValue(
                        "cache.name", "customerProfile")
                .lowCardinalityKeyValue(
                        "operation", "lookup")
                .observe(action::get);
    }
}
```

Usage:

```java
CustomerProfile result = customerCacheMetrics.observeLookup(
        () -> customerProfileService.find(tenantId, customerId)
);
```

This observation records the operation name and allowlisted metadata without adding customer IDs to the span. Still, other instrumentations may attach attributes automatically; audit the entire observability pipeline end-to-end.

### 19.3. Baggage and MDC Propagate Across Services

Baggage travels across service hops. Never store emails, tokens, or customer records in baggage for "easier debugging," as it propagates downstream and can be logged or traced by other services.

Use trace IDs, request IDs, or safe opaque operation references. Audit propagated headers and where tracing exporters store data.

### 19.4. Sampling Is Not Redaction

1% sampling shrinks stored trace volume, yet **the 1% sampled traces still hold intact secrets**. Every emitted span must comply with policy prior to sampling.

## 20. Micrometer Metrics and Cardinality: Never Use Keys or IDs as Tags

A common mistake:

```java
Counter.builder("redis.cache.miss")
        .tag("customerId", customerId)
        .tag("redisKey", redisKey)
        .register(meterRegistry)
        .increment();
```

With one million customers, you create one million label combinations. Besides exposing identifiers, this spikes memory/storage overhead and destabilizes metrics backends.

A better approach:

```java
Counter.builder("redis.cache.miss")
        .tag("cache", "customerProfile")
        .tag("service", "customer-service")
        .register(meterRegistry)
        .increment();
```

Appropriate **low-cardinality labels**:

- Predefined cache group names.
- Redis command types (`GET`/`SET`/`MGET`...).
- Outcomes (`hit`/`miss`/`error`).
- Environment and service.
- Normalized error categories.
- Approved tenant **tiers** or segments rather than raw tenant IDs.

**High-cardinality/sensitive labels** to avoid:

- Full Redis keys.
- Customer/user/session/order IDs.
- Emails, phone numbers, tokens.
- Query strings.
- Request/trace IDs as global metric tags.
- Payload hashes if linkable to individual users.

Note: even an HMAC digest without plaintext creates high cardinality and enables individual tracking, so it is **not automatically safe as a metric tag**.

## 21. Streams, Pub/Sub, Keyspace Notifications, and DLQs Also Need Masking

Redis holds more than cache values.

### 21.1. Redis Streams

A Stream event:

```redis
XADD events:orders * eventId evt-42 email alice@example.org type CREATED
```

stores the email directly in entry fields. Consumers, admin tooling, `XRANGE`, and backups can read the payload. When failed events move to a dead-letter stream, data is **duplicated** further.

If downstream consumers only need an order ID, publish:

```redis
XADD events:orders * eventId evt-42 orderRef order-42 type CREATED
```

and let authorized consumers fetch needed details from the durable data source.

When events genuinely must carry PII, enforce matching schemas, retention, ACLs, encryption, and consumer privileges. Never dump raw payloads into `log.error("failed message {}", record)` when handlers fail.

### 21.2. Pub/Sub

Pub/Sub stores no replay history, yet authorized active subscribers read message bodies live. A channel:

```text
notify:customer:alice@example.org
```

leaks the email in the channel name. Replace with event-type channels:

```text
notify:customer-updated
```

and send opaque references or safely designed payloads. Channel ACLs restrict subscriber groups, yet **do not replace data minimization**.

### 21.3. Keyspace Notifications

With `notify-keyspace-events` enabled, expired/deleted events carry key names. If keys contain emails or tokens, subscribing to `__keyevent@0__:expired` turns into a PII broadcast feed.

Therefore:

- Design safe keys **before** enabling keyspace notifications.
- Restrict `SUBSCRIBE` ACLs by channel pattern.
- Never log all event bodies by default.
- Accept that Pub/Sub events can drop while listeners are offline; never rely on them for mandatory sensitive work without a durable source.

### 21.4. DLQs and Retry Payloads

DLQs typically retain failed messages longer than normal streams for troubleshooting. If a DLQ copies raw requests containing secrets, it holds them longer with broader readership.

Prefer storing:

- Event ID / correlation ID.
- Event type and schema version.
- Error category / attempt count.
- Opaque reference to the payload in properly secured/retained storage.
- Minimal context needed for replay.

If full payloads must enter a DLQ, enforce encryption, access controls, tight retention, and clear deletion procedures.

## 22. TLS, Redis ACLs, and Network Isolation Protect Access—Not Data Masking

An application might configure Redis TLS as:

```yaml
spring:
  data:
    redis:
      ssl:
        enabled: true
      username: customer-cache-service
      password: ${REDIS_PASSWORD}
```

This is a modern Spring Boot example; prefixes and TLS properties vary by version. Secrets should come from a secret manager or controlled environment variables, never stored literally in Git.

### 22.1. TLS

TLS protects data **in transit** between the application and Redis along configured links. It does not make keys or values unreadable to the Redis server or authorized clients.

Never disable certificate or hostname checks just to get deployments passing. For Redis Sentinel/Cluster, secure TLS across all relevant links per provider topology.

### 22.2. ACL

Redis ACLs restrict which commands, key patterns, and Pub/Sub channels a user can access per Redis version capabilities.

For example, a customer-cache user does not need:

- `CONFIG SET`, `FLUSHALL`, or server-wide admin commands.
- `MONITOR`.
- Read access to other services' keys.
- Subscriptions to arbitrary channels.
- Read/write access to unrelated secret namespaces.

ACLs must match the real commands used by Spring Cache/Template/Repositories; granting only `GET` breaks if the framework issues `MGET`, `SET`, `DEL`, `SCAN`, or Lua.

### 22.3. What Does Application-Layer Encryption Add?

When values must stay hidden even from users with Redis read privileges, application-level encryption helps. It adds key-management complexity and stops Redis from executing direct operations on encrypted values.

Never assume a deployment with "TLS and ACLs enabled" is safe while developers log raw tokens at the HTTP layer.

## 23. RDB, AOF, Replicas, and Backups Extend Data Lifetimes

Redis may use RDB snapshots, Append Only Files (AOF), replication, and external backups. Whenever keys or values contain sensitive data, those persistence layers capture copies too.

### 23.1. Consequences After Key Deletion

Suppose the app runs:

```redis
DEL customer:profile:v1:<opaque-id>
```

Live Redis no longer holds the entry, yet:

- An earlier RDB snapshot still contains the data.
- AOF logs or backups preserve historical commands and state.
- Replicas and secondary snapshots may retain copies.
- Application/driver logs and traces may have copied keys and values.
- Monitoring exports or support tickets may hold excerpts.

You need a **data retention/deletion policy** spanning all of those places—not just `DEL` in Redis. Never claim "every copy is permanently erased" simply because Redis `GET` returns nil.

### 23.2. Safeguards

- Encryption at rest for storage and snapshots where supported by the provider.
- Backup encryption keys stored in an appropriate secret management system.
- Strictly limited read access to backups, with access auditing.
- Snapshot/backup and log retention windows aligned with policy.
- Approved workflows to purge or expire old copies.
- Collect heap/crash dumps only when needed and store them in restricted locations.
- Test restoring encrypted payloads across key rotations: **losing a decryption key can render backups unusable**.

Never encrypt values while leaving raw emails in key names, or encrypt backups while exporting plaintext AOF/logs into another environment.

## 24. Designing Diagnosable Redis Error Logs Without Leaks

A practical need: when Redis times out, operators need to know which endpoint failed, which command, how long it took, failure rates, and related trace IDs—without needing emails or tokens from keys.

A structured event:

```json
{
  "event": "redis_operation_failed",
  "service": "customer-service",
  "operation": "GET",
  "cache": "customerProfile",
  "errorCategory": "TIMEOUT",
  "elapsedMs": 3000,
  "traceId": "opaque-trace-id"
}
```

Fields not needed:

```json
{
  "email": "alice@example.org",
  "redisKey": "profile:alice@example.org",
  "redisValue": "full-customer-json",
  "authorization": "Bearer example"
}
```

### 24.1. Spring CacheErrorHandler and Key Handling

A custom `CacheErrorHandler` receives the raw key object:

```java
@Override
public void handleCacheGetError(
        RuntimeException exception,
        Cache cache,
        Object key) {
    // DO NOT: log.warn("Cache GET failed key={}", key, exception);

    log.warn(
            "Cache GET failed cache={} errorType={}",
            cache.getName(),
            exception.getClass().getSimpleName()
    );

    // Deciding whether to throw or fail-open must follow
    // business contracts and cache architecture.
}
```

This illustrates **log redaction only**, not a full `CacheErrorHandler` implementation. Real handlers must cover GET/PUT/EVICT/CLEAR error methods per your Spring version.

If Redis is an optional cache, failing open may fit; if Redis stores authoritative state, swallowing errors as misses breaks **correctness**. Safe logging does not mean ignoring exceptions.

### 24.2. Error Categorization

A clean set of error categories:

```text
CONNECT_TIMEOUT
COMMAND_TIMEOUT
AUTHENTICATION
PERMISSION
SERIALIZATION
WRONGTYPE
UNAVAILABLE
UNKNOWN_REDIS_ERROR
```

These work safely as metric tags or log fields without PII. Avoid putting `exception.getMessage()` into labels, as messages vary unboundedly and can leak sensitive contents.

## 25. Testing Against Leaks: Keys, Values, Logs, and Traces

Security tests must use **synthetic sensitive values**, never real tokens or real customer data.

### 25.1. Unit Test for Key Derivation

```java
package com.example.security.redis;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Base64;

import org.junit.jupiter.api.Test;

class PrivateRedisKeyFactoryTest {

    @Test
    void derivedKeyDoesNotContainRawIdentity() {
        String fakeSecret = Base64.getEncoder()
                .encodeToString(new byte[32]);

        PrivateRedisKeyFactory factory =
                new PrivateRedisKeyFactory(fakeSecret);

        String email = "alice@example.org";

        String first = factory.customerProfileKey(
                "test-tenant", email);

        String second = factory.customerProfileKey(
                "test-tenant", email);

        String other = factory.customerProfileKey(
                "other-tenant", email);

        assertThat(first)
                .startsWith("customer:profile:v2:")
                .doesNotContain(email);

        assertThat(first).isEqualTo(second);
        assertThat(first).isNotEqualTo(other);
    }
}
```

This unit test demonstrates deterministic key derivation—it **does not** prove production secret entropy. Zero-filled byte arrays are public test fixtures only, never real security keys.

### 25.2. Integration Testing Redis Keyspace with Synthetic Data

Using Testcontainers + `StringRedisTemplate`:

1. Derive HMAC keys from a synthetic tenant and synthetic email.
2. Write permitted cache data.
3. Run `SCAN` in the test namespace to confirm key names omit the fake email/phone/token.
4. Read values with test permissions/serializers and confirm excluded fields are absent.
5. Delete test keys in `finally`.
6. Never run `KEYS *` in production; this scan runs strictly in an isolated test environment.

Integration tests should also inspect the full Spring Cache prefix—not just the key factory output—since `customerProfiles::<safe-key>` is the real Redis key written by `CacheManager`.

### 25.3. Testing Logs with CapturedOutput

Spring Boot Test provides `OutputCaptureExtension` to inspect logging/stdout output in tests:

```java
package com.example.customer;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

@ExtendWith(OutputCaptureExtension.class)
class SafeCacheLogTest {

    private final CustomerCacheObserver observer =
            new CustomerCacheObserver();

    @Test
    void shouldNotPrintSensitiveIdentity(
            CapturedOutput output) {

        String syntheticEmail = "secret-fixture@example.org";

        // Use synthetic data in tests; the observer logs
        // only allowlisted metadata.
        observer.cacheMiss();

        assertThat(output.getAll())
                .doesNotContain(syntheticEmail)
                .doesNotContain("Authorization")
                .doesNotContain("Bearer ");
    }
}
```

Ensure test log levels actually capture the events under test. Calling a method that does not even receive an email is a **minimal sanity check**, not coverage of full service/driver/error paths. To catch real leaks, invoke full paths with synthetic secrets, trigger cache misses, errors, and exceptions, and assert against captured output.

### 25.4. Tracing Tests

With an in-memory span exporter or test observation handler, assert:

- Span names belong to an approved list.
- Attributes contain only normalized command, cache, outcome, and latency fields.
- No emails, phones, tokens, or raw Redis keys appear.
- Exception events omit sensitive payloads.
- Baggage contains no secret headers.
- Sampling policy is not treated as redaction.

Exact APIs vary by Micrometer Tracing/OpenTelemetry version; tests should inspect **actually exported telemetry**, not just manual attribute-setting calls.

### 25.5. Secret Scanning and Synthetic Canaries

Place a distinctive synthetic canary token in test inputs:

```text
SYNTHETIC_SECRET_SHOULD_NOT_APPEAR_IN_LOGS
```

Run workflows through Redis, logs, metrics, and tracing test exporters, then scan for the canary string. This catches unexpected leak paths, though it **does not prove every PII class is eliminated**.

Never use production credentials as canaries.

## 26. Incident Response When Logs or Traces Contain Sensitive Data

Suppose a distributed trace is found carrying `redis.key="session:<raw-token>"`.

Distinguish **stopping ongoing leakage** from **remediating already copied data**.

An appropriate runbook:

1. **Triage severity:** what leaked, in which environment, and can it grant unauthorized access?
2. **Stop the leak source:** disable the attribute/debug flag, deploy safe key naming, or pause the feature depending on severity.
3. **Restrict viewer access:** lock down log/trace backends, dashboards, exporters, tickets, and shared links.
4. **Scope exposure:** time range, affected records, services, traces, and backups.
5. **Rotate/revoke secrets** if tokens, passwords, or API keys were exposed—never just mask UI views.
6. **Handle historical copies:** enforce retention/deletion per policy and backend capabilities.
7. **Assess notification duties** with security and legal teams under applicable obligations.
8. **Prevent recurrence:** allowlists, static/dynamic tests, code review checklists, and logging/tracing guardrails.

Technical note: a value already shipped to downstream logs or backups **cannot be treated as unexposed** just because code is patched or Redis keys expire.

## 27. Designing Security In from the Start

### Step 1: Build an Inventory

Document every Redis dataset:

```text
Dataset: customerProfile
Key pattern: customer:profile:v2:<HMAC>
Value: CustomerCardCacheValue (no email/phone)
TTL: 15 minutes
Source of truth: PostgreSQL
Logging: cacheName, outcome, duration; no key/value logged
Tracing: redis operation + cache category; no raw IDs
Metrics: cacheName, result, errorType
Backup: per Redis deployment policy
Access: service user scoped only to relevant namespace
```

### Step 2: Avoid Storing Unnecessary Data

Use small projections and strip secrets or sensitive attributes not directly required for fast reads.

### Step 3: Design Safe Keys

Use random IDs or keyed HMAC derivations. Ensure tenant scoping, canonicalization, schema versioning, and a rotation plan.

### Step 4: Choose Value Protections

Decide which plaintext fields are permitted, or apply field-level or whole-value encryption where warranted; keep key management separate from app code.

### Step 5: Configure ACLs, TLS, and Retention

Restrict clients by namespace/commands, protect networks and backups, set purposeful TTLs, and never equate TTL with deleting all copies.

### Step 6: Control Logs and Traces

Use allowlists for event codes, cache names, outcomes, latencies, and trace IDs. Never attach raw Redis keys, payloads, tokens, or emails/phones to spans, MDC, metric tags, or exception messages.

### Step 7: Test Leak Surfaces

Use synthetic secrets to inspect:

- Live Redis keyspace.
- Serialized cache values.
- Driver and application logs under production-like settings.
- Exported span attributes and events.
- Metric labels and cardinality.
- Stream, DLQ, and Pub/Sub messages.

### Step 8: Prepare Rollback, Migration, and Legacy Data Cleanup

When migrating from raw email keys to HMAC keys:

- You may need dual-read across old and new keys during transition.
- Stop writing old keys as soon as possible.
- Do not log old keys during migration.
- Enforce TTLs/cleanup on old keys per policy.
- Distinguish regenerable caches from data requiring mandatory migration.
- Coordinate scrubbing/remediation across logs, traces, and backups if required.

## 28. Common Mistakes

| Mistake | Risk | Better Practice |
|---|---|---|
| Using emails/phones in Redis keys | PII leaks via `SCAN`, keyevents, logs | Opaque or HMAC keys |
| Base64-encoding emails and calling it encrypted | Trivially decoded | Keyed HMAC or random identifiers |
| Unkeyed SHA-256 of emails | Dictionary attacks | Keyed HMAC when lookup is required |
| Using HMAC digests as metric labels | Linkability and high cardinality | Low-cardinality labels |
| Omitting tenant from key derivation | Cache collisions and cross-tenant leaks | Tenant-scoped keys and authorization |
| Encrypting payloads while keeping raw IDs in keys | PII leaks via metadata | Protect both keys and values |
| Treating GZIP/Java serialization as security | Plaintext remains readable to anyone decoding | Use AEAD when needed |
| Reusing fixed IVs/nonces for AES-GCM | Breaks encryption security | Unique nonce per encryption under a key |
| Caching full entities just to read two fields | Unnecessary data exposure | Cache DTO projections |
| `@Indexed email` in Repositories | Index keys/sets may expose raw emails | Purpose-built HMAC lookup/index |
| Logging `Object.toString()` | Prints sensitive fields | Log approved metadata only |
| Logging raw Redis URIs/exceptions | Credential/argument leaks | Secret config and safe error categories |
| Leaving driver `TRACE` on in production | Command arguments flood logs | Time-boxed, controlled debug procedures |
| Putting keys/values in span attributes | Leaks into tracing backends | Attribute allowlists |
| Putting `userId`/`traceId` on all metrics | High cardinality and privacy risk | Tag service, cache, and outcome |
| Relying on sampling to hide secrets | Sampled traces still carry intact secrets | Redact prior to export |
| Relying on TLS to protect logs | TLS does not protect plaintext app logs | Separate logging policies |
| Relying on Redis TTL to purge backups | Backups have independent retention | Cross-system data lifecycle |
| Writing raw Stream payloads to DLQs/logs | Replicates sensitive data | Opaque references or encrypted DLQs |
| Logging keys in `CacheErrorHandler` | Leaks PII whenever Redis errors | Omit raw keys and values |
| Sharing one HMAC secret across all uses | Hard rotation and no domain separation | Key separation and scoped derivation |
| Rotating HMAC secrets without migration | Cache misses or lost primary data | Key versioning and dual-read/migration |
| Using "hidden keys" instead of authorization | Redis readers can still read values | ACLs + application authorization |

## 29. Quick Decision Matrix

| Data | Redis Key | Redis Value | Logging/Tracing |
|---|---|---|---|
| Public product pricing | `product:price:<publicId>` | Price + version | Command type, cache name, duration |
| User profile | `customer:profile:v2:<HMAC>` | Minimal DTO, encrypted if needed | No email, phone, or key |
| Sessions/tokens | Opaque random ID or suitable HMAC | Minimize plaintext tokens, short TTL, tight access | No tokens or replayable session IDs |
| OTPs | Opaque lookup key | Hash/verification state per suitable scheme, TTL | Attempt outcome, error category |
| Payment Redis Stream | `events:payments` | Opaque event ref or protected payload | Event type, event ID per policy |
| HMAC lookup index | `customer:index:v1:<HMAC>` | Opaque record reference | Never use per-user digests as labels |
| Rate-limit counters | `rate-limit:v1:<opaque-id>` | Counter/TTL | Policy name, aggregate allow/deny |
| Search query cache | Hash/HMAC of canonical query when needed | Minimal results | No raw search queries |

Evaluate keys, values, and observability payloads under the **exact same data classification policy**. Never treat a field as confidential in the database yet public in Redis logs just because it is cached.

## 30. Conclusion

In Spring Data Redis, **protecting sensitive data goes far beyond setting a Redis password or enabling TLS**. Key names expose emails, phones, and tokens via command arguments, `SCAN`, and keyspace notifications; serialized values can carry full entities into replicas, RDB/AOF files, and backups; and logs and distributed traces can leak data outside Redis for months.

A sound strategy combines:

- **No raw PII or secrets in Redis key names.** Use opaque identifiers, keyed HMACs, and tenant scoping where appropriate.
- **No unnecessary fields stored.** Cache minimal DTOs; encrypt payloads with managed AEAD when required by the threat model.
- **Allowlist-based logging and tracing.** Retain only command categories, cache names, outcomes, durations, and safe correlation IDs; never log unvetted keys, values, tokens, or raw exception payloads.
- **Tight access and retention limits.** Redis ACLs, TLS, backup controls, retention windows, and monitoring permissions each cover different layers.
- **Pre-release leak testing.** Test Redis keyspaces, serializers, logs, traces, metrics, Streams/PubSub, and DLQs with synthetic data.
- **Rotation/migration and incident plans.** Raw keys already copied into logs or traces do not vanish when code changes key formats.

The most practical rule: **put as little identifying or credential-bearing data as possible into places that need only an identifier and an operational signal**. That shrinks risk at the source while preserving debugging clarity and Redis performance observability.

## References

- [Redis — Security](https://redis.io/docs/latest/operate/oss_and_stack/management/security/)
- [Redis — Access Control Lists](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/)
- [Redis — Encryption](https://redis.io/docs/latest/operate/oss_and_stack/management/security/encryption/)
- [Redis — MONITOR](https://redis.io/docs/latest/commands/monitor/)
- [Redis — SLOWLOG](https://redis.io/docs/latest/commands/slowlog/)
- [Redis — Keyspace notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)
- [Spring Data Redis — Redis cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Micrometer Observation — Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [OpenTelemetry — Semantic conventions](https://opentelemetry.io/docs/specs/semconv/)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
