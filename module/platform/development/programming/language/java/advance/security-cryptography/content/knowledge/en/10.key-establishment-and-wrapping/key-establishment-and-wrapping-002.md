# 10.2 DH, ECDH, X25519, and X448 in the KeyAgreement Model

## 1. The Problem: Two Parties Generate the Same Secret Without Sending It

**Key agreement** allows Alice and Bob, each holding a **private key** and exchanging **public keys**, to compute **the same shared secret** over a network. An eavesdropper can see the public keys and exchanged packets, but cannot easily compute the secret if the algorithm, mathematical group, randomness, and implementation meet security requirements.

The Java Cryptography Architecture / Java Cryptography Extension (JCA/JCE) represents this operation via the `javax.crypto.KeyAgreement` engine. The four variants covered in this lesson:

- **DH** (finite-field Diffie–Hellman, often called FFDH): modular exponentiation with group parameters `p, g`.
- **ECDH** (Elliptic-Curve Diffie–Hellman): scalar point multiplication on an elliptic curve, for example `secp256r1`/P-256.
- **X25519**: Diffie–Hellman key exchange function based on Curve25519, designed with the Montgomery ladder; Java implementations typically use JCA algorithm `X25519` or `XDH` with `NamedParameterSpec.X25519`.
- **X448**: similar, using Curve448 and targeting a higher security level; JCA algorithm `X448` or `XDH` with parameter `NamedParameterSpec.X448`.

**What must not be confused:** KeyAgreement **does not encrypt data on its own, does not authenticate the peer on its own, does not issue certificates on its own, and does not automatically produce protocol-safe AES keys**. After obtaining the shared secret, you need a **KDF** with a context identifier (such as HKDF) to derive keys for AES-GCM or a key-encryption key (KEK) used to wrap keys. To defend against a man-in-the-middle (MITM), you must **authenticate public keys, transcript signatures, or peer identity**.

Two-party flow:

```text
 Alice                                               Bob
 private a                                           private b
 public A                                            public B
    |                                                    |
    |---------------------  A  ------------------------->|
    |<--------------------  B  --------------------------|
    |                                                    |
 DH/ECDH/X25519/X448(private a, B)      DH/ECDH/X25519/X448(private b, A)
    |                                                    |
    +--> shared secret S                    shared secret S <--+
                    |                                  |
             HKDF(salt, S, info)               HKDF(salt, S, info)
                    |                                  |
                session key  <-------- equal --------> session key
                    |                                  |
                      AEAD (for example AES-GCM)
```

Keys `a` and `b` are never sent. The letters `A` and `B` in the diagram are **properly formatted encoded public keys**, not the raw shared secret.

## 2. Comparing DH, ECDH, X25519, and X448

| Algorithm | Mathematical group / main parameters | JCA KeyPairGenerator | JCA KeyAgreement | Shared secret in the example |
| --- | --- | --- | --- | --- |
| DH | Finite field with `p, g`; e.g. 2048-bit DH parameters | `"DH"` (alias `"DiffieHellman"`) | `"DH"` | Typically **256 bytes** with 2048-bit parameters |
| ECDH | Named EC curve, e.g. P-256 (`secp256r1`) | `"EC"` + `ECGenParameterSpec("secp256r1")` | `"ECDH"` | **32 bytes** on P-256 in the example provider |
| X25519 | X25519/Curve25519, protocol per RFC 7748 | `"X25519"` + `NamedParameterSpec("X25519")` | `"X25519"` | **32 bytes** |
| X448 | X448/Curve448, per RFC 7748 | `"X448"` + `NamedParameterSpec("X448")` | `"X448"` | **56 bytes** |

The table shows the **output length of the agreement operation**, **not** a mandatory AES key byte count. A KDF can produce an AES-128 (16-byte) or AES-256 (32-byte) key, but **a longer output length does not increase security beyond the entropy/security strength of the input**. For example, X25519 typically targets roughly 128-bit equivalent security; deriving an AES-256 key does not automatically make the entire protocol 256-bit secure.

### 2.1 DH: The Finite-Field Group Must Match

Given a valid DH group with prime `p` and generator `g`, Alice chooses private exponent `a` and outputs `A = g^a mod p`; Bob chooses `b` and outputs `B = g^b mod p`. After receiving each other's public values, both compute the same secret:

```text
Alice: S = B^a mod p = g^(ab) mod p
Bob:   S = A^b mod p = g^(ab) mod p
```

