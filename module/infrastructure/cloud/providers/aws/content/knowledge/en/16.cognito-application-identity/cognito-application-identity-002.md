# Designing User Attributes, Groups, and App Clients

> **Chapter:** Application Identity with Cognito  
> **Module:** CLOUD_PROVIDERS_AWS — explore AWS across Regions/AZs, IAM, VPC, compute, storage, databases, integration, and serverless; build capabilities in service selection, security, monitoring, recovery, and cost management.

## Learning Objectives

When building an e-learning platform, customer portal, or SaaS application, sign-in is only a small part of identity management. The system needs to know **who the user is**, which groups they belong to, which applications can view/edit profile data, and which operations APIs are allowed to perform. In **Amazon Cognito User Pools**, the three core design objects are:

- **User attributes:** per-account information, including standard attributes, custom attributes, and verification status fields.
- **Groups:** sets of users with similar traits or application roles, appearing in tokens and optionally attached to an IAM role for Identity Pool integration scenarios.
- **App clients:** per-application configurations for mobile, SPA, web backend, or machine-to-machine apps; controlling authentication flows, OAuth scopes, callback URLs, token lifetimes, and **attribute read/write permissions**.

This lesson distinguishes **authentication**, **authorization**, and **application data ownership**, avoiding dangerous patterns such as relying on a user-editable attribute to determine administrative privileges.

After this lesson, you will be able to:

1. Design standard and custom attribute schemas following data-minimization principles, accounting for options that are difficult to change after pool creation.
2. Compare username, email/phone aliases, `preferred_username`, `sub`, and `email_verified` verification.
3. Determine when to use groups, the meaning of `Precedence`, and the `cognito:groups` and `cognito:preferred_role` claims.
4. Create separate app client designs for SPA, mobile, web server, and machine-to-machine applications, choosing the right public/confidential type and OAuth flows.
5. Separate `ReadAttributes`/`WriteAttributes` permissions, scopes, resource servers, and backend business permissions.
6. Inspect and verify ID/access tokens, handling federation/attribute mapping without introducing authorization vulnerabilities.
7. Inspect user pools, groups, and app clients using **read-only** AWS CLI commands without extracting client secrets or personal data.
8. Plan security, operations, auditing, limits, costs, and identity incident handling.

## 1. Placing User Pools in Application Architecture

### 1.1. User Pool vs. Identity Pool

**Amazon Cognito User Pool** is a user directory and identity provider (IdP) for applications. It manages sign-up, sign-in, account recovery, multi-factor authentication, federation with enterprise/social IdPs, and token issuance via supported protocols.

**Amazon Cognito Identity Pool** (Federated Identities) is an optional component for **exchanging an authenticated identity for temporary AWS credentials** according to IAM role configurations and trust policies. Many applications only need a User Pool + backend API, **without needing an Identity Pool**.

| Requirement | Appropriate Component | Notes |
|---|---|---|
| End-user sign-up and sign-in | Cognito User Pool | Password/passkey/MFA/federation depending on features and configuration |
| Issuing ID tokens and access tokens for web/mobile | User Pool app client | Tokens must be verified at the resource server |
| Authorizing `/courses`, `/reports` APIs | Backend/API Gateway + scopes/groups/app logic | Do not treat groups as a complete replacement for authorization |
| Granting direct Amazon S3 access via STS credentials | Identity Pool when designed appropriately | Verify IAM role mappings and resource scope |
| Granting developers permissions to operate Cognito | AWS IAM | IAM administration is separate from user authentication |
| Storing course/order/progress relationships | RDS/DynamoDB or application data store | Do not turn User Pool into a business database |

### 1.2. User-to-API Diagram

~~~mermaid
flowchart LR
    U[Student / Teacher] --> APP[Web SPA / Mobile / Server Web]
    APP --> CL[Appropriate app client]
    CL --> UP[(Cognito User Pool)]
    UP -->|ID token + access token| APP
    APP -->|Bearer access token| API[API Gateway / Backend]
    API --> AUTH[Verify JWT issuer, signature, token_use, app client + scope/group]
    AUTH --> DATA[(Business RDS / DynamoDB)]
    UP -. Groups / attributes .-> AUTH
    IDP[Google / OIDC / SAML IdP] --> UP
    IP[Identity Pool: optional] -. AWS temporary credentials .-> APP
    UP -. Identity token .-> IP
~~~

**A single user pool can have multiple app clients**. The same user can sign in to the student web portal and the mobile app using different client IDs. User attributes **are stored at the user pool level**, while how each app client can read/write attributes may differ.

### 1.3. Authentication Is Not Authorization

For example, teacher `teacher-001` signs in successfully and receives an access token. That only proves identity/token validity under the verified conditions. To allow `POST /courses/123/grade`, the backend must also verify:

1. The token is valid, unexpired, has the right issuer, and has the right purpose.
2. The client/scopes/groups are permitted to perform that category of operation.
3. The user is actually assigned to **teach course 123** in the business database.
4. Policies regarding course status, tenant, and audit are satisfied.

**`cognito:groups=["teachers"]` does not automatically mean that teacher can edit grades for every student in every course.**

## 2. User Attributes: Classify Before Designing the Schema

### 2.1. Standard Attributes and Custom Attributes

Cognito supports OIDC **standard attributes** and other directory attributes, for example:

| Attribute | Role | Use as primary business key? |
|---|---|---|
| `sub` | Stable, unique identifier within the user pool | **Recommended** as internal identity key (paired with user pool/issuer in multi-pool setups) |
| `username` | Username managed by the user pool mechanism | Should not replace `sub` across all sign-in models |
| `email` | Contact/sign-in email address if configured | **No**; mutable and requires verification |
| `email_verified` | Email verification status | Not an application role/permission |
| `phone_number` | Phone number in supported format | No; can change and be reassigned in the real world |
| `phone_number_verified` | Phone number verification status | Grants no business permissions |
| `preferred_username` | Display name or alias if enabled | No; mutable |
| `given_name`, `family_name`, `name` | Display profile details | No |
| `locale`, `zoneinfo` | Language/timezone preferences | No |
| `custom:tenantId` | Custom attribute if a tenant hint is needed | Use for authorization only when the write source is trusted and the backend verifies the relationship |

**`sub`** is the primary choice for linking profiles to business records. Cognito issues this identifier with a value that is **immutable within the same user pool**; do not hard-enforce parsing a fixed UUID format. When combining multiple user pools, use a logical key such as **`(issuer, sub)`** rather than assuming `sub` is globally unique.

### 2.2. Four Questions for Every Attribute

Before adding a field, document:

1. **Purpose:** is this field needed for sign-in, notifications, UI display, or access control?
2. **Trusted data source:** end user, support team, admin backend, HR system, or external IdP?
3. **Who reads/writes it:** SPA, mobile app, BFF, admin portal, background job?
4. **Lifecycle:** is the field mutable, does it need synchronization, does it contain sensitive data, and what is the retention/deletion policy?

An example design table:

| Data | Where Stored | Write Source | Client Can Read? | Client Can Self-Edit? |
|---|---|---|---|---|
| `sub` | Cognito | Issued by Cognito | Used as identity key | No |
| `email` | Cognito | User + verification | Yes as needed | Yes via verification flow |
| `given_name` | Cognito | User | Yes | Yes |
| `custom:tenantId` | Cognito or business data store | Trusted admin backend | Possibly, if needed for display | **No** |
| Teacher role for class 123 | Application database | Business system | Via authorized API | **No** |
| Password | Cognito auth flow | User over secure protocol | Never returned in plaintext | Not via normal profile update |
| Payment card / private medical records | Specialized compliant service | Approved workflow | Not by default | Do not store in custom attributes |

### 2.3. Do Not Use User Pool as a Catch-All Database

Custom attributes have schema and size limits and are unsuitable for storing:

- Long or frequently changing class rosters;
- Many-to-many user–group–resource relationships;
- Fine-grained permissions across thousands of objects;
- Images, transcripts, or specially regulated compliance data;
- Secrets, OAuth tokens from external systems, or access keys.

Cognito should hold a **minimal identity profile** and attributes required for authentication flows, while RDS/DynamoDB/S3 store business data with their own lifecycles and permissions.

## 3. Usernames, Sign-In Aliases, and Contact Verification

