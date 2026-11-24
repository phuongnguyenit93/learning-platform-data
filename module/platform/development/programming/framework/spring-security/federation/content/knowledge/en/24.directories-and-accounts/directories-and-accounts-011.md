# Coordinating User Onboarding, Role Changes, and Access Revocation Workflows

## Learning Objectives

After this lesson, you will be able to:

1. Describe the **Joiner–Mover–Leaver (JML)** workflow: adding users, changing job titles/groups/permissions, and revoking access in systems with LDAP/Active Directory, IdP/SSO, Spring Security apps, and APIs/tokens/sessions.
2. Distinguish **HR/personnel decision source**, **Identity Governance (IGA/IAM)**, **Directory/IdP**, **SCIM provisioning**, **identity linking**, and **application authorization**. Understand why successful SSO does not mean a person is allowed to access application data.
3. Design durable data models: immutable internal ID, `(trusted issuer, stable subject)` pair, SCIM `id` and `externalId`, tenant membership, role/permission grant, approver, expiry, revision, and audit.
4. Design an onboarding workflow that never auto-grants admin; handle approvals, provisioning, account linking, MFA, least-privilege testing, and activation timing.
5. Design role changes using **remove old privileges, then grant approved new privileges**, separating old/new permissions, checking Separation of Duties (SoD) conflicts, and preventing privilege accumulation.
6. Design leaver/offboarding workflows by urgency: block new logins, disable accounts/links, revoke sessions/tokens/API keys/grants, handle sessions on other services, and preserve logs per policy.
7. Understand SCIM 2.0 examples per **RFC 7643/7644** to create users, update `active`, and modify `Groups.members` using ETag/`If-Match` when supported; distinguish account syncing from authentication and session revocation.
8. Apply Spring Boot 3 / Spring Security 6 with `@EnableMethodSecurity`, `@PreAuthorize`, and policies re-reading accounts/permissions from trusted sources; understand the roles of `UserDetailsService`, `LdapAuthoritiesPopulator`, and `GrantedAuthoritiesMapper` depending on the authentication mechanism.
9. Build **idempotent, stale-version-resistant** lifecycle event consumers with periodic reconciliation; run a **standalone Java 17+** program demonstrating user creation, role transfer, deactivation, and controlled reactivation.
10. Test failure scenarios: delayed/out-of-order events, same email across different users, caches/`HttpSession` holding stale authorities, unexpired access tokens, sessions across multiple nodes, and deactivated partners/tenants.

## 1. Why Does Federated Authentication Need User Governance Workflows?

In a federation architecture, an employee may sign in via Active Directory/Kerberos, CAS, SAML2, OIDC, or an authenticating proxy. The **Identity Provider (IdP)** answers "who is signing in?", while the application answers "what is this person allowed to do on which resources?". **Directories and account lifecycles** supply critical inputs to both layers.

B2B application example:

- HR holds the employee record with `employeeId=E-103`, employment status, and org unit.
- IAM/IGA manages access requests, approvals, and conflict policies.
- AD/LDAP stores directory users, groups, or account status.
- The IdP emits OIDC `(iss, sub)` or SAML2 identity after authentication.
- Provisioning (possibly via SCIM) creates/updates/disables the local account in the Portal.
- The Portal stores `internalAccountId`, tenant memberships, and specific permissions like `REPORT_READ`, `REPORT_APPROVE`.
- Spring Security creates `Authentication` for the logged-in user; method/resource authorization checks effective permissions.

**A change in HR or AD does not automatically update every Spring Security session/token.** You must coordinate the lifecycle, permission data, and designed revocation mechanisms.

### 1.1. Three scenarios that must be coordinated

| Scenario | Business event | Security goal | Participating systems |
| --- | --- | --- | --- |
| **Joiner** – Add user | Employee/partner joins and needs access | Create only approved accounts and permissions; no auto-admin | HR/owner → IGA → Directory/IdP → provisioning → app |
| **Mover** – Change role | Changes department, project, tenant, or level | Remove unneeded old permissions, grant exact new ones, check SoD | HR/manager → IGA → groups/SCIM → local grants → sessions |
| **Leaver** – Revoke access | Resignation, contract end, compromised account | Stop new logins **and** live permissions/sessions/tokens | HR/SOC → IdP/Directory → apps → session/token stores → audit |

**Changing roles is not just "add the new group"**. If a user accumulates permissions without dropping old ones, multiple transfers leave them holding permissions across many departments they no longer need (privilege creep).

**Revoking access is not just "disable account in AD"**. An app that already authenticated the user may still hold an `HttpSession` or unexpired bearer token; it does not re-check AD/IdP on every request unless designed to do so.

## 2. Responsibility Diagram and Authoritative Data Sources

```mermaid
flowchart LR
    HR["HR / Contract / Partner owner"] --> IGA["IAM / IGA approvals & SoD"]
    IGA --> Dir["Directory / AD / LDAP"]
    IGA --> Prov["Provisioning / SCIM / events"]
    Dir --> IdP["Trusted IdP / SSO"]
    IdP --> Login["Spring Security authentication"]
    Prov --> Account["Application account + tenant grants"]
    Login --> Link["Issuer+subject → internal account"]
    Link --> Account
    Account --> Authz["Request / method / resource authorization"]
    IGA --> Revoke["Sessions & tokens revocation"]
    Revoke --> Authz
    Account --> Audit["Audit, revision, reconciliation"]
    Revoke --> Audit
```

### 2.1. Who decides what?

| Component | Primary source of truth | Does not do on its own |
| --- | --- | --- |
| **HR/Contract System** | Start/end dates, employment/partner status, org unit | Does not define Java `GrantedAuthority` |
| **Business owner/manager** | Role/permission needs per task/tenant/project | Does not bypass Security/IAM with admin roles |
| **IAM/IGA** | Access request/approval workflows, SoD, recertification | Does not guarantee all app sessions are revoked without integration |
| **Directory / AD / LDAP** | Directory objects, groups, account status, principal/UPN | Does not grant per-app object-level permissions |
| **IdP / Federation** | User authentication and identity assertions after trust checks | Does not know all local app permissions and sessions |
| **SCIM provisioning client** | Pushes User/Group state events to applications | Does not log out app sessions or validate SAML/OIDC |
| **Portal Account Service** | Internal account ID, tenant memberships, role/permission grants, revision | Does not verify SSO tickets on its own |
| **Spring Security** | `Authentication`, `GrantedAuthority`, and enforcement | Does not build HR approvals or SCIM unless integrated |
| **Session/Token Store** | App sessions, refresh tokens/grants, API token revocation | Does not know a user left unless signaled |
| **Security/SOC** | Incident response, emergency denials, and auditing | Does not replace routine approvals outside incidents |

### 2.2. Syncing state does not mean forwarding all permissions

**Authentication claims** (from the IdP) and **authorization grants** (from the app/IAM) can have separate sources. For example, OIDC `sub` only proves identity at the issuer; it **does not automatically become `ROLE_ADMIN`**. An AD group named `Administrators` likewise does not implicitly hold tenant management rights on the Portal.

Low-risk approach:

- IdP/Directory verifies identity, and groups when needed.
- The app keeps an **explicit mapping** between group object IDs/approved IAM roles and local per-tenant permissions.
- Local account must be `ACTIVE`, membership active, and grant unexpired.
- For sensitive actions, the authorization service re-checks **current permission sources**, rather than relying solely on a group name or authorities from hours-ago login.
- Audit the provenance of every grant: which request, who approved, conditions, expiry, target systems, and revision.

## 3. Common JML Data Model in an Application

### 3.1. Identifiers that must not be confused

| Identifier | Example | Scope / immutability |
| --- | --- | --- |
| HR/contract ID | `E-103` or `C-55` | Used in HR/contracts; not necessarily sent to every IdP |
| Directory object GUID/ID | AD/LDAP opaque ID | Bound to directory object; UPN/display name can change |
| OIDC `iss` + `sub` | `https://login.idp.example` + `opaque-user-001` | Use the verified identity pair, never bare `sub` across issuers |
| SAML2 issuer + stable subject | IdP entity ID + persistent NameID/profile | Use only per `NameID` contract; avoid auto-email if unstable |
| SCIM `id` | `b2d3-...` | Assigned by SCIM **service provider**, stable/non-reused |
| SCIM `externalId` | `hr:E-103` | Assigned by provisioning client, **scoped to provisioning domain** |
| SCIM `userName` | `a.nguyen@example.org` | Username in SCIM schema, not necessarily an internal PK |
| App `internalAccountId` | `acct-1007` | Immutable key for local users, sessions, grants, and audits |
| Tenant ID | `tenant-finance` | Permission scope; never taken from unverified query/header |
| Role ID | `TENANT_ANALYST` | Policy/permission set managed by app/IGA |
| Permission | `REPORT_APPROVE` | Specific action on an appropriate resource |
| Session/token ID | Opaque ID | Used for revocation, not identity linking |

