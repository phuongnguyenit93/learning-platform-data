# Proxy Granting Ticket Storage, Lifetimes, and Secret Protection in CAS Proxy

> **Topic:** Spring Security – federation · **Group:** CAS Proxy. This lesson explains how a CAS-enabled application receives and stores a **Proxy Granting Ticket (PGT)**, binds the PGT to the **Service Ticket (ST)** or **Proxy Ticket (PT)** validation result via **PGTIOU**, uses the PGT to request **fresh Proxy Tickets** for backends, manages expiration/revocation, and protects the PGT as a **reusable delegation secret**. The Spring Security/Apereo CAS integration snippets are fragments requiring real dependency config, a CAS Server, TLS, and a service registry; the standalone program at the end uses Java 17+.

## 1. Why Is a PGT Store Needed?

A web application A (a CAS service) has logged a user in via CAS. It needs to call backend B, also CAS-protected, **on behalf of the user**. Backend B never sees the browser, so it lacks the user's TGC/TGT; having A pass raw cookies or the user's password to B violates trust boundaries.

**CAS Proxy Authentication** solves this via the sequence:

```text
Browser/user               Service A                CAS Server             Backend B
     |                         |                         |                      |
     | login A                 |                         |                      |
     |------------------------>|                         |                      |
     |<--------- CAS /login?service=A ------------------>|                      |
     |<--------- redirect ?ticket=ST-A ------------------|                      |
     |------------------------>|                         |                      |
     |                         | /serviceValidate         |                      |
     |                         | ST-A + service=A         |                      |
     |                         | pgtUrl=A/proxyreceptor   |                      |
     |                         |------------------------>|                      |
     |                         |<--- callback pgtId + pgtIou                     |
     |                         |    CAS -> A/proxyreceptor|                      |
     |                         |<-- XML success + pgtIou -|                      |
     |                         | match IOU, bind PGT      |                      |
     |                         | to validated user       |                      |
     |                         |                         |                      |
     |                         | /proxy?pgt=PGT&targetService=B                  |
     |                         |------------------------>|                      |
     |                         |<------ PT-B ------------|                      |
     |                         |----------------------------------------------->|
     |                         |                        PT-B (service=B)        |
     |                         |                         |<---- /proxyValidate --|
     |                         |                         |---- CAS result ----->|
     |                         |<------------------------------- data -----------|
```

Core distinctions:

- **ST**: issued on browser login to one service; **short-lived and valid for a single validation**.
- **PGT**: secret issued to A during ticket validation, usable **multiple times** to request PTs; must be controlled like a delegation credential.
- **PT**: ticket scoped to **one specific backend `targetService`**, validated by B, normally **single-use** like an ST.
- **PGTIOU**: string linking the callback message carrying the PGT with the validation XML result containing the same IOU; **never used to call `/proxy`** and is not a PGT.

Because a PGT can be reused throughout its validity window, a leaked PGT carries higher risk than a single-use ST. This lesson focuses on the **PGT lifecycle and PGT storage on service A**, rather than dumping all STs/PTs into one table.

### Learning Objectives

After this lesson, you will:

1. Diagram the exact CAS `/serviceValidate` → `pgtUrl` callback → `PGTIOU` → PGT store → `/proxy` → `/proxyValidate` flow.
2. Distinguish **PGT, PGTIOU, ST, PT, TGT, and TGC**, especially “reusable PGT” vs. “single-use ST/PT.”
3. Design a PGT store with lookup keys, **CAS server / tenant / user / session / service A bindings**, state, and TTLs.
4. Separate a **temporary callback store** from an **active PGT vault** to prevent using PGTs not yet bound to a trusted validation result.
5. Define expiration across **CAS Server policy + app storage policy + session/logout/revocation**, rather than hardcoding a TTL assuming CAS will honor it forever.
6. Protect PGTs in RAM/Redis/DB/HSM-KMS, in transit/callbacks/logs/backups, and during key rotation.
7. Use Spring Security CAS's `ProxyGrantingTicketStorage`, `Cas20ProxyTicketValidator`, and `CasAuthenticationFilter` in their exact roles, distinguishing fragments from runnable apps.
8. Know when to purge a PGT, request a new PGT, validate the CAS proxy chain, and avoid enabling `acceptAnyProxy=true` lightly.
9. Run a Java 17 demo simulating **PGTIOU binding, AES-GCM storage, TTLs, session isolation, and revocation** with deterministic stdout.

## 2. Tickets and Secrets Are Not Uniform

| Artifact | Issued / Held By | Usage | One-Time? | Where Stored? |
| --- | --- | --- | --- | --- |
| **TGT** — Ticket Granting Ticket | CAS Server ticket registry | Underpins user SSO session and issues tickets | Not per ST semantics | CAS Server; never given to service A |
| **TGC** — Ticket Granting Cookie | Browser ↔ CAS origin | CAS locates TGT/SSO session | Cookie per CAS policy | Browser cookie jar scoped to CAS |
| **ST** — Service Ticket | CAS Server → browser → A | A verifies CAS login | **Yes**, one validation attempt | Not persisted long-term in app |
| **PGT** — Proxy Granting Ticket | CAS Server → A's HTTPS callback | A requests multiple PTs for backends | **No**; reusable within policy/time window | A's **protected PGT vault** |
| **PGTIOU** | CAS Server → callback and validation XML | Correlates PGT callback with ST/PT validation result | **Single-use correlation** in app | Temporary IOU map with very short TTL |
| **PT** — Proxy Ticket | CAS Server → A → backend B | B validates delegated call to B | **Yes**, short-lived / one validation | Sent only to target B; never cached for general reuse |
| **Local `HttpSession`** | Service A backend + browser cookie | Holds local authenticated principal | Session lifecycle | Session store; **separate from PGT vault** |

A PGT is neither a “global password” nor a standard OAuth refresh token, yet in risk terms it **resembles a longer-lived credential used to mint short-lived credentials**. Anyone capturing a PGT can try asking CAS for PTs targeting whatever services PGT and service authorization permit until it expires or is revoked.

### 2.1. How Do PGT and CAS TGT Relate?

CAS issues a PGT in the context of a CAS-authenticated client with a valid ticket validation; CAS manages its relationship to the SSO grant/client. Under the CAS protocol, **a PGT must expire when the client whose authentication is proxied logs out of CAS**.

This does **not** mean the app can read the TGT/TGC or is guaranteed to receive a successful CAS logout callback. Distinguish:

- The CAS Server is responsible for **rejecting expired/revoked PGTs**.
- Service A is responsible for **not retaining or attempting to use a PGT** after session logout, policy expiry, tenant unlinking, credential compromise, or receiving a revocation signal.
- If a CAS SLO event fails to arrive due to a network outage, service A might still hold encrypted PGT bytes until local TTL, **yet CAS must still reject the server-revoked PGT**. Never treat a local cache hit as proof that CAS still accepts it.
- When a CAS Server restart or ticket registry change drops a PGT, A must fail closed and re-run the approved flow—never reactivating an old PGT.

### 2.2. A PGT Is Not a PT

A uses the PGT to call:

```http
GET /cas/proxy?pgt=PGT-FAKE&targetService=https%3A%2F%2Fbackend.example.org%2Fapi HTTP/1.1
Host: sso.example.org
```

This is a **mock HTTP transcript** illustrating CAS protocol parameters; **never place real PGTs in examples, public docs, or access logs**. CAS verifies the PGT is still valid and A is permitted to proxy to `targetService`, then issues a `PT`. Backend B sends the PT to CAS `/proxyValidate` before trusting the username and proxy chain.

One PGT can request PT #1, #2, #3… while valid, yet **each PT must be bound to its exact `targetService` and used once**, never reusing B's PT at C or replaying across calls. When B is a stateless REST API needing multiple calls, A usually requests a **fresh PT per authentication** or uses a contract-governed protocol cache—never stretching a PT into an arbitrary bearer token.

## 3. Detailed Flow for Receiving Real PGT and PGTIOU

Assume:

```text
CAS Server:      https://sso.example.org/cas
Service A:       https://portal.example.org/login/cas
PGT callback A:  https://portal.example.org/login/cas/proxyreceptor
Backend B:       https://backend.example.org/api
```

All addresses are **illustrative** and require real public HTTPS, service registry entries, and valid certificates in deployment.

### 3.1. Step 1: A Validates ST and Requests a PGT

After the browser delivers `ST-A` to `/login/cas`, A calls CAS back-channel:

```http
GET /cas/serviceValidate?service=https%3A%2F%2Fportal.example.org%2Flogin%2Fcas&ticket=ST-A&pgtUrl=https%3A%2F%2Fportal.example.org%2Flogin%2Fcas%2Fproxyreceptor HTTP/1.1
Host: sso.example.org
```

`service` must match the service identity when the ST was issued. `pgtUrl` is A's registered and CAS-trusted **public callback URL for receiving the PGT**, not backend B's URL.

