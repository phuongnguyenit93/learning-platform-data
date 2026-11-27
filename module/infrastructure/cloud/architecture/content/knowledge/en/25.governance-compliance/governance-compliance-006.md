# Configuration Management, Drift Detection, and Non-Standard Resources

## Learning Objectives

In cloud environments, infrastructure and application configurations change continuously. One team provisions resources via Infrastructure as Code (IaC), another makes manual console edits to troubleshoot an incident, pipelines update images or policies, managed services modify metadata, and sandbox accounts spin up out-of-process resources. Over time, actual state diverges from the approved configuration. That phenomenon is called **configuration drift**.

Without drift controls, production may diverge from staging, security groups can widen unintentionally, databases may run under the wrong backup policy, encryption or logging may get disabled, and costs rise from ownerless resources. Deploying via IaC without continuously reconciling against actual state is not enough to maintain control.

This lesson covers how to manage configurations, detect drift, and handle non-standard resources in cloud architecture. Topics include desired state, source of truth, IaC, configuration inventories, change management, policy-as-code, drift detection, remediation, exception handling, audit evidence, and operational accountability.

This lesson belongs to the **Governance and Compliance** chapter, focusing on **configuration management, drift detection, and non-standard resources**. In Cloud Architecture, decisions must connect business requirements to networking, compute, data, deployment models, and controls—while balancing reliability, security, scalability, cost, and operations under Well-Architected principles.

After this lesson, you will be able to:

- Distinguish desired state, actual state, configuration baselines, and drift.
- Define sources of truth and ownership for each configuration/resource type.
- Design configuration change workflows via IaC, reviews, approvals, and deployments.
- Classify drift caused by manual changes, automation, providers, state loss, or pipeline failures.
- Detect drift using plans, cloud inventories, config rules, audit logs, and policy evaluation.
- Distinguish unmanaged, orphaned, shadow IT resources, and valid exception-approved resources.
- Design safe remediation with controlled blast radius and rollbacks.
- Apply policy-as-code, preventive guardrails, and continuous compliance.
- Manage exceptions, risk acceptance, owners, expiration, and evidence.
- Control secrets, encryption, networking, identity, backups, tags, and data residency.
- Build dashboards, alerts, KPIs, and repeatable audit processes.
- Evaluate appropriate cost and automation levels per workload.

## 1. What Is Configuration Drift?

Configuration drift occurs when running configurations or resources differ from the expected, approved, or declared state in the configuration management system.

For example, IaC declares a database accepts connections only from the private application subnet. An operator opens an additional public IP range while investigating an incident and forgets to close it afterward. The database still runs and the application still works, yet actual state has drifted from the security baseline.

Common forms of drift:

- **Manual drift:** changes made via console, CLI, or scripts outside the pipeline.
- **Automation drift:** another controller, autoscaler, or pipeline modifies the resource.
- **Provider-managed changes:** the cloud service alters attributes due to maintenance, versions, or features.
- **State drift:** IaC state files no longer match real resources or are lost.
- **Code drift:** repository configuration differs from what is deployed.
- **Environment drift:** dev, test, staging, and production diverge unintentionally into incompatible configs.
- **Dependency drift:** image, package, runtime, module, or policy versions change outside the baseline.
- **Unmanaged resources:** resources exist without an explicit owner, IaC source, or management record.

Not every discrepancy is an error. An attribute may be updated automatically by the provider, an autoscaler may adjust replica counts with load, or a time-bound exception may be approved. You must determine who owns the state, whether the change is authorized, and where approval evidence lives.

### 1.1. Desired State and Actual State

- **Desired state:** approved target configuration in IaC, config repositories, policies, or configuration management systems.
- **Actual state:** state currently existing in the cloud account, cluster, operating system, or application runtime.
- **Baseline:** minimum set of rules a workload/environment type must satisfy.
- **Drift:** discrepancy requiring evaluation between desired and actual state.
- **Reconciliation:** the process of detecting and returning actual state to desired state or recording a valid exception.

~~~mermaid
flowchart LR
    SRC["IaC / Config repository"] --> DES["Desired state"]
    DES --> DEPLOY["Deployment / Controller"]
    DEPLOY --> CLOUD["Cloud resources"]
    CLOUD --> ACT["Actual state"]
    ACT --> SCAN["Drift detection"]
    DES --> SCAN
    SCAN --> FIND["Classify findings"]
    FIND --> FIX["Remediate / Exception"]
    FIX --> CLOUD
    FIX --> SRC
~~~

### 1.2. How Configuration Drift Differs from Vulnerabilities and Compliance Findings

| Concept | Meaning | Example |
| --- | --- | --- |
| Configuration drift | Actual differs from desired/baseline | Security group has a rule absent from IaC |
| Vulnerability | Exploitable weakness | Runtime/package has a CVE |
| Compliance finding | Fails to meet a control/regulation | Log retention is below requirement |
| Misconfiguration | Incorrect or insecure configuration | Public bucket storing restricted data |
| Unmanaged resource | Resource lacking clear lifecycle/owner management | VM created manually in production account |

