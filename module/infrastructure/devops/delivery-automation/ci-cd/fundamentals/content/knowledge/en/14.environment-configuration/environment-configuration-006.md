# Detecting Configuration Drift Between Desired Specification and Actual State

## 1. What Is Configuration Drift?

A running system depends on many configuration settings: server or replica counts, container image versions, environment variables, access permissions, network rules, database configuration, resource limits, feature flags, and dependent service parameters. Teams typically describe these values in source code, configuration files, or infrastructure management tools. The running state is established after pipeline deployments and evolves as environment components continue operating.

**Configuration drift** occurs when the actual state of a system diverges from the state the team described and approved. For example:

- Git declares the application runs three replicas, while the cluster currently has two replicas due to someone editing it directly.
- Terraform defines a security group allowing ports only from the internal network, yet on the cloud an administrative port has been opened to the Internet.
- Staging uses a tested image digest, whereas production runs a mutable tag that has been overwritten with different contents.
- The `PAYMENT_TIMEOUT` environment variable in desired configuration is 3 seconds, while the running process uses 10 seconds.
- A service account is manually granted extra permissions with no corresponding change in the repository.
- A hotfix is applied directly on a host without being brought back into managed configuration.

Configuration drift does not necessarily stem from mistakes. It can arise from emergency changes, manual interventions, autoscaling, cloud provider updates, controllers, platform defaults, or incompletely modeled environment settings.

Within the scope of **DEVOPS_CI_CD_FUNDAMENTALS**, detecting and handling drift ensures deployed environments reflect the tested versions and configurations. It connects configuration management, pipeline as code, artifacts, environments, quality gates, traceability, and recoverability.

## 2. Desired State and Actual State

To detect drift, first define the two states being compared.

- **Desired state:** the state described in an approved configuration source, such as Git, Terraform configuration, Helm charts, Kubernetes manifests, or a configuration management system.
- **Actual state:** the state reported by the live system or provider at observation time, such as live cloud resources, cluster objects, or running process configuration.

This can be visualized as:

~~~mermaid
flowchart TD
    A["Git / IaC / approved configuration"] --> B["Desired state"]
    B --> C["Deploy or reconcile"]
    C --> D["Live environment"]
    D --> E["Actual state"]
    B --> F["Drift detection"]
    E --> F
    F --> G{"Any difference?"}
    G -- "No" --> H["Record synchronized state"]
    G -- "Yes" --> I["Classify and assess impact"]
    I --> J["Approve handling approach"]
    J --> K["Reconcile or update configuration"]
    K --> D
~~~

A meaningful comparison requires matching scope and timing. For instance, you cannot compare a static replica count in Git against a live replica count managed by an autoscaler without accounting for the autoscaling policy. Similarly, do not compare staging configuration against production configuration when differences between the two environments are intentional.

### 2.1. Sources of truth must be defined

Each configuration type needs a source of truth and an owner:

| Configuration type | Common desired source | Observable actual state |
|---|---|---|
| Cloud infrastructure | Terraform, Pulumi, or other IaC | APIs and resources returned by the provider |
| Kubernetes workloads | Manifests, Helm, Kustomize, GitOps repository | Objects in the API server and running Pods |
| Application | Versioned config files, schemas, and environment overlays | Values loaded by the app at startup or runtime |
| Access permissions | IAM policies, RBAC, policy as code | Effective granted permissions |
| Container images | Approved release records and digests | Running image digest |
| Feature flags | Flag management system or controlled config | Active flag state |
| Network and firewalls | IaC or centralized policies | Actual rules on cloud, host, or cluster |

Multiple sources must not simultaneously act as authoritative for the same property. If both Git and console edits are used to modify the same resource without synchronization rules, drift will continually recur.

## 3. Drift vs. Intentional Environment Differences

Not every difference between two environments is drift. Staging and production may need different configuration due to differing load, permissions, data, endpoints, and scale.

Examples:

- Staging runs two replicas while production runs six replicas.
- Staging uses a sandbox payment service while production uses the live endpoint.
- Production uses a less verbose log level to reduce data exposure risk.
- Production configures higher quotas and resource limits.
- A feature flag is enabled for a small user group before broader rollout.