**Never swap** `pgtUrl` and `targetService`: `pgtUrl` belongs to A to receive the secret; `targetService` belongs to B to request a PT afterward.

### 3.2. Step 2: CAS Calls Back `pgtUrl` Over HTTPS

Once PGT issuance conditions pass, CAS connects over HTTPS to A's `pgtUrl` and passes:

```http
GET /login/cas/proxyreceptor?pgtId=PGT-SECRET-EXAMPLE&pgtIou=PGTIOU-EXAMPLE HTTP/1.1
Host: portal.example.org
```

This is a **server-to-server CAS → A callback**, not a browser user navigating to the proxy receptor. Both `pgtId` and `pgtIou` appear in URL query strings per protocol, so **redact them at ingress, reverse proxies, access logs, WAFs, and APM**.

CAS checks A's TLS endpoint/certificate per policy. The CAS protocol requires the callback to return HTTP 200 for successful PGT flow; 3xx redirects may be handled by CAS servers depending on spec/implementation, yet production should expose a **stable non-redirecting URL** returning 200 after persisting, avoiding PGT leaks in redirects/logs.

On A, the proxy receptor **must not yet bind the PGT to any arbitrary username**. It should only stage a short-lived pending record keyed by IOU, guarding against duplicates and enforcing network/trust requirements.

### 3.3. Step 3: CAS Returns the ST Validation Result with PGTIOU

CAS returns XML in the response to backend A's `/serviceValidate` call:

```xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>alice</cas:user>
    <cas:proxyGrantingTicket>PGTIOU-EXAMPLE</cas:proxyGrantingTicket>
  </cas:authenticationSuccess>
</cas:serviceResponse>
```

**Easy mistake:** the contents of `cas:proxyGrantingTicket` are **PGTIOU**, **not the secret PGT**. The real PGT string was sent directly via `pgtId` in the callback.

Only after the CAS validation result is genuinely `authenticationSuccess` for a **valid ST/PT, service ID, and trusted CAS Server** may A use the XML's PGTIOU to look up the pending PGT and **bind the PGT to the authenticated principal/session/tenant**. If validation fails, no valid PGTIOU is present, or IOU lookup fails, **grant no proxy capability**.

### 3.4. Step 4: Correlating PGTIOU

```text
CAS->A callback                    A->CAS validation response
pgtIou = PGTIOU-123                cas:proxyGrantingTicket = PGTIOU-123
pgtId  = PGT-SECRET-456            cas:user = alice (validated)
        |                                      |
        +----------- same IOU -----------------+
                         |
               validate provenance and state
                         |
               bind PGT-SECRET-456 to
               CAS origin + tenant + alice + local session
                         |
                    active PGT vault
```

**Never** accept a callback as a login token, and never attach `pgtId` to a user merely because someone sent `?pgtIou=...`. An attacker can send forged HTTP requests to a public proxy receptor. PGTIOU carries random entropy and is confirmed by the **CAS back-channel validation response**, preventing blind trust in a bare callback.

### 3.5. Step 5: Using the PGT to Obtain a PT

When A needs to call B:

1. A resolves the **current user/session** from the local authenticated `SecurityContext`/session, never from a browser query like `subject=alice`.
2. Verifies user/tenant policy, confirms backend B is in **allowed `targetServices`**, and verifies the app session is not logged out or expired.
3. Queries the active vault by scoped key; decrypts the PGT into memory briefly without logging it.
4. A calls CAS `/proxy?pgt=PGT...&targetService=B` over **certificate/hostname-verified HTTPS** with redacted logs.
5. CAS issues a PT if the PGT is still valid and service policy allows.
6. A sends the PT **solely to B**; B validates via `/proxyValidate` and enforces proxy chain and authorization checks before processing.
7. If `/proxy` reports the PGT invalid/expired, A **deletes the active entry**, never retrying endlessly with the same PGT or downgrading to an old service ticket.

**Safety:** A must never accept PGTs from browser requests or expose PGTs in REST responses to the frontend. PGTs belong strictly in a server-side vault/credential store used by backend A exclusively on the HTTPS back-channel.

## 4. What Must the PGT Store Hold?

A secure design typically uses **two record tiers**:

1. **Pending PGTIOU store:** very short-lived records from the CAS callback before XML validation confirms the user.
2. **Active PGT vault:** PGT records already bound to an authentication/user/session and used to request PTs when needed.

### 4.1. Pending Store: Stage Only, Never Use Directly

| Field | Example | Purpose |
| --- | --- | --- |
| `pgtIouLookupKey` | HMAC/digest of `PGTIOU-...` | Locates IOU/PGT pair; avoids logging raw IOUs |
| `encryptedPgtId` | AES-GCM ciphertext | Keeps the PGT secret inside cache |
| `receivedAt` | UTC instant | Tracks callback timing |
| `expiresAt` | `receivedAt` + short pending TTL | Prevents orphan callbacks from retaining PGTs |
| `casOriginHint` | Trusted CAS connector identity if available | Aids scoping/diagnostics; **never proves caller alone** |
| `state` | `PENDING` | Cannot yet be used to request PTs |
| `nonce/version` | Crypto metadata | Decryption and key rotation |

**Pending callbacks do not know the username reliably**, because the user is confirmed in the **validation response**. Never create an active mapping for `alice` from an external query parameter.

### 4.2. Active Vault: Bound Credential

An active record may contain:

| Attribute | Meaning |
| --- | --- |
| `tenantId` / `registrationId` | Data and CAS integration boundary |
| `casServerId` | Approved CAS Server issuer/base URL, never browser-supplied |
| `serviceId` | CAS service A that received the ST/PT; prevents cross-service misuse |
| `localSessionKey` | Opaque authenticated session reference or secure identity context |
| `subjectKey` | Username/subject post CAS validation, namespaced by CAS/tenant |
| `pgtCiphertext` | Encrypted PGT; **never stored in plaintext** |
| `encryptionKeyId` | KMS/secret key version used for decryption |
| `issued/linkedAt` | Timestamp when A linked the validation result to the PGT |
| `expiresAt` | **Local upper bound** on usage, never exceeding policy |
| `status` | `ACTIVE` / `EXPIRED` / `REVOKED` / `ROTATING` |
| `sourceIouProofId` | Correlation record ID containing no raw secret |
| `lastUsedAt`, `lastProxyTarget` | Safe telemetry with allowlisted target ID |

**The lookup key must never be just username/email.** One user may hold two browser sessions; two tenants may have users sharing a NameID; one CAS Server may serve multiple services. Looking up by bare `username` can return the wrong context's PGT and cause cross-user or cross-tenant delegation.

### 4.3. Illustrative Vault Schema

```sql
-- STORAGE MODEL, not complete production DDL.
CREATE TABLE cas_pgt_vault (
    tenant_id           VARCHAR(128) NOT NULL,
    cas_server_id       VARCHAR(256) NOT NULL,
    service_id          VARCHAR(256) NOT NULL,
    session_key_hash    VARCHAR(128) NOT NULL,
    subject_key_hash    VARCHAR(128) NOT NULL,
    ciphertext          BLOB NOT NULL,
    nonce               BLOB NOT NULL,
    key_version         VARCHAR(64) NOT NULL,
    linked_at           TIMESTAMP NOT NULL,
    expires_at          TIMESTAMP NOT NULL,
    status              VARCHAR(16) NOT NULL,
    PRIMARY KEY (tenant_id, cas_server_id,
                 service_id, session_key_hash)
);
```

A real schema needs indexing/uniqueness/TTL jobs, transaction isolation, encryption AAD, retention, HMAC lookup keys, access policies, and auditing. A plain hash of a username does not resist dictionary attacks; for PII in lookup keys, use a keyed HMAC or governed pseudonymous ID. `ciphertext` is not “safe if the database user also has key-read permissions.”

### 4.4. Scoped Lookup Keys Instead of Bare IOU

The pending stage uses `PGTIOU` as a correlation key because the callback and XML validation response meet there. The active stage must use an **authenticated scope**; the IOU must not remain an open access key to the PT-issuing API.

One key construction:

```text
PENDING KEY:
  HMAC(k_lookup, casServerId || pgtIou)
  (short-lived, one-time bind)

ACTIVE KEY:
  tenantId || casServerId || serviceId || authenticatedSessionKey
  + store subject identity as validated attribute
  (never derive from untrusted request parameters)
```

In multi-CAS-Server environments, identical usernames or tenants do not imply shared trust. If a ticket/request belongs to CAS A, CAS B's vault **must never** return PGT A.

## 5. Lifetimes: Four Clocks That Cannot Be Merged

### 5.1. Critical TTL Types

