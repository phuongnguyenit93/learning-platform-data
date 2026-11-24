# 6.1 Block Ciphers, Stream Ciphers, Modes, and Padding

## 1. Why Do We Need to Distinguish These Four Concepts?

**Symmetric encryption** uses a secret key to encrypt and decrypt. However, the **primitive algorithm**, **mode**, **padding**, and **authentication** are not the same thing. Choosing a 256-bit AES key does not determine how an application processes a multi-megabyte file or knows whether the ciphertext has been modified.

This lesson builds the foundation for the chapter: identifying AES as a block cipher and ChaCha20 as a stream cipher, understanding AES modes and when padding is needed, and distinguishing encryption-only schemes from authenticated encryption (AEAD). Subsequent lessons dive deeper into transformations/providers, key management, the Cipher lifecycle, ECB/CBC/CTR, GCM, and ChaCha20. The examples here focus on **data shapes and selection principles** rather than repeating deep implementations of each mode.

Learning objectives after this lesson:

1. Explain why AES has a 128-bit block size even though the key can be 128/192/256 bits.
2. Describe how a stream cipher generates a keystream and XORs it with data, along with the consequences of reusing a keystream.
3. State the meaning and differences of ECB, CBC, CTR, and GCM when using AES across multiple blocks.
4. Calculate the exact number of CBC padding bytes and distinguish padding from an authentication tag.
5. Distinguish key, IV/nonce, counter, AAD, and tag, and know when AEAD is required.
6. Predict the output of a Java 17+ demo for a block cipher with non-block-aligned input and a stream cipher with 17-byte input.

## 2. Block Ciphers: Encrypting Fixed-Size Blocks

A **block cipher** transforms a plaintext block of a fixed length into a ciphertext block of the same length under a secret key:

```text
EncryptBlock(K, P) -> C
DecryptBlock(K, C) -> P
```

**AES** has a fixed block size of **128 bits = 16 bytes**. The three commonly used variants differ only in **key size**:

| AES Name | Key | AES Block |
| --- | ---: | ---: |
| AES-128 | 128 bit = 16 byte | 128 bit = 16 byte |
| AES-192 | 192 bit = 24 byte | 128 bit = 16 byte |
| AES-256 | 256 bit = 32 byte | 128 bit = 16 byte |

Therefore, "AES-256" does **not** mean AES processes a 32-byte block. If the plaintext is 11 bytes, a raw single-block encryption operation does not inherently know how to pad or combine data. If the plaintext is a 1 GB file, the underlying block algorithm also does not inherently define the ordering and relationship between blocks.

To process long messages, a **mode of operation** is required. Some modes use an IV/nonce, and some use padding; these decisions directly impact security.

### Why Not Encrypt Each Block Independently?

If the same AES key is used on the same plaintext block, the output of the underlying block encryption operation is identical. If the entire message is split into blocks and encrypted independently under ECB, two equal plaintext blocks produce two equal ciphertext blocks. An observer can detect repeating patterns even without reading plaintext bytes. **Increasing the key length does not eliminate ECB's pattern-leakage flaw.**

## 3. Stream Ciphers: Keystream and XOR

A **stream cipher** generates a cryptographically pseudorandom byte sequence (keystream) from the key and parameters, then XORs it with the plaintext:

```text
keystream = Stream(K, nonce, counter, ...)
C = P XOR keystream
P = C XOR keystream
```

Because it operates on a byte/stream basis, a 17-byte plaintext typically produces 17 bytes of ciphertext, **without needing padding to fit a 16-byte AES block**.

**ChaCha20** is a modern stream cipher: the IETF variant uses a **256-bit key**, a **96-bit nonce**, and a block counter. Plain ChaCha20 only encrypts; **ChaCha20-Poly1305** adds Poly1305 to provide AEAD authentication. These two names must not be used interchangeably.

The most dangerous risk in keystream-based modes is reusing the same keystream region. If two different plaintexts are XORed with the same `S`:

```text
C1 = P1 XOR S
C2 = P2 XOR S
=> C1 XOR C2 = P1 XOR P2
```

