# 3.3 Distinguishing Bit Count, Byte Count, Key Length, and Output Length

In Java cryptographic programming, numbers like **128, 256, 2048, 32, or 64** frequently appear alongside algorithms and APIs. They can denote **bits**, **bytes**, **secret key** length, asymmetric **modulus** size, **digest/MAC/tag** length, or the character count of a **display-encoded** string. These quantities are related, yet **cannot be substituted for one another**. Confusing units can break code, truncate stored bytes, or misjudge security strength.

## 1. Fundamental Units: Bits, Bytes, and Conversions

- A **bit** is a binary position holding 0 or 1. Common symbols: **bit** or **b**.
- A **byte** in Java has **8 bits**: the constant `Byte.SIZE` equals 8. The standard symbol for byte is **B**. Therefore **1 B = 8 bits**.
- Given `n` bytes, the number of bits needed to represent them is **8 × n**; if a bit count is divisible by 8, the byte count is **bits / 8**.
- For any bit length `n`, the **minimum bytes required to hold** that value is **ceil(n / 8)**, or for non-negative integers: **(n + 7) / 8**. The last byte may contain unused bits.
- `kB` = 1,000 bytes, `KiB` = 1,024 bytes. Distinguish these storage-capacity units from key lengths typically expressed in bits.

| Size | Equivalent bytes | Common context |
| --- | ---: | --- |
| 64 bits | 8 bytes | 64-bit integer value; 64-bit nonce in some protocols |
| 96 bits | 12 bytes | Commonly recommended nonce/IV for AES-GCM |
| 128 bits | 16 bytes | AES-128 key; 128-bit GCM tag |
| 192 bits | 24 bytes | AES-192 key |
| 256 bits | 32 bytes | AES-256 key; SHA-256 output |
| 384 bits | 48 bytes | SHA-384 output |
| 512 bits | 64 bytes | SHA-512 output |
| 2,048 bits | 256 bytes | Modulus component of an RSA-2048 key (commonly used length) |

**Specify the quantity explicitly:** "256 bits" is just a bit count; without knowing whether it refers to a *key*, *digest*, *tag*, *nonce*, or *modulus*, you cannot infer its role or security strength.

Direct calculation examples: 128 bits / 8 = **16 bytes**; 32 bytes × 8 = **256 bits**. An RSA key with a 2,048-bit modulus contains roughly 256 bytes representing the modulus; **the full file-encoded public/private key is typically longer**.

### 1.1. Bytes in Java and Array Length

In Java, `byte` is a **signed 8-bit** integer type representing values from -128 to 127. Signedness is merely how Java interprets the bit pattern as a number; **each element of `byte[]` still holds 8 bits**.

- `byte[].length` counts the **number of bytes in the array**, not bits.
- `Byte.SIZE` = 8; `Byte.BYTES` = 1.
- `int` is 32 bits and `long` is 64 bits in Java, yet a primitive type's bit width **is not the serialized content length or entropy**.
- For very large byte counts, use `long` multiplication or `Math.multiplyExact` as appropriate to avoid integer overflow when converting to bits.

### 1.2. String Character Length Does Not Equal Byte Length

Java's `String.length()` returns the **number of UTF-16 code units**, not Unicode characters in the code point sense, and certainly not bytes sent over the network.

For example, the string **"Việt"** has 4 UTF-16 code units, yet when encoded to UTF-8 it becomes **6 bytes = 48 bits**, because the character "ệ" takes 3 UTF-8 bytes. A non-BMP emoji typically has 1 code point, 2 UTF-16 code units, and 4 UTF-8 bytes.

How to measure properly before feeding text into hashes, MACs, encryption, or protocols:

```java
String text = "Việt";
byte[] data = text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
int bytes = data.length;
long bits = (long) bytes * Byte.SIZE;
```

**Consequence:** enforcing "maximum 256 characters" is not equivalent to enforcing "maximum 256 bytes." When bounding payloads, KDF inputs, or binary fields, state both the **encoding** and the unit of measurement.

## 2. Key Length: Key Size Differs from Encrypted Data Byte Count

