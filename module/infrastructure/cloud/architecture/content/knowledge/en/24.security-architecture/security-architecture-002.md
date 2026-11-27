# Zero Trust and Defense in Depth

> **Chapter:** Security Architecture  
> **Scope:** Designing cloud application architectures from business requirements through networking, compute, data, and deployment model choices. This lesson focuses on Zero Trust and defense in depth to protect identities, workloads, networks, data, and the supply chain; while balancing security with reliability, performance, scalability, cost, and operations using Well-Architected thinking.

## Learning Objectives

After this lesson, you can:

1. Explain Zero Trust principles and why internal networks, VPNs, or workload location cannot be treated as proof of trust.
2. Model trust boundaries, assets, identities, data flows, and attack paths in cloud architectures.
3. Apply explicit verification, least privilege, and assume-breach principles for users, services, workloads, and devices.
4. Design defense in depth across identity, network, application, compute, data, supply chain, and control plane layers.
5. Select risk-based controls for authentication, authorization, segmentation, encryption, secret management, logging, and detection.
6. Evaluate the impact of security on availability, performance, cost, and operations; verify through threat modeling, security testing, and incident exercises.

## 1. Why Zero Trust?

Cloud applications no longer reside inside a closed corporate network. Users may access them from personal devices, offices, mobile networks, or external providers. Workloads may run across multiple regions, accounts/subscriptions, clusters, and SaaS platforms. Microservices communicate over networks; data is replicated to caches, queues, backups, and analytics systems.

In that environment, the assumption that "requests coming from the internal network are safe" no longer holds. An account can be stolen, a container can be compromised, a firewall can be misconfigured, or a trusted dependency can be compromised.

**Zero Trust** is a design approach in which users, devices, workloads, or connections are never automatically trusted simply because they are inside a network or were previously authenticated. Every resource access request must be evaluated based on identity, permissions, context, and appropriate policy.

Zero Trust is not a product, an appliance, or enabling MFA once. It is a continuous set of principles and control architecture:

- Verify identity and access context.
- Grant least privilege, scoped and time-bound.
- Segment to limit lateral movement.
- Protect each workload and piece of data.
- Record, detect, and respond to anomalous behavior.
- Re-evaluate assumptions when device posture, identity, or risk changes.

### 1.1. Traditional Perimeter vs. Zero Trust

| Aspect | Perimeter-based security | Zero Trust approach |
| --- | --- | --- |
| Trust boundary | Primarily based on internal network/external perimeter | Boundaries around resources, identities, and flows |
| Internal access | Often trusted more behind VPN/firewall | Every access verified by policy |
| Identity | May be centralized at login/network entry | User, device, workload, and service identities |
| Permissions | May be broad by subnet/role | Least privilege, scoped, and time-bound |
| Network | Defense concentrated at the perimeter | Segmentation and policies between components |
| Monitoring | Focused on gateways/firewalls | Telemetry across identity, endpoints, workloads, and data |

Zero Trust does not eliminate firewalls, VPNs, or network perimeters. Those controls remain useful, but must not be treated as the sole proof for granting access.

### 1.2. Three Foundational Principles

1. **Verify explicitly:** base access decisions on identity, device, resource, action, and relevant context.
2. **Use least privilege:** grant only the permissions needed, for the scope and duration needed; prefer temporary privileges.
3. **Assume breach:** design to detect, isolate, and minimize damage even when a component has been compromised.

These three principles reinforce one another. MFA paired with permanent admin privileges is not least privilege. Network segmentation without verifying service identity can still allow a spoofed workload. Logging without a response process does not limit blast radius.

## 2. Modeling Trust Boundaries and Assets

Before choosing technologies, you must know what needs protection, who accesses it, where data goes, and where flows cross from one trust domain to another.

### 2.1. Identifying Assets

Assets are not just databases:

- Customer data, payment details, identity records, and tenant data.
- Credentials, API keys, certificates, signing keys, encryption keys, and tokens.
- Source code, container images, packages, build artifacts, and pipelines.
- Workload identities, service accounts, cloud roles, and control-plane permissions.
- APIs, queues, topics, object storage, backups, logs, and analytics exports.
- DNS, domains, certificates, configurations, infrastructure-as-code, and deployment workflows.
- The ability to access and operate the system during an incident.

Evaluate assets according to confidentiality, integrity, availability, provenance, and retention/deletion obligations.

### 2.2. Trust Boundaries

A trust boundary is a point where data, requests, or privileges cross into a domain with a different security policy. Examples: Internet to edge, edge to application, service to database, cloud account A to account B, build pipeline to production registry, or production to external SaaS.

~~~mermaid
flowchart TB
    U["User / device"] --> EDGE["Edge: WAF / API gateway"]
    subgraph APP["Trust boundary: application"]
      API["Booking API"]
      WORKER["Background worker"]
    end
    subgraph DATA["Trust boundary: data"]
      DB[("Booking database")]
      OBJ[("Object storage")]
      Q["Message broker"]
    end
    IDP["Identity provider"] --> EDGE
    EDGE --> API
    API --> DB
    API --> Q
    Q --> WORKER
    WORKER --> DB
    WORKER --> OBJ
    EXT["External payment provider"] <--> API