| Component | Controlled By | Purpose | Behavior on Expiration |
| --- | --- | --- | --- |
| ST/PT validity | CAS Server policy/protocol | Short-lived / single-use tickets | Validation rejects; never replay |
| **PGT server expiration** | CAS Server PGT policy, TGT/session lifecycle | How long CAS accepts the PGT to mint PTs | `/proxy` rejects |
| **Pending IOU TTL** | Application A | Window for callback and validation result to correlate | Purge pending PGT if unmatched |
| **Active vault TTL** | Application A security/storage policy | Avoid keeping PGTs locally too long | Stop decrypting/using; delete entry |
| Local `HttpSession` expiry | Service A session manager | Lifetime of authenticated user session on A | Delete session-bound PGT if policy requires |
| CAS SSO logout/expiry | CAS Server | Terminates associated SSO/delegation rights | Server PGT must expire when user logs out of CAS |

**Never hardcode** “PGT lives 8 hours” as a protocol guarantee. The CAS Protocol says a PGT **MUST expire on CAS logout**, while absolute/idle timeouts are determined by **Apereo CAS version and deployed policy**. Clients typically receive no exact `expiresAt` in CAS 2.0 validation XML, so it cannot be inferred from `pgtIou` or `pgtId`.

### 5.2. Effective Expiration Policy

Conceptually:

\[
T_{\text{effective}}=\min(T_{\text{local-limit}}, T_{\text{CAS-PGT-expiry}}, T_{\text{session-expiry}}, T_{\text{revocation}})
\]

Where:

- `T_local-limit`: upper bound set by A, such as business session policy or maximum PGT retention.
- `T_CAS-PGT-expiry`: if CAS provides a trustworthy expiry, use it; otherwise **never assume** a large number represents server TTL.
- `T_session-expiry`: if the PGT is tied to an authenticated session, logout/timeout immediately halts usage.
- `T_revocation`: CAS logout, user unlinking/tenant revocation, suspected leak, or compromised encryption key → close immediately without waiting for TTL.

Whenever the CAS Server rejects a PGT, the client must delete/invalidate its local entry even if local `expiresAt` has not elapsed. **Local TTL is solely a storage/usage upper bound, never proof the PGT remains valid at CAS.**

### 5.3. Pending TTL Must Be Very Short

The PGT callback may arrive **before** the validator parses the XML response, or vice versa depending on scheduling. Therefore:

- The pending store waits for correlation within a small window sized to real request/response timings.
- Asynchronous callback/validation designs should use bounded storage read retries **without re-validating the ST**; STs have single-use semantics.
- Upon timeout, delete the encrypted pending PGT and fail closed; never fabricate proxy access for the user.
- Duplicate `pgtIou` arrivals must be rejected or handled idempotently **per an explicit contract**—never overwrite a valid PGT with an attacker-supplied value.
- If the CAS validator reports failure or omits `cas:proxyGrantingTicket`, clean up any related pending records rather than grabbing “the newest PGT.”

Never use an unbounded in-memory map for orphaned callbacks; an attacker could exhaust heap memory with fake PGTIOUs. Enforce size/rate limits, expiry deletion, ingress filters, and monitoring.

### 5.4. Illustrative Annotated TTL Config

```yaml
# Illustrative application policy ONLY, NOT official
# Spring Security CAS configuration properties.
cas-proxy-vault:
  pending-correlation-ttl: PT30S
  active-local-upper-bound: PT20M
  cleanup-interval: PT1M
  max-pending-items: 10000
  delete-on-local-logout: true
  delete-on-cas-slo: true
  fail-closed-on-cas-rejection: true
```

Values like `PT30S`, `PT20M`, `PT1M`, and `10000` merely illustrate `Duration` syntax, **not fixed recommendations for every system**. Measure actual callback latency, CAS PGT expiration, session policy, SLAs, scale, and compliance. If CAS PGT policy is shorter than a 20-minute local bound, CAS will still reject after server expiry.

### 5.5. CAS Ticket Policy Is Release-Dependent

Apereo CAS configures **Proxy-Granting Ticket expiration policies** by version. Never copy property names from “development” docs into production releases unverified. Check your exact **CAS server version**, config catalog, and run live tests covering CAS logout, idle/max lifetimes, clock skew, ticket-registry eviction, and cluster failover.

Never stretch the CAS PGT timeout to mask a vault lookup, proxy callback, or session mapping bug. Increasing TTL widens the exposure window if a PGT leaks.

## 6. Revoking PGTs: Expiration vs. Logout and Incidents

### 6.1. Events That Must Delete or Invalidate

| Event | Service A Side | CAS Server Side |
| --- | --- | --- |
| User logs out locally on A | **Delete active entry** bound to session/user per policy | CAS TGT may remain; PGT may remain server-side |
| User logs out of CAS | Delete on SLO/revocation signal or local TTL; stop using | **PGT must expire** per protocol |
| User session on A times out | Do not use PGT from expired session | CAS may not yet be logged out |
| User switches account / unlinks CAS | Revoke old scope; never reuse PGT | May require server-side revocation per API/policy |
| Tenant disabled / backend access revoked | Delete all tenant-scoped PGTs and block `/proxy` | May update service proxy authorization |
| Suspected PGT compromise | Delete/blacklist, call CAS revoke/logout if supported; incident response | Server-side revocation is critical |
| Vault encryption key rotation | Re-encrypt or drop vault/require re-login per policy | Does **not** rotate CAS PGT automatically |
| CAS Server returns invalid PGT | Drop local entry, signal reauth/regrant appropriately | Old ticket rejected |

**A `DELETE` command in A's Redis does not revoke the PGT at the CAS Server.** If a PGT is genuinely compromised, act at the CAS Server (expire/revoke TGT/PGT, logout policies) and check issued PTs as server/backend capabilities permit; deleting client ciphertext merely stops A from using it.

### 6.2. CAS SLO Delivery Must Not Be Assumed 100% Reliable

The CAS Server can send logout notifications to registered services. Yet networks or apps can fail, callbacks can be blocked, or session stores may lack state. Therefore:

- CAS Server enforces PGT expiry/revocation independently.
- Service A maintains local TTLs, logout hooks, periodic cleanup, and handles `/proxy` rejections.
- If an SLO notification is missed, the local vault still must not use the PGT past its configured local session lifetime.
- Logout/revocation events must be idempotent and never need to carry raw PGT secrets in event payloads.

### 6.3. Never “Refresh a PGT” by Minting a Fake ST

A PGT is not a JWT that renews itself by re-signing. When a PGT expires, obtaining a new PGT requires going through a valid CAS authentication/ticket validation flow (leveraging existing CAS SSO if policy allows), producing a new callback and IOU. Never resubmit an old ST, forge `PGT-...`, or clone PGT values long-term.

## 7. Protecting PGT Secrets in Storage

### 7.1. Minimum Principles

- **Zero persistent plaintext PGTs** in databases/Redis, logs, metrics, browser storage, session cookies, source code, exception messages, or CI artifacts.
- Encrypt at rest using **AEAD** (e.g., AES-256-GCM) with keys from KMS/HSM/secrets manager, rotation, and clear ACLs.
- Appropriate TLS/mTLS for traffic between app ↔ store, app ↔ CAS, and CAS ↔ `pgtUrl`.
- Vault access **restricted solely to the backend responsible for requesting PTs**—never the frontend, service B, or general batch jobs.
- Data model isolates tenant/CAS/user/session; use encryption AAD to bind ciphertext to scope, preventing copying ciphertext from tenant A to B.
- Plaintext PGTs retrieved from storage stay in heap memory only as long as needed to call CAS `/proxy`; prohibit unencrypted heap/core dumps in ordinary environments.
- Never share secrets or root encryption keys across tenants when blast radius or compliance demands isolation.

### 7.2. Why Are Base64 and Hashing Insufficient?

Base64 only encodes bytes; it provides no confidentiality. A one-way hash of a PGT can help **match** or safely audit if keyed, yet when A calls `/proxy?pgt=...`, A must recover the plaintext PGT. Therefore **you cannot simply hash the PGT and expect `/proxy` to work**; use reversible encryption in the vault, or isolate CAS calls inside a privileged credential broker (so the app itself never holds direct decrypt privileges).

### 7.3. Recommended Encryption Model

```text
App receives PGT over HTTPS callback (brief plaintext)
                |
                v
Encrypt with AEAD
  key from KMS / envelope encryption
  nonce unique per key
  AAD = tenant + CAS server + service + local session + subject
                |
                v
Store nonce + ciphertext + authTag + keyVersion + expiresAt
                |
                v
For authorized backend call:
  verify session / scope / targetService / not expired
  decrypt briefly -> CAS /proxy over verified HTTPS
  scrub buffers when feasible; never log PGT
```

In AES-GCM, never **reuse a nonce with the same key**; use strong unique random nonces (typically 96-bit) or a governed nonce scheme. Every encryption operation should bind AAD from **immutable trusted identities**, never taking tenant or subject from browser forms.

**Key rotation differs from PGT rotation:** rotating the KMS key version and re-encrypting ciphertext does not mint a new PGT at CAS; it only updates how A stores it. On suspected PGT compromise, perform server-side revocation/regrant rather than merely re-encrypting DB rows.