These differences are valid when declared in controlled configuration or policy. They become drift when actual state diverges from the approved configuration for that specific environment.

Use overlays, input variables, or per-environment configuration instead of editing hosts manually after each deployment.

Example structure:

~~~text
config/
  base/
    application.yaml
  environments/
    dev.yaml
    staging.yaml
    production.yaml
~~~

`base` holds shared values. Each environment file specifies permitted differences. The pipeline must identify which overlay applies to the target environment and record the rendered configuration identifier.

### 3.1. Runtime values that legitimately change

Some values are managed dynamically by the system at runtime:

- Replica counts adjusted by a Horizontal Pod Autoscaler.
- Dynamically assigned cluster IP addresses or nodes.
- Timestamps, resource versions, and status fields managed by Kubernetes.
- Automatically renewed certificates.
- Rotated short-lived tokens.
- Leader or primary instance elections in distributed systems.

If a drift detector compares every field mechanically, it will raise excessive noise requiring no action. Define which fields are operator-managed, which are controller-managed, and which are ignored under policy.

## 4. Common Types of Configuration Drift

Drift can be classified by origin and impact severity.

| Drift type | Manifestation | Common risk |
|---|---|---|
| Infrastructure | Instance types, networks, storage, security groups differ from IaC | Outages, unexpected costs, or expanded attack surface |
| Workload | Image, replicas, command, resource limits differ from manifests | Running the wrong version or instability |
| Application | Environment variables, feature flags, timeouts changed | Behavior diverges from test results |
| Security | IAM, RBAC, firewall, or secret policies modified | Excessive permissions and data exposure |
| Dependency/runtime | Package, runtime, or agent versions differ from expectations | Build and production inconsistency |
| Data and schema | Migrations or data structures diverge from desired state | Incompatibilities during deploy or rollback |
| Process | Manual changes lacking commits, tickets, or release records | Loss of traceability |

Also distinguish configuration drift from software drift. If a container runs a different image digest than the release record, that is deployment version drift. If the image is right yet an environment variable is wrong, that is runtime configuration drift. Both can cause service behavior to differ from what was tested.

## 5. Where Does Drift Come From?

### 5.1. Manual changes outside the pipeline

Administrators may modify resources via cloud consoles, `kubectl edit`, SSH, or database administration tools. These actions may be necessary during incidents, yet if they are not recorded back in the configuration source, state drifts.

Mitigation involves restricting direct edit permissions, enforcing a break-glass workflow for emergencies, and requiring changes to be committed into Git or IaC once the service stabilizes.

### 5.2. Pipelines and IaC do not cover all attributes

If a resource is created with IaC while certain attributes are ignored or unmanaged by the provider, operators may alter them undetected.

For instance, Terraform may manage networks and instances without managing internal application configuration. Another tool or mechanism is then required to manage application configuration.

### 5.3. Competing automation modifying the same resource

Autoscalers, operators, controllers, policy engines, and human operators may touch the same object. Without defined field ownership, systems may repeatedly overwrite one another.

Specify which controller owns which attributes and use field ownership mechanisms or equivalent settings where supported by the platform.

### 5.4. Platform defaults or version changes

Upgrading Kubernetes, cloud providers, runtimes, or modules can alter defaults, API behavior, or auto-generated values. If desired configuration leaves critical properties implicit, actual state can shift with platform versions.

For security- or operations-critical attributes, declare values explicitly and validate them during upgrades.

### 5.5. Hotfixes never synchronized back

A direct hotfix can restore a service quickly. However, if the pipeline later applies the old configuration, the emergency fix may be overwritten. Or if the hotfix never enters Git, drift persists and reappears the next time an environment is provisioned.

After incident resolution, create an official change, review it, and update the desired source.

## 6. Detecting Drift with IaC

Infrastructure as Code describes infrastructure resources in versionable configuration. IaC tools can compare desired descriptions against live resource states observed from the provider.

With Terraform, understand the roles of three components:

- **Configuration:** desired declarations in Terraform configuration files.
- **State:** mapping between resources in configuration and real objects managed by Terraform, along with necessary metadata.
- **Remote infrastructure:** resources currently existing on the provider.

