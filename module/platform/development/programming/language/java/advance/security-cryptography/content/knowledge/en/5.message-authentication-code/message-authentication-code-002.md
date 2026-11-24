# 5.2 HMAC and How It Differs from Hashing Concatenated Keyed Data

## Objectives

After this lesson, you can explain why a **plain hash** and a **message authentication code (MAC)** solve two different problems; describe the HMAC construction and why **HMAC-SHA256 differs from `SHA-256(key || message)`**; recognize the length-extension weakness of naively concatenating a key with data; generate and verify HMACs in Java 17+; test an implementation with official test vectors; and manage keys, message formatting, and replay protection when applying HMAC to APIs.

This topic belongs to **5. Message Authentication Codes** in Java Security/JCA. The focus is on hash-based HMAC, especially `HmacSHA256`. This lesson does not require implementing cryptographic algorithms from scratch or building a full API signing protocol.

## 1. Why Is Hashing Data Alone Not Enough for Authentication?

A cryptographic hash function such as SHA-256 takes bytes `M` and computes `H(M)`. Anyone who knows `M` can compute the same digest themselves. Therefore, if one party transmits both the content and the digest over a channel where an adversary can tamper with data, the adversary can alter the data **and recompute the digest**, causing the `SHA-256` check to still succeed.

A Message Authentication Code (MAC) takes a **secret key K** and a **message M**, and produces a **tag T**. The verifier uses the same key to confirm that the tag corresponds to the message. While the key remains secret and the MAC construction is secure, an attacker who does not know the key cannot easily forge a valid tag for a new message.

| Criterion | `SHA-256(message)` | Homegrown `SHA-256(key \|\| message)` | `HMAC-SHA256(key, message)` |
| --- | --- | --- | --- |
| Uses a secret key | No | Yes | Yes |
| Designed/standardized as a MAC | No | No | Yes (HMAC) |
| Prevents a third party from altering both content and digest | No, unless the digest is authenticated independently | Not guaranteed | Yes, with a strong enough key and proper implementation |
| Susceptible to SHA-256-style **length-extension** | Not a MAC problem | **Yes**, for prefix construction `H(K \|\| M)` | Not vulnerable to that direct length-extension attack |
| Java engine | `MessageDigest` | `MessageDigest` (misused for authentication) | `Mac` |
| Standard name in Java | `SHA-256` | `SHA-256` | `HmacSHA256` |

**Using a key does not automatically turn a hash into a secure MAC.** Formulas like `H(K || M)` and `H(M || K)` look simple, but they do not inherit the security guarantees of a studied MAC construction. Different concatenation styles are vulnerable to different attacks; do not assume all styles suffer from the exact same length-extension attack.

HMAC protects **authenticated integrity and authenticity of a party knowing the key**; it **does not encrypt content**, does not stop anyone from reading plaintext, does not stop valid messages from being replayed, and does not provide non-repudiation like asymmetric digital signatures because both parties share the same key.

## 2. HMAC Construction: Two Keyed Hash Layers

