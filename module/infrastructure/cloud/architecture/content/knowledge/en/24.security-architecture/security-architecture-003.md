# Identity Federation, SSO, and Least-Privilege Access

## 1. Why Does a Cloud Architecture Need Identity Federation?

A cloud system has many groups of callers: employees logging into the console, developers deploying applications, service accounts running pipelines, containers accessing object storage, functions reading queues, partners integrating with APIs, and end users signing into the product. If every place maintains its own accounts, passwords, or access keys, the organization struggles to track who is accessing what, revoke privileges when staff change roles, control sessions, and investigate anomalous activity.

**Identity federation** allows a system to trust identities verified by another Identity Provider (IdP) according to a configured protocol and trust relationship. **Single Sign-On (SSO)** allows users to authenticate once with the IdP and access multiple federated applications without re-entering credentials for each one. **Least privilege** restricts each user, application, or workload to only the exact permissions needed, within the exact scope and duration required.

These three mechanisms answer different questions:

- Federation: which system issues and verifies the identity? Under what conditions do the two parties trust each other?
- SSO: which authenticated session does the user use to sign into multiple applications?
- Least privilege: what actions may the verified identity perform, and on which resources?

SSO centralizes login session management, but does not automatically make every application secure. If a federated role grants Administrator permissions across the entire cloud account, SSO merely makes broad privileges more convenient to use. The architecture must pair identity federation with authorization, lifecycle management, auditing, session controls, and access review processes.

In the **CLOUD_ARCHITECTURE** module, this forms the security foundation spanning networking, compute, storage, databases, and data platforms. Identity should serve as the primary control boundary; IP addresses or placement inside a private network are only supplementary signals.

### Learning Objectives

After this lesson, you can:

1. Distinguish between identity, authentication, federation, SSO, provisioning, and authorization.
2. Choose SAML 2.0 or OpenID Connect (OIDC) for appropriate SSO scenarios.
3. Separate authentication from account and entitlement provisioning via SCIM/lifecycle workflows.
4. Design workforce and workload identities without embedding long-lived credentials.
5. Apply RBAC, ABAC, permission boundaries, and resource-level policies following least privilege.
6. Design sessions, MFA, role assumption, JIT access, and privilege revocation workflows.
7. Control trust across accounts, projects, tenants, services, and cloud providers.
8. Establish auditing, access reviews, and pre-deployment policy testing.

## 2. Layers of an Identity System

| Component | Role | Examples |
|---|---|---|
| **Subject / principal** | Entity requesting access | Employee, service, function, partner |
| **Identity Provider (IdP)** | Authenticates the subject and issues assertions/tokens | Enterprise IdP |
| **Service Provider / Relying Party** | Application trusting the IdP for authentication | Cloud console, internal portal |
| **Federation trust** | Rules defining which IdP/issuer is trusted | SAML metadata, OIDC issuer/JWKS, trust policy |
| **Credential / authenticator** | Proves the subject controls the account or key | Password, passkey, security key, certificate |
| **Provisioning system** | Creates, updates, and disables accounts/groups | HRIS, IAM governance, SCIM |
| **Authorization engine** | Decides which actions are permitted | IAM policy, RBAC, ABAC, resource policy |
| **Audit / risk engine** | Records activity and evaluates risk | Sign-in logs, access events, SIEM |

### 2.1. Authentication and Authorization Are Not the Same

Authentication answers "who is the caller?". Authorization answers "what is the caller permitted to do with this resource?". Someone who signs in validly via SSO may still lack permission to read the production database. A workload presenting a valid certificate still cannot delete objects if the trust policy only grants read permissions.

An access decision typically combines the verified principal identity; a valid credential/session meeting MFA/risk requirements; matching groups/roles/attributes; an allowed action and resource within scope; no explicit deny or blocking permission boundary; and context such as environment, source identity, time, or network.

### 2.2. Trust Model

~~~mermaid
flowchart LR
    User["Employee / workload"] --> IdP["Identity Provider"]
    IdP --> Assertion["SAML assertion / OIDC token"]
    Assertion --> Trust["Federation trust validation"]
    Trust --> Session["Short-lived session"]
    Session --> AuthZ["Authorization policies"]
    AuthZ --> Resource["Cloud resource / API"]
    Resource --> Audit["Audit events"]
    Session --> Audit
~~~