**Requirement:** both sides must use the **same p/g group**, with validation of group security and public values. You cannot generate two random `DHParameterSpec`s independently and expect DH to succeed. With `KeyPairGenerator("DH")`, you can extract the parameters from `((DHPublicKey) alice.getPublic()).getParams()` and initialize the other side's generator with the same parameters. In **production systems**, never blindly trust an arbitrary `p,g` proposed over the network: prefer standardized, sufficiently strong FFDHE groups, validate public keys/subgroups, and bind the params into an authenticated handshake.

**2048-bit DH** is used in the example because it is easy to run on common JDKs; this is the modulus length, not 2048-bit security strength. Systems with higher security requirements may need larger groups or a different algorithm according to policy.

### 2.2 ECDH: Same Curve, Different Keys

ECDH operates with private scalars `a`/`b` and public points `A=aG`, `B=bG` on the same domain parameters. Both compute the shared point `abG`; the provider converts it into shared secret bytes according to the algorithm's rules. `ECGenParameterSpec("secp256r1")` generates a key pair on **P-256**, also commonly named `prime256v1` in many tools.

**Never** use a P-384 public key or an X25519 key as the peer public key for a `KeyAgreement("ECDH")` initialized with a P-256 private key. Algorithm, curve, and parameters must be compatible. A `KeyPairGenerator("EC")` object is **not** X25519: X25519 belongs to the `XDH` family with different key interfaces and math.

### 2.3 X25519 and X448: Explicit Algorithm Names

X25519/X448 are standardized in RFC 7748. They implement scalar multiplication on Montgomery curves with specific rules; their design and key formats are not interchangeable with `ECGenParameterSpec("secp256r1")`.

Java 17+ with a supporting provider can use:

```java
// Illustrative snippet; inside a Java method with appropriate imports.
KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
generator.initialize(new NamedParameterSpec("X25519"), new SecureRandom());
KeyPair myPair = generator.generateKeyPair();
KeyAgreement ka = KeyAgreement.getInstance("X25519");
ka.init(myPair.getPrivate());
ka.doPhase(peerPublicKey, true);
byte[] sharedSecret = ka.generateSecret();
```

`NamedParameterSpec.X25519` and `NamedParameterSpec.X448` are built-in standard constants; the example uses the string constructor so the same code applies to both. A provider/Java version might not support a given algorithm/curve, in which case you must handle `NoSuchAlgorithmException` or `InvalidAlgorithmParameterException` explicitly; never silently fall back to a weak group or skip authentication.

An X25519 public key on the wire is typically represented as **raw 32 bytes** per a specific protocol *or* X.509 SPKI (such as Java `getEncoded()`). An X448 raw public value is 56 bytes. **Do not mix the two encodings**: `X509EncodedKeySpec` requires SPKI DER with an ASN.1 header, not raw 32/56 bytes.

## 3. The KeyAgreement Lifecycle in JCA

Each side performs four basic steps:

```text
KeyAgreement.getInstance(algorithm)
       |
       v
init(ourPrivateKey)
       |
       v
doPhase(peerPublicKey, true)   // final phase in a 2-party exchange
       |
       v
generateSecret()               // shared secret byte[]
       |
       v
KDF + context + salt -> symmetric key / KEK
```

- **`getInstance`:** selects the agreement algorithm and provider; does not generate a key pair.
- **`init(privateKey)`:** supplies **your own** private key, distinct from the public key that must be sent to the peer. A wrong key type throws `InvalidKeyException`.
- **`doPhase(peerPublic, true)`:** accepts the **peer's** public key; the `true` flag indicates this is the final phase. In a **two-party** DH protocol, call this once. Multi-party protocols may have intermediate phases with `false`; do not assume every algorithm/provider supports multi-party agreement.
- **`generateSecret()`:** retrieves the **new shared secret as a byte[]** after the final phase completes. Both sides must use compatible keys/params so the secret bytes match. Calling this before `init`, before `doPhase`, or with missing phases can throw `IllegalStateException`.

Per the Javadoc, `generateSecret()` resets `KeyAgreement` back to the state after the most recent `init`; at the API level you can call `doPhase` and `generateSecret` again with the same private key. **However**, in ephemeral protocols, reusing a private key is usually a session policy error: it is better to generate a fresh key pair for each handshake and never share stateful `KeyAgreement` instances across threads/requests.

In addition to `generateSecret()` returning `byte[]`, JCA has overloads `generateSecret(byte[], offset)` and `generateSecret(String algorithm)`; the third overload depends on provider support and *does not replace a KDF with salt/info and protocol-specific domain separation labels*. **Do not take raw shared secret bytes and pass them directly to `new SecretKeySpec(secret, "AES")` arbitrarily.** Even if the length matches an AES key size, the output must pass through a KDF, context binding, and protocol security policy.

## 4. Java 17+ Program: Four Algorithms Sharing One KeyAgreement Pattern

