# 10.9. The Relationship Between Cryptographic Primitives and a Complete Authenticated Protocol

A **cryptographic primitive** performs a narrow, well-scoped function: Diffie–Hellman computes a shared secret, KEM encapsulates a secret for a recipient, a digital signature verifies data signed by a private-key holder, HKDF derives keys, AEAD provides authenticated encryption, and key wrapping protects keys in transit or storage. A **complete security protocol** must define how those primitives fit together with identities, public-key trust, handshake state, versioning, parameters, records, key lifecycles, replay protection, and error handling.

This is lesson 10.9 in the **“10. Key Establishment and Wrapping”** chapter of Java Advanced – Security & Cryptography. Two recurring questions run throughout:

1. Does *“both sides have the exact same secret bytes”* prove they are talking to the right party?
2. Does *“signed, wrapped, and encrypted with safe algorithms”* automatically create a safe protocol?

The answer to both questions is **no**, if identity binding, context, transcript binding, key validation, and state management are missing. This lesson explains why, with two runnable Java 21 programs and a mental model for evaluating protocols.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish the functions of **X25519/ECDH, KEM, key wrapping, Ed25519/Signature, HKDF, HMAC, and AES-GCM**.
- Trace a **man-in-the-middle (MITM)** flow where Diffie–Hellman executes validly yet the client establishes a secret with the attacker.
- Understand how an authenticated handshake requires a **trusted identity key**, client/server roles, negotiated algorithms, ephemeral public keys, nonces, **transcript binding**, key confirmation, and session checks.
- Explain *forward secrecy*, replay protection, unknown-key-share, downgrade, key/algorithm confusion, nonce reuse, and how authentication differs from authorization.
- Run Java 21 with `KeyAgreement("X25519")`, `Signature("Ed25519")`, `Mac("HmacSHA256")`, and `Cipher("AES/GCM/NoPadding")`; interpret outputs and accurately identify the demo's limitations.
- Determine when to use **TLS 1.3, JSSE, HPKE, or a standardized protocol** instead of stitching primitives into a new protocol.

## 1. Map: Which Question Does Each Primitive Answer?

| Component | Java 21 / standard example | What it provides | What it **does not provide on its own** |
| --- | --- | --- | --- |
| Key agreement | `KeyAgreement.getInstance("X25519")`; ECDH | Two parties with matching key types compute a **shared secret** | Identity of the other endpoint, negotiated transcript, MITM protection |
| KEM (key encapsulation) | KEM concept, `javax.crypto.KEM` (Java 21+ API, provider/algorithm dependent) | Encapsulate produces KEM ciphertext + secret; decapsulate recovers secret with matching key | Default sender authentication, full transcript protection, replay/authorization |
| Key wrapping | `Cipher.WRAP_MODE/UNWRAP_MODE` with supported scheme; AES-KW or RSA-OAEP used properly | Protects a key during transport or storage | Proof of who proposed policy, which session/recipient a key belongs to, overall protocol correctness |
| Digital signature | `Signature.getInstance("Ed25519")`, `RSASSA-PSS` | A public key verifies a message signed with the matching private key | Trust that the public key truly belongs to Alice/Bob; freshness without signing and checking context |
| MAC/HMAC | `Mac.getInstance("HmacSHA256")` | Integrity and origin check relative to a shared secret | Distinguishing two holders of the same key, freshness, content confidentiality |
| KDF/HKDF | HKDF-Extract/Expand, HMAC-SHA256 | Turns input secrets into separate keys by **label/context** | Self-authenticating the sender or fixing an already-leaked shared secret |
| AEAD | `Cipher.getInstance("AES/GCM/NoPadding")` | Protects payload and AAD under a secret key, IV, and tag | Sender identity if key is unauthenticated, replay protection for identical ciphertexts |
| Random nonce/sequence | `SecureRandom`, record counter | Unique/numbered values per policy | Replay protection if unprotected and unchecked by state |

**Necessary differs from sufficient:** authenticated encryption can prove a message used the right **traffic key**, yet if an attacker tricked you into establishing the traffic key with them, the AEAD tag is completely valid while the **peer is wrong**.

### 1.1 Three Layers That Are Easily Conflated

- **Secret agreement:** `K_A == K_B` only means two parties ran a valid key exchange. No identity check has occurred yet.
- **Peer/entity authentication:** identifies the rightful owner of a trusted key. A signature can prove possession of a private key **if the public key is bound to an identity**; knowing the peer is genuinely live also requires protocol freshness/possession/liveness checks.
- **Message authentication:** data/ciphertext was not tampered with and was created by a holder of the MAC/AEAD key. This is not transaction permission (*authorization*) and does not mean the request was never seen before.

A sound protocol verifies **the right peer, right message, right session, right version, right timing, and right permissions** before causing business side effects.

## 2. Components of an Authenticated Key-Exchange Protocol

A real handshake may require the following layers; they do not necessarily execute in the exact code order of a particular library.

