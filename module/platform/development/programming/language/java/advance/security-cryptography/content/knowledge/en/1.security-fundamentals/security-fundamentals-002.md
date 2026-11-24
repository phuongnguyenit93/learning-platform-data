# 1.2 Threat Modeling, Assets to Protect, and Trust Boundaries

Threat modeling is a way of analyzing a system from a security perspective: **what are we protecting, who or what can cause harm, how do they reach it, and which measures bring risk down to an acceptable level?** It is an iterative design and review activity that evolves with the system, not a vulnerability checklist or a one-time security scanner run.

In the **Java Advance - security-cryptography** module, threat modeling helps decide where authentication, authorization, integrity protection, encryption, key management, auditing, and resource limits are needed. Choosing an encryption algorithm before identifying assets and attack paths easily leads to a solution that is secure on one transport link yet leaks data at the application layer.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **asset**, **threat actor**, **threat**, **vulnerability**, **attack scenario**, **control**, and **residual risk**.
2. Inventory assets across the data lifecycle, including raw data, secret keys, tokens, access permissions, logs, and backups; identify the security properties required for each asset.
3. Draw data flows and **trust boundaries** across clients, Java services, databases, key management services, and third parties.
4. Use STRIDE alongside business abuse scenarios to uncover concrete attack paths, prioritize them, select controls, and define verification tests.
5. Recognize why **TLS, data encryption, and user authentication do not replace per-resource authorization checks**.

## 2. Core Concepts: How Does a Threat Differ from a Vulnerability?

| Concept | Meaning | Example in a Document Download API |
| --- | --- | --- |
| Asset | Something of value that needs protection | Contract content, file ownership permissions, decryption keys |
| Threat actor | A person or entity capable of causing harm, intentionally or accidentally | A legitimate user trying to read another organization's document; a compromised service account |
| Attack surface | Points where interaction with the system is possible | HTTPS endpoints, webhooks, job queues, KMS APIs, CI/CD pipelines |
| Threat | An event or action that can violate a security property | A user altering `documentId` to read a document they do not own |
| Vulnerability / weakness | A flaw that gives a threat a viable path to succeed | The API only checks login status and skips authorization on `documentId` |
| Control | A measure to prevent, detect, or reduce harm | Per-document and per-tenant authorization, token validation, auditing, quotas |
| Risk | Combination of likelihood and impact on protection goals | Customer document leak causing financial and legal damage |
| Residual risk | Risk remaining after controls are applied and verified | A compromised authorized account can still download permitted documents |

**Important distinction:** an attack idea does not prove the current system has a vulnerability; conversely, finding no bugs in one test does not prove the system is free of threats. A threat model documents *assumptions*, *scenarios*, and *verification evidence*, then updates as new information emerges.

A useful way to frame a scenario:

> "Who can introduce data or commands across which boundary, with what privileges, to alter which asset, and cause what harm? Where is the control, and how can that control be tested?"

## 3. Identifying Assets to Protect

Business data is not the only asset. List everything that **grants access to or decrypts data**. For each asset, record its owner, storage locations, authorized users, retention period, movement flows, and impact if leaked/modified/deleted/unavailable.

| Asset | Properties to Protect | Example Exposure or Modification Paths |
| --- | --- | --- |
| Plaintext of documents, personal data | Confidentiality, integrity, privacy | API responses, process memory, temporary files, logs, backups |
| Ciphertext and metadata | Integrity, availability, accurate owner binding | Object storage, object URLs, tenant metadata, nonces/IVs |
| Symmetric keys, private keys, KMS secrets, service passwords | Confidentiality and usage permissions; revocability/rotation | Environment variables, config files, source code, CI logs, IAM roles |
| Session tokens, refresh tokens, API keys | Confidentiality, expiration, permission scope | Headers, cookies, caches, error reports, observability tools |
| Identities, roles, policies, ACLs, tenant–object relationships | Integrity and authenticity | Client-supplied `ownerId` fields, authorization data in DB |
| Audit logs, timestamps, request IDs | Integrity, traceability, disclosure limits | Altered/deleted logs, logs containing tokens or plaintext |
| Services, quotas, backup data, infrastructure configs | Availability, recoverability | DDoS, deletion operations, misconfigurations, key/decryption failures |