### 7.4. When Storage Is Redis

Redis works well for multi-node PGTIOU correlation and active vaults, yet is not a “secrets vault” by default. Require:

- TLS and authentication/ACLs; service accounts should read/write only their own app/tenant namespace where possible.
- Server-side TTLs on both pending and active keys—never just Java `if (expired)`.
- Atomic `SET NX EX` or Lua/transaction logic preventing forged callbacks from overwriting an IOU before validation.
- Atomic consume/move from pending→active; prevent two validators from binding the same IOU.
- Per-tenant/CAS namespacing; never run `KEYS *` in request paths.
- Application-level encryption before writing; audit replication, persistence, backups, admin consoles, support tools, and snapshots.
- Rate limits, max pending counts, reaper metrics, and sound memory eviction settings.
- Encryption keys **never** stored in the same Redis instance or under the same IAM permissions as ciphertext.

Even with Redis TLS and disk encryption, admin access, snapshots, AOF, or debugging can expose plaintext if the app writes raw PGTs. Encrypt PGTs in the app/credential broker before sending to Redis.

### 7.5. When Storage Is an RDBMS

Use `ciphertext + keyVersion + nonce` columns, transactional updates, and expiration indexes. For new rows:

1. Use committed pending records after callback; never activate before CAS validation succeeds.
2. Transactional lookup by IOU + expiration + expected status.
3. Bind user/tenant/session post-validation; create/promote active credential and delete pending.
4. Reject duplicate validations or late callbacks and audit the reason.
5. Expiry job purges expired ciphertexts/records with clear backup retention policies.
6. Prevent `SELECT *`, SQL query logging, or ORM `toString()` from printing secret fields.

If DB backups already captured PGT ciphertexts, enforce backup encryption and retention; deleting an active row does not erase historical backups immediately. Distinguish **deleting local metadata** from **CAS Server revocation**.

### 7.6. When Is In-Memory Storage Appropriate?

A `ConcurrentHashMap` or in-memory `ProxyGrantingTicketStorageImpl` works for demos/single-node tests, yet production must address:

- Losing pending callbacks on app restart.
- CAS callback hitting pod A while validator runs on pod B.
- Lack of effective TTL/cleanup causing memory leaks.
- Shared JVM physical memory where heap dumps expose PGTs.
- Logout on node A failing to purge PGTs on node B.
- Missing encrypted persistence or reliable auditing.

Spring Security docs state the in-memory `ProxyGrantingTicketStorageImpl` example **should not be used in real apps** without protection and expiration `cleanup()`. Across multiple pods, use a shared/distributed implementation or strictly constrained callback affinity, managing TTLs and store encryption properly.

## 8. Securing the `pgtUrl` Callback Path

### 8.1. CAS Must Connect to a Trusted HTTPS Callback

The CAS protocol mandates an HTTPS callback to issue PGTs and verifies the endpoint certificate. Your `pgtUrl` must:

- Be a **public URL managed by A**, e.g., `https://portal.example.org/login/cas/proxyreceptor`.
- Be permitted by the CAS Server/service registry per security policy.
- Present a valid TLS certificate and hostname verified by the CAS Server.
- Route cleanly through reverse proxies to A's `CasAuthenticationFilter` or proxy-receptor handler.
- Return 200 upon saving the pending PGT, avoiding arbitrary redirects.
- Never accept `pgtUrl` from user query input or unreviewed config.

**Two-way trust note:** CAS verifies **A is the right HTTPS callback endpoint**. On A's side, however, an inbound TLS connection to A **does not prove the caller is the CAS Server** unless mutual TLS (mTLS) or another caller-auth mechanism is used. Protect the callback with ingress allowlists, mTLS between CAS–A, network segmentation, and most importantly **PGTIOU correlation against the CAS validation response**.

### 8.2. Forged Callbacks and Preemptive IOUs

An attacker can send:

```http
GET /login/cas/proxyreceptor?pgtId=PGT-ATTACKER&pgtIou=PGTIOU-GUESS HTTP/1.1
Host: portal.example.org
```

Never:

- Treat the callback as a successful login;
- Bind that PGT immediately to a user from the request;
- Create an `Authentication` or `HttpSession` merely from those two query parameters;
- Let browsers call an API `/proxy` with an arbitrary `pgtId`.

PGTIOU must have unpredictable random entropy; A promotes it only if the IOU matches a real ST/PT validation result from a **trusted CAS Server**. Also reject duplicate IOUs/pending overwrites, expired entries, and callbacks from unapproved networks/mTLS identities where feasible.

### 8.3. Do Not Turn the Callback into a Logout or Download Endpoint

`/login/cas/proxyreceptor` is a server-to-service CAS endpoint for receiving secrets. It is not a user-facing page, never returns `pgtId` in response bodies, never renders HTML containing tickets, and never logs queries. If a callback misses the Spring filter, return a controlled 404/rejection rather than falling back to a controller printing raw request parameters to console.

### 8.4. Reverse Proxies and Forwarded Headers

Suppose:

```text
External: https://portal.example.org/app/login/cas/proxyreceptor
Ingress:  /app/ -> /
Internal: http://portal-service:8080/login/cas/proxyreceptor
```

Then:

- `Cas20ProxyTicketValidator.proxyCallbackUrl` must be the **external HTTPS** callback.
- `CasAuthenticationFilter.proxyReceptorUrl` is the **local servlet path** post-rewrite, e.g., `/login/cas/proxyreceptor`.
- The CAS Server must trust the public TLS endpoint.
- The proxy must strip/overwrite untrusted `Forwarded`/`X-Forwarded-*`/`Host` headers and never accept arbitrary callback hosts.
- Enable Spring's forwarded-headers strategy only when ingress performs trusted header sanitization; avoid double prefixes.
- If the CAS callback sees 301/302, fix path/HTTPS/canonical URLs so the callback returns 200 directly.

**Do not confuse:** an HTTP reverse proxy in front of an app is completely different from a CAS **Proxy Granting Ticket**; Nginx does not grant an application the ability to request PTs.

## 9. Spring Security CAS: Components for PGTs

Spring Security CAS integration typically includes:

| Component | Effect |
| --- | --- |
| `CasAuthenticationEntryPoint` | Redirects browsers to CAS `/login` when A is unauthenticated |
| `CasAuthenticationFilter` | Receives STs at A's callback and optionally PGT callbacks at `proxyReceptorUrl` |
| `CasAuthenticationProvider` | Validates tickets and builds authenticated principals per policy |
| `ServiceProperties` | Service URL A uses when issuing/validating STs |
| `Cas20ProxyTicketValidator` | Calls CAS validation with `pgtUrl` to request PGTs and uses storage correlation |
| `ProxyGrantingTicketStorage` | Stores/retrieves `pgtIou→pgtId` pairs so the validator can obtain the PGT |
| `CasProxyDecider` / trusted proxy policy | Decides which proxy chains are accepted when acting as a backend |
| `Cas20ProxyRetriever` / CAS client equivalent | Uses PGT to request PTs from CAS `/proxy` per version API |
| `TicketValidator` | Server-to-server CAS validation rather than relying on browser assertions |

**Difference between A and B:** Service A is the CAS **proxying client** holding a PGT to request PTs. Backend B is the CAS **proxied target** receiving PTs and checking chains/trust, normally holding no PGT unless B also proxies onward to C.

### 9.1. Illustrative Dependencies

```xml
<!-- Maven fragment; requires Spring Boot parent/BOM and compatible versions -->
<dependency>
  <groupId>org.springframework.security</groupId>
  <artifactId>spring-security-cas</artifactId>
</dependency>
```

CAS client APIs carry historical package differences: newer docs use `org.apereo.cas.client.*`, while older samples use `org.jasig.cas.client.*`. Never mix both in the same source; pick the artifact/version you are building against and check its Javadoc. Spring Boot will not auto-configure a PGT vault from custom YAML without corresponding beans.

### 9.2. Sharing the Exact `ProxyGrantingTicketStorage`

Java fragment for **Spring Security CAS client compatible with the reference version**:

```java
import org.apereo.cas.client.proxy.ProxyGrantingTicketStorage;
import org.apereo.cas.client.proxy.ProxyGrantingTicketStorageImpl;
import org.apereo.cas.client.validation.Cas20ProxyTicketValidator;
import org.springframework.security.cas.web.CasAuthenticationFilter;

// FRAGMENT: not a standalone class.
// In-memory storage fits tutorials/tests only; production
// must use a vault with TTL/cleanup, security, and cluster semantics.
ProxyGrantingTicketStorage pgtStorage =
        new ProxyGrantingTicketStorageImpl();

Cas20ProxyTicketValidator validator =
        new Cas20ProxyTicketValidator("https://sso.example.org/cas");

validator.setProxyCallbackUrl(
        "https://portal.example.org/login/cas/proxyreceptor");
validator.setProxyGrantingTicketStorage(pgtStorage);

CasAuthenticationFilter casFilter = new CasAuthenticationFilter();
casFilter.setProxyReceptorUrl("/login/cas/proxyreceptor");
casFilter.setProxyGrantingTicketStorage(pgtStorage);

// Still must configure filter's AuthenticationManager, service URL,
// CasAuthenticationProvider with the right validator, filter ordering,
// reverse proxy routes, and registered service in CAS.
```

