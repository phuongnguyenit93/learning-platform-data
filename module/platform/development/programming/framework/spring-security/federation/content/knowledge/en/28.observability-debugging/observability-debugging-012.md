# Collecting Audit Logs for Login, Logout, and Partner Changes in Spring Security Federation

## 1. Goal and Context

In a **Spring Security – federation** system, an application may accept identities from multiple **Identity Providers (IdPs)** over **OpenID Connect (OIDC)**, **SAML 2.0**, or **CAS**. When an incident happens, the question is not just "Did HTTP return 200 or 302?" but also:

- Which user, via **which identity partner**, logged in successfully or failed?
- Was the failure in authentication, signature/issuer, attribute payload, authority mapping, MFA, or application policy?
- Did a logout operation **only delete the app's local session**, **initiate Single Logout (SLO)**, or **receive confirmation from the IdP**?
- Who changed the metadata, EntityID, issuer, certificate, ACS/redirect URI, client registration, role mapper, or SLO endpoint of a **federation partner**? Which change was approved, applied on which nodes, and was there a rollback?
- Can an investigation timeline be reconstructed without **storing raw tokens, CAS tickets, `SAMLResponse`, session cookies, or private keys**?

This lesson belongs to **Observability and debugging**. "**Partner**" here means a technical federation partner such as an **IdP/Asserting Party, SAML Service Provider, OIDC client/provider, CAS server/service**, or a B2B partner with trust configuration—not an end user or a purchase transaction.

**Learning outcomes:** build a standard event taxonomy; properly combine Spring Security events and protocol handlers; record both local logout and SAML/OIDC/CAS global logout; monitor trust-configuration changes; run a durable audit pipeline with access control and retention; and verify via **standalone Java 17**, Spring configuration examples, and an end-to-end test matrix.

> **Overarching principle:** an audit event must answer **when – where – who – did what – with what outcome – under which trust context**. Yet audit data **must never become a store of raw credentials, assertion XML, or raw personal information**.

## 2. Audit Trails Differ from Access Logs, Debug Logs, and Metrics

| Type | Primary Purpose | Example | Sufficient for Federation Investigation? |
| --- | --- | --- | --- |
| **HTTP access log** | Method, route, response code, latency | `POST /login/saml2/sso/corp 302` | **No**: 302 can be a success or an error redirect |
| **Application debug log** | Operational details for devs | "Resolver picked registration X" | Helpful for investigation, yet not necessarily complete/durable |
| **Security audit event** | Evidence of security actions and privilege/trust changes | `LOGIN_DENIED / INVALID_SIGNATURE` | **Yes**, if schema, completeness, and integrity are properly designed |
| **Trace/span** | Distributed flow, latency | trace ID, span between SP and IdP | Correlation only; not an audit record itself |
| **Metric** | Trends, alerts, operational SLOs | `login_failure_total{protocol="SAML2"}` | Insufficient to attribute individual changes |
| **Configuration change record** | Who changed which partner, what changed, before/after, approval, effective time | `PARTNER_SIGNING_CERT_ACTIVATED` | Mandatory when investigating trust changes |
| **IdP-side audit** | Authentication/MFA/SSO session and issuance at the IdP | `MFA_CHALLENGE_PASSED` | SP cannot substitute for it; must correlate safely |

**Never infer "login succeeded" from HTTP 200.** When the app has not created a Spring `Authentication` while the IdP completed authentication, the two systems have different outcomes. Likewise, a user clicking "Logout" does not prove every IdP session and other applications were terminated.

### Audit Trails Require Relative Immutability

An in-memory log or local app file easily rotates/vanishes on pod restarts. For security auditing, design for:

1. **Append-only**: append new events rather than silently editing/deleting old events.
2. **Traceability**: include `event_id`, `event_time`, `service`, `environment`, `partner_key`, and `correlation_id`.
3. **Integrity**: restrict edit/delete operations, audit access, and use WORM/object lock, checksum/hash chains, or SIEM integrity controls where appropriate.
4. **Durability**: do not store solely in one pod's RAM; use a durable repository or broker/collector.
5. **Controlled access**: security auditors can query; developers/support see only necessary fields.
6. **Reasonable retention**: govern storage/deletion/legal holds by policy rather than keeping everything forever just because "it might be useful".
7. **UTC timezone** and schema versioning for cross-system analysis.

The signature of a `SAMLResponse` does not replace the integrity of **audit storage**: SAML signing authenticates the SAML message, whereas audit evidence must be protected **after the event is recorded**.

## 3. Event Taxonomy: Do Not Stop at Just LOGIN and LOGOUT

Define explicit **`event_type`** values bounded by an enum/schema instead of free-form strings:

| Suggested Event Type | When Emitted | Outcome / Meaning |
| --- | --- | --- |
| `LOGIN_STARTED` | SP initiates federation flow | Just started, **not yet authenticated** |
| `LOGIN_CALLBACK_RECEIVED` | Callback/ACS receives request | Data received only, not yet verified |
| `LOGIN_AUTHENTICATED` | Spring provider verified and built a valid `Authentication` | Passed protocol validation and corresponding account mapping |
| `LOGIN_REJECTED` | Provider/filter rejects login | Authentication failed; safely classified reason |
| `LOGIN_POLICY_DENIED` | Identity valid yet denied by local business/tenant policy | Distinguishes authenticated from authorized |
| `LOGIN_SESSION_ESTABLISHED` | HTTP session/SSO principal ready | Concrete app session exists if app uses sessions |
| `SESSION_EXPIRED` | Session expired/invalidated by backend or container | **Do not assume the user actively logged out** |
| `LOGOUT_REQUESTED` | User/IdP/API requests logout | Does not yet prove cleanup or SLO completed |
| `LOGOUT_LOCAL_COMPLETED` | App cleared security context/session per design | Confirms **local logout** only |
| `LOGOUT_SLO_DISPATCHED` | SP sent logout request to IdP or vice versa | Sent/in flight; partner acceptance unknown |
| `LOGOUT_SLO_CONFIRMED` | Response/ack received and validated per protocol | Confirms only the proven correlated scope |
| `LOGOUT_SLO_REJECTED` | Bad signature, issuer, state, destination, correlation... | Cannot assert remote sessions were terminated |
| `PARTNER_CONFIG_PROPOSED` | Request to change a federation partner submitted | Not yet approved/effective |
| `PARTNER_CONFIG_APPROVED` | Authorized reviewer approved | Does not yet prove the system applied it |
| `PARTNER_CONFIG_ACTIVATED` | New config/metadata version applied | Effective across specified nodes/realm |
| `PARTNER_CONFIG_ROLLED_BACK` | Restored prior config version | Explicitly records old and new versions |
| `PARTNER_CERT_ROTATED` | Changed public cert/verification or encryption key reference | Must record key use, fingerprint, and status |
| `PARTNER_DISABLED` | Disabled trust relationship | Does not mean all old sessions/tokens are revoked |
| `AUDIT_DELIVERY_FAILED` | Pipeline failed to write/ship audit | Operational alert; never ignore silently |

These names are a **proposed system contract**, not all built-in Spring Security events. **Spring emits certain authentication/logout events**, whereas **partner config changes, SLO confirmation, and many protocol stages must be actively instrumented by the app/IdP/platform**.

### Event Status Must Be Bound to a Phase

A helpful rule:

~~~text
phase=PROTOCOL_CALLBACK, result=RECEIVED
  != phase=AUTHENTICATION, result=SUCCESS
  != phase=LOCAL_SESSION, result=ESTABLISHED
  != phase=BUSINESS_AUTHORIZATION, result=ALLOW

phase=LOGOUT_REQUEST, result=ACCEPTED
  != phase=LOCAL_SESSION, result=CLEARED
  != phase=REMOTE_SLO, result=CONFIRMED
~~~

If everything is collapsed into `LOGIN_SUCCESS` the moment HTTP POST `SAMLResponse` arrives, an attacker only needs to submit invalid XML to generate a fake "successful login". Record security outcomes **after** verification at the right layer.

## 4. Diagram of Event Sources and Collection Paths

~~~mermaid
flowchart TD
    B[Browser] --> S[Spring Security SP / RP]
    S --> IDP[IdP / CAS / Partner]
    IDP --> IA[IdP audit stream]
    S --> AE[Authentication events]
    S --> LE[Logout / SLO handlers]
    S --> CE[Partner config change service]
    AE --> EN[Approved audit event schema]
    LE --> EN
    CE --> OB[Transactional outbox]
    OB --> EN
    IA --> SIEM[Central SIEM / durable event store]
    EN --> SIEM
    SIEM --> C[Correlate / alert / investigate]
