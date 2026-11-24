# Periodic Review of Access Rights, Shared Data, and Partner Configurations

> **Topic:** Spring Security – federation. **Group:** Deployment and operations. This standalone Knowledge unit explains how to design, execute, and verify **periodic reviews** for federated sign-in systems: OpenID Connect (OIDC)/OAuth 2.0, SAML 2.0, CAS, and directory/SCIM connections where used. The three questions that must be answered **with factual evidence** are: **Who still has access to what? What identity data is being exchanged with whom, and for what purpose? Does each partner/key/callback configuration currently match the trust contract and remain secure?** The focus is on operating **Spring Security Servlet, Java 17+**, least privilege policy, data minimization, JML (joiner–mover–leaver), change management, and auditing. The cadences and day counts in the examples are **illustrative policies**, not statutory deadlines or Spring defaults.

## 1. Learning Outcomes

After completing this unit, learners can:

1. Build a **federation inventory** with owner, IdP/OP, RP/SP, application, tenant, registrationId, issuer/entityID, metadata URL, audience, ACS/redirect URI, key/cert, scopes/attributes, provisioning/deprovisioning, and change log.
2. Distinguish **federated authentication** (who the user is) from **business authorization** (what the user can do), and identify permission layers: IdP account, directory groups, claims/tokens, authority mapping, application authorization, resource/tenant permissions, API clients, and sessions.
3. Establish a risk-based review cadence (privileged, sensitive data, new partner, prolonged inactivity) and **immediate triggers upon significant events** (leaver, compromise, key leak, issuer/callback change, or increased data sharing).
4. Compare **actual effective access** with **approved desired access**, identifying orphan accounts, stale group grants, role creep, SoD conflicts, shared identities, expired contractors, and service accounts with unused permissions.
5. Review SAML/OIDC **attribute release**, scopes/consent, UserInfo, profile/group values, SCIM mappings, and retention; verify purpose, legal/contract basis, minimization, visibility/receiver, and subject notice where appropriate.
6. Verify partner trust configuration: signed SAML metadata, IdP certificates, `validUntil`/`cacheDuration`, OIDC discovery `issuer`/`jwks_uri`, allowed redirect URIs, logout endpoints, algorithms, SP signing/decryption credentials, TLS/PKIX, secret expiry, and trust anchors.
7. Implement a **requester – independent approver – implementer – verifier** workflow with snapshot/diff/approval/closure evidence, prohibiting owners from self-certifying their own privileged access.
8. Write Spring Security tests to prove runtime issuer/audience/role/tenant enforcement remains effective after changes; never treat a review spreadsheet as an authorization mechanism.
9. Run a standalone Java 17 demo to classify partner drift and entitlements needing review/revocation using synthetic data with deterministic output.
10. Create dashboards, tickets/runbooks, a negative test matrix, and acceptance/review-closure criteria.

**Principle:** "The account can still log in" **does not prove** valid authorization, and "the certificate has not expired" **does not prove** the partner is still trustworthy. A review must rely on an inventory with owners, desired policy, effective configuration, runtime evidence, data-sharing scope, and discrepancy remediation outcomes.

## 2. Federation Context and Boundaries

Assume an enterprise operates the portal `https://portal.example.org` with:

| Partner/Source | Protocol | Receiving System | Subject/Data | Owner |
| --- | --- | --- | --- | --- |
| North workforce IdP | OIDC Authorization Code | Web app `registrationId=north-oidc` | `sub`, `name`, `email`, select approved app roles | IAM + HR + app |
| South partner | SAML2 Web Browser SSO | SP `registrationId=south-saml` | Stable NameID, department, approved group claims | Partner + IAM + app |
| Intranet CAS | CAS protocol | CAS service/filter | Minimal CAS subject/service attributes | Internal IAM ops |
| Enterprise directory | LDAP/AD/SCIM | Provisioning/authorization store | account status, manager, group membership | Directory/HR |
| Data-exchange API | OAuth2 Resource Server | API with dedicated issuer/audience | Access scopes, tenant, resource grants | API owner + Security |

This is a **learning model**, not information about real partners. In production, every endpoint, owner, certificate, purpose, and tenant must come from a verified inventory. Never create review reports containing raw production SAMLResponses, ID Tokens, LDAP exports with passwords, or full employee rosters solely for audit purposes.

### 2.1. Permissions and Data Flow Diagram

```text
     HR / Partner HR              IAM / Directory / SCIM
       employment                  accounts / groups
          |                             |
          +----------+------------------+
                     |
              Identity Provider
           OIDC OP / SAML IdP / CAS
                     |
           signed assertion / tokens
           limited identity attributes
                     |
                     v
           Spring Security RP / SP
        verified issuer + stable subject
                     |
           local account resolution
                     |
           approved role/tenant policy
                     |
             protected resource
                     |
          audit + session/token lifecycle
```

The four systems may **not synchronize immediately**: HR disables an employee and the directory has already disabled the account, yet an older OAuth access token/JWT remains valid or a Spring HttpSession stays active; the IdP removed a group, yet the application DB still holds a direct grant; key N2 is published, yet one pod still trusts N1. Therefore, reviews **must reconcile across multiple sources**, rather than merely exporting an IdP list.

## 3. Three Control Ledgers That Must Be Reconciled

### 3.1. Ledger A — Access Rights (Access & Entitlement Inventory)

| Field | What to Store | Evidence |
| --- | --- | --- |
| `partnerId/registrationId` | Partner and pinned integration | App config/inventory |
| `issuer/entityID` | Trusted issuer; never taken from user query | Approved OIDC discovery/SAML metadata |
| `internalAccountId` | Pseudonymized internal ID for audit | Account store |
| `federatedKey` | OIDC `(issuer, sub)` or stable SAML identifier scoped to issuer | Trusted claims and account mapping |
| `tenantId/resource` | Granted scope | Authorization DB/policy |
| `effectiveRole/permission` | **True** access computed from groups/direct grants/ABAC | Authorization engine + grants |
| `sourceOfGrant` | HR, group, SCIM, manual exception, break-glass | Grant provenance |
| `grantOwner/approver` | Authorized approver, distinct from privileged owner per SoD | Ticket/approval |
| `createdAt/lastUsedAt/lastReviewedAt` | Grant age and activity level | Audited access records |
| `employment/contractStatus` | Active/leave/expired per authoritative source | HR/partner feed |
| `expiry/reviewDue` | Grant expiration and review cadence | Policy |
| `session/revocation state` | Which sessions/tokens remain usable after revocation | Spring Session/IdP API |

Distinguish **IdP group membership**, **Spring `GrantedAuthority`**, **database resource grants**, and **token scope**. These can be four separate sets. A user absent from the `APP_ADMIN` group at the IdP might still hold a direct admin grant in the database; reviewing only groups would miss it.

### 3.2. Ledger B — Shared Data Flows (Claim/Attribute Release Register)

| Field | Example | Why Needed |
| --- | --- | --- |
| `origin` | North OIDC OP | Information source |
| `recipient` | RP portal, reporting API | Actual receiving destination |
| `protocol/transport` | OIDC ID Token/UserInfo, SAML assertion, SCIM | Differs in lifecycle and protection |
| `claim/attribute` | `sub`, `email`, `groups`, `employeeId` | Know which data is shared |
| `purpose` | Login, contact, tenant policy | Grounded basis serving a purpose |
| `required/optional` | `sub` required; `name` optional | Data minimization |
| `classification` | Public/internal/PII/sensitive | Access rights/retention |
| `authorizedOwner` | Privacy + app owner | Accountable party |
| `transform/mapping` | IdP group ID→APP_READER | Prevent role escalation |
| `storage/retention` | Session only, DB, logs, backups | Avoid data duplication |
| `consent/notice/agreement` | Trust agreement/purpose/notice per context | Verify terms of use |
| `lastApprovedAt` | Release approval date | Drift detection |

**OIDC `scope` is not synonymous with SAML `AttributeStatement`.** `openid` establishes the OIDC flow, `profile`/`email` request standard claims at the OP; `groups` is usually a custom claim depending on the IdP. An OAuth2 access token `scope` is an API permission and is **not implicitly an organizational group** or role the RP is allowed to use. It requires owner-approved mapping and issuer/tenant binding.

### 3.3. Ledger C — Partner Configuration (Trust & Integration Register)

| Item | OIDC/OAuth2 | SAML2 | CAS/Other SCIM |
| --- | --- | --- | --- |
| Identity/provider | `issuer-uri`, `authorization_uri` | `IdP EntityID`, SSO/SLO | CAS base URL, SCIM base URL |
| RP/client identifier | `client_id` | `SP EntityID` | CAS `service` |
| Callback | Exact `redirect_uri` | Exact ACS/Recipient/Destination | CAS callback/service |
| Key trust | JWKS URI, algorithms, `kid` | Signing KeyDescriptors, metadata signer, SP keys | TLS/service credentials |
| Credential lifecycle | Client secret/private key/KMS | Signing/decryption private keys | SCIM bearer/service secret |
| Data sharing | Scopes, ID Token/UserInfo, API consent | Released attributes, NameID, groups | CAS attributes, SCIM schema |
| Validity | JWKS/cache/secret expiry | `validUntil`/`cacheDuration`, cert rollover | TLS/cert/token expiry |
| Logout/revoke | OIDC logout/token revocation/session | SAML SLO/SessionIndex | CAS SLO, SCIM deactivate |
| Owner/change | IdP+RP+Security | IdP+SP+Security | Directory/partner service |
| Allowed network | HTTPS/PKIX/hostname/egress | HTTPS/metadata fetch/ACS | mTLS/firewall/rate limit |

