# Hashing Identifying Data in Java Core Logging

## 1. Why Shouldn't You Log Raw Identifiers?

In Java applications, logs help connect actions of the same subject across multiple requests: a user, customer, account, device, session, or transaction. However, writing emails, phone numbers, ID document numbers, IP addresses, personally identifiable customer codes, or sensitive identifying keys directly into logs expands the data exposure surface whenever consoles, files, collectors, dashboards, or backups are accessed improperly.

**Hashing identifying data** in the context of logging means replacing the original identifier with a derived code (token) so that you can still **correlate log records** without storing the raw identifier directly. For guessable identifiers, the appropriate approach is usually **HMAC-SHA-256 with a secret key**, separated by purpose and scope, rather than simply calling `SHA-256(email)`.

~~~text
Not recommended:
  event=login_failed email=an@example.com phone=+84900000000

May be appropriate when correlating multiple logs within an authorized scope:
  event=login_failed userRef=v1_xxxxxxxxxxxxxxxxxxxxxx requestId=req-42

If you only need to track a single request:
  event=login_failed requestId=req-42
  (no need to add userRef)
~~~

`userRef` is an example of a pseudonymous identifier, **not proof that the data is completely anonymous**. Anyone authorized to cross-reference it—or anyone holding the HMAC key and a list of candidate IDs—can re-link it. Even without knowing the original ID, a stable token can still be used to track the behavior of the same subject over time.

**The first principle is data minimization**: if an investigation only needs `requestId`/`traceId` or an aggregate metric, **do not create a long-lived identifying token** just to fill out log fields. Never log passwords, private keys, OTP codes, or credentials in raw form or "just hashed once" for debugging; access tokens, session IDs, and other secrets also require strict exclusion policies.

## 2. How Do Hashing, HMAC, Encryption, Masking, and Tokenization Differ?

| Technique | How It Works | Can Same Input Be Linked? | Risks / Application in Logs |
| --- | --- | --- | --- |
| **Plain SHA-256** | `SHA256(identifier)`, no key | Yes, anywhere using the same algorithm and normalization | Easy to test candidate lists when email/phone/ID has a small space |
| **Hash with fixed public salt** | `SHA256(salt || identifier)` | Yes, if using the same salt | Does not resist dictionary attacks well once the salt is known; changing the salt can break joinability |
| **Hash with random salt per record** | Each event uses a different salt and stores the salt | Usually cannot compare records directly | Useful for other problems, but inconvenient for linking logs of the same user |
| **HMAC with secret key** | `HMAC-SHA256(secret, domain || identifier)` | Yes, within the same key + domain, if normalized consistently | Suitable for deterministic tokens; still a pseudonym, so the key must be protected |
| **Encryption** | Converts plaintext into ciphertext with a key | Depends on algorithm/mode | Can be decrypted by authorized parties; if decryption isn't needed, avoid using it just to route logs |
| **Masking** | Hides part of the value, e.g., `a***@example.com` | Partially linkable | Easy to read for support, but can still leak identifying information |
| **Surrogate/random ID** | Generates a random code tied to a request/session or a mapping table | Depends on ID/mapping-table lifecycle | Keeps real IDs out of logs; requires managing the mapping and access control |

**HMAC does not encrypt data**: there is no "decrypt HMAC" operation to recover the original ID. It allows someone with the key to **recompute the token** for a candidate and compare. Nor is it Java's `hashCode()`: `String.hashCode()` is only for data structures and lacks the security properties required to protect identifiers.

### Why Is `SHA-256(email)` Still Risky?

Emails, phone numbers, area codes, or sequential IDs have **low entropy** compared to SHA-256's 256-bit space. Anyone with the log file can generate millions of common candidates or take a public email list, compute SHA-256 for each value, and match them against the tokens in the logs. A strong hash function does not make a predictable input set secret.

Example of a dictionary match:

~~~text
Exposed log:  userHash = SHA256("an@example.com")
Viewer:       computes SHA256 for a list of candidate emails
Result:       matching hash => original email can be identified
~~~

