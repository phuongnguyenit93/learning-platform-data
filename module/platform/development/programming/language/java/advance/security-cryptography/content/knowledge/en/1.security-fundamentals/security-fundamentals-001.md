# 1.1 What Problems Do Information Security and Cryptography Solve in Java Applications?

Java applications commonly store accounts, process transactions, transmit data over networks, and call other services. A functionally correct program can still cause harm if unauthorized parties read data, alter messages, impersonate senders, or misuse stolen information. **Information security** is the goal of protecting systems and data against those risks; **cryptography** provides essential technical mechanisms to achieve a subset of those protection goals.

This lesson answers three questions: *What needs to be protected? Which problems do cryptographic mechanisms solve? How should those mechanisms be selected and combined in a Java application?* This is a foundational lesson on problem framing and security thinking; specific algorithm configurations, protocols, or large-scale key management systems must be designed separately according to real-world requirements.

## 1. Identifying Assets, Adversaries, and Trust Boundaries

Consider a Java e-commerce application:

1. Users log in and submit orders from a browser to a Java API.
2. The Java API reads customer information from a database.
3. The API calls a payment gateway and receives transaction notification webhooks.
4. The system writes logs, creates backups, and sends notifications to users.

Assets requiring protection include passwords or password verifiers, session tokens, personal data, amounts/orders, cryptographic keys, secret configurations, logs, and backups. Threats can come from network eavesdroppers, packet modifiers, compromised accounts, authorization flaws, operations staff, or compromised servers.

A **trust boundary** is where data moves between components with different levels of control: browser → API, API → database, API → payment service, running system → backup storage. Whenever data crosses a boundary, ask:

- Who is allowed to read, create, modify, or send this data?
- How does the receiver prove the sender's identity?
- If the message is modified in transit, who will detect it?
- Where do keys and secrets reside; what is the consequence if they are leaked?
- What still needs to be done even after encryption, such as access control or replay protection?

No single algorithm answers all of these questions.

## 2. Information Security Goals an Application Must Achieve

| Goal | Question to Address | Example in a Java Application |
| --- | --- | --- |
| **Confidentiality** | Can unauthorized parties read the content? | Hide customer data in transit or at rest; use TLS and encrypt sensitive data where needed. |
| **Integrity** | Can content be modified without authorization and go undetected? | Detect whether an amount in a message was altered; use message authentication codes, digital signatures, or authenticated encryption modes. |
| **Authenticity** | Does the message or communicating party genuinely come from a trusted principal? | Authenticate HTTPS servers, verify webhook signatures, and bind verification keys to the right identity. |
| **User Authentication** | Who is requesting this action? | Log in using an appropriate method, validate sessions/tokens, and require step-up authentication for high-risk actions. |
| **Authorization** | What is an authenticated principal allowed to do? | User A must not read User B's orders; enforce server-side checks per resource and action. |
| **Availability** | Does the service continue serving legitimate requests under failures or attacks? | Rate limiting, redundancy, backup recovery, monitoring, and incident response. |
| **Accountability / Conditional Non-repudiation** | Is there reliable evidence of an action or signature? | Digital signatures paired with key protection processes, identity binding, and proper evidence storage; a signature alone does not guarantee legal validity. |

The classic triad is **CIA: Confidentiality – Integrity – Availability**. Real-world systems also require authentication, authorization, auditability, and operational controls.

A crucial distinction: **authentication** answers "who are you?", whereas **authorization** answers "what are you allowed to do?". A valid token does not mean its holder can access every record. Cryptography can support authentication, but it cannot replace business-level authorization checks.

## 3. Cryptographic Mechanisms Solve Different Problems

### 3.1. Symmetric Encryption: Keeping Content Confidential

A **shared secret key** is used for both encryption and decryption. In Java, a common choice for application data is **AES-GCM**, because it protects content confidentiality while also verifying the integrity of the ciphertext and additional authenticated data (AAD).

