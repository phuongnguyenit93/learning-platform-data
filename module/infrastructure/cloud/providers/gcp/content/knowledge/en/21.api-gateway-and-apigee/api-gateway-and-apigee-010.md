# Apigee Hybrid and Deployment Requirements

> **Chapter:** API Gateway and Apigee  
> **Module:** CLOUD_PROVIDERS_GCP

An enterprise serves partner APIs over the Internet while keeping transaction data and backend systems inside private networks. It wants centralized API management, authentication, rate limiting, and API usage observability, yet still needs to **operate the request-processing path itself** on its own Kubernetes clusters. **Apigee hybrid** is designed for this use case: the **management plane** is managed by Google; the **runtime plane** is deployed and operated by the customer on a supported Kubernetes platform.

This lesson belongs to the **CLOUD_PROVIDERS_GCP** module, helping learners choose services, secure resources, automate deployments, and control reliability and cost across Google Cloud scenarios. The focus here is **architectural and operational prerequisites before installing Apigee hybrid**, rather than a "run one command to get a production gateway" guide.

**After this lesson, you can:**

1. Distinguish Apigee hybrid from API Gateway and fully Google-managed Apigee.
2. Describe the roles of the management plane, runtime plane, and configuration sync flow.
3. List runtime components and operational responsibilities: ingress, Message Processor, Cassandra, Redis/Valkey depending on version, MART, Synchronizer, Apigee Connect, and telemetry.
4. Evaluate Kubernetes platforms/versions, node pools, storage, networking, DNS/TLS, IAM, and Workload Identity before deployment.
5. Understand the provisioning workflow: organization → environment/group → cluster → identities → overrides → CRDs/Helm → proxy testing.
6. Plan HA, Cassandra backups, chart/version upgrades, monitoring, and budgeting.
7. Run **read-only** checks and design a lab/production readiness checklist without impacting live environments.

## 1. Choosing the Right API Management Solution

| Need | Google Cloud API Gateway | Google-Managed Apigee | **Apigee hybrid** |
| --- | --- | --- | --- |
| API routing, auth, and basic controls | Fits relatively straightforward cases | Yes, plus rich advanced API management | Yes, policies enforced in customer-managed runtime |
| API products, developer apps/keys, quotas, enterprise analytics | Different capability set/approach from Apigee | Centralized in Apigee | Uses Apigee management with self-hosted runtime |
| Who operates the gateway runtime? | Google | Google | **The enterprise**, on supported Kubernetes |
| Backends on-prem / multi-cloud | Connectable via appropriate architecture | Possible depending on networking/Apigee deployment | **Valuable** when runtime sits close to private networks/backends |
| Kubernetes / Cassandra / Helm operations | Not needed for the gateway itself | Not needed for Google-managed runtime | **Requires operations, observability, and DR teams** |
| Cost and complexity | Fits specific scale/feature sets | Apigee tier + network/usage | **Apigee cost + cluster/storage/network/operations** |

**Do not assume "hybrid" is always better or cheaper.** If the goal is simply exposing a few Cloud Run APIs with OpenAPI/JWT/API keys and no self-managed runtime is required, API Gateway is usually simpler. Choose hybrid when **processing location, internal connectivity, compliance, and operating model requirements** genuinely justify running Kubernetes and Cassandra.

Also do not mistake "hybrid" for a **completely offline runtime**: the runtime plane still needs outbound communication with the management plane and Google Cloud services for config sync, analytics, logs, and management.

## 2. Two Planes and Processing Flows

~~~mermaid
flowchart TB
  ADMIN["API platform / security team"] --> MGMT["Google-managed management plane\nUI · Management APIs · API products · Analytics"]
  MGMT -->|"Config, proxy revisions, policies"| SYN["Synchronizer\nCustomer Kubernetes"]
  MGMT <-->|"Apigee Connect: runtime-initiated channel"| CON["Connect Agent ↔ MART"]
  CLIENT["Mobile / partner clients"] --> DNS["DNS + TLS / Load Balancer"]
  DNS --> INGRESS["Apigee ingress gateway"]
  subgraph RUNTIME["Customer-managed runtime plane — Kubernetes"]
    INGRESS --> MP["Message Processors\nVerify key/token · Quota · Routing"]
    SYN --> MP
    MP <--> CASS["Cassandra\nPersistent API runtime state"]
    MP <--> CACHE["Redis / in-memory components"]
    CON
    UDCA["UDCA / Telemetry"]
  end
  MP --> BACK["Private backend\nGKE / Compute Engine / Cloud Run"]
  MP --> UDCA
  UDCA -->|"Analytics, logs, metrics: outbound TLS"| MGMT
~~~

The diagram illustrates **responsibility boundaries**, not every internal communication path or exact message storage location. In practice, operators, watchers, `cert-manager`, and version/feature-specific components also run.

### 2.1. Google-Managed Management Plane

Includes management capabilities such as organization, environments, environment groups, API proxies, API products, developer apps, deployment metadata, UI, and analytics. Administrators define and deploy API proxies through Apigee; **you do not need to host all of these management tools inside your runtime cluster**.

### 2.2. Customer-Managed Runtime Plane

Handles the live API request path: client → ingress → Message Processor executing policies → backend → response. Depending on topology, the runtime sits in GKE, an on-premises data center, or Kubernetes on another cloud. **You are responsible for clusters, capacity, security patches, persistent storage, networking, HA, and upgrades.**

### 2.3. What If Connectivity to the Management Plane Drops?

**Synchronizer** pulls management "contracts"/configurations to the runtime, and Message Processors execute using the locally synced state. If the path to the management plane is interrupted, **API traffic can continue running with the already-synced configuration**, provided ingress, backends, Cassandra, and the runtime remain healthy. However:

- **New** API proxies/configs may not reach the runtime yet.
- Reporting/analytics or management operations may lag.
- Tokens, entitlements, or policies depending on external services remain affected per design.
- This cannot be treated as a guarantee that "hybrid operates fully without Internet connectivity."

