# Designing single-tenant and multi-tenant application access

An Azure application may serve only employees within a single organization, or provide a service to users belonging to many different organizations. These two models differ in how the application is registered, which sign-in endpoint is used, how consent is granted, how tokens are validated, and how data is isolated. Choosing the wrong model can prevent users from signing in, force administrators to grant overly broad permissions, or risk cross-customer data leakage.

This lesson belongs to the **Identity with Microsoft Entra ID** chapter in the **CLOUD_PROVIDERS_AZURE** module. The module explores Azure from subscriptions, resource groups, and Entra ID to virtual networks, compute, storage, data, deployment, monitoring, security, and cost control. In that architecture, Microsoft Entra ID handles identity authentication and token issuance for applications. This lesson focuses on designing **single-tenant** and **multi-tenant** access from the sign-in experience to API and data security.

After this lesson, you will be able to:

- Distinguish tenant, app registration, application object, service principal, and enterprise application.
- Choose between single-tenant, single-tenant with B2B guests, or multi-tenant based on real requirements.
- Configure supported account types, redirect URIs, and authentication endpoints.
- Describe OpenID Connect/OAuth 2.0 flows, delegated permissions, application permissions, and consent.
- Design token validation, tenant access allowlisting, and authorization inside the application.
- Build customer onboarding/offboarding workflows for multi-tenant SaaS applications.
- Assess risks such as accepting an unintended issuer, trusting email instead of authenticated identity, and cross-tenant data leakage.

## 1. Foundational concepts

A **Microsoft Entra ID tenant** is an organization's identity management boundary. Each tenant has its own identifier (tenant ID), users, groups, enterprise applications, and access policies. A tenant is an identity concept, distinct from an **Azure subscription**, which primarily organizes resources, administrative rights, and billing. One tenant can be associated with multiple subscriptions.

To integrate an application with Entra ID, understand the following objects:

| Concept | Meaning | Role in design |
|---|---|---|
| App registration | Application configuration in the owning tenant: name, client ID, redirect URI, supported account types, API permissions | Where developers define the application |
| Application object | Object defining the application, residing in the **home tenant** where the app is registered | Configuration blueprint used for adopting tenants |
| Service principal | Application identity/instance in a specific tenant | Basis for that tenant to manage access permissions and consent |
| Enterprise application | Management UI for a service principal in a tenant | Manage assigned users, SSO, policies, and app permissions |
| Client ID (Application ID) | Identifier of the application, typically a GUID | Identifier declared by the app when requesting tokens |
| Tenant ID (Directory ID) | Identifier of the tenant | Used to select tenant, validate issuer, and isolate data |

For a single-tenant application, both the application object and service principal typically reside in the owning tenant. For a multi-tenant application, **the application object remains in the home tenant**, while **a service principal can be created in each customer tenant** when the app is consented to/adopted through Entra ID workflows.

For example, a vendor registers an application in the **Vendor** tenant. When customers A and B approve the application, each customer tenant gets its own service principal for the same application ID. This lets customer administrators control how the application is used within their own organization.

~~~text
Home tenant: Vendor
  |
  +-- Application object: SaaS Portal (Client ID: app-123)
  +-- Service principal of SaaS Portal in Vendor

Customer tenant A
  +-- Service principal of SaaS Portal (app-123)
  +-- Users, groups, policies, and permissions of tenant A

Customer tenant B
  +-- Service principal of SaaS Portal (app-123)
  +-- Users, groups, policies, and permissions of tenant B
~~~

Having a service principal in a customer tenant **does not automatically prove the customer has purchased the service, is permitted to access data, or has been activated in the application**. The application needs its own customer management layer to determine which tenants have been onboarded.

## 2. How do single-tenant and multi-tenant differ?

