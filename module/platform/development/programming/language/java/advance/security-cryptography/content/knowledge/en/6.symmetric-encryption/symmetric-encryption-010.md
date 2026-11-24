# 6.10 Handling `AEADBadTagException`, `BadPaddingException`, and Truncated Ciphertext

## Objectives

After this lesson, you can accurately identify the meaning of `AEADBadTagException` and `BadPaddingException` in the Java Cryptography Architecture (JCA/JCE), distinguish **truncated ciphertext** from **AEAD authentication failure**, design a ciphertext envelope with enough information for length validation, build an AES-GCM decryption flow that never releases plaintext before the tag is verified, and handle errors safely without leaking extra information to an adversary.

This lesson belongs to **6. Symmetric Encryption**. The focus is `AES/GCM/NoPadding`, though you also need to recognize that `BadPaddingException` appears in legacy modes such as `AES/CBC/PKCS5Padding`. The goal is **accurate diagnosis, safe rejection, and protocol consistency**; an exception alone is not conclusive proof of whether data was modified, truncated in transit, decrypted with the wrong key, or paired with mismatched parameters.

## 1. What Is Authenticated in AES-GCM?

AES-GCM is an **AEAD (Authenticated Encryption with Associated Data)** mode: it protects content secrecy (confidentiality) while simultaneously verifying the integrity and authenticity of the ciphertext and associated data (integrity/authenticity), provided the key, nonce, and usage are proper.

One AEAD encryption uses:

- **Secret key** `K`: the exact same matching key on both encryptor and decryptor.
- **Nonce/IV** `N`: does not need to be kept secret, yet **must never repeat under the same AES-GCM key**. In practice, a random 12-byte (96-bit) nonce from a cryptographic RNG is commonly used.
- **Plaintext** `P`: data needing confidentiality.
- **AAD**: data that is not encrypted yet still participates in authenticity checks, such as envelope version or request context.
- **Ciphertext** `C` and **authentication tag** `T`: outputs the receiver must verify in full before trusting plaintext.

In Java, the common decryption call is:

```java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, nonce));
cipher.updateAAD(aad);
byte[] plaintext = cipher.doFinal(ciphertextAndTag);
```

This is an **illustrative in-method snippet**, not a standalone program; it requires imports for `javax.crypto.Cipher` and `javax.crypto.spec.GCMParameterSpec`, along with properly formatted `key`, `nonce`, `aad`, and `ciphertextAndTag`. With `GCMParameterSpec(128, nonce)`, the tag is **128 bits = 16 bytes**. JCE expects ciphertext **followed immediately by the tag** in the decryption input: `C || T`. Some protocols store the tag in a separate field; when using `Cipher.doFinal`, concatenate them in the exact order expected by the provider.

**"NoPadding" does not mean there is no authentication tag.** GCM does not use CBC's PKCS#5/#7 padding, yet still requires processing the authentication tag. A missing or wrong tag means the receiver must not accept the plaintext.

### Envelope and Minimum Overhead

To transmit and receive safely, both sides must agree on a format. Illustrative example in this lesson:

```text
+------------+----------------+----------------------+-------------------+
| version    | nonce          | ciphertext           | GCM tag           |
| 1 byte     | 12 bytes       | 0..n bytes           | 16 bytes          |
+------------+----------------+----------------------+-------------------+
```

Minimum overhead is **1 + 12 + 16 = 29 bytes**; even for empty plaintext, the 16-byte tag must still be present. Leading envelope bytes are not encrypted themselves, yet **version must be passed into AAD** to protect against tampering while keeping the format extensible. The example also passes a shared `context` into AAD, such as `"POST /orders"`.

Real protocols may also need key IDs, lengths, algorithms, version parameters, and content types. They must have unambiguous encodings, size bounds, proper cryptographic binding, and validation before parsing input data.

## 2. Inheritance Relationship Between Java Exceptions

Important inheritance hierarchy:

