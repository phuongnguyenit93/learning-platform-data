# 8.8 Configuring OAEPParameterSpec, Digest, MGF1, and Label Consistently Between Both Parties

## Learning Objectives

After this lesson, you will:

1. Explain why RSA-OAEP requires a **consistent parameter set** rather than merely agreeing on "RSA, SHA-256".
2. Distinguish **OAEP digest**, mask generation function **MGF1**, **digest inside MGF1**, and **label (PSource.PSpecified)**.
3. Use **javax.crypto.spec.OAEPParameterSpec** in Java 17+ to specify all three parts explicitly instead of relying on transformation-name or provider defaults.
4. Perform Java 17 RSA-OAEP encryption/decryption, inspect effective configuration, and observe errors when the digest, MGF1 digest, or label mismatches.
5. Design a Java ↔ Java or Java ↔ external system interoperability contract, handle RSA size limits, and integrate RSA-OAEP into a secure **hybrid encryption** model.

**Key point to remember:** Two sides only decrypt RSA-OAEP interoperably if **the RSA key is right, the OAEP hash is right, the MGF is right, the MGF1 hash is right, and the label bytes match identically**, along with agreed key size and ciphertext format. A transformation string naming SHA-256 **is not enough to guarantee MGF1 also uses SHA-256** across all providers.

## 1. Why Must RSA Have OAEP?

RSA is a public-key algorithm: the encrypting side uses the recipient's **public key**, and the decrypting side uses the matching **private key**. Primitive RSA cannot be used directly on application data as an arbitrary "RSA encrypt(raw message)". Secure encryption requires an **encoding/padding mechanism designed for RSA encryption**.

**RSAES-OAEP (Optimal Asymmetric Encryption Padding)** is a randomized RSA encryption scheme defined in PKCS #1 / RFC 8017. It combines:

- The input message byte string M.
- An **OAEP hash** used in structuring the data block (notably hashing the label).
- A **mask generation function**, typically MGF1, with MGF1's own hash algorithm.
- A label L (which may be empty).
- An internal random OAEP seed.

RSA-OAEP ciphertexts differ across encryptions even when the public key and plaintext stay identical, because OAEP uses randomness. The sender does not need the private key to encrypt; the recipient must hold the private key to decrypt.

~~~text
Side A / Sender                                Side B / Recipient

B's public key                                 B's private key
Plaintext M                                    Ciphertext C
OAEP params P                                  OAEP params P
      |                                              |
  RSAES-OAEP encrypt                               RSAES-OAEP decrypt
      |                                              |
      +---------------- C ------------------------->+
                                                     |
                                               M or decryption error

P = (OAEP hash, MGF=MGF1, MGF1 hash, label bytes)
~~~

The encrypting and decrypting sides must use the **same OAEP params P**, while using keys in opposite roles: public key for encryption, private key for decryption.

**Do not confuse OAEP with digital signatures:** RSA-OAEP is an **encryption** scheme for a recipient. Anyone holding the public key can encrypt a message for the recipient; OAEP does not by itself prove the sender's identity. RSA-PSS is a separate **digital signature** mechanism that also uses MGF1, but configures it via **PSSParameterSpec**, not OAEPParameterSpec.

## 2. Four Important Fields in OAEPParameterSpec

In Java, **javax.crypto.spec.OAEPParameterSpec** takes four arguments:

~~~java
new OAEPParameterSpec(
    String mdName,               // Main OAEP hash
    String mgfName,              // MGF name, typically "MGF1"
    AlgorithmParameterSpec mgfSpec, // Digest inside MGF1
    PSource pSrc                 // Label, typically PSource.PSpecified
);
~~~

This is an explanatory constructor signature, not a standalone program. For actual use, provide objects, proper imports, and pass the spec to **Cipher.init(...)**.

| Parameter | Meaning | Explicit example |
| --- | --- | --- |
| **mdName** | Main hash in the OAEP algorithm, used to compute `lHash` of the label and determine `hLen` | "SHA-256" |
| **mgfName** | Mask generation algorithm; in the common scheme this is MGF1 | "MGF1" |
| **mgfSpec** | MGF1 parameters, typically **MGF1ParameterSpec** holding the hash used by MGF1 | MGF1ParameterSpec.SHA256 |
| **pSrc** | Source of encoding input P, normally **PSpecified(label bytes)** | new PSource.PSpecified(labelBytes) |

### 2.1 OAEP Digest and MGF1 Digest Are **Two Separate Choices**

Example:

~~~java
OAEPParameterSpec p = new OAEPParameterSpec(
    "SHA-256",
    "MGF1",
    MGF1ParameterSpec.SHA256,
    PSource.PSpecified.DEFAULT
);
~~~

Here:

- OAEP hash = **SHA-256**.
- MGF = **MGF1**.
- MGF1 hash = **SHA-256**.
- Label = **byte[0]** (empty).