| Criterion | Single-tenant | Multi-tenant |
|---|---|---|
| Primary audience | Identities within one chosen Entra ID tenant | Identities from multiple Entra ID tenants |
| App registration | Supports only accounts from the home tenant | Supports accounts from multiple organizations |
| Sign-in endpoint | Specific tenant's authority | Multi-organization authority or specific tenant after identifying customer |
| Service principal | In the owning tenant | In the home tenant and customer tenants after onboarding/consent |
| Consent | Follows a single tenant's process | Each customer tenant has its own consent policies and status |
| Tenant validation | Typically pinned to the chosen tenant ID | Must validate issuer, tenant ID, and the app's allowed tenant list |
| Data | Typically one organizational domain | Must isolate data per customer/tenant |
| Operations | Minimal customer onboarding workflows | Requires onboarding, consent, authorization, and offboarding per tenant |

**Single-tenant** is typically used for HR portals, internal accounting systems, operations dashboards, or apps serving a single enterprise. **Multi-tenant** suits SaaS products whose customers are independent organizations, such as an invoicing platform serving multiple companies.

An application serving multiple departments within the same tenant **does not need to be multi-tenant**. Conversely, an application serving two organizations with two independent tenants typically requires multi-tenant or an architecture inviting B2B guests into a chosen tenant.

## 3. Choosing a model based on business requirements

Before selecting Supported account types, answer:

1. Who are the users: employees of one enterprise, invited partners, or customers of multiple enterprises?
2. Do the identities belong to one tenant or independent tenants?
3. Does each customer need to independently administer consent, MFA, Conditional Access, and user assignments?
4. Is data shared within one organization or must it be strictly isolated per customer?
5. Does the app serve only interactive users, or also background tasks accessing APIs?
6. Must personal Microsoft accounts (MSA) be supported in addition to work/school accounts?

### Scenario A: internal application

A company has tenant **Corp-A** and an employee portal. Employees may only sign in with identities managed by Corp-A. Choose **single-tenant**. Use Corp-A's tenant ID to configure the authority and internal authorization policies.

### Scenario B: a few external partners

A Corp-A project team invites 15 specialists from a partner firm to use a collaboration portal. You can use **Microsoft Entra B2B collaboration** to invite external users as **guests** into tenant Corp-A, keeping the application in the single-tenant model.

Guests are represented by user objects inside tenant Corp-A. Tokens used to access the single-tenant app are typically tied to this resource tenant; the guest's home identity can reside in another tenant. Therefore, **single-tenant does not mean only full-time employees**, and multi-tenant is not mandatory simply to invite a handful of partners.

### Scenario C: SaaS product for multiple enterprises

A vendor sells asset management software to A, B, and C. Each customer wants employees to sign in with their own Entra ID tenant and manage consent and access policies. Choose **multi-tenant** and design tenant onboarding, authorization, data isolation, audit logging, and access revocation.

### Scenario D: application for individual users

If a product must support personal Microsoft accounts, choose the Supported account types option permitting **personal Microsoft accounts** and use the appropriate endpoints and flows. This is a separate choice and does not automatically come with multi-tenant for organizations. If you need to manage general consumer customer accounts, also evaluate Microsoft Entra External ID based on customer identity needs.

## 4. Supported account types and authority

In the Azure Portal, open **Microsoft Entra ID > App registrations > New registration**. The **Supported account types** setting determines which account types the application registration accepts.

| Option | Design meaning |
|---|---|
| Accounts in this organizational directory only | Single-tenant within one specified tenant |
| Accounts in any organizational directory | Multi-tenant for organizational Microsoft Entra ID tenants |
| Accounts in any organizational directory and personal Microsoft accounts | Multi-tenant organizations plus personal Microsoft accounts |
| Personal Microsoft accounts only | Personal Microsoft accounts only, when supported by the app type and use case |

**Authority** is the authentication service address used when the app redirects sign-in and requests tokens. For Microsoft identity platform v2 endpoints:

~~~text
Single-tenant:
https://login.microsoftonline.com/<TENANT_ID>/v2.0

Multi-tenant for organizational accounts:
https://login.microsoftonline.com/organizations/v2.0

Multi-organization and personal Microsoft accounts, if permitted by app registration:
https://login.microsoftonline.com/common/v2.0

