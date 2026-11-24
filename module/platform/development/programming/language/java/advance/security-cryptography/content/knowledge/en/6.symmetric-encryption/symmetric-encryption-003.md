# 6.3 Generating AES Keys with KeyGenerator and Constructing Keys from Valid Material

## 1. Nature of AES Keys

AES is a **symmetric** encryption algorithm: both the encryptor and decryptor need the same secret key. In JCA/JCE, an AES key is commonly represented by the `javax.crypto.SecretKey` interface and passed to `Cipher.init(...)`.

| AES | Length in Bits | Raw Key Bytes |
| --- | ---: | ---: |
| AES-128 | 128 bit | 16 byte |
| AES-192 | 192 bit | 24 byte |
| AES-256 | 256 bit | 32 byte |

AES always has a **128-bit block size**, regardless of whether AES-128/192/256 is used. Key length is also distinct from the IV/nonce (AES-GCM typically uses a 12-byte IV) and authentication tag (typically 128 bits). **The key must remain secret**; the IV does not need to be secret, yet **must never repeat when encrypting under the same key**.

Distinguish three input scenarios:

1. **Need to generate a fresh random key:** use `KeyGenerator`.
2. **Already have exact raw AES key bytes from a trusted source:** validate 16/24/32 bytes, then construct a `SecretKeySpec`.
3. **Only have a password or master secret:** perform proper **key derivation**; do not wrap raw password bytes directly into a key.

Having the right length only proves the key has a valid shape. A 32-byte all-zero array or a predictable password is not secure merely because it is 32 bytes long.

## 2. Generating a New AES Key with KeyGenerator

`KeyGenerator` is the JCA engine for creating secret keys. The illustrative snippet sits inside a Java method:

```java
KeyGenerator generator = KeyGenerator.getInstance("AES");
generator.init(256, new SecureRandom());
SecretKey aesKey = generator.generateKey();
```

Required imports: `javax.crypto.KeyGenerator`, `javax.crypto.SecretKey`, and `java.security.SecureRandom`. The complete program in Section 5 contains the full source code.

- `getInstance("AES")` selects an engine/provider supporting AES; `NoSuchAlgorithmException` occurs if the runtime does not support it.
- `init(256, random)` configures **256 bits**, not 256 bytes. Valid AES key sizes are 128/192/256 bits; a provider may enforce its own restrictions.
- `SecureRandom` produces cryptographic randomness. Never use `java.util.Random`, `Math.random()`, or a fixed seed to try generating reproducible keys.
- `generateKey()` returns a new `SecretKey`; it does not generate per-record IVs or persist the key across restarts.
- Call `init` explicitly to avoid relying on a provider's default key size choice. The `init(int)` overload may use a provider-chosen RNG, whereas the overload taking `SecureRandom` makes the randomness source explicit.

Wrong: `new SecretKeySpec(new byte[32], "AES")` because `new byte[32]` is all **zeros**. If a custom protocol requires generating raw bytes directly, you can use `SecureRandom.nextBytes(raw)` with exact 16/24/32 bytes; for standard JCA usage, `KeyGenerator` is clearer and easier to maintain.

## 3. Constructing a Key from a Valid Raw Key with SecretKeySpec

Suppose an application receives raw key bytes from a key vault or authenticated protocol. Validate before constructing the key:

```java
// Illustrative snippet; raw is a byte[] from a trusted source.
if (raw == null ||
        (raw.length != 16 && raw.length != 24 && raw.length != 32)) {
    throw new IllegalArgumentException("Invalid AES key length");
}
SecretKey key = new SecretKeySpec(raw, "AES");
```

`SecretKeySpec` **copies** the key bytes and attaches the algorithm name. It **does not generate randomness, derive keys, or assess entropy**. Its constructor may accept material whose length is incompatible with AES; `Cipher.init` is what may throw `InvalidKeyException`. Therefore, validate length at the ingestion boundary and handle provider errors as well.

**Encodings are not raw bytes:**

- A raw AES-256 key is **32 bytes**; its **hex form is 64 characters**, since each byte takes two characters.
- Base64 of 32 bytes is typically **44 characters**, including `=` padding. Hex/Base64 **are only representations**, not protective encryption.
- Importing from an external system: `Base64.getDecoder().decode(base64Key)` or `HexFormat.of().parseHex(hexKey)` (Java 17+), then validate the **decoded array length**.
- Do not call `base64Key.getBytes(UTF_8)` to build an AES key: those are bytes of the **encoded characters**, not the raw key.

Illustrative Base64 decoding snippet (not a standalone program, since `base64Key` is caller-supplied):