Another valid configuration has OAEP hash = SHA-256 yet MGF1 hash = SHA-1. Those two configurations **cannot interoperate to decrypt each other's ciphertexts**, even though both are loosely described as "RSA OAEP SHA-256".

Do not infer the MGF1 digest merely by reading **OAEPWithSHA-256AndMGF1Padding**. That name states the OAEP hash and MGF name, yet **does not explicitly state MGF1's internal hash**.

**Interoperable configuration requires specifying both hashes independently.** Setting both to SHA-256 is a consistent choice common in new systems when both sides support it, though the primary requirement remains agreeing via protocol and verifying in practice.

### 2.2 What Does OAEPParameterSpec.DEFAULT Mean?

Java SE 17 defines **OAEPParameterSpec.DEFAULT** as:

~~~text
OAEP digest = SHA-1
MGF         = MGF1
MGF1 digest = SHA-1
PSource     = PSpecified.DEFAULT = empty byte[]
~~~

This is the **default value of the OAEPParameterSpec.DEFAULT object**, not a guarantee that every Java transformation uses these values when no params are supplied. Providers and transformations may apply their own defaults.

For new services, **do not choose SHA-1 simply because it is the spec's default**. Explicitly design allowed algorithms and choose secure parameters suited to current requirements, such as SHA-256/MGF1-SHA-256.

Source: [Oracle Java SE 17 — OAEPParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/OAEPParameterSpec.html).

### 2.3 "ECB" in RSA Transformations Does Not Mean AES ECB Block Mode

Java JCA has common transformation names:

~~~text
RSA/ECB/OAEPPadding
RSA/ECB/OAEPWithSHA-256AndMGF1Padding
~~~

For RSA in these names, **ECB** is a historical API mode-naming convention, not a recommendation for AES-ECB or splitting data into ECB blocks. RSA-OAEP processes a single message bounded in size by the RSA modulus. Never apply block-cipher ECB rules to infer RSA security or streaming behavior.

When writing interoperable code, you can select **RSA/ECB/OAEPPadding** with an explicit `OAEPParameterSpec`. What determines behavior is the **actual parameter set passed to `Cipher.init`**, provider support, and two-way communication testing.

## 3. What Is MGF1 and Why Does Its Hash Matter?

**MGF (Mask Generation Function)** derives mask bytes from a seed and target length. **MGF1** invokes a hash function to produce a mask of arbitrary required length as defined in PKCS #1.

Intuitively:

~~~text
MGF1(seed, length, Hash)
            |
    Hash(seed || counter0)
    Hash(seed || counter1)
    Hash(seed || counter2)
            |
  Concatenate bytes and truncate to required length
            |
         mask bytes
~~~

This is only a conceptual diagram; applications never re-implement MGF1 themselves. **java.security.spec.MGF1ParameterSpec** specifies the hash for MGF1, such as **MGF1ParameterSpec.SHA256**.

The difference between OAEP hash and MGF1 hash is a **real protocol parameter**, not alternate spellings of the same setting:

| Configuration | OAEP hash | MGF1 hash | Label |
| --- | --- | --- | --- |
| P1 | SHA-256 | SHA-256 | empty |
| P2 | SHA-256 | SHA-1 | empty |
| P3 | SHA-256 | SHA-256 | UTF-8 bytes of "app:v1" |
| P4 | SHA-256 | SHA-256 | UTF-8 bytes of "app:v2" |

**P1, P2, P3, and P4 are distinct configurations**; ciphertext created under one generally fails to decrypt under another. This is OAEP's intended verification mechanism, not a library bug.

When two parties exchange technical specifications, document **mgfDigest** explicitly, not just "MGF1".

Source: [Oracle Java SE 17 — MGF1ParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/MGF1ParameterSpec.html).

## 4. OAEP Label: PSource.PSpecified and Byte-for-Byte Agreement

### 4.1 What Is the Label?

In RSAES-OAEP, **label L** is an optional byte string incorporated into encoding. OAEP computes **lHash = Hash(L)** and embeds it into the structure verified on decryption. Thus, if the decrypting side's label differs from the encrypting side's label, OAEP structural verification fails.

Java uses **PSource.PSpecified**:

~~~java
byte[] label = "app:v1".getBytes(StandardCharsets.UTF_8);

OAEPParameterSpec params = new OAEPParameterSpec(
    "SHA-256",
    "MGF1",
    MGF1ParameterSpec.SHA256,
    new PSource.PSpecified(label)
);
~~~

This is an illustrative snippet requiring the appropriate imports; see the complete Java program below.

Default:

~~~java
PSource.PSpecified.DEFAULT
~~~

corresponds to an **empty label (`byte[0]`)**. It is **not** the text string `"DEFAULT"`, not a single null character, and not a secret password.

### 4.2 Labels Must Match **Byte-for-Byte**, Not Merely Look Alike

Example:

~~~text
UTF-8("app:v1")   = 61 70 70 3a 76 31
UTF-8("app:v2")   = 61 70 70 3a 76 32
UTF-8("app:v1 ")  = 61 70 70 3a 76 31 20
empty label       = (0 bytes)
~~~

Differing by even a single byte renders the two sides' OAEP operations incompatible.

If a label contains Unicode, standardize the **charset** (usually UTF-8), normalization rules, whitespace, casing, and formatting. Two visually identical strings can have different Unicode representations, yielding **different label bytes**.

**Never use the default charset via zero-arg `getBytes()`** or let one side encode the label as UTF-8 while the other uses UTF-16. Never trim/canonicalize on one side without specifying it on the other.

### 4.3 Is the Label a Secret or Like AES-GCM AAD?

**No.** The label is a public parameter of the OAEP operation; it is not a key or secret. It creates a binding between the ciphertext and the chosen byte string, yet does not prove the sender and **does not substitute for application-wide message/metadata authentication**.

Specifically:

- The label does not separately encrypt any content.
- The label does not prove the ciphertext author's identity; anyone with the public key and label can encrypt.
- A mismatched label causes decryption to fail, yet does not prevent replaying an old valid ciphertext.
- In hybrid encryption, **AES-GCM AAD** protects payload metadata per its design; the OAEP label does not automatically protect all metadata fields of an application packet.
- **RFC 8017 specifies the empty label** for basic usage and notes that other label uses fall outside the specification's default usage scope. In deployment, pick a non-empty label only when both libraries/protocols confirm support.

When integrating with a peer that does not support custom labels, agree on an **empty label** from the start instead of assuming the peer uses the same string label as Java.