A single resource can simultaneously exhibit drift, misconfiguration, and a compliance finding. Classification helps assign the right owner and remediation.

## 2. Establishing a Source of Truth for Configurations

Drift detection cannot be reliable without knowing what the authoritative state is. Every resource/configuration type needs a source of truth and an accountable owner.

### 2.1. Usable Authoritative Sources

| Scope | Usable Source of Truth | Owner |
| --- | --- | --- |
| Cloud infrastructure | IaC repository and state backend | Platform/Cloud team |
| Kubernetes workloads | GitOps repository/Helm/Kustomize | Application/platform team |
| OS baseline | Image pipeline/config management | Compute/platform team |
| Application configuration | Versioned config repository or config service | Service owner |
| Identity/access policies | IAM policy repository and approval records | Security/IAM team |
| Network policies | Network IaC and architecture baseline | Network team |
| Database parameters | Database configuration repository/change records | DBA/data platform |
| Security controls | Policy-as-code and control catalog | Security/compliance |
| Container images | Immutable artifact registry and build provenance | Engineering/Supply chain |

Avoid having multiple authoritative sources writing to the same attribute without precedence rules. For example, console edits, Terraform, and GitOps all managing replica counts can endlessly overwrite each other.

### 2.2. One Owner per Managed Attribute

A resource may be touched by multiple tools, yet each critical attribute should have one clear owner. For example:

- Terraform manages VPCs, subnets, routes, and security groups.
- Kubernetes controllers manage replica counts.
- HPA scales replicas based on metrics.
- Application deployments manage image/version.
- Secret managers manage secret values; IaC only references secrets.

If Terraform constantly forces replica count back to 3 while HPA scales to 8, pipelines generate false drift or break auto-scaling. Define which attributes controllers may mutate freely and which must stay locked to the baseline.

### 2.3. Baselines by Environment and Workload

Do not apply one identical configuration to all workloads. Baselines can be segmented by production, staging, development, sandbox; public-facing vs. internal-only; general data processing vs. regulated workloads; criticality tier; tenant isolation model; data classification; region/residency requirements; and deployment model.

Production databases typically require higher backup/PITR, encryption, private networking, and auditing than ephemeral environments. Sandboxes still need guardrails against public exposure and cost overruns.

## 3. Managing Configuration with Infrastructure as Code

IaC describes infrastructure as code that can be reviewed, versioned, tested, and deployed repeatably. IaC establishes a clear desired state, yet it does not guarantee every change goes through the pipeline.

### 3.1. Standard Change Workflow

~~~mermaid
flowchart TD
    CHANGE["Change request"] --> BRANCH["Version-controlled change"]
    BRANCH --> REVIEW["Peer / security review"]
    REVIEW --> VALIDATE["Lint / test / policy check"]
    VALIDATE --> PLAN["Plan and impact review"]
    PLAN --> APPROVE["Approval by authorized owner"]
    APPROVE --> APPLY["Apply through controlled pipeline"]
    APPLY --> VERIFY["Post-deploy verification"]
    VERIFY --> AUDIT["Record version, actor, evidence"]
~~~

This process produces evidence of who changed what, why, who reviewed it, which pipeline deployed it, and what the outcome was.

### 3.2. Illustrative Terraform Example

~~~hcl
resource "aws_s3_bucket_public_access_block" "data" {
  bucket = aws_s3_bucket.data.id

  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}
~~~

This example illustrates a single provider. Production configurations also need bucket policies, key policies, lifecycles, logging, and appropriate access controls; resource/argument names vary by provider and version. Never copy samples straight into production without verifying data classification and KMS ownership requirements.

### 3.3. State Backends and Locking

IaC state can contain sensitive metadata and mappings between resources and code. You should:

- Store state in a protected, encrypted, backed-up backend.
- Enable locking/concurrency control as supported by the tool.
- Restrict state read/write permissions.
- Never store state inside public repositories.
- Partition state sensibly by account/environment/workload.
- Maintain a recovery procedure if state corrupts or resources are imported improperly.
- Audit state operations: imports, moves, replacements, or force-unlocks.

Lost or stale state can trick IaC into thinking resources do not exist and creating duplicates, or losing management of existing resources. Never manually edit state arbitrarily to hide drift.

### 3.4. Immutable vs. Mutable Configuration

Prefer immutable infrastructure for images, containers, and deployment artifacts: instead of patching running VMs, build new images and roll out. Some runtime configurations such as feature flags, policy thresholds, or scaling still require dynamic updates.

Distinguish:
- Immutable artifacts: images/packages with versions/digests.
- Versioned desired configs: commits/config releases with IDs.
- Dynamic runtime state: autoscalers, leases, controller state.
- Mutable secrets: rotated per policy without leaking in diffs.
- Provider-managed attributes: observed only or accepted within defined bounds.

## 4. Detecting Drift: Comparing Desired and Actual