Trust validation must verify issuer, audience, signature, validity window, and required protocol claims. After creating a session, the system must still enforce authorization for every action and resource.

## 3. Workforce Identity and Workload Identity

These two identity categories have different lifecycles and authentication mechanisms.

| Type | Represents | Typically Suitable Mechanisms |
|---|---|---|
| **Workforce identity** | Employees, administrators, developers, contractors | Enterprise IdP, SSO, MFA, group/role mapping, JIT elevation |
| **Workload identity** | VMs, containers, functions, CI/CD jobs, application services | Managed identity, workload federation, service accounts, short-lived tokens, mTLS |
| **Customer identity** | End users of the product | Customer IdP/CIAM, OIDC, risk-based passkey/MFA |
| **Partner identity** | B2B partners or integration clients | Dedicated federation, OAuth clients, certificates, or scoped identities |

Do not use shared employee accounts for applications. Each workload needs its own principal so audit trails show which service called an API. Likewise, do not share one service account across all pipelines when each pipeline can be scoped to its specific datasets and environments.

### 3.1. Workload Identity Is Not a Static Secret

A legacy pattern stores an access key in an environment variable or configuration file for an application to use indefinitely. If that key leaks in logs, images, or repositories, an attacker can use it until it is revoked.

Prefer platform-issued managed identities/service identities; federation from CI/CD workload identities to cloud roles; short-lived tokens with restricted audience and scope; identity-issued short-lived certificates; and governed, audited rotation/revocation processes.

When a platform does not support federation, static secrets can serve as a transitional option; require a secret manager, least-privilege secret read permissions, automated rotation, anomalous usage detection, and a retirement plan.

## 4. How Does SSO Work?

SSO reduces how often users must enter credentials by making the IdP the central authentication authority. Applications receive an assertion or token under a configured protocol and establish their own session.

### 4.1. SAML 2.0 Flow

SAML 2.0 typically exchanges XML assertions between an Identity Provider and a Service Provider (SP), commonly used in workforce SSO and enterprise applications.

~~~mermaid
sequenceDiagram
    participant U as User
    participant SP as Service Provider
    participant IdP as Identity Provider
    U->>SP: Access application
    SP-->>U: Redirect to IdP / AuthnRequest
    U->>IdP: Sign in, MFA if required
    IdP-->>U: SAML Response via browser
    U->>SP: Submit SAML Response
    SP->>SP: Verify signature, issuer, audience, time, recipient
    SP-->>U: Create application session
~~~

The application must verify the signature using a trusted signing certificate; check issuer, audience, destination/recipient, validity timestamps, request correlation, and replay protection as configured. Never merely parse XML and trust the assertion contents. Configure protections against XML signature wrapping and ensure safe XML processing.

### 4.2. OpenID Connect Flow

OIDC builds on OAuth 2.0 and uses an ID Token to convey user authentication details to a relying party. Authorization Code Flow with PKCE is typically suitable for web/mobile public clients; backend confidential clients can hold credentials in a protected environment.

~~~mermaid
sequenceDiagram
    participant U as User
    participant C as Client
    participant IdP as OIDC Provider
    participant API as Resource API
    U->>C: Initiate sign-in
    C->>IdP: Authorization request + state + nonce + PKCE
    IdP->>U: Authenticate / MFA
    IdP-->>C: Authorization code
    C->>IdP: Redeem code + PKCE verifier
    IdP-->>C: ID token + access token
    C->>C: Validate ID token
    C->>API: Access token
    API->>API: Validate access token + authorize resource
~~~

The ID Token is for the client to verify login; the access token is for the API/resource server. APIs must validate the access token's audience and never accept an ID Token in its place.

### 4.3. SAML vs. OIDC: Choosing by Ecosystem

| Criterion | SAML 2.0 | OIDC |
|---|---|---|
| Format | XML assertion | JWT ID Token; access token per profile/issuer |
| Common pattern | Enterprise browser SSO, legacy applications | Web, mobile, APIs, modern applications |
| Client integration | Redirect/POST bindings, metadata, and certificates | Authorization endpoint, token endpoint, JWKS/discovery |
| Claims | Attributes inside the assertion | Claims in ID/access tokens or userinfo |
| API authorization | Usually paired with another mechanism | OAuth access tokens/scopes commonly used |
| Key lifecycle | Signing certificate/metadata rollover | JWKS signing key rotation |

