# 3.8 Designing Data Formats with Version, Length, and Algorithm Identifier

## 1. Why Does Cryptographic Data Need a Specified Format?

A raw byte array after encryption **does not explain how to decrypt itself**. Applications must know which version the data belongs to, which algorithm and parameters were used, which key to select, where the nonce/IV sits, and how many bytes belong to ciphertext versus authentication tag. If those details live only in source code or are guessed from payload bytes, reading legacy records, migrating systems, rotating keys, and handling corrupted records all become error-prone.

This lesson designs a **binary envelope** (a cryptographic data wrapper record) for storage and transport. The three core elements are:

- **Version:** specifies the *byte layout and interpretation rules* of the record.
- **Length:** unambiguously defines field boundaries, detects truncation/trailing bytes, and bounds input-processing cost.
- **Algorithm identifier:** maps a stable integer to a **concrete algorithm suite + parameters**, independent of JDK provider names.

A sound format also specifies **magic bytes**, **key identifier**, **nonce/IV**, encoding/endianness rules, metadata authentication, and a policy for rejecting unsupported data.

> The example below is an **illustrative application-defined format**, not a Java SE, JCA, or RFC 5116 file standard. Real projects can adopt vetted protocol/envelope standards (such as JWE when appropriate) rather than inventing a new protocol. The goal here is learning how to specify and implement an unambiguous byte structure.

## 2. Separating Format Version, Algorithm Suite, and Key ID

| Field | Answers the question | Must not be misunderstood as |
| --- | --- | --- |
| `magic` | "Is this the format family the parser understands?" | Magic is **not** a signature or proof of trustworthy data. |
| `version` | "Which schema governs the layout and validation of subsequent bytes?" | **File/protocol** version is not Java version or cryptographic strength. |
| `suite_id` | "Which algorithm, mode, key length, nonce, and tag are used?" | Never map arbitrarily to a `Cipher.getInstance()` string read directly from the file. |
| `key_id` (`kid`) | "Which candidate key should be looked up in the trusted keystore?" | An ID is **not a key**, is not secret, and does not grant access itself. |
| `nonce`/`IV` | "What unique initialization value was used for this encryption under this key?" | Not a password/salt; being public **does not** permit reuse under the same AES-GCM key. |
| `length` | "How many bytes does the next field span?" | Lengths come from untrusted input and must be validated **before allocation**. |
| `ciphertext` + `tag` | "Where are the encrypted data and integrity proof?" | Return plaintext only after tag verification succeeds. |

**Version and suite do not substitute for one another.** You can keep `version=1` when adding a new suite if byte framing stays unchanged; when field ordering, encoding, or mandatory field semantics change, bump the version/schema. The `suite_id` mapping table is part of the protocol spec: IDs must never be reused with different meanings.

For long-lived storage, `kid` enables selecting an older key when reading historical ciphertext after write-key rotation. Real keys must come from a key store/KMS/HSM or authenticated key repository; never pull keys from an untrusted record itself.

## 3. Concrete Specification: Binary Envelope v1

Suppose the application accepts only `suite_id = 0x01`, defined as:

- **AES-128-GCM**, JCA transformation `AES/GCM/NoPadding`.
- **16-byte** key (128 bits), **12-byte** nonce, **16-byte** authentication tag (128 bits).
- Plaintext payload length from **0 to 1,048,576 bytes** (1 MiB).
- Ciphertext is concatenated with tag: `body = ciphertext || tag`, length **plaintext_length + 16**.
- `key_id` is ASCII in `[A-Za-z0-9._-]`, **1–32 bytes** long; e.g., `key-A`.
- All lengths in the table below are **byte counts**, not Unicode character counts. Multi-byte integers are encoded in **big-endian (network byte order)**.

### 3.1 Exact Layout