Sign in with a known tenant:
https://login.microsoftonline.com/<CUSTOMER_TENANT_ID>/v2.0
~~~

The values **organizations**, **common**, and **consumers** are special sign-in endpoint segments; they are not actual customer tenant IDs. **organizations** targets work/school accounts. **common** allows choosing organizational or personal accounts when the app is configured to support them. **consumers** targets personal Microsoft accounts.

For multi-tenant applications, using **organizations** to initiate sign-in does not mean accepting every tenant into the product. After authentication, the application server must still verify the issuer and check which tenants are permitted to use the service.

Do not confuse **Tenant ID** with **Client ID**: Tenant ID identifies the identity directory; Client ID identifies the application. Both are usually GUIDs, making them easy to copy incorrectly.

## 5. Authentication flow: signing in and calling APIs

Web applications typically use **OpenID Connect (OIDC)** to authenticate users, built on the **OAuth 2.0 Authorization Code Flow** to obtain required tokens. For SPAs and public-client apps, **PKCE** must be used. Web apps with a backend typically act as confidential clients keeping credentials server-side; never put client secrets in browser JavaScript.

Conceptual flow:

~~~mermaid
sequenceDiagram
    participant U as User
    participant W as Web app
    participant E as Microsoft Entra ID
    participant A as API
    U->>W: Choose Sign in
    W->>E: Authorization request (state, nonce, PKCE if applicable)
    E->>U: Authenticate, MFA/Conditional Access if applicable
    U->>E: Complete sign-in
    E-->>W: Authorization code
    W->>E: Exchange code for tokens via appropriate channel
    E-->>W: ID token and/or access token
    W->>W: Validate identity, tenant, permissions, and create session
    W->>A: Request with access token intended for API
    A->>A: Validate signature, issuer, audience, expiry, tenant, permissions
    A-->>W: Result within permitted data scope
~~~

Token concepts must be kept distinct:

| Component | What it is for | What it must not be used for |
|---|---|---|
| **ID token** | Informs the client of the OIDC user authentication result | Substituting for an access token to call APIs |
| **Access token** | Proves permission to access **a specific resource/API** | Proving authorization for an API with a different audience |
| **Refresh token** | Helps acquire new access tokens per policy and app type | Storing unprotected or sending to APIs as an access token |
| **Session cookie** | Maintains web app session after authentication | Serving as arbitrary permission proof without server session controls |

A web UI successfully signing a user in does not prove the user is allowed to read all data in an API. **The API must independently validate access tokens targeting its own audience and enforce authorization.** This model is especially vital in multi-tenant systems, because the same API can receive requests from many organizations.

## 6. Designing a single-tenant application

Suppose company A deploys an internal expense management portal. Requirement: only identities in tenant A can access it; some users have a viewer role, others an administrator role.

### Step 1: register the application

1. Open **Azure Portal > Microsoft Entra ID > App registrations > New registration**.
2. Enter a name, e.g., **Contoso Expense Portal**.
3. Select **Accounts in this organizational directory only**.
4. Select the appropriate platform type and enter the app's redirect URI, e.g., **https://expenses.contoso.example/signin-oidc**.
5. Complete registration and record the **Application (client) ID** and **Directory (tenant) ID**.

Redirect URIs must be registered accurately per platform and environment. Avoid overly broad redirect URIs or arbitrary redirects driven by user parameters. For dev/test/prod environments, manage URIs and credentials under environment separation policies.

### Step 2: configure authentication

Conceptual configuration parameters example:

~~~yaml
identity:
  authority: "https://login.microsoftonline.com/<TENANT_A_ID>/v2.0"
  clientId: "<WEB_APP_CLIENT_ID>"
  redirectUri: "https://expenses.contoso.example/signin-oidc"
  supportedTenants:
    - "<TENANT_A_ID>"
  flow: "authorization_code"
  usePkce: true
~~~

This is an example illustrating design, not a configuration that applies verbatim to every framework. In real applications, use supported libraries such as **MSAL** or **Microsoft.Identity.Web** to handle OIDC, token caching, state/nonce, and authorization code exchange.

