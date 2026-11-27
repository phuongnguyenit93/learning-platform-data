# Managing identity, configuration, and policy across distributed clusters

A hybrid and edge system often spans multiple Kubernetes or container clusters across regions, data centers, factories, retail stores, and edge locations. These clusters need shared security standards and platform configurations while still operating when WAN connectivity is unstable or the central management plane is temporarily unreachable. If each cluster creates its own identities, stores secrets ad hoc, and applies isolated policies, the organization struggles to control access, detect configuration drift, and prove compliance.

**Multi-cluster identity management** determines which users, workloads, nodes, and clusters are permitted to authenticate or access resources. **Multi-cluster configuration management** distributes desired configurations to each cluster and tracks actual state. **Multi-cluster policy management** establishes security, networking, resource, and operational rules applied consistently across the fleet.

In **CLOUD_CORE_SERVICES_COMPUTE**, you need a governance model that combines shared standards with local site execution. A central control plane can manage cluster registration, identity, configuration, and policy; each cluster still needs local authentication, caching of essential configuration, state storage, and local policy enforcement to keep operating when disconnected.

## 1. The challenge of managing a cluster fleet

A fleet can consist of:

- Central clusters running shared services.
- Regional production clusters.
- Data center or branch clusters.
- Edge clusters in factories, stores, or gateway appliances.
- Testing and development clusters.
- Clusters operated by partners or external units.

Clusters may differ in Kubernetes versions, hardware, networking, connectivity, and data requirements. Therefore, centralized management does not mean every cluster must have identical configuration.

### 1.1. Problems to solve

| Problem | Consequence if unmanaged |
| --- | --- |
| Inconsistent user identities | Long-lived local accounts, hard to revoke and audit |
| Workloads using long-lived credentials | Leaked secrets can grant prolonged unauthorized access |
| Clusters granting arbitrary permissions | Over-privileged access and weak cross-site control |
| Unversioned distributed configs | Clusters exhibit divergent behavior |
| Manually updated policies | A cluster can miss security baselines |
| Offline clusters without policy caches | Workloads may fail to schedule or run uncontrolled |
| No drift tracking | Actual configuration diverges from approved state |
| No clear ownership | Unclear who handles incidents or approves exceptions |

### 1.2. Central control plane and local enforcement

A common architecture separates two roles:

- **Central management plane:** manages inventory, identity federation, policy bundles, configuration releases, auditing, and fleet status.
- **Local cluster control plane:** authenticates requests, enforces RBAC/admission policies, runs workloads, caches received configs, and keeps operating when central connectivity drops.

~~~mermaid
flowchart TB
    IDP["Enterprise Identity Provider"] --> HUB["Central Fleet Management"]
    GIT["Config and Policy Repository"] --> HUB
    HUB --> REG["Cluster Registry and Audit"]
    HUB --> C1["Region Cluster"]
    HUB --> C2["Datacenter Cluster"]
    HUB --> C3["Edge Cluster"]
    C1 --> W1["Workloads and Local Policy"]
    C2 --> W2["Workloads and Local Policy"]
    C3 --> W3["Workloads and Cached Policy"]
    C3 -. "WAN unavailable" .-> OFF["Local operation with last valid release"]
~~~

The central management plane distributes desired state and collects results. Local clusters still need sufficient components to authenticate, enforce policies, and serve workloads within permitted boundaries.

### 1.3. Separating management plane and workload plane

The management plane governs the fleet; the workload plane serves business operations. If every application request had to traverse the central management plane, a WAN outage could disrupt edge operations.

Keep essential data and control flows local:

- Local APIs and workers call internal site services.
- Admission controllers and RBAC enforce rules inside the cluster.
- Verified policy bundles are cached locally.
- Telemetry is buffered while offline and forwarded upon reconnection.
- Sensitive administrative actions can require central connectivity or extra approval.

## 2. Classifying identities in multi-cluster systems

Do not share one credential type across operators, workloads, and clusters. Each identity category has a distinct lifecycle, permission set, and verification mechanism.