```text
Exception
  └─ GeneralSecurityException
       ├─ BadPaddingException
       │    └─ AEADBadTagException
       ├─ IllegalBlockSizeException
       ├─ InvalidKeyException
       ├─ InvalidAlgorithmParameterException
       └─ NoSuchAlgorithmException
```

`javax.crypto.AEADBadTagException` **extends** `javax.crypto.BadPaddingException`. Therefore:

- `catch (BadPaddingException e)` also catches `AEADBadTagException`.
- To handle them distinctly in inner layers, you must catch **`AEADBadTagException` before `BadPaddingException`**; reversing the order makes the specific branch unreachable and fails Java compilation.
- `IllegalBlockSizeException` is a **sibling** branch under `GeneralSecurityException`, not a subclass of `BadPaddingException`.
- Application-level format checks throwing e.g. `IllegalArgumentException` are outside the checked exception hierarchy above; establish clear error mapping at the protocol boundary.

| Exception | Where It Typically Occurs | What Can Be Concluded |
| --- | --- | --- |
| `AEADBadTagException` | `Cipher.doFinal` during AEAD decryption when tag verification fails | **Failed to authenticate** the supplied combination of key, nonce, AAD, ciphertext, and tag |
| `BadPaddingException` (base type) | `doFinal` in padded modes like CBC/PKCS5Padding; some providers may throw a more general error on AEAD | Final padding is invalid or provider decryption failed; insufficient alone to pinpoint root cause |
| `IllegalBlockSizeException` | `doFinal` when input does not match block/mode length rules | Input violates block processing constraints; possibly truncated, wrong mode, or bad framing |
| `InvalidKeyException` | `Cipher.init` | Key has wrong type, is unsuitable, or is rejected by provider/policy |
| `InvalidAlgorithmParameterException` | `Cipher.init` | IV/nonce/parameters invalid or unsupported by provider |
| `NoSuchAlgorithmException` / `NoSuchPaddingException` | `Cipher.getInstance` | Transformation not provided by the selected provider |

**Do not conclude from the exception name alone that an "attack" occurred.** For GCM, `AEADBadTagException` can stem from an accidental bit flip, wrong key, wrong nonce, mismatched AAD, missing tag, truncated packet, or deliberate forgery. All of these share the same cryptographic symptom: authentication failed.

Specifically, `AEADBadTagException` is the more precise exception for AEAD authentication failures on API-compliant providers; however, some providers or API wrappers may surface less specific errors. Applications should handle `GeneralSecurityException`/format errors appropriately at boundaries rather than relying on exception message strings or a single provider's quirks.

## 3. What Forms Can Truncated Ciphertext Take?

"Truncated ciphertext" can occur at the **transport layer**, the **envelope format layer**, or inside the **ciphertext/tag** itself:

1. **Missing part of the header:** not enough bytes to read version or nonce; reject before initializing `Cipher`. For instance, a 10-byte envelope cannot hold a 12-byte nonce and 16-byte tag.
2. **Full header present, yet insufficient bytes for the tag:** with a `1 + 12 + C + 16` byte layout, any input under 29 bytes is guaranteed invalid. Reject via length/bounds checks before calling `doFinal`.
3. **Missing a few trailing bytes while remaining at least 29 bytes long:** the application may not spot this immediately from total length if expected message length is unknown. GCM reads the last 16 bytes currently present as the tag; that tag is wrong, so **verification fails**, typically throwing `AEADBadTagException`.
4. **Missing middle ciphertext bytes or reordered bytes:** tag verification mismatches, typically also raising an AEAD error.
5. **Misreading multi-message framing boundaries:** concatenating two records or splitting mid-record due to bad framing produces similar authentication failures. Never treat `Cipher` creation succeeding as proof the record is complete.

Because different faults share the same symptom, **you cannot reliably tell apart "truncated", "tampered", "wrong AAD", and "wrong key" solely from `AEADBadTagException`**. To detect missing bytes at the protocol level, use explicit framing/length headers (e.g., bounded length prefix, controlled Content-Length, protocol record length), read the full record, and compare against actual bytes received.

### When Length Is Known Ahead of Time

If the protocol provides a `recordLength` field from a trusted/validated source, verify:

```text
receivedBytes == expectedRecordLength
expectedRecordLength >= minimumEnvelopeLength
expectedRecordLength <= maximumAllowedRecordLength
```

A length field is **unauthenticated** data if it sits outside the tag; enforce bounds on it and bind it into authenticated metadata if needed. Never allocate buffers directly from an unbounded client-supplied length. Receiving fewer bytes than expected indicates a **truncated record** at the transport layer; even then, responses returned to clients must not leak details useful for exploitation.

### When Length Is Unknown Ahead of Time

Read the complete record per the protocol's EOF/framing rules before decrypting. `doFinal` verifies the tag over **exactly the bytes supplied**. If input is shorter than the minimum envelope, you can classify it as malformed/truncated immediately; if it meets the minimum length yet is missing a slice, authentication failure is the right verdict, while the physical cause is diagnosed via logs/transport metrics.

## 4. Runnable Java 17 Example: Testing Modified or Truncated GCM Ciphertext

The program below intentionally creates a random AES key and a random nonce **for each encryption**, encoding the record as `[version:1][nonce:12][ciphertext][tag:16]`. `version` and `context` serve as AAD. Error handling returns status codes **strictly to teach internal classification**; on public APIs, collapse all invalid-record errors into a uniform authentication-failure response.

Create the exact file **`AeadFailuresDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.BadPaddingException;
import javax.crypto.Cipher;
import javax.crypto.IllegalBlockSizeException;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class AeadFailuresDemo {
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int TAG_BYTES = TAG_BITS / 8;
    private static final int HEADER_BYTES = 1 + NONCE_BYTES;
    private static final byte VERSION = 1;
    private static final SecureRandom RANDOM = new SecureRandom();

    private static byte[] encrypt(SecretKey key, byte[] plaintext, byte[] context)
            throws GeneralSecurityException {
        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(new byte[] { VERSION });
        cipher.updateAAD(context);
        byte[] ciphertextAndTag = cipher.doFinal(plaintext);

        byte[] envelope = new byte[HEADER_BYTES + ciphertextAndTag.length];
        envelope[0] = VERSION;
        System.arraycopy(nonce, 0, envelope, 1, NONCE_BYTES);
        System.arraycopy(ciphertextAndTag, 0, envelope, HEADER_BYTES,
                ciphertextAndTag.length);
        return envelope;
    }

    private static byte[] decrypt(SecretKey key, byte[] envelope, byte[] context)
            throws GeneralSecurityException {
        if (envelope == null || envelope.length < HEADER_BYTES + TAG_BYTES) {
            throw new IllegalArgumentException("Invalid envelope length");
        }
        if (envelope[0] != VERSION) {
            throw new IllegalArgumentException("Unsupported version");
        }

        byte[] nonce = Arrays.copyOfRange(envelope, 1, HEADER_BYTES);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(new byte[] { envelope[0] });
        cipher.updateAAD(context);
        return cipher.doFinal(envelope, HEADER_BYTES,
                envelope.length - HEADER_BYTES);
    }

    private static String status(SecretKey key, byte[] envelope, byte[] context) {
        try {
            decrypt(key, envelope, context);
            return "ACCEPT";
        } catch (AEADBadTagException e) {
            return "REJECT_AUTH";
        } catch (BadPaddingException | IllegalBlockSizeException e) {
            return "REJECT_CRYPTO";
        } catch (IllegalArgumentException e) {
            return "REJECT_FORMAT";
        } catch (GeneralSecurityException e) {
            return "REJECT_CRYPTO_SETUP";
        }
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey key = generator.generateKey();

        byte[] context = "POST /orders".getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "pay=100".getBytes(StandardCharsets.UTF_8);
        byte[] envelope = encrypt(key, plaintext, context);

        byte[] changedTag = envelope.clone();
        changedTag[changedTag.length - 1] ^= 1;

        byte[] changedNonce = envelope.clone();
        changedNonce[1] ^= 1;

        byte[] truncated = Arrays.copyOf(envelope, envelope.length - 1);
        byte[] tooShort = Arrays.copyOf(envelope,
                HEADER_BYTES + TAG_BYTES - 1);

        byte[] changedVersion = envelope.clone();
        changedVersion[0] = 2;

        System.out.println("valid: " + status(key, envelope, context));
        System.out.println("tag changed: " + status(key, changedTag, context));
        System.out.println("nonce changed: " + status(key, changedNonce, context));
        System.out.println("tail truncated: " + status(key, truncated, context));
        System.out.println("too short: " + status(key, tooShort, context));
        System.out.println("AAD changed: " + status(key, envelope,
                "POST /other".getBytes(StandardCharsets.UTF_8)));
        System.out.println("version changed: "
                + status(key, changedVersion, context));
        System.out.println("round-trip: "
                + Arrays.equals(plaintext, decrypt(key, envelope, context)));
    }
}
```