**Key length (key size)** is the bit length of key material or the key parameter size defined by the algorithm. Its representation varies across algorithm families.

### 2.1. Symmetric Keys: AES-128, AES-192, AES-256

AES accepts **128-, 192-, or 256-bit** keys, which are **16, 24, or 32 bytes** respectively. The number after "AES-" is the **key** bit length, not the ciphertext byte count, not an arbitrary round count, and not the tag length.

- In Java JCA/JCE, `KeyGenerator.getInstance("AES")` creates an AES key generator; `KeyGenerator.init(128)` requests **128 bits**, not 128 bytes.
- For exportable software AES keys, `SecretKey.getEncoded()` returns the key bytes: AES-128 is 16 bytes long.
- `SecretKey.getEncoded()` **can return `null`** for non-exportable keys, such as certain HSM/provider keys. Do not treat the presence or absence of exported bytes as the sole verification for all key types.
- **AES has a fixed 128-bit (16-byte) block size** regardless of whether the AES key is 128, 192, or 256 bits. Never infer block size from key size.
- Having more key bytes does not guarantee a more secure system if the key is derived from a weak password, hardcoded, leaked in logs, or mismanaged.

When reading `AES-256-GCM`, separate at least four distinct-purpose quantities: **256-bit key**, **128-bit AES block**, **typically 96-bit nonce**, and **typically 128-bit tag**.

### 2.2. Asymmetric Keys: RSA-2048 and Elliptic Curves

**RSA-2048** refers to the length of the **modulus n**, typically 2,048 bits = 256 bytes; **it does not mean a public key file is exactly 256 bytes**. An RSA public key also contains an exponent; a DER-encoded X.509 SubjectPublicKeyInfo has ASN.1 framing and metadata. A PKCS#8 private key contains even more components and can therefore be significantly larger.

- `RSAPublicKey.getModulus().bitLength()` gives the **actual bit length of the modulus**.
- `publicKey.getEncoded().length` gives the **byte count of the encoded public key structure**. The two metrics answer different questions.
- For RSA-2048, the RSA ciphertext from one encryption operation has the modulus size, typically **256 bytes**, whereas the **maximum plaintext size is much smaller**, depending on padding; for instance, RSA-OAEP with SHA-256 as the OAEP hash is bounded to **256 − 2 × 32 − 2 = 190 bytes** per encryption. Note that OAEP/MGF1 hash settings must align with the protocol rather than being assumed from the transformation name alone.
- An RSA signature typically has the same size as the modulus byte length; that is not the size of the private key stored on disk.

**P-256** is a curve with field parameters and group order around 256 bits; **it must not be equated** to an AES-256 key in equivalent security level. An EC public key can be encoded as a compressed point, uncompressed point, or X.509/DER wrapper; an ECDSA signature can likewise be variable-length DER or fixed protocol-defined raw `r || s`. Thus the byte length of a "public key" or "signature" also depends on **format**.

### 2.3. Key Size Is Not Security Strength

**Security strength** estimates the attacker's work factor, usually expressed in equivalent security bits against a specific attack model. It **is not equal to the number of bits written in the algorithm name**.

| Algorithm/parameter | Commonly seen length | Approximate classical security strength |
| --- | --- | --- |
| AES-128 | 128-bit key | 128 bits when key is random, secret, and algorithm is used properly |
| AES-256 | 256-bit key | 256 bits against exhaustive key search in an ideal model |
| RSA-2048 | 2,048-bit modulus | Roughly 112 bits |
| RSA-3072 | 3,072-bit modulus | Roughly 128 bits |
| ECDSA/ECDH on P-256 | ~256-bit curve parameters | Roughly 128 bits |

The rightmost numbers are **classical estimates, dependent on assumptions and cryptographic guidelines**; they are not absolute guarantees for every system, especially under implementation bugs, side channels, or quantum computing models. **RSA-2048 does not provide "2,048-bit security."** Selecting algorithms and key sizes requires considering security targets, data protection lifetime, protocol standards, and current regulations.

### 2.4. Key Material Length and Entropy Are Different Questions