The program generates two compatible key pairs (Alice/Bob), calls `init → doPhase → generateSecret` on each side, compares the bytes with `MessageDigest.isEqual`, and prints the secret size. It does not print private keys or shared secrets.

For **DH**, Bob reads the `DHParameterSpec` (p/g) from Alice's public key **within the scope of this demo**. In real systems, exchanging DH groups must follow a standardized group policy and be authenticated; never blindly trust params sent by an untrusted party.

Save as **`KeyAgreementFamiliesDemo.java`**:

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.security.spec.ECGenParameterSpec;
import java.security.spec.NamedParameterSpec;
import javax.crypto.KeyAgreement;
import javax.crypto.interfaces.DHPublicKey;
import javax.crypto.spec.DHParameterSpec;
import java.util.Arrays;

public final class KeyAgreementFamiliesDemo {
    private static void test(String name, String agreement,
                             KeyPair alice, KeyPair bob) throws Exception {
        KeyAgreement a = KeyAgreement.getInstance(agreement);
        a.init(alice.getPrivate());
        a.doPhase(bob.getPublic(), true);
        byte[] sa = a.generateSecret();

        KeyAgreement b = KeyAgreement.getInstance(agreement);
        b.init(bob.getPrivate());
        b.doPhase(alice.getPublic(), true);
        byte[] sb = b.generateSecret();
        try {
            System.out.println(name + " equal="
                    + MessageDigest.isEqual(sa, sb)
                    + " bytes=" + sa.length);
        } finally {
            Arrays.fill(sa, (byte) 0);
            Arrays.fill(sb, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();

        KeyPairGenerator dhAliceGen =
                KeyPairGenerator.getInstance("DH");
        dhAliceGen.initialize(2048, random);
        KeyPair aliceDh = dhAliceGen.generateKeyPair();
        DHParameterSpec params =
                ((DHPublicKey) aliceDh.getPublic()).getParams();
        KeyPairGenerator dhBobGen =
                KeyPairGenerator.getInstance("DH");
        dhBobGen.initialize(params, random);
        KeyPair bobDh = dhBobGen.generateKeyPair();
        test("DH", "DH", aliceDh, bobDh);

        KeyPairGenerator ec = KeyPairGenerator.getInstance("EC");
        ec.initialize(new ECGenParameterSpec("secp256r1"), random);
        KeyPair aliceEc = ec.generateKeyPair();
        KeyPair bobEc = ec.generateKeyPair();
        test("ECDH-P256", "ECDH", aliceEc, bobEc);

        for (String name : new String[] { "X25519", "X448" }) {
            KeyPairGenerator x = KeyPairGenerator.getInstance(name);
            x.initialize(new NamedParameterSpec(name), random);
            test(name, name, x.generateKeyPair(), x.generateKeyPair());
        }
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 KeyAgreementFamiliesDemo.java
java KeyAgreementFamiliesDemo
```

Verified output on an OpenJDK runtime supporting all four algorithms:

```text
DH equal=true bytes=256
ECDH-P256 equal=true bytes=32
X25519 equal=true bytes=32
X448 equal=true bytes=56
```

The result `equal=true` means **two agreements with matching private/public keys produced the same bytes**; it does not prove the authenticity of a peer over the network. `DH bytes=256` corresponds to the 2048-bit DH modulus in the example; byte lengths may differ if another DH group is used. `ECDH-P256 bytes=32` is the shared result encoding for P-256; X25519/X448 output 32/56 bytes as defined by the algorithms.

**Memory:** the program uses `Arrays.fill(sa, (byte) 0)` to shorten the lifetime of secret arrays it owns, but the Java GC, provider, `KeyPair` objects, and internal copies may persist longer. Never treat `Arrays.fill` as an absolute guarantee that every copy of a cryptographic secret has been erased.

## 5. Public Keys on the Network: How to Encode and Validate

To send public keys between Java processes, you typically call `getEncoded()` to obtain **X.509 SubjectPublicKeyInfo DER** and send it alongside algorithm metadata, version, curve/group, role, and handshake ID. The receiver uses `KeyFactory` with the exact algorithm to reconstruct it:

```java
// Illustrative snippet in a Java method; publicBytes comes from a parsed
// and size-bounded message with an explicit algorithm contract.
java.security.PublicKey imported =
        java.security.KeyFactory.getInstance("X25519")
                .generatePublic(new java.security.spec
                        .X509EncodedKeySpec(publicBytes));
```

The snippet above is intentionally **not standalone**: `publicBytes` comes from the protocol. For ECDH P-256, use `KeyFactory("EC")`; for DH use `KeyFactory("DH")`; for X448 use `KeyFactory("X448")`. RFC 7748 raw X25519/X448 point bytes are not SPKI DER. If the wire protocol sends raw u-coordinates, you must parse them with the right API/format (such as a provider supporting `XECPublicKeySpec`), not artificially wrap or label them as X.509.

For private keys: `PrivateKey.getEncoded()`, if exportable, is typically **PKCS#8 DER**; **never** transmit private keys between Alice and Bob to perform DH. Hardware providers may return `null` from `getEncoded()`; use the corresponding key handle instead of forcing export.

**Public key validation is a critical boundary:**

- **DH:** verify that the `p,g` group is on an allowed list/standard, check strength, and validate that the public DH value lies in the valid range; check subgroups as required by the protocol. Values like `1`, `0`, `p-1`, or small-subgroup elements can cause weak secrets or attacks depending on group structure. Never trust group configurations supplied by an attacker.
- **ECDH:** the curve must be an allowed curve and match the private key; the public point must be valid on the curve, not infinity or in the wrong subgroup (depending on curve/cofactor); use a trusted provider with appropriate checks and additional policy when importing keys from untrusted input.
- **X25519/X448:** comply with RFC 7748 and guard against invalid/low-order peer keys, including checking for and rejecting an **all-zero shared secret** as required by the protocol. Some JDKs/providers reject weak keys in `doPhase`/`generateSecret` with `InvalidKeyException`; do not assume all providers behave identically. Never accept empty values or wrong groups as a normal secret.
- Every wire format must enforce **size limits**, an algorithm/curve allow-list, and proper parser error handling. A public key may be public, yet it is still **untrusted input** to the parser.

**Peer identification:** even when a public key is mathematically valid, it may still belong to Mallory. Only a verified certificate chain, a securely distributed pinned key, a signature over the transcript, or a PSK-based authenticated handshake can bind a key to an identity.

## 6. From Shared Secret to AES Key: HKDF with Salt and Info

JCA `generateSecret()` returns shared material `S`, not a ciphertext format. DH/ECDH shared secrets have their own structure and distribution; do not take `S` directly as an AES key or misuse `Arrays.copyOf(S, 16)` or `SHA256(S)` without domain separation. Use standard RFC 5869 **HKDF** with a PRF such as HMAC-SHA256:

```text
IKM  = KeyAgreement.generateSecret()
salt = 32 bytes shared between both sides, need not be secret
PRK  = HKDF-Extract(salt, IKM) = HMAC_SHA256(salt, IKM)
info = protocol label || version || roles || transcript || key-purpose
OKM  = HKDF-Expand(PRK, info, requestedLength)
AES  = SecretKeySpec(OKM, "AES")
```

- **IKM** is the input keying material. `PRK` is the pseudorandom key. `OKM` is the output keying bytes.
- HKDF **salt** does not need to be secret; it can be a public handshake nonce or a value agreed upon by both parties. If the protocol supplies no salt, RFC 5869 defines an all-zero salt rule; **do not** turn salt into a second private key.
- **Info** binds the *protocol, version, both public keys, client/server roles, transmission direction, and key purpose*. Both sides must encode it identically **according to a single specification**. Concatenating strings without lengths/delimiters can be ambiguous; use length prefixes or a schema-driven binary format.
- With multiple session keys, use **distinct** label/info values for `client→server key`, `server→client key`, nonce-base, key wrapping, or exporter secrets. Never reuse the same HKDF output for multiple purposes.
- AES-256 needs 32 bytes of **OKM**. With HMAC-SHA256, if only 32 bytes are needed, `HKDF-Expand` uses **one block**: `T(1)=HMAC(PRK, info || 0x01)`. If more bytes are required, you must loop `T(i)=HMAC(PRK, T(i-1)||info||i)`, up to at most 255 blocks; **do not** use the single-block code below to generate multiple keys at once without modifying it.
- Key agreement does not change **source authentication** properties. HKDF with an unsigned transcript in `info` still cannot stop MITM if Mallory swaps the public keys and runs two separate handshakes.

The next program implements the **32-byte single-block HKDF case** directly using `Mac.getInstance("HmacSHA256")` to illustrate the mechanism. In production, use an audited HKDF library, keeping metadata and test vectors, rather than inventing a general-purpose KDF yourself.

## 7. Java 17+ Program: X25519 → HKDF-SHA256 → AES-GCM

This is an **end-to-end example in the same JVM** proving that Alice and Bob derive the same shared secret, derive the same AES-256 key using **HKDF-Extract + one HKDF-Expand block**, encrypt/decrypt with AES-GCM, and detect ciphertext/tag modification.

**Threat model warning:** the program only has two trusted peers in one JVM; it does **not** implement peer authentication, transcript signatures, certificates/pinning, network framing, or replay protection. Do not treat this as a complete key-exchange protocol ready to copy into an Internet product. For real deployments, prefer TLS 1.3 or an audited authenticated key exchange protocol.

Save as **`X25519HkdfAesGcmDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.security.spec.NamedParameterSpec;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyAgreement;
import javax.crypto.Mac;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class X25519HkdfAesGcmDemo {
    private static byte[] agree(KeyPair ours,
                                java.security.PublicKey theirs) throws Exception {
        KeyAgreement agreement = KeyAgreement.getInstance("X25519");
        agreement.init(ours.getPrivate());
        agreement.doPhase(theirs, true);
        return agreement.generateSecret();
    }

    private static byte[] transcript(byte[] a, byte[] b) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            byte[] domain = "demo-x25519-aes-gcm-v1"
                    .getBytes(StandardCharsets.US_ASCII);
            out.writeInt(domain.length);
            out.write(domain);
            out.writeInt(a.length);
            out.write(a);
            out.writeInt(b.length);
            out.write(b);
        }
        return bytes.toByteArray();
    }

    private static byte[] deriveAes256(
            byte[] shared, byte[] salt, byte[] info) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(salt, "HmacSHA256"));
        byte[] prk = mac.doFinal(shared);  // HKDF-Extract
        try {
            mac.init(new SecretKeySpec(prk, "HmacSHA256"));
            mac.update(info);
            mac.update((byte) 1);          // T(1), 32 bytes for AES-256
            return mac.doFinal();
        } finally {
            Arrays.fill(prk, (byte) 0);
        }
    }