| Identity type | Subject | Examples |
| --- | --- | --- |
| Human identity | Users or administrators | SREs, platform engineers, auditors |
| Workload identity | Applications or service accounts | APIs, controllers, batch workers |
| Cluster identity | A registered cluster | edge-site-017, region-prod-a |
| Node identity | Worker machines or edge devices | Node serials, VM instance identities |
| Service identity | Services communicating with other services | SPIFFE ID or certificate subject |
| Automation identity | CI/CD, GitOps controllers, provisioning agents | Deployment pipelines, policy sync agents |

Every identity must be tied to an owner, environment, scope, expiration, and status. Never share a single account across the entire fleet, because credential compromise makes blast-radius assessment and targeted revocation difficult.

## 3. Managing human identities

### 3.1. Using a centralized identity provider

Organizations typically maintain an enterprise identity provider for employee lifecycles, groups, and multi-factor authentication. Clusters can integrate via OIDC or platform-supported authentication mechanisms.

Basic flow:

1. Users sign in through the identity provider.
2. The identity provider authenticates, enforces MFA, and issues a token.
3. The Kubernetes API or management portal verifies the token.
4. Groups/claims map to RBAC permissions.
5. Audit logs record principal, action, resource, cluster, and timestamp.

Avoid creating local per-cluster users when centralized identity is available. However, maintain a controlled break-glass procedure for scenarios where the identity provider or WAN is unreachable.

### 3.2. Mapping groups to RBAC

Groups in the identity provider can map to roles:

- Fleet viewer: views inventory and status.
- Cluster operator: manages workloads within assigned clusters.
- Namespace developer: deploys applications within granted namespaces.
- Security auditor: reads policies, audit logs, and compliance evidence.
- Platform administrator: manages platform components.

Do not grant cluster-admin to developer groups simply because they deploy applications. Use namespace-scoped Roles/RoleBindings and reserve ClusterRoles/ClusterRoleBindings for permissions that genuinely require cluster scope.

### 3.3. Example namespace-scoped RBAC

The following manifest grants read access to pods, deployments, and pod logs in the `production-app` namespace:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: app-observer
  namespace: production-app
