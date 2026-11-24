# 9.1. How Do Digital Signatures Protect Data Integrity and Source Authentication?

## 1. The problem: knowing whether data was modified and came from the right source

Suppose system A sends system B a payment request: `order=42;amount=120000`. B needs to distinguish three questions:

1. **Integrity:** Were the data bytes altered after the signer created the signature?
2. **Source authentication:** Was the signature created by the party holding the **private key corresponding to a trusted public key**?
3. **Confidentiality:** Can unauthorized parties read the contents in transit?

**Digital signatures** solve the first two questions **under appropriate cryptographic and trust conditions**. They do not encrypt or hide the message by themselves. To keep data confidential, use TLS, appropriate data encryption, or another channel/storage security mechanism.

An important distinction: **mathematically verifying a valid signature** is not synonymous with **knowing who the signer is**. If an attacker generates their own key pair, signs a message themselves, and hands their own public key to the recipient, verification can return `true`. The recipient only has proof that “someone holding the private key paired with this public key signed it,” not yet proof that it is partner A. A mechanism is needed to **bind the public key to a trusted identity/partner**.

### Learning objectives

After this lesson, you can explain the signing–verification flow, perform signing/verification with JCA `Signature` in Java 17+, distinguish **integrity**, **source authentication**, **identity/trust**, **confidentiality**, replay protection, and other limitations; and understand why you must sign the **exact byte sequence** and control public keys, algorithms, and application context.

## 2. Principles of asymmetric digital signatures

Modern digital signatures use an **asymmetric key pair**:

- **Private key:** Kept secret by the signer and used when creating a signature. The recipient does not need to know this key.
- **Public key:** Used to verify the signature. It can be published, but **its origin and authorization for use must be authenticated**.

The process at a conceptual level:

```text
SIGNER (authorized to sign)                   RECEIVER / VERIFIER

Message M (exact bytes)                       Receives M' + signature + keyId...
          |                                                |
          v                                                v
Signature.initSign(privateKey)                Look up signer's trusted publicKey
Signature.update(M)                                        |
Signature.sign() -> signature S                            v
          |                                   Signature.initVerify(publicKey)
          +---------- M + S ------------>     Signature.update(M')
                                              Signature.verify(S)
                                                         |
                                              true: valid signature for M' with that key
                                              false/error: reject, do not trust data
```

In schemes such as Ed25519, RSA-PSS, or ECDSA, the signing algorithm has its own **message hashing/representation mechanism** specified by the algorithm. Do not assume that “just running SHA-256 and encrypting the digest with the private key” is enough to invent your own digital signature. You must use a standardized signature algorithm through JCA, with matching parameters, encoding, and policy on both sides.

Why is data tampering detected? The signature is cryptographically bound to the **message content** and the **private key**. When an attacker modifies a single byte of the verified message while keeping the original signature, `Signature.verify` with the legitimate signer's public key will fail, barring a break in cryptographic security assumptions or an implementation/protocol flaw.

**The message does not need to be kept secret** to have a valid signature: in many applications both the message and the signature are sent in cleartext. The value of a signature lies in detecting tampering and binding the signing source to an authenticated public key.

## 3. What does “protecting integrity” mean?

### 3.1. A signature binds the signed bytes

If party A signs byte sequence `M`, and party B verifies the exact `M` with signature `S` and a trusted public key, a valid result demonstrates under cryptographic assumptions that the content `M` has not been modified since the signature was created by the holder of the private key.

If B replaces `M` with `M'` (differing by one byte), the old signature is normally no longer valid. This applies to **every single byte**, not merely the linguistic meaning. For example:

- `"amount=120000"` differs from `"amount=120001"`.
- UTF-8 with line feed `LF` differs from `CRLF`.
- Two JSON objects with identical data but different field ordering typically produce different byte arrays.
- Unicode can represent visually identical characters using different sequences of code points.
- Base64 of the same bytes can have formatting variants; rules for signing a **Base64 string** differ from rules for signing the **decoded bytes**.

Therefore, the application must define **exactly what is signed**, how it is converted into `byte[]`, and how the receiver reconstructs the bytes for verification.

### 3.2. A signature protects only the fields actually included in the signed scope

Suppose a message has the fields `amount`, `currency`, `tenantId`, and `expiresAt`. If the signer only signs `amount` without including the remaining fields in the signed payload, changing `tenantId` or `expiresAt` **does not necessarily invalidate the signature**.

