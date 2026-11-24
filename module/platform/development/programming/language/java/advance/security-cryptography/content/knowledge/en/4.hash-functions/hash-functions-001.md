# 4.1. One-Wayness, Preimages, and Collisions of Cryptographic Hash Functions

A cryptographic hash function transforms data of arbitrary length into a **fixed-length hash value (digest)**. We commonly use SHA-256 to compute a fingerprint for a file, check whether data has changed, or serve as an internal building block in digital signatures and HMAC. However, to understand why a hash value can be used in security mechanisms, we must distinguish three properties: **preimage resistance**, **second-preimage resistance**, and **collision resistance**.

For example, the SHA-256 of the UTF-8 string `abc` is:

```text
Input bytes (UTF-8): 61 62 63
SHA-256 (hex):
ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
```

The result consists of 32 bytes, commonly represented as **64 hex digits**. A different string usually produces a different digest, but we cannot claim that *every* pair of distinct strings has different hashes.

After this lesson, you should be able to:
- Explain that a "one-way" hash function means it is computationally hard to find an input from a digest, not mathematically impossible.
- Clearly distinguish the problems of finding a **preimage**, a **second preimage**, and a **collision**, especially what information the attacker is given beforehand.
- Estimate the ideal attack cost for an `n`-bit output: roughly `2^n` for preimage/second preimage and `2^(n/2)` for collision.
- Understand the birthday bound, the impact of truncating a digest, and why low-entropy data can still be guessed easily.
- Apply SHA-256 in Java 17+, read results as bytes/hex, and avoid confusing a plain hash with an authentication mechanism or password storage.

## 1. What Is a Cryptographic Hash Function?

General notation:

```text
             H
Message M --------> Digest h = H(M)
(any length)        (fixed n bits)
```

Idealized model:

\[
H:\{0,1\}^{*}\rightarrow\{0,1\}^{n}
\]

Where:
- `M` is a sequence of **bytes/bits**, not implicitly characters; UTF-8 encoding, normalization, or JSON serialization directly affects the digest.
- `n` is the digest length in bits. For SHA-256, `n = 256`; for SHA-512, `n = 512`.
- `H` is a public, deterministic algorithm: the exact same byte sequence produces the same digest. The SHA-256 algorithm does not require a separate secret to operate.

A suitable cryptographic hash function is typically designed to have the following properties:
1. **Determinism:** `H(M)` always produces the same output if the algorithm and input bytes do not change.
2. **Forward efficiency:** given a message and algorithm, computing the digest has an acceptable cost.
3. **Preimage resistance:** given only a target digest, it is hard to find a message that hashes to that value.
4. **Second-preimage resistance:** given a specific message, it is hard to find a *different* message with the same digest.
5. **Collision resistance:** it is hard to find *any pair* of distinct messages with the same digest on one's own.

Items 3–5 are **security goals against an adversary with bounded computational resources**, not a guarantee that a unique message exists for each digest. The avalanche effect—changing a few input bits usually changes many output bits—is a desirable property, but observing the avalanche effect alone **is not sufficient to prove** the three resistance levels above.

### 1.1. Why Do Collisions Necessarily Exist?

Inputs can be arbitrarily long, whereas the output has only `2^n` distinct values. By the pigeonhole principle, many distinct messages share the same digest. In other words:

\[
\exists M_1 \neq M_2 : H(M_1) = H(M_2)
\]

**Collisions exist mathematically**; the practical security question is whether an adversary can **find** a useful collision at a feasible cost.

Do not interpret "low probability of collision" as "no collisions exist," and do not interpret "collisions exist" as "the hash function is broken." A good 256-bit hash function still has infinitely many colliding pairs, yet actively finding a pair via a generic attack is expected to be prohibitively expensive.

## 2. Three Problems: Preimage, Second Preimage, and Collision

Let us denote the target digest as `h`, the original message as `M`, and a new message as `M'`.

