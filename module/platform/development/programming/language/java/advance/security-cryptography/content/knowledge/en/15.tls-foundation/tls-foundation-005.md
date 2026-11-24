# 15.5 Ephemeral Keys, Forward Secrecy, and Their Relationship with Long-Term Certificate Keys

## Learning objectives

After this lesson, you can:

1. Distinguish the **long-term identity key bound to an X.509 certificate**, **ephemeral private key** used in key agreement, **shared secret**, **traffic keys**, and **session resumption PSK**.
2. Explain what **forward secrecy (FS)** protects, under which threat model and conditions; avoid confusing it with absolute security or identity authentication.
3. Compare **TLS 1.2 RSA key transport** with **TLS 1.2 (EC)DHE**, and understand why **TLS 1.3 uses ephemeral key exchange for certificate authentication**, while **PSK-only** and **0-RTT** are separate cases to examine.
4. Understand how TLS binds ephemeral key exchange to **Certificate**, **CertificateVerify**, **Finished**, and trust/hostname verification; explain why **a server with an RSA certificate can still have forward secrecy**.
5. Practice in Java 17+ using **X25519 KeyAgreement** and **Ed25519 Signature** to demonstrate ephemeral shared secrets and identity-key signatures, while recognizing the boundary: this is **not a hand-rolled TLS protocol**.
6. Inspect TLS in Java/JSSE systems, avoid obsolete choices, manage key lifecycles, and design tests for post-session identity key compromise.

**Core point:** **Certificates** let a client verify **which peer** is participating (via private-key possession and trust policy). **Ephemeral keys** create secrets used for **this session/connection** without deriving them from the certificate's long-term private key. In a secure (EC)DHE session whose session keys were properly derived and ephemeral secrets properly discarded, **an attacker who later steals the identity private key cannot use that key alone to decrypt past session recordings**.

Conversely, if a system uses a key exchange lacking forward secrecy, a compromised long-term key can expose many previously captured network recordings. **Digital signatures and key agreement serve two distinct functions; neither replaces the other.**

## 1. Threat model: "harvest today, steal the key tomorrow"

Suppose Alice accesses Bob's server over HTTPS.

- At time **T1**, Eve records a full copy of the TLS packets on the network without having access to the server yet.
- At time **T2** (after the old TLS session has ended), Eve steals Bob's **long-term private key**, e.g., a PKCS12 file, key backup, or signing access to an identity key.
- Eve attempts to decrypt the packets recorded at T1.

Forward secrecy asks:

> Once Eve obtains the **long-term secret at T2**, can she decrypt the **traffic of the earlier session at T1** using only the network capture and the stolen key?

In an FS design built on **fresh (EC)DHE** and erasing no-longer-needed keying material, the expected answer is **no** with respect to the compromise of the **long-term identity private key** alone. Traffic keys of the old session were derived from a shared secret that Eve cannot compute solely from the observed public shares and the later-stolen identity private key.

Timeline diagram:

~~~text
T1: Handshake using fresh ephemeral (EC)DHE
    Alice <---------------------------------> Bob
      |                                         |
   Ephemeral private a                     Ephemeral private b
      |                                         |
   Shared secret Z ---------------------- Shared secret Z
      |                                         |
   Derive traffic keys -> transmit encrypted data
      |
    Eve records ClientHello, ServerHello, certificate,
    key shares, handshake, and application ciphertext.

T1 ends:
    a, b, and unneeded secrets are erased/freed
    per implementation capability and policy.

T2: Eve obtains Bob's long-term identity private key.
    With only this key and the T1 capture:
       cannot derive Z or T1 traffic keys
       under a secure (EC)DHE model.
~~~

**FS does not mean data stays safe if Bob was compromised at T1.** If Eve compromised the server while the session was active—capturing session secrets, RAM plaintext, key logs, or controlling the application—she can read data even if the handshake used (EC)DHE.

### 1.1 What is protected and what is not

| Question | How does an FS (EC)DHE session answer? |
| --- | --- |
| After the session, the server's identity private key is stolen. Can past traffic recordings be decrypted with that key? | **Not from the identity key alone**, provided key exchange/algorithms are secure and ephemeral/session secrets are no longer exposed |
| The client did not verify the certificate—does (EC)DHE stop MITM on its own? | **No**; unauthenticated DH can suffer intermediate key insertion |
| Attacker captures traffic keys or plaintext while the session is live? | **FS cannot rescue data exposed during that live window** |
| Attacker obtains the identity private key before a new handshake? | **Can impersonate the server going forward**, unless trust/revocation/new keys and other controls block it |
| Server reuses ephemeral keys for a long time or logs keying material? | FS guarantees can be degraded or lost |
| Ciphertext from past TLS is stored at a proxy/DB as plaintext? | Network-layer FS does not protect those plaintext copies |
| Connection uses PSK-only or TLS 1.3 0-RTT data? | **Does not inherently share full (EC)DHE FS guarantees**; examine PSK lifecycle and specific mode |
| Future computing breakthroughs break today's (EC)DH? | Classical FS **does not protect** against solving the DH problem from public shares with new capabilities |

### 1.2 Do forward secrecy and "Perfect Forward Secrecy" differ?

In older documents and system configs, the term **Perfect Forward Secrecy (PFS)** was often used for this guarantee. Newer standards commonly say **forward secrecy**. The word "perfect" should not be read as "without exception". Cryptographic guarantees always depend on assumptions about algorithms, secret generation/deletion, handshake modes, and the threat model.

**Practical definition:** compromising certain long-term keys in the future **does not reveal previously completed sessions** under the defined security model.

## 2. Classifying keys in TLS — do not call all of them "the SSL key"

| Component | Lifecycle | Who holds it? | Main job |
| --- | --- | --- | --- |
| **Long-term identity private key** (RSA/ECDSA/EdDSA per TLS/provider) | Many sessions, tied to certificate/identity and rotation | Server or HSM; also client in mTLS | Proves possession of identity key, signs protocol handshake data |
| **Public key in X.509 certificate** | Public, with validity and certification chain | Readable by peer | Helps verify signatures and bind identity after PKI checks |
| **(EC)DHE ephemeral private key** | Generated for one handshake or bounded time per protocol/policy | Held separately by each peer | Combined with peer's public share to compute **shared secret** |
| **Ephemeral public share** | Sent in handshake; not secret | Visible to both peers and eavesdroppers | Public input to compute shared secret with private share |
| **(EC)DHE shared secret** | Intermediate, short-lived | Both peers after agreement | Input to key schedule/KDF; not a raw traffic key to use directly |
| **Handshake traffic secrets/keys** | While completing handshake | Both peers per send/receive direction | Protects encrypted handshake records |
| **Application traffic secrets/keys** | During connection, updatable | Both peers per send/receive direction | Encrypts and authenticates application records |
| **PSK/resumption secret/session ticket keys** | May persist across multiple connections | Client/server/ticket infrastructure | Authenticates or resumes sessions; FS risk depends on usage/storage/deletion |
| **CA signing private key** | Long-term at CA, absent from TLS handshake | CA/KMS/HSM | Signs certificates; **not** a key creating session traffic |