Properties commonly evaluated:

- **Confidentiality:** unauthorized principals cannot read the content.
- **Integrity:** unauthorized modification is prevented or detected.
- **Availability:** authorized principals can use the service, even under reasonable failure conditions.
- **Authenticity:** identity or message origin is accurately verified.
- **Authorization:** a valid identity only performs granted actions on permitted resources.
- **Accountability:** critical activities are recorded sufficiently for investigation; logs alone do not automatically prove absolute non-repudiation.
- **Privacy:** limiting collection, inference, linking, retention, and sharing of personal data.

### Categorizing Assets by Lifecycle

A plaintext item can travel through `client -> HTTPS -> JVM heap -> DB -> backup -> log/monitoring`. Encrypting records in the DB is insufficient if an endpoint serves plaintext to the wrong user, keys sit alongside data under the same access permissions, or debug logs print sensitive requests/responses. Do not overlook data in memory, temporary files, snapshots, test-environment copies, and error messages.

For secret keys, document separately: **who can request encryption/decryption**, who can retrieve/export keys, IAM policies, where keys are generated/stored, rotation/revocation mechanisms, old key versions needed to read historical data, and contingency plans if a key is leaked or lost. Permission to call `Decrypt` on KMS is a powerful asset even if key bytes never leave KMS.

## 4. What Is a Trust Boundary?

A **trust boundary** is where data or commands pass between zones with different owners, authentication mechanisms, privilege levels, or trust assumptions. Boundaries often align with network connections, though **not necessarily**: two components on the same host, in the same VPC, or in the same JVM can still have different privileges and data sources.

Example of a Java system allowing users to download encrypted documents:

```text
[Browser / User]              (untrusted input)
            |
            | B1: HTTPS + session/token
            v
[Gateway / Java API]          (authenticates identity, enforces authorization)
       |                 \
       | B2: SQL/TLS      \ B3: KMS API/TLS, IAM role
       v                   v
[DB: metadata/ACL]      [KMS: key management and usage]
       |
       | object reference
       v
[Object storage: ciphertext]  (separate access permissions and policies)
```

Note: the diagram above is a **simplified logical diagram** and does not imply the DB directly accesses object storage; real deployments usually have a separate Java API -> object storage flow, which must also be drawn as a boundary. Where TLS terminates at a gateway/load balancer must be explicitly noted: if the gateway decrypts TLS, the hop from gateway to backend is a separate flow to evaluate.

At **every boundary crossing**, ask six questions:

1. Who is sending and who is receiving? Are service/user identities properly verified?
2. Which bytes are **untrusted data** (IDs, headers, JWTs, file contents, events, tenant info)?
3. Does the receiver exercise higher privileges, query a DB, call KMS, or write files based on that data?
4. Where are input validation, **authorization**, size/rate limits, replay protection, and integrity verification placed?
5. Which assets are affected if data crossing the boundary is leaked, altered, lost, or replayed?
6. When a control fails, are there audit signals and ways to contain damage propagation?

Commonly overlooked boundaries:

- **Client -> backend:** the client controls IDs, bodies, queries, file uploads; even for logged-in users, all client-sent fields remain untrusted.
- **Gateway -> service:** gateway authentication does not automatically mean the backend has authorized the action; the backend needs a verifiable auth contract and must avoid trusting identity headers from the Internet.
- **Service -> DB/cache/object storage:** service accounts often have broader privileges than end users; enforce tenant isolation, permission-scoped queries, least privilege, and connection protection.
- **Service -> KMS/HSM:** decryption permissions can turn a compromised server into a "decryption oracle"; scope permissions per key, condition, and purpose, and monitor for abuse.
- **Application -> webhook/partner/queue:** external data or events must validate origin, signature/MAC when designed, timestamps, nonce/idempotency, and schema; transport auth solves only part of the problem.
- **Build/CI -> production secrets:** artifacts, dependencies, and deployers can alter code running with production privileges.

**Principle:** "internal", "running in Kubernetes", "uses HTTPS", or "logged in" are not guarantees for every action. Trust must have explicit *scope*, *verification conditions*, and *time bounds*.