**Email, display name, short username, and group display name are not durable federation keys.** They can change, collide, or be recycled.

### 3.2. Suggested data tables

```text
account
  account_id            -- opaque, immutable local PK
  lifecycle_status      -- PENDING, ACTIVE, SUSPENDED, DISABLED
  account_revision      -- monotonic version
  approved_at
  disabled_at
  disabled_reason_code

external_identity_link
  link_id
  account_id
  source_type           -- OIDC, SAML2, KERBEROS, PROXY...
  trusted_issuer        -- exact approved namespace
  external_subject      -- stable opaque subject
  link_status
  linked_at, unlinked_at
  UNIQUE(source_type, trusted_issuer, external_subject)

tenant_membership
  account_id, tenant_id
  status, valid_from, valid_until
  approved_by, approved_at

role_grant
  grant_id
  account_id, tenant_id, role_id
  source_request_id
  approved_by, approved_at
  valid_from, valid_until
  revoked_at
  UNIQUE(account_id, tenant_id, role_id, active_revision)

permission_policy
  role_id, permission, resource_scope, policy_version

lifecycle_event
  event_id              -- idempotency identity
  account_id
  source_system
  source_revision
  event_type
  received_at, applied_at
  outcome, reason
```

This is an **architectural model**, not copy-pasteable SQL DDL. Unique keys, transactions, snapshot consistency, and partial indexes must be designed for your specific DB (PostgreSQL/MySQL/etc.). When storing grants in `role_grant`, do not rely on `UNIQUE(...,active_revision)` alone across all DBs; you must still constrain **no two active duplicate grants** per actual policy.

### 3.3. Identity linking rules

1. An `ACTIVE` `(issuer, stable subject)` pair links to **exactly one** internal account at a time.
2. Multiple federated identities may point to the same account (e.g., IdP migration) **only after an evidenced and approved linking workflow**.
3. Never auto-link based on matching email or the local part before `@`.
4. An external subject changing due to IdP migration requires review—never run `toLowerCase` or strip realms to "merge them".
5. A disabled account cannot be restored merely by a SCIM "add group" event or a successful OIDC login.
6. Account reactivation must be an **explicitly approved workflow**, reviewing grants rather than restoring old permissions by default.
7. Never reuse a former employee's `internalAccountId` for a newcomer even if username/email is recycled.
8. Sensitive permissions need expiration dates, owners, and recertification; avoid "forever grants" from orphaned groups.

## 4. State Machine: Adding, Role-Changing, Locking, and Offboarding

```mermaid
stateDiagram-v2
    [*] --> PENDING: HR/owner creates request
    PENDING --> APPROVED: IAM/manager/Security approves
    APPROVED --> ACTIVE: Provision + identity link + test
    PENDING --> REJECTED: Fails policy
    APPROVED --> REJECTED: Cannot deploy
    ACTIVE --> ACTIVE: Mover: revoke old + grant approved new
    ACTIVE --> SUSPENDED: Incident / temporary suspension
    SUSPENDED --> ACTIVE: Review + approval
    ACTIVE --> DISABLED: Offboarding / departure
    SUSPENDED --> DISABLED: Contract terminated
    DISABLED --> REHIRE_REVIEW: Rehire requested
    REHIRE_REVIEW --> ACTIVE: Reverify + new approval
    REHIRE_REVIEW --> DISABLED: Rejected
    DISABLED --> [*]: Retention/anonymization per policy
```

**State is business logic, not a default Spring Security API.** To run it, you need transactional services, conditional state transitions, `accountRevision` updates, and revocation events.

### 4.1. Access decision table

| Account state | Allow new login? | Existing session access | Allow new role grant? |
| --- | --- | --- | --- |
| `PENDING` | No | No | Draft only; not yet effective |
| `APPROVED` but unprovisioned | No | No | Pending activation |
| `ACTIVE` | Yes if IdP/account/tenant policies pass | Yes per authorization + session policy | Per approval workflow |
| `SUSPENDED` | No | Must deny/revoke per scope | No |
| `DISABLED` | No | Must deny/revoke | No |
| `REHIRE_REVIEW` | No before approval | No | Never auto-restore old grants |

**Important:** Directory `ACTIVE` **does not mean all permissions**. An `ACTIVE` account without membership in tenant Alpha must still be denied when accessing tenant Alpha data.

### 4.2. State transitions require concurrency checks

For each transition, record:

- Subject/internal account ID and identity link namespace.
- Event source/type, source revision, event ID, and expected current revision.
- Requester and approver (independent from requester when policy demands).
- Prior/new status, prior/new roles/memberships, and valid-from/valid-to bounds.
- Target systems ACKed vs. errored/pending retry.
- Session/token revocation outcomes and verification timestamps.
- Audits free of secrets, raw `SAMLResponse`s, OIDC tokens, or session cookies.

Never mark a workflow complete merely because the directory wrote `enabled=false` while apps/tokens remain active.

## 5. Joiner — Controlled User Onboarding

### 5.1. Before creating an account

Start from a **trusted business decision**: valid employment/partner contract, owner, tenant, account type, role, and duties. Identify:

1. Start date/validity, manager, cost center, support team, contract end date.
2. Permitted external identity source: AD/Kerberos realm, OIDC issuer, SAML2 IdP, or partner gateway.
3. Stable subject/Directory object ID to bind the user to in the application.
4. Needed tenant(s) and resource scopes, and the **least-privilege** role bundle for the function.
5. Sensitive permissions needing extra approval, MFA/step-up, and SoD checks.
6. Whether an old account shares the email/username; if so, **never auto-merge**—verify identity proof and history.
7. Default grant lifetime, recertification schedule, and offboarding owner.

### 5.2. Standard joiner flow

```mermaid
sequenceDiagram
    participant HR as HR / Partner Owner
    participant IAM as IGA / Approvers
    participant DIR as Directory / IdP
    participant SCIM as Provisioning
    participant APP as Portal Account Service
    participant AUD as Audit
    HR->>IAM: Create approved joiner request (stable person ID, start date)
    IAM->>IAM: Check manager approval, MFA/SoD/least privilege
    IAM->>DIR: Create/enable directory identity as appropriate
    DIR-->>IAM: Stable external identity references
    IAM->>SCIM: Create/upsert app user + approved memberships
    SCIM->>APP: Versioned provisioning event / SCIM request
    APP->>APP: Link identity, create local account, grant approved roles
    APP-->>SCIM: Success + resource ID/version
    APP->>AUD: Record event, approver, snapshot/revision
    IAM->>APP: Go-live readiness check
    APP-->>IAM: Active only after policy tests
```

**Do not provision via a user-facing login callback right away** unless an explicit Joiner/JIT provisioning policy exists. JIT creation can be valid with an issuer/tenant allowlist, account anti-collision, approval, and restricted default roles; never let first login auto-grant `ROLE_ADMIN`.

### 5.3. Safe sequence

1. HR/owner submits request with an **immutable person/account reference** and start date.
2. IAM/IGA verifies owner, scope, legal basis, and SoD.
3. Directory/IdP creates the identity and assigns groups **for authentication** per policy—do not equate groups with all local roles.
4. App creates a `PENDING` local account and links `(issuer, subject)` once the source is verified.
5. Provision approved memberships and grants; enforce effective dates, blocking access before start date if policy forbids.
6. Verify local `enabled`, roles, tenant, account ownership, MFA requirements, and negative tests.
7. Flip to `ACTIVE` only after audits and required services are ready; never leave `ACTIVE` with a broken identity link.
8. Send onboarding notices without temporary credentials in insecure email/chat; guide users to SSO.
9. Configure review cycles and auto-expiry for contractors/time-bound grants.

### 5.4. Separating account existence from active permissions

A person may have a directory object and SCIM User record **before** their start date while not yet permitted to access data. Thus:

```text
T-7 days: HR approved contract, App account PENDING
T-2 days: SCIM User created with active=false or app status PENDING
T0:       Manager+IAM approval, MFA readiness; app account ACTIVE
T0+:      Tenant memberships + roles effective within scope
T+n:      Role expiry/review per policy
```

This is an **operational example**, not default SCIM or Spring Security behavior. SCIM's `active` attribute reflects the user state on the SCIM resource; the application must actually wire it to a **deny policy** for it to have security effect.

## 6. Mover — Changing Roles Without Accumulating Old Privileges

Changing groups is a **policy change**, not merely updating a department name in HR.

Suppose account `acct-1007` transfers from tenant Sales to Finance:

| Before | After (approved) |
| --- | --- |
| `tenant-sales: REPORT_READ` | Revoke Sales permission |
| `tenant-sales: CUSTOMER_EXPORT` | Revoke Sales export |
| No Finance membership | Add `tenant-finance` membership |
| No Finance grants | Grant Finance `REPORT_READ` |
| No `PAYMENT_APPROVE` | Still absent unless approved |

If the app only adds Finance while leaving Sales `CUSTOMER_EXPORT` intact, the user can access both departments' data despite having no business need.