**Do not confuse an HTTPS certificate chain with a SAML XML Signature certificate**: signing SAML Responses/Assertions uses trusted IdP SAML signing credentials; TLS authenticates the transport-layer server. Metadata carrying `ds:Signature` requires a separate metadata-signing trust anchor when mandated by contract.

## 4. Choosing Review Cadences: Periodic Plus Event-Driven

The table below is a **sample schedule** for technical illustration; organizations must set policies based on law, risk, contracts, and internal controls:

| Subject | Reference Cadence | Immediate Trigger |
| --- | --- | --- |
| Privileged production access / break-glass | 90 days or shorter by risk | Leaver, incident, SoD conflict, new privileged grant |
| Standard employee access | 180 days | Transfer, contractor expiration, source disabled |
| Federation partner config/trust | 90 days and before any key rollover | Metadata/key/issuer/ACS/redirect URI change |
| Attribute release/privacy register | 90–180 days depending on PII/risk | New claim/scope, purpose/recipient change, data incident |
| Client secrets, SP signing/decryption certs | Alert at 90/60/30 days before expiry | Lost key, rollover, cert distrust, invalid metadata |
| Service accounts/API clients | 90 days or by sensitivity | Key leak, scope change, unused credential, owner left |
| CI/canary trust/authorization regression | Every related deployment | Spring Security upgrade, IdP migration, policy update |
| Partner contract/owner/contact | At least per review cycle | Contract expiry, vendor change, ownership gap |

**A review period is not an authorization TTL.** If HR emits a leaver event today, do not wait 90 days to lock access. Event-driven revocation is a **near-real-time SLA** operational workflow combining session/token invalidation and action-time authorization.

### 4.1. Why There Are Multiple Clocks

```text
T_access_grant_review      When an entitlement requires re-certification by an approver
T_partner_configuration    When metadata/callback/client config requires owner review
T_key_expiry               When a certificate/secret reaches end of technical life
T_jwt_exp                  When an issued JWT expires
T_http_session_expiry      When an app session expires naturally or is revoked
T_contract_end             When a partner is no longer permitted to operate
T_employment_end           When a user loses entitlement per HR

Do not equate these milestones.
```

A grant may be "approved until next quarter" while a token issued today carries a `scope` for minutes/hours; a session in Spring Session Redis can survive a group change unless the application re-checks authorization. Reviews must explicitly document the **source of truth** and **revocation enforcement mechanism**.

### 4.2. Triggers When Partner Configurations Change

- IdP changes `issuer`/EntityID, domain/hostname, OIDC `jwks_uri`, SAML metadata URL, or endpoint; requires trust boundary review.
- A new public SAML signing key appears or an old key is removed, metadata signature/cert changes, or `validUntil` nears expiration.
- OAuth2 client adds a new `redirect_uri`, changes `grant_type`, `response_type`, `scope`, client auth method, or audience.
- SP ACS/EntityID/decryption cert changes; IdP SSO/SLO endpoints change; CAS service path changes.
- SCIM provisioning credentials/field mappings change or user/group deltas spike abnormally.
- Partner changes sub-processor/processor/receiver, processing region, or data purpose; consider privacy/legal review.
- Unapproved surprise IdP key; prioritize quarantine/incident response rather than automatically trusting any key inside a response.
- Application upgrades Spring Security/OpenSAML/Nimbus/cert library versions; run regression security tests.
- Partner compromise, mTLS/TLS PKIX failure, or metadata signature verification failure; treat as a security incident, not merely a periodic review ticket.

## 5. Governance: RACI and Separation of Duties

An effective review requires clear ownership:

| Role | Responsibility | Must Not Self-Perform |
| --- | --- | --- |
| Business/application owner | Confirm access per business need; approve least privilege | Approve their own admin access |
| IAM/federation engineer | Snapshot config, analyze diffs, implement role/metadata updates | Self-approve exceptions without an owner |
| HR/partner identity owner | Attest workforce/contract status, group provenance | Modify business authorization without review |
| Security/IAM governance | Check SoD, partner risk, key trust, exception duration | Create production grants without approvals |
| Privacy/data protection owner | Determine purpose, data minimization, retention, onward disclosure | Collect every claim by default "just in case" |
| Partner contact/IdP admin | Provide metadata, claims contract, rotation schedule, attestation | Unilaterally decide RP tenant permissions |
| Implementer/operator | Execute ticketed revocations/updates, record evidence | Delete audit logs after changes |
| Independent verifier/auditor | Compare desired/actual, test negative cases, close reviews | Trust a "fixed" comment without readback |

RACI needs at least **Responsible**, **Accountable**, **Consulted**, and **Informed** for each partner system. High-risk entitlements require **dual control** or an independent approver per policy. Absent reviewer or unresponsive partner → **access remains unapproved**; never auto-mark "approved by silence" unless policy explicitly permits it.

### 5.1. Review Decisions Must Have Real States

```text
DISCOVERED
  -> NEEDS_OWNER
  -> PENDING_REVIEW
  -> APPROVED or REVOKE_REQUESTED or ESCALATED
  -> IMPLEMENTED
  -> VERIFIED
  -> CLOSED_WITH_EVIDENCE
```

Never mark `CLOSED` simply because someone clicked `APPROVED` before real configuration changed. For revocations, verify the **effective grant** is gone and session/token lifecycles are handled. For excess data, verify the IdP stopped releasing the field, the RP stopped storing/logging it, and downstream recipients no longer consume it.

## 6. Access Review: Desired vs Observed vs Effective

### 6.1. Why Exporting IdP Groups Is Not Enough

Applications can have multiple layered permissions:

```text
HR status (employed/contracted/terminated)
     |
directory group membership
     |
IdP mapping -> SAML groups / OIDC custom claim
     |
Spring GrantedAuthorities / method security
     |
local DB direct grants / tenant-specific ACL
     |
resource-level ABAC and break-glass
     |
actual authorization at request time
```

A leaver disabled at the IdP may still possess a **local service token**, a legacy role in DB, or an active HttpSession. Conversely, a user may hold a group that the app does not map to any authority, yielding no effective permission. Review both **configuration** and **decision**.

### 6.2. Practical Reconciliation

1. Gather **desired access** from approved requests, HR/partner contracts, and business owner decisions.
2. Gather **observed grants** from directory groups, IdP app assignments, SAML/OIDC mapping configs, Spring authorities stores, local DBs, SCIM, API client grants, and privileged break-glass entries.
3. Compute **effective access** per the running authorization policy: role inheritance, deny overrides, tenant/resource/owner ABAC, delegated group memberships, temporary exceptions.
4. Compare desired vs effective by **stable immutable subject ID**, issuer, tenant, and resource: `EXTRA` (unapproved), `MISSING` (approved but absent), `STALE` (review overdue), `ORPHAN` (no HR/partner owner), `SOD_CONFLICT`.
5. Decide: keep, reduce, revoke, reapprove with expiry, fix provisioning, escalate security.
6. Execute in the **right authoritative layer** (IdP group, app permission DB, SCIM directory, service account credentials); never "delete in the dashboard" only for the source to auto-provision it back the next day.
7. Verify convergence across IdP, local DB, Spring Session, downstream API tokens, and caches within SLA.
8. Record before/after diff evidence and real negative authorization tests (not merely ticket state).

### 6.3. Use Only Source-Scoped Identifiers

- In OIDC, `sub` is only stable within `iss`. A safe federation key is typically **`(iss, sub)`**, mapped to an internal account ID.
- In SAML, a **stable persistent NameID** or equivalently guaranteed identifier must evaluate Format/NameQualifier/SPNameQualifier and IdP EntityID; transient NameIDs are not long-term keys.
- `email`/`preferred_username`/`name` can change, be recycled, or collide across IdPs. `email_verified` also depends on the claim source/trust policy and never authorizes auto-linking on its own.
- A user holding multiple identities from two IdPs may only be linked through an **approved account linking process** with auditable evidence.
- Partner tenants must not be inferred from email domains; define tenants via registration plus local authoritative membership.

### 6.4. Easily Overlooked Access Forms

| Type | Why Dangerous | How to Check |
| --- | --- | --- |
| Break-glass admin | Elevated privileges lingering after an incident | Owner, expiry, usage logs, independent approval |
| Contractor/guest | Contract end fails to update IdP group in time | External HR/contract status + expiry |
| Shared accounts | No individual accountability | Flag exception, eliminate, or tightly control |
| API service principals | Non-interactive, absent from HR exports | Client registration, scopes, owner, key history |
| Nested AD groups | Indirect membership grants overly broad access | Effective transitive memberships |
| Local DB direct grants | IdP group removal fails to revoke | Reconcile app grants against IdP/HR |
| Old JWTs or Spring sessions | Stale access persists during validity window | Token TTL, introspection, session invalidation |
| Dormant accounts | Infrequent login does not mean access is ungranted | Last used + approved business owner |
| Cross-tenant role mapping | `Admins` group at IdP A mapped into B | Issuer-specific allowlist, tenant check |
| Shadow OIDC clients | Legacy client apps still requesting access scopes | Inventory OP registrations, owner, client secret rotation |

**Priority order:** Access with no basis or belonging to departed personnel → **revoke immediately per incident/offboarding SLA**; overdue privileged reviews → restrict or escalate by risk; newly observed unapproved standard access → investigate provenance; expansion requests → never grant before owner approval.

## 7. JML, SCIM, and Session Revocation: Reviews Don't Wait Until Next Cycle

### 7.1. JML Sources and Actions

**Joiner:** Confirm HR/partner source, create identity with stable subject, grant minimal entitlements only, apply identity verification policy; never auto-grant admin based on email domain.

**Mover:** Changing department/tenant/role must **remove old grants** before or concurrently with adding new grants; check SoD. Someone moving from Finance to Sales must not retain payment-approval access merely because an old token carries that role.

