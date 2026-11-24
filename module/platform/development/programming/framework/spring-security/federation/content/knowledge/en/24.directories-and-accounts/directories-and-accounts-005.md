# Account Synchronization with SCIM in a Dedicated System and Spring Security Boundaries

**SCIM (System for Cross-domain Identity Management)** is a suite of standards for **provisioning, updating, deactivating, and managing identity data** between a governing source system and target applications. SCIM 2.0 is primarily defined by **RFC 7643** (Core Schema) and **RFC 7644** (Protocol), built on HTTP and JSON. SCIM commonly serves the **joiner–mover–leaver** lifecycle: new employees receive accounts, role/group changes update permissions, and departing employees have accounts deactivated across connected applications.

**Spring Security is not a dedicated SCIM provisioning/synchronization system.** It provides **authentication, `SecurityContext`, `UserDetails`, `AuthenticationProvider`, OAuth2/OIDC, and authorization** for a Spring application; it does not run an identity-sync orchestrator across hundreds of systems, does not auto-generate standard SCIM endpoints, and does not implement a reconciler, HR lifecycle, connector catalog, or multi-source conflict resolution. You can use Spring Security **to protect a SCIM API that you build**, and use SCIM-provisioned account data **to make login/authorization decisions** in the application; those are two separate responsibilities.

**Critical rules:** **SCIM provisioning does not equal SSO**, a **SCIM group does not automatically become a `GrantedAuthority`**, and **`active=false` at the target system does not automatically revoke every previously issued Spring session, OAuth token, or API key**. Data flow, identity mapping, account-state enforcement, and revocation must all be explicitly designed.

This lesson belongs to **Spring Security – federation → Directories and Accounts**, covering architecture, Users/Groups schemas, HTTP operations, deprovisioning, consistency, security, multi-tenant mapping, Spring Security examples, a standalone Java 17 program, and a production checklist.

## 1. When Is SCIM Needed Instead of SSO Login Alone?

An organization has employees in a human resources system (HRIS), identities managed in IAM/IdP, and dozens of applications like CRM, accounting, LMS, and Helpdesk. If only OIDC/SAML SSO is configured:

- Users can prove their identity when they reach the login page.
- Applications are not guaranteed to **already have an internal account**, license, tenant configuration, or groups.
- Departing users may still retain account data, permissions, sessions, and API tokens in target systems.
- Accounts may be created **Just-In-Time (JIT)** on first login, leaving users who never logged in unprovisioned; account deletion also does not happen automatically.
- Group/department/manager changes in HRIS do not propagate automatically to every application.
- Auditing which applications still hold active accounts for a person is difficult.

SCIM addresses the **identity provisioning data plane**: a dedicated provisioning service sends create/update/disable commands for Users and Groups to approved SCIM endpoints. SSO addresses the **authentication plane**. The application must still enforce the **authorization plane** under its own policy.

~~~text
       HRIS / Directory / IAM authoritative systems
                         |
                  Joiner / Mover / Leaver
                         |
                         v
        Identity Governance / Provisioning Engine
        - Identify authoritative data sources
        - Map schemas & tenants
        - Manage connectors, tokens, retries, audits
                         |
               SCIM 2.0 client requests
                         |
                  HTTPS + client auth
                         |
                         v
          Dedicated SCIM Service / SCIM Provider
          POST/GET/PATCH/PUT/DELETE Users, Groups
                         |
                Account + Membership Store
                         |
              +----------+------------+
              |                       |
              v                       v
       Business application     Authorization service
        Spring Security          entitlement/role policy
              |
        OIDC/SAML/other login
              |
      Check local account active,
      tenant and resource permissions
~~~

**The SCIM service and business app do not have to run on two separate machines**: in products with native SCIM support, they can live in the same deployment. However, **provisioning business responsibility** still needs its own component/owner rather than being dumped onto Spring Security core.

## 2. SCIM Roles and Who Owns the Data

| Role | Meaning | Example |
| --- | --- | --- |
| **Authoritative source** | System that determines truth for a given data type | HRIS owns termination date; directory owns account identity |
| **Provisioning engine / SCIM Client** | Reads events/reconciles and sends SCIM requests | IAM/IGA connector |
| **SCIM Service Provider** | Target REST API exposing Users/Groups | Provisioning service of a SaaS application |
| **Target account repository** | Stores identities and states inside the app | Users, memberships, and entitlements tables |
| **Identity Provider / Authorization Server** | Authenticates users and issues SAML/OIDC tokens | Corporate IdP |
| **Relying Party / Resource Server** | Receives users/tokens and enforces permissions | Spring Boot Portal/API |
| **Business authorization owner** | Approves functional/tenant policies | Billing owner team |
| **Reconciliation/audit component** | Detects drift and remediates under control | Provisioning job or IGA |

**Do not confuse the SCIM Client with an employee's browser**: a SCIM Client is typically a machine-to-machine application with its own credentials calling a protected SCIM endpoint directly. **End users never submit username/password to SCIM** to log in.

## 3. What Does SCIM Solve—and What Does It Not?

| Question | SCIM | Other component |
| --- | --- | --- |
| Create accounts at the target application? | **Yes**, when target supports create | HRIS/IAM decides when to create |
| Update display name, email, department? | **Yes**, per schema/extension | Data owner determines authoritative source |
| Add/remove group members? | **Yes**, via Groups/members if supported | Authorization owner decides which group maps to which role |
| Lock or disable a user? | **Possible**, typically `active=false` | App must enforce login/session blocking |
| Delete user from target? | **Yes**, DELETE per provider contract | Retention, legal hold, audit belong to app/business |
| Sign users in via SSO? | **No** | OIDC/SAML/Kerberos/other authentication |
| Verify passwords on every request? | **No** | Spring Security/IdP |
| Issue OAuth access tokens to users? | **Not a SCIM function** | Authorization Server |
| Automatically turn a Group into `ROLE_ADMIN`? | **No** | Application entitlement/role mapping |
| Revoke all issued sessions? | **Not by default** | Session registry, logout/revocation strategy |
| Design permission-approval workflows? | **Outside core protocol** | IAM/IGA, policy engine |
| Guarantee instant sync to every target? | **No** | Delivery/retry/reconciliation + SLA |
| Deduplicate across tenants and identity brokers? | **Not automatic** | Identity linking & source namespace policy |

**SCIM is a data-management protocol**, not a magic switch that makes Spring Security "know every user and role".

## 4. Foundational RFCs and Versions

**SCIM 2.0** rests on three core documents:

1. **RFC 7642 — Definitions, Overview, Concepts and Requirements:** cross-domain identity management context.
2. **RFC 7643 — Core Schema:** defines User, Group, common attributes, enterprise extension, and schema discovery.
3. **RFC 7644 — Protocol:** URI/HTTP methods, filtering, pagination, PATCH/PUT/DELETE, bulk, error format, concurrency, and security.

The REST base URI is often written like `https://provisioning.example.test/scim/v2`, **but that is an example**—not every server is required to use the exact `/scim/v2` path. Standard relative paths are typically:

~~~text
/Users
/Users/{id}
/Groups
/Groups/{id}
/ServiceProviderConfig
/ResourceTypes
/Schemas
~~~

Clients should read capabilities from discovery rather than assuming every implementation supports all operations/optional features. For instance, **PATCH, bulk, filtering, sorting, and ETag** have capability flags; never assume "SCIM 2.0 means every feature is enabled".

The standard **media type** for SCIM JSON is `application/scim+json`. SCIM may use bearer tokens or other HTTP authentication; the RFC itself does not mandate a single OAuth grant type.

## 5. Standard User Fields: id, externalId, and userName

In RFC 7643, three fields are easily confused:

| Field | Who assigns it? | Properties | Should it be used as a link key? |
| --- | --- | --- | --- |
| `id` | **SCIM Service Provider** (target) | Required, unique/stable/non-reassignable within provider; read-only | Used to call `/Users/{id}` and store target mapping |
| `externalId` | **Provisioning Client** | Optional, scoped to provisioning domain; provider need not enforce global uniqueness | Good for source mapping when paired with source/tenant scope |
| `userName` | **SCIM Service Provider defines semantics**; client usually sends on create | Required on User, unique among provider's Users, case-insensitive per core schema | Should not be an immutable lifecycle key, as it can change |
| `emails` | Source per contract | Multi-valued, updatable/recyclable | Never use as sole identity-link proof |
| `active` | Client or target per policy | User status per SCIM core | Used to update login eligibility; does not auto-revoke sessions |

