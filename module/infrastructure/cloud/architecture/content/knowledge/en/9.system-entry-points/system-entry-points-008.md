# Designing Administrative Access and Internal Service Access

A cloud system does not have entry points solely for external customers. Developers need to deploy new releases, operators need to inspect logs and troubleshoot incidents, automation tools need to provision resources, and backend services must call databases, queues, or internal APIs. If all these activities traverse the same entry path using the same type of identity, the system easily grants overly broad permissions, expands its attack surface needlessly, and makes it hard to determine who made a change.

Architectural design must distinguish at least two categories:

- **Administrative access:** humans or operational systems authorized to manage configurations, infrastructure, accounts, workloads, and incident remediation.
- **Internal service access:** applications, workers, or workload identities calling APIs, databases, queues, caches, and other services to execute business logic.

These two categories may share some underlying identity or network infrastructure, yet must have distinct **entry points, identities, permission scopes, authentication policies, and auditing** suited to their purpose. Within the CLOUD_ARCHITECTURE module, this directly intersects networking, compute, data, security, reliability, cost, and operations under Well-Architected principles.

## 1. Separating the Two Access Planes

In many designs, it helps to separate the **management plane** from the **service/data plane**:

- **Management plane:** where resources are created, modified, configured, observed, and governed. Examples: cloud consoles, resource management APIs, IAM systems, deployment pipelines, and Kubernetes control planes.
- **Service/data plane:** where business traffic is processed or data is accessed while the system operates. Examples: customers calling the Booking API, Booking API calling the Payments API, workers polling queues, or APIs querying databases.

This boundary is an **architectural framing tool**; exact names and boundaries vary across cloud services. Some services separate control planes and data planes completely, while others share endpoints or authentication mechanisms. Never assume all admin actions use a single endpoint or that all inter-service traffic is strictly data-plane under a vendor's product taxonomy.

| Criterion | Administrative Access | Internal Service Access |
|---|---|---|
| Principals | Staff, administrators, engineers, privileged pipelines/automation | APIs, workers, jobs, workload identities |
| Purpose | Managing resources, deploying, checking health, changing configs, incident response | Executing business logic, exchanging data and events between workloads |
| Entry points | Identity provider/SSO, cloud console, management APIs, bastion or zero-trust access, CI/CD | Private endpoints, internal load balancers, service discovery, private APIs, queue/database endpoints |
| Identities | Human user identities or automation identities with scoped admin roles | Machine/workload identities dedicated per application or service |
| Authorization | Task-scoped roles, bounded scope and duration; approvals for sensitive actions | Least privilege per service, API, resource, action, and dataset |
| Protocols | HTTPS to console/APIs, SSH/RDP if strictly required, admin tool APIs | HTTPS/gRPC, database protocols, queue protocols, or specialized protocols |
| Auditing | Who signed in, elevated privileges, changed configs, or approved which action? | Which workload called which service, with what scope, outcome, and data volume? |
| Primary risks | Compromised privileged accounts, broad-blast-radius changes, human mistakes | Spoofed workloads, lateral movement, leaked secrets, unauthorized data reads/writes |

**Never use an employee's personal account as an application's default runtime identity.** When a service uses a person's credentials to call a database or another API, permission lifecycles become tied to that employee and are hard to revoke, audit, and rotate. Every application should have a dedicated workload identity with tailored permissions.

## 2. Entry-Point Map for a Cloud System

Suppose a booking platform runs a Booking API, Payments API, database, queue, and worker. Operations teams must deploy, monitor, and troubleshoot. A reference architecture can separate flows as follows:

~~~mermaid
flowchart TB
    subgraph PEOPLE["Humans and admin tooling"]
        ADMIN["Engineers / Admins"]
        IDP["Enterprise IdP / SSO / MFA"]
        PORTAL["Cloud console / Management API"]
        CICD["CI/CD and automation identities"]
    end
    ADMIN --> IDP
    IDP --> PORTAL
    CICD -->|"Federation / short-lived role"| PORTAL
    subgraph CLOUD["Cloud environment"]
        subgraph MGMT["Management plane"]
            IAM["IAM / RBAC / policies"]
            AUDIT["Audit logs / security monitoring"]
            PORTAL --> IAM
            IAM --> AUDIT
        end
        subgraph PRIVATE["Private application network"]
            LB["Internal load balancer / service discovery"]
            BOOK["Booking API"]
            PAY["Payments API"]
            DB[("Booking database")]
            Q[("Message queue")]
            WORKER["Notification worker"]
            BOOK -->|"Service identity + TLS"| PAY
            BOOK -->|"Database identity"| DB
            BOOK --> Q
            Q --> WORKER
        end
        BOOK -. "Application / security telemetry" .-> AUDIT
        PAY -. "Application / security telemetry" .-> AUDIT
    end
~~~

The diagram conveys the core principle: employees enter through enterprise identity and administrative entry points; automation uses dedicated identities; workloads communicate over engineered service networks. Both management-plane audit logs and workload/transaction logs matter, and must protect read, edit, delete, and retention controls properly.

This diagram does not imply every control plane resides inside a private VPC/VNet. Many cloud management APIs are reached via authenticated public service endpoints while workload data planes use private endpoints. What matters is governing identity, source reachability, permission scope, and data flows per platform capabilities.

## 3. Designing Human Administrative Access

### 3.1. SSO, Identity Federation, and MFA

Organizations typically rely on a central **Identity Provider (IdP)**—such as Microsoft Entra ID or another federated IdP—so staff sign in once and receive scoped access to required platforms.

Conceptual flow:

1. Staff sign in with corporate accounts and complete multi-factor authentication (MFA) per policy.
2. The IdP verifies identity and issues an assertion/token via a supported federation protocol.
3. The cloud identity broker or federation layer resolves user/group claims and assigns an appropriate role.
4. The user receives a **time-bounded session or short-lived credentials** operating strictly within granted scope.
5. Sign-in, elevation, and administrative actions are logged for auditing.

**SSO does not grant unlimited permissions.** SSO handles authentication and identity federation; IAM/RBAC still dictates which resources and actions are allowed. Someone who only needs to view metrics should not gain database deletion rights simply because they sign in via the same IdP.

MFA mitigates stolen passwords, yet you still need session/token protection, phishing-resistant MFA where supported, device posture checks, session revocation, and anomaly detection. Prefer phishing-resistant MFA for high-privilege accounts whenever the ecosystem supports it.

### 3.2. Task-Based Roles and Least Privilege

Permission design should start from **actual job duties** rather than granting blanket admin roles:

| Role | Example Permissions | Permissions That Should Not Be Granted by Default |
|---|---|---|
| Developer | View dev logs/metrics, deploy to dev, read non-sensitive configs | Org-level IAM administration, deleting prod data |
| Release operator | Execute approved releases, monitor rollouts | Self-escalating permissions or altering security policies |
| Database operator | Monitor health, run approved backups/restores, perform approved maintenance | Reading unnecessary business data or modifying org-wide IAM |
| Security auditor | Read audit logs, view policies and compliance posture | Modifying/deleting log sources or disabling monitoring |
| Platform administrator | Manage platform infrastructure within assigned scope | Implicit ownership/access to all product data |

These roles are examples; organizations may split them further or combine them by team size. Always specify:

- **Principal:** Which user, group, service principal, role, or workload identity is acting?
- **Resource/scope:** Does the role apply at organization, account, subscription, project, resource group, cluster, namespace, or specific resource level?
- **Action:** View, create, update, delete, grant permissions, export data, or restore?
- **Condition:** Restrictions by environment, network, device posture, time window, ticket, or auth strength?
- **Duration:** Standing access or valid only within a work window?

Prefer granting roles at the **narrowest sufficient scope** and periodically prune unused permissions. Even "read-only" roles require scrutiny: reading secrets, exporting datasets, or viewing logs creates major risk without mutating configs.

### 3.3. Time-Bounded Privileged Access (JIT)

For sensitive operations, adopt **Just-In-Time (JIT) access** or temporary privilege elevation:

1. Staff hold a baseline role without standing broad admin rights.
2. When a change is needed, they submit a request stating reason, scope, duration, and ticket ID.
3. The system evaluates approvals or policy conditions.
4. Privileges activate for a bounded window and expire automatically.
5. All activity is audit-logged and reviewed afterward.