**Why the exact same storage object?** CAS sends the `pgtIou,pgtId` callback to the filter/receptor, while the validator reads `pgtIou` from the CAS XML validation response. If the two use **two unshared stores**, the validator will never find the matching pair.

**Across multiple pods:** two Java references pointing to one bean **inside a single JVM** do not bridge callback on pod A → validation on pod B. You need a shared storage backend with atomic IOU correlation/TTLs, or a topology guaranteeing affinity with explicit failover testing.

### 9.3. Connecting Validator to `CasAuthenticationProvider`

```java
import org.springframework.security.cas.authentication.CasAuthenticationProvider;

// FRAGMENT: provider is incomplete without
// ServiceProperties, AuthenticationUserDetailsService, and key.
CasAuthenticationProvider provider = new CasAuthenticationProvider();
provider.setTicketValidator(validator);
provider.setServiceProperties(serviceProperties);
provider.setKey("portal-cas-proxy-provider");

// serviceProperties is a ServiceProperties bean with A's service URL.
// Must add user-details mapping and wire the provider into
// AuthenticationManager and the filter configured above.
```

A PGT arrives only if the CAS Server/registered service authorizes proxying and both callback and validation succeed. Attaching `Cas20ProxyTicketValidator` **does not build vault security code automatically** or ensure credentials are safely persisted in KMS/Redis.

### 9.4. Cleanup and Expiration

Spring Security docs note cleaning up expired tickets via `ProxyGrantingTicketStorage.cleanup()` when using an implementation exposing that API. A CAS client version may provide scheduled cleanup; **never set a 24-hour cron and let pending PGTs linger too long**.

Distinguish:

- Cleanup of the **PGTIOU mapping store** used by the CAS client.
- TTL/revocation of the **active PGT vault** managed by the app.
- CAS Server **PGT expiration policy** enforced by the CAS Server.

Calling `cleanup()` on the pending IOU store alone does not purge session-bound active credentials. Conversely, deleting a local PGT does not revoke the real CAS PGT; define both lifecycles.

### 9.5. Do Not Overload One Implementation with Every Concern

The CAS client's `ProxyGrantingTicketStorage` primarily solves **correlating callback PGTIOU→PGT**. By default it does not provide:

- Tenant/session-specific authorization for using a PGT;
- KMS envelope encryption;
- Distributed CAS logout/revocation;
- Per-`targetService` allowlists;
- Multi-region consistency;
- Compliance/audit retention.

If an app keeps PGTs active beyond the callback handshake, design an **active credential vault/service facade** with its own policies, exposing only “request PT for approved target”—never exposing raw PGTs via controllers.

## 10. Requesting a Proxy Ticket from PGT and Protecting `targetService`

Example where A needs to call backend B:

```text
A scope = (tenant-a, CAS-A, service-A, session-42, alice)
    |
    |  lookup active PGT (encrypted)
    |  check notExpired/notRevoked/local user still authenticated
    |  check targetService in explicit allowlist
    v
CAS /proxy?pgt=<PGT_SECRET>&targetService=<BACKEND_B_URL>
    |
    v
CAS response with PT for backend B
    |
    v
A -> backend B, sends PT via approved CAS ticket mechanism
    |
    v
B -> CAS /proxyValidate, verifies PT and trusted proxy chain
    |
    v
B applies its own authorization
```

In the CAS protocol, `/proxy` takes `pgt` and `targetService`. This channel is **backend-to-CAS HTTPS**, yet because parameters sit in the query string, configure **redaction across A's HTTP client, CAS Server access logs, reverse proxies, and APM**. Never send the PGT to backend B or echo it in browser response URLs.

### 10.1. `targetService` Allowlist

A PGT may request PTs for multiple targets per CAS proxy policies. A must add local policy:

| Target | Allowed? | Reason |
| --- | --- | --- |
| `https://api-b.example.org/cas-proxy` | Yes | Approved backend for A |
| `https://api-c.example.org/cas-proxy` | Yes when feature requires | Bound to tenant/business privilege |
| `http://internal-unknown:8080` | No | Disallow cleartext or arbitrary hosts |
| `https://attacker.example/receive` | No | Block arbitrary browser-supplied `targetService` |

If a user sends `?targetService=https://attacker.example` and A forwards it directly as `/proxy` target, you create **confused deputy / proxy credential abuse / SSRF** risks. Use only backend-allowlisted target IDs/URLs and verify user/tenant authorization for the requested action.

### 10.2. Backend Must Validate PT and Proxy Chain

Backend B never trusts a PT merely because it has prefix `PT-`. It calls CAS `/proxyValidate` (or equivalent) and verifies:

- The ticket was issued by CAS for B's exact `targetService`.
- The ticket is unexpired, unused, and validation succeeded.
- The proxy chain contains proxies trusted by B—never arbitrary proxies.
- CAS server TLS/issuer and client settings match.
- Principal/attributes/tenant satisfy B's authorization rules.

Some Spring Security CAS examples show `acceptAnyProxy=true` for illustration. **Never use this as a production default**, as it admits proxy chains from unapproved sources. Configure `CasProxyDecider`, trusted proxy callback identities, and allowlisted service policies.

### 10.3. Failing PGTs Must Never Fall Back to Passwords or Old STs

If `/proxy` returns “PGT invalid/expired”:

1. Mark/remove the corresponding vault entry without leaking the PGT in exceptions.
2. Never retry the same PGT endlessly or mutate prefixes.
3. Never substitute an already-consumed ST for a PGT.
4. When business flow permits, prompt the user to re-run CAS SSO/authentication to obtain a fresh ST, validate, and acquire a fresh PGT.
5. On CAS Server outage, fail closed with a temporary error; never let backend B accept an unverified token.

## 11. Pure Java 17: Simulating Pending PGTIOU, Encrypted Vault, TTL, and Logout

The following program **runs on JDK 17+** with no Spring or CAS dependencies. It models:

- Callback receiving `pgtIou` and `pgtId`, **staging pending only**.
- **Never using the PGT before** a trusted validation result returns the matching IOU.
- Upon receiving a validated IOU and authenticated principal, creating an active entry bound to **tenant, CAS server, local session, and user**.
- Sealing the PGT in the map with **AES-GCM** and scoped AAD (though the demo keeps the key in memory).
- **Pending TTL**, **active local TTL**, subject/session/tenant isolation, multi-use reads, and logout revocation.
- Never printing the PGT secret to console.

**Crucial limitations:** this is a **local model**, not a CAS proxy protocol implementation. `receiveCallback` assumes caller/network protection and `bindValidatedIou` assumes a real CAS validation response already arrived—the program **makes no CAS calls**, checks no ST/PTs, verifies no TLS or signatures, mints no PTs, and enforces no CAS Server policy/revocation. `PGT-DEMO-SECRET` lacks real entropy. The runtime-generated AES key illustrates encryption only; production requires KMS/HSM/envelope encryption, multi-node storage, and authorization auditing.