### 6.1. Safe mover workflow

1. Detect role/team/tenant/manager change event from an authoritative source.
2. Take a **snapshot of current grants** and **approved target grants**, computing `toRemove = old - new` and `toAdd = new - old`.
3. Check **SoD**, tenant separation, admin privileges, grant expiry, and owner approvals for the target.
4. Apply changes consistently via transactions/revisions. For dangerous roles, **revoke old privileges first** or enforce a temporary deny while provisioning finishes.
5. Sync Directory/SCIM Group memberships and local app grants. When cross-system updates are non-atomic, track audits/correlation IDs, retry, and **deny at the app** while permissions are temporarily indeterminate.
6. Revoke or refresh sessions/tokens holding old authorities. Verify role changes take effect on the **next request** per SLA.
7. Test that the user has the right new permissions and **no longer holds old ones**. Both checks are mandatory.
8. Record effective date, previous/target grants, approver, revision, and rollback policy.

### 6.2. Separation of Duties (SoD)

For instance, a financial app forbids the same person from holding both `PAYMENT_CREATE` and `PAYMENT_APPROVE` in the same scope. Enforce this rule against **total effective permissions** across all group mappings, direct grants, inherited roles, and temporary elevations.

```text
oldGrants = {PAYMENT_CREATE}
requested = {PAYMENT_APPROVE}

if allowed to remove PAYMENT_CREATE first:
    target = {PAYMENT_APPROVE}
else if both would remain:
    SoD conflict -> DENY / require exception process
```

**Do not check only role names.** A user might receive `PAYMENT_APPROVE` from group A and `PAYMENT_CREATE` from group B; expand permissions to detect conflicts. Break-glass exceptions require approval, short duration, logging, monitoring, and post-review.

### 6.3. Temporary role elevation

A temporary grant for emergency support should include:

- Explicit account ID/tenant/resource.
- Minimal permissions and end timestamp.
- Reason/ticket, independent approver, and change record.
- MFA/step-up authentication if policy requires.
- Automatic expiration job plus recheck at the authorization layer.
- Early revocation/cancellation and session/token implications.
- Auditing of both successful and denied attempts.

Never hand out indefinite `SUPER_ADMIN` as an easy way to "help the newcomer get started".

## 7. Leaver — Revoking Access, Not Just Flipping One Account Switch

### 7.1. Planned vs. emergency

**Planned offboarding:** contract has an end date; prepare systems ahead of cutoff, confirm owners, transfer data lawfully, revoke grants on time, and report completion.

**Emergency suspension:** suspected account compromise, insider threat, lost partner trust, or disciplinary action. Prioritize **immediate access blocking** via central deny/revocation—do not wait for SCIM queues, directory replication, or JWT expiry.

The two flows differ in timing/approvals, yet both require removing access **across every active surface**.

### 7.2. Ordered offboarding checklist

1. Receive verified leaver signal from HR/SOC/partner owner.
2. Identify exact `internalAccountId`, external identities, tenant memberships, and application sessions; **never look up solely by email**.
3. Write `DISABLED`/`SUSPENDED` in the local authorization store or central deny gate **before/alongside** emitting downstream events; bump account revision.
4. Disable Directory/IdP credentials/login or revoke federated access per policy.
5. SCIM updates `User.active=false` (if app uses SCIM) and removes `Groups.members`/local grants accordingly; verify ACKs.
6. Revoke app `HttpSession`s across all nodes, refresh tokens/grants, API keys, personal access tokens, remember-me cookies, and other account-scoped tokens.
7. Address **already-issued access tokens**: self-contained JWTs may remain valid until `exp` if resource servers check only signature/expiry; enforce denylists/introspection/token versions or TTLs per risk policy.
8. For SAML2/CAS/OIDC SSO, coordinate IdP logout/revocation; **never assume** a logout callback always reaches every SP and clears all sessions.
9. Revoke roles/tenant memberships, privileged/delegated grants, user-owned service accounts/tokens, shared access, and app-specific workflows.
10. Execute work/data ownership transfers per policy. Never arbitrarily delete audit/legal retention records.
11. Run negative tests: fresh login fails, existing cookie fails, API token fails, direct app endpoint fails, and admin actions fail.
12. Record which systems ACKed or not, cutoff timestamp, approver, retrying events, and reconciliation owner.

### 7.3. Access surfaces to examine

| Surface | Automatically revoked when disabling AD/IdP? | How to handle |
| --- | --- | --- |
| New SSO login | Depends on issuer/session/policy | Disable account/trust, verify fresh login |
| Authenticated Spring `HttpSession` | **Not by default** | Session index, invalidate/delete/deny + check new requests |
| Spring Security `Authentication` authorities in session | Does not auto-refresh | Revoke session or check authz version/current state |
| JWT OAuth2/OIDC access token | Does not expire early automatically | Short TTL, token status/denylist, resource-server current-state policy |
| Refresh token | Depends on issuer/AS policy | Revoke at authorization server and app token grants |
| CAS/SAML SP session | Not guaranteed | SLO integration + local session revocation |
| API key / PAT | No | Revoke in app/secret store |
| User-owned service account | No | Review ownership, credentials, delegation |
| LDAP/AD group membership | May sync with delay | Reconcile groups & app permissions |
| SCIM User/Group resource | Only via provisioning flow | PATCH/DELETE/ACK and app enforcement |
| Background jobs/WebSockets | Not necessarily | Interrupt/reauthorize/drop connections per risk |
| Already exported/downloaded data | Cannot be "revoked" automatically | DLP/legal/audit/process; never promise web controls solve it |

### 7.4. Do not confuse "blocked new logins" with "no remaining access"

If a web app cached permissions in a session at 09:00 and HR disables the user at 09:05, the user can still make requests at 09:06 if the app checks only `session.isAuthenticated` and the authorities snapshot.

A sensitive design should check:

```text
authenticated identity
    AND localAccount.status == ACTIVE
    AND tenantMembership.status == ACTIVE
    AND permission currently effective
    AND session/token not revoked
    AND (MFA freshness if policy demands)
```

**The authorization source of truth** must apply cluster-wide (DB/cache version/central policy). If the authorization backend suffers an outage, sensitive actions must **fail closed**, never "temporarily grant admin during maintenance".

## 8. SCIM 2.0: User and Group Provisioning Mechanics

**SCIM** – System for Cross-domain Identity Management – standardizes identity administration APIs between provisioning clients and service providers. Two core specs:

- **RFC 7643:** `User` and `Group` data models and attributes (`id`, `externalId`, `userName`, `active`, `members`, etc.).
- **RFC 7644:** HTTP protocol for `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, filtering, bulk, and ETag/versioning when supported.

**SCIM is not a browser login protocol.** A `PATCH /Users/{id} active=false` does not automatically broadcast logout events to all Spring `HttpSession`s, JWTs, and services. The SCIM target must connect account-state changes to **authorization/session revocation**.

### 8.1. SCIM `id`, `externalId`, and `userName`

| Field | Who assigns it? | Scope / notes |
| --- | --- | --- |
| `id` | SCIM service provider (receiving app/server) | Opaque, stable, non-reused; never client-chosen on resource creation |
| `externalId` | Provisioning client (IGA/IdP) | Optional, scoped to the **provisioning domain namespace**, never assumed globally unique |
| `userName` | SCIM User attribute from provisioning data | Required by core schema, mutable per policy; never use in place of an immutable ID |
| `active` | User's administrative status | Must map carefully to local login/authorization denials |
| `groups` | Related group memberships | `groups` on User is typically read-only; membership is managed via `Group.members` |
| `meta.version` / ETag | SCIM provider when versioning is supported | Prevents lost updates; does not replace audit source revisions |
| `members` | List of User/Group member refs | May yield indirect grants via approved group mappings |

Never use `externalId="E-103"` alone as a lookup key across multiple tenants/provisioning domains. Key by `(provisioningDomain, externalId)` and map to `internalAccountId`.

### 8.2. Creating a SCIM account

Example request **for a secured SCIM endpoint only**:

```http
POST /scim/v2/Users HTTP/1.1
Host: portal.example.org
Content-Type: application/scim+json
Authorization: Bearer REDACTED_PROVISIONING_TOKEN
```

Body:

```json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User"
  ],
  "externalId": "hr:E-103",
  "userName": "a.nguyen@example.org",
  "active": false,
  "name": {
    "givenName": "An",
    "familyName": "Nguyen"
  }
}
```

Setting `active=false` illustrates a **pre-provisioning policy**: the account exists, but is not yet eligible for access. The RFC does not force organizations to provision inactive users prior to start dates.

The SCIM Server returns its assigned ID, e.g., `id="2819c223-7f76-453a-919d-413861904646"`, plus metadata if supported. The caller stores the mapping to update the right user later.

**Provisioning endpoint authentication:** must use OAuth2 `client_credentials`/scoped tokens, mTLS, or an approved machine-to-machine mechanism; never allow arbitrary browser users to POST to SCIM to mint admin accounts. Enforce scopes, rate limits, request size limits, auditing, and tenant isolation.

### 8.3. Activating or deactivating a User via PATCH

Once Joiner is approved, example SCIM PATCH:

```http
PATCH /scim/v2/Users/2819c223-7f76-453a-919d-413861904646 HTTP/1.1
Host: portal.example.org
Content-Type: application/scim+json
Authorization: Bearer REDACTED_PROVISIONING_TOKEN
If-Match: W/"revision-12"
```

Body:

```json
{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "replace",
      "path": "active",
      "value": true
    }
  ]
}
```

On Leaver:

```json
{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "replace",
      "path": "active",
      "value": false
    }
  ]
}
```

**Critical caveats not to skip:**

- `If-Match` is **optional for clients when the server supports resource versioning/ETag**; do not assume every SCIM server mandates it.
- `W/"revision-12"` is an **example value**. In real usage, read the ETag from a prior response—never fabricate server revisions.
- SCIM PATCH is **atomic on the patched resource** per RFC 7644; it does **not** provide an atomic transaction spanning multiple User/Group resources, app session stores, and the IdP.
- 200/204 indicates the SCIM operation succeeded at the service provider level; it is **not proof** that all bearer tokens and sessions were revoked.
- `active=false` only actually blocks access if app authorization/login enforcement binds that flag to account state.
- Never default to `DELETE` for leavers if history/audit/account ownership must be retained per policy. You can deprovision/disable while following approved retention/erasure rules.

### 8.4. Adding/removing Group members

Example adding a User ID to a Group via `Group.members`:

```json
{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "add",
      "path": "members",
      "value": [
        {
          "value": "2819c223-7f76-453a-919d-413861904646"
        }
      ]
    }
  ]
}
```

To revoke membership on role change/leaver:

```json
{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "remove",
      "path": "members[value eq \"2819c223-7f76-453a-919d-413861904646\"]"
    }
  ]
}
```

Use the bodies above against an authenticated `PATCH /scim/v2/Groups/{groupId}`. **Group membership does not automatically become a Spring role**: the app needs an explicit mapping `(approvedGroupId, tenant, policyVersion) → permission`. Avoid mapping straight from group display names.

A "move from Sales to Finance" event typically requires **at least two operations**: removing Sales membership/grants and adding Finance membership/grants, with SoD checks and an intermediate-state policy. If conflicting permissions could overlap simultaneously, place a deny gate until the workflow completes.

### 8.5. ETags, concurrent updates, and idempotency

Per RFC 7644, if the server supports versioning, clients can send `If-Match` so updates apply only if the current revision matches. On conflict/precondition failure, the workflow must **read the new revision, reconcile, and decide whether to update again**—never blindly retry a payload that could clobber newer changes.

Risks:

- Two provisioning workers editing group members concurrently.
- A delayed joiner event arriving after a leaver event.
- A PATCH succeeding on a resource before the HTTP response times out.
- Repeated SCIM POSTs creating duplicate accounts if idempotency/mapping checks are missing.
- Another tenant using a colliding `externalId` to edit the wrong user.

You need `eventId`/source revisions, uniqueness constraints, conditional upserts, state reconciliation, bounded retries, and error queues; **never rely solely on HTTP client retries** to achieve exactly-once event application.

## 9. LDAP/Active Directory: Where Can Accounts and Roles Come From?

Spring Security can authenticate directly against LDAP/AD, or sit behind IdP federation backed by LDAP/AD. Both architectures share **identical lifecycle needs** while differing in where authorities are loaded.

| Architecture | Authentication | Authority loading |
| --- | --- | --- |
| LDAP bind login | Spring Security `LdapAuthenticator`/LDAP bind | `LdapAuthoritiesPopulator` or local DB service |
| AD authentication | AD credentials/tickets/LDAP per design | AD groups and app-approved mapping |
| OIDC login from AD-backed IdP | Spring Security `oauth2Login`/OIDC | `OidcUserService`/`GrantedAuthoritiesMapper`, local account service |
| SAML2 login from enterprise IdP | `Saml2AuthenticationProvider` and assertion checks | Mapping authenticated SAML principal/groups to local permissions |
| CAS login from LDAP-backed CAS Server | CAS ticket validator → CAS Authentication | Local `UserDetailsService`/approved role mapping |
| Preauthenticated reverse proxy | Proxy verifies identity | `PreAuthenticatedAuthenticationProvider` → internal account/`UserDetailsService` |

### 9.1. What does `LdapAuthoritiesPopulator` do?

Spring Security LDAP supports `LdapAuthoritiesPopulator` to derive `GrantedAuthority` from directory entries and groups. When an app requires its own internal permissions:

- You can write a custom `LdapAuthoritiesPopulator` backed by DAO/JDBC to load authorized roles instead of converting every LDAP group into a Spring role.
- Clarify the user key: directory object ID/full DN/realm and account ID; never blindly query `WHERE username = ?` by display name/short name where cross-directory collisions exist.
- Roles loaded at authentication time can go **stale in-session** after directory groups change.
- A user losing an AD group is not automatically logged out of all apps while `HttpSession` and resource-server JWTs remain valid.
- Large AD groups/nested groups can have paging/recursive lookup quirks; test against your directory provider and guard against role explosion.

### 9.2. Authentication config differs from grant validity

With OIDC federation, Spring Security supports `GrantedAuthoritiesMapper` and delegating `OidcUserService` to map authorities at **login time**. A login-time mapping does not automatically update the session when a manager later removes a group.

With LDAP, `DefaultLdapAuthoritiesPopulator` searches groups by filter; role mapping and SoD still require business policies. **You cannot replace all JML requirements with "just sync AD groups".**

## 10. Spring Security 6: Enforcement at Request and Method Boundaries

This lesson does not build a full IdP or SCIM Server. The snippet below focuses on a **Portal app already configured with OIDC federation** that reads local account grants when needed.

### 10.1. Dependencies

In a Spring Boot 3 / Java 17 project with the Boot plugin and dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

**Requirements to run real OIDC:** the app must have valid `ClientRegistration`/provider metadata, redirect URIs, client credentials from a secret manager, HTTPS callbacks, and proper issuer trust config. Never let clients supply arbitrary issuer/JWKS URLs to become trusted IdPs.

### 10.2. SecurityFilterChain and method security

File `src/main/java/com/example/lifecycle/WebSecurityConfig.java`:

```java
package com.example.lifecycle;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/", "/error").permitAll()
                    .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}
```

**Never disable CSRF globally for browser apps.** If exposing SCIM provisioning endpoints, place them in a **separate security chain** with machine-to-machine authentication, scopes/mTLS, request validation, and auditing; never allow OIDC browser `ROLE_USER` clients to call SCIM mutation APIs.

### 10.3. File `AccountAuthorizationPolicy.java`: current permission lookup

An **in-memory fixture** example highlighting boundaries, not a replacement for a DB in production:

```java
package com.example.lifecycle;

import java.util.Map;
import java.util.Set;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.stereotype.Component;

@Component("accountPolicy")
public final class AccountAuthorizationPolicy {
    private record ExternalKey(String issuer, String subject) {}
    private record LocalAccount(
            String internalId, boolean active,
            Map<String, Set<String>> tenantGrants) {}

    // DEMO ONLY: production must use a DB/permission service,
    // with versioning, event updates, and transaction consistency.
    private final Map<ExternalKey, LocalAccount> accounts = Map.of(
        new ExternalKey("https://idp.example.org/realms/company", "sub-alice"),
        new LocalAccount("acct-1007", true,
            Map.of("tenant-finance", Set.of("REPORT_READ"))),
        new ExternalKey("https://idp.example.org/realms/company", "sub-bob"),
        new LocalAccount("acct-2004", false,
            Map.of("tenant-finance", Set.of("REPORT_READ")))
    );