~~~

This diagram is conceptual. Each flow must specify the principal (user, workload, service, automation), resource (API, row, object, queue, secret), action (read, write, delete, publish, deploy, administer), context (device posture, environment, risk, time, tenant), and decision (allow, deny, step-up, limit, or require approval).

### 2.3. Data and Flow Classification

| Example Classification | Typical Controls Needed |
| --- | --- |
| Public | Integrity, anti-defacement, availability |
| Internal | Authentication, authorization, appropriate encryption |
| Confidential | Least privilege, encryption, auditing, retention, and export restrictions |
| Restricted/regulated | Enhanced controls, isolation, key management, data residency, and approval workflows |

The tier names above are examples only. Organizations should use their own approved taxonomy and legal/contractual requirements.

Data flow mapping should record source, destination, protocol, classification, identity, encryption, log/backup storage locations, and purpose. A copy in a data lake or DLQ is also subject to protection requirements matching its actual contents.

## 3. Identity-First: Verifying Users, Devices, and Workloads

### 3.1. Human Identity

Users and administrators should authenticate through a centralized identity provider where appropriate. Controls may include:

- MFA or phishing-resistant authentication methods matched to risk level.
- Single sign-on and lifecycle provisioning/deprovisioning.
- Conditional access based on identity, device posture, and risk signals.
- Step-up authentication for sensitive operations.
- Session lifetimes, refresh token rotation, and session revocation.
- Privileged access management and temporary admin privileges.
- Separating everyday accounts from administrative accounts.

A successful login only proves a degree of identity assurance at authentication time. It does not mean the user is allowed to access all data or that the session should live indefinitely.

### 3.2. Workload and Service Identity

Services need distinct identities; a shared credential should not be used across workloads. Managed identities, workload identity federation, service accounts, or certificates can be used depending on platform capabilities.

Examples:
- The Booking API is permitted to read required secrets and write to the Booking DB.
- The Notification worker only reads the `booking-events` topic and sends notifications via the provider.
- The deployment pipeline is permitted to update production workloads within the approved repository/environment scope.
- The backup job is permitted to read data to be backed up and write to the backup vault; it does not have arbitrary permission to modify source data.

Do not place long-lived cloud access keys inside images, configuration files, unprotected environment variables, or repositories.

### 3.3. Tokens and Claims Do Not Replace Authorization

Tokens may carry subject, audience, issuer, expiry, scope, role, and other claims. Services must verify issuer, signature, audience, expiry, and required conditions before trusting claims. Do not accept a token merely because it arrived over an internal network.

Authorization must check the action on the specific resource. An authenticated role does not imply permission to read every booking. A tenant ID in the request body likewise does not prove the user has rights to that tenant.

### 3.4. Example Workload Authentication Flow

~~~mermaid
sequenceDiagram
    participant W as Booking workload
    participant ID as Cloud identity provider
    participant API as Target service
    participant POL as Authorization policy
    W->>ID: Request token via workload identity
    ID-->>W: Short-lived access token
    W->>API: Request + token
    API->>API: Verify issuer, audience, expiry
    API->>POL: Evaluate subject, action, resource
    POL-->>API: Allow / Deny
    API-->>W: Result with audit context
~~~

This flow illustrates the concept only. Token exchange, mTLS, federation, and policy evaluation mechanisms vary by platform.

## 4. Least Privilege and Access Management

Least privilege means a principal only has the minimum permissions needed to complete a specific task. It applies to users, applications, service accounts, deployment pipelines, support staff, and automation.

### 4.1. RBAC, ABAC, and Policy-Based Access

| Model | How Decisions Are Made | When Useful | Risks to Control |
| --- | --- | --- | --- |
| RBAC | By assigned role | Permissions by job function/group | Roles accumulating excessive permissions |
| ABAC | By subject, resource, action, and context attributes | Rules by tenant, classification, environment | Missing/incorrect attributes or difficult testing |
| ReBAC | By relationships between principals and resources | Project sharing, organizations, ownership hierarchies | Unintended transitive relationships |
| Policy-based | Centralized policy evaluation | Complex decisions needing auditability | Overly complex policies or operational overhead |

Models can be combined. RBAC manages baseline roles; ABAC adds conditions such as `tenant_id`, data classification, or environment.

### 4.2. Conceptual Policy Example

~~~text
ALLOW read booking
WHEN
  subject.role IN ["booking-support", "booking-owner"]
  AND subject.tenant_id == resource.tenant_id
  AND resource.classification <= subject.clearance
  AND request.environment == "production"

DENY delete booking
UNLESS
  subject has approved break-glass grant
  AND approval is valid
  AND action is audited
~~~

