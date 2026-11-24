# 10.5. Peer Authentication to Prevent Key Substitution During Agreement

**Key agreement** lets two parties establish a shared secret over an observable channel. However, there is an easily forgotten condition: **both sides must know who they are actually agreeing with**. If an attacker can substitute the public keys exchanged during the handshake, Diffie–Hellman/ECDH/X25519 alone **does not prevent a Man-in-the-Middle (MITM) attack**.

A man-in-the-middle can establish two separate key agreement sessions: one with Alice and one with Bob. Alice thinks she established a key with Bob; Bob thinks he established a key with Alice; in reality both share two separate keys with the attacker. Even when each side uses standard AES-GCM to protect data, the man-in-the-middle can decrypt and re-encrypt because the attacker holds valid keys for **both spoofed sessions**.

**The solution is not making DH keys longer or hashing the exchanged keys.** You must **authenticate public keys and peer identity**, bind the authentication proof to **the exact handshake session, roles, algorithms, and ephemeral public keys**, and only allow using session keys after verification passes.

## 1. Lesson Objectives

After completing this lesson, you will be able to:

- Explain why DH/ECDH/X25519 does not authenticate identity solely through computing a shared secret.
- Distinguish **agreement**, **authentication**, **authorization**, **key confirmation**, and **key wrapping**.
- Diagram a public-key-substitution MITM attack, knowing exactly why each side still computes a shared secret without having a secure Alice–Bob channel.
- Build peer authentication steps using digital signatures bound to identity, certificates/PKI, public-key pinning, or securely distributed PSKs.
- Identify which bytes must be bound into the **handshake transcript**: protocol version, cipher suite/KDF, roles, identities, ephemeral public keys, nonces, and context.
- Write and run a Java 17+ demonstration combining **X25519 + Ed25519 + HKDF-SHA256** with pre-trusted identity public keys.
- Test substituting public keys, forging signers, changing peer names, and replaying signatures from old sessions; understand the demo's limitations compared to TLS 1.3.
- Identify defects related to certificate validation, TOFU, key substitution, replay, downgrade, UKS, and access authorization checks.

## 2. Three Separate Questions About Keys

In practice, “key authentication” sometimes lumps together different tasks. Separate it into three questions:

**Question A — can the parties establish the same secret?**  
If Alice holds ephemeral private key `a` and Bob holds ephemeral private key `b`, X25519 computes:

\[
Z_A = X25519(a, B_{\text{ephemeral}})
\]

\[
Z_B = X25519(b, A_{\text{ephemeral}})
\]

With two valid key pairs and corresponding public keys exchanged intact, the two secrets `Z_A` and `Z_B` are equal. This is **key agreement capability**; it does not yet tell you who the public key actually came from.

**Question B — who is behind the public key?**  
Alice needs to know whether `B_ephemeral` belongs to **the exact agreement session with Bob**. To know that, Alice must have proof binding `B_ephemeral` to **the Bob identity Alice expects**, grounded in a trust anchor such as a pinned signing key, verified certificate, properly provisioned PSK, or an out-of-band verification procedure.

**Question C — what is the key authorized to be used for?**  
After both sides compute the shared secret and authenticate the transcript, they typically need a KDF (e.g., HKDF) to derive application keys and, when needed, directional keys/nonces. Afterward, the server must still check the principal's **access permissions**, not merely that the client knows a key.

A session can pass A yet fail B (MITM), or pass A and B yet fail C (an authenticated client not permitted to operate on another account).

## 3. Unauthenticated Diffie–Hellman: Key Substitution Attack

Suppose Alice and Bob want to establish a secure channel over a network where Mallory can read, intercept, and modify packets.

### 3.1. Passive eavesdropping only, no tampering

```text
Alice                                             Bob
------                                            ------
Generate (aPriv, aPub)                           Generate (bPriv, bPub)
        |                                             |
        +------------- aPub ------------------------->|
        |<------------ bPub --------------------------+
        |                                             |
Z_A = X25519(aPriv, bPub)             Z_B = X25519(bPriv, aPub)
        |                                             |
        +-------- HKDF -> session key ----------------+
```

If an attacker only **observes** both public keys without knowing the private keys, X25519 is designed to make computing the shared secret intractable. This is the foundational property of Diffie–Hellman.

**However, Mallory does not have to stay passive.** If the channel is unauthenticated, Mallory can replace both public keys.

### 3.2. MITM attack using two DH sessions

```text
  Alice                         Mallory                         Bob
  -----                         -------                         ---
  aPub -----------> [intercept]  mPub1 ------------->         Bob
  Alice <----------- mPub2       [intercept] <--------- bPub

 Alice computes:                    Mallory computes:
 X25519(aPriv, mPub2)               X25519(mPriv2, aPub)
                   -> Z_AM = Z_MA

                                  Mallory computes:             Bob computes:
                                  X25519(mPriv1, bPub)          X25519(bPriv, mPub1)
                                         Z_MB = Z_BM <-
```

Result:
- Alice shares **one secret with Mallory**, not Bob.
- Bob shares **a different secret with Mallory**, not Alice.
- Mallory knows both secrets, can derive traffic keys for both sides, and sits in the middle to decrypt/modify/re-encrypt.
- No X25519 operation warns that the peer name displayed in the UI does not match the subject that generated the public key.

This is why claiming “using ECDH already protects data against MITM” is **false without peer authentication**.

### 3.3. Why hashing the public key is also insufficient

Suppose Alice receives `bPub`, computes `SHA-256(bPub)`, and observes a fingerprint. A fingerprint only summarizes the bytes of the key Alice **received**. If an attacker replaces `bPub` with `mPub`, Alice can equally compute a completely valid fingerprint of `mPub`.

A fingerprint helps only when Alice **compares it against a pre-existing trusted fingerprint** obtained via an independent authenticated channel. Sending a public key and its own fingerprint inside the **same unauthenticated packet** does not stop substitution.

Switching X25519 to another curve, using more RSA bits, or switching SHA-256 to SHA-512 will not fix the root flaw: **there is no evidence binding the key to the intended peer**.

