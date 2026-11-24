# 5.4 Generating, Storing, and Separating HMAC Keys by Purpose

**HMAC (Hash-based Message Authentication Code)** lets parties sharing a **secret key** create and verify authentication tags for messages. With `HmacSHA256`, the full output is typically **32 bytes (256 bits)**, yet security depends heavily on **how the key is generated**, **who holds the key**, **what the key is used for**, and **how keys are rotated and revoked**. Computing HMAC with the right algorithm while reusing a single key across webhooks, sessions, and internal APIs can turn one minor incident into many.

Lesson goals: generate keys with sufficient entropy; store and provision keys within proper trust boundaries; understand the two approaches of **independent key separation** versus **purpose-based key derivation (key derivation/domain separation)**; and manage the lifecycle from issuance to revocation. Examples use Java 17+ and JCA/JCE.

## 1. Recognizing the Exact Role of an HMAC Key

HMAC uses a cryptographic hash function together with a secret key. With the notation:

```text
tag = HMAC(key, message)
valid = constant_time_compare(received_tag, HMAC(key, received_message))
```

- **The tag creator** knows the secret key; **the tag verifier** must also know the secret key, or invoke an authorized cryptographic service to verify.
- If the message changes while the tag stays the same, verification will fail with overwhelming probability when HMAC is used properly.
- **HMAC does not encrypt**: the authenticated message and headers remain readable. When transit confidentiality is needed, use TLS; when stored data needs protection, use an appropriate encryption solution.
- **HMAC does not prevent replay on its own**: a valid `message + tag` pair resent later will still verify. The protocol needs timestamps, nonces, sequences, idempotency, or replay-rejection mechanisms where required.
- **HMAC does not prove a single individual signed**: every party sharing the key has the capability to generate tags. It is authentication based on a *shared secret*, and does not provide non-repudiation like digital signatures under properly managed keys and identities.
- HMAC does not determine **authorization**; a webhook with a valid tag still needs checks on event type, source/tenant, business permissions, and processing state.

### 1.1. Key size differs from MAC length

With `HmacSHA256`, the full tag is **256 bits = 32 bytes**. Key length is a separate quantity. The key may be longer or shorter than 32 bytes depending on the protocol and entropy source. For **randomly generated secret keys**, **32 bytes (256 bits)** is a clear and commonly appropriate practical choice for HmacSHA256; this is not a rule that "HMAC-SHA256 requires a key of exactly 32 bytes."

Inside HMAC, a key longer than the hash's block size is processed per the HMAC construction and does not make the SHA-256 tag longer than 32 bytes. Do not conclude "a 512-bit key gives a 512-bit strong MAC"; the security bound still depends on the hash function, tag length, attack model, key management, and protocol.

| Component | Example | Is It Secret? |
| --- | --- | --- |
| **HMAC key** | 32 bytes from a cryptographic RNG | **Yes**; anyone with the key can forge tags |
| **Message** | Body, path, timestamp, nonce | Usually no; depends on the data and TLS |
| **MAC/tag** | 32-byte HmacSHA256 output | Does not need secrecy, but must remain bound to the message/context |
| **Key ID (`kid`)** | `webhook-prod-v2` | Usually public; only an identifier to look up the key, not proof of trust |
| **Key version** | `v1`, `v2` | Non-secret metadata; assists key rotation |
| **Purpose/context** | `session`, `webhook-inbound` | Does not need secrecy; used for binding and separation |
| **HKDF salt** | Random byte sequence that can be stored publicly | Does not need secrecy; must be recovered identically on re-derivation |

## 2. Generating HMAC Keys Safely

### 2.1. Generate from a CSPRNG, not predictable data

An HMAC key must be unpredictable to an adversary, even when they know the algorithm and many published messages and tags. Java provides `SecureRandom` as its cryptographic random number generator interface; a new 32-byte key can be created as follows:

```java
byte[] key = new byte[32];
new java.security.SecureRandom().nextBytes(key);
```

This is an *illustrative snippet* to make the size explicit, not a standalone program. In real code, store the key in a secure vault immediately after generation, manage who holds it, and ensure it can be retrieved while previously issued messages still need verification.

You may use a provider's `KeyGenerator` if it supports the right HMAC key algorithm; pay attention that its size parameter is in **bits**, not bytes. `SecretKeySpec(key, "HmacSHA256")` only **wraps an existing byte array**; it does not create entropy or turn a weak password into a strong key.

