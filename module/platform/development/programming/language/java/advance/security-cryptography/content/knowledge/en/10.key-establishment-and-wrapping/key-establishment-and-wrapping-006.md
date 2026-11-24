# 10.6 Cipher.WRAP_MODE, UNWRAP_MODE, and Key Wrapping Algorithms

## Learning Objectives

After this lesson, you will be able to:

1. Explain what **key wrapping** is, distinguishing **Key Encryption Key (KEK)** and **Data Encryption Key (DEK)** in a key-encryption architecture.
2. Understand precisely how to use **Cipher.WRAP_MODE**, **Cipher.UNWRAP_MODE**, **wrap(Key)**, and **unwrap(byte[], String, int)** in the Java Cryptography Architecture (JCA/JCE).
3. Choose the right key wrapping algorithm: **AESWrap (RFC 3394 / AES-KW)**, **AESWrapPad (RFC 5649 / AES-KWP)**, **RSA-OAEP**, or KMS/HSM mechanisms based on goals and deployment constraints.
4. Write Java 17+ code to wrap and unwrap AES keys, verify wrapped-key integrity, and explicitly configure OAEP when using RSA.
5. Understand limitations with non-exportable keys, required metadata, provider compatibility, KEK rotation, common mistakes, and safe error handling.

**Core message:** Key wrapping is the operation of protecting **another cryptographic key** with an appropriate wrapping key/mechanism; it is not simply “Base64-encoding a key.” In Java, the WRAP/UNWRAP modes put **Cipher** into a state dedicated to **Key** objects. Security depends on the **wrapping algorithm, wrapping key, parameters, provider, metadata management, and access permissions**; merely passing the `WRAP_MODE` constant does not make every wrapping mechanism safe.

## 1. What Is Key Wrapping and Why Is It Needed?

Suppose a service stores records using **AES-GCM**. Each record or group of data has a random AES key **DEK** to encrypt content. Storing the DEK in plaintext alongside the ciphertext lets anyone who steals both decrypt the record. The system needs a way to store or transfer the **DEK in a protected state**.

The standard solution is using a **KEK** to wrap the DEK:

~~~text
CREATE AND STORE

Record plaintext
      |
 [AES-GCM encrypt] <--------- DEK (Data Encryption Key)
      |                           |
Ciphertext + tag             [KEY WRAP] <------ KEK
      |                           |
      +---- store record -----> wrappedDEK
                             (not raw DEK)

READ AND DECRYPT

wrappedDEK --------> [KEY UNWRAP] <------ authorized KEK
                           |
                          DEK
                           |
Ciphertext + tag ----> [AES-GCM decrypt + verify tag]
                           |
                   Authenticated plaintext
~~~

The two protection layers serve two distinct roles:

- **DEK:** encrypts content (e.g., AES-GCM), usually randomly generated with a narrow usage scope.
- **KEK:** wraps/unwraps DEKs; typically resides in a **KMS/HSM/keystore** with its own access and rotation policies.

This is the core principle of **envelope encryption**: using efficient symmetric encryption for large data, and a key-wrapping/key-exchange mechanism to protect the small DEK.

**Important:** `wrappedDEK` is still administratively sensitive data, though not equivalent to the raw DEK in a well-designed system. Security comes not from variable names or Base64 encoding, but from the underlying algorithm and KEK access controls.

### 1.1 How Does Key Wrapping Differ from Ordinary Data Encryption?

Data encryption turns **byte[] plaintext → byte[] ciphertext**. Key wrapping takes **Key → byte[] wrappedKey**, and unwrapping takes bytes plus algorithm/key-type info to reconstruct a **Key**.

The underlying cryptographic primitives may be related, yet the **APIs and goals differ**:

| Need | Common mechanism | Input → output |
| --- | --- | --- |
| Encrypt records/images/files | AES-GCM | plaintext byte[] → ciphertext + tag |
| Protect an AES key for storage | AES-KW/AES-KWP or KMS WrapKey | Key DEK + KEK → wrapped key bytes |
| Send an AES key to an RSA public-key holder | RSA-OAEP | Key DEK + public key → key ciphertext |
| Derive keys from a shared secret | HKDF/KDF per specification | keying material → context-separated keys |
| Convert bytes to text | Base64, hex | byte[] ↔ text, **adds no security** |

**Key wrapping is not key derivation** and not key agreement. Key wrapping **transports/stores an existing key** in protected form; ECDH/X25519 is how parties **agree on shared material**, while a KDF turns that material into suitable keys.

## 2. Cipher in Java: Four Modes and How to Call Them

The **javax.crypto.Cipher** class provides four important opmode constants:

| Opmode | Typical working methods | Goal |
| --- | --- | --- |
| **Cipher.ENCRYPT_MODE** | update(...), doFinal(...) | Encrypt byte data |
| **Cipher.DECRYPT_MODE** | update(...), doFinal(...) | Decrypt byte data |
| **Cipher.WRAP_MODE** | **wrap(Key key)** | Wrap a Key object, returning byte[] |
| **Cipher.UNWRAP_MODE** | **unwrap(byte[] wrapped, String algorithm, int keyType)** | Unwrap to reconstruct a Key |

Typical pattern:

~~~java
// Illustrative snippet; variables kek, dek, and wrapped already exist.
Cipher wrapper = Cipher.getInstance("AESWrap");
wrapper.init(Cipher.WRAP_MODE, kek);
byte[] wrapped = wrapper.wrap(dek);

Cipher unwrapper = Cipher.getInstance("AESWrap");
unwrapper.init(Cipher.UNWRAP_MODE, kek);
Key recovered = unwrapper.unwrap(
        wrapped, "AES", Cipher.SECRET_KEY);