**Leaver:** Disable identity / SCIM `active=false` or provider-specific action per contract, revoke local grants, sessions, and refresh tokens/service credentials per scope, and verify downstream access. **Disabling an IdP account does not automatically invalidate already-issued JWTs** or RP HttpSessions.

### 7.2. Treat SCIM as Provisioning, Not an Authorization Engine

RFC 7643/7644 define the SCIM schema/protocol; SCIM `PATCH`/`PUT`/`DELETE` or `active=false` are lifecycle operations whose exact impact depends on schema/IdP and connector contracts. When a group is removed at the IdP:

1. Prove the SCIM event reaches the target, authenticated with a properly scoped service credential.
2. Prove the target handles it idempotently, maps the group to the right tenant, and drops no events during outages.
3. Confirm the local grant was removed in effective policy.
4. Confirm old sessions/tokens are bounded by TTL, revocation hooks, or action-time permission checks.
5. Test rollback/duplicate/out-of-order events; implement retries, dead-letter alerts, and batch reconciliation.
6. Avoid logging entire SCIM User resources containing PII in audit reports; use IDs and schema-safe summaries.

SCIM `active=false` does **not** mean all API JWTs are revoked by the RFC. If near-real-time denial is required, APIs must check authoritative account/entitlement state or a designed token introspection/revocation mechanism.

### 7.3. Logout ≠ Full Revocation

| Layer | Impact on Logout | What Review Must Check |
| --- | --- | --- |
| Spring HttpSession | Local session invalidation/cookie clearing | Session store, multi-pod, session indices |
| OIDC OP session | RP-initiated/back-channel logout per provider | `sid`/`sub` binding, Logout Token validation |
| SAML IdP session | SAML SLO if used and successful | SessionIndex and multi-SP coverage |
| OAuth refresh token | Revocable at AS via RFC 7009 if supported | Revocation endpoint/client scope/owner |
| OAuth access token JWT | May remain valid until `exp` under offline verification | TTL/denylists/authoritative checks |
| Opaque access token | Resource server introspects `active` per RFC 7662 | Caching/latency/availability policy |
| CAS TGC/TGT | CAS global login lifecycle | Whether local app session is invalidated |
| App business grants | Do not automatically change on logout | DB/AuthorizationManager state and cache |

**Do not wait for token expiry during a key-compromise or dangerous-grant incident** if urgent denial mechanisms exist. Design refresh/access token TTLs, session revocation, authorization epochs, and auditing commensurate with risk.

## 8. Shared Data: Controlling Purpose and Minimization

### 8.1. Map of OIDC Scopes/Claims

| Claim/Scope | Meaning | What Review Should Ask |
| --- | --- | --- |
| `openid` | OIDC authentication flow | Does the app need an ID Token for login? |
| `sub` + `iss` | Federated subject identity | Used instead of email as the stable key? |
| `profile` | May request many profile claims | Are all needed, or only `name`? |
| `email`/`email_verified` | Email contact/verification claim | Must it be stored? Which recipients use it? |
| `address`/`phone` | Contextually sensitive PII | Truly needed for SSO? |
| `groups` | Custom claim, not an OIDC Core standard scope | Bounded count/namespace/issuer? |
| `roles`/`entitlements` | Provider-specific authorization claims | Allowlist-mapped to APP_*? |
| `acr`/`amr`/`auth_time` | Authentication strength/context | Which risk levels does the app check without misusing? |
| API `scope` (e.g., `reports.read`) | Resource permission for access token | Right API/audience, read vs write? |
| `offline_access` | May issue refresh tokens per OP policy | Does the RP need long-lived access? |

Standard OIDC `profile` can request numerous personal details; **never request all scopes by default**. `email_verified=true` only carries meaning within an IdP/claim trust contract; never equate emails across two issuers. If only a display name is required, prefer the minimal claim rather than collecting birthdate, phone, and address.

**Review storage locations too:** ID Tokens often carry claims and may reside in sessions/security contexts; UserInfo responses, SCIM User resources, logs, data lakes, backups, and telemetry can duplicate PII. Check not only "what the IdP sends", but also "how long downstream RPs/processors keep it and who reads it."

### 8.2. SAML Attribute Release

Illustrative example:

```xml
<saml:AttributeStatement
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:Attribute Name="displayName">
    <saml:AttributeValue>Nguyen Minh An</saml:AttributeValue>
  </saml:Attribute>
  <saml:Attribute Name="groups">
    <saml:AttributeValue>app-report-readers</saml:AttributeValue>
  </saml:Attribute>
</saml:AttributeStatement>
```

This is an **unsigned AttributeStatement fragment and not a verifiable SAMLResponse**. Plausible-looking data does not prove the IdP signed it or that the assertion has valid Issuer/Audience/Recipient/NotOnOrAfter.

Review checklist questions:

1. Is `NameID` Format persistent/transient/email, and sufficiently stable?
2. Which directory supplies `groups`; are there nested groups or guest memberships outside contract?
3. Are hundreds of `memberOf` groups needlessly transmitted, bloating SAMLResponses and causing 413/DoS/session bloat?
4. Only IdP-approved and RP-allowlisted group values may map to app rights; never map `Admins` from any IdP to `ROLE_ADMIN`.
5. Are personal IDs, salaries, birthdates, or unnecessary attributes sent?
6. Is data encrypted when required by trust/privacy agreements? **XML encryption does not replace signature validation.**
7. Do privacy/retention rules cover raw XML/SAMLResponse debugging backups?
8. Modify release policy **at the IdP before signing**; never strip signed XML on the RP.
9. When reducing claims, test valid functionality and accurate permissions; avoid removing attributes needed for identity keys/correlation.
10. Metadata `RequestedAttribute` can express a request, not guarantee the IdP releases only those attributes; measure verified assertions in practice.

### 8.3. Data Minimization Is Not Indiscriminate Deletion

An unused field may still be under legal retention hold or part of an HR source; never purge data without authority. Procedure:

- Classify by purpose, trust agreement, retention schedule, legal holds, and downstream dependencies.
- Stop **new unnecessary collection/transmission** via IdP release policies/client scopes.
- Stop unnecessary mapping/storage/logging at the RP.
- Execute deletion/anonymization schedules in the proper systems per policy and contract.
- Confirm downstream recipients/sub-processors and backups are handled per obligations.
- Test against fail-open when a claim is dropped: the app must deny or handle optional nulls rather than defaulting to admin.
- Store evidence containing only schema/claim names, purpose/owner, counts/byte sizes, and approved diffs; avoid raw PII.

## 9. Trust Agreements and Partner Controls

A secure SSO integration needs both technical configuration and operational documentation/agreements. Items to record:

1. Legal entity/contact and escalation owners (business, security, privacy, IdP technical).
2. Allowed RP/client list, audience/entityID, tenant, ACS/redirect URIs, allowed origins/domains.
3. Protocols/profiles/bindings: OIDC Authorization Code + PKCE, SAML2 signed assertion, CAS service ticket.
4. Key/metadata authority: URL/hosting, metadata signer trust, JWKS key source, certificate rollover schedule, and emergency revocation.
5. Authentication assurance/step-up (MFA, `acr`, `amr`) when relied upon for sensitive operations.
6. Attribute schema, purposes, allowed data receivers, retention, onward disclosure, and incident/breach process.
7. Account identity key/subject stability, account linking policy, and JML/SCIM deprovisioning SLA.
8. Delegated authorization: who grants groups, group→permission mapping, least privilege, and SoD.
9. Session/logout/token lifetimes and incident handling when users are disabled.
10. Monitoring, evidence exchange, downtime/outage contacts, and test environments/key material.
11. Change management: notify/approve prior to changing issuer, ACS, redirect URI, signing keys, or data release.
12. Offboarding: remove keys/client registrations, disable app assignments, revoke secrets, destroy data per obligations, and verify true access denial.

**Never use "the partner signed a contract" as an excuse to trust any URL/KeyInfo/JWKS hinted by a browser.** Runtime must verify exact issuer/audience/recipient/signature and authoritative local tenant permissions.

## 10. OIDC/OAuth2 Partner Configuration: Deep Checklist

### 10.1. Items to Compare Actual vs Approved Baseline

| Item | Secure Baseline | Discrepancy Requiring Ticket |
| --- | --- | --- |
| `issuer-uri` | Exact approved HTTPS issuer | New hostname/issuer with no owner |
| OIDC discovery | OP metadata fetched/verified over trusted HTTPS | Wrong JWKS/token endpoints, SSRF redirects |
| `client-id` | Dedicated client per RP/tenant | Shared client across unrelated RPs |
| `client-secret` or private key | Secret store/KMS, rotation, least privilege | Hardcoded in file/Git, expired/unowned |
| `redirect-uri` | Exact registered HTTPS URL | Wildcards, public HTTP, open redirect |
| `authorization-grant-type` | Authorization Code, PKCE per policy | Unapproved legacy implicit/password grant |
| `scope` | Minimal `openid`, optional profile/email | Excess `offline_access`/broad API scopes |
| `response_type`/mode | Tested and compatible | Unexpected form_post/cookie failures |
| PKCE `code_challenge_method` | S256 where supported/required | Missing verifier or downgrade |
| ID Token validators | iss, aud, exp, nonce, signature/kid | alg none, wrong OP key |
| API access token validators | issuer, audience, exp/nbf, scopes/resource policy | Using ID Token instead of API access token |
| JWKS cache/key rotation | Trusted issuer-bound keys, overlap | Unknown kid accepted or stale trust |
| Logout/token revoke | Registered endpoints and supported policy | Long-lived tokens/sessions survive offboarding |
| HTTP client/egress | TLS/PKIX/host allowlist/timeouts | trustAll, SSRF, outbound to private IP |