**Entropy** measures the unpredictability of the key generation source. An arbitrary 32-byte array does not automatically hold 256 bits of entropy: 32 bytes from a properly used `SecureRandom` is one thing; 32 repeated characters from a weak password is another.

- Random keys: use a secure random source, such as Java's `KeyGenerator` or `SecureRandom` per algorithm requirements.
- Password-derived keys: use an appropriate password KDF with a **salt**, cost settings, and key management; never truncate or pad a password string to 16 or 32 bytes and call it secure AES-128/AES-256.
- A KDF may allow a **configurable output length**. For example, the `keyLength` parameter of `PBEKeySpec` is in **bits**, while `salt` is a **`byte[]`** and `iterations` is a **loop count**; these numbers do not share units.
- A key "stretched" by a KDF does not gain more entropy than the input password; physical length and unpredictability must be evaluated separately.

## 3. Output Lengths: Digest, MAC, Tag, Ciphertext, and Encoded Text

**Output length** must always state the operation: hash, MAC, signature, encryption, or serialization output. Each operation has its own formula or configuration.

### 3.1. Hash/Digest: Output Size Defined by the Algorithm

| Hash algorithm | Binary digest | Typical hex representation | Standard padded Base64 |
| --- | ---: | ---: | ---: |
| SHA-256 | 256 bits = **32 bytes** | 64 ASCII chars | 44 ASCII chars |
| SHA-384 | 384 bits = **48 bytes** | 96 ASCII chars | 64 ASCII chars |
| SHA-512 | 512 bits = **64 bytes** | 128 ASCII chars | 88 ASCII chars |
| SHA3-256 | 256 bits = **32 bytes** | 64 ASCII chars | 44 ASCII chars |

A hash accepts variable-length input and returns a fixed-size digest defined by the algorithm. `MessageDigest.getInstance("SHA-256").digest(bytes)` returns a **32-byte array**. Digest size **does not depend on the input message byte count**; 3 bytes or 3 GB of data both produce a 32-byte SHA-256 digest.

**A 256-bit SHA-256 output does not mean "256-bit collision resistance."** For an ideal 256-bit hash, generic collision resistance hits the birthday bound around **2^128 trials**, whereas generic preimage search is around **2^256**. Digest length is a data size; attack resistance targets must name the attack class.

Do not confuse **SHA-256's compression block size** (512 bits = 64 bytes per internal block) with its **digest size** (256 bits = 32 bytes). The name SHA-256 refers to the output size, not a key size (SHA-256 takes no key).

### 3.2. HMAC: Key Length and Tag Length Are Independent

**HmacSHA256** uses SHA-256 inside the MAC construction. Java's `Mac.getInstance("HmacSHA256")` normally produces a **32-byte (256-bit) tag**, even though the input HMAC key may be **16, 32, or 64 bytes** if it satisfies design requirements; **the "SHA256" name does not force the key to be 256 bits**.

- `SecretKey` for HMAC is a secret key whose byte length is typically chosen by the program/protocol.
- `Mac.getMacLength()` reports the instance's **output MAC length in bytes**.
- A protocol may truncate an HMAC tag per approved parameters; the transmitted/stored byte count then **differs** from the full digest. Never truncate arbitrarily on either side without specifying tag length and security level.
- HMAC proves shared-key knowledge and message integrity/authenticity; it **does not encrypt** content.

Counterexample: a 64-byte HMAC key does not make HmacSHA256 output 64 bytes; the default tag remains **32 bytes**. Conversely, switching to HmacSHA512 changes the full tag size to **64 bytes**, without mandating a 64-byte key.

### 3.3. AES-GCM: Distinguishing Key, Nonce, Tag, and Total Output

In a common **AES-128-GCM** example with a **12-byte nonce** and **128-bit = 16-byte tag**:

| Component | Example length | Role |
| --- | ---: | --- |
| AES key | 16 bytes = 128 bits | Secret key |
| GCM nonce/IV | 12 bytes = 96 bits | Value that must be unique under the same key; not a key |
| Plaintext | 5 bytes | Input data, e.g., UTF-8 text "hello" |
| Raw ciphertext | 5 bytes | Encrypted data portion in GCM, excluding tag |
| Authentication tag | 16 bytes = 128 bits | Integrity/authenticity protection for ciphertext and AAD |
| Result of `Cipher.doFinal(plaintext)` when encrypting with GCM in standard JCA | **21 bytes** | **5-byte ciphertext + 16-byte tag** |
| If packaged as `nonce \|\| ciphertext \|\| tag` | **33 bytes** | **12 + 5 + 16**, excluding other version/metadata |