Neither protocol replaces all capabilities of the other, and both can coexist. Choose based on IdP, application, B2B requirements, and platform support; avoid building custom protocol parsers when maintained libraries/SDKs exist.

## 5. Federation Trust: Verifying the Right Issuer

Federation is only secure when the relying party verifies the exact issuing source and intended target of the token/assertion.

### 5.1. Claims and Metadata to Bind

- **Issuer:** which IdP issued the assertion/token?
- **Subject:** which principal is identified? Is it stable and unique within the issuer?
- **Audience:** which application/API is the assertion/token intended for?
- **Signature/key:** is the signature valid under an allowed key and algorithm?
- **Validity:** is the token/assertion unexpired and within the allowed time window?
- **Nonce/state/request correlation:** does the response match the original auth request?
- **Tenant/domain:** which organization/tenant does the principal belong to?
- **Authentication context:** were required MFA or assurance levels satisfied?

Do not map roles based solely on email domain if that domain is not governed and verified. Never assume every claim emitted by an IdP carries equal trust; establish a claim contract and verify mappings when groups or attributes change.

### 5.2. Signing Key Rollover

An IdP may rotate signing certificates or JWKS keys. Applications must trust metadata/JWKS endpoints via the officially configured issuer; cache keys with a reasonable TTL and safely refresh upon encountering a new key ID; support old/new key overlap during rollover windows; alert on abnormal spikes in signature verification failures; and reject weak algorithms or tokens specifying algorithms outside an allowlist.

Never fetch keys from an arbitrary URL supplied inside a token. Key discovery must be anchored to the preconfigured issuer and trust anchor.

## 6. Provisioning and Deprovisioning: SCIM and Lifecycle

SSO only authenticates users; it does not automatically ensure a user has an account in each application, belongs to the right groups, or loses access upon departure.

**SCIM (System for Cross-domain Identity Management)** is a widely used provisioning protocol for automatically creating, updating, and disabling users/groups between an IdP or identity governance system and applications.

| Operation | Objective |
|---|---|
| Create | Create an account when staff are granted access to an application |
| Update | Sync name, status, groups, or required attributes |
| Deactivate | Disable the account upon departure or loss of eligibility |
| Group membership | Sync groups used for role mapping |
| Reconciliation | Detect account drift between the identity source and the application |

### 6.1. Workforce Lifecycle

~~~mermaid
flowchart TD
    Hire["Joiner: hired / onboarded"] --> Provision["Provision account + baseline access"]
    Provision --> Change["Mover: changes team / role"]
    Change --> Reevaluate["Recalculate groups and roles"]
    Reevaluate --> Active["Active access"]
    Active --> Leave["Leaver / contract ends"]
    Leave --> Disable["Disable identity and revoke sessions"]
    Disable --> Remove["Remove group grants / credentials"]
    Remove --> Audit["Verify deprovisioning and retain audit"]
~~~

When someone leaves the organization, disable the account and revoke/expire sessions and tokens as supported; remove group memberships and role assignments; revoke access keys, certificates, SSH keys, PATs, OAuth grants, and secondary credentials; transfer ownership of resources/repositories/jobs/services; disable local or emergency accounts per procedure; review service accounts or secrets the person managed; and retain audit evidence without keeping unnecessary login privileges.

Tokens issued before a user is disabled may remain valid until expiration if resource servers lack revocation/introspection mechanisms. Therefore, use short-lived access tokens, session revocation, and risk-appropriate policies.

### 6.2. SCIM Is Not an Authorization Engine

SCIM synchronizes users/groups and account status; it does not decide every action on cloud resources. Synchronized groups must map to reviewed roles/policies. If an IdP group is accidentally mapped to the Administrator role, provisioning will automatically propagate overly broad privileges.

## 7. RBAC: Role-Based Access

Role-Based Access Control (RBAC) bundles a set of permissions into a role to grant consistent access by job function.

| Role | Typical Scope | Not Granted by Default |
|---|---|---|
| `viewer` | View resources/configurations in assigned projects | Create, update, delete |
| `developer` | Deploy applications to non-production | Changing IAM, reading production secrets |
| `data-operator` | Run pipelines and view logs for assigned datasets | Account administration or modifying policies |
| `security-auditor` | Read audit/configuration posture | Modifying resources |
| `production-operator` | Perform defined operations in production | Account-wide IAM administration |
| `platform-admin` | Administer platform within responsibilities | Standing unrestricted super-admin rights |