RFC 9700 (OAuth 2.0 Security Best Current Practice, 2025) is the design review baseline: strict redirects, mix-up defense, PKCE, and avoiding weaker flows. Evaluate compatibility per OP/Spring Security release; never treat one sample configuration as a universal default.

### 10.2. Minimal Spring Boot 3.x OIDC Example

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          partner-north:
            provider: north-op
            client-id: "portal-north"
            client-secret: "SET_FROM_SECRET_MANAGER"
            authorization-grant-type: authorization_code
            scope: openid,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          north-op:
            issuer-uri: "https://idp-north.example.org/issuer"

server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
```

**Note:** This YAML is a **fragment**, not a runnable app without a real IdP, secret mount, Spring Boot OAuth2 client dependencies, and login/security configuration. The value `SET_FROM_SECRET_MANAGER` is a policy reminder marker; **never use that string as an actual secret**. For IdPs using cross-site `response_mode=form_post`, `SameSite=Lax` may withhold cookies needed for the callback, requiring an independent cookie policy review.

A typical review diff:

```diff
  registration.partner-north.scope = [openid, email]
+ registration.partner-north.scope += offline_access
+ redirect_uris += https://temporary-debug.example.net/callback
```

Both additions require owner/purpose/security review. Reject unvetted debug URLs because they can capture authorization codes. **Disable/block client registrations with no owner**, and never leave "temporary" secrets/redirects indefinitely.

### 10.3. API Resource Servers Are Not Automatically Protected by OAuth Login Alone

A web app using `oauth2Login()` has a local session, whereas a resource API using JWT Bearer tokens requires dedicated validation. Spring Security Resource Server can verify issuer/expiry and audience as configured. Boot 3.5 example (applies only to APIs using that exact issuer/audience):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://idp-north.example.org/issuer"
          audiences: "https://api.example.org/reports"
```

**Never use a single `issuer-uri`** if a resource server trusts multiple issuers without trust-specific custom resolvers/validators. In multi-tenant designs, bind issuer, audience, tenant, scope/resource, and local policy; never stop at finding a valid JWT signature. Never assume `aud` equals OAuth client_id across all APIs.

## 11. SAML2 Partner Configuration: Metadata and Keys

### 11.1. Reviewing Protocol Fields

| Item | Periodic Check | Why |
| --- | --- | --- |
| Spring `registrationId` | Maps to exact IdP and tenant | Prevents mixing partners |
| IdP `EntityID` / `Issuer` | Exact approved value | Prevents SAML tenant confusion |
| SP `EntityID` | Expected `AudienceRestriction` | Blocks assertions meant for another RP |
| ACS `/login/saml2/sso/{registrationId}` | Exact public HTTPS URL | Correct `Destination`/Recipient |
| `SingleSignOnService` | Allowed endpoint/binding | Prevents redirecting to unknown hosts |
| `SingleLogoutService` | Key/binding and session flow | Ensures SLO is protected |
| IdP `KeyDescriptor use=signing` | Trusted public verification certs | Correct XML Signature validation |
| SP signing credential | Private key at SP, public cert known to IdP | AuthnRequest/LogoutRequest signing |
| SP decryption credential | Private key at SP, public cert known to IdP | EncryptedAssertion |
| Metadata signature | Verification trust anchor if required | Prevents forged metadata |
| `validUntil` | Hard validity per spec/consumer policy | Rejects expired metadata |
| `cacheDuration` | Refresh scheduling hint | Do not confuse cache TTL with validity |
| NameID/attributes | Stable subject, minimal release | Privacy/identity mapping |
| Clock and replay | NotBefore/NotOnOrAfter, InResponseTo | Rejects stale assertions |

**Key subtlety:** SAML metadata `cacheDuration` hints when to refresh; `validUntil` is metadata expiration. A caching repository with a TTL does not automatically enforce `validUntil` if custom-built without checks. Verify your exact Spring Security/OpenSAML version and metadata resolver trust policy.

### 11.2. Three Distinct Keys to Inspect

```text
IDP signing key:
    IdP private -> signs SAML Response/Assertion
    SP public  -> verifies signed node

SP signing key:
    SP private -> signs AuthnRequest/LogoutRequest
    IdP public -> verifies request

SP decryption key:
    IdP uses SP public certificate to encrypt Assertion
    SP uses matching private key to decrypt
```

Plus **metadata-signing key** (if metadata carries an XML signature) and **TLS certificate** for HTTPS. These are not inherently identical. An IdP commonly uses a SAML signing certificate distinct from its TLS cert. Inventory public SHA-256 fingerprints, usage, owner, validity, and rotation tickets; keep private keys strictly in KMS/keystore/secret stores.

### 11.3. Standard Key Rollover

```text
T0   IdP signs with N1; metadata lists N1.
T1   IdP publishes signed/trusted metadata with N1 + N2.
T2   SP verifies & activates trusted [N1,N2].
T3   IdP switches signer to N2.
T4   SP accepts N2, may accept in-flight N1 in approved overlap.
T5   IdP metadata retires N1; SP refreshes to [N2].
T6   Negative test: N1 signature REJECTED on every pod.
```

If N1 is compromised, do not wait for a convenient overlap window; run emergency incident revocation. New signed/trusted metadata containing key N2 is not necessarily **eligible** for auto-activation if change-approval policy requires sign-off. **Never extract keys from unverified raw SAML `KeyInfo` in a Response and add them to trusted sets.**

### 11.4. Spring Security SAML2 Metadata

Spring Security associates `RelyingPartyRegistration` with AP/IdP metadata, ACS, SP EntityID, and certificates. In supporting releases, `http.saml2Metadata(...)` publishes SP metadata. Calling `RelyingPartyRegistrations.fromMetadataLocation(...)` once to build and store an `InMemoryRelyingPartyRegistrationRepository` **does not mean IdP metadata automatically refreshes forever**. When refresh is needed, use supported repository/resolver/caching strategies and verify expiry/signature/TLS, atomic publication, and multi-pod consistency.

A review must test a valid **signed SAMLResponse** under the new key and prove the old key is rejected after retirement, while validating issuer, audience, destination, recipient, timestamps, InResponseTo, and replay. HTTP 200 on metadata, non-expired certs, or a 302 browser login redirect is insufficient.

## 12. CAS, Kerberos, and Identity Paths Beyond OAuth/SAML

If CAS/LDAP/AD/SPNEGO connections exist in your federation estate, review them separately:

- **CAS:** registered `service` public HTTPS URI, CAS ticket-validation endpoint/TLS, allowed proxy tickets (if any), CAS attribute release, service owners, CAS logout behavior. Ticket `ST` is a one-time bearer artifact; never log it.
- **Kerberos/SPNEGO:** expected `HTTP/public-host@REALM` SPN, service keytab/KVNO/etype, ownership, delegation scope, key rotation, trusted reverse proxy/pre-auth. An HTTP 401 Negotiate challenge may be normal and does not prove valid authorization.
- **LDAP/AD:** service bind accounts, read permissions, TLS StartTLS/LDAPS certificates, group nesting, lock/disable flags, stale user caches, account control, privileged directory groups.
- **SCIM:** client credentials/scopes, target base URL/tenant binding, `active` mapping, group assignment/revocation, retries/dead letters, provisioning freshness.
- **Vendor portal admin:** IdP admin accounts for integrations, API tokens managing metadata/client registrations, emergency owners, and MFA; these are typically highly privileged yet absent from app business users.

Do not force service credentials into the "user SSO" list; classify them separately with owner/risk-based expiration.

## 13. Standardizing Review Tables and Evidence Templates

### 13.1. Example Pseudonymized Entitlement Row

| reviewId | partner | subjectRef | tenant | effectiveEntitlement | lastReviewed | decision | owner |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RV-101 | north-oidc | usr-17 (pseudonym) | north | APP_REPORT_READ | 2026-05-01 | REVIEW_DUE | Reports owner |
| RV-102 | north-oidc | usr-18 (pseudonym) | north | APP_ADMIN | 2026-10-20 | KEEP_APPROVED | Security owner |
| RV-103 | north-oidc | usr-19 (pseudonym) | north | APP_ADMIN | 2026-11-01 | REVOKE_NOW | IAM owner |
| RV-104 | south-saml | usr-33 (pseudonym) | south | APP_ADMIN | 2026-07-01 | REVIEW_DUE | South manager |
| RV-105 | south-saml | usr-34 (pseudonym) | south | APP_REPORT_READ | 2026-10-01 | REVOKE_NOW | South owner |

Synthetic data, not real people. `REVIEW_DUE` does not automatically mandate immediate revocation if the user remains active and policy permits temporary restricted access; the reviewer must decide by risk. `REVOKE_NOW` for a leaver or unauthorized grant is an emergency action with dedicated execution and verification.

### 13.2. Example Claim Release Register Row

```json
{
  "partnerId": "north-oidc",
  "source": "https://idp-north.example.org/issuer",
  "recipient": "portal.example.org",
  "field": "email",
  "purpose": "user notification after login",
  "classification": "personal-data",
  "required": false,
  "approved": true,
  "storage": "short-lived-profile-cache",
  "retentionPolicyId": "RET-PORTAL-PROFILE",
  "approvedByRole": "privacy-owner",
  "observedFrom": "schema-only-staging-assertion"
}
```

Never include real email values in audit configs. When a new field like `phone_number` appears outside the register, mark `DATA_DRIFT`, stop logging/storing it if possible, route to the privacy/app owner, check downstream recipients, and update the IdP release policy.

### 13.3. Example Approved vs Actual Config Diff

