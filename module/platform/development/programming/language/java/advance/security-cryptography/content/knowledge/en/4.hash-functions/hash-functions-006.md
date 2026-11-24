# 4.6. Comparing Digests with `MessageDigest.isEqual` and the Scope of API Guarantees

## 1. Context: Comparing Hash Values Can Have Security Implications

A digest (hash value) is a byte array produced from a message by a hash algorithm—for example, `SHA-256` returns **32 bytes (256 bits)**. In Java, we frequently need to compare:

- A recomputed digest from data against a stored expected digest to detect data tampering.
- A received HMAC value against an HMAC computed by the verifier using a **secret key**.
- Cryptographic values whose verification timing could be measured externally, where leaking internal mismatch details must be minimized.

If a comparison exits immediately upon encountering the first differing byte, execution time can depend on the position of that first differing byte. `java.security.MessageDigest.isEqual` is an API for comparing two byte arrays that has **properties designed to limit this kind of leak**, within the scope documented by Java.

Two questions must be distinguished: **are two byte arrays equal?** and **is the data source trustworthy?** `isEqual` only answers the first question; the second requires an appropriate algorithm, expected-value source, and security policy.

## 2. Signature, Inputs, and Return Value

API:

```java
public static boolean isEqual(byte[] digesta, byte[] digestb)
```

This is a **static method**: call `MessageDigest.isEqual(expected, actual)` without creating a `MessageDigest` object. It **does not compute a digest itself**, does not invoke SHA-256/HMAC, and does not verify the algorithm/provider used to produce the array.

For **two non-null byte arrays**:

- Returns `true` if their lengths are equal and every byte at the same index matches.
- Returns `false` if their lengths differ or at least one byte differs.
- Does not automatically convert hex/Base64 to bytes, skip whitespace, normalize Unicode, or allow a matching prefix to count as the full digest.
- Equal digests are not mathematical proof that two **original messages** are identical: any finite-output hash function always allows collisions; the difficulty of finding a collision depends on the hash algorithm.

**Do not use `==` or `byte[].equals` to check the contents of two digests.** For arrays, both perform reference comparison; two distinct array objects holding the exact same 32 SHA-256 bytes will be treated as unequal by `==`.

Minimal example (snippet placed inside a program that imports `MessageDigest` and `StandardCharsets`):

```java
byte[] a = MessageDigest.getInstance("SHA-256")
        .digest("hello".getBytes(StandardCharsets.UTF_8));
byte[] b = MessageDigest.getInstance("SHA-256")
        .digest("hello".getBytes(StandardCharsets.UTF_8));
boolean equal = MessageDigest.isEqual(a, b); // true
```

Here `MessageDigest.digest` performs hashing, while `MessageDigest.isEqual` performs only comparison. Java does not track the origin, algorithm, or cryptographic meaning of each byte array.

## 3. Timing Side-Channels: Why Ordinary Comparison Is Not Enough

Consider the following custom code:

```java
// Example for ANALYSIS only; do not use for comparing cryptographic data.
static boolean earlyExit(byte[] a, byte[] b) {
    if (a.length != b.length) return false;
    for (int i = 0; i < a.length; i++) {
        if (a[i] != b[i]) return false;
    }
    return true;
}
```

For two arrays of equal length, a mismatch at the first byte terminates the loop immediately; a mismatch at the last byte makes the loop traverse nearly the entire array. In a concrete protocol, an adversary capable of sending many trials and measuring latency might analyze this correlation. Practical exploitability depends on network jitter, access level, protocol design, machine speed, and many factors; a few fast/slow measurements **do not** by themselves prove a vulnerability.

Comparing common approaches:

| Approach | Checks byte contents? | Suitable for comparing MAC/digest when timing leaks must be mitigated? |
| --- | --- | --- |
| `a == b` | No, checks reference | No |
| `a.equals(b)` on `byte[]` | No, arrays inherit `Object.equals` | No |
| `Arrays.equals(a, b)` | Yes | No timing contract for cryptographic goals; has early-exit paths |
| `String.equals` on hex/Base64 strings | Compares characters | No timing guarantee for secret data |
| `MessageDigest.isEqual(a, b)` | Yes | Designed to reduce leaking mismatch position, within the API's scope |

