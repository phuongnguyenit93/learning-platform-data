# 10.1 Distinguishing Key Exchange, Key Agreement, Key Wrapping, and Key Encapsulation

## Objectives

When building a Java application using AES-GCM, TLS, a key store, or encrypting documents for a recipient, you need to know **whether the secret is generated or already exists**, **which party owns the key**, **what is transmitted over the network**, and **which API solves the right problem**. Four easily confused terms are *key exchange*, *key agreement*, *key wrapping*, and *key encapsulation* (KEM).

This lesson is a **concept map and mechanism selection guide**: learn how to identify requirements before implementing, understand how keys flow, and recognize what guarantees are missing. In-depth operations are covered in dedicated lessons on DH/ECDH/X25519/X448, the `KeyAgreement` lifecycle, HKDF, peer authentication, `Cipher.WRAP_MODE`, the Java 21 KEM API, and protocol design.

After reading, you should be able to classify a system by **existing key vs. new key**, **symmetric vs. asymmetric key**, **what the sender/recipient knows**, and **which step performs identity authentication**.

## 1. Four Non-Synonymous Concepts

| Term | Question the mechanism solves | Secret material | Notable output | Typical Java API |
| --- | --- | --- | --- | --- |
| **Key exchange** | How do two endpoints establish keys to communicate? | Depends on the protocol; may combine multiple primitives | Session keys and protocol proofs | A chain of `KeyAgreement`, `KEM`, KDF, signatures/MAC, AEAD |
| **Key agreement** | Can two parties **independently compute a shared secret** from their own private key and the peer's public key? | Each party has its own private key; the secret is not sent | **Raw shared secret** (usually passed through a KDF) | `javax.crypto.KeyAgreement` |
| **Key wrapping** | How do you protect **an existing key** for storage or transport? | Existing Data Encryption Key (DEK); Key Encryption Key (KEK) or authorized recipient key | **Wrapped key bytes**, unwrapped back into the old key | `Cipher.WRAP_MODE`, `Cipher.UNWRAP_MODE`, AESWrap/KMS |
| **Key encapsulation (KEM)** | How does a sender use a recipient's public key to generate a **new shared secret** that the recipient can recover? | Recipient holds the private key; sender generates a new secret internally | **Secret + encapsulation bytes** | `javax.crypto.KEM` (**Java 21+**) |

**Key exchange** is usually the name of an **objective or a complete protocol**. It may use key agreement, KEM, key transport/wrapping, or multiple components together. Do not treat “key exchange” as a synonym exclusively for Diffie–Hellman.

**Key agreement** uses contributions from *both sides*, such as X25519/ECDH. **Key wrapping** starts from *an existing DEK* and protects it under a KEK. **KEM encapsulation** creates a **new secret** and an **encapsulation message** for the recipient's public key; it does not have a default method to accept an arbitrary DEK as input. This is the most important distinction when reading Java APIs.

## 2. Naming the Key Types Correctly

- **DEK (Data Encryption Key):** the key used to encrypt the **content** of a file or record, for example AES-256 for AES-GCM.
- **KEK (Key Encryption Key):** the key used to **wrap/unwrap a DEK**; typically managed by a Key Management Service (KMS), Hardware Security Module (HSM), or a key hierarchy system.
- **Public/private key pair:** an asymmetric key pair used for DH, KEM, RSA transport, or signatures, depending on the algorithm. The private key must be protected; the public key **can be public, but its true owner must be authenticated** before trusting it.
- **Raw shared secret:** the result of DH or the secret recovered by a KEM; this is **key derivation material**, not automatically an AES key for a session.
- **Session/traffic key:** a key derived for a specific algorithm, direction, version, and context; for example, a client→server AES-GCM key.

A 32-byte secret is **not automatically** a protocol-appropriate AES-256 key. You need to design a **KDF** such as HKDF with context/labels, while verifying the key source and protecting against key/nonce reuse. Do not take a raw secret or a wrapped blob and directly turn it into data sent to the client without understanding the properties of the mechanism.

## 3. Key Agreement: Two Parties Independently Compute the Same Secret

