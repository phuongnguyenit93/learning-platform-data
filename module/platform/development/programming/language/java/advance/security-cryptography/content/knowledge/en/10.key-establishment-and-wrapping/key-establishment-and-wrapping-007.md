# 10.7 The Java 21 KEM API with Encapsulator, Decapsulator, and Encapsulation Messages

Starting in **Java 21**, the JDK includes the standard **`javax.crypto.KEM`** API (JEP 452) for performing a **Key Encapsulation Mechanism — KEM**. This bridges public-key cryptography and symmetric encryption: the sender uses the **recipient's public key** to generate a **shared secret** and an **encapsulation message**; the recipient uses the **corresponding private key** and the encapsulation message to recover the **same shared secret**. Both sides then use this secret as input to key derivation or data encryption.

This lesson's goal is to understand **`KEM`, `KEM.Encapsulator`, `KEM.Encapsulated`, `KEM.Decapsulator`**, the meaning of `key()`, `encapsulation()`, `params()`, the byte flow over the network, how to verify correctness, and how to combine KEM with **HKDF + AES-GCM** into an illustrative envelope. At the same time, you must recognize that **KEM does not encrypt files on its own, does not authenticate the sender on its own, and does not automatically form a complete security protocol**.

The main example uses **DHKEM + X25519**, compatible with the Java 21 API when the JDK provider supports this configuration. Available APIs and cryptographic profiles depend on the JDK/provider version; never assume every KEM algorithm, especially post-quantum families, is built into **JDK 21**.

## 1. What Problem Does KEM Solve?

Suppose Bob wants to receive confidential data from Alice. Bob creates or holds a key pair:

- **`pkR`**: public key that can be distributed to senders after verifying provenance;
- **`skR`**: private key Bob keeps secret.

Alice does not yet share a pre-existing AES key with Bob. Sending an AES key in plaintext would let an eavesdropper read it. KEM lets Alice establish a shared secret without sending that secret over the network.

```text
                   BOB (recipient)
               KeyPair(pkR, skR)
                     |
           pkR has been authenticated
                     |
                   ALICE (sender)
          Encapsulate(pkR) creates:
             sharedSecret_A
             encapsulationBytes
                     |
      send encapsulationBytes (do NOT send sharedSecret_A)
                     |
                   BOB
    Decapsulate(skR, encapsulationBytes)
                     |
             sharedSecret_B

    sharedSecret_A == sharedSecret_B
```

KEM consists of three foundational operations:

1. **Key generation (`KeyGen`):** creates a public/private key pair suited to the KEM algorithm. In the `DHKEM` with X25519 example, use `KeyPairGenerator.getInstance("X25519")`.
2. **Encapsulation (`Encap`):** takes a public key and returns a **shared secret and an encapsulation message**. The secret must stay private; the encapsulation message can be sent.
3. **Decapsulation (`Decap`):** takes a private key and an encapsulation message and returns the matching secret or an error per algorithm/provider.

**Key takeaway:** `encapsulationBytes` is data enabling the recipient to **recover the same secret**, **not** the encrypted file and not a Base64-encoded shared secret. Anyone who sees the encapsulation without the right private key should be unable to recover the shared secret under KEM's security model.

### 1.1. Why Is It Called “Key Encapsulation” Rather Than Simply “RSA Encrypt”?

With traditional RSA-OAEP key transport, the sender typically **pre-generates a small random key** and encrypts that key with RSA. With many KEMs (such as DHKEM), encapsulation **simultaneously generates** the shared secret and the encapsulation, rather than acting as a general-purpose function that accepts arbitrary key bytes and encrypts them. The Java API reflects this distinction directly: `Encapsulator.encapsulate()` **takes no plaintext message**.

Different KEMs can be built on DH/ECDH, lattices, or other primitives; Java's `KEM` is an **abstract interface** working through providers. The chosen algorithm and public/private keys must match; the `KEM` name does not mean every asymmetric key works with every KEM.

### 1.2. KEM Differs from Key Agreement and AEAD

| Component | Typical input / output | Purpose |
| --- | --- | --- |
| `KeyPairGenerator` | Algorithm → public/private key pair | Generate recipient keys |
| `KEM` | Algorithm name + provider | Select the KEM primitive |
| `Encapsulator.encapsulate()` | Configured public key → `SecretKey` + encapsulation bytes | Establish a shared secret from the sender side |
| `Decapsulator.decapsulate(bytes)` | Configured private key + encapsulation → `SecretKey` | Recover the shared secret on the recipient side |
| KDF/HKDF | Shared secret + context → application key(s) | Separate usage domains and derive appropriate keys/nonces |
| AEAD (AES-GCM, etc.) | Key + nonce + plaintext + AAD → ciphertext + tag | Encrypt data and authenticate ciphertext/metadata |
| Digital signature or authenticated protocol | Identity key and message | Authenticate origin when required by business logic |

Never use `KEM.encapsulate()` instead of `Cipher.doFinal(file)`. KEM **only handles establishing a shared secret**; MB/GB files must still go through symmetric encryption or properly designed authenticated streaming encryption.

## 2. Java 21 API: Four Key Types

JEP 452 adds classes in module `java.base`, package **`javax.crypto`**:

- **`KEM`:** factory/controller for a KEM algorithm, e.g., `KEM.getInstance("DHKEM")`; provides methods to create encapsulators or decapsulators.
- **`KEM.Encapsulator`:** sender-side object created from the **recipient's public key**; calling `encapsulate()` generates a fresh result.
- **`KEM.Encapsulated`:** result object holding **`SecretKey key()`**, **`byte[] encapsulation()`**, and **`byte[] params()`** (optional parameters, may be `null`).
- **`KEM.Decapsulator`:** recipient-side object created from the **corresponding private key**; calling `decapsulate(byte[])` recovers the shared secret.

### 2.1. Minimal Calls

```java
// Illustrative Java 21+ snippet, omitting key provisioning and try-catch.
KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
KeyPair receiverKeys = generator.generateKeyPair();

KEM kem = KEM.getInstance("DHKEM");

// Sender: only needs the receiver's authenticated public key.
KEM.Encapsulator sender = kem.newEncapsulator(receiverKeys.getPublic());
KEM.Encapsulated result = sender.encapsulate();
SecretKey senderSecret = result.key();
byte[] messageToSend = result.encapsulation();

// Receiver: must hold the corresponding private key.
KEM.Decapsulator receiver = kem.newDecapsulator(receiverKeys.getPrivate());
SecretKey receiverSecret = receiver.decapsulate(messageToSend);
```