Compile and run:

```bash
javac --release 17 AeadFailuresDemo.java
java AeadFailuresDemo
```

**Stdout on the test JDK with a 128-bit-tag AES-GCM provider** (compiled in Java 17 mode):

```text
valid: ACCEPT
tag changed: REJECT_AUTH
nonce changed: REJECT_AUTH
tail truncated: REJECT_AUTH
too short: REJECT_FORMAT
AAD changed: REJECT_AUTH
version changed: REJECT_FORMAT
round-trip: true
```

**Specific interpretation:**

- `valid: ACCEPT` and `round-trip: true` show that the matching key, nonce, AAD, and ciphertext/tag recover the original plaintext.
- Flipping one **tag** bit, one **nonce** bit, or altering **AAD** causes GCM verification to fail; on the tested provider, Java throws `AEADBadTagException` and the helper returns `REJECT_AUTH`.
- Truncating one trailing byte from `ciphertext+tag` while still leaving at least 29 bytes for the envelope makes the interpreted trailing tag invalid; `REJECT_AUTH` is an **authentication failure**, which alone cannot identify where the byte was lost.
- `too short` is only 28 bytes: at least one byte short of holding version/nonce/tag, so application code rejects it **before calling the provider**.
- Changing version to `2` is caught by schema validation. When a valid version is altered in a way not caught by the parser, binding version into AAD ensures the change still mismatches the tag.
- Even though the nonce is random—making the raw ciphertext bytes differ between runs—the **outcome categories** above remain stable under the tested configuration. Another provider might raise a broader exception class for certain errors; error handling should not rely on exact exception message text.

**Demo design note:** the `KeyGenerator` key is an ephemeral in-memory test key; the format and `context` are illustrative only. Real applications must define context encoding and message bounds, store keys in a proper key manager, use a **unique nonce per encryption under the same key**, and ship nonce/tag alongside ciphertext. Never use modified ciphertext to "recover" partial data or guess a missing nonce.

## 5. Writing `catch` in the Right Order and Mapping Errors at Boundaries

When logging internal diagnostics for the `Cipher` engine, a typical pattern is:

```java
try {
    byte[] plaintext = cipher.doFinal(ciphertextAndTag);
    // Process plaintext only after doFinal succeeds.
} catch (AEADBadTagException e) {
    // GCM/AEAD: tag failed verification.
} catch (BadPaddingException e) {
    // Padding error or general decryption error per provider.
} catch (IllegalBlockSizeException e) {
    // Input violates block/mode length requirements.
}
```

This is only an **illustrative block**: `cipher` has already been initialized with valid key, IV/AAD; `ciphertextAndTag` is a `byte[]`; the exception classes must be imported from `javax.crypto`. Reversing the order by catching `BadPaddingException` before `AEADBadTagException` makes the narrower branch unreachable and will not compile.

### External Responses Should Be Uniform

Suppose an API accepts user-submitted ciphertext; internally the system can classify:

| Internal Code | Case | External Response |
| --- | --- | --- |
| `MALFORMED_ENVELOPE` | Missing header/tag, invalid version, anomalous size field | `Invalid encrypted payload` |
| `AUTHENTICATION_FAILED` | GCM tag verification failed | `Invalid encrypted payload` |
| `DECRYPTION_FAILED` | Provider reported padding/block error on decrypt | `Invalid encrypted payload` |
| `KEY_OR_PROVIDER_CONFIG_ERROR` | Key/provider misconfigured or unavailable | Generic service error, revealing no internal keys/algorithms |

Exact HTTP status codes depend on your API contract; what matters is **never building a detailed distinguishing oracle** such as "tag wrong at byte 7", "right key but bad padding", "valid nonce", or returning unauthenticated plaintext. Applications may log error codes, received byte counts, format version, and correlation IDs to protected operational channels, yet **never log secret keys, plaintext, tokens, or sensitive full ciphertexts/tags**.

For deployment or missing-provider errors, monitor and fix configuration properly. **Never auto-fallback** from AES-GCM to AES-CBC, shrink tag length, drop AAD, or brute-force keys/nonces just to "make decryption work somehow".

## 6. How Does `BadPaddingException` in `AES-CBC/PKCS5Padding` Differ from GCM?

A legacy system might use:

```java
Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
```

That line only obtains the engine—it **has not encrypted/decrypted or set a key/IV yet**. In padded CBC:

- Plaintext is padded to a multiple of the AES block size (16 bytes).
- The receiver must validate and strip padding after decrypting the final block.
- If the trailing decrypted bytes **do not form valid padding**, the provider typically throws `BadPaddingException`.
- If input bytes do not align to block boundaries, the provider may throw `IllegalBlockSizeException`; the exact exception depends on the provider and operation.
- Tampered ciphertext, wrong key, or an incomplete record **can** trigger these errors; yet CBC can also return garbage plaintext **without throwing an exception** if padding bytes happen by chance to look valid.

Therefore, **CBC + padding does not provide authenticity merely by checking padding**. Returning distinguishable responses between "valid/invalid padding" can create a dangerous *padding oracle* in unauthenticated encryption systems. New systems should prefer AEAD such as AES-GCM; legacy systems must audit their authentication protocol and establish a strict migration plan. Never "fix" padding errors by dropping `PKCS5Padding`, zero-padding manually, truncating blocks, stripping trailing bytes, or returning partially decrypted data.

### Why Does `BadPaddingException` Still Appear with GCM?

Because of Java's API inheritance model, `AEADBadTagException extends BadPaddingException`. That is an **exception-taxonomy design detail**, not an indication that GCM uses PKCS#5 padding. If middleware catches only `BadPaddingException`, it may lump GCM tag-verification failures together with CBC padding errors. When analyzing logs, always check the actual **transformation** and **provider** used.

## 7. Plaintext Before Verification: A Serious Streaming Mistake

With AEAD, plaintext is trustworthy only once the **authentication tag has been verified successfully**. Some modes/providers can emit temporary plaintext bytes from `Cipher.update(...)` before `doFinal(...)`, while the tag has not yet been checked. Those bytes are **unauthenticated data**.

Safety rules:

1. **Never** pass temporary plaintext to clients, business parsers, queues, databases, or execution engines before verification completes.
2. For small messages, use `Cipher.doFinal(...)` over the full ciphertext/tag and return data only when the call succeeds.
3. For large messages, if an API/provider emits bytes prior to verification, quarantine them (in memory or a controlled temporary file) and publish/commit **only after `doFinal` succeeds**; wipe/discard untrusted data on failure.
4. Never use partial output to update state, release payments, decompress data in ways causing side effects, or infer "the first bytes decrypted so the key must be right".

**Note on `CipherInputStream`:** Java documentation notes that this class may catch integrity-checking exceptions such as `BadPaddingException` without cleanly rethrowing them to callers; consequently, it **may be unsuitable for authenticated decryption** such as GCM. Whenever detecting tag failure is mandatory, use `Cipher` directly and manage unauthenticated output under explicit policy.

Decrypting a large file straight into the destination file is unsafe if another reader can read it immediately. Prefer an isolated temporary file inaccessible to other apps, decrypt and verify in full, and only then **atomically rename/commit if the filesystem supports it**; on failure, delete/wipe the temporary file per policy.