~~~

**Source boundaries:** the IdP knows actual authentication/MFA at the IdP; the SP knows callback validation and local sessions; CAS knows ticket issuance/redemption; the config service knows who approved and applied partner metadata. **No single log source can prove events outside its observation boundary.**

**The diagram does not imply** the app always sends logs synchronously to the SIEM on the request thread. Critical config changes may need a durable local outbox; high-volume logins must account for latency, backpressure, and audit-loss risk.

## 5. Logging In via OIDC: What to Audit?

An OIDC Authorization Code flow normally has:

~~~text
1. GET /oauth2/authorization/{registrationId}
   -> LOGIN_STARTED (optional; not success)

2. Browser redirects to IdP, IdP authenticates/MFA
   -> IdP-side MFA/login events

3. GET /login/oauth2/code/{registrationId}?code=...&state=...
   -> callback RECEIVED only (not yet successful)

4. Spring validates state, exchanges code over HTTPS,
   validates ID Token signature, issuer, audience, expiry/nonce
   -> LOGIN_AUTHENTICATED or LOGIN_REJECTED

5. App maps (verified iss, sub) -> local user/tenant/roles
   -> LOGIN_POLICY_DENIED or local session ready

6. Browser redirected to clean app URL
   -> report current session and authorization normally
~~~

**Useful audit fields**:
- `protocol=OIDC`, `partner_key=corp_oidc` or configured registration ID.
- `stage=ID_TOKEN_VALIDATION`, `reason=INVALID_ISSUER`, `NONCE_MISMATCH`, `CODE_EXCHANGE_FAILED`... using **normalized error codes**.
- `subject_ref` as a local ID or stable pseudonymous reference after validation; no need to log raw `sub`/`email`.
- `issuer_ref` or partner config revision; never treat an issuer URL from an unverified request as a trusted identity.
- `client_key` if one service has multiple OAuth clients (administratively approved ID name).
- `session_ref` as a separate random audit reference if truly needed; **never use the raw session cookie**.
- `trace_id`/`interaction_id` independent of OAuth `state`.

**Do not log**:
- `code`, `state`, `nonce`, `code_verifier`, `client_secret`, access/refresh/ID tokens.
- Full callback URL/query string, `Authorization`/`Cookie`/`Set-Cookie` headers.
- Raw ID Token claims JSON containing PII.
- Token endpoint response bodies or HTTP client wire logs.

**Prevent mix-up:** if two IdPs share usernames or realms, record the exact `partner_key` of the **validated registration**, rather than taking `registrationId` from an untrusted path and treating it as a verified result. If the token is valid yet local roles/tenant deny access, record two clear events/stages rather than mislabeling it "OIDC authentication failed".

## 6. SAML2 Login: Auditing Validation and Mapping Separately

On SAML HTTP POST to `/login/saml2/sso/{registrationId}`, the browser submits `SAMLResponse`; Spring Security/OpenSAML decrypts (if encrypted), verifies signature/issuer/destination/recipient/audience/time/replay, and builds the authenticated principal.

Proposed mapping:

| Stage | Suggested Reason Code | Meaning |
| --- | --- | --- |
| `ACS_RECEIVED` | `CALLBACK_RECEIVED` | Request reached SP, not yet trusted |
| `RESPONSE_SIGNATURE` | `SIGNATURE_INVALID` | Signature failed verification |
| `ASSERTION_DECRYPTION` | `DECRYPTION_FAILED` | Failed to decrypt with SP decryption credential |
| `ASSERTION_ISSUER` | `ISSUER_MISMATCH` | Issuer does not belong to registered partner |
| `ASSERTION_CONDITIONS` | `ASSERTION_EXPIRED` / `ASSERTION_NOT_YET_VALID` | Time conditions invalid |
| `SUBJECT_CONFIRMATION` | `RECIPIENT_INVALID` / `IN_RESPONSE_TO_INVALID` | Invalid bearer/correlation |
| `AUDIENCE` | `AUDIENCE_MISMATCH` | Assertion not intended for SP |
| `REPLAY` | `ASSERTION_REPLAY` | Assertion/response ID already used per policy |
| `ATTRIBUTE_MAPPING` | `REQUIRED_ATTRIBUTE_MISSING` | Signed assertion valid yet business input missing |
| `LOCAL_AUTHORIZATION` | `TENANT_DENIED` / `APP_ROLE_MISSING` | Valid identity, lacks resource permissions |

**Do not assume the codes above are built-in exception classes**; they form a taxonomy for mapping provider failures into the audit schema. Never dump XML when debugging a reason; log safe exception types/mapped codes, trusted `registrationId`, response timing, and correlation.

**SAML `NameID`/Assertion ID can be PII/correlation secrets**: log raw values only when approved by security/privacy with retention controls. To link events, use a **local user key** mapped after validation, or governed pseudonymization. Never put raw `SAMLResponse` into central logs as evidence.

**Login authenticated ≠ authorized:** if the IdP sends `groups=["Domain Admins"]` yet the Reports app does not permit that group to view documents, log `LOGIN_AUTHENTICATED` followed by `LOGIN_POLICY_DENIED`. Never grant app `ROLE_ADMIN` solely because an IdP group is named "Domain Admins".

## 7. CAS: Audit Ticket Validation, Not Just the Callback URL

In classic CAS, the `Service Ticket (ST)` normally arrives via query parameter `ticket=ST-...` on the service callback (Spring Security `/login/cas` with the default filter). The app must verify the ticket with the CAS server and enforce `service`/proxy chain bindings per policy.

~~~text
CAS Server:
  user login, TGT/session and ST issue events

Browser:
  /login/cas?ticket=ST-EXAMPLE
  (NOT a successful authentication event)

Spring CAS validation:
  validate ticket and service
  result -> LOGIN_AUTHENTICATED or LOGIN_REJECTED
~~~

Log only `protocol=CAS`, partner key, result/reason, stage, and independent audit ID. **Never log full `/login/cas?ticket=...`**, CAS ST, Proxy Ticket (PT), Proxy-Granting Ticket (PGT), TGT, or validation responses containing PII. CAS tickets are normally single-use; `CAS_TICKET_REPLAY` is a distinct reason from `CAS_TICKET_EXPIRED` and `SERVICE_MISMATCH`.

CAS logout may clear only the local session or coordinate logout with the CAS server and services depending on mechanism/version. **Never emit an `SLO_CONFIRMED` event merely because a user clicked the Logout button.**

## 8. Logout: Multiple Completion Levels

Three statements of "logged out" are not equivalent:

1. **The app cleared its session/security context** — local logout.
2. **The SP sent a `LogoutRequest` or redirected to the IdP** — initiating federated logout.
3. **The IdP sent a valid response or back-channel action was verified** — partial SLO confirmed per protocol and actual scope.

Distinct states can be:

~~~text
LOGOUT_REQUESTED
  -> LOGOUT_LOCAL_COMPLETED
  -> LOGOUT_SLO_DISPATCHED
  -> LOGOUT_SLO_CONFIRMED | LOGOUT_SLO_REJECTED | LOGOUT_SLO_TIMEOUT
~~~

Not every flow traverses every arrow. For example, **IdP-initiated SAML SLO** starts from a validated inbound `LogoutRequest`; IdP-sent OIDC back-channel logout can revoke RP sessions directly without a browser redirect.

### Local Logout in Spring Security

Spring Security provides `LogoutFilter` and `LogoutHandler`; it normally clears `SecurityContext`, invalidates `HttpSession`, and clears CSRF/RememberMe per config. Per Spring Security docs, the default logout flow can publish **`LogoutSuccessEvent`** via `LogoutSuccessEventPublishingLogoutHandler`.

**Proper auditing:** emit `LOGOUT_LOCAL_COMPLETED` only after app cleanup finishes, not upon receiving HTTP `GET /logout` rendering a confirmation page. With CSRF enabled, a `POST /logout` with a valid token is normally the action performing logout.

### OIDC RP-Initiated Logout

`OidcClientInitiatedLogoutSuccessHandler` can redirect to the `end_session_endpoint` from the OIDC Provider's discovery metadata. Audit:

- `LOGOUT_LOCAL_COMPLETED` when the RP session has been invalidated.
- `LOGOUT_SLO_DISPATCHED` when generating the response/redirect to the OP.
- **Never treat sending the redirect as proof the IdP terminated sessions.**
- If a callback/confirmation exists, record `LOGOUT_SLO_CONFIRMED` **only when** the contract truly proves it; a browser redirect does not guarantee other RPs logged out.
- If the user closes the browser mid-flow, only local logout may have occurred.