Use this when protecting a sensitive stored field, backup file, or message where both sides already securely share a key. The ciphertext still requires the key to be read. Factors to manage include: generating sufficiently strong keys, storing keys separately from the data, **never reusing a nonce/IV with the same key**, storing the IV alongside the ciphertext, and verifying the authentication tag before using the decrypted result.

**Limitation:** encryption does not decide which user is allowed to read a record after the server decrypts it. Key compromise can expose the corresponding data; encryption does not fix authorization bugs.

### 3.2. Asymmetric Cryptography: Public Keys and Private Keys

A key pair consists of a **public key** that can be shared and a **private key** that must be kept secret. Different algorithms serve different goals: RSA-OAEP can encrypt appropriately sized data; Ed25519 is used for **digital signatures**, not encryption; ECDH/X25519 is used for key agreement and does not authenticate peer identity by itself.

In real applications, bulk data is typically encrypted with a symmetric key; asymmetric mechanisms help exchange or wrap keys, verify signatures, or establish secure communication sessions. Do not assemble primitives into a custom transport protocol when TLS and vetted libraries already exist.

### 3.3. Cryptographic Hash Functions: Creating a Data Fingerprint

Functions like **SHA-256** transform arbitrary data into a fixed-length value. Changing the data typically changes the hash value; it serves as a tool for fingerprinting, checking integrity when **the expected hash comes from a trusted source**, and acting as a building block in other mechanisms.

**SHA-256 is not encryption:** there is no "hash decryption" operation. However, a bare hash of a message **does not prove who sent it**: anyone modifying the data can also recompute the hash. Furthermore, CRC32 or ordinary checksums are not tools to protect against intentional tampering.

### 3.4. MAC/HMAC: Detecting Tampering and Authenticating Key Holders

**HMAC-SHA256** uses a shared secret key to generate a message authentication code. A receiver holding the key can check whether the content and MAC match. It fits when two trusted systems share a secret, such as a provider-specified webhook using HMAC.

HMAC **does not encrypt content**. Because both sides know the key, HMAC cannot prove to a third party which specific side signed it. HMAC itself also does not prevent replaying an old valid message; protocols must add timestamps, nonces, transaction IDs, expiration windows, or idempotency.

### 3.5. Digital Signatures: Verifying Source and Content

The signer uses a private key to generate a signature over the **exact byte sequence**; the verifier uses the corresponding public key to verify it. If the content changes, the old signature becomes invalid. Examples include verifying release packages, documents, or signed webhooks.

**Mandatory condition:** the public key must be bound to the right identity through a trusted channel, certificate, or verified configuration. A signature does not make data confidential, does not inherently prove the signing time, and does not automatically establish legal validity if the private key is shared, stolen, or poorly governed.

### 3.6. Dedicated Password Hashing: Store a Verifier, Not the Password

User passwords must not be stored in plaintext, with reversible encryption, or with a single pass of SHA-256. At registration, the system generates a **unique random salt per password** and computes a password derivation/hashing function with appropriate cost, such as **Argon2id** (typically via a maintained library) or **PBKDF2WithHmacSHA256** in the JDK when infrastructure alignment is required. Store the salt, algorithm parameters, and result; at login, compute and compare using the library's verification mechanism.

The salt does not need to be kept secret; its role is to prevent identical passwords from producing identical hashes and to hinder precomputation attacks. A **pepper**, if used, is an additional secret that must be managed separately from the database. Cost parameters need tuning, testing, and updating over time; do not invent your own password hashing algorithm.

### 3.7. Secure Randomness, Certificates, and TLS

- **SecureRandom** generates keys, nonces, random tokens, or salts requiring unpredictability. **Random**, system timestamps, and incrementing sequence numbers are unsuitable for generating security secrets.
- **X.509/PKI certificates** help bind a public key to an identity when the trust chain and hostname are validated properly.
- **TLS/HTTPS** protects connections between specific endpoints: authenticating the server and providing transport confidentiality and integrity. In Java, use standard HTTP/TLS stacks (JSSE, HttpClient, frameworks) instead of building a custom cryptographic protocol.

TLS only protects **each individual connection**. Data already decrypted inside the application, written to logs, or forwarded over another connection still needs appropriate protection. Never disable certificate or hostname verification just to make connection errors go away.