1. **Roles and goals:** who is client/server, whether one-way or mutual authentication is required, and what level of confidentiality, forward secrecy, and replay protection is needed.
2. **Policy and negotiation:** version, key-agreement/KEM groups, signature algorithms, AEAD, KDF, and allowed extensions. Negotiation must be protected against tampering/downgrade.
3. **Identity and trust anchor:** X.509 certificates + truststore, pinned key fingerprints, or trusted public keys from a registry. Identity must be bound to the verified key.
4. **Ephemeral key share / encapsulation:** generates a fresh session secret with an appropriate algorithm. May use (EC)DHE/X25519, KEM, or a hybrid per protocol.
5. **Authentication and transcript integrity:** signs/MACs the exact transcript, including roles, version, algorithm selection, identities, key shares, and meaningful metadata.
6. **Key derivation + separation:** uses a key-material KDF to derive **traffic keys, IV/base nonces, and finished/key-confirmation keys**, with distinct labels per direction/step.
7. **Key confirmation:** verifies both sides hold the secret and derived the right keys over the **same transcript**, usually via a Finished MAC or authenticated record; only allows data flow when the state machine permits.
8. **Record protection:** AEAD with non-repeating nonces/sequences per key, full AAD, record limits, and anti-replay per design.
9. **Session lifecycle:** timeouts, rekeying, session closure, connection recovery, packet-loss handling, error handling, and resource bounds.
10. **Application policy:** principal, authorization, idempotency, and business-command anti-replay; never authorize a transaction merely because TLS/handshake succeeded.

### 2.1 Why Is “Every API Call Succeeded” Not Enough?

Suppose an application prints:

```text
X25519 agreement: success
HKDF: success
AES/GCM decryption: success
```

These messages say *the math and keys were compatible*, **not** that the server being talked to is the intended server. If the peer's key share was swapped by an attacker from the start, the client computes a secret with the attacker, and the attacker decrypts and produces valid AES-GCM tags too. This is a **protocol** flaw, not an X25519 or AES-GCM bug.

## 3. MITM Attack When Using Diffie–Hellman Alone

Alice wants to exchange keys with Bob; Mallory can intercept and replace public keys in transit.

```text
 Alice                    Mallory                       Bob
   |                         |                           |
   | --- ephemeral pk_A ---->|                           |
   |                         |---- fake pk_M2 ---------->|
   |<-- fake pk_M1 ----------|                           |
   |                         |<-------- ephemeral pk_B ---|
   |                         |                           |
   | K_A = DH(sk_A, pk_M1)   |                           |
   |                         | K_MA = DH(sk_M1, pk_A)     |
   |                         | K_MB = DH(sk_M2, pk_B)     |
   |                         |                  K_B = DH(sk_B, pk_M2)
   |                         |                           |
 K_A == K_MA                   true           K_MB == K_B
```

Both Alice and Bob may believe “we completed an X25519 handshake.” In reality, Mallory knows **two independent secrets**; if the endpoints encrypt with them, Mallory can decrypt and re-encrypt between both channels. No cryptography needs to be broken—only unauthenticated public keys swapped.

### 3.1 Java 21 Demo: Right Algorithm, Wrong Peer

Create file **`UnauthenticatedDhDemo.java`**:

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import javax.crypto.KeyAgreement;

public class UnauthenticatedDhDemo {
    static byte[] agree(PrivateKey mine, PublicKey peer) throws Exception {
        KeyAgreement ka = KeyAgreement.getInstance("X25519");
        ka.init(mine);
        ka.doPhase(peer, true);
        return ka.generateSecret();
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator g = KeyPairGenerator.getInstance("X25519");
        KeyPair alice = g.generateKeyPair();
        KeyPair bob = g.generateKeyPair();

        // Mallory substitutes separate public keys when talking to each endpoint.
        KeyPair malloryToAlice = g.generateKeyPair();
        KeyPair malloryToBob = g.generateKeyPair();

        byte[] aliceSecret = agree(alice.getPrivate(),
                                   malloryToAlice.getPublic());
        byte[] malloryAlice = agree(malloryToAlice.getPrivate(),
                                    alice.getPublic());
        byte[] bobSecret = agree(bob.getPrivate(),
                                 malloryToBob.getPublic());
        byte[] malloryBob = agree(malloryToBob.getPrivate(),
                                  bob.getPublic());

        System.out.println("Alice shares with Mallory: " +
                MessageDigest.isEqual(aliceSecret, malloryAlice));
        System.out.println("Bob shares with Mallory: " +
                MessageDigest.isEqual(bobSecret, malloryBob));
    }
}
```

Compile and run with JDK 21:

```text
javac --release 21 -encoding UTF-8 UnauthenticatedDhDemo.java
java UnauthenticatedDhDemo
```

Stdout:

```text
Alice shares with Mallory: true
Bob shares with Mallory: true
```

**Explanation:** X25519 did nothing wrong: each side shared a secret with **the exact public key it received**. The flaw is that Alice and Bob **did not know whom the received public key belonged to**. The code does not run TCP or intercept network packets; it models an attacker swapping keys right at the receive boundary. `MessageDigest.isEqual` only checks whether two byte arrays match, not identity. The demo skips secret-memory clearing to stay concise; production needs strict key/secret lifecycle policies.

## 4. Authenticating the Exchange: Trust the Right Key Before Trusting the Signature

An instructive way to stop key substitution is for each side to have a **pre-distributed trusted identity signing key** and sign handshake data including the ephemeral public key.

```text
Alice holds skA_sign, with pkA_sign trusted by Bob
Bob   holds skB_sign, with pkB_sign trusted by Alice

ClientOffer = version, suite, role=client, id=Alice, nonceA, ephemeralPubA
sigA = Sign(skA_sign, Encode(ClientOffer))

ServerOffer = version, suite, role=server, id=Bob, nonceB, ephemeralPubB
sigB = Sign(skB_sign, Encode(ServerOffer))

