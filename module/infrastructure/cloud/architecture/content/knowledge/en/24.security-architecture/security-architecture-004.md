# Workload Identity and Short-Lived Access Without Static Keys

## 1. Why Do Workloads Need Distinct Identities?

A cloud application does not only have human users logging in. Components such as the Booking API, notification workers, backup jobs, deployment pipelines, image-processing functions, and data-reading services all need to call APIs, read secrets, write to databases, or access object storage. Each such component is a **workload** and needs a verifiable identity.

In many legacy systems, workloads are given shared API keys, access/secret keys, or passwords stored in configuration files, environment variables, images, or secret managers. This is quick to start with, yet creates significant risk: keys can persist for a long time, get copied through logs or images, make it hard to tell who is using them, resist selective revocation, and are often over-privileged to avoid operational failures.

**Workload identity** is an identity bound to a specific application, service, job, or running component. The system authenticates that identity based on the runtime environment or a trust mechanism, then grants appropriate access. Instead of carrying a long-lived secret everywhere, a workload can obtain **short-lived credentials** after proving its identity.

This model typically combines:

- Workload identities managed by the cloud platform, orchestrator, or identity provider.
- Federation to exchange tokens/identities across trust domains.
- A Security Token Service (STS) or equivalent mechanism to issue time-bound credentials.
- IAM policies granting least privilege to the exact resources and actions needed.
- TLS/mTLS to protect and authenticate connections.
- Auditing, rotation, expiration, and revocation to manage lifecycles.

In the **CLOUD_ARCHITECTURE** module, identity design forms the security foundation for compute, networking, data, and deployment models. It must balance **security, reliability, scalability, cost, and operations** according to Well-Architected thinking.

Running example throughout this lesson: a Booking API running on Kubernetes needs to read configuration from a secret manager, write bookings to a database, and upload invoices to object storage. An email worker only needs to read events and call an email service. A CI/CD pipeline needs to deploy to production. Each workload requires a distinct identity and distinct permissions; never share a single administrative access key across all three.

## 2. Distinguishing Identity Types

Identities participating in a system usually serve different purposes:

| Identity Type | Represents Whom/What? | Example |
| --- | --- | --- |
| Human identity | Users or staff | Operator logging in via SSO |
| Customer identity | Customers using the product | Guest booking with an account |
| Workload identity | Applications, services, jobs, or processes | `booking-api`, `invoice-worker` |
| Device identity | Devices or hardware | POS terminal, edge gateway |
| External partner identity | Partner systems | Payment provider calling webhooks or APIs |
| Federated identity | Identity verified in another domain and conditionally trusted | CI runner receiving an OIDC token from an identity provider |

Do not use a user identity as a service identity merely because both use tokens. User tokens typically carry user context, audience, and user-action permissions; workload credentials represent processes and require policies scoped to the resources the service must access.

### 2.1. Authentication and Authorization

- **Authentication:** determines who the principal is and whether the identity proof is valid.
- **Authorization:** determines which actions an authenticated principal is allowed to perform on which resources, under what conditions.

Holding a valid workload identity does not mean the workload may read every bucket or database. Identity is only one input to the policy engine evaluating access. Permissions must be granted by required resource, action, condition, environment, and duration.

### 2.2. A Workload Can Have Role-Separated Identities

A process may need to interact with multiple systems, but should not receive an overly broad combined privilege as a result. You can use a runtime workload identity with resource-scoped permissions, or split processes into separate workloads if they carry different trust levels and privileges.

For example, the API receiving booking requests does not need direct permission to send emails if a notification worker handles that task. Separating responsibilities reduces blast radius when a component is exploited.

## 3. Static Key Access Patterns and Risks

A long-lived access key typically consists of an identifier and secret used by a workload to sign requests or obtain tokens. When the secret remains unchanged for long periods, it can be copied and continue working long after the original process has been replaced.

### 3.1. Where Static Keys Commonly Leak

- Source code, repositories, pull requests, and configuration files.
- Docker/container images or build layers.
- Environment variables, crash dumps, process inspection, and debug output.
- Logs, traces, command history, and support bundles.
- Secrets shared across multiple environments or multiple services.
- Developer machines, CI runners, or poorly managed hosts.
- Backups, artifact registries, or old exports.

A secret manager helps govern storage and access to secrets, but **does not automatically turn a long-lived key into a short-lived credential**. If an application still reads a non-expiring access key from a secret manager and uses it indefinitely, lifecycle risks remain.