Roles should align with job functions, have an owner, and target specific resource scopes. Avoid roles accumulating permissions over years without review.

### 7.1. Role Explosion

Creating a role for every combination of team × environment × action × region causes the role count to grow rapidly. This can be reduced through clear functional roles; groups/attributes for scoping; resource hierarchies and inherited policies; parameterized permission set templates by environment/project; and short-lived roles for privileged tasks.

Do not lump everyone in the same department into one role if their actual duties differ. Simplification must preserve separation of duties.

## 8. ABAC: Attribute- and Context-Based Access

Attribute-Based Access Control (ABAC) evaluates attributes of the subject, resource, action, and environment to make access decisions.

Example attributes:

- Subject: `department`, `team`, `employmentType`, `clearance`, `tenantId`.
- Resource: `ownerTeam`, `environment`, `dataClassification`, `projectId`.
- Action: `read`, `deploy`, `delete`, `rotate-secret`.
- Environment: device posture, source network, time, approval ID, risk level.

~~~text
ALLOW deploy IF
  subject.team == resource.ownerTeam
  AND resource.environment == "staging"
  AND action == "deploy"
  AND session.mfa == true
~~~

ABAC is helpful when access depends on multiple frequently changing attributes. However, attributes must come from trusted sources, follow clear schemas, have validated values, and have update workflows. Never let a client self-assert `department=security` and use it to grant permissions.

### 8.1. Combining RBAC and ABAC

RBAC can define role groups; ABAC narrows scope. For example, only users with the `developer` role may deploy, and only to resources owned by their team in staging. Combining both models makes policies easier to manage than creating a separate role for every combination.

## 9. Least Privilege: Restricting Permissions by Action, Resource, and Condition

Least privilege is more than "don't grant Administrator." Restrict across multiple dimensions:

1. **Action:** allow only required APIs/actions; avoid wildcards unless necessary.
2. **Resource:** target only exact buckets, queues, databases, secrets, projects, or environments.
3. **Condition:** constrain by tenant, tags, network, MFA, source identity, or approval.
4. **Duration:** use short-lived sessions and JIT elevation instead of standing privileges.
5. **Data scope:** read only required fields/datasets; apply masking or row-level/column-level security.
6. **Delegation:** services may only assume downstream roles permitted by a narrow trust policy.
7. **Separation of duties:** requester, approver, and executor of sensitive tasks may need to be distinct.

### 9.1. Minimal Policy Example

~~~json
{
  "version": "2026-01-01",
  "statement": [
    {
      "effect": "allow",
      "actions": ["object:Get"],
      "resources": ["bucket/booking-reports/staging/*"],
      "conditions": {
        "principalTeam": "analytics",
        "environment": "staging"
      }
    }
  ]
}
~~~

This is a vendor-neutral illustrative policy, not a JSON policy usable directly on a specific provider. In production, check default deny, explicit deny, resource policies, boundaries, and how wildcards are evaluated.

### 9.2. Default Deny and Explicit Deny

The common principle is denying access by default unless an explicit allow exists. Some IAM engines give explicit deny precedence over allow; some models add policy boundaries, organization guardrails, or permission ceilings. Understand your provider's exact policy evaluation rules.

Do not assume two allow policies always combine into effective permission if a boundary or deny exists at another layer.

## 10. Temporary Privileges and Just-in-Time Access

A developer may need production access to resolve an incident without needing that privilege year-round. **Just-in-Time (JIT) access** grants time-bound privileges after meeting conditions such as a ticket, approval, MFA, and stated justification.

~~~mermaid
sequenceDiagram
    participant E as Engineer
    participant G as Access governance
    participant A as Approver
    participant IAM as IAM / Cloud STS
    E->>G: Request role + resource + duration + ticket
    G->>G: Check eligibility and policy
    G->>A: Approval request if required
    A-->>G: Approve / deny
    G->>IAM: Grant eligible short-lived session
    IAM-->>E: Temporary credentials
    E->>IAM: Perform approved action
    IAM->>IAM: Session expires / revoke
    G->>G: Audit and review activity
~~~