Alice verifies sigB with TRUSTED pkB_sign and expected id=Bob
Bob   verifies sigA with TRUSTED pkA_sign and expected id=Alice
Both confirm an ordered transcript and bind the shared secret to the transcript
```

**If Mallory replaces the ephemeral public key while keeping the old signature, `verify` fails.** Nor can Mallory sign a new offer as Bob without Bob's private key while Alice checks Bob's trusted public key properly.

### 4.1 Key Verification Differs from Identity Authentication

A public key sent alongside a signature created by that same key is **not enough**: an attacker can generate their own key pair, self-sign, and claim to be Bob. The client must have a **trust anchor** such as a policy/hostname-validated certificate chain, a valid certificate pin, or a trusted key registry. Checking `Signature.verify() == true` only proves *the private key matching the supplied public key* produced the signature; it **does not prove the key belongs to Bob without source authentication**.

**Data that must be signed/bound:** protocol version, role, identity or subject, key/algorithm identifiers, ephemeral key share, nonce, algorithm selection, and target/audience. Signing only the public key without signing **role and version** lets attackers cause *role confusion*, *downgrades*, or cross-protocol replays across similar protocols.

### 4.2 Why Bind the Transcript?

A **transcript** is the entire sequence of handshake messages in defined order and encoding, covering all security-relevant fields. Putting a transcript hash like `SHA-256(Encode(clientOffer) || Encode(serverOffer) || ...)` into the key schedule or signature/MAC lets both sides detect disagreements on:

- who is client/server and the expected identities;
- which algorithms, versions, and extensions were negotiated;
- which ephemeral public keys, nonces, and contexts were received;
- which **service, tenant, application, or resource** this session is for (per protocol);
- whether any message was injected, dropped, reordered, or transplanted across contexts.

Never concatenate raw text ad hoc: `"A" + "BC"` and `"AB" + "C"` collide. Use length prefixes, a published binary encoding, or tested canonical serialization. In standard protocols, **transcript construction is part of the specification**, not an arbitrary choice.

### 4.3 HKDF Uses the Shared Secret in the Right Context

With X25519, `generateSecret()` gives secret bytes (input key material – IKM). Usually HKDF is applied:

```text
PRK = HKDF-Extract(salt, X25519_secret)
K_c2s = HKDF-Expand(PRK, label(client-to-server) || context, 32)
K_s2c = HKDF-Expand(PRK, label(server-to-client) || context, 32)
K_finished = HKDF-Expand(PRK, label(key-confirmation) || context, 32)
```

HKDF is standardized in [RFC 5869](https://www.rfc-editor.org/rfc/rfc5869). `salt` and `info/context` are used per design; **never use raw shared secret bytes directly as an AES key just because they match the length**, and never run unseparated SHA-256 hashes for every key type. Per-direction labels/contexts prevent reusing the same key across distinct channels or roles.

Using the transcript hash as a public input in the key schedule provides **key binding** to the handshake. Do not confuse that with signature verification: without identity authentication, an attacker participating in the exchange can compute the exact same secret and transcript with the endpoint. **HKDF does not replace signatures or a standard peer authentication method.**

## 5. Java 21 Lab: Demonstrating *How* the Layers Coordinate

The next program uses:

- **Ed25519 identity key pairs** created beforehand with public keys assumed to be trusted out-of-band (kept in one process in the demo for ease of verification).
- **X25519 ephemeral key pairs** to establish an ephemeral shared secret. Each receiver verifies the signature over the offer, role/id, and suite/nonce before accepting the key share.
- **Length-prefix encoding** of handshake fields to avoid ambiguity; `SHA-256` transcript in a fixed order.
- **HKDF-HMAC-SHA256** as a **single 32-byte Expand block** for a **single client→server AES-256 key**, sufficient for one demo message.
- **AES-GCM** with a fresh random 12-byte IV/nonce and the transcript hash as AAD. Altering AAD causes tag verification to fail.

This is an **experiment illustrating the seams between primitives**. It is not a protocol for production deployment: it lacks network framing/parsers, certificate-chain verification, **bidirectional** finished/key confirmation, replay caches, session state, multi-record sequences/counters, timing/rotation/rekey management, concurrency handling, comprehensive secret erasure, downgrade-resistant state machines, and many other standard requirements. To build a real channel, use TLS 1.3/JSSE or a standardized, audited protocol.

Create file **`AuthenticatedChannelDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyAgreement;
import javax.crypto.Mac;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class AuthenticatedChannelDemo {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final String SUITE =
            "demo-v1:X25519:Ed25519:HKDF-SHA256:AES-256-GCM";

    record Offer(String role, String identity, byte[] nonce,
                 byte[] publicKey, byte[] signature) {}

    static void put(DataOutputStream out, byte[] bytes) throws Exception {
        out.writeInt(bytes.length);
        out.write(bytes);
    }
    static void put(DataOutputStream out, String string) throws Exception {
        put(out, string.getBytes(StandardCharsets.UTF_8));
    }

    static byte[] offerBytes(Offer offer) throws Exception {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(buffer);
        put(out, SUITE);
        put(out, offer.role());
        put(out, offer.identity());
        put(out, offer.nonce());
        put(out, offer.publicKey());
        out.flush();
        return buffer.toByteArray();
    }

    static Offer createOffer(String role, String identity,
                             PublicKey ephemeral, PrivateKey signingKey)
            throws Exception {
        byte[] nonce = new byte[32];
        RANDOM.nextBytes(nonce);
        Offer unsigned = new Offer(role, identity, nonce,
                                   ephemeral.getEncoded(), new byte[0]);
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(signingKey);
        signer.update(offerBytes(unsigned));
        return new Offer(role, identity, nonce,
                         unsigned.publicKey(), signer.sign());
    }

    static boolean verifyOffer(Offer offer, String requiredRole,
                               String requiredIdentity, PublicKey trustedKey)
            throws Exception {
        if (!requiredRole.equals(offer.role())
                || !requiredIdentity.equals(offer.identity())
                || offer.nonce().length != 32) {
            return false;
        }
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(trustedKey);
        verifier.update(offerBytes(offer));
        return verifier.verify(offer.signature());
    }

    static byte[] transcriptHash(Offer client, Offer server)
            throws Exception {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(buffer);
        put(out, "handshake-transcript-v1");
        put(out, offerBytes(client));
        put(out, client.signature());
        put(out, offerBytes(server));
        put(out, server.signature());
        return MessageDigest.getInstance("SHA-256")
                .digest(buffer.toByteArray());
    }

    static byte[] agree(PrivateKey mine, byte[] peerPublicKey)
            throws Exception {
        PublicKey other = KeyFactory.getInstance("X25519")
                .generatePublic(new X509EncodedKeySpec(peerPublicKey));
        KeyAgreement agreement = KeyAgreement.getInstance("X25519");
        agreement.init(mine);
        agreement.doPhase(other, true);
        return agreement.generateSecret();
    }

    // HKDF-Extract, then one-block HKDF-Expand for a 32-byte AES key.
    static byte[] channelKey(byte[] shared, byte[] context)
            throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(context, "HmacSHA256"));
        byte[] prk = mac.doFinal(shared);
        try {
            mac.init(new SecretKeySpec(prk, "HmacSHA256"));
            mac.update("client-to-server AES key v1".getBytes(
                    StandardCharsets.UTF_8));
            mac.update((byte) 1);
            return mac.doFinal();
        } finally {
            Arrays.fill(prk, (byte) 0);
        }
    }

    static byte[] seal(byte[] key, byte[] aad, byte[] iv, byte[] plain)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(key, "AES"),
                    new GCMParameterSpec(128, iv));
        cipher.updateAAD(aad);
        return cipher.doFinal(plain);
    }

    static byte[] open(byte[] key, byte[] aad, byte[] iv, byte[] encrypted)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, new SecretKeySpec(key, "AES"),
                    new GCMParameterSpec(128, iv));
        cipher.updateAAD(aad);
        return cipher.doFinal(encrypted);
    }

    public static void main(String[] args) throws Exception {
        // The trusted identity public keys were provisioned beforehand.
        KeyPairGenerator identityGenerator =
                KeyPairGenerator.getInstance("Ed25519");
        KeyPair clientIdentity = identityGenerator.generateKeyPair();
        KeyPair serverIdentity = identityGenerator.generateKeyPair();

        KeyPairGenerator ephemeralGenerator =
                KeyPairGenerator.getInstance("X25519");
        KeyPair clientEphemeral = ephemeralGenerator.generateKeyPair();
        KeyPair serverEphemeral = ephemeralGenerator.generateKeyPair();

        Offer client = createOffer("client", "Alice",
                clientEphemeral.getPublic(), clientIdentity.getPrivate());
        Offer server = createOffer("server", "Bob",
                serverEphemeral.getPublic(), serverIdentity.getPrivate());

        boolean clientAuthenticated = verifyOffer(client, "client", "Alice",
                clientIdentity.getPublic());
        boolean serverAuthenticated = verifyOffer(server, "server", "Bob",
                serverIdentity.getPublic());
        System.out.println("trusted client offer: " + clientAuthenticated);
        System.out.println("trusted server offer: " + serverAuthenticated);

        byte[] replaced = client.publicKey().clone();
        replaced[replaced.length - 1] ^= 1;
        Offer tampered = new Offer(client.role(), client.identity(),
                client.nonce(), replaced, client.signature());
        System.out.println("substituted key accepted: " +
                verifyOffer(tampered, "client", "Alice",
                            clientIdentity.getPublic()));

        if (!clientAuthenticated || !serverAuthenticated) {
            throw new SecurityException("Untrusted handshake");
        }

        byte[] context = transcriptHash(client, server);
        byte[] leftShared = agree(clientEphemeral.getPrivate(),
                                  server.publicKey());
        byte[] rightShared = agree(serverEphemeral.getPrivate(),
                                   client.publicKey());
        byte[] leftKey = channelKey(leftShared, context);
        byte[] rightKey = channelKey(rightShared, context);
        System.out.println("derived keys match: " +
                MessageDigest.isEqual(leftKey, rightKey));

        byte[] iv = new byte[12];
        RANDOM.nextBytes(iv);
        byte[] plaintext = "hello Bob".getBytes(StandardCharsets.UTF_8);
        byte[] ciphertext = seal(leftKey, context, iv, plaintext);
        byte[] opened = open(rightKey, context, iv, ciphertext);
        System.out.println("authenticated message: " +
                new String(opened, StandardCharsets.UTF_8));

        byte[] wrongContext = context.clone();
        wrongContext[0] ^= 1;
        boolean rejected = false;
        try {
            open(rightKey, wrongContext, iv, ciphertext);
        } catch (AEADBadTagException expected) {
            rejected = true;
        }
        System.out.println("changed transcript rejected: " + rejected);

        Arrays.fill(leftShared, (byte) 0);
        Arrays.fill(rightShared, (byte) 0);
        Arrays.fill(leftKey, (byte) 0);
        Arrays.fill(rightKey, (byte) 0);
    }
}
```

Compile and run with **JDK 21** (or a newer JDK supporting `--release 21`):

```text
javac -version
javac --release 21 -encoding UTF-8 AuthenticatedChannelDemo.java
java AuthenticatedChannelDemo
```

Expected stdout (keys and nonces are randomly generated and not printed):

```text
trusted client offer: true
trusted server offer: true
substituted key accepted: false
derived keys match: true
authenticated message: hello Bob
changed transcript rejected: true
```

### 5.1 Analyzing Each Result

- **Trusted offers:** both sides are assumed to hold each other's **true identity public keys** from a trusted channel; signatures verify the exact offer bytes including role/id/suite/nonce/key share.
- **Substituted key rejected:** flipping a byte of the public key while keeping the old signature causes verification to fail; an attacker cannot arbitrarily swap exchange keys without the signing private key.
- **Derived keys match:** `KeyAgreement` produces compatible shared secrets; HKDF-Extract uses the transcript hash as a public salt, and single-block HKDF-Expand feeds `info || 0x01` to produce a 32-byte c2s key. This uses **one block of RFC 5869**, not a general multi-block/arbitrary-length HKDF implementation.
- **Authenticated message:** AES-GCM uses the **same derived key, IV, and AAD (transcript hash)** on both sides to verify the tag and decrypt plaintext. Measuring only this outcome while omitting identity trust still allows a MITM to build a valid channel with the attacker.
- **Changed transcript rejected:** altering AAD while keeping ciphertext/tag causes `AEADBadTagException`. That illustrates context data authenticated at the record layer; it **does not replace** verifying signatures/peer trust.

**Important limitation:** the demo does not demonstrate a bidirectional *handshake Finished* exchange. `derived keys match: true` is compared inside one process, not via network key confirmation. A real system requires each side to send and verify proof of possession of the derived handshake key per the state machine before considering the session established.

### 5.2 Details Regarding Java and Encoding

- `KeyPairGenerator.getInstance("X25519")` and `KeyAgreement.getInstance("X25519")` perform key agreement; `Ed25519` belongs to digital signatures and uses `Signature`. Never treat `Ed25519` as `X25519` or vice versa.
- `ephemeral.getEncoded()` in the example returns the X.509/SubjectPublicKeyInfo encoding of the public key; `KeyFactory` reconstructs the public key from `X509EncodedKeySpec`. This is a **key encoding format**, not a CA-trusted X.509 certificate.
- `DataOutputStream.writeInt(length)` delimits field boundaries. Production must enforce maximum length bounds, fault-tolerant parsers, canonical encoding, algorithm/key-type checks, and safe network handling.
- `Signature.verify()` verifies the signature against a **pre-known public key**. Replacing the trusted public key with an unverified key carried in the request brings the MITM flaw right back.
- `new SecretKeySpec(context, "HmacSHA256")` uses the public transcript hash as the HKDF-Extract salt; the real secret remains `shared`. With a non-secret salt, HKDF does not rely on hiding the transcript.
- The demo generates one 12-byte IV for **one** message. Multi-record systems need unique nonces/counters per key, per-direction keys/nonces, volume limits, and rotation. Strictly avoid reusing an AES-GCM IV under the same key.
- `Arrays.fill` clears application-owned byte arrays at the end of the demo. Java providers/JVMs may keep copies in memory; this is not a guarantee that every trace of the secret is erased.

## 6. Where Do KEM, Key Wrapping, and Key Agreement Sit in a Protocol?

“Key agreement” and “key wrapping” both get key material to endpoints, yet their **structures and assumptions differ**.

| Mechanism | Sender does | Receiver does | Result |
| --- | --- | --- | --- |
| X25519/ECDH | Uses own private key and peer's public key to compute secret | Does the symmetric counterpart | Shared secret if public keys match the pairs |
| KEM | `Encapsulate(pk_receiver)` generates KEM ciphertext and secret | `Decapsulate(sk_receiver, kemCiphertext)` recovers secret | Same shared secret; does not authenticate sender by default |
| RSA-OAEP key transport | Encrypts/wraps a secret or session key with recipient's public key | Decrypts/unwraps with recipient's private key | Key material transferred to recipient |
| AES-KW (symmetric key wrap) | Wraps a key with a shared **key-encryption key** | Unwraps with the same KEK | Key protected in storage/transit, though the KEK itself still needs a trusted source |
| HKDF | Derives traffic keys from shared secret, transcript/context, and labels | Computes identically with matching inputs/context | Keys separated by function and direction |

### 6.1 KEM Does Not Authenticate the Sender Identity Automatically

A base-mode public-key KEM targeting Bob's key keeps the encapsulated secret confidential to Bob; **anyone** holding Bob's public key can encapsulate to send to Bob. If the application needs to know the sender is Alice, it needs a properly designed authentication/mode, authenticated Bob public key, transcript/associated data, and protocol governance.

**Java 21:** provides the `javax.crypto.KEM` API (introduced in Java 21), yet supported KEMs and providers must be verified per JDK/runtime. Do not confuse the presence of the **`KEM` class** with a specific KEM algorithm **being installed and available**. Check Java 21 and provider docs before choosing an algorithm name.

### 6.2 Key Wrapping Solves Key Transport and Storage

`Cipher.WRAP_MODE`/`UNWRAP_MODE` is a Java API pattern; the specific wrapping algorithm determines ciphertext format, integrity, and key binding. For example:

```text
Sender: sessionKey = SecureRandom(...)
        wrapped = Wrap(KEK_or_pkRecipient, sessionKey)
        send wrapped + algorithmId + associated metadata

