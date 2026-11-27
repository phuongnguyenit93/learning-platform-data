# Private Clusters and Protecting Control Plane Access in GKE

An e-commerce enterprise runs APIs and workers on **Google Kubernetes Engine (GKE)**, stores transactional data in **Cloud SQL**, product images in **Cloud Storage**, and container images in **Artifact Registry**. The security team mandates: nodes must not have external IPs, the Kubernetes API must not become an unintended public administrative endpoint, developers should only view required resources, and SREs must be able to troubleshoot incidents from the corporate network or a controlled access path.

In GKE, **private cluster** primarily refers to **nodes using internal IP addresses instead of external IPs**, combined with how connectivity to the **control plane** is configured. However, a dangerous misconception is that **"private nodes" automatically means "the Kubernetes API only has a private endpoint."** GKE supports IP-based endpoint configurations (private/public) and DNS-based endpoints; which options are available depends on cluster mode, version, and endpoint access settings.

This lesson belongs to the **GKE Fundamentals** chapter of the **CLOUD_PROVIDERS_GCP** module. It focuses on designing and verifying the layers of **network paths, identity, Kubernetes authorization, and operational governance** to protect the control plane, connecting with organizations, IAM, VPCs, Compute Engine, Cloud Run, storage/databases, release automation, reliability, and cost.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Distinguish the **control plane** from the **node/workload data plane**, and distinguish private nodes from a private control-plane endpoint.
2. Compare **IP-based public endpoints**, **IP-based private endpoints**, and **DNS-based endpoints**, as well as the scope of **Master Authorized Networks**.
3. Choose an appropriate Kubernetes API management path: from the VPC, over Cloud VPN/Interconnect, via an IAP-protected bastion, or via a DNS-based endpoint per policy.
4. Understand the roles of **Google Cloud IAM**, **Kubernetes RBAC**, and workload identities, without confusing permission to fetch kubeconfig with permission to modify the whole cluster.
5. Design subnets, Pod/Service secondary ranges, egress to Google APIs, and image pull permissions for private nodes.
6. Inspect GKE configuration with `gcloud`, fetch credentials for the right endpoint, and isolate network, authentication, and authorization errors.
7. Build a checklist for deployment, administrative recovery, monitoring, and cost estimation for a private cluster.

## 2. What Is the Control Plane and Why Protect It?

### 2.1. The Control Plane and Where Workloads Run

A GKE cluster has two logical component groups:

- **Control plane:** the Kubernetes API server, state store mechanisms, and orchestration components managed by GKE according to cluster mode. Users and CI/CD use the Kubernetes API to create, read, and update resources such as `Deployment`, `Service`, `Secret`, or `RoleBinding`.
- **Nodes and workloads:** Compute Engine worker nodes or GKE-managed node infrastructure where Pods actually run and talk to each other and data services. With **Standard**, users have greater control over node pool settings; with **Autopilot**, GKE manages more node and scheduling aspects.

~~~mermaid
flowchart TD
    USER["Engineer / CI/CD"] --> API["Kubernetes API server\n(GKE-managed control plane)"]
    API --> SCHED["Desired state / scheduling"]
    SCHED --> N1["Worker node A"]
    SCHED --> N2["Worker node B"]
    N1 --> P1["Pod: orders-api"]
    N2 --> P2["Pod: catalog-api"]
    P1 --> DB["Cloud SQL"]
    P2 --> STORE["Cloud Storage"]
    REG["Artifact Registry"] -. "Image pull via node identity" .-> N1
    REG -.-> N2
~~~

**The control plane is a highly sensitive administrative surface.** If a principal can modify a `Deployment`, `RoleBinding`, workload identity, or `Secret`, the blast radius extends beyond a single Pod. Protecting the Kubernetes API therefore requires both **restricting access paths** and **enforcing precise authorization**.

### 2.2. Control Plane Reachability Is Not Workload Reachability

For example, an engineer on the Internet may be able to reach a **public IP-based Kubernetes API endpoint** if the cluster enables it, policy permits the source IP, and identity is valid. That does not give the engineer a direct network path to Pod IPs or node VMs. Conversely, Pods can reach Cloud SQL over private IP while an administrator's laptop still cannot reach a private Kubernetes API endpoint.

| Access Path | Target | Key Controls |
| --- | --- | --- |
| Admin workstation → Kubernetes API | Control plane endpoint | Endpoint mode, routes, appropriate firewall/allowlist, IAM/authn, Kubernetes authorization. |
| Control plane → worker nodes | Node control/management channel | Connectivity required by GKE architecture and cluster networking. |
| Pod → Pod/Service | Internal data plane | VPC-native networking, Kubernetes NetworkPolicy when enabled/supported, service routing. |
| Pod → Google APIs | Cloud Storage, Secret Manager, etc. | DNS/egress, IAM, Workload Identity Federation for GKE. |
| Node → Artifact Registry | Container image pulls | Node identity, OAuth scopes where applicable, and network path to registry. |

A private cluster does not automatically enable NetworkPolicy, manage Kubernetes permissions, or grant applications access to Cloud SQL or Cloud Storage.

## 3. Three Easily Confused Concepts

### 3.1. Private Nodes

**Private nodes** are nodes not assigned direct public IP addresses under private-cluster networking. Nodes communicate over VPC internal IPs and still require paths to essential services, such as:

- Google APIs and required GKE control/management services.
- Artifact Registry to pull container images.
- External package sources outside Google Cloud, if startup or applications genuinely need them.
- Cloud SQL, Cloud Storage, Pub/Sub, and business dependencies.

Having no external IP **does not mean a VM cannot make outbound connections**. Outbound traffic depends on routes, DNS, Private Google Access, Cloud NAT, Private Service Connect endpoints, or other supported mechanisms.

### 3.2. Private IP-Based Control-Plane Endpoint

A **private endpoint** is a connection path to the Kubernetes API via a **private IP address** provided by GKE per the cluster's architecture. With supported cluster modes and endpoint configurations, clients can administer the cluster from the VPC, a host with private routing to the endpoint, or properly routed hybrid connectivity.

Choosing a private endpoint avoids relying on exposing a public IP-based endpoint for administration. However:

- Clients from **Cloud Shell or an Internet laptop** do not automatically have a route to the private IP.
- You may need a bastion, VPN, Interconnect, or another designed administrative access path.
- The private endpoint may still be governed by authorized networks configured for the private endpoint **if that control mode is enabled/supported**, along with other endpoint access rules.
- Different cluster generations use different control plane connectivity technologies (including Private Service Connect-based architectures); do not apply every routing/VPC peering assumption from older clusters to newer ones.

### 3.3. DNS-Based Endpoint

