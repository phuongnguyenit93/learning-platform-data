# 10.8 Experimenting with DHKEM and Distinguishing Generated Keys from Encapsulation Data

## Objectives and Environment Requirements

**DHKEM** (*Diffie–Hellman Key Encapsulation Mechanism*) is a mechanism for establishing a **shared secret** using public-key cryptography. Once the sender has the **recipient's trusted public key**, the sender can simultaneously generate:

1. A **shared secret** for both sides to use internally as key material.
2. An **encapsulation message** that can be transmitted publicly to the recipient.

The recipient uses the **corresponding private key** and the encapsulation message to recompute the **same shared secret**, without the sender having to transmit the secret over the network.

This lesson explains the exact roles of both outputs, experiments with Java's `javax.crypto.KEM` API, inspects data lengths and types, and then uses the shared secret to derive an AES-GCM key. The topic falls under **Key Establishment and Wrapping**, yet you must distinguish KEM from **plain key agreement**, **key wrapping**, and **full HPKE**.

> **Version requirement:** `javax.crypto.KEM`, `KEM.Encapsulated`, `KEM.Encapsulator`, and `KEM.Decapsulator` were introduced in **Java 21** (JEP 452). The runnable program in this lesson requires **JDK 21 or later with a provider supporting `DHKEM` and `X25519`**. It **will not compile on Java 17**, even though X25519 and `KeyAgreement` already existed in Java 17. Do not substitute `KeyAgreement` and call it the same as DHKEM.

## 1. The Problem: Sharing a Secret Without Sending That Secret

Suppose Bob wants to receive encrypted data from Alice:

- Bob holds key pair `(pkR, skR)`: `pkR` is published **after authenticating that it truly belongs to Bob**, while `skR` must be protected.
- Alice knows `pkR`, but **does not know `skR`**.
- Alice needs to create a session key that Bob can also recover; this key must not appear in the public message.

**Base DHKEM** flow:

```text
                         SENDER (ALICE)              RECEIVER (BOB)
                         -----------------            -----------------
Has Bob's public key:    pkR -----------------------  pkR / skR
                                |                           |
                    KEM.newEncapsulator(pkR)                |
                                |                           |
                         encapsulate()                      |
                          /          \                      |
             shared secret K          encapsulation enc      |
               (KEEP SECRET)                   |             |
                    |                           | -------->  |
        Derive AEAD key                       (PUBLIC)       |
                    |                                         |
                    |                             newDecapsulator(skR)
                    |                             decapsulate(enc)
                    |                                         |
               shared secret K <------ equal value -----------+
                    |                                         |
         encrypt with derived key                 decrypt with derived key
```

**Important:** `encapsulation` is **not the shared secret**. It is the data needed by *the holder of the private key* to compute the shared secret. Anyone who sees `enc` and `pkR` knows the transport data; they **must not be able to deduce the secret key** while the scheme and key size remain secure.

With the Java API, keep this result pair in mind:

```java
// Illustrative snippet inside a method handling checked exceptions:
KEM.Encapsulated result = sender.encapsulate();
SecretKey secret = result.key();        // internal, must stay secret
byte[] enc = result.encapsulation();    // transmit to receiver
```

Do not name both variables `encryptedKey`: it blurs the distinction between the **secret** and the **encapsulation message**.

## 2. Distinguishing by Data Type, Where Used, and Secrecy Level

| Property | `KEM.Encapsulated.key()` | `KEM.Encapsulated.encapsulation()` |
| --- | --- | --- |
| Return type | `SecretKey` | `byte[]` |
| Nature | **KEM shared secret / keying material** | **KEM encapsulation message** (often called KEM ciphertext) |
| Where used | Sender keeps secret; derives session keys/KDF | Sender **transmits publicly** to recipient |
| What does recipient do? | Never receives `key()` over the network; recovers it via `decapsulate` | Feeds the exact bytes into `decapsulate(enc)` |
| Secrecy level | **Secret**: never log, never put in headers | **Not secret**: may be stored/sent alongside ciphertext |
| Representation | `SecretKey` usually has algorithm `"Generic"` with default `encapsulate()` | Byte encoding per chosen KEM; **does not carry an AES key itself** |
| Length | `encapsulator.secretSize()` | `encapsulator.encapsulationSize()` |
| Security purpose | Material for KDF to derive AEAD/MAC keys | Enables recipient holding `skR` to **reconstruct the secret** |
| If made public | Secret leakage; breaks confidentiality of data under that key | Normal in KEM design; **must not be assumed secret** |

