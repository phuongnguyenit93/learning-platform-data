# Attached Clusters and Managing Kubernetes Outside GCP

Many organizations operate Kubernetes simultaneously on Google Kubernetes Engine (GKE), Amazon EKS, Azure AKS, and self-managed clusters in on-premises data centers. Each environment provides the Kubernetes API yet differs in how it handles identity, networking, storage, logs, metrics, upgrades, and incident support. When every team uses an entirely separate toolset, the platform easily drifts out of standard, lacks inventory, becomes hard to audit for permissions, and struggles to enforce consistent policies.

**GKE attached clusters** is the capability to connect existing Kubernetes clusters **outside Google Cloud** into a Google Cloud-supported management model. Combined with **fleet management**, organizations can manage inventory, access control, and selected configuration, security, and observability features across clusters on different platforms. This is part of a hybrid and multicloud infrastructure strategy, not an automatic migration of applications to GCP.

The most important point: **attaching does not mean Google Cloud owns or manages the entire control plane, worker nodes, and storage of the underlying cluster**. The original provider or operations team remains responsible for those components. This lesson walks through architecture design, registering and verifying an attached cluster, IAM/RBAC authorization, access via Connect Gateway, GitOps, policies, observability, security, and reliable operations.

## 1. The Hybrid and Multicloud Kubernetes Problem

Suppose a company operates four environments:

- EKS serving transactional systems on AWS.
- AKS running customer support applications on Azure.
- Self-managed Kubernetes in a data center for internal data processing.
- GKE running APIs and analytics services on Google Cloud.

All of them may use Deployments, Services, StatefulSets, or ConfigMaps, yet their underlying infrastructure implementations differ.

| Layer | Differences to govern |
|---|---|
| Identity | AWS IAM, Microsoft Entra ID, Google Cloud IAM, and Kubernetes RBAC |
| Cluster | Kubernetes version, distribution, node pools, and upgrades |
| Networking | VPC/VNet, CNI, ingress, DNS, firewalls, and routing |
| Storage | CSI drivers, PersistentVolumes, snapshots, and backups |
| Security | Admission policies, image policies, workload identity, secrets |
| Observability | Logs, metrics, traces, alerts, and retention |
| Delivery | Helm, Kustomize, GitOps, CI/CD, and artifact registries |
| DR | Regions, backups, cluster rebuilds, and data recovery |

The goal of centralized management is not to make every cloud identical, but to establish a **common minimum baseline** for inventory, permissions, policies, quality, and recoverability, while preserving necessary provider-specific differences.

## 2. Distinguishing GKE, Attached Clusters, and Fleet

| Concept | Role | Where workloads run |
|---|---|---|
| GKE Standard/Autopilot | Kubernetes provided on Google Cloud under the GKE model | Google Cloud |
| GKE Multi-Cloud | Product family for managing/deploying Kubernetes across multicloud environments as supported | Google Cloud or other platforms depending on type |
| GKE attached cluster | Registers an existing Kubernetes cluster outside GCP into Google Cloud's management plane | AWS, Azure, or supported external infrastructure |
| Fleet | Logical group of clusters and shared management configurations | Multiple environments |
| Fleet membership | Represents a registered cluster within a fleet | Management metadata in Google Cloud |

Do not confuse the **attached cluster resource** with the **fleet membership resource**. These two resource types can have different APIs, names, and locations; seeing a membership appear does not mean every attached-cluster feature is active.

### What does NOT change after attaching

- The original cluster continues using its existing control plane, nodes, and storage.
- Applications are not automatically migrated to GCP.
- EKS/AKS/on-prem remain governed by their native upgrade workflows, quotas, HA, and support.
- Google Cloud IAM does not replace Kubernetes RBAC or native cloud provider admin permissions.
- Volume/database data is not replicated to GCP simply because the cluster is registered.

**Support scope depends on distribution, Kubernetes version, cluster type, features, and timing.** Always check support documentation before deploying to production.

## 3. Reference Architecture

A management solution typically spans these layers:

1. Kubernetes clusters outside Google Cloud.
2. Connectivity components or agents per the supported attached-cluster model.
3. Cluster and fleet management resources in Google Cloud.
4. An approved remote access mechanism such as Connect Gateway.
5. GitOps, Policy Controller, or equivalent policy tooling.
6. Monitoring, Logging, and auditing.
7. Native operational workflows for nodes, networking, storage, and backups.

~~~mermaid
flowchart TD
    A[Platform team and CI CD] --> B[Google Cloud fleet]
    B --> C[Cluster inventory and membership]
    B --> D[Approved access and policy]
    B --> E[Monitoring and audit]
    C --> F[Cluster connectivity integration]
    D --> F
    E --> F
    F --> G[EKS at AWS]
    F --> H[AKS at Azure]
    F --> I[On-prem Kubernetes]
    G --> J[AWS control plane and workers]
    H --> K[Azure control plane and workers]
    I --> L[Data-center infrastructure]
~~~

This diagram illustrates logical architecture; it does not assert that every attached cluster uses identical agents, APIs, or features.

### Management plane and data plane

The **management plane** handles inventory, control, policies, and administrative access. The **data plane** runs Pods and application traffic. If management connectivity to Google Cloud is interrupted, workloads can keep serving if runtime dependencies remain intact, though policy sync, gateway access, or centralized observability may degrade.

A sound design measures these two health planes independently.

## 4. Criteria for Selecting Clusters to Connect

Before registering a cluster, verify:

- The distribution and Kubernetes version are supported by attached clusters.
- The API server and node health are stable.
- CNI, CSI, DNS, admission webhooks, and network policies are functioning properly.
- An owner is accountable on the native provider side.
- Someone holds sufficient permissions to install agents/integrations and configure identity.
- Outbound DNS/TLS/HTTPS and any required proxies can reach target endpoints.
- Requirements for data residency, logging, auditing, and key management are addressed.
- Runbooks exist for connection loss, certificate expiry, upgrades, and detaching.
- A project/billing owner is assigned and management, logging, and egress costs are budgeted.

Start with a **staging** or lab cluster containing no real sensitive data. During the pilot, verify read permissions, inventory, syncing, and a non-destructive policy before expanding to production.

## 5. Designing Fleets and Management Scopes

Fleets should reflect real accountability boundaries. Example:

~~~text
fleet-platform-staging
  eks-orders-staging
  aks-commerce-staging
  kubernetes-lab

fleet-platform-prod
  eks-orders-prod
  aks-commerce-prod
~~~

The structure above is an illustrative grouping, not fleet resource syntax. An organization can use one or multiple projects/fleets based on service limits and policies.

### Grouping rules

- Separate production and non-production environments where permission and policy isolation is required.
- Clusters within the same group should share aligned ownership, trust levels, and baselines.
- Apply labels or inventory metadata for cloud provider, business service, team, and environment.
- Never use one all-powerful deployment identity across every cluster.
- Keep membership names stable so dashboards and alerts do not lose links.

### Resource location

The location of an attached cluster or fleet membership does not necessarily match the region where the cluster physically runs. Some APIs use `global`, while others use regional locations. When invoking CLI commands or APIs, use the exact location returned in the resource name or documented for your version.

## 6. Preparing the Google Cloud Environment

The management project needs proper IAM, GKE Multi-Cloud/fleet APIs, and only the features actually used. Before enabling APIs or creating resources, determine:

| Component | Questions to answer |
|---|---|
| Fleet project | Which project owns memberships and policies? |
| Billing | Which entity pays for management services, logging, and egress? |
| IAM | Who can view inventory, attach/detach, use Gateway, and edit policies? |
| APIs | Which attached cluster types and fleet features must be enabled? |
| Security | Are there organization policies, VPC-SC, or identity restrictions? |
| Location | Which `global`/region locations do resources use? |
| IaC | Is Terraform or another tool the source of truth? |

You can inspect currently enabled APIs:

~~~bash
gcloud services list --enabled --project="FLEET_PROJECT_ID"
~~~

To view gcloud command groups in your environment:

~~~bash
gcloud container attached clusters --help
gcloud container fleet memberships --help
~~~

These are read-only help commands. Do not apply an unverified list of APIs or registration flags across every distribution.