```java
byte[] raw = java.util.Base64.getDecoder().decode(base64Key);
try {
    if (raw.length != 16 && raw.length != 24 && raw.length != 32) {
        throw new IllegalArgumentException("Wrong AES key size");
    }
    SecretKey imported = new SecretKeySpec(raw, "AES");
    // Use imported within the required scope.
} finally {
    java.util.Arrays.fill(raw, (byte) 0);
}
```

Import raw keys only after authenticating **source, format, usage permissions, and transport security**. Never log raw keys or their Base64/hex strings. Some keys managed by HSM/PKCS#11/KMS or specialized providers are **non-exportable**, where `SecretKey.getEncoded()` may return `null`. For such keys, use the `SecretKey`/key handle directly with a compatible provider rather than attempting to build a `SecretKeySpec`.

**Memory-clearing limitation:** `SecretKeySpec` retains its own copy of the key bytes; `Arrays.fill(raw, 0)` only zeroes the application's `raw` array and does not guarantee clearing copies inside the key object or provider. Immutable `String` objects are harder to scrub than arrays; minimize key exports/copies, keep lifetimes short, and use KMS/HSM when required by policy.

## 4. A Password Is Not an AES Key: Use a KDF

A common mistake is taking UTF-8 bytes of a 16/32-byte password and creating a `SecretKeySpec`. A guessable password like `"1234567890123456"` remains trivial to brute-force even though it is **16 bytes**. A single direct `SHA-256(password)` is also not a proper password KDF: fast hashes allow massive offline password guessing.

In Java 17+, `SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")` with `PBEKeySpec` supports deriving a key from a password:

```text
password (char[]) -----+
                       +-- PBKDF2-HMAC-SHA256(salt, iterations, 256 bits)
random salt (16B+) ----+                         |
                                                 v
                                        32 raw key bytes
                                                 |
                                                 v
                                      SecretKeySpec(raw, "AES")
```

- **Salt** is random, e.g. 16 bytes from `SecureRandom`; it does not need to be secret, but must be stored so the exact same key can be re-derived on decryption. A new salt with the same password yields a new key.
- **Iterations** raise the cost of password guessing. The value `210_000` in the program illustrates the API; tune it to your threat model, performance budget, and evolving policy rather than treating it as a permanent recommended constant.
- `PBEKeySpec(password, salt, iterations, 256)` requests **256 bits**, producing 32 bytes. Two derivations with identical password/salt/iterations/algorithm/length produce the same key.
- Store **version, KDF name, salt, iteration count, and output length** in the record format. Changing parameters and attempting to decrypt old ciphertext will derive a different key.
- Use `char[]` instead of holding passwords long-term in `String` when your application allows it; `PBEKeySpec.clearPassword()` and `Arrays.fill(...)` scrub arrays you control, though they do not guarantee every internal copy is erased.

Modern libraries may support memory-hard KDFs such as **Argon2id** per policy; Java SE JCA does not guarantee this algorithm name out of the box. When a high-entropy master secret must produce multiple subkeys, use a protocol-appropriate KDF/context separation (such as HKDF) rather than password bytes or a bare fast hash as a universal shortcut.

## 5. Runnable Example: KeyGenerator, SecretKeySpec, and AES-GCM