### Step 3: design access permissions

Authentication and authorization are two separate steps. You can define app roles such as **Expenses.Reader** and **Expenses.Admin**, then assign users or groups as needed. The application checks roles to decide who views reports, who approves expenses, or who configures policies.

If business rules require only a specific group to sign in, consider enabling **User assignment required** in **Enterprise applications** and assigning the right users/groups, alongside enforcing authorization inside the app. User assignment in Entra ID does not replace fine-grained record-level authorization rules.

### Step 4: account for guests

If collaboration with a partner is needed, you can invite them as guests via Entra B2B into tenant A and grant permissions following least privilege. Review organizational cross-tenant access, guest access, and Conditional Access policies. Never conclude every guest can freely access the app simply because they were invited into the tenant.

## 7. Designing a multi-tenant application for SaaS

Suppose vendor **Vendor** operates a contract management application for customers A and B. Each customer's users authenticate against their own Entra ID tenant; A's and B's data must remain isolated.

### Reference architecture

~~~text
                +-------------------------------+
                | SaaS web frontend / backend   |
                | Home tenant: Vendor           |
                | App registration: multi-tenant|
                +---------------+---------------+
                                |
                      OIDC / OAuth 2.0
                                |
                +---------------+---------------+
                | Microsoft Entra ID            |
                +---------------+---------------+
                                |
                +---------------+---------------+
                | SaaS API                      |
                | Validate token + tenant       |
                | Authorize user/app roles      |
                +---------------+---------------+
                                |
              +-----------------+------------------+
              |                                    |
     +--------v---------+                 +--------v---------+
     | Customer tenant A|                 | Customer tenant B|
     | Data partition A |                 | Data partition B |
     +------------------+                 +------------------+
~~~

The diagram is logical: organizations A and B have independent identity tenants, while data deployment may reside in a single Azure subscription, multiple subscriptions, a partitioned database, or separate databases. **Multi-tenant identity** and **multi-tenant data architecture** are related decisions, yet not identical.

### Step 1: register the application

1. In Vendor's home tenant, go to **App registrations > New registration**.
2. Select **Accounts in any organizational directory** if serving only work/school accounts.
3. Configure redirect URIs matching web/SPA/mobile platforms and environments.
4. Record the client ID; choose the **organizations** sign-in endpoint or tenant-specific authority once the customer organization is identified.
5. If the backend API is a separate resource, register/configure the API accordingly, specifying the scopes or app roles clients need to request.

Do not expand to personal Microsoft accounts if the SaaS product serves only organizational customers. An overly broad registration widens the authentication and authorization matrix that must be tested.

### Step 2: design tenant onboarding

A secure onboarding workflow typically includes:

1. The customer provides or confirms the organization's **tenant ID**.
2. An authorized administrator in the customer tenant reviews the application and grants **consent** when requested permissions require approval.
3. Entra ID creates/manages the application's service principal in the customer tenant via the appropriate consent/provisioning flow.
4. The backend validates the sign-in result or callback from the consent flow, checking state, tenant, permissions, and approval status.
5. The SaaS system links the tenant ID to the customer profile, product subscription, and data partition configuration.
6. Customer admins are assigned admin roles in the product and invite/assign users per policy.
7. The application marks the tenant **active** once contractual, consent, and configuration prerequisites are met.

Never accept a tenant ID from an HTTP parameter and immediately grant data access or provision an activated customer. A tenant ID received as input is only for lookup/initiation; base access decisions strictly on identity information from **validated tokens** and trusted onboarding records.

### Step 3: request appropriate consent

Each tenant has its own policy on whether users can self-consent or whether an administrator must approve. Sensitive permissions or application permissions typically require admin consent; less sensitive delegated permissions may be consented to by users depending on tenant configuration and policy.

For instance, a customer admin may need to approve the SaaS app reading data in the SaaS's own API or accessing Microsoft Graph with declared permissions. Request only permissions the app genuinely needs to deliver stated features.

