# Azure Arc-Enabled Kubernetes and Hybrid Cluster Governance

## 1. Why Govern Kubernetes Under a Hybrid Model?

An enterprise might run **Azure Kubernetes Service (AKS)** for public applications, on-premises Kubernetes in a data center for core systems, and edge clusters in factories or retail stores near local equipment. These clusters run in different locations yet share common needs: access control, configuration governance, policy enforcement, observability, and traceable application releases.

When each team operates clusters independently, enterprises quickly run into issues:

- No reliable inventory: which clusters are production, who owns them, and which Kubernetes versions are running?
- YAML edited live with `kubectl` without version history, causing **configuration drift**.
- Clusters diverge on image registries, resource requests/limits, namespaces, and network policies.
- Scattered logs and telemetry make it hard to pinpoint whether an issue stems from the app, node, network, or an Azure dependency.
- Overprivileged Kubernetes accounts; a cluster failure or network drop disrupts governance workflows.

**Azure Arc-enabled Kubernetes** brings Kubernetes clusters **running outside Azure or on supported infrastructure** into Azure's governance plane by registering them as Azure resources. Organizations can then apply supported capabilities such as Azure Resource Manager inventory, Azure Policy for Kubernetes, GitOps with Flux, monitoring, and Azure service integrations.

Most importantly: **connecting a cluster to Azure Arc does not migrate the cluster to Azure, turn it into AKS, or hand control-plane operations to Azure**. Control planes, worker nodes, storage, networking, and most Kubernetes lifecycle tasks remain the responsibility of the source platform and operations team.

Across the Azure journey—from subscriptions, resource groups, and Microsoft Entra ID to networking, compute, storage, monitoring, security, and cost control—Arc connects environments outside Azure into a **unified governance model**.

### Lesson Objectives

You will be able to:

1. Explain Azure Arc-enabled Kubernetes and distinguish it from AKS, AKS enabled by Azure Arc, and self-managed Kubernetes.
2. Prepare a cluster, Azure/Kubernetes permissions, and secure outbound connectivity; connect a cluster using Azure CLI.
3. Use Azure Resource Manager to organize inventory, tags, resource groups, and access across multiple clusters.
4. Design GitOps with Flux and guardrails against direct changes that cause drift.
5. Choose appropriate Azure Policy, monitoring, security, RBAC, and access mechanisms for hybrid clusters.
6. Assess limitations when Azure connectivity drops, troubleshoot agents/extensions, and write an operations runbook.
7. Run a verifiable small lab without treating Connected status as proof of application health.

## 2. Distinguishing Azure-Related Kubernetes Models

| Model | Where Do Control Plane & Nodes Run? | What Does Azure Manage? | Primary Ops Team Responsibility |
| --- | --- | --- | --- |
| **AKS** | AKS service on Azure infrastructure | Azure delivers managed Kubernetes with its own lifecycle tooling | Workloads, allowed cluster settings, security, networking, storage, SLOs |
| **Azure Arc-enabled Kubernetes** | Existing cluster on-prem, edge, other cloud, or supported environment | Projected Azure resource plus enabled extensions and management features | Continues operating the underlying Kubernetes platform and dependencies |
| **AKS enabled by Azure Arc** | Product-supported hybrid/on-prem platforms | Solution for deploying/managing AKS per specific product capabilities | Infrastructure and config governance matching the deployment model |
| **Unconnected self-managed Kubernetes** | Any suitable Kubernetes infrastructure | No Arc resource or central Azure governance | Self-organized inventory, policy, GitOps, monitoring, and operations |

**Do not equate** Azure Arc-enabled Kubernetes with a cluster provisioning tool. If a cluster already has a Kubernetes API, CNI, CSI, HA control plane, and backups, enabling Arc mainly adds **connectivity to the Azure management plane**. It does not provision nodes, fix networking, upgrade Kubernetes, or configure DR.

### 2.1 Capabilities That Can Be Combined

| Need | Related Azure Capability | Conditions / Aspects to Verify |
| --- | --- | --- |
| Subscription-wide inventory | Azure Resource Manager, resource groups, tags, Resource Graph | Active registered resource, reliable tags, and right Azure RBAC |
| Pushing app configs to clusters | GitOps/Flux via Arc extensions and configurations | Git repository, Flux source auth, RBAC, and extension prerequisites |
| Consistent policy | Azure Policy for Kubernetes within supported scope | Policy extension, effect types, in-cluster enforcement, and sync lag |
| Observability | Azure Monitor, Container Insights, or supported monitoring options | Telemetry agents/extensions, connectivity, Log Analytics workspace, ingest cost |
| Security | Microsoft Defender for Cloud / Defender for Containers per support | Plans, extensions/agents, scope, data, and security policies |
| Admin access | Kubernetes RBAC, Arc access / Cluster Connect where supported | User identity, Azure **and** Kubernetes permissions, auditing, connectivity |
| Azure services running hybrid | Arc extensions/capabilities depending on platform | Never assume every Azure service runs on every cluster |

Actual extension lists and features **vary by Kubernetes version, distribution, CPU architecture, region, licensing, and product terms**. Never treat the table above as a guarantee that every feature runs on every cluster.

## 3. Architecture of Azure Arc-Enabled Kubernetes

Suppose an organization runs two clusters:

- `k8s-dc1-prod`: data-center Kubernetes cluster running Orders API calling an on-premises SQL Server.
- `k8s-edge-01`: warehouse edge cluster processing equipment events and syncing data back to headquarters.

~~~mermaid
flowchart TB
    subgraph Azure["Azure management plane"]
        ARM["Azure Resource Manager\nconnectedClusters"]
        POLICY["Azure Policy / governance"]
        GITOPS["Flux configuration / extensions"]
        OBS["Azure Monitor / security"]
    end
    subgraph DC["On-premises data center"]
        K1["Kubernetes: k8s-dc1-prod"]
        A1["Azure Arc agents"]
        APP["Orders API + internal SQL"]
        K1 --- A1
        K1 --- APP
    end
    subgraph EDGE["Edge site"]
        K2["Kubernetes: k8s-edge-01"]
        A2["Azure Arc agents"]
        EDGEAPP["Local worker"]
        K2 --- A2
        K2 --- EDGEAPP
    end
    A1 -->|"Outbound TLS / Azure endpoints"| ARM
    A2 -->|"Outbound TLS / Azure endpoints"| ARM
    ARM --> POLICY
    ARM --> GITOPS
    ARM --> OBS