Save as **`AesKeySourcesDemo.java`**, Java 17+. The program generates an AES-256 key, **solely for educational purposes** extracts raw bytes via `getEncoded()`, builds a `SecretKeySpec` from those raw bytes, then encrypts with the original key and decrypts with the imported key.

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
public class AesKeySourcesDemo {
    static SecretKey fromRawAesKey(byte[] raw) {
        if (raw == null || (raw.length != 16 && raw.length != 24 && raw.length != 32)) {
            throw new IllegalArgumentException("AES key must be 16, 24, or 32 bytes");
        }
        return new SecretKeySpec(raw, "AES");
    }
    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, random);
        SecretKey generated = generator.generateKey();
        byte[] raw = generated.getEncoded();
        if (raw == null) throw new IllegalStateException("Key is not exportable");
        try {
            SecretKey imported = fromRawAesKey(raw);
            System.out.println("generatedBits=" + raw.length * 8);
            System.out.println("algorithm=" + imported.getAlgorithm());
            System.out.println("sameMaterial=" + MessageDigest.isEqual(raw, imported.getEncoded()));
            try {
                fromRawAesKey(new byte[17]);
                System.out.println("invalidLengthRejected=false");
            } catch (IllegalArgumentException expected) {
                System.out.println("invalidLengthRejected=true");
            }
            byte[] iv = new byte[12];
            random.nextBytes(iv);
            byte[] aad = "record:7".getBytes(StandardCharsets.UTF_8);
            byte[] message = "Hello AES".getBytes(StandardCharsets.UTF_8);
            Cipher encrypt = Cipher.getInstance("AES/GCM/NoPadding");
            encrypt.init(Cipher.ENCRYPT_MODE, generated, new GCMParameterSpec(128, iv));
            encrypt.updateAAD(aad);
            byte[] ciphertextAndTag = encrypt.doFinal(message);
            Cipher decrypt = Cipher.getInstance("AES/GCM/NoPadding");
            decrypt.init(Cipher.DECRYPT_MODE, imported, new GCMParameterSpec(128, iv));
            decrypt.updateAAD(aad);
            byte[] recovered = decrypt.doFinal(ciphertextAndTag);
            System.out.println("roundTrip=" + Arrays.equals(message, recovered));
        } finally {
            Arrays.fill(raw, (byte) 0);
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AesKeySourcesDemo.java
java AesKeySourcesDemo
```

```text
generatedBits=256
algorithm=AES
sameMaterial=true
invalidLengthRejected=true
roundTrip=true
```

The output stays stable despite random key and IV because no secret bytes are printed. `sameMaterial=true` proves the copied raw key matches the original key; `roundTrip=true` proves the same key/IV/AAD encrypts and decrypts accurately. It does **not** prove external source trust, access control, or key storage security.

`AES/GCM/NoPadding` is an explicitly specified transformation; the shorter `Cipher.getInstance("AES")` lets the provider pick an unwanted default mode/padding (such as ECB). For AES-GCM, the nonce is typically 12 bytes and the tag is typically 128 bits; `GCMParameterSpec(128, iv)` uses **128 bits for the tag**, not the key size. When encrypting a **new record under the same key**, you must pick a **fresh non-repeating IV** and call `Cipher.init` again. Never treat engine reset after `doFinal` as permission to reuse a key+IV pair.

## 6. Runnable Example: Deriving a Raw AES Key from a Password with PBKDF2

Save as **`PasswordDerivedAesDemo.java`**. The password in the code is strictly for a standalone runnable demo—never hardcode passwords like this in real applications.

```java
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.SecretKey;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.SecretKeySpec;
public class PasswordDerivedAesDemo {
    private static final int ITERATIONS = 210_000;
    private static final int KEY_BITS = 256;
    private static byte[] deriveRawKey(char[] password, byte[] salt) throws Exception {
        if (salt == null || salt.length < 16) {
            throw new IllegalArgumentException("Salt must be >= 16 bytes");
        }
        PBEKeySpec spec = new PBEKeySpec(password, salt, ITERATIONS, KEY_BITS);
        try {
            SecretKeyFactory factory = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256");
            byte[] derived = factory.generateSecret(spec).getEncoded();
            if (derived == null || derived.length != 32) {
                throw new IllegalStateException("Expected 256 bits of derived key material");
            }
            return derived;
        } finally {
            spec.clearPassword();
        }
    }
    public static void main(String[] args) throws Exception {
        char[] password = "example-password".toCharArray();
        byte[] salt = new byte[16];
        new SecureRandom().nextBytes(salt);
        byte[] first = null;
        byte[] second = null;
        byte[] changedSalt = null;
        try {
            first = deriveRawKey(password, salt);
            second = deriveRawKey(password, salt);
            salt[0] ^= 1;
            changedSalt = deriveRawKey(password, salt);
            SecretKey aesKey = new SecretKeySpec(first, "AES");
            System.out.println("keyBits=" + first.length * 8);
            System.out.println("algorithm=" + aesKey.getAlgorithm());
            System.out.println("sameInputsSameKey=" + MessageDigest.isEqual(first, second));
            System.out.println("changedSaltChangesKey=" + !MessageDigest.isEqual(first, changedSalt));
        } finally {
            Arrays.fill(password, '\0');
            Arrays.fill(salt, (byte) 0);
            if (first != null) Arrays.fill(first, (byte) 0);
            if (second != null) Arrays.fill(second, (byte) 0);
            if (changedSalt != null) Arrays.fill(changedSalt, (byte) 0);
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 PasswordDerivedAesDemo.java
java PasswordDerivedAesDemo
```

```text
keyBits=256
algorithm=AES
sameInputsSameKey=true
changedSaltChangesKey=true
```

Identical password + salt + iterations + KDF + output length will re-derive the **exact same raw AES key**. Generating a fresh salt when decrypting old data yields a different key. When changing passwords, applications must design proper protocol-level re-encryption or re-wrapping; old ciphertexts do not automatically decrypt under the new key.

## 7. Where Are Keys Stored or Managed?

| Source | Proper Action |
| --- | --- |
| Randomly generated key in-process | Use `SecretKey` directly; requires a storage/recovery strategy if decryption is needed after restarts |
| Securely provisioned raw AES key | Decode (if encoded), validate 16/24/32 bytes, create `SecretKeySpec` |
| Password | KDF with proper salt/cost; store parameters so it can be re-derived |
| Java `KeyStore`, HSM, or PKCS#11 | Use `SecretKey` or key handle via provider; do not assume exportability |
| Cloud KMS | Follow API, key ID/permissions, and non-exportable raw key policies |
| High-entropy master secret | Derive context- and purpose-separated keys via a protocol KDF |

`KeyStore` is an **API** for managing key entries; protection strength depends on the store type and provider (e.g., PKCS12, PKCS11), and it is not automatically an HSM. Separate permission to **use a key** from permission to **export a raw key**. During key rotation, store **key ID/version** in ciphertext metadata; data encrypted with an old key generally requires either the old key or a controlled re-encryption/re-wrapping workflow.

An AES-GCM record needs **key ID, IV, ciphertext+tag, AAD (or AAD construction rules)**, and format version. If the source is a password, include **KDF algorithm/salt/iterations/output bits**. Never store raw keys as metadata where ciphertext readers can inspect them.

## 8. Common Errors and How to Avoid Them

| Issue | Cause | Resolution |
| --- | --- | --- |
| `NoSuchAlgorithmException` | Provider lacks AES or PBKDF2 algorithm | Verify algorithm name and provider/runtime |
| `InvalidParameterException` in `KeyGenerator.init` | Unsuitable key length or policy restriction | Choose supported 128/192/256 bits |
| `IllegalArgumentException` on import | Invalid Base64/hex or wrong raw key length | Decode proper format, validate **byte count** |
| `InvalidKeyException` in `Cipher.init` | SecretKey invalid for algorithm/provider | Verify key algorithm, size, and provider |
| `InvalidAlgorithmParameterException` | Wrong IV/tag/mode parameters | Verify transformation and `GCMParameterSpec` |
| `AEADBadTagException` on decryption | Wrong key, IV, AAD, or ciphertext/tag | Reject record, do not use unauthenticated plaintext |
| `getEncoded() == null` | Key is non-exportable | Use key handle directly with a supporting provider |
| Lost ability to decrypt after restart | Key/version/salt/IV not persisted properly | Design key management and metadata before encrypting |

Never share a single active `Cipher` instance across multiple threads/requests. Do not log secrets or return overly detailed internal errors to external callers; when GCM authentication fails, discard any unauthenticated plaintext.

### Pre-Production Checklist

- New keys are generated by `KeyGenerator`/CSPRNG, or raw keys come from a verified source with valid lengths.
- Passwords always go through a KDF with salt and cost factor; parameter persistence/recovery is designed.
- `Cipher` uses an explicit transformation such as `AES/GCM/NoPadding`; IVs are unique within each encryption key's scope.
- Key ID/version, retention policy, backup, least-privilege access, and rotation are in place.
- No hardcoded keys, logging, unnecessary exports, or raw keys stored alongside ciphertext.
- Tests cover invalid key lengths, PBKDF2 same/different salts, AES-GCM round-trip, and modified GCM tags.

## 9. Self-Check

1. How many raw key bytes do AES-128/192/256 have? **16/24/32**.
2. Is parameter `256` in `KeyGenerator.init(256)` bits or bytes? **Bits**.
3. Does `SecretKeySpec` add entropy or generate keys? **No**.
4. A 64-character hex string for AES-256 decodes to how many raw bytes? **32**.
5. Is using a 16-character password directly as an AES-128 key secure? **Not guaranteed**; a proper KDF is required.
6. Why must the PBKDF2 salt be stored? To **re-derive the exact same key** during decryption, alongside the other parameters.
7. Can GCM reuse an IV while keeping the same key? **No**.
8. What does `getEncoded()==null` mean? The key may be **non-exportable**, requiring a compatible provider/handle.
9. Does zeroing the `raw` array erase the copy inside `SecretKeySpec`? **No**.
10. Does a new key automatically decrypt ciphertexts from an old key? **No**; version/old key tracking or a data migration process is needed.

## Java SE 21 References

- [KeyGenerator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KeyGenerator.html)
- [SecretKey](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/SecretKey.html)
- [SecretKeySpec](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/SecretKeySpec.html)
- [SecureRandom](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html)
- [SecretKeyFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/SecretKeyFactory.html)
- [PBEKeySpec](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html)
- [Cipher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html)
- [GCMParameterSpec](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html)
- [KeyStore](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.html)