GKE also supports a **DNS-based endpoint** for the Kubernetes control plane, manageable via endpoint access options and Google Cloud authentication. Google Cloud recommends this approach in many modern administrative workflows, particularly when enforcing **IAM** and controls such as **VPC Service Controls** in supported environments.

Crucial distinction: **a DNS-based endpoint is not the same as a private IP endpoint.** A DNS endpoint can be reached over the Internet/Google APIs path via supported mechanisms, while **who can connect** is controlled by authentication and IAM/policies. Thus, if internal policy mandates "the API must never be administered from outside the corporate network," you must check **whether the DNS endpoint is enabled or disabled**, not just private nodes or private endpoint flags.

Hostnames, IAM enforcement scope, and flags to enable/disable the DNS endpoint can vary across GKE/CLI versions. Always inspect actual endpoint state rather than inferring from a name like `private-cluster`.

## 4. Comparing Ways to Expose the Kubernetes API to Administrators

| Endpoint Type | Typical Connection Path | Controls to Watch | Misconception to Avoid |
| --- | --- | --- | --- |
| **Public IP-based endpoint** | Clients with Internet routing reach the API server's public endpoint. | Master Authorized Networks for IP endpoints, authentication, and authorization; cluster/org policies. | "Having a public IP means anyone can control the cluster" — false because authn/authz still apply; yet it widens the network surface. |
| **Private IP-based endpoint** | Clients in the VPC or networks with private routes to the control plane. | Network reachability, IP endpoint mode, IAM/RBAC, authorized networks on private endpoint when supported. | "Any VM in the VPC can reach it" — still depends on networks, routes, and policies. |
| **DNS-based endpoint** | Clients call the endpoint via DNS/Google APIs per GKE mechanisms. | IAM, endpoint access policies, VPC Service Controls where applicable, principal and Kubernetes authorization. | "A DNS name means a private address" — incorrect. |

### 4.1. Master Authorized Networks Is Not an IAM System

**Master Authorized Networks (MAN)** restricts **which source IP/CIDR ranges can reach IP-based control-plane endpoints** when using supported modes and endpoint types. It is a **network allowlist**, not a user directory, and does not replace Kubernetes authentication or authorization.

Example:

~~~text
Public IP-based endpoint: enabled
Authorized networks: 203.0.113.0/24   (illustrative CIDR per RFC 5737)

User A inside the CIDR range:
  May pass the source-IP check, but still needs authn/authz.

User B outside the CIDR range:
  Can be blocked at the network access layer even with a valid IAM account.
~~~

**MAN does not restrict the DNS-based endpoint in the same way as IP-based endpoints.** When the DNS endpoint is enabled, understand its distinct protective layers rather than relying solely on configured IP allowlists.

### 4.2. "Public Endpoint Disabled" Still Requires Checking the DNS Endpoint

A cluster with a private IP endpoint and no public IP-based endpoint may still expose a **DNS-based endpoint** if enabled. Therefore, security reports should record each setting explicitly:

~~~text
private nodes:              enabled/disabled
IP-based public endpoint:   enabled/disabled
IP-based private endpoint:  enabled/disabled
DNS-based endpoint:         enabled/disabled
authorized networks:        appropriate scope/allowlist
~~~

Never conclude whether a cluster is reachable from the Internet based solely on a single `privateClusterConfig` field in `gcloud describe` output.

### 4.3. Choosing a Model by Objective

| Objective | Design to Evaluate |
| --- | --- |
| Nodes without external IPs; office admins need API access. | Private nodes + private IP endpoint + VPN/Interconnect or secured bastion. |
| Distributed team administering from multiple networks with strict identity controls. | DNS-based endpoint with appropriate IAM/policies and explicit network access scope decisions. |
| Public IP endpoint still permitted for approved scenarios. | Narrow Master Authorized Networks, least-privilege IAM/RBAC, and access monitoring. |
| Organization requires strictly private paths to the Kubernetes API. | Evaluate both IP-based and DNS-based endpoints, administer from private networks, and test that no unintended path remains. |
| Organization uses VPC Service Controls. | Check support and configure perimeters for GKE-supported DNS endpoints/APIs; do not treat VPC SC as a traditional firewall. |

## 5. Networking for a Private GKE Cluster

### 5.1. VPC-Native, Subnets, and Secondary Ranges

GKE typically uses **VPC-native networking** (alias IPs) for modern clusters. Illustrative IP layout:

~~~text
Project: retail-lab
VPC: retail-vpc
Region: asia-southeast1

Primary subnet range (nodes):      10.30.0.0/20
Secondary range (Pods):            10.40.0.0/16
Secondary range (Services):        10.50.0.0/20
Private control-plane range
  (for architectures requiring a dedicated CIDR): 172.16.0.0/28

On-premises network:               192.168.100.0/24
~~~

These are **illustrative addresses**, not an allocated IP plan. Whether a private control-plane CIDR is required and how it is managed depend on the **cluster type and control-plane architecture**; not every new cluster requires `--master-ipv4-cidr`. For subnets and secondary ranges, size for Pod/Service/Node counts and growth over the cluster lifecycle.

Check for **overlaps** among:

- The primary subnet for nodes.
- Pod secondary range and Service secondary range.
- Control-plane endpoint/peering ranges if required by the architecture.
- Other VPCs, on-premises networks, and networks connected over VPN/Interconnect.

If CIDRs conflict, traffic may route incorrectly or cluster creation/configuration may fail. Changing CIDRs after a cluster holds workloads is difficult and often requires migration; never broaden firewall allowlists just to mask a routing conflict.

### 5.2. Control Plane Connectivity to Worker Nodes

GKE manages control plane components, yet the cluster still requires **management paths to nodes** and components such as webhooks or metrics servers depending on the architecture. When creating a private cluster:

1. Select the right VPC, subnet, and region/zone.
2. Review GKE-created/managed firewall rules and any organization-level network policies.
3. When deploying custom **webhooks** or components called by the API server, verify ports, paths, and certificates.
4. Never delete GKE-created firewall rules just because their names look unfamiliar; verify their exact purpose before making changes.
5. Read the networking docs for your cluster type to distinguish modern control plane connectivity from traditional VPC peering.

**A private cluster does not automatically mean all data-plane traffic is encrypted end-to-end.** Inter-service encryption, network segmentation, and authentication are separate layers.

### 5.3. Egress from Private Nodes

A node without an external IP still needs to pull container images, send metrics/logs, and occasionally fetch package updates. Several approaches exist:

| Destination | Options to Evaluate | Notes |
| --- | --- | --- |
| Google APIs / Cloud Storage | Private Google Access or supported private Google APIs solutions; proper DNS/routes/IAM. | PGA does not grant IAM permissions and does not replace egress policies. |
| Artifact Registry | Path to registry hostname, IAM Reader for node identity, and matching private access config. | `*.pkg.dev` requires checking DNS and supported endpoints; do not assume it behaves identically to `*.googleapis.com`. |
| Package repos / public Internet | Cloud NAT or managed egress proxy/firewall if needed. | Cloud NAT is outbound NAT; it **does not** open inbound SSH to nodes. |
| Cloud SQL private IP | Appropriate private networking/service connection plus database auth. | Network reachability to the DB does not grant table permissions. |
| Enterprise systems | Cloud VPN/Interconnect, Cloud Router/BGP, and hybrid DNS as needed. | Verify return paths and egress/ingress policies. |

**Never assign external IPs to all nodes** just to resolve an image pull failure. Diagnose DNS, TCP 443, IAM, OAuth scopes (where applicable), and proxy/NAT per destination.

### 5.4. Administration Over Hybrid Connectivity

Engineers may need to reach a private control-plane endpoint from the corporate network:

~~~mermaid
flowchart LR
    LAP["Laptop on corporate network"] --> ON["On-premises router"]
    ON --> VPN["HA VPN / Interconnect"]
    VPN --> VPC["GCP VPC: retail-vpc"]
    VPC --> API["Private IP-based endpoint\nGKE control plane"]
    API --> CL["Cluster resources"]
    IAM["IAM + Kubernetes authorization"] -. "Verify identity and permissions" .-> API
~~~

Proper routing to the private endpoint, firewalls, and global access settings per supported region/topology are required. If administrators sit in a different region from the control plane, verify **master global access** or cross-region access mechanisms rather than assuming a private endpoint is reachable from every region by default.

## 6. Protecting the Control Plane in Multiple Layers

### 6.1. Network and Endpoint Layer

Decide explicitly:

- Will a **public IP endpoint** be enabled?
- If yes, how does **Master Authorized Networks** restrict sources?
- Is the **private IP endpoint** enabled for internal administrative channels?
- Is the **DNS endpoint** enabled? Which principals/IAM policies may connect?
- Where do operations and CI/CD network paths traverse, who owns them, and are they logged/audited?

Do not optimize a single criterion (such as disabling the public endpoint) while forgetting that CI/CD pipelines or observability tools need Kubernetes API access to deploy and troubleshoot.

### 6.2. Identity Layer: Google Cloud IAM

**IAM** governs actions on GKE/Google Cloud resources: viewing clusters, fetching endpoint metadata/credentials, modifying cluster config, calling protected APIs, and supported integrated permissions.

Examples:

| Principal | Need | Required Scope |
| --- | --- | --- |
| Platform admin | Manage clusters and endpoint configs. | Appropriate GKE admin role, with approval for sensitive changes. |
| Developer | View workload status in one namespace. | Required cluster read metadata + narrow Kubernetes authorization. |
| CI deployer | Update Deployments/Services in an assigned namespace. | Cluster connection permission + matching Kubernetes authorization; no project-wide Owner. |
| Security auditor | Review IAM, API audit logs, and network configs. | Appropriate Reader/Auditor roles, without cluster modification rights. |

Common GKE IAM roles include `roles/container.clusterViewer`, `roles/container.developer`, and `roles/container.admin`; **never choose solely by role name**. Inspect actual permissions and project/cluster scope impact, especially when combined with Kubernetes RBAC.

### 6.3. Kubernetes Layer: Authorization and RBAC

Kubernetes uses **Role/ClusterRole** and **RoleBinding/ClusterRoleBinding** to govern Kubernetes API calls. GKE also integrates **Google Cloud IAM authorization** for supported Kubernetes operations; effective permissions may therefore involve both IAM and RBAC.

**Do not claim that every case strictly requires both an IAM Kubernetes resource role and an RBAC binding**, or that a single RBAC binding bypasses endpoint/IAM controls. Always check the authentication path, IAM permissions, and active Kubernetes policies.

~~~mermaid
flowchart TD
    U["Principal: developer@example.com"] --> PATH["Connection path to endpoint"]
    PATH --> AUTHN["Authentication / principal identity"]
    AUTHN --> AUTHZ["Kubernetes authorization\nRBAC and/or GKE IAM per model"]
    AUTHZ --> NS["Namespace: retail"]
    NS --> P["Read Pods / Services"]
    NS -. "Not automatically granted" .-> SEC["Secrets / cluster-wide admin"]
~~~

Least privilege principle: a developer who only needs to view Pods/Services in the `retail` namespace **must not** be granted `cluster-admin` just to silence a `kubectl get pods` error.

### 6.4. Kubernetes RBAC Example for Namespace Read Access

The manifests below **only illustrate** granting Pod and Service read access to an eligible identity. Do not apply them before verifying the exact principal that GKE authentication maps to the Kubernetes username:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: retail-observer
  namespace: retail
rules:
  - apiGroups: [""]
    resources: ["pods", "services"]
    verbs: ["get", "list", "watch"]
~~~

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: retail-observer-binding
  namespace: retail
subjects:
  - kind: User
    name: developer@example.com
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: retail-observer
  apiGroup: rbac.authorization.k8s.io
~~~

This Role **does not grant permission to read Secrets**, edit Deployments, or create ClusterRoleBindings. Creating a RoleBinding alters access permissions and must be approved by an admin. If the organization uses Google Groups for RBAC, identity setup and `subjects.kind: Group` follow a dedicated procedure; do not simply swap `User` for a group email without verifying integration.

### 6.5. Workload Identity Is Not Cluster Admin Permission

**Workload Identity Federation for GKE** lets Pods use a Kubernetes/Google Cloud identity per architecture to call Google APIs without embedding static service account keys. It solves **application runtime permissions** such as reading Cloud Storage or Secret Manager; **it does not grant developers `kubectl` access**.

Likewise, a node service account with Artifact Registry pull rights does not automatically grant `cluster-admin` to Pods. Separating the **GKE management principal**, **image-pull principal**, and **runtime principal** is essential.

## 7. Two Common Ways to Administer a Private IP Endpoint

### 7.1. Bastion VM Protected by IAP

A **bastion** is a managed VM inside the VPC with a route to the private IP endpoint. Engineers can use **IAP TCP forwarding** to SSH into the bastion **without an external IP**, then run `gcloud` and `kubectl` from the bastion.

~~~mermaid
flowchart LR
    USER["Engineer laptop"] --> IAP["IAP TCP forwarding"]
    IAP --> B["Bastion VM: internal IP"]
    B --> API["GKE private control-plane IP"]
    API --> K["Kubernetes API resources"]
    IAM["IAM + Kubernetes RBAC"] -. "Authorization" .-> API