Save `PgtVaultLifecycleDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class PgtVaultLifecycleDemo {
    record Scope(String tenant, String casServer, String sessionId) {}
    record Sealed(byte[] nonce, byte[] ciphertext) {}
    record Pending(Sealed sealed, Instant expiresAt) {}
    record Active(String subject, Sealed sealed, Instant expiresAt) {}

    static final class Vault {
        private final SecretKey key;
        private final SecureRandom random = new SecureRandom();
        private final Map<String, Pending> pending = new HashMap<>();
        private final Map<Scope, Active> active = new HashMap<>();

        Vault() throws Exception {
            KeyGenerator gen = KeyGenerator.getInstance("AES");
            gen.init(256);
            key = gen.generateKey();
        }

        private Sealed seal(byte[] bytes, String aad) throws Exception {
            byte[] nonce = new byte[12];
            random.nextBytes(nonce);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, key,
                    new GCMParameterSpec(128, nonce));
            cipher.updateAAD(aad.getBytes(StandardCharsets.UTF_8));
            return new Sealed(nonce, cipher.doFinal(bytes));
        }

        private byte[] open(Sealed sealed, String aad) throws Exception {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key,
                    new GCMParameterSpec(128, sealed.nonce()));
            cipher.updateAAD(aad.getBytes(StandardCharsets.UTF_8));
            return cipher.doFinal(sealed.ciphertext());
        }

        private String aad(Scope scope, String subject) {
            return scope.tenant() + "|" + scope.casServer()
                    + "|" + scope.sessionId() + "|" + subject;
        }

        boolean receiveCallback(
                String iou, String pgt, Instant now, Duration ttl)
                throws Exception {
            if (iou == null || pgt == null
                    || ttl.isNegative() || ttl.isZero()
                    || pending.containsKey(iou)) {
                return false;
            }

            byte[] bytes = pgt.getBytes(StandardCharsets.UTF_8);
            try {
                pending.put(iou, new Pending(
                    seal(bytes, "pending:" + iou), now.plus(ttl)));
                return true;
            } finally {
                Arrays.fill(bytes, (byte) 0);
            }
        }

        boolean bindValidatedIou(
                String iou, Scope scope, String subject,
                Instant now, Duration localTtl) throws Exception {
            Pending record = pending.remove(iou);
            if (record == null || !now.isBefore(record.expiresAt())
                    || localTtl.isNegative() || localTtl.isZero()) {
                return false;
            }

            byte[] bytes = open(record.sealed(), "pending:" + iou);
            try {
                active.put(scope, new Active(
                    subject, seal(bytes, aad(scope, subject)),
                    now.plus(localTtl)));
                return true;
            } finally {
                Arrays.fill(bytes, (byte) 0);
            }
        }

        boolean usable(
                Scope scope, String subject, Instant now) throws Exception {
            Active record = active.get(scope);
            if (record == null || !record.subject().equals(subject)
                    || !now.isBefore(record.expiresAt())) {
                return false;
            }

            byte[] bytes = open(
                    record.sealed(), aad(scope, subject));
            try {
                // Simulates internal PGT readability; does NOT verify
                // PGT validity at CAS or mint a Proxy Ticket.
                return bytes.length > 0;
            } finally {
                Arrays.fill(bytes, (byte) 0);
            }
        }

        void revokeLocalSession(Scope scope) {
            active.remove(scope);
        }
    }

    public static void main(String[] args) throws Exception {
        Instant now = Instant.parse("2026-11-07T00:00:00Z");
        Scope a = new Scope("tenant-a", "cas-a", "session-A");
        Scope otherSession =
                new Scope("tenant-a", "cas-a", "session-B");
        Scope otherTenant =
                new Scope("tenant-b", "cas-a", "session-A");

        Vault vault = new Vault();

        System.out.println("Callback staged: " +
            vault.receiveCallback("PGTIOU-ONE", "PGT-DEMO-SECRET",
                now, Duration.ofSeconds(10)));

        System.out.println("Before IOU validation: " +
            vault.usable(a, "alice", now));

        System.out.println("Validated IOU bound: " +
            vault.bindValidatedIou("PGTIOU-ONE", a, "alice",
                now, Duration.ofSeconds(120)));

        System.out.println("Owner can use PGT: " +
            vault.usable(a, "alice", now));
        System.out.println("Wrong subject denied: " +
            vault.usable(a, "bob", now));
        System.out.println("Other session denied: " +
            vault.usable(otherSession, "alice", now));
        System.out.println("Other tenant denied: " +
            vault.usable(otherTenant, "alice", now));

        System.out.println("PGT reusable locally: " +
            vault.usable(a, "alice", now.plusSeconds(1)));
        System.out.println("Local TTL expired: " +
            vault.usable(a, "alice", now.plusSeconds(120)));

        vault.revokeLocalSession(a);
        System.out.println("After local logout: " +
            vault.usable(a, "alice", now.plusSeconds(2)));

        vault.receiveCallback(
            "PGTIOU-LATE", "PGT-OTHER-DEMO",
            now, Duration.ofSeconds(10));
        System.out.println("Late IOU rejected: " +
            vault.bindValidatedIou(
                "PGTIOU-LATE", a, "alice",
                now.plusSeconds(11), Duration.ofSeconds(120)));
    }
}
```

Compile and run:

```bash
javac PgtVaultLifecycleDemo.java
java PgtVaultLifecycleDemo
```

**Exact stdout** (nonce and AES key are random, yet boolean outputs are fixed):

```text
Callback staged: true
Before IOU validation: false
Validated IOU bound: true
Owner can use PGT: true
Wrong subject denied: false
Other session denied: false
Other tenant denied: false
PGT reusable locally: true
Local TTL expired: false
After local logout: false
Late IOU rejected: false
```

### 11.1. Explanation of Checks

1. `Callback staged=true`: in the model, the callback stores the encrypted PGT in pending state; not yet bound to a user.
2. `Before IOU validation=false`: pending is not an active credential; backend A cannot use it.
3. `Validated IOU bound=true`: assumes CAS validation succeeded with the same IOU, so A binds the secret to `tenant-a/cas-a/session-A/alice`.
4. `Owner can use PGT=true`: scope + subject match and local TTL is active; a real app still must query CAS `/proxy` to verify the PGT remains valid.
5. `Wrong subject/Other session/Other tenant=false`: prevents cross-user, cross-session, and cross-tenant PGT misuse.
6. `PGT reusable locally=true`: unlike ST/PT, a PGT is not consumed simply by reading from the vault once; at CAS it may still expire or be revoked at any time.
7. `Local TTL expired=false`: reaching the exact expiry boundary counts as expired.
8. `After local logout=false`: local revocation immediately closes PGT usage even prior to the original TTL.
9. `Late IOU rejected=false`: an expired pending callback cannot be promoted to an active credential.

### 11.2. Why Is This Demo Not a Production PGT Vault?

- Maps are not thread-safe/atomic for concurrent callbacks/requests; never use `HashMap` for shared multi-threaded state.
- The demo accepts secrets from Java `String`, which cannot be zeroed out; temporary plaintext can linger on the heap until GC. `Arrays.fill` shrinks only one byte buffer's lifetime.
- The AES key lives in JVM memory and vanishes on restart; it lacks KMS, key versioning, key rotation, encrypted backups, and multi-pod access.
- `receiveCallback` does not verify CAS/ingress client certificates, lacks a CAS server allowlist, and has no cap on the pending map.
- `bindValidatedIou` trusts the caller's “validated” assertion without performing real ST/PT validation—production must invoke it solely after a trusted validator result.
- `usable` only decrypts and reads bytes; it **cannot know whether CAS revoked the PGT**, calls no `/proxy`, and checks no `targetService`. Never use such a boolean to bypass backend authorization.
- No session invalidation hooks/SLO listeners, CAS ticket-registry expiry, TTL cleanup jobs, logout fan-out, or distributed transactions.
- No auditing/metrics/circuit breakers or CAS failure handling.

The demo illustrates the **two-phase pending→active transition, confidentiality, and local time/scope guards**; real CAS clients and production vaults handle actual authentication and ticket protocols.

## 12. End-to-End Testing: CAS Server, A, and Backend B

### 12.1. Happy Path That Must Be Observed

1. Browser logs into A via CAS; CAS issues an ST for exact service A.
2. A validates the ST with exact service URL and approved `pgtUrl`.
3. CAS sends an HTTPS callback to A's proxy receptor with `pgtIou` and `pgtId`; A creates a pending entry **without logging secrets**.
4. CAS returns `authenticationSuccess` carrying `cas:proxyGrantingTicket = PGTIOU`.
5. A verifies the XML response from the trusted CAS backend and correlates the IOU with pending; the active vault binds the exact user/tenant/session.
6. A invokes a feature requiring B; local authorization and the `targetService` allowlist pass.
7. A retrieves the PGT from the vault and calls CAS `/proxy` over HTTPS; CAS issues PT B.
8. A sends the PT to B via a supported CAS proxy ticket mechanism; B calls CAS `/proxyValidate` and checks the proxy chain.
9. B returns authorized data; A sends its response to the browser. **The PGT never reaches the browser.**
10. Another call to B can request a **fresh PT** using the same PGT while still valid, if CAS and authorization permit.
11. User logs out of A/CAS; the local vault entry is deleted, and the server-side CAS PGT is revoked per policy/logout.

### 12.2. Mandatory Negative Tests