### OIDC Back-Channel Logout

Spring Security supports `oidcLogout(...).backChannel(...)`, defaulting to `/logout/connect/back-channel/{registrationId}` in corresponding docs. The OP sends a **Logout Token**; the RP verifies signature/claims and matches sessions by `sid` or `sub`/audience.

Auditing must distinguish:

~~~text
BACK_CHANNEL_LOGOUT_RECEIVED (untrusted until validation)
BACK_CHANNEL_LOGOUT_VALIDATED
LOCAL_SESSIONS_INVALIDATED (actual count, if known safely)
BACK_CHANNEL_LOGOUT_REJECTED (signature/audience/issuer/replay)
~~~

Never log raw Logout Tokens or sensitive `sid`/`sub`. **Never treat inbound HTTP 200 as certainty that every client/session was revoked**; record the outcome of your exact implementation and policy. Spring OIDC support has version-specific requirements around session registries/cookie names; check docs for your running version.

### SAML2 Single Logout

Spring Security supports **RP-initiated** and **AP/IdP-initiated** SAML SLO depending on metadata/configuration:

- RP-initiated: local app logout → emit signed `saml2:LogoutRequest` → IdP processes → SP receives and validates `saml2:LogoutResponse`.
- IdP-initiated: SP receives `saml2:LogoutRequest`, **validates signature/issuer/destination** → invalidates local session → emits `saml2:LogoutResponse`.
- Typically exposes `/logout/saml2/slo` per docs, alongside local `POST /logout` depending on DSL configuration.

**Audit at the right step:** receiving a request is not logout success; only after signature/replay/correlation pass is the request trusted; only after local session cleanup is local logout completed; SLO is confirmed only upon receiving and validating the response per contract. If the IdP returns no response or logout covers only part of the mesh, never emit `GLOBAL_LOGOUT_COMPLETED` unconditionally.

### CAS Single Logout

The CAS server may send back-channel/front-channel logout notifications depending on protocol and deployment. Record `CAS_LOGOUT_MESSAGE_RECEIVED`, validation/correlation outcome, and local sessions invalidated; **never put raw `LogoutRequest`/XML/tickets into the event body**. Whether Spring session listeners fire depends on CAS client/filter and session store—test it for real.

## 9. Logout Audit Matrix: Avoiding "False Successes"

| Situation | Expected Event | Must Not Be Concluded |
| --- | --- | --- |
| User opens `GET /logout` confirmation | `LOGOUT_PAGE_VIEWED` (if needed) | Not yet local logout |
| User `POST /logout` and session invalidated | `LOGOUT_LOCAL_COMPLETED` | That IdP/global sessions are all destroyed |
| RP redirects to OIDC `end_session_endpoint` | `LOGOUT_SLO_DISPATCHED` | That OP definitely revoked all sessions |
| OP sends back-channel Logout Token with bad signature | `LOGOUT_SLO_REJECTED` | That sessions must be cleared on an untrusted request |
| Valid OIDC Logout Token matching 1 session | `LOGOUT_SLO_CONFIRMED`/`LOCAL_SESSIONS_INVALIDATED` | That other clients logged out |
| Valid SAML `LogoutRequest` from IdP | `LOGOUT_REQUEST_VALIDATED`, then after cleanup `LOGOUT_LOCAL_COMPLETED` | Never log success before validation |
| Valid SAML `LogoutResponse` after RP request | `LOGOUT_SLO_CONFIRMED` per scope | Does not prove all downstream systems logged out |
| Invalid/unmatched SAML `LogoutResponse` | `LOGOUT_SLO_REJECTED` | Never treat HTTP response status as proof |
| Expired CAS ticket | `LOGIN_REJECTED` if login ticket validation | Do not confuse with logout |
| Automatic session timeout | `SESSION_EXPIRED` | Cannot attribute to user-initiated logout |
| Browser closes tab | Not necessarily a server-side event | Never fabricate a logout event |
| IdP session revoked while SP cache remains | `IDP_SESSION_REVOKED` at IdP and SP event upon actual revocation | Do not assume immediate privilege rollback |

To prevent confusion, include `origin=USER|IDP|SYSTEM|ADMIN` and `logout_scope=LOCAL|RP_INITIATED|IDP_INITIATED|BACK_CHANNEL`. Only set `origin=IDP` after protocol verification; before validation, it is an **untrusted callback**.

## 10. Federation Partners Are Trust Relationships with a Lifecycle

Partner changes can open new trust boundaries or compromise all users. Examples:

- Creating/disabling/enabling a SAML `RelyingPartyRegistration` for a partner.
- Changing **SAML EntityID**, Assertion Consumer Service, Single Logout Service URL, `NameIDFormat`, or attribute mapping.
- Importing new IdP metadata and **verification signing certificates**; rotating old/new certs.
- Changing **SP signing/decryption credential references**, without copying private keys.
- Changing OIDC `issuer-uri`, `client-id`, `client-secret reference`, registered redirect URIs, logout URI, scopes, or JWKS trust config.
- Changing CAS server URL, `service` binding, proxy callbacks, or trusted proxies.
- Changing group/role/tenant mappings, automatic account linking, and MFA assurance contracts.
- Changing allowed authentication protocols, decryption/signature requirements, `clockSkew`, and session TTLs.
- Changing partner owner, contact, approval/quorum, or active/suspended/retired status.
- Changing metadata refresh schedules, cache TTLs, source allowlists, and auto-rollover policies.

**High security impact:** changing an issuer/cert/redirect URI can allow an attacker IdP to mint tokens, redirect browsers to unintended origins, swap verification keys, or grant broad roles. Therefore you need an audit trail covering **before–after–approval–deployment–rollback**, not a single "config updated" line.

### Distinguishing Human Changes from Automated Changes

| Type | Example | Who Is Accountable? |
| --- | --- | --- |
| Manual admin action | Admin changes metadata URL | Admin `actor_ref` + approval |
| API automation | GitOps pipeline deploys partner revision | Workload/service principal, commit/change ID |
| Metadata refresh | Scheduled job fetches IdP metadata | Source service/system; inspect trust/policy |
| Key rotation | IdP publishes new cert | Partner revision, certificate fingerprints, overlap |
| Emergency disable | Security disables compromised partner | Operator, incident ID, reason, expedited approval |
| Rollback | Restores old verified config | Actor/approver, from/to revision, observed outcome |

**Never attribute an actor to a user based on an `X-User` HTTP header unverified by a trusted proxy.** The actor must come from an **authenticated management identity** (admin SSO/session) or a signed/verified workload identity. For automation, record both `service_actor` and the verified change ticket/commit reference rather than pretending a human clicked it.

## 11. Partner Change Lifecycle and Required Audit Checkpoints

~~~mermaid
sequenceDiagram
    participant A as Admin / Automation
    participant M as Partner Admin Service
    participant R as Reviewer
    participant D as Config DB / outbox
    participant N as Spring nodes
    A->>M: Propose config revision v4
    M->>D: Append PARTNER_CONFIG_PROPOSED
    R->>M: Approve reviewed change
    M->>D: Append PARTNER_CONFIG_APPROVED
    M->>M: Validate issuer, cert, URLs, policy and schema
    M->>D: Commit revision v4 and audit outbox atomically
    D-->>N: Refresh approved revision
    N->>D: Record PARTNER_CONFIG_ACTIVATED / node version
    opt Health/trust check fails
        A->>M: Request rollback
        M->>D: Record rollback to v3 + reason
    end
~~~

An audit record can contain:

~~~text
change_id=chg_402
partner_key=corp_saml
old_revision=rev_3
new_revision=rev_4
changed_field=signing_cert_fingerprint
old_value_reference=fp_sha256_OLD (public cert fingerprint only)
new_value_reference=fp_sha256_NEW
actor_ref=admin_7
approver_ref=reviewer_2
approval_ticket=SEC_1042
status=ACTIVATED
effective_nodes=[sp_1,sp_2]
event_time=2026-11-07T03:00:00Z
~~~

**This example is not a real SHA-256 fingerprint.** Real systems should store the properly formatted/byte-accurate fingerprint of the reviewed **public certificate**; never store private keys, client secrets, raw metadata containing unnecessary info, or arbitrary full JSON diffs.

### Rotating Verification Keys Has Two Separate Events

- **IdP publishes a new key in metadata/JWKS** (`PARTNER_METADATA_OBSERVED`): external source, not necessarily trusted/approved yet.
- **RP/SP actually activates trust in the new key** (`PARTNER_TRUST_ACTIVATED`): an applied security decision requiring audit with from/to versions.

