# 1.3 Distinguishing Confidentiality, Integrity, Authentication, and Authorization

The four concepts **confidentiality**, **integrity**, **authentication**, and **authorization** answer four distinct questions in Java application security: **who can know the data**, **whether the data has been altered**, **who the interacting principal is**, and **what that principal is allowed to do**. A system can get the first three right and still leak data if authorization checks fail.

## 1. Four Questions That Must Be Kept Separate

| Property | Core Question | Risk If Missing | Typical Mechanism |
| --- | --- | --- | --- |
| **Confidentiality** | Who can **read/know** the content? | Unauthorized parties see sensitive information | TLS, encryption at rest, key management, read access restrictions |
| **Integrity** | Has the content been **modified** without authorization or unexpectedly? | Amounts, commands, files, or messages altered undetected | HMAC, digital signatures, authenticated encryption like AES-GCM, data validation |
| **Authentication** | **Who** is the requesting principal, and is the identity proof trustworthy? | Another party impersonates a legitimate user/service | Securely verified passwords, MFA, passkeys, sessions, tokens, certificates |
| **Authorization** | What **actions on which resources** is the authenticated identity allowed in this context? | Legitimate users access other users' data or privileges | Resource ownership checks, RBAC, ABAC, policies, least privilege |

Remember: **identity authentication precedes authorization decisions**, yet both differ from data confidentiality and integrity. When referring to the security **CIA** triad, the A stands for **Availability**, not Authentication.

### 1.1. Confidentiality: Preventing Data Disclosure

Confidentiality requires information to be exposed only to principals permitted to know it. Consider everywhere data exists and moves:

- **In transit:** HTTPS/TLS hides content from network eavesdroppers when connections are established and certificates are verified properly.
- **At rest:** encrypt sensitive data on disk, in backups, or per field; decryption keys must be protected and scoped separately.
- **In application:** prevent tokens, passwords, secret keys, or personal data from leaking into logs, error messages, caches, or overly broad API responses.
- **At the access boundary:** even when the server can decrypt, it must still determine who is allowed to view the result.

For example, an AES-encrypted file can still leak if an endpoint decrypts and returns its content to any logged-in user. **Encryption does not create a rule for who may read**.

In Java, **AES-GCM** is a common choice for authenticated symmetric encryption: it protects confidentiality and detects ciphertext tampering when keys, nonces, and associated authenticated data are used properly. Proper key management and never reusing a nonce with the same key are mandatory conditions.

### 1.2. Integrity: Detecting or Preventing Unauthorized Modification

Integrity concerns whether data remains in its trusted state. Distinguish the tools:

- **Keyless SHA-256** creates a fingerprint of content. It helps when the expected hash comes from a trusted source. If an attacker can alter both the file and the published hash, comparing hashes neither proves origin nor prevents tampering.
- **HMAC-SHA256** uses a shared secret key to produce a message authentication code. Anyone without the key cannot feasibly forge a valid HMAC for altered content. HMAC does not encrypt content; any party holding the shared key can create tags.
- **Digital signatures** use a private key to sign and a public key to verify integrity and signing origin. Binding a public key to a specific identity still requires a trust mechanism such as certificates or authenticated key distribution.
- **AEAD**, such as AES-GCM, combines encryption with integrity/authenticity checks over ciphertext and AAD bound into the tag.

**Integrity does not mean freshness.** A valid HMAC message can be replayed. Depending on the protocol, add nonces, sequence numbers, expirations, idempotency keys, or replay caches and enforce them on the server.

Do not use ordinary string comparisons to check MACs in ways that can leak timing information; Java provides **MessageDigest.isEqual(byte[], byte[])** to compare byte arrays in a manner better suited for this purpose.

### 1.3. Authentication: Verifying Identity Before Trusting Requests

Authentication establishes a **principal** (user, service, device, or process) via evidence the system can verify, rather than trusting a self-declared name in the request.

- For users: password verifiers stored using a salted, cost-tuned password hashing algorithm (e.g., Argon2id, scrypt, or PBKDF2), paired with MFA/passkeys when needed. Never store raw passwords or use plain SHA-256 as a password hashing solution.
- For login sessions: the server validates a session or access token; session cookies need appropriate protection attributes like Secure, HttpOnly, and SameSite depending on context.
- For signed tokens: beyond the signature, validate issuer, audience, expiration, token type, and applicable application constraints. A token with a valid signature but wrong audience must still be rejected.
- For services: mTLS can authenticate identity via client certificates; a verified service identity remains subject to authorization policies.