Drift detection must span resources, configs, and runtime state. No single tool sees every layer.

### 4.1. Detection Methods

| Method | Scope | Strengths | Limitations |
| --- | --- | --- | --- |
| IaC plan/refresh | Resources managed by IaC | Shows differences against state/code | Misses unmanaged resources outside scope |
| Cloud asset/config inventory | Account-wide assets and configs | Finds resources absent from IaC | Needs ownership and baseline mappings |
| Cloud audit logs | Actors and API/config change history | Investigates who did what and when | Not all runtime state emits readable events |
| Policy evaluation | Evaluates resources against rules | Automatically surfaces findings | Rules may lack business context |
| Kubernetes reconciliation | Cluster objects vs. Git/manifests | Continuously syncs desired state | Must handle controller-owned fields |
| Host configuration scanning | OS/packages/configs | Detects drift inside VMs/nodes | Needs agents/credentials and proper scaling |
| Runtime monitoring | Processes, networking, behavior | Detects active runtime changes | Does not inherently know desired state |
| Vulnerability/config scanning | Images, packages, service settings | Detects technical risks | Does not replace ownership and approvals |

### 4.2. An IaC Plan Is Not a Cloud-Wide Inventory

If a resource is created manually outside modules/state, a `terraform plan` in an existing repository may have no idea that resource exists. Therefore combine:

1. Account/subscription/project-wide resource inventory.
2. Mapping resource IDs to IaC state/repositories/owners.
3. Policy/baseline evaluation.
4. Audit logs to trace change origins.
5. IaC plans for managed resources.

### 4.3. Periodic and Event-Driven Drift Detection

- **Scheduled scans:** run on a schedule, e.g., hourly/daily.
- **Event-driven:** re-evaluate when cloud audit events indicate resource creation/modification.
- **Continuous reconciliation:** controllers continuously compare and converge toward desired state.
- **Deployment-time validation:** verify before/after every release.

Combine these approaches: event-driven cuts detection latency; scheduled scans catch missed events or long-lived resources; deployment-time checks prevent bad changes upfront.

### 4.4. Detection Latency

A public resource detected hours later creates far longer exposure than a missing tag. Measure time from drift introduction to detection and remediation:

~~~text
Mean Time To Detect (MTTD)
  = Detection timestamp - Drift introduction timestamp

Mean Time To Remediate (MTTR)
  = Remediation verified timestamp - Detection timestamp
~~~

Track percentiles and severity, not just averages. Critical drift demands near-real-time alerts or preventive blocks, whereas missing tags in sandboxes can be batched.

## 5. Non-Standard and Unmanaged Resources

### 5.1. Categories to Distinguish

- **Unmanaged resource:** not registered in IaC/config inventory and lacking a clear lifecycle owner.
- **Orphaned resource:** previously managed, but its owner, parent, or workload is gone.
- **Shadow IT:** resource created outside governance/approval processes.
- **Out-of-policy resource:** has an owner yet violates baseline/policy.
- **Exception-approved resource:** diverges from baseline with risk acceptance, owner, scope, and expiration.
- **Ephemeral resource:** temporary resource created by jobs/controllers with explicit TTL/owner.
- **Provider-managed resource:** resource or field managed by the service per provider semantics.

Do not equate an untagged resource with an ownerless resource. Tags can be stripped, while ownership may still be traced via accounts, deployments, audit logs, naming, and billing metadata.

### 5.2. Inventory and Ownership

A resource inventory should capture resource ID, type, region, account/project, environment, workload/service, owner team/contact, cost center/product/tenant where applicable, source of truth/repository/module, creation time/creator principal, last modified time/actor, classification/compliance scope, backup/retention/criticality, lifecycle/expiry/TTL, and exception ID if any.

Never require tags to hold secrets, tokens, personal emails, or customer data.

### 5.3. Discovering Ownerless Resources

Discovery process:

1. Pull inventory across all managed accounts/projects/regions.
2. Normalize resource IDs, accounts, types, and tags.
3. Cross-reference against IaC state and deployment inventories.
4. Cross-reference creators/last actors from audit logs.
5. Trace relationships with workloads, network interfaces, DNS, storage mounts, and billing.
6. Flag unknown-owner/unmanaged/orphaned statuses.
7. Open a case with an assigned investigator and deadline.
8. Never auto-delete resources that might be serving production.

## 6. Classifying and Prioritizing Drift

Not all drift carries equal risk. A missing tag may affect cost allocation; a public firewall opening can create severe exposure.

### 6.1. Risk Scoring

Score based on impact, exposure, exploitability, criticality, scope, duration, and compensating controls.

~~~text
Risk score
  = Impact × Exposure × Exploitability × Scope factor
~~~

This model only aids prioritization; it does not replace security assessment. Weighted scales and severity thresholds approved by the organization can be used.

### 6.2. Severity and Response