~~~

This snippet depends on variables/imports from surrounding context and is **not a standalone program**. A compilable/runnable Java 17 program is in section 6.

### 2.1 What Happens with wrap(Key)?

**Cipher.wrap(Key key)** requires a Key object to be wrapped. The provider uses the configured algorithm, mode, wrapping key, and parameters to produce **byte[]**. In many software providers, this uses the **Key's encoded form** to protect it cryptographically. However, some HSMs/providers can wrap keys in hardware without ever exporting plaintext key bytes to the JVM.

Never assume every Key can be wrapped:

- **key.getEncoded() may return null** if the key is non-exportable or has no supported encoding format.
- **Cipher.wrap(...)** may throw **InvalidKeyException** when wrapping the key is impossible or unsafe; **IllegalBlockSizeException** may occur depending on algorithm and encoded key length.
- A provider might not support wrap/unwrap for a specific algorithm or Key type, even if it supports encrypt/decrypt.
- KEK usage permissions may be restricted inside an HSM/KMS (wrap-only, unwrap-only, or limited to a specific key type).

**WRAP_MODE does not bypass private-key protection policies or HSM extractability rules.**

### 2.2 unwrap(...) Cannot Take Only a Byte Array

Method signature:

~~~java
Key unwrap(byte[] wrappedKey,
           String wrappedKeyAlgorithm,
           int wrappedKeyType)
~~~

Meaning of the last two arguments:

- **wrappedKeyAlgorithm:** algorithm name of the **recovered key**, such as **"AES"**, **"HmacSHA256"**, or **"RSA"**. This is **not** the wrapping algorithm name `"AESWrap"` or `"RSA/ECB/OAEPPadding"`.
- **wrappedKeyType:** one of the three constants **Cipher.SECRET_KEY**, **Cipher.PUBLIC_KEY**, or **Cipher.PRIVATE_KEY** so the provider knows which Key type to reconstruct.

Correct example:

~~~java
Key dataKey = unwrapper.unwrap(
        wrappedBytes, "AES", Cipher.SECRET_KEY);
~~~

API-semantically incorrect example:

~~~java
// Wrong: AESWrap is the WRAPPING algorithm, not the DEK's algorithm.
Key dataKey = unwrapper.unwrap(
        wrappedBytes, "AESWrap", Cipher.SECRET_KEY);
~~~

Never choose the algorithm/key type from untrusted strings. **The algorithm name and key type passed to unwrap are not authenticated by wrapping in every format.** With many providers, unwrapped key bytes get tagged with whatever algorithm label the caller supplies; you must validate schema, key length, and key purpose.

### 2.3 Cipher unwrap Returns Key, Not Necessarily SecretKeySpec

The return type is declared as **java.security.Key**. After checking the right type, the application can use it as SecretKey, PublicKey, or PrivateKey if the provider returns the matching type.

~~~java
Key recovered = unwrapper.unwrap(
        wrapped, "AES", Cipher.SECRET_KEY);
if (!(recovered instanceof javax.crypto.SecretKey)) {
    throw new IllegalStateException("Unexpected key type");
}
javax.crypto.SecretKey dek = (javax.crypto.SecretKey) recovered;
~~~

The snippet above is illustrative and assumes `unwrapper` and `wrapped` exist.

**Do not call getEncoded() just to reuse a key if the provider can operate directly on the Key object.** For keys in an HSM, encoded bytes may never appear. To protect data, it is better to pass the Key to a valid Cipher and limit key exposure.

## 3. Important Key Wrapping Algorithms

### 3.1 AESWrap / AES-KW (RFC 3394, NIST SP 800-38F)

**AESWrap** is the Java algorithm name for **AES Key Wrap (AES-KW)** per RFC 3394. It uses an AES key as a **KEK** to protect another key's bytes, with structural integrity checking built into the algorithm.

Typical compatible example:

~~~text
KEK:       128- or 256-bit AES key
DEK:       128-bit AES key (16 bytes)
Algorithm: AESWrap
wrapped:   24 bytes = 16-byte DEK + 8-byte overhead
~~~

With **RFC 3394 AES-KW**, input data must be at least **16 bytes** long and a multiple of **8 bytes** (for the standard algorithm). Output is **8 bytes** longer than input; e.g., 16 bytes becomes 24 bytes, 32 bytes becomes 40 bytes.

The mechanism performs an **integrity check** via the RFC 3394 check value; an attacker without the KEK can hardly modify a wrapped key and have unwrap accept it. Nevertheless:

- AES-KW is **not** an AEAD mechanism with arbitrary AAD like AES-GCM.
- It **does not automatically bind** tenant ID, key ID, expiration, or external metadata fields.
- Never call the 8-byte overhead a **128-bit GCM tag**; their properties and formats differ.
- It does not authenticate the sender's identity or prove the key is authorized for any business operation.

Oracle Java SE 17 lists **AESWrap** corresponding to RFC 3394 AES-KW; the SunJCE provider supports **AESWrap**. Depending on the provider, you can use transformation **"AESWrap"** or equivalent formatted names like **"AES/KW/NoPadding"** when supported. Verify actual algorithm names and compatibility rather than assuming aliases behave identically across all providers.

### 3.2 AESWrapPad / AES-KWP (RFC 5649)

**AES-KWP** extends AES-KW to handle key data whose **length is not a multiple of 8 bytes** or is shorter than AES-KW's range, using a dedicated padding/integrity construction.