### 3.1. Three Commonly Confused Concepts

| Concept | Explanation | Stable? |
|---|---|---|
| `sub` | Identifier issued by Cognito | Stable within the pool |
| `username` | Internal username per user pool configuration | Managed by Cognito, do not treat like a mutable email |
| `email` / `phone_number` | Contact attribute and potential sign-in identifier | Mutable |
| `preferred_username` | User's chosen display name/alias if enabled | Mutable |

Do not create application foreign keys on `email`. Emails can change, lose ownership, or be re-registered by someone else later; using email as a business key makes account merging and email changes difficult.

### 3.2. Username Attributes and Alias Attributes

When creating a user pool, you choose the sign-in strategy:

- **Username attributes:** allows using email, phone number, or both as the username per configuration.
- **Alias attributes:** keeps a stable username while allowing sign-in with one or more aliases such as email/phone/`preferred_username` once verification conditions are met.

The two models have **different uniqueness and verification semantics**. With username attributes, the email/phone used at sign-up has uniqueness constraints per configuration. With aliases, an email/phone can exist across multiple profiles in unverified states, while a **verified alias** belongs to only one user for sign-in at a given time.

**Critical constraint:** choices for sign-in identifiers, username case sensitivity, and required standard attributes belong to the group of settings that **cannot be arbitrarily changed after pool creation**. If designed incorrectly, you usually must create a new user pool and plan a migration.

### 3.3. Product-Based Selection Examples

| Product | Starting Choice | Why? |
|---|---|---|
| Consumer student app | Email as sign-in identifier | Easy to use; requires email delivery/verification |
| Employee portal with staff IDs | Username + email alias | Employee ID/username stays stable, email remains a convenient login option |
| Mobile app with phone OTP | Phone sign-in where supported | Requires SMS/cost planning and SIM-swap defenses |
| Multi-IdP SaaS | Federation + `sub`/identity linking | Never merge people solely by matching unverified emails |
| Marketplace needing editable display names | Use `preferred_username`/profile name | Decouples display name from the identity key |

### 3.4. Email Verified Does Not Equal Permanent Account Ownership

`email_verified=true` proves an email check passed per policy at a point in time. It:

- Does not prove the user is a valid teacher or employee.
- Does not prove the same person still owns the inbox if the email address changed hands.
- Must not be writable by the client to bypass verification.
- Does not replace MFA for high-risk operations.

When allowing email or phone updates, configure **verification before update** per security requirements. For payment/admin accounts, require re-authentication before sensitive operations.

## 4. Custom Attributes: Data Types, Mutability, and Schema-Change Risks

### 4.1. Rules for Creating Custom Attributes

Cognito allows adding **custom attributes** to a user pool. Key points to verify:

- Attribute names in code/tokens carry the **`custom:`** prefix, such as `custom:tenantId`.
- Types include String, Number, Boolean, and DateTime per API support; values are stored/transmitted as **strings** when applications interact with Cognito and inside ID tokens.
- Each user pool has a quota on custom attributes (AWS documentation currently states a maximum of 50); do not treat it as a constantly evolving data model.
- Custom attributes **cannot be marked required** for users in the same way required standard attributes are.
- Once added to a pool, a custom attribute **cannot be deleted, renamed, have its type changed, or have its mutability/constraints altered**.
- A custom attribute can be **mutable** or **immutable**; immutable ones can only be set during user creation per service capabilities.
- Legacy developer attributes with the `dev:` prefix should not be the default choice for new designs; AWS recommends app client attribute permissions instead.

**Example schema JSON declaration (illustrative fields only):**

~~~json
{
  "Name": "tenantId",
  "AttributeDataType": "String",
  "DeveloperOnlyAttribute": false,
  "Mutable": false,
  "Required": false,
  "StringAttributeConstraints": {
    "MinLength": "1",
    "MaxLength": "64"
  }
}
~~~

In schema declaration APIs, `Name` is typically the **name without the `custom:` prefix**. When reading/writing user attributes, use `custom:tenantId`. Restrict names per current AWS rules; choose simple names using only ASCII letters, digits, underscores/hyphens per supported regexes.

### 4.2. Mutable or Immutable?

| Design | Example | Pros | Risks |
|---|---|---|---|
| Mutable | `custom:uiTheme` | User can change it when client has WriteAttributes | Unsuitable as authorization proof |
| Immutable | `custom:registrationSource` | Written once at account creation | Cannot be corrected if initial data was wrong |
| Mutable with admin-only write | `custom:tenantId` if tenant moves are needed | Admin backend can update via an approved workflow | Must block user self-writes across **all app clients** |
| Kept outside Cognito | `courseMemberships` | Flexible querying and business permission management | Requires separate API/data store |

**Choosing immutable does not automatically guarantee trustworthiness** if you allow registrants to supply the value at SignUp. For example, an immutable `custom:isAdmin` that an app client can write during sign-up is still dangerous: a user can set `"true"` during profile creation. Admin privileges must be set by an authoritative provisioning workflow.

### 4.3. Immutability Does Not Bypass Migrations

Suppose after a year, `tenantId` changes from a UUID to a multi-region enterprise code. Because you cannot alter the type/constraints of an existing custom attribute, you may have to:

1. Create a new attribute such as `custom:tenantKeyV2` if quota and design permit.
2. Backfill/transform data via authorized APIs/IaC, without exposing writes to clients.
3. Update application versions to read both old and new fields during the migration window.
4. Cut over backend logic and audit.
5. Leave the old attribute unused because **custom attribute schemas cannot be deleted**.

Therefore, add custom attributes only when there is a **clear identity justification and a long-term data contract**.

## 5. App Client Attribute Permissions: Read/Write Is Not OAuth Scopes

### 5.1. Why Each App Client Needs Separate Attribute Permissions

A single user pool may serve three applications:

~~~text
User Pool: school-users
├── App client: student-spa
│   ├── Read: sub, email, email_verified, given_name, custom:tenantId
│   └── Write: email, given_name (via verification flow)
├── App client: teacher-portal
│   ├── Read: profile fields needed for display per policy
│   └── Write: display name, support contact details
└── App client: admin-bff
    ├── Read: attributes needed for administration
    └── Write: administrative updates via backend access controls
~~~

An app client **does not create a separate copy** of the user. Profile changes in the same pool can appear in tokens/`GetUser` responses of other app clients if read permissions/claims allow.

### 5.2. ReadAttributes and WriteAttributes

| App Client Setting | Effect | Design Risk |
|---|---|---|
| `ReadAttributes` | App client permission to read profile attributes and corresponding ID token claims | Overexposing PII or leaking PII into logs |
| `WriteAttributes` | App can modify allowed attributes via user-facing APIs | Self-privilege escalation if writing `custom:role`/`custom:tenantId` is allowed |
| `AllowedOAuthScopes` | OAuth scopes the app may request | Does not replace Read/WriteAttributes |
| `ExplicitAuthFlows` | Enables specific Cognito API authentication flows | Enabling unnecessary flows increases attack surface |
| `CallbackURLs`, `LogoutURLs` | Redirect paths in OAuth/managed login | Wrong domain redirects can leak authorization codes or sessions |
| `GenerateSecret` / client secret | Confidential client authentication per supported modes | Must never be embedded in SPA/mobile |
| `AccessTokenValidity`, `IdTokenValidity`, `RefreshTokenValidity` | Token lifetimes | Balance UX against exposure window |

**Warning about defaults:** with app client creation APIs, **omitting `ReadAttributes`/`WriteAttributes` does not mean deny-all**. AWS documentation notes defaults permit a set of standard attributes, and in certain configurations allow broader attribute access than you might expect. `DescribeUserPoolClient` may also **omit those fields** when defaults are in effect. Always **explicitly configure least-privilege permissions**, and audit effective configuration rather than assuming empty fields mean safe defaults.

### 5.3. Special Rules for Authorization-Relevant Attributes

Suppose a system has `custom:tenantId` and `custom:roleLevel`. If the student app allows:

~~~text
WriteAttributes = ["email", "custom:tenantId", "custom:roleLevel"]
~~~

then a user can call the profile update API with self-chosen values, corrupting tenant/role logic **if the backend trusts those claims**.

Safer design:

~~~text
Student SPA:
  ReadAttributes  = ["email", "email_verified", "given_name",
                     "custom:tenantId"]
  WriteAttributes = ["email", "given_name"]

