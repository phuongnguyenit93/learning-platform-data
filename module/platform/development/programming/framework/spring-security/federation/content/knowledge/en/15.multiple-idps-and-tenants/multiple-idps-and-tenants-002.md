# Distinguishing Multiple Providers from Multiple Application Organizations (Tenants)

> **Topic:** Spring Security – Federation. **Section:** Multiple IdPs and Tenants. This lesson clearly separates the concept of **multiple identity providers (multiple Identity Providers – IdP/OP)** from **multiple organizations sharing the same application (multi-tenant SaaS)**. The focus is on designing many-to-many relationships between tenants and IdPs, provider-selection workflows, identity verification, mapping users to tenants, and protecting data per tenant in Java 17+/Spring Security Servlet, OIDC, and SAML2.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Accurately define `tenant`, `organization`, `IdP`, `OIDC issuer`, `SAML asserting party`, `client registration`, `Relying Party Registration`, and `local account`.
2. Explain why **having three IdPs does not mean having three tenants**, and **having one IdP does not mean the application has only one tenant**.
3. Design **one-to-one, one-to-many, many-to-one, and many-to-many** relationships between tenants and IdP connections.
4. Distinguish a **customer's IdP** from the **application's own tenant**; understand that a tenant/realm in an IdP product may not match the SaaS tenant model.
5. Design connection registry tables, external-identity-to-local-account mappings, and tenant memberships without relying on email or email domains as proof.
6. Place two control layers correctly: **authentication** (the IdP issues valid evidence to the application) and **authorization/tenant isolation** (is this person allowed to view organization X's resources?).
7. Configure multiple OIDC `ClientRegistration`s and multiple SAML `RelyingPartyRegistration`s in Spring Security; distinguish them from the Resource Server API multi-tenancy model.
8. Prevent **issuer confusion, tenant spoofing, login CSRF, account takeover, cross-tenant data access, and BOLA/IDOR**.
9. Test logging in across multiple IdPs, entering multiple tenants, switching tenants, revoking membership, sessions, and logout.
10. Choose safe designs for onboarding, configuration management, certificate/JWKS rotation, auditing, and day-to-day operations.

**Core principle:** **The IdP answers "who just authenticated this user and how is it proven?"**; **the tenant answers "which organization owns the data and business context the user intends to access?"**. These two questions may be related, but **must never be collapsed into one**.

## 2. Terminology: One Word "Tenant", Multiple Meanings

| Term | Meaning in the System | Example | Is It Synonymous with Another IdP/Tenant? |
| --- | --- | --- | --- |
| **Application tenant** | Organization/customer owning a data space, settings, and permissions in the SaaS | `org-red`, `org-blue` | Not necessarily 1:1 with an IdP |
| **Identity provider tenant** | Administrative domain/directory object in the IdP product; may be a directory, realm, domain, or tenant identifier | `realm=staff`, customer directory | Can serve multiple application tenants, or one app tenant can have multiple IdP directories |
| **Identity Provider (IdP)** | System that authenticates identities and issues SAML Assertions | Centralized SAML engine, partner IdP | Not automatically an application tenant |
| **OpenID Provider (OP)** | Issuer that issues OIDC ID Tokens to a Relying Party | `https://login.example.net/realms/staff` | One issuer can manage multiple groups/organizations |
| **OIDC `issuer`** | Identifier of the ID Token source, usually an HTTPS URI that must match exactly | `iss=https://login.example.net/realms/staff` | Not a SaaS data `tenantId` |
| **SAML IdP `entityID`** | Logical Asserting Party identifier in metadata/assertions | `https://sso.partner.example/idp` | Not a SaaS tenant name |
| **OIDC `ClientRegistration`** | Configuration for client ID, secret/PKCE, issuer, callback, scopes; selected by `registrationId` | `staff-oidc` | One IdP can have multiple client registrations |
| **SAML `RelyingPartyRegistration`** | Specific link between SP and IdP: `registrationId`, entityID, ACS, certificates | `partner-saml` | One IdP can have multiple RP registrations; each registration is not automatically an application tenant |
| **External identity** | User identified by verified issuer and subject | `(iss,sub)` or stable SAML NameID | Does not itself determine tenant membership |
| **Local account** | Account ID managed by the application | `accountId=8a...` | Can link multiple external identities |
| **Tenant membership** | Application relationship `(localAccountId, tenantId, role/status)` | User has `REPORT_VIEW` in `org-red` | Grants business permissions; distinct from successful authentication |
| **Authorization context** | Currently selected tenant, actor, and data/action scope | `activeTenant=org-red` | Must be checked against membership on every required decision |

**Examples of easily confused names:** a Microsoft Entra "tenant", a Keycloak "realm", and a "tenant" in a CRM application can all look like an organization. However, they live at **different administrative layers**. You can map them 1:1 under a deployment contract, but that is a **specific configuration rule**, not a law of the protocol.

### 2.1. What Is Multi-IdP (Multiple Identity Providers)?

An application accepts login through multiple identity systems, for example:

- Employees use the company's OIDC OP.
- Contractors use a partner's SAML IdP.
- Customers use another OIDC OP.
- Users are broker-authenticated from an upstream IdP and receive assertions/tokens via a centralized issuer.

The main technical problem is **selecting the right registration**, validating issuer/keys/signature/token/response, and mapping the verified external subject to a local user. The application might **contain only one organization** while accepting all three IdPs.

### 2.2. What Is Multi-Tenant?

A SaaS application serves multiple organizations on a shared product/backend (with either a shared database or separated databases). Each tenant has its own data, users, permissions, limits, settings, and organizational lifecycle.

The main problem is **isolating data and permissions**, not just choosing where to log in. One OP can authenticate users for **every tenant** in the SaaS, yet the application must still verify membership, resource ownership, and authorization on every request.

### 2.3. Never Treat the Two Concepts as Variants of Each Other

```text
                IDENTITY PLANE
        +-------------------------------+
        | OP A (OIDC) | IdP B (SAML)    |
        | OP C (OIDC) | Broker D        |
        +----------+--------------------+
                   |
                   | Verified ID Token / Assertion / Ticket
                   | for RP/SP
                   v
        +-------------------------------+
        | Application Authentication     |
        | External identity -> accountId |
        +-------------------------------+
                   |
                   | Policy / membership
                   v
                TENANCY PLANE
        +-------------------------------+
        | Tenant RED  | Tenant BLUE      |
        | Tenant GOLD | Tenant GREEN     |
        +-------------------------------+
                   |
                   | tenant + object authorization
                   v
        +-------------------------------+
        | Data / Reports / Orders / APIs |
        +-------------------------------+
```

The **Identity plane** concerns trust in identity. The **Tenancy plane** concerns data ownership and business policy. There is an intersection between the two domains: a tenant **may** restrict which IdPs its members are allowed to use, but that restriction still does not replace checking membership.

## 3. Four Mapping Patterns and Concrete Examples

| Pattern | Relationships | Valid Scenario | What Must Not Be Inferred |
| --- | --- | --- | --- |
| **1 tenant – 1 IdP** | `org-red ↔ IdP Red` | Customer uses their own enterprise IdP | IdP Red cannot have users in another tenant |
| **1 tenant – many IdPs** | `org-red ↔ Staff OIDC` and `Partner SAML` | Employees and suppliers share one workspace | Two users from two IdPs with the same email are the same person |
| **Many tenants – 1 IdP** | `org-red`, `org-blue` both use `Corporate OIDC` | A conglomerate runs multiple subsidiaries/project groups | A Corporate OIDC user can read every tenant |
| **Many tenants – many IdPs** | `org-red ↔ Corporate OIDC + Partner SAML`; `org-blue ↔ Corporate OIDC + External OIDC` | Multi-org B2B SaaS with partner networks | An issuer equals a `tenantId` or a role applies system-wide |

**1 tenant – many IdPs pattern:** User Red A comes from Corporate OIDC, User Red B comes from Partner SAML. Both can be granted Red report permissions if they have valid memberships. Do not turn Partner IdP into a new tenant simply because it is a second provider.

**Many tenants – 1 IdP pattern:** A user has one OIDC account from the Corporate OP and is authorized to access Red and Blue. Each time they switch between Red and Blue, the session may retain the same principal, but queries and actions must filter by the corresponding `tenantId`. Do not create an artificial second OIDC issuer just to represent Blue.

**Many-to-many pattern:** A person from Corporate OP can be in Red and Blue, while a partner from Partner SAML is only in Red. Tenant Gold uses its own Gold OP. Changing Red membership must not accidentally alter authentication or permissions in Blue/Gold.

### 3.1. Illustrative Connection Matrix

| Application Tenant | Corporate OIDC (`corp-oidc`) | Partner SAML (`partner-saml`) | Gold OIDC (`gold-oidc`) |
| --- | --- | --- | --- |
| `org-red` | Allowed as login source | Allowed as login source | Not allowed |
| `org-blue` | Allowed as login source | Not allowed | Not allowed |
| `org-gold` | Not allowed | Not allowed | Allowed as login source |

This table is only a **tenant → authentication connection policy**. It is **not** a per-user permission table. To read Red reports, the application also needs membership records:

```text
localAccountId=acct-100
externalIdentity=(corp-oidc, issuer=https://login.corp.example/realms/staff, sub=em-77)
memberships:
  (acct-100, org-red, REPORT_READ, ACTIVE)
  (acct-100, org-blue, REPORT_VIEW, ACTIVE)

localAccountId=acct-200
externalIdentity=(partner-saml, issuer=https://sso.partner.example/entity, stableNameID=p-42)
memberships:
  (acct-200, org-red, REPORT_READ, ACTIVE)
```

When `acct-100` accesses `org-gold`, **it must be denied** even though the user successfully logged in at Corporate OIDC. Neither a `Corporate → Gold` connection nor a specific membership for that user exists.

## 4. Identifiers That Must Usually Be Managed Separately

Name them clearly in schemas, code, and logs:

```text
tenantId                     = "org-red"
connectionId                 = "corp-oidc-for-red"
protocol                     = "OIDC"
clientRegistrationId         = "corp-oidc"
providerId                   = "corporate-op"
issuer                       = "https://login.corp.example/realms/staff"
externalSubject              = "em-77"
localAccountId               = "acct-100"
membershipRole               = "REPORT_READ"
currentTenant                = "org-red"
```

In SAML:

```text
tenantId                     = "org-red"
connectionId                 = "partner-saml-for-red"
protocol                     = "SAML2"
relyingPartyRegistrationId   = "partner-saml"
idpEntityId                  = "https://sso.partner.example/entity"
spEntityId                   = "https://app.example.org/saml2/service-provider-metadata/partner-saml"
assertionConsumerService     = "https://app.example.org/login/saml2/sso/partner-saml"
externalSubject              = stable NameID + qualifier per contract
localAccountId               = "acct-200"
```

- `tenantId` is the **business namespace**. Even if a user switches IdPs, the tenant and organizational data can remain intact.
- `clientRegistrationId`/`relyingPartyRegistrationId` is the **framework configuration lookup key**; depending on design, it can be shared across multiple tenants or created per tenant.
- `issuer`/IdP `entityID` is the **identifier of the evidence issuer**; it is verified against trusted IdP configuration and is not a `tenantId`.
- `sub` in OIDC is stable **within the scope of an issuer**; with pairwise subject identifiers, the same person can receive different `sub` values across clients/sector identifiers. Never auto-merge.
- SAML `NameID` has multiple formats; `transient` is unsuitable as a long-term internal key, while `persistent`/immutable attributes must be evaluated per contract; NameID does not automatically equal email.
- `localAccountId` should be an application-issued ID; do not use an email address, displayName, user-supplied tenant slug, or raw `sub` as a system-wide primary key.
- `membershipRole` is a permission within **a specific tenant**, not automatically a global admin role.

### 4.1. Do Not Equate OIDC Token Audience with Application Tenant

In OIDC login, the ID Token `aud` must contain the **RP's OAuth `client_id`**; it is not the SaaS `tenantId`. A token valid for client `web-portal` can be used to **authenticate the user** before the application determines whether the user belongs to Red or Blue. Do not change `aud` to `org-red` just because the user selected tenant Red.

In SAML, `AudienceRestriction` must match the registered **SP entityID**. If the same SP serves multiple tenants, you can adopt a strategy with one shared SP entityID or multiple SP registrations with per-tenant entityIDs. Either way, audience only proves which RP/SP the assertion is meant for; **it does not by itself prove permission to read an organization's resources**.

### 4.2. Why Email Domains Do Not Safely Identify a Tenant

A person with `user@red.example` may be an employee, contractor, guest using an alias, or someone with a reassigned mailbox; emails can change, be unverified, or be issued by another IdP. One organization can use multiple email domains, and one domain can serve multiple units. **Never use `email.endsWith("@red.example")` as proof of membership**, never auto-link accounts across two IdPs that share an email, and never use `preferred_username` as an identity key.

An email domain can assist **home realm discovery** as a UX hint: "You may want to sign in via Corporate." After login, you must still verify issuer+subject and query membership on the server.

## 5. Flow When a User Logs In from a Specific Tenant

One SaaS pattern supports paths such as:

```text
https://app.example.org/t/org-red/login
https://app.example.org/t/org-blue/login
```

Sequence:

```text
[Browser GET /t/org-red/login]
          |
          v
[Server resolves org-red from app registry]
          |
          v
[Reads ACTIVE authentication connections for Red]
          |
          v
[Displays "Corporate OIDC" / "Partner SAML" per policy]
          |
          v
[User selects 1 approved connection]
          |
          v
[Spring initiates OIDC / SAML by registrationId]
          |    state/nonce/PKCE or SAML Request ID/RelayState
          |    binds tenant-intent and anti-CSRF to session
          v
[Browser is redirected to the approved IdP]
          |
          v
[IdP authenticates and sends evidence to RP/SP callback]
          |
          v
[Spring verifies issuer/signature/audience/time/correlation]
          |
          v
[Server resolves external identity -> localAccountId]
          |
          v
[Server checks connection for Red + ACTIVE membership in Red]
          |
       ALLOWED?
       /      \
      NO       YES
      |         |
      v         v
 [403/deny] [Set activeTenant=Red in server session]
                |
                v
        [Authorize each object under Red]
```

**The `tenantId` in the initial URL is only a requested context, not a granted authorization result.** Never trust `tenantId` merely because it appeared in a client-called URL. After the callback, the server must reconcile the tenant-intent protected by login state/request repository against current membership. If missing or no longer valid, do not create a tenant-scoped session or grant access to Red.

### 5.1. Home Realm Discovery Is Not Authorization

The application may look up an IdP based on:

- A tenant slug entered on the login page.
- An organization code provided by the customer.
- An email domain typed by the user.
- Pre-rendered login buttons.
- Hostname/subdomain such as `red.app.example.org`.

These inputs **only help select an IdP** before a verified identity exists. They can be spoofed or wrong. Never let entering `red` in the URL automatically create Red membership. If the chosen IdP source is not in the allowed list for Red, reject before redirecting.

**Subdomain/Host must be trusted:** Reverse proxies must reject unknown Hosts, strip client-supplied `X-Forwarded-Host`, and pass only controlled values. Never use raw client-chosen HTTP headers to construct an issuer/JWKS URL, ACS URL, or database tenant. For vanity domains, map using a table with verified domain ownership.

### 5.2. Never Take the Tenant from an Unverified `state`/`RelayState`

OIDC uses `state` to prevent login CSRF and bind the response to the request; `nonce` binds the ID Token to the authorization request where applicable. SAML uses `AuthnRequest ID`, `InResponseTo`, `RelayState`, and session/request repository per profile. If the application needs to remember tenant-intent across a redirect, store it in **a server-side session or a signed/protected correlation store** bound to the request. Do not use `?tenant=org-red` on the callback or raw `RelayState` as the final answer for which tenant the user has been authorized into.

If a user opens two login tabs concurrently for Red and Blue, ensure correlation isolates each flow. Do not store a global `currentTenantPending` variable where tab B's later callback overwrites tab A.

### 5.3. IdP-Initiated SAML and "Not Knowing Which Tenant the User Started From"

In **SP-initiated SAML SSO**, Spring has request registration and correlation details; tenant-intent can be protected within the flow. In **IdP-initiated (unsolicited) SAML SSO**, there is no initial `AuthnRequest`, so the SP needs an explicit policy: is unsolicited SSO allowed, and how are the RP registration, issuer source, tenant, account, and membership resolved?

**Never unconditionally infer the tenant from the issuer** if the IdP is shared across multiple organizations. You can prompt the user to select a tenant **after** authentication, or require SP-initiated flows for sensitive tenant areas. Never auto-map to the first tenant found or an admin tenant simply because the SAML response came from a trusted IdP.

## 6. One IdP Serving Multiple Tenants: The Main Issue Is Post-Login Permissions

For example, Corporate OIDC has issuer `https://login.corp.example/realms/staff`. Thousands of employees from it can enter Red, Blue, or both. Spring verifies the ID Token from a trusted issuer. Next, the application must check:

1. The user's external key is `(issuer,sub)`; which `localAccountId` is it linked to?
2. Is the account `ACTIVE` or locked?
3. Does tenant Red exist and is it `ACTIVE`?
4. Does the user have an ACTIVE `membership(accountId,Red)`?
5. Does this person hold the required role/permission inside Red?
6. Does resource `report-123` actually belong to Red?
7. Are additional policies—such as owner, department, approval, MFA, time—satisfied?

If the user is later added to Blue, **you do not need to mint a second OIDC issuer** just to express the new membership. Update the membership record. If the user is removed from Red, authentication via the Corporate issuer remains valid for Blue, while Red permissions must be revoked. Do not revoke all permissions in remaining tenants unless required.

### 6.1. An IdP `groups` Claim Is Not Automatically a SaaS Membership

An IdP may emit groups like `staff`, `finance`, `partner-admin`. These names only have meaning relative to the source issuer/tenant/directory. If policy maps groups into tenant memberships or roles, maintain an explicit table:

```text
(provider/issuer, externalGroupId, tenantId) -> permissionSet

(corp-oidc, "grp-red-reader", org-red)  -> REPORT_READ
(corp-oidc, "grp-blue-reader", org-blue)-> REPORT_READ
(partner-saml, "grp-red-ext", org-red)   -> REPORT_READ_LIMITED
(other-idp, "Admin", any)               -> DENY unless approved
```

If an IdP group is renamed, never auto-grant permissions to any group containing `admin` or matching `endsWith("read")`. For sensitive permissions, you may need an authorization source **controlled by the application/org admin** outside IdP group memberships.

## 7. One Tenant Using Multiple IdPs: The Main Issue Is Identity Sources

Tenant Red allows login via Corporate OIDC and Partner SAML. Both may contain people with the same email or display name; they are still **distinct external identities**. A person may intentionally link them to one local account if they pass a proper security workflow. Never merge automatically.

With OIDC, the ID Token must verify `iss`, `aud`, signature, `exp`, and authorization flow `nonce`/state; the stable identifier within the issuer scope is `iss + sub`. With SAML, you need the IdP issuer, signing certificate, `AudienceRestriction` for the SP entityID, `Recipient`/`Destination` for the ACS, `InResponseTo`, clock skew, and replay protection.

**Email collision scenario:**

```text
OIDC Corporate:
  iss = https://login.corp.example/realms/staff
  sub = emp-77
  email = lan@example.org

SAML Partner:
  IdP entityID = https://sso.partner.example/entity
  persistent NameID = partner-1007
  mail = lan@example.org

Application:
  ExternalKey A != ExternalKey B
  => DO NOT auto-link to the same local account.
```

If account linking is permitted, the user must prove control over both the existing account and the new external identity, with step-up/approval for high-risk cases, auditing, and unique constraints. Email (even with `email_verified=true` from an OP) is a contact claim, **not a credential proving ownership of a local account**.

### 7.1. Should You Create One Client Registration per Tenant?

**There is no single answer; the decision depends on trust boundaries and operations.**

- **One shared registration for multiple tenants:** Reasonable when sharing the same issuer, `client_id`/SP entityID, SSO policies, callbacks, and key set; tenant data is separated **after login**. Fewer configs, but demands strict membership/tenant isolation.
- **One registration per tenant:** Reasonable when each customer needs its own client ID, redirect URI/ACS, SP metadata, SP signing certificate, distinct logout, separate IdP policies, or tenant self-managed federation. Increases registration count and lifecycle overhead.
- **One issuer with multiple client IDs:** Multiple OIDC `ClientRegistration`s can point to the same `issuer-uri` with different client_id/secret/redirect_uri values. Do not count registrations and treat them as the number of IdPs or tenants.
- **One SAML IdP with multiple SP registrations:** Can share the same `asserting party entityID` while varying SP `entityID`/ACS per tenant, especially when signing or audience requirements differ.

**One-to-one is an implementation choice**, not a requirement of OIDC or SAML. Explicitly record the mapping `tenantId → allowedConnectionIds → registrationId/issuer` instead of stuffing every concept into a single `provider` column.

## 8. Database/Registry Design Separating Four Layers

A typical relational schema:

```text
APPLICATION_TENANT
  tenant_id PK
  slug UNIQUE
  status
  plan
  isolation_mode

IDENTITY_PROVIDER
  provider_id PK
  protocol
  issuer_or_idp_entity_id
  metadata_source_or_discovery
  trust_config_version
  status

AUTHENTICATION_CONNECTION
  connection_id PK
  provider_id FK
  spring_registration_id
  client_id_or_sp_entity_id
  callback_or_acs
  lifecycle_status
  owner

TENANT_AUTH_CONNECTION
  tenant_id FK
  connection_id FK
  enabled
  home_realm_priority
  PRIMARY KEY (tenant_id, connection_id)

EXTERNAL_IDENTITY
  external_identity_id PK
  verified_issuer
  stable_subject
  source_qualifiers
  local_account_id FK
  UNIQUE (verified_issuer, stable_subject, relevant_qualifiers)

LOCAL_ACCOUNT
  local_account_id PK
  lifecycle_status
  display_profile

TENANT_MEMBERSHIP
  tenant_id FK
  local_account_id FK
  membership_status
  membership_role_version
  PRIMARY KEY (tenant_id, local_account_id)

TENANT_ROLE_ASSIGNMENT
  tenant_id FK
  local_account_id FK
  permission_code
  scope
  PRIMARY KEY (...)
```

**Explanation:**

- `IDENTITY_PROVIDER` describes the **source**. A branded provider can have multiple issuers/realms; the trust key should follow the **actual issuer/IdP entityID**, not just the vendor name.
- `AUTHENTICATION_CONNECTION` describes **one way the application connects** to a source. One provider can have multiple connections/registrations.
- `TENANT_AUTH_CONNECTION` is a many-to-many table specifying which connections a tenant may use. Never infer membership from this table.
- `EXTERNAL_IDENTITY` must hold the verified stable identifier; for SAML, add NameIDFormat/NameQualifier/SPNameQualifier or an immutable attribute if required by contract to avoid key collisions; for OIDC, `iss+sub` is foundational.
- `TENANT_MEMBERSHIP` is the **user–organization decision**. The same account can belong to multiple tenants with different roles.
- `TENANT_ROLE_ASSIGNMENT` should store audited, managed permissions/roles. A "global" `ROLE_ADMIN` authority may be inappropriate when administrative rights apply only to Red.
- `lifecycle_status` lets you disable an IdP connection while preserving tenant data, or suspend a tenant without deleting external identities shared across other tenants.

### 8.1. Uniqueness Rules and Security Invariants

1. `tenantId`/`accountId` are application-assigned, never taken directly from email.
2. OIDC external identity is keyed by `issuer + sub`, verified against the exact registered issuer; with pairwise subjects, never force identity matching across clients.
3. One external identity may link to only **one local account** at a time, unless the model explicitly supports multi-account with dedicated rules.
4. Every active connection may only point to an approved provider/issuer; changing issuer/cert/client_id requires change approval.
5. One user has different roles per tenant; never store a global role as a flat string applied across all tenants.
6. Check tenant status and membership status at appropriate access points; never retain stale permissions indefinitely in the session.
7. Resources must carry `tenant_id` or an equivalent storage boundary; never rely solely on UI filtering.
8. Audit records capture `actor account`, `active tenant`, and verified `connection/issuer`.

## 9. Standalone Java 17: Proving Provider ≠ Tenant

The example below models **permissions after identity has already been verified**; it does not perform OIDC/SAML, parse JWTs, or sign XML. It checks three separate conditions: the connection matches the configured issuer, the tenant permits the connection, and the external identity holds membership in that tenant.

File `ProviderVsTenantDemo.java`:

```java
import java.util.Map;
import java.util.Set;

public class ProviderVsTenantDemo {

    record Provider(String id, String issuer) { }

    record Tenant(String id, Set<String> allowedProviders) { }

    record ExternalIdentity(String issuer, String subject) { }

    static final String STAFF_ISSUER =
        "https://login.corp.example/realms/staff";
    static final String PARTNER_ISSUER =
        "https://login.partner.example/issuer";

    static final Map<String, Provider> PROVIDERS = Map.of(
        "staff", new Provider("staff", STAFF_ISSUER),
        "partner", new Provider("partner", PARTNER_ISSUER)
    );

    static final Map<String, Tenant> TENANTS = Map.of(
        "red", new Tenant("red", Set.of("staff", "partner")),
        "blue", new Tenant("blue", Set.of("staff")),
        "gold", new Tenant("gold", Set.of("partner"))
    );

    // In practice, this is authoritative server-side membership data,
    // not created from a self-asserted tenant claim from the browser.
    static final Map<ExternalIdentity, Set<String>> MEMBERSHIPS =
        Map.of(
            new ExternalIdentity(STAFF_ISSUER, "u-42"),
            Set.of("red", "blue"),
            new ExternalIdentity(PARTNER_ISSUER, "u-42"),
            Set.of("gold")
        );

    static boolean mayEnter(
            String tenantId,
            String providerId,
            ExternalIdentity identity) {

        Tenant tenant = TENANTS.get(tenantId);
        Provider provider = PROVIDERS.get(providerId);
        if (tenant == null || provider == null || identity == null) {
            return false;
        }

        boolean issuerMatches =
            provider.issuer().equals(identity.issuer());
        boolean tenantAllowsProvider =
            tenant.allowedProviders().contains(providerId);
        boolean userIsMember =
            MEMBERSHIPS.getOrDefault(identity, Set.of())
                .contains(tenantId);

        return issuerMatches && tenantAllowsProvider && userIsMember;
    }

    public static void main(String[] args) {
        ExternalIdentity staff =
            new ExternalIdentity(STAFF_ISSUER, "u-42");
        ExternalIdentity partner =
            new ExternalIdentity(PARTNER_ISSUER, "u-42");

        System.out.println("providers=" + PROVIDERS.size());
        System.out.println("tenants=" + TENANTS.size());
        System.out.println("staffRed=" +
            mayEnter("red", "staff", staff));
        System.out.println("staffBlue=" +
            mayEnter("blue", "staff", staff));
        System.out.println("staffGold=" +
            mayEnter("gold", "staff", staff));
        System.out.println("partnerGold=" +
            mayEnter("gold", "partner", partner));
        System.out.println("partnerRed=" +
            mayEnter("red", "partner", partner));
        System.out.println("sameExternalIdentity=" +
            staff.equals(partner));
        System.out.println("unknownTenant=" +
            mayEnter("unknown", "staff", staff));
    }
}
```

Compile/run with JDK 17+:

```bash
javac --release 17 ProviderVsTenantDemo.java
java ProviderVsTenantDemo
```

Deterministic stdout:

```text
providers=2
tenants=3
staffRed=true
staffBlue=true
staffGold=false
partnerGold=true
partnerRed=false
sameExternalIdentity=false
unknownTenant=false
```

**Key takeaways from the output:**

- There are **2 providers** yet **3 tenants**: two independent counts.
- The Staff identity has access to Red and Blue, even though both use the single Staff issuer.
- Partner and Staff both have `subject="u-42"`, but their issuers differ so their `ExternalIdentity` instances differ.
- Tenant Red allows the Partner provider by configuration, yet that specific partner identity **has no Red membership**, so `partnerRed=false`.
- Tenant Gold does not allow the Staff provider, so `staffGold=false`; even if a user sends `?tenant=gold`, this cannot be bypassed.

**Important limitation:** The demo assumes `ExternalIdentity` objects have already passed protocol verification in another layer. Production must look up local accounts, memberships, role-permissions, and object ownership; never accept a client-constructed `ExternalIdentity` and call `mayEnter` as a substitute for authentication. The code above intentionally uses the same `sub` value across two issuers to prove **you must never compare subject strings alone**.

## 10. Spring Security OIDC: Multiple Registrations Do Not Necessarily Mean Multiple Tenants

### 10.1. Spring Boot YAML for Multiple OpenID Providers

A Spring Boot servlet project with `spring-boot-starter-security` and `spring-boot-starter-oauth2-client` can configure two client registrations:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          staff-oidc:
            provider: corp
            client-id: portal-staff
            client-secret: ${STAFF_OIDC_CLIENT_SECRET}
            scope: openid,profile,email
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
          partner-oidc:
            provider: partner
            client-id: portal-partner
            client-secret: ${PARTNER_OIDC_CLIENT_SECRET}
            scope: openid,profile,email
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          corp:
            issuer-uri: https://login.corp.example/realms/staff
          partner:
            issuer-uri: https://login.partner.example/issuer
```

**The domains/client IDs here are illustrative configuration only.** To run, replace them with real approved OPs, keep secrets in a secret manager/environment variables, register exact HTTPS redirect URIs at each OP, and verify issuer discovery/tokens. Never hard-code client secrets in source code.

When `http.oauth2Login(...)` is enabled, typical default routes are:

- `GET /oauth2/authorization/staff-oidc`: starts login via client registration `staff-oidc`.
- `GET /oauth2/authorization/partner-oidc`: starts login via `partner-oidc`.
- `GET /login/oauth2/code/staff-oidc` or `.../partner-oidc`: callback processing the respective authorization code.

**This only proves the application has two login choices; it does not create tenants automatically.** If both Red and Blue want to use `staff-oidc`, the server can present the same link when users start from Red or Blue; tenant context must be safely stored/bound and membership verified after the callback.

### 10.2. `provider` in Spring Boot Is a Configuration Name, Not `tenantId`

In YAML, `registration.staff-oidc.provider: corp` references the `provider.corp` entry. The same `provider.corp` can be used by multiple client registrations (for example, client IDs for mobile and web apps or tenants with specific requirements). **The name `corp` is a configuration key**, whereas the OIDC `issuer-uri` is the OP's identity, `client-id` is the ID Token audience, and `tenantId` is application data.

Do not use the `registrationId` string to infer:
- Which issuer a token definitely came from without verification;
- Which tenant the user belongs to;
- Whether the user has access to `/t/org-red/**`;
- Which data the user has consented to access.

When a callback is processed, Spring Security must verify `state`, the client registration, and the ID Token (signature/issuer/audience/nonce) before the application builds tenant context from membership.

### 10.3. One Issuer, Multiple Client Registrations

For example, two registrations `red-oidc` and `blue-oidc` both point to `provider: corp` but have different client IDs per customer contracts. This is **2 client registrations**, **1 OP issuer**, and may be **2 app tenants** if the architecture defines it so, though it is not automatically 2 tenants.

With OIDC `pairwise sub`, the same human can receive different `sub` values across clients/sector IDs. When account linking is needed, use a method backed by user proof; do not infer from email or assume "same OP means same subject." The OIDC Core specification guarantees `iss+sub` as the identifier within an issuer scope and notes that pairwise identifiers depend on client/sector.

### 10.4. When One Vendor's IdP Has Multiple Issuers

One branded vendor can issue ID Tokens from different realms/directories/tenants. For instance, `https://login.example/realms/a` and `https://login.example/realms/b` are two distinct issuers in OIDC, even on the same hostname. **Issuer is case-sensitive and the path is significant**; Spring must check the exact expected `iss`, never accepting a broad namespace merely because the token was signed by a key hosted on the same domain.

Thus "multiple IdPs" sometimes means multiple issuer endpoints of the same product, and "multiple IdP tenants" does not always equal "multiple SaaS organizations."

## 11. Spring Security SAML2: Multiple Relying-Party Registrations

With `spring-security-saml2-service-provider`, multiple SAML connections can be configured under `spring.security.saml2.relyingparty.registration`. For example:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          red-saml:
            entity-id: "https://app.example.org/saml2/service-provider-metadata/red-saml"
            assertion-consumer-service-location: "https://app.example.org/login/saml2/sso/red-saml"
            assertingparty:
              entity-id: "https://idp.red.example/entity"
              verification:
                credentials:
                  - certificate-location: classpath:saml/red-idp.crt
              singlesignon:
                url: "https://idp.red.example/sso"
                binding: REDIRECT
          blue-saml:
            entity-id: "https://app.example.org/saml2/service-provider-metadata/blue-saml"
            assertion-consumer-service-location: "https://app.example.org/login/saml2/sso/blue-saml"
            assertingparty:
              entity-id: "https://idp.blue.example/entity"
              verification:
                credentials:
                  - certificate-location: classpath:saml/blue-idp.crt
              singlesignon:
                url: "https://idp.blue.example/sso"
                binding: REDIRECT
```

Certificate files must be **verified real IdP signing certificates**; the `example` domains are placeholders. If an IdP requires signed AuthnRequests, add **SP signing credentials** and the corresponding signing policy; never drop security requirements just to make login work.

When `saml2Login` is enabled, typical endpoints are:

- `GET /saml2/authenticate/red-saml`: creates an `AuthnRequest` using the `red` `RelyingPartyRegistration`.
- `GET /saml2/authenticate/blue-saml`: creates a request using `blue`.
- `POST /login/saml2/sso/red-saml` or `.../blue-saml`: SP processes the `SAMLResponse` at the ACS using the matching registration.
- `GET /saml2/metadata/red-saml` and `.../blue-saml` when `saml2Metadata` is enabled: publishes per-connection SP metadata.

Although the example names them `red-saml` and `blue-saml`, **`registrationId` does not have to match `tenantId`**. If an enterprise IdP serves both Red and Blue through a shared SP registration, users must still undergo tenant permission checks after SAML login. Conversely, if Red uses two SAML IdPs, both registrations can link to application tenant Red via `TENANT_AUTH_CONNECTION`.

**IdP-initiated SSO:** When there is no corresponding AuthnRequest, you need explicit policy for unsolicited responses, issuer resolution, recipient/audience, and post-login tenant selection. Letting Spring resolve `registrationId` from partially untrusted data while skipping issuer/cert validation is a dangerous bug. For sensitive applications, prefer SP-initiated SSO with request correlation.

## 12. Spring Security: Combining OIDC and SAML, Protecting Multi-Issuer APIs

A web application can support OIDC login and SAML2 login simultaneously, as well as a Resource Server API receiving Bearer tokens. However, **web users** and **machine-to-machine APIs** have different boundaries; design explicit filter chains.

### 12.1. Example Web Chain Supporting Both Login Methods

File `src/main/java/com/example/multitenant/WebLoginSecurity.java`, in a Spring Boot app with Spring Web, Spring Security, OAuth2 Client, and SAML2 Service Provider dependencies:

```java
package com.example.multitenant;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebLoginSecurity {

    @Bean
    SecurityFilterChain webLogin(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error",
                    "/oauth2/authorization/**",
                    "/saml2/authenticate/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .saml2Login(Customizer.withDefaults())
            .build();
    }
}
```

**Warning about this configuration:** This is a **minimal** template showing multiple authentication methods; production requires a per-tenant connection picker UI, metadata endpoints, CSRF/session/tenant authorization, logout, error handling, and other Spring Security filter chains. Never use `anyRequest().authenticated()` alone in a multi-tenant system and assume you have tenant isolation. When an API bearer-token flow is also required, use a separate higher-precedence `securityMatcher("/api/**")` chain, as shown below.

Registering a custom `SecurityFilterChain` can cause Boot's default configuration to back off; explicitly enable `oauth2Login` and `saml2Login` in the chain handling those URLs. If splitting across multiple chains, OAuth2 redirect and SAML ACS endpoints must belong to the proper chain rather than being excluded from necessary filters by an overly narrow `securityMatcher`.

### 12.2. Resource Server Multi-Tenancy: Same Word, Different Technical Scope

Spring Security Resource Server uses the term **multi-tenancy** when an API accepts Bearer tokens from multiple token issuers or multiple authentication strategies. For example:

```java
package com.example.multitenant;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiIssuerApiSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        JwtIssuerAuthenticationManagerResolver resolver =
            JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
                "https://issuer-a.example.org",
                "https://issuer-b.example.org");

        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(resolver))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .build();
    }
}
```

This is a **Spring Security servlet** class requiring `spring-boot-starter-oauth2-resource-server` and related dependencies; it is not a standalone Java 17 program run via `javac`. When used alongside `WebLoginSecurity` in the same project, add `@Order(2)` to the web chain or ensure explicit chain ordering; the API chain only handles `/api/**`.

**Crucial point:** `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)` allows **only issuers in the trusted allowlist**. It inspects the unverified `iss` as a hint to pick the `AuthenticationManager`, and then the decoder verifies the signature, issuer, audience, and claims per the corresponding configuration. Never take an arbitrary `iss` from a token and fetch `jwks_uri` or build a new `AuthenticationManager` without verifying the issuer is allowlisted; doing so creates issuer spoofing and SSRF risks.

**Multiple JWT issuers are not automatically multiple application tenants.** After `oauth2ResourceServer` validates a Bearer token, the API must still verify **resource audience, scopes/authorities, local identity mapping, tenant membership, and each object**. The sample code only authenticates; it does not enforce tenant authorization.

### 12.3. Differences Between Browser Login and Bearer Token API

| Attribute | Browser OIDC/SAML Login | OAuth2 Resource Server API |
| --- | --- | --- |
| Evidence | OIDC ID Token via authorization code flow / SAML Assertion | OAuth2 Access Token (JWT or opaque) |
| Session | Typically uses `HttpSession`/session cookie | Typically stateless per Bearer request |
| Where provider is selected | OIDC/SAML registration and login correlation | `AuthenticationManager`/`JwtDecoder`/issuer resolution |
| Primary configuration | `oauth2Login`, `saml2Login` | `oauth2ResourceServer` |
| Audience | OIDC ID Token audience = RP `client_id`; SAML = SP entityID | Access token audience must match the API per issuer/resource server policy |
| Tenant isolation | Membership + object authorization after login | Membership/tenant/object authorization after token validation |
| Confusion risk | Same email/issuer => auto-join tenant | Valid token issuer, yet token not meant for this API or actor not in tenant |

Never place a browser ID Token into an `Authorization: Bearer` header and treat it as an API access token. Never reuse an OIDC client registration as an arbitrary `JwtDecoder` for any issuer; each protocol has distinct validation and resource audience rules.

## 13. Tenant Context in Session and Preventing Cross-Tenant Data Leakage

If a user belongs to both Red and Blue, the UI can let them pick an active tenant. One approach stores `activeTenantId` in the server-side session after checking membership, then attaches tenant context to requests. However:

- **Switching the active tenant** is an authorized operation; before switching to Blue, verify the account is ACTIVE and Blue membership is ACTIVE.
- **Never use a `ThreadLocal` tenant context and forget to clear it** in a thread pool; use a safe filter/interceptor lifecycle so state never leaks to another request.
- **Never treat `activeTenantId` in the session as permanent proof** if access was just revoked; enforce policy versions/rechecks on critical actions.
- **`tenantId` from path or subdomain** is still only a requested tenant; handlers must compare it against active tenant/membership as designed.
- **Never use a client-supplied `tenantId` directly to pick a schema/database connection** before checking mapping and authorization.
- **Cache keys** must include tenant scope and relevant permissions; caching `report:123` is unsafe if another tenant also has ID 123. Use `(tenantId, reportId, policy context)` or isolated caches.
- **Search indexes, object storage, queues, background jobs, exports, and audit logs** must also carry verified tenant context and enforce permission checks, not just REST controllers.
- **Global admin** (if any) is a dedicated policy with auditing and step-up auth, never inferred from an `Admins` group sent by a customer IdP.

### 13.1. Tenant-Safe Query Pattern

Example repository using a parameterized query:

```sql
SELECT id, tenant_id, title
FROM report
WHERE tenant_id = :authorizedTenantId
  AND id = :reportId;
```

`:authorizedTenantId` must come from a service that has **verified the user has permission for that tenant**, never from a raw query string. After querying, the service must still check permissions on the specific report (owner, status, classification). Never use:

```sql
SELECT id, tenant_id, title
FROM report
WHERE id = :reportId;
```

for tenant-scoped requests, because a report ID may be valid yet belong to another tenant. **A tenant-aware repository/filter does not replace object-level authorization** when a single tenant has multiple permission tiers.

### 13.2. Warning About Concurrent Tenant Switching Across Multiple Tabs

If the active tenant is stored in **a shared `HttpSession`**, two tabs on the same origin share the session cookie; switching tenants in tab B can silently switch context in tab A. Mitigations:

- Put the tenant **in the route** (for example `/t/org-red/reports`) and verify permissions on every request, rather than relying on a global session variable that changes without changing the URL.
- Always verify the resource's `tenantId` matches the route.
- For APIs, resolve context from the token and server-side membership rather than trusting a session `activeTenant` changed by another tab.
- If a "current tenant" UI preference is needed, treat it as a **presentation preference**, not final authorization proof.
- Test two tabs and concurrent requests, especially background export/report jobs.

## 14. Onboarding and Lifecycle Management for Multiple IdPs/Tenants

### 14.1. Onboarding a New Tenant Does Not Automatically Onboard a New IdP

When creating a new organization in the SaaS:

1. Generate a stable `tenantId`, initial status `PENDING`, data policies, and owner.
2. Select an existing supported IdP connection or submit a new federation request.
3. If using a shared connection, configure the tenant→connection mapping and specific policies, **without granting membership to every user of that issuer**.
4. If the customer requires a dedicated IdP, verify owner/issuer/metadata/certificate/client redirect, perform a security review, and add the connection in `PENDING` status.
5. Test login and tenant permissions with test accounts; promote the connection/tenant to `ACTIVE` only after QA.
6. Define deprovisioning: lock the tenant, revoke access, retain/delete data per contract, and do not delete external identities if the user still belongs to other tenants.

**Crucially:** A tenant administrator must never be allowed to enter an arbitrary `metadataUrl`/`issuerUri` that causes the backend to fetch from internal networks; enforce allowlists/approval/egress controls to block SSRF and IdP trust poisoning.

### 14.2. Onboarding a New IdP Does Not Automatically Create a New Tenant

When adding a login provider:

1. Verify the organization owning the IdP and the issuer/IdP entityID; establish trust via DNS/TLS/metadata signatures per your model.
2. For OIDC, register the client, HTTPS callback, and verify discovery/JWKS from approved URLs; require exact `iss`, `aud`, and state/nonce.
3. For SAML, verify IdP metadata, signing certificate, SSO binding, and ACS/SP entityID; test signature/audience/recipient/time/correlation.
4. Assign a unique `connectionId` and `registrationId` that do not collide with existing keys; review impact on current users.
5. Map this connection only to **tenants approved by the owning organization**.
6. Define mappings for stable subject, email profile, groups, and permissions; never let a partner `Admin` group automatically become `ROLE_ADMIN`.
7. Test in staging against resources of another tenant and when the user has no membership.
8. Schedule certificate/JWKS rollover, metadata refresh, logout, incident response, and offboarding.

## 15. Governance Policy and Per-Tenant Authorization

A SaaS typically has at least these permission tiers:

| Role | Scope | Example | Risk If Confused |
| --- | --- | --- | --- |
| **Platform operator** | Platform-wide, tightly restricted | Manage infrastructure/tenants | Any user with group `admin` from a customer IdP could become superadmin |
| **Tenant administrator** | Specific tenant only | Manage Red members/connections | Red admin could alter Blue's data/config |
| **Tenant member** | Granted tenant and resources only | Read Red reports | Red membership could grant read access to Blue |
| **Identity provider operator** | Manage source IdP | Rotate OP/IdP signing cert | IdP operator could gain permission to delete tenant data |
| **Connection administrator** | Administer specific federation connection | Update issuer/cert/callback | Inject malicious metadata or bind connection to unauthorized tenant |

`ROLE_TENANT_ADMIN` is insufficient without the corresponding `tenantId`. Use `hasAuthority` at the route level only when the scope is clear, and continue checking `(localAccountId, tenantId, operation, resource)` in the service layer. Global admin privileges require dedicated policies and strong auditing.

Never treat `ROLE_ADMIN` in a user session as a "cross-tenant superuser" if the `Admins` group came from a single customer IdP/tenant; that is a common path to privilege escalation.

## 16. Threat Model: Multi-IdP Failures Differ from Multi-Tenant Failures

| Risk | Failing Layer | Example | Mitigation |
| --- | --- | --- | --- |
| **Issuer confusion** | Authentication | Token from issuer B verified with issuer A config or any `iss` trusted | Allowlist issuers only; verify exact issuer, signature, audience |
| **IdP trust poisoning** | Federation config | Tenant inputs metadata/JWKS URL causing app to trust attacker keys | Approval, signed metadata/trust anchors, egress URL allowlist |
| **Email-based account takeover** | Identity linking | OP B sends same email as OP A user and auto-links accounts | Stable issuer+subject, verified linking/step-up, unique constraints |
| **SAML cross-SP replay** | SAML validation | Assertion issued for SP A submitted to SP B's ACS | `AudienceRestriction`, `Recipient`, `Destination`, `InResponseTo`/replay |
| **Tenant spoofing** | Tenant routing | Client sends `X-Tenant: org-blue` or `?tenant=org-blue` | Verify tenant registry/membership; never trust raw headers |
| **BOLA/IDOR** | Resource authorization | Red user requests `/t/blue/reports/123` | Check tenant/resource ownership and permissions server-side |
| **Group name collision** | Entitlement mapping | Partner group `Admins` mapped to global `ROLE_ADMIN` | Exact `(source, tenant, group)` mapping allowlist |
| **Host header injection** | Discovery/redirect routing | Spoofed `X-Forwarded-Host` alters callback/tenant | Trusted proxy, canonical host, domain ownership checks |
| **Cross-tab tenant leak** | Session context | Red tab switches tenant while Blue tab is active | Tenant-bound routes, per-request rechecks, avoid mutable global tenant |
| **Wrong audience for API** | OAuth2 Resource Server | ID Token used as access token or token from another API | Verify resource audience/scope; separate web login and API chains |
| **Stale membership** | Authorization lifecycle | User revoked from Blue while session retains old rights | Invalidation/recheck/policy version, revoke on group changes |
| **Tenant enumeration** | UX/API | Error "org-blue exists" leaks customer list | Rate limiting, generic errors, least-privileged discovery |
| **Unsafe global logout** | Session/tenant | Red logout wrongly terminates session of another account/tenant | Session registry/correlation and explicit logout scope |
| **Shared cache across tenants** | Data layer | Report ID 42 serves another tenant's cache hit | Tenant-aware keys/isolation and object checks |
| **TOCTOU membership** | Authorization concurrency | Membership checked before async job runs after revocation | Propagate tenant+actor+policy version, recheck at execution |
| **Rogue customer admin** | Governance | Tenant admin binds another tenant's issuer or cert | Bounded admin roles, approval/dual control, audit |

**Key takeaway:** Successfully validating an ID Token or SAML assertion only closes the door on "unauthenticated users." It **does not** close the door on "authenticated users accessing the wrong organization."

## 17. High-Value Bug-Finding Test Scenarios

### 17.1. Positive/Negative Matrix

| Test Case | Setup | Expected Outcome |
| --- | --- | --- |
| **One tenant, two providers** | Red allows Staff OIDC and Partner SAML; two users have Red membership | Both log in via their source and enter Red with their respective permissions |
| **One provider, two tenants** | Staff OP; user has Red + Blue memberships | One valid principal can switch to each tenant after authorization |
| **Allowed provider without membership** | Partner connection allowed by Red; Partner user only belongs to Gold | Red access denied even though Partner login succeeded |
| **Tenant disallows provider** | Staff user requests Gold; Gold only allows Partner | Gold access denied |
| **Same subject, different issuers** | Staff `sub=u-42` and Partner `sub=u-42` | Two distinct external identities, not merged |
| **Same email, different issuers** | Two ID Tokens carry identical email | Local accounts are not auto-linked |
| **Wrong issuer with valid `registrationId` string** | Token signed by unknown issuer | OIDC validation rejects |
| **Issuer URL same hostname, different path** | Token `iss=/realm/other` instead of `/realm/staff` | Rejected for exact issuer mismatch |
| **SAML IdP returns wrong SP audience** | Validly signed Response, Audience != SP entityID | SP rejects |
| **SAML Recipient differs from ACS** | Validly signed Response, wrong Recipient/ACS | SP rejects |
| **OIDC state/nonce mismatch** | Callback from another login or wrong tab | Spring does not establish login from mismatched response |
| **Login callback without tenant-intent** | Lost SP-initiated correlation or unsolicited SAML | Does not pick an arbitrary tenant; prompts/validates per policy |
| **Fake tenant slug** | `/t/nonexistent/login` | Safe error; does not fetch an IdP URL from the slug |
| **Spoofed Host header** | `Host: blue.attacker.invalid` | Does not select a new tenant or redirect to untrusted hostname |
| **Switch active tenant** | Red+Blue user selects Blue | Verifies Blue membership then loads Blue data |
| **Two concurrent tabs** | Red tab and Blue tab | Requests in each tab never leak data due to session active-tenant changes |
| **Cross-tenant report ID** | Red user calls a report belonging to Blue | `403` or `404` per policy; no content disclosed |
| **Role collision** | Partner group `Admins` | Does not become platform admin or Red admin without explicit mapping |
| **Revoked membership** | Red revoked while user still holds session | Post-revocation requests denied within revocation SLA |
| **IdP cert/JWKS rotation** | Corp OP rotates keys or SAML IdP rotates X.509 | Only trusts approved keys of that issuer; does not widen trust to other tenants |
| **Valid API bearer issuer, wrong audience** | Access Token meant for another service | Resource Server rejects |
| **Session logout** | Web app logout while IdP SSO persists | User may SSO again, but tenant permissions must still be rechecked |
| **Disabled tenant** | Tenant Red status DISABLED | No Red access granted even when user is authenticated |
| **SCIM provisioning** | New/old membership synced from IdP | Updates only the matching tenant; does not delete memberships in other tenants |

**Test authoring approach:** Use a test IdP/OP to issue valid tokens/assertions for positive cases, and validly signed tokens/assertions with wrong issuer/audience/tenant policy for negative cases. Never tamper with a signed raw token/assertion and mistake a signature failure for a tenant rejection; tests must isolate the validator being evaluated.

### 17.2. Resource-Specific Testing

For example, a Staff user has `REPORT_READ` for Red and Blue, but lacks access to Blue's secret report:

```text
GET /t/red/reports/100         -> 200 if report belongs to Red and permission holds
GET /t/blue/reports/200        -> 200 if report belongs to Blue and permission holds
GET /t/blue/reports/299        -> 403/404 if object-level policy denies
GET /t/gold/reports/400        -> 403/404 due to no Gold membership
GET /t/red/reports/200         -> 403/404 because report 200 belongs to Blue
```

HTTP status codes may vary per existence-hiding policy; what is mandatory is **never disclosing content and never performing unauthorized actions**. Never treat an HTTP 200 on the login page as proof of tenant authorization.

### 17.3. Audit Log Testing and Privacy Criteria

Logs should capture `eventId`, `timestamp UTC`, `protocol`, `registrationId`, `verified issuer/idpEntityId`, safe reference `localAccountId`, `requestedTenantId`, `authorizedTenantId`, `permission`, `resourceTenantId`, `decision`, `policyVersion`, and `traceId`. Reduce sensitivity via pseudonymization and proper retention.

Never log raw `SAMLResponse`, ID Tokens, Access Tokens, Refresh Tokens, private keys, sensitive emails/NameIDs, or session cookies. Never use an issuer or tenant from **unverified claims** as an authoritative log label; record it only as rejected input when justified for investigation and properly filtered.

## 18. Design Pitfalls and Diagnostics

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| "We have 5 IdPs so we created 5 tenants" | Equated auth source with organization data scope | Design separate tenant registry with many-to-many connections |
| "Only one issuer yet multiple customers" | No post-login membership/resource authorization | Implement tenant membership and object isolation |
| "User has matching email domain but cannot enter tenant" | Email is just an attribute; no membership exists | Add valid membership through approval workflow; never auto-join |
| Login succeeds yet Red returns 403 | Authenticated differs from authorized; missing Red membership/role | Check account, tenant, connection policy, and permissions |
| SAML SSO succeeds yet lands in Blue by mistake | Tenant-intent not stored or wrong registration/active tenant resolved | Protect request correlation and check membership after login |
| User in Red and Blue sees swapped data when switching | Mutable/global tenant context in `HttpSession` | Put tenant in route, use immutable request context, and authorize per request |
| OP B's OIDC token accepted as OP A | Broken issuer/keys/audience validation | Bind decoder/token validation to trusted registration and exact issuer |
| API accepts Bearer tokens from any `iss` | Dynamic decoder from untrusted issuer | Allowlist trusted issuers and enforce separate API audience validation |
| SAML assertion for SP A accepted by SP B | Missing audience/recipient/correlation validation | Use Spring/OpenSAML; configure exact entityID and ACS |
| User revoked from tenant yet keeps access | Stale session authorities/cache or unchanged policy version | Invalidate/recheck membership and revoke sessions within SLA |
| One tenant sees another tenant's data | Query missing tenant predicate, un-scoped cache key, background job lost context | Add tenant scoping at data layer and object authorization |
| Onboarding a new IdP makes app hit internal network | Accepted arbitrary metadata URI, followed redirects/SSRF | Approve source URIs, enforce egress allowlist and metadata signatures |
| Same-vendor IdP has multiple issuers | Compared issuer only by hostname/vendor brand | Compare exact `iss` including approved path/realm/tenant |
| Logging out of one app still logs right back in | IdP SSO session persists; new local app session created | Distinguish local logout vs federated logout; recheck tenant permissions |
| Duplicate or missing Registration ID | Confused `tenantId` with `registrationId` or missing config | Use clear namespaces; inspect `ClientRegistrationRepository`/`RelyingPartyRegistrationRepository` |
| Tenant Red admin becomes admin of every tenant | Mapped IdP group `Admin` → unscoped `ROLE_ADMIN` | Map `(issuer,group,tenant)` to scoped permissions and check resources |

**Recommended debugging sequence:**

```text
1. Which tenantId is the request asking for, and is that tenant ACTIVE?
2. Which connection/registrationId did browser login use? Does the tenant allow it?
3. Did Spring verify SAML/OIDC with issuer, key, audience, and state?
4. External identity -> which localAccountId, and was it wrongly linked by email?
5. Is the account's membership in the requested tenant ACTIVE?
6. Are permissions in that tenant sufficient for the action?
7. Which tenant actually owns the resource? Are data/cache/search scopes right?
8. Did session/correlation/Host/proxy/async context alter the tenant?
9. If still failing, inspect audit policyVersion, IdP metadata/keys, and distributed cache.
```

## 19. Architecture and Operations Checklist

- [ ] `IdP/OP`, `issuer`, `provider`, `registrationId`, and `application tenantId` are defined separately.
- [ ] System maintains a separate `Tenant Registry` and `Identity Provider/Connection Registry` with a many-to-many `TenantAuthConnection` table.
- [ ] One tenant can use multiple IdPs and one IdP can serve multiple tenants under explicit policies.
- [ ] OIDC validation checks `iss`/`aud`/signature/`exp`/`state`/`nonce` per flow; SAML validation checks issuer/signature/audience/recipient/time/`InResponseTo`.
- [ ] Never use `email`, email domain, `displayName`, raw `sub`, or transient `NameID` to auto-link across IdPs.
- [ ] External identity keys carry appropriate issuer/tenant qualifiers; `localAccountId` is application-issued.
- [ ] Tenant-specific login stores tamper-resistant intent/correlation; post-login **always** checks membership and provider policy.
- [ ] Never treat raw `Host`/`X-Forwarded-Host`, path/query/`RelayState`/unverified JWTs as authority to set tenant or IdP trust.
- [ ] Use registration-per-tenant only when separate trust/client/ACS rules require it; never equate registration count with tenant count.
- [ ] Group/role mappings are scoped by issuer/tenant/group ID; never trust `ROLE_ADMIN` from a customer IdP.
- [ ] Resource authorization includes `tenant_id` and object-level checks; queries/cache/search/jobs/audit are all tenant-aware.
- [ ] Multi-issuer Resource Server accepts only trusted issuers and verifies resource audience; never confuse ID Tokens with Access Tokens.
- [ ] Multi-tab sessions/active tenant switching are tested; membership revocation meets SLA.
- [ ] Customer connection administrators have bounded permissions; issuer/cert/metadata URI changes require change approval, review, and auditing.
- [ ] Tenant onboarding/offboarding is separate from IdP onboarding/offboarding; never delete identities or data belonging to other organizations.
- [ ] Test one-to-many, many-to-one, and many-to-many patterns plus cross-tenant, unknown-issuer, and email-collision cases.
- [ ] Monitor issuing keys, metadata/JWKS rollover, session logout, and tenant authorization failures.
- [ ] Logging omits tokens, assertions, cookies, secrets, and unnecessary PII.

**Conclusion:** **Multiple providers** is a **federated authentication** problem: the application must know *which sources are trusted, how to verify evidence from them, and who the stable identity is*. **Multiple tenants** is an **organizational, data, and authorization** problem: the application must know *which organizations the authenticated user belongs to and what they may do on which resources*. A sound design uses **two distinct registries and a many-to-many join table**, links external identities to local accounts in a controlled manner, checks membership after authentication, and enforces tenancy at **every data access point**. Never substitute any of these steps with just an IdP name, issuer, email domain, or `registrationId`.

## 20. References

1. [Spring Security — OAuth2 Login Core Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html) — `ClientRegistration`, `ClientRegistrationRepository`, `registrationId`, and multi-provider configuration.
2. [Spring Security — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html) — authorization request resolver, user authorities mapping, and custom login logic.
3. [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) — multi-tenant `RelyingPartyRegistrationRepository`, AuthnRequest/ACS, `registrationId`, and metadata.
4. [Spring Security — OAuth2 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html) — `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers` and trusted issuer policies.
5. [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html) — URL authorization and post-authentication permission layers.
6. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html) — `iss+sub`, pairwise subjects, ID Token `aud`, state/nonce, email limitations.
7. [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html) — issuer metadata and exact issuer verification.
8. [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf) — `Issuer`, `AudienceRestriction`, `SubjectConfirmation`, NameID, and signatures.
9. [OASIS SAML 2.0 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf) — IdP/SP `entityID`, ACS, and relying-party metadata.
10. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) — deny by default, object-level authorization, least privilege.
11. [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/) — cross-tenant IDOR/BOLA risks.
12. [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) — restricting dynamic issuer/metadata fetches and egress.