## 3. Components to Operate in the Cluster

| Component | Role | Key Operational Risk |
| --- | --- | --- |
| **Apigee ingress gateway** | HTTPS entry point; routes host/path to API proxies | DNS, TLS/mTLS, L4/L7 LB, and public ingress protection |
| **Message Processor (MP)** | Processes requests/responses and executes proxy policies | CPU/memory, latency, autoscaling, backend connectivity |
| **Synchronizer** | Pulls environment configs and proxy deployments from Google | IAM, outbound HTTPS, wrong org/env, config propagation |
| **Cassandra** | Persistent state for Apigee hybrid | Disk IOPS, storage durability, NTP, backup/restore, and quorum |
| **Redis / in-memory components** | State/cache support depending on release | Capacity, restarts/recovery, upgrade compatibility |
| **MART** | Runtime data management API from management plane | Authorization, Connect Agent, service health |
| **Apigee Connect Agent** | Opens an **outbound** secure channel to the management plane | Egress 443, IAM, APIs, and long-lived connections |
| **UDCA** | Pushes analytics from runtime to Google-managed services | Network/credentials, lag, data governance |
| **Telemetry (logger/metrics)** | Emits logs/metrics for observability | Quotas, cost, PII in logs, signal loss |
| **Apigee Operator/Watcher** | Reconciles Kubernetes CRDs and watches deployments | Cluster permissions, version compatibility, controller health |
| **cert-manager and internal CA** | Manages certificates used internally by Apigee | Certificate renewal, supported versions, Secrets permissions |

Charts, CRDs, and certain backing components can change across **Apigee hybrid minor/patch versions**. For instance, in the 1.17 branch, there is a phased transition from Redis resources to Valkey across patches. Therefore, **never swap charts/CRDs manually or skip intermediate patches during upgrades**; follow the exact release notes and upgrade path of your target version.

**Data boundary to understand:** The runtime processes API traffic within infrastructure you control, yet **management configs, analytics, and certain metadata flow to the Google-managed plane**. Do not state in compliance documents that "all data stays strictly on-prem" solely because you chose hybrid.

## 4. Platform and Version Support

Per the **Apigee hybrid supported platforms and versions** matrix (always verify at deployment time), the **1.17** branch released in September 2026 supports specific Kubernetes platforms and versions, which may include:

- **GKE on Google Cloud** (**Standard**, not GKE Autopilot).
- **Google Distributed Cloud software-only** on VMware or bare metal.
- **Amazon EKS** and **Azure AKS**.
- **Red Hat OpenShift**.
- **Rancher Kubernetes Engine (RKE2)** and other platforms explicitly listed in the official table.

**GKE Autopilot is currently not supported for Apigee hybrid installation.** Never assume "any Kubernetes cluster works" simply because it exposes standard Kubernetes APIs. Support also depends on **Apigee minor/patch version**, Kubernetes/OpenShift version, Helm, `cert-manager`, and compatible addons.

### 4.1. Check the Version Matrix Before Designing

| Component | Questions to Answer |
| --- | --- |
| Apigee hybrid | Is the minor/patch currently supported by Google? What is its EOL schedule? |
| Kubernetes | Is the exact K8s version **in the matrix for the planned Apigee patch**? |
| Helm | Is Helm 3.x **at the supported level** for the target branch (1.17 matrix lists 3.17+)? |
| cert-manager | Supported version? Any known issues with CA/TLS rotation? |
| Platform-specific addons | Compatible Cloud Service Mesh, CSI driver, storage plugin, ingress/LB? |
| Client tools | `kubectl` within version skew; `gcloud` with required APIs enabled? |
| Upgrade path | Must you pass through v1.16 before v1.17? Are there special patch transitions? |

This lesson's examples assume **Apigee hybrid 1.17.x on GKE Standard** and **Helm 3.17+**. That is an illustrative compatible pairing, **not a guarantee that every v1.17 patch shares identical requirements**. Always read the exact docs for your chosen patch before installing.

### 4.2. Upgrades and EOL

Google publishes support timelines for each minor release. Once an older version reaches EOL, do not leave an unpatched runtime running merely because "the cluster still works." For 1.17, upgrade docs also include patch-specific CRD/cache migration steps; **never jump directly from a very old release to the latest** skipping the documented upgrade path.

## 5. Google Cloud and Apigee Organization Prerequisites

Prepare **before provisioning Kubernetes resources**:

1. Valid **Google Cloud project** and active **billing account**.
2. **Apigee hybrid entitlement/subscription** matching your organization's commercial model; enabling APIs does not replace licensing/contracts.
3. **Apigee organization** linked to the project via the hybrid provisioning workflow.
4. At least one **environment** (e.g., `test`) and one **environment group** (e.g., `api-test-group`) holding the API serving hostname.
5. **Apigee instance/runtime association** matching the region/cluster and organization per the provisioning flow.
6. **Google Cloud IAM** for provisioners, service identities for components, and scoped read/operate access.
7. Required **API services** enabled on the project (varies by platform).
8. Operational processes for **hostnames/DNS, TLS certificates, quotas, support escalation, and cost**.

### 5.1. APIs Typically Needed on GKE

In Apigee hybrid installation docs for GKE, the baseline API list includes:

~~~text
apigee.googleapis.com
apigeeconnect.googleapis.com
cloudresourcemanager.googleapis.com
compute.googleapis.com
container.googleapis.com
pubsub.googleapis.com
~~~

Additionally, integrated services like Cloud Logging/Monitoring, Cloud Storage, or the IAM Credentials API must have access/permissions when used by corresponding components. For EKS/AKS/GDC, the GKE/Compute API list differs; **do not copy one list verbatim assuming every environment shares identical API requirements**.

**Read-only** commands to inspect the project/APIs:

~~~bash
gcloud config get-value project

gcloud services list --enabled \
  --project=LAB_PROJECT_ID

gcloud projects describe LAB_PROJECT_ID
~~~