The standard Java name is **AESWrapPad** per RFC 5649 and NIST SP 800-38F. Never take a short `byte[]` and manually pad with zeros to “fit AESWrap”: the unwrapping side needs the exact original normalized length, and homegrown padding can break security/protocol properties.

**Never mix AESWrap and AESWrapPad** just because both start with AES. They are two different algorithms with different wrapped-byte structures.

Java includes the standard name AESWrapPad, yet **support by the specific provider in your deployment environment must be checked**. Never infer from a provider having AESWrap that AESWrapPad also works. The runnable example below uses AESWrap, which is documented for SunJCE.

### 3.3 RSA-OAEP Using a Public Key to Wrap a Secret Key

If the sender only has the recipient's **RSA public key**, **RSA-OAEP** can be used to wrap a small AES DEK; the recipient uses the private key to unwrap it.

~~~text
Sender                                Recipient
Public RSA key                       Private RSA key
     |                                     |
WRAP_MODE + RSA-OAEP                  UNWRAP_MODE + RSA-OAEP
     |                                     |
wrap(AES DEK)                         unwrap(bytes, "AES", SECRET_KEY)
     |                                     |
wrapped DEK ----------- send ----------> AES DEK
~~~

OAEP configuration must be explicitly agreed upon:

- **OAEP digest** (e.g., SHA-256).
- **MGF** (typically MGF1).
- **MGF1 digest** (e.g., SHA-256).
- **Label bytes** (e.g., empty label or UTF-8 of `"key:v1"`).
- Matching RSA key pair and ciphertext encoding.

In Java 17, you can use:

~~~java
OAEPParameterSpec spec = new OAEPParameterSpec(
        "SHA-256",
        "MGF1",
        MGF1ParameterSpec.SHA256,
        new PSource.PSpecified(
                "key:v1".getBytes(StandardCharsets.UTF_8))
);
~~~

This is an illustrative configuration snippet, not a standalone program. **Do not infer the MGF1 digest from a transformation name containing SHA-256**: defaults vary across providers. Pass the exact same **OAEPParameterSpec** to **Cipher.init** on both sides.

With RSA-2048, the wrap result is typically **256 bytes**; with OAEP SHA-256, the maximum plaintext is **190 bytes** (k - 2hLen - 2), enough for a 16/32-byte AES key but not for encrypting an entire file. RSA-OAEP is randomized, so wrapped bytes differ each time you wrap the same DEK.

**RSA-OAEP does not authenticate the sender**: anyone knowing the recipient's public key can produce a new ciphertext. If origin proof is needed, use a separate digital signature or protocol authentication mechanism.

### 3.4 Can AES-GCM Encrypt Key Bytes?

Cryptographically, **AES-GCM with a unique nonce and AAD** can protect small secret bytes, including encoded keys, when used within a properly designed protocol.

However, **do not assume every provider supports Cipher.wrap when Cipher is configured as AES/GCM/NoPadding**; wrap/unwrap support depends on each CipherSpi/provider. If using AES-GCM to protect key bytes, you must manage **nonce, tag, AAD**, obey the **unique nonce per KEK** rule, and frame metadata into the output format. For ordinary key wrapping, AES-KW/KWP or a dedicated key-wrapping service avoids unnecessary custom protocol design.

**Never use AES/ECB/NoPadding, AES/CBC/PKCS5Padding, or ad-hoc XOR to wrap keys yourself** and assume confidentiality and integrity match AES-KW. Plain CBC provides no integrity authentication; ECB leaks structure. These algorithms do not become safe key wrappers simply by passing WRAP_MODE.

## 4. Comparing Algorithms by Key Type and Constraints

| Algorithm | Wrapping key (KEK) | Suitable targets | Key conditions | Integrity capability |
| --- | --- | --- | --- | --- |
| **AESWrap / AES-KW** | Symmetric AES | Encoded secret key bytes of valid length | At least 16 bytes, multiple of 8 | Checked per AES-KW standard |
| **AESWrapPad / AES-KWP** | Symmetric AES | Encoded key bytes of flexible length | Provider must support standard KWP | Checked per AES-KWP standard |
| **RSA-OAEP** | Recipient RSA public key | Small DEK; unwrapped with matching private key | OAEP hash, MGF1 digest, label, modulus limit | Checks OAEP structure on decrypt; does not authenticate sender |
| **KMS/HSM WrapKey** | Internal KMS/HSM key per policy | Keys managed by key infrastructure | System API/policy/key handle, permissions, and audit | Per service's algorithm and guarantees |
| **AES-GCM on encoded key bytes** | Symmetric AES | Key bytes inside a properly designed custom protocol | Unique nonce, AAD, tag, framing | Provides AEAD when tag verification succeeds |

**There is no “one best wrapping algorithm for all key types.”** Consider trust model, compatibility requirements, key exportability, size limits, and which metadata must be authenticated.

### 4.1 Why Doesn't the Name AESWrap Explain That the DEK Is AES?

**"AESWrap"** is the cipher name used to protect key bytes. The wrapped DEK could be another secret key type if its byte representation and algorithm/length fit the wrapping mechanism.

Upon unwrapping, Java needs to know the algorithm name and Key type to reconstruct:

~~~text
Wrapping algorithm: AESWrap
Wrapping key:       KEK is AES
Wrapped key type:   Cipher.SECRET_KEY
Wrapped algorithm:  "AES" or "HmacSHA256" per contract
~~~

Never confuse the wrapping algorithm with **wrappedKeyAlgorithm** in the unwrap signature.

## 5. SecretKey, PublicKey, PrivateKey, and Encodings