Also separate **caller authentication** from **cryptographic message origin authentication**. HMAC proves a party holding the shared key generated or endorsed the message, but if multiple parties share the key, it does not identify which specific party sent it. Digital signatures can bind to one principal when keys and certificates are properly governed. Neither replaces the full user login flow.

**HTTPS/TLS** typically helps clients authenticate the server via valid certificates while protecting transport; it does not automatically tell the application that an end user is logged in.

### 1.4. Authorization: Deciding Actions on the Right Resource

After authentication, the backend uses the trusted identity and current context to decide whether to allow a **specific action**. Permissions must be checked at both the feature level **and** the object level.

For example, Alice and Bob both have the USER role and both log in successfully. Yet for a document owned by Alice, Bob must still be denied if the policy only allows the owner or an administrator to read it. Skipping this check is a form of **Broken Object Level Authorization (BOLA/IDOR)**.

Common policy models:

| Model | Decision Based On | Example |
| --- | --- | --- |
| **RBAC** (role-based) | Roles assigned to the principal | ADMIN can manage accounts |
| **ABAC** (attribute-based) | Principal, resource, and environment attributes | Allow reading records only in the same tenant and not locked |
| **Ownership/relationship check** | Relationship to the requested object | Document owner can read their own document |

Real systems often **combine** models: the caller must hold the READ_DOCUMENT permission, belong to the same tenant, and be the owner or in a shared group. Follow **deny by default**, **least privilege**, and server-side checks for every sensitive operation. Hiding UI buttons, enabling CORS, or holding a valid token does not replace these checks.

Trusted identity, roles, and tenant must come from verified authentication components and backend data; never take client-supplied role or ownerId directly to make authorization decisions.

## 2. One Technology Can Serve Multiple Goals, But Cannot Imply All of Them

| Measure | What It Actually Provides | What It Does Not Provide on Its Own |
| --- | --- | --- |
| **HTTPS/TLS** | Confidentiality and integrity in transit; endpoint authentication per certificate config | User login or per-document access permissions |
| **AES-GCM** | Confidentiality and tamper checks for ciphertext/AAD | User identity, object authorization, business-level replay protection |
| **File SHA-256** | Fingerprint to compare against a trusted expected hash | Proof of sender if the hash can also be altered |
| **HMAC-SHA256** | Integrity and proof of shared-key possession | Hiding content, distinguishing individual shared-key holders, authorization decisions |
| **Digital signature** | Tamper check and evidence bound to a signing key | Hiding content, application authorization |
| **Verified session/token** | Identity proof per authentication flow | Permission to read every record |
| **RBAC/ABAC + resource checks** | Decision to allow/deny an action | Data encryption or transport integrity proof |

**Common traps:**

1. **Logged in, yet able to read someone else's order:** authentication succeeded, **authorization failed**.
2. **Using HTTPS, yet writing passwords to logs:** transport is protected, but **confidentiality is broken** at the application layer.
3. **File with a public SHA-256 hash hosted right next to it and both are altered:** no trusted basis to conclude the file is intact.
4. **Encrypted payload using an unauthenticated mode:** confidentiality does not guarantee detecting tampering; use an appropriate AEAD mode.
5. **Valid HMAC on an old money-transfer command replayed:** message integrity may hold, yet business logic must prevent replay.

## 3. Following One Request: Four Independent Verification Steps

Consider the API **GET /documents/42**, where the record has **ownerId = alice** and the caller is **bob**:

1. **Transport protection:** client connects over HTTPS and verifies the server certificate. TLS protects content in transit, but does not decide whether Bob can view document 42.
2. **Authenticating Bob:** middleware checks the session or token and resolves the principal as bob. Missing/invalid credentials typically return **401 Unauthorized** (a slightly confusing HTTP name: this status relates to authentication requirements).
3. **Object authorization:** backend fetches document metadata and evaluates policy: does Bob have READ_DOCUMENT, the right tenant, and ownership or sharing access? If not, typically return **403 Forbidden**; some systems intentionally return **404** to avoid revealing resource existence, though the policy must be consistent.
4. **Fetching and returning content:** if permitted, the server returns the data; transport encryption and integrity mechanisms continue protecting it on the wire. If stored encrypted, decryption happens only after required permission checks pass.