For example, a database operator may have standing read access to metrics; to restore production, they request restore rights for one maintenance window, scoped strictly to the target database and approved action.

### 3.4. Break-Glass Access

**Break-glass** is an emergency access mechanism for when normal login or approval systems fail and the organization must restore service.

Break-glass design requires:

- Strictly limited, tightly guarded emergency accounts/mechanisms.
- Strong credential protection, robust MFA, and secure storage/rotation procedures.
- Immediate alerts whenever invoked, routed to independent audit logs where possible.
- Strict usage limited to defined emergencies and scopes; log justification, operator, and actions.
- Post-incident credential revocation/rotation and mandatory action review.

Never create shared "backup admin accounts" with static passwords and no alerting. Break-glass is a **controlled recovery mechanism**, not a shortcut around daily access workflows.

## 4. Bastions, VPNs, and Zero-Trust Models for Admin Access

### 4.1. Bastion Hosts

A **bastion host (jump host)** is a hardened intermediary used by staff to reach servers or admin interfaces inside private networks, preventing direct SSH/RDP exposure from the Internet to every internal machine.

~~~mermaid
flowchart LR
    OP["Engineer"] -->|"SSO + MFA"| ACCESS["VPN / Zero-trust access"]
    ACCESS --> BASTION["Bastion / Session gateway"]
    BASTION -->|"SSH/RDP only to permitted targets"| VM["Private VM / admin endpoint"]
    VM -. "Session logs / audit" .-> LOG["Central logging"]
~~~

Bastions centralize entry and session recording, yet become high-privilege targets. Patch them promptly, restrict inbound sources, forbid uncontrolled shared keys, record sessions where appropriate, and plan HA/recovery. If your cloud platform offers agent/session-based admin access without jump VMs, evaluate it to cut bastion overhead.

### 4.2. VPNs

VPNs establish encrypted network tunnels between devices/users or corporate networks and the cloud, depending on topology. However, **a VPN does not automatically grant access to every resource**; once the tunnel connects, IAM/RBAC, firewalls, endpoint policies, and app authentication still apply.

Traditional VPNs can grant overly broad network reachability if routes and ACLs are loose. Restrict advertised prefixes, choose split/full tunneling deliberately, segment by user group, and enforce device posture checks per policy.

### 4.3. Zero-Trust Network Access (ZTNA)

ZTNA describes an approach that **never trusts requests merely because they originate inside an internal network**. Every request is evaluated using identity, device posture, context, target resource, and policy. Some platforms publish specific internal apps without opening general network routing to entire subnets.

Zero trust does not mean "no private networks" or "every request must pass through one vendor box." It is a set of continuous verification principles: verify identity, limit privilege, segment networks, check device health, and shrink blast radius if an account is compromised.

| Model | Benefits | Risks / Requirements to Address |
|---|---|---|
| VPN to private network | Easy integration for tools needing traditional network protocols | Can over-expose network reachability if routes/ACLs are loose |
| Bastion / jump host | Centralizes private host administration and terminal sessions | High-privilege choke point; needs hardening, logging, and HA |
| Application-level ZTNA | Grants per-app contextual access without subnet-wide exposure | Requires identity/device integration, policy governance, and compatible apps |
| Cloud management via console/API | Leverages native provider IAM and auditing | Must govern endpoints, roles, sessions, permissions, and broad-impact risks |

You do not need to pick only one model. For example, cloud console/APIs govern infrastructure; ZTNA secures internal dashboards; a bastion covers the few hosts needing SSH/RDP. Every path needs clear scope and ownership.

## 5. Internal Service Access: Workload Identities and Private Endpoints

When the Booking API calls the Payments API, that is **service-to-service access**. Traffic may stay inside a private VPC/VNet via private endpoints, internal load balancers, service discovery, or transit networks. Yet private networking alone never verifies whether the caller is authorized for a business operation.

### 5.1. Workload Identities

Each workload should run under its own dedicated identity, such as:

- An IAM role bound to the workload on AWS (e.g., via compute-assigned roles or federation).
- A Managed Identity or Workload Identity on Azure.
- Workload Identity Federation / service accounts on Google Cloud.
- Service accounts or SPIFFE/SPIRE identities on internal platforms when properly operated.

These mechanisms are not strictly identical; evaluate credential issuance, trust boundaries, lifetimes, and federation capabilities per platform.

**Prefer short-lived credentials bound to workload identity**, avoiding hardcoded long-lived access keys, database passwords, or static tokens in source code, container images, unprotected env vars, or Git-committed configs.

Least-privilege examples:

| Workload | Identity | Required Permissions |
|---|---|---|
| Booking API | `booking-api-prod` | Call Payments API with payment-initiation scope; read/write required booking tables |
| Notification Worker | `notification-worker-prod` | Poll queue and send email via authorized mail service |
| Booking CI/CD | `booking-deploy-prod` | Deploy only Booking workloads via pipeline; no access to payment data |
| Monitoring agent | `monitoring-agent` | Ship telemetry to observability backend; no access to business databases |

### 5.2. Private Endpoints and Internal Load Balancers

**Private endpoints** let workloads reach a service over private addressing or provider-backed private links, reducing public Internet exposure. **Internal load balancers** distribute traffic within configured internal networks.

They are useful when:

- Databases or APIs should only be reachable from workloads in approved networks.
- Data does not need to traverse public endpoints.
- Teams want explicit control over routing, DNS, and firewall policies.
- Hybrid connectivity or environment segmentation constraints apply.

Private endpoints still require IAM, network policies, and service-level authentication. On some platforms, private DNS, endpoint policies, and principal permissions must be configured separately. A private endpoint alone does not restrict access to only one application.

### 5.3. Service Discovery and Internal DNS

Workloads typically address logical names like `payments.internal` instead of hardcoding instance IPs. Service discovery/DNS maps logical names to live targets as replicas, regions, or deployments change.

Design carefully:

- Per-environment namespaces and names, such as `payments.prod.internal` and `payments.staging.internal`.
- Private DNS zones, resolvers, forwarding rules, and record-management permissions.
- TTLs matched to failover goals; overly long TTLs retain stale IPs, while overly short ones raise DNS load.
- Endpoint access controls and exact-hostname TLS certificate validation.
- Prevent non-prod services from accidentally resolving to prod endpoints.

## 6. Service-to-Service Authentication, Authorization, and Encryption

### 6.1. Authentication and Authorization Are Two Distinct Steps

- **Authentication:** Which user or workload is calling?
- **Authorization:** Which actions is that identity permitted to perform on which resources?

For instance, the Booking API authenticates via workload identity to call the Payments API. That does not mean it may issue **refunds**, inspect full card histories, or alter payment configs. Authorization must enforce scopes, actions, and data boundaries via an API gateway, service code, or policy engine.

### 6.2. TLS and mTLS

**TLS** protects data in transit and lets clients verify server certificates. **Mutual TLS (mTLS)** adds client certificate verification by the server. mTLS is particularly valuable when service-to-service traffic needs transport-level workload identity.

~~~mermaid
sequenceDiagram
    participant B as Booking API
    participant P as Payments API
    B->>P: TLS connection + client identity (mTLS if used)
    P-->>B: Verify certificate / client trust
    B->>P: Request + business token/scope if needed
    P->>P: Authenticate and authorize
    P-->>B: Response per policy
~~~

mTLS does not automatically replace business authorization. A workload certificate proves "the caller is Booking API," not which specific business actions or records it may touch. OAuth tokens or policy engines can supply finer scopes/claims alongside it.

When using certificates, automate **issuance, rotation, revocation, trust-bundle updates, and expiry monitoring**. Long-lived static certs baked into container images quickly become unmanageable credentials.

### 6.3. API Gateways and Service Meshes