~~~

Layers to distinguish:

1. **IAP IAM** allows opening a TCP tunnel to the bastion.
2. **OS Login / SSH policy** controls who can log into the bastion OS.
3. **VPC/private routes and firewalls** allow the bastion to reach the private endpoint.
4. **GKE IAM / Kubernetes authorization** governs API calls to the cluster.

**IAP does not directly turn a Kubernetes private endpoint into an IAP-protected Kubernetes API.** In this architecture, IAP protects access to the **bastion VM**; the Kubernetes API still enforces its own endpoint policies and authorization.

### 7.2. Administration Over Cloud VPN or Interconnect

If the enterprise already runs HA VPN or Cloud Interconnect:

- The on-premises/VPC link must advertise and learn the proper routes.
- The control plane private endpoint must have a supported access path in the topology.
- Firewalls, endpoint access mode, and geographic scope must permit access.
- Kubernetes authentication/authorization still applies as normal.

Do not treat **Cloud Router BGP Established** as proof that `kubectl` will work. BGP solves only one routing piece; DNS, TCP 443, endpoint mode, IAM/RBAC, and API availability must be verified separately.

### 7.3. When to Use the DNS Endpoint?

A globally distributed team may consider the DNS endpoint to administer via **IAM identity** and supported protections instead of maintaining a VPN on every personal device. However:

- Explicitly approve **which network types may call the API**.
- Verify endpoint authorization, IAM Conditions, and VPC Service Controls where used.
- Restrict sensitive principals, enforce MFA, and manage CLI credentials.
- Audit access events and cluster modifications.

If internal policy mandates a private network path only, **never enable the DNS endpoint casually just to work around a timeout**.

## 8. Hands-On gcloud: Inspecting Configuration Before Changing Anything

### 8.1. Prepare Context

Commands in this section use **Bash** with illustrative resource and project names. Commands with `create`, `update`, or `enable` **modify real resources, may incur costs, and can break administrative access**; run them only in an approved test project.

~~~bash
PROJECT_ID="retail-lab"
REGION="asia-southeast1"
CLUSTER="retail-private"
NETWORK="retail-vpc"
SUBNET="gke-subnet"

# READ-ONLY: check active principal and CLI project.
gcloud auth list
gcloud config get-value project

# READ-ONLY: list clusters visible to the account.
gcloud container clusters list \
  --project="$PROJECT_ID"
~~~

### 8.2. Read the Full Control Plane Endpoint Configuration

~~~bash
# READ-ONLY: inspect existing GKE configuration.
gcloud container clusters describe "$CLUSTER" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format=yaml
~~~

In the output, examine these field groups **when present in the cluster schema**:

| Field Group | Question |
| --- | --- |
| `privateClusterConfig` | How are private nodes and the private endpoint configured? |
| `controlPlaneEndpointsConfig` | How are IP-based and DNS-based endpoint access set in supported APIs/versions? |
| `masterAuthorizedNetworksConfig` | Is there a CIDR allowlist for IP-based endpoints? |
| `network`, `subnetwork`, `networkConfig` | Which VPC/subnet does the cluster live in? |
| `ipAllocationPolicy` | Which Pod and Service CIDRs/secondary ranges are used? |
| `releaseChannel`, version, and cluster mode | Do endpoint settings or capabilities depend on version/mode? |

Never rely on **a single field** to claim a cluster is "secure." Verify actual endpoint access, IAM/RBAC, VPC connectivity, and organizational policies. Some fields appear in newer formats or are omitted when unsupported; use `--format=yaml` before writing automated filters.

### 8.3. Check Subnet and Secondary Ranges

~~~bash
# READ-ONLY: inspect subnet and secondary IP ranges.
gcloud compute networks subnets describe "$SUBNET" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="yaml(name,network,ipCidrRange,secondaryIpRanges,privateIpGoogleAccess)"

# READ-ONLY: inspect network.
gcloud compute networks describe "$NETWORK" \
  --project="$PROJECT_ID" \
  --format="yaml(name,subnetworks,routingConfig)"
~~~

If using **Shared VPC**, the subnet resides in the **host project**, while the cluster may live in a service project. Read and assign permissions in the right project; never assume cluster and subnet live in the same project simply because names match.

## 9. Illustrating Private GKE Standard Cluster Creation

### 9.1. Design Before Running the Command

Assume the learner already has:

- A lab project authorized to create GKE clusters.
- VPC `retail-vpc` and subnet `gke-subnet` in `asia-southeast1`.
- A primary subnet range for nodes, plus properly sized secondary ranges named `gke-pods` and `gke-services`.
- An administrative access path from a **bastion/VPC** to the private IP endpoint.
- Approved IAM, quotas, egress paths, and cluster/node budget.
- A **non-overlapping** private IP range for the control plane if the cluster architecture requires specifying one.

**Crucial:** enabling the private endpoint can cause `kubectl` from an admin workstation outside the VPC to **lose connectivity**. Before creating or switching a production cluster to a private endpoint, verify the alternative administrative path.

### 9.2. Cluster Creation Example

The following command illustrates a **GKE Standard cluster** configured with a private IP endpoint using a dedicated master CIDR. Some newer GKE models use different control-plane networking and do not require `--master-ipv4-cidr` in the same way; check CLI help and docs for the cluster model you are creating.

~~~bash
# WRITE: illustrative GKE Standard cluster creation in an authorized sandbox.
gcloud container clusters create retail-private \
  --project=retail-lab \
  --region=asia-southeast1 \
  --network=retail-vpc \
  --subnetwork=gke-subnet \
  --enable-ip-alias \
  --cluster-secondary-range-name=gke-pods \
  --services-secondary-range-name=gke-services \
  --enable-private-nodes \
  --enable-private-endpoint \
  --master-ipv4-cidr=172.16.0.0/28 \
  --num-nodes=1
~~~

Values are for learning only; **do not run this verbatim without verifying subnet ranges, region, and control-plane CIDR**. For a regional Standard cluster, `--num-nodes=1` typically means one node **per zone** across default node locations, so actual VM count and cost may exceed one.

Key flags:

| Flag | Meaning |
| --- | --- |
| `--enable-ip-alias` | Enables VPC-native / alias IP networking. |
| `--cluster-secondary-range-name` | Selects the secondary range for Pod IPs. |
| `--services-secondary-range-name` | Selects the secondary range for Kubernetes Services. |
| `--enable-private-nodes` | Requests private node networking. |
| `--enable-private-endpoint` | Selects the private IP-based endpoint per supported mechanism, avoiding the public IP-based path in this example. |
| `--master-ipv4-cidr` | Range reserved for control-plane connectivity in cluster models requiring this parameter. |
| `--num-nodes` | Initial node count per cluster zone/region semantics. |

