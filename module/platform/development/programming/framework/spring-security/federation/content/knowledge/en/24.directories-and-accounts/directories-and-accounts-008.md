# Handling Renames, Email Changes, Organization Transfers, and Account Deletions in Spring Security Federation

## 1. The Problem: A Person's Profile May Change, but Their Identity Must Not Be Confused

An enterprise Spring Boot application may authenticate via LDAP/Active Directory, Kerberos/SPNEGO, CAS, SAML 2.0, or OpenID Connect (OIDC). User profiles arrive from HRIS, directories, an Identity Provider (IdP), or a SCIM provisioning connector.

Example:

~~~text
User:              Nguyen Minh Anh
Username:          minh.anh
Email:             minh.anh@old.example.org
Department:        Finance
Org/tenant:        company-a
App account ID:    acct-8f20
External identity: (issuer=https://idp.example.org, sub=user-9832)
~~~

Later, the employee **changes their name**, **changes their email**, **transfers departments/organizations**, and eventually **leaves or requests account deletion**. The system must simultaneously do two seemingly opposite things:

- Keep the **exact same app account** and data ownership when a change is merely profile information for the same person.
- **Revoke old permissions and active sessions** on organization transfer, account state change, or employment termination; never let a new account inherit a former user's data just because an email/username was recycled.

This lesson belongs to **Spring Security - federation → Directories and Accounts**, topic **"Handling Renames, Email Changes, Organization Transfers, and Account Deletions"**. Do not assume a single IdP or database is the authoritative source for every organization; define an explicit contract across HRIS, directory, provisioning, and the application.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish **stable identifiers** from mutable attributes such as email, `displayName`, UPN, DN, and department.
2. Design an immutable **app-local account ID** and properly scoped external identity bindings.
3. Handle name/email changes **without creating duplicate accounts** or losing data.
4. Recognize **account takeover from email recycling** and prevent unverified account linking.
5. Handle organization/tenant transfers using **revoke-before-grant**, avoiding stale roles.
6. Understand SCIM `id`, `externalId`, `userName`, `active`, PATCH/DELETE, and ETags.
7. Distinguish OIDC `iss+sub`, SAML persistent `NameID`, and LDAP/AD object identifiers.
8. Build a lifecycle state machine (`ACTIVE`/`SUSPENDED`/`DISABLED`/`DELETED`).
9. Integrate a Spring Security account gate, authorities, `HttpSession`, and token revocation.
10. Handle duplicate/out-of-order events, partial provisioning failures, and reconciliation.
11. Run a standalone Java 17 example demonstrating rename, email update, org transfer, and disable.
12. Test the full joiner–mover–leaver lifecycle with privacy, auditing, and least privilege.

Examples use Java 17+, Spring Boot 3.x, Spring Security Servlet 6.x/7.x, and SCIM 2.0. Account codes and URLs are dummy values. Spring integration snippets must be placed in a project with proper dependencies/beans, unlike the standalone Java 17 demo.

## 2. An Identifier Must Never Be an Email String

A system typically has five layers of information:

| Layer | Example | Source | Does it change? |
| --- | --- | --- | --- |
| Directory/person identity | AD `objectGUID`, Entra object ID, HR person record | Directory/HRIS | Stable within object scope; may change on recreate/migration |
| Federated identity | OIDC `iss+sub`, SAML persistent subject | IdP | Per federation contract; may change on issuer/sector migration |
| Internal account | UUID `acct-8f20` | Application | **Never changes on rename/email change** |
| Profile | Display name, email, username, department | HRIS/IdP/profile service | May change frequently |
| Authorization state | Active, org memberships, roles, ACLs, security epoch | IAM and app policy | Must update whenever permissions change |

If you design:

~~~sql
CREATE TABLE business_documents (
    document_id BIGINT PRIMARY KEY,
    owner_email VARCHAR(320) NOT NULL
);
~~~

then a changed or recycled email address can orphan documents or transfer them to the wrong person. Instead, maintain an independent ownership key:

~~~sql
CREATE TABLE app_accounts (
    account_id UUID PRIMARY KEY,
    display_name VARCHAR(255),
    primary_email VARCHAR(320),
    status VARCHAR(32) NOT NULL,
    authz_version BIGINT NOT NULL DEFAULT 1
);

CREATE TABLE business_documents (
    document_id BIGINT PRIMARY KEY,
    owner_account_id UUID NOT NULL
        REFERENCES app_accounts(account_id)
);
~~~

This is illustrative DDL for databases supporting UUIDs. Production also requires tenant scoping, FKs/indexes, constraints, migrations, PII protections, and business authorization. **An FK on account ID does not by itself prevent cross-tenant access** if queries omit organization/resource ACL checks.

### Identifier stability comparison

| Field | Usable as identity key? | Limitations |
| --- | --- | --- |
| `displayName`, `givenName`, `familyName` | **No** | Names collide and change |
| Email | **No** | Can change; emails are recycled |
| Username/UPN | Not by default | Can change with name/domain/organization |
| LDAP DN | Not an immutable key | Renames/OU moves alter DN |
| AD `objectGUID` | Conditionally | Stable for the same object; not preserved across delete-recreate/cross-forest migration |
| AD `objectSid` | Conditionally | Domain/security principal scoped; migrations can change SID |
| Entra `objectId` | Yes, tenant-scoped | Different object in target tenant gets a different ID |
| OIDC `sub` | **Only when paired with `iss`** | Pairwise `sub` differs by client/sector |
| SAML persistent `NameID` | Per federation contract | Scoped to issuer/qualifiers; do not assume every Format is persistent |
| SAML transient `NameID` | **No** | Can change every session |
| CAS `cas:user` | Depends on contract | May be a mutable username |
| Kerberos `user@REALM` | Depends on contract | Principal/realm can change on rename/migration |
| SCIM `id` | Within provider namespace | Non-reassignable per RFC, issued by SCIM server |
| SCIM `externalId` | Scoped to provisioning domain | Client-assigned, not globally unique |
| App `account_id` | **Yes** | Immutable, non-reassignable, lifecycle-managed |

**OIDC Core** specifies the `(iss, sub)` pair as the identifier guaranteed for uniqueness/stability within the issuer's scope. Claims like `email`, `preferred_username`, and `name` carry no such guarantee. **RFC 7643** states SCIM `id` must be stable and non-reassignable within the service provider's resource set; `externalId` belongs to the provisioning client and only has meaning within a provisioning domain.

### Crucial lesson on namespaces

~~~text
Identity A: (iss=https://idp-a.example.org, sub=user-001)
Identity B: (iss=https://idp-b.example.org, sub=user-001)
~~~

These two identities **are not automatically the same person**. In multi-tenant systems, preserve tenant or directory/provisioning namespaces per contract; never use matching names/emails to auto-merge.

## 3. Data Model: Local Accounts and External Identity Bindings

An app should have at least:

~~~text
AppAccount:
  accountId [immutable UUID]
  displayName [mutable]
  primaryEmail [mutable]
  emailVerifiedAt [nullable]
  lifecycleStatus [PROVISIONED/ACTIVE/SUSPENDED/DISABLED/DELETED]
  authzVersion [monotonic]
  updatedAt, sourceVersion

ExternalIdentityBinding:
  bindingId
  accountId
  protocol [OIDC/SAML/LDAP/CAS/SCIM/...]
  issuerOrDirectoryNamespace
  externalSubjectIdentifier
  linkedAt
  verifiedMethod
  bindingStatus [ACTIVE/REVOKED]

Membership:
  accountId
  organizationId
  role/grant/resourceScope
  status, validFrom, validUntil
  policyVersion

Audit:
  eventId, source, accountId, eventType, actor
  occurredAt, processedAt, result
  authorizationDecision, correlationId
~~~

Example binding table (illustrative SQL):

~~~sql
CREATE TABLE external_identity_bindings (
    binding_id UUID PRIMARY KEY,
    account_id UUID NOT NULL
        REFERENCES app_accounts(account_id),
    protocol VARCHAR(24) NOT NULL,
    issuer_namespace VARCHAR(512) NOT NULL,
    subject_value VARCHAR(512) NOT NULL,
    binding_status VARCHAR(24) NOT NULL,
    linked_at TIMESTAMP NOT NULL,
    verified_method VARCHAR(64) NOT NULL,
    CONSTRAINT one_account_per_external_identity
        UNIQUE (protocol, issuer_namespace, subject_value)
);
~~~

If the application spans multiple tenants/provisioning domains, the unique constraint must accurately reflect the authoritative namespace. This does not mean an app-local account may only ever have one external identity: multiple bindings can be **verified and linked** to the same account, while each active external identity may map to at most one app account.

**Never use email as the identity-proving key.** A unique email constraint for contacts/notifications can be useful, yet uniqueness does not prove two historical identities are the same person.

### Account linking constraints

1. External subject lookup must happen only after the **authentication protocol** has validated issuer, signature, audience, and conditions.
2. A new binding requires **proof**: both account contexts reauthenticated, or an approved authoritative migration mapping.
3. A revoked/disabled binding must never auto-reenable just because an email or username matches again.
4. Link/unlink is a **security-sensitive operation**; audit actor, proof, and approval.
5. If IdP issuer or subject changes, create a new binding via a migration procedure—never auto-match by email.
6. Restrict any account restoration after offboarding per business policy, never inheriting old privileges.

## 4. Source of Truth for Each Data Type

One system does not necessarily have authority to modify every field:

| Data | Typical authoritative source | Cases requiring caution |
| --- | --- | --- |
| Employment status | HRIS/identity governance | App admin manually re-enabling a departed user |
| Directory identifier | AD/Entra/directory | Object recreated while app assumes same ID |
| Login authentication | IdP/AS/KDC | Trusting unverified headers/claims |
| Profile/display name | HRIS/directory/profile owner | "Rename" accidentally changing account ID |
| Work email | Corporate directory/verified self-service | Changing recovery email without verification |
| Department / org | HRIS/organization governance | Changing department without revoking groups |
| Roles/privileged grants | App/resource owner + approval | Mapping `department=Finance` to `ADMIN` |
| Resource ownership | Business domain owner | Auto-transferring documents along with new email/org |
| Account status in app | IAM + local security policy | Token still valid after disable |
| Legal hold / data retention | Legal/privacy policy | SCIM DELETE wiping financial records |

**Note:** if two sources can update the same field, define field ownership/conflict policies; never use "last write wins" for account status or privileged roles.

## 5. Rename Events: Update Profile, Preserve Owner ID

Before:

~~~text
accountId  = acct-8f20
displayName= Nguyen Minh Anh
email      = minh.anh@example.org
external   = (https://idp.example.org, subject-123)
~~~

After:

~~~text
accountId  = acct-8f20        (unchanged)
displayName= Nguyen Thi Minh Anh
email      = minh.anh@example.org
external   = (https://idp.example.org, subject-123) (unchanged)
~~~

### Steps

1. Receive the rename event from an authoritative source with source object ID and event revision.
2. Look up the **stable external binding** to the app account.
3. Verify idempotency and version (do not apply stale events).
4. Update `displayName`, `familyName`/`givenName`, search profile, and cached labels per policy.
5. Do not create a new user, and do not change `account_id` in document tables.
6. Do not alter roles, tenant, or permissions just because a name changed.
7. Audit by account ID, minimizing PII.
8. Identify legacy integrations using username/DN as a key and fix them.
9. If a rename accompanies a UPN/email change, handle them as **two events** with separate verification.

### Sessions after a rename

An active `SecurityContext` may still hold the old `principal.getName()`. If that is solely a display name, it can be refreshed from the profile store without forcing a global logout. If the identity principal string is still used as a downstream foreign key, that is a design smell requiring refactoring toward an immutable subject/account ID.

**Never use a minor profile update to re-grant all permissions.** Permissions must pass through their own authorization policy.

## 6. LDAP/Active Directory: A DN Rename Is Not an Identity Change

An initial LDAP distinguished name:

~~~text
cn=Minh Anh,ou=Finance,dc=corp,dc=example,dc=org
~~~

After rename/OU move:

~~~text
cn=Minh Anh Nguyen,ou=People,dc=corp,dc=example,dc=org
~~~

The DN is a locator path for a directory entry. It can change during renames/moves, so hardcoding DNs as app principal/account keys breaks lookups.

Appropriate approach:
- Look up objects by a **clearly scoped stable attribute**, such as AD `objectGUID` within the corresponding directory instance;
- Store `directoryNamespace+objectGUID` linked to the app account;
- When the DN changes, update search/index caches and bind targets without creating a different account;
- Do not treat `cn`, `sAMAccountName`, or `userPrincipalName` as immutable;
- Note that AD `objectGUID` has a binary representation and must be encoded consistently;
- `objectSid` and `SIDHistory` follow domain/migration semantics—do not interchange them arbitrarily;
- Object delete-and-recreate or cross-forest migrations can generate new identities requiring verified migration mappings.

In Spring LDAP, you can perform a directory search by username and then bind or compare credentials and load authorities. Never take an LDAP DN or query filter from the browser and concatenate unescaped strings. Use Spring LDAP escaping/query APIs, LDAPS/StartTLS, and least-privilege service accounts.

### Entra ID

Microsoft recommends developers use the user's **object ID** instead of UPN/email, because UPNs can change on name changes, domain changes, restructurings, or org transfers. The object ID must be scoped with the **tenant ID**. Moving to a different tenant can produce a new object, requiring migration mapping rather than email auto-linking.

## 7. Email Changes: Preventing Account Takeover from Recycled Emails

An email address may serve as:
- Notification destination;
- Recovery endpoint;
- Login UI username;
- An OIDC claim or SAML/SCIM attribute;
- A corporate work address issued by HR.

**Never use email as a unique identity key.** The same address can be owned by two people at different times.

### Wrong scenario

~~~text
T1: A owns shared.name@example.org, app account acct-A.
T2: A leaves; email returns to address pool.
T3: B is assigned shared.name@example.org.
T4: IdP authenticates B and returns claim email=shared.name@example.org.
T5: App auto-finds acct-A by email and grants B A's history/permissions.
~~~

This is a form of **account takeover** caused by auto-linking on a mutable attribute. Even with `email_verified=true`, that only reflects the IdP's contract regarding mailbox control **at the time of verification**—it does not prove B is A.

### Standard workflow

1. Identify authorized email-change sources: HRIS/directory or verified self-service.
2. For self-service, require reauthentication/step-up when risk is elevated.
3. Store `pendingEmail` if needed; send a challenge to the new address; never change recovery paths before verification.
4. Check the new email against tenant uniqueness policy. If it matches another account, **never auto-merge**.
5. Update primary email and verified status only after authoritative/proper verification.
6. Keep the account ID and external bindings unchanged and stable.
7. Update notification subscriptions, contact lists, UI search indexes, and caches.
8. Consider invalidating recovery paths on the old email and notifying of the email change over an independent channel.
9. Evaluate sessions/OIDC ID Tokens still carrying the old email without relying on email as an authorization key.
10. Record an audit event by app account ID and correlation ID; limit PII retention.

### Do not do the following

- Never use an unverified email for password resets.
- Never transfer document ownership from A to B because B now uses the old email.
- Never send recovery codes to an email that IAM reports no longer belongs to the user.
- Never accept a browser-supplied `newEmail` query parameter as `email_verified`.
- Never auto-link another SAML/OIDC/CAS account merely because the email claim matches.
- Never allow an admin in tenant A to edit an account's email in tenant B without object-level authorization.

## 8. OIDC: Use iss + sub, Never Email as the Key

OIDC Core guarantees a stable end-user identifier only for the **`(iss, sub)` pair**. Claims such as `email`, `preferred_username`, and `name` are not guaranteed unique or immutable over time.

Example **verified** ID Token claims in a valid flow:

~~~json
{
  "iss": "https://idp.example.org",
  "sub": "subject-123",
  "email": "minh.anh@old.example.org",
  "email_verified": true,
  "preferred_username": "minh.anh",
  "name": "Nguyen Minh Anh"
}
~~~

After rename:

~~~json
{
  "iss": "https://idp.example.org",
  "sub": "subject-123",
  "email": "minh.anh.nguyen@new.example.org",
  "email_verified": true,
  "preferred_username": "minh.anh.nguyen",
  "name": "Nguyen Thi Minh Anh"
}
~~~

The identity binding **stays the same**:

~~~text
(https://idp.example.org, subject-123) -> acct-8f20
~~~

**Do not look up the account by the new email** and do not create a duplicate account just because email/username changed.

### Pairwise subjects and issuer migration

OIDC supports pairwise subject identifiers; one person can receive different `sub` values across clients/sector identifiers. If the issuer URL, tenant, or sector identifier changes, the app may receive a new subject. That still does not permit auto-connecting via email. You need:
- An approved migration roster / signed authoritative mapping;
- Verification that old and new identities truly belong to the same person per IAM procedure;
- Adding the new binding to the existing app account when authorized;
- Auditing link/unlink events and preventing one external subject from mapping to multiple accounts;
- Removing the old binding only after cutover and security review.

## 9. SAML, CAS, and Kerberos Also Have Username-Change Issues

### SAML 2.0

- `NameID Format=emailAddress` is an email-like identifier that can change or be recycled.
- `transient NameID` is unsuitable as a persistent account key.
- `persistent NameID` is designed for long-term correlation within a federation relationship, potentially requiring properly scoped `Issuer`/`NameQualifier`/`SPNameQualifier`.
- Some federations use `subject-id` or `pairwise-id` per profile.
- The SP must validate SAML signature, issuer, audience, subject confirmation, and timing **before** extracting identity.
- If IdP mapping changes, perform a verified re-link, never an email fallback.

### CAS Protocol

- CAS `cas:user` may be a username/UPN depending on the CAS Server.
- A Service Ticket is a one-time credential, **not** a stable user identifier.
- If the CAS username changes, the application needs CAS attributes or directory object IDs with a stability contract, or a controlled migration.
- CAS SLO does not automatically fix wrong account mappings or stale app permissions.

### Kerberos/SPNEGO

- A principal such as `person@REALM` can change on rename or domain migration.
- Mapping from a verified Kerberos principal to a stable directory object ID may be necessary after Kerberos verification.
- Never equate identical usernames from two different realms.

## 10. Department or Organization Transfer: This Is a Permission Change

When moving from Finance → People, updating `department=People` is not enough. You must inspect:
- Group memberships in directory/IdP/SCIM;
- Local role grants;
- Project/workspace/resource ACLs;
- App sessions holding old authorities;
- API tokens and background jobs;
- Audit/approval privileges;
- Data ownership of documents in the old organization.

Before/after table:

| Attribute | Before | After |
| --- | --- | --- |
| App account ID | `acct-8f20` | `acct-8f20` (if same identity is permitted to remain) |
| Department | Finance | People |
| Local roles | `FINANCE_READ`, `FINANCE_EXPORT` | `PEOPLE_READ` |
| Finance resource access | Allowed per old permissions | **Must be revoked** unless separately granted |
| Old `HttpSession` authorities | Finance | **Must be invalidated/refreshed** |
| Ownership of historical finance documents | Per policy | **Does not auto-transfer** to the new org |

### Revoke-before-grant workflow

1. Validate the **authoritative mover event** using stable identity and event version.
2. Determine whether the move is intra-tenant or cross-tenant/legal entity.
3. Block sensitive old-org permissions **before** granting new-org access.
4. Remove old group roles, direct grants, delegated access, and approval permissions.
5. Apply target-org rules and approve new roles; never copy old roles verbatim.
6. Increment `authzVersion`/`securityEpoch` so old sessions/tokens cannot keep operating as-is.
7. Invalidate/refresh sessions, authorized clients, caches, and tokens via available mechanisms.
8. Update downstream group memberships/SCIM and monitor ACKs and SLAs.
9. Handle data ownership per business/legal policy.
10. Test that the user cannot enter the old org and holds only newly approved permissions.

### Tenant differs from department

Changing departments within the same tenant may only change group grants. Switching legal entities/tenants may require:
- Separating data and resource ownership;
- A new external identity from the target tenant's IdP;
- Disallowing automatic account migration due to legal requirements;
- Managing a new employment/contract relationship;
- An approved account binding or a separate app account;
- Different data residency and retention rules.

**Never treat a request query `tenant=people` as proof that the user belongs to People.** Business authorization must rely on current membership from a trusted source and the resource's org.

## 11. Mover Race: Slow Group Sync Leaves Old Permissions Active

An asynchronous flow can create a dangerous window:

~~~text
T0: HR transfers Finance -> People.
T1: IdP adds user to People group.
T2: Finance group is not removed due to connector failure.
T3: User holds token/session containing both Finance and People roles.
T4: User calls sensitive finance endpoint in the T1-T2 window.
~~~

Mitigations:
- **Revoke-before-grant** in orchestration;
- For high-risk actions, put the account in `SUSPENDED</BT>/deny until reconciliation finishes;
- Bump `authzVersion` as soon as entitlement changes begin;
- Backend current permission check before commit;
- Use SCIM Group membership updates and local ACL cleanup;
- Mark status `PENDING_DOWNSTREAM` when a connector has not ACKed;
- Alert on revocation SLA breaches rather than merely logging "event delivered".

An `ACTIVE` account does not prove current roles are synced properly. Separate **employment status**, **membership status**, and **business authorization**.

## 12. Multiple Organizations: Model Memberships Instead of One Org String

If a user holds multiple contracts/tenants, a single `user.organizationId` is insufficient. An illustrative model:

~~~sql
CREATE TABLE memberships (
    account_id UUID NOT NULL,
    organization_id UUID NOT NULL,
    membership_status VARCHAR(24) NOT NULL,
    authz_version BIGINT NOT NULL,
    PRIMARY KEY (account_id, organization_id)
);

CREATE TABLE resource_grants (
    resource_id UUID NOT NULL,
    account_id UUID NOT NULL,
    organization_id UUID NOT NULL,
    permission VARCHAR(64) NOT NULL,
    PRIMARY KEY (resource_id, account_id, organization_id, permission)
);
~~~

This is illustrative DDL without full FKs, indexes, or row-level security. When evaluating access:
- Identify the logged-in immutable account ID;
- Check current account status;
- Verify the selected organization has an active membership;
- Verify the resource belongs to the right tenant;
- Check read/write/approve permission on the resource;
- Never trust roles from an old token after a mover event if policy demands near-real-time revocation.

Changing orgs must never automatically move all historical resources into the new org. Data transfers must go through an audited and approved business ownership workflow.

## 13. Disabling and Deleting an Account Are Not the Same Operation

| Status | New logins | Active sessions | Data/audit |
| --- | --- | --- | --- |
| `SUSPENDED` | Deny per policy | Revoke/deny | Recoverable with approval |
| `DISABLED` | Deny | Revoke/deny | Usually retains record per policy |
| SCIM `active=false` | Administrative inactive | **Provider/app must enforce policy itself** | Resource may remain in SCIM |
| SCIM `DELETE` | Must no longer exist as queryable resource | App must deny/revoke | Physical retention depends on provider and legal policy |
| Internal `DELETED_TOMBSTONE` | Deny | Deny | Retain minimal trace if policy permits |

**SCIM RFC 7643** describes `active` as an administrative status; it does not imply all sessions/tokens are automatically revoked. **RFC 7644** allows a service provider after `DELETE` not to perform permanent physical deletion, provided queries to the deleted resource return not found and the resource does not appear in query results.

### Offboarding in the right order

1. Receive leaver event from trusted HRIS/IAM and look up immutable identity/account ID.
2. Disable the app account and IdP/directory account per policy.
3. Revoke organization memberships, roles, privileged grants, delegated access, and project access.
4. Revoke or expire Spring `HttpSession`s, OAuth2 grants/refresh tokens, API keys, long-running connections, and personal credentials as supported.
5. Send SCIM disable/remove/delete to downstream applications and group memberships.
6. Stop scheduled jobs/automations/service integrations acting on behalf of the user.
7. Transfer ownership of documents, workflows, and invoices per business approval; never auto-reassign blindly.
8. Execute data retention/deletion/archival per privacy/legal policy.
9. Clean up notifications/recovery emails, search indexes, caches, and invitations as appropriate.
10. Track ACKs, failures/retries, and reconciliation. Never declare success while downstream access remains.

**IdP disabling does not automatically expire every JWT.** A Spring `HttpSession` holding a built `SecurityContext` may persist; a signed access token may still be accepted by a resource server until `exp` if the server lacks revocation/introspection/a live account gate.

## 14. SCIM 2.0: Standardizing Account Changes

RFC 7643 defines SCIM User:
- `id`: service-provider-issued, stable, non-reassignable within that resource set, read-only;
- `externalId`: optional identifier supplied by the provisioning client, scoped to the provisioning domain;
- `userName`: login name per provider contract, not treated as immutable;
- `displayName`, `name.givenName`/`familyName`: profile;
- `emails`: list of addresses and `primary` flag;
- `active`: administrative status;
- Enterprise User extension: `department`, `organization`, `manager`, `employeeNumber`, and enterprise attributes.

### Example SCIM User response

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User",
    "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
  ],
  "id": "scim-provider-user-001",
  "externalId": "hr-person-5001",
  "userName": "minh.anh@company.example.org",
  "displayName": "Nguyen Minh Anh",
  "emails": [
    {
      "value": "minh.anh@company.example.org",
      "type": "work",
      "primary": true
    }
  ],
  "active": true,
  "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {
    "department": "Finance",
    "organization": "Company A"
  }
}
~~~

**This is mock response JSON.** On a SCIM POST creation, the client **must not supply `id`**; the service provider returns `id`. `externalId` is not globally unique and requires scoping.

### PATCH rename and email

~~~http
PATCH /scim/v2/Users/scim-provider-user-001 HTTP/1.1
Host: app.example.org
Authorization: Bearer [REDACTED]
Content-Type: application/scim+json
If-Match: W/"v17"
~~~

~~~json
{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {
      "op": "replace",
      "path": "displayName",
      "value": "Nguyen Thi Minh Anh"
    },
    {
      "op": "replace",
      "path": "emails",
      "value": [
        {
          "value": "minh.anh.nguyen@new.example.org",
          "type": "work",
          "primary": true
        }
      ]
    }
  ]
}
~~~

**Explanation:**
- `W/"v17"` is only a placeholder ETag; if the provider supports ETags, read the actual value from the resource.
- SCIM PATCH operations apply sequentially but must be **atomic within a single request** per RFC; if one operation fails, the whole request must not apply partially.
- `PUT` replacement can wipe omitted attributes; PATCH is suited for field-level updates when supported by the server.
- Some SCIM providers restrict changing `userName` or have custom `emails` array behavior; check `/Schemas`, `/ServiceProviderConfig`, and the vendor contract.
- Use `id` or a scoped `externalId` binding; never use a new email to "create a new user".

### PATCH disable

~~~http
PATCH /scim/v2/Users/scim-provider-user-001 HTTP/1.1
Content-Type: application/scim+json
Authorization: Bearer [REDACTED]
If-Match: W/"v18"
~~~

~~~json
{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {
      "op": "replace",
      "path": "active",
      "value": false
    }
  ]
}
~~~

Upon valid receipt:
- Update app-local lifecycle status to **deny login/authorization**;
- Trigger revocation of sessions/tokens/grants per requirements;
- Emit downstream deprovisioning events;
- Log audit and outcome.
- Never assume every vendor automatically destroys active sessions just because `active=false` was stored.

### DELETE

~~~http
DELETE /scim/v2/Users/scim-provider-user-001 HTTP/1.1
Authorization: Bearer [REDACTED]
If-Match: W/"v19"
~~~

Per RFC 7644, the provider may skip physical deletion, yet a `DELETE`d resource must no longer be retrievable via GET/QUERY under the SCIM endpoint per contract. The app must deny access and revoke permissions, while data retention/archival are handled separately.

**Do not use DELETE for every leaver** if business processes require suspended/reactivatable accounts. Clearly distinguish administrative deactivation from resource removal with the provisioning client.

## 15. SCIM Group Membership and Department Are Not Equivalent

Changing SCIM `department` from Finance to People does not remove the user from the directory/SCIM Group `finance-analysts`. When authorization relies on groups, you must:
- Remove old group memberships;
- Revoke direct roles/ACLs;
- Add new groups upon approval;
- Sync local grants and refresh authorities;
- Track updates on `Group` resources, not only `User.department`;
- Check nested groups and group mapping restrictions.

In SCIM, `User.groups` may be returned as read-only references per schema/provider; membership changes typically go through `Group.members`. Never have a SCIM client update `department` and claim roles are now accurate.

### Concurrency/ETag

When HRIS, IdP, and app admins make concurrent changes:
- Use narrow PATCHes instead of full-resource PUTs where appropriate;
- If the server supports versioning, send `If-Match` with the read ETag;
- On precondition mismatch errors, fetch current state and reconcile;
- Do not infinitely retry stale payloads;
- Separate write authority by field owner; never let profile sync re-enable a disabled account.

## 16. Session and Token Revocation in Spring Security

An app using Servlet login typically stores `Authentication` and authorities in `SecurityContext`, often backed by `HttpSession`. When a user transfers orgs or is disabled, the existing `Authentication` may still hold:
- Old account status;
- Old Finance roles;
- Old email/profile attributes;
- Active tokens/refresh grants;
- Old selected tenant.

A risk-appropriate strategy:

| Mechanism | Effect | Limitations |
| --- | --- | --- |
| Account gate at login | Blocks new logins if disabled | **Does not** stop existing sessions |
| Current-state authorization gate | Denies disabled user / revoked membership on request | Requires DB/cache consistency |
| `authzVersion`/`securityEpoch` | Denies/forces reauth if session version differs from current state | Must be checked consistently on sensitive paths |
| Session invalidation/index | Destroys sessions by immutable account ID | Multi-node needs shared session store/index |
| Short JWT TTL | Shrinks stale-token window | Not instantaneous |
| Token revocation/introspection | Lets backend verify live token validity | Requires infrastructure and policy |
| OAuth refresh grant revocation | Blocks minting new tokens from old grant | Already-issued access tokens may stay valid |
| SCIM downstream disable | Revokes other apps via provisioning | Asynchronous; needs ACKs/retries |
| WebSocket/job shutdown | Stops connections and background actions | Does not automatically happen on `HttpSession` logout |

**Important:** SAML SLO, OIDC logout, or CAS SLO can help terminate some sessions per protocol and configuration. However, there is no guarantee that all JWTs, API keys, WebSockets, and downstream SaaS apps are revoked automatically.

### Security epoch on org transfer

A session created at `authzVersion=6` holds Finance permissions. When HR transfers the org, the app increments the version to 7. Any sensitive request from a version-6 session must be denied or require reauthentication/refresh **before reading resources**. Reauthentication must load the new groups/memberships rather than re-granting old privileges.

## 17. Spring Security OIDC: Account Gate Example by Issuer + Subject

In OIDC login, Spring Security offers `OidcUserService`, which can inspect the account after the ID Token/claims have been verified by the OIDC provider.

**Partial Spring config** sample:

~~~java
package com.example.identity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

@Configuration
public class OidcAccountGateConfig {

    @Bean
    OAuth2UserService<OidcUserRequest, OidcUser> gatedOidcUserService(
            AccountAccessGuard accountAccessGuard) {

        var delegate = new OidcUserService();

        return request -> {
            OidcUser user = delegate.loadUser(request);

            String issuer = user.getIdToken()
                    .getIssuer().toString();
            String subject = user.getIdToken()
                    .getSubject();

            // App-owned service: exact (issuer, subject) lookup,
            // status active, current memberships/tenant checks.
            // Must throw a suitable AuthenticationException
            // if unknown/disabled/forbidden.
            accountAccessGuard.requireActive(issuer, subject);
            return user;
        };
    }
}
~~~

**Prerequisites:** `AccountAccessGuard` is a custom interface/service you implement; requires OAuth2/OIDC client configuration, Spring Security dependencies, a trusted issuer, a `SecurityFilterChain`, and a database. The code will not compile with bare `javac` and is not a complete application.

Wiring into the flow:

~~~java
@Bean
SecurityFilterChain security(
        HttpSecurity http,
        OAuth2UserService<OidcUserRequest, OidcUser> gatedOidcUserService)
        throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/health", "/error").permitAll()
                    .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                    .userInfoEndpoint(userInfo -> userInfo
                            .oidcUserService(gatedOidcUserService)))
            .build();
}
~~~

The snippet requires imports for `@Bean`, `HttpSecurity`, and `SecurityFilterChain`. This is a **login gate**; it does not replace session revocation when an account is disabled **after** login.

Never use `user.getEmail()` as the account lookup key. If local roles are needed, use `GrantedAuthoritiesMapper` or advanced OIDC `UserService` patterns per Spring docs to map authorities safely; never blindly trust `email domain` or unvetted `groups` to grant elevated privileges.

## 18. LDAP/SAML/CAS Integrations Require Independent Account Gates

**LDAP/AD**:
- Directory search/bind verifies user login;
- DN can change on rename/OU move;
- Group memberships can change after user login;
- The app needs a stable directory binding and current account status;
- Do not assume LDAP auth success automatically invalidates old `HttpSession`s.

**SAML 2.0**:
- Spring SP verifies signature, issuer, audience, recipient, timing, and subject confirmation;
- Use persistent identity subject + qualifiers per federation contract;
- Attributes may only refresh on the next login;
- Provisioning events (SCIM) update accounts/groups earlier, without replacing assertion validation;
- SAML Session Logout does not automatically revoke all API tokens.

**CAS Protocol**:
- CAS Server validates the Service Ticket, and the app builds `Authentication`;
- CAS `cas:user` may change when directory usernames change;
- Without a stable directory attribute, an approved account migration is needed;
- CAS SLO handles certain sessions, not a live entitlement gate.

**Kerberos**:
- Kerberos principal/UPN and realm are scoped and may change on migration;
- Mapping from a verified Kerberos principal to a directory object ID may be necessary;
- Never merge two principals with the same username across different realms.

## 19. Standalone Java 17: Rename, Email, Mover, Disable, and Stale Session Permissions

The following program uses **only the Java Standard Library**. It simulates `ExternalIdentity(issuer, subject)` bound to an immutable app account ID, profile updates, permission revocation on org transfer, and blocking all requests after disable.

File `AccountLifecycleDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public final class AccountLifecycleDemo {

    record ExternalIdentity(String issuer, String subject) {}

    static final class Account {
        final String accountId;
        String displayName;
        String email;
        String organization;
        boolean active = true;
        Set<String> roles;
        long authzVersion = 1;

        Account(String accountId, String displayName,
                String email, String organization,
                Set<String> roles) {
            this.accountId = accountId;
            this.displayName = displayName;
            this.email = email;
            this.organization = organization;
            this.roles = Set.copyOf(roles);
        }
    }

    static final class Directory {
        private final Map<String, Account> accounts = new HashMap<>();
        private final Map<ExternalIdentity, String> bindings =
                new HashMap<>();

        synchronized void create(Account account, ExternalIdentity identity) {
            if (accounts.containsKey(account.accountId)
                    || bindings.containsKey(identity)) {
                throw new IllegalArgumentException("duplicate identity");
            }
            accounts.put(account.accountId, account);
            bindings.put(identity, account.accountId);
        }

        synchronized String resolve(ExternalIdentity identity) {
            return bindings.getOrDefault(identity, "NO_MATCH");
        }

        private Account require(String id) {
            Account account = accounts.get(id);
            if (account == null) {
                throw new IllegalArgumentException("unknown account");
            }
            return account;
        }

        synchronized void rename(String id, String newName) {
            require(id).displayName = newName;
        }

        synchronized void changeEmail(String id, String verifiedEmail) {
            // Real service must verify event origin/email ownership.
            require(id).email = verifiedEmail;
        }

        synchronized void transfer(String id, String newOrganization,
                                   Set<String> newRoles) {
            Account account = require(id);
            account.organization = newOrganization;
            account.roles = Set.copyOf(newRoles);
            account.authzVersion++;
        }

        synchronized void disable(String id) {
            Account account = require(id);
            account.active = false;
            account.roles = Set.of();
            account.authzVersion++;
        }

        synchronized long version(String id) {
            return require(id).authzVersion;
        }

        synchronized String profile(String id) {
            Account account = require(id);
            return account.displayName + " / " + account.email;
        }

        synchronized String authorize(String id, long sessionVersion,
                                      String requiredOrg, String role) {
            Account account = accounts.get(id);
            if (account == null) {
                return "DENY_UNKNOWN";
            }
            if (!account.active) {
                return "DENY_DISABLED";
            }
            if (account.authzVersion != sessionVersion) {
                return "REAUTH_REQUIRED";
            }
            if (!account.organization.equals(requiredOrg)
                    || !account.roles.contains(role)) {
                return "DENY_SCOPE";
            }
            return "ALLOW";
        }
    }

    public static void main(String[] args) {
        Directory directory = new Directory();
        ExternalIdentity original = new ExternalIdentity(
                "https://idp.example.org", "subject-101");

        directory.create(new Account(
                "acct-001", "Linh Tran",
                "linh.old@example.org", "finance",
                Set.of("REPORT_READ")), original);

        long oldSessionVersion = directory.version("acct-001");
        directory.rename("acct-001", "Linh Nguyen");
        directory.changeEmail("acct-001", "linh.new@example.org");

        System.out.println("Stable account: "
                + directory.resolve(original));
        System.out.println("Updated profile: "
                + directory.profile("acct-001"));
        System.out.println("Finance before transfer: "
                + directory.authorize("acct-001",
                        oldSessionVersion, "finance", "REPORT_READ"));

        directory.transfer("acct-001", "people", Set.of("PEOPLE_READ"));
        System.out.println("Old session after transfer: "
                + directory.authorize("acct-001",
                        oldSessionVersion, "finance", "REPORT_READ"));

        long newSessionVersion = directory.version("acct-001");
        System.out.println("Old org after reauth: "
                + directory.authorize("acct-001",
                        newSessionVersion, "finance", "REPORT_READ"));
        System.out.println("New org after reauth: "
                + directory.authorize("acct-001",
                        newSessionVersion, "people", "PEOPLE_READ"));

        ExternalIdentity anotherPerson = new ExternalIdentity(
                "https://idp.example.org", "subject-999");
        System.out.println("Reused email cannot link: "
                + directory.resolve(anotherPerson));

        directory.disable("acct-001");
        System.out.println("After disable: "
                + directory.authorize("acct-001",
                        newSessionVersion, "people", "PEOPLE_READ"));
    }
}
~~~

Compile and run:

~~~bash
javac AccountLifecycleDemo.java
java AccountLifecycleDemo
~~~

**Exact** stdout:

~~~text
Stable account: acct-001
Updated profile: Linh Nguyen / linh.new@example.org
Finance before transfer: ALLOW
Old session after transfer: REAUTH_REQUIRED
Old org after reauth: DENY_SCOPE
New org after reauth: ALLOW
Reused email cannot link: NO_MATCH
After disable: DENY_DISABLED
~~~

**Explanation:**
1. Changing name/email does not alter the external subject binding or app account ID.
2. Org transfer increments `authzVersion`, blocking the old session.
3. After reauth, the Finance org is no longer valid even though the principal is the same person.
4. People org access is allowed only when the user is active and holds the new role.
5. Another external subject is not auto-linked even if display email matches.
6. After disable, all requests are blocked before checking roles.

**Limitations:** this example does not prove signed/verified OIDC tokens or SCIM requests, uses no DB/transactions, performs no real revocation, and omits multi-tenant memberships and auditing. `verifiedEmail` is just a parameter name in the demo; production needs real verification. Never use `HashMap` as a production identity store.

## 20. Event Ordering, Duplicates, and Conflict Resolution

A sample internal event:

~~~json
{
  "eventId": "evt-3901",
  "source": "trusted-hris",
  "sourceVersion": 18,
  "subject": {
    "directoryNamespace": "corp-ad-01",
    "directoryObjectId": "opaque-object-123"
  },
  "type": "ORGANIZATION_TRANSFER",
  "effectiveAt": "2026-11-07T04:00:00Z",
  "changes": {
    "oldOrgId": "finance",
    "newOrgId": "people"
  }
}
~~~

This is an **example schema**, not a standard SCIM event. A webhook endpoint must verify the sender (mTLS/OAuth token/signature per contract), tenant scope, and event integrity; never accept arbitrary JSON from a browser to modify permissions.

### Four cases to handle

- **Duplicate delivery:** same event ID arrives multiple times → idempotent; do not create extra accounts or re-grant roles.
- **Out-of-order events:** disable version 20 arrives before org-move version 18 → never let the older event re-enable the account.
- **Partial failure:** local app disabled the user, yet downstream SCIM connector fails → record `PENDING`/`FAILED` status, retry with backoff, alert, and reconcile.
- **Conflicting authorities:** HRIS edits department, app admin edits role, IdP edits email → use a field-ownership matrix, never "last write wins" for all fields.

### `occurredAt` is not enough

Source-set `occurredAt` timestamps can suffer clock skew. If the source supports monotonic revisions or trusted ETags, use them to reject stale updates. Otherwise, reconcile current authoritative state instead of blindly applying events ordered by `processedAt`.

### Transactional outbox

A safe pattern:
1. App commits account status/membership changes alongside an outbox record in a local transaction.
2. Worker publishes revocation/deprovisioning events after commit.
3. Consumers process idempotently.
4. Use ACKs/retries/backoff and dead-letter queues on failure.
5. Run periodic reconciliation comparing HRIS/IdP/app/downstream state.
6. Dashboard SLAs so "offboarding complete" is never reported while resources remain active.

Do not pretend a single Spring `@Transactional` on the app DB atomically commits the IdP, SCIM, Redis, and SaaS services.

## 21. Rehires and Account Delete-Recreate

Someone who leaves and returns to work may have:
- The same email as before or a different one;
- The same HR person ID or a new employment record;
- A recreated directory object with a new `objectGUID`/`objectId`;
- A new or existing OIDC issuer/sub depending on the IdP;
- Historical resources they **must not regain access to** under their new role.

The decision to create a new account vs. reactivate must depend on:
- Employment relationship and tenant policy;
- Business/data ownership approvals;
- Verified old/new identity mapping;
- Newly approved role grants;
- Revocation of old credentials;
- Audited linking/relinking.

**Never auto-enable a `DISABLED` account or restore `ADMIN` roles simply because the email matches.** A local tombstone can help detect account ID history, while retention and PII must be properly governed.

### Account deletion and privacy

You may need to:
- Block access immediately;
- Retain invoices/ledgers/audits per record-keeping requirements;
- Delete/anonymize profile PII that is no longer needed;
- Transfer business ownership with approval;
- Purge API keys/notifications/search indexes;
- Handle backups per retention schedule;
- Enforce legal holds.

SCIM `DELETE` cannot replace this entire workflow. Privacy regulations vary by country/industry; work with your privacy/legal owner on real retention policies.

## 22. Post-Change Operational Runbooks

### Rename/email

1. Compare external stable identifier and internal account ID before/after.
2. Check new profile attributes and verified email status.
3. Confirm document owner FKs remain unchanged.
4. Check mail recovery/notification paths.
5. Ensure no duplicate accounts appeared.
6. Audit the event with `sourceVersion`; never log raw tokens or excessive PII.

### Mover

1. Verify source event and old/new organization.
2. Block old permissions and bump `authzVersion`.
3. Remove old group/project/privileged grants.
4. Add new permissions after approval.
5. Verify active sessions/token access have been refreshed/revoked.
6. Test object-level access in old and new orgs.
7. Confirm downstream ACKs and document ownership.

### Leaver

1. Set app account status `DISABLED`/`SUSPENDED` per policy.
2. Deny new logins.
3. Revoke sessions, OAuth grants, API keys, and background automations within SLA.
4. Deprovision downstream directory groups/SCIM apps.
5. Transfer/archive business documents/assets per approval.
6. Prevent email reuse from automatically restoring the account.
7. Mark data retention/privacy and audit records.
8. Complete reconciliation; alert/escalate on partial failures.

## 23. Common Errors and Remedies

| Symptom | Cause | Remedy |
| --- | --- | --- |
| Email change spawns another account | Email used as key | Use `issuer+subject`/stable binding and account ID |
| Last-name change loses documents | Owner keyed by name/email | FK to immutable account ID |
| OU move breaks LDAP login | Hardcoded DN | Search by current directory identity |
| User B gets A's data | Recycled email + auto-link | Stop auto-linking, revoke, audit identity links |
| SCIM PATCH returns 412 | ETag/version conflict | Fetch current state, reconcile |
| Email changed yet UI stays stale | Token/session/profile cache | Refresh profile cache without changing identity |
| Group changed yet session keeps old role | Stale authorities | `authzVersion`, session revocation/live check |
| Org transfer loses all data | Ownership auto-transferred | Restore business data ownership |
| IdP locks user yet API still lets them in | Valid unexpired JWT without live gate | Revocation/introspection/TTL |
| SCIM `active=false` yet app still logs in | Inactive flag not wired to app gate | Implement active check/revocation |
| SCIM DELETE followed by account rebirth | Stale connector create event | Tombstones/idempotency/`sourceVersion` |
| New SAML no longer maps old account | Issuer/persistent subject changed | Controlled identity migration |
| CAS username change creates new user | Mutable username used as identity key | Stable directory ID / approved re-link |
| Entra tenant migration loses mapping | `objectId` is tenant-scoped | Authoritative cross-tenant link |
| Rehire automatically gets old roles | Auto-enabled account | New role approval |
| Downstream leaver stays active | Partial sync failure | ACK/retry/alert/manual revoke |
| Older event version reopens account | Last-write-wins | Source revision + security gate |
| Cross-tenant data leak | Query missing tenant/resource scope | Object-level authorization + constraints |

## 24. End-to-End Test Suite

| Case | What must hold |
| --- | --- |
| Rename `displayName` | Same external identity and `accountId`, owner unchanged |
| Rename username/UPN | LDAP/AD object binding remains accurate |
| LDAP move DN | Entry found via search, no duplicates |
| Verified email change | Primary email updated; old recovery paths cleaned |
| Unverified email change | Pending email cannot reset login |
| Email recycled to new person | **Does not** receive old account's data/roles |
| Same OIDC `sub` across different issuers | Two distinct identities |
| OIDC pairwise subject changes on sector migration | Linked only via verified migration |
| SAML transient `NameID` changes | Not used as persistent account key |
| SCIM `id`/`externalId` from two providers | Never merged outside namespace |
| Transfer Finance→People | Old permissions revoked before new grant |
| Org move while session retains Finance role | Session denied/reauth/stale version caught |
| Cross-tenant move | Does not auto-transfer ownership/PII |
| SCIM `active=false` | New logins denied, sessions revoked within SLA |
| SCIM `DELETE` | Resource removal contract and app denial enforced |
| JWT issued before disable | Cannot bypass revocation SLA |
| Duplicate disable event | Idempotent, no error/no privilege grant |
| Stale enable event after disable | Must not reopen account |
| Rehire with same email | Has no old permissions without approval |
| Cross-tenant account ID request | Object-level authorization denies |
| Downstream SCIM timeout | Reports partial/alerts, never fakes completion |
| Multi-node active sessions | Revocation works across all nodes |
| Multiple IdPs | Never auto-linked by email |
| Audit/retention | No secrets logged, PII meets retention limits |

**E2E tests do not stop at HTTP 200 from SCIM PATCH.** Verify database account links, session access, group memberships, object-level authorization, and actual downstream ACKs.

## 25. Misconceptions to Avoid

1. **"Email is an ID because it is unique."** Emails can change or be recycled.
2. **"OIDC `email_verified` proves it is the same person as the old account."** No.
3. **"OIDC `sub` needs no issuer."** False; the key must include the issuer.
4. **"SCIM `id` is generated by the provisioning client."** False; issued by the service provider.
5. **"SCIM `externalId` is globally unique."** False; scoped to the provisioning domain.
6. **"LDAP DN never changes."** False; renames/moves alter DNs.
7. **"SAML transient `NameID` works long-term."** False.
8. **"CAS ST itself is the user ID."** False; ST is a one-time login credential.
9. **"Changing department automatically removes all roles."** False; group/grant reconciliation is needed.
10. **"IdP disable immediately invalidates every `HttpSession`."** Not automatically.
11. **"SCIM `active=false` revokes all JWTs."** No.
12. **"SCIM `DELETE` must physically erase all backups/audits."** Not guaranteed by SCIM.
13. **"Valid JWT signature means the user can still do everything."** No; active status and ACLs still apply.
14. **"Org transfer automatically moves all documents to the new org."** No; business ownership is separate.
15. **"Rehire with same email auto-enables old roles."** Dangerous.
16. **"Later-arriving event is always more trustworthy."** Requires source/version/field authority.
17. **"One Spring `@Transactional` updates every SaaS synchronously."** No.
18. **"Account linking by email suffices for cross-tenant migration."** No.
19. **"Spring authorities auto-update immediately when directory groups change."** Not guaranteed.
20. **"Deleting a user from the IdP needs no tracking of tokens/API keys."** False.

## 26. Practice Questions with Answers

**Q1.** User changes email while `iss+sub` stays unchanged. Should a new app account be created?

**Answer:** No. Keep the internal account ID, update the verified email, and refresh contact/recovery info.

**Q2.** A's old email is reassigned to B. B's IdP sets `email_verified=true`. Should B receive A's data?

**Answer:** No. There is no proof the two subjects are the same person. Never auto-link.

**Q3.** Two OIDC issuers both return `sub=123`. Are they the same user?

**Answer:** Do not assume so; use `iss+sub`.

**Q4.** An LDAP OU rename changes the DN. What should be used to locate the user?

**Answer:** A scoped stable directory object identifier, directory search, and mapping; never a falsely assumed immutable DN.

**Q5.** Does Microsoft Entra recommend object ID or UPN for immutable account binding?

**Answer:** Tenant-scoped object ID; UPN/email can change.

**Q6.** Who assigns SCIM `id`?

**Answer:** The SCIM service provider; optional `externalId` is assigned by the provisioning client per domain.

**Q7.** Should SCIM `externalId=100` from two provisioning clients be merged?

**Answer:** Not merely because the strings match. Scope by source and use verified linking if it truly is the same identity.

**Q8.** For a Finance→People mover, should you revoke or grant first?

**Answer:** Revoke old permissions before granting new ones, with session/cache/token updates so there is no dual-access window.

**Q9.** Why do org transfers make old sessions dangerous?

**Answer:** Authorities, tenant, and claims can go stale; you need a live account gate/`authzVersion`/session revocation.

**Q10.** Does `active=false` automatically revoke already-issued access tokens?

**Answer:** No. Apps/resource servers must enforce revocation/introspection/TTLs or current-state checks.

**Q11.** Is SCIM `DELETE` always a physical hard delete?

**Answer:** No; a server may retain data internally per RFC, provided the resource no longer appears via the SCIM API as before.

**Q12.** Should you change the account ID when email changes to keep systems in sync?

**Answer:** No. An immutable account ID preserves ownership and audit integrity.

**Q13.** Pairwise OIDC `sub` changed after a sector migration. How do you relink?

**Answer:** Authoritative migration mapping or strong account-link verification, never email fallback.

**Q14.** A user transfers orgs, owning Finance documents. Should they auto-move to People?

**Answer:** No; business ownership and privacy policies govern that.

**Q15.** Disabled event version 20 arrives before enable event version 18. Should the old enable apply?

**Answer:** No; check source version and reconcile current state.

**Q16.** A Spring session logged in before the IdP disabled the account. Is a login gate alone enough?

**Answer:** No; you need revocation/current-state authorization for active sessions.

**Q17.** A validly signed SAML Assertion carries `NameID=email`. Should email be used as the key?

**Answer:** No; a signature does not turn a mutable email into an immutable subject.

**Q18.** Should a rehire with the same email regain old admin roles?

**Answer:** Not automatically; require employment/account approval and fresh least privilege.

**Q19.** SCIM PUT vs. PATCH for a rename?

**Answer:** PUT replaces the whole resource, while PATCH performs field-level operations atomically per RFC; handle ETag/versioning as well.

**Q20.** One connector fails after the local app has disabled the user. Can you report offboarding complete?

**Answer:** No. Record partial state, retry/alert/manually revoke, and reconcile.

## 27. Production Checklist

- [ ] Internal account ID is immutable, non-reassignable, and used for owner/audit FKs.
- [ ] External identity is scoped properly by issuer/directory/provider/tenant.
- [ ] Email, display name, UPN, and DN are never used as sole identity keys.
- [ ] OIDC account lookup uses verified `iss+sub`, with no email fallback.
- [ ] SAML subjects use an appropriate persistent/qualifiers contract.
- [ ] CAS/Kerberos/LDAP have stable directory bindings or approved migrations.
- [ ] SCIM `id`/`externalId` are properly understood per provider/client domain.
- [ ] Renames neither create duplicate accounts nor change ownership.
- [ ] Email updates include verification and recovery/notification cleanup.
- [ ] Email reuse cannot cause account takeover.
- [ ] LDAP DN renames/moves do not break lookups.
- [ ] Movers revoke old permissions before granting new roles.
- [ ] Tenant/resource ACLs check object-level access, not just roles.
- [ ] Active sessions and stale tokens are handled within SLA.
- [ ] Disable/suspend denies new logins and revokes active permissions/sessions.
- [ ] SCIM `active=false`/`DELETE` are tested per vendor without assuming all tokens vanish.
- [ ] Downstream provisioning has ACKs, retries, and reconciliation.
- [ ] Event idempotency, `sourceVersion`, and out-of-order handling are explicit.
- [ ] Stale enable events cannot reopen disabled accounts.
- [ ] Rehires/cross-tenant migrations go through verified identity linking.
- [ ] SCIM endpoints are protected by provisioning-client auth, tenant scoping, and input validation.
- [ ] ETags/`If-Match` prevent lost updates when supported by the provider.
- [ ] Audits record identities by immutable ID, minimize PII, and store no secrets.
- [ ] Data deletion/retention/legal holds follow dedicated policies.
- [ ] Monitoring tracks revocation latency, unmapped identities, and downstream failures.
- [ ] Tests verify user B with A's recycled email **cannot** access A's account.
- [ ] E2E tests cover multi-node/session stores and IdP migration paths.

## 28. Conclusion

**Renames and email changes are profile updates and must never alter the underlying subject.** **Organization transfers are permission changes**, requiring revocation of old entitlements and checks on active sessions/tokens. **Disabling/deleting an account is a multi-system workflow**, not a single SCIM PATCH or IdP logout.

Remember four principles:

1. **Stable identity:** immutable app-local account ID; external bindings with explicit, verified issuer/provisioning scope.
2. **Mutable profile:** display name, email, username, and LDAP DN do not define data ownership.
3. **Current authorization:** `ACTIVE`, org memberships, resource ACLs, security epochs, and revocation must be enforced even after login.
4. **No implicit relinking:** matching emails do not prove the same person; migrations, rehires, and tenant moves require approval and evidence.

A mature federation system guarantees the **right person, right account, right organization, right permissions, and right lifecycle** even as login names, emails, or organizations change.

### Official Documentation

1. OpenID Connect Core 1.0, Section 5.7 Claim Stability and Uniqueness: https://openid.net/specs/openid-connect-core-1_0.html
2. IETF RFC 7643 — SCIM Core Schema (id, externalId, active, emails, enterprise extension): https://www.rfc-editor.org/rfc/rfc7643.html
3. IETF RFC 7644 — SCIM Protocol (PATCH, DELETE, ETag, If-Match): https://www.rfc-editor.org/rfc/rfc7644.html
4. Microsoft Learn — UPN changes, using Entra object ID instead of UPN/email: https://learn.microsoft.com/en-us/azure/active-directory/hybrid/howto-troubleshoot-upn-changes
5. OASIS SAML 2.0 Core, persistent/transient NameID and qualifiers: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
6. Spring Security — OAuth2 Login advanced OIDC UserService and authorities mapping: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
7. Spring Security — LDAP Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html
8. Spring Security — Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
9. Spring Security — SAML2 Login: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
10. Spring Security — CAS Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html
11. Spring Session — SessionRepository and distributed sessions: https://docs.spring.io/spring-session/reference/api.html