Two-party X25519 model:

~~~text
Alice                           Network                           Bob
private a, public A                                               private b, public B

        A ----------------------->                                  |
        | <------------------------ B                               |
        |                                                           |
Z_A = X25519(a, B)                                     Z_B = X25519(b, A)
                  Z_A == Z_B, if keys and parameters match
        |                                                           |
    HKDF(context)                                             HKDF(context)
        |                                                           |
           identical traffic keys per role/label
~~~

Alice and Bob **do not transmit Z** over the network. Each side only sends its public key in the specified format, then uses **its own** private key combined with the peer's public key.

Java uses a state machine:

~~~java
// Snippet inside a method with PrivateKey myPrivate,
// PublicKey peerPublic and GeneralSecurityException handling.
KeyAgreement agreement = KeyAgreement.getInstance("X25519");
agreement.init(myPrivate);
agreement.doPhase(peerPublic, true);
byte[] rawSecret = agreement.generateSecret();
~~~

- For two parties, `doPhase(peerPublic, true)` marks the final phase.
- `generateSecret()` returns **secret bytes**; it does not encrypt payloads on its own, does not prove who the peer is, and does not apply a purpose-specific KDF.
- Finite-field DH requires trusted and compatible `p, g` group parameters; ECDH P-256 requires matching curves; X25519/X448 belong to a different algorithm/format family and must not be swapped arbitrarily.
- You must validate key encoding, type/curve/group, and public inputs according to the provider/standard, and **authenticate peer identity** via a trust anchor/pinning/signature/protocol.

If an attacker in the middle swaps the public keys, both sides can still compute a secret **with the attacker** without the API throwing an error. X25519 solves the secret computation problem; it **does not solve the identity trust problem on its own**.

## 4. Key Transport and Key Wrapping: Pre-Selected DEK

Suppose a file has already been encrypted with a DEK. The application needs to store the file long-term, but cannot store the DEK in plaintext alongside the ciphertext:

~~~text
DEK randomly generated
     |                    +---------------------------+
     +--> AES-GCM(file) -> | dataCiphertext + tag      |
     |                    +---------------------------+
     |
     +--> AES-KW(KEK, DEK) --> wrappedDEK
                               |
                        stored with keyId, version
                               |
                authorized --> unwrap with KEK --> original DEK
~~~

This is **envelope encryption**. `AESWrap` (AES Key Wrap, RFC 3394) protects **key bytes**; it has no AAD for metadata such as tenant, record ID, or expiration time. Cases where input lengths do not fit AES-KW may require AESWrapPad (AES-KWP) if supported by the provider. Metadata fields must be **bound/verified at the record/protocol layer**.

In Java, `Cipher.WRAP_MODE` and `UNWRAP_MODE` are **modes of operation**, not algorithm names:

~~~java
// Snippet with existing SecretKey kek and SecretKey dek:
Cipher wrap = Cipher.getInstance("AESWrap");
wrap.init(Cipher.WRAP_MODE, kek);
byte[] wrappedDek = wrap.wrap(dek);

Cipher unwrap = Cipher.getInstance("AESWrap");
unwrap.init(Cipher.UNWRAP_MODE, kek);
Key originalDek = unwrap.unwrap(
        wrappedDek, "AES", Cipher.SECRET_KEY);
~~~

In the `unwrap(...)` call, `"AES"` is the **algorithm of the recovered key**, which differs from the wrapping algorithm `"AESWrap"`. With software keys, `getEncoded()` may return raw bytes; with HSM/KMS, the key may be **non-extractable** and must be operated on through a provider/key handle. Do not try to export a KEK just to use a demo snippet.

**Key transport** refers to the case where the sender **chooses a DEK beforehand** and transfers it to an authenticated recipient, for example encrypting the DEK with the recipient's RSA public key using **RSA-OAEP**. The recipient uses the corresponding private key to recover it. This is also a way to *protect/transport an existing key*, but it differs from key agreement and KEM: the sender selects the key in advance and does not need an ephemeral DH contribution from both sides.