rules:
  - apiGroups: [""]
    resources: ["pods", "pods/log", "services"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: app-observer-binding
  namespace: production-app
subjects:
  - kind: Group
    name: platform-observers
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: app-observer
  apiGroup: rbac.authorization.k8s.io
~~~

The group name in this example must match the username/group claim received by the API server after OIDC configuration. RBAC handles authorization only; it does not authenticate users or verify MFA by itself.

### 3.4. Just-in-time access and break-glass

High-privilege administrative access should be time-bound and need-based:

- Users request access with a justification and ticket.
- The system verifies approval and duration.
- Access is granted at the narrowest scope.
- Audit logs record grant time, actions taken, and revocation.
- Access expires automatically after the access window.

Break-glass is emergency access when centralized authentication is unavailable. Break-glass credentials must be protected separately, stored offline or in a tightly controlled vault, inventoried, and tested periodically. Every usage must trigger alerts and post-incident review.

## 4. Workload identities and service accounts

Workload identity lets pods or containers authenticate to databases, cloud APIs, secret managers, or internal services without embedding long-lived access keys into images.

### 4.1. Dedicated service account per workload

Avoid letting every pod run under the default service account with broad permissions. Create service accounts per application or function and attach appropriate Roles/RoleBindings or federation mappings.

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: production-app
automountServiceAccountToken: false
~~~

This example disables automatic mounting of Kubernetes API tokens. If a workload needs to call the Kubernetes API or use a projected token for workload identity federation, configure appropriate projected volumes/token audiences and lifetimes rather than disabling tokens without an alternative.

### 4.2. Workload identity federation

A common pattern uses the cluster's OIDC issuer to mint short-lived tokens for service accounts. A cloud provider or identity broker trusts that issuer and exchanges tokens for scoped workload credentials.

Conceptual flow:

1. Pod runs under a dedicated service account.
2. Cluster issues a projected service account token with a specific audience.
3. Workload presents the token to a trusted identity endpoint.
4. Identity provider verifies issuer, signature, subject, audience, and expiration.
5. Workload receives short-lived credentials with mapped permissions.
6. Credentials renew automatically across their lifecycle and are never baked into images.

### 4.3. Avoiding overly broad trust

Each cluster has its own issuer and trust configuration. If multiple clusters share an overly permissive trust relationship, tokens from less-hardened clusters could be accepted for production resources.

Restrict federation by:

- Exact cluster issuer.
- Specific subject/service account.
- Specific audience.
- Namespace or workload identity.
- Environment and resource scope.
- Token lifetime and revocation conditions.

Never accept every subject from every cluster merely because tokens are signed by a trusted issuer.

### 4.4. Service-to-service identity

In distributed systems, services can mutually authenticate using mTLS and short-lived certificates. SPIFFE/SPIRE exemplifies workload identification and issuing SVIDs/certificates per trust domain.

Principles:

- Service identity does not rely on ephemeral IPs or hostnames.
- Certificates have short lifetimes and rotate automatically.
- Trust bundles are distributed and updated in a controlled manner.
- Peer identity verification and authorization are handled separately.
- Processes exist to revoke or remove trust if a cluster is compromised.

TLS encrypts the transport channel; authorization must still determine which service may invoke which API or resource.

## 5. Cluster and node identities

Clusters need stable identities to register, receive configurations, and ship telemetry.

### 5.1. Cluster registration

When creating a cluster, the fleet management system should record:

- Unique cluster ID.
- Name and owner.
- Environment: dev, staging, production.
- Site, region, and failure domain.
- Provider/platform and deployment mode.
- Kubernetes version or runtime version.
- Network reachability and management connectivity.
- Trust domain and identity issuer.
- Active policy/configuration release.
- Creation date, status, and credential expiration date.

Never use cluster name as a credential. Names can change or collide; cluster IDs and cryptographic identities must be verified separately.

### 5.2. Bootstrap identity

A bootstrap identity is the credential used for initial cluster registration. It should be:

- Short-lived or single-use.
- Restricted strictly to the registration action.
- Stored in a secret store or secure provisioning workflow.
- Never baked into node images or public scripts.
- Replaced by a permanent identity once registration succeeds.
- Revoked after bootstrapping.

If a bootstrap token leaks, attackers may register rogue clusters or seize administrative privileges depending on scope. Never use bootstrap credentials as long-term operational credentials.

### 5.3. Node identity

Nodes need identities to join clusters and obtain runtime certificates/credentials. Control:

- Node registration and authorization.
- Certificate rotation.
- Instance replacement and decommissioning.
- Node attestation if required by the environment.
- Preventing reuse of credentials from deleted nodes.

When a node is lost or suspected of compromise, revoke its identity and certificates, remove it from the cluster, inspect workloads that ran on it, and rotate related credentials.

## 6. Certificate and trust bundle management

In hybrid/edge deployments, certificates serve API servers, kubelets, mTLS, ingress, webhooks, registries, and service-to-service traffic.

### 6.1. Certificate lifecycle

A lifecycle workflow needs:

1. Issuance from a trusted CA or certificate authority.
2. Binding certificates to explicit identities and intended usage.
3. Expiration tracking and pre-expiry alerts.
4. Automated rotation prior to expiration.
5. Verification that the new certificate works before retiring the old one.
6. Revocation when an identity is compromised or no longer valid.

Do not issue non-rotating long-lived certificates simply because edge sites frequently lose connectivity. Instead, design appropriate lifetimes, cached trust bundles, and renewal workflows upon reconnection.

### 6.2. Multi-cluster trust bundles

Clusters may belong to different trust domains. When cross-cluster communication is required, distribute trust bundles with explicit scope and versioning:

- Cluster A trusts only service identities from approved domains.
- Cluster B does not blindly trust every certificate across the fleet.
- Trust bundles carry versions, checksums/signatures, and validity windows.
- If a CA is compromised, emergency procedures can revoke and replace trust roots.

Avoid one unrestricted shared root CA across all edge devices if compromise blast radius is too large. Partition CAs by region, site, or security domain.

## 7. Multi-cluster configuration management

Configuration must be managed as versioned desired state with clear owners and change history. Do not manually edit individual clusters and expect them to stay synchronized.

### 7.1. Layering configuration

A useful hierarchy:

1. **Organization baseline:** shared security, logging, and identity standards.
2. **Fleet profile:** configuration for cluster tiers, such as production or edge.
3. **Region/site profile:** endpoints, networking, timezone, and local storage.
4. **Cluster profile:** capacity, add-ons, and cluster-specific topology.
5. **Workload configuration:** application-level settings.

Inheritance order and override rules must be unambiguous. Sensitive configuration such as secrets should never be inherited as plaintext from a repository.

### 7.2. Declarative configuration and GitOps

GitOps treats a repository as the source of desired state. Controllers in each cluster compare live configuration against approved revisions and reconcile drift.

Typical flow:

1. Engineers propose configuration changes via pull request.
2. CI validates schemas, policies, linting, and security scans.
3. Authorized reviewers review and approve.
4. The repository records an immutable commit/version.
5. Fleet controllers or GitOps agents distribute releases to target clusters.
6. Agents verify, apply, and report status.
7. Drift is detected and handled per policy.

~~~mermaid
flowchart LR
    DEV["Engineer"] --> PR["Pull request"]
    PR --> CHECK["Validation and policy checks"]
    CHECK --> APPROVE["Approval"]
    APPROVE --> REPO["Versioned config repository"]
    REPO --> HUB["Fleet release controller"]
    HUB --> G1["Region GitOps agent"]
    HUB --> G2["Datacenter agent"]
    HUB --> G3["Edge agent"]
    G1 --> S1["Reconcile and report"]
    G2 --> S2["Reconcile and report"]
    G3 --> S3["Reconcile or use cached release"]
~~~

GitOps does not mean every change must automatically overwrite live state. Certain drift should raise alerts or enter an approval workflow rather than auto-reverting immediately, especially when manual edits reflect emergency mitigations.

### 7.3. Versioning and immutability

Each configuration release should include:

- Version or commit ID.
- Target cluster list.
- Bundle digest.
- Schema version.
- Creation timestamp and approver.
- Policy compatibility.
- Rollout and rollback criteria.

Clusters must report the exact version currently applied. Never rely on mutable tags like `latest` as the sole identifier for production releases.

## 8. Secrets and sensitive configuration

Configs and secrets have different lifecycles. Non-sensitive configs can live in Git; secrets must be governed through secret managers, encryption, and access policies.

### 8.1. Secrets management principles

- Never commit plaintext secrets into repositories.
- Never bake secrets into container images.
- Never pass secrets via labels or annotations.
- Keep secrets out of logs, crash dumps, and command-line arguments.
- Grant each workload access only to the secrets it requires.
- Use short-lived credentials wherever possible.
- Test rotation with overlap/transition windows.
- Audit who reads or modifies secrets.

### 8.2. Distributing secrets to the edge

Edge sites may experience extended WAN outages. Decide which secrets can be cached locally and for how long.

A policy might:

- Cache short-lived credentials for permitted local operations.
- Avoid caching fleet-wide admin credentials unnecessarily.
- Encrypt locally stored data and protect keys with TPM/HSM where available.
- Set expirations and restrict offline permissions.
- Refresh credentials and check revocation status when connectivity returns.
- Transition workloads to a safe state if secrets expire while offline, rather than letting credentials remain valid indefinitely.

No central rotation mechanism can immediately update an offline site. Designs must define acceptable offline windows and evaluate the risk of valid credentials persisting during those windows.

## 9. Multi-cluster policy management

Policies define which actions are permitted, denied, or flagged. Policies apply across multiple layers:

- Identity and authorization.
- Kubernetes admission control.
- Image provenance and registries.
- Pod security and Linux capabilities.
- Network ingress/egress.
- Resource quotas and limit ranges.
- Node/region placement.
- Data residency and encryption.
- Logging, auditing, and retention.

### 9.1. Policy-as-code

Policy-as-code expresses rules as configuration that can be reviewed, tested, versioned, and automatically distributed. Examples include OPA/Gatekeeper, Kyverno, Kubernetes Pod Security Admission, and cloud provider policy engines.

A well-designed policy includes:

- Clear owner and objective.
- Cluster/namespace/workload scope.
- Enforce, warn, or audit mode.
- Denial reason and remediation guidance.
- Version and effective date.
- Exception workflow with expiration.
- Test cases for both compliant and non-compliant workloads.

### 9.2. Enforce, audit, and warn

| Mode | Behavior | When to use |
| --- | --- | --- |
| Audit | Logs violations without blocking | Baseline discovery and impact assessment |
| Warn | Returns warnings to deployers | Gradual transition before enforcement |
| Enforce | Rejects non-compliant resources | Tested rules requiring strict compliance |

Never enable `enforce` fleet-wide before checking cluster versions, legacy workloads, webhook availability, and required exceptions. A faulty policy can block rollouts or prevent new workloads from starting.

### 9.3. Fail-open and fail-closed

Admission webhooks can be configured for how to behave when the webhook is unreachable:

- **Fail-closed:** requests are rejected if policy evaluation fails. Stronger protection, but can impact availability if the policy service breaks.
- **Fail-open:** requests proceed if the webhook does not respond. Increases availability, but can bypass controls.

Choose based on policy risk. For rules protecting critical security boundaries, fail-closed may be appropriate; for advisory or non-critical policies, consider fail-open with auditing. Use short timeouts, high availability, and webhook monitoring.

## 10. Policy baselines and exceptions

A fleet baseline may include:

- Allowing images only from approved registries.
- Requiring scanned or signed images per policy.
- Blocking privileged containers and host namespaces without an exception.
- Requiring resource requests/limits.
- Restricting `hostPath` and volume types.
- Requiring non-root execution and dropped capabilities.
- Controlling ingress/egress.
- Requiring audit logging and retention.
- Restricting regions, zones, or node pools.
- Requiring workload identities instead of static keys.

### 10.1. Layering policies

Not every cluster shares identical requirements. For example:

- Production may enforce image signatures and strict network segmentation.
- Development may allow debug images in isolated namespaces.
- Offline edge may require registry caches and signed policy bundles.
- Clusters handling sensitive data may require region pinning and mandatory encryption.

The organizational baseline remains the minimum floor. Specialized profiles may relax rules only with explicit approval and documented justification.

### 10.2. Controlled exceptions

Exceptions should document:

- Exempted policy.
- Specific resource/namespace/cluster.
- Accountable owner.
- Business justification and risk.
- Approver.
- Expiration date.
- Compensating controls.
- Audit trail and review schedule.

Never create fleet-wide wildcard exceptions just to unblock one workload deployment. Exceptions without expiration dates easily become permanent, unmonitored policy gaps.

## 11. Drift detection and reconciliation

Drift is the difference between approved desired configuration and actual cluster state.

Common causes:

- Manual edits by operators.
- Other controllers modifying resources.
- Offline clusters missing releases.
- API versions or default behaviors changing after upgrades.
- Policies altered or disabled.
- Incomplete secret/certificate rotations.

### 11.1. Classifying drift

| Drift type | Example | Action |
| --- | --- | --- |
| Benign | Fields defaulted by the API server | Normalize before comparing |
| Operational | Replica count adjusted by HPA | Exclude dynamic fields from desired-state comparison |
| Unauthorized | Manually added RBAC binding | Alert, revert, or require review |
| Security-critical | Privileged pod appears | Block, isolate, or remediate per runbook |
| Connectivity | Cluster missed recent releases | Keep last-known-good and report stale status |
| Version drift | Cluster lagging behind baseline upgrades | Schedule rollout or assess compatibility |

Do not auto-reconcile every field. HPAs, controllers, and operators manage specific fields; GitOps must avoid ownership conflicts and overwrite loops.

### 11.2. Drift remediation

Three approaches:

- **Notify-only:** report drift for the owner to resolve.
- **Reconcile:** restore resources to desired state.
- **Quarantine:** exclude the workload or cluster from sensitive traffic/administration when drift is severe.

Choose actions according to risk. For unexpected admin privilege changes, prioritize containment and auditing. For non-critical configuration, alerting may suffice.

## 12. Managing edge clusters during disconnection

Edge clusters often face limited bandwidth, high latency, and periods without central connectivity. Identity, configuration, and policy management must support bounded offline operation.

### 12.1. Local autonomy

When the WAN drops:

- Local workloads keep serving within permitted boundaries.
- The local control plane continues enforcing installed RBAC and admission policies.
- The GitOps agent retains the last verified release.
- Telemetry is buffered and shipped once connectivity recovers.
- Actions requiring the central identity provider may be restricted.
- Unverified bundles or certificates without valid signatures are rejected.

### 12.2. Last-known-good configuration

Clusters should retain the last verified configuration and policy release. When receiving a new release:

1. Verify signature and digest.
2. Confirm version/schema compatibility.
3. Validate policies and dependencies.
4. Apply to staging or test resources if available.
5. Run health checks and evaluate outcomes.
6. Mark the new release active only after checks succeed.
7. Retain the prior version for rollback.

If a rollout fails, the cluster reverts to last-known-good using a safe procedure. Never delete the prior release immediately upon applying a new one.

### 12.3. Offline identity

For edge sites, local authentication can rely on pre-issued short-lived credentials, certificates, or time-bounded cached identities. Specify:

- Who is authorized to log in offline?
- Which permissions remain available?
- Maximum offline credential lifetime?
- When is online revalidation required?
- What happens if a user is disabled centrally while the site is offline?

An offline site cannot immediately know an account was revoked centrally. For sensitive actions, require central connectivity or use very short-lived credentials.

### 12.4. Conflicts upon reconnection

During an outage, local operators may apply emergency changes. When connectivity returns:

- Compare local state against desired state.
- Distinguish approved emergency changes from unknown drift.
- Do not automatically delete changes that could affect operational safety.
- Log audit events and require owner confirmation on conflicts.
- Reconcile according to defined precedence and versioning rules.

## 13. Distributing configuration and policy via rollout rings

Never push a new policy or configuration to every cluster simultaneously. A flaw in a baseline rule can break workload scheduling across the entire fleet.

### 13.1. Rollout rings

A phased strategy may define:

1. Lab/dev clusters.
2. Canary clusters representing a region/site.
3. Low-criticality production groups.
4. Broader production.
5. Edge clusters grouped by connectivity and hardware tiers.

Each ring needs promotion gates:

- Agents received the expected version.
- Policy tests pass.
- No abnormal rise in admission rejections.
- Workload health remains intact.
- No severe drift or credential failures.
- Owner sign-off for high-risk changes.

### 13.2. Rollback

Policy rollback must be planned ahead of time:

- Retain prior versions and signed artifacts.
- Know which fields can be safely rolled back.
- Never roll back incompatible schema/data migrations.
- Have procedures to restore identity trust if CAs or issuers changed.
- Audit who triggered the rollback.

Some changes—such as CA rotation or certificate revocation—cannot be trivially reversed. Use overlapping trust bundles and staged cutovers.

## 14. Auditing, compliance, and ownership

Multi-cluster governance must answer who changed what, where, when, and under which approval.

### 14.1. Audit events

An audit record should contain:

- Actor identity and authentication method.
- Cluster ID and site.
- Resource/namespace.
- Action and outcome.
- Synchronized timestamp.
- Source IP or device context where applicable.
- Change request/approval ID.
- Config/policy release version.
- Correlation ID.

Never record access tokens, private keys, or secret values in audit logs.

### 14.2. Ownership metadata

Every cluster and workload needs clear owners and contacts. Useful metadata:

- Business owner.
- Technical owner.
- Environment.
- Cost center.
- Data classification.
- Criticality tier.
- Region/site.
- Policy profile.
- Support window.

Missing ownership slows incident response and leaves security exceptions unreviewed.

### 14.3. Compliance evidence

Artifacts to collect:

- Cluster inventory and versions.
- Active policy bundles/versions.
- Compliance scan results.
- Active exception list and expiration dates.
- RBAC bindings and privileged access history.
- Certificate expiration/rotation status.
- Drift reports.
- Backup/restore and DR exercise results.

Evidence must include timestamps, sources, and freshness status. Stale reports do not prove current cluster compliance.

## 15. Securing the control plane and management agents

Fleet management agents often hold elevated cluster privileges. If an agent is compromised, attackers can alter policies or deploy unauthorized workloads.

Safeguards:

- Run dedicated service accounts with least privilege.
- Separate read-only inventory agents from agents permitted to mutate resources.
- Verify bundle signatures and source repositories.
- Protect webhooks and API endpoints with mTLS or strong identity.
- Do not expose management APIs to the Internet unnecessarily.
- Restrict egress and inbound traffic.
- Monitor agent versions, heartbeats, and integrity.
- Provide mechanisms to revoke cluster identities.
- Separate release approval permissions from deployment execution permissions.

Never allow an unbounded central credential to administer every cluster without scoping, approvals, or auditing.

## 16. Example fleet repository structure

A GitOps repository can separate baselines, profiles, and workloads:

~~~text
fleet-config/
  policies/
    baseline/
    production/
    edge/
    exceptions/
  clusters/
    region-a-prod/
      profile.yaml
      workloads/
    datacenter-b/
      profile.yaml
      workloads/
    edge-site-017/
      profile.yaml
      workloads/
  identities/
    trust-bundles/
    service-account-mappings/
  releases/
    release-2026-11/
      manifest.yaml
~~~

This structure is illustrative. Do not store plaintext secrets in these directories. Instead, store references to secret managers, encrypted secret manifests, or policies governing runtime secret retrieval.

### 16.1. Example cluster profile

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: site-profile
  namespace: fleet-system
data:
  site: edge-site-017
  environment: production
  region: ap-southeast
  policyProfile: edge-restricted-v3
  configRelease: release-2026-11
  offlineMode: "enabled"
~~~

This ConfigMap holds only non-secret metadata for illustration. A controller can use labels/annotations or custom resources to bind clusters to profiles. Never treat a ConfigMap as proof of cluster authenticity; cryptographic identity must be verified independently.

## 17. Incident procedure for cluster compromise or lost trust

When suspecting cluster compromise, handle identity, policy, and connectivity together:

1. Identify the cluster ID, site, issuer, and associated credentials.
2. Stop issuing new credentials to that cluster.
3. Revoke or restrict suspected certificates/tokens.
4. Isolate management paths and egress per the incident plan.
5. Preserve audit logs, system logs, and forensic evidence.
6. Assess affected workloads, nodes, secrets, and trust bundles.
7. Rebuild nodes/clusters from trusted artifacts if required.
8. Issue a new cluster identity and re-register.
9. Distribute verified policy/config releases.
10. Return the cluster to the fleet only after owner/security sign-off.

Do not merely delete the cluster from a dashboard and consider the incident closed. Old credentials or trust relationships may still be accepted elsewhere until explicitly revoked.

## 18. Common design mistakes

- Sharing `cluster-admin` or a single service account across multiple workloads.
- Embedding long-lived credentials in images or manifests.
- Trusting every subject from every cluster under a shared issuer.
- Skipping certificate rotation or failing to track expirations.
- Storing plaintext secrets in Git.
- Leaving configuration and policy bundles unversioned.
- Pushing new policies across the entire fleet without canary rings.
- Enforcing untested policies that cause admission controllers to block valid workloads.
- Using fail-open on critical security policies without compensating controls.
- Using fail-closed on non-HA webhooks, causing cluster-wide outages when a webhook fails.
- Auto-reconciling fields managed by HPAs/operators, creating drift loops.
- Lacking last-known-good state for offline edge clusters.
- Caching offline credentials indefinitely.
- Creating exceptions without expiration dates.
- Failing to revoke trust when clusters are decommissioned or compromised.
- Missing owners, audit trails, and runbooks for individual sites.

## 19. Identity, configuration, and policy checklist

**Identity**

- [ ] Human identities integrate with an IdP, MFA, and group mapping.
- [ ] RBAC follows least privilege and minimal scope.
- [ ] Workloads use dedicated service accounts/identities.
- [ ] Federation constrains issuer, subject, audience, and resources.
- [ ] Bootstrap credentials are time-limited and revoked after registration.
- [ ] Certificate rotation and trust bundles are versioned.
- [ ] Break-glass access has owners, auditing, and expiration.

**Configuration**

- [ ] Configuration is layered across organization/fleet/site/cluster/workload.
- [ ] Desired state is versioned and approved.
- [ ] GitOps agents reconcile with clear field ownership.
- [ ] Secrets are stored in a secret manager or appropriate encrypted store.
- [ ] Drift detection and remediation policies are defined.
- [ ] Edge clusters maintain last-known-good state and local autonomy.

**Policy**

- [ ] Security baselines apply across the fleet.
- [ ] Policies define owners, scope, mode, and tests.
- [ ] Audit/warn modes are used before enforce where appropriate.
- [ ] Fail-open/fail-closed choices match policy risk and webhook HA.
- [ ] Exceptions include justification, approval, and expiration.
- [ ] Policy rollouts use rings and support rollback.

**Operations**

- [ ] Each cluster has an ID, owner, site, and environment.
- [ ] Audits log actor, action, cluster, and release version.
- [ ] Alerts exist for stale clusters, offline agents, and expiring certificates.
- [ ] Telemetry is buffered when edge sites go offline.
- [ ] Runbooks exist for decommissioning, compromise, and re-enrollment.
- [ ] Compliance evidence reports remain up to date.

## 20. Fleet governance rollout sequence

1. Inventory clusters, sites, owners, environments, and trust boundaries.
2. Select identity providers and federation models for humans, workloads, and clusters.
3. Standardize RBAC, service accounts, and workload identities.
4. Establish bootstrapping, certificate lifecycles, and trust bundles.
5. Build declarative configuration and policy-as-code repositories.
6. Separate baselines, fleet profiles, site profiles, and workload configs.
7. Integrate CI validation, approvals, signing, and release versioning.
8. Deploy local agents/controllers with least privilege.
9. Configure last-known-good caching and offline policies for the edge.
10. Start in audit/warn mode, resolve violations, and issue time-bound exceptions.
11. Enforce via rollout rings after testing and measuring impact.
12. Enable drift detection, auditing, compliance dashboards, and alerts.
13. Drill WAN outages, credential expirations, policy rollbacks, and cluster compromises.
14. Periodically review permissions, exceptions, certificates, and ownership.

## 21. Operational principles

1. **Dedicated identity per principal:** humans, workloads, nodes, and clusters never share credentials.
2. **Scoped federation:** validate issuer, subject, audience, and scope; never trust the entire fleet by default.
3. **Short-lived, rotating credentials:** limit blast radius if a token or certificate leaks.
4. **Declarative, versioned configuration:** approved repositories and releases act as the source of desired state.
5. **Tested policy-as-code:** use audit/warn before enforce when appropriate, with expiring exceptions.
6. **Local enforcement:** clusters must enforce RBAC and policies even when the management plane is offline.
7. **Last-known-good at the edge:** apply only verified bundles and preserve rollback capability.
8. **Classified drift:** distinguish benign/dynamic changes, emergency actions, and security violations.
9. **Ring-based rollouts:** validate impact on small cohorts before fleet-wide expansion.
10. **Complete auditing and ownership:** every cluster, policy, and exception has an owner, history, and runbook.

Managing identity, configuration, and policy across distributed clusters requires a fleet governance model with shared standards that does not depend entirely on continuous central connectivity. Identity federation authenticates users, workloads, and clusters within explicit scopes; GitOps and versioned configuration keep desired state consistent; policy-as-code controls deployments and operations; and local enforcement, cached releases, and last-known-good state allow the edge to keep operating safely while offline. Combining these mechanisms with certificate rotation, auditing, drift detection, and ring-based rollouts enables organizations to govern large hybrid/edge fleets while preserving site-level autonomy.
