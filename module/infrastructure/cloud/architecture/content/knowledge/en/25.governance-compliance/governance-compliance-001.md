# Translating Compliance Requirements into Architectural Controls

Compliance requirements typically originate from laws, industry regulations, customer contracts, internal policies, or security commitments. These documents often use concepts such as data protection, access restriction, record retention, auditing, recovery, and vendor management. The architecture team must translate those concepts into technical decisions that can be implemented and verified: where data is stored, who can access it, who manages encryption keys, which logs must be kept, when data must be deleted, who approves changes, and what evidence proves the controls are operating.

**Translating compliance requirements into architectural controls** is the process of turning obligations and governance goals into control objectives, controls, ownership, evidence, and operational processes across the system lifecycle. A requirement is only considered well addressed when it can answer: what risk needs to be reduced, how the system must behave, which component enforces it, who is responsible, where evidence is generated, and what happens when a control fails.

Compliance is not a feature that can be enabled with a checkbox, nor does it mean merely holding a cloud provider's certification. A provider may offer encryption services, audit logging, private networking, or storage regions, but the customer must still configure them, manage identities, classify data, restrict permissions, operate processes, and prove results within their own scope.

This lesson belongs to the **Governance and Compliance** section of the cloud architecture design module. The focus is on designing feasible controls with clear owners and evidence, while balancing security, reliability, performance, scalability, cost, and operability according to Well-Architected thinking.

After this lesson, you will be able to:

- Distinguish between obligations, policies, control objectives, control implementations, and evidence.
- Break down legal/contractual requirements into testable architectural requirements.
- Define data, system, environment, third-party scopes, and responsibility boundaries.
- Design controls for identity, network, encryption, logging, retention, residency, and SDLC.
- Build a traceability matrix, control ownership, evidence, and review cadence.
- Use policy-as-code and compliance automation while maintaining an exception-handling process.
- Prepare audit evidence, manage findings, and continuously improve controls.

## 1. From Requirement Text to System Behavior

A document might state that personal data must be protected from unauthorized access. That sentence sets the objective, but it is not enough for implementation. Architecture needs to interpret it into concrete questions:

- Which data is considered personal data?
- Which users, services, and administrators need access?
- Which permissions are allowed for each purpose?
- Where is the data transmitted and stored?
- Which accesses need to be logged, and who is allowed to view the logs?
- When a user requests deletion, how are copies in caches, warehouses, and backups handled?
- How do we prove that access has been revoked and data has been processed?

Basic translation flow:

~~~mermaid
flowchart TD
    SRC["Law / Regulation / Contract / Policy"] --> INTERP["Interpret scope and obligations"]
    INTERP --> RISK["Identify risks and control objectives"]
    RISK --> CTRL["Design controls"]
    CTRL --> ARCH["Map to architectural components"]
    ARCH --> EVID["Generate evidence and tests"]
    EVID --> OPERATE["Operate, monitor, handle findings"]
    OPERATE --> REVIEW["Periodic review / scope changes"]
    REVIEW --> INTERP
~~~

This process forms a feedback loop. When the system changes, new data sources are added, or obligations change, it is necessary to review whether the controls and evidence remain appropriate.

### Five Concepts to Distinguish

| Concept | Meaning | Example |
| --- | --- | --- |
| **Requirement / obligation** | What the organization must meet under law, contract, or policy | Only authorized personnel may view customer records |
| **Control objective** | The outcome/risk that needs to be controlled | Prevent access to customer data outside authorized purposes |
| **Control** | Technical mechanism or process that reduces risk | Role-based access, approval, auditing, and access reviews |
| **Implementation** | Specific component and configuration enforcing the control | IAM role, policy, private endpoint, query audit |
| **Evidence** | Proof demonstrating that the control is designed and operating | Policy version, access review record, log, test report |

One control can support multiple obligations, and one obligation may require multiple controls. You should not assume a single checkbox or screenshot proves the entire obligation.

## 2. Defining Compliance Scope Before Designing

Scope defines which systems, data, users, vendors, and processes fall under assessment. If the scope is wrong, controls may be missed or over-engineered, causing unnecessary cost.

### 2.1. Data Scope

Build an inventory for:

- Data types: identity, contact, financial, health, user content, authentication credentials, and operational data.
- Data subjects and processing purposes.
- Data origination sources and owning systems.
- Copies in databases, caches, object storage, data warehouses, logs, exports, and backups.
- Transmission paths across services, regions, and providers.
- Retention periods, archival rules, and deletion rules.
- Sensitivity levels and consequences of leakage or tampering.