Admin provisioning:
  Writes tenant/role via an authenticated, authorized backend API,
  validates source + audits, and uses IAM administrative APIs per policy.
~~~

**Audit all app clients in the same user pool**, not just the primary one. A forgotten test client with broad write permissions can alter attributes that production clients rely on for decisions.

### 5.4. Attribute Read Permissions and ID Token Claims

Cognito can include readable standard/custom attributes in the **ID token** depending on flow, scopes, and configuration; `GetUser` returns profile fields per the app client's permissions. Do not use the `ID token` as a container to ship the entire profile, because:

- Tokens travel through clients and may end up in logs if mishandled;
- Tokens have lifetimes, so subsequent attribute/group updates do not automatically update already-issued tokens;
- Can PII in a JWT be read by a holder even if the payload is encoded? **Signed JWTs are not typically encrypted**, so the payload can be base64url-decoded;
- Attribute read permissions differ from permissions to call business APIs.

When full profile data is needed, consider an authorized backend `/me` endpoint returning only what the UI requires.

## 6. Cognito Groups: Roles, Membership, and Precedence

### 6.1. What Problem Do Groups Solve?

A group is a collection of user pool users, for example:

~~~text
students
teachers
content-reviewers
school-admins
support-agents
~~~

Each user can belong to **multiple groups**. Group membership can appear in the `cognito:groups` claim of both **access tokens** and **ID tokens**, depending on token type/configuration, and applications can use it after verifying the token.

~~~mermaid
flowchart LR
    U[User sub=abc] --> G1[Group students]
    U --> G2[Group teachers]
    G1 --> TOK[JWT cognito:groups]
    G2 --> TOK
    TOK --> API[Backend authz]
    API --> DB[(Course membership database)]
    DB --> DEC[Per-resource decision]
~~~

Groups are a **coarse-grained** classification mechanism. Do not create a group for every row in a gradebook or a group for every course in a large system if authorization depends on millions of relationships. Fine-grained relationships belong in business data and must be checked by the backend.

### 6.2. Group Names and Authorization Policy

Example:

| Group | Broad Permission Suggested | Still Must Verify |
|---|---|---|
| `students` | View enrolled courses | Student has a valid enrollment |
| `teachers` | Manage lessons for assigned classes | Teacher is assigned to that course/tenant |
| `content-reviewers` | Review content within assigned scope | Content item and workflow state |
| `school-admins` | Administer a specific tenant | Tenant ID, active role, audit |
| `support-agents` | Ticket-scoped support access | Access reason, ticket scope, PII redaction |

Never check only `"school-admins" in cognito:groups` and allow editing every tenant. In multi-tenant apps, high-privilege groups still require **tenant boundaries** and backend permission verification.

### 6.3. Precedence and Preferred IAM Role

When a user belongs to multiple groups, groups can carry **`Precedence`** and `RoleArn` to drive IAM role selection in **Identity Pool role mapping**:

- `Precedence=0` has the highest priority; **lower** numbers take precedence over higher numbers.
- The group with the lowest precedence number typically determines the `cognito:preferred_role` claim in the **ID token** when an eligible role is attached.
- If multiple groups share the same precedence and the same role ARN, that role can be selected.
- If they share the same precedence but have **different role ARNs**, `cognito:preferred_role` may not be set; Identity Pool handles this via `AmbiguousRoleResolution`/`CustomRoleArn`.
- `cognito:roles` lists IAM roles associated with groups—**it does not mean the app backend itself is authorized by IAM**.
- Groups **do not support nesting**; group counts are subject to service quotas.

Example:

~~~text
User belongs to:
  students:    precedence=20, role=arn:...:role/StudentFilesRole
  teachers:    precedence=10, role=arn:...:role/TeacherFilesRole

Expected preferred role:
  TeacherFilesRole (by priority 10)
~~~

**Do not use group precedence as an application permission hierarchy**. Precedence primarily guides IAM role selection when using Cognito Identity Pools. In backend APIs, handle group membership with **dedicated policy logic**, such as deny-by-default, role hierarchies, and tenant-scoped permissions.

### 6.4. When Not to Attach IAM Roles to Groups

If all operations on AWS resources go through a **backend on Lambda/EC2/ECS**—where the backend has **its own execution role** and end users never call AWS APIs directly—you can use groups purely for application roles **without attaching an IAM role to each group**.

Only when the app needs to issue direct temporary AWS credentials via **Identity Pool** should you evaluate `RoleArn`, role mappings, IAM trust policies, principal tags, and resource permissions. That is a different model from REST API authorization.

### 6.5. Membership Management Is a Privileged Operation

**Never allow regular users to add themselves to admin groups.** Operations like `AdminAddUserToGroup` are administrative APIs and must be executed by an authenticated and business-authorized IAM principal/backend.

A workflow for adding a teacher:

1. The school verifies identity and contract.
2. Admin staff confirms the exact `sub`/user profile.
3. Admin backend verifies the operator's permissions.
4. Admin API adds the `teachers` group and logs an audit entry.
5. Backend updates fine-grained assignments per course.
6. The user signs in/refreshes tokens per policy to obtain updated claims, and the backend still cross-checks authoritative permission data.

## 7. Designing App Clients by Application Type

### 7.1. Public Clients vs. Confidential Clients

| Type | Example | Client Secret? | Typically Recommended OAuth Flow |
|---|---|---|---|
| **Public client** | Browser SPA | **No** | Authorization Code + **PKCE** |
| **Public client** | iOS/Android app | **No** | Authorization Code + PKCE, system browser |
| **Confidential client** | Server-rendered web app/BFF | Optional, kept server-side | Authorization Code, client auth at token endpoint |
| **Confidential client** | Machine-to-machine backend | **Yes** | `client_credentials` + custom scopes |
| **Backend proxy/BFF** | SPA calling BFF, BFF holds session | BFF can use a confidential client | Code flow, HttpOnly/Secure/SameSite cookies per design |

**Client ID is not a secret**; it is allowed to appear in client code. **Client secret is confidential**—never embed it in JS bundles, mobile APK/IPAs, or public repositories.

### 7.2. One User Pool, Multiple Clients

Example:

~~~text
User Pool: school-users
├── student-spa (public)
│   ├── Code + PKCE
│   ├── Callback: https://learn.example.com/auth/callback
│   └── Scopes: openid email profile school-api/courses.read
├── teacher-web (confidential BFF)
│   ├── Code flow / server-side secret
│   ├── Callback: https://teacher.example.com/oauth/callback
│   └── Scopes: openid email school-api/grades.write
└── report-service (confidential M2M)
    ├── client_credentials
    └── Scope: school-api/reports.generate
~~~

Separating app clients lets you tailor callback policies, token TTLs, auth flows, and attribute permissions per application. However, **separate clients do not provide absolute tenant isolation** if they share a user pool and API authorization lacks business constraints.

### 7.3. Settings to Decide During Design

| Setting | Design Decision | Risk If Misconfigured |
|---|---|---|
| `ClientName` | Environment + application + client type | Hard to distinguish prod/dev |
| `GenerateSecret` | Only for confidential clients per flow | Secret leaked in SPA/mobile or M2M blocked |
| `AllowedOAuthFlowsUserPoolClient` | Enable OAuth flows for user pool client | OAuth configuration inactive |
| `AllowedOAuthFlows` | `code`, `client_credentials`, etc. as needed | Unnecessary implicit flow enabled |
| `AllowedOAuthScopes` | Least privilege for the app | Tokens request overly broad scopes or miss needed ones |
| `CallbackURLs` | Exact HTTPS redirect URIs | Open redirect/code leakage/invalid redirect |
| `LogoutURLs` | Exact post-logout paths | Misdirection or redirect abuse |
| `SupportedIdentityProviders` | Permitted Cognito and IdPs | Allowing sign-in from unintended IdPs |
| `ReadAttributes` / `WriteAttributes` | Profile fields app can view/edit | PII exposure or privilege escalation |
| `ExplicitAuthFlows` | Direct API authentication flows | Leaving unnecessary password-based flows open |
| Token validity and refresh rotation | Session duration, re-auth, revocation | Tokens live too long or app refresh breaks |
| `PreventUserExistenceErrors` | Reduce leaking whether users exist | User enumeration via sign-in errors |