### 3.2. Risks of Sharing a Single Key

If the Booking API, worker, and deployment pipeline share one key:

- Audits cannot tell which process performed an action.
- One workload cannot be revoked without disrupting the others.
- Permissions usually have to be broad enough to cover all use cases.
- Keys must be distributed and synchronized across many places.
- Rotation requires coordinating every client and can cause outages.
- It is difficult to prove the credential has been purged from old images, logs, or backups.

## 4. Target Model: Trusted Identity and Short-Lived Credentials

A typical access flow:

~~~mermaid
sequenceDiagram
    participant W as Workload
    participant P as Runtime Identity Provider
    participant STS as Token / STS Service
    participant IAM as IAM Policy Engine
    participant R as Protected Resource
    W->>P: Prove workload identity
    P-->>W: Identity assertion / token
    W->>STS: Exchange assertion for short-lived credentials
    STS->>IAM: Evaluate trust policy and permissions
    IAM-->>STS: Allow with appropriate scope
    STS-->>W: Credentials with expiration
    W->>R: Call API with credentials
    R->>IAM: Verify token, scope, and policy
    IAM-->>R: Allow / deny
    R-->>W: Result
~~~

Step names and ordering vary across platforms. Some systems issue workload tokens directly; some exchange runtime assertions for cloud role sessions; others use certificates or SPIFFE SVIDs for service-to-service authentication.

Key points:

1. The workload proves its identity through a platform-trusted channel.
2. Trust policies verify issuer, subject, audience, environment, and other conditions.
3. Issued credentials are time-bound, scoped, and least-privilege.
4. Resources verify credentials and authorization at access time.
5. Workloads refresh credentials before expiration and never write secrets to logs.

## 5. Ways to Provision Workload Identity

### 5.1. Cloud-Native Workload Identity

Cloud providers typically offer mechanisms to attach roles/service accounts/managed identities to compute resources such as VMs, container services, serverless functions, or managed jobs. The runtime provides an endpoint or SDK for processes to obtain temporary credentials.

Benefits:

- Identity is bound to the running resource, reducing the need to store access keys.
- The cloud control plane manages credential issuance and expiration.
- IAM policies can restrict permissions per service/role.
- Easier auditing by principal or role session.

Things to verify:

- Which processes on the host/container can retrieve the identity?
- Can workloads on the same node be distinguished?
- Can unauthorized containers reach the metadata endpoint?
- How does the SDK cache/refresh credentials?
- When an instance/service terminates, how long do existing credentials remain valid?

Do not grant one broad instance role to all processes on the same machine if they have different trust levels.

### 5.2. Kubernetes Service Accounts and Workload Identity

In Kubernetes, a ServiceAccount provides identity for a pod. Projected tokens can carry an expiration and audience, then be used with federation to exchange for cloud role credentials. Exact mechanisms depend on cluster version, issuer, OIDC configuration, and cloud provider.

An illustrative pod declaration:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: booking-api
  namespace: production
  annotations:
    identity.example/role: booking-runtime-role
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: booking-api
  namespace: production
spec:
  template:
    spec:
      serviceAccountName: booking-api
      automountServiceAccountToken: true
      containers:
        - name: api
          image: registry.example/booking-api:v4
~~~

This is a conceptual example; annotations and configuration fields are not universal syntax for Kubernetes or any specific cloud provider. In production, use your platform's official configuration and control token projection, audience, issuer, RBAC, and networking.

ServiceAccount tokens can serve the Kubernetes API or act as federation assertions; do not confuse the two purposes. Do not mount tokens into containers if the workload does not need Kubernetes API access or identity federation.

### 5.3. Managed Identity for VMs/Serverless

A managed identity is a cloud-platform-managed identity attached to a resource. Applications request tokens from a runtime identity endpoint or SDK without storing a client secret. Either system-assigned or user-assigned identities may be used depending on the platform.

When choosing, consider:

- Is the identity lifecycle tied to the resource or independent for reuse?
- Is a single identity attached to multiple workloads?
- Which permissions are granted and how are they scoped by resource?
- How do logs distinguish between instances sharing the same identity?
- Can it be rotated or revoked without changing application configuration?

### 5.4. Workload Identity Outside the Cloud