## 5. Process for Building a Threat Model

### Step 1 — Lock Scope and Assumptions

Record the feature name, business flow, actors (users, admins, services, third parties), environment, entry/exit points, data types, and what is **out of scope**. For example: "Examine `GET /api/documents/{id}` and decryption for download; exclude payment flows." Document testable assumptions, such as "the gateway validates JWTs and the backend only accepts connections from the gateway"; do not treat assumptions as facts until tested.

### Step 2 — Inventory Assets and Permissions

Use the table in Section 3 to describe the impact of violating each property. Separate **data owners**, **authorized viewers**, **executing machine accounts**, and **key administrators**; these identities are not identical.

### Step 3 — Draw Data Flow Diagrams (DFD) and Mark Boundaries

A minimal DFD needs **external entities**, **processes**, **data stores**, **data flows**, and **trust boundaries**. On arrows, note the transferred data, protocol, authentication mechanism, where encryption terminates, and where authorization decisions occur. Draw separate paths for writes, reads, deletes, backups, and key rotation if risk levels differ.

### Step 4 — Identify Threat Scenarios

Walk through each asset and each boundary crossing. Combine STRIDE (Section 6) with questions like: "What if the client changes the ID?", "What if a token is stolen?", "What if a service role is compromised?", "What if data/ciphertext is swapped?", "What if the same event is retried multiple times?", "What if KMS is unresponsive?". State **precondition -> action -> bypassed control -> consequence**, avoiding vague notes like "risk of hacker".

### Step 5 — Prioritize and Assign Controls

Estimate **likelihood** and **impact** in real context; consider exposure, required privileges, exploit difficulty, and existing controls. For example, on an internal 1–5 scale: likelihood 4 and impact 5 yields 20; this is merely a prioritization aid for discussion, **not a quantitative probability or industry standard**. Assign a risk owner, implementer, deadline, and status (mitigate/transfer/avoid/accept with justification).

### Step 6 — Verify, Document, and Update

For every control, write tests or observable criteria: cross-tenant requests rejected, forged tokens denied, IAM blocks unauthorized keys, logs contain no bearer tokens, rate limits prevent resource exhaustion. Store the model artifact, decisions, and residual risks alongside the design version. Update whenever adding endpoints, providers, auth mechanisms, storage locations, or changing key flows.

## 6. STRIDE: A Prompt to Avoid Missing Threat Categories

STRIDE has six categories. Apply them to **concrete** components and data paths; one component can face multiple categories, and one threat can span multiple categories.

| Category | Check Question | Scenario in the Document API | Typical Control |
| --- | --- | --- | --- |
| **S — Spoofing** | Who can impersonate another user/service? | Attacker sends a forged token or spoofs `X-User` header | Verify token signature, issuer, audience, expiration; enforce mTLS/identity between services; strip untrusted headers |
| **T — Tampering** | Who can alter data/commands unexpectedly? | Ciphertext/metadata modified, tenant ID swapped | Enforce authorization and integrity checks; AEAD for encryption; DB/object write controls |
| **R — Repudiation** | Can we trace who did what? | An authorized user who downloaded/deleted a document denies the action | Audit with verified actor, resource ID, timestamp; tamper-evident logs; limit sensitive data in logs |
| **I — Information Disclosure** | Who can read unauthorized info? | BOLA lets user download another tenant's document; tokens leak into logs | Object-level authorization, tenant isolation, TLS, proper encryption, log redaction |
| **D — Denial of Service** | Who can exhaust system resources? | Spamming decryption requests exhausts KMS/CPU quotas | Rate limits, quotas, timeouts, backpressure, resource limits, circuit breakers as needed |
| **E — Elevation of Privilege** | Can a user act beyond their role? | Sending `role=admin` in input or overly broad service account | Derive roles from trusted sources, server-side checks per action, least-privilege IAM, separation of duties |

STRIDE is a **prompting framework**, not a guarantee of catching all business-logic, privacy, or supply-chain attacks. For workflow abuse, add *abuse cases*; for multi-step attack paths, use *attack trees*; for privacy requirements, supplement with LINDDUN. Do not make filling all six rows the goal instead of uncovering real risks.