**The certificate's key pair** and **the ephemeral key pair** are **two functionally distinct pairs**. Both are called "public/private keys", yet their lifecycles and purposes differ sharply.

### 2.1 Certificates do not contain private keys

An X.509 certificate contains a public key along with subject, issuer, validity, SAN, KU/EKU, signature, and extensions. **Private keys do not reside inside the certificate**. Private keys may be stored in PKCS12, an HSM, an OS keystore, or a KMS. Referring to "the certificate's private key" means the private key **matching the public key bound by the certificate**, not a secret field inside the certificate.

### 2.2 A server certificate can be RSA while the handshake still uses ECDHE

This is often confused. In the TLS 1.2 cipher suite **TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256**:

- **ECDHE**: ephemeral key agreement method.
- **RSA**: authentication/signing method using the server's RSA identity key.
- **AES_128_GCM**: protection mechanism for application records.
- **SHA256**: PRF/hash component per the cipher suite specification.

The word **RSA in `ECDHE_RSA`** does not mean TLS encrypted the premaster secret with the certificate's RSA public key. RSA is used for the **authentication signature**, while the shared secret comes from **ECDHE**.

Similarly, **TLS_ECDHE_ECDSA_...** uses ECDHE for key exchange and ECDSA for authentication. A certificate's key type (RSA or ECDSA) does not by itself decide FS; inspect the **actually negotiated handshake/key exchange**.

## 3. How does ephemeral (EC)DHE create a shared secret?

**Diffie-Hellman (DH)** lets two parties compute the same shared secret using their own private value and the peer's public value, without sending the shared secret over the network. The "E" in DHE/ECDHE stands for **ephemeral**, meaning key-exchange values are freshly generated and short-lived.

Conceptual diagram:

~~~text
Client Alice                                     Server Bob

Generate ephemeral private a                    Generate ephemeral private b
Generate public share A                         Generate public share B
       |                                               |
       +---------------- A -------------------------->+
       +<--------------- B ---------------------------+
       |                                               |
Z = DH(a, B)                                     Z = DH(b, A)
       |                                               |
       +--------------- same Z ------------------------+
                             |
                 KDF/HKDF + handshake context
                             |
                 Traffic secrets, keys, IVs
                             |
             Protect data via AEAD record layer
~~~

**Neither a, b, nor Z is transmitted** in the handshake. Public shares A and B can be recorded, yet are insufficient to compute Z under classical (EC)DH hardness assumptions.

With **ECDHE**, arithmetic takes place over an elliptic curve. Modern groups can include **X25519** or **secp256r1** when supported by both sides and the provider. For finite-field DHE, use standardized, sufficiently strong DH groups; **never generate weak DH parameters yourself or pick untrusted groups**.

### 3.1 Why must it be "ephemeral"?

If a fixed DH private value were reused across many sessions, leaking that value could affect multiple sessions and amplify compromise impact. With fresh ephemeral key pairs per handshake and timely deletion, finished private shares are no longer available for an attacker to harvest at T2.

**"Ephemeral" does not mean merely naming a variable `tempKey`**: you must genuinely use securely generated key material per policy, avoid unnecessary reuse, avoid writing it to logs/key dumps, avoid unintended persistence, and release it once done.

Exact details such as pre-generating key shares, implementation pooling, session resumption, KDFs, and erasure timing depend on the protocol and runtime. Never write a custom key agreement over sockets and call it TLS merely because it uses DH.

### 3.2 A shared secret is not a direct traffic key

A **`KeyAgreement.generateSecret()`** call may return a byte array shared secret. In TLS 1.3, this secret feeds into the **HKDF-based key schedule** along with the handshake transcript to derive multiple context-bound secrets and keys:

~~~text
(EC)DHE shared secret (+ PSK if handshake uses PSK)
                         |
                   TLS 1.3 key schedule
              HKDF-Extract / HKDF-Expand-Label
                         |
      +------------------+------------------+
      |                                     |
Handshake traffic secrets           Application traffic secrets
      |                                     |
  handshake keys                      traffic keys + IVs
                                      per send/receive direction
~~~

**Never use a raw DH shared secret straight as an AES key** or build keys/IVs by slicing bytes arbitrarily. The key schedule handles domain separation, handshake context, send/receive direction, updates, and other guarantees; the TLS implementation must handle this per standard.

### 3.3 Unauthenticated Diffie-Hellman is vulnerable to MITM

If Alice blindly accepts any public share B arriving from the network, Eve can substitute Eve's public share, running one key exchange with Alice and another with Bob. Both sides obtain keys, yet **each side actually exchanged keys with Eve**.

~~~text
Alice                 Eve (MITM)                 Bob
  |  public share A       |                       |
  +---------------------> |                       |
  |<------ public share E1|                       |
  |                       | --- public share E2 ->|
  |                       |<--- public share B ---|
  |                       |                       |
Shared secret Alice-Eve        Shared secret Eve-Bob
~~~

**Certificate + handshake authentication** defeats this attack: the client must validate the chain/trust, hostname, and proof that the server holds the identity private key; the authentication signature must bind to the **handshake transcript including the key exchange**, not just an isolated public share.

## 4. TLS 1.2: how does RSA key transport differ from ECDHE_RSA?

### 4.1 TLS 1.2 with static RSA key exchange — no FS

In the legacy **`TLS_RSA_WITH_AES_...`** style, the client generates a **premaster secret**, encrypts it using the **long-term RSA public key in the server certificate**, and sends it to the server. The server uses its long-term RSA private key to decrypt the premaster secret and derive session keys alongside the client.

~~~text
TLS 1.2 static RSA key transport:

Client:
   Generate premaster_secret
   RSA_encrypt(server_certificate_public_key, premaster_secret)
                      |
                 network packet
                      |
Server:
   RSA_decrypt(long_term_server_private_key, encrypted_premaster)
   -> premaster_secret -> traffic keys
~~~

If Eve records the encrypted premaster secret and application traffic records at T1, then steals the long-term RSA private key at T2, Eve **can decrypt the recorded premaster secret and recompute the past session's keying material** (given complete records and no other protection). Thus, this mechanism **has no forward secrecy**.

That is a structural issue, not because RSA is "always insecure". RSA can still serve as an **identity signature** in an FS-capable `ECDHE_RSA` handshake.

**Standards status note:** RFC 10015 (2026) **deprecated** RSA key exchange and several obsolete mechanisms in (D)TLS 1.2. TLS 1.3 has no static RSA key transport. Legacy Java documentation may still list old cipher suites for compatibility reasons, yet recognizing an old suite name does not mean enabling it in modern configurations.

### 4.2 TLS 1.2 with ECDHE_RSA — can provide FS

In **`TLS_ECDHE_RSA_...`**:

1. Client and server exchange ephemeral ECDHE shares.
2. The server proves possession of its RSA identity private key by signing handshake parameters per TLS 1.2 (typically **`ServerKeyExchange`**).
3. The client verifies the certificate chain/hostname and signature.
4. Both derive the premaster/shared secret via ECDHE, without decrypting a premaster ciphertext with the long-term RSA key.
5. Once ephemeral secrets vanish and security assumptions hold, stealing the RSA identity private key **after the session** is insufficient to decrypt past traffic.

~~~text
TLS 1.2 ECDHE_RSA:

Long-term RSA certificate/private key:
    authenticates/signs ECDHE parameters in handshake

Client ephemeral a, server ephemeral b:
    ECDHE(a, B) == ECDHE(b, A) -> premaster/master/traffic keys

Post-session compromise of RSA private key:
    can impersonate identity going forward,
    but does not yield the ephemeral shared secret already used.
~~~

### 4.3 TLS 1.2 distinction table

| Cipher suite / mechanism | Key exchange | Role of long-term certificate/key | FS against post-session certificate private key compromise? |
| --- | --- | --- | --- |
| **TLS_RSA_WITH_AES_128_GCM_SHA256** | RSA key transport | RSA private key decrypts premaster secret | **No** |
| **TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256** | Ephemeral ECDHE | RSA signs/authenticates handshake | **Yes, under ECDHE conditions and proper operations** |
| **TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256** | Ephemeral ECDHE | ECDSA signs/authenticates handshake | **Yes, under corresponding conditions** |
| **DHE_RSA** (eligible variants) | Ephemeral finite-field DHE | RSA authenticates | **Yes**, if strong groups and proper ephemeral handling are used |
| **Static DH/ECDH** | Long-term/static DH keys | May tie into identity/certificate | Does not provide FS like ephemeral exchange |

Suite names matter in **TLS 1.2** because they encode key exchange/auth mechanisms. Never apply the same suite-name reading rule to TLS 1.3.

## 5. TLS 1.3: ephemeral key exchange and certificate authentication

In a **certificate-based TLS 1.3 full handshake**, key exchange and identity authentication are designed with **clear functional separation**:

- **ClientHello / ServerHello, key_share:** exchanges public (EC)DHE values.
- **Certificate:** server presents the certificate chain authenticating identity.
- **CertificateVerify:** server proves possession of the identity private key via a **digital signature bound to the handshake transcript and TLS context**.
- **Finished:** MAC confirming the handshake transcript and possession of the right handshake secret; detects handshake tampering by design.
- **HKDF key schedule:** derives secrets/traffic keys from the (EC)DHE secret and handshake context, separated by phase and direction.

Simplified diagram:

~~~text
Client                                             Server
  |                                                  |
  | ClientHello + supported_groups + key_share A    |
  +------------------------------------------------->|
  |                                                  |
  |       ServerHello + selected key_share B         |
  |<-------------------------------------------------+
  |                                                  |
  |     [Both sides now hold Z = (EC)DHE(a,B)/(b,A)] |
  |                                                  |
  |            EncryptedExtensions                   |
  |            Certificate (server identity)         |
  |            CertificateVerify (signature)        |
  |            Finished (handshake MAC)              |
  |<-------------------------------------------------+
  |                                                  |
  |     Validate certificate chain + hostname       |
  |     Verify CertificateVerify + Finished          |
  |                                                  |
  | Finished                                        |
  +------------------------------------------------->|
  |                                                  |
  |<======== encrypted application data ============>|
~~~

This is an **illustrative diagram**, not a complete message-level replica of TLS 1.3. Depending on the handshake, `CertificateRequest`, client `Certificate`/`CertificateVerify` in mTLS, `HelloRetryRequest`, resumption/PSK, and other extensions may appear.

**Crucial point:** In a full certificate handshake, **the certificate's private key is used for authentication**, not as a static secret to decrypt an (EC)DHE shared secret. The certificate neither "contains the session key" nor "carries an encrypted session key" as in TLS 1.2 RSA key transport.

### 5.1 What does `CertificateVerify` bind?

In TLS 1.3, the `CertificateVerify` signature is computed over a standardized format containing a **context string** and the **handshake transcript hash**, using the negotiated signature algorithm. It **is not merely signing the string `"hello"`** or signing an isolated key share.

Binding the transcript enables the client to detect a MITM swapping handshake components, provided signature and PKI validation are performed properly. The signature proves the peer holds the identity private key matching the accepted certificate, while (EC)DHE produces the ephemeral secret.

**The signature alone does not verify SAN/hostname, trust chain, validity dates, EKU, and policy.** Those checks remain the responsibility of certificate/path/endpoint identity validation in the TLS stack.

### 5.2 What step is `Finished`?

**Finished** confirms both sides arrived at matching keying material and binds the **handshake contents** with a keyed MAC. If the handshake was modified without the proper secret, `Finished` verification fails.

Do not reduce this to "TLS is secure because it has `CertificateVerify`". Handshake security arises from **multiple interlocking checks**: version/cipher suite selection, key shares, transcript signatures, `Finished`, certificate validation, and record-layer integrity.

### 5.3 An RSA certificate does not mean RSA key transport

In TLS 1.3, a server can use an RSA certificate to **sign the handshake** with an appropriate signature algorithm; that **does not reintroduce static RSA key transport**. A TLS 1.3 cipher suite like:

~~~text
TLS_AES_128_GCM_SHA256
~~~

names the **AEAD cipher and hash** of the suite, **without encoding the key exchange or signature scheme** in the suite name itself. Seeing `SSLSession.getCipherSuite()` return that string does not tell you whether the peer used X25519/secp256r1 or an RSA/ECDSA certificate.

With TLS 1.3, inspect the **protocol version, handshake type (full/PSK), `key_share`/PSK mode, certificate/signature, and JSSE handshake diagnostics** to verify FS details.

### 5.4 Does TLS 1.3 always have forward secrecy?

You cannot answer with a blanket "always" while ignoring **PSK-only and 0-RTT**.

According to **RFC 9846 (July 2026)**, the current TLS 1.3 specification replacing RFC 8446, core principles remain:

- When a **public-key handshake uses fresh (EC)DHE**, the design provides FS under the cryptographic model, provided ephemeral/traffic secrets are properly managed.
- TLS 1.3 supports **PSK-only (`psk_ke`)**; this mode **does not inherently provide FS against compromise of a retained PSK**, because no fresh DH share contributes to the shared secret.
- TLS 1.3 supports **PSK + (EC)DHE (`psk_dhe_ke`)**; fresh DH provides FS for 1-RTT traffic derived under this mode.
- **0-RTT early data** relies on PSK and **lacks full forward secrecy guarantees like 1-RTT DHE**; it also introduces **cross-connection replay issues**.
- Under single-use PSK/session ticket schemes that delete all copies immediately, compromise exposure may be narrower; that is an **operational property depending on PSK deletion timing**, not a promise that "PSK-only always equals DHE".

Updated reference: [RFC 9846 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc9846.html), especially §2.2–2.3 and Appendix F.

## 6. Resumption, PSK, 0-RTT, and easily missed exceptions