**RSA-OAEP and AESWrap protect the key, not prove who the sender is.** Anyone who knows the RSA public key can encrypt a DEK for the recipient. For storage, you must enforce unwrap permissions, manage KEKs, handle rotation/rewrap, and prevent key swapping across objects/tenants. For transmission, you must authenticate the **exact recipient public key**.

## 5. KEM: New Secret, Public Encapsulation Message

KEM uses the recipient's public key to produce **two outputs**:

~~~text
Recipient Bob: (pkR, skR)
                       |
Sender Alice: Encap(pkR)
             /          \
  sharedSecret_A      encapsulation = enc   ---> Bob
       (SECRET)               (PUBLIC)          |
                                              Decap(skR, enc)
                                                    |
                                               sharedSecret_B

                    sharedSecret_A == sharedSecret_B
~~~

- **Secret:** never send, never log; must be passed through a **context-bound KDF** to obtain the actual keys used for AES-GCM/MAC.
- **Encapsulation (or KEM ciphertext):** the public data that must be sent; with **DHKEM over X25519**, it is typically the representation of the **ephemeral public key** in KEM format (32 bytes), **not the raw secret** or the file ciphertext.
- KEM does not encrypt large payloads on its own, does not authenticate the sender, and does not prevent replay. Base-mode KEM allows **anyone with pkR** to create a message for the recipient.
- Java 21 introduced `javax.crypto.KEM`. Java 17 has `KeyAgreement` X25519, but does not automatically include `KEM` or the DHKEM rules of RFC 9180.

Java 21+ snippet:

~~~java
// Snippet: Bob's public key must be authenticated beforehand.
// recipientPublic: PublicKey, recipientPrivate: PrivateKey.
KEM kem = KEM.getInstance("DHKEM");
KEM.Encapsulated result =
        kem.newEncapsulator(recipientPublic).encapsulate();
SecretKey localSecret = result.key();        // keep secret
byte[] message = result.encapsulation();     // send to Bob

SecretKey recipientSecret =
        kem.newDecapsulator(recipientPrivate)
           .decapsulate(message);
~~~

Do not use `message` as an AES key even though it may have the same length as the secret; this is **public transport data**. A KEM message with a valid length that has been modified may cause the recipient to derive a **different secret**, without necessarily throwing an exception. When using KEM → KDF → AEAD, the **AEAD tag** is what must verify the payload and AAD; a valid KEM does not inherently provide sender authentication.

## 6. A Java 21 Program Comparing Three Mechanisms on the Same Test Data

The program below only tests the **input/output shape** of KeyAgreement, AES Key Wrap, and DHKEM, helping show one operation that creates a secret, one operation that protects an **existing** key, and one operation that creates a secret together with an encapsulation. The program does not create a network protocol, does not derive traffic keys, does not verify identities, and does not use keys to encrypt payloads. In production, prefer standard protocols, KDFs, and properly designed AEAD.

Create file **MechanismComparisonDemo.java**:

~~~java
import java.security.Key;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KEM;
import javax.crypto.KeyAgreement;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class MechanismComparisonDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator x = KeyPairGenerator.getInstance("X25519");
        KeyPair alice = x.generateKeyPair();
        KeyPair bob = x.generateKeyPair();

        // 1. Agreement: own private + peer's public.
        KeyAgreement a = KeyAgreement.getInstance("X25519");
        a.init(alice.getPrivate());
        a.doPhase(bob.getPublic(), true);
        byte[] za = a.generateSecret();

        KeyAgreement b = KeyAgreement.getInstance("X25519");
        b.init(bob.getPrivate());
        b.doPhase(alice.getPublic(), true);
        byte[] zb = b.generateSecret();
        System.out.println("Agreement secret equal: "
                + MessageDigest.isEqual(za, zb));

        // 2. Wrap: protect an existing DEK using a KEK.
        KeyGenerator aes = KeyGenerator.getInstance("AES");
        aes.init(128);
        SecretKey dek = aes.generateKey();
        SecretKey kek = aes.generateKey();
        Cipher wrapper = Cipher.getInstance("AESWrap");
        wrapper.init(Cipher.WRAP_MODE, kek);
        byte[] wrapped = wrapper.wrap(dek);

        Cipher unwrapper = Cipher.getInstance("AESWrap");
        unwrapper.init(Cipher.UNWRAP_MODE, kek);
        Key restored = unwrapper.unwrap(
                wrapped, "AES", Cipher.SECRET_KEY);
        System.out.println("Wrap restores old DEK: "
                + MessageDigest.isEqual(
                        dek.getEncoded(), restored.getEncoded()));

        // 3. KEM: generate a new secret and public encapsulation.
        KeyPair recipient = x.generateKeyPair();
        KEM kem = KEM.getInstance("DHKEM");
        KEM.Encapsulated enc =
                kem.newEncapsulator(recipient.getPublic()).encapsulate();
        SecretKey received =
                kem.newDecapsulator(recipient.getPrivate())
                   .decapsulate(enc.encapsulation());
        System.out.println("KEM secret equal: "
                + MessageDigest.isEqual(
                        enc.key().getEncoded(), received.getEncoded()));
        System.out.println("KEM message present: "
                + (enc.encapsulation().length > 0));

        Arrays.fill(za, (byte) 0);
        Arrays.fill(zb, (byte) 0);
    }
}
~~~

Run with **JDK 21+** with a provider supporting DHKEM/X25519 and AESWrap:

~~~bash
javac --release 21 -encoding UTF-8 MechanismComparisonDemo.java
java MechanismComparisonDemo
~~~

Stdout:

~~~text
Agreement secret equal: true
Wrap restores old DEK: true
KEM secret equal: true
KEM message present: true
~~~

This result demonstrates **three distinct API contracts** in a single process. `Arrays.fill` only reduces the lifetime of self-owned arrays; it does not prove every secret inside the provider/JVM is wiped. `getEncoded()` is used in the demo with exportable software keys; an HSM/provider may return `null`. There is no identity authentication, key confirmation, nonce, replay protection, or policy yet, so do not treat this code as a secure channel.

## 7. Choosing a Mechanism for Real-World Problems

| Requirement | Typically suitable mechanism | What else must be done |
| --- | --- | --- |
| Two services need to establish session secrets over a connection | Key agreement/KEM **inside a standard protocol** such as TLS 1.3 | Identity authentication, transcript, KDF, traffic keys, nonce, policy |
| One side has created an AES-DEK and needs Bob to obtain that exact key | Key transport, RSA-OAEP, or wrapping via an appropriate KEK | Authenticate the exact public key/key owner, metadata, permissions |
| Encrypt large files and store keys long-term | DEK + AEAD, wrap DEK under a KEK in KMS/HSM | Key ID, unwrap permissions, rotation/backup, tenant/object binding |
| Send a file to a recipient with a public key, generating a new session secret | KEM + KDF + AEAD; consider HPKE | Authenticate recipient, sender auth when required, replay, wire format |
| Replace KEK while keeping the DEK | Unwrap/rewrap DEK | KMS permissions, atomic version update, and rollback policy |
| Interoperate across multiple languages/providers | A specified protocol/suite and test vectors | Public key format, OAEP parameters, HKDF info, AEAD AAD/nonce |

**Public keys must be authenticated in key agreement, KEM, and public-key transport alike.** If an attacker swaps the public key, you may end up sharing a secret or wrapping a DEK **for the attacker** even though the mathematical operation completes validly. Certificates, trusted pins, signatures over the transcript, and standardized protocol mechanisms are what bind keys to an identity.

## 8. Common Misconceptions and Consequences