Receiver: sessionKey = Unwrap(keyRecipient, wrapped)
          use sessionKey for records under agreed policy
```

This is **pseudocode**, not an invitation to invent a wrap format. “Unwrap returns a SecretKey” does not prove the sender was authorized, that the key is meant for this session/application, that the algorithm was not downgraded, or that the key was never replayed. Protect metadata and identity via protocol binding or standard containers.

Distinguish **RSA-OAEP wrapping a secret**, **AES Key Wrap wrapping a key with a KEK**, and **AES-GCM encrypting data**: each primitive has distinct input limits, nonce/IV rules, and verification checks. Never use raw RSA, never concatenate IV/key/ciphertext without a defined format, and never reuse key-exchange secret bytes across multiple purposes without a KDF/key separation.

### 6.3 Why Is Hybrid Encryption Needed for Large Data?

RSA-OAEP/KEM are usually used only to transport or establish **key material**. A hybrid model:

```text
Shared key or KEM secret → HKDF(context, labels) → traffic key
                                                    |
Plaintext ---------------------------------------> AEAD encrypt
                                                    |
send: key encapsulation/wrapped key + nonce + ciphertext + tag
```

AEAD can encrypt large data volumes within scheme/nonce/key limits and policy. Yet **hybrid encryption by itself does not guarantee sender authentication, replay protection, and context binding**. For example, HPKE (RFC 9180) defines modes and KDF/AEAD suites; base mode does not authenticate the sender's identity, while authenticated modes carry their own key assumptions and protections. Read the profile/protocol to see how identity and authorization must be checked.

## 7. Key Confirmation: Equal Secrets Do Not Prove the Same Session

For one side to conclude the peer **holds the newly derived key** and accepts the exact transcript, protocols typically use a MAC step over the transcript or an authenticated handshake record. Conceptual example:

```text
clientFinished = HMAC(K_finished_c, transcriptHash)
serverFinished = HMAC(K_finished_s, transcriptHash)