Exact values, TTL units, callback URL limits, and client-secret management features are updated by AWS; check API/docs for your current Region and product tier.

### 7.4. Client Secrets and Rotation

Per current AWS documentation, confidential app clients support **client secret rotation** mechanisms, including maintaining multiple secrets during a transition period or integrating with Secrets Manager where supported.

For operational code:

1. Never hardcode a client secret.
2. If the server needs a secret, store it in **Secrets Manager** or an organizational vault.
3. Read/cache the secret per policy and support refreshing after rotation.
4. Rotate in a test environment and confirm token exchange works before production.
5. Do not assume toggling `GenerateSecret` on an existing app client is trivial; design public/confidential types upfront.

**Distinguish client secret rotation from refresh token rotation**: one governs server application credentials, while the other governs user login token lifecycles.

## 8. OAuth 2.0/OIDC: Choosing Flows and Scopes per App Client

### 8.1. Authorization Code + PKCE for SPA/Mobile

~~~mermaid
sequenceDiagram
    participant B as Browser / Mobile
    participant APP as App client
    participant C as Cognito managed login
    participant API as Backend API
    B->>APP: User clicks Sign In
    APP->>APP: Generate state, nonce, code_verifier + code_challenge
    APP->>C: /oauth2/authorize (code, PKCE, scopes, redirect_uri)
    C->>B: Sign in + MFA / federated IdP
    C-->>APP: Redirect to callback with authorization code + state
    APP->>APP: Verify state
    APP->>C: /oauth2/token with code_verifier
    C-->>APP: ID + access + refresh tokens if granted
    APP->>API: Authorization Bearer access_token
    API->>API: Verify JWT + scope/group/resource permissions
~~~

For **public client** SPAs/mobile apps, use `Authorization Code + PKCE` instead of implicit grant. **PKCE does not replace state and nonce**; use a reputable OIDC library to handle CSRF protection, token substitution prevention, and related checks.

**Callback URLs** must be registered with exact values for the client. Use HTTPS for production, with valid exceptions for localhost during development per Cognito rules. Never use broad wildcard callback URLs or uncontrolled redirects.

### 8.2. OAuth Scopes Differ from Group Names

| Concept | Example | Effect |
|---|---|---|
| OIDC scope | `openid` | Requests OIDC sign-in / ID token |
| OIDC scope | `email`, `profile` | Requests corresponding claims/profile per permissions |
| Cognito scope | `aws.cognito.signin.user.admin` | Allows self-service user pool operations per Cognito rules |
| Custom API scope | `school-api/courses.read` | Lets the API check read-capability permission |
| Custom API scope | `school-api/grades.write` | Lets the API check write-capability permission |
| Cognito group | `teachers` | Classifies users in the user pool |
| Business policy | "Teacher A may grade class 123" | Checks a specific resource |

**`scope`** typically lives in the **access token**. **`cognito:groups`** can appear in both access and ID tokens, but it is not an OAuth scope. The resource server must validate **signature/issuer/expiry/token_use/client/appropriate audience**, and only then use scopes/groups as part of authorization logic.

### 8.3. Resource Servers and Custom Scopes

In Cognito, you can define a resource server identifier such as `school-api`, along with scopes:

~~~text
Resource server identifier: school-api
Scope names:
  courses.read
  courses.write
  grades.read
  grades.write
  reports.generate

Token scope values:
  school-api/courses.read
  school-api/grades.write
~~~

These represent **API capability permissions**, not row-level data permissions. For instance, an access token with `school-api/grades.write` does not mean it can modify all grade records; the backend still checks course assignment.

### 8.4. Machine-to-Machine Using client_credentials

An automated report-generation service can use a **confidential app client** and `client_credentials` to request an **access token** with custom scopes. There is no interactive user and typically **no user ID token** in this flow.

Secure design:

- Keep the client secret in a server/vault and rotate on schedule.
- Grant only the custom scopes the service requires.
- Have the API distinguish a **machine principal** from a human user.
- Log/audit by client/service; do not spoof a fake `admin` user.
- Apply appropriate rate limits and quotas; never share one client secret across unrelated independent services.

### 8.5. Refresh Token Rotation and Login Sessions

Cognito supports **refresh token rotation**. When enabled on an app client, each successful refresh can issue a new refresh token per service behavior; the app must store and revoke tokens securely.

Important: an app client with refresh token rotation enabled **cannot continue using the `REFRESH_TOKEN_AUTH` auth flow** as when rotation is disabled; it must use the token endpoint `refresh_token` grant or the `GetTokensFromRefreshToken` API per supported capabilities.

If a device loses its refresh token or refresh fails, the app must handle re-authentication or session revocation—never weaken security by making token lifetimes infinite.

## 9. ID Token, Access Token, Refresh Token, and Group Claims

### 9.1. Purpose of Each Token

| Token | Consumer | What It Contains | Use to Call Business APIs? |
|---|---|---|---|
| **ID token** | OIDC client to know the user authenticated | `sub`, `aud`, profile claims, and `token_use=id` | **Should not** be used as a bearer authorization token for APIs |
| **Access token** | Resource server/API | `scope`, `client_id`, `sub`, `token_use=access`, and relevant claims | **Yes**, after full verification |
| **Refresh token** | Client/session to obtain new tokens | Opaque token per Cognito mechanism | Never send to resource servers/business APIs |

Standard JWTs are **signed**, not **encrypted** by default. Never place passwords, downstream tokens, payment secrets, or excessive personal data into custom claims.

### 9.2. Simplified Example ID Token Payload

~~~json
{
  "iss": "https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_EXAMPLE",
  "sub": "cognito-sub-example",
  "aud": "example-public-client-id",
  "token_use": "id",
  "email": "learner@example.test",
  "email_verified": true,
  "custom:tenantId": "school-42",
  "cognito:groups": ["students"],
  "iat": 1795140000,
  "exp": 1795143600
}
~~~

**Mock data, not a validly signed token.** Actual claims depend on scopes, app client attribute permissions, token customization, groups, and IdP configuration. Do not assume every custom attribute always appears in the ID token.

### 9.3. Simplified Example Access Token Payload

~~~json
{
  "iss": "https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_EXAMPLE",
  "sub": "cognito-sub-example",
  "client_id": "example-public-client-id",
  "token_use": "access",
  "scope": "openid school-api/courses.read",
  "cognito:groups": ["students"],
  "iat": 1795140000,
  "exp": 1795143600
}
~~~

This example has no `aud` because Cognito access tokens commonly use `client_id` to identify the app client. With features supporting **resource binding**, an access token may contain `aud` set to the resource server URL. Therefore, APIs must check **audience/client_id according to exact token type and configuration**.

### 9.4. Backend JWT Verification Steps

~~~text
1. Fetch OIDC discovery/JWKS from the trusted Cognito User Pool issuer.
2. Verify the JWT signature using the public key matching kid.
3. Verify iss matches the configured user pool.
4. Verify token_use=access for business APIs.
5. Verify client_id and/or aud per flow/resource binding.
6. Verify exp, nbf/iat where applicable, and reasonable clock skew.
7. Check API scopes and group claims if used by policy.
8. Check user/tenant/resource ownership in the backend.
9. Enforce revocation/session policy if required by the application.
10. Audit critical decisions; never log raw JWTs verbatim.
~~~

Never simply `Base64 decode` a JWT and trust its claims; **without signature verification, a client-forged payload can look identical to a real token**. Handle JWKS key rotation and cache the key set appropriately; use a well-maintained JWT/OIDC library.

### 9.5. Group Changes Do Not Instantly Void Old Tokens

When a staff member is removed from `school-admins`, previously issued tokens may continue carrying the old `cognito:groups` until expiration or until session/revocation policies take effect per design. For sensitive permissions:

- Keep access token TTLs reasonably short.
- Implement token revocation/session management per product needs.
- Have the backend check **current permission state** from a controlled database/cache when near-instant propagation is required.
- Never trust an old JWT indefinitely solely because its signature is valid.

## 10. Federation: Attribute Mapping and Trust Boundaries

### 10.1. User Pool Can Accept External IdPs

A user pool can federate supported identity sources such as Google/OIDC/SAML. When a user signs in via an IdP, Cognito can map attributes from the IdP to the user pool profile.