The **enable APIs** command below **modifies the project**—use only on an authorized lab project:

~~~bash
gcloud services enable \
  apigee.googleapis.com \
  apigeeconnect.googleapis.com \
  cloudresourcemanager.googleapis.com \
  compute.googleapis.com \
  container.googleapis.com \
  pubsub.googleapis.com \
  --project=LAB_PROJECT_ID
~~~

Do not enable APIs or create an Apigee organization in a production project without an owner, license/subscription, IAM review, and budget. Some organization/region creation choices have constraints that are not easily reversible.

### 5.2. Organization, Environment, Environment Group

| Entity | Example | Role |
| --- | --- | --- |
| Organization | `demo-apigee-org` | API management scope and administrative boundary |
| Environment | `test` | Deployment space for proxies |
| Environment group | `api-test-group` | Groups one or more environments with host aliases |
| Host alias | `api.lab.example.com` | Hostname called by clients; matches routing/TLS |
| Runtime instance | `runtime-lab-01` | Associates runtime deployment per provisioning architecture |

Creating an environment group in the management plane **does not automatically create DNS A records, load balancers, or TLS certificates** in your cluster. You must align the exact hostname between Apigee management and runtime virtual host configuration.

## 6. IAM, Kubernetes RBAC, and Workload Identity

**Three separate permission layers:**

| Layer | Granted To | Used For |
| --- | --- | --- |
| **Google Cloud IAM** | Provisioners, Google Cloud service accounts | Managing the Apigee org, calling APIs, writing metrics/logs/analytics |
| **Kubernetes RBAC** | Cluster operators, Apigee Operator, SRE team | Creating CRDs, workloads, namespaces, secrets, storage |
| **Service identity / Workload Identity** | Pods/KSAs ↔ GSAs or equivalent federation | Allowing components to call Google APIs without long-lived key files |

On GKE, use **Workload Identity Federation for GKE** per the Apigee hybrid workflow. On EKS/AKS or on-prem, use Google-supported **Workload Identity Federation** where appropriate. Any approach using key files/Kubernetes Secrets requires strict key lifecycle protection; never place JSON keys in Git or container images.

**Example responsibility mapping:**

- `apigee-synchronizer`: pulls configuration from the management plane.
- `apigee-runtime`: permissions required by runtime components.
- `apigee-mart` and `apigee-watcher`: manage runtime configuration and status.
- `apigee-logger` / `apigee-metrics`: write to Cloud Logging/Monitoring when enabled.
- `apigee-cassandra`: supports backup/storage integration as configured.
- `apigee-guardrails`: checks resource/service usage per feature.

**Never grant Project Editor/Owner to every pod.** Use exact service accounts and roles per chart/component, auditing project/resource bindings, impersonation permissions, and rotation.

### 6.1. Read-Only Preflight Checks

~~~bash
# Check active identity and GKE context
gcloud auth list
kubectl config current-context
kubectl cluster-info

# Never expose service account keys
kubectl get serviceaccounts -n apigee
kubectl get pods -n apigee -o wide
~~~

If the namespace does not exist yet, `kubectl get ... -n apigee` returns NotFound; that **does not mean the cluster is broken**. Distinguish fresh installations from troubleshooting existing systems.

## 7. Sizing Kubernetes, Storage, and High Availability

### 7.1. Two Resource Pools with Different Needs

**Cassandra** is stateful, whereas Message Processors and many runtime control components scale primarily with traffic. The minimum cluster configuration docs recommend **separating node pools**:

| Item | Stateful Pool (Cassandra) | Stateless Pool (Runtime/MP) |
| --- | --- | --- |
| Common GKE name | `apigee-data` | `apigee-runtime` |
| Purpose | Persistent storage, Cassandra quorum | Processing requests, policies, and backends |
| Reference nodes | 1 node/zone × 3 zones | 1 node/zone × 3 zones |
| Reference production minimum | Around **8 vCPU, 32 GiB RAM/node** | Around **8 vCPU, 32 GiB RAM/node** |
| Reference non-prod minimum | Around **4 vCPU, 16 GiB RAM/node** | Around **4 vCPU, 16 GiB RAM/node** |
| Disk | Durable dynamic PVC/StorageClass with sufficient IOPS | Managed per workloads/charts |
| IO/network | At least ~**2,000 IOPS** (reference), **1 Gbps** network/node | Per chart/traffic and platform capabilities |

These are **documentation baseline figures**, not capacity planning for real traffic. Select machine types, disk classes, and replica counts based on **load testing, latency targets, number of environments, policies, API call volume, quotas, and log volume**. When choosing specific VMs, check memory/CPU SKUs in your region; never assume machine size solely from a node pool name.

**Production:** Google recommends at least **two clusters** to minimize disruption during upgrades or cluster outages, paired with DNS/LB failover and proper Cassandra replication/backups. A single regional cluster spanning multiple zones tolerates node/zone failures but **does not replace** a cluster-level DR plan.

### 7.2. Specific Requirements for Cassandra

- **PersistentVolumes/PVC:** a storage class supporting dynamic provisioning, disk durability, and appropriate multi-zone topology constraints.
- **IOPS/latency:** Cassandra is sensitive to disk I/O; use supported SAN/attached storage and **do not default to NFS** simply because it offers large capacity.
- **Network:** Cassandra gossip, replication, and consistency require stable connectivity; docs specify at least ~**1 Gbps/node** and p99 inter-node latency ideally below ~**100 ms**.
- **NTP:** synchronize clocks across nodes/regions to avoid data corruption or debugging confusion.
- **Backup/restore:** schedule backups, test restores, enforce encryption and retention; Google **does not back up customer Cassandra clusters** for you.
- **Pod disruption:** check PDBs/maintenance settings so node-pool upgrades never break quorum. PDB controls may vary across hybrid patches.
- **Capacity headroom:** keep spare CPU/IP/storage quota for rolling upgrades and node failover.