~~~

This diagram shows management relationships—**not every extension shares the exact same network flow or proxy**. Observability and GitOps components may require separate connectivity to Azure Monitor or Git repositories.

### 3.1 What Gets Created Upon Connection

When enabling Arc on a supported cluster, onboarding typically:

1. Deploys a set of **Arc agents** into Kubernetes, commonly inside the `azure-arc` namespace.
2. Establishes identity/connectivity between agents and the Azure Arc service.
3. Creates an Azure resource of type **`Microsoft.Kubernetes/connectedClusters`** in the chosen subscription/resource group.
4. Surfaces connection metadata/status in Azure and enables supported management operations via extensions/configurations.

A **connected cluster resource** is a control/governance representation; actual namespaces, Pods, PVCs, and the Kubernetes API server remain where the cluster runs. Creating an Arc resource **does not duplicate workloads** inside Azure.

### 3.2 What Happens When Connectivity to Azure Drops?

Distinguish two failure modes:

- **Azure management link drops while source cluster keeps running:** Kubernetes workloads usually continue serving if local dependencies remain available. Azure inventory/health goes stale, and Azure-pushed config/policy/extension updates delay or fail. Agents typically retry once connectivity returns.
- **Cluster, API server, or source infrastructure fails:** Azure Arc **does not auto-recover control planes, nodes, storage, or power**. Resilience depends on your Kubernetes design and local DR plan.

GitOps Flux may continue reconciling from Git **if Flux stays up and can reach the Git repo**; never assume this holds for all network outages. If Git sits off-site and Internet drops, reconciliation may serve cached state or fail to pull new commits depending on controller behavior. Define explicit offline behavior rather than assuming “Azure always manages everything.”

## 4. Preparing to Connect a Hybrid Cluster

### 4.1 Technical Prerequisites

Before taking action:

- Cluster runs a **Kubernetes distribution/version/CPU architecture supported by Azure Arc** with a working API server and valid admin credentials. Check current support docs first.
- `kubectl` points to the **exact intended context** with privileges to install agents/CRDs/roles in-cluster. Onboarding typically requires high privileges, so use approved cluster-admin credentials strictly for registration where required.
- Operator machine has compatible **Azure CLI, kubectl, Helm**, or components required by the current installation path.
- Azure subscription, resource group, and supported metadata region are ready; the Azure user or service principal has permissions to create connected clusters and related configs.
- Resource providers **`Microsoft.Kubernetes`** and **`Microsoft.KubernetesConfiguration`** are registered where required by features in use. Provider registration is a subscription-level admin action.
- Cluster/agents have **outbound HTTPS/TLS** to required Azure endpoints; DNS, proxies/firewalls, trust stores, time sync, and container image pulls meet prerequisites. Follow official hostname/port lists per region and extension rather than opening unrestricted egress.
- Named owners exist for **RBAC, networking, GitOps, observability, and billing**; never onboard production clusters without a rollback plan and change window.

### 4.2 Inspect Kubernetes Context Before Connecting

~~~bash
# The commands below ONLY READ state from kubeconfig and the API server.
kubectl config current-context
kubectl cluster-info
kubectl get nodes -o wide
kubectl get namespaces

# Verify existing permissions; does not grant new ones.
kubectl auth can-i create namespaces
kubectl auth can-i create clusterrolebindings
~~~

When kubeconfig holds multiple clusters, verify the live context and API endpoint. **Wrong context is one of the highest risks**: `connectedk8s connect` could register the wrong cluster, installing agents on production instead of lab. Record cluster UID/context, region, resource group, and owner in the runbook before saying GO.

### 4.3 Check Subscription and Resource Providers

~~~bash
# Sign in using your organization's approved method before running.
az account show \
  --query "{subscription:id,name:name,tenant:tenantId}" \
  --output table

az provider show --namespace Microsoft.Kubernetes \
  --query "{namespace:namespace,state:registrationState}" -o table
az provider show --namespace Microsoft.KubernetesConfiguration \
  --query "{namespace:namespace,state:registrationState}" -o table
~~~

With approval to register providers, an administrator can run:

~~~bash
# THESE COMMANDS MODIFY SUBSCRIPTION RESOURCE PROVIDER REGISTRATIONS.
az provider register --namespace Microsoft.Kubernetes
az provider register --namespace Microsoft.KubernetesConfiguration
~~~

Never grant subscription-wide Owner just to test one cluster. Scope Azure roles to the resource group where possible, confirm provider registration prerequisites, and keep Azure credentials separate from Kubernetes credentials.

## 5. Onboarding a Cluster to Azure Arc via Azure CLI

### 5.1 Install Matching CLI Extensions

Lab example below. Commands like `connectedk8s`, `k8s-extension`, or `k8s-configuration` come from Azure CLI extensions; verify support and exact syntax for your CLI version:

~~~bash
az extension add --name connectedk8s
az extension add --name k8s-extension
az extension add --name k8s-configuration

# List installed extensions; admin machines may already have them.
az extension list \
  --query "[].{name:name,version:version}" \
  --output table
~~~

`az extension add` modifies only your **local CLI environment**, not the cluster. In automation, pin tested Azure CLI/extension versions rather than letting pipelines silently auto-upgrade mid-release.

### 5.2 Create a Management Resource Group if Needed

~~~bash
# Example: run ONLY when authorized to create a lab resource group.
az group create \
  --name rg-arc-hybrid-lab \
  --location southeastasia
~~~

This performs a **real Azure resource group creation**, unlike read-only checks. Location sets where the **management resource and metadata** reside; it **does not move pods or nodes** to `southeastasia`.

### 5.3 Connect an Approved Cluster

~~~bash
# This command modifies BOTH the source cluster (installs Arc agents) AND Azure (creates resource).
# Before running, verify both kubectl context and subscription.
az account set --subscription "<subscription-id>"
kubectl config current-context