Workloads running in data centers, at the edge, or on CI runners may lack cloud-native metadata identities. Options include OIDC federation, certificate-based identity, SPIFFE/SPIRE, or a managed identity broker.

Do not solve this by placing long-lived cloud access keys on every VM. Establish trust relationships specifying issuer, subject, audience, environment, and concrete binding conditions.

## 6. Federation and OpenID Connect

**Federation** allows one trust domain to accept identity proof issued by another domain under a trust policy. Workloads can obtain tokens from a CI platform, Kubernetes cluster, or identity provider and exchange them for cloud resource access without storing long-lived client secrets.

**OpenID Connect (OIDC)** is an identity layer built on OAuth 2.0 that uses ID Tokens to describe authentication events and convey issuer/claims. In workload federation, platforms typically validate a signed token against a trust configuration; the token serves as an assertion to obtain another credential. Follow each platform's official flow.

### 6.1. Claims to Validate

| Claim/Attribute | Meaning | Risk if Trust Is Too Broad |
| --- | --- | --- |
| `iss` (issuer) | Where the token was issued | Accepting forged or external issuers |
| `sub` (subject) | Principal identity | Accepting any repository, namespace, or service account |
| `aud` (audience) | Intended recipient of the token | Tokens issued for another service get reused |
| `exp` / `nbf` | Validity window | Expired or not-yet-valid tokens erroneously accepted |
| `signature`/`key` | Proof the token was signed by the issuer | Missing signature verification or mishandling key rotation |
| `repository`/`environment` | CI/CD context if provided by issuer | Branches/forks/untrusted environments gain production rights |
| `namespace`/`service account` | Cluster workload context | Untrusted pods impersonate privileged workloads |

Do not check only the issuer. Trust policies generally must bind `issuer + subject + audience` and may add claims for repository, branch, environment, namespace, or service account. Choose claims with exact semantics and verify they are signed by the issuer rather than taken from arbitrary headers.

### 6.2. Example CI/CD Federation Flow

~~~mermaid
sequenceDiagram
    participant CI as CI Runner
    participant OIDC as CI OIDC Provider
    participant STS as Cloud STS
    participant IAM as Cloud IAM
    participant PROD as Production API
    CI->>OIDC: Request job token
    OIDC-->>CI: Signed token (issuer, subject, audience, expiry)
    CI->>STS: Exchange token for role session
    STS->>IAM: Check trust conditions
    IAM-->>STS: Trust allowed
    STS-->>CI: Short-lived deployment credentials
    CI->>PROD: Deploy using scoped permissions
~~~

Trust policies should specify the exact repository, protected branch/tag, or deployment environment allowed to deploy to production. Never allow pull requests from forks to gain production write privileges simply because the token has a valid issuer.

### 6.3. Audience and Confused Deputy

Audience restricts tokens to the intended relying party. If multiple systems accept the same token without binding audience, a token can be replayed against the wrong service. Configure specific audiences and reject wildcards unless thoroughly justified.

An overly privileged intermediary workload can inadvertently execute actions on behalf of an under-privileged caller (confused deputy). When a service receives commands from another workload, verify the caller's identity, the caller's permissions, and whether the service is permitted to act on its behalf; never assume every incoming request can exercise the service's full runtime permissions.

## 7. STS and Short-Lived Credentials

A **Security Token Service (STS)** or equivalent service issues temporary credentials to verified principals. Credentials may include access tokens, access key/session secret/session token triples, or signed assertions depending on the protocol.

A credential session typically contains:

- The principal/role being represented.
- Applicable permissions or scopes.
- Audience/resource target if supported by the protocol.
- Issue time and expiration.
- Session tags/claims for auditing or policy conditions.
- Context regarding source identity or role assumption.

### 7.1. Short Lifetime Does Not Automatically Mean Narrow Permissions

A 5-minute token is still dangerous if it grants account-wide administrative permissions. You must combine **short lifetime + least privilege + audience restriction + trust conditions + auditing**.

Too short a lifetime can cause repeated workload failures if STS or the identity provider is temporarily unavailable. Too long a lifetime widens the abuse window if a token is exposed. Choose durations based on threat model, refresh capability, identity service SLA, and platform policies.

### 7.2. Credential Refresh

Workloads should use official SDKs or credential provider chains to refresh automatically. Avoid writing custom signing/auth logic when platform libraries provide tested mechanisms.

A standard approach:

1. Obtain credentials at startup or before the first resource call.
2. Cache in memory according to expiration; avoid writing to logs/disk unnecessarily.
3. Refresh ahead of expiration with jitter.
4. If refresh fails transiently, use current credentials only until expiration; retry with backoff.
5. Once credentials expire and cannot refresh, fail access safely and emit alerts.

Do not wait until the exact moment of expiration to refresh: network latency and clock skew can cause initial requests to fail.

### 7.3. Clock Skew and Token Validation

Tokens carry `nbf`, `iat`, and `exp`. Skewed machine clocks can cause tokens to appear not yet valid or already expired. Synchronize system clocks, apply protocol-compliant skew tolerance, and monitor clock drift. Never widen tolerance excessively to "fix" clock errors because doing so extends the token acceptance window.

## 8. Least Privilege and Permission Boundaries

A workload identity should only hold permissions needed for its specific role:

| Workload | Illustrative Required Permissions | Permissions Not Granted by Default |
| --- | --- | --- |
| Booking API | Read runtime DB secret, access booking tables, write outbox | IAM administration, deleting backups, cluster deployment |
| Invoice worker | Read invoice events, write objects to tenant invoice prefix | Reading payment credentials or deleting entire buckets |
| Notification worker | Read events to send and call notification provider | Writing booking DB, reading all customer records |
| Search indexer | Read projection source, write search index | Updating bookings or administering accounts |
| CI deploy role | Deploy artifacts to permitted namespaces/environments | Reading customer data or administering billing |
| Backup job | Read source data and write to backup repository | Deleting all backups or modifying production data |

### 8.1. Scoping by Resource and Action

Policies should restrict by:

- Specific actions: get/list/put/delete/execute, avoiding broad wildcards by default.
- Specific resources: database/table/bucket/topic/secret/cluster.
- Environment: development, staging, production.
- Tenant or namespace when resources are shared.
- Network/source conditions or device/workload posture where supported.
- Time, session tags, or MFA/human approval for special actions.

Do not rely on a role name string as the sole security proof. Trust policies and resource policies must verify the actual principal, resource, action, and conditions.

### 8.2. Splitting Roles by Function

If a service needs to read secrets and write objects, but does not need to delete objects or manage IAM, grant only those exact rights. If a deployment job needs to update production compute, do not grant it read access to production data. Splitting roles limits impact if a pipeline or process is compromised.

## 9. Workload Identity and mTLS / Service-to-Service

Cloud IAM identity and mTLS address different layers:

- Cloud IAM/workload credentials typically identify principals calling cloud resource management APIs.
- mTLS authenticates both client and server on a TLS connection, commonly between services.
- Application authorization determines which business endpoints/actions an authenticated service may invoke.

A single identity source can be used, provided mappings between workload principal, certificate identity, and application role are explicitly defined.

### 9.1. SPIFFE and SPIRE

SPIFFE defines how to represent workload identities via a SPIFFE ID and SVID (SPIFFE Verifiable Identity Document). An SVID can be an X.509 certificate or a JWT depending on usage. SPIRE is an implementation providing attestation and issuing SVIDs to workloads.

This concept is useful in multi-cluster, multi-cloud, or hybrid environments requiring service-to-service identities independent of IP addresses and hostnames. Workloads are attested via node/workload selectors and issued time-bound SVIDs. Peers verify trust bundles/issuers and identities against policy.

SPIFFE/SPIRE does not replace all IAM, API authorization, or secret management. It provides the workload identity layer; each service must still decide which actions a principal is allowed to perform.

### 9.2. mTLS Flow

~~~mermaid
sequenceDiagram
    participant A as Service A
    participant B as Service B
    A->>B: TLS ClientHello
    B-->>A: Server certificate
    A->>B: Client certificate
    B->>B: Verify issuer, validity and identity
    A->>A: Verify server identity
    A->>B: Authorized API request
    B->>B: Map workload identity to application policy
    B-->>A: Response
~~~

Certificate expiration, trust bundle updates, and workload identity revocation must all be handled. Rotation should not disrupt connections en masse; deploy overlapping certificates/trust bundles during controlled windows.

## 10. Identity Propagation and Delegation

In a service chain A → B → C, distinguish between:

- C calling with C's own identity.
- C calling on behalf of the user or workload A.
- C calling on behalf of the authenticated tenant.