## 4. What Does Peer Authentication Actually Mean?

For Alice wanting to communicate with Bob, there are at least four components:

1. **Expected identity:** Alice knows beforehand whom she expects to talk to, e.g., `bob@example.internal`, a service name, tenant + service ID, or hostname `api.example.com`.
2. **Trusted authentication key:** Alice has a way to obtain **Bob's identity-verification key from a trusted source**, not solely from packets controlled by Mallory.
3. **Proof of possession:** Bob produces proof that only the entity holding the authorized private key/PSK can validly generate, such as a digital signature over the handshake transcript.
4. **Session binding:** this proof binds the **exact session** and relevant parameters, especially the ephemeral public keys, roles, nonces, protocol version, and chosen algorithm.

If the proof only shows “Bob knows some private key,” it still fails to prove it is **the private key belonging to Bob**. If a certificate is valid for another domain but Alice skips hostname checking, an adversary can present a certificate for a domain they own and pass chain validation. If the signature only signs a static string like `"I am Bob"`, an attacker can replay that signature in another session.

**Identity must come from the verifier's expectation**, never accepted merely because the other side self-asserted it in the payload.

### 4.1. Server authentication and mutual authentication

- **Server authentication:** the client verifies the server; the server may not verify the client's identity during the handshake and may use another step (token, account, OAuth, client certificate, etc.) afterward.
- **Mutual authentication:** both sides prove their identities using an appropriate mechanism, such as mTLS or two signatures on an authenticated handshake.
- **Authorization:** once identity is proven, the system checks whether that principal is allowed to call the API, access the resource, use the tenant, or perform the specific operation.

Therefore, **authenticated key agreement does not mean permission to access all data**.

## 5. Which Bytes Must a Handshake Sign or MAC?

Complete protocols typically construct a **handshake transcript**: an ordered byte sequence representing the exchanged messages and parameters. The signature/MAC/Finished value is computed over a digest or explicit structure tied to this transcript.

A model for this lesson:

```text
transcript_v1 =
    protocolId
    || suiteId
    || "initiator" || aliceExpectedIdentity
    || "responder" || bobExpectedIdentity
    || aliceNonce
    || bobNonce
    || aliceX25519EphemeralPublic
    || bobX25519EphemeralPublic
```

The `||` symbols denote **concatenation according to a specified format**. There must be an unambiguous encoding, such as length prefixes or deterministic serialization. Never simply concatenate raw strings ad hoc.

Alice verifies that Bob signed **the exact transcript of the session Alice is participating in** using Bob's trusted verification key. Likewise, Bob verifies Alice's proof if mutual authentication is required.

### 5.1. Meaning of each component

| Component | What happens if not bound? |
| --- | --- |
| Protocol name/version | Signature/key may be transplanted to another context or parsed differently |
| Cipher suite and KDF | Risk of negotiation confusion or downgrade to a weak algorithm |
| Initiator/responder roles | Can cause reflection/role confusion when identical data is used in both directions |
| Expected peer identity | Can associate the same session key with two different identities (unknown key-share) |
| Both ephemeral public keys | Attacker swaps one key without breaking the signature |
| Fresh session nonce/challenge | Signatures/messages from a previous session can be replayed |
| Explicit length-framed message structure | Different field pairs could serialize to the same byte input |
| Application context/tenant | Session key could be misapplied to another service, tenant, or operation |

Distinguish **what both sides sign/verify** from **what both sides display on screen**. If the UI says `Bob` while the transcript and verifier use `Mallory`'s key, validly signing an incorrect-identity transcript still fails to deliver the desired peer authentication.

### 5.2. Is signing only the public key enough?

Signing just `bEphemeralPublic` may prove whoever holds some private signing key signed that public key at some time, **but lacks sufficient binding**:
- Do Alice and Alice's nonce belong to this specific session?
- Which client/server role is the signature for?
- Does Bob know he is connecting to Alice rather than Mallory?
- Do both sides share the same protocol version and algorithms?

A stronger design **signs a well-defined transcript**, or uses a standard protocol with its own built-in handshake authentication generation and verification. Never invent “signing a few fields is enough” without a security model.

### 5.3. Freshness and replay

A fresh challenge/nonce included in the transcript prevents an old session's signature from **matching a new session's transcript**, provided both sides actually check the newly generated challenge. However, having a nonce in a handshake message does not automatically block replay of every application-layer request.

Production applications may also need:
- Sequence numbers or unique record nonces for AEAD;
- Replay caches, expiration, and idempotency for sensitive commands;
- Session identifiers bound to principal, scope, deadline, and resource;
- Protocol-specific rules for handshake re-acceptance/resumption.

Never conclude “valid signature” means “the transaction is guaranteed fresh and never executed before.”

## 6. Common Public-Key Authentication Mechanisms

### 6.1. Certificates and PKI

The sender can present a certificate containing a public key and subject/SAN; this certificate is signed by a CA or intermediate chain. The receiver uses configured trust anchors to verify the trust path.

For an HTTPS/TLS connection, the client must check **at least per deployment policy**:
1. A certificate path can be built to an allowed trust anchor.
2. Signatures, validity periods, algorithm/key strengths, and constraints are valid.
3. **The expected server identity matches SAN/hostname** per application standards; never accept a `CN` or server-supplied string as a substitute for hostname validation.
4. Key usage and extended key usage match server authentication where enforced.
5. Revocation/CT/enterprise trust policies and other constraints as required by the system.
6. The handshake proves the server holds the corresponding private key and the transcript was not altered, per protocol.

**Valid chain ≠ correct peer identity.** A valid certificate for `attacker.example` must not be accepted when the client intends to connect to `api.company.example`.

Never enable **trust-all certificates**, an “insecure hostname verifier,” or accept any self-signed certificate in production to work around certificate errors.

### 6.2. Public-key pinning and pre-configured signing keys

If two internal services have distributed authentication public keys over a trusted channel, the receiver can **pin** the key or fingerprint/SPKI hash per policy.