    public boolean canRead(
            Authentication authentication, String tenantId) {
        if (authentication == null || !authentication.isAuthenticated()
                || !(authentication.getPrincipal() instanceof OidcUser user)) {
            return false;
        }

        String issuer = user.getIdToken().getIssuer().toString();
        String subject = user.getIdToken().getSubject();
        LocalAccount local = accounts.get(new ExternalKey(issuer, subject));

        return local != null
                && local.active()
                && local.tenantGrants()
                        .getOrDefault(tenantId, Set.of())
                        .contains("REPORT_READ");
    }
}
```

**Explanation:**

- Spring Security authenticates the OIDC login with the configured IdP and creates `OidcUser`. The code above **does not validate ID tokens from a browser body itself**; it uses the principal already verified by the security filter chain.
- The `issuer + subject` pair acts as the identity key; `email` or `preferred_username` is insufficient.
- If the local account is **not `ACTIVE`**, `canRead` returns `false` even if the user holds an OIDC SSO session.
- Grants must match both `tenantId` and permission. A user cannot pick another tenant and reuse the old tenant's `REPORT_READ`.
- In production, replace the map with an **authoritative DB/policy store** updated by the JML workflow; any cache must enforce TTL/invalidation and a deny gate.
- A disabled account may still hold an old OIDC session. Method policy reading current state blocks actions as soon as local data updates; session/token revocation must still be implemented separately per requirements.
- This is a policy for one action; other permissions need corresponding method guards or attribute-based checks.
- Never call `OidcUser.getIdToken().getSubject()` on principals from SAML/CAS/Kerberos via blind casts; use a dedicated identity adapter per federation mechanism.

### 10.4. File `ReportService.java`: tenant-bound permissions

```java
package com.example.lifecycle;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("@accountPolicy.canRead(authentication, #p0)")
    public String readReport(String tenantId) {
        return "Report for " + tenantId;
    }
}
```

File `AppController.java`:

```java
package com.example.lifecycle;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AppController {
    private final ReportService reports;

    public AppController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/")
    public String publicHome() {
        return "Portal";
    }

    @GetMapping("/tenants/{tenantId}/reports")
    public String report(@PathVariable String tenantId) {
        return reports.readReport(tenantId);
    }
}
```

**Conditional behavior:**

- OIDC user `sub-alice` from the trusted issuer on tenant `tenant-finance` → receives `Report for tenant-finance`.
- Same user requesting `/tenants/tenant-sales/reports` → 403.
- Disabled OIDC user `sub-bob` → 403 even with a valid ID Token.
- Anonymous request to a protected route → Spring Security prompts login.
- The results above require valid IdP/OIDC client config, a Spring Boot main class, and the beans shown. **This is Spring Boot code requiring project dependencies**, not a standalone Java file runnable via `javac`.

### 10.5. Bringing JML into a local account service

The in-memory `AccountAuthorizationPolicy` is for learning only. Production needs:

- An identity link repository unique on `(issuer, subject)`.
- Account status and revision (`ACTIVE`/`DISABLED`).
- Tenant membership + role/permission grant repositories with `validFrom`/`validUntil`.
- A **trusted lifecycle processor** accepting authenticated SCIM/IGA events, validating approvals, writing DB transactions, and bumping revisions.
- Events/outbox to revoke sessions and invalidate permission caches.
- Authorization guards reading **effective** state on sensitive requests rather than copying authorities once at login.
- Session indexing by account ID or token versions for emergency revocation.
- Retries/reconciliation and auditing when downstream provisioning updates fail.

**Never expose an unauthenticated public `@PostMapping("/users/{id}/disable")`**. Lifecycle-changing endpoints must use machine-to-machine identity, dedicated scopes/roles, signed/audited events, rate limiting, and SoD approval.

## 11. Standalone Java 17+: Simulating JML Events, Revisions, and Offboarding

The program below **runs standalone on JDK 17+** without Spring, DB, CAS, SAML, or OIDC. It illustrates a **state machine**, explicit approvals, zero default roles, duplicate events, stale events, and access revocation. It is not a production provisioning engine; `approved=true` in the demo is a test fixture, **not proof of signature/approval**.

File `UserLifecycleDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public final class UserLifecycleDemo {
    enum State { ACTIVE, DISABLED }
    enum Kind { CREATE, GRANT, REVOKE, DISABLE, REACTIVATE }

    record Event(
            String id,
            String accountId,
            long revision,
            Kind kind,
            String permission,
            boolean approved) {}

    record Account(
            long revision,
            State state,
            Set<String> permissions) {}

    static final class Registry {
        private final Map<String, Account> accounts = new HashMap<>();
        private final Set<String> appliedEvents = new HashSet<>();

        String apply(Event event) {
            if (appliedEvents.contains(event.id())) {
                return "DUPLICATE";
            }

            Account before = accounts.get(event.accountId());
            if (before != null
                    && event.revision() <= before.revision()) {
                return "STALE";
            }

            if (before == null) {
                if (event.kind() != Kind.CREATE || !event.approved()) {
                    return "DENIED";
                }
                accounts.put(event.accountId(),
                        new Account(event.revision(),
                                State.ACTIVE, Set.of()));
                appliedEvents.add(event.id());
                return "CREATED";
            }

            Account after;
            String outcome;
            switch (event.kind()) {
                case CREATE -> {
                    return "DENIED";
                }
                case GRANT -> {
                    if (!event.approved()
                            || before.state() != State.ACTIVE
                            || event.permission() == null
                            || event.permission().isBlank()) {
                        return "DENIED";
                    }
                    Set<String> roles =
                            new HashSet<>(before.permissions());
                    roles.add(event.permission());
                    after = new Account(event.revision(),
                            State.ACTIVE, Set.copyOf(roles));
                    outcome = "GRANTED";
                }
                case REVOKE -> {
                    Set<String> roles =
                            new HashSet<>(before.permissions());
                    roles.remove(event.permission());
                    after = new Account(event.revision(),
                            before.state(), Set.copyOf(roles));
                    outcome = "REVOKED";
                }
                case DISABLE -> {
                    after = new Account(event.revision(),
                            State.DISABLED, Set.of());
                    outcome = "DISABLED";
                }
                case REACTIVATE -> {
                    if (!event.approved()) {
                        return "DENIED";
                    }
                    // Rehire does not auto-restore grants held before leaving.
                    after = new Account(event.revision(),
                            State.ACTIVE, Set.of());
                    outcome = "REACTIVATED";
                }
                default -> throw new IllegalStateException(
                        "Unknown event");
            }

            accounts.put(event.accountId(), after);
            appliedEvents.add(event.id());
            return outcome;
        }

        boolean can(String accountId, String permission) {
            Account a = accounts.get(accountId);
            return a != null
                    && a.state() == State.ACTIVE
                    && a.permissions().contains(permission);
        }
    }

    public static void main(String[] args) {
        Registry r = new Registry();
        String id = "acct-7";

        System.out.println(r.apply(new Event(
                "e1", id, 1, Kind.CREATE, "", true)));
        System.out.println(r.apply(new Event(
                "e2", id, 2, Kind.GRANT, "REPORT_READ", true)));
        System.out.println("Read before mover: "
                + r.can(id, "REPORT_READ"));

        System.out.println(r.apply(new Event(
                "e3", id, 3, Kind.REVOKE, "REPORT_READ", true)));
        System.out.println("Read after revoke: "
                + r.can(id, "REPORT_READ"));
        System.out.println(r.apply(new Event(
                "e4", id, 4, Kind.GRANT, "REPORT_EXPORT", true)));

        System.out.println(r.apply(new Event(
                "e5", id, 5, Kind.DISABLE, "", true)));
        System.out.println("Export after disable: "
                + r.can(id, "REPORT_EXPORT"));
        System.out.println(r.apply(new Event(
                "e4", id, 4, Kind.GRANT, "REPORT_EXPORT", true)));
        System.out.println(r.apply(new Event(
                "e6", id, 6, Kind.GRANT, "TENANT_ADMIN", true)));
        System.out.println(r.apply(new Event(
                "e7", id, 3, Kind.REVOKE, "REPORT_EXPORT", true)));
        System.out.println(r.apply(new Event(
                "e8", id, 7, Kind.REACTIVATE, "", false)));
        System.out.println(r.apply(new Event(
                "e9", id, 8, Kind.REACTIVATE, "", true)));
        System.out.println("Old role after rehire: "
                + r.can(id, "REPORT_EXPORT"));
    }
}
```

Compile and run:

```bash
javac UserLifecycleDemo.java
java UserLifecycleDemo
```

**Exact stdout:**

```text
CREATED
GRANTED
Read before mover: true
REVOKED
Read after revoke: false
GRANTED
DISABLED
Export after disable: false
DUPLICATE
DENIED
STALE
DENIED
REACTIVATED
Old role after rehire: false
```

**Reading the results:**

- `CREATE` with approval and revision 1 creates an `ACTIVE` account with **zero roles**.
- `GRANT REPORT_READ` is permitted while active; mover removes it via `REVOKE` before granting `REPORT_EXPORT`.
- `DISABLE` sets state `DISABLED` **and clears all permissions** in the demo model.
- Repeated event ID `e4` is blocked as `DUPLICATE`.
- Event `e6` has a newer revision, yet tries to grant `TENANT_ADMIN` to a `DISABLED` account → `DENIED`, never reactivating.
- Event `e7` with revision 3 arrives late after revision 5 → `STALE`, does not overwrite state.
- Unapproved rehire → `DENIED`; approved rehire → `ACTIVE` **with an empty grant set**, requiring fresh permission requests.
- Never trust an `approved` boolean from a real public JSON payload as proof of approval. Production must verify signer/service identity, workflow state, approver, and source revision in the DB.
- `HashMap`/`HashSet` are not thread-safe; multi-node applications need DB transactions/optimistic locking and persisted event idempotency. Never run this demo as a real user management service.
- The program cannot revoke `HttpSession`/JWT/SCIM groups; those require separate integrations.

### 11.1. Limitations of a single revision number

A single `Account.revision` in the demo assumes one **globally ordered** source stream. Real systems receive events from HR, IGA, SCIM, and app admins, each with its own sequence. **Never compare HR revision 42 with SCIM revision 12 to guess which is newer.**

Production can use:

- `sourceSystem` + `sourceRevision` for per-source ordering.
- One canonical `accountRevision` in the DB once the policy engine merges updates.
- Explicit priority for **`DISABLED` / security deny** over delayed grant events.
- Persisted event IDs and inbox deduplication.
- An outbox to emit revocations after the DB transaction commits.
- Periodic reconciliation to fix missed events.

**A `DISABLED` leaver must never become `ACTIVE` again due to a delayed joiner provisioning event**, even with a recent timestamp. Rehire is a special transition requiring owner approval, never inferred from a login event.

## 12. Asynchronous Events, Idempotency, and Consistency

### 12.1. One change can traverse multiple queues

```mermaid
sequenceDiagram
    participant HR as HR/IGA
    participant Q as Event Bus
    participant DB as App Account DB
    participant R as Revocation Service
    participant S as Session/Token Store
    participant API as Protected API
    HR->>Q: account DISABLED rev 55
    Q->>DB: Delivery 1
    DB->>DB: Transaction: status disabled + version 55
    DB->>R: Outbox revoke sessions/tokens
    R->>S: Delete/deny active sessions
    R-->>DB: ACK or retry result
    Q->>DB: Duplicate delivery rev 55
    DB-->>Q: Idempotent no-op
    Q->>DB: Late role grant rev 54
    DB-->>Q: Reject stale/blocked
    API->>DB: Current account status?
    DB-->>API: DISABLED
    API-->>API: Deny even if old token present