This snippet shows API relationships and is not a complete Java file (missing `import`s and error handling). Two complete programs appear in later sections.

### 2.2. Distinguishing `KEM`, `Encapsulator`, `Encapsulated`, and `encapsulation()`

The names are similar, but their roles are very different:

| Java name | Kind | Meaning |
| --- | --- | --- |
| `KEM` | API object | Knows the KEM algorithm and creates appropriately keyed workers |
| `KEM.Encapsulator` | Sender-side object | Bound to recipient's public key and provider |
| `KEM.Encapsulated` | Result value | Holds the shared secret, encapsulation byte array, and optional params |
| `result.key()` | `SecretKey` | **Must be kept secret**, never put into the network envelope |
| `result.encapsulation()` | `byte[]` | **Transmittable message** for the receiver; not a secret |
| `result.params()` | `byte[]` or `null` | Optional parameters so both sides configure compatibly |
| `KEM.Decapsulator` | Receiver-side object | Bound to recipient's private key |
| `decapsulate(encapsulation)` | `SecretKey` | Resulting secret on the receiver side |

The API allows calling `Encapsulator.encapsulate()` multiple times; **each call** produces a fresh shared secret and message. Do not reuse secrets and data-encryption nonces as if they were a “pre-agreed long-term key.” In particular, never pass `encapsulation()` into `SecretKeySpec` to use as an AES key: that is **public data**, not a secret.

### 2.3. Important Overloads

```java
KEM.getInstance("DHKEM");
kem.newEncapsulator(recipientPublicKey);
kem.newEncapsulator(recipientPublicKey, secureRandom);
kem.newEncapsulator(recipientPublicKey, parameterSpec, secureRandom);

kem.newDecapsulator(recipientPrivateKey);
kem.newDecapsulator(recipientPrivateKey, parameterSpec);

encapsulator.encapsulate();
encapsulator.encapsulate(from, to, keyAlgorithm);

decapsulator.decapsulate(encapsulationBytes);
decapsulator.decapsulate(encapsulationBytes, from, to, keyAlgorithm);
```

The lines above are illustrative call signatures; `secureRandom`/`parameterSpec`/keys are variables that must be constructed with valid types, not a standalone program. In `encapsulate(int from, int to, String algorithm)`, `from`/`to` are **byte indices** into the shared secret slice to return (`to` is **exclusive**), and `algorithm` is the **algorithm name assigned to the returned SecretKey**. The matching decapsulator overload must use the **same range and algorithm**. Providers may not support every combination.

**Rule to remember:** the no-arg `encapsulate()`/`decapsulate(bytes)` returns a `SecretKey` whose `getAlgorithm()` is typically **`"Generic"`**. A `"Generic"` value is intended as input to a **KDF**, from which you derive AES/HMAC keys for the application context. Do not interpret `"Generic"` as a data-encryption algorithm named Generic.

### 2.4. Data Sizes: `secretSize()` and `encapsulationSize()`

- `Encapsulator.secretSize()` and `Decapsulator.secretSize()` return the **number of bytes** of the provider/algorithm's standard shared secret.
- `Encapsulator.encapsulationSize()` and `Decapsulator.encapsulationSize()` return the **number of bytes** of the encapsulation message.
- These are two semantically different sizes, even when a configuration happens to give the same number for both.
- In **DHKEM(X25519, HKDF-SHA256)**, the encapsulation is typically **32 bytes** and the standard shared secret is **32 bytes**; these values come from the algorithm/profile, not from a 32-byte plaintext file.
- Use the decapsulator's size metadata to validate inputs before parsing/passing to the provider; avoid allocating or processing unbounded arrays from the network.

If the key lives in an HSM/non-exportable provider, `SecretKey.getEncoded()` **may return `null`**. The size methods let you query sizes without extracting raw key bytes. When you need a KDF on a non-exportable secret, use the appropriate provider/HSM derivation feature; never force the application to log/export secrets.

### 2.5. Encapsulation Message Differs from File Ciphertext

In KEM literature, the encapsulation message **may also be called a KEM ciphertext**. Even so, it is not the data ciphertext returned by AES-GCM:

```text
encapsulationBytes              : public KEM message, lets receiver recover secret
sharedSecret                    : exists only internally at sender/receiver
payloadCiphertextAndTag         : application data encrypted with AEAD
envelope                        : metadata + encapsulationBytes + AEAD payload
```

Because both byte arrays may be called “ciphertext” at different protocol layers, use clear variable/schema names in code: **`kemEncapsulation`** and **`aeadCiphertext`**. Never accidentally send `key().getEncoded()` instead of `encapsulation()`.

## 3. Send–Receive Flow and the Three Fields `key`, `encapsulation`, `params`

A standard KEM exchange with the Java API:

```text
Sender                                                   Receiver
  |                                                          |
  | <-- authentic public key pkR / key ID / algorithm -------|
  |                                                          |
  | KEM.getInstance("DHKEM")                                 |
  | enc = kem.newEncapsulator(pkR).encapsulate()             |
  |   senderSecret = enc.key()      [KEEP SECRET]            |
  |   encBytes     = enc.encapsulation()                     |
  |   optParams    = enc.params()                            |
  |                                                          |
  | --- protocol header + encBytes (+ optParams if needed) ->|
  |                                                          |
  |                               kem.newDecapsulator(skR)   |
  |                               .decapsulate(encBytes)     |
  |                                  -> receiverSecret       |
  |                                                          |
  | HKDF(senderSecret, context)   HKDF(receiverSecret, context)
  |          |                                  |
  |       AEAD key ------------------------> same AEAD key   |
  |     encrypts data                  authenticates & decrypts
```

### 3.1. What Does the Sender Know?

The sender must hold the **authenticated target public key**, know the protocol-allowed **KEM algorithm**, know the suite/hash, and any accompanying parameters. The sender **does not need the recipient's private key**. Consequently, using KEM with the recipient's public key alone **cannot prove the sender's identity**: anyone holding the valid public key can perform a new encapsulation.

### 3.2. What Does the Receiver Need?