```diff
partner: north-oidc
  issuer: https://idp-north.example.org/issuer
  redirect_uris:
    - https://portal.example.org/login/oauth2/code/north-oidc
+   - https://diagnostic.example.net/callback
  scopes:
    - openid
    - email
+   - offline_access

partner: south-saml
  idpEntityId: https://idp-south.example.org/saml
  trustedSigningCerts:
    - S1
+   - S2
  spAcs: https://portal.example.org/login/saml2/sso/south-saml
```

**Not every added line is bad:** S2 may be an approved rollover; `offline_access` may support a genuine API use case. Still, the review must prove owner/purpose, trust, expiry, and testing. The diagnostic callback line is **high risk** because it can receive OAuth codes; verify endpoint/custodian and remove if unapproved.

## 14. Designing an 8-Step Review Workflow

### Step 1 — Scope and Snapshot

- Pick a UTC cutoff timestamp/date; lock the inventory list of partners/tenants/apps/IdPs.
- Pull current configurations from **live sources** (OP client registry, effective Spring configs, resolved SAML metadata, IdP group mappings, SCIM targets, DB grants).
- Record timestamp, config revision/generation, SHA-256 of **public certificates**, reviewer roles, and evidence-emitting systems.
- Never export private keys, client secrets, raw tokens, SAMLResponses, or unrelated users; minimize data upfront.
- Check completeness: partners missing an owner are flagged **NEEDS_OWNER**, never dropped from scope.

### Step 2 — Collect Desired Baseline

- Approved client registration IDs, exact HTTPS redirect URIs/ACS/SP EntityIDs, issuer/trust anchors.
- Approved data fields/scopes/purpose/recipient/retention.
- Approved entitlement policies, service accounts, high-risk exceptions, SoD matrix.
- Reviewed JML source statuses, contractor end dates, group owners, token/session TTL policies.
- Every baseline change needs a ticket/version/approver; never let live config become the baseline automatically.

### Step 3 — Reconcile and Score Risk

- Compare current vs baseline; flag unknown issuers, callbacks, new certs, endpoints, unexpected scopes/attributes, or old keys still trusted.
- Compare effective access vs approved grants; flag leavers, stale privileged access, orphans, and unused/broad API clients.
- Classify severity: **P0 incident** (key compromise, leaked secrets, unapproved privileged grant), **P1 high** (unexpected callback/issuer, missing metadata signature per contract), **P2 normal** (review overdue, excess optional claim), per organizational risk scale.
- Never lump every anomaly into "P0" and deprive operations of priority differentiation.

### Step 4 — Reviewer Decisions

- Business owner confirms access need and tenant/resource.
- Security owner confirms trust keys/algorithms/SoD/risk/expiry.
- Privacy owner confirms data purpose/scope/retention and disclosures.
- Partner IdP owner confirms issuer/metadata/key rotation and SSO/SLO/config changes.
- A reviewer's own privileged access requires independent approval; never allow self-approval.

### Step 5 — Propose Changes and Impact

- If revoking access: identify authoritative source plus token/session ramifications.
- If reducing claims: IdP release policy plus RP mapping/null handling/downstream impact.
- If changing callbacks/certs: test plan, staged rollover, rollback criteria without reintroducing compromised keys.
- If expanding access: privilege justification, duration, separation of duties, and action-time authorization.
- Prepare canary/staging signed fixtures and acceptance criteria; never write "just redeploy" as a verification step.

### Step 6 — Controlled Execution

- Execute GitOps/config store/OP/IdP portal/SCIM updates using authorized accounts under approved change tickets.
- Rotate secrets inside KMS/secret managers; never paste them into dashboards/tickets.
- Deploy by tenant/registration with monitoring; do not confuse config reload with actual Spring repository refresh on each pod.
- Emergency compromise: prioritize isolate/revoke without waiting for normal deployment schedules.

### Step 7 — Readback, Regression, and Negative Validation

- Read back actual effective grants/certs/claims after changes and compare snapshot versions/fingerprints.
- Test signed SAML fixtures/key rollover, OIDC state/PKCE/JWT validators, and API audience/tenant enforcement.
- Test that **ungranted** users still receive 403/401, while valid users still receive 200 on the proper resources.
- Test logout/token/session invalidation upon revocation, including multi-pod/Redis setups.
- Verify actual ID Token/UserInfo/SAML/SCIM data fields no longer release extras and are purged from logs/backups past policy retention.
- Every defect gets an owner, ticket, and fix deadline. **Never close a review before readback proves compliance.**

### Step 8 — Evidence & Closure

- Store review scope, input/config fingerprints, date, reviewer decisions, implementer, verification, exceptions (expiry, risk owner), and audit IDs.
- Generate summary metrics: partners reviewed, grants reviewed, overdue, revoked, data drifts, key drifts, exception aging.
- Obtain independent sign-off or workflow approvals per policy.
- Report remaining open issues transparently instead of forcing 100% pass.
- Set `nextReviewAt` and event-driven triggers; verify automated schedules/alerts have owners.
- Store/access evidence per retention and privacy policy; strictly prohibit storing bearer artifacts merely to prove login.

## 15. Spring Security: Review Policies Must Reach Runtime Enforcement

### 15.1. Authentication Does Not Grant Resource Permissions

Simple configuration (fragment in Spring Boot 3.x/Security 6.x):

```java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class FederationWebSecurity {

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/reports/**").authenticated()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .saml2Login(Customizer.withDefaults())
            .build();
    }
}
```

**Critical warning:** `authenticated()` does not verify tenant or permission. Combining OIDC + SAML in one app requires real `ClientRegistrationRepository` and `RelyingPartyRegistrationRepository` beans, proper login page/entry points, and suitable CSRF/cookie policies. This snippet is not a standalone app. Never grant admin solely from `ROLE_USER` or un-allowlisted raw `groups`.

### 15.2. Method Security Enforces Authorization at Execution Time

Illustrative pattern separating role/tenant policy from SSO login:

```java
package com.example.federation;

import org.springframework.security.core.Authentication;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final PartnerAccessPolicy access;

    public ReportService(PartnerAccessPolicy access) {
        this.access = access;
    }

    @PreAuthorize("@partnerAccessPolicy.mayRead(authentication, #tenantId)")
    public String summary(String tenantId) {
        return "Aggregate reports for " + tenantId;
    }
}

@Service("partnerAccessPolicy")
class PartnerAccessPolicy {

    boolean mayRead(Authentication authentication, String tenantId) {
        // Example only; replace with real authoritative
        // issuer-scoped account and tenant membership lookup.
        return authentication != null
            && authentication.isAuthenticated()
            && tenantId != null
            && !tenantId.isBlank()
            && false; // Fail closed until real policy is connected.
    }
}
```

**Intentional fail-closed:** `return ... && false` denies all requests so a "dummy policy returning true" pattern is never copied to production. In real deployments, resolve authenticated issuer + stable subject → internal account mapping, checking account status/tenant ACL/grants from an authoritative store **whenever required** or via properly invalidated/versioned caches. `@PreAuthorize` requires `@EnableMethodSecurity` and Spring-managed beans (never self-invoke directly on non-proxied instances). Never assume `authentication.getName()` is safe if it is merely a mutable/colliding email.

**QA checkpoint:** Once the business owner revokes `reports.read`, even if an OIDC ID Token/HttpSession still carries the old group, calling `/reports/tenant-north` must deny per the designed effective resource policy/credential invalidation strategy. A spreadsheet claiming "REVOKED" while the endpoint returns 200 is a **QA FAIL**.

### 15.3. Binding Source to Role Mapping

When converting OIDC/SAML claims into Spring authorities, map via an allowlist table:

```text
issuerId        providerValue                appAuthority       tenant
north-oidc      group:report-reader-north    APP_REPORT_READ    north
south-saml      urn:south:group:finance-r     APP_REPORT_READ    south

UNMAPPED group / unknown issuer / wrong tenant -> NO PRIVILEGE
```

Never directly translate `groups=["admin"]` from any IdP into `ROLE_ADMIN`. API scope permissions must also bind to **audience/resource**; `SCOPE_reports.read` does not implicitly authorize reading another tenant's data.

## 16. Standalone Java 17: Periodic Drift and Review Classifier

The following program uses **pure JDK 17**—no Spring, no database, no secrets. It takes **verified synthetic fixtures**, evaluates partner metadata/trust/config, claim allowlists, and access grants as of a fixed date. The output is strictly **candidate findings for authorized humans/automation to act on**, never revoking or granting access automatically. It does not verify real SAML/XML signatures, ID Tokens/JWTs, TLS, HR sources, or SCIM APIs.

### 16.1. File `FederationReviewDemo.java`