## 4. Mapping "Problem → Mechanism → Remaining Responsibilities"

| Scenario | Suitable Mechanism | What Must Still Be Checked |
| --- | --- | --- |
| Browser calls Java API over the Internet | HTTPS/TLS with valid certificate and hostname | Session authentication, authorization, input validation, CSRF where applicable, safe error handling |
| Storing account passwords | Argon2id/PBKDF2 with unique salt and cost parameters | Brute-force protection, MFA when needed, reset policies, and session protection |
| Storing national IDs or sensitive files | AES-GCM or a managed encryption mechanism | Key management, post-decryption access control, backup storage, minimizing sensitive data in logs |
| Receiving payment webhooks | Digital signature or HMAC verification **per provider specification** | Validating exact raw payload/canonical form, expiration, replay, idempotency, transaction state |
| Verifying downloaded software packages | Hash comparison from a verified source or release signature | Trusting the hash/public key source, release pipeline, rollback protection |
| Issuing and validating access tokens | Opaque tokens or signed tokens fitting the architecture | Checking issuer/audience/expiry/algorithm/key, revocation when needed, endpoint authorization |
| Logging sensitive events | Minimal logging, access control, log integrity; optional signatures/hash chains if required | Storage protection, time sync, tamper/deletion protection, data retention policies |
| Mitigating service overload, DDoS, or logic bugs | Rate limits, quotas, timeouts, caching, redundancy, monitoring | Encryption and signatures **do not directly solve** availability |

A single request may require multiple mechanisms at once. For instance, a webhook with a valid HMAC could still be an old replayed message, or request business processing that already completed. HMAC checks the message, while business logic must check state and duplicate processing.

## 5. Two Security Questions on the Same Order

Suppose a Java application receives a payment command `order=42;amount=250000` and stores the transaction info for another service to read. **The same data** raises different questions:

- **Can someone who steals a backup read the amount?** This is a data-at-rest confidentiality goal. Authenticated encryption like AES-GCM can be used with keys separated from the backup; do not store keys alongside ciphertext under the same read permissions.
- **Can the webhook receiver tell if the message was modified or came from an authorized sender?** This is a message integrity and authenticity goal. If the protocol defines a shared secret, HMAC-SHA256 fits; if an independent third party needs to verify it, use a digital signature with a public key bound to the signer.
- **Should a webhook with a valid tag or signature be recorded multiple times?** No. The protocol/business logic must still verify whether the event was already processed, check freshness/nonce, and enforce idempotency.
- **Can any logged-in user read any order?** No. This is an object-level authorization problem; AES-GCM, HMAC, signatures, and TLS cannot decide this alone.

You must specify **which adversary is blocked**, **who holds which key**, and **where verification occurs**. A solution that protects backups well can still fail if the API decrypts and returns plaintext to the wrong user; a valid HMAC webhook can still be a replayed old event.

## 6. Tests That Prove a Mechanism Solves the Right Problem

| Goal | Suitable Test | What Cannot Be Inferred From That Result Alone |
| --- | --- | --- |
| Data-at-rest confidentiality | Reading a backup with an account lacking decryption keys must not yield plaintext | That an authorized API user cannot leak plaintext in logs/responses |
| Tamper detection | Modifying ciphertext/tag/AAD must cause AEAD decryption to reject | That the client is authorized for that specific record |
| Webhook authenticity | Modifying payload bytes while keeping the old MAC/signature must fail verification | That the message has not already been processed before |
| Data authorization | User A changing the ID to User B's record must be rejected by the backend | That bytes stored in the DB are encrypted |

Here we only need **selection and evaluation guidance**. Java implementation examples for each primitive, how to compare hashes/MACs/signatures, and byte formatting are covered separately in the lesson distinguishing these mechanisms; this lesson keeps the focus on **which security problems require applications to combine mechanisms with access control**.

## 7. Choosing the Right Java Primitive and Placing It in the Right Protection Layer

