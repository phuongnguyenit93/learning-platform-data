# 1.5. Relationships Among Keys, Algorithms, Parameters, Protocols, and Identities

In applied cryptography, saying "the system uses AES-256" or "the API has a TLS certificate" is not enough to conclude the system is secure. A genuine security mechanism is formed only when the **right key** is used with a **suitable algorithm**, **valid parameters**, inside a **protocol with clear ordering and verification rules**, while binding the cryptographic outcome to a **trusted identity**.

After this lesson, learners should be able to:
- Distinguish the roles and relationships of keys, algorithms, parameters, protocols, and identities.
- Explain why a valid signature, successfully decrypted ciphertext, or completed TLS connection may still be insufficient to trust a peer.
- Recognize how parameters such as nonces, salts, AAD, tag length, and protocol versions affect security.
- Design a data protection flow with appropriate identity verification, key management, tamper protection, and replay resistance.
- Connect that model to cryptographic APIs in Java 17+.

## 1. The Five Components and the Questions Each Answers

| Component | Main Question | Example | Common Mistake |
| --- | --- | --- | --- |
| **Key** | Who holds which secret/cryptographic capability? | Session AES key, Ed25519 private key, server public key, PSK | Assuming knowing the algorithm name suffices to decrypt; exposing keys in logs |
| **Algorithm** | What is the information-protection operation? | AES-GCM, Ed25519, SHA-256, HMAC-SHA256, HKDF, ECDHE | Using a plain hash to authenticate data against an active adversary |
| **Parameters** | Under what configuration and for which message is the algorithm operated? | 128/256-bit key, 96-bit nonce, 128-bit tag, AAD, salt, curve, hash, work factor | Reusing a GCM nonce with the same key |
| **Protocol** | What do parties send, in what order, what do they verify, and how are errors handled? | TLS 1.3 handshake, AEAD record format, key exchange and rotation rules | Strong algorithms without handshake authentication or replay protection |
| **Identity** | Which entity is the key or cryptographic result bound to, and on what trust basis? | DNS name in certificate SAN, service account, user, device | Accepting a signature from any public key supplied by the sender itself |

Read sequentially:

```text
Security goals + threat model
             ↓
Identify identities and trust relationships to prove
             ↓
Choose a protocol with negotiation, verification, and failure rules
             ↓
Protocol selects appropriate algorithms, keys, and parameters
             ↓
Cryptographic operation produces output; receiver verifies before using
```

The layers constrain one another. A key has no practical meaning without knowing its purpose, algorithm, and usage rights. A signature only proves **possession of the signing key**; authenticating identity requires knowing why the corresponding public key is trusted to belong to the target principal. A protocol cannot be secure if it skips verification error handling or accepts weak parameters.

## 2. Keys: Cryptographic Assets and Privilege Scope

### 2.1. Symmetric, Asymmetric, and Session Keys

- **Symmetric:** two parties share one secret key `K`. AES-GCM uses `K` to encrypt and produce an authentication tag; the decrypting party also needs `K`. HMAC uses a symmetric key to authenticate messages, but does not encrypt content. Because multiple parties may hold `K`, a valid tag **does not uniquely prove who the sender is**.
- **Asymmetric:** a pair consisting of a private key `sk` and a public key `pk`, mathematically related by the algorithm. For digital signatures, `sk` signs and `pk` verifies; the verifier never needs `sk`. A public key is not an "encrypted secret."
- **Long-term keys:** such as a server's TLS private key or root keys managed in KMS. They carry dedicated roles and lifecycles.
- **Ephemeral/session keys:** established or derived for a specific connection, session, purpose, or traffic direction. TLS 1.3 typically uses ephemeral key-exchange secrets and HKDF to derive traffic keys; keys encrypting records differ from the private key authenticating the server.

**Do not equate passwords with cryptographic keys.** Passwords typically have low entropy and require dedicated password derivation/hashing functions with salts and suitable computational cost (e.g., Argon2id via a vetted library; PBKDF2 where compatibility is required). HKDF is suited for deriving keys from already high-entropy key material, not for turning a weak password into a strong key.

### 2.2. Keys Must Be Bound to Purpose and Lifecycle

Minimum governance metadata for a key includes: `keyId`, allowed type/algorithm, purpose (`encrypt`, `sign`, `derive`…), owner/trust domain, version, status (active/retired/revoked), validity period, storage location, and rotation rules.

