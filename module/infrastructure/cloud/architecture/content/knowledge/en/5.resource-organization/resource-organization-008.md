# Provisioning, Handover, and Decommissioning Environments

> **Chapter:** Resource Organization  
> **Module:** CLOUD_ARCHITECTURE  
> **Scope:** Designing cloud application architectures from business needs to networking, compute, data, and deployment choices; balancing reliability, security, scalability, cost, and operations using Well-Architected thinking.

## Learning Objectives

After this lesson, you can:

1. Describe the lifecycle of a cloud environment from **request, approval, provisioning, validation, operational acceptance, and change management to decommissioning**.
2. Define the environment request record, owners, access permissions, resource labels, budgets, limits, and required control checkpoints.
3. Distinguish between provisioning **technical resources** and **handing over a ready-to-use environment** with acceptance criteria and accountable owners.
4. Build a decommissioning workflow that checks dependencies, data, backups, access revocation, cost stoppages, and completion evidence.
5. Apply Infrastructure as Code (IaC), automated policy checks, and configuration drift management to make the workflow repeatable.
6. Analyze trade-offs across provisioning speed, isolation strength, security, reliability, and cost using Well-Architected questions.

## 1. Why Does a Cloud Environment Need a Lifecycle Process?

An **environment** is a collection of resources, configurations, identities, access permissions, data, and operational processes serving a specific purpose—such as development, integration, testing, staging, or production. It may live inside a dedicated account/subscription/project, an isolated namespace within a shared cluster, or across multiple services. Exact names and technical boundaries depend on the cloud provider and required isolation level.

Cloud's rapid provisioning speed cuts both ways: product teams can spin up experiments quickly, yet unowned resources, inconsistent security configurations, live data inside test environments, and lingering costs after projects end also accumulate easily.

For example, a team spins up an environment to test a search feature for two weeks. If the only step is "create database + VM," two weeks later nobody may know:

- Who is authorized to decide whether the environment is still needed?
- Does the database hold personal data or only sample data?
- Do operators know where endpoints, logs, backups, and recovery procedures reside?
- Which resources are shared with other systems and cannot be deleted without breaking them?
- Do CI/CD account permissions, secrets, and API tokens still remain active after the environment stops?
- Who verifies that billing actually stopped?

A sound process must provide **end-to-end traceability and accountability**, not merely a resource creation script.

### 1.1. Environment Types and Distinguishing Principles

| Type | Purpose | Typical characteristics / controls |
|---|---|---|
| **Development (dev)** | Daily development and testing changes | Low cost, reproducible; synthetic data; does not require production-grade HA |
| **Integration/test** | Integration, contract, and functional verification | Resettable test data; automated spin-up/teardown; scoped permissions and appropriate mock integrations |
| **Ephemeral/preview** | Testing per branch, pull request, or short task | Has TTL, owner, budget; auto-closes upon completion |
| **Staging/pre-production** | Validating near-production conditions and rehearsing releases | Production-equivalent configs and critical paths; still requires data protection |
| **Production (prod)** | Serving live users | Change control, monitoring, backup/DR, access control, and operational policies matching business needs |
| **DR/standby** | Recovery from defined incidents | Data, cross-region failover/recovery, and RTO/RPO must be tested—not just provisioned |

**Staging does not have to match production in raw scale**, but it must be similar enough to exercise key risks: configurations, network policies, deployment mechanics, schemas, authentication, and required integrations. If production data must be used for testing, there must be an authorized basis, minimization/anonymization, and matching access/retention controls; synthetic data is preferred by default.

### 1.2. Provisioning, Handover, and Decommissioning Are Three Distinct Checkpoints

- **Provisioning:** creating and configuring resources, connectivity, identities, policies, observability, and platform capabilities per an approved design.
- **Acceptance/handover:** confirming the environment works for its intended purpose, passes technical checks, and is formally accepted by owners and operators.
- **Decommissioning:** confirming the environment is no longer needed, handling data and dependencies, revoking permissions, tearing down scoped resources, and verifying final state and billing.

Marking provisioning as "success" only means a script finished running. It **does not prove the application can be accessed safely, data can be recovered, or the ops team knows how to respond to incidents**. Conversely, an environment that stopped serving requests while databases, snapshots, IPs, logs, keys, and auxiliary resources linger is not fully decommissioned.

## 2. Lifecycle Model and Responsibilities

### 2.1. Reference State Flow

~~~mermaid
flowchart TD
    A[Requested: request record submitted] --> B{Review / Approve}
    B -- Needs info --> A
    B -- Rejected --> X[Rejected / Closed]
    B -- Approved --> C[Approved]
    C --> D[Provisioning via IaC]
    D --> E{Technical checks}
    E -- Failed --> F[Fix / Re-provision]
    F --> D
    E -- Passed --> G[Ready for acceptance]
    G --> H{Owner and ops accept?}
    H -- Not yet --> I[Remediate / complete docs]
    I --> G
    H -- Yes --> J[Active: in use and monitored]
    J --> K[Change / Periodic review]
    K --> J
    J --> L[Decommission requested]
    L --> M{Confirm data / dependencies / approval}
    M -- Insufficient --> J
    M -- Sufficient --> N[Quiesce / export / revoke / destroy]
    N --> O{Verify teardown}
    O -- Remaining resources or dependencies --> P[Controlled cleanup]
    P --> O
    O -- Complete --> Q[Retired / Closed]