JCA has the **java.security.Key** interface and its subinterfaces:

- **javax.crypto.SecretKey:** symmetric key; encoded format is typically **RAW** when exportable.
- **java.security.PublicKey:** public key; common encoded format is **X.509 SubjectPublicKeyInfo**.
- **java.security.PrivateKey:** asymmetric private key; common encoded format is **PKCS#8** if export is allowed.

Type constants for unwrapping:

~~~java
Cipher.SECRET_KEY
Cipher.PUBLIC_KEY
Cipher.PRIVATE_KEY
~~~

These are **Key type constants**, not cryptographic algorithms or mode values. Passing the wrong Key type or algorithm name can make unwrap fail, or construct a key object unsuitable for subsequent use.

### 5.1 getAlgorithm(), getFormat(), getEncoded()

**Key.getAlgorithm()** gives the algorithm name (e.g., `"AES"`). **Key.getFormat()** gives the encoded key format when supported. **Key.getEncoded()** returns the encoded `byte[]` or possibly **null**.

For an exportable software secret key, you may see:

~~~text
key.getAlgorithm(): AES
key.getFormat():    RAW
key.getEncoded():   [16, 24, or 32 bytes]
~~~

These bytes are **secret**, not public metadata. Never write them to logs, metrics, config files, or responses. That they can be returned in tests **does not mean you should always export them** in production.

### 5.2 Non-Exportable HSM/KMS Keys

An HSM may store key material under a key handle and refuse `getEncoded()`. A software Cipher cannot wrap a key whose bytes it cannot read; conversely, the HSM may provide hardware-internal wrapping according to policy.

The Javadoc for **Cipher.wrap(Key)** documents `InvalidKeyException` when wrapping is impossible or unsafe—for example, passing a hardware-protected key to a software-only cipher.

**Never attempt to bypass extractability boundaries** via reflection, in-memory dumps, or pulling private keys into the JVM just to “make an example run.” Use the provider/HSM wrap/unwrap API or official KMS workflows, with proper role and key-usage controls.

### 5.3 Should You Wrap Private Keys?

There are valid cases for **private key backup/escrow/migration** that are permitted and require strict protection. However, private keys are generally recommended to **stay non-exportable** inside an HSM when the security model requires it.

If a private key is genuinely permitted to be exported, the format such as PKCS#8, wrapping algorithm, KEK management, permissions, and auditing must be clearly specified; never assume calling **wrap(privateKey)** will succeed across every provider. For non-exportable private keys, the right solution is usually key handles and internal HSM protection features.

## 6. Complete Java 17+ Program: AESWrap, Tamper Detection, and RSA-OAEP

The program below demonstrates:

1. Generating an **AES-128 KEK** and **AES-128 DEK** in the same run using KeyGenerator.
2. Wrapping the DEK with **AESWrap**, then unwrapping with the same KEK.
3. Flipping one bit of the wrapped bytes to verify **AESWrap integrity**.
4. Generating an RSA-2048 keypair and wrapping the same DEK with the public key using **RSA-OAEP SHA-256/MGF1-SHA-256/label "key:v1"**.
5. Unwrapping with the private key and intentionally passing a different label to prove configuration must match.

This is a **standalone** program using APIs available since Java 17 and SunJCE/SunRsaSign on compatible JDKs. The demo generates random keys in one process; real applications use KEKs/DEKs provisioned and managed by an appropriate key management system.

Create **KeyWrapDemo.java** (UTF-8):

~~~java
import java.security.*;
import java.security.spec.MGF1ParameterSpec;
import java.util.Arrays;
import javax.crypto.*;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;

public class KeyWrapDemo {
    private static OAEPParameterSpec oaep(String label) {
        return new OAEPParameterSpec(
            "SHA-256", "MGF1", MGF1ParameterSpec.SHA256,
            new PSource.PSpecified(
                label.getBytes(java.nio.charset.StandardCharsets.UTF_8)));
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128);
        SecretKey kek = generator.generateKey();
        SecretKey dek = generator.generateKey();

        Cipher aesWrap = Cipher.getInstance("AESWrap");
        aesWrap.init(Cipher.WRAP_MODE, kek);
        byte[] wrappedAes = aesWrap.wrap(dek);

        Cipher aesUnwrap = Cipher.getInstance("AESWrap");
        aesUnwrap.init(Cipher.UNWRAP_MODE, kek);
        Key restoredAes = aesUnwrap.unwrap(
            wrappedAes, "AES", Cipher.SECRET_KEY);

        System.out.println("AESWrap bytes: " + wrappedAes.length);
        System.out.println("AES key restored: "
            + Arrays.equals(dek.getEncoded(), restoredAes.getEncoded()));

        byte[] tampered = wrappedAes.clone();
        tampered[tampered.length - 1] ^= 1;
        boolean tamperRejected;
        try {
            aesUnwrap.unwrap(tampered, "AES", Cipher.SECRET_KEY);
            tamperRejected = false;
        } catch (GeneralSecurityException expected) {
            tamperRejected = true;
        }
        System.out.println("AESWrap tamper rejected: " + tamperRejected);

        KeyPairGenerator rsaGenerator = KeyPairGenerator.getInstance("RSA");
        rsaGenerator.initialize(2048);
        KeyPair recipient = rsaGenerator.generateKeyPair();

        Cipher rsaWrap = Cipher.getInstance("RSA/ECB/OAEPPadding");
        rsaWrap.init(Cipher.WRAP_MODE, recipient.getPublic(), oaep("key:v1"));
        byte[] wrappedRsa = rsaWrap.wrap(dek);