**Equal length does not mean identical data.** Per RFC 9180, for `DHKEM(X25519, HKDF-SHA256)`, `Nsecret = 32 bytes` and `Nenc = 32 bytes`. This size coincidence makes beginners mistakenly treat `enc` as an AES-256 key. They have **completely different meanings**. Other suites show the difference more clearly:

| RFC 9180 KEM | KEM ID | `Nsecret` (bytes) | `Nenc` (bytes) |
| --- | --- | ---: | ---: |
| DHKEM(P-256, HKDF-SHA256) | `0x0010` | 32 | 65 |
| DHKEM(P-384, HKDF-SHA384) | `0x0011` | 48 | 97 |
| DHKEM(P-521, HKDF-SHA512) | `0x0012` | 64 | 133 |
| DHKEM(X25519, HKDF-SHA256) | `0x0020` | 32 | 32 |
| DHKEM(X448, HKDF-SHA512) | `0x0021` | 64 | 56 |

These are **values of standard RFC 9180 suites**, not a guarantee that the installed Java provider supports all of them. `KEM.getInstance("DHKEM")` combined with the matching **key type** lets the provider determine the variant; the protocol between two systems must still agree on the specific suite.

For `DHKEM(X25519, HKDF-SHA256)`, `enc` is the **sender's ephemeral public key serialized per KEM rules**, not the shared secret bytes and **not Bob's `pkR`**. Also, never replace `enc` with `recipient.getPublic().getEncoded()`: Java's encoded public key typically uses **X.509 SubjectPublicKeyInfo (DER)**, which has a different header and format from X25519 DHKEM's raw 32-byte `enc`.

## 3. What Does DHKEM Do Internally?

RFC 9180 §4.1 defines DHKEM using **Diffie–Hellman (DH)** and **HKDF** with domain separation. In **base mode**:

- Bob already has key pair `(skR, pkR)`.
- Alice generates an **ephemeral** key pair `(skE, pkE)` for this encapsulation.
- Alice computes `dh = DH(skE, pkR)`.
- Alice sends `enc = SerializePublicKey(pkE)`; she sends neither `skE` nor `dh`.
- Bob receives `enc`, reconstructs `pkE = DeserializePublicKey(enc)`, and computes `dh = DH(skR, pkE)`.
- Both sides run **HKDF LabeledExtract/LabeledExpand** over `dh` and the specified **kem_context** (`enc || SerializePublicKey(pkR)` in base mode) to obtain the same **`shared_secret`**.

Conceptual form (abbreviated to show structure, **not HKDF implementation code**):

```text
Encap(pkR):
    (skE, pkE) = GenerateKeyPair()
    enc = SerializePublicKey(pkE)
    dh = DH(skE, pkR)
    kem_context = enc || SerializePublicKey(pkR)
    shared_secret = ExtractAndExpand(dh, kem_context)
    return (shared_secret, enc)

Decap(enc, skR):
    pkE = DeserializePublicKey(enc)
    dh = DH(skR, pkE)
    kem_context = enc || SerializePublicKey(pkR)
    shared_secret = ExtractAndExpand(dh, kem_context)
    return shared_secret
```

In practice, the RFC also binds `suite_id`, `"KEM"`, labels, and lengths into HKDF; never replace it with a plain `KeyAgreement.generateSecret()` call and claim it yields the **same DHKEM bytes**. `KeyAgreement` can produce the **raw DH secret** without performing the full **DHKEM KDF and context binding**.

**Points to remember:**

1. `enc` is typically public data representing the **ephemeral public key**, not an AES-encrypted shared secret.
2. `shared_secret` is the output **after DHKEM's derivation step**, not necessarily identical to raw DH bytes.
3. Calling `encapsulate()` again with the same `pkR` generates a new ephemeral key, thus normally producing a **new `enc` and new secret**. Do not rely on randomness to produce fixed test vectors in production.
4. `decapsulate(enc)` with a different private key may produce **a different secret** instead of always throwing an exception. Successful `decapsulate` is **not authentication of application content**.
5. Base DHKEM does not prove “Alice is the sender,” because anyone holding `pkR` can `encapsulate`. To authenticate identity, use an appropriate protocol/certificate/signature or authenticated mode; never assume KEM handles that on its own.

## 4. Java 21+ API: Structure and Call Order

Java 21 provides `javax.crypto.KEM` as an **engine API** in module `java.base`.