| Offset, 0-based | Bytes | Field | Rule |
| --- | ---: | --- | --- |
| `0..3` | 4 | `magic` | ASCII `JENC` (`4A 45 4E 43` hex) |
| `4` | 1 | `version` | Unsigned `0x01` |
| `5` | 1 | `suite_id` | Unsigned `0x01` = AES-128-GCM/nonce-96/tag-128 |
| `6` | 1 | `kid_length` | Unsigned, must be in `[1,32]` |
| `7` | 1 | `nonce_length` | Unsigned, must equal `12` in v1/suite 1 |
| `8..11` | 4 | `body_length` | Unsigned 32-bit big-endian, must be in `[16,1.048.592]` |
| `12..(11+k)` | `k` | `key_id` | Valid ASCII, `k = kid_length` |
| `(12+k)..(23+k)` | 12 | `nonce` | 12 bytes generated for this encryption |
| `(24+k)..(23+k+c)` | `c` | `body` | Ciphertext plus 16-byte tag, `c = body_length` |

`fixed_header_length = 12`, `authenticated_header_length = 12 + k + 12 = 24 + k`, and `total_record_length = authenticated_header_length + body_length`. The parser must require **exact** consumption of this byte count; never silently ignore trailing bytes.

```text
+----------+---------+----------+---------+-----------+----------------+
| MAGIC(4) | VER(1)  | SUITE(1) | KIDLEN(1)| NONCELEN(1)| BODYLEN(4 BE)  |
+----------+---------+----------+---------+-----------+----------------+
| KEY_ID (k bytes) | NONCE (12 bytes) | ENCRYPTED_BODY (c bytes: C || TAG16) |
+------------------+------------------+--------------------------------------+
<------------ Authenticated header / AES-GCM AAD ------------->
```

Example with ASCII plaintext `Hello Java` (10 bytes) and `key_id = "key-A"` (5 bytes): header is `12 + 5 + 12 = 29` bytes, `body` is `10 + 16 = 26` bytes, total record length is **55 bytes**. Nonce, ciphertext, and tag vary with each encryption, so full hex output cannot be predicted beforehand.

### 3.2 ID Table Must Be Controlled by Trusted Code

```text
version 1, suite 0x01:
  algorithm      = AES
  JCA transform  = AES/GCM/NoPadding
  key bits       = 128
  nonce bytes    = 12
  tag bits       = 128
  body encoding  = ciphertext || 16-byte tag
```

If a new suite is needed, assign a **new ID** and write a dedicated spec + test suite. Never place JCA strings like `"AES"`, `"AES/ECB/PKCS5Padding"`, or provider names into data and pass them straight to the API: untrusted input could force an insecure or unintended algorithm. **Never automatically fall back** to a weaker algorithm when a requested suite is unavailable.

In v1, `nonce_length` is present to illustrate a length field and simplify structural checks; it **does not permit** arbitrarily changing the nonce to 8 or 16 bytes. The valid value remains fixed at 12 under suite 1. Any variable-length field must be documented with explicit bounds and algorithm rules.

## 4. Metadata Must Be Authenticated Alongside Ciphertext

For an **AEAD** such as AES-GCM, data is divided into:

- **Plaintext** `P`: encrypted and authenticated.
- **Associated Authenticated Data** (AAD) `A`: unencrypted, yet authenticated by the tag.
- **Nonce** `N`: transmitted publicly; must satisfy per-key uniqueness.
- **Ciphertext + authentication tag** `C || T`: sender output; receiver accepts only when tag verification succeeds.

In envelope v1, we place the **exact header bytes from offset `0` through the end of the nonce** into AAD:

```text
A = MAGIC || VERSION || SUITE || KIDLEN || NONCELEN
    || BODYLEN || KEY_ID || NONCE

(C || T) = AES-GCM-Encrypt(key, nonce, P, A)
P       = AES-GCM-Decrypt(key, nonce, C || T, A)
```