This is a pseudo-policy for explanation. Production implementation requires the syntax, semantics, deny/allow precedence, default-deny handling, and test cases of the chosen policy engine.

### 4.3. Temporary Privileges and Break-Glass

Administrative privileges should be granted on demand, time-bound, approved, and audited. Break-glass is reserved for emergencies when normal procedures cannot be used. It requires specially protected accounts/access paths, strong MFA, explicit permission scope and expiration, alerts upon use, post-incident review, and credential rotation/revocation if needed.

Do not create a single permanent super-admin account shared across the entire team.

## 5. Defense in Depth

Defense in depth means layering multiple complementary controls to protect assets across different tiers. If one layer is bypassed, other layers can still detect, block, or limit the impact.

~~~mermaid
flowchart TB
    L1["1. Identity: MFA, workload identity, authorization"]
    L2["2. Edge: WAF, DDoS, rate limit, API validation"]
    L3["3. Network: segmentation, private endpoints, egress control"]
    L4["4. Workload: hardened image, runtime policy, patching"]
    L5["5. Application: input validation, secure session, secrets"]
    L6["6. Data: encryption, access policy, backup, audit"]
    L7["7. Detection & response: logs, alerts, incident playbooks"]
    L1 --> L2 --> L3 --> L4 --> L5 --> L6 --> L7
~~~

Layers do not always execute strictly in request order. Defense in depth also does not mean buying as many products as possible. Overlapping controls without owners, log integration, or with high false-positive rates can increase cost without increasing effectiveness.

| Layer | Objective | Example Controls |
| --- | --- | --- |
| Identity | Right principal, right permissions | MFA, federation, short-lived tokens, RBAC/ABAC |
| Edge | Filter malicious requests and traffic | WAF, DDoS protection, rate limiting, bot policies |
| Network | Restrict traffic paths | VPC/VNet segmentation, private endpoints, firewalls, egress policies |
| Workload | Reduce runtime attack surface | Hardened images, patching, non-root, seccomp, admission policies |
| Application | Protect logic and sessions | Input validation, output encoding, CSRF protection, authorization |
| Data | Protect contents and integrity | Encryption, key management, row/object policies, backups |
| Detection/response | Detect and contain incidents | Auditing, SIEM, alerting, incident response |

Every control needs an owner, policy, testing method, and evidence of effectiveness. A WAF can block common payloads but does not replace tenant-aware authorization in the application.

## 6. Network Segmentation and East-West Traffic Control

### 6.1. North-South and East-West

- **North-south traffic:** traffic entering or leaving the system, such as client to API gateway or application to partner API.
- **East-west traffic:** communication between services, workloads, databases, brokers, and internal components.

Perimeter firewalls help control north-south traffic, but segmentation is required for east-west traffic. If one pod is compromised and all subnets/ports are open, an attacker can move laterally to databases or the control plane.

### 6.2. Segmentation Models

Segmentation can follow environment, trust level, workload identity, data classification, tenant/cell, region/account/subscription, and DR environment boundaries.

~~~mermaid
flowchart TB
    INTERNET["Internet"] --> WAF["WAF / public ingress"]
    WAF --> APPNET["Application network"]
    subgraph APP["Application workloads"]
      API["Public API"]
      WORKER["Private worker"]
    end
    WAF --> API
    API --> DATA["Restricted data network"]
    WORKER --> DATA
    subgraph DATAS["Data services"]
      DB[("Database")]
      STORE[("Object storage")]
      BROKER["Broker"]
    end
    DATA --> DB
    DATA --> STORE
    DATA --> BROKER
    ADMIN["Privileged admin path"] --> MGMT["Management plane"]
~~~

Networking is only one segmentation layer. Identity and authorization must still be verified at the destination service; never automatically grant DB access simply because the source IP belongs to an application subnet.

### 6.3. Default Deny and Egress Control

Sound policies typically start with deny-by-default between sensitive zones, then open specific flows that have an owner. Egress control restricts workloads from making arbitrary outbound Internet calls, reducing exfiltration and command-and-control risks.

Maintain allowlists by domain/IP/protocol where appropriate, private endpoints for cloud services, DNS policies, logging, and update workflows. Avoid hardcoded IP allowlists if a provider uses dynamic ranges without a maintenance mechanism.

Network policies must be tested for both allowed and blocked traffic. Misconfigured default-deny can break DNS, telemetry, secret retrieval, or backups.

## 7. Protecting Applications and APIs

Network controls cannot replace application-layer controls. The application is where business semantics, ownership, and per-object permissions are understood.

Essential controls include:
- Authentication and authorization for every endpoint/resource.
- Server-side validation; never trust client-supplied data or privilege claims.
- Output encoding and parameterized queries to mitigate injection.
- CSRF protection when using cookie-based browser sessions, tailored to the application model.
- Session/token lifecycle management and appropriate Secure/HttpOnly/SameSite cookie flags.
- Rate limiting by identity/tenant/endpoint and abuse prevention.
- Idempotency for operations that produce side effects.
- CORS restricted to required origins/methods/headers; CORS is not authorization.
- Error responses that do not leak stack traces, secrets, or internal structure.
- Dependency validation and appropriate security headers.