### 2.2. System and Environment Scope

Identify production applications, staging, development, CI/CD, identity platforms, monitoring, backups, support tooling, and third-party systems that can access data. Test environments can also fall in scope if they use real data or identifiable copies.

### 2.3. Geographic and Third-Party Scope

Record where data is collected, processed, stored, backed up, and operationally supported. Identify cloud providers, SaaS, payment providers, email providers, managed databases, observability tools, and support subprocessors. The region selected in the console may not fully describe the location of logs, metadata, keys, backups, or support access.

### 2.4. Responsibility Boundaries

For each control, specify who:

- Designs and approves it.
- Configures and deploys it.
- Operates it routinely.
- Monitors and handles violations.
- Collects evidence.
- Performs independent verification.

Avoid vague descriptions like “IT is responsible for security.” Assign specific owners by role: platform, application, security, privacy, data owner, procurement, legal/compliance, and operations.

## 3. Breaking Down Requirements into Control Objectives

A single requirement often contains multiple sub-obligations. Separate the verbs, objects, conditions, timeframes, and exceptions.

For example, the statement “only approved personnel may access sensitive data” can be broken down into:

1. Individual named identities exist for each person and service.
2. Access permissions are based on job role/purpose.
3. Sensitive permissions require approval before granting.
4. Permissions are time-bound or periodically reviewed.
5. Permissions are revoked when personnel change roles or leave.
6. Access and permission changes are audited.
7. Tests exist proving unauthorized users are denied.

### Control Objective Structure

A good objective clearly describes the outcome and boundaries:

~~~text
Control objective:
  Prevent unauthorized access to restricted customer data.

Scope:
  Production customer database, analytics export and support tooling.

Desired outcome:
  Only approved identities can access data for an authorized purpose.

Failure condition:
  Access is granted without approval, exceeds scope or is not traceable.
~~~

### Distinguishing Preventive, Detective, and Corrective Controls

| Type | Role | Example |
| --- | --- | --- |
| **Preventive** | Stops unwanted actions before they occur | IAM deny-by-default, private network, deployment approval |
| **Detective** | Detects misconfigurations or unauthorized behavior | Audit log alert, configuration scanner, access review |
| **Corrective** | Remediates or reduces impact after detection | Revoke access, rotate key, restore, incident response |

A critical risk usually requires combining all three types. For example, a private endpoint prevents public access, network auditing detects out-of-policy changes, and an incident runbook revokes the invalid route and investigates access that occurred.

## 4. Writing Verifiable Requirements

Architectural requirements must be concrete enough to design and test. Avoid unmeasurable statements such as “the system must be secure,” “comprehensive logging,” or “regular backups.”

Translation template:

| Question | Details to Specify |
| --- | --- |
| What | What object or behavior needs to be controlled? |
| Who | Who or which system is responsible? |
| Where | Which data/system/environment/region is in scope? |
| When | Checked before, during, or after activity? At what frequency? |
| How | Which technical mechanism/process enforces it? |
| Evidence | What evidence shows the control is working? |
| Failure | What happens if the control is not met? |

Example:

~~~text
Requirement:
  Restricted production database must not be reachable from the public internet.

Architecture control:
  Database has no public endpoint; access uses approved private network path.

Automated test:
  IaC policy rejects public database configuration.
  External connectivity test confirms no public route.

Operational evidence:
  Configuration scan result, change audit and exception register.

Owner:
  Platform engineering; Security reviews policy.
~~~

This example only illustrates how to write a control. Values such as scan frequency, log retention period, or approver must be determined from actual policy.

## 5. Traceability Matrix: From Obligation to Evidence

A traceability matrix connects requirement sources to configurations and evidence. It is an essential tool during audits, system changes, and when proving that no control has been missed.

### Matrix Template

| Field | Content |
| --- | --- |
| Requirement ID | Obligation/policy identifier |
| Source and version | Source document, version/effective date |
| Applicability | Why it applies or does not apply |
| Data/system scope | System, dataset, environment, region |
| Risk | Risk if not satisfied |
| Control objective | Outcome to achieve |
| Control ID | Internal control identifier |
| Implementation | Component, policy, configuration, process |
| Owner | Responsible person/team |
| Test method | How design and operation are tested |
| Evidence location | Controlled storage location for evidence |
| Frequency | Execution frequency |
| Exception/status | Status, exception, and expiration date |

### Traceability Example