An actual request might check permissions before and after loading metadata, or embed permission predicates directly into queries (e.g., scoping by principal/tenant). The invariant is **never return a document before confirming permission for that exact document**; never check merely "is logged in" or "has role USER".

Notable variants:

- **POST /documents:** requires creation permission in the selected tenant/group; never let the client set ownerId/tenantId to escalate privileges.
- **PUT /documents/42:** read permission does not automatically grant edit permission.
- **GET /documents?tenantId=...:** must restrict results to actually authorized tenants; frontend-only filtering is insufficient.
- **Service-to-service calls:** even after mTLS/token authentication, check that the service account is permitted to call the specific endpoint.

## 4. One Request, Four Independent Decisions

Suppose Bob calls `GET /documents/42`; this record has `ownerId=alice`, and its content is stored using AES-GCM. Verifying each property happens in different places:

| Check Order | Question | Outcome If Failed |
| --- | --- | --- |
| **Transport confidentiality** | Is the client connected to the right HTTPS server with a valid certificate and hostname? | Do not exchange sensitive content over an unverified endpoint |
| **Caller authentication** | Is the session/token valid, matching issuer/audience/expiration, and mapped to Bob? | Reject unauthenticated request (typically 401) |
| **Object authorization** | Does Bob have READ_DOCUMENT permission on document 42, in the right tenant and current conditions? | Deny before fetching/returning plaintext (403 or 404 per policy) |
| **Ciphertext integrity** | Once authorized to decrypt, do the key, nonce, ciphertext/tag, and AAD validate successfully? | Discard result, return controlled error, never use unauthenticated plaintext |

Implementation order may vary with queries and caching, yet **plaintext must never be returned to Bob without checking permission on document 42 itself**. Success of `Cipher.doFinal` or a payload HMAC is not proof that Bob may view the document. Conversely, having read permission on the document does not permit skipping tag verification on stored data.

Primitive-level behavior of AES-GCM can be tested by altering a byte of ciphertext/AAD and catching `AEADBadTagException`; this lesson focuses on **how to place security checks across different layers** rather than repeating a standalone encryption program.

## 5. Java 17+: Demonstrating HMAC Integrity and Owner Authorization

The next example intentionally separates two concerns: **verifyHmac** verifies whether a message was altered after tag generation; **canRead** checks whether an authenticated principal may read a document. In a real application, principal must come from verified middleware/session state, **never constructed from a self-declared userId in the request**.