| Severity | Example | Reference Response |
| --- | --- | --- |
| Critical | Public access to restricted data; disabling encryption/critical controls | Block or isolate immediately per incident procedure |
| High | Security group opening broad admin ports; audit logging disabled | Immediate alert, urgent owner handling |
| Medium | Backup retention below baseline; resource missing owner tag | Short-SLA ticket with escalation |
| Low | Missing descriptive tag; naming convention mismatch not affecting controls | Scheduled batch remediation |

Severity and SLAs must align with policy/risk appetite. Never auto-block public access or delete resources if doing so risks service outages; critical exposure requires the incident commander/security owner to decide safe containment.

### 6.3. Drift Can Be a Legitimate Change

An autoscaler scaling replicas from 3 to 8 is a controller-owned runtime change. If IaC diffs against it and forces it back to 3, it can break scale-out. Desired state should declare the policy (min/max/metrics) rather than hardcoding dynamic values.

Rules needed:
- Ignore/allow controller-owned attributes.
- Observe without auto-remediating provider-managed fields.
- Require approval for security-critical properties.
- Continuously reconcile compliance-critical attributes.
- Separate emergency changes from permanent desired state.

## 7. Remediation: Handling Drift Safely

Three main paths exist:

1. **Reconcile to desired:** restore the live resource back to the standard configuration.
2. **Adopt actual state:** if the live change is legitimate, update the IaC/config repository to reflect the approved decision.
3. **Approved exception:** retain the divergence time-bound with risk acceptance and compensating controls.

Not every drift finding should trigger an immediate `apply`. Applying can destroy resources, replace databases, reset firewalls, alter endpoints, or cause outages.

### 7.1. Remediation Workflow

~~~mermaid
flowchart TD
    D["Drift finding"] --> C["Classify / assess risk"]
    C --> U{"Unknown owner or impact?"}
    U -->|Yes| H["Quarantine change / investigate"]
    U -->|No| R{"Matches approved exception?"}
    R -->|Yes| E["Record exception and expiry"]
    R -->|No| A{"Actual change legitimate?"}
    A -->|Yes| I["Update source of truth after approval"]
    A -->|No| P["Plan remediation / rollback"]
    P --> AP["Review impact and approve"]
    AP --> FIX["Apply controlled fix"]
    I --> V["Verify actual state"]
    E --> V
    FIX --> V
    H --> V
    V --> CLOSE["Evidence / close finding"]
~~~

### 7.2. Prevent, Detect, and Correct

| Control | Purpose | Example |
| --- | --- | --- |
| Preventive | Block bad configs before creation | Policy-as-code, org policies, admission control |
| Detective | Detect existing deviations | Inventory scans, config rules, audit alerts |
| Corrective | Restore compliance or handle exceptions | IaC apply, rollback, quarantine, tickets |
| Compensating | Reduce risk while remediation is pending | Temporary firewall rules, extra monitoring, access revocation |

Controls work only when scope and bypass paths are governed. A policy blocking public storage fails if broad admin roles can disable the policy; audit policy edits and protect the control plane.

### 7.3. Auto-Remediation vs. Manual Remediation

Auto-remediation fits when rule semantics are clear, actions are reversible or low blast radius, owner/environment are known, tests/audits/idempotency/rollbacks exist, and valid workloads are unaffected.

Manual approval fits when downtime/data loss is possible, the resource lacks a known owner or sits outside IaC, changes cross accounts/networks, legal/business exception evaluation is needed, or a provider/manager controls lifecycle.

For example, auto-enabling required encryption when safely supported without affecting existing data may be fine; auto-terminating an untagged VM without confirming whether it runs critical workloads is not.

## 8. Policy-as-Code and Guardrails

Policy-as-code turns governance requirements into rules verifiable in pipelines or against live resources.

### 8.1. Example Policies

Common policies:

- Production resources must carry owner, environment, and cost center.
- Databases must not expose public endpoints without an exception.
- Storage holding restricted data must enable encryption and block public access.
- Production compute must run approved images.
- IAM policies must not grant wildcard privileges outside controlled roles.
- Audit logs must be enabled and written to protected destinations.
- Backups/retention must meet baselines per data tier.
- Regions must match residency requirements.

### 8.2. Pseudo-Rego Policy Example

~~~rego
package cloud.baseline

deny[msg] {
  input.environment == "production"
  not input.tags.owner
  msg := "Production resource must declare an owner"
}

deny[msg] {
  input.data_classification == "restricted"
  input.public_access == true
  msg := "Restricted data must not be publicly accessible"
}

deny[msg] {
  input.environment == "production"
  input.encryption.enabled != true
  msg := "Production resource requires encryption"
}
~~~

This is illustrative pseudo-policy; input schemas and rule syntax must match your actual engine/policy framework. Every rule needs unit tests for pass/fail, negative cases, and exception behavior.

### 8.3. Policy Enforcement Stages

- Pull request: static validation, IaC scanning, policy evaluation.
- Plan review: inspect resource creates/updates/deletes and blast radius.
- Deploy: policy gate before apply.
- Runtime: continuous config evaluation.
- Audit: store results, policy versions, resource snapshots, and exceptions.
- Remediation: trigger actions or auto-fixes per policy.