`Arrays.equals` is usually the right choice for byte arrays that are **not timing-sensitive**. For digests/tags that must be compared without leaking the mismatching byte position, prefer the dedicated API `MessageDigest.isEqual`.

**Do not convert raw digest bytes into a `String` using UTF-8 and compare strings.** Digests are arbitrary bytes, not guaranteed to be valid UTF-8. If a protocol transmits digests in Base64/hex, strictly decode them into `byte[]` before comparing.

## 4. How Far Does `isEqual`'s "Constant-Time" Guarantee Go?

### 4.1. What Java Documents

Java SE 17 documentation for `isEqual` states in its **Implementation Note** that all bytes of `digesta` are examined during comparison and computation time is designed to depend on **the length of `digesta`**, rather than on the contents of the two arrays or the length of `digestb`. Newer JDK docs, such as Java SE 24, explicitly clarify the exception when `digestb` is `null` or has **0-byte** length.

Therefore, for normal inputs of **two non-null, non-empty arrays**, place the *fixed-length expected* digest/tag as the first argument: `MessageDigest.isEqual(expectedTag, receivedTag)`. For untruncated HmacSHA256, the expected tag is 32 bytes.

When comparing in that order, the logic does not need to exit immediately at the first mismatching byte. This is **an algorithmic property of the comparison**, not proof that every execution path takes identical wall-clock time.

### 4.2. Important Exceptions and Limitations

1. **The first argument can vary in length.** The Implementation Note permits timing to depend on `digesta.length`. If this length is controlled by an untrusted party, do not infer length-independent timing across arbitrary input lengths.
2. **`null` and empty arrays are handled specially.** Certain OpenJDK paths take a fast-path when `digesta == digestb`, when either array is `null`, or when `digestb.length == 0`. Thus, do not claim "every case iterates through all bytes." The API is not a security contract allowing `null`/empty to be treated as valid tags.
3. **Same-reference case:** OpenJDK may return `true` immediately when both parameters point to the same byte array. Do not use aliases/same-reference inputs to benchmark timing properties; in real verification, the expected tag is computed independently from the received data.
4. **Tag length is not necessarily secret.** An application can reject wrong-length tags early because the standard format mandates 32 bytes. If the length itself is secret information, analyze the broader design rather than expecting `isEqual` to hide it.
5. **Surrounding steps still have their own timing:** request parsing, authorization checks, Base64 decoding, SHA/HMAC computation, DB reads, JSON errors, exceptions, and HTTP responses all lie outside `isEqual`'s timing contract.
6. **VM and hardware introduce noise:** JIT compilation, garbage collection, CPU caches, scheduling, compiler optimizations, and networking cause observed wall-clock timings to vary. "Constant-time" in the docs does not mean identical nanoseconds in every environment.
7. **No security guarantee if the algorithm or expected source is wrong.** Comparing an unkeyed SHA-256 against a client-supplied digest does not turn it into authentication; using the right API cannot fix a broken cryptographic design.

State table to avoid confusion:

| Two arguments | Expected logical result | Security notes |
| --- | --- | --- |
| Non-null, equal length and equal bytes | `true` | Standard content equality |
| Non-null, equal length but at least one differing byte | `false` | Avoids writing an early-exit loop yourself |
| Non-null, differing lengths | `false` | Do not accept truncated tags if the protocol requires full length |
| Same byte array reference | `true` | Has a fast-path in OpenJDK; do not use for timing tests |
| `null` or empty tag | Caller should **reject upfront** | Do not rely on implementation behavior for boundary cases |

## 5. Standalone Java 17+ Example: SHA-256 and HMAC Verification

The following program illustrates two distinct purposes:

- **SHA-256:** comparing digests of the same message, a different message, and a truncated digest.
- **HmacSHA256:** generating a random key for the demo; computing a tag with `Mac` and verifying with `MessageDigest.isEqual`; altering the message, altering the tag, or omitting the tag are all rejected.