| Mechanism | Role | Best Fit When | Limitations |
|---|---|---|---|
| **API Gateway** | API entry point enforcing auth, rate limits, routing, logging, transforms | Client/partner APIs or centralized API governance | Not required for every internal call; backends still need direct protection |
| **Internal API gateway** | Governs internal API flows | Multiple service teams share common policies and an API catalog | Adds a hop, cost, config, and another HA dependency |
| **Service mesh** | Provides service discovery/traffic policies, telemetry, and workload mTLS depending on product | Many services needing standardized east-west governance | Increases control/data plane complexity, debugging, and ops load |
| **Direct workload identity** | Services obtain credentials from compute identity | Simpler topologies or platforms with strong native IAM | Teams manage app policies, networking, and observability directly |

Do not adopt a service mesh or extra gateway merely because cloud-native hype suggests it. Decide based on service count, team boundaries, security needs, routing complexity, and operational capacity.

## 7. Data Access, Secrets, and Management Systems

### 7.1. Database Access Controls

Databases should accept connections only from authorized workloads or sources, over proper networks, using least-privilege principals. Key practices:

- Never expose database ports broadly to the public Internet just for GUI convenience.
- Use private networks/private endpoints where appropriate; restrict sources, ports, and paths.
- Assign separate database principals per application or role; avoid sharing one DBA account across all APIs.
- Separate read/write and schema permissions where needed; withhold DDL or admin rights from runtime apps unless required.
- Manage connection pools, timeouts, TLS, rotation, and audits; test effective permissions, not just firewall rules.

### 7.2. Secret Management

Store passwords, API keys, private keys, tokens, and sensitive connection strings in a dedicated **secret manager / key vault**. Grant workload identities scoped, time-bounded access to fetch secrets; never write secrets into logs, diagrams, or ADRs.

Rotating credentials can cause outages if applications cannot tolerate overlap windows. Design credential overlap, phased rollout, new-connection verification, and old-credential revocation. Never rotate keys abruptly without knowing every dependent application.

### 7.3. Accessing Cloud Management Systems

Cloud consoles and management APIs typically use endpoints separate from resource/data APIs. Organizations should:

- Enforce SSO, MFA, and device/context policies on sign-ins where supported.
- Scope roles/permission sets by account/subscription/project and job function.
- Restrict rights to modify IAM, networking, public endpoints, keys, and logging.
- Separate automation identities from human identities; pipelines must never rely on unmanaged personal keys.
- Store audit logs in a separate boundary hard for regular workloads or admins to alter/delete.
- Consider restricting admin access from unmanaged devices/networks if compliance requires it.

## 8. Deployment Pipelines and Automation Identities

CI/CD pipelines are also **administrative entry points** because they create and modify production resources. Treat pipeline identities as privileged principals:

1. Give each project or environment its own scoped workload identity / service principal.
2. Authenticate pipelines via OIDC federation or short-lived platform tokens whenever possible.
3. Keep credentials out of source code; guard and scope pipeline secrets tightly.
4. Restrict deploy roles solely to resources owned by that pipeline.
5. Gate infrastructure and IAM changes with peer review, policy checks, and risk-tiered approvals.
6. Log initiator, revision, artifact digest, pipeline identity, and change scope.
7. Handle failed releases via documented rollback workflows rather than granting broad admin rights to bypass controls.

**Separate build from deploy:** build artifacts in low-privilege build environments; run production deploys with a separate identity at the release stage. This prevents untrusted build scripts or dependencies from inheriting production write privileges.

~~~mermaid
flowchart LR
    DEV["Developer"] --> PR["Pull request / review"]
    PR --> BUILD["Build + test + scan"]
    BUILD --> ART["Signed artifact"]
    ART --> APPROVE["Release approval / policy"]
    APPROVE --> FED["Workload federation"]
    FED --> ROLE["Short-lived deploy role"]
    ROLE --> PROD["Production resources"]
    PROD -. "Audit events" .-> LOG["Central audit"]
~~~

These steps illustrate the pattern; Git tools, pipelines, registries, and cloud providers vary. Crucially, pipelines must never become a backdoor bypassing SSO, approvals, and auditing.

## 9. Risks of Merging Administrative and Service Paths

### 9.1. Sharing One Identity

If admins and runtime services share one credential, an app bug can abuse resource-management rights, and a leaked credential creates massive blast radius. **Fix:** separate user, automation, and workload identities with task-based permissions.