~~~mermaid
flowchart LR
    U[User] --> LOGIN[Cognito managed login]
    LOGIN --> IDP[External OIDC/SAML IdP]
    IDP -->|Verified claims| COG[(Cognito User Pool)]
    COG --> MAP[Attribute mappings]
    MAP --> ATTR[Standard/custom user attributes]
    COG --> APP[App client tokens]
    APP --> API[Backend authorization]
~~~

A mapping like `email → email` or `department → custom:department` can work, **but you must evaluate source trustworthiness, write permissions, and mutability**.

### 10.2. Rules for Mapped Attributes

- The target attribute must be **mutable** if the IdP can update its value at sign-in.
- **The relevant app client must have WriteAttributes** for the mapped attribute; otherwise sign-in may fail when Cognito attempts to update it.
- Mapping into an **immutable custom attribute** is a common design mistake; AWS may reject the login when the IdP sends a value requiring a write.
- Do not use an external IdP claim that end users can edit themselves as a condition for granting administrative privileges.
- For tenants/organizations, build a **backend/admin provisioning verification workflow**; never use an unverified `email domain` to grant high privilege.
- Design **account linking** to prevent duplicate users, account takeover, or erroneous merges just because two profiles share an email address.

### 10.3. Example Mapping Table

| IdP Claim | Cognito Attribute | Mutable? | Use for Authz? |
|---|---|---|---|
| `email` | `email` | Per configuration | Contact info only; check `email_verified` |
| `given_name` | `given_name` | Usually yes | No |
| `locale` | `locale` | Yes | No |
| `department` | `custom:department` | **Yes** if mapped on every login | Only after verifying the authoritative admin source |
| IdP-controlled `tenantId` | `custom:tenantId` | Yes if sync is needed | Only if IdP trust contract/authority is clear |
| User-editable `isSuperAdmin` | **Do not map to permissions** | Not applicable | **No** |

Federation links **identity**—it does not automatically turn every external claim into internal application permissions.

## 11. Multi-App and Multi-Tenant Design

### 11.1. Shared User Pool or Separate Pools?

| Design | Pros | Risks / Trade-offs |
|---|---|---|
| One user pool for multiple app clients | Single profile, multiple apps, shared auth | Must tightly govern read/write permissions; all clients share one directory |
| Separate pools for dev/staging/prod | Isolates test data from production | More configs, deployments, and cost overhead to manage |
| Dedicated pool per large enterprise tenant when high isolation is needed | Clear configuration/identity boundary | Quota, user management, federation, and operational complexity |
| Shared pool + tenant ID in DB and backend policies | Scales well for many small tenants | Tenant-level authorization must be strictly implemented and tested |

No single model fits every SaaS. Weigh compliance, user federation, email domains, data sovereignty, number of tenants, IAM scope, and budget.

### 11.2. Separating Identity ID from Domain Entities

A simple model in the application database:

~~~sql
CREATE TABLE app_user (
    internal_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cognito_issuer VARCHAR(256) NOT NULL,
    cognito_sub VARCHAR(256) NOT NULL,
    display_name VARCHAR(200),
    UNIQUE (cognito_issuer, cognito_sub)
);

CREATE TABLE tenant_membership (
    user_id BIGINT NOT NULL REFERENCES app_user(internal_id),
    tenant_id VARCHAR(64) NOT NULL,
    role_code VARCHAR(64) NOT NULL,
    PRIMARY KEY (user_id, tenant_id, role_code)
);
~~~

This schema is illustrative; SQL syntax varies by RDBMS and business model. **Do not use email as the key** in `tenant_membership`. When a user changes their email, tenant relationships must not break or silently shift.

### 11.3. Example Tenant-Scoped API Authorization

~~~text
POST /tenants/school-42/courses/123/grades

Backend:
  1. Verify access token (iss, signature, token_use, client_id/aud, exp).
  2. Check grades.write scope if the API uses OAuth scopes.
  3. Extract (issuer, sub) and map to internal app_user.
  4. Verify user is a teacher/admin of tenant school-42.
  5. Verify course 123 belongs to school-42.
  6. Verify teacher is assigned to grade course 123.
  7. Execute update + audit inside a transaction.
~~~

Even if the token carries `cognito:groups=["teachers"]` and `custom:tenantId="school-42"`, steps 4–6 still require server-side logic. A user may belong to multiple tenants; storing a single `tenantId` in Cognito is often insufficient.

## 12. Security Policy When Creating App Clients

### 12.1. Checklist by Application Type

| Control | SPA/Mobile | Server Web/BFF | M2M |
|---|---|---|---|
| Client secret | No | Optional, server-only | Yes |
| OAuth flow | Code + PKCE | Code flow, server session | client_credentials |
| Callback URLs | Exact HTTPS, localhost for dev when appropriate | Exact HTTPS | No user callbacks |
| Scopes | Minimal for UI/API | Per server functionality | Minimal custom API scopes |
| Read/WriteAttributes | Explicit, minimal | Explicit per backend business needs | Usually no user profile needed |
| Refresh token | Store securely, rotate if appropriate | Server-side/secure session | No user refresh token in client_credentials flow |
| MFA | Per user risk | Per user/admin risk | Human MFA not directly applicable |
| Token validation | API verifies independently | BFF/API verifies | API verifies client and scope |
| Logging | No tokens/PII | Redact headers/secrets | Never log client secrets |

### 12.2. MFA, Sign-Up, and User Enumeration

To protect the user directory, consider:

- MFA/passkey/password policies matching Cognito capabilities and risk level;
- Email/phone verification and recovery mechanisms;
- CAPTCHA/bot detection and threat protection per feature tier where appropriate;
- `PreventUserExistenceErrors` and sign-in error messages that do not reveal account existence;
- Rate limiting on sign-ups and password attempts;
- CloudTrail/metrics and alerts on administrative operations;
- Account lifecycle: disabled, deleted, archived, and reactivated states per compliance rules.

**Never assume Cognito MFA protects every sensitive operation**. Changing bank details, granting admin privileges, or exporting data may require **step-up authentication** and additional auditing.

### 12.3. Secrets and Token Storage

- Client secrets belong on the backend/Secrets Manager, never in HTML or JavaScript.
- Access tokens/ID tokens must never be written to analytics, URL query strings, or logs.
- For browsers, evaluate BFF + HttpOnly/Secure/SameSite cookies or OIDC SDK-supported mechanisms; avoid long-lived token storage easily accessed via XSS.
- Use TLS, Content Security Policy, security headers, and appropriate CORS rules.
- Validate callback URLs to prevent code injection, redirect abuse, and CSRF.
- Plan for logout, revocation, and token TTLs.
- Never treat `client_id` as a secret proof identifying the caller; public client IDs are public information.

## 13. Lab 1 — Inspecting a User Pool with AWS CLI (Read-Only)

> By default, this lab **does not create users, groups, or app clients**, does not issue tokens, and does not read passwords/client secrets. Use AWS CLI v2 and a **sandbox** IAM profile with Cognito read permissions. All IDs are placeholders. If your organization restricts configuration disclosure, store outputs only in authorized environments.

### 13.1. Verify Account and Region

Example in Bash/AWS CloudShell:

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1
REGION=ap-southeast-1

aws sts get-caller-identity --profile "$AWS_PROFILE"
~~~

If using CloudShell with pre-existing credentials and without an `aws-lab-dev` profile, omit the export and `--profile` flags. Never use a production account just for learning.

### 13.2. List User Pools

~~~bash
aws cognito-idp list-user-pools \
  --max-results 20 \
  --region "$REGION" \
  --query 'UserPools[].{Id:Id,Name:Name,LastModifiedDate:LastModifiedDate}' \
  --output table
~~~

This API is paginated. If only the first page appears, use the AWS CLI next token/paginator to continue; do not assume the account only has 20 pools.

### 13.3. Read Pool Schema

~~~bash
USER_POOL_ID=ap-southeast-1_EXAMPLE

aws cognito-idp describe-user-pool \
  --user-pool-id "$USER_POOL_ID" \
  --region "$REGION" \
  --query 'UserPool.{Id:Id,Name:Name,UsernameAttributes:UsernameAttributes,AliasAttributes:AliasAttributes,AutoVerifiedAttributes:AutoVerifiedAttributes,UsernameConfiguration:UsernameConfiguration,SchemaAttributes:SchemaAttributes}' \
  --output json