Create the file `DigestCompareDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Arrays;
import javax.crypto.KeyGenerator;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

public class DigestCompareDemo {
    private static byte[] utf8(String text) {
        return text.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] sha256(byte[] data) throws GeneralSecurityException {
        return MessageDigest.getInstance("SHA-256").digest(data);
    }

    private static byte[] hmacSha256(byte[] data, SecretKey key)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(key);
        return mac.doFinal(data);
    }

    private static boolean verifyHmac(byte[] data, byte[] suppliedTag,
            SecretKey key) throws GeneralSecurityException {
        byte[] expectedTag = hmacSha256(data, key);
        if (suppliedTag == null || suppliedTag.length != expectedTag.length) {
            return false;
        }
        return MessageDigest.isEqual(expectedTag, suppliedTag);
    }

    public static void main(String[] args) throws Exception {
        byte[] original = utf8("message=v1");
        byte[] modified = utf8("message=v2");

        byte[] digestA = sha256(original);
        byte[] digestBCopy = sha256(original);
        byte[] digestDifferent = sha256(modified);

        System.out.println("SHA-256 length: " + digestA.length);
        System.out.println("Same message: " +
                MessageDigest.isEqual(digestA, digestBCopy));
        System.out.println("Different message: " +
                MessageDigest.isEqual(digestA, digestDifferent));
        System.out.println("Short digest: " +
                MessageDigest.isEqual(digestA,
                        Arrays.copyOf(digestBCopy, digestBCopy.length - 1)));

        KeyGenerator generator = KeyGenerator.getInstance("HmacSHA256");
        generator.init(256);
        SecretKey key = generator.generateKey();
        byte[] tag = hmacSha256(original, key);
        byte[] tamperedTag = tag.clone();
        tamperedTag[0] ^= 1;

        System.out.println("HMAC valid: " + verifyHmac(original, tag, key));
        System.out.println("HMAC changed message: " +
                verifyHmac(modified, tag, key));
        System.out.println("HMAC changed tag: " +
                verifyHmac(original, tamperedTag, key));
        System.out.println("HMAC missing tag: " +
                verifyHmac(original, null, key));
    }
}
```

Compile and run with Java 17 or later:

```bash
javac DigestCompareDemo.java
java DigestCompareDemo
```

Exact stdout (even though the key and tag are randomly generated on each run):

```text
SHA-256 length: 32
Same message: true
Different message: false
Short digest: false
HMAC valid: true
HMAC changed message: false
HMAC changed tag: false
HMAC missing tag: false
```

**Step-by-step explanation:**

1. Hashing `message=v1` twice creates two separate arrays with identical bytes. `MessageDigest.isEqual(digestA, digestBCopy)` returns `true`; reference comparison `digestA == digestBCopy` would return `false`.
2. `message=v2` differs from the original message and thus produces a different digest in the example. Truncating one byte reduces the length to 31 bytes, which also yields `false`.
3. `KeyGenerator.getInstance("HmacSHA256")` creates a **secret key for illustration**, avoiding hardcoded keys in source code. Real systems must manage keys via a keystore/KMS or equivalent mechanism.
4. `Mac.getInstance("HmacSHA256")` and `mac.init(key)` compute a tag from the key and message bytes. The verifier recomputes `expectedTag` from the *same key* and *same message bytes*.
5. `verifyHmac` rejects missing/wrong-length tags per the **full 32-byte** contract, then calls `MessageDigest.isEqual(expectedTag, suppliedTag)`. The expected tag goes on the left and is computed independently.
6. Modifying message bytes or tag bytes causes verification to fail; null is also rejected. This illustrates the behavior of the sample system, not a proof that no attacks exist.

**Demo scope:** the program generates a fresh key on every run and performs both tagging and verification in the same process. To verify a tag created by another application, both parties must share the same securely distributed key and agree on the byte format. Never generate a new random key every time you verify a received tag.

## 6. Plain Digests and MACs: Same `isEqual`, Different Guarantees

### 6.1. SHA-256 Only Checks Digest Equality

If you have a file's SHA-256 from a **trusted source**, recomputing the digest and comparing detects data alteration. This is integrity verification under the condition that **the expected value is protected**.