JIT reduces standing privileges, but the process requires clearly eligible roles and resource scopes; maximum duration, justification, and ticket/incident reference; appropriate MFA or authentication assurance; approvals and separation of duties; session logging/recording where supported; and automatic expiration, early revocation upon completion, and auditing.

Emergency/break-glass access requires separate protection, immediate alerts on use, post-event verification, and periodic drills. Never allow break-glass to become a daily shortcut bypassing controls.

## 11. Cross-Account and Delegated Access

Cloud environments typically span multiple accounts/projects/subscriptions to isolate production, staging, security, data, and sandboxes. Federation enables a user or workload in one account to assume a role in another account if the trust policy permits it.

### 11.1. Both Sides of Role Assumption

For a principal to assume a role:

1. The source principal must have permission to invoke the assume/delegate action.
2. The target role must trust the exact source principal or federated identity.
3. Session policies/boundaries can further narrow effective permissions.
4. Resource policies and organization guardrails still apply.
5. The session must carry source identity/audit context for traceability.

Trust policies and permission policies are distinct. A trust policy answers "who can assume this role?"; a permission policy answers "once assumed, what can the role do?".

### 11.2. Avoiding Overly Broad Trust

Avoid trusting an entire account/tenant or wildcard principal without sufficiently narrow conditions. Restrict by exact account/project/tenant; configured issuer/provider; audience or subject claim; CI/CD repository/branch/environment; external ID for partner role assumption when required by protocol/provider; and controlled session tags/source identity.

Prevent partners from spoofing internal workload subject claims or assuming roles beyond contractual scope.

## 12. Service-to-Service Identity and Workload Federation

A CI/CD pipeline deploying to the cloud, or a function reading object storage, does not necessarily need long-lived access keys.

### 12.1. Workload Identity Federation

~~~mermaid
sequenceDiagram
    participant W as CI/CD workload
    participant O as OIDC issuer
    participant STS as Cloud Security Token Service
    participant R as Target resource
    W->>O: Request workload identity token
    O-->>W: Signed token (issuer, subject, audience)
    W->>STS: Exchange token under trust policy
    STS->>STS: Validate issuer, audience, subject, claims
    STS-->>W: Short-lived cloud session
    W->>R: Access with least-privilege role
~~~

Trust should bind exact repository, branch, environment, or workload subject. Trusting only a broad issuer without constraining subject/audience can let unrelated workloads obtain the role.

### 12.2. Managed Identity

Managed identities let compute services obtain cloud-platform-managed identities. Applications retrieve tokens from a runtime identity endpoint or SDK; key rotation and credential lifecycles are handled by the platform.

Even so, a managed identity still requires role/resource policies. Enabling an identity does not mean it has permission to access every resource in the subscription/account.

### 12.3. mTLS and Service Mesh

mTLS authenticates both ends of a transport connection using certificates. A service mesh can issue identities and rotate certificates automatically for workloads. However, certificates only authenticate peers within a trust domain; application authorization must still decide which endpoints/actions a peer may invoke.

Do not treat arbitrary subject CN or SAN values as proof of permissions without a controlled identity mapping.

## 13. Session Management, MFA, and Access Conditions

SSO provides centralized login, while each application maintains its own session. Design for:

- **Session lifetime:** maximum session duration.
- **Idle timeout:** session expiration after inactivity.
- **Reauthentication:** requiring fresh authentication for sensitive actions.
- **MFA / phishing-resistant authentication:** multi-factor or passkey/security-key requirements matched to risk.
- **Device posture:** allowing only compliant devices.
- **Risk-based access:** detecting anomalous location/device/behavior.
- **Token audience/scope:** preventing tokens from being used on unintended APIs.
- **Logout/revocation:** handling sessions at both application and IdP; understanding propagation limits.

MFA at the IdP does not automatically guarantee downstream access tokens preserve the assurance context. If an operation requires recent MFA, the application must check authentication context claims or enforce step-up authentication per protocol.

### 13.1. Sessions Should Not Live Forever

Long sessions reduce login prompts but widen the window for attackers using hijacked sessions. Use short-lived access tokens, risk-based refresh/session policies, reauthentication for privileged actions, and revocation when an identity is disabled.

## 14. Separation of Duties and Privileged Access Governance

Certain actions should not be requested, approved, and executed by the same principal:

| Task | Suggested Separation |
|---|---|
| Modifying production IAM trust policies | Proposer + reviewer/security approver |
| Deleting backups or retention-locked data | Data owner + authorized approver |
| Granting temporary admin access | Requester + separate approver + audit |
| Issuing signing keys/certificates | System owner + key custodian |
| Deploying production policy changes | Pull request review + dedicated pipeline identity |

Break-glass or super-admin access must maintain an explicit list of authorized users, phishing-resistant MFA protection, alerting, and separate access reviews. Never grant permanent broad access merely to avoid slow approval workflows.

## 15. Access Reviews and Unused Privileges

Least privilege requires continuous maintenance as teams, workloads, and resources evolve.

An access review should check:

- Which users/groups/roles have access to which resources?
- Do grants have an owner and business justification?
- Is last-used activity still required? (Unused does not automatically mean removable if it is a DR/recovery role.)
- Do roles contain wildcards or sensitive permissions beyond their purpose?
- Do service accounts have stale credentials, departed owners, or overly broad scopes?
- Do federated trusts contain unused issuers/subjects?
- Are permissions granted through multiple paths (groups, direct grants, resource policies)?
- Have temporary grants expired and been revoked?

### 15.1. Review Process

1. Export an inventory of identities, groups, roles, resource policies, and credentials.
2. Aggregate effective permissions per principal, including indirect grants.
3. Ask owners to confirm purpose and scope.
4. Identify excess permissions, orphaned identities, stale access keys, and obsolete trusts.
5. Approve changes/revocations through workflow.
6. Execute with an appropriate rollback plan.
7. Verify effective permissions after changes.
8. Record review outcomes, exceptions, approvers, and the next review date.

Do not inspect policy JSON alone; verify effective permissions after policies, groups, boundaries, and resource policies combine.

## 16. Auditing, Detection, and Incident Response

Key identity events include sign-in successes/failures, MFA challenges, and step-up events; user/group creation, updates, disabling, and removal; role assignments/grants/revocations and permission policy changes; role assumptions, token issuances, and session creations; secret/access key/certificate creation, rotation, and deletion; privileged access usage; trust relationship changes; anomalous access denied events; and break-glass usage.

Logs must include principal, issuer, subject/source identity, target role, resource, action, decision, timestamp, request/session ID, and relevant context. Avoid logging access tokens, refresh tokens, private keys, passwords, or secrets.

### 16.1. High-Value Alerts

- A workload assumes a role from a repository/branch/environment outside the allowlist.
- Admin privileges are granted outside JIT approval.
- A principal suddenly accesses numerous sensitive resources.
- A disabled identity still exhibits session/credential activity.
- Trust policies or federation metadata change outside standard workflows.
- A service account lacks an owner or an access key misses rotation policy.
- Repeated failed role assumptions or token audience mismatches.

Alerts must have owners/runbooks; some access-denied events are normal. Correlate with change tickets, baselines, and risk context to reduce false positives.

## 17. Common Mistakes

| Mistake | Consequence | Improvement |
|---|---|---|
| Assuming SSO equals least privilege | Users logging in once may receive overly broad rights | Map groups/roles by job function and resource scope |
| Using email as an immutable principal | Email changes or reuse cause mis-mapping | Use stable subject/object IDs within the issuer namespace |
| Configuring SAML/OIDC without provisioning | Departed staff retain local accounts/privileges | Implement SCIM or deprovisioning workflows and reconciliation |
| Mapping SCIM groups directly to admin without review | Incorrect group membership propagates high privileges | Require approvals, mapping policies, and access reviews |
| Using long-lived access keys for workloads | Leaked credentials remain usable for a long time | Managed identity/workload federation/short-lived tokens |
| Trusting an entire account/issuer | Out-of-scope principals can assume roles | Constrain subject, audience, tenant, and conditions |
| Confusing trust policies with permission policies | Principals can assume the role with overly broad access | Review both sides independently |
| Granting standing admin roles | Larger blast radius when an account is compromised | JIT, short sessions, MFA, and separation of duties |
| Checking roles only, ignoring resource scope | Access possible across other teams'/tenants' resources | Combine RBAC with ABAC/resource policies |
| Not revoking sessions on offboarding | Old tokens/sessions remain usable | Disable, revoke, use short TTLs, and verify downstream |
| Building custom SAML/OIDC parsers | Flaws in signature/claim/replay verification | Use maintained libraries/SDKs configured properly |
| Auditing only sign-ins | Blind to role assumptions or policy changes | Audit provisioning, authorization, and privileged actions too |