    private static Cipher gcm(int mode, byte[] key, byte[] nonce)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(mode, new SecretKeySpec(key, "AES"),
                new GCMParameterSpec(128, nonce));
        return cipher;
    }

    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();
        KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
        generator.initialize(new NamedParameterSpec("X25519"), random);
        KeyPair alice = generator.generateKeyPair();
        KeyPair bob = generator.generateKeyPair();

        byte[] secretA = agree(alice, bob.getPublic());
        byte[] secretB = agree(bob, alice.getPublic());
        byte[] salt = new byte[32];
        random.nextBytes(salt);
        byte[] info = transcript(
                alice.getPublic().getEncoded(),
                bob.getPublic().getEncoded());

        byte[] keyA = null;
        byte[] keyB = null;
        byte[] otherContextKey = null;
        try {
            System.out.println("sharedEqual="
                    + MessageDigest.isEqual(secretA, secretB));

            keyA = deriveAes256(secretA, salt, info);
            keyB = deriveAes256(secretB, salt, info);
            byte[] otherInfo = Arrays.copyOf(info, info.length + 1);
            otherInfo[otherInfo.length - 1] = 1;
            otherContextKey = deriveAes256(secretA, salt, otherInfo);
            System.out.println("derivedEqual="
                    + MessageDigest.isEqual(keyA, keyB));
            System.out.println("contextSeparated="
                    + !MessageDigest.isEqual(keyA, otherContextKey));
            System.out.println("derivedBits=" + (keyA.length * 8));

            byte[] nonce = new byte[12];
            random.nextBytes(nonce);
            byte[] aad = "record:1".getBytes(StandardCharsets.UTF_8);
            byte[] message = "Hello secure channel"
                    .getBytes(StandardCharsets.UTF_8);

            Cipher encrypt = gcm(Cipher.ENCRYPT_MODE, keyA, nonce);
            encrypt.updateAAD(aad);
            byte[] ciphertextAndTag = encrypt.doFinal(message);

            Cipher decrypt = gcm(Cipher.DECRYPT_MODE, keyB, nonce);
            decrypt.updateAAD(aad);
            byte[] recovered = decrypt.doFinal(ciphertextAndTag);
            System.out.println("roundTrip="
                    + Arrays.equals(message, recovered));

            byte[] modified = ciphertextAndTag.clone();
            modified[modified.length - 1] ^= 1;
            try {
                Cipher reject = gcm(Cipher.DECRYPT_MODE, keyB, nonce);
                reject.updateAAD(aad);
                reject.doFinal(modified);
                System.out.println("tamperRejected=false");
            } catch (AEADBadTagException expected) {
                System.out.println("tamperRejected=true");
            }
        } finally {
            Arrays.fill(secretA, (byte) 0);
            Arrays.fill(secretB, (byte) 0);
            if (keyA != null) Arrays.fill(keyA, (byte) 0);
            if (keyB != null) Arrays.fill(keyB, (byte) 0);
            if (otherContextKey != null)
                Arrays.fill(otherContextKey, (byte) 0);
        }
    }
}
```

Compile and run standalone:

```bash
javac --release 17 -encoding UTF-8 X25519HkdfAesGcmDemo.java
java X25519HkdfAesGcmDemo
```

Verified output:

```text
sharedEqual=true
derivedEqual=true
contextSeparated=true
derivedBits=256
roundTrip=true
tamperRejected=true
```

### 7.1 Why Does the Program Produce This Output?

`sharedEqual=true`: X25519(Alice's private, Bob's public) and X25519(Bob's private, Alice's public) produce the same 32 bytes. `derivedEqual=true`: HKDF receives the **same secret, salt, and info**, so both sides produce the same 32 bytes of AES-256 material. `contextSeparated=true`: changing one byte of `info` produces a different key (with overwhelming probability), illustrating domain separation.

`transcript(...)` builds bytes containing a **length-prefixed** protocol label and Alice/Bob SPKI DER in a fixed order. In a real protocol, both sides must agree on **roles and ordering**, include handshake messages, algorithm negotiation, and session identification, and **authenticate** the transcript contents. The demo does not do that on its own.

`roundTrip=true`: `Cipher("AES/GCM/NoPadding")` receives key bytes from HKDF, a random 12-byte IV, a 128-bit tag, and matching AAD on the decrypt side. `tamperRejected=true`: flipping the last byte of ciphertext+tag causes decrypt `doFinal` to throw `AEADBadTagException`; never use plaintext if the tag is invalid. `Cipher.updateAAD` must occur before encryption/decryption data as required by AEAD.

**GCM IVs must never repeat under the same key.** The example only performs one encryption, so a fresh random 12-byte IV suffices. For real sessions with millions of records, you need deterministic nonce allocation/sequence numbers per protocol design and within AES-GCM usage limits. Do not just call `new SecureRandom` arbitrarily per message when the protocol specifies a counter-based nonce; avoid reusing key+IV across restarts and retries.

**Protecting secrets:** `Arrays.fill` shortens the lifetime of application-owned arrays, but does not guarantee erasing every copy inside `KeyAgreement`/`Mac`/`Cipher`/`SecretKeySpec` or other objects. Never log raw shared secrets, PRK, derived keys, private keys, or sensitive ciphertexts. Note that `salt` and `info` in the example are public and do not need to be wiped for confidentiality, but must be transmitted accurately between both sides.

## 8. KeyAgreement Does Not Prevent MITM: Handshake Authentication Is Mandatory

If you only exchange public keys over an unauthenticated connection:

```text
Alice                     Mallory                       Bob
  A ------> [intercept]      M1 -------->                B
  A <------  M2             [intercept] <--------        B
    |                       |                              |
 S_Alice-Mallory      two shared secrets            S_Mallory-Bob