| Property | What the adversary is given | What the adversary wants to find | Success condition |
| --- | --- | --- | --- |
| **Preimage resistance** | A digest `h` | Any `M` | `H(M) = h` |
| **Second-preimage resistance** | A specific message `M` | An `M'` different from `M` | `H(M') = H(M)` |
| **Collision resistance** | The function `H`, **with no fixed `M` given beforehand** | Two distinct messages `M_1, M_2` | `H(M_1) = H(M_2)` |

The decisive difference lies in the **degree of freedom in choosing inputs**:

- **Preimage:** the digest is already chosen; the adversary needs to find *a solution* for that value.
- **Second preimage:** the original message is fixed; the adversary cannot freely choose both messages.
- **Collision:** the adversary is free to choose **both** messages, so they can test many candidates and look for any matching pair.

### 2.1. Visualizing Each Challenge

**Challenge A — Preimage:** The verifier gives a digest `h = SHA-256(secretMessage)` without revealing `secretMessage`. The task is to find **any** data `X` such that `SHA-256(X) = h`. `X` does not necessarily have to equal the original `secretMessage`.

**Challenge B — Second preimage:** The verifier publishes an approved contract file `M`. The adversary must craft a file `M' != M` such that `SHA-256(M') = SHA-256(M)`. Preserving the digest of a **fixed** message is the key constraint.

**Challenge C — Collision:** The adversary creates any two files `A` and `B` themselves, as long as `A != B` yet they share the same digest. If the adversary also controls the meaning of both files (for example, one benign-looking file and one malicious file), this can lay the groundwork for a document substitution attack in a poorly designed signing or approval protocol.

**Do not confuse:** having a collision `H(A)=H(B)` **does not automatically** enable finding a second preimage for another pre-selected document `M`. An attacker possessing the pair `A, B` cannot assume that `A = M`.

### 2.2. Three Related but Distinct Properties

Collision resistance is a strong requirement in many signing/content-addressing designs because the adversary can find a pair of data items before a trusted party processes either of them. Preimage and second-preimage resistance protect **fixed-target** scenarios.

Do not deduce "one-way hash function ⇒ collision resistant" or "easy to find collisions ⇒ can find an arbitrary preimage." These are different security games with different attack methods and input-choice models.

## 3. Ideal Difficulty by Bit Length

For an `n`-bit hash function modeled as a sufficiently good random mapping, with inputs/outputs chosen under appropriate conditions and no structural weaknesses, the generic difficulty is estimated as:

| Problem | Typical generic difficulty | If digest is 256 bits |
| --- | --- | --- |
| Finding a preimage of a random target | Approximately `2^n` trials | `2^256` |
| Finding a second preimage of a fixed message | Approximately `2^n` trials | `2^256` |
| Finding a collision of two freely chosen messages | Approximately `2^(n/2)` trials | `2^128` |

These are **estimates in an idealized model**, not proof that every real hash function achieves those exact bounds; unusually long inputs, algorithmic structure, multiple targets, and specific attack techniques can alter the work required. Furthermore, **passwords or PINs with few possibilities** will be guessed across their small input space rather than requiring `2^256` trials.

### 3.1. Why Collisions Are Faster to Find: The Birthday Bound

Suppose we try `q` distinct inputs and observe `q` uniformly distributed `n`-bit digests. There are approximately:

\[
\frac{q(q-1)}{2}
\]

pairs of digests that can be compared. Each pair has a probability of roughly `1/2^n` of matching in a random model. When `q` is small relative to the output space, the probability of at least one collision is approximately:

\[
P(\text{collision}) \approx 1 -
\exp\left(-\frac{q(q-1)}{2^{n+1}}\right).
\]

When `q` reaches the order of `2^{n/2}`, the collision probability becomes significant. To reach roughly **50%**, about `1.177 \times 2^{n/2}` random samples are needed; the constant factor 1.177 does not change the order of complexity.