az connectedk8s connect \
  --name arc-dc1-lab \
  --resource-group rg-arc-hybrid-lab \
  --location southeastasia
~~~

In a lab, use an authorized, supported test cluster. `arc-dc1-lab` is the **Azure resource name** and need not match the Kubernetes context name. Across multiple clusters, adopt names encoding site/location, environment, and owner without exposing sensitive data.

### 5.4 Verify Both Sides After Connecting

~~~bash
# Azure side: READ-ONLY inspection of Arc resource and connection details.
az connectedk8s show \
  --name arc-dc1-lab \
  --resource-group rg-arc-hybrid-lab \
  --output json

az resource list \
  --resource-group rg-arc-hybrid-lab \
  --resource-type "Microsoft.Kubernetes/connectedClusters" \
  --output table

# Kubernetes side: READ-ONLY inspection of Arc agent pods and workloads.
kubectl get pods -n azure-arc
kubectl get deployments -n azure-arc
~~~

Check the namespace if your distribution/onboarding path uses another name or agents are still starting. Agents may restart during initial registration; inspect events, image pulls, and network errors rather than glancing once at `kubectl get pods`.

**Connection passing criteria** require both the Azure resource and in-cluster agents to report healthy. Yet Arc Connected **is not proof** that application deployments, storage, or ingress in the cluster are healthy.

## 6. Inventory Governance with Azure Resource Manager

Once a cluster appears as `Microsoft.Kubernetes/connectedClusters`, use **resource groups, tags, Azure RBAC, resource-scoped policies, and inventory queries** to view hybrid clusters in one Azure governance model.

### 6.1 Designing Resource Groups and Tags

Example tagging taxonomy:

| Tag | Examples | Purpose |
| --- | --- | --- |
| `environment` | `prod`, `staging`, `lab` | Distinguish blast radius of changes |
| `site` | `dc1`, `edge-hn01` | Identify physical/logical site |
| `owner` | `platform-team` | Alert recipient and change approver |
| `businessUnit` | `commerce` | Accountability and budgeting |
| `dataClassification` | `internal` | Guide security policy enforcement |
| `recoveryTier` | `tier1` | Prioritize DR, SLOs, and support |

Azure tags on Arc resources **do not automatically propagate as Kubernetes labels/annotations** inside workloads. If namespaces, deployments, or cluster-targeted policies need labels, configure separate sync or GitOps.

### 6.2 Separating Azure Permissions and Kubernetes Permissions

Always separate two authorization planes:

- **Azure RBAC:** controls who can view/edit connected cluster resources, extensions, configurations, and related Azure objects.
- **Kubernetes RBAC:** controls who can `get`, `list`, `update`, or `delete` pods, deployments, secrets, and cluster resources via the Kubernetes API.

An Azure **Reader** on an Arc resource does not automatically gain `cluster-admin` in Kubernetes. Conversely, holding an admin kubeconfig **does not automatically** grant rights to edit Azure Policies or resource groups.

Capabilities like **Azure RBAC for Kubernetes authorization** or **Cluster Connect** may be enabled on supported Arc clusters to integrate identity/authorization. Configure and verify least-privilege RBAC, audit logging, and network prerequisites explicitly—**never assume** they are active simply from Arc registration.

### 6.3 Multi-Cluster Management Catalog

Organizations can separate lab and production clusters across resource groups/subscriptions to isolate policies, RBAC, blast radius, and cost reporting. Avoid placing every cluster under a single global admin without separation of duties.

Sample team-maintained inventory table:

| Arc Resource | Actual Runtime Location | Owner | Service Objective | Signals to Monitor |
| --- | --- | --- | --- | --- |
| `arc-dc1-prod` | DC1 on-premises | Platform | Orders API production | Arc connectivity + workload health |
| `arc-edge-hn01` | Edge HN01 | Edge Ops | Sync events | Offline duration + queue backlog |
| `arc-lab01` | Lab | Enablement | Test GitOps/policies | Zero production impact |

Never rely on the connectivity column as your sole availability metric. `Offline` may reflect a lost management link while Pods continue serving, or conversely Connected agents may mask Pods stuck in CrashLoopBackOff.

## 7. GitOps with Flux: Configuring Clusters from Git

### 7.1 GitOps Solves Configuration Drift

With manual operations, someone may run `kubectl edit deployment` in production. That edit lives outside Git, gets overwritten on the next deploy, or makes clusters diverge.

**GitOps** stores desired state in Git; a controller like **Flux** continuously compares cluster state against approved manifests and reconciles differences within its scope. Azure Arc integrates GitOps/Flux through supported extensions and cluster configurations.

~~~mermaid
flowchart LR
    PR["Pull request + review + CI"] --> REPO["Protected Git repo"]
    REPO --> FLUX["Flux controllers on hybrid cluster"]
    FLUX --> NS["Namespaces / Deployments / Services"]
    NS --> HEALTH["Health + telemetry"]
    HEALTH -->|Error -> PR rollback| REPO
    AZ["Azure Arc extension / configuration"] --> FLUX
~~~

This illustrates the config control loop. Real pipelines may add OCI registries, Helm chart repositories, private repo credentials, secret managers, or image automation. Establish one clear **source of truth**: never manage a resource with Flux while routinely patching it manually.

### 7.2 Repository Structure for Multiple Clusters

Illustrative layout:

~~~text
platform-gitops/
  base/
    namespaces/
    observability/
    network-policies/
  clusters/
    dc1-prod/
      kustomization.yaml
      apps/
      policies/
    edge-hn01/
      kustomization.yaml
      apps/
      policies/
    lab01/
      kustomization.yaml
      apps/
~~~

Place reusable common manifests in **base**; keep approved per-environment/cluster overrides in cluster folders. For `prod`, enforce branch protection, required reviewers, schema/policy checks, container scanning, and secret scanning. Keep plaintext secrets out of Git using supported encryption or secret management tools.

### 7.3 Enabling the Flux Extension via Azure CLI

The example below **makes real changes**: deploying the Flux extension onto a connected cluster. Run only after scope/roles are approved and Kubernetes version, egress, and extension compatibility are verified.