If an attacker can alter both the file **and** the accompanying digest, they simply recompute SHA-256. The comparison returns `true` even though the data is no longer trustworthy. `isEqual` creates neither secrecy nor authority.

### 6.2. HMAC Authenticates Integrity and Possession of the Key

HMAC takes a secret key and a message as inputs. The verifier holds the valid key, computes the expected tag itself, and compares it against the received tag. Under HMAC's security assumptions and proper key management, someone without the key cannot arbitrarily alter the message and forge a valid tag.

```text
SENDER                               RECEIVER
message bytes                        message bytes
     |                                    |
key + Mac(HmacSHA256)          key + Mac(HmacSHA256)
     |                                    |
     v                                    v
receivedTag  ---------------->      expectedTag
                                         |
                         MessageDigest.isEqual(
                             expectedTag, receivedTag)
                                         |
                                   true / false
```

This diagram does not depict **key transport**: the key must be securely pre-shared or retrieved via a key management system. HMAC does not encrypt content, does not prevent replay if the protocol lacks nonces/timestamps/messageIds, and does not check authorization on its own. Important security metadata must be included in the authenticated message, and appropriate server policies enforced.

### 6.3. Do Not Apply Directly to Passwords or Digital Signatures

- **Passwords:** Storing `SHA-256(password)` and calling `isEqual` does not resist offline password cracking if the database leaks. Use a dedicated salted, cost-tuned password-hashing/KDF function (Argon2id, scrypt, bcrypt, or PBKDF2 per system requirements) and the verification function of your chosen library.
- **Digital signatures:** To verify a signature from a private-key holder, use `java.security.Signature.verify` with the appropriate public key, algorithm, and policy. Comparing two digests with `isEqual` does not replace a digital signature.
- **Content confidentiality:** `isEqual` does not encrypt data. To protect both confidentiality and integrity, use properly designed authenticated encryption such as AES-GCM.

## 7. Organizing Verification in Production

1. **Specify byte standards:** algorithm name, UTF-8, field order, canonicalization, version number, Base64/hex format, and exactly what is fed into HMAC. JSON can have the same meaning yet differ in whitespace/field ordering; if the bytes differ, the MAC will differ.
2. **Bound input data:** validate request size, version, syntax, and tag length **before** processing large payloads. If full HmacSHA256 is required, reject 31-byte tags or empty values. Never pad with zero bytes or truncate tags to make them match.
3. **Fetch keys from a trusted source:** use a verified `keyId`, tenant isolation, rotation, and keep keys separate from ciphertext/tags. Never log or hardcode production keys.
4. **Compute the expected tag on the server:** use `Mac` over the same canonicalized message. `Mac` instances are stateful, so avoid sharing an actively updating instance across threads without synchronization.
5. **Compare bytes, not hex strings:** strictly decode the tag, confirm its length, then call `MessageDigest.isEqual(expectedTag, receivedTag)`. When stricter timing-channel protection is required, evaluate the entire request path, including parsing and error responses; do not treat the comparison step alone as sufficient.
6. **Check business logic and replay:** a valid MAC can still be an old message replayed. When required, include authenticated timestamp/nonce/messageId in the protocol, track one-time state, and enforce expiration.

Regarding hex/Base64 strings: `Base64` only encodes byte representation; it does not encrypt secrets. For binary digests, never use `new String(digestBytes)` or `digestBytes.toString()` for checking. Decoders must be strict on invalid characters, malformed padding, or out-of-range bytes; do not silently accept multiple decoding variants.

### On Truncated MACs

Some standard protocols specify truncated HMAC tags under a fixed-length policy. Truncation changes the difficulty of forgery; never let the client choose how many bytes to keep, and never accept a "matching prefix" if the protocol demands a full tag. The program example uses a **full 32-byte HmacSHA256 tag**, so checking `suppliedTag.length != expectedTag.length` is intentional.

## 8. Guarantee Scope Checklist Table