```java
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public final class FederationReviewDemo {

    private static final LocalDate AS_OF =
        LocalDate.parse("2026-11-07");

    // All intervals are EXAMPLE company policy,
    // not a Spring default or statutory requirement.
    private static final int PARTNER_REVIEW_DAYS = 90;
    private static final int PRIVILEGED_REVIEW_DAYS = 90;
    private static final int STANDARD_REVIEW_DAYS = 180;
    private static final int CERT_ALERT_DAYS = 90;

    record Partner(
        String id,
        LocalDate lastReviewed,
        LocalDate keyExpires,
        boolean metadataTrusted,
        boolean callbackHttps,
        Set<String> approvedClaims,
        Set<String> observedClaims
    ) { }

    record Grant(
        String partnerId,
        String subjectRef,
        String entitlement,
        boolean privileged,
        boolean sourceActive,
        boolean grantActive,
        boolean approved,
        LocalDate lastReviewed
    ) { }

    static String partnerReview(Partner p) {
        Set<String> flags = new TreeSet<>();

        if (!p.metadataTrusted()) {
            flags.add("METADATA_UNTRUSTED");
        }
        if (!p.callbackHttps()) {
            flags.add("INSECURE_CALLBACK");
        }
        if (!p.approvedClaims().containsAll(p.observedClaims())) {
            flags.add("EXCESS_CLAIMS");
        }
        if (p.lastReviewed() == null ||
            !p.lastReviewed().plusDays(PARTNER_REVIEW_DAYS)
                .isAfter(AS_OF)) {
            flags.add("REVIEW_DUE");
        }
        if (p.keyExpires() == null ||
            !p.keyExpires().isAfter(AS_OF)) {
            flags.add("KEY_EXPIRED");
        }
        else if (ChronoUnit.DAYS.between(
                AS_OF, p.keyExpires()) <= CERT_ALERT_DAYS) {
            flags.add("KEY_EXPIRING");
        }

        return flags.isEmpty()
            ? "CURRENT"
            : String.join(",", flags);
    }

    static String grantReview(Grant g) {
        if (!g.grantActive()) return "NO_ACTIVE_GRANT";

        // Source status and approval take precedence over due dates.
        if (!g.sourceActive()) {
            return "REVOKE_NOW_SOURCE_DISABLED";
        }
        if (!g.approved()) {
            return "REVOKE_NOW_UNAPPROVED";
        }

        long days = g.privileged()
            ? PRIVILEGED_REVIEW_DAYS
            : STANDARD_REVIEW_DAYS;

        if (g.lastReviewed() == null ||
            !g.lastReviewed().plusDays(days).isAfter(AS_OF)) {
            return "REVIEW_DUE";
        }

        return "CURRENT";
    }

    public static void main(String[] args) {
        Partner north = new Partner(
            "north-oidc",
            LocalDate.parse("2026-10-01"),
            LocalDate.parse("2027-01-15"),
            true,
            true,
            Set.of("sub", "name", "email"),
            Set.of("sub", "name", "email", "phone"));

        Partner south = new Partner(
            "south-saml",
            LocalDate.parse("2026-06-01"),
            LocalDate.parse("2027-05-01"),
            false,
            false,
            Set.of("NameID", "groups"),
            Set.of("NameID", "groups"));

        List<Grant> grants = List.of(
            new Grant("north-oidc", "usr-17",
                "APP_REPORT_READ", false, true, true, true,
                LocalDate.parse("2026-05-01")),
            new Grant("north-oidc", "usr-18",
                "APP_ADMIN", true, true, true, true,
                LocalDate.parse("2026-10-20")),
            new Grant("north-oidc", "usr-19",
                "APP_ADMIN", true, false, true, true,
                LocalDate.parse("2026-11-01")),
            new Grant("south-saml", "usr-33",
                "APP_ADMIN", true, true, true, true,
                LocalDate.parse("2026-07-01")),
            new Grant("south-saml", "usr-34",
                "APP_REPORT_READ", false, true, true, false,
                LocalDate.parse("2026-10-01")));

        System.out.println("north=" + partnerReview(north));
        System.out.println("south=" + partnerReview(south));

        long findings = 0;
        for (Grant g : grants) {
            String result = grantReview(g);
            System.out.println(
                "grant:" + g.subjectRef() + "=" + result);

            if (!"CURRENT".equals(result)
                    && !"NO_ACTIVE_GRANT".equals(result)) {
                findings++;
            }
        }
        System.out.println("openAccessItems=" + findings);
    }
}
```

Run commands:

```bash
javac --release 17 FederationReviewDemo.java
java FederationReviewDemo
```

Deterministic stdout:

```text
north=EXCESS_CLAIMS,KEY_EXPIRING
south=INSECURE_CALLBACK,METADATA_UNTRUSTED,REVIEW_DUE
grant:usr-17=REVIEW_DUE
grant:usr-18=CURRENT
grant:usr-19=REVOKE_NOW_SOURCE_DISABLED
grant:usr-33=REVIEW_DUE
grant:usr-34=REVOKE_NOW_UNAPPROVED
openAccessItems=4
```

### 16.2. Why Does It Produce These Results?

- `north` observes `phone` outside its approved claim set → `EXCESS_CLAIMS`; key expiry 2027-01-15 falls within 90 days of AS_OF → `KEY_EXPIRING`. North's last review on 2026-10-01 is within 90 days, and HTTPS/certificate trust flags pass in the mock.
- `south` has `metadataTrusted=false`, `callbackHttps=false` → `METADATA_UNTRUSTED` and `INSECURE_CALLBACK`; last review 2026-06-01 exceeds 90 days → `REVIEW_DUE`. These flags are test fixtures, not findings on any real partner.
- `usr-17` standard review from 2026-05-01 → 180 days elapsed, review due.
- `usr-18` privileged reviewed 2026-10-20 → still current.
- `usr-19` source account disabled while app grant remains active → `REVOKE_NOW_SOURCE_DISABLED`, taking precedence over the review date.
- `usr-33` privileged review 2026-07-01 → past 90 days.
- `usr-34` source active but grant lacks approval → `REVOKE_NOW_UNAPPROVED`, without waiting for the next cycle.
- `openAccessItems=4` counts 2 overdue reviews plus 2 revocation candidates. It **excludes** partner issues from access findings.

### 16.3. What the Demo Does Not Prove

- `metadataTrusted=true` is just a **fixture boolean**; production must validate metadata signature/TLS trust and exact issuer/registration, never accepting a boolean from the browser.
- `callbackHttps=true` does not validate hostname/redirect URI allowlists; compare exact URIs/certs.
- `observedClaims` are merely field names, not proof of content/validity/signatures. Production collects controlled schema metadata and pseudonymized observations post-validation.
- `sourceActive` must come from a **trusted** HR/partner directory, not raw user claims.
- `approved=true` must link to a grant ID, approver, timestamp, expiry, and SoD proof, not a request boolean.
- Connects to no IdP, Redis, SCIM, Spring Session, token revocation, SAML/ID token verification, or database. Never use `CURRENT` output as an API authorization decision.
- `LocalDate.plusDays` checks "due on or before AS_OF"; production requires explicit timezones/UTC cutoffs, holiday policies, and fixed-time scheduling.
- This is a report classifier and **does not revoke grants automatically**. Revocation must go through authoritative systems and readback as in Section 14.
- The Java 17 code uses `record`, `Set.of`, `TreeSet`, and `ChronoUnit`, requiring no external libraries beyond the JDK.

## 17. Dashboards and Review Alerting Mechanisms

### 17.1. Suggested Operational Metrics

```text
federation_partner_review_due_total{riskTier}
federation_partner_owner_missing_total{}
federation_metadata_signature_failures_total{registration}
federation_metadata_validity_seconds{registration}
federation_cert_expiry_days{registration,purpose}
federation_key_rotation_lag_seconds{registration}
federation_unapproved_redirect_uri_total{partner}
federation_excess_claims_total{partner}
federation_claim_release_change_total{partner}
federation_access_review_due_total{riskTier,tenant}
federation_unapproved_privileged_grants_total{tenant}
federation_orphan_accounts_total{partner}
federation_jml_revoke_latency_seconds{source}
federation_session_revoke_failures_total{app}
federation_config_diff_total{severity}
federation_review_closure_percent{reviewCycle}
```

Metric names are **suggestions**, not Spring/Micrometer built-ins. Avoid labels containing emails, `sub`, NameID, access tokens, group values, or arbitrary issuer URLs (high cardinality/PII). `registration` and `tenant` must come from bounded known IDs; never turn user-supplied values into labels.

### 17.2. Distinguishing Counts from Effectiveness

**Vanity metric:** 100% of rows marked "approved" by reviewers. Revoked grants might remain unremoved, expired certs unrotated, or excess claims still released.

**Meaningful metrics:** P95 time-to-revoke from authoritative offboarding to effective API denial; percentage of privileged grants with independent approval; count of sessions surviving revocation in tests; percentage of partner metadata resolved to the right trust generation across **all pods**; count of unapproved claims **observed after validation** and removed at the IdP; count of old keys still accepted post-retirement.

Dashboards do not replace evidence/tickets or security tests. For high-severity events, trigger immediate alerts instead of waiting for quarterly dashboard reviews.

## 18. Pre-Closure Test Matrix for Review Cycles