## 7. Preparing the External Cluster Side

The EKS/AKS/on-prem side requires its own set of prerequisites:

1. `cluster-admin` or a sufficiently authorized identity for registration and integration installation.
2. Native cloud provider permissions to configure networking/identity when the procedure requires them.
3. Outbound connectivity to required Google service endpoints.
4. Working DNS, TLS CA trust, and proxy settings.
5. Secured and audited policies for installing agents/CRDs/namespaces.
6. No admission policies blocking mandatory components from running.
7. A fallback procedure to uninstall the agent and revert changes after testing.

Never open a Kubernetes API server publicly just to make an onboarding step succeed. Depending on the model, outbound cluster-initiated connections reduce the need to expose endpoints directly, but must follow product documentation.

## 8. Attached Cluster Registration Workflow

Registration should be orchestrated as a verifiable change:

~~~mermaid
flowchart TD
    A[Assess cluster and owner] --> B[Confirm support and security]
    B --> C[Prepare IAM and network]
    C --> D[Register attached cluster]
    D --> E[Install required integration]
    E --> F[Check cluster and fleet status]
    F --> G[Verify least-privilege access]
    G --> H[Enable pilot policy and observability]
    H --> I[Record inventory and rollback]
~~~

### Detailed steps

- Survey the distribution, Kubernetes version, and required features.
- Follow the official registration procedure matching your provider and version.
- Record resource names, project, location, membership, and service identities.
- Verify agents/connectivity components inside the cluster.
- Use a read-only account to confirm inventory and health.
- Test integrations with Gateway, GitOps, Policy Controller, and Logging if selected.
- Save configuration and evidence in the ticketing/IaC system.
- Do not enable broad policy enforcement until validated in the lab.

Registration commands vary across cluster types. Before executing, check your current CLI syntax:

~~~bash
gcloud container attached clusters register --help
gcloud container attached clusters list --help
~~~

If your CLI lacks a command group or option, follow the Google Cloud documentation for your organization's attached cluster type and version. Do not treat an unverified example command as a production deployment command.

## 9. Verifying Fleet Membership

After registration, list memberships:

~~~bash
gcloud container fleet memberships list \
  --project="FLEET_PROJECT_ID"
~~~

Inspect membership details once you have the right location:

~~~bash
gcloud container fleet memberships describe "MEMBERSHIP_NAME" \
  --project="FLEET_PROJECT_ID" \
  --location="MEMBERSHIP_LOCATION"
~~~

### Fields to record

- Membership and attached cluster resource names.
- Distribution/version and native provider.
- Latest connection status.
- Enabled features and feature health.
- Owner, environment, and data classification.
- Last update timestamp and agent versions.
- Direct access runbook when Gateway is unavailable.

**The existence of a membership does not mean the cluster or workloads are healthy.** Check Kubernetes nodes/Pods and applications separately, as well as feature sync status where applicable.

## 10. Accessing Clusters via Connect Gateway

Connect Gateway can provide Kubernetes API access through Google Cloud's management layer in supported scenarios. Configuring access typically requires both Google Cloud IAM and cluster-side authentication/authorization mechanisms.

~~~mermaid
sequenceDiagram
    participant O as Operator
    participant I as Google Cloud IAM
    participant G as Connect Gateway
    participant C as Cluster-side connectivity
    participant K as Kubernetes API server
    O->>I: Authenticate identity
    O->>G: Request access to membership
    G->>I: Check gateway permissions
    G->>C: Forward authorized request
    C->>K: Kubernetes API request
    K-->>O: RBAC-controlled response
~~~

This diagram shows the conceptual flow; exact identities, headers, and agent mechanics depend on the actual configuration.

You can fetch a kubeconfig via Connect Gateway when supported:

~~~bash
gcloud container fleet memberships get-credentials "MEMBERSHIP_NAME" \
  --project="FLEET_PROJECT_ID" \
  --location="MEMBERSHIP_LOCATION"
~~~

Then verify the context:

~~~bash
kubectl config get-contexts
kubectl --context="APPROVED_ATTACHED_CONTEXT" get namespaces
~~~