A secure design must include in the signed scope all fields that affect **business meaning**, routing, access permissions, currency unit, operation type, protocol version, expiration, and request identifier—in an unambiguous byte format.

**Dangerous bug:** verifying the signature on the body while executing certain header fields or query string parameters that are **unsigned**, such as selecting the destination account via an `accountId` in the URL that is not bound to the payload.

### 3.3. A signature does not prove the content is truthful

A validly signed document can still contain a wrong price, fraudulent information, or an instruction the signer had no authority to issue. `Signature.verify(...) == true` is **not** a check of business rules, authorization, balance, limits, invoice validity, or user consent.

Integrity here means the content **matches exactly what was signed**, not that “the data is guaranteed to be factually true.”

## 4. How is “source authentication” understood?

### 4.1. Cryptography proves a link to the private key

Given public key `K_pub`, a valid signature on `M` indicates that a party capable of using the corresponding private key `K_priv` created the signature (assuming a secure signature scheme). From a public key and a valid signature alone, you cannot reliably infer the **person's name, organization, title, or current authorization** of the signer.

You must distinguish:

- **Cryptographic verification:** Does the algorithm verify bytes `M`, signature `S`, and public key `K_pub` as valid?
- **Key authenticity:** Why does B trust that `K_pub` belongs to partner A rather than a key planted by an attacker?
- **Authorization:** Which data types/tenants/actions is this key permitted to sign, and during what period?
- **Attribution/audit:** Who used the private key, under what circumstances, and is there supporting governance evidence?

Without **key authenticity**, an attacker can perform *public-key substitution*: generate a key pair, sign with it, and swap in their own public key for verification. A `true` result only validates the signature of the **forged key**, not the expected partner.

### 4.2. Ways to bind a public key to a trusted source

Depending on the system:

1. **Pinning/allowlist:** The receiver stores the partner's fingerprint or public key distributed over a trusted channel; it only uses keys that are registered and not revoked.
2. **X.509 digital certificates (PKI):** A certificate binds a public key to identity attributes verified by a certificate authority; the verifier must validate the **certificate chain** up to a trusted trust anchor, validity period, policies, name/identifier, key usage, and revocation status when required.
3. **Protected directory/JWKS:** Use an authenticated public key source, TLS, caching/rotation, and policies; never accept an arbitrary public key URL from an untrusted request without domain and trust verification.
4. **HSM/KMS and signing permissions:** Private keys reside in a protected key store, signing call permissions are controlled, and audit logs are recorded. This reduces key-compromise risk and strengthens process evidence, but does not turn every valid signature into unconditional authorization.

In Java, `X509Certificate.getPublicKey()` only **returns the public key**; that call itself **does not perform full trust path validation** for the certificate. To trust an identity in a PKI environment, use an appropriate certificate chain/path verification mechanism such as `CertPathValidator` with the proper trust policy. Never treat “the certificate parsed successfully” as “the certificate is trusted.”

### 4.3. Compromised keys and misuse of authority

If a private key is stolen or an unauthorized party gains access to call the signing system, an attacker can produce valid signatures. `Signature.verify` cannot detect key compromise on its own. You need key lifecycle management, access control, monitoring, rotation, certificate lifetimes, key revocation, and incident response procedures.

Therefore, the accurate statement is: **a valid signature + a public key properly bound to a source and trusted under policy + an uncompromised private key** provide strong evidence of integrity and signing origin. Never claim “if verify returns true, it was definitely signed by person X.”

## 5. Java 17+: key generation, signing, and verification with Signature (Ed25519)

JCA provides the `java.security.Signature` engine. The example uses `Ed25519` (from the EdDSA family) because its syntax is concise and it is supported by modern JDKs; this is a signature algorithm, **not a data encryption algorithm**.

Standard API flow:

- `KeyPairGenerator.getInstance("Ed25519")` and `generateKeyPair()` generate a key pair suitable for the demo.
- `Signature.getInstance("Ed25519")` obtains the engine for the signature algorithm.
- `initSign(privateKey)` sets the private key; `update(messageBytes)` feeds the exact specified bytes; `sign()` produces the signature.
- `initVerify(publicKey)` sets the public key; `update(messageBytes)` feeds the exact same bytes; `verify(signatureBytes)` returns a boolean or throws an exception for invalid API/provider-level cases.

