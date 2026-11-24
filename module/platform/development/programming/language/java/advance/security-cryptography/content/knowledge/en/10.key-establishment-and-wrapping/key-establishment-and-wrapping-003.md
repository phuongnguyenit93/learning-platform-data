# 10.3. The init, doPhase, generateSecret Lifecycle and Peer Key Validation

## 1. Why Is KeyAgreement Needed?

When two parties A and B communicate over an observable network, they need to establish **the same shared secret** from which to derive session keys for symmetric encryption or key wrapping. If A and B can do this without sending their private keys or the shared secret directly over the wire, we have **key agreement**.

In Java/JCA/JCE, `javax.crypto.KeyAgreement` provides the engine for algorithms such as **Diffie–Hellman (DH)**, **Elliptic Curve Diffie–Hellman (ECDH)**, and **X25519/X448** (in the XDH family). The typical two-party model is:

- A generates keypair `privateA/publicA`, B generates keypair `privateB/publicB` with the same algorithm and compatible parameters.
- A receives `publicB` and uses **privateA** to compute the shared secret.
- B receives `publicA` and uses **privateB** to compute the shared secret.
- By mathematical property, with valid keys and matching parameters, **both sides obtain the same value** without transmitting it over the network.

However, three things must never be equated:

1. **Following the API lifecycle**: `init` → `doPhase` → `generateSecret`.
2. **A technically valid peer public key**: right type, parameters/curve, encoding, and required cryptographic checks.
3. **The key actually belongs to the intended peer**: must be **authenticated via a trusted mechanism** such as a pinned key, verified certificate, or authenticated key exchange.

Steps (1) and (2) **do not guarantee step (3)**. A *man-in-the-middle* (MITM) attacker can swap public keys in transit and create **two separate key agreement sessions** if the system does not authenticate the peer's key.

**Lesson objectives:** understand `KeyAgreement` state, set `lastPhase` properly, manage `generateSecret` output, validate the peer's key across multiple layers, and then derive symmetric keys safely instead of treating the raw shared secret as a ready-to-use AES key.

## 2. Protocol-Level Mechanism: The Shared Secret Is Not Sent

Illustrating the **two-party** model:

```text
Alice                                              Bob
-----                                              ---
(privateA, publicA)                                (privateB, publicB)
         |                                            |
         |  ----- publicA (authenticated) ----------> |
         | <----- publicB (authenticated) ----------- |
         |                                            |
KeyAgreement.init(privateA)               KeyAgreement.init(privateB)
doPhase(publicB, true)                     doPhase(publicA, true)
generateSecret() -> sharedA                generateSecret() -> sharedB
         |                                            |
         +------------ sharedA == sharedB -------------+
                              |
                  KDF (HKDF + context)
                              |
              Session key for AEAD / key wrapping
```

**Public keys are not secrets.** Nevertheless, a public key received from the network is **not automatically trustworthy** just because it parses cleanly, is valid Base64, or is accepted by `KeyAgreement.doPhase`.

On A's side, the key passed to `init` is **A's own private key**; the key passed to `doPhase` is **B's public key**. Never pass B's private key to `doPhase`; never send A's private key to B. A real system must authenticate messages carrying public keys or match them against a protected trust/registration channel.

**Terminology note:** `KeyAgreement` typically *computes* a raw shared secret; it **does not encrypt** payloads, **does not create digital signatures**, and **does not wrap keys by itself**. Only after authenticating the exchange and deriving session keys can the application use `Cipher`/AEAD or an appropriate key-wrapping algorithm.

## 3. The KeyAgreement Lifecycle in JCA

### 3.1. Creating an Engine with getInstance

```java
KeyAgreement ka = KeyAgreement.getInstance("X25519");
```

You need to import `javax.crypto.KeyAgreement`. The string `"X25519"` is the **algorithm name**, not the provider. Since Java 17, standard JDKs support X25519, though systems with custom providers/crypto policies may differ; the application must configure allowed algorithms and verify support.

Do not pass `"AES"` to create a `KeyAgreement`: AES is a **symmetric encryption** algorithm, not a key agreement primitive. Likewise, `Ed25519` is used for signing/verification and **must not** be treated as an X25519 key that can be arbitrarily relabeled.