**Never run `kubectl delete pvc`, delete Cassandra pods en masse, change a production StorageClass, or force-redeploy** just to experiment. A cluster showing "pods Running" can still lose quorum or lose data if PVCs lack IOPS or recoverability.

### 7.3. Real Scale Signals to Measure

| Signal | Impact |
| --- | --- |
| Average/peak requests per second | Message Processor count, autoscaler headroom |
| P95/P99 API latency | Policy processing + backend latency budget |
| Number of proxies/policies | Per-request CPU/memory, sync payload size |
| Cassandra disk utilization/latency | Capacity, IOPS, compaction, and backups |
| Cross-region traffic | Egress costs, replication latency |
| Quota/analytics volume | Pub/Sub/UDCA backpressure, logs |
| Upgrade window | Number of clusters/nodes needed to sustain service |

## 8. Networking, Ingress, TLS, and Google Cloud Egress

Apigee hybrid has **two independent traffic paths**:

1. **Data path:** client → DNS/HTTPS → ingress gateway → Message Processor → enterprise backend.
2. **Control/telemetry path:** cluster Pods → Google-managed APIs over HTTPS for contract sync, management, reporting, and logs/metrics.

### 8.1. Connectivity Matrix to Verify

| Source | Destination | Typical Port / Protocol | Controls |
| --- | --- | --- | --- |
| Client/partner | Ingress LB → Apigee ingress | **HTTPS TCP/443** (recommended) | Public/private LB, WAF/DDoS, TLS |
| Ingress | Message Processors | Managed by charts/mesh | Kubernetes network policies and service discovery |
| Message Processors | Backend APIs | TCP/HTTPS per backend | DNS, routing/VPN/Interconnect, auth/mTLS |
| Synchronizer | `apigee.googleapis.com`, IAM APIs | **TCP/443 TLS** | DNS/egress proxy/firewall/identity |
| Apigee Connect Agent | `apigeeconnect.googleapis.com` | **TCP/443 TLS** | Agent **initiates outbound connections** |
| UDCA/analytics | Apigee/Google Storage endpoints | **TCP/443 TLS** | Data governance and quotas |
| Logger/Metrics | `logging.googleapis.com`, `monitoring.googleapis.com` | **TCP/443 TLS** | IAM, sampling, and cost |
| Cassandra nodes | Cassandra peers | Internal ports per version | Network policies, replication, MTU, latency |

The exact list of ports and endpoints depends on **release/config/plugins**. Consult the **Secure ports usage** documentation for your exact hybrid version before writing firewall rules. **Do not pin IP addresses of `*.googleapis.com`** because they can change; use DNS/proxy/firewall policies following Google-supported patterns.

### 8.2. Why Is No Inbound Management Port Needed from Google?

**Apigee Connect Agent** establishes an outbound connection to Google's management service, enabling runtime data management via MART **without exposing a public MART port** for inbound connections from the management plane. However, you **must still expose HTTPS ingress** if external customers or partners call APIs from outside the cluster.

**Do not confuse** "no inbound port needed for the control plane" with "no load balancer/DNS/443 needed for clients."

### 8.3. Public or Private Ingress?

| Scenario | Reference Design |
| --- | --- |
| Public partner API | External Load Balancer → Apigee ingress, TLS, WAF/Cloud Armor where appropriate |
| Internal-only applications | Internal Load Balancer/private DNS/VPN/Interconnect |
| Multi-cloud/on-prem | LB/proxy at data center, dedicated routes to backends, IP allowlists or mTLS per risk |
| Multi-region | DNS/GSLB failover and multiple runtime clusters; check backend/data consistency |

The **environment group hostname** (e.g., `api.lab.example.com`) must match host aliases, ingress certificates, DNS records, LB rules, and proxy base paths. Any mismatch can trigger TLS failures, `404`s, or routing to the wrong environment.

### 8.4. TLS/mTLS and Certificates

- You need a **public certificate or internal PKI** matching the hostname clients call; avoid expired certs or mismatched SANs.
- Configure **one-way TLS** or **mTLS** on ingress as required, managing Kubernetes Secrets/cert files per Apigee instructions.
- **Apigee's internal `cert-manager`** serves trust channels between internal components; **it does not automatically replace** ingress TLS certificates for public domains.
- Open only required ports, enforce TLS version/cipher policies, automate rotation, and alert on upcoming expirations.
- If a load balancer **terminates TLS** before ingress, explicitly design LB ↔ ingress TLS and trusted HTTP headers/identity—never let backends trust unverified `X-Forwarded-*` headers.

**Illustrative** `overrides.yaml` snippet for a virtual host:

~~~yaml
virtualhosts:
  - name: api-test-group
    sslCertPath: "./certs/api.lab.example.com.pem"
    sslKeyPath: "./certs/api.lab.example.com.key"
~~~

`name` must be the **environment group name**, not the hostname. Prepare **real certificates/keys and protect private keys** per your architecture; this snippet **is not enough to run a complete hybrid instance**.

## 9. Data, Compliance, and Separation of Responsibilities

A primary driver for hybrid is keeping **API request processing and backend connections** inside customer-managed environments. That does not mean all API-related information remains strictly on-prem.

| Data Category | Where Does It Typically Flow? | Required Checks |
| --- | --- | --- |
| Request/response payloads | Passes through customer-managed runtime | Avoid inadvertently logging sensitive payloads; encrypt client→ingress→backend |
| Runtime state | Cassandra / local runtime | PVCs, encryption at rest, backups, tenant access |
| API definitions/config | Management plane; pulled to runtime by Synchronizer | Config approvals, admin permissions, secrets |
| Analytics/usage | UDCA sends analytics data to managed services | Data classification, masking/hashing, location/residency |
| Logs/metrics | Cloud Logging/Monitoring when configured | PII retention, logging exclusions, cost |
| TLS secrets/identity | Cluster, Secret Store, workload identity | Secret rotation, RBAC, workload isolation |