Thus if an adversary modifies `version`, `suite_id`, `key_id`, `length`, or `nonce`, an accepted record must pass both **syntax/allowlist checks** and **tag verification**. An invalid header field may be rejected by the parser before reaching verification; reading fields at this stage is solely for **routing/validation** and does not make the data trustworthy.

During decryption, use the **exact original bytes** of the header to compute AAD. Avoid deserializing into an object and re-serializing AAD with different field ordering, case, charset, or Unicode form. If external context exists—such as tenant ID, object ID, usage purpose, or protocol domain—both sides must bind it into AAD with an unambiguous encoding (usually length-prefix + domain separator) so a valid ciphertext cannot be transplanted into another context.

> **AES-GCM does not prevent replay on its own.** An attacker can resend an *exact valid record* and the tag will still verify. If the application needs freshness/anti-replay, add policy-driven sequence numbers, record IDs, timestamps, and consumed-record tracking; place decision-critical fields into AAD or authenticated plaintext.

## 5. Java 17 Example: Creating, Reading, and Authenticating the Envelope

The following program demonstrates full `seal()` and `open()` for **v1/suite 1**. It uses big-endian `ByteBuffer`, `Byte.toUnsignedInt()`, size checks **before allocation**, a trusted keyring keyed by `kid`, and `Cipher.updateAAD()` **before** `doFinal()`.