**Never use email as the provisioning primary key.** An employee changing name/email, a recycled alias, or a partner with a colliding email must still preserve the right identity. Use `(authoritative_source, externalId)` as the identity link at the provisioning layer and **SCIM `id`** to manipulate target resources. When `userName` changes, avoid creating a second account.

### SCIM User example

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User",
    "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
  ],
  "externalId": "hris-employee-0042",
  "userName": "alice@corp.example.test",
  "active": true,
  "name": {
    "givenName": "Alice",
    "familyName": "Nguyen"
  },
  "emails": [
    {
      "value": "alice@corp.example.test",
      "type": "work",
      "primary": true
    }
  ],
  "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {
    "employeeNumber": "0042",
    "department": "Finance",
    "costCenter": "F-120"
  }
}
~~~

The data, domain names, and employee ID above are illustrative only. **Do not send `id` on creation** because the provider assigns `id`; the Enterprise User extension requires actual target support as advertised in `/ResourceTypes`/`/Schemas`.

## 6. Group Schema and Member References

A SCIM Group has a `displayName` and may contain a `members` set referencing Users/Groups by the target service's **SCIM resource IDs**.

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:Group"
  ],
  "externalId": "iam-group-finance-readers",
  "displayName": "finance-readers",
  "members": [
    {
      "value": "user-100",
      "type": "User",
      "$ref": "https://provisioning.example.test/scim/v2/Users/user-100"
    }
  ]
}
~~~

**Distinguish Group ID from display name.** A group with `displayName=finance-readers` in tenant North is not automatically the same group in tenant South. Group membership is provisioning data; the application must decide which group ID/namespace maps to which role or entitlement.

**Nested groups** can be expressed in the schema model, but support for group nesting/cascading varies across products and may be restricted. Check `/Schemas` and the vendor contract; never claim that every target automatically expands recursive membership or updates all permissions immediately.

## 7. Discovery Endpoints and Interoperability

A new SCIM Client should read configuration from the registered Service Provider:

~~~http
GET /scim/v2/ServiceProviderConfig HTTP/1.1
Host: provisioning.example.test
Accept: application/scim+json
Authorization: Bearer SCIM_CLIENT_TOKEN
~~~

Condensed capabilities example:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"
  ],
  "patch": { "supported": true },
  "bulk": {
    "supported": false,
    "maxOperations": 0,
    "maxPayloadSize": 0
  },
  "filter": {
    "supported": true,
    "maxResults": 100
  },
  "changePassword": { "supported": false },
  "sort": { "supported": false },
  "etag": { "supported": true },
  "authenticationSchemes": [
    {
      "type": "oauthbearertoken",
      "name": "OAuth Bearer Token"
    }
  ]
}
~~~

Remaining discovery endpoints:

- `GET /ResourceTypes`: advertised resource types and schema extensions.
- `GET /Schemas`: fields, types, mutability, required flags, uniqueness, multi-valuedness.
- `GET /ServiceProviderConfig`: optional capabilities, auth schemes, and limits.

**Note:** some discovery endpoints may be exposed publicly by servers per RFC, but enterprises may require authentication. Never hardcode that no token is needed. Public discovery does not allow writing data without authorization.

## 8. Creating Accounts: POST /Users

A SCIM Client can send a new user to the target:

~~~http
POST /scim/v2/Users HTTP/1.1
Host: provisioning.example.test
Authorization: Bearer SCIM_CLIENT_TOKEN
Content-Type: application/scim+json
Accept: application/scim+json

{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User"
  ],
  "externalId": "hris-0042",
  "userName": "alice@corp.example.test",
  "active": true,
  "name": {
    "givenName": "Alice",
    "familyName": "Nguyen"
  }
}
~~~

On success, the server returns **HTTP 201 Created**, issuing its own `id` and appropriate `Location` URL:

~~~http
HTTP/1.1 201 Created
Location: https://provisioning.example.test/scim/v2/Users/u-100
Content-Type: application/scim+json
ETag: W/"v1"

{
  "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
  "id": "u-100",
  "externalId": "hris-0042",
  "userName": "alice@corp.example.test",
  "active": true,
  "meta": {
    "resourceType": "User",
    "location": "https://provisioning.example.test/scim/v2/Users/u-100",
    "version": "W/\"v1\""
  }
}
~~~

The response is an **illustrative sample**; `ETag`/`meta.version` appear when the provider supports versioning. Never place real tokens in documentation/logs, and never assume the server preserves every request field verbatim.

### When POST times out

`POST` is not inherently idempotent. If the client does not receive a response, **do not endlessly retry POST** because the user may already have been created. Query by stored target `id`, or filter by scoped `externalId`/`userName` if supported; reconcile before creating again. On `409 uniqueness`, resolve duplicates under control rather than generating a random `userName` to "work around the error".

## 9. GET, ListResponse, Filtering, and Pagination

Reading a user by target ID:

~~~http
GET /scim/v2/Users/u-100 HTTP/1.1
Host: provisioning.example.test
Authorization: Bearer SCIM_CLIENT_TOKEN
Accept: application/scim+json
~~~

Searching by `externalId` **when the provider supports filtering**:

~~~text
GET /scim/v2/Users?filter=externalId%20eq%20%22hris-0042%22
~~~

In practice, properly URL-encode the filter, constrain user-supplied values, and never concatenate unescaped filter strings—avoiding syntax errors or probing data outside tenant scope.

A SCIM list response typically uses the **ListResponse** schema URI:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:ListResponse"
  ],
  "totalResults": 1,
  "startIndex": 1,
  "itemsPerPage": 1,
  "Resources": [
    {
      "schemas": [
        "urn:ietf:params:scim:schemas:core:2.0:User"
      ],
      "id": "u-100",
      "externalId": "hris-0042",
      "userName": "alice@corp.example.test",
      "active": true
    }
  ]
}
~~~

**Index-based pagination** in RFC 7644 uses **1-based `startIndex`** and `count` for desired results per page. Filter/sort features may be optional; check `ServiceProviderConfig`. For large user sets, use proper pagination and checkpoints/reconciliation rather than issuing one `GET` assuming unbounded results.

**Never treat an empty result as proof that a user was permanently deleted** when the client uses filters or lacks read entitlements. Check status, filter support, tenant scope, and retry before deciding to recreate.

## 10. PATCH: Modifying Specific Attributes Without Overwriting the Whole User

RFC 7644 defines SCIM PATCH, but **PATCH is an optional server capability**, advertised via `ServiceProviderConfig.patch.supported`. The body uses the **PatchOp** schema and an **`Operations`** array containing `add`, `remove`, or `replace`.

Example changing department:

~~~http
PATCH /scim/v2/Users/u-100 HTTP/1.1
Host: provisioning.example.test
Authorization: Bearer SCIM_CLIENT_TOKEN
Content-Type: application/scim+json

{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "replace",
      "path": "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:department",
      "value": "Accounting"
    }
  ]
}
~~~

Simpler example disabling an account:

~~~json
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
~~~

**Distinguish SCIM PATCH from JSON Patch (RFC 6902)**: SCIM uses `Operations` and SCIM attribute paths, and does not support array indexing like JSON Patch. Operations within a single SCIM PATCH request must be **processed atomically**: if one operation fails, the resource reverts to its initial state per RFC.

Do not assume every server returns the resource body after PATCH: it may return **200 with the resource** or **204 No Content** depending on the server. For sensitive deprovisioning, the client can GET/reconcile to confirm the actual state.

## 11. PUT: Full Replacement and the Risk of Accidentally Deleting Attributes

`PUT /Users/{id}` is used to **replace resource attributes** subject to SCIM mutability rules. Unlike PATCH, PUT may clear or reset omitted attributes depending on schema and RFC behavior.

**Risk:** the provisioning engine only wants to change department, but sends a PUT missing group-related or enterprise extension fields, wiping out target-managed data.