For example, with only a **16-bit** digest: there are `2^16 = 65,536` possible outputs. Only about **301 samples** are needed for the probability of seeing at least one matching pair to reach roughly 50% in a uniform model. This is why the Java experiment later easily finds a collision in the **first 2 bytes** of SHA-256.

The generic collision resistance strength of an `n`-bit hash is typically only around **`n/2` bits of security**, whereas ideal preimage strength can be around **`n` bits**. When designing IDs resilient against active adversaries or truncating digests for storage, do not confuse a "128-bit hash" with "128-bit collision resistance"; a 128-bit digest only has a birthday bound around `2^64`.

### 3.2. Finding a Collision Does Not Mean Guessing the Content

If `H(password)` is known, an adversary typically tries plausible passwords from a dictionary, hashes them, and compares. This is a form of **preimage guessing over a low-entropy input set**, different from an algorithm that freely searches for collisions.

A 4-digit PIN has at most 10,000 candidates. Even when passed through SHA-256, the entropy of the PIN **does not increase** to 256 bits. An adversary with the digest and offline testing capability can exhaustively search this small space very quickly if plain SHA-256 is used directly.

## 4. "One-Way" Is a Computational Property, Not Encryption

Differences between hashing and encryption:

| Hash Function | Encryption |
| --- | --- |
| Maps data to a fixed-size digest | Transforms plaintext into ciphertext according to a scheme and parameters |
| Typically requires no secret key | Requires a key to encrypt/decrypt, depending on the scheme |
| No true "decrypt hash" algorithm exists to recover the original input | Authorized parties with the appropriate key can decrypt, and verify the tag if AEAD |
| Multiple inputs can share the same digest | A valid decryption scheme must uniquely determine the plaintext from a valid ciphertext |
| Suitable as a building block for fingerprints, signatures, MACs, KDFs, etc. | Suitable for protecting confidentiality; AEAD also provides authentication/integrity |

When given only a digest, "reversing" it generally relies on testing candidates, exploiting predictable inputs, or finding algorithmic weaknesses. "Reverse SHA-256" websites typically look up digests in tables of common values: that is **not** mathematical decryption of SHA-256.

It is important to distinguish:
- **One-way in the security sense:** no efficient method is known to find a preimage in the relevant threat model.
- **Not uniquely invertible:** from a fixed digest alone, there is insufficient information to determine a unique original input because many inputs produce the same digest.
- **Unpredictable input:** an independent condition regarding entropy. Even a very strong hash function cannot turn a common password into an unguessable secret against an offline attack.

## 5. When Are These Properties Used?

### 5.1. File Integrity Verification

Suppose a downloader knows the expected SHA-256 digest beforehand from a **trusted source**, then computes the SHA-256 of the downloaded file and compares them. If the digests differ, the file certainly does not match the expected bytes (ignoring processing errors outside the model); if the digests match, the probability that an adversary intentionally supplied a different file with the same digest is evaluated according to the hash's security and the attack model.

However, if an attacker can replace **both the file and the SHA-256 line displayed on the same untrusted page**, the comparison does not authenticate the author or download source. To verify origin, you need an authenticated digest source, a valid digital signature with a trusted public key, or an equivalent authentication mechanism.

### 5.2. Digital Signatures and Signed Documents

Many signature schemes process a digest or an encoded/hashed byte sequence as specified by the signing algorithm. If an adversary can craft two documents carrying the same digest in an unconstrained signing context, they may try to get a signature on a benign document accepted for another document.

Therefore, **collision resistance** is especially critical in protocols where an attacker has the ability to choose documents submitted for signing. However, merely stating `H(M)` does not describe the entire security of a signature: you also need a standard signature algorithm, proper encoding/verification formatting, domain/message-type controls, trusted signing keys, and signing authorization.

### 5.3. Content Addressing, Caching, and Merkle Trees

Digests can be used to reference a content blob (content addressing) or to organize a Merkle tree. Given a defined data source and encoding rules, identical bytes yield identical digests, making reuse/update checks straightforward.