Seeing new metadata does not mean every Spring node is already using it. With metadata caches, startup snapshots, or cluster replication, per-node events or deployment digests may be needed to prove the **effective revision**.

### Separating Signing, Encryption, and Client Secrets

- The IdP **signing verification certificate** is a public trust anchor on the SP side.
- The SP **decryption private key** is an SP secret; the IdP only needs the public encryption certificate.
- An OIDC `client-secret` is a credential managed in a secret vault; log only the **secret reference/version**, never the value or an unsalted hash.
- CAS shared secrets/service registrations (if used in your deployment) must follow the same rule.
- When changing one key type, **never write a vague "certificate rotated"** without specifying `key_use=SIGNATURE_VERIFY|ENCRYPTION|SP_SIGN|CLIENT_AUTH`.

An allowed diff may include **fingerprints, EntityID, normalized and approved URLs, policy booleans, versions, and allowed scopes**. For URLs containing query/callback state or sensitive info, never log raw unreviewed URLs; apply dedicated field classification and sanitization.

## 12. Recommended Audit Event Schema

An audit record with fixed fields:

| Field | Meaning | Rule |
| --- | --- | --- |
| `schema_version` | Audit contract version | Mandatory, backward compatibility |
| `event_id` | Unique ID preventing duplicates on retry | Server-generated; never use tickets/tokens |
| `event_time` | When the event occurred | ISO 8601 UTC/`Instant` |
| `ingest_time` | When the collector received it | Indicates pipeline lag |
| `service` / `environment` / `instance` | Where emitted | Enumerated/approved values |
| `event_type` | Bounded taxonomy | Enum; never taken from query input |
| `protocol` | `OIDC`/`SAML2`/`CAS`/`LOCAL` | Enum |
| `stage` | `REQUEST`/`VALIDATION`/`SESSION`/`CONFIG_APPLY` | Enum |
| `outcome` | `SUCCESS`/`DENIED`/`PENDING`/`ERROR` | Never inferred from HTTP status |
| `reason_code` | Specific error class without leaking data | Allowlisted enum |
| `partner_key` | Internal partner code | Trusted registration/config only |
| `partner_revision` | Config snapshot used | Mandatory to reproduce cert/issuer errors |
| `actor_ref` / `subject_ref` | Verified identity ref/pseudonym | No raw credentials or excess PII |
| `origin` | `USER`/`IDP`/`ADMIN`/`AUTOMATION`/`SYSTEM` | Must reflect trust level |
| `interaction_id` / `trace_id` | Correlates multiple events in one flow | Independent of `state`/`nonce`/ticket |
| `change_id` / `old_revision` / `new_revision` | Partner change lifecycle | Present only on config events |
| `changed_fields` | Changed field names | Allowlist, no raw arbitrary JSON |
| `approval_ref` | Ticket/approver reference | Tamper-resistant, governed retention |
| `logout_scope` | Local/RP-initiated/IdP-initiated/back-channel | Never mark remote confirmed without proof |

### JSON Example of Successful Login

~~~json
{
  "schema_version": 1,
  "event_id": "evt_a740",
  "event_time": "2026-11-07T03:00:00Z",
  "service": "reports-sp",
  "environment": "prod",
  "instance": "sp_02",
  "event_type": "LOGIN_AUTHENTICATED",
  "protocol": "SAML2",
  "stage": "ASSERTION_VALIDATED",
  "outcome": "SUCCESS",
  "reason_code": "NONE",
  "partner_key": "corp_saml",
  "partner_revision": "rev_4",
  "subject_ref": "local_u_041",
  "interaction_id": "int_804"
}
~~~

### JSON Example of Partner Config Change

~~~json
{
  "schema_version": 1,
  "event_id": "evt_b122",
  "event_time": "2026-11-07T03:05:00Z",
  "service": "partner-admin",
  "environment": "prod",
  "event_type": "PARTNER_CONFIG_ACTIVATED",
  "protocol": "SAML2",
  "stage": "CONFIG_APPLY",
  "outcome": "SUCCESS",
  "reason_code": "NONE",
  "partner_key": "corp_saml",
  "change_id": "chg_402",
  "old_revision": "rev_3",
  "new_revision": "rev_4",
  "changed_fields": ["signing_cert_fingerprint", "metadata_url"],
  "actor_ref": "admin_7",
  "approver_ref": "reviewer_2",
  "interaction_id": "int_806"
}
~~~

**Synthetic example data**, not real user records. JSON schemas must enforce event-time source/clock semantics and field validators. An event from a pre-authenticated filter lacks a trusted subject, so `subject_ref` must be null/absent; **never take an HTTP `username` parameter as a verified actor**.

## 13. Sensitivity Rules: Never Log Directly

| Data Type | Why Never Log Raw? | Replace With |
| --- | --- | --- |
| `SAMLResponse`, decoded XML, Assertion, `NameID` | Contains identity, attributes, and login assertion | Registration ID, error code, pseudonymous subject after verify |
| CAS Service Ticket/Proxy Ticket/PGT | Short-lived credential or delegated rights | New `event_id` and protocol stage |
| OAuth authorization code, `state`, `nonce`, PKCE verifier | Front-channel correlation/credential data | Independent interaction ID |
| Access/Refresh/ID Token, Logout Token | Bearer credential, sensitive claims | Token type, validated issuer ref, safe reason |
| `Authorization`/`Cookie`/`Set-Cookie` | Credential/session hijacking | Do not capture; log route/status |
| Client secret, SP private decryption/signing key | Trust boundary breach | Secret reference/version and public cert fingerprint |
| Password/LDAP bind credential | Credential theft | Authentication outcome/validation stage |
| Full HTTP URL/query/headers/body | Can contain `ticket`/`code`/`SAMLResponse`/PII | Route template/registered endpoint ID |
| Raw `Authentication`/`principal` `toString()` | Can contain credentials, attributes, SAML XML | Explicit approved fields |
| Untrusted error messages/stack local variables | Tokens/URLs/log injection/PII | Mapped error enum + bounded safe context |

The OWASP Logging Cheat Sheet advises excluding or protecting session IDs, access tokens, passwords, encryption keys, and sensitive personal data. **Log injection** is also a risk: a user can inject CR/LF or control characters into a username/partner display name and forge "fake audit lines". Use **structured JSON logging, schema validation, output escaping, length bounds, and input classification** rather than concatenating raw values into text.

**Never compute a plain `SHA-256(email)` as a pseudonym and assume absolute anonymity**: emails often have predictable spaces susceptible to dictionary attacks. When a stable pseudonym is genuinely needed, consider **keyed HMAC with managed keys**, domain separation/rotation policies, and audit access controls; or use an approved opaque local user ID.

## 14. Correlation IDs: Never Use Credentials as Trace IDs

An OIDC login has several identifiers:
- Browser request ID from the reverse proxy.
- OAuth `state` and OIDC `nonce`.
- IdP event ID/SSO session ID.
- Spring trace/span ID.
- Local session ID.
- Audit `interaction_id`.

**Do not conflate them.** In particular, `state`, CAS tickets, JWT `jti`, or raw SAML Assertion IDs must not become public correlation IDs in logs. One sound design:

~~~text
trace_id (OpenTelemetry) = generated trusted observability identifier
interaction_id = independent random application flow id
event_id = unique identifier for each audit event
partner_key = internal configured registration ID
user_ref = local opaque identity key only AFTER authentication
~~~

If IdP/SP linking is needed, build a **bounded, protected mapping** between the IdP event ID/transaction reference and the SP interaction ID; never carry bearer tickets/tokens across log pipelines.

### Clocks and Ordering

Each event should include `event_time` (when it occurred), `ingest_time` (collector receipt), `instance`, and (if available) `sequence` or monotonic ordering within one producer. Multi-node logs can experience clock skew or delayed delivery. **Never treat ingest order as absolute event order.**

Write ISO 8601 UTC timestamps; monitor NTP/chrony node offsets and audit pipeline lag. During incidents, the timeline must distinguish **IdP authenticated** before **SP validated callback**, even if events arrive out of order at the SIEM.

## 15. Spring Security: Built-In Authentication Events

Spring Security Servlet **Authentication Events** docs describe `AuthenticationSuccessEvent` and `AbstractAuthenticationFailureEvent`, emitted via `AuthenticationEventPublisher`; `DefaultAuthenticationEventPublisher` can bridge to Spring's `ApplicationEventPublisher`:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;