| Scenario | Expected Outcome |
| --- | --- |
| Callback delivers PGT, yet ST validation fails | Creates no active PGT |
| Callback carries IOU absent from validation XML | Deletes/rejects pending |
| Validation XML carries IOU without a pending PGT | Grants no proxy rights |
| IOU already expired or missing | Rejects promotion |
| Duplicate IOU callback with a different PGT | Rejects; never overwrites secret |
| Callback from untrusted IP/TLS identity (per architecture) | Rejected at ingress/mTLS/network layer |
| `pgtUrl` is HTTP, invalid cert, or hostname mismatch | CAS fails to issue PGT |
| `pgtUrl` reverse proxy returns 404 or 302 loop | Proxy negotiation fails; investigate routing |
| `/serviceValidate` returns HTTP 200 with XML `authenticationFailure` | Never accepts PGT |
| Wrong service URL on ST validation | CAS `INVALID_SERVICE`; ST consumed |
| TGT/CAS SSO logout while local vault still holds encrypted PGT | `/proxy` rejected by CAS; vault purges entry |
| Local user logs out of A while CAS TGT persists | A's active PGT revoked per local policy |
| PGT exceeds local TTL | Never decrypts or calls CAS |
| Server-side PGT expires before local TTL | CAS rejects; A invalidates entry |
| Tenant A's PGT used for user/tenant B | Rejected by local scope |
| Session X's PGT used in session Y | Rejected by local scope |
| Browser sends `pgtId` to backend A | Ignored/rejected; never uses raw PGT |
| A uses attacker-chosen `targetService` | Rejected by target allowlist |
| Backend B accepts arbitrary proxy chain | Security test fails; tighten trusted proxy policy |
| Already-validated PT resubmitted | Rejects replay |
| B's PT presented to C | Rejects service binding |
| Redis plaintext `PGT-...` or AOF dump leaks secret | Security QA FAIL |
| APM/WAF/Nginx logs callback query containing `pgtId` | Security QA FAIL |
| CAS `/proxy` backend request logs raw `pgt` | Security QA FAIL |
| Pending map flooded with 100k fake callbacks | Bounded rejection/rate limit, no heap exhaustion |
| CAS callback hits pod A, validator hits pod B | IOU correlation via shared storage or fail closed |
| Two validation workers bind the same IOU | Only one atomic transaction succeeds |
| KMS key revoked/unavailable | Fails closed; never returns plaintext or retries insecurely |
| Corrupted ciphertext/auth tag | AEAD decrypt fails; revoke entry/audit |
| Clock reaches exact `expiresAt` | Expired; not usable |
| Logout/SLO arrives concurrently with `/proxy` call | Consistent race handling per policy; revoked credential unusable |
| PGT persists in backups after active deletion | Covered by retention/cryptographic-erase/incident policy |

### 12.3. Vault Unit Tests + Protocol Integration Tests Are Two Tiers

**Vault unit tests** prove TTLs, encryption, IOU correlation, scope isolation, concurrency, and revocation. They do **not** prove a real CAS Server issued a PGT properly or that backend B validated a PT.

**CAS integration tests** prove service registry, TLS callbacks, XML `cas:proxyGrantingTicket`, `/proxy` semantics, CAS Server PGT expiration, single-use PTs, and trusted proxy chains. Never write a CAS mock that “always returns `authenticationSuccess`” and declare security integration PASS.

### 12.4. Testing Concurrency and Restarts

A worthwhile test:

```text
CAS Server callback PGTIOU-X hits pod A
            |
            v
Shared pending store commits + TTL
            |
CAS /serviceValidate response handled on pod B
            |
            v
B atomically looks up/consumes PGTIOU-X
            |
            v
B binds user/session/tenant -> encrypted active PGT
            |
            v
Pod C reads active PGT in exact scope to request a PT
```

When using session affinity, also test failover and callbacks hitting another pod. If a pending record is lost on restart prior to promotion, the outcome **fails closed** and the user/caller needs a new auth/proxy grant flow—**never synthesize a PGT from PGTIOU** or accept a username from callback queries.

## 13. Logging and Operations Without Leaking PGTs

### 13.1. Recommended Audit Sample

```json
{
  "event": "cas_pgt_vault_transition",
  "service": "portal",
  "tenant": "tenant-a",
  "cas_server_id": "corp-cas",
  "state": "ACTIVE",
  "reason_code": "IOU_CORRELATED",
  "local_expiry_seconds": 1200,
  "request_id": "evt-742"
}
```

This is **mock data**. Never put `pgtId`, `pgtIou`, `ticket`, TGC, session cookies, principal emails/NameIDs, or raw HTTP queries into ordinary metrics/audits. Even public-friendly hashed/HMACed references must be evaluated for linkability and privacy. Use bounded allowlisted labels to avoid cardinality explosions.

### 13.2. Places Where PGTs Accidentally Leak

- Nginx `$request_uri` or default ingress access logs recording callback queries.
- Full APM/trace `http.url` containing `pgtId=...` or CAS `/proxy?pgt=...`.
- HTTP client debug logging of request URLs/queries.
- `Exception.getMessage()` embedding full URL queries.
- Cache debugging tools, Redis CLI transcripts, AOF/snapshots.
- ORM `toString()` or JSON serialization inside error responses.
- Heap dumps, crash dumps, support archives, unencrypted backups.
- Code review screenshots, cURL history, or CI test artifacts.

**Configure redaction at every layer.** Ensuring the app logger omits PGTs is insufficient if the ingress or CAS Server still logs query strings. Use dummy credentials in all test logs/traces and run scanners to catch `pgtId=`, `pgt=`, `PGT-`, and `PGTIOU-` in forbidden fields.

### 13.3. Appropriate Metrics

| Metric | Meaning |
| --- | --- |
| `cas_pgt_callback_total{result}` | Callback success/invalid/duplicate counts |
| `cas_pgt_iou_bind_total{result}` | IOU correlation outcomes |
| `cas_pgt_pending_entries` | Detects pending store growth/floods |
| `cas_pgt_active_entries` | Capacity/retention without exposing user labels |
| `cas_pgt_expiry_total{reason}` | Local TTL / CAS server rejection / revocation |
| `cas_proxy_ticket_request_total{result,target}` | CAS `/proxy` successes/failures |
| `cas_proxy_backend_validation_total{result}` | Backend `/proxyValidate` outcomes |
| `cas_pgt_decrypt_failure_total` | KMS/key mismatch or ciphertext tampering |
| `cas_pgt_storage_latency_seconds` | Redis/DB/KMS access latency |

Never put raw IOUs/PGTs, session keys, NameIDs, emails, or arbitrary browser-supplied `targetService` values in metric labels.

## 14. Incident Response on Suspected PGT Compromise

1. **Containment:** scope CAS servers, services, tenants, sessions, affected targets, and exposure window; never paste raw PGTs into chat or tickets.
2. **Stop usage:** revoke scoped local vault entries, block proxy capability from A if needed, and disable affected service registrations/target policies as warranted.
3. **CAS-side revocation:** coordinate with CAS admins to invalidate TGT/PGT/SLO sessions or supported admin endpoints; deleting local Redis rows alone is insufficient.
4. **Assess issued PTs:** inspect redacted backend logs, proxy chains, authorization events, PT lifetimes, and potential unauthorized actions; PTs are normally single-use yet may already have been spent.
5. **Safe recovery:** fix the leak vector (access logging, APM, Redis ACLs, mTLS, compromised key), rotate encryption keys if needed, and require reauthentication/regrant.
6. **Monitor:** watch for anomalous CAS `/proxy` calls, `targetService` spikes, concurrent calls, repeated invalid PGTs, and unusual proxy chains.
7. **Closure:** re-test callbacks/TTLs/revocation, verify zero raw secrets remain in logging pipelines, and update runbooks and ticket-retention policies.

**Never treat “we re-encrypted the old PGT” as proof the secret is safe:** if a copy of the credential escaped, only CAS server-side revocation (or true expiration) prevents that copy from being used.

## 15. Common Design Mistakes

| Anti-Pattern | Why It Is Wrong | Right Approach |
| --- | --- | --- |
| Storing plaintext PGT in `HttpSession`/browser cookie | Browser/session leaks; PGT is reusable | Server-side encrypted vault with session-bound authz |
| Passing PGT in frontend query parameters | Leaks via logs, Referrer, and history | Only backend calls CAS `/proxy` |
| Using `PGTIOU` instead of `PGT` at CAS `/proxy` | IOU is strictly a correlation token | Retrieve PGT from correlated callback |
| Binding callback PGT directly to query username | Callbacks can be forged; no validation success yet | Pending state + trusted CAS validation result |
| Keying PGT solely by username in map | Cross-session/cross-tenant collisions | Composite scope plus authorization checks |
| One global PGT across all tenants | Cross-tenant delegated access | Per-tenant/CAS/service isolation |
| Infinite active TTL trusting CAS auto-revocation | Local leaks, backup exposure, missed SLOs | Local upper bound + cleanup + server revocation |
| Assuming active local TTL means server PGT is valid | CAS logout/expiry may happen earlier | CAS `/proxy` result is truth; fail closed |
| Clearing only Redis after PGT compromise | Exfiltrated PGT copy still works at CAS | Revoke CAS PGT/TGT + investigate |
| Using in-memory `ProxyGrantingTicketStorageImpl` across pods | Callback/validator lack shared state | Shared encrypted store + atomic IOU binding |
| Never calling `cleanup` on pending records | Memory growth and orphaned secrets | TTLs, bounded pending entries, cleanup |
| Enabling `acceptAnyProxy=true` on backend | Admits unapproved proxy chains | Trusted proxy allowlist/decider |
| Plain HTTP `pgtUrl` or trust-all self-signed certs | PGT intercepted or leaked | HTTPS + cert validation, approved callback |
| Disabling app logs while APM captures `request.url` | Raw PGT in traces | Redaction at every layer |
| Letting browser pick arbitrary `targetService` | Confused deputy / SSRF | Service/target allowlist and user authz |
| Protecting DB with Base64 | Not encryption | AEAD + KMS + ACLs + encrypted backups |
| Reusing one PT across multiple calls | PTs are single-use; replay fails | Request a fresh PT when needed |
| Rotating KMS key thinking CAS PGT changed | KMS and CAS credentials are separate | Revoke/regrant at CAS on PGT compromise |
| Setting CAS/TGT expiry equal to `HttpSession` TTL | Two systems have separate lifecycles | Independent policies + revoke/timeout handlers |