Source: [Oracle — PSource.PSpecified](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/PSource.PSpecified.html), [RFC 8017 §7.1](https://www.rfc-editor.org/rfc/rfc8017.html#section-7.1).

## 5. An Explicit, Agreed OAEP Configuration

An example wire contract could state:

~~~text
Protocol:              encrypted-key-v1
Asymmetric algorithm:  RSAES-OAEP
RSA modulus:           2048 bits or stronger by policy
OAEP digest:           SHA-256
MGF algorithm:         MGF1
MGF1 digest:           SHA-256
Label bytes:           61 70 70 3a 76 31 (UTF-8 "app:v1")
Ciphertext encoding:   Base64 (RFC 4648 basic, padded)
Public key wire form:  X.509 SubjectPublicKeyInfo (DER or PEM)
Private key storage:   PKCS#8 or secured keystore/KMS
Error handling:        decryption failure -> reject, no plaintext use
~~~

This is an **application-defined example contract**, not an existing standard named `encrypted-key-v1`.

The key point is documenting **all three parts (digest/MGF1/label)** plus byte representations and key formats. If the sender only specifies "SHA-256" or "OAEP", the recipient still lacks enough information to configure decryption accurately.

### 5.1 Do Not Let External Data Dictate the Algorithm

A record may contain metadata such as version/keyId for the recipient to pick a configuration from an **allowed list**. However, never take an attacker-controlled string directly as a `Cipher` transformation name or silently accept weaker modes if decryption fails.

Better approach:

1. Server maintains a **version → fixed algorithm policy** table.
2. Version metadata only selects among supported versions.
3. Key ID is verified to belong to the right tenant/recipient/permissions.
4. Server rejects unknown versions/algorithms; never loop through multiple configurations until "plaintext comes out".
5. Key and version rotation follow clear procedures; never downgrade to non-OAEP RSA just because a ciphertext failed to decrypt.

## 6. Complete Java 17+: Valid Spec, Wrong MGF1, Wrong Label

Create **RsaOaepSpecDemo.java** (saved as UTF-8). The program generates a 2048-bit RSA pair for demonstration, configures OAEP digest SHA-256, MGF1 digest SHA-256, label **app:v1**, and tests three mismatched configurations.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.AlgorithmParameters;
import java.security.GeneralSecurityException;
import java.security.Key;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.spec.MGF1ParameterSpec;
import java.util.Arrays;
import java.util.HexFormat;

import javax.crypto.BadPaddingException;
import javax.crypto.Cipher;
import javax.crypto.IllegalBlockSizeException;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;

public class RsaOaepSpecDemo {
    private static final String TRANSFORMATION = "RSA/ECB/OAEPPadding";

    private static OAEPParameterSpec spec(String digest,
                                          MGF1ParameterSpec mgfDigest,
                                          String label) {
        return new OAEPParameterSpec(
                digest,
                "MGF1",
                mgfDigest,
                new PSource.PSpecified(
                        label.getBytes(StandardCharsets.UTF_8))
        );
    }

    private static byte[] encrypt(PublicKey key,
                                  byte[] plaintext,
                                  OAEPParameterSpec params)
            throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(Cipher.ENCRYPT_MODE, key, params);
        return cipher.doFinal(plaintext);
    }

    private static byte[] decrypt(PrivateKey key,
                                  byte[] ciphertext,
                                  OAEPParameterSpec params)
            throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(Cipher.DECRYPT_MODE, key, params);
        return cipher.doFinal(ciphertext);
    }

    private static boolean rejected(PrivateKey key,
                                    byte[] ciphertext,
                                    OAEPParameterSpec wrongParams)
            throws GeneralSecurityException {
        try {
            decrypt(key, ciphertext, wrongParams);
            return false;
        } catch (BadPaddingException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();

        OAEPParameterSpec correct = spec(
                "SHA-256", MGF1ParameterSpec.SHA256, "app:v1");

        byte[] message = "demo RSA-OAEP"
                .getBytes(StandardCharsets.UTF_8);

        Cipher sender = Cipher.getInstance(TRANSFORMATION);
        sender.init(Cipher.ENCRYPT_MODE, pair.getPublic(), correct);

        // Read effective parameters after init instead of relying on the padding name alone.
        AlgorithmParameters effective = sender.getParameters();
        OAEPParameterSpec actual =
                effective.getParameterSpec(OAEPParameterSpec.class);

        System.out.println("OAEP digest: " + actual.getDigestAlgorithm());
        System.out.println("MGF: " + actual.getMGFAlgorithm());
        System.out.println("MGF1 digest: "
                + ((MGF1ParameterSpec) actual.getMGFParameters())
                        .getDigestAlgorithm());
        System.out.println("Label hex: "
                + HexFormat.of().formatHex(
                        ((PSource.PSpecified) actual.getPSource())
                                .getValue()));

        byte[] ciphertext = sender.doFinal(message);
        byte[] restored = decrypt(
                pair.getPrivate(), ciphertext, correct);

        System.out.println("Round-trip: "
                + Arrays.equals(message, restored));
        System.out.println("Ciphertext bytes: " + ciphertext.length);

        OAEPParameterSpec wrongMgf = spec(
                "SHA-256", MGF1ParameterSpec.SHA1, "app:v1");
        OAEPParameterSpec wrongLabel = spec(
                "SHA-256", MGF1ParameterSpec.SHA256, "app:v2");
        OAEPParameterSpec wrongDigest = spec(
                "SHA-1", MGF1ParameterSpec.SHA256, "app:v1");

        System.out.println("Wrong MGF1 rejected: "
                + rejected(pair.getPrivate(), ciphertext, wrongMgf));
        System.out.println("Wrong label rejected: "
                + rejected(pair.getPrivate(), ciphertext, wrongLabel));
        System.out.println("Wrong OAEP digest rejected: "
                + rejected(pair.getPrivate(), ciphertext, wrongDigest));

        // SHA-256 hLen = 32; RSA-2048 k = 256.
        int maxMessageBytes = 256 - 2 * 32 - 2;
        System.out.println("Max message bytes: " + maxMessageBytes);

        boolean overLimitRejected;
        try {
            encrypt(pair.getPublic(),
                    new byte[maxMessageBytes + 1], correct);
            overLimitRejected = false;
        } catch (IllegalBlockSizeException expected) {
            overLimitRejected = true;
        }
        System.out.println("191 bytes rejected: " + overLimitRejected);

        Arrays.fill(message, (byte) 0);
        Arrays.fill(restored, (byte) 0);
    }
}
~~~

Run with JDK 17+ using SunJCE/RSA provider supporting these parameters:

~~~bash
javac -encoding UTF-8 RsaOaepSpecDemo.java
java RsaOaepSpecDemo
~~~

Expected stdout (these lines do not depend on the random ciphertext):

~~~text
OAEP digest: SHA-256
MGF: MGF1
MGF1 digest: SHA-256
Label hex: 6170703a7631
Round-trip: true
Ciphertext bytes: 256
Wrong MGF1 rejected: true
Wrong label rejected: true
Wrong OAEP digest rejected: true
Max message bytes: 190
191 bytes rejected: true
~~~

Explanation:

1. **actual.getDigestAlgorithm()** returns SHA-256: verifies the main OAEP hash.
2. **((MGF1ParameterSpec) actual.getMGFParameters()).getDigestAlgorithm()** returns SHA-256: verifies the hash **inside MGF1**, not inferred from the transformation string.
3. **getPSource()** reports the actual label. **6170703a7631** is the hex of UTF-8 bytes for **app:v1**.
4. Public key encrypts, matching private key decrypts with the **same spec**, so `Round-trip = true`.
5. Intentionally changing **MGF1 SHA-256 → SHA-1**, **label app:v1 → app:v2**, or **OAEP SHA-256 → SHA-1** causes decryption to fail. The example catches `BadPaddingException` on invalid OAEP padding.
6. RSA 2048 has a **256-byte** modulus, so ciphertext is **256 bytes**. With SHA-256 `hLen = 32` bytes, max plaintext is **190 bytes**; 191 bytes exceeds the limit for RSA-OAEP under this configuration.