If C uses its own runtime permissions without preserving caller context, an intermediate service can become a confused deputy. If A's raw token is forwarded across every hop, the token may carry an inappropriate audience or lifetime.

Options:

1. **Service identity:** each service authenticates with its own identity and verifies caller permissions at the API layer.
2. **Token exchange/delegation:** exchange the token for a new token with a narrower audience, scope, and lifetime.
3. **On-behalf-of pattern:** the service acts on the user's behalf using an identity-provider-supported flow.
4. **Signed context:** pass signed or integrity-protected context when tokens cannot be forwarded; receivers still verify source and scope.

Do not habitually forward access tokens across every service. Send credentials only to intended audiences and keep tokens out of logs, query strings, and unprotected messages.

## 11. Revocation, Rotation, and Handling Exposed Credentials

Short-lived credentials reduce the abuse window but do not replace incident response procedures.

### 11.1. Revocation Mechanisms

- Disable/revoke the workload identity or role trust.
- Revoke federated trust for the issuer/subject/environment.
- Reduce permissions or deny the principal in policies/resource policies.
- Revoke certificates or update trust bundles/CRLs/OCSP as supported by the system.
- Terminate compromised workloads/runners and rebuild from clean images/artifacts.
- Rotate downstream secrets if credential exposure risked exposing other secrets.
- Block network paths or sessions per the incident response plan.

Not every issued token is invalidated immediately when a policy changes. Some systems evaluate policy on every request; others accept tokens until expiration or experience propagation delays. Understand provider semantics and pick appropriate lifetimes.

### 11.2. Rotation with Overlap

For certificates or secrets that still require rotation, use a phased process:

1. Create the new credential and register trust.
2. Deploy workloads accepting the new credential.
3. Shift traffic or refresh sessions to the new credential.
4. Verify no requests still use the old credential.
5. Revoke the old credential and log the audit event.

Short-lived credentials still require scheduled and incident-driven rotation of signing keys, trust anchors, issuer keys, and client certificates. "No static keys in workloads" does not mean there are no long-lived cryptographic keys anywhere; signing keys and trust roots must be protected in the control plane.

## 12. Credential Caching, Refresh, and Availability

Short-lived credentials introduce a dependency on the identity provider/STS. If STS goes down, workloads with valid cached credentials can keep operating within that lifetime, but cannot refresh indefinitely.

Principles:

- Cache credentials in memory using tested SDK/provider mechanisms.
- Refresh early with jitter to prevent thundering herds across instances.
- Use retries with exponential backoff and a bounded total timeout.
- Monitor token issuance latency, error rates, and soon-to-expire credentials.
- Never log credentials or token exchange requests containing assertions.
- Provision appropriate capacity/HA for identity endpoints and STS.
- Do not arbitrarily extend credential lifetimes when STS fails; define degraded behavior according to business risk.

### 12.1. Credential Provider Chain

SDKs may resolve credentials from multiple sources (managed identity, workload federation, local dev profiles, environment variables, etc.). Provider order matters greatly. A stale environment variable could accidentally cause production to use a static key instead of the intended workload identity.

In production:

- Enable only approved provider sources.
- Fail startup if the identity source is wrong or lacks expected trust.
- Verify the active principal/role in safe health diagnostics.
- Never silently fall back to static keys when federation fails.
- Use separate low-privilege, appropriately scoped dev identities/profiles locally.

## 13. Securing Tokens, Assertions, and Metadata Endpoints

Tokens/assertions are bearer credentials or proofs used to obtain other credentials. Anyone capturing a token can use it within its permitted audience, expiration, and policy.

### 13.1. What Must Be Protected

- Never write tokens to application logs, tracing spans, exceptions, or crash reports.
- Never pass tokens in URLs/query strings.
- Never embed tokens into images, source code, or build artifacts.
- Restrict read permissions on projected token files and mount them only into the right containers.
- Protect identity metadata endpoints from unauthorized workloads.
- Block SSRF targeting metadata services using appropriate network/runtime controls.
- Restrict audience and expiration; verify issuer, subject, and signature.
- Handle signing key rotation and JWKS caching with proper semantics.

### 13.2. SSRF and Metadata Services

Some cloud VMs provide a metadata endpoint for workloads to fetch instance/identity information. If an application has a Server-Side Request Forgery (SSRF) vulnerability, attackers may try reaching the metadata endpoint to steal tokens. Mitigations may include requiring session/token headers on the metadata endpoint, hop limits, host/firewall controls, proxy policies, egress restrictions, and patching the SSRF flaw in the application.