### 6.1 What is a PSK?

A **Pre-Shared Key (PSK)** is a secret shared by both sides prior to a handshake (provisioned externally or derived from an earlier connection). In TLS 1.3, session resumption can use a resumption PSK and ticket to establish a subsequent connection faster.

**A PSK is not an X.509 private key.** A server may present a certificate during the initial full handshake, yet a PSK-based resumption handshake might not resend that certificate. You must understand TLS state/sessions and your application's trust policy.

### 6.2 Comparing `psk_ke` and `psk_dhe_ke`

~~~text
TLS 1.3 psk_ke:
    PSK ----------------> key schedule -> traffic keys
    (No fresh key_share contributes)
    => If PSK is retained and later compromised, lacks FS guarantees
       comparable to fresh (EC)DHE exchange.

TLS 1.3 psk_dhe_ke:
    PSK ------------------+
                          +--> key schedule -> traffic keys
    Fresh (EC)DHE Z ------+
    => FS for 1-RTT traffic when ephemerals are properly protected/erased,
       under protocol assumptions.
~~~

**Do not assume all HTTPS sessions using PSK lose FS**: examine the mode, when the PSK could be exposed, and its lifecycle. Conversely, seeing "TLS 1.3" does not prove every handshake performed fresh DHE.

### 6.3 0-RTT early data

When a client holds a PSK from a prior connection, TLS 1.3 can allow sending some application data in the **first flight** of a new handshake. This cuts latency while trading off security properties:

- **No full FS guarantee for early data**; early-data keys are derived from the PSK before receiving a fresh `ServerHello` key share.
- **Replay risk** across multiple connections; an attacker can attempt to replay captured early data.
- Side-effecting operations such as **money transfers, purchases, order creation, or password changes** should not be allowed in 0-RTT by default; explicit application profiles and replay/idempotency protections are required.
- **1-RTT application data after the handshake** can receive different protection when using PSK+(EC)DHE; never lump all TLS 1.3 traffic under a single "forward secret" claim.

RFC 9846 requires applications not to enable 0-RTT unintentionally and not to send unsafe replayable early data. In Java/JSSE, actual 0-RTT support depends on the JDK version, provider, and API; never assume common Java 17 JSSE enables 0-RTT automatically.

### 6.4 Session ticket encryption keys and PSK lifecycle

A server may issue session tickets for resumption. If tickets are encrypted/authenticated by a long-lived **server ticket protection key**, or resumption PSKs stay in a cache/DB too long, compromising the ticket infrastructure can impact resumed connections.

Necessary controls:

- Appropriate lifetimes for session tickets and resumption PSKs.
- Rotation and strict access control for ticket keys.
- Deleting unneeded keys/PSKs; never logging session secrets.
- Single-use or anti-replay rules if the application allows early data.
- Distinguishing full handshake, `psk_ke` resumption, and `psk_dhe_ke` resumption.
- Never designing "forward secrecy" around only the certificate private key while forgetting where PSKs/session tickets are stored.

## 7. Attacks and limits: understanding FS promises accurately

### 7.1 Certificate private key compromised after past sessions ended

**What can happen:**

- TLS 1.2 RSA key transport: attacker can decrypt recorded premaster secrets from the handshake; risk of decrypting past traffic.
- TLS 1.2 ECDHE and TLS 1.3 full (EC)DHE handshake: the identity key alone is insufficient to compute past shared secrets; past traffic stays protected as long as ephemeral secrets were not exposed.
- In new handshakes, an attacker holding the identity private key **can impersonate the server**, because signature/authentication is compromised. FS **does not prevent** future impersonation.

**Actions when an identity private key is lost:** revoke/rotate certificates and keys, lock down access, investigate the incident, update trust/deployments, and assess scope. Past records having FS is never a reason to skip incident response.

### 7.2 Attacker holds traffic secrets or endpoint memory

FS **cannot** erase exposure of data already read by an attacker. If an attacker obtains:

- Plaintext at reverse proxies, application logs, traces, or heap dumps.
- Ephemeral private keys while a session is active.
- (EC)DHE shared secrets or handshake traffic secrets.
- Application traffic keys or exported key logs (e.g., key log files used for packet analysis).
- A session ticket/PSK still valid under an eligible resumption mode.

then affected sessions or data can be decrypted or forged. Endpoint hardening, memory-dump hygiene, debug settings, and secret storage remain vital **even when using TLS 1.3**.

### 7.3 `KeyUpdate` is not a new DH exchange

TLS 1.3 provides a **`KeyUpdate`** mechanism to derive a new generation of traffic keys from the existing secret. This helps enforce key-usage limits and protects earlier generations if old keys were erased.

However, **`KeyUpdate` does not re-run (EC)DHE**. If an attacker already holds the **current traffic secret**, merely deriving a new generation from that secret **does not provide post-compromise security going forward**. Never confuse pre-compromise FS with "self-healing" after an attacker steals a live session secret.

Per RFC 9846's security analysis, mitigating certain compromises for new connections requires a **fresh asymmetric key exchange**, not merely ratcheting the same secret.

### 7.4 Forward secrecy is not post-quantum security

An attacker can record public DH shares and ciphertext today. If future capabilities can solve today's DH/ECDH problem from public shares (such as sufficiently powerful quantum computers running Shor's algorithm), having deleted the identity private key **is no longer decisive**. Therefore, **classical FS** does not equal protection against "harvest now, decrypt later" in a quantum threat model.

Reducing future HNDL risk requires evaluating standardized post-quantum or hybrid key-establishment protocols and deploying them properly—not concatenating X25519 with an arbitrary algorithm in application code. **X25519 in this lesson's Java example is a classical model**, not a post-quantum guarantee.

### 7.5 Applications storing plaintext can still negate protection

A TLS terminator or reverse proxy can decrypt traffic, then forward plaintext to internal services or store it in logs/databases. FS applies only to **per-session encrypted TLS traffic**, and does not automatically protect plaintext copies existing outside that connection.

Trace the full data path: client → CDN/LB/proxy → app → DB/queue/logs, and every trust boundary. A system boasting "TLS with PFS" that writes access tokens or raw payloads into public logs still has a severe security flaw.

## 8. Java 17+: simulating the two roles without building custom TLS

Java's JCA/JCE exposes the underlying primitives for learning:

- **`KeyPairGenerator.getInstance("X25519")`** generates an ephemeral X25519 key pair.
- **`KeyAgreement.getInstance("X25519")`** lets two sides compute a matching shared secret.
- **`KeyPairGenerator.getInstance("Ed25519")`** generates a sample identity key pair.
- **`Signature.getInstance("Ed25519")`** signs/verifies an illustrative transcript.

In this example, the server holds a **long-term Ed25519 identity key**, and the client knows the **trusted identity public key** in advance. Both sides generate fresh X25519 pairs per handshake and compute their secret. The server signs a transcript containing **both ephemeral public shares**, and the client verifies the signature with the known identity public key.