If inputs are controlled by an adversary, collision risks and the use of a hash as a **unique identifier key** must be evaluated. In tree structures, leaf hashes and internal node hashes should be clearly separated using tags/domain separation to prevent structural ambiguity. A hash alone does not prove who published the content.

### 5.4. Password Storage: Entirely Different Requirements

**Do not store `SHA-256(password)` directly** as a password verifier. SHA-256 is designed to be fast, whereas human-chosen passwords are often predictable. Use a dedicated password-hashing/KDF function with a per-password salt and properly tuned cost parameters: Argon2id is typically the preferred choice where supported; scrypt, bcrypt, or PBKDF2 may be suitable depending on deployment constraints, with vetted parameters.

**A salt is not a secret key**: it can be stored alongside the verifier; its purpose is to ensure records with the same password use different inputs, preventing precomputed hash tables from being reused across multiple records. A salt does not increase the intrinsic entropy of a weak password; choosing a function that is intentionally expensive in computation/memory is what increases the cost of offline guessing.

## 6. Bits, Bytes, Hex, and Digest Truncation

For SHA-256:

```text
256 bits = 32 bytes = 64 hexadecimal digits

"abc" (UTF-8): 61 62 63
SHA-256("abc"):
ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
```

Hex length is not an independent security strength: 64 hex digits encode 256 bits of output, whereas a general 64-character *text* string does not necessarily carry 256 bits of entropy.

### 6.1. Truncating a Digest Can Rapidly Reduce Security

If only the first `t` bits of a digest are kept and treated as an identifier:

\[
H_t(M) = \operatorname{prefix}_t(H(M))
\]

then in a uniform model, target preimage resistance is on the order of `2^t`, while collision resistance is only on the order of `2^{t/2}`. For example, keeping the **first 16 bits** of SHA-256 creates a *new 16-bit hash function* prone to collisions; discovering a collision there is **not** discovering a collision in full SHA-256.

Do not arbitrarily truncate digests in signing/authentication protocols or collision-resistant designs without determining the security level, data volume, and relevant standard requirements. For detecting intentional tampering, keep the full output of the standard algorithm whenever possible.

### 6.2. Byte Differences Lead to Digest Differences

Compare:

```text
"abc"      -> bytes 61 62 63
"abc\n"   -> bytes 61 62 63 0a
"ABC"      -> bytes 41 42 43
```

SHA-256 operates on **actual bytes**, unaware that two strings "look equivalent." A file with CRLF differs from LF and will have a different digest; JSON with different property ordering or whitespace can have a different digest; Unicode text can have multiple composite encodings.

When a protocol requires two parties to compute the digest/signature of the "same message," it must specify:
- Charset (e.g., UTF-8), Unicode normalization if applicable, and line/character encoding.
- Canonical serialization of JSON/XML/objects, field lengths and delimiters, and field ordering.
- Format version, domain/application context, and the exact bytes being protected.

**Do not arbitrarily trim, lowercase, or normalize after signing**: such operations can alter business meaning or introduce ambiguity. Standardize the format before hashing.

## 7. Java 17+: Observing Determinism and a 16-Bit Truncated Collision

The example below uses `MessageDigest` in the Java Cryptography Architecture (JCA). The program computes the SHA-256 of `abc`, compares digests, and then **deliberately takes only the first 16 bits** to find an easily observable collision.