**Avoid these key sources:**

- `new Random()`, `Math.random()`, system time, sequence numbers, usernames, or guessable identifiers.
- A user-entered string passed to `getBytes(UTF_8)`. Long byte length does not guarantee corresponding entropy.
- Keys hardcoded in Java, YAML, Docker images, CI variables printed in logs, or present in Git history.
- Shared keys copied from development into staging/production.
- Using the output of `SHA-256(password)` directly as an HMAC key as if the password had 256 bits of entropy.

If a secret must be derived from a human password, consider a salted, properly costed **password KDF** design (such as Argon2id/scrypt/PBKDF2, depending on ecosystem and policy), instead of padding characters, fast-hashing, or Base64-encoding. In service-to-service systems, prefer generating and managing **truly random** keys without involving passwords.

### 2.2. Do not confuse entropy, encoding, and length

- 32 bytes from properly used `SecureRandom` carry approximately **256 bits of entropy**; 32 bytes of the string `"aaaaaaaa..."` have very low entropy.
- `Base64`, hex, or PEM only **change byte representation**; they do not make a key more secure. 32 binary bytes can be represented as 44 standard Base64 characters, yet it remains a 32-byte key that must be kept secret.
- Do not print raw keys or Base64 strings of keys for testing. Log only **key ID, algorithm, version, status**, and operational fields containing no key material.
- An HMAC key is **different** from a nonce/IV or salt; the fact that a nonce/salt may be public never permits making an HMAC key public.

### 2.3. Who creates and provisions keys?

Clearly establish **the key owner** and provisioning path:

1. Ideally, a key/secret management system generates or imports keys through a controlled channel, grants permissions by service/tenant/purpose, and audits usage.
2. If a program must generate keys, use a CSPRNG, place the key immediately into secure storage with metadata; never print to terminal, send via chat/email, or commit to a repo.
3. When two systems need **the same** key to verify HMACs (e.g., sender and webhook receiver), share via a least-privilege provisioning/secret-manager workflow. Treat **both ends** as capable of creating MACs, so HMAC cannot tell them apart without additional constraints.
4. An HSM/KMS with MAC generation/verification features can avoid bringing raw keys into application processes; verify the vendor's specific API and algorithms. **Do not assume every KMS supports HMAC or the same `SecretKey` form**.

## 3. Key Storage: Protecting Secrecy and Access Scope

An HMAC key is a sensitive asset. Anyone who knows the key can forge messages across every context sharing that key.

| Storage / Delivery | Assessment and Notes |
| --- | --- |
| **Secret manager/KMS/HSM** | Preferred per system requirements; IAM separates read/write/sign/verify permissions, audit, rotation, and key protection. If a non-exportable MAC API exists, the application may not need raw key access. |
| **Secret loaded by the app at startup** | Allow only the necessary workload identity to read; restrict file permissions/mounts, avoid leaks via logs, crash dumps, error messages, and debug endpoints. |
| **Environment variables** | Usable in constrained environments, but environment variables are not a default secret vault; consider exposure via child processes, debug tools, logs, or deployment manifests. |
| **Databases / backups** | If keys must be stored there, encrypt with a **separate** managed key, restrict access, and govern backup/restore; never store plaintext in easily readable records. |
| **Source code, Dockerfiles, committed `application.yml`, docs, tickets, chat** | **Never store real keys**. Commit history and copies can persist even after a line is deleted. |

Core principles:

- **Least privilege:** a service that only verifies MACs should have **verify** permission on the KMS if the infrastructure supports split permissions, rather than reading raw keys or signing arbitrary messages by default.
- **Environment isolation:** development, test, staging, and production use independent keys. Isolate by tenant, partner, protocol, or service when trust boundaries require it.
- **Lifecycle control:** every key has an owner, purpose, algorithm, key ID, version, activation/stop-signing/stop-verifying dates, rotation/retention policies, and a revocation process.
- **No keys in logs or error responses:** avoid `Arrays.toString(key)`, `HexFormat.of().formatHex(key)`, or `Base64.getEncoder().encodeToString(key)` in logs. Tags may also require data hygiene/redaction depending on business rules, though a tag **is not a key**.
- **Memory considerations:** `Arrays.fill(key, (byte) 0)` can clear a temporary byte array you own, but does not guarantee wiping all copies in `SecretKeySpec`, providers, heap dumps, swap, or HSMs. Do not treat overwriting one array as complete protection.
- **Fail closed without a valid key**; never fall back to a default `"secret"` key, disable MAC checks, or downgrade to a weak algorithm.