~~~

The states above represent a recommended process model independent of any specific tool. In practice, record timestamps, approvers, request IDs, test results, and transition evidence. For production, decommissioning may require dedicated approval due to high impact and data retention obligations.

### 2.2. Who Is Accountable?

Common roles:

| Role | Primary responsibilities |
|---|---|
| **Business/service owner** | Defines purpose, priorities, business requirements, and accepts cost and residual risk |
| **Technical/application owner** | Defines workloads, dependencies, resource specs, application testing, and data handling |
| **Platform/cloud team** | Provides landing zone templates, IaC modules, guardrails, networking, core identities, and observability |
| **Security/compliance** | Defines access policies, data classification, storage regions, logging mandates, and exception rules |
| **Operations/SRE** | Verifies monitoring, on-call readiness, runbooks, backup/restore, change control, and recovery |
| **FinOps/budget owner** | Reviews budgets, cost-allocation tags, alerts, and idle resources |

One person may fill multiple roles in a small team, yet **every environment still needs at least one accountable owner and a designated operational channel**. Never leave an environment owned by an individual who left the team without assigning a replacement.

Example RACI table (R = Responsible, A = Accountable, C = Consulted, I = Informed):

| Activity | Service owner | Platform | Security | Operations | FinOps |
|---|---|---|---|---|---|
| Confirm need & lifespan | **A/R** | C | C | I | C |
| Design/provision foundation | C | **A/R** | C | C | I |
| Approve security exceptions | C | C | **A/R** | I | I |
| App & operational acceptance | **A** | R | C | R | I |
| Review cost/TTL | **A** | R | I | I | R |
| Approve retirement & data handling | **A** | R | C | C | I |
| Confirm resource teardown | I | **A/R** | C | R | C |

This matrix is illustrative: organizations may assign duties differently, but avoid any step lacking both an owner and a verifier.

## 3. Step 1 — Intake Request and Scope Definition

An environment record should capture enough detail to define **purpose, risk level, boundaries, and end-of-life** up front. Creating environments without this information makes networking, permissions, cost, and data decisions difficult.

### 3.1. Minimum Required Information

| Field | Example | Why needed |
|---|---|---|
| Request ID and requester | ENV-2026-042, Booking team | Trace decisions and changes |
| Name/service and environment type | booking-preview-pr-248, preview | Tie to workload and purpose |
| Business/technical owner | Booking team, team on-call rotation | Confirm need and handle incidents |
| Start date, expiration/review cycle | 14 days, review every 7 days | Prevent abandoned resources |
| Region and geographic rules | Region near target users; data stored per policy | Latency, compliance, service availability |
| Data classification | Synthetic, no PII | Determines permissions, backups, logging, and retention |
| Required components | API, relational DB, queue, object storage | Estimate costs and dependencies |
| Load and reliability targets | 50 req/s test load; no production HA required | Pick sizing and deployment model |
| Network/ingress/egress | CI + QA access via auth only, restricted egress | Define trust boundaries |
| Access and integrations | QA team, test pipeline, mocked providers | Determine identities and connectivity |
| Budget estimate + budget owner | Test spend cap and alerts | Prevent runaway resource bills |
| Shared dependencies and data | Uses sandbox DNS, no production payment connection | Prevent accidental deletion or dangerous links |
| Termination condition | PR closed or TTL expired, post-review | Basis for timely reclamation |

Not every environment needs an approval board. For low-risk types with established guardrails, enable **self-service provisioning** from templates. Cases involving sensitive data, public ingress, large budgets, privileged roles, or production deployments require deeper review.

### 3.2. Example Declarative Request

This YAML snippet illustrates an **input record for a custom workflow**, not a standard schema for AWS/Azure/GCP or a specific IaC tool:

~~~yaml
requestId: ENV-2026-042
service: booking-api
environment: preview
purpose: "Test PR-248: time-slot filtering feature"
owners:
  businessTeam: booking
  technicalTeam: booking-platform
  supportChannel: "booking-oncall"
lifecycle:
  requestedAt: "2026-11-18"
  expiresAt: "2026-12-02"
  reclaimOn: "pull-request-closed-or-TTL"
data:
  classification: synthetic
  productionCopyAllowed: false
location:
  region: "organization-approved-region"
network:
  publicIngress: false
  egressPolicy: restricted
workload:
  apiInstances: 1
  database: managed-relational-small
  queue: managed-queue
budget:
  alertThresholdPercent: 80
  ownerTeam: booking
dependencies:
  sharedDnsZone: sandbox.example.test
  paymentProvider: mocked
acceptance:
  technicalOwner: booking-platform
  operationsOwner: booking-oncall
~~~

Values such as region name, resource sizes, and quotas are examples only. In real implementations, the intake system must validate schema, requester permissions, allowed values, expiration dates, and service availability in the target region.