Create the file `HashFundamentalsDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.Map;

public class HashFundamentalsDemo {
    private static byte[] sha256(String input) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        return md.digest(input.getBytes(StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws Exception {
        byte[] digest = sha256("abc");
        System.out.println("SHA-256(abc): "
                + HexFormat.of().formatHex(digest));

        System.out.println("Same input => same digest: "
                + MessageDigest.isEqual(sha256("abc"), sha256("abc")));
        System.out.println("abc vs abd same digest: "
                + MessageDigest.isEqual(sha256("abc"), sha256("abd")));

        // Demo: collision on a deliberately truncated 16-bit digest.
        // It does NOT claim a collision in full 256-bit SHA-256.
        Map<Integer, String> seen = new HashMap<>();
        for (int i = 0; i < 100_000; i++) {
            String input = "message-" + i;
            byte[] fullDigest = sha256(input);
            int prefix16 = ((fullDigest[0] & 0xff) << 8)
                    | (fullDigest[1] & 0xff);

            String previous = seen.putIfAbsent(prefix16, input);
            if (previous != null) {
                System.out.println("Collision on 16-bit prefix: "
                        + previous + " / " + input);
                System.out.printf("Prefix (hex): %04x%n", prefix16);
                System.out.println("Full SHA-256 equal: "
                        + MessageDigest.isEqual(sha256(previous), fullDigest));
                break;
            }
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac HashFundamentalsDemo.java
java HashFundamentalsDemo
```

Output (verified with the JDK; fixed inputs and iteration order):

```text
SHA-256(abc): ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
Same input => same digest: true
abc vs abd same digest: false
Collision on 16-bit prefix: message-126 / message-133
Prefix (hex): 6620
Full SHA-256 equal: false
```

Detailed explanation:

1. `MessageDigest.getInstance("SHA-256")` creates an object to compute SHA-256. `digest(byte[])` returns a **32-byte** array, not a hex string. `HexFormat.of().formatHex(...)` is purely for display.
2. Hashing the exact same bytes of `abc` twice returns identical digests. This is **determinism**, not a proof of collision resistance.
3. Hashing `abc` and `abd` returns two different digests; this is **one observation** for a specific pair, from which one cannot deduce that every distinct pair has a different digest.
4. `prefix16` takes the first 2 bytes, so there are only `65,536` possible values. The program records previously seen prefixes and stops when a duplicate pair is encountered.
5. `message-126` and `message-133` share the prefix `6620`, yet their **full SHA-256 digests differ**. This is a collision of the function `H_16` that we defined via truncation, not a vulnerability in SHA-256.
6. `MessageDigest.isEqual(...)` compares digest bytes using the API intended for comparing hash values. It **does not turn** unkeyed SHA-256 into a MAC; do not use a self-reported digest match to authenticate a sender.

From this example, you can change `prefix16` to 8 bits or 24 bits to observe the change in the number of samples needed, but do not use a single small experiment to claim a "guaranteed" probability for every dataset. The birthday bound describes **probability** under appropriate distribution assumptions.

### 7.1. Why Does This Example Not "Break SHA-256"?

The program finds two strings `A, B` such that:

\[
\operatorname{prefix}_{16}(SHA256(A))
=
\operatorname{prefix}_{16}(SHA256(B)).
\]

Yet it simultaneously checks:

\[
SHA256(A) \neq SHA256(B).
\]

To prove a collision in **full SHA-256**, one must exhibit two distinct messages whose **entire 256-bit** digests match. Matching a few leading bytes is merely a collision on the truncated function we created.

### 7.2. Notes on Using MessageDigest Beyond Demos

- Explicitly specify `StandardCharsets.UTF_8` for text data. Do not rely on the platform default charset.
- A `MessageDigest` object is mutable; do not share a single instance across multiple threads by default. Create an instance per use or manage concurrency properly.
- `digest(...)` processes an input byte array; for large files, read in chunks and call `update(...)` repeatedly, then `digest()` to finalize, instead of forcing the entire file into RAM.
- Do not use `new String(digestBytes, UTF_8)` to represent a digest: a digest consists of arbitrary-looking bytes that may not form valid UTF-8. Use hex/base64 when text representation is needed.
- Rely on digest comparison against a **trusted expected value** only for integrity; if you must authenticate a counterparty, choose HMAC/signatures or an appropriate authentication protocol.

## 8. Common Mistakes and Limitations of Hash Functions