### 9.2. Leaving Admin Endpoints Exposed Publicly Without Controls

Public admin dashboards or APIs attract scanning, brute-force attacks, and exploit attempts. **Fix:** enforce strong authentication on admin entry points, restrict network/context conditions, use private access or ZTNA where appropriate, and monitor privileged logins and actions.

### 9.3. Assuming Private Networks Mean Safe

Attackers move laterally if a compromised private workload holds overly broad permissions. **Fix:** network segmentation, workload identities, TLS/mTLS, service authorization, secret scoping, and egress restrictions.

### 9.4. Letting Admins Share the App's Database Access Path

Admins connecting directly from laptops open uncontrolled pathways alongside continuous runtime app traffic. **Fix:** establish approved, audited admin DB access workflows while runtime apps use separate database identities and permissions.

### 9.5. Lacking Independent Audit Logs

If admins can delete logs recording their own actions, audits lose integrity. **Fix:** ship logs centrally into an isolated boundary, restrict delete rights, enforce retention/immutability where supported, and alert if logging stops.

### 9.6. Failing to Test Break-Glass and Permission Revocation

Emergency credentials can silently break, or temporary roles may fail to expire. **Fix:** test safely on a schedule, run drills, monitor TTLs, and review sessions/permissions post-incident.

### 9.7. Too Many Access Layers Without Clear Ownership

VPNs, bastions, gateways, proxies, and service meshes often accumulate with overlapping policies. **Fix:** diagram every entry and service flow, documenting owner, approver, log location, and failure handling per layer.

## 10. Design Example: Cloud Scheduling System

### Context

A business runs a Booking API and Payments API inside private networks. Platform manages cloud infrastructure; Security audits policies and logs; Booking deploys frequently; apps call databases and queues.

### Identity and Entry-Point Model

| Principal | Entry Point | Identity | Permission Scope |
|---|---|---|---|
| Booking Developer | SSO → cloud portal / dev tools | User identity + MFA | Dev environment; scoped log/metric reads |
| Booking Release Pipeline | CI/CD → federation → cloud role | `booking-deploy-prod` | Deploy Booking API and approved runtime configs |
| Booking API | Private service endpoint | `booking-api-prod` | Call Payments API within scope; access needed Booking tables |
| Notification Worker | Private queue endpoint | `notification-worker-prod` | Poll queue; fetch email-sender secret |
| Platform Admin | SSO/JIT → management API | Admin identity | Manage assigned network, compute, and policy scopes |
| Security Auditor | SSO → audit/security console | Auditor identity | Read audit logs and security posture; cannot delete logs |
| Break-glass Operator | Controlled emergency path | Dedicated emergency credential | Bounded recovery actions with alerts and post-review |

### Flow Matrix

| Source | Target | Flow | Controls |
|---|---|---|---|
| Admin laptop / managed device | Management console/API | Admin HTTPS | SSO, MFA, conditional access, role/JIT, audit |
| CI/CD | Cloud management API | Resource deployment | Federation, dedicated identity, narrow scope, approval |
| Booking API | Payments API | Private HTTPS | Route/firewall, TLS or mTLS, workload identity, authz |
| Booking API | Database | Private DB protocol | Private endpoint, TLS, DB principal, schema permissions |
| Booking API | Message queue | Queue protocol/API | Workload identity, publish permission, network policy |
| Notification Worker | Email Provider | Outbound HTTPS | Egress policy, secret manager, retries, sanitized logs |
| Security platform | Central audit store | Log collection & alerting | Separated read/write rights, protected retention |

**Key nuances:** Developers can view app logs without automatically reading secrets; pipelines can deploy the API without querying payment tables; Booking API can call permitted Payments endpoints without using deploy roles to alter Payments configs. Sharing a cloud organization never implies sharing one blanket admin role.

## 11. Testing and Operating Access Controls

Access designs prove their value only when tested for both allowed and denied scenarios:

| Test | Expected Result | Evidence |
|---|---|---|
| Developer signs in with SSO and MFA | Receives only task-appropriate role/scope | IdP sign-in logs, cloud audit events |
| Developer attempts to modify prod DB | Denied | Authorization denial, alert/audit entry |
| Booking pipeline deploys `Booking-prod` | Succeeds via dedicated identity; revision recorded | CI/CD logs, cloud audit, artifact digest |
| Booking pipeline attempts to edit `Payments-prod` | Denied | Role scope, policy evaluation logs |
| Booking API calls Payments API | Allowed over private endpoint with valid identity | Network flows, TLS/mTLS logs, app audit |
| Unknown workload calls Payments API | Blocked at network or service authorization | Denied connection/request and alert |
| Temporary credential/role expires | Further actions fail after expiry | Token expiry, IAM/JIT audit logs |
| Break-glass is activated | Triggers alerts, audited, and post-reviewed | Alert delivery, incident ticket |
| Logging disabled or failing delivery | Triggers alerts and remediation workflow | Monitoring health, independent audit |

### Metrics to Monitor

- Count of privileged accounts and unused permissions.
- JIT elevation count, duration, and denial rate.
- Anomalous logins, failed auth attempts, and sessions from unmanaged devices.
- East-west workload traffic, denied connections, TLS failures, and authorization errors.
- Secret accesses, rotations, token issuances, and credential expirations.
- Pipeline deploy successes/failures, IAM/policy changes, and rollbacks.
- Audit log health, ingestion lag, retention status, and deletion attempts.

Avoid over-collecting personal data or sensitive payloads merely "to have logs." Logs must serve troubleshooting and operations with strict reader RBAC, retention schedules, and protections.

## 12. Well-Architected Evaluation

| Pillar | Administrative Access Questions | Internal Service Access Questions |
|---|---|---|
| **Operational Excellence** | Are JIT, break-glass, access reviews, and role revocations active? | Are service inventories, secret rotations, runbooks, and call tracing in place? |
| **Security** | Are SSO/MFA, least privilege, device checks, and auditing sufficient? | Are workload identities, TLS/mTLS, authz, secrets, and network policies accurate? |
| **Reliability** | If the IdP or auth system fails, how does emergency admin recovery work? | If DNS, identity providers, private endpoints, or service meshes fail, how do apps react? |
| **Performance Efficiency** | Do SSO/proxies add noticeable lag to routine operations? | Do gateways, meshes, TLS, and policy checks add unacceptable latency/throughput overhead? |
| **Cost Optimization** | Are platform access, logging, and bastion costs proportional? | How do private endpoints, NAT, gateways, meshes, and telemetry scale with service count? |
| **Sustainability** | Are idle bastions/admin VMs and unnecessary logs eliminated? | Are gateways/meshes right-sized, avoiding bloated telemetry and idle resources? |

### Analyzing Key Trade-Offs

**Centralizing identity** streamlines employee lifecycle and policy enforcement, yet turns the IdP into a critical admin dependency—requiring redundancy and emergency procedures. **JIT access** trims standing privileges while adding friction during incidents; approval paths must move fast enough alongside guarded break-glass access.

**Private endpoints** reduce public exposure while adding DNS, routing, endpoint policy, and cost overhead that require lifecycle management. **mTLS** establishes transport workload identity while adding cert issuance/rotation/revocation burden. **Service meshes** standardize traffic controls yet add control planes, proxies, and operational complexity. Choose based on real risk and team maturity.

Goals like "all prod admin access uses MFA and auditing," "only Booking workloads call Payments API within allowed scopes," or "temporary roles expire within set bounds" must translate into policy tests, access verification, and alerts. Never declare a system secure simply because SSO is enabled or an API sits in a private subnet.

## 13. Access Architecture Design Workflow

Apply this workflow for new projects or reviews of existing systems:

1. **Inventory actors:** humans, teams, vendors, pipelines, apps, workers, and managed services.
2. **List actions:** sign in, deploy, view logs, query databases, call APIs, read secrets, edit policies, restore, and delete resources.
3. **Separate management and service/data planes:** assign endpoints, networks, identities, data boundaries, and owners per path.
4. **Select authentication:** SSO/federation/MFA for humans; workload identities, certificates, OAuth, or short-lived credentials for services.
5. **Design authorization:** roles, scopes, actions, conditions, durations, and approvers; separate runtime rights from deploy rights.
6. **Design network paths:** public/private endpoints, VPN/ZTNA/bastions, routes, firewalls, DNS, egress, and service discovery.
7. **Protect secrets and data:** secret managers, TLS/mTLS, database principals, encryption, and rotation.
8. **Design auditing and detection:** logs for sign-ins, elevations, admin actions, service calls, denied access, and logging changes.
9. **Test allow and deny paths:** verify legitimate flows succeed and out-of-scope calls fail.
10. **Operate the lifecycle:** access reviews, revocations, cert/secret rotations, offboarding, incidents, and break-glass drills.

### Sample ADR — Separating Admin Access from Service-to-Service Traffic

> **Context:** Operations staff and the Booking API currently share one credential with production read/write config rights to call the Payments API and inspect status.
>
> **Decision:** Enforce SSO + MFA + scoped/JIT roles for staff; give pipelines OIDC federation and deploy roles; give Booking API a dedicated workload identity scoped to Payments API operations; run service endpoints over private connectivity with TLS/mTLS as required. Centralize admin and workload audit logs with separated delete rights.
>
> **Rationale:** Reduces privilege, decouples credential lifecycles, and limits blast radius if a host or user account is compromised.
>
> **Trade-offs:** Increases identity count, policies, approval workflows, and observability components; requires automating provisioning/rotation and operating IdP/private endpoints.
>
> **Verification:** Developers cannot alter `Payments-prod`; Booking API invokes only allowed APIs/operations; unknown workloads are blocked; JIT roles auto-expire; break-glass triggers alerts and audit records.

## 14. Practice Exercise

An e-commerce system currently uses one shared admin account for three tasks: deploying apps, connecting to the database, and accessing the cloud console. APIs and workers run in a private network, yet the admin dashboard is exposed on the public Internet behind a static password. Developers can read production secrets to debug issues.

**Tasks:**

1. Identify at least five security/operational risks in the current setup.
2. Redesign identities for Developers, Platform Admins, CI/CD, API, Worker, and Security Auditors.
3. Diagram the administrative flow from staff devices to the cloud management plane.
4. Diagram service-to-service flows across API, database, queue, and worker.
5. Propose protections for the admin dashboard and database; clarify when to use private endpoints, VPN, bastions, or ZTNA.
6. Design JIT and break-glass workflows; explain how to verify independent audit logging.
7. Build a test matrix covering both permitted access and denied access cases.

### Solution Direction

- Eliminate the shared admin account; move humans to individual SSO/MFA identities with scoped roles.
- Give CI/CD a dedicated identity via federation/short-lived credentials restricted to deploying its target app.
- Give API and worker separate workload identities: API accesses needed database tables and publishes to the queue; worker only polls the queue and calls external providers.
- Move the admin dashboard behind SSO/MFA with device/source controls; expose publicly only if justified with full compensating layers.
- Keep the database private; apps connect via private endpoints/networks with dedicated principals. Staff access database admin tasks through approved, audited workflows.
- Scope secrets from a secret manager strictly to runtime workloads; developers do not read prod secrets by default and debug via sanitized logs/traces under controlled access.
- Implement JIT roles, guarded break-glass credentials, immediate alerts, and post-incident reviews.
- Test denied actions, permission revocation, credential rotation, and audit log completeness.

### Self-Check Questions

1. Why is signing in via SSO insufficient proof that a user may delete a database?
2. Why are workload identities safer than baking long-lived access keys into container images?
3. Does a private endpoint guarantee every client on that network may call the API? Which additional controls are needed?
4. When is a bastion useful, and what operational duties does it introduce?
5. What does mTLS prove at the connection layer, and why is application-layer authorization still required?
6. How do you design break-glass for recoverability without turning it into a shared daily admin account?
7. If the IdP becomes temporarily unavailable, which admin tasks are impacted and how should emergency recovery operate?

A sound cloud access architecture clearly defines **which human or workload is accessing, through which entry point, to which resource, under which permissions, and for what purpose**. When human administration is cleanly separated from service-to-service access, identities and data flows can be tightly scoped, audited, and tested independently—cutting risk while keeping operations, deployments, and scaling agile.