Here, **`GCMParameterSpec(128, nonce)` takes the tag length in bits**, while `nonce` is a 12-element `byte[]`. **The 128 in `GCMParameterSpec` does not indicate the AES key length.**

If the protocol stores the nonce externally, `doFinal()` does not prepend the 12-byte nonce to the output. You must define a decodable storage/wire format including version, nonce, ciphertext, tag, and required AAD metadata. GCM does not use PKCS#5-style plaintext padding; the table above reflects exact lengths for JCA `AES/GCM/NoPadding`.

**Nonce warning:** a 96-bit nonce must be generated/managed so that it **never repeats under the same key**. It may typically be public, yet repeating a nonce in AES-GCM catastrophically breaks confidentiality and integrity. Never treat "12 bytes long" as proof that a nonce is unique.

### 3.4. Encoding Increases Display Size, Not Cryptographic Strength

Arbitrary binary bytes may not be valid text characters. When key, digest, or ciphertext bytes must be printed or stored as text, you must choose an **encoding**; the text size will differ from the binary array.

- **Hex:** each byte produces **2 ASCII characters**; `n` bytes → **2n characters**. A 32-byte digest → 64 hex characters.
- **Standard padded Base64:** `n` bytes → **4 × ceil(n / 3)** ASCII characters. A 32-byte digest → 44 characters, typically ending with `=`.
- **Unpadded Base64URL:** uses a URL-safe alphabet and can be shorter than the padded form. For 32 bytes → **43 characters** without padding.
- Hex/Base64 strings consist of ASCII characters, so when UTF-8 encoded they usually take **1 byte per character**. Still, **32 binary bytes ≠ a 32-byte Base64 string**, and character count says nothing about new entropy.

Hex, Base64, and Base64URL **only represent bytes**; they are neither security encryption nor hashing. Never expose a key just because it was Base64-encoded; never log hex of secret keys in an application.

### 3.5. Signatures, RSA Ciphertext, and Container Formats

An RSA signature with a 2,048-bit modulus is typically **256 bytes** in raw signature form. An Ed25519 signature per spec is **64 bytes**, though file packaging formats can add headers/certificates. ECDSA outputs a `(r, s)` number pair, so its byte length depends on raw vs. DER encoding and encoding rules.

With RSA-OAEP, encrypted output (ciphertext) equals the modulus byte length, yet the **maximum plaintext size** is constrained by modulus and padding. For example, RSA-2048 + OAEP using SHA-256 as the OAEP hash: **at most 190 bytes of plaintext**, not 190 Unicode characters.

**Practical takeaway of this section:** always write "bytes of binary payload", "bits of key", "bytes of digest", "bits of tag", "bytes of DER file", "Base64 characters", rather than vaguely saying "length 256."

## 4. Java 17+: Directly Measuring Cryptographic Data Lengths

The following program uses Java JCA/JCE to compare: UTF-8, SHA-256, hex/Base64, AES-128, AES-GCM, and HmacSHA256. Key/nonce bytes are generated randomly and change across runs, yet **the printed length measurements are fixed** for this configuration.