| Misconception / Design Flaw | Issue | Correct Understanding or Handling |
| --- | --- | --- |
| "SHA-256 cannot have collisions" | Infinite inputs, finite digests | Collisions necessarily exist; security relies on the difficulty of finding them |
| "Preimage, second preimage, and collision are the same" | Ignores constraints on fixed messages/digests | Precisely identify what the adversary is allowed to choose |
| "A 256-bit hash has 256-bit collision resistance" | Ignores the birthday bound | Generic collision difficulty is around `2^128` |
| "Having any collision pair lets you replace a signed file M" | Confuses collision with second preimage | Check whether the attacker controls the document before signing |
| "Storing SHA-256(password) is already secure" | SHA-256 is too fast and passwords have low entropy | Use Argon2id/scrypt/bcrypt/PBKDF2 per appropriate policy with a salt |
| "Hashing is encryption, so you can decrypt a hash" | A digest has no decryption operation that recovers the original data | Use encryption when confidentiality and decryption are required |
| "Sending SHA-256 alongside a file proves the file came from the right server" | An adversary can modify both | The digest/signature must be verified through a trusted source |
| "Just hash(req) is enough to authenticate an API" | A hash has no secret and does not prove authorship | Use HMAC or signatures with proper key management and identity binding |
| "Using `SHA-256(secret || message)` as a MAC" | Homemade constructions can suffer from length-extension/ambiguity | Use standard HMAC-SHA256; do not invent your own MAC |
| "Changing 1 bit drastically changes the digest ⇒ the hash is secure" | Avalanche does not prove attack resistance | Requires algorithmic analysis and cryptographic evidence |
| "MD5/SHA-1 are still good enough for modern signatures" | Practical collisions have weakened these functions | Avoid MD5/SHA-1 for collision security; use accepted modern algorithms |
| "Comparing two hex strings means encoding doesn't matter" | Different UTF-8/JSON/newlines/Unicode → different bytes | Standardize the format clearly before hashing |
| "`String.hashCode()` and CRC32 are hashes too, so they can be used for signing" | Not designed to resist adversaries seeking collisions/forgeries | Use a dedicated cryptographic hash function |

### 8.1. Beware of Legacy Algorithms and Homemade Constructions

- **MD5** and **SHA-1** have practically demonstrated collision issues, making them unsuitable for security mechanisms requiring modern collision resistance. Do not equate an algorithm still existing in a legacy compatibility API with it being safe to choose for new designs.
- **SHA-256**, **SHA-384/512**, and the **SHA-3** family are standard hash families used according to security requirements and compatibility policies. Selecting a function must account for security strength, performance requirements, the application use case, associated signature/MAC algorithms, and applicable regulations.
- With Merkle–Damgård hashes like SHA-256, knowing `SHA-256(secret || message)` can open the door to a **length-extension attack** when an application builds a homemade MAC by prepending a secret before the message. Preimage resistance **does not mean** prepending a key to SHA-256 creates a secure MAC. Use standard HMAC and apply proper message/context separation.

Do not design your own hash algorithm, signature protocol, or MAC merely by concatenating strings and appending a digest; bugs in encoding, domain separation, and trust handling rarely surface in a "hash matches" unit test.

## 9. Analyzing Scenarios by the Right Property

**Scenario 1 — A published file has a trusted digest.** An attacker wants to replace the downloadable file with *a different file* that still matches the exact published digest. The target file/digest is fixed. This closely matches the **second-preimage** problem for the target file, assuming the published digest is authentic.

**Scenario 2 — Two contracts share the same digest before signing.** An attacker creates two contracts themselves, gets a user to sign the benign contract, and then transfers the signature to the other contract in a protocol that does not distinguish messages. The crux is the ability to find a **collision**, specifically a collision with properties required by the attack.

**Scenario 3 — Digest of a random API token.** An attacker only has the digest and wants to find any value with the same digest. This is a **preimage** problem; if the token has high enough entropy, it is generally hard. If the token is merely a 4-digit PIN, brute-forcing across the set of possible values can be easy.