| Test | Input/Action | Expected Outcome |
| --- | --- | --- |
| **Privileged grant overdue** | Last reviewed 91 days ago, 90-day policy | Review due |
| **Standard grant at boundary** | Last reviewed exactly 180 days ago | Review due per inclusive policy |
| **No review history** | Null lastReviewedAt | Flag review due |
| **Leaver still has grant** | HR disabled, app grant active | Emergency revoke candidate |
| **Partner contractor expired** | Contract ended, local account active | Revoke/escalate; do not wait for quarter |
| **Orphan role** | Group missing owner/approval | Needs owner, risk decision |
| **SoD conflict** | Approver = privileged grant owner | Independent approval required |
| **Shared/break-glass account** | No owner or no expiry | Escalate, time-bound exception |
| **Nested AD group** | Indirect APP_ADMIN grant | Effective access includes it |
| **Direct DB grant** | IdP group removed, local role still exists | Flag stale privilege |
| **SCIM active=false** | User disabled via SCIM | Target inactive, grants/session policy effective |
| **SCIM event lost** | Queue outage, target unchanged | Alert/retry/reconciliation |
| **SCIM duplicate/out-of-order** | Repeated PATCH or older change arrives later | Idempotent/version policy |
| **Existing JWT after revoke** | JWT still within exp | API action-time deny or bounded risk window |
| **Spring HttpSession after revoke** | Redis session still exists | Session invalidate/authoritative access deny |
| **Unknown issuer same email** | IdP B email matches IdP A | No auto-link/tenant grant |
| **Unapproved OIDC scope** | `offline_access` newly granted | Flag data/access drift |
| **Unapproved claim** | `phone` appears in UserInfo | DATA_DRIFT, stop unnecessary release |
| **Remove optional claim** | IdP stops `name` | No null dereference / privilege fallback |
| **Group claim explosion** | Thousands of groups from IdP | Enforce size/allowlist, no role escalation |
| **OIDC wrong `iss`** | Valid JWT from different issuer | Reject |
| **OIDC wrong `aud`** | API token for other service | Reject |
| **OIDC unknown `kid`** | Untrusted JWK key | Reject, trusted refresh only |
| **OIDC weak/none algorithm** | `alg=none` or unapproved | Reject |
| **OIDC redirect URI added** | New external callback | Change approval, quarantine if unauthorized |
| **OIDC authorization code replay** | Reuse code in staging | Reject; no state/PKCE bypass |
| **SAML issuer mismatch** | Signed Response from wrong registration | Reject |
| **SAML audience mismatch** | Assertion for another SP entityID | Reject |
| **SAML recipient/destination wrong** | Unregistered ACS | Reject |
| **SAML unknown signing cert** | Untrusted key | Reject |
| **SAML metadata signature invalid** | Tampered candidate metadata | Reject candidate |
| **SAML metadata expired** | At/past validUntil | No trust based on expired metadata |
| **SAML N1→N1+N2→N2** | Valid signed fixtures in stages | New key PASS after staged trust; old FAIL after retire |
| **Cross-tenant SAML** | Response from tenant A to B | Reject, no group/identity merge |
| **SP decryption key rotate** | IdP encrypts to new SP cert | All pods decrypt, old retired when safe |
| **CAS wrong service** | ST for other service URL | CAS validation reject |
| **CAS ST reuse** | Ticket validated twice | Second reject |
| **SPNEGO unknown SPN** | Ticket for wrong host | GSS reject |
| **Partner cert expired** | Cert near/past expiry | Alert, safe rollover/deny per policy |
| **Unapproved metadata redirect** | Fetch URL redirects to private IP | SSRF/egress reject |
| **Partner absent owner** | Contact departed organization | Escalate/disable risky integration |
| **App authorization negative** | Revoked user accesses resource | 403/401 (policy), never 200 |
| **App authorization positive** | Approved user reads allowed tenant | 200 correct resource |
| **Audit redaction** | Export review evidence | No bearer code, SAMLResponse, secrets, raw PII |
| **Multi-pod drift** | One pod holds old signing set | Fail rollout/converge, quarantine old trust |
| **Configuration revert** | Rollback to old metadata/client | Must not reintroduce revoked key/callback |
| **Review approval evidence** | Reviewer marks keep/revoke | Ticket owner/approval/readback/closure present |

**Fixture separation:** To test a SAML wrong audience with a valid signature, re-sign the SAML fixture **after** introducing the wrong audience using the test IdP. Modifying XML after signing only tests invalid signatures, not the audience validator. Never use raw production assertions/tokens in automated tests.

## 19. Real-World Scenarios and Runbooks

### 19.1. Admin Access Persists After Employee Departure

**Symptom:** HR marked leaver and IdP account is disabled, yet the user has an active session/JWT and local `APP_ADMIN` grant.

**Runbook:**

1. Confirm authoritative HR status/termination timestamp and grant ownership (never act on rumor).
2. Trigger emergency revocation per SLA: delete local grants, disable any personally tied service principals, and revoke refresh tokens/sessions via supported mechanisms.
3. Check Spring Session Redis/JDBC, Resource Server token TTL/authoritative permission checks, and every tenant resource.
4. Run negative tests with a disabled staging account or security-approved controlled test, avoiding taking over real accounts.
5. Investigate why SCIM/group sync failed to remove the grant; design reconciliation and alerts.
6. Close the incident only when **actual access is DENIED**, not just "IdP disabled."

### 19.2. OP Adds `offline_access` to Client

1. Compare actual client registration `scopes` with the approved register; is there a specific owner/purpose for refresh tokens?
2. Check OP consent/token issuance policy, client auth method, and secret storage.
3. If unneeded, remove the scope at client/OP and handle previously issued refresh tokens per policy.
4. Verify ID Token/UserInfo and API access tokens release no extra PII/scopes beyond purpose.
5. Regression-test web login & APIs; never enable implicit/password grants.
6. Save diff, approval, and outcome; never log refresh tokens.

### 19.3. Unknown Signing Key S2 Appears in SAML Metadata

1. Determine whether this is a planned rotation or unexpected; inspect HTTPS metadata source, metadata signature trust anchor, expected entityID, and hard validity.
2. Never automatically add S2 to all registrations/tenants. Ask the partner owner to confirm the public certificate fingerprint over an approved channel.
3. If valid, stage N1+S2 overlap (for the exact partner key pair); test new-key signed fixtures alongside issuer/audience/recipient.
4. After cutover, retire the old key and verify old-key signatures are rejected on all pods.
5. If compromise is suspected, quarantine/revoke/escalate incident; never keep trusting the old key just because it is "still within validity."
6. Ensure your own SAML SP decryption/signing keys are not confused with the IdP signing cert.

### 19.4. App Receives Excessive Groups/PII from IdP

1. Record counts and schema fields (not raw values/NameIDs) after signed verification.
2. Compare purpose against the release register; flag unrelated groups and unowned custom claims.
3. Request the IdP to narrow release/filter group claims; consider backend entitlement lookup if group counts are large.
4. Remove unnecessary RP mappings/storage; align session/cache/log retention with policy.
5. Test that legitimate users still sign in with accurate rights and unknown groups do not become admin.
6. Update trust agreements/contracts/data maps if a valid purpose or recipient changed.

### 19.5. Partner Unresponsive to Review Requests

1. Verify contacts/owners/last attestation; open a `NEEDS_OWNER` ticket with a deadline.
2. Check key expiry, metadata validity, actual auth volume, and data sensitivity; classify risk.
3. For high-risk or expired contracts, apply temporary restrictions or suspend via emergency approval; never delete all user accounts blindly if business/retention obligations apply.
4. Escalate to Security/Legal/Business owners; never mark approved by silence.
5. Test after restriction: targeted to the right tenant and contract without breaking other partners.
6. When the partner re-engages, run a full config/claims/grants review before restoring access.

### 19.6. Spring Security Upgrade Changes Authority Mapping

1. Capture Spring/Boot/OpenSAML versions, `GrantedAuthoritiesMapper` converters, and custom policies.
2. Use signed OIDC/SAML staging assertions to verify issuer-scoped claim→application authority mapping.
3. Compare before/after access decisions against per-tenant golden cases; allow only approved grants.
4. Negative tests: unknown group, wrong issuer, duplicate email, disabled user, stale session, admin SoD conflict.
5. If group names diverge, **never** map all values to `ROLE_ADMIN` just to make tests pass.
6. Roll back versions only if doing so does not reintroduce a vulnerability or revoked key, with security owner review.

## 20. Auditing Without Leaking Sensitive Data

### 20.1. Sufficient Audit Evidence

```text
reviewCycleId
snapshotAtUtc
partnerId/registrationId (approved local ID)
ownerRole/reviewerRole/approverRole
configVersion/hash (not raw private key)
issuerEntityId (approved canonical string)
publicSigningCertFingerprintSha256
keyPurpose/validity
redirectUriOrAcsCategory (or exact approved config under ACL)
approvedScope/attributeName schema only
numberOfEffectiveGrantsByRisk
pseudonymousGrantRef
decision + reason category
changeTicketId / implementation timestamp
verification result (negative/positive tests)
exceptionExpiresAt / escalationOwner
nextReviewAt
```

Do not collect in review exports:

```text
Raw SAMLResponse / RelayState / NameID values
OIDC authorization code / ID token / access/refresh tokens
CAS service ticket / TGT / TGC / PGT
Kerberos Negotiate header / keytab
JSESSIONID / SESSION cookies / CSRF token
SP or IdP private signing/decryption keys
Client secrets / SCIM bearer tokens
User passwords, full LDAP dump, unrelated HR details
```

Public certificate SHA-256 fingerprints can be stored and diffed old vs new, yet certificate/key details must preserve proper ownership context; never treat a fingerprint as a proxy for approval. Reviewer records and pseudonymous subjects can still constitute personal data; apply ACLs and retention to the evidence store itself.

### 20.2. Evidence Is Not Just a Screenshot

An IdP admin console screenshot saying "role removed" **does not prove** the runtime Spring Resource Server denies access. A YAML diff saying "scope removed" **does not prove** the OP stopped issuing refresh tokens or the RP deleted stored tokens. Attach:

- **Change evidence**: ticket/config diff signed by automation/owner.
- **Readback evidence**: actual source, config generation, session/token state.
- **Runtime evidence**: success/fail login and negative business resource tests.
- **Privacy evidence**: claim schemas/counters, logging/retention checks.
- **Closure evidence**: independent verifier, residual risk/exception expiry.

You do not need to store raw assertions to prove metadata signing; use independent test fixtures and signed validation outcomes with certificate fingerprints.

## 21. Review Quiz and Answers

**Q1.** A user is disabled at the IdP but still holds a valid 30-minute JWT and a local DB role. Can review wait until next quarter?

**Answer:** No. JML leaver is event-driven; handle authoritative revocation/local roles, sessions/refresh tokens, and the JWT risk window, testing denial within SLA.

**Q2.** A partner completes SAML login successfully. Does that prove the SP is secure enough?

**Answer:** Not yet. Verify signature/issuer/audience/recipient/timestamps, proper key trust, tenant permissions, minimal released data, and governance.