**Note on engine state:** A `Signature` after `initSign` is in signing mode; after `initVerify` it is in verification mode. Do not share a mutable instance concurrently across threads for signing/verifying, and do not forget to re-initialize or reset properly for a new message. The `update` API allows feeding multiple chunks; the order of the chunks must match the exact bytes verified by the other party.

### 5.1. Standalone program: DigitalSignatureDemo.java

The example generates a key pair for the sender and a **different** key pair to test a wrong key. The signer creates a signature for a byte sequence prefixed with `app=orders;v=1;...`; the receiver verifies the valid case, then tests modifying the message, modifying the signature, and swapping the public key. Neither keys nor actual signature bytes are printed.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;

public final class DigitalSignatureDemo {
    static byte[] sign(PrivateKey privateKey, byte[] message)
            throws GeneralSecurityException {
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(privateKey);
        signer.update(message);
        return signer.sign();
    }

    static boolean verify(PublicKey publicKey, byte[] message, byte[] signature)
            throws GeneralSecurityException {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(publicKey);
        verifier.update(message);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair sender = generator.generateKeyPair();
        KeyPair stranger = generator.generateKeyPair();

        byte[] message = "app=orders;v=1;order=42;amount=120000"
                .getBytes(StandardCharsets.UTF_8);
        byte[] signed = sign(sender.getPrivate(), message);
        byte[] changedMessage = message.clone();
        changedMessage[changedMessage.length - 1] ^= 1;

        byte[] changedSignature = signed.clone();
        changedSignature[changedSignature.length - 1] ^= 1;

        System.out.println("Signature length: " + signed.length + " bytes");
        System.out.println("Valid signature: " +
                verify(sender.getPublic(), message, signed));
        System.out.println("Modified message accepted: " +
                verify(sender.getPublic(), changedMessage, signed));
        System.out.println("Wrong public key accepted: " +
                verify(stranger.getPublic(), message, signed));
        System.out.println("Modified signature accepted: " +
                verify(sender.getPublic(), message, changedSignature));
        System.out.println("Same bytes again: " +
                verify(sender.getPublic(), message.clone(), signed));
    }
}
```

Compile and run with JDK 17+ with a provider supporting Ed25519:

```bash
javac DigitalSignatureDemo.java
java DigitalSignatureDemo
```

Exact stdout of the example:

```text
Signature length: 64 bytes
Valid signature: true
Modified message accepted: false
Wrong public key accepted: false
Modified signature accepted: false
Same bytes again: true
```

### 5.2. Explaining the output by security property

1. **Signature length: 64 bytes:** Ed25519 outputs a 64-byte signature per the algorithm format; this is a specific characteristic of Ed25519, **not** the signature length of all algorithms (for example, RSA-PSS depends on the modulus size).
2. **Valid signature: true:** The message is unchanged; the public key matches the signing private key; verification succeeds. In the example, the public key is taken directly from `sender`, so it **does not yet simulate trusted key distribution**.
3. **Modified message accepted: false:** Changing only the last byte of the message without creating a new signature. This illustrates the binding of the signature to the **signed bytes**.
4. **Wrong public key accepted: false:** Switching to the public key of an independent key pair causes the signature to be invalid; proving the signature depends on the corresponding key.
5. **Modified signature accepted: false:** Changing a single byte of the signature while keeping the message/key intact also causes verification to fail in the example.
6. **Same bytes again: true:** Creating a new array via `message.clone()` leaves the byte content unchanged, so verification succeeds. The array's **object reference** has no effect; the signature protects the byte content.

The `sender`/`stranger` variables are randomly generated on each run, so the key/signature bytes differ, while the stdout lines for length and boolean results remain as shown above. The program is intentionally simple to understand the **signing and verification mechanism**, not a production application: it does not persist keys, create/trust certificates, communicate over a network, or address replay protection on its own.

**For malformed signatures**, depending on the algorithm/provider, `Signature.verify` may return `false` **or throw `SignatureException`**. Do not turn an exception into acceptance; the application layer must treat both `false` and verification/malformed-input errors as invalid, handling/logging them according to policy without leaking sensitive information.

## 6. Why is hashing data and storing SHA-256 not enough for source authentication?

A hash such as `SHA-256(message)` can detect modification **when the expected digest comes from a trusted and protected source**. However, if an attacker can modify both the message **and** the accompanying digest, they can simply recompute SHA-256 without needing any secret. A plain hash provides no proof of the sender.

HMAC uses a **shared secret key**. Anyone who holds the key can generate and verify an HMAC; thus HMAC is suitable when parties share a key, but a third party cannot independently distinguish which member within the group holding the shared key created the tag.

Digital signatures use a **private key to sign** and a **public key to verify**. Many parties can verify without knowing the private key. When the public key is bound to a trusted source and only the signer is authorized to use the private key, a signature provides stronger source authentication evidence than a shared-secret model in systems with multiple verifiers.

| Property | Standalone SHA-256 digest | HMAC-SHA256 | Ed25519 / RSA-PSS / ECDSA signature |
| --- | --- | --- | --- |
| Is a secret needed to produce the check value? | No | Yes, shared key | Yes, private key |
| What does the verifier need? | Trusted expected digest | Same secret key | Trusted public key |
| Detects tampering if checked properly? | Yes, when the expected digest is protected | Yes | Yes |
| Authenticates source as a key holder? | No | Yes, within the secret-sharing group | Yes, the party authorized to use the corresponding private key |
| Can the verifier forge a valid check value? | Anyone can compute the digest | Yes, since they share the secret | **No**, if they only have the public key |
| Proves signer identity without trust binding? | No | No | **No** |
| Encrypts / hides content? | No | No | No |
| Automatic replay protection? | No | No | No |

Do not confuse terminology: **digital signature** does not mean “encrypting with the private key and decrypting with the public key.” That folklore explanation causes misunderstandings about padding, hashing, algorithms, and security goals. Always use the standard `Signature` signing/verification API and approved schemes.

## 7. Designing signed messages: signing the exact bytes and context

### 7.1. Choosing an unambiguously reproducible byte format

The signer and verifier must agree on:

- Encoding: use UTF-8 or a specified binary format, **never** rely on the default charset.
- Field order and field names; data types; number formatting rules (e.g., `120000` differs from `120000.0`); timestamp/timezone encoding.
- Escaping rules, Unicode normalization, newlines, and padding; presence/absence of whitespace.
- Version of serialization/canonicalization, and how unknown fields are handled.
- If using JSON/XML, sign **bytes canonicalized according to a clear specification** or sign the **original received/stored bytes**, rather than arbitrarily parsing and re-serializing in another way.
- If transmitting the signature in Base64, clearly define whether to **sign the payload bytes** or **sign the Base64 textual representation**; typically, you sign the payload bytes before encoding the signature.

In particular, **concatenating variable-length fields without boundaries** creates ambiguity risks: signing `"ab" + "c"` yields the same bytes as `"a" + "bc"` even though the two field pairs differ. Use binary framing, length prefixes, tag–length–value, or a canonical format for unambiguous representation.

### 7.2. Domain separation and signature scope

If the same key is used across multiple applications/protocols, a signature on `"approve=1"` could be **recontextualized (cross-context attack)** by an attacker into another workflow that also trusts that public key, if both places produce identical signed/verified bytes and do not check purpose.

One defense is **embedding context into the signed bytes**, for example:

```text
applicationId = orders
schemaVersion = 1
operation = authorize-payment
tenantId = shop-7
orderId = 42
amountMinorUnits = 120000
currency = VND
expiresAt = 2026-12-01T00:00:00Z
requestId = unique-id
```

This is a **description of logical fields**, not a canonicalized byte serialization. Define an exact format and sign the entire encoded byte version. `app=orders;v=1` in the demo illustrates a domain prefix, **not** a substitute for a production schema with strict field boundaries, permissions, limits, and versioning.

Use **separate keys by purpose** when appropriate, such as separating a transaction-signing key from an update-package-signing key; both the receiver and signer must enforce which operation types are allowed.

### 7.3. Signing large files or streaming data

`Signature.update(byte[])` can be called multiple times with consecutive chunks before `sign()` or `verify(...)`. When updating chunk by chunk, the **order and total bytes** must be identical to single-pass signing. Avoid hashing externally and then asking `Ed25519` to sign the digest when the actual protocol specifies signing the **original message**: doing so changes the signed content (and for Ed25519 it does not automatically switch to Ed25519ph mode).

Do not verify one copy of a file and then execute/trust **another copy that could be altered between the two steps**. For sensitive artifacts, ensure the verified data is the exact data that will be used; consider immutable streams/buffers, atomic storage, file handles, and TOCTOU mitigations appropriate to the environment.

## 8. Choosing algorithms and working with Java providers

### 8.1. Common signing algorithms

| Algorithm | Key characteristics to note |
| --- | --- |
| **Ed25519** | Belongs to EdDSA, generally simple to use, fixed 64-byte signature; available in modern JDK 17 runtimes when supported by the provider. |
| **SHA256withECDSA** | ECDSA over an appropriate curve, with SHA-256; public key and signature size/format must match. Java `Signature` typically represents ECDSA signatures using ASN.1 DER encoding for the `(r,s)` pair. |
| **RSASSA-PSS** | RSA-PSS signature; requires matching digest, MGF1 digest, salt length, trailer field, and modulus length; avoid inconsistent or downgraded configurations. |
| **SHA256withRSA** | Usually represents RSA PKCS#1 v1.5 with SHA-256 in JCA; may be needed for legacy compatibility, but new designs generally consider Ed25519 or RSA-PSS per compatibility standards/policies. |

Do not equate “ECDSA” with “ECDH”: ECDH is key agreement, not signatures. Do not arbitrarily use an RSA encryption key in place of a signing key if purpose, key usage, and key governance are separate.

**Never allow untrusted requests to freely choose any algorithm/provider the system will accept.** An `alg` header or equivalent metadata may serve as routing data against a configured allowlist/key; you must check that the algorithm is actually permitted for the specific key and use case to prevent algorithm-confusion/downgrade attacks.

### 8.2. JCA Signature is a stateful API

With `Signature`, the flow is `getInstance` → `initSign` or `initVerify` → one or more `update` calls → `sign`/`verify`. Common mistakes:

- Calling `update` before `initSign`/`initVerify`: invalid engine state.
- Calling `Signature.getInstance("Ed25519")` when the public key is the wrong type or the signature was created with another scheme.
- Using mismatched PSS parameters between the two sides.
- Verifying on bytes that were parsed/re-serialized differently from the signed version.
- Assuming `Signature` is thread-safe and sharing it across multiple requests without synchronization.
- Treating a successful `Signature.verify(...)` as **identity authentication** even when the public key came straight from the request.

### 8.3. Key storage, exchange, and rotation

In Java, `PublicKey.getEncoded()` for many common keys uses the `X.509 SubjectPublicKeyInfo (SPKI)` format; `PrivateKey.getEncoded()` (if the key is exportable) is typically `PKCS#8`. Do **not** mistake a key encoding format for a validated X.509 certificate: SPKI only represents public key information.