@Configuration
public class AuthenticationAuditWiring {

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher applicationEventPublisher) {
        return new DefaultAuthenticationEventPublisher(
                applicationEventPublisher);
    }
}
~~~

This is a **Spring project fragment**, requiring Spring dependencies and real security config; it will not run with plain `javac`. You can listen with:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.LogoutSuccessEvent;

@Component
public class FederationAuthenticationAuditListener {

    private final SecurityAuditSink sink;

    public FederationAuthenticationAuditListener(SecurityAuditSink sink) {
        this.sink = sink;
    }

    @EventListener
    public void onAuthenticationSuccess(AuthenticationSuccessEvent event) {
        sink.record("LOGIN_AUTHENTICATED", "SUCCESS", "NONE");
    }

    @EventListener
    public void onAuthenticationFailure(AbstractAuthenticationFailureEvent event) {
        sink.record("LOGIN_REJECTED", "DENIED",
                mapToAllowedReasonCode(event.getException()));
    }

    @EventListener
    public void onLogoutSuccess(LogoutSuccessEvent event) {
        sink.record("LOGOUT_LOCAL_COMPLETED", "SUCCESS", "NONE");
    }

    private String mapToAllowedReasonCode(Exception error) {
        // Only return allowlisted reason enums; never log error.getMessage().
        return error.getClass().getSimpleName().equals("BadCredentialsException")
                ? "BAD_CREDENTIALS" : "AUTHENTICATION_FAILED";
    }
}
~~~

In this fragment, **`SecurityAuditSink` is an application-defined interface**, **not a standard Spring class**. Mapping exceptions by simple class name is illustrative only; production should use a typed allowlist over approved exception classes so implementation details do not leak.

**Critical note on completeness:**

- `AuthenticationEventPublisher` attaches primarily to `AuthenticationManager`/`ProviderManager`; **it does not guarantee every OIDC/SAML/CAS login, pre-auth request, redirect, and all SLO paths emit the exact same event** under every config.
- `DefaultAuthenticationEventPublisher` maps many exception types, yet per the docs it uses **exact exception class matching**, so subclasses and custom exceptions may need extra mappings or a catch-all.
- `LogoutSuccessEvent` tracks Spring logout processing; **it does not by itself prove OIDC/SAML global logout was confirmed**.
- Authentication success/failure **differs from** authorization denied. Instrument 403/resource access decisions separately (with a privacy policy and sampling/cost strategy).

For web federation, **test the actual behavior** of `oauth2Login(...)` and `saml2Login(...)` success/failure handlers, CAS filter/provider, and logout handlers. When the publisher does not cover a stage, instrument an appropriate **authentication success/failure handler or provider-specific hook**, avoiding duplicates or logging "success before validation".

## 16. Authentication Success/Failure Handlers: Avoid Breaking Default Flows

Servlet `AuthenticationSuccessHandler`/`AuthenticationFailureHandler` can add auditing around browser logins. However, replacing the handler in `oauth2Login` or `saml2Login` can accidentally **drop `SavedRequestAwareAuthenticationSuccessHandler` behavior, session strategies, or valid redirects**.

A safe pattern is **delegation**:

~~~java
// Spring Security integration fragment; not standalone Java.
AuthenticationSuccessHandler savedRequestHandler =
        new SavedRequestAwareAuthenticationSuccessHandler();

AuthenticationSuccessHandler auditedSuccess =
        (request, response, authentication) -> {
            auditSink.recordVerifiedLogin(authentication, request);
            savedRequestHandler.onAuthenticationSuccess(
                    request, response, authentication);
        };

// .oauth2Login(oauth -> oauth.successHandler(auditedSuccess))
// or a protocol-specific success handler with same delegation rules.
~~~

Still, if `auditSink` throws an exception, login behavior can change; define an explicit failure policy. **Never** log raw `authentication.getCredentials()`, `getDetails()`, or `request.getParameterMap()`. Record identity **after** provider validation, taking registration/issuer from the verified security context.

**Count one login once:** if you both listen to `AuthenticationSuccessEvent` and install a success handler, you may emit **two audit records for the same flow**. Designate one canonical source for `LOGIN_AUTHENTICATED`, or use distinct phases and `event_id`/`interaction_id` to deduplicate/aggregate.

## 17. Spring Boot Actuator Auditing

Spring Boot Actuator provides an auditing framework via `AuditEventRepository`. Per Boot docs:

- Providing an `AuditEventRepository` bean enables auditing.
- By default with Spring Security, auditing records certain **authentication success/failure and access-denied** events.
- `InMemoryAuditEventRepository` is only convenient for **development**, unsuitable for durable production auditing.
- You can supply a custom `AuditEventRepository` and publish `AuditApplicationEvent` for business/config changes.
- To customize security event mapping, `AbstractAuthenticationAuditListener` and `AbstractAuthorizationAuditListener` are available.

Illustrative example publishing a **custom audit event** when a partner config is approved:

~~~java
import java.util.Map;
import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.stereotype.Service;

@Service
public class PartnerAuditService {
    private final AuditEventRepository auditRepository;

    public PartnerAuditService(AuditEventRepository repository) {
        this.auditRepository = repository;
    }

    public void recordApprovedChange(
            String adminReference,
            String partnerKey,
            String revision) {
        AuditEvent event = new AuditEvent(
                adminReference,
                "PARTNER_CONFIG_APPROVED",
                Map.of("partnerKey", partnerKey,
                       "newRevision", revision));
        auditRepository.add(event);
    }
}
~~~

The snippet **requires the Spring Boot Actuator dependency** and is a fragment containing no approval logic or transactional consistency. `adminReference`, `partnerKey`, and `revision` must be verified/allowlisted identifiers; never pass raw HTTP params or raw metadata into the `Map`. Never store secret values/diffs in audit events.

**Note:** Actuator auditing, Spring Security application events, and custom SIEM event sinks **are not completely identical**; you may use one or combine them while avoiding duplicates. Exposing `/actuator/auditevents` (if present in your version) must be restricted and tested; never expose event data to the Internet.

## 18. Partner Audits Must Bind to Transactions and Config Revisions

For trust-configuration changes, calling `auditRepository.add` **only after commit** can lead to:

~~~text
DB config commit SUCCESS
Audit insert FAIL
=> partner trust changed, but no durable audit evidence
~~~

Recording audit only before commit also carries risk:

~~~text
Audit insert SUCCESS
DB config rollback
=> audit claims ACTIVATED though trust never changed
~~~

**Transactional outbox** is a sound pattern:

1. Begin transaction on the configuration database.
2. Validate permissions/approval/expected revision.
3. Persist the new partner config revision.
4. Persist an **outbox audit event** with `event_id`/`old_revision`/`new_revision` inside the same transaction.
5. Commit or roll back **both together**.
6. An async worker ships outbox events to the broker/SIEM, retrying with backoff.
7. Consumers deduplicate by `event_id` (at-least-once delivery).
8. Monitor outbox backlog/age, ingest errors, and reconciliation.

Pseudocode example:

~~~text
@Transactional
activatePartnerChange(changeId, expectedOldRevision):
    requireAuthenticatedActor()
    requireApprovedChange(changeId)
    requireFourEyesIfRequired()
    old = partnerStore.loadForUpdate(partnerKey)
    assert old.revision == expectedOldRevision
    new = validateNewConfigAndCreateRevision(old, changeId)
    partnerStore.save(new)
    outboxStore.append(
        eventId = randomUnique(),
        type = PARTNER_CONFIG_ACTIVATED,
        actorRef = trustedActor,
        partnerKey = new.partnerKey,
        oldRevision = old.revision,
        newRevision = new.revision,
        changedFields = auditedAllowlist,
        occurredAt = serverUtcNow)
    COMMIT
~~~

**This is pseudocode, not a complete Spring bean**. A DB transaction does not automatically cover an IdP metadata server, Kubernetes rollout, or remote SIEM; you need **two event types**—"revision committed" and "effective on node(s)"—along with pending/failed/rolled-back states.

### Do Not Promise Exactly-Once

Brokers/collectors normally provide **at-least-once** delivery; retries can create duplicates. Keep `event_id` stable across retries with idempotency/dedup at sink and consumer; audit events must be append-only while transport duplicates are handled cleanly. Never generate a new `event_id` on each retry for the same logical event.

### What If the Audit Sink Fails?