| Requirement | Control objective | Implementation | Evidence |
| --- | --- | --- | --- |
| Restrict customer data access | Only approved identities can access | IAM role, database role, private endpoint | Role inventory, approval, access test, audit log |
| Protect stored data | Data copies in scope are encrypted | Encryption at rest, key policy | Resource configuration, key inventory, scan report |
| Monitor privileged access | Sensitive operations are traceable | Audit trail, central log, alert | Log sample, alert test, retention config |
| Delete per retention | Expired data is handled per policy | Lifecycle job, deletion workflow, backup policy | Job run, deletion manifest, exception record |
| Service recovery | Recoverable within approved targets | Backup/PITR, DR runbook | Restore drill, RTO/RPO result, action items |

A single piece of evidence can support multiple controls, but its exact scope and timeframe must be recorded. A point-in-time configuration screenshot does not prove the configuration was always correct or operated throughout the entire audit period.

## 6. Designing Identity and Access Controls

Identity and access management (IAM) is typically one of the most important control layers because users, workloads, and administrators all access resources via identities.

### 6.1. Unique Identity and Service Identity

- Every administrative user has an individual account; shared accounts are not used.
- Services use dedicated workload identities/roles instead of sharing credentials across applications.
- Break-glass accounts are tightly controlled, require MFA, are logged, and are reviewed after use.
- Long-lived credentials are minimized; secrets have rotation and an owner.
- CI/CD runner identities have no broader permissions than the pipeline requires.

### 6.2. Least Privilege

Permissions are only sufficient for the required task and scope:

- Separate read, write, admin, export, and key-management permissions.
- Separate production from non-production.
- Separate deployment permissions from permissions to read sensitive data.
- Separate snapshot creation permissions from snapshot download/export permissions.
- Use resource scopes, conditions, and session durations when supported by the platform.

### 6.3. Joiner, Mover, Leaver

IAM processes must handle personnel starting, changing teams, and leaving the organization. HR or identity source changes must trigger permission provisioning, adjustment, or revocation. Temporary and vendor permissions require expiration dates, sponsors, and reviews.

### 6.4. Access Reviews and Privileged Access

Compile an inventory of effective permissions, owners, and justifications. Reviews focus on sensitive permissions, stale accounts, unused permissions, overly broad permissions, and off-hours access. Privileged access should have approval, just-in-time elevation, MFA, session logging, and time limits where appropriate.

### Evidence

- Identity inventory and role/group mappings.
- Approval records and access review results.
- MFA/conditional access configurations.
- Privileged session logs and break-glass reviews.
- Tests for allowed and denied access.
- Evidence of account/permission revocation following personnel changes.

## 7. Network Controls and Trust Boundaries

Network controls define which paths are allowed between users, applications, databases, control planes, vendors, and the internet.

### Architectural Controls

- Public ingress passes through a gateway/load balancer/WAF according to an approved model.
- Databases, caches, brokers, and internal services use private connectivity where appropriate.
- Security groups/firewalls follow least privilege; avoid overly broad source ranges/ports.
- Egress is controlled to reduce exfiltration risks and unauthorized endpoint access.
- Segment production, staging, management, and data planes.
- Admin access uses a dedicated access path with identity and auditing.
- DNS, routing, private endpoints, and service mesh policies are managed as code and reviewed.
- TLS/mTLS is used based on the threat model and service capabilities.

### Network Segmentation Does Not Replace Authorization

A service residing in a private subnet does not mean every workload in that subnet is permitted to read all data. Network policies reduce reachability, while application/IAM/database authorization decides which actions are allowed. Multiple independent control layers should be used.

### Evidence

Network architecture diagrams, route/security policies, IaC scan reports, firewall change approvals, connectivity tests, and network change logs. Evidence is needed for both desired configuration and actual runtime state.

## 8. Data Protection: Encryption, Keys, and Secrets

Encryption is a vital control, but it must be tied to key lifecycle, access control, and data classification.

### Encryption at Rest

Identify which resources require encryption: databases, object storage, disks, snapshots, backups, queues, logs, and exports. A provider may enable encryption by default, but the customer needs to know key ownership, decrypt permissions, rotation, and the impact if a key is disabled.

### Encryption in Transit

Require TLS for client-to-service, service-to-service, database connections, and data transfers to brokers/storage where appropriate. Verify certificate validation, protocol versions, and behavior when certificates expire.

### Key Management

- Classify keys by data and environment.
- Restrict who can create, rotate, disable, schedule deletion, or grant decrypt permissions.
- Separation of duties between key administration and data administration if risk requires it.
- Monitor key usage and policy changes.
- Have procedures for key compromise and backup recovery.
- Before rotating or revoking a key, verify snapshot/backup and DR dependencies.