Private keys should be stored in a `KeyStore`, HSM, KMS, or appropriately protected key system. Restrict exporting private bytes, signing permissions, and logging/configuration exposure. Public keys can be distributed, but identity binding and key rotation must be enforced; when rotating keys, do not blindly discard all old signatures or accept old keys indefinitely. Design `keyId`, validity periods, versions, and revocation rules for long-lived signed data.

## 9. Security limitations that digital signatures do not solve automatically

### 9.1. Does not provide confidentiality

Anyone observing `message + signature` can still read the message if it is transmitted in cleartext. TLS/AEAD or appropriate encryption is needed when the payload is sensitive. **Sign-then-encrypt** or **encrypt-then-sign** both appear in standard protocols, but do not compose these steps ad hoc without proper design because of subtleties around what is signed and how verification works.

### 9.2. Does not automatically prevent replay

A validly signed request at time T can be re-sent verbatim at T+1; the signature remains valid for the exact same message bytes. If the business logic requires replay protection:

- Sign a unique business `requestId`/nonce, timestamp/expiry, and required context fields.
- The receiver checks expiration with a reasonable clock skew tolerance.
- Persist processed `requestId` or sequence-number state to reject duplicates.
- Use idempotency protocols when legitimate retries can occur.

Note that only a **signed timestamp** protects against arbitrary tampering; a timestamp *does not* stop replay by itself unless the server enforces a time window or anti-reuse state.