### 7.1. Object-Level API Authorization

A common flaw is checking that a user is logged in without checking whether that user is authorized for the requested object ID. For example, `GET /bookings/123` can be exploited to read another customer's booking if only the ID is checked.

Access decisions must verify subject, action, resource ownership/tenant, classification, and business state. Tests must cover:
- User A reading object A: allow.
- User A reading object B belonging to another tenant: deny.
- Service role not permitted to perform a sensitive action: deny.
- Expired token or wrong audience: deny.
- Client-modified tenant context: does not alter permissions.

### 7.2. The API Gateway Is a Control Point, Not the Sole Boundary

The gateway can enforce initial authentication, routing, TLS, rate limiting, and WAF rules. Target services must still enforce authorization at the data/business scope. If the gateway is misconfigured or a service is called directly, application-level policies are what protect the object.

## 8. Protecting Workloads, Containers, and Compute

A workload should be treated both as a principal with an identity and as an environment that could be compromised.

- Run containers as non-root and do not grant privileged mode without an approved justification.
- Drop unnecessary Linux capabilities; restrict syscalls with seccomp or equivalent mechanisms.
- Use read-only root filesystems and explicitly scoped writable volumes.
- Pin images by digest or immutable version; verify provenance/signatures when the pipeline supports it.
- Scan images and dependencies; maintain vulnerability remediation SLAs based on risk.
- Restrict metadata service access and credential exposure.
- Use workload identity instead of shared credentials.
- Segment networks and restrict egress.
- Apply resource requests/limits, quotas, and workload isolation.
- Patch base images, runtimes, node OS, and control planes according to shared responsibility.

### 8.1. Admission and Runtime Policies

In Kubernetes, Pod Security Standards/admission controls, policy engines, or equivalent mechanisms can reject workloads with dangerous configurations: privileged containers, disallowed hostPath mounts, running as root, host networking, or images from untrusted registries.

Policies need a clear baseline, exceptions with owners/expiration dates, pre-deploy CI validation, production admission enforcement, violation auditing, and a safe update process to avoid accidentally blocking all deployments.

Managed application platforms may provide different abstractions; verify actual runtime constraints rather than assuming Kubernetes-equivalent configurability.

## 9. Protecting Data and Managing Keys

### 9.1. Encryption in Transit and at Rest

Encryption in transit protects data across networks; encryption at rest reduces exposure if storage media is accessed improperly. However, encryption does not replace authorization: a workload authorized to read both the data and the key can still decrypt the content.

The design must specify TLS/mTLS across clients, gateways, services, databases, brokers, and providers; encryption at rest for DBs, object storage, queues, snapshots, backups, and logs; who owns and manages keys; key rotation, revocation, and recovery; separation of duties; and how operations behave if KMS is unavailable.

### 9.2. Key Management

Key management requires a complete lifecycle: creation, access grants, usage, rotation, policy-compliant backup/recovery, revocation, and auditing. Never roll your own cryptographic algorithms or store keys in source code.

Envelope encryption commonly uses a data encryption key (DEK) to encrypt data and a key-encryption key (KEK) managed by KMS/HSM to protect the DEK. Exact details depend on the cloud service and organizational standards.

### 9.3. Backups and Immutable Recovery

Backups are critical security assets; an attacker can delete or encrypt backups alongside production if they share administrative permissions. Consider separating accounts/projects/vaults and delete permissions; immutable/WORM retention; MFA/approval for destructive operations; encryption and auditing; restore testing; and protecting metadata, catalogs, and configurations needed for recovery.

A backup is not proven usable merely because the job reported success. You must prove restoration works and applications can read/write properly afterward.

## 10. Secrets, Certificates, and Credential Lifecycle

Secrets include passwords, API keys, signing keys, database credentials, certificate private keys, and tokens. Every secret needs an owner, purpose, read permissions, storage location, expiration/rotation schedule, and revocation procedure.

Principles:
- Use a secret manager or vault; never commit secrets to repositories.
- Inject secrets at runtime via identity; avoid baking them into images.
- Use distinct credentials per service/environment.
- Prefer short-lived tokens/certificates over long-lived keys.
- Rotate with valid overlap so rollouts do not cause downtime.
- Never write secrets to logs, traces, exceptions, or CI artifacts.
- Audit secret retrieval and detect anomalous access.
- Maintain an emergency revocation and post-incident credential rotation procedure.

Certificate lifecycles also require automated renewal, expiry monitoring, trust chain validation, and checks across both client-to-edge and edge-to-origin/service-to-service paths. An expired certificate is both a security failure and an availability outage.

## 11. Securing the Supply Chain and CI/CD

Build/deploy pipelines can modify production and are therefore high-value targets. If attackers compromise a source repository, build runner, registry, or deployment credential, they can ship images containing malicious code.