### Secret Management

Secrets should be stored in a secret manager, not embedded in source code, container images, CI logs, or public config files. Workload identities can reduce the need for static secrets. Rotation requires coordinating connection refreshes, rollbacks, and dual-version support during transition windows.

### Evidence

Encryption inventory, KMS/key policies, key rotation records, TLS scans, secret access audits, exception lists, and tests for unencrypted resources.

## 9. Data Governance: Classification, Residency, Retention, and Deletion

Data governance does not stop at the primary database. A record can be copied into caches, search indexes, event streams, data lakes, observability tools, and backups.

### 9.1. Classification

Define data classes and handling rules. For example:

| Illustrative Class | Characteristics | Controls That May Be Needed |
| --- | --- | --- |
| Public | Authorized for public release | Integrity, change approval, availability |
| Internal | Internal use only | Identity access, approved sharing, retention |
| Confidential | Business/customer data requiring protection | Encryption, least privilege, audit, controlled export |
| Restricted | Highly sensitive data or special obligations | Strong access controls, enhanced audit, masking, segregation, strict retention |

Class names and criteria must follow organizational policy. Do not label sensitivity based solely on column names; understand context, linkability, and intended use.

### 9.2. Data Residency and Cross-Border Flows

Residency may apply to primary data, replicas, backups, logs, metadata, support access, or derived data. Create a data flow map:

- Where data is collected and processed.
- Region storing databases/object storage.
- Region for backups/DR.
- Destinations for logs, telemetry, analytics, and support tooling.
- Subprocessors and cross-border transfer paths.

Selecting a region does not automatically prove compliance. Verify service scope, contracts, control planes, backup behavior, and support access conditions.

### 9.3. Retention and Deletion

Retention must be tied to record type, purpose, and obligations. Do not keep all data indefinitely just because storage is cheap. Conversely, do not delete too early when data is needed for disputes, audits, or legal holds.

Deletion workflows must cover primary stores, replicas, caches, search, warehouses, exports, backups, and downstream consumers. If backups do not support per-record deletion, define backup expiration timeframes, control restores so deleted data does not return to production, and document valid exceptions.

### 9.4. Data Minimization and Masking

Collect and share only fields required for the purpose. Use masking, tokenization, pseudonymization, or aggregation for analytics/test environments. Synthetic data must still be checked to ensure it does not accidentally contain real data.

### Evidence

Data inventory, classification records, data flow maps, retention schedules, deletion run logs, backup lifecycle configs, data subject request evidence, and access/export audits.

## 10. Logging, Audit Trails, and Traceability

Logging aids incident investigation and proves operations, but logs can also contain sensitive data and introduce additional risk.

### Distinguishing Operational Logs and Audit Logs

- **Operational logs:** support debugging, health, and performance.
- **Audit logs:** record actions requiring traceability, such as accessing sensitive data, permission changes, creating/deleting keys, policy changes, exports, and administrative operations.

Not every application log qualifies as audit evidence. Audit logs require protection for integrity, access, retention, and completeness fit for purpose.

### Audit Event Content

An audit record can capture:

- Who performed it (identity/service principal).
- What action was taken (action).
- Which resource (resource/scope).
- When it happened (synchronized timestamp).
- Source/access path (source/context).
- Outcome (success/denied/error).
- Correlation/request ID.
- Approval/ticket reference if applicable.

Do not log passwords, tokens, private keys, or full sensitive payloads. Mask data according to policy.

### Protecting the Audit Trail

- Ship logs to a separate destination with access controls.
- Restrict log modification/deletion permissions; use immutable/WORM options if required.
- Encrypt logs and backups.
- Synchronize time and monitor for log loss.
- Alert when logging pipelines stop or audit event volume is anomalous.
- Test that sensitive operations actually generate events.

### Evidence

Audit configuration, masked sample events, retention proof, access lists, integrity settings, alert tests, and log delivery health.

## 11. Secure SDLC and Change Control

Compliance must follow the development lifecycle. If reviews happen only before release, misconfigurations can reappear immediately afterward via IaC, deployment pipelines, or console actions.

### Gates in the SDLC

| Phase | Example Controls | Evidence |
| --- | --- | --- |
| Plan/design | Threat model, data classification, architecture review | Review record, risk register, ADR |
| Code | Peer review, secret scan, SAST, dependency check | Pull request, scan results |
| Build | SBOM, signed artifact, provenance | Build attestation, artifact digest |
| Test | Security test, contract test, appropriate DAST | Test report, remediation |
| Deploy | Approval, policy-as-code, least-privilege pipeline | Deployment record, policy result |
| Operate | Vulnerability monitoring, config drift, access review | Dashboard, scan, incident record |
| Retire | Revoke identity, delete data, archive required evidence | Decommission checklist, deletion record |