### 9.3. Does not automatically guarantee authorization or business correctness

An authenticated signer might not be permitted to modify another tenant, exceed a limit, or sign a message type outside its authority. After verification, the server must still check **authorization**, policy per `keyId`/identity, account status, limits, schema, and business conditions.

### 9.4. Does not absolutely prove “non-repudiation”

Digital signatures can support evidence of signing origin, but **non-repudiation** in a legal/operational sense also depends on private key control, signer identification, certificates, timestamps/evidence, authorization workflows, audit trails, and the possibility of key compromise. If a private key is shared across multiple employees or services, verification cannot distinguish which individual used that key.

A valid signature does not prove a human read, understood, or agreed to all terms, nor does it prove the content was not generated by a compromised machine holding signing rights.

### 9.5. Does not verify the trust chain on behalf of the application

If an application downloads an arbitrary certificate over the network and calls `certificate.getPublicKey()` to verify, returning `true` does not substitute for validating the certificate chain, trust anchor, name/identity, key usage, effective validity/revocation, and policy. Likewise, a client-controlled key ID in a header should only be used as a *key-lookup hint under policy*, not as proof of identity.

## 10. Verification workflow in a real-world application

A signature-receiving system should follow an ordered sequence of steps:

1. **Read the envelope within safe bounds:** message size, signature length, Base64 encoding, version, `keyId`, content type; reject malformed input. Do not parse unbounded JSON or trust client-supplied fields.
2. **Determine the permitted key and algorithm:** consult an allowlist/key registry/truststore; if using X.509, validate the trust path and policy; verify authorization to sign this message type.
3. **Canonicalize or extract the signed bytes per protocol:** never silently reformat; include version, purpose, tenant, amount, currency, and expiration if required by the protocol.
4. **Cryptographic verification:** `Signature.initVerify(trustedPublicKey)`, `update(exactMessageBytes)`, `verify(signatureBytes)`. Only treat as valid if it returns `true` with no errors.
5. **Verify context and business logic:** key still authorized, schema/authorization, signed timestamp/expiry, replay/idempotency, resource state.
6. **Only after that** accept, persist, or execute the data; audit the verification and key identifier with necessary metadata without logging private keys or sensitive data.