Consent **does not replace SaaS authorization**. Even after consent, users in a customer tenant may still need product roles assigned, workspace access granted, and organizational security policies enforced.

### Step 4: tenant discovery and tenant-specific sign-in

When the user's organization is not yet known, the application can start with the **organizations** endpoint to support multi-organization sign-in. Once the organization is confirmed and onboarded, the app can use an authority like **/CUSTOMER_TENANT_ID/v2.0** for interactions that should bind to a specific tenant.

Never determine a tenant by parsing the email domain after the `@` character. One organization can own multiple domains; guests can use emails from other organizations; emails or preferred usernames can change. Prefer the tenant ID from a validated token and the list of verified customer tenants.

## 8. OAuth 2.0 permissions: delegated, application, scope, and app role

In an architecture where a web frontend calls an API, distinguish two access patterns:

| Type | Signed-in user present? | Common authorization mechanism | Common flow |
|---|---|---|---|
| Delegated permissions | Yes; app acts on behalf of the user | OAuth scopes, optionally combined with roles | Authorization code, On-Behalf-Of |
| Application permissions | No user required; service acts with application identity | Application roles/app permissions | Client credentials |

A **Scope** describes a permission a client requests from an API on behalf of a user, such as **Contracts.Read** or **Contracts.Write**. In a delegated access token, the **scp** claim typically contains the space-separated list of granted scopes.

An **App role** can be assigned to users/groups or applications depending on configuration. An access token can carry the **roles** claim. Do not assume that having roles implies a user is present; application tokens also commonly contain app roles when application permissions are granted.

Example:

~~~text
Frontend calling API:
  User signs in
  --> client requests scope api://<API_CLIENT_ID>/Contracts.Read
  --> API checks scp and permissions on the contract

Automated sync worker:
  No user present
  --> client credentials requests consented application permissions
  --> API checks roles, caller identity, and allowed tenant
~~~

With client credentials, token requests to a resource typically use scope **{resource}/.default**, reflecting configured and consented application permissions; never treat this as a way to bypass permission approval.

If a frontend or API calls another downstream API on behalf of the user, consider **On-Behalf-Of (OBO)**. Each layer must use a token issued specifically for its target resource; never forward an ID token to a downstream API.

## 9. Token validation and authorization in single-tenant/multi-tenant apps

A dangerous design flaw is decoding a JWT and trusting its claims without validating signature, issuer, and audience. A JWT payload is readable before verification; that data is **untrusted**.

### Mandatory token checks

The API must use proven middleware/libraries to:

1. Validate the signature against Microsoft Entra ID signing keys retrieved from trusted OpenID Connect metadata, with key rotation handling.
2. Verify the token is not expired, respects not-before timestamps, and meets time-skew policies.
3. Confirm **aud** matches the exact API/resource the token was issued for.
4. Confirm **iss** is valid and matches the issuing tenant, rejecting arbitrary untrusted issuers.
5. Inspect the tenant ID (**tid**) after the token has been validated.
6. Verify token type, delegated permissions (**scp**) or application roles (**roles**), plus endpoint-specific conditions.
7. Enforce authorization at the business object level: workspace, record, project, contract, and customer data boundary.

For single-tenant apps, issuer policy typically pins to the chosen tenant. For multi-tenant apps, tokens from different tenants carry different issuers. Applications must use **tenant-aware issuer validation** following Microsoft guidance, then apply the product's own tenant allowlist/onboarding policy.

The OIDC metadata document for a specific tenant has the form:

~~~text
https://login.microsoftonline.com/<TENANT_ID>/v2.0/.well-known/openid-configuration
~~~

Segments such as **organizations** or **common** are used during sign-in discovery; never treat the literal string **common** as the actual issuer of all access tokens. To avoid security bugs, use appropriate official libraries (MSAL/Microsoft.Identity.Web with API authentication middleware) and configure issuer validation properly for the app type and tenant model.

### Common claims