### 11.1. Protection Layers

1. **Source:** branch protection, code review, MFA, least-privilege repository access, and dependency policies.
2. **Build:** isolated runners, ephemeral when appropriate, narrow secret scope, and pinned toolchains/dependencies.
3. **Artifact:** SBOM, provenance, image scanning, signing, and immutable digests.
4. **Registry:** private access, retention, replication policies, and pull/push auditing.
5. **Deployment:** short-lived workload identity, risk-based environment approvals, policy-as-code.
6. **Runtime:** allow only trusted artifacts/registries, with admission verification if supported.
7. **Response:** revoke tokens, lock pipelines, quarantine artifacts, redeploy known-good versions, and assess blast radius.

~~~mermaid
flowchart LR
    SRC["Source commit"] --> REVIEW["Review + branch protection"]
    REVIEW --> BUILD["Isolated build"]
    BUILD --> TEST["Unit / integration / security tests"]
    TEST --> SBOM["SBOM + provenance"]
    SBOM --> SIGN["Sign artifact"]
    SIGN --> REG["Private registry"]
    REG --> APPROVE["Policy + environment approval"]
    APPROVE --> DEPLOY["Deploy by immutable digest"]
    DEPLOY --> VERIFY["Runtime verification + telemetry"]
~~~

Never give build runners admin privileges over an entire cloud account. Separating build/test/deploy identities and limiting credential lifetimes reduces impact when a job is compromised.

### 11.2. Dependencies and Software Composition

Dependency scanners help detect packages with CVEs, unwanted licenses, or untrusted sources. CVE counts alone are not enough to make decisions: evaluate exploitability, runtime reachability, exposure, data sensitivity, and mitigating controls. Exceptions must have an owner, rationale, expiration date, and remediation plan.

## 12. Protecting the Cloud Control Plane and Configuration

The control plane manages resources, identities, networks, keys, logging, clusters, and policies. An account with permissions to modify the control plane can disable multiple protection layers.

Controls:
- Protect root/owner accounts specially, enforce strong MFA, and restrict day-to-day usage.
- Separate accounts/projects/subscriptions by environment, team, or trust boundary where beneficial.
- Grant IAM permissions using least privilege, role assumption, and short-lived access.
- Audit critical changes; alert when logging, encryption, network policies, or backups are disabled.
- Review, test, version-control, and apply drift detection to Infrastructure as Code.
- Use SCPs/organization policies or equivalent guardrails to prevent configurations outside policy.
- Controlled break-glass; do not lock out legitimate recovery paths.
- Control quotas, region allowlists, public resource exposure, and cross-account sharing permissions.

A secure configuration can be weakened by a single out-of-band console change. IaC and drift detection clarify desired versus actual state.

## 13. Detection, Logging, and Response

Zero Trust and defense in depth require detecting anomalous behavior, not just blocking requests. Telemetry must link identity, workload, resource, and action.

### 13.1. What Should Logs Capture?

- Authentication successes/failures, MFA/step-up, session, and token events.
- Authorization decisions, policy versions, and relevant resource classifications.
- IAM/role/key/secret changes and privileged access.
- Network policy, WAF, firewall, DNS, and egress events.
- Deployments, image digests, provenance, admission decisions, and configuration changes.
- Data access/export/deletion, backup/restore, and security-relevant events.
- Detection findings, incident timelines, and response actions.

Logs must avoid storing passwords, raw tokens, private keys, or unnecessary PII. Log store access permissions, retention, integrity, and storage regions must also be designed.

### 13.2. Detection Use Cases

| Signal | What It May Indicate | Investigation Action |
| --- | --- | --- |
| User login from unusual context | Credential compromise or legitimate behavior needing verification | Risk evaluation, MFA step-up, session review |
| Workload reads secrets outside normal pattern | Compromised service or overly broad policy | Check identity, deployments, traces, secret usage |
| Service calls port/topic outside dependency map | Lateral movement or misconfiguration | Deny/contain, inspect flows and workload |
| Admin IAM change or auditing disabled | Privilege escalation or dangerous operation | Escalate, preserve evidence, verify change owner |
| Sudden spike in data exports | Data exfiltration or unusual legitimate job | Data owner review, query/job audit |
| Image digest outside trusted pipeline | Supply-chain compromise | Block/quarantine, locate all deployments |
| Backup deletion/retention change | Attack undermining recovery capability | Protect vault, break-glass review, incident response |

### 13.3. Incident Response

Runbooks should describe:
1. Severity classification and incident command authority.
2. Scope confirmation: users, workloads, accounts, data, regions, and dependencies.
3. Containment: revoke tokens, disable principals, isolate workloads, block egress, or freeze deployments.
4. Preserve evidence and retain audit/logs per policy.
5. Eradication: rebuild images, rotate secrets/keys, fix policies/configs, and remove persistence.
6. Recovery: deploy known-good artifacts, restore data if needed, verify identity/network/data controls.
7. Post-incident: assess blast radius, notification/legal obligations, lessons learned, and remediation owners.