The receiver needs the **corresponding private key** and the exact KEM/suite/parameter configuration. Never pick a private key blindly from an untrusted `keyId`; the server must verify tenant, recipient, key version, rotation state, and algorithm allowlist. If the private key is lost, old encapsulations depending on it may become undecryptable under the storage architecture.

### 3.3. What Is `params()`?

`KEM.Encapsulated.params()` is an optional byte array holding **algorithm parameters** if the provider/algorithm needs extra data for the receiver to build a matching configuration. It **may be `null`**. For the JDK's default DHKEM/X25519 example, it is typically `null`.

If an algorithm requires an `AlgorithmParameterSpec`, Java provides `newEncapsulator(publicKey, spec, random)` and `newDecapsulator(privateKey, spec)`. When params are present, the receiver must **parse them per the provider/protocol definition**, check bounds/validity, and reconstruct the matching `AlgorithmParameterSpec` (when the provider supports `AlgorithmParameters`). You cannot pass `params()` arbitrarily into `decapsulate(byte[])` expecting auto-detection; `decapsulate` only takes **encapsulation bytes**.

### 3.4. Never Log `SecretKey` or Treat Binary Encapsulation as Secret

- **Shared secret / KDF output / AEAD key:** must stay secret; never log Base64, hex, byte arrays, or debug dumps.
- **Encapsulation:** does not normally require secrecy, but must have **integrity/context binding** at the envelope layer and strict input size limits.
- **Metadata:** version, key ID, suite, and optional params may be public, yet must never be assumed **authenticated** merely because they travel in the same message.

## 4. Standalone Java 21+ Example: `Encapsulator` and `Decapsulator`

This example uses **X25519** to create the recipient key pair, **DHKEM** to create an encapsulator and decapsulator, and verifies both sides recover the same shared secret. It also inspects `encapsulationSize()`, `secretSize()`, and failure when passing a truncated encapsulation message. **No secret bytes are printed**.

Save with exact name **KemBasicDemo.java**:

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.util.Arrays;
import javax.crypto.DecapsulateException;
import javax.crypto.KEM;
import javax.crypto.SecretKey;

public class KemBasicDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
        KeyPair receiverKeys = generator.generateKeyPair();

        KEM kem = KEM.getInstance("DHKEM");
        KEM.Encapsulator sender = kem.newEncapsulator(receiverKeys.getPublic());
        KEM.Encapsulated result = sender.encapsulate();

        byte[] encapsulation = result.encapsulation();
        SecretKey senderKey = result.key();

        KEM.Decapsulator receiver =
                kem.newDecapsulator(receiverKeys.getPrivate());
        SecretKey receiverKey = receiver.decapsulate(encapsulation);

        System.out.println("KEM algorithm: " + kem.getAlgorithm());
        System.out.println("encapsulation bytes: " + encapsulation.length);
        System.out.println("shared secret bytes: " + sender.secretSize());
        System.out.println("key algorithm: " + senderKey.getAlgorithm());
        System.out.println("same secret: "
                + MessageDigest.isEqual(
                        senderKey.getEncoded(), receiverKey.getEncoded()));
        System.out.println("optional params absent: "
                + (result.params() == null));

        boolean invalidLengthRejected = false;
        try {
            receiver.decapsulate(
                    Arrays.copyOf(encapsulation, encapsulation.length - 1));
        } catch (DecapsulateException expected) {
            invalidLengthRejected = true;
        }
        System.out.println("truncated encapsulation rejected: "
                + invalidLengthRejected);
    }
}
```

Use **JDK 21 or later** with a provider supporting `DHKEM` and `X25519`:

```bash
javac -encoding UTF-8 KemBasicDemo.java
java KemBasicDemo
```

Stdout from a common JDK DHKEM/X25519 configuration (verified):

```text
KEM algorithm: DHKEM
encapsulation bytes: 32
shared secret bytes: 32
key algorithm: Generic
same secret: true
optional params absent: true
truncated encapsulation rejected: true
```

### 4.1. Analyzing Each Call

**Step 1 — create key pair:** `KeyPairGenerator.getInstance("X25519")` uses the key-pair algorithm matching DHKEM over X25519. In production systems, the recipient's key pair is created, stored, and provisioned per policy, not generated fresh for every old file.

**Step 2 — select KEM:** `KEM.getInstance("DHKEM")` selects the KEM API from a provider. `DHKEM` is the algorithm name, while the specific profile (here X25519 + matching KDF) is determined by the key/provider support. `NoSuchAlgorithmException` or `InvalidKeyException` can be thrown if the algorithm/key is unsupported; the existence of the `KEM` class does not guarantee every provider supports every key type.

**Step 3 — encapsulation:** `sender.encapsulate()` returns **`KEM.Encapsulated`**, holding the sender-side secret and the `byte[]` message. In code, only the message bytes are transmitted.

**Step 4 — decapsulation:** `kem.newDecapsulator(receiverKeys.getPrivate())` creates the receiver side; `receiver.decapsulate(encapsulation)` returns a secret of equal value. The demo uses `getEncoded()` to compare for learning purposes; production code must account for **non-exportable** keys in HSMs/providers.

**Step 5 — sizes:** 32-byte encapsulation and 32-byte shared secret are specific to the DHKEM/X25519 profile in the example; **never** assume every KEM algorithm always outputs 32 bytes.

**Step 6 — truncated data:** `Arrays.copyOf(..., len - 1)` shrinks the message to 31 bytes. `DecapsulateException` shows invalid-length inputs are rejected.

### 4.2. A Very Common Misconception

**Modifying a byte in the encapsulation and calling `decapsulate()` does not always throw an exception.** With some KEMs, a tampered byte array that still has valid formatting can produce a **different shared secret** rather than a syntax error. Therefore, the receiver must use that secret in an **authenticated AEAD**; a tag failure is what stops accepting invalid plaintext. Never treat “decapsulation returned a SecretKey” as proof of a trustworthy sender or valid payload.

## 5. Using the Shared Secret: KDF, Domain Separation, and AEAD

KEM provides a shared secret; applications typically need **purpose-specific symmetric keys**. Using the entire raw secret directly as an AES key across protocols easily causes **key reuse** or missing context binding, especially when one KEM outcome supplies keys for encryption, MAC, or multiple purposes.

A controlled architecture:

```text
KEM encapsulate/decapsulate
        |
   shared secret (Generic)
        |
   HKDF-Extract/Expand + suite/context/version/recipient binding
        |
     +---------+----------+
     |                    |
   AEAD key           other purpose key (if designed in the protocol)
     |
 AES-GCM(key, nonce, plaintext, AAD)
     |
 ciphertext || authentication tag