| Claim | Meaning | Appropriate usage |
|---|---|---|
| **tid** | Issuing tenant | Map to onboarded customer after token validation |
| **iss** | Token issuer | Verify the issuing authority is trusted |
| **aud** | Intended resource | Ensure the API only accepts tokens issued for itself |
| **oid** | Object ID of user or service principal in tenant | Form an identity key with tid when appropriate |
| **sub** | Application-scoped subject identifier | Can serve as authenticated subject per design |
| **scp** | Granted delegated scopes | Check operations the user is permitted to perform |
| **roles** | App roles/application permissions | Determine roles and API calling permissions |
| **azp** or **appid** | Calling client identity, depending on token version | Verify calling app when the API restricts clients |

**UPN, preferred_username, name, email, and domain** are typically for display or contact and should not serve as stable authorization keys. For guest accounts, email may belong to a different domain than the tenant managing the object. For application data, the pair **(tid, oid)** is generally suitable to identify an object within a tenant context when present and verified.

### Example API protection logic

The following is **pseudocode** illustrating policy, not complete JWT middleware:

~~~text
token = microsoftEntraJwtMiddleware.validate(
    signature = required,
    issuer = validTenantAwareIssuer,
    audience = expectedApiAudience,
    lifetime = required
)

tenantId = token.claim("tid")
if tenantId not in onboardedActiveTenants:
    reject(403, "Tenant is not active")

if endpointRequiresDelegatedScope:
    requireScope(token, "Contracts.Read")
if endpointRequiresApplicationRole:
    requireAppRole(token, "Contracts.Sync")

customer = customerDirectory.lookupByTenantId(tenantId)
record = contractRepository.getByCustomerAndId(customer.id, request.contractId)
if record is missing or caller lacks access to record:
    reject(403, "Access denied")

return record
~~~

Middleware must **validate the token before** the application trusts and uses tid, oid, scp, or roles. In SaaS models, verifying an active tenant and checking data-level permissions are mandatory protective layers beyond JWT verification.

## 10. Data isolation in multi-tenant applications

Multi-tenant sign-in only solves **who is authenticated**. It does not prevent customer A's user from querying customer B's data. Data separation must be designed and tested inside the application.

### Storage models

| Model | Benefits | What to control |
|---|---|---|
| Shared database, shared tables with CustomerId/TenantId column | Resource efficiency, centralized operations | Every query must filter by tenant; consider row-level security |
| Shared database, separate schemas or table sets | Clearer logical separation | Migrations, configuration, and access permissions per schema |
| Dedicated database per tenant | Easier data isolation and backups for certain requirements | Cost, provisioning, migrations, and per-tenant monitoring |
| Dedicated subscription or deployment environment | Suits customers with strict isolation and compliance policies | Higher cost and operational complexity |

Dangerous example: an API receives **GET /contracts/123** and queries solely by contract ID without filtering by customer. User A can guess B's ID and retrieve B's data if the endpoint lacks tenant checks.

Secure design:

~~~sql
SELECT ContractId, CustomerId, Title
FROM Contracts
WHERE ContractId = @contractId
  AND CustomerId = @customerIdFromValidatedTenantContext;
~~~

The value **customerIdFromValidatedTenantContext** must come from mapping the validated token's tenant ID to the backend customer record. Never take it from a query string, request body, or client-supplied header and trust it as authorization.

Besides read filtering, apply the same rule to creates, updates, deletes, exports, caches, queues, file storage, search indexes, logs, and backups. Avoid cache keys containing only a record ID without customer isolation.

### Per-customer administrative permissions

One user may be an admin in tenant A yet only a reader in tenant B, or be invited as a guest across multiple organizations. Never bind permanent permissions to an email address. Store relationships among validated identity, customer ID, membership, and roles in the application, updating them whenever customer permissions change.

## 11. Consent, Conditional Access, and customer lifecycle

In multi-tenant SaaS, consent and authorization are related yet distinct:

- **Authentication:** Entra ID verifies identity and issues tokens per applicable configuration and policies.
- **Consent:** users or admins approve permissions requested by the app according to tenant policy.
- **Authorization:** the API and SaaS system decide which business operations the caller can perform on which data.
- **Provisioning:** adding or updating users, groups, roles, and tenants in the SaaS system.