1. **“Key exchange = the single DH algorithm.”** False: it is an objective/protocol that may combine multiple primitives.
2. **“An X25519 shared secret is long enough, so it can be used directly as any AES/MAC key.”** Missing KDF and key-purpose/role separation.
3. **“Both wrap and encapsulate encrypt a pre-selected DEK.”** No: wrap takes an existing key, whereas KEM by default generates a new secret.
4. **“A 32-byte encapsulation is an AES-256 key.”** No: despite having the same size, an encapsulation is public data.
5. **“AESWrap has tenant AAD like AES-GCM.”** No: AES-KW authenticates key material according to its own algorithm; metadata requires a different mechanism.
6. **“Receiving a public key means you know the sender.”** No: you must verify the source/identity; base KEM does not authenticate the sender.
7. **“Wrapping the DEK successfully means the file ciphertext is authenticated.”** No: the file needs a tag/MAC according to the payload encryption algorithm.
8. **“Having a shared secret means MITM is impossible.”** No: an attacker in the middle can establish two agreement sessions using their own keys.
9. **“Java 17 has KEM because it already has X25519.”** No: the `javax.crypto.KEM` API appeared in Java 21.
10. **“SecretKey.getEncoded() always returns bytes.”** No: keys in an HSM/KMS may be non-extractable.
11. **“Hand-rolled DHKEM + HKDF + AES-GCM = standard HPKE.”** No: HPKE also defines the key schedule, suite, mode, record context, and serialization.
12. **“A valid wrapped key cannot be swapped onto another file.”** No: you need authorization, policy, record binding, and replay/rollback protection.

## 9. Self-Check Exercises

**1.** A file already has an AES-256 DEK. You need to protect the DEK in a KMS so that the exact old DEK can be recovered later. Which mechanism is appropriate, and why is KEM not an `encapsulate(existingDek)` call?

**2.** Alice and Bob derive the same secret using X25519. What data is sent over the network, and what step is still missing for Alice to know it is truly Bob?

**3.** For a KEM message, which part is sent publicly, which part is kept secret, and which part is the ciphertext of the application data?

**4.** Why does `unwrap(bytes, "AES", SECRET_KEY)` require the string `"AES"` even though the transformation is already `"AESWrap"`?

**5.** If the recipient's long-term RSA private key is compromised, does key data previously transported via RSA-OAEP have forward secrecy by default? Explain.

**6.** A DEK is unwrapped validly, but the user does not belong to the record's tenant. Is the system allowed to decrypt and return the plaintext? Which layer must reject it?

**7.** A DHKEM encapsulation is modified while keeping a valid length. Why is merely checking for exceptions from `decapsulate()` not enough to protect the payload?

**8.** When should you use proven TLS/HPKE instead of assembling `KeyAgreement`, `KEM`, `Cipher`, and HKDF yourself?

## 10. Implementation Checklist

- [ ] Determine whether the key is **newly generated** or **already exists**; whether you need to exchange a secret, protect a DEK, or encrypt a payload.
- [ ] Choose the right primitive and API, explicitly specifying JDK version, provider, algorithm, and key types.
- [ ] Recipient/peer public keys must be authenticated according to policy; raw shared secrets must go through an appropriate KDF.
- [ ] Protect payloads with AEAD using proper nonce/tag/AAD; key wrapping does not replace data authentication.
- [ ] For DEK/KEK, manage key IDs, wrap/unwrap permissions, HSM/KMS, rewrap, backup, and rotation.
- [ ] Defend against MITM, replay, downgrade, and context confusion using a **specified and tested protocol**, not just a single succeeding operation.
- [ ] Never log private keys, shared secrets, traffic keys, or KEK/DEKs; check whether the provider has non-exportable keys.
- [ ] Test invalid key/suite errors, substituted public keys, tampered capsules/ciphertexts, swapped metadata, and disallowed versions.

## Reference Standards

- [Java SE 17 — KeyAgreement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyAgreement.html)
- [Java SE 17 — Cipher wrap/unwrap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html)
- [Java SE 21 — KEM API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.html)
- [RFC 7748 — X25519/X448](https://www.rfc-editor.org/rfc/rfc7748)
- [RFC 3394 — AES Key Wrap](https://www.rfc-editor.org/rfc/rfc3394)
- [RFC 5869 — HKDF](https://www.rfc-editor.org/rfc/rfc5869)
- [RFC 9180 — HPKE KEM/KDF/AEAD](https://www.rfc-editor.org/rfc/rfc9180)
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446)