~~~

Observe:

- `Required` and `Mutable` on standard/custom attributes;
- `AttributeDataType` and `StringAttributeConstraints`;
- `UsernameAttributes` vs. `AliasAttributes`;
- `AutoVerifiedAttributes` for email/phone if configured;
- custom attributes prefixed with `custom:`;
- which schema settings cannot easily change after pool creation.

**Do not run `list-users` or `admin-get-user` to extract personal data** without a legitimate purpose and authorization; this lab only needs the schema, not a real student roster.

### 13.4. List Groups

~~~bash
aws cognito-idp list-groups \
  --user-pool-id "$USER_POOL_ID" \
  --region "$REGION" \
  --query 'Groups[].{Name:GroupName,Precedence:Precedence,RoleArn:RoleArn}' \
  --output table
~~~

Group names and IAM `RoleArn` values can be **internal metadata**; store them only in authorized lab notes. Never list real members or share the list externally. If a group has no `RoleArn`, that is **not an error** when groups are only used for application roles.

### 13.5. List App Clients

~~~bash
aws cognito-idp list-user-pool-clients \
  --user-pool-id "$USER_POOL_ID" \
  --max-results 20 \
  --region "$REGION" \
  --query 'UserPoolClients[].{ClientName:ClientName,ClientId:ClientId}' \
  --output table
~~~

Note the **authorized** client IDs and compare names to see whether SPA/mobile/admin/M2M clients are separated.

### 13.6. Describe an App Client Without Exposing ClientSecret

**Very important:** `DescribeUserPoolClient` can return **`ClientSecret`** for confidential app clients. Therefore, **do not run `--output json` on the full response** and do not paste raw logs. Query only fields that do not contain secrets:

~~~bash
CLIENT_ID=exampleclientid

aws cognito-idp describe-user-pool-client \
  --user-pool-id "$USER_POOL_ID" \
  --client-id "$CLIENT_ID" \
  --region "$REGION" \
  --query 'UserPoolClient.{Name:ClientName,Id:ClientId,AllowedOAuthFlows:AllowedOAuthFlows,AllowedOAuthScopes:AllowedOAuthScopes,CallbackURLs:CallbackURLs,LogoutURLs:LogoutURLs,ReadAttributes:ReadAttributes,WriteAttributes:WriteAttributes,ExplicitAuthFlows:ExplicitAuthFlows,AccessTokenValidity:AccessTokenValidity,IdTokenValidity:IdTokenValidity,RefreshTokenValidity:RefreshTokenValidity,RefreshTokenRotation:RefreshTokenRotation,TokenValidityUnits:TokenValidityUnits,PreventUserExistenceErrors:PreventUserExistenceErrors}' \
  --output json
~~~

**Interpretation:**

- Missing `ReadAttributes` or `WriteAttributes` may mean the app uses **default permissions**, not "no permissions".
- Seeing a callback URL pointing to staging in a production app client warrants a change ticket after review.
- `AllowedOAuthFlows` and `AllowedOAuthScopes` must reflect the client type and what the API actually requires.
- If a client is an SPA yet still has a secret configured, assess the **secret exposure risk** and plan a client replacement.
- If an auth flow or token setting is missing or differs from expectations, check current AWS docs/version and actual configuration before drawing conclusions.

### 13.7. List Resource Servers and OAuth Scopes

~~~bash
aws cognito-idp list-resource-servers \
  --user-pool-id "$USER_POOL_ID" \
  --max-results 20 \
  --region "$REGION" \
  --query 'ResourceServers[].{Name:Name,Identifier:Identifier,Scopes:Scopes}' \
  --output json
~~~

Cross-check custom scope identifiers against each app client's `AllowedOAuthScopes`. A scope existing on a resource server **does not mean every client is allowed to request** that scope.

## 14. Lab 2 — Designing JSON and Controlled Changes

> This section provides **example configurations for review only**. Commands that create/modify Cognito user pools, groups, and app clients can directly impact user accounts and sign-in. **Do not execute in production** without approval, appropriate IAM permissions, a rollback plan, and test data. Not all schema changes are reversible.

### 14.1. Schema Design Sample

Suppose the application needs `custom:tenantId` to display the managed tenant. A partial schema at pool creation:

~~~json
{
  "Schema": [
    {
      "Name": "tenantId",
      "AttributeDataType": "String",
      "DeveloperOnlyAttribute": false,
      "Mutable": false,
      "Required": false,
      "StringAttributeConstraints": {
        "MinLength": "1",
        "MaxLength": "64"
      }
    }
  ]
}
~~~

**Do not use this sample as an entire `CreateUserPool` request**; the API requires or accepts many other settings. If tenant membership needs to change over time, an immutable `tenantId` may be the wrong choice; consider the business database or a mutable admin-only writable attribute.

### 14.2. Group Configuration Sample

Example groups:

~~~json
[
  {"GroupName": "students", "Precedence": 30},
  {"GroupName": "teachers", "Precedence": 20},
  {"GroupName": "content-reviewers", "Precedence": 10},
  {"GroupName": "school-admins", "Precedence": 0}
]
~~~

This illustrates **group precedence**, not verbatim CLI input. These precedences **do not define REST API authorization**; you still need backend policies. If you do not use an Identity Pool, you may **not need to set precedence**.

Mutating command, for sandbox use only when permitted:

~~~bash
# IMPACTING - do not run on shared or production pools
aws cognito-idp create-group \
  --user-pool-id ap-southeast-1_EXAMPLE \
  --group-name training-students \
  --description "Sandbox student group" \
  --precedence 30 \
  --region ap-southeast-1
~~~

To clean up a test group after confirming no users/shared dependencies remain, use `delete-group` per approved procedures; **never delete real production groups**.

### 14.3. App Client for SPA (Illustrative JSON)

~~~json
{
  "UserPoolId": "ap-southeast-1_EXAMPLE",
  "ClientName": "training-student-spa",
  "GenerateSecret": false,
  "AllowedOAuthFlowsUserPoolClient": true,
  "AllowedOAuthFlows": ["code"],
  "AllowedOAuthScopes": [
    "openid",
    "email",
    "profile",
    "school-api/courses.read"
  ],
  "CallbackURLs": [
    "https://learn.example.com/auth/callback"
  ],
  "LogoutURLs": [
    "https://learn.example.com/"
  ],
  "SupportedIdentityProviders": ["COGNITO"],
  "ReadAttributes": [
    "email",
    "email_verified",
    "given_name",
    "custom:tenantId"
  ],
  "WriteAttributes": [
    "email",
    "given_name"
  ],
  "PreventUserExistenceErrors": "ENABLED"
}
~~~

Verify that the `school-api` resource server and `courses.read` scope already exist. `ReadAttributes`/`WriteAttributes` must align with required standard attributes, user registration, federation, and AWS constraints; **this sample illustrates intent**, without guaranteeing verbatim acceptance across every pool/flow.

### 14.4. App Client for M2M (Illustrative JSON)

~~~json
{
  "UserPoolId": "ap-southeast-1_EXAMPLE",
  "ClientName": "training-report-job",
  "GenerateSecret": true,
  "AllowedOAuthFlowsUserPoolClient": true,
  "AllowedOAuthFlows": ["client_credentials"],
  "AllowedOAuthScopes": ["school-api/reports.generate"],
  "SupportedIdentityProviders": ["COGNITO"]
}
~~~

M2M has no user login/ID token; do not configure OIDC `openid/email` as if there were a human user. The client secret must be stored in a backend vault and support rotation; never print create-client request/response payloads to public CI logs since they may contain `ClientSecret`.

### 14.5. API Verification Contract After Creating App Clients

1. Verify the SPA only redirects to permitted callback URLs.
2. Verify Authorization Code + PKCE; no client secret is sent from the browser.
3. Verify the access token includes `school-api/courses.read` when requested.
4. Verify the access token does not include `grades.write` if not granted.
5. Test self-service update of an allowed attribute like `given_name`.
6. Attempting to modify `custom:tenantId` from the SPA must be rejected.
7. A user outside `teachers` calling the grading API must be rejected by the backend.
8. A user in `teachers` who is not assigned to the specific course must still be rejected.
9. Test key rotation/JWKS refresh and token expiration/revocation.
10. Log test evidence **without recording tokens, passwords, real emails, or client secrets**.