There is no single universal answer:
- For **critical trust-config changes**, failing closed or requiring a durable local outbox before commit may be the right policy.
- For **runtime logins**, waiting synchronously on a remote SIEM can cause outages; write to a durable local buffer/queue with health alerts/backpressure and defined retention.
- If **even one required security event cannot be stored** per governance, you may need to block high-risk operations or trigger a degraded-mode policy.
- Never silently catch all errors, continue, and still report "audit complete".
- Never log raw credentials to "compensate" for a disconnected SIEM.

Define RPO/RTO, maximum lost events, retry, dead-letter policies, and incident procedures for audit pipeline outages.

## 19. Audit Log Injection and Field Classification

A message like:

~~~text
INFO login rejected user=guest
SUCCESS user=admin    <-- injected newline by attacker
~~~

can occur if logs write raw `username`/`partner displayName` containing CR/LF into text. To prevent it:

1. Use a **JSON structured logger/encoder** with escaping.
2. **Bound length, character set, and trust source** of every field.
3. Use audit enums for `event_type`, `stage`, `outcome`, and `reason_code`.
4. Pull user/partner identifiers from internal canonical IDs rather than request bodies.
5. Never let untrusted input control message templates or JSON keys.
6. Before SIEM ingestion, drop or sanitize all sensitive HTTP attributes (headers, queries, bodies).
7. Enforce field schema validation and reject schema-violating fields with safe warnings rather than dropping whole events when one field is invalid.
8. Test CR, LF, Unicode control characters, log delimiters, oversized strings, UTF-8 encoding, JSON escaping, and ID injection.
9. Protect collection endpoints with mTLS/workload identity and rate limits; never allow Internet clients to POST fake audits.
10. Record source authenticity and distinguish untrusted callbacks from trusted events.

**Parameterized SLF4J logging does not automatically prevent all CRLF log injection** if the encoder prints raw strings containing newlines. OWASP recommends structured output paired with proper canonicalization/validation.

## 20. Standalone Java 17: An Audit Event Containing Only Allowed Fields

The program below uses **JDK 17 only**, with no Spring/IdP/network. It demonstrates building an **audit model with event enums and a field allowlist**, distinguishing login success, local logout, and partner changes, and blocking inputs containing newlines. The code **does not log in via OIDC/SAML, verify tickets, or send to a SIEM**; it simulates the data-normalization layer once the app has a trust context.

Create file **`FederationAuditDemo.java`**:

~~~java
import java.time.Instant;
import java.util.List;

public class FederationAuditDemo {

    enum EventType {
        LOGIN_AUTHENTICATED, LOGIN_REJECTED,
        LOGOUT_LOCAL_COMPLETED, PARTNER_CONFIG_ACTIVATED
    }

    enum Outcome { SUCCESS, DENIED }

    record AuditEvent(
            Instant time,
            EventType type,
            String partnerKey,
            String actorRef,
            Outcome outcome,
            String correlationId,
            String changedField) {}

    static String safeId(String text) {
        if (text == null ||
                !text.matches("[A-Za-z0-9_-]{1,32}")) {
            return "REDACTED";
        }
        return text;
    }

    static String safeChangedField(String field) {
        return switch (field) {
            case "signing_cert_fingerprint",
                 "metadata_url",
                 "client_id",
                 "role_mapper" -> field;
            default -> "NONE";
        };
    }

    static String render(AuditEvent event) {
        return event.time() + " " + event.type()
                + " partner=" + safeId(event.partnerKey())
                + " actor=" + safeId(event.actorRef())
                + " outcome=" + event.outcome()
                + " corr=" + safeId(event.correlationId())
                + " changed=" + safeChangedField(
                    event.changedField());
    }

    public static void main(String[] args) {
        Instant start = Instant.parse(
                "2026-11-07T03:00:00Z");

        List<AuditEvent> events = List.of(
                new AuditEvent(start,
                    EventType.LOGIN_AUTHENTICATED,
                    "corp_oidc", "user_42",
                    Outcome.SUCCESS, "int_100", "none"),

                new AuditEvent(start.plusSeconds(60),
                    EventType.LOGOUT_LOCAL_COMPLETED,
                    "corp_oidc", "user_42",
                    Outcome.SUCCESS, "int_101", "none"),

                new AuditEvent(start.plusSeconds(120),
                    EventType.PARTNER_CONFIG_ACTIVATED,
                    "corp_saml", "admin_7",
                    Outcome.SUCCESS, "chg_402",
                    "signing_cert_fingerprint"),

                new AuditEvent(start.plusSeconds(180),
                    EventType.LOGIN_REJECTED,
                    "evil\nLOGIN_AUTHENTICATED", "guest\nadmin",
                    Outcome.DENIED, "int_102", "none")
        );

        StringBuilder log = new StringBuilder();
        for (AuditEvent event : events) {
            String line = render(event);
            log.append(line).append('\n');
            System.out.println(line);
        }

        // Fake secrets simulate data present elsewhere in a request.
        String sampleToken = "FAKE-ACCESS-TOKEN-NEVER-LOG";
        String sampleTicket = "ST-FAKE-TICKET-NEVER-LOG";

        boolean noSecrets =
                !log.toString().contains(sampleToken)
                && !log.toString().contains(sampleTicket);

        System.out.println("No credentials in audit: "
                + noSecrets);

        System.out.println("CRLF input rejected: "
                + log.toString().contains(
                    "partner=REDACTED actor=REDACTED"));
    }
}
~~~

Compile/run:

~~~bash
javac FederationAuditDemo.java
java FederationAuditDemo
~~~

**Exact stdout:**

~~~text
2026-11-07T03:00:00Z LOGIN_AUTHENTICATED partner=corp_oidc actor=user_42 outcome=SUCCESS corr=int_100 changed=NONE
2026-11-07T03:01:00Z LOGOUT_LOCAL_COMPLETED partner=corp_oidc actor=user_42 outcome=SUCCESS corr=int_101 changed=NONE
2026-11-07T03:02:00Z PARTNER_CONFIG_ACTIVATED partner=corp_saml actor=admin_7 outcome=SUCCESS corr=chg_402 changed=signing_cert_fingerprint
2026-11-07T03:03:00Z LOGIN_REJECTED partner=REDACTED actor=REDACTED outcome=DENIED corr=int_102 changed=NONE
No credentials in audit: true
CRLF input rejected: true
~~~

### Code Explanation

- `Instant` gives audit logs deterministic UTC timestamps for the same input.
- `EventType` and `Outcome` are enums; callers cannot inject arbitrary `event_type` strings into the record.
- `safeId` permits only `[A-Za-z0-9_-]` up to 32 chars; non-conforming strings become **REDACTED** instead of printing multiline text.
- `safeChangedField` allows only approved **field names**; no secret values, raw diffs, PEMs, or certificate bodies.
- `LOGOUT_LOCAL_COMPLETED` is never renamed to global logout.
- `PARTNER_CONFIG_ACTIVATED` records the changed field name **`signing_cert_fingerprint`**, with no private keys.
- Two fake credentials exist in the demo yet are **never passed into `AuditEvent`**. `No credentials in audit: true` proves only that this example's render function did not print those two fake strings, **not that a real system's access logs/APM are clean**.
- `CRLF input rejected: true` proves the malicious partner/actor strings were rejected by the regex.
- In production, **never rely on regex alone**: enforce schemas, source identity verification, JSON serialization, persistence, access control, deduplication, and reconciliation.

**For real applications:** always derive `actor_ref` from a **verified** `SecurityContext`, `partner_key` from an approved registration/config, and `correlation_id` server-side. If a client passes `actorRef=user_42` in an HTTP parameter, even if it passes the regex, **never treat it as a trusted actor**.

## 21. End-to-End Test Matrix