During a standard `terraform plan` run, Terraform refreshes resource information as supported by the provider and calculates changes needed to bring the system back to configuration. If someone altered a resource directly in the cloud, the plan can surface that difference.

### 6.1. Inspecting plans before applying

Example:

~~~bash
terraform init
terraform plan -out=tfplan
terraform show tfplan
~~~

The plan indicates whether the tool intends to create, modify, replace, or destroy resources. Carefully inspect destroy/replace actions and changes to IAM, security groups, databases, storage, and public exposure.

Never automatically apply every plan merely because the command succeeded. Plans must be evaluated by environment, permissions, and change policy.

### 6.2. Refresh-only mode

Terraform provides refresh-only mode to inspect or update state to match current infrastructure without proposing resource changes from configuration.

~~~bash
terraform plan -refresh-only
~~~

This command reveals external changes detected by Terraform and how they would be reflected in state. If updating state after review is appropriate, run:

~~~bash
terraform apply -refresh-only
~~~

Refresh-only updates state to reflect actual state; it does not revert infrastructure back to desired configuration. When the goal is restoring resources to desired state, inspect a normal plan and evaluate Terraform's proposed actions.

State can contain sensitive data. Store state in a protected backend, restrict access, encrypt it, and avoid printing state contents or plans containing secrets to public logs.

### 6.3. Plans do not catch every kind of drift

Detection capabilities depend on providers, resource schemas, managed attributes, and refresh behavior. Changes unobserved by the provider or outside managed resource scope may not appear in plans.

Therefore, combine IaC plans with application configuration checks, policy checks, cloud security posture tools, and runtime monitoring.

## 7. Detecting Drift in Kubernetes and GitOps

In Kubernetes, desired state typically lives in manifests, Helm charts, or Kustomize overlays. Actual state consists of objects stored in the API server and live running workloads.

GitOps tools such as Argo CD or Flux continuously compare Git state against the cluster. They report:

- **Synced:** managed state matches desired state per comparison rules.
- **OutOfSync:** differences exist that require attention.
- **Healthy/Degraded:** operational status of resources or workloads based on health assessment.

Sync status and health status are distinct concepts. An application can be configuration-synced yet unhealthy due to an application bug. Conversely, a workload can serve traffic fine yet be `OutOfSync` because someone manually changed replicas or the image.

### 7.1. Reconciliation

A GitOps controller can either merely report drift or automatically reconcile the cluster back to desired state. When auto-sync/self-heal is enabled, manual changes may be overwritten by the controller on its next reconciliation cycle.

Before enabling auto-remediation:

- Clearly scope which resources and namespaces the controller manages.
- Exclude fields owned by other controllers.
- Verify handling of secrets and runtime data.
- Enforce Git change reviews and audits.
- Ensure break-glass interventions are not wiped out before the team records and evaluates them.

Do not enable broad self-healing across all resources without understanding field ownership. A controller can endlessly revert legitimate changes made by an autoscaler or another operator if both manage the same field.

### 7.2. Checking rendered manifests

With Helm or Kustomize, compare outputs rendered with the target environment's exact values/overlays. Inspecting standalone template files misses final values assembled from multiple sources.

Record the commit, chart version, values, and image digest used to generate manifests. That way, when the cluster drifts, the team knows the exact desired state being compared against.

## 8. Detecting Drift in Runtime Application Configuration

An application may receive configuration from multiple sources:

- Configuration files packaged in the artifact.
- Environment variables.
- Secret manager.
- ConfigMaps or mounted files.
- Command-line arguments.
- Feature flag systems.
- Service discovery or remote configuration.

To detect drift, determine the effective values the application is actively using and compare them against desired values after applying environment overlays.

For example, declared configuration:

~~~yaml
service:
  timeout: 3s
  retry:
    maxAttempts: 2
  featureFlags:
    newCheckout: false
~~~

Yet the live process might receive `SERVICE_TIMEOUT=10s` from an environment variable. If the application gives environment variables higher precedence, the effective value is 10 seconds. Inspecting only the YAML file would miss this discrepancy.

Ways to improve observability:

- Expose an application endpoint or command displaying effective configuration with secrets stripped.
- Log the config version or checksum at startup.
- Include config version and environment in logs/metrics.
- Validate required variables and permitted value ranges.
- Track feature flag changes and actors.
- Never write secret values into logs or diagnostic endpoints.