| Need | Common API/Mechanism | Key Takeaway |
| --- | --- | --- |
| Generating unpredictable values | **java.security.SecureRandom** | Use for secrets, IVs/nonces/salts as required by each algorithm. |
| Hashing content | **MessageDigest** with SHA-256 | A bare hash does not prove the sender and must not be used as a password hash. |
| Message authentication with shared key | **javax.crypto.Mac** with HmacSHA256 | Compare MACs securely; attach timestamps/nonces if replay protection is needed. |
| Encrypting data | **javax.crypto.Cipher**, **KeyGenerator**, **GCMParameterSpec** | Use AEAD and manage keys/IVs/tags properly. |
| Signing/verifying | **java.security.Signature**, **KeyPairGenerator** | Verify the public key's origin; the private key stays only with the signer. |
| Password key derivation | **SecretKeyFactory** with PBKDF2WithHmacSHA256 or an Argon2id library | Distinguish password verifiers from encryption keys; tune parameters to the threat model. |
| Storing/reading keys by design | **KeyStore** or platform KMS/HSM | KeyStore is a key storage interface; access policies, backups, and rotation still need design. |
| TLS-protected connections | **java.net.http.HttpClient**, JSSE, framework HTTPS | Keep default certificate/hostname verification; protect every connection hop. |

The table above is a **responsibility map**, not a guarantee that calling an API makes a system secure. Protection outcomes still depend on key origins, input data, error-handling behavior, and system-wide trust boundaries.

## 8. Application Design Example: Login and Payment Flows

### Registration and Login

1. The browser sends credentials over HTTPS to the Java API.
2. During registration, the server uses a dedicated password hashing function with a unique salt and chosen cost parameters; never store plaintext passwords.
3. During login, the server verifies the password against the stored record, applying brute-force rate limits and account takeover protections based on risk.
4. If valid, the server issues a session/token with clear lifetime, scope, storage rules, and revocation mechanism. Never log tokens or passwords.
5. Every API reading/modifying orders still checks resource ownership; never trust "already logged in" alone.

### Creating Orders and Receiving Payment Notifications

1. The API authenticates the requester, validates the amount, and checks business-level permissions.
2. The API calls the payment partner over TLS, handling secrets via a secret manager or KMS when available.
3. When a webhook arrives, the system verifies the signature/HMAC **over the exact data specified by the provider**, verifying key origin, expiration, and replay indicators.
4. The server uses a unique transaction ID and checks the current state for **idempotent** processing: receiving the same webhook twice must not record payment twice.
5. Logs contain enough information for auditing without exposing card numbers, secret tokens, keys, or unnecessary sensitive data.

In both flows, cryptography protects transport, data, and messages; **business rules and access control** remain indispensable separate layers.

## 9. Key Management: Where Many "Algorithmically Correct" Designs Still Fail

An application using standard AES-GCM can still lose all security benefits if keys are placed in source code, container images, logs, or exposed alongside the database. Define the key lifecycle before implementation:

- **Key generation:** use a cryptographic random source and algorithm-compatible key size/type, never derive from timestamps or hardcoded strings.
- **Access provisioning:** grant access only to necessary services following least privilege; never distribute signing private keys to verifier-only parties.
- **Key storage:** choose a protected keystore, secret manager, KMS, or HSM depending on the environment; separate development and production secrets.
- **Identification and rotation:** long-lived encrypted data must track which key version was used; plan re-encryption/recovery when rotating keys.
- **Compromise and revocation:** establish procedures to replace keys, invalidate sessions/tokens, assess affected data, and monitor incidents.
- **Backup and recovery:** losing a key can permanently destroy data; key backups must be protected and tested accordingly.
- **Operations:** avoid exposing keys or secret contents in stack traces, metrics, crash dumps, logs, and debug commands.

Not all data needs per-field encryption: TLS, disk encryption, column encryption, and other controls protect at **different boundaries**. Choose according to the threat model and real compliance requirements, avoiding cryptography that cannot be operated safely.

## 10. Common Misconceptions That Lead to Vulnerabilities