### Onboarding

The process must record the tenant ID, timestamp of admin consent, granted permissions, customer record, initial administrator, and activation status. If a customer grants only partial permissions, the application should clearly handle which features remain unavailable.

### Operations

Customer tenants may enforce MFA, Conditional Access, user consent restrictions, or block unapproved applications. SaaS vendors should surface clear error guidance helping customer admins inspect **Enterprise applications**, API permissions, user assignments, and sign-in logs. Registering an app as multi-tenant cannot bypass a customer tenant's security policies.

### Offboarding

When a customer stops using the product, the backend must disable the tenant in the customer directory, terminate access, and execute data handling/deletion per contract and retention policy. A customer admin may revoke consent or delete the SaaS enterprise application in their tenant. However, **deleting the service principal in the customer tenant does not automatically delete data stored by the SaaS backend**.

## 12. Common design mistakes

| Symptom | Possible cause | Resolution path |
|---|---|---|
| Tenant B users cannot sign in | App registration is still single-tenant or uses tenant A's authority | Check Supported account types and authority |
| Personal Microsoft accounts cannot sign in | App only supports organizational accounts | Determine whether MSA is genuinely required and pick the matching account type |
| Error requires admin approval | Requested permission needs admin consent or tenant restricts user consent | Trim unnecessary permissions and prepare an admin consent flow |
| Sign-in succeeds, yet API returns 401 | ID token sent to API, wrong audience, expired token, or invalid issuer | Verify API-specific access token, audience, and issuer validation |
| API returns 403 after sign-in | Tenant not onboarded, missing scope/role, or no object-level access | Check active tenant status, consent, app roles, and business permissions |
| User from an unknown tenant reaches post-login screens | App only verifies valid token without checking customer allowlist | Add tenant onboarding/allowlist and block unactivated tenants |
| Wrong customer's data accessed | Backend trusts tenantId from request or omits tenant filtering | Bind customer context to validated token; audit every query |
| Switched tenant, yet session shows old data | Session/cache not keyed by tenant or stale data not cleared | Key caches/sessions by tenant and clear stale data on context switch |
| Guest cannot see the app | Not invited/assigned, or B2B/assignment policy blocks access | Check guest object, user assignment, and access policies |

When analyzing incidents, record correlation ID/request ID, tenant ID, sign-in timestamp, and error code. Never log raw access tokens or refresh tokens; if inspecting claims for debugging, use safe tools and avoid sharing live tokens.

## 13. Design lab: internal portal and multi-organization SaaS

This exercise covers two architectures. You can complete the design without paid subscriptions or admin rights across multiple tenants. If practicing in the Portal, use an authorized test environment.

### Part A: single-tenant internal portal

Requirement: enterprise **Alpha** has one Entra ID tenant, 200 employees, and a project management portal. Only assigned users can view data; a few partner specialists need to collaborate for 2 months.

Design:

1. Choose a **single-tenant** app registration in Alpha's tenant.
2. Specify the authority using Alpha's tenant ID.
3. Create app roles **Projects.Reader** and **Projects.Manager**.
4. Assign only authorized users/groups; invite external specialists as Entra B2B guests if policy allows.
5. API validates token, issuer, and audience; enforces roles and per-project permissions.
6. Define how guest accounts and permissions are revoked at the end of the 2 months.

Deliverables are a component diagram, role-group matrix, and access denial rules.

### Part B: SaaS serving Alpha and Beta

Requirement: vendor **Vendor** operates a contract management application. Two customers, Alpha and Beta, have independent tenants, each with its own administrator; data must never leak between them.

Design:

1. Register an **Accounts in any organizational directory** app in Vendor's home tenant.
2. Use the **organizations** endpoint for multi-organization sign-in or tenant-specific authority once the customer is identified.
3. Build an admin consent and onboarding workflow for each tenant.
4. Store the mapping **validated tid → customer ID**, active status, and customer admin roles.
5. API checks signature, issuer, audience, token lifetime, active tenant, and scopes/app roles.
6. Every data query enforces filtering by customer ID derived from server-side context.
7. Build an offboarding workflow: revoke access, block requests, handle data, and record audits.