## 15. Operations, Monitoring, and Cost

### 15.1. Change Lifecycle

A user pool/app client change affects multiple applications:

~~~text
Design review
   ↓
Threat model + data classification
   ↓
Schema / groups / app-client policy as code
   ↓
Sandbox integration tests
   ↓
Staging with federated IdP and real-world auth flows
   ↓
Production rollout + monitoring
   ↓
Rollback/revoke plan and audit
~~~

**Hard-to-change** settings such as sign-in identifiers and custom attribute schemas must be thoroughly reviewed before creating a user pool. Changes to client OAuth URLs/scopes/attribute permissions need a migration plan for live apps.

### 15.2. Signals to Monitor

| Signal | Meaning | Response |
|---|---|---|
| Sign-up/sign-in successes and failures | Login experience and config errors | Classify password, MFA, callback, IdP issues |
| Token endpoint errors | Code/PKCE/client secret/scope errors | Inspect flow and client config |
| User existence probing | Enumeration attempts | Rate limiting, generic errors, threat protection |
| MFA failure/lockout | Risky failed logins | Secure recovery workflow |
| Group membership changes | Potential access level change | Audit `AdminAddUserToGroup`/`AdminRemoveUserFromGroup` |
| App client config changes | Potential OAuth scope/callback/read-write change | CloudTrail and config diff |
| IdP federation failures | Attribute mapping, issuer, metadata, write permission | Mapped attributes and login logs |
| Backend 401/403 | Invalid token or denied API/tenant access | Separate authn vs. authz, never log tokens |
| Token refresh failures | Session renewal/rotation or wrong client secret | SDK/rotation/revocation/expiry |
| Cognito/API costs | MAU, M2M token requests, features/tiers, and SMS/email | Budgets, pricing calculator, quotas |

Cognito uses a **pricing model based on user pools/feature plans, monthly active users (MAU), M2M flows, and related components** depending on account/Region. Services such as SNS/SMS, SES, Lambda triggers, CloudWatch logs, and AWS WAF can incur separate charges. Never finalize a budget using outdated unit rates; check current Cognito pricing.

### 15.3. Administrative IAM and Data Protection

- IAM principals calling `cognito-idp:DescribeUserPool`/`ListGroups` are separate from end users in the pool.
- Restrict permissions to create/delete groups, update clients, manage IdP links, and modify user profiles.
- Use IAM Identity Center/temporary roles rather than long-term access keys whenever safer alternatives exist.
- Never grant `cognito-idp:*` on all resources to a pipeline that only needs to read configuration.
- Review CloudTrail for IAM/management actions; enforce log retention and alerts per requirements.
- User attribute data can be PII; restrict `ListUsers` exports and token payload storage.
- Design account deletion, business data sync/backup, and privacy policies per applicable regulations.

## 16. Troubleshooting Common Errors

| Symptom | Likely Cause | How to Check |
|---|---|---|
| User signed in yet backend returns 401 | Invalid token signature/issuer/expiry/client | JWKS, `iss`, `exp`, `token_use`, client IDs |
| API returns 403 despite valid token | Missing scope/group/tenant/resource permission | Backend authorization—do not weaken token validation |
| SPA prompted for a client secret | Confidential client created for browser | Create a public app client without secret; migrate |
| OAuth redirect reports invalid `redirect_uri` | Callback URL mismatches config | Match exact scheme/host/path and client ID |
| Code exchange reports `invalid_grant` | Expired/reused code, PKCE/state mismatch | Authorization flow and code_verifier |
| Access token lacks custom scope | App client not granted scope or did not request it | Resource server, `AllowedOAuthScopes`, and request |
| ID token lacks `custom:tenantId` | App client lacks ReadAttributes or user has no value | Check config/attribute mapping without logging real tokens |
| User can edit tenant/role | Overly broad WriteAttributes on some app client | Audit all clients; remove write permission, review logs |
| Sending `email_verified=true` from client rejected | Self-editing verification flag disallowed by flow | Use verification flow or authorized admin API |
| Updating `custom:tenantId` reports immutable | Attribute created with `Mutable=false` | Cannot alter existing schema; plan migration |
| Federation sign-in fails during attribute mapping | Target attribute not mutable or app client not writable | IdP attribute mapping, WriteAttributes |
| Email sign-up reports `UsernameExistsException` | Sign-in identifier/uniqueness differs from expectation | Check `UsernameAttributes`/`AliasAttributes` |
| Email-formatted username rejected in alias pool | Pool uses email alias; username cannot match email format | Choose valid username or redesign pool |
| New group membership missing from token | Old JWT; refresh/sign-in hasn't issued new claims | Token lifecycle; verify authoritative permission store |
| `cognito:preferred_role` is empty | Multiple groups share precedence with different RoleArns | Review group precedence/IAM roles |
| Has `teachers` group yet still cannot edit class | Backend checks course assignment/tenant | Do not alter groups to bypass data ownership |
| `DescribeUserPoolClient` omits Read/WriteAttributes | Default permissions are active | Do not treat as deny-all; audit defaults and set least privilege |
| M2M receives no ID token | `client_credentials` has no user interaction | Use access token for APIs and custom scopes |
| Refresh fails after enabling rotation | Client still uses `REFRESH_TOKEN_AUTH` | Switch to token endpoint / GetTokensFromRefreshToken |
| Token payload exposes PII | Broad attribute permissions/claims | Reduce ReadAttributes, avoid PII in tokens/logs |
| User locked out due to MFA/IdP | Security policy, mapping, or account state | Follow recovery workflow; never disable MFA pool-wide |
| Unexpected quota or cost spike | Many clients/groups/MAUs/M2M tokens | Service Quotas, Cost Explorer, logs |

### 16.1. Investigation Runbook

~~~text
1. Verify AWS account, Region, user pool ID, and client ID.
2. Identify whether the failure is in sign-up, login, token exchange, token validation, or API authorization.
3. Compare sign-in identifiers, required/mutable attributes, and client type.
4. Inspect AllowedOAuthFlows, scopes, callbacks, and auth flows.
5. Inspect effective ReadAttributes/WriteAttributes including defaults.
6. If federated, inspect IdP mappings, mutability, and verified claims.
7. If group-based, inspect membership, precedence, and token freshness.
8. On the API side, verify iss/signature/aud-or-client_id/token_use/exp.
9. Check tenant/resource ownership and audit logs without logging raw JWTs.
10. Fix at the right layer, run negative tests, and roll out via sandbox/staging.
~~~

## 17. Case Study: Multi-Role Education Platform

### 17.1. Requirements

An online learning application has:

- **Student SPA** on `learn.example.com` and a mobile app.
- **Teacher portal** running through a backend-for-frontend.
- **School admin** authorized to invite teachers and manage classes for their own school.
- **Report worker** backend calling reporting APIs with no interactive user.
- A single user can be both a student and a teacher.
- Some teachers can belong to two different schools.
- An RDS database holds `teacher ↔ course ↔ tenant` relationships; S3 holds private documents.

Users must never be able to self-assign `school-admins` or change `tenantId` to view another school's data.

### 17.2. Recommended Design

| Component | Design | Why |
|---|---|---|
| User Pool | One pool for end-user apps, separate from dev/staging | Unified identity within the same environment |
| Stable identity | `(issuer, sub)` | Remains unchanged when email/display username changes |
| Standard attrs | `email`, `email_verified`, `given_name`, `family_name` | Only necessary data |
| Custom attrs | Minimal; optionally `custom:registrationSource` or tenant hint | Never turn tokens into a permissions database |
| Groups | `students`, `teachers`, `school-admins` | High-level roles, not per-course groups |
| App clients | Student SPA public, mobile public, Teacher BFF confidential, Report M2M confidential | Separates token flows/scopes/secret handling |
| OAuth scopes | `courses.read`, `grades.write`, `reports.generate` | Grants API capability permissions |
| Backend authorization | Checks school/class membership from RDS | Prevents cross-tenant access |
| Admin provisioning | IAM-protected/logged API with approval workflow | Prevents apps from adding users to groups directly |
| Secure delivery | HTTPS, PKCE, MFA for admins, token verification | Protects login sessions |
| Monitoring | CloudTrail, auth metrics, API 401/403, permission changes | Auditing and incident investigation |
| Costs | Track MAUs, M2M, SMS/email, Lambda triggers | Stay within budget |