### 3.2. init(privateKey): Setting the Initial State

```java
ka.init(ownPrivateKey);
```

`init` prepares the engine with the **local party's secret key** and required parameters. For X25519, the private key corresponds to a generated X25519 keypair; for classic DH/ECDH, compatible group/curve parameters are required. Overloads allow passing an `AlgorithmParameterSpec` and/or `SecureRandom` when the algorithm/provider needs them.

Errors to know:

- `InvalidKeyException` if an unsuitable key is supplied: wrong type, wrong algorithm, or incompatible.
- `InvalidAlgorithmParameterException` if an overload is called with incompatible parameters.
- Engine creation errors such as `NoSuchAlgorithmException` may occur if the algorithm does not exist in available providers.

**`init` does not fetch the peer's public key over the network** and does not verify who the peer is. It initializes the engine state to process agreement phases.

### 3.3. doPhase(peerPublicKey, lastPhase): Processing Each Participant

In **two-party** key agreement, you typically call:

```java
ka.doPhase(peerPublicKey, true);
```

- `peerPublicKey` is the key for the current phase, usually the **other party's public key**.
- `lastPhase=true` indicates **this is the final phase**.
- For two parties, call it **once** with `true`.
- `doPhase` returns an intermediate `Key` or `null` if that phase produces no intermediate key needed by the caller. In a two-party X25519 demo, the return value is not needed.

Multi-party algorithms can use multiple phases where `false` is passed before the final phase; however, **never** assume all providers/algorithms support multi-party configurations. With standard two-party X25519/ECDH, do not pass `false` and then call `generateSecret` as if it were complete.

If the engine has not been `init`ed, `doPhase` can throw `IllegalStateException`. An unsuitable peer key can cause `InvalidKeyException`. **That `doPhase` accepts a public key does not mean that public key's identity has been authenticated.**

### 3.4. generateSecret(): Retrieving the Raw Shared Secret

After completing all required phases:

```java
byte[] rawSharedSecret = ka.generateSecret();
```

`generateSecret()` allocates **a new byte[]** containing the shared secret. Never print it to the console, send it over the network, write it to logs, or hardcode it in configuration. Even though public keys are public, the shared secret must be handled as **secret key material**.

Java 17 provides these overloads:

| Method | Meaning |
| --- | --- |
| `generateSecret()` | Creates a new `byte[]` containing the shared secret. |
| `generateSecret(byte[] target, int offset)` | Writes the secret into a caller-provided buffer; returns the number of bytes written; may throw `ShortBufferException` if space is insufficient. |
| `generateSecret(String algorithm)` | Asks the provider to create a `SecretKey` for the specified algorithm; depends on provider/algorithm support and key material compatibility, and may throw an error. |

**Do not treat `generateSecret("AES")` as a standardized, session-bound HKDF across all providers.** This overload creates a key according to the engine/provider's mechanism and does not automatically supply the full salt, transcript hash, context, and key separation a modern protocol may require. When designing a new protocol, specify an **explicit KDF**, such as HKDF-HMAC-SHA256, following a verified spec and library.

**State after `generateSecret`:** the `KeyAgreement` documentation specifies that the engine resets to its state right after the most recent `init`. You can call `doPhase`/`generateSecret` again with the same private key, or call `init` to replace the private key; **resetting state does not generate a new private key**. If the protocol uses *ephemeral ECDH* for forward secrecy, the application must actually generate a fresh keypair per session policy rather than expecting engine reset to do so.

Calling `generateSecret` before `init` or before completing the required `doPhase` calls throws `IllegalStateException`.

### 3.5. Call-Order Table

| Sequence | Valid? | Result / note |
| --- | --- | --- |
| `getInstance` → `init(ownPrivate)` → `doPhase(peerPublic,true)` → `generateSecret()` | **Yes**, two-party | Returns raw shared secret if keys, algorithm, and checks are valid. |
| `getInstance` → `generateSecret()` | **No** | Not initialized / no phase processed; illegal state error. |
| `init(ownPrivate)` → `generateSecret()` | **No** | Missing peer public key; illegal state error. |
| `init(ownPrivate)` → `doPhase(peerPublic,true)` → `generateSecret()` → `generateSecret()` | **No**, if no new phase | After the first call the engine resets; must supply the peer's key again. |
| `init(ownPublic)` → `doPhase(peerPrivate,true)` | **Wrong key types** | Private key belongs in `init`; peer public key belongs in `doPhase`. |
| `init(ownPrivate)` → `doPhase(peerPublic,false)` → `generateSecret()` | **Incomplete two-party cycle** | `false` is only meaningful when more phases remain and the algorithm supports them. |