## 16. Production Checklist

- [ ] Confirmed service A truly requires Proxy Authentication rather than standard service ticket login.
- [ ] PGT, PGTIOU, PT, ST, TGT/TGC, and local sessions are clearly distinguished.
- [ ] CAS Server/service registry authorizes proxying strictly per trust and `targetService` policies.
- [ ] Service A validates ST/PT with a trusted HTTPS CAS Server before linking any PGT to a principal.
- [ ] `pgtUrl` is an approved public HTTPS callback; TLS/hostname/certificate are verified by CAS.
- [ ] `Cas20ProxyTicketValidator.proxyCallbackUrl` aligns with local `CasAuthenticationFilter.proxyReceptorUrl` post-routing.
- [ ] Callback `GET` (`pgtIou,pgtId`) writes only an encrypted pending record without creating sessions or roles.
- [ ] IOU is correlated with CAS `authenticationSuccess` XML; pending record is consumed atomically without duplicate overwrites.
- [ ] Active vault keys bind tenant, CAS server, local authenticated session/service, and subject.
- [ ] PGT store enforces AEAD/KMS encryption, proper key versions/AAD/nonces, and TLS+ACL+backup controls.
- [ ] Pending TTL is short with bounded counts, cleanup jobs, and duplicate/race controls.
- [ ] Active local TTL is bounded by policy without assuming a fixed CAS server PGT TTL.
- [ ] Local logout, session expiry, CAS SLO, tenant unlinking, and compromises all trigger scoped revocation.
- [ ] CAS Server PGT logout expiration is tested on the actual deployed release.
- [ ] Invalid/expired CAS `/proxy` responses purge local entries; never fail open or reuse old STs.
- [ ] Backend B validates PTs via `/proxyValidate` and a trusted proxy chain; never blindly enables `acceptAnyProxy=true`.
- [ ] `targetService` allowlist and per-user authorization run before A requests a PT.
- [ ] Multi-node/region callbacks, pending store, active vault, and CAS ticket registry maintain proper atomicity/consistency.
- [ ] Ingress/WAF/APM/HTTP client/CAS Server logs all redact PGT/IOU/tickets/cookies/PII.
- [ ] PGTs are never exposed to browsers, JavaScript, cookies, API responses, or error pages.
- [ ] Backup/restore/retention, encryption key loss, and incident response procedures are tested.
- [ ] Negative tests cover forged callbacks, IOU mismatches, expiry, replays, wrong tenant/session, stale CAS, tampered ciphertext, and SLO.
- [ ] Configs, classes, and packages are verified against exact Spring Security and CAS client versions.

## 17. Review Questions

**1. What is the biggest difference between a PGT and a Service Ticket?**  
A PGT can be used multiple times to request PTs while CAS permits; an ST is a service-specific login ticket valid for only one validation attempt.

**2. Can PGTIOU be used to call `/proxy?pgt=...`?**  
No. PGTIOU only links the callback's `pgtId` with `cas:proxyGrantingTicket` in the XML validation response. Pass the **real PGT** in backend CAS `/proxy` requests.

**3. Why does the CAS Server call `pgtUrl` before returning the XML response to A?**  
CAS delivers the secret PGT over a direct HTTPS callback while returning an IOU in the XML so A can bind the secret to the validated result/principal—keeping the PGT out of browser traffic.

**4. Can the PGT be bound immediately when the callback GET delivers `pgtId`?**  
No. Callbacks can be forged; use a pending store and correlate by IOU after successful validation from trusted CAS.

**5. A PGT has 10 minutes left on its local TTL, yet the user just logged out of CAS. Can it still request PTs?**  
No. The CAS protocol mandates PGT expiration on CAS logout. Local storage must revoke on signal and handle CAS rejections.

**6. Is keying the PGT store solely by username sufficient?**  
No. You must distinguish tenant, CAS server, service, local authenticated session, and user identity to prevent cross-tenant/session delegation.

**7. If you only hash the PGT, how can you request a Proxy Ticket?**  
CAS `/proxy` needs the plaintext PGT; one-way hashes cannot be reversed. Use an encrypted vault or a credential broker to submit the PGT from an authorized backend.

**8. If an encrypted PGT is stored in Redis, does deleting the Redis key revoke it at CAS?**  
No. Deleting Redis stops the app from using it; any exfiltrated copy of the PGT remains valid at CAS until server revocation or expiration.

**9. Why must `ProxyGrantingTicketStorage` be shared between the filter and validator?**  
The filter receives IOU/PGT from the CAS callback while the validator reads the IOU from XML; sharing one store lets them pair the secret. Multi-pod setups need a distributed shared store or a tested affinity topology.

**10. Does an HTTPS `pgtUrl` callback automatically prove the caller is the CAS Server?**  
No. A's TLS certificate authenticates A's endpoint to the caller, absent mTLS or caller auth. A must restrict inbound traffic and rely on IOUs from trusted validation responses.

**11. Should `acceptAnyProxy=true` be used on backend B?**  
Not as a default. The backend must restrict trusted proxy services and chains per policy.

**12. Can one PT be used for 10 REST calls to B?**  
Not under single-use ticket semantics. A should request fresh PTs or rely on a contracted authentication cache that does not bypass CAS validation guarantees.

**13. How do the CAS Server and app A differ on PGT TTL?**  
CAS governs server-side PGT validity; A enforces local upper bounds, revocation, and cleanup. A local TTL can never extend a credential already expired at CAS.

**14. Can a `TGT` be used instead of a PGT to call CAS `/proxy`?**  
No. A TGT is a CAS SSO grant, not a `pgt` API parameter for service A. The TGC belongs to the browser's CAS origin.

**15. How should you respond if a KMS key is compromised?**  
Assess which ciphertexts and PGTs could be decrypted; rotate KMS/key material, re-encrypt safely, and simultaneously revoke/regrant affected CAS PGTs if secret exposure is possible.

**16. What should happen when the CAS callback staged a PGT, yet the validation XML lacks an IOU?**  
Do not promote it; expire pending via TTL or clean up, investigate callback/certificate/service policy, and never grab “the latest PGT.”

## 18. Standards and References

- [Apereo CAS — CAS Protocol 2.0 Specification](https://apereo.github.io/cas/8.0.x/protocol/CAS-Protocol-V2-Specification.html): `pgtUrl`, `pgtId`, `pgtIou`, `/proxy`, multi-use PGT, expire on CAS logout, and ticket validation.
- [Apereo CAS — CAS Protocol 3.0 Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): `/serviceValidate`, `/proxyValidate`, `/proxy`, PGTIOU, and proxy chains; development docs may differ from production releases.
- [Apereo CAS — Proxy Authentication](https://apereo.github.io/cas/development/authentication/Configuring-Proxy-Authentication.html): proxy-enabled registered services, callback TLS, PGT issuance, and the alternative encrypted PGT extension; check your exact release.
- [Apereo CAS — Proxy Granting Ticket Policies](https://apereo.github.io/cas/development/ticketing/Configuring-Ticket-Expiration-Policy-PGT.html): version-specific expiration settings; never guess runtime defaults.
- [Spring Security — CAS Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): `ProxyGrantingTicketStorage`, `Cas20ProxyTicketValidator`, `CasAuthenticationFilter`, proxy callback/storage wiring, and cleanup reminders.
- [Spring Security — CasAuthenticationFilter Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationFilter.html): `proxyReceptorUrl`/`proxyGrantingTicketStorage` and filter responsibilities.
- [Spring Security — CAS Modules](https://docs.spring.io/spring-security/reference/modules.html): `spring-security-cas` dependency.
- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html): key lifecycle, KMS, storage, and revocation.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): secret store ACLs, rotation, and auditing.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): keeping secrets/tickets out of logs and structured auditing.
- [OWASP Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): trusted HTTPS and certificates.

**Remember:** **A PGT is a reusable delegation secret for requesting Proxy Tickets**, not a single-use ST and not a `PGTIOU`. Service A stores a PGT only after **HTTPS callback + IOU correlation with a trusted CAS ticket validation result**, inside a **vault encrypted and partitioned by tenant/user/session/CAS server, with TTLs, cleanup, and revocation**. The CAS Server must reject PGTs upon CAS logout/expiration; deleting local storage does not revoke the CAS-side PGT copy. Backend B accepts only **PTs bound to its exact `targetService` and an approved proxy chain**. PGT secrets must never leak through browsers, callback logs, Redis dumps, APM, HTTP query logs, or support artifacts.