`keyId` is merely a **lookup label**, not proof of identity or a secret. If a data packet claims `keyId=server-prod`, the receiver must still fetch the key from a trusted store and check that the key is authorized for the operation at hand. Never let an untrusted party pick arbitrary keys to bypass checks.

Practical principles:
1. Generate secret keys with a suitable cryptographic random source; `java.util.Random` is not for key generation.
2. Restrict key distribution and usage rights; prefer keystore/KMS/HSM according to risk, avoiding keys in source code, URLs, or logs.
3. Isolate keys by environment, tenant, purpose, and traffic direction as required by the protocol; derive using a KDF with appropriate labels/context.
4. Rotate and revoke keys via defined procedures; older data may need older decryption keys during retention periods. Revoking a certificate/signing key affects trust in subsequent signatures and sessions.
5. Clarify the blast radius of key compromise: a leaked symmetric key can affect both confidentiality and integrity of data encrypted under it; a leaked signing key allows signature forgery within the associated trust scope.

## 3. Algorithms: Each Category Solves a Different Problem

| Category | Core Property | Typical Examples | Does Not Guarantee by Itself |
| --- | --- | --- | --- |
| Authenticated Encryption (AEAD) | Data confidentiality + detection of ciphertext/AAD tampering when tag check succeeds | AES-GCM, ChaCha20-Poly1305 | Does not identify a single individual if multiple parties share the key; does not prevent replay |
| Digital Signatures | Verifies data is bound to the matching public key and unmodified after signing | Ed25519, ECDSA, RSA-PSS | Does not keep content secret; does not prove `pk` belongs to an authorized party |
| MAC | Integrity and authentication among parties sharing a secret | HMAC-SHA256 | Not publicly verifiable; hard to attribute to one party when many hold the key |
| Cryptographic Hash | Produces a digest with collision/preimage resistance by design | SHA-256, SHA-384 | Does not authenticate against an adversary able to alter both content and digest |
| KDF | Derives keys with proper context and output length | HKDF, PBKDF2 (for passwords) | Cannot compensate for poor input entropy |
| Key Exchange/Agreement | Establishes a shared secret without sending the session key directly | (EC)DHE, suitable KEM mechanisms | Does not authenticate the peer without binding identity to the transcript |

For example: `SHA-256(message)` can detect changes when the digest is retrieved from a **trusted channel**. If an adversary can modify both `message` and digest, a bare hash does not prevent forgery. To protect data against an active adversary, choose a MAC/signature or AEAD aligned with the key model.

**Algorithm names must be sufficiently specific.** "AES" only specifies the block cipher, not the mode or integrity rules. In Java, `Cipher.getInstance("AES/GCM/NoPadding")` specifies the concrete transformation; `NoPadding` here does not mean omitting the authentication tag. Likewise, "RSA" does not distinguish RSA-PSS signing from RSA-OAEP encryption; never use "encrypting with a private key" as a substitute for digital signatures.

## 4. Parameters: Small Values That Can Decide Security

Each algorithm defines its own parameter set. There is no single "safe for everything" configuration.

| Case | Parameters to Understand | Meaning |
| --- | --- | --- |
| AES-GCM | 128/256-bit key length; nonce/IV, typically 96 bits; tag typically 128 bits; AAD | Protects confidentiality and verifies tag. **Never repeat a (key, nonce) pair across two encryptions** |
| HKDF | Hash, `salt`, `info`, output length | Derives context-specific keys; `info` can separate applications, sessions, and directions |
| Password derivation | Unique `salt`, work factor/computational cost, KDF | Increases guessing cost and prevents identical passwords from yielding identical outputs under different salts |
| Ed25519 | Algorithm and key/signature format; public-key validation policy | Algorithm family fixes the curve/mode; do not confuse with ECDSA |
| ECDSA / ECDH | Accepted curve/group, e.g., P-256 | Both sides must agree on a valid group; authentication remains a separate step |
| RSA-PSS | Hash function, MGF, salt length, verification parameters | Signer and verifier must agree on configuration |
| TLS 1.3 | Version, AEAD/HKDF hash suite, key exchange group, signature algorithm, certificate policy | Checked negotiation, preventing an adversary from forcing disallowed configurations |

Three easily confused concepts:

- **Nonce/IV:** a value used for one encryption per mode rules; usually not secret. In AES-GCM, ensuring uniqueness per key is vital. A 96-bit random nonce works in small demos, while high-throughput/distributed systems must manage collision probability, bound key usage counts, and design a unified nonce allocation strategy; properly partitioned counters may be used.
- **Salt:** usually a public value fed into derivation/hashing, e.g., preventing identical passwords from producing identical hashes under different salts. Salt does **not** replace keys or input entropy.
- **Tag:** authentication output (e.g., GCM authentication tag); the decryptor must verify it succeeds before trusting and using plaintext. Never ignore authentication exceptions.

**AAD (Additional Authenticated Data)** is data that does not need encryption yet requires integrity protection, such as envelope version, message type, tenantId, or resourceId. Encryptor and decryptor must supply the exact same AAD. AAD does not hide values from observers and does not decide who is authorized to access the data.

Consider an incident: two requests from two tenants are encrypted with the same key; if the format only holds ciphertext and nonce, a valid ciphertext could be transplanted into another tenant's context if the application fails to bind/check tenant at the protocol layer. Putting context identifiers in AAD **and** enforcing business authorization prevents this confusion. Never treat a client-claimed field as a trusted identity.

## 5. Protocols: Combining Primitives into Verifiable Guarantees

A protocol defines **roles, sequence, format, state, checks, and error handling**. Using the exact same AES-GCM and Ed25519, two different protocols can provide different security guarantees.

At minimum, a protocol must answer:
1. Who initiates? Who is sender/receiver? From which trusted config or context is expected identity obtained?
2. By what rules do both sides pick algorithm/version/parameters? Is there an allowlist and rejection rule for weak/unknown algorithms?
3. Where do keys come from: configured keys, ephemeral keys, KDF, key exchange, or KMS? Are keys bound to session, role, and peer?
4. Which bytes are encrypted, signed, or placed in AAD? Is data canonically encoded with clear message-type and version framing?
5. When does the peer verify tags/signatures/certificates/hostnames and usage permissions? Does it reject all failures before running business logic?
6. Are **replay**, **downgrade**, key/peer confusion, out-of-order messages, and retry/idempotency handled?

### 5.1. TLS 1.3 Example: Binding Keys, Algorithms, Parameters, and Identities

A standard TLS 1.3 connection authenticating the server via certificate can be visualized as:

```text
Client                                              Server
  |-- ClientHello: TLS version, suites, key_share --->|
  |<-- ServerHello: valid choice, key_share ----------|
  |             establish handshake secrets           |
  |<-- Certificate, CertificateVerify, Finished ------|
  |  verify chain, SAN/hostname, transcript signature |
  |-- Finished -------------------------------------->|
  |<========== bidirectional AEAD application data ====>|
```

This is a **simplified diagram** of certificate-based authentication, not every TLS 1.3 handshake mode. TLS 1.3 also supports PSK and resumption; clients can be authenticated via certificates when mTLS is configured.

Role of each layer:
- **Algorithms/parameters:** parties negotiate AEAD, HKDF hash, key-share group, and signature algorithms per TLS 1.3 rules. A cipher suite like `TLS_AES_128_GCM_SHA256` indicates the AEAD and associated hash, and **does not itself dictate** the key exchange group or signature algorithm.
- **Keys:** secrets from key establishment/PSK pass through the key schedule, deriving separate handshake and application traffic keys for distinct purposes. The server's long-term private key proves identity via signature when using certificates; it is never sent over the network.
- **Protocol:** the handshake transcript and confirmation messages cryptographically bind parameter selection, keys, and authentication; an adversary cannot arbitrarily alter them and still pass cryptographic checks.
- **Identity:** the client validates the certificate trust path **and** expected server name against SAN DNS/IP entries, along with applicable validity/policy rules. Seeing a padlock or receiving any arbitrary certificate is insufficient to conclude you reached the right server.

An HTTPS connection protects a **transport channel** to an endpoint authenticated under policy; it does not authorize the user's actions, protect data after TLS termination, or prevent server-side authorization bugs.

### 5.2. AEAD Does Not Prevent Replay on Its Own

A message with a valid `ciphertext + tag` can still be an **old** message re-sent. The tag verifies integrity and key possession, not inherently the freshness of the event. Application protocols need `messageId`/sequence numbers/counters/timestamps+windows or one-time tokens paired with state checks aligned with retries and idempotency. The integrity-protected bytes themselves must include the anti-replay context.