## 18. Case Study: SSO Across Multiple Cloud Accounts

**Context:** a booking platform runs three cloud environments: development, staging, and production. Staff log in via an enterprise IdP; CI/CD deploys applications; data pipelines read specific datasets; the security team needs audit visibility; and partners run workloads submitting periodic reports.

### 18.1. Identity Architecture

~~~mermaid
flowchart TD
    HR["HR / Identity governance"] --> IdP["Enterprise IdP"]
    IdP --> SSO["SAML / OIDC SSO"]
    SSO --> Dev["Development account"]
    SSO --> Stage["Staging account"]
    SSO --> Prod["Production account"]
    CI["CI/CD OIDC identity"] --> STS["Cloud STS / federation"]
    STS --> DeployRole["Short-lived deploy role"]
    DeployRole --> Stage
    DeployRole --> Prod
    DataJob["Data pipeline identity"] --> DataRole["Dataset-scoped role"]
    DataRole --> Lake["Approved data locations"]
    Partner["Partner identity"] --> PartnerRole["Partner-specific role"]
    PartnerRole --> Reports["Report ingestion endpoint"]
    Dev --> Audit["Central identity / cloud audit"]
    Stage --> Audit
    Prod --> Audit
~~~

### 18.2. Workforce Access

- Enterprise IdP authenticates staff with SSO, risk-based MFA, and device policies.
- Groups are provisioned via SCIM; groups map only to approved permission sets.
- Developers have broader access in development and limited deployment access in staging.
- Production operators use JIT roles requiring a ticket, MFA, and short duration.
- Security auditors have read-only audit/configuration posture access without modifying production.
- When staff leave the company, the identity is disabled, sessions are revoked, and related direct grants/keys are reviewed.

### 18.3. Workload Access

- CI/CD uses OIDC federation, with trust policies binding repository, protected branch, and deployment environment.
- Deploy roles can only update designated services/resources and environments; no default IAM admin rights.
- Data pipelines have dedicated workload identities reading only assigned datasets and writing outputs to defined prefixes/paths.
- Partners use distinct principals and roles restricted to report ingestion; no cloud console access.
- Workload credentials are short-lived; no long-lived cloud access keys are stored in repositories.

### 18.4. Authorization and Auditing

| Principal | Permissions | Guardrails |
|---|---|---|
| Developer | Deploy staging | Team/project ownership, protected pipelines, short sessions |
| Production operator | Runbook-defined production actions | JIT, ticket, MFA, approval, audit |
| Security auditor | Read-only security/audit | Cannot modify policies or resources |
| CI/CD workload | Deploy artifacts to specific services | Issuer/subject/audience, branch/environment trust |
| Data pipeline | Read dataset A, write curated prefix B | Dataset scope, encryption, audit |
| Partner workload | Upload reports to dedicated endpoint/prefix | Partner identity, quota, schema validation |

### 18.5. Acceptance Criteria

- Staff log in via SSO without shared console accounts.
- Leavers are deprovisioned within SLA and associated sessions/credentials are revoked.
- CI/CD can only assume roles from permitted repositories/branches/environments.
- Elevated production access enforces JIT, approval, expiration, and auditing.
- Data workloads cannot read out-of-scope datasets.
- Partners cannot access the cloud console or other partners' data.
- Access reviews identify direct, group-derived, and assumed-role permissions.

## 19. Testing Federation and Least Privilege

| Test | How to Verify | Expected Result |
|---|---|---|
| Wrong issuer | Token/assertion from an untrusted IdP | Reject |
| Wrong audience | Token intended for another application | Reject |
| Expired assertion/token | Present an expired token | Reject |
| Invalid signature | Tamper payload or use an untrusted key | Reject |
| Replay | Resubmit a previously used assertion/response | Reject via replay protection |
| Wrong subject/tenant | Out-of-allowlist workload attempts role assumption | Deny |
| Excessive role | Developer attempts out-of-scope admin action | Deny |
| Resource boundary | Team A accesses Team B resource | Deny |
| Offboarding | Disable user and try old sessions/credentials | Revoke/expire per policy |
| JIT expiration | Call resource again after role expires | Deny |
| SCIM deprovision | Disable user at source | Downstream account disabled within SLA |
| Key rollover | IdP rotates signing key | System accepts valid new key and rejects untrusted keys |
| Workload token | Token has wrong audience/subject | STS refuses session issuance |
| Audit coverage | Assume role, grant/revoke, break-glass | Logs include principal, target, action, and timestamp |