### 17.3. Test Scenarios

1. Student with only `students` group attempts `POST /grades` → **403**.
2. Teacher in `teachers` attempts to edit an unassigned class → **403**.
3. School A admin attempts to modify a user from School B → **403**.
4. SPA client attempts `UpdateUserAttributes` to set `custom:tenantId=school-B` → **rejected**.
5. Teacher BFF reuses a refresh token from an unauthorized device → system enforces session/rotation/revocation policy.
6. M2M client attempts `grades.write` when granted only `reports.generate` → **403**.
7. External IdP sends a changed `custom:department` → sign-in succeeds only if the attribute is mutable and writable by the app client per mapping.
8. User changes email; course relationships keyed on `sub` remain intact.
9. User is removed from admin group; app handles stale tokens per freshness/authorization policy.
10. Passwords/client secrets/refresh tokens never appear in logs, query strings, or console screenshots.

### 17.4. Self-Check Questions

1. What is the primary difference in responsibility between User Pool and Identity Pool?
2. Why is `sub` better than email as a user key?
3. How does a username attribute differ from an email alias?
4. Can you arbitrarily switch the sign-in method from username to email on an existing user pool?
5. Why is an immutable `custom:isAdmin` that users can write at sign-up still insecure?
6. Can you delete a custom attribute after creating it? What does that imply for schema design?
7. How do an app client's `ReadAttributes` and `WriteAttributes` differ from `AllowedOAuthScopes`?
8. True or false: if `DescribeUserPoolClient` omits `WriteAttributes`, the client cannot write any attributes?
9. If a user belongs to both `students` and `teachers`, which groups appear in the token?
10. Between `Precedence=0` and `Precedence=20`, which takes priority when selecting an IAM role?
11. Can group precedence replace course-level backend authorization?
12. Can an SPA safely store a client secret inside its JavaScript bundle?
13. For SPA/mobile, why is Authorization Code + PKCE generally preferred over implicit?
14. Do ID tokens and access tokens serve the same purpose?
15. What must an API verify before reading `scope` and `cognito:groups`?
16. Does M2M `client_credentials` issue an ID token representing a real user?
17. What happens if an app client lacks write permission for a mapped IdP attribute?
18. Why cannot a custom attribute holding `tenantId` replace database membership tables?
19. How does refresh token rotation affect `REFRESH_TOKEN_AUTH`?
20. What data should never be placed in tokens or logs?

**Concise Answer Key:**

1. User Pool authenticates/issues tokens; Identity Pool grants temporary AWS credentials under configured conditions.
2. `sub` is stable within the pool, whereas email can change.
3. Username attributes use email/phone as the username itself; aliases add sign-in options over a fixed username per configuration.
4. No; usually requires creating a new pool and migrating.
5. Users can self-assign the wrong value right at account creation.
6. No; design a durable schema upfront or add a new attribute and migrate.
7. Attribute permissions control profile read/write; OAuth scopes govern API/OIDC access requests.
8. False; broad default permissions may be active.
9. Both can appear in `cognito:groups`.
10. `0` has higher priority.
11. No; the backend must verify tenant/resource ownership.
12. No; public clients cannot keep secrets reliably.
13. PKCE binds the code to the transacting client, mitigating code interception.
14. No; the ID token informs the client of identity, while the access token is for the resource server.
15. Signature, issuer, token_use, expiry, client ID/audience, and API-specific rules.
16. No; it represents a service principal.
17. Federated sign-in may fail when the attribute needs updating.
18. A user can hold multiple memberships, and policies change continuously.
19. You must use a compatible refresh mechanism instead of `REFRESH_TOKEN_AUTH`.
20. Passwords, client secrets, access/refresh tokens, and unnecessary personal data.

## 18. Pre-Production Checklist for Cognito

### User Pool and Attributes

- [ ] Selected User Pool/Identity Pool accurately for actual requirements.
- [ ] Internal identity key uses `sub` (paired with issuer when multi-pool), never email.
- [ ] Sign-in identifiers, alias options, case-sensitivity, and required attributes reviewed **before pool creation**.
- [ ] Standard attributes minimized, with email/phone verification and recovery planned.
- [ ] Custom attributes have durable names, types, mutability, and constraints.
- [ ] Custom attributes are not used to store secrets or complex business permission lists.
- [ ] Clients cannot self-write attributes used for authorization decisions.
- [ ] IdP attribute mappings have trusted sources, appropriate mutability, and write permissions.

### Groups and Authorization

- [ ] Groups represent broad roles, never replacing tenant/resource policies.
- [ ] Membership is modified only through audited administrative workflows.
- [ ] Understand that group precedence only governs preferred role selection with IAM/Identity Pool integration.
- [ ] Group claims/token freshness handled properly upon permission changes.
- [ ] API checks scopes, groups, and business data together on a deny-by-default basis.
- [ ] Negative tests cover cross-tenant access, broken object-level authorization, and self-escalation.

### App Clients and Tokens

- [ ] Separate app clients per application type (SPA/mobile/BFF/M2M).
- [ ] Public clients have no client secret; confidential client secrets live in a vault.
- [ ] OAuth Code + PKCE for public apps; exact, valid callback/logout URLs.
- [ ] `ReadAttributes`/`WriteAttributes` and OAuth scopes follow least privilege, with defaults audited.
- [ ] API verifies JWT signature/issuer/token_use/client/aud/exp, not just decoded payloads.
- [ ] M2M uses only required custom scopes and protects client credentials.
- [ ] Token TTL/refresh rotation/revocation/MFA designed for SLOs and risk.
- [ ] No tokens, client secrets, or unnecessary PII written to logs/analytics.

### Operations and Cost

- [ ] Tested sign-up/login/reset/MFA/federation and IdP attribute mapping.
- [ ] CloudTrail/metrics alert on group/app client changes and auth failures.
- [ ] Cognito administrative IAM scoped by environment and actual responsibilities.
- [ ] Migration/rollback plan ready for schema or app client changes.
- [ ] User data retention/deletion managed per applicable regulations.
- [ ] MAU/M2M/SMS/email/security feature costs estimated against current pricing.
- [ ] Plan in place to clean up sandbox user pools, clients, and resources **without deleting real data**.

**Expected Outcome:** Learners can design a Cognito User Pool with trusted-source attributes, groups representing application roles, and app clients with appropriate OAuth/attribute permissions; while verifying tokens, preventing cross-tenant authorization flaws, protecting personal data, and operating within budget.

## Official AWS Documentation

- [What is Amazon Cognito?](https://docs.aws.amazon.com/cognito/latest/developerguide/what-is-amazon-cognito.html)
- [Working with user attributes](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-attributes.html)
- [User pool sign-in with aliases and username attributes](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-attributes.html#user-pool-settings-aliases)
- [Adding groups to a user pool](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-user-groups.html)
- [Using role-based access control with Cognito Identity Pools](https://docs.aws.amazon.com/cognito/latest/developerguide/role-based-access-control.html)
- [Application-specific settings with app clients](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-client-apps.html)
- [Scopes, resource servers and M2M authorization](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-define-resource-servers.html)
- [Using tokens with user pools](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens.html)
- [Verifying JSON web tokens](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens-verifying-a-jwt.html)
- [Understanding ID tokens](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-id-token.html)
- [Understanding access tokens](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-access-token.html)
- [Refresh tokens and refresh token rotation](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-refresh-token.html)
- [Mapping IdP attributes to user pool profiles](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-specifying-attribute-mapping.html)
- [Updating user pool and app client configuration](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pool-updating.html)
- [Cognito user pools API reference](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/Welcome.html)
- [Cognito pricing](https://aws.amazon.com/cognito/pricing/)
- [AWS Pricing Calculator](https://calculator.aws/)

> **Usage Note:** All user pool IDs, app client IDs, account IDs, domain names, role names, token JSONs, and data in this lesson are illustrative for learning. Authentication features, client secret management, OAuth capabilities, service quotas, feature tiers, and AWS pricing are subject to change. Before creating or modifying production user pools/app clients, consult current AWS documentation, perform a security/PII review, test in a sandbox, and deploy through an approval process.