Rules:

1. Use PATCH if the server supports it and only a few fields need updating.
2. With PUT, read the current resource, understand per-attribute ownership, and send a complete representation per contract.
3. Never overwrite read-only attributes such as `id`/`meta.created` with client values.
4. Never use PUT to create a new user if the resource does not exist; RFC forbids using PUT to create SCIM resources.
5. With multiple provisioning clients, use version/`ETag` if supported.
6. Prevent an HRIS source from accidentally overwriting app-specific custom fields if HRIS is not their authoritative owner.
7. Test on a canary account and compare before-and-after state.
8. Do not endlessly retry PUT on `If-Match` conflicts; reconcile instead.

**Do not assume "PUT is like JPA's `updateProfile()`"**. In REST/SCIM, it is a full resource replacement with specific schema and concurrency semantics.

## 12. Syncing Groups and Member Lists

When an employee changes groups, the provisioning engine can modify `/Groups/{id}`. Example adding an existing user to a Group (when PATCH is supported):

~~~http
PATCH /scim/v2/Groups/g-finance HTTP/1.1
Host: provisioning.example.test
Authorization: Bearer SCIM_CLIENT_TOKEN
Content-Type: application/scim+json

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
          "value": "u-100",
          "type": "User"
        }
      ]
    }
  ]
}
~~~

To remove a user from a group, SCIM PATCH supports **valuePath filters**, conceptually:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "remove",
      "path": "members[value eq \"u-100\"]"
    }
  ]
}
~~~

Verify that the target supports group PATCH, `valuePath`, and any server-specific constraints. **Never try to clear group membership by sending an empty array to arbitrary providers** without checking semantics: it may wipe out all members.

**Important:** Group membership changes in the SCIM repository **do not automatically update the Spring `SecurityContext` of a logged-in user immediately**. For sensitive permissions, implement entitlement lookups, version checks, or session invalidation in the app.

## 13. Deprovisioning: active=false vs. DELETE

Two actions are commonly discussed when an employee leaves:

- **Deactivate (logical disable):** update `active=false` if the SCIM server supports it and the app has a contract to handle it. The resource can remain to preserve history, mappings, audits, and retention.
- **`DELETE /Users/{id}`:** requests resource deletion per SCIM protocol and business policy. Depending on implementation, the outcome may be hard delete, tombstone, or soft delete; never assume all records and logs are physically purged.
- **Application-level suspend/lock:** a local state that may exist independently of `active`; the application must enforce access-blocking states per policy.

~~~text
HRIS: employee left
    |
    v
Provisioning engine
    | -- SCIM PATCH active=false --> target
    | -- update group membership --> target
    v
Target account DB: active=false
    |
    +--> New login: DENY even if IdP session is still active
    |
    +--> Existing web session: must revoke or check active per request
    |
    +--> API keys/service tokens: independent revocation policy
    |
    +--> Audit/retention: retain per legal and business data rules
~~~

**Never promise "SCIM deactivate = immediate logout on every device".** If Spring only loads `UserDetails` once at login, the local session still holds old authorities. The IdP may also keep issuing tokens until upstream revocation occurs. Ensure **denial at the application** or session/token revocation within the agreed SLA.

## 14. Detailed Joiner–Mover–Leaver Lifecycle

| HR/IAM Event | SCIM Action | Additional Application Action |
| --- | --- | --- |
| Joiner: employee hired | Create User, `active` per policy, add Groups | Assign license if applicable; link IdP subject; no default auto-admin |
| Pre-hire: before start date | May create with `active=false` | Disallow login before effective date |
| Mover: department transfer | PATCH enterprise attributes, update group memberships | Revoke old group permissions, refresh entitlement cache |
| Mover: tenant transfer | Transfer/remove membership per policy | Check data isolation, transfer resource ownership if permitted |
| Rename: name/email change | PATCH name/email/`userName` as appropriate | Keep stable SCIM `id` and external identity link |
| Leave: offboarding | `active=false` or `DELETE` per policy | Revoke sessions, refresh tokens, API keys, delegated grants |
| Rehire: employee returns | Decide restore vs. new identity per HR/IGA policy | Prevent erroneous linking to old accounts, history, or entitlements |
| Identity merge/split | Approved workflow adjusting source links | Never auto-merge two people due to matching email |
| Group removed | Update `/Groups` membership | Remove permissions, check existing sessions/authorization |
| Tenant closed | Bulk disable/remove memberships per policy | Prevent cross-tenant access and preserve legal retention |

**The Mover phase is often harder than Joiner:** **revoking old permissions** must be tested, not just granting new ones. A provisioning job that grants new access without removing prior-role permissions causes privilege accumulation.

## 15. Source of Truth: Avoid Having Every System Write Everything

In large organizations, multiple systems hold data that is "authoritative" in its own domain:

| Attribute | Potentially authoritative source | Should not be allowed |
| --- | --- | --- |
| Employee number, hire/leave date | HRIS | Business app overwriting it |
| Identity subject/issuer link | IAM/IdP directory | Email form self-editing and auto-linking |
| Display name | HRIS or directory | SCIM target arbitrarily edited then overwritten |
| Department/manager | HRIS/IGA | Local app writing back without approval |
| Account status | HR lifecycle + security suspensions | SCIM `active=true` automatically lifting a security suspension |
| Application roles | App entitlement owner/IGA policy | Every SCIM group string becoming a permission |
| Tenant membership | Tenant administrator/IGA contract | Browser-chosen tenant header |
| License quota | SaaS target/commerce system | SCIM client guessing without checking target constraints |
| Audit/retention | Compliance/legal owner | `DELETE` erasing history despite legal hold |

**An `active=true` event from HRIS must never override an account lock placed by Security Operations.** You may need a composite state:

~~~text
effective_login_allowed =
    scim_provisioned_active
    AND NOT locally_suspended
    AND security_policy_allows
    AND tenant_access_current
    AND (other application requirements)
~~~

Do not use a single `active` boolean as the sole state machine for all security controls.

## 16. Synchronization Is Not a Distributed Transaction Across Systems

A single HRIS event might update 10 applications via SCIM. Nine may succeed while one returns `503`/`429`. **SCIM does not provide distributed transactions or atomic rollback across Service Providers.**

Operational architecture requirements:

1. **At-least-once delivery:** events may be redelivered.
2. **Idempotent apply by source key:** never create duplicate users on repeated events.
3. **Ordering or versioning:** a stale join event must not overwrite a newer leave event.
4. **Retry with backoff + jitter:** honor rate limits/`Retry-After` when returned by the provider.
5. **Dead-letter queue/quarantine:** for events that cannot recover automatically.
6. **Reconciliation:** periodically compare authoritative intended state against actual target state.
7. **Alerting:** especially on deactivation failures or privilege-removal failures.
8. **Audit & provenance:** know which event, who, when, and what the target confirmed.
9. **Controlled rollback:** never auto-reenable users merely because a deployment rolled back.
10. **Authorized manual intervention:** e.g., identity/tenant conflicts requiring human approval.

**Eventual consistency** must have an **SLA**: acceptable latency from HRIS leave to target denial. For sensitive applications, polling SCIM every few hours may be insufficient; real-time revocation and local authorization guards are needed.

## 17. Idempotency and Identity Mapping in Dedicated Provisioning

A safe mental model:

~~~text
source_system = HRIS_CORP
source_user_id = emp-0042
target_system = BILLING

(source_system, source_user_id, target_system)
    -> target SCIM id = u-100
~~~

If `userName` changes, the mapping still points to `u-100`. If another source also uses `externalId` `emp-0042`, that is a different identity:

~~~text
HRIS_CORP  / emp-0042 -> u-100
HRIS_PARTNER / emp-0042 -> u-201
~~~

**The SCIM spec states `externalId` is scoped to the provisioning domain; providers are not required to enforce global uniqueness.** Therefore, the provisioning engine should maintain explicit source namespaces and target identity mappings. A multi-tenant target app can enforce additional database constraints per its designed trust boundary.

### Handling duplicate events