Containment must balance availability and integrity. Revoking a shared key could bring down hundreds of services; understand the blast radius and maintain a safe rotation path.

## 14. Threat Modeling to Select the Right Controls

Threat modeling helps teams systematically examine how a system could be attacked. STRIDE, attack trees, or internal methodologies can be used.

### 14.1. Steps

1. Identify assets and security objectives.
2. Draw data flows and trust boundaries.
3. Enumerate principals, entry points, protocols, and permissions.
4. Identify threats across confidentiality, integrity, availability, and other obligations.
5. Assess likelihood/impact and existing controls.
6. Select mitigations; record residual risk, owner, and deadline.
7. Test and update when the architecture changes.

### 14.2. Threat Model Example for a Booking API

| Threat | Asset/Attack Path | Controls |
| --- | --- | --- |
| Spoofing | Impersonating client/service | MFA, token validation, workload identity, mTLS |
| Tampering | Altering bookings or events | Authorization, integrity checks, signed artifacts/events where appropriate |
| Repudiation | Unable to identify who changed state | Audits with actor, correlation ID, and integrity protection |
| Information disclosure | Reading another tenant's bookings | Object-level authorization, DB policies, cache isolation |
| Denial of service | Flooding API or worker queues | WAF/rate limits, quotas, backpressure, capacity |
| Elevation of privilege | Workload acquiring admin rights | Least privilege, short-lived identity, admission/runtime controls |

STRIDE helps categorize threats, but does not automatically yield probabilities or risk levels. Examine the actual implementation and real-world context.

### 14.3. Security Tests Must Verify Denied Paths

Beyond happy paths, test accessing another tenant's resources; tokens with wrong audience/issuer, expired, or revoked; workloads calling disallowed dependencies; pods/images running with privileges outside policy; APIs receiving abnormal methods/parameters; secret rotation; artifacts without valid provenance; and logs/exports not leaking sensitive data.

## 15. Real-World Scenario: Multi-Tenant Cloud Booking SaaS

A SaaS platform serving multiple enterprises has web/mobile clients behind a CDN/WAF/API gateway; Booking, Inventory, Payment, and Notification services; a transactional database, object storage, and a message broker; Kubernetes for some workloads and a managed container platform for workers; plus CI/CD, a registry, a secret manager, and external SaaS providers.

Requirements: prevent cross-tenant access; limit impact if a service is compromised; allow operations teams to troubleshoot production with auditing; keep bookings working when the notification provider fails.

~~~mermaid
flowchart TB
    USER["User + device context"] --> IDP["Identity provider / MFA"]
    IDP --> EDGE["WAF + API gateway"]
    EDGE --> AUTHZ["Application authorization"]
    AUTHZ --> BK["Booking service identity"]
    BK --> INV["Inventory service identity"]
    BK --> PAY["Payment boundary"]
    BK --> DB[("Tenant-aware booking data")]
    BK --> OUT["Outbox"]
    OUT --> BR["Private broker"]
    BR --> NOTI["Notification worker identity"]
    NOTI --> MSG["Email/SMS provider"]
    SEC["Security monitoring / SIEM"] -. "Identity, network, data, deployment logs" .-> OBS["Central audit and response"]
    BK -.-> OBS
    INV -.-> OBS
    PAY -.-> OBS
    NOTI -.-> OBS
~~~

### 15.1. Controls by Flow

| Flow | Controls |
| --- | --- |
| User → API | Policy-driven MFA/SSO, TLS, WAF, rate limiting, and token validation |
| API → Booking service | Service identity, authorization, and trace correlation |
| Booking → Inventory | mTLS/identity, reservation API permissions, timeouts |
| Booking → Database | Private endpoint, DB identity, minimal schema/operation privileges |
| Booking → Broker | Producer-only permissions on required topics |
| Worker → Broker | Consumer-only permissions, verified tenant context |
| Worker → Email/SMS | Egress allowlist, dedicated secrets, quotas |
| Operator → Production | JIT privilege, approval, MFA, session recording/auditing |
| CI/CD → Runtime | Artifact provenance, image digest, scoped deploy identity |

### 15.2. Verification

- A tenant A user cannot read or modify tenant B bookings via any API or query path.
- A notification outage does not lose committed bookings; the outbox is safely retried.
- The Booking service cannot read Payment secrets or administer the cluster.
- Images from outside the trusted pipeline are rejected from deployment.
- Break-glass actions trigger alerts, are audited, and expire on schedule.
- Unnecessary egress from workers is blocked; telemetry still works.
- Backup restores can be read using the approved recovery identity.

## 16. Trade-Offs: Security, Availability, Performance, and Cost