**Check the DNS-based endpoint independently after creation**, as selecting a private IP endpoint does not make a statement about the DNS endpoint across all versions and modes.

### 9.3. Endpoint Settings Can Vary by Product Generation

In newer deployments, Google Cloud may offer **DNS-based endpoint access** modes or separate toggles for IP-based access. When updating endpoints on an existing cluster:

1. Run `gcloud container clusters describe` to record the current state.
2. Read `gcloud container clusters update --help` for your current CLI version.
3. Confirm impact on both **IP-based** and **DNS-based** access.
4. Review network paths for users, CI/CD, GitOps controllers, and SREs.
5. Keep an active administrative session open to verify settings after the change.

Never use a one-size-fits-all command to disable endpoints across every cluster type, as one wrong flag can sever administrative access before an alternative channel is ready.

## 10. Fetching kubeconfig and Targeting the Right Endpoint

### 10.1. Private IP Endpoint

From a **bastion or machine with a private route** to the endpoint:

~~~bash
# READ/LOCAL WRITE: fetch cluster info and update user's kubeconfig.
gcloud container clusters get-credentials retail-private \
  --project=retail-lab \
  --region=asia-southeast1 \
  --internal-ip

# READ-ONLY Kubernetes API, though requires route, authentication, and permission.
kubectl cluster-info
kubectl get namespaces
kubectl get nodes
~~~

`get-credentials` may succeed because it calls the **Google Cloud Container API** to fetch metadata, yet `kubectl` still **times out** afterward if the machine lacks a route to the private Kubernetes API endpoint. This is the crucial difference between **permission to read cluster config** and **TCP/TLS reachability to the API server**.

`kubectl get nodes` may fail with `Forbidden` even while `kubectl cluster-info` or `kubectl get namespaces` succeeds, if Kubernetes authorization does not allow reading node resources.

### 10.2. DNS-Based Endpoint

For a cluster with the **DNS endpoint enabled and permitted**:

~~~bash
# READ/LOCAL WRITE: fetch kubeconfig pointing to the DNS-based endpoint.
gcloud container clusters get-credentials retail-private \
  --project=retail-lab \
  --region=asia-southeast1 \
  --dns-endpoint

# READ-ONLY: verify server endpoint and current context.
kubectl config current-context
kubectl config view --minify
~~~

If the DNS endpoint is disabled, IAM permissions are insufficient, or VPC Service Controls block access, subsequent commands may fail. Fetching kubeconfig via DNS does not mean you are authorized to perform every Kubernetes operation.

**Safety when viewing kubeconfig:** the file contains server URLs, CA data, and credential plugin commands; never paste raw kubeconfig or tokens into public logs or tickets. Avoid `kubectl config view --raw` in environments with uncontrolled logging.

### 10.3. `gke-gcloud-auth-plugin`

Modern GKE/`kubectl` versions use **`gke-gcloud-auth-plugin`** to obtain Google Cloud credentials for Kubernetes API authentication. If a machine lacks the plugin or the CLI uses the wrong account, `kubectl` will fail even when the network path to the endpoint is healthy.

~~~bash
# READ-ONLY: check gcloud principal and auth tooling.
gcloud auth list
gcloud version
gke-gcloud-auth-plugin --version

# READ-ONLY Kubernetes authorization (when the endpoint is reachable).
kubectl auth can-i list pods -n retail
kubectl auth can-i create deployments -n retail
kubectl auth can-i get secrets -n retail
~~~

`kubectl auth can-i` checks authorization at call time per supported API rules; it is not a tool proving all IAM/org policies are secure. For user/group bindings, verify the actual authenticated identity and target namespace.

### 10.4. Verifying the Endpoint in kubeconfig

After `get-credentials`, kubeconfig sets the **context**, cluster `server`, and auth method. When managing multiple environments:

- Clearly label project, cluster, and region on each context.
- Check `kubectl config current-context` before running any write command.
- Pass `--namespace` or use isolated contexts to avoid editing the wrong namespace.
- Separate staging and production permissions, and require review for RBAC changes.
- Never commit kubeconfig files containing sensitive environment details to repositories.

## 11. Securing Administrative Paths from Laptops and CI/CD

### 11.1. Developers Only Need to View a Namespace

Suppose `developer@example.com` needs to view Pods in the `retail` namespace without editing node pools. Design:

1. IAM allows identifying/reading cluster config and authenticating through the approved endpoint.
2. Endpoint mode and network path allow connectivity.
3. Kubernetes RBAC / IAM authorization grants read access only to required resources.
4. Logs capture sensitive administrative actions per policy.

**Do not grant `roles/container.admin` or a `cluster-admin` ClusterRoleBinding** just to fix a `Forbidden` error in one namespace.

### 11.2. CI/CD Deployer

A pipeline may need to update a `Deployment` in `retail-prod`. Separate responsibilities:

- **CI build identity:** builds images and pushes to Artifact Registry.
- **Deployer identity:** connects to the Kubernetes API and updates assigned resources.
- **Node identity:** pulls images from Artifact Registry.
- **Pod workload identity:** calls Cloud SQL, Cloud Storage, or Secret Manager at runtime.

If CI runs outside the VPC and the cluster has only a private endpoint, the pipeline needs a **valid network path**—such as a VPC-hosted runner, VPN/hybrid connectivity, or the DNS endpoint if policy allows. Never turn on the public endpoint and allow `0.0.0.0/0` just to make the pipeline run.

### 11.3. In-Cluster GitOps Controllers

A GitOps controller running **inside the cluster** can apply Kubernetes manifests without giving every developer direct private-IP access. Even so:

- Scope and audit what cluster permissions the controller holds.
- Secure how the controller pulls and authenticates against Git/artifacts.
- Require review and provenance tracking for manifests and revisions.
- Enforce separate approval workflows for cluster-level updates or sensitive RBAC changes.
- Note that during a cluster/control-plane outage, GitOps reconciliation cannot act until the control plane recovers.

This is an operational architecture, **not a reason to disable Kubernetes API authentication or authorization**.

## 12. Do Not Confuse Control Plane Protection with Workload Security

### 12.1. A Private Cluster Can Still Expose a Public Service

A cluster using private nodes and a private endpoint can still expose an **external Application Load Balancer** or a public `LoadBalancer` `Service` depending on controller/config support. That is completely separate from a **public control-plane endpoint**:

~~~text
Kubernetes API (control plane):
  private IP-based endpoint for administration