| Step | Java API | Meaning |
| --- | --- | --- |
| Generate recipient pair | `KeyPairGenerator.getInstance("X25519")` | Creates Bob's DH key; `getPublic()` is distributed after authentication, `getPrivate()` is kept secret |
| Select KEM | `KEM.getInstance("DHKEM")` | Selects the Key Encapsulation Mechanism algorithm |
| Create sender object | `kem.newEncapsulator(pkR)` | Prepares to encapsulate using the recipient's public key |
| Produce result | `encapsulator.encapsulate()` | Produces `KEM.Encapsulated` containing **secret + encapsulation** |
| Get sender secret | `result.key()` | `SecretKey`, kept secret and passed into a KDF |
| Get transport message | `result.encapsulation()` | `byte[]`, sent to the recipient |
| Params if any | `result.params()` | **Optional** parameter bytes, may be `null`; do not assume every KEM needs or every suite has them |
| Create receiver object | `kem.newDecapsulator(skR)` | Prepares decapsulation with the recipient's private key |
| Recover secret | `decapsulator.decapsulate(enc)` | Returns a `SecretKey` matching the sender when input/key are valid |
| Check sizes | `secretSize()`, `encapsulationSize()` | Number of **bytes** of secret and encapsulation, **not interchangeable** |

`KEM` and `Encapsulator`/`Decapsulator` objects in the API are designed to be immutable and safe for concurrent operations per contract, yet the **returned secret material must still be protected**. Keys from a provider/HSM may be non-exportable; `getEncoded()` may return `null`. Use `secretSize()` when you need the length without depending on key exportability.

Typically, `encapsulate()` is equivalent to `encapsulate(0, secretSize(), "Generic")`. The `SecretKey` carries algorithm **`Generic`** because it is keying material for a KDF, not yet typed/parameterized to feed directly into AES.

The API also provides overloads `encapsulate(from, to, algorithm)` and `decapsulate(enc, from, to, algorithm)` to obtain a slice of key material tagged with an algorithm name (e.g., `"AES"`). Use those only when **both sides agree on the exact byte range, algorithm, and derivation policy**; the safer, more flexible protocol approach is feeding the full KEM secret into a **domain-separated KDF** to derive dedicated keys.

### 4.1 Do Not Pin a Provider Unnecessarily

```java
// Illustrative snippet inside a method handling checked exceptions:
KEM kem = KEM.getInstance("DHKEM");
KEM.Encapsulator sender = kem.newEncapsulator(receiverPublicKey);
String senderProvider = sender.providerName();
```

When calling `KEM.getInstance("DHKEM")` without specifying a provider, implementation selection may depend on the public/private key passed when creating the encapsulator/decapsulator. You can inspect `providerName()` on each object. **Do not assume both sides use the same provider**; they need agreement on the algorithm/variant and standard encoding, plus interoperability testing. `DHKEM` is the **KEM name**, while `X25519` is the **keypair generation / DH group algorithm**—the two strings are not interchangeable in `getInstance`.

## 5. Runnable Java 21 Program: Distinguishing Secret, Encapsulation, and Using AES-GCM

The code below creates an X25519 recipient, runs DHKEM, prints **only names/lengths/comparison booleans** (never secret hex), verifies both sides compute the same secret, and derives an AES-128 key via **HKDF-SHA256** to encrypt/authenticate a message with **AES-GCM**. Finally, it tampers with the ciphertext and truncates the encapsulation to observe rejection.

**Intentional limitation:** the application HKDF and AES-GCM here **illustrate a KEM → KDF → AEAD composition**, **not a standard RFC 9180 HPKE implementation**; HPKE also has a complete key schedule, mode, suite identifier, nonce/sequence, and context. In real applications, prefer a vetted HPKE library/protocol when HPKE wire compatibility is required.