```

Mallory can generate a key pair for each side, then decrypt, read/modify, and re-encrypt the data. **DH/ECDH/X25519/X448 math still succeeds; what is missing is binding the public key to the peer's identity.** HMAC/HKDF or AES-GCM only authenticates **someone who knows the derived key**; it does not tell Alice that the key belongs to Bob if Mallory is the one running the agreement.

Mitigations must belong to an explicit **authenticated key exchange protocol**:

1. **Key/handshake signature authentication:** the peer uses a long-term private signing key to sign the transcript containing ephemeral public keys, roles, algorithm/curve negotiation, random nonces, and session context; the other side verifies it with a signing public key bound to a trusted identity.
2. **PKI/certificates:** verify the certificate chain, trust anchor, hostname/identity, validity, key usage, and protocol constraints; obtain the public signing key from the verified certificate rather than merely parsing a certificate and trusting it immediately.
3. **Pinned keys / PSK:** when a trusted distribution channel exists, use pinning or an authenticated PSK handshake with key confirmation and downgrade protection; do not invent ad-hoc MAC combinations lacking transcript binding.
4. **Existing protocols:** for real application transport, prefer **TLS 1.3** (or an audited authenticated protocol/framework). Hand-rolling a key-exchange protocol from JCA primitives carries high risks of replay, reflection, downgrade, context confusion, and session-management bugs.

**Forward secrecy** is achieved only conditionally: by using fresh ephemeral private keys, properly authenticating the handshake, not leaking ephemeral secrets before/after the session, and erasing unneeded material. Static DH has valid use cases, but does not inherently provide the properties of ephemeral DH; a later key compromise may expose past sessions depending on protocol structure.

## 9. Connecting Key Agreement with Key Wrapping and Data Sessions

“Key agreement and wrapping” usually consists of two distinct steps:

1. **Agreement:** Alice and Bob use DH/ECDH/XDH to produce a shared secret and derive keys with HKDF.
2. **Protection:** use a derived key as a **key-encryption key (KEK)** to wrap a **data-encryption key (DEK)**, or use it directly as an AEAD session key per the protocol.

Example DEK wrapping model:

```text
ECDH/X25519/X448 shared secret
          |
          v
 HKDF(info="app/KEK/v1", salt,...)
          |
          v
   256-bit key-encryption key
          |
          +----> AES Key Wrap (per format/protocol)
          |      or AES-GCM wrap with proper IV/tag/AAD
          v
    wrapped DEK  --- send/store ---> recipient
                                |
                           same valid KEK
                                |
                            unwrap DEK
                                |
                         use DEK for data