## 4. Validating the Peer Public Key: Three Distinct Layers

**Public key validation is not a single check.** To answer “is this B's trustworthy key?”, separate at least three layers.

### Layer 1 — Representation and Input Validation

- Is the public key data within the size limits, format, version, and encoding allowed by the protocol?
- If the protocol transmits `SubjectPublicKeyInfo` DER, use `X509EncodedKeySpec` with the corresponding `KeyFactory` rather than parsing raw bytes ad hoc.
- Enforce an **algorithm allowlist**; never let the client arbitrarily pick key types/curves from a header without policy.
- If the input is malformed, reject it rather than accepting or falling back to a weaker algorithm.

In many providers, Java's `PublicKey.getEncoded()` returns **X.509 SubjectPublicKeyInfo (SPKI)**, *not* a CA-signed X.509 certificate, and *not necessarily the raw 32-byte X25519* encoding of a wire protocol. `X509EncodedKeySpec` expects SPKI-encoded bytes; if the protocol transmits raw X25519 public keys, you must decode them according to the **protocol's** exact structure and byte order instead of wrapping them arbitrarily.

This layer only answers “is this a well-formed parseable key object?”; it does **not** yet answer “is the key valid for the group?” or “does it belong to peer B?”.

### Layer 2 — Algorithm, Parameter, and Key Value Validation

**Classic DH:** must follow approved `p, g` group parameters (and group/subgroup structure), check that the peer's public value lies in the valid range, and perform subgroup checks where required by the algorithm/group. Never invent prime groups of unknown origin.

**Traditional ECDH on Weierstrass curves** (e.g., `secp256r1`): verify the peer key has the right type, **right curve and parameters**, is not the point at infinity, has valid coordinates, and lies on the curve; where required by the group/curve, also check order/subgroup. Never accept arbitrary externally supplied curves. Use an implementation/provider with proper validation, while still enforcing a **curve policy** in the application; do not rely solely on comparing the string `"EC"`.

**X25519:** use the exact name `X25519`, type `XECPublicKey`, and parameter `NamedParameterSpec.X25519` if required by the protocol. Do not confuse with `X448` or `Ed25519`. X25519 is designed to handle point representations per RFC 7748 rules, so **do not mechanically apply Weierstrass ECDH point-validation formulas** to X25519 public keys. RFC 7748 allows checking for an **all-zero** raw shared secret and rejecting if it occurs; the Java example below includes this rejection step. A provider may reject invalid public keys/outputs during `doPhase` or `generateSecret`; this is **cryptographic validity checking**, not a substitute for identity verification.

**Important:** having the same algorithm name or same public key length is **not enough** to prove validity or trustworthiness. Group/curve value validation should be delegated to a trusted cryptographic library/provider following the algorithm's RFC/standard; never ignore exceptions if the provider reports an error.

### Layer 3 — Authenticating That the Key Belongs to the Right Peer

Even a mathematically valid X25519 public key can belong to an **attacker**. A trust binding is required, for example:

1. **Key pinning:** the application stores the peer's SPKI bytes/public key fingerprint from a **trusted provisioning workflow**; at connection time, it compares directly against the received key. Requires a controlled rotation/revocation and pin-update strategy.
2. **X.509 certificates/PKI:** verify the chain up to a trust anchor, identity/hostname/service identity, key usage, effective validity, and revocation/policy as needed. `certificate.getPublicKey()` alone **does not perform those trust checks**.
3. **Signature over the key exchange transcript:** an authenticated identity signing key signs the ephemeral public keys, nonces, role identities, and protocol context. The other side verifies the signature **using a trusted key** before using the result.
4. **PSK/authenticated protocol:** embed key agreement inside a vetted protocol such as TLS 1.3 (properly configured with certificate/PSK verification), instead of inventing a custom protocol on raw ECDH.