Save with exact filename **CryptoLengthsDemo.java**:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class CryptoLengthsDemo {
    public static void main(String[] args) throws Exception {
        byte[] utf8 = "Việt".getBytes(StandardCharsets.UTF_8);
        System.out.printf("Text UTF-8: %d bytes = %d bits%n",
                utf8.length, utf8.length * Byte.SIZE);

        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest("abc".getBytes(StandardCharsets.UTF_8));
        System.out.printf("SHA-256: %d bytes = %d bits%n",
                digest.length, digest.length * Byte.SIZE);
        System.out.printf("SHA-256 hex: %d characters%n",
                HexFormat.of().formatHex(digest).length());
        System.out.printf("SHA-256 Base64: %d characters%n",
                Base64.getEncoder().encodeToString(digest).length());

        KeyGenerator aesGenerator = KeyGenerator.getInstance("AES");
        aesGenerator.init(128);
        SecretKey aesKey = aesGenerator.generateKey();
        System.out.printf("AES-128 key: %d bytes%n",
                aesKey.getEncoded().length);

        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);
        byte[] plaintext = "hello".getBytes(StandardCharsets.UTF_8);
        Cipher encryptor = Cipher.getInstance("AES/GCM/NoPadding");
        encryptor.init(Cipher.ENCRYPT_MODE, aesKey,
                new GCMParameterSpec(128, nonce));
        byte[] ciphertextAndTag = encryptor.doFinal(plaintext);
        System.out.printf(
                "GCM nonce: %d bytes; plaintext: %d bytes; output: %d bytes%n",
                nonce.length, plaintext.length, ciphertextAndTag.length);

        KeyGenerator macGenerator = KeyGenerator.getInstance("HmacSHA256");
        macGenerator.init(256);
        SecretKey macKey = macGenerator.generateKey();
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(macKey);
        byte[] hmac = mac.doFinal(plaintext);
        System.out.printf("HmacSHA256 key: %d bytes; tag: %d bytes%n",
                macKey.getEncoded().length, hmac.length);
    }
}
```

Compile and run with JDK 17 or later, specifying UTF-8 for source encoding:

```bash
javac -encoding UTF-8 CryptoLengthsDemo.java
java CryptoLengthsDemo
```

Expected stdout (length values verified via JShell):

```text
Text UTF-8: 6 bytes = 48 bits
SHA-256: 32 bytes = 256 bits
SHA-256 hex: 64 characters
SHA-256 Base64: 44 characters
AES-128 key: 16 bytes
GCM nonce: 12 bytes; plaintext: 5 bytes; output: 21 bytes
HmacSHA256 key: 32 bytes; tag: 32 bytes
```

**Reading the output with the right quantities:**

1. The string "Việt" becomes 6 UTF-8 bytes; this is the **representation size** of the text, not 48 bits of randomness.
2. The SHA-256 digest is 32 bytes, yet its hex representation is 64 characters; standard Base64 is 44 characters.
3. `aesGenerator.init(128)` takes **bits**, whereas `aesKey.getEncoded().length` measures **bytes**.
4. `GCMParameterSpec(128, nonce)` specifies a **128-bit tag**; the `doFinal()` output is 5 bytes of ciphertext plus 16 bytes of tag; the 12-byte nonce is held **separately**.
5. The HMAC key was intentionally generated as 256 bits = 32 bytes; HmacSHA256 returns a 32-byte tag **due to the MAC algorithm**, not because the program forced the two lengths to match.

This example uses exportable keys from a standard software provider. For HSMs or non-exportable keys, `getEncoded()` can return `null`; retrieve key metadata via supported provider APIs rather than trying to dump key bytes to check size. Never log or transmit key arrays externally.

## 5. Java 17+: RSA Modulus and Key File Size Are Two Different Numbers

This standalone example generates a 2,048-bit RSA key pair, measures the modulus bit length, and checks whether the X.509/PKCS#8 encoded bytes of the key objects exceed the modulus byte count.

Save **RsaLengthsDemo.java**:

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPublicKey;

public class RsaLengthsDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();

        RSAPublicKey publicKey = (RSAPublicKey) pair.getPublic();
        int modulusBits = publicKey.getModulus().bitLength();
        int modulusBytes = (modulusBits + 7) / 8;

        System.out.printf("RSA modulus: %d bits = %d bytes%n",
                modulusBits, modulusBytes);
        System.out.printf("X.509 encoded public key exceeds modulus: %b%n",
                publicKey.getEncoded().length > modulusBytes);
        System.out.printf("PKCS#8 encoded private key exceeds modulus: %b%n",
                pair.getPrivate().getEncoded().length > modulusBytes);
    }
}
```

```bash
javac -encoding UTF-8 RsaLengthsDemo.java
java RsaLengthsDemo
```