Create **`EnvelopeDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Map;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class EnvelopeDemo {
    private static final byte[] MAGIC = "JENC".getBytes(StandardCharsets.US_ASCII);
    private static final int VERSION = 1;
    private static final int SUITE_AES128_GCM = 1;
    private static final int FIXED_HEADER = 12;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BYTES = 16;
    private static final int MAX_KID_BYTES = 32;
    private static final int MAX_PLAIN_BYTES = 1_048_576;
    private static final int MAX_BODY_BYTES = MAX_PLAIN_BYTES + TAG_BYTES;
    private static final SecureRandom RNG = new SecureRandom();

    private static boolean validKid(String kid) {
        return kid != null && kid.matches("[A-Za-z0-9._-]{1,32}");
    }

    private static void requireAes128(SecretKey key) throws GeneralSecurityException {
        if (key == null || !"AES".equalsIgnoreCase(key.getAlgorithm())
                || key.getEncoded() == null || key.getEncoded().length != 16) {
            throw new GeneralSecurityException("AES-128 key required");
        }
    }

    public static byte[] seal(byte[] plain, SecretKey key, String kid)
            throws GeneralSecurityException {
        requireAes128(key);
        if (plain == null || plain.length > MAX_PLAIN_BYTES || !validKid(kid)) {
            throw new GeneralSecurityException("Invalid input");
        }

        byte[] kidBytes = kid.getBytes(StandardCharsets.US_ASCII);
        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);
        int bodyLength = plain.length + TAG_BYTES;

        ByteBuffer headerBuffer = ByteBuffer
                .allocate(FIXED_HEADER + kidBytes.length + NONCE_BYTES)
                .order(ByteOrder.BIG_ENDIAN);
        headerBuffer.put(MAGIC);
        headerBuffer.put((byte) VERSION);
        headerBuffer.put((byte) SUITE_AES128_GCM);
        headerBuffer.put((byte) kidBytes.length);
        headerBuffer.put((byte) NONCE_BYTES);
        headerBuffer.putInt(bodyLength);
        headerBuffer.put(kidBytes);
        headerBuffer.put(nonce);
        byte[] header = headerBuffer.array();

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, nonce));
        cipher.updateAAD(header);
        byte[] body = cipher.doFinal(plain);
        if (body.length != bodyLength) {
            throw new GeneralSecurityException("Unexpected ciphertext length");
        }

        byte[] record = Arrays.copyOf(header, header.length + body.length);
        System.arraycopy(body, 0, record, header.length, body.length);
        return record;
    }

    public static byte[] open(byte[] record, Map<String, SecretKey> keyRing)
            throws GeneralSecurityException {
        if (record == null || record.length < FIXED_HEADER
                || record.length > FIXED_HEADER + MAX_KID_BYTES
                        + NONCE_BYTES + MAX_BODY_BYTES) {
            throw new GeneralSecurityException("Invalid record size");
        }

        ByteBuffer buffer = ByteBuffer.wrap(record).order(ByteOrder.BIG_ENDIAN);
        byte[] magic = new byte[MAGIC.length];
        buffer.get(magic);
        int version = Byte.toUnsignedInt(buffer.get());
        int suite = Byte.toUnsignedInt(buffer.get());
        int kidLength = Byte.toUnsignedInt(buffer.get());
        int nonceLength = Byte.toUnsignedInt(buffer.get());
        int bodyLength = buffer.getInt();

        if (!Arrays.equals(magic, MAGIC) || version != VERSION
                || suite != SUITE_AES128_GCM) {
            throw new GeneralSecurityException("Unsupported format");
        }
        if (kidLength < 1 || kidLength > MAX_KID_BYTES
                || nonceLength != NONCE_BYTES
                || bodyLength < TAG_BYTES || bodyLength > MAX_BODY_BYTES) {
            throw new GeneralSecurityException("Invalid field length");
        }

        int headerLength = FIXED_HEADER + kidLength + nonceLength;
        if (record.length != headerLength + bodyLength) {
            throw new GeneralSecurityException("Length mismatch");
        }

        byte[] kidBytes = new byte[kidLength];
        buffer.get(kidBytes);
        String kid = new String(kidBytes, StandardCharsets.US_ASCII);
        if (!validKid(kid)) {
            throw new GeneralSecurityException("Invalid key ID");
        }
        byte[] nonce = new byte[nonceLength];
        buffer.get(nonce);

        SecretKey key = keyRing.get(kid);
        if (key == null) {
            throw new GeneralSecurityException("Unknown key ID");
        }
        requireAes128(key);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, nonce));
        cipher.updateAAD(record, 0, headerLength);
        return cipher.doFinal(record, headerLength, bodyLength);
    }

    private static String check(byte[] record, Map<String, SecretKey> keyRing) {
        try {
            open(record, keyRing);
            return "ACCEPTED";
        } catch (GeneralSecurityException e) {
            return "REJECTED";
        }
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey key = generator.generateKey();
        Map<String, SecretKey> keyRing = Map.of("key-A", key);
        byte[] plain = "Hello Java".getBytes(StandardCharsets.US_ASCII);
        byte[] record = seal(plain, key, "key-A");

        System.out.println("Round-trip: " + Arrays.equals(plain, open(record, keyRing)));
        System.out.println("Record bytes: " + record.length);

        byte[] nonceChanged = record.clone();
        nonceChanged[FIXED_HEADER + "key-A".length()] ^= 1;
        System.out.println("Nonce modified: " + check(nonceChanged, keyRing));

        byte[] tagChanged = record.clone();
        tagChanged[tagChanged.length - 1] ^= 1;
        System.out.println("Tag modified: " + check(tagChanged, keyRing));

        byte[] truncated = Arrays.copyOf(record, record.length - 1);
        System.out.println("Truncated: " + check(truncated, keyRing));
    }
}
```

Compile/run from the file's directory using JDK 17+:

```bash
javac --release 17 EnvelopeDemo.java
java EnvelopeDemo
```

Stdout (output is stable even though key and nonce are randomly generated):

```text
Round-trip: true
Record bytes: 55
Nonce modified: REJECTED
Tag modified: REJECTED
Truncated: REJECTED
```

**Explanation of key points:**