Do not rely solely on a single metadata protection header if the runtime or network allows untrusted processes to reach the endpoint another way. Follow official platform guidance and the specific environment's threat model.

## 14. Auditing and Traceability

Workload identity pays off when logs can answer: **which workload, in which environment, using which credential/role, accessed which resource, which action was allowed or denied, and under which session?**

Track:

| Category | Fields/Signals |
| --- | --- |
| Principal | Workload identity, role/service account, source identity |
| Federation | Issuer, subject, audience, token exchange result |
| Session | Session ID, issue/expiry time, session tags |
| Resource | ARN/resource ID/table/bucket/topic/endpoint |
| Action | API/action, allow/deny, policy decision |
| Source | Workload environment, cluster/namespace, region, policy-compliant source IP |
| Lifecycle | Credential issued/refreshed/expired/revoked, certificate rotated |
| Anomaly | Unusual role assumption, unfamiliar audience, unusual geo/network, spike in rate |

Never log tokens or private keys for debugging convenience. Audit trails must be protected against unauthorized modification/deletion, have retention policies, and be shipped outside the workload's failure domain where necessary.

## 15. Environment Isolation and the Software Supply Chain

Workload identities must separate development, staging, and production. A CI runner from an untrusted pull request must never use a production release role.

Principles:

- Separate trust relationships by environment.
- Subject conditions bind repository/branch/tag/workflow using trusted issuer claims.
- Production deployments use protected environments or approvals per organizational process.
- Build roles only write artifacts to registries; deploy roles only deploy assigned resources.
- Runtime roles cannot modify pipelines or grant permissions to themselves.
- Artifacts must be traceable back to source commits and pipeline runs.
- Separate identity administration roles from workload runtime roles.

### 15.1. Prevent Workloads from Self-Escalating

If a workload can modify the trust policy of its own role or create new roles, the least-privilege boundary collapses. Rights to grant identities, modify IAM policies, create keys, and alter trust relationships should remain with control-plane/admin roles governed by reviews, audits, and separation of duties.

## 16. Reference Architecture Design for the Booking Platform

~~~mermaid
flowchart TB
    subgraph Runtime["Workload runtime"]
      API["Booking API<br/>ServiceAccount: booking-api"]
      INV["Invoice Worker<br/>ServiceAccount: invoice-worker"]
      NOTI["Notification Worker<br/>ServiceAccount: notification-worker"]
    end
    IDP["Workload Identity Provider / OIDC"]
    STS["STS / Token Exchange"]
    IAM["IAM Policies"]
    DB[("Booking Database")]
    OBJ[("Invoice Object Storage")]
    MSG["Event Topic"]
    EMAIL["Email Provider"]
    API --> IDP
    INV --> IDP
    NOTI --> IDP
    IDP --> STS --> IAM
    API -->|"scoped DB access"| DB
    INV -->|"write invoice prefix"| OBJ
    NOTI -->|"read notification event"| MSG
    NOTI -->|"send message"| EMAIL
~~~

Illustrative policies:

| Workload | Principal/Role | Resource | Permissions |
| --- | --- | --- | --- |
| Booking API | `booking-runtime` | Booking DB | Connect and operate on required tables |
| Booking API | `booking-secret-reader` | Booking DB secret | Read only the exact runtime secret |
| Invoice Worker | `invoice-writer` | Invoice bucket/prefix | Write objects within verified tenant scope |
| Notification Worker | `notification-consumer` | Notification topic | Consume assigned events |
| Notification Worker | `email-sender` | Email provider API | Send notifications via allowed senders/domains |
| CI deploy job | `production-deployer` | Production cluster/namespace | Deploy approved versions |

You do not need a single principal for all capabilities. Separating roles by function enables scoped auditing and revocation.

## 17. Lab: Replacing Static Access Keys with Workload Identity

**Context:** the Booking API and two workers currently share one access key stored in a secret manager. The key can read multiple buckets, write to the database, and manage some resources. The CI pipeline also uses the same key to deploy.

### Tasks