### 3.1. Non-exportable keys and Java JCA/JCE

In Java, `SecretKey` is an abstraction. For software keys, `getEncoded()` may return bytes; for non-exportable HSM/provider keys, this method may return `null`. Some providers require running `Mac` through that specific provider or calling a dedicated MAC API.

Therefore, architecture **should not rely on dumping a key to bytes** to verify "exact 32 bytes" in production. Configure key size and management policies at key creation time; application code calls HMAC through an interface implementable by JCA or KMS depending on the system.

## 4. Separating Keys by Purpose (Key Separation)

### 4.1. Why is one "super HMAC secret" dangerous?

Suppose an application uses one key to:

- Sign session cookies (session authentication);
- Verify partner webhooks;
- Sign file download URLs;
- Verify internal administrative tasks.

If the webhook key leaks from the integration side, an attacker can compute HMACs for the other message types. **Knowing a key = being able to forge MACs in every protocol using that key.** A parser that treats any message with a valid tag as "trusted" without checking scope opens the door to *cross-protocol confusion* attacks.

Good design separates secrets **and** separates message interpretation. Example boundaries:

| Purpose | Logical Identifier | Authorized Parties |
| --- | --- | --- |
| Session/cookie | `shop/prod/session/v3` | Session management service |
| Inbound partner webhook | `shop/prod/webhook/partner-A/v2` | Webhook gateway and the corresponding partner |
| Expiring URL | `shop/prod/download-link/v1` | URL issuing and verifying service |
| Internal request | `shop/prod/internal-job/v4` | Task-handling service |

Do not merely rename **variables**; use **different keys** or **independently derived subkeys**, purpose-scoped access policies, and purpose binding inside the MAC-protected data.

### 4.2. Approach A: generate independent random keys per purpose

The simplest approach is separate generation:

```text
K_session     <- SecureRandom(32 bytes)
K_webhook     <- SecureRandom(32 bytes)
K_download    <- SecureRandom(32 bytes)
K_internal    <- SecureRandom(32 bytes)
```

Each key is stored, labeled, provisioned, and rotated independently. If the webhook partner key leaks, the session key cannot be derived from it. **This is usually the easiest approach to audit, contain incidents, and rotate keys independently** when secret management infrastructure exists.

The tradeoff is that the number of keys, copies, and provisioning permissions grows with the number of purposes/tenants. Maintain a clear registry/secret manager; avoid collapsing into one shared key simply to reduce entries.

### 4.3. Approach B: derive subkeys from a root secret using HKDF

When managing many related keys from a **high-entropy root key**, **HKDF-SHA256** (RFC 5869) can derive subkeys per purpose:

```text
root_secret  --HKDF-Extract(salt)--> PRK
PRK + info("shop|prod|session|v1") --> K_session (32 bytes)
PRK + info("shop|prod|webhook|v1") --> K_webhook (32 bytes)
PRK + info("shop|prod|download|v1")-> K_download (32 bytes)
```

In standard HKDF:

- **IKM (input keying material):** input secret with suitable entropy. Here it is a strong random root, **not** a raw user password that has not passed through a password KDF.
- **Salt:** a typically random, optionally public value used in the `Extract` phase to produce **PRK (pseudorandom key)**. To re-derive the same key after a restart, **preserve the exact salt** alongside metadata; changing the salt changes the subkeys. HKDF defines a default when salt is omitted, though the choice should be explicitly designed and documented.
- **Info:** a byte string describing context, purpose, and version, used in the `Expand` phase. Different `info` values yield distinct subkeys under HKDF's security assumptions.
- **Length:** number of output **bytes** desired. With HmacSHA256, a 32-byte subkey corresponds to **256 bits**; HKDF Expand has a total output limit of at most **255 × HashLen** bytes.
- **The root key has overarching power:** compromising the root allows deriving **all subkeys**. Separating via HKDF avoids key reuse, but **does not achieve the same root-risk isolation as completely independent random keys**.