Stdout under a typical JDK provider:

```text
RSA modulus: 2048 bits = 256 bytes
X.509 encoded public key exceeds modulus: true
PKCS#8 encoded private key exceeds modulus: true
```

**Why?** `getModulus()` returns the integer `n` in RSA; `bitLength()` counts the bits needed for `n`. `getEncoded()` on a public key typically contains an X.509 SubjectPublicKeyInfo, while a private key typically contains PKCS#8, including multiple values and metadata. **Never use `getEncoded().length * 8` to state RSA modulus size or security strength.**

Random RSA key generation timing varies by environment, yet the modulus size in the example does not vary with random bytes. Different DER/PEM encodings and providers can yield different file lengths; thus programs must **not** hardcode an exact key file byte count. Protect private keys, avoid printing key contents, and never place real keys into documentation.

## 6. Choosing Lengths When Designing APIs, Storage, and Output Validation

Before designing a storage schema or wire format, answer **four questions**:

1. **What quantity?** Secret key, IV/nonce, salt, hash, MAC/tag, ciphertext, signature, public key, or encoded string?
2. **What unit?** Bits, bytes, ASCII characters, UTF-16 code units, or Unicode code points?
3. **What format?** Raw binary, hex, Base64, Base64URL, DER, PEM, or an envelope format with header/nonce/tag?
4. **Who determines the size?** Fixed by algorithm, configured parameter, plaintext length, padding option, or protocol?

Example implementing transmission of a **32-byte SHA-256 digest**:

- For a binary field, digest size is **32 bytes**.
- For a hex text field, allocate **64 ASCII characters**.
- For standard padded Base64, allocate **44 ASCII characters**.
- If storing algorithm ID, version, and separators as well, account for **overhead** beyond the digest.
- Never turn SHA-256 into a string via `new String(digest, UTF_8)`: a digest is arbitrary binary data and may not be valid UTF-8; use `HexFormat` or `Base64` if text is truly required.

Example storing the AES-GCM encryption result of 1,000-byte plaintext with a 16-byte tag and 12-byte nonce: `doFinal` in a standard configuration returns **1,016 bytes**, and a `nonce || ciphertext || tag` envelope needs at least **1,028 bytes** before adding version, AAD metadata, and other fields. If that 1,028-byte envelope is encoded in standard Base64, the output becomes **4 × ceil(1,028/3) = 1,372 ASCII characters**. Each step adds **formatting**, not security strength.

### 6.1. Using Java APIs with the Right Units

| Java API | Key value/unit | Mistake to avoid |
| --- | --- | --- |
| `Byte.SIZE`, `Byte.BYTES` | 8 bits/byte and 1 byte | Treating `byte` as 1 bit because of the name |
| `byte[].length` | Byte count | Reading it directly as bit count |
| `String.length()` | UTF-16 code units | Treating as UTF-8 bytes or code points |
| `getBytes(UTF_8).length` | Bytes of UTF-8 text | Failing to pin encoding |
| `KeyGenerator.init(128)` for AES | Key size in **bits** | Passing 16 when wanting a 16-byte key |
| `PBEKeySpec(..., keyLength)` | `keyLength` in **bits** | Confusing with `salt.length` in bytes |
| `GCMParameterSpec(128, iv)` | Authentication tag length in **bits** | Reading 128 as IV byte count or key size |
| `MessageDigest.digest(...).length` | Actual digest bytes | Seeing SHA-256 and assuming 256 bytes |
| `MessageDigest.getDigestLength()` | Digest bytes (if provider supports reporting length) | Assuming it returns bits |
| `Mac.getMacLength()` | Full MAC bytes | Treating it as MAC key length |
| `RSAPublicKey.getModulus().bitLength()` | RSA modulus bits | Treating `getEncoded().length` as modulus |
| `Key.getEncoded()` | Exported key format bytes, or `null` | Inferring security bits from encoded bytes |

### 6.2. Storage and Bounding Rules