### Minimum test matrix

| Scenario | Expected outcome |
|---|---|
| Alpha employee signs in to single-tenant portal with matching role | Signs in and acts only within assigned permissions |
| Beta tenant user not invited to Alpha tries single-tenant portal | Access denied |
| Guest invited to Alpha without app assignment | Denied access to content requiring assignment |
| Alpha employee signs in to SaaS when Alpha is onboarded | Accesses Alpha data per permissions |
| Beta employee signs in to SaaS when Beta is onboarded | Accesses Beta data per permissions |
| Valid token from a tenant not yet onboarded | Denied access to service |
| Token whose audience targets a different API | Rejected by API |
| Alpha user tries reading Beta's contract ID | Denied, with zero Beta data leaked |
| Background app lacks required application role/consent | Cannot call API for requested operation |
| Beta is offboarded while an old session remains | Backend rejects new requests based on tenant state |

### Self-check questions

1. Why do multiple departments sharing one Entra tenant not necessarily need a multi-tenant application?
2. How do the application object and service principal differ when a SaaS app is approved by multiple customers?
3. When should you use B2B guests instead of a multi-tenant app registration?
4. How does the **organizations** endpoint differ from an authority containing a tenant ID?
5. Why are a successful sign-in and a valid token still insufficient to access SaaS data?
6. What must the API verify in **iss**, **aud**, **tid**, **scp**, and **roles**?
7. Why is **email** not a trustworthy key for isolating multi-tenant data?
8. What must customer offboarding do beyond revoking consent?

## 14. Pre-production checklist

- [ ] Supported account types match target customers and enterprise policy.
- [ ] Redirect URIs are registered accurately; authorization code flow/PKCE used where appropriate.
- [ ] Client secrets/certificates are protected server-side; safer credentials and clear lifecycles are preferred.
- [ ] Clients and APIs use tokens matching the target audience; APIs validate signature, issuer, lifetime, and claims.
- [ ] For multi-tenant, only onboarded and active tenants can gain access.
- [ ] Scopes, app roles, admin consent, and user assignments follow least privilege.
- [ ] Data, caches, logs, and background jobs are isolated per customer/tenant.
- [ ] Tests cover cross-tenant access, stale sessions, guests, and revoked tenants.
- [ ] Processes exist for onboarding, offboarding, auditing, and sign-in troubleshooting.
- [ ] MFA/Conditional Access and each tenant's security requirements are factored into the design.

## 15. References

- [Microsoft identity platform application model](https://learn.microsoft.com/entra/identity-platform/application-model) — app registration, application object, and service principal.
- [Supported account types](https://learn.microsoft.com/entra/identity-platform/supported-accounts-validation) — determining which account types an application supports.
- [OpenID Connect on the Microsoft identity platform](https://learn.microsoft.com/entra/identity-platform/v2-protocols-oidc) — endpoints and sign-in flows.
- [Microsoft identity platform OAuth 2.0 authorization code flow](https://learn.microsoft.com/entra/identity-platform/v2-oauth2-auth-code-flow) — authorization codes and PKCE.
- [Permissions and consent](https://learn.microsoft.com/entra/identity-platform/permissions-consent-overview) — delegated/application permissions and consent models.
- [Microsoft Entra B2B collaboration](https://learn.microsoft.com/entra/external-id/what-is-b2b) — collaborating with external users.
- [Microsoft identity platform access tokens](https://learn.microsoft.com/entra/identity-platform/access-tokens) — tokens, claims, audience, and API validation.

Design should begin with **target users and data boundaries**, and only then select the app registration type. Single-tenant fits when an application operates within a single tenant (which may include B2B guests); multi-tenant fits when multiple independent tenants require separate authentication. In both models, Entra ID is responsible for identity and token issuance, while the application remains responsible for business and data authorization.