**Without Layer 3 checks, there is no peer authentication.** `KeyAgreement` alone provides the ability to compute a shared secret; it **does not** know the peer's name, tenant, or authorization to sign contracts.

## 5. Runnable Java 17+ Demo: X25519 and Public Key Checks

This demo creates three keypairs: Alice, Bob, and a key-substituting party. It verifies the following points:

- A and B each use **their own private key** and **the other's public key** through the `init` → `doPhase(..., true)` → `generateSecret()` lifecycle.
- A and B obtain the same **32-byte** X25519 raw shared secret.
- Transmitted **SPKI-encoded** public keys are parsed via `KeyFactory` and checked for key type and algorithm parameters.
- “Trusted Alice public key” in the demo is a **simulated pin provisioned out-of-band**. The substitute party's public key does not match the pin.
- Bob using the substitute public key computes a **different secret** from the A–B secret. This simulates the MITM risk, not a complete authentication protocol.
- If `generateSecret` is called before `doPhase`, the engine rejects it due to invalid state.

Create file `KeyAgreementLifecycleDemo.java`:

```java
import java.security.GeneralSecurityException;
import java.security.InvalidKeyException;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.interfaces.XECPublicKey;
import java.security.spec.NamedParameterSpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;
import javax.crypto.KeyAgreement;

public final class KeyAgreementLifecycleDemo {
    private static PublicKey parsePeerX25519(byte[] spki)
            throws GeneralSecurityException {
        if (spki == null || spki.length == 0 || spki.length > 1024) {
            throw new InvalidKeyException("Invalid peer key encoding size");
        }
        PublicKey result = KeyFactory.getInstance("X25519")
                .generatePublic(new X509EncodedKeySpec(spki));
        if (!(result instanceof XECPublicKey xec)
                || !(xec.getParams() instanceof NamedParameterSpec params)
                || !"X25519".equals(params.getName())) {
            throw new InvalidKeyException("Unexpected peer key parameters");
        }
        return result;
    }

    private static byte[] agree(PrivateKey ownPrivate, PublicKey peerPublic)
            throws GeneralSecurityException {
        KeyAgreement agreement = KeyAgreement.getInstance("X25519");
        agreement.init(ownPrivate);
        agreement.doPhase(peerPublic, true);
        byte[] shared = agreement.generateSecret();
        int nonzero = 0;
        for (byte b : shared) nonzero |= b & 0xff;
        if (nonzero == 0) {
            Arrays.fill(shared, (byte) 0);
            throw new InvalidKeyException("Rejected all-zero shared secret");
        }
        return shared;
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
        KeyPair alice = generator.generateKeyPair();
        KeyPair bob = generator.generateKeyPair();
        KeyPair attacker = generator.generateKeyPair();

        // In production this pin must be provisioned via a trusted channel.
        byte[] trustedAliceSpki = alice.getPublic().getEncoded();
        PublicKey aliceFromWire = parsePeerX25519(
                alice.getPublic().getEncoded());
        PublicKey bobFromWire = parsePeerX25519(
                bob.getPublic().getEncoded());
        PublicKey fakeAlice = parsePeerX25519(
                attacker.getPublic().getEncoded());

        System.out.println("Trusted peer pin matches: " +
                Arrays.equals(trustedAliceSpki, aliceFromWire.getEncoded()));
        System.out.println("Substituted peer passes pin: " +
                Arrays.equals(trustedAliceSpki, fakeAlice.getEncoded()));

        byte[] secretAlice = agree(alice.getPrivate(), bobFromWire);
        byte[] secretBob = agree(bob.getPrivate(), aliceFromWire);
        byte[] wrongSecretBob = agree(bob.getPrivate(), fakeAlice);
        try {
            System.out.println("X25519 secret bytes: " + secretAlice.length);
            System.out.println("Both parties agree: " +
                    MessageDigest.isEqual(secretAlice, secretBob));
            System.out.println("Wrong peer yields same secret: " +
                    MessageDigest.isEqual(secretAlice, wrongSecretBob));

            KeyAgreement unfinished = KeyAgreement.getInstance("X25519");
            unfinished.init(alice.getPrivate());
            boolean rejected = false;
            try {
                unfinished.generateSecret();
            } catch (IllegalStateException expected) {
                rejected = true;
            }
            System.out.println("No doPhase rejected: " + rejected);
        } finally {
            Arrays.fill(secretAlice, (byte) 0);
            Arrays.fill(secretBob, (byte) 0);
            Arrays.fill(wrongSecretBob, (byte) 0);
        }
    }
}
```