- For cryptographic binary data, store as binary when the system supports it; encode to text only at genuine text boundaries (JSON, HTTP headers, config).
- When storing digests/hashes as hex, size columns/files for the **encoded string length**, not just the binary digest length.
- Encryption output depends on mode, padding, tag, overhead, and actual plaintext. Never allocate buffers solely from key size; use APIs that compute output size or handle the array returned by `doFinal()`.
- When changing algorithm parameters (e.g., SHA-256 → SHA-512 or 96-bit → 128-bit tag), verify schemas, serialization, and compatibility.
- Sensitive key material should not be stored or logged in hex, Base64, or plaintext; those encodings provide no confidentiality.

## 7. Common Mistakes and Correct Thinking

| Misconception | Correct fact |
| --- | --- |
| "AES-256 needs `byte[256]`." | AES-256 needs **256 bits = 32 bytes** of key. |
| "An AES-256 key produces a fixed 256-byte ciphertext." | Key size **does not determine** ciphertext length; plaintext and mode/tag/padding do. |
| "An RSA-2048 public key is always 256 bytes." | The **modulus** is typically 256 bytes; an encoded public key includes exponent and metadata. |
| "SHA-256 returns 256 bytes." | A SHA-256 digest is **256 bits = 32 bytes**. |
| "A 64-character hex string means a 64-byte digest." | 64 hex characters represent **32 binary bytes**. |
| "HmacSHA256 requires an exact 32-byte key." | Key size and tag size are separate quantities; a full HmacSHA256 tag is **32 bytes**. |
| "GCM tag 128 means a 128-byte nonce." | `GCMParameterSpec(128, nonce)` has a **128-bit = 16-byte** tag; the nonce is passed as a separate byte array. |
| "Base64 makes a key stronger." | Base64 only changes representation; entropy does not increase. |
| "A 32-byte password automatically has 256-bit security." | Strength depends on generation/password and KDF, not byte count alone. |
| "`String.length()` is the request byte length." | It counts UTF-16 code units; encode to bytes before measuring. |

## 8. Self-Check Exercises

**Q1.** An AES KeyGenerator needs a 192-bit key. How long is the exported byte array of a standard AES key?  
**Answer:** **24 bytes**. In Java, call `aesGenerator.init(192)`, not `init(24)`.

**Q2.** SHA-512 hashes an 8 GB file. How long is the resulting digest, and how long is it in hex?  
**Answer:** **64-byte digest**; **128 hex characters**. File size does not change digest length.

**Q3.** An HmacSHA256 MAC uses a 48-byte key without tag truncation. How long is the expected tag?  
**Answer:** **32 bytes**. A 48-byte key does not turn a SHA-256 tag into 48 bytes.

**Q4.** AES-GCM encrypts 20 bytes of plaintext with a 128-bit tag and stores a 12-byte nonce alongside the ciphertext. How many bytes are needed for `nonce || ciphertext || tag` before headers?  
**Answer:** **12 + 20 + 16 = 48 bytes**. The `Cipher.doFinal()` portion in the JCA example is **36 bytes** (ciphertext + tag), excluding the nonce.

**Q5.** Does a 44-character Base64 string always decode to exactly 44 bytes?  
**Answer:** **No.** Base64 carries 6 bits per character and can include padding; for example, 32 binary bytes produce **44 standard Base64 characters**. You must decode to know the actual byte count.

**Q6.** RSA-2048 has a 256-byte modulus; why can `publicKey.getEncoded().length` be larger than 256?  
**Answer:** Because it is an **encoded public key format** carrying the exponent, ASN.1 structure, and algorithm info, not just the raw modulus.

**Q7.** If a `String` variable has 4 UTF-16 code units, does it necessarily have 4 UTF-8 bytes?  
**Answer:** **No.** Code points can take multiple UTF-8 bytes. The string "Việt" in the example has 4 UTF-16 code units yet 6 UTF-8 bytes.

### Takeaway When Reading Specifications

**Always state "of what" and "in what unit":** *256-bit AES key*, *128-bit GCM tag*, *12-byte nonce*, *32-byte SHA-256 digest*, *64-char hex digest*, *2,048-bit RSA modulus*, *how many bytes for the DER RSA public key*. Physical length, encoded length, security strength, and entropy are distinct concepts; choosing the right sizes requires identifying all four.