1. `KeyGenerator` creates an illustrative AES-128 key. In production, keys live outside the record; `keyRing` is a trusted `key_id → key` mapping used to read data encrypted with older keys. Never export keys into the envelope file.
2. `SecureRandom` generates a 96-bit nonce. This works for bounded record counts; it **does not guarantee zero nonce collisions** at huge scale or across multiple machines. For any AES-GCM key, enforce a nonce-uniqueness strategy, bound record counts, and rotate keys according to collision risk; multi-writer systems need coordination or distinct keys.
3. `GCMParameterSpec(128, nonce)` pins a 128-bit tag; JCA `Cipher.doFinal()` returns `ciphertext || tag` on encryption and verifies the tag on decryption. `updateAAD(header)` is invoked before processing ciphertext.
4. `open()` checks total size, magic/version/suite, lengths, charset, key ID, and **exact total byte count** before decrypting. Never infer remaining length from `available()` or trust unbounded lengths.
5. Flipping 1 byte in the nonce or tag causes the record to be rejected; dropping 1 byte makes `record.length` mismatch the declared length. The first two cases fail primarily at the **authentication tag**, while the last is rejected by the **parser** before invoking the cipher.
6. `requireAes128()` can inspect `key.getEncoded()` because the example uses exportable keys (`KeyGenerator`). Non-exportable HSM/KMS keys typically return `null`; when using them, validate key type/size via provider metadata and proper provider integration, **never treating `getEncoded() == null` as an invalid key**.
7. This is a small-record example holding the entire ciphertext in memory. Large data requires a dedicated **chunked authenticated format**, with chunk index/length/total-chunk count or authenticated end marker; never arbitrarily slice a GCM ciphertext and decrypt chunks as independent records.

The program initializes a fresh `Cipher` per record. Reusing a `Cipher` object must never lead to reusing the same **key + nonce** pair.

## 6. Bounding Lengths and Canonicalizing Bytes Are Security Requirements

### 6.1 Parse Untrusted Fields in a Safe Order

Recommended reading flow:

1. **Validate total input size** (at least 12 bytes and no larger than the maximum record limit). Never allocate memory from a file-supplied length before checking it.
2. Read the fixed first 12 bytes to check `magic`, `version`, `suite_id`, and the three length fields; use **unsigned** interpretation for 1-byte fields.
3. Check every `length` against **protocol-defined upper bounds**, against remaining available bytes, and guard additions against overflow before allocating.
4. Only after proving `record.length == fixed_header + kid_length + nonce_length + body_length`, extract `key_id`, `nonce`, and body.
5. Look up the candidate key from a trusted source, validate key/suite, supply exact original header bytes as AAD, **verify the tag successfully**, and only then pass plaintext to business logic.
6. Never rely solely on unauthenticated header state to grant permissions or persist durable state.

In the example, `body_length` is stored as 4 unsigned bytes yet Java reads it into a signed `int`. Because the valid bound is under 2 GiB, any value with the sign bit set is rejected by the range check; there is no need to allocate memory for huge unsigned numbers. Supporting formats above 2 GiB requires a dedicated **streaming parser** and checked `long` size arithmetic.

### 6.2 Encoding Must Be Unambiguous

Rules must be pinned in the spec rather than relying on system defaults:

- `ByteOrder.BIG_ENDIAN` or another explicitly stated byte order. Avoid mismatches across `DataInputStream`/`ByteBuffer` and other languages.
- `length` always measures **bytes in the chosen encoding**, never using `String.length()` as UTF-8 byte count.
- For free-form strings, mandate **canonical UTF-8** and define handling for invalid encodings, Unicode normalization, case rules, and field order. Our v1 example restricts `key_id` to ASCII to eliminate ambiguity.
- Never allow multiple encodings to represent the same semantic record if the format feeds signatures or hashing/canonicalization; avoid duplicate fields, unspecified order, or flexible whitespace/case.
- Never append trailing bytes, skip unknown fields, or default `version=0` when parsing fails.

When packing variable-length metadata fields for AAD or signatures, establish unambiguous boundaries such as `type || length || value` with canonical rules. Direct concatenation `userId || tenantId` can be ambiguous (`"ab" + "c"` equals `"a" + "bc"`). If using TLV/CBOR/Protocol Buffers, specify mandatory fields, duplicate-field handling, ordering/canonical encoding, and compatibility rules; **format version** must still define structural meaning.