An observer can deduce the relationship between the two plaintexts, and from a known portion of one plaintext can recover the corresponding portion of the other. Therefore, with stream ciphers and AES-CTR, **the nonce/counter must be managed so that keystream regions are never reused under the same key**. Do not use an all-zero default IV/counter repeatedly across messages.

**Warning:** a stream cipher can still decrypt "successfully" even if a bit in the ciphertext has been flipped. To defend against modification, an authentication mechanism such as AEAD or a properly designed scheme is required; do not treat successful decryption as an integrity check.

## 4. Modes: How AES Is Used for a Message

A **mode** defines how multiple blocks and parameters like IV/counter are coordinated, without changing the AES block size. The comparison table below covers only foundational characteristics:

| Mode | How It Works | IV/nonce | Padding | Built-in Authentication Tag? |
| --- | --- | --- | --- | --- |
| ECB | Each block independently | No | Yes if not block-aligned | **No** |
| CBC | Chaining with previous ciphertext block | Fresh, unpredictable IV for encryption | Usually uses PKCS5Padding | **No** |
| CTR | Encrypts counter blocks into a keystream, then XORs | Non-repeating counter blocks under the same key | No | **No** |
| GCM | Counter mode combined with GCM authentication mechanism | Unique IV/nonce per encryption under a key | No | **Yes** |

**ECB:** simple for illustrating a single block encryption, but leaks repeating plaintext blocks. **Do not choose ECB for encrypting application data.**

**CBC:** uses an IV (typically 16 bytes for AES) and chains block states, mitigating ECB-style pattern leakage when the IV is chosen properly. However, plain CBC **does not authenticate data**. Modifying the IV/ciphertext can affect the plaintext; leaking padding errors can create a padding oracle. If legacy CBC must be used, a proper authentication mechanism such as Encrypt-then-MAC is required, verifying the MAC **before** decryption.

**CTR:** derives a keystream from counter blocks; the ciphertext has the same length as the plaintext. If a counter block repeats under the same key, the keystream repeats and security is broken. CTR does not detect bit-flipping on its own.

**GCM:** an **AEAD (Authenticated Encryption with Associated Data)** mode that protects confidentiality and verifies integrity/authenticity via an **authentication tag**. In Java, `AES/GCM/NoPadding` is commonly used with a 12-byte nonce and a 128-bit tag, under the strict requirement of **never repeating a nonce when encrypting under the same key**. GCM does not handle key management, authorization rules, or replay protection for a valid packet on its own.

Distinction: ECB/CBC/CTR help illustrate mode mechanics and the risks of **encryption-only** schemes; AES-GCM illustrates an AEAD option that is generally better suited for new data. CBC/CTR attacks and HMAC Encrypt-then-MAC are studied in depth in lesson 6.5.

## 5. Padding Only Handles Length, Not Authentication

Some block modes like ECB/CBC require plaintext whose length is a multiple of 16 bytes if `NoPadding` is used. `PKCS5Padding` in Java JCE applies PKCS#7-style block padding rules compatible with AES: append `n` bytes, each having value `n`. If the plaintext is already block-aligned, **a full block of padding** is appended so unpadding is unambiguous.

| Plaintext | Padding Added with AES/CBC/PKCS5Padding | Ciphertext |
| ---: | ---: | ---: |
| 0 byte | 16 byte | 16 byte |
| 1 byte | 15 byte | 16 byte |
| 11 byte | 5 byte | 16 byte |
| 15 byte | 1 byte | 16 byte |
| 16 byte | 16 byte | 32 byte |
| 17 byte | 15 byte | 32 byte |

With an 11-byte input, five padding bytes are appended with hex value `05 05 05 05 05`. With 16 bytes, a full 16 bytes of value `10` are appended. **Valid padding does not prove the ciphertext has not been tampered with**; an attacker can manipulate CBC even when decryption throws no exception.

**NoPadding has different practical meanings:**

- `AES/ECB/NoPadding` and `AES/CBC/NoPadding` require input to be a multiple of 16 bytes; a trailing incomplete block can throw `IllegalBlockSizeException`.
- `AES/CTR/NoPadding` uses a keystream and can encrypt a 17-byte plaintext into 17 bytes.
- `AES/GCM/NoPadding` performs no block padding, yet **still produces an authentication tag**; a 128-bit tag adds 16 bytes to the ciphertext output.
- ChaCha20/ChaCha20-Poly1305 need no PKCS block padding; the AEAD variant has its own tag.