| ID | Scenario | Expected Audit Outcome |
| --- | --- | --- |
| L01 | Valid OIDC signature/issuer login, session established | `LOGIN_AUTHENTICATED` and session stage if applicable |
| L02 | OIDC callback received `code` before exchange | **Do not** emit login success before verification |
| L03 | Invalid OIDC state/nonce | `LOGIN_REJECTED`, bounded error code |
| L04 | OIDC token `iss` differs from IdP | Reject and never trust fake partner context |
| L05 | Invalid SAML signature | `LOGIN_REJECTED`/`SIGNATURE_INVALID`; no raw assertion |
| L06 | SAML decryption with wrong key | `DECRYPTION_FAILED`, not authenticated |
| L07 | SAML expired/NotBefore | Time-stage reason; do not print full XML |
| L08 | Valid SAML Assertion yet missing required tenant | `LOGIN_POLICY_DENIED` or explicit attribute-contract stage |
| L09 | SAML group Domain Admins lacks approved app role | Do not grant `ROLE_ADMIN`; audit deny on role-protected access |
| L10 | Valid CAS ST, matching service | Login authenticated after ticket validation |
| L11 | CAS ST replay | `LOGIN_REJECTED`/`TICKET_REPLAY` |
| L12 | CAS ST in query string | Ingress/APM/app audits contain **no** raw ticket |
| L13 | Users A/B with same username at two IdPs | Audit distinguishes trusted partner/issuer namespace |
| L14 | MFA fails at IdP, SP receives no callback | IdP audits failure; SP emits no login success |
| L15 | LDAP/AD account disabled at IdP | Login rejected per observed policy; never log password |
| L16 | Spring auth succeeds yet endpoint returns 403 | Separate authn success from authz deny |
| L17 | Login retried/redirected multiple times | Do not emit duplicate unverified login successes |
| O01 | `GET /logout` renders confirmation only | Do not emit local logout completed |
| O02 | `POST /logout`, session invalidated | `LOGOUT_LOCAL_COMPLETED` |
| O03 | OIDC RP-initiated redirect to OP | `LOGOUT_SLO_DISPATCHED`, not yet confirmed |
| O04 | Invalid OIDC back-channel Logout Token | `LOGOUT_SLO_REJECTED`, do not revoke arbitrarily |
| O05 | Valid OIDC back-channel matching sid/sub | Audit actual session revocation per scope |
| O06 | Valid SAML SP-initiated SLO response | `LOGOUT_SLO_CONFIRMED` per correlation |
| O07 | Bad-signature SAML IdP-initiated logout | Reject; session action follows verified policy |
| O08 | Valid SAML IdP-initiated logout | Local session cleared, signed response per flow |
| O09 | CAS back-channel message for wrong service | Reject/ignore per validator, not confirmed |
| O10 | Session timeout | `SESSION_EXPIRED`, not `USER_LOGOUT` |
| O11 | Browser closes tab | Never fabricate a local logout event |
| O12 | IdP logs out only one SP | Never claim all apps logged out |
| P01 | Admin proposes adding a new IdP | `PARTNER_CONFIG_PROPOSED` |
| P02 | Reviewer approves | `PARTNER_CONFIG_APPROVED` + approver ref |
| P03 | Missing approval, attempt to enable partner | Operation denied + change audit |
| P04 | Rotate IdP signing public cert | Old/new public fingerprint refs + key use |
| P05 | Rotate SP private decryption key | Log secret reference/version, **never bytes** |
| P06 | Change OIDC redirect URI to unknown domain | Validation/approval denies |
| P07 | Role mapper widened to broad admin | Audit diff field name/approval, high-severity alert |
| P08 | New metadata downloaded yet not activated | `OBSERVED` distinct from `ACTIVATED` |
| P09 | Revision DB committed while SIEM down | Outbox persists and retries; zero lost events |
| P10 | Deployed v4 to node A while node B still on v3 | Per-node effective revision detectable |
| P11 | Rollback v4→v3 | `PARTNER_CONFIG_ROLLED_BACK` and links |
| P12 | Admin tries to delete/modify old event | Permission denied + access-violation audit |
| S01 | Raw `Authorization`/`Cookie`/`SAMLResponse` in HTTP input | Absent from audit output, WAF/APM/logs |
| S02 | Username/partner CRLF injection | Structured escaping/allowlist, zero forged events |
| S03 | Very long error text | Truncated/omitted, event still logs reason code |
| S04 | Duplicate delivery on retry | Same `event_id`, consumer deduplicates |
| S05 | SIEM/collector outage | Alert, buffered delivery per declared durability |
| S06 | Clock skew across IdP/SP nodes | UTC/instance metadata aids investigation without misattribution |
| S07 | Actor source spoofed via `X-User` header | Never recorded as trusted actor |
| S08 | Audit endpoint exposed publicly | Endpoint protected, access control tested |
| S09 | Retention expires | Data deleted/archived per policy, legal holds preserved |
| S10 | Incident requires querying by change ID | Links change–approval–deploy–auth failures |

**Tests pass only when verifying both emitters and real sinks**, not merely mocking `auditSink.record(...)`. For callback URLs carrying codes/tickets, inspect reverse proxy/WAF/APM logs separately; for SAML POSTs, check HTTP body capture. Never use production tokens, signing keys, or real emails in tests.

## 22. Investigation Scenario: Logins Suddenly Fail After Rotating IdP Signing Certificate

Hypothetical timeline:

~~~text
03:00  PARTNER_CONFIG_APPROVED change=chg_402 rev_3->rev_4
03:02  PARTNER_CONFIG_ACTIVATED node=sp_1 revision=rev_4
03:03  PARTNER_CONFIG_ACTIVATED node=sp_2 revision=rev_3 (stale)
03:04  LOGIN_REJECTED node=sp_2 reason=SIGNATURE_INVALID
03:05  LOGIN_AUTHENTICATED node=sp_1 revision=rev_4
~~~

During investigation:

1. Confirm UTC event timestamps, clock sync, and event ingestion lag.
2. Query `partner_key`, `change_id`, `new_revision`, and `instance`.
3. Compare reviewed **trust anchor public certificate fingerprints**, without printing PEMs/private keys.
4. Check metadata refresh/failover and immutable config snapshots on each pod.
5. Check that issuer/EntityID/audience/ACS did not change unexpectedly.
6. If rollback is required, record `PARTNER_CONFIG_ROLLED_BACK` with actor/approval/incident.
7. Verify login success/failure after rollout with a synthetic test identity.
8. Never "quick-fix" by disabling signature validation; that is a severe security change that must be audited and normally rejected.

**An HTTP 302 access log cannot explain the root cause.** Only the `partner_revision + instance` pair in the audit record reveals failures occur solely on the un-updated node.

## 23. Investigation Scenario: User Claims They Logged Out Yet API Still Works

A possible timeline:

~~~text
10:00  LOGOUT_REQUESTED origin=USER
10:00  LOGOUT_LOCAL_COMPLETED app=reports-sp
10:00  LOGOUT_SLO_DISPATCHED protocol=OIDC
10:01  No verified OP confirmation observed
10:02  API request accepted using existing Access Token (not yet expired)
~~~

**Do not jump to concluding the logout implementation is broken**: Spring's browser session, the IdP SSO session, and the **API Access Token** have different lifetimes and revocation models. Ask:

- Was the local session invalidated?
- Did the OP `end_session` request actually complete?
- Is back-channel logout configured/validated and matching sessions?
- Does the API validate JWTs offline until `exp` or via introspection/revocation?
- Does the user hold a refresh token or another client?
- Does security policy require immediate access termination or within a defined SLA?
- Is there an `sid`/`sub`/audience mismatch preventing logout notifications from matching the local session?

**Audits must state the proven scope and outcome**, never emitting `GLOBAL_LOGOUT_COMPLETED` just because the browser landed on a "Logged out" page.

## 24. Anomaly Detection and Alerting

Alerts can be defined on event series:

| Rule | Signal | Caution |
| --- | --- | --- |
| Spike in `LOGIN_REJECTED` due to `SIGNATURE_INVALID` after config change | Wrong cert or IdP spoofing attack | Correlate approved rev/deploy; never log assertion |
| Multiple `LOGIN_REJECTED` for the same partner | Provider outage, abuse, or claims issue | Rate-limit alerts/sampling; never expose username |
| Repeated failed logins on one `actorRef` | Credential attack or account lockout | Pre-auth failures may lack a verified actor |
| Spike in SAML replay detection | Replay attempts or duplicate POSTs | Check replay store/network retries |
| Many `LOGOUT_SLO_DISPATCHED` without confirmation | IdP SLO failure/blocked callback | Some flows do not expect confirmation |
| Sudden change in metadata signing fingerprint | Cert rotation or compromise | Cross-check approved metadata/certificate pinning |
| Partner issuer/redirect URI changed outside change window | Unauthorized trust change | Escalate to security |
| Partner config activated on a subset of nodes | Rollout drift/metadata cache | Compare effective revision per instance |
| Audit queue backlog/age rising | SIEM/broker outage | Durability, retries, DLQ/alerts |
| Audit volume drops abnormally to 0 | Event source disabled or broken pipeline | Canary synthetic event |
| Same actor and approver on high-risk change | Four-eyes policy violation | Review approval/trust source |
| Repeated emergency rollbacks | Config quality/trust instability | Change review and automated tests |

**Never create metric labels from raw user IDs/emails/tokens**; avoid high cardinality and privacy disclosures. Aggregate by `event_type`/`partner_key`/`stage`/`reason_code`/`environment`, then drill down in a permission-controlled audit store when needed.