```

### 5.1. What Does the KDF Do Here?

- **Adapts/sizes key material** to the target algorithm's length, e.g., 16 bytes for AES-128 or 32 bytes for AES-256.
- **Domain separation:** feeds protocol name, version, algorithm suite, purpose, and recipient/tenant into KDF `info` to prevent using one secret for unintended purposes.
- **Context binding:** both sides agree on the exact encoding of `info`. When contexts differ, derived keys differ and AEAD decryption fails.
- **Privilege scoping:** a key derived for encryption cannot naturally be reused as an HMAC or signing key for another protocol.

RFC 9180 DHKEM **already derives its secret internally from DH** per the KEM specification, yet that does not mean the output is a complete key schedule for every application. A separate application-context HKDF step remains valuable to derive AES keys and separate usage domains.

In Java 21, you can implement RFC 5869 HKDF using `Mac.getInstance("HmacSHA256")` or use an audited cryptographic library. **Do not assume `javax.crypto.KDF` is a standard API available in Java 21**; this lesson intentionally uses only APIs guaranteed in Java 21.

### 5.2. Why Is AES-GCM Needed After KEM?

KEM only produces a **key/secret** and an encapsulation message. It does **not** encrypt file plaintext, does not include a nonce, does not generate an authentication tag, and does not detect payload ciphertext tampering. With AES-GCM:

- `Cipher.getInstance("AES/GCM/NoPadding")` is the AEAD transformation.
- `GCMParameterSpec(128, nonce)` selects a **128-bit tag**, with nonce as a separate `byte[]`; a 96-bit/12-byte nonce is a common simple profile choice.
- `Cipher.updateAAD(...)` includes metadata/encapsulation in the authenticated-but-**unencrypted** data.
- `Cipher.doFinal(plaintext)` outputs ciphertext + tag in standard Java provider format.
- When decrypting, **let `doFinal()` verify the tag**; an `AEADBadTagException` means the plaintext must be rejected.

AES-GCM nonces **must never repeat under the same AES key**. For example, derive a fresh shared secret/KDF key per message and generate a random 12-byte nonce; when designing for multiple messages under one key, enforce a nonce strategy and per-protocol message limits, rather than relying only on “the nonce is 12 bytes long.”

### 5.3. Encryption Does Not Mean Sender Authentication

Knowing only the recipient's public key, **anyone** can encapsulate and encrypt a new payload that the receiver will decrypt. Thus, data encrypted with KEM + AEAD can **preserve confidentiality and ciphertext integrity for a key context**, but **does not prove authorship on its own**. If sender identity authentication is required, use an authenticated protocol, a digital signature over the envelope, mutual TLS, or explicit sender authentication per design; the signer/verifier's public key requires its own trust system.

## 6. Standalone Java 21+ Example: KEM → HKDF → AES-GCM

This program demonstrates a **simple in-memory envelope**. Alice encapsulates with Bob's X25519 public key; both sides derive an AES-128 key via one round of **HKDF-Extract + HKDF-Expand (16-byte output)**, use AES-GCM to encrypt a payload, and verify:

- Both sides decrypt the exact plaintext.
- Modifying the ciphertext is rejected by GCM.
- Modifying the AAD/header is rejected by GCM.
- Using the wrong private key on the receiver side fails to decrypt/authenticate the payload.

**Note:** the HKDF helper only implements **1 Expand block** to obtain a **16-byte AES key**; it is **not** a general implementation for arbitrary RFC 5869 `L`. The example keeps all bytes in RAM without wire serialization or real key-ID management.

Save **KemEnvelopeDemo.java**:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KEM;
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class KemEnvelopeDemo {
    private static final byte[] HEADER =
            "demo:v1|DHKEM-X25519|AES-128-GCM|recipient-01"
                    .getBytes(StandardCharsets.UTF_8);

    private static byte[] hmac(byte[] key, byte[]... inputs)
            throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        for (byte[] value : inputs) mac.update(value);
        return mac.doFinal();
    }

    // HKDF-SHA256 Extract, then Expand 1 block to get a 16-byte AES-128 key.
    private static SecretKeySpec deriveKey(SecretKey kemSecret)
            throws Exception {
        byte[] raw = kemSecret.getEncoded();
        if (raw == null) {
            throw new IllegalStateException(
                    "non-exportable KEM secret needs provider KDF support");
        }
        byte[] prk = hmac(new byte[32], raw); // zero salt per HKDF
        byte[] block = hmac(prk, HEADER, new byte[]{1}); // T(1)
        SecretKeySpec key =
                new SecretKeySpec(Arrays.copyOf(block, 16), "AES");
        Arrays.fill(raw, (byte) 0);
        Arrays.fill(prk, (byte) 0);
        Arrays.fill(block, (byte) 0);
        return key;
    }

    private static Cipher newGcm(int mode, SecretKeySpec key,
                                 byte[] nonce, byte[] enc, byte[] header)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(mode, key, new GCMParameterSpec(128, nonce));
        cipher.updateAAD(header);
        cipher.updateAAD(enc);
        return cipher;
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator keyGenerator =
                KeyPairGenerator.getInstance("X25519");
        KeyPair recipient = keyGenerator.generateKeyPair();
        KEM kem = KEM.getInstance("DHKEM");

        // Sender: holds the receiver's authenticated public key.
        KEM.Encapsulated result =
                kem.newEncapsulator(recipient.getPublic()).encapsulate();
        byte[] encapsulation = result.encapsulation();
        SecretKeySpec senderAesKey = deriveKey(result.key());

        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);
        byte[] plain =
                "file-content-from-sender".getBytes(StandardCharsets.UTF_8);
        byte[] ciphertextAndTag =
                newGcm(Cipher.ENCRYPT_MODE, senderAesKey,
                        nonce, encapsulation, HEADER).doFinal(plain);

        // Receiver: receives encapsulation + nonce + ciphertext and holds private key.
        SecretKey recoveredSecret =
                kem.newDecapsulator(recipient.getPrivate())
                   .decapsulate(encapsulation);
        SecretKeySpec recipientAesKey = deriveKey(recoveredSecret);
        byte[] recovered =
                newGcm(Cipher.DECRYPT_MODE, recipientAesKey,
                        nonce, encapsulation, HEADER)
                        .doFinal(ciphertextAndTag);

        System.out.println("encapsulation bytes: " + encapsulation.length);
        System.out.println("AES key bytes: "
                + senderAesKey.getEncoded().length);
        System.out.println("nonce bytes: " + nonce.length);
        System.out.println("GCM tag overhead bytes: "
                + (ciphertextAndTag.length - plain.length));
        System.out.println("round-trip: "
                + Arrays.equals(plain, recovered));

        byte[] edited = ciphertextAndTag.clone();
        edited[0] ^= 1;
        boolean tamperedCiphertextRejected = false;
        try {
            newGcm(Cipher.DECRYPT_MODE, recipientAesKey, nonce,
                   encapsulation, HEADER).doFinal(edited);
        } catch (AEADBadTagException expected) {
            tamperedCiphertextRejected = true;
        }
        System.out.println("changed ciphertext rejected: "
                + tamperedCiphertextRejected);

        boolean changedHeaderRejected = false;
        try {
            newGcm(Cipher.DECRYPT_MODE, recipientAesKey, nonce,
                   encapsulation, "demo:v2".getBytes(StandardCharsets.UTF_8))
                    .doFinal(ciphertextAndTag);
        } catch (AEADBadTagException expected) {
            changedHeaderRejected = true;
        }
        System.out.println("changed AAD rejected: "
                + changedHeaderRejected);

        KeyPair wrongRecipient = keyGenerator.generateKeyPair();
        SecretKey wrongSecret =
                kem.newDecapsulator(wrongRecipient.getPrivate())
                   .decapsulate(encapsulation);
        SecretKeySpec wrongAes = deriveKey(wrongSecret);
        boolean wrongPrivateKeyRejected = false;
        try {
            newGcm(Cipher.DECRYPT_MODE, wrongAes, nonce,
                   encapsulation, HEADER).doFinal(ciphertextAndTag);
        } catch (AEADBadTagException expected) {
            wrongPrivateKeyRejected = true;
        }
        System.out.println("wrong recipient key rejected: "
                + wrongPrivateKeyRejected);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 KemEnvelopeDemo.java
java KemEnvelopeDemo
```