### 8.4. Preventive Guardrails and Break-Glass

Use organization policies, SCPs/management policies, IAM permission boundaries, or admission controllers to block dangerous actions. Design break-glass for genuine emergencies with dedicated identities and MFA, time-bound permissions, approval or post-incident reviews, tamper-proof auditing, automatic expiry/revocation, and post-emergency reconciliation.

Never use break-glass as an everyday deployment path. After an emergency change, bring the change into the source of truth or roll it back.

## 9. Configuration Management in Kubernetes and Runtime

Kubernetes has multiple controllers mutating the same objects. Drift detection must understand owners and field management.

### 9.1. GitOps Reconciliation

GitOps controllers compare repository manifests against cluster state and reconcile per policy. Account for:
- Fields owned by HPA/controllers.
- Admission mutations/defaulting.
- Secret-injection sidecars/operators.
- CRDs/operators generating child resources.
- Runtime-generated status fields.
- Manual `kubectl edit` and emergency patches.
- Resources pruned when removed from Git.

`kubectl diff` or GitOps sync status reveals differences, yet understanding field ownership and defaulting is necessary to avoid false positives.

### 9.2. Container and Node Drift

Control image pinning by digest rather than mutable tags, base image/version and patch levels, node OS/AMI baselines, runtime security profiles, admission policies for privilege/`hostPath`/capabilities, sidecar/agent versions, and secret/config versions.

Never shell into a running container to patch it and treat that as the new normal. Changes must flow through build/deploy pipelines and produce new artifacts.

### 9.3. Runtime Configs and Feature Flags

Feature flag/config services can change outside deployment releases. Record config key/version, actor or automation principal, reason/change ticket, scope (tenant/environment/region), effective time and expiration, approval when impacting security/data processing, and rollback values.

Dynamic configurations require auditing equivalent to IaC, even though they do not provision cloud resources.

## 10. Non-Standard Resources: Discovery and Lifecycle

### 10.1. Resource Discovery Workflow

~~~mermaid
flowchart TB
    INV["Cloud asset inventory"] --> NORM["Normalize resource identity"]
    NORM --> MAP["Map to IaC / owner / workload"]
    MAP --> POL["Evaluate baseline and policy"]
    POL --> FIND["Create finding"]
    FIND --> TKT["Assign owner and SLA"]
    TKT --> DEC{"Decision"}
    DEC -->|Adopt| SRC["Import into source of truth"]
    DEC -->|Delete| DEL["Approved decommission"]
    DEC -->|Exception| EX["Time-bound exception"]
    SRC --> VERIFY["Verify and audit"]
    DEL --> VERIFY
    EX --> VERIFY
~~~

### 10.2. Adopting/Importing Resources

When a non-standard resource is legitimate and must stay:
1. Identify owner/business purpose.
2. Check security/compliance/cost.
3. Choose the appropriate module and source of truth.
4. Safely import the resource into state/config management.
5. Inspect the plan to ensure no unintended replace/destroy occurs.
6. Review and apply small incremental adjustments.
7. Attach owner, lifecycle, backups, and alerts.
8. Close the finding with evidence.

Importing does not mean a resource automatically meets baseline; verify the entire actual configuration.

### 10.3. Decommissioning Resources

Before deleting, identify owners and consumers; check network dependencies, DNS, data mounts, backups, and service links; verify retention/legal holds; identify data needing archiving; drain traffic/jobs and stop writes; back up/export if needed; delete upon approval; confirm removal from billing/resource inventories; archive deletion evidence.

Never auto-delete a resource solely because it lacks tags or sits outside IaC. Orphaned disks, snapshots, or IPs might still be needed for recovery.

## 11. Exception Management and Risk Acceptance

Cases arise where baselines cannot apply immediately or special workloads need different settings. Exceptions must be managed as lifecycle objects, not forgotten ticket comments.

### 11.1. Exception Record

An exception should capture:
- Exception ID.
- Resource/scope/environment.
- Exempted policy/rule.
- Business justification.
- Risk and impact assessment.
- Compensating controls.
- Owner and approver.
- Start/effective timestamp.
- Expiration date.
- Review cadence.
- Remediation plan if temporary.
- Evidence and audit history.

### 11.2. Expiration and Revalidation

Expired exceptions must automatically transition to review-required, alert owners, and per policy:
- Auto-close the exception and reconcile if safe.
- Block subsequent changes/deployments.
- Escalate to owners/approvers.
- Require re-approval against current risk.

Never auto-delete resources when an exception expires. Policy may demand reconfiguration, but blast radius must be evaluated first.

### 11.3. Do Not Use Exceptions to Rubber-Stamp All Drift

If a baseline is constantly exempted, the baseline may be flawed or the architecture unsuitable. Analyze exception patterns to refine baselines, create distinct workload tiers, build new controls, segregate resources, or formally accept risk at the proper authority level.