Create file **`DhkemExperiment.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.DecapsulateException;
import javax.crypto.KEM;
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class DhkemExperiment {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final String MAC = "HmacSHA256";

    // HKDF-SHA256 Extract + one Expand block, L = 16 bytes.
    // Lesson-specific info: this is NOT the full HPKE key schedule.
    private static SecretKey deriveAes128(SecretKey kemSecret)
            throws GeneralSecurityException {
        byte[] ikm = kemSecret.getEncoded();
        if (ikm == null) {
            throw new GeneralSecurityException("Non-exportable key in demo");
        }
        Mac mac = Mac.getInstance(MAC);
        mac.init(new SecretKeySpec(new byte[32], MAC)); // no salt
        byte[] prk = mac.doFinal(ikm);                  // HKDF-Extract
        mac.init(new SecretKeySpec(prk, MAC));
        mac.update("DHKEM-demo/AES128GCM/v1"
                .getBytes(StandardCharsets.UTF_8));
        mac.update((byte) 1);
        byte[] okm = mac.doFinal();                    // HKDF-Expand T(1)
        return new SecretKeySpec(Arrays.copyOf(okm, 16), "AES");
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
        KeyPair recipient = generator.generateKeyPair();

        KEM kem = KEM.getInstance("DHKEM");
        KEM.Encapsulator sender = kem.newEncapsulator(recipient.getPublic());
        KEM.Encapsulated packet = sender.encapsulate();
        SecretKey senderSecret = packet.key();         // keep private
        byte[] enc = packet.encapsulation();           // send to receiver

        KEM.Decapsulator receiver = kem.newDecapsulator(
                recipient.getPrivate());
        SecretKey receiverSecret = receiver.decapsulate(enc);

        System.out.println("KEM: " + kem.getAlgorithm());
        System.out.println("Secret algorithm: " + senderSecret.getAlgorithm());
        System.out.println("Secret bytes: " + sender.secretSize());
        System.out.println("Encapsulation bytes: " + sender.encapsulationSize());
        System.out.println("Secrets match: " + MessageDigest.isEqual(
                senderSecret.getEncoded(), receiverSecret.getEncoded()));

        SecretKey writeKey = deriveAes128(senderSecret);
        SecretKey readKey = deriveAes128(receiverSecret);
        byte[] nonce = new byte[12];
        RANDOM.nextBytes(nonce);
        byte[] message = "Hello DHKEM".getBytes(StandardCharsets.UTF_8);

        Cipher encryptor = Cipher.getInstance("AES/GCM/NoPadding");
        encryptor.init(Cipher.ENCRYPT_MODE, writeKey,
                new GCMParameterSpec(128, nonce));
        encryptor.updateAAD(enc);
        byte[] body = encryptor.doFinal(message);

        Cipher decryptor = Cipher.getInstance("AES/GCM/NoPadding");
        decryptor.init(Cipher.DECRYPT_MODE, readKey,
                new GCMParameterSpec(128, nonce));
        decryptor.updateAAD(enc);
        byte[] recovered = decryptor.doFinal(body);
        System.out.println("AES-GCM round-trip: " + Arrays.equals(
                message, recovered));

        byte[] modified = body.clone();
        modified[0] ^= 1;
        Cipher verifier = Cipher.getInstance("AES/GCM/NoPadding");
        verifier.init(Cipher.DECRYPT_MODE, readKey,
                new GCMParameterSpec(128, nonce));
        verifier.updateAAD(enc);
        boolean tamperRejected = false;
        try {
            verifier.doFinal(modified);
        } catch (AEADBadTagException expected) {
            tamperRejected = true;
        }
        System.out.println("Tampered payload rejected: " + tamperRejected);

        boolean shortEncRejected = false;
        try {
            receiver.decapsulate(Arrays.copyOf(enc, enc.length - 1));
        } catch (DecapsulateException expected) {
            shortEncRejected = true;
        }
        System.out.println("Short encapsulation rejected: " + shortEncRejected);
    }
}
```

Compile and run in the directory containing the file (JDK 21 or later):

```bash
javac --release 21 DhkemExperiment.java
java DhkemExperiment
```

Stdout on a JDK supporting `DHKEM(X25519, HKDF-SHA256)` such as the test environment:

```text
KEM: DHKEM
Secret algorithm: Generic
Secret bytes: 32
Encapsulation bytes: 32
Secrets match: true
AES-GCM round-trip: true
Tampered payload rejected: true
Short encapsulation rejected: true
```

### 5.1 Reading the Results Properly

**What do the two 32-byte lines mean?**

- `Secret bytes: 32`: the KEM shared secret size of X25519/HKDF-SHA256 is 32 bytes.
- `Encapsulation bytes: 32`: the serialized ephemeral X25519 public key size as `enc` is 32 bytes.
- **You cannot infer** that `senderSecret.getEncoded()` equals `enc`, or that `enc` can be used as an AES key. Having **the same length is a coincidence of this variant**.

`Secret algorithm: Generic` indicates the default KEM returns **generic keying material**, not claiming it is already an AES-128/256 key. `Secrets match: true` proves that with matching public/private keys and the same `enc`, both sides compute the same secret. In the demo, byte comparison works because the provider returns **extractable** keys; production code working with HSMs may require provider KDF APIs without exporting secret bytes.