~~~bash
# Install the Flux extension on a lab Arc-enabled cluster.
az k8s-extension create \
  --name flux \
  --cluster-type connectedClusters \
  --cluster-name arc-dc1-lab \
  --resource-group rg-arc-hybrid-lab \
  --extension-type microsoft.flux

# Read-only listing of registered extensions.
az k8s-extension list \
  --cluster-type connectedClusters \
  --cluster-name arc-dc1-lab \
  --resource-group rg-arc-hybrid-lab \
  --output table
~~~

Extension names, flags, and supportability depend on your Azure CLI/extension versions at execution time. Never paste commands verbatim into production before checking current docs, versions, and permissions.

### 7.4 Creating a Flux Configuration Linked to a Git Repo

An **illustrative example** for a public lab repo (substitute a verified repo URL/path; never pass secrets on the command line):

~~~bash
# This command CREATES a GitOps config and can cause Flux to apply manifests to the cluster.
az k8s-configuration flux create \
  --resource-group rg-arc-hybrid-lab \
  --cluster-name arc-dc1-lab \
  --cluster-type connectedClusters \
  --name platform-lab \
  --namespace flux-system \
  --scope cluster \
  --url https://github.com/example-org/platform-gitops \
  --branch main \
  --kustomization name=platform path=./clusters/lab01 prune=true

# READ-ONLY listing of registered GitOps configs.
az k8s-configuration flux list \
  --resource-group rg-arc-hybrid-lab \
  --cluster-name arc-dc1-lab \
  --cluster-type connectedClusters \
  --output table
~~~

`example-org/platform-gitops` is a **placeholder**, not a live verified repo or runnable command. For private repos, configure supported authentication (SSH keys, token/identity, or product-supported mechanisms), least privilege, rotation, and never leave credentials in shell history or Git.

**`prune=true` deletes Flux-managed resources if their manifests disappear from Git.** In production, strictly bound Flux's resource scope, require approval for destructive changes, protect critical namespaces, and prepare recovery steps. Never enable `prune` blindly just because an example uses it.

### 7.5 Reconciliation States to Watch

A GitOps rollout succeeds when:

1. The Git revision matches the approved commit and source fetch succeeds.
2. Flux `GitRepository`/`Kustomization` or `HelmRelease` (if used) reports Ready.
3. Kubernetes Deployment rollout completes, replicas are ready, and Services/Ingress serve traffic.
4. App SLIs (success rate/latency) meet targets with no new dependency errors.
5. A rollback path via Git revert or tested recovery exists—not merely “apply succeeded.”

~~~bash
# The commands below are READ-ONLY checks inside the cluster.
kubectl get pods -n flux-system
kubectl get gitrepositories,kustomizations -A
kubectl get deployments -A

# Example check for an app after Flux syncs configuration.
kubectl rollout status deployment/orders-api -n orders --timeout=180s
~~~

The `orders` namespace, CRDs, and `orders-api` Deployment exist only once the controller and workload are deployed. If `kubectl get gitrepositories` reports an unknown resource type, inspect the Flux extension/CRDs rather than blaming the Git repository.

## 8. Consistent Governance with Azure Policy

Azure Policy lets teams define rules and track compliance across Azure resources. For **Azure Arc-enabled Kubernetes**, **Azure Policy for Kubernetes** pairs with an in-cluster policy extension/enforcement engine to audit or enforce rules on clusters.

Common governance goals:

- Allow container images only from approved registries per supported policies.
- Require owner or environment labels on namespaces/workloads.
- Audit or deny privileged Pods or risky configs where supported by policy rules.
- Enforce CPU/memory resource requests/limits or restrict host namespaces/hostPath mounts per policy.
- Audit compliance from a subscription/resource-group view to curb configuration drift across sites.

**Keep two layers distinct:**

- Azure Policy is **assigned** at management group/subscription/resource group/resource scope where supported.
- Kubernetes admission/policy is **enforced inside the cluster** by in-cluster components. Assigning a policy in Azure does not instantaneously enforce admission control on an offline cluster or one lacking the policy extension.

### 8.1 Safe Policy Rollout Workflow

1. Align policy rules with platform, app, and security teams; assess impact on existing workloads.
2. Verify the policy definition/effect and extension are **supported on your actual Kubernetes distribution/version**.
3. Start in **Audit** or dry-run mode where supported; measure violating resources, owners, and needed exemptions.
4. Fix manifests in GitOps first and re-measure compliance; only then consider **Deny**/enforcement when it will not cause an outage.
5. Scope exemptions tightly with rationale, approvers, and expiration dates; never drop controls across an entire subscription for one app.
6. Account for disconnected clusters: Azure compliance dashboards can go stale, so retain in-cluster checks and offline reporting.

For example, you may want every production Pod to set `resources.requests.cpu` and `resources.requests.memory`. Never assume Azure Policy ships that exact built-in template/effect on every release; verify built-in or custom policy support in a lab first.

### 8.2 GitOps and Policy Complement—Not Replace—Each Other

GitOps declares **what state the cluster should converge to**; policy defines **what states are allowed or flagged**. When a PR introduces a privileged container:

- CI / policy-as-code can catch it before merge.
- Azure/Kubernetes policy in-cluster can audit or block admission per config.
- Flux reports reconciliation failure if admission rejects an object; operators must read both Flux errors and policy violations.

Without coordinated rollout, flipping a policy straight to Deny can stall deployments. Release governance requires both Git PR review and staged policy enforcement.

## 9. Observing Hybrid Clusters with Azure Monitor and Local Tooling

### 9.1 Monitor Two Layers of Health

| Layer | Signals | Why It Matters |
| --- | --- | --- |
| **Arc management connectivity** | Connected/Disconnected, agent health, extension provisioning | Shows whether Azure can receive telemetry and push governance configs |
| **Kubernetes control plane** | API reachability, etcd health (if accessible), scheduler/controller | Assesses site-level cluster health |
| **Nodes** | Ready/NotReady, CPU/memory/disk pressure, kubelet | Spots node failures and capacity exhaustion |
| **Workloads** | Pods Ready, restarts, OOMKilled, Pending, CrashLoopBackOff | Evaluates deployments and runtimes |
| **Application SLIs** | Request success rate, latency, queue lag, data accuracy | Measures real user impact |
| **GitOps/policy** | Reconcile Ready, drift, admission denials, compliance | Confirms desired configs apply properly |
| **Hybrid connectivity** | DNS, TLS, proxy, Azure/Git endpoint latency, egress errors | Separates app bugs from management-link failures |