Application frontend:
  public HTTPS load balancer → Ingress/Gateway/Service → Pods
~~~

To keep an application **internal-only**, configure an **internal load balancer**, matching annotations/controllers, firewalls, and authentication. Never expect private nodes alone to make applications private.

### 12.2. Pod-to-Pod and Egress Policies

Once the control plane is protected, workloads still require:

- **Kubernetes NetworkPolicy** or GKE Dataplane V2 policies where available to restrict traffic between namespaces and Pods.
- **Workload Identity Federation for GKE** so Pods call Google APIs with least privilege and no static keys.
- **Pod Security Standards / admission controls** to curb privileged containers.
- **Image provenance**, scoped Artifact Registry access, vulnerability scanning, and Binary Authorization where appropriate.
- **Secrets management**, KMS, and rotation aligned to data sensitivity.
- **Cloud Logging/Monitoring** with appropriate audit access.

Having no external IP on nodes does not stop a Pod from sending data to the Internet if Cloud NAT and egress policies allow it. Controlling egress requires inspecting Pod-level policies, VPC firewalls, and NAT/proxies.

### 12.3. GKE Standard and Autopilot

Standard and Autopilot differ in node control, resource management, and supported networking/security options. When reading `gcloud container clusters create ...` examples:

- The example in Section 9 targets a **Standard cluster**.
- For **Autopilot**, use the `create-auto` flow and verify product-supported private networking and control-plane endpoint settings.
- Do not blindly copy Standard's `--num-nodes`, node-pool flags, or master CIDR flags to Autopilot.
- Evaluate Autopilot based on operational scope, workload compatibility, and real cost—not merely the word "private."

## 13. Deployment Scenario: Retail Production GKE

### 13.1. Requirements

An enterprise runs:

- A **GKE Standard regional cluster** hosting `catalog-api` and asynchronous workers.
- **Cloud Run** serving part of the API outside the cluster.
- **Artifact Registry** storing verified images.
- **Cloud SQL** via private connectivity in the designated region.
- **Cloud Storage** storing product images.
- Corporate internal systems connected via **HA VPN/Interconnect** for administration.
- CI/CD performing rollouts using a dedicated identity.

Security requirements:

1. GKE nodes have no external IPs.
2. Administration does not rely on a public IP-based control-plane endpoint.
3. Office staff/SREs have policy-compliant access to the Kubernetes API.
4. CI/CD does not receive permanent `cluster-admin`.
5. Pods can access only the required Google APIs.

### 13.2. Proposed Design

| Component | Illustrative Decision | What to Verify |
| --- | --- | --- |
| Cluster | GKE Standard regional, VPC-native. | Secondary IP ranges, zone count, quotas, and version. |
| Nodes | Private nodes, dedicated node SA. | No external IPs; egress and image pulls work. |
| Control plane | Private IP-based endpoint; DNS endpoint per org policy (deliberately enabled or disabled). | Presence or absence of unintended admin paths. |
| SRE path | Hybrid route to private endpoint or IAP bastion in VPC. | DNS/TCP 443, endpoint access, and authn/authz. |
| Namespace access | Appropriate Kubernetes Role/RoleBinding or Google IAM authorization. | No unnecessary cluster-wide edit rights. |
| CI/CD | Runner with network path; narrowly scoped deployer identity. | No long-lived JSON keys or allowlist bypasses. |
| Image pull | Node identity with Artifact Registry Reader. | Cross-project repo IAM, OAuth scopes, and egress. |
| Pod identity | Workload Identity Federation for GKE. | Minimal Cloud SQL/Storage/Secret Manager roles. |
| Service exposure | Public or internal Application LB per API. | Never confuse public Service with public control plane. |
| Monitoring | Audit Logs, `kubectl` failures, node readiness, app SLIs. | Runbooks and layered alerts in place. |

### 13.3. Flow of a Deployment

~~~mermaid
sequenceDiagram
    participant DEV as Developer
    participant CI as CI/CD
    participant AR as Artifact Registry
    participant API as GKE private control plane
    participant N as GKE node
    participant W as Pod workload
    DEV->>CI: Merge approved commit
    CI->>AR: Push image, receive digest
    CI->>API: Call Kubernetes API via approved admin path
    Note over CI,API: IAM, endpoint access, and authorization
    API->>N: Reconcile Pod/Deployment
    N->>AR: Pull image using node identity
    N->>W: Start container
    W-->>API: Readiness / resource status
    W->>AR: No image push needed at runtime
~~~

Actual flows involve more steps (scheduler, kubelet, admission, and controllers). The key takeaway is that **CI→control plane**, **node→registry**, and **Pod→data permissions** are three independent control planes.

### 13.4. Incident Drills

1. **SRE outside the VPC cannot call the API:** check private routes/bastion instead of opening an uncontrolled public endpoint.
2. **CI gets `Forbidden` updating a Deployment:** inspect Kubernetes authorization and principal; do not grant `cluster-admin`.
3. **Pod hits `ImagePullBackOff`:** check node identity, registry URI, and egress; do not alter the control-plane endpoint.
4. **Public app API receives unauthorized traffic:** inspect Ingress, load balancer, WAF, and app authentication; a private control plane does not protect user HTTP APIs.
5. **All nodes fail to pull images:** check Artifact Registry access, NAT/PGA/registry DNS, and network policies.
6. **On-prem VPN goes down:** test the backup administrative path (approved bastion or endpoint mode), designated owner, and recovery time.

## 14. Troubleshooting: Separating Networking, Identity, and Kubernetes RBAC