| Decision | Benefits | Trade-Offs / Risks |
| --- | --- | --- |
| MFA/step-up for sensitive actions | Reduces credential compromise risk | Adds interaction friction, recovery, and support overhead |
| Short-lived tokens | Shrinks misuse window of leaked credentials | Depends on identity service/refresh flows |
| mTLS/service identity | Mutual workload authentication | Certificate lifecycle and troubleshooting complexity |
| Default-deny egress | Reduces data exfiltration | Requires allowlist and dependency management |
| Strict network segmentation | Limits lateral movement | Increases DNS, connectivity, and policy complexity |
| Centralized logging | Improves investigation capability | Cost, privacy, retention, and access control |
| Image verification/admission | Blocks untrusted artifacts | Pipeline/registry outages can block deployments |
| Multi-account isolation | Reduces blast radius | Adds cross-account IAM, networking, and operational overhead |

### 16.1. Avoiding New Single Points of Failure

Centralized identity, KMS, policy engines, and logging are valuable but can also become critical dependencies. The design must consider:
- What happens when the identity provider or KMS is unavailable?
- Can running workloads continue with already-issued tokens/secrets within safe limits?
- Are valid caching/renewal mechanisms and clear expiration bounds defined?
- Does break-glass exist for emergency administration without leaving everyday privileges open?
- If the policy engine fails, is it fail-closed or what degraded behavior is permitted?
- Does a log collector failure cause business requests to fail?

Do not bypass security simply to keep uptime. Determine which operations must fail closed, which can use previously verified state for a bounded time, and which can be queued.

## 17. Measuring Security Effectiveness

| Objective | Example Metrics | Interpretation |
| --- | --- | --- |
| Identity | MFA coverage, stale accounts, privileged standing access | Which principals are out of policy compliance? |
| Least privilege | Excess permissions, unused privileges, JIT duration | Are permissions broader/longer than needed? |
| Workload | Image provenance coverage, vulnerability remediation age | Which artifacts are unverified or carry open vulnerabilities? |
| Network | Unknown flows, denied egress anomalies, exposed endpoints | Are there unusual flows or unintended public resources? |
| Data | Encryption coverage, access anomalies, retention exceptions | Is data protected and accessed properly? |
| Detection | Time to detect, time to contain, incident recurrence | Are detection and containment effective? |
| Recovery | Restore success, key recovery tests, backup immutability | Can we recover reliably? |
| Delivery | Policy violations in pipeline, emergency bypass count | Are controls integrated into delivery? |

Do not optimize metrics by suppressing alerts at all costs. Measure detection quality, false positives, coverage of critical assets, and missed incidents. Metrics must have definitions, sources, owners, and measurement cadences.

## 18. Sample Architecture Decision Record

~~~markdown
# ADR-072: Adopting Zero Trust for Service-to-Service Communication in the Booking Platform

Status: Proposed / Conditionally Approved
Decision owners: Security Architect + Platform + Application Owner
Date: YYYY-MM-DD

Context:
- Multiple services and workloads run across heterogeneous platforms.
- The internal network is currently treated as a relatively trusted zone.
- Some workloads use shared credentials and broad permissions.
- The SaaS handles multi-tenant data.

Objectives:
- Verify workload identity for sensitive flows.
- Scope permissions by service, tenant, resource, and action.
- Reduce lateral movement and credential lifetimes.
- Capture audit trails for detection and investigation.

Options:
A. Continue relying primarily on the network perimeter.
B. Workload identity + least privilege + phased segmentation.
C. Force immediate migration of all traffic to a service mesh.

Proposed Decision:
- Choose B; prioritize Booking, Payment, database, and broker.
- Use short-lived identities, specific policies, and tested default-deny
  for each trust boundary.
- Add telemetry and runbooks before expanding further.

Trade-offs:
- Requires certificate/token lifecycle management, policy ownership, and migration.
- Identity/policy failures can impact availability.

Acceptance Evidence:
- Negative authorization tests and cross-tenant tests.
- Workloads cannot read out-of-scope secrets or endpoints.
- Key/credential rotation without causing outages.
- Incident exercises proving containment and auditing.

Review Triggers:
- New workloads/tenants, threat model changes,
  high policy false positives, or SLO impact.
~~~

The ADR should attach data flows, threat models, policy owners, security test results, and rollback plans. Never roll out sweeping identity/network changes all at once without mapping dependencies first.