### 3.3. Policy Checks and Approval

Before approving, verify:

1. **Purpose and owner:** which service does the workload belong to, and who is accountable at expiration?
2. **Region and data:** does it comply with data residency, security, and retention rules?
3. **Access boundary:** does it need public Internet or only internal networks? Does it connect to production?
4. **Budget and quotas:** does it fit within account/project limits and cost estimates?
5. **Architecture:** what zone redundancy, backups, and SLOs are required? Does it use organization-approved services?
6. **Shared dependencies:** are there resources owned by other teams requiring coordination during creation and teardown?
7. **Lifespan:** what is the expiration date or trigger for review/reclamation?

Common checks can be automated: naming conventions, required tags, region allowlists, permitted instance types, blocking public databases, mandatory encryption, CIDR limits, least privilege, budgets, and TTLs. Exceptions require an approval ID, justification, expiration date, and accountable owner.

## 4. Step 2 — Controlled Design and Provisioning

### 4.1. Choosing the Right Isolation Boundary

| Option | Pros | Limitations and when to be cautious |
|---|---|---|
| **Dedicated account/subscription/project** | Clear quota, IAM, billing, and policy boundaries; minimizes cross-impact | Increases work to configure connectivity, policies, and multi-account governance |
| **Separate virtual network within an account** | Dedicated route/firewall controls; easy access to shared services | Still shares certain quotas, IAM, billing, and admin tiers |
| **Namespace inside a shared cluster** | Fast creation, efficient resource utilization | Namespaces are not strong security boundaries by default; evaluate RBAC, NetworkPolicy, node sharing, secrets, and quotas |
| **Shared resources with logical partitioning** | Lowers cost for small environments | Prone to resource contention, data leaks, or accidental deletion without strict permissions and ownership |

Production or sensitive data typically demands stronger isolation than preview environments. Never decide based solely on resource savings: consider blast radius, admin rights, audit needs, quotas, and incident response time.

### 4.2. Provisioning with Versioned Infrastructure Templates

**Infrastructure as Code (IaC)** declares desired state and enables change review before apply. A typical workflow:

~~~mermaid
sequenceDiagram
    actor Requester as Service owner
    participant Portal as Request portal / Git PR
    participant Policy as Policy / Approval
    participant Pipe as IaC pipeline
    participant Cloud as Cloud control plane
    participant Check as Validation / Inventory
    Requester->>Portal: Submit request with owner, TTL, budget, data
    Portal->>Policy: Validate schema, permissions, policies, and estimate
    alt Failed
        Policy-->>Requester: Return reasons and required fixes
    else Approved
        Policy->>Pipe: Authorize plan/apply for reviewed version
        Pipe->>Cloud: Create resources and scoped permissions
        Cloud-->>Pipe: Resource IDs and status
        Pipe->>Check: Verify policies, networking, logging, backups
        Check-->>Portal: Evidence + inventory + status
    end
~~~

**Essential template components** typically include account/project structure, networking and routes, IAM/workload identities, KMS/secrets, compute, datastores, logging/metrics, appropriate backups, budget/tags/owners, and policies. Avoid duplicating manual configurations across environments when shared IaC modules can manage them.

Inside the pipeline:

- Changes must be **reviewed via diff/plan**, clearly highlighting operations that create, modify, replace, or destroy resources.
- Deployment identities hold least-privilege permissions strictly scoped to the target and are protected from use outside the pipeline.
- IaC state is stored securely with locking/concurrency controls and strict access control; state files can contain sensitive values.
- Enforce policy-as-code or organizational config checks; never grant broad permissions just to make a pipeline "run easily."
- Provisioning results must register in inventory with resource IDs, owners, request IDs, TTLs, and operational contacts.

Illustrative **pseudocode** showing the steps, not vendor-specific syntax:

~~~text
validate(request) -> check_owner_policy_budget_ttl()
design = generate_iac_from_approved_template(request)
review(design.plan) -> approve_with_change_record()
apply_with_scoped_identity(design)
verify(network, iam, tags, encryption, monitoring, backup)
register_inventory(resource_ids, owner, ttl, dependency_graph)
create_acceptance_package()
~~~

### 4.3. Naming Conventions, Labels, and Inventory

Establish discoverable, meaningful names without embedding secrets or personal data. Example:

~~~text
Logical name: booking-preview-pr248-api
Tags/labels:
  service      = booking
  environment  = preview
  ownerTeam    = booking-platform
  costCenter   = product-booking
  requestId    = ENV-2026-042
  lifecycle    = ephemeral
  expiresAt    = 2026-12-02
  managedBy    = iac
~~~

Names and tags do not replace provider-assigned **resource IDs**. Inventory should record exact IDs, account/project/region, status, ownership and dependencies, creation timestamp, IaC version, backup policy, estimated/actual cost, and expiration. Services lacking full tag support need dedicated inventory mappings. Periodically scan for unowned resources or resources outside IaC state to catch drift.

### 4.4. Cost and Scalability Controls at Creation Time

Include at provisioning time:

- **Budgets and alerts:** budget owner, tracking thresholds, escalation paths, and actions when forecasts exceed targets.
- **Quotas/service limits:** prevent new environments from consuming quotas required by production.
- **Capacity policies:** environment-specific default sizes, autoscaling ceilings, and anomaly spend caps.
- **Retention/lifecycle:** explicit lifespans for logs, snapshots, objects, volumes, and temporary resources.
- **Accountability:** tags and cost reports grouped by service, environment, owner, or cost center.

Budget alerts are usually just signals with billing latency; **never assume they automatically prevent runaway spend**. Strict caps require combining quotas, policies, capacity design, and operational controls.

## 5. Step 3 — Post-Provisioning Validation and Technical Acceptance

An environment moves to **Ready for acceptance** only after producing evidence that it meets the approved design. Separate two validation layers:

1. **Infrastructure validation:** resources exist, network paths match diagrams, policies are active, permissions and labels are accurate, and observability is flowing.
2. **Workload validation:** application deploys cleanly, sample business flows succeed, data and integrations are in known states, and owners can take over.

Merely provisioning a database without testing a connection using a valid identity or verifying its backup policy is not sufficient for acceptance.

### 5.1. Acceptance Checklist and Evidence

| Validation group | Illustrative pass criteria | Evidence to retain |
|---|---|---|
| **Identity/IAM** | Users and workloads hold task-scoped permissions only; admin access uses MFA if required | IAM audit results, approved roles, access-denied test outputs |
| **Network** | Ingress/egress, subnets, routes, and firewalls match diagrams; DB is not directly Internet-exposed | Network tests, policy configs, external connection test results |
| **Encryption & secrets** | TLS, encryption at rest, secrets managed via vault; none in code or logs | Policy scans, config outputs, secret-handling checks |
| **Compute & storage** | Correct type/size/region; app boots and reaches datastores | Smoke tests, health checks, resource specs |
| **Data** | Data matches classification; synthetic data in preview; restricted read/write access | Classification report, retention config, access tests |
| **Observability** | Required logs, metrics, and traces are flowing; alerts route to right team | Dashboards, alert test logs, on-call routing links |
| **Reliability** | Replica/backup configs match environment tier; restore tested where required | Backup & restore drill results, runbooks, measured RTO/RPO |
| **Delivery** | Deployment and rollback pipelines work; no undocumented manual steps | Release/smoke test logs, artifact IDs, rollback plan |
| **FinOps** | Tags/owners complete, budgets/alerts/quotas active; estimated cost confirmed | Cost sheet or report, policy gate outputs |
| **Inventory** | Resource IDs, IaC boundaries, dependencies, and TTLs registered | Inventory snapshot, request/change links, owner |

Not every dev environment needs production-grade DR or SLOs. **Acceptance criteria must match the requested service tier**, with exceptions approved by an owner and given a review deadline.

### 5.2. Cross-Layer Smoke Test

For a booking application, a minimum test suite might:

1. Authenticate using the environment's auth mechanism and verify endpoint permissions.
2. Call the search API, confirming TLS, routing, load balancing, and log/correlation IDs.
3. Create a booking with synthetic data; verify the transaction and database access permissions.
4. Publish a test event to the queue and confirm the worker consumes, processes, and persists results without accidentally calling a production provider.
5. Resend the same idempotency key; confirm no duplicate booking is created.
6. Inspect telemetry across API, database, worker, and test alerts; clean up test data per policy.

For environments requiring fault tolerance, add a scope-appropriate single-instance/zone failure test; for environments needing backups, ensure at least a restore test schedule and designated executor exist. Checking "API returns 200" never replaces testing authorization, data integrity, or recovery.

### 5.3. Handling Acceptance Failures

When a check fails, record **failure condition → impact severity → remediation action → accountable person → re-test**. When configurations must change, prefer fixing the IaC source and re-applying through the workflow rather than applying manual patches that cause environment divergence.

For severe security issues—such as an unexpectedly public database or missing identity controls—never hand over the environment as ready. For low-risk issues temporarily accepted, record a formal exception specifying details, owner, and expiration date.

## 6. Step 4 — Operational Handover and Acceptance

**Handover** is transferring all information required to use and maintain the environment; **acceptance** is confirming real operational ownership. Simply sending a console URL saying "it's up" leaves responders during an incident unsure who has permissions, whom to page, or which actions are safe.

### 6.1. Minimum Handover Package

An **acceptance package** may include:

- **Environment identity:** name, account/project/subscription ID, region, environment type, status, owner, request ID, inventory link.
- **Logical and dependency diagrams:** ingress/egress, network boundaries, compute, datastores, queues, secrets, DNS, shared services, and third-party links.
- **IaC documentation:** repository/config paths, applied version/tag, pipelines, state backend location, and change review process.
- **Access and permissions:** user groups, workload identities, grant/revoke workflows, MFA rules, and emergency access procedures if applicable.
- **Application delivery:** build artifacts, runtime/environment settings, release process, smoke tests, and rollback or roll-forward handling.
- **Observability:** dashboards, logs, tracing, business metrics, alerts, severity tiers, and notification channels.
- **Recovery:** backup schedules/retention, HA/DR scope, restore procedures, drill results, and RTO/RPO targets if applicable.
- **Data and security:** classification level, data owner, retention limits, rules on live data usage, key/secret rotation, and audit logs.
- **Cost and lifecycle:** budgets, alerts, tags/cost centers, quotas, review/TTL dates, and decommissioning triggers and contacts.
- **Residual risks:** accepted exceptions, design limits, and remediation plans.