client verifies serverFinished with server-side key
server verifies clientFinished with client-side key
only when valid, transition state → ESTABLISHED
```

This is a **diagram**, not an exact replica of TLS. Critically, both directions must use different labels/keys, the transcript must align with state boundaries, and MAC mismatches must fail closed. Never treat “the server decrypted some message” as identity proof if the traffic key was never authenticated beforehand.

### 7.1 What Layers Does TLS 1.3 Implement?

Per [RFC 8446](https://www.rfc-editor.org/rfc/rfc8446), TLS 1.3 provides an explicit protocol framework for versioning, key exchange, certificate-based or PSK authentication, transcript hashing, HKDF key schedule, and **Finished**. With certificate authentication, `CertificateVerify` signs content bound to the transcript; `Finished` MACs the transcript using handshake keys. Keys/nonces and AEAD records are governed by state and direction; authentication failures terminate the handshake.

**Never equate the Java demo with TLS 1.3.** A compliant protocol also handles certificate path/hostname validation, algorithms/suites, resumption/PSK, 0-RTT replay caveats, alerts, key updates, framing, handshake ordering, and extensive test requirements. If a Java program needs TLS connections, prefer **JSSE** (`SSLContext`, `SSLSocket`/`SSLEngine`, HTTPS client/server) with proper trust/authentication settings instead of building a simplified TLS from `KeyAgreement` + `Cipher`.

### 7.2 TLS Server Authentication vs. Client Authentication

HTTPS commonly authenticates the **server** via certificate/hostname, while the **client** may be authenticated at the application layer (OAuth/session/token) or via mutual TLS depending on the system. An “authenticated” handshake does not mandate certificates on both ends.

In your design, document **who trusts whom** and **which directions are authenticated**. If Bob does not authenticate Alice via certificate, the protocol must specify another client identity mechanism and how it binds to the channel/transaction. Never assume TLS alone authorizes every request from Alice to transfer money.

## 8. Properties That Cannot Be Inferred from One Primitive

### 8.1 Forward secrecy

When using ephemeral (EC)DH and erasing session secrets promptly, a **subsequent** compromise of the identity private key may not expose secrets of already-finished sessions (*forward secrecy*, given proper threat model and design). By contrast, RSA key transport that encrypts traffic secrets under a long-term RSA private key can allow past ciphertexts to be decrypted if that private key leaks in the future.

**Never claim forward secrecy** just because the algorithm is named X25519. You must verify fresh per-session ephemeral keys, no unintended reuse, timely secret erasure, proper KDF and protocol binding, and that metadata/logs/backups do not retain session secrets.

### 8.2 Replay protection and freshness

Signatures, MACs, and AEAD tags remain valid when old messages/ciphertexts are replayed intact. If a server receives a “pay 100” request twice, it may execute the business operation twice even though the tag is completely valid. Protocols need nonces/sequence numbers, timestamps/expiration, **replay state**, or appropriate anti-replay; the business layer still needs **idempotency keys** for retries.

In stream protocols, sequence numbers and key epochs usually accompany record protection. In stateless APIs, signed nonces plus a store with reasonable TTL/atomic insertion may be needed. Never rely solely on timestamps without checking for duplicate requests within the window.

### 8.3 Unknown-key-share / identity misbinding

In an *unknown-key-share* (UKS) attack, two parties may compute the same secret while at least one **misunderstands the identity of the peer**. This is not simply leaked secret bytes; the flaw arises because messages/identities/contexts were not bound explicitly. Ensure the key schedule, signatures/MACs, and public-key checks bind **role, local peer identity, intended recipient, version, and appropriate context**.

### 8.4 Downgrade and algorithm confusion

If an attacker can edit “supported versions” or “selected suite” fields outside transcript authentication, both sides can be forced onto a weaker algorithm or disagree on algorithms. Always enforce an **allowlist** and minimum policy; check the negotiation transcript rather than blindly using whatever algorithm the request claims.

Never reuse the same key across multiple schemes or roles without domain separation; never reverse client→server into server→client under the same key/counter. `Signature`/`Cipher` calls may each accept valid individual parameters while a **protocol configuration** remains broken.

### 8.5 AEAD nonces and records

AES-GCM requires an IV/nonce that is **never reused with the same key**. If a record direction shares one key across messages and two nodes pick the same nonce, confidentiality/integrity can break. Specifications must define how nonces derive from sequence/epoch, key updates, record limits, overlap prevention across concurrent workers, and behavior when counters exhaust.

`AAD` authenticates unencrypted metadata such as version, stream ID, sequence, and headers. Both encrypt and decrypt must feed the **exact same AAD bytes** into verification; any metadata altered outside AAD/tag coverage can cause routing/context confusion.

### 8.6 Errors, parsing, and resources

Never let an attacker force the server to allocate huge arrays, run costly batches of signatures/decryptions, or leak error differences to an oracle. Enforce size limits on records/fields/chains, timeouts, concurrent handshake caps, and rate limits. In Java code, catch `GeneralSecurityException` for internal categorization, yet never return key, padding, tag, or certificate internals to external callers.

If a handshake fails at any authentication step, **never establish the session** and never execute side effects. Errors must terminate/roll back state per protocol rules.

## 9. Real-World Architecture: Separating Primitives, Handshake, and Application

A layered model:

```text
Trusted identity / certificate / key registry
                |
                v