**The order may require preliminary parsing steps before verification** to locate `keyId`/version, but these preliminary fields must always be treated as **unauthenticated** until signature and policy checks succeed. Avoid irreversible side effects prior to verification.

### Error example: verifying the right signature on the wrong data object

Suppose a JSON body `{"amount":120000}` is signed, while the server reads `currency=USD` from an unsigned query string. An attacker can keep the body+signature intact and change the query string from `VND` to `USD`, and the signature remains valid for the body. Fix: **bind currency into the signed data** and read from the same signed data source at execution time.

### Error example: trusting a sender-supplied public key

A request contains `payload`, `signature`, and `publicKey`. The server runs `verify(publicKey, payload, signature)` and permits the operation if true. An adversary generates their own key pair, signs their own payload, sends all three, and is accepted. Fix: look up the public key against a **server-managed registry/trust anchor**, then check permissions by identity/scope; never rely on an unanchored public key floating in the request.

## 11. Quick reference table of guarantees and limitations

| Statement | Accurate conclusion |
| --- | --- |
| Can a digital signature detect if a message was modified after signing? | **Yes**, if signed/verified over the exact bytes with a sufficiently secure algorithm and key. |
| Does `verify == true` authenticate the signer's identity? | **Only when** the public key is bound to the right identity and trusted policy, accounting for key-compromise risk. |
| Can anyone with the public key forge a valid signature? | **No**, under signature security assumptions; the private key or access to use it is required. |
| Does `verify == true` guarantee the message is valid business-wise? | **No**; validation and authorization are still required. |
| Does a signature encrypt the data? | **No**; a signed payload can still be read. |
| Does a signature prevent replay? | **Not automatically**; signed anti-replay data and server-side checks are required. |
| Does a signature protect fields outside the signed bytes? | **No**; meaningful fields must be included in the signed scope. |
| Are a SHA-256 checksum and a digital signature equivalent? | **No**; a hash lacks a private key to authenticate origin. |
| Do HMAC and signatures share the same key distribution model? | **No**; HMAC uses a shared key, while signatures use private/public keys. |
| Does a parseable X.509 certificate mean it is trusted? | **No**; trust path validation and appropriate constraints are required. |
| Does a valid signature prove a specific individual manually acted? | **No**; evidence of key control, procedures, and related factors is needed. |

