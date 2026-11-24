# 9.4 RSA PKCS#1 v1.5, RSASSA-PSS, ECDSA, and EdDSA

A digital signature is an asymmetric cryptographic mechanism enabling a recipient to check whether a byte sequence remains intact and was signed by the private key corresponding to a **trusted public key**. In Java applications, four key choices are **RSA PKCS#1 v1.5 signature**, **RSASSA-PSS**, **ECDSA**, and **EdDSA**. All use a private key to sign and a public key to verify, yet they are **not interchangeable**: hash algorithms, parameters, key types, signature formats, and verification rules differ.

This lesson explains their strengths and limitations in full, how to choose a scheme, programming with **java.security.Signature** on Java 17+, interoperability issues between Java and other systems, and hands-on practice with two standalone programs. Since this topic belongs to **digital signatures**, “RSA PKCS#1 v1.5” here refers strictly to **RSASSA-PKCS1-v1_5 for signing**, not **RSAES-PKCS1-v1_5 for encryption**.

## 1. Signing and verification model

~~~text
                  SIGNER                              RECEIVER
message bytes M, private key SK                message bytes M', public key PK
            |                                              |
            v                                              v
  Signature.initSign(SK)                         Signature.initVerify(PK)
  Signature.update(M)                            Signature.update(M')
  Signature.sign() -> S                          Signature.verify(S)
            |                                              |
            +------------- send M and S ------------------>|
                                                           |
                                         true: valid per key/profile
                                         false: must not be accepted
~~~

A valid signature only has value when the **public key is verified to belong to the right entity**. If the sender supplies an unauthenticated public key alongside the message and signature, `verify == true` only proves the signature matches the **key chosen by the sender**. You must authenticate keys from valid certificates, trusted configuration, trusted JWKS, or controlled key-distribution workflows.

**Digital signatures support:**

- **Integrity:** altering a byte of the message normally invalidates the old signature.
- **Origin authentication:** provides basis to trust the message was signed by the private key matching the authenticated public key.
- **Technical evidence:** useful for verifying software packages, notices, and documents; accountability/legal weight also depends on key governance, identity, timestamps, and procedures.

**Signatures do not automatically provide:** content confidentiality, operation authorization, replay protection, or guaranteed proof of signing time. Combine them with TLS, authorization, validity windows, transaction IDs, and key management procedures depending on the problem.

### 1.1. Distinguishing hash, MAC, and signature

| Mechanism | Key | Property | Limitation |
| --- | --- | --- | --- |
| SHA-256 | None | Fingerprint of data | Anyone altering data can recompute the hash; no source authentication. |
| HMAC-SHA256 | Shared secret | Authenticates a party knowing the secret and detects message edits | Both sides share the secret, so it cannot distinguish who created the tag; does not encrypt. |
| RSA/ECDSA/EdDSA signature | Private key signs, public key verifies | Integrity and binding to an identity-authenticated private key | Does not keep message secret; does not block replay by itself. |
| AES-GCM | Symmetric key | Plaintext confidentiality and ciphertext/AAD authentication | Not a public-key signature. |

With a randomized signature scheme, signing the same message twice can produce two signatures with **different bytes that are both valid**. Always use **Signature.verify**; never compare a received signature with a newly generated one using `Arrays.equals`.

## 2. Comparing the four schemes

| Scheme | Primitive / key | JCA Signature name | Characteristics |
| --- | --- | --- | --- |
| **RSASSA-PKCS1-v1_5** | RSA | **SHA256withRSA** | Hash + DigestInfo + EMSA-PKCS1-v1_5 padding. Deterministic signature for message/key. Common in existing systems. |
| **RSASSA-PSS** | RSA | **RSASSA-PSS** | PSS padding uses salt and MGF; hash/MGF/saltLength/trailer must match. Generally preferred for new RSA systems. |
| **ECDSA** | EC Weierstrass curve (e.g., P-256) | **SHA256withECDSA** | Signature is an integer pair `(r,s)`; signing nonce `k` must be handled securely; has DER and P1363 encodings. |
| **EdDSA** | Edwards curves (Ed25519, Ed448) | **Ed25519**, **Ed448** | Pure EdDSA is deterministic per key/message, compact output; pure/prehash/context variants must not be conflated. |

Comparable sizes often cited are **RSA-3072, ECDSA P-256, and Ed25519** at roughly **128-bit** classical security, though CPU cost, key/signature sizes, and support depend on providers, protocols, and policies. Never infer from output length alone that an implementation or production key is secure.

### 2.1. What must match between both sides?

A Java signer and a Go, Node.js, OpenSSL, or another Java provider verifier succeed when both share the exact same contract:

1. Scheme **v1.5/PSS/ECDSA/EdDSA**; same hash and variant.
2. Public key/curve/key ID for the right entity, with the corresponding private key protected.
3. Scheme-specific parameters (PSS hash, MGF, saltLength, trailer; ECDSA curve; Ed25519/Ed448).
4. **Signed bytes**: UTF-8, canonical JSON, raw body, newlines, field order, and exact delimiters.
5. Signature encoding **DER, P1363, RSA raw bytes, Ed25519 raw bytes** matching the protocol.
6. Envelope/version and extra checks such as timestamp, issuer, key usage, and replay.

Matching the algorithm name alone is **not enough** if input bytes or encoding differ.

## 3. RSASSA-PKCS1-v1_5: RSA signatures with classic padding

### 3.1. Mechanism

When using **SHA256withRSA**, JCA executes the RSASSA-PKCS1-v1_5 signature scheme:

1. Hash the exact message bytes with **SHA-256**.
2. Place the hash and algorithm identifier into an ASN.1 DER **DigestInfo** structure.
3. Apply **EMSA-PKCS1-v1_5** to build an encoded message with strictly checked padding structure.
4. Perform the RSA signing operation with the **private key**; verification executes the inverse check with the public key.

~~~text
M -> SHA-256(M) -> DigestInfo
                   |
                   v
           EMSA-PKCS1-v1_5 encoding
                   |
                   v
             RSA signature
~~~

Given the same key and input bytes, the scheme produces the same mathematical signature; implementations may use RSA blinding during computation without altering the final output. An RSA signature has size equal to the **modulus** size rounded up to bytes—for example, RSA-3072 produces **384 bytes**.

### 3.2. Why not use Cipher with a private key?

**RSAES-PKCS1-v1_5** and **RSASSA-PKCS1-v1_5** use different padding rules. Writing **Cipher.getInstance("RSA/ECB/PKCS1Padding")**, “encrypting” a hash with the private key, and comparing manually is not how a standardized, secure signature scheme is implemented. Use **Signature.getInstance("SHA256withRSA")** so the provider handles hash identifier, padding, error checking, and signing/verification math properly.

### 3.3. Where should it be used?

- Supporting legacy protocols with a clearly specified **RSASSA-PKCS1-v1_5** profile.
- Existing systems whose providers/keys/certs only support the compatibility profile.
- For new RSA designs, consider **RSASSA-PSS** if both sides support it. RFC 8017 recommends PSS for new RSA applications within its scope and retains PKCS#1 v1.5 for compatibility.

Use an explicit hash algorithm name like **SHA256withRSA**; never pick **SHA1withRSA** or **MD5withRSA** for new schemes. Verifiers must strictly validate the full padding structure rather than writing custom parsers that “check the hash at the end of the block.”

## 4. RSASSA-PSS: RSA signatures with salt and mask generation

RSA-PSS uses **EMSA-PSS** to construct an encoded message from the message hash, a salt, and a **mask generation function (MGF)**. The salt in PSS is a per-signature parameter, **distinct from a password-hashing salt**. Under standard profiles, the PSS salt does not need to be stored separately beside the signature; the verifier checks it within the encoded message structure.

~~~text
message M ----> Hash(M) --------+
                               |
random salt -------------------+--> EMSA-PSS-ENCODE
                                    (MGF1, saltLength, trailer)
                                                |
                                                v
                                      RSA private-key operation
                                                |
                                                v
                                           PSS signature
~~~

PSS normally produces **different signatures** when signing the same message/key because the salt varies; all still verify cleanly under the same parameter profile.

### 4.1. Parameters that must be pinned precisely

| Parameter | Illustrative profile | Meaning |
| --- | --- | --- |
| Hash | **SHA-256** | Message hash used in PSS. |
| MGF | **MGF1** | Mask generation function. |
| MGF digest | **SHA-256** | Hash used by MGF1; must be declared separately. |
| Salt length | **32 bytes** | Typically equals SHA-256 output in this profile; not universal across all profiles. |
| Trailer field | **1** | JCA parameter value corresponding to trailer `0xBC`. |
| RSA modulus | 3072 bits | Sufficient RSA key size for the chosen profile. |

Example inside a method given `rsaPrivateKey` and `messageBytes`:

~~~java
PSSParameterSpec pss = new PSSParameterSpec(
        "SHA-256", "MGF1", MGF1ParameterSpec.SHA256, 32, 1);

Signature signer = Signature.getInstance("RSASSA-PSS");
signer.setParameter(pss);
signer.initSign(rsaPrivateKey);
signer.update(messageBytes);
byte[] signature = signer.sign();
~~~

This is an **illustrative snippet**, not a standalone Java class; it requires importing `java.security.*` and `java.security.spec.*`. Complete runnable code appears in the hands-on section.

In Java, **PSSParameterSpec** takes parameters in order: **digestAlgorithm, mgfAlgorithm, mgfParameters, saltLen, trailerField**. **RSASSA-PSS** is only the algorithm name and is **not sufficient** by itself to specify SHA-256/MGF1-SHA256/salt 32/trailer 1. Configure all parameters explicitly on both signing and verifying sides, storing profiles by version and key ID; do not rely on provider defaults.

### 4.2. Never auto-fallback PSS parameters

If a signature was created with `saltLength=32` while the verifier expects `saltLength=20`, verification must fail. Depending on the provider, you may get **verify(false)** or a parameter exception. Never try decreasing salt lengths or falling back to v1.5 until something passes. If multiple legacy profiles must be supported, the server must enforce a **fixed allowlist per key/version**, never letting an unauthenticated message dictate security levels.

### 4.3. Using the same RSA key pair for PSS and v1.5?

An RSA key may be compatible with both schemes if key usage and provider allow, yet **the signatures are incompatible**. Designs should separate or bind **key ID ↔ scheme/hash/params/purpose** to prevent algorithm confusion. An HSM may block certain schemes/salt lengths even though the key is mathematically RSA.

## 5. ECDSA: signatures over elliptic curves

### 5.1. Curve, hash, and signing nonce

**ECDSA** uses a private scalar and a public point on a **Weierstrass elliptic curve**. A common profile:

- Key algorithm: **EC**.
- Curve: **secp256r1** (NIST P-256).
- Hash: **SHA-256**.
- Signature algorithm: **SHA256withECDSA**.
- Mathematical signature: a pair of integers **(r,s)**.

When creating a signature, ECDSA requires a **signing nonce k**, kept secret and generated strictly per algorithm rules. **Reusing k across different messages under the same private key, or generating predictable/biased k**, can leak the private key. Never implement nonces with timestamps, `Random`, or application counters; rely on a vetted cryptographic provider. Some ECDSA implementations use deterministic nonces per RFC 6979, though Java does not guarantee every provider signs deterministically per RFC 6979.

~~~text
message M + private key d + nonce k on curve
              |
              v
       ECDSA signature (r,s)
              |
              v
   encode r,s as DER or P1363 bytes
~~~

**Do not hash the message beforehand** when calling **Signature.getInstance("SHA256withECDSA")**, because that name already includes SHA-256. Feeding `SHA256(message)` into `update` signs a **different message** and causes double-hashing incompatible with standard profiles.

Illustrative snippet inside a method given `messageBytes`, importing `java.security.*` and `java.security.spec.*`:

~~~java
KeyPairGenerator gen = KeyPairGenerator.getInstance("EC");
gen.initialize(new ECGenParameterSpec("secp256r1"));
KeyPair keys = gen.generateKeyPair();

Signature signer = Signature.getInstance("SHA256withECDSA");
signer.initSign(keys.getPrivate());
signer.update(messageBytes);
byte[] derSignature = signer.sign();
~~~

**The curve matters:** a P-256 public key is not interchangeable with curve P-384 or Ed25519. Do not assume any key labeled “EC” works with every curve/profile. `Signature.verify` needs the public key matching the scheme/curve and the exact message bytes.

### 5.2. Two encodings of ECDSA signatures: DER and IEEE P1363

This is a very frequent source of cross-system bugs. The mathematical pair `(r,s)` can be encoded as:

| Encoding | Structure | P-256 | Java Signature name |
| --- | --- | --- | --- |
| **ASN.1 DER** | `SEQUENCE` containing two DER `INTEGER`s `r` and `s` | Length typically around 70–72 bytes, **variable** | **SHA256withECDSA** |
| **IEEE P1363** | Two fixed-width big-endian integers concatenated **r\|\|s** | **32 bytes r + 32 bytes s = 64 bytes** | **SHA256withECDSAinP1363Format** |

DER `INTEGER` uses signed representation and may require a leading `0x00` byte to avoid being interpreted as negative; thus you **cannot split a DER signature in half** to extract `r` and `s`. DER also carries `SEQUENCE` and length bytes. Use a strict ASN.1 parser when converting encodings, or choose the JCA algorithm name with **inP1363Format** when both sides support it.

JWS **ES256** in JOSE uses ECDSA P-256 + SHA-256, but the on-wire signature is **64-byte raw P1363**; Java's **SHA256withECDSA** normally outputs DER. Unless both sides specify the format clearly, verification will fail even with the right key, curve, and message.

### 5.3. Non-uniqueness and the low-S rule

In some ECDSA profiles, both `(r,s)` and `(r,n−s)` can be mathematically valid signatures for the same message (where `n` is the group order). Some protocols enforce **low-S canonicalization** to constrain signature variants. Do not assume every Java provider's `Signature.verify` automatically enforces this rule. If a protocol requires low-S, check it per **specific protocol rules** and include negative tests.

## 6. EdDSA: Ed25519 and Ed448

### 6.1. How does EdDSA differ from ECDSA?

**EdDSA** (RFC 8032) uses Edwards curves. Two prominent profiles:

| Profile | Curve | Raw public key (algorithm) | Signature | Notes |
| --- | --- | --- | --- | --- |
| **Ed25519** | edwards25519 | 32 bytes | 64 bytes | Classical security level around 128-bit per profile. |
| **Ed448** | edwards448 | 57 bytes | 114 bytes | Higher classical security level, around 224-bit. |

These are **RFC raw key** sizes; keys stored in **SubjectPublicKeyInfo/X.509** carry additional ASN.1 metadata so encoded byte lengths differ from raw key sizes. **Ed25519** is not **X25519**: Ed25519 is for signatures, X25519 is for key agreement. Having “25519” in both names does not make the keys or algorithms interchangeable.

**Deterministic pure EdDSA:** signing the same message bytes with the same private key under pure Ed25519 produces identical signature bytes. This property eliminates the ECDSA-style random-nonce failure class, yet still requires a **CSPRNG for key generation**, private key protection, implementation safety, and public-key origin authentication.

### 6.2. Using it in Java 17+

Illustrative snippet inside a method given `messageBytes` and importing `java.security.*`:

~~~java
KeyPairGenerator gen = KeyPairGenerator.getInstance("Ed25519");
KeyPair pair = gen.generateKeyPair();

Signature signer = Signature.getInstance("Ed25519");
signer.initSign(pair.getPrivate());
signer.update(messageBytes);
byte[] signature = signer.sign();

Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(pair.getPublic());
verifier.update(messageBytes);
boolean valid = verifier.verify(signature);
~~~

There is no need to declare **SHA256withEdDSA** or **PSSParameterSpec**. The name **Ed25519** already identifies the complete scheme. You can check support for **Ed448** under the standard Java name if provider and policy permit; never silently switch between Ed25519 and Ed448 within a protocol.

### 6.3. Pure Ed25519, Ed25519ph, and Ed25519ctx

RFC 8032 also defines:

- **Ed25519 (pure):** signs the message per the standard profile.
- **Ed25519ph:** prehashed variant with specific RFC domain separation/rules.
- **Ed25519ctx:** contextualized variant taking a context string into the signing operation.

They are **not mutually compatible**. In particular, computing **SHA-512(message)** and calling **Signature("Ed25519")** does not turn signing into Ed25519ph; it simply signs a different message using **pure Ed25519**. If a protocol truly requires ph/ctx, use an implementation supporting that exact variant.

**Deterministic Ed25519** does not mean verifying a signature by re-signing. If the recipient does not hold the private key, they still use **Signature.verify** with the public key. Only the private-key holder may call `initSign`.

## 7. Parameters, sizes, and formats must match

| Profile | Key generation | JCA signing | Signature form | What to preserve |
| --- | --- | --- | --- | --- |
| **RSA-v1.5 + SHA-256** | RSA 3072-bit | SHA256withRSA | 384 bytes for RSA-3072 | v1.5 scheme, digest, key ID. |
| **RSA-PSS + SHA-256** | RSA 3072-bit | RSASSA-PSS | 384 bytes for RSA-3072 | SHA-256, MGF1/SHA-256, 32-byte salt, trailer 1. |
| **ECDSA P-256 DER** | EC / secp256r1 | SHA256withECDSA | ASN.1 DER, variable length | Curve P-256, SHA-256, DER. |
| **ECDSA P-256 P1363** | EC / secp256r1 | SHA256withECDSAinP1363Format | Raw r\|\|s = 64 bytes | Curve P-256, SHA-256, P1363. |
| **Ed25519 pure** | Ed25519 | Ed25519 | 64 bytes | Exact pure Ed25519 variant, message bytes. |
| **Ed448 pure** | Ed448 | Ed448 | 114 bytes | Exact pure Ed448 variant, message bytes. |

RSA sizes are given in **modulus bits**, so RSA-3072 produces a 384-**byte** signature, not 3072 bytes. With ECDSA, DER length can vary across signatures; that length is not a criterion for strong vs. weak keys.

### 7.1. Scheme names are not key algorithm names

In Java:

- **KeyPairGenerator("RSA")** generates RSA keys; **Signature("SHA256withRSA")** or **Signature("RSASSA-PSS")** apply different schemes to suitable RSA keys.
- **KeyPairGenerator("EC")** with **ECGenParameterSpec("secp256r1")** generates an EC key; **Signature("SHA256withECDSA")** signs.
- **KeyPairGenerator("Ed25519")** generates an Ed25519 key; **Signature("Ed25519")** signs.
- **X25519** belongs to `KeyAgreement`, not `Signature`.

Never use “RSA” or “EC” alone as a substitute for a complete signature algorithm contract.

## 8. Does the public key belong to the right identity?

**Signature.verify(true)** only states that verification succeeded **under the supplied public key**. If a client sends a self-generated public key and the server immediately trusts it as a bank or payment service, verification provides zero identity authentication.

Trusted key sources are typically:

1. An X.509 certificate with verified certification path, key usage, validity period, identity, and trust policy.
2. JWKS or a key endpoint from a configured issuer accessed over an appropriate channel, with key ID and rotation rules.
3. Public keys pinned per partner in deployment configuration, a secret manager, or an access-controlled config store.
4. KMS/HSM managing the signing private key, while verifiers obtain the corresponding public key over a trusted channel.

**Key formats and signature formats are distinct.**

| Data kind | Common API or encoding | What to remember |
| --- | --- | --- |
| Exported/imported public key | **X509EncodedKeySpec**, X.509 SubjectPublicKeyInfo | `BEGIN PUBLIC KEY` PEM usually wraps Base64 SPKI; not a full certificate. |
| Exportable private key | **PKCS8EncodedKeySpec** | Highly sensitive private key; may be non-exportable from HSM/KMS. |
| X.509 certificate | **CertificateFactory**, `X509Certificate` | Requires chain/purpose/identity validation, not just extracting the public key. |
| ECDSA DER signature | **Signature("SHA256withECDSA")** | ASN.1 `(r,s)`, not a public key encoding. |
| Ed25519 signature | **Signature("Ed25519")** | 64-byte raw signature; raw keys have a different format and length. |

**Key.getEncoded() may return null** for non-exportable keys on hardware providers. Never assume all Java keys are portable across providers. For exportable keys, import must use the matching **KeyFactory**, format, algorithm, and policy.

## 9. Signed bytes determine the verification outcome

Java **Signature.update(byte[])** takes the actual byte sequence; two Java objects with identical business meaning do not necessarily produce identical bytes.

~~~text
JSON A: {"order":42,"amount":250000}
JSON B: { "amount": 250000, "order": 42 }

Both representations can describe the same object,
but byte sequences A and B differ.
A signature over A does not automatically verify on B.
~~~

Typical errors:

- Signer uses **UTF-8**, verifier converts `String` using another charset.
- Signer signs the **raw HTTP body**, receiver parses JSON and re-serializes it.
- One side preserves a **trailing newline**, the other strips it.
- One side uses Unicode **NFC** normalization, the other keeps combining characters.
- Timestamp, tenant, action, or key ID headers are **outside the signed bytes**, yet the server trusts them.
- Receiver treats **Base64 signature text** as raw signature bytes instead of decoding properly.
- Signer manually runs **SHA-256 on the message first** even though the `Signature` algorithm already hashes.

Define **canonicalization**, field order, delimiters, format version, timestamp encoding, and exact byte sequence per protocol. For webhooks signing the raw request body, keep the raw bytes intact. Never try multiple serialization variants until one happens to verify true.

### 9.1. JWS/JWT and Java signatures

| JWS `alg` | Scheme | Java mapping |
| --- | --- | --- |
| **RS256** | RSA v1.5 + SHA-256 | **SHA256withRSA** |
| **PS256** | RSA-PSS + SHA-256 | **RSASSA-PSS** with SHA-256 / MGF1 SHA-256 / 32-byte salt profile |
| **ES256** | ECDSA P-256 + SHA-256 | **SHA256withECDSAinP1363Format** for wire raw `r\|\|s` if provider supports it; standard DER must be converted properly |
| **EdDSA** with Ed25519 | Ed25519 | **Signature.getInstance("Ed25519")** |

A JWS signature protects the **exact JWS signing input bytes**, typically the encoded header, a dot, and the encoded payload. Never sign just the JSON payload and call it a JWS signature. When implementing JWT, use a **maintained JOSE/JWT library** with an algorithm allowlist, key ID, issuer, audience, expiry, and token policy rather than hand-rolling parsers or trusting an `alg` header from an untrusted source.

Once an expected algorithm and public key are selected by server policy, **never let an unauthenticated message trigger algorithm fallback** (e.g., from PS256 down to RS256 or `"none"`) or arbitrarily redirect the key source.

## 10. Java 17+: practicing signing and verifying the four schemes

The first program generates three key pairs for one run: **RSA-3072**, **EC P-256**, and **Ed25519**. It signs the exact bytes of **order=42;amount=250000** and then tests verifying against a tampered message **order=42;amount=250001**. Each sign and verify call uses a **separate Signature instance** to avoid mixing state.

The final section also tests deterministic pure **Ed25519** and an **RSA-PSS verification with the wrong saltLength**. So that stdout does not depend on changing signature bytes, the program prints booleans and profile labels.

Create **`SignatureSchemesDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;
import java.util.Arrays;

public class SignatureSchemesDemo {
    private static final byte[] MESSAGE =
            "order=42;amount=250000".getBytes(StandardCharsets.UTF_8);
    private static final byte[] ALTERED =
            "order=42;amount=250001".getBytes(StandardCharsets.UTF_8);
    private static final PSSParameterSpec PSS_SHA256 =
            new PSSParameterSpec(
                    "SHA-256", "MGF1", MGF1ParameterSpec.SHA256, 32, 1);

    private static Signature engine(String algorithm, boolean pss)
            throws Exception {
        Signature signature = Signature.getInstance(algorithm);
        if (pss) {
            signature.setParameter(PSS_SHA256);
        }
        return signature;
    }

    private static byte[] sign(String algorithm, boolean pss,
            KeyPair keys, byte[] message) throws Exception {
        Signature signature = engine(algorithm, pss);
        signature.initSign(keys.getPrivate());
        signature.update(message);
        return signature.sign();
    }

    private static boolean verify(String algorithm, boolean pss,
            KeyPair keys, byte[] message, byte[] signed) throws Exception {
        Signature verifier = engine(algorithm, pss);
        verifier.initVerify(keys.getPublic());
        verifier.update(message);
        return verifier.verify(signed);
    }

    private static void check(String label, String algorithm, boolean pss,
            KeyPair keys) throws Exception {
        byte[] signed = sign(algorithm, pss, keys, MESSAGE);
        boolean ok = verify(algorithm, pss, keys, MESSAGE, signed);
        boolean changed = verify(algorithm, pss, keys, ALTERED, signed);
        System.out.println(label + ": valid=" + ok +
                ", modified content=" + changed);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator rsa = KeyPairGenerator.getInstance("RSA");
        rsa.initialize(3072);
        KeyPair rsaKeys = rsa.generateKeyPair();

        KeyPairGenerator ec = KeyPairGenerator.getInstance("EC");
        ec.initialize(new ECGenParameterSpec("secp256r1"));
        KeyPair ecKeys = ec.generateKeyPair();

        KeyPairGenerator ed = KeyPairGenerator.getInstance("Ed25519");
        KeyPair edKeys = ed.generateKeyPair();

        check("PKCS1-v1_5", "SHA256withRSA", false, rsaKeys);
        check("PSS", "RSASSA-PSS", true, rsaKeys);
        check("ECDSA", "SHA256withECDSA", false, ecKeys);
        check("Ed25519", "Ed25519", false, edKeys);

        byte[] signedEd = sign("Ed25519", false, edKeys, MESSAGE);
        byte[] signedAgain = sign("Ed25519", false, edKeys, MESSAGE);
        System.out.println("Ed25519 repeats same signature: " +
                Arrays.equals(signedEd, signedAgain));

        Signature incompatiblePss = Signature.getInstance("RSASSA-PSS");
        incompatiblePss.setParameter(new PSSParameterSpec(
                "SHA-256", "MGF1", MGF1ParameterSpec.SHA256, 20, 1));
        incompatiblePss.initVerify(rsaKeys.getPublic());
        incompatiblePss.update(MESSAGE);
        byte[] pssTag = sign("RSASSA-PSS", true, rsaKeys, MESSAGE);
        System.out.println("PSS wrong salt length: " +
                incompatiblePss.verify(pssTag));
    }
}
~~~

Compile with a JDK supporting the standard Java 17 profiles:

~~~bash
javac --release 17 -encoding UTF-8 SignatureSchemesDemo.java
java SignatureSchemesDemo
~~~

Stdout on a tested JDK/provider:

~~~text
PKCS1-v1_5: valid=true, modified content=false
PSS: valid=true, modified content=false
ECDSA: valid=true, modified content=false
Ed25519: valid=true, modified content=false
Ed25519 repeats same signature: true
PSS wrong salt length: false
~~~

### 10.1. Why is this example instructive?

1. **RSA-v1.5:** `Signature("SHA256withRSA")` combines hash + v1.5 scheme, using an RSA key.
2. **RSA-PSS:** `Signature("RSASSA-PSS")` requires an explicit **PSSParameterSpec**; parameters are set prior to signing or verifying.
3. **ECDSA:** `KeyPairGenerator("EC")` is initialized on **secp256r1**, while `Signature` uses **SHA256withECDSA**.
4. **Ed25519:** `KeyPairGenerator` and `Signature` share the **Ed25519** profile, needing no PSS params.
5. **Tamper test:** modifying message bytes makes verify return false with the same signature and public key.
6. **Deterministic test:** pure Ed25519 with the same key/message yields identical signatures; validity checks must still use `Signature.verify`.
7. **Wrong PSS params:** signer uses 32-byte salt, verifier uses 20-byte salt. On the tested provider, `verify` returns false; another provider may reject the parameters or key with an exception. Never auto-fallback.
8. **Test-only private keys:** keys are generated ephemerally in memory and never printed/written out; production requires `KeyStore`, KMS/HSM, key usage, and public-key trust.

**Limitations:** do not treat a single run as proof that every provider supports all profiles. Fresh keys are generated on each run, so specific signatures will vary; the program prints **check statuses**, not signature bytes. Never use randomly generated demo keys to represent production identity keys.

## 11. Java 17+: testing ECDSA DER and P1363

The second program directly illustrates the difference between **SHA256withECDSA** (DER) and **SHA256withECDSAinP1363Format** (raw `r||s`) on the same EC P-256 key and same message. Each signature is verified using the algorithm with the matching encoding. Never compare the two signatures directly because ECDSA nonces can differ.

Create **`EcdsaFormatDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;

public class EcdsaFormatDemo {
    private static final byte[] MESSAGE =
            "payload-v1".getBytes(StandardCharsets.UTF_8);

    private static byte[] sign(String algorithm, KeyPair pair)
            throws Exception {
        Signature signer = Signature.getInstance(algorithm);
        signer.initSign(pair.getPrivate());
        signer.update(MESSAGE);
        return signer.sign();
    }

    private static boolean verify(
            String algorithm, KeyPair pair, byte[] signed)
            throws Exception {
        Signature verifier = Signature.getInstance(algorithm);
        verifier.initVerify(pair.getPublic());
        verifier.update(MESSAGE);
        return verifier.verify(signed);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator gen = KeyPairGenerator.getInstance("EC");
        gen.initialize(new ECGenParameterSpec("secp256r1"));
        KeyPair pair = gen.generateKeyPair();

        byte[] der = sign("SHA256withECDSA", pair);
        byte[] raw = sign("SHA256withECDSAinP1363Format", pair);

        System.out.println("DER ECDSA valid: " +
                verify("SHA256withECDSA", pair, der));
        System.out.println("P1363 ECDSA valid: " +
                verify("SHA256withECDSAinP1363Format", pair, raw));
        System.out.println("P1363 P-256 is 64 bytes: " +
                (raw.length == 64));
        System.out.println("DER starts with ASN.1 SEQUENCE: " +
                ((der[0] & 0xff) == 0x30));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 EcdsaFormatDemo.java
java EcdsaFormatDemo
~~~

Stdout:

~~~text
DER ECDSA valid: true
P1363 ECDSA valid: true
P1363 P-256 is 64 bytes: true
DER starts with ASN.1 SEQUENCE: true
~~~

### 11.1. Proper understanding

- **SHA256withECDSA** produces/accepts **ASN.1 DER** signatures with `r`/`s` as `INTEGER`s, so total length can vary.
- **SHA256withECDSAinP1363Format** produces/accepts **raw r||s**. For P-256, each integer is 32 bytes, so the signature is **64 bytes** long.
- The leading DER `SEQUENCE` tag byte is **0x30**, yet checking only the first byte is **not an ASN.1 validator** and must not be used as security validation. The provider's `Signature.verify` performs the verification.
- When integrating with external systems expecting raw ES256, never slice a DER signature in half; use a proper DER/P1363 conversion library or select the P1363 API directly.
- Never assume two ECDSA signing calls on the same message return identical signature bytes.

**Both programs above are complete examples with `main`** compiled under **javac --release 17**; only the small code snippets in the theory sections are in-method fragments.

## 12. JCA providers, key management, and compatibility

**JCA/JCE is an abstraction layer**: `Signature`, `KeyPairGenerator`, and `KeyFactory` are engine APIs; providers implement the algorithms. Sharing an algorithm name does not guarantee every JVM, provider, or HSM supports the **same key types, curves, PSS params, encodings, and throughput**.

### 12.1. Errors providers can return

| Java symptom | Possible cause | How to check |
| --- | --- | --- |
| **NoSuchAlgorithmException** | Provider/JDK does not offer the `Signature` or `KeyPairGenerator` name | Confirm Java version, provider order, standard name, and policy-allowed algorithms. |
| **InvalidAlgorithmParameterException** | Curve, saltLength, `PSSParameterSpec`, or other parameter unsupported | Cross-check standard profile and provider/HSM capabilities. |
| **InvalidKeyException** | Wrong key type, weak key, foreign provider key, or disallowed key usage | Check key type, key size, alias, HSM permissions, and policy. |
| **SignatureException** | Bad format / uninitialized signature / invalid operation | Check DER/P1363, bytes, init mode, input length, and provider. |
| **verify(false)** | Wrong message, key, params, or syntactically valid but non-matching signature | Locate the exact test vector difference; do not automatically assume an attack. |
| **Errors only under load** | Shared mutable `Signature`, provider lock/session exhaustion, key rotated mid-request | Isolate one engine per operation, manage HSM sessions and consistent key versions. |

When diagnosing in a trusted environment, **Signature.getProvider()** and **Signature.getAlgorithm()** reveal the chosen implementation and name; note that some engines/providers choose implementation details upon `init` with a key. Log algorithm names/key IDs per policy while avoiding logging private keys, keystore passwords, raw sensitive messages, or sensitive protocol signatures.

### 12.2. Key management rules

1. **Generate keys** with approved curves, sizes, and random sources; RSA sizes and EC curves must comply with policy.
2. **Store private keys** in appropriate protection (protected `KeyStore`, HSM/KMS, secret manager) with least privilege; never commit private keys to repositories or container images.
3. **Distribute public keys** over authenticated channels bound to the right issuer/partner; never accept arbitrary keys sent in requests.
4. **Bind key ID ↔ algorithm/scheme/hash/curve/params**; during key rotation, records/tokens must identify the version for accurate verification.
5. **Separate key usage** across signatures, key agreement, and encryption when policy requires. Do not use Ed25519 as X25519 or let clients dictate arbitrary operations on an RSA private key.
6. **Rotate and revoke** with clear acceptance windows for old signatures. An old signature can verify mathematically yet still be rejected by expiration or revocation.
7. **Protect key operations** with rate limiting, anomaly monitoring, and compromise response procedures.

### 12.3. Why check the public key when using certificates?

An X.509 certificate holds a public key and identity information, yet merely extracting the public key and calling `Signature.verify` **does not mean the certificate is trusted**. You must validate the certificate path against a trust anchor, validity period, intended usage, revocation per policy, and expected service/subject identity. For JWS/JWT, issuer/audience and trusted JWKS are part of a separate workflow.

## 13. Signature is a stateful engine: never share an instance across threads

A **java.security.Signature** object mutates state across **initSign/initVerify → update → sign/verify**. If placed in a `static` field of a web singleton with concurrent requests, operations from A and B can interleave:

~~~text
Unsafe:
shared.initVerify(keyA)
shared.update(messageA)
                           shared.initVerify(keyB)
                           shared.update(messageB)
shared.verify(sigA)  -> state no longer belongs to messageA/keyA

Clean pattern:
request A -> dedicated Signature instance -> initVerify A -> update A -> verify A
request B -> dedicated Signature instance -> initVerify B -> update B -> verify B
~~~

Create **a dedicated Signature instance per signing or verification call**, as shown in both examples. Never extrapolate that because `SecureRandom` is thread-safe, `Signature` can be shared too. Synchronizing individual methods **does not protect the whole operation sequence**; synchronizing the entire sequence defeats concurrency.

A public key object or key handle may be reusable if the provider allows it, which is completely different from sharing an **engine holding message state**. With HSMs, session pooling, timeouts, and backpressure are also needed; never “optimize” by uncontrolled reuse of mutable `Signature` objects.

## 14. Validate message and signature before business processing

A workflow receiving signed webhooks, release packages, or tokens can include:

1. **Enforce request size limits**, parse envelope/version, and decode signature bytes and key ID in the expected format.
2. Determine the **expected issuer/partner and allowed algorithms** from server configuration. Never let `alg` from unauthenticated data widen the allowlist.
3. Fetch the **trusted public key** for the allowed key ID; check key status and usage permissions.
4. Prepare the **message bytes** per protocol specification, preserving raw body or canonical encoding; protect metadata affecting business logic.
5. Use **Signature.getInstance** with the right algorithm/params/encoding, `initVerify`, `update` bytes, and `verify`.
6. If `verify` is false or data/format/algorithm is invalid, **reject**; do not execute transactions or grant privileges.
7. If `verify` is true, check **expiration, issuer, audience, replay/idempotency, authorization, and business state** before taking effect.
8. Log request ID, key ID, profile, and technical reason at permitted detail levels; external responses must not leak secrets or unnecessary internal state.

**Replay warning:** an attacker can resend an identical valid payload and signature. The signature will continue verifying true; the application must enforce freshness, nonces, timestamps, transaction IDs, and idempotency as required. In particular, timestamps or nonces used for replay defense must be bound to the signed bytes or trusted context.

## 15. Scheme selection guidelines

| Problem | Practical choice | Decision criteria |
| --- | --- | --- |
| Integrating with legacy RSA systems | **SHA256withRSA / RSASSA-PKCS1-v1_5** if policy allows | Partner systems support v1.5 profile and have a migration plan. |
| Designing new RSA signature APIs | **RSASSA-PSS** | Both sides agree on SHA/MGF/saltLength/trailer, key size, and provider. |
| ECDSA P-256 ecosystems | **SHA256withECDSA**, DER or P1363 as appropriate | Curve, hash, on-wire encoding, nonce management, and provider. |
| APIs or software packages supporting Ed25519 | **Signature("Ed25519")** | Standard pure Ed25519, key distribution, provider/HSM compatibility. |
| Specific FIPS/PKI/HSM systems | Policy/hardware-approved scheme | Certification, key usage, algorithm, key size, and deployment latency. |

Do not choose from a “newer algorithm is always better” leaderboard; evaluate **mandated protocols, standard recommendations, security requirements, and key protection capabilities**. RSA-PSS is a strong choice for new RSA applications; Ed25519 is compact and convenient for many modern applications, yet cannot replace a fixed RSA/ECDSA profile required by a receiver.

**Never fall back to `NONEwithRSA`, `NONEwithECDSA`, manual hashing before raw signing, or using `Cipher` to emulate `Signature`** merely because two parties hit an interoperability error.

## 16. Essential test suite

| Test case | Input or scenario | Expected outcome |
| --- | --- | --- |
| Matching profile | Message, signature, public key, params match | **verify true**. |
| Modified message | Flip one byte, keep old signature | **verify false**. |
| Modified signature | Flip signature byte or swap signature from another message | Reject or safely handle format error. |
| Wrong public key | Key of same scheme but from a different issuer | Do not accept. |
| PKCS1-v1_5 vs PSS | Sign `SHA256withRSA`, verify `RSASSA-PSS` or vice versa | Do not accept. |
| Wrong PSS salt | Sign `salt=32`, verify `salt=20` | Reject/false or parameter error. |
| Wrong PSS MGF | One side SHA-256 with MGF1-SHA256, other uses MGF1-SHA1 | Do not accept. |
| ECDSA DER vs P1363 | DER sent to verifier expecting raw `r\|\|s` | Reject; apply standard conversion. |
| Malformed ECDSA | Invalid DER `r`/`s`, wrong length | Reject with controlled error, never use a lenient parser. |
| Deterministic Ed25519 | Sign pure Ed25519 twice with same key/message | Identical signature bytes. |
| Wrong Ed25519 variant | Raw message vs arbitrarily prehashed message | Incompatible. |
| Unicode/JSON | Different whitespace, charset, normalization | Old raw-byte signature does not match if bytes change. |
| Provider matrix | Sign Java A, verify Go/OpenSSL/Java B on same vector | Must yield identical results per standard profile. |
| Key rotation | Old/new key ID, revoked key | Accept/reject according to version and policy. |
| Replay | Resend previously valid message+signature | Signature may remain true; business layer must enforce idempotency. |
| Concurrency | Parallel requests with distinct keys/messages | No mixed `Signature` state; controlled throughput. |
| Key permissions | Non-exportable handle or blocked operation | Proper error handling, never use unauthorized private keys. |

**Valuable test vectors** should store original message bytes in hex/files, algorithm, hash, curve/PSS params, test public key, properly encoded signature bytes, and expected result. Re-running them across providers catches interoperability bugs early. Never put real private keys into test repositories.

### 16.1. Interpreting errors accurately

- **verify(false)**: message/key/params/signature did not match in the performed check.
- **NoSuchAlgorithmException / InvalidKeyException**: algorithm or key rejected by the provider; diagnose technically, never downgrade the algorithm.
- **SignatureException**: may stem from engine state, input/encoding, or configuration; do not assume an attack solely from an exception.
- **Certificate/replay/policy failure**: `verify` may be true, yet the system must still reject because identity or authorization is not satisfied.

On signature errors, never log private keys, sensitive raw tokens, secret payloads, or detailed client responses that expose internal state.

## 17. Frequent mistakes

1. **Confusing RSASSA-PKCS1-v1_5 with RSAES-PKCS1-v1_5.** Sign with the `Signature` API, never use `Cipher` to fake an RSA signature.
2. **Using `SHA256withRSA` to verify PSS.** They are different schemes even with the same RSA key.
3. **Omitting complete `PSSParameterSpec`.** Hash/MGF/salt/trailer may differ across providers or senders.
4. **Auto-reducing PSS `saltLength` on verification failure.** That alters security policy outside the protocol.
5. **Choosing `SHA1withRSA`/`MD5withRSA` for new designs.** Do not use weak hashes when stronger profiles exist.
6. **Generating ECDSA nonces with `Random` or timestamps.** Nonce flaws can compromise the private key.
7. **Slicing a DER signature in half and calling it P1363.** ASN.1 DER is not raw `r||s`.
8. **Hashing the message before `SHA256withECDSA` or `Ed25519`.** Produces different input or wrong variant, typically causing mismatches.
9. **Confusing Ed25519 with X25519.** Signatures and key agreement have separate key types and operations.
10. **Treating a client-supplied public key as trusted identity.** `verify == true` does not prove it belongs to a specific partner.
11. **Blindly trusting `alg` inside a JWT.** Without a scheme allowlist and key policy, algorithm confusion occurs.
12. **Failing to sign business metadata.** Tenant/action/timestamp can be altered outside the authenticated scope.
13. **Comparing signatures with `equals` against a freshly generated signature.** PSS/ECDSA can be randomized; `Signature.verify` is the proper check.
14. **Sharing a `Signature` instance in a singleton.** `init`/`update`/`verify` can interleave across threads.
15. **Storing private keys in source code, logs, or public files.** Anyone obtaining the key can produce valid signatures.
16. **Ignoring replay/authorization.** A valid signature does not prove a command is permitted or unprocessed.
17. **Not storing format version, key ID, and params.** Changing providers or rotating keys breaks verification of older data.

## 18. Self-check questions

**Q1.** Does Java **SHA256withRSA** use v1.5 or PSS?  
**Answer:** RSASSA-PKCS1-v1_5 with SHA-256. PSS uses **RSASSA-PSS** and `PSSParameterSpec`.

**Q2.** RSA-PSS SHA-256 signs with `saltLength=32`; verifier uses `saltLength=20` with the matching RSA public key. Should it pass?  
**Answer:** No. **Scheme parameters differ**; it must reject or error per provider without auto-downgrading parameters.

**Q3.** Why can two ECDSA signatures on the same message differ?  
**Answer:** Because of the signing nonce `k`; many implementations choose a fresh `k` per signature. Both can be valid and must be checked via `Signature.verify`.

**Q4.** A JWS ES256 service requires 64-byte raw `r||s`, but Java produces DER. What should you do?  
**Answer:** Choose **SHA256withECDSAinP1363Format** if supported or use a standards-compliant DER/P1363 converter while preserving curve/hash/bytes.

**Q5.** For pure Ed25519, why shouldn't you run `SHA-512(message)` before calling `Signature("Ed25519")`?  
**Answer:** Because Ed25519 already performs its internal hashing. Manual prehashing signs a different message and does not turn it into Ed25519ph.

**Q6.** A server receives a message, signature, and public key from the same client and `verify` returns true; is that enough to treat the client as organization X?  
**Answer:** Not yet. You must verify that the public key is genuinely bound to organization X under trust policy.

**Q7.** A payment packet has a valid signature but is replayed from yesterday; does signature verification block it automatically?  
**Answer:** No. Add timestamp/nonce, transaction ID, freshness, and idempotency bound to the message.

**Q8.** Roughly how long is an RSA-3072 signature?  
**Answer:** **384 bytes** for both RSA v1.5 and PSS. 3072 is the **modulus bit length**.

**Q9.** Can one `Signature` object be used concurrently for both request A and request B?  
**Answer:** No: the object holds `init`/`update`/`sign`/`verify` state. Each task should have its own engine.

**Q10.** How do Ed25519 and X25519 differ?  
**Answer:** Ed25519 is for digital signatures, X25519 is for key exchange; do not treat them as one key type or one protocol.

## 19. Conclusion and references

**PKCS#1 v1.5** addresses RSA signature compatibility with classic profiles; **RSA-PSS** requires exact parameters and is preferred for new RSA applications; **ECDSA** requires secure signing nonces, matching curves, and proper **DER/P1363** formatting; **EdDSA** provides **Ed25519/Ed448** profiles distinct from ECDSA with a deterministic pure variant. All of them only hold value when **message bytes, algorithm/params, public-key trust, private-key protection, and replay/authorization handling** are all right.

Technical references:

- [RFC 8017 — PKCS #1 v2.2, RSASSA-PKCS1-v1_5 and RSASSA-PSS](https://www.rfc-editor.org/rfc/rfc8017.html)
- [RFC 8032 — EdDSA (Ed25519, Ed448)](https://www.rfc-editor.org/rfc/rfc8032.html)
- [NIST FIPS 186-5 — Digital Signature Standard](https://csrc.nist.gov/pubs/fips/186-5/final)
- [Java SE 17 — Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html)
- [Java SE 17 — Signature API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html)
- [Java SE 17 — PSSParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/PSSParameterSpec.html)
- [Java SE 17 — ECGenParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/ECGenParameterSpec.html)
- [RFC 7518 — JWA, RS256/PS256/ES256](https://www.rfc-editor.org/rfc/rfc7518.html)
- [RFC 8037 — EdDSA in JOSE](https://www.rfc-editor.org/rfc/rfc8037.html)