ClientHello / ServerHello --version, role, suite, key shares, nonces-->
                |
                v
Handshake transcript + signature / PSK authentication / Finished MAC
                |
                v
X25519 or KEM secret ----- HKDF(context/role/direction) ----+
                                                            |
                         +----------------------------------+
                         |
                    traffic keys + base nonces
                         |
                         v
             AEAD protected records + sequence/epoch
                         |
                         v
      Application identity + authorization + replay/idempotency
```

| Layer | What the application must verify | Failure mode if omitted |
| --- | --- | --- |
| Trust/identity | Public key/certificate truly belongs to expected peer | MITM uses a fake key yet signs validly |
| Handshake negotiation | Version, suite, roles, and policy inside authenticated transcript | Downgrade, role confusion |
| Key establishment | Shared secret with right peer, ephemeral keys, and purpose-separated KDF | Key substitution, key reuse, missing expected forward secrecy |
| Key confirmation | Both sides verify handshake outcome/secret | Accepting incomplete or transcript-mismatched sessions |
| Record AEAD | Unique nonces, right key/direction/AAD/sequence | Data exposure, record tampering, or replay |
| Application | Identity, permissions, request ID, idempotency, audit | Secure channel allowing unauthorized transactions |

### 9.1 Security Protocol and Business Logic Have Different Scopes

For example, a client uses TLS 1.3 to a legitimate server with encrypted transport and a valid certificate. You still must check whether the user is permitted to call `POST /transfer`; user ID may come from an access token/session, not automatically from TLS success. A valid request retried over a **new** TLS connection can still duplicate business effects without idempotency.

That is why architecture reviews ask: “Which protocol protects **bytes on the wire**, which mechanism establishes the **principal**, and which component enforces **transaction permissions and uniqueness**?”

## 10. Choosing a Solution by Goal

| Need | Usually suitable choice | What still must be verified |
| --- | --- | --- |
| HTTPS between Java service and server | TLS 1.3 via up-to-date JSSE/HTTPS stack | Hostname verification, truststore, ALPN/versions/suite policy, client auth if needed |
| Internal Java service mTLS | TLS 1.3 + client/server certificates | Trust anchors, workload identity, key rotation/revocation policy, authorization |
| Encrypt data for a recipient without a live connection | Standard hybrid encryption / matching HPKE profile | Trusted recipient public key, sender authentication mode, context/AAD, replay |
| Wrap a data-encryption key in a KMS system | KMS/HSM wrap/unwrap or standard AES-KW | Key ID, unwrap permissions, tenant/context binding, rotation, metadata integrity |
| Design a custom protocol | Start from a reviewed/standardized spec and threat model | State machine, crypto review, vectors, fuzzing, interop, rollback/replay/error paths |
| Simply learning the mechanisms | Java 21 examples in this lesson | Only conclude the narrow bounds the demo actually verifies |

**Pragmatic rule:** if you need a real secure channel, use deployed, tested, up-to-date protocols and libraries. Learning primitives helps you **configure properly, spot architectural flaws, and read specifications**—it does not mean you should hand-roll a handshake to replace TLS.

## 11. Checklist for Auditing an Authenticated Protocol

| Test / review question | Required behavior |
| --- | --- |
| Swap ephemeral public key while keeping old signature | Peer authentication fails before sending traffic |
| Replace identity public key with attacker's key | Trust/certificate/pinning rejects it |
| Swap client/server role or peer ID | Signature/transcript authentication fails |
| Downgrade version, swap cipher suite, strip required extension | Transcript mismatch or policy rejection |
| Reuse same shared secret under two different contexts | Key derivation applies proper labels/contexts; no unintended key collision |
| One side receives a different transcript than the other | Finished/key confirmation fails |
| Send a record message with wrong AAD | AEAD tag rejects; no plaintext delivered to application |
| Replay a record or command | Sequence/replay/idempotency state blocks duplicate effect per policy |
| Reset nonce/counter on reconnect/rotation | Epoch and key schedule prevent nonce reuse |
| Long-term signing private key leaks after session closes | Evaluate forward secrecy of prior sessions; requires proper ephemeral secret lifecycle |
| Send oversized input / wrong keyShare type / bad ciphertext | Bounded parser, fail-closed, no exploitable oracle or DoS |
| Certificate key used for wrong purpose or expired | Trust/policy/usage validation rejects |
| Server authenticated but client lacks permission | Application authorization rejects operation |

### 11.1 Common Misconceptions

1. **“Two equal shared secrets = authenticated peer.”** False: DH only proves key math; MITM can establish two separate shared secrets.
2. **“AES-GCM encryption means no MITM.”** False if the session key was established with the attacker; AEAD tags only mean something relative to a trusted key.
3. **“KEM or RSA-OAEP proves the sender.”** False for base public-key recipient encryption/encapsulation: anyone with the recipient's public key can send.
4. **“Signing the ephemeral key is enough.”** Not enough if the signing public key is untrusted, roles/negotiation/identities are unbound, or key confirmation is incomplete.
5. **“HKDF authenticates identity on its own.”** False: a KDF takes key material and context; it does not know whom a public key belongs to.
6. **“Using one traffic key for both directions is fine because we have nonces.”** Prone to separation/nonce-collision bugs; protocols need explicit directional keys and counters.
7. **“A safe wrapped key is a complete packet.”** Metadata, key ID, unwrap permissions, nonces/records, and replay protection still must be enforced.
8. **“Valid signature/AEAD means the packet is fresh.”** Replaying an exact packet leaves bytes and tags intact.
9. **“`X509EncodedKeySpec` is a CA-signed certificate.”** False: it is a public-key encoding format, not identity proof.
10. **“A lab program simulating 2 endpoints in one JVM proves a production protocol.”** False: demos lack state machines, network adversaries, trust lifecycles, and interop tests.

## 12. Reinforcement Exercises

1. **MITM analysis:** trace the paths of `pk_A`, `pk_B`, and Mallory's two public keys. Explain why Alice and Bob can both call `KeyAgreement.generateSecret()` successfully even though they share no secret with each other.
2. **Signatures:** run `UnauthenticatedDhDemo` and then `AuthenticatedChannelDemo`. Identify at which step a substituted key share is rejected, and which public key must be trusted before verifying the signature.
3. **Transcript:** if the client signs `pkA` while omitting `suite`, what binding flaw can an attacker exploit? If AAD is altered by one byte, how does AES-GCM behave?
4. **HKDF:** explain the differences among `shared`, `PRK`, and `traffic key`; why are two labels `client-to-server` and `server-to-client` needed? Why is the one-block implementation in the demo not a general HKDF?
5. **Key wrapping:** describe a DEK wrapped with RSA-OAEP, AES-KW, or a KMS key. Pinpoint exactly where authorization, recipient verification, and metadata protection occur.
6. **Key confirmation:** design *in words* a bidirectional Finished exchange with MACs over the transcript without writing a production protocol. If one side skips verifying the other's MAC, which guarantee is missing?
7. **Replay:** an authenticated payment is resent identically over a new TLS connection. Why isn't valid-certificate TLS enough to avoid double-charging? Specify the needed replay cache/idempotency.
8. **Forward secrecy:** compare ephemeral X25519 against key transport relying solely on a long-term decryption private key; what conditions must hold so a later key compromise does not expose old data?
9. **Threat model:** list which fields in the handshake and records an attacker can modify/truncate/delay/reorder; map each tampering to the verification check that catches it.
10. **Design decision:** a Java service needs client/server TLS and per-tenant authorization. Describe the roles of `SSLContext`/truststore, certificate identity, application authorization, and how to rotate keys without dropping transaction state.

**Completion criterion:** given a protocol diagram, you can identify which primitive establishes secrets/wraps keys, where identity authentication occurs, where transcript binding and KDF apply, where record protection/key confirmation sit, and which mechanism handles replay/authorization. If any layer is removed, you can describe **what remains mathematically valid yet becomes protocol-unsafe**.

## References

- [Java SE 21 — `KeyAgreement`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KeyAgreement.html): initialization and generating shared secrets.
- [Java SE 21 — `Signature`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Signature.html): signing and verifying with Ed25519/RSA-PSS.
- [Java SE 21 — `Cipher`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html): AEAD, `ENCRYPT_MODE`/`DECRYPT_MODE`, and key wrapping `WRAP_MODE`/`UNWRAP_MODE`.
- [Java SE 21 — `javax.crypto.KEM`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.html): encapsulate/decapsulate concepts and API scope.
- [Java SE 21 — Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html): names for X25519, Ed25519, HmacSHA256, and transformations.
- [RFC 7748](https://www.rfc-editor.org/rfc/rfc7748): Elliptic Curves for Security, X25519/X448.
- [RFC 5869](https://www.rfc-editor.org/rfc/rfc5869): HKDF-Extract/Expand and labels/context.
- [RFC 8446](https://www.rfc-editor.org/rfc/rfc8446): TLS 1.3 key schedule, CertificateVerify, Finished, and transcript binding.
- [RFC 9180](https://www.rfc-editor.org/rfc/rfc9180): Hybrid Public Key Encryption (HPKE), KEM/KDF/AEAD, and authentication modes.
- [Java 21 Secure Socket Extension (JSSE) Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html): TLS in Java, trust configuration, and peer authentication.