| Statement | True or False? |
| --- | --- |
| `MessageDigest.isEqual` computes SHA-256 for us | **False**: it only compares two `byte[]` arrays. |
| Two arrays of the same length and identical bytes at every index are considered equal | **True** for valid digest inputs. |
| The API has timing properties aimed at avoiding leaking the mismatching byte position | **True**, within the scope and exceptions stated in the Implementation Note. |
| **Every** call takes identical time, including `null`/empty/same-reference | **False**; boundary paths exist and timing properties only support conditional reasoning. |
| An entire HTTP endpoint becomes constant-time just by using `isEqual` | **False**: decoding, I/O, hashing, authentication, JIT, and networking are outside its scope. |
| Comparing a plain SHA-256 authenticates the sender | **False** unless the expected digest is protected; an attacker can recompute it. |
| Comparing HMAC properly with the API helps reduce timing leaks at the tag-comparison step | **True**, provided HMAC uses a secure secret key and a sound protocol. |
| Equal digests strictly prove the two original messages are identical | **False** mathematically, because collisions can occur. |
| `isEqual` stops replay, slows password guessing, encrypts content, or verifies digital signatures | **False**; each requires its own mechanism. |

## 9. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `==` or `byte[].equals` on digests | Two arrays with identical contents but different object references compare unequal | Use `MessageDigest.isEqual`; `Arrays.equals` if timing properties are unneeded. |
| Using `Arrays.equals` or an early-`return` loop for HMAC | No guarantee against timing dependence on the mismatching byte position | `MessageDigest.isEqual` with a fixed expected tag. |
| Using `String.equals` on hex/Base64 | String comparison risks inconsistent encoding handling and lacks a timing contract | Strictly decode into `byte[]`. |
| Treating "constant-time" as constant HTTP response latency | Ignores parsing, I/O, errors, and length variations | Define the threat model and evaluate the full pipeline. |
| Trusting `null`, empty, or wrong-length tags | Opens out-of-contract execution paths | Reject per protocol format upfront. |
| Client sends both message and plain SHA digest; server treats it as authenticated | Attacker can send a forged message with a self-computed digest | HMAC with a server key or digital signatures. |
| Both sides hash JSON/Unicode with different bytes | Valid MAC from sender still fails verification at receiver | Standardize canonical byte representation. |
| Storing `SHA-256(password)` instead of a password KDF | Vulnerable to offline cracking for weak passwords | Salted password hash/KDF with safe cost settings. |
| Comparing tags without checking authorization or replay | MAC may be valid for the wrong context or an old request | Cover metadata in the MAC and enforce business, replay, and `keyId` checks. |

## 10. Self-Check Exercises

1. Two `byte[]` arrays with different references hold the exact same 32 bytes: what do `a == b`, `Arrays.equals(a, b)`, and `MessageDigest.isEqual(a, b)` return?
2. Why does comparing `SHA-256(file)` against a client-supplied checksum not prove the file is trustworthy on its own?
3. When comparing HMACs, why should the **recomputed** expected tag be passed as the first argument?
4. What is not guaranteed when the received tag is `null`, empty, or has the wrong length?
5. Why can processing times in an HTTP endpoint still vary even when `MessageDigest.isEqual` is used properly?
6. Among plain SHA-256, HmacSHA256, password hashing, and digital signatures, which requires a shared secret key and which uses a public key?
7. If an HMAC tag is valid yet the request is sent a second time, does `isEqual` detect the replay by itself?

**Practice:** modify the first or last byte of a digest/tag in the example and observe the boolean output; compare with `Arrays.equals` for **result semantics**, without using a handful of timing measurements to claim timing security. Add tests for modified payload, a 31-byte short tag, and duplicate `messageId` requests according to your application's policy.

## 11. Official Documentation

- [Java SE 17: MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html) — `isEqual`, `digest`, and Implementation Note.
- [Java SE 24: MessageDigest](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/security/MessageDigest.html) — Implementation Note clarifying `null`/empty second-argument cases.
- [Java SE 17: Mac](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html) — creating and verifying MACs/HMACs.
- [OpenJDK: MessageDigest.java](https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/security/MessageDigest.java) — source reference; implementation details may vary across versions.