Distinguish configuration loaded at startup from dynamically read configuration. If an application reads environment variables only at boot, changing a variable on the orchestrator may not take effect until Pods are recreated.

## 9. Controlled Comparison: Normalization and Ignoring Dynamic Fields

Comparing desired and actual state should not be a naive plain-text diff. Two configurations may differ in field ordering or formatting while carrying identical semantics. Conversely, two identical files may produce different behavior due to defaults or variables loaded from external sources.

A sound comparison workflow should:

1. Parse data into typed structures.
2. Normalize defaults and ordering where appropriate.
3. Apply the target environment's overlay.
4. Exclude or annotate controller-managed fields.
5. Normalize dynamic values such as timestamps, auto-assigned IPs, or resource versions.
6. Compare operationally and security-relevant fields.
7. Output contextual diffs containing no secrets.

Avoid ignoring too many fields just to silence alerts. Every ignored field needs a justification, an owner, and periodic review. Broadly ignoring `image`, `securityContext`, or `serviceAccount` can blind drift detection to critical changes.

## 10. Classifying Drift by Severity and Action

Not every drift case warrants automatic remediation. Classify before deciding how to act.

| Severity | Examples | Recommended action |
|---|---|---|
| Critical | Administrative port opened to Internet, out-of-policy admin access granted, unapproved image digest | High-priority alert, block promotion, or isolate per runbook |
| High | Database misconfiguration, missing storage encryption, wrong workload version | Open incident/change request and require prompt remediation |
| Medium | Timeout, replica, or resource limit outside permitted bounds | Add to backlog with SLA and assigned owner |
| Low | Labels, annotations, or metadata not affecting behavior | Record and clean up during standardization cycle |
| Permitted | Replicas adjusted by autoscaler within limits | Not treated as a violation; continue monitoring per policy |

Severity should reflect impact, exploitability, blast radius, and service requirements. A minor label change may carry low risk, whereas altering a label used by network policies can compromise security.

### 10.1. Unknown status does not mean passing

If an API is unreachable, a provider returns an error, or the tool lacks read permissions, the system has no proof that actual state matches desired state.

Distinguish clearly:

- **PASS:** full scope compared with no policy-blocking drift found.
- **DRIFT_FOUND:** divergence detected requiring classification.
- **UNKNOWN/ERROR:** unable to inspect or missing data.
- **EXEMPTED:** divergence approved as intentional and still valid.

Never convert `UNKNOWN` into `PASS` just to unblock a pipeline. Policies may allow certain non-critical jobs to continue on inspection errors, but must accurately record status rather than issuing false compliance evidence.

## 11. Handling Drift: Update Desired State or Restore Actual State?

When drift is detected, there are two main paths:

**Update desired state:** if the live change is valid, intentional, and approved, bring that change into Git/IaC, review it, and deploy via the pipeline. This formalizes a hotfix into canonical configuration.

**Restore actual state:** if the live change is unauthorized or unwanted, return the system to approved configuration via the pipeline or controller. Verify impact before applying.

A handling workflow should include:

1. Identify the drifted resource, attribute, and environment.
2. Collect the diff, detection timestamp, and actor or system likely responsible.
3. Assess impact on security, availability, data, and users.
4. Determine whether the change was intentional or out-of-process.
5. Choose between updating desired state or restoring actual state.
6. Open a change request/pull request if needed and obtain proper approvals.
7. Apply through configuration management tooling.
8. Re-run drift detection and verify service health.
9. Document root cause and preventive actions.

Never blindly run apply or toggle self-heal the moment drift appears. A manual change might be a live hotfix preventing a larger outage; auto-reverting before understanding context can trigger downtime.

## 12. Preventing Drift Recurrence

Detecting drift is necessary but insufficient. Reduce opportunities for changes outside the source of truth.

### 12.1. Managing changes through Git

- Store IaC, manifests, and application configuration in reviewed repositories.
- Require pull requests for critical changes.
- Protect branches and enforce required status checks.
- Retain approval and commit history.
- Use shared modules or templates to curb ad-hoc configurations.
- Never keep production configuration files solely on personal machines.