`info` design should clearly encode **application, environment, protocol, purpose, partner or tenant if needed, algorithm, and version**. Any user-supplied fields must be canonicalized and unambiguously encoded, e.g., TLV or length-prefixing; never naively join delimiter-containing strings where two parameter sets can yield the same `info`.

**Never "derive keys" using `SHA256(root || purpose)` or Base64 of the root.** Use a defined and vetted KDF such as HKDF following its exact steps and parameters.

### 4.4. Key separation differs from tagging messages with labels

These are two distinct defense layers:

1. **Key separation:** `K_session != K_webhook`. Someone holding the webhook key cannot compute MACs under the session key.
2. **Message domain separation:** even within one key scope, including structured, unambiguous fields such as `protocol_version`, `purpose`, `tenant`, and `operation` in the MACed bytes prevents a tag for one message type from being interpreted as another.

Merely prepending `"session:"` to a message while keeping **one shared secret distributed to every service** fails to contain blast radius if that secret leaks. Conversely, even with independent keys, all business-critical fields must still be authenticated.

Metadata such as `purpose`, `tenant`, `environment`, and `key_id` are only **reference hints**, not self-verifying proof; **the server must enforce policies binding them to the key and request**.

## 5. Designing an Appropriate MAC and Verification Protocol

A protocol may use a structure like:

```text
version: 2
key_id: webhook-partner-A-v2
timestamp: 2026-10-31T12:00:00Z
nonce: 4f8b...     (example value)
body: {"event":"payment.paid","id":"evt123"}
mac: <HMAC-SHA256 of the defined canonical representation>
```

These values are only an illustrative model, **not a request with a precomputed MAC**. For real use, specify the exact signed bytes (method, path/query, timestamp, nonce, body, context) and canonicalization rules. If security-relevant bytes are omitted from the MAC, an attacker can alter them without changing the tag.

A sound server pipeline:

1. **Determine the trusted protocol and purpose from the route/configuration**; never let the client self-declare a purpose to pick a broader-privilege key scope.
2. Bound the format/length of `key_id`; look up the key in the registry **matching tenant + purpose + environment + status**. Since `key_id` is a client-supplied selector, treat it as untrusted input—never as a file path, URL, or arbitrary secret loader directive.
3. Use **only the server-mandated algorithm** (e.g., HmacSHA256); never accept `alg=none` or another algorithm based on untrusted headers.
4. Check timestamp within the allowed window, unused nonce/idempotency, and appropriate limits **if the protocol requires replay protection**.
5. Reconstruct **the exact signed bytes**, compute HMAC with the corresponding key, check standard tag length, and compare using a method that avoids content-dependent timing leaks, such as `MessageDigest.isEqual(byte[], byte[])` in Java once length is verified.
6. Only after a valid MAC, run business logic—still checking authorization, tenant, event type, and state preconditions. Replay tracking must update atomically if concurrent duplicate requests must be blocked.

**Canonicalization note:** header casing, query parameter ordering, UTF-8 encoding, line endings, JSON whitespace, Unicode normalization, and raw body handling can produce two different byte streams. In webhooks, if the partner signs the **raw HTTP body**, the receiver must use the exact received raw bytes per the spec, **never parse and re-serialize JSON** before computing HMAC.

**Tag comparison:** a full HmacSHA256 tag is 32 bytes. If a protocol permits tag truncation, it must define exact length parameters, appropriate bounds, length validation, and compute over the exact byte sequence. Never truncate tags arbitrarily to "save bandwidth."

## 6. Key Lifecycle: Create, Use, Rotate, Revoke, Destroy

HMAC keys typically outlive a single Java process instance. To replace keys without breaking in-flight valid requests, you need a **versioned key ring** with distinct states for new signing versus legacy verification.

| Stage | Actor | Rules |
| --- | --- | --- |
| **Generate** | Key management | Generate new random key, ID, owner, purpose, algorithm, timestamps; never reuse old secrets |
| **Store/provision** | Secret manager/KMS | Encrypt/store in HSM where appropriate; grant least-privilege access to workloads and partners |
| **Active signing** | MAC creator | Only **one active version for new signing** per scope needing consistency |
| **Verify overlap** | Verifier | May accept **both new and old keys** during a bounded transition window, each restricted to its purpose/scope |
| **Retire** | Key management | Stop signing with old key; stop verifying once old valid messages have expired/been processed |
| **Revoke/compromise** | Incident response | If compromised, revoke rapidly, audit potentially forged data, do not wait for scheduled rotation |
| **Destroy** | Key management/backup | Delete/crypto-shred per policy, including copies in backups and caches; audit destruction without logging the secret |