Compile and run (JDK 17+ with an X25519 provider):

```bash
javac KeyAgreementLifecycleDemo.java
java KeyAgreementLifecycleDemo
```

Verified stdout:

```text
Trusted peer pin matches: true
Substituted peer passes pin: false
X25519 secret bytes: 32
Both parties agree: true
Wrong peer yields same secret: false
No doPhase rejected: true
```

### 5.1. Why Does Stdout Always Follow This Structure?

The keypairs are generated randomly on each run, so the raw public/private/shared secret bytes **change** and are not printed. However:

- The `aliceFromWire` copy parsed from Alice's own SPKI will match the demo pin `trustedAliceSpki`.
- The substitute keypair's public key differs from Alice's pin, so pin verification yields `false` (with negligible mathematical key-collision probability, not as an absolute security test).
- By X25519's properties, Alice and Bob compute the same 32-byte shared secret. When Bob computes with a different keypair's public key, the result does not match the A–B secret.
- Calling `generateSecret` without calling `doPhase` violates the API contract and throws a state error.

The `MessageDigest.isEqual` line is only used to **demonstrate in the demo that two byte arrays match or differ**. In production applications, never send both parties' raw secrets over the network to compare them; doing so **exposes the session secret**. Use an authenticated session confirmation method (such as a finished message/MAC over the transcript) per a well-designed, verified protocol.

### 5.2. What the Demo Checks and Does Not Check

`parsePeerX25519` enforces a **1,024-byte demo size limit** (this is an illustrative policy, **not** a standard RFC 7748 threshold); it parses DER-SPKI with `KeyFactory` and verifies `XECPublicKey` has `NamedParameterSpec` X25519. It does **not** verify that the key belongs to Alice/Bob; the pin step illustrates trust.

In particular, `trustedAliceSpki` is taken directly from Alice's keypair in the same program; this **does not replicate key provisioning between two real machines**. In production, the receiver must obtain the trusted public key beforehand/via a trust anchor—never create a “pin” by saving whatever public key was just received over an untrusted connection and claiming MITM protection.

Using `Arrays.equals` for the **SPKI public key** is appropriate in this demo because those public bytes are not secret. For raw shared secrets, the demo uses `MessageDigest.isEqual` instead of logging/displaying them. The two raw secret arrays received by the application are wiped with `Arrays.fill` when no longer needed; this erasure is only best-effort for **those specific byte[]s** and does not prove every copy in the JVM/provider was erased.

### 5.3. Checking for an All-Zero Shared Secret

RFC 7748 for X25519 notes that implementations may check for an all-zero output and abort to mitigate risks from certain *small-order* inputs. The `agree` method ORs across **all bytes** rather than stopping at the first non-zero byte, and rejects if all are zero. If the provider rejects an invalid key directly inside `doPhase`/`generateSecret`, that flow must also be treated as an error and **never** fall back to another shared secret.

An all-zero check **is not peer authentication**: a valid X25519 public key controlled by an attacker still yields a non-zero shared secret. It must be combined with a trust/identity layer before considering the session trustworthy.

## 6. Man-in-the-Middle Attack When Running KeyAgreement Alone

Suppose Eve sits between Alice and Bob, intercepting public keys and substituting Eve's own keys:

```text
Alice                 Eve (MITM)                      Bob
  |                        |                           |
  | ---- publicAlice ----> |                           |
  |                        | -- publicEve1 ----------> |
  | <---- publicEve2 ----- |                           |
  |                        | <-------- publicBob ----- |
  |                        |                           |
secret(Alice, Eve2)   2 secrets with both sides   secret(Bob, Eve1)
  |                        |                           |
  +---- each pair computes a valid shared secret ------+
     BUT Alice and Bob do NOT share the same secret
```