## 6. Identity: From "Right Key" to "Right Authorized Entity"

Consider two distinct questions:

- **Cryptographic authentication:** was the message/handshake created by a party holding the matching key?
- **Identity binding:** which service/user/device is the key trusted to belong to, and on what trusted source is that verified?

Then comes **authorization**: is the authenticated entity allowed to perform this specific operation on this resource? Successful authentication does not replace authorization.

### 6.1. Digital Certificates and Identity–Key Mapping

An X.509 certificate holds a public key, identifying attributes (e.g., `subjectAltName`), validity period, and usage constraints; a CA's signature supports verifying that binding along a trust chain. For HTTPS verification, typically validate the chain to a proper trust anchor, hostname/SAN, validity, and applicable key/certificate usage policies; revocation checks depend on system policy and configuration. A self-signed certificate is not trusted by default; it is suitable only if explicitly trusted/pinned via an established process.

A valid certificate for `api.example.com` does not mean every call from that server holds database admin privileges. Certificates and connection identity are **inputs** to authorization policies, not authorization policies themselves.

Binding examples:
- `service-account/orders-prod` → one or more keys/certificates issued/managed by a trusted registry.
- `api.example.com` → certificate with matching SAN and chain to a trusted CA; the client already has the **expected name** from URL/config.
- `user:alice` → authenticated by the application via identity mechanisms (session/OIDC, etc.) and mapped to permissions; never assign a user based solely on a client-sent `keyId`.

In practice, an identity can change keys during rotation; a key can serve a restricted scope; revoked or expired keys must be handled according to policy at verification time.

### 6.2. Why Can "verify(signature) = true" Still Be Fooled?

An adversary generates their own key pair, signs `transfer 100`, and sends both the signature and their self-generated public key. Verification naturally returns `true`. If the server uses that received public key as the sole source to conclude the CFO signed it, the system suffers from **identity/key substitution**.

The right approach: obtain keys/certificates from a vetted registry, trust store, or verification flow; confirm the principal is authorized to sign that command type; ensure the signature covers exact content and context (version, command type, account, tenant, nonce/requestId) before execution.

**Signatures do not encrypt messages.** A valid signature also does not automatically establish "non-repudiation" in every legal/operational context: that depends on key protection, identity policies, and system evidence.

## 7. End-to-End Problem: Sending Payment Commands Between Two Services

Suppose `orders-service` sends a payment request to `payment-service`. Goals: do not expose figures in transit, prevent modifying recipient/amount, reject duplicate requests, and allow only the right service/tenant to call the API.

A design may combine these layers:

1. **Connection identity:** client configures the expected server URL; uses TLS 1.3/HTTPS with certificate verification. If mTLS is applied, `payment-service` also verifies client identity via certificate and maps it to a service principal.
2. **Application authorization:** validates access tokens or service authorization per policy; checks issuer, audience, validity window, permissions, and tenant; never treat mTLS or a valid token as blanket authority over all payments.
3. **Business protocol:** defines exact body and framing, unique `requestId`, version, and TTL. Server stores/queries an idempotency key to handle retries safely and reject policy-violating replays.
4. **Additional encryption if needed:** if data must stay protected beyond TLS termination, apply message-level AEAD; keys reach only the intended application endpoints, binding `version|tenantId|requestId|messageType` in verified AAD.
5. **Provenance verification if needed:** sign the canonical representation of the command with a signing key bound to `orders-service`. `payment-service` verifies the signature with a trusted registered key, then checks principal authorization before processing.
6. **Lifecycle:** rotate keys and certificates, monitor verification failures, manage clock skew, and keep proper audit logs; never log secrets, sensitive plaintext, or private keys.

Example envelope for application-encrypted data (format illustration only, not a protocol standard):

```json
{
  "version": 1,
  "algorithm": "AES-128-GCM",
  "keyId": "orders-data-v3",
  "nonce": "<base64-12-byte-nonce>",
  "aad": {
    "tenantId": "t-17",
    "messageType": "payment-request",
    "requestId": "r-204"
  },
  "ciphertextAndTag": "<base64-data>"
}
```