**Critical boundary:** This is an **educational model**, **not a TLS 1.3 implementation**. Real TLS defines specific context strings and transcript formats for `CertificateVerify`; requires certificate/path/hostname validation, `Finished` MACs, HKDF key schedule, cipher suite negotiation, AEAD record framing, replay/downgrade protections, error handling, and many other controls. **Never send two public shares + a signature in this demo format over a production network.**

### 8.1 Complete Java 17+ program

Create **`EphemeralIdentityDemo.java`** (UTF-8):

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.Arrays;
import javax.crypto.KeyAgreement;

public class EphemeralIdentityDemo {
    // Simulated transcript with domain separation and per-field lengths.
    // Not the TLS 1.3 Transcript/CertificateVerify format.
    private static byte[] transcript(PublicKey client, PublicKey server) {
        byte[] ctx = "educational-ephemeral-v1"
                .getBytes(StandardCharsets.UTF_8);
        byte[] c = client.getEncoded();
        byte[] s = server.getEncoded();

        return ByteBuffer.allocate(12 + ctx.length + c.length + s.length)
                .putInt(ctx.length).put(ctx)
                .putInt(c.length).put(c)
                .putInt(s.length).put(s)
                .array();
    }

    private static byte[] agree(KeyPair own, PublicKey peer)
            throws GeneralSecurityException {
        KeyAgreement a = KeyAgreement.getInstance("X25519");
        a.init(own.getPrivate());
        a.doPhase(peer, true);
        return a.generateSecret();
    }