Expected stdout with standard JDK DHKEM/X25519 and AES-GCM providers:

```text
encapsulation bytes: 32
AES key bytes: 16
nonce bytes: 12
GCM tag overhead bytes: 16
round-trip: true
changed ciphertext rejected: true
changed AAD rejected: true
wrong recipient key rejected: true
```

### 6.1. Reading the Encryption Flow

1. **`recipient`:** Bob's X25519 key pair. The demo generates the key pair in-process for ease of testing; a real system must provision public keys from a trusted source and store private keys per policy.
2. **`KEM.Encapsulated`:** contains a fresh shared secret and **32-byte encapsulation**. Only the encapsulation goes into the envelope; `result.key()` is never sent.
3. **`deriveKey`:** takes the shared secret, runs HKDF-Extract with a 32-byte zero salt for HMAC, then one HKDF-Expand step with `info = HEADER` and counter `0x01` to take **16 bytes** for AES-128. Both sender and receiver must use the **exact same HEADER** to derive the same key.
4. **`nonce`:** 12 random bytes for this encryption. The nonce does not need secrecy, but must not repeat under the same AES key.
5. **`cipher.updateAAD(HEADER)` then `updateAAD(encapsulation)`:** binds **header and encapsulation** to the GCM tag. If the receiver alters the header, nonce, or ciphertext, or uses the wrong key, verification fails.
6. **`ciphertextAndTag`:** encrypted payload + GCM tag; the demo does not write to a file. Length grows by **16 bytes** due to the 128-bit tag; nonce and encapsulation are kept separate.
7. **`doFinal` on decrypt:** treat plaintext as valid only when the tag passes. Never consume partial plaintext from a stream prior to verification in business logic.

### 6.2. Why Are There Two Derivation Steps?

In RFC 9180 DHKEM, the shared secret is already derived from Diffie–Hellman per the KEM design. Afterward, the application **continues using HKDF with application context** to obtain a key for a specific protocol. This separates the “established secret” from the “AES key used for payload in protocol version X.”

**Never** replace the HKDF helper with `new SecretKeySpec(encapsulation, "AES")`, because encapsulation is not secret. Nor should you take one shared secret and use it directly as multiple independent keys without a key schedule/domain separation.

### 6.3. Important Limitations of the Demo

- **DHKEM + a small HKDF + AES-GCM does not automatically become a full HPKE implementation**. RFC 9180 HPKE defines exact key schedules, suite IDs, nonce management, modes, and usage conditions; never label sample code “HPKE-compatible” unless it implements the full standard.
- The demo header is a **trusted program constant**, not a production serializer/parser. If headers have dynamic fields, use length-prefix/TLV/canonical formatting rather than concatenating strings with ambiguous delimiters.
- There is no sender authentication, anti-replay, key rotation, message limits, streaming, or access policy. This illustrates cryptographic building blocks, **not a production-ready protocol**.
- `getEncoded()` in `deriveKey` may return `null` if the secret is non-exportable; a provider/HSM may require internal KDFs and different key-handle mechanisms.
- `Arrays.fill` only clears owned temporary arrays on a best-effort basis; it **does not guarantee** erasing every copy inside the JVM/provider. The demo prints no raw keys, yet real applications must consider secret retention, logs, and crash dumps.
- The wrong-private-key test with X25519 may yield a different secret instead of throwing a decapsulation error; **AES-GCM** is what rejects the ciphertext under the wrong key. With other KEMs/providers, a bad encapsulation may fail right during decapsulation.
- A valid AEAD tag does not prove who the sender is, because **anyone can use the target public key** to produce a new encrypted message.

## 7. What Must an “Encapsulation Message” Contain on the Network?

`encapsulation()` alone contains only KEM bytes; it carries no version, recipient, nonce, or ciphertext. A real protocol needs an **envelope** describing all bytes required for the receiver to select the right algorithm/key and verify the entire payload.