### Infrastructure as Code

IaC helps control network, IAM, encryption, logging, backup, and region configurations through code reviews and version history. However, IaC only describes desired state. Drift detection and verification of actual resources are still needed.

### Change Management

Every change that could impact a control needs:

- Assessment of affected controls.
- Review/approval commensurate with risk level.
- Testing prior to deployment.
- A rollback/recovery plan.
- Recording of artifact/version and executor.
- Post-deployment state verification.

Emergency changes can use an expedited process, but they must have auditing and retrospective review, not create a permanent bypass.

## 12. Policy-as-Code and Compliance Automation

Policy-as-code expresses architectural rules as automatically checkable conditions. It is useful for repeatable configurations such as disallowing public databases, enforcing encryption, restricting regions, and requiring tags, logging, and backups.

### Reference Control Pipeline

~~~mermaid
flowchart TD
    PR["Pull request / IaC change"] --> LINT["Lint + validate"]
    LINT --> SEC["Security / secret / dependency scan"]
    SEC --> POLICY["Policy-as-code evaluation"]
    POLICY --> GATE{"Compliant?"}
    GATE -- "Yes" --> APPROVE["Required review / approval"]
    APPROVE --> DEPLOY["Deploy"]
    DEPLOY --> DRIFT["Runtime configuration scan"]
    DRIFT --> REPORT["Evidence and compliance dashboard"]
    GATE -- "No" --> FIX["Fix or request documented exception"]
    FIX --> PR
~~~

### Example Policy Logic

~~~text
deny if resource.type == "managed_database"
     and resource.public_access == true

deny if resource.environment == "production"
     and resource.encryption_at_rest != true

require if resource.data_classification in ["confidential", "restricted"]
     then resource.owner is not empty
      and resource.audit_enabled == true
~~~

This is pseudocode to illustrate the idea, not the syntax of a specific engine. Real policies must understand resource types, default states, scopes, exceptions, and how runtime checks work.

### IaC Scans and Runtime Scans

- **Pre-deploy scan:** catches misconfigurations before resources are created.
- **Runtime scan:** checks running resources, including changes made outside the pipeline.
- **Drift detection:** compares actual state against managed state.
- **Continuous control monitoring:** re-evaluates controls on a schedule or upon events.

A green pipeline does not guarantee production remains compliant forever. Users can make console changes, services can alter defaults, policies can be updated, or new resources can be created outside IaC.

## 13. Evidence Management and Audit Preparation

Audit evidence must be trustworthy, properly scoped, covering the right period, and retrievable. A policy document stating MFA is enabled does not prove every production account had MFA enforced during the audit period.

### Collecting Evidence

For each control, define:

- Evidence source (cloud API, SIEM, ticketing, CI/CD, HR/IAM, or test).
- Owner and verifier.
- Time period covered by the evidence.
- Integrity and access permissions.
- Collection frequency.
- Storage method, retention, and encryption.

### Design Effectiveness and Operating Effectiveness

- **Design effectiveness:** Is the control designed in a way that can reduce risk within the defined scope?
- **Operating effectiveness:** Has the control actually operated consistently over a period of time?

For example, a well-designed access review policy without review records during the quarter lacks evidence of operating effectiveness.

### Evidence Package

A package for a control may contain:

1. Control description and owner.
2. Scope/resource inventory.
3. Policy/configuration snapshot with timestamp/version.
4. Access/approval/change records within the period.
5. Test results and masked log samples.
6. Findings, exceptions, and remediation status.
7. Verifier and verification timestamp.

Do not create manual evidence solely for audits if systems can collect it automatically from authoritative sources. If screenshots or exports are necessary, record the source, timestamp, and how tampering is prevented.

## 14. Managing Findings, Exceptions, and Risk Acceptance

Not every control can be satisfied immediately. Exceptions may arise due to service limitations, legacy dependencies, migrations, or business requirements. Exceptions must be managed as owned risks, not open-ended notes.

### Exception Record

An exception should record:

- Control ID and affected resources/systems.
- Reason for non-compliance and supporting evidence.
- Risk level, likelihood, and impact.
- Compensating controls.
- Owner and authorized approver.
- Duration, expiration date, and revocation conditions.
- Remediation/migration plan.
- Review cadence and re-evaluation triggers.