## 12. Audit Evidence and Continuous Compliance

A control may exist in policy, yet auditors still require evidence that it operates. Evidence must show scope, timeframe, policy version, outcomes, and accountable parties.

| Control | Evidence |
| --- | --- |
| Encryption at rest | Resource config snapshots, key references, policy evaluations |
| Network exposure | Security group/firewall inventories, routes, public endpoint scans |
| Access governance | IAM policy versions, access reviews, audit logs |
| Backups | Backup status, retention, restore test evidence |
| Logging | Audit configurations, destinations, retention, access policies |
| IaC change control | Commits, reviews, plans, approvals, pipeline runs |
| Drift management | Findings, owners, severity, remediation/exceptions, closure evidence |
| Unmanaged resources | Inventory snapshots, mapping results, owner assignments |
| Exception control | Exception records, approvers, expirations, revalidations |

### 12.1. Evidence Integrity

Evidence must be protected from unauthorized edits. Store it in a separate audit account/bucket, enable versioning/immutable retention as required, record checksums, and restrict access via dedicated roles. Avoid placing secrets or PII inside evidence beyond audit needs.

### 12.2. Continuous Compliance

Compliance is more than a one-day snapshot. Measure:
- Percentage of resources compliant with baseline.
- Critical drift count and age.
- MTTD/MTTR by severity.
- Ownerless resources.
- Active exceptions and upcoming expirations.
- Remediation success rate.
- Policy false positive/false negative rates.
- Out-of-pipeline changes.
- Percentage of resources mapped to a source of truth.
- Evidence freshness.

## 13. Incident Process Upon Detecting Severe Drift

Critical drift may constitute a security incident or change incident. The process must prioritize protecting systems and data while preserving evidence.

1. Verify the finding and resource identity.
2. Inspect audit logs, actor, timestamp, and change path.
3. Assess public exposure, privileges, data classification, and blast radius.
4. Notify incident commander/security owner.
5. Select containment: revoke access, isolate network, disable key/endpoint, or roll back per policy.
6. Preserve evidence before altering state if doing so does not escalate risk.
7. Remediate through controlled paths or emergency procedures.
8. Verify actual state and workload health.
9. Investigate root cause and inspect similar resources.
10. Update IaC, policies, alerts, and runbooks.
11. Record incident closure and lessons learned.

Never auto-revert a change without understanding why it happened. An operator might have added a rule to stop an outage; deleting it immediately could break connectivity. For critical exposure, containment must follow incident policy and authorized decision-makers.

## 14. Observability and KPIs for Configuration Governance

### 14.1. Operational KPIs

| KPI | Meaning | How It Is Used |
| --- | --- | --- |
| Drift coverage | % of in-scope resources with drift detection | Uncover blind spots |
| Compliant resource ratio | % of resources meeting baseline | Track compliance trends |
| Unmanaged resource count | Resources unmapped to owner/source | Prioritize discovery |
| Critical drift count | Open high-severity drift findings | Escalation |
| MTTD | Time from introduction to detection | Evaluate detection speed |
| MTTR | Time from detection to verified remediation | Evaluate response speed |
| Changes outside pipeline | Changes bypassing standard workflows | Pinpoint drift sources |
| Exception aging | Age and time until expiration | Prevent permanent exceptions |
| Remediation success rate | % of verified fixes | Evaluate automation |
| False positive rate | Findings that are not true violations | Improve policy precision |
| Evidence freshness | Evidence currency and scope completeness | Audit readiness |

### 14.2. Dashboards

Dashboards can be segmented by audience:
- Executive: compliance trends, critical risks, exception exposure, and non-standard costs.
- Platform: drift by account/region/resource type, IaC coverage, policy failures.
- Security: public exposure, privileged access drift, encryption/logging gaps.
- Operations: alert age, owners, remediation status, change failures.
- Cost: orphaned resources, idle capacity, untagged spend, and budget variance.
- Audit: evidence completeness, exception expirations, and control coverage.

Do not display compliance percentage alone. A 99.9% compliant environment can still harbor one critical public bucket holding sensitive data.

### 14.3. Alert Design

Alerts should include resource ID, account/region, policy ID, severity, owner, first-seen, last-seen, actual/desired summary, and remediation link. Never include secrets or sensitive data inside notifications.

## 15. Guardrailed Remediation Automation

Automation lowers MTTR yet can amplify mistakes at scale. Automate only after understanding semantics and impact.

### 15.1. Automation Levels

- **Observe-only:** record findings without modifying resources.
- **Ticket automation:** open tickets, assign owners and SLAs.
- **Suggested remediation:** generate plans/PRs for review.
- **Approved execution:** authorized person approves, then pipeline applies.
- **Auto-remediation:** automatically fix verified rules with preconditions and rollbacks.
- **Preventive enforcement:** block bad configs at create/change time.

Start with observe-only or suggested remediation for complex resources; ramp up once precision and rollbacks are proven.