HMAC is specified in [RFC 2104](https://www.rfc-editor.org/rfc/rfc2104) and tested with vectors such as [RFC 4231](https://www.rfc-editor.org/rfc/rfc4231). For a hash function `H`, where `||` denotes **byte-string concatenation** and `⊕` denotes byte-wise XOR, the formula is:

\[
\mathrm{HMAC}(K,M)=H\big((K_0\oplus\mathrm{opad})\parallel H((K_0\oplus\mathrm{ipad})\parallel M)\big)
\]

Where:

- `K` is the secret key; `M` is the message byte sequence.
- `B` is the **block size of the hash function**, not the digest length. For HMAC-SHA256, `B = 64` bytes; the SHA-256 digest is **32 bytes** long.
- If the key is longer than `B`, HMAC first hashes the key with `H`; then appends `0x00` bytes at the end to create `K₀` of exact length `B`. If the key is already shorter than `B`, it is simply zero-padded; a key of exact length `B` needs no padding.
- `ipad` is `B` bytes of `0x36`, and `opad` is `B` bytes of `0x5c`.
- HMAC computes an **inner** hash of `(K₀ ⊕ ipad) || M`, then an **outer** hash of `(K₀ ⊕ opad) || innerDigest`.

Flow summary:

```text
K --[normalize to block size B]--> K0
                 |                    |
                 v                    v
           K0 XOR ipad          K0 XOR opad
                 |                    |
                 v                    |
        hash((K0 XOR ipad) || M)      |
                 |                    |
                 +--------> hash((K0 XOR opad) || innerDigest)
                                        |
                                        v
                                    HMAC tag
```

The full output of HMAC-SHA256 is **32 bytes = 256 bits**. The tag length does not depend on the message length. For display, 32 bytes become **64 hex characters**; hex is an encoding for storage or transmission, not the tag itself.

**Why two layers?** HMAC does not directly output the final state of `H(K || M)` as the tag; the inner hash value is processed through another hash layer with a key transformed by `opad`. An attacker who only knows the outer tag cannot obtain the internal state `H((K₀ ⊕ ipad) || M)` to perform message extension as with `H(K || M)`. HMAC's security guarantees rely on cryptographic assumptions about the hash function and the HMAC design, not merely on key concatenation.

**Do not implement `ipad/opad` yourself in production.** Use `javax.crypto.Mac` and a tested provider implementation to avoid bugs in handling long keys, block padding, hash state, and byte encoding.

## 3. Real Risks of Hashing Key-Concatenated Data

### 3.1 Prefix style: `SHA-256(key || message)`

SHA-256 uses an iterated hash construction whose state can continue processing additional blocks. If a naive protocol defines:

```text
tag = SHA-256(secretKey || message)
```

and an attacker knows `message`, `tag`, and the key length (or guesses candidate lengths), they can carry out a cryptographic **length-extension attack**: computing the tag for an extended byte sequence corresponding to

```text
message || gluePadding(secretKey || message) || attackerSuffix
```

without knowing the bytes of `secretKey`. `gluePadding` is the SHA-256 padding that depends on the **total byte length** of `secretKey || message`, containing the terminator bit and message length per the SHA-256 specification. Whether such a forged payload is accepted by the application parser depends on how the system interprets the bytes; nevertheless, this is a fundamental design flaw of prefix MACs.

In particular, inserting a fixed separator like `SHA-256(secretKey || ":" || message)` **does not turn it into HMAC** and does not generally prevent length-extension attacks.

### 3.2 Suffix style: `SHA-256(message || key)`

With the suffix style, the observed tag is the state after hashing **the key at the end**. Hence you cannot simply apply the same extension operation and append data after `message` while keeping the key at the end. However, this **does not prove** the formula is a secure MAC: its properties, collision risks, and security guarantees still depend on the hash structure and attack model. Do not deploy `hash(message || key)` or custom variants instead of `Mac`.

### 3.3 Why does HMAC exist if SHA-256 is still secure?

A hash function with collision resistance and preimage resistance **does not automatically** create an unforgeable MAC when combined with a key. HMAC was defined specifically to solve the MAC problem, avoiding prefix constructions vulnerable to length extension and providing independent cryptographic analysis. For Java applications, the default choice when you need a MAC from SHA-256 is **`HmacSHA256`**.

## 4. Java 17: HMAC, Key-Concatenated Hashing, and Official Verification

Java JCA/JCE clearly separates the engines:

- `MessageDigest.getInstance("SHA-256")` creates an **unkeyed hash function**.
- `Mac.getInstance("HmacSHA256")` creates a **keyed HMAC**; it must be initialized with `mac.init(key)` before calling `update` or `doFinal`.
- `SecretKeySpec(keyBytes, "HmacSHA256")` wraps key bytes suitable for `Mac` in examples; it is not a key generation or storage mechanism.
- `HexFormat` (Java 17+) converts `byte[]` to hex and parses hex to compare against test vectors.

The program below uses **public test keys from RFC 4231**, intended only for learning and testing. Never use these keys in a real service.

Create the file **`HmacVsConcatDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacVsConcatDemo {
    private static final String ALGORITHM = "HmacSHA256";

    public static void main(String[] args) throws Exception {
        byte[] key = new byte[20];
        Arrays.fill(key, (byte) 0x0b);
        byte[] message = "Hi There".getBytes(StandardCharsets.UTF_8);

        byte[] tag = hmac(key, message);
        byte[] rfcExpected = HexFormat.of().parseHex(
                "b0344c61d8db38535ca8afceaf0bf12b"
                        + "881dc200c9833da726e9376c2e32cff7");
        System.out.println("HMAC-SHA256: " + HexFormat.of().formatHex(tag));
        System.out.println("Matches RFC 4231 case 1: "
                + MessageDigest.isEqual(tag, rfcExpected));

        byte[] naive = prefixedSha256(key, message);
        System.out.println("SHA-256(key || message): "
                + HexFormat.of().formatHex(naive));
        System.out.println("HMAC equals naive hash: "
                + MessageDigest.isEqual(tag, naive));

        System.out.println("Verify original: " + verify(key, message, tag));
        System.out.println("Verify modified: " + verify(
                key, "Hi There!".getBytes(StandardCharsets.UTF_8), tag));

        Mac streaming = newMac(key);
        streaming.update("Hi ".getBytes(StandardCharsets.UTF_8));
        streaming.update("There".getBytes(StandardCharsets.UTF_8));
        System.out.println("Streaming equals one-shot: "
                + MessageDigest.isEqual(tag, streaming.doFinal()));

        byte[] key2 = "Jefe".getBytes(StandardCharsets.US_ASCII);
        byte[] message2 = "what do ya want for nothing?"
                .getBytes(StandardCharsets.US_ASCII);
        System.out.println("RFC 4231 case 2: "
                + HexFormat.of().formatHex(hmac(key2, message2)));
    }

    private static Mac newMac(byte[] key) throws Exception {
        Mac mac = Mac.getInstance(ALGORITHM);
        mac.init(new SecretKeySpec(key, ALGORITHM));
        return mac;
    }

    private static byte[] hmac(byte[] key, byte[] message)
            throws Exception {
        return newMac(key).doFinal(message);
    }

    private static boolean verify(byte[] key, byte[] message, byte[] suppliedTag)
            throws Exception {
        byte[] expectedTag = hmac(key, message);
        return MessageDigest.isEqual(expectedTag, suppliedTag);
    }

    private static byte[] prefixedSha256(byte[] key, byte[] message)
            throws NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        digest.update(key);
        digest.update(message);
        return digest.digest();
    }
}
```

Compile and run with Java 17 or later:

```bash
javac --release 17 HmacVsConcatDemo.java
java HmacVsConcatDemo
```

**Stdout when running on a JDK with standard-compliant `HmacSHA256` and `SHA-256` implementations** (verified when running the example):

```text
HMAC-SHA256: b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7
Matches RFC 4231 case 1: true
SHA-256(key || message): 9000e06f7d262eac9b27728faaaee3a54d901591a9262c1af171f25fe97c7717
HMAC equals naive hash: false
Verify original: true
Verify modified: false
Streaming equals one-shot: true
RFC 4231 case 2: 5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843
```

**Key takeaways from the output:**

1. Data `"Hi There"` with the 20-byte `0x0b` key produces HMAC-SHA256 matching **RFC 4231 test case 1**. Similarly, ASCII key `Jefe` and ASCII message `what do ya want for nothing?` match **test case 2**.
2. `SHA-256(key || message)` also produces a 64-character hex string, yet it **differs from HMAC-SHA256**. Having the same output length **does not** mean the same algorithm or the same security.
3. Verifying the tag with the same key/data returns `true`; changing **a single byte** of the message to `"Hi There!"` while keeping the old tag returns `false`.
4. Calling `Mac.update` with chunks `"Hi "` and `"There"` followed by `doFinal()` produces the same tag as calling `doFinal(message)` once, because the final byte sequence is identical.

`prefixedSha256` is only intended to **illustrate a design that should not be used as a MAC**; do not use that function to sign requests, login sessions, or sensitive data.

In the example, `newMac`/`hmac` declare `throws Exception` to keep the focus on the algorithm. In real applications, handle exceptions such as `NoSuchAlgorithmException` and `InvalidKeyException` explicitly according to system policy. When a provider lacks `HmacSHA256`, this part of the program cannot run properly; that is a configuration error to resolve, not a signal to fall back to `SHA-256(key || message)`.

## 5. Using `Mac` Properly in Java

### 5.1 Initializing and updating in chunks

Typical API:

```java
Mac mac = Mac.getInstance("HmacSHA256");
mac.init(new SecretKeySpec(secretKeyBytes, "HmacSHA256"));
mac.update(part1);
mac.update(part2);
byte[] tag = mac.doFinal();
```

This snippet is **illustrative inside a method**: `part1`, `part2`, and `secretKeyBytes` are provided `byte[]` values, the method must handle security exceptions, and `javax.crypto.Mac` and `javax.crypto.spec.SecretKeySpec` must be imported. `doFinal()` finishes the computation and resets the object to a reusable state with the initialized key. Do not call `doFinal()` between two chunks of **the same message**, as doing so computes two separate tags. Do not share a `Mac` instance being `update`d across multiple threads: it is a stateful engine; use a separate instance per operation when concurrency is needed.

Streaming helps process large request bodies/files without loading everything into memory; `update(buffer, 0, count)` must use the exact number of bytes actually read in each iteration. HMAC is computed over **exact bytes**, so changing encoding or chunk order changes the tag if it alters the input bytes.

### 5.2 Generating and protecting real keys

Do not use predictable strings like `"secret123"` or RFC test keys. An example of **generating a 32-byte (256-bit) random key** in Java is:

```java
byte[] secretKeyBytes = new byte[32];
new SecureRandom().nextBytes(secretKeyBytes);
```

This snippet requires importing `java.security.SecureRandom`. Generate the key **once per policy**, store it in a secret manager/KMS/HSM or controlled keystore, and distribute it securely to authorized verifying parties. Do not generate a new key before **each verification**, because then it will no longer match the key used by the tag creator.

Use keys with entropy appropriate to security requirements, e.g., **at least 256 random bits** in new designs with HMAC-SHA256. HMAC does not mandate a 32-byte key in every protocol; strength depends on entropy and key management. For HMAC-SHA256, keys longer than the SHA-256 block size (64 bytes) are normalized by hashing before use; arbitrarily lengthening a key does not automatically increase security.

In production: never log keys or full secret tags; never hardcode keys in source code; enforce access control, rotation, usage scope, and `keyId` versioning. You should **separate keys by purpose** (for example, webhooks and session tokens use different keys), by send/receive direction when the protocol requires it, and maintain a revocation procedure if a key leaks. `SecretKeySpec` only wraps key bytes in the program; it does not protect the key from anyone who can read memory.

### 5.3 Safe tag verification

The receiver must recompute the HMAC from the **exact received content bytes** and the appropriate key, then compare tags as bytes:

```java
byte[] expectedTag = hmac(secretKeyBytes, receivedMessageBytes);
boolean accepted = MessageDigest.isEqual(expectedTag, receivedTagBytes);
```

This snippet is illustrative inside a class containing the `hmac` method from the complete example, importing `java.security.MessageDigest`. `MessageDigest.isEqual` compares the byte values of two digests/tags and is designed to limit timing leaks compared to naive byte-by-byte comparison; to achieve appropriate comparison-time behavior, **validate the format and use a fixed-length tag per protocol**. With full HMAC-SHA256, the expected tag is **32 bytes** long. Do not accept empty tags, arbitrary lengths, or compare only the first few bytes without an explicit truncation design.

Do not use:

```java
// WRONG: compares references of two byte arrays, not their contents.
boolean equal = expectedTag == receivedTagBytes;
```

Do not compare hex strings using custom logic that can stop at the first differing character and then try to treat it as "constant time"; decode the transmitted tag (e.g., hex/Base64) into properly formatted bytes, validate the protocol-mandated length, and compare bytes. If the protocol allows **truncated tags**, the truncation length and security policy must be predetermined, agreed upon by both sides, and never left up to the sender.

**Do not return distinct detailed messages for "wrong tag" versus "wrong key" if that creates a useful oracle for an adversary.** Record detailed causes in a controlled internal logging channel; the API can return a uniform authentication error response.

## 6. Checking Provider Support for HMAC at Runtime

In Java, HMAC belongs to the **`Mac`** engine, not the `MessageDigest` engine. The two standard names are related but not interchangeable:

- `Mac.getInstance("HmacSHA256")`: Java's name for SHA-256 HMAC.
- `MessageDigest.getInstance("SHA-256")`: name for the unkeyed SHA-256 digest.
- `Mac.getInstance("SHA-256")`: not the standard call to request HMAC.

To discover which `Mac` algorithm names the runtime registers, the following snippet belongs **inside a Java method** importing `java.security.Security` and `java.util.Set`:

```java
Set<String> names = Security.getAlgorithms("Mac");
names.stream().sorted(String.CASE_INSENSITIVE_ORDER)
        .forEach(System.out::println);
```

To look up by a specific provider, place the following in a method importing `java.security.Provider`, `java.security.Security`, and `javax.crypto.Mac`, handling `NoSuchAlgorithmException`:

```java
for (Provider provider : Security.getProviders()) {
    Provider.Service service = provider.getService("Mac", "HmacSHA256");
    if (service != null) {
        System.out.println(provider.getName() + ": " + service.getAlgorithm());
    }
}
```

`provider.getService` indicates that a provider **advertises** a service matching the engine/name (or alias). To know whether it works with a real key, instantiate `Mac.getInstance("HmacSHA256", provider)`, `init` with a policy-compliant key, and test `doFinal` with a vector. `Security.getAlgorithms("Mac")` does not guarantee every provider supports every listed name. Do not hardcode `SunJCE` or assume provider names/aliases are identical across all JDKs, FIPS modes, hardware devices, or container environments.

Errors worth distinguishing:

| Error/Symptom | Meaning and Handling |
| --- | --- |
| `NoSuchAlgorithmException` from `Mac.getInstance("HmacSHA256")` | No implementation found via provider selection; verify standard name and active providers |
| `NoSuchAlgorithmException` when specifying a provider | The specified provider does not provide that algorithm name; inspect `getService("Mac", "HmacSHA256")` and verify the factory |
| `InvalidKeyException` from `mac.init(key)` | Invalid key or rejected by provider; check key type, length, policy, HSM/keystore permissions |
| `IllegalStateException` on `update`/`doFinal` before `init` | Engine not initialized with a key; always call `init` before processing data |
| HMAC mismatch even though algorithm is supported | Differences in input bytes/charset, key version, `keyId`, canonicalization, field order, tag encoding, or tag truncation |
| The same old tag still works to call the API | HMAC does not prevent replay on its own; include timestamp/nonce/counter in authenticated data and check for reuse |

When HMAC is a mandatory protocol requirement, **fail fast** if the provider or key is unavailable; never fall back automatically to `SHA-256(key || message)` or pick a different MAC algorithm that both parties have not explicitly negotiated.

## 7. Designing Messages Protected by HMAC

A tag is meaningful only when both sides agree on **the exact bytes signed** and how they are interpreted. Application-level bugs can weaken the system even when `Mac` computes correctly.

### 7.1 Do not concatenate multiple fields ambiguously

If you sign `HMAC(K, fieldA || fieldB)` without encoding boundaries, the pairs `("ab", "c")` and `("a", "bc")` both yield `"abc"`, making a tag valid for one combination valid for the other as well. Use a binary format with **per-field lengths**, canonical serialization, or an unambiguous structured encoding. Do not join strings with a delimiter that input might contain unless an exact escaping mechanism is in place.

### 7.2 Cover enough context requiring authentication

If a tag authenticates an API request, the protocol may need to cover `method`, `path`, a defined set of headers, timestamp, nonce/counter, protocol version, and **the exact body bytes** (or a digest of the body with a specified algorithm) in an unambiguous encoding. If only the body is signed without the method or destination, a valid tag can be misused out of context.

The protocol must also specify how query encoding, normalized paths, Unicode, JSON, and line endings are handled. Sender and receiver must compute HMAC over **the exact same byte sequence**, independent of arbitrary library serialization field ordering.

### 7.3 HMAC does not prevent replay by itself

An adversary can record both the message **and the valid tag**, then resend the exact pair. HMAC verification still returns `true`. To limit replay, validate a timestamp or nonce/sequence **inside the HMAC-protected data**, enforce time bounds, keep synchronized clocks, and **persist the state of used nonces/counters** within a defined window if duplicate requests must be rejected.

### 7.4 Verification rules and key governance

The receiver selects the right key by configured `keyId`/version, never by a key supplied by the sender. Avoid letting the sender choose weak algorithms; use an allowlist of algorithms and authenticate the algorithm/version context as well if the protocol supports multiple choices. Rotation requires a controlled overlap window for old keys, plus a revocation mechanism upon compromise.

In a system where multiple parties share the same key, HMAC confirms that the tag was produced **by someone who knows the key**, not that a single specific individual signed it; thus it cannot replace digital signatures where non-repudiation is required.

## 8. Common Mistakes to Avoid

| Wrong Practice or Misconception | Correct Practice |
| --- | --- |
| "`SHA-256(K \|\| M)` is also HMAC because it has a key" | Use `Mac` with `HmacSHA256`; avoid prefix keyed-hash length-extension |
| "`SHA-256(M \|\| K)` is definitely secure since it avoids prefix length-extension" | Do not deduce security from resisting one attack; use a standardized MAC |
| Comparing `HMAC-SHA256` with `SHA-256(K \|\| M)` output and blaming Java | They are two different formulas; HMAC has inner/outer pads and two hash passes |
| Calling Java `String.getBytes()` without specifying charset | Use `StandardCharsets.UTF_8` and define the byte schema on both sides |
| Using `new String(tagBytes)` to store a tag | Use hex/Base64 with standard encoding; keep the tag as bytes when comparing |
| Using `==` to compare two `byte[]` arrays | Compare contents with `MessageDigest.isEqual`, validating tag format/length |
| Deriving an HMAC key from a guessable password | Use a high-entropy random key and key management; if the input is a password, use a purpose-built KDF |
| Allowing repeated transactions because HMAC verified | Bind and check nonce/timestamp/counter; HMAC does not prevent replay |
| Sharing a mutable `Mac` instance across concurrent requests | Create a new instance or isolate state per operation |
| Logging keys, using RFC keys in production | Use a secret manager/KMS/HSM, access controls, and rotation |
| Using HMAC as a password-storage mechanism | HMAC is a MAC for messages; password storage requires proper password hashing like Argon2id/scrypt/bcrypt/PBKDF2 |

## 9. Self-Check

1. From the prefix SHA-256 structure `H(K || M)`, explain why an adversary knowing the tag and key length can continue computing the digest for extended data, whereas HMAC does not directly expose the inner hash state.
2. Run `HmacVsConcatDemo`. Why do `prefixedSha256` and `hmac` outputs both have 32 bytes yet differ? What bugs do the two RFC 4231 test vectors help catch?
3. Change just one byte of `"Hi There"` while keeping the old tag. Why does `verify` return `false`? If **both the key and tag** are changed, what happens between the two parties?
4. Explain the `("ab", "c")` and `("a", "bc")` example. Propose a clear encoding format so HMAC over two fields has unambiguous boundaries.
5. Design a webhook verification workflow using HMAC-SHA256: which fields must be covered, how is `keyId` managed, what are the timestamp limits, nonce tracking, and rotation handling?
6. Inspect the provider list in your Java environment; distinguish between "a provider advertises `Mac.HmacSHA256`" and "`Mac` initializes and passes the test vector."

## References

- [RFC 2104 — HMAC: Keyed-Hashing for Message Authentication](https://www.rfc-editor.org/rfc/rfc2104): HMAC formula, key handling, `ipad` and `opad`.
- [RFC 4231 — Identifiers and Test Vectors for HMAC-SHA-224, HMAC-SHA-256, HMAC-SHA-384, and HMAC-SHA-512](https://www.rfc-editor.org/rfc/rfc4231): HMAC-SHA256 test vectors case 1 and 2.
- [Java SE 17 — `Mac`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html): MAC engine, `init`, `update`, `doFinal`.
- [Java SE 17 — `SecretKeySpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/SecretKeySpec.html): wrapping key bytes for `Mac`.
- [Java SE 17 — `MessageDigest`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): SHA-256 hashing and byte comparison via `isEqual`.
- [Java SE 17 — Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): standardized names `HmacSHA256` and `SHA-256`.