### 12.2. Restricting direct modifications

- Use RBAC/IAM to restrict edit privileges.
- Grant read-only roles to observers.
- Separate deployment permissions from full resource administration permissions.
- Use break-glass access for emergencies.
- Log every modification and review post-incident.
- Revoke temporary privileges once resolved.

### 12.3. Controlled automated reconciliation

GitOps controllers or configuration tools can automatically converge actual state to desired state. Before enabling, define management scope, field ownership, change windows, and rollback mechanisms.

For stateful data resources or hard-to-reverse changes, consider alerting and requiring human approval instead of automatic remediation.

### 12.4. Scheduled checks

Drift can emerge after a pipeline finishes. Running checks only at deployment time misses changes occurring hours or days later.

Run checks:

- In pull requests to validate desired configuration.
- Before apply or deploy.
- Post-deployment.
- On a recurring schedule.
- After security events or permission changes.
- Before expanding rollouts or releasing new versions.

Frequency should match risk and tool capabilities. High-privilege resources or critical data stores warrant more frequent checks.

## 13. Integrating Drift Detection into CI/CD

Pipelines can run different steps depending on environment type:

~~~mermaid
flowchart TD
    A["Pull request changing IaC or manifests"] --> B["Format, validate, and policy check"]
    B --> C["Plan / render / diff"]
    C --> D{"Results valid?"}
    D -- "No" --> E["Block merge and report"]
    D -- "Yes" --> F["Review and approve"]
    F --> G["Apply or deploy"]
    G --> H["Post-deploy verification"]
    H --> I["Scheduled drift check"]
    I --> J{"Actual matches desired?"}
    J -- "Yes" --> K["Record PASS"]
    J -- "No" --> L["Classify drift and alert"]
    L --> M["Update desired or reconcile"]
    M --> I
~~~

A drift detection pipeline should:

- Target the exact workspace, state backend, cluster context, and environment.
- Hold sufficient read permissions to observe without write permissions when only inspecting.
- Never print secrets or sensitive state to logs.
- Record commit, tool version, timestamp, and inspection scope.
- Distinguish real drift from dynamic or controller-managed fields.
- Return `UNKNOWN` when inspection cannot complete.
- Auto-remediate only drift categories evaluated and permitted by policy.

### 13.1. Separating detection from remediation

A safe design separates two jobs:

- **Detect:** read-only inspection of actual state, diff generation, and reporting.
- **Remediate:** holds modification permissions, runs after approval or under explicitly defined automated policies.

This separation reduces the risk of a comparison bug immediately altering production. It also lets operators review the plan before execution.

## 14. Real-World Example: Cloud Security Group Drift

Suppose Terraform defines a security group allowing HTTPS connections only from a load balancer. During an investigation, an administrator opens SSH from all addresses to access a server.

Following this action:

1. Actual cloud state diverges from Terraform configuration.
2. The next `terraform plan` detects the extra ingress rule.
3. The drift report identifies the modified port, source CIDR, and resource.
4. The team evaluates whether this was an approved break-glass action.
5. If no longer needed, the team removes the out-of-policy rule via IaC.
6. If long-term admin access is required, the team redesigns access via VPN, bastion, or an approved access mechanism and updates configuration.
7. The pipeline runs plan, policy checks, and apply through normal workflow.
8. A subsequent drift check confirms the security group matches desired state.

This example shows drift detection both catches out-of-band changes and generates evidence to improve access design.

## 15. Real-World Example: Kubernetes Running the Wrong Image

Suppose a GitOps repository declares:

~~~yaml
spec:
  template:
    spec:
      containers:
        - name: checkout
          image: registry.example.invalid/checkout@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
~~~

However, an operator edits the Deployment directly to use the `latest` image tag. The cluster may still appear to run normally, yet actual state no longer corresponds to the reviewed release.

Verify:

- The actual running image digest of the Pod.
- Deployment revision history.
- Which user or controller modified the object.
- Which digest the `latest` tag resolved to at pull time.
- Whether the image has valid provenance and scan results.

If the GitOps controller has self-heal enabled, it can restore the image to the declared digest. Afterward, verify new Pods run the expected digest and pass health checks. If the change was a legitimate hotfix, commit the new digest into Git via a pull request and re-run quality gates.