Handover documents should **point to centrally managed locations** instead of pasting passwords, private keys, or tokens into documents. Secrets belong in a secrets manager; documentation only explains how to request and use access.

### 6.2. Acceptance Record Template with Verification Criteria

| Item | Illustrative value |
|---|---|
| Environment | booking-staging |
| Business owner | Booking team |
| Technical owner | Backend team |
| Operations/on-call | Platform/SRE team |
| Infrastructure version | Specific IaC commit/release reference |
| Workload version | Successfully tested artifact reference |
| Passed checks | Policy scan, smoke test, alert routing, backup check |
| Failed checks / exceptions | Issue ID, owner, remediation deadline, and impact |
| RTO/RPO | Concrete per-scenario values if business-required |
| Estimated cost | Per stated load model; paired with approved budget |
| Expiration/review | Date and review owner |
| Conclusion | Accepted / Accepted with approved exceptions / Rejected |

To transition to **Active**, the final accountable owner must sign off on results and operations must confirm they have the required **information, permissions, and tools**. Record acceptance timestamp, sign-off person, and accepted configuration version. For ephemeral preview environments spun up and torn down continuously, acceptance can be automated via policies and tests instead of manual sign-offs each time.

### 6.3. Distinguishing Application Acceptance from Infrastructure Acceptance

The platform team can hand over working VPCs, IAM, clusters, or databases, yet the **application owner** must still validate deployments, business flows, and data management. The operations team accepts on-call/runbooks without automatically becoming the business or data owner. Document responsibility boundaries clearly to prevent "infrastructure is green, application is broken" finger-pointing.

## 7. Step 5 — Maintaining the Environment During Active Use

After acceptance, the environment becomes **Active** and requires ongoing monitoring of configurations, permissions, resources, costs, and lifespans.

### 7.1. Review Cadences

| Event / cadence | Activities | Who participates |
|---|---|---|
| On release or infra change | Review IaC plan, policies, backward compatibility, rollout/rollback | Technical owner + Platform, Security per risk |
| Short cadence for previews | Check TTL, linked PRs, active owner, cost | Pipeline/automation and owner |
| Periodic per org policy | Audit IAM, tokens, public exposure, alerts, backups | Platform, Security, Operations |
| When SLO/capacity changes | Load tests, scale limits, quotas, budgets, concentration risks | Service owner, Operations, FinOps |
| On owner or team transfer | Hand over inventory, alerts, permissions, and docs | Outgoing owner, incoming owner, Operations |
| Prior to expiration | Confirm extension or initiate decommissioning | Service owner, Platform, data steward if relevant |

Review frequency is an internal decision tailored to environment type, data sensitivity, and impact. Never assume all previews must run 24/7 or that staging can be shut down anytime: align schedules with actual usage and identified risks.

### 7.2. Detecting Drift and Orphaned Resources

**Configuration drift** occurs when live cloud state diverges from desired IaC state—for example, someone edits a firewall rule in the console. Drift can introduce security holes, break deployments, or cause teardowns to fail.

Controls should include:

1. Periodically comparing live state against IaC/policies and logging results.
2. Opening issues/alerts for drift impacting security, reliability, or cost.
3. Defining timelines and rules for out-of-band emergency fixes; folding approved edits back into IaC.
4. Scanning for resources **without owners, without tags, outside IaC state, or unused by any app**.
5. Never auto-deleting resources merely for missing tags: verify owner, data, dependencies, and valid status first.

### 7.3. Designing Guardrailed Self-Service

A well-built self-service portal lets product teams spin up preview environments from standard templates. Delivery stays fast because core decisions are pre-encoded: allowed regions, resource types, permissions, quotas, TTLs, synthetic data, and acceptance suites. Exception requests route to an appropriate review workflow rather than granting broad admin rights.

This is an architectural trade-off: self-service reduces wait times but requires upfront investment in platform engineering, policy-as-code, inventory, and lifecycle automation. Successful self-service provisioning never absolves owners of cost or data accountability.

## 8. Step 6 — Safe, Evidenced Decommissioning

**Decommissioning is an architectural operation that can impact data and other services**, not merely running a delete command. Distinguish:

- **Suspend/stop:** pauses or scales down part of compute; volumes, IPs, logs, databases, snapshots, and managed services may continue incurring charges.
- **Retire:** shifts traffic away from the environment and ends active operational support as planned, while resources may temporarily remain to satisfy retention.
- **Decommission/destroy:** handles data per retention rules, revokes access, and destroys scoped resources after verifying safety conditions.

Never equate **TTL expiration** with **blanket permission to delete all data**. TTL is a signal to start a review or execute a pre-approved policy; production and retention-bound data still require matching approvals.