## 7. End-to-End Example: Tenant-Scoped Encrypted Document Download

**Problem:** A Java service stores files as ciphertext in object storage; the DB stores metadata including `documentId`, `tenantId`, `ownerId`, and the object reference; KMS protects keys. Users send `GET /api/documents/{id}` to download files. A valid user is **only permitted to view authorized documents within their own tenant**.

### 7.1 Valid Flow

1. Client calls the API over HTTPS with session/token credentials.
2. The authentication layer verifies identity evidence; the Java API receives a **verified principal**. If JWT is used, validate signature, allowed algorithms, issuer, audience, expiration, and required claims per protocol; decoding a JWT string into JSON does not authenticate it.
3. Server receives `id` from the URL **as client-controlled input**, fetching document metadata from a trusted store.
4. Policy checks **tenant**, **document permissions**, and **read action**. Never use client-claimed `ownerId` or `tenantId` for authorization decisions.
5. Only when policy permits does the service fetch ciphertext/decrypt via KMS under least privilege and return the content. Responses and logs obey data protection policies.

### 7.2 High-Priority Abuse Scenarios

| ID | Boundary & Scenario | Asset / Impact | Required Control | Verification Method |
| --- | --- | --- | --- | --- |
| T1 | B1: logged-in user changes `id=doc-a` to `id=doc-b` of another user/tenant (**BOLA**) | Document confidentiality leaked | Per-object, per-tenant, per-action policy on backend; deny by default | Test same-tenant different-owner, cross-tenant, non-existent doc; no plaintext returned |
| T2 | B1: forged, expired, or wrong-audience token used | Impersonation, unauthorized access | Standard token validation, never trust arbitrary client headers | Send token with missing/bad signature, wrong issuer/audience, expired; verify rejection |
| T3 | B2/B3: compromised service account or IAM role calls decrypt broadly | Mass plaintext leak despite encrypted storage | Least-privilege IAM/KMS policies, separation of duties, key scoping, audit & alerts | Attempt decrypt with unauthorized role; check KMS audit logs |
| T4 | API -> storage: ciphertext modified or tenant/object metadata swapped | Wrong data returned, integrity loss | Write controls, binding ciphertext to context, AEAD when required by design | Flip bits in ciphertext/AAD or swap object links; decryption must fail or be blocked |
| T5 | B1/B3: download/decrypt spam, oversized files | API outage or KMS quota exhaustion | Rate limits, size caps, timeouts, quotas, backpressure | Bounded load tests, measure errors and impact on legitimate users |
| T6 | API -> log/observability: logging tokens, plaintext, URLs with secrets | Data leakage via auxiliary systems | Redaction, never log credentials/plaintext, log access control & retention | Scan logs across success/error paths; no bearer tokens or plaintext present |

**Root-cause analysis of T1:**

- **Precondition:** Alice has a valid account and knows/guesses Bob's document ID. The ID is an input parameter; even a random UUID can leak via logs, links, or other APIs.
- **Boundary crossing:** client sends `id`; the API uses that ID to fetch metadata and decrypt using the server's privileges.
- **Likely design flaw:** the API checks "is logged in" then calls `decrypt(documentId)`, skipping whether Alice has permission for this document.
- **Consequence:** Bob's document is disclosed. **TLS does not stop it** because the request arrives over a valid channel; **storage encryption does not stop it** because the server itself holds decrypt permission.
- **Fixing at the right layer:** the backend evaluates authorization against the verified principal and trusted metadata/policy **before any plaintext retrieval**; deny by default; test across users and tenants.

This falls under **Broken Object Level Authorization (API1:2023)** in the OWASP API Security Top 10. Switching sequential IDs to UUIDs or merely hiding the download button in the UI does not fix the root cause.

### 7.3 Cryptographic and Key Management Boundaries

Cryptography only makes sense when it explicitly answers **which asset is protected against which threat actor**:

- **TLS** protects the channel up to the TLS termination point and authenticates endpoints per configuration; TLS does not determine whether a user is allowed to read a document. When TLS terminates at a proxy, map the proxy -> service path separately.
- **Data-at-rest encryption** helps protect plaintext confidentiality if storage/backups are read without authorization. If the process holding decryption permission is compromised, the threat shifts to key usage permissions and plaintext output paths.
- **Authenticated encryption** like AES-GCM can detect ciphertext/AAD tampering when used properly; never reuse a nonce/IV with the same key, and store/supply the exact AAD during decryption. AEAD does not perform authorization checks.
- **Digital signatures/MACs** help verify origin and integrity assuming keys/certificates are managed properly; they do not encrypt content for confidentiality.
- **Password hashing** differs from reversible encryption: use a password hashing mechanism with appropriate salt and cost (e.g., Argon2id per policy) rather than storing passwords with AES or plain SHA-256.
- **Keys and secrets** require separate storage, access control, rotation, and auditing. Avoid embedding keys in source code, build images, stack traces, or logs; restrict decrypt permissions even more strictly than ciphertext read permissions.

One control may mitigate one threat while leaving another intact. A good threat model states **conditions for the control to hold**, where to verify it, and residual risk.

## 8. Java 17 Example: Checking Authorization Before Touching Plaintext

The snippet below illustrates only **a simple owner-and-tenant authorization rule**. It does not connect to networks/DB/KMS, validate tokens, or perform real encryption. In a real application, `Principal` must come from a **verified authentication context**, and `Document` must come from a trusted metadata source.

Save as `TrustBoundaryDemo.java`:

```java
import java.util.Objects;

public class TrustBoundaryDemo {
    record Principal(String userId, String tenantId) {}
    record Document(String id, String ownerId, String tenantId) {}

    static boolean canRead(Principal actor, Document document) {
        if (actor == null || document == null
                || actor.userId() == null || actor.userId().isBlank()
                || actor.tenantId() == null || actor.tenantId().isBlank()) {
            return false;
        }

        return Objects.equals(actor.tenantId(), document.tenantId())
                && Objects.equals(actor.userId(), document.ownerId());
    }

    public static void main(String[] args) {
        Principal alice = new Principal("alice", "tenant-a");
        System.out.println(canRead(alice,
                new Document("doc-1", "alice", "tenant-a")));
        System.out.println(canRead(alice,
                new Document("doc-2", "bob", "tenant-a")));
        System.out.println(canRead(alice,
                new Document("doc-3", "alice", "tenant-b")));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac TrustBoundaryDemo.java
java TrustBoundaryDemo
```

Exact stdout output:

```text
true
false
false
```

The first line allows Alice to read her own document. The second line denies Bob's document in the same tenant; the third line denies a document with the same owner ID in a different tenant. **Comparing only user ID while ignoring tenant is incomplete**, just as comparing only tenant without per-document authorization is incomplete.

In a real system, replace `canRead` with the appropriate policy (owner, controlled sharing, roles, time conditions, action permissions). The function should return **deny** when metadata is missing or identity is unverified. Order matters: **authenticate -> load trusted metadata -> authorize resource -> fetch/decrypt -> return data**. Whether to return 403/404 and what to log must follow a policy that avoids leaking resource existence and never turns error messages into a leak channel.

### Turning the Model into Tests

For a real API, include at least these cases:

1. Authorized user, matching tenant, matching document: download succeeds with exact content.
2. Different user in the same tenant without permission: denied; service does not call KMS/decrypt.
3. User with identical name/ID in another tenant: denied; metadata queries always bind tenant per policy.
4. Token with invalid signature, wrong audience, expired, or missing: fails before content retrieval.
5. Request carrying forged `ownerId`, `tenantId`, or `role` in body/header: does not alter authorization decision.
6. Service role restricted to a specific key: decrypt request with an out-of-scope key is denied and audited.
7. Tampered ciphertext/AAD, error logs, retries, or quota-exceeding traffic: handled safely without returning corrupted plaintext or leaking secrets.

Include unit policy tests, integration tests across API/DB/KMS boundaries (in a safe test environment), and real IAM configuration checks. Passing tests do not replace reviewing assumptions and architectural changes.

## 9. Recording Decisions, Priorities, and Residual Risk

A minimal threat record should include:

| Field | Sample Content |
| --- | --- |
| `ID` / scope | `T1` — `GET /api/documents/{id}` |
| Asset, goal | Contract plaintext; only owner/shared users in the right tenant can read |
| Actor and precondition | Valid user can submit another document's ID |
| Boundary/attack path | Client -> Java API -> metadata -> KMS/decrypt |
| Consequence | Unauthorized disclosure of document content |
| Pre-control rating | Likelihood 4/5 x Impact 5/5 = 20/25 (internal example) |
| Control and location | Policy checking tenant, action, and object permission in backend, before decrypt |
| Evidence | Cross-tenant/cross-user tests, denied request audits, no KMS call |
| Owner, status | API owning team; implementing/verified; review date |
| Residual risk | A stolen valid token can still access permitted documents; consider session controls, MFA, and anomaly detection |

Do not add or subtract scores mechanically: numeric scales do not fully capture exposure, legal impact, attacker motivation, or correlations across threats. If risk is accepted, record the accountable owner, rationale, review deadline, and re-evaluation criteria.

**When to update the model?** Whenever adding data flows (webhooks, exports, analytics), sensitive data, new tenants, IAM permission changes, authentication methods, crypto libraries, TLS termination points, object sharing logic, or backup/restore steps. The model is a living document tied to design, code review, and testing.

## 10. Common Thinking Traps

- **"We use HTTPS, so it's secure."** HTTPS protects the channel up to TLS termination; requests from low-privilege users can still leak data if authorization is missing.
- **"The DB is encrypted, so even a compromised admin/service can't read it."** Check who holds decrypt permission and where plaintext appears. Encryption does not replace access control and privilege separation.
- **"The JWT is verified, so all user-sent object IDs are trustworthy."** A token authenticates the caller; every object/action needs independent authorization.
- **"UUIDs are random enough, so no policy is needed."** Hard-to-guess IDs are not a security boundary: IDs can leak or be shared unintentionally.
- **"Inside the same private network, there are no boundaries."** Services/roles have different privileges and data paths; compromised accounts still cause harm.
- **"Filling all six STRIDE boxes means we're done."** STRIDE is only an idea-generation checklist; you need concrete scenarios, impacts, owners, controls, and verification.
- **"Threat = an existing bug."** A threat is what could go wrong; separate assumptions, verified weaknesses, and unhandled risks.
- **"Log as much as possible."** Logs can turn into sensitive assets, especially if they contain plaintext, tokens, keys, or personal data.
- **"Authenticated encryption automatically ensures the data belongs to the right user."** AEAD protects integrity within the chosen key/AAD context; whether a user has rights to an object is decided by authorization.

## 11. Practice Exercise

A Spring/Java service receives webhooks from a partner, writes events to a queue, a worker updates payment status in a DB, and an API lets users view history. Create a one-page threat model:

1. List at least six assets: payment status/reference, user identity, webhook verification secret, message ID, DB update privilege, audit logs.
2. Draw boundaries **partner -> webhook**, **API -> queue**, **worker -> DB**, **user -> read API**, and mark who authenticates whom.
3. Write at least five scenarios: forged webhook, replayed valid webhook, modified tenant/order ID in payload, duplicate queue consumption causing wrong updates, user reading another user's transactions, or queue overload.
4. For each scenario, document precondition, affected asset, expected control, and one proving test. For instance, anti-replay may require origin authentication, bounded timestamps **and** event-ID idempotency on the consumer side; HTTPS alone is not enough.
5. Record one unverified assumption (e.g., "the partner supports webhook signing") and one residual risk after controls.

**Completion criteria:** someone reading the artifact can pinpoint every boundary crossing, trace the path from untrusted data to high privilege, see where it is checked, and know how to verify the outcome — without assuming "this service is probably safe."

## References

- [OWASP — Threat Modeling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html): modeling process, DFDs, STRIDE, controls, and reviews.
- [OWASP — API1:2023 Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/): examples of object-level authorization flaws.
- [OWASP — Threat Modeling in DevSecOps Guideline](https://owasp.github.io/DevSecOpsGuideline/2-Process/2-1-Design/2-1-1-Threat-modeling/): DFD, trust boundary, and STRIDE examples.