**Padding, Base64, and tags are three different things.** Base64/hex is merely a character representation of binary bytes. A tag/MAC checks authenticity under a key, not characters added to make the ciphertext block-aligned.

## 6. Key, IV/Nonce, Counter, AAD, and Tag

| Component | Role | Secret or Public? |
| --- | --- | --- |
| **Key** | Secret governing encryption/decryption and tag | Must be kept secret; generated from CSPRNG/KeyGenerator or KMS/keystore; supports rotation |
| **IV/nonce** | Parameter differentiating encryption invocations/mode state | Usually public; CBC needs a fresh unpredictable IV, GCM/ChaCha20 require non-repeating under the same key |
| **Counter** | Selects the next keystream block in CTR/ChaCha20 | Does not need to be secret, but must not reuse the same region under one key |
| **AAD** | Metadata that is authenticated but not encrypted | Can be public; the decryptor must supply the **exact same bytes** in the exact same order |
| **Tag** | Value authenticating ciphertext and AAD | Can be public; if the tag is invalid, **the plaintext must not be accepted** |

A GCM record may store `version || keyId || nonce || ciphertext || tag`; **do not** store the raw key next to the ciphertext. The Key ID only helps select the key and is not a secret. During decryption, the matching key/nonce/AAD/tag are required, and the tag must be verified successfully before using the plaintext or triggering any side effects.

A valid GCM tag **does not prevent replay on its own**: if an authenticated message is replayed intact, tag verification will still succeed. Replay protection requires sequence numbers/expiry/request IDs along with separate business state.

## 7. Java 17+: Testing the Difference Between Block and Stream

This standalone example **only demonstrates sizes**—**do not use ECB as a real data storage mechanism**. The program verifies that AES handles an exact 16-byte block, rejects a 17-byte plaintext when `NoPadding` is selected, and verifies that ChaCha20 encrypts/decrypts 17 bytes without padding.

Save the file **`BlockVsStreamDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.IllegalBlockSizeException;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.ChaCha20ParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class BlockVsStreamDemo {
    public static void main(String[] args) throws Exception {
        KeyGenerator aesKeys = KeyGenerator.getInstance("AES");
        aesKeys.init(128);
        SecretKey aes = aesKeys.generateKey();
        byte[] block = "0123456789abcdef"
                .getBytes(StandardCharsets.US_ASCII);

        // ECB here only demonstrates one raw AES block.
        Cipher ecb = Cipher.getInstance("AES/ECB/NoPadding");
        ecb.init(Cipher.ENCRYPT_MODE, aes);
        System.out.println("AES block bytes: " + block.length);
        System.out.println("AES one-block output: " + ecb.doFinal(block).length);

        boolean rejected = false;
        try {
            ecb.doFinal("seventeen-byte-xx"
                    .getBytes(StandardCharsets.US_ASCII));
        } catch (IllegalBlockSizeException expected) {
            rejected = true;
        }
        System.out.println("AES incomplete block rejected: " + rejected);

        SecureRandom rng = new SecureRandom();
        byte[] rawKey = new byte[32];
        byte[] nonce = new byte[12];
        rng.nextBytes(rawKey);
        rng.nextBytes(nonce);
        SecretKey chacha = new SecretKeySpec(rawKey, "ChaCha20");
        ChaCha20ParameterSpec params =
                new ChaCha20ParameterSpec(nonce, 1);
        byte[] message = "1234567890abcdefg"
                .getBytes(StandardCharsets.US_ASCII);

        Cipher enc = Cipher.getInstance("ChaCha20");
        enc.init(Cipher.ENCRYPT_MODE, chacha, params);
        byte[] ciphertext = enc.doFinal(message);

        Cipher dec = Cipher.getInstance("ChaCha20");
        dec.init(Cipher.DECRYPT_MODE, chacha, params);
        byte[] recovered = dec.doFinal(ciphertext);

        System.out.println("Stream input bytes: " + message.length);
        System.out.println("ChaCha20 ciphertext bytes: " + ciphertext.length);
        System.out.println("Stream round-trip: "
                + Arrays.equals(message, recovered));
        Arrays.fill(rawKey, (byte) 0);
    }
}
```