## 8. Designing Framing to Handle Truncated Ciphertext Reliably

### 8.1 Define One Record Before Decrypting

Specify how many bytes constitute **one record**, input bounds, and record count limits. For example:

```text
recordLength (4 bytes, unsigned, network byte order)
version (1 byte)
nonce (12 bytes)
ciphertext (variable)
tag (16 bytes)
```

This length layout is only a framing example—**not** the format from `AeadFailuresDemo` (which accepts a single envelope directly). The application reads exact `recordLength` bytes before decrypting, rejecting early EOF or oversized lengths. If a length field drives buffer allocation, validate it against upper bounds and guard against integer overflow when adding header/tag sizes.

When critical metadata sits outside the ciphertext, bind it into AAD and explicitly specify field order, field lengths, and schema version. If a protocol carries record length, header version, key ID, and algorithm, validate all of them against an allowlist; any fields affecting payload meaning must also be authenticated properly.

### 8.2 Never "Fix" a Truncated Record by Guessing the Tag

A common mistake on seeing `AEADBadTagException` is trying to append zero bytes, chop off the last 16 bytes, swap nonces, alter AAD, or decrypt partially. Those hacks alter the original data/protocol and never restore an authentic ciphertext. When transmission is incomplete, the right fix is **re-reading from a trusted source** via protocol-level retries using a complete fresh record and re-verifying from scratch.

If retrying a **decryption** on the same record with the same key/AAD is needed for diagnostics, the security outcome will not differ; never loop through candidate keys/tags to silently bypass authentication. For **encryption**, never retry by encrypting a different plaintext under the same AES-GCM key+nonce.

### 8.3 Stick to the Committed Format and Sizes

If you use a 128-bit GCM tag when encrypting, the receiver must expect an exact 128-bit tag length. Never take `length - 16` to slice the tag without first confirming header, trailer, and framing are valid; never accept a truncated tag and compare only leading bytes supplied by an attacker. If a protocol supports shorter tags, that must be an **explicit, security-reviewed design decision** agreed upon by sender and receiver and communicated unambiguously—never an error-recovery fallback.

## 9. Step-by-Step Failure Investigation Workflow

When investigating an `AEADBadTagException`/`BadPaddingException` in a real system, check in order:

1. **Check actual transformation:** `AES/GCM/NoPadding` or `AES/CBC/PKCS5Padding`? If GCM, verify tag length and AAD; if CBC, assess padding oracle risks and missing authentication.
2. **Check byte framing:** total byte count, header/version, nonce/tag byte counts, record length, and whether the stream hit premature EOF. Reject short records before crypto steps when possible.
3. **Verify key selection:** key ID, rotation version, provider/keystore; never log keys. With the wrong key, GCM tag mismatch looks identical to modified ciphertext.
4. **Verify nonce/IV:** both sides must pass identical nonce bytes; a 12-byte nonce and 16-byte tag are this lesson's format choice, not something to guess from ciphertext if a protocol differs.
5. **Verify AAD:** exact bytes and order, encoding, version, and request context. A single differing AAD byte breaks tag verification.
6. **Check ciphertext/tag and transport:** bad hex/Base64 decoding, newlines, whitespace, reversed bytes, charset transcoding, record truncation, or buffer sizing bugs?
7. **Isolate provider behavior with a standalone test:** run a round-trip with test key/nonce/AAD and known test vectors; never mutate production data to silence errors.
8. **Audit data emission policy:** publish plaintext only when `doFinal` succeeds; any exception must roll back/delete temporary output.

### Quick Diagnostic Table