### 8.1. Triggers and Approvals

Triggers for decommissioning:

- Linked branch/PR closed, test campaign finished, or project retired.
- Expiration date reached and owner did not extend within the notice window.
- Service migrated to a replacement environment with traffic and data moved.
- Environment violates policy or lacks an active owner; requires inspection, investigation, and formal decision.

Before executing, confirm **environment ID, owner, purpose, scope, dependency graph, data, retention obligations, approver, and timing**. Preview environments holding zero real data can auto-decommission on PR close if creation policy explicitly permits it. Production, sensitive-data environments, and shared resources require higher-risk reviews and approvals.

### 8.2. Step-by-Step Decommissioning Workflow

~~~mermaid
flowchart TD
    A[Decommission request: ID, reason, owner] --> B[Check dependencies and ownership]
    B --> C{Data to retain / legal hold / dependencies?}
    C -- Yes --> D[Complete export / migration / retention / owner transfer]
    D --> E[Confirm data and termination criteria]
    C -- No --> E
    E --> F{Approval per environment type?}
    F -- Not yet --> G[Hold / resolve missing conditions]
    G --> B
    F -- Approved --> H[Stop traffic / jobs / writes and notify]
    H --> I[Revoke credentials, routes, and related permissions]
    I --> J[Review destroy plan, strictly scoped to owned resources]
    J --> K[Execute teardown via IaC/workflow]
    K --> L[Reconcile inventory, data, cost, DNS, logs]
    L --> M{Remaining resources or obligations?}
    M -- Yes --> N[Controlled cleanup and monitoring]
    N --> L
    M -- No --> O[Archive completion record and mark Retired / Closed]
~~~

The order above adapts to dependencies. For instance, export data before revoking read rights; remove or repoint DNS before tearing down endpoints; stop writers and sync data before dropping databases; revoke deployment permissions at the right moment so automation does not recreate resources. No single fixed deletion sequence fits every architecture safely.

### 8.3. Dependency Checklist by Resource Layer

| Layer | Questions to verify before removal | Easily overlooked scenarios |
|---|---|---|
| **DNS/edge** | Are domains, CDNs, WAF rules, certificates, or health checks shared? | DNS still points to deleted endpoints; auto-renewing certs keep billing |
| **Network** | Who owns IPs, NATs, VPNs, load balancers, private endpoints, peerings, and routes? | Egress/NAT or static public IPs keep charging; deleting a route breaks another system |
| **Compute/orchestration** | Are VMs, containers, jobs, schedulers, autoscaling groups, or serverless functions attached? | A scheduler or controller recreates resources right after deletion |
| **Database/storage** | Does data need export, archiving, or retention, and who holds restore rights? | Dropping DB before backing up; orphaned snapshots/volumes/objects still incur spend |
| **Queue/events** | Are unprocessed messages, subscriptions, dead-letter queues, or event rules dependent? | Lost messages or triggers firing against deleted endpoints |
| **Identity/secrets** | Are workload identities, roles, tokens, keys, secrets, or service principals dedicated or shared? | Stale credentials remain valid or shared secrets get deleted accidentally |
| **Observability** | Must logs, metrics, dashboards, alerts, or audit trails be retained per policy? | Deleting incident evidence or leaving verbose logs incurring storage fees |
| **CI/CD/IaC** | Are pipelines, state backends, env vars, deploy keys, or webhooks still active? | A job re-provisions the workload; state deleted without tracking |
| **Billing/quota** | Do out-of-band resources or delayed billing charges remain? | Bills continue rising from backups, storage, support plans, or shared fees |

**Shared resources** must transfer ownership or remain intact based on dependencies. Never allow a pipeline to wipe an entire account/project when a target environment expires if other workloads reside there.

### 8.4. Handling Data, Backups, and Retention

Before deleting data, verify:

1. **Classification and data owner:** personal data, contractual data, audit logs, test data, or retention-bound records?
2. **Retention obligations:** retention duration, legal mandates, legal holds, regulatory deletion rights, and approval authority.
3. **Migration/export verification:** was data transferred to its new home, with row counts and integrity reconciled?
4. **Backups/snapshots:** which copies stay, which must be deleted, and who manages decryption keys and expiration?
5. **Deletion method:** logical delete, resource destruction, cryptographic erasure, or provider-committed deletion per org policy; verify scope, recoverability, and risk.

**Do not hastily destroy encryption keys** while backups must still be read for retention or recovery; losing the key can make data permanently unrecoverable. Conversely, keeping backups indefinitely "just in case" violates retention rules and adds cost. Document retain/delete decisions under current policy and data-owner approval.

For preview environments using **synthetic data only**, the flow is much simpler: confirm zero real data and zero shared dependencies, then delete per approved TTL. Production requires traffic-drain plans, stakeholder notices, data reconciliation, access reviews, audit trails, and clear retention timelines.

### 8.5. IaC Teardown and Blast-Radius Control

A controlled teardown workflow should:

- Run strictly against a **verified environment ID and scope**, displaying target account/project/region and exact resource IDs slated for deletion.
- Cross-check resources against **inventory, owners, policies, tags, and state**; tags alone are only hints and insufficient to prove ownership.
- Generate a **destroy plan**, requiring risk-tiered review with special scrutiny on databases, networking, keys, and shared resources.
- Avoid deleting IaC state before confirming resources are gone. If state has drifted, follow a controlled reconcile/import/cleanup workflow.
- Log the operation, executing identity, unresolved errors, and exact decommissioned resource IDs.
- Disable pipelines, controllers, schedulers, or automation that could re-provision the environment post-teardown.

Never run a single script deleting everything matching a name prefix; that easily destroys similarly named resources and ignores dependencies. If a destroy run fails midway, record remaining state and resume cleanly—never declare completion without reconciliation.

### 8.6. When Can You Confirm "Decommissioned"?

Establish evidence-backed completion criteria:

| Category | Verification evidence |
|---|---|
| **Traffic and business flows** | No active routes or jobs writing to the environment; replacement system serving traffic if applicable |
| **Data** | Export/migration/retention/deletion completed per approved decision; retained backups have owners and expiration dates |
| **Resources** | Inventory and cloud APIs show zero target resources outside approved retained items |
| **Permissions** | Environment-specific identities, tokens, roles, and CI/CD access revoked/updated |
| **Dependencies** | DNS, webhooks, events, queues, routes, alerts, dashboards, and certificates cleaned up or transferred |
| **Cost** | Post-teardown billing reports checked across a billing update cycle; residual charges resolved |
| **Records** | Tickets/ADRs/runbooks updated with sign-off person, close date, resource IDs, and retention exceptions |

**Billing data can lag**, so "no remaining resources" and "no lingering charges on the next billing report" are two checks performed at different times. You can close the infrastructure phase after technical reconciliation while keeping a post-decommission tracking item open until billing and retention settle.

## 9. Lifecycle Automation and Edge Cases

### 9.1. Designing a TTL Controller for Ephemeral Environments

A scheduled controller can detect expired previews and execute steps such as:

~~~text
for each environment in inventory:
    if environment.lifecycle != "ephemeral":
        continue
    if not is_expired(environment) and not source_event_closed(environment):
        continue
    notify(environment.owner, proposed_reclaim)
    if has_approved_extension(environment):
        update_expiry_and_audit(environment)
        continue
    if has_legal_hold_or_unknown_owner_or_shared_dependency(environment):
        open_review_ticket(environment)
        continue
    if not satisfies_preapproved_reclaim_policy(environment):
        open_review_ticket(environment)
        continue
    quiesce_and_check_data(environment)
    review_scope_and_teardown(environment)
    reconcile_inventory_and_cost_followup(environment)
~~~

This is **logical pseudocode**, not a production script. Automated reclamation is appropriate only when resource types, permissions, data, and risks are pre-defined. TTL expiration alone never authorizes deleting production, retention-bound data, or shared resources. Detecting a missing owner must trigger an ownership-transfer or exception workflow, never be interpreted as permission to delete.

### 9.2. Tricky Scenarios Requiring Special Handling

**Scenario A — Preview shares the staging database:** destroying the preview by dropping the database impacts other teams. Separate database ownership from preview-owned data objects, dropping only scoped schemas/data with blast-radius safeguards after verifying impact and retention. For high risk, switch to isolated databases by design.

**Scenario B — Expired environment has an account with an unknown owner:** ineligible for automatic teardown. Route to a triage queue across product service owners, platform, and security, applying risk-mitigation controls while locating an owner.

**Scenario C — VMs are stopped yet the bill keeps climbing:** check volumes, snapshots, static IPs, NAT/load balancers, databases, logs, managed services, and storage fees. Stopping and destroying differ in targeted resources and billing rules.

**Scenario D — Replacing production with a new environment:** shift DNS/traffic, ensure data compatibility, and complete reconciliation before teardown. You may keep the old environment read-only or write-frozen during an observation window, but set a firm deadline and clear retain/delete decision.

**Scenario E — A broad-permission pipeline recreates the environment:** tearing down resources while forgetting to disable triggers/webhooks or deployment permissions will not stick. Transfer or disable related deployment configs, then re-reconcile cloud state.

**Scenario F — Backups still within retention, but the project owner disbanded:** transfer backup ownership to the unit holding retention obligations, documenting decryption keys, access policies, and post-retention deletion dates. Never let unowned assets persist indefinitely.

## 10. Evaluating the Process with Well-Architected

An environment's lifecycle reflects multiple architectural pillars:

| Pillar | Questions to evaluate | Verification signals |
|---|---|---|
| **Operational Excellence** | Are creation, validation, acceptance, change, and teardown repeatable? | Pipelines, tickets, runbooks, owners, provisioning lead time, operator errors |
| **Security** | Are least privilege and data classification enforced from creation through deletion? | IAM scans, encryption, auditing, post-teardown access checks |
| **Reliability** | Do environments have required backup/HA/DR and clear incident accountability? | SLOs, restore/failover tests, on-call coverage, dependency maps |
| **Performance Efficiency** | Are resources right-sized to demand with capacity reviewed? | Load tests, utilization, quotas, data-driven resizing |
| **Cost Optimization** | Are owners, budgets, TTLs, and post-teardown spend stoppage verified? | Allocation tags, per-environment spend, orphan reports |
| **Sustainability** | Is waste avoided via auto-shutdown of idle tests and storage lifecycles? | TTL compliance, active hours, preview cleanup, storage lifecycles |