### Risk Acceptance

Risk acceptance must occur at the proper authority level and within policy limits. Technical teams cannot accept risk on behalf of business owners or risk owners when policy requires higher-level approval. Do not use risk acceptance to legitimize legal violations or prohibited actions.

### Remediation Lifecycle

1. Log finding and verify scope.
2. Assess severity and impact.
3. Choose a fix, mitigation, or valid exception.
4. Assign an owner and deadline.
5. Implement change and collect evidence.
6. Perform independent verification or re-test.
7. Close finding with evidence; update risk register.

### Compensating Controls

If a primary control cannot be enabled, a compensating control must reduce the same risk with justifiable effectiveness. For instance, a legacy system that does not yet support MFA might be placed behind a privileged access gateway, restricted to the management network, with session recording and limited accounts during migration. A compensating control is not automatically equivalent to the primary control; it requires evaluation and approval.

## 15. Shared Responsibility with Cloud Providers and SaaS

A cloud service may hold its own certifications, audit reports, and control environment. Organizations using the service must still determine which parts are controlled by the provider and which must be executed by the customer.

### How to Evaluate a Provider

- Identify which specific services/SKUs/regions fall under which report scope.
- Review the reporting period and carve-outs/subservice organizations.
- Read customer responsibilities/user entity controls (if any).
- Check data residency, subprocessors, and support access.
- Review incident notification, vulnerability handling, and SLAs.
- Evaluate backups, deletion, encryption, key ownership, and exports.
- Check the ability to provide evidence during audits or investigations.
- Define offboarding and data deletion procedures upon contract termination.

A provider's certification does not automatically prove the customer's application is compliant. For instance, the provider offers encryption at rest, yet resources may be misconfigured; the provider offers an audit service, yet the customer may not have enabled it or centralized the logs.

### Sample RACI

| Activity | Cloud provider | Platform team | Application/data owner | Security/compliance |
| --- | --- | --- | --- | --- |
| Datacenter/hardware protection | R/A | I | I | C |
| Workload IAM configuration | C | R | R | A/C |
| Schema/data classification | I | C | R/A | C |
| Private network policy | C | R/A | C | C |
| Backup service capability | R | R | C | C |
| Retention/restore testing | C | R | R | A/C |
| Audit log enablement/use | C | R | R | A/C |
| Risk exception | I | C | R | A (per authority policy) |

RACI must be tailored to the organization, contract, and service model. An item may have multiple responsible parties executing it, but there should be only one accountable owner for the final decision.

## 16. Integrating Compliance into Architecture Decisions and Design Reviews

Compliance should not appear for the first time at the end of a project. It needs to participate when defining context, data flows, technology choices, and operating models.

### Review Checkpoints

- What data types does the service process and for what purpose?
- Do regions, tenancy, and data flows satisfy policy?
- Do identity, privilege, and network boundaries follow least privilege?
- Are encryption, key ownership, secrets, and auditing sufficient?
- Are backup, restore, retention, deletion, and DR appropriate?
- Have vendors/subprocessors been assessed?
- Does logging protect privacy and support evidence?
- Do IaC/CI/CD have policy gates and drift detection?
- Do controls have owners, tests, evidence, and an exception path?

### Embedding Requirements into ADRs

Each ADR can record:

~~~text
Decision:
  Use private managed database in approved region.

Compliance drivers:
  Restricted customer records; approved data residency.

Controls:
  Private endpoint, workload identity, encryption key policy,
  audit logging, backup retention and restore exercise.

Evidence:
  IaC plan, runtime configuration scan, IAM review,
  audit log sample and restore test.

Trade-offs:
  Higher network setup effort; cross-region recovery constrained.

Owner / review trigger:
  Platform + data owner; review when region, data class or provider changes.
~~~

An ADR does not replace legal interpretation or a control register, but it links architectural decisions to obligations and trade-offs so reviewers understand why a choice was made.

## 17. Compliance Automation and Continuous Monitoring

Many controls can be checked periodically or on events:

- Resources missing an owner tag.
- Public databases or missing encryption.
- IAM policies with invalid wildcard permissions.
- Audit logs disabled or delivery pipelines with gaps.
- Backups violating retention policies.
- Resources created in unapproved regions.
- Certificates, secrets, or keys nearing expiration.
- Vulnerabilities exceeding severity/age thresholds.
- Expired exceptions that have not been addressed.

### Continuous Control Monitoring