## 25. Audit Quality, Retention, and Access Control

For audits to remain usable in long-term investigations:

- **Integrity**: append-only events, restricted updates/deletes; any admin modifying access policy must also be audited.
- **Availability**: HA collectors/queues/DB, retries, idempotency, and backlog monitoring.
- **Confidentiality**: encryption in transit/at rest, RBAC/ABAC for queries, export limits, PII redaction.
- **Retention**: policy aligned with legal/organizational obligations; do not retain indefinitely by default.
- **Subject access/privacy**: query/delete per applicable regulations, honor valid legal holds, never falsify history.
- **Clocks**: UTC `Instant`, trusted time sources, ingestion timestamps, and node IDs.
- **Schema evolution**: `schema_version`, backward-compatible field additions; never change event semantics while keeping the same type/version.
- **Security of auditing**: audit agents, SIEM API tokens, and storage credentials rotated, never appearing inside audit contents.
- **Operational resilience**: bounded queues, backpressure, DLQs, dead-letter access reviews, disk-full alerts.
- **Change provenance**: source system, actor/authenticated workload, approval ticket, config commit digest, effective revision.
- **Privacy by design**: omit IP/device fingerprints/geolocation unless required by use case; if required, classify as personal data with explicit retention/access controls.

If a field is redacted from an event, **record a reason code indicating a field was stripped**, rather than stashing the stripped raw value in a hidden payload "for debugging later".

## 26. Anti-Patterns to Avoid

### A. Relying on HTTP 200/302 Alone to Count Successful Logins

302 may redirect to an error page, retry, or login start; count only after Spring authentication success/verified session.

### B. Logging Full Request URLs or `Authentication.toString()`

Callbacks can carry CAS ST/OIDC `code`/`state`/`SAMLResponse`, and principals can carry attributes/PII. Use approved fields and independent correlation IDs.

### C. Treating `LogoutSuccessEvent` as Proof of Global SLO

Spring logout events normally reflect **local logout**; remote IdP/SP sessions require separate observation/validation.

### D. Logging Only "Updated Partner" Without Old/New Revisions

Makes it impossible to trace which cert, issuer, or role mapper broke things. Record field names, revision/fingerprint references, actor, approval, and effective nodes—never secrets.

### E. Using an In-Memory Audit Repository in Production

Pod restarts/rollouts wipe evidence and violate retention. Spring Boot recommends `InMemoryAuditEventRepository` for development; production requires a durable implementation.

### F. Catching All Audit Exceptions and Reporting Success Anyway

A broken audit pipeline can drop critical security events. Use a durable queue/outbox, health alerts, and a risk-appropriate failure policy.

### G. Emitting One Event per Handler and Double-Counting Logins

`AuthenticationEventPublisher`, success handlers, and Boot auditing can all observe one flow. Design canonical sources, `event_id`, and deduplication.

### H. Feeding Raw User Input into SIEM as Trusted Events

CRLF/log injection, actor spoofing, and unauthorized partner metadata must be classified/validated; **never let an HTTP parameter decide the trusted actor**.

### I. Using Tokens or `state` as Correlation IDs

These are sensitive values. Generate independent random IDs rather than shipping credentials through observability.

### J. Auditing Only Config Proposals Without Recording Revision Activation

Approval does not equal deployment. One node may still run stale config; audits need effective revision/rollback events.

### K. Logging Secret Diffs or Certificate Private Keys

Log only **field names, public certificate fingerprints, and secret references/versions**—never raw secrets/PEMs, hashed low-entropy client secrets, or raw Assertions.

## 27. Operations Handoff Checklist

- [ ] Distinct event taxonomy exists for login start, callback, authentication success/failure, and authorization denied.
- [ ] IdP-side authentication and Spring-side validated login are distinguished.
- [ ] OIDC `code`/`state`, `SAMLResponse`, and CAS tickets never leak into ingress/app/APM/SIEM logs.
- [ ] Trusted actor/subject is set only after authentication or management workload verification.
- [ ] Partner registration key, config revision, environment, service/instance, UTC event time, and interaction ID are recorded.
- [ ] `AuthenticationEventPublisher`/Spring events used properly; custom exception mappings tested.
- [ ] Spring Boot Actuator auditing uses a durable production repository, not `InMemoryAuditEventRepository`.
- [ ] No double-counting when both event listeners and success handlers are active.
- [ ] Local logout, SAML SLO, OIDC RP/back-channel logout, and CAS logout audited at distinct stages.
- [ ] Remote/global logout is never marked completed without validated evidence.
- [ ] Session timeouts are never counted as user-initiated logouts.
- [ ] Partner config proposed/approved/activated/rolled-back all emit audit records.
- [ ] Changing trust anchors/certs/issuers/redirect URIs/role mappers is a high-risk change with approval/audit.
- [ ] Old/new revisions and changed-field allowlists logged; zero raw secrets/private keys.
- [ ] Metadata observed is distinguished from trusted revision activated.
- [ ] Effective config revision verified per node/tenant when required.
- [ ] Partner config and audit outbox persisted atomically in a DB transaction.
- [ ] SIEM retries are idempotent by `event_id`, with backlog/dead-letter monitoring.
- [ ] Structured JSON logging, output escaping, and CRLF/oversized-input tests verified.
- [ ] Raw HTTP headers/queries/params never used as actor or event type.
- [ ] Audit endpoints and data enforce proper RBAC, encryption, retention, and legal holds.
- [ ] Logs and metrics contain no raw user identifiers/PII outside approved use cases.
- [ ] Tested 401/403, wrong issuer/signature, replay, failed SLO, and change rollback E2E.
- [ ] Synthetic canary events exist to detect a silent audit pipeline.
- [ ] Investigation runbook supports querying by partner/revision/instance/correlation ID.
- [ ] Practiced incident response if a secret ever leaks into logs, including revoke/purge/notify as needed.

## 28. Official Documentation and References

1. [Spring Security — Authentication Events](https://docs.spring.io/spring-security/reference/servlet/authentication/events.html): `AuthenticationEventPublisher`, `AuthenticationSuccessEvent`, `AbstractAuthenticationFailureEvent`, exception mappings.
2. [Spring Security — Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): `LogoutFilter`, `LogoutHandler`, `LogoutSuccessEvent`, default local logout, and customization.
3. [Spring Security — OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html): local logout, `OidcClientInitiatedLogoutSuccessHandler`, and OIDC back-channel.
4. [Spring Security — SAML2 Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): RP/IdP-initiated logout, `Saml2LogoutRequestFilter`, `Saml2LogoutResponseFilter`, signatures, and status.
5. [Spring Security — OAuth2 Login Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): verified OIDC/OAuth2 client authentication stages.
6. [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): SAML response validation, subject, and trust configuration.
7. [Spring Security — CAS Authentication Filter Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/cas/web/CasAuthenticationFilter.html): CAS ticket handling and service validation.
8. [Spring Boot Actuator — Auditing](https://docs.spring.io/spring-boot/reference/actuator/auditing.html): `AuditEventRepository`, security audits, custom `AuditApplicationEvent`, `InMemoryAuditEventRepository` for development only.
9. [Spring Security — LogoutSuccessEvent Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/event/LogoutSuccessEvent.html): event reflecting logout.
10. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): event attributes, data minimization, protection, log injection, integrity/retention.
11. [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session IDs, logout, and lifecycle.
12. [OWASP — SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): validate issuer/signature/audience, prevent replay.
13. [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): token leakage, redirect/client security, modern OAuth threat model.
14. [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): OIDC logout request/OP endpoint contract.
15. [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): Logout Token validation, session correlation.
16. [OASIS SAML2 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): SAML Web SSO/Single Logout profile semantics.
17. [Oracle Java 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): audit event times in UTC.
18. [OpenTelemetry Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/): trace/log correlation concepts, avoid credential attributes.

**Conclusion:** Federation audit logs are not a pile of raw HTTP logs. They are a **sequence of events with trusted sources, explicit states, and data protection**: logins recorded after protocol validation, logouts with realistic local/SLO scope, and partner changes following **proposed → approved → activated → rollback** alongside trust-config revisions. Leverage Spring Security authentication/logout events and Spring Boot auditing, while actively instrumenting SAML/OIDC/CAS stages, config changes, and pipeline durability. With **allowlisted structured fields, append-only durable storage, outbox/retries, UTC correlation, secrets minimization, and E2E negative tests**, operations teams can investigate "who did what, when, with which partner, and under which config" without introducing another token/private-key leak vector.