- Before POST, if a target `id` is stored, GET by `id` and reconcile.
- If no `id` is stored, query by `externalId` when filtering is supported and the source namespace is clear.
- If 0 results, create; if 1 result, update per policy; if multiple, halt and investigate the collision.
- If POST returns `409 uniqueness`, do not randomize `userName`; verify whether it belongs to the same source user.
- If a network timeout occurs after POST, **do not assume create failed**.
- On repeated PATCHes, design convergent desired state rather than endlessly appending duplicate group members.
- With older event versions, do not overwrite newer state.
- When an account is security-suspended, an old `active=true` event must not re-enable it.
- Use **account version/`If-Match`** when the target provides `ETag`s.

**Idempotence is a workflow property of the provisioning engine**, not a built-in guarantee of every SCIM POST.

## 18. ETag and If-Match to Prevent Lost Updates

A SCIM provider may support **`ETag`**, exposed in HTTP headers and `meta.version`. When modifying a previously read resource, the client can send:

~~~http
PATCH /scim/v2/Users/u-100 HTTP/1.1
Host: provisioning.example.test
Authorization: Bearer SCIM_CLIENT_TOKEN
Content-Type: application/scim+json
If-Match: W/"v7"

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
~~~

If the resource version changed, the server may return **412 Precondition Failed**. The client must GET again, compare desired state, and reapply per policy—never retry with a fabricated `If-Match` or strip the precondition just to force an overwrite.

**Lack of ETag does not mean the server cannot handle concurrency**, but the provisioning engine must implement alternative locking/versioning or reconciliation. **An atomic SCIM PATCH on one resource** is different from **a synchronized transaction across 10 applications**.

## 19. Securing the SCIM Endpoint

SCIM is a **high-privilege administrative API**: a client can create users, change groups, lock, or unlock accounts. If credentials leak, the blast radius can exceed that of a normal user login.

Principles:

- **HTTPS/TLS** with certificate and hostname verification.
- The SCIM client must have **separate authentication**, typically OAuth2 bearer `client_credentials` or mTLS per provider policy.
- Tokens must carry an **audience dedicated to the SCIM API**, the right client identity, and minimal scopes/permissions.
- Separate read-only Users/Groups credentials from create/modify/deactivate credentials where possible.
- Restrict which tenants/resources a client may modify; never let a connector for tenant A provision users in tenant B.
- Never accept user-supplied target URLs, preventing **SSRF or token exfiltration**.
- Never log OAuth tokens, passwords, API keys, raw PII, or unsanitized JSON user payloads.
- Validate schemas, attribute mutability, max payload size, member counts, rate limits, and timeouts.
- Enforce certificate/key rotation and avoid ownerless long-lived static secrets.
- Never grant admin rights based on email or `displayName`.
- Audit service identity, operation, target ID, tenant, outcome, correlation ID, and policy version.

**RFC 7644 does not mandate one universal authentication method for all providers**. `ServiceProviderConfig.authenticationSchemes` declares supported mechanisms; a Spring Resource Server uses JWT/opaque tokens only when that is the agreed architecture.

## 20. Why Use a Dedicated SCIM System Instead of Putting It Inside Spring Security?

**Spring Security manages request-level security**, not an account-lifecycle orchestration engine. Dedicated provisioning requires much that sits outside this library:

| Task | Spring Security core? | Appropriate component |
| --- | --- | --- |
| OIDC/OAuth2/SAML login (with modules) | Has corresponding integrations | Spring Security |
| Build `Authentication`/`SecurityContext` | Yes | Spring Security |
| Enforce `hasRole`/`hasAuthority`, method security | Yes | Spring Security + business policy |
| Validate bearer JWT/opaque tokens for SCIM API | Yes, via Resource Server | Spring Security |
| Build SCIM Users/Groups resources, schema discovery, PATCH engine | **Not provided out-of-the-box as a standard SCIM server** | SCIM service/vendor/library owned by IAM team |
| Pull HRIS events, provision accounts across dozens of targets | No | IGA/provisioning engine |
| Deduplication, cross-system identity mapping | No | Identity registry/provisioning service |
| Retries, DLQ, reconciliation, conflict resolution | No | Workflow/event processing |
| Multi-tenant provisioning policy | Not by default | IAM + target authorization |
| Mass revocation of app sessions/tokens | Not automatic on SCIM update | Session/revocation service and application |
| License entitlement/offboarding workflows | No | Business IAM/IGA |
| Data retention, GDPR/legal hold | No | Data governance + target policy |

**You can build a SCIM Service Provider with Spring Boot** and protect that API with Spring Security; however, **RFC 7643/7644 compliance must be implemented and tested yourself**—it does not appear simply by adding `spring-boot-starter-security`. Never invent a property like `spring.security.scim.enabled=true` expecting automatic SCIM provisioning.

## 21. How Does Spring Security Consume SCIM-Provisioned Data?

A Spring application can maintain an account table synced by IAM via SCIM:

~~~text
Identity Provider -- OIDC token ----> Spring Application
                                          |
                                     oauth2Login
                                       or JWT
                                          |
                                  verified issuer + subject
                                          |
                                   local identity link
                                          |
                   SCIM-provisioned local account active/groups
                                          |
                                 Spring Authentication
                                          |
                      GrantedAuthority + tenant/resource policy
~~~

**Authentication path:** verify the token/session per protocol. **Provisioning path:** update the account repository independently. The application must connect them via a **verified identity link** rather than blindly trusting `userName` or email.

Example:

~~~text
OIDC login identity:
  issuer  = https://idp.example.test/tenant/corp
  subject = user-oidc-7781

SCIM source:
  source_system = HRIS_CORP
  externalId    = emp-0042
  target id     = u-100

Internal linked account:
  local_account_id = acct-100
  active           = true
  tenant           = north
~~~

Only after IAM/the target has verified that both external identities belong to the **same person** does Spring allow `acct-100` to sign in. Never auto-link solely because emails match.

### Where is `active=false` checked?

In `UserDetailsService`, the `OidcUserService`/account-linking layer, a custom `AuthenticationProvider`, or an authorization guard; **never rely solely on the token still being valid**. With stateless JWT sessions and permissions requiring fast revocation, account-state checks may need to run on **every sensitive request**, not just initial login.

## 22. Spring Boot: Protecting a Custom SCIM API Built by a Dedicated Team

The sample below is for a **custom SCIM Service Provider written with Spring Boot 3.x / Spring Security 6.x**. Spring Security only **protects** `/scim/v2/**` using OAuth2 JWT. It **does not auto-create SCIM endpoints, request validation, schemas, persistence, or synchronization**.

**application.yml** (requires a real Authorization Server with JWKS/metadata):

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://auth.example.test"
          audiences: "scim-provisioning-api"
~~~

**SecurityFilterChain:**