1. **"Base64 is encryption."** False. Base64 only changes byte representation and can be decoded directly without any secret.
2. **"SHA-256 for passwords is enough."** False. Fast hashes allow high-speed guessing; use a dedicated password function, unique salts, and adequate cost.
3. **"We use HTTPS, so data in the database and logs is safe."** False. TLS protects transport between endpoints; other data copies have their own boundaries.
4. **"Having a digital signature makes the content secret."** False. Signatures support integrity/source authenticity; confidentiality requires proper encryption.
5. **"Checking HMAC once prevents webhook replay."** False. Old messages still carry valid MACs; freshness, deduplication, and idempotency are required.
6. **"Encrypting data is enough to stop unauthorized reading."** False. The server can decrypt for unauthorized users if per-resource authorization checks are missing.
7. **"Cryptography fixes SQL injection, XSS, or business logic flaws."** False. Input/output handling, parameterized queries, authorization, and dedicated testing are required.
8. **"Using AES-GCM with a fixed IV is more convenient."** Dangerous. Reusing a key/IV pair breaks critical GCM security guarantees.
9. **"Ignoring TLS certificate errors only affects test environments."** Dangerous if configs leak to other environments; fix the trust chain or certificate properly.
10. **"Strong algorithms guarantee a secure system."** False. Implementation, key management, identity verification, authorization, monitoring, and incident response all determine the outcome.

## 11. Process for Choosing a Solution for a Security Requirement

Before choosing a Java API, answer in order:

1. **What is the asset?** Personal data, passwords, messages, documents, tokens, or keys?
2. **Who is the adversary and what can they do?** Network eavesdropping, message tampering, reading database backups, compromising one account, or compromising a server?
3. **Which goals apply?** Confidentiality, integrity, source authenticity, authorization, availability, or audit evidence?
4. **Which boundaries exist?** In transit, in memory, at rest, between services, or with third parties?
5. **Who holds keys and who trusts whom?** Shared keys, key pairs, public key origin, versioning/rotation, and compromise recovery path?
6. **Does a standard protocol exist?** Prefer TLS and maintained, vetted standard mechanisms; do not invent algorithms or custom protocols.
7. **How is it verified?** Are there tests for tampered data, wrong keys, expired messages, replays, denied authorization, TLS errors, recovery, and rotation?

A concrete requirement should lead to a **concrete verification goal**. For example: "someone who reads a database backup must not see field X" may lead to encrypting field X and separating key access from the database. Conversely, "User A must not view User B's orders" requires server-side authorization checks regardless of whether the data is encrypted.

## 12. Knowledge Self-Check

**Q1.** A client sends an amount accompanied by the SHA-256 of that amount. The server receives both over an attacked channel. Can the server verify the sender?  
**Answer:** No. An adversary can change the amount and recompute SHA-256. An appropriate source/message authentication mechanism such as HMAC/signature or a trusted authenticated channel/protocol is needed.

**Q2.** Does HTTPS prevent a logged-in user from viewing another user's data?  
**Answer:** No. HTTPS protects the connection; the server must enforce authorization checks on every record and action.

**Q3.** If you need to store passwords for later verification, should you choose AES or a single SHA-256 hash?  
**Answer:** Choose neither as the primary mechanism. Use a dedicated password hashing function with a salt and appropriate cost parameters (e.g., Argon2id or PBKDF2 per deployment requirements).

**Q4.** Is a valid webhook signature enough to credit an account immediately?  
**Answer:** Not enough. You must verify the key belongs to the right partner, the payload is right, freshness, and transaction state; handle idempotently to prevent duplicate operations.

**Q5.** Why does the AES-GCM example both decrypt the original plaintext and reject modified ciphertext?  
**Answer:** AES-GCM is an authenticated encryption mode (AEAD). The tag binds the content and AAD to the key/IV; tag verification failure causes the API to reject mismatched data.

**Key takeaway:** Information security defines what must be protected. Cryptography provides tools such as encryption, MACs, hashes, signatures, password hashing, and TLS to protect specific goals. A secure Java application emerges only when the right tools are chosen, keys are managed properly, and cryptography is combined with authentication, authorization, input validation, operations, and recovery capabilities.
