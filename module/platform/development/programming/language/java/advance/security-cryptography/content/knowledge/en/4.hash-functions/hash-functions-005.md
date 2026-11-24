# 4.5 Distinguishing Checksums, Object.hashCode, and Cryptographic Digests

Three things commonly called a "hash" are easily conflated in Java: a **checksum** for detecting transmission/storage errors, **`hashCode()`** for supporting lookup and object comparison in structures like `HashMap`, and a **cryptographic digest** for producing an attack-resistant fingerprint of a byte sequence. They may all return numbers or hex strings, yet their **purpose, input data, collision properties, and security guarantees are completely different**.

This lesson belongs to the **Hash Functions** topic and focuses on choosing the right technique in Java, without confusing "error detection" with "origin authentication."

## 1. Learning Objectives

Upon completion, you will be able to:

1. Distinguish **checksums against accidental errors**, **`hashCode()` for data structures**, and **cryptographic digests** such as SHA-256.
2. Accurately state the `equals()`/`hashCode()` contract, the meaning of collisions, and the consequences when a `HashMap` key is mutated.
3. Explain why CRC32/CRC32C/Adler32 differ from SHA-256, and why **SHA-256 alone still cannot authenticate the sender**.
4. Write Java 17+ code to compute checksums, `String.hashCode()`, and SHA-256; interpret each result properly and know when to pass **bytes** versus when to define **objects**.
5. Choose checksums, digests, HMAC/digital signatures, or password KDFs according to real-world requirements.

## 2. Quick Comparison Table

| Criterion | Checksum | `Object.hashCode()` / `hashCode()` method | Cryptographic Digest |
| --- | --- | --- | --- |
| Question answered | Were bytes **accidentally** corrupted/altered? | Which **bucket** should an object be placed in/looked up from, and how to quickly filter comparison candidates? | Do two byte payloads share the same **cryptographic fingerprint**, assuming a collision-resistant algorithm? |
| Typical input | A byte sequence in a defined format | An object, via the class's `hashCode()` method | Any byte sequence; can be fed in multiple chunks |
| Examples | CRC32, CRC32C, Adler32 | `String.hashCode()`, `record.hashCode()`, `Objects.hash(...)` | SHA-256, SHA-384/512, SHA-3 |
| Output | Usually a short checksum (e.g., CRC32 is 32 bits) | Java returns a **32-bit signed `int`** | SHA-256 returns **32 bytes (256 bits)**; hex representation is 64 characters |
| Key property | Effective at detecting **unintentional transmission/storage errors** per error-correcting/detecting code design | Equal by `equals()` **must** have the same hash; unequal objects **may** share a hash | Designed to resist preimage, second-preimage, and collision attacks efficiently |
| Active adversary | Can modify data and recompute the checksum; CRC is not a security mechanism | Can craft many distinct objects with the same `hashCode()`; provides no authentication or security | Hard to intentionally find collisions with a strong algorithm, yet **anyone can compute the digest** of data they choose |
| Proper use cases | Error checking for packets, records, storage formats, and error-control systems | `HashMap`, `HashSet`, hash-table keys, filtering candidates before `equals` | Matching files against a **trusted** digest, content addressing, building blocks of HMAC/digital signatures and cryptographic protocols |

**Three rules to remember:**

- **A checksum is not a cryptographic digest:** detecting random byte corruption is different from stopping an adversary who intentionally crafts forged content with a matching fingerprint.
- **`hashCode()` is not a digest:** returning the same number **does not mean two objects are equal**, and certainly does not mean data has not been tampered with.
- **A digest is not authentication:** a collision-resistant SHA-256 still does not prove **who** supplied the bytes or who published the digest; preventing origin forgery requires a trust anchor, MAC, or digital signature.

## 3. Checksums: Detecting Unintentional Data Errors

### 3.1. Mechanism

A checksum is computed from the data bytes:

~~~text
Original data: bytes ──checksum algorithm──> checksum A
Received data: bytes ─checksum algorithm──> checksum B
A == B ?  →  data is likely uncorrupted under the algorithm's error model
~~~