~~~java
package com.example.provisioning.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ScimApiSecurityConfiguration {

    @Bean
    SecurityFilterChain scimApi(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/scim/v2/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/scim/v2/**")
                        .hasAuthority("SCOPE_scim.read")
                        .requestMatchers(HttpMethod.POST, "/scim/v2/**")
                        .hasAuthority("SCOPE_scim.write")
                        .requestMatchers(HttpMethod.PUT, "/scim/v2/**")
                        .hasAuthority("SCOPE_scim.write")
                        .requestMatchers(HttpMethod.PATCH, "/scim/v2/**")
                        .hasAuthority("SCOPE_scim.write")
                        .requestMatchers(HttpMethod.DELETE, "/scim/v2/**")
                        .hasAuthority("SCOPE_scim.write")
                        .anyRequest().denyAll())
                .sessionManagement(s -> s
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(csrf -> csrf.disable())
                .oauth2ResourceServer(oauth ->
                        oauth.jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

**Crucial caveats when applying:**

1. This is a **class in a Spring project**, requiring Spring Web, Spring Security, and OAuth2 Resource Server dependencies; it is not standalone JDK code.
2. `csrf.disable()` is appropriate only in a **genuinely cookie-free machine-to-machine Bearer-only** security chain. If the service uses browser sessions, design CSRF properly; never disable CSRF globally without conditions.
3. `SCOPE_scim.read`/`SCOPE_scim.write` are **custom example scopes defined by the AS/application**. The SCIM RFCs do not standardize those strings.
4. Matches only `/scim/v2/**`; **additional `SecurityFilterChain`s** are needed to protect business and management endpoints.
5. Verify JWT `iss`/`aud`/`exp`/signature; the app must also verify **client ID, tenant scope, operation, and resource-level authorization**, as a generic write scope may be overly broad.
6. Discovery endpoints can have their own read policy; this sample requires a token for GET, which is valid when an organization chooses it.
7. Controllers/services/DAOs must implement proper SCIM semantics: IDs, errors, atomic PATCH, filters, Groups, ETags, and data persistence.
8. With multiple OAuth clients, each client may only modify resources within its registered tenant/scope; never rely solely on a system-wide Bearer scope.
9. Verify Spring Boot properties and APIs against the **exact BOM version**; JWT `audiences` is supported in modern Spring Boot releases, but test the build/release.
10. Never treat API-level security as proof that an end user has business app access; a SCIM client is a machine identity.

**Do not treat the `SecurityFilterChain` above as a complete SCIM server.** It only authenticates and restricts requests reaching your separate SCIM handler.

## 23. Spring App Login Before Account Provisioning Completes

A race condition can occur:

~~~text
09:00 HRIS creates user.
09:01 IAM enables SSO/IdP login.
09:02 User succeeds at OIDC login.
09:03 SCIM POST to target has not run yet or is returning 503.
09:04 Spring finds no linked local account.
~~~

**Do not auto-create a local admin account from the token's email** just to avoid showing the user an error.

Strategies:

- **Fail closed** and display a "provisioning pending" message with a request correlation ID.
- **Deferred activation:** allow login to the target only after target SCIM provisioning confirms.
- **Controlled JIT provisioning:** if policy permits, create a minimal account via a separate verified flow with source mapping and restricted entitlements; do not let it replace SCIM lifecycle/deprovisioning.
- **Bounded wait/retry:** if IAM confirms a pending event, avoid infinite loops and grant no permissions while data is missing.
- **Monitoring:** alert when users receive SSO access while target provisioning misses its SLA.
- **Reconciliation:** once SCIM finishes creating the account, subsequent logins succeed per policy.

**JIT and SCIM can coexist with clear ownership**: who is authoritative, how duplicates are prevented, account state merging, and leave handling. There is no universal rule that SCIM must always run before SSO in every system.

## 24. Standalone Java 17: Simulating Idempotent Upsert and Account Disable

This example simulates **provisioning-repository policy** and **application-side authorization checks**; it does not implement a real SCIM server/protocol. It uses **`source + externalId`** as the key to avoid duplicates, keeps target IDs stable across updates, denies access when inactive, and does not map a raw `ROLE_ADMIN` group to administrative privileges.

Create file **`ScimLifecycleDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public class ScimLifecycleDemo {

    record Key(String source, String externalId) {}

    record Account(
            String targetId,
            Key key,
            String userName,
            boolean active,
            Set<String> groups,
            int version) {}

    static final class TargetDirectory {
        private final Map<Key, Account> accounts = new HashMap<>();
        private int idSequence;

        Account upsert(
                String source,
                String externalId,
                String userName,
                boolean active,
                Set<String> groups) {

            Key key = new Key(source, externalId);
            Account old = accounts.get(key);
            Set<String> safeGroups = Set.copyOf(groups);

            if (old != null
                    && old.userName().equals(userName)
                    && old.active() == active
                    && old.groups().equals(safeGroups)) {
                return old; // Duplicate event: no new id/version.
            }

            String id = old == null
                    ? "usr-" + (++idSequence)
                    : old.targetId();
            int version = old == null ? 1 : old.version() + 1;
            Account current = new Account(
                    id, key, userName, active, safeGroups, version);
            accounts.put(key, current);
            return current;
        }

        Account find(String source, String externalId) {
            return accounts.get(new Key(source, externalId));
        }

        int size() {
            return accounts.size();
        }

        String authorize(
                String source,
                String externalId,
                String tenant,
                String permission) {

            Account account = find(source, externalId);
            if (account == null) {
                return "DENY_UNKNOWN";
            }
            if (!account.active()) {
                return "DENY_INACTIVE";
            }
            if (!"north".equals(tenant)) {
                return "DENY_TENANT";
            }

            // App policy; do not use raw ROLE_ADMIN as a permission.
            String requiredGroup = switch (permission) {
                case "invoice.read" -> "north:invoice-readers";
                case "invoice.approve" -> "north:invoice-approvers";
                default -> null;
            };
            if (requiredGroup == null
                    || !account.groups().contains(requiredGroup)) {
                return "DENY_ENTITLEMENT";
            }
            return "ALLOW " + account.targetId();
        }
    }

    public static void main(String[] args) {
        TargetDirectory target = new TargetDirectory();

        Account created = target.upsert(
                "HRIS_CORP", "emp-42", "alice@corp.example.test",
                true, Set.of("north:invoice-readers", "ROLE_ADMIN"));

        System.out.println("Created: "
                + created.targetId() + " v" + created.version());

        Account duplicate = target.upsert(
                "HRIS_CORP", "emp-42", "alice@corp.example.test",
                true, Set.of("north:invoice-readers", "ROLE_ADMIN"));

        System.out.println("Duplicate event: "
                + duplicate.targetId() + " count=" + target.size()
                + " v" + duplicate.version());

        System.out.println("Read invoice: " + target.authorize(
                "HRIS_CORP", "emp-42", "north", "invoice.read"));

        System.out.println("Approve invoice: " + target.authorize(
                "HRIS_CORP", "emp-42", "north", "invoice.approve"));

        System.out.println("Other tenant: " + target.authorize(
                "HRIS_CORP", "emp-42", "south", "invoice.read"));

        Account disabled = target.upsert(
                "HRIS_CORP", "emp-42", "alice@corp.example.test",
                false, Set.of("north:invoice-readers", "ROLE_ADMIN"));

        System.out.println("Deactivated: v" + disabled.version());
        System.out.println("Existing identity: " + target.authorize(
                "HRIS_CORP", "emp-42", "north", "invoice.read"));

        Account retried = target.upsert(
                "HRIS_CORP", "emp-42", "alice@corp.example.test",
                false, Set.of("north:invoice-readers", "ROLE_ADMIN"));

        System.out.println("Retry disable: v" + retried.version());

        System.out.println("Wrong source: " + target.authorize(
                "HRIS_PARTNER", "emp-42", "north", "invoice.read"));

        target.upsert(
                "HRIS_CORP", "emp-42", "alice@corp.example.test",
                true, Set.of("north:invoice-readers"));

        System.out.println("After reactivation: " + target.authorize(
                "HRIS_CORP", "emp-42", "north", "invoice.read"));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac ScimLifecycleDemo.java
java ScimLifecycleDemo
~~~

**Exact stdout:**

~~~text
Created: usr-1 v1
Duplicate event: usr-1 count=1 v1
Read invoice: ALLOW usr-1
Approve invoice: DENY_ENTITLEMENT
Other tenant: DENY_TENANT
Deactivated: v2
Existing identity: DENY_INACTIVE
Retry disable: v2
Wrong source: DENY_UNKNOWN
After reactivation: ALLOW usr-1
~~~

### Line-by-line meaning

- The create event assigns target ID `usr-1` and version 1.
- A duplicate event does not create a second user or bump the version.
- Group `north:invoice-readers` only grants reading North invoices per policy.
- The `ROLE_ADMIN` string from the provisioning source **does not automatically become approve permission**.
- Switching to tenant South is denied.
- `active=false` causes local policy to deny immediately even though the user still exists in the repository.
- Retrying the disable event keeps version 2.
- The same `externalId` from a different source does not auto-match.
- Reactivation is a **policy-permitted event in the simulation**, and does not mean HRIS is allowed to bypass a real security suspension.

**Limitations:** **single-threaded, `HashMap`-based** example with no SCIM HTTP/JSON parser, DB transactions, optimistic locking, source event sequencing/versioning, distributed delivery, JWT verification, session invalidation, or per-user permission validation. Do not use directly to protect production endpoints. For sensitive domains, **reactivation must be approved by a security workflow**, not just a boolean from an old event.

## 25. Feeding SCIM Data into Spring UserDetails and Authorities

A Spring application can maintain its own account repository updated by SCIM. After authentication via OIDC/SAML/password, check the account:

~~~java
// Fragment inside an application's UserDetailsService,
// localAccounts is a dependency from the project's DB/repository.
@Override
public UserDetails loadUserByUsername(String linkedLocalAccountId) {
    LocalAccount account = localAccounts.find(linkedLocalAccountId);

    if (account == null) {
        throw new UsernameNotFoundException("Account is not provisioned");
    }

    if (!account.isProvisionedActive()
            || account.isLocallySuspended()) {
        throw new DisabledException("Account is not allowed to login");
    }

    return User.withUsername(account.getLocalId())
            .password("{noop}UNUSED_IN_FEDERATED_LOGIN")
            .disabled(false)
            .authorities(mapApprovedPermissions(account))
            .build();
}
~~~

**This is a Spring fragment**, not a runnable class; `LocalAccount`, `localAccounts`, and `mapApprovedPermissions` must be defined by the application. The password marker **must never be used for password-based authentication**; if the app also supports form login, isolate credential handling and use a proper `PasswordEncoder`.

**Important:** `loadUserByUsername` may only be called at login, not necessarily on every HTTP request. If a session or JWT remains live after SCIM sends `active=false`, the code above **is not enough** to revoke permissions immediately. Add account status/entitlement checks on sensitive requests or invalidate sessions/tokens.

### Authorizing by SCIM Groups

**Do not:**

~~~java
// Do not use on raw SCIM Group displayName:
new SimpleGrantedAuthority(group.getDisplayName());
~~~

**Do:** map approved group ID/source/tenant tuples to application permissions:

~~~text
(source=HRIS_CORP, targetGroup=g-101, tenant=north)
    -> ROLE_INVOICE_VIEWER

(source=HRIS_CORP, targetGroup=g-102, tenant=north)
    -> ROLE_INVOICE_APPROVER

group displayName = "ROLE_ADMIN" (not approved)
    -> No permission granted
~~~

Every domain action still requires ownership/tenant checks. Group membership from SCIM can be a **snapshot** of entitlements, not a guarantee of current permissions inside an older session.

## 26. Permissions in JWT/Claims vs. SCIM May Diverge

A user may be:

- Authenticated by the IdP with an unexpired ID Token/Access Token.
- Provisioned by SCIM in Billing, yet currently `active=false`.
- Removed from SCIM Group `finance-approvers` while an older JWT still carries `scope=invoice.approve` or a Spring session still holds old authorities.

**Successful authentication does not resolve account lifecycle.** You must define **policy precedence**:

~~~text
ALLOW request
 IF JWT/session has verified issuer/audience/time
 AND local SCIM-provisioned account is still active
 AND NOT locallySuspended
 AND current tenant membership is valid
 AND action permission is still valid
 AND resource ownership/ABAC rules pass
ELSE DENY
~~~

For pure stateless JWT apps, you may need **short token TTLs**, introspection, token revocation/denylists, or server-side account-state/version checks. For browser apps, you may need Spring Session registry invalidation triggered by SCIM disable events. **SCIM does not automatically invoke Spring's `LogoutHandler` on every device.**

**Never copy SCIM `active=true` into a JWT and trust it blindly until token expiry** if revocation must happen faster than the token lifetime.

## 27. SCIM Client Credentials, Scopes, and Operational Permissions

A SCIM connector usually runs under a **machine identity**. When using OAuth2, it may obtain tokens via `client_credentials`, but you must keep two flows separate:

~~~text
SCIM provisioning:
  IAM client -> AS (machine token) -> SCIM Provider API
  Token audience: scim-provisioning-api
  Token scopes: scim.read/scim.write (custom example)

User login:
  Browser -> OIDC OP -> Spring application
  ID Token subject = user identity
  Access token for business API != SCIM machine token
~~~

**Never send a SCIM client write token to a browser**, because it can create/disable users. Never let a business API accept a provisioning token as a user token just because it shares the same issuer or has a valid JWT signature. **Audience and token type** must be kept distinct.

Inside the SCIM application, check permissions per operation:

- Client `HRIS_CORP` may create/update Users from source `HRIS_CORP`, not all users.
- Client `GroupManager` may only modify groups within its assigned scope.
- Read-only audit clients have no `PATCH`/`DELETE`.
- Partner clients cannot provision users into tenant `north` outside contract.
- Token `issuer`, `exp`, `aud`, `client_id`, and scopes must be verified, with resource-level policies still enforced.
- Even with write scope, **`DELETE`/activating admin accounts** may require special policy.

**SCIM does not mandate OAuth2.** If the target uses mTLS or another authentication scheme advertised in discovery, implement that accordingly—never force every vendor onto one grant type.

## 28. Data Minimization, Privacy, and Retention

SCIM payloads can contain personal data: names, email addresses, phone numbers, department, manager, employee number, photos, and custom extension attributes.

**Sync only the attributes the target genuinely needs**:

1. Define the purpose and data owner for each attribute.
2. For an app that only needs display name and ID, never send salary, date of birth, or the entire HR record.
3. Use HTTPS, encryption at rest, and restricted read access on the SCIM repository.
4. Avoid logging SCIM request/response bodies in gateways/APM; redact tokens and PII.
5. Do not put email/employee number into high-cardinality metric labels.
6. Set retention rules upon offboarding and handle legal hold/anonymization per policy.
7. Define what `DELETE` means in the target system; never promise erasure of every log/backup.
8. In multi-tenant SaaS, ensure ID filters/queries cannot leak another tenant's data.
9. Audit schema extensions before syncing custom PII.
10. Keep an audit trail of who modified which attribute, without storing raw secrets in audit logs.
11. Self-service user updates must not overwrite authoritative sources without a merge process.
12. Test data removal and access revocation on a canary user.

**Privacy and security are two different questions:** protecting the SCIM token does not give the target permission to store all HR fields indefinitely.

## 29. Interoperability Across Vendors

Even when advertising "SCIM 2.0 support", products differ in:

| Aspect | What to verify |
| --- | --- |
| Base URL | `/scim/v2` or vendor-specific path |
| Resource types | Which Users, Groups, and extensions? |
| Create | Required fields and `userName` uniqueness |
| Update | Is PATCH supported, or only PUT? |
| Group membership | PATCH add/remove, nested groups, size limits |
| Filtering | Support for `eq`, `externalId`, which attributes? |
| Pagination | Page size, `startIndex`, `count`, limits |
| ETag | Are response versions and `If-Match` supported? |
| Bulk | Enabled or not, limits and partial failures |
| Deactivate | Does `active=false` actually block login? |
| Delete | Hard delete, soft delete, or tombstone? |
| Schema extensions | Enterprise User and custom attributes |
| Authentication | OAuth bearer, mTLS, or vendor-specific scheme |
| Error model | 409 uniqueness, 412 precondition, 401/403, and `scimType` |
| Rate limits | 429/`Retry-After` and vendor limits |
| Tenant scoping | Per-tenant token/base URL, cross-tenant ID isolation |
| Event ordering | Can older updates overwrite newer state? |
| Account linking | Source-scoped `externalId`; email not unique |
| Consistency | Time from PATCH success to app permission change |
| Session revocation | Does deactivate invalidate user sessions/tokens? |

**Run conformance/integration tests against the real provider** and read `ServiceProviderConfig`. A MockMvc test checking only that a controller returns 201 proves neither ID stability, atomic PATCH, nor that deactivate blocks login.

## 30. Common Errors and Remedies

| Symptom | Possible cause | Remedy |
| --- | --- | --- |
| POST create user returns 409 | Duplicate `userName` or uniqueness violation | Reconcile identity; never auto-randomize `userName` |
| POST times out, retry creates 2 accounts | Missing idempotent identity mapping | Query target `id`/`externalId` before retrying |
| User rename spawns a new user | Used email/`userName` as primary key | Use source `externalId` + stable SCIM `id` |
| PATCH returns 501 | Server does not support PATCH | Check discovery; use PUT per contract if needed |
| PATCH body rejected | Used JSON Patch `ops` instead of SCIM `Operations` | Use `PatchOp` schema and standard paths |
| PUT wipes groups/custom attrs | Sent representation missing fields | Use PATCH or full read-modify-write per schema |
| `If-Match` returns 412 | Resource version changed | GET, reconcile, and update safely |
| GET filter returns 0 despite user existing | Unsupported filter/wrong tenant scope | Check `ServiceProviderConfig` and access rights |
| Group update succeeds yet app returns 403 | Roles not mapped/refreshed | Check entitlement mapping/sessions/cache |
| `active=false` yet user still calls API | Old JWT/session and missing account-state check | Revoke/epoch/online checks |
| SCIM user `active=true` yet SSO login fails | Unverified identity link or IdP policy block | Verify subject/issuer; never auto-link email |
| User left tenant yet still sees data | Business authorization lacks tenant checks | Enforce object ownership in the app |
| Offboarded user re-enabled automatically | Old event overwrote newer disable | Enforce source event ordering/versioning |
| Group named `admins` becomes `ROLE_ADMIN` | Raw group mapping | Use allowlist and approval |
| Rate limit 429 backs up queue | No backoff/`Retry-After` | Retry with jitter, monitor SLA |
| Bulk group changes exceed limits | Bulk unsupported or payload too large | Chunk under control with per-operation status |
| SCIM bearer token shipped to frontend | Flawed credential design | Machine-only secret store, rotate credentials |
| SCIM PATCH blocked with 403 | Scope/client/tenant policy disallows it | Grant least-privilege permissions per target |
| SCIM client accepts arbitrary target URL | SSRF/token exfiltration risk | Fixed endpoint allowlist |
| App disabled user, rehire restores wrong person | Unproven identity linking | Approved rehire/merge workflow |
| Spring login auto-grants role when SCIM lags | Overly permissive JIT fallback | Fail closed / provisioning pending |

**Never fix issues by** disabling TLS, skipping authorization checks, minting default admins, bypassing disabled accounts, or widening SCIM write scope system-wide.

## 31. End-to-End Test Matrix

| # | Scenario | Expected |
| --- | --- | --- |
| 01 | Valid POST User, not yet existing | 201, returns stable provider `id` |
| 02 | Duplicate create event | No duplicate user created |
| 03 | POST duplicate `userName` | 409 uniqueness per RFC/contract |
| 04 | Same `externalId` from two provisioning domains | Accounts not auto-merged |
| 05 | `userName`/email changed | Target `id` and identity link preserved |
| 06 | Valid `active=false` PATCH | Target deactivated per policy |
| 07 | Disabled user attempts OIDC login | Backend rejects despite valid token |
| 08 | User logged in prior to disable | Session/token revoked or blocked by online check within SLA |
| 09 | Stale `active=true` event arrives after disable | Does not auto-reenable |
| 10 | User has `locallySuspended=true`, SCIM `active=true` | Still denied per local security policy |
| 11 | PATCH unsupported by server | Client avoids sending or falls back properly |
| 12 | Multi-op PATCH where one op fails | Resource retains prior state (atomic) |
| 13 | PUT missing custom fields | Data-loss risk detected |
| 14 | `GET /Users/{id}` | Correct resource for current ID/mapping |
| 15 | `ListResponse` with `startIndex=1` | Pagination neither drops nor duplicates users |
| 16 | `externalId` filter unsupported | Client detects and avoids creating duplicates |
| 17 | Stale `ETag`/`If-Match` version | 412, reconcile before retry |
| 18 | Valid Group add member | Target membership updated |
| 19 | Group remove member | Permissions revoked within SLA |
| 20 | Nested Group unsupported by provider | Does not fabricate group expansion |
| 21 | Read-only client calls PATCH | 403 |
| 22 | Tenant A client accesses Tenant B User | 403/tenant denial |
| 23 | SCIM token valid signature, wrong audience | 401 |
| 24 | Expired SCIM bearer token | 401 |
| 25 | Client secret/mTLS certificate rotation | Operates cleanly per runbook |
| 26 | Client sends unknown schema attribute | Validated/rejected per contract |
| 27 | Client sends read-only `id` on create | Server rejects or ignores client ID |
| 28 | Matching email, different subject | No account takeover |
| 29 | OIDC login before SCIM provisioning | Fails closed or controlled JIT |
| 30 | User lacks local identity link | No email-based auto-merge |
| 31 | Group `displayName=ROLE_ADMIN` | Does not auto-grant admin |
| 32 | Wrong-tenant resource request | Domain denies even if user/group exists |
| 33 | SCIM service outage | Retry/DLQ/reconciliation, alerts fire |
| 34 | 429 rate limit | Honors backoff/`Retry-After` |
| 35 | Mover events arrive out of order | Desired state/versioning controls outcome |
| 36 | Delete User under legal hold | Does not violate retention policy |
| 37 | Partial multi-target provisioning | Tracks per-target failures; never reports global success |
| 38 | Bulk unsupported | Client uses per-resource operations |
| 39 | SCIM logs would contain raw PII/tokens | Redaction and retention controls work |
| 40 | Disable 1 account across 10 targets | Reports 10 distinct outcomes and remediates failed targets |
| 41 | Rehire with same email, different identity | Awaits linking proof/approval |
| 42 | Role changed during Spring session | Staleness guard/session revocation triggers |
| 43 | Signed JWT for inactive user | Account-state policy denies |
| 44 | Concurrent PATCHes on one user | `ETag`/versioning prevents lost updates |
| 45 | Tenant-level provisioner token revoked | Can no longer modify target resources |

**A system only PASSES when both provisioning state and actual login/permission behavior are verified.** A 200/204 response from the SCIM API **is not enough** to prove the user is blocked on every existing session.

## 32. End-to-End Implementation Runbook to Production

### Phase A — Analysis and Responsibility Split

1. Identify authoritative sources, the provisioning engine, target SCIM servers, and Spring apps.
2. Specify Users/Groups, enterprise extensions, and attribute ownership.
3. Choose immutable external identity keys and mappings per source/tenant/target.
4. Define joiner–mover–leaver lifecycle and deactivation semantics.
5. Design group→role/entitlement mappings with app owners.
6. Finalize latency requirements from leave event to **blocked login** and **existing sessions revoked**.
7. Define account-linking workflows, JIT policy, and rehire handling.

### Phase B — SCIM Connectivity Setup

1. Register endpoints, mTLS or OAuth2 machine clients, scopes, and resource ownership.
2. Inspect `/ServiceProviderConfig`, `/ResourceTypes`, and `/Schemas` on the target.
3. Test POST, GET, supported PATCH/PUT, Groups, and DELETE/deactivate with canary users.
4. Verify filter/pagination/ETag/bulk capabilities before enabling the connector.
5. Set up secret rotation, monitoring, TLS trust, and network ACLs.
6. Restrict write clients by tenant and operation.
7. Log audit correlation IDs without raw payloads/credentials.

### Phase C — Synchronization and Reconciliation

1. Run a canary batch and verify target IDs are stored in the mapping table.
2. Test duplicate events, POST timeouts, 409 uniqueness, and 412 version conflicts.
3. Verify event versioning/tombstones so departed accounts cannot resurrect.
4. Use retries with exponential backoff + jitter and bounded queues.
5. Add dead-letter triage with an owner; never retry indefinitely.
6. Run reconciliation between desired state and actual target state.
7. Across 10 targets, record each target's result individually—never report "sync succeeded" when only 9 succeeded.

### Phase D — Spring Security Integration

1. Verify logins via the IdP for `issuer`/`subject`/`audience`.
2. Link external subjects to SCIM-provisioned local accounts with proper proof.
3. Check account `active` and `locallySuspended`; never auto-enable on SCIM `active=true` against security policy.
4. Map groups through approved app policies and enforce tenant/resource authorization.
5. Integrate session/token revocation on SCIM deactivation.
6. Keep `/scim/v2/**` machine-only; never give browsers provisioning tokens.
7. Test valid unexpired signed tokens for deactivated accounts.
8. Never use JIT as a backdoor around approvals or the SCIM lifecycle.

### Phase E — Rollout and Operations

1. Canary one tenant, one app, and one target group before rolling out broadly.
2. Monitor provisioning latency SLAs, partial failures, and 401/403 login anomalies.
3. Verify group-removal and deactivation behavior across web sessions and API tokens.
4. Exercise provider outages, retries, reconciliation, and duplicate detection.
5. Audit retention, data minimization, and legal holds.
6. Configure alerts for deactivation failures and P0 security exposures.
7. Maintain a rollback runbook that does not re-enable users against policy.
8. Review schema/mapping changes whenever vendors upgrade SCIM versions.

## 33. Observability and Auditing

The following metrics are suggested for implementation by the provisioning engine/SCIM provider—**they are not automatically emitted by Spring Security**:

| Metric | Interpretation |
| --- | --- |
| `scim_provision_requests_total` | Requests by target/operation/status |
| `scim_provision_success_total` | Operations confirmed successful by target |
| `scim_provision_failures_total` | 4xx/5xx/timeout errors by reason |
| `scim_provision_latency_seconds` | API call/response latency |
| `identity_lifecycle_end_to_end_delay` | Time from HR event until target state takes effect |
| `scim_deactivation_backlog` | Users pending deactivation across targets |
| `scim_reconcile_drift_total` | Drift between desired vs. actual state |
| `scim_duplicate_identity_conflicts` | `externalId`/`userName`/tenant collisions |
| `scim_group_membership_changes` | Add/remove members; avoid raw PII labels |
| `scim_412_version_conflicts` | Concurrency conflicts requiring handling |
| `scim_429_rate_limits` | Rate limits requiring backoff |
| `scim_dlq_depth` | Unprocessable events |
| `app_inactive_account_access_denied` | Access denials after deprovisioning |
| `app_stale_session_revocation_delay` | Delay to revoke local sessions/tokens |

**Never use raw emails, subjects, `externalId`s, tokens, or PII-bearing group memberships as metric labels.** Use controlled internal hashes/correlation IDs for auditing, restrict log access, and enforce retention.

**High-priority alerts:** `active=false` in IAM while sensitive requests are still accepted by Spring; group removed yet user retains approve privileges; provisioning client write token exposed; tenant connector modifying out-of-scope accounts; retry queue missing offboarding deadlines.

## 34. Self-Assessment Questions

**1. Does SCIM replace Spring Security for authenticating users?**  
No. SCIM manages accounts/groups; Spring Security enforces authentication and authorization as configured, using the synced data.

**2. Does adding `spring-boot-starter-security` immediately provide SCIM `/Users` and `/Groups`?**  
No. You need a dedicated SCIM service/provider implementation or supporting library/vendor implementing RFC semantics.

**3. How do `externalId` and `id` differ?**  
SCIM `id` is assigned by the provider and stable; `externalId` is supplied by the client and scoped to the provisioning domain.

**4. Should email be used to check whether a user is already provisioned?**  
Never as the sole identity key. Use source/`externalId`/target `id` and verified `issuer+subject` mappings.

**5. If a SCIM group is named `ROLE_ADMIN`, must Spring grant admin?**  
No. The application must map through an allowlist by source, tenant, role owner, and account status.

**6. Is PATCH mandatory on every SCIM 2.0 server?**  
No. RFC 7644 defines PATCH as an optional server capability; check `ServiceProviderConfig`.

**7. Is SCIM PATCH identical to RFC 6902 JSON Patch?**  
No. It uses `PatchOp` `schemas` and `Operations` with SCIM attribute paths and semantics.

**8. Can PUT create a brand-new user?**  
Per RFC 7644, PUT must not be used to create new resources; use POST.

**9. When POST times out, should you immediately loop POST retries?**  
Never blindly. Reconcile whether the account was already created to avoid duplicates.

**10. Does `active=false` automatically destroy an existing Spring `SecurityContext`?**  
No. You need session/token revocation or per-request account-state checks.

**11. Is it contradictory if a SCIM user is `active` yet OIDC login fails?**  
No. Provisioning and authentication are separate planes; IdP policy or account mapping can still reject.

**12. Why is reconciliation necessary?**  
Because multiple targets update asynchronously with retries, errors, out-of-order events, and drift.

**13. What must happen when group membership is removed?**  
Update SCIM Groups, remove target entitlements, and verify existing sessions/authorization freshness.

**14. Can a SCIM API use OAuth2 `client_credentials`?**  
Yes, if the provider/AS supports it; however, the RFC does not mandate OAuth2 exclusively. A SCIM client token is a machine credential, not a user login token.

**15. When should you build a SCIM service with Spring Boot?**  
When the team needs a dedicated Service Provider/API and is prepared to implement RFC 7643/7644, persistence, entitlements, error handling, tenant isolation, and conformance tests. Spring Security only secures the API.

## 35. Production Checklist

- [ ] Clearly separate **SCIM provisioning**, **SSO authentication**, and **application authorization**.
- [ ] A dedicated IAM/IGA/provisioning system owns joiner–mover–leaver, retries, DLQ, and reconciliation.
- [ ] Target SCIM Service Provider supports Users/Groups and schemas verified via discovery.
- [ ] Do not assume PATCH/filter/sort/bulk/ETag are always available; inspect `ServiceProviderConfig`.
- [ ] Maintain stable **`(source, externalId, target)` → SCIM `id`** mappings; never use email as sole key.
- [ ] Handle POST duplicates/timeouts safely with idempotency and identity conflict resolution.
- [ ] Test PUT replacement and atomic PATCH semantics.
- [ ] Reconcile PATCH Groups add/remove against actual application permissions.
- [ ] SCIM machine clients use TLS, dedicated auth, audience/scopes/tenant boundaries, and rotation.
- [ ] Backend SCIM API blocks cross-tenant edits, schema spoofing, oversized payloads, and unauthorized `DELETE`.
- [ ] Never log raw SCIM tokens, account PII, or entitlement data unnecessarily.
- [ ] Backend actively enforces `active=false`, not merely storing it in the users table.
- [ ] Locally suspended/locked state is never automatically cleared by SCIM `active=true`.
- [ ] Have a revocation plan for Spring sessions, JWT/refresh tokens, API keys, and delegated credentials.
- [ ] Group/role mapping uses an approved allowlist; never auto-grant admin from `displayName`.
- [ ] Account linking from OIDC `issuer+subject` to SCIM ID uses proof, not email.
- [ ] Login racing ahead of provisioning fails closed or uses controlled JIT.
- [ ] Concurrent updates and out-of-order lifecycle events cannot resurrect departed accounts.
- [ ] Per-target rollout, audit logs, reconciliation SLAs, and incident handling are in place.
- [ ] Conformance tests run against a real provider, not only JSON unit tests.
- [ ] Spring Security is assigned strictly authentication/authorization/API protection duties.
- [ ] Data minimization, legal retention, and privacy for SCIM attributes are approved.

## 36. Conclusion

**SCIM 2.0** is the standard communication foundation for **provisioning and synchronizing accounts/groups**, typically operated by a **dedicated IAM/IGA/provisioning system or Service Provider**. Three concepts must remain separate: **identities created/disabled via SCIM**, **users authenticated via OIDC/SAML/other mechanisms**, and **access permissions decided by the application via local account/tenant/resource policies**.

**Spring Security can protect a custom SCIM API and read provisioned account data to allow or deny login, but it is not itself a SCIM synchronization engine.** Production readiness requires stable identity mappings, schema/capability discovery, idempotency, group reconciliation, machine-client security, fail-closed handling, and revocation of local sessions/tokens. **Provisioning success is not enough; permission changes and deactivations must genuinely take effect at application runtime.**

### Official References

- IETF RFC 7642 — SCIM Definitions, Overview, Concepts, Requirements: https://www.rfc-editor.org/rfc/rfc7642
- IETF RFC 7643 — SCIM Core Schema (Users, Groups, Enterprise User, id/externalId): https://www.rfc-editor.org/rfc/rfc7643
- IETF RFC 7644 — SCIM Protocol (CRUD, PATCH, filter, pagination, ETag, error/security): https://www.rfc-editor.org/rfc/rfc7644
- Spring Security — Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — UserDetailsService: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html
- Spring Security — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — OAuth2 Resource Server Opaque Token: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- Spring Security — Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