**Technical note:** the program generates a random RSA pair on every run so ciphertext is not fixed; decryption success/failure reflects expected configuration behavior. Different OAEP providers may throw errors or reject parameters at different points during `init`. If a provider does not support a spec, that is an **interoperability issue to investigate**, not a reason to fall back blindly to defaults.

### 6.1 Why Call Cipher.doFinal Instead of Checking Padding Yourself?

**RSAES-OAEP performs structural/label decoding and verification inside the implementation.** Applications call `Cipher.doFinal` to receive plaintext or an error; never parse masks/seeds or check structural bytes yourself and leak error details to clients.

OAEP errors typically manifest as **BadPaddingException** on decryption. Depending on the provider and input, other exceptions such as `InvalidKeyException`, `InvalidAlgorithmParameterException`, or `IllegalBlockSizeException` can occur. On systems exposed to untrusted input:

- Reject invalid ciphertexts generically, avoiding granular errors that could act as an oracle.
- Never try **RSA/ECB/PKCS1Padding** or **RSA/ECB/NoPadding** to "rescue" an invalid OAEP ciphertext.
- Never assume mismatched label bytes can be fixed by trimming or changing charsets after decryption.
- Never print private keys, sensitive raw ciphertexts, or plaintexts to logs just for debugging.
- Enforce resource limits, validate ciphertext format, and verify key permissions prior to decryption.

### 6.2 Why Doesn't the Program Print Ciphertext?

OAEP uses randomness, so ciphertexts for the same M differ across encryptions. Printing a ciphertext as a sample value and telling learners to expect exact bytes would be unreliable. Instead, the example checks **length** and invariant properties.

Additionally, **Arrays.fill()** only zeroes byte arrays managed by your code and does not guarantee clearing copies inside the JVM. Example keys are generated in-memory; real applications need keystores, KMS/HSM, and private-key protection policies.

## 7. Size Limits: RSA-OAEP Is Not for Encrypting Large Files

Per RFC 8017, for RSAES-OAEP:

~~~text
mLen <= k - 2*hLen - 2

mLen = plaintext length (bytes)
k    = RSA modulus length (bytes)
hLen = OAEP hash output length (bytes)
~~~

With OAEP SHA-256, `hLen = 32`:

| RSA Modulus | k (bytes) | Max plaintext with OAEP SHA-256 |
| --- | ---: | ---: |
| 2048-bit | 256 | 190 bytes |
| 3072-bit | 384 | 318 bytes |
| 4096-bit | 512 | 446 bytes |

This is **byte count**, not Java `String` character count. A Unicode string can have a larger UTF-8 byte length than `String.length()`.

**MGF1 digest is a separate parameter**, yet in the length limit formula above, **hLen is the main OAEP hash**, not the output length of the MGF1 hash. Switching MGF1 from SHA-256 to SHA-1 does not shift `k - 2*hLen - 2` to use MGF1's length.

RSA-OAEP is **not meant for arbitrarily splitting a file into independent RSA pieces**. Encrypting many RSA blocks creates heavy overhead and protocol flaws. Instead, use **hybrid encryption**:

~~~text
1. Randomly generate an AES key (DEK).
2. Encrypt file / data with AES-GCM using a unique nonce.
3. Encrypt the small DEK with the recipient's RSA-OAEP public key.
4. Store/send:
   version, keyId, OAEP spec id, wrapped DEK,
   GCM nonce, ciphertext + tag, metadata/AAD per format.
5. Recipient:
   verify version/format and permissions,
   decrypt DEK with RSA-OAEP using exact parameters,
   decrypt + authenticate AES-GCM,
   release plaintext only when tag is valid.
~~~

In many real systems, KMS/HSM provides dedicated **key wrap/unwrap** or envelope encryption operations. When available, prefer vetted cryptographic protocols/libraries rather than inventing complex custom formats. OAEP protects exchanging the AES key; AES-GCM protects the bulk data payload.

**RSA-OAEP is public-key encryption, not a digital signature or sender authentication.** When sender authentication is needed, design digital signatures, MACs, or proper channel authentication. AES-GCM AAD can bind metadata, yet cannot by itself identify the sender if multiple parties share or can create the key.