        Cipher rsaUnwrap = Cipher.getInstance("RSA/ECB/OAEPPadding");
        rsaUnwrap.init(Cipher.UNWRAP_MODE, recipient.getPrivate(),
            oaep("key:v1"));
        Key restoredRsa = rsaUnwrap.unwrap(
            wrappedRsa, "AES", Cipher.SECRET_KEY);

        System.out.println("RSA-OAEP wrapped bytes: " + wrappedRsa.length);
        System.out.println("RSA-OAEP restored: "
            + Arrays.equals(dek.getEncoded(), restoredRsa.getEncoded()));

        Cipher wrongLabel = Cipher.getInstance("RSA/ECB/OAEPPadding");
        wrongLabel.init(Cipher.UNWRAP_MODE, recipient.getPrivate(),
            oaep("key:v2"));
        boolean wrongLabelRejected;
        try {
            wrongLabel.unwrap(wrappedRsa, "AES", Cipher.SECRET_KEY);
            wrongLabelRejected = false;
        } catch (GeneralSecurityException expected) {
            wrongLabelRejected = true;
        }
        System.out.println("RSA-OAEP wrong label rejected: "
            + wrongLabelRejected);
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 KeyWrapDemo.java
java KeyWrapDemo
~~~

Expected stdout on a JDK supporting the transformations above:

~~~text
AESWrap bytes: 24
AES key restored: true
AESWrap tamper rejected: true
RSA-OAEP wrapped bytes: 256
RSA-OAEP restored: true
RSA-OAEP wrong label rejected: true
~~~

**Basis of the numbers:**

- 128-bit AES DEK = **16 bytes**. With RFC 3394 AES-KW, the wrapped key is **24 bytes**, i.e., 16 + 8.
- 2048-bit RSA modulus = **256 bytes**. Wrapped RSA-OAEP output is **256 bytes**.
- Both restoration checks use **getEncoded() in the demo only** for software AES keys generated by KeyGenerator. In production, you may have to work directly with Key objects without exporting raw bytes.
- Flipping a byte in the AES-KW wrapped output causes the integrity check to fail with overwhelming probability; the demo detects this via exception.
- Matching OAEP SHA-256/MGF1-SHA-256 but passing **label `"key:v2"`** instead of **`"key:v1"`** causes unwrapping to fail.

Because the AES keys and RSA keypair are generated randomly on each run, the raw wrapped bytes differ each time. The example only prints **lengths and pass/fail booleans**, never raw keys, private keys, ciphertexts, or tags.

**Demo limitations:** This is a local functional check with no KMS, transport protocol, or real access control; catching `GeneralSecurityException` demonstrates the rejection path on failed unwrap, and exception messages must never be returned to leak cryptographic details to a client.

### 6.1 Why Catch GeneralSecurityException in the Demo?

**Cipher.wrap(...)** can throw `InvalidKeyException` or `IllegalBlockSizeException`; **Cipher.unwrap(...)** typically reports `InvalidKeyException` or `NoSuchAlgorithmException` per Javadoc. Failed unwrapping does not necessarily throw the exact same exception class across all providers and algorithms.

Catching **GeneralSecurityException** at the demo boundary captures declared cryptographic failures and treats failed unwrap as a rejection state. In a real service, you can categorize internally by valid cause (unauthorized key, bad format, unsupported algorithm, failed integrity check), while **returning a generic error** to untrusted callers and avoiding an oracle that leaks excessive detail.

Note that **UnsupportedOperationException** is a runtime exception if a provider does not implement wrap/unwrap. This is an API-support/deployment-configuration issue, not a signal to fall back to unsafe encryption.

### 6.2 What Does Recovering Identical Key Bytes Prove?

In the demo, **AES key restored: true** shows that the encoded key `byte[]` matches the original DEK. This is a **round-trip test**; it does not yet prove:

- the KEK is protected in a real environment;
- the wrapped blob belongs to the right tenant/record;
- the sender was authorized to create the wrapped key;
- the wrapped key was not replayed or swapped across resources;
- data encrypted under the DEK passed AEAD tag verification.

To prove a system is sound, you need **key recovery tests** as well as **policy, metadata binding, key lifecycle, and data encryption tests**.

## 7. Key Wrapping, Metadata, and Envelope Encryption Design

### 7.1 Record Format Must Be Explicit

An application encrypted record usually needs more than wrapped bytes. For example, an application-defined format:

~~~text
envelopeVersion:   1
tenantId:          tenant-A
recordId:          report-2026-07
wrappingAlg:       AESWrap
kekId:             kms-key/finance-v3
wrappedDek:        Base64( AES-KW(KEK, DEK) )
dataAlg:           AES/GCM/NoPadding
nonce:             Base64(12-byte nonce)
dataCiphertext:    Base64(ciphertext || GCM tag)
keyPurpose:        record-encryption
~~~

This is a **structural example**, not an audited standard protocol. Each field has a role:

- **envelopeVersion:** selects the schema and policy-allowed algorithms.
- **tenantId/recordId/keyPurpose:** binds permissions, data owner, and key usage type.
- **wrappingAlg:** identifies how to unwrap `wrappedDEK`.
- **kekId:** references the KEK in KMS/HSM; does not contain the raw KEK.
- **wrappedDek:** binary wrapped key Base64-encoded for JSON/text; Base64 adds no cryptographic protection.
- **dataAlg/nonce/dataCiphertext:** describes the data encrypted by the DEK.

**AES-KW has no AAD**, so metadata such as `tenantId`, `recordId`, and `keyPurpose` **are not automatically verified by AESWrap**. You must bind metadata in an authenticated protocol (such as AES-GCM AAD covering data and matching metadata, or a signed/MACed record under a trust model), enforce authorization, and tie `wrappedDEK` to the right context. Never accept client-modifiable metadata and merely check “unwrap succeeded.”

### 7.2 Protected Data Read Flow

A sound workflow:

1. **Authenticate the request** and check that the caller is authorized to read the specific record.
2. Parse and validate **envelopeVersion, allowed algorithms, sizes, key ID**, metadata fields, and tenant/record relationship.
3. Look up the KEK by key ID in **KMS/HSM** per permissions; never hand the KEK to arbitrary clients.
4. **Unwrap the DEK** with the exact algorithm and parameters. Reject if the integrity check fails.
5. Verify Key type, algorithm, DEK length, and **key usage**; never blindly trust an algorithm label from the payload.
6. Decrypt data with the DEK using **AES-GCM**, supplying the right nonce/AAD and verifying the tag; never use plaintext if verification fails.
7. Only after all checks pass, deliver plaintext to authorized business logic.
8. Record minimal audit logs (key ID, record ID, outcome, request ID); never log raw KEK/DEK or plaintext.

Successful unwrapping **does not guarantee `dataCiphertext` payload validity**: data still must be decrypted and authenticated. Conversely, a valid GCM payload in one context **does not grant access** to another caller.

### 7.3 Using RSA-OAEP Instead of AESWrap in an Envelope

With RSA-OAEP:

~~~text
wrappingAlg:       RSA-OAEP
rsaRecipientKeyId: recipient-key-2026
oaepDigest:        SHA-256
mgf:               MGF1
mgfDigest:         SHA-256
oaepLabel:         Base64(UTF8("key:v1"))
wrappedDek:        Base64(RSAES-OAEP(publicKey, DEK))
~~~

The recipient selects the **authorized private key** and the exact same parameter set. Never let unauthenticated fields force the server to downgrade algorithms or try keys belonging to other tenants. If fields can be modified, the application must check/block them at the policy layer or bind them into the record/protocol authentication mechanism.

**RSA-OAEP does not prove key origin**: anyone holding the public key can create a wrapped key. To know who sent it, you need digital signatures or authenticated transport and proper authorization policies.

## 8. KEK and DEK Lifecycles: Rotation, Rewrapping, and Access Control

### 8.1 Changing a KEK Does Not Necessarily Require Re-Encrypting Large Files

If the DEK remains valid and uncompromised, the **KEK** can be rotated like this:

~~~text
wrappedDEK_old --[UNWRAP with KEK_old]--> DEK
DEK            --[WRAP with KEK_new]----> wrappedDEK_new
~~~

These operations must be protected inside a KMS/HSM or trusted environment, minimizing the time the DEK exists in memory. Update **wrappedDEK + kekId/version** consistently and ensure a recovery plan if rotation is interrupted.

**Rewrapping does not create a new DEK** and does not re-encrypt `dataCiphertext`. It only changes how the same DEK is protected. If the DEK itself was compromised, rotating only the KEK will not make data previously encrypted under that DEK confidential again: you must evaluate issuing a new DEK, re-encrypting data, revoking access, and assessing blast radius.

### 8.2 “Wrap” and “Unwrap” Permissions Should Be Separated

A system may grant a writer service permission to create wrapped DEKs, while a reader service has permission to unwrap for decryption. Not every process that stores ciphertext needs permission to unwrap every record.

KMS/HSM systems typically provide:

- Key IDs/aliases and versions.
- Separate encrypt/wrap/decrypt/unwrap permissions by role and policy.
- Auditing of key operations.
- Rotation, disabling, revocation, and backup/restore.
- Keeping root/KEKs inside hardware boundaries.

**Do not confuse “application is allowed to wrap” with “allowed to unwrap.”** Over-privileged permissions increase impact when a service is compromised.

### 8.3 Expiration and Recovery Policies

Never delete an old KEK before all wrapped DEKs depending on it have been rewrapped or are no longer needed for decryption, unless a stronger security revocation reason overrides it. Track key versions, rotation state, migrated data, and recovery policies.

At the same time, never keep an old KEK active indefinitely for compatibility if the key may have been compromised. Transition plans must balance recoverability with revocation and security requirements.

## 9. Right Algorithm, Still Insecure Designs

### 9.1 Mistake: Storing the KEK Next to the Wrapped DEK

If the database holds `wrappedDEK` and the same system lets any process retrieve the plaintext KEK, protection value drops sharply. **Separating privilege domains** between storage and the key service is central to envelope encryption.

You may store the KMS key ID alongside the record; **a key ID is normally not secret**. Yet the raw KEK must never be stored or logged at the same access level as the data it protects.

### 9.2 Mistake: Using the Same KEK for All Tenants and Purposes

A single shared KEK widens the blast radius of a compromise. Partition by **tenant/application/purpose** where appropriate, combined with policies preventing one client from unwrapping another client's DEK. Separating KEKs also enables independent rotation and clearer auditing.

**Per-tenant keys do not replace authorization**; you must still verify whether the user has permission on the record.

### 9.3 Mistake: Not Checking “Is the Returned Key Valid for This Purpose?”

**Cipher.unwrap(..., "AES", SECRET_KEY)** lets the provider build a Key with algorithm `"AES"`, but it does not attest the record creator's intended purpose. If data could be injected under another context, enforce key ID/version, key type, length, tenant, purpose, and explicit policies.

For example, an AES-128 DEK authorized to encrypt internal records does not mean the service is permitted to use it to encrypt payloads belonging to another tenant.

### 9.4 Mistake: Treating Wrapped-Key Integrity as Integrity for Everything

AES-KW checks the integrity of **wrapped key bytes** per its scheme. It knows nothing about usernames, file contents, access permissions, original records, or timestamps unless those are protected by another mechanism.

Distinguish three layers:

1. **Key wrapping integrity:** `wrappedDEK` unwraps validly under the KEK.
2. **Payload integrity:** data ciphertext is authenticated with an appropriate AES-GCM tag/MAC.
3. **Authorization/business integrity:** right tenant, right user, right operation, and no replay/record swapping.

All three are needed when system requirements call for them.

### 9.5 Mistake: Silently Falling Back to Weaker Algorithms

If unwrapping with AESWrap fails, never try arbitrary transformations like `AES/ECB/NoPadding` or `RSA/ECB/PKCS1Padding` hoping to recover a “readable” Key. In a versioned protocol, the server accepts only the **algorithms and parameters permitted for that version**, rejecting anything else.

### 9.6 Mistake: Treating Wrapping as a Substitute for Sender Authentication

An RSA public key is public. RSA-OAEP lets you send a secret wrapped key to the private-key holder, yet **anyone with the public key** can create a `wrappedDEK`. If the recipient must be certain “Alice created this key,” you need a digital signature, a MAC with a shared key, mTLS, or independent protocol authentication.

## 10. Errors and Exceptions to Handle

| Error / situation | Common symptom | How to handle |
| --- | --- | --- |
| Calling wrap on Cipher not initialized in WRAP_MODE | IllegalStateException | Fix Cipher state; do not proceed |
| Provider does not support wrap | UnsupportedOperationException or transformation unavailable | Verify provider capabilities; never fall back weakly |
| Non-exportable or incompatible key | InvalidKeyException during wrap | Use compatible provider/HSM; never bypass extractability |
| Key bytes violate AES-KW size limits | Error on wrap or init depending on provider | Choose standard KWP/system if supported |
| Wrong/tampered wrapped bytes or wrong KEK | Unwrap fails (usually InvalidKeyException) | Reject; never use any key |
| Wrong RSA private key/OAEP digest/MGF1 digest/label | Unwrap invalid | Reject; check agreed config and key ID |
| Unsupported `wrappedKeyAlgorithm` | NoSuchAlgorithmException or provider error | Enforce algorithm allowlist; never trust arbitrary text |
| Wrong `wrappedKeyType` | Key construction error or unusable key type | Match against schema; never brute-force all types |
| Missing key ID/version | Policy/KMS error | Reject cleanly; audit minimal metadata |
| Unwrap succeeds but data GCM tag is invalid | AEADBadTagException on payload decrypt | Never release plaintext; investigate per policy |

**Never expose provider exception messages as a public API.** Granular errors distinguishing padding, key length, and key validity can create an oracle useful to adversaries. Return generic error codes to clients and log controlled internal diagnostics without logging raw keys or secret payloads.

In multi-threaded systems, **Cipher is stateful and must not be shared concurrently across requests**. Initialize per operation or manage instances without shared mutable state. Never reuse a Cipher initialized in `WRAP_MODE` to call `unwrap`; re-initialize in `UNWRAP_MODE` with the right key and parameters.

## 11. Secure Implementation Checklist

Before deploying key wrapping to production, verify:

- [ ] Clearly define **KEK/DEK**, algorithm, and purpose for each key.
- [ ] Generate keys via **SecureRandom/KeyGenerator** or a secure KMS/HSM; never use a plaintext password directly as a KEK.
- [ ] Select **AESWrap**, **AESWrapPad**, **RSA-OAEP**, or KMS/HSM services per specification; never invent custom key wrapping.
- [ ] Verify the **actual provider** supports the intended transformation, mode, and Key type.
- [ ] For AES-KW, check encoded key bytes meet size rules; for KWP, verify standard/provider support.
- [ ] For RSA-OAEP, explicitly configure **OAEP hash, MGF1 digest, and label** identically on both sides.
- [ ] For HSMs, respect **non-exportable** keys, wrap/unwrap permissions, and key handles.
- [ ] Specify **algorithm/key type/key ID/version/encoding** in the protocol and enforce an allowlist.
- [ ] Never log raw KEKs, DEKs, private keys, plaintexts, or secret buffers.
- [ ] Never treat Base64/hex as a cryptographic protection layer.
- [ ] Metadata and access permissions must be **checked/bound to context**; prevent wrapped-key swapping across tenants/records.
- [ ] Only use a DEK to decrypt data after valid unwrapping, successful AEAD payload authentication, and confirmed authorization.
- [ ] Maintain plans for **KEK rotation / DEK rotation / backup / recovery / revocation**.
- [ ] Test corrupted wrapped bytes, wrong KEK, wrong key type, wrong algorithm/label, unsupported provider, and KMS errors.
- [ ] Monitor errors, rate-limit requests, enforce least privilege, and never build algorithm-downgrade fallback logic.

### 11.1 Minimum Test Matrix

| Test | Expected result |
| --- | --- |
| AESWrap: right KEK, 16-byte AES-128 DEK | wrap → unwrap recovers exact Key |
| AESWrap: flip one bit in wrapped bytes | Integrity check fails |
| AESWrap: switch to a different KEK | Unwrap fails |
| AESWrap: invalid input key encoding length | Reject or use standard KWP if policy allows |
| AESWrapPad: unsupported provider | Caught at capability check; no silent fallback |
| RSA-OAEP: matching private key/hash/MGF1/label | DEK unwraps successfully |
| RSA-OAEP: wrong private key or label | Unwrap fails |
| Send raw wrapped bytes via Base64 then decode | Preserves bytes, adds no security |
| Confuse `wrappedKeyAlgorithm` with wrapping algorithm | Mismatch caught by schema/key validation |
| Pass non-exportable key to software-only provider | Rejected; use hardware wrapping if permitted |
| Swap `wrappedDEK` from another tenant | Rejected via authorization/context binding |
| Unwrap succeeds but payload GCM tag is invalid | Plaintext rejected |
| KEK rotation | DEK rewrapped; old data decrypts under new policy |

**Do not measure only “unwrap returns a Key.”** A sound test suite verifies Key type, length, permissions, metadata, and error handling.

## 12. Self-Check Questions

**Q1.** How does `WRAP_MODE` differ from `ENCRYPT_MODE`?

**Answer:** `WRAP_MODE` is for **Cipher.wrap(Key)** to protect Key objects and return `byte[]`; `ENCRYPT_MODE` is for encrypting data bytes via `doFinal`/`update`. Choosing `WRAP_MODE` does not automatically guarantee a secure algorithm.

**Q2.** What information does `UNWRAP_MODE` require?

**Answer:** The Cipher must be initialized with the right key/params; `unwrap` takes wrapped bytes, the **recovered key's algorithm name**, and the **Key type (`SECRET_KEY`/`PUBLIC_KEY`/`PRIVATE_KEY`)**.

**Q3.** Is a wrapped DEK the encrypted original data?

**Answer:** No. It is the **protected form of the DEK key**, distinct from the ciphertext of the record/file encrypted with that DEK.

**Q4.** Why does wrapping AES-128 with `AESWrap` usually produce 24 bytes?

**Answer:** An AES-128 key is 16 bytes; RFC 3394 AES-KW adds an 8-byte integrity overhead when wrapping.

**Q5.** When should `AESWrapPad` be used?

**Answer:** When wrapping key bytes that do not satisfy AES-KW length requirements, **provided the provider supports AES-KWP and both sides agree on the exact algorithm**.

**Q6.** Is `Key.getEncoded()` returning `null` a bug to fix by forcefully extracting the secret?

**Answer:** No. It can be a protective feature of an HSM/provider. Use authorized hardware or KMS wrap/unwrap APIs instead.

**Q7.** Which keys does RSA-OAEP use for wrapping and unwrapping?

**Answer:** Wrap with the recipient's **public key**; unwrap with the corresponding **private key**, using matching OAEP digest/MGF1 digest/label.

**Q8.** Does an RSA-OAEP ciphertext wrapping an AES DEK prove Alice sent the DEK?

**Answer:** No. Public keys may be known to many parties; origin authentication must be handled separately.

**Q9.** If unwrapping the DEK succeeds, can you skip verifying the data's AES-GCM tag?

**Answer:** No. Unwrapping protects the DEK, while payload integrity must still be authenticated at the data-encryption layer.

**Q10.** Why doesn't `AESWrap` automatically protect `tenantId` in a JSON envelope?

**Answer:** AES-KW has no arbitrary AAD. Metadata must be authenticated at the protocol/record layer and checked by authorization.

**Q11.** Does rewrapping a DEK during KEK rotation require re-encrypting the entire data file?

**Answer:** Not necessarily, if the DEK remains safe and the design allows it: unwrap with the old KEK and rewrap with the new KEK. If the **DEK was compromised**, you may need to issue a new DEK and re-encrypt the data.

**Q12.** If `AESWrap` unwrap throws an error, should you try `AES/ECB/NoPadding` to get a Key?

**Answer:** No. Reject and diagnose according to permitted versions/algorithms; never downgrade.

## 13. Standard Reference Documentation

- [Oracle Java SE 17 — javax.crypto.Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): WRAP_MODE, UNWRAP_MODE, wrap(Key), unwrap(...), exceptions, and Cipher lifecycle.
- [Oracle Java SE 17 — Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): AESWrap, AESWrapPad, RSA, and transformation names.
- [Oracle Java SE 17 — JDK Providers Documentation](https://docs.oracle.com/en/java/javase/17/security/oracle-providers.html): transformations supported by specific providers.
- [RFC 3394 — Advanced Encryption Standard (AES) Key Wrap Algorithm](https://www.rfc-editor.org/rfc/rfc3394): AES-KW algorithm, structure, lengths, and integrity check.
- [RFC 5649 — Advanced Encryption Standard (AES) Key Wrap with Padding](https://www.rfc-editor.org/rfc/rfc5649): AES-KWP, extended length support.
- [NIST SP 800-38F — Methods for Key Wrapping](https://csrc.nist.gov/pubs/sp/800/38/f/final): key-wrapping method recommendations.
- [RFC 8017 — RSAES-OAEP](https://www.rfc-editor.org/rfc/rfc8017.html#section-7.1): RSA-OAEP limits and structure.

## Conclusion

**`Cipher.WRAP_MODE` and `Cipher.UNWRAP_MODE` are two API modes for handling Key objects, not standalone security algorithms.** To store or transfer DEKs, choose a wrapping mechanism designed for keys (AES-KW/KWP, RSA-OAEP, or KMS/HSM), strictly manage KEKs and parameters, validate key types/lengths, protect metadata, and enforce access controls. **`wrap(Key)`** produces wrapped bytes; **`unwrap(..., wrappedKeyAlgorithm, wrappedKeyType)`** reconstructs the Key when cryptographic and provider checks pass. Only treat application data as valid when **key protection**, **payload authentication**, and **authorization** all succeed.