**Why run HKDF again when DHKEM already uses HKDF internally?** DHKEM uses HKDF to turn the **DH shared secret** into the **KEM shared secret**, bound to `kem_context`; meanwhile, the application needs to derive **purpose-specific keys** (such as AES-GCM, MAC, or exporter keys) bound to version/context information. `deriveAes128` illustrates HKDF-SHA256 with a 32-byte zero salt for extract (representing an absent salt per RFC 5869) and one expand block with custom `info` plus `0x01`, slicing 16 bytes for AES-128. This is **not the HPKE key schedule** and not a general-purpose HKDF library.

**What does AES-GCM verify?** Both sides derive the same AES key, use the same 12-byte nonce, and pass `enc` as **associated authenticated data (AAD)**, so decryption succeeds. Flipping a ciphertext byte causes the GCM tag check to fail. Truncating `encapsulation` from 32 to 31 bytes throws `DecapsulateException` due to invalid size.

> In the demo, AAD only binds `enc` to clarify the concept. Real protocols must also bind **version, suite ID, key ID, recipient/context/metadata requiring authentication** via an unambiguous encoding. Nonces must be **unique per AES-GCM key**, never reused under the same key. Base-mode KEM + AES-GCM does not authenticate the **sender's** name/identity.

### 5.2 Why Not Print the Raw Secret or Force Fixed Hex Output?

Every `encapsulate()` call generates a fresh ephemeral key and uses randomness. Therefore `enc` and `shared_secret` change on every run; printing hex to the console/logs risks leaking secrets and does not prove correctness. The lesson prints only types, lengths, equality, and AEAD outcomes. When reproducible **test vectors** are needed, use standard RFC 9180 vectors and dedicated test harnesses; never reuse fixed ephemeral private keys or nonces in production.

When testing `KEM` across providers, never assume `SecretKey.getEncoded()` always returns bytes. The API provides `secretSize()` to inspect length and provider-native mechanisms to use non-exportable keys. If a provider does not allow key export, the demo will fail cleanly inside the HKDF helper; real applications must adapt the KDF step to meet key policies.

## 6. Designing Transmission Data: What Can Be Sent, What Must Stay Secret?

A record using KEM to encrypt a payload with AEAD can be conceptualized as:

```text
+------------------+----------------+----------------+-------------------+
| version/suite ID | key ID (Bob)   | enc (public)   | nonce (public)    |
+------------------+----------------+----------------+-------------------+
| ciphertext (encrypted payload)            | AEAD tag (authenticated)   |
+--------------------------------------------------------------------------+

NEVER include fields: senderSecret / receiverSecret / privateKey.
```

Components and where they live:

| Data | Origin | Transmittable? | Notes |
| --- | --- | --- | --- |
| Bob's public key `pkR` | Bob/PKI/registry | Yes | Alice must authenticate that the key belongs to Bob and matches type/purpose. |
| Bob's private key `skR` | Bob/KMS/HSM | **No** | Keep secret; never store alongside ciphertext. |
| Sender's ephemeral private `skE` | Internal to DHKEM | **No** | Must never be exposed; created and managed by provider. |
| `enc` | `packet.encapsulation()` | **Yes** | The KEM message; must be validated against suite and size. |
| KEM shared secret | `packet.key()` / `decapsulate(enc)` | **No** | Material for deriving application keys. |
| AEAD nonce | Data encryptor | **Yes** | Must be unique per AEAD key; does not need secrecy. |
| AEAD ciphertext/tag | Data encryptor | **Yes** | Never use plaintext when tag fails. |
| Suite/version/key ID | Application protocol | Yes | Never let unauthenticated inputs force fallback to weak algorithms. |

**Encapsulation data is untrusted input to parsers and crypto providers.** Enforce length bounds, format, algorithm/key ID checks, and resource limits, handling decryption errors safely. `decapsulate` returning a `SecretKey` does not mean the source record was authenticated or the application ciphertext has integrity. Only after authenticating the payload/context with proper AEAD/signatures should the data drive business decisions.

## 7. Is `enc` a “Ciphertext Containing the Shared Key” in the Conventional Sense?

KEM literature sometimes calls `encapsulation` the **KEM ciphertext**. This terminology can mislead because it is **not** ciphertext of user data and is not necessarily a **directly encrypted key**.

For **DHKEM over a DH group**, `enc` is the **serialized ephemeral public key**. The shared secret arises from DH math between the sender's ephemeral private key and the recipient's private key, followed by a KDF. This differs from:

- Calling `Cipher.getInstance("AES/GCM/NoPadding")` to encrypt a message: output is **AEAD ciphertext + tag**.
- Calling `Cipher.wrap(aesKey)` with a key-encryption algorithm: creates a wrapped representation of **an already existing key**. Semantics/format depend on the wrap scheme.
- Calling `KeyAgreement.getInstance("X25519")`: produces a **raw DH shared secret** from one key on each side; the API **does not automatically produce an encapsulation format + RFC 9180 KDF**.
- Calling `KEM.encapsulate()`: **generates new key material along with a message enabling decapsulation**; the recipient recovers the same key material using its private key.
- Using **RFC 9180 HPKE**: combines **KEM + a specific KDF/key schedule + AEAD** in a standardized ciphersuite/mode, with context and multi-message rules.

Name variables according to purpose:

```text
KemOutput = {
    secret: KEM shared secret,         // private
    encapsulation: KEM transport bytes // public
}

Envelope = {
    kemId, recipientKeyId, enc,
    aeadNonce, encryptedPayloadAndTag
}
```

Never write `secret = enc`, `AES(enc, plaintext)`, or `recipientPrivateKey = packet.key()`. All three confuse roles and algorithms.

## 8. Experimental Failure Cases to Verify Yourself

| Scenario | Expected result | Explanation |
| --- | --- | --- |
| `encapsulate` with Bob.public, `decapsulate` with Bob.private | Secrets match | Matching recipient pair and KEM variant. |
| Using `enc` as an AES key because it is 32 bytes | **Design flaw** | `enc` is public and known to attackers; zero confidentiality. |
| Sending `packet.key().getEncoded()` to the recipient | **Design flaw** | Leaks shared secret on the wire, defeating KEM. |
| Using someone else's private key to decapsulate | Does not yield sender's secret; may yield a different secret or error | **Do not require one fixed exception** across all wrong-key/tamper cases. |
| Truncating `enc` from 32 to 31 bytes (X25519) | `DecapsulateException` | Wrong `encapsulationSize`; demonstrated in code. |
| Flipping 1 bit in `enc` while keeping valid length | May yield a different secret or be rejected; **no guaranteed tag-style rejection** | Base KEM has no application-data authentication tag. |
| Flipping 1 bit of AES-GCM body/tag | Rejected when tag verification fails | Integrity comes from AEAD, not KEM itself. |
| Modifying AAD `enc` after encryption while keeping body/tag | GCM verification fails | Binds `enc` to the authenticated ciphertext. |
| Calling `decapsulate()` without passing full `enc` | Error or wrong secret | Must pass exact encapsulation bytes per standard format. |
| Printing key material to check equality | Secret leakage risk | Compare internally or use dedicated test vectors; never log secrets. |
| Running on JDK 17 and importing `javax.crypto.KEM` | **Compilation error** | API starts in Java 21; use JDK 21+ or another specified algorithm/protocol. |
| Passing raw X25519 SPKI public key into `decapsulate` instead of `enc` | Wrong encoding/size | `enc` is not an arbitrary `PublicKey.getEncoded()`. |

**One crucial point:** never write tests asserting “every tampered encapsulation makes `decapsulate` throw” or “`decapsulate` succeeding means the peer is authenticated.” Both conclusions are false. Verify the **AEAD tag or protocol authentication** after establishing key material.

## 9. Choosing Algorithms, Providers, and Compatibility

### 9.1 Java 21 and RFC 9180

`DHKEM` is a name in **Java Security Standard Algorithm Names**. DHKEM groups defined by RFC 9180 have specific KEM IDs, KDFs, and encodings. Java's `KEM.getInstance("DHKEM")` can select a compatible implementation/variant based on key types/params; the Java 21 API does not automatically build a full application wire-format ciphersuite.

Good practices:

- Record the **protocol version**, chosen **KEM suite ID** per standard, recipient key ID, and agreed encapsulation format.
- Before decoding, validate `encapsulationSize()`, record size, and upper bounds on all length fields.
- If the application must interoperate with other languages, validate against **RFC 9180 test vectors** for the exact suite—do not rely only on “both use X25519.”
- When switching providers, test `encapsulate` on provider A and `decapsulate` on provider B with the same public/private keys, encoding, and params.
- Do not hardcode a specific provider such as `SunJCE` unless required for technical/compliance/HSM reasons, in which case document the dependency.
- If `KEM.getInstance()` or `newEncapsulator()`/`newDecapsulator()` reports an unsupported algorithm/key, treat it as a configuration error; **never silently fall back** to an unapproved KEM.

### 9.2 Selected Exceptions / API Behavior