If your organization has **data residency requirements**, verify control plane storage locations, analytics regions, `contractProvider` settings where applicable, and commercial/regulatory terms; **never unilaterally claim "data never leaves the country."**

**Rule:** Never put access tokens, customer details, credentials, or transaction data into analytics custom dimensions or logs just for debugging. Apply redaction, hashing, sampling, and retention per security requirements.

## 10. Overall Installation Roadmap: Provision → Cluster → Helm → Test

Real deployments should proceed in stages with verification gates. Google provides **The big picture** flow for Apigee hybrid:

~~~mermaid
flowchart TB
  P["1. Google Cloud project + billing + APIs"] --> O["2. Apigee org + environment + environment group"]
  O --> K["3. Supported Kubernetes platform + node pools/PVC"]
  K --> ID["4. Service accounts + WIF + egress/DNS/TLS"]
  ID --> OV["5. overrides.yaml + chart version + secrets"]
  OV --> CRD["6. Install cert-manager / Apigee CRDs"]
  CRD --> H["7. Helm charts in order and readiness"]
  H --> ING["8. Expose ingress, DNS + valid TLS"]
  ING --> PROXY["9. Deploy a test API proxy"]
  PROXY --> SLO["10. Functional + security + load + DR validation"]
~~~

**All examples below assume:** an **already provisioned Apigee org**, a GKE **Standard** cluster supporting hybrid 1.17, valid IAM, proper node pools/StorageClass, downloaded Helm/charts, and prepared secrets/certificates. **You cannot simply copy one YAML from this lesson and install all of Apigee hybrid.**

### 10.1. `overrides.yaml` Skeleton

This file customizes the runtime charts. Core fields commonly seen:

~~~yaml
# LEARNING SKELETON — NOT A COMPLETE PRODUCTION overrides.yaml
namespace: apigee

gcp:
  projectID: "LAB_PROJECT_ID"
  region: "asia-southeast1"

k8sCluster:
  name: "hybrid-gke-lab"
  region: "asia-southeast1"

org: "LAB_APIGEE_ORG"
instanceID: "LAB_INSTANCE_ID"

envs:
  - name: "test"
    # Cache encryption secret, service identity, and other required
    # properties must be configured per the patch's install guide.

virtualhosts:
  - name: "api-test-group"
    sslCertPath: "./certs/api.lab.example.com.pem"
    sslKeyPath: "./certs/api.lab.example.com.key"
~~~

**When using `instanceID`, it must match the provisioned Apigee instance/association;** `gcp.region`, the control plane/analytics region, and the cluster region are not always the same concept. In multi-region/multi-org topologies, verify instance ID and organization mapping rules.

**Never store secret/key files in Git.** Across multiple clusters, maintain per-cluster/region configurations and manage overrides as reviewed release artifacts. Fields like `envs[].cacheEncryptionSecret` may be mandatory depending on version; check the property reference before running Helm.

### 10.2. Download Helm Charts for the Right Branch

Apigee hybrid publishes charts from Google Artifact Registry:

~~~bash
# The commands below only inspect/pull artifacts without installing to the cluster.
# Replace RELEASE_PATCH with a supported and reviewed patch version.
helm version
kubectl version --client

helm show chart \
  oci://us-docker.pkg.dev/apigee-release/apigee-hybrid-helm-charts/apigee-operator \
  --version RELEASE_PATCH
~~~

Once a patch is chosen, run `helm pull ... --version RELEASE_PATCH` consistently for all charts—never mix 1.16 charts with 1.17 operators/CRDs. The `helm show chart` command is a **metadata read example**; replace `RELEASE_PATCH` before running.

Core charts installed in architectural order:

| Order | Helm Chart | Function |
| ---: | --- | --- |
| 1 | `apigee-operator` | Operator/controller |
| 2 | `apigee-datastore` | Cassandra datastore |
| 3 | `apigee-redis` (or corresponding chart in supported patch) | In-memory store |
| 4 | `apigee-telemetry` | Logger/metrics |
| 5 | `apigee-ingress-manager` | Ingress controller/gateway |
| 6 | `apigee-org` | MART, Apigee Connect, UDCA, and organization components |
| 7 | `apigee-env` | Synchronizer and runtime **per environment** |
| 8 | `apigee-virtualhost` | Env group/virtual host **per environment group** |

**Version warning:** chart names and components can change across patches, especially during the Redis/Valkey transition. **Never apply the chart order above mechanically** when release notes/upgrade guides specify a different sequence or migration chart.

### 10.3. CRDs and Helm Dry Run

Per current install docs, Apigee CRDs use Kustomize with server-side apply. The commands below are **examples run inside the extracted charts directory with appropriate cluster permissions**:

~~~bash
# DRY RUN ONLY; does not create CRDs:
kubectl apply -k apigee-operator/etc/crds/default/ \
  --server-side \
  --force-conflicts \
  --validate=false \
  --dry-run=server

# CHECK HELM RENDER / APPLY DRY RUN ONLY:
helm upgrade operator apigee-operator/ \
  --install \
  --namespace apigee \
  -f overrides.yaml \
  --dry-run=server
~~~

**Both commands still contact the Kubernetes API and require permissions.** On a fresh install, complete `cert-manager`, service accounts, CRDs, and all preflight steps in the official guide **before running real installs**. Never put `kubectl apply --force-conflicts` into production automation without understanding CRD field ownership.

After approval and following Google's full installation guide, the operator install command looks like:

~~~bash
# MODIFIES a real cluster; run only after preflight and change approval:
helm upgrade operator apigee-operator/ \
  --install \
  --namespace apigee \
  -f overrides.yaml
~~~

**Do not treat the operator command alone as "Apigee hybrid is installed."** Each remaining component must still be installed and verified in chart order. During upgrades, **do not follow the fresh-install procedure verbatim**; use the patch-specific upgrade/rollback guide.

### 10.4. Verify Status After Installation

~~~bash
# Read-only status checks against the right kubecontext
kubectl config current-context
helm list -n apigee
kubectl get pods -n apigee -o wide