**Scenario 4 — Two large files in storage share the first 2 bytes of SHA-256.** This is a collision of a **truncated 16-bit digest**, and says nothing about whether a collision of full SHA-256 exists.

**Scenario 5 — An attacker replaces both the download file and its SHA-256 on the same compromised website.** Here, no attack on the hash is needed; the vulnerability is an **untrusted digest source**. You must authenticate the source or signature, not simply pick a longer hash.

## 10. Self-Check Exercises

**Question 1.** For an ideal 160-bit hash function, roughly what is the generic difficulty of finding a colliding pair?

**Answer:** Roughly `2^80` trials, unlike the fixed-target preimage problem which is roughly `2^160` in the appropriate model.

**Question 2.** The verifier gives you a digest `h` without giving the original message. You must find any `M` such that `H(M)=h`. Which property is this?

**Answer:** Preimage resistance.

**Question 3.** The verifier gives you `M`; you need `M' != M` such that `H(M')=H(M)`. Are you allowed to freely craft any two distinct messages to find a collision?

**Answer:** No. This is a second-preimage challenge; the original message is fixed.

**Question 4.** A `n=32`-bit hash function has `2^32` possible output values. When testing a few tens of thousands of distinct inputs, why can a collision still occur early?

**Answer:** Because the number of pairs among samples grows roughly as the square of the number of samples; the birthday bound indicates that around `2^16` samples, a collision already has significant probability, without needing to exhaust all `2^32` values.

**Question 5.** Why doesn't `SHA-256("1234")` give the password "1234" guessing resistance comparable to a random 256-bit key?

**Answer:** The password space remains small and predictable. An adversary can compute SHA-256 of candidates and compare; you need a sufficiently strong password together with dedicated password hashing and authentication controls.

**Question 6.** Can you treat two SHA-256 digests of a file computed on two machines as indicating "different files" if one machine automatically converted CRLF to LF?

**Answer:** The digests can differ because the file bytes differ, even if the rendered text looks nearly identical. You must standardize bytes and canonicalization rules when the task requires matching logical content.

**Question 7.** Why do two distinct messages sharing the *first 4 hex characters* of SHA-256 not prove a collision of SHA-256?

**Answer:** 4 hex characters represent only the first 16 bits; the remaining 240 bits can differ. A full collision requires all 256 bits to match.

## 11. Summary Diagram

```text
                BYTE DATA M
                      |
              Cryptographic hash H
                      |
                 n-bit digest
                      |
      +---------------+------------------+
      |               |                  |
  Preimage        Second preimage     Collision
  Given h         Given M             Freely choose M1, M2
  Find M          Find M' != M        M1 != M2
  H(M) = h        H(M') = H(M)        H(M1) = H(M2)
  ~2^n            ~2^n               ~2^(n/2)
                      |
       The above difficulty bounds are an idealized model,
       not an absolute guarantee in every case
```

**Key takeaway:** *One-wayness* refers to the difficulty of finding an input for a fixed digest; *second preimage* requires replacing a known message while preserving its digest; *collision* allows freely choosing both messages and is therefore subject to the birthday bound. The cryptographic properties of a hash only hold in a protocol that uses the right bytes, the right algorithm, an appropriate length, and an authenticated trusted source.

### References

- NIST FIPS 180-4, *Secure Hash Standard (SHS)* — defines SHA-256 and SHA-2 algorithms: https://csrc.nist.gov/pubs/fips/180-4/upd1/final
- NIST FIPS 202, *SHA-3 Standard* — the SHA-3 family: https://csrc.nist.gov/pubs/fips/202/final
- NIST SP 800-107 Rev. 1, *Recommendation for Applications Using Approved Hash Algorithms* — defines hash security strengths: https://csrc.nist.gov/pubs/sp/800/107/r1/final
- Java SE 17 API, `MessageDigest`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html
- Java SE 17 API, `HexFormat`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html
- OWASP, *Password Storage Cheat Sheet* — guidance on dedicated password storage: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