## 12. Common mistakes when learning and implementing

- **“Signing means encrypting with the private key.”** Wrong model; use `Signature` and standard schemes, never hand-roll signing algorithms.
- **Self-signing and trusting the self-supplied public key.** Only validates a key pair supplied by the request; proves no authorized source.
- **Omitting business fields from the signature.** A signature does not protect currency, tenant, account, expiry, or action if they are outside the signed bytes.
- **Signing and verifying differently serialized strings.** Byte mismatches cause verify to return false even when objects look alike; define canonical formatting clearly.
- **Using a signing key with the wrong algorithm/parameters.** Mismatches in Ed25519/ECDSA/RSA-PSS, signature encoding, or hash cause verification failure.
- **Failing to distinguish format errors from valid signatures.** `Signature.verify` may return false or throw an exception; neither should be accepted.
- **Treating verification success as sufficient to execute.** Policy, signing permissions, anti-replay, expiration, and business checks are still required.
- **Confusing non-repudiation with an absolute guarantee.** Private keys can be shared, stolen, or a signing service abused.
- **Failing to protect the private key.** Placing keys in repos, logs, container images, CI artifacts, or world-readable files undermines source authentication.
- **Ignoring key rotation/revocation.** Accepting revoked or unauthorized keys indefinitely.
- **Calling `Signature.update` on chunks out of order.** A signature binds to the exact byte concatenation.
- **Confusing signature with confidentiality.** Signed data can be read; protect confidentiality independently.

## 13. Self-check questions and hands-on exercises

1. If a sender generates a key pair and sends `message, signature, publicKey`, what **does** `verify == true` prove and what does it **not** yet prove?
2. If one byte of `amount` is changed while keeping the old signature, how does verification with the legitimate public key behave? Why?
3. Two systems use the same JSON information, but one reorders fields before verification. What error can occur? How should canonical bytes be defined?
4. Why must `currency`, `tenantId`, `operation`, and `expiresAt` be signed if they affect permissions or processing outcomes?
5. A verifier possesses the public key but not the private key. Can they verify a signature? Can they create a valid new signature?
6. How do SHA-256 digest, HMAC-SHA256, and Ed25519 differ in key requirements and source authentication?
7. A validly signed record from yesterday is replayed today. Why might `Signature.verify` still return true, and what must the application add?
8. An X.509 certificate contains a public key but was issued by an untrusted CA. Is `Signature.verify == true` enough to bind identity?
9. Why does a compromised private key undermine conclusions about signing origin even when Ed25519 functions correctly?
10. Why does a valid signature **not** replace authorization checks or automatically guarantee confidentiality?

**Exercise 1:** Run `DigitalSignatureDemo`, flip the first/last byte of the message; confirm verify returns false. Change `"amount=120000"` to `"amount=120001"` before verifying while keeping the old signature.

**Exercise 2:** Extend the message with `tenantId`, `currency`, and `expiresAt` and serialize it in an unambiguous format; write tests where altering any field invalidates the signature. Ensure sender and receiver share test vectors with identical UTF-8 bytes.

**Exercise 3:** Simulate a key registry with two public keys for two different partners. Only allow partner A to use public key A to sign `orders`. Verifying with key B must fail or be rejected by policy; prevent the sender from arbitrarily swapping keys.

**Exercise 4:** Add `requestId` and `expiresAt` to the signed content and create a state cache tracking processed requests; observe that `verify` does not automatically detect duplicates, while the application can reject the second replay attempt.

## 14. Official references

- [Signature — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html): `getInstance`, `initSign`, `initVerify`, `update`, `sign`, `verify`, errors, and lifecycle.
- [KeyPairGenerator — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyPairGenerator.html): generating public/private key pairs.
- [Java Security Standard Algorithm Names — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): algorithm names such as `Ed25519`, `SHA256withECDSA`, and `RSASSA-PSS` by provider/spec.
- [X509Certificate — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509Certificate.html): accessing the public key and certificate attributes; not a complete trust-chain check.
- [CertPathValidator — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html): validating a certification path to a trust anchor with appropriate policy.
- [JCA Reference Guide — Java SE 17](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): provider architecture, public key cryptography, and the signature engine.