Seeing Connected or green `kubectl get nodes` **does not prove** ordering journeys succeed. Pair infrastructure metrics with synthetic probes and distributed tracing along critical paths, including databases and partner APIs.

### 9.2 Azure Monitor / Container Insights

Azure Monitor integrates with Arc-enabled Kubernetes **according to current support for that cluster type**, typically via a supported extension/agent feeding a Log Analytics workspace or compatible telemetry target.

Before enabling:

- Verify cluster type, OS/node architecture, extension support, and supported regions.
- Pick workspace, retention, and data collection rules/filters if supported.
- Estimate **data ingestion, retention, query, and egress costs** beforehand; never enable verbose logs across all namespaces unbounded.
- Verify DNS, outbound access, proxies/CAs, and identities; extensions may deploy DaemonSets/Pods consuming source cluster resources.
- Monitor the telemetry pipeline; missing logs in Azure may signal a broken telemetry link—**never assume Kubernetes is error-free**.

In Log Analytics, tables like `KubePodInventory` or `ContainerLogV2` depend on collection mode and schema version. Always inspect available tables and columns in your live workspace rather than blindly reusing old KQL queries.

**Illustrative query example** (use only when your workspace collects `KubePodInventory` with matching fields):

~~~kusto
KubePodInventory
| where TimeGenerated >= ago(30m)
| where Namespace == "orders"
| summarize LastSeen = max(TimeGenerated),
            Observations = count()
  by ClusterName, Name, PodStatus
| order by LastSeen desc
~~~

This query **does not by itself prove** Orders SLIs. Calculating SLOs requires ingress/app telemetry defining good/bad requests, sample sizes, and evaluation windows. A PodStatus row existing also does not prove an endpoint is actually serving live traffic.

### 9.3 Local Monitoring When WAN Connectivity Drops

For production clusters in factories or edge sites, maintain an observation path **independent of Azure connectivity**: local log buffers, local dashboards, alerts to on-site staff, or store-and-forward aggregation.

Aim to detect when:

- Azure Arc agents stop reporting while Pods keep serving locally.
- Off-site Git repos become unreachable so new config commits are pending.
- WAN loss prevents upstream data sync, growing local backlogs even while local HTTP `/healthz` probes still return 200.

Specify distinct SLOs for **on-site serving** vs. **central synchronization**; never let a single Connected status claim both are healthy.

## 10. Security, Identity, and Multi-Tenant Governance

### 10.1 Layering Permissions and Identities

| Layer | Permissions / Identity | Risk if Misconfigured |
| --- | --- | --- |
| Azure subscription / resource group | Azure RBAC for Arc resources, extensions/configs | Unauthorized users control GitOps or alter site-wide policies |
| Kubernetes API | Kubernetes RBAC, service accounts, auditing | One kubeconfig compromises the entire cluster |
| GitOps controller | Flux service accounts and Git credentials | Compromised controller or repo mutates multiple namespaces |
| Registries, secrets, cloud APIs | Workload tokens/secrets/identities | Key leaks, bad image pulls, or unauthorized data access |
| Network | Firewalls, proxies, TLS, DNS, private connectivity | Loss of management link or overly permissive egress |

Never grant Flux `cluster-admin` to manage a single app namespace when namespace-scoped permissions suffice. Likewise, pipeline service principals need access only to approved resource groups/clusters and actions; never share one credential between production and lab.

### 10.2 Secrets Management

- **Never commit plaintext secrets to Git** or print tokens into terminal output or CI logs.
- With GitOps, pick a supported secret management pattern (e.g., Secrets Store/External Secrets, GitOps encryption, or Azure Key Vault integration) and check workload identity support on the **source platform**.
- Never assume Pods on an Arc cluster receive Azure Managed Identity automatically like AKS; configure supported identity federation or secret retrieval per your real architecture.
- Maintain credential rotation/revocation, access logging, and an offline fallback if an off-site secret store becomes unreachable.
- Configure Kubernetes NetworkPolicies, admission controls, image verification, and runtime hardening per your CNI/cluster; Azure Arc does not enable these automatically.

### 10.3 Cluster Connect and Remote Access

Some Arc clusters support **Cluster Connect** to reach the Kubernetes API through an Azure-managed channel, subject to feature, agent, user, and RBAC prerequisites. When using it:

1. Enable only if needed and supported.
2. Enforce both Azure and Kubernetes RBAC per the authorization model.
3. Enable auditing/monitoring, restrict admin sessions, and review session lifecycles.
4. Check network prerequisites and test in a lab before production.

**Never treat Cluster Connect as a site-to-site VPN**, and never assume enabling it grants Kubernetes `cluster-admin` automatically. An admin control channel does not replace application paths to site databases, registries, or DNS.

### 10.4 Multi-Cluster Governance

Establish onboarding standards:

- Every cluster needs an owner, environment, contact, data classification, and review/expiration date.
- Production clusters require change approval for adding extensions, changing GitOps repos/paths, or modifying Azure RBAC.
- Roll out in rings: lab → staging → canary site → remaining sites.
- Never upgrade Flux/controllers/agents across all sites simultaneously before canary results stabilize.
- Reconcile inventory regularly; when a cluster is retired at source, clean up stale Arc resources under change approval.

## 11. Day-2 Operations: Upgrades, Drift, and Incidents

### 11.1 Who Upgrades Kubernetes?

Azure Arc-enabled Kubernetes **does not automatically manage control-plane or node OS upgrades on on-premises clusters**. Operations must follow the Kubernetes distribution vendor's upgrade procedure, protecting etcd quorum, backups, PodDisruptionBudgets, spare capacity, and compatibility testing.

Layers upgrade on independent cadences:

1. **Kubernetes distribution, control plane, and worker nodes:** per source platform.
2. **CNI, CSI, ingress, storage, and monitoring stacks:** per respective vendors/components.
3. **Azure Arc agents/extensions/Flux:** per Azure-supported release cadences and mechanisms.
4. **Workloads:** deployed via CI/CD/GitOps with health gates.

Upgrading one layer does not prove others remain compatible. Maintain a version matrix and test on a matching lab cluster first.

### 11.2 Managing Drift

Distinguish three types of drift:

- **GitOps drift:** live manifests diverge from the approved Git commit.
- **Platform drift:** Kubernetes versions, CNIs, admission controllers, storage classes, or runtime configs diverge across sites; Flux only sees resources inside its scope.
- **Azure management drift:** Arc resources, extensions, policy assignments, or tags diverge from baseline IaC.

Remediation workflow: detect, classify blast radius, confirm source of truth, submit PR/IaC fix, and verify post-reconciliation. Avoid long-term manual `kubectl edit` fixes on Flux-managed resources—Flux will overwrite them or conflict.

### 11.3 Runbook When Arc Status Shows Disconnected

1. **Confirm Kubernetes is still serving:** run `kubectl get nodes`, inspect pods/ingress, and verify local synthetic checks.
2. **Verify exact Azure scope:** subscription, resource group, connected cluster resource, and status timestamp.
3. **Check agent health:** inspect `azure-arc` namespace, pod events, image pulls, restarts, and relevant logs (handle credentials/logs carefully).
4. **Check connectivity:** DNS, HTTPS egress, proxies, CA certificates, clock/time sync, endpoint allowlists, and Git/extension endpoints where applicable.
5. **Classify impact:** management plane only, GitOps sync, policy compliance, telemetry ingestion, or live application traffic?
6. **Recover per runbook:** repair network/permissions/agents safely; avoid hastily deleting the Arc resource or reinstalling everything.
7. **Reconcile post-recovery:** verify Connected status, extension/GitOps Ready, policy state, fresh telemetry, and workload SLIs; log timeline and lessons learned.

If the cluster lost total WAN access, recovery depends on network/infra teams. Never treat “Disconnected” as a trigger to restart all application Pods—turning a management outage into an application outage.

## 12. Common Troubleshooting

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| `az connectedk8s connect` targets wrong cluster/context | Wrong kubeconfig context or unreachable API | Verify context, API endpoint, cluster identity, and local permissions |
| Arc agents not Ready | Image pull failure, low resources, PodSecurity/admission, DNS/proxy, RBAC | Inspect events/pods in the agent namespace, node capacity, and prerequisites |
| Arc resource exists but Disconnected | Blocked outbound Azure endpoints, TLS/CA, proxy, clock skew, or crashed agent | Inspect egress and agent health; compare Azure status timestamp |
| Extension creation fails | Unregistered provider, insufficient role, unsupported version/region/cluster | Check providers, Azure RBAC, compatibility, and extension provisioning errors |
| Flux fails to pull repo | Wrong Git URL/branch/path, expired credentials, DNS/firewall | Check Flux source status, verify repo and connectivity from inside cluster |
| Flux Ready yet app unhealthy | Valid manifests but broken app config, DB, image, or readiness probe | Check rollout, events, logs, dependencies, and SLIs |
| Unexpected policy violations | New policy scope/effect, non-baseline manifests, admission changes | Inspect assignment, constraints, exemptions, and PR history |
| Logs missing in Azure | DCR/agent/extension/egress or retention/cost cap | Cross-check local logs, ingestion metrics, and collection scope |
| Azure RBAC granted yet `kubectl` Forbidden | Azure and Kubernetes/Cluster Connect auth misconfigured | Verify enabled auth mechanism, Kubernetes RBAC bindings, and tokens |
| Cluster keeps running while Arc Disconnected | Management path down while data plane operates independently | Separate local serving health from Azure governance connectivity |

### 12.1 Caution When Disconnecting

Deleting a connected cluster resource in Azure or uninstalling Arc agents breaks governance integrations and impacts extensions/configurations. However, **it is not a way to “delete the underlying Kubernetes cluster.”** Proper decommissioning separates:

- Removing/updating Flux configs while preserving workloads/data per policy.
- Auditing extensions/agents, secrets, permissions, networking, and ongoing costs.
- Unregistering the Arc resource per approved runbook.
- Decommissioning **actual physical/virtual cluster infrastructure** via separate infra workflows if retiring the site.

Never test delete commands in production to see what happens. With GitOps `prune`, removing configs or repos requires special review because it can delete live Kubernetes resources.

## 13. Safe Application Deployment Architecture on Hybrid Clusters

Suppose Orders API runs on both `k8s-dc1-prod` and `k8s-edge-01`. A controlled rollout strategy:

1. CI builds the image once, scans dependencies/secrets/images, and signs/attaches provenance metadata where supported.
2. Push to an approved registry and record the **immutable digest**; confirm source clusters can pull images with proper credentials.
3. Open a PR updating GitOps manifests for the **lab cluster**; run schema/policy checks and peer review.
4. Once lab passes, promote the exact same image digest to a canary site; measure SLIs and runtime errors.
5. After meeting criteria and bake time, promote wave by wave across approved sites or namespaces.
6. On failure, revert the Git commit/rollout per runbook; verify data and external dependency compatibility.

~~~mermaid
flowchart TD
    CI["Build + scan + sign image"] --> REG["Registry with immutable digest"]
    REG --> PR["PR updates GitOps manifest"]
    PR --> LAB["Flux -> lab cluster"]
    LAB --> G{"Smoke/SLIs pass?"}
    G -->|No| STOP["Revert + analyze"]
    G -->|Yes| CAN["Flux -> canary site"]
    CAN --> H{"SLIs/ops/cost pass?"}
    H -->|No| STOP
    H -->|Yes| WAVE["Promote hybrid waves"]
~~~

### 13.1 Illustrative Deployment Manifest

This file demonstrates basic guardrails. **The image digest is a placeholder**; replace it with a real CI-generated digest. The manifest does not by itself provide TLS, authentication, NetworkPolicies, or database connectivity.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders
  labels:
    app: orders-api
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: orders-api
          image: ghcr.io/example-org/orders-api@sha256:REPLACE_WITH_VALID_DIGEST
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /readyz
              port: 8080
            periodSeconds: 10
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 512Mi
~~~