**Q3.** Does OIDC `email_verified=true` allow auto-linking a user from issuer A with the same email from issuer B?

**Answer:** No. Identity keys should combine issuer + subject; cross-issuer account linking requires separate verification and approval.

**Q4.** Is `scope=openid email profile offline_access` always appropriate for a web app needing only login and display name?

**Answer:** No. Request only scopes/claims needed for the purpose; `offline_access` introduces extra lifecycle/risk if refresh tokens are issued.

**Q5.** `SAML metadata cacheDuration` has elapsed, but `validUntil` is tomorrow. Must all logins be blocked immediately?

**Answer:** Not automatically. `cacheDuration` is a refresh timing hint; `validUntil` is hard validity. Last-known-good fallback operates only within approved policy/trust windows.

**Q6.** The IdP inserts a new SAML signing cert into metadata; can it be trusted solely because the XML contains that cert?

**Answer:** No. Metadata must be trusted/verified against trust anchors and approval policies, with proper key usage/issuer; never auto-learn keys from raw Responses.

**Q7.** Is removing a user's group in the directory enough to revoke all Spring sessions?

**Answer:** Not implicitly. Cached GrantedAuthorities, HttpSessions, and issued JWTs may persist; session invalidation and an action-time authorization/caching plan are required.

**Q8.** An app keeps numerous SAML group names "in case we need them later" with no purpose or owner. What should be done?

**Answer:** Flag release drift, confirm with Business/Privacy, reduce attribute release/storage/retention, and verify no impact on principals or least privilege.

**Q9.** Two IdPs both have an `Admins` group; can both map to `ROLE_ADMIN`?

**Answer:** Not without approved issuer/tenant-specific mapping. Raw group names do not independently prove entitlement.

**Q10.** A privileged grant is self-approved and closed by the reviewer. Does this satisfy SoD?

**Answer:** Typically no. Policy requires independent approval, accurate HR/business provenance, and auditing.

**Q11.** A partner switches Redirect URI to a temporary HTTP debug page; can it be temporarily accepted for a few hours?

**Answer:** Not by default. Authorization codes can leak; exact HTTPS redirect URIs, allowed hosts/owner/security review, and canary checks are needed beforehand.

**Q12.** The review sheet marks "revoke complete" yet the user still reads API data. What is the QA result?

**Answer:** FAIL. Close only after verifying effective denial (token/session/resource/tenant) and checking source auto-provisioning, caches, and authorization.

**Q13.** Does SCIM `active=false` guarantee the IdP automatically revokes all issued JWTs?

**Answer:** No. SCIM is a provisioning protocol; JWT/token lifecycles belong to OAuth AS/RP/resource enforcement.

**Q14.** When a cert is flagged as expiring in 90 days, is that automatically a security incident?

**Answer:** Not always. It is a planned renewal alert; if the cert is compromised, expired, or untrusted/invalid, escalation may be higher. Assess role, exposure, and rotation window.

**Q15.** Does audit evidence need full SAMLResponses to prove which groups the IdP released?

**Answer:** No. Use sanitized schemas/counts plus verified fixtures/results and restricted-access signed test logs without raw PII.

## 22. Pre-Production and Periodic Acceptance Checklist

- [ ] Inventory omits no IdP/OP, SP/RP, CAS, SCIM, API client, or user/group/service identity.
- [ ] Every partner has a business owner, IAM owner, security/privacy contact, technical contact, and contract expiry.
- [ ] Expected issuer/entityID, registrationId, audience/SP EntityID, ACS/redirect URI, and SSO/SLO endpoints are pinned and compared with actuals.
- [ ] TLS/PKIX/hostname checks, metadata signature verification policy, JWKS trusted keys, and key usage are maintained.
- [ ] SAML `validUntil`/`cacheDuration` are understood properly, and metadata refresh/repository convergence is tested.
- [ ] IdP/SP signing/decryption cert lifecycles and secret rotation have owners and risk-appropriate 90/60/30-day alerts.
- [ ] Unknown signing keys, untrusted metadata, wrong issuer/audience/recipient, and expired assertions/tokens are rejected.
- [ ] OIDC client grant types, PKCE, scopes, redirect URIs, and client authentication are reviewed per RFC 9700.
- [ ] API access tokens enforce issuer/audience/scope/resource, never substituting ID Tokens for access tokens.
- [ ] Shared data maintains a register of purpose, approved names, receivers, classification, retention, and downstream propagation.
- [ ] Custom `groups`/`roles` map via issuer/tenant allowlists, never granting admin from raw claims.
- [ ] SAML AttributeStatement/NameID and OIDC profile/email claims are minimized, removing unused PII and log leaks.
- [ ] Federation identity keys use issuer+stable subject or approved SAML equivalents; no auto-linking by matching email.
- [ ] Effective grants cover IdP groups, local direct grants, DB ACLs, API clients, break-glass, and nested memberships.
- [ ] JML uses authoritative HR/contract sources; leaver/mover triggers revoke within SLA immediately without waiting for audit cycles.
- [ ] SCIM events and actual app grants reconcile, with tested retries/dead letters/caching.
- [ ] Local sessions/JWTs/refresh tokens have risk-appropriate revocation/TTL/authoritative checks.
- [ ] Reviews separate approver/implementer/verifier, especially for privileged SoD.
- [ ] Reviewers decide keep/reduce/revoke/exception with rationale, owner, and expiry; never approve by silence.
- [ ] Configuration diffs and unexpected claims/redirects/keys generate appropriately prioritized tickets.
- [ ] Changes occur strictly via controlled deployments/IdP portals/secret stores, with rollbacks that never reintroduce revoked keys.
- [ ] All Spring Security pods/regions run the intended trust/role-mapping version; no stale key caches.
- [ ] Negative tests: revoked users cannot access tenants/resources; unknown issuers and group claims cannot escalate.
- [ ] Positive tests: approved user logins and valid resource access remain unaffected by claim reductions or key rotations.
- [ ] Audit artifacts are pseudonymized and access-restricted; zero raw tokens, cookies, SAMLResponses, or private keys.
- [ ] Dashboards track overdue reviews, stale privileges, drift, cert expiry, SCIM revocation latency, and runtime verification.
- [ ] Open findings have owners and deadlines; reviews never close if readback or tests FAIL.
- [ ] Next review dates and event-driven alerts operate continuously and are tracked across owner changes.
- [ ] SOP/runbook documentation stays current with Spring Security/IdP major versions, using signed staging fixtures and privacy safeguards.
- [ ] Sensitive changes carry documented approvers, rollback criteria, incident contacts, and retention-compliant evidence.
- [ ] Distinguished "SSO login works" from "effective access correct", "data sharing lawful/minimal", and "partner trust still approved".

**Conclusion:** Periodic SSO federation reviews must be a **continuous cycle**: verify effective entitlements, exchanged data by purpose, and partner trust configurations; convert every discrepancy into owned actions, verify via readback and runtime negative tests, and retain minimal evidence. Spring Security enforces authentication/authorization, yet does not perform access certification, privacy reviews, partner contracting, or key approvals on its own. A review cycle is complete only when **the right people retain the right permissions, unauthorized individuals are genuinely denied, unnecessary data stops flowing, and every issuer/callback/certificate continues to be verified under proper trust policies**.

## 23. Official Documentation and Reference Standards

1. [NIST SP 800-63C-4 – Federation and Assertions (final, 2025)](https://csrc.nist.gov/pubs/sp/800/63/c/4/final): federation trust, RP/IdP, issuer + subject user identifiers, privacy, and assertion protection.
2. [NIST SP 800-63-4 – Digital Identity Guidelines (2025)](https://csrc.nist.gov/pubs/sp/800/63/4/final): authentication/federation risk management framework.
3. [Spring Security – OAuth2 Client/Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/): client registrations, authorization, and callback endpoints.
4. [Spring Security – SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): RelyingPartyRegistration, asserting party metadata, and credentials.
5. [Spring Security – SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): parsing/publishing metadata and trust/refresh options.
6. [Spring Security – Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): AuthorizationManager, request/method-level decisions.
7. [Spring Security – Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer/audience validation, JWK trust.
8. [Spring Security – Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): SecurityContext/HttpSession lifecycle.
9. [RFC 9700 – OAuth2 Security BCP](https://www.rfc-editor.org/rfc/rfc9700): current best practice, redirect URI, PKCE, and token flow safety.
10. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `sub`/`iss`, scopes/claims, UserInfo, `email_verified`, and ID Token validation.
11. [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer metadata, endpoints, JWKS URI.
12. [OASIS SAML2 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): EntityID, KeyDescriptor, validUntil/cacheDuration.
13. [OASIS SAML2 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): Assertion, AudienceRestriction, SubjectConfirmation.
14. [OASIS SAML2 Bindings](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf): SAML Web SSO transport/binding.
15. [RFC 7643 – SCIM Core Schema](https://www.rfc-editor.org/rfc/rfc7643): SCIM users/groups/active attributes.
16. [RFC 7644 – SCIM Protocol](https://www.rfc-editor.org/rfc/rfc7644): provisioning operations, PATCH, GET, DELETE.
17. [RFC 7009 – OAuth2 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): token revocation endpoint.
18. [RFC 7662 – OAuth2 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): opaque token active state.
19. [RFC 7591 – OAuth2 Dynamic Client Registration](https://www.rfc-editor.org/rfc/rfc7591): client metadata, redirect_uris, and grant types.
20. [OWASP – Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default, per-request authorization.
21. [OWASP – Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session lifecycle/revocation.
22. [OWASP – SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): issuer/audience/signature/metadata trust.
23. [OWASP – Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): audit redaction and secret-safe logging.
24. [OWASP – Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): client secret/private key lifecycle.