## 19. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming internal network/VPN is safe | Lateral movement once a device/workload is compromised | Verify identity and permissions per resource |
| Turning on MFA and calling it Zero Trust | Broad permissions and workload identities remain uncontrolled | Combine verify explicitly, least privilege, and assume breach |
| Gateway authenticates and services skip authorization | BOLA/cross-tenant data exposure | Enforce object/tenant/action checks at service/data layers |
| Sharing one credential across workloads | Hard to trace and large blast radius | Distinct identities, short-lived credentials |
| Encrypting storage only | Data can still be read by overly privileged principals | Authorization, key governance, and auditing |
| Default-deny without a dependency map | DNS, telemetry, secrets, or backups break | Inventory flows, test allow/deny, and follow change processes |
| Buying disconnected security tools | Alert fatigue and fragmented logs | Integrate telemetry and assign owners for each control |
| Leaving CI/CD and registries unprotected | Malicious artifacts deployed with valid privileges | Isolated builds, provenance, signing, and scoped deploy identities |
| Backups sharing production admin rights | Attackers destroy recovery copies too | Separate vaults/accounts, immutability, and approvals |
| Logging raw tokens/PII | Audit system becomes a leak source | Redaction, access/retention policies |
| Failing closed everywhere without analysis | Identity/KMS outages cause widespread disruption | Risk- and action-based degraded behavior |
| Failing open to preserve availability | Unauthorized access when policy service fails | Clear default policies; fail closed for sensitive operations |
| Skipping negative path testing | Only proves legitimate users work | Test denies, expired tokens, tenant mismatches, and privilege abuse |
| Lacking owners/policy lifecycles | Policy drift and permanent exceptions | Owners, review dates, expirations, and audits |

## 20. Hands-On Exercise

A cloud-hosted multi-tenant booking SaaS platform includes an API gateway, Booking service, Payment service, Inventory service, database, object storage, message broker, Kubernetes cluster, CI/CD, and external SaaS providers. Currently, services share several credentials; the application subnet has fairly broad access to the database and broker; and support engineers hold standing production privileges. Product needs checkout continuity, while Security requires reducing cross-tenant access risks.

Complete the following:

1. List assets, data classifications, and trust boundaries; draw data flows across clients, gateway, services, database, broker, and SaaS.
2. Write a threat model using STRIDE or an equivalent method; prioritize at least six threats with owners.
3. Design human identity, workload identity, token validation, and JIT privileged access.
4. Define RBAC/ABAC policies for tenant-scoped booking reads; write at least five allow/deny test cases.
5. Design network segmentation, egress allowlists, and service-to-service authentication; explain how to roll them out without causing outages.
6. Select controls for container images, registries, CI/CD, secrets, certificates, and the cloud control plane.
7. Design encryption/key lifecycles, backup isolation, data retention, and auditing.
8. Describe detection use cases and incident response when a workload is compromised or a secret is leaked.
9. Evaluate identity provider/KMS unavailability; define fail-closed/degraded behavior by risk level.
10. Propose metrics and experiments proving Zero Trust improves security without breaking checkout SLOs.
11. Write an ADR covering options, trade-offs, residual risk, migration order, rollback, and review triggers.

**Self-assessment criteria:** a strong solution does not merely add a firewall, MFA, or service mesh. It defines principals, resources, permissions, and trust boundaries; tests both allowed and denied paths; reduces privileges and blast radius; includes detection/response; and proves correct behavior under failure.

## 21. Zero Trust and Defense-in-Depth Review Checklist

- [ ] Assets, data classifications, owners, and sources of truth are defined.
- [ ] Data flows/trust boundaries cover users, devices, workloads, partners, and the control plane.
- [ ] No access is granted solely because requests originate from an internal network.
- [ ] Human identities have appropriate MFA/conditional access; account lifecycles are clear.
- [ ] Every workload has a distinct identity, short-lived credentials, and least privilege.
- [ ] Tokens validate issuer, signature, audience, expiry, and required scopes.
- [ ] Authorization checks action, resource, ownership/tenant, and classification.
- [ ] JIT/break-glass admin access has approvals, auditing, expiration, and review.
- [ ] East-west segmentation, egress controls, and default-deny are tested.
- [ ] Applications/APIs enforce validation, object-level authorization, and rate limiting.
- [ ] Containers/runtimes are hardened; images have provenance and vulnerability policies.
- [ ] CI/CD, registries, artifact signing, and deploy identities are protected.
- [ ] Secrets/certificates/keys have lifecycles, rotation, revocation, and auditing.
- [ ] Data encryption, backup isolation, retention, and restores are verified.
- [ ] The cloud control plane has guardrails, auditing, and drift detection.
- [ ] Logs are redacted, access-controlled, integrity-protected, and stored in the right regions.
- [ ] Detection use cases, incident runbooks, and escalation owners are defined.
- [ ] Threat models and negative security tests are updated with architectural changes.
- [ ] Identity/KMS/policy dependencies have availability and degraded-mode plans.
- [ ] ADRs document trade-offs, residual risk, rollout/rollback, and review triggers.

## Key Takeaways

**Zero Trust** requires verifying every principal and access request in context; **defense in depth** places multiple complementary control layers to prevent, detect, and limit damage when one layer fails. Internal networks, VPNs, gateways, Kubernetes, or cloud providers do not automatically create absolute trust.

A strong cloud security architecture combines **identity, least privilege, segmentation, application authorization, workload hardening, data protection, supply-chain security, detection, and response**. Every control must map to concrete assets and threats, have an owner, and be verified under real operating conditions. Security is only sustainable when it simultaneously preserves correctness, availability, performance, scalability, and acceptable cost.