Switching to `SHA256("static-salt" + email)` when the salt sits in the code/repo or logs only forces an attacker to prepend the salt when testing candidates. When you need deterministic tokens, HMAC with **a key protected independently from the logs** prevents candidate computation when an attacker only has the log records and **does not have the key**.

If the key is leaked, an attacker can again compute tokens for a candidate list; therefore, the system still needs access control, retention policies, and key-compromise incident response.

## 3. Specify the Token Contract Before Implementing

Before choosing an algorithm, clearly define the log field's contract:

- **Purpose:** do you need to link logs of the same user within a single request, within a tenant, within a service, or across multiple services? Do not broaden the scope beyond what is needed.
- **ID source:** use the system's verified/validated canonical identifier; do not directly trust a client-supplied `email`/`userId` string when the goal is tracing an authenticated user.
- **ID type:** `user` and `account` might share the string `"42"` yet be two different entities. Include the ID type in the computation.
- **Tenant scope:** identical user IDs across two tenants must be handled according to a defined policy. For tenant isolation, include the canonical tenant in the HMAC input or use a separate key per tenant.
- **Version:** include a `v1_` prefix or a `tokenVersion=v1` field to distinguish future key rotations or normalization changes.
- **Output length:** a raw HMAC-SHA-256 digest is 32 bytes; you may truncate it to 16 bytes (128 bits) after evaluating scale and collision probability. Truncate after HMAC; **do not use MD5 just to get a shorter output**.
- **Intended use:** the token is for correlation and diagnostics—**not** as proof of identity, an authorization token, or a unique business key.

A simple log schema:

~~~json
{
  "event": "invoice_lookup_failed",
  "requestId": "req-42",
  "tenantRef": "tenant-a",
  "userRef": "v1_<base64url-truncated-hmac>",
  "tokenVersion": "v1",
  "outcome": "not_found"
}
~~~

The string `<base64url-truncated-hmac>` above is a format placeholder, not a token computed from real data. `tenantRef` may still be sensitive information for your system; keeping the tenant human-readable must follow its own policy. For sensitive audit data, ordinary correlation logs do not replace protected audit records with an appropriately designed storage model.

## 4. Input Normalization: The Common Cause of "Same User" Producing Two Tokens

HMAC is a deterministic transformation for **the same input bytes and the same key**; it does not inherently know that two spellings represent one identity.

The pairs below may be the same or different IDs depending on system rules:

~~~text
"AN@example.com" vs. "an@example.com"
"+84 90 000 0000" vs. "0900000000"
"café" written in precomposed Unicode characters vs. combining marks
"00123" vs. "123"
" tenant-a" vs. "tenant-a"
~~~

**Normalize strictly according to the identifier source's contract**:

1. If it is an **internal UUID/canonical string ID**, use the exact canonical identifier from the database/identity service. Do not strip leading zeros or lowercase a case-sensitive ID on your own.
2. If it is an **email**, do not automatically lowercase the entire local-part and assume two addresses are identical; the comparison rules must be dictated by the identity system in use. Whenever possible, resolve the email to an **authenticated internal user ID** before tokenizing.
3. If it is a **phone number**, normalize according to business-approved rules, such as E.164, without arbitrarily stripping characters in a way that merges two subscribers into one.
4. If Unicode normalization is needed, specify NFC/NFKC along with test logic and the exact version across all services. Do not change normalization during an upgrade without assessing token changes.
5. Reject null inputs, invalid strings, and missing keys at the appropriate layer. Do not silently "fix" IDs and accidentally merge two people.

When multiple languages/services compute the same token, the contract must specify **UTF-8**, the data structure fed into HMAC, the algorithm name, output truncation, encoding, prefix, and version. Writing just `HMAC(tenant + id)` is insufficient: ambiguous concatenation can make `("ab","c")` and `("a","bc")` produce the exact same bytes. Use per-field lengths or a canonical serialization format with unambiguous boundaries.