Policy testing should use simulated principals in test environments. Never attempt privilege escalation against production outside an approved scope.

## 20. Identity Architecture Review Checklist

### Federation and SSO

- [ ] SAML/OIDC chosen to fit the ecosystem and use cases.
- [ ] Issuer, subject, audience, signature, validity, and replay protection are verified.
- [ ] Signing key rollover and metadata/JWKS refresh procedures exist.
- [ ] MFA/step-up, session lifetime, idle timeout, and logout/revocation are defined.
- [ ] Customer, workforce, partner, and workload identities are separated.

### Provisioning and Lifecycle

- [ ] Joiner/mover/leaver workflows have owners and SLAs.
- [ ] SCIM/group sync has reviewed mappings and reconciliation.
- [ ] Offboarding covers local accounts, API keys, certificates, tokens, OAuth grants, and service ownership.
- [ ] Access reviews have cadence, approvers, and evidence.
- [ ] JIT/break-glass access has expiration, approvals, alerts, and auditing.

### Least Privilege and Trust

- [ ] Every principal has a purpose/owner and least-privilege permissions by action/resource.
- [ ] RBAC/ABAC relies on claims/attributes from trusted sources.
- [ ] Default deny, explicit deny, boundaries, and organization guardrails are understood correctly.
- [ ] Trust policies are separated from permission policies and constrain issuer/subject/audience.
- [ ] Cross-account delegation enforces appropriate session duration and source identity.
- [ ] Workloads prefer managed identities/federation and short-lived credentials.

### Auditing and Operations

- [ ] Sign-ins, provisioning, role assumptions, policy changes, and privileged actions are logged.
- [ ] Tokens, passwords, private keys, or secrets are never logged.
- [ ] Alerts exist for trust changes, privilege escalation, and anomalous identity activity.
- [ ] Runbooks exist to revoke credentials, disable identities, and handle account compromise.
- [ ] Positive/negative authorization and end-to-end offboarding have been tested.

## 21. Hands-On Exercise

**Context:** a company operates a booking platform with 120 employees, 4 engineering teams, 2 data teams, a support team, and two integration partners. The system spans three cloud accounts: dev, staging, and production. One CI pipeline currently uses a static access key with Administrator permissions to deploy; employees log into the console using individual accounts; and former employees' permissions sometimes remain in the database console.

Redesign the following:

1. Draw a trust architecture for workforce SSO, partner federation, and workload identity.
2. Choose SAML/OIDC for the console/web app and describe issuer/audience/subject validation.
3. Define SCIM/group lifecycles and joiner/mover/leaver workflows.
4. Design roles for developers, data engineers, support, auditors, and production operators.
5. Combine RBAC/ABAC to restrict teams, projects, environments, and datasets.
6. Replace the CI's static Administrator key with workload federation; constrain repository/branch/environment and target resources.
7. Design JIT production access, approvals, MFA, session duration, and break-glass access.
8. Write conceptual trust policies and permission scopes for each workload/partner.
9. Propose access reviews, audit events, and alerts for privilege escalation.
10. Build negative tests for wrong issuer/audience, stale users, excessive permissions, and cross-team access.

**Self-check hints:** SSO does not revoke previously granted local permissions; SCIM does not replace authorization; assumed roles require separate trust and permission policies. A valid CI token should only receive a session for the exact repository/environment and necessary deploy permissions, not account-wide Administrator.

## 22. Key Takeaways

Federation establishes trust across identity systems; SSO enables centralized login sessions; provisioning manages account lifecycles; authorization decides permitted actions and resources; least privilege restricts access by task, scope, conditions, and duration.

A trustworthy cloud architecture uses proper SAML/OIDC semantics, SCIM or lifecycle workflows to deprovision accounts, workload identities and short-lived credentials instead of static keys, narrowly scoped RBAC/ABAC and trust policies, JIT for privileged access, and continuous auditing/access reviews. Only when identity, sessions, permissions, and lifecycles are controlled together does SSO reduce complexity without expanding the blast radius.