Conceptual schema example:

```text
EnvelopeV1:
  magic/version                 :  supported format
  suiteId                       :  allowlisted KEM + KDF + AEAD
  recipientKeyId                :  ID selecting private key, scope-checked
  kemParamsLength/kemParams     :  if required by algorithm
  encapsulationLength           :  binary length, bounded
  encapsulationBytes            :  KEM message
  nonceLength/nonce             :  AEAD nonce
  ciphertextLength/ciphertext   :  AEAD ciphertext || tag
  associatedData                :  authenticated metadata (by convention)
```

**This is only a data layout**, not a standardized wire format or runnable Java code. A production format must specify byte order, length prefixes, versioning, maximum sizes, unknown-field handling, backward compatibility, and canonicalization of AAD-protected data.

### 7.1. Which Fields Are Public, Which Are Secret?

| Data | Transmittable? | Meaning |
| --- | --- | --- |
| Recipient public key | Yes, but must **authenticate origin** | Lets sender encapsulate for the right recipient |
| Recipient private key | **No** | Held solely by receiver or used inside HSM |
| `KEM.Encapsulated.key()` | **No** | Sender-side shared secret |
| `encapsulation()` | **Yes** | Must be sent so receiver can decapsulate |
| `params()` if required by algorithm | Yes if specified by protocol/provider | Receiver uses to build matching configuration |
| KDF-derived AES key | **No** | Internal use only |
| AEAD nonce | Yes | Decryption parameter, must be unique under one key |
| AES-GCM ciphertext + tag | Yes | Encrypted data and authentication tag |
| Suite, version, key ID, payload ID | Usually yes | Enables configuration lookup; must be validated and integrity-bound |

### 7.2. `keyId` Is Not Proof of Trust

`recipientKeyId` in an envelope comes from an external source. The receiver can use it to **look up an approved key**, but must validate tenant/object, version, policy, and status. Never automatically load keys from file paths or URLs constructed from an attacker-supplied `keyId`. Never allow a client to pick a weak algorithm or escape scope simply by editing `suiteId`.

### 7.3. Binding Metadata into AAD and KDF Context

If a header describes **recipient, protocol, suite, version, file ID, tenant** without authentication, an attacker can alter business semantics while the ciphertext remains valid under a misinterpretation. Canonicalize and feed integrity-relevant metadata into **AEAD AAD** per protocol, and feed appropriate context into **KDF info**.

KDF `info` and AAD serve two complementary purposes:

- **KDF info:** separates key domains (domain-separated key schedule).
- **AAD:** protects the integrity of metadata bytes attached to the ciphertext.

If a header contains multiple dynamic fields or could contain `|`, never use unescaped/non-length-prefixed `a|b|c` concatenation in a real protocol; two distinct parameter tuples can accidentally produce the same string. Standardize a canonical schema with cross-language test vectors.

### 7.4. `params()` Is Not `encapsulation()`

If `result.params() == null`, no non-empty params field is needed. If the algorithm requires params, the envelope must carry params bytes **separately**, and the receiver reconstructs the matching spec before creating the decapsulator.

Never append raw `params` onto `encapsulation` hoping the provider parses it automatically. Use `Decapsulator.encapsulationSize()` to validate the actual KEM message portion, not the length of the **entire envelope**.

## 8. KEM Errors, Wrong Results, and Failure Handling

### 8.1. Errors When Creating KEM/Encapsulator

| Error or state | Common cause | Handling |
| --- | --- | --- |
| `NoSuchAlgorithmException` | No provider supports KEM `"DHKEM"` or key algorithm | Check JDK/provider and policy; never silently fall back to a weak primitive |
| `InvalidKeyException` | Wrong public/private key or incompatible with KEM | Reject; check key type, trust, and version |
| `InvalidAlgorithmParameterException` | Wrong or missing `AlgorithmParameterSpec` | Follow algorithm/provider specification |
| `UnsupportedOperationException` | Overload/combination unsupported by provider | Choose an allowed profile or fix configuration; do not guess |
| `DecapsulateException` | Corrupted encapsulation, wrong length, or decapsulation failure | Reject request; log generic error without exposing private-key state |

### 8.2. Do Not Confuse Valid Syntax with a Valid Message

A 32-byte encapsulation passes only a **length** check, not proof that a trusted sender created it. A decapsulation that throws no exception also **does not prove** valid payload/metadata. You must:

1. Select KEM, key, and context from trusted configuration.
2. Validate byte lengths and format against an allowlist with memory bounds.
3. Decapsulate using an authorized private key.
4. Derive the AEAD key with the exact context.
5. Verify ciphertext/tag/AAD.
6. After verification, still check business authorization, anti-replay, expiration, and data validity.

Especially avoid returning detailed errors distinguishing private-key, encapsulation, tag, or policy failures. A generic response such as “Unable to process secure message” is far safer than revealing that a secret was “almost right.”

### 8.3. Tampered Data and Replay

**Tampering:** modifying ciphertext/AAD/tag must be rejected by AEAD. Modifying the encapsulation may cause either a decapsulation error **or** a different shared secret, causing the AEAD tag to fail. Never treat `decapsulate()` succeeding as sufficient.

**Replay:** an intact valid envelope resent unchanged can still decrypt cleanly. If the business operation requires replay protection (payments, state-changing commands), use timestamps, nonces/sequences, idempotency keys, replay caches, or atomic protocol state checks. AEAD and KEM **do not prevent replay on their own**.

**Truncation:** check payload length, framing, total chunk count, and finalization markers when streaming; each chunk having a valid tag does not guarantee the entire file is complete unless explicitly bound by the protocol.

## 9. KEM in Java 21 and Other Algorithms: Support Limits

`KEM.getInstance("DHKEM")` in the example is the **DHKEM** (Diffie–Hellman-based KEM) algorithm. With `X25519`, the corresponding mechanism is specified in **RFC 9180**. Other algorithms may be added by providers in future JDKs; **do not assume** Java 21 includes every post-quantum KEM merely because the `KEM` class exists.