| Symptom | Possible Cause | Action |
| --- | --- | --- |
| GCM throws `AEADBadTagException` | Mismatched tag, key, nonce, AAD, or ciphertext; modified/truncated record | Reject plaintext, verify format/byte sources with test data, keep public responses uniform |
| GCM lacks at least 16 tag bytes per format | Input below minimum length | Block before `Cipher.init/doFinal`, report malformed/truncated internally |
| Ciphertext truncated by 1 byte yet still meets minimum | Trailing bytes are misread as the tag and fail verification | Reject record; check expected length/EOF |
| CBC throws `BadPaddingException` | Invalid padding, wrong key, altered ciphertext, format error | Never expose this distinction publicly; review CBC design and migrate to AEAD where suitable |
| CBC throws `IllegalBlockSizeException` | Input unaligned to block size or mode | Check framing, block size, data type |
| CBC throws no exception yet plaintext is garbage | Padding happened to look valid; no integrity check exists | Never equate successful decryption with authenticity; use AEAD/MAC |
| `InvalidAlgorithmParameterException` | Invalid nonce/IV/tag length or rejected by provider | Verify transformation, `GCMParameterSpec`, and provider |
| Results differ across two environments | Different provider/JDK/config or input bytes | Log version, provider, transformation, record size, test vector; never log secret keys |
| GCM decryption stream leaks data despite bad tag | Unverified intermediate output or wrapper swallowing auth errors | Never publish plaintext before `doFinal`; avoid error-swallowing wrappers |

## 10. Service Integration Checklist

- [ ] Protocol specifies algorithm/mode, nonce/tag sizes, byte order, version, and AAD.
- [ ] AES-GCM uses **non-repeating nonces under the same key**; keys are managed properly and never logged.
- [ ] Receiver checks version, minimum total length, size caps, and framing before decrypting.
- [ ] Do not assume every tag error is active tampering; distinguish operational causes via controlled logs/transport metrics.
- [ ] Catch `AEADBadTagException` before `BadPaddingException` wherever fine-grained internal classification is needed.
- [ ] Never leak padding/tag/key details on public APIs.
- [ ] Plaintext is used or published **only after tag verification succeeds**.
- [ ] Tests cover round-trip, single-bit flips in ciphertext/tag/nonce, wrong AAD, truncated ciphertext, and missing headers.
- [ ] When storing multiple records, each record has clear boundaries and independent authentication; records never bleed into one another.
- [ ] Never fall back to an unauthenticated mode, strip tags, or patch corrupted data.

## 11. Practice Exercises

1. Run `AeadFailuresDemo.java`. Explain why modifying the tag, nonce, and AAD all produce `REJECT_AUTH` despite differing internal causes.
2. Change `Arrays.copyOf(envelope, envelope.length - 1)` to truncate down to **28 bytes**. Why does the status shift from `REJECT_AUTH` to `REJECT_FORMAT` in the example?
3. Add a `keyId` field (byte) to the envelope header. Design key-lookup rules and how to include that field in AAD; how do you prevent an attacker from steering which key gets selected?
4. When receiving 32 MiB of ciphertext over a stream, describe how to stage decrypted output in a temporary file and publish it only after tag verification succeeds.
5. Contrast the implications of `BadPaddingException` in CBC versus `AEADBadTagException` in GCM. Why is exception-free CBC decryption still insufficient to trust plaintext?
6. Design a test suite covering invalid header versions, oversized records, truncated ciphertext bytes, corrupted Base64, and different providers; indicate which errors the parser should block and which should be left to `Cipher.doFinal` verification.

## Official References

- [Java SE 17 — `AEADBadTagException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/AEADBadTagException.html): AEAD tag authentication failure and inheritance from `BadPaddingException`.
- [Java SE 17 — `BadPaddingException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/BadPaddingException.html): padding errors on decryption and related exceptions.
- [Java SE 17 — `IllegalBlockSizeException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/IllegalBlockSizeException.html): input unsuitable for block operations.
- [Java SE 17 — `Cipher`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): transformations, `updateAAD`, `doFinal`, GCM handling, and exceptions.
- [Java SE 17 — `GCMParameterSpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): tag length (bits) and IV/nonce.
- [Java SE 17 — `CipherInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/CipherInputStream.html): cautions when used with authenticated decryption modes.
- [NIST SP 800-38D — GCM/GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final): GCM specification, tags, and IV/nonce requirements.