### 15.2. Guardrails for Auto-Remediation

- Scope by resource type/environment/owner.
- Explicit allowlists and denylists.
- Idempotent actions.
- Rate limits and concurrency caps.
- Dry-run/plan before apply.
- Preconditions and postconditions.
- Canary or batch rollouts.
- Circuit breakers on remediation automation.
- Rollback procedures.
- Audit actor/service identity and version.
- Kill switch if remediation triggers an incident.
- Never touch ownerless or critical resources without approval.

### 15.3. Avoiding Controller Loops

If two controllers write the same attribute, they can endlessly overwrite each other. For instance, Terraform sets replica count to 4 while HPA scales to 10; GitOps syncs back to 4; HPA scales up again. Define clear field ownership and proper ignore/managed-fields configs.

## 16. TCO and Operational Impact

Configuration governance incurs costs from IaC/state backends and CI/CD; cloud inventory/config management; policy engines, scanners, and log storage; host agents/runtime config tools; remediation workers, ticketing, and approval workflows; audit evidence retention; engineering time maintaining modules/baselines; false positives/manual reviews; training, incident response, and exception governance.

Value delivered includes reduced misconfigurations/security exposure, fewer ownerless resources and wasted spend, consistent environment reproduction, faster audits/investigations, lower change failure rates, and stronger multi-account/region control.

~~~text
Cost of configuration governance
  = Tooling + Inventory/scan compute
    + Logs/evidence storage
    + Remediation automation
    + Engineering and audit effort

Avoided cost
  = Reduced incident impact
    + Reduced orphaned/idle resource spend
    + Reduced manual audit effort
    + Reduced change/recovery failures
~~~

Do not deploy a heavy policy platform for every sandbox. Control rigor should match criticality, data classification, blast radius, and rate of change.

## 17. Case Study: Detecting and Remediating Drift in a SaaS Platform

### 17.1. Context

A SaaS runs across three cloud accounts: production, staging, and sandbox. Infrastructure is managed with Terraform; Kubernetes workloads deploy via GitOps; databases and object storage use managed services. Multiple teams hold operational access, and some emergency changes still happen directly in the console.

An audit finds:
- A production storage bucket had its public access block altered.
- A database security group gained a CIDR outside the private subnet.
- A VM lacks owner/cost center tags.
- HPA replica counts differ from the Git manifest.
- One database's backup retention is below baseline.

### 17.2. Discovery and Classification

Inventory discovers resources across accounts/regions. IaC state mapping identifies the bucket and security group as managed; the VM has no mapping; the database belongs to a module owned by data platform; replica counts are driven by HPA so they are not drift if policy aligns.

Audit logs show the bucket was modified by an operator principal during an emergency; the security group rule came from a legacy script; the VM belonged to an uncleaned test job.

### 17.3. Remediation

- Bucket: inspect access logs and consumers, contain public access, restore baseline, review data exposure.
- Security group: confirm CIDR is no longer needed, remove via controlled change, verify app connectivity.
- VM: identify job owner, export data if needed, decommission upon approval; add TTL/cleanup.
- HPA: update comparison rules to ignore HPA-owned runtime fields while keeping min/max and metric baselines.
- Backup: increase retention to match data tier, run a restore test, and update evidence.

### 17.4. Preventing Recurrence

- Restrict console mutation rights in production; time-bound audited break-glass.
- Enable event-driven config evaluation for public access/security groups.
- Enforce owner/environment/expiry tags at resource creation.
- Add IaC policy gates checking baselines before apply.
- Run scheduled inventory scans for unmanaged/orphaned resources.
- Track exception records for emergency changes with expirations.
- Build dashboards displaying drift aging and out-of-pipeline changes.

~~~mermaid
flowchart TB
    INV["Account/region inventory"] --> MAP["IaC and owner mapping"]
    MAP --> DET["Policy and drift detection"]
    DET --> TRIAGE["Risk triage"]
    TRIAGE --> FIX1["Security remediation"]
    TRIAGE --> FIX2["Adopt/decommission resource"]
    TRIAGE --> FIX3["Correct controller ownership"]
    FIX1 --> VERIFY["Post-fix verification"]
    FIX2 --> VERIFY
    FIX3 --> VERIFY
    VERIFY --> PREV["Preventive guardrails + audit"]
~~~

## 18. Common Pitfalls

| Pitfall | Consequence | Remedy |
| --- | --- | --- |
| Treating IaC plan as cloud-wide inventory | Manually created resources go unseen | Combine with account-wide inventory |
| Auto-reverting all drift | Can cause outages or data loss | Classify, assess impact, approve |
| Ownerless resources | Findings linger indefinitely | Ownership tags/registry and escalation |
| Multiple controllers writing same field | Reconciliation loops, config flapping | Explicit field ownership |
| Treating provider-managed changes as violations | Constant false positives | Classify attributes and provider semantics |
| Not auditing console changes | Cannot trace actor/root cause | Cloud audit logs and alerts |
| Exceptions without expiration | Baselines gradually eroded | Time-bound exceptions and revalidation |
| Overly broad blocking policies | Blocks valid deployments | Test policies, scope exceptions, staged rollouts |
| Tracking only compliance percentage | Critical gaps masked | Severity, aging, and risk-weighted metrics |
| Deleting untagged resources immediately | Loss of needed workloads/data | Discovery, owner confirmation, and decommission plans |
| Fixing drift live without updating source | Pipelines reintroduce divergence | Adopt or roll back into source of truth |
| Storing evidence under same admin rights | Can be altered/deleted | Immutable/segregated audit storage |