Run with JDK 17+ that has a provider supporting AES and ChaCha20:

```bash
javac --release 17 BlockVsStreamDemo.java
java BlockVsStreamDemo
```

Stdout verified with equivalent JDK commands:

```text
AES block bytes: 16
AES one-block output: 16
AES incomplete block rejected: true
Stream input bytes: 17
ChaCha20 ciphertext bytes: 17
Stream round-trip: true
```

**Reading the output:** `AES/ECB/NoPadding` rejects a 17-byte message without length handling, while plain ChaCha20 generates an exact 17-byte keystream to XOR with the message. The key and nonce are randomly generated, so the actual ciphertext bytes change, while the length and round-trip lines remain stable. Plain ChaCha20 here **does not authenticate the ciphertext**; do not use the demo as a production encryption scheme. `Arrays.fill` only clears the original buffer and does not guarantee clearing copies inside `SecretKeySpec` or the provider.

## 8. Decision Flow and Common Pitfalls

**When designing a new encryption feature:** determine upfront whether only confidentiality or also integrity is needed, along with key management scope, nonce handling, and data tampering risks. For many applications, choose a standard AEAD such as AES-GCM or ChaCha20-Poly1305, then define version/key ID/nonce/tag/AAD and write tamper and round-trip tests. Do not roll your own authentication by combining a mode with a public hash.

**When reading legacy data:** verify the exact mode/padding/IV/key/format used; do not guess provider defaults from `Cipher.getAlgorithm()`. You cannot convert legacy ECB/CBC ciphertexts to GCM simply by changing the transformation name in the reader. A compatibility and authenticated migration strategy is required.

Misconceptions to recognize:

1. AES-256 has a 256-bit block: **false**, an AES block is always 128 bits.
2. ECB hides data patterns automatically when using a strong key: **false**.
3. Successfully decrypting CBC/CTR means the ciphertext has not been modified: **false**.
4. NoPadding means there is no tag: **false** for GCM.
5. Reusing an IV/nonce/counter under the same key is harmless: **false**, especially for GCM and stream ciphers.
6. AAD is encrypted data: **false**, AAD is only authenticated.
7. A valid tag means the user is authorized: **false**, authorization is separate.
8. Calling `Cipher.getInstance("AES")` always selects GCM: **false**, the default mode/padding depends on the provider.

### Self-Check Questions

1. How many bytes are the key and block size of AES-256, respectively, and why?
2. How does a stream cipher handle 17 bytes differently from a raw AES block operation?
3. Why does ECB leak repeating patterns even with a longer key?
4. With CBC/PKCS5Padding, why does a 16-byte plaintext produce a 32-byte ciphertext?
5. What happens when CTR or ChaCha20 reuses the same keystream region?
6. Why does GCM NoPadding still have an authentication tag, and what must happen when the tag is invalid?
7. How do key, nonce, AAD, and tag differ in secrecy requirements and authentication capability?
8. Why does AEAD not automatically prevent replay, enforce authorization, or manage key lifecycles?

## References

- [Java SE 17 — Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): transformations, padding, and AEAD.
- [Java SE 17 — ChaCha20ParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/ChaCha20ParameterSpec.html): nonce/counter.
- [Java SE 17 — Java Cryptography Architecture](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): algorithms and providers.
- [NIST SP 800-38A](https://csrc.nist.gov/pubs/sp/800/38/a/final): ECB, CBC, CTR.
- [NIST SP 800-38D](https://csrc.nist.gov/pubs/sp/800/38/d/final): GCM and nonce/tag limits.
- [RFC 8439](https://www.rfc-editor.org/rfc/rfc8439.html): ChaCha20 and ChaCha20-Poly1305.

**Conclusion:** a block cipher describes a block-processing primitive, a stream cipher uses a keystream, a mode defines how a message is encrypted, and padding resolves length in block-based modes. **Data authentication is required whenever ciphertext can be modified**, rather than merely decrypting to bytes.