In a real design, specify **canonical serialization** of AAD (field order, UTF-8 encoding, length/delimiters, version), pin allowed algorithms in trusted config, determine tenant/request from authoritative server sources, reject invalid values, and govern `keyId`. Never trust `algorithm` or `keyId` merely because a client declared them in JSON. Including cleartext AAD in the envelope supports integrity checks, but does not make AAD confidential.

## 8. Java 17+: A Valid Signature Can Still Come From an Untrusted Key

This standalone example simulates two Ed25519 key pairs: one public key **pre-configured as trusted** by the receiver, and one key pair **self-generated by an untrusted sender**. The attacker signs the payload with their own key; the receiver must verify using the **expected identity's key**, not an arbitrary public key bundled with the request.

Save as `IdentityBindingDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;

public class IdentityBindingDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("Ed25519");
        KeyPair trusted = generator.generateKeyPair();
        KeyPair attacker = generator.generateKeyPair();
        byte[] request =
                "pay:100".getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(attacker.getPrivate());
        signer.update(request);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(attacker.getPublic());
        verifier.update(request);
        System.out.println("Untrusted key verifies own signature: "
                + verifier.verify(signature));

        verifier.initVerify(trusted.getPublic());
        verifier.update(request);
        System.out.println("Trusted key verifies attacker signature: "
                + verifier.verify(signature));
    }
}
```

Run with JDK 17+:

```bash
javac --release 17 IdentityBindingDemo.java
java IdentityBindingDemo
```

Output when run with a standard Ed25519 provider:

```text
Untrusted key verifies own signature: true
Trusted key verifies attacker signature: false
```

**Why do the two lines differ?** The signature math holds for the attacker's key, yet **that key does not belong to the identity the application intends to trust**. This is a key/identity confusion error (`key substitution`), not an Ed25519 mathematical flaw. In real production systems, the receiver fetches the public key from a trusted registry/certificate, bound to sender, tenant, purpose, and revocation status. It must also check that the signer is **authorized** to sign that command type and that the signed bytes include required context.

The simulation generates both keys in RAM, lacks certificates/PKI, and does not prove real-world identity. It **only proves** why `Signature.verify` alone is insufficient to authorize a transaction.

## 9. Adding Parameters and Protocol Rules to Bind Authority to Messages

For payment command `tenant=t-17, requestId=r-204, pay=100`, do not just sign `pay=100` and accept the entire operation. A message contract may require:

1. **Key and identity:** look up `keyId` in a trusted registry, verify the key belongs to `orders-service`, is active, and is authorized to sign commands for this tenant.
2. **Algorithms and parameters:** signing/verifying keys use an allowlisted algorithm and configuration; for AEAD-encrypted payloads, enforce matching key, unique nonce, tag, and version/tenant/requestId AAD.
3. **Protocol:** specify exact signed bytes, canonical encoding, message type, expiration, `requestId`, and anti-replay checks.
4. **Execution:** run business logic only after verification and authorization succeed; use an idempotency key so retries do not credit funds twice.

Separate **operation verification** (`verify == true`, valid tag) from **context evaluation** (right key, right principal, right tenant, right time, and right permission). That is the core contribution of the key–algorithm–parameter–protocol–identity relationship.

## 10. Common Design Flaws Viewed Through the Five Components

| Symptom | Missing or Misbound Component | Consequence and Remediation |
| --- | --- | --- |
| Using AES-ECB because "AES is strong" | Algorithm/mode | Leaks data patterns, lacks authentication; use AEAD per security needs |
| Reusing GCM nonce with the same key | Parameters + key management | Can severely break security; ensure unique nonces, bound key usage |
| Using plain SHA-256 to "sign" data | Algorithm | Adversaries modify both data and hash; use MAC/signature per trust model |
| Verifying signature with a request-supplied public key | Identity + trust | Verifies attacker's signature; look up keys from trusted sources and check permissions |
| Disabling hostname verification / trusting all TrustManager certs | Identity + protocol | TLS encrypts to the wrong peer; enable chain and endpoint identity checks |
| Checking only AEAD tag without checking `messageId` | Protocol/state | Valid replays succeed; add freshness, sequence, and idempotency |
| Blindly trusting client-provided `keyId` or `alg` | Protocol + configuration | Wrong key/algorithm selection or algorithm confusion; enforce allowlists and binding |
| Sharing one key across multiple purposes without isolation | Key + KDF | Expands blast radius and context confusion; isolate keys/contexts, enforce usage |
| User authenticates yet resource permissions go unchecked | Identity + authorization | Cross-tenant access/IDOR; check authorization per request |
| Accepting plaintext despite verification failure | Protocol + error handling | Feeds untrusted data into business logic; fail closed before processing |
| Signing JSON while each side serializes differently | Protocol + encoding | Verification fails or creates ambiguity; canonicalize byte representation, version |