Rules:
- The trusted key comes from a verified configuration/policy, **not** from the peer's own message awaiting verification.
- The pin is checked before accepting the signature, matching the right identity and key usage.
- A backup/rotation and compromise-handling strategy is required; a wrong or expired pin can cause outages.
- For SPKI pins, standardize the encoding/fingerprint format and avoid confusing it with fingerprints of raw key encodings.

Pinning is a deployment-dependent choice, not automatically superior to PKI for every system. In large-scale applications, poor pin lifecycle management can cause widespread connection failures.

### 6.3. Trust on First Use (TOFU)

The TOFU model remembers the public key seen on the **first connection** and warns if it later changes. It is useful in workflows like SSH where a user/operator verifies the fingerprint out-of-band.

Critical limitation: if an attacker is performing a MITM **on the very first connection**, the application may pin the attacker's key by mistake. TOFU is **not equivalent** to verifying a certificate/identity from a trusted source. If the public key later changes, never auto-accept the new key without a rotation/verification workflow.

### 6.4. PSK, password-authenticated key exchange, and out-of-band channels

When two parties already share a **sufficiently strong pre-shared key (PSK) distributed secretly with proper identity**, a protocol can use a MAC/handshake binder to authenticate the session. You must bind PSK identity, transcript, cipher suite, and permissions into context; never accept a PSK claimed from adversary-controlled data.

For human-memorable passwords, **do not turn one into a PSK** via `SHA-256(password)` and use it as a MAC key in a custom handshake: this can expose offline/dictionary attacks. When password-based authentication is needed in key exchange, use a **PAKE** (e.g., a standardized protocol with a vetted implementation) instead of homegrown DH + password hashing.

For two devices that can compare a short verification code or scan a QR code directly, an **out-of-band authenticated comparison** mechanism can also bind public keys, provided the protocol is properly designed and the comparison channel is genuinely trustworthy.

## 7. Session Keys Must Be Derived from the Shared Secret and Transcript

After authenticating the peer and agreeing on ephemeral public keys, X25519 produces a shared secret. Never take raw X25519 bytes directly as an **AES-GCM key and nonce** using ad-hoc rules.

Typically, use a context-bound KDF:

\[
Z = X25519(\text{own ephemeral private},\ \text{peer ephemeral public})
\]

\[
PRK = HKDF\text{-}Extract(\text{salt}, Z)
\]

\[
K_{app} = HKDF\text{-}Expand(PRK,\ \text{info},\ L)
\]

- HKDF `salt` is a **not-necessarily-secret** input that may relate to the transcript hash per protocol design.
- `info` should separate protocol/version, key purpose, and direction: e.g., `client-to-server key` and `server-to-client key` are two distinct purposes.
- `L` is the required output byte length, e.g., **32** for an AES-256 key.
- The transcript hash binds key derivation to the same handshake, but **HKDF itself does not prove peer identity**: you must verify signatures/MACs and the trusted key source before using the keys.

In the Java demo below, we use `salt = SHA-256(transcript)` and one fixed `info` string for a **single demo key**, to make checking that both sides compute the same key straightforward. **Real bidirectional applications** must separate keys/nonces/traffic secrets per direction and manage sequence numbers against nonce reuse.

### 7.1. Key confirmation does not equal identity proof

After deriving keys, both sides can exchange a **confirmation MAC/Finished** proving the peer holds the secret matching the transcript and key schedule.

Conceptual example:

```text
confirmAlice = HMAC(K_confirm_A, "alice-finished" || transcriptHash)
confirmBob   = HMAC(K_confirm_B, "bob-finished"   || transcriptHash)
```

The receiver checks the corresponding tag before allowing the application to send data. In protocols with built-in authentication, Finished/record integrity proofs help detect secret or transcript mismatches.

However, if Mallory created **two spoofed DH sessions** without identity authentication, Mallory also knows the confirmation keys for both sessions and can compute both valid MACs. **Key confirmation only carries full value when combined with peer authentication and session context binding.**

In the Java example, we compare the HMACs computed on both sides **inside the same process** to illustrate key agreement. That is not yet a complete **wire-level key confirmation exchange**.

## 8. Java 17+: X25519 + Ed25519 + Transcript Binding

Below is a **self-contained runnable** JDK 17+ example that intentionally separates two key types:

- **X25519 ephemeral key pairs:** used strictly for per-session key agreement.
- **Ed25519 identity key pairs:** used strictly to sign and verify the transcript. Verification public keys are simulated as **pre-distributed via a trusted channel/pin**.
- **Transcript encoding:** writes each field with a 4-byte length prefix (big-endian), keeping fixed ordering to avoid string ambiguity.
- **HKDF-SHA256:** illustrates RFC 5869 Extract/Expand for a 32-byte output.
- **Attack tests:** substituting an ephemeral public key, altering expected identity, signing with an impostor key, and replaying a signature onto a fresh challenge.