| Location | Error or state | How to handle |
| --- | --- | --- |
| `KeyPairGenerator.getInstance("X25519")` | `NoSuchAlgorithmException` | JDK/provider does not support the key-generation algorithm. |
| `KEM.getInstance("DHKEM")` | `NoSuchAlgorithmException` | KEM unavailable on this runtime/provider. |
| `newEncapsulator(pkR)` / `newDecapsulator(skR)` | `InvalidKeyException` or missing parameter/provider support | Verify key type/source and policy; never swap public and private keys. |
| `encapsulate()` | Provider/randomness error | Never reuse failed output or substitute homemade keys/encapsulations. |
| `decapsulate(enc)` | `DecapsulateException` on invalid inputs such as bad size | Reject record; never log secrets, never fall back to another KEM. |
| `secret.getEncoded() == null` | Non-exportable key | Use provider-native/KDF APIs; **never assume byte[] is always present**. |
| `AES/GCM/NoPadding` `doFinal()` | `AEADBadTagException` | Ciphertext/key/nonce/AAD altered or mismatched; reject all plaintext. |

`KEM.Decapsulator.decapsulate(encapsulation)` checks the size of `enc`; in the example, an invalid 31-byte input is rejected. Yet **KEM structural validation does not replace payload authentication**.

### 9.3 Key Pair Lifecycle and Security Properties

- The recipient public key must be **authenticated** (PKI, pinning, trusted registry). If an attacker swaps `pkR` before the sender encapsulates, the sender shares a secret with the attacker instead of Bob.
- The recipient private key must be protected by an appropriate keystore/KMS/HSM, with key usage/policy, rotation, and historical retention while legacy records still need decryption.
- Using a fresh ephemeral sender key per call helps separate sessions, yet if Bob uses a **static recipient private key** that is later compromised, an attacker can decapsulate stored `enc` values. **There is no automatic forward secrecy against compromise of a static recipient key.**
- Base DHKEM (where anyone knowing `pkR` can encapsulate) **does not authenticate the sender**. AES-GCM only proves the ciphertext matches the session key; a separate origin/identity authentication mechanism is needed if required.
- Do not treat X25519 KEM as post-quantum. If your threat model requires post-quantum/hybrid PQ security, select a specified scheme and proper implementation rather than concatenating bytes from two KEMs and calling it secure.
- Digital signatures, key agreement, KEM, key wrapping, and AEAD address different layers. **Right APIs do not automatically ensure a right protocol**.

## 10. Extended Hands-On Exercises

**Exercise 1 — Observe lengths:** Run the program multiple times with X25519. Record `Secret bytes=32`, `Encapsulation bytes=32`, and equality outputs without printing secrets. Explain why equal length **does not** allow assigning `enc` as the key.

**Exercise 2 — Wrong recipient key:** Generate another X25519 pair and pass its private key to `decapsulate(enc)` from the first pair. If the provider returns a secret, compare it **internally** with the sender secret without assuming an exception must be thrown. Then pass that wrong key to AES-GCM to confirm the tag rejects the ciphertext.

**Exercise 3 — Wrong length:** Truncate/pad `enc` to 31 or 33 bytes; observe `DecapsulateException` and check `encapsulationSize()` beforehand so the parser rejects oversized/undersized input.

**Exercise 4 — Isolate failure sources:** Individually test (a) corrupted encapsulation, (b) corrupted AEAD body, (c) wrong AEAD nonce, (d) wrong AAD. Distinguish KEM errors from GCM tag errors without printing private keys or unauthenticated plaintext.

**Exercise 5 — Standardize format:** Propose a binary envelope containing magic/version, KEM suite, recipient key ID, `enc` length + bytes, AEAD nonce, ciphertext length + body/tag. Define encoding/endianness, max sizes, and AAD scope. Explicitly note **no field carries the KEM shared secret**.

**Exercise 6 — Interoperability:** If two providers are available, cross-test encapsulate/decapsulate across them. Keep suite/encoding consistent and verify results against RFC 9180 test vectors rather than testing only a single runtime.

## 11. Design and Review Checklist