These flaws explain why **simply upgrading AES-128 to AES-256** cannot fix a design with missing authentication, nonce reuse, or broken identity binding.

## 11. Design and Self-Review Process

When reading or building a security feature, answer in sequence:

1. **Goals:** to what degree are confidentiality, integrity, peer authentication, freshness, authorization, and auditing required? Can adversaries read/intercept/modify/replay messages or control clients?
2. **Identity:** who are the allowed sender/receiver? Is expected identity taken from trusted config or self-declared client input? What is the trust anchor/key registry?
3. **Keys:** where are keys generated/exchanged/derived, who can use them, under what scope, and how are they stored and rotated/revoked? Are keys isolated by purpose and session?
4. **Algorithms and parameters:** pick primitives for the exact goal; how are mode, hash, nonce, tag, salt, curve, KDF context, and sizes bound/checked?
5. **Protocol:** define version, roles, canonical encoding, handshake/message sequence, AAD, signature scope, timeouts, failure handling, downgrade protection, and anti-replay.
6. **Authorization:** after proving identity, are tenant/resource/operation permissions checked at the right moment?
7. **Operations:** are verification failures, key lifecycles, nonce counts, identity revocation, version compatibility, and migrations monitored without weakening security checks?
8. **Testing:** test wrong key, wrong nonce, wrong tag, wrong AAD, wrong public key, wrong hostname/CA certificate, tampered messages, replays, downgrades, cross-tenant calls, and unauthorized users. All must be rejected per policy.

### Quick-Check Questions

**Q1.** Alice and Bob share an AES-GCM key. Bob decrypts successfully and validates the tag. Does Bob have cryptographic proof that *specifically Alice*, and nobody else holding the key, sent it?

**Answer:** No. The tag shows the message matches the symmetric key and checked parameters. When multiple parties hold the key, it cannot uniquely distinguish who created the message; additional identification and binding mechanisms are needed.

**Q2.** Is an Ed25519 signature returning `verify=true` with a request-supplied public key enough to confirm "an administrator's request"?

**Answer:** No. You must know which trusted source bound that public key to the administrator and whether it remains valid and authorized to sign; otherwise, an adversary can generate their own key and signature.

**Q3.** Both nonce and AAD can be sent publicly. Why are they needed?

**Answer:** The nonce ensures distinct encryptions and, in GCM, must never repeat a key–nonce pair; AAD binds contextual data to the tag check without encrypting it. Both are security parameters, not secrets.

**Q4.** TLS already protects the request channel; are authorization and idempotency still needed?

**Answer:** Yes. TLS protects the channel and authenticates endpoints per TLS policy; order permissions and duplicate request handling belong to the application protocol/business logic.

**Q5.** When rotating a TLS certificate, must AES keys encrypting historical data also be rotated?

**Answer:** Not necessarily. TLS authentication keys, traffic keys, and data-at-rest keys have distinct purposes and lifecycles. Rotation is decided by policy, incident scope, and each key's usage boundaries.

## 12. Relationship Summary

**Algorithms** define cryptographic operations; **keys** grant cryptographic capability to holders; **parameters** specify how an operation applies to each message; **protocols** define steps to construct, negotiate, verify, and process outputs; **identities** bind keys and sessions to trusted entities, while **authorization** decides what those entities may do.

A cryptographic result holds security meaning only within a **verified context**. The most important question is not "which algorithm are we using?" but rather: **"Whose exact key, with which parameters, inside which protocol, proving what to the right peer and for the right action?"**

### Official References

- RFC 8446 — TLS 1.3: https://www.rfc-editor.org/rfc/rfc8446
- RFC 5869 — HKDF: https://www.rfc-editor.org/rfc/rfc5869
- NIST SP 800-38D — GCM/GMAC and IV requirements: https://csrc.nist.gov/pubs/sp/800/38/d/final
- Java Cryptography Architecture (JCA), Java SE 17: https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html