kubectl get apigeedatastores -n apigee
kubectl get apigeeorganizations -n apigee
kubectl get apigeeenvironments -n apigee
kubectl get apigeetelemetries -n apigee

kubectl get svc -n apigee
kubectl get pvc -n apigee
kubectl get events -n apigee --sort-by=.lastTimestamp
~~~

If CRDs/charts are not installed yet, querying custom resources reports **unknown resource type**; do not mistake that for a runtime failure. After installation, verify CRDs reach `running`/**Ready** states along with Pods and Helm releases—not merely whether Pod counts look `Running`.

### 10.5. Expose Ingress and Smoke-Test HTTPS

1. Configure the ingress gateway using the appropriate chart/overrides.
2. Provision the Load Balancer (internal/public), routing, ports, and health probes.
3. Issue a **valid** TLS certificate for the host alias and create the DNS record.
4. Verify gateway health and invoke a test proxy.
5. Expose endpoints publicly only after approving auth, quotas, rate limiting, and data controls.

Example **read-only check from an authorized client** once LB/DNS/TLS are in place:

~~~bash
# Substitute actual DOMAIN and assigned IP; never use -k to bypass TLS verification.
curl --resolve "api.lab.example.com:443:INGRESS_IP" \
  "https://api.lab.example.com/healthz/ingress"
~~~

After deploying an **API proxy** with base path `/orders/v1` targeting a mock/private lab backend, test both an allowed request and a policy-rejected request. **Never use real production tokens in sample commands or logs.**

## 11. Production Rollout, HA, Backup, and Upgrades

### 11.1. Minimum HA Capabilities

- Two production runtime clusters when zero-disruption HA/upgrades are required, with active **traffic failover**.
- Cassandra on durable storage with proper quorum/replication and **restore-tested** backups.
- Ingress/LB, DNS, and backend routing with defined RTO/RPO and traffic-drain procedures.
- PodDisruptionBudgets, node-pool upgrades, capacity headroom, and Kubernetes upgrades planned ahead.
- Separate dev/staging/prod with isolated configs, secrets, IAM, and network policies.
- A **management-plane disconnect runbook** documenting what keeps serving requests and what lags in sync.

### 11.2. Backing Up Cassandra and Configuration Data

Apigee hybrid backup docs identify **Cassandra as the primary persistent runtime datastore** requiring a backup/restore strategy; most other components are stateless and redeployable from charts/overrides. Still, store your **source of truth for overrides, Helm/chart versions, secrets/certificates, IAM mappings, and LB/DNS configs** in a separate secure location.

**Never rely on ad-hoc VM snapshots or arbitrary PVC copies as a standard Cassandra backup** without consistency guarantees. Use the supported Apigee hybrid backup/restore workflow, store backups in a separate failure domain, and run periodic restore drills.

### 11.3. Ordered Upgrades and Rollback Readiness

Reference operational workflow:

1. Select a **supported patch**, reading release notes, known issues, compatibility, and migration steps.
2. Prepare Cassandra backups, `overrides.yaml`, certificate references, and identities.
3. Build/update a preprod environment matching production topology closely.
4. Run **Helm dry runs**, checking CRD migrations, API deprecations, and resource quotas.
5. **Drain/divert traffic away from the cluster** being upgraded when running multiple clusters.
6. Upgrade charts/CRDs in the patch's documented order; verify status and test API requests after each group.
7. Restore traffic gradually, monitoring latency/errors, Cassandra, and analytics delivery.
8. On failure, follow the **branch/patch-specific rollback guide**; never assume `helm rollback` alone suffices.

**Risk example:** in certain 1.17 patches, Redis/Valkey CRD schemas change. Rolling back to 1.16 involves specific conversion webhook/CRD handling steps; **never unilaterally downgrade charts** once datastores/CRDs have been migrated.

## 12. Observability and SLO-Driven Operations

| Signal | Where to Observe | Action to Take |
| --- | --- | --- |
| API 2xx/4xx/5xx, p95/p99 | Apigee analytics, runtime/LB telemetry | Separate client, policy, and backend errors |
| Ingress health, TLS expiry | LB probes, ingress controller, certificates | Alert on handshake 5xx / 502 / 503 |
| MP CPU/memory/replicas | Kubernetes/Cloud Monitoring | Tune HPA, policy latency, node capacity |
| Cassandra disk IOPS, latency, quorum | Cassandra metrics, PVC/storage monitoring | Forecast compaction, storage, and backups |
| Synchronizer config sync lag | Component logs, deployment state | Check egress/IAM/APIs, contract version |
| Apigee Connect availability | Connect Agent metrics/logs | Detect management connectivity failures |
| UDCA analytics lag/errors | Telemetry logs, analytics pipeline | Distinguish healthy data plane from delayed analytics |
| Helm/Operator/CRD health | `helm list`, `kubectl get ...` | Track upgrades and drift |
| Logs/Cloud Billing/quotas | Cloud Logging/Monitoring/Billing | Control volume and spend |

Define **primary endpoint SLOs** from real requests (success rate/latency) and **secondary SLOs** for config sync lag, analytics delay, and backup RPO. **"Pods Running" does not mean the API gateway is healthy** if certificates are expired or backends are timing out.

### 12.1. Quick Fault Isolation

| Symptom | Priority Layer to Investigate |
| --- | --- |
| Client cannot resolve host | DNS records, split-horizon DNS |
| TLS handshake / cert error | Ingress certificate, SANs, issuer, LB termination |
| `404` after proxy deploy | Env group hostname, proxy base path, env association |
| `401/403` from proxy | API key/OAuth/mTLS policies, developer app/product, separate IAM |
| `502/503` and backend unreachable | MP → backend DNS/route/TLS, target health |
| Newly deployed proxy does not appear | Synchronizer, permissions, org/env, management egress |
| Runtime requests succeed, yet analytics missing | UDCA / egress 443 / IAM and managed analytics |
| Cassandra Pods CrashLoop / PVC Pending | StorageClass, disk quota/IOPS, affinity, KSA/IAM |
| `ImagePullBackOff` | Registry credentials, network, image/chart version |
| Management actions slow while API traffic runs | Apigee Connect/MART/management connectivity |
| All clusters fail after upgrade | Version mismatch/CRD migration, unisolated rollout |

### 12.2. Short Diagnostic Runbook

~~~mermaid
flowchart TD
    ERR["Gateway / deployment error"] --> Q{"Does client request reach ingress?"}
    Q -- "No" --> NET["DNS, LB, TLS, ingress routing"]
    Q -- "Yes" --> MP{"Does Message Processor handle it?"}
    MP -- "No" --> POD["Pods, HPA, cluster capacity, mesh"]
    MP -- "Yes" --> BACK{"Does backend respond?"}
    BACK -- "No" --> TARGET["Route/TLS/timeout/backend health"]
    BACK -- "Yes" --> POL["Policies/auth/quota and response metrics"]
    ERR --> MGMT{"Proxy config out of sync?"}
    MGMT -- "Yes" --> SYNC["Synchronizer, Apigee Connect, IAM, egress 443"]
    ERR --> DATA{"Cassandra/PVC failing?"}
    DATA -- "Yes" --> CASS["Quorum, IOPS, disk, NTP, backup/DR"]
~~~

When an API fails, never immediately widen project-wide IAM or delete Cassandra PVCs. Determine whether the **data plane** and **management/telemetry plane** are failing separately or together, capture evidence, then apply the targeted fix.

## 13. Case Study: Banking API Connected to Private Backends

**Business requirement:** A bank launches partner APIs backed by a core banking system in its data center. It must enforce controls on all API traffic before reaching the backend, keep applications and transaction data inside managed networks, yet let development teams define API products and manage consumption.

**Proposed architecture:**

- Google-managed Apigee management plane with RBAC and API product/proxy governance.
- Two Kubernetes runtime clusters (each supporting Apigee hybrid) in separate failure domains.
- External ingress gateway with HTTPS/mTLS per partner requirements, DDoS/WAF, and DNS failover.
- Message Processors executing API key/OAuth, quota, spike arrest, and threat protection policies before calling backends.
- Stateful Cassandra with provisioned storage IOPS, backups, and a DR plan.
- Control/analytics outbound 443 through approved proxy/policies, accounting for residency/redaction.
- Observability on both gateway and backend, with proxy revision rollback through release pipelines.

**Critical decision:** Which analytics data flows to Google-managed services? If policy forbids sending PII, mask/hash or exclude it from analytics/logs **before enabling production**. Relying solely on Message Processors running on-prem is not enough.

**Measuring outcomes:** target 99.x% success/latency SLOs, failover tests, Cassandra restore drills, quota enforcement, zero secrets in logs, HA headroom, and full TCO tracking.

## 14. Practice: Building a Deployment Readiness Dossier

This is a **design and read-only verification lab** that does not require learners to provision expensive Apigee orgs/clusters. If your organization provides a sandbox with hybrid already installed, inspect only the authorized environment.

### Part A — Solution Selection

Suppose an enterprise has:
- 25 partner APIs; backends in a private VPC and an on-prem data center.
- 1,500 requests/second at peak (hypothetical figure, not yet sized).
- Requirements for auditing, developer app credentials, quotas, and controlled data residency.
- A Kubernetes SRE team capable of maintaining clusters, storage, and upgrades.

**Task:** compare API Gateway, Google-managed Apigee, and Apigee hybrid across 5 criteria: data path, IAM/API management, operations, HA/DR, and cost. Base the decision on **evidence**—never pick hybrid just for the name.

### Part B — GKE Standard Preflight

On an **authorized lab cluster**:

~~~bash
# DO NOT modify resources
gcloud config get-value project
gcloud container clusters list --project=LAB_PROJECT_ID

kubectl config current-context
kubectl get nodes -o wide
kubectl get storageclass
kubectl get pv,pvc -A

helm version
kubectl version --client
~~~

Complete the table:

| Check | Result to Record |
| --- | --- |
| Supported platform | GKE Standard (not Autopilot), K8s version in matrix |
| Helm/cert-manager | Version compatible with target hybrid patch |
| Node pools | Stateful/stateless separated, node count/headroom |
| Disk | Dynamic PVC, IOPS/latency, backup class |
| NTP/network | Clock sync, peer traffic, 443 egress |
| IAM | Google Cloud roles, KSA/GSA/WIF mappings |
| Organization | Org/env/envgroup + instance association |
| DNS/TLS | Host alias, valid cert/SAN, LB type |
| Data governance | Data classification, analytics redaction, residency |

### Part C — Inspect Deployment (If Hybrid Is Installed)

~~~bash
# READ-ONLY, right context and namespace
helm list -n apigee
kubectl get pods -n apigee
kubectl get apigeedatastores -n apigee
kubectl get apigeeenvironments -n apigee
kubectl get svc -n apigee -l app=apigee-ingressgateway
~~~

**If resources do not exist**, record `NOT INSTALLED`—do not install them yourself just to "complete the exercise." On an authorized ingress URL, verify the HTTPS certificate and a mock proxy test. Never test invalid tokens against real partner environments.

### Part D — Hypothetical Incident Analysis

1. **API returns 200, yet analytics lags by 20 minutes:** investigate UDCA/egress/managed analytics; never delete Cassandra.
2. **One zone fails and Cassandra quorum degrades:** inspect replicas/backups/PDBs without deleting PVCs; execute DR plan.
3. **Newly deployed proxy does not appear:** check org/env mapping, Synchronizer/Connect, and logs; never expose MART publicly.
4. **TLS certificate expires:** renew certificate/rotation/LB; do not widen backend firewalls.
5. **Upgrading v1.16 → v1.17:** consult release notes, CRD conversion, and version-dependent patch sequences.

**Deliverable:** two-plane diagram, requirements table, required permissions, per-incident runbooks, capacity estimate from measured RPS, and two-cluster upgrade strategy.

## 15. Self-Check Questions

1. **Does hybrid mean Google operates the runtime too?** No; the customer operates the runtime on supported Kubernetes.
2. **Why choose hybrid over API Gateway?** When you need advanced API management plus data-path/location control and accept operating Kubernetes/Cassandra.
3. **Does GKE Autopilot support Apigee hybrid 1.17?** No, per current supported platforms.
4. **If the management plane goes down, do all APIs immediately die?** Not necessarily; the runtime holds synced contracts, though new configs/analytics and some dependencies may be impacted.
5. **Which component stores core persistent state?** Cassandra.
6. **With a three-zone GKE cluster, do you still need backups?** Yes; HA does not replace backup/restore.
7. **Does Apigee Connect require opening a public inbound port for MART?** No; Connect Agent initiates outbound TLS.
8. **Can you hard-code `apigee.googleapis.com` IPs?** No; IPs change—use supported DNS/egress.
9. **What does an environment group represent?** A set of environments sharing host aliases tied to virtualhost routing.
10. **Can you install CRDs arbitrarily with `kubectl apply -f CRD.yaml`?** No; follow the exact Kustomize/server-side CRD procedure.
11. **Why check the Helm and cert-manager support matrix?** To avoid controller/CRD/TLS incompatibilities.
12. **When is a runtime truly ready?** Components/PVCs/ingress are healthy, proxy routes work, and policies/auth/backends plus logs/metrics are verified.
13. **Why does keeping API traffic local not guarantee all data stays local?** Analytics/config may flow to the Google-managed plane.
14. **With two clusters, how do you upgrade?** Drain traffic from one cluster, upgrade/test, restore traffic; repeat on the second cluster per the patch guide.
15. **Can you use minimum node counts instead of load testing?** No; you must capacity test based on RPS, policies, latency, and backend behavior.
16. **What does TCO include?** Apigee commercial cost, Kubernetes nodes/disks/LB/egress, backups, logs, and SRE staffing.

## 16. Apigee Hybrid Production Checklist

- [ ] Justified hybrid need; compared against API Gateway and managed Apigee.
- [ ] Project, billing, subscription/entitlement, and Apigee org/env/envgroup provisioned properly.
- [ ] Runtime Kubernetes platform and version are in the **supported matrix**; not using Autopilot.
- [ ] Helm, cert-manager, CSI, and K8s/CRD versions match the selected release patch.
- [ ] Node pools for Cassandra/MP have sufficient CPU, RAM, IOPS, networking, and headroom.
- [ ] NTP, persistent volumes, Cassandra backup/restore drills, and RTO/RPO are in place.
- [ ] Production HA has sufficient clusters/zone isolation and failover routing.
- [ ] Least-privilege IAM/Kubernetes RBAC/Workload Identity; no service account keys in Git.
- [ ] Outbound HTTPS 443 reaches the right Apigee/Google endpoints without hard-coding IPs.
- [ ] Ingress DNS/TLS/mTLS/LB and backend routing are tested.
- [ ] `overrides`, Helm releases, and secret references managed under change review.
- [ ] Charts/CRDs installed in the exact order and per patch-specific instructions.
- [ ] Mock proxy → mock backend, auth/quota/threat policies, and telemetry verified.
- [ ] Data governance/analytics/PII/residency evaluated including the management plane.
- [ ] Monitoring covers p95/p99, 5xx, Cassandra, Synchronizer, Connect, UDCA, and certificates.
- [ ] Upgrade/EOL schedule, canary rollouts, backups, and rollback/DR runbooks exist.
- [ ] Budgeted for licenses, compute, storage, networking, observability, and SRE operations.

## 17. Official Google Cloud Documentation

Select the exact version/patch when consulting documentation since instructions, chart names, CRDs, and requirements evolve.

- [What is Apigee hybrid? (v1.17)](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/what-is-hybrid) — management plane/runtime plane, components, and data placement.
- [The big picture](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/big-picture) — provisioning, installation, and testing roadmap.
- [Prerequisites](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/prerequisites.html) — billing, IAM, NTP, tools, and clusters.
- [Supported platforms and versions](https://docs.cloud.google.com/apigee/docs/hybrid/supported-platforms) — Kubernetes/Helm/cert-manager matrices, EOL.
- [Enable APIs](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/precog-enableapi) — platform-dependent APIs.
- [Minimum cluster configurations](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/cluster-overview) — node pools, disk IOPS, network/HA.
- [Secure ports usage](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/ports.html) — ingress/egress and Apigee Connect.
- [Install service accounts](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/install-service-accounts) — per-component permissions.
- [Service account authentication](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/install-sa-authentication) — Workload Identity Federation and alternatives.
- [Configuration property reference](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/config-prop-ref) — `overrides.yaml` schema.
- [Helm reference](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/helm-reference) — chart mapping/order and upgrades.
- [Download Helm charts](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/install-download-charts) — charts from Artifact Registry.
- [Ingress TLS/mTLS](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/ingress-tls) — certs and virtual hosts.
- [Expose Apigee ingress](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/install-expose-apigee-ingress.html) — LB/DNS/TLS health checks.
- [Cassandra backup overview](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/cassandra-backup-overview.html) — persistent state and DR.
- [Upgrade Apigee hybrid 1.17](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/upgrade) — patch sequence, CRDs, and rollback.
- [Apigee hybrid release notes](https://docs.cloud.google.com/apigee/docs/hybrid/release-notes) — feature fixes, known issues, support changes.

**Key takeaway:** Apigee hybrid lets **Google manage the API control plane** while the enterprise **operates the data plane on Kubernetes**. In return for runtime control comes responsibility for **supported platforms, Cassandra, NTP, IAM/identity, outbound 443, ingress DNS/TLS, Helm/CRDs, HA, backups, upgrades, and cost**. Move to production only once every one of those layers has verified test evidence.