- [ ] Runtime uses **Java 21+** for `javax.crypto.KEM`; not mistakenly assumed in Java 17 APIs.
- [ ] Recipient key pair matches `DHKEM` (e.g., X25519); public key identity is **authenticated**.
- [ ] `KEM.Encapsulated.key()` is protected as a **secret**, never sent, logged, or stored publicly.
- [ ] `KEM.Encapsulated.encapsulation()` is sent/stored as a **public transport message**, never treated as a raw secret or AES key.
- [ ] Receiver uses the **recipient private key** and exact `enc` bytes in `newDecapsulator(...).decapsulate(...)`.
- [ ] Protocol specifies suite/algorithm, encoding, and `encapsulationSize()`, with clear max-length and version/key ID fields.
- [ ] KEM shared secret is derived into purpose-specific keys using an appropriate **KDF/HPKE key schedule**; never substitute raw DH secrets for DHKEM output.
- [ ] Payload uses AEAD with proper nonce/tag/AAD; tag failure **fails closed**.
- [ ] Never claim `decapsulate` authenticates the sender, prevents replay, or always errors on bit-flipped encapsulations.
- [ ] Plan exists for managing/rotating recipient private keys and addressing compromise/forward secrecy under the threat model.
- [ ] Tests cover matching/mismatched keys, truncated `enc`, tampered payloads, mismatched AAD, cross-provider interop, and encodings.

## 12. Self-Check Questions

**1. How do `packet.key()` and `packet.encapsulation()` differ?**  
`key()` is a **secret `SecretKey`**, kept private and usually fed into a KDF. `encapsulation()` is the **public KEM message bytes** sent to the recipient, containing no copy of the raw secret.

**2. With X25519, why are both 32 bytes long?**  
Because RFC 9180 defines **`Nsecret = Nenc = 32`** for this suite. Both happen to share the same length, yet have different roles and generation mechanisms; many other suites have different `Nenc` and `Nsecret`.

**3. What data does Bob need to obtain the same shared secret?**  
His private key `skR` and the sender's `enc` bytes, plus consistent KEM/parameter selection. Bob **never receives the secret from the sender**.

**4. Does successfully calling `decapsulate(enc)` to get a `SecretKey` prove Alice sent it?**  
**No.** Base DHKEM allows anyone holding `pkR` to encapsulate; protocol-level sender authentication is needed if required.

**5. Can `getEncoded()` of an X25519 public key be used instead of `enc`?**  
**Not arbitrarily.** `enc` follows KEM serialization (32-byte raw ephemeral X25519 public key), whereas `PublicKey.getEncoded()` in Java is typically X.509 SPKI.

**6. Why won't the example run on Java 17?**  
The `javax.crypto.KEM` API was added in **Java 21**. `KeyAgreement` X25519 in older versions does not perform the same `DHKEM ExtractAndExpand` automatically.

**7. Does a modified encapsulation always trigger `DecapsulateException`?**  
**No.** Wrong-sized inputs fail, whereas valid-sized inputs with altered bytes can yield a different secret. **AEAD tags or separate authentication** are needed to detect application data tampering.

**8. Is the Java example in this lesson full RFC 9180 HPKE?**  
**No.** It uses standard DHKEM plus a simple custom-info HKDF and AES-GCM to teach how they compose. Official HPKE defines detailed key schedules, contexts, modes, and nonces and requires a dedicated implementation.

## Official References

- [Java SE 21 — `javax.crypto.KEM`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.html): sender/receiver model, `newEncapsulator`, `encapsulate`, `newDecapsulator`, `decapsulate`, provider selection.
- [Java SE 21 — `KEM.Encapsulated`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Encapsulated.html): `key()`, `encapsulation()`, `params()`, and their return types.
- [Java SE 21 — `KEM.Encapsulator`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Encapsulator.html): `secretSize`, `encapsulationSize`, `encapsulate` overloads.
- [Java SE 21 — `KEM.Decapsulator`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Decapsulator.html): `decapsulate` and error conditions.
- [Java SE 21 — `DecapsulateException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/DecapsulateException.html): decapsulation failure exception.
- [Java SE 21 — Standard Algorithm Names](https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html): `DHKEM` under KEM names and algorithm standardization.
- [OpenJDK JEP 452 — Key Encapsulation Mechanism API](https://openjdk.org/jeps/452): rationale and scope of the API (JDK 21).
- [RFC 9180 — Hybrid Public Key Encryption](https://www.rfc-editor.org/rfc/rfc9180.html): §4.1 DHKEM, §7.1 KEM IDs and Nsecret/Nenc lengths, §5 HPKE key schedule/context.
- [RFC 5869 — HMAC-based Extract-and-Expand Key Derivation Function (HKDF)](https://www.rfc-editor.org/rfc/rfc5869): extract/expand and KDF-level context binding.

**Takeaway:** `KEM.encapsulate()` **produces two things**: a **`SecretKey` to keep secret and derive keys from**, and an **`encapsulation` to send publicly to the recipient**. `decapsulate(enc)` combines that public data with the **private key** to re-establish the shared secret. Using `enc` as a secret key is a severe design bug; equally, never confuse base KEM with AEAD encryption, identity authentication, or full HPKE.