This config is a **structural guide only**. The `orders` namespace must exist, the registry must be reachable, probes must reflect real readiness, and workloads need secure secrets/configs. Setting `maxUnavailable: 0` requires spare capacity for a surge Pod; on resource-constrained edge sites, tight capacity can leave rollouts stuck Pending. Requests/limits are examples—size CPU/RAM from actual workload measurements.

### 13.2 Hybrid Does Not Guarantee Dependencies Are Local

An edge API may call Azure SQL, Service Bus, Entra ID, Key Vault, or SaaS partners. Evaluate:

- DNS resolution, egress allowlists, certificates, proxies, and latency to Azure services.
- Offline app behavior during WAN drops: local queues/caches, idempotency, replay, and bounded offline dataset limits.
- Reconciliation consistency between site and HQ upon reconnect to prevent duplicates or out-of-order messages.
- Per-scenario RTO/RPO: node failure, site outage, WAN outage, Azure database outage.
- Private connectivity or custom network architecture if needed; Arc onboarding does not automatically create VPN/ExpressRoute.

An Arc-connected cluster whose app cannot reach SQL over the network is still a **data/application outage**—adding tags to the Arc resource will never fix it.

## 14. Costs and Responsibility Boundaries

Connecting clusters to Azure Arc and enabling add-on services may carry **distinct billing models**. Never assume “using Arc means every management service is free,” and never price local physical nodes as if they were Azure VMs.

Cost items to include in a business case:

| Line Item | Who Pays / Scope | How to Control |
| --- | --- | --- |
| On-prem/edge cluster | Hardware, hypervisor, power, network, licenses, staffing | Site- and workload-level TCO inventory |
| Internet/MPLS/VPN/ExpressRoute | Hybrid connectivity, egress, link maintenance | Bandwidth forecasting, routing choices, redundancy |
| Azure Monitor / Log Analytics | Ingestion, retention, queries/solutions per current pricing | Data collection filters, retention, sampling, budgets |
| Security/Defender plans | Per plan, scope, and supported resource types | Enable only required features; check real unit prices |
| Registry/Artifacts | Storage, pulls, traffic, image lifecycle | Image pruning, immutable digests, local caching |
| Extensions/add-on services | Varies by feature and published pricing | Review pricing/trials/plans before fleet-wide rollout |
| Operational effort | On-call, upgrades, DR, testing, policy upkeep | Automation, canaries, runbooks, clear ownership |

Use **Azure Cost Management** for Azure-side charges and internal tooling for on-premises costs. Azure tags on Arc resources do not allocate local electricity or hardware expenses automatically.

## 15. End-to-End Practice Lab on a Lab Cluster

### Step 1: Document Scope and Hypothesis

Pick **one supported test cluster** with the right kubeconfig and approved permissions. Objective: register in Azure Arc, verify agents, apply tags/owner, test Flux on a lab namespace, and confirm workloads keep serving if a **lab management link** is temporarily severed (where permitted). Never sever production networks.

### Step 2: Pre-Connection Checks

- Confirm cluster name/context/API endpoint, OS, K8s version, and node count.
- Review network requirements, firewalls/proxies, and supported regions.
- Verify Azure roles, Kubernetes privileges, provider registration, and resource group.
- Capture baseline state: namespaces, deployments, Pod readiness, and monitoring.

### Step 3: Connect to Arc

Use the commands in Section 5, replacing placeholders with your real lab subscription, resource group, and cluster. Verify **`az connectedk8s show`** returns the resource and **`kubectl get pods -n azure-arc`** shows no abnormal errors. Record the Azure resource ID, connection timestamp, and operator.

### Step 4: Enable Bounded GitOps

- Create a Git repo containing only the reviewed lab namespace/app with zero secrets.
- Install the Flux extension on the lab cluster and create a configuration pointing to the exact path.
- Enforce PR review rules and avoid `prune=true` on namespaces containing stateful data or non-Flux resources.
- Bump replicas from 1 to 2 via PR; verify reconciliation and Pod Ready status.
- Introduce harmless drift within lab scope and observe Flux reconcile it; **never touch production**.

### Step 5: Add Governance and Observability

- Add `environment=lab` and `owner=platform` tags to the Arc resource.
- Test what Azure Reader does—and does not—allow in Kubernetes RBAC.
- If the policy extension is supported, test a simple **Audit** policy in lab; inspect compliance reporting and remediation.
- Enable minimal budgeted telemetry or use existing monitoring; measure Pod readiness separately from request success.

### Step 6: Simulate Management Link Loss (Optional, With Approval)

In an isolated lab, briefly block outbound Azure connectivity **using a network-team-approved method** with an independent recovery path. Record:

- Do local workloads keep serving requests?
- How long until the Arc resource updates status (accounting for sync lag)?
- Can Flux still reach the Git repo? Are logs sufficient to prove it?
- After restoring connectivity, do extensions/GitOps/telemetry resync cleanly?

**Never conclude “losing Azure Arc stops Kubernetes” just because the Azure blade shows Disconnected.** Conversely, never claim offline survivability if the app calls cloud databases or cloud identity over the WAN.

### Step 7: Report Results

~~~yaml
# Sample lab REPORT template, NOT an Azure resource schema.
cluster: arc-dc1-lab
site: dc1-lab
azure_scope: rg-arc-hybrid-lab
operator: platform-lab
checks:
  - name: "Arc resource visible and agent healthy"
    result: "PASS / FAIL / INCONCLUSIVE"
  - name: "Flux reconciles reviewed Git revision"
    result: "PASS / FAIL / INCONCLUSIVE"
  - name: "Kubernetes RBAC least privilege verified"
    result: "PASS / FAIL / INCONCLUSIVE"
  - name: "Application SLI measured independently"
    result: "PASS / FAIL / INCONCLUSIVE"
  - name: "WAN isolation recovery (optional)"
    result: "NOT_RUN / PASS / FAIL"