## 19. Hands-on Exercise

A SaaS company operates production, staging, and sandbox across multiple cloud accounts. IaC manages networking/databases/compute; GitOps manages Kubernetes; the security team defines encryption/logging/private-access baselines. An audit finds public object storage, wrong backup retention on a database, two ownerless VMs, and a replica count change driven by HPA.

Complete the following:

1. Identify the source of truth and owner for VPC, security groups, buckets, databases, VMs, and Kubernetes deployments.
2. Classify each finding as drift, unmanaged, orphaned, controller-managed, or approved exception.
3. Design an inventory schema mapping resource ID, account, region, owner, IaC state, and cost center.
4. Select preventive, detective, and corrective controls for public access, encryption, backups, and mandatory tags.
5. Write policy-as-code rules for production owner tags, restricted-data public access, and encryption.
6. Identify HPA/provider-managed fields that should be excluded from drift comparisons.
7. Design a remediation plan with impact review, approval, canary, rollback, and evidence.
8. Define an exception record with owner, compensating controls, approver, and expiration.
9. Design alerts for critical drift and dashboards for drift aging/MTTD/MTTR.
10. Specify how to investigate console changes from audit logs and prevent recurrence.
11. Build workflows to safely import/adopt resources and decommission ownerless VMs.
12. Evaluate costs of the IaC/policy/inventory platform against risk and manual audits.
13. Write an ADR on auto-remediation levels for each resource group.

**Self-assessment guidance:** A strong submission has clear sources of truth, does not treat every difference as an error, detects out-of-IaC resources, remediates without outages, keeps exceptions time-bound, and provides evidence proving resolved state.

## 20. Pre-Production Checklist

- [ ] Every resource/config type has a clear source of truth and owner.
- [ ] Baselines differ by environment, criticality, and data classification.
- [ ] IaC state is protected with encryption, locking, backups, and auditing.
- [ ] Controller-owned fields are identified to avoid false drift.
- [ ] Inventory covers all accounts, projects, regions, and resource types.
- [ ] IaC mapping and unmanaged-resource discovery run periodically.
- [ ] Drift detection combines plans, inventories, audit logs, and policy evaluation.
- [ ] Critical policies have preventive guardrails and runtime detection.
- [ ] Findings record resource ID, actual/desired state, severity, owner, and first-seen.
- [ ] Auto-remediation has dry-runs, scope, rate limits, rollbacks, and kill switches.
- [ ] Resources without confirmed owners are never auto-deleted.
- [ ] Exceptions have risk acceptance, compensating controls, approver, and expiration.
- [ ] Emergency changes have auditing, time-bound access, and post-change reconciliation.
- [ ] Runtime secrets/configs have versioning, access controls, and change audits.
- [ ] Evidence integrity and retention meet audit requirements.
- [ ] KPIs include coverage, compliance, unmanaged count, MTTD, MTTR, and exception aging.
- [ ] Remediation is verified after apply and re-tested.
- [ ] TCO and operational ownership are periodically reviewed.

## 21. Well-Architected Assessment

| Pillar | Questions When Reviewing Configuration Governance |
| --- | --- |
| **Operational Excellence** | Can desired state, owners, change workflows, drift detection, remediation, and audit evidence operate repeatably? |
| **Security** | Do IAM, networking, encryption, logging, secrets, and public exposure have preventive/detective controls and exception governance? |
| **Reliability** | Does remediation bound blast radius, support rollbacks, and preserve service health; can recovery environments be rebuilt from source of truth? |
| **Performance Efficiency** | Do inventory/scanning/reconciliation run efficiently without overloading APIs/control planes? |
| **Cost Optimization** | Are non-standard/orphaned resources detected; are tag/cost ownership and idle resources managed? |
| **Sustainability** | Are orphaned resources, redundant configs, drift-induced overprovisioning, and repetitive manual operations reduced? |

**Conclusion:** Effective configuration management requires an owned desired state, full-environment inventory, and a detect–classify–remediate–verify loop. IaC provides change control; policy-as-code prevents misconfigurations; inventories and audits uncover non-standard resources; guardrailed remediation brings systems back to approved states. Not every discrepancy should be auto-reverted—you must understand controllers, providers, business context, and blast radius. Maintain time-bound exceptions, track MTTD/MTTR, and preserve auditable evidence to keep cloud environments secure, reliable, and cost-controlled under Well-Architected principles.