Eve can use the session key shared with Alice to read/rewrite messages, then create new messages protected under the other session key shared with Bob, if the protocol does not authenticate the key exchange and lacks additional protections.

**Distinguish two outcomes:**

- `doPhase` succeeds: only proves the public key is algorithm-compatible, **does not prove identity**.
- `generateSecret` returns nonzero bytes: proves agreement with *some* public key completed, **does not prove the intended peer participated**.

**Countermeasures:** authenticate public keys and handshake messages using trusted certificates/signatures/PSKs, verify participant identities, and **bind the entire transcript** (A/B roles, public keys, algorithm, session ID/nonces, version, and context) into key derivation and confirmation. For typical applications, prefer **TLS 1.3 or an audited protocol** rather than inventing a custom key-exchange protocol.

## 7. From Raw Secret to AES, MAC, or Wrapping Keys

### 7.1. Why Not Use the Raw Shared Secret Directly?

The agreed secret is **keying material**, not automatically a compliant `SecretKey` for every purpose. The protocol must:

1. Validate the algorithm, parameters, and inputs.
2. Authenticate the public keys/context according to the threat model.
3. Use a specified **KDF** to extract and derive one or more keys from the raw secret.
4. Feed **transcript/context information** into derivation: algorithm name, version, public keys, A/B roles, nonces/session ID, and usage purpose.
5. Derive **purpose-separated keys**: such as an A→B AES-GCM key, B→A AES-GCM key, key-confirmation MAC key, or key-wrapping key.

A common approach is **HKDF** (`Extract` and `Expand` per RFC 5869) over the shared secret, with an explicitly agreed salt and `info`. Conceptual example (not runnable Java code):

```text
sharedSecret = X25519(privateLocal, publicPeer)

transcriptHash = Hash(protocolVersion || algorithms || roleIds
                   || publicAlice || publicBob || nonces || context)

PRK = HKDF-Extract(salt, sharedSecret)
clientWriteKey = HKDF-Expand(PRK, "client_write" || transcriptHash, keyLen)
serverWriteKey = HKDF-Expand(PRK, "server_write" || transcriptHash, keyLen)

Zero out application-owned raw sharedSecret / temporary PRK after use.
```

The quoted strings here are **illustrative purpose labels**, not the standard format of TLS or any existing protocol. In practice, you must use an unambiguous encoding and clearly define `salt`/`info`, key direction, version, key lengths, AEAD selection, and replay-protection state. Without an audited protocol design, do not implement your own HKDF/handshake solely from this diagram.

Java 17 **does not mandate a universal HKDF API across all providers**. You can use an approved cryptographic library to perform standard HKDF or use an integrated standard protocol. Never use `new SecretKeySpec(rawSharedSecret, "AES")` as a default key-schedule shortcut for a new protocol.

### 7.2. Connection to Key Wrapping

Once you have a **key-encryption key (KEK)** properly context-derived from key agreement, the application can use a designated **key wrap** algorithm or AEAD to protect a **data-encryption key (DEK)**, then send the wrapped data to the other side.

`KeyAgreement.generateSecret()` **does not perform wrap/unwrap itself**, does not produce ciphertext, and does not replace `Cipher`. Successful unwrapping must be combined with peer/key-transcript authentication and key-usage policy; a cryptographically well-derived key belonging to the wrong peer can still cause severe security failures.

## 8. Maintaining State, Key Lifetimes, and Distinguishing Key Types

### 8.1. Ephemeral vs. Static Private Keys

- **Ephemeral keypair:** generated per session/handshake; once finished, avoid reuse and clean up references/buffers as supported by the provider. This is a core component of many protocols offering forward secrecy.
- **Static keypair:** may serve identification/multi-session agreement depending on design; requires lifecycle management, private key protection, and re-evaluation of forward secrecy.
- **Signing key ≠ key-agreement key:** Ed25519 uses `Signature`; X25519 uses `KeyAgreement`. Never “relabel” or reuse the same key material across algorithms for different purposes without an analyzed specification.

**Forward secrecy** does not appear merely by calling `generateSecret`. It depends on the protocol, how ephemeral keys and authentication are combined, destruction of ephemeral private keys, and the algorithm's security assumptions.