| Concept | Usable with Java 21 KEM API? | Notes |
| --- | --- | --- |
| `javax.crypto.KEM`, `KEM.Encapsulator`, `KEM.Decapsulator` | **Yes**, standard API since Java 21 | Part of `java.base` |
| `DHKEM` with X25519 | Yes in common JDK profiles/providers | X25519 public/private keys; 32-byte encapsulation and secret in the example config |
| DHKEM with other curves | Depends on profile/provider | Do not assume identical sizes |
| Post-quantum KEMs such as ML-KEM | **Depends on JDK/provider/version** | Not described as built into JDK 21; verify on target runtime |
| High-level `javax.crypto.KDF` API | **Not a Java 21 API** | Example uses `Mac` to demonstrate HKDF |
| AES-GCM with `javax.crypto.Cipher` | Yes | Depends on key/nonce/tag and policy |
| Full HPKE | Not created automatically by `KEM.getInstance` alone | Requires exact key schedule, AEAD, mode, framing, and standard profile |

### 9.1. What Does Provider Selection Affect?

If you omit the provider in `KEM.getInstance(algorithm)`, Java may select different providers when creating **encapsulator** and **decapsulator** depending on the key/spec. You can inspect:

```java
String kemAlgorithm = kem.getAlgorithm();
String senderProviderName = encapsulator.providerName();
String receiverProviderName = decapsulator.providerName();
int kemMessageBytes = encapsulator.encapsulationSize();
int sharedBytes = decapsulator.secretSize();
```

This snippet illustrates the API and is not a complete program. Before deploying, test **matching key types, profiles, versions, params, and wire formats** on both sides. Never hardcode a provider name just to “make them match” when keys reside in an HSM: that specific provider may have its own key handles and require its own API.

### 9.2. Different Providers Do Not Mean Different Secrets

A standard KEM and profile must produce **compatible shared secrets** for the same key and encapsulation. Still, two runtimes both having the `KEM` class does not guarantee they support the same suites. With a Java 21 sender and a different-system receiver, both must agree on X25519 public-key encoding, DHKEM profile, encapsulation bytes, KDF algorithm, `info`, and AEAD wire format.

Use **cross-platform test vectors**; never rely on `toString()` or Java serialization of `SecretKey`/`KEM.Encapsulated` for protocol transport.

## 10. Security Responsibilities When Using KEM

### 10.1. Verify the Recipient's Public Key

KEM is only as trustworthy as Alice receiving Bob's real `pkR`. If an attacker replaces Bob's public key with the attacker's own, Alice encapsulates a shared secret the attacker can decapsulate and encrypts data for the wrong party. You need certificates/PKI, an authenticated directory, policy-driven key pinning, or a trusted provisioning workflow.

### 10.2. Protect Long-Term Private Keys

The recipient's private key may live in a Java KeyStore, HSM/KMS, or dedicated key management service. Restrict usage permissions, audit, back up, and rotate. If a static private key is compromised, historical envelopes retaining encapsulations and ciphertexts can be decrypted. Therefore, **KEM with a static recipient private key does not provide forward secrecy by default**, even though the sender uses an ephemeral key in DHKEM.

### 10.3. Key Rotation / Versioning

Envelopes should include `recipientKeyId` and `suiteVersion`. When rotating, senders use the newly authenticated public key; receivers may keep old keys within allowed policy to read legacy data. Losing an old private key before rewrapping/re-encrypting data can render old data unrecoverable. If a private key is compromised, revoke it, assess impact, and transition keys per incident response—do not merely rename the key ID.

### 10.4. Secret Handling

- Never print `result.key().getEncoded()` or derived AES keys in logs.
- Never send shared secrets in hex/Base64, because encoding is not encryption.
- Do not retain keys longer than needed; restrict debug access, heap dumps, and secret exports.
- Java's `Arrays.fill` clears byte arrays on a best-effort basis and gives no guarantee of wiping every copy inside the provider/JVM.
- If the provider keeps secrets non-exportable, prefer provider/key-handle KDF/AEAD operations instead of forcing raw key export.

### 10.5. KEM Does Not Solve Every System Requirement

A system using KEM + AEAD still needs **sender authentication**, authorization, anti-replay, expiration, nonce governance, input validation, an algorithm allowlist, resource limits, monitoring, and upgrade checks. Never equate successful decryption with permission to execute a business action.

## 11. Common Mistakes When Learning and Using `javax.crypto.KEM`

| Mistake | Why it is wrong | Correct practice |
| --- | --- | --- |
| Using `encapsulation()` as an AES key | Encapsulation is a public message | Use `key()` / `decapsulate()` for the secret, then KDF |
| Sending `result.key().getEncoded()` to the receiver | Leaks the shared secret, breaking security | Send only encapsulation and required metadata |
| Calling `encapsulate(fileBytes)` to encrypt a file | Java KEM has no arbitrary-message encrypt API | KEM establishes the secret; AEAD encrypts the payload |
| Treating KEM as a bulk data encryption algorithm | KEM only establishes a small key | Hybrid KEM + KDF + AES-GCM/streaming |
| Assuming `KeyPairGenerator("X25519")` proves it's Bob | Public keys can be swapped | Authenticate public key identity/provenance |
| Treating successful `decapsulate()` as sender authentication | Anyone with the public key can send a KEM message | Add sender authentication if needed |
| Treating `params()` as ciphertext | Optional params carry configuration | Parse into parameters per spec/protocol |
| Confusing `secretSize()` as bits | The API returns bytes | Multiply bytes × 8 when displaying bits |
| Hardcoding 32 bytes for every KEM | Sizes depend on algorithm/provider | Query `encapsulationSize()` and `secretSize()` |
| Calling `getEncoded()` without checking `null` | Non-exportable keys may not export | Use provider-internal KDF or supported interfaces |
| Assuming Java 21 includes all post-quantum KEMs | API class ≠ provider algorithm set | Verify actual JDK, provider, and policy |
| Using `javax.crypto.KDF` and claiming Java 21 compatibility | That API is not in Java 21 | Use `Mac`/Java 21–compatible HKDF libraries |
| Assuming no exception on tampered encapsulation means valid | Decapsulation can yield a different secret | Use AEAD to verify the final payload |
| Failing to bind version/keyId/AAD | Context confusion and downgrade | Canonical header, suite allowlist, authenticated metadata |
| Reusing the same AEAD key/nonce multiple times | AES-GCM nonce reuse can be catastrophic | Manage unique key/nonce pairs and usage limits |
| Calling hand-rolled KEM + AES “RFC 9180 HPKE” | HPKE defines key schedule, modes, and format | Follow the full HPKE suite or a standard library |
| Neglecting private-key rotation | Legacy data may be lost or exposed | Key ID, version, backup/re-encrypt/rewrap per policy |