| Symptom | Possible Causes | How to Inspect |
| --- | --- | --- |
| `gcloud get-credentials` succeeds, `kubectl` times out | Machine lacks a route to the private IP endpoint, or VPN/bastion/firewall/DNS fails. | Inspect kubeconfig server, cluster endpoint config, TCP 443, and network path. |
| `kubectl` reports `Unauthorized`/401 | Missing/expired token or auth plugin, or unrecognized principal. | `gcloud auth list`, `gke-gcloud-auth-plugin`, auth session. |
| `kubectl` reports `Forbidden`/403 | Principal authenticated, but not authorized for Kubernetes action; IAM/RBAC/endpoint policy. | `kubectl auth can-i`, RoleBindings, IAM permissions, and logs. |
| `get-credentials --internal-ip` then running from Cloud Shell fails | Cloud Shell is not automatically on the same VPC/private route to the control plane. | Use an approved admin path; do not open a public IP arbitrarily. |
| DNS endpoint fails | DNS access disabled, missing IAM, blocked by VPC SC/policy, or DNS/egress error. | Endpoint config, principal, API access, and logs. |
| Private endpoint reachable from only part of the network | Routing/peering, private endpoint authorized networks if active, or regional/global access limits. | Inspect network paths, endpoint mode, and actual CIDRs. |
| Cluster creates, yet nodes stay `NotReady` | Node egress/GKE management path, VM startup, quotas, firewalls, or guest/system issue. | GKE/node pool status, node logs, VPC/firewalls/Google APIs. |
| Pod `ImagePullBackOff` | Node identity missing Reader, wrong image URI/digest, OAuth scopes, or egress. | `kubectl describe pod`, Artifact Registry IAM, node networking. |
| Pod cannot call Cloud Storage | Workload identity/IAM, DNS/Google APIs egress, missing token, or VPC SC. | ServiceAccount mapping, IAM, request logs, networking. |
| External Service unreachable | Load balancer/Ingress controller, firewalls, backend health, DNS, or app auth. | LB frontend/backend health and app logs—do not focus on control plane. |
| CI can still edit cluster after revoking a RoleBinding | Another binding, IAM authorization, group membership, or higher-scope permission exists. | Audit effective permissions across all layers, not one RBAC file. |

### 14.1. Seven-Step Investigation Sequence

1. **Right cluster?** Verify project, region, cluster name, kubecontext, and server endpoint.
2. **Which endpoints are active?** Inspect IP/DNS endpoint config, private/public access, and authorized networks.
3. **Which network is the client on?** Laptop, Cloud Shell, bastion, VPC runner, VPN, or another region.
4. **Does TCP/TLS reach the Kubernetes API?** If not, check routes, DNS, firewalls, and endpoint mode first.
5. **Does authentication work?** Check gcloud principal, credential plugin, tokens, and IAM.
6. **Does authorization work?** Check `kubectl auth can-i`, RBAC/IAM, and namespace.
7. **Is the workload healthy?** If the API works while Pods fail, investigate nodes, registry, network policies, and the app.

Never debug a `403 Forbidden` by changing Pod CIDRs. Never edit IAM when the real failure is a network timeout to a private endpoint.

## 15. Auditing, Configuration Changes, and Admin Recovery

### 15.1. Events to Monitor

- Who creates/deletes GKE clusters or changes endpoint access, authorized networks, or network settings?
- Who grants IAM roles or creates/edits sensitive RoleBindings/ClusterRoleBindings?
- Which principals log in or deploy workloads, according to enabled audit logs?
- Are there out-of-band changes to node pools, network policies, service accounts, or public Ingresses?
- Is there a spike in failed `kubectl` calls due to auth, networking, or permission denials?
- What are API operation success rates, control plane/node health, and application SLOs?

**Cloud Audit Logs and GKE/Kubernetes control plane logging** have distinct scopes, log types, pricing, and retention policies. Never assume every resource read or every `kubectl` command is logged by default; verify each audit log category and configuration explicitly.

### 15.2. Avoiding Self-Lockout

Changes that commonly break administrative access:

1. Switching to a private IP endpoint while CI/SRE only connect from the Internet.
2. Disabling the DNS endpoint while pipelines strictly rely on `--dns-endpoint`.
3. Tightening authorized networks while forgetting the operations team's actual NAT egress IP.
4. Deleting a platform admin RoleBinding before verifying replacement access.
5. Changing firewall or VPN routes without testing private control-plane traffic.

Before making changes:

- Record current endpoint, IAM/RBAC, and VPC route configurations.
- Establish and test an **alternative admin path** from the actual principal.
- Review policy changes via IaC/merge requests with designated approvers.
- Maintain an organization-approved rollback/break-glass procedure with event logging.
- After the change, verify `get-credentials` and a `kubectl get` over the intended endpoint/proxy.

Never assume "we can always reopen the API with another command" if the principal lost permissions or the network path was cut. Recovery plans must be designed and rehearsed in advance.

### 15.3. Automating Governance

Terraform or appropriate Infrastructure as Code tools can manage clusters, VPCs/subnets, endpoint modes, IAM, and node pools. Kubernetes manifests/GitOps manage in-cluster resources per ownership boundaries.

Avoid conflicts between:

- IaC managing IAM and cluster configuration.
- GKE auto-creating/managing firewall rules and underlying components.
- GitOps/Helm managing Kubernetes RoleBindings and Deployments.
- Operators making manual edits via Console or `gcloud`.

Establish a clear **source of truth**, code review, and drift detection so tool A doesn't enable an endpoint only for tool B to turn it back off on the next apply.

## 16. Cost and Reliability

### 16.1. Is a Private Cluster Free?

**No.** Private networking is an architectural and security choice. Costs may arise from:

| Component | Costs to Account For |
| --- | --- |
| GKE cluster | Cluster management fees per mode and current terms; Standard and Autopilot have different models. |
| Compute/node pools | vCPUs, memory, VM disks, node pool sizing, and autoscaling. |
| Networking | Cloud NAT, VPN/Interconnect, load balancers, data transfer, and IP/network services where applicable. |
| Artifact pulls | Artifact Registry storage/transfer, network paths, and related services. |
| Logging/monitoring | Log volume, retention, metrics/traces, and audit logs per pricing. |
| Security/admin | Bastion VMs, IAP/admin paths, policy engines, and optional security add-ons. |

Having no external IPs on nodes does not mean **zero outbound traffic charges** or **no need for Cloud NAT**. Cloud NAT, when used, carries its own pricing. Likewise, redundant VPNs boost admin path reliability but add cost and failure domains to track.

### 16.2. Control Plane HA Does Not Replace Workload HA

GKE manages the control plane per service design, yet application availability still depends on:

- Enough replicas across appropriate nodes and zones.
- Sensible readiness/liveness probes and PodDisruptionBudgets.
- Cluster autoscaling backed by sufficient quotas and capacity.
- Healthy Cloud SQL/Storage data tiers, VPC links, and backend load balancers.
- CI/CD fallback plans if the control-plane endpoint is temporarily unreachable.

A cluster with a well-secured private endpoint running only **one Pod** for all transactions will still go down if that Pod dies. Measure SLOs from the user's perspective, not just API server status.

### 16.3. Useful Operational Metrics

- Percentage of clusters whose endpoint access complies with policy.
- Count of principals holding `cluster-admin` or sensitive administrative IAM roles.
- Deployment success rate and `kubectl` errors caused by authorization or networking.
- Node readiness, Pod scheduling latency, and image pull failures.
- Connectivity health from on-premises/bastion/CI runners to the private endpoint.
- Out-of-window policy/network changes and recovery times.
- Log ingestion volume and network/cluster costs vs. budget.

## 17. Applied Exercises