    private static byte[] sign(PrivateKey key, byte[] message)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance("Ed25519");
        s.initSign(key);
        s.update(message);
        return s.sign();
    }

    private static boolean verify(PublicKey key, byte[] message, byte[] tag)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance("Ed25519");
        s.initVerify(key);
        s.update(message);
        return s.verify(tag);
    }

    public static void main(String[] args) throws Exception {
        // Simulate the server's long-term identity, e.g., certificate key.
        KeyPairGenerator idGen = KeyPairGenerator.getInstance("Ed25519");
        KeyPair longTermServerIdentity = idGen.generateKeyPair();

        // Each handshake uses two separate ephemeral X25519 key pairs.
        KeyPairGenerator ephemeralGen =
                KeyPairGenerator.getInstance("X25519");
        KeyPair c = ephemeralGen.generateKeyPair();
        KeyPair s = ephemeralGen.generateKeyPair();

        byte[] secretC = agree(c, s.getPublic());
        byte[] secretS = agree(s, c.getPublic());

        // Server signs the transcript using its long-term identity key.
        byte[] handshake = transcript(c.getPublic(), s.getPublic());
        byte[] signed = sign(
                longTermServerIdentity.getPrivate(), handshake);

        System.out.println("X25519 secrets agree: "
                + MessageDigest.isEqual(secretC, secretS));
        System.out.println("Shared secret bytes: " + secretC.length);
        System.out.println("Identity signature valid: "
                + verify(longTermServerIdentity.getPublic(),
                         handshake, signed));

        // An attacker swaps the server's public share in the transcript.
        KeyPair fakeServerShare = ephemeralGen.generateKeyPair();
        byte[] tampered = transcript(
                c.getPublic(), fakeServerShare.getPublic());
        System.out.println("Modified share rejected: "
                + !verify(longTermServerIdentity.getPublic(),
                          tampered, signed));

        // Another independent handshake uses fresh ephemeral key pairs.
        KeyPair nextClient = ephemeralGen.generateKeyPair();
        KeyPair nextServer = ephemeralGen.generateKeyPair();
        byte[] nextSecret = agree(
                nextClient, nextServer.getPublic());
        System.out.println("Fresh exchange differs: "
                + !MessageDigest.isEqual(secretC, nextSecret));

        // Shorten the lifetime of secret byte[] arrays directly held by the program.
        Arrays.fill(secretC, (byte) 0);
        Arrays.fill(secretS, (byte) 0);
        Arrays.fill(nextSecret, (byte) 0);
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 EphemeralIdentityDemo.java
java EphemeralIdentityDemo
~~~

Expected stdout on a Java 17+ provider supporting **X25519** and **Ed25519**:

~~~text
X25519 secrets agree: true
Shared secret bytes: 32
Identity signature valid: true
Modified share rejected: true
Fresh exchange differs: true
~~~

**Line-by-line explanation:**

1. **`X25519 secrets agree: true`** — client and server compute the exact same secret from their matching ephemeral private/public key pairs.
2. **`Shared secret bytes: 32`** — X25519 outputs a 32-byte shared secret.
3. **`Identity signature valid: true`** — the original transcript was signed with the Ed25519 private key; the public key **assumed already trusted by the client** verifies the signature.
4. **`Modified share rejected: true`** — when the server's ephemeral share is swapped in the transcript while keeping the old signature, **signature** verification fails.
5. **`Fresh exchange differs: true`** — an independent X25519 exchange using fresh key pairs produces a different secret with overwhelming probability.

**Never print raw private keys or shared secrets** to stdout; those are sensitive cryptographic values. Raw public keys can be public, yet must never be mistaken for authenticated identities without verifying signatures and certificates.

**Limits of the Java demo:** There is no PKI, certificate chain, SAN/hostname, TLS HKDF, `Finished`, record layer, or networking. The client directly trusts `longTermServerIdentity.getPublic()` in the same process—which **only illustrates signatures when the public key is already trusted**. In real HTTPS, the public key arrives in a certificate that must pass truststore and hostname policies. Nor is this demo code a formal proof that a custom-built protocol provides complete FS or MITM resistance.

The arrays zeroed with `Arrays.fill()` are only buffers directly held by our code; **this does not guarantee every copy of secrets inside provider/JVM/native memory is erased**. The demo still creates `KeyPair` instances holding private key objects whose lifetime is managed by the Java runtime; never copy this clearing technique and claim absolute secret erasure.

### 8.2 What the demo proves and does not prove

| Observation | Valid conclusion |
| --- | --- |
| Two sides compute the same 32 bytes with X25519 | The `KeyAgreement` primitive works correctly in this test |
| Ed25519 verifies the transcript | Public shares can be bound to a trusted identity public key |
| Altering one public share invalidates the signature | Signature protects signed content from tampering without the private signing key |
| Fresh pair yields a new secret | Using new key pairs produces a fresh session secret with negligible collision probability |
| Recording transcript/public shares and later leaking signing key | No way to recompute the old X25519 secret **from the signing key alone** under X25519 assumptions, if ephemeral privates stayed secret |
| Demo runs without TLS | **Does not** create a production-grade authenticated or secure transport channel |

### 8.3 Why not use a digital signature instead of ephemeral keys?

An Ed25519 or RSA signature serves to **prove the signer holds the private signing key** matching a trusted public key. A signature does not directly establish a secret known only to client and server. Conversely, `KeyAgreement` establishes a shared secret but **does not authenticate server identity on its own**.

The two operations complement each other:

~~~text
Identity key signature:
   "This public share/handshake belongs to a session authenticated by the valid server"
   (provided PKI/public-key trust and protocol are sound)

Ephemeral KeyAgreement:
   "Both sides share a session-specific secret"
   (yet on its own cannot prevent MITM)

TLS handshake:
   combines authentication + authenticated key exchange +
   key schedule + Finished + AEAD traffic protection
~~~

Never replace `KeyAgreement` with RSA signing a random string, never send raw shared secrets over the wire, and never try to "improve" TLS by manually stitching primitives together.

## 9. Observing real TLS through Java JSSE

In Java 17 applications, **JSSE** and APIs like **`SSLSocket`, `SSLEngine`, `SSLContext`, `SSLParameters`, `SSLSession`, `HttpsURLConnection`/`HttpClient`** implement or use TLS through the configured provider.

**First thing to know:** many properties in the JVM reflect **supported capabilities** or **enabled capabilities**, not an actually negotiated handshake. For example, the supported suites list may include legacy TLS 1.2 names; that does not prove a server accepts them or that any connection used them.

### 9.1 Inspecting supported TLS protocols and suites

The following Java snippet is **standalone** and makes no network connections; it only lists **capabilities of the active JSSE provider**.

File **`JsseCapabilitiesDemo.java`**:

~~~java
import java.util.Arrays;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLParameters;

public class JsseCapabilitiesDemo {
    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, null, null);
        SSLEngine engine = context.createSSLEngine();

        System.out.println("TLSv1.3 supported: "
                + Arrays.asList(engine.getSupportedProtocols())
                        .contains("TLSv1.3"));
        System.out.println("TLSv1.3 enabled: "
                + Arrays.asList(engine.getEnabledProtocols())
                        .contains("TLSv1.3"));

        SSLParameters params = context.getSupportedSSLParameters();
        System.out.println("Supported suites count: "
                + params.getCipherSuites().length);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 JsseCapabilitiesDemo.java
java JsseCapabilitiesDemo
~~~

**Output depends on the actual JDK/provider/security properties**, so no single fixed number is given for `Supported suites count`. On a standard JDK 17 JSSE supporting TLS 1.3, the first two lines are normally `true`; locked-down administrative configs may differ. This program **performs no handshake**, so it does not prove runtime usage of ECDHE, PKIX, or forward secrecy.

### 9.2 What should you check on a real handshake?

When authorized to inspect an approved endpoint, record:

1. **Negotiated protocol version**, not merely supported protocols—for instance from **`SSLSession.getProtocol()`** after the handshake.
2. **Negotiated cipher suite**, e.g., from **`SSLSession.getCipherSuite()`**.
3. For **TLS 1.2**, key exchange is normally visible in the suite (`ECDHE_RSA`, `DHE_RSA`, or static RSA).
4. For **TLS 1.3**, the cipher suite **omits KEX/auth mode**; also inspect handshake **`key_share`**, chosen group, PSK mode, and full vs. resumption status.
5. Ensure **certificate chain/trust path, hostname, EKU/KU, validity times, and revocation policy** are enforced by the application.
6. Confirm whether **TLS 1.3 0-RTT** is enabled, and if so, what anti-replay and idempotency policies apply.
7. If clients use mTLS, inspect client certificate/auth separately rather than conflating it with server authentication.
8. Check the **termination point**: does TLS end at a reverse proxy or directly at the app, and is mTLS/TLS used on the next internal hop?

**Never infer forward secrecy solely because a certificate is ECDSA or RSA**, nor merely because `SSLSession` returns `TLS_AES_128_GCM_SHA256`.

### 9.3 JSSE handshake debugging in the lab

In authorized environments, Java supports diagnostic JSSE logging, e.g., via system property:

~~~text
javax.net.debug=ssl,handshake
~~~

This reveals negotiated versions, cipher suites, `key_share`, handshake messages, and certificate validation depending on the JDK. It **is not an automated security sign-off**: inspect actual configs and outputs; debug logs can leak sensitive metadata and bloat log volume. Never leave it enabled long-term in production.

If packet capture is necessary, use authorized tools/sniffers within approved test scope. **Never enable TLS session key logging** to files and forget to delete them: key logs can decrypt traffic that FS would otherwise protect against identity-key compromise.

### 9.4 How should TLS be configured in Java 17 applications?

In principle:

- **Prefer TLS 1.3** wherever peers and providers support it; when TLS 1.2 is needed for compatibility, allow only **cipher suites with (EC)DHE and AEAD** per current policy.
- Never enable **static RSA key transport** for legacy compatibility without risk review; RFC 10015 deprecated it.
- Never enable SSLv3/TLS 1.0/1.1 or weak ciphers just to "get it working".
- Ensure `TrustManager`/`KeyManager` and identity certificates have proper permissions, chains, and hostnames.
- Never use a **trust-all `X509TrustManager`** or an **always-true `HostnameVerifier`**.
- Keep providers/JDK security-patched; never build TLS 1.3 out of the exercise's `KeyAgreement` + `Signature`.
- Never hardcode a single list of named groups or signature algorithms across all hosts without assessing compatibility and policy. Align with authoritative provider and crypto policies.
- Test **1-RTT full handshakes, resumption, and mTLS (if used)**, rather than checking only one successful HTTPS call.

**Note on cipher suite naming:** TLS 1.3 names such as `TLS_AES_256_GCM_SHA384` only express AEAD/hash; **X25519, secp256r1, RSA-PSS, or ECDSA do not appear in the name**. Those are separate handshake selections from TLS 1.2.

## 10. Operating to ensure FS has practical meaning

### 10.1 Protect long-term certificate private keys

FS limits **retroactive decryption** after an identity private key leaks, yet does not make that key unimportant. An attacker with a certificate's private key and network position can **impersonate the peer in future handshakes** until trust, revocation, or key rotation stops them.

Therefore:

- Protect keys with HSMs, keystores, or secret managers as required.
- Restrict signing privileges, key export, usage scope, and audit access.
- Reissue certificates/keys on schedule and during incidents.
- Enforce accurate certificate revocation/truststore and hostname verification.
- Avoid sharing one signing key across too many endpoints/tenants without explicit policy.
- Never send private keys through tickets, chat, logs, or source repositories.

### 10.2 Never retain ephemeral secrets "for debugging convenience"

Ephemeral keys, shared secrets, and session keys require the shortest possible lifetimes per implementation and protocol. If an organization logs raw session secrets, keeps broad memory dumps, enables TLS key logging, or retains session state in backups too long, **FS guarantees against identity-key loss alone no longer reflect real exposure**.

Java apps should never extract shared secrets to log "for comparison" or keep ephemeral private keys in global caches. Rely on standard JSSE implementations instead of managing raw ephemeral keys in application code.

### 10.3 Session resumption and PSK need dedicated policies

Clarify:

- Full handshake mode vs. PSK resumption?
- PSK-only vs. PSK+(EC)DHE?
- Is 0-RTT enabled?
- Where are ticket keys stored, who has access, and what is their lifetime/rotation?
- How are old tickets/PSKs purged and handled across multi-instance failover?
- How are 0-RTT anti-replay and idempotency enforced at the application layer?

Enabling TLS 1.3 while mismanaging session resumption can introduce attack paths outside the guarantees of a fresh (EC)DHE full handshake.

### 10.4 Do not replace security at other layers

FS does not fix:

- SQL injection, XSS, or command injection in the application.
- Leaking JWTs/API keys through logs or browser storage.
- Data-at-rest encryption lacking key/rotation policy.
- Broken cross-tenant authorization.
- An endpoint willingly returning plaintext to a wrongly authorized attacker.
- A CA or truststore poisoned with a rogue root causing false authentication.
- Backups/monitoring containing session secrets or raw sensitive data.

Treat TLS as **one** layer of a secure system, not "turn on PFS and we're done".

## 11. Common misconceptions

1. **"The server certificate is RSA, so there is definitely no FS."** False: RSA may be used only for authentication in `ECDHE_RSA`/TLS 1.3, while traffic keys come from DHE.
2. **"Since we have ECDHE, we don't need certificates."** False: unauthenticated DH falls to MITM; certificate/PSK trust and handshake authentication are required.
3. **"The certificate holds the ephemeral session key."** False: the cert holds the identity public key; ephemeral keys are created during the handshake.
4. **"The identity private key decrypts every TLS session."** False for ECDHE and TLS 1.3 full certificate handshakes; true only for legacy TLS 1.2 static RSA key transport.
5. **"The TLS 1.3 cipher suite name shows whether the server uses RSA or ECDSA and X25519."** False: TLS 1.3 suites omit KEX/auth from their names.
6. **"TLS 1.3 has absolute FS on every connection, including 0-RTT."** False: distinguish full (EC)DHE, PSK-only, and early data.
7. **"0-RTT is as safe as ordinary requests."** False: it carries replay risk and lacks full FS; restrict to replay-safe operations.
8. **"Ephemeral keys must be sent to the peer so both compute the secret."** False: only the **public share** is sent; the private share stays secret.
9. **"The DH shared secret is used straight as the AES key."** False: the TLS key schedule derives separate keys, IVs, and contexts.
10. **"Seeing the same shared secret on both sides means you have a secure TLS channel."** False: a demo lacks PKI, `Finished`, AEAD, replay, and downgrade protections.
11. **"If the identity key leaks after an old session, FS still protects all future sessions."** False: an attacker can impersonate the server in new handshakes.
12. **"Leaking a session traffic key doesn't matter because of FS."** False: leaked traffic/session keys unlock the data they protect.
13. **"Calling `KeyUpdate` definitely recovers if the current key was stolen."** False: `KeyUpdate` does not rerun ECDHE; impact depends on which key leaked.
14. **"Each connection having a different secret guarantees FS."** Not enough: if secrets derive from a long-term secret that later leaks, past sessions can be reconstructed.
15. **"Forward secrecy equals protection against future quantum computers."** No: classical ECDH can be broken once its hardness assumption fails.
16. **"Checking `TLSv1.3` in supported proves endpoints use TLS 1.3."** False: inspect the **negotiated protocol** on a real session.
17. **"TLS cipher suite `ECDHE_RSA` means RSA encrypts the premaster secret."** False: RSA authenticates signatures, ECDHE establishes the secret.
18. **"Short certificate lifetimes automatically create forward secrecy."** No: frequent certificate rotation limits compromise windows, yet does not replace ephemeral key exchange.
19. **"If the client skips hostname verification, ECDHE still blocks MITM."** False: an on-path attacker can run separate key exchanges with each side.
20. **"Once you have FS, you can freely store TLS session secrets or heap dumps."** False: direct secret leakage breaks confidentiality of recorded sessions.

## 12. Analysis scenarios

### Scenario A — Server uses an RSA certificate; need to verify whether FS holds

The ops team sees certificate type RSA and concludes there is no FS. Proper assessment:

- Inspect the **actual session protocol**.
- If TLS 1.2, check whether the suite is **`ECDHE_RSA`** or **`TLS_RSA_...`**; their properties differ sharply.
- If TLS 1.3, inspect full handshake/`key_share` or PSK mode; do not infer from certificate type or `TLS_AES_...` suite name.
- Check JDK/provider, security properties, and actually enabled cipher suites.

**Conclusion:** Certificate key type speaks to **authentication**, and does not by itself decide key establishment or forward secrecy.

### Scenario B — Server private key stolen after six months

An attacker recorded TLS packets six months ago and now steals the server's RSA identity key.

- Static RSA TLS 1.2 sessions: can be decrypted retroactively.
- TLS 1.2 ECDHE / TLS 1.3 full DHE sessions: cannot be decrypted from the RSA identity key alone, provided old ephemeral/session secrets were not leaked.
- New handshakes: attacker can impersonate the server unless revoked/blocked.

**Action:** assess exposure by protocol/suite/mode and compromise window; rotate keys/certificates and run incident response—never claim "TLS makes it harmless".

### Scenario C — Service enables resumption and 0-RTT

To cut latency, a team accepts 0-RTT requests calling a transaction-creation API. An attacker replays a captured early-data request.

**Problem:** 0-RTT carries replay risk; early-data FS is not equivalent to 1-RTT fresh DHE. Duplicate operations may result.

**Fix:** disallow side-effecting operations in 0-RTT without proper replay protection and idempotency profiles; restrict early data, monitor session tickets, and enforce anti-replay at infrastructure/business layers.

### Scenario D — Session key log leaked during debugging

A developer enables key logging for Wireshark to decrypt lab HTTPS and accidentally uploads the key log to a shared artifact store. An attacker obtains both the log file and packet capture.

**Problem:** FS against **long-term identity key** compromise does not protect when **session traffic secrets were exported directly**. Treat key log files as secrets, restrict access, revoke/investigate, and keep them out of production pipelines.

### Scenario E — Endpoint compromised while a session is live

An attacker reads app or TLS runtime memory, extracting session keys and plaintext. Afterward, the organization rotates the certificate.

**Problem:** rotating the certificate cannot erase already-captured session data, and FS never promises protection against an **adversary controlling a live endpoint**. Run host/app incident response and determine what data was exposed.

### Scenario F — TLS 1.3 `KeyUpdate` mistaken for a "fresh DH"

A team wants to recover after an attacker steals an application traffic secret, so they only trigger `KeyUpdate`.

**Problem:** `KeyUpdate` derives from the existing traffic secret without exchanging fresh ephemeral DH shares; an attacker holding the base secret can track subsequent key generations. Establish a new handshake with controlled key establishment and authentication to recover per incident-response models.

## 13. Test matrix and self-check questions

### 13.1 Test matrix for Java/TLS deployments

| Test | What to observe | Conclusion |
| --- | --- | --- |
| Full TLS 1.3 certificate handshake | `key_share` + certificate auth + `Finished` | Establishes FS basis via fresh (EC)DHE; still needs endpoint/secret lifecycle |
| TLS 1.2 `ECDHE_RSA` | Actual negotiated suite contains `ECDHE_RSA` | RSA cert authenticates; ECDHE establishes secret |
| TLS 1.2 `TLS_RSA` | Actual negotiated suite uses static RSA key exchange | Lacks FS; eliminate under modern policy |
| TLS 1.3 PSK-only | `psk_ke` mode without fresh `key_share` | Do not assume FS while the PSK persists |
| TLS 1.3 PSK+(EC)DHE | `psk_dhe_ke` and fresh key share | FS for 1-RTT subject to DHE/secret management |
| TLS 1.3 0-RTT | `early_data`, resumption PSK, anti-replay | Do not assume FS or replay safety |
| Invalid certificate/hostname | Handshake rejected | Identity authentication is not bypassed |
| Key logging/debug enabled in production | Check configs, files, ACLs, retention | Prevent leaking session secrets |
| Long-term identity key compromise | Inventory protocols/handshake modes & history | Separate past traffic exposure from future impersonation risk |
| Calling only `getSupportedProtocols()` | Lists `TLSv1.3` | **Insufficient** to confirm negotiated session |
| Replacing RSA certificate with ECDSA | Changes only signature key algorithm | Do not conclude FS without checking key establishment |
| TLS terminates at reverse proxy | Post-proxy network hops and log/data storage | Client-to-proxy TLS FS does not automatically protect downstream hops |

### 13.2 Questions and answers

**Question 1.** Does an X.509 certificate contain each session's ephemeral key?

**Answer:** No. The certificate holds the identity public key and verification metadata. Ephemeral key pairs are generated for handshake key exchange.

**Question 2.** Does an RSA certificate deprive TLS 1.3 of forward secrecy?

**Answer:** No. An RSA certificate can be used for signature authentication; a full TLS 1.3 certificate handshake uses fresh (EC)DHE to establish the shared secret.

**Question 3.** How does TLS 1.2 `TLS_RSA` differ from `TLS_ECDHE_RSA`?

**Answer:** `TLS_RSA` encrypts the premaster secret with the static RSA public key, losing FS if the private key leaks later. `TLS_ECDHE_RSA` uses ephemeral ECDHE to create the premaster secret, while RSA only authenticates the handshake.

**Question 4.** Why can't (EC)DHE prevent MITM on its own?

**Answer:** Because anyone can substitute public shares; you must authenticate the right peer and bind the transcript with signatures/`Finished` per protocol.

**Question 5.** When the server's identity private key leaks after an FS session ended, can an attacker decrypt old packets from that key alone?

**Answer:** Not under standard security assumptions, provided fresh ephemeral key material and past traffic secrets did not leak and algorithms remain sound. However, the attacker can impersonate the server in future handshakes.

**Question 6.** How do session tickets/PSKs affect FS?

**Answer:** PSK-only does not inherently guarantee FS if the PSK remains stored and leaks; PSK+(EC)DHE adds fresh DH to provide FS for 1-RTT. PSK lifetime and deletion are critical operational factors.

**Question 7.** Does 0-RTT early data have the same FS and anti-replay properties as TLS 1.3 1-RTT DHE?

**Answer:** No. Early data relies on PSK and carries cross-connection replay risk; restrict allowed operations and apply matching safeguards.

**Question 8.** Why doesn't `TLS_AES_128_GCM_SHA256` tell you whether X25519 or RSA was used?

**Answer:** TLS 1.3 separates key exchange and signature selection from cipher suite names; inspect the handshake's negotiated `key_share`/PSK/certificate.

**Question 9.** Does this lesson's X25519+Ed25519 demo replace JSSE?

**Answer:** No. The demo lacks PKIX, TLS transcript formatting/`Finished`/HKDF/record layer/host validation, and many mandatory security mechanisms.

**Question 10.** Is `KeyUpdate` enough to recover if an attacker learns the current application traffic secret?

**Answer:** No. `KeyUpdate` does not rerun DH; it only derives a new generation from the current secret.

**Question 11.** Why shouldn't `KeyAgreement.generateSecret()` output be used directly as an AES key by intuition?

**Answer:** TLS uses an HKDF key schedule to separate secrets by context, traffic direction, and phase, avoiding direct reuse of raw shared secrets.

**Question 12.** Once you have FS, do you still need to protect logs, proxies, and databases?

**Answer:** Yes. FS protects past traffic against one specific class of compromise; it does not protect plaintext copies, session key logs, or data already decrypted by endpoints.

## 14. References

- [RFC 9846 (July 2026) — TLS 1.3](https://www.rfc-editor.org/rfc/rfc9846.html): current TLS 1.3 specification, **replacing RFC 8446 (2018)**; §2.2–2.3 on PSK/0-RTT, §4 on handshake, §7 on key schedule, Appendix F on forward secrecy and key compromise.
- [RFC 8446 (2018) — TLS 1.3, historical](https://www.rfc-editor.org/rfc/rfc8446.html): older study resource, now replaced by RFC 9846.
- [RFC 5246 — TLS 1.2, historical](https://www.rfc-editor.org/rfc/rfc5246.html): RSA key exchange and (EC)DHE mechanisms in TLS 1.2 (superseded as current standard by RFC 9846).
- [RFC 10015 (2026) — Deprecating Obsolete Key Exchange Methods in TLS 1.2](https://www.rfc-editor.org/rfc/rfc10015.html): deprecates/recommends discontinuing RSA key transport and obsolete methods in TLS 1.2.
- [Oracle Java SE 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): `SSLContext`, `SSLSocket`/`SSLEngine`, TLS 1.3, handshake, cipher suites, providers, and debugging.
- [Oracle Java SE 17 — KeyAgreement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyAgreement.html): API for computing shared secrets with X25519.
- [Oracle Java SE 17 — Signature](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html): API for signing/verifying identity signatures.
- [Oracle Java SE 17 — Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): names for X25519/Ed25519/TLS algorithms and cipher suites.
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525.html): guidelines for verifying service identity when using TLS.

## Conclusion

**Long-term identity keys and ephemeral keys solve two different problems.** The private key matching a certificate **authenticates** the peer and binds the handshake; ephemeral (EC)DHE establishes a shared secret **independent of decrypting a premaster secret with a static identity private key**. With fresh (EC)DHE, proper KDF handling, and ephemeral secret erasure, stealing the identity private key **after a session** is not enough to decrypt previously recorded traffic: that is the practical meaning of forward secrecy.

When evaluating a TLS connection, examine the **actual session protocol, key exchange/resumption mode, 0-RTT, certificate validation, and key lifecycle**—never conclude from certificate type or cipher suite name alone. **TLS 1.2 static RSA key transport lacks FS; TLS 1.2 (EC)DHE and full TLS 1.3 certificate handshakes using fresh (EC)DHE provide FS under the appropriate model; TLS 1.3 PSK-only and 0-RTT are exceptions that must be deliberately managed.** In Java 17+, let **JSSE** run TLS, and use JCA X25519/Ed25519 only for learning primitives or rigorously audited specialized protocols.