```

**At-least-once delivery** is the norm; never assume events arrive exactly once or in order. If a role grant arrives after a disable, enforce rules that never re-enable or grant permissions to disabled accounts.

### 12.2. Inbox/outbox design

**Inbox** at the account service:
- Unique `eventId` (deduplication).
- Source/tenant/account scope, source revision, and event type.
- Signature/mTLS/authenticated caller validation and approved workflow verification.
- Apply inside a transaction with optimistic locking.
- Record outcome: `APPLIED`, `DUPLICATE`, `STALE`, `DENIED`, or `RETRYABLE_ERROR`.

**Outbox** in the same transaction as the account change:
- `ACCOUNT_DISABLED`/`ROLE_REVOKED` event with `accountId` + revision.
- Downstream consumers revoke app sessions, caches, refresh grants, and API tokens.
- Retries with backoff and dead-letter/alerts on missing ACKs.
- Never emit external notifications before the DB transaction commits, or downstream systems observe inconsistent state.

**Atomicity:** a DB transaction guarantees internal account+outbox consistency, but does not automatically turn the SCIM service, Redis session store, and IdP revocation into **one** distributed transaction. Track per-destination progress and fail-closed rules.

### 12.3. Event ordering and precedence

| Event sequence | Safe behavior |
| --- | --- |
| Create rev1 → Grant rev2 | Create account, grant approved role |
| Grant rev2 arrives before Create rev1 | Do not auto-create role; retry/quarantine per ordering contract |
| Disable rev5 → late Grant rev4 | Reject stale grant |
| Disable rev5 → Grant rev6 | **Reject** if account is disabled, even with higher revision |
| Duplicate Disable rev5 | Idempotent; do not emit unbounded side-effect spam |
| Approved Rehire rev8 | May reactivate to `ACTIVE` per policy; **never resurrect old grants** |
| Role expiry while user holds JWT | Authorization deny/current-state/version check or token revocation per SLA |
| SCIM Group update succeeds while app cache is stale | Invalidate/bump revision; test actual resource access |
| One target system fails to ACK | Do not report global completion; retry/alert |
| HR leaver while IGA still has pending joiner ticket | Hold/deny pending grants per lifecycle precedence |

### 12.4. Reconciliation does not replace immediate denial

Queues can drop messages or consumers can have bugs. Reconciliation should:
1. Read desired state from HR/IGA policies and actual state from Directory/SCIM/apps.
2. Compare by stable account/tenant IDs, never matching by email.
3. Detect discrepancies: accounts that should be disabled still active, orphan roles, expired grants still active, users missing mappings.
4. Emit corrective events/requests with revisions and audits—never overwrite blindly.
5. For mismatches risking unauthorized access, apply **immediate deny** instead of waiting for a nightly batch.
6. Emit per-target metrics/SLAs and outcomes.

**Never treat the current state of a compromised app as the "source of truth" to write back to HR/IGA.** Select source-of-truth per attribute type.

## 13. Login Sessions, Tokens, and When Permission Changes Take Effect

### 13.1. What Spring Security saves on login

Spring Security places `Authentication` into `SecurityContext`. In stateful browser apps, it can be persisted into `HttpSession` via `SecurityContextRepository`. Authorities in the token/session reflect permissions **at authentication time**, and do not automatically refresh when role tables change.

In Spring Security 6, custom authentication filters/controllers are responsible for persisting context properly. However, **saving a session does not automatically create a revocation mechanism**.

```text
09:00 Login / OIDC, Authentication authorities = [REPORT_READ]
09:05 IAM revokes REPORT_READ
09:06 Browser sends JSESSIONID
       If app trusts stale authorities only -> may still allow
       If app checks current local grants/revision -> deny
```

### 13.2. Permission freshness strategies

| Strategy | Benefits | Limitations |
| --- | --- | --- |
| Load permissions at login | Fast after login | Roles go stale in-session |
| Load permissions on every request | Near-request-time accuracy | DB/network cost; needs caching/failure policy |
| Read fresh permissions on sensitive methods | Enforces at business boundary | Must apply consistently across all routes/resources |
| Account authorization revision/epoch | Detects rights changes quickly | Requires shared store/invalidation |
| Revoke all account sessions on mover/leaver | Limits stale app sessions | Needs session index + multi-node coverage |
| Short-lived access tokens + refresh checks | Shrinks stale-JWT window | No instant stop before `exp` without denylist |
| Token introspection/revocation | Centralized active-status check | Latency/availability and token-type support |
| IdP/SSO logout | Ends SSO session | Does not guarantee app sessions/tokens are cleared |

**Core lesson:** "how fast permission changes take effect" is a **security SLA**, not just directory sync latency. Revoking `TENANT_ADMIN` must block access much faster than changing a UI preference.

### 13.3. OIDC, SAML2, and CAS handle logout differently

- **OIDC/OAuth2:** authorization servers may support refresh-token revocation/end-session/back-channel logout depending on profile; JWT access tokens at resource servers may persist until expiry. Spring `oauth2Login`/sessions and resource-server bearer auth are two separate layers.
- **SAML2:** Single Logout works only if both sides support/configure/test it; IdP logout does not automatically invalidate all SP sessions.
- **CAS:** CAS Single Logout callbacks must match the right app session by ticket/`SessionIndex`; across multiple nodes, in-memory maps fail—test clustering.
- **Kerberos:** TGT/OS ticket caches and app `HttpSession`s have separate lifecycles; disabling AD does not necessarily destroy app sessions.
- **Reverse-proxy preauth:** the proxy may clear its SSO cookie while origin app sessions survive unless every request is gated or revoked.

**Do not confuse "the user logged out of the IdP" with "every action on the Portal is blocked immediately".** Verify enforcement at the app/resource server.

### 13.4. Revocation in multi-node environments

If the app runs across multiple pods:

- Session stores must be shared (Spring Session Redis/JDBC) or use cluster-aware revocation.
- Use a session index keyed by `internalAccountId`, namespaced by app/tenant.
- Every node must consult the same status/revision deny gate; no pod may retain old permissions past SLA.
- Cache invalidation must be confirmed, not fire-and-forget assumed "done".
- Issued JWT access tokens are separate from `HttpSession`; deleting a Redis session **does not invalidate a JWT**.
- WebSockets/batch jobs/long-running requests may have captured authentication prior to revocation; define policies for active operations when risk is high.
- Monitor `session_delete_failure`, `authz_cache_stale`, `downstream_unacknowledged`, `request_after_disable`, and `token_replay` signals.

## 14. Least Privilege, SoD, and Approvals

### 14.1. Never treat IdP roles as app roles

Suppose an IdP assertion contains `groups=["Admins"]`. Never write:

```java
// ANTI-PATTERN: external group display name treated as admin.
if (claims.toString().contains("Admins")) {
    granted.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
}
```

The right approach is explicit mapping:

```text
trusted issuer + immutable group object ID + tenant
      -> approved mapping policy/version
      -> local permission / role
      -> expiration / request approval