### Exercise 1 — Are Private Nodes Enough?

A GKE cluster enables private nodes yet keeps a public IP-based Kubernetes API endpoint. Can you claim the API is "unreachable from the Internet"? If the organization wants a private-only admin path, which additional endpoints must be checked?

**Hint:** no. Check IP-based public/private endpoints and the DNS-based endpoint independently; design private admin paths and IAM/RBAC.

### Exercise 2 — `get-credentials` Succeeds Yet `kubectl` Times Out

An engineer runs `gcloud container clusters get-credentials ... --internal-ip` from a home laptop. Fetching credentials succeeds, yet `kubectl get pods` times out. Explain why both results are consistent and propose a controlled access path.

**Hint:** the Container API returns metadata for kubeconfig, while the laptop has no private route to the control plane; use an approved VPN or IAP bastion.

### Exercise 3 — IAM and RBAC

A developer must read Pods/Services in the `retail` namespace without editing cluster-wide RBAC. Describe the IAM permissions to view/connect to the cluster, a narrow Role/RoleBinding for the namespace, and how to verify with `kubectl auth can-i`. Why not grant `cluster-admin`?

### Exercise 4 — DNS Endpoint and Authorized Networks

The infrastructure team configured Master Authorized Networks on the public IP-based endpoint, then enabled the DNS-based endpoint. Does that IP allowlist automatically restrict the DNS endpoint in the exact same way? Which additional layers must be enforced?

**Hint:** no. Review IAM, endpoint access policies, VPC Service Controls where supported, and Kubernetes authorization; explicitly decide corporate network requirements.

### Exercise 5 — Private Nodes Cannot Pull Images

GKE private nodes report `ImagePullBackOff` for an image in another project's Artifact Registry. Check the node service account, IAM Reader on the source repo, OAuth scopes if applicable, DNS/egress to the registry, and image URI. Why won't editing a developer's RoleBinding fix this?

### Exercise 6 — Designing a Retail Cluster

Assume GKE, Cloud SQL, and Cloud Run are in Singapore; the corporate network uses VPN; assets are in Cloud Storage and images in Artifact Registry. Propose:

- Private/public/DNS control-plane endpoint mode.
- Kubernetes API paths for SREs and CI.
- Pod/Service CIDRs verified not to overlap on-premises networks.
- IAM separation across CI, nodes, and Pod runtime.
- SLO metrics, VPN-loss test cases, and recovery procedures.

### Exercise 7 — Finding the Wrong Layer

`kubectl get pods` works, yet a Pod cannot read Secret Manager. Must this be a control-plane endpoint issue? Outline checks for Workload Identity Federation for GKE, Secret Manager IAM, DNS/Google APIs egress, and application logs.

### Exercise 8 — Self-Lockout Scenario

A team wants to disable both the public IP endpoint and the DNS endpoint in production, yet CI currently runs solely on hosted runners outside the VPC. Build a migration plan for the CI path before altering endpoint settings, including validation and rollback steps.

## 18. Production Checklist and Official Documentation

| Item | What to Verify Before Deployment |
| --- | --- |
| **Cluster mode** | Standard/Autopilot and GKE version support the planned endpoint configuration. |
| **Private nodes** | No external IPs; working egress for images, node management, and Google APIs. |
| **IP endpoints** | Public/private IP endpoint mode matches policy; never infer from cluster name. |
| **DNS endpoint** | Enable/disable explicitly approved; IAM and VPC SC reviewed independently where applicable. |
| **Master Authorized Networks** | Narrow CIDRs on supported IP endpoints; never confuse with DNS endpoint IAM. |
| **VPC/IP planning** | Primary node range, Pod/Service secondary ranges, and control-plane range have zero overlap. |
| **Hybrid access** | VPN/Interconnect, routes, master global access if needed, and valid return paths. |
| **Bastion/IAP** | Bastion hardened; IAP IAM, OS Login/SSH, logs, and network paths verified. |
| **IAM** | Least-privilege separation across cluster admins, metadata readers, and deployers. |
| **Kubernetes authorization** | RBAC/IAM resource permissions, namespace boundaries, and `cluster-admin` reviews. |
| **Workload identity** | Node/image-pull identity separated from Pod runtime identity and data access. |
| **Network segmentation** | Ingress/LB, NetworkPolicy, firewalls, and egress policies per workload. |
| **Logging/audit** | Control plane, IAM, endpoint/network changes, and sensitive Kubernetes events monitored. |
| **CI/CD** | Valid API path, image digests, manifest reviews, rollback, and short-lived auth. |
| **Resilience** | Lockout-prevention runbooks, multi-zone Pods, and VPN/endpoint loss drills. |
| **Cost** | GKE/nodes/networking/NAT/VPN/bastion/logging/transfer budgeted and tracked. |

Official Google Cloud documentation to verify against the latest cluster modes, versions, and endpoint capabilities:

- [GKE cluster networking overview](https://cloud.google.com/kubernetes-engine/docs/concepts/cluster-networking)
- [GKE private clusters](https://cloud.google.com/kubernetes-engine/docs/concepts/private-cluster-concept)
- [Create a private GKE Standard cluster](https://cloud.google.com/kubernetes-engine/docs/how-to/legacy/network-isolation)
- [Customize control plane access](https://cloud.google.com/kubernetes-engine/docs/how-to/control-plane-authorized-networks)
- [GKE DNS-based endpoint](https://cloud.google.com/kubernetes-engine/docs/concepts/about-control-plane-endpoints)
- [GKE access control](https://cloud.google.com/kubernetes-engine/docs/concepts/access-control)
- [Kubernetes RBAC with GKE](https://cloud.google.com/kubernetes-engine/docs/how-to/role-based-access-control)
- [GKE Workload Identity Federation](https://cloud.google.com/kubernetes-engine/docs/concepts/workload-identity)
- [VPC-native clusters](https://cloud.google.com/kubernetes-engine/docs/concepts/alias-ips)
- [Private Google Access](https://cloud.google.com/vpc/docs/private-google-access)
- [IAP TCP forwarding](https://cloud.google.com/iap/docs/using-tcp-forwarding)
- [gcloud container clusters reference](https://cloud.google.com/sdk/gcloud/reference/container/clusters)

**Key takeaway:** GKE private nodes reduce the network exposure of **worker nodes**, while control-plane access must be protected **separately** through IP/DNS endpoint choices, approved connection paths, IAM, and Kubernetes authorization. Private IPs do not replace RBAC; a DNS endpoint does not imply a private IP; and IAM cannot fix a broken route. Separating those layers cleanly lets operations teams administer clusters safely, preserve recovery paths, and run applications with reliable performance and controlled cost.