## 12. KEM Code and Protocol Verification Checklist

1. **JDK/API:** is the application running Java 21+? Does `javax.crypto.KEM` exist and does the chosen provider support the intended profile?
2. **Key pair:** is the private key securely protected and does the recipient's public key come from an authenticated source?
3. **Algorithm:** is `KEM.getInstance("DHKEM")` compatible with the key type (e.g., X25519) on both sides?
4. **Encapsulation:** is only `encapsulation()` transmitted, with no shared secret or derived AES key exposed?
5. **Params:** if `params()` is non-null, does the receiver parse/validate it and build the matching spec?
6. **Sizes:** are `encapsulationSize()`, byte bounds, and version validated before decapsulating/allocating?
7. **KDF:** is the shared secret passed through a key schedule/domain separation with explicit context rather than using enc bytes or reusing one key across purposes?
8. **AEAD:** is the nonce unique per key, tag verified, AAD bound to metadata and encapsulation, and plaintext accepted only after verification?
9. **Authentication:** is sender authentication required, and is a dedicated mechanism used rather than treating public-key encryption as a signature?
10. **Envelope:** are byte encodings, key ID, suite, params, lengths, AAD, and cross-runtime/language compatibility specified and tested?
11. **Lifecycle:** are key rotation, backup/restore, incident response, private-key compromise, secret logging/heap dumps, and error handling addressed?
12. **Negative tests:** are truncated enc, wrong keys, wrong versions, tampered ciphertext/tag/header, replay, oversized inputs, and unsupported algorithms cleanly rejected?

## 13. Self-Check Exercises

**Q1.** Which class does Java 21 use to initialize a KEM, and what are the two nested classes on each side?  
**Answer:** `javax.crypto.KEM`; sender side is `KEM.Encapsulator`, receiver side is `KEM.Decapsulator`.

**Q2.** Does `sender.encapsulate()` return the encapsulation byte array directly or an object?  
**Answer:** A `KEM.Encapsulated` object; use `result.key()` for the secret, `result.encapsulation()` for the message bytes, and `result.params()` for optional params.

**Q3.** In DHKEM/X25519, the example produces a 32-byte encapsulation and a 32-byte shared secret. Are these two arrays identical?  
**Answer:** **No**. Same size does not mean same meaning. Encapsulation can be public; the shared secret must stay secret.

**Q4.** Alice sends `result.key().getEncoded()` over the network “so Bob can decrypt easily.” What is wrong?  
**Answer:** It directly exposes the shared secret. Bob must use his private key and `encapsulation()` to `decapsulate`, never receiving the raw secret.

**Q5.** An `encapsulation()` has one byte altered while remaining 32 bytes long. Is `decapsulate()` guaranteed to throw?  
**Answer:** No. Depending on the KEM/provider, it may produce a different secret. You must verify the payload and metadata AEAD tag to reject it.

**Q6.** If `encapsulate(0, 16, "AES")` succeeds, are the two numeric arguments bits or bytes?  
**Answer:** **Byte** offsets into the shared secret: `from=0`, `to=16` exclusive. The decapsulation overload must match; do not interpret them as bit 0 to bit 16.

**Q7.** Why can't the receiver recover the secret from `encapsulation()` using only the public key?  
**Answer:** Decapsulation requires the matching private key; the public key is insufficient to recover the shared secret under the security model.

**Q8.** Is using KEM + AES-GCM enough for Bob to know Alice sent the message?  
**Answer:** No. Anyone with Bob's public key can create a new secret/envelope. Separate sender authentication is required.

**Q9.** An envelope carries `keyId`, `nonce`, and `encapsulation`. Is parsing enough to trust those fields?  
**Answer:** No. They are external inputs; validate policy/key scope/lengths and bind critical metadata into AAD/KDF context.

**Q10.** Can you switch from Java 21 to another JDK and assume `KEM.getInstance("ML-KEM")` will always run?  
**Answer:** No. Algorithm support depends on the specific JDK/provider version; having the `KEM` class in Java 21 does not mean every KEM is available.

**Q11.** Once you have an encapsulation, do you still need an AES-GCM nonce and tag?  
**Answer:** **Yes** when using AES-GCM: KEM does not replace the nonce/tag and does not encrypt the payload.

**Q12.** Why isn't hand-assembled KEM + KDF + AES-GCM automatically compatible with HPKE?  
**Answer:** HPKE specifies exact suite IDs, KDF key schedule, mode, context, nonce policy, and protocol rules. Full HPKE compliance is required for interoperability.

## 14. API References

- [JEP 452 — Key Encapsulation Mechanism API](https://openjdk.org/jeps/452): introduces the motivation and design of the new API in JDK 21.
- [Java SE 21 — javax.crypto.KEM](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.html): contracts, factories, overloads, provider selection.
- [Java SE 21 — KEM.Encapsulator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Encapsulator.html): `encapsulate` and the two size methods.
- [Java SE 21 — KEM.Encapsulated](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Encapsulated.html): `key`, `encapsulation`, `params`.
- [Java SE 21 — KEM.Decapsulator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Decapsulator.html): `decapsulate`, errors, and input size.
- [RFC 9180 — Hybrid Public Key Encryption](https://www.rfc-editor.org/rfc/rfc9180): DHKEM, KDF, AEAD, and standard HPKE protocols.
- [RFC 5869 — HMAC-based Extract-and-Expand Key Derivation Function](https://www.rfc-editor.org/rfc/rfc5869): HKDF-Extract/Expand used in the key derivation example.

### Key Takeaway

**Java 21 `KEM` provides the key encapsulation primitive; `Encapsulator` generates the secret and encapsulation message; `Decapsulator` recovers the secret with the private key. Send only the encapsulation, never the secret.** From the shared secret, layer a **context-bound KDF + AEAD with nonce/AAD/tag**, verify public keys, select the right key ID/suite, and handle errors properly. KEM establishes keys safely per its algorithmic model, **and does not replace bulk data encryption, sender authentication, or a complete security protocol**.