### 6.3 Length Declared in Header Does Not Mean Content Is Authenticated

`body_length` tells the parser how many bytes to read, yet before tag verification an adversary can alter it. Therefore:

- **Bound first, authenticate second:** use lengths to reject malformed or resource-abusing records immediately, then include lengths in AAD to protect accepted data semantics.
- Avoid `new byte[untrustedLength]` before verifying `0 <= length <= MAX`.
- Avoid substituting `ciphertext.length` for a declared length field when the protocol requires consistency checks; truncated or padded files must be detected.
- For large files, enforce anti-overload rules for decryption, decompression (if any), and streaming parsing instead of holding everything in RAM.

## 7. Version Upgrades, Algorithm Changes, and Key Lifecycle

**Case 1: changing the algorithm while keeping layout.** When the system adds another suite later, assign a new ID and admit it to the allowlist only with a specification and test vectors. For instance, `suite_id=2` must spell out JCA transformation, key/nonce/tag sizes, body format, and tests; never read `suite_id=2` and infer the algorithm from names or provider defaults.

**Case 2: changing the record layout.** For example, adding `context_id`, `created_at`, `KDF parameters`, or multiple ciphertext segments. Design `version=2` with its own layout and parser. Each version's version bytes and metadata fields must be authenticated within the corresponding AAD or signature scope. Never guess versions by byte length, accept missing mandatory fields, or allow silent downgrade ("retry v1 until something works").

**Case 3: key rotation.** Generate a new write key, assign a new `key_id`, and keep old read keys while historical data remains readable. When decrypting and re-encrypting, generate a **fresh nonce for the new key**, authenticate the old record first, and update/swap state safely to avoid data loss; once migration completes, revoke old read keys per policy. `key_id` must be bound to **tenant/purpose/usage permissions** in the trusted keystore, disallowing arbitrary cross-routing.

**Case 4: encrypting from a password instead of a generated key.** Another format may need **KDF ID, salt, iteration/work factor, and KDF parameters** to re-derive the key. Those fields require explicit encoding, lengths, cost limits, and authentication. **KDF salts** and **AEAD nonces** serve different purposes; never swap one for the other. Never place passwords, raw keys, or sensitive secrets in the header.

**Anti-downgrade:** Permitting v1 reads for historical data is a **compatibility policy**; accepting an obsolete suite in a new protocol flow is a separate security decision. Write new records with the approved version/suite, scope legacy support tightly, and record deprecation timelines.

## 8. Mandatory Tests for Readers and Writers

| Case | Expected outcome | Why |
| --- | --- | --- |
| Round-trip empty, short, and max 1 MiB plaintexts | Decrypted bytes match byte-for-byte | Valid body range from 16-byte tag up to published limit |
| Modify one byte in `nonce`, `key_id`, or body/tag | Rejected | Header and ciphertext/tag cannot be silently swapped |
| Modify `magic`, `version`, or `suite_id` to unsupported values | Rejected immediately | No silent fallback |
| `kid_length=0`, `kid_length=255`, `nonce_length != 12` | Rejected prior to allocation | Bounds and suite invariants |
| Negative `body_length` when read as `int`, oversized, or smaller than tag | Rejected prior to allocation | Prevents integer overflow / memory DoS |
| File missing 1 byte or having 1 extra byte | Rejected | Exact record framing |
| Unknown `key_id` or wrong key | Fails decryption | Only trusted keyring keys accepted |
| Right key but wrong external context (if format has context binding) | Authentication fails | Prevents cross-context record transplantation |
| Multiple records with same key/nonce | Prevented at writer side and nonce strategy verified | AES-GCM requires unique nonce per key |
| V2/new schema or new suite | Accepted only by the matching version-aware parser | Controlled upgrades and explicit compatibility |