Full file: `AuthenticatedKexDemo.java`.

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.util.Arrays;
import javax.crypto.KeyAgreement;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class AuthenticatedKexDemo {
    static final SecureRandom RNG = new SecureRandom();

    static byte[] random(int n) {
        byte[] data = new byte[n];
        RNG.nextBytes(data);
        return data;
    }

    // Framing: 4-byte length prefix followed by exactly that many bytes.
    static void field(DataOutputStream out, String value) throws IOException {
        field(out, value.getBytes(StandardCharsets.UTF_8));
    }

    static void field(DataOutputStream out, byte[] value) throws IOException {
        out.writeInt(value.length);
        out.write(value);
    }

    static byte[] transcript(
            String initiator, String responder,
            byte[] aliceNonce, byte[] bobNonce,
            PublicKey aliceEphemeral, PublicKey bobEphemeral
    ) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(buffer)) {
            field(out, "auth-kex-demo:v1");
            field(out, "X25519+Ed25519+HKDF-SHA256");
            field(out, "initiator");
            field(out, initiator);
            field(out, "responder");
            field(out, responder);
            field(out, aliceNonce);
            field(out, bobNonce);
            // Java public key encoding: X.509 SubjectPublicKeyInfo format.
            field(out, aliceEphemeral.getEncoded());
            field(out, bobEphemeral.getEncoded());
        }
        return buffer.toByteArray();
    }

    static byte[] sign(PrivateKey key, byte[] message)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance("Ed25519");
        s.initSign(key, RNG);
        s.update(message);
        return s.sign();
    }

    static boolean verify(PublicKey trustedKey, byte[] message, byte[] signature)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance("Ed25519");
        s.initVerify(trustedKey);
        s.update(message);
        return s.verify(signature);
    }

    static byte[] agree(PrivateKey own, PublicKey peer)
            throws GeneralSecurityException {
        KeyAgreement ka = KeyAgreement.getInstance("X25519");
        ka.init(own);
        ka.doPhase(peer, true);
        return ka.generateSecret();
    }

    static byte[] hmac(byte[] key, byte[] message)
            throws GeneralSecurityException {
        Mac h = Mac.getInstance("HmacSHA256");
        h.init(new SecretKeySpec(key, "HmacSHA256"));
        return h.doFinal(message);
    }

    static byte[] applicationKey(byte[] sharedSecret, byte[] transcript)
            throws GeneralSecurityException {
        // RFC 5869 HKDF-Extract(salt, IKM) and first Expand block.
        byte[] salt = MessageDigest.getInstance("SHA-256").digest(transcript);
        byte[] prk = hmac(salt, sharedSecret);

        byte[] info = "auth-kex-demo:v1|app-key"
                .getBytes(StandardCharsets.UTF_8);
        byte[] input = Arrays.copyOf(info, info.length + 1);
        input[input.length - 1] = 1; // HKDF block counter 0x01

        try {
            return hmac(prk, input); // First full 32-byte HKDF-Expand block.
        } finally {
            Arrays.fill(prk, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        // DEMO ONLY: Identity public keys are treated as pre-authenticated.
        // Real applications get them from validated certificates or trusted pins.
        KeyPairGenerator identity = KeyPairGenerator.getInstance("Ed25519");
        KeyPair aliceIdentity = identity.generateKeyPair();
        KeyPair bobIdentity = identity.generateKeyPair();
        PublicKey pinnedAliceKey = aliceIdentity.getPublic();
        PublicKey pinnedBobKey = bobIdentity.getPublic();

        KeyPairGenerator ephemeral = KeyPairGenerator.getInstance("X25519");
        KeyPair a = ephemeral.generateKeyPair();
        KeyPair b = ephemeral.generateKeyPair();
        byte[] aNonce = random(16);
        byte[] bNonce = random(16);

        byte[] t = transcript(
                "alice", "bob",
                aNonce, bNonce,
                a.getPublic(), b.getPublic()
        );

        byte[] aliceSignature = sign(aliceIdentity.getPrivate(), t);
        byte[] bobSignature = sign(bobIdentity.getPrivate(), t);

        boolean aliceTrustedBob = verify(pinnedBobKey, t, bobSignature);
        boolean bobTrustedAlice = verify(pinnedAliceKey, t, aliceSignature);

        System.out.println("Alice verifies Bob: " + aliceTrustedBob);
        System.out.println("Bob verifies Alice: " + bobTrustedAlice);
        if (!aliceTrustedBob || !bobTrustedAlice) {
            throw new GeneralSecurityException("Unauthenticated peer");
        }

        byte[] aliceShared = agree(a.getPrivate(), b.getPublic());
        byte[] bobShared = agree(b.getPrivate(), a.getPublic());
        byte[] aliceKey = applicationKey(aliceShared, t);
        byte[] bobKey = applicationKey(bobShared, t);

        System.out.println("Derived keys equal: "
                + MessageDigest.isEqual(aliceKey, bobKey));

        // Mallory changes Bob's ephemeral X25519 public key in transit.
        KeyPair maliciousEphemeral = ephemeral.generateKeyPair();
        byte[] substituted = transcript(
                "alice", "bob", aNonce, bNonce,
                a.getPublic(), maliciousEphemeral.getPublic()
        );
        System.out.println("Substituted X25519 key accepted: "
                + verify(pinnedBobKey, substituted, bobSignature));

        // Even with the original signature, changing the expected peer ID fails.
        byte[] wrongIdentity = transcript(
                "alice", "mallory", aNonce, bNonce,
                a.getPublic(), b.getPublic()
        );
        System.out.println("Changed peer identity accepted: "
                + verify(pinnedBobKey, wrongIdentity, bobSignature));

        // Impostor may sign the correct bytes, but does not hold Bob's key.
        KeyPair imposter = identity.generateKeyPair();
        System.out.println("Impostor signature accepted: "
                + verify(
                    pinnedBobKey, t,
                    sign(imposter.getPrivate(), t)
                ));

        // Bob's old signature is invalid over a new session challenge.
        byte[] fresh = transcript(
                "alice", "bob", random(16), bNonce,
                a.getPublic(), b.getPublic()
        );
        System.out.println("Replayed old response accepted: "
                + verify(pinnedBobKey, fresh, bobSignature));

        // Local demonstration only, not a real network Finished exchange.
        byte[] confirmA = hmac(
                aliceKey,
                "auth-kex-demo:v1|confirm:alice".getBytes(StandardCharsets.UTF_8)
        );
        byte[] confirmB = hmac(
                bobKey,
                "auth-kex-demo:v1|confirm:alice".getBytes(StandardCharsets.UTF_8)
        );
        System.out.println("Key confirmation valid: "
                + MessageDigest.isEqual(confirmA, confirmB));

        Arrays.fill(aliceShared, (byte) 0);
        Arrays.fill(bobShared, (byte) 0);
        Arrays.fill(aliceKey, (byte) 0);
        Arrays.fill(bobKey, (byte) 0);
    }
}
```

Compile and run:

```bash
javac AuthenticatedKexDemo.java
java AuthenticatedKexDemo
```

Verified stdout output with compatible Java 17 APIs:

```text
Alice verifies Bob: true
Bob verifies Alice: true
Derived keys equal: true
Substituted X25519 key accepted: false
Changed peer identity accepted: false
Impostor signature accepted: false
Replayed old response accepted: false
Key confirmation valid: true
```

### 8.1. Why is substituting the X25519 public key detected?

Bob signs transcript `t`, which includes **both** `aPub` and `bPub`. When Mallory swaps `bPub` for `mPub` on its way to Alice, Alice reconstructs `substituted` from the key she sees and tries to verify Bob's original signature:

```java
verify(pinnedBobKey, substituted, bobSignature)
```

The result is `false` because the signed bytes no longer match the transcript Alice is verifying. Mallory does not possess the Ed25519 private signing key trusted for Bob's identity to forge a valid signature for the new transcript.

If Mallory swaps **aPub** on the Alice → Bob direction, Bob must likewise build/verify the transcript from the exact values received, and Alice must verify the transcript of the session she is participating in. When the two sides' transcripts differ, properly designed signing/verification and confirmation will fail the handshake.

**Note:** a valid signature is meaningful only because `pinnedBobKey` was assumed trusted and bound to Bob's identity. If the program grabbed `pinnedBobKey` from the very packet Mallory sent without checking, Mallory could simply swap the key too and self-sign: still MITM.

### 8.2. Why is changing the peer identity detected?

The transcript contains not only keys, but also identity strings **in their exact roles**. In the demo, Alice intends to talk to `bob`, so verifying Bob's signature against a transcript listing `mallory` as responder must be rejected.

In production, identity must come from **trusted application configuration or resolution**, never taking a `responder` field self-reported by the other side as the “expected identity.” This guarantee is critical to prevent **unknown key-share (UKS)**: one party believing it shares a key with a different identity even though the cryptographic secrets match.

### 8.3. Why is an impostor signature rejected?

Mallory can generate a valid Ed25519 key pair and validly sign the transcript. However, **just any valid key pair of the algorithm** is not Bob's key. Alice must verify with `pinnedBobKey`, never with a public key Mallory attaches inside the same message.

This is where PKI or pinning solves **binding a key to an identity**, while Ed25519 signatures solve **whether the signer holds the private key**.

### 8.4. Demo limitations — do not use as a production handshake

The example illustrates core principles, **not a complete wire protocol proven secure**:

- All key pairs are generated and exchanged in **one process**, so it does not model network framing, real key distribution, trust anchors, or certificate validation.
- `pinnedAliceKey` and `pinnedBobKey` are simply assigned from newly created keys; the demo **assumes** trust provisioning already occurred. Never use this pattern to “learn keys” from the network and treat them as authenticated.
- It does not model handshake state machines, retransmissions, timeouts, key updates, transcript renegotiation, or concurrent sessions.
- Untrusted X25519 public key bytes are not validated after network parsing; you need decoding/validation per provider and curve standard, rejecting malformed/low-order/all-zero secrets if the app/provider does not handle them fully.
- The demo transcript uses `getEncoded()` from Java public keys; another implementation might use raw 32-byte X25519 keys. **Specify a single wire encoding** and cross-test it; never mix encodings.
- The code does not implement full replay protection, multi-tenant identity isolation, authorization, or certificate revocation.
- Both directions currently share one demo `app-key` output. Production protocols must derive **separate send/receive keys**, distinct nonces/sequence numbers, record framing, AEAD authentication, and usage limits.
- Local `confirmA`/`confirmB` only compare two values in the same program; network key confirmation requires actually **sending and verifying Finished/MAC values with proper roles and transcripts**, not just printing `true`.
- Calling `Arrays.fill(...)` shortens the lifetime of self-owned arrays, but does not guarantee private keys and intermediate copies inside the JVM/provider are wiped immediately.
- Never design a custom hybrid/mTLS encryption protocol in place of TLS 1.3 or an audited protocol when you simply need a secure transport channel.

## 9. TLS 1.3 as a Real-World Example of Authenticated Key Agreement

For HTTPS or internal service-to-service communication, **TLS 1.3** is the standard choice instead of assembling X25519 + Ed25519 + HKDF yourself and sending data. A TLS 1.3 handshake in certificate-based server authentication mode (conceptual view) involves:

```text
Client                                              Server
------                                              ------
ClientHello
  supported versions, cipher suites,
  key_share (ECDHE), random    --------------------->
                                  <------------------ ServerHello
                                                       selected suite, key_share
                      [Both sides derive handshake traffic secrets]
                                  <------------------ EncryptedExtensions
                                  <------------------ Certificate
                                  <------------------ CertificateVerify
                                  <------------------ Finished
Client:
  validate certificate chain + expected DNS name
  verify CertificateVerify over TLS handshake transcript
  verify Finished + transcript integrity
  if all pass -> send Finished  -------------------->
                     [Application traffic keys bound to handshake]
Client/Server exchange authenticated encrypted application records
```

Key takeaways:
- **ECDHE key share** establishes the shared secret; it **does not** authenticate identity by itself.
- **Certificate** provides the server's PKI-bound identity public key; the client must verify the chain and **expected hostname**.
- **CertificateVerify** proves possession of the private signing key matching the certificate and signs a structure over the handshake transcript with a TLS 1.3-defined context.
- **Finished** is a MAC authenticating the transcript with keys derived from handshake secrets; it detects handshake mismatches/tampering and provides key confirmation per TLS design.
- **HKDF** and the key schedule derive traffic secrets per stage and direction, never using raw DH secrets directly as a single AES key.
- **mTLS** adds client certificate/proof authentication when required by the application; server authentication does not mean the client is authorized for APIs.
- TLS 1.3 also includes PSK modes, resumption, HelloRetryRequest, and many other rules; the diagram above only illustrates a common **certificate-based full handshake** and does not replace the RFC.

### 9.1. What a real client must check

Suppose a client connects to `https://payments.example.com`. A CA-signed certificate for `files.example.com` must not be accepted simply because it belongs to the same organization or same CA. The client has an **expected reference identity** of `payments.example.com` and must match the certificate identity per standard rules.

In Java, prefer standard HTTP/TLS clients (such as `java.net.http.HttpClient` or verified TLS provider configurations) and default/properly configured trust managers instead of installing:

```java
// Anti-pattern (DO NOT use):
// TrustManager that accepts every certificate
// HostnameVerifier that always returns true
```

Never use these anti-patterns to work around development environment errors. Properly add trusted CAs and ensure the server presents the right certificate, hostname, and chain; never sacrifice peer authentication just to “make it connect.”

### 9.2. The server only proves its key, so who is the client?

TLS server authentication proves the client is connecting to a server with the right PKI identity. It **does not automatically** prove the user or client application is authorized to call an API. After the handshake, the application still needs token/session/client-cert authentication or another mechanism, then authorization checks on resources.

mTLS can help bind **workload identity** to a client certificate, yet authorization must still check whether that certificate identity is permitted for the specific action/tenant. Never treat a “TLS connected” boolean as sufficient permission for everything.

## 10. Which Attacks Does Binding Identity and Keys Prevent?

### 10.1. Key substitution / classic MITM

An adversary replaces an ephemeral public key; if the transcript is signed and verified with a trusted identity key, the substitution is detected. Without authentication, both sides establish shared secrets with the attacker.

### 10.2. Unknown key-share (UKS)

A configuration or protocol flaw can lead Alice to believe a session key belongs to Bob while Bob believes he is talking to Mallory, or map keys to the wrong identity. This is dangerous even when the attacker does not directly know the shared secret.

Prevent by:
- Signing/authenticating both identities and roles;
- Checking the **expected** peer identity rather than a self-claimed identity;
- Binding transcript/traffic keys to protocol and endpoints;
- Verifying key → principal/tenant mapping and authorization.

### 10.3. Downgrade / cipher-suite confusion

If algorithms are altered by an adversary outside authenticated coverage, both sides may fall back to weak algorithms or misinterpret messages. Sign/bind the selected suite, version, KDF, curve, and cipher options; reject anything outside the allowlist. Never try “multiple algorithms until one signature passes.”

### 10.4. Replay and session identity

A signature over an old transcript becomes invalid once a party generates a fresh nonce/ephemeral key and builds a new transcript. Still, this alone does not make all operations replay-proof: applications need request anti-replay and protocol-level AEAD record nonces/sequence numbers.

### 10.5. Key compromise impersonation (KCI)

In some protocols, compromising Alice's long-term authentication key can affect various properties beyond impersonating Alice to others. KCI analysis requires examining the exact authenticated key exchange structure, whose key leaked, and who is trying to impersonate whom.

Never blindly claim a “DH + signature” pattern is immune to all forms of KCI or all key compromises; choose a protocol whose security analysis matches your threat model.

### 10.6. Forward secrecy

If every session uses **fresh ephemeral X25519 key pairs** and temporary keys are erased promptly, a later compromise of the **long-term identity signing key** does not automatically let an attacker recover old shared secrets from recorded public traffic, under the security assumptions of the scheme and protocol. This is one component of **forward secrecy**.

However, if a session key, ephemeral private key, or plaintext leaked earlier, signatures cannot “un-leak” that data. Full forward secrecy requires a properly designed and proven protocol; do not infer it merely from calling `KeyPairGenerator` each time.

### 10.7. Invalid curve / malformed public keys

When receiving X25519 public keys over the network, never assume every byte array is a safe public key. Use standards-compliant decoders/providers and key agreement implementations, handle malformed inputs, check that shared secret outputs do not hit disallowed cases (such as all-zero per X25519 guidance), and reject errors.

**Never design your own** public key conversion/decoding step or ignore provider exceptions just to “accept the key at all costs.”

## 11. Connection to Key Wrapping

The parent topic of this chapter is **key establishment and wrapping**. The two mechanisms are related but not identical:

- **Key agreement:** both sides contribute ephemeral keys and compute a shared secret (X25519/ECDH), then HKDF derives traffic keys. Ephemeral keys/peer identity must be authenticated against MITM.
- **Key wrapping/transport:** one side generates a symmetric key (CEK/DEK) and protects it so the recipient can recover it—for example, RSA-OAEP with the recipient's public key or appropriate KEM/AEAD key wrap. The **recipient's public key** must be authenticated to avoid wrapping the CEK for an attacker.

If an attacker swaps the recipient's public key in a wrapping scheme, the sender encrypts the CEK for the attacker; in key agreement, the attacker establishes two spoofed shared secrets. **The shared root problem is missing authenticated binding between the public key and the right peer.**

Frameworks like HPKE define specific security configurations and authentication modes (base/auth/PSK depending on profile). Never call every form of public-key encryption “peer-authenticated”; read the exact mode and authentication guarantees the scheme provides.

## 12. Common Mistakes and Fixes

| Mistake / claim | Why it is dangerous | Correct practice |
| --- | --- | --- |
| “X25519 gave the same secret, so it must be Bob” | An attacker can run two sessions with Alice and Bob | Verify trusted identity keys and transcript |
| “The public key has a fingerprint, so it's safe” | An attacker's key also has a valid fingerprint | Compare against a fingerprint/key from a trusted channel |
| “Sent a certificate, so hostname checking isn't needed” | Another host's cert still has a valid chain | Validate expected DNS/application identity |
| “Accept all certificates to avoid SSL errors” | Disables peer authentication, invites MITM | Configure CA/PKI properly |
| “Signing just the public key suffices for any handshake” | Fails to bind roles, nonces, suite, partner | Sign/authenticate full transcript per spec |
| “Valid signature with the attached key proves it's Bob” | Attacker generated both signing key and signature | Provision trusted keys independently |
| “Nonces can be reused across sessions” | Enables replay/session confusion | Use fresh nonces/ephemerals and track state |
| “HKDF(sharedSecret) prevents MITM on its own” | Mallory holds two separate DH secrets | Authenticate first and bind transcript/KDF |
| “Finished MAC proves the client is Alice” | An unauthenticated MITM computes MACs for his sessions | Combine Finished + identity authentication + binding |
| “TLS encryption is on, hostname verification doesn't matter” | Channel may terminate at the wrong endpoint | Full TLS certificate & name validation |
| “Once the handshake passes, every API is allowed” | Authentication does not replace authorization | Map identity to permissions and resources |
| “Try algorithms until verification succeeds” | Downgrade, protocol confusion | Enforce version/cipher allowlist, fail closed |
| “TOFU provides trusted PKI from the first connection” | First connection can still be MITM'd | Verify initial fingerprint out-of-band if needed |
| “Leaked private identity signing key is fine because of ECDHE” | Attacker can impersonate identity in future sessions | Protect/rotate/revoke signing keys |
| “Zeroing a Java byte[] guarantees all keys are gone” | JVM/provider may retain copies | Memory hygiene, scoping, KMS/HSM per threat model |
| “AEAD ciphertext has a tag, so we know Bob sent it” | Anyone knowing the key or public key can produce valid messages depending on scheme | Verify principal/sender authentication separately |

## 13. Steps to Test an Authenticated Handshake

### 13.1. Positive tests

1. Alice expects Bob; Bob's trusted identity key matches. Bob expects Alice; Alice's trusted key matches.
2. Both sides encode the transcript with identical version, encoding, roles, identities, nonces, and ephemeral public keys.
3. Both signature/MAC proofs verify successfully against **properly pinned/cert-validated keys**.
4. Shared secret and traffic keys derive identically; AEAD records in each direction use valid nonces/sequences.
5. The application checks principal authorization before processing requests.

### 13.2. Negative tests

| Test case | Condition | Expected outcome |
| --- | --- | --- |
| Swap `bEphemeralPublic` | Mallory injects a different X25519 key | Signature/transcript check fails |
| Swap `aEphemeralPublic` | Mallory alters the initiator's key | Alice and Bob cannot agree on an authenticated transcript |
| Wrong trusted identity key | Verifying with Mallory's key instead of Bob's when policy expects Bob | Bob's identity rejected |
| Impostor signature | Mallory signs with his own Ed25519 private key | Verification with trusted Bob key fails |
| Wrong peer name | `bob` replaced with `mallory` | Identity/transcript binding fails |
| Wrong role | Initiator/responder swapped | Fails per transcript/signature rules |
| Wrong version/suite | Switching X25519/HKDF profile to another algorithm | Fails, no downgrade |
| Signature from old session | Fresh nonce/challenge with old signature | Fails |
| Malformed/weak public key | Untrusted bytes, anomalous parser/curve input | Fails closed, no session key produced |
| Valid cert, wrong SAN | Server cert belongs to another host | Hostname verification fails |
| Untrusted cert chain | Self-signed unknown CA | Rejected unless explicit trust policy allows |
| Expired/revoked cert | Violates certificate policy | Rejected per validation policy |
| Wrong Finished | Shared secrets or transcripts differ | Rejected before app data |
| Replayed business request | Handshake authenticated, but command resent | Handled by replay/idempotency policy |
| Unauthorized resource | Authenticated client lacks tenant/resource permission | Authorization rejected |

In automated tests, do not merely assert “both sides derive the same key”—assert **the exact expected peer identity** and **that attack-controlled modifications are rejected**.

### 13.3. Debugging interoperability when two sides fail authentication

Reasonable check sequence:

1. Confirm protocol version, suite, and handshake state match.
2. Confirm **expected peer identity** and the source of the trusted identity public key/certificate.
3. Compare canonical transcript bytes or transcript hash using **non-sensitive test fixtures**; check field ordering, public key encoding, UTF-8, roles, nonces, and length prefixes.
4. If the transcript matches yet signature verification fails, check signature algorithm/key format, certificate identity key, signature byte encoding, and policy.
5. If signatures pass yet session keys differ, check matching ephemeral public/private pairs, X25519 provider, HKDF extract salt/info, and transcript hash.
6. If keys match yet records fail, check AEAD AAD, sequence/nonce management, and traffic-key direction.
7. If crypto passes yet API calls are rejected, check authorization policy, principal mapping, tenant/resource, and replay checks.

**Never log private keys, raw shared secrets, traffic keys, or production plaintext** to debug. When tracing is needed, prefer session IDs, algorithm names, key lengths, policy status, and transcript hashes managed under sensitive-data rules.

## 14. Pre-Production Implementation Checklist

### Client/Initiator

- [ ] Expected server identity is determined by trusted endpoint/application configuration.
- [ ] Server's trusted public key is authenticated via certificate/path/name validation or a properly provisioned pin.
- [ ] Server proves possession of the corresponding private key over the **exact session transcript**, including client nonce, server nonce, both key shares, suite, and roles.
- [ ] Never silently accept key/cert/hostname changes or “trust all” on errors.
- [ ] Derive traffic keys from the authenticated handshake using a standard key schedule with direction separation.
- [ ] Never send sensitive data before completing required handshake steps.

### Server/Responder

- [ ] Server authentication keys/certificates have a secure lifecycle, stored in a Keystore/KMS/HSM where appropriate.
- [ ] Client key shares/identities are parsed and validated per standards, with size/DoS limits.
- [ ] If client authentication is required, verify client certificate/signature/PSK against provisioned principals.
- [ ] Map client identity to tenant/role/resource only after authentication and policy checks.
- [ ] Protect against replay and manage session/key updates, sequence numbers, and nonces per protocol.

### Both sides

- [ ] Never stitch DH+hash+AES and call it a secure channel without a formal authenticated key exchange design.
- [ ] Protocol/version, suite, roles, identity, transcript, and encoding are defined and cross-tested.
- [ ] Negative tests exist: MITM key replacement, wrong identity, wrong signer, replay, downgrade, malformed key, wrong Finished.
- [ ] Policies exist for certificate/key rotation, revocation, compromise response, and auditing.
- [ ] Limits exist for session counts, timeouts, payload/key lengths, error behavior, and resource consumption.
- [ ] Ensure authentication is not confused with authorization or end-to-end identity across proxies.

## 15. Self-Check Exercises

**Q1.** Alice and Bob run X25519 successfully, but exchange public keys over unauthenticated HTTP. Can an attacker eavesdrop on data after both turn on AES-GCM?

**Answer:** Yes, if the attacker performs an active MITM by replacing public keys and establishing two separate key sessions. The attacker holds keys for both sessions and can decrypt and re-encrypt without breaking X25519 or AES-GCM.

**Q2.** The sender transmits `bPub` and `SHA-256(bPub)` in the same packet. Can Alice be sure `bPub` belongs to Bob?

**Answer:** No. An attacker can replace both. The fingerprint must be compared against a previously trusted value or verified over an independent authenticated channel.

**Q3.** Bob signs `bPub` without including `aPub` and the client nonce in the proof. What is the potential issue?

**Answer:** The proof is not sufficiently bound to the specific session and Alice's public key, which can allow replay/misbinding/unknown-key-share attacks in under-bound designs. Sign a transcript including both key shares, identities, roles, suite, and freshness.

**Q4.** A TLS server presents a CA-valid certificate, but for a different hostname. Should the client proceed?

**Answer:** No; a valid certificate chain does not prove the **expected hostname**. Verify SAN/reference identity along with certificate policy.

**Q5.** If Mallory generates his own Ed25519 key and signs Bob's exact transcript, will verification pass?

**Answer:** No, provided Alice verifies using **Bob's trusted public key**. If Alice instead uses the public key Mallory attached as the trust source, the design is broken and vulnerable to MITM.

**Q6.** Why does having the same shared secret not prove both parties intend to communicate with the same identity?

**Answer:** The secret proves key agreement succeeded mathematically, not name/key binding. You must bind expected identities and roles in an authenticated transcript and trusted-key mapping.

**Q7.** Does a valid key confirmation MAC immediately prove the peer is Bob?

**Answer:** No, if there is no peer authentication. A MITM can compute valid confirmation MACs for the two DH sessions he established. Confirmation is meaningful only within proper authentication.

**Q8.** Bob's long-term Ed25519 signing key is compromised today. What happens to new sessions and old sessions?

**Answer:** An attacker can impersonate Bob in future handshakes until the key is revoked/rotated; confidentiality of past data depends on the protocol, ephemeral private-key lifecycle, traffic keys, and whether secrets leaked. Properly designed ephemeral DH can contribute to forward secrecy, though absolute guarantees never rest on a single detail alone.

**Q9.** Is TOFU safe against MITM on the very first connection?

**Answer:** No. If an attacker is present initially, the application may store the attacker's key by mistake. Verify the initial fingerprint out-of-band when required by the security model.

**Q10.** In Java 17, `KeyAgreement.getInstance("X25519")` produces the shared secret; what is `Signature.getInstance("Ed25519")` used for?

**Answer:** X25519 derives the shared secret from two key shares; Ed25519 signs and verifies the transcript to bind the handshake to a trusted identity signing key. The two algorithms have different roles and do not replace each other.

**Q11.** Is authorization still needed after mTLS verifies the client certificate?

**Answer:** Yes. Proving identity does not automatically grant all permissions; the server must still map the principal to policies for each tenant/operation.

**Q12.** When protecting a CEK sent to Bob using RSA-OAEP instead of key agreement, do you still need to authenticate Bob's public key?

**Answer:** Yes. If an attacker replaces Bob's public key with their own, the CEK gets encrypted for the attacker. Different model, same key–identity binding problem.

## 16. Summary Diagram

```text
KEY AGREEMENT ALONE:
 Alice --- aPub --> [Mallory swaps] --- mPub --> Bob
 Alice <-- mPub --- [Mallory swaps] <-- bPub --- Bob
     |                      |                     |
  secret A-M          two shared secrets        secret M-B
     |                      |                     |
  encrypted channel <---- attacker ----> encrypted channel
  (not to Bob)           can decrypt            (not to Alice)

AUTHENTICATED KEY AGREEMENT:
 Alice <-> exchanged ephemeral public keys <-> Bob
   |                                              |
   |-- expected identity "bob"                    |-- expected identity "alice"
   |-- trusted Bob signing key                    |-- trusted Alice signing key
   |                                              |
   +---- same canonical transcript:
          version, suite, roles, identities,
          nonces, aPub, bPub
                    |
             Sign/verify transcript
                    |
             Reject substituted key
                    |
            X25519 + HKDF transcript-bound
                    |
          Direction-separated traffic keys
                    |
          Finished/key confirmation + AEAD
                    |
          Authenticate principal + authorize action
```

**Most important takeaway:** *Agreeing on the same key does not prove the key belongs to the right peer*. To prevent public-key substitution, the verifier must have a **trust anchor for identity/keys**, verify **proof over the exact current session transcript**, and then derive/use session keys according to a standardized protocol. For real-world application connections, prefer **TLS 1.3/mTLS properly configured for certificate and hostname validation** over a homegrown handshake.

### References

- RFC 7748 — *Elliptic Curves for Security* (X25519): https://www.rfc-editor.org/rfc/rfc7748
- RFC 8032 — *Edwards-Curve Digital Signature Algorithm (EdDSA)* (Ed25519): https://www.rfc-editor.org/rfc/rfc8032
- RFC 5869 — *HMAC-based Extract-and-Expand Key Derivation Function (HKDF)*: https://www.rfc-editor.org/rfc/rfc5869
- RFC 8446 — *The Transport Layer Security (TLS) Protocol Version 1.3*: https://www.rfc-editor.org/rfc/rfc8446
- RFC 5280 — *Internet X.509 Public Key Infrastructure Certificate and CRL Profile*: https://www.rfc-editor.org/rfc/rfc5280
- NIST SP 800-56A Rev. 3 — *Pair-Wise Key-Establishment Schemes Using Discrete Logarithm Cryptography*: https://csrc.nist.gov/pubs/sp/800/56/a/r3/final
- Java SE 17 API, `KeyAgreement`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyAgreement.html
- Java SE 17 API, `Signature`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html
- Java SE 17 API, `KeyPairGenerator`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyPairGenerator.html
- Java SE 17 API, `Mac`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html