### 6.1. Rotation example with `kid`

Suppose a service uses `key_id=webhook-v1` and issues `webhook-v2`:

- **Prepare:** generate an independent v2 secret, update the receiver so it knows v2 before the sender switches to signing with v2.
- **Transition:** sender starts emitting `kid=v2` and HMAC with key v2. Receiver verifies v2; temporarily continues verifying v1 for messages issued before the cutoff.
- **Finalize:** after the validity window and propagation delay, disable v1 verification, revoke access, and purge caches/backups per policy.
- **If v1 is compromised:** replace the key and **revoke immediately per incident response**, do not keep an "overlap" by default just to avoid client errors. Sessions/tokens signed with v1 may need invalidation and stakeholders notified.

**Do not try every key, every purpose, and every tenant to "find a matching MAC"** when the request specifies a key ID. That widens acceptance outside policy and obscures expiration boundaries. Look up the exact scope, check status, then verify.

### 6.2. Root key lifecycle with HKDF

Rotating the root produces a brand-new set of subkeys (even if `info` stays unchanged), so:

- Store **root key version + salt + info structure + KDF algorithm + output length** as essential information for re-derivation.
- Replace the root on schedule at the key-management layer and roll out new subkeys gradually; key IDs must identify the right version.
- A compromised root means all subkeys derived from it may be compromised; plan rotation for **the entire affected subkey domain**.
- Do not distribute the raw root to every microservice just so they derive subkeys themselves. Whenever possible, provision only scoped subkeys or expose a permission-bounded derivation/MAC API.
- Never reuse the raw root directly to HMAC business messages: the root is dedicated to the KDF under that design.

## 7. Java 17+: Generating Independent HMAC Keys and Binding Purpose

The standalone program below generates **two independent 32-byte random keys** for `session` and `webhook`. The prefix `demo:v1|purpose|` adds domain separation in the MACed bytes; the demo only uses two fixed purposes chosen by trusted code. Real systems need unambiguous encoding and server-side scope enforcement policies.