Source: [RFC 8017 — RSAES-OAEP](https://www.rfc-editor.org/rfc/rfc8017.html#section-7.1).

## 8. Interoperability: Java ↔ Java and Java ↔ Other Languages

### 8.1 What Else Must Be Agreed Upon Beyond the Hash?

When two sides say "OAEP SHA-256", ask explicitly:

1. RSAES-OAEP or another RSA mechanism?
2. Is **OAEP digest** SHA-256 or SHA-1?
3. Is **MGF** MGF1?
4. Is **MGF1 digest** SHA-256, SHA-1, or another value?
5. What are the exact **Label** bytes, or empty `byte[]`?
6. Is the **Public key** X.509 SubjectPublicKeyInfo, PKCS#1 RSA PUBLIC KEY, or another type?
7. Is the **Private key** PKCS#8, PKCS#1, or inside an HSM/keystore?
8. Is **Ciphertext** raw RSA bytes or Base64/hex of those bytes? Basic or URL-safe Base64?
9. What are the **Modulus length** and key ID?
10. On error, how are failures rejected without leaking internal details?

**Key encoding is not OAEP encoding.** OAEP is the scheme encoding a message; X.509/PKCS#8/PEM are key storage/exchange formats; Base64 is text representation of bytes.

### 8.2 Example Concept Mapping Between Two Sides

Suppose Side A is Java and Side B is a service using another crypto library. The contract defines:

~~~text
RSAES-OAEP:
    hashAlgorithm = SHA-256
    mgf = MGF1
    mgf1HashAlgorithm = SHA-256
    label = hex(6170703a7631)

Ciphertext:
    256 raw bytes for RSA-2048
    transferred as Base64 Basic (no line breaks)
~~~

Side A uses:

~~~java
new OAEPParameterSpec(
    "SHA-256",
    "MGF1",
    MGF1ParameterSpec.SHA256,
    new PSource.PSpecified(
        "app:v1".getBytes(StandardCharsets.UTF_8))
);
~~~

Side B must have equivalent parameters: **OAEP hash SHA-256, MGF1(SHA-256), label bytes 6170703a7631**. Side B's exact function calls depend on its library, yet the byte/algorithm semantics must match.

Note: some libraries default to an **empty label** and some do not support custom labels; some libraries configure OAEP hash and MGF1 hash with **two separate options**, while others use internal defaults. Therefore, run **real interoperability tests**, not just doc-level name comparisons.

### 8.3 Why Not Guess MGF1 from the Transformation String?

For example, Java code calling:

~~~java
Cipher.getInstance("RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
~~~

That string **does not explicitly express the MGF1 digest**. In some SunJCE implementations, transformations like this have been known to use **MGF1 SHA-1** when no caller-supplied `OAEPParameterSpec` is given, whereas another provider may use SHA-256 for MGF1. That exact discrepancy produces the bug where "both sides say SHA-256 yet cannot decrypt".

Reliable approach:

- Construct **OAEPParameterSpec** with SHA-256 digest and **MGF1ParameterSpec.SHA256** if that is the contract.
- Pass the same spec to **Cipher.init(...)** for both encrypt/decrypt.
- You can inspect **Cipher.getParameters().getParameterSpec(OAEPParameterSpec.class)** after init to verify what the provider actually adopted, when the provider supports returning parameters.
- Test with a fixed ciphertext generated by the peer and decrypt in both directions; also test mismatched MGF digest and mismatched label.
- If you must interoperate with a legacy system using MGF1 SHA-1, select the legacy parameters **explicitly, with versioning and a migration plan**, rather than letting accidental defaults decide.

### 8.4 Null, Empty, and Text Labels Mean Different Things

In some non-Java APIs, **null** may be interpreted by the library as an **empty label**. However, **in Java**, the clearest way to specify an empty label is **PSource.PSpecified.DEFAULT** or **new PSource.PSpecified(new byte[0])**.

Never pass a literal string `"null"` or `"DEFAULT"` in place of an empty label. If the contract uses label `"app:v1"`, convert exact UTF-8 bytes; do not let Side A use `app:v1` while Side B uses `app:v1` with a trailing newline.

### 8.5 Importing Public/Private Keys Across Formats

Java can use:

~~~java
// Illustrative snippet depending on encodedPublic/encodedPrivate variables.
PublicKey pub = KeyFactory.getInstance("RSA").generatePublic(
    new X509EncodedKeySpec(encodedPublic));

PrivateKey priv = KeyFactory.getInstance("RSA").generatePrivate(
    new PKCS8EncodedKeySpec(encodedPrivate));
~~~

This is an illustrative snippet, not a standalone program; import **java.security.KeyFactory**, **java.security.PublicKey/PrivateKey**, and the corresponding KeySpecs.

**X509EncodedKeySpec** is X.509 SubjectPublicKeyInfo widely supported by Java; **PKCS8EncodedKeySpec** is PKCS#8. Some third-party files use PEM labels like **BEGIN RSA PUBLIC KEY** or **BEGIN RSA PRIVATE KEY** in PKCS#1 structure rather than SubjectPublicKeyInfo/PKCS#8; you cannot blindly feed PKCS#1 DER into `X509EncodedKeySpec` or `PKCS8EncodedKeySpec` and expect it to always work. Safely convert the format or use an appropriate parser.

Never write private key bytes to logs or source code. Public keys must have their origin authenticated (certificates, trust stores, pinning/management) whenever there is any risk an attacker could substitute their own public key.

## 9. OAEP Interoperability Test Matrix

| Case | Expectation |
| --- | --- |
| Matching keypair, SHA-256, MGF1 SHA-256, same label | Decrypts plaintext accurately |
| Matching keypair, OAEP SHA-256, yet MGF1 SHA-1 on receiver | Decryption fails |
| Matching keypair, MGF1 SHA-256, yet OAEP hash SHA-1 on receiver | Decryption fails |
| Matching hashes/MGF1, yet label differs by one byte | Decryption fails |
| Sender uses empty label, receiver uses non-empty label | Decryption fails |
| Same visible label text, yet different charset/Unicode normalization | Decryption may fail due to different bytes |
| Wrong private key | Decryption fails |
| Ciphertext modified or truncated | Decryption fails, plaintext not used |
| 190-byte message, RSA-2048 + OAEP SHA-256 | Within input length limit |
| 191-byte message, RSA-2048 + OAEP SHA-256 | Rejected as over limit |
| RSA-2048, raw ciphertext | 256 bytes long |
| Same plaintext/key/params encrypted twice | Ciphertexts typically differ due to OAEP random seed |
| Public key read with wrong KeySpec | Format conversion or error handling required |
| Receiver algorithm unsupported by provider | Reject or pick supported provider per policy; never auto-downgrade |

### 9.1 Interoperability Tests Should Run in Both Directions

For real systems, do not test only Java encrypting and decrypting itself. You need:

1. **Java encrypt → B decrypt.**
2. **B encrypt → Java decrypt.**
3. Ciphertexts generated with an **empty label** and with the **specified label** (if any).
4. Both **MGF1 SHA-1 and SHA-256** negative cases to verify mismatch detection, while only using legacy settings in production when permitted by contract.
5. Tests verifying key serialization, Base64 decoding, and JSON/HTTP byte transport do not corrupt ciphertext.
6. Tests across older/newer provider versions and documenting supported providers.

Because OAEP ciphertext changes due to the random seed, **never compare raw ciphertexts across two encryptions** to prove compatibility. Verify **decrypted plaintext and error paths**.

### 9.2 Testing Errors Without Creating Oracles

Never return granular responses distinguishing "wrong MGF1", "wrong label", "wrong OAEP digest", or "wrong padding byte" to callers for untrusted ciphertexts. Applications normally return a generic decryption failure; internal logs record appropriate diagnostic detail without leaking keys/plaintexts. Avoid timing or retry behaviors that reveal clues. Only use OAEP in protocols with proper end-to-end protections and rate/permission controls.

## 10. Common Real-World Mistakes

1. **"OAEPWithSHA-256AndMGF1Padding means MGF1 is definitely SHA-256."** Insufficient information; MGF1 digest needs an explicit spec or provider verification.
2. **"Both sides only need the same OAEP digest."** Wrong: MGF algorithm, MGF1 digest, and label bytes must also match.
3. **"OAEPParameterSpec.DEFAULT uses SHA-256."** Wrong: Java 17 defines DEFAULT as SHA-1 for both OAEP and MGF1, plus an empty label.
4. **"MGF1ParameterSpec.SHA256 automatically sets the OAEP digest to SHA-256."** Wrong: that sets only the hash inside MGF1; `mdName` is a separate parameter.
5. **"Labels with identical visible text definitely have the same value."** Wrong: charset, normalization, spaces, and newlines all affect bytes.
6. **"PSource.PSpecified.DEFAULT is a default password."** Wrong: it is an empty label, not a secret.
7. **"Changing the label is a way to authenticate the sender."** Wrong: anyone with the public key and label can encrypt; separate authentication is required.
8. **"You can encrypt a 1 MB file directly with one RSA-OAEP call."** Wrong: plaintext length is bounded by `k - 2hLen - 2`; use hybrid encryption.
9. **"RSA/ECB means splitting payload into multiple RSA blocks like AES-ECB."** Wrong: that model does not apply to RSA.
10. **"RSA-OAEP can replace RSA-PSS digital signatures."** Wrong: encrypting with a public key differs from signing with a private key.
11. **"Base64 ciphertext decoded cleanly, so RSA padding must be right."** Wrong: Base64 only turns text into bytes; RSA-OAEP checks padding/structure against the key and params.
12. **"If the label is wrong, just try an empty label or switch to SHA-1 until it works."** Dangerous: creates downgrade vulnerabilities and breaks protocol boundaries. Configurations must be fixed/allowlisted by version.
13. **"A public key from the sender is trustworthy simply because it parses."** Wrong: key origin must be authenticated to avoid encrypting for an attacker.
14. **"Encrypting with a public key proves the sender holds the private key."** Wrong: public keys are public.
15. **"An RSA-OAEP ciphertext of the right length must be valid."** Wrong: only decryption and OAEP verification validate it.
16. **"A Java-only round-trip is enough to guarantee Python/Go/OpenSSL can decrypt."** Wrong: run cross-language tests with real MGF digests, labels, key formats, and encodings.

## 11. Diagnostic Scenarios

### Scenario A — Java encrypts successfully, another service always reports OAEP decoding error

Java only specified `"RSA/ECB/OAEPWithSHA-256AndMGF1Padding"`, while the peer configured OAEP hash SHA-256 and MGF1 SHA-256. Java's effective defaults may not match the peer's MGF1 hash.

**How to investigate:** read the effective `OAEPParameterSpec` on the Java side, verify Side B's MGF1 digest, label bytes, key pair, and raw ciphertext. Set an explicit spec and test cross-language ciphertexts in both directions.

### Scenario B — Switching the label from empty to "app:v1"

One team switches `PSource.PSpecified.DEFAULT` to label `app:v1`, while the decrypting service still uses empty. All new ciphertexts will fail decryption under the old configuration.

**How to handle:** version the protocol/key record and roll out changes across both sides in a controlled manner. Avoid continuous blind fallbacks; if two versions truly must be supported, the server selects based on allowed metadata and verifies permissions/origin.

### Scenario C — Text label containing Unicode

Side A uses a business name string with Vietnamese diacritics in UTF-8, while Side B uses a visually similar string with a different Unicode normalization. Different label hashes cause OAEP decoding to fail.

**How to handle:** publish the label as **hex/Base64 of the canonical bytes** in the contract and use those exact bytes. If a label is derived from text, specify UTF-8 and an explicit normalization form.

### Scenario D — Encrypting a 2 KB JSON payload with RSA-2048

RSA-OAEP SHA-256 holds at most 190 bytes; a 2 KB payload exceeds the limit.

**How to handle:** generate a random AES key, encrypt the payload with AES-GCM, and encrypt the AES key with RSA-OAEP. Fully define and verify nonce/AAD/tag/version per a hybrid format.

### Scenario E — Partner only supports an empty label

The Java service wants a custom label, whereas the partner's library does not support non-empty OAEP labels. Changing only one side will fail decryption.

**How to handle:** if policy permits, design the protocol with an empty label on both sides and bind context at the payload/AEAD layer instead. Never turn the label into a secret identification mechanism or skip tag checks during hybrid decryption.

## 12. Self-Check Questions

**1. What are the four important fields in OAEPParameterSpec?**

Main OAEP hash, MGF name (usually MGF1), MGF1 parameters including its own hash, and PSource representing the label bytes.

**2. Is SHA-256 OAEP with MGF1 SHA-1 the same as SHA-256 OAEP with MGF1 SHA-256?**

No. Those are two different OAEP parameter sets and cannot decrypt each other.

**3. Just looking at transformation `RSA/ECB/OAEPWithSHA-256AndMGF1Padding`, do you know the MGF1 digest?**

Not portably. You should configure `MGF1ParameterSpec` explicitly and/or read back the effective parameters from the provider.

**4. What does Java 17's `OAEPParameterSpec.DEFAULT` use?**

OAEP hash SHA-1, MGF1 with SHA-1, empty label. That does not mean every transformation uses those same defaults.

**5. What is the hex of UTF-8 label `app:v1`?**

**6170703a7631**. Label bytes must match identically on both sides; adding a space or newline changes them.

**6. Can an OAEP label be used as a password or to prove sender identity?**

No. The label is not a secret, and anyone can use the public key to encrypt.

**7. With RSA-2048 and OAEP SHA-256, what is the plaintext limit?**

**190 bytes**, because k = 256 and hLen = 32: 256 - 64 - 2 = 190.

**8. What if you have 1 MB of data to encrypt for an RSA recipient?**

Use hybrid encryption: AES-GCM encrypts the data, RSA-OAEP encrypts the small AES key, and metadata/nonce/AAD/tag are managed securely.

**9. If the private key, MGF1 digest, or label is wrong, should you try `RSA/ECB/PKCS1Padding` to decrypt?**

No. Reject or handle per allowed protocol versions; never fall back to weak mechanisms.

**10. Why check `Cipher.getParameters()` and run cross-language integration tests?**

Because transformation names and provider defaults may not fully specify parameters; tests verify hash, MGF1, label, key format, and ciphertext encoding across both implementations.

## Conclusion

**RSA-OAEP cannot be configured with just the single word "SHA-256".** When encrypting or decrypting, both sides must agree on **OAEP digest, MGF algorithm, MGF1 digest, label bytes, RSA key, and wire format**. In Java 17+, **OAEPParameterSpec("SHA-256", "MGF1", MGF1ParameterSpec.SHA256, new PSource.PSpecified(labelBytes))** expresses this unambiguously. Call `Cipher.init` with explicit parameters, verify effective parameters, and test two-way interoperability. If ciphertext fails to decrypt, treat it as a contract error to investigate—**never substitute defaults or downgrade security mechanisms**.