Never use the default context unless you are certain which cluster it targets.

## 11. Distinguishing Google Cloud IAM and Kubernetes RBAC

At least two independent authorization layers exist:

| Layer | Controls |
|---|---|
| Google Cloud IAM | Viewing fleets, attached clusters, using Gateway, updating memberships or features |
| Kubernetes RBAC | Operations on Pods, Deployments, Secrets, and namespaces inside the cluster |
| Provider IAM | Modifying EKS/AKS control planes, worker nodes, networking, and storage in the native cloud |
| Admission policies | Allowing/denying manifests against security standards |
| Workload identity | Which principal workloads use to call Google Cloud APIs or external services |

An operator with Gateway access is not automatically `cluster-admin`. Conversely, a Kubernetes RoleBinding grants no permissions to modify a Google Cloud project.

### Namespace-scoped read-only RBAC

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-reader
  namespace: fleet-lab
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
~~~

Bind to a group actually authenticated by the cluster:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: platform-readers
  namespace: fleet-lab
subjects:
  - kind: Group
    name: platform-readers
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: pod-reader
  apiGroup: rbac.authorization.k8s.io
~~~

Group names in manifests only work if Kubernetes authentication maps operators into that group. Do not assume IAM groups and Kubernetes groups sync automatically.

## 12. Application Identity: Workload Identity Federation

Workloads running outside GCP need identities to call Cloud Storage, Pub/Sub, or Secret Manager. **Attaching a cluster does not automatically give every Pod ADC like GKE or Cloud Run.**

A safe option is Workload Identity Federation for external workloads, using identity claims from an authorized system.

~~~mermaid
flowchart LR
    A[Pod on EKS or AKS] --> B[External identity token]
    B --> C[Google Security Token Service]
    C --> D[Short-lived Google credential]
    D --> E[Cloud Storage or Pub Sub]
    F[Identity pool and provider] --> C
    G[IAM grants on resource] --> E
~~~

### Configuration layers

- External identity issuer/audience trusted by Google Cloud.
- Workload identity pool and provider with accurate attribute mappings.
- Attribute conditions restricting cluster, namespace, and service account where appropriate.
- IAM on the resource or authorization to impersonate a Google service account.
- External account credential configuration for the Google Auth Library.
- Token refresh mechanism and protection of metadata/credential sources.

Never accept every token issued by a broad identity provider without restricting principals. Avoid long-lived JSON service account keys whenever federation is viable.

### Testing

In a lab project/bucket:

1. An authorized Pod can read the permitted object.
2. An unauthorized Pod is denied.
3. No private keys exist in containers or Git.
4. Access tokens/ID tokens are never printed to logs.
5. IAM access can be revoked per incident response procedures.

## 13. GitOps and Multi-Cluster Configuration Sync

GitOps manages manifests through pull requests, reviews, and a controlled Git revision. In a fleet environment, you can use Config Sync across supported clusters, or Argo CD/Flux if the organization has standardized on them and needs different tooling.

Example repository layout:

~~~text
platform-config/
  base/
    namespaces/
    rbac/
    networkpolicies/
    observability/
  overlays/
    eks-staging/
    aks-staging/
    eks-prod/
    aks-prod/
~~~

### Principles

- Base manifests contain only shareable Kubernetes definitions.
- Differences in IngressClass, StorageClass, CSI, CNI, and identity belong in overlays.
- Production branches require proper approvals.
- CI validates schemas, policies, and permission risks before merge.
- Controllers monitor drift, sync errors, and health.
- Roll back by reverting to a known-good release; avoid repeated manual edits directly on clusters.

Example lab Namespace:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: fleet-lab
  labels:
    environment: staging
    owner: platform-runtime
~~~

If a manifest is edited via `kubectl` while GitOps holds the source of truth, the controller may overwrite that change. Define break-glass procedures and update source control during incident resolution.

## 14. Policy Controller and Admission Standards

A multi-cloud platform needs a shared security baseline without erasing cluster-specific requirements:

- Block privileged containers unless an explicit exception exists.
- Restrict `hostPath`, `hostNetwork`, and Linux capabilities.
- Require owner/environment labels and approved image registries.
- Limit wildcard RBAC and `cluster-admin` usage.
- Validate reasonable resource requests/limits.
- Enforce Pod security, image signatures, and provenance where supported.
- Restrict which namespaces or workloads can access sensitive secrets.

### Phased rollout

1. Write policies and unit-test them against sample manifests.
2. Run in audit or dry-run mode if supported by the tool.
3. Review violations, false positives, and application owners.
4. Create scoped exceptions with justification, owner, scope, and expiration.
5. Canary enforce on low-risk namespaces/clusters.
6. Monitor admission errors and rollout health.
7. Expand progressively across cluster groups.

Never enforce a brand-new policy simultaneously across all production clusters without testing compatibility first.

### Policies do not replace network firewalls

Admission controls check configuration. NetworkPolicy works properly only when supported by the CNI and configured correctly. Cloud firewalls, proxies, and VPC segmentation still require separate design at each provider.

## 15. Cross-Cloud Networking and Connectivity

Classify traffic by purpose:

| Traffic path | Items to check |
|---|---|
| Cluster agent → Google APIs | DNS, HTTPS, CA, proxy, egress allowlist |
| Operator → Connect Gateway | SSO, IAM, endpoint reachability |
| Pod → Artifact Registry | Registry auth, image pulls, egress, and latency |
| Pod → Cloud Storage/Pub/Sub | WIF identity, networking, quotas, and data residency |
| Pod → database in another cloud | VPN/interconnect, routes, encryption, and egress |
| Logs/metrics → Google Cloud | Volume, PII, retention, and cost |

Never widen firewalls solely to pass a test. If using a proxy with TLS interception, verify it does not break the trust chain required by connectivity components.

### Two independent connectivity planes

- **Management traffic:** registration, policies, inventory, and administrative Kubernetes access.
- **Application traffic:** requests, databases, objects, events, and business dependencies.

When management traffic fails, applications do not necessarily fail. Conversely, Connect Gateway showing Connected does not guarantee traffic to databases or ingress is healthy.

### Residency

Telemetry data, control metadata, and application payloads do not carry the same sensitivity. Document clearly which data types leave for Google Cloud, their location, and retention. Do not assume attaching automatically sends application data to GCP.

## 16. Observing Logs, Metrics, and Health

Signals to monitor:

- Node Ready/NotReady and Pods in Pending/CrashLoopBackOff states.
- Deployment/StatefulSet readiness.
- Admission policy violations.
- GitOps sync/drift status.
- Agent connectivity and certificate/token expiration.
- Application request latency, error rates, throughput, and saturation.
- Kubernetes audit logs, IAM changes, and access errors.
- Egress volume, billing, and resource usage.

Some Cloud Logging, Cloud Monitoring, or Managed Service for Prometheus features can be deployed via agents/collectors and integrations. **Merely registering a cluster does not guarantee all logs and metrics appear in Cloud Monitoring.**

### Designing labels

Suggested dimensions:

~~~text
fleet=platform-production
cluster=eks-orders-prod
provider=aws
environment=production
namespace=orders
workload=orders-api
~~~

Avoid adding high-cardinality dimensions like user IDs, request IDs, or Pod UIDs as metric labels without clear justification; high cardinality drives up cost.

### Independent views

Maintain at least three dashboard groups:

1. Application SLOs: availability, latency, error rate.
2. Cluster health: nodes, Pods, autoscaling, capacity.
3. Management integrations: agent connections, sync, policies, gateway.

## 17. CI/CD and Multi-Cluster Deployment

An artifact should preserve the exact same image digest between staging and production, while manifests use per-cluster overlays.

~~~mermaid
flowchart TD
    A[Source commit] --> B[Build test scan]
    B --> C[Image digest]
    C --> D[Staging EKS overlay]
    C --> E[Staging AKS overlay]
    D --> F[Staging checks]
    E --> F
    F --> G[Approval]
    G --> H[Production canary]
    H --> I[Observe SLO]
    I --> J[Gradual rollout to remaining clusters]
~~~

Distinguish clearly:

- Running the same container image does not mean clusters share identical storage/ingress settings.
- Cloud Deploy does not necessarily treat every attached cluster like a native GKE target; verify support or choose an appropriate GitOps workflow.
- Secrets and service accounts must not be shared arbitrarily across clouds.
- A rollout failure should stay isolated to the target cluster.

### Always specify context

~~~bash
kubectl config get-contexts
kubectl config current-context
kubectl --context="APPROVED_LAB_CONTEXT" get namespaces
~~~

Apply manifests only after confirming the context matches the intended environment:

~~~bash
kubectl --context="APPROVED_LAB_CONTEXT" apply -f namespace.yaml
~~~

Never write scripts that loop over every kubeconfig context and blindly apply a single production manifest.

## 18. Storage and Data When Running Outside GCP

An attached cluster continues using its native CSI drivers and storage backend. A PersistentVolume on EKS does not turn into a Google Cloud Persistent Disk.

For stateful workloads, define:

- PersistentVolume provisioners and snapshot support.
- Replication and backups by region/provider.
- Database ownership, HA, RTO/RPO, and retention.
- Key management and decryption access during DR.
- Restore capability onto another cluster in the same cloud or another cloud.
- Cross-cloud data transfer costs.

Multi-cloud fleet management does not replace disaster recovery. If you want cross-cloud application failover, design data replication, schemas, DNS/traffic routing, and data consistency separately.

## 19. Upgrading Clusters, Agents, and Component Versions

Kubernetes upgrades require coordination across two layers:

| Layer | Responsibility |
|---|---|
| Native provider | Control plane, worker nodes, VPC/VNet, CNI, CSI, quotas |
| GCP management | Compatibility with attached-cluster integrations, fleet features, and Google IAM |
| Platform team | Agents, Config Sync, Policy Controller, GitOps, and alerts |
| Application team | API deprecations, CRD compatibility, workloads, and SLOs |

Safe workflow:

1. Check the cluster/agent/Kubernetes version support matrix.
2. Review API deprecations and rollback options.
3. Back up critical configurations and data.
4. Upgrade staging and verify all integrations.
5. Verify Gateway, policies, GitOps, and observability.
6. Proceed to production via canary/maintenance windows.
7. Update inventory and runbooks.

Do not expect Google Cloud to upgrade EKS or AKS nodes on behalf of the native owner simply because the cluster is attached.

## 20. When the Management Plane or Connectivity Fails

Scenarios to drill:

| Incident | Potential impact | Mitigation |
|---|---|---|
| Agent cannot reach Google Cloud | Gateway or sync may degrade | Check proxy/egress/TLS; keep native access intact |
| Google IAM/SSO unavailable | Operators cannot use Gateway | Break-glass into the native cluster |
| GitOps source down | New config changes fail to sync | Hold safe state and retry per runbook |
| Admission webhook fails | Deployments may be blocked depending on failure policy | HA, policy rollback, and emergency procedures |
| EKS/AKS region outage | Workloads and data plane lose availability | Execute DR in the native cloud |
| Expired certificate or outdated agent | Management connectivity fails | Version/cert rotation and monitoring |

### Break-glass design

- Maintain emergency identities managed by the native cloud provider.
- Lock down and audit access strictly.
- Use only when incident criteria are met.
- Time-bound and revoke right after resolution.
- Run periodic drills to verify the procedure works end-to-end.

Do not wait until Gateway disconnects to figure out how to create a native admin account.

## 21. Security and Shared Responsibility

Layers to protect:

1. Google Cloud IAM for fleets, Gateway, and policies.
2. Provider IAM for native clusters, nodes, and networking.
3. Kubernetes RBAC for resources inside namespaces.
4. Admission policies for Pods, images, and RBAC manifests.
5. Workload identity when Pods call Google APIs.
6. Encryption, retention, backups, and data classification.
7. Network segmentation and egress controls.
8. Supply chain and source control for manifests.

### Testing positive and negative paths

- An authorized operator can read Pods in the lab namespace.
- Another operator is denied at Gateway.
- A read-only operator cannot delete Deployments.
- A Pod without WIF cannot read the test bucket.
- Policy-violating manifests are flagged in audit mode or rejected in enforce mode.
- Logs contain no unnecessary credentials or PII.