open_issues:
  - "List any unresolved permissions, network or policy issues"
rollback_owner: platform-team
~~~

Use this template solely for reporting and review—never submit it to the Arc API. Mark PASS/FAIL only with evidence; use **INCONCLUSIVE/NOT_RUN** if telemetry is missing or a step was skipped.

## 16. Production Readiness Checklist

| Item | Pre-Approval Questions |
| --- | --- |
| Scope/owner | Are resource ID, site, environment, accountable owner, and data classification defined? |
| Kubernetes | Are distribution/version/architecture, HA, CNI/CSI, storage, backups, and DR verified? |
| Azure | Are subscription/resource group/location, providers, tags, policies, and Azure RBAC accurate? |
| Kubeconfig/RBAC | Is the exact context selected, with least-privilege onboarding creds and revocation plan? |
| Connectivity | Are DNS, TLS, proxies, Azure endpoints, Git registries, and app paths clearly separated? |
| Agents | Are Arc namespace, pod/extension health, and resource overhead validated? |
| GitOps | Are repo owners, branch protection, source auth, Flux scope, prune policy, and rollback approved? |
| Policy | Are Audit-first rollout, remediation, exemptions, and offline checks defined? |
| Observability | Are Arc status, Kubernetes health, app SLIs, and WAN-loss alerts active? |
| Secrets | Zero committed secrets, rotation enabled, identity and offline fallback designed? |
| Day-2 | Are upgrade matrices, capacity, on-call, incident runbooks, and decommission plans ready? |
| Cost | Are log ingestion, security, networking, registry, and on-prem hardware costs estimated? |

Never mark a cluster “production-ready” simply because `az connectedk8s connect` returned exit code 0. Require evidence across **workloads, data, security, monitoring, and recovery**—not Azure management state alone.

## 17. Applied Exercises and Self-Check Questions

### Exercise 1: What Does Centralized Governance Mean?

A data-center Kubernetes cluster runs Orders API. After registering with Azure Arc, the resource appears in an Azure resource group. An admin concludes: “From now on Azure operates our nodes and upgrades Kubernetes automatically; we no longer need backups.”

**Answer:** Incorrect. Arc registers a **connected cluster resource** and related governance capabilities; it does not transfer ownership of the control plane, nodes, storage, or data. The source team must still maintain backups, upgrades, networking, security, HA, and DR for that cluster type. Azure Arc helps govern policies/GitOps/observability when configured, but does not replace Kubernetes operational responsibility.

### Exercise 2: Management Failure or Application Failure?

For 12 minutes, Azure shows the Arc cluster as `Disconnected`. On site, `kubectl get nodes` reports all nodes `Ready`, and local synthetic checks show 9,990 successful requests out of 10,000 valid requests; meanwhile, another workload depending on an Azure SQL database times out because the WAN is down.

**Question:** What is the local synthetic success rate? Can you conclude the entire system still meets its SLO?

**Solution:**

\[
\mathrm{LocalSuccessRate}=\frac{9{,}990}{10{,}000}\times100\%=99.9\%.
\]

You can only state that the **measured local journey** achieved 99.9% during that window. You cannot claim the SQL-dependent workload meets its SLO while timing out, nor infer every Pod is healthy or data is synchronized. Separate Arc management connectivity, WAN/data dependencies, and per-application SLIs.

### Exercise 3: Designing a Three-Site GitOps Rollout

An enterprise runs three clusters: `lab01`, `dc1-prod`, and `edge-hn01`. A PR updates the API's container image and memory limits. Design:

1. A rollout order minimizing blast radius.
2. Stop/rollback triggers if memory pressure or request errors rise.
3. Git repo protections and Flux permission boundaries in production.

**Suggested answer:** Start with `lab01` and verify metrics/SLIs; proceed to a canary site with bounded traffic before rolling out to remaining production clusters. Pin immutable image digests, monitor memory/OOMKilled, latency/timeouts, and Pod readiness; if thresholds breach, halt promotion and revert via runbook while checking backward compatibility. Enforce PR reviews, branch protection, secret/image scanning, and least-privilege controller/service accounts.

### Exercise 4: Estimating Data-Based Monitoring Costs

Two sites ship an average of **6 GiB of logs/day/site** to a usage-billed ingestion service. Assume an ingestion rate of **1.50 USD/GiB** for math practice (not an actual Azure price sheet), ignoring retention and other fees. Estimated 30-day cost:

\[
2\times6\times30\times1.50=540\ \mathrm{USD}.
\]

If noisy telemetry is filtered down to **4 GiB/day/site**, the estimate drops to:

\[
2\times4\times30\times1.50=360\ \mathrm{USD},
\]

saving **180 USD per 30 days** under these assumptions. Ensure filtering never drops critical security events or incident evidence; actual costs depend on tier, retention, contracts, and current pricing.

### Self-Check Questions

1. How does Arc-enabled Kubernetes differ from AKS in control-plane location and upgrade responsibility?
2. Does an Azure connected cluster resource store all Pods and PVCs from the source cluster?
3. Why must you verify both `kubectl context` and subscription before running `az connectedk8s connect`?
4. Does Azure RBAC Reader on an Arc resource grant permission to delete a Kubernetes Deployment?
5. Which two distinct problems do Flux and Azure Policy solve? When can a Deny policy cause Flux reconciliation to fail?
6. What consequences can `prune=true` in a GitOps configuration cause, and how should it be controlled?
7. Why does Arc `Disconnected` not automatically mean the local site API is down?
8. Which metrics beyond Arc agent status are needed to evaluate true hybrid cluster health?
9. What costs arise when enabling Azure Monitor on an on-premises cluster besides running the nodes?
10. After a WAN outage, what must be reconciled across GitOps revisions, policies, telemetry, and application data?

**Key takeaway:** Azure Arc-enabled Kubernetes brings hybrid clusters into the **Azure governance layer**, without moving control planes or workloads into Azure. Its value comes from pairing **inventory and Azure RBAC**, **GitOps/Flux**, **policy, security, and observability** with accountable source-side Kubernetes operations. Sound designs tolerate management disconnects, enforce least privilege, govern changes, and measure health **by application user experience**, not Connected status alone.