Storage/transport protocols often place a checksum alongside content to detect errors caused by signal noise, read/write faults, transmission glitches, or recording errors. **You cannot conclude "A == B means the two byte sequences are definitely identical"**: finite output length means collisions exist.

**CRC (Cyclic Redundancy Check)** interprets data as bits and computes the remainder modulo a specified polynomial. The polynomial design effectively detects many error patterns (such as single-bit flips or burst errors within the code's capability). CRC **is not designed to stop an attacker from intentionally modifying data**, because the algorithm and calculation are public and have algebraic structure allowing the checksum to be adjusted/recomputed.

- **CRC32 (`java.util.zip.CRC32`)** is common in ZIP/GZIP and many legacy formats; for `"abc"` in UTF-8, its hex value is `352441c2`.
- **CRC32C (`java.util.zip.CRC32C`)** uses the Castagnoli polynomial, chosen by many storage/transport systems; for the exact `"abc"` bytes, it yields `364b3fb7`. **CRC32 and CRC32C are not interchangeable**, even though both are 32-bit checksums. Sender and receiver must agree on the variant, byte order, and framing convention.
- **Adler32 (`java.util.zip.Adler32`)** uses a different modular-addition checksum, commonly used in zlib; `"abc"` gives `024d0127`. It is also **not a cryptographic hash function**.
- Very simple byte-sum checksums are sometimes used for basic error detection, but they miss many more error patterns than a dedicated CRC.

A CRC32 has a **32-bit output**, so it cannot uniquely map every message. For two nearly uniformly distributed values, the probability of an accidental match is roughly `2^-32`; this is **not** a security guarantee against intentional tampering. CRC has linear relationships that allow an attacker to actively construct data with the same CRC in multiple ways.

In Java, `Checksum.update(byte[], offset, len)` feeds bytes, `Checksum.getValue()` returns the value as a `long` (because 32-bit checksums are usually treated as **unsigned**), and `reset()` lets you reuse the object. To compute checksums for **two independent messages**, call `reset()` before the new message or create a new object; do not accidentally compute the checksum of concatenated data.

### 3.2. When Should Checksums Be Used?

Use a checksum when the goal is **detecting unintentional corruption** and the protocol specifies the algorithm. For example, a data packet on a link that is already **secured by another mechanism** can still use CRC for efficient low-level error checking. If you need to prove a **trusted publisher** or resist adversarial tampering, a checksum **cannot replace** HMAC/digital signatures.

A matching checksum is a reliable signal **within its defined error model and verified checksum source**, not proof against tampering or proof of identity.

## 4. `Object.hashCode()`: Supporting Java Data Structures

### 4.1. What Is `hashCode()` Really?

`Object` declares the method:

~~~java
public int hashCode()
~~~

Subclasses can **override** it to define a hash code based on the object's meaningful state. `String.hashCode()` is a prominent example; Java `record`s also provide `equals()`/`hashCode()` implementations consistent with the record components.

A `HashMap<K,V>` uses the hash code to determine the candidate bucket position/group, then uses `equals()` to distinguish keys that share the same hash code. `HashSet` applies the same mechanism to elements.

- **Mandatory contract:** If `a.equals(b) == true`, then `a.hashCode() == b.hashCode()`.
- **The converse is false:** Two **unequal** objects can still have the same `hashCode()` (a collision).
- As long as state relevant to `equals` does not change, calling `hashCode()` multiple times within the same execution must remain consistent. There is no general requirement that every class's hash code remain stable across separate JVM runs.
- If you override `equals()`, you must override `hashCode()` consistently. Omitting either causes hash-based collections to behave logically incorrectly.

**Reproducible collision example:**

~~~text
"Aa".hashCode() = 2112
"BB".hashCode() = 2112
"Aa".equals("BB") = false
~~~

This **does not cause `HashMap` to treat `"Aa"` and `"BB"` as the same key**. It must check `equals()` after grouping candidates by hash. Hash tables tolerate collisions; heavy collisions can hurt performance, so good hash code distribution still matters.

### 4.2. Default `Object`, `String`, and `Objects` Are Not the Same

- `new Object().hashCode()` uses `Object`'s default implementation, typically tied to object identity in the JVM, yet it is **not guaranteed by Java** to be a memory address, a unique value, or a persistent identifier.
- `String.hashCode()` overrides it based on string content using a deterministic algorithm specified by Java; different strings can still collide. It is an `int` and is **not** SHA-256.
- `System.identityHashCode(obj)` retrieves the identity-style `Object` hash even when a class overrides `hashCode()`; it is still neither unique, persistent, nor cryptographic.
- `Objects.hashCode(obj)` is a null-safe utility (returns 0 if null, otherwise calls `obj.hashCode()`); `Objects.hash(fields...)` combines multiple fields for the Java contract, **not as a cryptographic hash function**. In performance-sensitive code, consider the varargs array allocation cost of `Objects.hash(...)`.

**Mutable keys are a trap:** If you insert an object into a `HashMap` and then mutate a field participating in `equals/hashCode`, subsequent lookups may search a different bucket and fail even though the object is still in the map. Prefer **immutable keys**, such as `String` or a `record` with immutable components, and never mutate state that defines key identity.

A 32-bit hash code is also **not a unique ID**, content fingerprint, security key, or value suitable for access-control decisions.

## 5. Cryptographic Digests: Attack-Resistant Byte Fingerprints

### 5.1. Mechanism and Properties

A cryptographic hash function such as SHA-256 takes a byte sequence of arbitrary length and returns a fixed-length digest:

~~~text
UTF-8("abc") → [0x61, 0x62, 0x63]
SHA-256(bytes) → 32 bytes
Hex representation of digest → ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
~~~

**Hex is not a different digest:** It is just a display format for the binary digest. For SHA-256, 32 bytes display as 64 hex characters. Base64 can also represent those exact same 32 bytes as another text encoding.

A secure cryptographic hash aims for:

1. **Preimage resistance:** given `H(m)`, it is hard to find an `m` that produces that exact digest.
2. **Second-preimage resistance:** given `m`, it is hard to find `m' != m` with the same digest.
3. **Collision resistance:** it is hard to actively find **any** pair `m != m'` with the same digest. For an ideal 256-bit digest, the birthday-method collision cost is around `2^128` trials, distinct from the full space of `2^256` digests.

"Hard" refers to **computational cost when using the right algorithm/length**, not the mathematical absence of collisions. Therefore digests are often suitable for content matching or content addressing, yet you still must verify bytes, context, algorithm, and digest source depending on the goal.

- **SHA-256** is a standard, widely used choice available in the JDK via `MessageDigest.getInstance("SHA-256")`.
- **SHA-512/SHA-3** can be appropriate when specified by a protocol/requirement. Do not unilaterally swap algorithms on either side if the format is fixed.
- **MD5 and SHA-1** have severe collision weaknesses; do not choose them where an attacker must be prevented from crafting forged content with a matching digest.
- **SHA-256 must not be used to store passwords directly:** passwords usually have low entropy. Use a slow, salted password-hashing/KDF function (Argon2id, scrypt, or PBKDF2 depending on the ecosystem and safe parameters), which is distinct from hashing a file.

### 5.2. A Digest Does Not Authenticate Origin by Itself

Suppose a website serves `app.zip` for download and also posts `SHA256SUMS` on the same website. If an attacker compromises the website, they can **replace both the file and the SHA-256 line** to match the malicious file. Your `MessageDigest` check will match, yet **it does not prove the true publisher**.

Choose additional protections according to the threat model:

- **Digest from an independent trusted channel:** can serve as an expected value to detect alterations on a download.
- **HMAC:** two parties sharing a secret can compute/verify an authentication tag bound to the data bytes; suitable for message authentication in systems sharing a key.
- **Digital signatures:** the signer holds a private key; recipients use a **verified public key** to verify the signature, suitable for distributing artifacts to many verifiers.
- **TLS/AEAD:** when content confidentiality in transit or at rest is needed, use an appropriate protocol/cipher; SHA-256 **does not encrypt** content.

Checksums, `hashCode()`, and SHA-256 all require no secret to compute. **Security differences stem from mathematical properties and usage**, while proof of identity must come from a trusted protocol.

## 6. Java Objects and Byte Sequences Are Not the Same Input

To compare accurately, you must define **what is being hashed**.

| Input / Operation | Meaning |
| --- | --- |
| `"abc".hashCode()` | Hash code of the `String` content for collections; the `int` value is `96354`. |
| `CRC32.update("abc".getBytes(UTF_8))` | Checksum of **3 UTF-8 bytes**: `61 62 63`. |
| `SHA-256("abc".getBytes(UTF_8))` | Cryptographic digest of the **same 3 UTF-8 bytes**, 32-byte result. |
| `sha256(fileBytes)` | Hashes the exact bytes of the file, **not** implicitly the filename string or normalized content. |
| `sha256(serialize(object))` | Hashes the serialized form per a defined rule; changing serialization can change the digest even if the object has the same business meaning. |

**Differences often overlooked:**

- **Encoding:** `UTF-8` differs from `UTF-16`. `String.hashCode()` operates on the `String`'s UTF-16 code units, whereas `MessageDigest` takes **bytes**; you must choose `StandardCharsets.UTF_8` or an agreed format.
- **Line endings:** `"abc"`, `"abc\n"`, LF files, and CRLF files have different bytes → different SHA-256/CRC.
- **Unicode normalization:** two visually identical strings can have different Unicode code point/byte sequences (e.g., composed vs. decomposed accented characters). Normalize **only if the protocol specifies it**, and hash the exact normalized form.
- **JSON and structured data:** different field ordering, whitespace, or numeric formatting can produce different bytes even if semantically equivalent. When signing/hashing structured data across languages, agree on **canonical serialization** first.
- **Format and algorithm provenance:** sending a checksum requires specifying or fixing CRC32 vs. CRC32C, framing, and byte order. For digests, specify SHA-256 vs. another algorithm; hex may be uppercase or lowercase, whereas the **digest bytes** are what matter.

**Do not arbitrarily use `Object.toString()`, `hashCode()`, or default serialization to produce a durable digest of an object.** They make no promises of canonicalization, cross-version stability, or appropriate security guarantees.

## 7. Java 17+ Example: One Program, Three Kinds of Values

This example uses standard JDK APIs with no Maven or external dependencies. The program deliberately chooses `"Aa"` and `"BB"` to produce a **`String.hashCode()` collision**, then demonstrates that `HashMap` still stores both keys. It also computes checksums and the digest of `"abc"`.

Save as **`ChecksumHashDigestDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.HashMap;
import java.util.Map;
import java.util.zip.Adler32;
import java.util.zip.CRC32;
import java.util.zip.CRC32C;
import java.util.zip.Checksum;

public class ChecksumHashDigestDemo {
    static byte[] utf8(String value) {
        return value.getBytes(StandardCharsets.UTF_8);
    }

    static String checksum(Checksum checksum, byte[] data) {
        checksum.update(data, 0, data.length);
        return "%08x".formatted(checksum.getValue());
    }

    static byte[] sha256(byte[] data) throws Exception {
        return MessageDigest.getInstance("SHA-256").digest(data);
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = utf8("abc");
        System.out.println("CRC32(abc)     = " + checksum(new CRC32(), bytes));
        System.out.println("CRC32C(abc)    = " + checksum(new CRC32C(), bytes));
        System.out.println("Adler32(abc)   = " + checksum(new Adler32(), bytes));
        System.out.println("SHA-256(abc)   = "
                + HexFormat.of().formatHex(sha256(bytes)));

        String first = "Aa";
        String second = "BB";
        System.out.println("hashCode(Aa)   = " + first.hashCode());
        System.out.println("hashCode(BB)   = " + second.hashCode());
        System.out.println("Aa equals BB?  = " + first.equals(second));

        Map<String, String> values = new HashMap<>();
        values.put(first, "first");
        values.put(second, "second");
        System.out.println("Map size       = " + values.size());
        System.out.println("Map[BB]        = " + values.get("BB"));

        System.out.println("SHA equals?    = " + MessageDigest.isEqual(
                sha256(utf8(first)), sha256(utf8(second))));
        System.out.println("CRC32 matches? = " + checksum(new CRC32(), bytes)
                .equals(checksum(new CRC32(), utf8("abd"))));
    }
}
~~~

Run:

~~~bash
javac ChecksumHashDigestDemo.java
java ChecksumHashDigestDemo
~~~

Exact output on JDK 17+:

~~~text
CRC32(abc)     = 352441c2
CRC32C(abc)    = 364b3fb7
Adler32(abc)   = 024d0127
SHA-256(abc)   = ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
hashCode(Aa)   = 2112
hashCode(BB)   = 2112
Aa equals BB?  = false
Map size       = 2
Map[BB]        = second
SHA equals?    = false
CRC32 matches? = false
~~~

**Output analysis:**

1. CRC32, CRC32C, and Adler32 take the **same 3 bytes** yet produce different outputs because their algorithms differ. Do not use a value from one algorithm to verify another.
2. SHA-256 takes those exact same bytes, yet its output is 256 bits long and has attack-resistance goals that CRC lacks. Its hex digest is 64 characters.
3. `"Aa"` and `"BB"` share the **same `hashCode` yet `equals()` returns `false`**. `HashMap` uses both the hash code and equality, so it stores two entries; matching hashes do not overwrite keys.
4. SHA-256 of `"Aa"` and `"BB"` are unequal. This **does not** prove SHA-256 never collides; it is merely a specific check for these two messages.
5. Checksums of `"abc"` and `"abd"` differ in the example. **Do not** conclude CRC can stop someone from intentionally altering bytes and crafting a matching checksum.

In the example, each checksum uses a fresh `new CRC32()`/`new CRC32C()`/`new Adler32()` object, avoiding state accumulation across messages. `MessageDigest.getInstance("SHA-256").digest(data)` computes the byte digest; `HexFormat` only formats the digest as hex characters. `MessageDigest.isEqual` compares two digest arrays without stopping immediately at the first differing byte; for authentication protocols, you must still verify all input conditions and lengths per design.

### 7.1. Streaming Large Files Instead of Reading Everything into RAM

When a file can be large, do not force `Files.readAllBytes(...)` to load everything. Call `MessageDigest.update(...)` repeatedly; the result equals a single-shot hash of the **exact concatenated byte sequence**, independent of how chunks are split.

The **illustrative method snippet below belongs inside a Java class**, not as a standalone program. It uses imports `java.io.InputStream`, `java.nio.file.Files`, `java.nio.file.Path`, and `java.security.MessageDigest`:

~~~java
static byte[] sha256File(Path file) throws Exception {
    MessageDigest digest = MessageDigest.getInstance("SHA-256");
    try (InputStream in = Files.newInputStream(file)) {
        byte[] buffer = new byte[8192];
        int count;
        while ((count = in.read(buffer)) != -1) {
            digest.update(buffer, 0, count);
        }
    }
    return digest.digest();
}
~~~

Call `HexFormat.of().formatHex(sha256File(Path.of("archive.zip")))` to obtain the hex string for the actual file bytes. To verify a download, compare the result against an expected digest from a **trusted source**. Also record the algorithm, timestamp, artifact name, and digest channel to reduce operational ambiguity.

**API note:** `MessageDigest`/`Checksum` objects hold internal state. Do not share the same instance across independently updating threads without explicit synchronization and reset rules. The full example creates a fresh instance per computation.

## 8. Choosing the Right Technique in Real-World Scenarios

| Scenario | Appropriate Technique | Reason |
| --- | --- | --- |
| Reading records from disk, wanting to detect random bit corruption | Format-specified checksum, such as CRC32C | Fast, targets accidental errors; does not prove origin |
| A ZIP/GZIP format mandates CRC32 | **Exact CRC32 per specification** | Cannot be arbitrarily replaced with CRC32C or SHA-256 |
| Implementing `HashMap<CustomerKey, Order>` | Proper `equals()` and `hashCode()` contract; immutable keys | Used solely for key distribution/lookup |
| Using a hash as a release-file identifier key | **SHA-256 of file bytes** | Much stronger collision resistance than checksum/`hashCode` for content IDs |
| Checking a file downloaded from a potentially spoofed server | SHA-256 **from a trusted channel** or digital signature with verified public key | A self-published digest beside the file cannot stop an attacker altering both |
| Authenticating webhooks between two services with a shared secret | **HMAC-SHA256** plus anti-replay rules | Plain SHA-256 has no authentication key |
| Allowing many clients to verify the publisher of an update | **Digital signature**, e.g., Ed25519 | Verifiers hold the public key; only the private-key holder signs |
| Storing user passwords | Appropriate **password hashing/KDF**, per-user salt, right cost parameters | Plain SHA-256 is too fast and does not address password-guessing attacks |
| Using CRC or SHA-256 for "data encryption" | **Wrong tool**; need encryption if data must stay confidential | Neither checksums nor digests provide a way to keep content secret |

### 8.1. Case Study: "The Downloaded File and Hash Matched, Yet It Was Still Malware"

Weak workflow:

~~~text
Compromised site
  ├── release.zip file replaced with a malicious file
  └── SHA256SUMS       recomputed accordingly
User downloads both → SHA-256 matches → can still receive the malicious file
~~~

Stronger workflow: obtain the publisher's public key through a **trusted channel**, verify the signature over the exact defined artifact or manifest, and check data and version policy. Digests bind bytes; signatures protect the reference value/signer. Key distribution and key revocation mechanisms remain critical.

### 8.2. Case Study: "I Stored Object `hashCode()` in the Database to Deduplicate"

This design is wrong because:

- It is only 32 bits; collisions are normal as data grows.
- Calculation depends on class, fields, and `equals/hashCode` implementation; code changes can alter values.
- Some default hash codes are tied to object identity and are unstable after creating new objects or restarting.
- Two objects considered equal in Java logic do not necessarily share the same **serialized bytes**, and vice versa.

For content addressing, build a **canonical serialization** of the content-defining fields and hash it with SHA-256 (alongside a namespace/schema version to prevent ambiguity). You still must apply appropriate data constraints and comparisons if business identity must be guaranteed; do not treat a digest as ownership or a signature.

### 8.3. Case Study: "CRC32 Mismatched While SHA-256 Matched"

If both parties truly hashed the **exact same bytes** with the same SHA-256 algorithm, a matching digest with differing CRC32 can stem from **differing CRC procedures**: one side used CRC32C, forgot to reset `Checksum`, hashed a different byte range, or formatted/packed the remainder with different endianness. Do not jump to concluding a primitive is "broken." Compare input bytes, algorithm, chunk order, lengths, and metadata first.

Even when both calculations use the same algorithm and canonical bytes, mathematically a digest and CRC each still have their own collision possibilities. Therefore **avoid absolute claims** based solely on a single hash value match.

## 9. Common Mistakes When Coding in Java

| Mistake | Consequence | Correct Practice |
| --- | --- | --- |
| Using `hashCode()` to detect file tampering | Collisions and instability/mismatch with file bytes | SHA-256 or an appropriate checksum; define a trusted reference source |
| Overriding `equals()` without overriding `hashCode()` | `HashMap`/`HashSet` may fail to find equal keys | Implement and test both using the same identifying fields |
| Using a mutable key in `HashMap` and changing hash-affecting fields | Keys can "disappear" on lookup | Use immutable keys or never mutate identifying fields |
| Assuming `hashCode(a)==hashCode(b)` means `a.equals(b)` | Erroneously merges data on collision | Use `equals` to determine equality |
| Substituting CRC32C for CRC32 because both are 32 bits | Different outputs, incompatible error checks | Preserve the exact variant, seed, byte handling, and protocol framing |
| Not resetting a `Checksum` object between two payloads | Second payload result accumulates the first payload | Use a new instance or `reset()` at the right boundary |
| Calling `String.getBytes()` without specifying a charset | Bytes vary by environment/config and protocol becomes fragile | Use `StandardCharsets.UTF_8` or a specified charset |
| Hashing JSON with different field order on each side | Digest/tag mismatch | Use the same canonicalization/serialization |
| Comparing SHA-256 against a digest from the same compromised source | False sense of security | Use a trusted digest source, HMAC, or digital signature |
| Using MD5/SHA-1 to defend against forged data | Exploitable via collisions in many scenarios | Choose SHA-256/SHA-3 per vetted protocols |
| Hashing passwords with plain SHA-256 | Vulnerable to high-speed offline guessing | Use Argon2id/scrypt/PBKDF2, unique salt, and safe cost settings |
| Sharing `MessageDigest` or `Checksum` across multiple threads | Race conditions, corrupted mixed state | Create dedicated instances or enforce synchronization |
| Using a digest instead of encryption | Digests do not allow authorized decryption and do not hide low-entropy secrets | Use encryption for confidentiality, digests for fingerprints |

## 10. Self-Check Exercises (with Answers)

**Exercise 1.** Two distinct `String`s share the same `hashCode()`. Must `HashMap` treat them as the same key?

**Answer:** No. `HashMap` uses the hash to narrow down a bucket and `equals()` to check actual key equality. `"Aa"` and `"BB"` are a real example: both hash to 2112 yet `equals` is false.

**Exercise 2.** After a mutable key's `hashCode()` changes, why might `map.get(key)` fail to find the value?

**Answer:** The map searches the bucket for the **new** hash code, whereas the entry resides in the bucket for the **old** hash code. Fields participating in `equals/hashCode` must remain stable while the object is used as a key.

**Exercise 3.** Files A and B have the same CRC32 checksum. Can you conclude they are identical and created by a trusted publisher?

**Answer:** No. CRC32 is 32 bits, so collisions occur and it provides no resistance against intentional tampering; it has no identity authentication mechanism.

**Exercise 4.** Why do CRC32(`"abc"`) and CRC32C(`"abc"`) differ even though both are 32 bits?

**Answer:** They use **different CRC polynomials/algorithms**. The number "32" only denotes checksum width, not formula compatibility.

**Exercise 5.** You download `installer.jar` and `installer.sha256` from the same server. The hashes match; is this enough protection against a compromised server?

**Answer:** No. An attacker can replace both the file and the digest. You need an independent trust anchor, such as a checksum from an authenticated channel or a digital signature with a trusted public key.

**Exercise 6.** Two services compute SHA-256 of JSON with the same meaning, yet get different digests. Should you change the SHA-256 function?

**Answer:** Usually no. Check source bytes, UTF-8, field order, whitespace, newlines, Unicode normalization, and canonicalization first. SHA-256 operates on **bytes**, not JSON semantics.

**Exercise 7.** When is HMAC-SHA256 needed instead of SHA-256 on webhook requests?

**Answer:** When you need to authenticate a sender **sharing a secret**, preventing anyone without the secret from forging valid requests. The protocol must also include replay protection; HMAC alone does not block replaying an intact request.

## 11. Algorithm Selection Checklist

Before writing code, ask yourself in sequence:

1. **Is there an active adversary modifying/forging data?** If only checking random errors and a format mandates CRC/Adler, use a checksum. If an active adversary exists, do not stop at CRC.
2. **Are you hashing objects or bytes?** For `HashMap` keys, implement `equals/hashCode` properly and keep keys immutable. For files/messages, define the exact bytes.
3. **Do you need a collision-resistant fingerprint against an adversary?** Choose SHA-256 or the protocol-specified algorithm, feeding bytes via `MessageDigest`.
4. **Where does the expected digest come from, and who is authorized to publish it?** If origin authentication is needed, add HMAC/digital signatures or a trusted reference source. Never treat SHA-256 automatically as a signature.
5. **Do you need confidentiality or password storage?** Use encryption/AEAD for confidentiality and a password KDF for passwords; do not assign those jobs to checksums, `hashCode()`, or standalone SHA-256.

**Core takeaway:** A **checksum** detects data corruption under an error model; **`hashCode()`** supports equality contracts and lookup structures in Java; a **cryptographic digest** creates a collision- and preimage-resistant fingerprint. Their numeric/hex forms look similar, yet **they cannot substitute for one another**, and none of them proves sender identity on its own.