Never grant `cluster-admin` to everyone just to fix one permission error. Determine whether the failure occurred at Gateway IAM, authentication mapping, RBAC, or admission.

## 22. Multi-Cloud Cost and FinOps

Attaching clusters can introduce or increase several cost categories:

- Underlying EKS/AKS/on-prem infrastructure costs.
- Attached cluster management fees under the applicable pricing model.
- Network egress when sending data to Google Cloud.
- Log/metric ingestion and retention.
- Artifact Registry downloads and storage.
- GitOps/CI/CD runners, security scanning, and operations.

### How to measure

Track costs by cluster, cloud provider, team, environment, and workload. When comparing costs across two clouds, include networking, storage, observability, SLAs, and operational effort—not just CPU/memory.

Reduce unnecessary cross-cloud log/metric shipping using sampling, retention policies, and secret/PII filtering. Never disable critical security or SLO signals solely for short-term cost savings.

## 23. Troubleshooting Attached Clusters

| Symptom | Likely cause | Diagnosis |
|---|---|---|
| Cluster missing from fleet | Wrong project/location, incomplete registration | Membership list, resource names |
| Membership exists but disconnected | Agent, DNS, proxy, cert, egress | Agent logs and endpoint connectivity |
| Gateway HTTP 403 | Missing Google IAM or org policy block | Principal and gateway permissions |
| `kubectl` Forbidden after connecting | Kubernetes RBAC or group mapping | RoleBinding/ClusterRoleBinding |
| Pod not Ready | CNI, image, storage, workload | Pod events and node status |
| GitOps drift | Repo auth, webhook, policy conflict | Sync status, Git revision |
| Admission rejected | Misaligned constraint | Policy violations and exceptions |
| Missing logs/metrics | Uninstalled collector, IAM, or quota error | Collector, export endpoint, billing |
| ImagePullBackOff | Registry auth or networking | Image digest, pull secret, egress |
| Broken after upgrade | Version skew or CRD incompatibility | Support matrix and agent versions |
| Abnormal egress spike | Centralized telemetry or image transfers | Usage and billing export |

A structured diagnostic sequence:

1. Separate **management** errors from **application** errors.
2. Check project, location, membership, and owner.
3. Inspect networking, agents, DNS, and certificates.
4. Check IAM and RBAC independently.
5. Check GitOps/policy/observability integrations.
6. Review recent changes in both the native cloud and Google Cloud.
7. Invoke break-glass only when authorized by the runbook.
8. Document root cause and remediation clearly.

## 24. Lab: Attaching EKS Staging to a Fleet

Suppose the company has:

- An EKS cluster named **eks-orders-staging**.
- Fleet project **FLEET_PROJECT_ID**.
- A GitOps repo containing namespaces, RBAC, and an audit policy.
- A test Cloud Storage bucket with read-only IAM for one workload.
- Platform team and AWS owner approval for the exercise.

### Phase A: Assessment

Record Kubernetes distribution/version, region, AWS account, networking, IAM, storage, owner, mandatory policies, and attached-cluster version requirements.

### Phase B: Registration

1. Prepare IAM permissions in GCP and on the source cluster.
2. Verify outbound networking.
3. Follow the official registration guide for the distribution/version.
4. Verify the attached cluster resource and fleet membership.
5. Verify agents/connectivity and record resource IDs.

### Phase C: Read-only access

Using an appropriately authorized identity, fetch the context via Gateway where supported:

~~~bash
kubectl config get-contexts
kubectl --context="APPROVED_EKS_CONTEXT" get nodes
kubectl --context="APPROVED_EKS_CONTEXT" get namespaces
~~~

Then test reading Pods with a read-only identity while confirming Deployment deletion is denied.

### Phase D: Policies and GitOps

- Create namespace `fleet-lab` from Git.
- Apply read-only Role/RoleBinding.
- Apply an audit-only policy disallowing privileged Pods.
- Verify sync status and violation lists.
- Revert a commit and verify controller rollback.
- Do not enable cluster-wide enforcement during the lab.