### 8.2. Do Not Share Mutable Engines Across Threads

`KeyAgreement` is a stateful object: `init` and `doPhase` mutate its processing state. Never share **one instance** across concurrent sessions or different peers assuming the engine isolates them. Each handshake should have its own engine and key material. After `generateSecret`, running a new exchange requires calling `doPhase` (and often `init` with a fresh key) according to the design.

### 8.3. Never Log Private Keys or Shared Secrets

You may log non-sensitive metadata (algorithm, key identifier, accept/reject outcome, sanitized errors), but never log `privateKey.getEncoded()`, raw secrets, session keys, KDF intermediate keys, or sensitive request payloads. If a key is exported as a `byte[]`, wipe the caller-owned copy after use; note this still **does not prove** the provider/GC/JVM wiped every trace in memory.

### 8.4. Checking keyId Is Not Authentication

A `keyId` field sent over the network can be used to **look up** a public key in a trusted registry. However, the `keyId` string itself can be chosen by an attacker; only accept a key when the registry, trust policy, authentication, and authorization all align. Prevent tenant confusion, signing/agreement purpose confusion, algorithm confusion, and downgrade attacks.

## 9. Common Java Errors and How to Handle Them

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| `NoSuchAlgorithmException` at `getInstance("X25519")` | Provider/JDK lacks support or policy disallows it | Choose a verified JDK/provider; configure an approved algorithm list. |
| `InvalidKeyException` at `init` | Passed public key instead of private key, wrong type, or wrong parameters | Pass only the local private key of the matching algorithm. |
| `InvalidKeyException` at `doPhase` | Peer key has wrong algorithm/curve, invalid input, or provider rejected it | Check DER/curve/type/policy and reject; never disable validation. |
| `IllegalStateException` at `doPhase` | Engine not initialized | Start with `init`. |
| `IllegalStateException` at `generateSecret` | Not initialized or phases incomplete | For two parties, call `doPhase(peer,true)` first. |
| `ShortBufferException` from `generateSecret(buffer,offset)` | Caller buffer too small | Allocate a sufficiently large buffer or use `generateSecret()` for a new `byte[]`; never use a partial secret. |
| `InvalidKeySpecException` from `KeyFactory.generatePublic` | Malformed SPKI DER or unparseable key | Reject malformed data; do not guess or swallow errors. |
| Secrets differ between the two sides | Wrong public/private key, peer substituted, wrong group, or mismatched keypair | Verify peer public key identity/trust and transcript; never send secrets to compare directly. |
| All-zero shared secret in X25519 | Peer public key may relate to small-order input or substitution | Reject the shared secret and session; let the provider validate per RFC. |
| Creating an AES key directly from raw secret | Missing KDF, key separation, and session binding | Use a protocol-designed KDF such as HKDF. |
| Handshake runs but MITM still succeeds | Only validated format/curve, did not authenticate identity | Pin/trust certificates, signatures, or use authenticated TLS. |
| Reusing engine/private key while expecting forward secrecy | Misunderstanding `generateSecret` state reset | Generate fresh ephemeral keypairs per session/policy. |

**Distinguish technical errors from security conclusions:** rejecting invalid inputs is right. But if a forged public key is completely well-formed and `doPhase` throws no error, that result **does not** let you skip authenticating the key's source.

## 10. Before–After Scenario: Validating the Peer Properly

### Before: only parse the key and finish agreement

```text
Receive publicKey bytes from socket
-> KeyFactory.generatePublic(bytes)
-> KeyAgreement.init(myPrivate)
-> KeyAgreement.doPhase(peerPublic,true)
-> byte[] secret = generateSecret()
-> Use secret as encryption key
```

Problems: the public key could be substituted by an attacker; missing identity authentication, missing KDF, missing protocol context, and missing key separation. Agreement can complete with an attacker.

### After: verify both structure and key provenance