## 5. Standalone Java 17 Example: HMAC-SHA256 for Log Identifiers

The following program uses only JDK 17. It generates a token from **tenant + identifier type + canonicalized ID**, with **domain separation** and **length-prefixing** to avoid field-boundary ambiguity.

**Warning:** the fixed key below exists only so the lesson can run without configuration. Because it is public in the code, this key **does not protect real data**; never use it in applications, production logs, unit tests containing real data, or documents containing real PII.

Save as **`LogIdentifierHmacDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class LogIdentifierHmacDemo {
    // DEMO ONLY. Do not use a hard-coded key in a real environment.
    private static final byte[] DEMO_KEY =
            "DEMO_ONLY_NOT_A_REAL_SECRET_123456"
                    .getBytes(StandardCharsets.UTF_8);

    // Separate fields using big-endian byte length.
    private static void field(Mac mac, String value) {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        mac.update(ByteBuffer.allocate(4).putInt(bytes.length).array());
        mac.update(bytes);
    }

    private static String token(String tenant, String type, String id)
            throws Exception {
        // Mac is stateful: create a new instance for each computation.
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(DEMO_KEY, "HmacSHA256"));

        // Domain prefix avoids sharing with HMACs used for other purposes.
        mac.update("log-ref:v1".getBytes(StandardCharsets.UTF_8));
        field(mac, tenant);
        field(mac, type);
        field(mac, id);

        byte[] digest = mac.doFinal();
        // Truncate to 128 bits for illustration; do not arbitrarily truncate shorter.
        String encoded = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(Arrays.copyOf(digest, 16));
        return "v1_" + encoded;
    }

    public static void main(String[] args) throws Exception {
        String first = token("tenant-a", "user", "user-0042");

        System.out.println("stable=" + first.equals(
                token("tenant-a", "user", "user-0042")));
        System.out.println("tenant_scoped=" + !first.equals(
                token("tenant-b", "user", "user-0042")));
        System.out.println("type_scoped=" + !first.equals(
                token("tenant-a", "account", "user-0042")));
        System.out.println("prefix=" + first.startsWith("v1_"));
        System.out.println("length=" + first.length());
    }
}
~~~

Compile and run with Java 17 or later:

~~~bash
javac -encoding UTF-8 LogIdentifierHmacDemo.java
java LogIdentifierHmacDemo
~~~

**Deterministic stdout** (logic verified against equivalent JShell/JDK behavior):

~~~text
stable=true
tenant_scoped=true
type_scoped=true
prefix=true
length=25
~~~

Explanation:

1. `Mac.getInstance("HmacSHA256")` and `SecretKeySpec` use JCA's HMAC-SHA-256. The same **key + bytes + algorithm** produces the same result. Because it only prints booleans, the program exposes neither the raw ID nor the full token to stdout.
2. `"log-ref:v1"` is a fixed domain for **generating log identifiers**. Do not reuse the same computation as a MAC for message authentication or another protocol.
3. `field(...)` feeds the UTF-8 byte length (4 bytes) followed by the value into the HMAC. This cleanly distinguishes field combinations, provided every system follows the contract.
4. `tenant` and `type` provide **scoping**: the same `id` with a different tenant/type yields a different token with very high probability. This is correlation separation, **not a substitute for tenant authorization checks**.
5. `Arrays.copyOf(digest, 16)` takes the first 16 bytes of the HMAC; `Base64.getUrlEncoder().withoutPadding()` encodes them into **22 characters**. Adding `v1_` (3 characters) gives a length of 25.
6. `Mac` must not be shared across threads because it is stateful and makes no thread-safety guarantees. Creating a new instance each time as shown is a safe illustration; you can optimize after measuring in practice.
7. The example expects an **already canonicalized** ID. The code does not normalize inputs itself so it doesn't accidentally alter an ID's meaning. In production, null/empty/format constraints and tenant permissions must be validated before calling.
8. The `tenant_scoped=true` output is a property of **these specific demo inputs** and a stable HMAC; in theory, a truncated output still carries a small collision probability rather than an absolute uniqueness guarantee.

### Why Not Use `MessageDigest.getInstance("SHA-256")`?

`MessageDigest` is for **keyless** hashing. When an identifier has few candidates, it lets anyone with the logs hash a list of IDs and look for matches. HMAC requires a secret key to compute the token, raising a substantial barrier when the key is well protected. Simply "hashing harder" with multiple rounds of SHA-256 or concatenating a static salt in code does not replace secret management.

## 6. How Should Secret Keys Be Used in Production?

The example above illustrates the computation, **not a production-ready key manager**. In a real deployment, you need to:

- **Generate keys with sufficient randomness:** e.g., 32 bytes (256 bits) created by a CSPRNG/secret manager. Do not use operator passwords, short guessable keys, tenant names, or hard-coded strings.
- **Store keys in a secret management system:** a secret manager/KMS or equivalent with ACLs, auditing, and lifecycle management. If the application receives the key via an environment variable or secret file, protect process configuration, access permissions, and deployment paths; never log environment values.
- **Never embed keys in source code, JARs, images, Git configs, or test snapshots.** Anyone reading source with a demo key must understand it provides no security.
- **Grant least-privilege access:** only services that need to compute tokens should receive the key. Dashboards and collectors typically **do not need the key**—they only store tokens.
- **Isolate scopes:** for data across tenants/environments that must not be correlated, include the scope in the MAC message and consider separate keys per environment/tenant when stronger isolation is required.
- **Do not fall back when the key is missing:** never fall back to `SHA256(rawId)` or logging `rawId` directly. Fail startup or disable the `userRef` field with a safe operational alert, depending on system requirements.

Example **snippet** showing how to read a Base64 key distributed by a secret system (not a standalone program; does not fetch keys directly from the cloud):

~~~java
import java.util.Base64;
import javax.crypto.spec.SecretKeySpec;

String configured = System.getenv("LOG_PSEUDONYM_KEY_B64");
if (configured == null || configured.isBlank()) {
    throw new IllegalStateException("logging pseudonym key missing");
}
byte[] keyBytes = Base64.getDecoder().decode(configured);
if (keyBytes.length != 32) {
    throw new IllegalStateException("logging pseudonym key has invalid size");
}
SecretKeySpec hmacKey = new SecretKeySpec(keyBytes, "HmacSHA256");
// Pass hmacKey to a lifecycle-managed helper; never log keyBytes.
~~~

This is merely one way to receive a key from **a configuration channel**—it does not mean environment variables are inherently safe; a secret manager, process access controls, and deployment policies remain essential. On Base64 or key-size errors, do not print the key string into exceptions or telemetry.

In a real application, **inject the key** into the HMAC computation class rather than keeping `DEMO_KEY` as in learning code. Use the injected `SecretKey` and create a new `Mac` instance per computation. Do not let the logging backend read sensitive data from user configuration and pass it unchecked to an appender.

## 7. Key Rotation and Log Correlation Over Time

Suppose a user has token `v1_abc...` from key `K1`. When rotating to `K2`, that same user will typically get token `v2_xyz...`. This is expected because HMAC depends on the key. **Rotating the key does not change tokens already written to old logs.**

Your rotation design should answer:

1. When does `v1` stop being used for **new writes**, and when does `v2` take effect? Do all instances switch to the same version simultaneously?
2. Is it necessary to join old and new logs? If so, limit the time window and the roles permitted to join them; avoid creating unnecessary permanent correlation paths.
3. Should old keys be retained? If stored, enforce expiration, privileged access, and auditing; delete them on schedule per retention/policy.
4. If a key is compromised, do you need to stop using it immediately, investigate emitted records, revoke access, or delete/restrict logs according to policy?
5. Do tokens from multiple services need to match? They must agree on serialization, canonicalization, domain, and key/scope by design; do not share keys broadly just for search convenience.

**Attach the version to the token or log field** so investigators know which rule an event used. Do not treat the `v1_` prefix as a secret key ID; the prefix is just metadata. Some systems choose a different token per day or per request to **reduce long-term tracking**; the trade-off is harder event correlation across those boundaries.

Logging both `v1` and `v2` tokens simultaneously for every user over long periods just for convenient joins is discouraged: it increases linkability and data exposure. If a migration mapping is truly required, give it an explicit purpose, lifetime, access control, and dedicated audit trail.

## 8. Integrating with the Logger: Transform Before Emitting Events

Hashing/HMAC must happen **before the value enters the logging system**. Putting the raw ID into `MDC` and hoping some formatter will mask it is unsafe: secondary appenders, error handlers, async queues, collectors, or other JSON encoders can still emit the raw ID.

With an SLF4J-backed logger, the structural idea is:

~~~java
// Service snippet: not a standalone program.
String userRef = tokenService.forUser(verifiedTenantId, canonicalUserId);
logger.info("event=profile_loaded userRef={} requestId={}",
        userRef, requestId);
~~~

`tokenService` must manage the real HMAC key, tenant/type scope, and version; inputs come from authenticated application components. **Do not** log `canonicalUserId` in a debug message alongside `userRef`, as doing so defeats the protection.

If multiple code paths need the context:

~~~java
// Snippet illustrating SLF4J MDC.
Map<String, String> previous = MDC.getCopyOfContextMap();
try {
    MDC.put("userRef", userRef);          // Already HMAC-hashed beforehand.
    MDC.put("requestId", requestId);     // Request-specific correlation ID.
    logger.info("event=profile_loaded");
} finally {
    if (previous == null) MDC.clear();
    else MDC.setContextMap(previous);
}
~~~

The snippet above requires importing `java.util.Map` and `org.slf4j.MDC`; it is not a pure JDK program. Layouts like Logback's `%X{userRef}` can output the token placed in MDC. When using thread pools, MDC may not propagate automatically from producer to worker; capture/restore across boundaries and always clean up in `finally` so user A's token never leaks onto user B's events.

**Hashing in an async appender after enqueuing is not a good default** if the event already carries the raw ID. Other buffers/sinks may already have seen the raw value, and the worker may no longer have the right context. Enforce the policy where the event is created or in a mandatory, tested logging facade.

### Structured Logging and Exceptions

A safe JSON event might look like:

~~~json
{
  "event": "profile_lookup_failed",
  "userRef": "v1_<token>",
  "requestId": "req-42",
  "status": "not_found"
}
~~~

Do not let `Throwable.getMessage()`, stack traces, URL queries, or payloads enter logs **unchecked** if they might contain emails, phone numbers, API keys, or raw IDs. Even when `userRef` is generated properly, a call like `log.error("lookup failed for " + rawEmail, e)` still leaks data.

Parameterized logging (such as SLF4J's `"userRef={}"`) helps with formatting, but **does not automatically hide sensitive data**. Hashing one field does not replace masking, redaction, log injection handling, retention policies, or log access controls.

## 9. HMAC Does Not Replace Privacy Safeguards

Pseudonymization reduces the appearance of direct identifiers, but residual risks remain:

| Scenario | Residual Risk | Additional Safeguard |
| --- | --- | --- |
| Token remains stable for years | Users can be tracked over time | Shorten retention, narrow key/scope and token lifetime |
| Key is compromised | Attackers can test candidate IDs | Secret management, rotation, incident response, and access restrictions |
| Input has a small candidate set | Tokens can be confirmed if key/mapping leaks | Protect the key; do not call HMAC absolute anonymity |
| Log also includes email in message | `userRef` field is safer, but event still leaks PII | Redact all fields, stack traces, and request metadata |
| Tenants A and B share internal IDs | Cross-tenant linking possible without scoping | Include canonical tenant/type/purpose in the HMAC input |
| Token used for authorization | Observable/predictable tokens can be abused | Never use log tokens as credentials or proof of permission |
| Two different IDs collide after truncation | Rare collision causes erroneous joins | Choose enough bits, quantify risk, never use as a business key |
| Logs copied across collectors/backups | Expands storage and access surface | Policy-driven RBAC, encryption, retention, deletion, and auditing |

**HMAC-hashed data can still be personal data in many legal contexts** if it can be linked back to a person or used for tracking. Compliance decisions depend on regulations, data types, purpose, and re-identification risk; evaluate with your security/legal teams rather than declaring "it's hashed so we can keep it forever."

### Data You Should Never "Just Hash and Log"

- **Passwords, private keys, OTPs, recovery codes:** never write to logs, even hashed; do not use the logging system as a credential store.
- **Access tokens, refresh tokens, session cookies:** prefer not logging them at all. If session tracking is required for investigations, consider a low-privilege correlation ID or an HMAC with a tight scope and TTL under an approved policy.
- **Health, financial, identity document, or precise location data:** process only if there is a genuinely authorized purpose; HMAC does not eliminate privacy risk.
- **Email/phone:** if you need to contact a user, do so through an authorized business system rather than trying to "reverse tokens" from logs.

## 10. Performance and Thread Safety

HMAC-SHA-256 is usually fast enough for short IDs, but you should not turn every log call into an expensive computation chain without measuring. Keep in mind:

1. For **DEBUG** logs that may be disabled, avoid building tokens or formatting expensive data before knowing the event will actually be emitted. You can check `logger.isDebugEnabled()`, though never use that to skip mandatory audit/security logs.
2. `Mac` is stateful and not guaranteed to be thread-safe. Do not share a single `Mac` instance across threads. Create one per call as in the example, or design a tested pooling/thread-local mechanism that cleans up properly on key rotation.
3. **Caching** tokens can reduce repeated HMAC computations, but the cache must bound size/TTL and protect raw IDs in memory; never keep an unbounded map of sensitive IDs.
4. While `userRef` cardinality in a **log field** may be acceptable, never put a per-user token into **metric labels**, as that can cause time-series cardinality explosions.
5. If cross-request correlation is unnecessary, use a per-request random `requestId` instead of HMAC-hashing a long-lived identifier—it minimizes data and simplifies operations.

Truncating the token to 16 bytes only reduces display size; the full HMAC-SHA-256 computation still runs. A 128-bit output has no mathematical uniqueness guarantee, so do not use it as a business primary key.

## 11. Functional and Security Testing

### Functional Tests

With a fixed key, domain, and canonical ID:

- Same tenant/type/ID → **stable token**; valid logs in the same scope can be linked.
- Same ID, **different tenant** → different token; verify no cross-tenant correlation per the defined schema.
- Same ID, **different type/purpose** → different token; prevents collisions between `user` and `account`.
- Same input, **different key/version** → different token; verify during rotation.
- Unicode strings, empty inputs, nulls, long IDs, and non-canonical data → handled by a clear policy without producing wrong IDs or logging raw values.
- In distributed systems, the same contract and key/scope → produce compatible tokens across services **authorized** to correlate.
- Token has the expected prefix/version and encoding; when truncating HMAC to 16 bytes, unpadded `Base64url` is 22 characters, plus the `v1_` prefix equals 25.

### Data-Leakage Tests

1. Create test data with a marker like `TEST_PRIVATE_ID_12345` and emit INFO/DEBUG/WARN/ERROR logs, including exceptions.
2. Search for the marker **across all outputs**: stdout, files, async appenders, collectors, indexes, dashboards, error reporting, and trace attributes. Expected result: no raw marker appears in unauthorized places.
3. Test **missing or malformed keys**: no fallback to raw IDs or unkeyed SHA-256; configuration errors are surfaced without printing secrets.
4. Test **MDC in a thread pool**: task A followed by task B on the same thread must not carry over each other's `userRef`/`tenant`.
5. Test rotation: two versions are not mixed inexplicably, investigators can still read versions, and old keys are properly restricted.
6. Test storage policies: someone authorized only for tenant A's logs cannot find/read tenant B's events by altering queries.
7. Simulate partial pipeline exposure: log data alone must not allow reversing IDs via a simple SHA-256 dictionary; if the key is compromised, evaluate the response procedure.

**Do not use real emails or phone numbers as test vectors in test outputs.** Test fixtures should be synthetic data and never reused as production keys.

## 12. Common Mistakes

| Mistake | Why It's Wrong | How to Fix |
| --- | --- | --- |
| Using `String.hashCode()` | Non-cryptographic hash, easy collisions, no secret | Use a risk-assessed pseudonymization mechanism |
| Using `SHA256(email)` and calling it "anonymous" | Vulnerable to dictionary attacks over emails/phones | Minimize data first; if joins are needed, use HMAC with a secret key |
| Putting a static salt/pepper in Git | Anyone reading the code can test candidates | Manage keys independently in a secret manager/KMS |
| Using a random salt per event while expecting joins | Every record gets a different token and cannot be compared directly | Use scoped, versioned deterministic HMAC |
| HMAC without tenant/type separation | IDs can be linked across unauthorized contexts | Domain separation and tenant/type in the MAC input |
| Arbitrarily lowercasing IDs | Two distinct IDs may be merged | Normalize according to the identity system |
| Hashing in an appender while raw values sit in message/MDC | Other outputs still leak the raw value | Tokenize before creating the log and test end-to-end |
| Logging raw values when the key is missing | One config error causes a severe data leak | Fail closed for sensitive fields; emit a safe alert |
| Attaching long-lived tokens to metric labels | Explodes cardinality and enables user tracking | Use low-cardinality labels; keep correlation in controlled log fields |
| Treating the hash as authorization | Anyone who reads the token could be mistaken for the account owner | Base authorization on an authenticated principal |
| Protecting only current logs and forgetting backups | Old copies still retain PII/tokens | Enforce RBAC, retention, and deletion across the full lifecycle |
| Reusing one `Mac` across threads | Stateful object; can corrupt results | One instance per computation or verified thread-local management |

## 13. Production Readiness Checklist

1. **Ask whether cross-log correlation is truly needed.** If not, keep only `requestId` or `traceId`.
2. **Classify source data** and confirm authorized purposes; never log raw secret IDs or credentials.
3. **Choose HMAC-SHA-256 with a secret key** when deterministic tokens are needed for guessable IDs; do not rely on unkeyed hashes as the primary safeguard.
4. **Write a byte-level contract**: canonical ID, tenant, type, domain, UTF-8, length-prefixing, version, token length, and output encoding.
5. **Keep keys out of source code**, managed by role, environment, and rotation procedures; never fall back to exposing raw IDs.
6. **Tokenize before the logger**, ensuring exceptions, MDC, structured JSON, and async pipelines do not leak raw data.
7. **Test stability and isolation**, including nulls, Unicode, key rotation, multiple services, and thread pools.
8. **Keep logs within access/retention boundaries**, monitoring for PII output across all sinks and backups.
9. **Never treat `userRef` as a credential or business ID**, and do not use long-lived tokens for unnecessary tracking.
10. **Review periodically**: which log fields are collected, who reads them, retention periods, which keys remain active, and whether correlation has drifted beyond its original purpose.

**Remember:** Hashing changes an identifier's representation, but **does not automatically anonymize data**. For guessable IDs that require correlation, HMAC with a secret key, clear canonicalization, and controlled scoping and versioning are generally more useful than plain SHA-256. The safest approach remains **not logging unnecessary data**, combined with key protection, access control, retention-based deletion, and end-to-end leakage testing.

### References

- OWASP — [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): data types to exclude, minimizing/masking sensitive data, protecting logs at rest and in transit.
- Java SE 17 — [Java Cryptography Architecture Reference Guide: Mac/HMAC](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html).
- Java SE 17 — [`javax.crypto.Mac`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html), [`SecretKeySpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/SecretKeySpec.html), [`Base64`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Base64.html).
- SLF4J — [MDC API](https://www.slf4j.org/api/org/slf4j/MDC.html) and [Manual](https://www.slf4j.org/manual.html).