Beyond unit tests, maintain **test vectors** containing header hex, plaintext, test key, fixed nonce **strictly for tests**, and expected ciphertext/tag; verify across Java and other languages if the protocol is cross-platform. Never use fixed test-vector keys/nonces for real encryption.

## 9. Common Design Mistakes

1. **No version field:** old records are parsed using a new default format or algorithm and become unrecoverable after upgrades.
2. **Recording only `"AES"` or `"RSA"`:** omits mode, padding, key size, tag/nonce; providers may differ in defaults. Authenticated encryption should specify an explicit transformation like `AES/GCM/NoPadding`.
3. **Reading an algorithm string from the file and passing it straight to JCA:** lets untrusted input choose the algorithm. Use **numeric suite ID → fixed allowlist**.
4. **Unbounded lengths or wrong units:** parser can over-allocate, misframe, or accept truncated fields. Use byte lengths, unsigned parsing, checked arithmetic, and exact consumption.
5. **Metadata left outside AAD/signature:** allows swapping `key_id`, version, context, or parameters without full protection; bind the exact bytes.
6. **Reusing an AES-GCM nonce with the same key:** severely breaks confidentiality and integrity. Never generate with `Random`; even `SecureRandom` needs record limits and collision-prevention strategies.
7. **Streaming out partial plaintext before tag verification:** callers may act on unauthenticated data before the tag fails. Release plaintext only after `doFinal` succeeds.
8. **Treating Base64, magic, CRC, or checksums as security:** they aid transport and accidental-error detection, **not authentication tags or signatures**.
9. **Using Java object serialization as an ad-hoc wire format:** class/JDK coupled, introduces deserialization risk, and lacks a clean cryptographic schema. Use a versioned, bounds-checked binary format.
10. **Confusing authentication with replay protection or sender identity:** AES-GCM proves a record is valid for a key holder; preventing replay or proving a specific signer requires additional mechanisms.

## 10. Checklist Before Storing or Publishing a Format

- [ ] Formal byte specification exists: magic, version, suite registry, field order, endianness, charset, lengths/bounds, and error rules.
- [ ] Each suite fully specifies algorithm/mode/padding, key type and size, nonce, tag, and ciphertext framing.
- [ ] All critical header bytes are bound into AAD (or signature); required context/purpose is authenticated too.
- [ ] Parser rejects unknown version/suite, malformed/truncated/trailing bytes, duplicate fields, and any out-of-bounds length **before large allocations**.
- [ ] Records are never trusted for keys or permissions; key IDs only look up candidate keys in a trusted registry.
- [ ] Nonce uniqueness, key rotation, compatibility, and anti-downgrade policies are explicitly designed.
- [ ] Test vectors, boundary tests, tamper tests, multi-runtime/provider tests, and replay handling (if needed) are in place.
- [ ] Writes are crash/restart-safe; for chunked formats, chunk ordering, chunk count, and end markers are all authenticated.

## Primary References

- [RFC 5116 — An Interface and Algorithms for Authenticated Encryption](https://www.rfc-editor.org/rfc/rfc5116.html): AEAD model, unambiguous AAD, nonce uniqueness; defines AES-128-GCM with 12-byte nonce and 16-byte tag.
- [NIST SP 800-38D — Galois/Counter Mode (GCM) and GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final): requirements for GCM, IV/nonce, and authentication.
- [Java SE 17 — `javax.crypto.Cipher`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): transformations, `updateAAD`, `doFinal`, and authentication tags.
- [Java SE 17 — `GCMParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): `tLen` in bits and IV/nonce passed to GCM.
- [Java SE 17 — `ByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): byte read/write rules and byte order.

**Remember:** A secure cryptographic format must be **self-describing enough to parse**, while **never trusting self-described data until boundaries are checked and authentication succeeds**. Version, length, and algorithm ID underpin evolvability, while AAD/tag, nonce discipline, and parser validation underpin security.