```text
Receive size/format-bounded handshake envelope
-> Check version + algorithm allowlist
-> Parse peerPublic according to specified encoding
-> Validate key type, parameters, curve/group, and value per standard/provider
-> Authenticate peer key via pin/truststore/transcript signature/PSK
-> Verify role/identity/scope/tenant and anti-downgrade
-> Generate ephemeral private, KeyAgreement.init(privateLocal)
-> doPhase(authenticatedPeerPublic,true) -> generateSecret()
-> Reject anomalous outputs like all-zero X25519 (if provider did not already)
-> Context/transcript-bound KDF + derive separate session keys
-> Key confirmation/finished message per protocol
-> Process payload only after handshake and policy succeed
```

**This is a conceptual flowchart, not a complete protocol.** Key verification and transcript contents may follow different ordering/choreography in TLS and standard protocols. Applications should build on a protocol with a complete security design rather than assembling steps into an ad-hoc protocol.

## 11. Review Questions and Hands-On Exercises

1. What must two DH/ECDH parties transmit to compute the same shared secret? Why not send the private key?
2. In `KeyAgreement`, which key does `init` take and which key does `doPhase` take? If swapped, where might errors appear?
3. For two-party key agreement, why `doPhase(peer,true)` instead of `false`? When might `false` be used?
4. What does `generateSecret` return? Does it encrypt messages, authenticate the peer, or create an AES key with a complete KDF on its own?
5. After `generateSecret`, what state is the engine in? Does it automatically generate a new ephemeral private key?
6. Why does `KeyFactory.generatePublic` succeeding **not prove** the key belongs to the expected server?
7. Compare the checks needed for classic DH, ECDH on `secp256r1`, and X25519; what differs in group/point validation?
8. If Alice and Bob suffer a MITM swapping public keys, will `doPhase` necessarily throw an exception? Why?
9. Does pinning a public key by saving whatever key was just received on an untrusted channel protect the first connection? What kind of trust source is needed?
10. Why should the raw shared secret be combined with HKDF and the transcript to derive purpose-specific keys?
11. Why does an X25519 all-zero check not prove the key came from the right peer?
12. To use agreement output for **key wrapping**, which steps belong to `KeyAgreement` and which belong to the KDF and `Cipher`/key-wrap algorithm?

**Exercise A:** run `KeyAgreementLifecycleDemo`. Replace Bob's public key with a newly generated X25519 keypair, verify that Alice and Bob's secrets no longer match, yet the engine can still complete agreement with the new key. Explain why checking only the algorithm is insufficient.

**Exercise B:** try calling `generateSecret` before `doPhase`, and after calling `generateSecret` the first time without running a new phase. Observe `IllegalStateException` per the engine lifecycle.

**Exercise C:** simulate a registry containing the peer's SPKI provisioned over a trusted channel; verify that a format-valid public key that **does not match the pin** is rejected before using the secret. Try using a certificate chain with a proper trust anchor in a separate lab to see how trust verification differs from `KeyFactory` parsing.

**Exercise D:** design a transcript containing protocol version, algorithm name, A/B roles, both public keys, and a session nonce. Specify unambiguous serialization along with HKDF `info` rules; distinguish A→B and B→A keys; test that altering any authenticated context field causes session confirmation to mismatch.

## 12. Official References

- [KeyAgreement (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyAgreement.html): `getInstance`, `init`, `doPhase`, `generateSecret`, `lastPhase`, and state-reset behavior.
- [KeyFactory (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyFactory.html): constructing public keys from `KeySpec` and format checking.
- [X509EncodedKeySpec (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/X509EncodedKeySpec.html): public keys encoded as X.509 SubjectPublicKeyInfo.
- [XECPublicKey (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/interfaces/XECPublicKey.html): public keys for the XEC/XDH family, curve parameters, and coordinates.
- [NamedParameterSpec (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/NamedParameterSpec.html): parameter names `X25519`, `X448`, and related algorithm families.
- [RFC 7748 — Elliptic Curves for Security](https://www.rfc-editor.org/rfc/rfc7748): X25519/X448, Diffie–Hellman, byte representation, small-order cases, and all-zero shared secrets.
- [RFC 5869 — HMAC-based Extract-and-Expand Key Derivation Function](https://www.rfc-editor.org/rfc/rfc5869): HKDF-Extract, HKDF-Expand, and key-separation purposes.
- [Java Security Standard Algorithm Names (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): algorithm names `X25519`, `ECDH`, and key standards.