## 16. Pseudocode Example for a Drift Report

A drift report should highlight actionable attributes rather than dumping the entire configuration.

~~~yaml
drift_report:
  environment: production
  checked_at: "2026-11-18T08:30:00Z"
  source_revision: "4f8c2a1"
  scope: "network/security-groups"

  summary:
    status: DRIFT_FOUND
    blocking_findings: 1
    advisory_findings: 1

  findings:
    - resource: "checkout-admin-sg"
      attribute: "ingress.ssh.source"
      desired: "10.20.0.0/16"
      actual: "0.0.0.0/0"
      severity: critical
      action: "review-and-remediate"

    - resource: "checkout-api"
      attribute: "replicas"
      desired: "managed-by-autoscaler"
      actual: 5
      severity: informational
      action: "ignore-by-approved-policy"
~~~

Reports must exclude secrets, private keys, tokens, and full state dumps. Sanitize `actual` values if they may contain sensitive data. For autoscaler-managed attributes, policies should explicitly state the scope and why they are not treated as violations.

## 17. Common Anti-Patterns

| Anti-pattern | Consequence | Improvement |
|---|---|---|
| Checking drift only at deploy time | Post-deployment drift goes undetected | Run scheduled checks and checks after sensitive changes |
| Treating every difference as an error | Alert fatigue from dynamic or controller fields | Normalize and declare field ownership |
| Auto-applying on every drift detection | Can revert active hotfixes or cause downtime | Classify, review, and separate detect from remediate |
| Editing production directly without updating Git | Drift reappears on the next deployment | Sync changes back to the source of truth |
| Maintaining multiple sources of truth | Tools repeatedly overwrite one another | Assign a single owner per configuration category |
| Ignoring check errors due to missing permissions | `UNKNOWN` state mistaken for `PASS` | Distinguish observation failures from passing checks |
| Comparing staging against production | Valid differences misreported as drift | Compare actual vs. desired state within the same environment |
| Printing full state or runtime config | Risks exposing secrets | Redact and emit only necessary diffs |
| Ignoring IAM/network changes | Silently increases security risk | Assign dedicated severity and alerts |
| Untracked exceptions | Unclear which drift is accepted and until when | Track owner, justification, and expiration for exceptions |

## 18. Configuration Drift Management Checklist

**Desired source**

- [ ] Every configuration category has a clear source of truth and owner.
- [ ] Desired state is stored in Git or a versioned management system.
- [ ] Per-environment differences are explicitly declared.
- [ ] Dynamic and controller-managed fields are identified.

**Detection**

- [ ] Tooling exists to compare desired state against actual state.
- [ ] Checks cover infrastructure, workloads, and runtime configuration appropriately.
- [ ] Checks run both in pipelines and on a schedule.
- [ ] Reports tie back to commit, environment, and timestamp.
- [ ] Uninspectable states record `UNKNOWN/ERROR`.

**Handling**

- [ ] Drift is classified by impact.
- [ ] Workflows exist to update desired state or restore actual state.
- [ ] Detect and remediate privileges are properly separated.
- [ ] Emergency changes use break-glass workflows with post-review.
- [ ] Post-remediation verification and root-cause documentation occur.

**Security and operations**

- [ ] Direct edit privileges are restricted and audited.
- [ ] State, secrets, and runtime config are never exposed in logs.
- [ ] Exception policies specify owners and expiration dates.
- [ ] Alerts exist for drift involving IAM, networks, and images.
- [ ] Safeguards prevent controllers or automation from overwriting one another.

## 19. Conclusion

Configuration drift is the gap between approved state and the state the system is actually executing. Accurate detection requires defining sources of truth, distinguishing intentional differences from drift, understanding controller- or automation-managed fields, and comparing within the right environment scope.

IaC plans, GitOps diffs, runtime configuration checks, and scheduled audits provide complementary perspectives. When divergence is detected, classify impact before deciding whether to update desired state or restore actual state. Separating detection from automated remediation, preserving evidence, and syncing hotfixes back to configuration sources keep environments consistent, traceable, and recoverable across the entire CI/CD lifecycle.