~~~mermaid
flowchart LR
    CLOUD["Cloud configuration / APIs"] --> COLLECT["Inventory + evidence collectors"]
    CI["CI/CD + IaC"] --> COLLECT
    IAM["Identity and access systems"] --> COLLECT
    LOG["Audit / SIEM"] --> COLLECT
    COLLECT --> EVAL["Control evaluation"]
    EVAL --> DASH["Compliance dashboard"]
    EVAL --> FIND["Finding / ticket"]
    FIND --> OWNER["Control owner"]
    OWNER --> FIX["Remediate / exception"]
    FIX --> VERIFY["Re-test and close"]
    VERIFY --> DASH
~~~

Automation needs to handle false positives, scope, and freshness. A scanner failing to see a resource might be due to missing read permissions or collector errors; it must not be marked compliant when evidence is incomplete. UNKNOWN or NOT EVALUATED states must be distinguished from PASS.

### Maturity Levels

Progress can be evaluated across levels:

1. **Manual:** manual checklists and evidence collection.
2. **Repeatable:** stable processes, owners, and cadence.
3. **Automated:** automated scans, policy tests, and evidence collection.
4. **Continuous:** drift/findings detected and resolved within defined timeframes.
5. **Measured:** control effectiveness, false positives, remediation time, and residual risk are measured for improvement.

Not everything needs to be automated from day one. Prioritize controls with high risk, high change frequency, and easily collectible evidence.

## 18. Common Pitfalls

**Copying statutory text verbatim into technical checklists.** Legal wording must be interpreted for scope, purpose, and risk before designing.

**Assuming cloud provider certifications cover the application.** Controls at the workload, IAM, data lifecycle, and customer process layers still must be implemented.

**Failing to define applicability and scope.** Systems, logs, backups, or auxiliary SaaS tools can be overlooked.

**Writing policies without implementation.** A document requiring MFA does not enable MFA; a retention policy without a lifecycle job does nothing.

**Having implementation without evidence.** Being unable to prove the control operated during the assessment period.

**Using a single screenshot as long-term evidence.** A configuration snapshot does not prove operating effectiveness or full scope.

**Lacking owners and cadence.** Controls go unreviewed, findings go unresolved, and exceptions persist indefinitely.

**Using policy-as-code without checking runtime drift.** Console changes or out-of-pipeline resources can break controls after deployment.

**Marking UNKNOWN as compliant.** Missing evidence must be treated as a state requiring investigation, not PASS.

**Logging everything without protecting logs.** Audit trails can become concentrations of sensitive data and credentials.

**Applying retention only to the primary database.** Caches, analytics, exports, backups, and downstream copies also have lifecycles.

**Accepting exceptions without expiration.** Temporary risks can become permanent configurations.

**Using compensating controls without evaluating effectiveness.** Compensating measures must prove they reduce risk across an equivalent scope.

**Leaving security reviews until the end of the project.** Changing regions, identities, or storage after building can be very expensive.

## 19. Hands-on Exercise: Translating Compliance Requirements into a Control Architecture

**Hypothetical scenario:** A SaaS scheduling platform serves enterprise customers across multiple markets. The application includes an API gateway, Booking Service, Customer Service, Payment Service, managed relational database, object storage, cache, event broker, data warehouse, CI/CD, and monitoring system. Data includes customer identity/contact information, appointments, payment status, and access logs. Some customers require primary data in a specific region; the support team needs controlled access to troubleshoot incidents. This is a simulated scenario and does not represent legal conclusions for any specific country or industry.

### Task 1 — Define Scope and Data Flow

Map the data flow from clients to APIs, services, databases, caches, event brokers, warehouses, logs, backups, and providers. Mark:

- Data owner and classification.
- Processing purpose and consumers.
- Regions for primary, replicas, backups, logs, and support.
- Third parties/subprocessors.
- Retention, deletion, and export paths.

### Task 2 — Analyze Obligations and Control Objectives

Take the hypothetical requirements:

1. Only approved personnel can access customer records.
2. Production databases must not be public.
3. Sensitive data must be encrypted at rest and in transit.
4. Privileged access must be audited and reviewed.
5. Data is stored per retention schedules and has a deletion workflow.
6. The service must be recoverable within owner-approved RTO/RPO targets.

For each requirement, write the control objective, risk, scope, control type, owner, and test method.

### Task 3 — Design Implementation

Propose IAM, private networking, TLS, key management, audit logging, data masking, backup/restore, retention lifecycle, deletion workflow, and CI/CD policy gates. Clearly indicate what the provider manages and what the customer must configure/verify.

### Task 4 — Build a Traceability Matrix