```

Group names can collide across tenants and IdPs; whenever admin privileges stem from an external claim, verify claim origin, group membership, issuer/audience, and business owner.

### 14.2. High-privilege grants require dual approval

Sensitive grants should require:
- Manager/resource owner.
- Security/IAM owner or dedicated independent approver.
- SoD policy validation across **total effective permissions**.
- Time-bound activation, revocation workflows, and recertification.
- Never letting the requester self-approve their own grant.
- Full auditing of who requested, approved, executed, and verified.

Break-glass access requires a targeted emergency workflow with MFA, session monitoring, very short expiry, and post-incident review—never reuse it to bypass routine daily processes.

### 14.3. Evaluating grant validity per request

A practical guard logic:

```text
allow(subject, tenantId, resourceId, action, atTime):
    verified = request.Authentication from trusted mechanism
    local = identityLink(verified.issuer, verified.subject)
    require local.account.status == ACTIVE
    require local.account NOT IN revoked/disabled list
    require valid tenantMembership(local.account, tenantId, atTime)
    require grantAllows(local.account, tenantId, action, resourceId, atTime)
    require separationOfDutiesSatisfied(local.account, action)
    require MFA freshness for high-risk action if policy requires
    return ALLOW
otherwise DENY
```

This is **policy pseudocode**, not a built-in Spring Security API. `@PreAuthorize` or `AuthorizationManager` can call an internal service to execute these checks. Never check only `ROLE_USER` and allow access across all tenants.

## 15. Resilience, Provisioning Errors, and Auditing

### 15.1. Each target system can fail independently

| Scenario | Risk | Mitigation |
| --- | --- | --- |
| HR creates Joiner, IdP create fails | App account orphaned or start date misaligned | Keep not `ACTIVE`, retry idempotently |
| Directory create OK, SCIM POST times out | Duplicate app users on blind retry | Save `externalId`/client event ID; GET/reconcile before recreating |
| Duplicate role grant event | Unintended permission/side-effect duplication | Idempotent event ID + DB unique constraints |
| Delayed leaver event | User retains access past cutoff | Immediate local deny gate; prioritize security revocation |
| Mover removes role A fails, adds B succeeds | User holds conflicting A+B permissions | SoD deny/intermediate inactive state; retry removal |
| SCIM `User.active=false` OK, Group remove fails | App might still evaluate group permissions if active unchecked | Check disabled status before any grants |
| Session deletion fails | Stale authenticated sessions | Retry/backoff/alert; authz denies by current state |
| Cache invalidation missed on one node | Node keeps honoring revoked role | Revision checks/readiness/force refresh |
| Account linked by email after IdP migration | Account takeover / tenant mix-up | Proof-based linking, immutable IDs, collision checks |
| IAM/DB outage during admin action | Cannot verify current permissions | Fail closed; never grant admin from stale caches |
| CAS/SAML SLO callback lost | SP app session remains active | Local session index/revocation; don't rely solely on IdP logout |

### 15.2. What must be audited

- Lifecycle event ID, source, account ID, tenant, prior/current state, and revision.
- Requester, approver(s), effective date, and necessary business/incident reason.
- Granted/revoked permission IDs, resource scope, expiry, and role policy version.
- SCIM resource IDs/ETag outcomes, downstream statuses, and retry attempts.
- Session/token revocation acknowledgments and negative-test timestamps.
- Safe denial reasons that never leak other users' existence on public APIs.
- Reconciliation findings, exception approvals, and post-mortems.
- **Never log** passwords, refresh tokens, raw `SAMLResponse`s, ID/access tokens, CAS STs, `JSESSIONID`s, unnecessary private group memberships, or PII beyond retention policy.

### 15.3. Privacy and data deletion

On leaver events, sometimes audits/work documents must be kept under retention and legal hold; sometimes unneeded personal data must be deleted or anonymized. **Disabling an account and immediately deleting all data are two separate decisions.** Never delete `accountId`/audits before completing ownership transfers, mandatory retention, and legal/policy compliance.

## 16. Testing JML from Source Data to Actual Runtime Permissions

### 16.1. Functional and security matrix

| Scenario | Expected result |
| --- | --- |
| Unapproved Joiner | Neither `ACTIVE` nor holding grants |
| Approved Joiner, app user not yet provisioned | Cannot log in successfully by auto-creating an account |
| Directory user active while local account `PENDING` | Application denies |
| Provision duplicate `externalId` from different provisioning domain | Users are not mis-merged |
| Identical OIDC `sub` from two issuers | Two distinct external identity keys |
| Email matching an old account | No auto-linking or inheriting old permissions |
| User granted `REPORT_READ` in tenant A | Accesses tenant A report if resource policy passes |
| User A changes URL to tenant B | 403 without tenant B membership/grant |
| Mover Sales→Finance | Sales permissions removed, Finance matches approved set |
| Mover adds Finance without removing Sales | Test catches privilege creep |
| Mover violates SoD | Rejected / exception workflow; no auto-grant |
| SCIM PATCH User `active=false` | Local account disabled and new requests denied |
| SCIM Group member removed | Local group mappings/permissions update accurately |
| SCIM PATCH with stale ETag | Conflict/precondition; never silently overwrites |
| Delayed role grant after Disable | Never auto-reactivates user |
| Duplicate event ID | Idempotent; no duplicate grants/subscriptions |
| Unapproved rehire | Remains disabled |
| Approved rehire | Never auto-restores pre-offboarding grants |
| Local user disabled while IdP still logs in | App returns 403/denies per local policy |
| Session authenticated before role revocation | Revocation/guard blocks old action within SLA |
| Unexpired JWT access token after leaver | Resource-server denies or enforces bounded policy window |
| SCIM server returns 200 while session survives | Test **catches** incomplete offboarding |
| One cluster node has stale cache | Does not bypass revocation; alerts/readiness catch it |
| SCIM/DB IAM outage | Never auto-grants admin; retries/alerts |
| Emergency suspension | Central deny takes effect before/alongside provisioning |
| Long-running/WebSocket action | Handled per risk policy |
| App local logout while IdP session stays alive | SSO may re-login; access still checks local status |
| Missing audit on high-risk admin change | Process test/alert fails |

### 16.2. Testing across three layers

**Provisioning layer:** HR/IGA approvals, SCIM requests, group memberships, account status, and revisions. Use staging identities and protect provisioning tokens.

**Authentication layer:** OIDC/SAML/CAS/Kerberos/proxy identities validated for right issuer/subject without email auto-linking. Disabled app users must be rejected even if IdP authentication succeeds.

**Authorization/revocation layer:** access resources using **existing session cookies and bearer tokens** issued before the change. This is the single most important check that happy-path provisioning tests routinely miss.

Never just check "SCIM PATCH returned 204" and mark a leaver complete while an app session can still access resources.

### 16.3. Two-request test suite to detect stale permissions

1. Log in as a user with `REPORT_EXPORT`, saving the browser cookie/app session and API access token (if supported).
2. Confirm export works while approved per tenant policy.
3. Dispatch a mover event revoking `REPORT_EXPORT`, record revision, and collect downstream ACKs.
4. Resend the export request using **that exact old session cookie**.
5. Expected: 403/deny within the revocation SLA; if 200, track down stale authorities/caches.
6. Send a request to the resource server using the old access token to verify real revocation/TTL behavior.
7. Send a still-valid read-only request to avoid conflating "revoke everything" with "revoke export only".
8. Repeat while load-balancing to node B, with stale Redis caches, and with delayed IGA events.
9. Repeat for a leaver: old cookie, old token, fresh login, and direct-origin requests must all be blocked.
10. Capture evidence with zero raw tokens in logs or test reports.

### 16.4. Testing the Java 17 code

Run `UserLifecycleDemo.java` per section 11 and compare against exact stdout. The demo illustrates policy logic and **does not replace testing real SCIM, OIDC IdP, LDAP/AD, Spring Session, or DB concurrency**.

### 16.5. Building Spring Boot examples

In a project with the Gradle wrapper:

```bash
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-oauth2-client
./gradlew compileJava
./gradlew test
```

On Windows use `.\gradlew.bat`. The Spring code examples need a `PortalApplication` main class to run as a real web app, plus OIDC `ClientRegistration` and issuer client credentials; passing `compileJava` **does not prove** end-to-end SCIM provisioning/IdP/logout without that infrastructure.

## 17. Symptom-Based Diagnostics

| Symptom | Likely cause | Remediation |
| --- | --- | --- |
| New user appears in AD yet Portal won't log in | App not provisioned/linked/`ACTIVE`, wrong issuer/subject | Check identity links, SCIM ACKs, state |
| User logs in via OIDC yet gets 403 | Local account unapproved or missing grants/tenant | Check local entitlements; do not rush to grant admin |
| User changed departments yet still sees old data | Old role not revoked, stale session/cache | Diff desired vs. effective grants; revoke/refresh |
| SCIM PATCH `active=false` returns 204 yet user still accesses | App doesn't enforce disabled or JWT session lingers | Enforce local status; revoke sessions/tokens |
| SCIM PATCH `Group.members` returns 412 | Stale ETag | Fetch latest ETag, reconcile, retry conditionally |
| SCIM POST retry creates duplicate user | Missing idempotency/mapping | Deduplicate events, check `externalId`/domain, lookup + unique constraint |
| Accounts merged because of email | Identity linking keyed on mutable email | Link `issuer+stable subject`; run migration review |
| Spring `hasRole` doesn't recognize role | `ROLE_` prefix / authority naming mismatch | Check `GrantedAuthority` and `hasRole` vs. `hasAuthority` |
| Local grants revoked yet `@PreAuthorize` doesn't fire | Missing `@EnableMethodSecurity` or self-invocation | Enable it and invoke through Spring-managed proxy |
| One pod still holds admin rights | Cache/session/revision mismatch | Distributed invalidation and authorization recheck |
| JWT stays active after disable | Resource server verifies only signature/exp | Check revocation status/token version/introspection |
| Directory outage causes fail-open | "Temporarily allow" fallback | Fail closed for sensitive actions; alert |
| Leaver then rehire auto-gets admin | Reused old grants / auto-enable | Explicit approval; no grant resurrection |
| Role group names differ yet object IDs match | Display-name-based mapping | Map by stable group object ID + tenant scope |
| SCIM delete wipes audit/ownership | Flawed retention policy | Disable and run retention/transfer workflows |
| System A mover event overwrites System B leaver | Missing precedence/source revision | Canonical state machine with tombstone/deny |
| Instant re-login after local logout | IdP/CAS SSO session still active | Local deny/reauth policies; don't confuse logout layers |
| Cannot prove who approved a role | Missing approval/audit store | SoD, approval records, reconciliation |

## 18. Operational Checklists

### Joiner

- [ ] HR/owner source verified identity and start date.
- [ ] Immutable account reference exists; no email auto-linking.
- [ ] Issuers/subjects and provisioning domains are approved.
- [ ] Manager/IAM/Security approvals complete per role risk.
- [ ] SoD/least privilege/MFA verified.
- [ ] Account created `PENDING`; never auto-`ACTIVE` before cutoff/approval.
- [ ] SCIM/Directory updates track mapped IDs, revisions, and ACKs.
- [ ] Tenant memberships/local grants match business need with expiry/reviews.
- [ ] Positive/negative login and resource authorization tests pass.
- [ ] Full audit trail and assigned support owner exist.

### Mover

- [ ] Old/new role diffs computed; old permissions removed.
- [ ] SoD, tenant scopes, and temporary elevation expiries checked.
- [ ] Events carry revisions/approvals; stale duplicates rejected.
- [ ] Directory groups + SCIM groups + local grants synced.
- [ ] Sessions/permission caches updated or revoked.
- [ ] User **no longer** holds old permissions via old cookie/token.
- [ ] Audit trail and rollback plan prevent restoring unauthorized privileges.

### Leaver / Emergency suspend

- [ ] Account/local deny state enabled at cutoff.
- [ ] New IdP/Directory logins blocked or trust revoked.
- [ ] SCIM `active=false`/group removals/local grants updated; all targets ACKed or retrying/alerting.
- [ ] App `HttpSession`s revoked/denied cluster-wide.
- [ ] Refresh tokens, API keys/PATs, and self-contained JWTs handled per token policy.
- [ ] Privileged/delegated grants, WebSockets/jobs, and user-owned service accounts reviewed.
- [ ] Fresh login, old cookie, old bearer token, and direct routes pass negative tests.
- [ ] Auditing, ownership transfers, and data retention/erasure follow policy.
- [ ] Never declare DONE while any target lacks ACK or old sessions remain untested.

## 19. Self-Check Questions

**1. What does JML stand for?**

Joiner (adding a user), Mover (changing position/role), and Leaver (ending relationship/access). These workflows require coordinating HR/IGA, directory/IdP, provisioning, local grants, and session/token revocation.

**2. Why does a successful IdP login not automatically allow a user to use the Portal?**

The IdP authenticates identity. The Portal must still verify an `ACTIVE` local account, valid identity link, tenant membership, permission grants, and session/token policies.

**3. When creating a user via SCIM, how do `id` and `externalId` differ?**

`id` is assigned and stably maintained by the service provider; `externalId` is set by the provisioning client and scoped to the provisioning domain. Never merge IDs across sources just because strings match.

**4. Why should users never be linked by email?**

Emails can change, collide, or be recycled. Federated identity must rely on verified issuer/realm plus a stable subject.

**5. Why must Mover check removed permissions as well as added ones?**

Failing to remove old permissions causes privilege accumulation, violating least privilege, tenant isolation, and Separation of Duties.

**6. What is SoD?**

Separation of Duties prevents one person from simultaneously holding conflicting permissions (e.g., creating and approving their own payment). Evaluate against total effective permissions, including inherited group grants.

**7. Does SCIM `PATCH active=false` automatically log the user out of every application?**

No. SCIM updates the user resource at the service provider. Apps must enforce account-disabled checks and revoke/deny sessions, tokens, and permissions by design.

**8. Why is atomic SCIM `PATCH` insufficient for full offboarding?**

It is atomic only on **one SCIM resource** per RFC, not a multi-system transaction across the IdP, groups, app DB, Redis sessions, JWT issuer, and resource servers.

**9. If a Grant event arrives after Disable with a higher revision, what should happen?**

Never grant permissions to a `DISABLED` account; reactivation must go through an approved new workflow rather than letting a grant event resurrect the account.

**10. Why can Spring `Authentication.getAuthorities()` go stale?**

Authorities are typically computed at login time and stored in `SecurityContext`/`HttpSession`. When permissions change, the app must refresh/recheck/revoke within SLA.

**11. Why does deleting an `HttpSession` not revoke a JWT access token?**

Resource servers can accept JWTs independently until `exp` if they check only signature/expiry. You need token status/introspection/versioning/denylists or short lifetimes per policy.

**12. Can SCIM `Group.members` automatically become Spring `ROLE_ADMIN`?**

Not by default. You need an explicit approved `(group object ID + issuer/tenant) → permission` mapping and SoD checks.

**13. Should a rehire restore previous grants?**

Not by default. Reactivation requires verifying identity, account ownership, and approvals; old permissions may no longer be appropriate.

**14. SCIM PATCH returned HTTP 204—is the Leaver workflow finished?**

Not necessarily. Verify local denial, session/token revocation, group grants, all downstream ACKs, and negative tests.

**15. With multiple provisioning sources, why can't revisions be compared directly?**

Each source has its own sequence. Maintain per-source ordering plus a canonical account revision and precedence in the policy engine.

**16. In Spring Security, what is the role of `@EnableMethodSecurity`?**

Enables method-level authorization such as `@PreAuthorize`. Configuring URL matchers in `SecurityFilterChain` alone does not activate method security annotations.

**17. What are the most important tests after revoking a role?**

Replay requests using **cookies/tokens issued prior to revocation** and confirm the old action is blocked, including when routed to another node.

**18. If Directory/IGA is unreachable during an admin action request, what should you do?**

Never allow access based on possibly stale old admin rights; fail closed or follow a security-approved outage policy with logging and alerts.

**19. For a contractor with an end date, what should be automated?**

Expiring grants/memberships, scheduled deprovisioning, session/token revocation, owner notifications, auditing, and post-cutoff verification—never rely solely on managers remembering to revoke manually.

**20. When should emergency suspension be used instead of planned offboarding?**

When compromise or urgent risk is suspected. Block app access/deny and revoke sessions first, then complete provisioning/reconciliation—never wait in normal queues for high-risk incidents.

## Remember

**The Joiner–Mover–Leaver workflow is a lifecycle of trust and permissions, not merely directory syncing.**

- **Joiner:** verify source and person ID → approvals → directory/IdP identity → SCIM/app provisioning → identity link → least-privilege grants → `ACTIVE` and test.
- **Mover:** compute target permissions → check SoD → revoke old permissions → grant approved new permissions → refresh sessions/caches/tokens → verify old permissions are gone.
- **Leaver:** central deny/local account disable → block new SSO logins → revoke SCIM/groups/local grants → destroy sessions/tokens across all nodes → audit/reconcile and verify with old credentials.

**Four essential boundaries:** Authentication differs from authorization; identity differs from username/email; provisioning differs from revocation; and an event or HTTP 200 differs from permissions actually ceasing to work at real resources.

With Spring Security, maintain **identity links via issuer + stable subject**, load permissions from approved internal sources, and enforce at request/method/resource boundaries. **Never trust old authorities indefinitely**, especially for admin and cross-tenant actions.

### References

- [RFC 7643 – SCIM Core Schema: User, Group, id, externalId, active](https://www.rfc-editor.org/rfc/rfc7643)
- [RFC 7644 – SCIM Protocol: PATCH, versioning, ETag, group membership](https://www.rfc-editor.org/rfc/rfc7644)
- [Spring Security – LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html)
- [Spring Security – OAuth2 Login Advanced: Mapping User Authorities](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security – Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
- [Spring Session – Reference](https://docs.spring.io/spring-session/reference/)
- [OWASP – Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [OWASP – Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