```

**Never** use the raw shared secret directly as a DEK/KEK just because the array happens to be 32 bytes long. If wrapping with AES-GCM, you need authenticated ciphertext, a unique IV, and appropriate AAD. If using AES-KW, use a provider-appropriate transformation/format and verify AES-KW length and integrity rules. Separate `"KEK"` and `"AEAD session key"` labels via `info` in HKDF; never use **the same raw key for all roles**.

Stored or transmitted records should explicitly include: algorithm suite, curve/group, ephemeral public keys, salt/KDF version/info schema, IV/nonce, ciphertext+tag or wrapped key, key ID/session ID, and authenticated fields. Storing public keys, salt, and IV in metadata **does not require secrecy**, but you must ensure the integrity of critical metadata so it cannot be altered during the handshake.

## 10. Security and Common Implementation Pitfalls

| Error / symptom | Cause | How to handle |
| --- | --- | --- |
| `InvalidKeyException` in `init` / `doPhase` | Public key passed instead of private, wrong algorithm/curve, invalid peer key, or weak public key | Validate type/algorithm, group, and public key; use the right private/public key |
| `InvalidAlgorithmParameterException` | Key generator received an invalid curve/param or the provider rejects it | Use an allow-list of named curves/groups and check provider support |
| `NoSuchAlgorithmException` | Provider lacks `ECDH`/`X25519`/`X448` | Check Java/provider; never auto-fallback to a weak group |
| `IllegalStateException` in `generateSecret` | Missing `init`, missing phases, or wrong state | Follow the exact order `init → doPhase(..., true) → generateSecret` |
| DH secrets mismatch / phase failure | Both sides initialized different `DHParameterSpec`s | Share the same **authenticated** group and verify p/g |
| HKDF outputs mismatch despite equal shared secret | Different salt, info, role order, or transcript encoding | Define a unique length/byte-order/label wire format |
| Using ECDH P-256 with an X25519 peer public key | These are two incompatible algorithms/curves | Use EC/P-256 for ECDH, XDH/X25519 for X25519 |
| Sending private key/`generateSecret()` over network | Confusing the shared secret with the public key | Send only **public** material as defined by the protocol |
| Using `SecretKeySpec(shared, "AES")` directly | Missing KDF/domain separation | HKDF with salt + context; derive purpose-specific keys |
| Skipping public key authentication | MITM establishes two separate agreement sessions | Use TLS/authenticated handshake/PKI/pinning |
| Sharing one `KeyAgreement` across threads | Engine state gets mixed across sessions | Create a new engine per handshake |
| Reusing ephemeral private keys for too long | Weakens forward secrecy and unlinkability | Generate fresh per session per protocol and erase old material |
| Reusing an AES-GCM nonce with the same key | Breaks AEAD confidentiality and integrity | Non-overlapping nonce allocation and protocol-driven lifecycle |
| Not checking for all-zero XDH shared secret | Invalid/low-order peer input can yield a weak secret | Follow RFC/provider validation; reject all-zero secrets |
| Treating `equal=true` as complete security | Missing identity authentication or KDF/AEAD | Add authentication, KDF, and replay protection |
| Hand-rolling a handshake without transcript binding | Downgrade, reflection, role confusion, unknown key-share | Use an audited protocol; sign/bind the full transcript |

**Note on output length:** X25519 returns 32 bytes, X448 returns 56 bytes; **do not** think 56 bytes is an AES-448 key. AES only accepts 16, 24, or 32 bytes, and the security strength of the entire system is the weakest link among all involved components (group, KDF, AEAD, authentication, RNG, key management).

**When a cryptographic error occurs:** never continue using a partial shared secret/key or unauthenticated AEAD plaintext. Wipe/invalidate the session and return a consistent failure to higher layers; avoid detailed error messages that become an oracle helping attackers infer private state. Never log secrets, and never “temporarily switch” to an unauthenticated cipher.

## 11. Algorithm Selection Guide

- **New applications needing key exchange:** generally prefer **X25519** if the entire infrastructure/protocol supports it. It has a clean API and modern key-exchange design; authentication + KDF + AEAD are still required.
- **Interoperating with EC/NIST systems:** **ECDH P-256** is a common choice via `ECGenParameterSpec("secp256r1")`, widely supported by PKI and hardware/enterprise systems.
- **Requiring a 448-bit curve profile:** **X448** targets a higher security level at higher computational cost and potentially narrower support; choose it when protocol and peer compatibility require it.
- **Legacy finite-field DH interoperability:** **DH/FFDHE** with trusted standard groups and policy-compliant minimum sizes (avoid weak groups/short keys). Never use arbitrary params from an unauthenticated peer; FFDHE-2048 provides lower security strength than X25519/P-256.
- **Applications with data requiring long-term secrecy against quantum computers:** DH, ECDH, X25519, and X448 are all **classical** key agreement algorithms and do not resist sufficiently large quantum computers. You need to evaluate **hybrid post-quantum KEM + classical agreement** protocols per relevant standards; merely increasing HKDF length or switching to AES-256 cannot fix this.

Whichever algorithm you choose, the system still requires two-endpoint interoperability tests, key validation checks, transcript authentication, replay/downgrade handling, nonce uniqueness, and key rotation. Never benchmark only `generateSecret()` while ignoring key generation, serialization, network latency, and provider overhead.

## 12. Self-Check Knowledge Questions

1. **What do DH/ECDH/X25519/X448 transmit over the network?** **Public** keys—never private keys or shared secrets.
2. **Which key does Alice pass to `KeyAgreement.init`?** **Alice's** private key; `doPhase` receives **Bob's** public key.
3. **Why does `doPhase(peer, true)` use `true`?** It marks the **final phase** of two-party agreement, allowing `generateSecret()` afterward.
4. **Can two DH parties independently generate two different p/g groups?** No; they must use the **same valid group** with validation.
5. **Is `ECDH` P-256 the same as X25519?** No. The algorithms, curves, and parameter APIs are different.
6. **How long are X25519 and X448 shared secrets?** **32 bytes** and **56 bytes**, respectively.
7. **Does `generateSecret()` return an authenticated AES key?** No; it is a raw shared secret that needs **KDF + protocol context + authentication**.
8. **What happens if you run HKDF with the same IKM/salt but different `info`?** The outputs differ (with overwhelming probability), supporting domain/key-purpose separation.
9. **Why can a man-in-the-middle still read traffic when DH computes validly?** Because the public keys **are not authenticated**; the attacker substitutes their own keys and maintains two secrets.
10. **Does X25519 + HKDF + AES-GCM automatically form a secure TLS alternative?** No; it still lacks authentication, transcript binding, replay/downgrade protection, session management, and a complete protocol.
11. **Can a `KeyAgreement` object be reused after `generateSecret()`?** The JCA API resets it to the post-`init` state, but for **ephemeral DH** you should use a fresh private key and engine per handshake.
12. **Does GCM accept the 56-byte X448 output directly as AES-448?** No; derive an AES-128/192/256 key through a KDF.
13. **Does finite-field DH with a 2048-bit group provide 2048-bit security?** No; modulus length is not equal to security strength.
14. **To wrap a DEK after ECDH, which key should you use?** Derive a **KEK** using HKDF with a purpose label and use an authenticated wrapping mechanism per protocol, not the raw shared secret.
15. **Does using a fresh ephemeral private key guarantee complete forward secrecy on its own?** Not yet: you also need an authenticated handshake, key erasure, and protection against secret leakage under your threat model.

## Reference Standards and Official APIs

- [KeyAgreement, Java SE 21: init, doPhase, generateSecret, and reset lifecycle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KeyAgreement.html)
- [KeyPairGenerator, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyPairGenerator.html)
- [DHParameterSpec and DHPublicKey](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/DHParameterSpec.html)
- [ECGenParameterSpec, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/spec/ECGenParameterSpec.html)
- [NamedParameterSpec: X25519 and X448](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/spec/NamedParameterSpec.html)
- [Mac, Java SE 21: HmacSHA256](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Mac.html)
- [Cipher: AES/GCM/NoPadding](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html)
- [RFC 7748: Elliptic Curves for Security (X25519, X448)](https://www.rfc-editor.org/rfc/rfc7748.html)
- [RFC 5869: HMAC-based Extract-and-Expand Key Derivation Function (HKDF)](https://www.rfc-editor.org/rfc/rfc5869.html)
- [RFC 7919: Negotiated Finite Field Diffie-Hellman Ephemeral Parameters for TLS](https://www.rfc-editor.org/rfc/rfc7919.html)
- [RFC 8446: TLS 1.3 and authenticated key exchange](https://www.rfc-editor.org/rfc/rfc8446.html)