1. Inventory current workloads, environments, resources, and actions.
2. Locate everywhere the static key appears: secret store, configs, images, CI, logs, or developer machines.
3. Separate identities for Booking API, Invoice Worker, Notification Worker, and CI deployment.
4. Select cloud-native identity, Kubernetes federation, OIDC federation, or SPIFFE/mTLS based on runtime.
5. Design trust policies specifying issuer, subject, audience, environment, and concrete conditions.
6. Author least-privilege IAM policies per workload/resource/action.
7. Configure credential duration, refresh, retry, clock sync, and STS-unavailable behavior.
8. Design rotation/revocation and exposed-credential response workflows.
9. Audit SSRF/metadata endpoints, token logging, service account mounts, and provider-chain fallbacks.
10. Build an audit dashboard and anomalous-assumption alerts.
11. Execute a phased migration: provision new identities, deploy side-by-side, verify active principals, revoke the static key, and verify all access paths.
12. Write an ADR documenting trade-offs across availability, security, performance, cost, and operations.

### Sample Trust Matrix

| Workload | Issuer/Runtime | Trusted Subject | Audience | Role/Scope | Expiry |
| --- | --- | --- | --- | --- | --- |
| Booking API | Cluster OIDC issuer | Namespace `production`, ServiceAccount `booking-api` | Cloud STS | Booking runtime policy | Short-lived per platform |
| Invoice Worker | Cluster OIDC issuer | Namespace `production`, ServiceAccount `invoice-worker` | Cloud STS | Invoice object writer | Short-lived per platform |
| Notification Worker | Cluster OIDC issuer | Namespace `production`, ServiceAccount `notification-worker` | Cloud STS | Event consumer + email sender | Short-lived per platform |
| CI production deploy | CI OIDC issuer | Protected repository/environment | Cloud STS | Production deploy role | Job session only |

Values in the table must match actual claims emitted by the issuer and evaluated by the policy engine. Never copy sample subjects into production without verifying provider format and semantics.

### Completion Criteria

- Each workload has a distinct identity or sufficient scoping for isolation and attribution.
- Static credentials are no longer a runtime dependency for migrated flows.
- Trust policies bind issuer, subject, audience, and environment.
- Permissions follow least privilege across specific resources and actions.
- Credentials expire, refresh safely, and never leak into logs.
- Runbooks exist for revocation, signing key rotation, and incident response.
- No silent fallback to static keys occurs if federation fails.
- Untrusted CI contexts cannot obtain production deployment privileges.
- Audits trace principal, role session, resource, and action.

## 18. Well-Architected Pre-Production Workload Identity Checklist

- [ ] Human, customer, workload, device, and partner identities are clearly distinguished.
- [ ] Every workload has a distinct identity aligned with trust boundaries and duties.
- [ ] Authentication and authorization are designed as two separate steps.
- [ ] Trust policies verify issuer, subject, audience, expiry, and required claims.
- [ ] Federation rejects wildcards and untrusted repositories/namespaces.
- [ ] Credentials have appropriate lifetimes, refresh ahead of expiration, and are not arbitrarily stored/logged.
- [ ] IAM policies follow least privilege, constraining actions, resources, and conditions.
- [ ] No single broad admin role is shared across APIs, workers, CI, and backups.
- [ ] Metadata endpoints, projected tokens, SSRF vectors, and token files are protected.
- [ ] SDK credential provider chains do not silently fall back to static keys in production.
- [ ] mTLS/SPIFFE is applied at the right layer and mapped to application authorization.
- [ ] Identity propagation avoids confused deputy issues and wrong-audience token forwarding.
- [ ] Rotation/revocation procedures exist for credentials, signing keys, certificates, and trust anchors.
- [ ] Policy propagation delays and post-revocation token validity windows are understood.
- [ ] STS/identity providers have appropriate HA, quotas, timeouts, retries, and monitoring.
- [ ] Audit trails capture principal/session/resource/action without storing secrets.
- [ ] CI/CD trust is separated by protected branch/environment and deployment approval.
- [ ] Credential expiration, STS outages, issuer key rotation, and compromise response have been tested.
- [ ] ADRs document trade-offs across reliability, security, performance, cost, and operations.

**Core Takeaway:** workloads need verifiable identities, least privilege, and short-lived credentials. Cloud-native identities, federation, STS, mTLS, and SPIFFE address different layers that can work together as a unified model. When trust policies accurately bind issuer/subject/audience, credentials are refreshed and revoked under control, and audits trace every workload, the system sharply reduces static-key risk and limits blast radius if a process is compromised.