Save as **HmacAuthorizationDemo.java**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Set;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class HmacAuthorizationDemo {
    record Principal(String userId, Set<String> roles) {}
    record Document(String ownerId, String content) {}

    static byte[] hmac(String message, byte[] secret)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(message.getBytes(StandardCharsets.UTF_8));
    }

    static boolean verifyHmac(String message, byte[] expectedTag, byte[] secret)
            throws GeneralSecurityException {
        return MessageDigest.isEqual(expectedTag, hmac(message, secret));
    }

    static boolean canRead(Principal principal, Document document) {
        return principal.roles().contains("ADMIN")
                || principal.userId().equals(document.ownerId());
    }

    public static void main(String[] args) throws Exception {
        byte[] secret = "demo-secret-change-in-production"
                .getBytes(StandardCharsets.UTF_8);
        String payload = "owner=alice;amount=900";
        byte[] tag = hmac(payload, secret);

        System.out.println("Original message valid: "
                + verifyHmac(payload, tag, secret));
        System.out.println("Altered message valid: "
                + verifyHmac("owner=alice;amount=990", tag, secret));

        Document doc = new Document("alice", payload);
        Principal alice = new Principal("alice", Set.of("READER"));
        Principal bob = new Principal("bob", Set.of("READER"));

        System.out.println("Alice can read: " + canRead(alice, doc));
        System.out.println("Bob can read: " + canRead(bob, doc));
    }
}
```

Compile and run:

```bash
javac HmacAuthorizationDemo.java
java HmacAuthorizationDemo
```

Stdout output:

```text
Original message valid: true
Altered message valid: false
Alice can read: true
Bob can read: false
```

**Explanation of output:**

- The original message matches the HMAC; changing **900** to **990** while keeping the old tag causes verification to fail. HMAC **does not hide message content**.
- Alice is the document owner so she can read it; Bob shares the READER role but does not own the document, so he is denied. In this illustrative policy, ADMIN can also read. This is a **separate authorization rule**, completely independent of whether the payload's HMAC is valid.
- The two Principal objects are constructed directly to test the policy. This is **not a login authentication example**. Never treat a client-supplied username as a verified principal.
- The hardcoded HMAC key is for demonstration only. In production, use a strong secret key from a secret manager, restrict who can access the key, implement key rotation, and enforce context/time/replay controls per protocol.

## 6. Common Design and Reasoning Mistakes

| Flawed Claim | Why It Fails and How to Fix |
| --- | --- |
| "Once logged in, any ID can be accessed." | Authentication only establishes identity. Enforce authorization on **every action and every object**, including owner and tenant. |
| "Having HTTPS means the API is secure." | TLS protects the channel; it does not fix access control bugs, sensitive data in logs, or application secret leaks. |
| "Self-hashing with SHA-256 guarantees the server sent the data." | Keyless hashes do not prove origin; use a trusted expected hash, HMAC, or signature depending on the trust model. |
| "Encryption implies tamper resistance." | Not all encryption modes are authenticated; prefer AEAD like AES-GCM and reject data when tag verification fails. |
| "A JWT with a valid signature is enough." | Must also validate issuer, audience, expiry, key, and applicable policies; object permissions are still checked separately. |
| "Hiding the edit button or enabling CORS is authorization." | Client UI and CORS are not backend authorization gates; reject unauthorized actions on the server. |
| "HMAC proves Alice signed it." | HMAC uses a shared key: any key holder can generate a MAC; binding to an individual requires appropriate identity/key separation. |
| "A message with a valid signature must be a fresh request." | Signatures/MACs do not prevent replay by themselves; require timestamps, nonces, sequences, or idempotency controls. |
| "Passwords should be encrypted so they can be decrypted on login." | Passwords should be stored as salted/cost-tuned password hashes; verify against the verifier on login without decrypting the original password. |

When reviewing a Java application, ask in sequence:

1. **Confidentiality:** which data is sensitive, and where does it appear across transport, storage, logs, caches, and responses? Who holds the keys?
2. **Integrity:** how is tampering detected? Who trusts the hash, MAC, signature, or tag? Is replay prevented?
3. **Authentication:** what evidence verifies the principal? Are sessions/tokens/certificates fully validated and time-bounded?
4. **Authorization:** who is allowed **which action + which resource + which tenant/context**? Is deny-by-default enforced on the server?

## 7. Scenario-Based Self-Check

**Scenario A.** Bob logs in successfully. The API returns Alice's invoice when Bob changes the ID in the URL. Which property is missing?  
**Answer:** **Authorization**, specifically object-level authorization (BOLA/IDOR). Authentication may be completely sound.

**Scenario B.** A user downloads a file and compares its SHA-256 against a value fetched from the same compromised webpage. Is integrity proven?  
**Answer:** **No trusted basis.** An attacker can replace both the file and the hash. The expected hash/verification key must come from a trusted source.

**Scenario C.** Two services share an HMAC key; the tag is valid. Can we prove only service A sent it?  
**Answer:** **No.** The tag proves the creator knew the shared key, without distinguishing among parties holding that key. Separate identities and keys are needed if business rules require attribution.

**Scenario D.** A server stores documents with AES-GCM. A legitimate user calls the API to decrypt another user's document. Should the content be returned because decryption succeeded?  
**Answer:** **No.** AES-GCM handles ciphertext confidentiality and tamper detection; the backend must still authenticate the user and authorize document access.

**Scenario E.** A signed command is replayed verbatim an hour later. The signature is still valid. What else does the system need?  
**Answer:** Checks for expiration, nonce/sequence number, and processing state to prevent **replay**, per protocol requirements.

Key takeaway to carry into upcoming cryptography and application security lessons: **confidentiality protects against seeing content; integrity protects against modification; authentication establishes a trusted identity; authorization enforces policy on specific actions/resources.** Secure design requires placing these layers at the right boundaries, never inferring one layer's success from another.