Save with exact name **HmacPurposeDemo.java**:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class HmacPurposeDemo {
    static byte[] generateKey() {
        byte[] key = new byte[32];
        new SecureRandom().nextBytes(key);
        return key;
    }

    static byte[] tag(byte[] key, String purpose, String payload) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        mac.update(("demo:v1|" + purpose + "|").getBytes(StandardCharsets.UTF_8));
        return mac.doFinal(payload.getBytes(StandardCharsets.UTF_8));
    }

    static boolean verify(byte[] key, String purpose, String payload,
                          byte[] expected) throws Exception {
        return expected != null && expected.length == 32
                && MessageDigest.isEqual(expected, tag(key, purpose, payload));
    }

    public static void main(String[] args) throws Exception {
        byte[] sessionKey = generateKey();
        byte[] webhookKey = generateKey();
        String payload = "user=alice";
        byte[] sessionTag = tag(sessionKey, "session", payload);

        System.out.println("session key bytes: " + sessionKey.length);
        System.out.println("session tag bytes: " + sessionTag.length);
        System.out.println("correct purpose: "
                + verify(sessionKey, "session", payload, sessionTag));
        System.out.println("wrong purpose: "
                + verify(sessionKey, "webhook", payload, sessionTag));
        System.out.println("wrong key: "
                + verify(webhookKey, "session", payload, sessionTag));
        System.out.println("tampered payload: "
                + verify(sessionKey, "session", "user=bob", sessionTag));

        Arrays.fill(sessionKey, (byte) 0);
        Arrays.fill(webhookKey, (byte) 0);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 HmacPurposeDemo.java
java HmacPurposeDemo
```

Expected stdout (random keys differ each run, but conclusions hold in practice):

```text
session key bytes: 32
session tag bytes: 32
correct purpose: true
wrong purpose: false
wrong key: false
tampered payload: false
```

**Explanation:**

- `new SecureRandom().nextBytes(key)` creates a new 32-byte key array; the program does not print the raw key.
- `tag()` uses `Mac.getInstance("HmacSHA256")` and `SecretKeySpec`. It creates a separate `Mac` instance for the computation; `Mac` is stateful and **a mutable instance should not be shared across threads without coordination**.
- The `wrong purpose` check uses **the same** session key with different purpose data in the HMAC input; `wrong key` uses **a different key**; both show two protection layers that should not be conflated.
- `MessageDigest.isEqual` compares the two tag byte arrays after checking the expected length. Do not use `new String(tag)` or comparisons with content-dependent behavior to verify tags.
- `Arrays.fill` is only best-effort temporary array cleanup and **does not guarantee clearing every copy** the provider/JVM may hold. The demo **does not persist keys across restarts**, manage rotation/key IDs, or perform real session authentication.

For larger applications, `generateKey()` is typically the key management system's responsibility, while business logic receives only the appropriate HMAC operation permissions.

## 8. Java 17+: Deriving Purpose-Scoped Keys with HKDF-SHA256

The following example implements full **HKDF-Extract + HKDF-Expand** with HmacSHA256 per RFC 5869 for illustration. First it verifies **RFC 5869 test vector case 1** using public values; then it generates a random root and salt and derives two 32-byte keys from two distinct `info` values. The example prints neither root, PRK, nor subkeys.

Save **`HkdfPurposeDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class HkdfPurposeDemo {
    static final int HASH_LEN = 32;

    static byte[] hmac(byte[] key, byte[]... inputs)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        for (byte[] input : inputs) mac.update(input);
        return mac.doFinal();
    }

    static byte[] extract(byte[] salt, byte[] ikm)
            throws GeneralSecurityException {
        return hmac(salt == null || salt.length == 0
                ? new byte[HASH_LEN] : salt, ikm);
    }

    static byte[] expand(byte[] prk, byte[] info, int length)
            throws GeneralSecurityException {
        if (length < 1 || length > 255 * HASH_LEN)
            throw new IllegalArgumentException("invalid length");

        byte[] output = new byte[length];
        byte[] previous = new byte[0];
        int offset = 0;
        for (int counter = 1; offset < length; counter++) {
            previous = hmac(prk, previous, info, new byte[]{(byte) counter});
            int count = Math.min(HASH_LEN, length - offset);
            System.arraycopy(previous, 0, output, offset, count);
            offset += count;
        }
        Arrays.fill(previous, (byte) 0);
        return output;
    }

    static byte[] context(String purpose) {
        return ("app=shop|env=prod|alg=HmacSHA256|purpose="
                + purpose + "|version=1").getBytes(StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        byte[] ikm = new byte[22];
        Arrays.fill(ikm, (byte) 0x0b);
        byte[] salt = HexFormat.of().parseHex("000102030405060708090a0b0c");
        byte[] info = HexFormat.of().parseHex("f0f1f2f3f4f5f6f7f8f9");
        byte[] okm = expand(extract(salt, ikm), info, 42);

        String expected =
                "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c"
              + "5db02d56ecc4c5bf34007208d5b887185865";
        System.out.println("RFC 5869 case 1 valid: "
                + expected.equals(HexFormat.of().formatHex(okm)));

        byte[] root = new byte[32];
        byte[] appSalt = new byte[32];
        new SecureRandom().nextBytes(root);
        new SecureRandom().nextBytes(appSalt);
        byte[] prk = extract(appSalt, root);
        byte[] sessionKey = expand(prk, context("session"), 32);
        byte[] webhookKey = expand(prk, context("webhook"), 32);

        System.out.println("derived key bytes: " + sessionKey.length);
        System.out.println("same purpose stable: "
                + MessageDigest.isEqual(sessionKey,
                        expand(prk, context("session"), 32)));
        System.out.println("other purpose differs: "
                + !MessageDigest.isEqual(sessionKey, webhookKey));

        Arrays.fill(root, (byte) 0);
        Arrays.fill(prk, (byte) 0);
        Arrays.fill(sessionKey, (byte) 0);
        Arrays.fill(webhookKey, (byte) 0);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 HkdfPurposeDemo.java
java HkdfPurposeDemo
```

Stdout:

```text
RFC 5869 case 1 valid: true
derived key bytes: 32
same purpose stable: true
other purpose differs: true
```

**Output analysis:**

1. The test vector confirms the example follows the exact order `HKDF-Extract(salt, IKM)` and `HKDF-Expand(PRK, info, L)`, where each Expand block depends on the previous block, `info`, and a 1-byte counter. The public expected value from RFC 5869 is not a production key.
2. The subkeys for `session` and `webhook` are both 32 bytes yet differ because their `info` differs. Given identical root, salt, info, and length, HKDF is deterministic: re-deriving gives the exact same output.
3. Root and salt are randomly generated at runtime; a real application must store/recover **root and salt together with version** by design, otherwise keys generated on subsequent runs will differ.
4. The example only uses fixed code-chosen purposes. In multi-tenant/multi-partner systems, canonicalize and unambiguously encode `info`, and validate the trusted source of each attribute and access permissions. **Never allow self-declared `purpose` or `tenant` to grant signing/verifying rights.**
5. For production use, prefer vetted cryptographic libraries or services implementing HKDF; this example clarifies the RFC structure and checks outputs accurately. Zeroing temporary arrays in the demo is best-effort only and does not turn the Java heap into guaranteed secure memory.

## 9. Real-World Design Scenarios

### 9.1. Webhooks from two different partners

If Partner A and Partner B both send `payment.paid`, create separate keys `partner-A/prod/webhook/v1` and `partner-B/prod/webhook/v1`. When a request arrives, map the partner via endpoint/configuration and pick the scoped key. A valid tag from A **must never** authenticate a message claiming to be B.

If a partner shares an HMAC key with the server, both hold the secret. When origin attribution to a non-shared identity is required, consider digital signatures or an appropriate service authentication mechanism instead of assuming HMAC provides non-repudiation.

### 9.2. Sessions and signed download URLs

One service signs session cookies; another signs document download URLs. The two purposes have different policies: cookies belong to login sessions; URLs must carry expiration, resource, action, and possibly recipient constraints. Use **separate keys** so leaking the signed-URL key does not enable forging sessions. Never grant `K_session` to a service that only needs to verify URLs.

### 9.3. Multi-tenant and microservices

If each tenant requires a distinct trust boundary, consider **per-tenant keys** held by a secret manager, or HKDF with canonicalized context containing tenant ID and purpose. Clearly examine who holds the root: separation via HKDF **does not** reduce the impact of a full root compromise. When strict isolation is required, use independent keys and tenant-scoped IAM restrictions.

### 9.4. Rotating v1 while messages are still valid

Allow the receiver to keep v1 in **verify-only** mode for the designed maximum lifetime; the sender emits only v2. Attach `kid` to the envelope and verify it within scope. After the window closes, remove v1 from the allowlist. If v1 was compromised, evaluate **immediate revocation** and invalidate active messages rather than prioritizing compatibility.

### 9.5. Discovering a key in Git or logs

Simply "deleting the line" is not enough. Treat the secret as compromised: issue a new key, update consumers, revoke the old key, investigate potential forged signing, and record an audit trail. Scrub logs/backups/history as feasible per policy, and review secret scanning/CI controls to prevent recurrence.

## 10. Common Mistakes and Fixes

| Mistake | Risk | Correct Approach |
| --- | --- | --- |
| Hardcoding `"changeit"` as the HMAC key | Anyone with source access can forge MACs | Generate strong random keys and store them in a secret manager |
| Using `Random`/timestamp/password as key | Guessable, low entropy | `SecureRandom`/KMS; if a password must be used, apply an appropriate password KDF |
| Using one key for sessions, webhooks, URLs | Compromising one system affects all purposes | Independent keys or purpose-scoped HKDF, with clear IAM boundaries |
| Only renaming `SESSION_KEY`/`WEBHOOK_KEY` variables with identical bytes | No actual secret separation | Issue distinct keys or derive subkeys with distinct `info` |
| Using hex/Base64 to "hide" a secret | Encoding is trivially decoded | Access control, encryption at rest/secret manager, avoid logging |
| Putting the HKDF root in all microservices | Every service can derive every subkey | Provision only scoped keys, keep the root in a restricted trust zone |
| Homegrown `SHA256(root \|\| purpose)` | Unvetted KDF design without standard proofs | Use RFC-compliant HKDF with unambiguous context |
| Letting the client freely choose `alg`/`kid`/purpose | Confusion/downgrade/wrong secret lookup | Server fixes algorithm, looks up `kid` within trusted scope, checks status |
| Signing serialized JSON while verifying differently re-serialized JSON | HMAC mismatch despite identical meaning | Specify canonical bytes; for raw-body webhooks, verify raw body |
| Verifying every key version indefinitely | Old keys remain lingering weak points | Bounded overlap windows; retire/revoke on schedule or incident |
| Assuming HMAC stops replay | Old valid requests still carry valid tags | Timestamps, nonces/sequences, TTL, and atomic replay cache/logic |
| Assuming `Arrays.fill` guarantees no key remains in RAM | JVM/provider may keep copies | Minimize key lifetime/scope, restrict dumps, prefer non-exportable keys |
| Printing the key to debug verification failures | Exposes the real secret | Log `kid`/version/correlation ID; never log the secret |
| Sharing the same key between test and production | Lower-environment leaks impact production | Separate secrets and separate IAM policies per environment |

## 11. Pre-Deployment HMAC Review Checklist

1. **Key generation:** is the key generated by a CSPRNG/KMS? Are length and entropy sufficient? Are sample secrets, passwords, or hardcoded keys avoided?
2. **Ownership:** are the service/partner/tenant, owner, and single purpose of each key defined? Is least privilege enforced?
3. **Storage:** is the key safely stored/backed up/restored, kept out of source control, logs, heap dumps, or unintended diagnostics?
4. **Domain separation:** are independent keys or HKDF with explicit context used? Is sharing the root or overly broad scope avoided?
5. **Message:** are canonical byte rules explicit? Are all security-relevant fields included in the MAC and is the algorithm pinned?
6. **Verification:** is the key looked up by purpose + tenant + version, tag length validated, safely compared, and invalid keys/failed verifications rejected?
7. **Replay and authorization:** are replay protection and business authorization enforced independently of HMAC?
8. **Rotation:** are `kid`, keyring, active/verify-only/retired lifecycle, emergency compromise revocation, and v1 cleanup schedule in place?
9. **Operations:** are secret scanning, key-free logs, permission audits, and tests for wrong key/wrong purpose/tampered message/expired timestamp active?

## 12. Self-Check Exercises

**Question 1.** Two systems use the same 32-byte HmacSHA256 key under different variable names. Have the keys been separated?  
**Answer:** **No.** Renaming variables does not change key material; independent secret keys or distinct purpose derivations are required.

**Question 2.** An HmacSHA256 key generated with `SecureRandom` is 32 bytes long. Is the full tag 32 bytes long because the key happens to be 32 bytes long?  
**Answer:** The full tag is **32 bytes because of HmacSHA256**, not because the key happens to be 32 bytes long.

**Question 3.** A client sends `kid="admin-prod"`. Should the server automatically read that secret and verify with the admin key?  
**Answer:** **No.** `kid` is untrusted input; lookup must be constrained to the server-determined purpose, tenant, environment, and valid key state.

**Question 4.** An application stores only the derived key `K_webhook`, without the root. Can `K_session` be derived from it if HKDF was used properly?  
**Answer:** Under the expected cryptographic model, **it is infeasible to derive** another key from one subkey. However, **compromising the root** allows deriving all subkeys, so the root requires stronger protection.

**Question 5.** A webhook has a valid tag, but its timestamp is old and its nonce has already been processed. Accept or reject?  
**Answer:** **Reject** per replay-protection policy; a valid MAC alone is not enough to re-accept business processing.

**Question 6.** When rotating the HKDF root, `info` stays the same while a new root is used. Will the subkeys match the old ones?  
**Answer:** **No**, HKDF output depends on root/PRK, salt, info, and length. Versions and transition windows must be managed.

**Question 7.** A 32-byte secret is printed as Base64 into a log. Is that safe because readers cannot see the raw bytes?  
**Answer:** **No.** Base64 decodes directly back to the exact 32 key bytes. The log has leaked the secret.

**Question 8.** Does a valid HMAC from Partner A prove with certainty that the individual Alice at Partner A signed it?  
**Answer:** **No.** Any person or system knowing the shared key can create the MAC; attributing to a specific identity requires appropriate keys and authentication mechanisms.

### Key Takeaway

**Generate keys with a cryptographic random source, keep keys under least privilege, truly separate keys by purpose, bind context in the MACed bytes, manage key IDs and versions, and maintain rotation/revocation procedures.** HMAC-SHA256 is a useful primitive; the complete key management and verification workflow is what determines whether the application truly resists message forgery.