Never optimize one pillar in isolation. Dropping all staging environments to cut costs weakens compatibility testing and raises production deployment risk. Conversely, keeping every preview indefinitely to "avoid accidental deletion" inflates cost, attack surface, and operational clutter. Good processes select automation and control levels based on **purpose, risk, and evidence**.

### 10.1. Process Operational Metrics

Measure:

- **Provisioning lead time:** from valid request to ready environment, segmented by risk tier to spot bottlenecks.
- **First-pass acceptance rate:** percentage of environments passing acceptance on the first try, reflecting template/guardrail quality.
- **Ownership completeness:** percentage of environments with valid owners, cost centers, dependency maps, and review cycles.
- **Policy exception age:** count of overdue or unhandled exceptions.
- **TTL compliance:** percentage of expired previews properly extended or reclaimed per policy.
- **Orphaned resource count/cost:** count and spend of resources missing owners or absent from inventory.
- **Decommission completeness:** percentage of teardowns backed by full evidence for resources, permissions, data, and billing verification.
- **Drift remediation time:** time to return configuration drift back to approved state.

Segment metrics by environment type. Never chase faster production approvals at all costs; the goal is **speed for standardized work, paired with deliberate control at high-impact gates**.

## 11. Practice Exercise: Environment Lifecycle for a Booking Service

**Context:** The Booking team operates a live production system. They need a staging environment to test schema changes and a preview environment for a new pull request. The preview will run for 10 days, spinning up an API, small database, queue, and object storage with zero real data. Staging must mock calls to the payment provider. After testing, the preview must be decommissioned; staging remains active for future releases.

Design a lifecycle specification covering:

1. **Request records:** fill in purpose, environment type, owner, expiration/review dates, data classification, networking, services, budget, and dependencies for both preview and staging.
2. **Permissions/approvals:** build a RACI across service owner, platform, security, operations, and FinOps; specify what is self-service versus mandatory review.
3. **Provisioning architecture:** diagram accounts/projects, networking, compute, database, queue, IAM, and logging; explain isolation across preview, staging, and production.
4. **IaC and policy gates:** describe template inputs and checks for public ingress, TTL, required tags, quotas, encryption, secrets, and resource ownership.
5. **Acceptance:** build an evidence-backed checklist covering smoke tests, access rights, logs/alerts, backups if required, mock payment checks, and cost estimates.
6. **Handover:** propose an acceptance package listing owners, runbooks, dashboards, pipelines, contacts, IaC version, and residual risks.
7. **Preview teardown:** describe triggers on PR close/TTL expiry, data/dependency checks, destroy plan, credential revocation, job/DNS cleanup, and billing reconciliation.
8. **Well-Architected review:** identify at least one risk per pillar, mitigation steps, and closure evidence.

Example pre-closure verification table for a decommission request:

| Question | Result to record | Evidence / owner |
|---|---|---|
| Correct target environment and ID? | Yes/No | Inventory + request ID |
| Any data retention obligations? | No / Yes + retention decision | Data owner + policy |
| Any resources shared with staging/prod? | No / Yes + handling plan | Dependency graph |
| Traffic, triggers, and jobs stopped? | Yes/No | Monitoring + configs |
| Credentials and permissions revoked? | Yes/No | IAM/secrets review |
| Deletion list reviewed? | Yes/No | IaC destroy plan |
| Remaining resources or charges to track? | No / Yes + follow-up ticket | Inventory + billing report |
| Who signed off closure? | Role name, timestamp | Audit record |

**Completion criterion:** A different operator can recreate the environment from the approved request and IaC, verify quality before use, identify who is accountable throughout its life, and decommission it without losing required data or disrupting shared systems.

## 12. Key Principles to Take Away

1. **No unowned environments:** every environment requires a known owner, purpose, resource boundary, and termination criteria.
2. **Never equate provisioning with handover:** a completed pipeline run does not prove an environment is ready or accepted by an owner.
3. **Automate alongside guardrails:** IaC templates, policy-as-code, inventory, reviews, and audits enable fast yet governed delivery.
4. **Both changes and teardowns can cause outages:** evaluate data, dependencies, permissions, retention obligations, and recovery plans.
5. **Verify against live state:** reconcile resources, access tests, restores, telemetry, and billing reports—never rely solely on labels or a single command's exit code.
6. **Optimize by risk:** synthetic-data previews with TTLs can self-provision and auto-reclaim; production or sensitive-data environments require stricter approvals and evidence.

The **request → approval → provisioning → validation → acceptance → operations → decommissioning → reconciliation** lifecycle turns resource organization into an integral part of cloud architecture. It ensures every resource has a reason to exist, an accountable owner, appropriate protections, and a clean end of life.