### Phase E: Workload authentication

Configure WIF for a lab Pod following external identity guidance. Verify reading the granted object succeeds while accessing an out-of-scope object is denied.

### Phase F: Availability

Simulate interrupting the management path in an approved lab:

- Do applications keep serving?
- Does Gateway accurately report connection loss?
- Do audits/alerts trigger?
- Does the break-glass path to the native cluster work?
- After restoration, do the agent and sync recover?

### Phase G: Review

Save a report containing cluster/membership IDs, IAM/RBAC test results, feature availability, logs/metrics, reconnection time, incurred costs, and action items with owners.

## 25. Production Readiness Checklist

### Before onboarding

- [ ] Distribution/Kubernetes version and features verified as supported.
- [ ] Cluster owner, network owner, and platform owner confirm responsibilities.
- [ ] GCP project, billing, location, and IAM verified.
- [ ] Provider and Kubernetes permissions follow least privilege.
- [ ] DNS, egress, proxies, TLS, and policies configured securely.
- [ ] Rollback/detach procedure exists if registration fails.

### After onboarding

- [ ] Attached resource and fleet membership match intended project/location.
- [ ] Agent connectivity and health verified.
- [ ] Google IAM and Kubernetes RBAC tested separately.
- [ ] Gateway uses approved identities.
- [ ] GitOps source-of-truth, drift detection, and policy auditing operational.
- [ ] Logs/metrics/audits meet requirements without leaking secrets.
- [ ] Inventory owner/environment, runbooks, and upgrade plans updated.

### Ongoing operations

- [ ] Track version skew and agent/certificate lifecycles.
- [ ] Review IAM, RBAC, WIF, and break-glass permissions.
- [ ] Policy exemptions have owners and expiration dates.
- [ ] Track egress, telemetry, and control-plane costs.
- [ ] DR/backups tested against RTO/RPO.
- [ ] Verify GitOps recovery, rollouts, and rollbacks.
- [ ] Detach procedure documented for end-of-life decommissioning.

## 26. Detaching, Decommissioning, and Common Mistakes

When stopping GCP management of a cluster:

1. Confirm the cluster and workloads remain managed by the native system.
2. Audit dependencies on Gateway, GitOps, policies, and telemetry.
3. Migrate alerts/automation to alternative channels if needed.
4. Archive audit trails and resource inventory per retention requirements.
5. Remove connections/agents/memberships following the official sequence.
6. Revoke unused IAM and federated identities.
7. Verify workloads experience no unplanned impact.
8. Update inventory and billing ownership.

**Detaching does not delete the EKS/AKS/on-prem cluster.** Conversely, deleting the native cluster before cleaning up memberships can leave stale metadata behind.

Common mistakes:

| Anti-pattern | Consequence |
|---|---|
| Thinking attach means Google manages nodes and upgrades | Unclear accountability during incidents |
| Assuming all attached clusters have identical features | Configuration/rollout failures |
| Granting `cluster-admin` to every operator | Excessive blast radius and risk |
| Opening the API server publicly to ease registration | Expanded attack surface |
| Embedding Google service account keys in Pods | Credential exposure risk |
| Enforcing policies across the entire fleet at once | Blocks valid deployments |
| Checking only that membership is Connected | Misses application SLO failures |
| Lacking a native admin access path | Helpless when Gateway fails |
| Mixing manifests across all providers | CNI/CSI/Ingress/identity failures |
| Shipping all logs cross-cloud without controls | Inflated cost and data exposure risk |
| Treating fleet as DR | Data is neither backed up nor replicated |
| Skipping cleanup during decommissioning | Lingering permissions and inaccurate inventory |

**Conclusion:** GKE attached clusters extend Google Cloud's Kubernetes management capabilities to clusters outside GCP, giving organizations unified inventory, authorization, and shared policy/observability tooling. Success relies on respecting native cloud provider ownership, verifying support matrices, separating IAM/RBAC/workload identity, controlling networking, syncing safely via GitOps, and maintaining operational resilience when management connectivity fails. It establishes consistent multicloud governance without surrendering accountability for each individual cluster.