Create requirement/control IDs; link source, risk, implementation, resource, evidence, owner, frequency, and exceptions. Identify which evidence can be collected automatically and which requires manual verification.

### Task 5 — Design Continuous Compliance

Write policy logic for public databases, missing encryption, disabled auditing, disallowed regions, and missing owner tags. Define PASS/FAIL/UNKNOWN outcomes, ticket routing, severity, remediation deadlines, and re-testing.

### Task 6 — Handle Exceptions

A legacy integration does not yet support private connectivity for 60 days. Create an exception record including risk, scope, compensating controls, owner, approver, expiration, remediation plan, and revocation triggers. Assess whether sensitive data processing can continue.

### Task 7 — Prepare an Audit Package

Select one control and build a package containing policy, configuration snapshot, inventory, approvals, access reviews, test report, sample audit events, and findings. Distinguish evidence proving design effectiveness from operating effectiveness.

### Deliverables

| Deliverable | Content |
| --- | --- |
| Data/system scope map | Data flows, regions, vendors, environments, and classifications |
| Requirement register | Source, version, applicability, obligation, and risk |
| Control register | Objective, preventive/detective/corrective, owner, and frequency |
| Traceability matrix | Requirement → control → implementation → evidence |
| Architecture package | IAM, network, encryption, logging, retention, and DR controls |
| Policy-as-code | Rules, CI gates, runtime scans, and UNKNOWN state |
| Exception register | Risk, compensating controls, approvals, and expiration |
| Audit evidence package | Design/operating evidence and finding status |
| ADR | Decisions, trade-offs, assumptions, and review triggers |

## 20. Well-Architected Assessment

| Pillar | Questions for Governance and Compliance |
| --- | --- |
| **Operational Excellence** | Does each control have an owner, runbook, cadence, evidence source, finding workflow, and review trigger? |
| **Security** | Are identity, least privilege, segmentation, encryption, keys, auditing, data lifecycle, and vendor access controlled? |
| **Reliability** | Do backup/restore, DR, log delivery, key recovery, control-plane dependencies, and incident processes meet targets? |
| **Performance Efficiency** | Do logging, encryption, policy evaluation, and monitoring impact latency/capacity; can overhead be controlled? |
| **Cost Optimization** | Are evidence retention, SIEM ingestion, KMS, auditing, scanning, backups, and compliance tooling budgeted? |
| **Sustainability** | Are redundant log collection, retaining expired data, and unnecessary duplicate scans/pipelines avoided? |

## 21. Checklist Before Moving Compliance Controls to Production

- [ ] Requirement source, version, applicability scope, and interpreter are documented.
- [ ] Data/system/environment/region/vendor scope has been mapped.
- [ ] Obligations are broken down into verifiable risks and control objectives.
- [ ] Each control has an ID, owner, control type, implementation, test, and evidence.
- [ ] Traceability matrix links requirement → control → resource → evidence.
- [ ] Shared responsibility with cloud provider/SaaS is verified per specific service and contract.
- [ ] IAM, service identity, least privilege, access reviews, and privileged access have evidence.
- [ ] Network, private access, egress, and TLS are verified in both IaC and runtime.
- [ ] Encryption at rest/in transit, key ownership, rotation, and recovery are defined.
- [ ] Classification, residency, retention, deletion, and backup lifecycles cover all copies.
- [ ] Audit trails have integrity, access controls, retention, and alerts on log loss.
- [ ] Secure SDLC, change approvals, IaC scans, and runtime drift detection are established.
- [ ] Policy-as-code distinguishes PASS, FAIL, and UNKNOWN; false positive handling exists.
- [ ] Evidence has sufficient scope/timeframe and proves both design and operating effectiveness.
- [ ] Findings/exceptions have a risk owner, approval, compensating controls, expiration, and remediation.
- [ ] Processes exist for audit requests, evidence export, and evidence protection.
- [ ] Access denial, encryption checks, restores, deletions, and incident processes have been tested.
- [ ] Controls are reviewed when data flows, providers, regions, versions, or processing purposes change.
- [ ] Costs of compliance tooling, logging, evidence retention, and operations are accounted for.

Translating compliance requirements into architectural controls is the process of connecting obligations to observable, verifiable system behavior. Start with scope and risk, define control objectives, design implementations alongside owners, and then collect evidence and monitor in operations. IAM, networking, encryption, data lifecycle, auditing, SDLC, and policy automation are common layers, but they are only valuable when aligned with actual obligations and backed by operational evidence. An architecture capable of long-term compliance must manage changes, exceptions, vendors, and recovery—not just pass once at go-live.
